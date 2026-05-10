#!/usr/bin/env bash
set -euo pipefail

NEWS_RUNTIME_HOST="${NEWS_RUNTIME_HOST:-}"
if [[ -z "${NEWS_RUNTIME_HOST}" ]]; then
  echo "NEWS_RUNTIME_HOST must be set to your SSH host alias or hostname." >&2
  exit 2
fi
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

REMOTE_ROOT="${REMOTE_ROOT:-/opt/news-event-hub}"
REMOTE_CONFIG_DIR="${REMOTE_ROOT}/config"
REMOTE_SYSTEMD_DIR="${REMOTE_CONFIG_DIR}/systemd"
REMOTE_SCRIPT_DIR="${REMOTE_ROOT}/scripts"
REMOTE_DATA_DIR="${REMOTE_ROOT}/data"
REMOTE_STATE_DIR="${REMOTE_ROOT}/state"
REMOTE_LOG_DIR="${REMOTE_ROOT}/logs"
REMOTE_DB_PATH="${REMOTE_STATE_DIR}/news_event.db"
REMOTE_SCHEMA_PATH="${REMOTE_CONFIG_DIR}/schema.sql"

REQUIRED_FILES=(
  "${ROOT_DIR}/scripts/build_event_layer.py"
  "${ROOT_DIR}/config/schema.sql"
  "${ROOT_DIR}/config/source_registry_v1.yaml"
  "${ROOT_DIR}/data/entity_aliases_v1.csv"
  "${ROOT_DIR}/scripts/init_unified_news_db.py"
  "${ROOT_DIR}/config/systemd/unified-news-event-layer.service"
  "${ROOT_DIR}/config/systemd/unified-news-event-layer.timer"
)

echo "[deploy-event] host=${NEWS_RUNTIME_HOST}"
echo "[deploy-event] remote_root=${REMOTE_ROOT}"

"${ROOT_DIR}/scripts/deploy_runtime_repo_checkout.sh"

for path in "${REQUIRED_FILES[@]}"; do
  if [[ ! -f "${path}" ]]; then
    echo "[deploy-event] missing local file: ${path}" >&2
    exit 1
  fi
done

ssh "${NEWS_RUNTIME_HOST}" "python3 - <<'PY'
import importlib
for module in ('sqlite3',):
    importlib.import_module(module)
PY
test -w /etc/systemd/system"

ssh "${NEWS_RUNTIME_HOST}" "mkdir -p '${REMOTE_CONFIG_DIR}' '${REMOTE_SYSTEMD_DIR}' '${REMOTE_SCRIPT_DIR}' '${REMOTE_DATA_DIR}' '${REMOTE_STATE_DIR}' '${REMOTE_LOG_DIR}'"

scp "${ROOT_DIR}/scripts/build_event_layer.py" "${NEWS_RUNTIME_HOST}:${REMOTE_SCRIPT_DIR}/build_event_layer.py"
scp "${ROOT_DIR}/config/schema.sql" "${NEWS_RUNTIME_HOST}:${REMOTE_CONFIG_DIR}/schema.sql"
scp "${ROOT_DIR}/config/source_registry_v1.yaml" "${NEWS_RUNTIME_HOST}:${REMOTE_CONFIG_DIR}/source_registry_v1.yaml"
scp "${ROOT_DIR}/data/entity_aliases_v1.csv" "${NEWS_RUNTIME_HOST}:${REMOTE_DATA_DIR}/entity_aliases_v1.csv"
scp "${ROOT_DIR}/scripts/init_unified_news_db.py" "${NEWS_RUNTIME_HOST}:${REMOTE_SCRIPT_DIR}/init_unified_news_db.py"
scp "${ROOT_DIR}/config/systemd/unified-news-event-layer.service" "${NEWS_RUNTIME_HOST}:${REMOTE_SYSTEMD_DIR}/unified-news-event-layer.service"
scp "${ROOT_DIR}/config/systemd/unified-news-event-layer.timer" "${NEWS_RUNTIME_HOST}:${REMOTE_SYSTEMD_DIR}/unified-news-event-layer.timer"

