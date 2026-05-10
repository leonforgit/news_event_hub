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
REMOTE_STATE_DIR="${REMOTE_ROOT}/state"
REMOTE_LOG_DIR="${REMOTE_ROOT}/logs"
REMOTE_CACHE_DIR="${REMOTE_ROOT}/cache/fred_us_macro_open_data"
REMOTE_DB_PATH="${REMOTE_STATE_DIR}/news_event.db"
REMOTE_SCHEMA_PATH="${REMOTE_CONFIG_DIR}/schema.sql"

REQUIRED_FILES=(
  "${ROOT_DIR}/config/source_registry_v1.yaml"
  "${ROOT_DIR}/config/schema.sql"
  "${ROOT_DIR}/scripts/init_unified_news_db.py"
  "${ROOT_DIR}/scripts/import_fred_us_macro_open_data.py"
  "${ROOT_DIR}/config/systemd/unified-news-fred-macro-import.service"
  "${ROOT_DIR}/config/systemd/unified-news-fred-macro-import.timer"
)

echo "[deploy-fred-macro] host=${NEWS_RUNTIME_HOST}"
echo "[deploy-fred-macro] remote_root=${REMOTE_ROOT}"

"${ROOT_DIR}/scripts/deploy_runtime_repo_checkout.sh"

for path in "${REQUIRED_FILES[@]}"; do
  if [[ ! -f "${path}" ]]; then
    echo "[deploy-fred-macro] missing local file: ${path}" >&2
    exit 1
  fi
done

ssh "${NEWS_RUNTIME_HOST}" "python3 - <<'PY'
import importlib
for module in ('sqlite3', 'yaml'):
    importlib.import_module(module)
PY
test -w /etc/systemd/system"

ssh "${NEWS_RUNTIME_HOST}" "mkdir -p '${REMOTE_CONFIG_DIR}' '${REMOTE_SYSTEMD_DIR}' '${REMOTE_SCRIPT_DIR}' '${REMOTE_STATE_DIR}' '${REMOTE_LOG_DIR}' '${REMOTE_CACHE_DIR}'"

scp "${ROOT_DIR}/config/source_registry_v1.yaml" "${NEWS_RUNTIME_HOST}:${REMOTE_CONFIG_DIR}/source_registry_v1.yaml"
scp "${ROOT_DIR}/config/schema.sql" "${NEWS_RUNTIME_HOST}:${REMOTE_CONFIG_DIR}/schema.sql"
scp "${ROOT_DIR}/scripts/init_unified_news_db.py" "${NEWS_RUNTIME_HOST}:${REMOTE_SCRIPT_DIR}/init_unified_news_db.py"
scp "${ROOT_DIR}/scripts/import_fred_us_macro_open_data.py" "${NEWS_RUNTIME_HOST}:${REMOTE_SCRIPT_DIR}/import_fred_us_macro_open_data.py"
scp "${ROOT_DIR}/config/systemd/unified-news-fred-macro-import.service" "${NEWS_RUNTIME_HOST}:${REMOTE_SYSTEMD_DIR}/unified-news-fred-macro-import.service"
scp "${ROOT_DIR}/config/systemd/unified-news-fred-macro-import.timer" "${NEWS_RUNTIME_HOST}:${REMOTE_SYSTEMD_DIR}/unified-news-fred-macro-import.timer"

ssh "${NEWS_RUNTIME_HOST}" "python3 '${REMOTE_SCRIPT_DIR}/init_unified_news_db.py' --db '${REMOTE_DB_PATH}' --schema '${REMOTE_SCHEMA_PATH}' --registry '${REMOTE_CONFIG_DIR}/source_registry_v1.yaml'"

ssh "${NEWS_RUNTIME_HOST}" "chmod +x '${REMOTE_SCRIPT_DIR}/init_unified_news_db.py' '${REMOTE_SCRIPT_DIR}/import_fred_us_macro_open_data.py' && systemd-analyze verify '${REMOTE_SYSTEMD_DIR}/unified-news-fred-macro-import.service' '${REMOTE_SYSTEMD_DIR}/unified-news-fred-macro-import.timer' && cp '${REMOTE_SYSTEMD_DIR}/unified-news-fred-macro-import.service' /etc/systemd/system/unified-news-fred-macro-import.service && cp '${REMOTE_SYSTEMD_DIR}/unified-news-fred-macro-import.timer' /etc/systemd/system/unified-news-fred-macro-import.timer && systemctl daemon-reload && systemctl enable --now unified-news-fred-macro-import.timer"

echo "[deploy-fred-macro] triggering first import"
if ! ssh "${NEWS_RUNTIME_HOST}" "systemctl start unified-news-fred-macro-import.service"; then
  echo "[deploy-fred-macro] first import failed; retrying once after a short backoff"
  sleep 3
  ssh "${NEWS_RUNTIME_HOST}" "journalctl -u unified-news-fred-macro-import.service -n 40 --no-pager || true"
  ssh "${NEWS_RUNTIME_HOST}" "systemctl reset-failed unified-news-fred-macro-import.service || true"
  ssh "${NEWS_RUNTIME_HOST}" "systemctl start unified-news-fred-macro-import.service"
fi

echo "[deploy-fred-macro] timer status"
ssh "${NEWS_RUNTIME_HOST}" "systemctl status unified-news-fred-macro-import.timer --no-pager | sed -n '1,12p'"

echo "[deploy-fred-macro] service status"
ssh "${NEWS_RUNTIME_HOST}" "systemctl status unified-news-fred-macro-import.service --no-pager | sed -n '1,18p'"

echo "[deploy-fred-macro] sqlite summary"
ssh "${NEWS_RUNTIME_HOST}" "python3 - <<'PY'
import sqlite3
conn = sqlite3.connect('${REMOTE_DB_PATH}')
try:
    print('fred_articles:', conn.execute(\"SELECT COUNT(*) FROM news_articles WHERE source_id = 'fred_us_macro_open_data'\").fetchone()[0])
    print('fred_latest_article:', conn.execute(\"SELECT MAX(published_at) FROM news_articles WHERE source_id = 'fred_us_macro_open_data'\").fetchone()[0])
    print('fred_source_health:')
    for row in conn.execute(\"\"\"
        SELECT status, checked_at, articles_last_24h, last_article_at, error_message
        FROM source_health
        WHERE source_id = 'fred_us_macro_open_data'
        ORDER BY checked_at DESC, id DESC
        LIMIT 5
    \"\"\"):
        print(row)
finally:
    conn.close()
PY"

echo "[deploy-fred-macro] recent log tail"
ssh "${NEWS_RUNTIME_HOST}" "tail -n 40 '${REMOTE_LOG_DIR}/fred_macro_import.log' || true"
