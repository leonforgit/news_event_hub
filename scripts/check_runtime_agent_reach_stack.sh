#!/usr/bin/env bash
set -euo pipefail

NEWS_RUNTIME_HOST="${NEWS_RUNTIME_HOST:-}"
if [[ -z "${NEWS_RUNTIME_HOST}" ]]; then
  echo "NEWS_RUNTIME_HOST must be set to your SSH host alias or hostname." >&2
  exit 2
fi
REMOTE_ROOT="${REMOTE_ROOT:-/opt/news-event-hub}"

ssh "${NEWS_RUNTIME_HOST}" "set -euo pipefail
echo '[runtime-agent-reach] version'
'${REMOTE_ROOT}/scripts/agent_reach_cli.sh' --version
echo
echo '[runtime-agent-reach] units'
systemctl is-enabled unified-news-agent-reach-watch.timer || true
systemctl is-active unified-news-agent-reach-watch.timer || true
systemctl is-enabled unified-news-agent-reach-watch.service || true
systemctl is-active unified-news-agent-reach-watch.service || true
echo
echo '[runtime-agent-reach] support-tools'
command -v mcporter || true
command -v yt-dlp || true
echo
echo '[runtime-agent-reach] doctor'
'${REMOTE_ROOT}/scripts/run_agent_reach_watch.sh'
tail -n 80 '${REMOTE_ROOT}/state/agent_reach/doctor_latest.txt'
echo
echo '[runtime-agent-reach] cookie-inventory'
cat '${REMOTE_ROOT}/state/agent_reach/cookie_inventory_latest.json'
"