ssh "${NEWS_RUNTIME_HOST}" "python3 '${REMOTE_SCRIPT_DIR}/init_unified_news_db.py' --db '${REMOTE_DB_PATH}' --schema '${REMOTE_SCHEMA_PATH}' --registry '${REMOTE_CONFIG_DIR}/source_registry_v1.yaml'"

ssh "${NEWS_RUNTIME_HOST}" "chmod +x '${REMOTE_SCRIPT_DIR}/init_unified_news_db.py' '${REMOTE_SCRIPT_DIR}/build_event_layer.py' && systemd-analyze verify '${REMOTE_SYSTEMD_DIR}/unified-news-event-layer.service' '${REMOTE_SYSTEMD_DIR}/unified-news-event-layer.timer' && cp '${REMOTE_SYSTEMD_DIR}/unified-news-event-layer.service' /etc/systemd/system/unified-news-event-layer.service && cp '${REMOTE_SYSTEMD_DIR}/unified-news-event-layer.timer' /etc/systemd/system/unified-news-event-layer.timer && systemctl daemon-reload && systemctl enable --now unified-news-event-layer.timer"

echo "[deploy-event] triggering first build"
if ! ssh "${NEWS_RUNTIME_HOST}" "systemctl start unified-news-event-layer.service"; then
  echo "[deploy-event] first event-layer start failed; retrying once after a short backoff"
  sleep 3
  ssh "${NEWS_RUNTIME_HOST}" "journalctl -u unified-news-event-layer.service -n 40 --no-pager || true"
  ssh "${NEWS_RUNTIME_HOST}" "systemctl reset-failed unified-news-event-layer.service || true"
  ssh "${NEWS_RUNTIME_HOST}" "systemctl start unified-news-event-layer.service"
fi

echo "[deploy-event] timer status"
ssh "${NEWS_RUNTIME_HOST}" "systemctl status unified-news-event-layer.timer --no-pager | sed -n '1,12p'"

echo "[deploy-event] service status"
ssh "${NEWS_RUNTIME_HOST}" "systemctl status unified-news-event-layer.service --no-pager | sed -n '1,18p'"

echo "[deploy-event] sqlite summary"
ssh "${NEWS_RUNTIME_HOST}" "python3 - <<'PY'
import sqlite3
conn = sqlite3.connect('${REMOTE_DB_PATH}')
try:
    print('events_total:', conn.execute('SELECT COUNT(*) FROM events').fetchone()[0])
    print('article_event_links_total:', conn.execute('SELECT COUNT(*) FROM article_event_links').fetchone()[0])
    print('event_entity_links_total:', conn.execute('SELECT COUNT(*) FROM event_entity_links').fetchone()[0])
    print('daily_digest_rows:', conn.execute('SELECT COUNT(*) FROM v_daily_digest').fetchone()[0])
    print('radar_industry_rows:', conn.execute('SELECT COUNT(*) FROM v_radar_industry').fetchone()[0])
    print('top_daily_digest:')
    for row in conn.execute(\"\"\"
        SELECT event_id, event_title, event_type, event_rank_score, novelty_state, confirmation_count
        FROM v_daily_digest
        ORDER BY event_rank_score DESC, datetime(last_seen_at) DESC
        LIMIT 10
    \"\"\"):
        print(row)
    print('top_radar_industry:')
    for row in conn.execute(\"\"\"
        SELECT industry, event_id, event_title, event_rank_score, novelty_state, confirmation_count
        FROM v_radar_industry
        ORDER BY industry, event_rank_score DESC
        LIMIT 10
    \"\"\"):
        print(row)
finally:
    conn.close()
PY"

echo "[deploy-event] recent log tail"
ssh "${NEWS_RUNTIME_HOST}" "tail -n 40 '${REMOTE_LOG_DIR}/event_layer.log' || true"
