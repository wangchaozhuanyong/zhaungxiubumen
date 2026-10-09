现行协作入口：`playbooks/department-system-current.md`。按注册表核本角色专业职责与批准子Skill，普通在途不持有总部协调轮次；本候选须独立QA和总部采用。

# 准确QA2 R0评审入口

本文件描述候选采用后的入口；本轮未在运行根目录登记准入或QA verdict。唯一默认评审仍为固定`qa`。QA2是`qa-technical`，不会被别名成`qa`，不取得生产准入。

总控先在原工作流准确选出独立制作部门和唯一QA2评审，冻结真实candidate JSON、版本与哈希。必须已经存在的准确工作流；不能靠计划创建重开旧任务。计划必填字段见 `examples/qa2-review-plan.json`。该文件只是脱敏字段示例，假身份/零哈希不能通过，不是实际准入证据。

采用后由总控在明确项目根下运行：

```bash
python3 tools/qa_review_plan.py \
  --project-root <PROJECT_ROOT> \
  --task-id <准确原任务> --plan <项目内冻结评审计划.json>
```

这一步核准确task/action/class/scope/CV/candidate pin、固定制作/评审/总部身份、当前健康与同项目同cwd，并把准确计划pin追加到原事件链、绑定快照；不改旧回执。仅允许 `internal_control_candidate`、`read_only_candidate`，`risk_level=R0`，`single_final_reviewer=true`，外部/生产标志明确false。候选JSON须同任务、同CV、同制作部门且pin匹配当前原字节。

随后正常路由预检与实际发送仍由总控承担，本CLI不发送消息。QA2的实际 `dispatch_sent` 须冻结计划pin及candidate pin，scope与计划一致；原任务中其后非空固定QA2 `chat_ack`、其后准确 `outbox_received` 齐全。派工/ACK/outbox/QA verdict时间有序且不在未来。QA2 V2须包含准确 `fixed_chat_task_id/candidate_version/risk_level=R0`，以及：

```json
{
  "review_identity": {
    "task_id": "fc-synthetic-qa2-example-v1",
    "action_id": "review-synthetic-control",
    "action_class": "internal_control_candidate",
    "scope": "project:synthetic-control:exact-v1",
    "candidate_version": "synthetic-v1",
    "candidate_sha256": "0000000000000000000000000000000000000000000000000000000000000000"
  },
  "qa_verdict": "pass",
  "production_write_allowed": false,
  "external_permission_issued": false,
  "production_release_eligible": false,
  "chat_reply": {
    "nonempty": true,
    "in_current_fixed_department_chat": true,
    "ref": "synthetic-only-replace-with-actual-native-ref",
    "sha256": "0000000000000000000000000000000000000000000000000000000000000000"
  }
}
```

实际值须来自真实当前固定聊天，不能用上面假值。QA2的 `qa_verdict` 原生回执仍用原receipt-record入口，部门明确 `qa-technical`，准确action/class/scope及当前QA2 outbox pin。原制作V2同CV且绑定所审candidate。没有当前派工/非空ACK/outbox或任一身份/字节不匹配时拒绝，不能通过重算伪造回执链补齐。原链SHA只是防意外篡改，不是对聊天来源的数字签名。

准确R0 PASS/BLOCKED接入原生状态、事件复核、总部有限close_scope与同任务在途/既有QA结果关联。原生发布门禁继续要求固定QA1的准确网站候选；QA2 R0 PASS不能替代它。历史回执哈希不改，旧任务无显式计划时继续QA1。评审计划冻结后不能换范围/版本/角色，变更需总控按原任务引用安排明确下一版本或子任务。
