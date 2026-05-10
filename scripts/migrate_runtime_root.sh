#!/usr/bin/env bash
set -euo pipefail

NEWS_RUNTIME_HOST="${NEWS_RUNTIME_HOST:-}"
if [[ -z "${NEWS_RUNTIME_HOST}" ]]; then
  echo "NEWS_RUNTIME_HOST must be set to your SSH host alias or hostname." >&2
  exit 2
fi
OLD_ROOT="${OLD_ROOT:-/opt/news-event-hub-legacy}"
NEW_ROOT="${NEW_ROOT:-/opt/news-event-hub}"
BACKUP_SUFFIX="${BACKUP_SUFFIX:-migrated_backup_$(date -u +%Y%m%dT%H%M%SZ)}"

if [[ "${OLD_ROOT}" == "${NEW_ROOT}" ]]; then
  echo "[migrate-runtime-root] old and new root are identical: ${OLD_ROOT}" >&2
  exit 1
fi

echo "[migrate-runtime-root] host=${NEWS_RUNTIME_HOST}"
echo "[migrate-runtime-root] old_root=${OLD_ROOT}"
echo "[migrate-runtime-root] new_root=${NEW_ROOT}"

ssh "${NEWS_RUNTIME_HOST}" "
  set -euo pipefail

  OLD_ROOT='${OLD_ROOT}'
  NEW_ROOT='${NEW_ROOT}'
  BACKUP_ROOT=\"\${OLD_ROOT}.${BACKUP_SUFFIX}\"

  echo '[migrate-runtime-root] preflight'
  if [ ! -d \"\${OLD_ROOT}\" ] && [ ! -d \"\${NEW_ROOT}\" ]; then
    echo 'neither old nor new root exists' >&2
    exit 1
  fi

  for unit in \
    unified-news-collector.timer \
    unified-news-collector.service \
    unified-news-event-layer.timer \
    unified-news-event-layer.service \
    unified-news-consumer-views.timer \
    unified-news-consumer-views.service \
    unified-news-browser-signal-collector.timer \
    unified-news-browser-signal-collector.service \
    unified-news-agent-reach-watch.timer \
    unified-news-agent-reach-watch.service
  do
    systemctl stop \"\$unit\" >/dev/null 2>&1 || true
  done

  mkdir -p \"\$(dirname \"\${NEW_ROOT}\")\"

  if [ -d \"\${OLD_ROOT}\" ] && [ ! -d \"\${NEW_ROOT}\" ]; then
    mkdir -p \"\${NEW_ROOT}\"
    cp -a \"\${OLD_ROOT}\"/. \"\${NEW_ROOT}\"/
    mv \"\${OLD_ROOT}\" \"\${BACKUP_ROOT}\"
    echo \"[migrate-runtime-root] copied old root to new root and archived old root at \${BACKUP_ROOT}\"
  elif [ -d \"\${OLD_ROOT}\" ] && [ -d \"\${NEW_ROOT}\" ]; then
    cp -a \"\${OLD_ROOT}\"/. \"\${NEW_ROOT}\"/
    mv \"\${OLD_ROOT}\" \"\${BACKUP_ROOT}\"
    echo \"[migrate-runtime-root] refreshed existing new root and archived old root at \${BACKUP_ROOT}\"
  else
    echo '[migrate-runtime-root] new root already present and old root already absent'
  fi

  printf '\\n[migrate-runtime-root] roots\\n'
  ls -ld \"\${NEW_ROOT}\" 2>/dev/null || true
  ls -ld \"\${BACKUP_ROOT}\" 2>/dev/null || true
"
