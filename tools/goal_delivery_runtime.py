"""Complete-goal routing and evidence readers. No provider calls or new permits.

Local provenance is audit evidence, not authentication. Actual tool permissions,
human authorization and production channels remain outside this module.
"""
from __future__ import annotations
import argparse
import copy
from contextlib import nullcontext
import datetime as dt
import json
import re
import uuid
from pathlib import Path
import workflow_control as w

MODEL = "goal_delivery_assistant_v1"
REQUIRED = ("objective", "completion_criteria", "primary_owner", "responsible_assistant",
            "existing_results", "authorized_scope", "dependencies", "producer_departments",
            "acceptance_capability")


def enabled(root, snapshot=None):
    config = w.read_json(Path(root) / "data/task-contract.json").get("goal_delivery_runtime", {})
    return (config.get("model") == MODEL and config.get("assistant_decisions_enabled") is True
            and (snapshot is None or isinstance(snapshot.get("goal_delivery"), dict)))


def validate_goal(root, goal):
    if not enabled(root) or not isinstance(goal, dict) or any(k not in goal for k in REQUIRED):
        raise w.WorkflowError("enabled complete goal contract required")
    result = copy.deepcopy(goal)
    registry = w.department_registry(root)
    for name in ("objective", "primary_owner", "responsible_assistant", "acceptance_capability"):
        if not isinstance(result[name], str) or not result[name].strip():
            raise w.WorkflowError("nonempty complete goal identity required")
    for name in ("completion_criteria", "existing_results", "authorized_scope", "dependencies", "producer_departments"):
        if not isinstance(result[name], list) or len(result[name]) > 100:
            raise w.WorkflowError("bounded complete goal arrays required")
    if not result["completion_criteria"] or not result["authorized_scope"] or not result["producer_departments"]:
        raise w.WorkflowError("criteria, exact scope and producers required")
    if any(not isinstance(x, str) or not x.strip() or any(c in x for c in "*?[]|\n\r")
           for x in result["authorized_scope"]):
        raise w.WorkflowError("exact authorized scopes required")
    assistant = registry.get(result["responsible_assistant"], {})
    authority = assistant.get("coordination_authority", {})
    if (authority.get("routine_decisions") is not True
            or result["acceptance_capability"] not in authority.get("review_capabilities", [])
            or assistant.get("new_dispatch_enabled") is False):
        raise w.WorkflowError("assigned assistant lacks acceptance capability")
    producers = result["producer_departments"]
    if (len(set(producers)) != len(producers) or result["primary_owner"] not in producers
            or any(d not in registry or registry[d].get("new_dispatch_enabled") is False for d in producers)
            or result["responsible_assistant"] in producers):
        raise w.WorkflowError("registered independent producers and reviewer required; no self review")
    if result.get("parent_task_id"):
        w.validate_task_id(result["parent_task_id"])
    actions = result.setdefault("required_execution_actions", [])
    if not isinstance(actions, list) or len(actions) > 100:
        raise w.WorkflowError("bounded declared production actions required")
    identities = []
    for action in actions:
        if (not isinstance(action, dict) or not action.get("action_id")
                or action.get("action_class") not in w.EXTERNAL_ACTION_CLASSES
                or action.get("scope") not in result["authorized_scope"]
                or action.get("department") not in producers):
            raise w.WorkflowError("declared production action must use exact existing scope/producer/channel")
        identities.append(tuple(action.get(k) for k in ("action_id", "action_class", "scope", "department")))
    if len(set(identities)) != len(identities):
        raise w.WorkflowError("unique production action identities required")
    dependency_ids = []
    for dependency in result["dependencies"]:
        if not isinstance(dependency, dict):
            raise w.WorkflowError("explicit named dependency objects required")
        if "depends_on" in dependency:
            continue
        if (any(not dependency.get(k) for k in ("id", "owner", "scope", "unblock_condition"))
                or dependency["scope"] not in result["authorized_scope"]):
            raise w.WorkflowError("exact named external dependency/owner/condition required")
        dependency_ids.append(dependency["id"])
    if len(set(dependency_ids)) != len(dependency_ids):
        raise w.WorkflowError("unique dependency identities required")
    for pin in result["existing_results"]:
        if not isinstance(pin, dict) or w.file_digest(root, pin.get("path", "")) != pin:
            raise w.WorkflowError("existing result bytes must be reused exactly")
    auth = result.get("human_authorization")
    if not isinstance(auth, dict) or any(not auth.get(k) for k in
            ("source_thread_id", "message_id", "executor", "scope", "evidence_path")):
        raise w.WorkflowError("real human authorization provenance required")
    if auth["executor"] != result["primary_owner"] or auth["scope"] not in result["authorized_scope"]:
        raise w.WorkflowError("human authorization executor/scope mismatch")
    pin = w.file_digest(root, auth["evidence_path"])
    source = w.read_json(w.safe_path(root, pin["path"]))
    message = source.get("message", {})
    if (source.get("source_thread_id") != auth["source_thread_id"]
            or message.get("type") != "userMessage" or message.get("id") != auth["message_id"]
            or not any(c.get("type") == "text" and str(c.get("text", "")).strip()
                       for c in message.get("content", []) if isinstance(c, dict))):
        raise w.WorkflowError("native nonempty human message evidence required; no fabricated HQ dispatch")
    result["authorization_pin"] = pin
    result.setdefault("source_mode", "approved_dispatch")
    if result["source_mode"] not in {"approved_dispatch", "owner_direct"}:
        raise w.WorkflowError("known actual task source mode required")
    declarations = result.get('collaboration_scopes', [])
    if not isinstance(declarations, list) or len(declarations) > 100:
        raise w.WorkflowError('bounded exact collaboration declarations required')
    bindings = w.read_json(Path(root) / 'data/department-registry.json').get('collaboration_bindings', {})
    seen = set()
    for declaration in declarations:
        if (not isinstance(declaration, dict) or declaration.get('scope') not in result['authorized_scope']
                or declaration.get('sender_department') != result['primary_owner']
                or declaration.get('target_department') not in bindings):
            raise w.WorkflowError('original owner exact collaboration scope and fixed binding required')
        key = (declaration['scope'], declaration['target_department'])
        if key in seen:
            raise w.WorkflowError('unique collaboration declaration required')
        seen.add(key)
    return result


def restore_goal(root, snapshot):
    result = copy.deepcopy(snapshot)
    for row in w.read_jsonl(Path(root) / w.WORKFLOW_EVENTS):
        if row.get("task_id") != snapshot.get("task_id"):
            continue
        detail = row.get("details", {})
        if isinstance(detail.get("goal_delivery"), dict):
            result["goal_delivery"] = detail["goal_delivery"]
    if enabled(root, result):
        goal = result["goal_delivery"]
        if w.file_digest(root, goal["authorization_pin"]["path"]) != goal["authorization_pin"]:
            raise w.WorkflowError("frozen human authorization changed")
    return result


def bind_goal(root, task_id, goal):
    task_id = w.validate_task_id(task_id)
    goal = validate_goal(root, goal)
    if goal.get("parent_task_id") == task_id:
        raise w.WorkflowError("goal cannot be its own parent")
    with w.workflow_lock(root):
        snapshot = w.read_json(w.snapshot_path(root, task_id))
        if not snapshot:
            raise w.WorkflowError("existing original workflow required")
        if w.validate_workflow_events(root, task_id) or w._validate_receipt_chain(root, task_id)[1]:
            raise w.WorkflowError("valid original event and receipt chains required")
        old = restore_goal(root, snapshot).get("goal_delivery")
        if old is not None:
            if old != goal:
                raise w.WorkflowError("goal is frozen; use explicit scoped transfer or new goal")
            return {"result": "duplicate_ignored", "goal_delivery": goal}
        planned = {x["department"] for x in snapshot.get("departments", [])}
        if not (set(goal["producer_departments"]) | {goal["responsible_assistant"]}) <= planned:
            raise w.WorkflowError("complete-goal producers and assistant must be planned")
        w.append_workflow_event(root, task_id, snapshot["current_state"], {"goal_delivery": goal, "goal_delivery_bound": True})
        snapshot["goal_delivery"] = goal
        snapshot["updated_at"] = w.utc_timestamp()
        w.atomic_write_json(w.snapshot_path(root, task_id), snapshot)
    return {"result": "bound", "goal_delivery": goal, "external_permission_issued": False}



def _native_document(root, pin):
    if not isinstance(pin, dict) or w.file_digest(root, pin.get("path", "")) != pin:
        raise w.WorkflowError("frozen delegation evidence changed")
    value = w.read_json(w.safe_path(root, pin["path"]))
    if value.get("isError") is True:
        raise w.WorkflowError("failed native delegation evidence")
    if "content" in value and not value.get("thread"):
        texts = [x.get("text", "") for x in value["content"] if x.get("type") == "text"]
        if len(texts) != 1:
            raise w.WorkflowError("one actual native delegation document required")
        try:
            value = json.loads(texts[0])
        except (ValueError, TypeError):
            raise w.WorkflowError("actual native delegation document required")
    return value


