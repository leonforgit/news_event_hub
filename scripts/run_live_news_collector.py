#!/usr/bin/env python3
from __future__ import annotations

import argparse
import contextlib
import csv
import hashlib
import html
import io
import json
import os
import re
import sqlite3
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, unquote, urlencode, urljoin, urlparse, urlunparse
import xml.etree.ElementTree as ET

import requests
import yaml
from bs4 import BeautifulSoup

try:
    import akshare as ak  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - exercised only where akshare is unavailable
    ak = None


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = ROOT / "runtime" / "news_event.db"
DEFAULT_REGISTRY = ROOT / "config" / "source_registry_v1.yaml"
DEFAULT_CATALOG = ROOT / "config" / "live_collector_catalog_v1.json"
DEFAULT_SCHEMA = ROOT / "config" / "schema.sql"
DEFAULT_CONSUMER_EXPORT_ROOT = ROOT / "state" / "consumer_exports"
DEFAULT_WATCHLIST_REGISTRY = Path.home() / ".codex" / "state" / "investment" / "watchlist" / "watchlist_registry.csv"
DEFAULT_WEIBO_STATE = ROOT / "state" / "auth" / "weibo_storage_state.json"
DEFAULT_AGENT_REACH_STATE = ROOT / "state" / "auth" / "agent_reach" / "playwright_shared_auth.json"
BLOCKED_SOURCE_IDS = {"xiaohongshu_tracked_search"}
BLOCKED_SOURCE_FAMILIES = {"social:xiaohongshu"}
REQUEST_TIMEOUT = 25
SQLITE_BUSY_TIMEOUT_MS = 600000
FEED_QUARANTINE_MINUTES = 360
ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}
WHITESPACE_RE = re.compile(r"\s+")
HTML_TAG_RE = re.compile(r"<[^>]+>")
CLS_PATTERN = re.compile(
    r'"brief":"(?P<brief>.*?)".*?"id":(?P<id>\d+),"ctime":(?P<ctime>\d+).*?"shareurl":"(?P<shareurl>https://api3\.cls\.cn/share/article/\d+\?os=web\\u0026sv=[^"]+)"',
    re.S,
)
CHINA_TZ = timezone(timedelta(hours=8))
HK_TZ = timezone(timedelta(hours=8))
HKEX_PARTIAL_URL = "https://www1.hkexnews.hk/search/partial.do"
HKEX_TITLE_URL = "https://www1.hkexnews.hk/search/titleSearchServlet.do"
CNINFO_CATEGORY = (
    "category_ndbg_szsh;category_bndbg_szsh;category_sf_szsh;category_dqbg_szsh;"
    "category_zqbg_szsh;category_lh_szsh;category_ydfy_szsh;category_gszc_szsh;category_qtpzyj_szsh"
)
GUBA_DISCOVERY_TITLE_RE = re.compile(
    r"(传闻|据传|据悉|听说|爆料|传出|小作文|重组|并购|收购|洽购|资产注入|借壳|定增|回购|增持|"
    r"订单|中标|提价|涨价|扩产|停产|复产|合作|签约|项目|批复|规划|产能|供货|拿单)",
    re.IGNORECASE,
)
GUBA_DISCOVERY_NOISE_RE = re.compile(
    r"(午评|收评|早评|复盘|实盘|打板|龙头战法|缠论|老师|大神|明天|尾盘|短线|超短|妖股|"
    r"预测|竞猜|签到|打卡|持仓分享|看多|看空)",
    re.IGNORECASE,
)
WEIBO_DISCOVERY_RE = re.compile(
    r"(传闻|据传|据悉|听说|爆料|小作文|并购|收购|重组|借壳|定增|扩产|停产|复产|"
    r"订单|中标|提价|涨价|回购|增持|资产注入|控制权|要约|投建|募资|获批|批复)",
    re.IGNORECASE,
)
WEIBO_NOISE_RE = re.compile(
    r"(抽奖|转发微博|早安|午安|晚安|签到|福利视频|段子|星座|八卦|追剧|自拍|"
    r"日常分享|粉丝福利|超话|打卡)",
    re.IGNORECASE,
)
WEIBO_MEDIA_AUTHOR_RE = re.compile(
    r"(资讯|财经|证券|日报|时报|晚报|新闻|观察|研报|快讯|快报|资本|投研|研究院|"
    r"官微|客服|小助理|公司公告)",
    re.IGNORECASE,
)
WEIBO_SYNDICATION_RE = re.compile(
    r"(^【.+?】)|"
    r"(文章来源|原标题|责任编辑|记者|通讯员|客户端|据.+?报道|.+?日讯|全文如下|点击链接|"
    r"网页链接|原文链接|视频链接|直播回放)",
    re.IGNORECASE,
)
WEIBO_RUMORISH_RE = re.compile(
    r"(传闻|据传|据悉|听说|爆料|小作文|停产|复产|回购|增持|定增|资产注入|"
    r"并购|收购|重组|订单|中标|提价|涨价|扩产|投建|募资|批复|获批|控制权)",
    re.IGNORECASE,
)
WEIBO_OFFICIAL_REPOST_RE = re.compile(
    r"(公告，公司拟|公告称|披露.*公告|发布公告|拟按每股|配售价|投资总额|设立全资子公司|"
    r"董事会审议通过|公司公告显示)",
    re.IGNORECASE,
)
WEIBO_GENERIC_POST_RE = re.compile(
    r"(受益个股汇总|个股汇总|板块.*汇总|板块.*受益|核心龙头|价值投资日志|周[一二三四五六日天].*重磅消息|"
    r"利好利空|港股异动|正在直播|直播回放|直播|智通财经APP|.*?APP获悉|快讯播报|早盘必读|尾盘观察|"
    r"收评|午评|复盘|点评|投资逻辑|产业链梳理|相关标的)",
    re.IGNORECASE,
)
WEIBO_BASKET_MOVE_RE = re.compile(r"[A-Za-z\u4e00-\u9fff0-9\.\-]+[+＋-]\d+(?:\.\d+)?%")
DEFAULT_WEIBO_KEYWORDS = ("传闻", "收购", "并购", "重组", "订单", "扩产", "停产", "提价", "增持", "回购")
DEFAULT_XUEQIU_KEYWORDS = DEFAULT_WEIBO_KEYWORDS
SCHEDULER_DEFAULTS = {
    "high_freq": 10,
    "daily": 360,
    "on_demand": None,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the phase-1 live collector for the unified news database.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="SQLite database path.")
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA, help="Schema SQL path.")
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY, help="Source registry YAML path.")
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG, help="Live collector catalog JSON path.")
    parser.add_argument("--consumer-export-root", type=Path, default=DEFAULT_CONSUMER_EXPORT_ROOT, help="Shared consumer export directory for target resolution.")
    parser.add_argument("--watchlist-registry", type=Path, default=DEFAULT_WATCHLIST_REGISTRY, help="Canonical watchlist registry CSV for tracked targets.")
    parser.add_argument("--weibo-state-path", type=Path, default=DEFAULT_WEIBO_STATE, help="Weibo storage-state JSON for shared signal collection.")
    parser.add_argument(
        "--target-name",
        action="append",
        dest="target_names",
        help="Optional ad-hoc tracked target name. Can be repeated and is merged ahead of watchlist/feed-derived targets.",
    )
    parser.add_argument(
        "--scheduler-class",
        action="append",
        dest="scheduler_classes",
        help="Only run these scheduler classes. Can be repeated.",
    )
    parser.add_argument(
        "--source-id",
        action="append",
        dest="source_ids",
        help="Only run the specified source ids. Can be repeated.",
    )
    parser.add_argument("--force", action="store_true", help="Ignore min_interval_minutes and run due sources immediately.")
    parser.add_argument("--limit-sources", type=int, default=0, help="Optional max number of sources to process.")
    return parser.parse_args()


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def isoformat_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds")


def parse_iso_datetime(value: str | None) -> datetime | None:
    clean = str(value or "").strip()
    if not clean:
        return None
    try:
        parsed = datetime.fromisoformat(clean.replace("Z", "+00:00"))
    except ValueError:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
            try:
                parsed = datetime.strptime(clean, fmt).replace(tzinfo=timezone.utc)
                break
            except ValueError:
                continue
        else:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def normalize_title(value: str | None) -> str:
    return WHITESPACE_RE.sub(" ", str(value or "").strip().lower())


def strip_html(value: str | None) -> str:
    if not value:
        return ""
    clean = html.unescape(str(value))
    clean = HTML_TAG_RE.sub(" ", clean)
    return WHITESPACE_RE.sub(" ", clean).strip()


def detect_language(title: str | None, summary: str | None) -> str:
    sample = f"{title or ''} {summary or ''}"
    return "zh" if re.search(r"[\u4e00-\u9fff]", sample) else "en"


def normalize_url(url: str) -> str:
    if not url:
        return ""
    parsed = urlparse(url)
    if parsed.scheme and parsed.scheme not in {"http", "https"}:
        return ""
    if parsed.scheme in {"http", "https"} and not parsed.netloc:
        return ""
    query = parse_qs(parsed.query)
    filtered_query = {
        key: values
        for key, values in query.items()
        if not key.lower().startswith("utm_") and key.lower() not in {"oc", "src", "guccounter"}
    }
    normalized = parsed._replace(query=urlencode(filtered_query, doseq=True), fragment="")
    return urlunparse(normalized)


def canonicalize_link(link: str) -> tuple[str, str]:
    parsed = urlparse(link)
    if "bing.com" in parsed.netloc and parsed.path.endswith("/news/apiclick.aspx"):
        raw_target = parse_qs(parsed.query).get("url", [link])[0]
        target = normalize_url(unquote(raw_target))
        return target, target
    cleaned = normalize_url(link)
    return cleaned, cleaned


def decode_embedded_json_string(value: str | None) -> str:
    raw = str(value or "")
    if not raw:
        return ""
    try:
        decoded = html.unescape(json.loads(f'"{raw}"'))
    except json.JSONDecodeError:
        fallback = raw.replace("\\/", "/").replace("\\u0026", "&").replace("\\n", " ").replace("\\r", " ").replace("\\t", " ")
        decoded = html.unescape(fallback)
    return WHITESPACE_RE.sub(" ", decoded).strip()


def parse_datetime(value: str | None) -> str | None:
    if not value:
        return None
    normalized = str(value).strip().replace("Z", "+00:00")
    try:
        parsed = parsedate_to_datetime(normalized)
    except (TypeError, ValueError, IndexError):
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat(timespec="seconds")


def parse_cn_date(value: str | None) -> str | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d", "%Y%m%d"):
        try:
            parsed = datetime.strptime(value.strip(), fmt).replace(tzinfo=CHINA_TZ)
            return parsed.astimezone(timezone.utc).isoformat(timespec="seconds")
        except ValueError:
            continue
    return None


def parse_human_datetime(value: str | None, run_dt: datetime) -> str | None:
    clean = " ".join(str(value or "").strip().split())
    if not clean:
        return None
    if clean.isdigit():
        try:
            stamp = int(clean)
            if len(clean) >= 13:
                parsed = datetime.fromtimestamp(stamp / 1000.0, tz=timezone.utc)
            else:
                parsed = datetime.fromtimestamp(stamp, tz=CHINA_TZ)
            return parsed.astimezone(timezone.utc).isoformat(timespec="seconds")
        except (TypeError, ValueError, OSError):
            return None
    if clean == "刚刚":
        return isoformat_utc(run_dt)
    minute_match = re.search(r"(\d+)\s*分钟前", clean)
    if minute_match:
        return isoformat_utc(run_dt - timedelta(minutes=int(minute_match.group(1))))
    hour_match = re.search(r"(\d+)\s*小时前", clean)
    if hour_match:
        return isoformat_utc(run_dt - timedelta(hours=int(hour_match.group(1))))
    day_match = re.search(r"(\d+)\s*天前", clean)
    if day_match:
        return isoformat_utc(run_dt - timedelta(days=int(day_match.group(1))))
    if re.fullmatch(r"\d{1,2}:\d{2}", clean):
        local_now = run_dt.astimezone(CHINA_TZ)
        parsed = datetime.strptime(f"{local_now.date().isoformat()} {clean}", "%Y-%m-%d %H:%M").replace(tzinfo=CHINA_TZ)
        if parsed > local_now + timedelta(hours=2):
            parsed -= timedelta(days=1)
        return parsed.astimezone(timezone.utc).isoformat(timespec="seconds")
    return parse_datetime(clean)


