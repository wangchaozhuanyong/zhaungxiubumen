"""Exact assistant continuation grants; never final release authorization."""
from __future__ import annotations

import datetime as dt
from pathlib import Path
import human_control
import re

ASSISTANTS = {"operations-assistant", "operations-assistant-2", "operations-assistant-3"}
DECISIONS = {"send_qa", "rework", "continue", "wait_external", "close_scope", "release_gate"}
FOLLOWTHROUGH = {"dispatch_sent", "blocked_with_owner", "external_wait_registered",
                 "prior_action_verified", "inflight_result_verified", "dependency_resolved"}


def _w():
    import workflow_control
    return workflow_control


def validate_adoption(root):
    """Shared exact control adoption gate; this does not issue any grant."""
    w = _w()
    state = human_control.guard(root)
    if not state.get("configured"):
        raise w.WorkflowError("persistent human control required for assistant grants")
    policy = w.load_policy(root)
    cfg = policy.get("department_system_upgrade", {})
    if not isinstance(cfg, dict):
        raise w.WorkflowError("routine admission configuration object required")
    # Installation and enabling are separate; no developer self-admission.
    adoption_pin = cfg.get("adoption")
    if (cfg.get("admitted") is not True or not isinstance(adoption_pin, dict)
            or w.file_digest(root, adoption_pin.get("path", "")) != adoption_pin):
        raise w.WorkflowError("independent QA adoption required before routine grants")
    adoption = w.read_json(w.safe_path(root, adoption_pin["path"]))
    qa_pin = adoption.get("qa_outbox")
    if (adoption.get("status") != "adopted_after_independent_qa"
            or adoption.get("qa_department") not in {"qa", "qa-technical"}
            or not isinstance(qa_pin, dict) or w.file_digest(root, qa_pin.get("path", "")) != qa_pin):
        raise w.WorkflowError("exact independent QA evidence required")
    box = w.read_json(w.safe_path(root, qa_pin["path"]))
    if (box.get("department") != adoption["qa_department"] or box.get("risk_level") != "R0"
            or box.get("production_release_eligible") is not False
            or box.get("qa_result") not in {"PASS_INTERNAL_APPLICATION_ALLOWED", "PASS_FOR_OWNER_REVIEW"}
            or not re.fullmatch(r"[a-f0-9]{64}", str(adoption.get("candidate_sha256", "")))
            or box.get("candidate_sha256") != adoption.get("candidate_sha256")
            or box.get("candidate_path") != adoption.get("candidate_path")
            or w.file_digest(root, str(adoption.get("candidate_path", "")))["sha256"] != adoption.get("candidate_sha256")):
        raise w.WorkflowError("independent control QA candidate mismatch")
    w.validate_outbox(root, [qa_pin], adoption["qa_department"], str(box.get("task_id", "")))
    chain, invalid = w._validate_receipt_chain(root, str(box.get("task_id", "")))
    matches = [r for r in chain if r.get("receipt_id") == adoption.get("qa_receipt_id")
               and r.get("receipt_type") == "qa_verdict" and r.get("department") == adoption["qa_department"]
               and r.get("verdict") == "pass" and qa_pin in r.get("evidence", [])
               and r.get("chat_task_id") == w.department_registry(root).get(adoption["qa_department"], {}).get("chat_binding", {}).get("task_id")]
    if invalid or len(matches) != 1:
        raise w.WorkflowError("independent native QA receipt required")
    # Role files, a flipped admission flag and even QA alone do not establish
    # application. Bind the adopting HQ decision to that exact QA result.
    candidate_pin = w.file_digest(root, adoption["candidate_path"])
    decisions = [r for r in w._result_handoff_rows(root, str(box.get("task_id", "")))
                 if r.get("record_id") == adoption.get("controller_decision_record_id")]
    controller = w.department_registry(root).get("operations", {}).get("chat_binding", {})
    if (len(decisions) != 1 or decisions[0].get("event") != "controller_decision"
            or decisions[0].get("actor_role") != "operations"
            or decisions[0].get("actor_thread_id") != controller.get("task_id")
            or decisions[0].get("decision") != "close_scope"
            or decisions[0].get("qa_status") != "pass"
            or decisions[0].get("sender_department") != adoption["qa_department"]
            or decisions[0].get("candidate_version") != box.get("candidate_version")
            or decisions[0].get("outbox") != qa_pin
            or decisions[0].get("result_sha256") != qa_pin["sha256"]
            or decisions[0].get("acceptance_scope") != matches[0].get("scope")
            or not matches[0].get("scope")
            or candidate_pin not in decisions[0].get("evidence", [])
            or qa_pin not in decisions[0].get("evidence", [])):
        raise w.WorkflowError("exact headquarters native adoption decision required")
    return adoption


