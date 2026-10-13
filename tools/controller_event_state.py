"""Derive a bounded controller wait plan from current receipts, never send tools.

The checkpoint is a reference, not proof that a department is still running.
This reader replaces the stale, manually maintained event-continuation cache.
It does not wake an ended chat, grant permissions or mutate business history.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path

import workflow_control as workflow


def _future_wait(row: dict, now: dt.datetime) -> bool:
    stamp = workflow._parse_observed_at(row.get("next_check_at"))
    return (row.get("followthrough_status") in {"external_wait_registered", "blocked_with_owner"}
            and all(row.get(k) for k in ("next_owner", "next_action", "unblock_condition"))
            and stamp is not None and stamp > now)


def _owned_goals(root: Path, role: str, plan: dict, queue: dict, now: dt.datetime) -> list[dict]:
    """Isolate bad tasks; the runtime's exact proofs remain the only closure gate."""
    from goal_delivery_runtime import restore_goal, enabled, completion_obligations, _task_block, _current_goal_owners
    inventory = []
    current_owners = _current_goal_owners(root)
    for path in sorted((root / workflow.WORKFLOW_DIR).glob("*.json")):
        exact_owner = 'ownership_unresolved'
        try:
            raw = workflow.read_json(path)
            if raw.get('task_id') != path.stem:
                raise workflow.WorkflowError("current task snapshot identity differs from its exact path")
            if current_owners.get(path.stem, raw.get("goal_delivery", {}).get("responsible_assistant")) != role:
                continue
            exact_owner = role
            snapshot = restore_goal(root, raw)
            if not enabled(root, snapshot) or snapshot["goal_delivery"]["responsible_assistant"] != role:
                continue
            task = snapshot["task_id"]
            receipts, invalid = workflow._validate_receipt_chain(root, task)
            if invalid or workflow.validate_workflow_events(root, task):
                raise workflow.WorkflowError("owned goal current event/receipt chain requires recovery: " + task)
            goal = snapshot["goal_delivery"]
            completion = queue.get('completion_status', {}).get(task)
            if completion is None:
                completion = completion_obligations(root, snapshot, receipts)
            records = {r.get("action_id") or "unresolved:" + str(r.get("original_receipt")): r
                       for r in plan.get("collaboration_state", []) if r.get("task_id") == task}
            records.update({r.get("action_id") or "unresolved:" + str(r.get("original_receipt")): r
                            for r in queue.get("collaboration_not_proven", []) if r.get("task_id") == task})
            not_proven = [r for r in records.values() if r.get("proof_state") == "NOT_PROVEN"]
            sent_actions = {r.get("action_id") for r in receipts if r.get("receipt_type") == "dispatch_sent"}
            prepared = [a["action_id"] for a in goal.get("approved_actions", [])
                        if a.get("action_class") == "thread_message" and a.get("required_for_completion", True)
                        and a.get("action_id") not in records and a.get("action_id") not in sent_actions]
            latest = {}
            for row in workflow._result_handoff_rows(root, task):
                latest.setdefault(workflow._result_identity(row), {}).update(row)
            external = [r for r in latest.values() if _future_wait(r, now)]
            task_queue = [r for r in queue.get("results", []) + queue.get("followthrough_results", []) if r.get("task_id") == task]
            collaboration_pending = [r for r in queue.get("collaboration_pending", []) if r.get("task_id") == task]
            remaining = [r for r in queue.get('completion_followthrough', []) if r.get('task_id') == task]
            waiting = [r for r in plan.get("tasks", []) if r.get("task_id") == task]
            returned = [key for key, value in records.items() if value.get("proof_state") == "PROVEN" and value["status"] == "result_received"]
            state = snapshot.get("current_state")
            closed = state == 'closed' and (completion.get('state') == 'legacy_exact_scope'
                                           or not completion['missing'] and not completion['blockers'])
            if state == 'closed' and not closed:
                raise workflow.WorkflowError("closed snapshot lacks exact complete acceptance: " + task)
            completion_waits = [row['wait_dependency'] for row in remaining
                                if row.get('status') == 'named_completion_dependency_wait']
            deferred = bool((external
                             or completion_waits and len(completion_waits) == len(remaining)) and not waiting and not prepared
                            and not task_queue and not collaboration_pending and not not_proven
                            and not any(row.get('actionable') for row in remaining))
            if task_queue:
                stage, action = "result_decision_or_followthrough_pending", "收取准确结果，验收并登记真实下一动作"
            elif closed:
                stage, action = "formally_closed_scope", "本准确范围已正式收口；后续任务另列，不自动关闭父目标"
            elif state in {"failed", "cancelled"}:
                stage, action = "terminal_without_completion", "保留失败/取消原因，恢复需新明确授权；不称完成"
            elif not_proven:
                stage, action = "collaboration_NOT_PROVEN_requires_exact_source", "恢复本准确协作原生来源、thread/turn/message 身份和原文字节；不重复派工"
            elif collaboration_pending:
                stage, action = "collaboration_followthrough_required", "收取原协作结果并落实准确下一动作或关闭已验范围"
            elif prepared:
                stage, action = "prepared_not_sent", "核准确许可与现场身份后执行已批准动作；prepared 不算派发"
            elif any(row.get('actionable') for row in remaining):
                stage, action = "remaining_completion_followthrough", "沿原目标落实全部残余完成标准；已关闭小范围不关闭整目标"
            elif deferred:
                stage, action = "named_external_wait", (completion_waits[-1]['next_action'] if completion_waits else external[-1]['next_action'])
            elif state == "qa_passed":
                stage, action = "acceptance_record_requires_execution_or_dependency", "沿原许可落实当前版本实际执行、后检、采用、试点或具名依赖"
            elif returned or state == "evidence_received":
                stage, action = "returned_result_requires_acceptance_or_execution", "唯一负责助理验收整项标准并落实许可内接续"
            elif state == "qa_blocked":
                stage, action = "rework_required", "沿原任务修复准确未通过范围并提交新版本"
            elif waiting:
                stage, action = "inflight_event_wait", "其他可执行事项处理后，等待本冻结批次真实事件并保存实际 cursor"
            else:
                stage, action = "responsibility_requires_reconciliation", "恢复原任务真实进展与最小下一动作；ACK、idle、空队列不算完成"
            inventory.append({"task_id": task, "department": role, "next_owner": role,
                              "primary_owner": goal["primary_owner"], "parent_task_id": goal.get("parent_task_id"),
                              "snapshot": workflow.file_digest(root, str(path.relative_to(root))),
                              "native_workflow_state": state, "status": stage, "next_action": action,
                              "completion_criteria": goal["completion_criteria"], "completion_contract_state": completion['contract_state'],
                              "completion_obligations": completion, "remaining_followthrough": remaining,
                              "formally_closed_scope": closed, "business_goal_closed": False,
                              "prepared_action_ids": prepared, "returned_action_ids": returned, "collaboration_records": records,
                              "collaboration_pending": collaboration_pending, "collaboration_not_proven": not_proven,
                              "collaboration_proof_state": "NOT_PROVEN" if not_proven else "PROVEN" if records else "NOT_APPLICABLE",
                              "external_waits": external, "requires_action": not (closed or deferred or state in {"failed", "cancelled"}),
                              "unblock_condition": (completion_waits[-1]['unblock_condition'] if completion_waits else external[-1].get('unblock_condition')) if deferred else "当前准确结果、全部冻结标准及实际接续证明",
                              "next_check_at": (completion_waits[-1]['next_check_at'] if completion_waits else external[-1].get('next_check_at')) if deferred else None})
        except (workflow.WorkflowError, ValueError, OSError, KeyError, TypeError, AttributeError) as exc:
            inventory.append({**_task_block(path.stem, exact_owner, exc), 'department': exact_owner,
                              'status': 'blocked_evidence_invalid', 'requires_action': False, 'formally_closed_scope': False})
    return inventory


