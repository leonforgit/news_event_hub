# Unified News Source Inventory

## 目的

这份文档回答当前阶段最关键的一个问题：

- 我们现在到底已经接了哪些新闻源
- 哪些源应进入统一新闻系统
- 哪些源只是旧链路遗产或补充层
- 哪些源应排除在统一新闻系统主体之外

本文件服务于 `Unified News System Phase 1`，默认与 [unified_news_system_phase1_plan.md](docs/unified_news_system_phase1_plan.md) 配套阅读。

## 当前统一口径

### 只保留 News

统一新闻系统当前只处理 `News`，不处理：

- OpenBB sidecar 数据
- 价格 / 指数 / 资金流
- proxy / context / tape
- 结构化时间序列或景气指标

### 只保留两条 lane

- `confirmation lane`
  - 官方、公告、监管、政府、主流财经确认源
- `signal lane`
  - 社交、论坛、预测市场、传闻与早期发酵源

### 去向字段说明

- `迁入 Phase 1`
  - 应进入统一新闻系统第一阶段主体
- `兼容保留`
  - 迁移期先保留，但不是统一系统的长期 canonical source
- `后续再接`
  - 方向正确，但不在第一阶段优先迁入范围
- `排除`
  - 不应进入统一新闻系统主体

## A. 投资机会报告链路

以下是当前 `investment_report` 链路里 `enabled` 且仍可视为新闻输入的源资产。

### A1. 应迁入 Phase 1 的 confirmation lane 主干

| source_key | 当前来源形态 | lane | 去向 | 备注 |
| --- | --- | --- | --- | --- |
| `sec_8k_current` | SEC Atom | confirmation | 迁入 Phase 1 | 美股公司公告硬信息 |
| `sec_6k_current` | SEC Atom | confirmation | 迁入 Phase 1 | ADR / 海外发行人公告 |
| `cninfo_sz_latest` | CNINFO | confirmation | 迁入 Phase 1 | A 股公告主干 |
| `cninfo_sh_latest` | CNINFO | confirmation | 迁入 Phase 1 | A 股公告主干 |
| `hkex_tracked_latest` | HKEX tracked | confirmation | 迁入 Phase 1 | 港股公告主干 |
| `fed_press` | RSS | confirmation | 迁入 Phase 1 | 宏观确认源 |
| `fred_us_macro_open_data` | GitHub raw JSON importer | confirmation | 迁入 Phase 1 | FRED 美国核心宏观发布事件结构化 sidecar，附带部分 consensus / surprise 字段 |
| `govcn_yaowen` | gov.cn JSON | confirmation | 迁入 Phase 1 | 中国政策确认源 |
| `xinhua_fortune_html` | HTML list | confirmation | 迁入 Phase 1 | 中国政策 / 产业新闻补充 |
| `cls_telegraph_html` | CLS Telegraph | confirmation | 迁入 Phase 1 | 高频快讯主干 |
| `company_stcn_html` | HTML list | confirmation | 迁入 Phase 1 | 中国公司新闻补充 |
| `company_jiemian_stock_html` | HTML list | confirmation | 迁入 Phase 1 | 中国公司新闻补充 |
| `company_jiemian_company_html` | HTML list | confirmation | 迁入 Phase 1 | 中国公司新闻补充 |
| `reuters_macro_bing` | Bing News RSS | confirmation | 迁入 Phase 1 | 海外宏观确认源，当前为搜索聚合形态 |
| `reuters_company_bing` | Bing News RSS | confirmation | 迁入 Phase 1 | 海外公司事件确认源，当前为搜索聚合形态 |

### A2. 迁移期兼容保留的 confirmation lane 补充源

