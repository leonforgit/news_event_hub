# Shared Ranking Features V1

## 目的

这份文档定义第二层共享 ranking feature 的 v1 范围。

重点不是直接给出一套最终 consumer 分数，而是明确：

- 哪些特征应该沉淀在共享层
- 哪些特征适合所有下游复用
- 哪些只应由下游做轻量调权

## 核心原则

共享层应提供：

- 对事件本身的理解
- 对确认程度的理解
- 对研究价值的理解

共享层不应直接写死每个 consumer 的偏好。

## 分层原则

### Shared Feature

所有主要消费者都应该能直接复用。

### Consumer Weight

各下游可以在共享 feature 之上做轻量加权。

### Consumer-Specific Output

最终展示口径、排序阈值、文案风格仍由各下游决定。

## Event Shared Features V1

### 1. freshness

回答：

- 这是不是今天真正新增的变化

主要看：

- `first_seen_at`
- `last_seen_at`
- 当前 article 是否带来新的增量

### 2. delta_strength

回答：

- 这次更新相对之前变化有多大

例如：

- rumor 变 confirmation
- headline 变实锤
- 政策从定调变细则

### 3. confirmation_strength

回答：

- 这件事被确认到什么程度

主要依赖：

- `confirmation_count`
- `source_mix`
- source trust tier

### 4. lane_mix

回答：

- 这是纯事实层事件，还是 signal 已经先行、confirmation 后补

它不是最终分数，而是共享解释维度。

### 5. specificity

回答：

- 这件事讲得够不够具体

例如是否明确：

- 主体
- 动作
- 金额
- 时间
- 对手方

### 6. entity_relevance

回答：

- 这件事和公司 / 行业 / 主题的映射有多强

没有映射关系的事件，在投资研究里价值通常有限。

### 7. researchability

回答：

- 这件事能不能导出下一步研究动作

例如：

- 去看哪家公司
- 去验证哪条产业链
- 去跟踪哪条政策影响

### 8. investability_hint

回答：

- 这是不是一个更像“可研究机会”的事件，而不是一般资讯

它不是最终投资结论，只是共享层的倾向判断。

## Article Shared Features V1

article 层只保留基础 feature，不决定最终优先级。

建议保留：

- `source_trust_score`
- `freshness_score`
- `specificity_score`
- `source_originality_score`
- `content_completeness_score`
- `entity_resolvability_score`

## Shared Penalties V1

共享层应直接维护的基础惩罚包括：

- `background_penalty`
- `stale_penalty`
- `duplicate_event_penalty`
- `weak_mapping_penalty`
- `late_recap_penalty`
- `single_dirty_source_penalty`

## 不应放在共享层的内容

以下更适合留给 consumer：

- 组合持仓相关权重
- watchlist 私有偏好
- 某个行业雷达专属扩散逻辑
- 某份报告的版面和栏目限制

这些不应写死在共享层 feature 里。

## 共享层输出建议

V1 建议共享层至少产出：

- `event_rank_score`
- `event_rank_flags`
- 一组可解释 shared features

例如：

```json
{
  "freshness": 0.92,
  "confirmation_strength": 0.78,
  "entity_relevance": 0.81,
  "researchability": 0.88,
  "flags": {
    "signal_only": false,
    "background_penalty": 0.0,
    "late_recap_penalty": 0.2
  }
}
```

## 与 Consumer 的边界

共享层回答：

- 这是什么事件
- 有多新
- 有多确定
- 有多值得研究

consumer 回答：

- 对我这个工作流来说，应不应该更靠前
- 应该如何展示
- 应该导出什么具体动作

## 当前结论

shared ranking feature v1 的目标不是直接取代所有下游决策，而是先让所有下游建立在同一套事件理解之上。

只有共享层先统一，consumer-specific ranking 才有意义。
