---
codex_output: true
codex_output_category: "source-review"
codex_output_entity: "AkShare"
codex_output_title: "AkShare 可接入源评估（2026-04-12）"
---

# AkShare 可接入源评估

日期：`2026-04-12`

## 1. 结论先行

AkShare 适合作为 `兼容聚合层`，不适合作为我们定义 canonical source 的唯一依据。

对 `news_event_hub` 来说，当前最值得继续吸收的不是“所有新闻相关函数”，而是少数满足以下条件的 feed：

- 能稳定返回最近增量
- 有明确发布时间
- 最好有原文链接
- 适合落到 `article/event` 共享层，而不是只产生情绪分数或日历提醒

基于官方文档、当前安装版本源码检查、以及 `2026-04-12` 本地实抓，建议分成三档：

### 建议优先评估接入

- `stock_info_global_ths`
- `stock_info_global_futu`
- `stock_news_main_cx`

### 适合做定向 / tracked collector，不建议直接进 baseline live path

- `stock_news_em`

### 暂不建议接入 article/event 主干

- `stock_info_global_sina`
- `stock_js_weibo_report`
- `news_report_time_baidu`
- `news_economic_baidu`

## 2. 已确认当前已接入的 AKShare 源

仓库当前已经接入并上线的 AKShare 源有四条：

- `akshare_news_cctv`
- `akshare_stock_info_global_cls`
- `akshare_stock_info_global_em`
- `akshare_stock_notice_report`

它们已经覆盖：

- `macro`：`news_cctv`
- `mixed high-frequency flash`：`stock_info_global_cls` / `stock_info_global_em`
- `company hard disclosure`：`stock_notice_report`

所以这轮评估的重点，不是重复接同类 feed，而是看还有哪些 `source family` 值得补进来。

## 3. 候选源判断

| 接口 | 判断 | 适合落点 | 原因 | 主要问题 |
| --- | --- | --- | --- | --- |
| `stock_info_global_ths` | `推荐` | `confirmation lane`, `baseline high_freq` | 有 `标题 / 内容 / 发布时间 / 链接`，结构完整；和现有 `cls/em` 同类，接线成本低 | 与 `em/cls` 有明显重复，需单独标 `source_family` 并依赖 event merge 去重 |
| `stock_info_global_futu` | `推荐` | `confirmation lane`, `baseline high_freq` | 有 `标题 / 内容 / 发布时间 / 链接`，接口稳定，当前样本里既有重复也有增量 | 海外平台口径，部分内容可能与其他快讯源交叉转述 |
| `stock_news_main_cx` | `推荐` | `confirmation lane`, `daily/high_freq hybrid` | 财新质量高；原始响应里有 `title / summary / url / time / labels`，适合做高质量补充源 | AKShare wrapper 丢掉了 `time` 与 `labels`，更适合直连财新接口而不是完全照抄 wrapper |
| `stock_news_em(symbol)` | `条件推荐` | `tracked company collector` | 单个股票的最近新闻很适合 watchlist / entity backfill | 不是 baseline feed；按股票遍历会放大请求量与重复率 |
| `stock_info_global_sina` | `低优先` | 如接入也应仅作补充 | 当前样本有一定独特性，请求也简单 | 只有 `时间 / 内容`，没有链接；证据回溯与去重都偏弱 |
| `stock_js_weibo_report` | `不建议` | 最多做 sidecar signal feature | 输出是 `name / rate`，本质是舆情聚合分数 | 不是 article，不适合进入共享 article/event 主干 |
| `news_report_time_baidu` | `不建议` | 日历 sidecar | 财报日历本身有价值 | 当前实抓需要 cookie，且它是 `calendar` 不是新闻 feed |
| `news_economic_baidu` | `不建议` | 日历 sidecar | 宏观日历本身有价值 | 当前实抓需要 cookie，且不是 article/event 证据 |

## 4. 这轮实抓里最有价值的发现

### 4.1 `stock_info_global_ths` 是最顺手的下一条

它当前直接返回：

- `标题`
- `内容`
- `发布时间`
- `链接`

而且数据形态和现有 `akshare_stock_info_global_em` 很接近，意味着：

- collector 代码可以直接复用现有 `akshare_*` parser 模式
- registry 中也容易表达成新的 `source_family`
- 比接一个需要 cookies 或二次抓正文的源更快落地

如果要在 AKShare 里挑一条“最像现在就能接”的源，我会先选它。

