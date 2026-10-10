"""Exact independent result review. Metadata is not authentication or permission."""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path

R0_CLASSES = {"internal_control_candidate", "read_only_candidate"}
IDENTITY = ("task_id", "action_id", "action_class", "scope", "candidate_version", "candidate_sha256")
GOAL_IDENTITY = ("objective", "completion_criteria", "primary_owner", "responsible_assistant",
                 "authorized_scope", "producer_departments", "acceptance_capability")


def _workflow():
    import workflow_control
    return workflow_control


def _review_context(root, snapshot):
    """Recover the original role/goal context before selecting historical plans."""
    if snapshot.get("departments") and snapshot.get("goal_delivery") is not None:
        return snapshot
    w = _workflow()
    result = dict(snapshot)
    events = [row for row in w.read_jsonl(root / w.WORKFLOW_EVENTS) if row.get("task_id") == snapshot.get("task_id")]
    for event in events:
        detail = event.get("details", {})
        if not snapshot.get("departments"):
            if detail.get("departments"):
                result["departments"] = detail["departments"]
            if detail.get("assignment_departments"):
                result["departments"] = detail["assignment_departments"]
            if "owner_approval_required" in detail:
                result["owner_approval_required"] = detail["owner_approval_required"]
        if snapshot.get("goal_delivery") is None and isinstance(detail.get("goal_delivery"), dict):
            result["goal_delivery"] = detail["goal_delivery"]
        if snapshot.get("goal_contract") is None and isinstance(detail.get("goal_contract"), dict):
            result["goal_contract"] = detail["goal_contract"]
    return result


def _goal(root, snapshot):
    from result_coordination import goal_delivery
    return goal_delivery(root, snapshot=snapshot)


def _goal_reviewer(root, snapshot):
    from result_coordination import coordinator_roles, review_capabilities
    w = _workflow()
    goal = _goal(root, snapshot)
    if goal is None:
        return None
    reviewer = goal.get("responsible_assistant")
    producers = goal.get("producer_departments", [])
    if (reviewer == "operations" or reviewer not in coordinator_roles(root)
            or not isinstance(producers, list) or not producers or reviewer in producers
            or not isinstance(goal.get("acceptance_capability"), str)
            or goal["acceptance_capability"] not in review_capabilities(root, reviewer)):
        raise w.WorkflowError("one assigned capable independent assistant required; self review rejected")
    return reviewer


def _initial_assignment(root, snapshot, dispatch):
    """An initial complete-goal assignment cannot freeze future source bytes."""
    w = _workflow()
    goal = _goal(root, snapshot)
    if goal is None:
        return False
    pin = snapshot.get("goal_contract")
    if pin is None:
        pins = [row.get("details", {}).get("goal_contract") for row in w.read_jsonl(root / w.WORKFLOW_EVENTS)
                if row.get("task_id") == snapshot.get("task_id") and row.get("details", {}).get("goal_contract")]
        pin = pins[-1] if pins else None
    if not isinstance(pin, dict) or w.file_digest(root, pin.get("path", "")) != pin:
        return False
    contract = w.read_json(w.safe_path(root, pin["path"]))
    contract = contract.get("goal_delivery", contract)
    return (all(contract.get(key) == goal.get(key) for key in GOAL_IDENTITY)
            and dispatch.get("receipt_type") == "dispatch_sent"
            and dispatch.get("action_id") == "assign-goal-review:" + snapshot["task_id"]
            and dispatch.get("scope") in goal["authorized_scope"]
            and pin in dispatch.get("evidence", []))


