#!/usr/bin/env python3
from __future__ import annotations

from datetime import datetime, timezone

from run_browser_signal_collector import (
    normalize_xiaohongshu_items,
    normalize_xueqiu_dom_items,
    parse_xiaohongshu_time_text,
    parse_xueqiu_time_text,
)


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    run_dt = datetime(2026, 4, 7, 12, 0, tzinfo=timezone.utc)
    assert_true(
        parse_xueqiu_time_text("昨天 14:35· 来自雪球", run_dt) == "2026-04-06T06:35:00+00:00",
        "xueqiu time parser should resolve yesterday timestamps in China timezone",
    )
    assert_true(
        parse_xueqiu_time_text("修改于04-05 15:28· 来自雪球", run_dt) == "2026-04-05T07:28:00+00:00",
        "xueqiu time parser should resolve month-day timestamps in China timezone",
    )
    items = normalize_xueqiu_dom_items(
        [
            {
                "author": "产业链观察",
                "time_text": "昨天 14:35· 来自雪球",
                "href": "/5691044915/382763346",
                "title": "泡泡玛特海外扩张提速",
                "body_text": "泡泡玛特公司海外扩张继续推进，订单兑现速度超预期。",
                "raw_text": "",
            },
            {
                "author": "短线老师",
                "time_text": "昨天 13:00· 来自雪球",
                "href": "/1234567890/111111111",
                "title": "",
                "body_text": "泡泡玛特 午评：明天继续看多。",
                "raw_text": "",
            },
        ],
        {"max_items_per_target": 4},
        run_dt,
        {"name": "泡泡玛特", "ticker": "9992.HK", "region": "HK"},
        ("订单", "扩张", "收购"),
    )
    assert_true(len(items) >= 1, "dom normalization should keep at least one discovery-like record")
    assert_true(items[0]["canonical_url"] == "https://xueqiu.com/5691044915/382763346", "dom normalization should build canonical xueqiu status urls")
    assert_true(
        parse_xiaohongshu_time_text("03-27", run_dt) == "2026-03-27T04:00:00+00:00",
        "xiaohongshu time parser should resolve month-day timestamps in China timezone",
    )
    xhs_items = normalize_xiaohongshu_items(
        [
            {
                "explore_href": "/explore/69d37b3600000000230106bf",
                "title": "段永平在雪球上对泡泡玛特的发言",
                "author": "君竹阁",
                "time_text": "1天前",
                "likes": "480",
                "raw_text": "段永平在雪球上对泡泡玛特的发言 君竹阁 1天前 480",
            },
            {
                "explore_href": "/explore/69d37b3600000000230106c0",
                "title": "大家都在搜",
                "author": "",
                "time_text": "",
                "likes": "",
                "raw_text": "大家都在搜 泡泡玛特最火的3个系列",
            },
        ],
        {"max_items_per_target": 4},
        run_dt,
        {"name": "泡泡玛特", "ticker": "9992.HK", "region": "HK"},
        ("门店", "联名", "黄牛", "翻红"),
    )
    assert_true(len(xhs_items) == 1, "xiaohongshu normalization should keep note cards and drop query-note blocks")
    assert_true(
        xhs_items[0]["canonical_url"] == "https://www.xiaohongshu.com/explore/69d37b3600000000230106bf",
        "xiaohongshu normalization should build canonical explore urls",
    )
    print("browser_signal_smoke_ok")


if __name__ == "__main__":
    main()
