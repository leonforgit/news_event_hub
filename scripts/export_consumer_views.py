#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
import re

from discovery_routing import build_entity_discovery_routes, build_feed_discovery_contract
from build_event_layer import canonical_company_id, canonicalize_entity_name, looks_like_company_entity, trim_company_candidate


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = ROOT / "state" / "news_event.db"
DEFAULT_OUTPUT_ROOT = ROOT / "state" / "consumer_exports"
ENTITY_ALIAS_PATH = ROOT / "data" / "entity_aliases_v1.csv"
WATCHLIST_REGISTRY_PATH = Path.home() / ".codex" / "state" / "investment" / "watchlist" / "watchlist_registry.csv"
CONSUMER_EXPORT_POLICY_PATH = ROOT / "config" / "consumer_export_policy_v1.json"
ADAPTER_VERSION = "consumer_views_v1"
SQLITE_BUSY_TIMEOUT_MS = 600000

MACRO_EVENT_TYPES = {"macro_data", "policy", "commodity_disruption", "regulation"}
RESEARCH_CHINESE_COMPANY_SUFFIX_RE = re.compile(r"(公司|集团|股份|控股|银行|证券|药业|制药|科技|电子|半导体|能源|汽车|航空|物流|矿业|保险|电力|通信|传媒|工业|机械|材料|医药)$")
RESEARCH_CHINESE_BAD_FRAGMENT_RE = re.compile(
    r"(分析师|负责人|高管|报告|供应|中断|风险|警告|显示|指出|项目|组织|交易中心|盘后|专栏|风口研报|子公司|实控人|本公司|食品价格|全球|"
    r"需求|格局|方案|产业|领域|应用|逻辑|赛道|主线|趋势|风口|解读|精选|盘点|路线图|图谱|机会|问题|事件|关键技术|技术研发|押注|题材|方向|"
    r"控股股东|第二大股东|工业协会|金管局|能源部|台办|市委书记|书记|论坛|委员会|协会|政府|监管局)",
    re.IGNORECASE,
)
RESEARCH_CHINESE_NONCOMPANY_RE = re.compile(
    r"(部|局|台办|协会|委员会|论坛|书记|市委|政府|金管局|能源部|股东)",
    re.IGNORECASE,
)
RESEARCH_LATIN_MULTIWORD_RE = re.compile(r"^[A-Z][A-Za-z0-9&\.\-]{1,24}(?:\s+[A-Z][A-Za-z0-9&\.\-]{1,24})+$")
RESEARCH_LATIN_CORP_SUFFIX_RE = re.compile(r"\b(Inc|Corp|Corporation|Group|Bank|AG|REIT|Pharma|Pharmaceuticals|Aerospace|Systems|Technologies|Therapeutics|Energy|Holdings)\b", re.IGNORECASE)
RESEARCH_LATIN_NONCOMPANY_RE = re.compile(r"\b(Foundation|Association|University|College|Museum|Summit|Expo|Festival|Commission|Institute)\b", re.IGNORECASE)
RESEARCH_COMPANY_EVENT_HINT_RE = re.compile(
    r"(investor call|earnings|results|guidance|shares|stock|acquisition|acquire|merger|deal|agreement|contract|order|capacity|production|launch|funding|offering|buyback|dividend|"
    r"投资者|业绩|预告|回购|分红|收购|并购|合同|订单|扩产|减持|增持|融资|发债|获批|批准|中标|签署)",
    re.IGNORECASE,
)
RESEARCH_ENTERTAINMENT_NOISE_RE = re.compile(
    r"(headline|opening night|party|expo|festival|tour|concert|album|licensing expo|entertainment|music|las vegas)",
    re.IGNORECASE,
)
RESEARCH_INSTITUTIONAL_EVENT_NOISE_RE = re.compile(
    r"(协会|安全局|能源部|金管局|台办|市委|论坛|会议|会见|审计机构|监管机构|交易所|工业会)",
    re.IGNORECASE,
)
RESEARCH_GENERIC_SECTOR_ENTITY_RE = re.compile(
    r"(工业|航空|能源)$",
    re.IGNORECASE,
)
RESEARCH_GENERIC_SECTOR_EVENT_NOISE_RE = re.compile(
    r"(燃油|短缺|行业|产能治理|供需|监管|空域|公告有效期|恢复输送能力)",
    re.IGNORECASE,
)
NUMBER_RE = re.compile(r"\d")
OFFICIAL_SOURCE_PREFIXES = ("sec_", "cninfo_", "hkex_", "fed_", "gov_")
TICKER_SUFFIX_REGION_MAP = {
    "HK": "HK",
    "SH": "CN",
    "SZ": "CN",
    "BJ": "CN",
    "US": "US",
}
DEFAULT_CONSUMER_EXPORT_POLICY: dict[str, Any] = {
    "version": "consumer_export_policy_v1",
    "default_research_limit": 0,
    "persistent_event_lookback_hours": 24 * 14,
    "persistent_event_state": "mature",
    "persistent_event_min_event_rank_score": 60,
    "persistent_event_min_article_count": 3,
    "persistent_event_min_independent_evidence_count": 2,
    "persistent_event_min_signal_platform_count": 1,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export Layer 3 consumer views from the shared news event database.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--run-at", default=None, help="ISO 8601 timestamp override.")
    parser.add_argument("--lookback-hours", type=int, default=72)
    parser.add_argument("--opportunity-limit", type=int, default=40)
    parser.add_argument("--radar-per-industry-limit", type=int, default=5)
    parser.add_argument("--research-limit", type=int, default=RESEARCH_EVENT_LIMIT)
    parser.add_argument(
        "--no-dated-copy",
        action="store_true",
        help="Only write latest consumer views. Use for frequent online exports to avoid large dated JSON accumulation.",
    )
    return parser.parse_args()


def parse_run_dt(raw: str | None) -> datetime:
    if not raw:
        return datetime.now(timezone.utc)
    parsed = datetime.fromisoformat(raw)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def open_db(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path, timeout=SQLITE_BUSY_TIMEOUT_MS / 1000)
    conn.execute(f"PRAGMA busy_timeout = {SQLITE_BUSY_TIMEOUT_MS}")
    conn.row_factory = sqlite3.Row
    return conn


def load_json_value(raw: str | None, fallback: Any) -> Any:
    if not raw:
        return fallback
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return fallback


def load_consumer_export_policy() -> dict[str, Any]:
    if not CONSUMER_EXPORT_POLICY_PATH.exists():
        return dict(DEFAULT_CONSUMER_EXPORT_POLICY)
    try:
        loaded = json.loads(CONSUMER_EXPORT_POLICY_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return dict(DEFAULT_CONSUMER_EXPORT_POLICY)
    if not isinstance(loaded, dict):
        return dict(DEFAULT_CONSUMER_EXPORT_POLICY)
    return {
        **DEFAULT_CONSUMER_EXPORT_POLICY,
        **loaded,
    }


CONSUMER_EXPORT_POLICY = load_consumer_export_policy()
RESEARCH_EVENT_LIMIT = int(CONSUMER_EXPORT_POLICY.get("default_research_limit") or 0)
PERSISTENT_EVENT_LOOKBACK_HOURS = int(CONSUMER_EXPORT_POLICY.get("persistent_event_lookback_hours") or DEFAULT_CONSUMER_EXPORT_POLICY["persistent_event_lookback_hours"])


def normalize_lookup_key(value: str | None) -> str:
    text = str(value or "").strip().lower()
    return re.sub(r"[\s\-_/:\\()（）【】\[\]，。,.;；'\"`]+", "", text)


def load_entity_alias_map() -> dict[str, dict[str, list[str]]]:
    result: dict[str, dict[str, list[str]]] = defaultdict(dict)
    if not ENTITY_ALIAS_PATH.exists():
        return result
    grouped: dict[tuple[str, str], set[str]] = defaultdict(set)
    with ENTITY_ALIAS_PATH.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            entity_type = str(row.get("entity_type") or "").strip()
            canonical_id = str(row.get("canonical_id") or "").strip()
            canonical_name = str(row.get("canonical_name") or "").strip()
            alias = str(row.get("alias") or "").strip()
            if not entity_type or not canonical_id:
                continue
            if canonical_name:
                grouped[(entity_type, canonical_id)].add(canonical_name)
            if alias:
                grouped[(entity_type, canonical_id)].add(alias)
    for (entity_type, canonical_id), aliases in grouped.items():
        result[entity_type][canonical_id] = sorted(aliases)
    return result


def infer_region_from_ticker(ticker: str) -> str:
    clean = str(ticker or "").strip().upper()
    if not clean:
        return ""
    if "." not in clean and re.fullmatch(r"[A-Z]{1,6}", clean):
        return "US"
    suffix = clean.rsplit(".", 1)[-1]
    return TICKER_SUFFIX_REGION_MAP.get(suffix, "")


def load_company_metadata_map() -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    if not WATCHLIST_REGISTRY_PATH.exists():
        return result
    with WATCHLIST_REGISTRY_PATH.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            status = str(row.get("status") or "active").strip().lower()
            if status and status not in {"active", "holding", "watch", "tracked"}:
                continue
            name = str(row.get("name") or "").strip()
            ticker = str(row.get("ticker") or "").strip().upper()
            if not name:
                continue
            metadata = {
                "ticker": ticker,
                "region": infer_region_from_ticker(ticker),
            }
            for candidate in (name, ticker, ticker.split(".", 1)[0] if ticker else ""):
                key = normalize_lookup_key(candidate)
                if key:
                    result[key] = metadata
    return result


def resolve_company_profile_metadata(
    entity_name: str,
    entity_id: str,
    aliases: list[str],
    metadata_map: dict[str, dict[str, str]],
) -> dict[str, str]:
    for candidate in [entity_name, entity_id, *aliases]:
        key = normalize_lookup_key(candidate)
        if key and key in metadata_map:
            return dict(metadata_map[key])
    inferred_region = "CN" if any(re.search(r"[\u4e00-\u9fff]", item or "") for item in [entity_name, *aliases]) else ""
    return {"ticker": "", "region": inferred_region}


def is_researchable_company_name(entity_name: str, aliases: list[str]) -> bool:
    clean = canonicalize_entity_name(trim_company_candidate(entity_name)) or ""
    if not clean:
        return False
    if aliases:
        return True
    if clean in {"资管公司"}:
        return False
    if clean.startswith(("又一", "批复同意")):
        return False
    if RESEARCH_LATIN_NONCOMPANY_RE.search(clean):
        return False
    if re.search(r"[：:，,。！？“”\"']", clean):
        return False
    if re.search(r"[\u4e00-\u9fff]", clean):
        if RESEARCH_CHINESE_BAD_FRAGMENT_RE.search(clean):
            return False
        if RESEARCH_CHINESE_NONCOMPANY_RE.search(clean):
            return False
        if len(clean) <= 6 and RESEARCH_CHINESE_BAD_FRAGMENT_RE.search(clean) is None:
            return True
        if RESEARCH_CHINESE_COMPANY_SUFFIX_RE.search(clean) and RESEARCH_CHINESE_BAD_FRAGMENT_RE.search(clean) is None and len(clean) <= 20:
            return True
        return False
    if RESEARCH_LATIN_MULTIWORD_RE.match(clean):
        return True
    if RESEARCH_LATIN_CORP_SUFFIX_RE.search(clean):
        return True
    return bool(re.search(r"[a-z][A-Z]|[A-Z]{2,}", clean))


def is_researchable_company_profile(entity_name: str, aliases: list[str], entity_events: list[dict[str, Any]]) -> bool:
    if not is_researchable_company_name(entity_name, aliases):
        return False
    if aliases:
        return True
    strong_event = False
    for event in entity_events:
        event_type = str(event.get("event_type") or "")
        title = str(event.get("event_title") or "")
        researchability = score_vector_value(event, "researchability")
        entity_impact = score_vector_value(event, "entity_impact")
        if RESEARCH_ENTERTAINMENT_NOISE_RE.search(title):
            continue
        if RESEARCH_INSTITUTIONAL_EVENT_NOISE_RE.search(title):
            continue
        if RESEARCH_GENERIC_SECTOR_ENTITY_RE.search(entity_name) and RESEARCH_GENERIC_SECTOR_EVENT_NOISE_RE.search(title):
            continue
        if event_type in {"deal_mna", "production_supply", "contract_order", "earnings_guidance", "company_action", "financing_capital", "regulation"}:
            strong_event = True
            break
        if RESEARCH_COMPANY_EVENT_HINT_RE.search(title) and (researchability >= 0.45 or entity_impact >= 0.55):
            strong_event = True
            break
        if researchability >= 0.72 and entity_impact >= 0.72:
            strong_event = True
            break
    return strong_event


def fetch_recent_events(conn: sqlite3.Connection, cutoff_iso: str, persistent_cutoff_iso: str, limit: int | None) -> list[sqlite3.Row]:
    persistent_state = str(CONSUMER_EXPORT_POLICY.get("persistent_event_state") or "mature")
    min_event_rank_score = float(CONSUMER_EXPORT_POLICY.get("persistent_event_min_event_rank_score") or 0.0)
    min_article_count = int(CONSUMER_EXPORT_POLICY.get("persistent_event_min_article_count") or 0)
    min_independent_evidence_count = int(CONSUMER_EXPORT_POLICY.get("persistent_event_min_independent_evidence_count") or 0)
    min_signal_platform_count = int(CONSUMER_EXPORT_POLICY.get("persistent_event_min_signal_platform_count") or 0)
    query = """
        SELECT
            event_id,
            event_title,
            event_type,
            topic_key,
            event_state,
            first_seen_at,
            last_seen_at,
            novelty_state,
            confirmation_count,
            source_mix,
            score_vector,
            calibrated_confirmation,
            uncertainty,
            article_count_raw,
            independent_evidence_count,
            source_family_count,
            signal_platform_count,
            primary_industry,
            primary_entity,
            event_rank_score,
            event_rank_flags,
            opportunity_state
        FROM events
        WHERE COALESCE(opportunity_state, 'unreviewed') != 'rejected'
          AND (
              datetime(last_seen_at) >= datetime(?)
              OR (
                  event_state = ?
                  AND datetime(last_seen_at) >= datetime(?)
                  AND (
                      COALESCE(event_rank_score, 0) >= ?
                      OR COALESCE(article_count_raw, 0) >= ?
                      OR COALESCE(independent_evidence_count, 0) >= ?
                      OR COALESCE(signal_platform_count, 0) >= ?
                  )
              )
          )
        ORDER BY event_rank_score DESC, datetime(last_seen_at) DESC, event_id DESC
        """
    params: tuple[Any, ...]
    if limit is None:
        params = (
            cutoff_iso,
            persistent_state,
            persistent_cutoff_iso,
            min_event_rank_score,
            min_article_count,
            min_independent_evidence_count,
            min_signal_platform_count,
        )
    else:
        query += "\n        LIMIT ?"
        params = (
            cutoff_iso,
            persistent_state,
            persistent_cutoff_iso,
            min_event_rank_score,
            min_article_count,
            min_independent_evidence_count,
            min_signal_platform_count,
            limit,
        )
    rows = conn.execute(query, params).fetchall()
    return list(rows)


def fetch_entities(conn: sqlite3.Connection, event_ids: list[str]) -> dict[str, list[dict[str, Any]]]:
    if not event_ids:
        return {}
    placeholders = ",".join("?" for _ in event_ids)
    rows = conn.execute(
        f"""
        SELECT event_id, entity_type, entity_id, entity_name, relevance_score, mapping_reason, mapping_confidence, mapping_version, mapping_source
        FROM event_entity_links
        WHERE event_id IN ({placeholders})
        ORDER BY relevance_score DESC, entity_name ASC
        """,
        event_ids,
    ).fetchall()
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["event_id"])].append(
            {
                "entity_type": str(row["entity_type"]),
                "entity_id": str(row["entity_id"]),
                "entity_name": str(row["entity_name"]),
                "relevance_score": float(row["relevance_score"] or 0.0),
                "mapping_reason": str(row["mapping_reason"] or ""),
                "mapping_confidence": float(row["mapping_confidence"] or 0.0),
                "mapping_version": str(row["mapping_version"] or ""),
                "mapping_source": str(row["mapping_source"] or ""),
            }
        )
    return grouped