def _assigned_review_round(root, snapshot, receipts, plan):
    """Resume the original assignment; never turn a new reviewer into that role.

    Actual dispatch/ACK receipts are already checked by the native receipt
    consumer. A continuation still needs the frozen original goal and an exact
    recorded routing decision. This does not create or replace a result lease.
    """
    w = _workflow()
    goal = _goal(root, snapshot)
    if goal is None:
        return None
    reviewer = _goal_reviewer(root, snapshot)
    history = [(i, row) for i, row in enumerate(receipts)
               if row.get("department") in {reviewer, "qa", "qa-technical"}]
    if any(row.get("department") != reviewer for _, row in history):
        return None
    sends = [(i, row) for i, row in history
             if row.get("receipt_type") in {"dispatch_sent", "dispatch_failed"}]
    if not sends or not any(_initial_assignment(root, snapshot, row) for _, row in sends):
        return None
    index, current = sends[-1]
    if (current.get("receipt_type") != "dispatch_sent"
            or current.get("task_id") != snapshot["task_id"]
            or current.get("chat_task_id") != plan["reviewer_thread_id"]
            or current.get("scope") not in goal["authorized_scope"]
            or plan.get("scope") not in goal["authorized_scope"]):
        return None
    if not _initial_assignment(root, snapshot, current):
        policies = [row for row in w.read_jsonl(root / w.POLICY_DECISIONS)
                    if row.get("decision_id") == current.get("policy_decision_id")]
        expected = {"status": "allow", "routing_status": "routing_allowed",
                    "task_id": snapshot["task_id"], "action_id": current.get("action_id"),
                    "action_class": "thread_message", "scope": current.get("scope"),
                    "target_department": reviewer, "target_thread_id": plan["reviewer_thread_id"]}
        if len(policies) != 1 or any(policies[0].get(key) != value for key, value in expected.items()):
            return None
    acks = [(i, row) for i, row in history if i > index
            and row.get("receipt_type") == "chat_ack"
            and row.get("chat_task_id") == plan["reviewer_thread_id"]
            and row.get("ack_nonempty") is True]
    if not acks:
        return None
    ack_index, ack = acks[-1]
    dispatch_at, ack_at = [w._parse_observed_at(row.get("created_at")) for row in (current, ack)]
    if dispatch_at is None or ack_at is None or not dispatch_at <= ack_at <= dt.datetime.now(dt.timezone.utc):
        return None
    return {"dispatch": current, "dispatch_index": index, "ack": ack, "ack_index": ack_index}


def _binding(root, snapshot):
    """Recover the frozen binding from append-only events if snapshot was lost."""
    w = _workflow()
    binding = snapshot.get("qa_review_plan")
    if binding is None:
        events = [row for row in w.read_jsonl(root / w.WORKFLOW_EVENTS)
                  if row.get("task_id") == snapshot.get("task_id")
                  and row.get("details", {}).get("qa_review_plan_bound")]
        binding = events[-1]["details"]["qa_review_plan_bound"] if events else None
    return binding


def load_plan(root: Path, snapshot: dict, binding: dict | None = None) -> dict | None:
    w = _workflow()
    snapshot = _review_context(root, snapshot)
    binding = _binding(root, snapshot) if binding is None else binding
    if binding is None:
        return None
    if not isinstance(binding, dict) or not isinstance(binding.get("pin"), dict):
        raise w.WorkflowError("invalid exact QA review-plan binding")
    pin = binding["pin"]
    if w.file_digest(root, pin.get("path", "")) != pin:
        raise w.WorkflowError("frozen QA review plan changed")
    plan = w.read_json(w.safe_path(root, pin["path"]))
    if not snapshot.get("departments"):
        events = [row for row in w.read_jsonl(root / w.WORKFLOW_EVENTS)
                  if row.get("task_id") == snapshot.get("task_id")]
        original = next((row.get("details", {}) for row in events if row.get("state") == "planned"), {})
        snapshot = {**snapshot, "departments": original.get("departments", []),
                    "owner_approval_required": original.get("owner_approval_required", False)}
        if "goal_delivery" in original and "goal_delivery" not in snapshot:
            snapshot["goal_delivery"] = original["goal_delivery"]
        for row in events:
            details = row.get("details", {})
            if (details.get("plan_refresh") or details.get("binding_refresh")) and details.get("departments"):
                snapshot["departments"] = details["departments"]
                if "owner_approval_required" in details:
                    snapshot["owner_approval_required"] = details["owner_approval_required"]
    validate_plan(root, snapshot, plan)
    if binding.get("reviewer_department") != plan["reviewer_department"]:
        raise w.WorkflowError("reviewer binding differs from frozen plan")
    return plan


def _bindings(root, snapshot):
    """Bound plan history is recovered from its original immutable events."""
    w = _workflow()
    rows = [event["details"]["qa_review_plan_bound"] for event in w.read_jsonl(root / w.WORKFLOW_EVENTS)
            if event.get("task_id") == snapshot.get("task_id") and event.get("details", {}).get("qa_review_plan_bound")]
    rows += snapshot.get("qa_review_plan_history", [])
    current = _binding(root, snapshot)
    if current is not None:
        rows.append(current)
    unique = []
    for row in rows:
        if row not in unique:
            unique.append(row)
    return unique


