#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import subprocess
import sys
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

import run_live_news_collector as live_news_collector
from discovery_routing import (
    ROUTE_KEYS,
    build_company_discovery_routes,
    build_entity_discovery_routes,
    build_macro_discovery_route,
    build_special_situation_discovery_route,
    build_tracking_update_discovery_route,
    source_ids_for_route,
)
from export_consumer_views import build_exports, normalize_lookup_key, write_json
from run_browser_signal_collector import DEFAULT_BROWSER_CATALOG, fetch_xueqiu_dom_search
from run_live_news_collector import (
    DEFAULT_AGENT_REACH_STATE,
    DEFAULT_CATALOG,
    DEFAULT_CONSUMER_EXPORT_ROOT,
    DEFAULT_DB,
    DEFAULT_REGISTRY,
    DEFAULT_SCHEMA,
    DEFAULT_WATCHLIST_REGISTRY,
    DEFAULT_WEIBO_STATE,
    ensure_bootstrap,
    fetch_source,
    infer_region_from_ticker,
    is_recent_enough,
    isoformat_utc,
    load_catalog,
    load_registry,
    normalize_company_name,
    upsert_article,
    utc_now,
)


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_DIR = ROOT / "runtime" / "company_discovery"
DEFAULT_BROWSER_SIGNAL_PYTHON = ROOT / "runtime" / "browser_signal" / ".venv" / "bin" / "python"
DEFAULT_REBUILD_LOOKBACK_DAYS = 365
DEFAULT_EXPORT_LOOKBACK_HOURS = 24 * 30
DEFAULT_RESEARCH_LIMIT = 180
MAX_MATCH_SCAN_ROWS = 2500
CHINESE_RE = re.compile(r"[\u4e00-\u9fff]")
WORD_RE = re.compile(r"[A-Za-z0-9]+")
ROUTE_DEFAULT_ENTITY_TYPE = {
    "company": "company",
    "macro": "macro_theme",
    "industry": "industry",
    "institution": "institution",
    "special_situation": "company",
    "tracking_update": "mixed",
}


