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
REMOTE_RUNTIME_DIR="${REMOTE_ROOT}/runtime/agent_reach"
REMOTE_STATE_DIR="${REMOTE_ROOT}/state/agent_reach"
REMOTE_LOG_DIR="${REMOTE_ROOT}/logs"
INSTALL_MCPORTER_ON_RUNTIME="${INSTALL_MCPORTER_ON_RUNTIME:-1}"

REQUIRED_FILES=(
  "${ROOT_DIR}/scripts/agent_reach_cli.sh"
  "${ROOT_DIR}/scripts/install_agent_reach.sh"
  "${ROOT_DIR}/scripts/export_agent_reach_cookie_inventory.py"
  "${ROOT_DIR}/scripts/run_agent_reach_watch.sh"
  "${ROOT_DIR}/scripts/sync_runtime_agent_reach_auth.sh"
  "${ROOT_DIR}/config/systemd/unified-news-agent-reach-watch.service"
  "${ROOT_DIR}/config/systemd/unified-news-agent-reach-watch.timer"
)

echo "[deploy-agent-reach] host=${NEWS_RUNTIME_HOST}"
echo "[deploy-agent-reach] remote_root=${REMOTE_ROOT}"

"${ROOT_DIR}/scripts/deploy_runtime_repo_checkout.sh"

for path in "${REQUIRED_FILES[@]}"; do
  if [[ ! -f "${path}" ]]; then
    echo "[deploy-agent-reach] missing local file: ${path}" >&2
    exit 1
  fi
done

ssh "${NEWS_RUNTIME_HOST}" "python3 - <<'PY'
import importlib
for module in ('sys', 'venv', 'subprocess', 'json'):
    importlib.import_module(module)
PY
test -w /etc/systemd/system"

ssh "${NEWS_RUNTIME_HOST}" "mkdir -p '${REMOTE_CONFIG_DIR}' '${REMOTE_SYSTEMD_DIR}' '${REMOTE_SCRIPT_DIR}' '${REMOTE_RUNTIME_DIR}' '${REMOTE_STATE_DIR}' '${REMOTE_LOG_DIR}'"

scp "${ROOT_DIR}/scripts/agent_reach_cli.sh" "${NEWS_RUNTIME_HOST}:${REMOTE_SCRIPT_DIR}/agent_reach_cli.sh"
scp "${ROOT_DIR}/scripts/install_agent_reach.sh" "${NEWS_RUNTIME_HOST}:${REMOTE_SCRIPT_DIR}/install_agent_reach.sh"
scp "${ROOT_DIR}/scripts/export_agent_reach_cookie_inventory.py" "${NEWS_RUNTIME_HOST}:${REMOTE_SCRIPT_DIR}/export_agent_reach_cookie_inventory.py"
scp "${ROOT_DIR}/scripts/check_runtime_agent_reach_stack.sh" "${NEWS_RUNTIME_HOST}:${REMOTE_SCRIPT_DIR}/check_runtime_agent_reach_stack.sh"
scp "${ROOT_DIR}/scripts/run_agent_reach_watch.sh" "${NEWS_RUNTIME_HOST}:${REMOTE_SCRIPT_DIR}/run_agent_reach_watch.sh"
scp "${ROOT_DIR}/scripts/sync_runtime_agent_reach_auth.sh" "${NEWS_RUNTIME_HOST}:${REMOTE_SCRIPT_DIR}/sync_runtime_agent_reach_auth.sh"
scp "${ROOT_DIR}/config/systemd/unified-news-agent-reach-watch.service" "${NEWS_RUNTIME_HOST}:${REMOTE_SYSTEMD_DIR}/unified-news-agent-reach-watch.service"
scp "${ROOT_DIR}/config/systemd/unified-news-agent-reach-watch.timer" "${NEWS_RUNTIME_HOST}:${REMOTE_SYSTEMD_DIR}/unified-news-agent-reach-watch.timer"

ssh "${NEWS_RUNTIME_HOST}" "chmod +x '${REMOTE_SCRIPT_DIR}/agent_reach_cli.sh' '${REMOTE_SCRIPT_DIR}/install_agent_reach.sh' '${REMOTE_SCRIPT_DIR}/check_runtime_agent_reach_stack.sh' '${REMOTE_SCRIPT_DIR}/run_agent_reach_watch.sh' '${REMOTE_SCRIPT_DIR}/sync_runtime_agent_reach_auth.sh'"
ssh "${NEWS_RUNTIME_HOST}" "AGENT_REACH_HOME='${REMOTE_RUNTIME_DIR}' '${REMOTE_SCRIPT_DIR}/install_agent_reach.sh'"

if [[ "${INSTALL_MCPORTER_ON_RUNTIME}" == "1" ]]; then
  ssh "${NEWS_RUNTIME_HOST}" "if command -v npm >/dev/null 2>&1; then command -v mcporter >/dev/null 2>&1 || npm install -g mcporter; fi"
fi

ssh "${NEWS_RUNTIME_HOST}" "systemd-analyze verify '${REMOTE_SYSTEMD_DIR}/unified-news-agent-reach-watch.service' '${REMOTE_SYSTEMD_DIR}/unified-news-agent-reach-watch.timer' && cp '${REMOTE_SYSTEMD_DIR}/unified-news-agent-reach-watch.service' /etc/systemd/system/unified-news-agent-reach-watch.service && cp '${REMOTE_SYSTEMD_DIR}/unified-news-agent-reach-watch.timer' /etc/systemd/system/unified-news-agent-reach-watch.timer && systemctl daemon-reload"

if [[ -f "${ROOT_DIR}/state/auth/agent_reach/playwright_shared_auth.json" ]]; then
  "${ROOT_DIR}/scripts/sync_runtime_agent_reach_auth.sh"
fi

echo "[deploy-agent-reach] installed but NOT enabled"
echo "[deploy-agent-reach] enable later with:"
echo "  ssh ${NEWS_RUNTIME_HOST} 'systemctl enable --now unified-news-agent-reach-watch.timer'"
ssh "${NEWS_RUNTIME_HOST}" "systemctl list-unit-files unified-news-agent-reach-watch.service unified-news-agent-reach-watch.timer --no-pager || true"
