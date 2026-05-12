#!/usr/bin/env bash
set -euo pipefail

NEWS_RUNTIME_HOST="${NEWS_RUNTIME_HOST:-}"
if [[ -z "${NEWS_RUNTIME_HOST}" ]]; then
  echo "NEWS_RUNTIME_HOST must be set to your SSH host alias or hostname." >&2
  exit 2
fi
LOCAL_STATE="${LOCAL_STATE:-}"
REMOTE_STATE="${REMOTE_STATE:-/opt/news-event-hub/state/auth/weibo_storage_state.json}"

if [[ -z "${LOCAL_STATE}" ]]; then
  echo "LOCAL_STATE must point to a local Weibo storage-state JSON file." >&2
  exit 2
fi

if [[ ! -f "${LOCAL_STATE}" ]]; then
  echo "Missing local Weibo storage state: ${LOCAL_STATE}" >&2
  exit 1
fi

REMOTE_STATE_DIR="$(dirname "${REMOTE_STATE}")"
ssh "${NEWS_RUNTIME_HOST}" "install -d -m 700 '${REMOTE_STATE_DIR}'"
rsync -az --chmod=F600,D700 "${LOCAL_STATE}" "${NEWS_RUNTIME_HOST}:${REMOTE_STATE}"
ssh "${NEWS_RUNTIME_HOST}" "chown news-event-hub:news-event-hub '${REMOTE_STATE}' 2>/dev/null || true; chmod 600 '${REMOTE_STATE}'"
echo "Synced Weibo storage state to ${NEWS_RUNTIME_HOST}:${REMOTE_STATE}"
