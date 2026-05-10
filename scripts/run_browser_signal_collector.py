#!/usr/bin/env python3
from __future__ import annotations

import argparse
import contextlib
import json
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote, urljoin

from run_live_news_collector import (
    CHINA_TZ,
    DEFAULT_AGENT_REACH_STATE,
    DEFAULT_CONSUMER_EXPORT_ROOT,
    DEFAULT_DB,
    DEFAULT_REGISTRY,
    DEFAULT_SCHEMA,
    DEFAULT_WATCHLIST_REGISTRY,
    SQLITE_BUSY_TIMEOUT_MS,
    WEIBO_BASKET_MOVE_RE,
    WEIBO_DISCOVERY_RE,
    WEIBO_GENERIC_POST_RE,
    WEIBO_MEDIA_AUTHOR_RE,
    WEIBO_NOISE_RE,
    WEIBO_OFFICIAL_REPOST_RE,
    WEIBO_RUMORISH_RE,
    WEIBO_SYNDICATION_RE,
    apply_schema,
    classify_source_health,
    ensure_bootstrap,
    ensure_runtime_indexes,
    finalize_source_health,
    isoformat_utc,
    is_recent_enough,
    load_catalog,
    load_registry,
    merge_sources,
    normalize_url,
    parse_human_datetime,
    record_source_health,
    resolve_shared_targets,
    should_keep_xueqiu_post,
    source_due,
    strip_html,
    upsert_article,
    utc_now,
)


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BROWSER_CATALOG = ROOT / "config" / "browser_signal_catalog_v1.json"
XUEQIU_SEARCH_URL = "https://xueqiu.com/k?q={query}"
XIAOHONGSHU_SEARCH_URL = "https://www.xiaohongshu.com/search_result?keyword={query}&type=51"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run browser-backed signal collectors for WAF/policy-blocked sources.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="SQLite database path.")
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA, help="Schema SQL path.")
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY, help="Source registry YAML path.")
    parser.add_argument("--catalog", type=Path, default=DEFAULT_BROWSER_CATALOG, help="Browser signal catalog JSON path.")
    parser.add_argument("--consumer-export-root", type=Path, default=DEFAULT_CONSUMER_EXPORT_ROOT, help="Shared consumer export directory for target resolution.")
    parser.add_argument("--watchlist-registry", type=Path, default=DEFAULT_WATCHLIST_REGISTRY, help="Canonical watchlist registry CSV for tracked targets.")
    parser.add_argument("--storage-state-path", type=Path, default=DEFAULT_AGENT_REACH_STATE, help="Optional Playwright storage-state JSON.")
    parser.add_argument(
        "--target-name",
        action="append",
        dest="target_names",
        help="Optional ad-hoc tracked target name. Can be repeated and is merged ahead of watchlist/feed-derived targets.",
    )
    parser.add_argument("--headful", action="store_true", help="Run Chromium headed for debugging.")
    parser.add_argument("--scheduler-class", action="append", dest="scheduler_classes", help="Only run these scheduler classes.")
    parser.add_argument("--source-id", action="append", dest="source_ids", help="Only run these source ids.")
    parser.add_argument("--force", action="store_true", help="Ignore source min intervals.")
    parser.add_argument("--limit-sources", type=int, default=0, help="Optional max number of sources to process.")
    return parser.parse_args()


def normalize_time_text(value: str) -> str:
    clean = " ".join(str(value or "").strip().split())
    clean = clean.replace("修改于", "").strip()
    if "·" in clean:
        clean = clean.split("·", 1)[0].strip()
    return clean


def parse_xueqiu_time_text(value: str, run_dt: datetime) -> str | None:
    clean = normalize_time_text(value)
    if not clean:
        return None
    parsed = parse_human_datetime(clean, run_dt)
    if parsed:
        return parsed
    if clean.startswith("昨天 "):
        time_part = clean.replace("昨天 ", "", 1).strip()
        if re.fullmatch(r"\d{1,2}:\d{2}", time_part):
            local_now = run_dt.astimezone(CHINA_TZ)
            parsed_dt = datetime.strptime(f"{(local_now - timedelta(days=1)).date().isoformat()} {time_part}", "%Y-%m-%d %H:%M").replace(tzinfo=CHINA_TZ)
            return parsed_dt.astimezone(timezone.utc).isoformat(timespec="seconds")
    match = re.fullmatch(r"(\d{2})-(\d{2})\s+(\d{1,2}:\d{2})", clean)
    if match:
        month, day, time_part = match.groups()
        local_now = run_dt.astimezone(CHINA_TZ)
        year = local_now.year
        parsed_dt = datetime.strptime(f"{year}-{month}-{day} {time_part}", "%Y-%m-%d %H:%M").replace(tzinfo=CHINA_TZ)
        if parsed_dt > local_now + timedelta(days=2):
            parsed_dt = parsed_dt.replace(year=year - 1)
        return parsed_dt.astimezone(timezone.utc).isoformat(timespec="seconds")
    return None


