---
name: flashcast-department-learning
description: "为 FLASH CAST 装修公司各部门记录、复盘并继承有证据支持的工作经验；适用于部门任务完成、失败复盘和下一次派工前的学习加载。"
---

# FLASH CAST 部门学习技能

这个 Skill 是所有部门共用的“学习底座”，给部门增加可继承的工作记忆，不是重新训练模型参数。每个部门还必须同时加载自己的专业 Skill：专业 Skill 负责岗位方法，本 Skill 负责经验记录和继承。部门每次工作前读取自己的记忆，工作后把经过证据支持的经验沉淀下来，下一次任务再读取使用。

## 什么时候使用

只要任务属于 FLASH CAST 装修公司虚拟员工的任一部门，就使用本 Skill，尤其是：

- 新任务开始前，需要知道这个部门以前确认过什么；
- 任务完成、失败或被阻断后，需要记录原因和下一步；
- 周复盘时，需要区分哪些经验已经验证、哪些仍是假设。

## 工作循环

### 1. 开始前加载记忆

确认当前 `department_id` 和 `task_id`，然后按顺序读取：

1. `data/learning/department-learning-registry.json`
2. 当前部门的 `data/learning/departments/<department_id>.json`
3. `data/learning/department-inheritance.json`
4. 本次任务指定的最新证据文件

只继承当前部门相关的规则和经验，不把别的部门的猜测当作自己的事实。

### 2. 工作中区分三种内容

- **事实**：有文件、用户确认或可复核记录支持；
- **推断**：根据事实作出的判断，必须标为推断；
- **经验**：事实和结果共同证明后，才可以作为下次任务的默认参考。

缺少证据时写“待确认”，不能把数据缺失学习成“结果为 0”。

### 3. 完成后沉淀学习

部门必须先在自己的 Codex 聊天框直接回复老板/总控，再写结构化回传，最后记录一条学习事件。建议命令：

```bash
python3 tools/flashcast_ops.py department-learning-record \
  --department analytics \
  --task-id fc-20260831-example \
  --memory-type paid_search_review \
  --lesson "累计窗口不能代替单日数据；点击不能直接定义为有效线索" \
  --signal "Ads 有点击但主要转化为 0" \
  --evidence "data/google-ads/2026-08-01_2026-08-30_campaigns.csv" \
  --outcome "暂不扩量，先核对转化追踪和销售真值" \
  --next-action "补齐单日导出并核对 GA4 到 Google Ads 映射" \
  --confidence high \
  --data-window "2026-08-01..2026-08-31" \
  --last-verified-at "2026-08-31" \
  --review-after "2026-09-07"
```

学习记录必须包含部门、任务、经验、证据、结果和下一步。V2 应尽量记录 `data_window`、`last_verified_at`、`review_after`、`confidence`、`status`；有冲突或替代关系时使用 `conflicts_with` 和 `supersedes`。不能写入密码、Token、Cookie、OAuth、私钥或完整客户个人信息。

### 4. 下次任务怎么用

下一次任务先读本部门记忆：

- `inherited_lessons` 是从总控和旧资料带来的起始经验，必须结合当前证据复核；
- `verified_lessons` 可以作为工作起点，但仍要核对当前数据；
- `provisional_lessons` 只能作为待验证假设；
- `blocked_patterns` 是需要避免重复踩坑的模式；
- 新事实与旧经验冲突时，保留冲突，优先最新且可验证的证据。
- `review_after` 已过的经验只能作为过期参考，不能冒充当前事实；
- 没有 V2 新鲜度字段的旧记录按 `legacy/provisional` 加载，不自动删除，也不自动升级为已验证。

## 重要边界

这个 Skill 只负责工作记忆、经验继承和复盘，不会自动修改 Google Ads、GA4、GTM、网站、CMS、CRM，也不会自动联系客户。外部执行仍按项目审批规则处理。

详细字段和状态见 [references/learning-schema.md](references/learning-schema.md)。
