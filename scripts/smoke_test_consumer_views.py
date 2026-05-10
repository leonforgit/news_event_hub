#!/usr/bin/env python3
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from export_consumer_views import build_exports


ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = ROOT / "config" / "schema.sql"


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def open_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    return conn


def seed_source_registry(conn: sqlite3.Connection) -> None:
    conn.executemany(
        """
        INSERT INTO source_registry (
            source_id, name, lane, source_family, source_type, trust_tier, coverage_scope,
            collector_owner, scheduler_class, origin_system, legacy_key,
            phase1_disposition, enabled, description
        ) VALUES (?, ?, ?, ?, ?, ?, ?, 'shared', 'high_freq', 'news_event_hub', ?, 'migrate_phase1', 1, '')
        """,
        [
            ("cninfo_sz_latest", "Cninfo SZ", "confirmation", "exchange:cninfo", "exchange", 1, "company", "cninfo_sz_latest"),
            ("prnewswire_company_a", "PR Newswire Company A", "confirmation", "wire:prnewswire", "rss", 1, "company", "prnewswire_company_a"),
            ("prnewswire_company_b", "PR Newswire Company B", "confirmation", "wire:prnewswire", "rss", 1, "company", "prnewswire_company_b"),
            ("macro_wire", "Macro Wire", "confirmation", "media:macro", "rss", 1, "macro", "macro_wire"),
            ("signal_x", "Signal X", "signal", "social:rumor", "social", 3, "mixed", "signal_x"),
        ],
    )


def seed_articles(conn: sqlite3.Connection) -> None:
    conn.executemany(
        """
        INSERT INTO news_articles (
            article_id, source_id, title, title_norm, summary, body_text,
            url, canonical_url, published_at, timestamp_quality,
            content_hash, language, collector_scope, collected_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'exact', ?, 'zh', 'baseline_shared', ?)
        """,
        [
            (
                "art_chip_1",
                "cninfo_sz_latest",
                "台积电公告：将投资120亿元加码先进封装产能",
                "台积电公告：将投资120亿元加码先进封装产能",
                "summary",
                "body",
                "https://example.com/chip-1",
                "https://example.com/chip-1",
                "2026-04-07T09:10:00+00:00",
                "hash_chip_1",
                "2026-04-07T09:11:00+00:00",
            ),
            (
                "art_chip_2",
                "prnewswire_company_a",
                "台积电将投资120亿元扩充先进封装产能",
                "台积电将投资120亿元扩充先进封装产能",
                "summary",
                "body",
                "https://example.com/chip-2",
                "https://example.com/chip-2",
                "2026-04-07T09:12:00+00:00",
                "hash_chip_2",
                "2026-04-07T09:13:00+00:00",
            ),
            (
                "art_chip_3",
                "prnewswire_company_b",
                "台积电扩充先进封装产能计划获更多细节披露",
                "台积电扩充先进封装产能计划获更多细节披露",
                "summary",
                "body",
                "https://example.com/chip-3",
                "https://example.com/chip-3",
                "2026-04-07T09:14:00+00:00",
                "hash_chip_3",
                "2026-04-07T09:15:00+00:00",
            ),
            (
                "art_macro_1",
                "macro_wire",
                "美联储官员称需继续观察通胀",
                "美联储官员称需继续观察通胀",
                "summary",
                "body",
                "https://example.com/macro-1",
                "https://example.com/macro-1",
                "2026-04-07T08:30:00+00:00",
                "hash_macro_1",
                "2026-04-07T08:31:00+00:00",
            ),
            (
                "art_rejected",
                "signal_x",
                "传闻某题材热度上升",
                "传闻某题材热度上升",
                "summary",
                "body",
                "https://example.com/rejected",
                "https://example.com/rejected",
                "2026-04-07T08:20:00+00:00",
                "hash_rejected",
                "2026-04-07T08:21:00+00:00",
            ),
            (
                "art_music_noise",
                "prnewswire_company_a",
                "The Temptations to Headline Licensing Expo’s Opening Night Party in Las Vegas",
                "the temptations to headline licensing expo’s opening night party in las vegas",
                "summary",
                "body",
                "https://example.com/music-noise",
                "https://example.com/music-noise",
                "2026-04-07T09:00:00+00:00",
                "hash_music_noise",
                "2026-04-07T09:01:00+00:00",
            ),
            (
                "art_bank_1",
                "prnewswire_company_a",
                "Northwest Bank launches regional SMB lending program",
                "northwest bank launches regional smb lending program",
                "summary",
                "body",
                "https://example.com/bank-1",
                "https://example.com/bank-1",
                "2026-04-06T13:00:00+00:00",
                "hash_bank_1",
                "2026-04-06T13:01:00+00:00",
            ),
            (
                "art_ai_noise",
                "prnewswire_company_a",
                "【电报解读】AI电力需求重塑能源融资格局，该产业或是解决AI能源需求的关键方案",
                "ai电力需求重塑能源融资格局，该产业或是解决ai能源需求的关键方案",
                "summary",
                "body",
                "https://example.com/ai-noise",
                "https://example.com/ai-noise",
                "2026-04-06T14:00:00+00:00",
                "hash_ai_noise",
                "2026-04-06T14:01:00+00:00",
            ),
            (
                "art_persistent_1",
                "macro_wire",
                "欧盟推进芯片补贴框架进入执行阶段",
                "欧盟推进芯片补贴框架进入执行阶段",
                "summary",
                "body",
                "https://example.com/persistent-chip-policy",
                "https://example.com/persistent-chip-policy",
                "2026-04-02T09:00:00+00:00",
                "hash_persistent_chip_policy",
                "2026-04-02T09:01:00+00:00",
            ),
        ],
    )


