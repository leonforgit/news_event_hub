#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = ROOT / "runtime" / "news_event.db"
DEFAULT_SCHEMA = ROOT / "config" / "schema.sql"
DEFAULT_REGISTRY = ROOT / "config" / "source_registry_v1.yaml"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Initialize and seed the unified news database.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="SQLite database path.")
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA, help="Schema SQL path.")
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY, help="Source registry YAML path.")
    parser.add_argument("--check-only", action="store_true", help="Validate schema/registry without writing the database.")
    return parser.parse_args()


def load_registry(path: Path) -> list[dict[str, Any]]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    sources = payload.get("sources")
    if not isinstance(sources, list):
        raise SystemExit(f"registry file is missing a top-level 'sources' list: {path}")
    normalized: list[dict[str, Any]] = []
    for item in sources:
        if not isinstance(item, dict):
            raise SystemExit(f"registry item must be a mapping: {item!r}")
        source_id = str(item.get("source_id") or "").strip()
        name = str(item.get("name") or "").strip()
        lane = str(item.get("lane") or "").strip()
        if not source_id or not name or lane not in {"confirmation", "signal"}:
            raise SystemExit(f"invalid registry item: {item!r}")
        normalized.append(item)
    return normalized


def table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def ensure_event_schema_evolution(conn: sqlite3.Connection) -> None:
    if not table_exists(conn, "events"):
        return
    existing = {str(row[1]) for row in conn.execute("PRAGMA table_info(events)").fetchall()}
    additions = [
        ("topic_key", "ALTER TABLE events ADD COLUMN topic_key TEXT"),
        ("event_state", "ALTER TABLE events ADD COLUMN event_state TEXT NOT NULL DEFAULT 'emerging'"),
        ("score_vector", "ALTER TABLE events ADD COLUMN score_vector TEXT"),
        ("calibrated_confirmation", "ALTER TABLE events ADD COLUMN calibrated_confirmation REAL"),
        ("uncertainty", "ALTER TABLE events ADD COLUMN uncertainty REAL"),
        ("article_count_raw", "ALTER TABLE events ADD COLUMN article_count_raw INTEGER NOT NULL DEFAULT 0"),
        ("independent_evidence_count", "ALTER TABLE events ADD COLUMN independent_evidence_count INTEGER NOT NULL DEFAULT 0"),
        ("source_family_count", "ALTER TABLE events ADD COLUMN source_family_count INTEGER NOT NULL DEFAULT 0"),
        ("signal_platform_count", "ALTER TABLE events ADD COLUMN signal_platform_count INTEGER NOT NULL DEFAULT 0"),
    ]
    for column, sql in additions:
        if column not in existing:
            conn.execute(sql)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_events_state ON events (event_state)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_events_topic ON events (topic_key)")


