#!/usr/bin/env bash
set -euo pipefail

NEWS_RUNTIME_HOST="${NEWS_RUNTIME_HOST:-}"
if [[ -z "${NEWS_RUNTIME_HOST}" ]]; then
  echo "NEWS_RUNTIME_HOST must be set to your SSH host alias or hostname." >&2
  exit 2
fi
REMOTE_ROOT="${REMOTE_ROOT:-/opt/news-event-hub}"
REMOTE_DB="${REMOTE_DB:-${REMOTE_ROOT}/state/news_event.db}"
REMOTE_EXPORT_ROOT="${REMOTE_EXPORT_ROOT:-${REMOTE_ROOT}/state/consumer_exports}"

ssh "${NEWS_RUNTIME_HOST}" "set -euo pipefail
REMOTE_ROOT='${REMOTE_ROOT}'
REMOTE_DB='${REMOTE_DB}'
REMOTE_EXPORT_ROOT='${REMOTE_EXPORT_ROOT}'

echo '[runtime-news] repo'
if git -C \"\$REMOTE_ROOT\" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  git -C \"\$REMOTE_ROOT\" status --short --branch
  git -C \"\$REMOTE_ROOT\" log -1 --oneline
else
  echo 'not_a_git_repo'
fi
echo

echo '[runtime-news] units'
for unit in \
  unified-news-collector.timer \
  unified-news-collector.service \
  unified-news-event-layer.timer \
  unified-news-event-layer.service \
  unified-news-consumer-views.timer \
  unified-news-consumer-views.service \
  unified-news-browser-signal-collector.timer \
  unified-news-browser-signal-collector.service
do
  enabled=\$(systemctl is-enabled \"\$unit\" 2>/dev/null || true)
  active=\$(systemctl is-active \"\$unit\" 2>/dev/null || true)
  printf '%s enabled=%s active=%s\n' \"\$unit\" \"\${enabled:-unknown}\" \"\${active:-unknown}\"
done
echo

echo '[runtime-news] runtime-paths'
for path in \
  \"\$REMOTE_ROOT/config/source_registry_v1.yaml\" \
  \"\$REMOTE_ROOT/config/live_collector_catalog_v1.json\" \
  \"\$REMOTE_ROOT/config/browser_signal_catalog_v1.json\" \
  \"\$REMOTE_ROOT/config/news_event_hub.env\" \
  \"\$REMOTE_DB\" \
  \"\$REMOTE_EXPORT_ROOT\"
do
  if [ -e \"\$path\" ]; then
    printf 'present %s\n' \"\$path\"
  else
    printf 'missing %s\n' \"\$path\"
  fi
done
echo

echo '[runtime-news] db-summary'
if [ -f \"\$REMOTE_DB\" ]; then
  python3 - <<'PY'
import sqlite3

conn = sqlite3.connect('file:${REMOTE_DB}?mode=ro', uri=True)
try:
    queries = [
        ('source_registry_total', 'SELECT COUNT(*) FROM source_registry'),
        ('source_registry_enabled', 'SELECT COUNT(*) FROM source_registry WHERE enabled = 1'),
        ('news_articles_total', 'SELECT COUNT(*) FROM news_articles'),
        ('events_total', 'SELECT COUNT(*) FROM events'),
        ('latest_article_published_at', 'SELECT COALESCE(MAX(published_at), \"\") FROM news_articles'),
        ('latest_event_updated_at', 'SELECT COALESCE(MAX(updated_at), \"\") FROM events'),
    ]
    for label, sql in queries:
        value = conn.execute(sql).fetchone()[0]
        print(f'{label}={value}')
finally:
    conn.close()
PY
else
  echo 'missing_db'
fi
echo

echo '[runtime-news] export-summary'
python3 - <<'PY'
import json
from pathlib import Path

root = Path('${REMOTE_EXPORT_ROOT}')
targets = {
    'opportunity_report_feed_latest.json': [
        ('top_events', lambda data: len(data.get('top_events') or [])),
        ('ranking_view', lambda data: ((data.get('ranking_contract') or {}).get('view') or '')),
    ],
    'research_feed_latest.json': [
        ('recent_events', lambda data: len(data.get('recent_events') or [])),
        ('entity_profiles', lambda data: len(data.get('entity_profiles') or {})),
        ('topic_profiles', lambda data: len(data.get('topic_profiles') or {})),
        ('ranking_view', lambda data: ((data.get('ranking_contract') or {}).get('view') or '')),
    ],
    'industry_radar_feed_latest.json': [
        ('industries', lambda data: len(data.get('industries') or [])),
        ('event_pool_count', lambda data: data.get('event_pool_count') or 0),
        ('macro_events', lambda data: len(((data.get('radar_views') or {}).get('macro_events') or []))),
        ('company_events', lambda data: len(((data.get('radar_views') or {}).get('company_events') or []))),
    ],
    'entity_day_panel_latest.json': [
        ('rows', lambda data: len(data.get('rows') or [])),
        ('days', lambda data: len(data.get('days') or [])),
    ],
    'industry_day_panel_latest.json': [
        ('rows', lambda data: len(data.get('rows') or [])),
        ('days', lambda data: len(data.get('days') or [])),
    ],
    'mapping_review_latest.json': [
        ('unresolved_count', lambda data: data.get('unresolved_count') or 0),
        ('low_confidence_count', lambda data: data.get('low_confidence_count') or 0),
    ],
}

for name, fields in targets.items():
    path = root / name
    if not path.exists():
        print(f'{name}: missing')
        continue
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except Exception as exc:
        print(f'{name}: error={exc}')
        continue
    parts = [f'generated_at={data.get(\"generated_at\") or \"\"}']
    for label, getter in fields:
        try:
            parts.append(f'{label}={getter(data)}')
        except Exception as exc:
            parts.append(f'{label}=error:{exc}')
    print(f'{name}: ' + ' '.join(parts))
PY
echo

echo '[runtime-news] source-health'
python3 - <<'PY'
import json
from pathlib import Path

path = Path('${REMOTE_EXPORT_ROOT}') / 'source_health_latest.json'
if not path.exists():
    print('source_health_latest.json: missing')
else:
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except Exception as exc:
        print(f'source_health_latest.json: error={exc}')
    else:
        sources = data.get('source_health') or []
        degraded = [item for item in sources if str(item.get('status') or '') == 'degraded']
        failed = [item for item in sources if str(item.get('status') or '') == 'failed']
        print(
            'source_health_latest.json:',
            f'generated_at={data.get(\"generated_at\") or \"\"}',
            f'total={len(sources)}',
            f'degraded={len(degraded)}',
            f'failed={len(failed)}',
        )
        for item in (failed + degraded)[:8]:
            print(
                ' ',
                f'- {item.get(\"source_id\")}:',
                f'status={item.get(\"status\")}',
                f'last_collected_at={item.get(\"last_collected_at\") or \"\"}',
            )
PY
"
