# Layer 2 Ranking Contract V1

## 目的

这份文档把 `Layer 2` 从“shared ranking MVP”正式收敛为：

`evidence fusion + event state machine + score vector + view-specific ranking contract`

它回答的问题不是“学一个共享分数”，而是：

- 共享层如何融合 `fact` 与 `signal` 两条证据赛道
- 共享层如何定义 `event` 的状态与生命周期
- 共享层应向多个 consumer 输出什么样的稳定 contract
- 哪些排序属于共享层，哪些排序应留给下游

## 一句话定义

`Layer 2` 不是单一 ranker，而是一个以 `event` 为中心的共享契约层。

它的职责是：

- 融合 article 级证据
- 管理 event 粒度与 event 状态
- 输出多轴 score / flags / counters
- 为 global feed、research retrieval、radar 等视图提供可复用的基础 ranking contract

## 服务对象

Layer 2 面向的不是终端读者，而是下游消费系统与研究流程：

- `industry_signal_radar`
- `investment_report` / 日报周报链路
- 研究线程 / company deep dive / object research
- 后续新增的共享新闻 consumer

## 设计原则

### 1. `event` 是共享对象，不是 `article`

共享层回答的是：

- 今天发生了什么变化
- 这件事被确认到什么程度
- 它和哪些对象、行业、主题相关
- 它是否值得继续研究

而不是“哪篇文章更热”。

### 2. `fact lane` 与 `signal lane` 分赛道建模

两条 lane 都进入共享层，但不应用一套文章排序逻辑处理：

- `fact lane` 更像证据质量评估
- `signal lane` 更像早期发现价值评估

### 3. 共享层输出 contract，不输出终局审美

共享层应提供：

- 默认可用、稳定、可解释的基础排序
- 供下游复用的 shared scores / flags / counters

共享层不应替某个单一 consumer 写死最终 feed 审美。

### 4. `coverage` 只能辅助，不能主导

传播广度可以帮助判断：

- 确认程度
- 超额关注度

但不能直接等价于“重要性”。

### 5. global feed 与 research retrieval 目标函数不同

- `global feed` 回答“全市场今天先看什么”
- `research retrieval` 回答“研究某个对象时，怎么把相关材料尽量找全并找准”

两者必须独立设计。

## Layer 2 的核心对象

### A. Topic

`topic` 是持续存在的主题或主线。

例如：

- 关税
- OPEC
- AI capex
- 中东地缘

它不是直接消费对象，而是长周期归类对象。

### B. Event

`event` 是离散发生、可研究、可排序的变化点。

例如：

- 某公司宣布回购
- 某项关税措施正式落地
- 某并购交易获得确认

`event` 是共享层的最小消费对象。

### C. Update

`update` 是围绕同一 event 的新增证据或新增子事实。

例如：

- 传闻出现
- 公告确认
- 新增金额细节
- 被公司否认

`update` 用于承载“同一事件上的新进展”，避免把持续主题无限吸成一个大 event。

## Event State Machine V1

共享层不只给分数，还要显式维护状态。

建议先采用五态：

- `watch`
  - signal-only，值得观察，但尚未进入强确认语义层
- `emerging`
  - 已有初步 fact evidence，或多源 signal 开始共振
- `confirmed`
  - 已有较强独立事实确认
- `contested`
  - 证据冲突，或确认与否认并存
- `mature`
  - 事件已成熟，新增信息边际价值下降

补充：

- `closed` 仍可保留为终止态，但不一定作为默认活跃态之一

## Lane-Specific Evidence Ranking

### 1. Facts Lane Evidence Ranking

Facts lane 评的是“证据质量”，不是“被转了多少次”。

主要维度：

- `source_trust`
- `officialness`
- `originality`
- `specificity`
- `entity_mapping_confidence`
- `extraction_completeness`
- `contradiction_risk`
- `recency`

核心规则：

- `confirmation_count` 不应按 article 数算
- 应按 `independent evidence units` 算
- 同一传播链应做 `source family collapse`

### 2. Signal Lane Evidence Ranking

Signal lane 评的是“早期发现的期望价值”，不是“像不像次级事实”。

主要维度：

- `entity_match_strength`
- `specificity`
- `novelty`
- `lead_time_bonus`
- `cross_post_resonance`
- `noise_cost`
- `likely_confirmation_in_T`

signal 的价值更接近：

`p(confirm in T) * expected_entity_impact * lead_time_bonus - noise_cost`

因此 signal lane 更适合用延迟标签校验：

- `24h / 72h / 168h` 内是否获得 fact confirmation
- 提前量多大
- false positive 成本多高

## Shared Event Contract

Layer 2 对外的 event contract 建议至少包含以下部分。