def _verdict_binding(root, snapshot, receipts, receipt):
    current = _binding(root, snapshot)
    if _goal(root, snapshot) is None or len(_bindings(root, snapshot)) <= 1:
        return current
    w = _workflow()
    pin = next((p for p in receipt.get("evidence", []) if p.get("path", "").endswith(".json")), None)
    if not pin or w.file_digest(root, pin["path"]) != pin:
        raise w.WorkflowError("historical verdict must reference its exact reviewer outbox bytes")
    box = w.read_json(w.safe_path(root, pin["path"]))
    identity = box.get("review_identity")
    events = [row for row in w.read_jsonl(root / w.WORKFLOW_EVENTS) if row.get("task_id") == snapshot["task_id"]]
    candidates = []
    for binding in _bindings(root, snapshot):
        if binding.get("reviewer_department") != box.get("department"):
            continue
        plan = load_plan(root, snapshot, binding)
        if identity != {key: plan[key] for key in IDENTITY}:
            continue
        bound_before = any(event.get("details", {}).get("qa_review_plan_bound") == binding
                           and event.get("created_at", "") <= receipt.get("created_at", "") for event in events)
        dispatch_pin = any(row.get("department") == plan["reviewer_department"]
                           and row.get("receipt_type") == "dispatch_sent"
                           and binding["pin"] in row.get("evidence", []) for row in receipts)
        if bound_before and (binding["pin"] in box.get("evidence", []) or dispatch_pin):
            candidates.append(binding)
    if len(candidates) != 1:
        raise w.WorkflowError("one exact reviewed historical plan pin and identity required")
    return candidates[0]


def _validate_rework(root, snapshot, receipts, old_binding, plan):
    w = _workflow()
    goal = _goal(root, snapshot)
    old = load_plan(root, snapshot, old_binding)
    verdicts = [row for row in receipts if row.get("receipt_type") == "qa_verdict"]
    if (goal is None or not verdicts or verdicts[-1].get("verdict") != "blocked"
            or plan.get("rework_of") != verdicts[-1].get("receipt_id")
            or verdicts[-1].get("department") != plan["reviewer_department"]):
        raise w.WorkflowError("rework requires the latest exact blocked verdict; PASS cannot reopen")
    same = ("task_id", "action_id", "action_class", "scope", "producer_department", "reviewer_department",
            "reviewer_thread_id", "risk_level", "single_final_reviewer", "production_write_allowed", "external_permission_issued")
    if (any(old.get(key) != plan.get(key) for key in same)
            or old_binding.get("goal_identity", {key: goal[key] for key in GOAL_IDENTITY}) != {key: goal[key] for key in GOAL_IDENTITY}
            or plan["candidate_version"] == old["candidate_version"]
            or plan["candidate"]["sha256"] == old["candidate"]["sha256"]
            or plan["candidate"]["path"] == old["candidate"]["path"]):
        raise w.WorkflowError("rework must preserve goal/scope/producer/reviewer and freeze a new candidate version")
    changed, diff, methods = plan.get("changed_scope"), plan.get("evidence_diff"), plan.get("revalidation_methods")
    if (not isinstance(changed, list) or not changed or any(x not in goal["authorized_scope"] for x in changed)
            or len(set(changed)) != len(changed) or not isinstance(diff, dict)
            or diff.get("previous_candidate") != old["candidate"] or diff.get("candidate") != plan["candidate"]
            or not isinstance(diff.get("summary"), str) or not diff["summary"].strip()
            or not isinstance(methods, dict) or set(methods) != set(changed)
            or any(not isinstance(x, str) or not x.strip() for x in methods.values())):
        raise w.WorkflowError("exact changed scope, candidate evidence diff and revalidation methods required")
    producer_rows = [row for row in receipts if row.get("department") == plan["producer_department"]
                     and row.get("receipt_type") == "outbox_received"]
    if not producer_rows or receipts.index(producer_rows[-1]) <= receipts.index(verdicts[-1]):
        raise w.WorkflowError("new producer result after blocked review required for rework binding")
    pin = next((p for p in producer_rows[-1].get("evidence", []) if p.get("path", "").endswith(".json")), None)
    box = w.read_json(w.safe_path(root, pin["path"])) if pin else {}
    if box.get("candidate_version") != plan["candidate_version"] or plan["candidate"] not in box.get("evidence", []):
        raise w.WorkflowError("new producer outbox must bind the exact rework candidate/version")


