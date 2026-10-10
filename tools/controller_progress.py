"""Read-only controller checkout; files never send messages or grant a release."""
from __future__ import annotations

import argparse
import datetime as dt
import json
from collections import Counter
from pathlib import Path

import qa_dispatch_priority as priority
import workflow_control as workflow


def parse_time(value: str) -> dt.datetime:
    stamp = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        raise ValueError("timestamp requires timezone")
    return stamp.astimezone(dt.timezone.utc)


def inspect_live(registry: dict, live: dict, now: dt.datetime, exact_sections: bool = False) -> tuple[list[dict], list[str]]:
    errors = []
    try:
        age = (now - parse_time(live["observed_at"])).total_seconds()
        if not 0 <= age <= 300:
            errors.append("live_snapshot_stale_or_future")
    except (ValueError, KeyError, TypeError):
        errors.append("live_snapshot_timestamp_missing")
    rows = []
    for dep, item in registry.items():
        bind = item["chat_binding"]
        matches = [t for t in live.get("threads", []) if t.get("id") == bind["task_id"]]
        reason = ""
        thread = matches[0] if len(matches) == 1 else {}
        if len(matches) != 1:
            reason = "fixed_thread_missing_or_ambiguous"
        elif any(thread.get(a) != bind.get(b) for a, b in (
            ("projectId", "project_id"), ("cwd", "cwd"), ("title", "title")
        )):
            reason = "fixed_thread_identity_mismatch"
        groups = [s for s in live.get("sections", [])
                  if "codex:thread:local:" + bind["task_id"] in s.get("itemKeys", [])]
        expected_name = "装修公司总控" if dep == "operations" else "装修公司部门"
        group_ok = (len(groups) == 1 and (groups[0].get("sectionId", groups[0].get("id")) == bind.get("sidebar_section_id")
                    if exact_sections else groups[0].get("name") == expected_name))
        if not group_ok:
            reason = reason or "fixed_thread_group_missing_or_mismatch"
        status = thread.get("status", "unknown")
        if isinstance(status, dict):
            status = status.get("type", "unknown")
        identity_ok = not reason and not errors
        rows.append({"department": dep, "name": item["name"],
                     "thread_id": bind["task_id"], "native_status": status,
                     "identity_verified": identity_ok,
                     "dispatch_health_current": workflow._chat_binding_healthy(
                         bind, verification_ttl_hours=26, now=now),
                     "identity_issue": reason or (errors[0] if errors else "")})
    return rows, errors


def decide_continuation(roles: list[dict], checkpoint: dict, queue: dict,
                        qa: dict, errors: list[str], business_work: list[dict] | None = None) -> dict:
    """A timeout/active/closed/zero intake count is never a stop condition."""
    owned = {row["department"] for row in checkpoint.get("active_tasks", [])}
    waiting = [row for row in roles if row["department"] in owned
               and row["native_status"] == "active" and row["identity_verified"]]
    ended = [row for row in roles if row["department"] in owned
             and row["native_status"] != "active" and row["identity_verified"]]
    unresolved = [row for row in roles if row["department"] in owned
                  and not row["identity_verified"]]
    reasons = list(errors)
    if any(not row["identity_verified"] for row in roles):
        reasons.append("registered_role_identity_not_fully_verified")
    if unresolved:
        reasons.append("owned_task_identity_needs_recovery")
    if ended:
        reasons.append("owned_task_ended_collect_actual_reply_before_stopping")
    if queue.get("pending_count", 0):
        reasons.append("result_intake_or_decision_pending")
    if qa.get("waiting_dispatch"):
        reasons.append("exact_QA_dispatch_pending")
    if checkpoint.get("prepared_waiting_qa"):
        reasons.append("explicit_prepared_QA_packet_requires_real_dispatch")
    if qa.get("mode") == "BLOCKED_INVALID_PRIORITY_EVIDENCE":
        reasons.append("QA_priority_evidence_invalid")
    if queue.get("followthrough_pending_count", 0):
        reasons.append("decision_followthrough_or_due_review_pending")
    if any(row.get("requires_action", True) for row in business_work or []):
        reasons.append("business_backlog_action_or_dependency_reconciliation_pending")
    if waiting:
        reasons.append("owned_internal_tasks_running_use_native_event_wait")
    return {"ordinary_stop_allowed": not reasons,
            "next_mode": "COLLECT_OR_RECONCILE" if ended or any(
                r != "owned_internal_tasks_running_use_native_event_wait" for r in reasons)
            else "NATIVE_EVENT_WAIT" if waiting else "NO_EXECUTABLE_CONTROL_ITEM",
            "reasons": reasons,
            "event_wait_targets": [{"thread_id": row["thread_id"],
                                     "department": row["department"]} for row in waiting],
            "wait_timeout_is_completion": False,
            "project_queue_wakes_ended_controller": False,
            "business_goal_closed": False}