def parse_china_datetime_fields(date_value: str | None, time_value: str | None, run_dt: datetime) -> str | None:
    date_text = str(date_value or "").strip()
    time_text = str(time_value or "").strip()
    local_today = run_dt.astimezone(CHINA_TZ).date().isoformat()
    candidates: list[str] = []
    if date_text and time_text:
        candidates.append(f"{date_text} {time_text}")
    if time_text and re.fullmatch(r"\d{1,2}:\d{2}(:\d{2})?", time_text):
        candidates.append(f"{date_text or local_today} {time_text}")
    if time_text:
        candidates.append(time_text)
    seen: set[str] = set()
    for candidate in candidates:
        if candidate in seen or not candidate:
            continue
        seen.add(candidate)
        for fmt in (
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y/%m/%d %H:%M:%S",
            "%Y/%m/%d %H:%M",
            "%Y.%m.%d %H:%M:%S",
            "%Y.%m.%d %H:%M",
            "%Y%m%d %H:%M:%S",
            "%Y%m%d %H:%M",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%dT%H:%M",
        ):
            try:
                parsed = datetime.strptime(candidate, fmt).replace(tzinfo=CHINA_TZ)
                return parsed.astimezone(timezone.utc).isoformat(timespec="seconds")
            except ValueError:
                continue
    parsed_date = parse_cn_date(date_text) if date_text else None
    if parsed_date:
        inferred = parse_iso_datetime(parsed_date)
        if inferred is not None:
            inferred = inferred.astimezone(CHINA_TZ).replace(hour=12, minute=0, second=0, microsecond=0)
            return inferred.astimezone(timezone.utc).isoformat(timespec="seconds")
    if time_text:
        return parse_human_datetime(time_text, run_dt)
    return None


def parse_date_like(value: Any) -> str | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        parsed = value if value.tzinfo else value.replace(tzinfo=CHINA_TZ)
        return parsed.astimezone(timezone.utc).isoformat(timespec="seconds")
    if isinstance(value, date):
        parsed = datetime.combine(value, datetime.min.time()).replace(tzinfo=CHINA_TZ)
        parsed = parsed.replace(hour=12)
        return parsed.astimezone(timezone.utc).isoformat(timespec="seconds")
    text = str(value).strip()
    if not text:
        return None
    parsed = parse_cn_date(text)
    if parsed is not None:
        parsed_dt = parse_iso_datetime(parsed)
        if parsed_dt is not None:
            return parsed_dt.astimezone(CHINA_TZ).replace(hour=12, minute=0, second=0, microsecond=0).astimezone(timezone.utc).isoformat(timespec="seconds")
    return parse_datetime(text)


def maybe_strip_regex_delimiters(value: str | None) -> str:
    text = str(value or "").strip()
    if len(text) >= 2 and text.startswith("/") and text.endswith("/"):
        return text[1:-1]
    return text


def html_node_text(node: Any) -> str:
    if node is None:
        return ""
    return WHITESPACE_RE.sub(" ", node.get_text(" ", strip=True)).strip()


def parse_html_list_items(html_text: str, source: dict[str, Any], run_dt: datetime) -> list[dict[str, Any]]:
    item_selector = str(source.get("item_selector") or "").strip()
    link_selector = str(source.get("link_selector") or "").strip()
    title_selector = str(source.get("title_selector") or link_selector).strip()
    if not item_selector or not link_selector or not title_selector:
        return []
    summary_selector = str(source.get("summary_selector") or "").strip()
    published_selector = str(source.get("published_at_selector") or "").strip()
    published_attr = str(source.get("published_at_attr") or "").strip()
    publisher_selector = str(source.get("publisher_selector") or "").strip()
    base_url = str(source.get("base_url") or source.get("url") or "").strip()
    url_allow_pattern = maybe_strip_regex_delimiters(source.get("url_allow_regex"))
    soup = BeautifulSoup(html_text, "lxml")
    items: list[dict[str, Any]] = []
    for node in soup.select(item_selector):
        link_node = node.select_one(link_selector)
        title_node = node.select_one(title_selector) or link_node
        if link_node is None or title_node is None:
            continue
        raw_href = str(link_node.get("href") or "").strip()
        url = normalize_url(urljoin(base_url, raw_href))
        if not url:
            continue
        if url_allow_pattern and re.search(url_allow_pattern, url) is None:
            continue
        title = html_node_text(title_node)
        if not title:
            continue
        summary = html_node_text(node.select_one(summary_selector)) if summary_selector else ""
        publisher = html_node_text(node.select_one(publisher_selector)) if publisher_selector else ""
        published_raw = ""
        if published_selector == "__self__":
            if published_attr:
                published_raw = str(node.get(published_attr) or "").strip()
            else:
                published_raw = html_node_text(node)
        elif published_selector:
            published_node = node.select_one(published_selector)
            if published_node is not None:
                published_raw = str(published_node.get(published_attr) or "").strip() if published_attr else html_node_text(published_node)
        published_at = parse_human_datetime(published_raw, run_dt) or parse_date_like(published_raw)
        detail_summary = summary or title
        if publisher:
            detail_summary = f"{publisher}：{detail_summary}"
        items.append(
            {
                "title": title,
                "summary": detail_summary,
                "body_text": detail_summary,
                "url": url,
                "canonical_url": url,
                "published_at": published_at,
            }
        )
    return limit_items(items, source)


def load_json_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def normalize_company_name(value: str | None) -> str:
    return WHITESPACE_RE.sub(" ", str(value or "").replace("\u3000", " ").strip())


def infer_region_from_ticker(ticker: str) -> str | None:
    clean = str(ticker or "").strip().upper()
    if clean.endswith(".HK"):
        return "HK"
    if clean.endswith(".SH") or clean.endswith(".SZ"):
        return "CN"
    return None


