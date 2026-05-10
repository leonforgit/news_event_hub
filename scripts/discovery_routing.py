from __future__ import annotations

import re
from typing import Any


CHINESE_RE = re.compile(r"[\u4e00-\u9fff]")
DISCOVERY_ENTRYPOINT = "scripts/run_company_discovery.py"

GLOBAL_OPTIONAL_RECALL_SOURCE_IDS = [
    "marketaux_global_optional",
    "mediastack_global_optional",
]
GLOBAL_DISCOVERY_SOURCE_IDS = [
    "akshare_stock_info_global_cls",
    "akshare_stock_info_global_em",
    "akshare_stock_info_global_ths",
    "reuters_company_bing",
    "company_cnbc_bing",
    "company_marketwatch_bing",
    "serpstack_company_discovery_optional",
    "company_mna_bing",
    "company_spin_bing",
    "company_asset_sale_bing",
    "company_capacity_bing",
    "company_financing_bing",
    "company_resources_bing",
    "company_new_industry_bing",
    "company_rumor_bing",
    "reddit_tracked_search",
]
CN_HK_DISCOVERY_SOURCE_IDS = [
    "company_rumor_china_bing",
    "weibo_tracked_mobile",
    "xueqiu_tracked_search",
]
CN_ONLY_DISCOVERY_SOURCE_IDS = [
    "cninfo_sz_latest",
    "cninfo_sh_latest",
    "akshare_stock_notice_report",
    "company_stcn_html",
    "company_jiemian_stock_html",
    "company_jiemian_company_html",
    "guba_tracked_direct",
]
HK_ONLY_DISCOVERY_SOURCE_IDS = [
    "hkex_tracked_latest",
]
US_ONLY_DISCOVERY_SOURCE_IDS = [
    "sec_8k_current",
    "sec_6k_current",
]
MACRO_DISCOVERY_SOURCE_IDS = [
    "fed_press",
    "govcn_yaowen",
    "akshare_news_cctv",
    "jinshi_api",
    "jinshi_telegram_channel",
    "xinhua_fortune_html",
    "cls_telegraph_html",
    "reuters_macro_bing",
    "prnewswire_policy_public_interest",
    "macro_oil_bing",
    "macro_rates_bing",
    "macro_china_bing",
    "macro_us_china_bing",
    "macro_middleeast_bing",
    "macro_defense_policy_bing",
]
MACRO_SIGNAL_SOURCE_IDS = [
    "reddit_market_forums",
    "v2ex_all_feed",
]
INDUSTRY_DISCOVERY_SOURCE_IDS = [
    "xinhua_fortune_html",
    "cls_telegraph_html",
    "akshare_stock_info_global_cls",
    "akshare_stock_info_global_em",
    "akshare_stock_info_global_ths",
    "cailian_api",
    "prnewswire_all_releases",
    "prnewswire_financial_services",
    "globenewswire_press_releases",
    "company_new_industry_bing",
    "company_capacity_bing",
    "company_resources_bing",
]
INDUSTRY_SIGNAL_SOURCE_IDS = [
    "xueqiu_public_timeline",
    "xueqiu_hot_stocks",
    "reddit_market_forums",
    "v2ex_all_feed",
    "weibo_tracked_mobile",
]
INSTITUTION_DISCOVERY_SOURCE_IDS = [
    "fed_press",
    "govcn_yaowen",
    "xinhua_fortune_html",
    "reuters_macro_bing",
    "macro_china_bing",
    "macro_us_china_bing",
    "macro_defense_policy_bing",
    "prnewswire_policy_public_interest",
]
SPECIAL_SITUATION_DISCOVERY_SOURCE_IDS = [
    "reuters_company_bing",
    "company_mna_bing",
    "company_spin_bing",
    "company_asset_sale_bing",
    "company_financing_bing",
    "globenewswire_mna",
    "serpstack_company_discovery_optional",
]
SPECIAL_SITUATION_SIGNAL_SOURCE_IDS = [
    "reddit_tracked_search",
    "company_rumor_bing",
    "company_rumor_china_bing",
    "xueqiu_tracked_search",
]
TRACKING_DISCOVERY_SOURCE_IDS = [
    "cls_telegraph_html",
    "akshare_stock_info_global_cls",
    "akshare_stock_info_global_em",
    "akshare_stock_info_global_ths",
    "cailian_api",
    "marketaux_global_optional",
    "mediastack_global_optional",
]
TRACKING_SIGNAL_SOURCE_IDS = [
    "xueqiu_public_timeline",
    "xueqiu_hot_stocks",
    "reddit_market_forums",
    "v2ex_all_feed",
]
ROUTE_KEYS = (
    "company",
    "macro",
    "industry",
    "institution",
    "special_situation",
    "tracking_update",
)


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        clean = str(value or "").strip()
        if not clean or clean.casefold() in seen:
            continue
        seen.add(clean.casefold())
        result.append(clean)
    return result


