# News Hub Cutover Checklist

Updated: 2026-04-09

## 目标

把 `News Event Hub` 固定为 `Investment` 工作区唯一的新闻上游，并把“共享事件消费”与“研究对象定向新闻补抓”两种能力一起建设起来。

当前总原则：

- `News Event Hub` 只负责新闻类内容
- 券商研报、电话会议、财报、IR deck、原始 PDF 等不归这里管理
- 上述非新闻材料统一交给 `Materials` 系统
- 下游如果发现新闻缺口，应先回补到共享层，而不是长期维持私有新闻抓取

## 责任边界

### 由 `News Event Hub` 负责

- 持续新闻抓取
- 研究启动时的定向新闻补抓
- article 标准化、去重、事件化、映射、ranking
- `consumer_exports` 与共享新闻检索出口
- 新闻证据的可回溯链接与元数据

### 不由 `News Event Hub` 负责

- 券商研报
- 电话会议 transcript / 录音
- 财报、年报、招股书等原始文档
- 公司演示材料、白皮书、PDF 文件管理

## 能力建设主线

### A. Source Completeness

- [ ] 盘点 `Investment` 工作区所有仍在直接抓新闻的脚本、服务、fallback
- [ ] 把下游独有但共享层没有的新闻源反向收编到 `News Event Hub`
- [x] 已把 `industry_signal_radar` 的 `akshare:news_cctv / akshare:stock_info_global_cls / akshare:stock_info_global_em` 接入共享 collector
- [x] 已把 `investment_report` 的 7 条确认型 `company_*_bing` 主题源接入共享 collector
- [x] 已把 `company_rumor_bing / company_rumor_china_bing` 纳入共享 source map，并明确为默认不启用的 signal 发现层
- [ ] 建立“新对象研究时的定向新闻补抓”入口
- [ ] 让补抓结果回写共享层，而不是只留在对象私有目录

### B. Research Retrieval Quality

- [x] 已为公司建立第一版稳定的实体别名与 ticker 映射：
  - repo 内 alias registry：`data/entity_aliases_v1.csv`
  - builder 已开始把英文名 / ticker / canonical 中文名归到统一 company id
  - watchlist registry 当前作为动态 alias 补充层，不覆盖 repo 内 canonical mapping
- [ ] 提供 `event view` 与 `article view` 两种研究出口
- [ ] 支持按实体、时间窗、主题标签检索
- [ ] 支持研究型高相关召回，而不是只按时间倒序
- [ ] 用真实对象做召回回测，例如 `泡泡玛特`

### C. Consumer Cutover

- [x] `industry_signal_radar` 默认优先读取共享 feed
- [x] `investment_report` 本地消费链路默认优先读取共享 feed
- [ ] 清理仍然保留的旧私有 fallback
- [ ] 明确哪些 fallback 允许短期保留，哪些必须下线

### D. Legacy Shutdown

- [x] 确认阿里云 `investment_tracker.db` 仍在发生新闻写入
- [x] 确认阿里云本地不存在共享 feed 缓存，不能直接切成 shared-only 继续跑
- [x] 停用阿里云旧新闻链路
- [x] 停用阿里云 `investment-server-snapshot` 四个 timer：`premarket / midday / close / weekly`
- [ ] 冻结 `investment_tracker.db`，保留为 legacy 参考，不再继续扩张新闻职责

## 2026-04-07 状态核对

- [x] `news_event_hub` 仓库当前 Git 状态干净
- [x] `private runtime` 三层 timer / service 最近一次执行成功
- [x] `Industry Signal Radar` 当前默认优先读取共享 feed
- [x] `Investment Report` 当前本地消费链路默认优先读取共享 feed
- [x] 阿里云 `investment_tracker.db` 仍有 `news_ingest_runs / news_analysis_runs / news_llm_runs` 新写入
- [x] 阿里云当前 `investment-server-snapshot` 仍会触发旧新闻刷新
- [x] 共享 collector 已在本地与 `private runtime` 实抓验证 `akshare_news_cctv / akshare_stock_info_global_cls / akshare_stock_info_global_em`
- [x] `legacy_catalog_in_scope_missing_from_shared` 已清零；当前旧 catalog 剩余缺口只剩明确不由共享新闻层负责的 `commentary_gap`

## 当前第一优先级

1. 停掉阿里云旧 snapshot / 旧新闻链路，阻止第二套新闻库继续增长。
2. 把 `Investment` 工作区里剩余的旧 fallback 继续收口到共享层。
3. 继续补“研究型定向新闻补抓 + 高质量检索”能力。
