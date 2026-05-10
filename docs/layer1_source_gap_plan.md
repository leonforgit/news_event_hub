# Layer 1 Source Gap Plan

Updated: 2026-04-12

## 结论先行

截至当前这一轮收口完成后，旧 `investment_report` catalog 里属于共享新闻层职责的 source 已经基本清干净：

- `legacy_catalog_in_scope_missing_from_shared = 0`
- 当前 audit 剩余缺口只剩 `investor_*` commentary layer，不再属于 `News Event Hub` 第一层主职责

所以 Layer 1 的下一阶段重点，已经不再是“继续清旧私有源”，而是：

1. 把已经认可但还没进 `live collector` 的高优先 source 真正接入 live path
2. 补新的高价值主干源，让共享新闻接口从“可用”走向“足够强”

## 当前 Layer 1 的真实短板

### 1. `source map` 已扩大，但 `live path` 还不够厚

当前 registry 状态：

- `source_registry_total = 67`
- `source_registry_enabled = 55`

当前 live collector catalog 状态：

- `catalog_total = 48`
- `enabled_not_in_live_catalog = 9`

这意味着当前问题已经不是“定义上没有”，而是“很多已认可 source 还没有固定抓取”。

### 2. `signal lane` baseline 已闭环，下一步主做质量治理

当前 enabled lane 结构：

- `confirmation = 46`
- `signal = 9`

当前 enabled 的 signal source：

- `weibo_tracked_mobile`
- `guba_tracked_direct`
- `v2ex_all_feed`
- `reddit_market_forums`
- `reddit_tracked_search`
- `xueqiu_public_timeline`
- `xueqiu_hot_stocks`
- `xueqiu_tracked_search`（browser-backed）

其中前七条已进入 live collector catalog，`xueqiu_tracked_search` 已切到独立 browser signal catalog。`xiaohongshu_tracked_search` 当前已按“暂时不接入”口径撤出活跃抓取。

也就是说，当前问题已经从“signal 没接进去”切换为：

- `signal` 的 freshness / quality 压噪
- 研究型定向搜索的排序与筛选
- 是否继续扩到 `Twitter` 等第二批平台

### 3. 全球直连 newswire 仍在补厚，但第一批官方源已经落下

当前 live path 的强项：

- `SEC 8-K / 6-K`
- `CLS telegraph`
- `AKShare cls / em / ths / cctv`
- `PRNewswire`
- `GlobeNewswire`
- `金十 Telegram relay`
- `Marketaux`
- `Reuters` 聚合

当前这一层的短板，已经不再是“完全没有官方 newswire”，而是：

- `Business Wire` 这类 feed/account 化入口还没接进来
- 中文授权型高价值 wire 还没有进入正式直连层

### 4. 仍偏“搜索聚合 + 补充抓取”，而不是“更强的直连接口”

当前 enabled source 中，`rss` 仍然很多，且不少是 Bing 聚合口径。

这能作为迁移期补充，但如果要把 Layer 1 做成真正稳定的上游，下一步必须继续提高：

- 直连 disclosure / official release 比例
- 直连高质量 newswire / API 比例
- signal 原生采集比例

## 下一阶段分层计划

### P0: 先把现有资产真正接进 live path

这些 source 已经在共享 registry 中被认可，而且都是当前最该优先进入固定抓取的对象。

#### P0-A. 公告与硬信息主干

- `cninfo_sz_latest`
- `cninfo_sh_latest`
- `hkex_tracked_latest`
- `akshare_stock_notice_report`

当前进展：

- 已完成 `cninfo_sz_latest`
- 已完成 `cninfo_sh_latest`
- 已完成 `akshare_stock_notice_report`
- 已完成 `hkex_tracked_latest`

目标：

- 让 A 股 / 港股公司硬信息不再主要依赖历史回填
- 把中国 / 港股公司的 live disclosure 真正并入共享 article layer

#### P0-B. 中国公司新闻补充主干

- `company_stcn_html`
- `company_jiemian_stock_html`
- `company_jiemian_company_html`

当前进展：

- 上述三条已全部接入 live collector 并完成 `private runtime` 首轮实抓

目标：

- 把中国公司新闻补充层从“定义中已认可”推进到“live collector 已固定抓取”
- 降低对主题型 Bing 聚合源的依赖

