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
REMOTE_RUNTIME_DIR="${REMOTE_ROOT}/runtime/browser_signal"

REQUIRED_FILES=(
  "${ROOT_DIR}/config/browser_signal_catalog_v1.json"
  "${ROOT_DIR}/scripts/install_browser_signal_runtime.sh"
  "${ROOT_DIR}/scripts/run_browser_signal_collector.py"
  "${ROOT_DIR}/scripts/smoke_test_browser_signal_collector.py"
  "${ROOT_DIR}/config/systemd/unified-news-browser-signal-collector.service"
  "${ROOT_DIR}/config/systemd/unified-news-browser-signal-collector.timer"
)

echo "[deploy-browser-signal] host=${NEWS_RUNTIME_HOST}"

"${ROOT_DIR}/scripts/deploy_runtime_repo_checkout.sh"

for path in "${REQUIRED_FILES[@]}"; do
  if [[ ! -f "${path}" ]]; then
    echo "[deploy-browser-signal] missing local file: ${path}" >&2
    exit 1
  fi
done

ssh "${NEWS_RUNTIME_HOST}" "python3 --version >/dev/null && node --version >/dev/null && npm --version >/dev/null && test -w /etc/systemd/system"
ssh "${NEWS_RUNTIME_HOST}" "mkdir -p '${REMOTE_CONFIG_DIR}' '${REMOTE_SYSTEMD_DIR}' '${REMOTE_SCRIPT_DIR}' '${REMOTE_RUNTIME_DIR}'"

scp "${ROOT_DIR}/config/browser_signal_catalog_v1.json" "${NEWS_RUNTIME_HOST}:${REMOTE_CONFIG_DIR}/browser_signal_catalog_v1.json"
scp "${ROOT_DIR}/scripts/install_browser_signal_runtime.sh" "${NEWS_RUNTIME_HOST}:${REMOTE_SCRIPT_DIR}/install_browser_signal_runtime.sh"
scp "${ROOT_DIR}/scripts/run_browser_signal_collector.py" "${NEWS_RUNTIME_HOST}:${REMOTE_SCRIPT_DIR}/run_browser_signal_collector.py"
scp "${ROOT_DIR}/scripts/smoke_test_browser_signal_collector.py" "${NEWS_RUNTIME_HOST}:${REMOTE_SCRIPT_DIR}/smoke_test_browser_signal_collector.py"
scp "${ROOT_DIR}/config/systemd/unified-news-browser-signal-collector.service" "${NEWS_RUNTIME_HOST}:${REMOTE_SYSTEMD_DIR}/unified-news-browser-signal-collector.service"
scp "${ROOT_DIR}/config/systemd/unified-news-browser-signal-collector.timer" "${NEWS_RUNTIME_HOST}:${REMOTE_SYSTEMD_DIR}/unified-news-browser-signal-collector.timer"

ssh "${NEWS_RUNTIME_HOST}" "chmod +x '${REMOTE_SCRIPT_DIR}/install_browser_signal_runtime.sh' '${REMOTE_SCRIPT_DIR}/run_browser_signal_collector.py'"
ssh "${NEWS_RUNTIME_HOST}" "BROWSER_SIGNAL_HOME='${REMOTE_RUNTIME_DIR}' '${REMOTE_SCRIPT_DIR}/install_browser_signal_runtime.sh'"
ssh "${NEWS_RUNTIME_HOST}" "'${REMOTE_RUNTIME_DIR}/.venv/bin/python' '${REMOTE_SCRIPT_DIR}/smoke_test_browser_signal_collector.py'"
ssh "${NEWS_RUNTIME_HOST}" "systemd-analyze verify '${REMOTE_SYSTEMD_DIR}/unified-news-browser-signal-collector.service' '${REMOTE_SYSTEMD_DIR}/unified-news-browser-signal-collector.timer' && cp '${REMOTE_SYSTEMD_DIR}/unified-news-browser-signal-collector.service' /etc/systemd/system/unified-news-browser-signal-collector.service && cp '${REMOTE_SYSTEMD_DIR}/unified-news-browser-signal-collector.timer' /etc/systemd/system/unified-news-browser-signal-collector.timer && systemctl daemon-reload && systemctl enable --now unified-news-browser-signal-collector.timer"

echo "[deploy-browser-signal] triggering first browser-signal run"
ssh "${NEWS_RUNTIME_HOST}" "systemctl start unified-news-browser-signal-collector.service"
ssh "${NEWS_RUNTIME_HOST}" "systemctl status unified-news-browser-signal-collector.timer --no-pager | sed -n '1,12p'"
ssh "${NEWS_RUNTIME_HOST}" "systemctl status unified-news-browser-signal-collector.service --no-pager | sed -n '1,18p'"
ssh "${NEWS_RUNTIME_HOST}" "tail -n 40 '${REMOTE_ROOT}/logs/browser_signal_collector.log' || true"
