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


def _historical_send_time_order(times, now, policy_timestamp):
    if any(value is None or value > now for value in times):
        _fail("historical decision/policy/send time order required")
    decision_at, policy_at, sent_at = times
    # Only the original whole-second policy can lose subsecond ordering.
    # Decision and native send keep their exact recorded precision.
    whole_second = policy_at.microsecond == 0 and policy_timestamp == policy_at.isoformat(timespec="seconds")
    lower = decision_at.replace(microsecond=0) if whole_second else decision_at
    if not lower <= policy_at <= sent_at or decision_at > sent_at:
        _fail("historical decision/policy/send time order required")


def _historical_sent_source(root, parent, proof):
    """Prove the original consumed send without recursing through later QA.

    No recorded send means the ordinary current-installation check still
    applies. A phase or closed snapshot alone never creates this boundary.
    """
    import parent_initial_child_review as child_review
    import scoped_candidate_adoption as s
    if (parent.get("task_id") != s.TASK or not isinstance(proof, dict)
            or set(proof) != {"schema_version", "mode", "child_contract", "action",
                            "adoption", "attempt_path", "native_send_receipt_path"}
            or type(proof.get("schema_version")) is not int or proof["schema_version"] != 1
            or proof.get("mode") != "read_only" or not isinstance(proof.get("action"), dict)
            or set(proof["action"]) != set(ACTION_FIELDS)):
        _fail("one exact original historical first-send source required")
    action = proof["action"]
    child_id = w.validate_task_id(str(action.get("task_id") or ""))
    rows = s._receipts(root, child_id)
    rounds = [row for row in rows if row.get("department") == s.PRODUCER
              and row.get("receipt_type") in {"dispatch_sent", "dispatch_failed"}]
    if not rounds:
        return None
    if len(rounds) != 1 or rounds[0].get("receipt_type") != "dispatch_sent":
        _fail("one actual original historical producer send required")
    dispatch = rounds[0]
    parent = child_review._snapshot(root, parent)
    child = child_review._snapshot(root, w.read_json(w.snapshot_path(root, child_id)))
    goal, child_goal = parent["goal_delivery"], child["goal_delivery"]
    if (child_id == s.TASK or child.get("goal_contract") != proof["child_contract"]
            or action.get("parent_task_id") != s.TASK or child_goal.get("parent_task_id") != s.TASK
            or child_goal.get("initial_dispatch_mode") != "read_only"
            or child_goal.get("source_mode") != "approved_dispatch"
            or child_goal.get("required_execution_actions") or child_goal.get("collaboration_scopes")
            or any(child_goal.get(name) != goal.get(name) for name in (
                "primary_owner", "producer_departments", "responsible_assistant", "acceptance_capability",
                "human_authorization", "authorization_pin"))
            or child_goal.get("authorized_scope") != [s.SCOPE]
            or any(child_goal.get(name, False) is not False for name in (
                "production_write_allowed", "production_release_eligible", "external_permission_issued"))):
        _fail("historical send must retain original child/parent/human/read-only contract")
    approved = [row for row in child_goal.get("approved_actions", [])
                if row.get("action_id") == action.get("action_id")]
    if (len(approved) != 1 or approved[0].get("parent_initial_dispatch") != proof
            or any(approved[0].get(name) != action.get(name) for name in ACTION_FIELDS)):
        _fail("historical send must retain its exact frozen approved action")
    frozen = approved[0]
    decision = _fenced_decision(root, parent, frozen, "sent")
    registry = w.department_registry(root)
    fixed = registry[s.PRODUCER]["chat_binding"]["task_id"]
    expected = {"task_id": child_id, "action_id": action["action_id"], "action_class": "thread_message",
                "department": s.PRODUCER, "chat_task_id": fixed, "scope": s.SCOPE}
    if (any(dispatch.get(name) != value for name, value in expected.items())
            or action.get("sender_department") != s.ROLE or action.get("target_department") != s.PRODUCER
            or action.get("target_thread_id") != fixed):
        _fail("historical send receipt must identify the exact original action and fixed producer")
    metadata = dispatch.get("parent_initial_dispatch", {})
    expected_metadata = {"parent_task_id": s.TASK, "decision_record_id": decision["record_id"],
        "coordinator_role": s.ROLE, "coordinator_owner": decision["coordinator_owner"],
        "coordination_fence": decision["coordination_fence"], "child_contract": child["goal_contract"],
        "parent_contract": parent["goal_contract"], "human_authorization": goal["authorization_pin"],
        "external_permission_issued": False, "actual_message_sent": True, "new_permissions": 0}
    if any(metadata.get(name) != value for name, value in expected_metadata.items()):
        _fail("historical send must retain exact original committed decision/claim/fence metadata")
    policy = _policy(root, action, dispatch.get("policy_decision_id"))
    child_review._native_effect(root, action, dispatch, metadata, proof)
    times = [w._parse_observed_at(row.get(name)) for row, name in (
        (decision, "created_at"), (policy, "checked_at"), (dispatch, "created_at"))]
    _historical_send_time_order(times, dt.datetime.now(dt.timezone.utc), policy.get("checked_at"))
    return dispatch


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
        adopted = validate_adoption(root, parent, adoption, sent_source=proof if phase == "sent" else None)
    elif (parent["task_id"] == "fc-20261011-goal-publication-notice-followthrough-repair-v1"
            and isinstance(adoption, dict) and adoption.get("mode") == "tnew_source_only_adopted"):
        adopted = w.tnew_adopted_completion_context(root, parent, adoption)
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
    _candidate_result(parent, request, request["initial_dispatch"], root=root)
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