def reviewer_department(root: Path, snapshot: dict) -> str:
    snapshot = _review_context(root, snapshot)
    plan = load_plan(root, snapshot)
    return plan["reviewer_department"] if plan else (_goal_reviewer(root, snapshot) or "qa")


def validate_plan(root: Path, snapshot: dict, plan: dict) -> None:
    w = _workflow()
    goal = _goal(root, snapshot)
    modern = goal is not None
    if (plan.get("schema_version") != 1 or plan.get("task_id") != snapshot.get("task_id")
            or plan.get("risk_level") not in ({"R0", "R1", "R2", "R3"} if modern else {"R0"})
            or plan.get("single_final_reviewer") is not True
            or (not modern and plan.get("action_class") not in R0_CLASSES)
            or any(plan.get(k) is not False for k in ("production_write_allowed", "external_permission_issued"))
            or (not modern and snapshot.get("owner_approval_required"))):
        raise w.WorkflowError("exact single-reviewer result-only plan required" if modern else "exact single-reviewer internal R0 plan required")
    if any(not isinstance(plan.get(k), str) or not plan[k].strip() for k in IDENTITY):
        raise w.WorkflowError("complete exact QA identity required")
    scope = plan["scope"]
    if ((not modern and not scope.startswith("project:")) or scope.endswith((":", "/"))
            or any(c in scope for c in "*?[]|,\n\r")):
        raise w.WorkflowError("one exact project scope required")
    reviewer, producer = plan.get("reviewer_department"), plan.get("producer_department")
    registry = w.department_registry(root)
    planned = {row.get("department"): row for row in snapshot.get("departments", [])}
    if modern:
        allowed_reviewer = _goal_reviewer(root, snapshot)
        role_valid = (reviewer == allowed_reviewer and producer in goal["producer_departments"]
                      and not (set(planned) & {"qa", "qa-technical"}))
    else:
        role_valid = reviewer in {"qa", "qa-technical"} and set(planned) & {"qa", "qa-technical"} == {reviewer}
    if (not role_valid or producer not in registry
            or producer in {"operations", "qa", "qa-technical"} or producer == reviewer
            or reviewer not in registry or reviewer not in planned or producer not in planned
            ):
        raise w.WorkflowError("one known independent planned reviewer and producer required")
    producer_bind, review_bind = [registry[d].get("chat_binding", {}) for d in (producer, reviewer)]
    ops_bind = registry.get("operations", {}).get("chat_binding", {})
    controller = plan.get("controller_department")
    controller_valid = (controller in {"operations", reviewer} if modern else controller == "operations")
    controller_bind = registry.get(controller, {}).get("chat_binding", {})
    if (plan.get("reviewer_thread_id") != review_bind.get("task_id")
            or planned[reviewer].get("chat_task_id") != review_bind.get("task_id")
            or planned[producer].get("chat_task_id") != producer_bind.get("task_id")
            or producer_bind.get("task_id") == review_bind.get("task_id")
            or not controller_valid
            or plan.get("controller_thread_id") != controller_bind.get("task_id")):
        raise w.WorkflowError("exact fixed reviewer/producer/controller required")
    if any(not b.get("project_id") or b.get("project_id") != ops_bind.get("project_id")
           or b.get("cwd") != str(root.resolve()) for b in (producer_bind, review_bind, ops_bind)):
        raise w.WorkflowError("same project and cwd required")
    pin = plan.get("candidate")
    if not isinstance(pin, dict) or w.file_digest(root, pin.get("path", "")) != pin:
        raise w.WorkflowError("exact immutable candidate file pin required")
    candidate = w.read_json(w.safe_path(root, pin["path"]))
    if (pin.get("sha256") != plan["candidate_sha256"]
            or candidate.get("task_id") != plan["task_id"]
            or candidate.get("candidate_version") != plan["candidate_version"]
            or candidate.get("department") != producer):
        raise w.WorkflowError("candidate task/version/producer/hash mismatch")


