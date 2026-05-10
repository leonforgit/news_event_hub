# Agent Reach Dual-Mode Plan

Updated: 2026-04-07

## 目标

把 `Agent-Reach` 相关能力拆成两层：

1. 本地 `skill / operator tool`
   - 供研究、定向补抓、临时检索使用
   - 允许带登录态、带人工介入、带较强平台依赖

2. `private runtime` 上的共享抓取层
   - 只保留适合固定运行、适合定时抓取、适合共享入库的那一部分
   - 默认不依赖频繁人工登录和脆弱浏览器会话

## 总原则

- `News Event Hub` 不是把 `Agent-Reach` 整体搬进来
- `Agent-Reach` 更适合作为：
  - 平台接入参考
  - 本地研究工具层
  - signal / backfill 的补充能力
- 共享主路径仍然应该以：
  - 可持续
  - 可定时
  - 可观测
  - 可回写共享库
  为标准

## 双模式定义

### A. 本地模式

适用场景：

- 研究新公司时的临时定向补抓
- 某个对象的社交讨论补充检索
- 需要登录态、Cookie、浏览器状态的平台
- 人工触发的深挖，而不是固定定时抓取

输出要求：

- 优先回到标准化 `article / social signal` 结构
- 如果只是一次性研究补充，也至少要保留可回写共享层的接口空间

### B. private runtime 模式

适用场景：

- 定时抓取
- 稳定公开入口
- 不需要频繁人工干预
- 可以进入 source health 和 shared exports

运行要求：

- 有明确 source id
- 有固定 scheduler class
- 有 source health
- 不把脆弱登录态当作 Layer 1 主干默认依赖

## 平台分层建议

### 1. Twitter / X

本地模式：

- 适合
- 适合作为研究型定向补抓与舆情补充

private runtime 模式：

- 先做 `on-demand`，不先做 `daily scheduled`
- 原因：
  - Cookie / 登录态依赖强
  - 平台风控高
  - 作为 shared signal 主干的稳定性不足

建议定位：

- `local-first`
- `wsl on-demand optional`

### 2. Reddit

本地模式：

- 适合
- 可作为研究型补充检索

private runtime 模式：

- 已可做
- 当前第一条原生 shared source 已接入 live collector：
  - `reddit_market_forums`
  - 覆盖 `wallstreetbets / stocks / investing`
- 当前第一条 tracked shared source 也已接入 live collector：
  - `reddit_tracked_search`
- 后续再补：
  - 更细粒度 subreddit / query

建议定位：

- `shared scheduled baseline`
- `shared tracked search + local/broader expansion later`

### 3. 小红书

本地模式：

- 适合
- 对消费品、品牌、渠道口碑研究有价值

private runtime 模式：

- 当前已作为 browser-backed tracked search 进入共享层：
  - `xiaohongshu_tracked_search`
  - 更适合研究对象级定向检索，而不是公共热榜主干

建议定位：

- `browser-backed tracked search`
- `local-first for broader exploration`

### 4. 公众号

本地模式：

- 适合
- 对公司深挖、行业深挖、中文长文补充有价值

private runtime 模式：

- 可以做 `on-demand retrieval`
- 不建议一开始就做广义定时抓全量
- 更合理的是：
  - 给定实体 / 主题 / 文章链接时拉取

建议定位：

- `local-first`
- `wsl on-demand selective`

### 5. 微博

本地模式：

- 适合

private runtime 模式：

- 适合
- 而且这里优先用我们已经有的原生共享 collector，不优先依赖 Agent-Reach

建议定位：

- `shared scheduled`
- 当前继续调优 `weibo_tracked_mobile`

### 6. V2EX

本地模式：

- 适合

private runtime 模式：

- 已适合
- 当前第一条原生 shared source 已接入 live collector：
  - `v2ex_all_feed`
  - 覆盖 `V2EX 全部` Atom feed

建议定位：

- `shared scheduled`

### 7. 雪球

本地模式：

- 非常适合
- 对公司研究和中文投资讨论补充有明显价值

private runtime 模式：

- 可以做，但前提是共享登录态与 Cookie 管理到位
- 更适合从 `tracked search / on-demand` 开始，而不是直接做全量定时广抓

当前判断：

- `Agent-Reach` 对我们最有直接帮助的就是 `雪球` 这一块
- 当前共享登录态已经稳定
- `雪球 public timeline / hot stocks` 已进入共享 live collector
- `tracked search` 直接走 HTTP 会命中 WAF，但现在已经切到 browser-backed collector

建议定位：

- `local-first`
- `wsl public signal scheduled + tracked/on-demand via browser collector`

## 推荐执行顺序

### Phase A. 本地能力先全

- [ ] 配好本地 `Twitter`
- [ ] 配好本地 `Reddit`
- [ ] 配好本地 `小红书`
- [ ] 配好本地 `公众号`
- [ ] 配好本地 `微博`
- [ ] 配好本地 `V2EX`
- [ ] 配好本地 `雪球`
- [ ] 为本地研究线程提供统一入口，而不是分散记命令

### Phase B. private runtime 只落稳定共享源

- [ ] 微博：继续沿用并调优当前原生 shared collector
- [x] V2EX：已作为 shared scheduled signal source 接入
- [x] Reddit：market forums baseline 已进入 shared scheduled
- [x] Reddit：tracked search 已进入 shared scheduled
- [x] 雪球：公共 signal 已进入 shared scheduled
- [x] 雪球：tracked search 已改成 browser-backed collector
- [x] 小红书：tracked search 已进入 browser-backed collector
- [ ] 公众号：先做 `on-demand`

### Phase C. 再决定哪些能升级为定时抓取

- [ ] 评估 Twitter 是否值得进 private runtime 定时层
- [ ] 评估 Reddit 更多 subreddit / query 是否值得扩成第二批定时源
- [x] 雪球 tracked search 已在 browser-backed collector 下进入共享 tracked scheduled
- [x] 小红书 tracked search 已在 browser-backed collector 下进入共享 tracked scheduled
- [ ] 明确哪些平台永远只保留本地模式

## 对 `News Event Hub` 的直接价值

### 立刻有帮助的

- 本地研究型定向补抓
- signal lane 候选扩展
- 公众号 / 雪球 / Reddit / Twitter 的对象研究补充检索

### 不应误解的

- 它不是共享新闻数据库
- 它不是 event/ranking 系统
- 它不是 consumer export 层
- 它不应替代当前 Layer 1 主干 collector

## 当前结论

最合理的路线不是：

- “把 7 个平台一次性全做成 private runtime 定时抓取”

## 2026-04-07 执行进展

- 本地 `Agent-Reach` 运行位已装好：
  - `runtime/agent_reach/.venv`
  - `scripts/agent_reach_cli.sh`
  - `scripts/run_agent_reach_watch.sh`
- `private runtime` 已完成安装、auth 同步与 systemd skeleton 部署，但默认不启用
- 当前共享 auth 导出里，已稳定持久化的平台集合为：
  - `Twitter / X`
  - `Reddit`
  - `雪球`
  - `微博`
  - `小红书`
- 因此下一步的关键是：
  - 把适合共享化的那部分真正接进 `scheduled`
  - 对会命中 WAF / policy block 的平台补 browser-backed collector

1. 本地先把 7 个平台都变成可用研究工具
2. private runtime 只先接最稳的那部分
3. 再把适合共享化的能力逐步回写到 `News Event Hub`
