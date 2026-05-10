# Layer 2 Independent Evidence Counting V1

## 目的

这份文档冻结 Layer 2 对 `independent evidence` 的计数口径。

它回答的问题是：

- `confirmation_count` 到底在数什么
- 哪些 source 应视为同一传播链
- 哪些 source 可以视为独立证据

## 一句话结论

`confirmation_count` 不是 article 数，也不是 source_id 数。

它应尽量接近：

`independent evidence units`

也就是：

- 同一传播链不重复计数
- 同一原始来源的多个 feed 不重复计数
- 真正独立的公告 / wire / 原生平台输入才独立计数

## 当前 V1 计数对象

### 1. article_count_raw

表示：

- 原始 article 条数

作用：

- 反映原始覆盖量
- 不直接用作确认度

### 2. source_family_count

表示：

- 当前 event 覆盖到多少个 source family

作用：

- 反映传播链广度
- 是 `coverage_independent` 的基础输入之一

### 3. independent_evidence_count

表示：

- 去重后的独立证据总数

当前口径：

- `confirmation family` 数
- 加 `signal family` 数

### 4. confirmation_count

表示：

- `independent confirmation evidence` 数量

也就是说：

- 共享层里的 `confirmation_count`
- 应等于去重后的 confirmation family 数

它不应再等于：

- article 数
- 转载媒体数
- 同家 wire 的多个 feed 数

## Source Family 的定义

`source_family` 用来表达“这条 source 属于哪个原始传播链 / 原始来源族”。

例如：

- `wire:reuters`
- `wire:prnewswire`
- `wire:globenewswire`
- `wire:cls`
- `wire:jinshi`
- `exchange:cninfo`
- `exchange:hkex`
- `media:jiemian`
- `media:stcn`
- `forum:reddit`
- `forum:v2ex`
- `forum:guba`
- `social:weibo`
- `social:xueqiu`
- `social:xiaohongshu`

## 当前 V1 的计数规则

### A. 同一 source family 不重复计数

例如：

- `prnewswire_all_releases`
- `prnewswire_financial_services`
- `prnewswire_general_business`

如果它们指向同一 event，则默认只算一个 confirmation family，而不是三个。

### B. 同一交易所公告流不重复计数

例如：

- 同属 `exchange:cninfo` 的不同入口
- 同属 `exchange:hkex` 的同类入口

如果本质是同一公告体系，不应被重复计成多个独立确认。

### C. 社交平台内不同抓取口径也应按平台家族折叠

例如：

- `xueqiu_public_timeline`
- `xueqiu_tracked_search`

它们都属于 `social:xueqiu`。

但注意：

- 它们仍可在 `article_count_raw` 中体现原始覆盖量
- 不应在 `confirmation_count` 中重复放大

### D. source_family 缺失时退回启发式

如果 registry 没显式给 `source_family`：

- 先尝试从 canonical URL host 推断
- 再退回 source_id 前缀
- 最后才退回单个 source_id

## 当前不解决什么

V1 先不尝试：

- 自动识别同一新闻在跨站转载链中的全文转载关系
- 自动识别“同一记者 / 同一 wire 被不同站全文转载”的深层归并
- 复杂的 cross-platform evidence de-duplication

这些后续可以继续加，但不阻塞当前 contract 冻结。

## 当前配置落点

V1 的 `source_family` 应优先写在：

- `config/source_registry_v1.yaml`

由 shared registry 统一维护，而不是分散在 builder 脚本里私下猜。

## 当前结论

Layer 2 的 `independent evidence counting` 应建立在：

- `source_family`
- `article_count_raw`
- `independent_evidence_count`
- `confirmation_count`

这四层之上。

其中最关键的是：

`confirmation_count = independent confirmation families`

而不是“有多少篇文章都写了这件事”。
