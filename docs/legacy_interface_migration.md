# Legacy Interface Migration

## 目的

这份文档回答三件事：

1. 旧接口现在各自依赖什么
2. 共享库先提供什么兼容面
3. 后续应该怎么迁移，而不是继续各自维护私有新闻链路

## 当前旧接口盘点

### 投资机会报告

当前仍主要依赖：

- `scripts/refresh_market_news.py`
- `scripts/analyze_market_news.py`
- `scripts/run_investment_reporting_pipeline.py`
- payload 内的 `news_digest`

当前痛点：

- 自己抓新闻
- 自己做 digest
- 与共享 event / ranking 脱节

### 行业雷达

当前仍主要依赖：

- `量化/industry_signal_radar/scripts/radar_news_policy.py`
- `量化/industry_signal_radar/scripts/radar_scan_runner.py`

当前痛点：

- 自己抓新闻
- 自己做 policy article 聚类
- 输出没有沉淀到共享 event 层

### 研究线程

当前问题更明显：

- 可能会定向抓取
- 但没有统一读取入口
- 也没有统一回写入口

## 当前兼容策略

### 1. 先兼容输入面

`News Event Hub` 当前先提供：

- `legacy_news_digest_latest.json`

让旧 `news_digest` 风格 consumer 可以先从共享库读取，而不是继续依赖私有抓取链。

### 2. 再切 canonical feed

共享层已经同时提供：

- `opportunity_report_feed_latest.json`
- `industry_radar_feed_latest.json`
- `research_feed_latest.json`

后续消费者应从兼容层逐步迁到 canonical feed。

## 字段迁移方向

### 投资机会报告

旧字段到新来源的对应关系：

- `top_market_news`
  - 来自 `opportunity_report_feed_latest.json -> macro_events`
- `new_opportunity_candidates`
  - 来自 `opportunity_report_feed_latest.json -> opportunity_buckets.new_opportunity_candidates`
- `tracking_updates`
  - 来自 `opportunity_report_feed_latest.json -> opportunity_buckets.tracking_updates`
- `watchlist_candidates`
  - 来自 `opportunity_report_feed_latest.json -> opportunity_buckets.watchlist_candidates`
- `company_headlines`
  - 来自 `opportunity_report_feed_latest.json -> legacy_news_digest.company_headlines`

暂时仍是兼容占位的字段：

- `investor_views`
- `polymarket_opportunities`

### 投资机会雷达

旧雷达侧的 `policy_articles`，迁移方向是：

- 先读取 `industry_radar_feed_latest.json -> industries[*].policy_articles`
- 再逐步改成读取 `industries[*].shared_events`

但这只是兼容入口。

当前共享层对 `industry_radar_feed_latest.json` 的主定位已经改成：

- 一份完整的 `event_pool`
- 一份显式 `discovery_contract`
- 一个 `persistent_window_start`，用于承接仍在发酵的成熟事件
- 一组 `macro / company / industry / institution / special_situation / tracking` 视角
- `discovery_contract.route_catalog` 已开始冻结这些视角对应的标准补抓 source 集
- 这些标准 route 现在都能通过共享 discovery runner 直接执行
- 行业分组只是为了兼容旧展示层保留

也就是说：

- 兼容字段名先保留
- 底层对象已经从 article cluster 换成 shared event

### 研究线程

建议直接读 canonical feed：

- `research_feed_latest.json`

不要再新造一份研究私有兼容层。

## 推荐迁移顺序

1. 先把 consumer 的输入源改成 `consumer_exports/`
2. 在不改展示层的前提下，先切 `legacy_news_digest_latest.json` 或 `policy_articles` 兼容字段
3. 再逐步改成 canonical feed
4. 最后再关闭旧私有抓取/聚类链路

## 哪些旧接口现在不该再扩张

以下旧接口可以继续运行，但不应再继续扩功能：

- `refresh_market_news.py` 的私有新闻抓取职责
- `radar_news_policy.py` 的私有公共新闻抓取职责
- 各局部脚本里的一次性新闻聚类

后续应该新增功能的地方，应优先落在：

- `news_event_hub/scripts/export_consumer_views.py`
- `news_event_hub` 的 shared event / ranking / consumer adapter

## 当前阶段性结论

这次迁移的关键不是“立刻删掉旧接口”，而是：

- 先让共享库可读
- 再让旧 consumer 切输入面
- 最后才下线旧私有链路