def business_work_items(backlog: dict, now: dt.datetime) -> list[dict]:
    """Keep explicit unfinished child scopes even when the parent was verified.

    This is a conservative work inventory, not evidence that a change is safe to
    publish. A missing owner/dependency review is itself a reconciliation action.
    Only a future wait with owner and unlock conditions permits deferral.
    """
    terminal = {"closed", "verified", "verified_production", "verified_public", "completed", "published"}
    found = []

    def visit(value: dict, parent: dict, path: str, top: bool = False) -> None:
        status = str(value.get("execution_status") or value.get("status") or "")
        next_action = value.get("next_action") or value.get("minimum_next_action")
        unsaved = any(value.get(key) is False for key in (
            "CMS_saved", "public_verified", "published", "implemented"))
        open_scope = bool((status and status not in terminal) or unsaved)
        if (open_scope and (next_action or unsaved)) or (top and status not in terminal):
            owner = (value.get("next_owner") or value.get("owner")
                     or value.get("implementation_owner") or parent.get("owner"))
            condition = value.get("unblock_condition") or value.get("dependencies")
            review = value.get("next_check_at")
            try:
                future_wait = (status.startswith("blocked") or status == "wait_external") and bool(
                    owner and condition and review and parse_time(review) > now)
            except (ValueError, TypeError):
                future_wait = False
            found.append({"parent_id": parent.get("id"), "scope_path": path,
                          "title": value.get("title") or value.get("problem") or parent.get("title"),
                          "status": status or "explicit_unfinished_scope",
                          "task_id": value.get("original_task_id") or value.get("source_task_id")
                                     or value.get("task_id") or parent.get("original_task_id"),
                          "next_owner": owner or "operations（核定原负责人）",
                          "next_action": next_action or "核对原范围及最小接续动作",
                          "unblock_condition": condition or "尚未核定；需总控核对准确依赖",
                          "next_check_at": review, "requires_action": not future_wait,
                          "wait_has_current_owner_condition_and_time": bool(future_wait),
                          "not_release_authorization": True})
        for key, child in value.items():
            if key == "historical_state_snapshots":
                continue
            if isinstance(child, dict):
                visit(child, parent, path + "/" + key)
            elif isinstance(child, list):
                for index, item in enumerate(child):
                    if isinstance(item, dict):
                        visit(item, parent, path + "/" + key + "/" + str(index))

    for item in backlog.get("items", []):
        visit(item, item, str(item.get("id")), top=True)
    return found


def latest_results(root: Path) -> dict:
    latest, states = {}, {}
    for path in (root / workflow.RESULT_HANDOFF_DIR).glob("*.jsonl"):
        rows = workflow._result_handoff_rows(root, path.stem)
        for row in rows:
            identity = (row["task_id"], row["sender_department"],
                        row["candidate_version"], row["result_sha256"])
            state = states.setdefault(identity, {"result_first_recorded_at": row["created_at"]})
            state.update(row)
    for state in states.values():
        dep = state["sender_department"]
        # A followthrough on an old candidate must not hide a later delivery.
        if dep not in latest or parse_time(state["result_first_recorded_at"]) > parse_time(
                latest[dep]["result_first_recorded_at"]):
            latest[dep] = state
    return latest


