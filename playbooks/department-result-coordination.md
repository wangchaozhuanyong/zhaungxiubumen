现行协作入口：`playbooks/department-system-current.md`。按注册表核本角色专业职责与批准子Skill，普通在途不持有总部协调轮次；本候选须独立QA和总部采用。

# 准确结果协调接入

本模块调用实际 `workflow_control.record_result_handoff` 的候选入口；不是原先未调用的 ownership 原型。运行根目录未安装。协调身份固定为原 `task_id`、发送部门、候选版本和最终 outbox SHA-256。创建占用前核对唯一原生 queued 行、哈希链、当前 outbox 字节、V2 和注册固定聊天；不扫描历史、不发送消息、不授予发布权限。

`tools/result_coordination.py` 的 SQLite 位于调用项目 `logs/result-coordination.sqlite3`，共享锁位于 `logs/.result-coordination.lock`。所有占用修改使用共享 flock 和 `BEGIN IMMEDIATE`；入口在持有协调锁时调用原生工作流，因此顺序始终为协调锁→SQLite 短事务→原生工作流锁。原生非控制通知继续沿既有入口，不打断聊天。

`operations-assistant` 只能 claim、核验、保存预核/下一动作草稿、续期、释放和准确移交；不能写最终 `controller_received`、`controller_decision`、`controller_followthrough`，即使没有占用也拒绝。活跃占用下，总控必须提供准确 owner、token、fence 和 result_key；活跃助理占用会阻止总控，须先明确释放或移交。role/owner 字段只是审计元数据，不是身份认证或权限凭据。

TTL 为 1–900 秒；bool/浮点数和超过 900 秒均拒绝。重复相同唤醒请求沿用 token/fence；过期占用必须有明确恢复原因，恢复/移交/释放均推进 fence，使旧持有人失效。预核记录 completed、partial、qa_rework、external_blocked、queue_failed 或 failed 时仍须给出下一负责人、动作和解除条件；这些状态都是草稿，不产生原生决策，不结束业务目标。新 scope 只有在准确冻结 outbox 已存在且完全一致时才可记录。

原生最终动作前冻结请求语义和全部 outbox/证据字节指纹，并预留 event/idempotency effect。运行异常保留 uncertain；下一次先回读原生准确幂等键及字段/证据。如果原生已追加，返回同一 record_id 并完成协调记录；不会再次调用原生副作用。如果未找到追加，必须 `recover-reservation` 提供原因，回读证明未追加后才标 retry_ready。原生明确 `WorkflowError` 校验拒绝时，也先回读证明不存在该动作，再释放该失败校验预留，使原有“修正输入后重试”行为可继续。字节变化、不同语义、损坏或缺失的已提交记录保持拒绝。

入口包装协议：

```python
with result_coordination.handoff_guard(root, request) as admission:
    if admission.replay_record is not None:
        return ({**admission.replay_record, "result": "duplicate_ignored"},
                [result_handoff_path(root, request["task_id"])])
    record, paths = _native_record_result_handoff(root, request)
    admission.complete(record)
    return record, paths
```

CLI 使用项目内输入 JSON，不隐式创建工作区：

```bash
python3 tools/result_coordination.py claim --root /absolute/project --input /absolute/project/drafts/claim.json
python3 tools/result_coordination.py readback --root /absolute/project --input /absolute/project/drafts/readback.json
```

claim 输入：`identity`（四字段）、`role`、`owner`、`request_id`、可选 `ttl_seconds`。readback 输入仅 `identity`。renew/release/transfer/precheck 使用相同 identity/role/owner 与完整 `claim` 回读对象；release 加 `reason`；recover 加 `request_id`/`reason`；transfer 加 `target_role`/`target_owner`/`request_id`；precheck 加 `status`/`next_owner`/`next_action`/`unblock_condition`。recover-reservation 输入为 `handoff_request` 和 `reason`。CLI 本身只操作协调数据；不写原生最终决策。

集成检查运行 `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest test_result_coordination -v`，调用候选实际入口和原有真实工作流 fixture。临时项目始终位于本候选 `.test-tmp`，结束后由 tempfile 清理。29 项通过，详见 `result-coordination-tests.log`：独立连接/同时争抢、精确身份、TTL/fence、助理拒绝、转移/释放、草稿状态、原生已追加后的崩溃回读、未追加后的显式恢复、证据变化与旧入口默认行为。

负责人：总部助理制作候选；operations 收取后交固定 QA，决定采用。候选未安装、未产生正式 QA 结论、未改变生产权限；根总控负责后续准确源指纹合并和回滚包。采用前必须核对当前源文件与候选冻结基线，保留并行修改，不以候选整目录覆盖运行目录。

rework3：原生入口与guard共用事件schema；未知/只读/错事件字段、错误类型和evidence_paths先拒绝，零reservation/原生追加/成功audit。已知coordinator_role/scope在通知中只是登记/重试上下文，不是权限；旧行不改，重复只返回retry_context，新增首行保存上下文。final操作的真实routine_grant.scope仍准确验权，operations的scope仅reported_scope；历史缺上下文字段按原生事实读回，不伪补旧账。