def seed_events(conn: sqlite3.Connection) -> None:
    conn.executemany(
        """
        INSERT INTO events (
            event_id, event_title, event_type, first_seen_at, last_seen_at,
            topic_key, event_state, novelty_state, confirmation_count, source_mix, score_vector,
            calibrated_confirmation, uncertainty, article_count_raw, independent_evidence_count,
            source_family_count, signal_platform_count, primary_industry,
            primary_entity, event_rank_score, event_rank_flags, opportunity_state
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                "evt_chip_keep",
                "台积电加码先进封装产能",
                "production_supply",
                "2026-04-07T09:10:00+00:00",
                "2026-04-07T09:14:00+00:00",
                "company:tsmc",
                "confirmed",
                "new",
                2,
                '{"confirmation": 2, "signal": 0}',
                '{"market_significance": 0.62, "entity_impact": 0.94, "entity_local_priority": 0.95, "researchability": 0.88, "novelty": 0.80, "coverage_independent": 0.45}',
                0.82,
                0.18,
                3,
                2,
                2,
                0,
                "半导体",
                "台积电",
                68.5,
                '{"event_state_reason": "confirmed_by_independent_facts", "update_count": 2, "latest_update_signature": "先进封装产能计划获更多细节披露", "recent_updates": [{"update_signature": "先进封装产能计划获更多细节披露", "title": "台积电扩充先进封装产能计划获更多细节披露", "published_at": "2026-04-07T09:14:00+00:00", "source_id": "prnewswire_company_b"}, {"update_signature": "将投资120亿元扩充先进封装产能", "title": "台积电将投资120亿元扩充先进封装产能", "published_at": "2026-04-07T09:12:00+00:00", "source_id": "prnewswire_company_a"}], "flags": {"structural_event": true, "ongoing_topic": false}}',
                "unreviewed",
            ),
            (
                "evt_macro_keep",
                "美联储官员称需继续观察通胀",
                "macro_data",
                "2026-04-07T08:30:00+00:00",
                "2026-04-07T08:30:00+00:00",
                "macro:fed",
                "emerging",
                "developing",
                1,
                '{"confirmation": 1, "signal": 0}',
                '{"market_significance": 0.86, "entity_impact": 0.22, "entity_local_priority": 0.24, "researchability": 0.28, "novelty": 0.75, "coverage_independent": 0.30}',
                0.58,
                0.30,
                1,
                1,
                1,
                0,
                "",
                "",
                72.0,
                '{"event_state_reason": "single_confirmation_pending_breadth", "flags": {"structural_event": false, "ongoing_topic": true}}',
                "unreviewed",
            ),
            (
                "evt_rejected",
                "传闻某题材热度上升",
                "social_signal",
                "2026-04-07T08:20:00+00:00",
                "2026-04-07T08:20:00+00:00",
                "industry:consumer-electronics",
                "watch",
                "new",
                1,
                '{"confirmation": 0, "signal": 1}',
                '{"market_significance": 0.20, "entity_impact": 0.40, "entity_local_priority": 0.42, "researchability": 0.25, "novelty": 0.70, "coverage_independent": 0.18}',
                0.12,
                0.82,
                1,
                1,
                1,
                1,
                "消费电子",
                "",
                55.0,
                '{"event_state_reason": "single_signal_only", "flags": {"structural_event": false, "ongoing_topic": false}}',
                "rejected",
            ),
            (
                "evt_music_noise",
                "The Temptations to Headline Licensing Expo’s Opening Night Party in Las Vegas",
                "commodity_disruption",
                "2026-04-07T09:00:00+00:00",
                "2026-04-07T09:01:00+00:00",
                "company:the-temptations",
                "confirmed",
                "new",
                1,
                '{"confirmation": 1, "signal": 0}',
                '{"market_significance": 0.61, "entity_impact": 0.76, "entity_local_priority": 0.78, "researchability": 0.62, "novelty": 0.84, "coverage_independent": 0.24}',
                0.55,
                0.35,
                1,
                1,
                1,
                0,
                "",
                "The Temptations",
                67.8,
                '{"event_state_reason": "single_confirmation_pending_breadth", "flags": {"structural_event": false, "ongoing_topic": false}}',
                "unreviewed",
            ),
            (
                "evt_bank_keep",
                "Northwest Bank launches regional SMB lending program",
                "company_action",
                "2026-04-06T13:00:00+00:00",
                "2026-04-06T13:00:00+00:00",
                "company:northwest-bank",
                "emerging",
                "developing",
                1,
                '{"confirmation": 1, "signal": 0}',
                '{"market_significance": 0.41, "entity_impact": 0.73, "entity_local_priority": 0.77, "researchability": 0.74, "novelty": 0.65, "coverage_independent": 0.22}',
                0.49,
                0.34,
                1,
                1,
                1,
                0,
                "银行",
                "Northwest Bank",
                49.2,
                '{"event_state_reason": "single_confirmation_pending_breadth", "flags": {"structural_event": false, "ongoing_topic": false}}',
                "unreviewed",
            ),
            (
                "evt_ai_noise",
                "【电报解读】AI电力需求重塑能源融资格局，该产业或是解决AI能源需求的关键方案",
                "financing_capital",
                "2026-04-06T14:00:00+00:00",
                "2026-04-06T14:00:00+00:00",
                "company:ai",
                "emerging",
                "developing",
                1,
                '{"confirmation": 1, "signal": 0}',
                '{"market_significance": 0.49, "entity_impact": 0.78, "entity_local_priority": 0.81, "researchability": 0.35, "novelty": 0.85, "coverage_independent": 0.43}',
                0.17,
                0.76,
                2,
                1,
                1,
                0,
                "",
                "AI电力需求重塑能源",
                66.9,
                '{"event_state_reason": "single_confirmation_pending_breadth", "flags": {"structural_event": true, "ongoing_topic": false}}',
                "unreviewed",
            ),
            (
                "evt_persistent_mature",
                "欧盟推进芯片补贴框架进入执行阶段",
                "policy",
                "2026-04-01T08:00:00+00:00",
                "2026-04-02T09:00:00+00:00",
                "industry:semiconductor",
                "mature",
                "stale",
                3,
                '{"confirmation": 3, "signal": 0}',
                '{"market_significance": 0.74, "entity_impact": 0.56, "entity_local_priority": 0.58, "researchability": 0.72, "novelty": 0.42, "coverage_independent": 0.66}',
                0.81,
                0.16,
                4,
                3,
                3,
                0,
                "半导体",
                "",
                64.0,
                '{"event_state_reason": "persistent_policy_rollout", "flags": {"structural_event": true, "ongoing_topic": true}}',
                "mapped",
            ),
        ],
    )
    conn.executemany(
        "INSERT INTO article_event_links (article_id, event_id, link_type, created_at) VALUES (?, ?, ?, datetime('now'))",
        [
            ("art_chip_1", "evt_chip_keep", "primary"),
            ("art_chip_2", "evt_chip_keep", "supporting"),
            ("art_chip_3", "evt_chip_keep", "supporting"),
            ("art_macro_1", "evt_macro_keep", "supporting"),
            ("art_rejected", "evt_rejected", "supporting"),
            ("art_music_noise", "evt_music_noise", "supporting"),
            ("art_bank_1", "evt_bank_keep", "supporting"),
            ("art_ai_noise", "evt_ai_noise", "supporting"),
            ("art_persistent_1", "evt_persistent_mature", "supporting"),
        ],
    )
    conn.executemany(
        """
        INSERT INTO event_entity_links (
            event_id, entity_type, entity_id, entity_name, relevance_score,
            mapping_reason, mapping_confidence, mapping_version, mapping_source, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, 'mapping_layer_v1', ?, datetime('now'))
        """,
        [
            ("evt_chip_keep", "industry", "semiconductor", "半导体", 0.98, "industry_keyword_match", 0.84, "builder"),
            ("evt_chip_keep", "company", "tsmc", "台积电", 0.95, "primary_entity_extract", 0.95, "builder"),
            ("evt_rejected", "industry", "consumer_electronics", "消费电子", 0.92, "industry_keyword_match", 0.81, "builder"),
            ("evt_music_noise", "company", "the-temptations", "The Temptations", 0.78, "primary_entity_extract", 0.68, "builder"),
            ("evt_bank_keep", "industry", "banking", "银行", 0.76, "industry_keyword_match", 0.76, "builder"),
            ("evt_bank_keep", "company", "northwest-bank", "Northwest Bank", 0.92, "primary_entity_extract", 0.91, "builder"),
            ("evt_ai_noise", "company", "ai", "AI电力需求重塑能源", 0.95, "preserved_existing_link", 1.0, "preserved_existing"),
            ("evt_macro_keep", "institution", "zh-ministry", "沙特能源部", 0.92, "institution_entity_extract", 0.92, "builder"),
            ("evt_rejected", "company", "zh-shareholder", "控股股东张勇", 0.92, "primary_entity_extract", 0.92, "builder"),
            ("evt_macro_keep", "institution", "zh-steel", "中国钢铁工业协会", 0.92, "institution_entity_extract", 0.92, "builder"),
            ("evt_macro_keep", "company", "zh-aviation", "欧盟航空", 0.92, "primary_entity_extract", 0.92, "builder"),
            ("evt_persistent_mature", "industry", "semiconductor", "半导体", 0.88, "industry_keyword_match", 0.82, "builder"),
            ("evt_persistent_mature", "institution", "eu-commission", "欧盟委员会", 0.86, "institution_entity_extract", 0.80, "builder"),
        ],
    )
    conn.executemany(
        """
        INSERT INTO source_health (source_id, checked_at, status, articles_last_24h, last_article_at, error_message)
        VALUES (?, datetime('now'), ?, ?, ?, '')
        """,
        [
            ("cninfo_sz_latest", "ok", 1, "2026-04-07T09:10:00+00:00"),
            ("prnewswire_company_a", "ok", 1, "2026-04-07T09:12:00+00:00"),
            ("prnewswire_company_b", "ok", 1, "2026-04-07T09:14:00+00:00"),
            ("macro_wire", "ok", 1, "2026-04-07T08:30:00+00:00"),
            ("signal_x", "degraded", 0, ""),
        ],
    )


def seed_large_radar_pool(conn: sqlite3.Connection, count: int) -> None:
    source_rows = [
        (
            "bulk_source",
            "Bulk Source",
            "confirmation",
            "wire:bulk",
            "rss",
            2,
            "company",
            "bulk_source",
        )
    ]
    conn.executemany(
        """
        INSERT INTO source_registry (
            source_id, name, lane, source_family, source_type, trust_tier, coverage_scope,
            collector_owner, scheduler_class, origin_system, legacy_key,
            phase1_disposition, enabled, description
        ) VALUES (?, ?, ?, ?, ?, ?, ?, 'shared', 'high_freq', 'news_event_hub', ?, 'migrate_phase1', 1, '')
        """,
        source_rows,
    )
    event_rows = []
    entity_rows = []
    for idx in range(count):
        event_id = f"evt_bulk_{idx:03d}"
        entity_id = f"bulk-company-{idx:03d}"
        entity_name = f"Bulk Company {idx:03d}"
        published_at = f"2026-04-07T09:{idx % 60:02d}:00+00:00"
        event_rows.append(
            (
                event_id,
                f"{entity_name} signs capacity agreement",
                "contract_order",
                published_at,
                published_at,
                f"company:{entity_id}",
                "emerging",
                "new",
                1,
                '{"confirmation": 1, "signal": 0}',
                '{"market_significance": 0.55, "entity_impact": 0.70, "entity_local_priority": 0.72, "researchability": 0.68, "novelty": 0.90, "coverage_independent": 0.30}',
                0.44,
                0.41,
                1,
                1,
                1,
                0,
                "",
                entity_name,
                35.0 + (idx % 5),
                '{"event_state_reason": "single_confirmation_pending_breadth", "flags": {"structural_event": true, "ongoing_topic": false}}',
                "unreviewed",
            )
        )
        entity_rows.append(
            (event_id, "company", entity_id, entity_name, 0.88, "primary_entity_extract", 0.88, "builder")
        )
    conn.executemany(
        """
        INSERT INTO events (
            event_id, event_title, event_type, first_seen_at, last_seen_at,
            topic_key, event_state, novelty_state, confirmation_count, source_mix, score_vector,
            calibrated_confirmation, uncertainty, article_count_raw, independent_evidence_count,
            source_family_count, signal_platform_count, primary_industry,
            primary_entity, event_rank_score, event_rank_flags, opportunity_state
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        event_rows,
    )
    conn.executemany(
        """
        INSERT INTO event_entity_links (
            event_id, entity_type, entity_id, entity_name, relevance_score,
            mapping_reason, mapping_confidence, mapping_version, mapping_source, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, 'mapping_layer_v1', ?, datetime('now'))
        """,
        entity_rows,
    )


def main() -> None:
    conn = open_db()
    try:
        seed_source_registry(conn)
        seed_articles(conn)
        seed_events(conn)
        conn.execute(
            """
            INSERT INTO event_entity_links (event_id, entity_type, entity_id, entity_name, relevance_score, created_at)
            VALUES (?, 'company', ?, ?, 0.7, ?)
            """,
            ("evt_macro_keep", "junk-fragment", "盘后A股上市公司重点公告精选", "2026-04-07T09:00:00+00:00"),
        )
        conn.commit()

        run_dt = datetime(2026, 4, 7, 10, 0, tzinfo=timezone.utc)
        exports = build_exports(
            conn,
            run_dt=run_dt,
            lookback_hours=72,
            opportunity_limit=20,
            radar_per_industry_limit=5,
            research_limit=20,
        )

        opportunity = exports["opportunity_report_feed_latest.json"]
        legacy = exports["legacy_news_digest_latest.json"]
        radar = exports["industry_radar_feed_latest.json"]
        research = exports["research_feed_latest.json"]
        source_health = exports["source_health_latest.json"]
        entity_day_panel = exports["entity_day_panel_latest.json"]
        industry_day_panel = exports["industry_day_panel_latest.json"]
        institution_day_panel = exports["institution_day_panel_latest.json"]
        mapping_review = exports["mapping_review_latest.json"]
        manifest = exports["manifest_latest.json"]

        top_event_ids = [item["event_id"] for item in opportunity["top_events"]]
        assert_true("evt_chip_keep" in top_event_ids, "opportunity export should include high-score shared events")
        assert_true("evt_rejected" not in top_event_ids, "opportunity export should not leak rejected events")
        chip_event = next(item for item in opportunity["top_events"] if item["event_id"] == "evt_chip_keep")
        assert_true(chip_event["event_state"] == "confirmed", "consumer exports should expose event_state")
        assert_true("event_state_reason" in chip_event, "consumer exports should expose event_state_reason for downstream routing")
        assert_true(chip_event["granularity_class"] == "structural_multi_update", "consumer exports should expose stable granularity class for downstream views")
        assert_true(chip_event["topic_key"] == "company:tsmc", "consumer exports should expose topic_key")
        assert_true(chip_event["supporting_articles"][0]["source_id"] == "cninfo_sz_latest", "within-event evidence ordering should put official primary evidence first")
        assert_true(chip_event["supporting_articles"][0]["link_type"] == "primary", "within-event evidence ordering should preserve primary official evidence at the top")
        assert_true("official_direct" in chip_event["supporting_articles"][0]["evidence_rank_reason"], "evidence ordering should explain official-first placement")
        assert_true("primary_link" in chip_event["supporting_articles"][0]["evidence_rank_reason"], "evidence ordering should explain primary-link placement")
        assert_true("evidence_rank_score" in chip_event["supporting_articles"][0], "supporting articles should expose within-event evidence rank scores")
        assert_true(chip_event["supporting_articles"][2]["source_id"] == "prnewswire_company_b", "same-family repeat evidence should sort after unique families")
        assert_true("same_family_repeat" in chip_event["supporting_articles"][2]["evidence_rank_reason"], "same-family repeats should be flagged in evidence ordering")
        assert_true(chip_event["update_count"] == 2, "consumer exports should expose distinct update counts per event")
        assert_true(bool(chip_event["latest_update_signature"]), "consumer exports should expose the latest update signature")
        assert_true(len(chip_event["recent_updates"]) == 2, "consumer exports should expose recent update snapshots for event-level consumption")
        assert_true(opportunity["ranking_contract"]["view"] == "global_feed", "opportunity export should declare global feed ranking contract")
        assert_true(bool(legacy["top_market_news"]), "legacy digest should include macro-compatible top_market_news items")
        assert_true("analysis_summary_cn" in legacy and str(legacy["analysis_summary_cn"]).strip(), "legacy digest should carry a deterministic compatibility summary")
        radar_industries = [item["industry"] for item in radar["industries"]]
        radar_event_ids = [item["event_id"] for item in radar["event_pool"]]
        assert_true(radar["consumer"] == "investment_radar", "radar export should declare the wider investment radar contract")
        assert_true(radar["legacy_consumer"] == "industry_radar", "radar export should keep the legacy consumer label for migration")
        assert_true(radar["radar_scope"] == "all_investment_opportunities", "radar export should declare all-opportunity scope")
        assert_true(radar["discovery_contract"]["entrypoint"] == "scripts/run_company_discovery.py", "radar export should expose the shared discovery entrypoint")
        assert_true("macro" in radar["discovery_contract"]["route_catalog"], "radar export should expose macro discovery routing, not just company discovery")
        assert_true("industry" in radar["discovery_contract"]["route_catalog"], "radar export should expose industry discovery routing")
        assert_true(radar["discovery_contract"]["route_catalog"]["macro"]["is_executable"] is True, "macro discovery routes should now be executable through the shared runner")
        assert_true(radar["discovery_contract"]["route_catalog"]["industry"]["is_executable"] is True, "industry discovery routes should now be executable through the shared runner")
        assert_true(bool(radar["persistent_window_start"]), "radar export should expose the extended persistent-event window start")
        assert_true(radar["event_pool_count"] == len(radar_event_ids), "radar export should expose the full event pool count")
        assert_true("evt_chip_keep" in radar_event_ids and "evt_macro_keep" in radar_event_ids, "radar event pool should include company and macro opportunities, not just industry buckets")
        assert_true("evt_persistent_mature" in radar_event_ids, "radar event pool should keep recent mature events that still carry strong investment value")
        assert_true(
            any(item["event_id"] == "evt_macro_keep" for item in radar["radar_views"]["macro_events"]),
            "radar export should expose macro opportunities in dedicated views",
        )
        assert_true(
            any(item["event_id"] == "evt_chip_keep" for item in radar["radar_views"]["company_events"]),
            "radar export should expose company opportunities in dedicated views",
        )
        assert_true(
            any(item["event_id"] == "evt_macro_keep" for item in radar["opportunity_buckets"]["new_opportunity_candidates"]),
            "radar opportunity buckets should admit macro events without forcing an industry mapping",
        )
        assert_true(radar_industries == ["半导体", "银行"], "radar export should keep valid mapped industries and exclude rejected-only industries")
        assert_true("半导体" in research["industry_index"], "research export should build industry lookup indexes")
        assert_true("score_vector" in research["recent_events"][0], "research export should expose score vector for downstream reranking")
        assert_true(research["ranking_contract"]["view"] == "research_retrieval", "research export should declare research-specific ranking contract")
        assert_true(research["discovery_contract"]["entrypoint"] == "scripts/run_company_discovery.py", "research export should expose the shared discovery contract")
        assert_true(bool(opportunity["as_of"]), "shared exports should expose as_of semantics")
        assert_true(bool(research["window_start"]), "research exports should expose lookback window start")
        assert_true(bool(research["persistent_window_start"]), "research exports should expose the extended persistent-event window start")
        assert_true(research["recent_events"][0]["event_id"] == "evt_chip_keep", "research retrieval should prioritize entity-local company events over higher-global-score macro context")
        assert_true(any(item["event_id"] == "evt_persistent_mature" for item in research["recent_events"]), "research retrieval should retain mature but still-relevant events instead of dropping them at the export boundary")
        assert_true("research_rank_score" in research["recent_events"][0], "research export should expose research_rank_score")
        assert_true("research_rank_reason" in research["recent_events"][0], "research export should expose research_rank_reason")
        assert_true("entity_local_priority" in research["recent_events"][0]["score_vector"], "research export should expose entity_local_priority for downstream reranking")
        assert_true(research["recent_events"][0]["opportunity_bucket"] == "company", "event briefs should expose opportunity bucket contract")
        assert_true(research["recent_events"][0]["followup_path"] == "open_company_research", "event briefs should expose follow-up path contract")
        assert_true("台积电" in research["entity_profiles"], "research export should build entity-first company profiles")
        assert_true("盘后A股上市公司重点公告精选" not in research["entity_profiles"], "research export should filter generic company roundup fragments out of entity profiles")
        assert_true("The Temptations" not in research["entity_profiles"], "research export should filter entertainment-style PR entities out of company profiles")
        assert_true("HealthWell Foundation" not in research["entity_profiles"], "research export should filter non-company institutions out of company profiles")
        assert_true("AI电力需求重塑能源" not in research["entity_profiles"], "research export should filter conceptual Chinese headline fragments out of company profiles")
        assert_true("沙特能源部" not in research["entity_profiles"], "research export should filter government/department-style Chinese entities out of company profiles")
        assert_true("控股股东张勇" not in research["entity_profiles"], "research export should filter shareholder-identity fragments out of company profiles")
        assert_true("中国钢铁工业" not in research["entity_profiles"], "research export should filter institution-derived sector fragments out of company profiles")
        assert_true("欧盟航空" not in research["entity_profiles"], "research export should filter region-sector fragments out of company profiles")
        assert_true("沙特能源部" in research["institution_profiles"], "research export should build institution profiles for policy bodies")
        assert_true("中国钢铁工业协会" in research["institution_profiles"], "research export should build institution profiles for association bodies")
        assert_true(research["institution_profiles"]["沙特能源部"]["entity_type"] == "institution", "institution profiles should keep institution entity type")
        assert_true(research["institution_index"]["沙特能源部"][0]["event_id"] == "evt_macro_keep", "institution index should expose top events for institution retrieval")
        assert_true(research["entity_profiles"]["台积电"]["entity_id"] == "tsmc", "entity profiles should expose canonical entity ids")
        assert_true(research["entity_profiles"]["台积电"]["discovery_routes"]["entrypoint"] == "scripts/run_company_discovery.py", "company profiles should expose standard discovery routes")
        assert_true("serpstack_company_discovery_optional" in research["entity_profiles"]["台积电"]["discovery_routes"]["live_source_ids"], "company discovery routes should expose the shared structured-search backend")
        assert_true("xueqiu_public_timeline" in research["industry_profiles"]["半导体"]["discovery_routes"]["signal_source_ids"], "industry profiles should expose shared signal surfaces for backfill")
        assert_true("fed_press" in research["institution_profiles"]["沙特能源部"]["discovery_routes"]["live_source_ids"], "institution profiles should expose the shared policy/macro confirmation sources")
        assert_true("TSMC" in research["entity_profiles"]["台积电"]["aliases"], "entity profiles should expose alias terms from the shared alias registry")
        assert_true("tsmc" in research["entity_profiles"]["台积电"]["lookup_terms"], "entity profiles should expose lookup terms for downstream retrieval")
        assert_true(research["entity_profiles"]["台积电"]["top_events"][0]["event_id"] == "evt_chip_keep", "entity profiles should keep entity-local top events")
        assert_true(research["entity_profiles"]["台积电"]["timeline"][0]["event_id"] == "evt_chip_keep", "entity profiles should expose a timeline ordered for research consumption")
        assert_true("company:tsmc" in research["entity_profiles"]["台积电"]["topic_slices"], "entity profiles should expose topic slices keyed by topic_key")
        assert_true(bool(research["entity_profiles"]["台积电"]["related_queries"]), "entity profiles should expose related query suggestions")
        assert_true(any(item["query"] == "半导体" for item in research["entity_profiles"]["台积电"]["related_queries"]), "related queries should include linked industries for downstream retrieval")
        assert_true(research["entity_profiles"]["台积电"]["evidence_bundle"][0]["source_id"] == "cninfo_sz_latest", "entity evidence bundles should inherit within-event official-first ordering")
        assert_true(research["entity_profiles"]["台积电"]["evidence_bundle"][0]["event_id"] == "evt_chip_keep", "entity evidence bundles should carry parent event linkage")
        assert_true(research["recent_events"][0]["entities_by_type"]["company"][0]["mapping_reason"] == "primary_entity_extract", "mapping layer fields should flow through consumer exports")
        assert_true(research["recent_events"][0]["entities_by_type"]["company"][0]["mapping_version"] == "mapping_layer_v1", "mapping version should flow through consumer exports")
        assert_true(research["entity_query_index"]["沙特能源部"]["entity_type"] == "institution", "research export should route institution lookups through the query index")
        assert_true("company:tsmc" in research["topic_index"], "research export should build topic-key retrieval indexes")
        assert_true("company:tsmc" in research["topic_profiles"], "research export should build topic profiles for topic-centric retrieval")
        assert_true(research["topic_profiles"]["company:tsmc"]["timeline"][0]["event_id"] == "evt_chip_keep", "topic profiles should expose timeline views")
        assert_true(research["entity_query_index"]["tsmc"]["entity_name"] == "台积电", "research export should expose a normalized entity query index for consumer-side lookup routing")
        assert_true(research["entity_query_index"]["companytsmc"]["entity_type"] == "topic", "research export should route normalized topic-key lookups through the query index")
        assert_true(len(source_health["source_health"]) == 5, "source health export should include latest per-source health rows")
        assert_true(source_health["status"] == "warn", "source health export should expose a top-level degraded status")
        assert_true(source_health["summary"]["ok"] == 4 and source_health["summary"]["degraded"] == 1, "source health export should expose top-level ok/degraded/down summary")
        assert_true(entity_day_panel["consumer"] == "entity_day_panel", "entity-day export should expose its own consumer contract")
        assert_true(industry_day_panel["consumer"] == "industry_day_panel", "industry-day export should expose its own consumer contract")
        assert_true(institution_day_panel["consumer"] == "institution_day_panel", "institution-day export should expose its own consumer contract")
        assert_true(bool(entity_day_panel["as_of"]) and bool(entity_day_panel["window_start"]), "entity-day panel should expose point-in-time semantics")
        assert_true(bool(industry_day_panel["as_of"]) and bool(industry_day_panel["window_start"]), "industry-day panel should expose point-in-time semantics")
        assert_true(bool(institution_day_panel["as_of"]) and bool(institution_day_panel["window_start"]), "institution-day panel should expose point-in-time semantics")
        entity_names = [row["entity_name"] for row in entity_day_panel["rows"]]
        assert_true("台积电" in entity_names, "entity-day panel should include mapped company-day rows")
        assert_true("Northwest Bank" in entity_names, "entity-day panel should keep lower-ranked but valid company-day rows")
        tsmc_panel = next(row for row in entity_day_panel["rows"] if row["entity_name"] == "台积电")
        assert_true(tsmc_panel["panel_date"] == "2026-04-07", "entity-day panel should key rows by the event's point-in-time day")
        assert_true(tsmc_panel["granularity_mix"]["structural_multi_update"] == 1, "entity-day panel should summarize granularity classes for grouped events")
        assert_true(tsmc_panel["top_events"][0]["event_id"] == "evt_chip_keep", "entity-day panel should keep event briefs for downstream factor work")
        assert_true("company:tsmc" in tsmc_panel["topic_keys"], "entity-day panel should preserve topic keys for point-in-time linking")
        industry_names_panel = [row["entity_name"] for row in industry_day_panel["rows"]]
        assert_true("半导体" in industry_names_panel, "industry-day panel should include mapped industry-day rows")
        semi_panel = next(row for row in industry_day_panel["rows"] if row["entity_name"] == "半导体")
        assert_true(semi_panel["top_events"][0]["event_id"] == "evt_chip_keep", "industry-day panel should preserve top events for factor consumers")
        institution_names_panel = [row["entity_name"] for row in institution_day_panel["rows"]]
        assert_true("沙特能源部" in institution_names_panel, "institution-day panel should include mapped institution-day rows")
        ministry_panel = next(row for row in institution_day_panel["rows"] if row["entity_name"] == "沙特能源部")
        assert_true(ministry_panel["top_events"][0]["event_id"] == "evt_macro_keep", "institution-day panel should preserve top events for institution consumers")
        assert_true(ministry_panel["entity_type"] == "institution", "institution-day panel should preserve institution entity type")
        assert_true(manifest["point_in_time_contract"]["consumer_topn_decoupled"] is True, "manifest should declare point-in-time panels as decoupled from top-N consumer truncation")
        assert_true(mapping_review["low_confidence_count"] >= 1, "mapping review export should surface low-confidence links for operator review")
        assert_true(any(item["entity_name"] == "The Temptations" for item in mapping_review["low_confidence_links"]), "mapping review export should keep low-confidence company links reviewable")
    finally:
        conn.close()

    large_pool_conn = open_db()
    try:
        seed_large_radar_pool(large_pool_conn, count=130)
        large_pool_conn.commit()
        large_exports = build_exports(
            large_pool_conn,
            run_dt=datetime(2026, 4, 7, 10, 0, tzinfo=timezone.utc),
            lookback_hours=72,
            opportunity_limit=5,
            radar_per_industry_limit=3,
            research_limit=5,
        )
        large_radar = large_exports["industry_radar_feed_latest.json"]
        assert_true(large_radar["event_pool_count"] == 130, "radar event pool should not be truncated by a fixed candidate cap")
        assert_true(len(large_radar["event_pool"]) == 130, "radar export should retain every in-window event in the pool")
    finally:
        large_pool_conn.close()

    print("consumer_views_smoke_ok")


if __name__ == "__main__":
    main()