def fetch_supporting_articles(conn: sqlite3.Connection, event_ids: list[str]) -> dict[str, list[dict[str, Any]]]:
    if not event_ids:
        return {}
    placeholders = ",".join("?" for _ in event_ids)
    rows = conn.execute(
        f"""
        SELECT
            ael.event_id,
            ael.link_type,
            a.article_id,
            a.title,
            a.canonical_url,
            a.published_at,
            a.collected_at,
            a.source_id,
            sr.name AS source_name,
            COALESCE(sr.source_family, '') AS source_family,
            COALESCE(sr.lane, '') AS lane,
            COALESCE(sr.trust_tier, 3) AS trust_tier
        FROM article_event_links ael
        JOIN news_articles a ON ael.article_id = a.article_id
        LEFT JOIN source_registry sr ON a.source_id = sr.source_id
        WHERE ael.event_id IN ({placeholders})
        ORDER BY datetime(COALESCE(a.published_at, a.collected_at, a.created_at)) DESC, a.article_id DESC
        """,
        event_ids,
    ).fetchall()
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        event_id = str(row["event_id"])
        grouped[event_id].append(
            {
                "link_type": str(row["link_type"] or ""),
                "article_id": str(row["article_id"]),
                "title": str(row["title"]),
                "canonical_url": str(row["canonical_url"] or ""),
                "published_at": str(row["published_at"] or ""),
                "collected_at": str(row["collected_at"] or ""),
                "source_id": str(row["source_id"]),
                "source_name": str(row["source_name"] or row["source_id"]),
                "source_family": str(row["source_family"] or ""),
                "lane": str(row["lane"] or ""),
                "trust_tier": int(row["trust_tier"] or 3),
            }
        )
    return grouped


def parse_dt(value: str) -> datetime:
    if not value:
        return datetime.fromtimestamp(0, tz=timezone.utc)
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return datetime.fromtimestamp(0, tz=timezone.utc)


def is_official_evidence(article: dict[str, Any]) -> bool:
    source_id = str(article.get("source_id") or "")
    family = str(article.get("source_family") or "")
    if source_id.startswith(OFFICIAL_SOURCE_PREFIXES):
        return True
    return family.startswith("exchange:") or family.startswith("official:")


def is_originalish_source(article: dict[str, Any]) -> bool:
    family = str(article.get("source_family") or "")
    if family.startswith(("exchange:", "wire:", "api:", "official:")):
        return True
    return int(article.get("trust_tier") or 3) <= 1


