# News System Layer Model V1

## 目的

这份文档把 `News Event Hub` 当前应该承载哪些层、哪些层不该由它承载，明确成一份可执行的 source-of-truth。

它不是替代现有的三层动态规划：

- `Layer 1 Foundation`
- `Layer 2 Shared Event & Ranking`
- `Layer 3 Consumer Integration`

而是从“系统职责”角度，把共享新闻系统重新拆成更贴实现的功能层。

## 与三层动态规划的关系

这份“六层职责模型”不替代顶层三层架构，而是把三层架构继续拆到更贴近实现的粒度。

对应关系建议固定为：

- `Layer 1 Foundation`
  - 源采集层
  - 标准化层
- `Layer 2 Shared Event & Ranking`
  - 事件状态层
  - 映射层
  - 机会转移层
- `Layer 3 Consumer Integration`
  - 共享导出层

也就是说：

- 三层是顶层产品/系统骨架
- 六层是 `News Event Hub` 内部职责骨架

后续文档、实现和对外解释都应保持这两套口径一致，不把它们写成互相竞争的两种架构。

## 一句话结论

`News Event Hub` 应该承载：

1. 源采集层
2. 标准化层
3. 事件状态层
4. 映射层
5. 机会转移层
6. 共享导出层

`News Event Hub` 不应承载：

7. 决策路由层
8. 完整反馈评估层

其中：

- 决策路由层应保持 `pull-based consumer` 口径，由下游自己来取
- 反馈评估层应由下游系统完成，其中 `Qlib` 可承担市场反应评估的一部分

## 分层视图

### 1. 源采集层

回答的问题：

- 哪些新闻源被允许进入系统
- 这些源如何被持续抓取
- 源的健康状态如何记录

当前归属：

- `source_registry`
- `run_live_news_collector.py`
- `run_browser_signal_collector.py`
- `source_health`

当前状态：

- 已建立
- 已可运行

### 2. 标准化层

回答的问题：

- 来自不同来源的内容，如何压成统一 article 对象
- 基础去重、时间戳、语言、来源族如何表达

当前归属：

- `news_articles`
- `source_family`
- `collector_scope`
- article 级 normalize / dedupe

当前状态：

- 已建立
- 已可运行

### 3. 事件状态层

回答的问题：

- 多篇 article 如何归成一个 `event`
- `event` 现在处于 `watch / emerging / confirmed / contested / mature` 的哪一阶段
- event 内证据如何排序

当前归属：

- `events`
- `article_event_links`
- `event_state`
- `score_vector`
- `within-event evidence ordering`

当前状态：

- 已建立
- 已有第一版 contract 与实现

### 4. 映射层

回答的问题：

- 这件事和哪些公司、行业、主题、宏观主线相关
- 这些对象的 canonical ID 是什么
- 映射强度和映射理由是什么

当前归属：

- `event_entity_links`
- `primary_entity`
- `primary_industry`
- alias / canonical mapping

当前状态：

- 已有 schema 和部分实现
- 但还没有正式成层

这是当前最值得前推的缺口之一。

### 5. 机会转移层

回答的问题：

- 一个 `event` 何时升级为 `opportunity candidate`
- 它更适合进入 `日报 / watchlist / 研究线程 / Radar`
- 它对 thesis 的影响是 `positive / negative / neutral / unclear`

当前归属：

- `opportunity_signals`
- `opportunity_state`
- 面向 consumer 的 opportunity bucket

当前状态：

- schema 有占位
- 但 contract 还未正式落成

这是当前第二个最值得前推的缺口。

### 6. 共享导出层

回答的问题：

- 下游应该从哪里读共享新闻系统
- 各 consumer 读到的是哪种 canonical feed

当前归属：

- `opportunity_report_feed_latest.json`
- `industry_radar_feed_latest.json`
- `research_feed_latest.json`
- `source_health_latest.json`

当前状态：

- 已建立
- 当前默认保持 pull-based 模式

### 7. 决策路由层

回答的问题：

- 哪个 consumer 现在应该处理这件事
- 该不该开研究线程、升 watchlist、写 decision gate、进 action review

当前归属：

