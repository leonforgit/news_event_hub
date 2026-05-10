# Layer 2 Event State Machine V1

## 目的

这份文档冻结 Layer 2 对 `event_state` 的第一版状态机口径。

它回答的问题是：

- 什么情况下 event 进入 `watch`
- 什么情况下从 `watch` 推进到 `emerging`
- 什么情况下进入 `confirmed`
- 什么情况下标成 `contested`
- 什么情况下进入 `mature`

## 一句话结论

`event_state` 不应只是 `event_rank_score` 的副产物。

它应该是共享层对“这件事目前处在什么证据阶段”的显式表达。

## V1 状态集合

### 1. watch

表示：

- `signal-only`
- 值得观察
- 尚未进入强确认语义层

典型条件：

- 只有单条 `signal family`
- 没有 `confirmation family`

### 2. emerging

表示：

- 事件已开始形成
- 但确认度还没到 `confirmed`

典型条件：

- 已有单条 `confirmation family`
- 或多平台 `signal` 共振
- 或单条高价值 `signal` 已具备结构性动作 / 高局部影响

### 3. confirmed

表示：

- 已有较强独立事实确认

典型条件：

- 至少 `2` 个独立 `confirmation family`
- 或 `1` 个确认族且属于官方披露 / 官方源
- 或单确认但 `calibrated_confirmation` 已明显跨过高置信阈值

### 4. contested

表示：

- 证据冲突
- 或存在明确否认 / 辟谣 / 澄清 / 未达成等反向证据

这一状态优先级高于：

- `watch`
- `emerging`
- `confirmed`

### 5. mature

表示：

- 事件已成熟
- 新增信息边际价值下降

典型条件：

- `novelty_state = stale`
- 或事件已进入显式终止 / 完成语义，且已有一定确认基础

## V1 推进规则

### A. contested 优先

如果标题或摘要出现：

- `否认`
- `辟谣`
- `澄清`
- `未达成`
- `未签署`
- `rejects / denies`

则优先进入 `contested`。

### B. stale / terminal 优先进入 mature

如果：

- `novelty_state = stale`
- 或事件已经出现 `终止 / 取消 / 完成 / completed / settled`

则默认进入 `mature`，而不是继续停留在 `confirmed`。

### C. confirmed 看独立确认，不看 article 数

`confirmed` 的判断基于：

- `independent confirmation families`
- `official source presence`
- `calibrated_confirmation`

而不是：

- article 数
- 同一家 wire 的多个 feed 数

### D. emerging 是“已开始成形”而不是“还不够热”

以下都可以进入 `emerging`：

- 单确认族
- 多平台 signal 共振
- 单条高价值 signal

### E. watch 是有限保留，不是垃圾桶

`watch` 用来承接：

- 单条 signal
- 还未进入更强证据阶段的发现层对象

它可以进入共享层，但不应与 `confirmed` 同权混排。

## V1 当前实现锚点

当前实现里，状态机会依赖这些输入：

- `confirmation_count`
- `signal_count`
- `official_source_present`
- `structural_event`
- `high_local_impact`
- `calibrated_confirmation`
- `uncertainty`
- `novelty_state`

## 当前不解决什么

V1 先不做：

- 显式状态迁移表落库
- per-event 状态历史回放
- `update` 级状态推进日志

这些可以在后续 `update` 对象落地后再补。

## 当前结论

Layer 2 的 `event_state` 应表达：

- 这件事现在所处的证据阶段

而不是：

- 这件事当前分数高不高
- 或者这件事是不是热门