def _delegation_context(root, snapshot, binding):
    """Read existing source receipts; never synthesize a child dispatch or ACK."""
    snapshot = restore_goal(root, snapshot)
    goal = snapshot.get("goal_delivery", {})
    role = goal.get("responsible_assistant")
    source_id = w.validate_task_id(binding.get("delegation_task_id", ""))
    admissions = w.read_json(Path(root) / "data/task-contract.json").get("goal_delivery_runtime", {}).get("review_delegation_admission", [])
    expected = [x for x in admissions if x.get("delegation_task_id") == source_id]
    if len(expected) != 1 or any(binding.get(k) != v for k, v in expected[0].items()):
        raise w.WorkflowError("original frozen delegation admission and approved source pins required")
    if (not enabled(root, snapshot) or source_id == snapshot["task_id"]
            or binding.get("task_id") != snapshot["task_id"]
            or binding.get("parent_task_id") != goal.get("parent_task_id")
            or binding.get("responsible_assistant") != role
            or role in goal.get("producer_departments", [])
            or binding.get("authority") != goal.get("authorization_pin")
            or goal.get("required_execution_actions")):
        raise w.WorkflowError("exact independent internal child delegation identity required")
    if w.file_digest(root, binding["authority"]["path"]) != binding["authority"]:
        raise w.WorkflowError("original human authorization changed")
    # Invalid JSON must not be silently skipped by the legacy reader.
    for path in (w.receipts_path(root, source_id), Path(root) / w.WORKFLOW_EVENTS):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    row = json.loads(line)
                except ValueError:
                    raise w.WorkflowError("intact actual delegation chains required")
                if not isinstance(row, dict):
                    raise w.WorkflowError("intact actual delegation chains required")
    rows, invalid = w._validate_receipt_chain(root, source_id)
    if invalid or w.validate_workflow_events(root, source_id):
        raise w.WorkflowError("intact actual delegation chains required")
    selected = []
    for kind, key in (("dispatch_sent", "dispatch"), ("chat_ack", "ack")):
        ref = binding.get(key, {})
        matches = [(i, r) for i, r in enumerate(rows) if r.get("receipt_id") == ref.get("receipt_id")
                   and r.get("receipt_hash") == ref.get("receipt_hash") and r.get("receipt_type") == kind]
        if len(matches) != 1:
            raise w.WorkflowError("exact original delegation dispatch and ACK required")
        selected.append(matches[0])
    (di, dispatch), (ai, ack) = selected
    registry = w.department_registry(root)
    fixed = registry.get(role, {}).get("chat_binding", {})
    if (di >= ai or ack.get("ack_nonempty") is not True
            or any(r.get("department") != role or r.get("chat_task_id") != fixed.get("task_id") for r in (dispatch, ack))
            or any(r.get("department") == role and r.get("receipt_type") in {"dispatch_sent", "dispatch_failed"}
                   and (r.get("supersedes_receipt_id") == dispatch["receipt_id"]
                        or (r.get("action_id") == dispatch.get("action_id") and r.get("scope") == dispatch.get("scope")))
                   for r in rows[di+1:])
            or registry.get(role, {}).get("new_dispatch_enabled") is False
            or not any(x.get("department") == role and x.get("chat_task_id") == fixed.get("task_id")
                       for x in snapshot.get("departments", []))
            or registry.get(role, {}).get("coordination_authority", {}).get("routine_decisions") is not True
            or goal["acceptance_capability"] not in registry[role]["coordination_authority"].get("review_capabilities", [])):
        raise w.WorkflowError("current same fixed capable assistant delegation required")
    for key, receipt in (("message", dispatch), ("native_send", dispatch), ("native_ack", ack)):
        pin = binding.get(key)
        if pin not in receipt.get("evidence", []) or w.file_digest(root, pin.get("path", "")) != pin:
            raise w.WorkflowError("selected actual delegation receipt evidence required")
    send = _native_document(root, binding["native_send"])
    native_ack = _native_document(root, binding["native_ack"])
    messages = [m for turn in native_ack.get("turns", []) for m in turn.get("items", [])
                if m.get("type") == "agentMessage" and m.get("id") == binding.get("ack_message_id")
                and isinstance(m.get("text"), str) and m["text"].strip()]
    if (send.get("threadId") != fixed.get("task_id")
            or native_ack.get("thread", {}).get("id") != fixed.get("task_id") or len(messages) != 1):
        raise w.WorkflowError("actual same fixed thread send and nonempty native ACK required")
    decisions = [r for r in w.read_jsonl(Path(root) / "logs/policy-decisions.jsonl")
                 if r.get("decision_id") == dispatch.get("policy_decision_id")]
    message = binding["message"]
    expected = {"department": "operations", "task_id": source_id, "status": "allow",
                "action_class": "thread_message", "action_id": dispatch.get("action_id"),
                "scope": dispatch.get("scope"), "payload_sha256": message["sha256"],
                "target_department": role, "target_thread_id": fixed.get("task_id"),
                "target_thread_title": fixed.get("title"), "source_project_id": fixed.get("project_id"),
                "target_project_id": fixed.get("project_id"), "target_cwd": fixed.get("cwd"),
                "target_sidebar_section_id": fixed.get("sidebar_section_id")}
    if len(decisions) != 1 or any(decisions[0].get(k) != v for k, v in expected.items()):
        raise w.WorkflowError("actual HQ delegation allow and exact payload identity required")
    approval_pin = binding.get("approved_goals", {})
    if w.file_digest(root, approval_pin.get("path", "")) != approval_pin:
        raise w.WorkflowError("frozen approved child list changed")
    approval = w.read_json(w.safe_path(root, approval_pin["path"]))
    text = w.safe_path(root, message["path"]).read_text(encoding="utf-8")
    prepared = w._parse_observed_at(approval.get("prepared_at"))
    sent = w._parse_observed_at(dispatch.get("created_at"))
    if (approval.get("parent_task_id") != goal.get("parent_task_id")
            or approval.get("authorized_by") != "operations" or approval.get("reviewer") != role
            or approval.get("no_external_write") is not True
            or approval.get("state") != "approved_internal_pilot_not_dispatched"
            or not prepared or not sent or prepared > sent
            or source_id not in text or goal.get("parent_task_id", "") not in text
            or approval_pin["path"] not in text):
        raise w.WorkflowError("existing complete dispatch must explicitly delegate the approved internal children")
    entries = [x for x in approval.get("tasks", []) if x.get("task_id") == snapshot["task_id"]]
    if len(entries) != 1:
        raise w.WorkflowError("child is not in the original approved list")
    entry = entries[0]
    child_message = w.file_digest(root, entry.get("message_path", ""))
    if (entry.get("department") != goal["primary_owner"]
            or goal["producer_departments"] != [entry.get("department")]
            or goal["authorized_scope"] != [entry.get("approved_scope")]
            or entry.get("already_sent") is not False
            or child_message["sha256"] != entry.get("message_sha256")
            or binding.get("child_message") != child_message):
        raise w.WorkflowError("exact approved child producer scope and original message required")
    return {"binding": binding, "dispatch": dispatch, "ack": ack}


def review_delegation(root, snapshot):
    events = [r for r in w.read_jsonl(Path(root) / w.WORKFLOW_EVENTS) if r.get("task_id") == snapshot.get("task_id")]
    bindings = [r["details"]["review_delegation_bound"] for r in events if r.get("details", {}).get("review_delegation_bound")]
    if not bindings:
        return None
    if any(b != bindings[0] for b in bindings) or w.validate_workflow_events(root, snapshot["task_id"]):
        raise w.WorkflowError("one intact frozen child delegation binding required")
    return _delegation_context(root, snapshot, bindings[0])


def bind_review_delegation(root, task_id, input_path, coordinator_role):
    task_id = w.validate_task_id(task_id)
    binding = w.read_json(w.safe_path(root, input_path))
    with w.workflow_lock(root):
        snapshot = restore_goal(root, w.read_json(w.snapshot_path(root, task_id)))
        if coordinator_role not in {"operations", snapshot.get("goal_delivery", {}).get("responsible_assistant")}:
            raise w.WorkflowError("only the original assigned assistant binds delegation")
        rows, invalid = w._validate_receipt_chain(root, task_id)
        if invalid or w.validate_workflow_events(root, task_id):
            raise w.WorkflowError("valid child chains required")
        role = snapshot.get("goal_delivery", {}).get("responsible_assistant")
        _delegation_context(root, snapshot, binding)
        old = review_delegation(root, snapshot)
        if old:
            if old["binding"] != binding:
                raise w.WorkflowError("child delegation is frozen")
            return {"result": "duplicate_ignored", "binding": binding}
        if any(r.get("department") == role for r in rows):
            raise w.WorkflowError("cannot replace existing child reviewer history with inherited delegation")
        w.append_workflow_event(root, task_id, snapshot["current_state"], {"review_delegation_bound": binding})
        snapshot["review_delegation"] = binding
        w.atomic_write_json(w.snapshot_path(root, task_id), snapshot)
    return {"result": "bound", "binding": binding, "child_native_receipts_created": 0,
            "external_permission_issued": False}


def assigned_actor(root, snapshot, role, scope=None):
    if not enabled(root, snapshot):
        return False
    goal = snapshot["goal_delivery"]
    authority = w.department_registry(root).get(role, {}).get("coordination_authority", {})
    return (role in {"operations", goal["responsible_assistant"]}
            and (role == "operations" or authority.get("dispatch_approved_next") is True)
            and (scope is None or scope in goal["authorized_scope"]))


def approved_action(root, snapshot, requested):
    """A scoped goal does not authorize an arbitrary next message payload."""
    goal = snapshot["goal_delivery"]
    rows = [x for x in goal.get("approved_actions", []) if isinstance(x, dict)
            and all(x.get(k) == requested.get(k) for k in requested)]
    if len(rows) != 1 or not w.SHA256_PATTERN.fullmatch(str(requested.get("payload_sha256", ""))):
        return None
    row = rows[0]
    pin = row.get("payload")
    if (not isinstance(pin, dict) or w.file_digest(root, pin.get("path", "")) != pin
            or pin["sha256"] != requested["payload_sha256"]):
        return None
    return row


def collaboration_route(root, snapshot, requested):
    registry = w.read_json(Path(root) / "data/department-registry.json")
    binding = registry.get("collaboration_bindings", {}).get(requested.get("target_department"))
    if not isinstance(binding, dict):
        return None
    reasons = []
    goal = snapshot["goal_delivery"]
    if (requested.get("action_class") != "thread_message"
            or requested.get("scope") not in goal["authorized_scope"]
            or not (assigned_actor(root, snapshot, requested.get("sender_department"), requested.get("scope"))
                    or requested.get("sender_department") == goal["primary_owner"])):
        reasons.append("goal_collaboration_exact_authorized_actor_scope_required")
    mapping = {"target_project_id": "project_id", "target_thread_id": "thread_id",
               "target_thread_title": "title", "target_cwd": "cwd"}
    if any(not binding.get(v) or requested.get(k) != binding[v] for k, v in mapping.items()):
        reasons.append("goal_collaboration_exact_binding_required")
    source = w.department_registry(root).get(requested.get("sender_department"), {}).get("chat_binding", {})
    if (source.get("project_id") != requested.get("source_project_id")
            or not w._same_resolved_path(str(source.get("cwd", "")), str(Path(root).resolve()))
            or not w._chat_binding_healthy(source, verification_ttl_hours=26)):
        reasons.append("goal_collaboration_actual_source_binding_required")
    try:
        for pin in goal.get("collaboration_records", []):
            if w.file_digest(root, pin["path"]) != pin:
                raise w.WorkflowError("actual collaboration ledger bytes changed")
            prior = w.read_json(w.safe_path(root, pin["path"]))
            if prior.get("action_id") == requested.get("action_id") and prior.get("status") in {"sent", "result_received"}:
                reasons.append("goal_collaboration_already_dispatched_read_before_retry")
        if w.file_digest(root, goal["authorization_pin"]["path"]) != goal["authorization_pin"]:
            reasons.append("goal_collaboration_original_human_provenance_changed")
        action = approved_action(root, snapshot, requested)
        if action is None:
            reasons.append("goal_collaboration_frozen_approved_message_required")
        else:
            pin = action.get("live_identity")
            if not isinstance(pin, dict) or w.file_digest(root, pin.get("path", "")) != pin:
                raise w.WorkflowError("exact live proof required")
            live = w.read_json(w.safe_path(root, pin["path"]))
            observed = w._parse_observed_at(live.get("observed_at"))
            targets = [x for x in live.get("threads", []) if x.get("id") == binding["thread_id"]]
            sources = [x for x in live.get("threads", []) if x.get("id") == source.get("task_id")]
            now = dt.datetime.now(dt.timezone.utc)
            if (observed is None or not 0 <= (now - observed).total_seconds() <= 300
                    or len(targets) != 1 or len(sources) != 1
                    or any(targets[0].get(k) != v for k, v in {"projectId": binding["project_id"],
                           "title": binding["title"], "cwd": binding["cwd"], "status": "idle"}.items())
                    or any(sources[0].get(k) != v for k, v in {"projectId": source.get("project_id"),
                           "title": source.get("title"), "cwd": source.get("cwd")}.items())
                    or live.get("target_sidebar_section_id") != requested.get("target_sidebar_section_id")
                    or not live.get("native_receipt_ref")):
                reasons.append("goal_collaboration_fresh_actual_idle_identity_required")
    except (w.WorkflowError, KeyError, TypeError, ValueError, OSError):
        reasons.append("goal_collaboration_frozen_evidence_invalid")
    return reasons


