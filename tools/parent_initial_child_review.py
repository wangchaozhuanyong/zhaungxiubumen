"""Read the existing first-send provenance for one independent child review.

This never sends, binds, grants a permission or turns the producer's native
dispatch/ACK into a reviewer dispatch/ACK. The parent remains incomplete until
its separate real trial and final acceptance consumers succeed.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import workflow_control as w

FIELDS = {"schema_version", "mode", "task_id", "parent_task_id", "producer_department",
          "responsible_assistant", "scope", "authority", "goal_contract", "parent_goal_contract",
          "parent_decision_record_id", "action_id", "policy_decision_id", "dispatch_receipt_id",
          "dispatch_receipt_hash", "ack_receipt_id", "ack_receipt_hash", "producer_outbox",
          "producer_outbox_receipt_id", "producer_outbox_receipt_hash", "notification_record_id",
          "controller_received_record_id"}


def _fail(message):
    raise w.WorkflowError("parent initial child review: " + message)


def _pin(root, pin):
    if not isinstance(pin, dict) or w.file_digest(root, str(pin.get("path") or "")) != pin:
        _fail("original frozen source bytes changed or missing")
    return pin


def _snapshot(root, snapshot):
    """Validate contract/events without recursing into a later goal verdict."""
    import goal_delivery_runtime as g
    snapshot = g.restore_goal(root, snapshot)
    if not g.enabled(root, snapshot):
        _fail("original complete goal required")
    _pin(root, snapshot.get("goal_contract"))
    contract = g.validate_goal(root, w.read_json(w.safe_path(root, snapshot["goal_contract"]["path"])))
    for name in (*g.REQUIRED, "human_authorization", "authorization_pin", "parent_task_id",
                 "initial_dispatch_mode", "source_mode"):
        if snapshot["goal_delivery"].get(name) != contract.get(name):
            _fail("original complete goal/human/source mode changed")
    # The ordinary state validator resolves its reviewer through load_plan,
    # which consumes this source. Check the original full byte/hash chain here
    # instead; real receipt/state consumers retain their ordinary validation.
    previous = ""
    task_events = []
    try:
        for line in (Path(root) / w.WORKFLOW_EVENTS).read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            if (not isinstance(row, dict) or row.get("previous_event_hash", "") != previous
                    or row.get("event_hash") != w.sha256_value({key: value for key, value in row.items() if key != "event_hash"})):
                _fail("original goal event byte/hash chain changed")
            previous = row["event_hash"]
            if row.get("task_id") == snapshot["task_id"]:
                task_events.append(row)
    except (OSError, ValueError, TypeError) as exc:
        _fail("strict original goal events required: " + str(exc))
    if not task_events or task_events[0].get("state") != "planned":
        _fail("original planned goal event required")
    return snapshot


def _native_effect(root, action, dispatch, metadata, proof):
    """Re-read the immutable before-call reservation and consumed native effect."""
    import goal_delivery_runtime as g
    import parent_initial_dispatch as initial
    attempt_pin = _pin(root, metadata.get("attempt"))
    native_pin = _pin(root, metadata.get("actual_native_transport"))
    if (attempt_pin["path"] != proof["attempt_path"]
            or native_pin["path"] != proof["native_send_receipt_path"]
            or any(pin not in dispatch.get("evidence", []) for pin in (attempt_pin, native_pin))):
        _fail("original reserved attempt/native transport pins required")
    attempt = w.read_json(w.safe_path(root, attempt_pin["path"]))
    base = {key: value for key, value in metadata.items() if key not in {
        "attempt", "actual_native_transport", "attempt_id", "proof_mode", "actual_message_sent", "new_permissions"}}
    arguments = {"threadId": action["target_thread_id"],
                 "prompt": w.safe_path(root, action["payload"]["path"]).read_bytes().decode("utf-8")}
    if (attempt.get("state") != "called_no_response" or attempt.get("source") != base
            or attempt.get("tool") != initial.TOOL or attempt.get("arguments") != arguments
            or attempt.get("payload") != action["payload"] or attempt.get("actual_message_sent") is not False
            or not attempt.get("attempt_id") or attempt["attempt_id"] != metadata.get("attempt_id")
            or any(attempt.get(key) != dispatch.get(key) for key in ("task_id", "action_id", "scope", "policy_decision_id"))):
        _fail("original before-call reservation and exact action changed")
    events = [row for row in w.read_jsonl(Path(root) / w.WORKFLOW_EVENTS)
              if row.get("task_id") == action["task_id"] and row.get("details", {}).get(
                  "parent_initial_dispatch_attempt") == attempt_pin
              and row.get("details", {}).get("action_id") == action["action_id"]
              and row.get("details", {}).get("policy_decision_id") == dispatch["policy_decision_id"]]
    if len(events) != 1:
        _fail("one original hash-chained before-call reservation required")
    native = json.loads(w.safe_path(root, native_pin["path"]).read_bytes(), object_pairs_hook=initial._unique_fields)
    observed, reserved = [w._parse_observed_at(value) for value in
                          (native.get("observed_at"), attempt.get("reserved_at"))]
    if (any(native.get(name) is True for name in ("fixture_only", "simulation", "simulated"))
            or native.get("attempt_id") != attempt["attempt_id"]
            or native.get("proof_mode", "send") != metadata.get("proof_mode")
            or ("isError" in native and native["isError"] is not False)
            or observed is None or reserved is None or not reserved <= observed <= dt.datetime.now(dt.timezone.utc)):
        _fail("original successful native effect and reservation timing required")
    if metadata["proof_mode"] == "send":
        if (native.get("tool") != initial.TOOL or native.get("arguments") != arguments
                or g._collaboration_native(root, native_pin).get("threadId") != action["target_thread_id"]):
            _fail("original exact native send target/tool/UTF8 payload required")
    elif metadata["proof_mode"] == "readback":
        raw = native.get("actual_native_readback", {})
        texts = [item.get("text") for item in raw.get("content", []) if item.get("type") == "text"]
        if (native.get("tool") != "mcp__codex_app__read_thread"
                or native.get("arguments") != {"threadId": action["target_thread_id"]}
                or raw.get("isError") is not False or len(texts) != 1 or not isinstance(texts[0], str)):
            _fail("original successful native readback required")
        document = json.loads(texts[0], object_pairs_hook=initial._unique_fields)
        matches = []
        for turn in document.get("turns", []):
            started = turn.get("startedAt")
            started = (dt.datetime.fromtimestamp(started, dt.timezone.utc) if type(started) in {int, float}
                       else w._parse_observed_at(started))
            if started is None or not reserved <= started <= observed or not turn.get("id"):
                continue
            for item in turn.get("items", []):
                body = item.get("content")
                if (item.get("type") == "userMessage" and item.get("id") and isinstance(body, list) and body
                        and all(isinstance(part, dict) and part.get("type") == "text"
                                and isinstance(part.get("text"), str) for part in body)
                        and "".join(part["text"] for part in body) == arguments["prompt"]):
                    matches.append(item)
        if (document.get("thread", {}).get("id") != action["target_thread_id"]
                or ("isError" in document and document["isError"] is not False) or len(matches) != 1):
            _fail("original positive target/user-message readback required")
    else:
        _fail("original send or positive readback effect required")


def prepare(root, snapshot, proof):
    """Consume the existing parent/child chain, with no actual reviewer send."""
    import parent_initial_dispatch as initial
    import scoped_candidate_adoption as s
    import qa_review_plan as q
    root = Path(root).resolve()
    child = _snapshot(root, snapshot)
    goal = child["goal_delivery"]
    if (not isinstance(proof, dict) or set(proof) != FIELDS or type(proof.get("schema_version")) is not int
            or proof["schema_version"] != 1 or proof.get("mode") != "parent_initial_read_only"
            or proof.get("task_id") != child["task_id"] or proof.get("parent_task_id") != s.TASK
            or goal.get("parent_task_id") != s.TASK or child["task_id"] == s.TASK
            or goal.get("initial_dispatch_mode") != "read_only" or goal.get("source_mode") != "approved_dispatch"
            or proof.get("producer_department") != s.PRODUCER or proof.get("responsible_assistant") != s.ROLE
            or proof.get("scope") != s.SCOPE or goal.get("authorized_scope") != [s.SCOPE]
            or proof.get("authority") != goal.get("authorization_pin")
            or proof.get("goal_contract") != child.get("goal_contract")
            or q._goal_reviewer(root, child) != s.ROLE):
        _fail("one original independent F4 read-only child identity required")
    parent = _snapshot(root, w.read_json(w.snapshot_path(root, s.TASK)))
    if proof.get("parent_goal_contract") != parent.get("goal_contract"):
        _fail("original parent goal pin required")
    registry = w.department_registry(root)
    planned = {row.get("department"): row for row in child.get("departments", [])}
    if any(planned.get(role, {}).get("chat_task_id") != registry[role]["chat_binding"]["task_id"]
           for role in (s.PRODUCER, s.ROLE)):
        _fail("original fixed producer/independent reviewer goal bindings required")
    rows = s._receipts(root, child["task_id"])
    def receipt(kind, name):
        selected = [row for row in rows if row.get("receipt_id") == proof.get(name + "_receipt_id")]
        if (len(selected) != 1 or selected[0].get("receipt_hash") != proof.get(name + "_receipt_hash")
                or selected[0].get("receipt_type") != kind or selected[0].get("department") != s.PRODUCER
                or (kind in {"dispatch_sent", "chat_ack"} and selected[0].get("chat_task_id") != registry[s.PRODUCER]["chat_binding"]["task_id"])
                or (selected[0].get("chat_task_id") and selected[0]["chat_task_id"] != registry[s.PRODUCER]["chat_binding"]["task_id"])):
            _fail("one original producer " + kind + " receipt required")
        return selected[0]
    dispatch, ack, outbox = receipt("dispatch_sent", "dispatch"), receipt("chat_ack", "ack"), receipt("outbox_received", "producer_outbox")
    if not rows.index(dispatch) < rows.index(ack) < rows.index(outbox) or ack.get("ack_nonempty") is not True:
        _fail("original ordered producer dispatch/ACK/result required")
    current_round = [row for row in rows if row.get("department") == s.PRODUCER
                     and row.get("receipt_type") in {"dispatch_sent", "dispatch_failed"}]
    if current_round != [dispatch]:
        _fail("exact original first producer round required")
    checked, invalid = w._validate_receipt_chain(root, child["task_id"], through_receipt_id=outbox["receipt_id"])
    if invalid or any(row not in checked for row in (dispatch, ack, outbox)):
        _fail("original producer receipt prefix changed")
    actions = [row for row in goal.get("approved_actions", []) if row.get("action_id") == proof.get("action_id")]
    if len(actions) != 1:
        _fail("one original approved first-send action required")
    action = actions[0]
    source = action.get("parent_initial_dispatch")
    context = initial._context(root, parent, source, "sent")
    if (action.get("decision_record_id") != proof.get("parent_decision_record_id")
            or any(action.get(key) != context["action"].get(key) for key in initial.ACTION_FIELDS)
            or source["child_contract"] != child["goal_contract"]):
        _fail("original parent/child decision/action contract differs")
    decision = initial._fenced_decision(root, parent, action, "sent")
    metadata = dispatch.get("parent_initial_dispatch", {})
    expected = {"parent_task_id": s.TASK, "decision_record_id": decision["record_id"],
        "coordinator_role": s.ROLE, "coordinator_owner": decision["coordinator_owner"],
        "coordination_fence": decision["coordination_fence"], "child_contract": child["goal_contract"],
        "parent_contract": parent["goal_contract"], "human_authorization": goal["authorization_pin"],
        "adoption": context["adopted"], "external_permission_issued": False,
        "actual_message_sent": True, "new_permissions": 0}
    if (any(metadata.get(key) != value for key, value in expected.items())
            or proof.get("policy_decision_id") != dispatch.get("policy_decision_id")
            or dispatch.get("action_id") != action["action_id"] or dispatch.get("action_class") != "thread_message"
            or dispatch.get("scope") != action["scope"]):
        _fail("original consumed parent first-send provenance changed")
    initial._policy(root, action, proof["policy_decision_id"])
    _native_effect(root, action, dispatch, metadata, source)
    pin = _pin(root, proof.get("producer_outbox"))
    if pin not in outbox.get("evidence", []):
        _fail("original current producer result pin required")
    result = w.read_json(w.safe_path(root, pin["path"]))
    w.validate_outbox(root, [pin], s.PRODUCER, child["task_id"])
    if (any(result.get(name) is True for name in ("fixture_only", "simulation", "simulated"))
            or result.get("parent_task_id") != s.TASK or result.get("status") != "completed"
            or result.get("fixed_chat_task_id") != registry[s.PRODUCER]["chat_binding"]["task_id"]
            or any(result.get(name, False) is not False for name in (
                "production_write_allowed", "production_release_eligible", "external_permission_issued"))):
        _fail("actual completed read-only child result and no new permission required")
    identity = {"task_id": child["task_id"], "sender_department": s.PRODUCER,
                "candidate_version": result["candidate_version"], "result_sha256": pin["sha256"], "outbox": pin}
    handoffs = w._result_handoff_rows(root, child["task_id"])
    def handoff(event, name):
        selected = [row for row in handoffs if row.get("event") == event
                    and all(row.get(key) == value for key, value in identity.items())]
        if len(selected) != 1 or selected[0].get("record_id") != proof.get(name + "_record_id"):
            _fail("unique original completed result " + event + " required")
        return selected[0]
    queued = handoff("notification_queued", "notification")
    intake = handoff("controller_received", "controller_received")
    if (intake.get("coordinator_role") != s.ROLE or intake.get("responsible_assistant") != s.ROLE
            or handoffs.index(intake) <= handoffs.index(queued)):
        _fail("one actual original independent A2 queued-result intake required")
    s._committed(root, intake)
    fixed = w.department_registry(root)[s.PRODUCER]["chat_binding"]["task_id"]
    w._validate_goal_completed_result(root, queued, fixed, through_receipt_id=outbox["receipt_id"])
    stamps = [w._parse_observed_at(row.get("created_at")) for row in (decision, dispatch, ack, outbox, queued, intake)]
    if any(value is None for value in stamps) or stamps != sorted(stamps) or stamps[-1] > dt.datetime.now(dt.timezone.utc):
        _fail("actual parent decision/send/ACK/result/queue/intake order required")
    return {"source_kind": "parent_initial_child_review", "source_task_id": s.TASK, "proof": proof,
            "producer_dispatch": dispatch, "producer_ack": ack, "producer_outbox_receipt": outbox,
            "notification": queued, "controller_received": intake,
            "reviewer_source_created_at": intake["created_at"], "prepared_only": True,
            "reviewer_dispatch_fabricated": False, "reviewer_ack_fabricated": False,
            "external_permission_issued": False, "parent_goal_completed": False}


def build_proof(root, snapshot, producer_outbox_pin):
    """Select existing exact records, then validate; never manufacture facts."""
    import scoped_candidate_adoption as s
    child = _snapshot(root, snapshot)
    rows = s._receipts(root, child["task_id"])
    producers = [row for row in rows if row.get("department") == s.PRODUCER]
    def one(kind):
        selected = [row for row in producers if row.get("receipt_type") == kind
                    and (kind != "outbox_received" or producer_outbox_pin in row.get("evidence", []))]
        if len(selected) != 1:
            _fail("one existing original producer " + kind + " required for preparation")
        return selected[0]
    dispatch, ack, outbox = one("dispatch_sent"), one("chat_ack"), one("outbox_received")
    metadata = dispatch.get("parent_initial_dispatch", {})
    handoffs = w._result_handoff_rows(root, child["task_id"])
    def record(event):
        selected = [row for row in handoffs if row.get("event") == event and row.get("outbox") == producer_outbox_pin]
        if len(selected) != 1:
            _fail("one existing exact " + event + " required for preparation")
        return selected[0]
    proof = {"schema_version": 1, "mode": "parent_initial_read_only", "task_id": child["task_id"],
        "parent_task_id": metadata.get("parent_task_id"), "producer_department": s.PRODUCER,
        "responsible_assistant": s.ROLE, "scope": dispatch.get("scope"),
        "authority": metadata.get("human_authorization"), "goal_contract": metadata.get("child_contract"),
        "parent_goal_contract": metadata.get("parent_contract"),
        "parent_decision_record_id": metadata.get("decision_record_id"), "action_id": dispatch.get("action_id"),
        "policy_decision_id": dispatch.get("policy_decision_id"), "producer_outbox": producer_outbox_pin,
        "notification_record_id": record("notification_queued")["record_id"],
        "controller_received_record_id": record("controller_received")["record_id"]}
    for name, row in (("dispatch", dispatch), ("ack", ack), ("producer_outbox", outbox)):
        proof[name + "_receipt_id"], proof[name + "_receipt_hash"] = row["receipt_id"], row["receipt_hash"]
    prepare(root, child, proof)
    return proof