def bind_plan(root: Path, *, task_id: str, plan_path: str, coordinator_role: str = "operations") -> dict:
    w = _workflow()
    snapshot = w.read_json(w.snapshot_path(root, w.validate_task_id(task_id)))
    modern = _goal(root, snapshot) is not None
    if coordinator_role != "operations" and (not modern or coordinator_role != _goal_reviewer(root, snapshot)):
        raise w.WorkflowError("only operations records final reviewer plan")
    task_id = w.validate_task_id(task_id)
    pin = w.file_digest(root, plan_path)
    with w.workflow_lock(root):
        snapshot = w.read_json(w.snapshot_path(root, task_id))
        if not snapshot:
            raise w.WorkflowError("original workflow required")
        modern = _goal(root, snapshot) is not None
        if coordinator_role != "operations" and (not modern or coordinator_role != _goal_reviewer(root, snapshot)):
            raise w.WorkflowError("only the assigned assistant or operations binds this exact reviewer plan")
        plan = w.read_json(w.safe_path(root, plan_path))
        validate_plan(root, snapshot, plan)
        old = _binding(root, snapshot)
        binding = {"pin": pin, "reviewer_department": plan["reviewer_department"]}
        if modern:
            binding["goal_identity"] = {key: _goal(root, snapshot)[key] for key in GOAL_IDENTITY}
        if old is not None:
            if old == binding or {k:v for k,v in old.items() if k != "review_delegation"} == binding:
                if old.get("review_delegation"):
                    from goal_delivery_runtime import review_delegation
                    if review_delegation(root, snapshot)["binding"] != old["review_delegation"]:
                        raise w.WorkflowError("frozen original review delegation changed")
                return {"result": "duplicate_ignored", **old}
            if not modern:
                raise w.WorkflowError("reviewer plan is frozen; cannot replace/reopen")
        receipts, invalid = w._validate_receipt_chain(root, task_id)
        if invalid or w.validate_workflow_events(root, task_id):
            raise w.WorkflowError("valid original chains required for reviewer admission")
        if modern and not any(r.get("department") == plan["reviewer_department"]
                              and r.get("receipt_type") in {"dispatch_sent", "dispatch_failed"} for r in receipts):
            from goal_delivery_runtime import review_delegation
            inherited = review_delegation(root, snapshot)
            if inherited:
                binding["review_delegation"] = inherited["binding"]
        review_history = [(i, r) for i, r in enumerate(receipts) if r.get("department") in
                          ({plan["reviewer_department"], "qa", "qa-technical"} if modern else {"qa", "qa-technical"})]
        if old is not None:
            _validate_rework(root, snapshot, receipts, old, plan)
        elif plan.get("rework_of"):
            raise w.WorkflowError("original frozen plan required for rework")
        elif review_history:
            if (not modern or _assigned_review_round(root, snapshot, receipts, plan) is None
                    or any(r.get("receipt_type") == "qa_verdict" for _, r in review_history)):
                raise w.WorkflowError("cannot change reviewer after QA dispatch or history")
        now = dt.datetime.now(dt.timezone.utc)
        health_roles = (plan["producer_department"], plan["reviewer_department"])
        if coordinator_role == "operations" or not modern:
            health_roles = ("operations", *health_roles)
        if any(not w._chat_binding_healthy(w.department_registry(root)[d].get("chat_binding", {}),
                                          verification_ttl_hours=26, now=now)
               for d in health_roles):
            raise w.WorkflowError("fresh fixed-role health required")
        details = {"qa_review_plan_bound": binding}
        if old is not None:
            history = [row for row in _bindings(root, snapshot) if row != binding]
            snapshot["qa_review_plan_history"] = history
            details.update(qa_review_plan_history=history, rework_of=plan["rework_of"], old_verdict_migrated=False)
        snapshot["qa_review_plan"] = binding
        w.append_workflow_event(root, task_id, snapshot["current_state"], details)
        snapshot["updated_at"] = w.utc_timestamp()
        snapshot["event_count"] = sum(row.get("task_id") == task_id for row in w.read_jsonl(root / w.WORKFLOW_EVENTS))
        w.atomic_write_json(w.snapshot_path(root, task_id), snapshot)
    return {"result": "recorded", **binding, "production_write_allowed": False}