def xueqiu_extract_script() -> str:
    return """
() => {
  const clean = (value) => (value || '').replace(/\\s+/g, ' ').trim();
  const statsOnly = (value) => /^[\\d\\s%+\\-.]+$/.test(value || '');
  return Array.from(document.querySelectorAll('article')).map((article) => {
    const lines = (article.innerText || '')
      .split('\\n')
      .map((item) => clean(item))
      .filter(Boolean);
    const anchors = Array.from(article.querySelectorAll('a[href]')).map((anchor) => ({
      href: anchor.getAttribute('href') || '',
      text: clean(anchor.innerText || ''),
      hasImg: !!anchor.querySelector('img')
    }));
    const heading = article.querySelector('h3');
    const title = clean(heading ? heading.innerText : '');
    let timeHref = '';
    let timeText = '';
    for (const anchor of anchors) {
      if (/\\/\\d+\\/\\d+$/.test(anchor.href) && /(来自|昨天|小时前|分钟前|修改于|\\d{2}-\\d{2})/.test(anchor.text)) {
        timeHref = anchor.href;
        timeText = anchor.text;
        break;
      }
    }
    if (!timeHref) {
      const fallback = anchors.find((anchor) => /\\/\\d+\\/\\d+$/.test(anchor.href));
      if (fallback) {
        timeHref = fallback.href;
        timeText = fallback.text;
      }
    }
    let author = '';
    for (const anchor of anchors) {
      const text = anchor.text;
      if (!text || anchor.hasImg) continue;
      if (/来自|收藏|转发|展开|已添加/.test(text)) continue;
      if (text === title) continue;
      if (/^\\/S\\//.test(anchor.href)) continue;
      if (statsOnly(text)) continue;
      author = text;
      break;
    }
    const contentLines = lines.filter((line) => {
      if (!line) return false;
      if (line === author || line === timeText || line === title) return false;
      if (/^(展开|收藏|转发|已添加|热门|都在问)$/.test(line)) return false;
      if (statsOnly(line)) return false;
      return true;
    });
    return {
      author,
      time_text: timeText,
      href: timeHref,
      title,
      body_text: contentLines.join(' '),
      raw_text: clean(article.innerText || '')
    };
  });
}
"""


def xiaohongshu_extract_script() -> str:
    return """
() => {
  const clean = (value) => (value || '').replace(/\\s+/g, ' ').trim();
  const toText = (el, selector) => {
    const node = selector ? el.querySelector(selector) : el;
    return clean(node ? (node.innerText || '') : '');
  };
  return Array.from(document.querySelectorAll('section.note-item')).map((section) => {
    const hiddenExplore = section.querySelector('a[href^="/explore/"]');
    const coverLink = section.querySelector('a.cover[href]');
    const authorAnchor = section.querySelector('a.author[href]');
    const title = toText(section, 'a.title');
    const author = toText(section, '.author .name');
    const time_text = toText(section, '.author .time');
    const likes = toText(section, '.count');
    return {
      explore_href: hiddenExplore ? (hiddenExplore.getAttribute('href') || '') : '',
      cover_href: coverLink ? (coverLink.getAttribute('href') || '') : '',
      author_href: authorAnchor ? (authorAnchor.getAttribute('href') || '') : '',
      title,
      author,
      time_text,
      likes,
      raw_text: clean(section.innerText || '')
    };
  });
}
"""


