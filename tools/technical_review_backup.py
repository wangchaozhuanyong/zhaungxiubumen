"""Bounded technical backup eligibility; no route, lease or permission writes."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
import sqlite3

PRIMARY_METHOD = "web-dev-toolkit:code-reviewer"

SELECTION_FIELD = "qualified_assistant_selection"
SELECTION_SCHEMA = "flashcast-qualified-initial-review/v1"
NATIVE_SELECTION_SCHEMA = "flashcast-qualified-assistant-goal/v1"
SELECTION_PROOF_FIELDS = {"schema", "task_id", "reviewer", "producer", "scope", "goal_identity", "authorization_pin",
    "method_adoption", "hq_native_selection", "hq_selection_input", "hq_turn_id", "hq_message_id"}
QUALIFIED_ROLE = "operations-assistant-3"
QUALIFIED_PRODUCER = "system-development"
METHOD_ADOPTION_TASK = "fc-20261010-system-flow-throughput-and-ledger-close-v1"
METHOD_ADOPTION_VERSION = "system-flow-throughput-ledger-cleanup-v4"
METHOD_ADOPTION_SCOPE = "project:flashcast:system-flow-throughput-ledger-cleanup:v1"
# Permanent, independently accepted CAS provenance for the already installed
# method. This is not a newly added registry flag or a new capability grant.
METHOD_ADOPTION = {
    "candidate_manifest": {
        "path": "logs/handoffs/2026-10-10-system-remaining-execution-v1/system-development/rework-parent-linked-child-review-source-v4/candidate-manifest.json",
        "sha256": "53c7065761fe62a2f4a4932b2e1518924e614b8ad21221f724f44cfe8bed229f", "size": 25737},
    "independent_review": {
        "path": "logs/handoffs/2026-10-10-system-remaining-execution-v1/assistant2/F4-independent-candidate-scope-PASS-v4.json",
        "sha256": "1e672361e4d226b16aefb03e4a969125a13f21e28199f52195c02a97bd2122bc", "size": 3313},
    "adoption_journal": {
        "path": "backups/fc-20261010-system-flow-throughput-and-ledger-close-v1/e62c2c44-e6e4-4e13-9117-4899b481e52b/journal.json",
        "sha256": "1fe31a5e5a69058907f5cfc876bdccde4b2078dc04263adce7fa38699f0307ac", "size": 15574},
}
GOAL_IDENTITY_FIELDS = ("objective", "completion_criteria", "primary_owner", "responsible_assistant",
    "existing_results", "authorized_scope", "dependencies", "producer_departments", "acceptance_capability",
    "human_authorization", "source_mode", "parent_task_id", "required_execution_actions", "collaboration_scopes")


def qualified_goal_identity(goal):
    """Non-self-referential complete contract carried by the native HQ selection."""
    defaults = {"source_mode": "approved_dispatch", "parent_task_id": None,
                "required_execution_actions": [], "collaboration_scopes": []}
    return {key: goal.get(key, defaults.get(key)) for key in GOAL_IDENTITY_FIELDS}


def _pinned_document(root, pin):
    import workflow_control as w
    if not isinstance(pin, dict) or w.file_digest(root, pin.get("path", "")) != pin:
        raise w.WorkflowError("qualified reviewer frozen source changed")
    value = w.read_json(w.safe_path(root, pin["path"]))
    if not isinstance(value, dict):
        raise w.WorkflowError("qualified reviewer object source required")
    return value


def _adopted_methods(root, item, config, proof):
    """Recheck the exact permanent method subset, never all obsolete F4 sources."""
    import workflow_control as w
    import scoped_candidate_adoption as adopted
    if proof != METHOD_ADOPTION:
        return False
    manifest = _pinned_document(root, proof["candidate_manifest"])
    review = _pinned_document(root, proof["independent_review"])
    journal = _pinned_document(root, proof["adoption_journal"])
    identity = {"task_id": METHOD_ADOPTION_TASK, "candidate_version": METHOD_ADOPTION_VERSION,
                "scope": METHOD_ADOPTION_SCOPE}
    fingerprint = adopted._hash({key: manifest.get(key) for key in ("task_id", "scope", "changes", "field_changes")})
    if (any(any(value.get(key) != expected for key, expected in identity.items())
            for value in (manifest, review, journal))
            or any(value.get("candidate_fingerprint") != fingerprint for value in (manifest, review, journal))
            or review.get("reviewer") != "operations-assistant-2"
            or review.get("producer_department") != QUALIFIED_PRODUCER
            or review.get("acceptance_capability") != "development"
            or review.get("phase") != "candidate_source_only"
            or review.get("verdict") != "PASS_CANDIDATE_SCOPE_ONLY"
            or any(review.get(key) is not False for key in ("goal_completion_claimed", "final_goal_verdict", "pilot_complete"))
            or review.get("candidate_manifest") != proof["candidate_manifest"]
            or journal.get("actor") != "operations-assistant-2" or journal.get("state") != "adopted"
            or journal.get("external_writes") != 0 or journal.get("permissions_issued") is not False
            or journal.get("independent_review") != proof["independent_review"]
            or journal.get("authorized_source") != review.get("human_authorization")):
        return False
    for key in ("human_authorization", "goal_contract", "producer_outbox", "review_plan"):
        adopted._pin(root, review.get(key))
    outbox = _pinned_document(root, journal.get("review_outbox"))
    # The original independently accepted native carrier is immutable. Inspect
    # only its selected A2 message; no claim/token fields are consumed here.
    before = _pinned_document(root, journal.get("registry_before"))
    after = _pinned_document(root, journal.get("registry_after"))
    original_binding = next(row for row in after["departments"] if row.get("id") == "operations-assistant-2")["chat_binding"]
    from goal_delivery_runtime import _collaboration_native
    document = _collaboration_native(root, outbox.get("actual_native_reply"))
    reply_pin = adopted._pin(root, outbox.get("visible_reply"))
    raw_reply = w.safe_path(root, reply_pin["path"]).read_bytes()
    selected = [(turn, msg) for turn in document.get("turns", []) if turn.get("id") == outbox.get("source_turn_id")
                for msg in turn.get("items", []) if msg.get("type") == "agentMessage"
                and msg.get("id") == outbox.get("source_message_id")]
    if (len(selected) != 1 or document.get("thread", {}).get("id") != original_binding.get("task_id")
            or document.get("thread", {}).get("cwd") != original_binding.get("cwd")
            or outbox.get("department") != "operations-assistant-2"
            or outbox.get("task_id") != METHOD_ADOPTION_TASK or outbox.get("candidate_version") != METHOD_ADOPTION_VERSION
            or outbox.get("fixed_chat_task_id") != original_binding.get("task_id")
            or outbox.get("chat_reply", {}).get("nonempty") is not True
            or outbox.get("chat_reply", {}).get("in_current_fixed_department_chat") is not True
            or outbox.get("source_reply_sha256") != reply_pin["sha256"]
            or proof["independent_review"] not in list(__import__("qa_review_plan")._evidence_pins(outbox.get("evidence", [])))):
        return False
    turn, message = selected[0]
    observed = w._parse_observed_at(outbox.get("reply_observed_at"))
    started, completed = w._parse_observed_at(journal.get("started_at")), w._parse_observed_at(journal.get("completed_at"))
    native_started = turn.get("startedAt")
    if (turn.get("status") not in {"inProgress", "completed"} or turn.get("error")
            or type(native_started) not in {int, float} or native_started <= 0
            or message.get("phase") not in {"commentary", "final_answer"}
            or not isinstance(message.get("text"), str) or not message["text"].strip()
            or message["text"].encode("utf-8") != raw_reply
            or observed is None or started is None or completed is None
            or not native_started <= observed.timestamp() <= started.timestamp() <= completed.timestamp()
            <= w.dt.datetime.now(w.dt.timezone.utc).timestamp()):
        return False
    original_item = next(row for row in after["departments"] if row.get("id") == QUALIFIED_ROLE)
    previous_item = next(row for row in before["departments"] if row.get("id") == QUALIFIED_ROLE)
    fields = {"approved_subskills", "approved_subskill_paths", "coordination_authority"}
    operations = journal.get("field_operations", [])
    if (len(operations) != len(fields) or {operation.get("field") for operation in operations} != fields
            or any(operation.get("department_id") != QUALIFIED_ROLE
                   or operation.get("before") != previous_item.get(operation["field"])
                   or operation.get("after") != original_item.get(operation["field"])
                   or item.get(operation["field"]) != operation.get("after") for operation in operations)):
        return False
    for path in (item["professional_skill"], config["method_manifest"]["path"]):
        entries = [entry for entry in manifest["changes"] if entry.get("path") == path]
        operations = [entry for entry in journal["source_operations"] if entry.get("path") == path]
        if len(entries) != 1 or len(operations) != 1:
            return False
        entry, operation = entries[0], operations[0]
        adopted._pin(root, entry["candidate"])
        adopted._pin(root, entry["diff"])
        current = w.file_digest(root, path)
        if ({key: current[key] for key in ("sha256", "size")} != {key: entry["candidate"][key] for key in ("sha256", "size")}
                or operation.get("after_sha256") != current["sha256"]):
            return False
        expected = entry["expected_source"]
        if expected == "ABSENT":
            if entry.get("baseline") is not None or operation.get("before_sha256") != "ABSENT" or operation.get("backup") is not None:
                return False
        else:
            adopted._pin(root, entry["baseline"])
            adopted._pin(root, operation.get("backup"))
            if (operation.get("before_sha256") != expected.get("sha256")
                    or {key: operation["backup"][key] for key in ("sha256", "size")} != expected):
                return False
    return True


def _qualified_binding(root, role, project):
    import workflow_control as w
    item = w.department_registry(root).get(role, {})
    binding = item.get("chat_binding", {})
    return bool(item.get("new_dispatch_enabled") is not False
        and w._chat_binding_healthy(binding)
        and all(isinstance(binding.get(key), str) and binding[key].strip() for key in ("task_id", "title", "project_id", "cwd"))
        and binding["project_id"] == project
        and w._same_resolved_path(binding["cwd"], str(Path(root).resolve())))


def _qualified_responsibility(root, role, goal, task_id):
    """Actual ordinary HQ policy/send/ACK, read only after initial registration."""
    import workflow_control as w
    from goal_delivery_runtime import _collaboration_native
    snapshot = w.read_json(w.snapshot_path(root, task_id))
    contract_pin = snapshot.get("goal_contract")
    contract = _pinned_document(root, contract_pin)
    if (snapshot.get("task_id") != task_id or qualified_goal_identity(contract) != qualified_goal_identity(goal)
            or contract.get(SELECTION_FIELD) != goal.get(SELECTION_FIELD)
            or snapshot.get("goal_delivery") != goal or goal.get("assignment_history")
            or not any(row.get("department") == role and row.get("chat_task_id") == w.department_registry(root)[role]["chat_binding"]["task_id"]
                       for row in snapshot.get("departments", []))):
        return False
    events = []
    previous = ""
    for line in (Path(root) / w.WORKFLOW_EVENTS).read_text(encoding="utf-8").splitlines():
        event = json.loads(line)
        if (not isinstance(event, dict) or event.get("previous_event_hash", "") != previous
                or event.get("event_hash") != w.sha256_value({key: value for key, value in event.items() if key != "event_hash"})):
            return False
        previous = event["event_hash"]
        if event.get("task_id") == task_id:
            events.append(event)
    if not any(event.get("details", {}).get("goal_contract") == contract_pin for event in events):
        return False
    rows, previous = [], ""
    for line in w.receipts_path(root, task_id).read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if (not isinstance(row, dict) or row.get("task_id") != task_id or row.get("previous_hash") != previous
                or row.get("receipt_hash") != w.sha256_value(w._receipt_payload_for_hash(row))):
            return False
        previous = row["receipt_hash"]
        rows.append(row)
    binding = w.department_registry(root)[role]["chat_binding"]
    hq = w.department_registry(root)["operations"]["chat_binding"]
    action, scope = "assign-goal-review:" + task_id, goal["authorized_scope"][0]
    dispatches = [(i, row) for i, row in enumerate(rows) if row.get("receipt_type") == "dispatch_sent"
                  and row.get("department") == role and row.get("chat_task_id") == binding["task_id"]
                  and row.get("action_id") == action and row.get("scope") == scope]
    if len(dispatches) != 1:
        return False
    di, dispatch = dispatches[0]
    if (dispatch.get("action_class") != "thread_message"
            or any(row.get("supersedes_receipt_id") == dispatch["receipt_id"] for row in rows[di + 1:])):
        return False
    # Validate every pin in the original responsibility window before an
    # earlier valid proof can return. No receipt or frozen source is rewritten.
    def unique_fields(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise w.WorkflowError("ambiguous responsibility attachment fields")
            value[key] = item
        return value
    def invalid_constant(value):
        raise w.WorkflowError("legal responsibility attachment JSON required")
    def frozen_attachment(pin):
        if (not isinstance(pin, dict) or set(pin) != {"path", "sha256", "size"}
                or not isinstance(pin.get("path"), str) or not pin["path"]
                or not isinstance(pin.get("sha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", pin["sha256"])
                or type(pin.get("size")) is not int or pin["size"] < 0
                or w.file_digest(root, pin["path"]) != pin):
            raise w.WorkflowError("frozen responsibility attachment changed")
        document = json.loads(w.safe_path(root, pin["path"]).read_bytes(),
                              object_pairs_hook=unique_fields, parse_constant=invalid_constant)
        if not isinstance(document, dict):
            raise w.WorkflowError("responsibility attachment object required")
        return document
    acknowledgements = []
    for row in rows[di + 1:]:
        if row.get("department") != role:
            continue
        if row.get("receipt_type") in {"dispatch_sent", "dispatch_failed"}:
            break
        if row.get("receipt_type") == "chat_ack":
            acknowledgements.append(row)
    attachments = {w.canonical_json(pin): frozen_attachment(pin)
                   for row in [dispatch, *acknowledgements] for pin in row.get("evidence", [])}
    if contract_pin not in dispatch.get("evidence", []):
        # The exact recorded transport can pin the payload instead of repeating
        # its contract pin. Reuse only that strict envelope proof; the existing
        # direct-pin native responsibility path below remains unchanged.
        import qa_review_plan as q
        if (q._binding(root, snapshot) or {}).get("native_multi_goal_review") is not None:
            return False
        return (q._initial_assignment(root, snapshot, dispatch)
                and q._initial_assignment_envelope(root, snapshot, dispatch, contract_pin))
    policies = [row for row in w.read_jsonl(Path(root) / w.POLICY_DECISIONS) if row.get("decision_id") == dispatch.get("policy_decision_id")]
    expected = {"status": "allow", "routing_status": "routing_allowed", "task_id": task_id, "department": "operations",
        "action_class": "thread_message", "action_id": action, "scope": scope, "payload_sha256": contract_pin["sha256"],
        "target_department": role, "target_thread_id": binding["task_id"], "target_thread_title": binding["title"],
        "target_cwd": binding["cwd"], "target_project_id": binding["project_id"], "source_project_id": binding["project_id"],
        "target_sidebar_section_id": binding.get("sidebar_section_id")}
    if len(policies) != 1 or any(policies[0].get(key) != value for key, value in expected.items()):
        return False
    checked, registered = w._parse_observed_at(policies[0].get("checked_at")), w._parse_observed_at(dispatch.get("created_at"))
    if checked is None or registered is None or not checked <= registered <= w.dt.datetime.now(w.dt.timezone.utc):
        return False
    if any("native_send_result" in attachments[w.canonical_json(pin)] for pin in dispatch.get("evidence", [])):
        return _qualified_recorded_handoff(root, role, task_id, contract_pin, dispatch, rows[di + 1:],
                                            policies[0], binding, hq)
    sends = []
    for pin in dispatch.get("evidence", []):
        document = attachments[w.canonical_json(pin)]
        if pin == contract_pin:
            continue
        if any(key in document for key in ("content", "threadId", "native_send", "actual_send", "actual_native_send")):
            native = _collaboration_native(root, pin)
            if native.get("threadId") == binding["task_id"]:
                sends.append(native)
        else:
            raise w.WorkflowError("recognized native responsibility send attachment required")
    if len(sends) != 1:
        return False
    # These two exact old weekly summaries are observations, never native
    # authority. A changed, unknown, failed or malformed summary is not skipped.
    summaries = [
        {"path": "logs/handoffs/2026-10-10-weekly-safe-cleanup-native-enablement-v1/assistant2-independent-review/A2-original-weekly-complete-goal-native-incoming-and-nonempty-ACK-v1.json",
         "sha256": "8dac839c20bdb3cb73a5606ae3861700394370f81f282b1c5f41072bf9faf8ba", "size": 18136},
        {"path": "logs/handoffs/2026-10-10-weekly-safe-cleanup-native-enablement-v1/ready/HQ-responsibility-preparation-v1/HQ-A2-weekly-nonempty-ACK-local-source-proof-v1.json",
         "sha256": "ba89eb001acd744829c6c2f0fe158f38d7b8bfdb7d4915ef46adae9495c8ab1a", "size": 3478},
    ]
    native_acknowledgements = []
    for ack in acknowledgements:
        natives = []
        for pin in ack.get("evidence", []):
            if (task_id == "fc-20261010-weekly-safe-cleanup-native-enablement-v1"
                    and role == "operations-assistant-2" and pin in summaries):
                continue
            document = attachments[w.canonical_json(pin)]
            if (document.get("error") or ("truncated" in document and document["truncated"] is not False)):
                raise w.WorkflowError("intact successful native responsibility ACK attachment required")
            native = _collaboration_native(root, pin)
            if (not isinstance(native.get("thread"), dict) or not isinstance(native.get("turns"), list)
                    or not native["turns"] or any(not isinstance(turn, dict) for turn in native["turns"])
                    or any(turn.get("error") or ("truncated" in turn and turn["truncated"] is not False)
                           for turn in native["turns"])
                    or any(not isinstance(turn.get("items"), list)
                           or any(not isinstance(item, dict) for item in turn["items"]) for turn in native["turns"])
                    or any(item.get("type") == "functionCallOutput" and isinstance(item.get("output"), dict)
                           and (item["output"].get("truncated") is not False
                                or ("isError" in item["output"] and item["output"]["isError"] is not False))
                           for turn in native["turns"] for item in turn["items"])):
                raise w.WorkflowError("intact successful native responsibility ACK attachment required")
            natives.append((pin, native))
        native_acknowledgements.append((ack, natives))
    proven_sources, limited_sources = set(), []
    for ack, natives in native_acknowledgements:
        ack_at = w._parse_observed_at(ack.get("created_at"))
        if (ack.get("receipt_type") != "chat_ack" or ack.get("chat_task_id") != binding["task_id"]
                or ack.get("ack_nonempty") is not True or ack_at is None
                or ack.get("action_id") != action or ack.get("scope") != scope
                or ack.get("policy_decision_id") not in {"", dispatch.get("policy_decision_id")}
                or not registered <= ack_at <= w.dt.datetime.now(w.dt.timezone.utc)):
            return False
        for pin, native in natives:
            thread = native.get("thread", {})
            if (thread.get("id") != binding["task_id"] or thread.get("title") != binding["title"]
                    or thread.get("cwd") != binding["cwd"] or thread.get("projectId", binding["project_id"]) != binding["project_id"]):
                return False
            for turn in native.get("turns", []):
                start, items = turn.get("startedAt"), turn.get("items", [])
                if (not turn.get("id") or turn.get("status") not in {"inProgress", "completed"} or turn.get("error")
                        or type(start) not in {int, float} or not checked.timestamp() <= start <= ack_at.timestamp()
                        or ("turnId" in sends[0] and sends[0]["turnId"] != turn["id"])
                        or not isinstance(items, list) or not items or not isinstance(items[0], dict)):
                    return False
                incoming, output = items[0], items[0].get("output", {})
                if "output" not in incoming or output is None:
                    # One exact limited native read omits the incoming output.
                    # It must link every exposed responsibility field to the
                    # original complete source; that source must independently
                    # pass all unchanged native authority guards below.
                    if (task_id != "fc-20261010-weekly-safe-cleanup-native-enablement-v1"
                            or role != "operations-assistant-2" or pin != {
                                "path": "logs/handoffs/2026-10-10-weekly-safe-cleanup-native-enablement-v1/ready/HQ-responsibility-preparation-v1/HQ-A2-weekly-nonempty-ACK-ACTUAL-v1.json",
                                "sha256": "edeaa1c30b57eef1587fc85ca584494c0ebe5abb3abbe191f7f818f8c0514703", "size": 5211}):
                        return False
                    replies = [item for item in items if item.get("type") == "agentMessage"]
                    if (not replies or any(not item.get("id") or item.get("phase") not in {"commentary", "final_answer"}
                            or not isinstance(item.get("text"), str) or not item["text"].strip() for item in replies)):
                        return False
                    matches = []
                    for full_ack, full_natives in native_acknowledgements:
                        if full_ack.get("receipt_id") != "382fec13-afbd-4015-ad58-edcca2261153":
                            continue
                        for full_pin, full_native in full_natives:
                            if any(full_native["thread"].get(key) != thread[key]
                                   for key in ("id", "kind", "hostId", "title", "cwd", "projectId") if key in thread):
                                continue
                            for full_turn in full_native["turns"]:
                                full_items = full_turn["items"]
                                if (not full_items or any(full_turn.get(key) != value
                                        for key, value in turn.items() if key != "items")
                                        or not isinstance(full_items[0].get("output"), dict)
                                        or any(full_items[0].get(key) != value for key, value in incoming.items() if key != "output")
                                        or any(len([item for item in full_items if all(item.get(key) == value
                                                for key, value in reply.items())]) != 1 for reply in replies)):
                                    continue
                                matches.append(full_pin)
                    if len(matches) != 1:
                        return False
                    limited_sources.append(w.canonical_json(matches[0]))
                    continue
                if (incoming.get("type") != "functionCallOutput" or not incoming.get("id")
                        or incoming.get("name") != "send_message_to_thread" or incoming.get("namespace") != "codex_app"
                        or not isinstance(output, dict) or output.get("truncated") is not False or not isinstance(output.get("text"), str)):
                    return False
                wrapper = re.fullmatch(r"<codex_delegation>\s*<source_thread_id>([^<>]+)</source_thread_id>\s*<input>([\s\S]*)</input>\s*</codex_delegation>\s*", output["text"])
                if (wrapper and wrapper.group(1) == hq["task_id"]
                        and wrapper.group(2).encode("utf-8") == w.safe_path(root, contract_pin["path"]).read_bytes()
                        and any(item.get("type") == "agentMessage" and item.get("id")
                                and item.get("phase") in {"commentary", "final_answer"}
                                and isinstance(item.get("text"), str) and item["text"].strip()
                                for item in items if isinstance(item, dict))):
                    proven_sources.add(w.canonical_json(pin))
                else:
                    return False
    return bool(proven_sources) and all(pin in proven_sources for pin in limited_sources)


def _qualified_recorded_handoff(root, role, task_id, contract_pin, dispatch, later, policy, binding, hq):
    """Read one existing qualified HQ send and its original native session ACK.

    Only the recorded outer send format and platform-owned append-only session
    rows are supported. The exact original three row hashes are checked; a
    later whole-session hash is neither needed nor trusted. No source is made.
    """
    import workflow_control as w
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise w.WorkflowError("ambiguous qualified handoff source")
            result[key] = value
        return result
    def frozen(pin):
        _pinned_document(root, pin)
        return json.loads(w.safe_path(root, pin["path"]).read_bytes(), object_pairs_hook=unique)
    def native_result(value):
        if (not isinstance(value, dict) or set(value) != {"content", "isError"}
                or value["isError"] is not False or not isinstance(value["content"], list)
                or len(value["content"]) != 1 or not isinstance(value["content"][0], dict)
                or set(value["content"][0]) != {"type", "text"}
                or value["content"][0]["type"] != "text"
                or not isinstance(value["content"][0]["text"], str)):
            raise w.WorkflowError("exact successful qualified native result required")
        return json.loads(value["content"][0]["text"], object_pairs_hook=unique)
    if role != QUALIFIED_ROLE or not dispatch.get("receipt_id"):
        return False
    sends = [(pin, frozen(pin)) for pin in dispatch.get("evidence", [])
             if "native_send_result" in frozen(pin)]
    if len(sends) != 1:
        return False
    send_pin, send = sends[0]
    fields = {"task_id", "source_thread_id", "target_department", "target_thread_id", "action_id", "scope",
              "payload_sha256", "payload_size", "policy_decision_id", "policy_result", "native_send_result", "live_identity"}
    if (set(send) != fields or contract_pin not in dispatch.get("evidence", [])
            or any(send.get(key) != value for key, value in {
                "task_id": task_id, "source_thread_id": hq["task_id"], "target_department": role,
                "target_thread_id": binding["task_id"], "action_id": dispatch["action_id"],
                "scope": dispatch["scope"], "payload_sha256": contract_pin["sha256"],
                "payload_size": contract_pin["size"], "policy_decision_id": dispatch["policy_decision_id"]}.items())
            or native_result(send["native_send_result"]) != {"threadId": binding["task_id"]}):
        return False
    result = send["policy_result"]
    policy_fields = {"status", "task_id", "decision_id", "routing_status", "routing_quarantine_mode",
                     "routing_health_probe_mode", "source_project_id", "target_project_id", "target_department",
                     "target_thread_id", "target_thread_title", "target_cwd", "target_sidebar_section_id",
                     "payload_sha256", "department", "checked_at"}
    if (not isinstance(result, dict) or any(result.get(key) != policy.get(key) for key in policy_fields)
            or result.get("routing_quarantine_mode") is not False or result.get("routing_health_probe_mode") is not False):
        return False
    live = native_result(send["live_identity"])
    targets = [item for key in ("pinnedThreads", "threads") for item in live.get(key, [])
               if isinstance(item, dict) and item.get("id") == binding["task_id"]]
    if (live.get("schemaVersion") != 4 or len(targets) != 1
            or any(targets[0].get(key) != value for key, value in {
                "kind": "codex", "hostId": "local", "title": binding["title"],
                "cwd": binding["cwd"], "projectId": binding["project_id"]}.items())):
        return False
    observations = []
    for row in later:
        if row.get("department") != role:
            continue
        if row.get("receipt_type") in {"dispatch_sent", "dispatch_failed"}:
            break
        for pin in row.get("evidence", []) if row.get("receipt_type") == "chat_ack" else []:
            document = frozen(pin)
            if document.get("proof_kind") == "actual_native_nonempty_ack_local_session_observation":
                observations.append((row, document))
    if len(observations) != 1:
        return False
    ack, observed = observations[0]
    ack_fields = {"schema_version", "proof_kind", "task_id", "department", "fixed_chat_task_id", "new_turn_id",
                  "source_turn_id", "source_message_id", "ack_nonempty", "in_current_fixed_department_chat",
                  "is_candidate_result", "phase", "reply_text_utf8", "reply_sha256", "reply_size",
                  "message_timestamp", "observed_at", "native_reply", "local_session_source",
                  "actual_complete_goal_send", "control_boundary"}
    if (set(observed) != ack_fields
            or any(row.get("supersedes_receipt_id") == ack.get("receipt_id") for row in later)
            or ack.get("chat_task_id") != binding["task_id"] or ack.get("ack_nonempty") is not True
            or ack.get("action_id") != dispatch["action_id"] or ack.get("scope") != dispatch["scope"]
            or observed.get("schema_version") != 1 or observed.get("task_id") != task_id
            or observed.get("department") != role or observed.get("fixed_chat_task_id") != binding["task_id"]
            or observed.get("ack_nonempty") is not True or observed.get("in_current_fixed_department_chat") is not True
            or observed.get("is_candidate_result") is not False or observed.get("phase") not in {"commentary", "final_answer"}
            or not observed.get("new_turn_id") or observed.get("source_turn_id") != observed["new_turn_id"]
            or not observed.get("source_message_id")
            or observed.get("actual_complete_goal_send") != {
                "dispatch_receipt_id": dispatch["receipt_id"], "policy_decision_id": dispatch["policy_decision_id"],
                "action_id": dispatch["action_id"], "scope": dispatch["scope"],
                "goal_payload_sha256": contract_pin["sha256"], "goal_payload_size": contract_pin["size"], "evidence": send_pin}):
        return False
    source = observed.get("local_session_source", {})
    if (not isinstance(source, dict) or set(source) != {"path", "session_id", "cwd", "message_line",
            "message_row_sha256", "message_row_size", "task_started_line", "task_started_row_sha256",
            "turn_context_line", "turn_context_row_sha256"}):
        return False
    path = Path(source.get("path", ""))
    platform = Path.home() / ".codex" / "sessions"
    if (not path.is_absolute() or path.resolve() != path or path.is_symlink()
            or not path.is_relative_to(platform) or source.get("session_id") != binding["task_id"]
            or source.get("cwd") != binding["cwd"] or not w._same_resolved_path(binding["cwd"], str(root))):
        return False
    relative = path.relative_to(platform)
    if (len(relative.parts) != 4 or any(not re.fullmatch(pattern, part)
            for pattern, part in zip((r"[0-9]{4}", r"[0-9]{2}", r"[0-9]{2}"), relative.parts[:3]))
            or not re.fullmatch(r"rollout-[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}-[0-9]{2}-[0-9]{2}-"
                                + re.escape(binding["task_id"]) + r"\.jsonl", path.name)):
        return False
    first, context, last = (source.get(key) for key in ("task_started_line", "turn_context_line", "message_line"))
    if (any(type(value) is not int for value in (first, context, last))
            or not 1 < first < context < last <= context + 64):
        return False
    selected, incoming = {}, []
    with path.open("rb") as stream:
        for number, raw in enumerate(stream, 1):
            if number > last:
                break
            if number in {1, first, context, last}:
                selected[number] = (raw, json.loads(raw, object_pairs_hook=unique))
            elif context < number < last:
                record = json.loads(raw, object_pairs_hook=unique)
                item = record.get("payload", {})
                if record.get("type") == "response_item" and item.get("type") == "function_call_output":
                    incoming.append(record)
    if len(selected) != 4 or len(incoming) != 1:
        return False
    for number, key in ((first, "task_started"), (context, "turn_context"), (last, "message")):
        if hashlib.sha256(selected[number][0]).hexdigest() != source.get(key + "_row_sha256"):
            return False
    if len(selected[last][0]) != source.get("message_row_size"):
        return False
    meta, started, turn, reply = (selected[number][1] for number in (1, first, context, last))
    turn_id, message_id = observed["source_turn_id"], observed["source_message_id"]
    if (meta.get("type") != "session_meta" or meta.get("payload", {}).get("id") != binding["task_id"]
            or meta.get("payload", {}).get("session_id") != binding["task_id"]
            or meta.get("payload", {}).get("cwd") != binding["cwd"]
            or meta.get("payload", {}).get("originator") != "codex_work_desktop"
            or started.get("type") != "event_msg" or started.get("payload", {}).get("type") != "task_started"
            or started["payload"].get("turn_id") != turn_id
            or started["payload"].get("turn_attribution", {}).get("turn_trigger") != "app_tool_send_message"
            or turn.get("type") != "turn_context" or turn.get("payload", {}).get("turn_id") != turn_id
            or turn["payload"].get("cwd") != binding["cwd"]
            or reply.get("type") != "response_item" or reply.get("payload") != observed.get("native_reply")
            or reply.get("timestamp") != observed.get("message_timestamp")
            or reply.get("metadata", {}).get("client_authored") is not False):
        return False
    retained = reply.get("metadata", {}).get("retained_source", {})
    if (retained.get("complete") is not True or retained.get("id") != {
            "message_id": message_id, "turn_id": turn_id, "role": "assistant"}):
        return False
    item, received = reply["payload"], incoming[0]["payload"]
    text = observed.get("reply_text_utf8")
    if (item.get("type") != "message" or item.get("role") != "assistant" or item.get("id") != message_id
            or item.get("phase") != observed["phase"]
            or item.get("internal_chat_message_metadata_passthrough", {}).get("turn_id") != turn_id
            or not isinstance(text, str) or not text.strip()
            or item.get("content") != [{"type": "output_text", "text": text}]
            or hashlib.sha256(text.encode("utf-8")).hexdigest() != observed.get("reply_sha256")
            or len(text.encode("utf-8")) != observed.get("reply_size")
            or received.get("name") != "send_message_to_thread" or received.get("namespace") != "codex_app"
            or not received.get("id")
            or received.get("internal_chat_message_metadata_passthrough", {}).get("turn_id") != turn_id
            or not isinstance(received.get("output"), str)):
        return False
    wrapper = re.fullmatch(r"<codex_delegation>\s*<source_thread_id>([^<>]+)</source_thread_id>\s*<input>([\s\S]*)</input>\s*</codex_delegation>\s*", received["output"])
    if (not wrapper or wrapper.group(1) != hq["task_id"]
            or wrapper.group(2).encode("utf-8") != w.safe_path(root, contract_pin["path"]).read_bytes()):
        return False
    moments = [w._parse_observed_at(value) for value in (policy.get("checked_at"), started.get("timestamp"),
        incoming[0].get("timestamp"), reply.get("timestamp"), observed.get("observed_at"), ack.get("created_at"))]
    if any(value is None for value in moments) or moments != sorted(moments) or moments[-1] > w.dt.datetime.now(w.dt.timezone.utc):
        return False
    return True


def qualified_initial_review(root, role, goal, *, task_id=None, require_responsibility=True):
    """Explicit new-goal selection of the adopted method, not a default mapping.

    Initial registration checks HQ's complete native selection. Normal review,
    claim and acceptance additionally require the real ordinary responsibility
    handoff; this reader creates neither a dispatch nor a lease/permission.
    """
    import workflow_control as w
    try:
        root = Path(root).resolve()
        proof = goal.get(SELECTION_FIELD)
        if (not isinstance(proof, dict) or set(proof) not in
                (SELECTION_PROOF_FIELDS, SELECTION_PROOF_FIELDS | {"hq_goal_input"})
                or type(require_responsibility) is not bool):
            return False
        selected_task = w.validate_task_id(proof.get("task_id", ""))
        if task_id is not None and selected_task != task_id:
            return False
        item = w.department_registry(root).get(role, {})
        authority = item.get("coordination_authority", {})
        config = authority.get("technical_review_backup", {})
        scopes = goal.get("authorized_scope", [])
        project = w.load_policy(root).get("routing_policy", {}).get("source_project_id")
        if (proof.get("schema") != SELECTION_SCHEMA or role != QUALIFIED_ROLE or proof.get("reviewer") != role
                or proof.get("producer") != QUALIFIED_PRODUCER or goal.get("primary_owner") != QUALIFIED_PRODUCER
                or goal.get("producer_departments") != [QUALIFIED_PRODUCER] or goal.get("responsible_assistant") != role
                or goal.get("acceptance_capability") != "development" or goal.get("required_execution_actions", []) != []
                or goal.get("source_mode", "approved_dispatch") != "approved_dispatch" or goal.get("assignment_history")
                or not isinstance(scopes, list) or len(scopes) != 1 or proof.get("scope") != scopes[0]
                or not isinstance(scopes[0], str) or not scopes[0].startswith("project:flashcast:")
                or any(char in scopes[0] for char in "*?[]|\n\r") or not project
                or proof.get("goal_identity") != qualified_goal_identity(goal)
                or authority.get("routine_decisions") is not True or item.get("new_dispatch_enabled") is False
                or authority.get("production_write_allowed") is not False or item.get("production_write_allowed") is not False
                or "development_backup" not in authority.get("review_capabilities", [])
                or config.get("enabled") is not True or config.get("capability") != "development_backup"
                or config.get("mapped_acceptance_capability") != "development"
                or config.get("allowed_producer_departments") != [QUALIFIED_PRODUCER]
                or config.get("allowed_scope_prefixes") != ["project:flashcast:"]
                or config.get("default_assistant") != "operations-assistant-2"
                or config.get("transfer_from") != ["operations-assistant-2"] or config.get("explicit_transfer_required") is not True
                or config.get("production_write_allowed") is not False
                or not all(_qualified_binding(root, who, project) for who in (role, QUALIFIED_PRODUCER, "operations"))
                or not _methods_ready(root, item, config) or not _adopted_methods(root, item, config, proof.get("method_adoption"))):
            return False
        auth = goal.get("human_authorization", {})
        auth_pin = w.file_digest(root, auth.get("evidence_path", ""))
        human = _pinned_document(root, auth_pin)
        if (proof.get("authorization_pin") != auth_pin or goal.get("authorization_pin", auth_pin) != auth_pin
                or auth.get("executor") != QUALIFIED_PRODUCER or auth.get("scope") != scopes[0]
                or human.get("source_thread_id") != auth.get("source_thread_id")
                or human.get("message", {}).get("type") != "userMessage"
                or human.get("message", {}).get("id") != auth.get("message_id")
                or not any(part.get("type") == "text" and isinstance(part.get("text"), str) and part["text"].strip()
                           for part in human.get("message", {}).get("content", []) if isinstance(part, dict))):
            return False
        from goal_delivery_runtime import _collaboration_native
        document = _collaboration_native(root, proof.get("hq_native_selection"))
        binding = w.department_registry(root)["operations"]["chat_binding"]
        thread = document.get("thread", {})
        pin = proof.get("hq_selection_input")
        if not isinstance(pin, dict) or w.file_digest(root, pin.get("path", "")) != pin:
            return False
        raw = w.safe_path(root, pin["path"]).read_bytes()
        selected = [(turn, message) for turn in document.get("turns", []) if turn.get("id") == proof.get("hq_turn_id")
                    for message in turn.get("items", []) if message.get("type") == "agentMessage" and message.get("id") == proof.get("hq_message_id")]
        if (len(selected) != 1 or not proof.get("hq_turn_id") or not proof.get("hq_message_id")
                or thread.get("id") != binding["task_id"] or thread.get("title") != binding["title"]
                or thread.get("cwd") != binding["cwd"] or thread.get("projectId", project) != project):
            return False
        turn, message = selected[0]
        if (turn.get("status") not in {"inProgress", "completed"} or turn.get("error")
                or message.get("phase") not in {"commentary", "final_answer"}
                or type(turn.get("startedAt")) not in {int, float} or not 0 < turn["startedAt"] <= w.dt.datetime.now(w.dt.timezone.utc).timestamp()
                or not isinstance(message.get("text"), str) or not message["text"].strip() or message["text"].encode("utf-8") != raw):
            return False
        expected = {"schema": NATIVE_SELECTION_SCHEMA, "task_id": selected_task, "goal": qualified_goal_identity(goal),
            "authorization_pin": auth_pin, "resource_selection": {"reviewer": role, "capability": "development",
                "method_manifest": config["method_manifest"], "method_adoption": METHOD_ADOPTION},
            "production_write_allowed": False, "external_permission_issued": False}
        def unique_fields(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise w.WorkflowError("ambiguous native qualified goal fields")
                result[key] = value
            return result
        if "hq_goal_input" in proof:
            source_pin = proof["hq_goal_input"]
            _pinned_document(root, source_pin)
            source_goal = json.loads(w.safe_path(root, source_pin["path"]).read_bytes(), object_pairs_hook=unique_fields)
            from goal_delivery_runtime import REQUIRED
            if (any(key not in source_goal for key in (*REQUIRED, "human_authorization", "task_id"))
                    or source_goal.get("task_id") != selected_task or SELECTION_FIELD in source_goal
                    or qualified_goal_identity(source_goal) != qualified_goal_identity(goal)
                    or source_goal.get("authorization_pin", auth_pin) != auth_pin
                    or not _ordinary_resource_selection(raw.decode("utf-8"), role, selected_task, scopes[0],
                                                         source_pin, METHOD_ADOPTION["adoption_journal"])):
                return False
        elif json.loads(raw, object_pairs_hook=unique_fields) != expected:
            return False
        return not require_responsibility or _qualified_responsibility(root, role, goal, selected_task)
    except (OSError, ValueError, TypeError, KeyError, StopIteration, AttributeError, sqlite3.Error, w.WorkflowError):
        return False


def _ordinary_resource_selection(text, role, task_id, scope, goal_pin, adoption_pin):
    """A clear current HQ choice with exact source references, not any citation.

    The source document uses the existing complete-goal format. This text is
    ordinary prose; a dedicated HQ JSON or finished turn is not required.
    """
    def exact_pin(value):
        path, sha, size = value.get("path"), value.get("sha256"), value.get("size")
        if not isinstance(path, str) or not isinstance(sha, str) or type(size) is not int:
            return False
        occurrences = list(re.finditer(re.escape(path), text))
        if len(occurrences) != 1:
            return False
        # One exact file reference must associate its digest and byte count,
        # not collect matching numbers from unrelated paragraphs.
        mention = text[occurrences[0].start():occurrences[0].end() + 512]
        return bool(re.search(r"(?<![0-9a-f])" + re.escape(sha) + r"(?![0-9a-f])", mention)
                    and re.search(r"(?:\b(?:bytes?|size)\s*[：:=]?\s*" + str(size) + r"(?![0-9])"
                                  r"|(?<![0-9])" + str(size) + r"\s*(?:字节|B\b|bytes?\b))", mention,
                                  re.IGNORECASE))
    if (not isinstance(text, str) or not text.strip() or text.lstrip().startswith(("{", "["))
            or any(value not in text for value in (task_id, role, QUALIFIED_PRODUCER, scope, "development"))
            or not exact_pin(goal_pin) or not exact_pin(adoption_pin)):
        return False
    # Anchored assertion clauses prevent an ACK, prepared proposal or history
    # summary from becoming a choice merely because it cites all frozen files.
    # A separate sentence about old PREPARED or later responsibility ACK is
    # permitted; no global word blacklist is used.
    # An explicit current status declaration takes precedence over a later
    # apparent choice. References to an old PREPARED record are unaffected.
    current_status = re.compile(
        r"^\s*(?:(?:当前|本消息|本次)\s*)?(?:状态|status)\s*[：:=]\s*"
        r"[\s`*\"']*(?:PREPARED|ACK(?:_ONLY)?)(?:\s|[，。；,:：;`*\"']|$)", re.IGNORECASE)
    assertion = re.compile(
        r"^\s*(?:(?:重要)?资源(?:选择|决定)[：:]?\s*)?(?:总部\s*)?"
        r"(?:"
        r"(?:(?:现(?:决定)?|本目标|本任务|明确(?:决定)?|决定)\s*)?"
        r"(?:选择|指定|确定|安排|(?i:select|assign|designate))\s*(?:由\s*)?"
        r"|(?:现\s*)?(?:明确\s*)?决定\s*由\s*"
        r")" + re.escape(role) + r"(?=\s|[，。；,:：;]|$)")
    # A current same-goal revocation or conflicting sole reviewer has priority
    # over an earlier affirmative choice. Explicit old-goal/history references
    # keep their own scope; quoted material is never a current decision.
    lead = r"^\s*(?:(?:总部|本目标|本任务|当前目标|当前任务)\s*)?(?:(?:本次|现在|当前|现|明确|决定)\s*)*"
    revoked = re.compile(lead + r"(?:撤销|取消|收回|废止|不再(?:选择|指定|安排))\s*(?:对\s*)?"
                         + re.escape(role) + r"(?=\s|[，。；,:：;的]|$)")
    invalidated = re.compile(lead + r"(?:声明\s*)?(?:对\s*)?" + re.escape(role)
                            + r".{0,60}(?:指定|选择).{0,30}(?:不再有效|无效|已撤销|已取消)")
    other_choice = re.compile(assertion.pattern.replace(re.escape(role), r"(?P<reviewer>[a-z][a-z0-9-]*)"))
    reassigned = re.compile(lead + r"(?:改由|改派(?:给|为)?|重新(?:选择|指定))\s*(?P<reviewer>[a-z][a-z0-9-]*)(?=\s|[，。；,:：;]|$)")
    old_goal = re.compile(r"^\s*(?:(?:另一个|其他|不同|无关)(?:的)?(?:旧)?(?:目标|任务)|旧(?:目标|任务))")
    history = re.compile(r"^\s*(?:历史(?:引用|记录|说明|草案)|旧(?:记录|草案))")
    current_goal = re.compile(r"^\s*(?:总部|本目标|本任务|当前目标|当前任务)")
    quoted = False
    chosen = False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            quoted = not quoted
            continue
        if quoted or line.lstrip().startswith(">"):
            continue
        unrelated_line = bool(old_goal.match(line))
        for clause in re.split(r"[。；;]", line):
            if (old_goal.match(clause) or history.match(clause)
                    or (unrelated_line and not current_goal.match(clause))):
                continue
            if current_status.match(clause) or revoked.match(clause) or invalidated.match(clause):
                return False
            alternative = other_choice.match(clause) or reassigned.match(clause)
            if (alternative and alternative.group("reviewer") != role and "唯一" in clause
                    and "development" in clause and any(word in clause for word in ("验收", "助理", "reviewer"))):
                return False
            if assertion.match(clause):
                chosen = True
    return chosen


def _resource_pin(path):
    path = Path(path)
    if not path.is_absolute() or not path.is_file() or path.is_symlink():
        return None
    raw = path.read_bytes()
    return {"path": str(path), "sha256": hashlib.sha256(raw).hexdigest(), "size": len(raw)}


def _methods_ready(root, role, config):
    import workflow_control as w
    skill = role.get("professional_skill")
    if not isinstance(skill, str) or not skill:
        return False
    skill_path = w.safe_path(root, skill)
    if (not skill_path.is_file() or skill_path.is_symlink()
            or hashlib.sha256(skill_path.read_bytes()).hexdigest() != config.get("professional_skill_sha256")):
        return False
    pin = config.get("method_manifest")
    if not isinstance(pin, dict) or w.file_digest(root, pin.get("path", "")) != pin:
        return False
    manifest = w.read_json(w.safe_path(root, pin["path"]))
    if (manifest.get("department") != role.get("id")
            or manifest.get("capability") != "development_backup"
            or manifest.get("mapped_acceptance_capability") != "development"
            or manifest.get("use_scope") != "independent_acceptance_only"
            or any(manifest.get(key) is not False for key in
                   ("production_write_allowed", "account_permissions_granted", "producer_implementation_allowed"))):
        return False
    names, paths = role.get("approved_subskills", []), role.get("approved_subskill_paths", [])
    if not isinstance(names, list) or not isinstance(paths, list) or len(names) != len(paths):
        return False
    approved = dict(zip(names, paths))
    required, methods = manifest.get("required_methods"), manifest.get("methods")
    if not isinstance(required, list) or PRIMARY_METHOD not in required or not isinstance(methods, list):
        return False
    seen = set()
    for method in methods:
        if (not isinstance(method, dict) or method.get("name") in seen
                or not isinstance(method.get("use"), str) or not method["use"].strip()
                or method.get("production_tool_invocation_granted") is not False):
            return False
        name, path = method.get("name"), method.get("path")
        if not isinstance(name, str) or not isinstance(path, str) or approved.get(name) != path:
            return False
        expected = {key: method.get(key) for key in ("path", "sha256", "size")}
        if _resource_pin(path) != expected:
            return False
        seen.add(name)
    return set(required) <= seen


def _committed_transfer(root, task_id, role, config, goal):
    """Only an existing fenced SQL transfer plus original task event can activate."""
    import workflow_control as w
    history = goal.get("assignment_history", [])
    if not isinstance(history, list) or not history or not task_id:
        return False
    change = history[-1]
    if (not isinstance(change, dict) or change.get("target_assistant") != role
            or change.get("previous_assistant") not in config["transfer_from"]
            or type(change.get("fence")) is not int or change["fence"] < 1
            or change.get("result_identity", {}).get("task_id") != task_id):
        return False
    database = Path(root) / "logs/result-coordination.sqlite3"
    if not database.is_file() or database.is_symlink():
        return False
    with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True) as connection:
        matches = []
        for raw, previous, recorded in connection.execute(
                "SELECT payload_json,previous_hash,record_hash FROM coordination_audit ORDER BY seq"):
            payload = json.loads(raw)
            if (payload.get("event") == "transfer"
                    and payload.get("identity") == change["result_identity"]
                    and payload.get("details", {}).get("assignment_change") == change):
                digest = hashlib.sha256(json.dumps([previous, payload], sort_keys=True,
                    ensure_ascii=True, separators=(",", ":")).encode()).hexdigest()
                if recorded != digest:
                    return False
                matches.append(payload)
    if len(matches) != 1:
        return False
    events = w.read_jsonl(Path(root) / w.WORKFLOW_EVENTS)
    # Check provenance hashes without recursively selecting the reviewer again.
    # The existing workflow consumer separately validates state/receipt rules.
    previous = ""
    for event in events:
        if (event.get("previous_event_hash", "") != previous
                or event.get("event_hash") != w.sha256_value(
                    {key: value for key, value in event.items() if key != "event_hash"})):
            return False
        previous = event["event_hash"]
    return any(event.get("task_id") == task_id
               and event.get("details", {}).get("assignment_transfer") == change for event in events)


def review_capable(root, role, goal, *, task_id=None, transfer_from=None, allow_backup=True):
    """Normal capabilities stay exact; a backup never becomes a default reviewer.

    transfer_from is a read-only preparation context supplied by the existing
    explicit transfer consumer. Ordinary claims require its committed evidence.
    """
    import workflow_control as w
    try:
        root = Path(root).resolve()
        from goal_continuity import shared_capable
        if shared_capable(root, role, goal):return True
        item = w.department_registry(root).get(role, {})
        authority = item.get("coordination_authority", {})
        capability = goal.get("acceptance_capability")
        producers = goal.get("producer_departments", [])
        if (not isinstance(capability, str) or not isinstance(producers, list) or role in producers
                or authority.get("routine_decisions") is not True or item.get("new_dispatch_enabled") is False):
            return False
        capabilities = authority.get("review_capabilities", [])
        if (capability in capabilities and capability != "development_backup"
                and not (role == QUALIFIED_ROLE and capability == "development"
                         and isinstance(authority.get("technical_review_backup"), dict))):
            return True
        if (allow_backup and transfer_from is None and SELECTION_FIELD in goal
                and qualified_initial_review(root, role, goal, task_id=task_id, require_responsibility=True)):
            return True
        config = authority.get("technical_review_backup", {})
        if (not allow_backup or capability != "development" or not isinstance(config, dict)
                or config.get("enabled") is not True or "development_backup" not in capabilities
                or config.get("capability") != "development_backup"
                or config.get("mapped_acceptance_capability") != capability
                or config.get("default_assistant") != "operations-assistant-2"
                or config.get("transfer_from") != ["operations-assistant-2"]
                or config.get("explicit_transfer_required") is not True
                or config.get("production_write_allowed") is not False
                or item.get("production_write_allowed") is not False
                or goal.get("required_execution_actions")):
            return False
        permitted = config.get("allowed_producer_departments", [])
        scopes, prefixes = goal.get("authorized_scope", []), config.get("allowed_scope_prefixes", [])
        if (not producers or not isinstance(permitted, list) or not set(producers) <= set(permitted)
                or not isinstance(scopes, list) or not scopes or not isinstance(prefixes, list) or not prefixes
                or any(not isinstance(prefix, str) or not prefix.startswith("project:flashcast:") for prefix in prefixes)
                or any(not isinstance(scope, str) or not any(scope.startswith(prefix) for prefix in prefixes) for scope in scopes)
                or not _methods_ready(root, item, config)):
            return False
        if transfer_from is not None:
            return transfer_from in config["transfer_from"]
        return (goal.get("responsible_assistant") == role
                and _committed_transfer(root, task_id, role, config, goal))
    except (OSError, ValueError, TypeError, KeyError, sqlite3.Error, w.WorkflowError):
        return False
