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
REMOTE_SCRIPT_DIR="${REMOTE_ROOT}/scripts"
REMOTE_STATE_DIR="${REMOTE_ROOT}/state"
REMOTE_LOG_DIR="${REMOTE_ROOT}/logs"
REMOTE_DB_PATH="${REMOTE_STATE_DIR}/news_event.db"

echo "[deploy] host=${NEWS_RUNTIME_HOST}"
echo "[deploy] remote_root=${REMOTE_ROOT}"

"${ROOT_DIR}/scripts/deploy_runtime_repo_checkout.sh"

ssh "${NEWS_RUNTIME_HOST}" "mkdir -p '${REMOTE_CONFIG_DIR}' '${REMOTE_SCRIPT_DIR}' '${REMOTE_STATE_DIR}' '${REMOTE_LOG_DIR}'"

scp "${ROOT_DIR}/config/schema.sql" "${NEWS_RUNTIME_HOST}:${REMOTE_CONFIG_DIR}/schema.sql"
scp "${ROOT_DIR}/config/source_registry_v1.yaml" "${NEWS_RUNTIME_HOST}:${REMOTE_CONFIG_DIR}/source_registry_v1.yaml"
scp "${ROOT_DIR}/scripts/init_unified_news_db.py" "${NEWS_RUNTIME_HOST}:${REMOTE_SCRIPT_DIR}/init_unified_news_db.py"

ssh "${NEWS_RUNTIME_HOST}" "chmod +x '${REMOTE_SCRIPT_DIR}/init_unified_news_db.py' && python3 '${REMOTE_SCRIPT_DIR}/init_unified_news_db.py' --db '${REMOTE_DB_PATH}' --schema '${REMOTE_CONFIG_DIR}/schema.sql' --registry '${REMOTE_CONFIG_DIR}/source_registry_v1.yaml'"

echo "[deploy] sqlite summary"
ssh "${NEWS_RUNTIME_HOST}" "python3 - <<'PY'
import sqlite3
db_path = '${REMOTE_DB_PATH}'
conn = sqlite3.connect(db_path)
try:
    total = conn.execute('SELECT COUNT(*) FROM source_registry').fetchone()[0]
    enabled = conn.execute('SELECT COUNT(*) FROM source_registry WHERE enabled = 1').fetchone()[0]
    print(f'db_path: {db_path}')
    print(f'source_registry_total: {total}')
    print(f'source_registry_enabled: {enabled}')
finally:
    conn.close()
PY"
