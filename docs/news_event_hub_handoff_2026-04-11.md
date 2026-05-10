# News Event Hub Handoff 2026-04-11

## 这轮完成了什么

这轮先把 `News Event Hub` 的职责边界重新收紧成一套更可执行的设计稿，而不是继续只按“已有三层规划”抽象讨论。

新增的 source-of-truth 文档：

- `docs/news_system_layer_model_v1.md`
- `docs/mapping_layer_v1.md`
- `docs/opportunity_transition_layer_v1.md`

本轮同步更新：

- `README.md`
- `STATUS.md`
- `START_HERE.md`

## 当前共识

### 0. 三层与六层的关系

当前已经确认：

- 顶层仍然是三层动态规划：
  - `Layer 1 Foundation`
  - `Layer 2 Shared Event & Ranking`
  - `Layer 3 Consumer Integration`
- 新增的“六层职责模型”只是 `News Event Hub` 内部实现拆分，不替代顶层三层骨架

### 1. Hub 应承载的层

`News Event Hub` 现在应承载：

1. 源采集层
2. 标准化层
3. 事件状态层
4. 映射层
5. 机会转移层
6. 共享导出层

### 2. Hub 不承载的层

当前不由 `News Event Hub` 主动承载：

- 决策路由层
- 完整反馈评估层

其中：

- 决策路由仍保持 `pull-based consumer` 口径
- 反馈评估由下游完成，`Qlib` 只承担市场反应评估这一子层

### 3. Qlib 的主输入

对 `Qlib` 而言，主事件输入应该来自 `News Event Hub`，不是来自 `Radar` 的 prose 输出。

`Radar` 后续可以输出辅助衍生特征，但不应成为 Qlib 的事件真相源。

## 当前最缺的实现层

### A. Mapping Layer 正式成层

虽然 schema 和部分实现已经有了，但当前仍缺：

- 输入/输出 contract
- canonical mapping version 语义
- `mapping_reason / mapping_confidence`
- unresolved queue

### B. Opportunity Transition 正式成层

虽然已有 `opportunity_signals` 占位，但当前仍缺：

- `opportunity_type`
- `opportunity_bucket`
- `thesis_impact`
- `followup_path`

### C. Point-in-time export

当前 feeds 以 `latest` 为主，足够给下游读，但还不够给 `Qlib` 做严肃评估。

后续必须补：

- dated export
- entity-day / industry-day event panel
- as-of 口径

### D. 长期趋势信号识别

这已经被确认为后续长期规划，但不是当前任务。

目标是后续基于历史 `event + mapping` 累积识别：

- 目前尚未高热度、但出现频率在缓慢抬升的对象/主题
- 由多次弱事件逐渐汇成的长期主线
- 市场尚未充分关注、但新闻层面已经持续冒头的潜在趋势

这项能力当前不先做，原因是它依赖：

- 更稳的 `Mapping Layer`
- 更稳的 `Opportunity Transition`
- 更清晰的 `dated export / as-of` 口径

## 推荐的后续顺序

### Phase 1

先补 Mapping Layer：

- 明确 stable registry
- 明确 canonical object classes
- 给 `event_entity_links` 增加更稳定的理由和置信度表达

### Phase 2

再补 Opportunity Transition：

- 稳定 `opportunity bucket`
- 稳定 `thesis impact`
- 稳定 `follow-up path`

### Phase 3

最后补 point-in-time export：

- 面向 `Radar`
- 面向 `research`
- 面向 `Qlib`

### Phase 4

再补长期趋势信号识别：

- `event frequency drift`
- `topic accumulation`
- `entity/theme slow-burn trend detection`

## 与其他子工作区的边界

### Radar

`Radar` contract 已放到 `industry_signal_radar` 子工作区去定义。

这里保持：

- `Hub` 提供 canonical event / mapping / opportunity candidate
- `Radar` 负责发现、排序、提醒

### Qlib

`Qlib` contract 已放到 `qlib_paper_trading` 子工作区去定义。

这里保持：

- `Hub` 提供结构化事件特征
- `Qlib` 负责反馈评估与模拟交易侧验证

## 建议下一步直接做的事

如果下一轮继续在 `News Event Hub` 内推进，优先做这三件事：

1. 给 `Mapping Layer` 补一个更明确的 field contract 和 registry contract
2. 给 `Opportunity Transition` 补一个更明确的 bucket / impact / follow-up 枚举
3. 定义第一版 `dated export` / `entity-day panel`，为 `Qlib` 做准备
