#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

try:
    import yaml
except ModuleNotFoundError:  # pragma: no cover - production runtime already uses PyYAML
    yaml = None


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = ROOT / "runtime" / "news_event.db"
DEFAULT_SCHEMA = ROOT / "config" / "schema.sql"
DEFAULT_REGISTRY = ROOT / "config" / "source_registry_v1.yaml"
DEFAULT_CACHE_DIR = ROOT / "runtime" / "fred_us_macro_open_data"
DEFAULT_EVENTS_URL = (
    "https://raw.githubusercontent.com/superpilot69/fred-us-macro-open-data/main/"
    "data/fred-us-macro-events.json"
)
DEFAULT_METADATA_URL = (
    "https://raw.githubusercontent.com/superpilot69/fred-us-macro-open-data/main/"
    "metadata/dataset-metadata.json"
)
SOURCE_ID = "fred_us_macro_open_data"
SOURCE_REPO_URL = "https://github.com/superpilot69/fred-us-macro-open-data"
ADAPTER_VERSION = "fred_us_macro_open_data_import_v1"
SQLITE_BUSY_TIMEOUT_MS = 600000

FALLBACK_SOURCE_CONFIG = {
    "source_id": SOURCE_ID,
    "name": "FRED US Macro Open Data",
    "lane": "confirmation",
    "source_family": "macro:fred",
    "source_type": "api",
    "trust_tier": 1,
    "coverage_scope": "macro",
    "collector_owner": "shared",
    "scheduler_class": "daily",
    "origin_system": "news_event_hub",
    "legacy_key": "superpilot69/fred-us-macro-open-data",
    "phase1_disposition": "migrate_phase1",
    "enabled": True,
    "description": "FRED source-of-record U.S. macro release events enriched with partial Investing.com consensus fields.",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import structured FRED U.S. macro events into the shared news/event database."
    )
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="SQLite database path.")
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA, help="Schema SQL path.")
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY, help="Source registry YAML path.")
    parser.add_argument("--events-url", default=DEFAULT_EVENTS_URL, help="Remote fred-us-macro-events.json URL.")
    parser.add_argument("--metadata-url", default=DEFAULT_METADATA_URL, help="Remote dataset-metadata.json URL.")
    parser.add_argument("--events-file", type=Path, default=None, help="Optional local events JSON file for offline runs/tests.")
    parser.add_argument("--metadata-file", type=Path, default=None, help="Optional local metadata JSON file for offline runs/tests.")
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR, help="Runtime cache directory for downloaded JSON.")
    parser.add_argument("--lookback-days", type=int, default=400, help="Import events released within this many days. Use 0 for full history.")
    parser.add_argument("--since", default="", help="Optional lower bound release timestamp/date; overrides --lookback-days.")
    parser.add_argument("--until", default="", help="Optional upper bound release timestamp/date.")
    parser.add_argument("--max-events", type=int, default=0, help="Optional cap after filtering, newest first. Use 0 for no cap.")
    parser.add_argument("--dry-run", action="store_true", help="Fetch and count without writing the database.")
    return parser.parse_args()


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def parse_datetime(raw: str | None) -> datetime | None:
    value = str(raw or "").strip()
    if not value:
        return None
    if len(value) == 10 and value[4] == "-" and value[7] == "-":
        value = f"{value}T00:00:00+00:00"
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def isoformat_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds")


def normalize_text(value: str | None) -> str:
    return " ".join(str(value or "").strip().split())


def stable_hash(*parts: str) -> str:
    return hashlib.sha256("||".join(parts).encode("utf-8")).hexdigest()


def read_text_from_file_or_url(file_path: Path | None, url: str, cache_path: Path) -> str:
    if file_path:
        return file_path.read_text(encoding="utf-8")
    request = Request(url, headers={"User-Agent": f"{ADAPTER_VERSION} (+{SOURCE_REPO_URL})"})
    with urlopen(request, timeout=45) as response:
        body = response.read().decode("utf-8")
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(body, encoding="utf-8")
    return body


def load_json_payload(file_path: Path | None, url: str, cache_path: Path) -> dict[str, Any]:
    payload = json.loads(read_text_from_file_or_url(file_path, url, cache_path))
    if not isinstance(payload, dict):
        raise SystemExit(f"expected top-level JSON object from {file_path or url}")
    return payload


def load_source_config(registry_path: Path) -> dict[str, Any]:
    if yaml is None or not registry_path.exists():
        return dict(FALLBACK_SOURCE_CONFIG)
    payload = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
    for row in (payload or {}).get("sources", []):
        if isinstance(row, dict) and row.get("source_id") == SOURCE_ID:
            return {**FALLBACK_SOURCE_CONFIG, **row}
    return dict(FALLBACK_SOURCE_CONFIG)


def apply_schema(conn: sqlite3.Connection, schema_path: Path) -> None:
    conn.executescript(schema_path.read_text(encoding="utf-8"))


