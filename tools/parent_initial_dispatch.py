"""Exact parent-authorized first send; no native calls or new permissions.

The attempt is reserved before returning native arguments. An unanswered call
can only be settled by exact native send/readback evidence, never by calling
begin again. Actor metadata is provenance, not native-tool authentication.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
import sqlite3
import uuid

import workflow_control as w

TOOL = "mcp__codex_app__send_message_to_thread"
ACTION_FIELDS = ("task_id", "parent_task_id", "sender_department", "source_project_id",
                 "target_project_id", "target_department", "target_thread_id",
                 "target_thread_title", "target_cwd", "target_sidebar_section_id",
                 "payload_sha256", "action_id", "action_class", "scope", "payload")
ADOPTION_FIELDS = ("control_qa_outbox_path", "control_applied_proof", "control_qa_receipt_id")
NEXT_FIELDS = ("next_task_id", "next_action_id", "next_scope", "initial_dispatch")


def _fail(message):
    raise w.WorkflowError("parent initial dispatch: " + message)


def _pin(root, pin):
    if not isinstance(pin, dict) or w.file_digest(root, str(pin.get("path") or "")) != pin:
        _fail("frozen evidence bytes changed or missing")
    return pin


def _unique_fields(pairs):
    result = {}
    for name, value in pairs:
        if name in result:
            _fail("duplicate native proof fields cannot establish an effect")
        result[name] = value
    return result


def _snapshot(root, task_id):
    import goal_delivery_runtime as g
    snapshot = g.restore_goal(root, w.read_json(w.snapshot_path(root, w.validate_task_id(task_id))))
    if not g.enabled(root, snapshot):
        _fail("complete original goal required")
    _pin(root, snapshot.get("goal_contract"))
    contract = g.validate_goal(root, w.read_json(w.safe_path(root, snapshot["goal_contract"]["path"])))
    goal = snapshot["goal_delivery"]
    for key in (*g.REQUIRED, "human_authorization", "authorization_pin", "parent_task_id", "initial_dispatch_mode", "source_mode"):
        if goal.get(key) != contract.get(key):
            _fail("original complete goal contract differs")
    if w.validate_workflow_events(root, task_id):
        _fail("original workflow event chain is invalid")
    if w._validate_receipt_chain(root, task_id)[1]:
        _fail("original workflow receipt chain is invalid")
    return snapshot


def _context(root, parent, proof, phase="prepare"):
    """Validate frozen child input even before its real initialization."""
    import goal_delivery_runtime as g
    if (not isinstance(proof, dict) or set(proof) != {"schema_version", "mode", "child_contract", "action",
            "adoption", "attempt_path", "native_send_receipt_path"} or type(proof.get("schema_version")) is not int
            or proof["schema_version"] != 1
            or proof.get("mode") != "read_only"):
        _fail("explicit project-local read-only first-send proof required")
    child_pin = _pin(root, proof.get("child_contract"))
    child = g.validate_goal(root, w.read_json(w.safe_path(root, child_pin["path"])))
    goal = parent["goal_delivery"]
    action = proof.get("action")
    if not isinstance(action, dict) or set(action) != set(ACTION_FIELDS):
        _fail("one exact bounded first-send action tuple required")
    child_id = w.validate_task_id(str(action.get("task_id") or ""))
    if (child_id == parent["task_id"] or child.get("parent_task_id") != parent["task_id"]
            or action.get("parent_task_id") != parent["task_id"]
            or child.get("initial_dispatch_mode") != "read_only"
            or child.get("source_mode") != "approved_dispatch"
            or child.get("required_execution_actions") or child.get("collaboration_scopes")
            or any(child.get(name, False) is not False for name in (
                "production_write_allowed", "production_release_eligible", "external_permission_issued"))
            or goal.get("required_execution_actions")
            or child["primary_owner"] != goal["primary_owner"]
            or child["producer_departments"] != goal["producer_departments"]
            or goal["producer_departments"] != [goal["primary_owner"]]
            or child["responsible_assistant"] != goal["responsible_assistant"]
            or child["acceptance_capability"] != goal["acceptance_capability"]
            or not set(child["authorized_scope"]) <= set(goal["authorized_scope"])
            or child["human_authorization"] != goal["human_authorization"]
            or child["authorization_pin"] != goal["authorization_pin"]):
        _fail("exact original parent/human/producer/assistant/read-only scope required")
    role = goal["responsible_assistant"]
    if (role != "operations-assistant-2" or goal["primary_owner"] != "system-development"
            or goal["acceptance_capability"] != "development"
            or any(not scope.startswith("project:flashcast:") for scope in child["authorized_scope"])
            or not g.assigned_actor(root, parent, role, action.get("scope"))
            or action.get("sender_department") != role
            or action.get("target_department") != goal["primary_owner"]
            or action.get("action_class") != "thread_message"
            or not isinstance(action.get("action_id"), str) or not action["action_id"].strip()
            or action.get("scope") not in child["authorized_scope"]):
        _fail("only original assigned assistant and producer may continue this scope")
    registry = w.department_registry(root)
    source = registry[role].get("chat_binding", {})
    target = registry[goal["primary_owner"]].get("chat_binding", {})
    mapping = {"target_thread_id": "task_id", "target_thread_title": "title", "target_cwd": "cwd",
               "target_project_id": "project_id", "target_sidebar_section_id": "sidebar_section_id"}
    if (not source.get("project_id") or action.get("source_project_id") != source["project_id"]
            or action.get("target_project_id") != source["project_id"]
            or not w._same_resolved_path(str(source.get("cwd") or ""), str(Path(root).resolve()))
            or not w._same_resolved_path(str(target.get("cwd") or ""), str(Path(root).resolve()))
            or any(not target.get(value) or action.get(key) != target[value] for key, value in mapping.items())
            or (phase != "sent" and (not w._chat_binding_healthy(source, verification_ttl_hours=26)
                                     or not w._chat_binding_healthy(target, verification_ttl_hours=26)))):
        _fail("current original project-local healthy fixed bindings required")
    payload = _pin(root, action.get("payload"))
    if payload["sha256"] != action.get("payload_sha256"):
        _fail("exact approved UTF-8 payload hash required")
    try:
        text = w.safe_path(root, payload["path"]).read_bytes().decode("utf-8")
    except UnicodeDecodeError:
        _fail("original message must be UTF-8")
    # Include machine-readable original identifiers and contract/authority pins.
    required_text = (child_id, parent["task_id"], action["scope"], child_pin["path"], child_pin["sha256"],
                     goal["authorization_pin"]["path"], goal["authorization_pin"]["sha256"])
    if not text.strip() or any(value not in text for value in required_text):
        _fail("message must identify exact child/parent/scope/contract/human pins")
    adoption = proof.get("adoption")
    from scoped_candidate_adoption import TASK, validate_adoption
    if parent["task_id"] == TASK:
        adopted = validate_adoption(root, parent, adoption)
    else:
        if not isinstance(adoption, dict) or set(adoption) != set(ADOPTION_FIELDS):
            _fail("exact independently adopted original control proof required")
        adopted = w._verify_operations_rework_completion(root, adoption, parent["task_id"])
    for name in ("attempt_path", "native_send_receipt_path"):
        path = proof.get(name)
        prefix = "logs/goal-initial-dispatch/" + child_id + "/"
        if (not isinstance(path, str) or not path.startswith(prefix)
                or str(w.safe_path(root, path).relative_to(Path(root).resolve())) != path):
            _fail("attempt/native output must use exact child-owned log paths")
    if proof["attempt_path"] == proof["native_send_receipt_path"]:
        _fail("attempt and native response paths must differ")
    return {"child": child, "action": action, "adopted": adopted}


def freeze_next(root, snapshot, request, evidence):
    """Freeze declared next-task semantics on the real parent decision."""
    if not any(name in request for name in NEXT_FIELDS):
        return {}
    if any(name not in request for name in NEXT_FIELDS):
        _fail("all exact next-task fields must be declared together")
    parent = _snapshot(root, snapshot["task_id"])
    context = _context(root, parent, request["initial_dispatch"])
    _candidate_result(parent, request, request["initial_dispatch"])
    action = context["action"]
    if (request.get("event") != "controller_decision"
            or request.get("decision") not in {"continue", "accept"}
            or request.get("coordinator_role") != parent["goal_delivery"]["responsible_assistant"]
            or request.get("next_owner") != action["target_department"]
            or request["next_task_id"] != action["task_id"]
            or request["next_action_id"] != action["action_id"]
            or request["next_scope"] != action["scope"]):
        _fail("actual assigned parent decision must explicitly bind this first send")
    required = [request["initial_dispatch"]["child_contract"], action["payload"],
                parent["goal_contract"], parent["goal_delivery"]["authorization_pin"],
                context["adopted"]["control_qa"], context["adopted"]["control_applied_proof"]]
    required.extend(context["adopted"].get("required_evidence", []))
    if any(pin not in evidence for pin in required):
        _fail("parent decision must freeze every source/contract/adoption/message pin")
    return {name: request[name] for name in NEXT_FIELDS}


def _candidate_result(parent, record, proof):
    from scoped_candidate_adoption import TASK, VERSION, PRODUCER
    if parent["task_id"] != TASK:
        return
    pin = proof.get("adoption", {}).get("producer_outbox")
    if (not isinstance(pin, dict) or record.get("candidate_version") != VERSION
            or record.get("sender_department") != PRODUCER or record.get("result_sha256") != pin.get("sha256")
            or record.get("outbox_path", record.get("outbox", {}).get("path")) != pin.get("path")
            or ("outbox" in record and record["outbox"] != pin)):
        _fail("parent current-version intake/decision must bind the exact independently adopted producer outbox")


def _fenced_decision(root, parent, action, phase):
    """Read existing SQL/audit only; no database creation, token output or writes."""
    import result_coordination as c
    rows = w._result_handoff_rows(root, parent["task_id"])
    matches = [row for row in rows if row.get("event") == "controller_decision"
               and row.get("record_id") == action.get("decision_record_id")]
    if len(matches) != 1:
        _fail("one actual frozen parent decision required")
    record = matches[0]
    _candidate_result(parent, record, action.get("parent_initial_dispatch", {}))
    decisions = [row for row in rows if row.get("event") == "controller_decision"]
    if phase != "sent" and (not decisions or decisions[-1] != record):
        _fail("latest parent decision required; superseded decisions cannot send")
    role = parent["goal_delivery"]["responsible_assistant"]
    if (record.get("coordinator_role") != role or record.get("decision_actor") != role
            or record.get("responsible_assistant") != role
            or record.get("decision") not in {"continue", "accept"}
            or record.get("next_owner") != action.get("target_department")
            or record.get("next_task_id") != action.get("task_id")
            or record.get("next_action_id") != action.get("action_id")
            or record.get("next_scope") != action.get("scope")
            or record.get("initial_dispatch") != action.get("parent_initial_dispatch")):
        _fail("parent decision exact actor/child/action/scope proof differs")
    identity = c.exact_identity(record)
    intakes = [row for row in rows[:rows.index(record)] if row.get("event") == "controller_received"
               and all(row.get(name) == value for name, value in identity.items())]
    if (len(intakes) != 1 or intakes[0].get("coordinator_role") != role
            or intakes[0].get("coordinator_owner") != record.get("coordinator_owner")
            or intakes[0].get("coordination_fence") != record.get("coordination_fence")):
        _fail("original exact fenced assistant intake must precede parent decision")
    intake = intakes[0]
    key = c._key(identity)
    effect = c._sha([record["event"], record["idempotency_key"]])
    database = w.safe_path(root, str(c.DATABASE))
    if not database.is_file():
        _fail("actual fenced coordination database required")
    connection = sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("BEGIN")
        reservation = connection.execute("SELECT status,payload_json,native_record_json FROM reservations WHERE result_key=? AND effect_key=?",
                                         (key, effect)).fetchone()
        claim = connection.execute("SELECT role,owner,fence,expires,identity_json FROM claims WHERE result_key=?", (key,)).fetchone()
        audit = list(connection.execute("SELECT seq,payload_json,previous_hash,record_hash FROM coordination_audit ORDER BY seq"))
        intake_reservation = connection.execute(
            "SELECT status,payload_json,native_record_json FROM reservations WHERE result_key=? AND effect_key=?",
            (key, c._sha([intake["event"], intake["idempotency_key"]]))).fetchone()
    except sqlite3.Error as exc:
        _fail("actual fenced coordination records unavailable: " + str(exc))
    finally:
        connection.close()
    if (not reservation or reservation["status"] != "committed"
            or json.loads(reservation["native_record_json"] or "null") != record):
        _fail("parent decision must be committed with identical native readback")
    if (not intake_reservation or intake_reservation["status"] != "committed"
            or json.loads(intake_reservation["native_record_json"] or "null") != intake
            or c._native_readback(root, json.loads(intake_reservation["payload_json"])) != intake):
        _fail("original fenced intake must retain committed exact native readback")
    payload = json.loads(reservation["payload_json"])
    reserved = payload.get("request", {})
    if (any(reserved.get(name) != record.get(name) for name in NEXT_FIELDS)
            or c._native_readback(root, payload) != record):
        _fail("parent decision reserved exact payload/evidence differs")
    previous = ""
    own = []
    for row in audit:
        value = json.loads(row["payload_json"])
        if row["previous_hash"] != previous or row["record_hash"] != c._sha([previous, value]):
            _fail("coordination audit hash chain changed")
        previous = row["record_hash"]
        if value.get("identity") == identity:
            own.append({**value, "seq": row["seq"]})
    committed = [i for i, row in enumerate(own) if row.get("event") == "effect_readback_committed"
                 and row.get("details", {}).get("effect_key") == effect
                 and row.get("details", {}).get("native_record_id") == record["record_id"]]
    if not committed:
        _fail("exact committed decision audit required")
    committed_index = committed[0]
    reserved_rows = [i for i, row in enumerate(own[:committed_index]) if row.get("event") == "effect_reserved"
                     and row.get("details", {}).get("effect_key") == effect
                     and row.get("details", {}).get("role") == role
                     and row.get("details", {}).get("owner") == record.get("coordinator_owner")]
    if len(reserved_rows) != 1:
        _fail("one original role/owner reservation audit required")
    claims = [row for row in own[:reserved_rows[0]] if row.get("event") in {"claim", "recover_expired", "transfer", "release"}]
    details = claims[-1].get("details", {}) if claims else {}
    if (not claims or claims[-1]["event"] not in {"claim", "recover_expired"}
            or details.get("role") != role or details.get("owner") != record.get("coordinator_owner")
            or details.get("fence") != record.get("coordination_fence")):
        _fail("original same-owner/fence claim audit required")
    claimed, reserved_audit, committed_audit = claims[-1], own[reserved_rows[0]], own[committed_index]
    created = w._parse_observed_at(record.get("created_at"))
    received = w._parse_observed_at(intake.get("created_at"))
    now = dt.datetime.now(dt.timezone.utc).timestamp()
    if (created is None or received is None
            or not claimed["at"] <= reserved_audit["at"] <= committed_audit["at"] <= now
            or not received.timestamp() <= created.timestamp() <= committed_audit["at"]
            or any(row.get("event") in {"release", "claim", "recover_expired", "transfer"}
                   and claimed["seq"] < row["seq"] < committed_audit["seq"] for row in own)):
        _fail("original uninterrupted claim/reserve/commit and nonfuture intake/decision timing required")
    if phase != "sent" and (not claim or claim["role"] != role
            or claim["owner"] != record.get("coordinator_owner")
            or claim["fence"] != record.get("coordination_fence")
            or claim["expires"] <= dt.datetime.now(dt.timezone.utc).timestamp()
            or json.loads(claim["identity_json"]) != identity):
        _fail("current unexpired original same-owner/fence responsibility required")
    return record


def validate_action(root, snapshot, action, phase="prepare"):
    if phase not in {"prepare", "policy", "sent"}:
        _fail("known validation phase required")
    if not action.get("parent_task_id"):
        return {}
    child = _snapshot(root, snapshot["task_id"])
    parent = _snapshot(root, action["parent_task_id"])
    proof = action.get("parent_initial_dispatch")
    context = _context(root, parent, proof, phase)
    if (action.get("task_id") != child["task_id"] or child["goal_contract"] != proof["child_contract"]
            or any(action.get(name) != context["action"].get(name) for name in ACTION_FIELDS)
            or child["goal_delivery"].get("parent_task_id") != parent["task_id"]):
        _fail("initialized child contract and frozen parent first-send action differ")
    record = _fenced_decision(root, parent, action, phase)
    if any(row.get("receipt_type") == "dispatch_sent" and row.get("department") == action["target_department"]
           for row in w.read_jsonl(w.receipts_path(root, child["task_id"]))):
        _fail("first send already recorded; read original receipt before retry")
    markers = w.safe_path(root, "logs/goal-initial-dispatch/" + child["task_id"])
    old_markers = markers.exists() and (markers.is_symlink() or any(markers.rglob("*")))
    # Child-wide protection survives new action IDs, paths or parent decisions.
    # No file in this dedicated first-send directory is a retry permission.
    if phase != "sent" and old_markers:
        _fail("existing or uncertain first-send attempt requires exact native readback; no resend")
    return {"parent_task_id": parent["task_id"], "decision_record_id": record["record_id"],
            "coordinator_role": record["coordinator_role"], "coordinator_owner": record["coordinator_owner"],
            "coordination_fence": record["coordination_fence"], "child_contract": proof["child_contract"],
            "parent_contract": parent["goal_contract"], "human_authorization": parent["goal_delivery"]["authorization_pin"],
            "adoption": context["adopted"], "external_permission_issued": False}


def _policy(root, action, decision_id):
    rows = [row for row in w.read_jsonl(Path(root) / w.POLICY_DECISIONS) if row.get("decision_id") == decision_id]
    if len(rows) != 1:
        _fail("one actual exact allow policy decision required")
    decision = rows[0]
    expected = {name: action[name] for name in ACTION_FIELDS if name not in {"payload", "parent_task_id", "sender_department"}}
    expected.update(department=action["sender_department"], status="allow", routing_status="routing_allowed")
    if any(decision.get(name) != value for name, value in expected.items()):
        _fail("actual allow policy does not match exact original first-send tuple")
    return decision


def begin(root, input_path):
    """Reserve once before native call, returning its exact original arguments."""
    root = Path(root).resolve()
    request = w.read_json(w.safe_path(root, input_path))
    with w.workflow_lock(root):
        snapshot = _snapshot(root, str(request.get("task_id") or ""))
        rows = [row for row in snapshot["goal_delivery"].get("approved_actions", [])
                if row.get("action_id") == request.get("action_id")]
        if len(rows) != 1 or not rows[0].get("parent_task_id"):
            _fail("one frozen parent-linked approved child action required")
        action = rows[0]
        metadata = validate_action(root, snapshot, action, "prepare")
        decision = _policy(root, action, request.get("policy_decision_id"))
        proof = action["parent_initial_dispatch"]
        arguments = {"threadId": action["target_thread_id"],
                     "prompt": w.safe_path(root, action["payload"]["path"]).read_bytes().decode("utf-8")}
        attempt = {"schema_version": 1, "attempt_id": str(uuid.uuid4()), "state": "called_no_response",
                   "task_id": action["task_id"], "action_id": action["action_id"], "scope": action["scope"],
                   "policy_decision_id": decision["decision_id"], "payload": action["payload"],
                   "tool": TOOL, "arguments": arguments, "source": metadata,
                   "reserved_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="microseconds"), "actual_message_sent": False,
                   "uncertain_retry_allowed": False, "external_permission_issued": False}
        path = w.safe_path(root, proof["attempt_path"])
        path.parent.mkdir(parents=True, exist_ok=True)
        # O_EXCL complements the shared workflow lock if a foreign writer races.
        with path.open("x", encoding="utf-8") as handle:
            json.dump(attempt, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        pin = w.file_digest(root, proof["attempt_path"])
        w.append_workflow_event(root, snapshot["task_id"], snapshot["current_state"], {
            "parent_initial_dispatch_attempt": pin, "action_id": action["action_id"],
            "policy_decision_id": decision["decision_id"], "actual_message_sent": False})
        return {"result": "reserved_before_native_call", "attempt": pin, "tool": TOOL,
                "arguments": arguments, "actual_message_sent": False, "external_permission_issued": False}


def validate_sent(root, snapshot, receipt, routing_decision):
    """Settle a reserved call using exact native send or positive readback only."""
    import goal_delivery_runtime as g
    snapshot = g.restore_goal(root, snapshot)
    rows = [row for row in snapshot.get("goal_delivery", {}).get("approved_actions", [])
            if row.get("action_id") == routing_decision.get("action_id")]
    if not rows or not any(row.get("parent_task_id") for row in rows):
        return {}
    if len(rows) != 1:
        _fail("one exact original parent-linked first-send action required")
    action = rows[0]
    if any(receipt.get(name) != value for name, value in {
            "task_id": action["task_id"], "action_id": action["action_id"], "action_class": "thread_message",
            "scope": action["scope"], "department": action["target_department"],
            "chat_task_id": action["target_thread_id"], "policy_decision_id": routing_decision["decision_id"]}.items()):
        _fail("dispatch receipt must identify original exact action; missing fields cannot bypass proof")
    metadata = validate_action(root, snapshot, action, "sent")
    _policy(root, action, receipt["policy_decision_id"])
    proof = action["parent_initial_dispatch"]
    pins = receipt.get("evidence", [])
    attempt_pin = w.file_digest(root, proof["attempt_path"])
    native_pin = w.file_digest(root, proof["native_send_receipt_path"])
    if attempt_pin not in pins or native_pin not in pins:
        _fail("dispatch requires original frozen attempt and actual native response pins")
    attempt = w.read_json(w.safe_path(root, attempt_pin["path"]))
    recorded = [row for row in w.read_jsonl(Path(root) / w.WORKFLOW_EVENTS)
                if row.get("task_id") == action["task_id"]
                and row.get("details", {}).get("parent_initial_dispatch_attempt") == attempt_pin
                and row.get("details", {}).get("action_id") == action["action_id"]
                and row.get("details", {}).get("policy_decision_id") == receipt["policy_decision_id"]]
    if len(recorded) != 1:
        _fail("attempt must retain its original hash-chained before-call workflow pin")
    arguments = {"threadId": action["target_thread_id"],
                 "prompt": w.safe_path(root, action["payload"]["path"]).read_bytes().decode("utf-8")}
    if (attempt.get("state") != "called_no_response" or not attempt.get("attempt_id")
            or attempt.get("source") != metadata or attempt.get("tool") != TOOL
            or attempt.get("arguments") != arguments or attempt.get("payload") != action["payload"]
            or any(attempt.get(name) != receipt.get(name) for name in ("task_id", "action_id", "scope", "policy_decision_id"))):
        _fail("original reserved first-send attempt differs")
    native = json.loads(w.safe_path(root, native_pin["path"]).read_bytes(), object_pairs_hook=_unique_fields)
    if "isError" in native and native["isError"] is not False:
        _fail("failed outer native proof cannot establish an effect")
    if native.get("attempt_id") != attempt["attempt_id"]:
        _fail("native response/readback must identify original reserved attempt")
    observed = w._parse_observed_at(native.get("observed_at"))
    reserved = w._parse_observed_at(attempt.get("reserved_at"))
    if (observed is None or reserved is None or observed < reserved
            or observed > dt.datetime.now(dt.timezone.utc)):
        _fail("actual native effect must follow original reserved attempt")
    if native.get("proof_mode", "send") == "send":
        if native.get("tool") != TOOL or native.get("arguments") != arguments:
            _fail("actual native send tool/arguments/payload/target differ")
        result = g._collaboration_native(root, native_pin)
        if result.get("threadId") != action["target_thread_id"]:
            _fail("actual native send result target differs")
    elif native.get("proof_mode") == "readback":
        if (native.get("tool") != "mcp__codex_app__read_thread"
                or native.get("arguments") != {"threadId": action["target_thread_id"]}):
            _fail("exact original target native readback required")
        envelope = native.get("actual_native_readback")
        if not isinstance(envelope, dict) or envelope.get("isError") is not False:
            _fail("successful actual native readback required")
        contents = envelope.get("content")
        if not isinstance(contents, list) or any(not isinstance(item, dict) for item in contents):
            _fail("original raw MCP readback content required")
        texts = [item.get("text") for item in contents if item.get("type") == "text"]
        if len(texts) != 1 or not isinstance(texts[0], str):
            _fail("one original native readback document required")
        envelope = json.loads(texts[0], object_pairs_hook=_unique_fields)
        if not isinstance(envelope, dict) or ("isError" in envelope and envelope["isError"] is not False):
            _fail("successful decoded raw native readback required")
        turns = envelope.get("turns", [])
        if (envelope.get("thread", {}).get("id") != action["target_thread_id"]
                or not isinstance(turns, list) or any(not isinstance(turn, dict) for turn in turns)):
            _fail("actual raw native target/turns readback required")
        matched = []
        for turn in turns:
            started = turn.get("startedAt")
            if isinstance(started, (int, float)) and not isinstance(started, bool):
                started = dt.datetime.fromtimestamp(started, dt.timezone.utc)
            else:
                started = w._parse_observed_at(started)
            if started is None or not reserved <= started <= observed or not turn.get("id"):
                continue
            for message in turn.get("items", []):
                if not isinstance(message, dict) or message.get("type") != "userMessage" or not message.get("id"):
                    continue
                body = message.get("content")
                if (isinstance(body, list) and body and all(isinstance(item, dict) and item.get("type") == "text"
                        and isinstance(item.get("text"), str) for item in body)
                        and "".join(item["text"] for item in body) == arguments["prompt"]):
                    matched.append(message)
        if len(matched) != 1:
            _fail("positive native readback must prove exact original target and UTF-8 user message")
    else:
        _fail("native send or positive readback proof required; no resend")
    return {**metadata, "attempt": attempt_pin, "actual_native_transport": native_pin,
            "attempt_id": attempt["attempt_id"], "proof_mode": native.get("proof_mode", "send"),
            "actual_message_sent": True, "new_permissions": 0}