| source_key | 当前来源形态 | lane | 去向 | 备注 |
| --- | --- | --- | --- | --- |
| `marketaux_global_optional` | MarketAux API | confirmation | 已接入共享 collector | env-gated 全局补充源，已上线但不宜做长期唯一主干 |
| `mediastack_global_optional` | Mediastack API | confirmation | 已接入共享 collector | env-gated 全球新闻补充 recall，作为 MarketAux 之外的第二条 APILayer 生态 API |
| `macro_oil_bing` | Bing News RSS | confirmation | 兼容保留 | 商品相关宏观新闻补充，不是独立商品数据 |
| `macro_rates_bing` | Bing News RSS | confirmation | 兼容保留 | 利率 / 汇率新闻补充 |
| `macro_china_bing` | Bing News RSS | confirmation | 兼容保留 | 中国政策新闻补充 |
| `macro_us_china_bing` | Bing News RSS | confirmation | 兼容保留 | 中美政策新闻补充 |
| `macro_middleeast_bing` | Bing News RSS | confirmation | 兼容保留 | 地缘与能源新闻补充 |
| `macro_defense_policy_bing` | Bing News RSS | confirmation | 兼容保留 | 军售 / 地缘政策新闻补充 |
| `company_mna_bing` | Bing News RSS | confirmation | 已并入共享 collector | 公司并购主题搜索补充源 |
| `company_spin_bing` | Bing News RSS | confirmation | 已并入共享 collector | 公司分拆主题搜索补充源 |
| `company_asset_sale_bing` | Bing News RSS | confirmation | 已并入共享 collector | 公司资产出售主题搜索补充源 |
| `company_capacity_bing` | Bing News RSS | confirmation | 已并入共享 collector | 公司产能扩张主题搜索补充源 |
| `company_financing_bing` | Bing News RSS | confirmation | 已并入共享 collector | 公司融资主题搜索补充源 |
| `company_resources_bing` | Bing News RSS | confirmation | 已并入共享 collector | 资源扩张主题搜索补充源 |
| `company_new_industry_bing` | Bing News RSS | confirmation | 已并入共享 collector | 新产业进入主题搜索补充源 |
| `company_bloomberg_bing` | Bing News RSS | confirmation | 兼容保留 | 当前只是搜索聚合，不是直连 Bloomberg |
| `company_wsj_bing` | Bing News RSS | confirmation | 兼容保留 | 当前只是搜索聚合 |
| `company_cnbc_bing` | Bing News RSS | confirmation | 兼容保留 | 当前只是搜索聚合 |
| `company_ap_bing` | Bing News RSS | confirmation | 兼容保留 | 当前只是搜索聚合 |
| `company_ft_bing` | Bing News RSS | confirmation | 兼容保留 | 当前只是搜索聚合 |
| `company_marketwatch_bing` | Bing News RSS | confirmation | 兼容保留 | 当前只是搜索聚合 |
| `company_financial_media_bing` | Bing News RSS | confirmation | 兼容保留 | 泛财经媒体兜底源 |

### A3. signal lane 现有源

| source_key | 当前来源形态 | lane | 去向 | 备注 |
| --- | --- | --- | --- | --- |
| `weibo_tracked_mobile` | 原生搜索 | signal | 迁入 Phase 1 | 当前最值得保留的中文社交直连接入 |
| `guba_tracked_direct` | 原生板块跟踪 | signal | 迁入 Phase 1 | 当前最值得保留的股吧直连接入 |
| `serpstack_company_discovery_optional` | Serpstack API | signal | 已注册共享 source map | 仅用于 on-demand company discovery 的结构化搜索 backend，不进入固定轮询 collector |
| `v2ex_all_feed` | V2EX Atom | signal | 迁入 Phase 1 | 已接入共享 collector，作为公开论坛信号补充 |
| `reddit_market_forums` | Reddit 原生 JSON | signal | 迁入 Phase 1 | 已接入共享 collector，当前覆盖 wallstreetbets / stocks / investing |
| `reddit_tracked_search` | Reddit 定向搜索 | signal | 迁入 Phase 1 | 已接入共享 collector，承接研究对象级讨论补抓 |
| `xueqiu_public_timeline` | 雪球公共热帖 | signal | 迁入 Phase 1 | 已接入共享 collector，作为第一批稳定雪球公共信号源 |
| `xueqiu_hot_stocks` | 雪球热股榜 | signal | 迁入 Phase 1 | 已接入共享 collector，作为关注度变化信号 |
| `xueqiu_tracked_search` | 雪球定向搜索 | signal | 迁入 Phase 1 | 已切到 browser-backed collector，承接公司级定向讨论检索 |
| `xiaohongshu_tracked_search` | 小红书定向搜索 | signal | 暂停接入 | 当前保留在 source map 中，但已撤出活跃 browser-backed collector |
| `reddit_rumor_bing` | Bing News RSS | signal | 后续再接 | 当前为搜索发现形态，不是 Reddit 原生接入 |
| `weibo_rumor_bing` | Bing News RSS | signal | 后续再接 | 可做发现层，但不宜做第一批主干 |
| `xueqiu_rumor_bing` | Bing News RSS | signal | 后续再接 | 当前为搜索发现形态 |
| `guba_rumor_bing` | Bing News RSS | signal | 后续再接 | 当前为搜索发现形态 |
| `company_rumor_bing` | Bing News RSS | signal | 已纳入共享 source map | 公司传闻发现层，当前默认不启用 |
| `company_rumor_china_bing` | Bing News RSS | signal | 已纳入共享 source map | A/H 公司传闻发现层，当前默认不启用 |

