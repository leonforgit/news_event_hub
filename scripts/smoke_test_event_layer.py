#!/usr/bin/env python3
from __future__ import annotations

import sqlite3
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from build_event_layer import (
    Article,
    article_title_clean,
    collect_event_updates,
    compute_rank,
    event_id_for_key,
    extract_institution_entity,
    extract_primary_entity,
    headline_focus_text,
    infer_event_type,
    insert_entity_links,
    keyword_match,
    merge_key,
    MACRO_THEMES,
    INDUSTRY_KEYWORDS,
)


ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = ROOT / "config" / "schema.sql"
NOW = datetime(2026, 4, 6, 22, 0, tzinfo=timezone.utc)


def make_article(
    *,
    title: str,
    summary: str = "",
    source_id: str = "cls_telegraph_html",
    source_family: str = "",
    lane: str = "confirmation",
    trust_tier: int = 1,
    coverage_scope: str = "mixed",
    published_at: str = "2026-04-06T21:00:00+00:00",
    canonical_url: str = "https://example.com/test",
) -> Article:
    return Article(
        article_id=f"test_{abs(hash((title, summary, source_id))) % 10_000_000}",
        source_id=source_id,
        source_family=source_family,
        title=title,
        title_norm=title.lower(),
        summary=summary,
        canonical_url=canonical_url,
        published_at=published_at,
        collected_at=published_at,
        lane=lane,
        trust_tier=trust_tier,
        coverage_scope=coverage_scope,
    )


def score_article(article: Article) -> tuple[float, dict]:
    return score_articles([article])


def score_articles(articles: list[Article]) -> tuple[float, dict]:
    representative = articles[0]
    title = article_title_clean(representative)
    classification_text = headline_focus_text(title) or title[:140]
    event_type, action_key = infer_event_type(title, representative)
    primary_entity = extract_primary_entity(title, representative)
    primary_industry = keyword_match(classification_text, INDUSTRY_KEYWORDS)
    macro_theme = keyword_match(classification_text, MACRO_THEMES)
    return compute_rank(
        articles,
        event_type,
        action_key,
        primary_entity,
        primary_industry,
        macro_theme,
        NOW,
    )


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def open_db(path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def build_temp_db_with_articles(articles: list[Article]) -> tuple[tempfile.TemporaryDirectory[str], Path]:
    tmp_dir = tempfile.TemporaryDirectory()
    db_path = Path(tmp_dir.name) / "news_event_smoke.db"
    conn = open_db(db_path)
    try:
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        source_ids = sorted({article.source_id for article in articles})
        for source_id in source_ids:
            lane = next(article.lane for article in articles if article.source_id == source_id)
            coverage_scope = next((article.coverage_scope for article in articles if article.source_id == source_id), "mixed")
            conn.execute(
                """
                INSERT INTO source_registry (
                    source_id, name, lane, source_family, source_type, trust_tier, coverage_scope,
                    collector_owner, scheduler_class, origin_system, legacy_key,
                    phase1_disposition, enabled, description
                ) VALUES (?, ?, ?, ?, 'rss', 1, ?, 'shared', 'high_freq', 'news_event_hub', ?, 'migrate_phase1', 1, '')
                """,
                (
                    source_id,
                    source_id,
                    lane,
                    next((article.source_family for article in articles if article.source_id == source_id), ""),
                    coverage_scope or "mixed",
                    source_id,
                ),
            )
        for article in articles:
            conn.execute(
                """
                INSERT INTO news_articles (
                    article_id, source_id, title, title_norm, summary, body_text, url,
                    canonical_url, published_at, timestamp_quality, content_hash, language,
                    collector_scope, collected_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'exact', ?, 'zh', 'baseline_shared', ?)
                """,
                (
                    article.article_id,
                    article.source_id,
                    article.title,
                    article.title_norm,
                    article.summary,
                    article.summary,
                    f"https://example.com/{article.article_id}",
                    article.canonical_url or f"https://example.com/{article.article_id}",
                    article.published_at,
                    f"hash_{article.article_id}",
                    article.collected_at,
                ),
            )
        conn.commit()
    finally:
        conn.close()
    return tmp_dir, db_path


def run_builder(db_path: Path, *extra_args: str) -> None:
    subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "build_event_layer.py"), "--db", str(db_path), "--as-of", NOW.isoformat(), *extra_args],
        check=True,
        capture_output=True,
        text=True,
    )