def transfer_plan(root: Path, *, task_id: str, plan_path: str, target_role: str,
                  prepare_only: bool = False, assignment_change: dict | None = None) -> dict:
    """Prepare an explicit reviewer replacement, preserving all candidate bytes.

    Preparation is read-only. The assignment consumer commits the new goal,
    binding and previous binding history together; no old PASS is moved.
    Call under the coordination lock when coupled to a lease transfer.
    """
    from result_coordination import review_capabilities
    w = _workflow()
    root = Path(root).resolve()
    task_id = w.validate_task_id(task_id)
    snapshot = w.read_json(w.snapshot_path(root, task_id))
    goal = _goal(root, snapshot)
    binding = _binding(root, snapshot)
    if goal is None or not isinstance(binding, dict):
        raise w.WorkflowError("new frozen review plan required for explicit reviewer transfer")
    old = load_plan(root, snapshot)
    previous = goal["responsible_assistant"]
    capability = goal.get("acceptance_capability")
    if (target_role == previous or capability not in review_capabilities(root, previous)
            or capability not in review_capabilities(root, target_role)):
        raise w.WorkflowError("reviewer transfer requires a different assistant with the same task capability")
    receipts, invalid = w._validate_receipt_chain(root, task_id)
    if invalid or w.validate_workflow_events(root, task_id):
        raise w.WorkflowError("valid original chains required for reviewer transfer")
    if any(row.get("receipt_type") == "qa_verdict" for row in receipts):
        raise w.WorkflowError("existing verdict cannot be moved to another reviewer; ordinary transfer refused")
    pin = w.file_digest(root, plan_path)
    new = w.read_json(w.safe_path(root, plan_path))
    replaceable = {"reviewer_department", "reviewer_thread_id", "controller_department", "controller_thread_id"}
    if any(old.get(key) != new.get(key) for key in (set(old) | set(new)) - replaceable):
        raise w.WorkflowError("reviewer transfer must retain exact candidate and review identity")
    registry = w.department_registry(root)
    if new.get("reviewer_department") != target_role or new.get("reviewer_thread_id") != registry.get(target_role, {}).get("chat_binding", {}).get("task_id"):
        raise w.WorkflowError("new plan must bind the exact target assistant")
    departments = [{**row, "department": target_role,
                    "chat_task_id": registry[target_role]["chat_binding"]["task_id"]}
                   if row.get("department") == previous else dict(row)
                   for row in snapshot.get("departments", [])]
    target_snapshot = {**snapshot, "goal_delivery": {**goal, "responsible_assistant": target_role},
                       "departments": departments}
    validate_plan(root, target_snapshot, new)
    now = dt.datetime.now(dt.timezone.utc)
    if not w._chat_binding_healthy(registry[target_role].get("chat_binding", {}), verification_ttl_hours=26, now=now):
        raise w.WorkflowError("fresh target assistant binding required for reviewer transfer")
    packet = {"previous_binding": binding, "new_binding": {"pin": pin, "reviewer_department": target_role},
              "previous_assistant": previous, "target_assistant": target_role,
              "acceptance_capability": capability, "departments": departments,
              "candidate": old["candidate"], "review_identity": {key: old[key] for key in IDENTITY},
              "old_verdict_migrated": False}
    if prepare_only:
        return packet
    if not isinstance(assignment_change, dict) or assignment_change.get("previous_assistant") != previous or assignment_change.get("target_assistant") != target_role:
        raise w.WorkflowError("actual fenced assignment transfer required; prepared plan is not applied")
    from goal_delivery_runtime import record_assignment_transfer
    change = {**assignment_change, "review_plan_transfer": packet}
    return record_assignment_transfer(root, change["result_identity"], change)


