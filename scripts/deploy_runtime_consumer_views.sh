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
REMOTE_OUTPUT_DIR="${REMOTE_STATE_DIR}/consumer_exports"
REMOTE_LOG_DIR="${REMOTE_ROOT}/logs"
REMOTE_DB_PATH="${REMOTE_STATE_DIR}/news_event.db"

REQUIRED_FILES=(
  "${ROOT_DIR}/scripts/export_consumer_views.py"
  "${ROOT_DIR}/data/entity_aliases_v1.csv"
  "${ROOT_DIR}/config/systemd/unified-news-consumer-views.service"
  "${ROOT_DIR}/config/systemd/unified-news-consumer-views.timer"
)

echo "[deploy-consumer] host=${NEWS_RUNTIME_HOST}"
echo "[deploy-consumer] remote_root=${REMOTE_ROOT}"

"${ROOT_DIR}/scripts/deploy_runtime_repo_checkout.sh"

for path in "${REQUIRED_FILES[@]}"; do
  if [[ ! -f "${path}" ]]; then
    echo "[deploy-consumer] missing local file: ${path}" >&2
    exit 1
  fi
done

ssh "${NEWS_RUNTIME_HOST}" "python3 - <<'PY'
import importlib
for module in ('sqlite3', 'json'):
    importlib.import_module(module)
PY"

ssh "${NEWS_RUNTIME_HOST}" "test -w /etc/systemd/system && mkdir -p '${REMOTE_CONFIG_DIR}' '${REMOTE_SYSTEMD_DIR}' '${REMOTE_SCRIPT_DIR}' '${REMOTE_DATA_DIR}' '${REMOTE_OUTPUT_DIR}' '${REMOTE_LOG_DIR}'"

scp "${ROOT_DIR}/scripts/export_consumer_views.py" "${NEWS_RUNTIME_HOST}:${REMOTE_SCRIPT_DIR}/export_consumer_views.py"
scp "${ROOT_DIR}/data/entity_aliases_v1.csv" "${NEWS_RUNTIME_HOST}:${REMOTE_DATA_DIR}/entity_aliases_v1.csv"
scp "${ROOT_DIR}/config/systemd/unified-news-consumer-views.service" "${NEWS_RUNTIME_HOST}:${REMOTE_SYSTEMD_DIR}/unified-news-consumer-views.service"
scp "${ROOT_DIR}/config/systemd/unified-news-consumer-views.timer" "${NEWS_RUNTIME_HOST}:${REMOTE_SYSTEMD_DIR}/unified-news-consumer-views.timer"

ssh "${NEWS_RUNTIME_HOST}" "chmod 644 '${REMOTE_SCRIPT_DIR}/export_consumer_views.py' && systemd-analyze verify '${REMOTE_SYSTEMD_DIR}/unified-news-consumer-views.service' '${REMOTE_SYSTEMD_DIR}/unified-news-consumer-views.timer' && cp '${REMOTE_SYSTEMD_DIR}/unified-news-consumer-views.service' /etc/systemd/system/unified-news-consumer-views.service && cp '${REMOTE_SYSTEMD_DIR}/unified-news-consumer-views.timer' /etc/systemd/system/unified-news-consumer-views.timer && systemctl daemon-reload && systemctl enable --now unified-news-consumer-views.timer"

ssh "${NEWS_RUNTIME_HOST}" "python3 '${REMOTE_SCRIPT_DIR}/export_consumer_views.py' --db '${REMOTE_DB_PATH}' --output-root '${REMOTE_OUTPUT_DIR}'"

echo "[deploy-consumer] export summary"
ssh "${NEWS_RUNTIME_HOST}" "python3 - <<'PY'
import json
from pathlib import Path

root = Path('${REMOTE_OUTPUT_DIR}')
investment = json.loads((root / 'opportunity_report_feed_latest.json').read_text(encoding='utf-8'))
legacy = json.loads((root / 'legacy_news_digest_latest.json').read_text(encoding='utf-8'))
radar = json.loads((root / 'industry_radar_feed_latest.json').read_text(encoding='utf-8'))
research = json.loads((root / 'research_feed_latest.json').read_text(encoding='utf-8'))

print('opportunity_top_events:', len(investment.get('top_events') or []))
print('legacy_top_market_news:', len(legacy.get('top_market_news') or []))
print('radar_industries:', len(radar.get('industries') or []))
print('research_recent_events:', len(research.get('recent_events') or []))
PY"