def _candidate_result(parent, record, proof, *, root=None):
    from scoped_candidate_adoption import TASK, VERSION, PRODUCER
    if parent["task_id"] == "fc-20261011-goal-publication-notice-followthrough-repair-v1":
        pin = proof.get("adoption", {}).get("producer_outbox")
        if root is None:
            _fail("actual project-local TNEW producer source required")
        exact = _pin(root, pin)
        producer = w.read_json(w.safe_path(root, exact["path"]))
        if (not isinstance(pin, dict) or record.get("sender_department") != "system-development"
                or producer.get("task_id") != parent["task_id"] or producer.get("department") != "system-development"
                or record.get("candidate_version") != producer.get("candidate_version")
                or record.get("result_sha256") != pin.get("sha256")
                or record.get("outbox_path", record.get("outbox", {}).get("path")) != pin.get("path")
                or ("outbox" in record and record["outbox"] != pin)):
            _fail("original TNEW decision must retain the exact independently adopted producer outbox")
        return
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
    _candidate_result(parent, record, action.get("parent_initial_dispatch", {}), root=root)
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



def _responsibility_approval_document(root, pin):
    """Preserve native container flags before and after approval decoding.

    Only native evidence containers are checked recursively; message text and
    ordinary business fields never become transport failure markers.
    """
    import qa_review_plan as q
    try:
        value = q._review_source_document(root, pin)
        q._review_native_containers(value)
        if "content" in value and not value.get("thread"):
            value = q._review_raw_native_result(value)
        q._review_native_containers(value)
    except (ValueError, TypeError, OSError):
        _fail("successful complete unambiguous native HQ approval required")
    return value


