#!/usr/bin/env bash
set -euo pipefail

NEWS_RUNTIME_HOST="${NEWS_RUNTIME_HOST:-}"
if [[ -z "${NEWS_RUNTIME_HOST}" ]]; then
  echo "NEWS_RUNTIME_HOST must be set to your SSH host alias or hostname." >&2
  exit 2
fi
LOCAL_STATE="${LOCAL_STATE:-$HOME/.codex/state/investment/research/opportunities/auth/weibo_storage_state.json}"
REMOTE_STATE="${REMOTE_STATE:-/opt/news-event-hub/state/auth/weibo_storage_state.json}"

if [[ ! -f "${LOCAL_STATE}" ]]; then
  echo "Missing local Weibo storage state: ${LOCAL_STATE}" >&2
  exit 1
fi

ssh "${NEWS_RUNTIME_HOST}" "mkdir -p '$(dirname "${REMOTE_STATE}")'"
rsync -az "${LOCAL_STATE}" "${NEWS_RUNTIME_HOST}:${REMOTE_STATE}"
echo "Synced Weibo storage state to ${NEWS_RUNTIME_HOST}:${REMOTE_STATE}"