def should_keep_xueqiu_dom_post(text: str, target_name: str, keywords: tuple[str, ...], author: str, title: str = "") -> bool:
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
    if len(combined_text) < 36:
        return False
    window_text = combined_text
    if WEIBO_DISCOVERY_RE.search(window_text):
        return True
    lowered = window_text.lower()
    if any(keyword.lower() in lowered for keyword in keywords):
        return True
    if clean_title:
        return True
    if len(clean_text) >= 80:
        return True
    return not WEIBO_MEDIA_AUTHOR_RE.search(author or "")


def normalize_xueqiu_dom_items(records: list[dict[str, Any]], source: dict[str, Any], run_dt: datetime, target: dict[str, Any], keywords: tuple[str, ...]) -> list[dict[str, Any]]:
    max_items = int(source.get("max_items_per_target", 4))
    items: list[dict[str, Any]] = []
    for record in records:
        if not isinstance(record, dict):
            continue
        author = str(record.get("author") or "雪球用户").strip()
        title = strip_html(str(record.get("title") or ""))
        body_text = strip_html(str(record.get("body_text") or record.get("raw_text") or ""))
        combined = f"{title} {body_text}".strip()
        if not should_keep_xueqiu_dom_post(body_text, target["name"], keywords, author, title=title):
            continue
        href = str(record.get("href") or "").strip()
        url = normalize_url(urljoin("https://xueqiu.com", href)) if href else ""
        published_at = parse_xueqiu_time_text(str(record.get("time_text") or ""), run_dt)
        title_text = title or (combined[:80] + ("…" if len(combined) > 80 else ""))
        summary_parts = [f"雪球搜索线索：{target['name']}", f"作者 {author}"]
        if record.get("time_text"):
            summary_parts.append(str(record["time_text"]).strip())
        items.append(
            {
                "title": title_text,
                "summary": "，".join(summary_parts),
                "body_text": combined,
                "url": url,
                "canonical_url": url,
                "published_at": published_at,
            }
        )
        if len(items) >= max_items:
            break
    deduped = {item["canonical_url"] or item["title"]: item for item in items}
    return list(deduped.values())


def parse_xiaohongshu_time_text(value: str, run_dt: datetime) -> str | None:
    clean = normalize_time_text(value)
    if not clean:
        return None
    parsed = parse_human_datetime(clean, run_dt)
    if parsed:
        return parsed
    match = re.fullmatch(r"(\d{2})-(\d{2})", clean)
    if match:
        month, day = match.groups()
        local_now = run_dt.astimezone(CHINA_TZ)
        year = local_now.year
        parsed_dt = datetime.strptime(f"{year}-{month}-{day} 12:00", "%Y-%m-%d %H:%M").replace(tzinfo=CHINA_TZ)
        if parsed_dt > local_now + timedelta(days=2):
            parsed_dt = parsed_dt.replace(year=year - 1)
        return parsed_dt.astimezone(timezone.utc).isoformat(timespec="seconds")
    return None


def parse_xiaohongshu_like_count(value: str) -> int:
    clean = normalize_time_text(value).replace("赞", "").strip()
    if not clean:
        return 0
    if clean.endswith("万"):
        with contextlib.suppress(ValueError):
            return int(float(clean[:-1]) * 10000)
    with contextlib.suppress(ValueError):
        return int(float(clean))
    return 0


def should_keep_xiaohongshu_note(text: str, target_name: str, keywords: tuple[str, ...], likes: int) -> bool:
    clean_text = " ".join(str(text or "").split())
    if not clean_text or target_name not in clean_text:
        return False
    if clean_text.startswith("大家都在搜"):
        return False
    lowered = clean_text.lower()
    if any(keyword.lower() in lowered for keyword in keywords):
        return True
    return likes >= 1 or len(clean_text) >= 12