def _modern_inspect(root: Path, registry: dict, live: dict, now: dt.datetime, coordinator_role: str) -> dict:
    from controller_event_state import derive
    state, queue = derive(root, now, coordinator_role=coordinator_role)
    chosen = ({key: item for key, item in registry.items() if key == "operations"
               or item.get("coordination_authority", {}).get("routine_decisions") is True}
              if coordinator_role == "operations" else {coordinator_role: registry[coordinator_role]})
    roles, live_errors = inspect_live(chosen, live, now, exact_sections=True)
    inventory = state["responsibility_inventory"]
    for role in roles:
        role["latest_recorded_result"] = None
        role["current_checkpoint_tasks"] = [r for r in inventory if r["department"] == role["department"]]
        role["unfinished_control_results"] = [r for r in queue["results"] + queue["followthrough_results"]
                                              if r.get("task_id") in {g["task_id"] for g in role["current_checkpoint_tasks"]}]
    reasons = []
    if coordinator_role != "operations":
        reasons.extend(str(e) for e in live_errors + state["validation_errors"])
        if any(not r["identity_verified"] for r in roles):
            reasons.append("current_coordinator_identity_requires_recovery")
        if queue["pending_count"]:
            reasons.append("owned_result_intake_or_acceptance_pending")
        if queue["followthrough_pending_count"]:
            reasons.append("owned_decision_actual_followthrough_pending")
        if queue["collaboration_pending_count"]:
            reasons.append("owned_collaboration_formal_intake_or_actual_followthrough_pending")
        if queue["collaboration_not_proven_count"]:
            reasons.append("owned_collaboration_NOT_PROVEN_requires_exact_source")
        if state["ready_internal_actions"]:
            reasons.append("owned_goal_requires_current_next_action")
        if state["watched_tasks"]:
            reasons.append("owned_actual_sent_task_requires_wait_or_collection")
    targets = [t for batch in state["event_wait_batches"] for t in batch]
    target_status = {t["threadId"]: [r.get("status") for r in live.get("threads", []) if r.get("id") == t["threadId"]]
                     for t in targets}
    active = all(len(rows) == 1 and (rows[0].get("type") if isinstance(rows[0], dict) else rows[0]) == "active"
                 for rows in target_status.values())
    next_mode = ("DELEGATED_ASSISTANTS_OWN_CONTINUATION" if coordinator_role == "operations" else
                 "NATIVE_EVENT_WAIT" if targets and active and not state["ready_internal_actions"]
                 and not state["validation_errors"] and not queue["total_actionable_count"] and not live_errors
                 and not queue["collaboration_pending_count"]
                 and not queue["collaboration_not_proven_count"]
                 and all(r["identity_verified"] for r in roles)
                 else "COLLECT_OR_RECONCILE" if reasons else "NO_EXECUTABLE_CONTROL_ITEM")
    continuation = {"ordinary_stop_allowed": not reasons, "next_mode": next_mode, "reasons": reasons,
                    "event_wait_batches": state["event_wait_batches"], "event_wait_targets": targets,
                    "wait_timeout_is_completion": False, "project_queue_wakes_ended_controller": False,
                    "business_goal_closed": False}
    return {"schema_version": "2.0", "coordination_model": "goal_delivery_assistant_v1",
            "coordinator_role": coordinator_role, "generated_at_myt": now.astimezone(dt.timezone(dt.timedelta(hours=8))).isoformat(),
            "source": state["source"], "checkpoint_sources": state["checkpoint_sources"],
            "observation_time_is_not_native_freshness": True, "responsibility_inventory": inventory,
            "validation_errors": state["validation_errors"], "live_identity_errors": live_errors,
            "current_native_observation_required": state["current_native_observation_required"],
            "department_count": len(roles), "roles": roles,
            "control_counts": {key: queue[key] for key in ("pending_count", "followthrough_pending_count", "total_actionable_count", "collaboration_pending_count", "collaboration_not_proven_count", 'professional_pending_count', 'HQ_knowledge_pending_count', 'named_due_dependency_count', 'legacy_unmapped_count', 'notification_delivery_pending_count')},
            'HQ_knowledge_pending': queue['HQ_knowledge_pending'], 'legacy_unmapped': queue['legacy_unmapped'],
            'notification_delivery_pending': queue['notification_delivery_pending'],
            'native_resume_plan': state['native_resume_plan'],
            "control_rows_are_not_distinct_business_tasks": True,
            "distinct_control_task_count": len({r["task_id"] for r in queue["results"] + queue["followthrough_results"]}),
            "unfinished_control_rows": queue["results"] + queue["followthrough_results"],
            "collaboration_pending": queue["collaboration_pending"],
            "collaboration_not_proven": queue["collaboration_not_proven"],
            "legacy_QA_mode": "retired_history", "QA_waiting_dispatch": [], "prepared_QA_packets": [],
            "QA_dispatched_wait_result": [], "business_backlog_rows": [], "business_unfinished_scopes": inventory,
            "business_actionable_or_reconciliation_count": sum(r["requires_action"] for r in inventory),
            "formally_closed_scope_count": sum(r["formally_closed_scope"] for r in inventory),
            "continuation": continuation, "natural_daily_unique_IP": "DATA_MISSING", "AI_effect": "NOT_MEASURED",
            "messages_sent": 0, "business_ledger_modified": False, "permissions_or_external_writes": 0}