def prepare_assignment_transfer(root, identity, assignment_change):
    """Read-only validation under caller's coordination and workflow locks.

    Reused before lease commit and after commit/recovery. No SQL connection,
    workflow lock reacquisition, receipt append or assignment write occurs here.
    """
    snapshot = restore_goal(root, w.read_json(w.snapshot_path(root, identity["task_id"])))
    goal = snapshot.get("goal_delivery", {})
    history = list(goal.get("assignment_history", []))
    if assignment_change in history:
        return snapshot, None
    if goal.get("responsible_assistant") != assignment_change.get("previous_assistant"):
        raise w.WorkflowError("original responsible assistant changed; exact recovery required")
    receipts, invalid = w._validate_receipt_chain(root, identity["task_id"])
    if invalid or w.validate_workflow_events(root, identity["task_id"]):
        raise w.WorkflowError("intact original chains required for assignment transfer")
    if any(x.get("receipt_type") == "qa_verdict" for x in receipts):
        raise w.WorkflowError("accepted verdict cannot be migrated")
    packet = assignment_change.get("review_plan_transfer")
    details = {}
    if packet:
        from qa_review_plan import _binding, transfer_plan
        if _binding(root, snapshot) != packet["previous_binding"]:
            raise w.WorkflowError("previous frozen review plan changed")
        prepared = transfer_plan(root, task_id=identity["task_id"], plan_path=packet["new_binding"]["pin"]["path"],
                                 target_role=assignment_change["target_assistant"], prepare_only=True)
        if prepared != packet:
            raise w.WorkflowError("prepared exact candidate transfer changed")
        snapshot["qa_review_plan"] = packet["new_binding"]
        snapshot["departments"] = packet["departments"]
        details["qa_review_plan_bound"] = packet["new_binding"]
        details["assignment_departments"] = packet["departments"]
    else:
        target = assignment_change["target_assistant"]
        binding = w.department_registry(root)[target].get("chat_binding", {})
        if not w._chat_binding_healthy(binding, verification_ttl_hours=26):
            raise w.WorkflowError("fresh actual target assistant binding required for transfer recovery")
        rows = [{**item, "department": target, "chat_task_id": binding["task_id"]}
                if item.get("department") == assignment_change["previous_assistant"] else item
                for item in snapshot.get("departments", [])]
        if not any(item.get("department") == target for item in rows):
            rows.append({"department": target, "chat_task_id": binding["task_id"],
                         "execution_wave": max([r.get("execution_wave", 1) for r in rows] + [1]) + 1,
                         "depends_on": list(goal["producer_departments"])})
        snapshot["departments"] = rows
        details["assignment_departments"] = rows
    return snapshot, details


def record_assignment_transfer(root, identity, assignment_change, *, _workflow_locked=False):
    """Replay a committed fenced transfer while caller holds coordination lock."""
    from result_coordination import CoordinationStore, exact_identity
    identity = exact_identity(identity)
    store = CoordinationStore(root)
    try:
        store._begin()
        row = store._row(identity)
        audits = [json.loads(x["payload_json"]) for x in store.conn.execute("SELECT payload_json FROM coordination_audit ORDER BY seq")]
        valid = [x for x in audits if x.get("event") == "transfer"
                 and x.get("identity") == identity and x.get("details", {}).get("assignment_change") == assignment_change]
        if (not valid or row is None or row["fence"] != assignment_change.get("fence")
                or row["role"] != assignment_change.get("target_assistant")):
            raise w.WorkflowError("committed fenced assignment audit required")
        store.conn.commit()
    finally:
        store.close()
    with (nullcontext() if _workflow_locked else w.workflow_lock(root)):
        snapshot, details = prepare_assignment_transfer(root, identity, assignment_change)
        goal = snapshot.get("goal_delivery", {})
        history = list(goal.get("assignment_history", []))
        if details is None:
            return {"result": "duplicate_ignored", "responsible_assistant": goal["responsible_assistant"]}
        goal = {**goal, "responsible_assistant": assignment_change["target_assistant"],
                "assignment_history": history + [assignment_change]}
        snapshot["goal_delivery"] = goal
        details.update(goal_delivery=goal, assignment_transfer=assignment_change)
        w.append_workflow_event(root, identity["task_id"], snapshot["current_state"], details)
        snapshot["updated_at"] = w.utc_timestamp()
        w.atomic_write_json(w.snapshot_path(root, identity["task_id"]), snapshot)
    return {"result": "recorded", "responsible_assistant": goal["responsible_assistant"],
            "fence": assignment_change["fence"], "old_verdict_migrated": False}


def owner_direct(root, snapshot, department):
    if not enabled(root, snapshot):
        return False
    goal = snapshot["goal_delivery"]
    if goal.get("source_mode") != "owner_direct" or department not in goal["producer_departments"]:
        return False
    return w.file_digest(root, goal["authorization_pin"]["path"]) == goal["authorization_pin"]


def execution_preflight(root, snapshot, action_id, action_class, scope, department):
    """Exact self-check replaces serial QA, but never the existing approval gate."""
    if not enabled(root, snapshot):
        return None
    goal = snapshot["goal_delivery"]
    if scope not in goal["authorized_scope"] or department not in goal["producer_departments"]:
        raise w.WorkflowError("execution outside complete-goal authorized scope")
    declared = goal.get("required_execution_actions", [])
    if declared and not any(all(x.get(k) == v for k, v in
               {"action_id": action_id, "action_class": action_class, "scope": scope, "department": department}.items()) for x in declared):
        raise w.WorkflowError("production action differs from frozen delivery requirements")
    items = [x for x in goal.get("execution_preflights", []) if all(x.get(k) == v for k, v in
             {"action_id": action_id, "action_class": action_class, "scope": scope, "department": department}.items())]
    if len(items) != 1:
        raise w.WorkflowError("one exact production self-check required")
    item = items[0]
    if item.get("risk_level") not in {"R1", "R2", "R3"}:
        raise w.WorkflowError("explicit production risk required")
    for name in ("facts", "self_check", "backup", "rollback"):
        pin = item.get(name)
        if not isinstance(pin, dict) or w.file_digest(root, pin.get("path", "")) != pin:
            raise w.WorkflowError("exact facts/self-check/backup/rollback evidence required")
    check = w.read_json(w.safe_path(root, item["self_check"]["path"]))
    if check.get("status") != "PASS" or any(check.get(k) != item[k] for k in
            ("action_id", "action_class", "scope", "department")):
        raise w.WorkflowError("exact successful production self-check required")
    return item


def status(root, task_id):
    snapshot, _ = w.reconcile_workflow(root, task_id=task_id)
    if not enabled(root, snapshot):
        raise w.WorkflowError("bound complete goal required")
    goal = snapshot["goal_delivery"]
    state = snapshot.get("current_state")
    names = {"evidence_received": "awaiting_assistant_acceptance", "qa_blocked": "rework",
             "closed": "completed_scope", "waiting_owner_approval": "specific_dependency_wait"}
    handoff = w.result_handoff_status(root, task_id)
    children = []
    for path in (Path(root) / w.WORKFLOW_DIR).glob("*.json"):
        child = w.read_json(path)
        if child.get("goal_delivery", {}).get("parent_task_id") == task_id:
            children.append({"task_id": child["task_id"], "state": child.get("current_state"),
                             "does_not_auto_close_parent": True})
    rows = w._result_handoff_rows(root, task_id)
    follow = next((r for r in reversed(rows) if r.get("event") == "controller_followthrough"), {})
    states = {"dispatch_sent": "next_task_actually_assigned", "external_wait_registered": "specific_dependency_wait",
              "blocked_with_owner": "specific_dependency_wait", "no_executable_work": "temporarily_no_executable_work"}
    return {"task_id": task_id, "state": states.get(follow.get("followthrough_status"), names.get(state, "executing")), "native_workflow_state": state,
            "primary_owner": goal["primary_owner"], "responsible_assistant": goal["responsible_assistant"],
            "parent_task_id": goal.get("parent_task_id"), "children": children,
            "completion_criteria": goal["completion_criteria"], "result_handoff": handoff,
            "latest_actual_followthrough": follow, "collaboration_records": goal.get("collaboration_records", []),
            "HQ_second_review_required": False, "business_goal_closed": False,
            "organic_ip_goal": "DATA_MISSING", "AI_effect": "NOT_MEASURED"}


def pending(root, role):
    registry = w.department_registry(root)
    if registry.get(role, {}).get("coordination_authority", {}).get("routine_decisions") is not True:
        raise w.WorkflowError("registered assistant coordinator required")
    owned = [p.stem for p in (Path(root) / w.WORKFLOW_DIR).glob("*.json")
             if w.read_json(p).get("goal_delivery", {}).get("responsible_assistant") == role]
    from result_coordination import result_lane
    for path in (Path(root) / w.RESULT_HANDOFF_DIR).glob('*.jsonl'):
        if path.stem in owned:
            continue
        for row in w._result_handoff_rows(root, path.stem):
            if row.get('event') != 'notification_queued':
                continue
            lane = result_lane(root, row)
            if lane.get('source_mode') == 'scheduled_run' and lane.get('target_department') == role:
                owned.append(path.stem)
                break
    waiting, followthrough, collaboration_pending, collaboration_not_proven = [], [], [], []
    knowledge, notifications, named_due = [], [], []
    from result_coordination import result_lane, notification_plan
    for task_id in owned:
        grouped = {}
        for row in w._result_handoff_rows(root, task_id):
            key = w._result_identity(row)
            entry = grouped.setdefault(key, {"task_id": task_id, "sender_department": key[0],
                        "candidate_version": key[1], "result_sha256": key[2], "received": False,
                        "decided": False, "queued": False, "controller_followthrough": "pending"})
            if row["event"] == "notification_queued": entry["queued"] = True
            elif row["event"] == "controller_received": entry["received"] = True
            elif row["event"] == "controller_decision":
                entry.update(decided=True, controller_decision=row.get("decision"), next_owner=row.get("next_owner"), next_action=row.get("next_action"))
            elif row["event"] == "controller_followthrough":
                entry.update(controller_followthrough=row.get("followthrough_status"), next_check_at=row.get("next_check_at"))
        for entry in grouped.values():
            lane = result_lane(root, entry)
            entry.update(result_lane=lane['lane'], target_department=lane.get('target_department'))
            if lane.get('source_mode') == 'collaboration':
                # This exact source is counted by collaboration_pending below;
                # it has no ordinary queued outbox or notification workload.
                continue
            if lane['lane'] == 'HQ_knowledge':
                entry['acceptance_proven'] = lane.get('acceptance_proven', False)
                if not entry['received']:
                    knowledge.append(entry)
                continue
            if lane['lane'] != 'professional_acceptance':
                continue
            if not entry['decided'] and (entry['queued'] or entry['received']):
                waiting.append(entry)
            if entry['decided'] and w._followthrough_due(entry):
                followthrough.append(entry)
                if entry.get('controller_decision') == 'wait_external':
                    named_due.append(entry)
        snapshot = restore_goal(root, w.read_json(w.snapshot_path(root, task_id)))
        if enabled(root, snapshot) and snapshot["goal_delivery"]["responsible_assistant"] == role:
            collaboration_pending.extend(_collaboration_pending(root, snapshot, role))
            if snapshot.get("current_state") not in w.TERMINAL_STATES:
                collaboration_not_proven.extend(state for state in _collaboration_wait_states(root, snapshot)
                                                if state["proof_state"] == "NOT_PROVEN")
    return {"coordinator_role": role, "pending": waiting, "pending_count": len(waiting),
            "followthrough_pending": followthrough, "followthrough_pending_count": len(followthrough),
            "collaboration_pending": collaboration_pending, "collaboration_pending_count": len(collaboration_pending),
            "collaboration_not_proven": collaboration_not_proven,
            "collaboration_not_proven_count": len(collaboration_not_proven),
            "professional_pending_count": len(waiting), "HQ_knowledge_pending": knowledge,
            "HQ_knowledge_pending_count": len(knowledge), "named_due_dependencies": named_due,
            "named_due_dependency_count": len(named_due),
            "notification_delivery_pending": notification_plan(root, role)['notifications'],
            "notification_delivery_pending_count": notification_plan(root, role)['pending_count'],
            "durable_inbox_does_not_wake_ended_chat": True}