def _validate_goal_acceptance(root, snapshot, receipts, box, verdict):
    """A producer candidate PASS cannot stand in for the complete goal."""
    w = _workflow()
    goal = _goal(root, snapshot)
    if goal is None:
        return
    acceptance = box.get("goal_acceptance")
    if (not isinstance(acceptance, dict)
            or any(acceptance.get(key) != goal.get(key) for key in
                   ("completion_criteria", "primary_owner", "responsible_assistant"))):
        raise w.WorkflowError("assistant verdict must bind the complete goal criteria and responsibility")
    scope, remaining = acceptance.get("accepted_scope"), acceptance.get("remaining_scope")
    if (not isinstance(scope, list) or any(value not in goal["authorized_scope"] for value in scope)
            or len(set(scope)) != len(scope) or not isinstance(remaining, list)
            or any(not isinstance(value, str) or not value.strip() for value in remaining)
            or (verdict == "pass" and (scope != goal["authorized_scope"] or remaining))
            or (verdict == "blocked" and not remaining)
            or verdict not in {"pass", "blocked"}):
        raise w.WorkflowError("PASS must accept the full exact goal scope; blocked must state remaining scope")
    pins = acceptance.get("producer_results")
    if not isinstance(pins, dict) or set(pins) != set(goal["producer_departments"]):
        raise w.WorkflowError("complete goal acceptance must bind every producer current outbox pin")
    from goal_delivery_runtime import owner_direct
    for producer in goal["producer_departments"]:
        boxes = [(i, row) for i, row in enumerate(receipts)
                 if row.get("department") == producer and row.get("receipt_type") == "outbox_received"]
        if not boxes:
            raise w.WorkflowError("complete goal producer result missing")
        box_index, receipt = boxes[-1]
        pin = next((p for p in receipt.get("evidence", []) if p.get("path", "").endswith(".json")), None)
        if pin is None or pins[producer] != pin or w.file_digest(root, pin["path"]) != pin:
            raise w.WorkflowError("complete goal producer current result bytes differ")
        dispatches = [i for i, row in enumerate(receipts) if row.get("department") == producer
                      and row.get("receipt_type") in {"dispatch_sent", "dispatch_failed"}]
        start = dispatches[-1] if dispatches else -1
        if ((start >= 0 and receipts[start].get("receipt_type") != "dispatch_sent")
                or (start == -1 and not owner_direct(root, snapshot, producer))
                or not any(start < i < box_index and row.get("department") == producer
                           and row.get("receipt_type") == "chat_ack" and row.get("ack_nonempty") is True
                           for i, row in enumerate(receipts))):
            raise w.WorkflowError("complete goal producer outbox must belong to its current acknowledged round")
        w.validate_outbox(root, [pin], producer, snapshot["task_id"])
        result = w.read_json(w.safe_path(root, pin["path"]))
        if (result.get("task_id") != snapshot["task_id"] or result.get("department") != producer
                or not isinstance(result.get("candidate_version"), str) or not result["candidate_version"].strip()):
            raise w.WorkflowError("complete goal producer task/version mismatch")


