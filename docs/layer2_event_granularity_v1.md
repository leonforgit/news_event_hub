# Layer 2 Event Granularity V1

## 目的

这份文档把 `topic / event / update` 的边界冻结下来，避免后续 ranking、state machine 和 retrieval 建立在模糊粒度上。

它回答三个问题：

1. 什么属于 `topic`
2. 什么属于 `event`
3. 什么属于 `update`

## 一句话结论

- `topic` 是持续存在的主题容器
- `event` 是共享层的最小消费对象
- `update` 是围绕同一 event 的新增证据或新增子事实

当前系统先稳定：

- `topic` 作为归类键存在
- `event` 作为共享排序对象存在
- `update` 先作为 Layer 2 内部语义对象存在，不单独建表

## 1. Topic

`topic` 是持续存在、可以跨多个 event 延续的主题。

它回答的是：

- 这件事长期属于哪条主线
- 不同时间发生的多个 event 是否属于同一长期主题

例如：

- `macro:trade_tariff`
- `macro:middle_east_geopolitics`
- `industry:semiconductor`
- `company:pop_mart`

### Topic 的作用

- 做长期归类
- 做 research retrieval 的上层召回
- 防止把长期主题误当成单一 event

### Topic 当前不做什么

- 不直接参与下游消费排序
- 不作为首页 feed 的最小对象
- 不承担“今天发生了什么”的表达

## 2. Event

`event` 是一段时间内围绕同一个变化点、可被研究和排序的最小对象。

它回答的是：

- 到底发生了哪件具体变化
- 这件变化和哪些对象相关
- 它值不值得被共享层优先消费

### Event 的判定边界

至少同时满足以下多数条件时，才属于同一个 event：

- 同一对象或同一核心主题
- 同一动作
- 同一时间窗口
- 同一研究含义

### 应拆开的典型情况

- `政策发布` 与 `政策解读`
- `并购传闻` 与 `交易终止`
- `回购计划公告` 与 `回购执行完成`
- `季度预告` 与 `正式业绩披露`
- `今天的新变化` 与 `背景复述`

## 3. Update

`update` 是围绕同一 event 的新增证据、状态推进或新增子事实。

它回答的是：

- 同一事件上这次新增了什么
- 是不是带来了状态变化
- 这是不是新的 confirmation / contradiction / detail

例如：

- 先有传闻，后有公告确认
- 先有 headline，后补金额 / 对手方 / 日期
- 先有初步消息，后被否认

### 当前实现口径

在 V1 阶段，`update` 先不单独建表。

当前先由以下机制承载：

- `article_event_links`
- `event_state`
- `first_seen_at / last_seen_at`
- `novelty_state`
- `supporting_articles`

也就是说：

- `update` 已是定义层对象
- 但还不是独立持久化表

## 当前系统的最小冻结口径

### Topic Key

共享层先为每个 event 写一个 `topic_key`，用于稳定表达“这件事属于哪条长期主线”。

当前建议：

- 有 `primary_entity` 时：
  - `company:<slug>`
- 否则有 `primary_industry` 时：
  - `industry:<slug>`
- 否则有 `macro_theme` 时：
  - `macro:<slug>`
- 否则退化为：
  - `event_type:<slug>`

### Event Key

`event_id` 仍然由当前 merge-key 驱动，代表离散 event 身份。

### Update Boundary

V1 暂不引入独立 `update_id`。

当前更新语义以：

- 新 evidence 进入 event
- `event_state` 推进
- `last_seen_at` 更新

来表达。

## 为什么先这样做

这样可以先解决两个最现实的问题：

1. 避免把长期主题无限吸成一个大 event
2. 避免为了引入 update 概念而过早把 Layer 2 schema 复杂化

## 下一阶段再做什么

当以下能力成熟后，再考虑把 `update` 单独 materialize：

- `event_state` 已稳定
- `independent evidence counting` 已稳定
- `within-event evidence ordering` 已稳定
- research retrieval 开始需要显式按更新流消费

## 当前结论

V1 的冻结口径是：

- `topic`：长期主线容器
- `event`：共享层最小消费对象
- `update`：同一 event 上的新增证据 / 状态推进，先不单独建表

因此后续 ranking、retrieval、state machine 都应建立在这个边界之上，而不再把三者混为一谈。
