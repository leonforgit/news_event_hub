# Layer 3 Consumer Contract V1

## 目标

Layer 3 的最小可用版，不是立刻改写所有下游，而是先把共享库稳定导出成几份明确的 consumer feed。

这样做的目的有两个：

1. 让下游先有统一读取入口
2. 让旧接口迁移从“直接改业务逻辑”变成“先切换输入面”

## 当前导出物

默认导出目录：

- `private runtime`: `/opt/news-event-hub/state/consumer_exports`

当前导出 5 份文件：

1. `opportunity_report_feed_latest.json`
   - 面向投资机会报告的 canonical feed
   - 包含 `top_events`、`macro_events`、`opportunity_buckets`

2. `industry_radar_feed_latest.json`
   - 面向投资机会雷达的 canonical feed
   - 默认暴露完整 `event_pool`
   - 同时保留 `industry -> shared_events` 兼容分组

3. `research_feed_latest.json`
   - 面向研究线程的 lookup feed
   - 包含 `recent_events`、`entity_index`、`industry_index`

4. `legacy_news_digest_latest.json`
   - 旧 `news_digest` 的最小兼容输出
   - 用于让旧 consumer 先切换到共享库输出面

5. `source_health_latest.json`
   - 当前共享新闻层的最新 source health 摘要

另有：

- `manifest_latest.json`
  - 导出批次的 manifest

## 契约边界

### 1. canonical feed 与 legacy feed 分开

- `opportunity_report_feed_latest.json`
- `industry_radar_feed_latest.json`
- `research_feed_latest.json`

这三份是 Layer 3 的 canonical consumer feed。

`legacy_news_digest_latest.json` 只是过渡层，不是长期 source-of-truth。

### 2. 下游不应再重做共享层工作

下游可以做轻量调权，但不应再重复：

- 抓取
- article normalize
- article 去重
- article -> event merge
- shared ranking

### 3. Layer 3 不承诺补齐所有旧字段语义

当前 `legacy_news_digest_latest.json` 的定位是：

- 结构兼容优先
- 共享层已有内容优先
- 旧系统独占字段先留空或最小占位

例如当前：

- `investor_views`
- `polymarket_opportunities`

仍是占位字段，而不是由 `News Event Hub` 强行伪造的一套私有逻辑。

## 投资机会报告契约

建议优先读取：

- `opportunity_report_feed_latest.json`

关键字段：

- `top_events`
- `macro_events`
- `opportunity_buckets.new_opportunity_candidates`
- `opportunity_buckets.tracking_updates`
- `opportunity_buckets.watchlist_candidates`

如果旧链路暂时还只能消费 `news_digest` 风格结构，则先读取：

- `legacy_news_digest_latest.json`

## 投资机会雷达契约

建议优先读取：

- `industry_radar_feed_latest.json`

关键字段：

- `event_pool_count`
- `event_pool`
- `persistent_window_start`
- `discovery_contract`
- `opportunity_buckets`
- `radar_views.macro_events`
- `radar_views.company_events`
- `radar_views.industry_events`
- `radar_views.institution_events`
- `industries[*].industry`
- `industries[*].shared_news_score`
- `industries[*].shared_events`

为了减少旧接口摩擦，当前还额外保留：

- `industries[*].policy_articles`

它是共享 event 的兼容投影，不再是旧 AKShare 文章聚类的原始结果。

也就是说当前这份 feed 的主语义已经不是“只按行业看新闻”，而是：

- 先把当前窗口内的共享事件完整暴露给雷达
- 再按 `macro / company / industry / institution / tracking` 等视角投影
- 最后保留 `industries[*]` 作为旧接口兼容层

## 研究线程契约

建议读取：

- `research_feed_latest.json`

关键字段：

- `recent_events`
- `persistent_window_start`
- `entity_index`
- `industry_index`
- `discovery_contract`
- `entity_profiles[*].discovery_routes`
- `industry_profiles[*].discovery_routes`
- `institution_profiles[*].discovery_routes`

这份输出的目的，是让研究线程先从共享库读取增量事件，而不是重新散抓新闻。

如果研究线程发现共享库里没有足够厚的目标对象：

- 先读 `entity_profiles[*].lookup_terms`
- 再读 `entity_profiles[*].related_queries`
- 然后按 company / industry / institution 对应 profile 里的 `discovery_routes` 走标准补抓口径

当前 `discovery_contract.route_catalog` 不再只是 source map：

- 标准 route 都会带 `entrypoint`
- 标准 route 都会带 `is_executable = true`
- 下游可以直接复用共享 discovery runner，而不是再单独实现私有补抓逻辑

当前 `persistent_window_start` 的保留口径来自：

- `config/consumer_export_policy_v1.json`

## 运行与刷新

当前 Layer 3 导出由：

- `scripts/export_consumer_views.py`

负责生成。

在 `private runtime` 上，使用：

- `unified-news-consumer-views.service`
- `unified-news-consumer-views.timer`

定时刷新。

## 当前仍然保留的边界

以下内容仍然不属于当前 Layer 3 MVP：

- 研究线程的标准化回写接口
- 投资机会报告对共享 feed 的所有 legacy fallback 下线
- 行业雷达对共享 feed 的所有 legacy fallback 下线
- 所有旧接口的完全下线

这一步先解决的是：`共享库已经可被消费`。
