# FLASH CAST 部门学习记录规范

## 部门记忆文件

路径：`data/learning/departments/<department_id>.json`

核心字段：

- `department`：部门 ID；
- `display_name`：部门名称；
- `verified_lessons`：已经有证据和结果支持的经验；
- `provisional_lessons`：有一定信号但还没有重复验证的经验；
- `blocked_patterns`：已确认会造成误判、返工或风险的模式；
- `last_updated_at`：最近一次更新；
- `event_count`：该部门学习事件总数。

每条经验至少包含：

```json
{
  "lesson_id": "稳定唯一值",
  "task_id": "来源任务",
  "lesson": "下次工作可复用的具体经验",
  "signal": "观察到的信号",
  "evidence": ["项目内证据路径"],
  "outcome": "这次实际结果",
  "next_action": "下一次怎么做",
  "confidence": "high|medium|low",
  "status": "verified|provisional|retired",
  "observed_at": "ISO-8601 时间",
  "data_window": "YYYY-MM-DD..YYYY-MM-DD",
  "last_verified_at": "YYYY-MM-DD 或 ISO-8601",
  "review_after": "YYYY-MM-DD",
  "freshness_status": "current|stale|review_date_missing|legacy_or_review_date_missing",
  "conflicts_with": ["lesson_id"],
  "supersedes": ["lesson_id"],
  "record_version": "2.0"
}
```

V1/旧记录保持可读。缺少 `record_version`、`review_after` 或 `last_verified_at` 时，加载器将其标记为 legacy/provisional 或待复核；不自动删除、改写或升级为 `verified`。

## 学习状态

- `verified`：事实、结果和后续复核相互支持；
- `provisional`：有信号，但需要下一次任务继续验证；
- `retired`：被更新证据推翻或不再适用，保留记录但不得作为默认规则。

## 质量规则

1. 经验必须能指向证据路径。
2. 缺失数据不等于零结果。
3. 单次偶然结果默认只能是 `provisional`，除非用户明确确认或有充分复核。
4. 学习事件追加写入 `logs/learning-events.jsonl`，不覆盖历史事件。
5. 学习记忆不能保存秘密或完整客户个人资料。
6. 到达 `review_after` 后状态为 `stale`，必须用新证据复核。
7. 冲突不覆盖：用 `conflicts_with` 保留关系；确定替代时用 `supersedes`。
