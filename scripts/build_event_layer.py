#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import functools
import hashlib
import json
import math
import re
import sqlite3
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = ROOT / "runtime" / "news_event.db"
SCHEMA_PATH = ROOT / "config" / "schema.sql"
ENTITY_ALIAS_PATH = ROOT / "data" / "entity_aliases_v1.csv"
INDUSTRY_TAXONOMY_PATH = ROOT / "config" / "industry_taxonomy_v1.json"
DEFAULT_WATCHLIST_REGISTRY = Path.home() / ".codex" / "state" / "investment" / "watchlist" / "watchlist_registry.csv"
SQLITE_BUSY_TIMEOUT_MS = 600000
SQLITE_BEGIN_RETRY_ATTEMPTS = 8
SQLITE_BEGIN_RETRY_SLEEP_SECONDS = 5.0

WHITESPACE_RE = re.compile(r"\s+")
CHINESE_RE = re.compile(r"[\u4e00-\u9fff]")
DATE_NUM_RE = re.compile(r"\b\d{1,4}(?:[./:-]\d{1,2})+(?:[ T]\d{1,2}:\d{2}(?::\d{2})?)?\b")
SEC_ENTITY_RE = re.compile(r"^(.+?)\s*\(\d{6,}\)\s*\((?:Filer|Issuer)\)$", re.IGNORECASE)
REUTERS_ENTITY_RE = re.compile(
    r"^([A-Z][A-Za-z0-9&\.\-,'/ ]{1,80}?)\s+"
    r"(?:to|will|works|warns|agree|agrees|seals|buys|plans|says|posts|expects|cuts|raises|beats|misses|signs|wins|faces|weighs|seeks|launches|offers)\b"
)
BRACKET_TITLE_RE = re.compile(r"^【([^】]{2,120})】")
LEADING_CHINESE_COMPANY_RE = re.compile(
    r"^([\u4e00-\u9fffA-Za-z]{2,24}(?:有限责任公司|有限公司|公司|集团|股份|控股|银行|证券|科技|能源|药业|制药|汽车|航空|物流|矿业|电子|半导体|地产|保险|电力|通信|传媒|工业|机械|材料|医药|食品|基因|医疗))"
)
QUOTED_COMPANY_RE = re.compile(r"[\"“”「」『』]([^\"“”「」『』]{2,24})[\"“”「」『』]")
LATIN_COMPANY_IN_TEXT_RE = re.compile(
    r"(?<![A-Za-z0-9])([A-Z][A-Za-z0-9&\.\-]{1,24}(?:\s+[A-Z][A-Za-z0-9&\.\-]{1,24}){0,2})(?![A-Za-z0-9])(?:股份|公司|集团|控股|银行|证券)?"
)
BRAND_DESCRIPTOR_RE = re.compile(
    r"^([A-Za-z0-9\u4e00-\u9fff]{2,16})(?:婴幼儿食品|婴儿食品商|婴儿食品|食品配送公司|配送公司|品牌零售服务商|零售服务商)",
    re.IGNORECASE,
)
ROUTINE_FILING_RE = re.compile(
    r"\b(8-k|6-k|10-k|10-q|424b2|424b3|pre 14a|def 14a|n-csrs|sc 13g|sc 13d|f-3|s-3|s-8|20-f)\b",
    re.IGNORECASE,
)

COMPANY_HINT_RE = re.compile(
    r"(公司|集团|股份|控股|银行|证券|科技|能源|药业|药业|制药|汽车|航空|物流|矿业|电子|半导体|地产|保险|电力|通信|传媒|工业|机械|材料|医药|食品|基因|医疗|BofA|Goldman|Unilever|McCormick|Lilly|Centessa)",
    re.IGNORECASE,
)
NON_COMPANY_ENTITY_RE = re.compile(
    r"(财长|央行行长|央行|大使|总干事|总统|总理|部长|司长|议长|委员会|发言人|秘书长|已故|"
    r"国防军|议会|海关总署|世界卫生组织|财务大臣|政府|外交部|证监会|国资委|会长|遗孀|董事长|董事会|行政总裁|首席执行官|CEO|CFO|指数|"
    r"能源部|安全局|金管局|台办|交易所|协会|工业会|工业协会|股东)",
    re.IGNORECASE,
)
INSTITUTION_ENTITY_RE = re.compile(
    r"(能源部|财政部|商务部|外交部|发改委|统计局|海关总署|证监会|国资委|央行|委员会|协会|工业协会|工业会|"
    r"商会|联合会|交易所|金管局|安全局|台办|政府|议会|法院|检察院|监管局|监管总局)$",
    re.IGNORECASE,
)
INSTITUTION_PREFIX_RE = re.compile(
    r"^(?:周末要闻汇总|要闻汇总|市场消息|消息面|市场快讯|简讯|快讯|财经深一度丨|财经深一度)\s*[：:丨,，-]?\s*",
    re.IGNORECASE,
)
INSTITUTION_BULLETIN_PREFIX_RE = re.compile(
    r"^(?:【)?(?:财联社)?\s*\d+月\d+(?:日)?(?:晚间)?新闻精选(?:】)?\s*\d+[、.]\s*",
    re.IGNORECASE,
)
INSTITUTION_CONTEXT_SPLIT_RE = re.compile(
    r"(官员称|发言人称|行长称|官员表示|发言人表示|表示|称|触发|部署|推进|宣布|启动|暂停|恢复|维持|加码|收紧)",
    re.IGNORECASE,
)
INSTITUTION_ROLE_SUFFIX_RE = re.compile(
    r"(官员|发言人|行长|副行长|主席|总裁|秘书长)$",
    re.IGNORECASE,
)
INSTITUTION_LEADING_PARTICLE_RE = re.compile(r"^(?:与|和|同|向|在|就)\s*")
ENTITY_ACTION_SPLIT_RE = re.compile(
    r"(并购|收购|合并|重组|要约|deal|merge|merger|acquire|acquisition|takeover|"
    r"回购|增持|减持|分红|buyback|repurchase|dividend|"
    r"融资|募资|配售|发债|定增|发行|offering|share sale|bond sale|raise|"
    r"业绩|盈利预警|业绩预告|guidance|earnings|profit|revenue|forecast|results|"
    r"中标|订单|合同|签约|合作|award|order|contract|"
    r"停产|复产|扩产|减产|增产|产能|supply|output|production|shutdown|restart|"
    r"上涨|下跌|涨|跌|上升|下降|暂停|转向|变更|获得|获批|获准|批准|核准|推出|启动|完成|"
    r"签署|印发|筹划|出售|回应|否认|澄清|发布|显示|预计|表明|称|表示)",
    re.IGNORECASE,
)
ENTITY_CONTEXT_SPLIT_RE = re.compile(
    r"((?<!基)因|由于|受|据悉|正在|将|拟|计划|高管称|表示|显示|指出|认为|称|暂停|转向|变更|获得|获批|批准|核准|批复|印发|筹划|出售|返航|冲击)",
    re.IGNORECASE,
)
GENERIC_COMPANY_FRAGMENT_RE = re.compile(
    r"^(盘后|盘前|专栏|风口研报|子公司|本公司|实控人|分析师|公司累计|公司累计算力|全球|食品价格|A股上市公司|上市公司重点|又一|批复同意|资管公司|这家公司|该公司|公司目前|公司将|公司仍|公司已|据)"
    r"|ETF"
    r"|报告显示"
    r"|高管称"
    r"|控股股东"
    r"|第二大股东",
    re.IGNORECASE,
)
CONCEPTUAL_ENTITY_FRAGMENT_RE = re.compile(
    r"(需求|格局|方案|产业|领域|应用|逻辑|赛道|主线|趋势|风口|解读|精选|盘点|路线图|图谱|机会|问题|事件|关键技术|技术研发|押注|题材|方向)",
    re.IGNORECASE,
)
REGIONAL_SECTOR_FRAGMENT_RE = re.compile(
    r"^(欧盟|中国|国际|全球|国内|美国|日本|韩国|沙特|中东).*(工业|航空|能源)$",
    re.IGNORECASE,
)
LATIN_COMPANY_NAME_RE = re.compile(
    r"^[A-Z][A-Za-z0-9&\.\-]{1,24}(?:\s+[A-Z][A-Za-z0-9&\.\-]{1,24}){0,2}$"
)
CHINESE_COMPANY_SUFFIX_RE = re.compile(
    r"(有限责任公司|有限公司|公司|集团|股份|控股|银行|证券|科技|能源|药业|制药|汽车|航空|物流|矿业|电子|半导体|地产|保险|电力|通信|传媒|工业|机械|材料|医药|食品|基因|医疗)$"
)
GENERIC_EVENT_ENTITY_FRAGMENT_RE = re.compile(
    r"(燃油|短缺|治理|新机制|输送能力|供需|系统性|恢复|会见|论坛|培训会|订单额增长|价格|涨价预期)",
    re.IGNORECASE,
)

ACTION_PATTERNS: list[tuple[str, re.Pattern[str], str]] = [
    ("deal_mna", re.compile(r"(并购|收购|合并|重组|要约|deal|merge|merger|acquire|acquisition|takeover)", re.IGNORECASE), "deal"),
    ("company_action", re.compile(r"((?<!逆)回购|增持|减持|分红|buyback|repurchase|dividend)", re.IGNORECASE), "capital_return"),
    ("financing_capital", re.compile(r"(融资|募资|配售|发债|定增|发行|offering|share sale|bond sale|raise)", re.IGNORECASE), "financing"),
    ("earnings_guidance", re.compile(r"(业绩|盈利预警|业绩预告|guidance|earnings|profit|revenue|forecast|results)", re.IGNORECASE), "earnings"),
    ("contract_order", re.compile(r"(中标|订单|合同|签约|合作|award|order|contract)", re.IGNORECASE), "order"),
    ("production_supply", re.compile(r"(停产|复产|扩产|减产|增产|产能|supply|output|production|shutdown|restart)", re.IGNORECASE), "supply"),
    ("regulation", re.compile(r"(制裁|禁令|出口限制|反垄断|监管|probe|investigation|sanction|ban|tariff)", re.IGNORECASE), "regulation"),
    ("policy", re.compile(r"(政策|方案|措施|细则|央行|降息|加息|降准|逆回购|政府|部委|fed|central bank|stimulus|tax|lpr|mlf)", re.IGNORECASE), "policy"),
    ("commodity_disruption", re.compile(r"(原油|石油|天然气|黄金|铜|煤|霍尔木兹|航运|shipping|oil|gold|gas|copper)", re.IGNORECASE), "commodity"),
    ("social_signal", re.compile(r"(传闻|据悉|爆料|rumor|polymarket|reddit|x.com|twitter)", re.IGNORECASE), "signal"),
    (
        "macro_data",
        re.compile(
            r"(consumer price index|producer price index|personal consumption expenditures|"
            r"core pce|pce price|retail sales|initial jobless claims|jobless claims|"
            r"nonfarm payrolls?|unemployment rate|jolts|fed interest rate decision|"
            r"gross domestic product|cpi|ppi|pce|非农|失业|就业|初请|零售销售|"
            r"国内生产总值|通胀|物价指数)",
            re.IGNORECASE,
        ),
        "macro_release",
    ),
    ("macro_data", re.compile(r"(cpi|ppi|非农|就业|inflation|payrolls|gdp|指数.*上涨|指数.*下跌|yield|bond yields|dollar|美元指数)", re.IGNORECASE), "macro_move"),
]

DEFAULT_INDUSTRY_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("银行", ("银行", "bank", "banks")),
    ("半导体", ("半导体", "chip", "chips", "semiconductor")),
    ("新能源车", ("新能源", "电动车", "新能源汽车", "ev", "battery")),
    ("航运", ("航运", "shipping", "oil tanker", "港口", "海运")),
    ("石油天然气", ("原油", "石油", "天然气", "oil", "gas", "lng", "产油", "opec", "opec+")),
    ("黄金有色", ("黄金", "gold", "铜", "铝", "矿", "mining")),
    ("医药", ("制药", "药业", "biopharma", "pharma", "drugmaker", "医疗")),
    ("消费食品", ("食品", "饮料", "快消", "food", "beverage")),
]

MACRO_THEMES: list[tuple[str, tuple[str, ...]]] = [
    ("美联储", ("fed", "federal reserve", "fomc", "fed interest rate", "美联储")),
    ("美元", ("美元指数", "dollar", "usd", "汇率")),
    ("通胀", ("inflation", "cpi", "ppi", "pce", "price index", "通胀", "物价指数")),
    ("美国就业", ("nonfarm", "payroll", "jobless", "claims", "unemployment", "jolts", "就业", "失业", "初请", "非农")),
    ("美国增长", ("gdp", "gross domestic product", "retail sales", "零售销售", "国内生产总值")),
    ("中东地缘", ("伊朗", "中东", "霍尔木兹", "iran", "middle east")),
    ("贸易关税", ("关税", "tariff", "贸易", "trade", "制裁", "sanction")),
    ("原油", ("原油", "石油", "oil", "brent", "wti", "opec", "opec+", "产油国")),
    ("黄金", ("黄金", "gold")),
]

MARKET_RELEVANT_RE = re.compile(
    r"(关税|制裁|税|利率|降息|加息|降准|逆回购|回购|并购|收购|订单|合同|融资|募资|中标|"
    r"停产|复产|扩产|减产|出口限制|原油|黄金|天然气|航运|银行|半导体|电池|汽车|地产|"
    r"oil|gold|gas|shipping|deal|merge|earnings|guidance|buyback|contract|order|tariff|sanction|fed|rates?)",
    re.IGNORECASE,
)

