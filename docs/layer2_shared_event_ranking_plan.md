# Layer 2 Shared Event & Ranking Plan

## 这一层是什么

Layer 2 是 `News Event Hub` 的共享中间层，也是当前工作区的核心主线。

它不只是一个“排序函数”，而是一个 `ranking contract` 层：

- `evidence fusion`
- `article -> event` 归并
- `event state machine`
- `score vector / flags / counters`
- 面向多个下游的共享视图契约

## 为什么这一层最关键

如果没有这一层：

- 同一件事会被多篇文章重复顶上来
- 官方确认与传闻会混成文章热度
- 不同下游会各自重写一套 ranking 逻辑

所以真正要共享的不是“文章库”，而是“事件理解层”。

## 这一层当前的核心问题

### 1. 什么是 event

V1 需要先定义：

- 一个对象
- 一个动作
- 一个时间点附近
- 一个研究含义

### 2. article 怎么归并成 event

同一对象、同一动作、同一时间窗口、同一研究动作的多篇文章，应优先归并。

### 3. event 上沉淀哪些共享 feature / state / counters

V1 至少应包括：

- 新旧程度
- 确认度
- 来源结构
- 对象映射
- 是否具备研究动作价值
- 事件状态
- 独立证据计数
- 不确定性表达

### 4. 哪些 ranking 逻辑应放共享层

共享层应产出通用 feature、基础排序与 view-specific ranking contract，不应让每个 consumer 都重做一遍“新闻理解”。

## 当前建议的 V1 范围

当前 `event v1` 的正式定义见：

- [event_v1_definition.md](docs/event_v1_definition.md)
- [layer2_event_granularity_v1.md](docs/layer2_event_granularity_v1.md)
- [article_to_event_merge_rules_v1.md](docs/article_to_event_merge_rules_v1.md)
- [shared_ranking_features_v1.md](docs/shared_ranking_features_v1.md)
- [layer2_ranking_contract_v1.md](docs/layer2_ranking_contract_v1.md)
- [layer2_independent_evidence_v1.md](docs/layer2_independent_evidence_v1.md)
- [layer2_event_state_machine_v1.md](docs/layer2_event_state_machine_v1.md)

### Event Object

- `event_id`
- `event_type`
- `event_title`
- `first_seen_at`
- `last_seen_at`
- `novelty_state`
- `confirmation_count`
- `source_mix`
- `primary_entity`
- `primary_industry`
- `opportunity_state`

### Shared Features

- `freshness`
- `confirmation_strength`
- `lane_mix`
- `entity_relevance`
- `investability_hint`
- `followup_actionability`

### Shared Ranking Output

- 基础 `event_rank_score`
- 单独校准的 `confirmation / uncertainty`
- `score vector`
- `flags`
- `counters`
- 供下游覆盖但不重造的共享特征层

## 当前阶段目标

这一层当前目标不是立刻写复杂算法，而是先把对象、状态、计数口径与 contract 定义对。

## 长期扩展：慢变量趋势信号

这不是当前迭代主任务，但属于 `Layer 2` 的长期扩展方向。

后续随着 `event + mapping + point-in-time history` 稳定，Layer 2 应进一步支持：

- 识别某类事件在较长时间窗内的缓慢累积
- 识别“当前不热，但频率持续抬升”的主题或对象信号
- 从离散 `event` 之上派生 `trend candidate`

这个方向当前先不进入实现主线，原因是它依赖：

- 更稳的 `event granularity`
- 更稳的 `mapping layer`
- 更清晰的 `dated export / as-of semantics`

所以短期顺序仍是：

1. 先把 `event / mapping / opportunity / export` 收稳
2. 再做长期趋势识别

## 近期 checklist

- [x] 明确 Layer 2 是共享中间层，而不只是排序函数
- [x] 明确 `event` 不是 `article`
- [x] 明确下一阶段真正排序对象应该是 `event`
- [x] 收敛 `event v1` 的正式定义
- [x] 收敛 `article -> event` 的归并规则
- [x] 收敛 `event_type` 的第一版枚举
- [x] 收敛共享 feature 列表
- [x] 区分共享 ranking 与 consumer-specific 调权边界
- [x] 设计第一版 event 视图 / adapter 输出
- [x] 在 `private runtime` 跑通第一版 Layer 2 event build 与 ranking write-back
- [x] 把 Layer 2 正式定义为 `ranking contract`
- [x] 引入 `event state machine + score vector + flags + counters` 口径
- [x] 把 `event_state / score_vector / counters` 的第一批字段接入 schema、builder 与 consumer export
- [x] 冻结 `topic / event / update` 的粒度边界
- [x] 冻结 `event_state machine`
- [x] 为 `event` 写入第一版 `topic_key`
- [x] 冻结 `independent evidence counting` 口径
- [x] 在 consumer export 层将 global feed 与 research retrieval 的 ranking contract 显式拆开
- [x] 在 consumer export 层接入 `within-event evidence ordering`
- [x] 在 `research_feed` 中接入第一版 `entity-first retrieval + evidence bundle`
- [x] 在 builder 中接入第一版 `entity alias / ticker mapping`
- [x] 在 builder 中接入第一版 `entity context signature` 跨语言 merge
- [x] 收紧 company entity extraction，并在 rebuild 中清洗 legacy `event_entity_links`
- [x] 为 `research_feed.entity_profiles` 增加 research-specific company gate 与 `lookup_terms`
- [x] 为英文娱乐/会展 PR 噪音补充 `research company profile` 过滤样例与 smoke
- [x] 为 `Foundation / Association / University` 这类非公司机构补充 `research company profile` 过滤样例与 smoke
- [x] 为 shared event 导出补上 `update_count / latest_update_signature / recent_updates`
- [x] 为 shared ranking 接入第一版 `micro_event_protected / macro_coverage_capped` coverage 校准
- [x] 为 `research_feed` 补上 `timeline / topic_slices / related_queries / entity_query_index`
- [x] 为 `score_vector` 补上 `entity_local_priority`
- [x] 为 `research_feed` 补上 `topic_profiles`
- [x] 将 `entity_query_index` 收敛为 normalized lookup key，并让 topic key 也可回路由

## 第二层完成标志

至少满足：

1. 共享层能稳定产出 `event`
2. 同一事件不会被多篇文章重复占位
3. 事件能映射到行业、个股、主题或宏观主线
4. 下游开始消费 shared event / ranking contract，而不是直接消费 article 热度
