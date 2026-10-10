"""Owner-approved one-Logo channel. No general Ads, activation or payment gate."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

ROOT = "<PROJECT_ROOT>"
PROJECT = "<LOCAL_PROJECT_ID>"
SOURCE = "<LOCAL_TASK_ID>"
QA = "<LOCAL_TASK_ID>"
TASK = "fc-20260920-google-ads-rm100-budget-plan"
AUTH_TURN = 'synthetic-evidence-not-native'
AUTH_MESSAGE = 'synthetic-evidence-not-native'
PREFIX = "owner_paid_logo:example-ads-account:v1:"
VERSION = "paid-business-logo-owner-channel-v1"
CAMPAIGNS = []
ASSET = "000415033906"
LOGO_SCOPE = "google_ads:example-ads-account:campaigns:00057225103+00063878462:business-logo:asset-000415033906:campaign-association-only:v1"
UNCHANGED = []
ACTIONS = {}
SESSION_ROOT = Path.home() / ".codex/sessions"
CONTROL_SCOPE = "project:flashcast:owner-paid-logo-one-shot-control:v1"
IDENTITY = ("task_id", "action_id", "action_class", "scope", "candidate_version", "candidate_sha256")
HISTORICAL_QA1_BLOCKED_PIN = {}
HISTORICAL_REVIEW_ATTEMPT_PATH = 'synthetic-evidence-not-native'
HEADQUARTERS = "<LOCAL_TASK_ID>"
QA_TECHNICAL = "<LOCAL_TASK_ID>"
TOOL_REQUEST_FORMAT = "read_thread.codex_delegation.functionCallOutput.v1"
HISTORICAL_LOGO_PACKET_PIN = {}
HISTORICAL_REVIEW_ATTEMPT_PIN = {}
HISTORICAL_REVIEW_SEND_PIN = {}


def _require(ok, reason):
    if not ok:
        raise ValueError(reason)


class _Evidence:
    """Read pinned project files. No receipts, session bodies or permissions are written."""
    def __init__(self, root):
        self.root = root.resolve()

    def path(self, value):
        _require(isinstance(value, str) and value, "project_path_required")
        p = (self.root / value).resolve()
        _require(p != self.root and p.is_relative_to(self.root), "project_path_required")
        return p

    def raw(self, value):
        p = self.path(value["path"])
        raw = p.read_bytes()
        _require(hashlib.sha256(raw).hexdigest() == value["sha256"], "frozen_pin_changed")
        if "size" in value:
            _require(type(value["size"]) is int and len(raw) == value["size"], "frozen_pin_size_changed")
        return raw

    def pin(self, value):
        self.raw(value)
        return self.path(value["path"])

    def json(self, value):
        return json.loads(self.raw(value).decode("utf-8"))


@dataclass(frozen=True)
class _Reply:
    thread_id: str
    turn_id: str
    message_id: str
    namespace: str
    text: str
    request_texts: tuple[str, ...] = ()

    @property
    def sha256(self):
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()


def _app_request_text(content) -> str:
    _require(isinstance(content, list) and bool(content)
             and all(isinstance(c, dict) and c.get("type") in (None, "text", "input_text")
                     and isinstance(c.get("text"), str) for c in content),
             "native_user_utf8_text_required")
    return "".join(c["text"] for c in content)


def _native_reply(e: _Evidence, descriptor: dict) -> _Reply:
    """Versioned adapters for saved native shapes; booleans never authenticate a reply."""
    _require(type(descriptor["schema_version"]) is int and descriptor["schema_version"] == 1,
             "native_reader_version_required")
    fmt = descriptor["format"]
    if fmt == "read_thread.turn.v1":
        native = e.json(descriptor["pin"])
        turn = native["turn"]
        _require(turn["status"] == "completed", "completed_fixed_qa_required")
        rows = [m for m in turn["items"] if m.get("id") == descriptor["message_id"]]
        _require(len(rows) == 1 and rows[0]["type"] == "agentMessage", "unique_native_qa_reply_required")
        requests = tuple(_app_request_text(m["content"]) for m in turn["items"] if m.get("type") == "userMessage")
        reply = _Reply(native["thread_id"], turn["id"], rows[0]["id"], "app.agentMessage", rows[0]["text"], requests)
    elif fmt == "read_thread.completed-result.v1":
        native = e.json(descriptor["pin"])
        _require(native["source_method"] == "mcp__codex_app__read_thread"
                 and native["turn_status"] == "completed", "completed_fixed_qa_required")
        message = native["result_message"]
        _require(message["type"] == "agentMessage", "native_agent_message_required")
        reply = _Reply(native["thread_id"], native["turn_id"], message["id"], "app.agentMessage", message["text"])
    elif fmt == "local_session.response_item.v1":
        provenance = e.json(descriptor["pin"])
        _require(provenance["schema_version"] == 1, "local_provenance_version_required")
        rows = [r for r in provenance["rows"] if r["kind"] == descriptor["kind"]]
        _require(len(rows) == 1, "unique_local_provenance_required")
        row = rows[0]
        session = Path(row["session_path"]).resolve()
        _require(session.is_relative_to(SESSION_ROOT.resolve()), "native_local_session_path_required")
        line = row["native_message"]["line"]
        _require(type(line) is int and line > 0, "exact_local_response_line_required")
        session_meta, context, record = None, None, None
        # A response_item has no turn_id. The preceding actual turn_context is required.
        with session.open(encoding="utf-8") as stream:
            for index, raw in enumerate(stream, 1):
                if index > line:
                    break
                if '"session_meta"' not in raw and '"turn_context"' not in raw and index != line:
                    continue
                value = json.loads(raw)
                if value.get("type") == "session_meta": session_meta = value["payload"]
                if value.get("type") == "turn_context": context = (index, value["payload"])
                if index == line: record = value
        _require(session_meta and session_meta["id"] == row["thread_id"]
                 and session_meta["cwd"] == str(e.root), "local_session_identity_required")
        _require(context and context[1]["turn_id"] == row["turn_id"]
                 and context[1]["cwd"] == str(e.root)
                 and any(c["line"] == context[0] and c["turn_id"] == row["turn_id"]
                         and c["cwd"] == str(e.root) for c in row["exact_turn_context"]), "local_turn_context_required")
        _require(record and record["type"] == "response_item", "local_response_item_required")
        message = record["payload"]
        _require(message["type"] == "message" and message["role"] == "assistant"
                 and message["id"] == row["native_message"]["local_response_item_message_id"], "local_message_identity_required")
        _require(message["content"] and all(c["type"] == "output_text" and isinstance(c["text"], str)
                                            for c in message["content"]), "local_utf8_text_required")
        text = "".join(c["text"] for c in message["content"])
        reply = _Reply(row["thread_id"], row["turn_id"], message["id"], "local_session.response_item", text)
        _require(reply.sha256 == row["native_message"]["sha256"] == row["expected_sha256"]
                 and len(text.encode("utf-8")) == row["native_message"]["utf8_bytes"], "local_utf8_digest_required")
        # Completion comes from an existing read_thread result, never from response_item alone.
        _require(descriptor["completion"]["format"] in {"read_thread.turn.v1", "read_thread.completed-result.v1"},
                 "separate_native_completion_required")
        completed = _native_reply(e, descriptor["completion"])
        _require(completed.namespace == "app.agentMessage" and completed.thread_id == reply.thread_id
                 and completed.turn_id == reply.turn_id and completed.sha256 == reply.sha256,
                 "local_completed_turn_required")
        _require(row.get("message_id") == reply.message_id, "local_message_namespace_mismatch")
    else:
        raise ValueError("unsupported_native_reader_format")
    _require(all(isinstance(v, str) and v for v in (reply.thread_id, reply.turn_id, reply.message_id))
             and isinstance(reply.text, str) and reply.text.strip(), "nonempty_native_qa_reply_required")
    return reply


def _match_reply(box, reply, thread_id, *, legacy=False):
    chat = box["chat_reply"]
    fixed = box["identity"]["chat_task_id"] if legacy else box["fixed_chat_task_id"]
    digest = chat["body_sha256"] if legacy else chat["sha256"]
    _require(fixed == reply.thread_id == thread_id and chat["message_id"] == reply.message_id
             and digest == reply.sha256, "exact_native_reply_required")
    if not legacy:
        _require(chat["turn_id"] == reply.turn_id, "exact_native_turn_required")
    if reply.namespace == "local_session.response_item":
        _require(chat["message_id"].startswith("msg_"), "local_message_namespace_mismatch")


@dataclass(frozen=True)
class _DelegationRequest:
    target_thread_id: str
    turn_id: str
    tool_output_id: str
    source_thread_id: str
    raw_wrapper: str
    payload: bytes
    created_at: dt.datetime
    namespace: str = "app.functionCallOutput/codex_app/send_message_to_thread"


def _delegation_request(e, descriptor, target_thread_id, turn_id, payload) -> _DelegationRequest:
    """Read the actual tool output and original local record; never manufacture a user item."""
    _require(type(descriptor["schema_version"]) is int and descriptor["schema_version"] == 1
             and descriptor["format"] == TOOL_REQUEST_FORMAT, "native_tool_request_version_required")
    _require(target_thread_id in {QA, QA_TECHNICAL}
             and descriptor["target_thread_id"] == target_thread_id
             and descriptor["turn_id"] == turn_id
             and descriptor["source_thread_id"] == HEADQUARTERS, "fixed_native_tool_request_context_required")
    native = e.json(descriptor["pin"])
    _require(isinstance(native, dict) and isinstance(native.get("turn"), dict)
             and isinstance(native["turn"].get("items"), list)
             and all(isinstance(m, dict) for m in native["turn"]["items"]), "native_tool_record_shape_required")
    _require(type(native["schema_version"]) is int and native["schema_version"] == 1
             and native["source_method"] == "mcp__codex_app__read_thread"
             and native["thread_id"] == target_thread_id and native["turn"]["id"] == turn_id
             and native["turn"]["status"] == "completed", "actual_native_tool_turn_required")
    item_id = descriptor["tool_output_id"]
    _require(isinstance(item_id, str) and item_id.startswith("fco_"), "native_tool_output_id_required")
    rows = [m for m in native["turn"]["items"] if m.get("id") == item_id]
    _require(len(rows) == 1, "unique_native_tool_output_required")
    item = rows[0]
    _require(item["type"] == "functionCallOutput" and item["name"] == "send_message_to_thread"
             and item["namespace"] == "codex_app", "exact_native_tool_namespace_required")
    _require(isinstance(item.get("output"), dict), "native_tool_output_shape_required")
    _require(item["output"]["truncated"] is False and isinstance(item["output"]["text"], str),
             "complete_native_tool_wrapper_required")
    raw = item["output"]["text"]
    _require(type(descriptor["wrapper_utf8_bytes"]) is int
             and len(raw.encode("utf-8")) == descriptor["wrapper_utf8_bytes"]
             and hashlib.sha256(raw.encode("utf-8")).hexdigest() == descriptor["wrapper_sha256"],
             "exact_native_wrapper_digest_required")
    prefix = "<codex_delegation>\n  <source_thread_id>" + HEADQUARTERS + "</source_thread_id>\n  <input>"
    suffix = "</input>\n</codex_delegation>"
    _require(raw.startswith(prefix) and raw.endswith(suffix)
             and all(raw.count(token) == 1 for token in ("<codex_delegation>", "</codex_delegation>",
                     "<source_thread_id>", "</source_thread_id>", "<input>", "</input>")),
             "canonical_headquarters_delegation_wrapper_required")
    inner = raw[len(prefix):-len(suffix)].encode("utf-8")
    expected = e.raw(payload)
    _require(inner == expected and hashlib.sha256(inner).hexdigest() == payload["sha256"],
             "native_tool_inner_payload_must_match_exact_request")
    local = descriptor["local_record"]
    session = Path(local["source_path"]).resolve()
    _require(session.is_relative_to(SESSION_ROOT.resolve()), "native_local_session_path_required")
    line = local["line"]
    _require(type(line) is int and line > 0 and type(local["turn_context_line"]) is int,
             "exact_local_tool_record_line_required")
    meta, context, record, raw_line, copies = None, None, None, None, 0
    with session.open("rb") as stream:
        for index, data in enumerate(stream, 1):
            if index <= line:
                value = json.loads(data)
                if value.get("type") == "session_meta": meta = value["payload"]
                if value.get("type") == "turn_context": context = (index, value["payload"])
                if index == line: record, raw_line = value, data
            elif item_id.encode("utf-8") in data:
                value = json.loads(data)
            else:
                continue
            _require(isinstance(value, dict), "local_tool_record_shape_required")
            _require(value.get("type") != "response_item" or isinstance(value.get("payload"), dict),
                     "local_tool_payload_shape_required")
            if value.get("type") == "response_item" and value.get("payload", {}).get("id") == item_id:
                copies += 1
    _require(copies == 1, "unique_original_local_tool_output_required")
    _require(raw_line is not None and type(local["raw_utf8_bytes"]) is int
             and len(raw_line) == local["raw_utf8_bytes"]
             and hashlib.sha256(raw_line).hexdigest() == local["raw_sha256"], "original_local_tool_record_digest_required")
    _require(meta and meta["id"] == target_thread_id and meta["cwd"] == str(e.root), "local_tool_session_identity_required")
    _require(context and context[0] == local["turn_context_line"]
             and context[1]["turn_id"] == turn_id and context[1]["cwd"] == str(e.root), "actual_local_tool_turn_context_required")
    _require(record and record["type"] == "response_item", "original_local_tool_response_item_required")
    message = record["payload"]
    _require(record["metadata"]["client_authored"] is False
             and record["metadata"]["sender_user_messages"]["receiver_turn_id"] == turn_id
             and record["metadata"]["sender_user_messages"]["receiver_message_id"] == item_id,
             "actual_host_delivery_receiver_context_required")
    _require(message["type"] == "function_call_output" and message["id"] == item_id
             and message["name"] == item["name"] and message["namespace"] == item["namespace"]
             and message["output"] == raw and message["internal_chat_message_metadata_passthrough"]["turn_id"] == turn_id,
             "app_and_original_local_tool_record_must_match")
    seconds = message["internal_chat_message_metadata_passthrough"]["create_time"]
    _require(type(seconds) in (int, float) and 0 <= seconds <= dt.datetime.now(dt.timezone.utc).timestamp(),
             "actual_local_tool_timestamp_required")
    created = dt.datetime.fromtimestamp(seconds, dt.timezone.utc)
    _require(created <= dt.datetime.now(dt.timezone.utc), "future_native_tool_input_denied")
    return _DelegationRequest(target_thread_id, turn_id, item_id, HEADQUARTERS, raw, inner, created)


def _bind_delegation_dispatch(e, descriptor, observed, dispatch, plan, w, receipts):
    """Same exact existing sender policy and dispatch; old evidence cannot serve a new send."""
    reviewer = plan["reviewer_department"]
    _require((reviewer, plan["reviewer_thread_id"]) in {("qa", QA), ("qa-technical", QA_TECHNICAL)},
             "exact_native_tool_fixed_reviewer_required")
    _require(descriptor["dispatch_receipt_id"] == dispatch["receipt_id"]
             and plan["controller_thread_id"] == HEADQUARTERS
             and plan["reviewer_thread_id"] == observed.target_thread_id,
             "native_tool_input_must_bind_current_dispatch")
    decisions = [r for r in w.read_jsonl(e.root / "logs/policy-decisions.jsonl")
                 if r.get("decision_id") == dispatch.get("policy_decision_id")]
    _require(len(decisions) == 1, "exact_dispatch_policy_decision_required")
    decision = decisions[0]
    _require(decision["status"] == "allow" and decision["routing_status"] == "routing_allowed"
             and decision["task_id"] == plan["task_id"] and decision["action_id"] == plan["action_id"]
             and decision["action_class"] == "thread_message" and decision["scope"] == plan["scope"]
             and decision["department"] == "operations" and decision["target_department"] == reviewer
             and decision["source_project_id"] == PROJECT and decision["target_project_id"] == PROJECT
             and decision["target_thread_id"] == observed.target_thread_id and decision["target_cwd"] == str(e.root)
             and decision["payload_sha256"] == hashlib.sha256(observed.payload).hexdigest(),
             "native_tool_current_sender_policy_required")
    checked = w._parse_observed_at(decision["checked_at"])
    sent = w._parse_observed_at(dispatch["created_at"])
    current = [i for i, r in enumerate(receipts) if r.get("receipt_id") == dispatch["receipt_id"]]
    _require(len(current) == 1 and receipts[current[0]] == dispatch,
             "native_tool_current_dispatch_chain_required")
    prior = [r for r in receipts[:current[0]] if r.get("department") == reviewer
             and r.get("receipt_type") in {"dispatch_sent", "dispatch_failed"}]
    _require(not any(r.get("policy_decision_id") == decision["decision_id"] for r in prior),
             "native_tool_dispatch_policy_already_used")
    prior_times = [w._parse_observed_at(r["created_at"]) for r in prior]
    _require(checked is not None and all(t is not None and t < checked for t in prior_times),
             "native_tool_policy_must_follow_prior_dispatch_attempts")
    _require(checked is not None and sent is not None
             and checked <= observed.created_at <= sent <= dt.datetime.now(dt.timezone.utc),
             "native_tool_input_outside_current_dispatch_window")
    return decision


def _native_request(e, descriptor, reply, payload):
    """Compare the actual native user record, rather than a claimed payload digest."""
    _require(type(descriptor["schema_version"]) is int and descriptor["schema_version"] == 1,
             "native_request_reader_version_required")
    if descriptor["format"] == TOOL_REQUEST_FORMAT:
        return _delegation_request(e, descriptor, reply.thread_id, reply.turn_id, payload)
    expected = e.raw(payload).decode("utf-8")
    if descriptor["format"] == "read_thread.userMessage.v1":
        native = e.json(descriptor["pin"])
        _require(native["thread_id"] == reply.thread_id and native["turn"]["id"] == reply.turn_id,
                 "native_request_turn_required")
        rows = [m for m in native["turn"]["items"] if m.get("id") == descriptor["message_id"]]
        _require(len(rows) == 1 and rows[0]["type"] == "userMessage", "unique_native_user_request_required")
        text = _app_request_text(rows[0]["content"])
    elif descriptor["format"] == "local_session.user_message.v1":
        session = Path(descriptor["source_path"]).resolve()
        _require(session.is_relative_to(SESSION_ROOT.resolve()), "native_local_session_path_required")
        line = descriptor["line"]
        _require(type(line) is int and line > 0, "exact_local_request_line_required")
        meta, context, record = None, None, None
        with session.open(encoding="utf-8") as stream:
            for index, raw in enumerate(stream, 1):
                if index > line: break
                if '"session_meta"' not in raw and '"turn_context"' not in raw and index != line: continue
                value = json.loads(raw)
                if value.get("type") == "session_meta": meta = value["payload"]
                if value.get("type") == "turn_context": context = value["payload"]
                if index == line: record = value
        _require(meta and context and meta["id"] == reply.thread_id and meta["cwd"] == str(e.root)
                 and context["turn_id"] == reply.turn_id and context["cwd"] == str(e.root), "native_request_turn_required")
        _require(record and record["type"] == "response_item", "native_user_response_item_required")
        message = record["payload"]
        _require(message["type"] == "message" and message["role"] == "user"
                 and message["id"] == descriptor["message_id"], "native_user_message_identity_required")
        _require(message["content"] and all(c["type"] == "input_text" for c in message["content"]),
                 "native_user_utf8_text_required")
        text = "".join(c["text"] for c in message["content"])
    else:
        raise ValueError("unsupported_native_request_format")
    _require(isinstance(text, str) and text == expected, "native_request_must_match_exact_payload")


def _technical_qa2(e, rule, pack, departments, healthy):
    """Future input only: a passing current source-bound R0 chain is mandatory."""
    import qa_review_plan as q
    w = q._workflow()
    dep = e.json(rule["technical_qa2"])
    _require(type(dep["schema_version"]) is int and dep["schema_version"] == 1
             and dep["kind"] == "owner_paid_logo.technical_qa2.v1",
             "technical_qa2_contract_required")
    _require(dep["logo_packet"] == rule["packet"], "technical_qa2_logo_packet_required")
    e.pin(dep["logo_packet"])
    source_pins = dep["consumer_source_pins"]
    _require(len(source_pins) == 2 and {p["path"] for p in source_pins} == {
        "tools/owner_paid_logo_policy.py", "tools/workflow_control.py"}, "exact_consumer_sources_required")
    for value in source_pins:
        e.pin(value)
        module_path = Path(__file__) if value["path"].endswith("owner_paid_logo_policy.py") else Path(w.__file__)
        _require(hashlib.sha256(module_path.read_bytes()).hexdigest() == value["sha256"], "running_consumer_source_mismatch")
    candidate = e.json(dep["candidate"])
    request = e.json(dep["technical_request"])
    plan = e.json(dep["review_plan"])
    expected = {key: plan[key] for key in IDENTITY}
    _require(dep["review_identity"] == expected and all(candidate[k] == plan[k] for k in IDENTITY[:-1])
             and dep["candidate"]["sha256"] == plan["candidate_sha256"], "exact_technical_review_identity_required")
    _require(candidate["source_business_task_id"] == request["source_business_task_id"] == TASK
             and candidate["source_candidate_version"] == request["source_candidate_version"], "technical_qa2_business_source_required")
    control = e.json(candidate["source_candidate"])
    _require(control["task_id"] == TASK and control["candidate_version"] == candidate["source_candidate_version"]
             and control["action_class"] == "internal_control_candidate" and control["scope"] == CONTROL_SCOPE
             and control["risk_level"] == "R0", "original_logo_control_candidate_required")
    required_sources = source_pins + [rule["packet"], candidate["source_candidate"]]
    for value in required_sources:
        _require(value in candidate["frozen_sources"], "technical_candidate_source_pin_required")
        e.pin(value)
    _require(request["candidate"] == dep["candidate"] and request["review_plan"] == dep["review_plan"]
             and request["review_identity"] == expected and request["request_payload"] == dep["request_payload"]
             and request["reviewer_department"] == "qa-technical"
             and request["reviewer_thread_id"] == plan["reviewer_thread_id"]
             and all(p in request["minimum_review_sources"] for p in source_pins), "exact_technical_request_required")
    _require(plan["reviewer_department"] == "qa-technical" and plan["candidate"] == dep["candidate"], "unique_technical_reviewer_required")
    snapshot = w.read_json(w.snapshot_path(e.root, plan["task_id"]))
    _require(snapshot and q.load_plan(e.root, snapshot) == plan
             and snapshot["qa_review_plan"]["pin"] == dep["review_plan"], "current_technical_plan_binding_required")
    _require(w.department_registry(e.root) == departments, "technical_registry_binding_required")
    for role in (plan["producer_department"], "qa-technical", "operations"):
        _require(healthy(departments[role]["chat_binding"], verification_ttl_hours=26), "technical_registered_health_required")
    receipts, invalid = w._validate_receipt_chain(e.root, plan["task_id"])
    _require(not invalid and not w.validate_workflow_events(e.root, plan["task_id"]), "valid_technical_chain_required")
    _require(any(row.get("task_id") == plan["task_id"] for row in w.read_jsonl(e.root / w.WORKFLOW_EVENTS)),
             "actual_technical_workflow_events_required")
    _require(any(row.get("task_id") == plan["task_id"]
                 and row.get("details", {}).get("qa_review_plan_bound") == snapshot["qa_review_plan"]
                 for row in w.read_jsonl(e.root / w.WORKFLOW_EVENTS)), "actual_technical_plan_binding_event_required")
    boxes = [r for r in receipts if r.get("department") == "qa-technical" and r.get("receipt_type") == "outbox_received"]
    verdicts = [r for r in receipts if r.get("department") == "qa-technical" and r.get("receipt_type") == "qa_verdict"]
    _require(boxes and verdicts and boxes[-1]["receipt_id"] == dep["outbox_receipt_id"]
             and verdicts[-1]["receipt_id"] == dep["verdict_receipt_id"] and verdicts[-1]["verdict"] == "pass"
             and dep["outbox"] in boxes[-1]["evidence"] and dep["outbox"] in verdicts[-1]["evidence"],
             "current_technical_pass_receipts_required")
    verdict_index = receipts.index(verdicts[-1])
    _require(not any(r.get("department") == "qa-technical"
                     and r.get("receipt_type") in {"dispatch_sent", "dispatch_failed", "chat_ack", "outbox_received"}
                     for r in receipts[verdict_index + 1:]), "technical_result_superseded_by_new_review")
    q.validate_verdict(e.root, snapshot, receipts[:verdict_index], verdicts[-1])
    box = e.json(dep["outbox"])
    _require(box["schema_version"] == "2.0" and box["status"] == "completed" and box["qa_verdict"] == "pass"
             and box["review_identity"] == expected and all(box[k] == plan[k] for k in IDENTITY[:-1]),
             "exact_technical_qa2_pass_required")
    for value in [dep["candidate"], dep["review_plan"], dep["technical_request"], rule["packet"]] + source_pins:
        _require(value in box["evidence"], "technical_qa2_evidence_binding_required")
    reply = _native_reply(e, dep["native_observation"])
    _match_reply(box, reply, plan["reviewer_thread_id"])
    _require(dep["request_payload"] in box["evidence"], "technical_request_payload_evidence_required")
    dispatches = [r for r in receipts if r.get("department") == "qa-technical"
                  and r.get("receipt_type") in {"dispatch_sent", "dispatch_failed"}]
    _require(dispatches and dispatches[-1]["receipt_type"] == "dispatch_sent"
             and dep["request_payload"] in dispatches[-1]["evidence"]
             and dep["technical_request"] in dispatches[-1]["evidence"], "technical_native_dispatch_payload_required")
    observed_request = _native_request(e, dep["native_request"], reply, dep["request_payload"])
    if isinstance(observed_request, _DelegationRequest):
        _bind_delegation_dispatch(e, dep["native_request"], observed_request, dispatches[-1], plan, w, receipts)


def _final_successor(e, rule, pack, dep, departments, healthy):
    """Consume a separately authorized R0 carrier; never rename it to the Logo business."""
    import qa_review_plan as q
    w = q._workflow()
    _require(dep["proof_format"] == "logo_final_successor.v1" and departments is not None and healthy is not None,
             "final_successor_consumer_context_required")
    _require(dep["logo_packet"] == rule["packet"] and dep["technical_qa2"] == rule["technical_qa2"]
             and dep["logo_packet"] != HISTORICAL_LOGO_PACKET_PIN, "current_final_successor_dependencies_required")
    old_packet = e.json(HISTORICAL_LOGO_PACKET_PIN)
    _require(old_packet["original_task_id"] == TASK and old_packet["candidate_version"] == VERSION
             and old_packet["owner_authorization"] == pack["owner_authorization"]
             and old_packet["logo_candidate"] == pack["logo_candidate"], "original_logo_leaf_bindings_required")
    for value in (HISTORICAL_REVIEW_ATTEMPT_PIN, HISTORICAL_REVIEW_SEND_PIN): e.pin(value)
    business = {"task_id": TASK, "action_id": ACTIONS["associate"][1], "action_class": ACTIONS["associate"][0],
                "scope": LOGO_SCOPE, "candidate_version": VERSION, "candidate_sha256": pack["logo_candidate"]["sha256"]}
    source = {"business_identity": business, "original_logo_packet": HISTORICAL_LOGO_PACKET_PIN,
              "logo_candidate": pack["logo_candidate"], "owner_authorization": pack["owner_authorization"],
              "historical_final_qa": HISTORICAL_QA1_BLOCKED_PIN, "historical_review_attempt": HISTORICAL_REVIEW_ATTEMPT_PIN,
              "historical_review_send": HISTORICAL_REVIEW_SEND_PIN, "account_id": "example-ads-account",
              "campaign_ids": CAMPAIGNS, "asset_id": ASSET, "association_level": "CAMPAIGN_ONLY",
              "unchanged": UNCHANGED, "owner_expires_at": "2026-10-14T14:00:00Z"}
    carrier, plan, request = [e.json(dep[k]) for k in ("carrier", "review_plan", "final_request")]
    identity = {key: plan[key] for key in IDENTITY}
    _require(type(carrier["schema_version"]) is int and carrier["schema_version"] == 1
             and carrier["kind"] == "owner_paid_logo.final_review_carrier.v1"
             and carrier["task_id"] != TASK and carrier["candidate_version"] != VERSION
             and carrier["action_id"] not in {ACTIONS["review"][1], ACTIONS["associate"][1]}
             and carrier["action_class"] in q.R0_CLASSES and carrier["department"] == "operations-assistant"
             and all(carrier[k] == plan[k] for k in IDENTITY[:-1])
             and dep["carrier"] == plan["candidate"] and dep["carrier"]["sha256"] == plan["candidate_sha256"]
             and dep["review_identity"] == identity, "exact_new_final_carrier_identity_required")
    _require(plan["reviewer_department"] == "qa" and plan["reviewer_thread_id"] == QA
             and plan["controller_department"] == "operations" and plan["controller_thread_id"] == HEADQUARTERS,
             "fixed_final_successor_reviewer_required")
    _require(type(request["schema_version"]) is int and request["schema_version"] == 1
             and request["kind"] == "owner_paid_logo.final_review_request.v1"
             and request["carrier"] == dep["carrier"] and request["review_plan"] == dep["review_plan"]
             and request["review_identity"] == identity and request["request_payload"] == dep["request_payload"]
             and request["reviewer_department"] == "qa" and request["reviewer_thread_id"] == QA,
             "exact_final_successor_request_required")
    for value in (carrier, request):
        _require(value["source_refs"] == source and value["logo_packet"] == rule["packet"]
                 and value["technical_qa2"] == rule["technical_qa2"], "exact_final_successor_source_refs_required")
    _require(dep["request_payload"] != pack["actions"]["review"]["payload"]
             and dep["request_payload"]["sha256"] != pack["actions"]["review"]["payload"]["sha256"],
             "consumed_original_review_payload_cannot_be_successor")
    e.pin(dep["request_payload"])
    # Source-only PASS is insufficient: this current source-and-packet dependency is independently checked.
    _technical_qa2(e, rule, pack, departments, healthy)
    snapshot = w.read_json(w.snapshot_path(e.root, plan["task_id"]))
    _require(snapshot and q.load_plan(e.root, snapshot) == plan
             and snapshot["qa_review_plan"]["pin"] == dep["review_plan"], "current_final_successor_plan_required")
    _require(w.department_registry(e.root) == departments, "final_successor_registry_required")
    for role in (plan["producer_department"], "qa", "operations"):
        _require(healthy(departments[role]["chat_binding"], verification_ttl_hours=26), "final_successor_registered_health_required")
    receipts, invalid = w._validate_receipt_chain(e.root, plan["task_id"])
    _require(not invalid and not w.validate_workflow_events(e.root, plan["task_id"]), "valid_final_successor_chain_required")
    _require(any(row.get("task_id") == plan["task_id"]
                 and row.get("details", {}).get("qa_review_plan_bound") == snapshot["qa_review_plan"]
                 for row in w.read_jsonl(e.root / w.WORKFLOW_EVENTS)), "actual_final_successor_plan_event_required")
    attempts = [r for r in receipts if r.get("department") == "qa"
                and r.get("receipt_type") in {"dispatch_sent", "dispatch_failed"}]
    _require(len(attempts) == 1 and attempts[0]["receipt_type"] == "dispatch_sent", "final_successor_single_dispatch_required")
    dispatch = attempts[0]
    for value in (dep["carrier"], dep["review_plan"], dep["final_request"], dep["request_payload"], rule["packet"]):
        _require(value in dispatch["evidence"], "final_successor_dispatch_inputs_required")
    boxes = [r for r in receipts if r.get("department") == "qa" and r.get("receipt_type") == "outbox_received"]
    verdicts = [r for r in receipts if r.get("department") == "qa" and r.get("receipt_type") == "qa_verdict"]
    _require(len(boxes) == len(verdicts) == 1 and boxes[0]["receipt_id"] == dep["outbox_receipt_id"]
             and verdicts[0]["receipt_id"] == dep["verdict_receipt_id"] and verdicts[0]["verdict"] == "pass"
             and dep["outbox"] in boxes[0]["evidence"] and dep["outbox"] in verdicts[0]["evidence"],
             "current_final_successor_pass_receipts_required")
    verdict_index = receipts.index(verdicts[0])
    _require(not any(r.get("department") == "qa" and r.get("receipt_type") in {
        "dispatch_sent", "dispatch_failed", "chat_ack", "outbox_received", "qa_verdict"}
        for r in receipts[verdict_index + 1:]), "final_successor_result_superseded")
    q.validate_verdict(e.root, snapshot, receipts[:verdict_index], verdicts[0])
    _require(e.pin(dep["proof"]) == e.path(pack["final_qa_proof_path"])
             and e.path(dep["proof"]["path"]) != e.path(HISTORICAL_QA1_BLOCKED_PIN["path"]),
             "new_final_successor_proof_path_required")
    proof, box = e.json(dep["proof"]), e.json(dep["outbox"])
    reply = _native_reply(e, dep["native_observation"])
    review = {"content_verdict": "pass", "association_verdict": "pass", "scope": LOGO_SCOPE}
    raw_result = {"schema_version": "owner-paid-logo-final-result/1", "review_identity": identity,
                  "source_refs": source, "logo_packet": rule["packet"], "technical_qa2": rule["technical_qa2"],
                  "logo_review": review, "qa_verdict": "pass", "result": "PASS", "risk_level": "R0",
                  "production_write_allowed": False, "external_permission_issued": False,
                  "production_release_eligible": False}
    def unique_object(pairs):
        _require(len(pairs) == len({key for key, _ in pairs}), "duplicate_native_final_result_field")
        return dict(pairs)
    native_result = json.loads(reply.text, object_pairs_hook=unique_object)
    _require(reply.namespace == "app.agentMessage" and native_result == raw_result
             and all(native_result[k] is False for k in ("production_write_allowed", "external_permission_issued", "production_release_eligible")),
             "native_final_successor_result_must_itself_pass_exact_logo_review")
    _require(proof["schema_version"] == "owner-paid-logo-final-proof/1" and proof["result"] == "PASS"
             and box["schema_version"] == "2.0" and box["status"] == "completed", "final_successor_proof_format_required")
    for value in (proof, box):
        _require(all(value[k] == plan[k] for k in IDENTITY) and value["department"] == "qa"
                 and value["fixed_chat_task_id"] == QA and value["qa_verdict"] == "pass"
                 and value["source_refs"] == source and value["logo_packet"] == rule["packet"]
                 and value["technical_qa2"] == rule["technical_qa2"]
                 and value["logo_review"] == review and value["risk_level"] == "R0"
                 and all(value[k] is False for k in ("production_write_allowed", "external_permission_issued", "production_release_eligible"))
                 and value["chat_reply"]["namespace"] == reply.namespace,
                 "exact_final_successor_result_and_logo_pass_required")
        _match_reply(value, reply, QA)
    _require(dep["native_request"]["format"] == TOOL_REQUEST_FORMAT, "actual_final_successor_tool_request_required")
    observed = _native_request(e, dep["native_request"], reply, dep["request_payload"])
    decision = _bind_delegation_dispatch(e, dep["native_request"], observed, dispatch, plan, w, receipts)
    _require(dep["native_ack"]["format"] == "read_thread.turn.v1"
             and dep["native_ack"]["pin"] == dep["native_request"]["pin"], "actual_final_successor_ack_turn_required")
    ack = _native_reply(e, dep["native_ack"])
    _require(ack.thread_id == QA and ack.turn_id == reply.turn_id and ack.message_id != reply.message_id,
             "distinct_actual_final_successor_ack_required")
    native_items = e.json(dep["native_ack"]["pin"])["turn"]["items"]
    final_items = [(i, m) for i, m in enumerate(native_items) if m.get("id") == reply.message_id]
    ack_indices = [i for i, m in enumerate(native_items) if m.get("id") == ack.message_id]
    tool_indices = [i for i, m in enumerate(native_items) if m.get("id") == observed.tool_output_id]
    _require(len(final_items) == len(ack_indices) == len(tool_indices) == 1
             and final_items[0][1]["type"] == "agentMessage" and final_items[0][1]["text"] == reply.text
             and tool_indices[0] < ack_indices[0] < final_items[0][0], "actual_final_successor_ack_result_order_required")
    ack_receipts = [r for r in receipts if r.get("department") == "qa" and r.get("receipt_type") == "chat_ack"]
    _require(len(ack_receipts) == 1 and ack_receipts[0]["receipt_id"] == dep["ack_receipt_id"]
             and ack_receipts[0]["ack_nonempty"] is True and dep["native_ack"]["pin"] in ack_receipts[0]["evidence"],
             "actual_final_successor_ack_receipt_required")
    _require(carrier["attempt_path"] == dep["attempt"]["path"]
             and carrier["attempt_path"] not in {HISTORICAL_REVIEW_ATTEMPT_PATH,
                 pack["actions"]["review"]["attempt_path"], pack["actions"]["associate"]["attempt_path"]},
             "distinct_final_successor_attempt_path_required")
    attempt = e.json(dep["attempt"])
    _require(dep["attempt_format"] == "codex_app.send_message_to_thread.attempt.v1"
             and attempt["task_id"] == plan["task_id"] and attempt["action_id"] == plan["action_id"]
             and attempt["policy_decision_id"] == dispatch["policy_decision_id"]
             and attempt["target_thread_id"] == QA and attempt["payload_sha256"] == dep["request_payload"]["sha256"]
             and attempt["status"] == "native_send_started_not_yet_claimed_success",
             "exact_final_successor_attempt_required")
    attempt_time = w._parse_observed_at(attempt["started_at"])
    _require(attempt_time is not None and w._parse_observed_at(decision["checked_at"]) <= attempt_time <= observed.created_at,
             "current_final_successor_attempt_time_required")
    for value in (dep["carrier"], dep["review_plan"], dep["final_request"], dep["request_payload"],
                  rule["packet"], rule["technical_qa2"], dep["attempt"]):
        _require(value in box["evidence"], "final_successor_result_inputs_required")
    e.pin(dep["report"])


def _final_qa(e, rule, pack, departments=None, healthy=None):
    # The original blocked decision is immutable even if future input pins change.
    historical = e.json(HISTORICAL_QA1_BLOCKED_PIN)
    _require(historical["qa_verdict"] == "blocked", "historical_logo_qa_blocked_must_be_preserved")
    dep = e.json(rule["final_qa_evidence"])
    if dep.get("kind") == "owner_paid_logo.final_successor.v1":
        _require(type(dep["schema_version"]) is int and dep["schema_version"] == 1, "final_successor_contract_version_required")
        _final_successor(e, rule, pack, dep, departments, healthy)
        return
    _require(type(dep["schema_version"]) is int and dep["schema_version"] == 1
             and dep["kind"] == "owner_paid_logo.final_qa_evidence.v1",
             "final_qa_evidence_contract_required")
    _require(e.pin(dep["proof"]) == e.path(pack["final_qa_proof_path"]), "exact_final_proof_path_required")
    _require(e.path(dep["proof"]["path"]) != e.path(HISTORICAL_QA1_BLOCKED_PIN["path"]),
             "historical_logo_qa_blocked_requires_new_authorized_successor")
    proof = e.json(dep["proof"])
    box = e.json(dep["outbox"])
    reply = _native_reply(e, dep["native_observation"])
    fmt = dep["proof_format"]
    if fmt == "legacy_wrapper.v1":
        _require(proof["source_method"] == "mcp__codex_app__read_thread"
                 and proof["outbox"] == dep["outbox"] and proof["report"] == dep["report"]
                 and proof["native_turn"] == dep["native_observation"]["pin"]
                 and proof["message_id"] == reply.message_id, "legacy_final_proof_binding_required")
        _require(dep["native_observation"]["format"] == "read_thread.turn.v1"
                 and e.pin(pack["actions"]["review"]["payload"]).read_text(encoding="utf-8") in reply.request_texts,
                 "qa_turn_must_follow_exact_request")
        _match_reply(box, reply, QA, legacy=True)
    elif fmt == "logo_result.v1":
        cls, action, _, _ = ACTIONS["associate"]
        for value in (proof, box):
            _require(value["task_id"] == TASK and value["department"] == "qa"
                     and value["fixed_chat_task_id"] == QA and value["candidate_version"] == VERSION
                     and value["candidate_sha256"] == pack["logo_candidate"]["sha256"]
                     and value["action_id"] == action and value["action_class"] == cls and value["scope"] == LOGO_SCOPE,
                     "exact_logo_result_identity_required")
        _require(proof["schema_version"] == "flashcast-qa-proof/1" and proof["result"] == "PASS"
                 and proof["qa_verdict"] == "pass" and box["schema_version"] == "department-outbox/2"
                 and box["status"] == "completed", "final_logo_result_pass_required")
        _require(proof["chat_reply"]["message_id"] == reply.message_id
                 and proof["chat_reply"]["turn_id"] == reply.turn_id
                 and proof["chat_reply"]["sha256"] == reply.sha256, "final_logo_proof_reply_required")
        _match_reply(box, reply, QA)
        _require(pack["actions"]["review"]["payload"] in box["evidence"]
                 and rule["packet"] in proof["frozen_inputs_verified"], "exact_final_request_and_packet_required")
        _require(dep["native_request"]["format"] != TOOL_REQUEST_FORMAT, "final_logo_successor_tool_contract_not_admitted")
        _native_request(e, dep["native_request"], reply, pack["actions"]["review"]["payload"])
    else:
        raise ValueError("unsupported_final_qa_proof_format")
    _require(box["task_id"] == TASK and box["department"] == "qa" and box["qa_verdict"] == "pass"
             and box["candidate_version"] == VERSION, "exact_independent_logo_qa_pass_required")
    _require(rule["packet"] in box["evidence"], "qa_must_bind_frozen_logo_packet")
    e.pin(dep["report"])


def check(root: Path, policy: dict, departments: dict, request: dict, healthy) -> list[str]:
    raise ValueError("public_template_has_no_native_authorization")
    raise ValueError("public_template_has_no_native_authorization")
    evidence = _Evidence(root)
    require, path, pin, json_pin = _require, evidence.path, evidence.pin, evidence.json
    try:
        require(str(root.resolve()) == ROOT, "project_root_required")
        require(policy["routing_policy"]["source_project_id"] == PROJECT
                and policy["routing_policy"]["source_project_root"] == ROOT, "project_binding_required")
        key = request["scope"].removeprefix(PREFIX)
        require(request["scope"].startswith(PREFIX) and key in ACTIONS, "exact_action_required")
        cls, aid, dept, tid = ACTIONS[key]
        require(request["task_id"] == TASK and request["department"] == "paid-growth-data"
                and request["action_class"] == cls and request["action_id"] == aid,
                "exact_action_tuple_required")
        require(request.get("skill") == "google-ads-renovation-ppc", "approved_skill_required")
        require(departments["paid-growth-data"]["approved_subskills"] == ["google-ads-renovation-ppc"],
                "registered_skill_required")
        rule = policy["owner_paid_logo_v1"]
        require(rule["status"] == "owner_approved_exact_logo_channel"
                and rule["global_paid_gate_unchanged"] is True
                and rule["unrelated_ads_or_payment_authority"] is False, "exact_logo_rule_required")
        pack = json_pin(rule["packet"])
        require(pack["original_task_id"] == TASK and pack["candidate_version"] == VERSION
                and pack["account_id"] == "example-ads-account" and pack["campaign_ids"] == CAMPAIGNS
                and pack["asset_id"] == ASSET and pack["association_level"] == "CAMPAIGN_ONLY"
                and pack["unchanged"] == UNCHANGED, "exact_logo_scope_required")
        for value in pack["frozen_inputs"]:
            pin(value)
        candidate = json_pin(pack["logo_candidate"])
        require(candidate["task_id"] == TASK and candidate["scope"] == LOGO_SCOPE
                and [t["id"] for t in candidate["targets"]] == CAMPAIGNS
                and candidate["asset"]["id"] == ASSET and candidate["asset"]["dimensions"] == "512x512"
                and candidate["association_level"] == "CAMPAIGN_ONLY"
                and candidate["unchanged"] == UNCHANGED, "frozen_logo_candidate_required")
        auth = json_pin(pack["owner_authorization"])
        require(auth["source_thread_id"] == SOURCE and auth["source_method"] == "mcp__codex_app__read_thread"
                and auth["turn_id"] == AUTH_TURN, "native_owner_source_required")
        message = auth["message"]
        body = message["content"][0]["text"]
        require(message["id"] == AUTH_MESSAGE and message["type"] == "userMessage"
                and "仅两套新系列Logo关联" in body
                and "FLASH CAST｜质检与Reality Checker部｜2026-09" in body
                and body.strip().endswith("批准执行"), "native_exact_logo_approval_required")
        now = dt.datetime.now(dt.timezone.utc)
        require(now <= dt.datetime(2026, 10, 14, 14, tzinfo=dt.timezone.utc), "approval_window_expired")
        live = json.loads(path(pack["live_identity_path"]).read_text())
        observed = dt.datetime.fromisoformat(live["observed_at"].replace("Z", "+00:00"))
        require(observed.tzinfo is not None and 0 <= (now - observed).total_seconds() <= 300,
                "fresh_native_identity_required")
        require(live["source_method"] == "mcp__codex_app__list_threads", "native_identity_source_required")
        sections = [s for s in live["sections"] if s["name"] == "装修公司部门"]
        require(len(sections) == 1, "unique_native_section_required")
        threads = {t["id"]: t for t in live["threads"]}
        for did, thread_id in [("paid-growth-data", SOURCE), ("qa", QA)]:
            require(sum(t["id"] == thread_id for t in live["threads"]) == 1, "unique_native_thread_required")
            binding = departments[did]["chat_binding"]
            require(healthy(binding, verification_ttl_hours=26), "registered_health_required")
            require(binding["task_id"] == thread_id and binding["project_id"] == PROJECT
                    and binding["cwd"] == ROOT, "registered_identity_required")
            t = threads[thread_id]
            require(t["projectId"] == PROJECT and t["cwd"] == ROOT and t["title"] == binding["title"]
                    and "codex:thread:local:" + thread_id in sections[0]["itemKeys"], "native_identity_required")
        require(request["source_project_id"] == PROJECT and request["target_project_id"] == PROJECT
                and request["target_department"] == dept and request["target_thread_id"] == tid
                and request["target_thread_title"] == threads[tid]["title"]
                and request["target_cwd"] == ROOT
                and request["target_sidebar_section_id"] == sections[0]["sectionId"], "native_target_tuple_required")
        action = pack["actions"][key]
        payload = pin(action["payload"])
        require(request["payload_sha256"] == action["payload"]["sha256"], "exact_payload_required")
        require(not path(action["attempt_path"]).exists(), "single_use_attempt_already_recorded")
        if key == "review":
            require(not path(HISTORICAL_REVIEW_ATTEMPT_PATH).exists(), "single_use_attempt_already_recorded")
            require(threads[QA]["status"] == "idle", "fixed_qa_must_be_idle")
        else:
            require(request["consume_approval"] is True, "consume_exact_logo_permit_required")
            require(json.loads(payload.read_text()) == {
                "action": "associate_existing_business_logo", "account_id": "example-ads-account",
                "campaign_ids": CAMPAIGNS, "asset_id": ASSET, "association_level": "CAMPAIGN_ONLY",
                "unchanged": UNCHANGED}, "logo_association_only_payload_required")
            _technical_qa2(evidence, rule, pack, departments, healthy)
            _final_qa(evidence, rule, pack, departments, healthy)
        return []
    except (KeyError, ValueError, TypeError, OSError, IndexError, AttributeError, RuntimeError, ImportError) as exc:
        return ["owner_paid_logo_denied:" + str(exc)]
