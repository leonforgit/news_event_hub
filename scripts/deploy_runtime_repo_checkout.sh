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
REMOTE_TMP_DIR="${REMOTE_TMP_DIR:-/tmp/news_event_hub_repo_sync}"
REMOTE_BUNDLE_PATH="${REMOTE_TMP_DIR}/news_event_hub.bundle"

if ! git -C "${ROOT_DIR}" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "[deploy-repo] local root is not a git repo: ${ROOT_DIR}" >&2
  exit 1
fi

LOCAL_BUNDLE="$(mktemp /tmp/news_event_hub.XXXXXX.bundle)"
cleanup() {
  rm -f "${LOCAL_BUNDLE}"
}
trap cleanup EXIT

echo "[deploy-repo] host=${NEWS_RUNTIME_HOST}"
echo "[deploy-repo] remote_root=${REMOTE_ROOT}"

git -C "${ROOT_DIR}" bundle create "${LOCAL_BUNDLE}" --all

ssh "${NEWS_RUNTIME_HOST}" "mkdir -p '${REMOTE_TMP_DIR}' '${REMOTE_ROOT}'"
scp "${LOCAL_BUNDLE}" "${NEWS_RUNTIME_HOST}:${REMOTE_BUNDLE_PATH}" >/dev/null

ssh "${NEWS_RUNTIME_HOST}" "
  set -euo pipefail
  cd '${REMOTE_ROOT}'
  if [ ! -d .git ]; then
    git init -b main >/dev/null
  fi
  git remote remove codex-bundle >/dev/null 2>&1 || true
  git remote add codex-bundle '${REMOTE_BUNDLE_PATH}'
  git fetch codex-bundle --tags >/dev/null
  git reset --hard FETCH_HEAD >/dev/null
  git remote remove codex-bundle >/dev/null 2>&1 || true
  rm -f '${REMOTE_BUNDLE_PATH}'
  git status --short --branch
  git log -1 --oneline
"