def evidence_specificity(article: dict[str, Any]) -> float:
    title = str(article.get("title") or "")
    score = 0.2
    if NUMBER_RE.search(title):
        score += 0.3
    if len(title) >= 18:
        score += 0.2
    if any(token in title for token in ("公告", "签署", "获批", "订单", "回购", "并购", "增持", "减持", "临床", "合同", "扩产")):
        score += 0.2
    if article.get("canonical_url"):
        score += 0.1
    return min(score, 1.0)


def order_supporting_articles(articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    published_by_article = {
        str(article.get("article_id") or ""): parse_dt(str(article.get("published_at") or article.get("collected_at") or ""))
        for article in articles
    }
    timestamps = [dt.timestamp() for dt in published_by_article.values()]
    max_ts = max(timestamps, default=0.0)
    min_ts = min(timestamps, default=0.0)

    def freshness_score(article: dict[str, Any]) -> float:
        article_id = str(article.get("article_id") or "")
        published = published_by_article.get(article_id, datetime.fromtimestamp(0, tz=timezone.utc))
        ts = published.timestamp()
        if max_ts <= min_ts:
            return 1.0 if max_ts > 0 else 0.0
        return max(min((ts - min_ts) / (max_ts - min_ts), 1.0), 0.0)

    def base_key(article: dict[str, Any]) -> tuple[float, ...]:
        published = published_by_article.get(
            str(article.get("article_id") or ""),
            datetime.fromtimestamp(0, tz=timezone.utc),
        )
        return (
            1.0 if is_official_evidence(article) else 0.0,
            1.0 if str(article.get("link_type") or "") == "primary" else 0.0,
            1.0 if is_originalish_source(article) else 0.0,
            evidence_specificity(article),
            freshness_score(article),
            published.timestamp(),
        )

    sorted_articles = sorted(articles, key=base_key, reverse=True)
    unique_first: list[dict[str, Any]] = []
    repeats: list[dict[str, Any]] = []
    seen_families: set[str] = set()
    for article in sorted_articles:
        family = str(article.get("source_family") or article.get("source_id") or "")
        ordered = dict(article)
        freshness = freshness_score(article)
        reasons: list[str] = []
        if is_official_evidence(article):
            reasons.append("official_direct")
        if str(article.get("link_type") or "") == "primary":
            reasons.append("primary_link")
        if is_originalish_source(article):
            reasons.append("original_source")
        if evidence_specificity(article) >= 0.6:
            reasons.append("high_specificity")
        if family not in seen_families and freshness >= 0.7:
            reasons.append("newest_nonredundant_update")
        elif family in seen_families:
            reasons.append("same_family_repeat")
        else:
            reasons.append("unique_family_support")
        ordered["evidence_rank_score"] = round(
            100.0
            * (
                0.30 * (1.0 if is_official_evidence(article) else 0.0)
                + 0.20 * (1.0 if str(article.get("link_type") or "") == "primary" else 0.0)
                + 0.15 * (1.0 if is_originalish_source(article) else 0.0)
                + 0.20 * evidence_specificity(article)
                + 0.15 * freshness
            ),
            3,
        )
        ordered["evidence_rank_reason"] = "|".join(reasons)
        if family and family not in seen_families:
            seen_families.add(family)
            unique_first.append(ordered)
        else:
            repeats.append(ordered)
    return unique_first + repeats


def hydrate_events(
    rows: list[sqlite3.Row],
    entity_map: dict[str, list[dict[str, Any]]],
    article_map: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    hydrated: list[dict[str, Any]] = []
    for row in rows:
        event_id = str(row["event_id"])
        entities = entity_map.get(event_id, [])
        articles = order_supporting_articles(article_map.get(event_id, []))
        grouped_entities: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for entity in entities:
            grouped_entities[entity["entity_type"]].append(entity)
        source_mix = load_json_value(str(row["source_mix"] or ""), {})
        score_vector = load_json_value(str(row["score_vector"] or ""), {})
        rank_flags = load_json_value(str(row["event_rank_flags"] or ""), {})
        source_mix = source_mix if isinstance(source_mix, dict) else {}
        score_vector = score_vector if isinstance(score_vector, dict) else {}
        rank_flags = rank_flags if isinstance(rank_flags, dict) else {}
        hydrated.append(
            {
                "event_id": event_id,
                "event_title": str(row["event_title"]),
                "event_type": str(row["event_type"]),
                "topic_key": str(row["topic_key"] or ""),
                "event_state": str(row["event_state"] or "emerging"),
                "first_seen_at": str(row["first_seen_at"]),
                "last_seen_at": str(row["last_seen_at"]),
                "novelty_state": str(row["novelty_state"]),
                "confirmation_count": int(row["confirmation_count"] or 0),
                "calibrated_confirmation": float(row["calibrated_confirmation"] or 0.0),
                "uncertainty": float(row["uncertainty"] or 0.0),
                "event_rank_score": float(row["event_rank_score"] or 0.0),
                "event_state_reason": str(rank_flags.get("event_state_reason") or ""),
                "primary_industry": str(row["primary_industry"] or ""),
                "primary_entity": str(row["primary_entity"] or ""),
                "opportunity_state": str(row["opportunity_state"] or "unreviewed"),
                "source_mix": source_mix,
                "score_vector": score_vector,
                "article_count_raw": int(row["article_count_raw"] or 0),
                "independent_evidence_count": int(row["independent_evidence_count"] or 0),
                "source_family_count": int(row["source_family_count"] or 0),
                "signal_platform_count": int(row["signal_platform_count"] or 0),
                "update_count": int(rank_flags.get("update_count") or 0),
                "latest_update_signature": str(rank_flags.get("latest_update_signature") or ""),
                "recent_updates": list(rank_flags.get("recent_updates") or []),
                "event_rank_flags": rank_flags,
                "entities": entities,
                "entities_by_type": grouped_entities,
                "supporting_articles": articles[:5],
                "source_count": len({article["source_id"] for article in articles if article.get("source_id")}),
            }
        )
    return hydrated


def event_brief(event: dict[str, Any], *, include_supporting_articles: bool = True) -> dict[str, Any]:
    industries = [item["entity_name"] for item in event["entities_by_type"].get("industry", [])]
    companies = [item["entity_name"] for item in event["entities_by_type"].get("company", [])]
    themes = [item["entity_name"] for item in event["entities_by_type"].get("theme", [])]
    macro_themes = [item["entity_name"] for item in event["entities_by_type"].get("macro_theme", [])]
    opportunity = derive_opportunity_candidate(event)
    flags_bucket = (event.get("event_rank_flags") or {}).get("flags") if isinstance(event.get("event_rank_flags"), dict) else {}
    brief = {
        "event_id": event["event_id"],
        "title": event["event_title"],
        "event_type": event["event_type"],
        "topic_key": event["topic_key"],
        "event_state": event["event_state"],
        "event_state_reason": event.get("event_state_reason") or "",
        "granularity_class": derive_export_granularity_class(event),
        "score": round(float(event["event_rank_score"]), 3),
        "global_rank_score": round(float(event["event_rank_score"]), 3),
        "novelty_state": event["novelty_state"],
        "confirmation_count": int(event["confirmation_count"]),
        "calibrated_confirmation": round(float(event.get("calibrated_confirmation") or 0.0), 3),
        "uncertainty": round(float(event.get("uncertainty") or 0.0), 3),
        "source_count": int(event["source_count"]),
        "article_count_raw": int(event.get("article_count_raw") or 0),
        "independent_evidence_count": int(event.get("independent_evidence_count") or 0),
        "source_family_count": int(event.get("source_family_count") or 0),
        "signal_platform_count": int(event.get("signal_platform_count") or 0),
        "update_count": int(event.get("update_count") or 0),
        "latest_update_signature": str(event.get("latest_update_signature") or ""),
        "recent_updates": list(event.get("recent_updates") or [])[:3],
        "primary_industry": event["primary_industry"],
        "primary_entity": event["primary_entity"],
        "industries": industries,
        "companies": companies,
        "themes": themes,
        "macro_themes": macro_themes,
        "first_seen_at": event["first_seen_at"],
        "last_seen_at": event["last_seen_at"],
        "source_mix": event["source_mix"],
        "score_vector": event.get("score_vector") or {},
        "entities_by_type": event.get("entities_by_type") or {},
        "opportunity_type": opportunity["opportunity_type"],
        "opportunity_bucket": opportunity["opportunity_bucket"],
        "portfolio_relevance": opportunity["portfolio_relevance"],
        "watchlist_relevance": opportunity["watchlist_relevance"],
        "thesis_impact": opportunity["thesis_impact"],
        "followup_path": opportunity["followup_path"],
    }
    if include_supporting_articles:
        brief["supporting_articles"] = event["supporting_articles"][:3]
    return brief


def score_vector_value(event: dict[str, Any], key: str, default: float = 0.0) -> float:
    try:
        return float((event.get("score_vector") or {}).get(key, default) or default)
    except (TypeError, ValueError):
        return default


def build_global_feed_contract() -> dict[str, Any]:
    return {
        "view": "global_feed",
        "primary_rank_field": "event_rank_score",
        "primary_objective": "today_market_priority",
        "preferred_axes": [
            "market_significance",
            "confirmation",
            "novelty",
            "researchability",
        ],
        "notes": [
            "signal-only events are mixed in with a limited quota",
            "global feed favors shared market significance over entity-local recall",
        ],
    }


def compute_research_rank(event: dict[str, Any]) -> tuple[float, str]:
    entity_local_priority = score_vector_value(event, "entity_local_priority", score_vector_value(event, "entity_impact"))
    entity_impact = score_vector_value(event, "entity_impact")
    researchability = score_vector_value(event, "researchability")
    novelty = score_vector_value(event, "novelty")
    coverage_independent = score_vector_value(event, "coverage_independent")
    confirmation = float(event.get("calibrated_confirmation") or 0.0)
    uncertainty = float(event.get("uncertainty") or 0.0)
    state = str(event.get("event_state") or "")
    has_company = bool(event["entities_by_type"].get("company")) or bool(str(event.get("primary_entity") or "").strip())
    has_industry = bool(event["entities_by_type"].get("industry")) or bool(str(event.get("primary_industry") or "").strip())
    signal_only = bool((event.get("source_mix") or {}).get("signal")) and not bool((event.get("source_mix") or {}).get("confirmation"))

    entity_focus = 1.0 if has_company else (0.8 if has_industry else 0.45)
    local_impact_bonus = 0.08 if has_company and entity_impact >= 0.78 else 0.0
    undercovered_bonus = 0.06 if has_company and int(event.get("independent_evidence_count") or 0) <= 2 else 0.0
    state_bonus = {
        "confirmed": 0.12,
        "emerging": 0.08,
        "watch": 0.02,
        "contested": 0.04,
        "mature": -0.06,
        "closed": -0.10,
    }.get(state, 0.0)
    signal_penalty = 0.05 if signal_only else 0.0

    score = 100.0 * (
        0.24 * entity_impact
        + 0.08 * entity_local_priority
        + 0.22 * researchability
        + 0.16 * entity_focus
        + 0.12 * novelty
        + 0.12 * coverage_independent
        + 0.12 * confirmation
        + local_impact_bonus
        + undercovered_bonus
        + state_bonus
        - 0.10 * uncertainty
        - signal_penalty
    )

    if has_company and entity_impact >= 0.78:
        reason = "entity_local_priority"
    elif has_company:
        reason = "company_research_recall"
    elif has_industry:
        reason = "industry_research_recall"
    elif signal_only:
        reason = "signal_watchlist_support"
    else:
        reason = "broad_research_context"
    return round(min(max(score, 0.0), 100.0), 4), reason


def build_research_contract() -> dict[str, Any]:
    return {
        "view": "research_retrieval",
        "primary_rank_field": "research_rank_score",
        "primary_objective": "entity_recall_and_precision",
        "preferred_axes": [
            "entity_local_priority",
            "entity_impact",
            "researchability",
            "novelty",
            "coverage_independent",
            "calibrated_confirmation",
        ],
        "notes": [
            "research retrieval is ranked independently from the global shared feed",
            "entity-local importance is allowed to outrank broad market significance",
        ],
    }


def rank_research_evidence_bundle(events: list[dict[str, Any]], limit: int = 12) -> list[dict[str, Any]]:
    ranked: list[tuple[tuple[float, ...], dict[str, Any]]] = []
    seen_article_ids: set[str] = set()
    for event in events:
        event_score = float(event.get("research_rank_score") or 0.0)
        event_title = str(event.get("event_title") or "")
        event_id = str(event.get("event_id") or "")
        event_state = str(event.get("event_state") or "")
        for article in event.get("supporting_articles") or []:
            if not isinstance(article, dict):
                continue
            article_id = str(article.get("article_id") or "")
            if not article_id or article_id in seen_article_ids:
                continue
            seen_article_ids.add(article_id)
            evidence_score = float(article.get("evidence_rank_score") or 0.0)
            published = parse_dt(str(article.get("published_at") or article.get("collected_at") or ""))
            enriched = dict(article)
            enriched["event_id"] = event_id
            enriched["event_title"] = event_title
            enriched["event_state"] = event_state
            ranked.append(
                (
                    (
                        event_score,
                        evidence_score,
                        published.timestamp(),
                    ),
                    enriched,
                )
            )
    ranked.sort(key=lambda item: item[0], reverse=True)
    return [item[1] for item in ranked[:limit]]


def event_brief_with_research(event: dict[str, Any]) -> dict[str, Any]:
    brief = event_brief(event)
    brief["research_rank_score"] = round(float(event.get("research_rank_score") or 0.0), 3)
    brief["research_rank_reason"] = str(event.get("research_rank_reason") or "")
    return brief


def build_profile_timeline(events: list[dict[str, Any]], limit: int = 12) -> list[dict[str, Any]]:
    ranked = sorted(
        events,
        key=lambda item: (
            str(item.get("last_seen_at") or ""),
            float(item.get("research_rank_score") or 0.0),
            float(item.get("event_rank_score") or 0.0),
        ),
        reverse=True,
    )
    return [event_brief_with_research(event) for event in ranked[:limit]]


def rank_events_for_research(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ranked_events: list[dict[str, Any]] = []
    for event in events:
        research_rank_score, research_rank_reason = compute_research_rank(event)
        enriched = dict(event)
        enriched["research_rank_score"] = research_rank_score
        enriched["research_rank_reason"] = research_rank_reason
        ranked_events.append(enriched)
    ranked_events.sort(
        key=lambda item: (
            float(item.get("research_rank_score") or 0.0),
            float(item.get("event_rank_score") or 0.0),
            str(item.get("last_seen_at") or ""),
        ),
        reverse=True,
    )
    return ranked_events


def build_profile_topic_slices(
    events: list[dict[str, Any]],
    *,
    limit_topics: int = 6,
    limit_per_topic: int = 4,
) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        topic_key = str(event.get("topic_key") or "").strip()
        if not topic_key:
            continue
        grouped[topic_key].append(event)

    slices: dict[str, dict[str, Any]] = {}
    ranked_topics = sorted(
        grouped.items(),
        key=lambda item: (
            len(item[1]),
            max(float(event.get("research_rank_score") or 0.0) for event in item[1]),
            max(str(event.get("last_seen_at") or "") for event in item[1]),
        ),
        reverse=True,
    )
    for topic_key, topic_events in ranked_topics[:limit_topics]:
        ranked_events = sorted(
            topic_events,
            key=lambda item: (
                float(item.get("research_rank_score") or 0.0),
                float(item.get("event_rank_score") or 0.0),
                str(item.get("last_seen_at") or ""),
            ),
            reverse=True,
        )
        slices[topic_key] = {
            "topic_key": topic_key,
            "event_count": len(topic_events),
            "latest_seen_at": max((str(event.get("last_seen_at") or "") for event in topic_events), default=""),
            "top_events": [event_brief_with_research(event) for event in ranked_events[:limit_per_topic]],
        }
    return slices


def build_related_queries(
    entity_name: str,
    entity_id: str,
    aliases: list[str],
    events: list[dict[str, Any]],
    entity_type: str,
) -> list[dict[str, str]]:
    candidates: list[tuple[str, str]] = [
        (entity_name, "canonical_name"),
        (entity_id, "canonical_id"),
    ]
    candidates.extend((alias, "alias") for alias in aliases)
    for event in events[:8]:
        primary_industry = str(event.get("primary_industry") or "").strip()
        if primary_industry:
            candidates.append((primary_industry, "primary_industry"))
        topic_key = str(event.get("topic_key") or "").strip()
        if topic_key:
            candidates.append((topic_key, "topic_key"))
        if entity_type == "company":
            for industry in event.get("entities_by_type", {}).get("industry", []):
                name = str(industry.get("entity_name") or "").strip()
                if name:
                    candidates.append((name, "linked_industry"))
    related: list[dict[str, str]] = []
    seen: set[str] = set()
    for value, reason in candidates:
        clean = str(value or "").strip()
        if not clean:
            continue
        key = clean.casefold()
        if key in seen:
            continue
        seen.add(key)
        related.append({"query": clean, "reason": reason})
    return related[:12]


def build_entity_retrieval_index(
    events: list[dict[str, Any]],
    entity_type: str,
    limit_per_entity: int = 10,
) -> dict[str, dict[str, Any]]:
    alias_map = load_entity_alias_map()
    company_metadata_map = load_company_metadata_map() if entity_type == "company" else {}
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        for entity in event["entities_by_type"].get(entity_type, []):
            entity_id = str(entity["entity_id"])
            entity_name = str(entity["entity_name"])
            if entity_type == "company":
                normalized_name = canonicalize_entity_name(trim_company_candidate(entity_name))
                if not normalized_name or not looks_like_company_entity(normalized_name):
                    continue
                entity_name = normalized_name
                entity_id = canonical_company_id(normalized_name) or entity_id
            grouped[(entity_id, entity_name)].append(event)

    profiles: dict[str, dict[str, Any]] = {}
    for (entity_id, entity_name), entity_events in sorted(grouped.items()):
        aliases = list(alias_map.get(entity_type, {}).get(entity_id, []))
        company_metadata = {"ticker": "", "region": ""}
        if entity_type == "company":
            company_metadata = resolve_company_profile_metadata(entity_name, entity_id, aliases, company_metadata_map)
        if entity_type == "company" and not is_researchable_company_profile(entity_name, aliases, entity_events):
            continue
        ranked = sorted(
            entity_events,
            key=lambda item: (
                float(item.get("research_rank_score") or 0.0),
                float(item.get("event_rank_score") or 0.0),
                str(item.get("last_seen_at") or ""),
            ),
            reverse=True,
        )
        top_events: list[dict[str, Any]] = []
        for event in ranked[:limit_per_entity]:
            top_events.append(event_brief_with_research(event))
        latest_seen_at = max((str(event.get("last_seen_at") or "") for event in ranked), default="")
        lookup_terms = sorted(
            {
                entity_name,
                entity_id,
                *aliases,
            }
        )
        profiles[entity_name] = {
            "entity_name": entity_name,
            "entity_id": entity_id,
            "entity_type": entity_type,
            "aliases": aliases,
            "lookup_terms": lookup_terms,
            "event_count": len(ranked),
            "latest_seen_at": latest_seen_at,
            "top_events": top_events,
            "timeline": build_profile_timeline(ranked, limit=12),
            "topic_slices": build_profile_topic_slices(ranked),
            "related_queries": build_related_queries(entity_name, entity_id, aliases, ranked, entity_type),
            "evidence_bundle": rank_research_evidence_bundle(ranked, limit=12),
        }
        if company_metadata["ticker"]:
            profiles[entity_name]["ticker"] = company_metadata["ticker"]
        if company_metadata["region"]:
            profiles[entity_name]["region"] = company_metadata["region"]
        if entity_type in {"company", "industry", "institution"}:
            profiles[entity_name]["discovery_routes"] = build_entity_discovery_routes(
                entity_name=entity_name,
                entity_type=entity_type,
                aliases=aliases,
                ticker=company_metadata["ticker"],
                region=company_metadata["region"],
            )
    return profiles


def build_topic_index(events: list[dict[str, Any]], limit_per_topic: int = 8) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        topic_key = str(event.get("topic_key") or "").strip()
        if not topic_key:
            continue
        grouped[topic_key].append(event)
    result: dict[str, list[dict[str, Any]]] = {}
    for topic_key, topic_events in sorted(grouped.items()):
        ranked = sorted(
            topic_events,
            key=lambda item: (
                float(item.get("research_rank_score") or 0.0),
                float(item.get("event_rank_score") or 0.0),
                str(item.get("last_seen_at") or ""),
            ),
            reverse=True,
        )
        result[topic_key] = []
        for event in ranked[:limit_per_topic]:
            result[topic_key].append(event_brief_with_research(event))
    return result


def build_topic_profiles(
    events: list[dict[str, Any]],
    *,
    limit_topics: int = 20,
    limit_per_topic: int = 6,
) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        topic_key = str(event.get("topic_key") or "").strip()
        if not topic_key:
            continue
        grouped[topic_key].append(event)

    profiles: dict[str, dict[str, Any]] = {}
    ranked_topics = sorted(
        grouped.items(),
        key=lambda item: (
            len(item[1]),
            max(float(event.get("research_rank_score") or 0.0) for event in item[1]),
            max(str(event.get("last_seen_at") or "") for event in item[1]),
        ),
        reverse=True,
    )
    for topic_key, topic_events in ranked_topics[:limit_topics]:
        ranked = sorted(
            topic_events,
            key=lambda item: (
                float(item.get("research_rank_score") or 0.0),
                float(item.get("event_rank_score") or 0.0),
                str(item.get("last_seen_at") or ""),
            ),
            reverse=True,
        )
        top_event = ranked[0] if ranked else {}
        display_label = (
            str(top_event.get("primary_entity") or "").strip()
            or str(top_event.get("primary_industry") or "").strip()
            or topic_key
        )
        profiles[topic_key] = {
            "topic_key": topic_key,
            "display_label": display_label,
            "event_count": len(topic_events),
            "latest_seen_at": max((str(event.get("last_seen_at") or "") for event in topic_events), default=""),
            "top_events": [event_brief_with_research(event) for event in ranked[:limit_per_topic]],
            "timeline": build_profile_timeline(ranked, limit=limit_per_topic),
            "evidence_bundle": rank_research_evidence_bundle(ranked, limit=10),
        }
    return profiles


def event_day_key(event: dict[str, Any]) -> str:
    seen = parse_dt(str(event.get("last_seen_at") or event.get("first_seen_at") or ""))
    return seen.date().isoformat()


def build_point_in_time_day_panel(
    events: list[dict[str, Any]],
    *,
    entity_type: str,
    limit_rows: int = 400,
    limit_events: int = 6,
) -> dict[str, Any]:
    alias_map = load_entity_alias_map()
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    canonical_names: dict[tuple[str, str, str], str] = {}

    for event in events:
        panel_date = event_day_key(event)
        for entity in event.get("entities_by_type", {}).get(entity_type, []):
            entity_name = str(entity.get("entity_name") or "").strip()
            entity_id = str(entity.get("entity_id") or "").strip()
            if not entity_name:
                continue
            if entity_type == "company":
                normalized_name = canonicalize_entity_name(trim_company_candidate(entity_name)) or entity_name
                if not is_researchable_company_name(normalized_name, list(alias_map.get("company", {}).get(entity_id, []))):
                    continue
                entity_name = normalized_name
                entity_id = canonical_company_id(entity_name) or entity_id
            key = (panel_date, entity_id or entity_name, entity_name)
            grouped[key].append(event)
            canonical_names[key] = entity_name

    rows: list[dict[str, Any]] = []
    for (panel_date, entity_id, entity_name), entity_events in grouped.items():
        ranked = sorted(
            entity_events,
            key=lambda item: (
                float(item.get("research_rank_score") or 0.0),
                float(item.get("event_rank_score") or 0.0),
                str(item.get("last_seen_at") or ""),
            ),
            reverse=True,
        )
        state_mix = Counter(str(event.get("event_state") or "unknown") for event in entity_events)
        bucket_mix = Counter(derive_opportunity_candidate(event)["opportunity_bucket"] for event in entity_events)
        granularity_mix = Counter(
            derive_export_granularity_class(event)
            for event in entity_events
        )
        aliases = sorted(alias_map.get(entity_type, {}).get(entity_id, []))
        lookup_terms = sorted({canonical_names[(panel_date, entity_id, entity_name)], entity_id, *aliases} - {""})
        latest_seen_at = max((str(event.get("last_seen_at") or "") for event in entity_events), default="")
        max_confirmation = max((float(event.get("calibrated_confirmation") or 0.0) for event in entity_events), default=0.0)
        max_global_score = max((float(event.get("event_rank_score") or 0.0) for event in entity_events), default=0.0)
        max_research_score = max((float(event.get("research_rank_score") or 0.0) for event in entity_events), default=0.0)
        topic_keys = sorted({str(event.get("topic_key") or "") for event in entity_events if str(event.get("topic_key") or "").strip()})
        rows.append(
            {
                "panel_key": f"{panel_date}::{entity_type}::{entity_id or normalize_lookup_key(entity_name)}",
                "panel_date": panel_date,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "entity_name": entity_name,
                "aliases": aliases,
                "lookup_terms": lookup_terms,
                "event_count": len(entity_events),
                "confirmed_event_count": int(state_mix.get("confirmed", 0)),
                "latest_seen_at": latest_seen_at,
                "max_confirmation": round(max_confirmation, 3),
                "max_global_rank_score": round(max_global_score, 3),
                "max_research_rank_score": round(max_research_score, 3),
                "event_state_mix": dict(state_mix),
                "opportunity_bucket_mix": dict(bucket_mix),
                "granularity_mix": dict(granularity_mix),
                "topic_keys": topic_keys,
                "top_events": [event_brief_with_research(event) for event in ranked[:limit_events]],
                "evidence_bundle": rank_research_evidence_bundle(ranked, limit=min(8, limit_events + 2)),
            }
        )

    rows.sort(
        key=lambda item: (
            item["panel_date"],
            float(item.get("max_research_rank_score") or 0.0),
            int(item.get("event_count") or 0),
            str(item.get("entity_name") or ""),
        ),
        reverse=True,
    )

    day_summaries: list[dict[str, Any]] = []
    date_grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        date_grouped[str(row["panel_date"])].append(row)
    for panel_date, panel_rows in sorted(date_grouped.items(), reverse=True):
        day_summaries.append(
            {
                "panel_date": panel_date,
                "row_count": len(panel_rows),
                "entity_count": len({str(row.get("entity_id") or row.get("entity_name") or "") for row in panel_rows}),
                "event_count": sum(int(row.get("event_count") or 0) for row in panel_rows),
            }
        )

    return {
        "row_count": len(rows),
        "days": day_summaries,
        "rows": rows[:limit_rows],
    }


def derive_export_granularity_class(event: dict[str, Any]) -> str:
    flags_bucket = (event.get("event_rank_flags") or {}).get("flags") if isinstance(event.get("event_rank_flags"), dict) else {}
    explicit = str((flags_bucket or {}).get("granularity_class") or "").strip()
    if explicit:
        return explicit
    update_count = int(event.get("update_count") or 0)
    structural_event = bool((flags_bucket or {}).get("structural_event"))
    ongoing_topic = bool((flags_bucket or {}).get("ongoing_topic"))
    if ongoing_topic and update_count >= 3:
        return "ongoing_topic_rollup"
    if ongoing_topic:
        return "ongoing_topic"
    if structural_event and update_count >= 2:
        return "structural_multi_update"
    if structural_event:
        return "structural_discrete"
    if update_count >= 3:
        return "rolling_update"
    return "discrete_update"


def fetch_mapping_review(
    conn: sqlite3.Connection,
    cutoff_iso: str,
    *,
    unresolved_limit: int = 100,
    low_confidence_limit: int = 100,
) -> dict[str, Any]:
    unresolved_rows = conn.execute(
        """
        SELECT
            uem.event_id,
            uem.topic_key,
            uem.event_title,
            uem.unresolved_reason,
            uem.mapping_version,
            uem.detected_at,
            e.last_seen_at
        FROM unresolved_event_mappings uem
        LEFT JOIN events e ON e.event_id = uem.event_id
        WHERE datetime(COALESCE(e.last_seen_at, uem.detected_at)) >= datetime(?)
        ORDER BY datetime(COALESCE(e.last_seen_at, uem.detected_at)) DESC, uem.event_id DESC
        LIMIT ?
        """,
        (cutoff_iso, unresolved_limit),
    ).fetchall()
    low_confidence_rows = conn.execute(
        """
        SELECT
            eel.event_id,
            e.event_title,
            e.topic_key,
            e.last_seen_at,
            eel.entity_type,
            eel.entity_id,
            eel.entity_name,
            eel.mapping_reason,
            eel.mapping_confidence,
            eel.mapping_version,
            eel.mapping_source
        FROM event_entity_links eel
        JOIN events e ON e.event_id = eel.event_id
        WHERE datetime(e.last_seen_at) >= datetime(?)
          AND eel.mapping_confidence > 0
          AND eel.mapping_confidence < 0.7
        ORDER BY eel.mapping_confidence ASC, datetime(e.last_seen_at) DESC, eel.event_id DESC
        LIMIT ?
        """,
        (cutoff_iso, low_confidence_limit),
    ).fetchall()
    unresolved_reason_mix = Counter(str(row["unresolved_reason"] or "unknown") for row in unresolved_rows)
    entity_type_mix = Counter(str(row["entity_type"] or "unknown") for row in low_confidence_rows)
    return {
        "unresolved_count": len(unresolved_rows),
        "low_confidence_count": len(low_confidence_rows),
        "unresolved_reason_mix": dict(unresolved_reason_mix),
        "low_confidence_entity_type_mix": dict(entity_type_mix),
        "unresolved_events": [
            {
                "event_id": str(row["event_id"]),
                "event_title": str(row["event_title"] or ""),
                "topic_key": str(row["topic_key"] or ""),
                "unresolved_reason": str(row["unresolved_reason"] or ""),
                "mapping_version": str(row["mapping_version"] or ""),
                "detected_at": str(row["detected_at"] or ""),
                "last_seen_at": str(row["last_seen_at"] or ""),
            }
            for row in unresolved_rows
        ],
        "low_confidence_links": [
            {
                "event_id": str(row["event_id"]),
                "event_title": str(row["event_title"] or ""),
                "topic_key": str(row["topic_key"] or ""),
                "last_seen_at": str(row["last_seen_at"] or ""),
                "entity_type": str(row["entity_type"] or ""),
                "entity_id": str(row["entity_id"] or ""),
                "entity_name": str(row["entity_name"] or ""),
                "mapping_reason": str(row["mapping_reason"] or ""),
                "mapping_confidence": round(float(row["mapping_confidence"] or 0.0), 3),
                "mapping_version": str(row["mapping_version"] or ""),
                "mapping_source": str(row["mapping_source"] or ""),
            }
            for row in low_confidence_rows
        ],
    }


def build_entity_query_index(
    entity_profiles: dict[str, dict[str, Any]],
    industry_profiles: dict[str, dict[str, Any]],
    institution_profiles: dict[str, dict[str, Any]],
    topic_profiles: dict[str, dict[str, Any]],
) -> dict[str, dict[str, str]]:
    query_index: dict[str, dict[str, str]] = {}
    for profile_group in (entity_profiles, industry_profiles, institution_profiles):
        for profile in profile_group.values():
            entity_name = str(profile.get("entity_name") or "")
            entity_id = str(profile.get("entity_id") or "")
            entity_type = str(profile.get("entity_type") or "")
            for term in profile.get("lookup_terms") or []:
                clean = str(term or "").strip()
                if not clean:
                    continue
                normalized = normalize_lookup_key(clean)
                if not normalized:
                    continue
                query_index.setdefault(
                    normalized,
                    {
                        "entity_name": entity_name,
                        "entity_id": entity_id,
                        "entity_type": entity_type,
                    },
                )
    for topic_key in topic_profiles:
        normalized = normalize_lookup_key(topic_key)
        if not normalized:
            continue
        query_index.setdefault(
            normalized,
            {
                "entity_name": topic_key,
                "entity_id": topic_key,
                "entity_type": "topic",
            },
        )
    return query_index


def is_macro_event(event: dict[str, Any]) -> bool:
    return event["event_type"] in MACRO_EVENT_TYPES


def has_industry_or_company(event: dict[str, Any]) -> bool:
    return bool(event["entities_by_type"].get("industry")) or bool(event["entities_by_type"].get("company"))


def has_signal_lane(event: dict[str, Any]) -> bool:
    try:
        return int(event["source_mix"].get("signal", 0)) > 0
    except (AttributeError, TypeError, ValueError):
        return False


POSITIVE_TITLE_RE = re.compile(r"(签署|中标|获批|回购|分红|增持|扩产|收购|合作|launch|order|contract|buyback|dividend|acquire|approval)", re.IGNORECASE)
NEGATIVE_TITLE_RE = re.compile(r"(减持|下调|亏损|处罚|调查|诉讼|中断|停产|召回|裁员|延期|terminate|lawsuit|probe|cut|loss|downgrade|halt)", re.IGNORECASE)


def derive_opportunity_candidate(event: dict[str, Any]) -> dict[str, Any]:
    title = str(event.get("event_title") or "")
    state = str(event.get("event_state") or "")
    has_company = bool(event["entities_by_type"].get("company")) or bool(str(event.get("primary_entity") or "").strip())
    has_industry = bool(event["entities_by_type"].get("industry")) or bool(str(event.get("primary_industry") or "").strip())
    market_significance = score_vector_value(event, "market_significance")
    entity_local_priority = score_vector_value(event, "entity_local_priority", score_vector_value(event, "entity_impact"))
    researchability = score_vector_value(event, "researchability")
    signal_only = bool((event.get("source_mix") or {}).get("signal")) and not bool((event.get("source_mix") or {}).get("confirmation"))
    structural = bool(((event.get("event_rank_flags") or {}).get("flags") or {}).get("structural_event")) if isinstance(event.get("event_rank_flags"), dict) else False
    event_type = str(event.get("event_type") or "")

    if signal_only or state == "watch":
        opportunity_bucket = "tracking_update"
    elif is_macro_event(event):
        opportunity_bucket = "macro"
    elif has_company:
        opportunity_bucket = "company"
    elif has_industry:
        opportunity_bucket = "industry"
    elif event_type in {"deal_mna", "financing_capital", "special_situation"} or structural:
        opportunity_bucket = "special_situation"
    else:
        opportunity_bucket = "tracking_update"

    opportunity_type_map = {
        "macro": "macro_monitor",
        "industry": "industry_research",
        "company": "company_research",
        "special_situation": "special_situation_review",
        "tracking_update": "tracking_update",
    }
    opportunity_type = opportunity_type_map[opportunity_bucket]

    if signal_only or state in {"watch", "contested"}:
        thesis_impact = "unclear"
    elif NEGATIVE_TITLE_RE.search(title):
        thesis_impact = "negative"
    elif POSITIVE_TITLE_RE.search(title):
        thesis_impact = "positive"
    elif is_macro_event(event):
        thesis_impact = "neutral"
    else:
        thesis_impact = "unclear"

    if signal_only or state == "watch":
        followup_path = "wait_for_confirmation"
    elif opportunity_bucket == "company":
        followup_path = "open_company_research"
    elif opportunity_bucket == "industry":
        followup_path = "refresh_industry_note"
    elif opportunity_bucket == "macro":
        followup_path = "monitor_macro_topic"
    elif opportunity_bucket == "special_situation":
        followup_path = "review_special_situation"
    else:
        followup_path = "send_to_radar"

    portfolio_relevance = round(min(max(0.55 * market_significance + 0.45 * entity_local_priority, 0.0), 1.0), 3)
    watchlist_relevance = round(min(max(0.60 * entity_local_priority + 0.40 * researchability, 0.0), 1.0), 3)

    return {
        "opportunity_type": opportunity_type,
        "opportunity_bucket": opportunity_bucket,
        "portfolio_relevance": portfolio_relevance,
        "watchlist_relevance": watchlist_relevance,
        "thesis_impact": thesis_impact,
        "followup_path": followup_path,
    }


def select_opportunity_candidates(
    events: list[dict[str, Any]],
    *,
    per_bucket_limit: int | None = 12,
    include_macro_without_mapping: bool = False,
) -> dict[str, list[dict[str, Any]]]:
    new_candidates: list[dict[str, Any]] = []
    tracking_updates: list[dict[str, Any]] = []
    watchlist_candidates: list[dict[str, Any]] = []
    for event in events:
        has_explicit_mapping = has_industry_or_company(event) or bool(event["entities_by_type"].get("institution"))
        if not has_explicit_mapping and not (include_macro_without_mapping and is_macro_event(event)):
            continue
        if not include_macro_without_mapping and is_macro_event(event) and not event["entities_by_type"].get("industry"):
            continue
        brief = event_brief(event, include_supporting_articles=False)
        score = float(event["event_rank_score"] or 0.0)
        if score >= 55:
            new_candidates.append(brief)
        elif score >= 40:
            tracking_updates.append(brief)
        elif score >= 25:
            watchlist_candidates.append(brief)
    if per_bucket_limit is not None:
        new_candidates = new_candidates[:per_bucket_limit]
        tracking_updates = tracking_updates[:per_bucket_limit]
        watchlist_candidates = watchlist_candidates[:per_bucket_limit]
    return {
        "new_opportunity_candidates": new_candidates,
        "tracking_updates": tracking_updates,
        "watchlist_candidates": watchlist_candidates,
    }


def build_summary_text(events: list[dict[str, Any]], opportunity_buckets: dict[str, list[dict[str, Any]]]) -> str:
    total = len(events)
    macro_count = sum(1 for event in events if is_macro_event(event))
    company_count = sum(1 for event in events if event["entities_by_type"].get("company"))
    industry_names = [
        event["primary_industry"]
        for event in events
        if str(event.get("primary_industry") or "").strip()
    ]
    top_industries = [name for name, _ in Counter(industry_names).most_common(3)]
    industry_text = "、".join(top_industries) if top_industries else "行业映射仍偏分散"
    return (
        f"共享新闻库当前输出 {total} 条重点事件，宏观与政策主线 {macro_count} 条，"
        f"公司/行业相关事件 {company_count} 条；机会候选分布为新增 {len(opportunity_buckets['new_opportunity_candidates'])} 条、"
        f"跟踪 {len(opportunity_buckets['tracking_updates'])} 条、观察 {len(opportunity_buckets['watchlist_candidates'])} 条。"
        f"当前更集中的行业线索主要落在 {industry_text}。这是一层共享兼容摘要，"
        "最终解释与组合关联仍应由下游工作流继续补充。"
    )


def build_opportunity_report_feed(events: list[dict[str, Any]], run_dt: datetime, limit: int) -> dict[str, Any]:
    selected = events[:limit]
    opportunity_buckets = select_opportunity_candidates(selected)
    macro_events = [event_brief(event) for event in selected if is_macro_event(event)][:10]
    company_headlines = [event_brief(event) for event in selected if event["entities_by_type"].get("company")][:10]
    signal_events = [event_brief(event) for event in selected if has_signal_lane(event)][:8]
    summary_text = build_summary_text(selected, opportunity_buckets)
    legacy_digest = {
        "report_date": run_dt.date().isoformat(),
        "generated_at": run_dt.isoformat(timespec="seconds"),
        "article_count": sum(len(event["supporting_articles"]) for event in selected),
        "signal_count": len(opportunity_buckets["new_opportunity_candidates"]) + len(opportunity_buckets["tracking_updates"]),
        "top_market_news": macro_events,
        "official_macro_supplements": macro_events[:5],
        "new_opportunity_candidates": opportunity_buckets["new_opportunity_candidates"],
        "tracking_updates": opportunity_buckets["tracking_updates"],
        "watchlist_candidates": opportunity_buckets["watchlist_candidates"],
        "company_headlines": company_headlines,
        "company_official_news": company_headlines[:5],
        "company_media_news": company_headlines[:5],
        "market_rumors": signal_events,
        "credible_rumors": signal_events,
        "social_rumor_candidates": [event for event in signal_events if event["event_type"] == "social_signal"][:5],
        "investor_views": [],
        "polymarket_opportunities": [],
        "market_context_cn": summary_text,
        "analysis_summary_cn": summary_text,
        "shared_adapter_meta": {
            "adapter_version": ADAPTER_VERSION,
            "compatibility_scope": "minimal",
            "not_yet_backfilled_fields": ["investor_views", "polymarket_opportunities"],
        },
    }
    return {
        "schema_version": ADAPTER_VERSION,
        "consumer": "opportunity_report",
        "ranking_contract": build_global_feed_contract(),
        "generated_at": run_dt.isoformat(timespec="seconds"),
        "as_of": run_dt.isoformat(timespec="seconds"),
        "window_start": (run_dt - timedelta(hours=72)).isoformat(timespec="seconds"),
        "report_date": run_dt.date().isoformat(),
        "top_events": [event_brief(event) for event in selected[:20]],
        "macro_events": macro_events,
        "opportunity_buckets": opportunity_buckets,
        "legacy_news_digest": legacy_digest,
    }


def build_radar_opportunity_views(events: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    views = {
        "macro_events": [],
        "company_events": [],
        "industry_events": [],
        "institution_events": [],
        "special_situations": [],
        "tracking_updates": [],
        "signal_watchlist": [],
    }
    for event in events:
        compact = event_brief(event, include_supporting_articles=False)
        opportunity_bucket = compact["opportunity_bucket"]
        if is_macro_event(event):
            views["macro_events"].append(compact)
        if event["entities_by_type"].get("company"):
            views["company_events"].append(compact)
        if event["entities_by_type"].get("industry"):
            views["industry_events"].append(compact)
        if event["entities_by_type"].get("institution"):
            views["institution_events"].append(compact)
        if opportunity_bucket == "special_situation":
            views["special_situations"].append(compact)
        if opportunity_bucket == "tracking_update":
            views["tracking_updates"].append(compact)
        if has_signal_lane(event):
            views["signal_watchlist"].append(compact)
    return views


def build_radar_feed(events: list[dict[str, Any]], run_dt: datetime, per_industry_limit: int) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        for entity in event["entities_by_type"].get("industry", []):
            grouped[entity["entity_name"]].append(event)
    opportunity_buckets = select_opportunity_candidates(
        events,
        per_bucket_limit=None,
        include_macro_without_mapping=True,
    )
    radar_views = build_radar_opportunity_views(events)
    industries: list[dict[str, Any]] = []
    for industry, rows in sorted(grouped.items()):
        ranked = sorted(rows, key=lambda item: (float(item["event_rank_score"]), str(item["last_seen_at"])), reverse=True)
        shared_events = [event_brief(event) for event in ranked[:per_industry_limit]]
        policy_articles = [
            {
                "event_id": item["event_id"],
                "title": item["title"],
                "published_at": item["last_seen_at"],
                "source_count": item["source_count"],
                "confirmation_count": item["confirmation_count"],
                "event_type": item["event_type"],
                "score": item["score"],
            }
            for item in shared_events
        ]
        industries.append(
            {
                "industry": industry,
                "shared_news_score": round(sum(item["score"] for item in shared_events[:3]) / 100.0, 4),
                "event_count": len(ranked),
                "shared_events": shared_events,
                "policy_articles": policy_articles,
            }
        )
    industries.sort(key=lambda item: (item["shared_news_score"], item["event_count"], item["industry"]), reverse=True)
    return {
        "schema_version": ADAPTER_VERSION,
        "consumer": "investment_radar",
        "legacy_consumer": "industry_radar",
        "discovery_contract": build_feed_discovery_contract(),
        "generated_at": run_dt.isoformat(timespec="seconds"),
        "as_of": run_dt.isoformat(timespec="seconds"),
        "window_start": (run_dt - timedelta(hours=72)).isoformat(timespec="seconds"),
        "persistent_window_start": (run_dt - timedelta(hours=PERSISTENT_EVENT_LOOKBACK_HOURS)).isoformat(timespec="seconds"),
        "report_date": run_dt.date().isoformat(),
        "radar_scope": "all_investment_opportunities",
        "event_pool_count": len(events),
        "event_pool": [event_brief(event, include_supporting_articles=False) for event in events],
        "opportunity_buckets": opportunity_buckets,
        "radar_views": radar_views,
        "industries": industries,
    }


def build_research_feed(events: list[dict[str, Any]], run_dt: datetime, limit: int | None) -> dict[str, Any]:
    ranked_events = rank_events_for_research(events)
    selected = ranked_events if not limit or limit <= 0 else ranked_events[:limit]
    entity_profiles = build_entity_retrieval_index(ranked_events, "company")
    industry_profiles = build_entity_retrieval_index(ranked_events, "industry")
    institution_profiles = build_entity_retrieval_index(ranked_events, "institution")
    topic_index = build_topic_index(ranked_events)
    topic_profiles = build_topic_profiles(ranked_events)
    return {
        "schema_version": ADAPTER_VERSION,
        "consumer": "research",
        "ranking_contract": build_research_contract(),
        "discovery_contract": build_feed_discovery_contract(),
        "generated_at": run_dt.isoformat(timespec="seconds"),
        "as_of": run_dt.isoformat(timespec="seconds"),
        "window_start": (run_dt - timedelta(hours=72)).isoformat(timespec="seconds"),
        "persistent_window_start": (run_dt - timedelta(hours=PERSISTENT_EVENT_LOOKBACK_HOURS)).isoformat(timespec="seconds"),
        "report_date": run_dt.date().isoformat(),
        "recent_events": [
            {
                **event_brief(event),
                "research_rank_score": round(float(event.get("research_rank_score") or 0.0), 3),
                "research_rank_reason": str(event.get("research_rank_reason") or ""),
            }
            for event in selected
        ],
        "entity_index": {key: value["top_events"][:10] for key, value in entity_profiles.items()},
        "industry_index": {key: value["top_events"][:10] for key, value in industry_profiles.items()},
        "institution_index": {key: value["top_events"][:10] for key, value in institution_profiles.items()},
        "entity_profiles": entity_profiles,
        "industry_profiles": industry_profiles,
        "institution_profiles": institution_profiles,
        "topic_index": topic_index,
        "topic_profiles": topic_profiles,
        "entity_query_index": build_entity_query_index(entity_profiles, industry_profiles, institution_profiles, topic_profiles),
    }


def fetch_source_health(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT
            sh.source_id,
            sh.checked_at,
            sh.status,
            sh.articles_last_24h,
            sh.last_article_at,
            sh.error_message
        FROM source_health sh
        JOIN source_registry sr ON sr.source_id = sh.source_id
        WHERE sr.enabled = 1
          AND sh.id IN (
              SELECT MAX(id)
              FROM source_health
              GROUP BY source_id
          )
        ORDER BY sh.source_id
        """
    ).fetchall()
    return [
        {
            "source_id": str(row["source_id"]),
            "checked_at": str(row["checked_at"]),
            "status": str(row["status"]),
            "articles_last_24h": int(row["articles_last_24h"] or 0),
            "last_article_at": str(row["last_article_at"] or ""),
            "error_message": str(row["error_message"] or ""),
        }
        for row in rows
    ]


def summarize_source_health(rows: list[dict[str, Any]]) -> dict[str, Any]:
    summary = {"total": len(rows), "ok": 0, "degraded": 0, "down": 0, "other": 0}
    degraded_sources: list[str] = []
    down_sources: list[str] = []
    for row in rows:
        status = str(row.get("status") or "").strip().lower()
        source_id = str(row.get("source_id") or "").strip()
        if status in {"ok", "pass"}:
            summary["ok"] += 1
        elif status in {"degraded", "warn"}:
            summary["degraded"] += 1
            if source_id:
                degraded_sources.append(source_id)
        elif status in {"down", "fail", "failed", "error"}:
            summary["down"] += 1
            if source_id:
                down_sources.append(source_id)
        else:
            summary["other"] += 1
    status = "warn" if summary["degraded"] or summary["down"] or summary["other"] else "pass"
    return {
        "status": status,
        "summary": summary,
        "warnings": [
            f"degraded_sources={summary['degraded']}" if summary["degraded"] else "",
            f"down_sources={summary['down']}" if summary["down"] else "",
            f"other_status_sources={summary['other']}" if summary["other"] else "",
        ],
        "degraded_source_ids": degraded_sources[:20],
        "down_source_ids": down_sources[:20],
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_exports(
    conn: sqlite3.Connection,
    run_dt: datetime,
    lookback_hours: int,
    opportunity_limit: int,
    radar_per_industry_limit: int,
    research_limit: int,
) -> dict[str, dict[str, Any]]:
    cutoff_iso = (run_dt - timedelta(hours=lookback_hours)).isoformat(timespec="seconds")
    persistent_cutoff_iso = (run_dt - timedelta(hours=max(lookback_hours, PERSISTENT_EVENT_LOOKBACK_HOURS))).isoformat(timespec="seconds")
    rows = fetch_recent_events(conn, cutoff_iso, persistent_cutoff_iso, None)
    panel_rows = rows
    event_ids = sorted({str(row["event_id"]) for row in rows})
    entity_map = fetch_entities(conn, event_ids)
    article_map = fetch_supporting_articles(conn, event_ids)
    events = hydrate_events(rows, entity_map, article_map)
    panel_events = hydrate_events(panel_rows, entity_map, article_map)
    ranked_panel_events = rank_events_for_research(panel_events)
    source_health = fetch_source_health(conn)
    source_health_summary = summarize_source_health(source_health)
    opportunity_feed = build_opportunity_report_feed(events, run_dt, opportunity_limit)
    radar_feed = build_radar_feed(events, run_dt, radar_per_industry_limit)
    research_feed = build_research_feed(events, run_dt, research_limit)
    entity_day_panel = build_point_in_time_day_panel(ranked_panel_events, entity_type="company")
    industry_day_panel = build_point_in_time_day_panel(ranked_panel_events, entity_type="industry")
    institution_day_panel = build_point_in_time_day_panel(ranked_panel_events, entity_type="institution")
    mapping_review = fetch_mapping_review(conn, cutoff_iso)
    manifest = {
        "schema_version": ADAPTER_VERSION,
        "generated_at": run_dt.isoformat(timespec="seconds"),
        "as_of": run_dt.isoformat(timespec="seconds"),
        "window_start": cutoff_iso,
        "report_date": run_dt.date().isoformat(),
        "event_count": len(events),
        "source_health_count": len(source_health),
        "exports": {
            "opportunity_report": "opportunity_report_feed_latest.json",
            "industry_radar": "industry_radar_feed_latest.json",
            "research": "research_feed_latest.json",
            "legacy_news_digest": "legacy_news_digest_latest.json",
            "source_health": "source_health_latest.json",
            "entity_day_panel": "entity_day_panel_latest.json",
            "industry_day_panel": "industry_day_panel_latest.json",
            "institution_day_panel": "institution_day_panel_latest.json",
            "mapping_review": "mapping_review_latest.json",
        },
        "point_in_time_contract": {
            "event_window_scope": "full_lookback_window",
            "consumer_topn_decoupled": True,
            "panel_date_field": "last_seen_at_date",
        },
    }
    return {
        "opportunity_report_feed_latest.json": opportunity_feed,
        "industry_radar_feed_latest.json": radar_feed,
        "research_feed_latest.json": research_feed,
        "legacy_news_digest_latest.json": opportunity_feed["legacy_news_digest"],
        "source_health_latest.json": {
            "schema_version": ADAPTER_VERSION,
            "generated_at": run_dt.isoformat(timespec="seconds"),
            "report_date": run_dt.date().isoformat(),
            "status": source_health_summary["status"],
            "summary": source_health_summary["summary"],
            "warnings": [item for item in source_health_summary["warnings"] if item],
            "degraded_source_ids": source_health_summary["degraded_source_ids"],
            "down_source_ids": source_health_summary["down_source_ids"],
            "source_health": source_health,
        },
        "entity_day_panel_latest.json": {
            "schema_version": ADAPTER_VERSION,
            "consumer": "entity_day_panel",
            "generated_at": run_dt.isoformat(timespec="seconds"),
            "as_of": run_dt.isoformat(timespec="seconds"),
            "window_start": cutoff_iso,
            "report_date": run_dt.date().isoformat(),
            **entity_day_panel,
        },
        "industry_day_panel_latest.json": {
            "schema_version": ADAPTER_VERSION,
            "consumer": "industry_day_panel",
            "generated_at": run_dt.isoformat(timespec="seconds"),
            "as_of": run_dt.isoformat(timespec="seconds"),
            "window_start": cutoff_iso,
            "report_date": run_dt.date().isoformat(),
            **industry_day_panel,
        },
        "institution_day_panel_latest.json": {
            "schema_version": ADAPTER_VERSION,
            "consumer": "institution_day_panel",
            "generated_at": run_dt.isoformat(timespec="seconds"),
            "as_of": run_dt.isoformat(timespec="seconds"),
            "window_start": cutoff_iso,
            "report_date": run_dt.date().isoformat(),
            **institution_day_panel,
        },
        "mapping_review_latest.json": {
            "schema_version": ADAPTER_VERSION,
            "generated_at": run_dt.isoformat(timespec="seconds"),
            "as_of": run_dt.isoformat(timespec="seconds"),
            "window_start": cutoff_iso,
            "report_date": run_dt.date().isoformat(),
            **mapping_review,
        },
        "manifest_latest.json": manifest,
    }


def main() -> None:
    args = parse_args()
    run_dt = parse_run_dt(args.run_at)
    with open_db(args.db) as conn:
        payloads = build_exports(
            conn,
            run_dt=run_dt,
            lookback_hours=args.lookback_hours,
            opportunity_limit=args.opportunity_limit,
            radar_per_industry_limit=args.radar_per_industry_limit,
            research_limit=args.research_limit,
        )
    args.output_root.mkdir(parents=True, exist_ok=True)
    dated_root = args.output_root / "dated" / run_dt.strftime("%Y") / run_dt.strftime("%m") / run_dt.strftime("%d") / run_dt.strftime("%H%M%SZ")
    for name, payload in payloads.items():
        write_json(args.output_root / name, payload)
        if not args.no_dated_copy:
            write_json(dated_root / name, payload)
    print(f"generated_at: {run_dt.isoformat(timespec='seconds')}")
    print(f"output_root: {args.output_root}")
    if args.no_dated_copy:
        print("dated_root: disabled")
    else:
        print(f"dated_root: {dated_root}")
    print(f"files_written: {len(payloads)}")
    print(
        "opportunity_top_events:",
        len(payloads["opportunity_report_feed_latest.json"].get("top_events", [])),
    )
    print(
        "radar_industries:",
        len(payloads["industry_radar_feed_latest.json"].get("industries", [])),
    )
    print(
        "research_recent_events:",
        len(payloads["research_feed_latest.json"].get("recent_events", [])),
    )
    print(
        "entity_day_rows:",
        len(payloads["entity_day_panel_latest.json"].get("rows", [])),
    )
    print(
        "industry_day_rows:",
        len(payloads["industry_day_panel_latest.json"].get("rows", [])),
    )


if __name__ == "__main__":
    main()