def _queued_responsibility_action_source(root, child, action, proof, approval, dispatch, ack, rows):
    """Consume the real original queue plus the uniquely frozen unsent intent.

    The native HQ payload delegates this whole goal and names the SYS task file;
    it does not contain a future action tuple. Keep these two sources distinct.
    No caller flag, reconstructed MCP output or new business dispatch is used.
    """
    import qa_review_plan as q
    from goal_source_recovery import queued_assignment_source
    task='fc-20261021-two-original-post-intake-receipt-followthrough-v1'
    base='logs/handoffs/2026-10-20-clean-department-window-rotation-v1/operations/unfinished-business-followthrough-20261021-v1/two-original-post-intake-receipt-followthrough-v1/'
    original_pin={'path':base+'operations-assistant-2-independent-review-v1/A2-TWO-FIRST-SYS-ACTION-ACTUAL-QUEUED-RESPONSIBILITY-INPUT-v1.json',
                  'sha256':'60fe6568887edbbcfd75640a57eaed0656ae3bcd1eb8b95b442db0b2e371a996','size':4125}
    original=q._review_source_document(root,original_pin)
    if (child.get('task_id')!=task or set(action)!=set(original)
            or any(action.get(k)!=v for k,v in original.items()if k!='live_identity')
            or proof!=original['goal_responsibility_dispatch']):
        _fail('only the exact frozen original queued responsibility action may resume')
    source_pin=proof.get('actual_queued_assignment')
    if (source_pin not in dispatch.get('evidence',[])or source_pin not in ack.get('evidence',[])
            or ack.get('idempotency_key')!=dispatch.get('idempotency_key','')+'-ack'
            or ack.get('policy_decision_id')!=dispatch.get('policy_decision_id')
            or any(row.get('supersedes_receipt_id')in{dispatch['receipt_id'],ack['receipt_id']}for row in rows)):
        _fail('original actual queued dispatch/ACK source and uniqueness required')
    item=q._review_source_document(root,source_pin)
    # This existing validator proves actual command/transport, exact policy,
    # immutable human/contract/payload, receiving userMessage/ACK and time order.
    snapshot,actual_dispatch=queued_assignment_source(root,item)
    if (snapshot.get('task_id')!=child['task_id']or snapshot.get('goal_contract')!=child['goal_contract']
            or actual_dispatch!=dispatch or item.get('sender_department')!='operations'
            or item.get('department')!=child['goal_delivery']['responsible_assistant']
            or item.get('scope')!=action['scope']or item.get('authorization_pin')!=child['goal_delivery']['authorization_pin']
            or proof.get('actual_native_approval')!=item.get('actual_native_recipient')
            or proof.get('approval_turn_id')!=item.get('receiver_turn_id')
            or proof.get('approval_item_id')!=item.get('receiver_message_id')):
        _fail('same original HQ queue, receiving approval and real receipt links required')
    turns=[t for t in approval.get('turns',[])if t.get('id')==item['receiver_turn_id']]
    messages=[m for t in turns for m in t.get('items',[])if m.get('id')==item['receiver_message_id']and m.get('type')=='userMessage']
    body=w.safe_path(root,_pin(root,item['payload'])['path']).read_text(encoding='utf-8')
    if (len(turns)!=1 or len(messages)!=1 or messages[0].get('content')!=[{'type':'text','text':body}]
            or str(w.safe_path(root,child['goal_contract']['path']))not in body
            or '同目录'+Path(action['payload']['path']).name not in body
            or Path(action['payload']['path']).parent!=Path(item['payload']['path']).parent):
        _fail('actual original whole-goal queue must name this exact original producer task')
    _pin(root,action['payload'])