def record_preflight(root, task_id, input_path):
    item = w.read_json(w.safe_path(root, input_path))
    with w.workflow_lock(root):
        snapshot = restore_goal(root, w.read_json(w.snapshot_path(root, task_id)))
        if not enabled(root, snapshot) or snapshot.get("current_state") in w.TERMINAL_STATES:
            raise w.WorkflowError("active complete goal required")
        goal = snapshot["goal_delivery"]
        prior = goal.get("execution_preflights", [])
        matches = [x for x in prior if all(x.get(k) == item.get(k) for k in ("action_id", "action_class", "scope", "department"))]
        if matches:
            if matches != [item]:
                raise w.WorkflowError("exact preflight frozen; new action identity required")
            return {"result": "duplicate_ignored", "external_permission_issued": False}
        candidate = {**snapshot, "goal_delivery": {**goal, "execution_preflights": prior + [item]}}
        if item.get("action_class") not in w.EXTERNAL_ACTION_CLASSES:
            raise w.WorkflowError("existing production channel required")
        execution_preflight(root, candidate, item.get("action_id"), item.get("action_class"), item.get("scope"), item.get("department"))
        snapshot["goal_delivery"] = candidate["goal_delivery"]
        w.append_workflow_event(root, task_id, snapshot["current_state"], {"goal_delivery": snapshot["goal_delivery"],
                                "production_preflight_registered": w.file_digest(root, input_path), "external_permission_issued": False})
        w.atomic_write_json(w.snapshot_path(root, task_id), snapshot)
    return {"result": "recorded", "external_permission_issued": False, "assistant_acceptance_after_delivery": True}


def record_approved_action(root, task_id, input_path):
    """Freeze a precise routine decision, or owner action in an original declared collaboration scope."""
    action = w.read_json(w.safe_path(root, input_path))
    with w.workflow_lock(root):
        snapshot = restore_goal(root, w.read_json(w.snapshot_path(root, task_id)))
        if not enabled(root, snapshot):
            raise w.WorkflowError("complete original goal required")
        goal = snapshot["goal_delivery"]
        declarations = [d for d in goal.get('collaboration_scopes', []) if isinstance(d, dict)
                        and d.get('target_department') == action.get('target_department')
                        and d.get('scope') == action.get('scope')
                        and d.get('sender_department') == action.get('sender_department') == goal['primary_owner']]
        declared = len(declarations) == 1
        decisions = [row for row in w._result_handoff_rows(root, task_id)
                     if row.get("event") == "controller_decision" and row.get("record_id") == action.get("decision_record_id")]
        if not declared and (len(decisions) != 1 or decisions[0].get("decision") not in {"rework", "continue", "accept"}
                or decisions[0].get("coordinator_role") != goal["responsible_assistant"]
                or action.get("sender_department") != goal["responsible_assistant"]
                or action.get("target_department") != decisions[0].get("next_owner")
                or action.get("target_department") not in goal["producer_departments"]
                or action.get("action_class") != "thread_message" or action.get("task_id") != task_id
                or action.get("scope") not in goal["authorized_scope"] or not action.get("action_id")):
            raise w.WorkflowError("actual assigned routine decision and original producer/scope required")
        if declared and (action.get('action_class') != 'thread_message' or action.get('task_id') != task_id
                         or not action.get('action_id') or snapshot.get('current_state') in w.TERMINAL_STATES
                         or w.file_digest(root, goal['authorization_pin']['path']) != goal['authorization_pin']):
            raise w.WorkflowError('active same goal original owner authorization required')
        pin = action.get("payload")
        if (not isinstance(pin, dict) or w.file_digest(root, pin.get("path", "")) != pin
                or pin["sha256"] != action.get("payload_sha256")):
            raise w.WorkflowError("exact prepared approved message bytes required")
        binding = (w.read_json(Path(root) / 'data/department-registry.json').get('collaboration_bindings', {}).get(action['target_department'], {})
                   if declared else w.department_registry(root)[action["target_department"]].get("chat_binding", {}))
        mapping = {"target_thread_id": "thread_id" if declared else "task_id", "target_thread_title": "title", "target_cwd": "cwd",
                   "target_project_id": "project_id", "target_sidebar_section_id": "sidebar_section_id"}
        if declared:
            mapping.pop('target_sidebar_section_id')
        if any(action.get(k) != binding.get(v) or not binding.get(v) for k, v in mapping.items()):
            raise w.WorkflowError("exact original fixed producer/collaboration binding required")
        old = [x for x in goal.get("approved_actions", []) if x.get("action_id") == action["action_id"]]
        if old:
            if old != [action]:
                raise w.WorkflowError("routine action identity already frozen to different bytes")
            return {"result": "duplicate_ignored", "actual_message_sent": False}
        snapshot["goal_delivery"] = {**goal, "approved_actions": goal.get("approved_actions", []) + [action]}
        w.append_workflow_event(root, task_id, snapshot["current_state"], {"goal_delivery": snapshot["goal_delivery"],
                               "approved_message_prepared": w.file_digest(root, input_path), "actual_message_sent": False})
        w.atomic_write_json(w.snapshot_path(root, task_id), snapshot)
    return {"result": "recorded", "actual_message_sent": False, "external_permission_issued": False}


def record_dependency(root, task_id, input_path):
    pin = w.file_digest(root, input_path)
    receipt = w.read_json(w.safe_path(root, input_path))
    with w.workflow_lock(root):
        snapshot = restore_goal(root, w.read_json(w.snapshot_path(root, task_id)))
        if not enabled(root, snapshot):
            raise w.WorkflowError("complete parent goal required")
        goal = snapshot["goal_delivery"]
        dependencies = [d for d in goal["dependencies"] if d.get("id") == receipt.get("dependency_id")]
        if (len(dependencies) != 1 or receipt.get("task_id") != task_id or receipt.get("status") != "resolved"
                or any(receipt.get(k) != dependencies[0].get(k) for k in ("owner", "scope", "unblock_condition"))
                or not receipt.get("native_receipt_ref")):
            raise w.WorkflowError("exact named actual dependency resolution receipt required")
        evidence = receipt.get("evidence")
        if not isinstance(evidence, dict) or w.file_digest(root, evidence.get("path", "")) != evidence:
            raise w.WorkflowError("actual frozen dependency input required")
        previous = goal.get("dependency_records", [])
        if pin in previous:
            return {"result": "duplicate_ignored", "parent_closed": False}
        snapshot["goal_delivery"] = {**goal, "dependency_records": previous + [pin]}
        w.append_workflow_event(root, task_id, snapshot["current_state"], {"goal_delivery": snapshot["goal_delivery"], "dependency_receipt": pin})
        w.atomic_write_json(w.snapshot_path(root, task_id), snapshot)
    return {"result": "recorded", "parent_closed": False, "assistant_acceptance_required": True}


def completion_dependencies(root, snapshot):
    goal = snapshot["goal_delivery"]; missing = []
    records = []
    for pin in goal.get("dependency_records", []):
        if w.file_digest(root, pin["path"]) != pin:
            raise w.WorkflowError("frozen actual dependency record changed")
        record = w.read_json(w.safe_path(root, pin["path"]))
        if w.file_digest(root, record["evidence"]["path"]) != record["evidence"]:
            raise w.WorkflowError("frozen actual dependency input changed")
        records.append(record)
    for dep in goal["dependencies"]:
        if "depends_on" in dep:
            continue
        if not any(r.get("status") == "resolved" and r.get("dependency_id") == dep.get("id")
                   and all(r.get(k) == dep.get(k) for k in ("owner", "scope", "unblock_condition")) for r in records):
            missing.append("external_dependency:" + dep["id"] + ":owner:" + dep["owner"])
    collaboration_states = _collaboration_wait_states(root, snapshot)
    formal_pending = _collaboration_pending(root, snapshot, goal["responsible_assistant"], include_terminal=True)
    for state in collaboration_states:
        if state.get("proof_state") == "NOT_PROVEN" and not state.get("action_id"):
            missing.append("collaboration_not_proven:unresolved_receipt:" + state["reason"])
    for action in goal.get("approved_actions", []):
        bindings = w.read_json(Path(root) / "data/department-registry.json").get("collaboration_bindings", {})
        if action.get("target_department") not in bindings or action.get("required_for_completion", True) is False:
            continue
        state = next((x for x in collaboration_states if x.get("action_id") == action["action_id"]), {})
        if state.get("proof_state") == "NOT_PROVEN":
            missing.append("collaboration_not_proven:" + action["action_id"] + ":" + state["reason"])
        elif state.get("proof_state") != "PROVEN" or state.get("status") != "result_received":
            missing.append("collaboration_result:" + action["action_id"])
        elif any(item.get("action_id") == action["action_id"] for item in formal_pending):
            missing.append("collaboration_formal_followthrough:" + action["action_id"])
    return missing


def record_collaboration(root, task_id, input_path):
    """An audit of actual native transport; no fake registered department ACK."""
    pin = w.file_digest(root, input_path)
    record = w.read_json(w.safe_path(root, input_path))
    with w.workflow_lock(root):
        snapshot = restore_goal(root, w.read_json(w.snapshot_path(root, task_id)))
        if not enabled(root, snapshot) or record.get("task_id") != task_id:
            raise w.WorkflowError("exact parent complete goal required")
        goal = snapshot["goal_delivery"]
        action = [x for x in goal.get("approved_actions", []) if x.get("action_id") == record.get("action_id")]
        if len(action) != 1 or record.get("scope") != action[0].get("scope"):
            raise w.WorkflowError("one frozen approved parent collaboration action required")
        binding = w.read_json(Path(root) / "data/department-registry.json").get("collaboration_bindings", {}).get(action[0].get("target_department"), {})
        if (record.get("tool") != "mcp__codex_app__send_message_to_thread" or not record.get("native_receipt_ref")
                or record.get("status") not in {"sent", "result_received"}
                or record.get("target_thread_id") != binding.get("thread_id")
                or record.get("payload_sha256") != action[0].get("payload_sha256")
                or not record.get("message_ref")):
            raise w.WorkflowError("actual exact native collaboration receipt required")
        decisions = [row for row in w.read_jsonl(Path(root) / w.POLICY_DECISIONS)
                     if row.get("decision_id") == record.get("policy_decision_id")]
        if (len(decisions) != 1 or decisions[0].get("status") != "allow"
                or any(decisions[0].get(k) != action[0].get(k) for k in ("task_id", "action_id", "scope", "payload_sha256", "target_thread_id"))):
            raise w.WorkflowError("actual exact permitted collaboration policy receipt required")
        _validate_collaboration_native(root, action[0], record)
        if record["status"] == "result_received":
            prior_state = next((x for x in _collaboration_wait_states(root, snapshot)
                                if x.get("action_id") == record["action_id"]), {})
            if (prior_state.get("proof_state") != "PROVEN"
                    or prior_state.get("policy_decision_id") != record["policy_decision_id"]):
                raise w.WorkflowError("original proven actual collaboration send required before returned result")
        prior = goal.get("collaboration_records", [])
        if pin in prior:
            return {"result": "duplicate_ignored", "parent_closed": False}
        state = next((x for x in _collaboration_wait_states(root, snapshot)
                      if x.get("action_id") == record["action_id"]), {})
        if state and (record["status"] == "sent" or state.get("status") != "sent"):
            raise w.WorkflowError("original proven collaboration action cannot be replayed or replaced")
        snapshot["goal_delivery"] = {**goal, "collaboration_records": prior + [pin]}
        w.append_workflow_event(root, task_id, snapshot["current_state"], {"goal_delivery": snapshot["goal_delivery"], "collaboration_receipt": pin})
        w.atomic_write_json(w.snapshot_path(root, task_id), snapshot)
    return {"result": "recorded", "parent_closed": False, "does_not_grant_permission": True}