def main() -> None:
    calendar_article = make_article(
        title="【周二（4月7日）重点关注财经事件和经济数据】① 20:30 美国2月耐用品订单月率",
    )
    calendar_score, calendar_flags = score_article(calendar_article)
    assert_true(calendar_flags["action_key"] == "calendar_preview", "calendar preview should be classified explicitly")
    assert_true(calendar_score < 20, "calendar preview should stay out of digest threshold")

    price_move_article = make_article(
        title="美元指数3日上涨",
        source_id="reuters_macro_bing",
        summary="美元指数上涨",
    )
    price_move_score, price_move_flags = score_article(price_move_article)
    assert_true(price_move_flags["action_key"] == "macro_move", "macro move action key mismatch")
    assert_true(price_move_score < 20, "generic macro move should stay out of digest threshold")

    housekeeping_article = make_article(
        title="红果短剧：针对近期AI短剧素材违规使用问题频发的情况，已处置作品670部",
        summary="平台专项开展集中治理",
    )
    housekeeping_score, _ = score_article(housekeeping_article)
    assert_true(housekeeping_score < 20, "platform housekeeping notice should stay out of digest threshold")

    roundup_article = make_article(
        title="Business News | Today's International Headlines | Reuters",
        source_id="reuters_macro_bing",
    )
    roundup_score, _ = score_article(roundup_article)
    assert_true(roundup_score < 20, "wire roundup shell should stay out of digest threshold")

    geopolitics_article = make_article(
        title="【伊朗两处住宅遭袭受损 至少13人死亡】财联社4月6日电",
        summary="救援队在事故现场已发现13名遇难者",
    )
    geopolitics_score, geopolitics_flags = score_article(geopolitics_article)
    assert_true(geopolitics_flags["macro_theme"] == "中东地缘", "geopolitics sample should map to Middle East macro theme")
    assert_true(geopolitics_score < 20, "routine geopolitics casualty update should stay out of digest threshold")

    weak_financing_article = make_article(
        title="【国际货币基金组织：中东战争将导致经济增长放缓 通胀加剧】财联社4月7日电",
        summary="国际货币基金组织已收到一些国家的融资援助请求",
    )
    weak_financing_score, _ = score_article(weak_financing_article)
    assert_true(weak_financing_score < 20, "macro quote with incidental financing wording should stay out of digest threshold")

    summary_only_industry_article = make_article(
        title="【香港财政司司长陈茂波：目前轮候来港上市申请个案已超过500宗】财联社4月5日电",
        summary="更重要的是，来港上市企业愈来愈多属新兴产业，包括人工智能、半导体、机械人、自动驾驶、生物科技等。",
    )
    summary_only_title = article_title_clean(summary_only_industry_article)
    summary_only_classification = headline_focus_text(summary_only_title) or summary_only_title[:140]
    summary_only_industry = keyword_match(summary_only_classification, INDUSTRY_KEYWORDS)
    assert_true(summary_only_industry is None, "industry mapping should not be pulled in only by trailing summary keywords")

    ai_industry_article = make_article(
        title="Meta plans new AI data center cluster and expands inference software stack",
        source_id="reuters_company_bing",
    )
    ai_industry_title = article_title_clean(ai_industry_article)
    ai_industry_classification = headline_focus_text(ai_industry_title) or ai_industry_title[:140]
    ai_industry = keyword_match(ai_industry_classification, INDUSTRY_KEYWORDS)
    assert_true(ai_industry == "算力AI软件", "industry taxonomy should cover AI/compute/software opportunity clusters")

    retail_industry_article = make_article(
        title="京东加码即时零售并扩大电商平台商家扶持计划",
        source_id="cls_telegraph_html",
    )
    retail_industry_title = article_title_clean(retail_industry_article)
    retail_industry_classification = headline_focus_text(retail_industry_title) or retail_industry_title[:140]
    retail_industry = keyword_match(retail_industry_classification, INDUSTRY_KEYWORDS)
    assert_true(retail_industry == "零售电商", "industry taxonomy should cover retail and ecommerce opportunity clusters")

    teaser_article = make_article(
        title="这家持牌金融租赁公司，招商转让！",
        summary="一则项目转让信息",
        source_id="cls_telegraph_html",
    )
    teaser_score, _ = score_article(teaser_article)
    assert_true(teaser_score < 20, "generic teaser headline should stay out of digest threshold")

    official_comment_article = make_article(
        title="日本财务大臣片山皋月称，七国集团财长和央行行长一致认为，油价大幅波动正导致金融和外汇市场高度动荡。一直与G7同行保持密切联系。",
        source_id="reuters_macro_bing",
    )
    official_comment_score, _ = score_article(official_comment_article)
    assert_true(official_comment_score < 20, "official commentary without concrete market action should stay out of digest threshold")

    diplomatic_article = make_article(
        title="【中国驻乌克兰大使马升琨与乌方签署乌克兰小麦粉输华议定书】财联社4月7日电",
    )
    diplomatic_score, _ = score_article(diplomatic_article)
    assert_true(diplomatic_score < 20, "diplomatic protocol headlines should stay out of digest threshold")

    watch_signal_score, watch_signal_flags = score_article(
        make_article(
            title="泡泡玛特相关讨论在社区升温",
            summary="社区开始出现零散讨论",
            source_id="xueqiu_public_timeline",
            source_family="social:xueqiu",
            lane="signal",
            canonical_url="https://xueqiu.com/status/watch-1",
        )
    )
    assert_true(str(watch_signal_flags["event_state"]) == "watch", "single low-confidence signal should enter watch state")
    assert_true(str(watch_signal_flags["event_state_reason"]) == "single_signal_only", "watch state should expose its reason")
    assert_true(watch_signal_score < 50, "watch signals may gain recall score from strong entity mapping, but should stay below confirmed priority bands")

    emerging_signal_score, emerging_signal_flags = score_articles(
        [
            make_article(
                title="泡泡玛特与欧洲渠道初步接触合作开店",
                summary="社区在讨论合作开店传闻",
                source_id="xueqiu_public_timeline",
                source_family="social:xueqiu",
                lane="signal",
                canonical_url="https://xueqiu.com/status/emerging-1",
            ),
            make_article(
                title="泡泡玛特与欧洲渠道初步接触合作开店",
                summary="reddit 也在讨论同一合作线索",
                source_id="reddit_market_forums",
                source_family="forum:reddit",
                lane="signal",
                canonical_url="https://reddit.com/r/stocks/emerging-1",
            ),
        ]
    )
    assert_true(str(emerging_signal_flags["event_state"]) == "emerging", "multi-platform signal resonance should enter emerging state")
    assert_true(str(emerging_signal_flags["event_state_reason"]) == "multi_signal_resonance", "emerging signal should expose resonance reason")
    assert_true(int(emerging_signal_flags["counters"]["signal_count"]) == 2, "signal resonance should count two independent signal families")

    confirmed_official_score, confirmed_official_flags = score_article(
        make_article(
            title="泡泡玛特：关于回购股份方案的公告",
            summary="公司披露回购股份安排",
            source_id="cninfo_sz_latest",
            source_family="exchange:cninfo",
            lane="confirmation",
            canonical_url="https://www.cninfo.com.cn/official-buyback",
        )
    )
    assert_true(str(confirmed_official_flags["event_state"]) == "confirmed", "single official disclosure should enter confirmed state")
    assert_true(str(confirmed_official_flags["event_state_reason"]) == "confirmed_by_independent_facts", "official confirmation should expose confirmed reason")
    assert_true(confirmed_official_score > watch_signal_score, "official confirmed evidence should outrank watch-only signals")

    contested_score, contested_flags = score_article(
        make_article(
            title="公司否认将出售核心资产",
            summary="公司就市场传闻作出澄清",
            source_id="cls_telegraph_html",
            source_family="wire:cls",
            lane="confirmation",
            canonical_url="https://www.cls.cn/detail/contested-1",
        )
    )
    assert_true(str(contested_flags["event_state"]) == "contested", "denial-style updates should enter contested state")
    assert_true(str(contested_flags["event_state_reason"]) == "contradiction_or_denial", "contested state should expose its reason")
    assert_true(contested_score >= 0, "contested events should still keep a non-negative base score")

    broker_note_article = make_article(
        title="【华泰证券：A股短期维持防御和低相关性配置 中期布局电力链和景气度】财联社4月7日电",
    )
    broker_note_score, _ = score_article(broker_note_article)
    assert_true(broker_note_score < 20, "broker strategy notes should stay out of digest threshold")
    for broker_title in (
        "华泰证券指出煤炭龙头估值有修复空间",
        "中信证券指出看好银行股估值修复",
        "券商最新研报：看好半导体设备国产替代",
    ):
        broker_variant_score, _ = score_article(
            make_article(
                title=broker_title,
                source_id="reuters_macro_bing",
            )
        )
        assert_true(broker_variant_score < 20, f"broker-note variant should stay out of digest threshold: {broker_title}")

    survey_article = make_article(
        title="【机构最新调研路线图出炉 迈瑞医疗最获关注】财联社4月5日电",
        summary="Wind数据显示，机构本周共调研了355家上市公司。",
    )
    survey_score, _ = score_article(survey_article)
    assert_true(survey_score < 20, "institutional survey roundups should stay out of digest threshold")

    commentary_article = make_article(
        title="【外围扰动难动摇市场中期上行根基 机构建议逢低布局产业趋势向上行业】财联社4月7日电",
        summary="机构研判市场后市配置。",
    )
    commentary_score, _ = score_article(commentary_article)
    assert_true(commentary_score < 20, "market commentary shells should stay out of digest threshold")

    broker_note_article = make_article(
        title="【华泰证券：预计核电龙头股价或将先后迎来盈利修复、成长加速与估值提升三重利好】财联社4月7日电",
        summary="华泰证券研报指出长期成长空间。",
    )
    broker_note_score, _ = score_article(broker_note_article)
    assert_true(broker_note_score < 20, "broker-note headlines should stay out of digest threshold")

    goldman_note_article = make_article(
        title="高盛预计2026年铜价平均为12,650美元，此前预期为12,850美元。",
        source_id="reuters_macro_bing",
    )
    goldman_note_score, _ = score_article(goldman_note_article)
    assert_true(goldman_note_score < 20, "analyst price-target shells should stay out of digest threshold")

    bullet_teaser_article = make_article(
        title="①硅光+CPO，全球首发3.2T NPO模块并完成大厂验证；②BD出海+减肥药，这家公司实现热门多肽量产。",
        summary="题材导读",
    )
    bullet_teaser_score, _ = score_article(bullet_teaser_article)
    assert_true(bullet_teaser_score < 20, "bullet teaser shells should stay out of digest threshold")

    high_open_article = make_article(
        title="【国际油价6日微涨】财联社4月7日电，纽约商品交易所5月交货的轻质原油期货价格上涨87美分。",
        source_id="cls_telegraph_html",
    )
    high_open_score, _ = score_article(high_open_article)
    assert_true(high_open_score < 20, "pure commodity price recap should stay out of digest threshold")

    cold_company_articles = [
        make_article(
            title="金丹科技签署可降解材料长期供货合同",
            source_id="cninfo_sz_latest",
            source_family="exchange:cninfo",
            coverage_scope="company",
        ),
        make_article(
            title="金丹科技：签署可降解材料长期供货合同",
            source_id="cls_telegraph_html",
            source_family="media:cls",
            coverage_scope="company",
            published_at="2026-04-06T21:10:00+00:00",
        ),
    ]
    cold_company_score, cold_company_flags = score_articles(cold_company_articles)

    broad_macro_articles = [
        make_article(
            title="多家机构称中东局势升级或继续推升全球能源成本",
            source_id="reuters_macro_bing",
            source_family="media:reuters",
            coverage_scope="macro",
        ),
        make_article(
            title="分析人士表示中东战事恐继续推升全球能源成本",
            source_id="macro_wire",
            source_family="media:macro",
            coverage_scope="macro",
            published_at="2026-04-06T21:05:00+00:00",
        ),
        make_article(
            title="机构观点：中东地缘紧张仍将扰动全球能源价格",
            source_id="marketaux_global_optional",
            source_family="api:marketaux",
            coverage_scope="macro",
            published_at="2026-04-06T21:08:00+00:00",
        ),
        make_article(
            title="策略师称中东风险仍将持续传导至全球能源链",
            source_id="macro_extra_a",
            source_family="media:macroextraa",
            coverage_scope="macro",
            published_at="2026-04-06T21:06:00+00:00",
        ),
        make_article(
            title="机构研判中东紧张局势继续抬升全球能源成本预期",
            source_id="macro_extra_b",
            source_family="media:macroextrab",
            coverage_scope="macro",
            published_at="2026-04-06T21:07:00+00:00",
        ),
    ]
    broad_macro_score, broad_macro_flags = score_articles(broad_macro_articles)
    assert_true(cold_company_score > broad_macro_score, "undercovered structural company events should outrank broad macro commentary shells with higher coverage")
    assert_true(bool(cold_company_flags["flags"]["micro_event_protected"]), "cold structural company events should expose micro_event_protected")
    assert_true(bool(broad_macro_flags["flags"]["macro_coverage_capped"]), "broad macro topics should expose macro_coverage_capped when coverage residual inflates")

    commentary_micro_articles = [
        make_article(
            title="渣打：为期两周的美伊停火协议对能源供应的推动力可能有限",
            source_id="macro_wire",
            source_family="media:macro",
            coverage_scope="macro",
        )
    ]
    _, commentary_micro_flags = score_articles(commentary_micro_articles)
    assert_true(
        not commentary_micro_flags["flags"]["micro_event_protected"],
        "institutional commentary mentioning a company name should not trigger micro-event protection",
    )

    title_a = "【日本商船三井公司：关联公司一艘液化石油气船通过霍尔木兹海峡】财联社4月4日电"
    title_b = "日本商船三井公司：关联公司一艘液化石油气船通过霍尔木兹海峡"
    article_a = make_article(title=title_a, published_at="2026-04-04T09:20:50+00:00")
    article_b = make_article(
        title=title_b,
        published_at="2026-04-04T09:19:34+00:00",
        source_id="reuters_company_bing",
    )
    clean_entity_a = extract_primary_entity(article_title_clean(article_a), article_a)
    clean_entity_b = extract_primary_entity(article_title_clean(article_b), article_b)
    assert_true(clean_entity_a == clean_entity_b == "日本商船三井公司", "entity cleaning should normalize bracket variants")
    event_type_a, action_key_a = infer_event_type(article_title_clean(article_a), article_a)
    classify_a = headline_focus_text(article_title_clean(article_a)) or article_title_clean(article_a)[:140]
    key_a = merge_key(article_a, article_title_clean(article_a), event_type_a, action_key_a, clean_entity_a, keyword_match(classify_a, INDUSTRY_KEYWORDS), keyword_match(classify_a, MACRO_THEMES))
    event_type_b, action_key_b = infer_event_type(article_title_clean(article_b), article_b)
    classify_b = headline_focus_text(article_title_clean(article_b)) or article_title_clean(article_b)[:140]
    key_b = merge_key(article_b, article_title_clean(article_b), event_type_b, action_key_b, clean_entity_b, keyword_match(classify_b, INDUSTRY_KEYWORDS), keyword_match(classify_b, MACRO_THEMES))
    assert_true(key_a == key_b, "equivalent Mitsui titles should merge into the same event key")
    article_c = make_article(
        title=title_b,
        published_at="2026-04-05T13:19:34+00:00",
        source_id="reuters_company_bing",
    )
    event_type_c, action_key_c = infer_event_type(article_title_clean(article_c), article_c)
    classify_c = headline_focus_text(article_title_clean(article_c)) or article_title_clean(article_c)[:140]
    key_c = merge_key(article_c, article_title_clean(article_c), event_type_c, action_key_c, clean_entity_b, keyword_match(classify_c, INDUSTRY_KEYWORDS), keyword_match(classify_c, MACRO_THEMES))
    assert_true(key_b == key_c, "shared event identity should remain stable across time buckets for the same entity/action headline")

    alias_article = make_article(
        title="POP MART signs North America expansion contract",
        source_id="reuters_company_bing",
        source_family="host:reuters",
        canonical_url="https://www.reuters.com/world/china/pop-mart-expansion",
    )
    alias_entity = extract_primary_entity(article_title_clean(alias_article), alias_article)
    assert_true(alias_entity == "泡泡玛特", "alias mapping should canonicalize English company names into shared canonical entities")
    alias_type, alias_action = infer_event_type(article_title_clean(alias_article), alias_article)
    alias_classify = headline_focus_text(article_title_clean(alias_article)) or article_title_clean(alias_article)[:140]
    alias_key = merge_key(
        alias_article,
        article_title_clean(alias_article),
        alias_type,
        alias_action,
        alias_entity,
        keyword_match(alias_classify, INDUSTRY_KEYWORDS),
        keyword_match(alias_classify, MACRO_THEMES),
    )
    assert_true(alias_key.startswith("entity|pop_mart|contract_order|order|northamerica-expansion"), "alias mapping should drive stable canonical company ids and cross-language context signatures in merge keys")

    general_update_article_a = make_article(
        title="OpenAI因能源成本问题暂停英国星际之门项目",
        source_id="reuters_company_bing",
        coverage_scope="company",
        published_at="2026-04-07T09:00:00+00:00",
    )
    general_update_article_b = make_article(
        title="OpenAI暂停英国星际之门项目 因能源成本过高",
        source_id="company_marketwatch_bing",
        coverage_scope="company",
        published_at="2026-04-08T09:00:00+00:00",
    )
    general_update_type_a, general_update_action_a = infer_event_type(article_title_clean(general_update_article_a), general_update_article_a)
    general_update_type_b, general_update_action_b = infer_event_type(article_title_clean(general_update_article_b), general_update_article_b)
    general_update_entity_a = extract_primary_entity(article_title_clean(general_update_article_a), general_update_article_a)
    general_update_entity_b = extract_primary_entity(article_title_clean(general_update_article_b), general_update_article_b)
    general_update_key_a = merge_key(
        general_update_article_a,
        article_title_clean(general_update_article_a),
        general_update_type_a,
        general_update_action_a,
        general_update_entity_a,
        keyword_match(article_title_clean(general_update_article_a), INDUSTRY_KEYWORDS),
        keyword_match(article_title_clean(general_update_article_a), MACRO_THEMES),
    )
    general_update_key_b = merge_key(
        general_update_article_b,
        article_title_clean(general_update_article_b),
        general_update_type_b,
        general_update_action_b,
        general_update_entity_b,
        keyword_match(article_title_clean(general_update_article_b), INDUSTRY_KEYWORDS),
        keyword_match(article_title_clean(general_update_article_b), MACRO_THEMES),
    )
    assert_true(
        general_update_key_a == general_update_key_b,
        "general_update company headlines with the same underlying fact should still use entity-level merge keys",
    )

    distinct_general_update_article = make_article(
        title="OpenAI考虑在法国新建AI数据中心",
        source_id="reuters_company_bing",
        coverage_scope="company",
        published_at="2026-04-08T10:00:00+00:00",
    )
    distinct_general_update_type, distinct_general_update_action = infer_event_type(article_title_clean(distinct_general_update_article), distinct_general_update_article)
    distinct_general_update_entity = extract_primary_entity(article_title_clean(distinct_general_update_article), distinct_general_update_article)
    distinct_general_update_key = merge_key(
        distinct_general_update_article,
        article_title_clean(distinct_general_update_article),
        distinct_general_update_type,
        distinct_general_update_action,
        distinct_general_update_entity,
        keyword_match(article_title_clean(distinct_general_update_article), INDUSTRY_KEYWORDS),
        keyword_match(article_title_clean(distinct_general_update_article), MACRO_THEMES),
    )
    assert_true(
        distinct_general_update_key != general_update_key_a,
        "different general_update facts for the same company should not be over-merged",
    )

    trimmed_candidate_article = make_article(
        title="浙江浙能燃料集团有限公司增持1206.54万股股份",
        source_id="cls_telegraph_html",
    )
    trimmed_entity = extract_primary_entity(article_title_clean(trimmed_candidate_article), trimmed_candidate_article)
    assert_true(trimmed_entity == "浙江浙能燃料集团有限公司", "entity extraction should trim structural action suffixes off company headlines")

    non_company_candidate_article = make_article(
        title="已故三星集团会长遗孀出售1500万股三星股票",
        source_id="reuters_company_bing",
    )
    non_company_entity = extract_primary_entity(article_title_clean(non_company_candidate_article), non_company_candidate_article)
    assert_true(non_company_entity is None, "entity extraction should reject person-context or index-like title fragments as company entities")

    openai_candidate_article = make_article(
        title="OpenAI因能源成本问题暂停英国“星际之门”项目",
        source_id="reuters_company_bing",
    )
    openai_entity = extract_primary_entity(article_title_clean(openai_candidate_article), openai_candidate_article)
    assert_true(openai_entity == "OpenAI", "entity extraction should trim causal and action context to recover the underlying company")

    generic_company_fragment_article = make_article(
        title="盘后A股上市公司重点公告精选",
        source_id="cls_telegraph_html",
    )
    generic_company_entity = extract_primary_entity(article_title_clean(generic_company_fragment_article), generic_company_fragment_article)
    assert_true(generic_company_entity is None, "entity extraction should reject generic company roundup fragments")

    leading_company_article = make_article(
        title="维维股份2025年净利润3.35亿元 连续三年保持50%以上分红比例",
        source_id="cls_telegraph_html",
    )
    leading_company_entity = extract_primary_entity(article_title_clean(leading_company_article), leading_company_article)
    assert_true(leading_company_entity == "维维股份", "entity extraction should recover leading Chinese company names even when the headline immediately continues into earnings details")

    leading_company_colon_article = make_article(
        title="三元基因：2025全年营收创新高 四季度盈利拐点已现",
        source_id="cls_telegraph_html",
    )
    leading_company_colon_entity = extract_primary_entity(article_title_clean(leading_company_colon_article), leading_company_colon_article)
    assert_true(leading_company_colon_entity == "三元基因", "entity extraction should preserve colon-prefixed company names with biotech-style suffixes")

    quoted_company_article = make_article(
        title="婴儿食品商“喜宝”遭投毒勒索 奥地利召回产品并启动调查",
        source_id="cls_telegraph_html",
    )
    quoted_company_entity = extract_primary_entity(article_title_clean(quoted_company_article), quoted_company_article)
    assert_true(quoted_company_entity == "喜宝", "entity extraction should prefer quoted company names over full noisy headline fragments")

    embedded_latin_company_article = make_article(
        title="Uber斥资3.18亿美元增持德国食品配送公司Delivery Hero股份",
        source_id="weibo_tracked_mobile",
        lane="signal",
        coverage_scope="company",
    )
    embedded_latin_company_entity = extract_primary_entity(article_title_clean(embedded_latin_company_article), embedded_latin_company_article)
    assert_true(embedded_latin_company_entity == "Delivery Hero", "entity extraction should recover embedded Latin company names instead of partial suffix fragments")

    generic_pronoun_article = make_article(
        title="【研选】商业航天产业有望迎来快速发展期，这家公司目前合作的客户包括中国星网、中国卫星等",
        source_id="cls_telegraph_html",
    )
    generic_pronoun_entity = extract_primary_entity(article_title_clean(generic_pronoun_article), generic_pronoun_article)
    assert_true(generic_pronoun_entity is None, "entity extraction should reject generic pronoun-style company fragments")

    ministry_candidate_article = make_article(
        title="沙特能源部：东西输油管道的全部输送能力已成功恢复",
        source_id="cls_telegraph_html",
    )
    ministry_entity = extract_primary_entity(article_title_clean(ministry_candidate_article), ministry_candidate_article)
    assert_true(ministry_entity is None, "entity extraction should reject ministry-style policy bodies as company entities")
    ministry_institution = extract_institution_entity(article_title_clean(ministry_candidate_article))
    assert_true(ministry_institution == "沙特能源部", "institution extraction should preserve ministry-style policy bodies")

    association_candidate_article = make_article(
        title="中国钢铁工业协会：建立钢铁行业产能治理新机制",
        source_id="cls_telegraph_html",
    )
    association_entity = extract_primary_entity(article_title_clean(association_candidate_article), association_candidate_article)
    assert_true(association_entity is None, "entity extraction should reject association-derived sector names as company entities")
    association_institution = extract_institution_entity(article_title_clean(association_candidate_article))
    assert_true(association_institution == "中国钢铁工业协会", "institution extraction should preserve association-style policy bodies")

    regional_sector_article = make_article(
        title="欧盟航空燃油三周后或系统性短缺",
        source_id="cls_telegraph_html",
    )
    regional_sector_entity = extract_primary_entity(article_title_clean(regional_sector_article), regional_sector_article)
    assert_true(regional_sector_entity is None, "entity extraction should reject regional-sector fragments as company entities")
    regional_sector_institution = extract_institution_entity(article_title_clean(regional_sector_article))
    assert_true(regional_sector_institution is None, "institution extraction should not coerce regional-sector fragments into institutions")

    institution_prefix_article = make_article(
        title="周末要闻汇总：证监会部署上市公司治理新安排",
        source_id="cls_telegraph_html",
    )
    institution_prefix_entity = extract_institution_entity(article_title_clean(institution_prefix_article))
    assert_true(institution_prefix_entity == "证监会", "institution extraction should strip noisy roundup prefixes and preserve the underlying institution")

    exchange_prefix_article = make_article(
        title="市场消息：土耳其伊斯坦布尔证券交易所触发熔断",
        source_id="cls_telegraph_html",
    )
    exchange_prefix_entity = extract_institution_entity(article_title_clean(exchange_prefix_article))
    assert_true(exchange_prefix_entity == "土耳其伊斯坦布尔证券交易所", "institution extraction should recover exchange names from market-message style headlines")

    comma_suffix_article = make_article(
        title="财经深一度丨上市公司治理迎来新部署，证监会",
        source_id="cls_telegraph_html",
    )
    comma_suffix_entity = extract_institution_entity(article_title_clean(comma_suffix_article))
    assert_true(comma_suffix_entity == "证监会", "institution extraction should recover institution names from comma-suffix commentary titles")

    leading_particle_article = make_article(
        title="与深圳数据交易所签署合作协议",
        source_id="cls_telegraph_html",
    )
    leading_particle_entity = extract_institution_entity(article_title_clean(leading_particle_article))
    assert_true(leading_particle_entity == "深圳数据交易所", "institution extraction should strip leading particles before exchange-style institution names")

    central_bank_article = make_article(
        title="英国央行官员称仍需观察通胀路径",
        source_id="cls_telegraph_html",
    )
    central_bank_entity = extract_institution_entity(article_title_clean(central_bank_article))
    assert_true(central_bank_entity == "英国央行", "institution extraction should trim role suffixes and keep the underlying central bank")

    bulletin_prefix_article = make_article(
        title="【财联社4月10日晚间新闻精选】 1、证监会：增设创业板第四套上市标准",
        source_id="cls_telegraph_html",
    )
    bulletin_prefix_entity = extract_institution_entity(article_title_clean(bulletin_prefix_article))
    assert_true(
        bulletin_prefix_entity == "证监会",
        "institution extraction should strip bulletin-style news selection prefixes and preserve the underlying institution",
    )

    institution_tmp_dir, institution_db_path = build_temp_db_with_articles([])
    institution_conn = open_db(institution_db_path)
    try:
        institution_conn.execute(
            "INSERT INTO events (event_id, event_type, event_title, topic_key, first_seen_at, last_seen_at, novelty_state, event_state, confirmation_count, source_mix, score_vector, calibrated_confirmation, uncertainty, article_count_raw, independent_evidence_count, source_family_count, signal_platform_count, primary_industry, primary_entity, event_rank_score, event_rank_flags, opportunity_state, created_at, updated_at) VALUES (?, 'policy', 'test', 'event_type:policy', ?, ?, 'new', 'confirmed', 1, '{}', '{}', 1.0, 0.0, 1, 1, 1, 0, '', '', 1.0, '{}', 'unreviewed', ?, ?)",
            ("evt_institution", NOW.isoformat(), NOW.isoformat(), NOW.isoformat(), NOW.isoformat()),
        )
        insert_entity_links(
            institution_conn,
            "evt_institution",
            None,
            "沙特能源部",
            None,
            None,
        )
        institution_rows = institution_conn.execute(
            "SELECT entity_type, entity_id, entity_name FROM event_entity_links WHERE event_id = ? ORDER BY entity_type, entity_name",
            ("evt_institution",),
        ).fetchall()
        assert_true(
            len(institution_rows) == 1
            and institution_rows[0][0] == "institution"
            and institution_rows[0][2] == "沙特能源部",
            "entity link rebuild should persist extracted institutions as institution links",
        )

        institution_conn.execute(
            "INSERT INTO events (event_id, event_type, event_title, topic_key, first_seen_at, last_seen_at, novelty_state, event_state, confirmation_count, source_mix, score_vector, calibrated_confirmation, uncertainty, article_count_raw, independent_evidence_count, source_family_count, signal_platform_count, primary_industry, primary_entity, event_rank_score, event_rank_flags, opportunity_state, created_at, updated_at) VALUES (?, 'policy', 'test2', 'event_type:policy', ?, ?, 'new', 'confirmed', 1, '{}', '{}', 1.0, 0.0, 1, 1, 1, 0, '', '', 1.0, '{}', 'unreviewed', ?, ?)",
            ("evt_institution_preserved", NOW.isoformat(), NOW.isoformat(), NOW.isoformat(), NOW.isoformat()),
        )
        insert_entity_links(
            institution_conn,
            "evt_institution_preserved",
            None,
            None,
            None,
            None,
            preserved_links=[
                {
                    "entity_type": "institution",
                    "entity_id": "legacy-noisy",
                    "entity_name": "周末要闻汇总：证监会",
                    "relevance_score": 0.8,
                    "created_at": NOW.isoformat(),
                },
                {
                    "entity_type": "institution",
                    "entity_id": "legacy-market",
                    "entity_name": "市场消息：土耳其伊斯坦布尔证券交易所",
                    "relevance_score": 0.8,
                    "created_at": NOW.isoformat(),
                },
                {
                    "entity_type": "institution",
                    "entity_id": "legacy-bulletin",
                    "entity_name": "4月10日晚间新闻精选】 1、证监会",
                    "relevance_score": 0.8,
                    "created_at": NOW.isoformat(),
                },
            ],
        )
        normalized_rows = institution_conn.execute(
            "SELECT entity_type, entity_name FROM event_entity_links WHERE event_id = ? ORDER BY entity_name",
            ("evt_institution_preserved",),
        ).fetchall()
        assert_true(
            normalized_rows == [("institution", "土耳其伊斯坦布尔证券交易所"), ("institution", "证监会")],
            "entity link rebuild should normalize preserved institution noise down to canonical institution names",
        )
    finally:
        institution_conn.close()
        institution_tmp_dir.cleanup()

    macro_update_articles = [
        make_article(
            title="美联储官员称需继续观察通胀",
            source_id="macro_wire",
            coverage_scope="macro",
        ),
        make_article(
            title="美联储会议纪要显示官员担忧关税推升通胀",
            source_id="macro_wire",
            coverage_scope="macro",
            published_at="2026-04-06T21:20:00+00:00",
        ),
    ]
    macro_updates = collect_event_updates(
        macro_update_articles,
        None,
        None,
        "美联储政策",
        "policy",
    )
    assert_true(len(macro_updates) == 2, "event updates should preserve distinct macro sub-updates inside the same topic")
    assert_true(bool(macro_updates[0]["update_signature"]), "event updates should expose a stable update signature")

    preserved_tmp_dir, preserved_db_path = build_temp_db_with_articles([])
    preserved_conn = open_db(preserved_db_path)
    try:
        preserved_conn.execute(
            "INSERT INTO events (event_id, event_type, event_title, topic_key, first_seen_at, last_seen_at, novelty_state, event_state, confirmation_count, source_mix, score_vector, calibrated_confirmation, uncertainty, article_count_raw, independent_evidence_count, source_family_count, signal_platform_count, primary_industry, primary_entity, event_rank_score, event_rank_flags, opportunity_state, created_at, updated_at) VALUES (?, 'company_action', 'test', 'company:test', ?, ?, 'new', 'confirmed', 1, '{}', '{}', 1.0, 0.0, 1, 1, 1, 0, '', '浙江浙能燃料集团有限公司', 1.0, '{}', 'unreviewed', ?, ?)",
            ("evt_preserved_company", NOW.isoformat(), NOW.isoformat(), NOW.isoformat(), NOW.isoformat()),
        )
        insert_entity_links(
            preserved_conn,
            "evt_preserved_company",
            "浙江浙能燃料集团有限公司",
            None,
            None,
            None,
            preserved_links=[
                {
                    "entity_type": "company",
                    "entity_id": "legacy-bad",
                    "entity_name": "浙江浙能燃料集团有限公司增持1206.54万股股份",
                    "relevance_score": 0.9,
                    "created_at": NOW.isoformat(),
                },
                {
                    "entity_type": "company",
                    "entity_id": "legacy-good",
                    "entity_name": "浙江浙能燃料集团有限公司",
                    "relevance_score": 0.9,
                    "created_at": NOW.isoformat(),
                },
            ],
        )
        rows = preserved_conn.execute(
            "SELECT entity_type, entity_id, entity_name FROM event_entity_links WHERE event_id = ? ORDER BY entity_name",
            ("evt_preserved_company",),
        ).fetchall()
        company_rows = [row for row in rows if row[0] == "company"]
        assert_true(len(company_rows) == 1, "entity link rebuild should collapse preserved company junk down to the current canonical company entity")
        assert_true(company_rows[0][2] == "浙江浙能燃料集团有限公司", "entity link rebuild should keep the trimmed canonical company name")
    finally:
        preserved_conn.close()
        preserved_tmp_dir.cleanup()

    oil_article = make_article(
        title="主要产油国宣布5月继续增产",
        source_id="cls_telegraph_html",
    )
    _, oil_flags = score_article(oil_article)
    assert_true(oil_flags["features"]["entity_relevance"] >= 0.55, "oil supply headline should pick up commodity mapping")

    geo_article_a = make_article(
        title="【伊朗两处住宅遭袭受损 至少13人死亡】财联社4月7日电",
        published_at="2026-04-07T10:05:00+00:00",
    )
    geo_article_b = make_article(
        title="【联合国秘书长呼吁各方保护平民】财联社4月7日电",
        published_at="2026-04-07T10:25:00+00:00",
    )
    geo_type_a, geo_action_a = infer_event_type(article_title_clean(geo_article_a), geo_article_a)
    geo_classify_a = headline_focus_text(article_title_clean(geo_article_a)) or article_title_clean(geo_article_a)[:140]
    geo_key_a = merge_key(
        geo_article_a,
        article_title_clean(geo_article_a),
        geo_type_a,
        geo_action_a,
        extract_primary_entity(article_title_clean(geo_article_a), geo_article_a),
        keyword_match(geo_classify_a, INDUSTRY_KEYWORDS),
        keyword_match(geo_classify_a, MACRO_THEMES),
    )
    geo_type_b, geo_action_b = infer_event_type(article_title_clean(geo_article_b), geo_article_b)
    geo_classify_b = headline_focus_text(article_title_clean(geo_article_b)) or article_title_clean(geo_article_b)[:140]
    geo_key_b = merge_key(
        geo_article_b,
        article_title_clean(geo_article_b),
        geo_type_b,
        geo_action_b,
        extract_primary_entity(article_title_clean(geo_article_b), geo_article_b),
        keyword_match(geo_classify_b, INDUSTRY_KEYWORDS),
        keyword_match(geo_classify_b, MACRO_THEMES),
    )
    assert_true(geo_key_a != geo_key_b, "different macro-theme updates in the same hour should not collapse into one event key")

    tmp_dir, db_path = build_temp_db_with_articles([article_a, article_b])
    try:
        run_builder(db_path, "--as-of", (NOW + timedelta(days=2)).isoformat())
        conn = open_db(db_path)
        try:
            row = conn.execute(
                """
                SELECT
                    COUNT(*),
                    MAX(confirmation_count),
                    MAX(event_state),
                    MAX(independent_evidence_count),
                    MAX(source_family_count),
                    MAX(topic_key)
                FROM events
                """
            ).fetchone()
            assert_true(int(row[0] or 0) == 1, "related Mitsui articles should merge into one event in SQLite build")
            assert_true(int(row[1] or 0) == 2, "merged event should keep confirmation count")
            assert_true(str(row[2] or "") == "mature", "stale multi-source confirmation event should enter mature state")
            assert_true(int(row[3] or 0) >= 2, "merged event should record independent evidence count")
            assert_true(int(row[4] or 0) >= 2, "merged event should record source family count")
            assert_true(str(row[5] or "").startswith("company:"), "entity-led event should persist a company topic_key")
            event_id = conn.execute("SELECT event_id FROM events LIMIT 1").fetchone()[0]
            rank_payload = conn.execute(
                "SELECT event_rank_flags, score_vector, calibrated_confirmation, uncertainty FROM events WHERE event_id = ?",
                (event_id,),
            ).fetchone()
            assert_true(rank_payload is not None, "event contract payload should be persisted")
            assert_true("market_significance" in str(rank_payload[1] or ""), "score_vector should be written to events table")
            assert_true(float(rank_payload[2] or 0.0) > 0.0, "calibrated confirmation should be populated")
            conn.execute("UPDATE events SET opportunity_state = 'mapped' WHERE event_id = ?", (event_id,))
            conn.commit()
        finally:
            conn.close()

        run_builder(db_path, "--no-rebuild")
        conn = open_db(db_path)
        try:
            event_row = conn.execute("SELECT event_id, opportunity_state FROM events LIMIT 1").fetchone()
            assert_true(event_row is not None, "event should still exist after --no-rebuild refresh")
            state = conn.execute("SELECT opportunity_state FROM events LIMIT 1").fetchone()[0]
            assert_true(state == "mapped", "--no-rebuild should preserve existing opportunity_state")
        finally:
            conn.close()

        run_builder(db_path)
        conn = open_db(db_path)
        try:
            rows = conn.execute("SELECT event_id, opportunity_state FROM events").fetchall()
            assert_true(len(rows) == 1, "rebuilding identical data should not create duplicate event rows")
            assert_true(rows[0][0] == event_id, "rebuilding identical data should keep the same event_id")
            assert_true(rows[0][1] == "mapped", "rebuilding identical data should preserve mapped state")
        finally:
            conn.close()
    finally:
        tmp_dir.cleanup()

    family_tmp_dir, family_db_path = build_temp_db_with_articles(
        [
            make_article(
                title="Acme Corp announces $500 million factory expansion",
                summary="Factory expansion plan",
                source_id="prnewswire_all_releases",
                source_family="wire:prnewswire",
                canonical_url="https://www.prnewswire.com/news-releases/acme-expansion.html",
            ),
            make_article(
                title="Acme Corp announces $500 million factory expansion",
                summary="Factory expansion plan",
                source_id="prnewswire_general_business",
                source_family="wire:prnewswire",
                canonical_url="https://www.prnewswire.com/news-releases/acme-expansion.html",
            ),
        ]
    )
    try:
        run_builder(family_db_path)
        conn = open_db(family_db_path)
        try:
            row = conn.execute(
                """
                SELECT
                    COUNT(*),
                    MAX(article_count_raw),
                    MAX(confirmation_count),
                    MAX(independent_evidence_count),
                    MAX(source_family_count)
                FROM events
                """
            ).fetchone()
            assert_true(int(row[0] or 0) == 1, "same-wire family duplicates should merge into one shared event")
            assert_true(int(row[1] or 0) == 2, "raw article count should preserve duplicated wire coverage")
            assert_true(int(row[2] or 0) == 1, "same source family should only contribute one confirmation unit")
            assert_true(int(row[3] or 0) == 1, "same source family should collapse to one independent evidence unit")
            assert_true(int(row[4] or 0) == 1, "same source family should count as one family")
        finally:
            conn.close()
    finally:
        family_tmp_dir.cleanup()

    alias_tmp_dir, alias_db_path = build_temp_db_with_articles(
        [
            make_article(
                title="POP MART signs North America store expansion contract",
                source_id="reuters_company_bing",
                source_family="host:reuters",
                canonical_url="https://www.reuters.com/world/china/pop-mart-expansion",
                published_at="2026-04-07T09:00:00+00:00",
            ),
            make_article(
                title="泡泡玛特签署北美扩张合作协议",
                source_id="company_jiemian_company_html",
                source_family="media:jiemian",
                canonical_url="https://www.jiemian.com/article/pop-mart-expansion",
                published_at="2026-04-07T09:20:00+00:00",
            ),
        ]
    )
    try:
        run_builder(alias_db_path)
        conn = open_db(alias_db_path)
        try:
            row = conn.execute(
                """
                SELECT COUNT(*), COUNT(DISTINCT topic_key), MAX(primary_entity)
                FROM events
                """
            ).fetchone()
            assert_true(int(row[0] or 0) == 1, "cross-language alias variants with the same canonical company and context should merge into one event")
            assert_true(int(row[1] or 0) == 1, "alias variants should still collapse to one canonical topic key")
            assert_true(str(row[2] or "") == "泡泡玛特", "alias variants should persist the canonical company display name")
            link_rows = conn.execute(
                """
                SELECT entity_id, entity_name
                FROM event_entity_links
                WHERE entity_type = 'company'
                ORDER BY entity_id, entity_name
                """
            ).fetchall()
            assert_true(len(link_rows) == 1, "merged alias variants should emit one canonical company entity link")
            assert_true(all(str(row[0] or "") == "pop_mart" for row in link_rows), "alias variants should use canonical company ids in entity links")
            assert_true(all(str(row[1] or "") == "泡泡玛特" for row in link_rows), "alias variants should use canonical company display names in entity links")
        finally:
            conn.close()
    finally:
        alias_tmp_dir.cleanup()

    persisted_tmp_dir = tempfile.TemporaryDirectory()
    persisted_db_path = Path(persisted_tmp_dir.name) / "persisted_state_smoke.db"
    conn = open_db(persisted_db_path)
    try:
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        conn.execute(
            """
            INSERT INTO source_registry (
                source_id, name, lane, source_family, source_type, trust_tier, coverage_scope,
                collector_owner, scheduler_class, origin_system, legacy_key,
                phase1_disposition, enabled, description
            ) VALUES ('cls_telegraph_html', 'cls_telegraph_html', 'confirmation', 'wire:cls', 'rss', 1, 'mixed', 'shared', 'high_freq', 'news_event_hub', 'cls_telegraph_html', 'migrate_phase1', 1, '')
            """
        )
        conn.execute(
            """
            INSERT INTO news_articles (
                article_id, source_id, title, title_norm, summary, body_text, url,
                canonical_url, published_at, timestamp_quality, content_hash, language,
                collector_scope, collected_at
            ) VALUES (?, 'cls_telegraph_html', ?, ?, ?, ?, ?, ?, ?, 'exact', ?, 'zh', 'baseline_shared', ?)
            """,
            (
                article_a.article_id,
                article_a.title,
                article_a.title_norm,
                article_a.summary,
                article_a.summary,
                "https://example.com/recent",
                "https://example.com/recent",
                article_a.published_at,
                "recent_hash",
                article_a.collected_at,
            ),
        )
        conn.execute(
            """
            INSERT INTO news_articles (
                article_id, source_id, title, title_norm, summary, body_text, url,
                canonical_url, published_at, timestamp_quality, content_hash, language,
                collector_scope, collected_at
            ) VALUES ('historical_article', 'cls_telegraph_html', '历史事件标题', 'historical title', 'historical summary', 'historical summary', 'https://example.com/historical', 'https://example.com/historical', '2026-01-01T09:00:00+00:00', 'exact', 'historical_hash', 'zh', 'baseline_shared', '2026-01-01T09:00:00+00:00')
            """
        )
        conn.execute(
            """
            INSERT INTO events (
                event_id, event_type, event_title, first_seen_at, last_seen_at,
                novelty_state, confirmation_count, source_mix, primary_industry, primary_entity,
                event_rank_score, event_rank_flags, opportunity_state, created_at, updated_at
            ) VALUES ('evt_historical_keep', 'company_action', '历史事件', '2026-01-01T09:00:00+00:00', '2026-01-01T09:00:00+00:00', 'stale', 1, '{"confirmation":1}', NULL, '历史公司', 10.0, '{}', 'mapped', '2026-01-01T09:00:00+00:00', '2026-01-01T09:00:00+00:00')
            """
        )
        conn.execute(
            "INSERT INTO article_event_links (article_id, event_id, link_type, created_at) VALUES ('historical_article', 'evt_historical_keep', 'primary', datetime('now'))"
        )
        conn.commit()
    finally:
        conn.close()

    try:
        run_builder(persisted_db_path)
        current_event_id = event_id_for_key(key_a)
        conn = open_db(persisted_db_path)
        try:
            conn.execute(
                "INSERT INTO event_entity_links (event_id, entity_type, entity_id, entity_name, relevance_score, created_at) VALUES (?, 'theme', 'manual-shipping-theme', 'Manual Shipping Theme', 0.7, datetime('now'))",
                (current_event_id,),
            )
            conn.commit()
        finally:
            conn.close()

        run_builder(persisted_db_path)
        conn = open_db(persisted_db_path)
        try:
            historical = conn.execute("SELECT opportunity_state FROM events WHERE event_id = 'evt_historical_keep'").fetchone()
            assert_true(historical is not None and historical[0] == "mapped", "historical event outside lookback should persist with its state")
            manual_link_count = conn.execute(
                "SELECT COUNT(*) FROM event_entity_links WHERE event_id = ? AND entity_id = 'manual-shipping-theme'",
                (current_event_id,),
            ).fetchone()[0]
            assert_true(int(manual_link_count) == 1, "existing detailed entity link should survive rebuild")
        finally:
            conn.close()
    finally:
        persisted_tmp_dir.cleanup()

    rollback_tmp_dir, rollback_db_path = build_temp_db_with_articles([article_a, article_b])
    try:
        run_builder(rollback_db_path)
        conn = open_db(rollback_db_path)
        try:
            rollback_event_id = conn.execute("SELECT event_id FROM events LIMIT 1").fetchone()[0]
            conn.execute(
                "INSERT INTO event_entity_links (event_id, entity_type, entity_id, entity_name, relevance_score, created_at) VALUES (?, 'theme', 'manual-shipping-theme', 'Manual Shipping Theme', 0.7, datetime('now'))",
                (rollback_event_id,),
            )
            conn.execute(
                """
                CREATE TRIGGER fail_manual_entity_link_reinsert
                BEFORE INSERT ON event_entity_links
                WHEN NEW.entity_id = 'manual-shipping-theme'
                BEGIN
                    SELECT RAISE(ABORT, 'forced entity-link failure');
                END;
                """
            )
            conn.commit()
        finally:
            conn.close()

        proc = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "build_event_layer.py"), "--db", str(rollback_db_path), "--as-of", NOW.isoformat()],
            capture_output=True,
            text=True,
        )
        assert_true(proc.returncode != 0, "fault-injected rebuild should fail so rollback behavior can be verified")

        conn = open_db(rollback_db_path)
        try:
            link_count = conn.execute(
                "SELECT COUNT(*) FROM article_event_links WHERE event_id = ?",
                (rollback_event_id,),
            ).fetchone()[0]
            manual_link_count = conn.execute(
                "SELECT COUNT(*) FROM event_entity_links WHERE event_id = ? AND entity_id = 'manual-shipping-theme'",
                (rollback_event_id,),
            ).fetchone()[0]
            assert_true(int(link_count) == 2, "failed rebuild should roll back article-event relationship deletions")
            assert_true(int(manual_link_count) == 1, "failed rebuild should roll back preserved entity-link deletions")
        finally:
            conn.close()
    finally:
        rollback_tmp_dir.cleanup()

    migrated_tmp_dir, migrated_db_path = build_temp_db_with_articles([article_a, article_b])
    try:
        legacy_event_id = "evt_legacy_mitsui_state"
        conn = open_db(migrated_db_path)
        try:
            conn.execute(
                """
                INSERT INTO events (
                    event_id, event_type, event_title, first_seen_at, last_seen_at,
                    novelty_state, confirmation_count, source_mix, primary_industry, primary_entity,
                    event_rank_score, event_rank_flags, opportunity_state, created_at, updated_at
                ) VALUES (?, 'production_supply', '旧版日本商船三井事件', '2026-04-04T09:20:50+00:00', '2026-04-04T09:20:50+00:00', 'developing', 1, '{"confirmation":1}', '航运', '日本商船三井公司', 42.0, '{}', 'mapped', '2026-04-04T09:20:50+00:00', '2026-04-04T09:20:50+00:00')
                """,
                (legacy_event_id,),
            )
            conn.execute(
                """
                INSERT INTO article_event_links (article_id, event_id, link_type, created_at)
                VALUES (?, ?, 'primary', datetime('now'))
                """,
                (article_a.article_id, legacy_event_id),
            )
            conn.execute(
                """
                INSERT INTO event_entity_links (event_id, entity_type, entity_id, entity_name, relevance_score, created_at)
                VALUES (?, 'theme', 'manual-legacy-theme', 'Manual Legacy Theme', 0.7, datetime('now'))
                """,
                (legacy_event_id,),
            )
            conn.commit()
        finally:
            conn.close()

        run_builder(migrated_db_path)
        conn = open_db(migrated_db_path)
        try:
            migrated_event_id = event_id_for_key(key_a)
            migrated_state = conn.execute(
                "SELECT opportunity_state FROM events WHERE event_id = ?",
                (migrated_event_id,),
            ).fetchone()
            assert_true(migrated_state is not None and migrated_state[0] == "mapped", "state should migrate when merge-key changes but the old event articles are a subset of the new event")
            migrated_manual_link = conn.execute(
                "SELECT COUNT(*) FROM event_entity_links WHERE event_id = ? AND entity_id = 'manual-legacy-theme'",
                (migrated_event_id,),
            ).fetchone()[0]
            assert_true(int(migrated_manual_link) == 1, "manual entity links should follow the migrated event state when the event_id changes")
            legacy_row = conn.execute(
                "SELECT COUNT(*) FROM events WHERE event_id = ?",
                (legacy_event_id,),
            ).fetchone()[0]
            assert_true(int(legacy_row) == 0, "obsolete legacy event rows should be pruned after state migration")
        finally:
            conn.close()
    finally:
        migrated_tmp_dir.cleanup()

    shrink_tmp_dir, shrink_db_path = build_temp_db_with_articles([article_a])
    try:
        legacy_event_id = "evt_legacy_mitsui_two_articles"
        conn = open_db(shrink_db_path)
        try:
            conn.execute(
                """
                INSERT INTO news_articles (
                    article_id, source_id, title, title_norm, summary, body_text, url,
                    canonical_url, published_at, timestamp_quality, content_hash, language,
                    collector_scope, collected_at
                ) VALUES ('legacy_support_article', 'cls_telegraph_html', ?, ?, '', '', 'https://example.com/legacy-support', 'https://example.com/legacy-support', '2026-04-04T09:19:34+00:00', 'exact', 'legacy_support_hash', 'zh', 'baseline_shared', '2026-04-04T09:19:34+00:00')
                """,
                (title_b, title_b.lower()),
            )
            conn.execute(
                """
                INSERT INTO events (
                    event_id, event_type, event_title, first_seen_at, last_seen_at,
                    novelty_state, confirmation_count, source_mix, primary_industry, primary_entity,
                    event_rank_score, event_rank_flags, opportunity_state, created_at, updated_at
                ) VALUES (?, 'production_supply', '旧版双文章事件', '2026-04-04T09:19:34+00:00', '2026-04-04T09:20:50+00:00', 'developing', 2, '{"confirmation":2}', '航运', '日本商船三井公司', 42.0, '{}', 'rejected', '2026-04-04T09:19:34+00:00', '2026-04-04T09:20:50+00:00')
                """,
                (legacy_event_id,),
            )
            conn.execute(
                "INSERT INTO article_event_links (article_id, event_id, link_type, created_at) VALUES (?, ?, 'primary', datetime('now'))",
                (article_a.article_id, legacy_event_id),
            )
            conn.execute(
                "INSERT INTO article_event_links (article_id, event_id, link_type, created_at) VALUES ('legacy_support_article', ?, 'supporting', datetime('now'))",
                (legacy_event_id,),
            )
            conn.commit()
        finally:
            conn.close()

        run_builder(shrink_db_path)
        conn = open_db(shrink_db_path)
        try:
            migrated_event_id = event_id_for_key(key_a)
            migrated_state = conn.execute(
                "SELECT opportunity_state FROM events WHERE event_id = ?",
                (migrated_event_id,),
            ).fetchone()
            assert_true(migrated_state is not None and migrated_state[0] == "rejected", "state should also survive when an old supporting article falls out of the current lookback")
        finally:
            conn.close()
    finally:
        shrink_tmp_dir.cleanup()

    radar_tmp_dir = tempfile.TemporaryDirectory()
    radar_db_path = Path(radar_tmp_dir.name) / "radar_threshold_smoke.db"
    radar_now = datetime.now(timezone.utc).replace(microsecond=0)
    radar_keep_at = radar_now.isoformat(timespec="seconds")
    radar_drop_at = (radar_now - timedelta(hours=1)).isoformat(timespec="seconds")
    radar_rejected_at = (radar_now - timedelta(hours=2)).isoformat(timespec="seconds")
    conn = open_db(radar_db_path)
    try:
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        conn.execute(
            """
            INSERT INTO events (
                event_id, event_type, event_title, first_seen_at, last_seen_at,
                novelty_state, confirmation_count, source_mix, primary_industry, primary_entity,
                event_rank_score, event_rank_flags, opportunity_state, created_at, updated_at
            ) VALUES
            (?, 'production_supply', '航运供给扰动', ?, ?, 'new', 2, '{"confirmation":2}', '航运', NULL, 45.0, '{}', 'unreviewed', ?, ?),
            (?, 'macro_data', '半导体板块早盘跟涨', ?, ?, 'new', 1, '{"confirmation":1}', '半导体', NULL, 12.0, '{}', 'unreviewed', ?, ?),
            (?, 'production_supply', '已拒绝的航运噪音', ?, ?, 'new', 1, '{"confirmation":1}', '航运', NULL, 50.0, '{}', 'rejected', ?, ?)
            """,
            (
                "evt_radar_keep",
                radar_keep_at,
                radar_keep_at,
                radar_keep_at,
                radar_keep_at,
                "evt_radar_drop",
                radar_drop_at,
                radar_drop_at,
                radar_drop_at,
                radar_drop_at,
                "evt_radar_rejected",
                radar_rejected_at,
                radar_rejected_at,
                radar_rejected_at,
                radar_rejected_at,
            ),
        )
        conn.execute(
            """
            INSERT INTO event_entity_links (event_id, entity_type, entity_id, entity_name, relevance_score, created_at) VALUES
            ('evt_radar_keep', 'industry', 'shipping', '航运', 0.9, datetime('now')),
            ('evt_radar_drop', 'industry', 'semiconductor', '半导体', 0.9, datetime('now')),
            ('evt_radar_rejected', 'industry', 'shipping', '航运', 0.9, datetime('now'))
            """
        )
        rows = conn.execute("SELECT event_id FROM v_radar_industry ORDER BY event_id").fetchall()
        assert_true(rows == [("evt_radar_keep",)], "radar view should only expose industry events that also pass the shared score threshold")
        digest_rows = conn.execute("SELECT event_id FROM v_daily_digest ORDER BY event_id").fetchall()
        assert_true(("evt_radar_rejected",) not in digest_rows, "daily digest should not expose rejected shared-layer events")
    finally:
        conn.close()
        radar_tmp_dir.cleanup()

    unresolved_articles = [
        make_article(
            title="签署关键供货合同，产线扩建同步推进",
            summary="报道提到结构性公司动作，但标题未直接写明主体",
            source_id="cls_telegraph_html",
            coverage_scope="company",
            canonical_url="https://example.com/unresolved-reviewable",
        ),
        make_article(
            title="黎巴嫩总理萨拉姆推迟赴美行程",
            summary="政策/地缘更新，不属于当前需要人工补映射的 review surface",
            source_id="cls_telegraph_html",
            coverage_scope="mixed",
            canonical_url="https://example.com/unresolved-macro",
        ),
        make_article(
            title="【电报解读】AI电力需求重塑能源融资格局，该产业或是解决AI能源需求的关键方案",
            summary="概念性产业解读，不应进入 unresolved mapping review surface",
            source_id="cls_telegraph_html",
            coverage_scope="company",
            canonical_url="https://example.com/unresolved-conceptual",
        ),
        make_article(
            title="上交所举办“三开门”审计机构专场宣讲暨业务培训会",
            summary="监管/培训活动，不应进入 unresolved mapping review surface",
            source_id="cls_telegraph_html",
            coverage_scope="mixed",
            canonical_url="https://example.com/unresolved-reg-forum",
        ),
    ]
    unresolved_tmp_dir, unresolved_db_path = build_temp_db_with_articles(unresolved_articles)
    try:
        run_builder(unresolved_db_path)
        conn = open_db(unresolved_db_path)
        try:
            unresolved_rows = conn.execute(
                "SELECT event_title, unresolved_reason, mapping_version FROM unresolved_event_mappings"
            ).fetchall()
            assert_true(len(unresolved_rows) == 0, "builder should skip non-reviewable unresolved mapping noise")
        finally:
            conn.close()
    finally:
        unresolved_tmp_dir.cleanup()

    print("event_layer_smoke_ok")


if __name__ == "__main__":
    main()