def _build_route(
    *,
    route_key: str,
    entity_type: str,
    mode: str,
    search_terms: list[str] | None = None,
    live_source_ids: list[str] | None = None,
    signal_source_ids: list[str] | None = None,
    browser_source_ids: list[str] | None = None,
    optional_recall_source_ids: list[str] | None = None,
    notes: list[str] | None = None,
    entrypoint: str = "",
) -> dict[str, Any]:
    route: dict[str, Any] = {
        "route_key": route_key,
        "entity_type": entity_type,
        "mode": mode,
        "search_terms": _dedupe_preserve_order(list(search_terms or [])),
        "live_source_ids": _dedupe_preserve_order(list(live_source_ids or [])),
        "signal_source_ids": _dedupe_preserve_order(list(signal_source_ids or [])),
        "browser_source_ids": _dedupe_preserve_order(list(browser_source_ids or [])),
        "optional_recall_source_ids": _dedupe_preserve_order(list(optional_recall_source_ids or [])),
        "refresh_flow": [
            "run_selected_sources",
            "rebuild_event_layer",
            "refresh_consumer_exports",
        ],
        "notes": list(notes or []),
    }
    if entrypoint:
        route["entrypoint"] = entrypoint
        route["is_executable"] = True
    return route


def source_ids_for_company_discovery(
    search_terms: list[str],
    ticker: str = "",
    region: str = "",
) -> tuple[list[str], list[str]]:
    live_ids = list(GLOBAL_DISCOVERY_SOURCE_IDS)
    browser_ids: list[str] = []
    clean_region = str(region or "").strip().upper() or "GLOBAL"
    has_chinese = any(CHINESE_RE.search(term or "") for term in search_terms)
    if clean_region in {"CN", "HK"} or has_chinese:
        live_ids.extend(CN_HK_DISCOVERY_SOURCE_IDS)
        browser_ids.append("xueqiu_tracked_search")
    if clean_region == "CN":
        live_ids.extend(CN_ONLY_DISCOVERY_SOURCE_IDS)
    if clean_region == "HK":
        live_ids.extend(HK_ONLY_DISCOVERY_SOURCE_IDS)
    if clean_region in {"US", "GLOBAL"}:
        live_ids.extend(US_ONLY_DISCOVERY_SOURCE_IDS)
    return _dedupe_preserve_order(live_ids), _dedupe_preserve_order(browser_ids)


def source_ids_for_route(
    route_key: str,
    search_terms: list[str],
    ticker: str = "",
    region: str = "",
) -> tuple[list[str], list[str]]:
    clean_route_key = str(route_key or "").strip().lower() or "company"
    if clean_route_key == "company":
        return source_ids_for_company_discovery(search_terms, ticker=ticker, region=region)
    if clean_route_key == "macro":
        return (
            _dedupe_preserve_order(MACRO_DISCOVERY_SOURCE_IDS + MACRO_SIGNAL_SOURCE_IDS + GLOBAL_OPTIONAL_RECALL_SOURCE_IDS),
            [],
        )
    if clean_route_key == "industry":
        return (
            _dedupe_preserve_order(INDUSTRY_DISCOVERY_SOURCE_IDS + INDUSTRY_SIGNAL_SOURCE_IDS + GLOBAL_OPTIONAL_RECALL_SOURCE_IDS),
            [],
        )
    if clean_route_key == "institution":
        return (
            _dedupe_preserve_order(INSTITUTION_DISCOVERY_SOURCE_IDS + MACRO_SIGNAL_SOURCE_IDS + GLOBAL_OPTIONAL_RECALL_SOURCE_IDS),
            [],
        )
    if clean_route_key == "special_situation":
        return (
            _dedupe_preserve_order(SPECIAL_SITUATION_DISCOVERY_SOURCE_IDS + SPECIAL_SITUATION_SIGNAL_SOURCE_IDS + GLOBAL_OPTIONAL_RECALL_SOURCE_IDS),
            ["xueqiu_tracked_search"],
        )
    if clean_route_key == "tracking_update":
        return (
            _dedupe_preserve_order(TRACKING_DISCOVERY_SOURCE_IDS + TRACKING_SIGNAL_SOURCE_IDS + GLOBAL_OPTIONAL_RECALL_SOURCE_IDS),
            [],
        )
    return (_dedupe_preserve_order(GLOBAL_OPTIONAL_RECALL_SOURCE_IDS), [])


