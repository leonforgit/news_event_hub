#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import run_company_discovery as company_discovery


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    tmp_dir = tempfile.TemporaryDirectory()
    try:
        db_path = Path(tmp_dir.name) / "discovery.db"
        output_root = Path(tmp_dir.name) / "consumer_exports"
        report_root = Path(tmp_dir.name) / "reports"
        recent_ts = datetime.now(timezone.utc).replace(microsecond=0).isoformat(timespec="seconds")

        registry = company_discovery.load_registry(company_discovery.DEFAULT_REGISTRY)
        catalog_map = company_discovery.load_catalog_map(company_discovery.DEFAULT_CATALOG)
        target = company_discovery.build_target("泡泡玛特", ["Pop Mart"], "9992.HK", "HK")
        live_ids, browser_ids = company_discovery.source_ids_for_target(target)
        assert_true("serpstack_company_discovery_optional" in live_ids, "company discovery should include the Serpstack backend in global live discovery candidates")
        assert_true("xueqiu_tracked_search" in browser_ids, "company discovery should still keep browser-backed Xueqiu discovery for HK targets")
        macro_target = company_discovery.build_target(
            "欧盟芯片补贴",
            ["芯片补贴"],
            "",
            "GLOBAL",
            entity_type="macro_theme",
            route_key="macro",
        )
        macro_live_ids, macro_browser_ids = company_discovery.source_ids_for_target(macro_target)
        assert_true("reuters_macro_bing" in macro_live_ids, "macro discovery should include macro confirmation sources")
        assert_true(not macro_browser_ids, "macro discovery should not depend on browser-only sources by default")

        serpstack_source = company_discovery.build_source("serpstack_company_discovery_optional", registry, catalog_map)
        configured_serpstack = company_discovery.configure_source(
            serpstack_source,
            target,
            argparse.Namespace(
                consumer_export_root=output_root,
                watchlist_registry=company_discovery.DEFAULT_WATCHLIST_REGISTRY,
                weibo_state_path=company_discovery.DEFAULT_WEIBO_STATE,
                storage_state_path=company_discovery.DEFAULT_AGENT_REACH_STATE,
            ),
        )
        assert_true(configured_serpstack["type"] == "serpstack_search_json", "company discovery should register the Serpstack source from the shared catalog")
        assert_true(configured_serpstack["explicit_targets"][0]["name"] == "泡泡玛特", "configured Serpstack source should carry explicit discovery targets")

        original_source_ids_for_target = company_discovery.source_ids_for_target
        original_fetch_source = company_discovery.fetch_source
        original_execute_xueqiu_dom_fetch = company_discovery.execute_xueqiu_dom_fetch
        try:
            def stub_source_ids_for_target(target):
                if target.route_key == "macro":
                    return (["reuters_macro_bing", "reddit_market_forums"], [])
                return (
                    ["reuters_company_bing", "reddit_tracked_search"],
                    ["xueqiu_tracked_search"],
                )

            company_discovery.source_ids_for_target = stub_source_ids_for_target

            def stub_fetch_source(_session, source, _run_dt):
                if source["source_id"] == "reuters_company_bing":
                    return (
                        [
                            {
                                "title": "泡泡玛特拟扩大美国直营网点",
                                "summary": "泡泡玛特拟扩大美国直营网点，并继续推进海外门店扩张。",
                                "body_text": "泡泡玛特拟扩大美国直营网点，并继续推进海外门店扩张。",
                                "url": "https://www.reuters.com/world/china/pop-mart-us-stores/",
                                "canonical_url": "https://www.reuters.com/world/china/pop-mart-us-stores/",
                                "published_at": recent_ts,
                            }
                        ],
                        None,
                    )
                if source["source_id"] == "reddit_tracked_search":
                    return (
                        [
                            {
                                "title": "泡泡玛特在美国门店排队热度继续提升",
                                "summary": "Reddit 用户讨论泡泡玛特在美国门店的排队热度。",
                                "body_text": "Reddit 用户讨论泡泡玛特在美国门店的排队热度。",
                                "url": "https://www.reddit.com/r/stocks/comments/test/pop_mart_us_store/",
                                "canonical_url": "https://www.reddit.com/r/stocks/comments/test/pop_mart_us_store/",
                                "published_at": recent_ts,
                            }
                        ],
                        None,
                    )
                if source["source_id"] == "reuters_macro_bing":
                    return (
                        [
                            {
                                "title": "欧盟推进芯片补贴框架进入执行阶段",
                                "summary": "欧盟推进芯片补贴框架进入执行阶段，市场关注半导体资本开支与区域供给变化。",
                                "body_text": "欧盟推进芯片补贴框架进入执行阶段，市场关注半导体资本开支与区域供给变化。",
                                "url": "https://www.reuters.com/world/europe/eu-chip-subsidy-framework/",
                                "canonical_url": "https://www.reuters.com/world/europe/eu-chip-subsidy-framework/",
                                "published_at": recent_ts,
                            }
                        ],
                        None,
                    )
                if source["source_id"] == "reddit_market_forums":
                    return (
                        [
                            {
                                "title": "欧洲芯片补贴会不会改变半导体资本开支格局？",
                                "summary": "论坛用户讨论欧洲芯片补贴对半导体行业的影响。",
                                "body_text": "论坛用户讨论欧洲芯片补贴对半导体行业的影响。",
                                "url": "https://www.reddit.com/r/investing/comments/test/eu_chip_subsidy/",
                                "canonical_url": "https://www.reddit.com/r/investing/comments/test/eu_chip_subsidy/",
                                "published_at": recent_ts,
                            }
                        ],
                        None,
                    )
                return ([], None)

            def stub_execute_xueqiu_dom_fetch(source, _run_dt, _storage_state_path):
                assert_true(source["source_id"] == "xueqiu_tracked_search", "browser discovery should use xueqiu tracked search source")
                return (
                    [
                        {
                            "title": "泡泡玛特北美门店扩张观察",
                            "summary": "雪球用户讨论泡泡玛特北美扩张。",
                            "body_text": "雪球用户讨论泡泡玛特北美扩张。",
                            "url": "https://xueqiu.com/111/222",
                            "canonical_url": "https://xueqiu.com/111/222",
                            "published_at": recent_ts,
                        }
                    ],
                    None,
                )

            company_discovery.fetch_source = stub_fetch_source
            company_discovery.execute_xueqiu_dom_fetch = stub_execute_xueqiu_dom_fetch

            args = argparse.Namespace(
                company="泡泡玛特",
                target_name="",
                aliases=["Pop Mart"],
                search_terms=None,
                ticker="9992.HK",
                region="HK",
                entity_type="company",
                route_key="company",
                db=db_path,
                schema=company_discovery.DEFAULT_SCHEMA,
                registry=company_discovery.DEFAULT_REGISTRY,
                catalog=company_discovery.DEFAULT_CATALOG,
                browser_catalog=company_discovery.DEFAULT_BROWSER_CATALOG,
                consumer_export_root=output_root,
                watchlist_registry=company_discovery.DEFAULT_WATCHLIST_REGISTRY,
                weibo_state_path=company_discovery.DEFAULT_WEIBO_STATE,
                storage_state_path=company_discovery.DEFAULT_AGENT_REACH_STATE,
                rebuild_lookback_days=365,
                export_lookback_hours=24 * 30,
                research_limit=180,
                article_limit=12,
                event_limit=6,
                output_dir=report_root,
                output_file=None,
            )

            result = company_discovery.run_discovery(args)

            assert_true(result["routing"]["entrypoint"] == "scripts/run_company_discovery.py", "company discovery should echo the shared discovery entrypoint in its result contract")
            assert_true("reuters_company_bing" in result["routing"]["live_source_ids"], "company discovery routing should expose selected live sources")
            assert_true(result["coverage_after"]["matching_articles"] >= 3, "discovery should persist matched articles back into the shared db")
            assert_true(result["coverage_after"]["matching_events"] >= 1, "discovery should rebuild at least one matching event")
            assert_true(len(result["research"]["articles"]) >= 3, "research payload should return matched articles")
            assert_true(len(result["research"]["events"]) >= 1, "research payload should return matching events")

            with sqlite3.connect(db_path) as conn:
                article_count = conn.execute(
                    "SELECT COUNT(*) FROM news_articles WHERE source_id IN ('reuters_company_bing', 'reddit_tracked_search', 'xueqiu_tracked_search')"
                ).fetchone()[0]
                event_count = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
            assert_true(int(article_count) >= 3, "discovery should insert source articles into news_articles")
            assert_true(int(event_count) >= 1, "event rebuild should materialize events into the shared db")
            assert_true((output_root / "research_feed_latest.json").exists(), "discovery should refresh shared consumer exports")

            macro_args = argparse.Namespace(
                company="",
                target_name="欧盟芯片补贴",
                aliases=["芯片补贴"],
                search_terms=["欧洲半导体补贴"],
                ticker="",
                region="GLOBAL",
                entity_type="macro_theme",
                route_key="macro",
                db=db_path,
                schema=company_discovery.DEFAULT_SCHEMA,
                registry=company_discovery.DEFAULT_REGISTRY,
                catalog=company_discovery.DEFAULT_CATALOG,
                browser_catalog=company_discovery.DEFAULT_BROWSER_CATALOG,
                consumer_export_root=output_root,
                watchlist_registry=company_discovery.DEFAULT_WATCHLIST_REGISTRY,
                weibo_state_path=company_discovery.DEFAULT_WEIBO_STATE,
                storage_state_path=company_discovery.DEFAULT_AGENT_REACH_STATE,
                rebuild_lookback_days=365,
                export_lookback_hours=24 * 30,
                research_limit=180,
                article_limit=12,
                event_limit=6,
                output_dir=report_root,
                output_file=None,
            )
            macro_result = company_discovery.run_discovery(macro_args)
            assert_true(macro_result["query"]["route_key"] == "macro", "generic discovery should preserve the executed route key")
            assert_true(macro_result["routing"]["is_executable"] is True, "macro discovery routes should now be executable, not contract-only")
            assert_true("reuters_macro_bing" in macro_result["routing"]["live_source_ids"], "macro discovery result should expose the selected macro confirmation sources")
            assert_true(macro_result["coverage_after"]["matching_articles"] >= 2, "macro discovery should persist matched macro articles back into the shared db")
        finally:
            company_discovery.source_ids_for_target = original_source_ids_for_target
            company_discovery.fetch_source = original_fetch_source
            company_discovery.execute_xueqiu_dom_fetch = original_execute_xueqiu_dom_fetch
    finally:
        tmp_dir.cleanup()

    print("company_discovery_smoke_ok")


if __name__ == "__main__":
    main()
