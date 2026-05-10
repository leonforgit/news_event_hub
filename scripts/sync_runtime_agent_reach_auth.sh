#!/usr/bin/env bash
set -euo pipefail

NEWS_RUNTIME_HOST="${NEWS_RUNTIME_HOST:-}"
if [[ -z "${NEWS_RUNTIME_HOST}" ]]; then
  echo "NEWS_RUNTIME_HOST must be set to your SSH host alias or hostname." >&2
  exit 2
fi
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

LOCAL_AUTH_STATE="${LOCAL_AUTH_STATE:-${ROOT_DIR}/state/auth/agent_reach/playwright_shared_auth.json}"
LOCAL_PLATFORM_DIR="${LOCAL_PLATFORM_DIR:-${ROOT_DIR}/state/auth/agent_reach/platforms}"
REMOTE_ROOT="${REMOTE_ROOT:-/opt/news-event-hub}"
REMOTE_AUTH_DIR="${REMOTE_ROOT}/state/auth/agent_reach"

if [[ ! -f "${LOCAL_AUTH_STATE}" ]]; then
  echo "missing local auth state: ${LOCAL_AUTH_STATE}" >&2
  exit 1
fi

ssh "${NEWS_RUNTIME_HOST}" "mkdir -p '${REMOTE_AUTH_DIR}'"
scp "${LOCAL_AUTH_STATE}" "${NEWS_RUNTIME_HOST}:${REMOTE_AUTH_DIR}/playwright_shared_auth.json"
ssh "${NEWS_RUNTIME_HOST}" "chmod 600 '${REMOTE_AUTH_DIR}/playwright_shared_auth.json'"

if [[ -d "${LOCAL_PLATFORM_DIR}" ]]; then
  ssh "${NEWS_RUNTIME_HOST}" "mkdir -p '${REMOTE_AUTH_DIR}/platforms'"
  scp -r "${LOCAL_PLATFORM_DIR}/." "${NEWS_RUNTIME_HOST}:${REMOTE_AUTH_DIR}/platforms/"
fi

echo "remote_auth_dir=${REMOTE_AUTH_DIR}"