def validate(root, pin, role, *, now=None):
    w = _w(); now = now or dt.datetime.now(dt.timezone.utc)
    if not isinstance(now, dt.datetime) or now.tzinfo is None:
        raise w.WorkflowError("timezone-aware routine grant clock required")
    validate_adoption(root)
    state = human_control.guard(root)
    policy = w.load_policy(root)
    if not isinstance(pin, dict) or w.file_digest(root, pin.get("path", "")) != pin:
        raise w.WorkflowError("frozen exact routine grant required")
    grant = w.read_json(w.safe_path(root, pin["path"]))
    human_control.guard(root, grant.get("task_id"))
    binding = w.department_registry(root).get(role, {}).get("chat_binding", {})
    issued = w._parse_observed_at(grant.get("issued_at")); expires = w._parse_observed_at(grant.get("expires_at"))
    if (role not in ASSISTANTS or grant.get("issuer") != "operations"
            or grant.get("actor_role") != role or grant.get("actor_thread_id") != binding.get("task_id")
            or binding.get("project_id") != policy.get("routing_policy", {}).get("source_project_id")
            or binding.get("cwd") != str(Path(root).resolve())
            or not w._chat_binding_healthy(binding, verification_ttl_hours=26, now=now)
            or not isinstance(grant.get("owner_authorization_ref"), str) or not grant["owner_authorization_ref"].strip()
            or grant.get("production_authority_granted") is not False
            or grant.get("risk_level") not in {"R0", "R1", "R2"}
            or type(grant.get("human_control_revision")) is not int or grant["human_control_revision"] != state["revision"]
            or issued is None or expires is None or not issued <= now < expires <= issued + dt.timedelta(hours=26)
            or grant.get("status") != "active" or grant.get("consumed") is not False):
        raise w.WorkflowError("routine grant unknown, stale, consumed or outside admitted actor scope")
    import result_coordination as c
    c.exact_identity(grant)
    _scope = grant.get("scope")
    if (not isinstance(_scope, str) or not _scope.strip()
            or any(marker in _scope for marker in "*?[]|\n\r")):
        raise w.WorkflowError("nonempty exact routine scope required")
    for field, allowed in (("allowed_events", c.FINAL_EVENTS), ("allowed_decisions", DECISIONS),
                           ("allowed_next_owners", set(w.department_registry(root)))):
        values = grant.get(field)
        if (not isinstance(values, list) or any(not isinstance(v, str) for v in values)
                or len(values) != len(set(values)) or not set(values).issubset(allowed)):
            raise w.WorkflowError("unknown or malformed bounded routine allowance")
    linked = grant.get("allowed_linked_tasks")
    if (not isinstance(linked, list) or any(not isinstance(task, str) or not task.strip() for task in linked)
            or len(linked) != len(set(linked))):
        raise w.WorkflowError("exact allowed linked task array required")
    for task in linked: w.validate_task_id(task)
    for field in ("release", "routing"):
        if field in grant and not isinstance(grant[field], dict):
            raise w.WorkflowError("bounded routine " + field + " object required")
    if "accepted_scopes" in grant:
        values = grant["accepted_scopes"]
        if (not isinstance(values, list) or any(not isinstance(v, str) or not v.strip() for v in values)
                or len(values) != len(set(values))):
            raise w.WorkflowError("exact accepted scope array required")
    return grant