def ensure_mapping_schema_evolution(conn: sqlite3.Connection) -> None:
    if table_exists(conn, "event_entity_links"):
        row = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'event_entity_links'"
        ).fetchone()
        create_sql = str(row[0] or "") if row else ""
        if "'institution'" not in create_sql:
            conn.execute("ALTER TABLE event_entity_links RENAME TO event_entity_links_legacy_migration")
            conn.execute(
                """
                CREATE TABLE event_entity_links (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id        TEXT NOT NULL REFERENCES events (event_id) ON DELETE CASCADE,
                    entity_type     TEXT NOT NULL
                                        CHECK (entity_type IN ('industry', 'company', 'theme', 'macro_theme', 'institution')),
                    entity_id       TEXT NOT NULL,
                    entity_name     TEXT NOT NULL,
                    relevance_score REAL DEFAULT 1.0,
                    mapping_reason  TEXT,
                    mapping_confidence REAL,
                    mapping_version TEXT,
                    mapping_source  TEXT,
                    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
                )
                """
            )
            conn.execute(
                """
                INSERT INTO event_entity_links (
                    id, event_id, entity_type, entity_id, entity_name, relevance_score,
                    mapping_reason, mapping_confidence, mapping_version, mapping_source, created_at
                )
                SELECT
                    id, event_id, entity_type, entity_id, entity_name, relevance_score,
                    mapping_reason, mapping_confidence, mapping_version, mapping_source, created_at
                FROM event_entity_links_legacy_migration
                """
            )
            conn.execute("DROP TABLE event_entity_links_legacy_migration")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_eel_event ON event_entity_links (event_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_eel_entity ON event_entity_links (entity_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_eel_entity_type ON event_entity_links (entity_type)")
        existing = {str(row[1]) for row in conn.execute("PRAGMA table_info(event_entity_links)").fetchall()}
        additions = [
            ("mapping_reason", "ALTER TABLE event_entity_links ADD COLUMN mapping_reason TEXT"),
            ("mapping_confidence", "ALTER TABLE event_entity_links ADD COLUMN mapping_confidence REAL"),
            ("mapping_version", "ALTER TABLE event_entity_links ADD COLUMN mapping_version TEXT"),
            ("mapping_source", "ALTER TABLE event_entity_links ADD COLUMN mapping_source TEXT"),
        ]
        for column, sql in additions:
            if column not in existing:
                conn.execute(sql)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS unresolved_event_mappings (
            event_id           TEXT PRIMARY KEY REFERENCES events (event_id) ON DELETE CASCADE,
            topic_key          TEXT,
            event_title        TEXT NOT NULL,
            unresolved_reason  TEXT NOT NULL,
            mapping_version    TEXT NOT NULL DEFAULT 'mapping_layer_v1',
            detected_at        TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at         TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_unresolved_event_mappings_topic ON unresolved_event_mappings (topic_key)")


def ensure_opportunity_schema_evolution(conn: sqlite3.Connection) -> None:
    if not table_exists(conn, "opportunity_signals"):
        return
    existing = {str(row[1]) for row in conn.execute("PRAGMA table_info(opportunity_signals)").fetchall()}
    additions = [
        ("opportunity_type", "ALTER TABLE opportunity_signals ADD COLUMN opportunity_type TEXT"),
        ("opportunity_bucket", "ALTER TABLE opportunity_signals ADD COLUMN opportunity_bucket TEXT"),
    ]
    for column, sql in additions:
        if column not in existing:
            conn.execute(sql)


def ensure_source_registry_schema_evolution(conn: sqlite3.Connection) -> None:
    if not table_exists(conn, "source_registry"):
        return
    existing = {str(row[1]) for row in conn.execute("PRAGMA table_info(source_registry)").fetchall()}
    if "source_family" not in existing:
        conn.execute("ALTER TABLE source_registry ADD COLUMN source_family TEXT")


def apply_schema(conn: sqlite3.Connection, schema_path: Path) -> None:
    ensure_source_registry_schema_evolution(conn)
    ensure_event_schema_evolution(conn)
    ensure_mapping_schema_evolution(conn)
    ensure_opportunity_schema_evolution(conn)
    conn.executescript(schema_path.read_text(encoding="utf-8"))


def upsert_sources(conn: sqlite3.Connection, sources: list[dict[str, Any]]) -> None:
    sql = """
    INSERT INTO source_registry (
        source_id,
        name,
        lane,
        source_family,
        source_type,
        trust_tier,
        coverage_scope,
        collector_owner,
        scheduler_class,
        origin_system,
        legacy_key,
        phase1_disposition,
        enabled,
        description
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
    """
    rows = []
    for item in sources:
        rows.append(
            (
                str(item["source_id"]),
                str(item["name"]),
                str(item["lane"]),
                str(item.get("source_family") or ""),
                str(item.get("source_type") or "scrape"),
                int(item.get("trust_tier") or 2),
                str(item.get("coverage_scope") or "mixed"),
                str(item.get("collector_owner") or "shared"),
                str(item.get("scheduler_class") or "daily"),
                str(item.get("origin_system") or "news_event_hub"),
                str(item.get("legacy_key") or item["source_id"]),
                str(item.get("phase1_disposition") or "migrate_phase1"),
                1 if bool(item.get("enabled")) else 0,
                str(item.get("description") or ""),
            )
        )
    conn.executemany(sql, rows)


def print_summary(conn: sqlite3.Connection) -> None:
    total = conn.execute("SELECT COUNT(*) FROM source_registry").fetchone()[0]
    enabled = conn.execute("SELECT COUNT(*) FROM source_registry WHERE enabled = 1").fetchone()[0]
    by_lane = conn.execute(
        "SELECT lane, COUNT(*) FROM source_registry GROUP BY lane ORDER BY lane"
    ).fetchall()
    by_disposition = conn.execute(
        "SELECT phase1_disposition, COUNT(*) FROM source_registry GROUP BY phase1_disposition ORDER BY phase1_disposition"
    ).fetchall()
    print(f"db_ready: {total} sources ({enabled} enabled)")
    print("lane_counts:")
    for lane, count in by_lane:
        print(f"  - {lane}: {count}")
    print("phase1_disposition_counts:")
    for disposition, count in by_disposition:
        print(f"  - {disposition}: {count}")


def main() -> None:
    args = parse_args()
    sources = load_registry(args.registry)
    if args.check_only:
        print(f"registry_ok: {len(sources)} sources from {args.registry}")
        return

    args.db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(args.db)
    try:
        apply_schema(conn, args.schema)
        upsert_sources(conn, sources)
        conn.commit()
        print_summary(conn)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