def normalize_xiaohongshu_items(records: list[dict[str, Any]], source: dict[str, Any], run_dt: datetime, target: dict[str, Any], keywords: tuple[str, ...]) -> list[dict[str, Any]]:
    max_items = int(source.get("max_items_per_target", 4))
    items: list[dict[str, Any]] = []
    for record in records:
        if not isinstance(record, dict):
            continue
        title = strip_html(str(record.get("title") or ""))
        author = strip_html(str(record.get("author") or "小红书用户"))
        raw_text = strip_html(str(record.get("raw_text") or title))
        likes = parse_xiaohongshu_like_count(str(record.get("likes") or ""))
        if not should_keep_xiaohongshu_note(raw_text or title, target["name"], keywords, likes):
            continue
        href = str(record.get("explore_href") or "").strip()
        if not href:
            continue
        url = normalize_url(urljoin("https://www.xiaohongshu.com", href))
        published_at = parse_xiaohongshu_time_text(str(record.get("time_text") or ""), run_dt)
        summary_parts = [f"小红书搜索线索：{target['name']}", f"作者 {author}"]
        if record.get("time_text"):
            summary_parts.append(str(record["time_text"]).strip())
        if likes:
            summary_parts.append(f"{likes} 赞")
        items.append(
            {
                "title": title or raw_text[:80],
                "summary": "，".join(summary_parts),
                "body_text": raw_text or title,
                "url": url,
                "canonical_url": url,
                "published_at": published_at,
            }
        )
        if len(items) >= max_items:
            break
    deduped = {item["canonical_url"] or item["title"]: item for item in items}
    return list(deduped.values())


def fetch_xueqiu_dom_search(playwright: Any, source: dict[str, Any], run_dt: datetime, storage_state_path: Path) -> tuple[list[dict[str, Any]], str | None]:
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

    browser = playwright.chromium.launch(
        headless=not bool(source.get("headful_debug")),
        args=["--disable-blink-features=AutomationControlled"],
    )
    context_kwargs: dict[str, Any] = {
        "locale": "zh-CN",
        "timezone_id": "Asia/Shanghai",
        "user_agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
        ),
        "viewport": {"width": 1440, "height": 1024},
    }
    if storage_state_path.exists():
        context_kwargs["storage_state"] = str(storage_state_path)
    context = browser.new_context(**context_kwargs)
    context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")
    page = context.new_page()
    page.set_default_timeout(20000)
    targets = resolve_shared_targets(
        source,
        Path(str(source.get("consumer_export_root") or DEFAULT_CONSUMER_EXPORT_ROOT)),
        Path(str(source.get("watchlist_registry") or DEFAULT_WATCHLIST_REGISTRY)),
    )
    keywords = tuple(
        str(item).strip() for item in (source.get("keywords_cn") or ()) if str(item).strip()
    ) or ("传闻", "收购", "并购", "重组", "订单", "扩产", "停产", "提价", "增持", "回购")
    items: list[dict[str, Any]] = []
    errors: list[str] = []
    try:
        for target in targets:
            try:
                page.goto(XUEQIU_SEARCH_URL.format(query=quote(target["name"])), wait_until="domcontentloaded")
                with contextlib.suppress(PlaywrightTimeoutError):
                    page.wait_for_selector("article", timeout=10000)
                page.wait_for_timeout(1200)
                records = page.evaluate(xueqiu_extract_script())
                items.extend(normalize_xueqiu_dom_items(records or [], source, run_dt, target, keywords))
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{target['name']}:{exc}")
    finally:
        context.close()
        browser.close()
    deduped = {item["canonical_url"] or item["title"]: item for item in items}
    return list(deduped.values()), "; ".join(errors[:8]) if errors else None


def fetch_xiaohongshu_web_search(playwright: Any, source: dict[str, Any], run_dt: datetime, storage_state_path: Path) -> tuple[list[dict[str, Any]], str | None]:
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

    browser = playwright.chromium.launch(
        headless=not bool(source.get("headful_debug")),
        args=["--disable-blink-features=AutomationControlled"],
    )
    context_kwargs: dict[str, Any] = {
        "locale": "zh-CN",
        "timezone_id": "Asia/Shanghai",
        "user_agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
        ),
        "viewport": {"width": 1440, "height": 1024},
    }
    if storage_state_path.exists():
        context_kwargs["storage_state"] = str(storage_state_path)
    context = browser.new_context(**context_kwargs)
    context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")
    page = context.new_page()
    page.set_default_timeout(25000)
    targets = resolve_shared_targets(
        source,
        Path(str(source.get("consumer_export_root") or DEFAULT_CONSUMER_EXPORT_ROOT)),
        Path(str(source.get("watchlist_registry") or DEFAULT_WATCHLIST_REGISTRY)),
    )
    keywords = tuple(
        str(item).strip() for item in (source.get("keywords_cn") or ()) if str(item).strip()
    ) or ("新品", "开业", "门店", "联名", "黄牛", "排队", "断货", "爆火", "销量", "热卖", "翻红", "偶遇")
    items: list[dict[str, Any]] = []
    errors: list[str] = []
    try:
        for target in targets:
            try:
                page.goto(XIAOHONGSHU_SEARCH_URL.format(query=quote(target["name"])), wait_until="domcontentloaded")
                with contextlib.suppress(PlaywrightTimeoutError):
                    page.wait_for_selector("section.note-item", timeout=12000)
                page.wait_for_timeout(1800)
                records = page.evaluate(xiaohongshu_extract_script())
                items.extend(normalize_xiaohongshu_items(records or [], source, run_dt, target, keywords))
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{target['name']}:{exc}")
    finally:
        context.close()
        browser.close()
    deduped = {item["canonical_url"] or item["title"]: item for item in items}
    return list(deduped.values()), "; ".join(errors[:8]) if errors else None