def check_result(root, request):
    role = request.get("coordinator_role", "operations")
    if role == "operations": return None
    w = _w(); grant = validate(root, request.get("routine_grant"), role)
    for field in ("task_id", "sender_department", "candidate_version", "result_sha256", "scope"):
        if not grant.get(field) or request.get(field) != grant[field]:
            raise w.WorkflowError("routine grant exact task/candidate/result/scope mismatch")
    event = request.get("event")
    if event not in grant.get("allowed_events", []):
        raise w.WorkflowError("routine event outside grant")
    if event == "controller_decision":
        if request.get("decision") not in DECISIONS or request.get("decision") not in grant.get("allowed_decisions", []):
            raise w.WorkflowError("decision outside exact admitted routine grant")
        from routine_authority import check_special_decision
        check_special_decision(root, request, grant)
        if request.get("next_owner") not in grant.get("allowed_next_owners", []):
            raise w.WorkflowError("routine next owner outside grant")
    elif event == "controller_followthrough":
        if request.get("followthrough_status") not in FOLLOWTHROUGH:
            raise w.WorkflowError("assistant cannot assert final production execution")
        if request.get("linked_task_id") and request["linked_task_id"] not in grant.get("allowed_linked_tasks", []):
            raise w.WorkflowError("routine linked task outside grant")
    elif event != "controller_received":
        raise w.WorkflowError("unknown routine event")
    return grant


