# Layer 1 Foundation Plan

## 这一层是什么

Layer 1 是 `News Event Hub` 的地基层。

它的任务不是解释新闻价值，而是稳定地产出共享 article 输入。

## 这一层负责什么

- `news_event.db`
- `source_registry`
- baseline collectors
- fixed schedule / timer
- source health
- article 标准化
- 去重与最小质量控制

## 当前状态

当前已达到：

- 统一数据库已部署到 `private runtime`
- 首批 article backfill 已完成
- 第一版 live collector 已落地
- `systemd timer` 已启动
- 已有 `source_health` 写入

当前还未完成：

- 源覆盖远未到理想状态
- `signal lane` live coverage 明显不足
- collector 稳定性和失败恢复还未系统化
- targeted research 写回入口还未建立
- 虽然 `legacy_catalog_in_scope_missing_from_shared = 0`，但高价值 source 仍有一大批没有进入固定 live path

## 当前阶段目标

这一层当前目标不是“完工”，而是从 `最小可用` 继续走向 `可持续可扩展`。

## 当前重点问题

### 1. 源覆盖不均衡

当前 live collector 主体仍偏 `confirmation lane`。

更具体的 source gap 已单列到：

- [layer1_source_gap_plan.md](docs/layer1_source_gap_plan.md)

### 2. 频率分层还很初步

虽然已经有 10 分钟 tick + 源级间隔，但还只是第一版调度。

### 3. 运行治理还不完整

还缺：

- 更系统的失败重试策略
- 更细的 source health 解释
- 更明确的 collector 观测口径

## 近期 checklist

- [x] 在 `private runtime` 建立统一数据库
- [x] 完成第一轮 article backfill
- [x] 建立 live collector 主干
- [x] 建立 `systemd` 固定抓取
- [x] 写入 `source_health`
- [x] 清空旧 `investment_report` catalog 中新闻层 in-scope source 的共享收口缺口
- [ ] 把 `cninfo` / `hkex` / `company_*_html` 这批高价值已认可 source 接入 live path
  当前已完成 `cninfo_sz_latest`、`cninfo_sh_latest`、`company_stcn_html`、`company_jiemian_stock_html`、`company_jiemian_company_html`、`xinhua_fortune_html`
- [ ] 把 `weibo_tracked_mobile` / `guba_tracked_direct` 接入 live path，建立第一版 signal baseline
  当前已完成 `hkex_tracked_latest`、`guba_tracked_direct`、`weibo_tracked_mobile` 接线；其中 `hkex/guba` 已实跑通过，`weibo` 当前仍需 freshness 调优
- [x] 评估并接入第一批直连 newswire / API 主干源
  当前已完成 `PRNewswire` 四条 RSS feed 与 `GlobeNewswire` 两条 RSS feed 的 live collector 接线及 `private runtime` 首轮实抓
- [x] 接入第一条 Telegram relay 快讯源
  当前已完成 `jinshi_telegram_channel` 接线，并验证本地与 `private runtime` 首轮实抓
- [x] 接入第一条 env-gated 补充 API
  当前已完成 `marketaux_global_optional` 接线，并验证本地与 `private runtime` 首轮实抓；同时已加 `rolling 24h quota guard`
- [ ] 继续推进第二批直连 newswire / API 主干源
  下一步优先面向 `Business Wire` 的稳定 feed/account 形态与授权型中文 wire
- [x] 补一批“可稳定实抓”的公开补充源
  当前已完成 `macro_oil_bing`、`macro_china_bing`、`macro_us_china_bing`、`company_cnbc_bing`、`company_marketwatch_bing`
  已试抓但暂未保留到 live path 的候选包括 `macro_rates_bing`、`macro_middleeast_bing`、`macro_defense_policy_bing`、`company_bloomberg_bing`、`company_wsj_bing`、`company_ap_bing`、`company_ft_bing`、`company_financial_media_bing`
- [ ] 建立更明确的 collector runbook
- [ ] 建立 targeted research 回写入口

## 第一层完成标志

不是“源全接完”，而是至少满足：

1. 共享库稳定运行
2. 高频与低频源都有明确调度口径
3. `confirmation lane` 和 `signal lane` 都进入 live path
4. source health 可观测
5. 下游不再把第一层当作一次性试验品
