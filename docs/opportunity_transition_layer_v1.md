# Opportunity Transition Layer V1

## 目的

这份文档定义 `News Event Hub` 如何把共享 `event` 转译成下游可消费的 `opportunity candidate`。

它回答的问题是：

- 哪些事件值得进入投资机会视角
- 这些事件更适合进入哪种 consumer
- 它对 thesis 的影响应该怎样表达

## 一句话结论

`Opportunity Transition Layer` 应该放在 `News Event Hub` 内部，但只做到：

- `event -> opportunity candidate`

不做到：

- `opportunity -> final action`

它是共享解释层，不是决策系统。

## 当前已有基础

当前 schema 已有：

- `events.opportunity_state`
- `opportunity_signals`
- Layer 3 的 `opportunity_report_feed`

说明 V1 的工作不是从零设计，而是把“占位的机会层”正式收成 contract。

## 非目标

当前 V1 不负责：

- 是否开仓
- 是否加入正式持仓
- 是否写 decision gate
- 是否直接推送动作指令

这些属于下游：

- `Radar`
- `research/`
- `decision/`

## V1 输入

### 1. 共享事件输入

- `event_id`
- `event_type`
- `event_state`
- `score_vector`
- `event_rank_score`
- `event_rank_flags`
- `supporting_articles`

### 2. 映射层输入

- `event_entity_links`
- `primary_entity`
- `primary_industry`

### 3. 证据输入

- `confirmation_count`
- `independent_evidence_count`
- `signal_platform_count`
- `calibrated_confirmation`
- `uncertainty`

## V1 输出

最小机会对象建议包含：

- `opportunity_id`
- `event_id`
- `opportunity_title`
- `opportunity_type`
- `opportunity_bucket`
- `opportunity_rank`
- `portfolio_relevance`
- `watchlist_relevance`
- `thesis_impact`
- `followup_path`
- `rank_flags`

其中：

- `thesis_impact`
  - `positive`
  - `negative`
  - `neutral`
  - `unclear`

## V1 机会桶

建议先稳定成 5 类：

- `macro`
- `industry`
- `company`
- `special_situation`
- `tracking_update`

这几类足够对接：

- 每日投资机会报告
- Radar
- 对象研究线程
- watchlist 更新

## V1 升级原则

### 1. 不是所有 event 都进入 opportunity layer

共享层可以保留很多 event，但 opportunity layer 应该更保守。

优先升级的 event：

- `confirmed structural events`
- `high local impact emerging events`
- `contested but high-importance events`
- `watchlist / thesis 相关的 tracking updates`

### 2. 机会层回答“值得进一步处理”，不回答“应该立刻动作”

这一步的语义是：

- 值不值得打开
- 值不值得继续研究
- 值不值得提升优先级

而不是：

- 马上买
- 马上卖
- 马上建仓

### 3. thesis impact 是共享表达，不是 consumer 私有文风

V1 的 thesis impact 应该只表达：

- 对 thesis 的方向性影响

不要在共享层里提前写成 consumer 私有 prose。

### 4. follow-up path 是下一步建议，不是动作指令

例如可以是：

- `open_company_research`
- `refresh_industry_note`
- `move_to_watchlist_review`
- `wait_for_confirmation`
- `send_to_radar`

## V1 与 consumer 的边界

### 对 Opportunity Report

共享层提供：

- canonical `opportunity candidate`
- buckets
- 排序基础字段

日报/周报自己决定最终版面与口吻。

### 对 Radar

共享层提供：

- 候选机会对象
- 基础 rank / thesis impact / follow-up path

Radar 再叠加：

- 价格
- 资金
- proxy
- 覆盖度

### 对对象研究

研究线程不是直接读 raw article，而是先读：

- `opportunity candidate`
- 对应 event bundle

然后再按需打开原始证据。

### 对 Qlib

Qlib 不直接使用 prose 级机会对象，而是读取：

- event -> entity/day 的结构化特征

## 当前缺什么

当前缺少：

- 正式的 `opportunity_type / opportunity_bucket` 口径
- `thesis_impact` 的稳定规则
- `followup_path` 的共享枚举
- point-in-time export contract

## 当前结论

`Opportunity Transition Layer V1` 应该让 `News Event Hub` 具备把共享事件转成“可研究机会候选”的能力。

它是 `News Event Hub` 内部的共享升级层，但不是替代 `Radar`、`research`、`decision` 的动作层。