def check_routing(root, requested):
    """A precheck does not send. Actual send still needs native reservation/readback."""
    w = _w()
    try:
        if requested.get("action_class") != "thread_message":
            raise w.WorkflowError("routine grant only permits exact internal messages")
        policy = w.load_policy(root)
        pins = policy.get("department_system_upgrade", {}).get("routing_grants", {})
        key = requested.get("task_id", "") + ":" + requested.get("action_id", "")
        grant = validate(root, pins.get(key), requested.get("sender_department"))
        route = grant.get("routing")
        if not isinstance(route, dict) or any(requested.get(k) != route.get(k) for k in requested):
            raise w.WorkflowError("exact routine route mismatch")
        if str(requested.get("scope", "")).startswith("owner_project_handoff:"):
            if requested.get("sender_department") != "operations-assistant-2":
                raise w.WorkflowError("only exact assistant2 developer bridge")
            import developer_bridge
            return developer_bridge.precheck(root, requested, policy)
        registry = w.department_registry(root)
        target_entry = registry.get(requested.get("target_department"), {})
        target = target_entry.get("chat_binding", {})
        associated = target_entry.get("relationship") == "associated_code_department"
        expected_project = target.get("project_id") if associated else policy["routing_policy"]["source_project_id"]
        if (requested.get("source_project_id") != policy["routing_policy"]["source_project_id"]
                or requested.get("target_department") in ASSISTANTS | {"operations"}
                or not expected_project or requested.get("target_project_id") != expected_project
                or any(requested.get(k) != target.get(v) for k,v in (
                    ("target_thread_id","task_id"),("target_thread_title","title"),
                    ("target_cwd","cwd"),("target_sidebar_section_id","sidebar_section_id")))
                or not w._chat_binding_healthy(target, verification_ttl_hours=26)):
            raise w.WorkflowError("routine route cannot cross project or invent fixed target")
        live_pin = grant.get("live_identity")
        if not isinstance(live_pin, dict) or w.file_digest(root, live_pin.get("path", "")) != live_pin:
            raise w.WorkflowError("frozen fresh native inventory required")
        live = w.read_json(w.safe_path(root, live_pin["path"]))
        stamp = w._parse_observed_at(live.get("observed_at"))
        now = dt.datetime.now(dt.timezone.utc)
        from native_inventory import threads, sections, fixed_binding
        rows = threads(live)
        matches = [row for row in rows if row.get("id") == target.get("task_id")]
        actor = registry.get(requested.get("sender_department"), {}).get("chat_binding", {})
        sources = [row for row in rows if row.get("id") == actor.get("task_id")]
        native_groups = sections(live)
        target_member = ("codex:project:" + str(target.get("project_id")) if associated
                         else "codex:thread:local:" + str(target.get("task_id")))
        groups = [group for group in native_groups
                  if group["id"] == target.get("sidebar_section_id")
                  and target_member in group.get("itemKeys", [])]
        source_groups = [group for group in native_groups
                         if group["id"] == actor.get("sidebar_section_id")
                         and "codex:thread:local:" + str(actor.get("task_id")) in group.get("itemKeys", [])]
        if (stamp is None or not 0 <= (now - stamp).total_seconds() <= 300 or len(matches) != 1
                or len(sources) != 1 or len(groups) != 1 or len(source_groups) != 1
                or any(sources[0].get(k) != v for k,v in {"projectId": actor.get("project_id"),
                    "cwd": actor.get("cwd"), "title": actor.get("title")}.items())
                or any(matches[0].get(k) != v for k,v in {"projectId": target.get("project_id"),
                    "cwd": target.get("cwd"), "title": target.get("title"), "status": "idle"}.items())):
            raise w.WorkflowError("fresh exact idle target required; active targets stay queued")
        # Associated code work keeps its independently registered project/cwd.
        # The registry relationship is only identity metadata: the frozen grant
        # and fresh native project membership above remain mandatory.
        fixed_binding(root, requested["target_department"], live)
        fixed_binding(root, requested["sender_department"], live)
        sent = w.safe_path(root, str(grant.get("native_send_receipt_path") or ""))
        attempt = w.safe_path(root, str(grant.get("native_attempt_receipt_path") or ""))
        if sent == Path(root).resolve() or attempt == Path(root).resolve() or sent.exists() or attempt.exists():
            raise w.WorkflowError("routine send consumed or uncertain; readback required")
        return [], ["routine_grant:exact_actor_scope", "native_send_reservation:required"]
    except (w.WorkflowError, OSError, ValueError, KeyError, TypeError):
        return ["routine_grant_exact_route_required"], ["routine_grant:exact_actor_scope"]


