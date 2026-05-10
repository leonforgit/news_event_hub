# AGENTS.md

适用于整个 `量化/news_event_hub/` 子工作区。

默认继承上层工作区的通用规则；如果这里更具体，以这里为准。

## Workspace Identity

- 这是 `共享新闻/事件基础设施` 子工作区
- 不是日报项目
- 不是行业雷达项目
- 不是某个对象研究工作区

任何实现、文档或脚本都应优先服务 `多消费者复用`，而不是偏向某一条下游产品线。

## Canonical Scope

- 本地 repo 内保留：
  - 产品定义
  - 架构定义
  - ranking 规则
  - source registry
  - schema source
  - 小型映射表与样例
  - 稳定脚本入口
- 主 runtime 保留在 `private runtime`
  - `news_event.db`
  - collector cache
  - source health
  - 运行日志
  - 中间聚类结果

不要把大规模原始新闻正文、抓取缓存或 SQLite 主库直接提交进仓库。

## Design Rules

- 新闻系统按两条赛道建模：
  - `fact lane`
    - 官方、公告、主流财经 API、稳定媒体
  - `signal lane`
    - 社交、论坛、赔率、讨论区、早期异动线索
- 排名最小消费单位默认不是文章，而是事件
- 任何 consumer-facing 输出都应从共享层消费，不应重新发明自己的抓取口径
- 研究过程里的定向抓取结果也应能回写共享底座
- 不要把“背景介绍/旧闻复述/无投资映射的公司动态”当作高优先事件

## Directory Rules

- `docs/`
  - 放 durable 定义和设计，不放临时聊天式笔记
- `config/`
  - 放 schema、source registry、ranking 配置
- `scripts/`
  - 放稳定入口；不要把一次性探索脚本长期留在这里
- `data/`
  - 放小型耐久样例和映射
- `runtime/`
  - 这里只作为本地占位与说明层，不视为主 runtime

## Git Hygiene

- 这是一个定义先行的子工作区，结构性文档更新应尽量做成清晰的小提交
- 如果上层仓库已有无关 dirty paths，不要顺手卷进去
- 在开始写实现代码之前，先把产品和架构定义文档稳定下来
- 结束一个稳定阶段前，运行：
  - `python3 scripts/check_git_hygiene.py --strict`

## Done Checklist

- 新增或修改的 durable 定义文档已反映到 `README.md` 或 `STATUS.md`
- 没有把主 runtime 数据库、缓存或大体量语料直接提交进仓库
- 讨论阶段的结论已经进入 `docs/` 的 source-of-truth 文档，而不是只留在聊天上下文里
- 如果完成了一个稳定阶段，已运行 `python3 scripts/check_git_hygiene.py --strict`