- 不属于 `News Event Hub`

设计结论：

- `News Event Hub` 不主动路由
- 下游系统自行 pull 共享 feed 并作各自决策

### 8. 反馈评估层

回答的问题：

- 哪类事件后续更容易得到确认
- 哪类事件有更高的市场反应
- 哪类事件更能形成研究价值或动作价值

当前归属：

- 不由 `News Event Hub` 独自承担

设计结论：

- `News Event Hub` 负责准备 point-in-time 事件面板
- `Qlib` 可承担“市场反应评估”这一子层
- `Radar / research / decision` 还需要各自补研究价值与动作价值评估

## 当前缺口清单

### A. 缺少正式映射层 contract

当前已经开始做：

- alias registry
- canonical company id
- `event_entity_links`

但仍缺：

- 映射输入/输出 contract
- 映射置信度与理由字段
- unresolved mapping queue
- point-in-time 映射版本语义

### B. 缺少正式机会转移层 contract

当前已有：

- `opportunity_signals` 表占位
- opportunity feed bucket

但仍缺：

- event -> opportunity 的稳定升级规则
- 与 `watchlist / research / Radar / Qlib` 的统一字段口径
- thesis impact 与 follow-up path 的稳定表达

### C. 缺少 point-in-time 反馈导出 contract

当前 consumer feeds 以 `latest` 为主，足够支持读取，但不够支持严肃评估。

后续必须补：

- dated export
- entity-day / industry-day event panel
- stable as-of semantics

## 长期规划：趋势信号层

这不是当前 V1 主任务，但应作为后续长期规划明确记录。

### 想解决的问题

随着共享新闻库持续累积，系统后续应能识别：

- 某类事件还未形成高热度，但出现频率在缓慢上升
- 某个公司/行业/主题的弱信号，正在从零散事件演变成持续主线
- 市场暂时没有充分关注，但新闻层面已经出现持续提及和扩散

例如：

- 某类 supply chain 调整在三周内被多次提及
- 某个新技术主题在不同公司新闻里反复出现
- 某个行业问题先以零散 company events 出现，随后逐步变成 sector-level pattern

### 它放在哪一层

这个能力更适合视为：

- 以 `event + mapping + point-in-time history` 为基础的派生分析层
- 当前归属于 `Layer 2` 的长期扩展，而不是新的顶层主线

也就是说：

- 它不改变当前三层结构
- 但会建立在 `事件状态层 + 映射层 + dated export` 之上

### 为什么不是当前任务

因为它依赖几个前置条件先稳定：

- event 粒度要更稳
- mapping layer 要更稳
- point-in-time export 要先补齐
- entity/day / topic/day 的历史面板要先可重放

所以当前顺序应该是：

1. 先把 `Mapping Layer`
2. 再把 `Opportunity Transition Layer`
3. 再把 `dated export / as-of semantics`
4. 最后再做 `trend signal detection`

### 未来可能的输出

未来如果进入实现，可以考虑输出：

- `trend_candidate`
- `trend_entity_links`
- `trend_topic_links`
- `trend_strength`
- `trend_acceleration`
- `trend_horizon`
- `trend_reason`

但这些字段当前不纳入 V1 schema 主线。

## 对下游的边界

### 对 Radar

`News Event Hub` 提供：

- 共享事件输入
- 映射结果
- opportunity candidate

`Radar` 负责：

- 结合价格、资金、代理变量做机会排序
- 生成每日机会面板与告警

### 对对象研究

`News Event Hub` 提供：

- mapped event bundle
- supporting articles
- evidence ordering

对象研究默认从“映射处理后的事件包”进入，再按需下钻原稿。

### 对 Qlib

`News Event Hub` 提供：

- point-in-time 结构化事件因子

`Qlib` 负责：

- event study
- factor test
- 反馈评估中的市场反应部分

## 当前结论

`News Event Hub` 不是简单新闻库，而是 `共享新闻解释层`。

它当前最需要继续补齐的，不是再扩一个下游，而是：

1. 映射层正式成层
2. 机会转移层正式成层
3. 为 Radar / research / Qlib 准备稳定的 point-in-time export contract