### 4.2 `stock_info_global_futu` 也值得接，但优先级略低于 THS

它的结构同样完整，而且样本里有一些 `em/ths/cls` 没完全覆盖到的条目。

但它和其他全球快讯源的传播链重合也比较明显，所以更像：

- `coverage expansion`
- 不是 `new fact family`

换句话说，它能补 coverage，但不会像 `公告 / 官方披露 / 高质量独家媒体` 那样显著提升事件确认强度。

### 4.3 `stock_news_main_cx` 很有价值，但不建议按“AKShare 普通快讯源”方式接

这条源的原始响应里实际有：

- `title`
- `summary`
- `url`
- `time`
- `labels`

其中 `labels` 对 entity mapping 很有帮助。

但当前 AKShare wrapper 只保留了：

- `tag`
- `summary`
- `url`

这意味着如果我们真要接它，比较合理的做法不是简单加一个 `akshare_stock_news_main_cx`，而是：

- 把它当作 `Caixin direct-compatible feed`
- 直接请求财新的公开 JSON 接口
- 保留 `time` 和 `labels`

否则会平白损失一批对 event build 很有价值的结构字段。

### 4.4 `stock_news_em` 更像 tracked company source，不像 baseline source

它按股票代码返回最近新闻，适合：

- watchlist 公司扩展证据
- entity profile 回填
- 某家公司出现结构性事件后的后续追踪

不适合：

- 当成统一 live baseline feed 去全市场轮询

因为那会让抓取量、重复率、以及公司覆盖选择偏差都一起放大。

## 5. 与当前架构的映射建议

### A. 适合进入共享 live collector

优先顺序建议：

1. `stock_info_global_ths`
2. `stock_info_global_futu`

建议口径：

- lane: `confirmation`
- scheduler_class: `high_freq`
- coverage_scope: `mixed`
- source_type: `api`

并且一定要补独立 `source_family`，不要并进已有 `wire:cls` 或 `media:eastmoney`。

### B. 适合进入“高质量补充源”而不是普通快讯层

- `stock_news_main_cx`

建议口径：

- lane: `confirmation`
- coverage_scope: `mixed`
- scheduler_class: `daily` 或较低频 `high_freq`
- 实现上优先直连原接口，少依赖 AKShare wrapper 裁剪后的字段

### C. 适合 tracked / on-demand collector

- `stock_news_em`

建议口径：

- 不放进 baseline catalog
- 只对 tracked symbols / canonical entities 拉取
- 更适合服务 `entity profile`、`watchlist follow-up`、`event update expansion`

### D. 不进入共享 article/event 主干

- `stock_js_weibo_report`
- `news_report_time_baidu`
- `news_economic_baidu`

它们最多作为未来的：

- `calendar sidecar`
- `sentiment sidecar`

而不是 Layer 1 article collector。

## 6. 对现有 inventory 的直接影响

`docs/unified_news_source_inventory.md` 里目前还有三条旧兼容占位：

- `akshare_news_sina`
- `akshare_news_eastmoney`
- `akshare_news_10jqka`

这轮评估后，建议后续把它们重写成真实函数口径，而不是继续保留模糊别名：

- `akshare_news_eastmoney` -> 已由 `akshare_stock_info_global_em` 覆盖
- `akshare_news_10jqka` -> 应对应 `stock_info_global_ths`
- `akshare_news_sina` -> 如继续保留，应明确对应 `stock_info_global_sina`

这样 `source_registry`、`source_family` 和 `legacy_key` 才不会继续混淆。

## 7. 我建议的下一步

如果下一轮要真正落地，我建议按这个顺序：

1. 先接 `stock_info_global_ths`
2. 再评估是否补 `stock_info_global_futu`
3. 把 `stock_news_main_cx` 作为“直连财新接口”的单独任务
4. 把 `stock_news_em` 留到 tracked company collector 阶段

## 8. 参考

- AKShare 在线文档首页：<https://akshare.akfamily.xyz/>
- AKShare 股票数据文档：<https://akshare.akfamily.xyz/data/stock/stock.html>
- AKShare GitHub 仓库：<https://github.com/akfamily/akshare>

补充说明：

- `2026-04-12` 查询时，在线文档首页显示版本为 `1.18.55`
- 当前本地环境安装版本为 `1.18.40`
- 本文判断同时参考了官方文档、当前安装源码、以及当日本地实抓样本