def build_company_discovery_routes(
    company: str,
    aliases: list[str] | None = None,
    ticker: str = "",
    region: str = "",
) -> dict[str, Any]:
    search_terms = _dedupe_preserve_order([company, *(aliases or []), ticker, ticker.split(".", 1)[0] if ticker else ""])
    live_source_ids, browser_source_ids = source_ids_for_company_discovery(search_terms, ticker=ticker, region=region)
    clean_region = str(region or "").strip().upper() or "GLOBAL"
    route = _build_route(
        route_key="company",
        entity_type="company",
        mode="query_driven",
        search_terms=search_terms,
        live_source_ids=live_source_ids,
        signal_source_ids=["reddit_tracked_search", "company_rumor_bing", "company_rumor_china_bing"],
        browser_source_ids=browser_source_ids,
        optional_recall_source_ids=GLOBAL_OPTIONAL_RECALL_SOURCE_IDS,
        notes=[
            "Use the shared feed lookup first; trigger company discovery only when the shared library is thin or missing the target.",
            "Company discovery is executable today and should write matched articles back into the shared database before rebuilding events.",
        ],
        entrypoint=DISCOVERY_ENTRYPOINT,
    )
    route["route_version"] = "company_discovery_v1"
    route["region"] = clean_region
    route["refresh_flow"] = [
        "run_discovery_sources",
        "rebuild_event_layer",
        "refresh_consumer_exports",
    ]
    return route


def build_macro_discovery_route(search_terms: list[str] | None = None) -> dict[str, Any]:
    live_source_ids, browser_source_ids = source_ids_for_route("macro", list(search_terms or []))
    route = _build_route(
        route_key="macro",
        entity_type="macro_theme",
        mode="query_driven",
        search_terms=list(search_terms or []),
        live_source_ids=live_source_ids,
        browser_source_ids=browser_source_ids,
        optional_recall_source_ids=GLOBAL_OPTIONAL_RECALL_SOURCE_IDS,
        notes=[
            "Macro misses should start from policy, official, and wire confirmation sources, then widen to forum-style signal surfaces for reaction context.",
            "The shared discovery runner can execute this route directly with target search terms and write the matched articles back into the shared database.",
        ],
        entrypoint=DISCOVERY_ENTRYPOINT,
    )
    route["route_version"] = "macro_discovery_v1"
    return route


def build_special_situation_discovery_route(search_terms: list[str] | None = None) -> dict[str, Any]:
    live_source_ids, browser_source_ids = source_ids_for_route("special_situation", list(search_terms or []))
    route = _build_route(
        route_key="special_situation",
        entity_type="company",
        mode="query_driven",
        search_terms=list(search_terms or []),
        live_source_ids=live_source_ids,
        signal_source_ids=SPECIAL_SITUATION_SIGNAL_SOURCE_IDS,
        browser_source_ids=browser_source_ids,
        optional_recall_source_ids=GLOBAL_OPTIONAL_RECALL_SOURCE_IDS,
        notes=[
            "Special situations should bias toward M&A, financing, spin-off, asset-sale, and rumor/discussion routes rather than generic company news.",
            "This route is executable through the shared discovery runner and should be used when the event pool is missing a corporate-action setup.",
        ],
        entrypoint=DISCOVERY_ENTRYPOINT,
    )
    route["route_version"] = "special_situation_discovery_v1"
    return route


def build_tracking_update_discovery_route(search_terms: list[str] | None = None) -> dict[str, Any]:
    live_source_ids, browser_source_ids = source_ids_for_route("tracking_update", list(search_terms or []))
    route = _build_route(
        route_key="tracking_update",
        entity_type="mixed",
        mode="query_driven",
        search_terms=list(search_terms or []),
        live_source_ids=live_source_ids,
        signal_source_ids=TRACKING_SIGNAL_SOURCE_IDS,
        browser_source_ids=browser_source_ids,
        optional_recall_source_ids=GLOBAL_OPTIONAL_RECALL_SOURCE_IDS,
        notes=[
            "Tracking updates are broad and should use mixed market-wide feeds plus attention/heat signal surfaces instead of narrow company-only search.",
            "This route is executable through the shared discovery runner for thesis-monitoring backfills.",
        ],
        entrypoint=DISCOVERY_ENTRYPOINT,
    )
    route["route_version"] = "tracking_update_discovery_v1"
    return route