def initialize_goal(root, task_id, input_path):
    import flashcast_ops
    goal = validate_goal(root, w.read_json(w.safe_path(root, input_path)))
    args = argparse.Namespace(request=goal["objective"], task_id=task_id, goal_input=input_path)
    plan, _ = flashcast_ops.dispatch_plan(Path(root), args)
    return plan


def transfer(root, input_path):
    from result_coordination import CoordinationStore
    request = w.read_json(w.safe_path(root, input_path))
    store = CoordinationStore(root)
    try:
        return store.transfer(request, request["role"], request["owner"], request["claim"],
                              request["target_role"], request["target_owner"], request["request_id"],
                              request.get("ttl_seconds", 900), request.get("review_plan_path", ""))
    finally:
        store.close()


def recover_transfer(root, input_path):
    from result_coordination import CoordinationStore, coordination_lock, exact_identity
    identity = exact_identity(w.read_json(w.safe_path(root, input_path)))
    with coordination_lock(root):
        store = CoordinationStore(root)
        try:
            store._begin()
            rows = [json.loads(x["payload_json"]) for x in store.conn.execute("SELECT payload_json FROM coordination_audit ORDER BY seq")]
            changes = [row["details"].get("assignment_change") for row in rows
                       if row.get("identity") == identity and row.get("event") == "transfer"]
            store.conn.commit()
        finally:
            store.close()
        if not changes or not changes[-1]:
            raise w.WorkflowError("existing committed transfer audit required for recovery")
        return record_assignment_transfer(root, identity, changes[-1])


def _collaboration_native(root, pin):
    """Read original pinned normalized or raw MCP sends without rewriting them."""
    # Inspect the original envelope before any generic content decoder can
    # discard its flags, wrappers or competing representations.
    if not isinstance(pin, dict) or w.file_digest(root, pin.get("path", "")) != pin:
        raise w.WorkflowError("frozen delegation evidence changed")
    def unique_fields(pairs):
        result = {}
        for key, item in pairs:
            if key in result:
                raise ValueError("duplicate native response field")
            result[key] = item
        return result

    def check_evidence_flags(document):
        # These are native evidence containers, not message bodies or chat
        # metadata. Missing flags retain the existing normalized export path.
        documents = [document]
        if isinstance(document.get("structuredContent"), dict):
            documents.append(document["structuredContent"])
        for candidate in documents[:]:
            if isinstance(candidate.get("wait"), dict):
                documents.append(candidate["wait"])
        for evidence in documents:
            if "isError" in evidence and evidence["isError"] is not False:
                raise w.WorkflowError("successful actual native evidence required")
            polls = evidence.get("polls")
            if isinstance(polls, list):
                for poll in polls:
                    if isinstance(poll, dict) and "isError" in poll and poll["isError"] is not False:
                        raise w.WorkflowError("successful actual native poll evidence required")

    try:
        original = json.loads(w.safe_path(root, pin["path"]).read_bytes(), object_pairs_hook=unique_fields)
    except (ValueError, TypeError):
        raise w.WorkflowError("unambiguous original collaboration document required")
    if not isinstance(original, dict):
        raise w.WorkflowError("actual collaboration document required")
    check_evidence_flags(original)
    wrapper_names = ("native_send", "actual_send", "actual_native_send")
    wrappers = [key for key in wrapper_names if key in original]
    if len(wrappers) > 1:
        raise w.WorkflowError("one original collaboration send wrapper required")

    def decode_mcp(envelope):
        if not isinstance(envelope, dict) or envelope.get("isError") is not False:
            raise w.WorkflowError("explicit successful original MCP send envelope required")
        content = envelope.get("content")
        if not isinstance(content, list) or any(not isinstance(item, dict) for item in content):
            raise w.WorkflowError("one actual collaboration transport document required")
        texts = [item.get("text") for item in content if item.get("type") == "text"]
        if len(texts) != 1 or not isinstance(texts[0], str):
            raise w.WorkflowError("one actual collaboration transport document required")
        try:
            decoded = json.loads(texts[0], object_pairs_hook=unique_fields)
        except (ValueError, TypeError):
            raise w.WorkflowError("actual collaboration transport document required")
        if not isinstance(decoded, dict) or any(key in decoded for key in wrapper_names):
            raise w.WorkflowError("one actual decoded native document required")
        check_evidence_flags(decoded)
        return decoded

    def inventory(document):
        fields = [key for key in ("threads", "pinnedThreads") if key in document]
        if any(not isinstance(document[key], list) or any(not isinstance(row, dict) for row in document[key])
               for key in fields):
            raise w.WorkflowError("actual native thread inventory arrays required")
        return bool(fields)

    if wrappers:
        wrapper = wrappers[0]
        outer, envelope = original, original[wrapper]
        if ((wrapper == "actual_native_send" or "tool" in outer)
                and outer.get("tool") != "mcp__codex_app__send_message_to_thread"):
            raise w.WorkflowError("same actual native send tool required")
        if (not isinstance(envelope, dict)
                or ("isError" in outer and outer["isError"] is not False)
                or ("isError" in envelope and envelope["isError"] is not False)):
            raise w.WorkflowError("successful actual collaboration transport required")
        if wrapper == "actual_native_send" and "content" not in envelope:
            # Preserve the existing normalized response shape. A raw envelope
            # never falls back to this branch after malformed content.
            value = envelope
        else:
            value = decode_mcp(envelope)
        representations = (outer, envelope)
    elif "content" in original:
        value = decode_mcp(original)
        if inventory(value):
            if "threadId" in original or "threadId" in value:
                raise w.WorkflowError("native thread inventory cannot prove a send")
            if "tool" in original and original["tool"] != "mcp__codex_app__list_threads":
                raise w.WorkflowError("same actual native inventory tool required")
            if "structuredContent" in original and original["structuredContent"] != value:
                raise w.WorkflowError("original MCP inventory representations disagree")
            return _native_document(root, pin)
        if "threadId" not in value and (isinstance(value.get("thread"), dict)
                or isinstance(value.get("polls"), list) or isinstance(value.get("wait"), dict)):
            # Existing raw completed/wait exports retain their original strict
            # thread/turn/message/cursor readers; they do not prove a send.
            return _native_document(root, pin)
        outer, envelope, representations = original, original, (original,)
        if "tool" in original and original["tool"] != "mcp__codex_app__send_message_to_thread":
            raise w.WorkflowError("same actual native send tool required")
    else:
        if inventory(original):
            if "threadId" in original:
                raise w.WorkflowError("native thread inventory cannot prove a send")
            if (("tool" in original and original["tool"] != "mcp__codex_app__list_threads")
                    or ("isError" in original and original["isError"] is not False)):
                raise w.WorkflowError("successful actual native inventory observation required")
            return _native_document(root, pin)
        if "threadId" in original or not (isinstance(original.get("thread"), dict)
                or isinstance(original.get("polls"), list) or isinstance(original.get("wait"), dict)):
            raise w.WorkflowError("original native send envelope or completed/wait export required")
        return _native_document(root, pin)
    if (not isinstance(value, dict) or inventory(value) or inventory(outer)
            or any(key in value for key in wrapper_names)
            or not isinstance(value.get("threadId"), str) or not value["threadId"].strip()
            or ("isError" in value and value["isError"] is not False)):
        raise w.WorkflowError("actual send thread identity required")
    decoded = ({key: item for key, item in value.items() if key not in {"isError", "structuredContent"}}
               if value is envelope else value)
    for representation in representations:
        if any(key in representation and representation[key] != value["threadId"]
               for key in ("threadId", "target_thread_id")):
            raise w.WorkflowError("original send thread representations disagree")
        if "structuredContent" in representation:
            structured = representation["structuredContent"]
            if not isinstance(structured, dict) or structured != decoded:
                raise w.WorkflowError("original MCP structured and text send representations disagree")
    if wrappers and "content" in outer and decode_mcp(outer) != decoded:
        raise w.WorkflowError("original outer and wrapped MCP send representations disagree")
    return value


def _collaboration_final_message(native, tid):
    """Read completed turns in existing exports; idle alone proves nothing."""
    document = native.get("wait", native)
    if "polls" in document:
        polls = document.get("polls")
        if not isinstance(polls, list):
            raise w.WorkflowError("actual completed collaboration poll required")
        matches = [row for row in polls if isinstance(row, dict) and row.get("thread", {}).get("id") == tid]
        if len(matches) != 1:
            raise w.WorkflowError("one exact actual completed collaboration thread required")
        turn, message = matches[0].get("latestTurn", {}), matches[0].get("latestAssistantMessage", {})
        if (not turn.get("id") or turn.get("status") != "completed" or turn.get("error")
                or message.get("turnId") != turn["id"]):
            raise w.WorkflowError("completed collaboration turn and its final message required; ACK or idle is not a result")
        if "wait" in native and (native.get("thread", {}).get("id") != tid
                or native.get("turn", {}).get("id") != turn["id"]
                or native.get("turn", {}).get("status") != "completed" or native.get("turn", {}).get("error")
                or ("turnId" in native.get("message", {}) and native["message"]["turnId"] != turn["id"])
                or any(native.get("message", {}).get(k) != message.get(k) for k in ("id", "phase"))):
            raise w.WorkflowError("same frozen thread/turn/final reply and native poll required")
        if "wait" in native:
            # Native wait snapshots can summarize text. The full read-thread
            # message with the same exact ID is checked against frozen reply bytes.
            return native["message"]
        return message
    # A normalized export must itself prove thread -> completed turn -> message.
    message = native.get("message", {})
    if (native.get("thread", {}).get("id") != tid or not native.get("turn_id")
            or native.get("status") != "completed" or native.get("error")
            or not isinstance(message, dict) or message.get("turnId") != native["turn_id"]):
        raise w.WorkflowError("exact completed collaboration thread/turn/message required; ACK or idle is not a result")
    return message


class CollaborationProofError(w.WorkflowError):
    """Stable per-action proof failure; never a new permission or a role-wide veto."""
    def __init__(self, reason, detail):
        self.reason = reason
        super().__init__(detail)


