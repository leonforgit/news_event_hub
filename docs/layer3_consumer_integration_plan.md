# Layer 3 Consumer Integration Plan

## 这一层是什么

Layer 3 是下游消费层。

它的任务不是重新定义新闻，而是把共享层变成可消费输出。

## 这一层服务谁

- 投资机会报告
- 行业雷达
- 行业/公司研究流程

## 这一层的原则

### 1. 下游做轻量消费

下游应该消费共享层，而不是自己重做抓取、归并、理解和排序。

### 2. 下游可以做轻微调权，但不应重造事件层

例如：

- 投资机会报告更重组合相关性
- 行业雷达更重行业扩散性
- 研究线程更重对象命中

但这些都应建立在共享 event / ranking feature 之上。

### 3. 迁移要显式进行

旧接口不能默默废弃，必须有迁移说明和 adapter 边界。

## 当前状态

当前这一层已经进入 `最小可用 adapter` 阶段。

已落地：

- `scripts/export_consumer_views.py`
- `scripts/smoke_test_consumer_views.py`
- `docs/layer3_consumer_contract_v1.md`
- `docs/legacy_interface_migration.md`

当前重点已经从“只定义消费者”推进到：

- 把共享库变成实际可读的消费出口
- 给旧接口明确迁移边界
- 推动下游逐个从私有新闻链路切到共享 consumer feed

## 三类消费者

### 投资机会报告

当前已经开始消费：

- `opportunity_report_feed_latest.json`
- `legacy_news_digest_latest.json`
- `source_health_latest.json`
- 通过本地适配层把 shared event feed 投影成现有 `news_digest`
- 当共享 feed 缺失或过旧时，暂时回退到同步下来的旧 `news_digest`

下一步仍应更多消费：

- 高优先事件列表
- 与 watchlist / portfolio 相关的 shared features
- 可解释的事件摘要

### 行业雷达

当前已经开始消费：

- `industry_radar_feed_latest.json`
- `source_health_latest.json`
- 通过薄适配层把共享行业名映射回 `industry_id`
- 当共享 feed 缺失或陈旧时，暂时回退到旧 `radar_news_policy.py`

下一步仍应更多消费：

- 行业映射后的事件视图
- 政策 / 公司 / 宏观变化对行业的 overlay

### 研究工作流

未来应更多消费：

- 某对象相关的新事件
- 某 thesis 的增量证据
- 回写共享库的 targeted research 路径

## 近期 checklist

- [x] 明确 Layer 3 是消费层，不是私有新闻层
- [x] 明确三类主要消费者
- [x] 盘点投资机会报告的旧接口依赖
- [x] 盘点行业雷达的旧接口依赖
- [ ] 设计研究工作流的回写契约
- [x] 设计研究工作流的读取契约
- [x] 明确共享层输出给各 consumer 的最小 adapter
- [x] 写出旧接口迁移说明
- [x] 让 `investment_report` 开始默认读取共享 consumer feed
- [x] 让 `industry_signal_radar` 开始默认读取共享 consumer feed

## 第三层完成标志

至少满足：

1. 主要下游开始默认从共享层读取
2. 旧抓取旁路明显收缩
3. 各下游只保留薄适配层，不再各自维护一套新闻理解系统