def upsert_source(conn: sqlite3.Connection, source: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO source_registry (
            source_id, name, lane, source_family, source_type, trust_tier, coverage_scope,
            collector_owner, scheduler_class, origin_system, legacy_key,
            phase1_disposition, enabled, description
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(source_id) DO UPDATE SET
            name = excluded.name,
            lane = excluded.lane,
            source_family = excluded.source_family,
            source_type = excluded.source_type,
            trust_tier = excluded.trust_tier,
            coverage_scope = excluded.coverage_scope,
            collector_owner = excluded.collector_owner,
            scheduler_class = excluded.scheduler_class,
            origin_system = excluded.origin_system,
            legacy_key = excluded.legacy_key,
            phase1_disposition = excluded.phase1_disposition,
            enabled = excluded.enabled,
            description = excluded.description,
            updated_at = datetime('now')
        """,
        (
            str(source.get("source_id") or SOURCE_ID),
            str(source.get("name") or SOURCE_ID),
            str(source.get("lane") or "confirmation"),
            str(source.get("source_family") or "macro:fred"),
            str(source.get("source_type") or "api"),
            int(source.get("trust_tier") or 1),
            str(source.get("coverage_scope") or "macro"),
            str(source.get("collector_owner") or "shared"),
            str(source.get("scheduler_class") or "daily"),
            str(source.get("origin_system") or "news_event_hub"),
            str(source.get("legacy_key") or "superpilot69/fred-us-macro-open-data"),
            str(source.get("phase1_disposition") or "migrate_phase1"),
            1 if bool(source.get("enabled", True)) else 0,
            str(source.get("description") or ""),
        ),
    )


def consensus_summary(consensus: dict[str, Any]) -> str:
    if not consensus:
        return ""
    pieces = []
    actual = consensus.get("actual")
    forecast = consensus.get("forecast")
    previous = consensus.get("previous")
    surprise = consensus.get("surprise")
    unit = consensus.get("unit") or ""
    if actual is not None:
        pieces.append(f"actual={actual}{unit}")
    if forecast is not None:
        pieces.append(f"forecast={forecast}{unit}")
    if previous is not None:
        pieces.append(f"previous={previous}{unit}")
    if surprise is not None:
        pieces.append(f"surprise={surprise}{unit}")
    return ", ".join(pieces)


def build_article_from_event(event: dict[str, Any], dataset_metadata: dict[str, Any], collected_at: str) -> dict[str, Any] | None:
    metadata = event.get("metadata") if isinstance(event.get("metadata"), dict) else {}
    release_at = parse_datetime(event.get("createdAt"))
    if release_at is None:
        return None

    upstream_id = normalize_text(event.get("id"))
    if not upstream_id:
        return None
    series_id = normalize_text(metadata.get("seriesId"))
    title = normalize_text(event.get("textZh")) or normalize_text(event.get("textEn")) or normalize_text(event.get("text"))
    if not title:
        return None
    if not title.startswith("美国"):
        title = f"美国宏观数据：{title}"

    consensus = metadata.get("consensus") if isinstance(metadata.get("consensus"), dict) else {}
    summary_parts = [
        normalize_text(event.get("textEn")) or normalize_text(event.get("text")),
        f"series={series_id}" if series_id else "",
        f"observation={normalize_text(metadata.get('observationDate'))}" if metadata.get("observationDate") else "",
        f"release={isoformat_utc(release_at)}",
        consensus_summary(consensus),
    ]
    summary = " | ".join(part for part in summary_parts if part)
    body = {
        "adapter": ADAPTER_VERSION,
        "source_repo": SOURCE_REPO_URL,
        "upstream_event_id": upstream_id,
        "dataset_generated_at": dataset_metadata.get("generatedAt"),
        "upstream_generated_at": dataset_metadata.get("upstreamGeneratedAt"),
        "release_date_approximate": bool(metadata.get("releaseDateApproximate")),
        "event": event,
    }
    source_url = normalize_text(event.get("url")) or (f"https://fred.stlouisfed.org/series/{series_id}" if series_id else SOURCE_REPO_URL)
    article_id = "fred_macro_" + stable_hash(SOURCE_ID, upstream_id)[:32]
    return {
        "article_id": article_id,
        "source_id": SOURCE_ID,
        "title": title,
        "title_norm": title.casefold(),
        "summary": summary,
        "body_text": json.dumps(body, ensure_ascii=False, sort_keys=True),
        "url": source_url,
        "canonical_url": source_url,
        "published_at": isoformat_utc(release_at),
        "timestamp_quality": "estimated" if metadata.get("releaseDateApproximate") else "exact",
        "content_hash": stable_hash(SOURCE_ID, upstream_id),
        "language": "zh",
        "collector_scope": "baseline_shared",
        "collected_at": collected_at,
    }


def filter_events(
    events: list[dict[str, Any]],
    since: datetime | None,
    until: datetime | None,
    max_events: int,
) -> list[dict[str, Any]]:
    selected = []
    for event in events:
        release_at = parse_datetime(event.get("createdAt"))
        if release_at is None:
            continue
        if since and release_at < since:
            continue
        if until and release_at > until:
            continue
        selected.append(event)
    selected.sort(key=lambda item: parse_datetime(item.get("createdAt")) or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    if max_events > 0:
        selected = selected[:max_events]
    return selected


def upsert_articles(conn: sqlite3.Connection, articles: list[dict[str, Any]]) -> tuple[int, int]:
    insert_sql = """
    INSERT INTO news_articles (
        article_id, source_id, title, title_norm, summary, body_text, url, canonical_url,
        published_at, timestamp_quality, content_hash, language, collector_scope, collected_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(article_id) DO UPDATE SET
        title = excluded.title,
        title_norm = excluded.title_norm,
        summary = excluded.summary,
        body_text = excluded.body_text,
        url = excluded.url,
        canonical_url = excluded.canonical_url,
        published_at = excluded.published_at,
        timestamp_quality = excluded.timestamp_quality,
        content_hash = excluded.content_hash,
        language = excluded.language,
        collector_scope = excluded.collector_scope,
        collected_at = excluded.collected_at
    """
    inserted = 0
    updated = 0
    for article in articles:
        exists = conn.execute("SELECT 1 FROM news_articles WHERE article_id = ?", (article["article_id"],)).fetchone() is not None
        conn.execute(
            insert_sql,
            (
                article["article_id"],
                article["source_id"],
                article["title"],
                article["title_norm"],
                article["summary"],
                article["body_text"],
                article["url"],
                article["canonical_url"],
                article["published_at"],
                article["timestamp_quality"],
                article["content_hash"],
                article["language"],
                article["collector_scope"],
                article["collected_at"],
            ),
        )
        if exists:
            updated += 1
        else:
            inserted += 1
    return inserted, updated


def record_source_health(conn: sqlite3.Connection, status: str, error_message: str | None) -> None:
    row = conn.execute(
        """
        SELECT COUNT(*) AS articles_last_24h, MAX(published_at) AS last_article_at
        FROM news_articles
        WHERE source_id = ?
          AND julianday(published_at) >= julianday('now', '-24 hours')
        """,
        (SOURCE_ID,),
    ).fetchone()
    conn.execute(
        """
        INSERT INTO source_health (source_id, status, articles_last_24h, last_article_at, error_message)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            SOURCE_ID,
            status,
            int(row[0] or 0) if row else 0,
            str(row[1]) if row and row[1] else None,
            error_message,
        ),
    )


def main() -> None:
    args = parse_args()
    if args.lookback_days < 0:
        raise SystemExit("--lookback-days must be >= 0")
    if args.max_events < 0:
        raise SystemExit("--max-events must be >= 0")

    events_payload = load_json_payload(args.events_file, args.events_url, args.cache_dir / "fred-us-macro-events.json")
    metadata_payload = load_json_payload(args.metadata_file, args.metadata_url, args.cache_dir / "dataset-metadata.json")
    events_raw = events_payload.get("events")
    if not isinstance(events_raw, list):
        raise SystemExit("events payload is missing top-level events list")
    events = [event for event in events_raw if isinstance(event, dict)]

    now = utc_now()
    since = parse_datetime(args.since) if args.since else None
    if since is None and args.lookback_days > 0:
        since = now - timedelta(days=args.lookback_days)
    until = parse_datetime(args.until) if args.until else None
    selected = filter_events(events, since, until, args.max_events)
    collected_at = isoformat_utc(now)
    articles = [
        article
        for article in (build_article_from_event(event, metadata_payload, collected_at) for event in selected)
        if article is not None
    ]

    if args.dry_run:
        print(
            "fred_us_macro_import dry_run "
            f"fetched={len(events)} selected={len(selected)} convertible={len(articles)} "
            f"since={isoformat_utc(since) if since else 'full_history'}"
        )
        return

    args.db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(args.db, timeout=SQLITE_BUSY_TIMEOUT_MS / 1000)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute(f"PRAGMA busy_timeout = {SQLITE_BUSY_TIMEOUT_MS}")
        apply_schema(conn, args.schema)
        upsert_source(conn, load_source_config(args.registry))
        inserted, updated = upsert_articles(conn, articles)
        record_source_health(conn, "ok", None)
        conn.commit()
    except Exception as exc:
        conn.rollback()
        try:
            apply_schema(conn, args.schema)
            upsert_source(conn, load_source_config(args.registry))
            record_source_health(conn, "down", str(exc))
            conn.commit()
        except Exception:
            conn.rollback()
        raise
    finally:
        conn.close()

    print(
        "fred_us_macro_import ok "
        f"fetched={len(events)} selected={len(selected)} inserted={inserted} updated={updated} "
        f"since={isoformat_utc(since) if since else 'full_history'}"
    )


if __name__ == "__main__":
    main()
