---
name: flashcast-department-learning
description: "为 FLASH CAST 装修公司各部门记录、复盘并继承有证据支持的工作经验；适用于部门任务完成、失败复盘和下一次派工前的学习加载。"
---

# FLASH CAST 部门学习技能

这个 Skill 为部门保存有证据的经验。专业主Skill负责岗位方法，本Skill负责经验继承；开始前加载当前模式的只读有效学习视图，原记忆用于追溯，不能代替现行规则或真实授权。

## 什么时候使用

只要任务属于 FLASH CAST 装修公司虚拟员工的任一部门，就使用本 Skill，尤其是：

- 新任务开始前，需要知道这个部门以前确认过什么；
- 任务完成、失败或被阻断后，需要记录原因和下一步；
- 周复盘时，需要区分哪些经验已经验证、哪些仍是假设。

## 工作循环

### 1. 开始前加载记忆

确认当前注册 `department_id` 和 `task_id`，先执行只读命令：

```bash
python3 tools/flashcast_ops.py department-learning-effective --department <department_id>
```

视图的规则来源为现行AGENTS、运行规则和注册主Skill，包含准确文件哈希；经验按当前 `goal_delivery_runtime.model`、retired/status、supersedes及新鲜度过滤。`current_lessons` 可作本轮经验参考，`knowledge_reference` 仅供复核，`historical_references` 解释退出原因。每类都不将旧 `next_action` 输出为当前派工命令。要解释原事实时再读取：

1. `data/learning/department-learning-registry.json`
2. 当前部门的 `data/learning/departments/<department_id>.json`
3. `data/learning/department-inheritance.json`
4. 本次任务指定的最新证据文件

历史JSON、继承通知和所有历史字节保持原样。未声明适用当前模式的旧操作经验、retired角色/记录及已被有效supersedes替代的记录不进入当前规则；旧next_action仅解释原任务，新的动作仍由当前目标和真实授权决定。只继承当前部门相关且有证据的经验，不把别的部门猜测当事实。

### 2. 工作中区分三种内容

- **事实**：有文件、用户确认或可复核记录支持；
- **推断**：根据事实作出的判断，必须标为推断；
- **经验**：事实和结果共同证明后，才可以作为下次任务的默认参考。

缺少证据时写“待确认”，不能把数据缺失学习成“结果为 0”。

### 3. 完成后沉淀学习

部门先在自己的固定聊天提交非空结果，再冻结V2回传，最后记录有证据的学习事件。专业成果交唯一负责助理，助理已验收总结交总部知悉。建议命令：

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

学习记录包含部门、原任务、经验、证据、结果和原任务下一步。V2尽量记录 `data_window`、`last_verified_at`、`review_after`、`confidence`、`status`；冲突与替代使用 `conflicts_with` 和 `supersedes`。新记录默认绑定当前运行模式，不能改写旧记录补成当前经验；不能写入密码、Token、Cookie、OAuth、私钥或完整客户个人信息。

### 4. 下次任务怎么用

下一次任务先用有效视图核适用模式，再按需回读原记忆：

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
