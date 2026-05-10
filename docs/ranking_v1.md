# Ranking V1

## 核心判断

当前最大问题不是“新闻不够多”，而是“排序对象错了、惩罚规则不够狠”。

相关 source-of-truth：

- [event_v1_definition.md](docs/event_v1_definition.md)
- [article_to_event_merge_rules_v1.md](docs/article_to_event_merge_rules_v1.md)
- [shared_ranking_features_v1.md](docs/shared_ranking_features_v1.md)

所以 `ranking v1` 的基本原则是：

- 不直接对文章做最终排序
- 先文章，再事件，再投资机会

## 三层排序

### 1. Article Rank

文章层只做基础清洗与预排序，不直接决定是否进日报。

建议因子：

- `source_trust_score`
- `freshness_score`
- `specificity_score`
- `source_originality_score`
- `content_completeness_score`
- `entity_resolvability_score`

建议惩罚：

- `background_penalty`
  - 背景介绍、缘由复盘、历史科普
- `stale_penalty`
  - 旧闻复述
- `generic_tick_penalty`
  - 单纯价格播报、没有新驱动

### 2. Event Rank

这是最重要的一层。

事件层建议因子：

- `novelty_score`
  - 今天是不是新增信息
- `delta_score`
  - 相比昨天发生了什么变化
- `confirmation_score`
  - 是否多源确认
- `specificity_score`
  - 主体、金额、政策动作、时间是否明确
- `mapping_strength_score`
  - 能否映射到行业/公司/主题
- `market_reaction_score`
  - 价格、成交、赔率、讨论热度是否共振
- `researchability_score`
  - 能否形成后续研究入口

建议惩罚：

- `duplicate_event_penalty`
- `weak_mapping_penalty`
- `late_recap_penalty`
- `single_dirty_source_penalty`

### 3. Opportunity Rank

这是最终给日报、周报、watchlist 的排序。

建议因子：

- `event_rank`
- `portfolio_relevance_score`
- `watchlist_relevance_score`
- `industry_radar_overlap_score`
- `thesis_impact_score`
- `followup_path_score`

建议惩罚：

- `low_investability_penalty`
  - 看起来像新闻，但没有研究对象
- `no_action_path_penalty`
  - 不能导出下一步动作

## 两条赛道

### Confirmation Lane

用于决定“发生了什么”。

权重应更重：

- 可信度
- 时间明确性
- 多源确认
- 原始性

### Signal Lane

用于决定“市场开始怎么想”。

权重应更重：

- 异常度
- 热度变化
- 赔率变化
- 讨论扩散
- 与事实层的偏离程度

Signal lane 不应单独决定头条，但可以提升某些事件的优先级。

## Ranking 的硬规则

v1 应优先有硬规则，而不是只靠连续分值。

### 不能直接上日报头部的内容

- 老旧背景综述
- 历史原因解释
- 无明确新动作的宏观价格播报
- 与可研究对象没有映射关系的噪音公司动态

### 可以进入研究线索池但不能直升重点的内容

- 单一社交源爆料
- 单一论坛异动
- 单一赔率异常但无事实确认

## GitHub / 外部调研带来的启发

现成项目可以借鉴的是能力模块，而不是最终排序逻辑。

可借鉴模块：

- 抓取与正文提取：`news-please`
- 语义向量与聚类：`sentence-transformers`、`BERTopic`
- 去重归并：`dedupe`、`simhash`
- 社交事件检测：`SocialED`
- 在线更新：`River`
- 数据接入：`PRAW`、`Polymarket py-clob-client`

但“投资机会 ranking” 仍需要结合本工作区自己的目标自定义。

## V1 验收口径

一版可接受的 ranking，至少应达到：

1. 重大新事件能稳定排到前面
2. 老旧背景材料不会占据宏观主线
3. 噪音型公司新闻不会轻易进入重点公司新闻
4. 舆论信号会被保留，但不会压过事实层
5. 日报输出能回答“今天为什么值得研究这几个事件”
