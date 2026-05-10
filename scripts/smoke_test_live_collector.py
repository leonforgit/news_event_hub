#!/usr/bin/env python3
from __future__ import annotations

import sqlite3
import json
import os
import tempfile
from datetime import date
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

import run_live_news_collector as live_collector

from run_live_news_collector import (
    build_akshare_news_cctv_items,
    build_akshare_stock_notice_report_items,
    build_akshare_stock_info_global_cls_items,
    build_akshare_stock_info_global_em_items,
    build_akshare_stock_info_global_ths_items,
    parse_atom_items,
    build_watchlist_targets,
    ensure_bootstrap,
    classify_source_health,
    ensure_runtime_indexes,
    fetch_source,
    FeedResponseError,
    load_registry,
    parse_marketaux_items,
    parse_mediastack_items,
    parse_guba_tracked_items,
    parse_reddit_listing_items,
    parse_reddit_search_items,
    parse_serpstack_items,
    parse_xueqiu_hot_stock_items,
    parse_xueqiu_public_timeline_items,
    parse_xueqiu_search_items,
    merge_sources,
    parse_cninfo_items,
    parse_cls_telegraph_items,
    parse_html_list_items,
    parse_rss_items,
    record_source_health,
    resolve_shared_targets,
    run_due_sources,
    summarize_source_health,
    source_due,
    source_run_quota_available,
    upsert_article,
)


ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = ROOT / "config" / "schema.sql"


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def open_db(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 0")
    return conn


def main() -> None:
    conn = open_db(":memory:")
    try:
        now_utc = datetime.now(timezone.utc).replace(microsecond=0)
        recent_collected_at = now_utc.isoformat(timespec="seconds")
        older_collected_at = (now_utc - timedelta(hours=26)).isoformat(timespec="seconds")
        stale_published_at = (now_utc - timedelta(days=7)).isoformat(timespec="seconds")
        estimated_published_at = (now_utc - timedelta(days=2)).replace(hour=4, minute=0, second=0).isoformat(timespec="seconds")
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        ensure_runtime_indexes(conn)
        conn.execute(
            """
            INSERT INTO source_registry (
                source_id, name, lane, source_family, source_type, trust_tier, coverage_scope,
                collector_owner, scheduler_class, origin_system, legacy_key,
                phase1_disposition, enabled, description
            ) VALUES ('test_source', 'Test Source', 'confirmation', '', 'rss', 1, 'mixed', 'shared', 'high_freq', 'news_event_hub', 'test_source', 'migrate_phase1', 1, '')
            """
        )
        conn.execute(
            """
            INSERT INTO source_registry (
                source_id, name, lane, source_family, source_type, trust_tier, coverage_scope,
                collector_owner, scheduler_class, origin_system, legacy_key,
                phase1_disposition, enabled, description
            ) VALUES
            ('other_source', 'Other Source', 'confirmation', '', 'rss', 1, 'mixed', 'shared', 'high_freq', 'news_event_hub', 'other_source', 'migrate_phase1', 1, ''),
            ('stale_source', 'Stale Source', 'confirmation', '', 'rss', 1, 'mixed', 'shared', 'high_freq', 'news_event_hub', 'stale_source', 'migrate_phase1', 1, ''),
            ('unknown_time_source', 'Unknown Time Source', 'confirmation', '', 'rss', 1, 'mixed', 'shared', 'high_freq', 'news_event_hub', 'unknown_time_source', 'migrate_phase1', 1, ''),
            ('ok_source', 'OK Source', 'confirmation', '', 'rss', 1, 'mixed', 'shared', 'high_freq', 'news_event_hub', 'ok_source', 'migrate_phase1', 1, ''),
            ('bad_source', 'Bad Source', 'confirmation', '', 'rss', 1, 'mixed', 'shared', 'high_freq', 'news_event_hub', 'bad_source', 'migrate_phase1', 1, '')
            """
        )
        conn.commit()

        source = {
            "source_id": "test_source",
            "scheduler_class": "high_freq",
            "min_interval_minutes": 10,
            "max_age_hours": 6,
        }
        item = {
            "title": "示例新闻标题",
            "summary": "示例摘要",
            "body_text": "示例摘要",
            "url": "https://example.com/item?utm_source=test",
            "canonical_url": "https://example.com/item",
            "published_at": "2026-04-07T10:00:00+00:00",
        }

        action_first = upsert_article(conn, source, item, "2026-04-07T10:05:00+00:00")
        action_second = upsert_article(conn, source, item, "2026-04-07T10:06:00+00:00")
        count = conn.execute("SELECT COUNT(*) FROM news_articles").fetchone()[0]
        assert_true(action_first == "inserted", "first upsert should insert")
        assert_true(action_second == "updated", "same article should update rather than duplicate")
        assert_true(int(count) == 1, "duplicate collector writes should not create a second article row")

        other_source = {
            "source_id": "other_source",
            "scheduler_class": "high_freq",
            "min_interval_minutes": 10,
            "max_age_hours": 6,
        }
        other_action = upsert_article(conn, other_source, item, "2026-04-07T10:06:30+00:00")
        cross_source_count = conn.execute(
            "SELECT COUNT(*) FROM news_articles WHERE canonical_url = 'https://example.com/item'"
        ).fetchone()[0]
        assert_true(other_action == "inserted", "same content from a different source should remain a separate confirmation row")
        assert_true(int(cross_source_count) == 2, "cross-source confirmation rows should not be collapsed by a global content-hash unique index")

        collision_item_a = {
            "title": "无链接无时间同标题",
            "summary": "第一版内容",
            "body_text": "第一版内容",
            "url": "",
            "canonical_url": "",
            "published_at": "",
        }
        collision_item_b = {
            "title": "无链接无时间同标题",
            "summary": "第二版内容",
            "body_text": "第二版完全不同内容",
            "url": "",
            "canonical_url": "",
            "published_at": "",
        }
        collision_first = upsert_article(conn, source, collision_item_a, "2026-04-07T10:06:40+00:00")
        collision_second = upsert_article(conn, source, collision_item_b, "2026-04-07T10:06:41+00:00")
        collision_rows = conn.execute(
            "SELECT COUNT(*) FROM news_articles WHERE source_id = 'test_source' AND title = '无链接无时间同标题'"
        ).fetchone()[0]
        assert_true(collision_first == "inserted" and collision_second == "inserted", "same-title items without url/published_at should not overwrite each other when content differs")
        assert_true(int(collision_rows) == 2, "collector should preserve distinct no-url/no-published items with different content hashes")

        run_dt = datetime(2026, 4, 7, 10, 7, tzinfo=timezone.utc)
        assert_true(source_due(conn, source, run_dt, force=False), "source should be due before any health record")
        conn.execute(
            """
            INSERT INTO source_health (source_id, checked_at, status, articles_last_24h, last_article_at, error_message)
            VALUES ('test_source', ?, 'ok', 1, '2026-04-07T10:00:00+00:00', NULL)
            """,
            ("2026-04-07T10:05:00+00:00",),
        )
        conn.commit()
        assert_true(not source_due(conn, source, run_dt, force=False), "source should not be due immediately after a recent health check")

        old_checked = (run_dt - timedelta(minutes=20)).isoformat(timespec="seconds")
        conn.execute("DELETE FROM source_health")
        conn.execute(
            """
            INSERT INTO source_health (source_id, checked_at, status, articles_last_24h, last_article_at, error_message)
            VALUES ('test_source', ?, 'ok', 1, '2026-04-07T10:00:00+00:00', NULL)
            """,
            (old_checked,),
        )
        conn.commit()
        assert_true(source_due(conn, source, run_dt, force=False), "source should become due again after min interval elapses")

        conn.execute("DELETE FROM source_health")
        record_source_health(conn, "test_source", "ok", None)
        conn.commit()
        recorded = conn.execute("SELECT status FROM source_health ORDER BY id DESC LIMIT 1").fetchone()
        assert_true(recorded is not None and recorded[0] == "ok", "record_source_health should persist an ok row")

        quota_source = {
            "source_id": "test_source",
            "scheduler_class": "high_freq",
            "min_interval_minutes": 10,
            "max_age_hours": 6,
            "max_runs_per_24h": 2,
        }
        conn.execute("DELETE FROM source_health WHERE source_id = 'test_source'")
        conn.executemany(
            """
            INSERT INTO source_health (source_id, checked_at, status, articles_last_24h, last_article_at, error_message)
            VALUES ('test_source', ?, 'ok', 1, '2026-04-07T10:00:00+00:00', NULL)
            """,
            [
                ("2026-04-07T09:00:00+00:00",),
                ("2026-04-07T10:00:00+00:00",),
            ],
        )
        conn.commit()
        assert_true(not source_run_quota_available(conn, quota_source, run_dt), "source quota helper should block once the rolling 24h cap is reached")
        assert_true(not source_due(conn, quota_source, run_dt, force=False), "source_due should honor rolling 24h source quotas")
        assert_true(not source_due(conn, quota_source, run_dt, force=True), "force runs should still respect rolling 24h source quotas")
        conn.execute("DELETE FROM source_health WHERE source_id = 'test_source'")
        conn.commit()

        stale_source = {
            "source_id": "stale_source",
            "coverage_scope": "mixed",
            "trust_tier": 1,
        }
        stale_item = {
            "title": "旧闻标题",
            "summary": "旧闻摘要",
            "body_text": "旧闻摘要",
            "url": "https://example.com/old-item",
            "canonical_url": "https://example.com/old-item",
            "published_at": stale_published_at,
        }
        upsert_article(conn, stale_source, stale_item, recent_collected_at)
        articles_last_24h, last_article_at = summarize_source_health(conn, "stale_source")
        assert_true(int(articles_last_24h) == 0, "old published_at rows should not be counted as fresh just because they were re-collected recently")
        assert_true(last_article_at is None, "last_article_at should stay empty when the source has no article inside the freshness window")

        unknown_time_item = {
            "title": "未知发布时间新闻",
            "summary": "collector still sees it",
            "body_text": "collector still sees it",
            "url": "https://example.com/unknown-time",
            "canonical_url": "https://example.com/unknown-time",
            "published_at": "",
        }
        unknown_time_source = {
            "source_id": "unknown_time_source",
            "coverage_scope": "mixed",
            "trust_tier": 1,
        }
        upsert_article(conn, unknown_time_source, unknown_time_item, older_collected_at)
        upsert_article(conn, unknown_time_source, unknown_time_item, recent_collected_at)
        unknown_last_article_at = summarize_source_health(conn, "unknown_time_source")[1]
        assert_true(
            unknown_last_article_at == recent_collected_at,
            "source health should fall back to latest collected_at when published_at is missing",
        )

        estimated_time_item = {
            "title": "日期粒度新闻",
            "summary": "只有日期，没有精确时间",
            "body_text": "只有日期，没有精确时间",
            "url": "https://example.com/date-only",
            "canonical_url": "https://example.com/date-only",
            "published_at": estimated_published_at,
            "timestamp_quality": "estimated",
        }
        upsert_article(conn, {"source_id": "test_source"}, estimated_time_item, recent_collected_at)
        estimated_articles_last_24h, estimated_last_article_at = summarize_source_health(conn, "test_source")
        assert_true(
            estimated_articles_last_24h >= 1 and estimated_last_article_at == recent_collected_at,
            "estimated timestamps should use collected_at for freshness accounting",
        )

        rss_items = parse_rss_items(
            """
            <rss><channel>
              <item>
                <title>Malformed Link Item</title>
                <description>ignored</description>
                <link>file:///etc/passwd</link>
                <pubDate>Tue, 07 Apr 2026 10:00:00 GMT</pubDate>
              </item>
              <item>
                <title>Valid Link Item</title>
                <description>kept</description>
                <link>https://example.com/path?utm_source=test</link>
                <pubDate>Tue, 07 Apr 2026 10:05:00 GMT</pubDate>
              </item>
            </channel></rss>
            """,
            {"name": "rss-source"},
        )
        assert_true(len(rss_items) == 1, "rss parser should skip non-http links")
        assert_true(rss_items[0]["canonical_url"] == "https://example.com/path", "rss parser should still normalize valid http links")
        try:
            parse_rss_items("<html><body>rate limited</body></html>", {"name": "rss-source"})
            raise AssertionError("non-feed HTML should raise a quarantine error")
        except FeedResponseError as exc:
            assert_true("quarantine_non_xml_rss_response" in str(exc), "rss parser should label HTML/error pages as quarantined feed responses")

        conn.execute("DELETE FROM source_health WHERE source_id = 'test_source'")
        conn.execute(
            """
            INSERT INTO source_health (source_id, checked_at, status, articles_last_24h, last_article_at, error_message)
            VALUES ('test_source', ?, 'down', 0, NULL, 'quarantine_non_xml_rss_response: html page returned')
            """,
            (run_dt.isoformat(timespec="seconds"),),
        )
        conn.commit()
        quarantine_source = dict(source)
        quarantine_source["quarantine_minutes"] = 360
        assert_true(not source_due(conn, quarantine_source, run_dt + timedelta(minutes=30), force=False), "quarantined feed source should stay isolated during cool-off")
        assert_true(source_due(conn, quarantine_source, run_dt + timedelta(minutes=400), force=False), "quarantined feed source should become due after cool-off")

        atom_items = parse_atom_items(
            """
            <feed xmlns="http://www.w3.org/2005/Atom">
              <entry>
                <title>V2EX 测试帖子</title>
                <link href="https://www.v2ex.com/t/123456" />
                <updated>2026-04-07T12:00:00Z</updated>
                <content type="html">&lt;p&gt;这里是内容&lt;/p&gt;</content>
              </entry>
            </feed>
            """,
            {"max_items": 10},
        )
        assert_true(len(atom_items) == 1, "atom parser should emit one item")
        assert_true(atom_items[0]["canonical_url"] == "https://www.v2ex.com/t/123456", "atom parser should preserve entry links")
        assert_true(atom_items[0]["published_at"] == "2026-04-07T12:00:00+00:00", "atom parser should preserve ISO timestamps")

        cls_payload = json.dumps(
            {
                "brief": "Line 1\nLine 2",
                "id": 123,
                "ctime": 1775556000,
                "shareurl": "https://api3.cls.cn/share/article/123?os=web&sv=810",
            },
            ensure_ascii=True,
            separators=(",", ":"),
        ).replace("&", "\\u0026")
        cls_items = parse_cls_telegraph_items(
            cls_payload,
            {"max_items": 10},
            datetime(2026, 4, 7, 10, 0, tzinfo=timezone.utc),
        )
        assert_true(len(cls_items) == 1, "cls parser should extract one telegraph item")
        assert_true(cls_items[0]["title"] == "Line 1 Line 2", "cls parser should decode embedded JSON escape sequences")
        assert_true(cls_items[0]["canonical_url"].startswith("https://api3.cls.cn/share/article/123"), "cls parser should preserve a normalized http url")

        cctv_items = build_akshare_news_cctv_items(
            [
                {
                    "date": "20260406",
                    "title": "新闻联播摘要",
                    "content": "宏观政策与消费恢复。",
                }
            ],
            {"max_items": 10},
            datetime(2026, 4, 7, 10, 0, tzinfo=timezone.utc),
        )
        assert_true(len(cctv_items) == 1, "cctv akshare parser should build one item")
        assert_true(cctv_items[0]["published_at"] == "2026-04-06T04:00:00+00:00", "cctv akshare parser should infer a midday timestamp for date-only records")
        assert_true(cctv_items[0]["url"] == "", "cctv akshare parser should tolerate sources without article links")

        cls_akshare_items = build_akshare_stock_info_global_cls_items(
            [
                {
                    "标题": "公司公告快讯",
                    "内容": "公司发布回购公告。",
                    "发布日期": "2026-04-07",
                    "发布时间": "18:41:20",
                }
            ],
            {"max_items": 10},
            datetime(2026, 4, 7, 10, 0, tzinfo=timezone.utc),
        )
        assert_true(len(cls_akshare_items) == 1, "cls akshare parser should build one item")
        assert_true(cls_akshare_items[0]["published_at"] == "2026-04-07T10:41:20+00:00", "cls akshare parser should combine date and time fields in China timezone")

        em_items = build_akshare_stock_info_global_em_items(
            [
                {
                    "标题": "指数期货异动",
                    "摘要": "标普500指数期货跌幅扩大。",
                    "发布时间": "2026-04-07 19:00:33",
                    "链接": "https://finance.eastmoney.com/a/202604073696584783.html?utm_source=test",
                }
            ],
            {"max_items": 10},
            datetime(2026, 4, 7, 10, 0, tzinfo=timezone.utc),
        )
        assert_true(len(em_items) == 1, "eastmoney akshare parser should build one item")
        assert_true(em_items[0]["canonical_url"] == "https://finance.eastmoney.com/a/202604073696584783.html", "eastmoney akshare parser should normalize tracking params from links")
        assert_true(em_items[0]["published_at"] == "2026-04-07T11:00:33+00:00", "eastmoney akshare parser should normalize local timestamps to UTC")

        ths_items = build_akshare_stock_info_global_ths_items(
            [
                {
                    "标题": "同花顺快讯标题",
                    "内容": "同花顺快讯内容摘要。",
                    "发布时间": "2026-04-07 19:04:57",
                    "链接": "https://news.10jqka.com.cn/20260407/c675923678.shtml?utm_source=test",
                }
            ],
            {"max_items": 10},
            datetime(2026, 4, 7, 10, 0, tzinfo=timezone.utc),
        )
        assert_true(len(ths_items) == 1, "ths akshare parser should build one item")
        assert_true(ths_items[0]["canonical_url"] == "https://news.10jqka.com.cn/20260407/c675923678.shtml", "ths akshare parser should normalize tracking params from links")
        assert_true(ths_items[0]["published_at"] == "2026-04-07T11:04:57+00:00", "ths akshare parser should normalize local timestamps to UTC")

        notice_items = build_akshare_stock_notice_report_items(
            [
                {
                    "代码": "300750",
                    "名称": "宁德时代",
                    "公告标题": "关于签署合作框架协议的公告",
                    "公告类型": "重大合同",
                    "公告日期": date(2026, 4, 7),
                    "网址": "https://data.eastmoney.com/notices/detail/300750/AN202604071234567890.html?utm_source=test",
                }
            ],
            {"max_items": 10},
        )
        assert_true(len(notice_items) == 1, "notice akshare parser should build one item")
        assert_true(notice_items[0]["title"] == "宁德时代：关于签署合作框架协议的公告", "notice akshare parser should prefix company name into title")
        assert_true(notice_items[0]["canonical_url"] == "https://data.eastmoney.com/notices/detail/300750/AN202604071234567890.html", "notice akshare parser should normalize tracking params from links")
        assert_true(notice_items[0]["published_at"] == "2026-04-07T04:00:00+00:00", "notice akshare parser should infer a midday timestamp for date-only records")

        cninfo_items = parse_cninfo_items(
            {
                "announcements": [
                    {
                        "secName": "唯科科技",
                        "shortTitle": "第三届董事会第二次会议决议公告",
                        "announcementTime": 1775562138000,
                        "adjunctUrl": "finalpage/2026-04-07/1225083022.PDF",
                    }
                ]
            },
            {"name": "CNINFO Shenzhen Latest Announcements"},
        )
        assert_true(len(cninfo_items) == 1, "cninfo parser should build one item")
        assert_true(cninfo_items[0]["title"] == "唯科科技：第三届董事会第二次会议决议公告", "cninfo parser should join company and announcement title")
        assert_true(cninfo_items[0]["canonical_url"] == "https://static.cninfo.com.cn/finalpage/2026-04-07/1225083022.PDF", "cninfo parser should build the static pdf url")

        html_list_items = parse_html_list_items(
            """
            <html><body>
              <div class="content">
                <div class="tt"><a href="/article/detail/123.html">重大资产重组预案披露</a></div>
                <div class="text">公司拟通过发行股份购买资产。</div>
                <div class="info"><span>证券时报</span><span>19:50</span></div>
              </div>
            </body></html>
            """,
            {
                "url": "https://www.stcn.com/article/list/company.html",
                "item_selector": "div.content",
                "link_selector": ".tt a",
                "title_selector": ".tt a",
                "summary_selector": ".text",
                "published_at_selector": ".info span:last-child",
                "publisher_selector": ".info span:first-child",
                "url_allow_regex": "/article/detail/\\d+\\.html$",
                "max_items": 10,
            },
            datetime(2026, 4, 7, 12, 0, tzinfo=timezone.utc),
        )
        assert_true(len(html_list_items) == 1, "html list parser should build one item")
        assert_true(html_list_items[0]["canonical_url"] == "https://www.stcn.com/article/detail/123.html", "html list parser should join relative urls against the source base url")
        assert_true(html_list_items[0]["summary"].startswith("证券时报："), "html list parser should prefix publisher when available")

        telegram_items = parse_html_list_items(
            """
            <html><body>
              <div class="tgme_widget_message_wrap">
                <a class="tgme_widget_message_date" href="https://t.me/jin10data/1283355"><time datetime="2026-04-07T16:26:49+00:00"></time></a>
                <div class="tgme_widget_message_text">2027年FOMC票委、芝加哥联储主席古尔斯比将于十分钟后就货币政策发表讲话。</div>
              </div>
            </body></html>
            """,
            {
                "url": "https://t.me/s/jin10data",
                "item_selector": ".tgme_widget_message_wrap",
                "link_selector": "a.tgme_widget_message_date",
                "title_selector": ".tgme_widget_message_text",
                "summary_selector": ".tgme_widget_message_text",
                "published_at_selector": "time",
                "published_at_attr": "datetime",
                "url_allow_regex": "https://t\\.me/jin10data/\\d+$",
                "max_items": 10,
            },
            datetime(2026, 4, 7, 17, 0, tzinfo=timezone.utc),
        )
        assert_true(len(telegram_items) == 1, "html list parser should support telegram public channel pages")
        assert_true(telegram_items[0]["canonical_url"] == "https://t.me/jin10data/1283355", "telegram parser should keep the canonical message url")
        assert_true(telegram_items[0]["published_at"] == "2026-04-07T16:26:49+00:00", "telegram parser should preserve the message timestamp")

        marketaux_items = parse_marketaux_items(
            {
                "data": [
                    {
                        "title": "Example Corp agrees to acquire WidgetCo in cash deal",
                        "description": "The companies entered into a definitive agreement.",
                        "url": "https://example.com/news/example-corp-widgetco?utm_source=test",
                        "published_at": "2026-04-07T16:00:00Z",
                        "source": {"name": "Reuters"},
                        "entities": [{"symbol": "EXMP", "name": "Example Corp"}],
                    }
                ]
            },
            {"name": "MarketAux Optional Market Feed", "publisher": "MarketAux", "max_items": 10},
        )
        assert_true(len(marketaux_items) == 1, "marketaux parser should emit one item")
        assert_true(marketaux_items[0]["canonical_url"] == "https://example.com/news/example-corp-widgetco", "marketaux parser should normalize tracking params from urls")
        assert_true(marketaux_items[0]["published_at"] == "2026-04-07T16:00:00+00:00", "marketaux parser should preserve exact timestamps")

        mediastack_items = parse_mediastack_items(
            {
                "data": [
                    {
                        "title": "Example Corp expands Europe retail footprint",
                        "description": "The company plans to open more stores across Europe.",
                        "url": "https://example.com/news/example-corp-europe?utm_medium=test",
                        "published_at": "2026-04-07T16:30:00Z",
                        "source": "CNBC",
                    }
                ]
            },
            {"name": "Mediastack Optional News Feed", "publisher": "Mediastack", "max_items": 10},
        )
        assert_true(len(mediastack_items) == 1, "mediastack parser should emit one item")
        assert_true(mediastack_items[0]["canonical_url"] == "https://example.com/news/example-corp-europe", "mediastack parser should normalize tracking params from urls")
        assert_true(mediastack_items[0]["summary"].startswith("CNBC："), "mediastack parser should prefix the publisher when available")

        serpstack_items = parse_serpstack_items(
            {
                "organic_results": [
                    {
                        "title": "Example Corp explores new financing options",
                        "url": "https://www.marketwatch.com/story/example-corp-financing?utm_campaign=test",
                        "snippet": "People familiar with the matter said the company is evaluating financing options.",
                    }
                ]
            },
            {"name": "Serpstack Company Discovery", "max_items_per_target": 4},
            {"name": "Example Corp"},
        )
        assert_true(len(serpstack_items) == 1, "serpstack parser should emit one item")
        assert_true(serpstack_items[0]["canonical_url"] == "https://www.marketwatch.com/story/example-corp-financing", "serpstack parser should normalize tracking params from urls")
        assert_true("Serpstack 搜索线索：Example Corp" in serpstack_items[0]["summary"], "serpstack parser should carry tracked target context in summaries")

        guba_items = parse_guba_tracked_items(
            """
            <table><tbody class="listbody">
              <tr class="listitem">
                <td><span class="title"><a href="/news,600000,123456.html">据传新增大订单落地</a></span></td>
                <td><span class="read">1234</span></td>
                <td><span class="reply">56</span></td>
                <td><span class="author"><a href="/user/1">产业链观察</a></span></td>
              </tr>
              <tr class="listitem">
                <td><span class="title"><a href="/news,600000,789000.html">午评：明天继续看多</a></span></td>
                <td><span class="read">200</span></td>
                <td><span class="reply">10</span></td>
                <td><span class="author"><a href="/user/2">短线老师</a></span></td>
              </tr>
            </tbody></table>
            """,
            {"max_items_per_board": 6, "url": "https://guba.eastmoney.com/list,600000.html"},
            {"code": "600000", "name": "浦发银行"},
        )
        assert_true(len(guba_items) == 1, "guba parser should keep discovery-like posts and filter noise")
        assert_true("股吧讨论线索：浦发银行" in guba_items[0]["summary"], "guba parser should include tracked company context")

        reddit_items = parse_reddit_listing_items(
            {
                "data": {
                    "children": [
                        {
                            "data": {
                                "title": "What Are Your Moves Tomorrow, April 08, 2026",
                                "permalink": "/r/wallstreetbets/comments/1sf6vyv/what_are_your_moves_tomorrow_april_08_2026/",
                                "author": "wsbapp",
                                "created_utc": 1775591852,
                                "ups": 98,
                                "num_comments": 3782,
                                "selftext": "Daily discussion",
                                "stickied": True,
                            }
                        },
                        {
                            "data": {
                                "title": "Samsung's record Q1 signals further upside on AI memory boom",
                                "permalink": "/r/wallstreetbets/comments/1sf7xyz/samsung_ai_memory/",
                                "author": "macrotrader",
                                "created_utc": 1775594800,
                                "ups": 139,
                                "num_comments": 23,
                                "selftext": "",
                                "url_overridden_by_dest": "https://www.example.com/samsung-ai-memory",
                                "stickied": False,
                                "link_flair_text": "News",
                            }
                        },
                    ]
                }
            },
            {
                "exclude_title_regex": "What Are Your Moves Tomorrow|Daily Discussion",
                "max_items_per_subreddit": 5,
            },
            "wallstreetbets",
        )
        assert_true(len(reddit_items) == 1, "reddit parser should drop stickied daily threads and keep substantive posts")
        assert_true(
            reddit_items[0]["url"] == "https://www.reddit.com/r/wallstreetbets/comments/1sf7xyz/samsung_ai_memory/",
            "reddit parser should canonicalize permalink URLs",
        )
        assert_true(
            "Outbound link: https://www.example.com/samsung-ai-memory" in reddit_items[0]["body_text"],
            "reddit parser should preserve the outbound link in body_text for context",
        )

        reddit_search_items = parse_reddit_search_items(
            {
                "data": {
                    "children": [
                        {
                            "data": {
                                "title": "泡泡玛特：进站加油，换胎再战！",
                                "permalink": "/r/u_Dolphin_research/comments/1s12345/popmart_research/",
                                "author": "u_Dolphin_research",
                                "subreddit": "u_Dolphin_research",
                                "created_utc": 1774491315,
                                "ups": 15,
                                "num_comments": 2,
                                "selftext": "继续跟踪泡泡玛特的经营表现。",
                            }
                        },
                        {
                            "data": {
                                "title": "完全无关的帖子",
                                "permalink": "/r/example/comments/1s11111/other/",
                                "author": "other_user",
                                "subreddit": "example",
                                "created_utc": 1774491315,
                                "ups": 20,
                                "num_comments": 1,
                                "selftext": "与目标无关。",
                            }
                        },
                    ]
                }
            },
            {"max_items_per_target": 3},
            {"name": "泡泡玛特"},
        )
        assert_true(len(reddit_search_items) == 1, "reddit search parser should keep only query-matching posts")
        assert_true(
            "Reddit 搜索线索：泡泡玛特" in reddit_search_items[0]["summary"],
            "reddit search parser should carry tracked target context in summaries",
        )

        xueqiu_items = parse_xueqiu_search_items(
            {
                "list": [
                    {
                        "id": "987654321",
                        "title": "泡泡玛特海外扩张提速",
                        "description": "市场传闻其海外门店扩张计划继续推进，并带来新增订单。",
                        "created_at": "3分钟前",
                        "retweet_count": 11,
                        "reply_count": 8,
                        "like_count": 35,
                        "user": {"id": "12345", "screen_name": "产业链跟踪"},
                    },
                    {
                        "id": "123000000",
                        "title": "午评：继续看多泡泡玛特",
                        "description": "短线继续看多。",
                        "created_at": "5分钟前",
                        "user": {"id": "54321", "screen_name": "短线老师"},
                    },
                ]
            },
            {"max_items_per_target": 4},
            datetime(2026, 4, 7, 12, 0, tzinfo=timezone.utc),
            {"name": "泡泡玛特", "ticker": "9992.HK", "region": "HK"},
            ("传闻", "订单", "扩张", "扩产"),
        )
        assert_true(len(xueqiu_items) == 1, "xueqiu parser should keep discovery-like posts and filter market-noise chatter")
        assert_true(xueqiu_items[0]["canonical_url"] == "https://xueqiu.com/12345/987654321", "xueqiu parser should build a stable canonical status url")
        assert_true("雪球讨论线索：泡泡玛特" in xueqiu_items[0]["summary"], "xueqiu parser should include tracked company context")

        xueqiu_public_items = parse_xueqiu_public_timeline_items(
            {
                "list": [
                    {
                        "data": json.dumps(
                            {
                                "id": 382784111,
                                "title": "关于自由现金流类指数的一些思考",
                                "description": "帖子正文内容",
                                "target": "/6828304753/382784111",
                                "reply_count": 44,
                                "retweet_count": 7,
                                "like_count": 165,
                                "created_at": 1775521466000,
                                "user": {"screen_name": "躺师傅"},
                            },
                            ensure_ascii=False,
                        )
                    }
                ]
            },
            {"max_items": 10},
            datetime(2026, 4, 7, 12, 0, tzinfo=timezone.utc),
        )
        assert_true(len(xueqiu_public_items) == 1, "xueqiu public timeline parser should emit one post")
        assert_true(xueqiu_public_items[0]["canonical_url"] == "https://xueqiu.com/6828304753/382784111", "xueqiu public timeline parser should build canonical post urls")
        assert_true("雪球热帖线索" in xueqiu_public_items[0]["summary"], "xueqiu public timeline parser should emit signal-oriented summaries")

        xueqiu_hot_stock_items = parse_xueqiu_hot_stock_items(
            {
                "data": {
                    "items": [
                        {
                            "symbol": "NVDA",
                            "code": "NVDA",
                            "name": "英伟达",
                            "value": 1856.0,
                            "current": 178.1,
                            "percent": 0.26,
                        }
                    ]
                }
            },
            {"max_items": 10},
            datetime(2026, 4, 7, 12, 0, tzinfo=timezone.utc),
        )
        assert_true(len(xueqiu_hot_stock_items) == 1, "xueqiu hot stock parser should emit one leaderboard signal")
        assert_true(xueqiu_hot_stock_items[0]["canonical_url"] == "https://xueqiu.com/S/NVDA", "xueqiu hot stock parser should point back to the stock page")
        assert_true("雪球热股榜第 1 位" in xueqiu_hot_stock_items[0]["summary"], "xueqiu hot stock parser should preserve leaderboard rank context")

        resolver_tmp = tempfile.TemporaryDirectory()
        try:
            watchlist_path = Path(resolver_tmp.name) / "watchlist.csv"
            watchlist_path.write_text(
                "ticker,name,status\n9992.HK,泡泡玛特,active\n9961.HK,携程集团,active\n603616.SH,韩建河山,active\n301362.SZ,民爆光电,active\n",
                encoding="utf-8",
            )
            export_root = Path(resolver_tmp.name) / "consumer_exports"
            export_root.mkdir(parents=True, exist_ok=True)
            (export_root / "research_feed_latest.json").write_text(
                json.dumps(
                    {
                        "entity_index": {
                            "泡泡玛特": [],
                            "韩建河山": [],
                            "民爆光电": [],
                            "Broadcom": [],
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (export_root / "opportunity_report_feed_latest.json").write_text(
                json.dumps(
                    {
                        "opportunity_buckets": {
                            "new_opportunity_candidates": [{"primary_entity": "携程集团", "companies": ["携程集团"]}],
                            "tracking_updates": [],
                            "watchlist_candidates": [{"primary_entity": "泡泡玛特", "companies": ["泡泡玛特"]}],
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            watchlist_targets = build_watchlist_targets(watchlist_path)
            assert_true(len(watchlist_targets) == 4, "watchlist resolver should load active tracked rows")
            hk_targets = resolve_shared_targets({"type": "hkex_tracked"}, export_root, watchlist_path)
            cn_targets = resolve_shared_targets({"type": "guba_tracked_html"}, export_root, watchlist_path)
            weibo_targets = resolve_shared_targets({"type": "weibo_mobile_search", "max_targets": 8}, export_root, watchlist_path)
            xueqiu_targets = resolve_shared_targets({"type": "xueqiu_status_search", "max_targets": 8}, export_root, watchlist_path)
            xueqiu_dom_targets = resolve_shared_targets({"type": "xueqiu_dom_search", "max_targets": 8}, export_root, watchlist_path)
            serpstack_targets = resolve_shared_targets({"type": "serpstack_search_json", "target_names": ["Morimatsu", "泡泡玛特"], "max_targets": 8}, export_root, watchlist_path)
            assert_true([item["code"] for item in hk_targets] == ["09992", "09961"], "hkex resolver should keep HK watchlist codes")
            assert_true(sorted(item["code"] for item in cn_targets) == ["301362", "603616"], "guba resolver should keep CN watchlist codes")
            assert_true(any(item["name"] == "泡泡玛特" for item in weibo_targets), "weibo resolver should include Chinese watchlist names")
            assert_true(all(item["name"] != "Broadcom" for item in weibo_targets), "weibo resolver should ignore non-Chinese names for mobile search")
            assert_true(any(item["name"] == "携程集团" for item in xueqiu_targets), "xueqiu resolver should reuse shared Chinese tracked names")
            assert_true(all(item["name"] != "Broadcom" for item in xueqiu_targets), "xueqiu resolver should ignore non-Chinese feed entities")
            assert_true(any(item["name"] == "泡泡玛特" for item in xueqiu_dom_targets), "xueqiu dom resolver should reuse shared Chinese tracked names")
            serpstack_names = [item["name"] for item in serpstack_targets]
            assert_true(serpstack_names[:2] == ["Morimatsu", "泡泡玛特"], "serpstack resolver should prioritize explicit multilingual targets without forcing Chinese-only filtering")
            explicit_targets = resolve_shared_targets(
                {"type": "reddit_search_json", "target_names": ["Morimatsu", "泡泡玛特"], "max_targets": 8},
                Path(resolver_tmp.name) / "missing_consumer_exports",
                Path(resolver_tmp.name) / "missing_watchlist.csv",
            )
            explicit_hk_targets = resolve_shared_targets(
                {"type": "hkex_tracked", "explicit_targets": [{"name": "泡泡玛特", "ticker": "9992.HK", "region": "HK"}]},
                Path(resolver_tmp.name) / "missing_consumer_exports",
                Path(resolver_tmp.name) / "missing_watchlist.csv",
            )
            explicit_cn_targets = resolve_shared_targets(
                {"type": "guba_tracked_html", "explicit_targets": [{"name": "民爆光电", "ticker": "301362.SZ", "region": "CN"}]},
                Path(resolver_tmp.name) / "missing_consumer_exports",
                Path(resolver_tmp.name) / "missing_watchlist.csv",
            )
            assert_true(
                [item["name"] for item in explicit_targets] == ["Morimatsu", "泡泡玛特"],
                "explicit target names should seed tracked search even without watchlist or consumer exports",
            )
            assert_true(explicit_hk_targets[0]["code"] == "09992", "explicit hk targets should resolve exchange code for on-demand discovery")
            assert_true(explicit_cn_targets[0]["code"] == "301362", "explicit cn targets should resolve board code for on-demand discovery")
        finally:
            resolver_tmp.cleanup()

        xueqiu_missing_state_tmp = tempfile.TemporaryDirectory()
        try:
            missing_export_root = Path(xueqiu_missing_state_tmp.name) / "consumer_exports"
            missing_export_root.mkdir(parents=True, exist_ok=True)
            (missing_export_root / "research_feed_latest.json").write_text(
                json.dumps({"entity_index": {"泡泡玛特": []}}, ensure_ascii=False),
                encoding="utf-8",
            )
            (missing_export_root / "opportunity_report_feed_latest.json").write_text(
                json.dumps({"opportunity_buckets": {}}, ensure_ascii=False),
                encoding="utf-8",
            )
            missing_watchlist = Path(xueqiu_missing_state_tmp.name) / "watchlist.csv"
            missing_watchlist.write_text("ticker,name,status\n9992.HK,泡泡玛特,active\n", encoding="utf-8")
            xueqiu_items, xueqiu_error = fetch_source(
                requests.Session(),
                {
                    "source_id": "xueqiu_tracked_search",
                    "type": "xueqiu_status_search",
                    "consumer_export_root": str(missing_export_root),
                    "watchlist_registry": str(missing_watchlist),
                    "storage_state_path": str(Path(xueqiu_missing_state_tmp.name) / "missing_state.json"),
                    "max_targets": 2,
                    "pages": 1,
                    "count": 10,
                    "source": "user",
                },
                datetime(2026, 4, 7, 12, 0, tzinfo=timezone.utc),
            )
            assert_true(xueqiu_items == [], "xueqiu fetch should return no items when shared auth state is missing")
            assert_true(str(xueqiu_error).startswith("missing_xueqiu_storage_state:"), "xueqiu fetch should surface missing shared auth state explicitly")
        finally:
            xueqiu_missing_state_tmp.cleanup()

        original_marketaux = os.environ.pop("MARKETAUX_API_KEY", None)
        try:
            merged_sources = merge_sources(
                {
                    "keep_source": {"enabled": True, "phase1_disposition": "migrate_phase1", "scheduler_class": "high_freq"},
                    "disabled_source": {"enabled": False, "phase1_disposition": "migrate_phase1", "scheduler_class": "high_freq"},
                    "wrong_phase": {"enabled": True, "phase1_disposition": "ignore", "scheduler_class": "high_freq"},
                    "env_gated": {"enabled": True, "phase1_disposition": "migrate_phase1", "scheduler_class": "high_freq"},
                },
                [
                    {"key": "keep_source", "type": "rss"},
                    {"key": "disabled_source", "type": "rss"},
                    {"key": "wrong_phase", "type": "rss"},
                    {"key": "env_gated", "type": "marketaux_json", "enabled_if_env": "MARKETAUX_API_KEY"},
                ],
                scheduler_classes={"high_freq"},
                source_ids=None,
            )
            assert_true([row["source_id"] for row in merged_sources] == ["keep_source"], "merge_sources should keep only enabled phase-1 sources matching the scheduler filter")

            gated_sources = merge_sources(
                {"env_gated": {"enabled": True, "phase1_disposition": "migrate_phase1", "scheduler_class": "high_freq"}},
                [{"key": "env_gated", "type": "marketaux_json", "enabled_if_env": "MARKETAUX_API_KEY"}],
                scheduler_classes={"high_freq"},
                source_ids=None,
            )
            assert_true(gated_sources == [], "env-gated source should be skipped when its key is missing")
            os.environ["MARKETAUX_API_KEY"] = "test-token"
            gated_sources = merge_sources(
                {"env_gated": {"enabled": True, "phase1_disposition": "migrate_phase1", "scheduler_class": "high_freq"}},
                [{"key": "env_gated", "type": "marketaux_json", "enabled_if_env": "MARKETAUX_API_KEY"}],
                scheduler_classes={"high_freq"},
                source_ids=None,
            )
            assert_true([row["source_id"] for row in gated_sources] == ["env_gated"], "env-gated source should join the live set once the key exists")
        finally:
            if original_marketaux is None:
                os.environ.pop("MARKETAUX_API_KEY", None)
            else:
                os.environ["MARKETAUX_API_KEY"] = original_marketaux

        bootstrap_tmp_dir = tempfile.TemporaryDirectory()
        bootstrap_db_path = Path(bootstrap_tmp_dir.name) / "bootstrap.db"
        bootstrap_conn = open_db(str(bootstrap_db_path))
        try:
            ensure_bootstrap(bootstrap_conn, SCHEMA_PATH, load_registry(ROOT / "config" / "source_registry_v1.yaml"))
            bootstrap_conn.commit()
            registry_rows = bootstrap_conn.execute("SELECT COUNT(*) FROM source_registry").fetchone()[0]
            assert_true(int(registry_rows) > 0, "bootstrap should seed source_registry from the YAML registry, not just apply schema")
        finally:
            bootstrap_conn.close()
            bootstrap_tmp_dir.cleanup()

        ok_source = {
            "source_id": "ok_source",
            "scheduler_class": "high_freq",
            "min_interval_minutes": 10,
            "max_age_hours": 6,
        }
        bad_source = {
            "source_id": "bad_source",
            "scheduler_class": "high_freq",
            "min_interval_minutes": 10,
            "max_age_hours": 6,
        }

        def stub_process(conn: sqlite3.Connection, _session: object, current_source: dict, current_run_dt: datetime) -> dict:
            if current_source["source_id"] == "bad_source":
                raise RuntimeError("simulated source failure")
            action = upsert_article(
                conn,
                current_source,
                {
                    "title": "批处理成功标题",
                    "summary": "ok summary",
                    "body_text": "ok summary",
                    "url": f"https://example.com/{current_source['source_id']}",
                    "canonical_url": f"https://example.com/{current_source['source_id']}",
                    "published_at": "2026-04-07T10:09:00+00:00",
                },
                "2026-04-07T10:09:30+00:00",
            )
            record_source_health(conn, str(current_source["source_id"]), "ok", None)
            return {
                "source_id": str(current_source["source_id"]),
                "status": "ok",
                "fetched_items": 1,
                "eligible_items": 1,
                "inserted": 1 if action == "inserted" else 0,
                "updated": 1 if action == "updated" else 0,
                "duplicate": 1 if action == "duplicate" else 0,
                "skipped": 1 if action == "skipped" else 0,
                "error": None,
            }

        conn.commit()
        batch_results = run_due_sources(
            conn,
            None,
            [ok_source, bad_source],
            datetime(2026, 4, 7, 10, 10, tzinfo=timezone.utc),
            process_fn=stub_process,
        )
        ok_articles = conn.execute("SELECT COUNT(*) FROM news_articles WHERE source_id = 'ok_source'").fetchone()[0]
        bad_health = conn.execute(
            "SELECT status FROM source_health WHERE source_id = 'bad_source' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert_true(int(ok_articles) == 1, "a later source failure should not roll back the earlier source's persisted article rows")
        assert_true(bad_health is not None and bad_health[0] == "down", "unhandled per-source failures should still leave a down health record behind")
        assert_true([row["status"] for row in batch_results] == ["ok", "down"], "batch processing should isolate source failures instead of failing the whole run")

        lock_tmp_dir = tempfile.TemporaryDirectory()
        lock_db_path = Path(lock_tmp_dir.name) / "lock_test.db"
        lock_conn = open_db(str(lock_db_path))
        race_conn = open_db(str(lock_db_path))
        try:
            ensure_bootstrap(lock_conn, SCHEMA_PATH, {"ok_source": {
                "source_id": "ok_source",
                "name": "OK Source",
                "lane": "confirmation",
                "source_type": "rss",
                "trust_tier": 1,
                "coverage_scope": "mixed",
                "collector_owner": "shared",
                "scheduler_class": "high_freq",
                "origin_system": "news_event_hub",
                "legacy_key": "ok_source",
                "phase1_disposition": "migrate_phase1",
                "enabled": True,
                "description": "",
            }})
            lock_conn.commit()
            lock_conn.execute("BEGIN IMMEDIATE")
            locked_results = run_due_sources(
                race_conn,
                None,
                [ok_source],
                datetime(2026, 4, 7, 10, 11, tzinfo=timezone.utc),
                process_fn=stub_process,
            )
            assert_true(locked_results[0]["status"] == "skipped", "sqlite writer lock should be treated as a collector skip, not a source down")
        finally:
            lock_conn.rollback()
            lock_conn.close()
            race_conn.close()
            lock_tmp_dir.cleanup()

        assert_true(classify_source_health(source, 0, 0) == ("degraded", "collector fetched 0 items"), "empty fetch should degrade source health")
        assert_true(
            classify_source_health(source, 5, 0) == ("degraded", "collector fetched items but none within 6h freshness window"),
            "stale-only fetch should degrade source health",
        )
        assert_true(classify_source_health(source, 5, 2) == ("ok", None), "fresh eligible items should keep source health ok")

        original_fetch_source = live_collector.fetch_source
        try:
            def partial_fetch(_session: requests.Session, _source: dict, _run_dt: datetime):
                return (
                    [
                        {
                            "title": "局部成功条目",
                            "summary": "partial ok",
                            "body_text": "partial ok",
                            "url": "https://example.com/partial",
                            "canonical_url": "https://example.com/partial",
                            "published_at": "2026-04-07T10:00:00+00:00",
                        }
                    ],
                    "Morimatsu:503 Service Unavailable",
                )

            live_collector.fetch_source = partial_fetch
            partial_source = {
                "source_id": "test_source",
                "scheduler_class": "high_freq",
                "min_interval_minutes": 10,
                "max_age_hours": 6,
            }
            partial_result = live_collector.process_source(
                conn,
                requests.Session(),
                partial_source,
                datetime(2026, 4, 7, 12, 0, tzinfo=timezone.utc),
            )
            partial_count = conn.execute(
                "SELECT COUNT(*) FROM news_articles WHERE source_id = 'test_source' AND title = '局部成功条目'"
            ).fetchone()[0]
            latest_health = conn.execute(
                "SELECT status, error_message FROM source_health WHERE source_id = 'test_source' ORDER BY id DESC LIMIT 1"
            ).fetchone()
            assert_true(partial_result["status"] == "degraded", "partial fetch errors should degrade rather than drop successful tracked items")
            assert_true(int(partial_count) == 1, "partial fetch errors should still persist successful items")
            assert_true(
                latest_health is not None and latest_health[0] == "degraded" and "Morimatsu:503 Service Unavailable" in str(latest_health[1]),
                "partial fetch errors should be preserved in source health records",
            )
        finally:
            live_collector.fetch_source = original_fetch_source
    finally:
        conn.close()

    print("live_collector_smoke_ok")


if __name__ == "__main__":
    main()