#### P0-C. signal baseline 主干

- `weibo_tracked_mobile`
- `guba_tracked_direct`
- `v2ex_all_feed`
- `reddit_market_forums`
- `reddit_tracked_search`
- `xueqiu_public_timeline`
- `xueqiu_hot_stocks`
- `xueqiu_tracked_search`（browser-backed）

目标：

- 让 `signal lane` 第一次真正进入 live path
- 建立 signal health / freshness / noise 控制的真实运行面

当前阻塞：

- 共享 target resolver 已完成，并已把 `guba_tracked_direct` / `weibo_tracked_mobile` 接进 live collector
- `v2ex_all_feed` 已接入 live collector，并完成 `private runtime` 首轮实抓
- `reddit_market_forums` 已接入 live collector，并完成 `private runtime` 首轮实抓
- `reddit_tracked_search` 已接入 live collector，并完成 `private runtime` 手动重跑验证
- `xueqiu_public_timeline` / `xueqiu_hot_stocks` 已完成 `private runtime` 首轮实抓
- `xueqiu_tracked_search` 已切到 browser-backed collector，并完成 `private runtime` 首轮强制实抓
- `xiaohongshu_tracked_search` 当前已按“暂时不接入”口径撤出活跃共享抓取
- 当前结论已经从“signal baseline 仍在建设”切换为“signal baseline 已完成，剩余问题是质量治理与 Phase 2 扩展”

### P1: 再补新的高质量 confirmation sources

这一层不是旧资产迁移，而是为了让共享新闻接口真正变强。

优先补“公司公告 / 公司 release / 高质量新闻分发”。

#### P1-A. 官方 / 半官方公司 release wires

已核对到的官方入口：