def build_watchlist_targets(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    targets: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            status = str(row.get("status") or "").strip().lower()
            if status not in {"", "active"}:
                continue
            ticker = str(row.get("ticker") or "").strip().upper()
            name = normalize_company_name(row.get("name"))
            if not ticker or not name:
                continue
            region = infer_region_from_ticker(ticker)
            if region is None:
                continue
            code = ticker.split(".", 1)[0]
            targets.append(
                {
                    "ticker": ticker,
                    "name": name,
                    "region": region,
                    "code": code.zfill(5) if region == "HK" else code.zfill(6),
                }
            )
    return targets


def build_feed_targets(export_root: Path) -> list[dict[str, Any]]:
    research_feed = load_json_file(export_root / "research_feed_latest.json")
    opportunity_feed = load_json_file(export_root / "opportunity_report_feed_latest.json")
    names: list[str] = []
    for name in (research_feed.get("entity_index") or {}).keys():
        clean = normalize_company_name(name)
        if clean:
            names.append(clean)
    for bucket in ("new_opportunity_candidates", "tracking_updates", "watchlist_candidates"):
        for row in (opportunity_feed.get("opportunity_buckets") or {}).get(bucket, []) or []:
            for candidate in row.get("companies") or []:
                clean = normalize_company_name(candidate)
                if clean:
                    names.append(clean)
            primary_entity = normalize_company_name(row.get("primary_entity"))
            if primary_entity:
                names.append(primary_entity)
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for name in names:
        if name in seen:
            continue
        seen.add(name)
        deduped.append({"name": name})
    return deduped


def build_explicit_targets(source: dict[str, Any]) -> list[dict[str, Any]]:
    raw_targets = source.get("target_names") or source.get("explicit_targets") or []
    if isinstance(raw_targets, str):
        raw_targets = [raw_targets]
    targets: list[dict[str, Any]] = []
    for entry in raw_targets:
        if isinstance(entry, dict):
            name = normalize_company_name(entry.get("name"))
            ticker = str(entry.get("ticker") or "").strip().upper()
            region = str(entry.get("region") or "").strip().upper() or infer_region_from_ticker(ticker) or ""
        else:
            name = normalize_company_name(entry)
            ticker = ""
            region = ""
        if not name:
            continue
        code = ""
        if ticker:
            code_raw = ticker.split(".", 1)[0]
            if region == "HK":
                code = code_raw.zfill(5)
            elif region == "CN":
                code = code_raw.zfill(6)
            else:
                code = code_raw
        targets.append({"name": name, "ticker": ticker, "region": region, "code": code, "explicit": True})
    return targets


def merge_named_targets(*target_groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    for group in target_groups:
        for row in group:
            name = normalize_company_name(row.get("name"))
            if not name or name in seen_names:
                continue
            seen_names.add(name)
            normalized = dict(row)
            normalized["name"] = name
            merged.append(normalized)
    return merged


def build_social_search_targets(source: dict[str, Any], watchlist_targets: list[dict[str, Any]], export_root: Path) -> list[dict[str, Any]]:
    require_chinese = bool(source.get("require_chinese_name", True))
    explicit_targets = build_explicit_targets(source)
    watchlist_names = [
        {"name": row["name"], "ticker": row["ticker"], "region": row["region"], "explicit": False}
        for row in watchlist_targets
        if row.get("region") in {"CN", "HK", "US"} and row.get("name")
    ]
    feed_targets = [{**row, "explicit": False} for row in build_feed_targets(export_root)]
    merged: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    for row in explicit_targets + watchlist_names + feed_targets:
        name = normalize_company_name(row.get("name"))
        if not name or name in seen_names:
            continue
        if require_chinese and not row.get("explicit") and not re.search(r"[\u4e00-\u9fff]", name):
            continue
        seen_names.add(name)
        merged.append(
            {
                "name": name,
                "ticker": str(row.get("ticker") or "").strip().upper(),
                "region": str(row.get("region") or "").strip().upper(),
            }
        )
    max_targets = int(source.get("max_targets") or 8)
    return merged[:max_targets]


def resolve_shared_targets(source: dict[str, Any], export_root: Path, watchlist_registry: Path) -> list[dict[str, Any]]:
    source_type = str(source.get("type") or "").strip()
    watchlist_targets = build_watchlist_targets(watchlist_registry)
    explicit_targets = build_explicit_targets(source)
    if source_type == "hkex_tracked":
        explicit_hk = [row for row in explicit_targets if row.get("region") == "HK" and row.get("code")]
        watchlist_hk = [row for row in watchlist_targets if row.get("region") == "HK"]
        return merge_named_targets(explicit_hk, watchlist_hk)
    if source_type == "guba_tracked_html":
        explicit_cn = [row for row in explicit_targets if row.get("region") == "CN" and row.get("code")]
        watchlist_cn = [row for row in watchlist_targets if row.get("region") == "CN"]
        return merge_named_targets(explicit_cn, watchlist_cn)
    if source_type in {"weibo_mobile_search", "xueqiu_status_search", "xueqiu_dom_search", "xiaohongshu_web_search"}:
        return build_social_search_targets(source, watchlist_targets, export_root)
    if source_type in {"reddit_search_json", "serpstack_search_json"}:
        source = dict(source)
        source["require_chinese_name"] = False
        return build_social_search_targets(source, watchlist_targets, export_root)
    return []


def build_bing_rss_url(query: str) -> str:
    return f"https://www.bing.com/news/search?q={quote(query)}&format=rss"


def decode_response_text(response: requests.Response) -> str:
    candidates = [
        "utf-8-sig",
        "utf-8",
        response.encoding,
        "windows-1252",
    ]
    for encoding in candidates:
        if not encoding:
            continue
        try:
            return response.content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return response.text


class FeedResponseError(ValueError):
    """Raised when a declared feed source returns non-feed content."""


def parse_feed_xml(xml_text: str, *, feed_kind: str) -> ET.Element:
    clean = str(xml_text or "").lstrip("\ufeff").strip()
    if not clean:
        raise FeedResponseError(f"quarantine_empty_{feed_kind}_response")
    prefix = clean[:120].replace("\n", " ").replace("\r", " ")
    lower_prefix = prefix.lower()
    if lower_prefix.startswith("<!doctype html") or lower_prefix.startswith("<html") or "<html" in lower_prefix[:80]:
        raise FeedResponseError(f"quarantine_non_xml_{feed_kind}_response: html page returned")
    if not clean.startswith("<"):
        raise FeedResponseError(f"quarantine_non_xml_{feed_kind}_response: prefix={prefix[:80]}")
    try:
        return ET.fromstring(clean)
    except ET.ParseError as exc:
        raise FeedResponseError(f"quarantine_invalid_{feed_kind}_xml: {exc}") from exc


def resolve_user_agent(source: dict[str, Any]) -> str:
    user_agent = str(source.get("user_agent") or "").strip()
    if source.get("type") == "sec_atom":
        contact = str(source.get("contact_email") or "research@example.com").strip()
        if user_agent:
            return user_agent.replace("research@example.com", contact)
        return f"PersonalInvestmentResearchBot/1.0 (contact: {contact})"
    return user_agent or "Mozilla/5.0"


def load_registry(path: Path) -> dict[str, dict[str, Any]]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    rows = payload.get("sources")
    if not isinstance(rows, list):
        raise SystemExit(f"registry file is missing a top-level 'sources' list: {path}")
    registry: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        source_id = str(row.get("source_id") or "").strip()
        if source_id:
            registry[source_id] = row
    return registry


def load_catalog(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("sources")
    if not isinstance(rows, list):
        raise SystemExit(f"catalog file is missing a top-level 'sources' list: {path}")
    return [row for row in rows if isinstance(row, dict)]


def source_env_enabled(source: dict[str, Any]) -> bool:
    env_name = str(source.get("enabled_if_env") or "").strip()
    if not env_name:
        return True
    return bool(os.environ.get(env_name, "").strip())


def merge_sources(
    registry: dict[str, dict[str, Any]],
    catalog_rows: list[dict[str, Any]],
    scheduler_classes: set[str] | None,
    source_ids: set[str] | None,
) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    for row in catalog_rows:
        key = str(row.get("key") or "").strip()
        if not key:
            continue
        reg = registry.get(key)
        if not reg:
            continue
        family = str(reg.get("source_family") or "").strip()
        if key in BLOCKED_SOURCE_IDS or family in BLOCKED_SOURCE_FAMILIES:
            continue
        if not bool(reg.get("enabled")):
            continue
        if str(reg.get("phase1_disposition") or "").strip() not in {"migrate_phase1", "compat_keep"}:
            continue
        scheduler_class = str(reg.get("scheduler_class") or "").strip()
        if scheduler_classes and scheduler_class not in scheduler_classes:
            continue
        if source_ids and key not in source_ids:
            continue
        candidate = {
            **reg,
            **row,
            "source_id": key,
            "scheduler_class": scheduler_class,
        }
        if not source_env_enabled(candidate):
            continue
        merged.append(
            candidate
        )
    return merged


def apply_schema(conn: sqlite3.Connection, schema_path: Path) -> None:
    conn.executescript(schema_path.read_text(encoding="utf-8"))


def sync_registry_to_db(conn: sqlite3.Connection, registry: dict[str, dict[str, Any]]) -> None:
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
    rows: list[tuple[Any, ...]] = []
    for source_id, item in registry.items():
        rows.append(
            (
                source_id,
                str(item.get("name") or source_id),
                str(item.get("lane") or "confirmation"),
                str(item.get("source_family") or ""),
                str(item.get("source_type") or "scrape"),
                int(item.get("trust_tier") or 2),
                str(item.get("coverage_scope") or "mixed"),
                str(item.get("collector_owner") or "shared"),
                str(item.get("scheduler_class") or "daily"),
                str(item.get("origin_system") or "news_event_hub"),
                str(item.get("legacy_key") or source_id),
                str(item.get("phase1_disposition") or "migrate_phase1"),
                1 if bool(item.get("enabled")) else 0,
                str(item.get("description") or ""),
            )
        )
    conn.executemany(sql, rows)


def ensure_bootstrap(conn: sqlite3.Connection, schema_path: Path, registry: dict[str, dict[str, Any]]) -> None:
    apply_schema(conn, schema_path)
    ensure_runtime_indexes(conn)
    sync_registry_to_db(conn, registry)


def matches_any_term(text: str | None, terms: list[str] | tuple[str, ...] | None) -> bool:
    clean = str(text or "").strip().lower()
    if not clean or not terms:
        return False
    return any(str(term).strip().lower() in clean for term in terms if str(term).strip())


def rss_item_allowed(payload: dict[str, str], source: dict[str, Any]) -> bool:
    publisher = payload.get("Source") or payload.get("source") or str(source.get("publisher") or source.get("name") or "")
    title = payload.get("title") or ""
    summary = strip_html(payload.get("description", ""))
    if source.get("publisher_allow_terms") and not matches_any_term(publisher, source.get("publisher_allow_terms")):
        return False
    if source.get("publisher_block_terms") and matches_any_term(publisher, source.get("publisher_block_terms")):
        return False
    if source.get("title_allow_terms") and not matches_any_term(title, source.get("title_allow_terms")):
        return False
    if source.get("title_block_terms") and matches_any_term(title, source.get("title_block_terms")):
        return False
    if source.get("summary_allow_terms") and not matches_any_term(summary, source.get("summary_allow_terms")):
        return False
    if source.get("summary_block_terms") and matches_any_term(summary, source.get("summary_block_terms")):
        return False
    return True


def parse_marketaux_items(payload: dict[str, Any], source: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for record in payload.get("data", []) or []:
        if not isinstance(record, dict):
            continue
        url = str(record.get("url") or record.get("article_url") or "").strip()
        title = str(record.get("title") or "").strip()
        if not title or not url:
            continue
        canonical_url = normalize_url(url)
        if not canonical_url:
            continue
        description = strip_html(str(record.get("description") or record.get("snippet") or record.get("summary") or ""))
        source_field = record.get("source")
        if isinstance(source_field, dict):
            publisher = (
                str(source_field.get("name") or "").strip()
                or str(source_field.get("title") or "").strip()
                or str(source.get("publisher") or source.get("name") or "").strip()
            )
        else:
            publisher = str(source_field or source.get("publisher") or source.get("name") or "").strip()
        entities = record.get("entities") if isinstance(record.get("entities"), list) else []
        has_entities = any(isinstance(entity, dict) and (entity.get("symbol") or entity.get("name")) for entity in entities)
        summary = description or title
        if publisher and summary and publisher.lower() not in summary.lower():
            summary = f"{publisher}：{summary}"
        items.append(
            {
                "title": title,
                "summary": summary,
                "body_text": description or summary,
                "url": url,
                "canonical_url": canonical_url,
                "published_at": parse_datetime(record.get("published_at") or record.get("published") or record.get("updated_at")),
                "timestamp_quality": "exact" if record.get("published_at") or record.get("published") or record.get("updated_at") else "unknown",
                "intent": "company" if has_entities else str(source.get("intent") or "mixed"),
            }
        )
    return limit_items(items, source)


def parse_mediastack_items(payload: dict[str, Any], source: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for record in payload.get("data", []) or []:
        if not isinstance(record, dict):
            continue
        title = strip_html(record.get("title"))
        url = str(record.get("url") or "").strip()
        if not title or not url:
            continue
        canonical_url = normalize_url(url)
        if not canonical_url:
            continue
        description = strip_html(record.get("description") or "")
        publisher = str(record.get("source") or source.get("publisher") or source.get("name") or "").strip()
        summary = description or title
        if publisher and summary and publisher.lower() not in summary.lower():
            summary = f"{publisher}：{summary}"
        items.append(
            {
                "title": title,
                "summary": summary,
                "body_text": description or summary,
                "url": url,
                "canonical_url": canonical_url,
                "published_at": parse_datetime(record.get("published_at") or record.get("published") or record.get("date")),
                "timestamp_quality": "exact" if record.get("published_at") or record.get("published") or record.get("date") else "unknown",
                "intent": str(source.get("intent") or "mixed"),
            }
        )
    return limit_items(items, source)


def build_templated_query(template: str | None, target: dict[str, Any]) -> str:
    clean_template = str(template or "").strip()
    target_name = normalize_company_name(target.get("name"))
    ticker = str(target.get("ticker") or "").strip().upper()
    region = str(target.get("region") or "").strip().upper()
    code = ticker.split(".", 1)[0] if ticker else ""
    if clean_template:
        query = (
            clean_template.replace("{target}", target_name)
            .replace("{ticker}", ticker)
            .replace("{code}", code)
            .replace("{region}", region)
        )
        return WHITESPACE_RE.sub(" ", query).strip()
    return target_name


def parse_serpstack_items(payload: dict[str, Any], source: dict[str, Any], target: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    target_name = normalize_company_name(target.get("name"))
    candidates = payload.get("news_results") or payload.get("organic_results") or []
    if not isinstance(candidates, list):
        return []
    for record in candidates:
        if not isinstance(record, dict):
            continue
        title = strip_html(record.get("title"))
        url = str(record.get("url") or record.get("link") or "").strip()
        if not title or not url:
            continue
        canonical_url = normalize_url(url)
        if not canonical_url:
            continue
        host = urlparse(canonical_url).netloc.replace("www.", "")
        snippet = strip_html(record.get("snippet") or record.get("description") or "")
        summary = snippet or title
        if target_name:
            summary = f"Serpstack 搜索线索：{target_name} {summary}".strip()
        if host and host.lower() not in summary.lower():
            summary = f"{host}：{summary}"
        items.append(
            {
                "title": title,
                "summary": summary,
                "body_text": snippet or summary,
                "url": url,
                "canonical_url": canonical_url,
                "published_at": parse_datetime(record.get("date") or record.get("published_at")),
                "timestamp_quality": "exact" if record.get("date") or record.get("published_at") else "unknown",
                "intent": str(source.get("intent") or "company"),
            }
        )
    max_items_per_target = int(source.get("max_items_per_target") or 0)
    if max_items_per_target > 0:
        return items[:max_items_per_target]
    return items


def parse_rss_items(xml_text: str, source: dict[str, Any]) -> list[dict[str, Any]]:
    root = parse_feed_xml(xml_text, feed_kind="rss")
    items: list[dict[str, Any]] = []
    for item in root.findall("./channel/item"):
        payload = {child.tag.split("}", 1)[-1]: (child.text or "").strip() for child in item}
        if not rss_item_allowed(payload, source):
            continue
        raw_link = payload.get("link") or payload.get("guid") or ""
        url, canonical_url = canonicalize_link(raw_link)
        if not url:
            continue
        title = strip_html(payload.get("title", ""))
        summary = strip_html(payload.get("description", ""))
        items.append(
            {
                "title": title,
                "summary": summary,
                "body_text": summary,
                "url": url,
                "canonical_url": canonical_url,
                "published_at": parse_datetime(payload.get("pubDate")),
            }
        )
    return items


def parse_atom_items(xml_text: str, source: dict[str, Any]) -> list[dict[str, Any]]:
    root = parse_feed_xml(xml_text, feed_kind="atom")
    items: list[dict[str, Any]] = []
    for entry in root.findall("./atom:entry", ATOM_NS):
        title = strip_html(entry.findtext("atom:title", default="", namespaces=ATOM_NS))
        link_el = entry.find("atom:link[@rel='alternate']", ATOM_NS)
        if link_el is None:
            link_el = entry.find("atom:link", ATOM_NS)
        link = link_el.attrib.get("href", "").strip() if link_el is not None else ""
        summary = strip_html(entry.findtext("atom:summary", default="", namespaces=ATOM_NS))
        updated = entry.findtext("atom:updated", default="", namespaces=ATOM_NS)
        url, canonical_url = canonicalize_link(link)
        if not url:
            continue
        items.append(
            {
                "title": title,
                "summary": summary,
                "body_text": summary,
                "url": url,
                "canonical_url": canonical_url,
                "published_at": parse_datetime(updated),
            }
        )
    return limit_items(items, source)


def parse_govcn_json_items(payload: list[dict[str, Any]], source: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for record in payload or []:
        title = str(record.get("TITLE") or "").strip()
        url = normalize_url(str(record.get("URL") or "").strip())
        if not title or not url:
            continue
        subtitle = str(record.get("SUB_TITLE") or "").strip()
        summary = f"{source['name']}：{title}"
        if subtitle:
            summary = f"{summary} {subtitle}"
        items.append(
            {
                "title": title,
                "summary": summary,
                "body_text": summary,
                "url": url,
                "canonical_url": normalize_url(url),
                "published_at": parse_cn_date(record.get("DOCRELPUBTIME")),
            }
        )
    return items


def parse_cninfo_items(payload: dict[str, Any], source: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for record in payload.get("announcements") or []:
        sec_name = str(record.get("secName") or "").strip()
        short_title = str(record.get("shortTitle") or record.get("announcementTitle") or "").strip()
        adjunct_url = str(record.get("adjunctUrl") or "").lstrip("/")
        if not sec_name or not short_title or not adjunct_url:
            continue
        url = normalize_url(f"https://static.cninfo.com.cn/{adjunct_url}")
        if not url:
            continue
        title = f"{sec_name}：{short_title}"
        items.append(
            {
                "title": title,
                "summary": f"CNINFO公告：{sec_name} 发布《{short_title}》。",
                "body_text": f"CNINFO公告：{sec_name} 发布《{short_title}》。",
                "url": url,
                "canonical_url": url,
                "published_at": parse_human_datetime(str(record.get("announcementTime") or ""), utc_now()),
            }
        )
    return items


def parse_reddit_listing_items(payload: dict[str, Any], source: dict[str, Any], subreddit: str) -> list[dict[str, Any]]:
    rows = ((payload or {}).get("data") or {}).get("children") or []
    max_items = int(source.get("max_items_per_subreddit") or source.get("max_items") or 8)
    exclude_title_re = None
    if source.get("exclude_title_regex"):
        exclude_title_re = re.compile(str(source.get("exclude_title_regex") or ""), re.IGNORECASE)
    min_score = int(source.get("min_score") or 0)
    min_comments = int(source.get("min_comments") or 0)
    items: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        entry = row.get("data") or {}
        if not isinstance(entry, dict):
            continue
        if entry.get("stickied"):
            continue
        title = strip_html(str(entry.get("title") or ""))
        if not title:
            continue
        if exclude_title_re and exclude_title_re.search(title):
            continue
        score = int(entry.get("ups") or 0)
        comments = int(entry.get("num_comments") or 0)
        if min_score or min_comments:
            if score < min_score and comments < min_comments:
                continue
        permalink = str(entry.get("permalink") or "").strip()
        if not permalink:
            continue
        canonical_url = normalize_url(urljoin("https://www.reddit.com", permalink))
        author = str(entry.get("author") or "reddit_user").strip()
        flair = str(entry.get("link_flair_text") or "").strip()
        published_at = None
        created_utc = entry.get("created_utc")
        if created_utc is not None:
            with contextlib.suppress(TypeError, ValueError, OSError):
                published_at = datetime.fromtimestamp(float(created_utc), tz=timezone.utc).isoformat(timespec="seconds")
        body_text = strip_html(str(entry.get("selftext") or ""))
        outbound_url = normalize_url(str(entry.get("url_overridden_by_dest") or entry.get("url") or "").strip())
        if outbound_url and outbound_url != canonical_url:
            link_note = f"Outbound link: {outbound_url}"
            body_text = f"{body_text}\n{link_note}".strip() if body_text else link_note
        summary_parts = [f"Reddit r/{subreddit}", f"u/{author}", f"{score} upvotes", f"{comments} comments"]
        if flair:
            summary_parts.append(f"flair={flair}")
        items.append(
            {
                "title": title,
                "summary": " | ".join(summary_parts),
                "body_text": body_text,
                "url": canonical_url,
                "canonical_url": canonical_url,
                "published_at": published_at,
            }
        )
        if len(items) >= max_items:
            break
    return items


def parse_reddit_search_items(
    payload: dict[str, Any],
    source: dict[str, Any],
    target: dict[str, Any],
) -> list[dict[str, Any]]:
    rows = ((payload or {}).get("data") or {}).get("children") or []
    max_items = int(source.get("max_items_per_target") or source.get("max_items") or 4)
    min_score = int(source.get("min_score") or 0)
    min_comments = int(source.get("min_comments") or 0)
    query = normalize_company_name(target.get("name"))
    items: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        entry = row.get("data") or {}
        if not isinstance(entry, dict):
            continue
        title = strip_html(str(entry.get("title") or ""))
        body_text = strip_html(str(entry.get("selftext") or ""))
        combined = f"{title} {body_text}".strip()
        if query and query.lower() not in combined.lower():
            continue
        permalink = str(entry.get("permalink") or "").strip()
        if not permalink:
            continue
        score = int(entry.get("ups") or 0)
        comments = int(entry.get("num_comments") or 0)
        if min_score or min_comments:
            if score < min_score and comments < min_comments:
                continue
        canonical_url = normalize_url(urljoin("https://www.reddit.com", permalink))
        author = str(entry.get("author") or "reddit_user").strip()
        subreddit = str(entry.get("subreddit") or "").strip()
        flair = str(entry.get("link_flair_text") or "").strip()
        published_at = None
        created_utc = entry.get("created_utc")
        if created_utc is not None:
            with contextlib.suppress(TypeError, ValueError, OSError):
                published_at = datetime.fromtimestamp(float(created_utc), tz=timezone.utc).isoformat(timespec="seconds")
        outbound_url = normalize_url(str(entry.get("url_overridden_by_dest") or entry.get("url") or "").strip())
        if outbound_url and outbound_url != canonical_url:
            link_note = f"Outbound link: {outbound_url}"
            body_text = f"{body_text}\n{link_note}".strip() if body_text else link_note
        summary_parts = [f"Reddit 搜索线索：{query}", f"r/{subreddit}", f"u/{author}", f"{score} upvotes", f"{comments} comments"]
        if flair:
            summary_parts.append(f"flair={flair}")
        items.append(
            {
                "title": title,
                "summary": " | ".join(summary_parts),
                "body_text": body_text or title,
                "url": canonical_url,
                "canonical_url": canonical_url,
                "published_at": published_at,
            }
        )
        if len(items) >= max_items:
            break
    return items


def parse_jsonp_payload(text: str) -> dict[str, Any]:
    match = re.search(r"callback\((.*)\)\s*;?\s*$", text.strip(), re.S)
    if not match:
        raise ValueError("invalid JSONP payload")
    payload = json.loads(match.group(1))
    return payload if isinstance(payload, dict) else {}


def parse_hkex_datetime(value: str | None) -> str | None:
    clean = str(value or "").strip()
    if not clean:
        return None
    try:
        parsed = datetime.strptime(clean, "%d/%m/%Y %H:%M").replace(tzinfo=HK_TZ)
    except ValueError:
        return None
    return parsed.astimezone(timezone.utc).isoformat(timespec="seconds")


def resolve_hkex_stock_id(session: requests.Session, code: str, name: str | None, market: str) -> tuple[str | None, str | None]:
    candidates = [code, code.lstrip("0") or code]
    if name:
        candidates.append(name)
    headers = {"User-Agent": "Mozilla/5.0"}
    for query in candidates:
        try:
            response = session.get(
                HKEX_PARTIAL_URL,
                params={"lang": "EN", "type": "A", "name": query, "market": market, "callback": "callback"},
                headers=headers,
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            payload = parse_jsonp_payload(response.text)
        except Exception:
            continue
        for item in payload.get("stockInfo", []) or []:
            item_code = str(item.get("code") or "").zfill(5)
            if item_code == code:
                return str(item.get("stockId") or ""), str(item.get("name") or name or "")
    return None, None


def parse_hkex_items(payload: dict[str, Any], source: dict[str, Any], tracked_name: str) -> list[dict[str, Any]]:
    try:
        rows = json.loads(str(payload.get("result") or "[]"))
    except json.JSONDecodeError:
        return []
    items: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        file_link = str(row.get("FILE_LINK") or "").strip()
        if not file_link:
            continue
        url = normalize_url(file_link if file_link.startswith("http") else f"https://www1.hkexnews.hk{file_link}")
        title = html.unescape(str(row.get("TITLE") or "").strip())
        if not title or not url:
            continue
        stock_name = html.unescape(str(row.get("STOCK_NAME") or tracked_name or "")).replace("<br/>", " / ").strip()
        short_text = html.unescape(str(row.get("SHORT_TEXT") or "").replace("<br/>", " ").strip())
        long_text = html.unescape(str(row.get("LONG_TEXT") or "").replace("<br/>", " ").strip())
        items.append(
            {
                "title": f"{stock_name}: {title}" if stock_name else title,
                "summary": f"HKEX公告：{short_text or long_text or title}",
                "body_text": short_text or long_text or title,
                "url": url,
                "canonical_url": url,
                "published_at": parse_hkex_datetime(row.get("DATE_TIME")),
            }
        )
    return items


def guba_title_allowed(title: str, author: str) -> bool:
    clean_title = " ".join(str(title or "").split())
    clean_author = " ".join(str(author or "").split())
    if not clean_title:
        return False
    if GUBA_DISCOVERY_NOISE_RE.search(clean_title):
        return False
    if any(token in clean_author for token in ("资讯", "研报")):
        return False
    return bool(GUBA_DISCOVERY_TITLE_RE.search(clean_title))


def parse_guba_tracked_items(html_text: str, source: dict[str, Any], tracked_company: dict[str, Any]) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html_text, "lxml")
    rows = soup.select("tbody.listbody tr.listitem")
    max_items = int(source.get("max_items_per_board", 6))
    base_url = str(source.get("base_url") or source.get("url") or "https://guba.eastmoney.com/")
    items: list[dict[str, Any]] = []
    for row in rows:
        title_node = row.select_one("td .title a")
        if title_node is None:
            continue
        title = html_node_text(title_node)
        url = normalize_url(urljoin(base_url, str(title_node.get("href") or "")))
        author = html_node_text(row.select_one("td .author a"))
        if not title or not url or not guba_title_allowed(title, author):
            continue
        read_text = html_node_text(row.select_one("td .read"))
        reply_text = html_node_text(row.select_one("td .reply"))
        try:
            read_count = int(read_text or "0")
        except ValueError:
            read_count = 0
        try:
            reply_count = int(reply_text or "0")
        except ValueError:
            reply_count = 0
        items.append(
            {
                "title": title,
                "summary": f"股吧讨论线索：{tracked_company['name']}，作者 {author or '未知'}，阅读 {read_count}，评论 {reply_count}",
                "body_text": title,
                "url": url,
                "canonical_url": url,
                "published_at": None,
            }
        )
        if len(items) >= max_items:
            break
    deduped = {item["url"]: item for item in items}
    return list(deduped.values())


def domain_matches(domain: str, allowed_domain_terms: tuple[str, ...]) -> bool:
    normalized = domain.lstrip(".").lower()
    if not normalized:
        return False
    for term in allowed_domain_terms:
        clean = str(term or "").strip().lstrip(".").lower()
        if not clean:
            continue
        if normalized == clean or normalized.endswith(f".{clean}"):
            return True
    return False


def load_storage_state_cookies(path: Path, allowed_domain_terms: tuple[str, ...], default_domain: str = "") -> list[dict[str, str]]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    raw_cookies = payload.get("cookies") if isinstance(payload, dict) else payload
    if not isinstance(raw_cookies, list):
        return []
    cookies: list[dict[str, str]] = []
    for item in raw_cookies:
        if not isinstance(item, dict):
            continue
        domain = str(item.get("domain") or "")
        if allowed_domain_terms and not domain_matches(domain, allowed_domain_terms):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        cookies.append(
            {
                "name": name,
                "value": str(item.get("value") or ""),
                "domain": domain or default_domain,
                "path": str(item.get("path") or "/"),
            }
        )
    return cookies


def apply_cookies_to_session(session: requests.Session, cookies: list[dict[str, str]]) -> None:
    for cookie in cookies:
        session.cookies.set(cookie["name"], cookie["value"], domain=cookie.get("domain") or None, path=cookie.get("path") or "/")


def iterate_weibo_mblogs(cards: Any) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    if not isinstance(cards, list):
        return items
    for card in cards:
        if not isinstance(card, dict):
            continue
        if isinstance(card.get("mblog"), dict):
            items.append(card["mblog"])
        items.extend(iterate_weibo_mblogs(card.get("card_group")))
    return items


def weibo_target_event_window(text: str, target_name: str) -> str:
    index = text.find(target_name)
    if index == -1:
        return ""
    start = max(0, index - 80)
    end = min(len(text), index + len(target_name) + 80)
    return text[start:end]


def should_keep_weibo_post(text: str, target_name: str, keywords: tuple[str, ...], author: str) -> bool:
    clean_text = " ".join(str(text or "").split())
    if not clean_text or target_name not in clean_text:
        return False
    if WEIBO_NOISE_RE.search(clean_text):
        return False
    if len(WEIBO_BASKET_MOVE_RE.findall(clean_text)) >= 3:
        return False
    if WEIBO_GENERIC_POST_RE.search(clean_text):
        return False
    if WEIBO_SYNDICATION_RE.search(clean_text) and len(clean_text) >= 120:
        return False
    if WEIBO_OFFICIAL_REPOST_RE.search(clean_text) and not re.search(r"(据产业人士|据渠道|据传|据悉|传闻|爆料)", clean_text):
        return False
    if author and target_name in author and not WEIBO_RUMORISH_RE.search(clean_text):
        return False
    if WEIBO_MEDIA_AUTHOR_RE.search(author or "") and not WEIBO_RUMORISH_RE.search(clean_text):
        return False
    window_text = weibo_target_event_window(clean_text, target_name) or clean_text
    if WEIBO_DISCOVERY_RE.search(window_text):
        return True
    if len(clean_text) >= 180 and not WEIBO_RUMORISH_RE.search(window_text):
        return False
    lowered = window_text.lower()
    return any(keyword.lower() in lowered for keyword in keywords)


def ticker_to_xueqiu_symbol(ticker: str, region: str | None = None) -> str:
    clean = str(ticker or "").strip().upper()
    if not clean:
        return ""
    if re.fullmatch(r"(SH|SZ|HK)\d{5,6}", clean):
        return clean
    if "." in clean:
        code, suffix = clean.split(".", 1)
        suffix = suffix.upper()
        if suffix == "SZ":
            return f"SZ{code.zfill(6)}"
        if suffix == "SH":
            return f"SH{code.zfill(6)}"
        if suffix == "HK":
            return f"HK{code.zfill(5)}"
    if region == "HK" and clean.isdigit():
        return f"HK{clean.zfill(5)}"
    if region == "CN" and clean.isdigit():
        if clean.startswith(("6", "9")):
            return f"SH{clean.zfill(6)}"
        return f"SZ{clean.zfill(6)}"
    return clean


def should_keep_xueqiu_post(text: str, target_name: str, keywords: tuple[str, ...], author: str, title: str = "") -> bool:
    clean_text = " ".join(str(text or "").split())
    clean_title = " ".join(str(title or "").split())
    combined_text = f"{clean_title} {clean_text}".strip()
    if not combined_text or target_name not in combined_text:
        return False
    if WEIBO_NOISE_RE.search(combined_text):
        return False
    if len(WEIBO_BASKET_MOVE_RE.findall(combined_text)) >= 3:
        return False
    if WEIBO_GENERIC_POST_RE.search(combined_text):
        return False
    if WEIBO_SYNDICATION_RE.search(combined_text) and len(combined_text) >= 120:
        return False
    if WEIBO_OFFICIAL_REPOST_RE.search(combined_text) and not re.search(r"(据产业人士|据渠道|据传|据悉|传闻|爆料)", combined_text):
        return False
    if author and target_name in author and not WEIBO_RUMORISH_RE.search(combined_text):
        return False
    if WEIBO_MEDIA_AUTHOR_RE.search(author or "") and not WEIBO_RUMORISH_RE.search(combined_text):
        return False
    window_text = weibo_target_event_window(combined_text, target_name) or combined_text
    if WEIBO_DISCOVERY_RE.search(window_text):
        return True
    if len(combined_text) >= 180 and not WEIBO_RUMORISH_RE.search(window_text):
        return False
    lowered = window_text.lower()
    return any(keyword.lower() in lowered for keyword in keywords)


def parse_weibo_search_items(payload: dict[str, Any], source: dict[str, Any], run_dt: datetime, target: dict[str, Any], keywords: tuple[str, ...]) -> list[dict[str, Any]]:
    mblogs = iterate_weibo_mblogs(((payload.get("data") or {}) if isinstance(payload, dict) else {}).get("cards"))
    max_items = int(source.get("max_items_per_target", 4))
    items: list[dict[str, Any]] = []
    for mblog in mblogs:
        if not isinstance(mblog, dict):
            continue
        text = strip_html(str(mblog.get("text") or ""))
        user = mblog.get("user") if isinstance(mblog.get("user"), dict) else {}
        author = str(user.get("screen_name") or "微博用户").strip()
        if not should_keep_weibo_post(text, target["name"], keywords, author):
            continue
        bid = str(mblog.get("bid") or "").strip()
        status_id = str(mblog.get("id") or "").strip()
        url = normalize_url(f"https://m.weibo.cn/status/{bid or status_id}") if (bid or status_id) else "https://m.weibo.cn/"
        title = text[:80] + ("…" if len(text) > 80 else "")
        items.append(
            {
                "title": title,
                "summary": f"微博讨论线索：{target['name']}，作者 {author}，转发 {int(mblog.get('reposts_count') or 0)}，评论 {int(mblog.get('comments_count') or 0)}，点赞 {int(mblog.get('attitudes_count') or 0)}",
                "body_text": text,
                "url": url,
                "canonical_url": url,
                "published_at": parse_human_datetime(str(mblog.get("created_at") or ""), run_dt),
            }
        )
        if len(items) >= max_items:
            break
    deduped = {item["url"]: item for item in items}
    return list(deduped.values())


def parse_xueqiu_search_items(payload: dict[str, Any], source: dict[str, Any], run_dt: datetime, target: dict[str, Any], keywords: tuple[str, ...]) -> list[dict[str, Any]]:
    max_items = int(source.get("max_items_per_target", 4))
    candidates: list[Any] = []
    if isinstance(payload, dict):
        for key in ("list", "statuses", "items"):
            value = payload.get(key)
            if isinstance(value, list):
                candidates = value
                break
        if not candidates:
            nested = payload.get("data")
            if isinstance(nested, dict):
                for key in ("list", "statuses", "items"):
                    value = nested.get(key)
                    if isinstance(value, list):
                        candidates = value
                        break
    items: list[dict[str, Any]] = []
    for entry in candidates:
        if not isinstance(entry, dict):
            continue
        user = entry.get("user") if isinstance(entry.get("user"), dict) else {}
        author = str(user.get("screen_name") or user.get("name") or "雪球用户").strip()
        title = strip_html(str(entry.get("title") or ""))
        text = strip_html(str(entry.get("description") or entry.get("text") or entry.get("body") or entry.get("content") or title))
        combined = f"{title} {text}".strip()
        if not should_keep_xueqiu_post(text, target["name"], keywords, author, title=title):
            continue
        status_id = str(entry.get("id") or entry.get("status_id") or "").strip()
        user_id = str(user.get("id") or entry.get("user_id") or "").strip()
        symbol = ticker_to_xueqiu_symbol(str(target.get("ticker") or ""), target.get("region"))
        if user_id and status_id:
            url = f"https://xueqiu.com/{user_id}/{status_id}"
        elif status_id:
            url = f"https://xueqiu.com/statuses/{status_id}"
        elif symbol:
            url = f"https://xueqiu.com/S/{symbol}"
        else:
            url = "https://xueqiu.com/"
        summary = (
            f"雪球讨论线索：{target['name']}，作者 {author}，"
            f"转发 {int(entry.get('retweet_count') or entry.get('retweetCount') or 0)}，"
            f"评论 {int(entry.get('reply_count') or entry.get('comment_count') or 0)}，"
            f"点赞 {int(entry.get('like_count') or entry.get('fav_count') or 0)}"
        )
        display_title = title or (combined[:80] + ("…" if len(combined) > 80 else ""))
        items.append(
            {
                "title": display_title,
                "summary": summary,
                "body_text": combined,
                "url": url,
                "canonical_url": normalize_url(url),
                "published_at": parse_human_datetime(str(entry.get("created_at") or entry.get("createdAt") or ""), run_dt),
            }
        )
        if len(items) >= max_items:
            break
    deduped = {item["url"]: item for item in items}
    return list(deduped.values())


def parse_xueqiu_public_timeline_items(payload: dict[str, Any], source: dict[str, Any], run_dt: datetime) -> list[dict[str, Any]]:
    max_items = int(source.get("max_items") or 20)
    items: list[dict[str, Any]] = []
    for entry in payload.get("list", []) or []:
        if not isinstance(entry, dict):
            continue
        raw_post = entry.get("data")
        if isinstance(raw_post, str):
            try:
                post = json.loads(raw_post)
            except json.JSONDecodeError:
                continue
        elif isinstance(raw_post, dict):
            post = raw_post
        else:
            continue
        user = post.get("user") if isinstance(post.get("user"), dict) else {}
        author = str(user.get("screen_name") or "雪球用户").strip()
        title = strip_html(str(post.get("title") or ""))
        text = strip_html(str(post.get("text") or post.get("description") or title))
        target = str(post.get("target") or "").strip()
        url = normalize_url(urljoin("https://xueqiu.com", target)) if target else ""
        if not title and not text:
            continue
        summary = (
            f"雪球热帖线索：作者 {author}，"
            f"转发 {int(post.get('retweet_count') or 0)}，"
            f"评论 {int(post.get('reply_count') or 0)}，"
            f"点赞 {int(post.get('like_count') or 0)}"
        )
        items.append(
            {
                "title": title or (text[:80] + ("…" if len(text) > 80 else "")),
                "summary": summary,
                "body_text": text,
                "url": url,
                "canonical_url": url,
                "published_at": parse_human_datetime(str(post.get("created_at") or ""), run_dt),
            }
        )
        if len(items) >= max_items:
            break
    deduped = {item["canonical_url"] or item["title"]: item for item in items}
    return list(deduped.values())


def parse_xueqiu_hot_stock_items(payload: dict[str, Any], source: dict[str, Any], run_dt: datetime) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    for rank, entry in enumerate((data.get("items") or [])[: int(source.get("max_items") or 20)], start=1):
        if not isinstance(entry, dict):
            continue
        symbol = str(entry.get("symbol") or entry.get("code") or "").strip()
        name = str(entry.get("name") or symbol).strip()
        if not symbol and not name:
            continue
        url = normalize_url(f"https://xueqiu.com/S/{symbol}") if symbol else "https://xueqiu.com/"
        current = entry.get("current")
        percent = entry.get("percent")
        summary_parts = [f"雪球热股榜第 {rank} 位", f"关注度 {entry.get('value') or 0:g}"]
        if current is not None:
            summary_parts.append(f"现价 {current}")
        if percent is not None:
            summary_parts.append(f"涨跌幅 {percent}%")
        items.append(
            {
                "title": f"雪球热股榜：{name}",
                "summary": "，".join(summary_parts),
                "body_text": json.dumps(entry, ensure_ascii=False),
                "url": url,
                "canonical_url": url,
                "published_at": isoformat_utc(run_dt),
                "timestamp_quality": "unknown",
            }
        )
    return items


def parse_cls_telegraph_items(html_text: str, source: dict[str, Any], run_dt: datetime) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    max_items = int(source.get("max_items", 80) or 80)
    for match in CLS_PATTERN.finditer(html_text):
        cls_id = match.group("id")
        if cls_id in seen_ids:
            continue
        seen_ids.add(cls_id)
        brief = decode_embedded_json_string(match.group("brief"))
        url = normalize_url(decode_embedded_json_string(match.group("shareurl")))
        if not brief or not url:
            continue
        items.append(
            {
                "title": brief,
                "summary": brief,
                "body_text": brief,
                "url": url,
                "canonical_url": normalize_url(url),
                "published_at": parse_human_datetime(match.group("ctime"), run_dt),
            }
        )
        if len(items) >= max_items:
            break
    return items


def limit_items(items: list[dict[str, Any]], source: dict[str, Any]) -> list[dict[str, Any]]:
    max_items = int(source.get("max_items", 0) or 0)
    if max_items <= 0:
        return items
    return items[:max_items]


def akshare_records(frame: Any) -> list[dict[str, Any]]:
    if frame is None:
        return []
    cleaned = frame.fillna("") if hasattr(frame, "fillna") else frame
    if hasattr(cleaned, "to_dict"):
        records = cleaned.to_dict(orient="records")
        return [row for row in records if isinstance(row, dict)]
    return []


def call_akshare(function: Any, **kwargs: Any) -> Any:
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return function(**kwargs)


def build_akshare_news_cctv_items(records: list[dict[str, Any]], source: dict[str, Any], run_dt: datetime) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for record in records:
        title = strip_html(record.get("title"))
        content = strip_html(record.get("content"))
        if not title:
            continue
        items.append(
            {
                "title": title,
                "summary": content or title,
                "body_text": content or title,
                "url": "",
                "canonical_url": "",
                "published_at": parse_china_datetime_fields(record.get("date"), "", run_dt),
                "timestamp_quality": "estimated",
            }
        )
    return limit_items(items, source)


def build_akshare_stock_info_global_cls_items(records: list[dict[str, Any]], source: dict[str, Any], run_dt: datetime) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for record in records:
        title = strip_html(record.get("标题"))
        content = strip_html(record.get("内容"))
        if not title:
            continue
        items.append(
            {
                "title": title,
                "summary": content or title,
                "body_text": content or title,
                "url": "",
                "canonical_url": "",
                "published_at": parse_china_datetime_fields(record.get("发布日期"), record.get("发布时间"), run_dt),
                "timestamp_quality": "exact",
            }
        )
    return limit_items(items, source)


def build_akshare_stock_info_global_em_items(records: list[dict[str, Any]], source: dict[str, Any], run_dt: datetime) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for record in records:
        title = strip_html(record.get("标题"))
        summary = strip_html(record.get("摘要"))
        url = normalize_url(str(record.get("链接") or "").strip())
        if not title:
            continue
        items.append(
            {
                "title": title,
                "summary": summary or title,
                "body_text": summary or title,
                "url": url,
                "canonical_url": url,
                "published_at": parse_china_datetime_fields("", record.get("发布时间"), run_dt),
                "timestamp_quality": "exact",
            }
        )
    return limit_items(items, source)


def build_akshare_stock_info_global_ths_items(records: list[dict[str, Any]], source: dict[str, Any], run_dt: datetime) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for record in records:
        title = strip_html(record.get("标题"))
        summary = strip_html(record.get("内容"))
        url = normalize_url(str(record.get("链接") or "").strip())
        if not title:
            continue
        items.append(
            {
                "title": title,
                "summary": summary or title,
                "body_text": summary or title,
                "url": url,
                "canonical_url": url,
                "published_at": parse_china_datetime_fields("", record.get("发布时间"), run_dt),
                "timestamp_quality": "exact",
            }
        )
    return limit_items(items, source)


def build_akshare_stock_notice_report_items(records: list[dict[str, Any]], source: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for record in records:
        company = strip_html(record.get("名称"))
        title_text = strip_html(record.get("公告标题"))
        notice_type = strip_html(record.get("公告类型"))
        url = normalize_url(str(record.get("网址") or "").strip())
        if not title_text:
            continue
        title = f"{company}：{title_text}" if company else title_text
        summary_parts = ["东方财富公告快报"]
        if company:
            summary_parts.append(company)
        if notice_type:
            summary_parts.append(notice_type)
        summary_parts.append(title_text)
        summary = "：".join(summary_parts[:2]) if len(summary_parts) >= 2 else summary_parts[0]
        if len(summary_parts) > 2:
            summary = f"{summary} { ' '.join(summary_parts[2:]) }"
        items.append(
            {
                "title": title,
                "summary": summary,
                "body_text": summary,
                "url": url,
                "canonical_url": url,
                "published_at": parse_date_like(record.get("公告日期")),
                "timestamp_quality": "estimated",
            }
        )
    return limit_items(items, source)


def fetch_source(session: requests.Session, source: dict[str, Any], run_dt: datetime) -> tuple[list[dict[str, Any]], str | None]:
    headers = {"User-Agent": resolve_user_agent(source)}
    source_type = str(source.get("type") or "").strip()
    try:
        if source_type == "rss":
            response = session.get(str(source["url"]), headers=headers, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            return parse_rss_items(decode_response_text(response), source), None
        if source_type == "atom":
            response = session.get(str(source["url"]), headers=headers, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            xml_text = decode_response_text(response)
            return parse_atom_items(xml_text, source), None
        if source_type == "bing_news_rss":
            response = session.get(build_bing_rss_url(str(source["query"])), headers=headers, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            return parse_rss_items(decode_response_text(response), source), None
        if source_type == "reddit_subreddit_json":
            subreddits = [str(item).strip() for item in (source.get("subreddits") or []) if str(item).strip()]
            if not subreddits:
                subreddit = str(source.get("subreddit") or "").strip()
                if subreddit:
                    subreddits = [subreddit]
            listing = str(source.get("listing") or "hot").strip() or "hot"
            limit = int(source.get("limit") or 12)
            target_headers = {
                "User-Agent": resolve_user_agent(source),
                "Accept": "application/json, text/plain, */*",
            }
            items: list[dict[str, Any]] = []
            errors: list[str] = []
            for subreddit in subreddits:
                try:
                    response = session.get(
                        f"https://www.reddit.com/r/{subreddit}/{listing}.json",
                        params={"limit": str(limit), "raw_json": "1"},
                        headers=target_headers,
                        timeout=REQUEST_TIMEOUT,
                    )
                    response.raise_for_status()
                    items.extend(parse_reddit_listing_items(response.json(), source, subreddit))
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"{subreddit}:{exc}")
            deduped = {item["url"]: item for item in items}
            return list(deduped.values()), "; ".join(errors[:8]) if errors else None
        if source_type == "reddit_search_json":
            targets = resolve_shared_targets(
                source,
                Path(str(source.get("consumer_export_root") or DEFAULT_CONSUMER_EXPORT_ROOT)),
                Path(str(source.get("watchlist_registry") or DEFAULT_WATCHLIST_REGISTRY)),
            )
            limit = int(source.get("limit") or 8)
            sort = str(source.get("sort") or "new").strip() or "new"
            target_headers = {
                "User-Agent": resolve_user_agent(source),
                "Accept": "application/json, text/plain, */*",
            }
            items: list[dict[str, Any]] = []
            errors: list[str] = []
            for target in targets:
                try:
                    response = session.get(
                        "https://www.reddit.com/search.json",
                        params={"q": target["name"], "type": "link", "sort": sort, "limit": str(limit), "raw_json": "1"},
                        headers=target_headers,
                        timeout=REQUEST_TIMEOUT,
                    )
                    response.raise_for_status()
                    items.extend(parse_reddit_search_items(response.json(), source, target))
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"{target['name']}:{exc}")
            deduped = {item["url"]: item for item in items}
            return list(deduped.values()), "; ".join(errors[:8]) if errors else None
        if source_type == "sec_atom":
            response = session.get(str(source["url"]), headers=headers, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            xml_text = decode_response_text(response)
            items = parse_atom_items(xml_text, source)
            if not items:
                items = parse_rss_items(xml_text, source)
            return items, None
        if source_type == "govcn_json":
            response = session.get(str(source["url"]), headers=headers, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            return parse_govcn_json_items(response.json(), source), None
        if source_type == "marketaux_json":
            token = os.environ.get(str(source.get("enabled_if_env") or ""), "").strip()
            if not token:
                return [], None
            params = dict(source.get("query_params") or {})
            params["api_token"] = token
            if "published_after" not in params:
                days_back = int(source.get("days_back", 2))
                published_after = run_dt.astimezone(timezone.utc) - timedelta(days=days_back)
                params["published_after"] = published_after.strftime("%Y-%m-%dT%H:%M:%S")
            headers.update({"Accept": "application/json"})
            response = session.get(str(source["url"]), headers=headers, params=params, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            return parse_marketaux_items(response.json(), source), None
        if source_type == "mediastack_news":
            token = os.environ.get(str(source.get("enabled_if_env") or ""), "").strip()
            if not token:
                return [], None
            params = dict(source.get("query_params") or {})
            params["access_key"] = token
            headers.update({"Accept": "application/json", "apikey": token})
            response = session.get(str(source["url"]), headers=headers, params=params, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            return parse_mediastack_items(response.json(), source), None
        if source_type == "serpstack_search_json":
            token = os.environ.get(str(source.get("enabled_if_env") or ""), "").strip()
            if not token:
                return [], None
            targets = resolve_shared_targets(
                source,
                Path(str(source.get("consumer_export_root") or DEFAULT_CONSUMER_EXPORT_ROOT)),
                Path(str(source.get("watchlist_registry") or DEFAULT_WATCHLIST_REGISTRY)),
            )
            if not targets:
                return [], None
            items: list[dict[str, Any]] = []
            errors: list[str] = []
            base_params = dict(source.get("query_params") or {})
            query_template = str(source.get("query_template") or source.get("query") or "").strip()
            target_headers = {
                **headers,
                "Accept": "application/json",
                "apikey": token,
            }
            for target in targets:
                try:
                    params = dict(base_params)
                    params["access_key"] = token
                    params["query"] = build_templated_query(query_template, target)
                    response = session.get(str(source["url"]), headers=target_headers, params=params, timeout=REQUEST_TIMEOUT)
                    response.raise_for_status()
                    items.extend(parse_serpstack_items(response.json(), source, target))
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"{target['name']}:{exc}")
            deduped = {item["canonical_url"]: item for item in items if item.get("canonical_url")}
            return limit_items(list(deduped.values()), source), "; ".join(errors[:8]) if errors else None
        if source_type == "cninfo_latest":
            days_back = int(source.get("days_back", 2))
            start_date = (run_dt.astimezone(CHINA_TZ) - timedelta(days=days_back)).date().isoformat()
            end_date = run_dt.astimezone(CHINA_TZ).date().isoformat()
            data = {
                "pageNum": "1",
                "pageSize": str(source.get("page_size", 80)),
                "column": source.get("column", "szse"),
                "tabName": "fulltext",
                "plate": source.get("plate", "sz"),
                "searchkey": source.get("searchkey", ""),
                "secid": source.get("secid", ""),
                "category": source.get("category", CNINFO_CATEGORY),
                "seDate": f"{start_date}~{end_date}",
                "sortName": "nothing",
                "sortType": "desc",
                "isHLtitle": "true",
            }
            headers.update(
                {
                    "Referer": "https://www.cninfo.com.cn/new/commonUrl/pageOfSearch?url=disclosure/list/search&lastPath=disclosure/list/notice",
                    "X-Requested-With": "XMLHttpRequest",
                }
            )
            response = session.post(str(source["url"]), headers=headers, data=data, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            return parse_cninfo_items(response.json(), source), None
        if source_type == "html_list":
            response = session.get(str(source["url"]), headers=headers, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            return parse_html_list_items(decode_response_text(response), source, run_dt), None
        if source_type == "hkex_tracked":
            targets = resolve_shared_targets(
                source,
                Path(str(source.get("consumer_export_root") or DEFAULT_CONSUMER_EXPORT_ROOT)),
                Path(str(source.get("watchlist_registry") or DEFAULT_WATCHLIST_REGISTRY)),
            )
            market = str(source.get("market") or "SEHK")
            row_range = str(source.get("row_range") or 80)
            days_back = int(source.get("days_back", 14))
            from_date = (run_dt.astimezone(HK_TZ) - timedelta(days=days_back)).strftime("%Y%m%d")
            to_date = run_dt.astimezone(HK_TZ).strftime("%Y%m%d")
            items: list[dict[str, Any]] = []
            errors: list[str] = []
            for company in targets:
                stock_id, stock_name = resolve_hkex_stock_id(session, str(company["code"]), str(company.get("name") or ""), market)
                if not stock_id:
                    errors.append(f"{company['code']}:stock_id_not_found")
                    continue
                response = session.get(
                    HKEX_TITLE_URL,
                    params={
                        "sortDir": "0",
                        "sortByOptions": "DateTime",
                        "category": "0",
                        "market": market,
                        "stockId": stock_id,
                        "documentType": "-1",
                        "fromDate": from_date,
                        "toDate": to_date,
                        "title": "",
                        "searchType": "0",
                        "t1code": "-2",
                        "t2Gcode": "-2",
                        "t2code": "-2",
                        "rowRange": row_range,
                        "lang": "E",
                    },
                    headers={"User-Agent": "Mozilla/5.0"},
                    timeout=REQUEST_TIMEOUT,
                )
                response.raise_for_status()
                items.extend(parse_hkex_items(response.json(), source, stock_name or str(company.get("name") or company["code"])))
            deduped = {item["url"]: item for item in items}
            return list(deduped.values()), "; ".join(errors[:8]) if errors else None
        if source_type == "cls_telegraph_html":
            response = session.get(str(source["url"]), headers=headers, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            return parse_cls_telegraph_items(decode_response_text(response), source, run_dt), None
        if source_type == "akshare_news_cctv":
            if ak is None:
                raise ModuleNotFoundError("akshare is not installed")
            primary_date = run_dt.astimezone(CHINA_TZ).strftime("%Y%m%d")
            fallback_date = (run_dt.astimezone(CHINA_TZ) - timedelta(days=1)).strftime("%Y%m%d")
            for date_str in [primary_date, fallback_date]:
                records = akshare_records(call_akshare(ak.news_cctv, date=date_str))
                if records:
                    return build_akshare_news_cctv_items(records, source, run_dt), None
            return [], None
        if source_type == "akshare_stock_info_global_cls":
            if ak is None:
                raise ModuleNotFoundError("akshare is not installed")
            records = akshare_records(call_akshare(ak.stock_info_global_cls))
            return build_akshare_stock_info_global_cls_items(records, source, run_dt), None
        if source_type == "akshare_stock_info_global_em":
            if ak is None:
                raise ModuleNotFoundError("akshare is not installed")
            records = akshare_records(call_akshare(ak.stock_info_global_em))
            return build_akshare_stock_info_global_em_items(records, source, run_dt), None
        if source_type == "akshare_stock_info_global_ths":
            if ak is None:
                raise ModuleNotFoundError("akshare is not installed")
            records = akshare_records(call_akshare(ak.stock_info_global_ths))
            return build_akshare_stock_info_global_ths_items(records, source, run_dt), None
        if source_type == "akshare_stock_notice_report":
            if ak is None:
                raise ModuleNotFoundError("akshare is not installed")
            days_back = int(source.get("days_back", 2))
            symbol = str(source.get("symbol") or "全部").strip() or "全部"
            for offset in range(days_back + 1):
                date_str = (run_dt.astimezone(CHINA_TZ) - timedelta(days=offset)).strftime("%Y%m%d")
                records = akshare_records(call_akshare(ak.stock_notice_report, symbol=symbol, date=date_str))
                if records:
                    return build_akshare_stock_notice_report_items(records, source), None
            return [], None
        if source_type == "xueqiu_public_timeline":
            state_path = Path(str(source.get("storage_state_path") or DEFAULT_AGENT_REACH_STATE)).expanduser()
            cookies = load_storage_state_cookies(
                state_path,
                (".xueqiu.com", "xueqiu.com", ".stock.xueqiu.com"),
                default_domain=".xueqiu.com",
            )
            if not cookies:
                return [], f"missing_xueqiu_storage_state:{state_path}"
            apply_cookies_to_session(session, cookies)
            count = int(source.get("count") or 20)
            category = int(source.get("category") or -1)
            response = session.get(
                "https://xueqiu.com/v4/statuses/public_timeline_by_category.json",
                params={"since_id": "-1", "max_id": "-1", "count": str(count), "category": str(category)},
                headers={"User-Agent": resolve_user_agent(source), "Referer": "https://xueqiu.com/"},
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            return parse_xueqiu_public_timeline_items(response.json(), source, run_dt), None
        if source_type == "xueqiu_hot_stock":
            state_path = Path(str(source.get("storage_state_path") or DEFAULT_AGENT_REACH_STATE)).expanduser()
            cookies = load_storage_state_cookies(
                state_path,
                (".xueqiu.com", "xueqiu.com", ".stock.xueqiu.com"),
                default_domain=".xueqiu.com",
            )
            if not cookies:
                return [], f"missing_xueqiu_storage_state:{state_path}"
            apply_cookies_to_session(session, cookies)
            size = int(source.get("size") or source.get("max_items") or 20)
            stock_type = int(source.get("stock_type") or 10)
            response = session.get(
                "https://stock.xueqiu.com/v5/stock/hot_stock/list.json",
                params={"size": str(size), "type": str(stock_type)},
                headers={"User-Agent": resolve_user_agent(source), "Referer": "https://xueqiu.com/"},
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            return parse_xueqiu_hot_stock_items(response.json(), source, run_dt), None
        if source_type == "guba_tracked_html":
            targets = resolve_shared_targets(
                source,
                Path(str(source.get("consumer_export_root") or DEFAULT_CONSUMER_EXPORT_ROOT)),
                Path(str(source.get("watchlist_registry") or DEFAULT_WATCHLIST_REGISTRY)),
            )
            max_boards = int(source.get("max_boards", 12))
            items: list[dict[str, Any]] = []
            errors: list[str] = []
            for company in targets[:max_boards]:
                url = f"https://guba.eastmoney.com/list,{company['code']}.html"
                try:
                    response = session.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
                    response.raise_for_status()
                    board_source = dict(source)
                    board_source["url"] = url
                    items.extend(parse_guba_tracked_items(decode_response_text(response), board_source, company))
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"{company['code']}:{exc}")
            deduped = {item["url"]: item for item in items}
            return list(deduped.values()), "; ".join(errors[:8]) if errors else None
        if source_type == "weibo_mobile_search":
            targets = resolve_shared_targets(
                source,
                Path(str(source.get("consumer_export_root") or DEFAULT_CONSUMER_EXPORT_ROOT)),
                Path(str(source.get("watchlist_registry") or DEFAULT_WATCHLIST_REGISTRY)),
            )
            state_path = Path(str(source.get("weibo_state_path") or DEFAULT_WEIBO_STATE)).expanduser()
            cookies = load_storage_state_cookies(
                state_path,
                (".weibo.cn", "m.weibo.cn", ".weibo.com", ".sina.com.cn"),
                default_domain=".weibo.cn",
            )
            if not cookies:
                return [], f"missing_weibo_storage_state:{state_path}"
            apply_cookies_to_session(session, cookies)
            pages = int(source.get("pages") or 1)
            keywords = tuple(
                str(item).strip() for item in (source.get("keywords_cn") or DEFAULT_WEIBO_KEYWORDS) if str(item).strip()
            ) or DEFAULT_WEIBO_KEYWORDS
            target_headers = {
                "User-Agent": (
                    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
                    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1"
                ),
                "Referer": "https://m.weibo.cn/",
                "Accept": "application/json, text/plain, */*",
                "X-Requested-With": "XMLHttpRequest",
            }
            items: list[dict[str, Any]] = []
            errors: list[str] = []
            for target in targets:
                for page in range(1, pages + 1):
                    try:
                        response = session.get(
                            "https://m.weibo.cn/api/container/getIndex",
                            params={"containerid": f"100103type=1&q={target['name']}", "page_type": "searchall", "page": str(page)},
                            headers=target_headers,
                            timeout=REQUEST_TIMEOUT,
                        )
                        response.raise_for_status()
                        items.extend(parse_weibo_search_items(response.json(), source, run_dt, target, keywords))
                    except Exception as exc:  # noqa: BLE001
                        errors.append(f"{target['name']}:{exc}")
                        break
            deduped = {item["url"]: item for item in items}
            return list(deduped.values()), "; ".join(errors[:8]) if errors else None
        if source_type == "xueqiu_status_search":
            targets = resolve_shared_targets(
                source,
                Path(str(source.get("consumer_export_root") or DEFAULT_CONSUMER_EXPORT_ROOT)),
                Path(str(source.get("watchlist_registry") or DEFAULT_WATCHLIST_REGISTRY)),
            )
            state_path = Path(str(source.get("storage_state_path") or DEFAULT_AGENT_REACH_STATE)).expanduser()
            cookies = load_storage_state_cookies(
                state_path,
                (".xueqiu.com", "xueqiu.com", ".stock.xueqiu.com"),
                default_domain=".xueqiu.com",
            )
            if not cookies:
                return [], f"missing_xueqiu_storage_state:{state_path}"
            apply_cookies_to_session(session, cookies)
            pages = int(source.get("pages") or 1)
            count = int(source.get("count") or 10)
            sort = str(source.get("sort") or "time").strip() or "time"
            search_source = str(source.get("source") or "user").strip() or "user"
            keywords = tuple(
                str(item).strip() for item in (source.get("keywords_cn") or DEFAULT_XUEQIU_KEYWORDS) if str(item).strip()
            ) or DEFAULT_XUEQIU_KEYWORDS
            base_headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
                ),
                "Referer": "https://xueqiu.com/",
                "Accept": "application/json, text/plain, */*",
                "X-Requested-With": "XMLHttpRequest",
            }
            items: list[dict[str, Any]] = []
            errors: list[str] = []
            for target in targets:
                symbol = ticker_to_xueqiu_symbol(str(target.get("ticker") or ""), target.get("region"))
                target_headers = dict(base_headers)
                target_headers["Referer"] = f"https://xueqiu.com/S/{symbol}" if symbol else "https://xueqiu.com/"
                for page in range(1, pages + 1):
                    try:
                        response = session.get(
                            "https://xueqiu.com/statuses/search.json",
                            params={
                                "q": target["name"],
                                "symbol": symbol,
                                "count": str(count),
                                "page": str(page),
                                "sort": sort,
                                "source": search_source,
                            },
                            headers=target_headers,
                            timeout=REQUEST_TIMEOUT,
                        )
                        response.raise_for_status()
                        items.extend(parse_xueqiu_search_items(response.json(), source, run_dt, target, keywords))
                    except Exception as exc:  # noqa: BLE001
                        errors.append(f"{target['name']}:{exc}")
                        break
            deduped = {item["url"]: item for item in items}
            return list(deduped.values()), "; ".join(errors[:8]) if errors else None
    except Exception as exc:  # noqa: BLE001
        return [], str(exc)
    return [], f"unsupported source type: {source_type}"


def is_recent_enough(item: dict[str, Any], max_age_hours: int | None, run_dt: datetime) -> bool:
    if not max_age_hours:
        return True
    published_at = parse_iso_datetime(item.get("published_at"))
    if published_at is None:
        return True
    return published_at >= run_dt - timedelta(hours=max_age_hours)


def build_content_hash(source_id: str, title_norm: str, summary: str | None, body_text: str | None, canonical_url: str | None) -> str:
    payload = "||".join(
        [
            source_id,
            title_norm,
            (summary or "").strip()[:2000],
            (body_text or "").strip()[:4000],
            (canonical_url or "").strip(),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_article_id(source_id: str, canonical_url: str | None, title_norm: str, published_at: str | None, content_hash: str) -> str:
    if canonical_url and published_at:
        seed = "||".join([source_id, canonical_url, title_norm, published_at])
    else:
        seed = "||".join([source_id, canonical_url or "", title_norm, published_at or "", content_hash])
    return "live_" + hashlib.sha256(seed.encode("utf-8")).hexdigest()


def find_existing_article_id(
    conn: sqlite3.Connection,
    source_id: str,
    canonical_url: str | None,
    url: str | None,
    title_norm: str,
    published_at: str | None,
    content_hash: str | None = None,
) -> str | None:
    queries: list[tuple[str, tuple[Any, ...]]] = []
    if content_hash:
        queries.append(
            (
                "SELECT article_id FROM news_articles WHERE source_id = ? AND content_hash = ? ORDER BY collected_at DESC LIMIT 1",
                (source_id, content_hash),
            )
        )
    if canonical_url:
        queries.append(
            (
                "SELECT article_id FROM news_articles WHERE source_id = ? AND canonical_url = ? ORDER BY collected_at DESC LIMIT 1",
                (source_id, canonical_url),
            )
        )
    if url and url != canonical_url:
        queries.append(
            (
                "SELECT article_id FROM news_articles WHERE source_id = ? AND url = ? ORDER BY collected_at DESC LIMIT 1",
                (source_id, url),
            )
        )
    if title_norm and published_at:
        queries.append(
            (
                "SELECT article_id FROM news_articles WHERE source_id = ? AND title_norm = ? AND published_at = ? ORDER BY collected_at DESC LIMIT 1",
                (source_id, title_norm, published_at),
            )
        )
    for sql, params in queries:
        row = conn.execute(sql, params).fetchone()
        if row:
            return str(row[0])
    return None


def upsert_article(conn: sqlite3.Connection, source: dict[str, Any], item: dict[str, Any], collected_at: str) -> str:
    title = str(item.get("title") or "").strip()
    if not title:
        return "skipped"
    summary = str(item.get("summary") or "").strip() or None
    body_text = str(item.get("body_text") or "").strip() or summary
    url = str(item.get("url") or "").strip() or None
    canonical_url = str(item.get("canonical_url") or url or "").strip() or None
    published_at = str(item.get("published_at") or "").strip() or None
    title_norm = normalize_title(title)
    if not title_norm:
        return "skipped"
    content_hash = build_content_hash(str(source["source_id"]), title_norm, summary, body_text, canonical_url)
    article_id = find_existing_article_id(conn, str(source["source_id"]), canonical_url, url, title_norm, published_at, content_hash)
    if not article_id:
        article_id = build_article_id(str(source["source_id"]), canonical_url, title_norm, published_at, content_hash)
    language = detect_language(title, summary)
    item_timestamp_quality = str(item.get("timestamp_quality") or "").strip().lower()
    if item_timestamp_quality in {"exact", "estimated", "unknown"}:
        timestamp_quality = item_timestamp_quality
    else:
        timestamp_quality = "exact" if published_at else "unknown"
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
    try:
        exists = conn.execute("SELECT 1 FROM news_articles WHERE article_id = ?", (article_id,)).fetchone() is not None
        conn.execute(
            insert_sql,
            (
                article_id,
                str(source["source_id"]),
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
                "baseline_shared",
                collected_at,
            ),
        )
        return "updated" if exists else "inserted"
    except sqlite3.IntegrityError as exc:
        message = str(exc).lower()
        if "content_hash" in message or "idx_articles_content_hash" in message or "idx_articles_source_content_hash" in message:
            return "duplicate"
        raise


def summarize_source_health(conn: sqlite3.Connection, source_id: str) -> tuple[int, str | None]:
    row = conn.execute(
        """
        SELECT
            COUNT(*) AS articles_last_24h,
            MAX(
                CASE
                    WHEN timestamp_quality IN ('estimated', 'unknown') THEN COALESCE(collected_at, published_at, created_at)
                    ELSE COALESCE(published_at, collected_at, created_at)
                END
            ) AS last_article_at
        FROM news_articles
        WHERE source_id = ?
          AND datetime(
                CASE
                    WHEN timestamp_quality IN ('estimated', 'unknown') THEN COALESCE(collected_at, published_at, created_at)
                    ELSE COALESCE(published_at, collected_at, created_at)
                END
              ) >= datetime('now', '-1 day')
        """,
        (source_id,),
    ).fetchone()
    return int(row[0] or 0), str(row[1]) if row and row[1] else None


def record_source_health(conn: sqlite3.Connection, source_id: str, status: str, error_message: str | None) -> None:
    articles_last_24h, last_article_at = summarize_source_health(conn, source_id)
    conn.execute(
        """
        INSERT INTO source_health (
            source_id,
            checked_at,
            status,
            articles_last_24h,
            last_article_at,
            error_message
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            source_id,
            isoformat_utc(utc_now()),
            status,
            articles_last_24h,
            last_article_at,
            error_message,
        ),
    )


def combine_error_messages(*messages: str | None) -> str | None:
    combined: list[str] = []
    seen: set[str] = set()
    for message in messages:
        clean = str(message or "").strip()
        if not clean or clean in seen:
            continue
        seen.add(clean)
        combined.append(clean)
    return "; ".join(combined) if combined else None


def finalize_source_health(
    source: dict[str, Any],
    fetched_items: int,
    eligible_items: int,
    collector_error: str | None,
) -> tuple[str, str | None]:
    base_status, base_error = classify_source_health(source, fetched_items, eligible_items)
    combined_error = combine_error_messages(base_error, collector_error)
    if collector_error and fetched_items > 0:
        return "degraded", combined_error
    return base_status, combined_error


def ensure_runtime_indexes(conn: sqlite3.Connection) -> None:
    conn.execute("DROP INDEX IF EXISTS idx_articles_content_hash")
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_articles_source_content_hash
        ON news_articles (source_id, content_hash)
        WHERE content_hash IS NOT NULL
        """
    )


def scheduler_min_interval_minutes(source: dict[str, Any]) -> int | None:
    min_interval = source.get("min_interval_minutes")
    if min_interval in (None, ""):
        min_interval = SCHEDULER_DEFAULTS.get(str(source.get("scheduler_class") or "").strip())
    if min_interval in (None, ""):
        return None
    return int(min_interval)


def source_run_quota_available(conn: sqlite3.Connection, source: dict[str, Any], run_dt: datetime) -> bool:
    max_runs = source.get("max_runs_per_24h")
    if max_runs in (None, ""):
        return True
    row = conn.execute(
        """
        SELECT COUNT(*)
        FROM source_health
        WHERE source_id = ?
          AND datetime(checked_at) >= datetime(?)
        """,
        (
            str(source["source_id"]),
            isoformat_utc(run_dt - timedelta(days=1)),
        ),
    ).fetchone()
    recent_runs = int(row[0] or 0) if row else 0
    return recent_runs < int(max_runs)


def classify_source_health(
    source: dict[str, Any],
    fetched_items: int,
    eligible_items: int,
) -> tuple[str, str | None]:
    if fetched_items == 0:
        return "degraded", "collector fetched 0 items"
    max_age_hours = int(source.get("max_age_hours")) if source.get("max_age_hours") is not None else None
    if max_age_hours is not None and eligible_items == 0:
        return "degraded", f"collector fetched items but none within {max_age_hours}h freshness window"
    return "ok", None


def source_due(conn: sqlite3.Connection, source: dict[str, Any], run_dt: datetime, force: bool) -> bool:
    if not source_run_quota_available(conn, source, run_dt):
        return False
    if force:
        return True
    min_interval = scheduler_min_interval_minutes(source)
    if not min_interval:
        return False
    row = conn.execute(
        "SELECT checked_at, status, COALESCE(error_message, '') FROM source_health WHERE source_id = ? ORDER BY checked_at DESC LIMIT 1",
        (str(source["source_id"]),),
    ).fetchone()
    if not row or not row[0]:
        return True
    last_checked = parse_iso_datetime(str(row[0]))
    if last_checked is None:
        return True
    last_status = str(row[1] or "").strip().lower()
    last_error = str(row[2] or "").strip().lower()
    if last_status == "down" and "quarantine_" in last_error:
        quarantine_minutes = int(source.get("quarantine_minutes") or FEED_QUARANTINE_MINUTES)
        if run_dt < last_checked + timedelta(minutes=quarantine_minutes):
            return False
    return run_dt >= last_checked + timedelta(minutes=int(min_interval))


def process_source(conn: sqlite3.Connection, session: requests.Session, source: dict[str, Any], run_dt: datetime) -> dict[str, Any]:
    result = {
        "source_id": str(source["source_id"]),
        "status": "ok",
        "fetched_items": 0,
        "eligible_items": 0,
        "inserted": 0,
        "updated": 0,
        "duplicate": 0,
        "skipped": 0,
        "error": None,
    }
    items, error = fetch_source(session, source, run_dt)
    result["fetched_items"] = len(items)
    if error and not items:
        result["status"] = "down"
        result["error"] = error
        record_source_health(conn, result["source_id"], "down", error)
        return result
    filtered = [
        item
        for item in items
        if is_recent_enough(item, int(source.get("max_age_hours")) if source.get("max_age_hours") is not None else None, run_dt)
    ]
    result["eligible_items"] = len(filtered)
    collected_at = isoformat_utc(run_dt)
    for item in filtered:
        action = upsert_article(conn, source, item, collected_at)
        result[action] += 1
    result["status"], result["error"] = finalize_source_health(
        source,
        result["fetched_items"],
        result["eligible_items"],
        error,
    )
    record_source_health(conn, result["source_id"], result["status"], result["error"])
    return result


def run_due_sources(
    conn: sqlite3.Connection,
    session: requests.Session | None,
    due_sources: list[dict[str, Any]],
    run_dt: datetime,
    process_fn: Any = None,
) -> list[dict[str, Any]]:
    handler = process_fn or process_source
    results: list[dict[str, Any]] = []
    for source in due_sources:
        try:
            conn.execute("BEGIN IMMEDIATE")
            if not source_due(conn, source, run_dt, force=bool(source.get("_force_run"))):
                conn.rollback()
                results.append(
                    {
                        "source_id": str(source["source_id"]),
                        "status": "skipped",
                        "fetched_items": 0,
                        "eligible_items": 0,
                        "inserted": 0,
                        "updated": 0,
                        "duplicate": 0,
                        "skipped": 1,
                        "error": "source already claimed by another collector run",
                    }
                )
                continue
            result = handler(conn, session, source, run_dt)
            conn.commit()
        except sqlite3.OperationalError as exc:
            conn.rollback()
            message = str(exc).lower()
            if "locked" in message or "busy" in message:
                result = {
                    "source_id": str(source["source_id"]),
                    "status": "skipped",
                    "fetched_items": 0,
                    "eligible_items": 0,
                    "inserted": 0,
                    "updated": 0,
                    "duplicate": 0,
                    "skipped": 1,
                    "error": f"collector skipped due to sqlite lock: {exc}",
                }
                results.append(result)
                continue
            result = {
                "source_id": str(source["source_id"]),
                "status": "down",
                "fetched_items": 0,
                "eligible_items": 0,
                "inserted": 0,
                "updated": 0,
                "duplicate": 0,
                "skipped": 0,
                "error": f"unhandled collector error: {exc}",
            }
            try:
                conn.execute("BEGIN")
                record_source_health(conn, result["source_id"], "down", result["error"])
                conn.commit()
            except Exception:
                conn.rollback()
        except Exception as exc:
            conn.rollback()
            result = {
                "source_id": str(source["source_id"]),
                "status": "down",
                "fetched_items": 0,
                "eligible_items": 0,
                "inserted": 0,
                "updated": 0,
                "duplicate": 0,
                "skipped": 0,
                "error": f"unhandled collector error: {exc}",
            }
            try:
                conn.execute("BEGIN")
                record_source_health(conn, result["source_id"], "down", result["error"])
                conn.commit()
            except Exception:
                conn.rollback()
        results.append(result)
    return results


def main() -> None:
    args = parse_args()
    if not args.db.exists():
        raise SystemExit(f"database missing: {args.db}")
    registry = load_registry(args.registry)
    catalog_rows = load_catalog(args.catalog)
    scheduler_classes = set(args.scheduler_classes or []) or None
    source_ids = set(args.source_ids or []) or None
    sources = merge_sources(registry, catalog_rows, scheduler_classes, source_ids)
    for source in sources:
        source["consumer_export_root"] = str(args.consumer_export_root)
        source["watchlist_registry"] = str(args.watchlist_registry)
        source["weibo_state_path"] = str(args.weibo_state_path)
        if args.target_names:
            source["target_names"] = list(args.target_names)
    if args.limit_sources > 0:
        sources = sources[: args.limit_sources]
    run_dt = utc_now()

    conn = sqlite3.connect(args.db, timeout=SQLITE_BUSY_TIMEOUT_MS / 1000)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(f"PRAGMA busy_timeout = {SQLITE_BUSY_TIMEOUT_MS}")
    ensure_bootstrap(conn, args.schema, registry)
    conn.commit()
    session = requests.Session()
    due_sources = [source for source in sources if source_due(conn, source, run_dt, args.force)]
    for source in due_sources:
        source["_force_run"] = bool(args.force)
    try:
        results = run_due_sources(conn, session, due_sources, run_dt)
    finally:
        session.close()
        conn.close()

    total_inserted = sum(int(item["inserted"]) for item in results)
    total_updated = sum(int(item["updated"]) for item in results)
    total_duplicate = sum(int(item["duplicate"]) for item in results)
    total_skipped = sum(int(item["skipped"]) for item in results)
    total_down = sum(1 for item in results if item["status"] == "down")
    total_degraded = sum(1 for item in results if item["status"] == "degraded")

    print(f"run_at: {isoformat_utc(run_dt)}")
    print(f"sources_configured: {len(sources)}")
    print(f"sources_due: {len(due_sources)}")
    print(f"total_inserted: {total_inserted}")
    print(f"total_updated: {total_updated}")
    print(f"total_duplicate: {total_duplicate}")
    print(f"total_skipped: {total_skipped}")
    print(f"total_degraded: {total_degraded}")
    print(f"total_down: {total_down}")
    for item in results:
        status_text = (
            f"{item['status']} fetched={item['fetched_items']} eligible={item['eligible_items']} "
            f"inserted={item['inserted']} updated={item['updated']} duplicate={item['duplicate']}"
        )
        if item.get("error"):
            status_text += f" error={item['error']}"
        print(f"- {item['source_id']}: {status_text}")


if __name__ == "__main__":
    main()