### A4. 排除出统一新闻系统主体的旧源类型

以下虽然存在于旧 catalog，但当前不应作为统一新闻系统主体纳入：

- `investor_*`
  - 投资人观点、做空观点、大 V 观点
- 卖方公开研究 feed
  - `Goldman / Morgan Stanley / BlackRock / JPM` 等公开观点流

这些更适合作为 `view / commentary layer`，不是共享新闻数据库本体。

## B. 行业雷达链路

以下是 `industry_signal_radar` 当前 manifest 中与新闻相关的源。

### B1. 已激活、应并入统一新闻系统的源

| source_id | 当前形态 | lane | 去向 | 备注 |
| --- | --- | --- | --- | --- |
| `akshare:news_cctv` | AKShare / 央视新闻联播摘要 | confirmation | 已并入共享 collector | 已于 2026-04-07 完成本地与 private runtime 实抓验证 |
| `akshare:stock_info_global_cls` | AKShare / 财联社全球快讯 | confirmation | 已并入共享 collector | 已于 2026-04-07 完成本地与 private runtime 实抓验证 |
| `akshare:stock_info_global_em` | AKShare / 东方财富全球快讯 | confirmation | 已并入共享 collector | 已于 2026-04-07 完成本地与 private runtime 实抓验证 |
| `akshare:stock_info_global_ths` | AKShare / 同花顺全球快讯 | confirmation | 已并入共享 collector | 已于 2026-04-12 完成接线与本地验证 |
| `akshare:stock_notice_report` | AKShare / 公告快报 | confirmation | 迁入 Phase 1 | 已在雷达活跃使用 |

### B2. 已规划、应纳入统一新闻系统的源

| source_id | 当前形态 | lane | 去向 | 备注 |
| --- | --- | --- | --- | --- |
| `cninfo` | 公告 | confirmation | 迁入 Phase 1 | 雷达侧已规划，和统一系统目标一致 |
| `sse_disclosures` | 公告 | confirmation | 迁入 Phase 1 | 雷达侧已规划 |
| `szse_disclosures` | 公告 | confirmation | 迁入 Phase 1 | 雷达侧已规划 |
| `bse_disclosures` | 公告 | confirmation | 后续再接 | 第一阶段优先级低于深沪港美主干 |
| `gov_cn_policy_library` | 政策 | confirmation | 迁入 Phase 1 | 政策确认源 |
| `cls` | 财联社 | confirmation | 迁入 Phase 1 | 目标态应与共享系统汇合 |
| `stcn` | 证券时报 | confirmation | 迁入 Phase 1 | 补充确认源 |
| `cs_com` | 中证网 | confirmation | 迁入 Phase 1 | 补充确认源 |
| `cnstock` | 中国证券网 | confirmation | 兼容保留 | 可作为补充，但优先级略低 |
| `jiemian` | 界面新闻 | confirmation | 兼容保留 | 可作为补充 |
| `thepaper_finance` | 澎湃财经 | confirmation | 兼容保留 | 可作为补充 |
| `xueqiu_auxiliary` | 雪球社区 | signal | 后续再接 | 属于 signal lane，不应以雷达 news_policy 视角直接混入主体 |

### B3. 当前应排除在统一新闻系统主体之外的雷达源

以下条目虽然在雷达 manifest 中带有 `news_policy` 或紧邻新闻层，但当前不应进入统一新闻系统主体：

| source_id | 当前类型 | 去向 | 备注 |
| --- | --- | --- | --- |
| `miit_operation_monitoring` | `fundamental_proxy` | 排除 | 更接近部门运行监测 / proxy |
| `moa_monitoring` | `fundamental_proxy` | 排除 | 更接近行业运行 / 数据公报 |
| `nea_releases` | `fundamental_proxy` | 排除 | 当前在雷达里承担的是行业上下文角色 |
| `ndrc_releases` | `fundamental_proxy` | 排除 | 当前在雷达里承担的是行业上下文角色 |

这些源是否未来以“政策新闻文本源”重接，应另开定义，不应直接沿用当前雷达 proxy 语义。

## C. News Event Hub 当前定义层

`news_event_hub` 当前 registry 仍然是早期草案，它已经表达了方向，但和三处真实源资产还没有完全对齐。

### C1. 当前 registry 中可保留为共享系统目标态的源