### 1. Identity

- `event_id`
- `event_type`
- `event_state`
- `topic_set`
- `entity_set`
- `first_seen_at`
- `last_seen_at`

### 2. Score Vector

共享层不只输出一个总分，而应输出多轴向量：

- `market_significance`
- `entity_impact`
- `confirmation`
- `novelty`
- `researchability`
- `coverage_independent`
- `coverage_residual`
- `urgency`
- `uncertainty`

说明：

- `market_significance`
  - 这件事对全市场的整体重要性
- `entity_impact`
  - 这件事对相关公司 / 行业 / 主题的局部冲击
- `coverage_independent`
  - 去重后的独立证据广度
- `coverage_residual`
  - 相对预期 coverage 基线的超额关注度

### 3. Flags

- `signal_only`
- `mixed_evidence`
- `official_source_present`
- `structural_event`
- `ongoing_topic`
- `contested`
- `undercovered_entity`
- `high_local_impact`

### 4. Counters

- `article_count_raw`
- `independent_evidence_count`
- `source_family_count`
- `signal_platform_count`

### 5. Ranking Fields

共享层需要显式区分：

- `event_rank_score`
  - 默认共享排序分
- `calibrated_confirmation`
  - 单独校准过的确认轴
- `uncertainty`
  - 单独表达不确定性

不要拿 raw rank score 冒充确认度。

## View-Specific Ranking Contract

### 1. Global Feed

目标：

- 今天全市场先看什么

偏好：

- `market_significance`
- `confirmation`
- `novelty`
- `researchability`

策略：

- `signal-only` 事件可以进入，但以 `watch/emerging` 小 quota 混入
- 不与 `confirmed` 事件同权混排

### 2. Research Retrieval

目标：

- 研究某个对象时，把相关材料尽量找全并尽量找准

偏好：

- `entity_impact`
- `entity_match_strength`
- `specificity`
- `novelty`
- `evidence completeness`

策略：

- 独立于 global feed 设计
- 支持 `exact match + alias/ticker match + semantic retrieval` 的 hybrid
- 支持 `event view + article view + within-event evidence ordering`

### 3. Radar / Theme Views

目标：

- 哪个行业 / 主题值得打开看

偏好：

- `entity_impact`
- `topic relevance`
- `confirmation`
- `novelty`

策略：

- 允许对 `signal-only` / `emerging` 给更高权重
- 但仍基于共享层输出的多轴 contract，而不是下游自建新闻理解

## Candidate Gating

Shared Event Ranking 不应一上来把全部 event 直接混排。

建议先做 candidate gating：

- `confirmed structural events`
- `high-entity-impact emerging events`
- `limited-quota watch events`
- `contested but high-significance events`

再在 bucket 内排序，并以 blend policy 输出最终 feed。

这样可以避免：

- 宏观热门主题无限占位
- signal-only 事件同权污染
- “visibility floor” 被误用成所有结构性事件强上首页

## Within-Event Evidence Ordering

Layer 2 还应显式支持 event 内证据排序。

研究场景点开 event 后，最先看到哪条 evidence，也是一套独立排序。

建议优先级：

- `official / direct evidence first`
- `original source first`
- `highest specificity first`
- `newest non-redundant update first`

## 当前阶段最先要冻结的东西

在进入 learned ranking 之前，建议先冻结以下 contract：

1. `topic / event / update` 的粒度边界
2. `event_type`
3. `event_state`
4. `independent evidence` 的计数口径
5. `score vector / flags / counters` 输出口径

如果这些对象还不稳，learned ranker 很容易学到错误代理变量。

## 推进顺序建议

### Phase A. Contract Freeze

- 冻结 `event granularity`
- 冻结 `event state machine`
- 冻结 `score vector + flags + counters`

### Phase B. Evidence Fusion

- 做 `source family collapse`
- 做 `independent evidence counting`
- 明确 `signal -> emerging -> confirmed` 的状态推进条件

### Phase C. Retrieval Split

- 单独建设 `entity-first research retrieval`
- 不再让 research retrieval 直接复用 global feed 排序

### Phase D. Learned Ranking

- 在 contract 稳定后再引入 learned ranker
- 优先学 lane-specific evidence ranking，再学 shared event blend

## 当前结论

Layer 2 的核心不是“学一个更聪明的 shared score”，而是：

- 用 `event` 承载共享对象
- 用 `evidence fusion` 承载多源证据
- 用 `event state` 管理不确定性
- 用 `score vector + flags + counters` 为多个 consumer 提供可复用 contract
- 用 `view-specific ranking` 区分 global feed、radar、research retrieval

换句话说：

`Layer 2` 不是一个 ranker；它是一个 `ranking contract`。
