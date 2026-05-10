# APILayer 候选评估（2026-04-16）

## 目的

这份文档用于评估 `APILayer` 生态里哪些 API 值得纳入 `News Event Hub` 的候选池。

评估口径不是“API 是否强大”，而是：

- 是否服务 `news / event` 主线
- 是否能进入当前 `Layer 1 Foundation`
- 是否适合作为 `confirmation lane` 或 `signal / recall` 补充层
- 是否会与当前已接能力高度重叠

## 当前结论

按当前仓库边界，`APILayer` 里最值得纳入候选池的是：

1. `Mediastack`
2. `Serpstack`
3. `Marketstack`
4. `Fixer` / `Exchangerates API`

其中：

- `Mediastack` 是最像“可直接接入共享 collector 的补充新闻 API”
- `Serpstack` 更像搜索发现层，适合替换或补强一部分 `Bing News RSS`
- `Marketstack` 不是新闻源，但可以作为后续 `event reaction` sidecar 候选
- `Fixer` / `Exchangerates API` 只适合做 FX 上下文补充，不适合进入当前主干

注：

- 截至 `2026-04-16`，我在 APILayer 官方文档里检索到的是 `Serpstack`
- 用户截图里出现的是 `Zenserp`
- 当前候选评估以 `2026-04-16` 的官方文档目录为准

不建议作为当前阶段候选的有：

- `Aviationstack`
- `Weatherstack`
- `IPstack` / `IPAPI`
- `Numverify`

它们与当前项目的 `news -> event -> mapping -> ranking` 主线契合度太低。

## 与当前仓库边界的关系

`News Event Hub` 当前定义是共享新闻/事件输入层，而不是通用市场数据仓或实时行情平台。

本仓库已有明确边界：

- 目标是沉淀 `事实获取 -> 事件化 -> 映射 -> 排序 -> 多消费者分发`
- 下游默认消费 `event`，不是文章列表
- `没有新增动作的纯价格播报` 不应作为高优先事件
- 当前阶段 `不把 OpenBB、价格、proxy、context、flow 等 sidecar 数据并入新闻系统`

因此，任何 APILayer 候选都应优先满足：

- 能补足新闻 coverage
- 能提高 discovery / recall
- 能服务 event 归并或证据确认

而不是单纯提供 quote / weather / flight / geolocation 数据。

## 候选排序

| 候选 | 推荐级别 | 适合位置 | 推荐原因 | 主要风险 |
| --- | --- | --- | --- | --- |
| `Mediastack` | `P0` | `confirmation/recall` 补充层 | 直接提供全球新闻 JSON，最贴近当前 collector 形态 | 与 `MarketAux`、现有 wire / RSS 存在重叠，容易引入重复传播链 |
| `Serpstack` | `P1` | `discovery` / `search recall` | 可把通用搜索从 `Bing RSS` 升级成结构化 SERP 接口 | 本质仍是搜索聚合，不是原始确认源；噪音控制很关键 |
| `Marketstack` | `P2` | `event reaction` sidecar | 可为事件补价格、ticker、exchange 元数据 | 容易把系统重心拉向行情库，偏离当前边界 |
| `Fixer` / `Exchangerates API` | `P3` | `macro normalization` sidecar | 可给汇率型宏观事件补标准化 FX context | 不是新闻源，对当前 Layer 1 主线帮助有限 |
| `Aviationstack` | `Not now` | 无 | 只有在做航空链条专题事件时才有边际价值 | 太垂直，不值得放进共享新闻主干 |
| `Weatherstack` | `Not now` | 无 | 仅对农业、能源、航运等少数链条有辅助价值 | 更像专题研究 sidecar，不适合共享主干 |

## 逐项判断

### 1. `Mediastack`

推荐结论：`最值得进入候选池`

适合原因：

- 官方定位就是全球新闻与博客文章 API
- 支持按 `date / timeframe / country / language / source / keywords / category` 过滤
- 形态上非常接近当前共享 collector 已经支持的 `JSON -> normalize -> article` 路径
- 可以作为 `MarketAux` 之外的第二条 `env-gated` 全球补充新闻 API

在本仓库中的合理定位：

- `不是主干官方确认源`
- `是补充 recall / coverage fill`
- `更适合 GLOBAL / US / non-CN-HK coverage gap`

建议接法：

- 新增候选 `source_id`: `mediastack_global_optional`
- `lane`: `confirmation`
- `source_type`: `api`
- 初始定位：`env-gated optional recall`
- 初始策略：只拉英文、只拉有明确 source/published_at/url 的条目，并启用严格 dedupe

主要风险：

- 与 `MarketAux` 和现有 wire / RSS 会有较强重叠
- source family 去重必须提前设计，否则会把二手转载误算成多源确认

### 2. `Serpstack`

推荐结论：`值得做 discovery 候选，但不要当确认源`

适合原因：

- 官方定位是结构化 Google SERP 数据接口
- 比当前若干 `Bing News RSS` 主题源更灵活
- 适合接到 `company discovery`、`macro topic discovery`、`targeted search recall` 这类路径

在本仓库中的合理定位：

