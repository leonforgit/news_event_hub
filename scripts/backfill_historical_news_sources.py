#!/usr/bin/env python3
"""Backfill date-addressable news sources into the shared news/event database."""

from __future__ import annotations

import argparse
import json
import sqlite3
import time
from datetime import date, datetime, time as dt_time, timedelta
from pathlib import Path
from typing import Any

import requests

from run_live_news_collector import (
    CHINA_TZ,
    CNINFO_CATEGORY,
    DEFAULT_CATALOG,
    DEFAULT_REGISTRY,
    DEFAULT_SCHEMA,
    REQUEST_TIMEOUT,
    SQLITE_BUSY_TIMEOUT_MS,
    ak,
    akshare_records,
    build_akshare_news_cctv_items,
    build_akshare_stock_notice_report_items,
    call_akshare,
    ensure_bootstrap,
    isoformat_utc,
    load_catalog,
    load_registry,
    merge_sources,
    parse_cninfo_items,
    upsert_article,
    utc_now,
)


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = ROOT / "state" / "news_event.db"
DEFAULT_SOURCE_IDS = (
    "cninfo_sz_latest",
    "cninfo_sh_latest",
    "akshare_stock_notice_report",
    "akshare_news_cctv",
)
SUPPORTED_SOURCE_TYPES = {
    "cninfo_latest",
    "akshare_stock_notice_report",
    "akshare_news_cctv",
}
SOURCE_TYPE_MIN_DATES = {
    "akshare_news_cctv": date(2016, 2, 4),
}
LOOKUP_INDEX_SQL = """
CREATE UNIQUE INDEX IF NOT EXISTS idx_articles_source_content_hash
    ON news_articles (source_id, content_hash) WHERE content_hash IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_articles_source_canonical_collected
    ON news_articles (source_id, canonical_url, collected_at DESC)
    WHERE canonical_url IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_articles_source_url_collected
    ON news_articles (source_id, url, collected_at DESC)
    WHERE url IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_articles_source_title_published_collected
    ON news_articles (source_id, title_norm, published_at, collected_at DESC)
    WHERE title_norm IS NOT NULL AND published_at IS NOT NULL;
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill historical daily news/announcement sources.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="Target news_event.db path.")
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA, help="Schema SQL path.")
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY, help="Source registry YAML path.")
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG, help="Live collector catalog JSON path.")
    parser.add_argument("--start-date", required=True, help="Inclusive start date, YYYY-MM-DD.")
    parser.add_argument("--end-date", default=date.today().isoformat(), help="Inclusive end date, YYYY-MM-DD.")
    parser.add_argument(
        "--source-id",
        action="append",
        dest="source_ids",
        help="Source id to backfill. Repeatable. Defaults to CNINFO, Eastmoney notices, and CCTV daily news.",
    )
    parser.add_argument("--sleep-seconds", type=float, default=0.25, help="Delay between provider requests.")
    parser.add_argument("--limit-days", type=int, default=0, help="Optional maximum number of calendar days to process.")
    parser.add_argument("--cninfo-page-size", type=int, default=100, help="CNINFO page size per request.")
    parser.add_argument("--max-cninfo-pages", type=int, default=80, help="Safety cap for CNINFO pagination per day/source.")
    parser.add_argument("--ensure-lookup-indexes", action=argparse.BooleanOptionalAction, default=True, help="Ensure article lookup indexes before writing.")
    parser.add_argument("--dry-run", action="store_true", help="Fetch and parse but do not write rows.")
    return parser.parse_args()


def parse_ymd(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def date_range(start: date, end: date, limit_days: int = 0) -> list[date]:
    if end < start:
        raise SystemExit(f"end-date must be >= start-date: {start} > {end}")
    days: list[date] = []
    cursor = start
    while cursor <= end:
        days.append(cursor)
        if limit_days and len(days) >= limit_days:
            break
        cursor += timedelta(days=1)
    return days


def day_run_dt(day: date) -> datetime:
    return datetime.combine(day, dt_time(hour=12, minute=0), tzinfo=CHINA_TZ)


def historical_source(source: dict[str, Any]) -> dict[str, Any]:
    output = dict(source)
    output["max_age_hours"] = None
    output["max_items"] = 0
    return output


def fetch_cninfo_day(
    session: requests.Session,
    source: dict[str, Any],
    day: date,
    page_size: int,
    max_pages: int,
) -> tuple[list[dict[str, Any]], str | None, int]:
    items: list[dict[str, Any]] = []
    page_count = 0
    headers = {
        "User-Agent": str(source.get("user_agent") or "Mozilla/5.0"),
        "Referer": "https://www.cninfo.com.cn/new/commonUrl/pageOfSearch?url=disclosure/list/search&lastPath=disclosure/list/notice",
        "X-Requested-With": "XMLHttpRequest",
    }
    for page_num in range(1, max_pages + 1):
        payload = {
            "pageNum": str(page_num),
            "pageSize": str(page_size),
            "column": source.get("column", "szse"),
            "tabName": "fulltext",
            "plate": source.get("plate", "sz"),
            "searchkey": source.get("searchkey", ""),
            "secid": source.get("secid", ""),
            "category": source.get("category", CNINFO_CATEGORY),
            "seDate": f"{day.isoformat()}~{day.isoformat()}",
            "sortName": "nothing",
            "sortType": "desc",
            "isHLtitle": "true",
        }
        response = session.post(str(source["url"]), headers=headers, data=payload, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        body = response.json()
        page_items = parse_cninfo_items(body, source)
        page_count += 1
        if not page_items:
            break
        items.extend(page_items)
        total_pages_raw = body.get("totalpages") or body.get("totalPages") or body.get("totalPageNum")
        try:
            total_pages = int(total_pages_raw)
        except (TypeError, ValueError):
            total_pages = 0
        if total_pages and page_num >= total_pages:
            break
        if len(page_items) < page_size and not total_pages:
            break
    error = None
    if page_count >= max_pages:
        error = f"hit max-cninfo-pages={max_pages}"
    deduped = {str(item.get("canonical_url") or item.get("url") or item.get("title")): item for item in items}
    return list(deduped.values()), error, page_count


def fetch_akshare_day(source: dict[str, Any], day: date) -> tuple[list[dict[str, Any]], str | None, int]:
    if ak is None:
        raise ModuleNotFoundError("akshare is not installed")
    date_str = day.strftime("%Y%m%d")
    source_type = str(source.get("type") or "")
    if source_type == "akshare_news_cctv":
        records = akshare_records(call_akshare(ak.news_cctv, date=date_str))
        return build_akshare_news_cctv_items(records, source, day_run_dt(day)), None, 1
    if source_type == "akshare_stock_notice_report":
        symbol = str(source.get("symbol") or "全部").strip() or "全部"
        try:
            records = akshare_records(call_akshare(ak.stock_notice_report, symbol=symbol, date=date_str))
        except KeyError as exc:
            if str(exc).strip("'\"") == "代码":
                return [], None, 1
            raise
        return build_akshare_stock_notice_report_items(records, source), None, 1
    raise ValueError(f"unsupported akshare source type: {source_type}")


def write_items(
    conn: sqlite3.Connection,
    source: dict[str, Any],
    items: list[dict[str, Any]],
    collected_at: str,
    dry_run: bool,
) -> dict[str, int]:
    result = {"inserted": 0, "updated": 0, "duplicate": 0, "skipped": 0}
    if dry_run:
        result["skipped"] = len(items)
        return result
    for item in items:
        action = upsert_article(conn, source, item, collected_at)
        result[action] = result.get(action, 0) + 1
    return result


def ensure_lookup_indexes(conn: sqlite3.Connection) -> None:
    conn.executescript(LOOKUP_INDEX_SQL)


def main() -> None:
    args = parse_args()
    source_ids = tuple(args.source_ids or DEFAULT_SOURCE_IDS)
    registry = load_registry(args.registry)
    sources = merge_sources(load_registry(args.registry), load_catalog(args.catalog), scheduler_classes=None, source_ids=set(source_ids))
    by_id = {str(source["source_id"]): historical_source(source) for source in sources}
    missing = [source_id for source_id in source_ids if source_id not in by_id]
    if missing:
        raise SystemExit(f"source ids not enabled/found in registry+catalog: {', '.join(missing)}")
    unsupported = [
        source_id
        for source_id, source in by_id.items()
        if str(source.get("type") or "") not in SUPPORTED_SOURCE_TYPES
    ]
    if unsupported:
        raise SystemExit(f"unsupported source types for historical backfill: {', '.join(unsupported)}")

    days = date_range(parse_ymd(args.start_date), parse_ymd(args.end_date), int(args.limit_days or 0))
    conn = sqlite3.connect(args.db, timeout=SQLITE_BUSY_TIMEOUT_MS / 1000)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(f"PRAGMA busy_timeout = {SQLITE_BUSY_TIMEOUT_MS}")
    ensure_bootstrap(conn, args.schema, registry)
    if args.ensure_lookup_indexes:
        ensure_lookup_indexes(conn)
    conn.commit()

    totals: dict[str, Any] = {
        "started_at": isoformat_utc(utc_now()),
        "db": str(args.db),
        "start_date": days[0].isoformat() if days else args.start_date,
        "end_date": days[-1].isoformat() if days else args.end_date,
        "source_ids": list(source_ids),
        "days": len(days),
        "fetched": 0,
        "inserted": 0,
        "updated": 0,
        "duplicate": 0,
        "skipped": 0,
        "errors": 0,
        "dry_run": bool(args.dry_run),
    }
    session = requests.Session()
    try:
        for day in days:
            for source_id in source_ids:
                source = by_id[source_id]
                source_type = str(source.get("type") or "")
                row: dict[str, Any] = {
                    "date": day.isoformat(),
                    "source_id": source_id,
                    "source_type": source_type,
                    "status": "ok",
                    "fetched": 0,
                    "inserted": 0,
                    "updated": 0,
                    "duplicate": 0,
                    "skipped": 0,
                    "requests": 0,
                    "error": None,
                }
                try:
                    min_source_date = SOURCE_TYPE_MIN_DATES.get(source_type)
                    if min_source_date and day < min_source_date:
                        row["status"] = "skipped"
                        row["error"] = f"source_min_date={min_source_date.isoformat()}"
                        print(json.dumps(row, ensure_ascii=False), flush=True)
                        continue
                    if source_type == "cninfo_latest":
                        items, warning, requests_made = fetch_cninfo_day(
                            session,
                            source,
                            day,
                            page_size=int(args.cninfo_page_size),
                            max_pages=int(args.max_cninfo_pages),
                        )
                    else:
                        items, warning, requests_made = fetch_akshare_day(source, day)
                    row["requests"] = requests_made
                    row["fetched"] = len(items)
                    if warning:
                        row["status"] = "degraded"
                        row["error"] = warning
                    collected_at = isoformat_utc(day_run_dt(day))
                    if not args.dry_run:
                        conn.execute("BEGIN IMMEDIATE")
                    write_result = write_items(conn, source, items, collected_at, bool(args.dry_run))
                    if not args.dry_run:
                        conn.commit()
                    row.update(write_result)
                    for key in ("fetched", "inserted", "updated", "duplicate", "skipped"):
                        totals[key] += int(row[key])
                except Exception as exc:  # noqa: BLE001
                    if conn.in_transaction:
                        conn.rollback()
                    row["status"] = "error"
                    row["error"] = f"{type(exc).__name__}: {exc}"
                    totals["errors"] += 1
                print(json.dumps(row, ensure_ascii=False), flush=True)
                if args.sleep_seconds > 0:
                    time.sleep(float(args.sleep_seconds))
    finally:
        session.close()
        conn.close()

    totals["finished_at"] = isoformat_utc(utc_now())
    print(json.dumps({"summary": totals}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