LOW_SIGNAL_PUBLIC_AFFAIRS_RE = re.compile(
    r"(假期|返程|游人|好春光|总体平稳|道路交通|安全形势|电话|通电话|会见|致信|讲话|贺信|贺电|"
    r"文旅|旅游|春光|客流|清明|节日|访叙利亚|欢度|高校|表彰|体育|奥运|观鸟经济|春日经济|"
    r"新图景|一线观察|权威数读|发送旅客|旅客\d+万人次|新质生产力)",
    re.IGNORECASE,
)

PURE_PRICE_MOVE_RE = re.compile(
    r"(涨幅扩大|跌幅扩大|日内涨|日内跌|失守|站上|现报|报\d|收于|升至每加仑|涨超|跌超|上涨\d|下跌\d|高开|低开|收涨|收跌|微涨|微跌)",
    re.IGNORECASE,
)

PROBABILITY_ONLY_RE = re.compile(r"(概率为|fedwatch|观察)", re.IGNORECASE)
CALENDAR_PREVIEW_RE = re.compile(
    r"(重点关注财经事件和经济数据|重点关注财经事件|投资日历|资本市场大事提醒|次日\d{2}:\d{2}|美国\d+月.*月率|PMI|库存|耐用品订单|通胀预期)",
    re.IGNORECASE,
)
PLATFORM_HOUSEKEEPING_RE = re.compile(
    r"(短剧|作品|违规使用|平台专项|集中治理|全面核查|治理行为|下架.*部)",
    re.IGNORECASE,
)
WIRE_ROUNDUP_RE = re.compile(
    r"(today'?s international headlines|business news\s*\||trading day seeking signals from the noise|overnight global headlines|你需要知道的隔夜全球要闻)",
    re.IGNORECASE,
)
STRATEGIC_MARKET_HOOK_RE = re.compile(
    r"(霍尔木兹|海峡|航运|油轮|石油|原油|天然气|lng|石化|炼厂|油田|气田|产量|出口|制裁|关税|pipeline|shipping|oil|gas|petrochemical|refiner)",
    re.IGNORECASE,
)
GEOPOLITICAL_ROUTINE_RE = re.compile(
    r"(死亡|遇难|受伤|伤亡|爆炸声|居民楼|住宅|废墟|救援|无人机|击落|社交媒体|发言人|代表团|称.*最强|承受苦难|发表视频声明|暂无回应)",
    re.IGNORECASE,
)
CAPITAL_MARKET_HOOK_RE = re.compile(
    r"(债券融资|发行债券|发债|募资|融资|配售|定增|offering|share sale|bond sale|capital raise)",
    re.IGNORECASE,
)
GENERIC_TEASER_RE = re.compile(r"^(这家|这只|这项|这类|这份|此类)", re.IGNORECASE)
MARKET_COMMENTARY_RE = re.compile(
    r"(机构研判|机构建议|策略展望|后市配置|进一步聚焦业绩确定性|最被低估的板块|有望在二季度继续向上|大概率已探明底部|将围绕基本面展开|逢低布局|低相关性配置|中期布局|研报表示|研报指出)",
    re.IGNORECASE,
)
INSTITUTIONAL_SURVEY_RE = re.compile(
    r"(调研路线图|机构调研|最获关注|被调研|关注度居前|路线图出炉)",
    re.IGNORECASE,
)
BULLET_TEASER_RE = re.compile(r"^(?:[①②③④⑤⑥⑦⑧⑨⑩]|\d+[、\.\s])", re.IGNORECASE)
BROKER_NOTE_RE = re.compile(
    r"(^【?.*证券[:：]|证券指出|研报表示|研报指出|券商.*研报|券商最新研报|"
    r"华泰证券|中信证券|国泰君安|海通证券|申万宏源|中金公司|高盛预计|摩根士丹利|摩根大通|瑞银|花旗|巴克莱|"
    r"Goldman|JPMorgan|Morgan Stanley|UBS|预计.*股价|预计.*三重利好)",
    re.IGNORECASE,
)
OFFICIAL_COMMENTARY_ONLY_RE = re.compile(
    r"(财务大臣.*称|部长.*称|总理.*称|主席.*称|一致认为|保持密切联系|保持联系|继续保持联系|密切联系|呼吁各方|发表网志称|"
    r"表示正在评估|称正在评估|表示需保持警惕)",
    re.IGNORECASE,
)
DIPLOMATIC_PROTOCOL_RE = re.compile(
    r"(大使|总干事|司长|部长).*(会见|签署|呼吁|表示|称)|签署.*议定书|保护平民|转运工作|人道主义",
    re.IGNORECASE,
)
ENTITY_TRIM_RE = re.compile(r"^[\s【】\[\]\(\)（）<>《》「」『』\"'`]+|[\s【】\[\]\(\)（）<>《》「」『』\"'`]+$")
CONTESTED_RE = re.compile(r"(否认|辟谣|澄清|无意|不会|未达成|未签署|rejects|denies|denied)", re.IGNORECASE)
TERMINAL_UPDATE_RE = re.compile(r"(推迟|终止|取消|完成|settled|completed|closed|delay|delayed|terminate|terminated|cancelled)", re.IGNORECASE)
STRUCTURAL_ACTION_KEYS = {"deal", "capital_return", "order", "supply", "policy", "regulation", "commodity", "financing"}
STRUCTURAL_MICRO_EVENT_TYPES = {
    "deal_mna",
    "contract_order",
    "production_supply",
    "company_action",
    "earnings_guidance",
    "financing_capital",
    "regulation",
}
OFFICIAL_SOURCE_PREFIXES = (
    "sec_",
    "cninfo_",
    "hkex_",
    "akshare_stock_notice_report",
    "gov_",
    "fred_us_macro_open_data",
)
ALIAS_CLEAN_RE = re.compile(r"[\s\-_/:\\()（）【】\[\]，。,.;；'\"`]+")
MERGE_WORD_RE = re.compile(r"[a-z0-9]+|[\u4e00-\u9fff]+", re.IGNORECASE)
MERGE_STOPWORDS = {
    "the",
    "a",
    "an",
    "and",
    "or",
    "to",
    "for",
    "of",
    "in",
    "on",
    "with",
    "by",
    "from",
    "plan",
    "plans",
    "planned",
    "planning",
    "accelerate",
    "accelerates",
    "accelerated",
    "sign",
    "signs",
    "signed",
    "company",
    "group",
    "announces",
    "announced",
    "will",
    "its",
    "签署",
    "签约",
    "公司",
    "集团",
    "公告",
    "相关",
    "store",
}
ACTION_CONTEXT_STOPWORDS = {
    "deal",
    "order",
    "contract",
    "buyback",
    "financing",
    "capacity",
    "supply",
    "regulation",
    "policy",
    "commodity",
}
CONTEXT_NORMALIZATION_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\benergy cost(s)?\b|能源成本(?:问题|过高|上升|攀升)?", re.IGNORECASE), " energycost "),
    (re.compile(r"\bnorth america\b|北美", re.IGNORECASE), " northamerica "),
    (re.compile(r"\beurope\b|欧洲", re.IGNORECASE), " europe "),
    (re.compile(r"\bchina\b|中国", re.IGNORECASE), " china "),
    (re.compile(r"\bhong kong\b|香港", re.IGNORECASE), " hongkong "),
    (re.compile(r"\bstore(s)?\b|门店|开店", re.IGNORECASE), " store "),
    (re.compile(r"\bexpansion\b|expand|expands|expanded|扩张|扩建|扩产", re.IGNORECASE), " expansion "),
    (re.compile(r"\bcontract(s)?\b|合同|中标|订单|合作协议|合作", re.IGNORECASE), " contract "),
    (re.compile(r"\bdeal(s)?\b|协议|交易|签署", re.IGNORECASE), " deal "),
    (re.compile(r"\bbuyback\b|repurchase|repurchases?|回购", re.IGNORECASE), " buyback "),
    (re.compile(r"\bfinancing\b|funding|offering|融资|募资|发债|定增", re.IGNORECASE), " financing "),
    (re.compile(r"\bcapacity\b|factory|plant|产能|工厂|基地", re.IGNORECASE), " capacity "),
    (re.compile(r"\border(s)?\b|award|订单|中标", re.IGNORECASE), " order "),
]


@dataclass
class Article:
    article_id: str
    source_id: str
    source_family: str
    title: str
    title_norm: str
    summary: str
    canonical_url: str
    published_at: str | None
    collected_at: str
    lane: str
    trust_tier: int
    coverage_scope: str | None


@dataclass(frozen=True)
class EntityAlias:
    entity_type: str
    canonical_id: str
    canonical_name: str
    alias: str
    alias_norm: str


def load_view_sql(view_name: str) -> str:
    schema_text = SCHEMA_PATH.read_text(encoding="utf-8")
    match = re.search(
        rf"CREATE VIEW IF NOT EXISTS {re.escape(view_name)} AS\s*(.*?;)",
        schema_text,
        re.DOTALL,
    )
    if not match:
        raise RuntimeError(f"missing view definition for {view_name} in {SCHEMA_PATH}")
    return f"CREATE VIEW {view_name} AS\n{match.group(1).strip()}"


def non_negative_int(value: str) -> int:
    number = int(value)
    if number < 0:
        raise argparse.ArgumentTypeError("value must be non-negative")
    return number


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build Layer 2 events and shared ranking on top of news_articles.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="SQLite database path.")
    parser.add_argument("--limit-articles", type=non_negative_int, default=0, help="Optional max recent articles to process.")
    parser.add_argument("--max-article-count", type=non_negative_int, default=0, help="Abort before writing if the selected article window is larger than this. Use 0 to disable.")
    parser.add_argument("--lookback-days", type=non_negative_int, default=30, help="Only include articles seen within this many days. Use 0 for all.")
    parser.add_argument("--window-start", default="", help="Optional inclusive event-time lower bound, ISO datetime or YYYY-MM-DD. Overrides lookback lower bound when set.")
    parser.add_argument("--window-end", default="", help="Optional exclusive event-time upper bound, ISO datetime or YYYY-MM-DD.")
    parser.add_argument("--include-source-id", action="append", default=[], help="Only include this source_id. Repeatable.")
    parser.add_argument("--exclude-source-id", action="append", default=[], help="Exclude this source_id from event building. Repeatable.")
    parser.add_argument("--as-of", default="", help="UTC timestamp used for lookback and ranking. Defaults to current time.")
    parser.add_argument("--slice-safe", action="store_true", help="Only replace article links touched by the current article window, preserving historical links for persistent events.")
    parser.add_argument("--window-granularity", default="", help="Optional snapshot granularity, e.g. day, rolling3, week, month, year.")
    parser.add_argument("--window-label", default="", help="Optional stable snapshot label for the current window.")
    parser.add_argument("--snapshot-only", action="store_true", help="Write event_window_snapshots without mutating core events or article links.")
    parser.add_argument("--no-rebuild", action="store_true", help="Do not clear existing event/link tables before writing.")
    return parser.parse_args()


