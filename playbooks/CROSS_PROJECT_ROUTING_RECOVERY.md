# FLASH CAST 跨项目路由阻断与恢复手册

## 适用范围

当 FLASH CAST 任务疑似把消息、计划任务或监控指令发送到 Vendure、CloudBridge、购物网站、ID 系统或其他项目时使用。

本手册只处理 FLASH CAST 项目内的路由控制和证据。它不能替代 Codex 全局权限中间件，也不能证明其他项目没有独立运行自己的计划任务。

## 立即收口

1. 停止当前 FLASH CAST 工作流继续派发，不撤销已有证据。
2. 只读查看疑似消息的计划任务 ID、目标任务 ID、目标标题、项目 ID 和 `cwd`。
3. 检查 `data/department-registry.json` 中是否存在完全一致的固定绑定。
4. 如果项目 ID、任务 ID、标题或 `cwd` 任一不一致，标记 `blocked_cross_project`。
5. 不在 FLASH CAST 总控中继续读取或处理目标外部项目内容。

## 路由预检

发送前对任务包或计划任务提示词计算 SHA-256；不要把正文写入路由日志。

```bash
python3 tools/flashcast_ops.py policy-check \
  --task-id <workflow-task-id> \
  --department operations \
  --action-id <unique-routing-action-id> \
  --action-class thread_message \
  --scope department:<target-department> \
  --source-project-id <LOCAL_PROJECT_ID> \
  --target-project-id <LOCAL_PROJECT_ID> \
  --target-department <target-department> \
  --target-thread-id <fixed-task-id> \
  --target-thread-title "<fixed-title>" \
  --target-cwd "<PROJECT_ROOT>" \
  --payload-sha256 <sha256>
```

只有同时出现 `status=allow` 和 `routing_status=routing_allowed` 才可使用 Codex 任务消息工具发送。

## 发送后回执

发送工具明确成功后，登记：

```bash
python3 tools/flashcast_ops.py receipt-record \
  --task-id <workflow-task-id> \
  --receipt-type dispatch_sent \
  --department <target-department> \
  --chat-task-id <fixed-task-id> \
  --policy-decision-id <routing-allow-decision-id> \
  --idempotency-key <stable-idempotency-key>
```

没有放行的 `policy_decision_id`、目标不匹配或路由决定已拒绝时，`dispatch_sent` 必须失败。

## 计划任务规则

- FLASH CAST 计划任务只能绑定注册表中的 6 个固定部门任务。
- 创建或更新前使用相同身份字段执行 `automation_create` 或 `automation_update` 预检。
- 临时发布监控必须在目标项目的专用发布任务中建立，不得由 FLASH CAST 总控代建。
- 临时监控提示词必须包含终止条件：成功、失败、取消或超时后关闭；无实质变化时保持安静。
- 不直接编辑 `~/.codex/automations/*/automation.toml`；使用 Codex 计划任务工具更新。

## 复核与恢复

1. 检查 `logs/policy-decisions.jsonl` 中是否有准确的 allow/deny 记录。
2. 对本次错误目标执行只读 shadow precheck，预期为 `blocked_cross_project`。
3. 对正确固定部门执行 precheck，预期为 `routing_allowed`。
4. 运行 `python3 -m unittest discover -s tools -p 'test_*.py'`。
5. 只有测试和两个 shadow precheck 都符合预期，才恢复 FLASH CAST 分派。

## 回滚

使用本次变更对应的逐文件 backup `change-id` 先运行 `rollback` 预演。真实恢复需要 `--apply --owner-approved`。不要删除追加式策略日志或历史聊天记录。
