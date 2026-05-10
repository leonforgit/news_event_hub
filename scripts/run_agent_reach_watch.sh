#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
OUT_DIR="${ROOT_DIR}/state/agent_reach"
AUTH_STATE="${ROOT_DIR}/state/auth/agent_reach/playwright_shared_auth.json"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"

mkdir -p "${OUT_DIR}"

if [[ -f "${AUTH_STATE}" ]]; then
  python3 "${SCRIPT_DIR}/export_agent_reach_cookie_inventory.py" \
    --state-in "${AUTH_STATE}" \
    --out-dir "${ROOT_DIR}/state/auth/agent_reach/platforms" \
    > "${OUT_DIR}/cookie_inventory_${TIMESTAMP}.json"
  cp "${OUT_DIR}/cookie_inventory_${TIMESTAMP}.json" "${OUT_DIR}/cookie_inventory_latest.json"
fi

"${SCRIPT_DIR}/agent_reach_cli.sh" doctor > "${OUT_DIR}/doctor_${TIMESTAMP}.txt"
cp "${OUT_DIR}/doctor_${TIMESTAMP}.txt" "${OUT_DIR}/doctor_latest.txt"
echo "${TIMESTAMP}" > "${OUT_DIR}/doctor_latest.timestamp"

echo "agent_reach_watch_ok ${TIMESTAMP}"
