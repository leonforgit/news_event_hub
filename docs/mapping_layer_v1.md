# Mapping Layer V1

## 目的

这份文档定义 `News Event Hub` 的 `Mapping Layer V1`。

它回答的问题是：

- 一个 `event` 到底和谁有关
- 这些对象的 canonical ID 是什么
- 这个映射的强弱和可信度如何表达

## 一句话结论

`Mapping Layer` 是 `News Event Hub` 的核心层，不属于任何下游 consumer。

它应该把新闻事件统一映射到：

- `company`
- `industry`
- `theme`
- `macro_theme`

并输出稳定的 `event_entity_links`，供 `Radar / research / Qlib` 复用。

## 非目标

当前 V1 不负责：

- 最终动作决策
- watchlist 升降级
- 下游写主稿
- 直接给 Qlib 生成交易信号

## V1 输入

### 1. Event 层输入

- `event_id`
- `event_title`
- `event_type`
- `event_state`
- `topic_key`
- `supporting_articles`
- `score_vector`

### 2. Article 层输入

- `title`
- `summary`
- `body_text`
- `source_id`
- `source_family`
- `published_at`

### 3. 静态 registry 输入

- `data/entity_aliases_v1.csv`
- `config/industry_taxonomy_v1.json`
- 稳定 company canonical mapping
- 稳定 industry canonical mapping
- 主题 / 宏观主线 registry

### 4. 动态补充输入

- watchlist 中的动态 alias
- 研究线程新增的高价值对象名
- Radar 侧短期补充的行业 / 主题词

## V1 输出

### A. event_entity_links

最小输出字段：

- `event_id`
- `entity_type`
- `entity_id`
- `entity_name`
- `relevance_score`

### B. event 轻量冗余字段

- `primary_entity`
- `primary_industry`

### C. 研究与评估友好字段

V1 建议继续补出但不要求立即入表：

- `mapping_reason`
- `mapping_confidence`
- `mapping_version`
- `mapping_source`

## 映射对象类型

### 1. company

用于：

- 公司事件
- 结构性公司新闻
- 影响集中在单个上市主体的事件

### 2. industry

用于：

- 行业政策
- 行业景气变化
- 行业供需或资金扩散

### 3. theme

用于：

- AI capex
- 创新药出海
- 电网设备
- 商业航天

这类跨行业主题。

### 4. macro_theme

用于：

- 关税
- OPEC
- 利率路径
- 中东地缘

这类不适合直接归到单个行业或公司，但会持续影响多个对象的主线。

### 5. institution

用于：

- 部委
- 行业协会
- 监管主体
- 交易所 / 管理机构

这类不应误映射成 `company`，但又值得作为共享对象保留下来的政策/制度主体。

## V1 映射流程

### Step 1. 抽取候选对象

从：

- `event_title`
- `summary`
- `body_text`
- supporting article 标题窗口

抽取候选：

- 公司名
- 行业词
- 主题词
- 宏观主线词

### Step 2. canonical 归一

把抽到的候选名映射到稳定 canonical ID。

这一步要优先使用：

- repo 内稳定 alias registry
- 已知公司 / 行业真相源

不要把下游临时字符串搜索当成长期 canonical 机制。

### Step 3. 评分

对每个候选映射给出 `relevance_score`。

V1 可参考的评分维度：

- title 命中强度
- supporting article 一致性
- event_type 与 entity_type 是否匹配
- 是否出现 structural action
- 是否存在官方 / 直接证据
- 是否只是背景陪衬

### Step 4. 写回

把高于阈值的映射写入：

- `event_entity_links`
- `primary_entity`
- `primary_industry`

## V1 设计原则

### 1. company / industry / theme / macro_theme 分开建模

不要把所有对象混成一个平面词表。

### 2. canonical mapping 优先于 consumer 私有补丁

下游可以补充 alias，但不应该各自重新发明 canonical truth。

### 3. mapping 是共享资产，不是 consumer 视图

研究线程、Radar、Qlib 看到的应该是同一批 canonical 映射结果。

### 4. 映射要能 point-in-time 重放

后续为了评估，至少要知道：

- 这个 event 在当时被映射到了什么对象
- 使用了哪一版 mapping 规则

### 5. unresolved 不能静默丢失

没有高置信命中的 event，不应只是安静失败。

V1 后续应补：

- unresolved mapping queue
- 高频漏样本 review 入口

## 当前已有基础

当前已经具备：

- `event_entity_links`
- `primary_entity / primary_industry`
- alias registry
- industry taxonomy config
- canonical company id
- entity-first research feed

说明 V1 不是从零开始，而是把已经分散存在的能力正式收成一层。

## 当前缺什么

当前主要缺少：

- 正式的 `Mapping Layer` source-of-truth 文档
- 更明确的输入/输出字段边界
- `mapping_reason / mapping_confidence / mapping_version`
- unresolved queue
- 与 Qlib 的 point-in-time 对齐口径

## 对下游的消费方式

### 对 Radar

Radar 不自己重建 canonical mapping，只在共享映射之上做对象级排序和调权。

### 对研究线程

研究线程默认读 `mapped event bundle`，再按需下钻原文。

### 对 Qlib

Qlib 不直接吃原始 article，而是吃按 `entity/date` 对齐后的映射结果和事件特征。

## 当前结论

`Mapping Layer V1` 的目标不是“映射得多花哨”，而是先让整个工作区共享同一套：

- 事件 -> 对象
- 对象 -> canonical ID
- 映射强度

只要这层稳定，后面的 `Radar / research / Qlib` 才不会各自吃不同真相源。
