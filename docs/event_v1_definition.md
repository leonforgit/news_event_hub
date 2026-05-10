# Event V1 Definition

## 目的

这份文档是 `News Event Hub` 的 `event v1` 正式定义。

它回答四个问题：

1. `event` 到底是什么
2. `article` 什么时候应归并到同一个 `event`
3. `event` 上要沉淀哪些共享字段和共享 feature
4. `event` 在 v1 明确不解决什么问题

## 一句话定义

`event` = `一段时间内，围绕同一个变化点的、可被研究和排序的最小事件对象`

它不是文章，也不是长期主题，更不是下游日报里的一条展示文案。

## Event 与 Article 的边界

### Article

`article` 是单条新闻载体。

例如：

- 一篇 Reuters
- 一条财联社快讯
- 一条 gov.cn 新闻
- 一篇 SEC / 交易所公告

### Event

`event` 是多条 article 背后指向的同一个变化。

例如：

- 美联储发布某项新监管动作
- 某公司宣布回购
- 某政策正式发布
- 某并购传闻被确认或否认

## V1 粒度原则

V1 的 `event` 粒度先定为：

- 一个对象
- 一个动作
- 一个时间点附近
- 一个研究含义

这意味着：

- 不要把事件做成长期大主题
- 不要把纯背景解释也当成新事件
- 不要把研究意义不同的内容硬并在一起

## 正例

以下内容通常应视为同一个 event：

- 同一家公司宣布回购，Reuters、财联社、公告分别报道
- 同一政策由政府网先发、媒体后续确认和补细节
- 同一并购传闻先出现、后续被公司正式确认或否认

## 反例

以下内容通常不应强行并成一个 event：

- `政策发布` 与 `政策解读`
- `并购传闻` 与 `业绩暴雷`
- `回购计划公告` 与 `回购实施完成`
- `今天新增变化` 与 `多年历史背景回顾`

## Event 的判定锚点

V1 归并时优先看四个锚点：

1. `对象锚点`
   - 是否指向同一个公司、行业、主题或宏观对象
2. `动作锚点`
   - 是否描述同一个变化动作
3. `时间锚点`
   - 是否处在同一个事件时间窗口
4. `研究锚点`
   - 是否对应同一个研究动作或投资含义

四个锚点一致度高时，应优先归并。

## Article -> Event 归并规则

### 应优先归并

满足以下多数条件时，优先归并到同一个 `event`：

- 同一对象
- 同一动作
- 发布时间接近
- 新增信息属于同一事件进展
- 对下游研究动作的指向相同

### 应拆开

出现以下情况时，应优先拆成不同 `event`：

- 对象不同
- 动作不同
- 时间已经跨到一个新阶段
- 研究意义已经变化
- 一条是新增事实，一条只是背景复述

### 传闻与确认的处理

V1 的默认处理不是“传闻和确认一定拆开”，而是：

- 如果它们指向同一对象、同一动作、同一时间窗口
- 则可以属于同一个 `event`
- 但要在事件内部通过 `source_mix`、`confirmation_count`、`novelty_state` 体现状态变化

也就是说：

- `event` 负责承载“同一变化”
- `lane` 和确认度负责承载“这件事当前被确认到什么程度”

## Event 生命周期

V1 先采用四态：

- `new`
- `developing`
- `stale`
- `closed`

### new

第一次形成事件，且仍属于新增变化。

### developing

事件已有后续确认、补细节或状态推进。

### stale

事件没有新的增量变化，更多进入历史尾部。

### closed

事件已完成、被证伪，或不再值得继续追踪。

## Event V1 核心字段

V1 至少应稳定维护以下字段：

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

## 字段解释

### first_seen_at

该事件在共享层第一次被看到的时间。

### last_seen_at

该事件最近一次出现新增 article 或新增状态推进的时间。

### confirmation_count

这里不应简单理解为“文章数”，而应更接近：

- 独立确认源数量
- 或独立 confirmation evidence 数量

它的作用是衡量“这件事被确认到什么程度”，而不是衡量媒体转载量。

### source_mix

建议表达为：

```json
{"confirmation": 3, "signal": 1}
```

它的意义是告诉下游：

- 这个事件现在主要由哪条 lane 支撑
- 是只有 signal，还是 confirmation 已经进来

## Event Type V1

V1 不求一次性穷尽，但建议先收敛到一版小枚举：

- `policy`
- `regulation`
- `company_action`
- `earnings_guidance`
- `deal_mna`
- `financing_capital`
- `production_supply`
- `contract_order`
- `macro_data`
- `geopolitics_trade`
- `commodity_disruption`
- `social_signal`

原则是：

- 优先按“研究动作和投资含义”分
- 不优先按媒体栏目名分

## Shared Feature V1

event 上建议沉淀的共享 feature 至少包括：

- `freshness`
- `delta_strength`
- `confirmation_strength`
- `lane_mix`
- `specificity`
- `entity_relevance`
- `researchability`
- `investability_hint`

## 与 Ranking 的关系

V1 的核心原则是：

- `article` 只做基础清洗和预排序
- `event` 才是共享 ranking 的主对象

因为真正该回答的问题是：

- 今天新发生了什么
- 这件事被确认到什么程度
- 它能映射到哪个研究对象
- 它是否值得现在继续跟进

这些都更适合挂在 `event` 上，而不是单篇 article 上。

## V1 不解决什么

为了控制范围，event v1 明确不追求：

- 多层级父子事件树
- 长期叙事主题图谱
- 完整自动化的跨语言语义聚类
- 完整无人工兜底的复杂事件拆并
- 机会层的最终投资结论

V1 的目标不是“做最强事件知识图谱”，而是先做出：

- 可稳定使用
- 可被多个下游共享
- 能明显优于 article 直排

的中间层。

## 当前结论

`event v1` 的本质不是“新闻汇总卡片”，而是共享层的最小研究对象。

只有把这一层定义清楚，后面的 ranking 和 consumer integration 才不会继续分散化。