def validate_responsibility_action(root, snapshot, action, phase="prepare"):
    """First routine producer send under the actually assigned whole goal.

    Parent is a relation, not a fabricated source workflow or prior decision.
    """
    import goal_delivery_runtime as g
    import qa_review_plan as q
    if phase not in {"prepare", "policy", "sent"}:
        _fail("known responsibility validation phase required")
    child = _snapshot(root, snapshot["task_id"])
    goal = child["goal_delivery"]; role = goal["responsible_assistant"]
    proof = action.get("goal_responsibility_dispatch")
    if (not isinstance(proof, dict) or proof.get("schema_version") != "goal-responsibility-initial-dispatch-v1"
            or proof.get("goal_contract") != child["goal_contract"]
            or proof.get("authorization_pin") != goal["authorization_pin"]
            or action.get("task_id") != child["task_id"]
            or action.get("parent_task_id") not in {None, goal.get("parent_task_id")}
            or action.get("sender_department") != role
            or action.get("target_department") not in goal["producer_departments"]
            or action.get("target_department") in {"operations", role}
            or action.get("action_class") != "thread_message"
            or action.get("scope") not in goal["authorized_scope"] or not action.get("action_id")):
        _fail("exact frozen whole goal, actual responsible assistant, producer and scope required")
    _pin(root, child["goal_contract"]); _pin(root, goal["authorization_pin"])
    registry = w.department_registry(root)
    authority = registry[role].get("coordination_authority", {})
    if (authority.get("routine_decisions") is not True or authority.get("dispatch_approved_next") is not True
            or registry[role].get("new_dispatch_enabled") is False
            or registry[action["target_department"]].get("new_dispatch_enabled") is False):
        _fail("current routine authority and producer required")
    rows, invalid = w._validate_receipt_chain(root, child["task_id"])
    if invalid:
        _fail("intact original receipt chain required")
    refs = []
    for kind, key in (("dispatch_sent", "responsibility_dispatch"), ("chat_ack", "responsibility_ack")):
        ref = proof.get(key, {})
        selected = [(index, row) for index, row in enumerate(rows)
                    if row.get("receipt_id") == ref.get("receipt_id")
                    and row.get("receipt_hash") == ref.get("receipt_hash") and row.get("receipt_type") == kind
                    and row.get("department") == role
                    and row.get("chat_task_id") == registry[role]["chat_binding"]["task_id"]]
        if len(selected) != 1:
            _fail("exact real HQ responsibility dispatch and ACK required")
        refs.append(selected[0])
    (di, dispatch), (ai, ack) = refs
    if (di >= ai or not q._initial_assignment(root, child, dispatch)
            or ack.get("ack_nonempty") is not True
            or any(row.get("department") == role and row.get("receipt_type") in {"dispatch_sent", "dispatch_failed"}
                   for row in rows[ai+1:])):
        _fail("original complete responsibility assignment and non-superseded ACK required")
    # Reuse V6's actual initial-envelope validation, including canonical raw
    # ACK parsing and original time boundaries. No parent/child history added.
    if not q._initial_assignment_envelope(
            root, child, dispatch, child["goal_contract"]):
        _fail("real intact native initial assignment transport required")
    approval = _responsibility_approval_document(root, proof.get("actual_native_approval"))
    if approval.get("thread", {}).get("id") != registry[role]["chat_binding"]["task_id"]:
        _fail("approval must arrive in this actual responsible assistant chat")
    queued = proof.get("source_kind") == "official_native_queue"
    if queued:
        _queued_responsibility_action_source(root,child,action,proof,approval,dispatch,ack,rows)
    else:
        turn = [row for row in approval.get("turns", []) if row.get("id") == proof.get("approval_turn_id")]
        items = [item for row in turn for item in row.get("items", [])
                 if item.get("id") == proof.get("approval_item_id") and item.get("type") == "functionCallOutput"]
        if len(turn) != 1 or len(items) != 1:
            _fail("one actual native HQ approval turn/item required")
        try:
            q._review_native_containers(turn[0])
            q._review_native_containers(items[0])
        except (ValueError, TypeError):
            _fail("successful complete selected native HQ approval source required")
        output = items[0].get("output", {})
        text = output.get("text") if isinstance(output, dict) else output
        from re import fullmatch, escape
        match = fullmatch(r"\s*<codex_delegation>\s*<source_thread_id>(" +
            escape(registry["operations"]["chat_binding"]["task_id"]) +
            r")</source_thread_id>\s*<input>([\s\S]+)</input>\s*</codex_delegation>\s*", text or "")
        if not match or (isinstance(output, dict) and output.get("truncated") is not False):
            _fail("actual nontruncated current HQ delegation required")
        body = match[2]
        import hashlib
        exact_contract_body = hashlib.sha256(body.encode("utf-8")).hexdigest()==child["goal_contract"]["sha256"]
        if (any(value not in body for value in (child["task_id"],action["scope"]))
                or (not exact_contract_body and child["goal_contract"]["sha256"] not in body)):
            _fail("HQ approval must pin this exact whole task/scope/contract")
    payload = _pin(root, action.get("payload"))
    if payload["sha256"] != action.get("payload_sha256"):
        _fail("exact current prepared payload required")
    if not queued and payload != child["goal_contract"] and any(value not in body for value in (
            payload["sha256"], action["action_id"], action["target_thread_id"])):
        _fail("non-contract payload needs exact native HQ action/target/payload approval")
    # Live evidence is action-specific and required for the actual opportunity.
    live = _pin(root, action.get("live_identity"))
    observed = w.read_json(w.safe_path(root, live["path"]))
    now = dt.datetime.now(dt.timezone.utc)
    at = w._parse_observed_at(observed.get("observed_at"))
    if (at is None or at>now or (phase!="sent" and (now-at).total_seconds()>300)):
        _fail("fresh actual idle identity before send required")
    for who, status in ((role, None), (action["target_department"], "idle")):
        fixed = registry[who]["chat_binding"]
        entries = [row for row in observed.get("threads", []) if row.get("id") == fixed["task_id"]]
        if len(entries) != 1 or any(entries[0].get(k) != fixed[v] for k,v in (
                ("projectId","project_id"),("title","title"),("cwd","cwd"))):
            _fail("actual same project/title/cwd/fixed identity required")
        if status and entries[0].get("status") != status:
            _fail("active target stays queued; idle opportunity required")
        groups = [row for row in observed.get("sections", []) if row.get("sectionId") == fixed["sidebar_section_id"]]
        if len(groups) != 1 or "codex:thread:local:" + fixed["task_id"] not in groups[0].get("itemKeys", []):
            _fail("actual fixed sidebar group required")
    if any(row.get("department") == action["target_department"]
            and row.get("receipt_type") in {"dispatch_sent","dispatch_failed"} for row in rows):
        _fail("initial producer round already sent or uncertain; read back before retry")
    markers = w.safe_path(root, "logs/goal-initial-dispatch/" + child["task_id"])
    if phase != "sent" and markers.exists() and (markers.is_symlink() or any(markers.rglob("*"))):
        _fail("first attempt exists or is uncertain; no resend")
    for name in ("attempt_path","native_send_receipt_path"):
        w.safe_path(root, proof.get(name, ""))
        if not str(proof.get(name, "")).startswith("logs/goal-initial-dispatch/" + child["task_id"] + "/"):
            _fail("owned first-send attempt paths required")
    return {"goal_contract": child["goal_contract"], "human_authorization": goal["authorization_pin"],
            "responsibility_dispatch": proof["responsibility_dispatch"], "responsibility_ack": proof["responsibility_ack"],
            "actual_native_approval": proof["actual_native_approval"], "coordinator_role": role,
            "external_permission_issued": False, "new_permissions": 0}


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
        if len(rows) != 1 or not (rows[0].get("parent_initial_dispatch") or rows[0].get("goal_responsibility_dispatch")):
            _fail("one frozen original approved initial action required")
        action = rows[0]
        metadata = (validate_responsibility_action(root, snapshot, action, "prepare")
                    if action.get("goal_responsibility_dispatch") else validate_action(root, snapshot, action, "prepare"))
        decision = _policy(root, action, request.get("policy_decision_id"))
        proof = action.get("goal_responsibility_dispatch", action.get("parent_initial_dispatch"))
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
    if not rows or not any(row.get("parent_initial_dispatch") or row.get("goal_responsibility_dispatch") for row in rows):
        return {}
    if len(rows) != 1:
        _fail("one exact original parent-linked first-send action required")
    action = rows[0]
    if any(receipt.get(name) != value for name, value in {
            "task_id": action["task_id"], "action_id": action["action_id"], "action_class": "thread_message",
            "scope": action["scope"], "department": action["target_department"],
            "chat_task_id": action["target_thread_id"], "policy_decision_id": routing_decision["decision_id"]}.items()):
        _fail("dispatch receipt must identify original exact action; missing fields cannot bypass proof")
    metadata = (validate_responsibility_action(root, snapshot, action, "sent")
                if action.get("goal_responsibility_dispatch") else validate_action(root, snapshot, action, "sent"))
    _policy(root, action, receipt["policy_decision_id"])
    proof = action.get("goal_responsibility_dispatch", action.get("parent_initial_dispatch"))
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
