# Current System Audit

## 结论先行

当前 `Investment` 工作区里，新闻处理并不是一套共享底座，而是至少两条半独立链路：

1. `投资机会报告` 自己抓新闻、自己做 signals、自己生成 digest
2. `industry_signal_radar` 自己抓新闻、自己做行业 overlay
3. 研究过程中还存在潜在的定向抓取需求，但当前没有标准回写路径

这正是需要建立 `News Event Hub` 的原因。

## 机会报告链路

### 当前入口

- `scripts/run_investment_reporting_pipeline.py`
- `scripts/refresh_market_news.py`
- `scripts/analyze_market_news.py`
- `scripts/generate_investment_daily_pdf_report.py`

### 现有资产

- 已有 `investment_tracker.db`
- 已有 `news_articles`
- 已有 `news_signals`
- 已有 `news_digest`
- source catalog 覆盖较广

### 当前问题

- 更像“日报特化新闻链路”，不是共享底座
- 某些 root-level `macro_news` 会覆盖较新的 digest 宏观选择
- 排名会把“像新闻的事件”抬起来，但不一定有投资价值

## 行业雷达链路

### 当前入口

- `量化/industry_signal_radar/scripts/radar_news_policy.py`
- `量化/industry_signal_radar/scripts/radar_scan_runner.py`

### 现有资产

- 已在 `private runtime` 跑日更
- 已对接若干 `AKShare` 新闻源
- 已有行业关键词与公司名映射
- 已有 `policy_articles` 聚类与 source health
- 已有自己的 SQLite 运行库

### 当前问题

- 新闻文章并没有沉淀成共享 article/event 层
- 目前主要只为行业雷达自己服务
- 私有运行库更偏 snapshot / alert，不适合作为共享新闻底座直接扩展

## 当前运行时观察

### 机会报告侧

- `investment_tracker.db` 里已存在数千条 `news_articles`
- 也存在大量 `news_signals`
- 说明“新闻入库”并不是从零开始

### 报告输出侧

- 当前 digest 中仍会出现不符合目标的公司新闻
- 这说明问题不只在抓取，还在排序与展示规则

## 已确认的问题类型

### 1. Source duplication

- 各下游自己维护抓取链路
- 同一类新闻可能重复采集、重复解析、重复打标签

### 2. Ranking mismatch

- 旧背景材料会混入宏观主线
- 噪音公司新闻会进入重点新闻

### 3. No shared write-back path

- 研究过程中的定向抓取没有统一回写路径
- 即使抓到高价值内容，也容易只留在局部工作区

## 已确认的正确方向

- 在 `private runtime` 上建立共享 `news_event.db`
- 行业雷达承担 baseline 公共新闻采集
- 日报改为消费共享库
- 研究过程中的定向抓取统一回写共享库
- 排名从文章升级到事件层