def build_entity_discovery_routes(
    entity_name: str,
    entity_type: str,
    aliases: list[str] | None = None,
    ticker: str = "",
    region: str = "",
) -> dict[str, Any]:
    clean_entity_type = str(entity_type or "").strip()
    search_terms = _dedupe_preserve_order([entity_name, *(aliases or [])])
    if clean_entity_type == "company":
        return build_company_discovery_routes(company=entity_name, aliases=aliases, ticker=ticker, region=region)
    if clean_entity_type == "industry":
        live_source_ids, browser_source_ids = source_ids_for_route("industry", search_terms, ticker=ticker, region=region)
        route = _build_route(
            route_key="industry",
            entity_type="industry",
            mode="query_driven",
            search_terms=search_terms,
            live_source_ids=live_source_ids,
            signal_source_ids=INDUSTRY_SIGNAL_SOURCE_IDS,
            browser_source_ids=browser_source_ids,
            optional_recall_source_ids=GLOBAL_OPTIONAL_RECALL_SOURCE_IDS,
            notes=[
                "Industry gaps should be backfilled by querying the standard industry/company mixed confirmation sources first, then signal feeds for discussion and attention shifts.",
                "This route is executable through the shared discovery runner and should write the matched articles back into the shared database before rebuilding events.",
            ],
            entrypoint=DISCOVERY_ENTRYPOINT,
        )
        route["route_version"] = "industry_discovery_v1"
        return route
    if clean_entity_type == "institution":
        live_source_ids, browser_source_ids = source_ids_for_route("institution", search_terms, ticker=ticker, region=region)
        route = _build_route(
            route_key="institution",
            entity_type="institution",
            mode="query_driven",
            search_terms=search_terms,
            live_source_ids=live_source_ids,
            signal_source_ids=MACRO_SIGNAL_SOURCE_IDS,
            browser_source_ids=browser_source_ids,
            optional_recall_source_ids=GLOBAL_OPTIONAL_RECALL_SOURCE_IDS,
            notes=[
                "Institution misses should fan out through macro and policy confirmation sources before falling back to broad recall APIs.",
                "This route is executable through the shared discovery runner and should write matched articles back into the shared database before rebuilding events.",
            ],
            entrypoint=DISCOVERY_ENTRYPOINT,
        )
        route["route_version"] = "institution_discovery_v1"
        return route
    return _build_route(
        route_key=clean_entity_type or "generic",
        entity_type=clean_entity_type or "generic",
        mode="source_guided",
        search_terms=search_terms,
        live_source_ids=GLOBAL_OPTIONAL_RECALL_SOURCE_IDS,
        notes=[
            "No dedicated discovery route is defined for this entity type yet; use the optional global recall APIs as a fallback.",
        ],
    )


def build_feed_discovery_contract() -> dict[str, Any]:
    return {
        "route_version": "feed_discovery_contract_v2",
        "entrypoint": DISCOVERY_ENTRYPOINT,
        "supported_entity_types": ["company", "industry", "institution", "macro_theme"],
        "supported_opportunity_buckets": [
            "macro",
            "company",
            "industry",
            "institution",
            "special_situation",
            "tracking_update",
        ],
        "active_entrypoints": [DISCOVERY_ENTRYPOINT],
        "route_catalog": {
            "company": build_company_discovery_routes(company=""),
            "macro": build_macro_discovery_route(),
            "industry": build_entity_discovery_routes(entity_name="", entity_type="industry"),
            "institution": build_entity_discovery_routes(entity_name="", entity_type="institution"),
            "special_situation": build_special_situation_discovery_route(),
            "tracking_update": build_tracking_update_discovery_route(),
        },
        "notes": [
            "Use shared feed lookup first and treat discovery as a backfill step for missing or too-thin opportunity slices.",
            "All standard routes now resolve to the shared discovery runner; downstream systems should reuse these routes instead of inventing private backfill logic.",
        ],
    }
