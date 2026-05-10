# Start Here

这是 `News Event Hub` 的单一路由入口。

如果你从一个新线程进入这个子工作区，默认按下面顺序读取：

1. [STATUS.md](STATUS.md)
   - 先看当前阶段、已定边界、未决问题
2. [README.md](README.md)
   - 再看这个工作区是什么、不是什么、目录怎么理解
3. [AGENTS.md](AGENTS.md)
   - 再看本地工作规则与 done checklist
4. [product_definition.md](docs/product_definition.md)
   - 理解这个系统到底为谁服务、解决什么问题
5. [workspace_three_layer_plan.md](docs/workspace_three_layer_plan.md)
   - 理解这个工作区的三层动态规划骨架
6. [layer1_foundation_plan.md](docs/layer1_foundation_plan.md)
   - 看地基层当前做到哪里、还缺什么
7. [layer2_shared_event_ranking_plan.md](docs/layer2_shared_event_ranking_plan.md)
   - 看共享中间层当前主线是什么
8. [event_v1_definition.md](docs/event_v1_definition.md)
   - 看 `event v1` 的正式定义、边界和归并原则
9. [news_system_layer_model_v1.md](docs/news_system_layer_model_v1.md)
   - 看共享新闻系统到底应该承载哪些层、哪些层不该由 Hub 承载
10. [mapping_layer_v1.md](docs/mapping_layer_v1.md)
   - 看 `event -> entity` 的共享映射 contract
11. [opportunity_transition_layer_v1.md](docs/opportunity_transition_layer_v1.md)
   - 看共享事件如何升级成 `opportunity candidate`
12. [implementation_checklist_v1.md](docs/implementation_checklist_v1.md)
   - 看当前未完成项、推进顺序和哪些已经被 check 掉
13. [article_to_event_merge_rules_v1.md](docs/article_to_event_merge_rules_v1.md)
   - 看 `article -> event` 的规则和保守策略
14. [shared_ranking_features_v1.md](docs/shared_ranking_features_v1.md)
   - 看 shared ranking feature 的范围和 consumer 边界
15. [layer3_consumer_integration_plan.md](docs/layer3_consumer_integration_plan.md)
   - 看下游消费契约和迁移方向
16. [layer3_consumer_contract_v1.md](docs/layer3_consumer_contract_v1.md)
   - 看三个 consumer adapter 的最小输出契约
17. [legacy_interface_migration.md](docs/legacy_interface_migration.md)
   - 看旧接口如何迁到共享层
18. [current_system_audit.md](docs/current_system_audit.md)
   - 了解机会报告与行业雷达目前各自怎么处理新闻、问题出在哪里
19. [architecture.md](docs/architecture.md)
   - 理解共享新闻/事件库与各下游产品的关系
20. [ranking_v1.md](docs/ranking_v1.md)
   - 理解 ranking 该如何设计
21. [acceptance_criteria.md](docs/acceptance_criteria.md)
   - 了解什么时候这个系统才算达到可用标准
22. [integration_plan.md](docs/integration_plan.md)
   - 理解行业雷达、日报、研究工作流怎样接这层底座
23. [news_event_hub_handoff_2026-04-11.md](docs/news_event_hub_handoff_2026-04-11.md)
   - 看本轮已定共识、缺口和继续推进顺序

## 当前结论

- 这个项目已经确定要独立存在于 `量化/` 下
- 它是共享基础设施子工作区，不是行业雷达或日报的附属目录
- 主运行数据库默认应放在 `private runtime`
- 当前顶层骨架已经明确为三层动态规划：
  - Foundation
  - Shared Event & Ranking
  - Consumer Integration
- 当前也已明确：三层是顶层骨架，`Hub` 内部再拆成六个实现职责层；两者不是替代关系
- 第三层现在已经有最小可用 adapter，不再只是规划文档
- 当前已进一步明确：`映射层` 与 `机会转移层` 也属于 `News Event Hub` 本体，而不是后续下游私有补丁
- 当前还新增了一项长期但非当前任务的方向：
  - 后续要基于历史 `event + mapping` 累积识别“目前不热、但频率在缓慢抬升”的长期趋势信号

## 当前不做的事

- 暂不直接开写整套 collector 实现
- 暂不直接改造日报主脚本
- 暂不把行业雷达现有运行库直接改成共享新闻库

## 推荐下一步

- 继续补强 Layer 1，而不是把它误判为已经完成
- 继续提纯 `Mapping Layer` 和 `Opportunity Transition Layer` 的质量，而不是停在第一版 contract
- 继续提纯 point-in-time export 的 panel 口径和历史稳定性，给 `Radar / research / Qlib` 做更稳的下游消费
- 长期再做 `trend signal detection`，不要和当前 contract 落地阶段混在一起