def process_browser_source(conn: sqlite3.Connection, source: dict[str, Any], run_dt: datetime, storage_state_path: Path, headful: bool) -> dict[str, Any]:
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
    source_type = str(source.get("type") or "").strip()
    source = dict(source)
    if headful:
        source["headful_debug"] = True
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        if source_type == "xueqiu_dom_search":
            items, error = fetch_xueqiu_dom_search(playwright, source, run_dt, storage_state_path)
        elif source_type == "xiaohongshu_web_search":
            items, error = fetch_xiaohongshu_web_search(playwright, source, run_dt, storage_state_path)
        else:
            items, error = [], f"unsupported browser source type: {source_type}"
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


def main() -> None:
    args = parse_args()
    if not args.db.exists():
        raise SystemExit(f"database missing: {args.db}")
    registry = load_registry(args.registry)
    catalog_rows = load_catalog(args.catalog)
    due_candidates = merge_sources(
        registry,
        catalog_rows,
        set(args.scheduler_classes or []) or None,
        set(args.source_ids or []) or None,
    )
    for source in due_candidates:
        source["consumer_export_root"] = str(args.consumer_export_root)
        source["watchlist_registry"] = str(args.watchlist_registry)
        if args.target_names:
            source["target_names"] = list(args.target_names)
    if args.limit_sources:
        due_candidates = due_candidates[: int(args.limit_sources)]
    run_dt = utc_now()
    conn = sqlite3.connect(args.db, timeout=SQLITE_BUSY_TIMEOUT_MS / 1000)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(f"PRAGMA busy_timeout = {SQLITE_BUSY_TIMEOUT_MS}")
    try:
        ensure_bootstrap(conn, args.schema, registry)
        conn.commit()
        due_sources = [source for source in due_candidates if source_due(conn, source, run_dt, args.force)]
        results: list[dict[str, Any]] = []
        for source in due_sources:
            try:
                conn.execute("BEGIN IMMEDIATE")
                if not source_due(conn, source, utc_now(), force=args.force):
                    conn.rollback()
                    continue
                result = process_browser_source(conn, source, run_dt, args.storage_state_path, args.headful)
                conn.commit()
            except sqlite3.OperationalError as exc:
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
                    "error": str(exc),
                }
                record_source_health(conn, result["source_id"], "down", result["error"])
                conn.commit()
            results.append(result)
        print(f"run_at: {isoformat_utc(run_dt)}")
        print(f"sources_configured: {len(due_candidates)}")
        print(f"sources_due: {len(due_sources)}")
        print(f"total_inserted: {sum(int(item['inserted']) for item in results)}")
        print(f"total_updated: {sum(int(item['updated']) for item in results)}")
        print(f"total_duplicate: {sum(int(item['duplicate']) for item in results)}")
        print(f"total_skipped: {sum(int(item['skipped']) for item in results)}")
        print(f"total_degraded: {sum(1 for item in results if item['status'] == 'degraded')}")
        print(f"total_down: {sum(1 for item in results if item['status'] == 'down')}")
        for item in results:
            error_text = f" error={item['error']}" if item.get("error") else ""
            print(
                f"- {item['source_id']}: {item['status']} "
                f"fetched={item['fetched_items']} eligible={item['eligible_items']} "
                f"inserted={item['inserted']} updated={item['updated']} duplicate={item['duplicate']}{error_text}"
            )
    finally:
        conn.close()


if __name__ == "__main__":
    main()