def _validate_collaboration_native(root, action, record):
    # Require the pin supplied at the original recording boundary. Never derive
    # a missing historical pin by hashing whatever now occupies native_ref.
    ref, native_pin = record.get("native_receipt_ref"), record.get("actual_native_transport")
    if not isinstance(native_pin, dict):
        raise CollaborationProofError("native_transport_pin_missing", "frozen actual native transport pin required")
    # Existing native references may carry a saved receipt fragment. The file
    # component must still be exactly the original pinned file, never inferred.
    if not isinstance(ref, str) or not ref or native_pin.get("path") != ref.partition("#")[0]:
        raise CollaborationProofError("native_transport_path_mismatch", "same frozen actual native transport path required")
    try:
        native = _collaboration_native(root, native_pin)
    except (w.WorkflowError, OSError, ValueError, TypeError, AttributeError) as exc:
        raise CollaborationProofError("native_transport_changed_or_invalid", str(exc)) from exc
    if record.get("status") == "sent":
        if native.get("threadId") != action["target_thread_id"]:
            raise CollaborationProofError("native_send_identity_mismatch", "actual collaboration send thread identity required")
        return native_pin
    for name in ("result", "visible_reply"):
        evidence = record.get(name)
        if not isinstance(evidence, dict) or w.file_digest(root, evidence.get("path", "")) != evidence:
            raise CollaborationProofError("returned_evidence_changed_or_missing", "frozen actual returned collaboration evidence required")
    try:
        message = _collaboration_final_message(native, action["target_thread_id"])
    except (w.WorkflowError, TypeError, AttributeError) as exc:
        raise CollaborationProofError("native_completion_identity_mismatch", str(exc)) from exc
    if (message.get("id") != record.get("message_ref") or message.get("phase") != "final_answer"
            or not isinstance(message.get("text"), str)):
        raise CollaborationProofError("native_final_message_mismatch", "same actual final message required; ACK is not a result")
    # read_bytes preserves CRLF/LF and leading/trailing whitespace. UTF-8 encode
    # the saved provider's complete text; no strip or universal-newline reading.
    reply = w.safe_path(root, record["visible_reply"]["path"]).read_bytes()
    text = message["text"].encode("utf-8")
    if not reply or text != reply:
        raise CollaborationProofError("visible_reply_utf8_mismatch", "actual final reply UTF-8 bytes must match exactly")
    return native_pin


