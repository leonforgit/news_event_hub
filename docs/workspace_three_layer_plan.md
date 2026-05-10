# News Event Hub Three-Layer Plan

## 目的

这份文档是 `News Event Hub` 的顶层动态规划总纲。

它不替代各层细化文档，而是负责回答三个问题：

1. 这个工作区到底在建设哪三层
2. 当前主要卡在哪一层
3. 三层之间的依赖关系是什么

## 三层架构

### Layer 1: Foundation

职责：

- 建好统一数据库
- 建好 source registry
- 建好 collectors
- 建好固定抓取与调度
- 建好 source health
- 建好 article 标准化与去重

一句话：

`持续产出干净、可复用的 article 对象`

当前状态：

- 已达到 `最小可用`
- 但远未达到 `理想接入面`
- 仍处于持续建设中

对应动态规划：

- [layer1_foundation_plan.md](docs/layer1_foundation_plan.md)

### Layer 2: Shared Event & Ranking Layer

职责：

- 定义 `article -> event`
- 定义事件对象
- 沉淀共享 feature
- 设计共享 ranking 规则
- 产出可被多个下游共同消费的共享视图

一句话：

`把 article 提升成可排序、可研究、可共享的 event`

当前状态：

- 正式进入定义阶段
- 这是当前主工作面

对应动态规划：

- [layer2_shared_event_ranking_plan.md](docs/layer2_shared_event_ranking_plan.md)

### Layer 3: Consumer Integration

职责：

- 让共享层被投资机会报告消费
- 让共享层被行业雷达消费
- 让共享层被行业/公司研究流程消费
- 完成旧接口迁移与消费契约收口

一句话：

`让下游只做轻量消费，不再各自重造新闻理解逻辑`

当前状态：

- 还未正式进入大规模改造
- 先做消费契约与迁移边界定义

对应动态规划：

- [layer3_consumer_integration_plan.md](docs/layer3_consumer_integration_plan.md)

## 三层依赖关系

### Layer 1 -> Layer 2

如果第一层没有持续稳定地产出 article，对第二层的 event 和 ranking 讨论就会失真。

### Layer 2 -> Layer 3

如果第二层没有定义清楚 event 和 shared ranking feature，下游消费就只能继续各自实现一套私有逻辑。

### Layer 1 与 Layer 3 不应直接硬耦合

下游不应该直接围绕某个 collector 或某个原始 source 写私有逻辑。

真正应该被消费的是共享层输出，而不是抓取过程本身。

## 当前阶段判断

当前不是“第一层完成，第二层开始”，而是：

- 第一层已经 `初步可用`
- 第一层仍在继续补强
- 第二层正式进入定义与规划
- 第三层先做消费契约与迁移设计

## 当前主线

当前工作区的主线应明确为：

1. 持续补强 Layer 1 的 source coverage 与 runtime 稳定性
2. 把 Layer 2 做成整个工作区最核心的共享能力
3. 用 Layer 3 约束共享层的输出契约，而不是过早做零散下游改造

## 顶层 checklist

- [x] 明确工作区采用三层动态规划结构
- [x] 明确三层各自职责与边界
- [x] 明确当前状态不是“第一层结束”，而是“第一层可用、第二层启动”
- [x] 把现有文档路由收敛到三层规划骨架
- [x] 把 Layer 2 的 event 定义收敛成更正式的 source-of-truth
- [ ] 把 Layer 3 的消费契约和旧接口迁移边界补全