- `不是 confirmation lane 主干`
- `是 search/discovery recall 层`
- `可以替代部分 Bing 聚合检索，但不能替代原始信源`

建议接法：

- 不先接入主 live collector
- 先作为 `run_company_discovery.py` 或未来 `on-demand recall` 的候选后端
- 仅在明确 query-driven 任务里调用，避免常驻高频轮询

主要风险：

- 搜索引擎聚合结果天然噪音更高
- 容易把搜索结果页面当成“新闻确认源”，从而污染 evidence ranking

### 3. `Marketstack`

推荐结论：`可以保留为中期 sidecar 候选，不建议现在接`

适合原因：

- 官方支持全球股票、指数、商品、ticker、exchange 元数据
- 如果后续要做 `event -> market reaction` 的辅助特征，它很顺手
- 可用于补 `ticker normalization`、上市地信息、基础价格响应窗口

不建议现在接的原因：

- 它不是新闻 API
- 当前项目明确定义不把价格与 sidecar 数据并入本阶段主线
- 一旦过早接入，容易把注意力从 `source coverage / event quality / mapping quality` 转到价格特征工程

更合理的未来位置：

- `Layer 2.5` 或 `event study` sidecar
- 不进入共享 `news_articles`
- 只为已成型 event 追加 reaction/context

### 4. `Fixer` / `Exchangerates API`

推荐结论：`只保留为低优先 sidecar 候选`

适合原因：

- 对汇率、跨币种报价、宏观事件的 FX 语境标准化有帮助
- 能服务少量 `macro event` 的上下文解释

不适合当前主干的原因：

- 不是新闻源
- 对 article/event 生成本身无直接贡献
- 只有在后续 consumer 确实需要稳定 FX normalization 时才值得接

### 5. `Aviationstack`

推荐结论：`当前不建议`

原因：

- 它是垂直行业数据 API，不是通用新闻或搜索接口
- 只有在未来明确建设 `航空 / 航运 / 机场 / 航司` 专题事件层时才可能有价值
- 目前放进共享主干只会带来 scope 漂移

### 6. `Weatherstack`

推荐结论：`当前不建议`

原因：

- 它的价值主要出现在农业、能源、航运、灾害交易等专题研究
- 对当前共享新闻底座的 `coverage / confirmation / recall` 不构成主缺口
- 更像专题研究线程按需调用的 sidecar，不是 hub 级基础设施

## 与现有已接能力的重叠关系

### 已有能力

- `MarketAux`: 已作为 `env-gated` 全球补充新闻 API 接入
- `Bing News RSS`: 当前承担若干主题搜索补充
- `PRNewswire` / `GlobeNewswire`: 已承担部分 wire 主干
- `Reddit` / `Xueqiu` / `V2EX`: 已承担 signal lane

### 因此更合理的增量是

- 用 `Mediastack` 补“全球新闻 recall”
- 用 `Serpstack` 补“结构化搜索发现”

而不是：

- 再加更多与主线无关的垂直数据 API
- 或过早把 `Marketstack` 这类行情 API 混入 Layer 1

## 建议的接入顺序

### 第一顺位

`Mediastack`

理由：

- 与当前架构最匹配
- collector 接入成本最低
- 最容易形成和 `MarketAux` 对照的第二条全球补充 API

### 第二顺位

`Serpstack`

理由：

- 最适合作为 `company discovery` / `macro recall` 增强器
- 可以有选择地替换一部分 `Bing RSS` 查询路径

### 第三顺位

`Marketstack`

理由：

- 只在我们明确要做 `event reaction` 或 `post-event market context` 时再接

## 推荐动作

如果只做一条最小下一步，建议是：

1. 把 `Mediastack` 加入 `Layer 1 source gap` 候选池
2. 明确它的定位为 `env-gated optional recall`
3. 暂不进入默认 active source
4. 先设计 `source_family` 与去重口径，再决定是否真正接入

如果要做第二条，则是：

1. 不把 `Serpstack` 放进固定轮询 collector
2. 只把它设计成 `query-driven discovery backend`
3. 优先服务 `run_company_discovery.py`

## 参考来源

以下结论基于 2026-04-16 检索到的官方 APILayer 文档：

- [APILayer docs 首页](https://docs.apilayer.com/)
- [Mediastack API 文档](https://docs.apilayer.com/mediastack/docs/api-documentation)
- [Mediastack Quickstart](https://docs.apilayer.com/mediastack/docs/quickstart-guide)
- [Serpstack API 文档](https://docs.apilayer.com/serpstack/docs/api-documentation)
- [Marketstack API 文档](https://docs.apilayer.com/marketstack/docs/api-documentation)
- [Marketstack Changelog](https://docs.apilayer.com/changelog/docs/marketstack)
- [Fixer API 文档](https://docs.apilayer.com/fixer/docs/api-documentation)
- [Exchangerates API 文档](https://docs.apilayer.com/exchangeratesapi/docs/api-documentation)
- [Aviationstack API 文档](https://docs.apilayer.com/aviationstack/docs/api-documentation)
- [Weatherstack API 文档](https://docs.apilayer.com/weatherstack/docs/api-documentation)