def inspect(root: Path, live: dict, now: dt.datetime | None = None, coordinator_role: str = "operations") -> dict:
    now = now or dt.datetime.now(dt.timezone.utc)
    registry = workflow.department_registry(root)
    if root.resolve() != Path(registry["operations"]["chat_binding"]["cwd"]).resolve():
        raise ValueError("controller project cwd mismatch")
    from goal_delivery_runtime import enabled
    if enabled(root):
        return _modern_inspect(root.resolve(), registry, live, now, coordinator_role)
    if coordinator_role != "operations":
        raise ValueError("assistant continuation requires enabled goal runtime")
    policy = json.loads((root / "data/content/organic-execution-policy.json").read_text())
    cp = policy["keyword_content_coverage_acceptance"]["controller_checkpoint"]
    checkpoint = json.loads(workflow.safe_path(root, cp).read_text())
    queue = workflow.result_handoff_pending(root)
    qa = priority.inspect(root)
    roles, errors = inspect_live(registry, live, now)
    latest = latest_results(root)
    for role in roles:
        result = latest.get(role["department"])
        role["latest_recorded_result"] = None
        if result:
            pin = result.get("outbox", {})
            current = workflow.file_digest(root, pin["path"])
            matched = current["sha256"] == pin["sha256"]
            role["latest_recorded_result"] = {
                "task_id": result["task_id"], "candidate_version": result["candidate_version"],
                "result_sha256": result["result_sha256"], "outbox": pin["path"],
                "outbox_hash_matches": matched, "latest_event": result["event"],
                "recorded_at": result["created_at"], "decision": result.get("decision"),
                "followthrough_status": result.get("followthrough_status"),
                "action_reference": result.get("action_reference"),
                "next_owner": result.get("next_owner"), "next_action": result.get("next_action"),
                "unblock_condition": result.get("unblock_condition"),
                "next_check_at": result.get("next_check_at"),
                "not_current_publication_proof": True}
        in_flight = [a for a in checkpoint.get("active_tasks", [])
                     if a.get("department") == role["department"]]
        role["current_checkpoint_tasks"] = in_flight
        role["unfinished_control_results"] = [x for x in (
            queue.get("results", []) + queue.get("followthrough_results", []))
            if x.get("sender_department") == role["department"] or x.get("next_owner") == role["department"]]
    backlog = json.loads((root / "data/content/organic-growth-backlog.json").read_text())
    business_rows = [{key: item.get(key) for key in (
        "id", "title", "status", "target", "next_action", "verified_scope", "verified_at")}
        for item in backlog["items"]]
    business_work = business_work_items(backlog, now)
    counts = {k: queue.get(k, 0) for k in (
        "pending_count", "followthrough_pending_count", "total_actionable_count")}
    return {"schema_version": "1.0", "generated_at_myt": now.astimezone(
                dt.timezone(dt.timedelta(hours=8))).isoformat(),
            "controller_checkpoint": cp, "department_count": len(roles), "roles": roles,
            "control_counts": counts,
            "control_rows_are_not_distinct_business_tasks": True,
            "distinct_control_task_count": len({x["task_id"] for x in (
                queue.get("results", []) + queue.get("followthrough_results", []))}),
            "QA_waiting_dispatch": qa.get("waiting_dispatch", []),
            "prepared_QA_packets": checkpoint.get("prepared_waiting_qa", []),
            "QA_dispatched_wait_result": qa.get("dispatched_without_result", []),
            "business_backlog_rows": business_rows,
            "backlog_status_counts": dict(Counter(x["status"] for x in business_rows)),
            "backlog_verified_is_historical_scope_only": True,
            "business_unfinished_scopes": business_work,
            "business_actionable_or_reconciliation_count": sum(
                row["requires_action"] for row in business_work),
            "unfinished_control_rows": queue.get("results", []) + queue.get("followthrough_results", []),
            "continuation": decide_continuation(roles, checkpoint, queue, qa, errors, business_work),
            "natural_daily_unique_IP": "DATA_MISSING", "AI_effect": "NOT_MEASURED",
            "messages_sent": 0, "business_ledger_modified": False,
            "permissions_or_external_writes": 0}


def cell(value) -> str:
    return str(value or "待核验").replace("|", "\\|").replace("\n", " ")