| source_id | 当前定义 | lane | 去向 | 备注 |
| --- | --- | --- | --- | --- |
| `akshare_news_cctv` | AKShare / 央视新闻联播摘要 | confirmation | 已接入共享 collector | 已与真实 radar source map 对齐，并已于 2026-04-07 上线 |
| `akshare_stock_info_global_cls` | AKShare / 财联社全球快讯 | confirmation | 已接入共享 collector | 已与雷达现役 feed 对齐，并已于 2026-04-07 上线 |
| `akshare_stock_info_global_em` | AKShare / 东方财富全球快讯 | confirmation | 已接入共享 collector | 已与雷达现役 feed 对齐，并已于 2026-04-07 上线 |
| `akshare_stock_info_global_ths` | AKShare / 同花顺全球快讯 | confirmation | 已接入共享 collector | 已于 2026-04-12 作为共享兼容补充源接入 |
| `cailian_api` | 财联社 | confirmation | 迁入 Phase 1 | 目标态正确，但尚未启用 |
| `jinshi_api` | 金十 | confirmation | 迁入 Phase 1 | 目标态正确，但尚未启用 |
| `jinshi_telegram_channel` | 金十 Telegram 频道 | confirmation | 已接入共享 collector | 按 operator-managed relay 口径接入，并入共享快讯层 |
| `exchange_sse` | 上交所公告 | confirmation | 迁入 Phase 1 | 目标态正确 |
| `exchange_szse` | 深交所公告 | confirmation | 迁入 Phase 1 | 目标态正确 |
| `polymarket` | Polymarket | signal | 后续再接 | 方向正确，但当前未接 |
| `v2ex_all_feed` | V2EX 全部 feed | signal | 已接入共享 collector | 第一条低维护公开论坛 signal source |
| `reddit_market_forums` | Reddit 市场论坛 | signal | 已接入共享 collector | 第一条 Reddit 原生 signal source，当前覆盖 wallstreetbets / stocks / investing |
| `reddit_tracked_search` | Reddit 定向搜索 | signal | 已接入共享 collector | 承接研究对象级讨论补抓 |
| `xiaohongshu_tracked_search` | 小红书定向搜索 | signal | 暂停接入 | 暂不进入共享活跃抓取，后续如恢复再重新接回 browser-backed collector |
| `xueqiu_discuss` | 雪球讨论 | signal | 后续再接 | 方向正确，但当前未接 |
| `guba_eastmoney` | 股吧 | signal | 后续再接 | 方向正确，但当前未接 |

### C2. 当前 registry 中需要重写或替换的条目

| source_id | 当前定义 | 去向 | 备注 |
| --- | --- | --- | --- |
| `akshare_news_sina` | AKShare / 新浪财经 | 兼容保留 | 需与旧系统实际 source key 对齐 |
| `akshare_news_eastmoney` | AKShare / 东方财富 | 兼容保留 | 需与雷达中的 `stock_info_global_em` 等真实条目统一 |
| `akshare_news_10jqka` | AKShare / 同花顺 | 兼容保留 | 需确认长期是否仍纳入主体 |
| `investment_tracker_legacy` | 机会报告历史新闻库 | 兼容保留 | 迁移期桥接层，不应成为长期 canonical source |

## D. 统一后的 Phase 1 主干建议

### D1. confirmation lane 第一批主干

- `SEC 8-K / 6-K`
- `CNINFO`
- `SSE / SZSE`
- `HKEX`
- `gov.cn`
- `Fed press`
- `财联社`
- `Reuters`
- `证券时报`
- `界面`
- `东方财富全球快讯`

### D2. signal lane 第一批主干

- `weibo_tracked_mobile`
- `guba_tracked_direct`
- `v2ex_all_feed`
- `reddit_market_forums`
- `reddit_tracked_search`
- `xueqiu_public_timeline`
- `xueqiu_hot_stocks`
- `xueqiu_tracked_search`

### D3. 已明确重要但不作为 Phase 1 主干的源

- `Polymarket`
- `Reddit`
- `X / Twitter`
- `Bloomberg` 直连接入
- `金十官方 API`

这些源方向明确，但当前需要先解决接入稳定性、接口方式或优先级问题。

## 当前结论

当前系统不是“没有源”，而是“源已经分散地存在于多个旧链路中，但还没有一个统一 source inventory 和统一去向判断”。

现在已经足够支撑下一步工作：

1. 以本文件为基线，重写 `news_event_hub` 的 source registry
2. 把第一批确认源统一迁入 `private runtime`
3. 开始梳理旧接口和旧消费者如何切换到共享新闻库
