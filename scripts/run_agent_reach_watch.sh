#!/usr/bin/env bash
set -euo pipefail
umask 077

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
OUT_DIR="${ROOT_DIR}/state/agent_reach"
AUTH_STATE="${ROOT_DIR}/state/auth/agent_reach/playwright_shared_auth.json"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"

install -d -m 700 "${OUT_DIR}"

if [[ -f "${AUTH_STATE}" ]]; then
  RAW_COOKIE_ARGS=()
  if [[ "${NEWS_EVENT_HUB_EXPORT_RAW_COOKIES:-0}" == "1" ]]; then
    RAW_COOKIE_ARGS+=(--export-raw-cookies)
  fi
  python3 "${SCRIPT_DIR}/export_agent_reach_cookie_inventory.py" \
    --state-in "${AUTH_STATE}" \
    --out-dir "${ROOT_DIR}/state/auth/agent_reach/platforms" \
    "${RAW_COOKIE_ARGS[@]}" \
    > "${OUT_DIR}/cookie_inventory_${TIMESTAMP}.json"
  chmod 600 "${OUT_DIR}/cookie_inventory_${TIMESTAMP}.json"
  cp "${OUT_DIR}/cookie_inventory_${TIMESTAMP}.json" "${OUT_DIR}/cookie_inventory_latest.json"
  chmod 600 "${OUT_DIR}/cookie_inventory_latest.json"
fi

"${SCRIPT_DIR}/agent_reach_cli.sh" doctor > "${OUT_DIR}/doctor_${TIMESTAMP}.txt"
chmod 600 "${OUT_DIR}/doctor_${TIMESTAMP}.txt"
cp "${OUT_DIR}/doctor_${TIMESTAMP}.txt" "${OUT_DIR}/doctor_latest.txt"
chmod 600 "${OUT_DIR}/doctor_latest.txt"
echo "${TIMESTAMP}" > "${OUT_DIR}/doctor_latest.timestamp"
chmod 600 "${OUT_DIR}/doctor_latest.timestamp"

echo "agent_reach_watch_ok ${TIMESTAMP}"