@dataclass
class DiscoveryTarget:
    target_name: str
    entity_type: str
    route_key: str
    aliases: list[str]
    ticker: str
    region: str
    search_terms: list[str]
    explicit_targets: list[dict[str, str]]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run on-demand discovery against the shared news system.")
    parser.add_argument("--company", default="", help="Primary company name to research. Backward-compatible alias for --target-name with route_key=company.")
    parser.add_argument("--target-name", default="", help="Primary target name to research.")
    parser.add_argument("--alias", action="append", dest="aliases", help="Optional alias. Can be repeated.")
    parser.add_argument("--search-term", action="append", dest="search_terms", help="Optional additional discovery search term. Can be repeated.")
    parser.add_argument("--ticker", default="", help="Optional ticker, e.g. 9992.HK / 301362.SZ / NVDA.")
    parser.add_argument("--region", default="", help="Optional region override: CN / HK / US / GLOBAL.")
    parser.add_argument("--entity-type", default="", help="Target entity type: company / industry / institution / macro_theme / mixed.")
    parser.add_argument("--route-key", default="company", choices=list(ROUTE_KEYS), help="Discovery route key to execute.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="SQLite database path.")
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA, help="Schema SQL path.")
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY, help="Source registry YAML path.")
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG, help="Live collector catalog JSON path.")
    parser.add_argument("--browser-catalog", type=Path, default=DEFAULT_BROWSER_CATALOG, help="Browser signal catalog JSON path.")
    parser.add_argument("--consumer-export-root", type=Path, default=DEFAULT_CONSUMER_EXPORT_ROOT, help="Shared consumer export directory.")
    parser.add_argument("--watchlist-registry", type=Path, default=DEFAULT_WATCHLIST_REGISTRY, help="Canonical watchlist registry CSV.")
    parser.add_argument("--weibo-state-path", type=Path, default=DEFAULT_WEIBO_STATE, help="Weibo storage-state JSON.")
    parser.add_argument("--storage-state-path", type=Path, default=DEFAULT_AGENT_REACH_STATE, help="Playwright storage-state JSON.")
    parser.add_argument("--rebuild-lookback-days", type=int, default=DEFAULT_REBUILD_LOOKBACK_DAYS)
    parser.add_argument("--export-lookback-hours", type=int, default=DEFAULT_EXPORT_LOOKBACK_HOURS)
    parser.add_argument("--research-limit", type=int, default=DEFAULT_RESEARCH_LIMIT)
    parser.add_argument("--article-limit", type=int, default=24, help="How many matched articles to return.")
    parser.add_argument("--event-limit", type=int, default=12, help="How many matched events to return.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="Directory for discovery result JSON.")
    parser.add_argument("--output-file", type=Path, default=None, help="Optional explicit JSON output path.")
    parser.add_argument("--source-id", action="append", dest="source_ids", help="Restrict discovery to one source id. Can be repeated.")
    parser.add_argument("--max-live-sources", type=int, default=0, help="Optional cap for live sources after routing and filtering.")
    parser.add_argument("--max-browser-sources", type=int, default=0, help="Optional cap for browser-backed sources after routing and filtering.")
    parser.add_argument("--request-timeout-seconds", type=int, default=25, help="Per-request timeout used by live source fetchers.")
    parser.add_argument("--skip-event-rebuild", action="store_true", help="Skip global event-layer rebuild for bounded on-demand checks.")
    parser.add_argument("--skip-consumer-export", action="store_true", help="Do not write refreshed consumer exports to disk.")
    return parser.parse_args()


def dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        clean = str(value or "").strip()
        if not clean or clean.casefold() in seen:
            continue
        seen.add(clean.casefold())
        result.append(clean)
    return result


def normalize_target_name(value: str, entity_type: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    if entity_type == "company":
        return normalize_company_name(raw)
    return re.sub(r"\s+", " ", raw)


def build_target(
    target_name: str,
    aliases: list[str] | None,
    ticker: str,
    region: str,
    *,
    entity_type: str = "company",
    route_key: str = "company",
    extra_search_terms: list[str] | None = None,
) -> DiscoveryTarget:
    clean_route_key = str(route_key or "company").strip() or "company"
    clean_entity_type = str(entity_type or "").strip() or ROUTE_DEFAULT_ENTITY_TYPE.get(clean_route_key, "company")
    primary_name = normalize_target_name(target_name, clean_entity_type)
    if not primary_name:
        raise ValueError("target_name or company is required")
    clean_ticker = str(ticker or "").strip().upper()
    inferred_region = str(region or "").strip().upper() or infer_region_from_ticker(clean_ticker) or "GLOBAL"
    raw_terms = [primary_name, *(aliases or []), *(extra_search_terms or [])]
    if clean_ticker:
        raw_terms.append(clean_ticker)
        raw_terms.append(clean_ticker.split(".", 1)[0])
    search_terms = dedupe_preserve_order(
        [normalize_target_name(value, clean_entity_type) for value in raw_terms if normalize_target_name(value, clean_entity_type)]
    )
    explicit_targets = []
    for name in search_terms:
        explicit_targets.append(
            {
                "name": name,
                "ticker": clean_ticker,
                "region": inferred_region,
                "entity_type": clean_entity_type,
                "route_key": clean_route_key,
            }
        )
    return DiscoveryTarget(
        target_name=primary_name,
        entity_type=clean_entity_type,
        route_key=clean_route_key,
        aliases=dedupe_preserve_order(
            [normalize_target_name(value, clean_entity_type) for value in aliases or [] if normalize_target_name(value, clean_entity_type)]
        ),
        ticker=clean_ticker,
        region=inferred_region,
        search_terms=search_terms,
        explicit_targets=explicit_targets,
    )


def load_catalog_map(path: Path) -> dict[str, dict[str, Any]]:
    return {str(row.get("key") or "").strip(): row for row in load_catalog(path)}


def build_source(
    source_id: str,
    registry: dict[str, dict[str, Any]],
    catalog_map: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    registry_row = dict(registry[source_id])
    catalog_row = dict(catalog_map[source_id])
    return {
        **registry_row,
        **catalog_row,
        "source_id": source_id,
        "scheduler_class": str(registry_row.get("scheduler_class") or ""),
    }


def source_ids_for_target(target: DiscoveryTarget) -> tuple[list[str], list[str]]:
    return source_ids_for_route(target.route_key, target.search_terms, ticker=target.ticker, region=target.region)


def build_target_route(target: DiscoveryTarget) -> dict[str, Any]:
    if target.route_key == "company":
        return build_company_discovery_routes(
            company=target.target_name,
            aliases=target.aliases,
            ticker=target.ticker,
            region=target.region,
        )
    if target.route_key == "macro":
        return build_macro_discovery_route(search_terms=target.search_terms)
    if target.route_key == "special_situation":
        return build_special_situation_discovery_route(search_terms=target.search_terms)
    if target.route_key == "tracking_update":
        return build_tracking_update_discovery_route(search_terms=target.search_terms)
    return build_entity_discovery_routes(
        entity_name=target.target_name,
        entity_type=target.entity_type,
        aliases=target.aliases,
        ticker=target.ticker,
        region=target.region,
    )


def quote_query_term(value: str) -> str:
    clean = str(value or "").strip()
    if not clean:
        return ""
    escaped = clean.replace('"', "")
    return f"\"{escaped}\""


def build_bing_query(source_id: str, target: DiscoveryTarget, original_query: str) -> str:
    quoted_terms = [quote_query_term(term) for term in target.search_terms[:6] if quote_query_term(term)]
    alias_clause = " OR ".join(quoted_terms)
    if not alias_clause:
        return original_query
    if source_id == "reuters_company_bing":
        return f"({alias_clause}) site:reuters.com Reuters company"
    if source_id == "company_cnbc_bing":
        return f"({alias_clause}) CNBC company earnings acquisition financing"
    if source_id == "company_marketwatch_bing":
        return f"({alias_clause}) MarketWatch company earnings acquisition financing"
    return f"({alias_clause}) {original_query}"


def configure_source(source: dict[str, Any], target: DiscoveryTarget, args: argparse.Namespace) -> dict[str, Any]:
    configured = dict(source)
    configured["consumer_export_root"] = str(args.consumer_export_root)
    configured["watchlist_registry"] = str(args.watchlist_registry)
    configured["weibo_state_path"] = str(args.weibo_state_path)
    configured["storage_state_path"] = str(args.storage_state_path)
    configured["target_names"] = list(target.search_terms[:12])
    configured["explicit_targets"] = list(target.explicit_targets[:12])
    configured["max_targets"] = max(int(configured.get("max_targets") or 0), min(len(target.search_terms), 12)) or min(len(target.search_terms), 12)
    if configured.get("type") == "reddit_search_json":
        configured["limit"] = max(int(configured.get("limit") or 0), 12)
    if configured.get("type") == "weibo_mobile_search":
        configured["pages"] = max(int(configured.get("pages") or 0), 2)
    if configured.get("type") == "xueqiu_status_search":
        configured["pages"] = max(int(configured.get("pages") or 0), 2)
        configured["count"] = max(int(configured.get("count") or 0), 15)
    if configured.get("type") == "xueqiu_dom_search":
        configured["max_items_per_target"] = max(int(configured.get("max_items_per_target") or 0), 6)
    if configured.get("type") == "bing_news_rss":
        configured["query"] = build_bing_query(str(configured["source_id"]), target, str(configured.get("query") or ""))
    return configured


def build_match_terms(target: DiscoveryTarget) -> list[str]:
    terms = list(target.search_terms)
    if target.ticker:
        code = target.ticker.split(".", 1)[0]
        terms.extend([target.ticker, code])
    return dedupe_preserve_order(terms)


def text_contains_term(text: str, term: str) -> bool:
    haystack = str(text or "")
    needle = str(term or "").strip()
    if not haystack or not needle:
        return False
    if CHINESE_RE.search(needle):
        return needle in haystack
    if re.fullmatch(r"[A-Z0-9]{2,8}(?:\.[A-Z]{2})?", needle, re.IGNORECASE):
        return re.search(rf"(?<![A-Za-z0-9]){re.escape(needle)}(?![A-Za-z0-9])", haystack, re.IGNORECASE) is not None
    return needle.casefold() in haystack.casefold()


def item_matches_target(item: dict[str, Any], match_terms: list[str]) -> bool:
    text = " ".join(
        str(item.get(field) or "")
        for field in ("title", "summary", "body_text", "url", "canonical_url")
    )
    return any(text_contains_term(text, term) for term in match_terms)


def persist_items(
    conn: sqlite3.Connection,
    source: dict[str, Any],
    items: list[dict[str, Any]],
    run_dt: datetime,
) -> dict[str, int]:
    counters = defaultdict(int)
    collected_at = isoformat_utc(run_dt)
    for item in items:
        action = upsert_article(conn, source, item, collected_at)
        counters[action] += 1
    conn.commit()
    return {
        "inserted": int(counters["inserted"]),
        "updated": int(counters["updated"]),
        "duplicate": int(counters["duplicate"]),
        "skipped": int(counters["skipped"]),
    }


def run_live_discovery_source(
    conn: sqlite3.Connection,
    session: requests.Session,
    source: dict[str, Any],
    target: DiscoveryTarget,
    run_dt: datetime,
) -> dict[str, Any]:
    started = time.monotonic()
    raw_items, error = fetch_source(session, source, run_dt)
    match_terms = build_match_terms(target)
    matched_items = [item for item in raw_items if item_matches_target(item, match_terms)]
    fresh_items = [
        item
        for item in matched_items
        if is_recent_enough(item, int(source.get("max_age_hours")) if source.get("max_age_hours") is not None else None, run_dt)
    ]
    persisted = persist_items(conn, source, fresh_items, run_dt) if fresh_items else {"inserted": 0, "updated": 0, "duplicate": 0, "skipped": 0}
    status = "ok"
    if error and not raw_items:
        status = "down"
    elif error:
        status = "degraded"
    elif not fresh_items:
        status = "degraded"
    return {
        "source_id": str(source["source_id"]),
        "status": status,
        "error": error,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "fetched_items": len(raw_items),
        "matched_items": len(matched_items),
        "eligible_items": len(fresh_items),
        **persisted,
    }


def run_browser_discovery_source(
    conn: sqlite3.Connection,
    source: dict[str, Any],
    target: DiscoveryTarget,
    run_dt: datetime,
    storage_state_path: Path,
) -> dict[str, Any]:
    started = time.monotonic()
    match_terms = build_match_terms(target)
    if str(source.get("type") or "") == "xueqiu_dom_search":
        raw_items, error = execute_xueqiu_dom_fetch(source, run_dt, storage_state_path)
    else:
        raw_items, error = [], f"unsupported browser source type: {source.get('type')}"
    matched_items = [item for item in raw_items if item_matches_target(item, match_terms)]
    fresh_items = [
        item
        for item in matched_items
        if is_recent_enough(item, int(source.get("max_age_hours")) if source.get("max_age_hours") is not None else None, run_dt)
    ]
    persisted = persist_items(conn, source, fresh_items, run_dt) if fresh_items else {"inserted": 0, "updated": 0, "duplicate": 0, "skipped": 0}
    status = "ok"
    if error and not raw_items:
        status = "down"
    elif error:
        status = "degraded"
    elif not fresh_items:
        status = "degraded"
    return {
        "source_id": str(source["source_id"]),
        "status": status,
        "error": error,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "fetched_items": len(raw_items),
        "matched_items": len(matched_items),
        "eligible_items": len(fresh_items),
        **persisted,
    }


def execute_xueqiu_dom_fetch(source: dict[str, Any], run_dt: datetime, storage_state_path: Path) -> tuple[list[dict[str, Any]], str | None]:
    try:
        from playwright.sync_api import sync_playwright
    except ModuleNotFoundError as exc:
        fallback_python = DEFAULT_BROWSER_SIGNAL_PYTHON
        if not fallback_python.exists():
            return [], str(exc)
        snippet = """
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(sys.argv[1]) / "scripts"))
from run_browser_signal_collector import fetch_xueqiu_dom_search
from playwright.sync_api import sync_playwright

source = json.loads(sys.argv[2])
run_dt = datetime.fromisoformat(sys.argv[3])
storage_state_path = Path(sys.argv[4])
with sync_playwright() as playwright:
    items, error = fetch_xueqiu_dom_search(playwright, source, run_dt, storage_state_path)
print(json.dumps({"items": items, "error": error}, ensure_ascii=False))
"""
        proc = subprocess.run(
            [
                str(fallback_python),
                "-c",
                snippet,
                str(ROOT),
                json.dumps(source, ensure_ascii=False),
                run_dt.isoformat(timespec="seconds"),
                str(storage_state_path),
            ],
            capture_output=True,
            text=True,
            cwd=str(ROOT),
        )
        if proc.returncode != 0:
            stderr = proc.stderr.strip() or proc.stdout.strip() or str(exc)
            return [], stderr
        try:
            payload = json.loads(proc.stdout.strip() or "{}")
        except json.JSONDecodeError:
            return [], proc.stdout.strip() or str(exc)
        return list(payload.get("items") or []), str(payload.get("error") or "").strip() or None

    with sync_playwright() as playwright:
        return fetch_xueqiu_dom_search(playwright, source, run_dt, storage_state_path)


def query_matching_articles(conn: sqlite3.Connection, target: DiscoveryTarget, limit: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT article_id, source_id, title, summary, canonical_url, published_at, collected_at
        FROM news_articles
        ORDER BY datetime(COALESCE(published_at, collected_at, created_at)) DESC, article_id DESC
        LIMIT ?
        """,
        (MAX_MATCH_SCAN_ROWS,),
    ).fetchall()
    match_terms = build_match_terms(target)
    matches: list[dict[str, Any]] = []
    for row in rows:
        payload = {
            "article_id": str(row[0]),
            "source_id": str(row[1]),
            "title": str(row[2] or ""),
            "summary": str(row[3] or ""),
            "canonical_url": str(row[4] or ""),
            "published_at": str(row[5] or ""),
            "collected_at": str(row[6] or ""),
        }
        if item_matches_target(payload, match_terms):
            matches.append(payload)
        if len(matches) >= limit:
            break
    return matches


def count_matching_events(conn: sqlite3.Connection, target: DiscoveryTarget) -> int:
    rows = conn.execute(
        """
        SELECT e.event_id, e.event_title, e.primary_entity, group_concat(eel.entity_name, ' || ')
        FROM events e
        LEFT JOIN event_entity_links eel ON eel.event_id = e.event_id
        GROUP BY e.event_id, e.event_title, e.primary_entity
        ORDER BY datetime(COALESCE(e.last_seen_at, e.first_seen_at)) DESC
        LIMIT ?
        """,
        (MAX_MATCH_SCAN_ROWS,),
    ).fetchall()
    match_terms = build_match_terms(target)
    matched = 0
    for row in rows:
        text = " ".join(str(value or "") for value in row)
        if any(text_contains_term(text, term) for term in match_terms):
            matched += 1
    return matched


def query_matching_events(conn: sqlite3.Connection, target: DiscoveryTarget, limit: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT
            e.event_id,
            e.event_title,
            e.event_type,
            e.topic_key,
            e.primary_entity,
            e.primary_industry,
            e.novelty_state,
            e.event_state,
            e.last_seen_at,
            e.event_rank_score,
            group_concat(DISTINCT eel.entity_name) AS linked_entities
        FROM events e
        LEFT JOIN event_entity_links eel ON eel.event_id = e.event_id
        GROUP BY
            e.event_id,
            e.event_title,
            e.event_type,
            e.topic_key,
            e.primary_entity,
            e.primary_industry,
            e.novelty_state,
            e.event_state,
            e.last_seen_at,
            e.event_rank_score
        ORDER BY datetime(COALESCE(e.last_seen_at, e.first_seen_at)) DESC, e.event_rank_score DESC
        LIMIT ?
        """,
        (MAX_MATCH_SCAN_ROWS,),
    ).fetchall()
    match_terms = build_match_terms(target)
    matches: list[dict[str, Any]] = []
    for row in rows:
        payload = {
            "event_id": str(row[0]),
            "title": str(row[1] or ""),
            "event_type": str(row[2] or ""),
            "topic_key": str(row[3] or ""),
            "primary_entity": str(row[4] or ""),
            "primary_industry": str(row[5] or ""),
            "novelty_state": str(row[6] or ""),
            "event_state": str(row[7] or ""),
            "last_seen_at": str(row[8] or ""),
            "event_rank_score": float(row[9] or 0.0),
            "linked_entities": [item.strip() for item in str(row[10] or "").split(",") if item.strip()],
        }
        haystack = " ".join(
            [
                payload["title"],
                payload["topic_key"],
                payload["primary_entity"],
                payload["primary_industry"],
                *payload["linked_entities"],
            ]
        )
        if any(text_contains_term(haystack, term) for term in match_terms):
            matches.append(payload)
        if len(matches) >= limit:
            break
    return matches


def run_build_event_layer(db_path: Path, lookback_days: int) -> dict[str, Any]:
    command = [
        sys.executable,
        str(ROOT / "scripts" / "build_event_layer.py"),
        "--db",
        str(db_path),
        "--lookback-days",
        str(lookback_days),
    ]
    proc = subprocess.run(command, capture_output=True, text=True, check=True)
    return {"command": command, "stdout": proc.stdout.strip()}


def filter_source_ids(source_ids: list[str], args: argparse.Namespace, *, source_kind: str) -> list[str]:
    requested = {
        str(value).strip()
        for value in (getattr(args, "source_ids", None) or [])
        if str(value).strip()
    }
    filtered = [source_id for source_id in source_ids if not requested or source_id in requested]
    cap_name = "max_live_sources" if source_kind == "live" else "max_browser_sources"
    cap = int(getattr(args, cap_name, 0) or 0)
    if cap > 0:
        filtered = filtered[:cap]
    return filtered


def write_consumer_exports(output_root: Path, payloads: dict[str, dict[str, Any]], run_dt: datetime) -> list[str]:
    output_root.mkdir(parents=True, exist_ok=True)
    dated_root = output_root / "dated" / run_dt.strftime("%Y") / run_dt.strftime("%m") / run_dt.strftime("%d") / run_dt.strftime("%H%M%SZ")
    written: list[str] = []
    for name, payload in payloads.items():
        write_json(output_root / name, payload)
        write_json(dated_root / name, payload)
        written.append(name)
    return written


def resolve_research_profile(research_feed: dict[str, Any], target: DiscoveryTarget) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    query_index = research_feed.get("entity_query_index") or {}
    entity_profiles = research_feed.get("entity_profiles") or {}
    industry_profiles = research_feed.get("industry_profiles") or {}
    institution_profiles = research_feed.get("institution_profiles") or {}
    topic_profiles = research_feed.get("topic_profiles") or {}
    for term in build_match_terms(target):
        lookup = query_index.get(normalize_lookup_key(term))
        if not isinstance(lookup, dict):
            continue
        entity_type = str(lookup.get("entity_type") or "")
        entity_name = str(lookup.get("entity_name") or "")
        if entity_type == "company" and entity_name in entity_profiles:
            return lookup, entity_profiles[entity_name]
        if entity_type == "industry" and entity_name in industry_profiles:
            return lookup, industry_profiles[entity_name]
        if entity_type == "institution" and entity_name in institution_profiles:
            return lookup, institution_profiles[entity_name]
        if entity_type == "topic":
            topic_key = str(lookup.get("topic_key") or entity_name)
            if topic_key in topic_profiles:
                return lookup, topic_profiles[topic_key]
    return None, None


def fallback_matching_events(research_feed: dict[str, Any], target: DiscoveryTarget, limit: int) -> list[dict[str, Any]]:
    match_terms = build_match_terms(target)
    events: list[dict[str, Any]] = []
    for event in research_feed.get("recent_events") or []:
        text = " ".join(
            [
                str(event.get("title") or ""),
                str(event.get("primary_entity") or ""),
                str(event.get("topic_key") or ""),
            ]
        )
        if any(text_contains_term(text, term) for term in match_terms):
            events.append(event)
        if len(events) >= limit:
            break
    return events


def build_result_payload(
    args: argparse.Namespace,
    target: DiscoveryTarget,
    source_results: list[dict[str, Any]],
    coverage_before: dict[str, int],
    coverage_after: dict[str, int],
    build_result: dict[str, Any],
    payloads: dict[str, dict[str, Any]],
    matched_articles: list[dict[str, Any]],
    direct_events: list[dict[str, Any]],
    diagnostics: dict[str, Any],
) -> dict[str, Any]:
    research_feed = payloads["research_feed_latest.json"]
    lookup_hit, profile = resolve_research_profile(research_feed, target)
    if profile and str((lookup_hit or {}).get("entity_type") or "") in {"company", "industry", "institution"}:
        matched_events = list((profile.get("top_events") or [])[: args.event_limit])
        evidence_bundle = list((profile.get("evidence_bundle") or [])[: args.article_limit])
    elif profile:
        matched_events = list((profile.get("top_events") or [])[: args.event_limit])
        evidence_bundle = list((profile.get("evidence_bundle") or [])[: args.article_limit])
    else:
        matched_events = direct_events or fallback_matching_events(research_feed, target, args.event_limit)
        evidence_bundle = []
    return {
        "run_at": utc_now().isoformat(timespec="seconds"),
        "query": {
            "target_name": target.target_name,
            "company": target.target_name if target.route_key == "company" else "",
            "entity_type": target.entity_type,
            "route_key": target.route_key,
            "aliases": target.aliases,
            "ticker": target.ticker,
            "region": target.region,
            "search_terms": target.search_terms,
        },
        "routing": build_target_route(target),
        "diagnostics": diagnostics,
        "coverage_before": coverage_before,
        "coverage_after": coverage_after,
        "discovery": {
            "sources_run": len(source_results),
            "inserted_total": sum(int(item.get("inserted") or 0) for item in source_results),
            "updated_total": sum(int(item.get("updated") or 0) for item in source_results),
            "duplicate_total": sum(int(item.get("duplicate") or 0) for item in source_results),
            "matched_total": sum(int(item.get("matched_items") or 0) for item in source_results),
            "source_results": source_results,
        },
        "event_rebuild": build_result,
        "research": {
            "entity_lookup_hit": lookup_hit,
            "profile": profile,
            "events": matched_events,
            "evidence_bundle": evidence_bundle,
            "articles": matched_articles,
        },
    }


def run_discovery(args: argparse.Namespace) -> dict[str, Any]:
    total_started = time.monotonic()
    phase_timings: dict[str, float] = {}

    def mark_phase(name: str, started: float) -> None:
        phase_timings[name] = round(time.monotonic() - started, 3)

    run_dt = utc_now()
    original_request_timeout = live_news_collector.REQUEST_TIMEOUT
    used_request_timeout = max(int(getattr(args, "request_timeout_seconds", original_request_timeout) or original_request_timeout), 1)
    live_news_collector.REQUEST_TIMEOUT = used_request_timeout
    target_name = str(args.target_name or args.company or "").strip()
    target = build_target(
        target_name,
        args.aliases,
        args.ticker,
        args.region,
        entity_type=args.entity_type,
        route_key=args.route_key,
        extra_search_terms=args.search_terms,
    )
    registry = load_registry(args.registry)
    live_catalog = load_catalog_map(args.catalog)
    browser_catalog = load_catalog_map(args.browser_catalog)
    live_source_ids, browser_source_ids = source_ids_for_target(target)
    routed_live_source_ids = list(live_source_ids)
    routed_browser_source_ids = list(browser_source_ids)
    live_source_ids = filter_source_ids(live_source_ids, args, source_kind="live")
    browser_source_ids = filter_source_ids(browser_source_ids, args, source_kind="browser")

    phase_started = time.monotonic()
    conn = sqlite3.connect(args.db, timeout=5.0)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    ensure_bootstrap(conn, args.schema, registry)
    conn.commit()
    mark_phase("bootstrap", phase_started)
    phase_started = time.monotonic()
    coverage_before = {
        "matching_articles": len(query_matching_articles(conn, target, args.article_limit)),
        "matching_events": count_matching_events(conn, target),
    }
    mark_phase("coverage_before", phase_started)

    results: list[dict[str, Any]] = []
    session = requests.Session()
    try:
        phase_started = time.monotonic()
        for source_id in live_source_ids:
            if source_id not in registry or source_id not in live_catalog:
                continue
            source = configure_source(build_source(source_id, registry, live_catalog), target, args)
            results.append(run_live_discovery_source(conn, session, source, target, run_dt))
        mark_phase("live_sources", phase_started)
        phase_started = time.monotonic()
        for source_id in browser_source_ids:
            if source_id not in registry or source_id not in browser_catalog:
                continue
            source = configure_source(build_source(source_id, registry, browser_catalog), target, args)
            results.append(run_browser_discovery_source(conn, source, target, run_dt, args.storage_state_path))
        mark_phase("browser_sources", phase_started)
    finally:
        session.close()
        conn.close()
        live_news_collector.REQUEST_TIMEOUT = original_request_timeout

    phase_started = time.monotonic()
    if bool(getattr(args, "skip_event_rebuild", False)):
        build_result = {"status": "skipped", "reason": "skip_event_rebuild=true", "command": [], "stdout": ""}
    else:
        build_result = run_build_event_layer(args.db, args.rebuild_lookback_days)
    mark_phase("event_rebuild", phase_started)
    phase_started = time.monotonic()
    with sqlite3.connect(args.db) as export_conn:
        export_conn.row_factory = sqlite3.Row
        payloads = build_exports(
            export_conn,
            run_dt=run_dt,
            lookback_hours=args.export_lookback_hours,
            opportunity_limit=40,
            radar_per_industry_limit=5,
            research_limit=args.research_limit,
        )
        matched_articles = query_matching_articles(export_conn, target, args.article_limit)
        matched_events = query_matching_events(export_conn, target, args.event_limit)
        coverage_after = {
            "matching_articles": len(matched_articles),
            "matching_events": count_matching_events(export_conn, target),
        }
    mark_phase("export_build", phase_started)
    phase_started = time.monotonic()
    written_exports: list[str] = []
    if not bool(getattr(args, "skip_consumer_export", False)):
        written_exports = write_consumer_exports(args.consumer_export_root, payloads, run_dt)
    mark_phase("consumer_export_write", phase_started)
    diagnostics = {
        "request_timeout_seconds": used_request_timeout,
        "skip_event_rebuild": bool(getattr(args, "skip_event_rebuild", False)),
        "skip_consumer_export": bool(getattr(args, "skip_consumer_export", False)),
        "routed_live_source_ids": routed_live_source_ids,
        "routed_browser_source_ids": routed_browser_source_ids,
        "selected_live_source_ids": live_source_ids,
        "selected_browser_source_ids": browser_source_ids,
        "written_exports": written_exports,
        "phase_timings_seconds": phase_timings,
        "total_elapsed_seconds": round(time.monotonic() - total_started, 3),
    }
    return build_result_payload(args, target, results, coverage_before, coverage_after, build_result, payloads, matched_articles, matched_events, diagnostics)


def default_output_path(output_dir: Path, target: DiscoveryTarget, run_dt: datetime) -> Path:
    slug = normalize_lookup_key(target.target_name) or target.route_key or "target"
    return output_dir / f"{run_dt.strftime('%Y%m%dT%H%M%SZ')}_{slug}.json"


def main() -> None:
    args = parse_args()
    result = run_discovery(args)
    target_name = str(args.target_name or args.company or "").strip()
    target = build_target(
        target_name,
        args.aliases,
        args.ticker,
        args.region,
        entity_type=args.entity_type,
        route_key=args.route_key,
        extra_search_terms=args.search_terms,
    )
    run_dt = datetime.fromisoformat(str(result["run_at"]))
    output_path = args.output_file or default_output_path(args.output_dir, target, run_dt.astimezone(timezone.utc))
    write_json(output_path, result)
    print(json.dumps({"output_file": str(output_path), **result}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