def render(status: dict) -> str:
    if status.get("coordination_model") == "goal_delivery_assistant_v1":
        lines = ["# 当前责任与未完成范围", "", "读取时间：" + status["generated_at_myt"],
                 "当前协调角色：" + status["coordinator_role"], "",
                 "来源为当前负责助理的目标与记录过的真实事件等待；读取时间不代表现场观测已刷新。",
                 "", "| 原任务 | 当前负责助理 | 实际阶段 | 下一动作 | 解除条件 / 复查 |", "| --- | --- | --- | --- | --- |"]
        for row in status["responsibility_inventory"]:
            lines.append("| " + " | ".join(map(cell, [row["task_id"], row["next_owner"], row["status"], row["next_action"],
                         str(row["unblock_condition"]) + " / " + str(row.get("next_check_at") or "原任务事件/当前恢复")])) + " |")
        lines += ["", "正式收口的准确范围：" + str(status["formally_closed_scope_count"]),
                  "结果收取/验收待办：" + str(status["control_counts"]["pending_count"]),
                  "决策后真实下一动作待办：" + str(status["control_counts"]["followthrough_pending_count"]),
                  "协作结果正式收取/验收/真实接续待办：" + str(status["control_counts"]["collaboration_pending_count"]),
                  '专业待验收 / HQ待知悉 / 具名到期依赖 / 旧账待映射：' + ' / '.join(str(status['control_counts'][key]) for key in ('professional_pending_count', 'HQ_knowledge_pending_count', 'named_due_dependency_count', 'legacy_unmapped_count')),
                  '通知待送达：' + str(status['control_counts']['notification_delivery_pending_count']) + '（持久入队不等于实际发送）',
                  "协作证据 NOT_PROVEN（逐项恢复原来源）：" + str(status["control_counts"]["collaboration_not_proven_count"]),
                  "", "普通收工允许：" + str(status["continuation"]["ordinary_stop_allowed"]),
                  "下一模式：" + status["continuation"]["next_mode"],
                  "原因：" + ", ".join(status["continuation"]["reasons"]),
                  "", "旧 QA 仅保留历史读取，不形成新验收队列。ACK/prepared/idle/空待办均不是完成证明。",
                  "原生事件等待每批至多8个聊天、单次至多60秒，必须记录实际 cursor；队列不能唤醒已结束聊天。",
                  "子范围收口不自动关闭父目标，也不表示整个业务目标或生产上线已经完成。", ""]
        return "\n".join(lines)
    lines = ["# 公司工作进度与未完成清单", "", "更新时间：" + status["generated_at_myt"],
             "", "此表只汇总真实控制记录与现场状态；候选、QA和历史 verified 均不自动表示生产上线。",
             "", "## 现在各部门在哪里", "",
             "| 部门 | 现场状态 | 最近记录范围 | 精确在途任务 / 本版 / 轮次 | 下一负责人 | 未完成 / 下一步 / 解除条件 |",
             "| --- | --- | --- | --- | --- | --- |"]
    for role in status["roles"]:
        result = role["latest_recorded_result"] or {}
        active = role["current_checkpoint_tasks"]
        tasks = "; ".join(" / ".join(str(a.get(key) or "待核定") for key in (
            "task_id", "candidate_version", "turn_id", "status")) for a in active) or "本检查点无在途任务"
        owner = ("; ".join(str(a.get("next_owner") or a["department"]) for a in active)
                 if active else result.get("next_owner") or role["department"])
        next_action = ("; ".join(str(a.get("next_action") or "收取本准确轮次真实结果并决策")
                                for a in active) if active else result.get("next_action")
                       or "核对本部门未完成记录及准确依赖")
        if not active and result.get("latest_event") == "controller_followthrough":
            stage = result.get("followthrough_status")
            if stage in {"internal_control_completed", "dispatch_sent", "execution_verified",
                         "prior_action_verified", "inflight_result_verified"}:
                next_action = "该条结果的后续动作已关联（" + str(stage) + "）；原决策动作已接续：" + next_action + "；业务余项见下表"
            elif stage in {"external_wait_registered", "blocked_with_owner"}:
                next_action = "已登记具名等待（" + str(stage) + "）；" + next_action
        condition = ("; ".join(str(a.get("unblock_condition") or "当前轮实际结果及独立验收")
                               for a in active) if active else result.get("unblock_condition"))
        if condition:
            next_action += "; 解除条件：" + str(condition)
        check_time = ("; ".join(str(a.get("next_check_at") or "按当前轮事件等待接续")
                                for a in active) if active else result.get("next_check_at"))
        if check_time:
            next_action += "; 复查：" + str(check_time)
        label = role["native_status"] + ("（身份待核验）" if not role["identity_verified"] else "")
        lines.append("| " + " | ".join(map(cell, [role["name"], label,
            result.get("candidate_version", "本表无新增结果证明"), tasks, owner, next_action])) + " |")
    lines += ["", "## 原业务主账", "",
              "下列父项保留原状态；具体候选/生产证据仍须沿原任务验收。", "",
              "| 原条目 | 工作范围 | 主账状态 | 原下一动作 |", "| --- | --- | --- | --- |"]
    for item in status["business_backlog_rows"]:
        lines.append("| " + " | ".join(map(cell, [item["id"], item["title"],
                     item["status"], item["next_action"]])) + " |")
    lines += ["", "## 业务主账中的未完范围", "",
              "已验父范围不关闭明确未完子项；缺负责人/依赖或复查时间的范围仍须对账。",
              "", "| 原范围 / 原任务 | 状态 | 下一负责人 | 下一动作 | 解除条件 / 复查 |",
              "| --- | --- | --- | --- | --- |"]
    for item in status.get("business_unfinished_scopes", []):
        lines.append("| " + " | ".join(map(cell, [item["scope_path"] + " / " + str(item.get("task_id") or "待核定"),
            item["status"], item["next_owner"], item["next_action"],
            str(item["unblock_condition"]) + " / " + str(item.get("next_check_at") or "复查时间待核定")])) + " |")
    lines += ["", "## 决策后仍需对账的控制记录", "",
              "{} 条控制记录涉及 {} 个原任务，不能当作相同数量的网站故障，也不能批量重派。".format(
                  status["control_counts"]["total_actionable_count"], status["distinct_control_task_count"]),
              "", "| 原任务 / 本版 | 下一负责人 | 已作决策 | 未完动作 / 条件 |",
              "| --- | --- | --- | --- |"]
    for item in status["unfinished_control_rows"]:
        lines.append("| " + " | ".join(map(cell, [item["task_id"] + " / " + item["candidate_version"],
                     item.get("next_owner"), item.get("controller_decision"),
                     item.get("next_action") or "收取非空回复/outbox并作明确决策"])) + " |")
    lines += ["", "## 已准备但尚未实际派发的 QA 包", ""]
    packets = status.get("prepared_QA_packets", [])
    if packets:
        for packet in packets:
            lines.append("- " + " / ".join(cell(packet.get(k)) for k in
                ("task_id", "candidate_version", "department", "packet_path", "next_action")))
    else:
        lines.append("当前检查点未列待派 QA 包；不代表业务已完成。")
    lines += ["", "## 当前接续判断", "", "普通收工允许：" + str(status["continuation"]["ordinary_stop_allowed"]),
              "", "原因：" + ", ".join(status["continuation"]["reasons"]), "",
              "总控有内部在途任务时使用原生事件等待；结果队列不能自动唤醒已结束的总控。中断/运行限制须留下真实原因、原任务/轮次/cursor和上述未完清单，恢复时先收结果。",
              "", "50自然去重IP/日：DATA_MISSING；AI引用/推荐：NOT_MEASURED。", ""]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live-proof", required=True)
    parser.add_argument("--json-output")
    parser.add_argument("--report-output")
    parser.add_argument("--coordinator-role", default="operations")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    try:
        live = json.loads(workflow.safe_path(root, args.live_proof).read_text())
        result = inspect(root, live, coordinator_role=args.coordinator_role)
        for name, content in ((args.json_output, json.dumps(result, ensure_ascii=False, indent=2) + "\n"),
                              (args.report_output, render(result))):
            if name:
                path = workflow.safe_path(root, name)
                path.parent.mkdir(parents=True, exist_ok=True)
                if name == args.json_output:
                    workflow.atomic_write_json(path, result)
                else:
                    # Readers must see either the previous report or this full report.
                    temporary = path.with_name(path.name + ".controller-tmp")
                    temporary.write_text(content)
                    temporary.replace(path)
        print(json.dumps({k: result[k] for k in (
            "generated_at_myt", "department_count", "control_counts", "distinct_control_task_count",
            "continuation", "messages_sent", "permissions_or_external_writes")}, ensure_ascii=False))
        return 0 if result["continuation"]["ordinary_stop_allowed"] else 2
    except (ValueError, OSError, workflow.WorkflowError) as error:
        print(json.dumps({"status": "BLOCKED_PROGRESS_EVIDENCE", "error": str(error)}, ensure_ascii=False))
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