- `PR Newswire RSS`
  - 官方页：[PR Newswire RSS](https://www.prnewswire.com/rss/)
  - 当前官方说明明确提供 RSS，且支持主新闻 feed 与发布合作
- `Business Wire RSS / Atom`
  - 官方页：[Business Wire feed options](https://www.businesswire.com/help/feed-options)
  - 当前官方说明明确提供 RSS 与 full-text Atom，可按关键词定制
- `GlobeNewswire`
  - 官方页：[GlobeNewswire press release content](https://www.globenewswire.com/fr/newswire-press-release-content)
  - 当前官方说明明确支持 Reader Account、RSS news release feeds 与 custom delivery

这三类源的价值：

- 能补更直接的公司新闻发布链
- 对美股 / 海外公司 event recall 很有帮助
- 比单纯 Bing 主题聚合更稳、更接近源头

当前进展：

- 已完成 `PRNewswire` 四条官方 RSS feed 接入并部署：
  - `prnewswire_all_releases`
  - `prnewswire_financial_services`
  - `prnewswire_general_business`
  - `prnewswire_policy_public_interest`
- 已完成 `GlobeNewswire` 两条官方 RSS feed 接入并部署：
  - `globenewswire_press_releases`
  - `globenewswire_mna`
- 已完成一批“公开补充源”的 live 接线与部署：
  - `xinhua_fortune_html`
  - `macro_oil_bing`
  - `macro_china_bing`
  - `macro_us_china_bing`
  - `company_cnbc_bing`
  - `company_marketwatch_bing`
- `Business Wire` 当前暂不强上：
  - 官方说明确认提供 RSS / full-text Atom
  - 但更偏定制 feed / account 形态
  - 当前浏览器侧可确认帮助页与目录页存在，但公共入口响应不稳定
  - 下一步应按稳定 feed 方案接，而不是临时抓一个不稳定入口

#### P1-B. 全局补充 API

- `Marketaux`
  - 官方页：[marketaux](https://www.marketaux.com/)
  - 文档页：[Marketaux API docs](https://www.marketaux.com/documentation)
- `Mediastack`
  - 官方文档目录：[Mediastack docs](https://docs.apilayer.com/mediastack/docs/api-documentation)
  - 当前定位：第二条 APILayer 生态下的全球新闻补充 recall API
- `Serpstack`
  - 官方文档目录：[Serpstack docs](https://docs.apilayer.com/serpstack/docs/api-documentation)
  - 当前定位：`on-demand company discovery` 的结构化搜索后端，不进入固定 live polling

当前官方文档确认：

- 有 `/v1/news/all`
- 有 `/v1/news/sources`
- 支持 symbols / entities / language / source filtering

这一层的定位不是长期唯一主干，而是：

- 作为全球补充 recall
- 用于弥补非中美港主干范围的 coverage 空洞
- 当前进展：
  - `marketaux_global_optional` 已接入 env-gated live collector
  - `mediastack_global_optional` 已注册到 env-gated live collector
  - `serpstack_company_discovery_optional` 已注册到 shared source map，并接到 `run_company_discovery.py`
  - 本地与 `private runtime` 首轮实抓已通过
  - 已增加 `max_runs_per_24h = 72` 的 rolling 24h quota guard，主动避开 `100/day` 限额
  - 当前仍应把它视为“补充 recall 层”，而不是长期唯一主干

#### P1-C. 中文高价值 wire / 快讯授权层

- `财联社`
  - 当前共享层已通过 `CLS telegraph` 与 `AKShare cls` 保有兼容接法
  - 但还不能把它视为“已确认公开 self-serve 官方 API 的正式直连主干”
- `金十`
  - 当前已通过 `jinshi_telegram_channel` 作为operator-managed  Telegram relay 接入共享层
  - 但这不等于“已拿到金十官方 API / 授权型直连接口”
  - 如果要升级为正式核心主干，仍应按授权 / 数据合作路径推进

### P2: 继续保留但不优先激活的层

#### P2-A. 主题型 Bing 补充源

当前已经进入共享 collector 的：

- `company_mna_bing`
- `company_spin_bing`
- `company_asset_sale_bing`
- `company_capacity_bing`
- `company_financing_bing`
- `company_resources_bing`
- `company_new_industry_bing`

它们当前应视为：

- 已收口
- 可运行
- 但不是 Layer 1 长期最核心主干

#### P2-A1. 已验证的公开补充源

当前已验证稳定、并进入 live path 的：

- `xinhua_fortune_html`
- `macro_oil_bing`
- `macro_china_bing`
- `macro_us_china_bing`
- `company_cnbc_bing`
- `company_marketwatch_bing`

这些源当前的定位是：

- 用来补厚 Layer 1 的公开新闻覆盖
- 作为主干 disclosure / newswire 的外侧补充层
- 只有在本地与 `private runtime` 都实抓稳定后才保留在 live path

#### P2-A2. 已试抓但暂不保留的候选补充源

当前已经试抓，但因空结果或响应不稳定暂不保留在 live path 的：

- `macro_rates_bing`
- `macro_middleeast_bing`
- `macro_defense_policy_bing`
- `company_bloomberg_bing`
- `company_wsj_bing`
- `company_ap_bing`
- `company_ft_bing`
- `company_financial_media_bing`

这些候选当前应视为：

- 已纳入候选池
- 需要重写 query 或等待更稳定入口
- 不应为了“看起来源更多”而直接推上线

#### P2-B. signal rumor 占位源

当前已纳入共享 source map，但默认不启用：

- `company_rumor_bing`
- `company_rumor_china_bing`

原因：

- 当前 query 实抓结果为空
- 如果强行启用，只会让 health 面板产生假警报

## 推荐执行顺序

1. 先把 `P0-A` 公告主干接进 live path
2. 再把 `P0-B` 中国公司新闻补充层接进 live path
3. 然后把 `P0-C` signal baseline 跑起来
4. 再推进 `P1-A` 剩余的 `Business Wire`
5. 并行补更多“能稳定实抓”的公开补充源
6. 再决定 `Marketaux` 这类补充 API 的成本 / 稳定性 / 依赖边界
7. 最后推进授权型中文 wire 的正式直连方案

## 这一轮之后的判断口径

接下来判断 Layer 1 是否“够强”，不要再只看 registry 总数，而要看下面四个指标：

1. `enabled source` 中有多少真正进入 live path
2. `confirmation lane` 是否已经覆盖美股 / A 股 / 港股的 live disclosure 主干
3. `signal lane` 是否已经有真实固定抓取，不再只是定义占位
4. 是否已经有一批非 Bing 聚合的直连高质量上游
