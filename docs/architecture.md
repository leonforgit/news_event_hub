# Architecture

## 总体原则

系统应从“每个产品各抓各的新闻”切换为：

`一次采集 -> 一次标准化 -> 一次事件化 -> 多视图消费`

同时也要支持：

`持续公共采集 + 按研究对象定向新闻补抓 -> 统一回写共享层`

这里的边界是：

- 只处理新闻类内容
- 不处理券商研报、电话会议 transcript / 录音、财报 PDF、IR deck 等原始研究材料
- 上述非新闻材料统一交给 `Materials` 系统管理

## 三层骨架

这个工作区当前采用三层架构来组织长期建设：

1. `Layer 1 Foundation`
2. `Layer 2 Shared Event & Ranking`
3. `Layer 3 Consumer Views / Integration`

其中：

- 第一层负责 article 输入
- 第二层负责 event 与共享 ranking
- 第三层负责下游消费

## 目标架构

### 1. Source Registry

统一管理新闻源，而不是让日报和雷达各自维护一套。

Source 需要至少记录：

- `source_id`
- `lane`
  - `confirmation`
  - `signal`
- `source_type`
- `trust_tier`
- `coverage_scope`
- `collector_owner`
- `scheduler_class`
- `enabled`

### 2. Collector Layer

负责抓取原始内容。

分两类 collector：

- `baseline collectors`
  - 雷达日常固定跑的公共新闻源
- `targeted collectors`
  - 研究过程中针对某个公司/行业/主题定向抓取

两类 collector 的输出都必须进入同一个共享库。

### 3. Normalize Layer

把不同来源的原始内容统一成标准文章对象。

标准字段至少包括：

- `article_id`
- `source_id`
- `title`
- `summary`
- `body_text`
- `url`
- `canonical_url`
- `published_at`
- `timestamp_quality`
- `title_norm`
- `content_hash`
- `language`
- `collector_scope`
  - `baseline_radar`
  - `targeted_research`

### 4. Event Layer

这是核心层。

这里不再把“文章”直接喂给日报或雷达，而是把多条文章聚成同一事件。

`event v1` 的正式定义见：

- [event_v1_definition.md](docs/event_v1_definition.md)

事件至少需要：

- `event_id`
- `event_type`
- `event_state`
- `event_title`
- `first_seen_at`
- `last_seen_at`
- `novelty_state`
- `confirmation_count`
- `source_mix`
- `entity_links`
- `market_links`
- `topic_links`
- `score_vector`
- `flags`
- `counters`

### 5. Mapping Layer

把事件映射到：

- 行业
- 公司
- 主题链
- 宏观主线
- watchlist / tracker 对象

### 6. Ranking Layer

不要再理解成“单一 shared score”。

这一层更合理的结构是：

- `facts lane evidence ranking`
- `signal lane evidence ranking`
- `shared event ranking contract`
- `within-event evidence ordering`

其中共享层对外应显式输出：

- `event_rank_score`
- `calibrated_confirmation`
- `uncertainty`
- `score_vector`
- `flags`
- `counters`

而不是只给一个总分。

如果按消费视角拆，则至少包括三种 view：

- `global feed`
- `research retrieval`
- `radar / theme view`

下游产品默认消费 `event` 或 `opportunity`，而不是原始 article。

### 7. Consumer Views

#### 行业雷达视图

- 按行业聚合
- 输出 `policy/event overlay`
- 重点是发现“哪个行业值得打开看”

#### 日报视图

- 输出“今天最值得研究的事件”
- 不再自己重新抓新闻

#### 研究视图

- 输出与某对象直接相关的新事实
- 支持研究线程中的定向回写
- 支持按对象做定向新闻补抓
- 不能只返回 event 排序结果，还要支持 article 级证据回溯

#### 研究型检索要求

研究型场景的目标不是“今天最热”，而是“把某个对象的有效新闻尽量找全并尽量找准”。

因此共享层后续需要提供：

- 按公司 / 行业 / 主题的实体检索
- ticker、别名、英文名、旧称的统一映射
- `event view` 与 `article view` 双视角输出
- 按时间窗、主题标签、相关度的研究型召回

## private runtime 部署边界

当前推荐：

- 主共享库：`private runtime`
- 主 collector runtime：`private runtime`
- 本地 repo：只保留 source-of-truth 定义与小型样例

## 与现有系统的关系

### 机会报告系统

已有资产：

- `investment_tracker.db` 内已有 `news_articles / news_signals`
- 更广的 source catalog
- 已有日报 digest 消费链

限制：

- 强日报导向
- 当前更像“新闻文章 + 日报信号”，不是共享事件底座
- 当前阿里云 snapshot 链路仍会触发旧新闻刷新，需退出新闻职责

### 行业雷达系统

已有资产：

- `private runtime` 日更运行位
- 新闻标准化与行业映射逻辑
- source health 与 runtime 经验

限制：

- 当前只把行业 overlay 结果入库
- 没有共享 article/event 表

## 当前建议

- 不直接把 `industry_signal_radar.db` 改造成共享新闻库
- 不继续把 `investment_tracker.db` 作为未来唯一公共库直接扩大
- 更合理的方向是：
  - 新建共享 `news_event.db`
  - 迁移和复用两边已有的成熟能力
  - 停用阿里云旧新闻链路
  - 让共享层成为工作区唯一新闻上游