def _legacy_unmapped(root):
    """Read legacy tasks separately, so one obsolete pin cannot hide modern work."""
    from result_coordination import result_lane, goal_delivery
    from goal_delivery_runtime import _task_block, deduplicate_records
    tasks = {p.stem for directory, suffix in ((workflow.WORKFLOW_DIR, '*.json'), (workflow.RESULT_HANDOFF_DIR, '*.jsonl'))
             for p in (root / directory).glob(suffix)}
    old, errors = [], []
    for task in sorted(tasks):
        try:
            if goal_delivery(root, task) is not None:
                continue
            local = workflow.result_handoff_pending(root, [task])
            old.extend(row for row in local.get('results', []) + local.get('followthrough_results', [])
                       if result_lane(root, row)['lane'] == 'legacy_unmapped')
        except (workflow.WorkflowError, ValueError, OSError, KeyError, TypeError, AttributeError) as exc:
            errors.append(_task_block(task, 'operations', exc))
    return deduplicate_records(old), errors


def _modern_derive(root: Path, registry: dict, role: str, now: dt.datetime) -> tuple[dict, dict]:
    from goal_delivery_runtime import wait_plan, pending as assistant_pending, deduplicate_records
    binding = registry.get(role, {}).get("chat_binding", {})
    if (not binding.get("task_id") or not binding.get("project_id") or Path(binding.get("cwd", "")).resolve() != root
            or (role != "operations" and registry.get(role, {}).get("coordination_authority", {}).get("routine_decisions") is not True)):
        raise ValueError("current registered coordinator identity required")
    roles = ([r for r, item in registry.items() if r != "operations" and item.get("coordination_authority", {}).get("routine_decisions") is True]
             if role == "operations" else [role])
    queue = {key: [] for key in ("results", "followthrough_results", "collaboration_pending", "collaboration_not_proven",
                                'HQ_knowledge_pending', 'named_due_dependencies', 'named_waiting_dependencies',
                                'notification_delivery_pending', 'completion_followthrough', 'task_errors')}
    plans, inventory, errors, checkpoint_sources = {}, [], [], []
    for owner in roles:
        # A corrupt wait cursor affects waiting only; arrived work still projects.
        cursor_path = root / "logs/goal-delivery-waits" / (owner + ".json")
        try:
            cache = workflow.read_json(cursor_path)
            cursors = cache.get("cursors", {})
            if cache and cache.get("coordinator_role") != owner:
                raise ValueError("current assistant cursor identity mismatch")
            if not isinstance(cursors, dict) or any(not isinstance(v, str) or not v.strip() for v in cursors.values()):
                raise ValueError("actual saved native cursors required")
            cursor_error = None
        except (workflow.WorkflowError, ValueError, OSError, KeyError, TypeError, AttributeError) as exc:
            cache, cursors, cursor_error = {}, {}, {'coordinator_role': owner, 'reason': str(exc), 'stage': 'wait_cursor_recovery'}
            errors.append(cursor_error)
        item = assistant_pending(root, owner)
        scoped = {'results': item['pending'], 'followthrough_results': item['followthrough_pending'],
                  **{key: item.get(key, []) for key in ('collaboration_pending', 'collaboration_not_proven', 'completion_followthrough')},
                  'completion_status': item.get('completion_status', {})}
        plan = wait_plan(root, owner, cursors=cursors, queue=item)
        if cursor_error:
            plan.update(batches=[], cursor_recovery_required=True)
        plans[owner] = plan
        for key in queue:
            source = 'pending' if key == 'results' else 'followthrough_pending' if key == 'followthrough_results' else key
            queue[key].extend(item.get(source, []))
        queue['task_errors'].extend(plan.get('task_errors', []))
        inventory.extend(_owned_goals(root, owner, plan, scoped, now))
        checkpoint_sources.append({"coordinator_role": owner,
                                   "cursor_record": workflow.file_digest(root, str(cursor_path.relative_to(root))) if cache else None,
                                   "native_observed_at": cache.get("observed_at"), "source": "owned_goal_snapshots_and_recorded_native_wait"})
    for key in queue:
        queue[key] = deduplicate_records(queue[key], delivery=key == 'notification_delivery_pending')
    inventory = deduplicate_records(inventory)
    errors.extend(queue['task_errors'])
    errors.extend(row for row in inventory if row.get('status') == 'blocked_evidence_invalid')
    if role == "operations":
        from direct_system_repair import inventory as direct_inventory
        try:
            inventory.extend(direct_inventory(root))
        except (workflow.WorkflowError, ValueError, OSError, KeyError, TypeError) as exc:
            from direct_system_repair import TASK
            from goal_delivery_runtime import _task_block
            errors.append(_task_block(TASK, "operations", exc))
    old, old_errors = _legacy_unmapped(root)
    errors.extend(old_errors)
    queue.update(legacy_unmapped=old, legacy_unmapped_count=len(old), legacy_control_records_are_business_jobs=False,
                 pending_count=len(queue['results']), professional_pending_count=len(queue['results']),
                 followthrough_pending_count=len(queue['followthrough_results']), collaboration_pending_count=len(queue['collaboration_pending']),
                 collaboration_not_proven_count=len(queue['collaboration_not_proven']), HQ_knowledge_pending_count=len(queue['HQ_knowledge_pending']),
                 named_due_dependency_count=len(queue['named_due_dependencies']), named_waiting_dependency_count=len(queue['named_waiting_dependencies']),
                 notification_delivery_pending_count=len(queue['notification_delivery_pending']), completion_followthrough_count=len(queue['completion_followthrough']))
    actionable = [row for row in inventory if row['requires_action'] and row['status'] != 'inflight_event_wait']
    ready_results = deduplicate_records(queue['results'] + queue['followthrough_results'] + queue['collaboration_pending']
                    + queue['collaboration_not_proven'] + [row for row in queue['completion_followthrough'] if row.get('actionable')]
                    + queue['named_due_dependencies'])
    ready_deliveries = [row for row in queue['notification_delivery_pending'] if row.get('actionable')]
    ready_knowledge = queue['HQ_knowledge_pending'] if role == 'operations' else []
    represented = {row.get('task_id') for row in ready_results}
    standalone_internal = [row for row in actionable if row['task_id'] not in represented]
    queue['ready_internal_action_count'] = len(actionable)
    queue['total_actionable_count'] = len(ready_results) + len(ready_deliveries) + len(ready_knowledge) + len(standalone_internal)
    queue['actionable_business_task_count'] = len({row.get('task_id', row.get('identity', {}).get('task_id'))
        for row in ready_results + ready_deliveries + ready_knowledge + actionable})
    queue['control_records_are_business_jobs'] = False
    watched = [dict(task, coordinator_role=owner) for owner, plan in plans.items() for task in plan['tasks']]
    ready_before_wait = bool(ready_results or ready_deliveries or ready_knowledge or actionable)
    batches = [] if ready_before_wait else [batch for plan in plans.values() for batch in plan['batches']]
    return {"schema_version": "3.0", "coordinator_role": role, "project_id": binding["project_id"],
            "controller_thread_id": binding["task_id"], "cwd": str(root), "updated_at": now.isoformat(),
            "coordination_model": "goal_delivery_assistant_v1", "HQ_may_end_coordination": role == "operations",
            "source": "current_responsible_assistant_goal_runtime", "checkpoint_sources": checkpoint_sources,
            "observation_time_is_not_native_freshness": True, "delegated_assistant_batches": plans,
            "responsibility_inventory": inventory, "watched_tasks": [] if role == "operations" else watched,
            "ready_internal_actions": [row for row in actionable if row.get('actual_executor') == 'operations']
                                      if role == "operations" else actionable,
            "ready_result_actions": ready_results, "ready_knowledge_intake": ready_knowledge,
            "ready_notification_actions": ready_deliveries, "validation_errors": deduplicate_records(errors),
            "wait_deferred_for_ready_work": ready_before_wait, "event_wait_batches": batches,
            "max_wait_ms_per_call": 60000, "cursor_record_required": True,
            "current_native_observation_required": any('afterCursor' not in target for batch in batches for target in batch),
            "native_wakeup_available": False, "no_high_frequency_polling": True,
            'result_categories': {key: queue[key] for key in ('professional_pending_count', 'HQ_knowledge_pending_count',
                      'named_due_dependency_count', 'legacy_unmapped_count', 'notification_delivery_pending_count')},
            'native_resume_plan': {'entry': 'running responsible assistant: pending -> ready actions -> wait-begin -> native wait_threads -> wait-record; interruption: wait-recover',
                                   'ended_chat': 'authorized original daily automation or explicit native follow-up only; queue cannot wake it',
                                   'owner': role, 'native_wakeup_proven': False},
            "result_queue_auto_wakes_ended_controller": False, "messages_sent": 0, "permissions_issued": 0,
            "business_goal_closed": False, "legacy_unassigned_results_require_explicit_goal_migration": True}, queue