def ensure_event_schema(conn: sqlite3.Connection) -> None:
    existing = {str(row[1]) for row in conn.execute("PRAGMA table_info(events)").fetchall()}
    additions = [
        ("event_state", "ALTER TABLE events ADD COLUMN event_state TEXT NOT NULL DEFAULT 'emerging'"),
        ("score_vector", "ALTER TABLE events ADD COLUMN score_vector TEXT"),
        ("calibrated_confirmation", "ALTER TABLE events ADD COLUMN calibrated_confirmation REAL"),
        ("uncertainty", "ALTER TABLE events ADD COLUMN uncertainty REAL"),
        ("article_count_raw", "ALTER TABLE events ADD COLUMN article_count_raw INTEGER NOT NULL DEFAULT 0"),
        ("independent_evidence_count", "ALTER TABLE events ADD COLUMN independent_evidence_count INTEGER NOT NULL DEFAULT 0"),
        ("source_family_count", "ALTER TABLE events ADD COLUMN source_family_count INTEGER NOT NULL DEFAULT 0"),
        ("signal_platform_count", "ALTER TABLE events ADD COLUMN signal_platform_count INTEGER NOT NULL DEFAULT 0"),
    ]
    for column, sql in additions:
        if column not in existing:
            conn.execute(sql)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_events_state ON events (event_state)")
    if {str(row[0]) for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}:
        pass
    link_existing = {str(row[1]) for row in conn.execute("PRAGMA table_info(event_entity_links)").fetchall()}
    link_additions = [
        ("mapping_reason", "ALTER TABLE event_entity_links ADD COLUMN mapping_reason TEXT"),
        ("mapping_confidence", "ALTER TABLE event_entity_links ADD COLUMN mapping_confidence REAL"),
        ("mapping_version", "ALTER TABLE event_entity_links ADD COLUMN mapping_version TEXT"),
        ("mapping_source", "ALTER TABLE event_entity_links ADD COLUMN mapping_source TEXT"),
    ]
    for column, sql in link_additions:
        if column not in link_existing:
            conn.execute(sql)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS unresolved_event_mappings (
            event_id           TEXT PRIMARY KEY REFERENCES events (event_id) ON DELETE CASCADE,
            topic_key          TEXT,
            event_title        TEXT NOT NULL,
            unresolved_reason  TEXT NOT NULL,
            mapping_version    TEXT NOT NULL DEFAULT 'mapping_layer_v1',
            detected_at        TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at         TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_unresolved_event_mappings_topic ON unresolved_event_mappings (topic_key)")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS event_window_snapshots (
            snapshot_id                  TEXT PRIMARY KEY,
            event_id                     TEXT NOT NULL,
            window_granularity          TEXT NOT NULL,
            window_label                TEXT NOT NULL,
            window_start                TEXT NOT NULL,
            window_end                  TEXT NOT NULL,
            as_of                       TEXT NOT NULL,
            event_type                  TEXT,
            event_title                 TEXT NOT NULL,
            topic_key                   TEXT,
            event_state                 TEXT,
            first_seen_at               TEXT NOT NULL,
            last_seen_at                TEXT NOT NULL,
            novelty_state               TEXT NOT NULL,
            confirmation_count          INTEGER NOT NULL DEFAULT 0,
            source_mix                  TEXT,
            score_vector                TEXT,
            calibrated_confirmation     REAL,
            uncertainty                 REAL,
            article_count_raw           INTEGER NOT NULL DEFAULT 0,
            independent_evidence_count  INTEGER NOT NULL DEFAULT 0,
            source_family_count         INTEGER NOT NULL DEFAULT 0,
            signal_platform_count       INTEGER NOT NULL DEFAULT 0,
            primary_industry            TEXT,
            primary_entity              TEXT,
            event_rank_score            REAL,
            event_rank_flags            TEXT,
            article_ids                 TEXT,
            created_at                  TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at                  TEXT NOT NULL DEFAULT (datetime('now')),
            UNIQUE(event_id, window_granularity, window_label)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_event_window_snapshots_window "
        "ON event_window_snapshots (window_granularity, window_label, event_rank_score DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_event_window_snapshots_topic "
        "ON event_window_snapshots (topic_key, window_granularity, last_seen_at DESC)"
    )
    opp_existing = {str(row[1]) for row in conn.execute("PRAGMA table_info(opportunity_signals)").fetchall()}
    opp_additions = [
        ("opportunity_type", "ALTER TABLE opportunity_signals ADD COLUMN opportunity_type TEXT"),
        ("opportunity_bucket", "ALTER TABLE opportunity_signals ADD COLUMN opportunity_bucket TEXT"),
    ]
    for column, sql in opp_additions:
        if column not in opp_existing:
            conn.execute(sql)


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def resolve_as_of(value: str | None) -> datetime:
    parsed = parse_iso(value)
    return parsed.replace(microsecond=0) if parsed else utc_now()


def resolve_window_bound(value: str | None) -> str | None:
    parsed = parse_iso(value)
    if not parsed:
        return None
    return parsed.replace(microsecond=0).isoformat(timespec="seconds")


def normalize_text(value: str | None) -> str:
    return WHITESPACE_RE.sub(" ", str(value or "").strip())


def normalize_alias_text(value: str | None) -> str:
    text = str(value or "").strip().lower()
    return ALIAS_CLEAN_RE.sub("", text)