def validate_verdict(root: Path, snapshot: dict, receipts: list, receipt: dict) -> None:
    w = _workflow()
    snapshot = _review_context(root, snapshot)
    binding = _verdict_binding(root, snapshot, receipts, receipt)
    plan = load_plan(root, snapshot, binding)
    if plan is None:
        if _goal(root, snapshot) is not None:
            raise w.WorkflowError("new assistant verdict requires its exact frozen review plan")
        if receipt.get("department") != "qa":
            raise w.WorkflowError("legacy and production reviewer remains fixed qa")
        return
    expected = {key: plan[key] for key in IDENTITY}
    reviewer = plan["reviewer_department"]
    if (receipt.get("department") != reviewer or receipt.get("chat_task_id") != plan["reviewer_thread_id"]
            or any(receipt.get(k) != plan[k] for k in ("task_id", "action_id", "action_class", "scope"))):
        raise w.WorkflowError("verdict differs from exact single-reviewer identity")
    indices = [(i, r) for i, r in enumerate(receipts)
               if r.get("department") == reviewer and r.get("receipt_type") in {"dispatch_sent", "dispatch_failed"}]
    inherited = None
    if not indices:
        from goal_delivery_runtime import review_delegation
        inherited = review_delegation(root, snapshot)
        if not inherited or binding.get("review_delegation") != inherited["binding"]:
            raise w.WorkflowError("latest actual reviewer dispatch required, or exact inherited delegation")
        dispatch, ack = inherited["dispatch"], inherited["ack"]
        initial_assignment = True
        boxes = [r for r in receipts if r.get("department") == reviewer and r.get("receipt_type") == "outbox_received"]
    else:
        if not indices or indices[-1][1].get("receipt_type") != "dispatch_sent":
            raise w.WorkflowError("latest actual reviewer dispatch required")
        index, dispatch = indices[-1]
        resumed = _assigned_review_round(root, snapshot, receipts, plan)
        initial_assignment = _initial_assignment(root, snapshot, dispatch) or resumed is not None
        strict_candidate_dispatch = (binding["pin"] in dispatch.get("evidence", [])
                                     and plan["candidate"] in dispatch.get("evidence", [])
                                     and dispatch.get("scope") == plan["scope"])
        if (not (initial_assignment or strict_candidate_dispatch)
                or dispatch.get("chat_task_id") != plan["reviewer_thread_id"]):
            raise w.WorkflowError("dispatch must freeze exact plan/candidate/scope")
        acknowledgements = [(i, r) for i, r in enumerate(receipts[index + 1:], index + 1)
                            if r.get("department") == reviewer and r.get("receipt_type") == "chat_ack"
                            and r.get("chat_task_id") == plan["reviewer_thread_id"] and r.get("ack_nonempty") is True]
        if not acknowledgements:
            raise w.WorkflowError("current nonempty fixed-reviewer ACK required")
        ack_index, ack = acknowledgements[-1]
        boxes = [r for r in receipts[ack_index + 1:] if r.get("department") == reviewer
                 and r.get("receipt_type") == "outbox_received"]
    if not boxes:
        raise w.WorkflowError("current exact reviewer outbox required")
    now = dt.datetime.now(dt.timezone.utc)
    stamps = [w._parse_observed_at(r.get("created_at")) for r in (dispatch, ack, boxes[-1], receipt)]
    if any(x is None for x in stamps) or not stamps[0] <= stamps[1] <= stamps[2] <= stamps[3] <= now:
        raise w.WorkflowError("actual reviewer timestamps must be ordered and not future")
    pin = next((p for p in boxes[-1].get("evidence", []) if p.get("path", "").endswith(".json")), None)
    if pin is None or pin not in receipt.get("evidence", []) or w.file_digest(root, pin["path"]) != pin:
        raise w.WorkflowError("verdict must reference current exact reviewer outbox bytes")
    box = w.read_json(w.safe_path(root, pin["path"]))
    w.validate_outbox(root, [pin], reviewer, plan["task_id"])
    if (initial_assignment or plan.get("rework_of")) and (binding["pin"] not in box.get("evidence", []) or plan["candidate"] not in box.get("evidence", [])):
        raise w.WorkflowError("initially assigned assistant final outbox must freeze the actual review plan and candidate")
    if plan.get("rework_of") and box.get("revalidation") != {"changed_scope": plan["changed_scope"], "methods": plan["revalidation_methods"]}:
        raise w.WorkflowError("rework verdict must state the exact changed scope and revalidation methods")
    reply = box.get("chat_reply", {})
    if (box.get("task_id") != plan["task_id"] or box.get("department") != reviewer
            or box.get("fixed_chat_task_id") != plan["reviewer_thread_id"]
            or box.get("candidate_version") != plan["candidate_version"]
            or box.get("review_identity") != expected or box.get("qa_verdict") != receipt.get("verdict")
            or box.get("risk_level") != plan["risk_level"]
            or any(box.get(k) is not False for k in ("production_write_allowed", "external_permission_issued", "production_release_eligible"))
            or reply.get("nonempty") is not True or reply.get("in_current_fixed_department_chat") is not True
            or not reply.get("ref") or not w.SHA256_PATTERN.fullmatch(str(reply.get("sha256", "")))):
        raise w.WorkflowError("exact real reply metadata and result-only reviewer outbox identity required")
    if inherited and box.get("review_delegation") != inherited["binding"]:
        raise w.WorkflowError("final reviewer outbox must declare the exact original delegation")
    _validate_goal_acceptance(root, snapshot, receipts, box, receipt.get("verdict"))
    producer_boxes = [r for r in receipts if r.get("department") == plan["producer_department"]
                      and r.get("receipt_type") == "outbox_received"]
    if not producer_boxes:
        raise w.WorkflowError("original producer outbox required")
    producer_pin = next((p for p in producer_boxes[-1].get("evidence", []) if p.get("path", "").endswith(".json")), None)
    producer = w.read_json(w.safe_path(root, producer_pin["path"])) if producer_pin else {}
    if producer.get("candidate_version") != plan["candidate_version"] or plan["candidate"] not in producer.get("evidence", []):
        raise w.WorkflowError("original producer must bind the reviewed candidate/version")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--plan", required=True)
    parser.add_argument("--coordinator-role", default="operations")
    args = parser.parse_args()
    try:
        result = bind_plan(args.project_root.resolve(), task_id=args.task_id, plan_path=args.plan,
                           coordinator_role=args.coordinator_role)
    except (ValueError, OSError, _workflow().WorkflowError) as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc), "production_write_allowed": False})); return 2
    print(json.dumps(result)); return 0


if __name__ == "__main__":
    raise SystemExit(main())