def reserve_route(root, grant_pin, role, request):
    """Reserve one exact native send; this function never sends a message."""
    import result_coordination as c
    w = _w()
    with human_control.action_gate(root), c.coordination_lock(root):
        grant = validate(root, grant_pin, role)
        route = grant.get("routing")
        if not isinstance(route, dict) or request.get("routing") != route:
            raise w.WorkflowError("exact frozen routing request required")
        identity = c.exact_identity(grant)
        c._validate_queued(root, identity)
        store = c.CoordinationStore(root)
        try:
            store._lease(identity, role, request.get("coordinator_owner"), request.get("coordination_claim"))
        finally:
            store.close()
        reasons, _ = check_routing(root, route)
        if reasons:
            raise w.WorkflowError("exact routine route not admitted")
        attempt = w.safe_path(root, grant["native_attempt_receipt_path"])
        # Exclusive file creation is the durable send reservation, before API use.
        # A crash leaves an uncertain attempt, not permission to blindly resend.
        import uuid
        value = {"schema_version": 1, "status": "reserved_uncertain", "reservation_id": uuid.uuid4().hex,
                 "grant": grant_pin, "actor_role": role, "actor_thread_id": grant["actor_thread_id"],
                 "routing": route, "created_at": w.utc_timestamp(), "message_sent": False,
                 "coordinator_owner": request.get("coordinator_owner"),
                 "coordination_claim": request.get("coordination_claim"),
                 "actor_metadata_is_authentication": False}
        attempt.parent.mkdir(parents=True, exist_ok=True)
        import os, json
        with attempt.open("x", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.flush(); os.fsync(handle.fileno())
        return value


def commit_route(root, grant_pin, role, proof):
    """Commit exact trusted native readback; metadata itself is not authentication."""
    import result_coordination as c
    w = _w()
    with human_control.action_gate(root), c.coordination_lock(root):
        grant = validate(root, grant_pin, role)
        attempt = w.read_json(w.safe_path(root, grant["native_attempt_receipt_path"]))
        route = grant.get("routing", {})
        stamp = w._parse_observed_at(proof.get("observed_at")) if isinstance(proof, dict) else None
        now = dt.datetime.now(dt.timezone.utc)
        if (attempt.get("status") != "reserved_uncertain" or attempt.get("grant") != grant_pin
                or attempt.get("actor_role") != role or attempt.get("routing") != route
                or not isinstance(proof, dict) or proof.get("source") != "trusted_native_send_readback"
                or proof.get("reservation_id") != attempt.get("reservation_id")
                or proof.get("target_thread_id") != route.get("target_thread_id")
                or proof.get("payload_sha256") != route.get("payload_sha256")
                or proof.get("actor_thread_id") != grant.get("actor_thread_id")
                or proof.get("nonempty") is not True or not proof.get("message_id")
                or stamp is None or not 0 <= (now - stamp).total_seconds() <= 300):
            raise w.WorkflowError("exact trusted native send readback required; no resend")
        path = w.safe_path(root, grant["native_send_receipt_path"])
        value = {**attempt, "status": "sent_native_readback_verified", "message_sent": True,
                 "native_readback": proof, "committed_at": w.utc_timestamp()}
        if path.exists():
            old = w.read_json(path)
            if old.get("reservation_id") != value["reservation_id"] or old.get("native_readback") != proof:
                raise w.WorkflowError("committed native route differs; reconcile")
            return old
        w.atomic_write_json(path, value)
        return value


def verify_dispatch_decision(root, decision, task_id, action_id, scope, target_department, target_thread_id):
    """Actual receipt consumer binds original allow, admitted grant and native send."""
    w = _w()
    cfg = w.load_policy(root).get("department_system_upgrade", {})
    pin = cfg.get("routing_grants", {}).get(task_id + ":" + action_id)
    role = decision.get("department")
    grant = validate(root, pin, role)
    route = grant.get("routing", {})
    expected = {"task_id": task_id, "action_id": action_id, "scope": scope,
                "target_department": target_department, "target_thread_id": target_thread_id}
    if (any(route.get(k) != v or decision.get(k) != v for k,v in expected.items())
            or decision.get("payload_sha256") != route.get("payload_sha256")
            or decision.get("source_project_id") != route.get("source_project_id")):
        raise w.WorkflowError("native dispatch decision differs from bounded routine grant")
    sent = w.read_json(w.safe_path(root, grant["native_send_receipt_path"]))
    attempt = w.read_json(w.safe_path(root, grant["native_attempt_receipt_path"]))
    if (sent.get("status") != "sent_native_readback_verified" or sent.get("message_sent") is not True
            or sent.get("grant") != pin or sent.get("routing") != route
            or sent.get("actor_role") != role or sent.get("actor_thread_id") != grant.get("actor_thread_id")
            or not attempt.get("reservation_id") or sent.get("reservation_id") != attempt.get("reservation_id")):
        raise w.WorkflowError("native routine send/readback reservation required")
    return grant


def main():
    import argparse, json
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("command", choices=("validate", "reserve-route", "commit-route"))
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--input", type=Path, required=True)
    a = p.parse_args()
    request = _w().read_json(_w().safe_path(a.root, a.input))
    args = (a.root, request["grant"], request["actor_role"])
    if a.command == "validate": result = validate(*args)
    elif a.command == "reserve-route": result = reserve_route(*args, request["request"])
    else: result = commit_route(*args, request["native_readback"])
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__": main()