def _collaboration_wait_states(root, snapshot):
    """Strict proofs by action; historical gaps cannot swallow other goals."""
    goal = snapshot["goal_delivery"]
    actions = goal.get("approved_actions", [])
    states = {}
    for pin in goal.get("collaboration_records", []):
        record, action = {}, {}
        try:
            if not isinstance(pin, dict) or w.file_digest(root, pin.get("path", "")) != pin:
                raise CollaborationProofError("collaboration_receipt_changed_or_missing", "frozen collaboration receipt changed")
            record = w.read_json(w.safe_path(root, pin["path"]))
            matched = [a for a in actions if a.get("action_id") == record.get("action_id")]
            if len(matched) != 1:
                raise CollaborationProofError("approved_action_identity_mismatch", "one original approved collaboration action required")
            action = matched[0]
            identity = {k: action.get(k) for k in ("task_id", "action_id", "scope", "payload_sha256", "target_thread_id")}
            if (action.get("task_id") != snapshot["task_id"] or action.get("action_class") != "thread_message"
                    or action.get("scope") not in goal.get("authorized_scope", [])
                    or not action.get("target_department") or not action.get("target_thread_id")
                    or approved_action(root, snapshot, identity) != action
                    or any(record.get(k) != v for k, v in identity.items())
                    or record.get("tool") != "mcp__codex_app__send_message_to_thread"
                    or record.get("status") not in {"sent", "result_received"}
                    or not record.get("policy_decision_id") or not record.get("message_ref")):
                raise CollaborationProofError("collaboration_identity_mismatch", "exact recorded collaboration task/action/scope/payload/thread required")
            native_pin = _validate_collaboration_native(root, action, record)
            state = states.get(action["action_id"])
            if record["status"] == "sent":
                if state:
                    raise CollaborationProofError("collaboration_send_replayed", "original collaboration send cannot be replayed")
                states[action["action_id"]] = {"task_id": snapshot["task_id"], "action_id": action["action_id"],
                    "department": action["target_department"], "threadId": action["target_thread_id"],
                    "proof_state": "PROVEN", "status": "sent", "approved_action": action, "collaboration": pin,
                    "native_transport": native_pin, "policy_decision_id": record["policy_decision_id"]}
            else:
                if (not state or state.get("proof_state") != "PROVEN"
                        or record["policy_decision_id"] != state["policy_decision_id"]):
                    raise CollaborationProofError("original_send_not_proven", "original proven actual collaboration send required before returned result")
                if state["status"] == "result_received":
                    raise CollaborationProofError("collaboration_result_replayed", "original collaboration result cannot be replaced")
                state.update(status="result_received", result_receipt=pin, result=record["result"],
                             visible_reply=record["visible_reply"], native_result=native_pin)
        except (w.WorkflowError, OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
            # An unreadable frozen receipt is kept under its pin, without trusting
            # changed bytes for an action ID. Completion remains fail-closed.
            key = action.get("action_id") or record.get("action_id") or "unresolved:" + str(pin.get("path") if isinstance(pin, dict) else pin)
            states[key] = {"task_id": snapshot["task_id"], "action_id": action.get("action_id") or record.get("action_id"),
                "department": action.get("target_department"), "threadId": action.get("target_thread_id"),
                "responsible_assistant": goal["responsible_assistant"], "proof_state": "NOT_PROVEN",
                "status": "not_proven", "observed_status": record.get("status"),
                "reason": getattr(exc, "reason", "collaboration_proof_invalid"), "detail": str(exc),
                "original_receipt": pin, "proves_completion": False, "proves_next_action": False}
    return list(states.values())


def _collaboration_pending(root, snapshot, role, include_terminal=False):
    """Returned collaboration is ready for intake, never a synthetic outbox."""
    if (not snapshot["goal_delivery"].get("collaboration_records")
            or (not include_terminal and snapshot.get("current_state") in w.TERMINAL_STATES)):
        return []
    receipts, invalid = w._validate_receipt_chain(root, snapshot["task_id"])
    if invalid or w.validate_workflow_events(root, snapshot["task_id"]):
        raise w.WorkflowError("intact actual collaboration intake chains required")
    states = _collaboration_wait_states(root, snapshot)
    pending = []
    rows = w._result_handoff_rows(root, snapshot["task_id"])
    for state in states:
        if state.get("proof_state") != "PROVEN" or state["status"] != "result_received":
            continue
        matched = [row for row in rows if row.get("outbox") == state["result"]
                   and row.get("result_sha256") == state["result"]["sha256"]
                   and row.get("sender_department") == state["department"]
                   and row.get("coordinator_role") == role
                   and row.get("source_mode") == "collaboration"
                   and row.get("action_id") == state["action_id"]
                   and row.get("scope") == state["approved_action"]["scope"]
                   and row.get("collaboration_source") == state["result_receipt"]]
        for row in matched:
            if any(w.file_digest(root, pin.get("path", "")) != pin for pin in row.get("evidence", [])):
                raise w.WorkflowError("formal collaboration intake evidence changed")
        received = any(row.get("event") == "controller_received" for row in matched)
        decision = next((row for row in reversed(matched) if row.get("event") == "controller_decision"), None)
        follow = next((row for row in reversed(matched) if row.get("event") == "controller_followthrough"), {})
        actual = False
        expected = {"dispatch_sent": "dispatch_sent", "execution_verified": "postcheck",
                    "prior_action_verified": "outbox_received", "inflight_result_verified": "outbox_received"}
        status = follow.get("followthrough_status", "pending")
        if received and decision and status in expected:
            linked_id = w.validate_task_id(follow.get("linked_task_id", ""))
            linked, invalid = w._validate_receipt_chain(root, linked_id)
            exact = [row for row in linked if row.get("receipt_id") == follow.get("action_receipt_id")
                     and row.get("receipt_type") == expected[status]]
            actual = not invalid and len(exact) == 1
            if status == "dispatch_sent" and actual:
                try:
                    w._validate_collaboration_followthrough_receipt(root, snapshot["task_id"], decision, follow)
                except w.WorkflowError:
                    actual = False
            if status == "execution_verified":
                actual = actual and linked_id == snapshot["task_id"] and exact[0].get("verdict") == "pass"
            elif status in {"prior_action_verified", "inflight_result_verified"}:
                pin = follow.get("linked_outbox", {})
                actual = (actual and pin in exact[0].get("evidence", [])
                          and w.file_digest(root, pin.get("path", "")) == pin)
        if actual:
            continue
        pending.append({**state, "responsible_assistant": role, "received": received,
            "decided": bool(received and decision), "controller_followthrough": status,
            "next_owner": decision.get("next_owner") if decision else role,
            "next_action": decision.get("next_action") if decision else "formal_intake_original_collaboration_result",
            "next_check_at": follow.get("next_check_at"), "unblock_condition": follow.get("unblock_condition"),
            "state": "ready_for_formal_intake" if not received else
                     "received_pending_decision" if not decision else "decided_pending_actual_followthrough",
            "proves_completion": False, "proves_next_action": False})
    return pending


def collaboration_result_source(root, identity):
    """Read a declared collaboration result without inventing a department outbox.

    The original returned document supplies the candidate version; this adapter
    does not associate a new hash with an old send or turn an audit into QA PASS.
    """
    sender = identity.get("sender_department")
    if sender in w.department_registry(root):
        return None
    binding = w.read_json(Path(root) / "data/department-registry.json").get("collaboration_bindings", {}).get(sender)
    if not isinstance(binding, dict) or not binding.get("thread_id"):
        raise w.WorkflowError("declared fixed collaboration result sender required")
    snapshot = restore_goal(root, w.read_json(w.snapshot_path(root, identity.get("task_id", ""))))
    if not enabled(root, snapshot):
        raise w.WorkflowError("original active complete goal collaboration required")
    receipts, invalid = w._validate_receipt_chain(root, snapshot["task_id"])
    if invalid or w.validate_workflow_events(root, snapshot["task_id"]):
        raise w.WorkflowError("intact actual collaboration intake chains required")
    matches = [state for state in _collaboration_wait_states(root, snapshot)
               if state.get("department") == sender and state.get("threadId") == binding["thread_id"]
               and state.get("proof_state") == "PROVEN" and state.get("status") == "result_received"
               and state.get("result", {}).get("sha256") == identity.get("result_sha256")]
    if len(matches) != 1:
        raise w.WorkflowError("one exact original proven collaboration send and returned result required")
    state = matches[0]
    returned = w.read_json(w.safe_path(root, state["result_receipt"]["path"]))
    result_path = w.safe_path(root, state["result"]["path"])
    try:
        result = json.loads(result_path.read_bytes())
    except (ValueError, UnicodeError):
        result = {}
    result = result if isinstance(result, dict) else {}
    version = returned.get("candidate_version") or result.get("candidate_version")
    if (not isinstance(version, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9+._-]{0,199}", version)
            or version != identity.get("candidate_version")
            or (returned.get("candidate_version") and result.get("candidate_version")
                and returned["candidate_version"] != result["candidate_version"])):
        raise w.WorkflowError("candidate version must come from the original frozen collaboration result")
    if result.get("task_id", snapshot["task_id"]) != snapshot["task_id"] or result.get("department", sender) != sender:
        raise w.WorkflowError("original collaboration result task and sender required")
    action = state["approved_action"]
    policies = [row for row in w.read_jsonl(Path(root) / w.POLICY_DECISIONS)
                if row.get("decision_id") == state["policy_decision_id"]]
    if (len(policies) != 1 or policies[0].get("status") != "allow"
            or any(policies[0].get(k) != action.get(k) for k in
                   ("task_id", "action_id", "scope", "payload_sha256", "target_thread_id"))):
        raise w.WorkflowError("original exact collaboration policy receipt required")
    return {"task_id": snapshot["task_id"], "department": sender, "candidate_version": version,
            "scope": action["scope"], "status": "completed", "source_mode": "collaboration",
            "fixed_chat_task_id": binding["thread_id"], "result": state["result"], "state": state,
            "responsible_assistant": snapshot["goal_delivery"]["responsible_assistant"]}


def validate_collaboration_result_handoff(root, request):
    source = collaboration_result_source(root, request)
    if source is None:
        return None
    state = source["state"]
    if (request.get("event") not in {"controller_received", "controller_decision", "controller_followthrough"}
            or request.get("source_mode") != "collaboration"
            or request.get("scope") != source["scope"] or request.get("action_id") != state["action_id"]
            or request.get("coordinator_role") != source["responsible_assistant"]
            or request.get("outbox_path") != source["result"]["path"]
            or ("source_thread_id" in request and request["source_thread_id"] != source["fixed_chat_task_id"])
            or ("collaboration_source" in request and request["collaboration_source"] != state["result_receipt"])):
        raise w.WorkflowError("exact collaboration action/scope/result and assigned assistant required")
    return source


def wait_plan(root, role, cursors=None):
    registry = w.department_registry(root)
    if role != "operations" and registry.get(role, {}).get("coordination_authority", {}).get("routine_decisions") is not True:
        raise w.WorkflowError("registered coordinator required")
    if cursors is None:
        cursors = w.read_json(Path(root) / "logs/goal-delivery-waits" / f"{role}.json").get("cursors", {})
    targets, tasks, collaboration_states = {}, [], []
    for path in (Path(root) / w.WORKFLOW_DIR).glob("*.json"):
        raw = w.read_json(path)
        if raw.get("goal_delivery", {}).get("responsible_assistant") != role:
            continue
        snapshot = restore_goal(root, raw)
        if not enabled(root, snapshot) or snapshot.get("current_state") in w.TERMINAL_STATES:
            continue
        goal = snapshot["goal_delivery"]
        if goal["responsible_assistant"] != role:
            continue
        rows, invalid = w._validate_receipt_chain(root, snapshot["task_id"])
        if invalid:
            raise w.WorkflowError("wait requires intact actual receipt chain")
        results = w._result_handoff_rows(root, snapshot["task_id"])
        for dep in goal["producer_departments"]:
            sent = next((r for r in reversed(rows) if r.get("department") == dep and r.get("receipt_type") == "dispatch_sent"), None)
            if not sent or any(r.get("sender_department") == dep and r.get("event") == "notification_queued"
                               and r.get("created_at", "") >= sent["created_at"] for r in results):
                continue
            tid = sent.get("chat_task_id")
            if tid:
                item = {"threadId": tid}
                if (cursors or {}).get(tid):
                    item["afterCursor"] = cursors[tid]
                targets[tid] = item
                tasks.append({"task_id": snapshot["task_id"], "department": dep, "threadId": tid,
                              "dispatch": {k: sent[k] for k in ("receipt_id", "receipt_hash")}})
        for state in _collaboration_wait_states(root, snapshot):
            collaboration_states.append(state)
            if state.get("proof_state") != "PROVEN" or state["status"] != "sent":
                continue
            tid = state["threadId"]
            targets[tid] = {"threadId": tid, **({"afterCursor": cursors[tid]} if cursors.get(tid) else {})}
            tasks.append({**state, "wait_source": "collaboration"})
    ordered = sorted(targets.values(), key=lambda x: x["threadId"])
    return {"coordinator_role": role, "tool": "mcp__codex_app__wait_threads", "timeoutMs": 60000,
            "batches": [ordered[i:i+8] for i in range(0, len(ordered), 8)], "tasks": tasks,
            "collaboration_state": collaboration_states,
            "cursor_record_required": True, "HQ_may_end_coordination": True,
            "native_wakeup_guaranteed": False, "creates_automation": False,
            "state": "inflight_event_wait" if ordered else "temporarily_no_executable_work"}


def begin_wait(root, role, input_path):
    """Freeze one actual planned batch BEFORE calling native wait_threads."""
    request = w.read_json(w.safe_path(root, input_path))
    with w.workflow_lock(root):
        prior = w.read_json(Path(root) / "logs/goal-delivery-waits" / f"{role}.json")
        plan = wait_plan(root, role, prior.get("cursors", {}))
        targets = request.get("targets")
        timeout = request.get("timeoutMs", 60000)
        if (targets not in plan["batches"] or not targets or len(targets) > 8
                or not isinstance(timeout, int) or isinstance(timeout, bool) or not 0 <= timeout <= 60000):
            raise w.WorkflowError("one bounded actual in-flight batch required")
        tids = {x["threadId"] for x in targets}
        for existing in (Path(root) / "logs/goal-delivery-waits/batches").glob("*.json"):
            pending = w.read_json(existing)
            if (pending.get("coordinator_role") == role and pending.get("state") in {'waiting', 'retry_ready'}
                    and tids.intersection(x["threadId"] for x in pending.get("targets", []))):
                if pending.get('state') == 'retry_ready' and pending.get('targets') == targets and pending.get('timeoutMs') == timeout:
                    pending.update(state='waiting', effect_stage='prepared_not_called', resumed_at=w.utc_timestamp())
                    w.atomic_write_json(existing, pending)
                    return pending
                raise w.WorkflowError("overlapping native wait still open; recover its frozen batch before another wait")
        payload = {"batch_id": str(uuid.uuid4()), "coordinator_role": role,
                   "tool": plan["tool"], "timeoutMs": timeout, "targets": targets,
                   "tasks": [x for x in plan["tasks"] if x["threadId"] in tids],
                   "started_at": w.utc_timestamp(), "state": "waiting", "effect_stage": "prepared_not_called", "proves_next_action": False}
        path = Path(root) / "logs/goal-delivery-waits/batches" / (payload["batch_id"] + ".json")
        w.atomic_write_json(path, payload)
        return payload




def wait_call_started(root, role, input_path):
    request = w.read_json(w.safe_path(root, input_path))
    batch_id = str(uuid.UUID(request.get('batch_id', '')))
    with w.workflow_lock(root):
        path = Path(root) / 'logs/goal-delivery-waits/batches' / (batch_id + '.json')
        batch = w.read_json(path)
        if batch.get('coordinator_role') != role or batch.get('state') != 'waiting':
            raise w.WorkflowError('same assistant open original wait batch required')
        if batch.get('effect_stage') == 'called_no_response':
            raise w.WorkflowError('call already started; read back exact native effect before retry')
        if batch.get('effect_stage', 'legacy_call_state_unknown') != 'prepared_not_called':
            raise w.WorkflowError('legacy wait effect unknown; explicit native readback required')
        batch.update(effect_stage='called_no_response', call_started_at=w.utc_timestamp())
        w.atomic_write_json(path, batch)
        return batch


def recover_wait(root, role, input_path):
    """Three interruption points; recovery never creates a business dispatch."""
    request = w.read_json(w.safe_path(root, input_path))
    batch_id = str(uuid.UUID(request.get('batch_id', '')))
    path = Path(root) / 'logs/goal-delivery-waits/batches' / (batch_id + '.json')
    batch = w.read_json(path)
    if batch.get('coordinator_role') != role or not isinstance(request.get('reason'), str) or not request['reason'].strip():
        raise w.WorkflowError('original assistant batch and actual interruption reason required')
    if request.get('native_result_input'):
        record = w.read_json(w.safe_path(root, request['native_result_input']))
        if record.get('batch_id') != batch_id or not isinstance(record.get('actual_native_wait'), dict):
            raise w.WorkflowError('returned result must be committed to original batch')
        result = record_wait(root, role, request['native_result_input'])
        return {'result': 'returned_result_committed', 'batch_id': batch_id, 'wait_result': result,
                'business_redispatch': False}
    if batch.get('state') == 'completed':
        with w.workflow_lock(root):
            _merge_wait_completion(root, role, batch)
        return {'result': 'completion_cache_repaired', 'batch_id': batch_id, 'business_redispatch': False}
    stage = batch.get('effect_stage', 'legacy_call_state_unknown')
    if stage != 'prepared_not_called':
        pin = request.get('actual_effect_readback')
        if not isinstance(pin, dict) or w.file_digest(root, pin.get('path', '')) != pin:
            raise w.WorkflowError('original fresh native effect readback pin required before interrupted wait recovery')
        observed = w._parse_observed_at(request.get('observed_at'))
        native = _collaboration_native(root, pin)
        allowed = {target['threadId'] for target in batch['targets']}
        polls = native.get('polls', [])
        valid_polls = (isinstance(polls, list) and polls
                       and all(isinstance(row, dict) and isinstance(row.get('thread'), dict) for row in polls))
        if (request.get('tool') != 'mcp__codex_app__wait_threads'
                or observed is None or not 0 <= (dt.datetime.now(dt.timezone.utc)-observed).total_seconds() <= 300
                or not valid_polls or not isinstance(native.get('timedOut'), bool)
                or {row['thread'].get('id') for row in polls} != allowed
                or len(polls) != len(allowed)
                or any(row.get('status') in {'completed', 'needsAttention'} for row in polls)
                or any(row.get('latestTurn', {}).get('status') == 'completed' for row in polls)
                or request.get('effect_observation') != 'not_observed'):
            raise w.WorkflowError('actual bounded original target readback and explicit not_observed required')
    with w.workflow_lock(root):
        current = w.read_json(path)
        if current != batch or current.get('state') != 'waiting':
            raise w.WorkflowError('wait changed during effect recovery; reread original batch')
        recovery = {'point': stage, 'reason': request['reason'],
                    'input': w.file_digest(root, input_path), 'at': w.utc_timestamp(),
                    'effect_observation': 'not_called' if stage == 'prepared_not_called' else 'not_observed',
                    'unknown_effect_is_completion': False}
        current.update(state='retry_ready', effect_stage='prepared_not_called',
                       recoveries=current.get('recoveries', []) + [recovery])
        w.atomic_write_json(path, current)
    return {'result': 'resume_original_wait', 'batch_id': batch_id, 'targets': batch['targets'],
            'timeoutMs': batch['timeoutMs'], 'task_associations': batch['tasks'],
            'business_redispatch': False, 'native_completion_proven': False}


def _merge_wait_completion(root, role, batch):
    """Repair the cursor cache from a durable completion, preserving newer keys."""
    path = Path(root) / "logs/goal-delivery-waits" / f"{role}.json"
    prior = w.read_json(path)
    result = batch["result"]
    cursors = dict(prior.get("cursors", {}))
    times = dict(prior.get("cursor_observed_at", {}))
    for tid, cursor in batch["completion_cursors"].items():
        observed = w._parse_observed_at(times.get(tid))
        if observed is None or observed <= w._parse_observed_at(result["observed_at"]):
            cursors[tid], times[tid] = cursor, result["observed_at"]
    old_time = w._parse_observed_at(prior.get("observed_at"))
    metadata = prior if old_time and old_time > w._parse_observed_at(result["observed_at"]) else result
    w.atomic_write_json(path, {**metadata, "cursors": cursors, "cursor_observed_at": times})


def _actual_wait_cursors(root, record, allowed, frozen=None, with_errors=False):
    """Use the original native pin and retain only actually returned cursors."""
    native_pin = record.get("actual_native_wait")
    if not isinstance(native_pin, dict) or native_pin.get("path") != record["native_receipt_ref"] or (frozen is not None and native_pin != frozen):
        raise w.WorkflowError("same frozen actual native wait receipt required")
    native = _collaboration_native(root, native_pin)
    polls = native.get("polls")
    if not isinstance(polls, list) or not isinstance(native.get("timedOut"), bool):
        raise w.WorkflowError("actual native wait polls required")
    cursors = {}
    for poll in polls:
        if not isinstance(poll, dict):
            raise w.WorkflowError("actual native wait poll identity required")
        thread = poll.get("thread")
        tid = thread.get("id") if isinstance(thread, dict) else None
        cursor = poll.get("cursor")
        if tid not in allowed or tid in cursors or not isinstance(cursor, str) or not cursor:
            raise w.WorkflowError("native wait poll must belong to one frozen target")
        cursors[tid] = cursor
    errors = native.get("errors", [])
    if not isinstance(errors, list):
        raise w.WorkflowError("explicit original per-target native wait errors required")
    failed = {}
    for error in errors:
        if not isinstance(error, dict):
            raise w.WorkflowError("exact native wait error target required")
        thread = error.get("thread", {})
        tid = error.get("threadId") or (thread.get("id") if isinstance(thread, dict) else None)
        detail = error.get("error")
        if (tid not in allowed or tid in failed or tid in cursors
                or (error.get("threadId") and isinstance(thread, dict) and thread.get("id")
                    and thread["id"] != error["threadId"])
                or not isinstance(detail, (str, dict)) or not detail):
            raise w.WorkflowError("one explicit actual error for each failed frozen target required")
        failed[tid] = error
    if set(cursors) | set(failed) != allowed:
        # wait_threads returns when the first target completes. Missing polls
        # remain unknown; only the original matching completion permits this
        # partial response. A timeout still requires the full frozen batch.
        wake = native.get("wake")
        if (native["timedOut"] is not False or not isinstance(wake, dict)
                or wake.get("reason") != "turnCompleted"
                or not isinstance(wake.get("threadId"), str) or wake["threadId"] not in cursors
                or not isinstance(wake.get("turnId"), str) or not wake["turnId"].strip()):
            raise w.WorkflowError("partial native wait requires the original returned target completion")
        completed_poll = next(poll for poll in polls if poll["thread"]["id"] == wake["threadId"])
        turn = completed_poll.get("latestTurn")
        if (not isinstance(turn, dict) or turn.get("id") != wake["turnId"]
                or turn.get("status") != "completed" or turn.get("error") is not None
                or ("hostId" in wake and (not isinstance(wake["hostId"], str) or not wake["hostId"].strip()
                    or wake["hostId"] != completed_poll["thread"].get("hostId")))):
            raise w.WorkflowError("partial native wait wake must match the actual completed poll turn")
    if record.get("cursors") != cursors:
        raise w.WorkflowError("wait cursors must match actual native polls exactly")
    return (native_pin, failed) if with_errors else native_pin


def record_wait(root, role, input_path):
    pin = w.file_digest(root, input_path)
    record = w.read_json(w.safe_path(root, input_path))
    if record.get("tool") != "mcp__codex_app__wait_threads" or not record.get("native_receipt_ref"):
        raise w.WorkflowError("actual native wait receipt reference required; not a simulated queue")
    if not isinstance(record.get("timeoutMs"), int) or isinstance(record["timeoutMs"], bool) or not 0 <= record["timeoutMs"] <= 60000:
        raise w.WorkflowError("bounded actual native wait required")
    try:
        batch_id = str(uuid.UUID(record.get("batch_id", "")))
    except (ValueError, TypeError, AttributeError):
        raise w.WorkflowError("frozen actual in-flight batch required before native wait")
    with w.workflow_lock(root):
        batch_path = Path(root) / "logs/goal-delivery-waits/batches" / (batch_id + ".json")
        batch = w.read_json(batch_path)
        if (batch.get("coordinator_role") != role or batch.get("tool") != record["tool"]
                or batch.get("timeoutMs") != record["timeoutMs"] or batch.get("batch_id") != batch_id):
            raise w.WorkflowError("same assistant frozen actual in-flight batch required")
        allowed = {x["threadId"] for x in batch["targets"]}
        if (not allowed or len(allowed) != len(batch["targets"]) or len(allowed) > 8
                or allowed != {task["threadId"] for task in batch["tasks"]}):
            raise w.WorkflowError("frozen wait targets require all original task associations")
        cursors = record.get("cursors")
        if not isinstance(cursors, dict) or any(t not in allowed or not isinstance(c, str) or not c for t, c in cursors.items()):
            raise w.WorkflowError("wait cursor must belong to this assistant actual in-flight batch")
        for task in batch["tasks"]:
            rows, invalid = w._validate_receipt_chain(root, task["task_id"])
            if invalid or w.validate_workflow_events(root, task["task_id"]):
                raise w.WorkflowError("original frozen wait receipt and event chains required")
            if task.get("wait_source") == "collaboration":
                snapshot = restore_goal(root, w.read_json(w.snapshot_path(root, task["task_id"])))
                states = _collaboration_wait_states(root, snapshot)
                if (not enabled(root, snapshot) or snapshot["goal_delivery"]["responsible_assistant"] != role
                        or not any(state.get("proof_state") == "PROVEN" and all(state.get(k) == task.get(k) for k in (
                            "task_id", "action_id", "department", "threadId", "approved_action",
                            "collaboration", "native_transport", "policy_decision_id")) for state in states)):
                    raise w.WorkflowError("original frozen collaboration wait identity and assigned assistant required")
                continue
            if not any(
                    r.get("receipt_type") == "dispatch_sent" and r.get("department") == task["department"]
                    and r.get("chat_task_id") == task["threadId"]
                    and all(r.get(k) == v for k, v in task["dispatch"].items()) for r in rows):
                raise w.WorkflowError("original frozen wait dispatch identity required")
        if batch.get("state") == "completed":
            if batch.get("native_receipt") != pin:
                raise w.WorkflowError("completed wait batch cannot consume conflicting native result")
            # A consumed legacy completion remains historical. Same original
            # input repairs only its cache; it never receives a new native pin.
            frozen = batch.get("result", {}).get("actual_native_wait")
            if frozen is not None:
                _actual_wait_cursors(root, record, allowed, frozen)
            _merge_wait_completion(root, role, batch)
            return batch["result"]
        if batch.get("state") != "waiting":
            raise w.WorkflowError("open frozen wait batch required")
        native_wait, native_errors = _actual_wait_cursors(root, record, allowed, with_errors=True)
        path = Path(root) / "logs/goal-delivery-waits" / f"{role}.json"
        prior = w.read_json(path)
        payload = {"coordinator_role": role, "cursors": {**prior.get("cursors", {}), **cursors},
                   "batch_id": batch_id, "native_receipt": pin,
                   "native_receipt_ref": record["native_receipt_ref"], "observed_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                   "proves_next_action": False, "native_wakeup_guaranteed": False}
        if native_wait is not None:
            payload["actual_native_wait"] = native_wait
        if native_errors:
            payload.update(native_errors=native_errors, state="native_wait_partial_failure",
                           failed_targets=sorted(native_errors), recovery_owner=role,
                           recovery_action="review_actual_native_error_then_resume_original_targets",
                           native_completion_proven=False)
        # Persist the exact native completion first. A same-pin replay repairs
        # a missing cursor cache; a conflicting completion stays rejected.
        batch.update(state="completed", effect_stage="returned_committed", native_receipt=pin, result=payload, completion_cursors=cursors)
        w.atomic_write_json(batch_path, batch)
        _merge_wait_completion(root, role, batch)
        return payload


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", default=str(Path(__file__).resolve().parents[1]))
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init"); init.add_argument("--task-id", required=True); init.add_argument("--input", required=True)
    change = sub.add_parser("transfer"); change.add_argument("--input", required=True)
    recover = sub.add_parser("transfer-recover"); recover.add_argument("--input", required=True)
    inbox = sub.add_parser("pending"); inbox.add_argument("--role", required=True)
    for name in ("preflight-record", "collaboration-record", "dependency-record", "approved-action-record"):
        command = sub.add_parser(name); command.add_argument("--task-id", required=True); command.add_argument("--input", required=True)
    bind = sub.add_parser("bind"); bind.add_argument("--task-id", required=True); bind.add_argument("--input", required=True)
    show = sub.add_parser("status"); show.add_argument("--task-id", required=True)
    wait = sub.add_parser("wait-plan"); wait.add_argument("--role", required=True)
    begin = sub.add_parser("wait-begin"); begin.add_argument("--role", required=True); begin.add_argument("--input", required=True)
    inherit = sub.add_parser("delegation-bind"); inherit.add_argument("--task-id", required=True); inherit.add_argument("--role", required=True); inherit.add_argument("--input", required=True)
    save = sub.add_parser("wait-record"); save.add_argument("--role", required=True); save.add_argument("--input", required=True)
    for name in ('wait-call-start', 'wait-recover'):
        command = sub.add_parser(name); command.add_argument('--role', required=True); command.add_argument('--input', required=True)
    args = parser.parse_args(); root = Path(args.project_root).resolve()
    try:
        if args.command == "init": result = initialize_goal(root, args.task_id, args.input)
        elif args.command == "transfer": result = transfer(root, args.input)
        elif args.command == "transfer-recover": result = recover_transfer(root, args.input)
        elif args.command == "pending": result = pending(root, args.role)
        elif args.command == "preflight-record": result = record_preflight(root, args.task_id, args.input)
        elif args.command == "collaboration-record": result = record_collaboration(root, args.task_id, args.input)
        elif args.command == "dependency-record": result = record_dependency(root, args.task_id, args.input)
        elif args.command == "approved-action-record": result = record_approved_action(root, args.task_id, args.input)
        elif args.command == "bind": result = bind_goal(root, args.task_id, w.read_json(w.safe_path(root, args.input)))
        elif args.command == "status": result = status(root, args.task_id)
        elif args.command == "delegation-bind": result = bind_review_delegation(root, args.task_id, args.input, args.role)
        elif args.command == "wait-begin": result = begin_wait(root, args.role, args.input)
        elif args.command == "wait-record": result = record_wait(root, args.role, args.input)
        elif args.command == 'wait-call-start': result = wait_call_started(root, args.role, args.input)
        elif args.command == 'wait-recover': result = recover_wait(root, args.role, args.input)
        else:
            cursor_file = root / "logs/goal-delivery-waits" / f"{args.role}.json"
            result = wait_plan(root, args.role, w.read_json(cursor_file).get("cursors", {}))
        print(json.dumps(result, ensure_ascii=False, indent=2)); return 0
    except (w.WorkflowError, ValueError, KeyError, OSError) as error:
        print(json.dumps({"status": "blocked", "reason": str(error), "external_permission_issued": False})); return 1


if __name__ == "__main__":
    raise SystemExit(main())