@functools.lru_cache(maxsize=1)
def load_industry_keywords() -> tuple[tuple[str, tuple[str, ...]], ...]:
    if not INDUSTRY_TAXONOMY_PATH.exists():
        return tuple(DEFAULT_INDUSTRY_KEYWORDS)
    try:
        payload = json.loads(INDUSTRY_TAXONOMY_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return tuple(DEFAULT_INDUSTRY_KEYWORDS)
    rows: list[tuple[str, tuple[str, ...]]] = []
    for item in payload.get("industries") or []:
        label = normalize_text(item.get("label"))
        terms = tuple(
            normalize_text(term)
            for term in (item.get("terms") or [])
            if normalize_text(term)
        )
        if not label or not terms:
            continue
        rows.append((label, terms))
    return tuple(rows or DEFAULT_INDUSTRY_KEYWORDS)


INDUSTRY_KEYWORDS = load_industry_keywords()


def slugify(value: str) -> str:
    clean = normalize_text(value).lower()
    ascii_clean = re.sub(r"[^a-z0-9]+", "-", clean).strip("-")
    if ascii_clean:
        if len(ascii_clean) <= 80:
            return ascii_clean
        digest = hashlib.sha1(clean.encode("utf-8")).hexdigest()[:12]
        return f"{ascii_clean[:64]}-{digest}"
    digest = hashlib.sha1(clean.encode("utf-8")).hexdigest()[:12]
    return f"zh-{digest}"


def parse_iso(value: str | None) -> datetime | None:
    clean = str(value or "").strip()
    if not clean:
        return None
    try:
        parsed = datetime.fromisoformat(clean.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def article_timestamp(article: Article) -> datetime:
    return parse_iso(article.published_at) or parse_iso(article.collected_at) or utc_now()


def resolve_window_metadata(args: argparse.Namespace, now: datetime, window_start: str | None, window_end: str | None) -> dict[str, str] | None:
    granularity = normalize_text(args.window_granularity)
    label = normalize_text(args.window_label)
    if not granularity and not label and not args.snapshot_only:
        return None
    if not granularity:
        raise SystemExit("--window-granularity is required when writing window snapshots")
    if not label:
        raise SystemExit("--window-label is required when writing window snapshots")
    start = window_start
    if not start and args.lookback_days > 0:
        start = (now.astimezone(timezone.utc) - timedelta(days=int(args.lookback_days))).isoformat(timespec="seconds")
    end = window_end or now.astimezone(timezone.utc).isoformat(timespec="seconds")
    if not start:
        raise SystemExit("--window-start is required for all-history window snapshots")
    return {
        "granularity": granularity,
        "label": label,
        "start": start,
        "end": end,
        "as_of": now.astimezone(timezone.utc).isoformat(timespec="seconds"),
    }


def article_title_clean(article: Article) -> str:
    title = normalize_text(article.title)
    title = re.sub(r"^财联社\d+月\d+日电，?", "", title)
    return title


def infer_event_type(text: str, article: Article) -> tuple[str, str]:
    summary = normalize_text(article.summary).lower()
    combo = f"{text.lower()} {summary} {article.source_id.lower()}"
    if CALENDAR_PREVIEW_RE.search(combo):
        return "macro_data", "calendar_preview"
    if article.source_id in {"sec_8k_current", "sec_6k_current"} and SEC_ENTITY_RE.match(text):
        return "company_action", "routine_filing"
    if ROUTINE_FILING_RE.search(combo):
        return "company_action", "routine_filing"
    if article.source_id == "fred_us_macro_open_data":
        return "macro_data", "macro_release"
    for event_type, pattern, action_key in ACTION_PATTERNS:
        if pattern.search(combo):
            return event_type, action_key
    if article.lane == "signal":
        return "social_signal", "signal"
    return "company_action" if article.coverage_scope == "company" else "macro_data", "general_update"


def extract_primary_entity(text: str, article: Article) -> str | None:
    alias_match = find_entity_alias(text)
    if alias_match:
        return alias_match[0]

    match = SEC_ENTITY_RE.match(text)
    if match:
        candidate = canonicalize_entity_name(trim_company_candidate(match.group(1)))
        if candidate and looks_like_company_entity(candidate):
            return candidate

    lead_match = LEADING_CHINESE_COMPANY_RE.match(text)
    if lead_match:
        trailing_text = text[lead_match.end():]
        if trailing_text.startswith(("商", "生产商", "制造商", "配送商")):
            lead_match = None
    if lead_match:
        candidate = canonicalize_entity_name(trim_company_candidate(lead_match.group(1)))
        if candidate and looks_like_company_entity(candidate):
            return candidate

    if "：" in text:
        left = canonicalize_entity_name(trim_company_candidate(text.split("：", 1)[0]))
        if left and 1 < len(left) <= 24 and looks_like_company_entity(left):
            return left

    rmatch = REUTERS_ENTITY_RE.match(text)
    if rmatch:
        candidate = canonicalize_entity_name(trim_company_candidate(rmatch.group(1)))
        if candidate and looks_like_company_entity(candidate):
            return candidate

    for quote_match in QUOTED_COMPANY_RE.finditer(text):
        candidate = canonicalize_entity_name(trim_company_candidate(quote_match.group(1)))
        if candidate and (
            looks_like_company_entity(candidate)
            or (
                CHINESE_RE.search(candidate)
                and 2 <= len(candidate) <= 8
                and NON_COMPANY_ENTITY_RE.search(candidate) is None
                and CONCEPTUAL_ENTITY_FRAGMENT_RE.search(candidate) is None
            )
        ):
            return candidate

    brand_match = BRAND_DESCRIPTOR_RE.match(text)
    if brand_match:
        candidate = canonicalize_entity_name(trim_company_candidate(brand_match.group(1)))
        if candidate and looks_like_company_entity(candidate):
            return candidate

    bmatch = BRACKET_TITLE_RE.match(text)
    if bmatch:
        candidate = canonicalize_entity_name(trim_company_candidate(bmatch.group(1)))
        if candidate and looks_like_company_entity(candidate):
            return candidate

    latin_candidates = sorted(
        {match.group(1) for match in LATIN_COMPANY_IN_TEXT_RE.finditer(text)},
        key=len,
        reverse=True,
    )
    for raw_candidate in latin_candidates:
        candidate = canonicalize_entity_name(trim_company_candidate(raw_candidate))
        if candidate and looks_like_company_entity(candidate):
            return candidate

    if COMPANY_HINT_RE.search(text):
        pieces = re.split(r"[，,:： ]+", text)
        for piece in pieces[:3]:
            piece = canonicalize_entity_name(trim_company_candidate(piece))
            if piece and 1 < len(piece) <= 30 and looks_like_company_entity(piece):
                return piece
    return None


def extract_institution_entity(text: str) -> str | None:
    candidates: list[str] = []
    clean_text = clean_entity_candidate(text)
    if "：" in clean_text:
        left, right = clean_text.split("：", 1)
        candidates.extend([left, right])
    if ":" in clean_text:
        left, right = clean_text.split(":", 1)
        candidates.extend([left, right])
    candidates.extend(re.split(r"[，,丨|]", clean_text))
    candidates.append(clean_text)
    seen: set[str] = set()
    for raw_candidate in candidates:
        candidate = clean_entity_candidate(raw_candidate)
        candidate = INSTITUTION_PREFIX_RE.sub("", candidate)
        candidate = INSTITUTION_BULLETIN_PREFIX_RE.sub("", candidate)
        candidate = INSTITUTION_LEADING_PARTICLE_RE.sub("", candidate)
        context_parts = INSTITUTION_CONTEXT_SPLIT_RE.split(candidate, maxsplit=1)
        candidate = clean_entity_candidate(context_parts[0] if context_parts else candidate)
        candidate = INSTITUTION_ROLE_SUFFIX_RE.sub("", candidate)
        candidate = trim_company_candidate(candidate)
        candidate = clean_entity_candidate(candidate)
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        if looks_like_company_entity(candidate):
            continue
        if not INSTITUTION_ENTITY_RE.search(candidate):
            continue
        if len(candidate) > 32:
            continue
        return candidate
    return None


def keyword_match(text: str, table: list[tuple[str, tuple[str, ...]]]) -> str | None:
    lowered = text.lower()
    for label, terms in table:
        if any(term.lower() in lowered for term in terms):
            return label
    return None


def build_title_skeleton(text: str) -> str:
    clean = normalize_text(text).lower()
    clean = DATE_NUM_RE.sub(" ", clean)
    clean = re.sub(r"(财联社\d+月\d+日电|财联社|路透社|reuters|federal reserve|state council important news)", " ", clean, flags=re.IGNORECASE)
    clean = re.sub(r"[^\w\u4e00-\u9fff]+", " ", clean)
    clean = WHITESPACE_RE.sub(" ", clean).strip()
    return clean[:120]


def build_entity_context_signature(text: str, primary_entity: str | None, action_key: str) -> str:
    clean = normalize_text(text).lower()
    clean = DATE_NUM_RE.sub(" ", clean)
    clean = re.sub(r"(财联社\d+月\d+日电|财联社|路透社|reuters)", " ", clean, flags=re.IGNORECASE)
    for alias in alias_variants_for_company(primary_entity):
        alias_clean = normalize_text(alias).strip()
        if not alias_clean:
            continue
        clean = re.sub(re.escape(alias_clean.lower()), " ", clean, flags=re.IGNORECASE)
    for pattern, replacement in CONTEXT_NORMALIZATION_RULES:
        clean = pattern.sub(replacement, clean)
    clean = re.sub(r"[^\w\u4e00-\u9fff]+", " ", clean)
    tokens: list[str] = []
    seen: set[str] = set()
    for token in MERGE_WORD_RE.findall(clean):
        normalized = str(token or "").strip().lower()
        if not normalized:
            continue
        if normalized in MERGE_STOPWORDS:
            continue
        if normalized in ACTION_CONTEXT_STOPWORDS:
            continue
        if len(normalized) <= 1 and not normalized.isdigit():
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        tokens.append(normalized)
    if not tokens:
        return ""
    if action_key == "general_update":
        tokens = sorted(tokens)
        return "-".join(tokens[:6])
    return "-".join(tokens[:4])


def build_update_signature(
    text: str,
    primary_entity: str | None,
    primary_industry: str | None,
    macro_theme: str | None,
    action_key: str,
) -> str:
    clean = normalize_text(text).lower()
    clean = DATE_NUM_RE.sub(" ", clean)
    clean = re.sub(r"(财联社\d+月\d+日电|财联社|路透社|reuters)", " ", clean, flags=re.IGNORECASE)
    for alias in alias_variants_for_company(primary_entity):
        alias_clean = normalize_text(alias).strip()
        if alias_clean:
            clean = re.sub(re.escape(alias_clean.lower()), " ", clean, flags=re.IGNORECASE)
    for label in (primary_industry, macro_theme):
        label_clean = normalize_text(label).strip().lower()
        if label_clean:
            clean = re.sub(re.escape(label_clean), " ", clean, flags=re.IGNORECASE)
    for pattern, replacement in CONTEXT_NORMALIZATION_RULES:
        clean = pattern.sub(replacement, clean)
    clean = re.sub(r"[^\w\u4e00-\u9fff]+", " ", clean)
    tokens: list[str] = []
    seen: set[str] = set()
    for token in MERGE_WORD_RE.findall(clean):
        normalized = str(token or "").strip().lower()
        if not normalized:
            continue
        if normalized in MERGE_STOPWORDS:
            continue
        if len(normalized) <= 1 and not normalized.isdigit():
            continue
        if action_key in ACTION_CONTEXT_STOPWORDS and normalized == action_key:
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        tokens.append(normalized)
    if not tokens:
        return build_title_skeleton(text)[:80]
    return "-".join(tokens[:6])


def collect_event_updates(
    articles: list[Article],
    primary_entity: str | None,
    primary_industry: str | None,
    macro_theme: str | None,
    action_key: str,
) -> list[dict[str, str]]:
    ranked_articles = sorted(
        articles,
        key=lambda article: article_timestamp(article),
        reverse=True,
    )
    updates: list[dict[str, str]] = []
    seen: set[str] = set()
    for article in ranked_articles:
        title = article_title_clean(article)
        signature = build_update_signature(title, primary_entity, primary_industry, macro_theme, action_key)
        if not signature or signature in seen:
            continue
        seen.add(signature)
        updates.append(
            {
                "update_signature": signature,
                "title": title[:200],
                "published_at": article.published_at or article.collected_at,
                "source_id": article.source_id,
            }
        )
    return updates


def clean_entity_candidate(value: str | None) -> str:
    clean = normalize_text(value)
    clean = ENTITY_TRIM_RE.sub("", clean)
    clean = re.sub(r"^(?:财联社\d+月\d+日电|财联社|路透社|reuters)\s*[：:,-]?\s*", "", clean, flags=re.IGNORECASE)
    clean = ENTITY_TRIM_RE.sub("", clean)
    return clean[:80]


def normalize_company_name(value: str | None) -> str:
    clean = normalize_text(value)
    clean = re.sub(r"\b(?:inc|corp|corporation|co|company|holdings|holding|group|limited|ltd|plc)\b\.?", " ", clean, flags=re.IGNORECASE)
    clean = re.sub(r"\s+", " ", clean).strip(" -_,")
    return clean[:80]


@functools.lru_cache(maxsize=1)
def load_entity_aliases() -> tuple[list[EntityAlias], dict[str, tuple[str, str]]]:
    aliases: list[EntityAlias] = []
    alias_lookup: dict[str, tuple[str, str]] = {}
    seen_rows: set[tuple[str, str, str, str]] = set()

    def add_alias(entity_type: str, canonical_id: str, canonical_name: str, alias: str) -> None:
        clean_alias = clean_entity_candidate(alias)
        alias_norm = normalize_alias_text(clean_alias)
        if not clean_alias or not alias_norm:
            return
        if not CHINESE_RE.search(clean_alias):
            has_digit = any(ch.isdigit() for ch in alias_norm)
            if not has_digit and len(alias_norm) < 4:
                return
        row_key = (entity_type, canonical_id, canonical_name, alias_norm)
        if row_key in seen_rows:
            return
        seen_rows.add(row_key)
        aliases.append(
            EntityAlias(
                entity_type=entity_type,
                canonical_id=canonical_id,
                canonical_name=canonical_name,
                alias=clean_alias,
                alias_norm=alias_norm,
            )
        )
        alias_lookup.setdefault(alias_norm, (canonical_name, canonical_id))

    if ENTITY_ALIAS_PATH.exists():
        with ENTITY_ALIAS_PATH.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                entity_type = str(row.get("entity_type") or "company").strip() or "company"
                canonical_id = str(row.get("canonical_id") or "").strip()
                canonical_name = clean_entity_candidate(row.get("canonical_name"))
                alias = str(row.get("alias") or "").strip()
                if not canonical_id or not canonical_name or not alias:
                    continue
                add_alias(entity_type, canonical_id, canonical_name, canonical_name)
                add_alias(entity_type, canonical_id, canonical_name, alias)

    if DEFAULT_WATCHLIST_REGISTRY.exists():
        with DEFAULT_WATCHLIST_REGISTRY.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                status = str(row.get("status") or "active").strip().lower()
                if status and status not in {"active", "holding", "watch", "tracked"}:
                    continue
                name = normalize_company_name(row.get("name"))
                ticker = str(row.get("ticker") or "").strip().upper()
                if not name:
                    continue
                canonical_id = slugify(name)
                add_alias("company", canonical_id, name, name)
                if ticker:
                    add_alias("company", canonical_id, name, ticker)
                    code = ticker.split(".", 1)[0]
                    if code:
                        add_alias("company", canonical_id, name, code)

    aliases.sort(key=lambda item: (len(item.alias_norm), len(item.alias), item.alias), reverse=True)
    return aliases, alias_lookup


def find_entity_alias(text: str) -> tuple[str, str] | None:
    raw_text = normalize_text(text)
    norm_text = normalize_alias_text(raw_text)
    if not raw_text or not norm_text:
        return None
    aliases, _ = load_entity_aliases()
    for alias in aliases:
        if CHINESE_RE.search(alias.alias) or any(ch.isdigit() for ch in alias.alias_norm):
            if alias.alias_norm in norm_text:
                return alias.canonical_name, alias.canonical_id
            continue
        boundary = re.compile(rf"(?<![A-Za-z0-9]){re.escape(alias.alias)}(?![A-Za-z0-9])", re.IGNORECASE)
        if boundary.search(raw_text):
            return alias.canonical_name, alias.canonical_id
    return None


def canonicalize_entity_name(value: str | None) -> str | None:
    clean = clean_entity_candidate(value)
    if not clean:
        return None
    alias_match = find_entity_alias(clean)
    if alias_match:
        return alias_match[0]
    return clean


def trim_company_candidate(value: str | None) -> str:
    clean = clean_entity_candidate(value)
    if not clean:
        return ""
    parts = ENTITY_ACTION_SPLIT_RE.split(clean, maxsplit=1)
    head = clean_entity_candidate(parts[0] if parts else clean)
    if head:
        context_parts = ENTITY_CONTEXT_SPLIT_RE.split(head, maxsplit=1)
        head = clean_entity_candidate(context_parts[0] if context_parts else head)
    if head and head != clean:
        return head
    return clean


def looks_like_company_entity(candidate: str | None) -> bool:
    clean = clean_entity_candidate(candidate)
    if not clean:
        return False
    alias_match = find_entity_alias(clean)
    if alias_match is None and CHINESE_RE.search(clean) is None and len(normalize_alias_text(clean)) < 4:
        return False
    if NON_COMPANY_ENTITY_RE.search(clean):
        return False
    if GENERIC_COMPANY_FRAGMENT_RE.search(clean):
        return False
    if REGIONAL_SECTOR_FRAGMENT_RE.search(clean) and alias_match is None:
        return False
    if GENERIC_EVENT_ENTITY_FRAGMENT_RE.search(clean) and alias_match is None and CHINESE_COMPANY_SUFFIX_RE.search(clean) is None:
        return False
    if CONCEPTUAL_ENTITY_FRAGMENT_RE.search(clean) and alias_match is None:
        return False
    if "%" in clean:
        return False
    if len(clean) > 32:
        return False
    if "、" in clean and find_entity_alias(clean) is None:
        return False
    if any(token in clean for token in ("亿元", "万股", "美元", "港元", "亿元", "月率")):
        return False
    if any(ch.isdigit() for ch in clean) and normalize_alias_text(clean) not in {alias.alias_norm for alias in load_entity_aliases()[0]}:
        return False
    if COMPANY_HINT_RE.search(clean) is not None or alias_match is not None:
        return True
    return LATIN_COMPANY_NAME_RE.match(clean) is not None


def canonical_company_id(primary_entity: str | None) -> str | None:
    if not primary_entity:
        return None
    _, alias_lookup = load_entity_aliases()
    alias_norm = normalize_alias_text(primary_entity)
    mapped = alias_lookup.get(alias_norm)
    if mapped:
        return mapped[1]
    return slugify(primary_entity)


@functools.lru_cache(maxsize=256)
def alias_variants_for_company(primary_entity: str | None) -> tuple[str, ...]:
    canonical_id = canonical_company_id(primary_entity)
    canonical_name = canonicalize_entity_name(primary_entity)
    if not canonical_id and not canonical_name:
        return tuple()
    aliases, _ = load_entity_aliases()
    rows = {
        alias.alias
        for alias in aliases
        if alias.entity_type == "company"
        and (
            (canonical_id and alias.canonical_id == canonical_id)
            or (canonical_name and alias.canonical_name == canonical_name)
        )
    }
    if canonical_name:
        rows.add(canonical_name)
    return tuple(sorted(rows, key=len, reverse=True))


def headline_focus_text(text: str) -> str:
    clean = normalize_text(text)
    if not clean:
        return ""
    clean = re.split(r"(?:财联社\d+月\d+日电，?|财联社|路透社|reuters)", clean, maxsplit=1, flags=re.IGNORECASE)[0]
    clean = re.split(r"[\n。！？!?]", clean, maxsplit=1)[0]
    clean = normalize_text(clean)
    return clean[:140]


def merge_bucket(ts: datetime, event_type: str, action_key: str, source_id: str) -> str:
    if source_id == "cls_telegraph_html" or action_key in {"macro_move", "commodity"}:
        return ts.strftime("%Y-%m-%dT%H")
    return ts.strftime("%Y-%m-%d")


def merge_key(article: Article, text: str, event_type: str, action_key: str, primary_entity: str | None, primary_industry: str | None, macro_theme: str | None) -> str:
    title_signature = build_title_skeleton(text)
    if primary_entity:
        company_id = canonical_company_id(primary_entity) or slugify(primary_entity)
        context_signature = build_entity_context_signature(text, primary_entity, action_key)
        if action_key == "general_update" and not context_signature:
            ts = article_timestamp(article)
            bucket = merge_bucket(ts, event_type, action_key, article.source_id)
            return f"entity|{company_id}|{event_type}|{action_key}|{title_signature}|{bucket}"
        signature = context_signature or title_signature
        return f"entity|{company_id}|{event_type}|{action_key}|{signature}"
    if primary_industry:
        if action_key == "general_update":
            ts = article_timestamp(article)
            bucket = merge_bucket(ts, event_type, action_key, article.source_id)
            return f"industry|{slugify(primary_industry)}|{event_type}|{action_key}|{title_signature}|{bucket}"
        return f"industry|{slugify(primary_industry)}|{event_type}|{action_key}|{title_signature}"
    if macro_theme:
        return f"macro|{slugify(macro_theme)}|{event_type}|{action_key}|{title_signature}"
    ts = article_timestamp(article)
    bucket = merge_bucket(ts, event_type, action_key, article.source_id)
    return f"title|{event_type}|{title_signature}|{bucket}"


def topic_key_for(event_type: str, primary_entity: str | None, primary_industry: str | None, macro_theme: str | None) -> str:
    if primary_entity:
        return f"company:{canonical_company_id(primary_entity) or slugify(primary_entity)}"
    if primary_industry:
        return f"industry:{slugify(primary_industry)}"
    if macro_theme:
        return f"macro:{slugify(macro_theme)}"
    return f"event_type:{slugify(event_type or 'general')}"


def choose_representative(articles: list[Article]) -> Article:
    def score(article: Article) -> tuple[int, int, int, int]:
        title = article_title_clean(article)
        return (
            1 if article.lane == "confirmation" else 0,
            -int(article.trust_tier),
            1 if ROUTINE_FILING_RE.search(f"{title} {article.summary}") is None else 0,
            -len(title),
        )
    return sorted(articles, key=score, reverse=True)[0]


def build_source_mix(articles: list[Article]) -> dict[str, int]:
    per_lane: dict[str, set[str]] = defaultdict(set)
    for article in articles:
        per_lane[article.lane].add(article.source_id)
    return {lane: len(source_ids) for lane, source_ids in per_lane.items()}


def source_family_id(article: Article) -> str:
    if article.source_family:
        return article.source_family
    host = ""
    if article.canonical_url:
        try:
            host = urlparse(article.canonical_url).netloc.lower().strip()
        except ValueError:
            host = ""
    if host.startswith("www."):
        host = host[4:]
    if host:
        if "reuters.com" in host:
            return "host:reuters"
        if "prnewswire.com" in host:
            return "host:prnewswire"
        if "globenewswire.com" in host:
            return "host:globenewswire"
        if "reddit.com" in host:
            return "host:reddit"
        if "xueqiu.com" in host:
            return "host:xueqiu"
        if "xiaohongshu.com" in host:
            return "host:xiaohongshu"
        if "weibo.com" in host or "weibo.cn" in host:
            return "host:weibo"
        if "v2ex.com" in host:
            return "host:v2ex"
        if "cls.cn" in host:
            return "host:cls"
        if "cninfo.com.cn" in host:
            return "host:cninfo"
        if "hkexnews.hk" in host or "hkex.com.hk" in host:
            return "host:hkex"
    source_id = article.source_id.lower()
    for prefix in (
        "prnewswire_",
        "globenewswire_",
        "reddit_",
        "xueqiu_",
        "xiaohongshu_",
        "weibo_",
        "v2ex_",
        "cninfo_",
        "hkex_",
        "company_",
        "macro_",
    ):
        if source_id.startswith(prefix):
            return f"source_prefix:{prefix.rstrip('_')}"
    return f"source:{source_id}"


def build_evidence_counters(articles: list[Article]) -> dict[str, int]:
    families_by_lane: dict[str, set[str]] = defaultdict(set)
    for article in articles:
        families_by_lane[article.lane].add(source_family_id(article))
    confirmation_families = families_by_lane.get("confirmation", set())
    signal_families = families_by_lane.get("signal", set())
    return {
        "article_count_raw": len(articles),
        "independent_evidence_count": len(confirmation_families) + len(signal_families),
        "independent_confirmation_count": len(confirmation_families),
        "source_family_count": len(confirmation_families | signal_families),
        "signal_platform_count": len(signal_families),
    }


def has_official_source(articles: list[Article]) -> bool:
    return any(article.source_id.startswith(OFFICIAL_SOURCE_PREFIXES) for article in articles)


def coverage_expected_baseline(event_type: str, primary_entity: str | None, primary_industry: str | None, macro_theme: str | None) -> float:
    baseline = 1.0
    if macro_theme:
        baseline += 1.5
    elif primary_industry:
        baseline += 0.5
    elif not primary_entity:
        baseline += 0.25
    if event_type in {"policy", "regulation", "macro_data", "commodity_disruption"}:
        baseline += 1.0
    return baseline


def derive_event_state(
    novelty: str,
    confirmation_count: int,
    signal_count: int,
    official_source_present: bool,
    structural_event: bool,
    high_local_impact: bool,
    calibrated_confirmation: float,
    uncertainty: float,
    text: str,
) -> tuple[str, str]:
    if CONTESTED_RE.search(text):
        return "contested", "contradiction_or_denial"
    if novelty == "stale":
        return "mature", "stale_event"
    if novelty == "closed":
        return ("mature", "terminal_update") if confirmation_count > 0 or official_source_present else ("watch", "closed_signal_only")
    if confirmation_count >= 2 or (confirmation_count >= 1 and official_source_present):
        return "confirmed", "confirmed_by_independent_facts"
    if calibrated_confirmation >= 0.68 and uncertainty <= 0.45 and confirmation_count >= 1:
        return "confirmed", "high_confidence_fact"
    if confirmation_count >= 1:
        return "emerging", "single_confirmation_pending_breadth"
    if signal_count >= 2:
        return "emerging", "multi_signal_resonance"
    if signal_count >= 1 and (structural_event or high_local_impact or uncertainty <= 0.7):
        return "emerging", "high_value_signal"
    if signal_count >= 1:
        return "watch", "single_signal_only"
    return "emerging", "default_nonempty_event"


def freshness_score(last_seen: datetime, now: datetime) -> float:
    age_hours = max((now - last_seen).total_seconds() / 3600.0, 0.0)
    if age_hours <= 6:
        return 1.0
    if age_hours <= 24:
        return 0.85
    if age_hours <= 72:
        return 0.55
    if age_hours <= 168:
        return 0.25
    return 0.05


def specificity_score(title: str, summary: str, primary_entity: str | None, action_key: str) -> float:
    score = 0.25
    if primary_entity:
        score += 0.25
    if re.search(r"\d", title) or re.search(r"\d", summary):
        score += 0.2
    if action_key not in {"general_update", "macro_move"}:
        score += 0.2
    if len(title) >= 18:
        score += 0.1
    return min(score, 1.0)


def entity_relevance_score(primary_entity: str | None, primary_industry: str | None, macro_theme: str | None) -> float:
    if primary_entity:
        return 1.0
    if primary_industry:
        return 0.8
    if macro_theme:
        return 0.55
    return 0.15


def researchability_score(event_type: str, action_key: str) -> float:
    if action_key in {"deal", "capital_return", "order", "supply", "policy", "regulation", "commodity"}:
        return 0.85
    if action_key == "calendar_preview":
        return 0.05
    if event_type in {"earnings_guidance", "deal_mna", "policy", "regulation", "contract_order"}:
        return 0.8
    if action_key == "macro_release":
        return 0.45
    if action_key == "macro_move":
        return 0.15
    if action_key == "routine_filing":
        return 0.1
    return 0.2 if action_key == "general_update" else 0.35


def novelty_state(first_seen: datetime, last_seen: datetime, article_count: int, confirmation_count: int, now: datetime, text: str) -> str:
    age_hours = max((now - last_seen).total_seconds() / 3600.0, 0.0)
    if TERMINAL_UPDATE_RE.search(text):
        return "closed" if age_hours > 24 else "developing"
    if age_hours <= 24 and article_count == 1 and confirmation_count <= 1:
        return "new"
    if age_hours <= 72:
        return "developing"
    if age_hours <= 168:
        return "stale"
    return "closed"


def compute_rank(articles: list[Article], event_type: str, action_key: str, primary_entity: str | None, primary_industry: str | None, macro_theme: str | None, now: datetime) -> tuple[float, dict[str, Any]]:
    rep = choose_representative(articles)
    rep_title = article_title_clean(rep)
    focus_title = headline_focus_text(rep_title)
    rep_summary = normalize_text(rep.summary)
    times = [article_timestamp(article) for article in articles]
    first_seen = min(times)
    last_seen = max(times)
    source_mix = build_source_mix(articles)
    counters = build_evidence_counters(articles)
    confirmation_count = counters["independent_confirmation_count"]
    signal_count = source_mix.get("signal", 0)
    official_source_present = has_official_source(articles)

    features = {
        "freshness": freshness_score(last_seen, now),
        "delta_strength": min(1.0, 0.10 + 0.15 * (len(articles) > 1) + 0.2 * (confirmation_count > 1) + 0.2 * (signal_count > 0 and confirmation_count > 0)),
        "confirmation_strength": min(1.0, 0.18 * confirmation_count + 0.06 * signal_count),
        "lane_mix": 1.0 if confirmation_count > 0 and signal_count > 0 else (0.8 if confirmation_count > 0 else 0.45),
        "specificity": specificity_score(rep_title, rep_summary, primary_entity, action_key),
        "entity_relevance": entity_relevance_score(primary_entity, primary_industry, macro_theme),
        "researchability": researchability_score(event_type, action_key),
    }
    features["investability_hint"] = min(1.0, 0.45 * features["entity_relevance"] + 0.55 * features["researchability"])
    market_significance = min(
        1.0,
        0.45 * features["specificity"]
        + 0.25 * features["confirmation_strength"]
        + 0.20 * features["researchability"]
        + 0.10 * (1.0 if macro_theme else 0.35 if primary_industry else 0.15),
    )
    entity_impact = min(
        1.0,
        0.45 * features["entity_relevance"]
        + 0.30 * features["specificity"]
        + 0.25 * features["researchability"],
    )
    entity_local_priority = min(
        1.0,
        0.55 * entity_impact
        + 0.20 * features["specificity"]
        + 0.15 * features["freshness"]
        + 0.10 * (1.0 if primary_entity else 0.35 if primary_industry else 0.0),
    )
    coverage_independent = min(1.0, math.log1p(max(counters["independent_evidence_count"], 0)) / math.log(5.0))
    expected_coverage = coverage_expected_baseline(event_type, primary_entity, primary_industry, macro_theme)
    coverage_residual = min(1.0, max(counters["independent_evidence_count"] - expected_coverage, 0.0) / 3.0)
    calibrated_confirmation = min(
        1.0,
        0.55 * features["confirmation_strength"]
        + 0.25 * (1.0 if official_source_present else 0.0)
        + 0.20 * min(1.0, confirmation_count / 3.0),
    )
    uncertainty = min(
        1.0,
        max(
            0.0,
            0.85
            - 0.55 * calibrated_confirmation
            - 0.10 * (1.0 if official_source_present else 0.0)
            + (0.15 if signal_count > 0 and confirmation_count == 0 else 0.0),
        ),
    )
    score_vector = {
        "market_significance": round(market_significance, 4),
        "entity_impact": round(entity_impact, 4),
        "entity_local_priority": round(entity_local_priority, 4),
        "confirmation": round(calibrated_confirmation, 4),
        "novelty": round(features["freshness"], 4),
        "researchability": round(features["researchability"], 4),
        "coverage_independent": round(coverage_independent, 4),
        "coverage_residual": round(coverage_residual, 4),
        "urgency": round(max(features["freshness"], 0.6 * features["delta_strength"]), 4),
        "uncertainty": round(uncertainty, 4),
    }

    is_public_affairs = LOW_SIGNAL_PUBLIC_AFFAIRS_RE.search(focus_title) is not None
    is_pure_price_move = PURE_PRICE_MOVE_RE.search(focus_title) is not None and re.search(r"(因|由于|because|after|amid)", focus_title, re.IGNORECASE) is None
    is_probability_only = PROBABILITY_ONLY_RE.search(focus_title) is not None
    is_calendar_preview = action_key == "calendar_preview" or CALENDAR_PREVIEW_RE.search(focus_title) is not None
    is_unmapped_signal = action_key == "signal" and not primary_entity and not primary_industry and not macro_theme
    is_platform_housekeeping = PLATFORM_HOUSEKEEPING_RE.search(focus_title) is not None
    is_generic_macro_move = action_key == "macro_move" and primary_entity is None and primary_industry is None
    is_wire_roundup = WIRE_ROUNDUP_RE.search(focus_title) is not None
    is_routine_geopolitics = (
        macro_theme == "中东地缘"
        and action_key in {"general_update", "policy"}
        and primary_entity is None
        and primary_industry is None
        and STRATEGIC_MARKET_HOOK_RE.search(focus_title) is None
    )
    is_casualty_or_rhetoric_update = is_routine_geopolitics and GEOPOLITICAL_ROUTINE_RE.search(focus_title) is not None
    is_weak_financing_macro = (
        event_type == "financing_capital"
        and primary_entity is None
        and primary_industry is None
        and CAPITAL_MARKET_HOOK_RE.search(focus_title) is None
    )
    is_generic_teaser = GENERIC_TEASER_RE.search(focus_title) is not None
    is_market_commentary = MARKET_COMMENTARY_RE.search(focus_title) is not None
    is_institutional_survey = INSTITUTIONAL_SURVEY_RE.search(focus_title) is not None
    is_bullet_teaser = BULLET_TEASER_RE.search(focus_title) is not None
    is_broker_note = BROKER_NOTE_RE.search(focus_title) is not None
    has_concrete_market_action = re.search(
        r"(宣布|上调|下调|制裁|批准|征收|开放|关闭|通过|签署协议|达成协议|增产|减产|"
        r"空袭|袭击|收购|回购|订单|合同|发债|募资|融资|供给|出口限制)",
        focus_title,
        re.IGNORECASE,
    ) is not None
    is_official_commentary_only = (
        OFFICIAL_COMMENTARY_ONLY_RE.search(focus_title) is not None
        and primary_entity is None
        and not has_concrete_market_action
    )
    is_diplomatic_protocol = (
        DIPLOMATIC_PROTOCOL_RE.search(focus_title) is not None
        and primary_entity is None
        and CAPITAL_MARKET_HOOK_RE.search(focus_title) is None
    )

    penalties = {
        "background_penalty": 0.35 if re.search(r"(背景|回顾|缘由|what is|explainer|how to)", rep_title, re.IGNORECASE) else 0.0,
        "stale_penalty": 0.5 if features["freshness"] <= 0.25 else (0.2 if features["freshness"] <= 0.55 else 0.0),
        "weak_mapping_penalty": 0.55 if features["entity_relevance"] < 0.3 else (0.2 if features["entity_relevance"] < 0.6 else 0.0),
        "late_recap_penalty": 0.25 if re.search(r"(周回顾|日报|收评|午评|Trading Day|attempt a rebound|weekly recap|market wrap|morning brief|opening bell)", rep_title, re.IGNORECASE) else 0.0,
        "single_dirty_source_penalty": 0.5 if confirmation_count == 0 and signal_count <= 1 else 0.0,
        "routine_filing_penalty": 0.7 if action_key == "routine_filing" else 0.0,
        "generic_tick_penalty": 0.75 if is_generic_macro_move else 0.0,
        "low_market_relevance_penalty": 0.55 if (not primary_entity and not primary_industry and not macro_theme and MARKET_RELEVANT_RE.search(f'{rep_title} {rep_summary}') is None) else 0.0,
        "public_affairs_penalty": 0.85 if is_public_affairs else 0.0,
        "pure_price_move_penalty": 0.85 if is_pure_price_move else 0.0,
        "probability_only_penalty": 0.55 if is_probability_only else 0.0,
        "calendar_preview_penalty": 0.95 if is_calendar_preview else 0.0,
        "unmapped_signal_penalty": 0.45 if is_unmapped_signal else 0.0,
        "platform_housekeeping_penalty": 0.85 if is_platform_housekeeping else 0.0,
        "wire_roundup_penalty": 0.9 if is_wire_roundup else 0.0,
        "routine_geopolitics_penalty": 0.75 if is_routine_geopolitics else 0.0,
        "casualty_or_rhetoric_penalty": 0.45 if is_casualty_or_rhetoric_update else 0.0,
        "weak_financing_macro_penalty": 0.6 if is_weak_financing_macro else 0.0,
        "generic_teaser_penalty": 0.8 if is_generic_teaser else 0.0,
        "market_commentary_penalty": 0.8 if is_market_commentary else 0.0,
        "institutional_survey_penalty": 0.85 if is_institutional_survey else 0.0,
        "bullet_teaser_penalty": 0.8 if is_bullet_teaser else 0.0,
        "broker_note_penalty": 0.8 if is_broker_note else 0.0,
        "official_commentary_penalty": 0.8 if is_official_commentary_only else 0.0,
        "diplomatic_protocol_penalty": 0.8 if is_diplomatic_protocol else 0.0,
    }

    high_local_impact = bool(primary_entity and entity_impact >= 0.78)
    undercovered_structural_entity = bool(
        primary_entity
        and event_type in STRUCTURAL_MICRO_EVENT_TYPES
        and action_key in STRUCTURAL_ACTION_KEYS
        and macro_theme is None
        and counters["independent_evidence_count"] <= 2
        and features["specificity"] >= 0.55
        and penalties["market_commentary_penalty"] == 0.0
        and penalties["broker_note_penalty"] == 0.0
        and penalties["official_commentary_penalty"] == 0.0
        and penalties["institutional_survey_penalty"] == 0.0
    )
    macro_coverage_heaviness = (
        coverage_residual
        if macro_theme and not primary_entity and action_key in {"general_update", "macro_move", "policy", "commodity"}
        else 0.0
    )
    micro_event_bonus = 7.5 if undercovered_structural_entity else (3.5 if high_local_impact and counters["independent_evidence_count"] <= 2 else 0.0)
    macro_coverage_drag = 8.0 * macro_coverage_heaviness if features["specificity"] < 0.72 else 4.0 * macro_coverage_heaviness
    score = (
        100.0
        * (
            0.18 * features["freshness"]
            + 0.12 * features["delta_strength"]
            + 0.18 * features["confirmation_strength"]
            + 0.08 * features["lane_mix"]
            + 0.12 * features["specificity"]
            + 0.12 * features["entity_relevance"]
            + 0.10 * features["researchability"]
            + 0.10 * features["investability_hint"]
        )
    )
    score += micro_event_bonus
    score -= macro_coverage_drag
    score -= 100.0 * sum(penalties.values()) * 0.2
    if action_key == "routine_filing":
        score = min(score, 15.0)
    if is_public_affairs:
        score = min(score, 18.0)
    if is_calendar_preview:
        score = min(score, 8.0)
    if is_unmapped_signal:
        score = min(score, 19.0)
    if is_platform_housekeeping:
        score = min(score, 18.0)
    if is_wire_roundup:
        score = min(score, 12.0)
    if is_routine_geopolitics:
        score = min(score, 18.0)
    if is_weak_financing_macro:
        score = min(score, 18.0)
    if is_generic_teaser:
        score = min(score, 16.0)
    if is_market_commentary:
        score = min(score, 18.0)
    if is_institutional_survey:
        score = min(score, 18.0)
    if is_bullet_teaser:
        score = min(score, 18.0)
    if is_broker_note:
        score = min(score, 18.0)
    if is_official_commentary_only:
        score = min(score, 18.0)
    if is_diplomatic_protocol:
        score = min(score, 18.0)
    if is_pure_price_move:
        score = min(score, 19.0)
    if is_generic_macro_move:
        score = min(score, 19.0)
    if is_probability_only:
        score = min(score, 19.0)
    score = max(score, 0.0)
    event_state, event_state_reason = derive_event_state(
        novelty_state(first_seen, last_seen, len(articles), confirmation_count, now, f"{focus_title} {rep_summary}"),
        confirmation_count,
        signal_count,
        official_source_present,
        action_key in STRUCTURAL_ACTION_KEYS,
        high_local_impact,
        calibrated_confirmation,
        uncertainty,
        f"{focus_title} {rep_summary}",
    )

    flags = {
        "event_state": event_state,
        "event_state_reason": event_state_reason,
        "features": features,
        "score_vector": score_vector,
        "penalties": penalties,
        "counters": {
            "article_count_raw": counters["article_count_raw"],
            "independent_evidence_count": counters["independent_evidence_count"],
            "source_family_count": counters["source_family_count"],
            "signal_platform_count": counters["signal_platform_count"],
            "confirmation_count": confirmation_count,
            "signal_count": signal_count,
        },
        "flags": {
            "signal_only": confirmation_count == 0 and signal_count > 0,
            "mixed_evidence": confirmation_count > 0 and signal_count > 0,
            "official_source_present": official_source_present,
            "structural_event": action_key in STRUCTURAL_ACTION_KEYS,
            "ongoing_topic": bool(macro_theme and not primary_entity),
            "contested": event_state == "contested",
            "undercovered_entity": bool(primary_entity and counters["independent_evidence_count"] <= 2),
            "high_local_impact": high_local_impact,
            "micro_event_protected": undercovered_structural_entity,
            "macro_coverage_capped": bool(macro_coverage_heaviness > 0.0),
        },
        "calibrated_confirmation": round(calibrated_confirmation, 4),
        "uncertainty": round(uncertainty, 4),
        "action_key": action_key,
        "macro_theme": macro_theme,
    }
    return round(score, 4), flags


def article_filter_sql(
    lookback_days: int,
    now: datetime,
    window_start: str | None,
    window_end: str | None,
    include_source_ids: set[str],
    exclude_source_ids: set[str],
) -> tuple[list[str], list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    start_bound = window_start
    if not start_bound and lookback_days > 0:
        start_bound = (now.astimezone(timezone.utc) - timedelta(days=int(lookback_days))).isoformat(timespec="seconds")
    if start_bound:
        clauses.append("(a.published_at >= ? OR (a.published_at IS NULL AND a.collected_at >= ?))")
        params.extend([start_bound, start_bound])
    if window_end:
        clauses.append("(a.published_at < ? OR (a.published_at IS NULL AND a.collected_at < ?))")
        params.extend([window_end, window_end])
    if include_source_ids:
        placeholders = ",".join("?" for _ in include_source_ids)
        clauses.append(f"a.source_id IN ({placeholders})")
        params.extend(sorted(include_source_ids))
    if exclude_source_ids:
        placeholders = ",".join("?" for _ in exclude_source_ids)
        clauses.append(f"a.source_id NOT IN ({placeholders})")
        params.extend(sorted(exclude_source_ids))
    return clauses, params


def count_selected_articles(conn: sqlite3.Connection, clauses: list[str], params: list[Any]) -> int:
    sql = "SELECT COUNT(*) FROM news_articles a"
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    row = conn.execute(sql, params).fetchone()
    return int(row[0] or 0)


def fetch_articles(conn: sqlite3.Connection, clauses: list[str], params: list[Any], limit_articles: int) -> list[Article]:
    sql = """
    SELECT
        a.article_id,
        a.source_id,
        COALESCE(s.source_family, '') AS source_family,
        a.title,
        COALESCE(a.title_norm, '') AS title_norm,
        COALESCE(a.summary, '') AS summary,
        COALESCE(a.canonical_url, '') AS canonical_url,
        a.published_at,
        a.collected_at,
        s.lane,
        s.trust_tier,
        s.coverage_scope
    FROM news_articles a
    JOIN source_registry s ON s.source_id = a.source_id
    """
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY COALESCE(a.published_at, a.collected_at) DESC"
    if limit_articles > 0:
        sql += f" LIMIT {int(limit_articles)}"
    rows = conn.execute(sql, params).fetchall()
    return [Article(*row) for row in rows]


def load_existing_event_state(conn: sqlite3.Connection) -> dict[str, dict[str, str]]:
    rows = conn.execute(
        """
        SELECT event_id, opportunity_state, created_at, first_seen_at, last_seen_at
        FROM events
        """
    ).fetchall()
    return {
        str(event_id): {
            "opportunity_state": str(opportunity_state or "unreviewed"),
            "created_at": str(created_at or ""),
            "first_seen_at": str(first_seen_at or ""),
            "last_seen_at": str(last_seen_at or ""),
        }
        for event_id, opportunity_state, created_at, first_seen_at, last_seen_at in rows
    }


def load_existing_entity_links(conn: sqlite3.Connection) -> dict[str, list[dict[str, Any]]]:
    rows = conn.execute(
        """
        SELECT event_id, entity_type, entity_id, entity_name, relevance_score, mapping_reason, mapping_confidence, mapping_version, mapping_source, created_at
        FROM event_entity_links
        ORDER BY rowid
        """
    ).fetchall()
    payload: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event_id, entity_type, entity_id, entity_name, relevance_score, mapping_reason, mapping_confidence, mapping_version, mapping_source, created_at in rows:
        payload[str(event_id)].append(
            {
                "entity_type": str(entity_type),
                "entity_id": str(entity_id),
                "entity_name": str(entity_name),
                "relevance_score": float(relevance_score or 0.0),
                "mapping_reason": str(mapping_reason or ""),
                "mapping_confidence": float(mapping_confidence or 0.0),
                "mapping_version": str(mapping_version or ""),
                "mapping_source": str(mapping_source or ""),
                "created_at": str(created_at or ""),
            }
        )
    return payload


def load_existing_event_articles(conn: sqlite3.Connection) -> dict[str, dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT event_id, article_id, link_type
        FROM article_event_links
        ORDER BY event_id, article_id
        """
    ).fetchall()
    payload: dict[str, dict[str, Any]] = defaultdict(lambda: {"articles": set(), "primary_article_id": None})
    for event_id, article_id, link_type in rows:
        bucket = payload[str(event_id)]
        bucket["articles"].add(str(article_id))
        if str(link_type or "") == "primary" and not bucket["primary_article_id"]:
            bucket["primary_article_id"] = str(article_id)
    return payload


def reset_event_relationships(conn: sqlite3.Connection, event_id: str, article_ids: set[str] | None = None) -> None:
    if article_ids is None:
        conn.execute("DELETE FROM article_event_links WHERE event_id = ?", (event_id,))
    elif article_ids:
        conn.execute(
            "UPDATE article_event_links SET link_type = 'supporting' WHERE event_id = ? AND link_type = 'primary'",
            (event_id,),
        )
        conn.execute("CREATE TEMP TABLE IF NOT EXISTS tmp_event_reset_article_ids (article_id TEXT PRIMARY KEY)")
        conn.execute("DELETE FROM tmp_event_reset_article_ids")
        conn.executemany(
            "INSERT OR IGNORE INTO tmp_event_reset_article_ids (article_id) VALUES (?)",
            ((article_id,) for article_id in article_ids),
        )
        conn.execute(
            """
            DELETE FROM article_event_links
            WHERE event_id = ?
              AND article_id IN (SELECT article_id FROM tmp_event_reset_article_ids)
            """,
            (event_id,),
        )
    conn.execute("DELETE FROM event_entity_links WHERE event_id = ?", (event_id,))
    conn.execute("DELETE FROM unresolved_event_mappings WHERE event_id = ?", (event_id,))


def cleanup_processed_article_links(conn: sqlite3.Connection, processed_article_ids: set[str], current_event_ids: set[str]) -> None:
    if not processed_article_ids:
        return
    conn.execute("CREATE TEMP TABLE IF NOT EXISTS tmp_processed_article_ids (article_id TEXT PRIMARY KEY)")
    conn.execute("DELETE FROM tmp_processed_article_ids")
    conn.executemany(
        "INSERT OR IGNORE INTO tmp_processed_article_ids (article_id) VALUES (?)",
        ((article_id,) for article_id in processed_article_ids),
    )
    if current_event_ids:
        conn.execute("CREATE TEMP TABLE IF NOT EXISTS tmp_current_event_ids (event_id TEXT PRIMARY KEY)")
        conn.execute("DELETE FROM tmp_current_event_ids")
        conn.executemany(
            "INSERT OR IGNORE INTO tmp_current_event_ids (event_id) VALUES (?)",
            ((event_id,) for event_id in current_event_ids),
        )
        conn.execute(
            """
            DELETE FROM article_event_links
            WHERE article_id IN (SELECT article_id FROM tmp_processed_article_ids)
              AND event_id NOT IN (SELECT event_id FROM tmp_current_event_ids)
            """
        )
    else:
        conn.execute(
            """
            DELETE FROM article_event_links
            WHERE article_id IN (SELECT article_id FROM tmp_processed_article_ids)
            """
        )


def delete_orphan_events(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        DELETE FROM events
        WHERE event_id IN (
            SELECT e.event_id
            FROM events e
            LEFT JOIN article_event_links ael ON ael.event_id = e.event_id
            WHERE ael.event_id IS NULL
        )
        """
    )
    conn.execute(
        """
        DELETE FROM event_entity_links
        WHERE event_id NOT IN (SELECT event_id FROM events)
        """
    )


def refresh_views(conn: sqlite3.Connection) -> None:
    conn.execute("DROP VIEW IF EXISTS v_radar_industry")
    conn.execute(load_view_sql("v_radar_industry"))
    conn.execute("DROP VIEW IF EXISTS v_daily_digest")
    conn.execute(load_view_sql("v_daily_digest"))


def resolve_preserved_context(
    event_id: str,
    article_ids: set[str],
    existing_event_state: dict[str, dict[str, str]],
    existing_entity_links: dict[str, list[dict[str, Any]]],
    existing_event_articles: dict[str, dict[str, Any]],
) -> tuple[dict[str, str] | None, list[dict[str, Any]] | None]:
    direct_state = existing_event_state.get(event_id)
    direct_links = existing_entity_links.get(event_id)
    if direct_state or direct_links:
        return direct_state, direct_links
    if not article_ids:
        return None, None

    best_event_id: str | None = None
    best_score: tuple[float, ...] | None = None
    ambiguous = False
    for candidate_event_id, candidate_payload in existing_event_articles.items():
        candidate_articles = set(candidate_payload.get("articles") or set())
        if not candidate_articles:
            continue
        overlap = article_ids & candidate_articles
        if not overlap:
            continue
        current_coverage = len(overlap) / max(len(article_ids), 1)
        candidate_coverage = len(overlap) / max(len(candidate_articles), 1)
        primary_article_id = str(candidate_payload.get("primary_article_id") or "")
        primary_hit = bool(primary_article_id) and primary_article_id in article_ids
        exact_match = article_ids == candidate_articles
        strong_overlap = min(current_coverage, candidate_coverage) >= 0.5
        if not exact_match and not (primary_hit and strong_overlap):
            continue
        score = (
            1.0 if exact_match else 0.0,
            1.0 if primary_hit else 0.0,
            min(current_coverage, candidate_coverage),
            float(len(overlap)),
            -abs(len(candidate_articles) - len(article_ids)),
        )
        if best_score is None or score > best_score:
            best_event_id = candidate_event_id
            best_score = score
            ambiguous = False
        elif score == best_score:
            ambiguous = True

    if best_event_id is None or ambiguous:
        return None, None
    return existing_event_state.get(best_event_id), existing_entity_links.get(best_event_id)


def build_event_title(articles: list[Article], primary_entity: str | None, action_key: str) -> str:
    rep = choose_representative(articles)
    title = article_title_clean(rep)
    if primary_entity and action_key == "routine_filing":
        filing = normalize_text(rep.summary) or "Routine filing"
        return f"{primary_entity}: {filing}"
    return title[:240]


def event_id_for_key(key: str) -> str:
    return "evt_" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]


def insert_event(
    conn: sqlite3.Connection,
    event_id: str,
    event_type: str,
    event_title: str,
    topic_key: str,
    first_seen: datetime,
    last_seen: datetime,
    novelty: str,
    event_state: str,
    confirmation_count: int,
    source_mix: dict[str, int],
    score_vector: dict[str, Any],
    calibrated_confirmation: float,
    uncertainty: float,
    article_count_raw: int,
    independent_evidence_count: int,
    source_family_count: int,
    signal_platform_count: int,
    primary_industry: str | None,
    primary_entity: str | None,
    rank_score: float,
    rank_flags: dict[str, Any],
    existing_state: dict[str, str] | None,
) -> None:
    created_at = existing_state.get("created_at") if existing_state else ""
    opportunity_state = existing_state.get("opportunity_state") if existing_state else "unreviewed"
    existing_first_seen = parse_iso(existing_state.get("first_seen_at") if existing_state else "")
    existing_last_seen = parse_iso(existing_state.get("last_seen_at") if existing_state else "")
    if existing_first_seen and existing_first_seen < first_seen:
        first_seen = existing_first_seen
    if existing_last_seen and existing_last_seen > last_seen:
        last_seen = existing_last_seen
    conn.execute(
        """
        INSERT INTO events (
            event_id,
            event_type,
            event_title,
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
            opportunity_state,
            created_at,
            updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        ON CONFLICT(event_id) DO UPDATE SET
            event_type = excluded.event_type,
            event_title = excluded.event_title,
            topic_key = excluded.topic_key,
            event_state = excluded.event_state,
            first_seen_at = excluded.first_seen_at,
            last_seen_at = excluded.last_seen_at,
            novelty_state = excluded.novelty_state,
            confirmation_count = excluded.confirmation_count,
            source_mix = excluded.source_mix,
            score_vector = excluded.score_vector,
            calibrated_confirmation = excluded.calibrated_confirmation,
            uncertainty = excluded.uncertainty,
            article_count_raw = excluded.article_count_raw,
            independent_evidence_count = excluded.independent_evidence_count,
            source_family_count = excluded.source_family_count,
            signal_platform_count = excluded.signal_platform_count,
            primary_industry = excluded.primary_industry,
            primary_entity = excluded.primary_entity,
            event_rank_score = excluded.event_rank_score,
            event_rank_flags = excluded.event_rank_flags,
            updated_at = datetime('now')
        """,
        (
            event_id,
            event_type,
            event_title,
            topic_key,
            event_state,
            first_seen.isoformat(timespec="seconds"),
            last_seen.isoformat(timespec="seconds"),
            novelty,
            confirmation_count,
            json.dumps(source_mix, ensure_ascii=False, sort_keys=True),
            json.dumps(score_vector, ensure_ascii=False, sort_keys=True),
            calibrated_confirmation,
            uncertainty,
            article_count_raw,
            independent_evidence_count,
            source_family_count,
            signal_platform_count,
            primary_industry,
            primary_entity,
            rank_score,
            json.dumps(rank_flags, ensure_ascii=False, sort_keys=True),
            opportunity_state or "unreviewed",
            created_at or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        ),
    )


def snapshot_id_for(event_id: str, granularity: str, label: str) -> str:
    key = f"{event_id}|{granularity}|{label}"
    return "ews_" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:24]


def upsert_event_window_snapshot(
    conn: sqlite3.Connection,
    window_meta: dict[str, str],
    event_id: str,
    event_type: str,
    event_title: str,
    topic_key: str,
    first_seen: datetime,
    last_seen: datetime,
    novelty: str,
    event_state: str,
    confirmation_count: int,
    source_mix: dict[str, int],
    score_vector: dict[str, Any],
    calibrated_confirmation: float,
    uncertainty: float,
    article_count_raw: int,
    independent_evidence_count: int,
    source_family_count: int,
    signal_platform_count: int,
    primary_industry: str | None,
    primary_entity: str | None,
    rank_score: float,
    rank_flags: dict[str, Any],
    article_ids: set[str],
) -> None:
    granularity = window_meta["granularity"]
    label = window_meta["label"]
    conn.execute(
        """
        INSERT INTO event_window_snapshots (
            snapshot_id,
            event_id,
            window_granularity,
            window_label,
            window_start,
            window_end,
            as_of,
            event_type,
            event_title,
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
            article_ids,
            updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        ON CONFLICT(event_id, window_granularity, window_label) DO UPDATE SET
            snapshot_id = excluded.snapshot_id,
            window_start = excluded.window_start,
            window_end = excluded.window_end,
            as_of = excluded.as_of,
            event_type = excluded.event_type,
            event_title = excluded.event_title,
            topic_key = excluded.topic_key,
            event_state = excluded.event_state,
            first_seen_at = excluded.first_seen_at,
            last_seen_at = excluded.last_seen_at,
            novelty_state = excluded.novelty_state,
            confirmation_count = excluded.confirmation_count,
            source_mix = excluded.source_mix,
            score_vector = excluded.score_vector,
            calibrated_confirmation = excluded.calibrated_confirmation,
            uncertainty = excluded.uncertainty,
            article_count_raw = excluded.article_count_raw,
            independent_evidence_count = excluded.independent_evidence_count,
            source_family_count = excluded.source_family_count,
            signal_platform_count = excluded.signal_platform_count,
            primary_industry = excluded.primary_industry,
            primary_entity = excluded.primary_entity,
            event_rank_score = excluded.event_rank_score,
            event_rank_flags = excluded.event_rank_flags,
            article_ids = excluded.article_ids,
            updated_at = datetime('now')
        """,
        (
            snapshot_id_for(event_id, granularity, label),
            event_id,
            granularity,
            label,
            window_meta["start"],
            window_meta["end"],
            window_meta["as_of"],
            event_type,
            event_title,
            topic_key,
            event_state,
            first_seen.isoformat(timespec="seconds"),
            last_seen.isoformat(timespec="seconds"),
            novelty,
            confirmation_count,
            json.dumps(source_mix, ensure_ascii=False, sort_keys=True),
            json.dumps(score_vector, ensure_ascii=False, sort_keys=True),
            calibrated_confirmation,
            uncertainty,
            article_count_raw,
            independent_evidence_count,
            source_family_count,
            signal_platform_count,
            primary_industry,
            primary_entity,
            rank_score,
            json.dumps(rank_flags, ensure_ascii=False, sort_keys=True),
            json.dumps(sorted(article_ids), ensure_ascii=False),
        ),
    )


def insert_links(conn: sqlite3.Connection, event_id: str, articles: list[Article]) -> None:
    representative = choose_representative(articles).article_id
    for article in articles:
        link_type = "primary" if article.article_id == representative else "supporting"
        conn.execute(
            """
            INSERT INTO article_event_links (article_id, event_id, link_type, created_at)
            VALUES (?, ?, ?, datetime('now'))
            ON CONFLICT(article_id, event_id) DO UPDATE SET
                link_type = excluded.link_type
            """,
            (article.article_id, event_id, link_type),
        )


def insert_entity_links(
    conn: sqlite3.Connection,
    event_id: str,
    primary_entity: str | None,
    institution_entity: str | None,
    primary_industry: str | None,
    macro_theme: str | None,
    preserved_links: list[dict[str, Any]] | None = None,
) -> int:
    rows: list[tuple[str, str, str, float, str, float, str, str, str]] = []
    for row in preserved_links or []:
        entity_type = str(row["entity_type"])
        entity_id = str(row["entity_id"])
        entity_name = str(row["entity_name"])
        relevance_score = float(row["relevance_score"])
        mapping_reason = str(row.get("mapping_reason") or "preserved_existing_link")
        mapping_confidence = float(row.get("mapping_confidence") or relevance_score or 0.7)
        mapping_version = str(row.get("mapping_version") or "mapping_layer_v1")
        mapping_source = str(row.get("mapping_source") or "preserved_existing")
        created_at = str(row.get("created_at") or "")
        if entity_type == "company":
            normalized_name = canonicalize_entity_name(trim_company_candidate(entity_name))
            if not normalized_name or not looks_like_company_entity(normalized_name):
                continue
            normalized_id = canonical_company_id(normalized_name) or slugify(normalized_name)
            if primary_entity:
                primary_company_id = canonical_company_id(primary_entity) or slugify(primary_entity)
                if normalized_id != primary_company_id:
                    continue
            entity_id = normalized_id
            entity_name = normalized_name
        elif entity_type == "institution":
            normalized_name = extract_institution_entity(entity_name)
            if not normalized_name:
                continue
            entity_id = slugify(normalized_name)
            entity_name = normalized_name
        rows.append(
            (
                entity_type,
                entity_id,
                entity_name,
                relevance_score,
                mapping_reason,
                mapping_confidence,
                mapping_version,
                mapping_source,
                created_at,
            )
        )
    if primary_entity:
        rows.append(
            (
                "company",
                canonical_company_id(primary_entity) or slugify(primary_entity),
                primary_entity,
                1.0,
                "primary_entity_extract",
                0.95,
                "mapping_layer_v1",
                "builder",
                "",
            )
        )
    if institution_entity:
        rows.append(
            (
                "institution",
                slugify(institution_entity),
                institution_entity,
                0.82,
                "institution_entity_extract",
                0.8,
                "mapping_layer_v1",
                "builder",
                "",
            )
        )
    if primary_industry:
        rows.append(
            (
                "industry",
                slugify(primary_industry),
                primary_industry,
                0.9,
                "industry_keyword_match",
                0.82,
                "mapping_layer_v1",
                "builder",
                "",
            )
        )
    if macro_theme:
        rows.append(
            (
                "macro_theme",
                slugify(macro_theme),
                macro_theme,
                0.8,
                "macro_theme_match",
                0.78,
                "mapping_layer_v1",
                "builder",
                "",
            )
        )

    seen: set[tuple[str, str, str]] = set()
    inserted = 0
    for entity_type, entity_id, entity_name, relevance_score, mapping_reason, mapping_confidence, mapping_version, mapping_source, created_at in rows:
        dedupe_key = (entity_type, entity_id, entity_name)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        conn.execute(
            """
            INSERT INTO event_entity_links (
                event_id,
                entity_type,
                entity_id,
                entity_name,
                relevance_score,
                mapping_reason,
                mapping_confidence,
                mapping_version,
                mapping_source,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                entity_type,
                entity_id,
                entity_name,
                relevance_score,
                mapping_reason,
                mapping_confidence,
                mapping_version,
                mapping_source,
                created_at or datetime.now(timezone.utc).isoformat(timespec="seconds"),
            ),
        )
        inserted += 1
    return inserted


def upsert_unresolved_mapping(
    conn: sqlite3.Connection,
    event_id: str,
    topic_key: str,
    event_title: str,
    unresolved_reason: str,
) -> None:
    conn.execute(
        """
        INSERT INTO unresolved_event_mappings (
            event_id,
            topic_key,
            event_title,
            unresolved_reason,
            mapping_version,
            detected_at,
            updated_at
        ) VALUES (?, ?, ?, ?, 'mapping_layer_v1', datetime('now'), datetime('now'))
        ON CONFLICT(event_id) DO UPDATE SET
            topic_key = excluded.topic_key,
            event_title = excluded.event_title,
            unresolved_reason = excluded.unresolved_reason,
            mapping_version = excluded.mapping_version,
            updated_at = datetime('now')
        """,
        (event_id, topic_key, event_title, unresolved_reason),
    )


def should_queue_unresolved_mapping(
    event_title: str,
    event_type: str,
    source_mix: dict[str, int],
    rank_flags: dict[str, Any],
) -> bool:
    title = normalize_text(event_title)
    if not title:
        return False
    confirmation_count = int(source_mix.get("confirmation") or 0)
    signal_count = int(source_mix.get("signal") or 0)
    flags_bucket = rank_flags.get("flags") if isinstance(rank_flags.get("flags"), dict) else {}
    structural_event = bool(flags_bucket.get("structural_event"))
    if event_type in {"macro_data", "policy", "commodity_disruption"}:
        return False
    if event_type == "social_signal":
        return False
    if signal_count > 0 and confirmation_count == 0:
        return False
    if (
        GENERIC_TEASER_RE.search(title)
        or BULLET_TEASER_RE.search(title)
        or MARKET_COMMENTARY_RE.search(title)
        or INSTITUTIONAL_SURVEY_RE.search(title)
        or BROKER_NOTE_RE.search(title)
        or WIRE_ROUNDUP_RE.search(title)
        or PLATFORM_HOUSEKEEPING_RE.search(title)
        or PURE_PRICE_MOVE_RE.search(title)
        or GEOPOLITICAL_ROUTINE_RE.search(title)
        or OFFICIAL_COMMENTARY_ONLY_RE.search(title)
        or DIPLOMATIC_PROTOCOL_RE.search(title)
    ):
        return False
    trimmed = trim_company_candidate(title)
    if CONCEPTUAL_ENTITY_FRAGMENT_RE.search(trimmed) and find_entity_alias(title) is None:
        return False
    if len(trimmed) <= 8 and find_entity_alias(title) is None and not structural_event:
        return False
    company_cue = False
    if find_entity_alias(title) is not None:
        company_cue = True
    elif LEADING_CHINESE_COMPANY_RE.match(title):
        lead = canonicalize_entity_name(trim_company_candidate(LEADING_CHINESE_COMPANY_RE.match(title).group(1)))
        company_cue = bool(lead and looks_like_company_entity(lead))
    elif "：" in title:
        left = canonicalize_entity_name(trim_company_candidate(title.split("：", 1)[0]))
        company_cue = bool(left and looks_like_company_entity(left))
    elif BRACKET_TITLE_RE.match(title):
        bracket = canonicalize_entity_name(trim_company_candidate(BRACKET_TITLE_RE.match(title).group(1)))
        company_cue = bool(bracket and looks_like_company_entity(bracket))
    elif REUTERS_ENTITY_RE.match(title):
        reuters = canonicalize_entity_name(trim_company_candidate(REUTERS_ENTITY_RE.match(title).group(1)))
        company_cue = bool(reuters and looks_like_company_entity(reuters))
    if not company_cue:
        return False
    return structural_event or company_cue or confirmation_count > 0


def derive_granularity_class(flags: dict[str, Any]) -> str:
    flags_bucket = flags.get("flags") if isinstance(flags.get("flags"), dict) else {}
    counters_bucket = flags.get("counters") if isinstance(flags.get("counters"), dict) else {}
    structural_event = bool(flags_bucket.get("structural_event"))
    ongoing_topic = bool(flags_bucket.get("ongoing_topic"))
    update_count = int(counters_bucket.get("update_count") or 0)
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


def begin_immediate_with_retry(conn: sqlite3.Connection) -> None:
    for attempt in range(1, SQLITE_BEGIN_RETRY_ATTEMPTS + 1):
        try:
            conn.execute("BEGIN IMMEDIATE")
            return
        except sqlite3.OperationalError as exc:
            message = str(exc).lower()
            if "locked" not in message and "busy" not in message:
                raise
            if attempt >= SQLITE_BEGIN_RETRY_ATTEMPTS:
                raise
            sleep_seconds = SQLITE_BEGIN_RETRY_SLEEP_SECONDS * attempt
            print(
                "sqlite_write_lock_wait "
                f"attempt={attempt} sleep_seconds={sleep_seconds:.1f} error={exc}"
            )
            time.sleep(sleep_seconds)


def main() -> None:
    args = parse_args()
    if not args.db.exists():
        raise SystemExit(f"database missing: {args.db}")
    conn = sqlite3.connect(args.db, timeout=SQLITE_BUSY_TIMEOUT_MS / 1000)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(f"PRAGMA busy_timeout = {SQLITE_BUSY_TIMEOUT_MS}")
    ensure_event_schema(conn)
    conn.commit()
    now = resolve_as_of(args.as_of)
    try:
        include_source_ids = {normalize_text(source_id) for source_id in args.include_source_id if normalize_text(source_id)}
        exclude_source_ids = {normalize_text(source_id) for source_id in args.exclude_source_id if normalize_text(source_id)}
        window_start_bound = resolve_window_bound(args.window_start)
        window_end_bound = resolve_window_bound(args.window_end)
        window_meta = resolve_window_metadata(args, now, window_start_bound, window_end_bound)
        clauses, params = article_filter_sql(
            lookback_days=args.lookback_days,
            now=now,
            window_start=window_start_bound,
            window_end=window_end_bound,
            include_source_ids=include_source_ids,
            exclude_source_ids=exclude_source_ids,
        )
        selected_article_count = count_selected_articles(conn, clauses, params)
        print(f"article_candidates: {selected_article_count}", flush=True)
        if args.max_article_count and selected_article_count > int(args.max_article_count):
            raise SystemExit(
                "selected article window too large: "
                f"{selected_article_count} > max_article_count={int(args.max_article_count)}"
            )
        articles = fetch_articles(conn, clauses=clauses, params=params, limit_articles=args.limit_articles)
        if args.snapshot_only:
            existing_event_state: dict[str, dict[str, str]] = {}
            existing_entity_links: dict[str, list[dict[str, Any]]] = {}
            existing_event_articles: dict[str, dict[str, Any]] = {}
        else:
            existing_event_state = load_existing_event_state(conn)
            existing_entity_links = load_existing_entity_links(conn)
            existing_event_articles = load_existing_event_articles(conn)

        groups: dict[str, list[Article]] = defaultdict(list)
        metadata: dict[str, dict[str, Any]] = {}

        for article in articles:
            title = article_title_clean(article)
            classification_text = headline_focus_text(title) or title[:140]
            event_type, action_key = infer_event_type(title, article)
            primary_entity = extract_primary_entity(title, article)
            institution_entity = extract_institution_entity(title)
            primary_industry = keyword_match(classification_text, INDUSTRY_KEYWORDS)
            macro_theme = keyword_match(classification_text, MACRO_THEMES)
            key = merge_key(article, title, event_type, action_key, primary_entity, primary_industry, macro_theme)
            groups[key].append(article)
            if key not in metadata:
                metadata[key] = {
                    "event_type": event_type,
                    "action_key": action_key,
                    "primary_entity": primary_entity,
                    "institution_entity": institution_entity,
                    "primary_industry": primary_industry,
                    "macro_theme": macro_theme,
                }
            else:
                if primary_entity and not metadata[key].get("primary_entity"):
                    metadata[key]["primary_entity"] = primary_entity
                if institution_entity and not metadata[key].get("institution_entity"):
                    metadata[key]["institution_entity"] = institution_entity
                if primary_industry and not metadata[key].get("primary_industry"):
                    metadata[key]["primary_industry"] = primary_industry
                if macro_theme and not metadata[key].get("macro_theme"):
                    metadata[key]["macro_theme"] = macro_theme

        current_event_ids = {event_id_for_key(key) for key in groups}
        processed_article_ids = {article.article_id for article in articles}
        begin_immediate_with_retry(conn)
        if not args.snapshot_only and not args.no_rebuild:
            cleanup_processed_article_links(conn, processed_article_ids, current_event_ids)

        event_count = 0
        ranked_count = 0
        snapshot_count = 0
        for key, group_articles in groups.items():
            meta = metadata[key]
            times = [article_timestamp(article) for article in group_articles]
            first_seen = min(times)
            last_seen = max(times)
            source_mix = build_source_mix(group_articles)
            counters = build_evidence_counters(group_articles)
            confirmation_count = counters["independent_confirmation_count"]
            combined_text = " ".join(article_title_clean(article) for article in group_articles)
            novelty = novelty_state(first_seen, last_seen, len(group_articles), confirmation_count, now, combined_text)
            score, flags = compute_rank(
                group_articles,
                str(meta["event_type"]),
                str(meta["action_key"]),
                meta.get("primary_entity"),
                meta.get("primary_industry"),
                meta.get("macro_theme"),
                now,
            )
            recent_updates = collect_event_updates(
                group_articles,
                meta.get("primary_entity"),
                meta.get("primary_industry"),
                meta.get("macro_theme"),
                str(meta["action_key"]),
            )
            flags["update_count"] = len(recent_updates)
            flags["latest_update_signature"] = str(recent_updates[0]["update_signature"]) if recent_updates else ""
            flags["recent_updates"] = recent_updates[:5]
            counters_bucket = flags.get("counters") if isinstance(flags.get("counters"), dict) else {}
            counters_bucket["update_count"] = len(recent_updates)
            flags["counters"] = counters_bucket
            flags_bucket = flags.get("flags") if isinstance(flags.get("flags"), dict) else {}
            flags_bucket["granularity_class"] = derive_granularity_class(flags)
            flags["flags"] = flags_bucket
            if window_meta is not None:
                flags["window"] = window_meta
            event_state = str(flags.get("event_state") or "emerging")
            topic_key = topic_key_for(
                str(meta["event_type"]),
                meta.get("primary_entity"),
                meta.get("primary_industry"),
                meta.get("macro_theme"),
            )
            score_vector = flags.get("score_vector") if isinstance(flags.get("score_vector"), dict) else {}
            calibrated_confirmation = float(flags.get("calibrated_confirmation") or 0.0)
            uncertainty = float(flags.get("uncertainty") or 0.0)
            event_counters = flags.get("counters") if isinstance(flags.get("counters"), dict) else {}
            event_id = event_id_for_key(key)
            event_title = build_event_title(group_articles, meta.get("primary_entity"), str(meta["action_key"]))
            article_ids = {article.article_id for article in group_articles}
            if window_meta is not None:
                upsert_event_window_snapshot(
                    conn,
                    window_meta,
                    event_id,
                    str(meta["event_type"]),
                    event_title,
                    topic_key,
                    first_seen,
                    last_seen,
                    novelty,
                    event_state,
                    confirmation_count,
                    source_mix,
                    score_vector,
                    calibrated_confirmation,
                    uncertainty,
                    int(event_counters.get("article_count_raw") or len(group_articles)),
                    int(event_counters.get("independent_evidence_count") or counters["independent_evidence_count"]),
                    int(event_counters.get("source_family_count") or counters["source_family_count"]),
                    int(event_counters.get("signal_platform_count") or counters["signal_platform_count"]),
                    meta.get("primary_industry"),
                    meta.get("primary_entity"),
                    score,
                    flags,
                    article_ids,
                )
                snapshot_count += 1
            if args.snapshot_only:
                event_count += 1
                if score > 0:
                    ranked_count += 1
                continue
            preserved_state, preserved_links = resolve_preserved_context(
                event_id,
                article_ids,
                existing_event_state,
                existing_entity_links,
                existing_event_articles,
            )
            reset_event_relationships(conn, event_id, article_ids if args.slice_safe else None)
            insert_event(
                conn,
                event_id,
                str(meta["event_type"]),
                event_title,
                topic_key,
                first_seen,
                last_seen,
                novelty,
                event_state,
                confirmation_count,
                source_mix,
                score_vector,
                calibrated_confirmation,
                uncertainty,
                int(event_counters.get("article_count_raw") or len(group_articles)),
                int(event_counters.get("independent_evidence_count") or counters["independent_evidence_count"]),
                int(event_counters.get("source_family_count") or counters["source_family_count"]),
                int(event_counters.get("signal_platform_count") or counters["signal_platform_count"]),
                meta.get("primary_industry"),
                meta.get("primary_entity"),
                score,
                flags,
                preserved_state,
            )
            insert_links(conn, event_id, group_articles)
            inserted_entity_links = insert_entity_links(
                conn,
                event_id,
                meta.get("primary_entity"),
                meta.get("institution_entity"),
                meta.get("primary_industry"),
                meta.get("macro_theme"),
                preserved_links=preserved_links,
            )
            if inserted_entity_links == 0:
                if should_queue_unresolved_mapping(
                    event_title,
                    str(meta["event_type"]),
                    source_mix,
                    flags,
                ):
                    upsert_unresolved_mapping(
                        conn,
                        event_id,
                        topic_key,
                        event_title,
                        "no_entity_candidate",
                    )
            event_count += 1
            if score > 0:
                ranked_count += 1

        if not args.snapshot_only and not args.no_rebuild:
            delete_orphan_events(conn)
        if not args.snapshot_only:
            refresh_views(conn)
        conn.commit()

        top_rows = conn.execute(
            """
            SELECT event_id, event_title, event_type, event_state, event_rank_score, novelty_state, confirmation_count
            FROM events
            ORDER BY event_rank_score DESC, datetime(last_seen_at) DESC
            LIMIT 10
            """
        ).fetchall()

        print(f"articles_processed: {len(articles)}")
        print(f"events_built: {event_count}")
        print(f"events_ranked_positive: {ranked_count}")
        if window_meta is not None:
            print(f"window_snapshots_written: {snapshot_count}")
        print("top_events:")
        for row in top_rows:
            print(row)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
