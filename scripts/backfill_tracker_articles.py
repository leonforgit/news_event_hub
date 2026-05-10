#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import re
import sqlite3
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TARGET_DB = ROOT / "runtime" / "news_event.db"
DEFAULT_SOURCE_DB = Path.home() / ".codex" / "state" / "investment" / "research" / "opportunities" / "data" / "runtime" / "investment_tracker.db"


WHITESPACE_RE = re.compile(r"\s+")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill unified news_articles from investment_tracker.db")
    parser.add_argument("--source-db", type=Path, default=DEFAULT_SOURCE_DB, help="Legacy investment_tracker.db path.")
    parser.add_argument("--target-db", type=Path, default=DEFAULT_TARGET_DB, help="Unified news_event.db path.")
    parser.add_argument("--limit", type=int, default=0, help="Optional max rows to import.")
    parser.add_argument("--include-compat", action="store_true", help="Also import compat_keep sources.")
    return parser.parse_args()


def normalize_title(value: str | None) -> str:
    text = (value or "").strip().lower()
    return WHITESPACE_RE.sub(" ", text)


def detect_language(title: str | None, summary: str | None) -> str:
    sample = f"{title or ''} {summary or ''}"
    return "zh" if re.search(r"[\u4e00-\u9fff]", sample) else "en"


def build_content_hash(title_norm: str, summary: str | None, body_text: str | None, canonical_url: str | None) -> str:
    payload = "||".join(
        [
            title_norm,
            (summary or "").strip()[:2000],
            (body_text or "").strip()[:4000],
            (canonical_url or "").strip(),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def target_mapping(conn: sqlite3.Connection, include_compat: bool) -> dict[str, dict[str, Any]]:
    allowed = ["migrate_phase1"]
    if include_compat:
        allowed.append("compat_keep")
    query = f"""
    SELECT source_id, legacy_key, enabled, phase1_disposition
    FROM source_registry
    WHERE phase1_disposition IN ({",".join("?" for _ in allowed)})
    """
    rows = conn.execute(query, allowed).fetchall()
    mapping: dict[str, dict[str, Any]] = {}
    for source_id, legacy_key, enabled, disposition in rows:
        if legacy_key:
            mapping[str(legacy_key)] = {
                "source_id": str(source_id),
                "enabled": int(enabled),
                "phase1_disposition": str(disposition),
            }
    return mapping


def fetch_source_rows(conn: sqlite3.Connection, legacy_keys: list[str], limit: int) -> list[sqlite3.Row]:
    placeholders = ",".join("?" for _ in legacy_keys)
    sql = f"""
    SELECT
        id,
        source_key,
        title,
        summary,
        body_text,
        url,
        canonical_url,
        published_at,
        fetched_at
    FROM news_articles
    WHERE source_key IN ({placeholders})
    ORDER BY COALESCE(published_at, fetched_at) DESC, id DESC
    """
    if limit > 0:
        sql += f" LIMIT {int(limit)}"
    conn.row_factory = sqlite3.Row
    return conn.execute(sql, legacy_keys).fetchall()


def upsert_articles(conn: sqlite3.Connection, rows: list[sqlite3.Row], mapping: dict[str, dict[str, Any]]) -> tuple[int, int]:
    insert_sql = """
    INSERT INTO news_articles (
        article_id,
        source_id,
        title,
        title_norm,
        summary,
        body_text,
        url,
        canonical_url,
        published_at,
        timestamp_quality,
        content_hash,
        language,
        collector_scope,
        collected_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(article_id) DO UPDATE SET
        source_id = excluded.source_id,
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
    skipped = 0
    for row in rows:
        source_key = str(row["source_key"])
        target = mapping.get(source_key)
        if not target or not target["enabled"]:
            skipped += 1
            continue
        title = str(row["title"] or "").strip()
        summary = row["summary"]
        body_text = row["body_text"]
        canonical_url = row["canonical_url"] or row["url"]
        title_norm = normalize_title(title)
        content_hash = build_content_hash(title_norm, summary, body_text, canonical_url)
        article_id = f"tracker_{int(row['id'])}"
        timestamp_quality = "exact" if row["published_at"] else "unknown"
        language = detect_language(title, summary)
        conn.execute(
            insert_sql,
            (
                article_id,
                target["source_id"],
                title,
                title_norm,
                summary,
                body_text,
                row["url"],
                canonical_url,
                row["published_at"],
                timestamp_quality,
                content_hash,
                language,
                "baseline_shared",
                row["fetched_at"],
            ),
        )
        inserted += 1
    return inserted, skipped


def main() -> None:
    args = parse_args()
    if not args.source_db.exists():
        raise SystemExit(f"source db missing: {args.source_db}")
    if not args.target_db.exists():
        raise SystemExit(f"target db missing: {args.target_db}")

    target_conn = sqlite3.connect(args.target_db)
    source_conn = sqlite3.connect(args.source_db)
    try:
        mapping = target_mapping(target_conn, include_compat=args.include_compat)
        if not mapping:
            raise SystemExit("no source_registry mappings found in target db")
        rows = fetch_source_rows(source_conn, list(mapping.keys()), args.limit)
        inserted, skipped = upsert_articles(target_conn, rows, mapping)
        target_conn.commit()
        total_articles = target_conn.execute("SELECT COUNT(*) FROM news_articles").fetchone()[0]
        print(f"legacy_rows_selected: {len(rows)}")
        print(f"inserted_or_updated: {inserted}")
        print(f"skipped: {skipped}")
        print(f"target_news_articles_total: {total_articles}")
    finally:
        source_conn.close()
        target_conn.close()


if __name__ == "__main__":
    main()
