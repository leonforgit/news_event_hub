# Agent Reach Runtime

Updated: 2026-04-07

## 当前状态

- 本地 `Agent-Reach` 已完成安装：
  - `runtime/agent_reach/.venv`
  - `scripts/agent_reach_cli.sh --version` 已通过
- 本地 watch 已完成手动 smoke：
  - `scripts/run_agent_reach_watch.sh`
- `private runtime` 已完成：
  - 脚本同步
  - 远端安装
  - auth state 同步
  - systemd skeleton 部署
- `private runtime` 已补到的 support tools：
  - `mcporter`
  - `yt-dlp` with `--js-runtimes node`
- 已新增远端复核脚本：
  - `scripts/check_runtime_agent_reach_stack.sh`
- `private runtime` 当前保持：
  - `unified-news-agent-reach-watch.timer = disabled`
  - `unified-news-agent-reach-watch.service = disabled`
- 当前 `private runtime` 手动 doctor readiness 已记录在 health output
- 当前共享 auth state 已导出到平台 inventory，且已稳定持久化的平台集合为：
  - `Twitter / X`
  - `Reddit`
  - `雪球`
  - `微博`
  - `小红书`
- 当前已新增 browser-backed signal runtime：
  - `runtime/browser_signal/.venv`
  - `scripts/run_browser_signal_collector.py`
  - `config/browser_signal_catalog_v1.json`
  - `unified-news-browser-signal-collector.service`
  - `unified-news-browser-signal-collector.timer`
- 当前 `xueqiu_tracked_search` 已切到 browser-backed collector，并完成 `private runtime` 首轮强制实抓
- 当前 `Reddit` 已有第一条原生 shared source 进入 live collector：
  - `reddit_market_forums`
  - 覆盖 `wallstreetbets / stocks / investing`
  - 已完成 `private runtime` 首轮实抓
- 当前 `Reddit tracked search` 已进入 live collector：
  - `reddit_tracked_search`
  - 已完成 `private runtime` 手动重跑验证
- 当前 `小红书 tracked search` 已按“暂时不接入”口径撤出活跃 browser-backed collector：
  - `xiaohongshu_tracked_search`
  - source map 与 auth state 仍保留，但当前不进入共享定时抓取
- `2026-04-07` 已补通：
  - `Reddit` 登录态已重新沉淀进共享 storage-state
  - 本地与 `private runtime` Reddit auth inventory 已通过
  - `雪球` 登录态已成功沉淀进共享 storage-state
  - 本地与 `private runtime` 雪球 auth inventory 已通过
  - `微博` 登录态已成功沉淀进共享 storage-state
  - 本地与 `private runtime` 微博 auth inventory 已通过
  - `小红书` 登录态已成功沉淀进共享 storage-state，但当前不对应活跃共享源
- 当前共享 auth 稳定平台集合：
  - `Twitter / X`
  - `Reddit`
  - `雪球`
  - `微博`
  - `小红书`
- 为避免单次 `state-save` 覆掉之前已成功的平台 auth，已新增：
  - `scripts/merge_playwright_storage_state.py`

## 当前目标

为 `News Event Hub` 准备两套默认不启用的 `Agent-Reach` 运行骨架：

1. 本地 `skill / operator tool`
2. `private runtime` 上的安装、认证同步、watch service/timer 模板

这一步的目标是：

- 先把入口与运行位搭好
- 先把认证状态沉淀下来
- 先让本地和 private runtime 都具备“随时可启用”的条件
- 但暂时不默认开启定时任务

## 本地运行位

默认安装路径：

- `runtime/agent_reach/.venv`

本地命令入口：

- `scripts/install_agent_reach.sh`
- `scripts/agent_reach_cli.sh`
- `scripts/run_agent_reach_watch.sh`

本地认证状态：

- `state/auth/agent_reach/playwright_shared_auth.json`
- `state/auth/agent_reach/platforms/`

本地状态输出：

- `state/agent_reach/doctor_latest.txt`
- `state/agent_reach/cookie_inventory_latest.json`

## private runtime 运行位

默认远端路径：

- `/opt/news-event-hub/runtime/agent_reach/.venv`

远端脚本：

- `/opt/news-event-hub/scripts/install_agent_reach.sh`
- `/opt/news-event-hub/scripts/agent_reach_cli.sh`
- `/opt/news-event-hub/scripts/run_agent_reach_watch.sh`

远端认证状态：

- `/opt/news-event-hub/state/auth/agent_reach/playwright_shared_auth.json`
- `/opt/news-event-hub/state/auth/agent_reach/platforms/`

远端状态输出：

- `/opt/news-event-hub/state/agent_reach/doctor_latest.txt`
- `/opt/news-event-hub/state/agent_reach/cookie_inventory_latest.json`

远端日志：

- `/opt/news-event-hub/logs/agent_reach_watch.log`

## 当前脚本

### 本地安装与调用

- `scripts/install_agent_reach.sh`
  - 在本地或远端安装 `agent-reach`
  - 默认使用 repo 自己的 `runtime/agent_reach/.venv`

- `scripts/agent_reach_cli.sh`
  - 对 repo 内运行位的稳定 wrapper
  - 默认把 repo 内 `.venv/bin` 注入 `PATH`，让 `agent-reach doctor` 能识别同环境里的 CLI 依赖

### 认证状态

- `scripts/export_agent_reach_cookie_inventory.py`
  - 从 Playwright storage state 提取平台级 cookie inventory

- `scripts/sync_runtime_agent_reach_auth.sh`
  - 把本地 auth state 与平台 cookie inventory 同步到 `private runtime`

### private runtime 部署

- `scripts/deploy_runtime_agent_reach_stack.sh`
  - 把脚本与 systemd 模板部署到 `private runtime`
  - 执行远端安装
  - 默认补装 `mcporter`
  - 如本地已有 auth state，则一并同步
  - 默认不执行 `enable --now`

- `scripts/check_runtime_agent_reach_stack.sh`
  - 复核远端版本、unit 状态、support tools、doctor 输出与 cookie inventory

## systemd 模板

已提供但默认不启用：

- `config/systemd/unified-news-agent-reach-watch.service`
- `config/systemd/unified-news-agent-reach-watch.timer`

当前用途：

- 周期性运行 `agent-reach doctor`
- 生成 cookie inventory / doctor 输出
- 为后续 `signal lane` 平台化接入预留运行位

## 当前边界

这套运行骨架当前还不是：

- `Twitter / 公众号` 等全部平台的最终共享抓取实现
- 全平台定时抓取方案

它当前只是：

- 安装位
- 认证位
- watch 位
- 可部署但默认不启用的 systemd 骨架
- 以及已被 `News Event Hub` 复用的 browser-backed signal collector 运行位

## 推荐顺序

1. 先在本地完成安装与 auth state 沉淀
2. 再把远端 private runtime 安装位与 systemd 模板部署好
3. 再逐个平台决定是否进入 `signal lane` 的：
   - `scheduled`
   - `tracked search`
   - `on-demand`

## 当前结论

这一步已经完成了“本地可跑 + private runtime 已就位但默认不启用”的目标。

下一步的真正重点不是继续搭运行骨架，而是：

1. 继续稳住多平台 auth persistence
2. 调优已接入的 browser-backed signal 质量
3. 决定 `Twitter / 公众号` 是否进入第二批共享化接入