def derive(root: Path, now: dt.datetime | None = None, coordinator_role: str = "operations") -> tuple[dict, dict]:
    root = root.resolve()
    now = now or dt.datetime.now(dt.timezone.utc)
    registry = workflow.department_registry(root)
    binding = registry.get("operations", {}).get("chat_binding", {})
    from goal_delivery_runtime import enabled
    if enabled(root):
        return _modern_derive(root, registry, coordinator_role, now)
    if coordinator_role != "operations":
        raise ValueError("assistant continuation requires enabled goal runtime")
    policy = workflow.load_policy(root).get("routing_policy", {})
    if (not binding.get("task_id") or not binding.get("project_id")
            or binding.get("project_id") != policy.get("source_project_id")
            or Path(binding.get("cwd", "")).resolve() != root):
        raise ValueError("current controller identity is incomplete")
    execution = workflow.read_json(root / "data/content/organic-execution-policy.json")
    checkpoint_path = execution["keyword_content_coverage_acceptance"]["controller_checkpoint"]
    checkpoint = json.loads(workflow.safe_path(root, checkpoint_path).read_text(encoding="utf-8"))
    if (not isinstance(checkpoint, dict) or not isinstance(checkpoint.get("active_tasks"), list)
            or any(not isinstance(item, dict) for item in checkpoint["active_tasks"])):
        raise ValueError("current checkpoint requires an explicit active task list")
    queue = workflow.result_handoff_pending(root)
    watched, resolved, errors = [], [], []
    seen = set()
    for item in checkpoint.get("active_tasks", []):
        task, department = item.get("task_id"), item.get("department")
        candidate, receipt_id = item.get("candidate_version"), item.get("dispatch_receipt_id")
        key = (task, department, candidate, receipt_id)
        if key in seen:
            continue
        seen.add(key)
        # Owner-designated external projects have their own route. They cannot
        # become an ordinary fixed-department watch or an inferred permission.
        if department not in registry or department == "operations":
            errors.append({"task_id": task, "reason": "not_a_fixed_execution_department"})
            continue
        target = registry[department].get("chat_binding", {})
        if (not all(key) or target.get("project_id") != binding["project_id"]
                or Path(target.get("cwd", "")).resolve() != root):
            errors.append({"task_id": task, "reason": "incomplete_or_cross_project_watch"})
            continue
        receipts, invalid = workflow._validate_receipt_chain(root, task)
        sent = next((row for row in receipts if row.get("receipt_id") == receipt_id), {})
        if (invalid or sent.get("receipt_type") != "dispatch_sent"
                or sent.get("department") != department
                or sent.get("chat_task_id") != target.get("task_id")):
            errors.append({"task_id": task, "reason": "dispatch_receipt_or_pins_invalid"})
            continue
        pos = receipts.index(sent)
        ack = next((row for row in receipts[pos + 1:] if row.get("receipt_type") == "chat_ack"
                    and row.get("department") == department
                    and row.get("chat_task_id") == target["task_id"]
                    and row.get("ack_nonempty") is True
                    and (sent.get("action_class") not in {"cms_content_candidate", "site_code_candidate", "site_code_rework_candidate"}
                         or (row.get("action_id") == sent.get("action_id")
                             and row.get("scope") == sent.get("scope")))), None)
        if not ack:
            errors.append({"task_id": task, "reason": "nonempty_ACK_missing"})
            continue
        # Exact candidate, sender and current outbox bytes must match; workflow
        # closed, native idle, old candidates and ACKs cannot close this watch.
        rows = workflow._result_handoff_rows(root, task)
        grouped = {}
        for row in rows:
            if (row.get("sender_department") == department
                    and row.get("candidate_version") == candidate
                    and row.get("created_at", "") >= sent["created_at"]):
                grouped.setdefault(row["result_sha256"], []).append(row)
        settled = None
        for result_hash, events in grouped.items():
            intake = next((r for r in events if r["event"] == "controller_received"), None)
            decision = next((r for r in events if r["event"] == "controller_decision"), None)
            follow = next((r for r in reversed(events) if r["event"] == "controller_followthrough"), None)
            if not intake or not decision:
                continue
            # Persisted records store the pinned outbox under `outbox`; the
            # input request uses outbox_path. Never mistake request shape for
            # the actual ledger, or crash before reporting a recovery error.
            pin = intake.get("outbox", {})
            if pin is None:
                pin = {}
            if not isinstance(pin, dict):
                errors.append({"task_id": task, "reason": "settled_result_outbox_not_object"})
                continue
            path = pin.get("path") or intake.get("outbox_path")
            try:
                if not path or (pin.get("sha256") and pin["sha256"] != result_hash):
                    raise ValueError("result_outbox_pin_missing_or_mismatched")
                outbox = workflow.safe_path(root, path)
                actual_hash = workflow.file_digest(root, str(outbox.relative_to(root)))["sha256"]
            except (workflow.WorkflowError, OSError, ValueError, TypeError):
                errors.append({"task_id": task, "reason": "settled_result_outbox_unavailable"})
                continue
            if actual_hash != result_hash:
                errors.append({"task_id": task, "reason": "settled_result_hash_changed"})
                continue
            if decision.get("decision") == "close_scope" or follow:
                settled = {"task_id": task, "department": department,
                           "candidate_version": candidate, "result_sha256": result_hash,
                           "controller_received": intake["record_id"],
                           "controller_decision": decision["record_id"],
                           "controller_followthrough": follow["record_id"] if follow else None,
                           "business_goal_closed": False}
        if settled:
            resolved.append(settled)
        else:
            watched.append({"task_id": task, "department": department,
                            "candidate_version": candidate, "dispatch_receipt_id": receipt_id,
                            "ack_receipt_id": ack["receipt_id"], "thread_id": target["task_id"],
                            "turn_id": item.get("turn_id", ""),
                            "event_cursor": item.get("event_cursor", ""),
                            "mode": "WAIT_OR_COLLECT_EXACT_RESULT",
                            "requires_fresh_native_identity_before_tool": True})
    targets = []
    for thread in sorted({row["thread_id"] for row in watched}):
        tasks = [row for row in watched if row["thread_id"] == thread]
        cursors = {row["event_cursor"] for row in tasks}
        target = {"thread_id": thread, "host_id": "local"}
        if len(cursors) == 1 and "" not in cursors:
            target["after_cursor"] = next(iter(cursors))
        # Mixed or absent cursors require a fresh snapshot, never a guessed ID.
        targets.append(target)
    return {"schema_version": "2.0", "project_id": binding["project_id"],
            "controller_thread_id": binding["task_id"], "cwd": str(root),
            "updated_at": now.isoformat(), "controller_checkpoint": checkpoint_path,
            "source": "current_checkpoint_and_validated_native_receipts",
            "watched_tasks": watched, "resolved_watches": resolved,
            "ready_internal_actions": checkpoint.get("prepared_waiting_qa", []),
            "validation_errors": errors, "event_wait_targets": targets,
            "max_wait_ms_per_call": 60000, "polling_or_scheduler_created": False,
            "result_queue_auto_wakes_ended_controller": False,
            "messages_sent": 0, "permissions_issued": 0, "business_goal_closed": False}, queue


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", help="Optional derived cache, inside this project only")
    parser.add_argument("--coordinator-role", default="operations")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    state, queue = derive(root, coordinator_role=args.coordinator_role)
    if args.output:
        path = workflow.safe_path(root, args.output)
        workflow.atomic_write_json(path, state)
    print(json.dumps({"state": state, "queue_counts": {k: queue.get(k, 0) for k in (
        "pending_count", "followthrough_pending_count", "total_actionable_count")}}, ensure_ascii=False))
    return 3 if state["validation_errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
