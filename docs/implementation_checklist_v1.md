# News Event Hub Implementation Checklist V1

这份文档是当前主线的动态 checklist。

目标不是记录所有想法，而是记录“还没有完成、且会继续被逐条 check 掉”的实现项。

## 当前主线

- [x] 顶层三层动态规划已经明确
- [x] `Hub` 内部六层职责模型已经明确
- [x] Layer 1 / Layer 2 / Layer 3 最小可用已落地
- [x] Mapping Layer field contract 第一版真正落地到 schema / builder / export
- [x] Opportunity Transition contract 第一版真正落地到 schema / export
- [x] dated / as-of export 第一版落地
- [x] point-in-time `entity-day / industry-day` panel 第一版落地
- [x] point-in-time panel 已与 top-N consumer truncation 解耦，改为基于 full lookback window 构建
- [x] Layer 2 granularity / mapping / retrieval 第一轮稳定化已落地
- [x] runtime verification summary 已与当前 export contract 对齐

## Phase 1: Mapping Layer

- [x] 给 `event_entity_links` 增加：
  - `mapping_reason`
  - `mapping_confidence`
  - `mapping_version`
  - `mapping_source`
- [x] builder 在写入 `event_entity_links` 时，开始写出上述字段
- [x] consumer export 开始透出 mapping contract 字段
- [x] 建立 `unresolved_event_mappings` queue
- [x] 对“无高置信映射”的事件开始进入 unresolved queue

## Phase 2: Opportunity Transition

- [x] 给 `opportunity_signals` 补齐：
  - `opportunity_type`
  - `opportunity_bucket`
- [x] 在 shared export 中开始输出：
  - `opportunity_type`
  - `opportunity_bucket`
  - `thesis_impact`
  - `followup_path`
  - `portfolio_relevance`
  - `watchlist_relevance`
- [x] 固定第一版 `event -> opportunity candidate` 派生规则

## Phase 3: Point-in-time Export

- [x] 每次 export 除 `latest` 外，额外写 dated snapshot
- [x] 所有导出明确写出 `as_of`
- [x] 所有导出明确写出 `window_start`
- [x] 第一版 `entity-day panel`
- [x] 第一版 `industry-day panel`
- [x] point-in-time panel 不再复用 top-N consumer subset，而是直接读取 full lookback window

## Phase 4: 第一轮稳定化

- [x] `event granularity` 第一轮稳定化
  - 新增 `granularity_class`
  - point-in-time panel 已开始按 granularity 汇总
- [x] 英文长尾实体误识别第一轮收紧
  - `research / point-in-time` 视图已共用更严格的 company gate
- [x] mapping confidence / unresolved review 第一轮收紧
  - 已新增 `mapping_review_latest.json`
  - 已把 unresolved queue 与低置信映射导出成 review surface
- [x] research retrieval 稳定性第一轮提升
  - point-in-time panel 已与 top-N consumer 截断解耦
  - `entity-day / industry-day` 已进入 shared export

## Runtime Discipline

- [x] `check_runtime_news_runtime.sh` 已对齐当前 export filenames 与 source health 结构

## 长期规划说明

以下方向已明确，但不放入当前“逐项 check 掉”的执行 checklist：

- 长期趋势信号识别
  - 基于历史 `event + mapping + point-in-time history`
  - 识别“当前尚未高热度、但频率在缓慢抬升”的对象 / 行业 / 主题信号
  - 当前排在 `Mapping / Opportunity / point-in-time export` 稳定之后
