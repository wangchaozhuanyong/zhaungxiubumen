"""Exact independent result review. Metadata is not authentication or permission."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
from pathlib import Path

R0_CLASSES = {"internal_control_candidate", "read_only_candidate"}
IDENTITY = ("task_id", "action_id", "action_class", "scope", "candidate_version", "candidate_sha256")
GOAL_IDENTITY = ("objective", "completion_criteria", "primary_owner", "responsible_assistant",
                 "authorized_scope", "producer_departments", "acceptance_capability")

# This is the frozen original notice, not a configurable message exemption.
_ORIGINAL_OWNER_DIRECT_AUTHORITY_NOTICE = {
    "task_id": "fc-20261010-paid-three-page-exact-publication-followthrough-v1",
    "scope": "project:flashcast:paid-three-page-original-publication-followthrough:v1",
    "reviewer_department": "operations-assistant-2", "producer_department": "publishing",
    "acceptance_capability": "cms", "action_id": "resolve-existing-authority-CMS-candidate-acceptance-v1",
    "dispatch_receipt_id": "60fe914b-c48a-47e1-9e55-e32d2e47b961",
    "dispatch_receipt_hash": "e0f20c9eaebb58ec30187a4225823012efce8602fa3ae3d528b7b5d37710d0a2",
    "ack_receipt_id": "e5efa857-9b86-41d6-a6d9-a37cf3f8c464",
    "ack_receipt_hash": "2424f3bdef7d01d3b8016c5079a7500ec133455450ed35a2b12c855f81e6b8d1",
    "policy_decision_id": "pol-7a33418269261fedcdcd",
    "authority": {"path": "logs/handoffs/2026-10-10-paid-three-page-original-followthrough-v1/human-authority-v1.json",
        "sha256": "bc04562c7436feab791ed17685e76b9f63db4410909bcf6b659b1c04b1f3f9e5", "size": 1784},
    "goal_contract": {"path": "logs/handoffs/2026-10-10-paid-three-page-original-followthrough-v1/complete-goal-input-v1.json",
        "sha256": "a7299fbe48422fad9dc52af129f0db58c4b5da3c5b0035f17671f882d428be04", "size": 3143},
    "payload": {"path": "logs/handoffs/2026-10-10-system-flow-interruption-resume-1853-v1/assistant2-existing-authorization-scope-decision-v1.md",
        "sha256": "2df41471cb3a6bd4248d53617ebf9d419effc85c5e118e7bbd61873feb491d06", "size": 1686},
    "native_send": {"path": "logs/handoffs/2026-10-10-system-flow-interruption-resume-1853-v1/assistant2-existing-authorization-scope-decision-actual-send-v1.json",
        "sha256": "62628e8e4c81323d6e48d94198de4a56d07533268d03e11c72bde47d2490f12a", "size": 1069},
    "native_ack": {"path": "logs/handoffs/2026-10-10-system-flow-interruption-resume-1853-v1/assistant2-existing-authorization-scope-decision-actual-ack-v1.json",
        "sha256": "ab483b06a9fd4e456e6599eaba182c2e4b85c178d9f9f9b0ae8e0d7a1fed422d", "size": 1163},
    "policy_row": {"path": "logs/handoffs/2026-10-11-acceptance-message-and-historical-adoption-boundary-repair-v1/ready/T3-original-authority-notice-policy-exact-row-v1.jsonl",
        "sha256": "3d591eac70d77a5c7703cbddaef5c4c8ce592df8781d53daebfc300f54dd3496", "size": 1484},
}


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


def _goal_reviewer(root, snapshot, *, transfer_from=None, preparation_only=False):
    from result_coordination import coordinator_roles
    from technical_review_backup import review_capable, qualified_initial_review
    w = _workflow()
    goal = _goal(root, snapshot)
    if goal is None:
        return None
    reviewer = goal.get("responsible_assistant")
    producers = goal.get("producer_departments", [])
    if (reviewer == "operations" or reviewer not in coordinator_roles(root)
            or not isinstance(producers, list) or not producers or reviewer in producers
            or not isinstance(goal.get("acceptance_capability"), str)
            or not (review_capable(root, reviewer, goal, task_id=snapshot.get("task_id"), transfer_from=transfer_from)
                    or (preparation_only and transfer_from is None
                        and qualified_initial_review(root, reviewer, goal, task_id=snapshot.get("task_id"),
                                                     require_responsibility=False)))):
        raise w.WorkflowError("one assigned capable independent assistant required; self review rejected")
    return reviewer


def _initial_goal_identity(root, snapshot, contract):
    """Keep frozen goal bytes while recognizing one committed backup transfer.

    Assignment provenance outlives a result lease. This reader grants no claim,
    accepts no old verdict, and leaves current-result token/fence gates intact.
    """
    w = _workflow()
    goal = _goal(root, snapshot)
    if goal is None or any(contract.get(key) != goal.get(key)
                           for key in GOAL_IDENTITY if key != "responsible_assistant"):
        return False
    previous, current = contract.get("responsible_assistant"), goal.get("responsible_assistant")
    if previous == current:
        return True
    from sqlite3 import Error as SQLiteError
    from technical_review_backup import _committed_transfer
    try:
        config = w.department_registry(root).get(current, {}).get("coordination_authority", {}).get("technical_review_backup", {})
        history = goal.get("assignment_history", [])
        if (not isinstance(config, dict) or config.get("explicit_transfer_required") is not True
                or config.get("default_assistant") != previous
                or config.get("transfer_from") != [previous]
                or not isinstance(history, list) or len(history) != 1
                or not isinstance(history[0], dict)
                or history[0].get("previous_assistant") != previous
                or history[0].get("target_assistant") != current
                or _goal_reviewer(root, snapshot) != current
                or any(contract.get(key) != goal.get(key) for key in
                       ("parent_task_id", "human_authorization"))
                or contract.get("source_mode", "approved_dispatch") != goal.get("source_mode", "approved_dispatch")
                or contract.get("required_execution_actions", []) != goal.get("required_execution_actions", [])
                or w.file_digest(root, contract["human_authorization"]["evidence_path"]) != goal.get("authorization_pin")
                or any(row.get("receipt_type") == "qa_verdict" and row.get("department") != current
                       for row in w.read_jsonl(w.receipts_path(root, snapshot["task_id"])))):
            return False
        return _committed_transfer(root, snapshot["task_id"], current, config, goal)
    except (w.WorkflowError, OSError, ValueError, TypeError, KeyError, SQLiteError):
        return False


def _initial_assignment(root, snapshot, dispatch, native_proof=None, *, source_pins=None):
    """An initial complete-goal assignment cannot freeze future source bytes."""
    w = _workflow()
    goal = _goal(root, snapshot)
    if goal is None:
        return False
    if native_proof is None:
        native_proof = (_binding(root, snapshot) or {}).get("native_multi_goal_review")
    if native_proof is not None:
        source = prepare_native_multi_goal_review(root, snapshot, native_proof)
        if dispatch == source["dispatch"] and snapshot["task_id"] == source["source_task_id"]:
            return True
    pin = snapshot.get("goal_contract")
    if pin is None:
        pins = [row.get("details", {}).get("goal_contract") for row in w.read_jsonl(root / w.WORKFLOW_EVENTS)
                if row.get("task_id") == snapshot.get("task_id") and row.get("details", {}).get("goal_contract")]
        pin = pins[-1] if pins else None
    if not isinstance(pin, dict) or w.file_digest(root, pin.get("path", "")) != pin:
        return False
    contract = w.read_json(w.safe_path(root, pin["path"]))
    contract = contract.get("goal_delivery", contract)
    return (_initial_goal_identity(root, snapshot, contract)
            and dispatch.get("receipt_type") == "dispatch_sent"
            and dispatch.get("action_id") == "assign-goal-review:" + snapshot["task_id"]
            and dispatch.get("scope") in goal["authorized_scope"]
            and (pin in dispatch.get("evidence", [])
                 or _initial_assignment_envelope(root, snapshot, dispatch, pin, source_pins=source_pins)))



def _initial_assignment_envelope(root, snapshot, dispatch, contract_pin, *, historical_send_pin=None, source_pins=None):
    """Associate the actual complete-goal transport with its original payload.

    The direct contract-pin path above remains unchanged. This explicit native
    envelope path reads existing policy/send/ACK bytes, creates no receipts and
    never substitutes a health observation for the original dispatch time.
    """
    from goal_source_recovery import initial_assignment_source
    if initial_assignment_source(root,snapshot,dispatch,contract_pin):
        return True
    if _saved_initial_assignment_envelope(root, snapshot, dispatch, contract_pin, source_pins=source_pins):
        return True
    if _modern_initial_assignment_transport(root, snapshot, dispatch, contract_pin):
        return True
    if _initial_assignment_wait_envelope(root, snapshot, dispatch, contract_pin):
        return True
    w = _workflow()
    try:
        def unique(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError("duplicate initial assignment field")
                result[key] = value
            return result

        def document(pin):
            if not isinstance(pin, dict) or w.file_digest(root, pin.get("path", "")) != pin:
                raise w.WorkflowError("frozen initial assignment evidence changed")
            value = json.loads(w.safe_path(root, pin["path"]).read_bytes(), object_pairs_hook=unique)
            if not isinstance(value, dict):
                raise ValueError("initial assignment object required")
            return value

        def rows(path):
            values = [json.loads(line, object_pairs_hook=unique)
                      for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
            if any(not isinstance(row, dict) for row in values):
                raise ValueError("original initial assignment rows required")
            return values

        task_id, goal = snapshot["task_id"], _goal(root, snapshot)
        role = goal["responsible_assistant"]
        registry = w.department_registry(root)
        fixed, hq = [registry[who]["chat_binding"] for who in (role, "operations")]
        contract = document(contract_pin)
        contract = contract.get("goal_delivery", contract)
        if (contract.get("task_id") != task_id or dispatch.get("task_id") != task_id
                or any(contract.get(key) != goal.get(key) for key in ("parent_task_id", "human_authorization"))
                or contract.get("source_mode", "approved_dispatch") != goal.get("source_mode", "approved_dispatch")
                or contract.get("required_execution_actions", []) != goal.get("required_execution_actions", [])
                or w.file_digest(root, contract["human_authorization"]["evidence_path"]) != goal.get("authorization_pin")
                or dispatch.get("department") != role or dispatch.get("action_class") != "thread_message"
                or dispatch.get("chat_task_id") != fixed["task_id"]
                or fixed.get("cwd") != str(Path(root).resolve()) or hq.get("cwd") != fixed["cwd"]
                or not fixed.get("project_id") or hq.get("project_id") != fixed["project_id"]
                or not any(row.get("department") == role and row.get("chat_task_id") == fixed["task_id"]
                           for row in snapshot.get("departments", []))):
            return False
        policies = [row for row in rows(root / w.POLICY_DECISIONS)
                    if row.get("decision_id") == dispatch.get("policy_decision_id")]
        expected = {"task_id": task_id, "department": "operations", "status": "allow",
                    "routing_status": "routing_allowed", "action_class": "thread_message",
                    "action_id": dispatch["action_id"], "scope": dispatch["scope"],
                    "payload_sha256": contract_pin["sha256"], "target_department": role,
                    "target_thread_id": fixed["task_id"], "target_thread_title": fixed["title"],
                    "source_project_id": fixed["project_id"], "target_project_id": fixed["project_id"],
                    "target_cwd": fixed["cwd"], "target_sidebar_section_id": fixed.get("sidebar_section_id")}
        if len(policies) != 1 or any(policies[0].get(key) != value for key, value in expected.items()):
            return False
        checked = w._parse_observed_at(policies[0].get("checked_at"))
        sent = w._parse_observed_at(dispatch.get("created_at"))
        now = dt.datetime.now(dt.timezone.utc)
        if checked is None or sent is None or not checked <= sent <= now:
            return False
        envelopes = [value for value in map(document, dispatch.get("evidence", []))
                     if "actual_tool_result" in value or "tool_name" in value]
        if len(envelopes) != 1:
            return False
        envelope = envelopes[0]
        # The permanent history reader alone supplies the immutable dispatch
        # pin from an authenticated adopted lineage. Keep the original wrapper
        # bytes, including its descriptive metadata; ordinary intake stays strict.
        historical_metadata = historical_send_pin is not None
        if historical_metadata and (historical_send_pin not in dispatch.get("evidence", [])
                or document(historical_send_pin) != envelope
                or not isinstance(envelope.get("purpose"), str) or not envelope["purpose"].strip()):
            return False
        _review_native_containers(envelope)
        expected_send = {"schema_version": 1, "task_id": task_id, "sender_department": "operations",
                         "target_department": role, "target_thread_id": fixed["task_id"],
                         "action_id": dispatch["action_id"], "policy_decision_id": dispatch["policy_decision_id"],
                         "payload_sha256": contract_pin["sha256"],
                         "tool_name": "mcp__codex_app__send_message_to_thread"}
        if (set(envelope) - set(expected_send) - {"recorded_at", "actual_tool_result", "isError", "truncated", "failed", "superseded"} - ({"purpose"} if historical_metadata else set())
                or any(envelope.get(key) != value for key, value in expected_send.items())
                or any(key in envelope for key in ("content", "structuredContent", "threadId", "native_send", "actual_send", "actual_native_send"))
                or ("isError" in envelope and envelope["isError"] is not False)):
            return False
        observed = w._parse_observed_at(envelope.get("recorded_at"))
        if observed is None:
            try:
                observed = dt.datetime.strptime(envelope.get("recorded_at", ""), "%Y-%m-%d %H:%M:%S UTC").replace(tzinfo=dt.timezone.utc)
            except (ValueError, TypeError):
                return False
        result = envelope.get("actual_tool_result", {})
        content = result.get("content")
        second_precision = isinstance(dispatch.get("created_at"), str) and re.fullmatch(
            r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+00:00", dispatch["created_at"]) is not None
        observed_before_receipt = (observed < sent + dt.timedelta(seconds=1) if second_precision else observed <= sent)
        if (set(result) - {"content", "isError", "structuredContent", "truncated", "failed", "superseded", "threadId", "target_thread_id"}
                or result.get("isError") is not False or not checked <= observed <= now or not observed_before_receipt
                or any(key in result and result[key] != fixed["task_id"] for key in ("threadId", "target_thread_id"))
                or not isinstance(content, list) or len(content) != 1 or not isinstance(content[0], dict)
                or content[0].get("type") != "text" or not isinstance(content[0].get("text"), str)):
            return False
        # Only the original, already identity-checked locator fields differ
        # from the ordinary raw response. Unknown fields remain rejected.
        native = _review_raw_native_result({key: value for key, value in result.items()
                                           if key not in {"threadId", "target_thread_id"}})
        if (set(native) - {"threadId", "target_thread_id", "turnId", "isError", "truncated", "failed", "superseded"}
                or native.get("threadId") != fixed["task_id"]
                or ("target_thread_id" in native and native["target_thread_id"] != fixed["task_id"])
                or ("isError" in native and native["isError"] is not False)
                or any(key in native for key in ("threads", "pinnedThreads", "native_send", "actual_send", "actual_native_send"))
                or ("structuredContent" in result and result["structuredContent"] != native)):
            return False
        receipts, previous = rows(w.receipts_path(root, task_id)), ""
        for row in receipts:
            if (row.get("task_id") != task_id or row.get("previous_hash", "") != previous
                    or row.get("receipt_hash") != w.sha256_value(w._receipt_payload_for_hash(row))):
                return False
            previous = row["receipt_hash"]
        selected = [(i, row) for i, row in enumerate(receipts) if row == dispatch]
        matching = [row for row in receipts if row.get("department") == role
                    and row.get("receipt_type") in {"dispatch_sent", "dispatch_failed"}
                    and row.get("action_id") == dispatch["action_id"] and row.get("scope") == dispatch["scope"]]
        if len(selected) != 1 or len(matching) != 1:
            return False
        index = selected[0][0]
        if any(row.get("supersedes_receipt_id") == dispatch["receipt_id"] for row in receipts[index + 1:]):
            return False
        subsequent = []
        for row in receipts[index + 1:]:
            if row.get("department") == role and row.get("receipt_type") in {"dispatch_sent", "dispatch_failed"}:
                break
            if row.get("department") == role and row.get("receipt_type") == "chat_ack":
                subsequent.append(row)
        if len(subsequent) != 1:
            return False
        ack = subsequent[0]
        ack_at = w._parse_observed_at(ack.get("created_at"))
        if (ack.get("chat_task_id") != fixed["task_id"] or ack.get("ack_nonempty") is not True
                or ack_at is None or not sent <= ack_at <= now):
            return False
        acknowledgements = [value for value in map(document, ack.get("evidence", [])) if "native_wait_poll" in value]
        if len(acknowledgements) != 1:
            return False
        ack_doc = acknowledgements[0]
        poll = ack_doc.get("native_wait_poll", {})
        turn, message = poll.get("latestTurn", {}), poll.get("latestAssistantMessage", {})
        return (ack_doc.get("schema_version") == 1 and ack_doc.get("task_id") == task_id
                and ack_doc.get("department") == role and ack_doc.get("fixed_chat_task_id") == fixed["task_id"]
                and ack_doc.get("ack_nonempty") is True and ack_doc.get("is_candidate_result") is False
                and poll.get("schemaVersion") == 1 and poll.get("thread", {}).get("id") == fixed["task_id"]
                and isinstance(poll.get("cursor"), str) and bool(poll["cursor"])
                and type(poll.get("revision")) is int and poll["revision"] > 0
                and turn.get("id") == ack_doc.get("new_turn_id") and bool(turn.get("id"))
                and ("turnId" not in native or native["turnId"] == turn["id"])
                and turn.get("status") in {"inProgress", "completed"} and not turn.get("error")
                and type(turn.get("startedAt")) in {int, float}
                and checked.timestamp() <= turn["startedAt"] <= ack_at.timestamp()
                and message.get("id") == poll.get("latestAssistantMessageId") and bool(message.get("id"))
                and message.get("turnId") == turn["id"] and message.get("phase") in {"commentary", "final_answer"}
                and isinstance(message.get("text"), str) and bool(message["text"].strip()))
    except (w.WorkflowError, OSError, ValueError, TypeError, KeyError, AttributeError):
        return False


def _evidence_pins(value):
    """Read both existing list and named-dict evidence without changing bytes."""
    if isinstance(value, list):
        for item in value:
            yield from _evidence_pins(item)
    elif isinstance(value, dict):
        if set(("path", "sha256", "size")) <= set(value):
            yield value
        else:
            for item in value.values():
                yield from _evidence_pins(item)


def _producer_candidate_bound(root, plan, producer_pin, producer):
    w = _workflow()
    candidate = plan.get("candidate")
    if candidate != producer_pin:
        return candidate in list(_evidence_pins(producer.get("evidence", [])))
    # A validated V2 or V3 producer outbox can itself be the immutable candidate.
    # Its evidence cannot contain its own final hash; no synthetic adapter needed.
    if not isinstance(producer_pin, dict):
        return False
    try:
        if w.file_digest(root, producer_pin.get("path", "")) != producer_pin:
            return False
    except (w.WorkflowError, OSError, ValueError, TypeError):
        return False
    version = producer.get("schema_version")
    if not isinstance(version, str) or version not in {"2.0", "3.0"}:
        return False
    department = plan.get("producer_department")
    binding = w.department_registry(root).get(department, {}).get("chat_binding", {})
    if version == "3.0":
        try:
            w.validate_outbox(root, [producer_pin], department, plan.get("task_id"))
        except (w.WorkflowError, OSError, ValueError, TypeError):
            return False
        if any(key in producer and producer[key] != expected for key, expected in (
                ("sender_department", department), ("chat_task_id", binding.get("task_id")),
                ("project_id", binding.get("project_id")), ("cwd", binding.get("cwd")))):
            return False
    return (producer.get("task_id") == plan.get("task_id")
            and producer.get("department") == department
            and producer.get("candidate_version") == plan.get("candidate_version")
            and producer.get("fixed_chat_task_id") == binding.get("task_id")
            and producer_pin.get("sha256") == plan.get("candidate_sha256"))


def _exact_text_reference(text, value):
    """No prefix matches: a different task, filename or path is a different source."""
    return bool(isinstance(value, str) and value and re.search(
        r"(?<![A-Za-z0-9_./:-])" + re.escape(value) + r"(?![A-Za-z0-9_./:-])", text))


def _owner_direct_native_input(root, pin, input_pin, receiver, sender, registry):
    """Bind the actual received function output to its original UTF-8 input file.

    These local hash pins detect mutation; they do not authenticate a platform
    account or create a dispatch/ACK or an execution permission.
    """
    w = _workflow()
    source = w.read_json(w.safe_path(root, pin["path"]))
    item = source.get("actual_function_call_output", {})
    if receiver not in registry or sender not in registry or not isinstance(item, dict):
        raise w.WorkflowError("registered original native source/receiver required")
    output = item.get("output", {})
    turn = source.get("actual_receiving_turn", {})
    if not isinstance(output, dict) or not isinstance(turn, dict):
        raise w.WorkflowError("original native output/receiving turn required")
    raw = output.get("text")
    receiver_binding = registry[receiver].get("chat_binding", {})
    sender_binding = registry[sender].get("chat_binding", {})
    if (source.get("schema_version") != 1
            or source.get("source_tool") != "mcp__codex_app__read_thread"
            or source.get("source_is_actual_native_function_call_output") is not True
            or source.get("no_synthetic_userMessage_or_dispatch") is not True
            or source.get("new_production_permissions") is not False
            or source.get("actual_input_equals_frozen_message_bytes", True) is not True
            or source.get("actual_receiver_department") != receiver
            or source.get("actual_receiver_thread_id") != receiver_binding.get("task_id")
            or source.get("actual_receiver_project_root") != str(Path(root).resolve())
            or receiver_binding.get("cwd") != str(Path(root).resolve())
            or sender_binding.get("cwd") != str(Path(root).resolve())
            or not turn.get("id") or turn.get("status") not in {"inProgress", "completed"}
            or not isinstance(turn.get("startedAt"), (int, float))
            or isinstance(turn.get("startedAt"), bool)
            or not 0 < turn["startedAt"] <= dt.datetime.now(dt.timezone.utc).timestamp()
            or item.get("type") != "functionCallOutput" or not item.get("id")
            or item.get("name") != "send_message_to_thread" or item.get("namespace") != "codex_app"
            or output.get("truncated") is not False or not isinstance(raw, str)):
        raise w.WorkflowError("actual original native responsibility receiving/source identity required")
    match = re.fullmatch(r"<codex_delegation>\n  <source_thread_id>([^<\n]+)</source_thread_id>\n  <input>([\s\S]+)</input>\n</codex_delegation>", raw)
    if match is None or match.group(1) != sender_binding.get("task_id"):
        raise w.WorkflowError("exact original native delegation source required")
    text = match.group(2)
    data = text.encode("utf-8")
    if (not text.strip() or w.safe_path(root, input_pin["path"]).read_bytes() != data
            or input_pin.get("sha256") != hashlib.sha256(data).hexdigest()
            or input_pin.get("size") != len(data)):
        raise w.WorkflowError("original received input UTF8 bytes differ from frozen source")
    for field, value in (("actual_wrapper_sha256", hashlib.sha256(raw.encode("utf-8")).hexdigest()),
                         ("actual_wrapper_bytes", len(raw.encode("utf-8"))),
                         ("actual_input_utf8_sha256", hashlib.sha256(data).hexdigest()),
                         ("actual_input_utf8_bytes", len(data))):
        if field in source and source[field] != value:
            raise w.WorkflowError("original native wrapper/input hash metadata changed")
    return {"input": text, "source_thread_id": match.group(1),
            "receiver_thread_id": source["actual_receiver_thread_id"],
            "native_item_id": item["id"], "turn_id": turn["id"]}


def _owner_direct_complete_received_input(root, pin, payload, receiver, sender, registry):
    """Match the provider's three literal XML entities to the exact original MD.

    Only the expected UTF-8 bytes have a transport representation. Never unescape
    arbitrary text, strip it, or accept a shortened/projection-only body.
    """
    w = _workflow()
    raw = w.safe_path(root, payload["path"]).read_bytes()
    if w.file_digest(root, payload["path"]) != payload:
        raise w.WorkflowError("exact original complete human forwarding payload required")
    text = raw.decode("utf-8")
    encoded = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    document = _review_source_document(root, pin)
    if "content" in document:
        document = _review_raw_native_result(document)
    fixed, source = [registry[role]["chat_binding"] for role in (receiver, sender)]
    thread, turns = document.get("thread", {}), document.get("turns")
    if (document.get("schemaVersion") != 1 or not isinstance(turns, list) or not turns
            or any(thread.get(key) != value for key, value in {"id": fixed["task_id"], "kind": "codex",
                   "hostId": "local", "title": fixed["title"], "cwd": fixed["cwd"]}.items())
            or ("projectId" in thread and thread["projectId"] != fixed["project_id"])):
        raise w.WorkflowError("actual complete original receiving thread/turns required")
    found = []
    for turn in turns:
        if not isinstance(turn, dict) or not isinstance(turn.get("items"), list):
            raise w.WorkflowError("original full received turn items required")
        for item in turn["items"]:
            if (not isinstance(item, dict) or item.get("type") != "functionCallOutput"
                    or item.get("name") != "send_message_to_thread" or item.get("namespace") != "codex_app"):
                continue
            output = item.get("output", {})
            body = output.get("text") if isinstance(output, dict) else None
            if not isinstance(body, str):
                continue
            match = re.fullmatch(r"<codex_delegation>\n  <source_thread_id>([^<\n]+)</source_thread_id>\n  <input>([\s\S]+)</input>\n</codex_delegation>", body)
            if match is None or match[2] != encoded:
                continue
            for container in (document, thread, turn, item, output):
                _review_native_containers(container)
            if (match[1] != source["task_id"] or output.get("truncated") is not False
                    or turn.get("status") not in {"inProgress", "completed"} or not turn.get("id") or not item.get("id")):
                raise w.WorkflowError("exact successful original human forwarding source required")
            found.append({"thread": thread, "turn": turn, "item": item,
                          "observed_at": document.get("observed_at_utc"), "input": text})
    if len(found) != 1:
        raise w.WorkflowError("one exact complete actual human forwarding FCO required")
    return found[0]


def _owner_direct_human_responsibility(root, snapshot, goal, proof, registry):
    """Use the assigned assistant's actual user authorization and original send.

    Existing proof slots name the immutable human JSON, complete message,
    successful forwarding return and full original producer receiving source.
    No HQ dispatch, replacement ACK or production permission is fabricated.
    """
    w = _workflow()
    import goal_delivery_runtime as g
    reviewer, producer, task = goal["responsible_assistant"], proof["producer_department"], snapshot["task_id"]
    validated = g.validate_goal(root, goal, task_id=task)
    source, target = [registry[role]["chat_binding"] for role in (reviewer, producer)]
    authority = validated["authorization_pin"]
    if (goal.get("source_mode") != "owner_direct" or reviewer == producer
            or producer != goal.get("primary_owner") or producer not in goal.get("producer_departments", [])
            or proof.get("scope") != goal["human_authorization"]["scope"]
            or proof["scope"] not in goal["authorized_scope"]
            or goal.get("authorization_pin") != authority
            or proof.get("authority") != authority
            or proof.get("reviewer_native_responsibility") != authority
            or proof.get("reviewer_responsibility_input") != authority
            or proof.get("goal_contract") != snapshot.get("goal_contract")
            or source.get("cwd") != str(Path(root).resolve()) or target.get("cwd") != source["cwd"]
            or not source.get("project_id") or target.get("project_id") != source["project_id"]
            or goal["human_authorization"]["source_thread_id"] != source["task_id"]):
        raise w.WorkflowError("exact assigned assistant human responsibility required")
    human = _review_source_document(root, authority)
    _review_native_containers(human)
    identity, message = human.get("source_thread", {}), human.get("message", {})
    for container in (identity, message):
        _review_native_containers(container)
    content = message.get("content")
    if (human.get("source_thread_id") != source["task_id"] or not human.get("source_turn_id")
            or any(identity.get(key) != value for key, value in {"id": source["task_id"], "hostId": "local",
                    "title": source["title"], "cwd": source["cwd"]}.items())
            or ("projectId" in identity and identity["projectId"] != source["project_id"])
            or ("kind" in identity and identity["kind"] != "codex")
            or message.get("type") != "userMessage" or message.get("id") != goal["human_authorization"]["message_id"]
            or ("turnId" in message and message["turnId"] != human["source_turn_id"])
            or not isinstance(content, list) or not content
            or any(not isinstance(item, dict) or set(item) != {"type", "text"} or item.get("type") != "text"
                   or not isinstance(item.get("text"), str) for item in content)
            or not any(item["text"].strip() for item in content)):
        raise w.WorkflowError("original nonempty userMessage and fixed source identity required")
    contract_pin, payload = proof["goal_contract"], proof["producer_native_input"]
    contract = _review_source_document(root, contract_pin)
    contract = contract.get("goal_delivery", contract)
    if (any(contract.get(key) != goal.get(key) for key in GOAL_IDENTITY)
            or contract.get("human_authorization") != goal.get("human_authorization")
            or contract.get("source_mode") != "owner_direct" or contract.get("parent_task_id") != goal.get("parent_task_id")
            or contract.get("required_execution_actions", []) != goal.get("required_execution_actions", [])
            or proof.get("original_handoff") not in goal.get("existing_results", [])):
        raise w.WorkflowError("exact original owner-direct contract and existing handoff required")
    _closed_review_source_pins(root, [payload, proof["original_handoff"]])
    raw = w.safe_path(root, payload["path"]).read_bytes()
    contract_raw = w.safe_path(root, contract_pin["path"]).read_bytes()
    text = raw.decode("utf-8")
    outside = raw.replace(contract_raw, b"").decode("utf-8")
    if (raw.count(contract_raw) != 1
            or re.findall(r"(?<![A-Za-z0-9_])task_id\s*=\s*([A-Za-z0-9_-]+)", text) != [task]
            or any(not _exact_text_reference(text, value) for value in
                   (task, reviewer, producer, source["task_id"], goal["human_authorization"]["message_id"]))
            or not any(_exact_text_reference(text, value) for value in
                       (contract_pin["path"], str(w.safe_path(root, contract_pin["path"]))))
            or set(re.findall(r"(?<![A-Za-z0-9_-])fc-[A-Za-z0-9_-]+", outside)) - {task, goal.get("parent_task_id")}
            or set(re.findall(r"(?:project|cms):[A-Za-z0-9_:.-]+", outside)) - set(goal["authorized_scope"])):
        raise w.WorkflowError("one complete original goal and exact human/roles/payload required")
    attempt = _review_source_document(root, proof["producer_send_attempt"])
    keys = {"schema", "target_thread_id", "title", "source_thread_id", "human_message_id", "intent_at",
            "message_path", "sha256", "utf8_bytes", "actual_send_effect"}
    if (set(attempt) != keys or attempt.get("schema") != "exact-one-native-send-intent/v1"
            or attempt.get("target_thread_id") != target["task_id"] or attempt.get("title") != target["title"]
            or attempt.get("source_thread_id") != source["task_id"]
            or attempt.get("human_message_id") != goal["human_authorization"]["message_id"]
            or w.safe_path(root, attempt.get("message_path", "")) != w.safe_path(root, payload["path"])
            or attempt.get("sha256") != payload["sha256"] or type(attempt.get("utf8_bytes")) is not int
            or attempt["utf8_bytes"] != payload["size"] or attempt.get("actual_send_effect") != "NOT_YET_OBSERVED"):
        raise w.WorkflowError("original intent may only locate the exact frozen human forwarding payload")
    send = _review_source_document(root, proof["producer_native_send"])
    _review_native_containers(send)
    send_keys = {"schema", "role", "target_thread_id", "target_title", "source_thread_id", "human_message_id",
                 "tool_name", "actual_tool_result", "prepared_only"}
    if (set(send) != send_keys or send.get("schema") != "actual-one-native-send-return/v1"
            or send.get("role") != producer or send.get("target_thread_id") != target["task_id"]
            or send.get("target_title") != target["title"] or send.get("source_thread_id") != source["task_id"]
            or send.get("human_message_id") != goal["human_authorization"]["message_id"]
            or send.get("tool_name") != "mcp__codex_app__send_message_to_thread" or send.get("prepared_only") is not False
            or _review_raw_native_result(send["actual_tool_result"]) != {"threadId": target["task_id"]}):
        raise w.WorkflowError("successful exact original owner-direct native send required")
    received = _owner_direct_complete_received_input(root, proof["producer_native_received"], payload, producer, reviewer, registry)
    rows, previous = _strict_source_rows(root, task), ""
    for row in rows:
        if (row.get("task_id") != task or row.get("previous_hash", "") != previous
                or row.get("receipt_hash") != w.sha256_value(w._receipt_payload_for_hash(row))):
            raise w.WorkflowError("actual intact original owner-direct receipt chain required")
        previous = row["receipt_hash"]
    end = next((i for i, row in enumerate(rows) if row.get("department") == producer
                and row.get("receipt_type") == "outbox_received"), len(rows))
    acks = [row for row in rows[:end] if row.get("department") == producer and row.get("receipt_type") == "chat_ack"]
    if len(acks) != 1 or len(acks[0].get("evidence", [])) != 1:
        raise w.WorkflowError("one actual original professional ACK required")
    ack = acks[0]
    native_ack = _review_source_document(root, ack["evidence"][0])
    _review_native_containers(native_ack)
    thread, turn, reply = [native_ack.get(key, {}) for key in ("thread", "turn", "message")]
    for container in (thread, turn, reply):
        _review_native_containers(container)
    if (ack.get("ack_nonempty") is not True or ack.get("chat_task_id") != target["task_id"]
            or ack.get("scope") not in {"", proof["scope"]}
            or ack.get("action_class") not in {"", "thread_message"}
            or any(ack.get(key) for key in ("supersedes_receipt_id", "replacement_reason", "approval_id"))
            or any(row.get("supersedes_receipt_id") == ack["receipt_id"] for row in rows)
            or native_ack.get("task_id") != task or native_ack.get("department") != producer
            or native_ack.get("source_thread_id") != target["task_id"]
            or any(thread.get(key) != value for key, value in {"id": target["task_id"], "kind": "codex",
                    "hostId": "local", "title": target["title"], "cwd": target["cwd"]}.items())
            or ("projectId" in thread and thread["projectId"] != target["project_id"])
            or native_ack.get("source") != "mcp__codex_app__read_thread"
            or native_ack.get("actual_native_read") is not True or native_ack.get("nonempty") is not True
            or native_ack.get("selected_projection_not_raw_full_return") is not True
            or turn.get("id") != received["turn"]["id"] or turn.get("status") not in {"inProgress", "completed"}
            or reply.get("type") != "agentMessage" or not reply.get("id") or reply.get("turnId") != turn["id"]
            or reply.get("phase") not in {"commentary", "final_answer"}
            or not isinstance(reply.get("text"), str) or not reply["text"].strip()
            or set(re.findall(r"(?<![A-Za-z0-9_-])fc-[A-Za-z0-9_-]+", reply["text"])) - {task, goal.get("parent_task_id")}):
        raise w.WorkflowError("exact original professional selected ACK and receiving turn required")
    # The selected projection is bound to the actual full receiving source,
    # not trusted because a local boolean calls it native.
    full_turn = received["turn"]
    messages = [item for item in full_turn.get("items", []) if item.get("id") == reply["id"]]
    if (len(messages) != 1 or any(messages[0].get(key) != reply.get(key) for key in ("type", "id", "text", "phase"))
            or ("turnId" in messages[0] and messages[0]["turnId"] != turn["id"])):
        raise w.WorkflowError("original ACK must equal its unique actual full native message")
    _review_native_containers(messages[0])
    intent_at, at = [_review_observed_at(value) for value in (attempt.get("intent_at"), ack.get("created_at"))]
    start = full_turn.get("startedAt")
    observed = _review_observed_at(received["observed_at"])
    if (intent_at is None or at is None or observed is None
            or not intent_at <= at <= observed <= dt.datetime.now(dt.timezone.utc)
            or type(start) not in {int, float} or not 0 < start <= at.timestamp()
            or turn.get("startedAt") != start
            or (full_turn.get("completedAt") is not None and
                (type(full_turn["completedAt"]) not in {int, float} or not max(start, intent_at.timestamp()) <= full_turn["completedAt"] <= observed.timestamp()))):
        raise w.WorkflowError("ordered actual original human forwarding and ACK observations required")
    return {"reviewer_native_item_id": message["id"], "reviewer_responsibility_input_sha256": authority["sha256"],
            "producer_native_item_id": received["item"]["id"], "producer_input_sha256": payload["sha256"],
            "task_id": task, "scope": proof["scope"], "producer_send": {"threadId": target["task_id"]}}


def _owner_direct_responsibility(root, snapshot, goal, proof, registry):
    """Use the real original receipt and current complete goal, never a new grant."""
    w = _workflow()
    reviewer, producer = goal["responsible_assistant"], proof["producer_department"]
    if proof.get("scope") != goal["human_authorization"]["scope"]:
        raise w.WorkflowError("original owner-direct exact task/scope required")
    if (goal.get("source_mode") == "owner_direct"
            and goal["human_authorization"].get("source_thread_id") == registry[reviewer]["chat_binding"]["task_id"]):
        return _owner_direct_human_responsibility(root, snapshot, goal, proof, registry)
    responsibility = _owner_direct_native_input(root, proof["reviewer_native_responsibility"],
        proof["reviewer_responsibility_input"], reviewer, "operations", registry)
    received = _owner_direct_native_input(root, proof["producer_native_received"],
        proof["producer_native_input"], producer, reviewer, registry)
    contract_path = proof["goal_contract"]["path"]
    absolute_contract = str(w.safe_path(root, contract_path))
    text = received["input"]
    tasks = re.findall(r"(?<![A-Za-z0-9_])task_id\s*=\s*([A-Za-z0-9_-]+)", text)
    if (tasks != [snapshot["task_id"]] or not _exact_text_reference(text, snapshot["task_id"])
            or not _exact_text_reference(text, goal["human_authorization"]["message_id"])
            or not (_exact_text_reference(text, contract_path) or _exact_text_reference(text, absolute_contract))
            or not _exact_text_reference(text, Path(proof["original_handoff"]["path"]).stem)
            or not _exact_text_reference(text, reviewer)
            or not _exact_text_reference(text, producer)):
        raise w.WorkflowError("original native producer input must bind exact task/goal/human/handoff/roles")
    attempt = w.read_json(w.safe_path(root, proof["producer_send_attempt"]["path"]))
    if (attempt.get("task_id") != snapshot["task_id"]
            or attempt.get("target_thread_id") != received["receiver_thread_id"]
            or attempt.get("source_mode") != "owner_direct_human_authorized_forwarding"
            or attempt.get("human_message_id") != goal["human_authorization"]["message_id"]
            or attempt.get("payload_sha256") != proof["producer_native_input"]["sha256"]
            or attempt.get("payload_size") != proof["producer_native_input"]["size"]
            or attempt.get("native_send_started") is not True
            or attempt.get("ordinary_dispatch_or_allow_fabricated") is not False
            or attempt.get("CMS_permission_created") is not False
            or attempt.get("production_executed") is not False):
        raise w.WorkflowError("original native producer send attempt/task/input/human source mismatch")
    # The real batch responsibility names the already existing original packet.
    # Its task and scope come only from the frozen contract + original native
    # producer input, not another numbered task in the same batch message.
    packet = str(Path(contract_path).parent) + "/"
    absolute_packet = str(w.safe_path(root, contract_path).parent) + "/"
    sections = re.split(r"(?m)^\d+[.、] ", responsibility["input"])
    exact = [section for section in sections if any(_exact_text_reference(section, ref)
             for ref in (contract_path, absolute_contract, packet, absolute_packet))]
    if len(exact) != 1:
        raise w.WorkflowError("one exact original task packet in actual reviewer responsibility required")
    task_refs = set(re.findall(r"(?<![A-Za-z0-9_-])fc-[A-Za-z0-9_-]+", exact[0]))
    scope_refs = set(re.findall(r"project:[A-Za-z0-9_:.-]+", exact[0]))
    if (task_refs - {snapshot["task_id"], goal.get("parent_task_id"), goal.get("coordination_origin_parent_task_id")}
            or scope_refs - set(goal["authorized_scope"])):
        raise w.WorkflowError("reviewer responsibility references a different original task/scope")
    return {"reviewer_native_item_id": responsibility["native_item_id"],
            "reviewer_responsibility_input_sha256": proof["reviewer_responsibility_input"]["sha256"],
            "producer_native_item_id": received["native_item_id"],
            "producer_input_sha256": proof["producer_native_input"]["sha256"],
            "task_id": snapshot["task_id"], "scope": proof["scope"]}


def prepare_owner_direct_review(root, snapshot, proof):
    """Validate existing original sources only; preparation never sends or writes."""
    from goal_delivery_runtime import validate_goal, _native_document
    w = _workflow()
    goal = _goal(root, snapshot)
    reviewer = _goal_reviewer(root, snapshot)
    if (goal is None or goal.get("source_mode") != "owner_direct" or not isinstance(proof, dict)
            or proof.get("schema_version") != 1 or proof.get("task_id") != snapshot.get("task_id")
            or proof.get("responsible_assistant") != reviewer
            or proof.get("producer_department") not in goal.get("producer_departments", [])):
        raise w.WorkflowError("exact independent original owner-direct review identity required")
    validate_goal(root, goal)
    if proof.get("authority") != goal.get("authorization_pin") or proof.get("goal_contract") != snapshot.get("goal_contract"):
        raise w.WorkflowError("original human/goal pins required for owner-direct review")
    for name in ("authority", "goal_contract", "original_handoff", "producer_outbox", "producer_native_send",
                 "producer_native_received", "producer_native_input", "producer_send_attempt",
                 "reviewer_native_responsibility", "reviewer_responsibility_input",
                 "reviewer_source_outbox", "reviewer_native_reply"):
        pin = proof.get(name)
        if not isinstance(pin, dict) or w.file_digest(root, pin.get("path", "")) != pin:
            raise w.WorkflowError("exact original owner-direct source pin required: " + name)
    contract = w.read_json(w.safe_path(root, proof["goal_contract"]["path"]))
    contract = contract.get("goal_delivery", contract)
    if (any(contract.get(key) != goal.get(key) for key in GOAL_IDENTITY)
            or proof["original_handoff"] not in goal.get("existing_results", [])):
        raise w.WorkflowError("original owner-direct goal and existing handoff must match")
    producer = proof["producer_department"]
    fixed = w.department_registry(root)
    responsibility = _owner_direct_responsibility(root, snapshot, goal, proof, fixed)
    send = responsibility.get("producer_send") if "producer_send" in responsibility else _native_document(root, proof["producer_native_send"])
    if (send.get("threadId") != fixed[producer].get("chat_binding", {}).get("task_id")
            or ("task_id" in send and send["task_id"] != snapshot["task_id"])
            or ("input" in send and send["input"] != w.safe_path(root, proof["producer_native_input"]["path"]).read_text())):
        raise w.WorkflowError("original native producer send target mismatch")
    try:
        rows = [json.loads(line) for line in w.receipts_path(root, snapshot["task_id"]).read_text().splitlines() if line.strip()]
    except (OSError, ValueError) as exc:
        raise w.WorkflowError("strict original producer receipt source required") from exc
    if any(not isinstance(row, dict) for row in rows):
        raise w.WorkflowError("strict original producer receipt objects required")
    boxes = [row for row in rows if row.get("receipt_type") == "outbox_received" and row.get("department") == producer
             and proof["producer_outbox"] in row.get("evidence", [])]
    if len(boxes) != 1 or not isinstance(boxes[0].get("receipt_id"), str) or not boxes[0]["receipt_id"]:
        raise w.WorkflowError("one real original producer receipt required")
    # Full QA readback re-enters this source preparation. Validate the precise
    # original producer prefix here; the enclosing full consumer still validates
    # every later formal verdict and current receipt rather than recursing.
    receipts, invalid = w._validate_receipt_chain(root, snapshot["task_id"], through_receipt_id=boxes[0]["receipt_id"])
    if invalid or boxes[0] not in receipts:
        raise w.WorkflowError("valid exact original producer receipt prefix required")
    producer_box = w.read_json(w.safe_path(root, proof["producer_outbox"]["path"]))
    w.validate_outbox(root, [proof["producer_outbox"]], producer, snapshot["task_id"])
    intake = [row for row in w._result_handoff_rows(root, snapshot["task_id"])
              if row.get("record_id") == proof.get("intake_record_id")
              and row.get("event") == "controller_received" and row.get("coordinator_role") == reviewer
              and row.get("outbox") == proof["producer_outbox"]
              and row.get("sender_department") == producer
              and row.get("candidate_version") == producer_box.get("candidate_version")]
    if len(intake) != 1:
        raise w.WorkflowError("actual assigned assistant original result intake required")
    source = w.read_json(w.safe_path(root, proof["reviewer_source_outbox"]["path"]))
    w.validate_outbox(root, [proof["reviewer_source_outbox"]], reviewer, snapshot["task_id"])
    native = w.read_json(w.safe_path(root, proof["reviewer_native_reply"]["path"]))
    reply = source.get("chat_reply", {})
    text = native.get("text")
    native_sha = hashlib.sha256(text.encode("utf-8")).hexdigest() if isinstance(text, str) and text.strip() else None
    if (source.get("schema_version") != "2.0" or source.get("task_id") != snapshot["task_id"] or source.get("department") != reviewer
            or source.get("fixed_chat_task_id") != fixed[reviewer].get("chat_binding", {}).get("task_id")
            or native.get("task_id") != snapshot["task_id"] or native.get("fixed_chat_task_id") != source["fixed_chat_task_id"]
            or native.get("cwd") != str(Path(root).resolve())
            or native.get("nonempty") is not True or native.get("in_current_fixed_department_chat") is not True
            or not native.get("source_message_id") or not native.get("source_turn_id")
            or not native_sha or native.get("message_sha256") != native_sha or native.get("utf8_bytes") != len(text.encode("utf-8"))
            or reply.get("proof") != proof["reviewer_native_reply"] or reply.get("message_sha256") != native_sha
            or reply.get("source_message_id") != native["source_message_id"] or reply.get("source_turn_id") != native["source_turn_id"]
            or reply.get("nonempty") is not True or reply.get("in_current_fixed_department_chat") is not True):
        raise w.WorkflowError("exact existing native reviewer reply provenance required")
    stamps = [w._parse_observed_at(value) for value in
              (boxes[0].get("created_at"), intake[0].get("created_at"), source.get("created_at"))]
    if any(value is None for value in stamps) or not stamps[0] <= stamps[1] <= stamps[2] <= dt.datetime.now(dt.timezone.utc):
        raise w.WorkflowError("ordered original producer/intake/reviewer source timestamps required")
    return {"proof": proof, "producer_receipt_created_at": boxes[0]["created_at"],
            "reviewer_source_created_at": source.get("created_at"),
            "original_native_responsibility": responsibility,
            "prepared_only": True, "reviewer_dispatch_fabricated": False,
            "external_permission_issued": False}


def owner_direct_review_context(root, snapshot, binding=None):
    """Read an already bound plan's exact origin; metadata grants no permission."""
    binding = _binding(root, snapshot) if binding is None else binding
    if not isinstance(binding, dict) or "owner_direct_review" not in binding:
        return None
    w = _workflow()
    pin = binding.get("pin", {})
    if w.file_digest(root, pin.get("path", "")) != pin:
        raise w.WorkflowError("owner-direct frozen review plan changed")
    plan = w.read_json(w.safe_path(root, pin["path"]))
    proof = binding["owner_direct_review"]
    if plan.get("owner_direct_review") != proof:
        raise w.WorkflowError("owner-direct binding differs from exact original proof")
    return prepare_owner_direct_review(root, snapshot, proof)


def _strict_source_rows(root, task_id):
    w = _workflow()
    try:
        rows = [json.loads(line) for line in w.receipts_path(root, task_id).read_text().splitlines() if line.strip()]
    except (OSError, ValueError) as exc:
        raise w.WorkflowError("strict original responsibility receipts required") from exc
    if any(not isinstance(row, dict) for row in rows):
        raise w.WorkflowError("original responsibility receipt objects required")
    return rows


def prepare_native_multi_goal_review(root, snapshot, proof):
    """Consume the original multi-goal responsibility, without relabelling a send.

    The source task's real send/ACK authenticates the frozen received message.
    Each covered goal retains its own human, contract and producer round. This
    is review provenance only: no dispatch, account grant or goal PASS is made.
    """
    from goal_delivery_runtime import validate_goal, _native_document
    w = _workflow()
    goal = _goal(root, snapshot)
    reviewer = _goal_reviewer(root, snapshot)
    if (not isinstance(proof, dict) or proof.get("schema_version") != 1 or goal is None
            or proof.get("task_id") != snapshot.get("task_id")
            or proof.get("responsible_assistant") != reviewer
            or proof.get("producer_department") != goal.get("primary_owner")
            or goal.get("producer_departments") != [proof.get("producer_department")]
            or goal.get("acceptance_capability") != "development"
            or proof.get("scope") not in goal.get("authorized_scope", [])
            or proof.get("authority") != goal.get("authorization_pin")
            or proof.get("goal_contract") != snapshot.get("goal_contract")):
        raise w.WorkflowError("exact original independent multi-goal review identity required")
    validate_goal(root, goal)
    for name in ("authority", "goal_contract", "reviewer_native_responsibility", "reviewer_responsibility_input"):
        pin = proof.get(name)
        if not isinstance(pin, dict) or w.file_digest(root, pin.get("path", "")) != pin:
            raise w.WorkflowError("exact original multi-goal source pin required: " + name)
    contract = w.read_json(w.safe_path(root, proof["goal_contract"]["path"]))
    contract = contract.get("goal_delivery", contract)
    if (any(contract.get(key) != goal.get(key) for key in GOAL_IDENTITY)
            or contract.get("source_mode") != goal.get("source_mode")
            or contract.get("human_authorization") != goal.get("human_authorization")):
        raise w.WorkflowError("original multi-goal contract/human/source mode changed")
    registry = w.department_registry(root)
    producer = proof["producer_department"]
    if reviewer != "operations-assistant-2" or producer != "system-development":
        raise w.WorkflowError("original A2 system-development responsibility required")
    headquarters = registry.get("operations", {}).get("chat_binding", {})
    if any(not binding.get("project_id") or binding.get("project_id") != headquarters.get("project_id")
           or binding.get("cwd") != str(Path(root).resolve()) for binding in
           (headquarters, registry[reviewer].get("chat_binding", {}), registry[producer].get("chat_binding", {}))):
        raise w.WorkflowError("original responsibility must stay in the exact fixed local project")
    responsibility = _owner_direct_native_input(root, proof["reviewer_native_responsibility"],
        proof["reviewer_responsibility_input"], reviewer, "operations", registry)
    sections = re.split(r"(?m)^\d+[.、] ", responsibility["input"])[1:]
    exact = [section for section in sections if _exact_text_reference(section, snapshot["task_id"])]
    if len(exact) != 1:
        raise w.WorkflowError("one exact goal in original native responsibility required")
    task_refs = set(re.findall(r"(?<![A-Za-z0-9_-])fc-[A-Za-z0-9_-]+", exact[0]))
    scope_refs = set(re.findall(r"project:[A-Za-z0-9_:.-]+", exact[0]))
    if (task_refs != {snapshot["task_id"]} or scope_refs - set(goal["authorized_scope"])
            or (goal.get("source_mode") == "approved_dispatch" and proof["scope"] not in scope_refs)):
        raise w.WorkflowError("exact original responsibility goal/scope required")
    source_task = w.validate_task_id(proof.get("source_task_id", ""))
    source_snapshot = _review_context(root, w.read_json(w.snapshot_path(root, source_task)))
    source_goal = _goal(root, source_snapshot)
    if (source_goal is None or source_goal.get("responsible_assistant") != reviewer
            or source_goal.get("primary_owner") != producer
            or source_goal.get("producer_departments") != [producer]
            or source_goal.get("acceptance_capability") != "development"
            or source_goal.get("parent_task_id") != goal.get("parent_task_id")
            or not any(_exact_text_reference(section, source_task) for section in sections)):
        raise w.WorkflowError("actual original source task/assigned responsibility required")
    validate_goal(root, source_goal)
    rows = _strict_source_rows(root, source_task)
    def exact_receipt(kind):
        selected = [row for row in rows if row.get("receipt_id") == proof.get(kind + "_receipt_id")]
        if (len(selected) != 1 or selected[0].get("receipt_hash") != proof.get(kind + "_receipt_hash")
                or selected[0].get("receipt_type") != {"dispatch": "dispatch_sent", "ack": "chat_ack"}[kind]
                or selected[0].get("task_id") != source_task or selected[0].get("department") != reviewer
                or selected[0].get("chat_task_id") != responsibility["receiver_thread_id"]):
            raise w.WorkflowError("one exact original multi-goal " + kind + " receipt required")
        return selected[0]
    dispatch, ack = exact_receipt("dispatch"), exact_receipt("ack")
    if rows.index(ack) <= rows.index(dispatch) or ack.get("ack_nonempty") is not True:
        raise w.WorkflowError("ordered real multi-goal send/ACK required")
    validated, invalid = w._validate_receipt_chain(root, source_task, through_receipt_id=ack["receipt_id"])
    if invalid or dispatch not in validated or ack not in validated:
        raise w.WorkflowError("valid original multi-goal receipt prefix required")
    policies = [row for row in w.read_jsonl(root / w.POLICY_DECISIONS)
                if row.get("decision_id") == dispatch.get("policy_decision_id")]
    binding = registry[reviewer]["chat_binding"]
    expected = {"status": "allow", "routing_status": "routing_allowed", "department": "operations",
                "task_id": source_task, "action_id": dispatch.get("action_id"), "action_class": "thread_message",
                "scope": dispatch.get("scope"), "target_department": reviewer,
                "target_thread_id": binding["task_id"], "target_project_id": binding["project_id"],
                "source_project_id": binding["project_id"], "target_cwd": str(Path(root).resolve()),
                "payload_sha256": proof["reviewer_responsibility_input"]["sha256"]}
    if len(policies) != 1 or any(policies[0].get(key) != value for key, value in expected.items()):
        raise w.WorkflowError("original native responsibility must match actual exact HQ policy bytes")
    send_docs = [_native_document(root, pin) for pin in dispatch.get("evidence", [])
                 if pin.get("path", "").endswith(".json")]
    if not any(doc.get("threadId") == responsibility["receiver_thread_id"] for doc in send_docs):
        raise w.WorkflowError("actual original responsibility send target required")
    native_acks = [_native_document(root, pin) for pin in ack.get("evidence", [])
                   if pin.get("path", "").endswith(".json")]
    def actual_ack(doc):
        if doc.get("thread", {}).get("id") != binding["task_id"] or doc.get("thread", {}).get("cwd") != str(Path(root).resolve()):
            return False
        return any(turn.get("id") == responsibility["turn_id"] and any(
            item.get("type") == "functionCallOutput" and item.get("id") == responsibility["native_item_id"]
            and item.get("name") == "send_message_to_thread" and item.get("namespace") == "codex_app"
            for item in turn.get("items", [])) and any(item.get("type") == "agentMessage"
                and isinstance(item.get("text"), str) and item["text"].strip() for item in turn.get("items", []))
            for turn in doc.get("turns", []))
    if not any(actual_ack(doc) for doc in native_acks):
        raise w.WorkflowError("actual original ACK must bind the same received native function/turn")
    own_rows = _strict_source_rows(root, snapshot["task_id"])
    original_acks = [row for row in own_rows if row.get("department") == producer
                     and row.get("receipt_type") == "chat_ack" and row.get("ack_nonempty") is True]
    if not original_acks:
        raise w.WorkflowError("this goal's own actual producer ACK required")
    checked, invalid = w._validate_receipt_chain(root, snapshot["task_id"], through_receipt_id=original_acks[0]["receipt_id"])
    if invalid or original_acks[0] not in checked:
        raise w.WorkflowError("this goal's original producer prefix required")
    stamps = [w._parse_observed_at(row.get("created_at")) for row in (dispatch, ack)]
    if any(x is None for x in stamps) or stamps != sorted(stamps) or stamps[-1] > dt.datetime.now(dt.timezone.utc):
        raise w.WorkflowError("original multi-goal send/ACK time order required")
    return {"dispatch": dispatch, "ack": ack, "source_task_id": source_task,
            "dispatch_index": rows.index(dispatch), "ack_index": rows.index(ack),
            "native_multi_goal_review": proof, "original_native_responsibility": responsibility,
            "prepared_only": True, "reviewer_dispatch_fabricated": False,
            "external_permission_issued": False, "parent_goal_completed": False}


def native_multi_goal_review_context(root, snapshot, binding=None):
    """Read the exact bound original source; never create a task ACK."""
    w = _workflow()
    binding = _binding(root, snapshot) if binding is None else binding
    if not isinstance(binding, dict) or "native_multi_goal_review" not in binding:
        return None
    pin = binding.get("pin", {})
    if w.file_digest(root, pin.get("path", "")) != pin:
        raise w.WorkflowError("original native multi-goal review plan changed")
    plan = w.read_json(w.safe_path(root, pin["path"]))
    proof = binding["native_multi_goal_review"]
    if plan.get("native_multi_goal_review") != proof:
        raise w.WorkflowError("bound plan differs from original multi-goal proof")
    return prepare_native_multi_goal_review(root, snapshot, proof)


def _tnew_source_goal(root, snapshot):
    """One original goal identity; this reader issues no review or permission."""
    w = _workflow()
    task = "fc-20261011-goal-publication-notice-followthrough-repair-v1"
    scope = "project:flashcast:goal-publication-notice-followthrough-repair:v1"
    prefix = "logs/handoffs/2026-10-11-goal-publication-notice-followthrough-repair-v1/"
    contract = {"path": prefix + "HQ-prepared/goal-input-PREPARED-v1.json",
        "sha256": "c1ef5c9395c36b5838f945a9d57f579a2bea6654c09135b58188509a6ec8c194", "size": 10977}
    human = {"path": prefix + "HQ-prepared/human-authorization-native.json",
        "sha256": "6492c4032ab17a65cab6dda864a159a0cb8957d842d70bb283acb1eb5ceb217f", "size": 1010}
    goal = _goal(root, snapshot)
    if (snapshot.get("task_id") != task or snapshot.get("goal_contract") != contract or goal is None
            or goal.get("authorization_pin") != human or goal.get("authorized_scope") != [scope]
            or goal.get("primary_owner") != "system-development" or goal.get("producer_departments") != ["system-development"]
            or goal.get("responsible_assistant") != "operations-assistant-2" or goal.get("acceptance_capability") != "development"
            or goal.get("source_mode", "approved_dispatch") != "approved_dispatch" or goal.get("required_execution_actions")):
        raise w.WorkflowError("exact original TNEW source authority and independent responsibility required")
    original = _review_source_document(root, contract)
    _review_source_document(root, human)
    if not _initial_goal_identity(root, snapshot, original.get("goal_delivery", original)):
        raise w.WorkflowError("original TNEW goal contract cannot be replaced")
    return goal


def tnew_entry_bootstrap_responsibility(root, snapshot, manifest_pin, contract_pin, *,
        defer_assignment=False, assignment_backings=None, assignment_fields=()):
    """Read the exact reviewed adjacent helper, without inventing a bound plan."""
    import importlib.util
    import sys
    w = _workflow()
    root = Path(root).resolve()
    goal = _tnew_source_goal(root, snapshot)
    if type(defer_assignment) is not bool or (defer_assignment and assignment_backings is not None):
        raise w.WorkflowError("separate bootstrap effect and complete responsibility reads required")
    contract = _review_source_document(root, contract_pin)
    manifest = _review_source_document(root, manifest_pin)
    flags = ("production_write_allowed", "production_release_eligible", "external_permission_issued",
             "goal_completion_claimed", "final_goal_verdict", "pilot_complete")
    fields = {"schema", "task_id", "scope", "candidate_version", "candidate_fingerprint", "candidate_manifest",
        "producer_outbox", "goal_contract", "human_authorization", "HQ_scope_decision", "historical_review_plan",
        "historical_source_continuation", "original_goal_continuation_sources", "normal_review_plan",
        "producer_department", "reviewer_department", "controller_department", "action_class", "risk_level", "prepared_only", *flags}
    if (set(contract) != fields or contract.get("schema") != "flashcast-source-bootstrap-review-contract/v1"
            or contract.get("candidate_manifest") != manifest_pin or contract.get("normal_review_plan") is not None
            or contract.get("prepared_only") is not False or any(contract.get(key) is not False for key in flags)
            or any(contract.get(key) != value for key, value in {"task_id": snapshot["task_id"],
                "scope": goal["authorized_scope"][0], "goal_contract": snapshot["goal_contract"],
                "human_authorization": goal["authorization_pin"], "producer_department": "system-development",
                "reviewer_department": "operations-assistant-2", "controller_department": "operations-assistant-2",
                "action_class": "internal_control_candidate", "risk_level": "R0"}.items())
            or contract.get("candidate_version") != manifest.get("candidate_version")
            or contract.get("candidate_fingerprint") != manifest.get("candidate_fingerprint")):
        raise w.WorkflowError("exact plan-free original bootstrap review contract required")
    if (manifest.get("schema") != "flashcast-exact-source-candidate/v1"
            or any(manifest.get(key) != contract[key] for key in
                ("task_id", "scope", "candidate_version", "candidate_fingerprint", "goal_contract", "human_authorization"))
            or manifest.get("primary_owner") != contract["producer_department"]
            or manifest.get("responsible_assistant") != contract["reviewer_department"]
            or manifest.get("project_root") != str(root)
            or manifest.get("candidate_fingerprint") != w.sha256_value({key: value for key, value in manifest.items()
                if key != "candidate_fingerprint"}) or any(manifest.get(key) is not False for key in flags)):
        raise w.WorkflowError("exact original five-source bootstrap manifest identity required")
    required_paths = {"tools/qa_review_plan.py", "tools/paid_three_page_bounded_cms.py", "tools/workflow_control.py",
                      "tools/goal_delivery_runtime.py", "tools/parent_initial_dispatch.py"}
    if ({row.get("path") for row in manifest.get("files", [])} != required_paths
            or len(manifest["files"]) != len(required_paths) or manifest.get("field_changes") != []):
        raise w.WorkflowError("only original five-source zero-field bootstrap entry package required")
    helper_pin = manifest.get("source_review_helper")
    _closed_review_source_pins(root, [helper_pin])
    directory = Path(manifest_pin["path"]).parent
    if (helper_pin.get("path") != str(directory / "rollback/source_review_context.py")
            or helper_pin not in manifest.get("inputs", []) or manifest.get("source_successor_helper") != helper_pin):
        raise w.WorkflowError("one exact adjacent reviewed bootstrap helper required")
    path = w.safe_path(root, helper_pin["path"])
    raw = path.read_bytes()
    if path.is_symlink() or any(parent.is_symlink() for parent in path.parents) or path != path.resolve():
        raise w.WorkflowError("physical canonical reviewed bootstrap helper required")
    name = "_flashcast_tnew_bootstrap_" + helper_pin["sha256"]
    prior = sys.modules.get(name)
    spec = importlib.util.spec_from_file_location(name, path)
    helper = importlib.util.module_from_spec(spec)
    sys.modules[name] = helper
    try:
        exec(compile(raw, str(path), "exec"), helper.__dict__)
        if (helper.TASK != snapshot["task_id"] or helper.SCOPE != contract["scope"]
                or helper.VERSION != contract["candidate_version"] or helper.ROLE != contract["reviewer_department"]
                or helper.PRODUCER != contract["producer_department"] or set(helper.SOURCE_PATHS) != required_paths):
            raise w.WorkflowError("reviewed bootstrap helper must retain original exact package identity")
        result = helper.bootstrap_responsibility(root, snapshot, manifest_pin, contract_pin,
            defer_assignment=defer_assignment, assignment_backings=assignment_backings, assignment_fields=assignment_fields)
        if (not isinstance(result, dict) or set(result) != {"contract_pin", "producer_pin", "historical_plan_pin",
                "historical_continuation_pin", "identity", "receipt_id", "queue_record_id", "intake_record_id",
                "responsibility_windows", "producer_window", "normal_review_plan", "read_only"}
                or result.get("contract_pin") != contract_pin
                or result.get("producer_pin") != contract["producer_outbox"]
                or result.get("historical_plan_pin") != contract["historical_review_plan"]
                or result.get("historical_continuation_pin") != contract["historical_source_continuation"]
                or result.get("identity") != {"task_id": snapshot["task_id"], "sender_department": contract["producer_department"],
                    "candidate_version": contract["candidate_version"], "result_sha256": contract["producer_outbox"]["sha256"]}
                or result.get("normal_review_plan") is not None or result.get("read_only") is not True
                or any(not isinstance(result.get(key), str) or not result[key] for key in
                    ("receipt_id", "queue_record_id", "intake_record_id"))
                or (not defer_assignment and (not isinstance(result.get("responsibility_windows"), list)
                    or not result["responsibility_windows"] or not isinstance(result.get("producer_window"), dict)))
                or (defer_assignment and (result.get("responsibility_windows") is not None or result.get("producer_window") is not None))):
            raise w.WorkflowError("exact original bootstrap responsibility result required")
        if w.file_digest(root, helper_pin["path"]) != helper_pin or path.read_bytes() != raw:
            raise w.WorkflowError("reviewed bootstrap helper changed during its read")
        return result
    finally:
        if prior is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = prior


def prepare_tnew_parent_initial_child_review(root, snapshot, proof):
    """Only criterion 12 inherits proven original parent responsibility."""
    import parent_initial_child_review as child_source
    import parent_initial_dispatch as initial
    import goal_delivery_runtime as g
    from scoped_candidate_adoption import _committed, _receipts
    w = _workflow()
    root = Path(root).resolve()
    fields = child_source.FIELDS | {"parent_original_responsibility_sources", "parent_adoption"}
    if (not isinstance(proof, dict) or set(proof) != fields or type(proof.get("schema_version")) is not int
            or proof["schema_version"] != 1 or proof.get("mode") != "tnew_parent_initial_read_only"):
        raise w.WorkflowError("explicit original TNEW criterion-12 child source required")
    parent = child_source._snapshot(root, w.read_json(w.snapshot_path(root, proof["parent_task_id"])))
    parent_goal = _tnew_source_goal(root, parent)
    child = child_source._snapshot(root, snapshot)
    goal = child["goal_delivery"]
    scope, producer, reviewer = parent_goal["authorized_scope"][0], "system-development", "operations-assistant-2"
    if (proof.get("task_id") != child["task_id"] or child["task_id"] == parent["task_id"]
            or goal.get("parent_task_id") != parent["task_id"] or goal.get("initial_dispatch_mode") != "read_only"
            or goal.get("source_mode") != "approved_dispatch" or goal.get("required_execution_actions") or goal.get("collaboration_scopes")
            or proof.get("producer_department") != producer or proof.get("responsible_assistant") != reviewer
            or proof.get("scope") != scope or goal.get("authorized_scope") != [scope]
            or proof.get("authority") != parent_goal["authorization_pin"] or goal.get("authorization_pin") != proof["authority"]
            or goal.get("human_authorization") != parent_goal["human_authorization"]
            or proof.get("goal_contract") != child.get("goal_contract") or proof.get("parent_goal_contract") != parent["goal_contract"]
            or goal.get("primary_owner") != producer or goal.get("producer_departments") != [producer]
            or goal.get("responsible_assistant") != reviewer or goal.get("acceptance_capability") != "development"
            or any(goal.get(key, False) is not False for key in ("production_write_allowed", "production_release_eligible", "external_permission_issued"))):
        raise w.WorkflowError("exact original TNEW parent/child human and read-only identity required")
    declarations = g._completion_contract(root, parent).get("requirements", [])
    if len([row for row in declarations if row.get("requirement_id") == "original-criterion-12"
            and row.get("criterion_index") == 11 and row.get("requirement_type") == "internal_pilot"]) != 1:
        raise w.WorkflowError("only original criterion 12 internal pilot may inherit this responsibility")
    adopted = w.tnew_adopted_completion_context(root, parent, proof["parent_adoption"])
    parent_plan = load_plan(root, parent)
    sources = proof["parent_original_responsibility_sources"]
    if (parent_plan is None or not isinstance(sources, list) or len(sources) != 17
            or len({value.get("path") for value in sources if isinstance(value, dict)}) != 17
            or sources != parent_plan.get("original_goal_continuation_sources")):
        raise w.WorkflowError("exact original parent responsibility full-pin array required")
    _closed_review_source_pins(root, sources)
    continuation_pin = parent_plan.get("adopted_source_continuation")
    authenticated, last, contract = _tnew_actual_bootstrap_context(root, parent, continuation_pin)
    if (proof["parent_adoption"].get("actual_source_successors") !=
            [row["continuation_pin"] for row in authenticated["layers"]]
            or parent_plan.get("candidate") != adopted["producer_outbox"]
            or last.get("producer_pin") != adopted["producer_outbox"]
            or contract.get("producer_outbox") != adopted["producer_outbox"]
            or sources != contract.get("original_goal_continuation_sources")
            or parent_plan.get("candidate_version") != last.get("candidate_version")
            or adopted.get("candidate_manifest") != last.get("manifest_pin")):
        raise w.WorkflowError("child must retain its currently bound actually adopted parent PP and complete succession")
    parent_manifest = _review_source_document(root, last["manifest_pin"])
    if not all(value in parent_manifest.get("inputs", []) for value in sources):
        raise w.WorkflowError("all original parent responsibility inputs must belong to the exact adopted manifest")
    tnew_entry_bootstrap_responsibility(root, parent, last["manifest_pin"], last["bootstrap_review_contract"],
        assignment_backings=authenticated["source_backings"], assignment_fields=authenticated["field_effects"])
    registry = w.department_registry(root)
    planned = {row.get("department"): row for row in child.get("departments", [])}
    if any(planned.get(role, {}).get("chat_task_id") != registry[role]["chat_binding"]["task_id"] for role in (producer, reviewer)):
        raise w.WorkflowError("exact independent fixed child producer and reviewer required")
    rows = _receipts(root, child["task_id"])
    if len({row.get("receipt_id") for row in rows}) != len(rows):
        raise w.WorkflowError("unique complete original child receipt identities required")
    if any(row.get("department") in {"qa", "qa-technical"}
            or (row.get("department") == reviewer and row.get("receipt_type") in
                {"dispatch_sent", "dispatch_failed", "chat_ack"}) for row in rows):
        raise w.WorkflowError("first inherited child source cannot replace reviewer dispatch or ACK history")
    selected = []
    for kind, name in (("dispatch_sent", "dispatch"), ("chat_ack", "ack"), ("outbox_received", "producer_outbox")):
        found = [row for row in rows if row.get("receipt_id") == proof.get(name + "_receipt_id")]
        if (len(found) != 1 or found[0].get("receipt_hash") != proof.get(name + "_receipt_hash")
                or found[0].get("receipt_type") != kind or found[0].get("department") != producer
                or (kind in {"dispatch_sent", "chat_ack"} and found[0].get("chat_task_id") != registry[producer]["chat_binding"]["task_id"])
                or (found[0].get("chat_task_id") and found[0]["chat_task_id"] != registry[producer]["chat_binding"]["task_id"])):
            raise w.WorkflowError("one exact actual child producer receipt required")
        selected.append(found[0])
    dispatch, ack, outbox = selected
    if (not rows.index(dispatch) < rows.index(ack) < rows.index(outbox) or ack.get("ack_nonempty") is not True
            or [row for row in rows if row.get("department") == producer and row.get("receipt_type") in {"dispatch_sent", "dispatch_failed"}] != [dispatch]
            or [row for row in rows if row.get("department") == producer and row.get("receipt_type") == "outbox_received"] != [outbox]
            or any(row.get("supersedes_receipt_id") in {item["receipt_id"] for item in selected} for row in rows)):

        raise w.WorkflowError("only the true first child send/ACK/completed result may inherit responsibility")
    actions = [row for row in goal.get("approved_actions", []) if row.get("action_id") == proof.get("action_id")]
    if len(actions) != 1:
        raise w.WorkflowError("one approved actual child first-send action required")
    action = actions[0]
    source = action.get("parent_initial_dispatch", {})
    if source.get("adoption") != proof["parent_adoption"]:
        raise w.WorkflowError("child source must retain the actual parent adopted proof")
    context = initial._context(root, parent, source, "sent")
    decision = initial._fenced_decision(root, parent, action, "sent")
    if (action.get("decision_record_id") != proof.get("parent_decision_record_id")
            or any(action.get(key) != context["action"].get(key) for key in initial.ACTION_FIELDS)
            or source.get("child_contract") != child["goal_contract"] or context["adopted"] != adopted):
        raise w.WorkflowError("exact consumed child decision/action/adoption required")
    metadata = dispatch.get("parent_initial_dispatch", {})
    expected = {"parent_task_id": parent["task_id"], "decision_record_id": decision["record_id"],
        "coordinator_role": reviewer, "coordinator_owner": decision["coordinator_owner"], "coordination_fence": decision["coordination_fence"],
        "child_contract": child["goal_contract"], "parent_contract": parent["goal_contract"], "human_authorization": goal["authorization_pin"],
        "adoption": adopted, "external_permission_issued": False, "actual_message_sent": True, "new_permissions": 0}
    if (any(metadata.get(key) != value for key, value in expected.items()) or proof.get("policy_decision_id") != dispatch.get("policy_decision_id")
            or dispatch.get("action_id") != action["action_id"] or dispatch.get("action_class") != "thread_message" or dispatch.get("scope") != scope
            or any(ack.get(key) != dispatch.get(key) for key in ("task_id", "action_id", "action_class", "scope", "policy_decision_id"))):
        raise w.WorkflowError("actual child first-send provenance and ACK identity required")
    initial._policy(root, action, proof["policy_decision_id"])
    child_source._native_effect(root, action, dispatch, metadata, source)
    result_pin = proof["producer_outbox"]
    result = _review_source_document(root, result_pin)
    w.validate_outbox(root, [result_pin], producer, child["task_id"])
    if (result_pin not in outbox.get("evidence", []) or result.get("parent_task_id") != parent["task_id"]
            or result.get("status") != "completed" or result.get("department") != producer
            or result.get("fixed_chat_task_id") != registry[producer]["chat_binding"]["task_id"]
            or any(result.get(key) is True for key in ("fixture_only", "simulation", "simulated"))
            or any(result.get(key, False) is not False for key in ("production_write_allowed", "production_release_eligible", "external_permission_issued"))):
        raise w.WorkflowError("actual completed independent child result without external writes required")
    identity = {"task_id": child["task_id"], "sender_department": producer, "candidate_version": result["candidate_version"],
                "result_sha256": result_pin["sha256"], "outbox": result_pin}
    handoffs = w._result_handoff_rows(root, child["task_id"])
    selected_handoffs = []
    for event, key in (("notification_queued", "notification_record_id"), ("controller_received", "controller_received_record_id")):
        found = [row for row in handoffs if row.get("event") == event and all(row.get(key) == value for key, value in identity.items())]
        if len(found) != 1 or found[0].get("record_id") != proof.get(key):
            raise w.WorkflowError("one exact actual child completion queue and independent intake required")
        selected_handoffs.append(found[0])
    queued, intake = selected_handoffs
    if (intake.get("coordinator_role") != reviewer or intake.get("responsible_assistant") != reviewer
            or intake.get("decision_actor") != reviewer or handoffs.index(queued) >= handoffs.index(intake)):
        raise w.WorkflowError("actual independent child result intake required")
    _committed(root, intake)
    w._validate_goal_completed_result(root, queued, registry[producer]["chat_binding"]["task_id"], through_receipt_id=outbox["receipt_id"])
    stamps = [_review_observed_at(row.get("created_at")) for row in (decision, dispatch, ack, outbox, queued, intake)]
    if any(value is None for value in stamps) or stamps != sorted(stamps) or stamps[-1] > dt.datetime.now(dt.timezone.utc):
        raise w.WorkflowError("actual child decision/send/ACK/result/queue/intake time order required")
    return {"source_kind": "parent_initial_child_review", "source_task_id": parent["task_id"], "proof": proof,
        "producer_dispatch": dispatch, "producer_ack": ack, "producer_outbox_receipt": outbox,
        "notification": queued, "controller_received": intake, "reviewer_source_created_at": intake["created_at"],
        "prepared_only": True, "reviewer_dispatch_fabricated": False, "reviewer_ack_fabricated": False,
        "external_permission_issued": False, "parent_goal_completed": False}


def _prepare_parent_initial_child_review(root, snapshot, proof):
    if isinstance(proof, dict) and proof.get("mode") == "tnew_parent_initial_read_only":
        return prepare_tnew_parent_initial_child_review(root, snapshot, proof)
    from parent_initial_child_review import prepare
    return prepare(root, snapshot, proof)


def parent_initial_child_review_context(root, snapshot, binding=None):
    """Read the child's real inherited responsibility, never a reviewer ACK."""
    w = _workflow()
    binding = _binding(root, snapshot) if binding is None else binding
    if not isinstance(binding, dict) or "parent_initial_child_review" not in binding:
        return None
    pin = binding.get("pin", {})
    if w.file_digest(root, pin.get("path", "")) != pin:
        raise w.WorkflowError("frozen parent-linked child review plan changed")
    plan = w.read_json(w.safe_path(root, pin["path"]))
    proof = binding["parent_initial_child_review"]
    if plan.get("parent_initial_child_review") != proof:
        raise w.WorkflowError("bound child plan differs from exact original first-send source")
    return _prepare_parent_initial_child_review(root, snapshot, proof)


def _same_goal_rework_notice(root, snapshot, receipts, dispatch, plan):
    """Recognize a fully recorded clarification of an existing producer rework.

    This transport says that the already assigned producer was actually sent
    the blocked rework. It carries no review assignment and supplies no ACK.
    Unknown messages, changed roles, failed sends and new assignments remain
    review-round boundaries. No task-specific receipt or action ID is exempted.
    """
    w = _workflow()
    try:
        def unique(pairs):
            value = {}
            for key, item in pairs:
                if key in value:
                    raise ValueError("duplicate same-goal rework source field")
                value[key] = item
            return value

        def document(pin):
            if (not isinstance(pin, dict) or set(pin) != {"path", "sha256", "size"}
                    or w.file_digest(root, pin.get("path", "")) != pin):
                raise ValueError("frozen same-goal rework source changed")
            value = json.loads(w.safe_path(root, pin["path"]).read_bytes(), object_pairs_hook=unique)
            if not isinstance(value, dict):
                raise ValueError("same-goal rework source object required")
            return value

        def native_result(value):
            content = value.get("content") if isinstance(value, dict) else None
            if (not isinstance(value, dict) or value.get("isError") is not False
                    or not isinstance(content, list) or len(content) != 1
                    or content[0].get("type") != "text" or not isinstance(content[0].get("text"), str)):
                raise ValueError("one successful native rework result required")
            result = json.loads(content[0]["text"], object_pairs_hook=unique)
            if (not isinstance(result, dict)
                    or ("structuredContent" in value and value["structuredContent"] != result)):
                raise ValueError("native rework result differs from structured result")
            return result

        goal = _goal(root, snapshot)
        task, reviewer, producer = snapshot["task_id"], plan["reviewer_department"], plan["producer_department"]
        scope, registry = plan["scope"], w.department_registry(root)
        if (goal is None or goal.get("responsible_assistant") != reviewer
                or producer not in goal.get("producer_departments", []) or producer == reviewer
                or scope not in goal.get("authorized_scope", []) or plan.get("task_id") != task):
            return False

        def transport(row, role, extra_fields):
            fixed, hq = [registry[name]["chat_binding"] for name in (role, "operations")]
            evidence = row.get("evidence", [])
            if (row.get("task_id") != task or row.get("department") != role
                    or row.get("receipt_type") != "dispatch_sent" or row.get("action_class") != "thread_message"
                    or row.get("scope") != scope or row.get("chat_task_id") != fixed.get("task_id")
                    or row.get("action_id") == "assign-goal-review:" + task
                    or not row.get("action_id") or row.get("supersedes_receipt_id") or row.get("approval_id")
                    or row.get("replacement_reason") or len(evidence) not in {1, 2}
                    or any(item.get("supersedes_receipt_id") == row.get("receipt_id") for item in receipts)
                    or fixed.get("cwd") != str(Path(root).resolve()) or hq.get("cwd") != fixed.get("cwd")
                    or not fixed.get("project_id") or fixed.get("project_id") != hq.get("project_id")):
                raise ValueError("same existing fixed-goal successful transport required")
            source = evidence[-1]
            send = document(source)
            compact = len(evidence) == 1
            if compact:
                if set(send) != {"task_id", "action_id", "payload_sha256", "payload_path", "policy_decision_id",
                                 "native_send", "native_fresh_identity"}:
                    raise ValueError("exact compact existing rework transport required")
                payload = w.file_digest(root, send.get("payload_path", ""))
                if Path(payload["path"]).parent != Path(source["path"]).parent:
                    raise ValueError("original same-package rework payload required")
            else:
                payload = evidence[0]
            if w.file_digest(root, payload.get("path", "")) != payload:
                raise ValueError("same-goal payload bytes changed")
            text = w.safe_path(root, payload["path"]).read_bytes().decode("utf-8")
            expected = {"task_id": task, "action_id": row["action_id"],
                        "payload_sha256": payload["sha256"],
                        "policy_decision_id": row.get("policy_decision_id")}
            expected.update({"payload_path": payload["path"]} if compact else
                            {"payload_bytes": payload["size"], **extra_fields})
            if ((not compact and set(send) != set(expected) | {"native_send", "actual_live_identity"})
                    or any(send.get(key) != value for key, value in expected.items())
                    or native_result(send["native_send"]) != {"threadId": fixed["task_id"]}):
                raise ValueError("exact existing rework purpose and successful native send required")
            live = native_result(send["native_fresh_identity" if compact else "actual_live_identity"])
            targets = [item for group in ("pinnedThreads", "threads") for item in live.get(group, [])
                       if isinstance(item, dict) and item.get("id") == fixed["task_id"]]
            if (live.get("schemaVersion") != 4 or len(targets) != 1
                    or any(targets[0].get(key) != value for key, value in {
                        "kind": "codex", "hostId": "local", "title": fixed["title"], "cwd": fixed["cwd"],
                        "projectId": fixed["project_id"]}.items())):
                raise ValueError("exact live fixed receiver identity required")
            policies = [item for item in w.read_jsonl(root / w.POLICY_DECISIONS)
                        if item.get("decision_id") == row.get("policy_decision_id")]
            expected_policy = {"status": "allow", "routing_status": "routing_allowed", "task_id": task,
                "department": "operations", "action_id": row["action_id"], "action_class": "thread_message",
                "scope": scope, "payload_sha256": payload["sha256"], "target_department": role,
                "target_thread_id": fixed["task_id"], "target_thread_title": fixed["title"],
                "target_cwd": fixed["cwd"], "source_project_id": fixed["project_id"],
                "target_project_id": fixed["project_id"], "target_sidebar_section_id": fixed.get("sidebar_section_id"),
                "routing_quarantine_mode": False, "routing_health_probe_mode": False}
            if len(policies) != 1 or any(policies[0].get(key) != value for key, value in expected_policy.items()):
                raise ValueError("exact original rework policy required")
            checked, sent = [w._parse_observed_at(value) for value in
                             (policies[0].get("checked_at"), row.get("created_at"))]
            if checked is None or sent is None or not checked <= sent <= dt.datetime.now(dt.timezone.utc):
                raise ValueError("ordered real rework policy/send time required")
            return payload, source, text, sent, compact

        notice_payload, notice_source, text, notice_at, compact = transport(dispatch, reviewer, {
            "purpose": "Resolve current sender-approval question with already actually dispatched original SYS rework; no new human permission or additional assistant sends"})
        if (not _exact_text_reference(text, task)
                or not dispatch.get("action_id", "").startswith("clarify-original-")):
            return False
        index = receipts.index(dispatch)
        blocked = [row for row in receipts[:index] if row.get("receipt_type") == "qa_verdict"
                   and row.get("department") == reviewer and row.get("verdict") == "blocked"
                   and all(row.get(key) == plan.get(key) for key in ("task_id", "action_id", "action_class", "scope"))]
        if not blocked:
            return False
        original_block = blocked[-1]
        pins = [pin for pin in original_block.get("evidence", []) if pin.get("path", "").endswith(".json")]
        if len(pins) != 1:
            return False
        box = document(pins[0])
        if (box.get("task_id") != task or box.get("department") != reviewer or box.get("qa_verdict") != "blocked"
                or box.get("review_identity") != {**{key: plan[key] for key in IDENTITY if key not in
                   {"candidate_version", "candidate_sha256"}}, "candidate_version": box.get("candidate_version"),
                   "candidate_sha256": box.get("review_identity", {}).get("candidate_sha256")}
                or any(box.get(key) is not False for key in
                       ("production_write_allowed", "external_permission_issued", "production_release_eligible"))):
            return False
        matches = []
        for row in receipts[receipts.index(original_block) + 1:index]:
            if row.get("department") != producer or row.get("receipt_type") != "dispatch_sent":
                continue
            if not _exact_text_reference(text, row.get("receipt_id")):
                continue
            if not row.get("action_id", "").startswith("resume-original-"):
                continue
            payload, source, body, sent, producer_compact = transport(row, producer, {
                "existing_authorization_reference": goal["human_authorization"]["evidence_path"],
                "new_human_authorization_created": False})
            source_reference = source["path"]
            if compact and producer_compact:
                if (not row.get("action_id", "").startswith("resume-original-")
                        or Path(source["path"]).parent != Path(notice_source["path"]).parent):
                    continue
                source_reference = Path(source["path"]).name
                initial = [item for item in receipts[:receipts.index(original_block)]
                           if item.get("department") == reviewer and item.get("receipt_type") == "dispatch_sent"
                           and _initial_assignment(root, snapshot, item)]
                if len(initial) != 1:
                    continue
                initial_index = receipts.index(initial[0])
                next_send = next((i for i, item in enumerate(receipts[initial_index + 1:], initial_index + 1)
                                  if item.get("department") == reviewer
                                  and item.get("receipt_type") in {"dispatch_sent", "dispatch_failed"}), len(receipts))
                original_acks = [item for item in receipts[initial_index + 1:next_send]
                                 if item.get("department") == reviewer and item.get("receipt_type") == "chat_ack"
                                 and item.get("ack_nonempty") is True]
                producer_acks = [item for item in receipts[receipts.index(row) + 1:index]
                                 if item.get("department") == producer and item.get("receipt_type") == "chat_ack"
                                 and item.get("ack_nonempty") is True and _exact_text_reference(text, item.get("receipt_id"))]
                if (len(original_acks) != 1 or len(producer_acks) != 1
                        or not all(_exact_text_reference(body, item["receipt_id"]) for item in
                                   (initial[0], original_acks[0]))):
                    continue
                producer_ack = producer_acks[0]
                ack_pins = producer_ack.get("evidence", [])
                if len(ack_pins) != 1:
                    continue
                observed = native_result(document(ack_pins[0]))
                polls = [item for item in observed.get("polls", [])
                         if isinstance(item, dict) and item.get("thread", {}).get("id")
                         == registry[producer]["chat_binding"]["task_id"]]
                if len(polls) != 1:
                    continue
                poll, ack_at = polls[0], w._parse_observed_at(producer_ack.get("created_at"))
                turn, message = poll.get("latestTurn", {}), poll.get("latestAssistantMessage", {})
                if (producer_ack.get("chat_task_id") != registry[producer]["chat_binding"]["task_id"]
                        or ack_at is None or not sent <= ack_at <= notice_at or poll.get("schemaVersion") != 1
                        or not isinstance(poll.get("cursor"), str) or not poll["cursor"]
                        or type(poll.get("revision")) is not int or poll["revision"] <= 0
                        or turn.get("status") not in {"inProgress", "completed"} or turn.get("error")
                        or not turn.get("id") or type(turn.get("startedAt")) not in {int, float}
                        or not sent.timestamp() <= turn["startedAt"] <= ack_at.timestamp()
                        or not message.get("id") or message.get("id") != poll.get("latestAssistantMessageId")
                        or message.get("turnId") != turn["id"] or message.get("phase") not in {"commentary", "final_answer"}
                        or not isinstance(message.get("text"), str) or not message["text"].strip()):
                    continue
            elif compact != producer_compact:
                continue
            digest_reference = (bool(re.search(r"(?<![A-Za-z0-9])SHA256" + re.escape(payload["sha256"])
                                              + r"(?![A-Fa-f0-9])", text))
                                or _exact_text_reference(text, payload["sha256"]))
            if (all(_exact_text_reference(text, value) for value in (source_reference, row["policy_decision_id"]))
                    and digest_reference and str(payload["size"]) in text and _exact_text_reference(body, task)
                    and w._parse_observed_at(original_block.get("created_at")) <= sent <= notice_at):
                matches.append(row)
        return len(matches) == 1
    except (w.WorkflowError, OSError, ValueError, TypeError, KeyError, AttributeError):
        return False


def _review_source_document(root, pin, *, object_only=True):
    """Read one exact source object, rejecting ambiguous fields before use."""
    w = _workflow()
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError("duplicate original review source field")
            value[key] = item
        return value
    def constant(value):
        raise ValueError("finite original review source JSON required")
    if (not isinstance(pin, dict) or set(pin) != {"path", "sha256", "size"}
            or not isinstance(pin.get("path"), str) or not pin["path"]
            or not isinstance(pin.get("sha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", pin["sha256"])
            or type(pin.get("size")) is not int or pin["size"] < 0
            or w.file_digest(root, pin["path"]) != pin):
        raise ValueError("exact frozen original review source required")
    value = json.loads(w.safe_path(root, pin["path"]).read_bytes(),
                       object_pairs_hook=unique, parse_constant=constant)
    if object_only and not isinstance(value, dict):
        raise ValueError("original review source object required")
    return value


def _review_observed_at(value):
    parsed = _workflow()._parse_observed_at(value)
    if parsed is None and isinstance(value, str):
        try:
            parsed = dt.datetime.strptime(value, "%Y-%m-%d %H:%M:%S UTC").replace(tzinfo=dt.timezone.utc)
        except ValueError:
            pass
    return parsed


def _review_source_failed(value):
    return (not isinstance(value, dict) or bool(value.get("error"))
            or ("isError" in value and value["isError"] is not False)
            or ("truncated" in value and value["truncated"] is not False)
            or any(value.get(key) for key in ("superseded", "superseded_by", "supersedes_message_id", "supersedes_turn_id")))


def _modern_goal_assignment_send(root, snapshot, dispatch, contract_pin):
    """Read the ordinary eight-field complete-goal transport and actual policy.

    Return the original envelope and policy only after exact frozen-goal,
    registered-role, receipt-chain and successful native-target checks. A caller
    still has to prove the original ACK; this reader grants no review authority.
    """
    w = _workflow()
    try:
        task, goal = snapshot["task_id"], _goal(root, snapshot)
        registry = w.department_registry(root)
        role = dispatch.get("department")
        if goal is None or role not in {goal.get("responsible_assistant"), *goal.get("producer_departments", [])}:
            return None
        binding, hq = [registry[name]["chat_binding"] for name in (role, "operations")]
        action = ("assign-goal-review:" if role == goal["responsible_assistant"] else "dispatch-" + role + ":") + task
        contract = _review_source_document(root, contract_pin)
        contract = contract.get("goal_delivery", contract)
        if (not _initial_goal_identity(root, snapshot, contract)
                or any(contract.get(key) != goal.get(key) for key in ("parent_task_id", "human_authorization"))
                or contract.get("source_mode", "approved_dispatch") != goal.get("source_mode", "approved_dispatch")
                or contract.get("required_execution_actions", []) != goal.get("required_execution_actions", [])
                or w.file_digest(root, contract["human_authorization"]["evidence_path"]) != goal.get("authorization_pin")
                or dispatch.get("task_id") != task or dispatch.get("receipt_type") != "dispatch_sent"
                or dispatch.get("action_id") != action or dispatch.get("action_class") != "thread_message"
                or dispatch.get("scope") not in goal["authorized_scope"]
                or dispatch.get("chat_task_id") != binding["task_id"] or len(dispatch.get("evidence", [])) != 1
                or binding.get("cwd") != str(Path(root).resolve()) or hq.get("cwd") != binding["cwd"]
                or not binding.get("project_id") or hq.get("project_id") != binding["project_id"]
                or any(dispatch.get(key) for key in ("supersedes_receipt_id", "approval_id", "replacement_reason"))):
            return None
        receipts, previous = w.read_jsonl(w.receipts_path(root, task)), ""
        for row in receipts:
            if (row.get("task_id") != task or row.get("previous_hash", "") != previous
                    or row.get("receipt_hash") != w.sha256_value(w._receipt_payload_for_hash(row))):
                return None
            previous = row["receipt_hash"]
        if (len([row for row in receipts if row == dispatch]) != 1
                or len([row for row in receipts if row.get("department") == role
                        and row.get("action_id") == action and row.get("scope") == dispatch["scope"]
                        and row.get("receipt_type") in {"dispatch_sent", "dispatch_failed"}]) != 1
                or any(row.get("supersedes_receipt_id") == dispatch["receipt_id"] for row in receipts)):
            return None
        envelope = _review_source_document(root, dispatch["evidence"][0])
        expected = {"task_id": task, "department": role, "action_id": action,
                    "action_class": "thread_message", "scope": dispatch["scope"], "goal_contract": contract_pin}
        if (set(envelope) != set(expected) | {"policy_decision", "native_send"}
                or any(envelope.get(key) != value for key, value in expected.items())
                or _review_raw_native_result(envelope["native_send"]) != {"threadId": binding["task_id"]}):
            return None
        policies = [row for row in w.read_jsonl(root / w.POLICY_DECISIONS)
                    if row.get("decision_id") == dispatch.get("policy_decision_id")]
        expected_policy = {"status": "allow", "routing_status": "routing_allowed", "task_id": task,
            "department": "operations", "action_id": action, "action_class": "thread_message",
            "scope": dispatch["scope"], "payload_sha256": contract_pin["sha256"], "target_department": role,
            "target_thread_id": binding["task_id"], "target_thread_title": binding["title"], "target_cwd": binding["cwd"],
            "source_project_id": binding["project_id"], "target_project_id": binding["project_id"],
            "target_sidebar_section_id": binding.get("sidebar_section_id"), "approval_id": "",
            "routing_quarantine_mode": False, "routing_health_probe_mode": False,
            "message_body_stored": False, "paid_promotion_enabled": False, "project_layer_only": True}
        if (len(policies) != 1 or any(policies[0].get(key) != value for key, value in expected_policy.items())
                or any(policies[0].get(key) is not value for key, value in expected_policy.items()
                       if type(value) is bool)):
            return None
        policy, embedded = policies[0], envelope["policy_decision"]
        cli_keys = {"status", "run_id", "artifacts", "task_id", "approval_id", "decision_id", "reason",
            "required_receipts", "routing_status", "routing_quarantine_mode", "routing_health_probe_mode",
            "target_automation_status", "source_project_id", "target_project_id", "target_department",
            "target_thread_id", "target_thread_title", "target_cwd", "target_sidebar_section_id", "payload_sha256",
            "message_body_stored", "paid_promotion_enabled", "department", "checked_at"}
        if not isinstance(embedded, dict):
            return None
        if set(embedded) == cli_keys:
            if (embedded["run_id"] != "" or embedded["artifacts"] !=
                    ["data/action-policy.json", "logs/approvals/ledger.jsonl", "logs/policy-decisions.jsonl"]
                    or any(embedded[key] != policy.get(key) for key in cli_keys - {"run_id", "artifacts"})):
                return None
        elif embedded != policy:
            return None
        if any(embedded.get(key) is not False for key in
               ("routing_quarantine_mode", "routing_health_probe_mode", "message_body_stored", "paid_promotion_enabled")):
            return None
        checked, sent = [_review_observed_at(value) for value in (policy.get("checked_at"), dispatch.get("created_at"))]
        if checked is None or sent is None or not checked <= sent <= dt.datetime.now(dt.timezone.utc):
            return None
        return {"envelope": envelope, "policy": policy, "dispatch": dispatch,
                "contract_pin": contract_pin, "receipts": receipts, "department": role}
    except (w.WorkflowError, OSError, ValueError, TypeError, KeyError, AttributeError):
        return None


def _modern_initial_assignment_transport(root, snapshot, dispatch, contract_pin):
    """Select one original target ACK from the complete ordinary native batch.

    Other registered project polls are context, not reviewer assignments. Keep
    the entire pinned batch and reject all duplicate, failed or drifted polls.
    """
    w = _workflow()
    try:
        source = _modern_goal_assignment_send(root, snapshot, dispatch, contract_pin)
        if source is None:
            return False
        goal, task, role = _goal(root, snapshot), snapshot["task_id"], dispatch["department"]
        receipts, registry = source["receipts"], w.department_registry(root)
        index = receipts.index(dispatch)
        end = next((i for i, row in enumerate(receipts) if i > index and row.get("department") == role
                    and row.get("receipt_type") in {"dispatch_sent", "dispatch_failed"}), len(receipts))
        acks = [row for row in receipts[index + 1:end] if row.get("department") == role
                and row.get("receipt_type") == "chat_ack"]
        if len(acks) != 1 or len(acks[0].get("evidence", [])) != 1:
            return False
        ack, fixed = acks[0], registry[role]["chat_binding"]
        if (ack.get("ack_nonempty") is not True or ack.get("chat_task_id") != fixed["task_id"]
                or any(ack.get(key) != dispatch.get(key) for key in ("task_id", "action_id", "action_class", "scope", "policy_decision_id"))
                or any(ack.get(key) for key in ("supersedes_receipt_id", "approval_id", "replacement_reason"))
                or any(row.get("supersedes_receipt_id") == ack["receipt_id"] for row in receipts)):
            return False
        raw = _review_source_document(root, ack["evidence"][0])
        batch = _review_raw_native_result(raw)
        if (set(batch) - {"timedOut", "wake", "polls", "errors", "error", "truncated", "isError", "failed", "superseded"}
                or type(batch.get("timedOut")) is not bool or "wake" not in batch
                or not isinstance(batch.get("polls"), list) or not batch["polls"]):
            return False
        now, seen, selected = dt.datetime.now(dt.timezone.utc), set(), []
        for poll in batch["polls"]:
            poll_keys = {"schemaVersion", "cursor", "revision", "changed", "thread", "latestTurn",
                         "latestAssistantMessageId", "latestAssistantMessage", "latestToolMarkerId", "latestToolMarker"}
            if (not poll_keys <= set(poll) or set(poll) - poll_keys -
                    {"error", "errors", "truncated", "failed", "superseded", "isError"}):
                return False
            thread, turn = poll.get("thread", {}), poll.get("latestTurn")
            thread_id = thread.get("id")
            bindings = [entry["chat_binding"] for entry in registry.values() if isinstance(entry, dict)
                        and isinstance(entry.get("chat_binding"), dict) and entry["chat_binding"].get("task_id") == thread_id]
            if (len(bindings) != 1 or thread_id in seen or poll.get("schemaVersion") != 1
                    or type(poll.get("revision")) is not int or poll["revision"] < 1
                    or not isinstance(poll.get("cursor"), str) or not poll["cursor"].endswith(":" + str(poll["revision"]))
                    or type(poll.get("changed")) is not bool or thread.get("hostId") != "local"):
                return False
            seen.add(thread_id)
            binding = bindings[0]
            identity = {"kind": "codex", "hostId": "local", "title": binding["title"],
                        "cwd": binding["cwd"], "projectId": binding["project_id"]}
            if (binding.get("cwd") != str(Path(root).resolve()) or binding.get("project_id") != fixed.get("project_id")
                    or any(key in thread and thread[key] != value for key, value in identity.items())):
                return False
            if turn is not None:
                start = turn.get("startedAt")
                if (not turn.get("id") or turn.get("status") not in {"inProgress", "completed"}
                        or type(start) not in {int, float} or not 0 < start <= now.timestamp()
                        or (turn.get("completedAt") is not None and
                            (type(turn["completedAt"]) not in {int, float} or not start <= turn["completedAt"] <= now.timestamp()))):
                    return False
            message = poll.get("latestAssistantMessage")
            if message is None:
                if poll.get("latestAssistantMessageId") is not None:
                    return False
            elif (not isinstance(turn, dict) or not message.get("id") or message["id"] != poll.get("latestAssistantMessageId")
                    or message.get("turnId") != turn["id"] or message.get("phase") not in {"commentary", "final_answer"}
                    or ("role" in message and message["role"] != "assistant")
                    or not isinstance(message.get("text"), str) or not message["text"].strip()):
                return False
            if thread_id == fixed["task_id"]:
                selected.append(poll)
        if len(selected) != 1:
            return False
        poll = selected[0]
        turn, message = poll.get("latestTurn"), poll.get("latestAssistantMessage")
        checked, sent, at = [_review_observed_at(value) for value in
                             (source["policy"].get("checked_at"), dispatch.get("created_at"), ack.get("created_at"))]
        if (not isinstance(turn, dict) or not isinstance(message, dict) or checked is None or sent is None or at is None
                or not checked <= sent <= at <= now or not checked.timestamp() <= turn["startedAt"] <= at.timestamp()
                or ack.get("idempotency_key") != ":".join((task, role, "initial-ACK", turn["id"], message["id"]))
                or set(re.findall(r"(?<![A-Za-z0-9_-])fc-[A-Za-z0-9_-]+", message["text"])) - {task, goal.get("parent_task_id")}
                or set(re.findall(r"project:[A-Za-z0-9_:.-]+", message["text"])) - set(goal["authorized_scope"])):
            return False
        return True
    except (w.WorkflowError, OSError, ValueError, TypeError, KeyError, AttributeError):
        return False


def _initial_assignment_wait_envelope(root, snapshot, dispatch, contract_pin):
    """Associate an actual complete-goal send with its raw native wait ACK.

    A batch wait may contain the producer and sole reviewer. Every exposed poll
    must match an actually dispatched same-goal participant; duplicate, foreign
    or failed source polls cannot supply the selected reviewer's responsibility.
    """
    w = _workflow()
    try:
        import goal_delivery_runtime as g
        task, goal = snapshot["task_id"], _goal(root, snapshot)
        if goal is None:
            return False
        role, registry = goal["responsible_assistant"], w.department_registry(root)
        fixed, hq = [registry[name]["chat_binding"] for name in (role, "operations")]
        contract = _review_source_document(root, contract_pin)
        contract = contract.get("goal_delivery", contract)
        if (not _initial_goal_identity(root, snapshot, contract)
                or any(contract.get(key) != goal.get(key) for key in ("parent_task_id", "human_authorization"))
                or contract.get("source_mode", "approved_dispatch") != goal.get("source_mode", "approved_dispatch")
                or contract.get("required_execution_actions", []) != goal.get("required_execution_actions", [])
                or w.file_digest(root, contract["human_authorization"]["evidence_path"]) != goal.get("authorization_pin")
                or dispatch.get("task_id") != task or dispatch.get("department") != role
                or dispatch.get("receipt_type") != "dispatch_sent" or dispatch.get("action_class") != "thread_message"
                or dispatch.get("action_id") != "assign-goal-review:" + task
                or dispatch.get("scope") not in goal["authorized_scope"] or dispatch.get("chat_task_id") != fixed["task_id"]
                or fixed.get("cwd") != str(Path(root).resolve()) or hq.get("cwd") != fixed["cwd"]
                or not fixed.get("project_id") or hq.get("project_id") != fixed["project_id"]):
            return False
        receipts, previous = w.read_jsonl(w.receipts_path(root, task)), ""
        for row in receipts:
            if (row.get("task_id") != task or row.get("previous_hash", "") != previous
                    or row.get("receipt_hash") != w.sha256_value(w._receipt_payload_for_hash(row))):
                return False
            previous = row["receipt_hash"]
        if len([row for row in receipts if row == dispatch]) != 1:
            return False
        selected_index = receipts.index(dispatch)
        selected_acks = []
        for row in receipts[selected_index + 1:]:
            if row.get("department") != role:
                continue
            if row.get("receipt_type") in {"dispatch_sent", "dispatch_failed"}:
                break
            if row.get("receipt_type") == "chat_ack":
                selected_acks.append(row)
        if len(selected_acks) != 1 or len(selected_acks[0].get("evidence", [])) != 1:
            return False
        ack = selected_acks[0]
        source = _review_source_document(root, ack["evidence"][0])
        native = g._collaboration_native(root, ack["evidence"][0])
        if (set(source) - {"content", "isError", "structuredContent"}
                or set(native) - {"timedOut", "wake", "polls", "errors", "error", "truncated", "isError"}
                or source.get("isError") is not False or _review_source_failed(source) or native.get("errors")
                or _review_source_failed(native)
                or not isinstance(native.get("polls"), list) or not native["polls"]
                or type(native.get("timedOut")) is not bool):
            return False
        participants = {row["chat_task_id"]: row["department"] for row in snapshot.get("departments", [])
                        if row.get("department") in registry and row.get("chat_task_id")}
        seen, reviewer_seen = set(), False
        now = dt.datetime.now(dt.timezone.utc)
        policies = w.read_jsonl(root / w.POLICY_DECISIONS)
        for poll in native["polls"]:
            thread = poll.get("thread", {})
            thread_id = thread.get("id")
            if thread_id not in participants or thread_id in seen or _review_source_failed(thread):
                return False
            seen.add(thread_id)
            participant = participants[thread_id]
            binding = registry[participant]["chat_binding"]
            sends = [(i, row) for i, row in enumerate(receipts) if row.get("department") == participant
                     and row.get("receipt_type") in {"dispatch_sent", "dispatch_failed"}
                     and row.get("scope") == dispatch["scope"] and i <= selected_index]
            if len(sends) != 1:
                return False
            index, sent_row = sends[0]
            window_end = next((i for i, row in enumerate(receipts) if i > index
                               and row.get("department") == participant
                               and row.get("receipt_type") in {"dispatch_sent", "dispatch_failed"}), len(receipts))
            acknowledgements = [row for row in receipts[index + 1:window_end] if row.get("department") == participant
                                and row.get("receipt_type") == "chat_ack"]
            if len(acknowledgements) != 1 or ack["evidence"][0] not in acknowledgements[0].get("evidence", []):
                return False
            observed_ack = acknowledgements[0]
            if (sent_row.get("receipt_type") != "dispatch_sent" or sent_row.get("action_class") != "thread_message"
                    or sent_row.get("chat_task_id") != thread_id or len(sent_row.get("evidence", [])) != 1
                    or observed_ack.get("chat_task_id") != thread_id or observed_ack.get("ack_nonempty") is not True
                    or observed_ack.get("action_id") != sent_row.get("action_id")
                    or observed_ack.get("action_class") not in {"", "thread_message"}
                    or observed_ack.get("policy_decision_id") not in {"", sent_row.get("policy_decision_id")}
                    or observed_ack.get("scope") != sent_row.get("scope")
                    or any(row.get("supersedes_receipt_id") in {sent_row["receipt_id"], observed_ack["receipt_id"]} for row in receipts)
                    or any(row.get(key) for row in (sent_row, observed_ack)
                           for key in ("supersedes_receipt_id", "approval_id", "replacement_reason"))):
                return False
            envelope_pin = sent_row["evidence"][0]
            envelope = _review_source_document(root, envelope_pin)
            expected = {"task_id": task, "action_id": sent_row["action_id"], "payload_sha256": contract_pin["sha256"],
                        "payload_bytes": contract_pin["size"], "policy_decision_id": sent_row["policy_decision_id"]}
            if (set(envelope) != set(expected) | {"native_send", "actual_live_identity"}
                    or any(envelope.get(key) != value for key, value in expected.items())
                    or g._collaboration_native(root, envelope_pin) != {"threadId": thread_id}):
                return False
            inventory = envelope["actual_live_identity"]
            content = inventory.get("content", [])
            if (inventory.get("isError") is not False or len(content) != 1
                    or content[0].get("type") != "text" or not isinstance(content[0].get("text"), str)):
                return False
            def unique(pairs):
                result = {}
                for key, value in pairs:
                    if key in result:
                        raise ValueError("ambiguous original live participant identity")
                    result[key] = value
                return result
            live = json.loads(content[0]["text"], object_pairs_hook=unique)
            targets = [row for group in ("pinnedThreads", "threads") for row in live.get(group, [])
                       if isinstance(row, dict) and row.get("id") == thread_id]
            expected_identity = {"kind": "codex", "hostId": "local", "title": binding["title"],
                                 "cwd": binding["cwd"], "projectId": binding["project_id"]}
            if (live.get("schemaVersion") != 4 or len(targets) != 1
                    or ("structuredContent" in inventory and inventory["structuredContent"] != live)
                    or any(targets[0].get(key) != value for key, value in expected_identity.items())
                    or binding.get("cwd") != str(Path(root).resolve()) or binding.get("project_id") != fixed["project_id"]
                    or thread.get("hostId") != "local"
                    or any(key in thread and thread[key] != value for key, value in expected_identity.items())):
                return False
            decisions = [row for row in policies if row.get("decision_id") == sent_row["policy_decision_id"]]
            expected_policy = {"status": "allow", "routing_status": "routing_allowed", "task_id": task,
                "department": "operations", "action_id": sent_row["action_id"], "action_class": "thread_message",
                "scope": sent_row["scope"], "payload_sha256": contract_pin["sha256"], "target_department": participant,
                "target_thread_id": thread_id, "target_thread_title": binding["title"], "target_cwd": binding["cwd"],
                "source_project_id": fixed["project_id"], "target_project_id": fixed["project_id"],
                "target_sidebar_section_id": binding.get("sidebar_section_id"),
                "routing_quarantine_mode": False, "routing_health_probe_mode": False}
            if len(decisions) != 1 or any(decisions[0].get(key) != value for key, value in expected_policy.items()):
                return False
            checked, sent, at = [_review_observed_at(value) for value in
                                 (decisions[0].get("checked_at"), sent_row.get("created_at"), observed_ack.get("created_at"))]
            turn, message = poll.get("latestTurn", {}), poll.get("latestAssistantMessage", {})
            start = turn.get("startedAt")
            if (checked is None or sent is None or at is None or not checked <= sent <= at <= now
                    or poll.get("schemaVersion") != 1 or _review_source_failed(poll)
                    or not isinstance(poll.get("cursor"), str) or not poll["cursor"]
                    or type(poll.get("revision")) is not int or poll["revision"] < 1
                    or not turn.get("id") or turn.get("status") not in {"inProgress", "completed"} or _review_source_failed(turn)
                    or type(start) not in {int, float} or not checked.timestamp() <= start <= at.timestamp()
                    or not message.get("id") or message.get("id") != poll.get("latestAssistantMessageId")
                    or message.get("turnId") != turn["id"] or message.get("phase") not in {"commentary", "final_answer"}
                    or _review_source_failed(message) or ("role" in message and message["role"] != "assistant")
                    or not isinstance(message.get("text"), str) or not message["text"].strip()):
                return False
            if (set(re.findall(r"(?<![A-Za-z0-9_-])fc-[A-Za-z0-9_-]+", message["text"]))
                    - {task, goal.get("parent_task_id")}
                    or set(re.findall(r"project:[A-Za-z0-9_:.-]+", message["text"])) - set(goal["authorized_scope"])):
                return False
            if participant == role:
                reviewer_seen = (sent_row == dispatch and observed_ack == ack)
        return reviewer_seen
    except (w.WorkflowError, OSError, ValueError, TypeError, KeyError, AttributeError):
        return False


def _same_original_ack_group(root, snapshot, receipts, dispatch, acks, plan):
    """Fold exact observations of one original ACK, retaining every receipt.

    Complete native input and initial nonempty reply are the authority. Limited
    native reads and the two supported observation shapes must match that
    source; their summaries or private-session locators grant no responsibility.
    """
    w = _workflow()
    try:
        import goal_delivery_runtime as g
        goal, registry = _goal(root, snapshot), w.department_registry(root)
        role, task = plan["reviewer_department"], snapshot["task_id"]
        fixed, hq = [registry[name]["chat_binding"] for name in (role, "operations")]
        contract = snapshot.get("goal_contract")
        _review_source_document(root, contract)
        if (not acks or goal is None or role != goal["responsible_assistant"]
                or plan.get("task_id") != task or plan.get("scope") != dispatch.get("scope")
                or plan.get("reviewer_thread_id") != fixed["task_id"]
                or not _initial_assignment(root, snapshot, dispatch)
                or contract not in dispatch.get("evidence", [])
                or dispatch.get("department") != role or dispatch.get("action_class") != "thread_message"
                or dispatch.get("chat_task_id") != fixed["task_id"]
                or fixed.get("cwd") != str(Path(root).resolve()) or hq.get("cwd") != fixed["cwd"]
                or not fixed.get("project_id") or hq.get("project_id") != fixed["project_id"]):
            return None
        policies = [row for row in w.read_jsonl(root / w.POLICY_DECISIONS)
                    if row.get("decision_id") == dispatch.get("policy_decision_id")]
        expected = {"status": "allow", "routing_status": "routing_allowed", "task_id": task,
            "department": "operations", "action_class": "thread_message", "action_id": dispatch["action_id"],
            "scope": dispatch["scope"], "payload_sha256": contract["sha256"], "target_department": role,
            "target_thread_id": fixed["task_id"], "target_thread_title": fixed["title"],
            "target_cwd": fixed["cwd"], "source_project_id": fixed["project_id"],
            "target_project_id": fixed["project_id"], "target_sidebar_section_id": fixed.get("sidebar_section_id")}
        if len(policies) != 1 or any(policies[0].get(key) != value for key, value in expected.items()):
            return None
        checked, sent = [_review_observed_at(value) for value in
                         (policies[0].get("checked_at"), dispatch.get("created_at"))]
        now = dt.datetime.now(dt.timezone.utc)
        if checked is None or sent is None or not checked <= sent <= now:
            return None
        sends = []
        for pin in dispatch.get("evidence", []):
            attachment = _review_source_document(root, pin)
            if pin != contract:
                expected_send = {"task_id": task, "source_thread_id": hq["task_id"],
                    "target_thread_id": fixed["task_id"], "target_department": role,
                    "action_id": dispatch["action_id"], "scope": dispatch["scope"],
                    "payload_sha256": contract["sha256"], "payload_size": contract["size"],
                    "policy_decision_id": dispatch["policy_decision_id"]}
                if any(key in attachment and attachment[key] != value for key, value in expected_send.items()):
                    return None
                native = g._collaboration_native(root, pin)
                if native.get("threadId") != fixed["task_id"]:
                    return None
                sends.append((pin, native))
        if len(sends) != 1:
            return None
        documents, natives, summaries, local = {}, [], [], []
        for index, ack in acks:
            at = _review_observed_at(ack.get("created_at"))
            if (ack.get("task_id") != task or ack.get("department") != role
                    or ack.get("receipt_type") != "chat_ack" or ack.get("ack_nonempty") is not True
                    or ack.get("chat_task_id") != fixed["task_id"] or ack.get("scope") != dispatch["scope"]
                    or ack.get("action_id") != dispatch["action_id"]
                    or ack.get("action_class") not in {"", "thread_message"}
                    or ack.get("policy_decision_id") not in {"", dispatch["policy_decision_id"]}
                    or ack.get("supersedes_receipt_id") or ack.get("approval_id") or ack.get("replacement_reason")
                    or any(row.get("supersedes_receipt_id") == ack.get("receipt_id") for row in receipts)
                    or at is None or not sent <= at <= now or not ack.get("evidence")):
                return None
            for pin in ack["evidence"]:
                value = _review_source_document(root, pin)
                documents[w.canonical_json(pin)] = value
                if value.get("source") == "mcp__codex_app__read_thread":
                    if (set(value) != {"schema_version", "task_id", "source", "observed_at", "native_thread",
                            "native_turn", "actual_incoming_function_output", "actual_nonempty_assistant_ack",
                            "read_options", "prepared"}
                            or value.get("schema_version") != 1 or value.get("task_id") != task
                            or value.get("prepared") is not False):
                        return None
                    observation = _review_observed_at(value.get("observed_at", {}).get("current_time"))
                    if observation is None or not sent <= observation <= at:
                        return None
                    summaries.append((value, at))
                elif value.get("proof_kind") == "actual_native_nonempty_ACK_source_observation":
                    local.append((value, at))
                else:
                    if _review_source_failed(value):
                        return None
                    if (("content" in value and set(value) - {"content", "isError", "structuredContent"})
                            or ("content" not in value and set(value) - {"schemaVersion", "thread", "page", "turns",
                                                                       "untrustedDataNotice", "error", "isError", "truncated"})):
                        return None
                    native = g._collaboration_native(root, pin)
                    natives.append((pin, native, at))
        complete, limited = [], []
        for pin, native, at in natives:
            thread, turns = native.get("thread"), native.get("turns")
            if (set(native) - {"schemaVersion", "thread", "page", "turns", "untrustedDataNotice", "error", "isError", "truncated"}
                    or native.get("schemaVersion") != 1 or _review_source_failed(native) or _review_source_failed(thread)
                    or any(thread.get(key) != value for key, value in
                           {"id": fixed["task_id"], "title": fixed["title"], "cwd": fixed["cwd"]}.items())
                    or any(key in thread and thread[key] != value for key, value in
                           {"kind": "codex", "hostId": "local", "projectId": fixed["project_id"]}.items())
                    or not isinstance(turns, list) or len(turns) != 1 or not isinstance(turns[0], dict)):
                return None
            turn = turns[0]
            items, start = turn.get("items"), turn.get("startedAt")
            if (not turn.get("id") or turn.get("status") not in {"inProgress", "completed"}
                    or _review_source_failed(turn)
                    or type(start) not in {int, float} or not checked.timestamp() <= start <= at.timestamp()
                    or ("turnId" in sends[0][1] and sends[0][1]["turnId"] != turn["id"])
                    or not isinstance(items, list) or not items or any(not isinstance(item, dict) for item in items)):
                return None
            incoming = items[0]
            replies = [item for item in items if item.get("type") == "agentMessage"]
            if (incoming.get("type") != "functionCallOutput" or not incoming.get("id")
                    or incoming.get("name") != "send_message_to_thread" or incoming.get("namespace") != "codex_app"
                    or _review_source_failed(incoming)
                    or not replies or any(not item.get("id") or item.get("phase") not in {"commentary", "final_answer"}
                        or not isinstance(item.get("text"), str) or not item["text"].strip() or _review_source_failed(item)
                        or ("role" in item and item["role"] != "assistant") for item in replies)):
                return None
            output = incoming.get("output")
            source = (thread, turn, incoming, replies)
            if "output" not in incoming:
                limited.append(source)
                continue
            if (not isinstance(output, dict) or output.get("truncated") is not False
                    or ("isError" in output and output["isError"] is not False)
                    or not isinstance(output.get("text"), str)):
                return None
            wrapper = re.fullmatch(r"<codex_delegation>\s*<source_thread_id>([^<>]+)</source_thread_id>\s*<input>([\s\S]*)</input>\s*</codex_delegation>\s*", output["text"])
            if (wrapper is None or wrapper.group(1) != hq["task_id"]
                    or wrapper.group(2).encode("utf-8") != w.safe_path(root, contract["path"]).read_bytes()):
                return None
            complete.append(source)
        if not complete:
            return None
        canonical = complete[0]
        identity_keys = ("id", "kind", "hostId", "title", "cwd", "projectId")
        def projection(source, *, limited=False):
            thread, turn, incoming, replies = source
            base_thread, base_turn, base_incoming, base_replies = canonical
            if (any(key in thread and thread[key] != base_thread.get(key, fixed.get("project_id")
                        if key == "projectId" else None) for key in identity_keys)
                    or turn.get("id") != base_turn["id"] or turn.get("startedAt") != base_turn["startedAt"]
                    or turn.get("status") not in {"inProgress", "completed"} or _review_source_failed(turn)
                    or _review_source_failed(thread)
                    or any(base_incoming.get(key) != value for key, value in incoming.items())
                    or not replies or replies[0] != base_replies[0]
                    or (limited and any(not any(all(item.get(key) == value for key, value in reply.items())
                                               for full in complete for item in full[3]) for reply in replies))):
                return False
            return True
        if not all(projection(source) for source in complete) or not all(projection(source, limited=True) for source in limited):
            return None
        for value, at in summaries:
            source = (value["native_thread"], value["native_turn"], value["actual_incoming_function_output"],
                      [value["actual_nonempty_assistant_ack"]])
            options = value.get("read_options")
            if (not all(isinstance(item, dict) for item in source[:3]) or not projection(source, limited=True)
                    or not isinstance(options, dict) or options.get("includeOutputs") is not True
                    or type(options.get("maxOutputCharsPerItem")) is not int
                    or options["maxOutputCharsPerItem"] < len(source[2].get("output", {}).get("text", ""))
                    or type(source[1].get("startedAt")) not in {int, float}
                    or not checked.timestamp() <= source[1]["startedAt"] <= at.timestamp()):
                return None
        message, turn = canonical[3][0], canonical[1]
        raw = message["text"].encode("utf-8")
        for value, at in local:
            expected = {"schema_version": 1, "task_id": task, "department": role,
                "fixed_chat_task_id": fixed["task_id"], "source_turn_id": turn["id"],
                "source_message_id": message["id"], "phase": message["phase"], "ack_nonempty": True,
                "in_current_fixed_department_chat": True, "reply_text_utf8": message["text"],
                "reply_sha256": hashlib.sha256(raw).hexdigest(), "reply_size": len(raw),
                "is_QA": False, "receipt_or_queue_mutated": False, "message_sent": False}
            responsibility = {"dispatch_receipt_id": dispatch["receipt_id"],
                              "policy_decision_id": dispatch["policy_decision_id"], "evidence": sends[0][0]}
            observed, stamped = [_review_observed_at(value.get(key)) for key in ("observed_at", "message_timestamp")]
            local_source, original = value.get("local_session_source", {}), value.get("local_session_source", {}).get("original_record", {})
            payload, metadata = original.get("payload", {}), original.get("metadata", {})
            native_pin = value.get("actual_native_read_thread")
            if (set(value) != set(expected) | {"proof_kind", "message_timestamp", "observed_at", "actual_native_read_thread",
                                              "local_session_source", "actual_responsibility_send"}
                    or any(value.get(key) != item for key, item in expected.items())
                    or value.get("actual_responsibility_send") != responsibility
                    or not isinstance(native_pin, dict) or w.canonical_json(native_pin) not in documents
                    or not any(pin == native_pin for pin, _, _ in natives)
                    or observed is None or stamped is None or not sent <= stamped <= observed <= at
                    or stamped.timestamp() < turn["startedAt"]
                    or local_source.get("original_payload_values_not_normalized") is not True
                    or original.get("type") != "response_item" or original.get("timestamp") != value["message_timestamp"]
                    or payload.get("type") != "message" or payload.get("role") != "assistant"
                    or payload.get("id") != message["id"] or payload.get("phase") != message["phase"]
                    or payload.get("content") != [{"type": "output_text", "text": message["text"]}]
                    or payload.get("internal_chat_message_metadata_passthrough", {}).get("turn_id") != turn["id"]
                    or metadata.get("client_authored") is not False
                    or metadata.get("retained_source", {}).get("complete") is not True
                    or metadata.get("retained_source", {}).get("id") !=
                       {"message_id": message["id"], "turn_id": turn["id"], "role": "assistant"}):
                return None
        return min(acks, key=lambda item: item[0])
    except (w.WorkflowError, OSError, ValueError, TypeError, KeyError, AttributeError):
        return None


def _same_original_responsibility_ack_group(root, snapshot, receipts, dispatch, acks, plan):
    """Keep separately proven messages in one original responsibility window.

    A complete selected source plus its independently pinned original FCO event
    supplies the original goal. A local ACK is checked against only its exact
    message/start/context session rows. Different messages are never folded as
    byte-identical observations, and every original receipt remains in the chain.
    """
    w = _workflow()
    try:
        goal, task = _goal(root, snapshot), snapshot["task_id"]
        role, registry = plan["reviewer_department"], w.department_registry(root)
        fixed, hq = [registry[name]["chat_binding"] for name in (role, "operations")]
        contract = snapshot["goal_contract"]
        if (goal is None or role != goal["responsible_assistant"] or not acks
                or plan.get("task_id") != task or plan.get("scope") != dispatch.get("scope")
                or plan.get("reviewer_thread_id") != fixed["task_id"]
                or contract not in dispatch.get("evidence", [])
                or not _initial_assignment(root, snapshot, dispatch)
                or dispatch.get("receipt_type") != "dispatch_sent"
                or dispatch.get("action_id") != "assign-goal-review:" + task
                or dispatch.get("department") != role or dispatch.get("action_class") != "thread_message"
                or dispatch.get("chat_task_id") != fixed["task_id"]
                or any(dispatch.get(key) for key in ("supersedes_receipt_id", "approval_id", "replacement_reason"))
                or fixed.get("cwd") != str(Path(root).resolve()) or hq.get("cwd") != fixed["cwd"]
                or not fixed.get("project_id") or fixed["project_id"] != hq.get("project_id")):
            return None
        policies = [row for row in w.read_jsonl(root / w.POLICY_DECISIONS)
                    if row.get("decision_id") == dispatch.get("policy_decision_id")]
        expected_policy = {"status": "allow", "routing_status": "routing_allowed", "task_id": task,
            "department": "operations", "action_id": dispatch["action_id"], "action_class": "thread_message",
            "scope": dispatch["scope"], "payload_sha256": contract["sha256"], "target_department": role,
            "target_thread_id": fixed["task_id"], "target_thread_title": fixed["title"], "target_cwd": fixed["cwd"],
            "source_project_id": fixed["project_id"], "target_project_id": fixed["project_id"],
            "target_sidebar_section_id": fixed.get("sidebar_section_id"),
            "routing_quarantine_mode": False, "routing_health_probe_mode": False}
        if (len(policies) != 1 or any(policies[0].get(key) != value for key, value in expected_policy.items())
                or any(policies[0].get(key) is not value for key, value in expected_policy.items() if type(value) is bool)):
            return None
        contract_doc = _review_source_document(root, contract)
        contract_doc = contract_doc.get("goal_delivery", contract_doc)
        if (not _initial_goal_identity(root, snapshot, contract_doc)
                or any(contract_doc.get(key) != goal.get(key) for key in ("parent_task_id", "human_authorization"))
                or contract_doc.get("source_mode", "approved_dispatch") != goal.get("source_mode", "approved_dispatch")
                or contract_doc.get("required_execution_actions", []) != goal.get("required_execution_actions", [])
                or w.file_digest(root, contract_doc["human_authorization"]["evidence_path"]) != goal.get("authorization_pin")):
            return None
        send_pins = [pin for pin in dispatch.get("evidence", []) if pin != contract]
        if len(send_pins) != 1:
            return None
        send = _review_source_document(root, send_pins[0])
        _review_native_containers(send)
        expected_send = {"task_id": task, "source_thread_id": hq["task_id"], "target_department": role,
            "target_thread_id": fixed["task_id"], "action_id": dispatch["action_id"], "scope": dispatch["scope"],
            "payload_sha256": contract["sha256"], "payload_size": contract["size"],
            "policy_decision_id": dispatch["policy_decision_id"]}
        if (set(send) != set(expected_send) | {"policy_result", "native_send_result", "live_identity"}
                or any(send.get(key) != value for key, value in expected_send.items())
                or _review_raw_native_result(send["native_send_result"]) != {"threadId": fixed["task_id"]}):
            return None
        embedded = send["policy_result"]
        _review_native_containers(embedded)
        shared = {"status", "task_id", "decision_id", "routing_status", "routing_quarantine_mode",
            "routing_health_probe_mode", "source_project_id", "target_project_id", "target_department",
            "target_thread_id", "target_thread_title", "target_cwd", "target_sidebar_section_id",
            "payload_sha256", "department", "checked_at"}
        if (any(embedded.get(key) != policies[0].get(key) for key in shared)
                or any(embedded.get(key) is not False for key in ("routing_quarantine_mode", "routing_health_probe_mode"))):
            return None
        live = _review_raw_native_result(send["live_identity"])
        targets = [row for group in ("pinnedThreads", "threads") for row in live.get(group, [])
                   if isinstance(row, dict) and row.get("id") == fixed["task_id"]]
        if (live.get("schemaVersion") != 4 or len(targets) != 1
                or any(targets[0].get(key) != value for key, value in {"kind": "codex", "hostId": "local",
                    "title": fixed["title"], "cwd": fixed["cwd"], "projectId": fixed["project_id"]}.items())):
            return None
        checked, sent = [_review_observed_at(value) for value in (policies[0].get("checked_at"), dispatch.get("created_at"))]
        if checked is None or sent is None:
            return None
        now, previous = dt.datetime.now(dt.timezone.utc), ""
        for row in receipts:
            if (row.get("task_id") != task or row.get("previous_hash", "") != previous
                    or row.get("receipt_hash") != w.sha256_value(w._receipt_payload_for_hash(row))):
                return None
            previous = row["receipt_hash"]
        if (len([row for row in receipts if row == dispatch]) != 1
                or any(row.get("supersedes_receipt_id") == dispatch["receipt_id"] for row in receipts)):
            return None
        original_index = receipts.index(dispatch)
        end = next((i for i, row in enumerate(receipts) if i > original_index and row.get("department") == role
                    and row.get("receipt_type") in {"dispatch_sent", "dispatch_failed"}), len(receipts))
        if any(not original_index < index < end or receipts[index] != ack for index, ack in acks):
            return None
        sources, local, messages = [], [], set()
        for index, ack in acks:
            at = _review_observed_at(ack.get("created_at"))
            if (ack.get("task_id") != task or ack.get("department") != role or ack.get("receipt_type") != "chat_ack"
                    or ack.get("chat_task_id") != fixed["task_id"] or ack.get("ack_nonempty") is not True
                    or ack.get("action_id") not in {"", dispatch["action_id"]}
                    or ack.get("scope") not in {"", dispatch["scope"]} or ack.get("action_class") not in {"", "thread_message"}
                    or ack.get("policy_decision_id") not in {"", dispatch["policy_decision_id"]}
                    or any(ack.get(key) for key in ("supersedes_receipt_id", "approval_id", "replacement_reason"))
                    or any(row.get("supersedes_receipt_id") == ack.get("receipt_id") for row in receipts)
                    or at is None or not checked <= sent <= at <= now or len(ack.get("evidence", [])) != 1):
                return None
            doc = _review_source_document(root, ack["evidence"][0])
            _review_native_containers(doc)
            if doc.get("proof_kind") == "actual_native_nonempty_ack_local_session_observation":
                local.append((doc, at))
                continue
            expected_keys = {"schemaVersion", "thread", "turns", "collection_method", "original_native_event",
                             "API_source_was_transport_truncated"}
            if set(doc) != expected_keys or doc.get("schemaVersion") != 1 or type(doc.get("API_source_was_transport_truncated")) is not bool:
                return None
            event = _review_source_document(root, doc["original_native_event"])
            _review_native_containers(event)
            payload, thread, turns = event.get("payload", {}), doc["thread"], doc["turns"]
            if (event.get("type") != "event_msg" or payload.get("type") != "item_completed"
                    or payload.get("thread_id") != fixed["task_id"]
                    or not isinstance(turns, list) or len(turns) != 1
                    or any(thread.get(key) != value for key, value in {"id": fixed["task_id"], "kind": "codex",
                            "hostId": "local", "title": fixed["title"], "cwd": fixed["cwd"]}.items())
                    or ("projectId" in thread and thread["projectId"] != fixed["project_id"])):
                return None
            turn, native_item = turns[0], payload.get("item", {})
            _review_native_containers(turn)
            _review_native_containers(payload)
            _review_native_containers(native_item)
            items = turn.get("items")
            if (payload.get("turn_id") != turn.get("id") or not turn.get("id")
                    or turn.get("status") not in {"inProgress", "completed"} or not isinstance(items, list)
                    or native_item.get("type") != "FunctionCallOutput" or not native_item.get("id")
                    or native_item.get("name") != "send_message_to_thread" or native_item.get("namespace") != "codex_app"
                    or not isinstance(native_item.get("output"), str)):
                return None
            selected = [item for item in items if item.get("id") == native_item["id"]]
            replies = [item for item in items if item.get("type") == "agentMessage"]
            if len(selected) != 1 or len(replies) != 1:
                return None
            item, reply = selected[0], replies[0]
            for value in (item, item.get("output", {}), reply):
                _review_native_containers(value)
            if (item.get("type") != "functionCallOutput" or item.get("name") != native_item["name"]
                    or item.get("namespace") != native_item["namespace"] or item.get("output", {}).get("truncated") is not False
                    or item["output"].get("text") != native_item["output"]
                    or not reply.get("id") or reply.get("phase") not in {"commentary", "final_answer"}
                    or not isinstance(reply.get("text"), str) or not reply["text"].strip()
                    or ("turnId" in reply and reply["turnId"] != turn["id"])):
                return None
            raw = w.safe_path(root, contract["path"]).read_bytes().decode("utf-8")
            encoded = raw.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            wrapper = "<codex_delegation>\n  <source_thread_id>" + hq["task_id"] + "</source_thread_id>\n  <input>" + encoded + "</input>\n</codex_delegation>"
            if item["output"]["text"] != wrapper:
                return None
            event_at = _review_observed_at(event.get("timestamp"))
            start, event_start, event_end = turn.get("startedAt"), payload.get("started_at_ms"), payload.get("completed_at_ms")
            if (event_at is None or not checked <= event_at <= at or type(start) not in {int, float}
                    or not checked.timestamp() <= start <= event_at.timestamp()
                    or type(event_start) not in {int, float} or type(event_end) not in {int, float}
                    or not checked.timestamp() * 1000 <= event_start <= event_end <= at.timestamp() * 1000):
                return None
            sources.append((turn, reply))
            if reply["id"] in messages:
                return None
            messages.add(reply["id"])
        if not sources or not local or len({turn["id"] for turn, _ in sources}) != 1:
            return None
        turn = sources[0][0]
        for doc, at in local:
            text = doc.get("reply_text_utf8")
            raw = text.encode("utf-8") if isinstance(text, str) else b""
            expected = {"schema_version": 1, "task_id": task, "department": role, "fixed_chat_task_id": fixed["task_id"],
                "new_turn_id": turn["id"], "source_turn_id": turn["id"], "ack_nonempty": True,
                "in_current_fixed_department_chat": True, "is_candidate_result": False,
                "reply_sha256": hashlib.sha256(raw).hexdigest(), "reply_size": len(raw)}
            native = doc.get("native_reply", {})
            _review_native_containers(native)
            original = doc.get("actual_complete_goal_send", {})
            send_pins = [pin for pin in dispatch["evidence"] if pin != contract]
            boundary = doc.get("control_boundary", {})
            if (not raw or any(doc.get(key) != value for key, value in expected.items())
                    or any(doc.get(key) is not value for key, value in expected.items() if type(value) is bool)
                    or not doc.get("source_message_id") or doc["source_message_id"] in messages
                    or doc.get("phase") not in {"commentary", "final_answer"}
                    or native.get("type") != "message" or native.get("role") != "assistant"
                    or native.get("id") != doc["source_message_id"] or native.get("phase") != doc["phase"]
                    or native.get("content") != [{"type": "output_text", "text": text}]
                    or native.get("internal_chat_message_metadata_passthrough", {}).get("turn_id") != turn["id"]
                    or len(send_pins) != 1 or original != {"dispatch_receipt_id": dispatch["receipt_id"],
                        "policy_decision_id": dispatch["policy_decision_id"], "action_id": dispatch["action_id"],
                        "scope": dispatch["scope"], "goal_payload_sha256": contract["sha256"],
                        "goal_payload_size": contract["size"], "evidence": send_pins[0]}
                    or boundary != {"ledger_mutation_performed": False, "message_sent": False,
                                    "professional_qa_performed": False, "proof_records_ack_only": True}
                    or any(type(value) is not bool for value in boundary.values())):
                return None
            locator = doc.get("local_session_source", {})
            path = Path(locator.get("path", "")).resolve()
            session_root = (Path.home() / ".codex/sessions").resolve()
            selected_lines = {key: locator.get(key + "_line") for key in ("message", "task_started", "turn_context")}
            if (not path.is_relative_to(session_root) or not path.name.endswith("-" + fixed["task_id"] + ".jsonl")
                    or locator.get("session_id") != fixed["task_id"] or locator.get("cwd") != fixed["cwd"]
                    or any(type(value) is not int or value < 1 for value in selected_lines.values())
                    or len(set(selected_lines.values())) != len(selected_lines)):
                return None
            records = {}
            with path.open("rb") as handle:
                for number, line in enumerate(handle, 1):
                    for name, selected_line in selected_lines.items():
                        if number == selected_line:
                            if (hashlib.sha256(line).hexdigest() != locator.get(name + "_row_sha256")
                                    or (name == "message" and len(line) != locator.get("message_row_size"))):
                                return None
                            records[name] = json.loads(line)
                    if number >= max(selected_lines.values()):
                        break
            if (set(records) != set(selected_lines) or records["message"].get("type") != "response_item"
                    or records["message"].get("payload") != native
                    or records["task_started"].get("type") != "event_msg"
                    or records["task_started"].get("payload", {}).get("type") != "task_started"
                    or records["task_started"].get("payload", {}).get("turn_id") != turn["id"]
                    or records["turn_context"].get("type") != "turn_context"
                    or records["turn_context"].get("payload", {}).get("turn_id") != turn["id"]
                    or records["turn_context"].get("payload", {}).get("cwd") != fixed["cwd"]):
                return None
            stamp, observed = [_review_observed_at(doc.get(key)) for key in ("message_timestamp", "observed_at")]
            if (stamp is None or observed is None or not sent <= stamp <= observed <= at
                    or _review_observed_at(records["message"].get("timestamp")) != stamp
                    or not turn["startedAt"] <= stamp.timestamp()):
                return None
            messages.add(doc["source_message_id"])
        for text in [reply["text"] for _, reply in sources] + [doc["reply_text_utf8"] for doc, _ in local]:
            if (set(re.findall(r"(?<![A-Za-z0-9_-])fc-[A-Za-z0-9_-]+", text)) - {task, goal.get("parent_task_id")}
                    or set(re.findall(r"project:[A-Za-z0-9_:.-]+", text)) - set(goal["authorized_scope"])):
                return None
        return min(acks, key=lambda row: row[0])
    except (w.WorkflowError, OSError, ValueError, TypeError, KeyError, AttributeError):
        return None


def _same_goal_functional_result_notice(root, snapshot, receipts, dispatch, plan):
    """A proven native result resumes its original functional responsibility."""
    w = _workflow()
    try:
        import goal_delivery_runtime as g
        import native_control_result as n
        from scoped_candidate_adoption import _committed
        goal, registry = _goal(root, snapshot), w.department_registry(root)
        task, role = snapshot["task_id"], plan["reviewer_department"]
        fixed, hq = [registry[name]["chat_binding"] for name in (role, "operations")]
        if (goal is None or goal.get("acceptance_capability") != "functional"
                or goal.get("responsible_assistant") != role or plan.get("producer_department") != "operations"
                or plan.get("action_class") != "runtime_control" or plan.get("task_id") != task
                or dispatch.get("task_id") != task or dispatch.get("department") != role
                or dispatch.get("receipt_type") != "dispatch_sent" or dispatch.get("action_class") != "thread_message"
                or dispatch.get("scope") != plan.get("scope") or plan.get("scope") not in goal["authorized_scope"]
                or dispatch.get("chat_task_id") != fixed["task_id"] or plan.get("reviewer_thread_id") != fixed["task_id"]
                or not re.fullmatch(r"resume-original-[a-z0-9-]+-functional-(?:actual-)?final-result-v[1-9][0-9]*", dispatch.get("action_id", ""))
                or any(dispatch.get(key) for key in ("supersedes_receipt_id", "replacement_reason", "approval_id"))
                or any(row.get("supersedes_receipt_id") == dispatch.get("receipt_id") for row in receipts)
                or fixed.get("cwd") != str(Path(root).resolve()) or hq.get("cwd") != fixed["cwd"]
                or not fixed.get("project_id") or hq.get("project_id") != fixed["project_id"]
                or len(dispatch.get("evidence", [])) != 1):
            return False
        source = dispatch["evidence"][0]
        send = _review_source_document(root, source)
        if set(send) != {"task_id", "action_id", "payload_path", "payload_sha256", "policy_decision_id", "native_send", "native_fresh_identity"}:
            return False
        # Reject container failure flags before native decoding can unwrap them.
        if any(_review_source_failed(send[key])
               or any(flag in send[key] and send[key][flag] is not False
                      for flag in ("failed", "superseded"))
               for key in ("native_send", "native_fresh_identity")):
            return False
        payload = w.file_digest(root, send.get("payload_path", ""))
        if (Path(payload["path"]).parent != Path(source["path"]).parent
                or any(send.get(key) != value for key, value in {"task_id": task, "action_id": dispatch["action_id"],
                      "policy_decision_id": dispatch.get("policy_decision_id"), "payload_sha256": payload["sha256"]}.items())
                or g._collaboration_native(root, source) != {"threadId": fixed["task_id"]}):
            return False
        # The source envelope pins both native results; decode the original
        # inventory independently, rather than treating its descriptive fields
        # as an account or project identity.
        inventory = send["native_fresh_identity"]
        if inventory.get("isError") is not False or len(inventory.get("content", [])) != 1:
            return False
        content = inventory["content"][0]
        if content.get("type") != "text" or not isinstance(content.get("text"), str):
            return False
        live = n._json(content["text"])
        targets = [item for group in ("pinnedThreads", "threads") for item in live.get(group, [])
                   if isinstance(item, dict) and item.get("id") == fixed["task_id"]]
        if (live.get("schemaVersion") != 4 or len(targets) != 1
                or ("structuredContent" in inventory and inventory["structuredContent"] != live)
                or any(targets[0].get(key) != value for key, value in {"kind": "codex", "hostId": "local",
                       "title": fixed["title"], "cwd": fixed["cwd"], "projectId": fixed["project_id"]}.items())):
            return False
        policies = [row for row in w.read_jsonl(root / w.POLICY_DECISIONS)
                    if row.get("decision_id") == dispatch.get("policy_decision_id")]
        expected = {"status": "allow", "routing_status": "routing_allowed", "task_id": task,
            "department": "operations", "action_id": dispatch["action_id"], "action_class": "thread_message",
            "scope": plan["scope"], "payload_sha256": payload["sha256"], "target_department": role,
            "target_thread_id": fixed["task_id"], "target_thread_title": fixed["title"],
            "target_cwd": fixed["cwd"], "source_project_id": fixed["project_id"], "target_project_id": fixed["project_id"],
            "target_sidebar_section_id": fixed.get("sidebar_section_id"),
            "routing_quarantine_mode": False, "routing_health_probe_mode": False}
        if len(policies) != 1 or any(policies[0].get(key) != value for key, value in expected.items()):
            return False
        checked, sent = [_review_observed_at(value) for value in (policies[0].get("checked_at"), dispatch.get("created_at"))]
        now = dt.datetime.now(dt.timezone.utc)
        if checked is None or sent is None or not checked <= sent <= now:
            return False
        index = receipts.index(dispatch)
        initial = [(i, row) for i, row in enumerate(receipts[:index])
                   if row.get("department") == role and _initial_assignment(root, snapshot, row)]
        if len(initial) != 1:
            return False
        initial_index, original = initial[0]
        original_acks = [(i, row) for i, row in enumerate(receipts[:index])
                         if i > initial_index and row.get("department") == role and row.get("receipt_type") == "chat_ack"]
        if not _same_original_ack_group(root, snapshot, receipts, original, original_acks, plan):
            return False
        boxes = [row for row in receipts[:index] if row.get("receipt_type") == "outbox_received"
                 and row.get("department") == "operations" and plan.get("candidate") in row.get("evidence", [])]
        if len(boxes) != 1:
            return False
        result_row = boxes[0]
        delivery = [(pin, _review_source_document(root, pin)) for pin in result_row.get("evidence", [])
                    if pin != plan["candidate"]]
        delivery = [(pin, value) for pin, value in delivery if value.get("schema") == "actual_native_control_delivery/v1"]
        if len(delivery) != 1:
            return False
        completed = n.received_candidate(root, snapshot, plan, receipts, require_intake=False)
        rows = w._result_handoff_rows(root, task)
        rows = [row for row in rows if row.get("sender_department") == "operations" and row.get("outbox") == plan["candidate"]]
        queues = [row for row in rows if row.get("event") == "notification_queued"]
        intakes = [row for row in rows if row.get("event") == "controller_received"]
        if len(queues) != 1 or len(intakes) != 1:
            return False
        queue, intake = queues[0], intakes[0]
        expected_queue = {"target_department": role, "candidate_version": plan["candidate_version"],
            "result_sha256": plan["candidate"]["sha256"], "source_thread_id": hq["task_id"],
            "source_turn_id": completed["source_turn_id"], "source_message_id": completed["source_message_id"],
            "source_reply_sha256": completed["source_reply_sha256"], "runtime_control_complete": True}
        if (any(queue.get(key) != value for key, value in expected_queue.items())
                or any(intake.get(key) != value for key, value in expected_queue.items() if key != "target_department")
                or intake.get("coordinator_role") != role or intake.get("responsible_assistant") != role
                or intake.get("decision_actor") != role or intake.get("intake_mode") != "queue"
                or type(intake.get("coordination_fence")) is not int or intake["coordination_fence"] < 1):
            return False
        _committed(root, intake)
        times = [_review_observed_at(value) for value in (completed["reply_observed_at"], result_row.get("created_at"),
                 queue.get("created_at"), intake.get("created_at"))]
        if any(value is None for value in times) or not times[0] <= times[1] <= times[2] <= sent <= now or not times[2] <= times[3] <= now:
            return False
        text = w.safe_path(root, payload["path"]).read_bytes().decode("utf-8")
        # No account, authority scope or replacement reviewer can be smuggled
        # into an ordinary result notice while retaining its old locators.
        if (set(re.findall(r"project:[A-Za-z0-9_:.-]+", text)) - set(goal["authorized_scope"])
                or any(name not in {role, goal.get("schedule_target_department")} and _exact_text_reference(text, name)
                       for name in registry if name.startswith("operations-assistant-"))):
            return False
        def mentions(value):
            if _exact_text_reference(text, value):
                return True
            if "/" in value:
                return any(_exact_text_reference(text, part) for part in
                           (str(w.safe_path(root, value)), Path(value).name, str(Path(value).relative_to(Path(source["path"]).parent))
                            if Path(value).is_relative_to(Path(source["path"]).parent) else value))
            return bool(re.search(r"(?<![A-Za-z0-9_])(?:SHA(?:256)?|ACK|turn|message)" + re.escape(value)
                                  + r"(?![A-Za-z0-9_-])", text))
        contract = snapshot["goal_contract"]
        refs = [task, contract["path"], contract["sha256"], original["receipt_id"], original["policy_decision_id"],
                role, plan["candidate_version"], plan["candidate"]["path"], plan["candidate"]["sha256"],
                result_row["receipt_id"], queue["record_id"], delivery[0][0]["path"], delivery[0][0]["sha256"],
                completed["source_turn_id"], completed["source_message_id"], completed["actual_native_completion"]["path"],
                "actual_native_control_complete/v1", "RUNTIME_CONTROL_COMPLETE"]
        return (all(mentions(value) for value in refs)
                and any(mentions(row["receipt_id"]) for _, row in original_acks)
                and all(re.search(r"(?<![0-9])" + str(pin["size"]) + r"B?(?![0-9])", text)
                        for pin in (contract, plan["candidate"], delivery[0][0])))
    except (w.WorkflowError, OSError, ValueError, TypeError, KeyError, AttributeError):
        return False


def _received_native_review_candidate(root, snapshot, plan):
    """Keep the ordinary consumer; a proven result notice uses exact ACK groups.

    The notice reader already verifies the actual full native result and unique
    independent committed intake. This narrow route avoids reinterpreting its
    proven supplements through the older summary-locator compatibility reader.
    """
    w = _workflow()
    receipts = w.read_jsonl(w.receipts_path(root, snapshot["task_id"]))
    notices = [row for row in receipts if row.get("department") == plan.get("reviewer_department")
               and row.get("receipt_type") == "dispatch_sent"
               and _same_goal_functional_result_notice(root, snapshot, receipts, row, plan)]
    if notices:
        return
    from native_control_result import received_candidate
    received_candidate(root, snapshot, plan, require_intake=True)


def _closed_review_source_pins(root, pins):
    """Normalize explicit full pins; no directory or body-hash discovery."""
    w = _workflow()
    result = {}
    for pin in pins:
        if (not isinstance(pin, dict) or set(pin) != {"path", "sha256", "size"}
                or type(pin.get("size")) is not int or pin["size"] < 0
                or w.file_digest(root, pin.get("path", "")) != pin):
            raise w.WorkflowError("exact closed review source pin required")
        previous = result.get(pin["path"])
        if previous is not None and previous != pin:
            raise w.WorkflowError("conflicting closed review source pins")
        result[pin["path"]] = pin
    return list(result.values())


def _review_manifest_source_pins(root, snapshot, plan, pin, *, candidate_version=None, fingerprint=None):
    """Authenticate a pinned same-goal source-only package before reading inputs."""
    w = _workflow()
    document = _review_source_document(root, pin, object_only=False)
    if (not isinstance(document, dict) or document.get("schema") != "flashcast-exact-source-candidate/v1"
            or document.get("task_id") != snapshot["task_id"]):
        return None
    goal = _goal(root, snapshot)
    if (goal is None or document.get("goal_contract") != snapshot.get("goal_contract")
            or document.get("human_authorization") != goal.get("authorization_pin")
            or snapshot.get("goal_contract") not in document.get("inputs", [])
            or goal.get("authorization_pin") not in document.get("inputs", [])):
        raise w.WorkflowError("source manifest must preserve the exact original goal and human authorization")
    if (document.get("task_id") != snapshot["task_id"]
            or document.get("scope") != plan["scope"]
            or (candidate_version is not None and document.get("candidate_version") != candidate_version)
            or document.get("primary_owner") != plan["producer_department"]
            or document.get("responsible_assistant") != plan["reviewer_department"]
            or document.get("project_root") != str(Path(root).resolve())
            or (fingerprint is not None and document.get("candidate_fingerprint") != fingerprint)
            or document.get("candidate_fingerprint") != hashlib.sha256(json.dumps(
                {key: value for key, value in document.items() if key != "candidate_fingerprint"},
                ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            or any(document.get(key) is not False for key in
                   ("production_write_allowed", "production_release_eligible", "external_permission_issued",
                    "goal_completion_claimed", "final_goal_verdict", "pilot_complete"))):
        raise w.WorkflowError("exact same-goal source-only manifest required")
    import difflib
    directory = Path(pin["path"]).parent
    files = document.get("files")
    if not isinstance(files, list) or not files or len({row.get("path") for row in files}) != len(files):
        raise w.WorkflowError("unique exact source manifest files required")
    for row in files:
        frozen = row.get("candidate")
        after = w.file_digest(root, frozen.get("path", ""))
        if (after != frozen or row.get("after") != {key: after[key] for key in ("sha256", "size")}
                or row.get("candidate_relative_path") != "candidate/" + row["path"]
                or Path(frozen["path"]) != directory / row["candidate_relative_path"]):
            raise w.WorkflowError("exact candidate manifest layout/after bytes required")
        last = w.safe_path(root, frozen["path"]).read_bytes()
        if row.get("before") == {"exists": False}:
            if row.get("baseline") is not None:
                raise w.WorkflowError("absent source baseline required")
            first = b""
        else:
            baseline = row.get("baseline")
            before = w.file_digest(root, baseline.get("path", ""))
            if before != baseline or row.get("before") != {key: before[key] for key in ("sha256", "size")}:
                raise w.WorkflowError("exact source baseline bytes required")
            first = w.safe_path(root, baseline["path"]).read_bytes()
        for direction, old, new in (("forward", first, last), ("reverse", last, first)):
            diff = row.get(direction + "_diff")
            if w.file_digest(root, diff.get("path", "")) != diff:
                raise w.WorkflowError("exact source difference pin required")
            expected = "".join(difflib.unified_diff(old.decode().splitlines(keepends=True), new.decode().splitlines(keepends=True),
                fromfile="a/" + row["path"] if old else "/dev/null", tofile="b/" + row["path"] if new else "/dev/null")).encode()
            if w.safe_path(root, diff["path"]).read_bytes() != expected:
                raise w.WorkflowError("complete exact source difference required")
    _closed_review_source_pins(root, document.get("protected_sources", []))
    return _closed_review_source_pins(root, document.get("inputs", []))


def _candidate_review_source_pins(root, snapshot, plan):
    """Read source-only package inputs from the exact current candidate."""
    candidate = plan.get("candidate")
    if not isinstance(candidate, dict) or not candidate.get("path", "").endswith(".json"):
        return []
    producer = _review_source_document(root, candidate)
    if not _producer_candidate_bound(root, plan, candidate, producer):
        return []
    matches = []
    for pin in _evidence_pins(producer.get("evidence", [])):
        if not pin.get("path", "").endswith(".json"):
            continue
        pins = _review_manifest_source_pins(root, snapshot, plan, pin,
                    candidate_version=plan["candidate_version"], fingerprint=producer.get("candidate_fingerprint"))
        if pins is not None:
            matches.append(pins)
    if len(matches) > 1:
        raise _workflow().WorkflowError("one exact source candidate manifest required")
    return matches[0] if matches else []


def _review_native_containers(value):
    """Check native evidence before wrapper/content decoding loses flags."""
    if (not isinstance(value, dict) or _review_source_failed(value) or value.get("errors")
            or value.get("status") == "failed"):
        raise ValueError("successful complete native container required")
    if any(key in value and value[key] is not False for key in ("failed", "superseded")):
        raise ValueError("boolean native failure markers required")
    for key in ("structuredContent", "output", "actual_tool_result", "thread", "turn", "message",
                "latestTurn", "latestAssistantMessage"):
        if isinstance(value.get(key), dict):
            _review_native_containers(value[key])
    for key in ("polls", "content"):
        if isinstance(value.get(key), list):
            for child in value[key]:
                if not isinstance(child, dict):
                    raise ValueError("native evidence object list required")
                _review_native_containers(child)


def _review_raw_native_result(value):
    _review_native_containers(value)
    if ("isError" in value and value["isError"] is not False) or set(value) - {"content", "isError", "structuredContent", "truncated", "failed", "superseded"}:
        raise ValueError("exact successful raw native response required")
    content = value.get("content")
    if (not isinstance(content, list) or len(content) != 1 or not isinstance(content[0], dict)
            or set(content[0]) != {"type", "text"} or content[0].get("type") != "text"):
        raise ValueError("one complete native text document required")
    def unique(pairs):
        result = {}
        for key, item in pairs:
            if key in result:
                raise ValueError("ambiguous native source fields")
            result[key] = item
        return result
    result = json.loads(content[0]["text"], object_pairs_hook=unique,
                        parse_constant=lambda value: (_ for _ in ()).throw(ValueError("finite native source required")))
    _review_native_containers(result)
    if "structuredContent" in value and value["structuredContent"] != result:
        raise ValueError("native structured/text source disagreement")
    return result


def _review_received_input(root, pins, payload, receiver, sender, registry, *, include_pin=False):
    """Select one actual FCO carrying the exact immutable UTF-8 payload."""
    w = _workflow()
    raw = w.safe_path(root, payload["path"]).read_bytes()
    fixed, source = [registry[role]["chat_binding"] for role in (receiver, sender)]
    found = {}
    for pin in pins:
        if not pin["path"].endswith(".json"):
            continue
        document = _review_source_document(root, pin, object_only=False)
        if not isinstance(document, dict) or not isinstance(document.get("thread"), dict):
            continue
        thread = document["thread"]
        if thread.get("id") != fixed["task_id"]:
            continue
        turns = document.get("turns")
        if turns is None and isinstance(document.get("turn"), dict):
            if isinstance(document.get("message"), dict):
                turns = [{**document["turn"], "items": [document["message"]]}]
            elif isinstance(document["turn"].get("items"), list):
                turns = [document["turn"]]
        if turns is None:
            # Closed evidence also contains plain thread/turn observations;
            # these do not claim to be this received function-call source.
            continue
        if not isinstance(turns, list):
            raise ValueError("complete received native turns required")
        for turn in turns:
            if not isinstance(turn, dict) or not isinstance(turn.get("items", []), list):
                raise ValueError("complete native received source items required")
            for item in turn.get("items", []):
                if (not isinstance(item, dict) or item.get("type") != "functionCallOutput"
                        or item.get("name") != "send_message_to_thread" or item.get("namespace") != "codex_app"):
                    continue
                output = item.get("output", {})
                if not isinstance(output, dict) or not isinstance(output.get("text"), str):
                    continue
                matched = re.fullmatch(r"<codex_delegation>\s*<source_thread_id>([^<]+)</source_thread_id>\s*<input>([\s\S]*)</input>\s*</codex_delegation>", output["text"])
                if matched is None or matched[2].encode("utf-8") != raw:
                    continue
                # Only the selected body supplies this authority. Unrelated
                # metadata/tool observations cannot add or remove its flags.
                for container in (document, thread, turn, item, output):
                    _review_native_containers(container)
                if (matched[1] != source["task_id"] or output.get("truncated") is not False
                        or turn.get("status") not in {"inProgress", "completed"} or not turn.get("id") or not item.get("id")
                        or any(thread.get(key) != value for key, value in {"kind": "codex", "hostId": "local",
                            "title": fixed["title"], "cwd": fixed["cwd"]}.items())
                        or ("projectId" in thread and thread["projectId"] != fixed["project_id"])):
                    raise ValueError("exact original sender/receiver native input required")
                if include_pin and (turn["id"], item["id"]) in found and found[(turn["id"], item["id"])]["pin"] != pin:
                    raise ValueError("ambiguous original received source pins")
                found[(turn["id"], item["id"])] = {"thread": thread, "turn": turn, "item": item,
                    **({"pin": pin} if include_pin else {})}
    if len(found) != 1:
        raise ValueError("one complete actual received native source required")
    return next(iter(found.values()))


def _review_exact_native_reply(root, box, role, references=()):
    """Check selected or full original native reply without fabricating fields."""
    w = _workflow()
    fixed = w.department_registry(root)[role]["chat_binding"]
    native = _review_source_document(root, box.get("actual_native_reply"))
    _review_native_containers(native)
    if "content" in native:
        native = _review_raw_native_result(native)
    thread = native.get("thread", {})
    turns = native.get("turns")
    if turns is None and isinstance(native.get("turn"), dict) and isinstance(native.get("message"), dict):
        turns = [{**native["turn"], "items": [native["message"]]}]
    turns = [turn for turn in (turns or []) if turn.get("id") == box.get("source_turn_id")]
    reply = box.get("visible_reply")
    if (w.file_digest(root, reply.get("path", "")) != reply or not w._chat_binding_healthy(fixed, verification_ttl_hours=26)
            or thread.get("id") != box.get("fixed_chat_task_id") or thread.get("id") != fixed["task_id"]
            or any(thread.get(key) != value for key, value in {"kind": "codex", "hostId": "local", "title": fixed["title"], "cwd": fixed["cwd"]}.items())
            or ("projectId" in thread and thread["projectId"] != fixed["project_id"]) or len(turns) != 1):
        raise w.WorkflowError("one exact original reviewer native source required")
    turn = turns[0]
    _review_native_containers(turn)
    raw = w.safe_path(root, reply["path"]).read_bytes()
    messages = [item for item in turn.get("items", []) if item.get("id") == box.get("source_message_id")]
    if len(messages) != 1:
        raise w.WorkflowError("one exact original reviewer message required")
    message = messages[0]
    _review_native_containers(message)
    meta = box.get("chat_reply", {})
    expected = {"nonempty": True, "in_current_fixed_department_chat": True,
                "source_turn_id": turn["id"], "source_message_id": message["id"],
                "message_sha256": reply["sha256"], "sha256": reply["sha256"], "utf8_bytes": len(raw), "ref": message["id"]}
    if (turn.get("status") not in {"inProgress", "completed"} or message.get("type") != "agentMessage"
            or message.get("phase") not in {"commentary", "final_answer"} or not isinstance(message.get("text"), str)
            or not message["text"].strip() or message["text"].encode("utf-8") != raw
            or box.get("source_reply_sha256") != reply["sha256"] or any(meta.get(key) != value for key, value in expected.items())
            or any(not _exact_text_reference(message["text"], value) for value in references)):
        raise w.WorkflowError("one exact nonempty original reviewer UTF-8 reply required")
    observed, created = [_review_observed_at(box.get(key)) for key in ("reply_observed_at", "created_at")]
    if (type(turn.get("startedAt")) not in {int, float} or observed is None or created is None
            or not 0 <= turn["startedAt"] <= observed.timestamp() or not observed <= created <= dt.datetime.now(dt.timezone.utc)):
        raise w.WorkflowError("ordered original reviewer native observation required")


def _original_goal_adopted_source(root, snapshot, plan, sources, before):
    """Authenticate a prior real source effect, without replaying its history."""
    w = _workflow()
    import paid_three_page_bounded_cms as b
    import result_coordination as c
    from scoped_candidate_adoption import _committed
    def require(value, reason):
        if not value:
            raise w.WorkflowError("original adopted source: " + reason)
    task, role = snapshot["task_id"], plan["reviewer_department"]
    flags = ("production_write_allowed", "production_release_eligible", "external_permission_issued",
             "goal_completion_claimed", "final_goal_verdict", "pilot_complete")
    matches = []
    for source in sources:
        if not source["path"].endswith(".json"):
            continue
        value = _review_source_document(root, source, object_only=False)
        if (isinstance(value, dict) and value.get("schema") == "actual_qualified_native_handoff_source_continuation/v1"
                and value.get("task_id") == task and value.get("scope") == plan["scope"]):
            matches.append((source, value))
    require(len(matches) == 1, "one explicit actual original source continuation required")
    continuation_pin, continuation = matches[0]
    require(continuation.get("prepared_only") is False and all(continuation.get(key) is False for key in flags),
            "actual bounded original source continuation required")
    bindings = [binding for binding in _bindings(root, snapshot)
                if binding.get("pin") == continuation.get("review_plan") and binding.get("reviewer_department") == role]
    require(len(bindings) == 1, "actual original canonical bound plan required")
    previous_plan = load_plan(root, snapshot, bindings[0])
    producer_pin = continuation["producer_outbox"]
    require(previous_plan["candidate"] == producer_pin and previous_plan["candidate_version"] == continuation["candidate_version"]
            and previous_plan["candidate_version"] != plan["candidate_version"]
            and all(previous_plan.get(key) == plan.get(key) for key in
                    ("task_id", "action_id", "action_class", "scope", "producer_department", "reviewer_department", "reviewer_thread_id")),
            "unchanged prior canonical goal and independent responsibility required")
    manifest_pin, review_pin, journal_pin = [continuation[key] for key in ("candidate_manifest", "source_qa", "source_adoption")]
    manifest, box, journal = [_review_source_document(root, value) for value in (manifest_pin, review_pin, journal_pin)]
    goal = _goal(root, snapshot)
    require(manifest.get("schema") == "flashcast-exact-source-candidate/v1" and manifest.get("task_id") == task
            and manifest.get("candidate_version") == continuation["candidate_version"] and manifest.get("scope") == plan["scope"]
            and manifest.get("primary_owner") == plan["producer_department"] and manifest.get("responsible_assistant") == role
            and manifest.get("goal_contract") == snapshot["goal_contract"] and manifest.get("human_authorization") == goal["authorization_pin"]
            and manifest.get("project_root") == str(Path(root).resolve())
            and manifest.get("candidate_fingerprint") == w.sha256_value({key:value for key,value in manifest.items() if key != "candidate_fingerprint"})
            and all(manifest.get(key) is False for key in flags), "exact prior reviewed source manifest required")
    review = box.get("candidate_review", {})
    require(box.get("department") == box.get("sender_department") == role and box.get("task_id") == task
            and box.get("candidate_version") == continuation["candidate_version"] and box.get("scope") == plan["scope"]
            and box.get("status") == "partial" and not box.get("goal_acceptance") and box.get("qa_verdict") != "pass"
            and box.get("prepared_only", False) is False and review.get("actor") == role
            and review.get("phase") == "candidate_source_only" and review.get("direction") == "forward"
            and review.get("verdict") == "PASS_SOURCE_CANDIDATE_ONLY" and review.get("candidate_manifest") == manifest_pin
            and review.get("candidate_fingerprint") == manifest["candidate_fingerprint"] and review.get("producer_outbox") == producer_pin
            and review.get("review_plan") == continuation["review_plan"] and review.get("goal_contract") == snapshot["goal_contract"]
            and review.get("human_authorization") == goal["authorization_pin"]
            and all(box.get(key) is False and review.get(key) is False for key in flags), "actual independent prior source-only QA required")
    w.validate_outbox(root, [review_pin], role, task)
    b._native(root, box, [task, continuation["candidate_version"], manifest["candidate_fingerprint"],
                         producer_pin["sha256"], manifest_pin["sha256"], "PASS_SOURCE_CANDIDATE_ONLY"], role)
    require(journal_pin["path"] == f"backups/{task}/{manifest['candidate_fingerprint']}/forward/journal.json"
            and journal.get("task_id") == task and journal.get("candidate_version") == continuation["candidate_version"]
            and journal.get("candidate_fingerprint") == manifest["candidate_fingerprint"] and journal.get("candidate_manifest") == manifest_pin
            and journal.get("review_outbox") == review_pin and journal.get("authorized_source") == goal["authorization_pin"]
            and journal.get("actor") == role and journal.get("direction") == "forward" and journal.get("status") == "complete"
            and journal.get("external_writes") == 0 and journal.get("effect_uncertain") is False
            and journal.get("permissions_issued") is False and journal.get("source_effect_state") == "ALL_REVIEWED_AFTER_VERIFIED",
            "real completed exact prior source CAS journal required")
    operations = journal.get("source_operations", [])
    files = manifest.get("files", [])
    require(isinstance(files, list) and files and len(operations) == len(files)
            and len({row.get("path") for row in files}) == len(files)
            and journal.get("applied") == [row["path"] for row in operations], "complete prior reviewed source operation set required")
    for row in files:
        candidate = row["candidate"]
        _closed_review_source_pins(root, [row["baseline"], candidate, row["forward_diff"], row["reverse_diff"]])
        found = [operation for operation in operations if operation.get("path") == row["path"]]
        require(len(found) == 1, "one exact prior source CAS operation required")
        operation = found[0]
        _closed_review_source_pins(root, [operation["backup"]])
        require(operation.get("before") == row["before"] and operation.get("after_expected") == operation.get("after_actual") == row["after"]
                and operation.get("verified_after") is True and operation.get("write_attempted") is True
                and operation.get("source_syscall_attempted") is True and operation.get("before_mode") == row.get("before_mode")
                and {key:operation["backup"][key] for key in ("sha256", "size")} == row["before"], "real exact prior CAS before/after readback required")
    handoffs = w._result_handoff_rows(root, task)
    decisions = [row for row in handoffs if row.get("record_id") == journal.get("decision_record_id")]
    follows = [row for row in handoffs if row.get("record_id") == continuation.get("adoption_followthrough_record_id")]
    require(len(decisions) == len(follows) == 1, "unique actual prior decision and followthrough required")
    decision, follow = decisions[0], follows[0]
    identity = {"task_id":task,"sender_department":plan["producer_department"],"candidate_version":continuation["candidate_version"],"result_sha256":producer_pin["sha256"]}
    require(c.exact_identity(decision) == c.exact_identity(follow) == identity and decision.get("event") == "controller_decision"
            and decision.get("decision") == "continue" and decision.get("outbox") == producer_pin and review_pin in decision.get("evidence", [])
            and decision.get("next_owner") == role and decision.get("next_action") == "adopt-" + continuation["candidate_version"]
            and decision.get("business_goal_closed") is False and decision.get("qa_status") != "pass"
            and all(row.get("coordinator_role") == row.get("decision_actor") == row.get("responsible_assistant") == role for row in (decision, follow))
            and follow.get("event") == "controller_followthrough" and follow.get("followthrough_status") == "blocked_with_owner"
            and follow.get("outbox") == producer_pin and follow.get("business_goal_closed") is False
            and follow.get("coordinator_owner") == decision.get("coordinator_owner")
            and follow.get("coordination_fence") == decision.get("coordination_fence") and journal_pin in follow.get("evidence", [])
            and isinstance(follow.get("unblock_condition"), str)
            and follow["unblock_condition"].startswith("source-adopted:" + journal["execution_id"] + ";remaining:")
            and len(follow["unblock_condition"]) > len("source-adopted:" + journal["execution_id"] + ";remaining:")
            and handoffs.index(decision) < handoffs.index(follow), "exact actual permanent prior source adoption followthrough required")
    _committed(root, decision); b._v5_source_decision_fence(root, decision, role)
    _committed(root, follow); fence = b._v5_source_decision_fence(root, follow, role)
    released = b._source_release_readback(root, follow, fence)
    times = [_review_observed_at(value) for value in (box["created_at"], decision["created_at"], journal["started_at"], journal["completed_at"], follow["created_at"])]
    def upper(value, parsed):
        return parsed + dt.timedelta(seconds=1) if re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+00:00", value) else parsed
    require(all(value is not None for value in times)
            and times[0] <= upper(decision["created_at"], times[1]) and times[1] <= times[2] <= times[3]
            and times[3] < upper(follow["created_at"], times[4])
            and times[4].timestamp() <= fence["reserved_at"] <= fence["committed_at"]
            and times[3].timestamp() <= fence["committed_at"] <= released["released_at"] <= before.timestamp(),
            "actual prior QA/CAS/commit/release must precede this original continuation")
    queues = [row for row in handoffs if row.get("event") == "notification_queued" and row.get("outbox") == producer_pin]
    receipts = w.read_jsonl(w.receipts_path(root, task))
    received = [row for row in receipts if row.get("department") == plan["producer_department"] and row.get("receipt_type") == "outbox_received" and producer_pin in row.get("evidence", [])]
    prior_producer = _review_source_document(root,producer_pin)
    fixed_producer = w.department_registry(root)[plan["producer_department"]]["chat_binding"]["task_id"]
    require(len(queues) == len(received) == 1 and _producer_candidate_bound(root,previous_plan,producer_pin,prior_producer)
            and c.exact_identity(queues[0]) == identity and queues[0].get("source_thread_id") == fixed_producer
            and queues[0].get("source_turn_id") == prior_producer.get("source_turn_id"),
            "unique exact prior producer outbox and completed source thread/turn required")
    w._validate_goal_completed_result(root, queues[0], fixed_producer, through_receipt_id=received[0]["receipt_id"])
    completed = _review_source_document(root, queues[0]["actual_native_completion"])
    _review_native_containers(completed)
    if isinstance(completed.get("wait"),dict):
        _review_native_containers(completed["wait"])
    native_turn = completed.get("turn", completed)
    require(native_turn.get("id",native_turn.get("turn_id")) == prior_producer.get("source_turn_id")
            and type(native_turn.get("completedAt")) in {int,float} and native_turn["completedAt"] <= before.timestamp(),
            "actual prior completed producer final must precede continuation")
    return continuation_pin


def _hq_original_goal_continuation(root, snapshot, receipts, dispatch, plan):
    """Authenticate the original HQ continuation and a later distinct result.

    The resume keeps its actual old responsibility window. It never needs to
    predict a future candidate hash, and never replaces that candidate's own
    completed-final or the canonical blocked-review rework lineage.
    """
    w = _workflow()
    evidence = dispatch.get("evidence", [])
    if len(evidence) != 1 or not evidence[0].get("path", "").endswith(".json"):
        return None
    send = _review_source_document(root, evidence[0])
    canonical = send.get("schema_version") == "native-dispatch-canonical-v1"
    if not canonical and send.get("schema") != "HQ_native_original_goal_continuation_send_actual_v1":
        return None
    def require(value, reason):
        if not value:
            raise w.WorkflowError("HQ original goal continuation: " + reason)
    try:
        _review_native_containers(send)
        goal, registry = _goal(root, snapshot), w.department_registry(root)
        task, role, owner = snapshot["task_id"], plan["reviewer_department"], plan["producer_department"]
        fixed, hq, producer = [registry[name]["chat_binding"] for name in (role,"operations",owner)]
        contract = snapshot["goal_contract"]
        require(goal is not None and goal["responsible_assistant"] == role and goal["primary_owner"] == owner
                and goal["producer_departments"] == [owner] and _goal_reviewer(root, snapshot) == role
                and plan["task_id"] == task and plan["scope"] in goal["authorized_scope"]
                and plan["reviewer_thread_id"] == fixed["task_id"]
                and _initial_goal_identity(root, snapshot, _review_source_document(root, contract).get("goal_delivery", _review_source_document(root, contract)))
                and all(binding.get("cwd") == str(Path(root).resolve()) and binding.get("project_id") == fixed["project_id"] for binding in (fixed,hq,producer)),
                "exact original complete goal and independent fixed roles required")
        persisted, previous, seen = w.read_jsonl(w.receipts_path(root,task)), "", set()
        for row in persisted:
            require(row.get("task_id") == task and row.get("receipt_id") and row["receipt_id"] not in seen
                    and row.get("previous_hash") == previous and row.get("receipt_hash") == w.sha256_value(w._receipt_payload_for_hash(row)),
                    "complete actual receipt hash chain required")
            previous = row["receipt_hash"]; seen.add(row["receipt_id"])
        require(persisted[:len(receipts)] == receipts and not w.validate_workflow_events(root, task)
                and len([row for row in receipts if row == dispatch]) == 1, "complete actual ledger and exact continuation receipt required")
        index = receipts.index(dispatch)
        initial = [row for row in receipts[:index] if row.get("department") == role and row.get("action_id") == "assign-goal-review:" + task
                   and row.get("receipt_type") in {"dispatch_sent","dispatch_failed"}]
        require(len(initial) == 1 and _initial_assignment(root,snapshot,initial[0])
                and _initial_assignment_envelope(root,snapshot,initial[0],contract), "intact original complete-goal dispatch and ACK responsibility required")
        # Preserve the qualified canonical initial representation. Check its
        # selected native containers without normalizing raw display text.
        initial_index = receipts.index(initial[0])
        initial_end = next((i for i,row in enumerate(receipts) if i > initial_index and row.get("department") == role
                            and row.get("receipt_type") in {"dispatch_sent","dispatch_failed"}),len(receipts))
        initial_acks = [row for row in receipts[initial_index+1:initial_end]
                        if row.get("department") == role and row.get("receipt_type") == "chat_ack"]
        require(len(initial_acks) == 1 and all(initial_acks[0].get(key) == initial[0].get(key) for key in
                    ("task_id","department","action_id","action_class","scope","policy_decision_id","chat_task_id"))
                and not any(initial_acks[0].get(key) for key in ("supersedes_receipt_id","replacement_reason","approval_id"))
                and not any(row.get("supersedes_receipt_id") == initial_acks[0]["receipt_id"] for row in receipts),
                "one intact canonical original assignment ACK identity required")
        for source in initial_acks[0].get("evidence",[]):
            original_ack = _review_source_document(root,source)
            _review_native_containers(original_ack)
            if isinstance(original_ack.get("native_wait_poll"),dict):
                _review_native_containers(original_ack["native_wait_poll"])
        keys = ({"schema_version","task_id","sender_department","target_department","target_thread_id","action_id","policy_decision_id",
                 "payload_sha256","tool_name","recorded_at","actual_target_live","actual_target_section","actual_tool_result"} if canonical else
                {"schema","task_id","source_thread_id","target_thread_id","target_department","action_id","policy_decision_id",
                 "payload_sha256","actual_tool","actual_input","actual_native_result","presend_actual_idle_snapshot"})
        native_result = send.get("actual_tool_result") if canonical else send.get("actual_native_result")
        require(set(send) == keys and send["task_id"] == task
                and (send.get("sender_department") == "operations" if canonical else send.get("source_thread_id") == hq["task_id"])
                and send["target_thread_id"] == fixed["task_id"] and send["target_department"] == role
                and send["action_id"] == dispatch.get("action_id") and send["policy_decision_id"] == dispatch.get("policy_decision_id")
                and send.get("tool_name" if canonical else "actual_tool") == "mcp__codex_app__send_message_to_thread"
                and _review_raw_native_result(native_result) == {"threadId":fixed["task_id"]}
                and dispatch.get("department") == role and dispatch.get("receipt_type") == "dispatch_sent"
                and dispatch.get("action_class") == "thread_message" and dispatch.get("task_id") == task
                and dispatch.get("chat_task_id") == fixed["task_id"] and dispatch.get("scope") == plan["scope"]
                and not any(dispatch.get(key) for key in ("supersedes_receipt_id","replacement_reason","approval_id"))
                and not any(row.get("supersedes_receipt_id") == dispatch["receipt_id"] for row in receipts), "exact unchanged successful HQ continuation transport required")
        supplied = plan.get("original_goal_notice_sources" if canonical else "original_goal_continuation_sources",[])
        require(isinstance(supplied,list) and supplied and len({pin.get("path") for pin in supplied}) == len(supplied), "unique explicit real continuation input pins required")
        _closed_review_source_pins(root,supplied)
        if canonical:
            payloads = [pin for pin in supplied if pin["sha256"] == send["payload_sha256"] and not pin["path"].endswith(".json")]
            require(len(payloads) == 1,"one exact canonical continuation UTF-8 payload required")
            body = w.safe_path(root,payloads[0]["path"]).read_bytes().decode("utf-8")
        else:
            arguments = send["actual_input"]
            require(isinstance(arguments,dict) and set(arguments) == {"threadId","hostId","prompt"}
                    and arguments["threadId"] == fixed["task_id"] and arguments["hostId"] == "local"
                    and isinstance(arguments["prompt"],str) and arguments["prompt"].strip(), "exact original fixed receiver input required")
            body = arguments["prompt"]
        require(body.strip() and hashlib.sha256(body.encode("utf-8")).hexdigest() == send["payload_sha256"] and _exact_text_reference(body,task)
                and (not canonical or (_exact_text_reference(body,contract["path"]) and _exact_text_reference(body,plan["scope"])))
                and (canonical or not (set(re.findall(r"project:[A-Za-z0-9_:.-]+",body)) - set(goal["authorized_scope"]))),
                "complete exact same-goal original UTF-8 input required")
        # Canonical HQ can mention independently assigned goals. Only this
        # frozen goal, plan and exact policy scope supply this reader's authority.
        from result_coordination import coordinator_roles
        require(not any(name not in {"operations",role,goal.get("schedule_target_department")} and _exact_text_reference(body,name)
                        for name in coordinator_roles(root)), "continuation cannot replace original independent reviewer")
        policies = [row for row in w.read_jsonl(root/w.POLICY_DECISIONS) if row.get("decision_id") == dispatch.get("policy_decision_id")]
        expected = {"status":"allow","routing_status":"routing_allowed","task_id":task,"department":"operations","action_id":dispatch["action_id"],
                    "action_class":"thread_message","scope":plan["scope"],"payload_sha256":send["payload_sha256"],"target_department":role,
                    "target_thread_id":fixed["task_id"],"target_thread_title":fixed["title"],"target_cwd":fixed["cwd"],
                    "source_project_id":fixed["project_id"],"target_project_id":fixed["project_id"],"target_sidebar_section_id":fixed.get("sidebar_section_id"),
                    "approval_id":"","routing_quarantine_mode":False,"routing_health_probe_mode":False}
        require(len(policies) == 1 and all(policies[0].get(key) == value for key,value in expected.items())
                and all(policies[0].get(key) is False for key in ("routing_quarantine_mode","routing_health_probe_mode")), "exact original continuation policy required")
        checked, sent = [_review_observed_at(value) for value in (policies[0].get("checked_at"),dispatch.get("created_at"))]
        require(checked is not None and sent is not None and checked <= sent <= dt.datetime.now(dt.timezone.utc), "ordered exact original policy and continuation required")
        if canonical:
            live, section = send["actual_target_live"], send["actual_target_section"]
            _review_native_containers(live); _review_native_containers(section)
            recorded = _review_observed_at(send["recorded_at"])
            sent_second_precision = bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+00:00",dispatch["created_at"]))
            recorded_at_receipt = (sent <= recorded < sent + dt.timedelta(seconds=1) if sent_second_precision
                                   else recorded <= sent) if recorded is not None else False
            require(all(live.get(key) == value for key,value in {"id":fixed["task_id"],"kind":"codex","hostId":"local",
                        "title":fixed["title"],"cwd":fixed["cwd"],"projectId":fixed["project_id"]}.items())
                    and live.get("status") == "idle" and type(live.get("updatedAt")) in {int,float}
                    and live["updatedAt"] <= sent.timestamp() and recorded is not None and checked <= recorded and recorded_at_receipt
                    and section.get("sectionId") == fixed.get("sidebar_section_id")
                    and isinstance(section.get("itemKeys"),list)
                    and len(section["itemKeys"]) == len(set(section["itemKeys"]))
                    and "codex:thread:local:"+fixed["task_id"] in section["itemKeys"],
                    "exact canonical pre-send target identity, idle observation, group and time required")
        else:
            idle = send["presend_actual_idle_snapshot"]; _review_native_containers(idle)
            require(idle.get("timedOut") is False and idle.get("wake",{}).get("reason") == "turnCompleted" and len(idle.get("polls",[])) == 1,
                    "one actual completed pre-send observation required")
            poll = idle["polls"][0]; _review_native_containers(poll)
            oldturn, oldmessage = poll.get("latestTurn",{}), poll.get("latestAssistantMessage",{})
            require(poll.get("schemaVersion") == 1 and poll.get("thread",{}).get("id") == fixed["task_id"]
                    and poll.get("thread",{}).get("hostId") == "local" and poll.get("thread",{}).get("status",{}).get("type") == "idle"
                    and idle["wake"].get("threadId") == fixed["task_id"] and idle["wake"].get("turnId") == oldturn.get("id")
                    and oldturn.get("status") == "completed" and oldturn.get("error") is None and type(oldturn.get("completedAt")) in {int,float}
                    and oldturn["completedAt"] <= sent.timestamp() and oldmessage.get("turnId") == oldturn["id"]
                    and oldmessage.get("phase") == "final_answer" and oldmessage.get("id") == poll.get("latestAssistantMessageId")
                    and isinstance(oldmessage.get("text"),str) and oldmessage["text"].strip(), "intact exact completed original reviewer pre-send observation required")
        candidate = _review_source_document(root,plan["candidate"])
        require(_producer_candidate_bound(root,plan,plan["candidate"],candidate) and candidate.get("goal_contract") == contract
                and candidate.get("human_authorization") == goal["authorization_pin"] and candidate.get("scope") == plan["scope"]
                and candidate.get("responsible_assistant") == role, "separate exact current producer candidate identity required")
        original_reply = _review_source_document(root, candidate.get("actual_native_reply"))
        _review_native_containers(original_reply)
        original_thread = original_reply.get("thread", {})
        original_turns = original_reply.get("turns")
        if original_turns is None and isinstance(original_reply.get("turn"), dict) and isinstance(original_reply.get("message"), dict):
            original_turns = [{**original_reply["turn"], "items": [original_reply["message"]]}]
        require(isinstance(original_turns, list), "complete original producer native turns required")
        original_turns = [turn for turn in original_turns if isinstance(turn, dict)
                          and turn.get("id") == candidate.get("source_turn_id")]
        require(len(original_turns) == 1, "one original producer reply turn required")
        original_turn = original_turns[0]
        _review_native_containers(original_turn)
        original_messages = [message for message in original_turn.get("items", []) if isinstance(message, dict)
                             and message.get("id") == candidate.get("source_message_id")]
        require(len(original_messages) == 1, "one original frozen producer reply message required")
        original_message = original_messages[0]
        _review_native_containers(original_message)
        original_bytes = w.safe_path(root, candidate["visible_reply"]["path"]).read_bytes()
        original_meta = candidate.get("chat_reply", {})
        require(w.file_digest(root, candidate["visible_reply"]["path"]) == candidate["visible_reply"]
                and all(original_thread.get(key) == value for key, value in {"id": producer["task_id"], "kind": "codex",
                    "hostId": "local", "title": producer["title"], "cwd": producer["cwd"]}.items())
                and original_thread.get("projectId", producer["project_id"]) == producer["project_id"]
                and original_turn.get("id") == candidate.get("source_turn_id")
                and original_turn.get("status") in {"inProgress", "completed"}
                and original_message.get("type") == "agentMessage" and original_message.get("id") == candidate.get("source_message_id")
                and original_message.get("phase") in {"commentary", "final_answer"}
                and isinstance(original_message.get("text"), str) and original_message["text"].strip()
                and original_message["text"].encode("utf-8") == original_bytes
                and candidate.get("source_reply_sha256") == candidate["visible_reply"]["sha256"]
                and all(original_meta.get(key) == value for key, value in {"nonempty": True,
                    "in_current_fixed_department_chat": True, "source_turn_id": original_turn["id"],
                    "source_message_id": original_message["id"], "ref": original_message["id"],
                    "sha256": candidate["visible_reply"]["sha256"], "utf8_bytes": len(original_bytes)}.items()),
                "intact original frozen producer reply and UTF-8 identity required")
        sources = _candidate_review_source_pins(root,snapshot,plan)
        known = [contract,goal["authorization_pin"],plan["candidate"],*sources,*[pin for row in receipts for pin in row.get("evidence",[])]]
        closed = _closed_review_source_pins(root,known+supplied)
        payloads = [pin for pin in supplied if pin["sha256"] == send["payload_sha256"] and w.safe_path(root,pin["path"]).read_bytes() == body.encode("utf-8")]
        require(len(payloads) == 1, "one complete existing original continuation payload required")
        payload = payloads[0]
        found = {}
        for source in closed:
            if not source["path"].endswith(".json"): continue
            doc = _review_source_document(root,source,object_only=False)
            if not isinstance(doc,dict) or doc.get("thread",{}).get("id") != fixed["task_id"]: continue
            for turn in doc.get("turns",[]):
                for item in turn.get("items",[]):
                    if item.get("type") != "functionCallOutput" or item.get("name") != "send_message_to_thread" or item.get("namespace") != "codex_app": continue
                    output = item.get("output",{})
                    if not isinstance(output.get("text"),str): continue
                    match = re.fullmatch(r"<codex_delegation>\s*<source_thread_id>([^<]+)</source_thread_id>\s*<input>([\s\S]*)</input>\s*</codex_delegation>",output["text"])
                    if match is None or match[2].encode("utf-8") != body.encode("utf-8"): continue
                    for container in (doc,doc["thread"],turn,item,output): _review_native_containers(container)
                    require(match[1] == hq["task_id"] and output.get("truncated") is False
                            and turn.get("status") in {"inProgress","completed","interrupted"} and turn.get("error") is None
                            and turn.get("id") and item.get("id") and all(doc["thread"].get(key) == value for key,value in
                                {"kind":"codex","hostId":"local","title":fixed["title"],"cwd":fixed["cwd"]}.items())
                            and doc["thread"].get("projectId",fixed["project_id"]) == fixed["project_id"], "complete exact original received continuation source required")
                    key = (turn["id"],item["id"])
                    require(key not in found, "ambiguous received continuation source rejected")
                    found[key] = {"pin":source,"turn":turn}
        require(len(found) == 1, "one actual received original continuation required")
        received = next(iter(found.values())); turn = received["turn"]
        require(all(pin in known or pin == payload or pin == received["pin"] for pin in supplied), "unknown continuation input source rejected")
        end = next((i for i,row in enumerate(receipts) if i > index and row.get("department") == role and row.get("receipt_type") in {"dispatch_sent","dispatch_failed"}),len(receipts))
        acks = [(i,row) for i,row in enumerate(receipts) if index < i < end and row.get("department") == role and row.get("receipt_type") == "chat_ack"]
        require(len(acks) == 1, "one actual original continuation ACK required")
        ack_index, ack = acks[0]
        require(ack.get("ack_nonempty") is True and ack.get("chat_task_id") == fixed["task_id"]
                and all(ack.get(key) == dispatch.get(key) for key in ("task_id","action_id","action_class","scope","policy_decision_id"))
                and not any(ack.get(key) for key in ("supersedes_receipt_id","replacement_reason","approval_id"))
                and not any(row.get("supersedes_receipt_id") == ack["receipt_id"] for row in receipts) and len(ack.get("evidence",[])) == 1,
                "exact original continuation ACK identity required")
        native = _review_source_document(root,ack["evidence"][0]); _review_native_containers(native)
        if canonical:
            ackkeys = {"schema_version","task_id","department","fixed_chat_task_id","new_turn_id","ack_nonempty",
                       "is_candidate_result","native_wait_poll","raw_native_wait","recorded_at"}
            require(set(native) == ackkeys and native["schema_version"] == "native-chat-ack-canonical-v1"
                    and native["task_id"] == task and native["department"] == role and native["fixed_chat_task_id"] == fixed["task_id"]
                    and native["new_turn_id"] == turn["id"] and native["ack_nonempty"] is True and native["is_candidate_result"] is False,
                    "intact exact canonical same-goal ACK source required")
            batch = _review_raw_native_result(native["raw_native_wait"])
            require(type(batch.get("timedOut")) is bool and "wake" in batch and len(batch.get("polls",[])) == 1
                    and not set(batch)-{"timedOut","wake","polls","errors","error","truncated","failed","superseded","isError"},
                    "one complete successful canonical ACK poll required")
            apoll = native["native_wait_poll"]; _review_native_containers(apoll)
            require(batch["polls"][0] == apoll,"exact canonical raw wait and selected ACK poll must agree")
        else:
            ackkeys = {"schema","task_id","actual_native_tool","actual_result","source_message","dispatch_evidence","chat_ack_only","is_final_result"}
            require(set(native) == ackkeys and native["schema"] == "HQ_original_goal_continuation_actual_nonempty_ACK_v1"
                    and native["task_id"] == task and native["actual_native_tool"] == "mcp__codex_app__wait_threads"
                    and native["dispatch_evidence"] == evidence[0]["path"] and native["chat_ack_only"] is True and native["is_final_result"] is False,
                    "intact exact original wait ACK source required")
            batch = native["actual_result"]; _review_native_containers(batch)
            require(type(batch.get("timedOut")) is bool and "wake" in batch and len(batch.get("polls",[])) == 1
                    and not set(batch)-{"timedOut","wake","polls","errors","error","truncated","failed","superseded","isError"}, "one complete successful original wait ACK poll required")
            apoll = batch["polls"][0]; _review_native_containers(apoll)
        message = apoll.get("latestAssistantMessage",{}); _review_native_containers(message)
        rawmessages = [item for item in turn.get("items",[]) if item.get("id") == message.get("id")]
        at = _review_observed_at(ack.get("created_at"))
        if canonical:
            ack_recorded = _review_observed_at(native["recorded_at"])
            ack_second_precision = bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+00:00",ack["created_at"]))
            ack_at_receipt = (at <= ack_recorded < at + dt.timedelta(seconds=1) if ack_second_precision
                             else ack_recorded <= at) if at is not None and ack_recorded is not None else False
            require(at is not None and ack_recorded is not None and sent <= ack_recorded and ack_at_receipt
                    and ack_recorded <= dt.datetime.now(dt.timezone.utc),"canonical ACK observation must match its actual receipt precision")
        require(apoll.get("schemaVersion") == 1 and apoll.get("thread",{}).get("id") == fixed["task_id"] and apoll.get("thread",{}).get("hostId") == "local"
                and type(apoll.get("revision")) is int and apoll["revision"] > 0 and isinstance(apoll.get("cursor"),str)
                and apoll["cursor"].endswith(":"+str(apoll["revision"])) and type(apoll.get("changed")) is bool
                and apoll.get("latestTurn",{}).get("id") == turn["id"] and apoll.get("latestTurn",{}).get("status") in {"inProgress","completed"}
                and apoll.get("latestTurn",{}).get("error") is None and apoll.get("latestTurn",{}).get("startedAt") == turn.get("startedAt")
                and message.get("id") == apoll.get("latestAssistantMessageId") and (canonical or message == native["source_message"])
                and message.get("turnId") == turn["id"] and message.get("phase") in {"commentary","final_answer"}
                and isinstance(message.get("text"),str) and bool(message["text"].strip()) and len(rawmessages) == 1
                and at is not None and checked <= sent <= at <= dt.datetime.now(dt.timezone.utc)
                and type(turn.get("startedAt")) in {int,float} and checked.timestamp() <= turn["startedAt"] <= at.timestamp(),
                "original ACK must match its exact observed receiving turn and wait message")
        rawmessage = rawmessages[0]; _review_native_containers(rawmessage)
        require(rawmessage.get("type") == "agentMessage" and rawmessage.get("phase") == message["phase"]
                and (rawmessage.get("text") == message["text"] or (not message["text"].endswith("\n") and rawmessage.get("text") == message["text"]+"\n")),
                "only exact observed native ACK or its single terminal-LF view is legal")
        if turn["status"] == "interrupted":
            require(type(turn.get("completedAt")) in {int,float} and turn["completedAt"] >= at.timestamp(), "historical interruption must follow the actual ACK observation")
        _original_goal_adopted_source(root,snapshot,plan,sources,sent)
        boxes = [row for row in receipts if row.get("department") == owner and row.get("receipt_type") == "outbox_received" and plan["candidate"] in row.get("evidence",[])]
        require(len(boxes) == 1, "one separate actual current producer outbox receipt required")
        queues = [row for row in w._result_handoff_rows(root,task) if row.get("event") == "notification_queued" and row.get("sender_department") == owner
                  and row.get("outbox") == plan["candidate"] and row.get("candidate_version") == plan["candidate_version"] and row.get("result_sha256") == plan["candidate_sha256"]]
        require(len(queues) == 1, "one separate actual current completed producer result required")
        w._validate_goal_completed_result(root,queues[0],producer["task_id"],through_receipt_id=boxes[0]["receipt_id"])
        completed = _review_source_document(root,queues[0]["actual_native_completion"])
        _review_native_containers(completed)
        if isinstance(completed.get("wait"),dict):
            _review_native_containers(completed["wait"])
        observed, created = [_review_observed_at(candidate.get(key)) for key in ("reply_observed_at","created_at")]
        final_observed = _review_observed_at(queues[0].get("reply_observed_at"))
        require(type(original_turn.get("startedAt")) in {int,float} and observed is not None and created is not None
                and final_observed is not None and original_turn["startedAt"] <= observed.timestamp()
                and (canonical or sent.timestamp() <= original_turn["startedAt"])
                and observed <= created <= final_observed <= dt.datetime.now(dt.timezone.utc),
                "current candidate original reply and completion observations must remain ordered")
        require(queues[0].get("source_turn_id") == candidate.get("source_turn_id")
                and completed.get("turn",{}).get("id") == candidate.get("source_turn_id")
                and all(completed.get("thread",{}).get(key) == value for key,value in
                        {"id":producer["task_id"],"kind":"codex","hostId":"local","title":producer["title"],"cwd":producer["cwd"]}.items())
                and completed.get("thread",{}).get("projectId",producer["project_id"]) == producer["project_id"]
                and type(completed.get("turn",{}).get("completedAt")) in {int,float}
                and (canonical or sent.timestamp() <= completed["turn"]["completedAt"]),
                "separate later candidate must bind its exact own completed producer turn")
        return {"dispatch":dispatch,"dispatch_index":index,"ack":ack,"ack_index":ack_index}
    except (OSError,ValueError,TypeError,KeyError,AttributeError) as exc:
        raise w.WorkflowError("HQ original goal continuation: complete exact native and source provenance required") from exc


def _modern_original_goal_continuation(root, snapshot, receipts, dispatch, plan):
    """Read a same-goal native resume before the first canonical plan exists.

    The optional full-pin index supplies existing input bytes, never authority.
    Initial responsibility, the original completed result and this send/ACK are
    independently authenticated; a recognized but invalid resume cannot fall
    back to a different dispatch or to a fabricated source-only package.
    """
    w = _workflow()
    evidence = dispatch.get("evidence", [])
    if len(evidence) != 1 or not evidence[0].get("path", "").endswith(".json"):
        return None
    send = _review_source_document(root, evidence[0])
    if send.get("schema") != "flashcast-original-goal-continuation-actual-send/v1":
        return None
    def require(value, message):
        if not value:
            raise w.WorkflowError("original goal continuation: " + message)
    try:
        goal, registry = _goal(root, snapshot), w.department_registry(root)
        task, role, owner = snapshot["task_id"], plan["reviewer_department"], plan["producer_department"]
        fixed, hq, producer = [registry[name]["chat_binding"] for name in (role, "operations", owner)]
        contract = snapshot["goal_contract"]
        require(goal is not None and goal["responsible_assistant"] == role and goal["primary_owner"] == owner
                and goal["producer_departments"] == [owner] and _goal_reviewer(root, snapshot) == role
                and plan["task_id"] == task and plan["scope"] in goal["authorized_scope"]
                and plan["reviewer_thread_id"] == fixed["task_id"]
                and _initial_goal_identity(root, snapshot, _review_source_document(root, contract).get(
                    "goal_delivery", _review_source_document(root, contract)))
                and all(binding.get("cwd") == str(Path(root).resolve())
                        and binding.get("project_id") == fixed.get("project_id") for binding in (fixed, hq, producer)),
                "exact original goal and independent fixed roles required")
        persisted, previous, seen = w.read_jsonl(w.receipts_path(root, task)), "", set()
        for row in persisted:
            require(row.get("task_id") == task and row.get("receipt_id") and row["receipt_id"] not in seen
                    and row.get("previous_hash") == previous
                    and row.get("receipt_hash") == w.sha256_value(w._receipt_payload_for_hash(row)),
                    "complete actual original receipt hash chain required")
            previous = row["receipt_hash"]
            seen.add(row["receipt_id"])
        # Verdict validation supplies its original prefix. Verify the complete
        # persisted ledger without recursively revalidating that same verdict.
        require(persisted[:len(receipts)] == receipts and not w.validate_workflow_events(root, task),
                "actual original receipt prefix and complete event chain required")
        require(len([row for row in receipts if row == dispatch]) == 1, "one actual resume dispatch required")
        index = receipts.index(dispatch)
        initial = [row for row in receipts[:index] if row.get("department") == role
                   and row.get("action_id") == "assign-goal-review:" + task
                   and row.get("receipt_type") in {"dispatch_sent", "dispatch_failed"}]
        require(len(initial) == 1 and _initial_assignment(root, snapshot, initial[0]),
                "intact original complete-goal responsibility required")
        expected_send = {"schema", "task_id", "action_id", "scope", "policy_decision_id", "payload_sha256",
                         "tool_name", "tool_arguments", "actual_tool_result", "live_identity", "receipt_status"}
        require(set(send) == expected_send and send["task_id"] == task and send["scope"] == plan["scope"]
                and send["action_id"] == dispatch.get("action_id")
                and send["policy_decision_id"] == dispatch.get("policy_decision_id")
                and send["tool_name"] == "mcp__codex_app__send_message_to_thread"
                and send["receipt_status"] == "actual_native_send_returned_not_final_delivery"
                and dispatch.get("department") == role and dispatch.get("task_id") == task
                and dispatch.get("receipt_type") == "dispatch_sent" and dispatch.get("action_class") == "thread_message"
                and dispatch.get("chat_task_id") == fixed["task_id"] and dispatch.get("scope") == plan["scope"]
                and dispatch.get("action_id") != "assign-goal-review:" + task
                and not any(dispatch.get(key) for key in ("supersedes_receipt_id", "replacement_reason", "approval_id"))
                and not any(row.get("supersedes_receipt_id") == dispatch.get("receipt_id") for row in receipts)
                and _review_raw_native_result(send["actual_tool_result"]) == {"threadId": fixed["task_id"]},
                "exact successful native resume transport required")
        arguments = send["tool_arguments"]
        require(isinstance(arguments, dict) and set(arguments) == {"threadId", "hostId", "prompt"}
                and arguments["threadId"] == fixed["task_id"] and arguments["hostId"] == "local"
                and isinstance(arguments["prompt"], str) and bool(arguments["prompt"].strip()),
                "exact fixed resume arguments required")
        body = arguments["prompt"]
        require(hashlib.sha256(body.encode("utf-8")).hexdigest() == send["payload_sha256"]
                and _exact_text_reference(body, task) and _exact_text_reference(body, contract["path"])
                and not (set(re.findall(r"project:[A-Za-z0-9_:.-]+", body)) - set(goal["authorized_scope"])),
                "original contract and exact same-scope UTF-8 payload required")
        from result_coordination import coordinator_roles
        require(not any(name not in {"operations", role, goal.get("schedule_target_department")}
                        and _exact_text_reference(body, name) for name in coordinator_roles(root)),
                "resume cannot replace the original reviewer")
        live = send["live_identity"]
        require(isinstance(live, list) and len(live) == 2 and len({row.get("id") for row in live}) == 2,
                "one original sender and receiver identity required")
        for binding in (fixed, hq):
            matches = [row for row in live if row.get("id") == binding["task_id"]]
            require(len(matches) == 1, "one original native live identity required")
            _review_native_containers(matches[0])
            require(all(matches[0].get(key) == value for key, value in {"kind": "codex", "hostId": "local",
                        "title": binding["title"], "cwd": binding["cwd"], "projectId": binding["project_id"]}.items()),
                    "exact original sender and receiver project identity required")
        policies = [row for row in w.read_jsonl(root / w.POLICY_DECISIONS)
                    if row.get("decision_id") == dispatch.get("policy_decision_id")]
        expected_policy = {"status": "allow", "routing_status": "routing_allowed", "task_id": task,
            "department": "operations", "action_id": dispatch["action_id"], "action_class": "thread_message",
            "scope": plan["scope"], "payload_sha256": send["payload_sha256"], "target_department": role,
            "target_thread_id": fixed["task_id"], "target_thread_title": fixed["title"], "target_cwd": fixed["cwd"],
            "source_project_id": fixed["project_id"], "target_project_id": fixed["project_id"],
            "target_sidebar_section_id": fixed.get("sidebar_section_id"), "approval_id": "",
            "routing_quarantine_mode": False, "routing_health_probe_mode": False}
        require(len(policies) == 1 and all(policies[0].get(key) == value for key, value in expected_policy.items())
                and all(policies[0].get(key) is False for key in ("routing_quarantine_mode", "routing_health_probe_mode")),
                "exact original resume policy required")
        checked, sent = [_review_observed_at(value) for value in (policies[0].get("checked_at"), dispatch.get("created_at"))]
        require(checked is not None and sent is not None and checked <= sent <= dt.datetime.now(dt.timezone.utc),
                "ordered original policy and actual dispatch required")
        candidate = _review_source_document(root, plan["candidate"])
        require(_producer_candidate_bound(root, plan, plan["candidate"], candidate)
                and candidate.get("goal_contract") == contract and candidate.get("human_authorization") == goal["authorization_pin"]
                and candidate.get("scope") == plan["scope"] and candidate.get("responsible_assistant") == role,
                "exact original producer result identity required")
        original_reply = _review_source_document(root, candidate.get("actual_native_reply"))
        _review_native_containers(original_reply)
        original_thread = original_reply.get("thread", {})
        original_turns = original_reply.get("turns")
        if original_turns is None and isinstance(original_reply.get("turn"), dict) and isinstance(original_reply.get("message"), dict):
            original_turns = [{**original_reply["turn"], "items": [original_reply["message"]]}]
        require(isinstance(original_turns, list), "complete original producer native turns required")
        original_turns = [turn for turn in original_turns if isinstance(turn, dict)
                          and turn.get("id") == candidate.get("source_turn_id")]
        require(len(original_turns) == 1, "one original producer reply turn required")
        original_turn = original_turns[0]
        _review_native_containers(original_turn)
        original_messages = [message for message in original_turn.get("items", []) if isinstance(message, dict)
                             and message.get("id") == candidate.get("source_message_id")]
        require(len(original_messages) == 1, "one original frozen producer reply message required")
        original_message = original_messages[0]
        _review_native_containers(original_message)
        original_bytes = w.safe_path(root, candidate["visible_reply"]["path"]).read_bytes()
        original_meta = candidate.get("chat_reply", {})
        require(w.file_digest(root, candidate["visible_reply"]["path"]) == candidate["visible_reply"]
                and all(original_thread.get(key) == value for key, value in {"id": producer["task_id"], "kind": "codex",
                    "hostId": "local", "title": producer["title"], "cwd": producer["cwd"]}.items())
                and original_thread.get("projectId", producer["project_id"]) == producer["project_id"]
                and original_turn.get("id") == candidate.get("source_turn_id")
                and original_turn.get("status") in {"inProgress", "completed"}
                and original_message.get("type") == "agentMessage" and original_message.get("id") == candidate.get("source_message_id")
                and original_message.get("phase") in {"commentary", "final_answer"}
                and isinstance(original_message.get("text"), str) and original_message["text"].strip()
                and original_message["text"].encode("utf-8") == original_bytes
                and candidate.get("source_reply_sha256") == candidate["visible_reply"]["sha256"]
                and all(original_meta.get(key) == value for key, value in {"nonempty": True,
                    "in_current_fixed_department_chat": True, "source_turn_id": original_turn["id"],
                    "source_message_id": original_message["id"], "ref": original_message["id"],
                    "sha256": candidate["visible_reply"]["sha256"], "utf8_bytes": len(original_bytes)}.items()),
                "intact original frozen producer reply and UTF-8 identity required")
        boxes = [row for row in receipts[:index] if row.get("department") == owner
                 and row.get("receipt_type") == "outbox_received" and plan["candidate"] in row.get("evidence", [])]
        require(len(boxes) == 1, "one actual original producer outbox receipt required")
        producer_sends = [row for row in receipts[:receipts.index(boxes[0])] if row.get("department") == owner
                          and row.get("receipt_type") in {"dispatch_sent", "dispatch_failed"}]
        require(len(producer_sends) == 1 and _modern_initial_assignment_transport(root, snapshot, producer_sends[0], contract),
                "intact original producer dispatch and ACK required")
        queued = [row for row in w._result_handoff_rows(root, task) if row.get("event") == "notification_queued"
                  and row.get("sender_department") == owner and row.get("outbox") == plan["candidate"]
                  and row.get("candidate_version") == plan["candidate_version"] and row.get("result_sha256") == plan["candidate_sha256"]]
        require(len(queued) == 1 and queued[0].get("target_department") == role,
                "one actual completed original producer result required")
        completion = queued[0]
        w._validate_goal_completed_result(root, completion, producer["task_id"],
            through_receipt_id=boxes[0]["receipt_id"])
        completed = _review_source_document(root, completion["actual_native_completion"])
        _review_native_containers(completed)
        if isinstance(completed.get("wait"), dict):
            _review_native_containers(completed["wait"])
            for poll in completed["wait"].get("polls", []):
                _review_native_containers(poll)
        require(all(completed.get("thread", {}).get(key) == value for key, value in {"id": producer["task_id"],
                    "kind": "codex", "hostId": "local", "title": producer["title"], "cwd": producer["cwd"]}.items())
                and completed.get("thread", {}).get("projectId", producer["project_id"]) == producer["project_id"]
                and completed.get("turn", {}).get("id") == candidate.get("source_turn_id")
                and type(completed.get("turn", {}).get("completedAt")) in {int, float}
                and completed["turn"]["completedAt"] <= sent.timestamp()
                and _exact_text_reference(body, plan["candidate_sha256"]),
                "original completed result must precede and bind this resume")
        supplied = plan.get("original_goal_continuation_sources", [])
        require(isinstance(supplied, list) and supplied and len({pin.get("path") for pin in supplied}) == len(supplied),
                "unique explicit original continuation input pins required")
        known = [contract, goal["authorization_pin"], plan["candidate"], completion["actual_native_completion"], completion["visible_reply"],
                 *list(_evidence_pins(candidate.get("evidence", []))),
                 *[pin for row in receipts for pin in row.get("evidence", [])]]
        closed = _closed_review_source_pins(root, known + supplied)
        payloads = [pin for pin in supplied if pin["sha256"] == send["payload_sha256"]
                    and w.safe_path(root, pin["path"]).read_bytes() == body.encode("utf-8")]
        require(len(payloads) == 1, "one exact existing resume payload file required")
        payload = payloads[0]
        received = _review_received_input(root, closed, payload, role, "operations", registry, include_pin=True)
        require(all(pin in known or pin == payload or pin == received["pin"] for pin in supplied),
                "unknown continuation index source rejected")
        end = next((i for i, row in enumerate(receipts) if i > index and row.get("department") == role
                    and row.get("receipt_type") in {"dispatch_sent", "dispatch_failed"}), len(receipts))
        acks = [(i, row) for i, row in enumerate(receipts) if index < i < end
                and row.get("department") == role and row.get("receipt_type") == "chat_ack"]
        require(len(acks) == 1, "one actual resume ACK required")
        ack_index, ack = acks[0]
        require(ack.get("ack_nonempty") is True and ack.get("chat_task_id") == fixed["task_id"]
                and all(ack.get(key) == dispatch.get(key) for key in ("task_id", "action_id", "action_class", "scope", "policy_decision_id"))
                and not any(ack.get(key) for key in ("supersedes_receipt_id", "replacement_reason", "approval_id"))
                and not any(row.get("supersedes_receipt_id") == ack.get("receipt_id") for row in receipts)
                and len(ack.get("evidence", [])) == 1, "exact original resume ACK identity required")
        native = _review_source_document(root, ack["evidence"][0])
        expected_ack = {"schema", "task_id", "action_id", "scope", "tool_name", "tool_arguments", "actual_tool_result",
                        "ack_nonempty", "ack_is_delivery", "source_turn_id", "source_message_id", "payload_sha256"}
        require(set(native) == expected_ack and native.get("schema") == "flashcast-original-goal-resume-actual-ACK/v1"
                and all(native.get(key) == send.get(key) for key in ("task_id", "action_id", "scope", "payload_sha256"))
                and native.get("tool_name") == "mcp__codex_app__wait_threads"
                and native.get("tool_arguments") == {"targets": [{"hostId": "local", "threadId": fixed["task_id"]}], "timeoutMs": 0}
                and native.get("ack_nonempty") is True and native.get("ack_is_delivery") is False,
                "exact successful native resume ACK wrapper required")
        batch = _review_raw_native_result(native["actual_tool_result"])
        require(type(batch.get("timedOut")) is bool and "wake" in batch and len(batch.get("polls", [])) == 1
                and not set(batch) - {"timedOut", "wake", "polls", "errors", "error", "truncated", "failed", "superseded", "isError"},
                "one intact native resume ACK poll required")
        poll, turn = batch["polls"][0], received["turn"]
        message = poll.get("latestAssistantMessage", {})
        original_messages = [item for item in turn.get("items", []) if item.get("id") == native["source_message_id"]]
        at = _review_observed_at(ack.get("created_at"))
        require(poll.get("schemaVersion") == 1 and poll.get("thread", {}).get("id") == fixed["task_id"]
                and poll.get("thread", {}).get("hostId") == "local" and type(poll.get("revision")) is int and poll["revision"] > 0
                and isinstance(poll.get("cursor"), str) and poll["cursor"].endswith(":" + str(poll["revision"]))
                and type(poll.get("changed")) is bool and poll.get("latestTurn", {}).get("id") == turn["id"]
                and native["source_turn_id"] == turn["id"] and message.get("id") == native["source_message_id"]
                and poll.get("latestAssistantMessageId") == message.get("id") and len(original_messages) == 1
                and original_messages[0].get("type") == "agentMessage" and original_messages[0].get("phase") == message.get("phase")
                and message.get("phase") in {"commentary", "final_answer"} and message.get("turnId") == turn["id"]
                and isinstance(message.get("text"), str) and bool(message["text"].strip())
                and original_messages[0].get("text", "").encode("utf-8") == message["text"].encode("utf-8")
                and type(turn.get("startedAt")) in {int, float} and poll.get("latestTurn", {}).get("startedAt") == turn["startedAt"]
                and poll.get("latestTurn", {}).get("status") in {"inProgress", "completed"}
                and at is not None and checked <= sent <= at <= dt.datetime.now(dt.timezone.utc)
                and checked.timestamp() <= turn["startedAt"] <= at.timestamp(),
                "resume ACK must match the complete original receiving turn and message")
        _review_native_containers(poll)
        _review_native_containers(original_messages[0])
        return {"dispatch": dispatch, "dispatch_index": index, "ack": ack, "ack_index": ack_index}
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
        raise w.WorkflowError("original goal continuation: complete exact native sources required") from exc


def _owner_original_resume_bound_prefix(root, snapshot, receipts, dispatch, plan):
    """Revalidate an actually bound pre-verdict successor back to its origin.

    Recomputes the writer's source metadata with its actual receipt prefix.
    No verdict, binding, event, time or dispatch is manufactured.
    """
    w = _workflow()
    binding = _binding(root, snapshot)
    if (not isinstance(binding, dict) or plan != _review_source_document(root, binding.get('pin'))
            or w.validate_workflow_events(root, snapshot['task_id'])):
        return False
    events = [e for e in w.read_jsonl(root / w.WORKFLOW_EVENTS) if e.get('task_id') == snapshot['task_id']]
    selected = [(i, e) for i, e in enumerate(events)
                if e.get('details', {}).get('qa_review_plan_bound') == binding]
    if len(selected) != 1:
        return False
    index, event = selected[0]
    proof = event['details'].get('original_pre_verdict_successor')
    if not isinstance(proof, dict) or proof.get('prior_plan') == binding['pin']:
        return False
    previous = [e['details']['qa_review_plan_bound'] for e in events[:index]
                if e.get('details', {}).get('qa_review_plan_bound', {}).get('pin') == proof.get('prior_plan')]
    producers = [i for i, row in enumerate(receipts) if row.get('receipt_id') == proof.get('producer_outbox_receipt_id')]
    if len(previous) != 1 or len(producers) != 1:
        return False
    historical = {**snapshot, 'qa_review_plan': previous[0]}
    computed = _validate_rework(root, historical, receipts[:producers[0] + 1], previous[0], plan)
    if computed != proof:
        return False
    rows = w._result_handoff_rows(root, snapshot['task_id'])
    intake = [row for row in rows if row.get('record_id') == proof['controller_received_record_id']]
    if len(intake) != 1:
        return False
    received, bound = (_review_observed_at(x) for x in (intake[0].get('created_at'), event.get('created_at')))
    return bool(received and bound and received <= bound <= dt.datetime.now(dt.timezone.utc))


def _owner_original_producer_HQ_resume(root, snapshot, receipts, dispatch, plan):
    """Read one true later HQ responsibility resume, retaining its accepted prefix.

    This only classifies the frozen native notice. Current-result, independent
    acceptance, source/adoption, authority and production guards remain outside.
    """
    task = 'fc-20261021-owner-delegated-nonpayment-decisions-repair-v1'
    if (snapshot.get('task_id') != task or dispatch.get('receipt_id') != '1a3ac28a-f06c-42ce-a14b-1b9a1d785b69'):
        return False
    w = _workflow()
    base = 'logs/handoffs/2026-10-20-clean-department-window-rotation-v1/operations/unfinished-business-followthrough-20261021-v1/'
    evidence_base = base + 'owner-delegated-nonpayment-decisions-system-repair-v1/operations-assistant-2-independent-review-v1/'
    frozen_pin = {'path': evidence_base + 'OWNER-PARENT-FINAL-QA-LATER-HQ-RESUME-EXACT-REJECTION-v1.json',
                  'sha256':'9174401f50d5e6f09e77b34448adbd8025a48f482e472e5a6e4466e0a22196a2','size':6444}
    try:
        # Exact immutable triage proves which real dispatch/ACK is being read;
        # flags or a newly supplied plan cannot manufacture a resume.
        frozen = _review_source_document(root, frozen_pin)
        goal = _goal(root, snapshot); scope = 'project:flashcast:owner-delegated-nonpayment-decisions:20261021:v1'
        if (goal is None or goal['primary_owner'] != 'system-development'
                or goal['producer_departments'] != ['system-development']
                or goal['responsible_assistant'] != 'operations-assistant-2' or goal['authorized_scope'] != [scope]
                or any(plan.get(k) != v for k,v in {'task_id':task,'scope':scope,'producer_department':'system-development',
                    'reviewer_department':'operations-assistant-2'}.items())
                or dispatch != frozen['actual_later_HQ_ordinary_resume_dispatch']):return False
        rows = _strict_source_rows(root,task)
        if not receipts or receipts != rows[:len(receipts)]:return False
        previous = ''; seen = set()
        for row in rows:
            if (row.get('task_id') != task or not row.get('receipt_id') or row['receipt_id'] in seen
                    or row.get('previous_hash','') != previous
                    or row.get('receipt_hash') != w.sha256_value(w._receipt_payload_for_hash(row))):return False
            for pin in row.get('evidence',[]):
                if w.file_digest(root,pin.get('path','')) != pin:return False
            previous=row['receipt_hash'];seen.add(row['receipt_id'])
        if sum(row == dispatch for row in receipts) != 1:return False
        ack = frozen['actual_later_nonempty_ACK']; anchor_id = 'c20280b2-946e-4674-abb1-bc2e5e872cad'
        anchors=[(i,row)for i,row in enumerate(receipts)if row.get('receipt_id')==anchor_id]
        acknowledgements=[row for row in receipts if row.get('department')=='system-development'
            and row.get('action_id')==dispatch['action_id']and row.get('receipt_type')=='chat_ack']
        if (len(anchors)!=1 or anchors[0][1].get('receipt_hash')!='88129ccb02765a74943e0a858907c51aa251c492a0fea64c207c259696408262'
                or acknowledgements != [ack] or receipts.index(dispatch)>=receipts.index(ack)
                or any(row.get('supersedes_receipt_id') in {dispatch['receipt_id'],ack['receipt_id']}for row in rows)):return False
        original_plan_pin={'path':evidence_base+'OWNER-V2-NORMAL-REVIEW-PLAN-v1.json',
            'sha256':'e16275f817ab8be407e09fc5dbe5bae447fb60e0ebcb6983374e0b397fc5394b','size':1263}
        original_plan=_review_source_document(root,original_plan_pin)
        if plan != original_plan or snapshot.get('qa_review_plan',{}).get('pin')!=original_plan_pin:
            return _owner_original_resume_bound_prefix(root, snapshot, receipts, dispatch, plan)
        # Reuse the already committed original independent source prefix only.
        # No later parent QA is recursively required to authenticate itself.
        accepted=w._goal_bounded_candidate_subject(root,snapshot,receipts[:anchors[0][0]+1],original_plan,'system-development')
        if (accepted.get('state')!='PROVEN' or accepted.get('source_fingerprint')!='e65e1cdeb1c8f9eb1f3629f609513a3e1eb2c1a06e47be61dc463c1fe192b522'
                or anchors[0][0]>=receipts.index(dispatch)):return False
        from goal_continuity import _dispatch_source
        original_assignment_pin={'path':base+'owner-delegated-nonpayment-decisions-system-repair-v1/system-development-v1/actual-SYS-assignment-input-v1.json',
            'sha256':'a80ade54485e5abea5143759473cf8bce328d6ea8827a603b140c609fa715171','size':4156}
        original_snapshot, original_dispatch=_dispatch_source(root,_review_source_document(root,original_assignment_pin))
        if (original_snapshot.get('goal_contract')!=snapshot.get('goal_contract')
                or any(original_snapshot['goal_delivery'].get(k)!=goal.get(k) for k in
                       (*GOAL_IDENTITY,'source_mode','human_authorization','authorization_pin','required_execution_actions'))
                or original_snapshot['goal_delivery']['authorization_pin']!=goal['authorization_pin']
                or original_dispatch['receipt_id']!='42a56fc4-8b45-4443-9f3c-e1b820a35462'
                or original_dispatch not in receipts[:anchors[0][0]]):return False
        pins=dispatch['evidence']; source=_review_source_document(root,pins[0]); prepared=_review_source_document(root,pins[1])
        request_pin={'path':base+'owner-departments-stopped-work-resume-20261021-v1/system-development-resume-prepare-request-v1.json',
            'sha256':'ad7ea51710f0467c9cb3151ccbcf00911d5e4a7a4d097e1df2d1672939e7c1a6','size':1669}
        request=_review_source_document(root,request_pin);registry=w.department_registry(root)
        fixed=registry['system-development']['chat_binding'];hq=registry['operations']['chat_binding']
        from department_rotation import _current_metadata_identity
        original_binding={**fixed,'sidebar_section_id':request['target_sidebar_section_id']}
        if (not _current_metadata_identity(root,'system-development',fixed,original_binding)
                or source.get('task_id')!=task or source.get('role')!='system-development'
                or source.get('actual_sent_payload_sha256')!=request['payload_sha256']
                or request.get('authorization_changes')!=[]or request.get('assignment_record_required')is not False
                or any(request.get(k)!=v for k,v in {'task_id':task,'scope':scope,'sender_department':'operations',
                    'action_id':dispatch['action_id'],'action_class':'thread_message','source_project_id':hq['project_id'],
                    'target_department':'system-development','target_thread_id':fixed['task_id'],'target_thread_title':fixed['title'],
                    'target_project_id':fixed['project_id'],'target_cwd':fixed['cwd']}.items())
                or hq['project_id']!=fixed['project_id']or fixed['cwd']!=str(Path(root).resolve())):return False
        payload=request['payload'];body=w.safe_path(root,payload['path']).read_text()
        if w.file_digest(root,payload['path'])!=payload or request['payload_sha256']!=payload['sha256']:return False
        policy=prepared.get('policy_decision',{});pre=prepared.get('authorization_precheck',{})
        policies=[x for x in w.read_jsonl(Path(root)/w.POLICY_DECISIONS)if x.get('decision_id')==dispatch['policy_decision_id']]
        if (policies != [policy]or prepared.get('status')!='ready_to_send'or prepared.get('payload')!=payload
                or any(policy.get(k)!=v for k,v in {**{k:request[k]for k in ['task_id','scope','action_id','action_class','source_project_id',
                    'target_department','target_thread_id','target_thread_title','target_project_id','target_cwd','target_sidebar_section_id','payload_sha256']},
                    'department':'operations','status':'allow','routing_status':'routing_allowed'}.items())
                or any(pre.get(k)!=v for k,v in {'status':'within_original_authorization','original_authorization':goal['authorization_pin'],
                    'external_permission_issued':False,'actual_action_allowed':False}.items())):return False
        from goal_delivery_runtime import _collaboration_native
        sender=_collaboration_native(root,source['actual_native_sender']);receiver=_collaboration_native(root,source['actual_native_recipient'])
        for page,binding in [(sender,hq),(receiver,fixed)]:
            if any(page.get('thread',{}).get(k)!=binding[v]for k,v in {'id':'task_id','title':'title','cwd':'cwd'}.items()):return False
        calls=[(t,c)for t in sender.get('turns',[])for c in t.get('items',[])if c.get('id')==source.get('native_send_call_id')]
        if len(calls)!=1:return False
        turn,call=calls[0];_review_native_containers(turn);_review_native_containers(call)
        if (turn.get('status')not in {'inProgress','completed'}or call.get('type')!='mcpToolCall'or call.get('server')!='codex_app'
                or call.get('tool')!='send_message_to_thread'or call.get('status')!='completed'
                or call.get('arguments')!={'threadId':fixed['task_id'],'prompt':body}
                or _review_raw_native_result(_review_source_document(root,source['actual_send_return']))!={'threadId':fixed['task_id']}):return False
        turns=[t for t in receiver.get('turns',[])if t.get('id')==source.get('receiver_turn_id')]
        if len(turns)!=1:return False
        received=turns[0];_review_native_containers(received)
        messages=[m for m in received.get('items',[])if m.get('id')==source.get('ack_message_id')]
        if (received.get('status')not in {'inProgress','completed'}or len(messages)!=1
                or messages[0].get('type')!='agentMessage'or not str(messages[0].get('text','')).strip()):return False
        _review_native_containers(messages[0])
        times=[_review_observed_at(row.get('created_at'))for row in [original_dispatch,receipts[anchors[0][0]],dispatch,ack]]
        checked=_review_observed_at(policy.get('checked_at'));started=received.get('startedAt')
        if (not all(times)or times!=sorted(times)or checked is None or not times[1]<=checked<=times[2]<=times[3]<=dt.datetime.now(dt.timezone.utc)
                or type(started)not in {int,float}or not checked.timestamp()<=started<=times[3].timestamp()):return False
        return True
    except (w.WorkflowError,OSError,ValueError,TypeError,KeyError,AttributeError):
        return False


def _same_original_source_notice(root, snapshot, receipts, dispatch, plan, *, source_pins=(), producer=False):
    """Authenticate existing clarification/routine rework without a new round."""
    if producer and _owner_original_producer_HQ_resume(root,snapshot,receipts,dispatch,plan):
        return True
    w = _workflow()
    if not producer and (_modern_original_goal_continuation(root, snapshot, receipts, dispatch, plan) is not None
                         or _hq_original_goal_continuation(root, snapshot, receipts, dispatch, plan) is not None):
        return True
    try:
        goal, registry = _goal(root, snapshot), w.department_registry(root)
        task, reviewer, owner, scope = snapshot["task_id"], plan["reviewer_department"], plan["producer_department"], plan["scope"]
        receiver, sender = (owner, reviewer) if producer else (reviewer, "operations")
        fixed, sender_fixed = [registry[role]["chat_binding"] for role in (receiver, sender)]
        if (goal is None or goal["responsible_assistant"] != reviewer or goal["primary_owner"] != owner
                or goal["producer_departments"] != [owner] or scope not in goal["authorized_scope"]
                or _goal_reviewer(root, snapshot) != reviewer or plan["task_id"] != task
                or dispatch.get("task_id") != task or dispatch.get("department") != receiver
                or dispatch.get("receipt_type") != "dispatch_sent" or dispatch.get("action_class") != "thread_message"
                or dispatch.get("scope") != scope or dispatch.get("chat_task_id") != fixed["task_id"]
                or not dispatch.get("action_id") or dispatch.get("action_id") == "assign-goal-review:" + task
                or any(dispatch.get(key) for key in ("supersedes_receipt_id", "replacement_reason", "approval_id"))
                or any(row.get("supersedes_receipt_id") == dispatch.get("receipt_id") for row in receipts)
                or fixed.get("cwd") != str(Path(root).resolve()) or sender_fixed.get("cwd") != fixed["cwd"]
                or not fixed.get("project_id") or sender_fixed.get("project_id") != fixed["project_id"]):
            return False
        closed = _closed_review_source_pins(root, source_pins)
        if not closed:
            return False
        initial = [row for row in receipts[:receipts.index(dispatch)] if row.get("department") == reviewer
                   and row.get("receipt_type") == "dispatch_sent" and _initial_assignment(root, snapshot, row)]
        if (len(initial) != 1 or not _initial_assignment_wait_envelope(root, snapshot, initial[0], snapshot.get("goal_contract"))):
            return False
        evidence = dispatch.get("evidence", [])
        if producer:
            if len(evidence) != 2:
                return False
            payload, send = evidence
            if payload not in closed or send not in closed or _review_raw_native_result(_review_source_document(root, send)) != {"threadId": fixed["task_id"]}:
                return False
            recorded_at = _review_observed_at(dispatch.get("created_at"))
        else:
            if len(evidence) != 1 or evidence[0] not in closed:
                return False
            send = _review_source_document(root, evidence[0])
            expected = {"schema_version", "task_id", "sender_department", "target_department", "target_thread_id", "action_id",
                        "policy_decision_id", "payload_sha256", "tool_name", "recorded_at", "actual_tool_result",
                        "not_new_ordinary_business_task", "responding_to_pending_permission_clarification", "additional_external_permission"}
            if (set(send) != expected or send.get("schema_version") != 1 or send.get("task_id") != task
                    or send.get("sender_department") != sender or send.get("target_department") != receiver
                    or send.get("target_thread_id") != fixed["task_id"] or send.get("action_id") != dispatch["action_id"]
                    or send.get("policy_decision_id") != dispatch.get("policy_decision_id")
                    or send.get("tool_name") != "mcp__codex_app__send_message_to_thread"
                    or send.get("not_new_ordinary_business_task") is not True
                    or send.get("responding_to_pending_permission_clarification") is not True
                    or send.get("additional_external_permission") is not False
                    or _review_raw_native_result(send["actual_tool_result"]) != {"threadId": fixed["task_id"]}):
                return False
            payloads = [pin for pin in closed if pin["sha256"] == send.get("payload_sha256")
                        and not pin["path"].endswith(".json")]
            if len(payloads) != 1:
                return False
            payload, recorded_at = payloads[0], _review_observed_at(send.get("recorded_at"))
        body = w.safe_path(root, payload["path"]).read_bytes().decode("utf-8")
        from result_coordination import coordinator_roles
        if (not _exact_text_reference(body, task)
                or set(re.findall(r"project:[A-Za-z0-9_:.-]+", body)) - set(goal["authorized_scope"])
                or any(name not in {"operations", reviewer, goal.get("schedule_target_department")}
                       and _exact_text_reference(body, name) for name in coordinator_roles(root))):
            return False
        source = _review_received_input(root, closed, payload, receiver, sender, registry)
        policies = [row for row in w.read_jsonl(root / w.POLICY_DECISIONS) if row.get("decision_id") == dispatch.get("policy_decision_id")]
        expected = {"status": "allow", "routing_status": "routing_allowed", "task_id": task, "department": sender,
                    "action_id": dispatch["action_id"], "action_class": "thread_message", "scope": scope,
                    "payload_sha256": payload["sha256"], "target_department": receiver, "target_thread_id": fixed["task_id"],
                    "target_thread_title": fixed["title"], "target_cwd": fixed["cwd"], "source_project_id": fixed["project_id"],
                    "target_project_id": fixed["project_id"], "target_sidebar_section_id": fixed.get("sidebar_section_id"),
                    "routing_quarantine_mode": False, "routing_health_probe_mode": False}
        if len(policies) != 1 or any(policies[0].get(key) != value for key, value in expected.items()):
            return False
        checked, sent = [_review_observed_at(value) for value in (policies[0].get("checked_at"), dispatch.get("created_at"))]
        if checked is None or sent is None or recorded_at is None or not checked <= recorded_at <= sent <= dt.datetime.now(dt.timezone.utc):
            return False
        authority = _review_source_document(root, goal["authorization_pin"])
        original = authority.get("primary_source_pin", goal["authorization_pin"])
        original_doc = _review_source_document(root, original)
        if (original_doc.get("source_thread_id") != goal["human_authorization"]["source_thread_id"]
                or original_doc.get("message", {}).get("type") != "userMessage"
                or original_doc.get("message", {}).get("id") != goal["human_authorization"]["message_id"]):
            return False
        if not producer:
            return _exact_text_reference(body, original["path"])
        acknowledgements = [row for row in receipts[receipts.index(dispatch) + 1:]
                            if row.get("department") == owner and row.get("receipt_type") == "chat_ack"
                            and row.get("action_id") == dispatch["action_id"]]
        if len(acknowledgements) != 1:
            return False
        ack = acknowledgements[0]
        at = _review_observed_at(ack.get("created_at"))
        if (ack.get("ack_nonempty") is not True or ack.get("chat_task_id") != fixed["task_id"]
                or ack.get("scope") != scope or ack.get("policy_decision_id") != dispatch["policy_decision_id"]
                or any(ack.get(key) for key in ("supersedes_receipt_id", "replacement_reason", "approval_id"))
                or any(row.get("supersedes_receipt_id") == ack.get("receipt_id") for row in receipts)
                or at is None or not sent <= at <= dt.datetime.now(dt.timezone.utc) or len(ack.get("evidence", [])) != 1):
            return False
        native = _review_source_document(root, ack["evidence"][0])
        _review_native_containers(native)
        if "content" in native:
            native = _review_raw_native_result(native)
        elif native.get("schemaVersion") != 1 or set(native) != {"schemaVersion", "thread", "turns"}:
            return False
        if native.get("thread", {}).get("id") != fixed["task_id"]:
            return False
        _review_native_containers(native)
        thread = native.get("thread", {})
        if (any(thread.get(key) != value for key, value in {"kind": "codex", "hostId": "local", "title": fixed["title"],
                "cwd": fixed["cwd"]}.items()) or ("projectId" in thread and thread["projectId"] != fixed["project_id"])):
            return False
        turns = [turn for turn in native.get("turns", []) if turn.get("id") == source["turn"]["id"]]
        if len(turns) != 1:
            return False
        turn = turns[0]
        _review_native_containers(turn)
        if (turn.get("status") not in {"inProgress", "completed"} or type(turn.get("startedAt")) not in {int, float}
                or turn["startedAt"] != source["turn"].get("startedAt")
                or not checked.timestamp() <= turn["startedAt"] <= at.timestamp()):
            return False
        messages = [item for item in turn.get("items", []) if item.get("type") == "agentMessage"
                    and item.get("phase") in {"commentary", "final_answer"} and item.get("id")
                    and isinstance(item.get("text"), str) and item["text"].strip()]
        if len(messages) != 1 or _review_source_failed(messages[0]):
            return False
        _review_native_containers(messages[0])
        import paid_three_page_bounded_cms as b
        from scoped_candidate_adoption import _committed
        decisions = [row for row in w._result_handoff_rows(root, task) if row.get("event") == "controller_decision"
                     and row.get("decision") == "rework" and _exact_text_reference(body, row.get("record_id"))]
        if len(decisions) != 1:
            return False
        decision = decisions[0]
        if (decision.get("coordinator_role") != reviewer or decision.get("decision_actor") != reviewer
                or decision.get("responsible_assistant") != reviewer or decision.get("sender_department") != owner
                or decision.get("next_owner") != owner or decision.get("business_goal_closed") is not False
                or decision.get("qa_status") == "pass" or type(decision.get("coordination_fence")) is not int
                or decision["coordination_fence"] < 1 or not decision.get("coordinator_owner")):
            return False
        _committed(root, decision)
        times = b._v5_source_decision_fence(root, decision, reviewer)
        if times["committed_at"] > checked.timestamp():
            return False
        follows = [row for row in w._result_handoff_rows(root, task) if row.get("event") == "controller_followthrough"
                   and all(row.get(key) == decision.get(key) for key in ("task_id", "sender_department", "candidate_version",
                       "result_sha256", "coordinator_role", "coordinator_owner", "coordination_fence", "decision_actor", "responsible_assistant", "outbox"))
                   and row.get("business_goal_closed") is False and row.get("followthrough_status") == "blocked_with_owner"]
        if len(follows) != 1:
            return False
        follow = follows[0]
        _committed(root, follow)
        decision_at, followed_at = [_review_observed_at(row.get("created_at")) for row in (decision, follow)]
        if decision_at is None or followed_at is None or not decision_at <= followed_at <= checked:
            return False
        result_pin = decision.get("outbox")
        old_boxes = [row for row in receipts[:receipts.index(dispatch)] if row.get("department") == owner
                     and row.get("receipt_type") == "outbox_received" and result_pin in row.get("evidence", [])]
        original_sends = [row for row in receipts[:receipts.index(old_boxes[-1])] if row.get("department") == owner
                          and row.get("receipt_type") in {"dispatch_sent", "dispatch_failed"}] if old_boxes else []
        if len(original_sends) != 1 or original_sends[0].get("receipt_type") != "dispatch_sent":
            return False
        original_send = original_sends[0]
        initial_acks = [row for row in receipts[receipts.index(original_send) + 1:receipts.index(old_boxes[-1])]
                        if row.get("department") == owner and row.get("receipt_type") == "chat_ack"
                        and row.get("ack_nonempty") is True and row.get("action_id") == original_send.get("action_id")]
        original_review_acks = [row for row in receipts[receipts.index(initial[0]) + 1:receipts.index(dispatch)]
                               if row.get("department") == reviewer and row.get("receipt_type") == "chat_ack"
                               and row.get("action_id") == initial[0].get("action_id")]
        if (not initial_acks or not original_review_acks
                or any(row.get("evidence") != original_review_acks[0].get("evidence") for row in initial_acks)):
            return False
        boxes = []
        for pin in decision.get("evidence", []):
            if not pin.get("path", "").endswith(".json"):
                continue
            box = _review_source_document(root, pin)
            proof = box.get("candidate_review", {})
            if not isinstance(proof, dict) or proof.get("verdict") != "BLOCKED_SOURCE_CANDIDATE_ONLY":
                continue
            if (box.get("department") != reviewer or box.get("task_id") != task or box.get("scope") != scope
                    or box.get("candidate_version") != decision.get("candidate_version")
                    or proof.get("actor") != reviewer or proof.get("producer_outbox") != result_pin
                    or proof.get("review_plan") not in [binding["pin"] for binding in _bindings(root, snapshot)]
                    or (proof.get("goal_contract") is not None and proof.get("goal_contract") != snapshot.get("goal_contract"))
                    or any(box.get(key) is not False for key in ("production_write_allowed", "production_release_eligible", "external_permission_issued"))):
                return False
            old_plan = _review_source_document(root, proof["review_plan"])
            old_result = _review_source_document(root, result_pin)
            if (old_plan.get("task_id") != task or old_plan.get("scope") != scope
                    or old_plan.get("producer_department") != owner or old_plan.get("reviewer_department") != reviewer
                    or old_plan.get("reviewer_thread_id") != registry[reviewer]["chat_binding"]["task_id"]
                    or old_plan.get("candidate") != result_pin or old_plan.get("candidate_version") != decision.get("candidate_version")
                    or old_plan.get("candidate_sha256") != decision.get("result_sha256")
                    or not _producer_candidate_bound(root, old_plan, result_pin, old_result)):
                return False
            _review_exact_native_reply(root, box, reviewer, [task, "BLOCKED_SOURCE_CANDIDATE_ONLY"])
            boxes.append(box)
        return len(boxes) == 1
    except (w.WorkflowError, OSError, ValueError, TypeError, KeyError, AttributeError):
        return False


def _qualified_review_box_sources(root, snapshot, binding, plan, pin, verdict, *, require_manifest=False, receipts=()):
    """Authenticate a current reviewer box without creating a verdict receipt."""
    w = _workflow()
    expected = {key: plan[key] for key in IDENTITY}
    box = _review_source_document(root, pin)
    reply = box.get("chat_reply", {})
    if (box.get("schema_version") != "2.0" or box.get("task_id") != plan["task_id"]
            or box.get("department") != plan["reviewer_department"] or box.get("sender_department") != plan["reviewer_department"]
            or box.get("fixed_chat_task_id") != plan["reviewer_thread_id"]
            or box.get("candidate_version") != plan["candidate_version"] or box.get("review_identity") != expected
            or box.get("scope") != plan["scope"] or verdict not in {"pass", "blocked"}
            or box.get("qa_verdict") != verdict or box.get("risk_level") != plan["risk_level"]
            or any(box.get(key) is not False for key in ("production_write_allowed", "production_release_eligible", "external_permission_issued"))
            or reply.get("nonempty") is not True or reply.get("in_current_fixed_department_chat") is not True
            or not reply.get("ref") or not w.SHA256_PATTERN.fullmatch(str(reply.get("sha256", "")))
            or binding["pin"] not in box.get("evidence", []) or plan["candidate"] not in box.get("evidence", [])):
        raise w.WorkflowError("closed source reviewer outbox differs from exact original plan/candidate")
    if not box.get("actual_native_reply"):
        if require_manifest:
            raise w.WorkflowError("received closed-source reviewer native effect required")
        return []
    _review_exact_native_reply(root, box, plan["reviewer_department"])
    pins = list(_evidence_pins(box.get("evidence", [])))
    manifests = []
    for evidence in pins:
        if evidence.get("path", "").endswith(".json"):
            sources = _review_manifest_source_pins(root, snapshot, plan, evidence)
            if sources is not None:
                manifests.append((evidence, sources))
    if len(manifests) > 1 or (require_manifest and len(manifests) != 1):
        raise w.WorkflowError("one exact same-goal closed-source manifest required")
    closed = _closed_review_source_pins(root, pins + (manifests[0][1] if manifests else []))
    original_source_used = manifests and any(
        row.get("receipt_type") == "dispatch_sent"
        and ((row.get("department") == plan["reviewer_department"]
              and _same_original_source_notice(root, snapshot, receipts, row, plan, source_pins=closed))
             or (row.get("department") == plan["producer_department"]
                 and _same_original_source_notice(root, snapshot, receipts, row, plan, source_pins=closed, producer=True)))
        for row in receipts)
    if manifests and (require_manifest or original_source_used):
        _review_exact_native_reply(root, box, plan["reviewer_department"],
            [plan["task_id"], plan["candidate_version"], plan["candidate_sha256"], manifests[0][0]["sha256"], verdict.upper()])
    return closed


def _received_review_source_pins(root, snapshot, receipts, binding, plan):
    """Read missing responsibility sources from one already received current box."""
    w = _workflow()
    persisted = w.read_jsonl(w.receipts_path(root, snapshot["task_id"]))
    if not receipts or persisted[:len(receipts)] != receipts:
        raise w.WorkflowError("closed-source reviewer intake must exist in the actual receipt prefix")
    previous = ""
    seen = set()
    for row in receipts:
        if (row.get("task_id") != snapshot["task_id"] or not row.get("receipt_id") or row["receipt_id"] in seen
                or row.get("previous_hash") != previous
                or row.get("receipt_hash") != w.sha256_value(w._receipt_payload_for_hash(row))):
            raise w.WorkflowError("exact persisted closed-source receipt hash chain required")
        seen.add(row["receipt_id"])
        previous = row["receipt_hash"]
    if (not binding.get("pin") or _review_source_document(root, binding["pin"]) != plan
            or binding.get("reviewer_department") != plan["reviewer_department"]
            or _goal_reviewer(root, snapshot) != plan["reviewer_department"]):
        raise w.WorkflowError("exact current sole-reviewer plan binding required")
    expected = {key: plan[key] for key in IDENTITY}
    matches = []
    for row in receipts:
        if row.get("department") != plan["reviewer_department"] or row.get("receipt_type") != "outbox_received":
            continue
        for pin in row.get("evidence", []):
            if not pin.get("path", "").endswith(".json"):
                continue
            box = _review_source_document(root, pin, object_only=False)
            if not isinstance(box, dict) or box.get("review_identity") != expected:
                continue
            if (box.get("candidate_version") != plan["candidate_version"]
                    or binding["pin"] not in box.get("evidence", []) or plan["candidate"] not in box.get("evidence", [])):
                continue
            received, created = [_review_observed_at(value) for value in (row.get("created_at"), box.get("created_at"))]
            # Existing receipt timestamps truncate fractional seconds; their
            # recorded second is an interval, not the precise send instant.
            second_precision = isinstance(row.get("created_at"), str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+00:00", row["created_at"]) is not None
            ordered = received is not None and created is not None and (
                created < received + dt.timedelta(seconds=1) if second_precision else created <= received)
            if (row.get("chat_task_id") != plan["reviewer_thread_id"] or received is None or created is None
                    or not ordered or received > dt.datetime.now(dt.timezone.utc)
                    or any(item.get("supersedes_receipt_id") == row.get("receipt_id") for item in receipts)):
                raise w.WorkflowError("successful ordered current reviewer outbox intake required")
            matches.append((pin, box))
    if len(matches) != 1:
        raise w.WorkflowError("one already received exact current reviewer box required")
    pin, box = matches[0]
    return _qualified_review_box_sources(root, snapshot, binding, plan, pin, box.get("qa_verdict"), require_manifest=True)


def _verdict_review_source_pins(root, snapshot, receipts, receipt, binding, plan):
    """Bootstrap closed sources only from the exact independently owned box."""
    w = _workflow()
    if _goal(root, snapshot) is None:
        return []
    # Existing single-ACK/candidate/functional notices keep their original
    # validator. Bootstrap this stricter source reader only for a later source
    # which those established paths cannot already authenticate.
    reviewer = plan["reviewer_department"]
    unknown_review = any(row.get("department") == reviewer and row.get("receipt_type") in {"dispatch_sent", "dispatch_failed"}
        and row.get("action_id") != "assign-goal-review:" + snapshot["task_id"]
        and not (binding["pin"] in row.get("evidence", []) and plan["candidate"] in row.get("evidence", []) and row.get("scope") == plan["scope"])
        and not _same_goal_rework_notice(root, snapshot, receipts, row, plan)
        and not _same_goal_functional_result_notice(root, snapshot, receipts, row, plan)
        and not _original_owner_direct_authority_notice(root, snapshot, binding, plan, receipts, row)
        for row in receipts)
    producer_boxes = [i for i, row in enumerate(receipts) if row.get("department") == plan["producer_department"] and row.get("receipt_type") == "outbox_received"]
    later_producer = bool(producer_boxes) and any(i > producer_boxes[-1] and row.get("department") == plan["producer_department"]
        and row.get("receipt_type") in {"dispatch_sent", "dispatch_failed"} for i, row in enumerate(receipts))
    if not unknown_review and not later_producer:
        return []
    own = [row for row in receipts if row.get("department") == plan["reviewer_department"]
           and row.get("receipt_type") == "outbox_received"]
    matches = [(row, pin) for row in own for pin in row.get("evidence", [])
               if pin in receipt.get("evidence", []) and pin.get("path", "").endswith(".json")]
    if len(matches) != 1:
        return []
    row, pin = matches[0]
    return _qualified_review_box_sources(root, snapshot, binding, plan, pin, receipt.get("verdict"), receipts=receipts)


def _saved_original_source_index(root, snapshot, *, plan=None, source_pins=None):
    """A full-pin index supplies original bytes, never dispatch authority.

    An unbound plan may supply the index before first binding. Later readers
    use the same frozen plan; no already-bound plan is a first-bind condition.
    """
    if source_pins is None:
        if plan is None:
            binding = _binding(root, snapshot)
            plan = load_plan(root, snapshot, binding) if binding is not None else None
        source_pins = (plan or {}).get("original_goal_continuation_sources", [])
    if not source_pins:
        return []
    if not isinstance(source_pins, list):
        raise _workflow().WorkflowError("saved original responsibility: typed full-pin source list required")
    return _closed_review_source_pins(root, source_pins)

def _saved_original_native_documents(root, pins):
    """Decode exact provider exports without discarding outer failure flags."""
    result = []
    for pin in pins:
        if not pin["path"].endswith(".json"):
            continue
        value = _review_source_document(root, pin, object_only=False)
        if not isinstance(value, dict):
            continue
        if "content" in value and not value.get("thread"):
            value = _review_raw_native_result(value)
        if isinstance(value.get("thread"), dict) and isinstance(value.get("turns"), list):
            _review_native_containers(value)
            if value.get("schemaVersion") != 1 or any(not isinstance(turn, dict) for turn in value["turns"]):
                raise ValueError("actual complete provider thread export required")
            result.append((pin, value))
    return result

def _saved_original_dispatch_window(root, snapshot, receipts, dispatch, pins, *, initial=False):
    """Authenticate one saved canonical/raw send and its original ACK.

    The old result is tied to the original provider call arguments, immutable
    policy, payload and receiving window. No call timestamp or idle observation
    is invented; the initial schema-1 contract never required pre-send idle.
    """
    w = _workflow()
    def require(value, reason):
        if not value:
            raise w.WorkflowError("saved original responsibility: " + reason)
    goal, registry = _goal(root, snapshot), w.department_registry(root)
    task, role = snapshot["task_id"], goal["responsible_assistant"]
    fixed, hq = [registry[name]["chat_binding"] for name in (role, "operations")]
    require(receipts == _strict_source_rows(root, task), "complete current receipt chain required")
    require(len({row.get("receipt_id") for row in receipts}) == len(receipts), "unique original receipt identities required")
    contract = snapshot["goal_contract"]
    require(_initial_goal_identity(root, snapshot, _review_source_document(root, contract))
            and w.file_digest(root, goal["human_authorization"]["evidence_path"]) == goal["authorization_pin"]
            and fixed["cwd"] == hq["cwd"] == str(Path(root).resolve())
            and fixed["project_id"] == hq["project_id"], "original human, goal and fixed project required")
    require(dispatch.get("task_id") == task and dispatch.get("department") == role
            and dispatch.get("chat_task_id") == fixed["task_id"] and dispatch.get("receipt_type") == "dispatch_sent"
            and dispatch.get("action_class") == "thread_message" and dispatch.get("scope") in goal["authorized_scope"]
            and not any(dispatch.get(key) for key in ("supersedes_receipt_id", "replacement_reason", "approval_id"))
            and not any(row.get("supersedes_receipt_id") == dispatch.get("receipt_id") for row in receipts)
            and len(dispatch.get("evidence", [])) == 1, "exact original dispatch identity required")
    index = receipts.index(dispatch)
    end = next((i for i, row in enumerate(receipts) if i > index and row.get("department") == role
                and row.get("receipt_type") in {"dispatch_sent", "dispatch_failed"}), len(receipts))
    acks = [(i, row) for i, row in enumerate(receipts) if index < i < end
            and row.get("department") == role and row.get("receipt_type") == "chat_ack"]
    require(len(acks) == 1, "one original non-superseded ACK window required")
    ack_index, ack = acks[0]
    require(ack.get("ack_nonempty") is True and ack.get("chat_task_id") == fixed["task_id"]
            and all(ack.get(key) == dispatch.get(key) for key in ("task_id", "action_id", "action_class", "scope"))
            and ack.get("policy_decision_id") in {"", dispatch.get("policy_decision_id")}
            and not any(ack.get(key) for key in ("supersedes_receipt_id", "replacement_reason", "approval_id"))
            and not any(row.get("supersedes_receipt_id") == ack.get("receipt_id") for row in receipts)
            and len(ack.get("evidence", [])) == 1, "original ACK identity cannot be relabelled")
    policies = [row for row in w.read_jsonl(Path(root) / w.POLICY_DECISIONS)
                if row.get("decision_id") == dispatch.get("policy_decision_id")]
    expected = {"status": "allow", "routing_status": "routing_allowed", "department": "operations",
        "task_id": task, "action_id": dispatch["action_id"], "action_class": "thread_message", "scope": dispatch["scope"],
        "target_department": role, "target_thread_id": fixed["task_id"], "target_thread_title": fixed["title"],
        "target_cwd": fixed["cwd"], "target_project_id": fixed["project_id"], "source_project_id": fixed["project_id"],
        "target_sidebar_section_id": fixed["sidebar_section_id"], "approval_id": "",
        "routing_quarantine_mode": False, "routing_health_probe_mode": False}
    require(len(policies) == 1 and all(policies[0].get(key) == value for key, value in expected.items())
            and all(policies[0].get(key) is False for key in ("routing_quarantine_mode", "routing_health_probe_mode")),
            "unique original exact allow policy required")
    policy = policies[0]
    checked, sent, ack_at = [_review_observed_at(value) for value in
                            (policy.get("checked_at"), dispatch.get("created_at"), ack.get("created_at"))]
    now = dt.datetime.now(dt.timezone.utc)
    require(all(value is not None for value in (checked, sent, ack_at)) and checked <= sent <= ack_at <= now,
            "original policy/send/ACK order required")
    send = _review_source_document(root, dispatch["evidence"][0]); _review_native_containers(send)
    if initial:
        expected_send = {"schema_version": "native-dispatch-canonical-v1", "task_id": task,
            "sender_department": "operations", "target_department": role, "target_thread_id": fixed["task_id"],
            "action_id": "assign-goal-review:" + task, "policy_decision_id": dispatch["policy_decision_id"],
            "payload_sha256": contract["sha256"], "tool_name": "mcp__codex_app__send_message_to_thread"}
        require(dispatch["action_id"] == expected_send["action_id"] and {"recorded_at", "actual_tool_result"} <= set(send)
                and set(send) <= set(expected_send) | {"recorded_at", "actual_tool_result", "isError", "truncated", "failed", "superseded"}
                and all(send.get(key) == value for key, value in expected_send.items())
                and policy.get("payload_sha256") == contract["sha256"], "saved initial canonical contract transport required")
        native = _review_raw_native_result(send["actual_tool_result"])
        observed = _review_observed_at(send.get("recorded_at"))
        second_precision = bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+00:00", dispatch["created_at"]))
        before_receipt = (observed < sent + dt.timedelta(seconds=1) if second_precision else observed <= sent) if observed is not None else False
        require(observed is not None and checked <= observed <= now and before_receipt,
                "original canonical observation stays in its receipt precision window")
    else:
        require(set(send) <= {"content", "isError", "structuredContent", "truncated", "failed", "superseded"}
                and dispatch["action_id"] != "assign-goal-review:" + task, "original raw resume response required")
        native = _review_raw_native_result(send)
    require(native == {"threadId": fixed["task_id"]}, "original successful target result required")
    payloads = [pin for pin in [contract, *pins] if pin["sha256"] == policy.get("payload_sha256")]
    unique_payloads = {w.canonical_json(pin): pin for pin in payloads}
    require(len(unique_payloads) == 1, "one existing exact original UTF-8 payload pin required")
    payload = next(iter(unique_payloads.values())); body = w.safe_path(root, payload["path"]).read_bytes().decode("utf-8")
    require(_exact_text_reference(body, task)
            and not (set(re.findall(r"project:[A-Za-z0-9_:.-]+", body)) - set(goal["authorized_scope"]))
            and (initial or _exact_text_reference(body, dispatch["scope"])), "same original task and scope in actual payload required")
    documents = _saved_original_native_documents(root, pins)
    calls = {}
    for _, document in documents:
        thread = document["thread"]
        if thread.get("id") != hq["task_id"]:
            continue
        require(thread.get("kind") == "codex" and thread.get("hostId") == "local"
                and thread.get("title") == hq["title"] and thread.get("cwd") == hq["cwd"]
                and thread.get("projectId", hq["project_id"]) == hq["project_id"], "original HQ provider identity required")
        for turn in document["turns"]:
            for item in turn.get("items", []):
                if (item.get("type") != "mcpToolCall" or item.get("server") != "codex_app"
                        or item.get("tool") != "send_message_to_thread" or item.get("arguments", {}).get("prompt") != body):
                    continue
                _review_native_containers(turn); _review_native_containers(item)
                require(item.get("status") == "completed" and set(item.get("arguments", {})) == {"threadId", "hostId", "prompt"}
                        and item["arguments"]["threadId"] == fixed["task_id"] and item["arguments"]["hostId"] == "local"
                        and turn.get("status") == "completed" and not turn.get("error")
                        and type(turn.get("startedAt")) in {int, float} and type(turn.get("completedAt")) in {int, float}
                        and turn["startedAt"] <= checked.timestamp() <= sent.timestamp() <= turn["completedAt"] <= now.timestamp(),
                        "completed original send call/arguments and truthful turn bounds required")
                key = (turn["id"], item["id"])
                value = (item["arguments"], turn["startedAt"], turn["completedAt"])
                require(key not in calls or calls[key] == value, "conflicting original send observations rejected")
                calls[key] = value
    require(len(calls) == 1, "one original provider send call matching this policy/payload required")
    ack_doc = _review_source_document(root, ack["evidence"][0]); _review_native_containers(ack_doc)
    if initial:
        require(set(ack_doc) <= {"schema_version", "task_id", "department", "fixed_chat_task_id", "new_turn_id",
                    "ack_nonempty", "is_candidate_result", "native_wait_poll", "raw_native_wait", "recorded_at",
                    "isError", "truncated", "failed", "superseded"}
                and {"native_wait_poll", "raw_native_wait"} <= set(ack_doc)
                and ack_doc.get("schema_version") == "native-chat-ack-canonical-v1"
                and ack_doc.get("task_id") == task and ack_doc.get("department") == role
                and ack_doc.get("fixed_chat_task_id") == fixed["task_id"] and ack_doc.get("ack_nonempty") is True
                and ack_doc.get("is_candidate_result") is False, "saved original canonical ACK identity required")
        raw_wait = _review_raw_native_result(ack_doc["raw_native_wait"])
        require(type(raw_wait.get("timedOut")) is bool and "wake" in raw_wait
                and not set(raw_wait) - {"timedOut", "wake", "polls", "errors", "error", "isError", "truncated", "failed", "superseded"},
                "original canonical ACK raw wait shape required")
        polls = [poll for poll in raw_wait.get("polls", []) if poll.get("thread", {}).get("id") == fixed["task_id"]]
        require(len(polls) == 1 and polls[0] == ack_doc.get("native_wait_poll"), "canonical ACK must match its exact original raw poll")
        poll = polls[0]; _review_native_containers(poll)
        turn, message = poll.get("latestTurn", {}), poll.get("latestAssistantMessage", {})
        require(poll.get("schemaVersion") == 1 and isinstance(poll.get("cursor"), str) and poll["cursor"]
                and type(poll.get("revision")) is int and poll["revision"] > 0
                and poll["cursor"].endswith(":" + str(poll["revision"])) and type(poll.get("changed")) is bool
                and poll.get("thread", {}).get("hostId") == "local"
                and poll.get("latestAssistantMessageId") == message.get("id")
                and turn.get("id") == ack_doc.get("new_turn_id") and message.get("turnId") == turn.get("id"),
                "actual original ACK poll/turn/message required")
        ack_observed = _review_observed_at(ack_doc.get("recorded_at"))
        ack_second_precision = bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+00:00", ack["created_at"]))
        ack_before_receipt = (ack_observed < ack_at + dt.timedelta(seconds=1) if ack_second_precision else ack_observed <= ack_at) if ack_observed is not None else False
        require(ack_observed is not None and sent <= ack_observed <= now and ack_before_receipt,
                "original canonical ACK observation stays in its receipt precision window")
    else:
        require(ack_doc.get("schemaVersion") == 1 and ack_doc.get("thread", {}).get("id") == fixed["task_id"],
                "actual saved read_thread ACK required")
        received = {}
        for _, document in documents:
            thread = document["thread"]
            if thread.get("id") != fixed["task_id"]:
                continue
            require(thread.get("kind") == "codex" and thread.get("hostId") == "local"
                    and thread.get("title") == fixed["title"] and thread.get("cwd") == fixed["cwd"]
                    and thread.get("projectId", fixed["project_id"]) == fixed["project_id"], "original receiving provider identity required")
            for turn in document["turns"]:
                for item in turn.get("items", []):
                    if item.get("type") != "functionCallOutput" or item.get("namespace") != "codex_app" or item.get("name") != "send_message_to_thread":
                        continue
                    output = item.get("output", {}); text = output.get("text") if isinstance(output, dict) else output
                    match = re.fullmatch(r"\s*<codex_delegation>\s*<source_thread_id>" + re.escape(hq["task_id"]) +
                        r"</source_thread_id>\s*<input>([\s\S]+)</input>\s*</codex_delegation>\s*", text or "")
                    if not match or match[1].encode("utf-8") != body.encode("utf-8"):
                        continue
                    _review_native_containers(turn); _review_native_containers(item)
                    require(isinstance(output, dict) and output.get("truncated") is False,
                            "complete actual received FCO required")
                    messages = [entry for entry in turn.get("items", []) if entry.get("type") == "agentMessage"
                                and entry.get("phase") in {"commentary", "final_answer"} and isinstance(entry.get("text"), str)
                                and entry["text"].strip() and turn["items"].index(entry) > turn["items"].index(item)]
                    require(messages, "actual first nonempty receiving ACK required")
                    message = messages[0]; _review_native_containers(message)
                    original = [(old_turn, old_message) for old_turn in ack_doc.get("turns", [])
                                for old_message in old_turn.get("items", []) if old_message.get("id") == message["id"]]
                    require(len(original) == 1 and original[0][0].get("id") == turn["id"]
                            and original[0][1].get("text", "").encode("utf-8") == message["text"].encode("utf-8")
                            and original[0][1].get("phase") == message["phase"], "original receipt ACK binds this same received FCO/turn/message")
                    key = (turn["id"], item["id"], message["id"])
                    received[key] = (turn, message)
        require(len(received) == 1, "one actual original receiving FCO and ACK required")
        turn, message = next(iter(received.values()))
        lives = []
        for pin in pins:
            if not pin["path"].endswith(".json"):
                continue
            live = _review_source_document(root, pin, object_only=False)
            if not isinstance(live, dict) or not isinstance(live.get("threads"), list) or not isinstance(live.get("sections"), list):
                continue
            _review_native_containers(live)
            observed = _review_observed_at(live.get("observed_at"))
            if observed is None or not observed <= checked or (checked-observed).total_seconds() > 300:
                continue
            good = True
            for binding in (hq, fixed):
                entries = [entry for entry in live["threads"] if entry.get("id") == binding["task_id"]]
                sections = [section for section in live["sections"] if section.get("sectionId") == binding["sidebar_section_id"]]
                good = good and len(entries) == len(sections) == 1 and all(entries[0].get(key) == binding[field] for key, field in
                    (("title", "title"), ("cwd", "cwd"), ("projectId", "project_id")))
                good = good and "codex:thread:local:" + binding["task_id"] in sections[0].get("itemKeys", [])
                if good:
                    _review_native_containers(entries[0])
                if binding == fixed:
                    good = good and entries[0].get("status") == "idle"
            if good:
                lives.append(pin)
        require(len(lives) == 1, "one original fresh idle/section observation for this resume required")
    require(turn.get("status") in {"inProgress", "completed"} and not turn.get("error")
            and type(turn.get("startedAt")) in {int, float} and checked.timestamp() <= turn["startedAt"] <= ack_at.timestamp()
            and message.get("id") and message.get("phase") in {"commentary", "final_answer"}
            and isinstance(message.get("text"), str) and message["text"].strip(), "ordered actual nonempty original ACK required")
    source_turn_id, source_call_id = next(iter(calls))
    return {"dispatch": dispatch, "dispatch_index": index, "ack": ack, "ack_index": ack_index,
            "source_turn_id": source_turn_id, "source_call_id": source_call_id}

def _saved_initial_assignment_envelope(root, snapshot, dispatch, contract_pin, *, source_pins=None):
    w = _workflow()
    try:
        evidence = dispatch.get("evidence", [])
        if len(evidence) != 1 or _review_source_document(root, evidence[0]).get("schema_version") != "native-dispatch-canonical-v1":
            return False
        pins = _saved_original_source_index(root, snapshot, source_pins=source_pins)
        if not pins or contract_pin != snapshot.get("goal_contract"):
            return False
        _saved_original_dispatch_window(root, snapshot, _strict_source_rows(root, snapshot["task_id"]), dispatch, pins, initial=True)
        return True
    except (w.WorkflowError, OSError, ValueError, TypeError, KeyError, AttributeError):
        return False

def _saved_original_goal_continuation(root, snapshot, receipts, dispatch, plan):
    evidence = dispatch.get("evidence", [])
    # The separately approved 14:23 v2 recovery kept its three original
    # evidence pins. The original truncated v1 read remains rejected; this
    # path needs the exact later one-case native source-composition authority.
    if (dispatch.get("receipt_id") == "eed3be33-a17c-46a8-8842-9c79d449d21a"
            and len(evidence) == 3):
        pins = _saved_original_source_index(root, snapshot, plan=plan)
        if not pins:
            raise _workflow().WorkflowError("approved original 14:23 responsibility sources required")
        return _saved_original_dispatch_window(root, snapshot, receipts, dispatch, pins)
    if len(evidence) != 1:
        return None
    source = _review_source_document(root, evidence[0])
    if "content" not in source or source.get("thread"):
        return None
    pins = _saved_original_source_index(root, snapshot, plan=plan)
    if not pins:
        raise _workflow().WorkflowError("saved original responsibility: recognized raw send requires exact closed native sources")
    return _saved_original_dispatch_window(root, snapshot, receipts, dispatch, pins)


def _review_same_goal_send_wrapper(value):
    """Decode the two real transport wrappers without changing pinned bytes.

    Normalization is representation only. Callers must still authenticate the
    original policy, payload, actual native call and receiving ACK.
    """
    _review_native_containers(value)
    typed = {"actual_tool", "thread_id", "raw_tool_return", "exact_consumed_prompt"}
    legacy = {"actual_thread_id", "raw_tool_return", "exact_consumed_prompt"}
    if set(value) == typed:
        tool, target = value["actual_tool"], value["thread_id"]
    elif set(value) == legacy:
        tool, target = "mcp__codex_app__send_message_to_thread", value["actual_thread_id"]
    else:
        raise ValueError("known complete same-goal native send wrapper required")
    payload = value["exact_consumed_prompt"]
    if (tool not in {"send_message_to_thread", "mcp__codex_app__send_message_to_thread"}
            or not isinstance(target, str) or not target.strip()
            or not isinstance(payload, dict) or set(payload) != {"path", "sha256", "size"}
            or not isinstance(payload["path"], str) or not payload["path"]
            or not isinstance(payload["sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", payload["sha256"])
            or type(payload["size"]) is not int or payload["size"] <= 0
            or _review_raw_native_result(value["raw_tool_return"]) != {"threadId": target}):
        raise ValueError("exact successful native target and UTF-8 payload identity required")
    return {"actual_tool": tool, "thread_id": target,
            "raw_tool_return": value["raw_tool_return"], "exact_consumed_prompt": payload}


def _same_goal_hq_native_continuation(root, snapshot, receipts, dispatch, plan):
    """Read a normal HQ continuation from receipt-bound native 5+3 sources.

    Receipt IDs, candidate versions, and dates are deliberately absent from
    selection. A new continuation needs its own successful source shapes,
    original goal, exact routing policy, native transport, and nonempty ACK.
    """
    import html
    w = _workflow()
    evidence = dispatch.get("evidence", [])
    if (not isinstance(evidence, list) or len(evidence) != 5
            or not isinstance(evidence[0], dict) or not evidence[0].get("path", "").endswith(".txt")
            or not all(isinstance(pin, dict) and pin.get("path", "").endswith(".json") for pin in evidence[1:])):
        return None
    root = Path(root).resolve()
    def require(value, reason):
        if not value:
            raise w.WorkflowError("same-goal HQ native continuation: " + reason)
    def unique(pairs):
        value = {}
        for key, item in pairs:
            require(key not in value, "ambiguous nested native or command field rejected")
            value[key] = item
        return value
    def native_json(value):
        return json.loads(value, object_pairs_hook=unique,
                          parse_constant=lambda item: (_ for _ in ()).throw(ValueError("finite native JSON required")))
    require(len({pin["path"] for pin in evidence}) == 5
            and all(w.file_digest(root, pin["path"]) == pin for pin in evidence),
            "five exact receipt-bound source pins required")
    policy_return, send, live, producer_read = [
        _review_source_document(root, pin) for pin in evidence[1:]]
    # Only the typed native route enters this reader; an unknown five-source
    # notice must continue to the existing narrow readers.
    typed_send = set(send) == {"actual_tool", "thread_id", "raw_tool_return", "exact_consumed_prompt"}
    legacy_send = set(send) == {"actual_thread_id", "raw_tool_return", "exact_consumed_prompt"}
    if (set(policy_return) != {"exit_code", "stdout", "stderr"}
            or not (typed_send or legacy_send)
            or not isinstance(live.get("threads"), list) or not isinstance(live.get("sections"), list)):
        return None
    # Read the immutable legacy wrapper without rewriting its source or hash.
    # The actual sender session below still proves the tool, arguments, payload,
    # target and successful raw result. Field normalization grants no authority.
    send = _review_same_goal_send_wrapper(send)
    _review_raw_native_result(producer_read)
    require(receipts == _strict_source_rows(root, snapshot["task_id"])
            and len([row for row in receipts if row == dispatch]) == 1
            and len({row.get("receipt_id") for row in receipts}) == len(receipts),
            "complete current unambiguous receipt chain required")
    goal, registry = _goal(root, snapshot), w.department_registry(root)
    task = snapshot["task_id"]
    role, owner = plan.get("reviewer_department"), plan.get("producer_department")
    require(goal is not None and role == goal.get("responsible_assistant")
            and owner == goal.get("primary_owner") and goal.get("producer_departments") == [owner]
            and role != owner and _goal_reviewer(root, snapshot) == role
            and plan.get("task_id") == task and plan.get("scope") in goal.get("authorized_scope", [])
            and role in registry and owner in registry and "operations" in registry,
            "unchanged original goal and independent reviewer required")
    fixed, hq, producer = [registry[name]["chat_binding"] for name in (role, "operations", owner)]
    require(plan.get("reviewer_thread_id") == fixed["task_id"]
            and all(binding.get("cwd") == str(root) and binding.get("project_id") == fixed["project_id"]
                    for binding in (fixed, hq, producer))
            and _initial_goal_identity(root, snapshot,
                _review_source_document(root, snapshot["goal_contract"]))
            and w.file_digest(root, goal["human_authorization"]["evidence_path"]) == goal["authorization_pin"],
            "original human authority, complete goal and fixed project required")
    require(dispatch.get("task_id") == task and dispatch.get("department") == role
            and dispatch.get("receipt_type") == "dispatch_sent"
            and dispatch.get("action_class") == "thread_message"
            and dispatch.get("scope") == plan["scope"]
            and dispatch.get("chat_task_id") == fixed["task_id"]
            and dispatch.get("action_id") != "assign-goal-review:" + task
            and not any(dispatch.get(key) for key in
                        ("supersedes_receipt_id", "replacement_reason", "approval_id"))
            and not any(row.get("supersedes_receipt_id") == dispatch["receipt_id"] for row in receipts),
            "successful unsuperseded original-scope HQ dispatch required")
    index = receipts.index(dispatch)
    end = next((i for i, row in enumerate(receipts) if i > index and row.get("department") == role
                and row.get("receipt_type") in {"dispatch_sent", "dispatch_failed"}), len(receipts))
    acks = [(i, row) for i, row in enumerate(receipts) if index < i < end
            and row.get("department") == role and row.get("receipt_type") == "chat_ack"]
    require(len(acks) == 1, "one actual ACK in this original dispatch window required")
    ack_index, ack = acks[0]
    ack_pins = ack.get("evidence", [])
    require(isinstance(ack_pins, list) and len(ack_pins) == 3
            and len({pin.get("path") for pin in ack_pins if isinstance(pin, dict)}) == 3
            and all(isinstance(pin, dict) and w.file_digest(root, pin["path"]) == pin for pin in ack_pins)
            and ack_pins[0]["path"].endswith(".json") and ack_pins[1]["path"].endswith(".txt")
            and ack_pins[2]["path"].endswith(".json")
            and ack.get("ack_nonempty") is True
            and all(ack.get(key) == dispatch.get(key) for key in
                    ("task_id", "department", "action_id", "action_class", "scope",
                     "policy_decision_id", "chat_task_id"))
            and not any(ack.get(key) for key in
                        ("supersedes_receipt_id", "replacement_reason", "approval_id"))
            and not any(row.get("supersedes_receipt_id") == ack["receipt_id"] for row in receipts),
            "one nonempty unsuperseded matched native ACK required")
    body = w.safe_path(root, evidence[0]["path"]).read_bytes().decode("utf-8")
    ack_text = w.safe_path(root, ack_pins[1]["path"]).read_bytes().decode("utf-8")
    require(body.strip() and ack_text.strip() and _exact_text_reference(body, task)
            and _exact_text_reference(body, plan["scope"])
            and not (set(re.findall(r"project:[A-Za-z0-9_:.-]+", body))
                     - set(goal["authorized_scope"])),
            "nonempty same-goal/scope UTF-8 payload without other project authority required")
    from result_coordination import coordinator_roles
    require(not any(name not in {"operations", role, owner, goal.get("schedule_target_department")}
                    and _exact_text_reference(body, name) for name in coordinator_roles(root)),
            "HQ payload cannot transfer the sole independent reviewer")
    require(policy_return.get("exit_code") == 0 and policy_return.get("stderr") == ""
            and isinstance(policy_return.get("stdout"), str),
            "actual successful policy command output required")
    try:
        returned_policy = native_json(policy_return["stdout"])
    except (TypeError, ValueError) as exc:
        raise w.WorkflowError("same-goal HQ native continuation: malformed policy return") from exc
    policies = [row for row in w.read_jsonl(root / w.POLICY_DECISIONS)
                if row.get("decision_id") == dispatch.get("policy_decision_id")]
    require(len(policies) == 1 and returned_policy.get("decision_id") == dispatch["policy_decision_id"]
            and returned_policy.get("status") == "allow"
            and returned_policy.get("routing_status") == "routing_allowed", "actual exact ALLOW return required")
    policy = policies[0]
    expected_policy = {"status": "allow", "routing_status": "routing_allowed",
        "task_id": task, "department": "operations", "action_id": dispatch["action_id"],
        "action_class": "thread_message", "scope": plan["scope"],
        "target_department": role, "target_thread_id": fixed["task_id"],
        "target_thread_title": fixed["title"], "target_cwd": fixed["cwd"],
        "target_sidebar_section_id": fixed["sidebar_section_id"],
        "target_project_id": fixed["project_id"], "source_project_id": fixed["project_id"],
        "payload_sha256": evidence[0]["sha256"], "approval_id": "",
        "routing_quarantine_mode": False, "routing_health_probe_mode": False}
    require(all(policy.get(key) == value for key, value in expected_policy.items())
            and all(returned_policy.get(key) == value for key, value in expected_policy.items()
                    if key in returned_policy)
            and returned_policy.get("decision_id") == policy.get("decision_id")
            and returned_policy.get("checked_at") == policy.get("checked_at")
            and policy.get("routing_quarantine_mode") is False
            and policy.get("routing_health_probe_mode") is False,
            "ledger and returned policy must allow this one HQ route")
    checked, sent, ack_at = [_review_observed_at(value) for value in
                             (policy.get("checked_at"), dispatch.get("created_at"), ack.get("created_at"))]
    now = dt.datetime.now(dt.timezone.utc)
    require(all(value is not None for value in (checked, sent, ack_at))
            and checked <= sent <= ack_at <= now,
            "policy, dispatch receipt and ACK receipt order required")
    _review_native_containers(send["raw_tool_return"])
    require(send["actual_tool"] in {"send_message_to_thread", "mcp__codex_app__send_message_to_thread"}
            and send["thread_id"] == fixed["task_id"]
            and send["exact_consumed_prompt"] == evidence[0]
            and _review_raw_native_result(send["raw_tool_return"]) == {"threadId": fixed["task_id"]},
            "native send result and exact consumed prompt required")
    _review_native_containers(live)
    require(live.get("schemaVersion") in {3, 4}
            and live.get("unavailableHosts") == [] and live.get("unavailableSources") == [],
            "complete original live list required")
    for binding, status in ((hq, "active"), (fixed, "idle")):
        entries = [entry for entry in live["threads"] if entry.get("id") == binding["task_id"]]
        sections = [section for section in live["sections"] if section.get("sectionId") == binding["sidebar_section_id"]]
        require(len(entries) == len(sections) == 1
                and all(entries[0].get(key) == value for key, value in
                        {"kind": "codex", "hostId": "local", "title": binding["title"],
                         "cwd": binding["cwd"], "projectId": binding["project_id"],
                         "status": status}.items())
                and "codex:thread:local:" + binding["task_id"] in sections[0].get("itemKeys", [])
                and len(sections[0].get("itemKeys", [])) == len(set(sections[0].get("itemKeys", []))),
                "original fixed chats, status and sidebar identities required")
    _review_native_containers(producer_read)
    original_producer = _review_raw_native_result(producer_read)
    producer_thread = original_producer.get("thread", {})
    require(original_producer.get("schemaVersion") == 1
            and all(producer_thread.get(key) == value for key, value in
                    {"id": producer["task_id"], "kind": "codex", "hostId": "local",
                     "title": producer["title"], "cwd": producer["cwd"]}.items())
            and producer_thread.get("projectId", producer["project_id"]) == producer["project_id"]
            and isinstance(original_producer.get("turns"), list),
            "complete fixed producer native read required")
    completed = [turn for turn in original_producer["turns"] if turn.get("status") == "completed"
                 and not turn.get("error") and type(turn.get("completedAt")) in {int, float}
                 and turn["completedAt"] <= checked.timestamp()
                 and any(item.get("type") == "agentMessage" and item.get("phase") == "final_answer"
                         and isinstance(item.get("text"), str) and item["text"].strip()
                         for item in turn.get("items", []))]
    require(len(completed) == 1, "one completed original producer final before HQ continuation required")
    finals = [item for item in completed[0]["items"] if item.get("type") == "agentMessage"
              and item.get("phase") == "final_answer" and isinstance(item.get("text"), str)
              and item["text"].strip()]
    require(len(finals) == 1 and _exact_text_reference(body, producer["task_id"])
            and _exact_text_reference(body, completed[0]["id"])
            and _exact_text_reference(body, finals[0]["id"]),
            "HQ continuation must name its exact completed producer turn and final")
    wait = _review_source_document(root, ack_pins[0]); _review_native_containers(wait)
    require(set(wait) == {"timedOut", "wake", "polls"} and wait["timedOut"] is True
            and wait["wake"] is None and isinstance(wait["polls"], list) and len(wait["polls"]) == 1,
            "complete original wait result required")
    poll = wait["polls"][0]; _review_native_containers(poll)
    turn, message = poll.get("latestTurn", {}), poll.get("latestAssistantMessage", {})
    require(poll.get("schemaVersion") == 1 and poll.get("thread", {}).get("id") == fixed["task_id"]
            and poll["thread"].get("hostId") == "local"
            and poll.get("latestAssistantMessageId") == message.get("id")
            and turn.get("id") == message.get("turnId")
            and turn.get("status") in {"inProgress", "completed"} and not turn.get("error")
            and message.get("phase") in {"commentary", "final_answer"}
            and message.get("text") == ack_text and type(turn.get("startedAt")) in {int, float}
            and checked.timestamp() <= turn["startedAt"] <= ack_at.timestamp(),
            "actual same-turn native nonempty ACK required")
    receipt_return = _review_source_document(root, ack_pins[2])
    require(set(receipt_return) == {"exit_code", "stdout", "stderr"}
            and receipt_return["exit_code"] == 0 and receipt_return["stderr"] == "",
            "actual dispatch receipt command return required")
    try:
        recorded_dispatch = native_json(receipt_return["stdout"])
    except (TypeError, ValueError) as exc:
        raise w.WorkflowError("same-goal HQ native continuation: malformed dispatch return") from exc
    require(recorded_dispatch.get("receipt_id") == dispatch["receipt_id"]
            and recorded_dispatch.get("task_id") == task
            and recorded_dispatch.get("department") == role
            and recorded_dispatch.get("result") == "recorded"
            and recorded_dispatch.get("status") == "complete",
            "actual recorded dispatch return must identify this receipt")
    # The provider's append-only sessions retain the exact send, delivered FCO,
    # and first A2 reply. Locate by fixed chat IDs and equal native bytes, not
    # by a particular date, receipt ID or candidate version.
    sessions = Path.home() / ".codex" / "sessions"
    def session_for(binding):
        choices = list(sessions.rglob("*" + binding["task_id"] + "*.jsonl"))
        require(bool(choices) and all(file.is_file() and not file.is_symlink()
                and file.resolve().is_relative_to(sessions.resolve()) for file in choices),
                "actual fixed-chat native sessions required")
        return choices
    def session_events(files, marker):
        result = []
        for file in files:
            with file.open("rb") as stream:
                for line in stream:
                    if marker not in line:
                        continue
                    require(line.endswith(b"\n"), "complete native session line required")
                    event = native_json(line)
                    if event.get("type") == "event_msg" and event.get("payload", {}).get("type") == "item_completed":
                        result.append(event["payload"])
        return result
    sender_events = session_events(session_for(hq), b'"send_message_to_thread"')
    sends = [event for event in sender_events if event.get("thread_id") == hq["task_id"]
             and event.get("item", {}).get("type") == "McpToolCall"
             and event["item"].get("server") == "codex_app"
             and event["item"].get("tool") == "send_message_to_thread"
             and event["item"].get("pluginId") == "codex-app-tools@openai-bundled"
             and event["item"].get("status") == "completed"
             and event["item"].get("arguments") ==
                 {"threadId": fixed["task_id"], "hostId": "local", "prompt": body}
             and event["item"].get("result") == send["raw_tool_return"]]
    require(len(sends) == 1, "one actual original HQ native send with exact arguments/result required")
    actual_send = sends[0]
    list_events = session_events(session_for(hq), b'"list_threads"')
    lists = []
    for event in list_events:
        item = event.get("item", {})
        if (event.get("thread_id") != hq["task_id"] or item.get("type") != "McpToolCall"
                or item.get("server") != "codex_app" or item.get("tool") != "list_threads"
                or item.get("status") != "completed"):
            continue
        try:
            observed = _review_raw_native_result(item.get("result"))
        except (TypeError, ValueError, KeyError):
            continue
        if observed == live:
            lists.append(event)
    require(len(lists) == 1, "one exact original provider list matching receipt source required")
    listed = lists[0]
    producer_reads = []
    for event in session_events(session_for(hq), b'"read_thread"'):
        item = event.get("item", {})
        if (event.get("thread_id") != hq["task_id"] or item.get("type") != "McpToolCall"
                or item.get("server") != "codex_app" or item.get("tool") != "read_thread"
                or item.get("status") != "completed"
                or item.get("arguments", {}).get("threadId") != producer["task_id"]
                or item["arguments"].get("hostId") != "local"):
            continue
        try:
            observed = _review_raw_native_result(item.get("result"))
            if "content" in observed and "thread" not in observed:
                observed = _review_raw_native_result(observed)
        except (TypeError, ValueError, KeyError):
            continue
        if (observed.get("thread", {}).get("id") != producer["task_id"]
                or observed.get("schemaVersion") != 1):
            continue
        matches = [turn for turn in observed.get("turns", []) if turn.get("id") == completed[0]["id"]
                   and turn.get("status") == "completed" and not turn.get("error")
                   and turn.get("completedAt") == completed[0]["completedAt"]
                   and any(message.get("id") == finals[0]["id"]
                           and message.get("text") == finals[0]["text"]
                           and message.get("phase") == "final_answer"
                           for message in turn.get("items", []))]
        if len(matches) == 1:
            producer_reads.append(event)
    require(len(producer_reads) == 1,
            "one actual HQ native read of the same completed producer final required")
    receiver_events = session_events(session_for(fixed), b'"FunctionCallOutput"')
    delivered = []
    for event in receiver_events:
        item = event.get("item", {})
        if (event.get("thread_id") != fixed["task_id"] or event.get("turn_id") != turn["id"]
                or item.get("type") != "FunctionCallOutput" or item.get("namespace") != "codex_app"
                or item.get("name") != "send_message_to_thread"):
            continue
        output = item.get("output")
        _review_native_containers(item)
        match = re.fullmatch(r"\s*<codex_delegation>\s*<source_thread_id>([^<]+)</source_thread_id>\s*"
                             r"<input>([\s\S]+)</input>\s*</codex_delegation>\s*", output or "")
        if match and match[1] == hq["task_id"] and html.unescape(match[2]) == body:
            delivered.append(event)
    require(len(delivered) == 1, "one untruncated exact delivered HQ payload in A2 native turn required")
    fco = delivered[0]
    reply_events = session_events(session_for(fixed), b'"AgentMessage"')
    messages_after_fco = [event for event in reply_events if event.get("thread_id") == fixed["task_id"]
                          and event.get("turn_id") == turn["id"]
                          and event.get("item", {}).get("type") == "AgentMessage"
                          and event["item"].get("phase") in {"commentary", "final_answer"}
                          and type(event.get("started_at_ms")) is int
                          and type(fco.get("completed_at_ms")) is int
                          and event["started_at_ms"] >= fco["completed_at_ms"]
                          and any(block.get("type") == "Text" and isinstance(block.get("text"), str)
                                  and block["text"].strip() for block in event["item"].get("content", []))]
    require(bool(messages_after_fco), "actual first A2 native reply required")
    first_reply = min(messages_after_fco, key=lambda event: event["started_at_ms"])
    replies = [event for event in reply_events if event.get("thread_id") == fixed["task_id"]
               and event.get("turn_id") == turn["id"]
               and event.get("item", {}).get("type") == "AgentMessage"
               and event["item"].get("id") == message["id"]
               and event["item"].get("phase") == message["phase"]
               and event["item"].get("content") == [{"type": "Text", "text": ack_text + "\n"}]]
    require(len(replies) == 1 and replies[0] == first_reply,
            "one actual first A2 reply equal to ACK UTF-8 required")
    reply = replies[0]
    send_start, send_done = actual_send.get("started_at_ms"), actual_send.get("completed_at_ms")
    list_done, read_done, fco_done = (listed.get("completed_at_ms"),
                                    producer_reads[0].get("completed_at_ms"), fco.get("completed_at_ms"))
    reply_start, reply_done = reply.get("started_at_ms"), reply.get("completed_at_ms")
    require(all(type(value) is int for value in
                (send_start, send_done, list_done, read_done, fco_done, reply_start, reply_done))
            and checked.timestamp() * 1000 <= send_start <= fco_done
            and send_start - checked.timestamp() * 1000 <= 300000
            and send_start <= send_done <= sent.timestamp() * 1000
            and fco_done <= sent.timestamp() * 1000 <= reply_start <= reply_done
            and reply_done <= ack_at.timestamp() * 1000
            and list_done <= send_start and 0 <= send_start - list_done <= 300000
            and completed[0]["completedAt"] * 1000 <= read_done <= send_start
            and turn["startedAt"] * 1000 <= fco_done,
            "actual fresh live list, native send/FCO, receipt and first reply order required")
    return {"dispatch": dispatch, "dispatch_index": index, "ack": ack, "ack_index": ack_index,
            "source_turn_id": actual_send["turn_id"], "source_call_id": actual_send["item"]["id"]}


def _actual_original_hq_20261013_notice(root, snapshot, receipts, dispatch, plan):
    """Read one later HQ/A2 dispatch from its exact six receipt-bound sources."""
    if dispatch.get("receipt_id") != "9942f756-c6ca-432f-be3f-f0e5c4c0bff5":
        return None
    w = _workflow()
    root = Path(root).resolve()
    task = "fc-20261011-goal-publication-notice-followthrough-repair-v1"
    scope = "project:flashcast:goal-publication-notice-followthrough-repair:v1"
    action = "HQ-original-system-operational-metadata-notice-whole-goal-continuation-20261013-1404"
    prefix = "logs/handoffs/2026-10-11-goal-publication-notice-followthrough-repair-v1/HQ-continuation-20261013-1404/"
    def frozen(name, sha, size):
        return {"path": prefix + name, "sha256": sha, "size": size}
    send_pins = [
        frozen("A2-original-complete-system-repair-actual-native-send.json", "bc2d9931f2d78c80c1925f4698fbddacba0a1a2ad31b494ba0f2b3aed3dfc0f2", 5749),
        frozen("A2-original-whole-system-final-repair-task.txt", "2733fd495f39a73105558d7d3e641002e3a49db649f2fccdf3f229f0dd17e5d3", 5077),
        frozen("HQ-local-system-metadata-and-notice-repair-decision.json", "17c1fb1865367db500358e2aa9512e5af447d03feb1c394be2feabf2a6aee441", 2117),
        frozen("ROOT-ACTUAL-human-continue-department-system-repair.json", "1d428a6a4784bda6da5391f082df1c59954d2ea4cb983f0e8d8365280e2f2ba3", 1871),
    ]
    ack_pins = [
        frozen("A2-original-whole-repair-new-real-ACK-native.json", "44d5464c8be061060c2e7bfafa1bd73b7f74f8209e3db25088d47b900d7b20d0", 1271),
        frozen("A2-original-whole-repair-exact-new-ACK-UTF8.txt", "0a97ba837bcbd4201397538333141cc32ae95a9f67cff84b97663547d17e790b", 271),
    ]
    def require(value, reason):
        if not value:
            raise w.WorkflowError("original HQ/A2 responsibility: " + reason)
    goal = _goal(root, snapshot)
    registry = w.department_registry(root)
    role, owner = "operations-assistant-2", "system-development"
    fixed, hq, producer = [registry[name]["chat_binding"] for name in (role, "operations", owner)]
    require(snapshot.get("task_id") == task and goal is not None
        and goal.get("responsible_assistant") == role and goal.get("primary_owner") == owner
        and goal.get("producer_departments") == [owner] and scope in goal.get("authorized_scope", [])
        and plan.get("task_id") == task and plan.get("scope") == scope
        and plan.get("reviewer_department") == role and plan.get("producer_department") == owner
        and plan.get("reviewer_thread_id") == fixed["task_id"]
        and all(value.get("cwd") == str(root) and value.get("project_id") == fixed["project_id"]
            for value in (fixed, hq, producer)), "unchanged original goal and fixed chat identities required")
    require(receipts == _strict_source_rows(root, task) and len([row for row in receipts if row == dispatch]) == 1
        and dispatch.get("evidence") == send_pins and dispatch.get("receipt_type") == "dispatch_sent"
        and dispatch.get("department") == role and dispatch.get("task_id") == task
        and dispatch.get("scope") == scope and dispatch.get("action_id") == action
        and dispatch.get("action_class") == "thread_message" and dispatch.get("chat_task_id") == fixed["task_id"]
        and not any(dispatch.get(key) for key in ("supersedes_receipt_id", "replacement_reason", "approval_id"))
        and not any(row.get("supersedes_receipt_id") == dispatch["receipt_id"] for row in receipts),
        "complete actual dispatch ledger, evidence and actor required")
    index = receipts.index(dispatch)
    next_send = next((i for i, row in enumerate(receipts) if i > index and row.get("department") == role
        and row.get("receipt_type") in {"dispatch_sent", "dispatch_failed"}), len(receipts))
    acks = [row for row in receipts[index + 1:next_send] if row.get("department") == role
        and row.get("receipt_type") == "chat_ack"]
    require(len(acks) == 1 and acks[0].get("receipt_id") == "875d97ac-0c08-4e2a-9931-f303c997e957"
        and acks[0].get("evidence") == ack_pins and acks[0].get("ack_nonempty") is True
        and all(acks[0].get(key) == dispatch.get(key) for key in
            ("task_id", "department", "action_id", "action_class", "scope", "policy_decision_id", "chat_task_id"))
        and not any(acks[0].get(key) for key in ("supersedes_receipt_id", "replacement_reason", "approval_id"))
        and not any(row.get("supersedes_receipt_id") == acks[0]["receipt_id"] for row in receipts),
        "one real nonempty unsuperseded matching A2 ACK required")
    for source in [*send_pins, *ack_pins]:
        require(w.file_digest(root, source["path"]) == source, "frozen historical source changed")
    send, decision, human, wait = [_review_source_document(root, value) for value in
        (send_pins[0], send_pins[2], send_pins[3], ack_pins[0])]
    body = w.safe_path(root, send_pins[1]["path"]).read_text(encoding="utf-8")
    ack_text = w.safe_path(root, ack_pins[1]["path"]).read_text(encoding="utf-8")
    require(set(send) == {"source_tool", "native_return", "actual_arguments", "prompt_pin"}
        and send["source_tool"] == "mcp__codex_app__send_message_to_thread"
        and send["prompt_pin"] == send_pins[1]
        and send["actual_arguments"] == {"threadId": fixed["task_id"], "hostId": "local", "prompt": body}
        and _review_raw_native_result(send["native_return"]) == {"threadId": fixed["task_id"]}
        and _exact_text_reference(body, task) and _exact_text_reference(body, scope)
        and _exact_text_reference(body, decision["human_current_instruction"]["path"])
        and _exact_text_reference(body, send_pins[2]["path"]),
        "actual native send and exact scoped UTF-8 payload required")
    require(decision.get("schema_version") == "flashcast-HQ-local-system-repair-decision/v1"
        and decision.get("task_id") == task and decision.get("scope") == scope
        and decision.get("decision_actor") == "operations" and decision.get("producer") == owner
        and decision.get("sole_independent_acceptor") == role
        and decision.get("human_current_instruction") == send_pins[3]
        and decision.get("new_external_permissions") is False
        and decision.get("external_write_allowed") is False
        and decision.get("no_push_or_deploy") is True
        and human.get("source_tool") == "mcp__codex_app__read_thread"
        and human.get("thread", {}).get("id") == hq["task_id"]
        and human["thread"].get("cwd") == str(root)
        and human.get("current_turn", {}).get("status") == "inProgress"
        and human["current_turn"]["items"] == [{"type": "userMessage",
            "id": "example-native-8bc5cf513a31ed9f",
            "content": [{"type": "text", "text": "继续修复\n"}]}],
        "real human continuation, HQ decision and unchanged authority scope required")
    policies = [row for row in w.read_jsonl(root / w.POLICY_DECISIONS)
        if row.get("decision_id") == dispatch.get("policy_decision_id")]
    require(len(policies) == 1 and all(policies[0].get(key) == value for key, value in {
        "task_id": task, "department": "operations", "status": "allow", "routing_status": "routing_allowed",
        "action_id": action, "action_class": "thread_message", "scope": scope,
        "target_department": role, "target_thread_id": fixed["task_id"],
        "target_thread_title": fixed["title"], "target_cwd": str(root),
        "source_project_id": fixed["project_id"], "target_project_id": fixed["project_id"],
        "payload_sha256": send_pins[1]["sha256"], "routing_quarantine_mode": False,
        "routing_health_probe_mode": False}.items()),
        "one actual same-scope ALLOW policy and exact payload required")
    checked, sent, ack_at = [_review_observed_at(value) for value in
        (policies[0].get("checked_at"), dispatch.get("created_at"), acks[0].get("created_at"))]
    require(all(value is not None for value in (checked, sent, ack_at))
        and checked <= sent <= ack_at <= dt.datetime.now(dt.timezone.utc),
        "policy, native send and actual ACK time order required")
    _review_native_containers(wait)
    require(set(wait) == {"timedOut", "wake", "polls"} and wait["timedOut"] is True
        and wait["wake"] is None and isinstance(wait["polls"], list) and len(wait["polls"]) == 1,
        "complete original wait result required")
    poll = wait["polls"][0]
    turn, message = poll.get("latestTurn", {}), poll.get("latestAssistantMessage", {})
    require(poll.get("schemaVersion") == 1 and poll.get("thread", {}).get("id") == fixed["task_id"]
        and poll["thread"].get("hostId") == "local"
        and poll.get("latestAssistantMessageId") == message.get("id")
        and turn.get("id") == message.get("turnId")
        and turn.get("status") in {"inProgress", "completed"} and not turn.get("error")
        and message.get("phase") in {"commentary", "final_answer"}
        and isinstance(message.get("text"), str) and message["text"] == ack_text
        and bool(ack_text.strip()) and type(turn.get("startedAt")) in {int, float}
        and checked.timestamp() <= turn["startedAt"] <= sent.timestamp() <= ack_at.timestamp(),
        "actual same-turn native ACK text and time required")
    # The dispatch receipt was recorded after the A2 commentary appeared.
    # Authenticate the native send, the complete receiving FCO, and that exact
    # commentary in their original append-only sessions to establish order.
    import html
    sessions = Path.home() / ".codex/sessions"
    hq_session = sessions / "2026/10/06/rollout-2026-10-06T00-58-55-example-native-0d0689f4e3a4c895_example-native-9d841697a48914a9.jsonl"
    a2_session = sessions / "2026/10/08/rollout-2026-10-08T05-34-43-example-native-2ab501c514875e3b.jsonl"
    def native_rows(path, wanted):
        require(path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(sessions.resolve()),
            "actual native session locator required")
        selected = {}
        with path.open("rb") as stream:
            for number, line in enumerate(stream, 1):
                if number in wanted:
                    sha, size = wanted[number]
                    require(line.endswith(b"\n") and len(line) == size and hashlib.sha256(line).hexdigest() == sha,
                        "exact physical native session row changed")
                    selected[number] = json.loads(line)
                if number >= max(wanted):
                    break
        require(set(selected) == set(wanted), "original native session rows incomplete")
        return selected
    sender = native_rows(hq_session, {86436: (
        "50911f1d0b427a33ab8b633de0d348719a923e862fd3606d3f264a48b2838b9a", 5815)})[86436]
    receiver = native_rows(a2_session, {
        51849: ("002c2877c85e277c152a44271000a871ff10a9cb033ca4b812cfe104d991cce3", 5652),
        51852: ("37a041bf115e0e5e8c3131b010454ae591f5949cfbdda39f4fc55ec252fde80f", 699)})
    send_event, fco_event, reply_event = sender["payload"], receiver[51849]["payload"], receiver[51852]["payload"]
    send_item, fco_item, reply_item = send_event["item"], fco_event["item"], reply_event["item"]
    native_text = fco_item.get("output")
    match = re.fullmatch(r"<codex_delegation>\n  <source_thread_id>([^<\n]+)</source_thread_id>\n  <input>([\s\S]+)</input>\n</codex_delegation>",
        native_text) if isinstance(native_text, str) else None
    require(sender.get("type") == receiver[51849].get("type") == receiver[51852].get("type") == "event_msg"
        and all(value.get("type") == "item_completed" for value in (send_event, fco_event, reply_event))
        and send_event.get("thread_id") == hq["task_id"]
        and fco_event.get("thread_id") == reply_event.get("thread_id") == fixed["task_id"]
        and fco_event.get("turn_id") == reply_event.get("turn_id") == turn["id"]
        and send_item.get("type") == "McpToolCall" and send_item.get("server") == "codex_app"
        and send_item.get("tool") == "send_message_to_thread"
        and send_item.get("pluginId") == "codex-app-tools@openai-bundled"
        and send_item.get("status") == "completed"
        and send_item.get("arguments") == send["actual_arguments"]
        and send_item.get("result") == send["native_return"]
        and fco_item.get("type") == "FunctionCallOutput"
        and fco_item.get("namespace") == "codex_app" and fco_item.get("name") == "send_message_to_thread"
        and match is not None and match.group(1) == hq["task_id"]
        and html.unescape(match.group(2)) == body
        and reply_item.get("type") == "AgentMessage" and reply_item.get("id") == message["id"]
        and reply_item.get("phase") == message["phase"]
        and reply_item.get("content") == [{"type": "Text", "text": ack_text + "\n"}],
        "exact native HQ send, delivered full FCO and first A2 reply required")
    start_ms, sent_ms = send_event.get("started_at_ms"), send_event.get("completed_at_ms")
    fco_ms, reply_start_ms, reply_ms = (fco_event.get("completed_at_ms"),
        reply_event.get("started_at_ms"), reply_event.get("completed_at_ms"))
    require(all(type(value) is int for value in (start_ms, sent_ms, fco_ms, reply_start_ms, reply_ms))
        and checked.timestamp() * 1000 <= start_ms <= sent_ms <= fco_ms <= reply_start_ms <= reply_ms
        <= sent.timestamp() * 1000 <= ack_at.timestamp() * 1000
        and turn["startedAt"] * 1000 <= fco_ms,
        "actual original native send/FCO/reply/receipt ordering required")
    require(send_event.get("turn_id") and send_item.get("id")
        and send_event.get("thread_id") == hq["task_id"],
        "physical original HQ sender turn and call identity required")
    return {"dispatch": dispatch, "dispatch_index": index,
        "ack": acks[0], "ack_index": receipts.index(acks[0]),
        "native_turn_id": turn["id"], "native_message_id": message["id"],
        "source_turn_id": send_event["turn_id"], "source_call_id": send_item["id"]}

def _saved_original_first_binding_round(root, snapshot, receipts, plan):
    """First source-only binding authenticates original responsibility and
    the current completed producer independently; it needs no prior QA/CAS.
    Replacement still enters the unchanged blocked-verdict/rework guards.
    """
    w = _workflow()
    if _binding(root, snapshot) is not None:
        return None
    role = _goal_reviewer(root, snapshot)
    reviewer_thread = w.department_registry(root)[role]["chat_binding"]["task_id"]
    original_action = "assign-goal-review:" + snapshot["task_id"]
    if any(row.get("receipt_type") in {"dispatch_sent", "dispatch_failed", "chat_ack"}
           and row.get("department") != role
           and (row.get("chat_task_id") == reviewer_thread or row.get("action_id") == original_action)
           for row in receipts):
        raise w.WorkflowError("saved original responsibility: original reviewer actor cannot be replaced")
    sends = [(i, row) for i, row in enumerate(receipts) if row.get("department") == role
             and row.get("receipt_type") in {"dispatch_sent", "dispatch_failed"}]
    if not sends or len(sends[0][1].get("evidence", [])) != 1:
        return None
    first = _review_source_document(root, sends[0][1]["evidence"][0])
    if first.get("schema_version") != "native-dispatch-canonical-v1":
        return None
    pins = _saved_original_source_index(root, snapshot, plan=plan)
    if not pins:
        return None
    if (plan.get("task_id") != snapshot["task_id"] or plan.get("reviewer_department") != role
            or plan.get("scope") not in _goal(root, snapshot)["authorized_scope"]
            or plan.get("reviewer_thread_id") != w.department_registry(root)[role]["chat_binding"]["task_id"]
            or any(row.get("department") in {"qa", "qa-technical"} for row in receipts)):
        raise w.WorkflowError("saved original responsibility: exact first source-only plan identity required")
    if any(row.get("department") == role and row.get("receipt_type") == "chat_ack" for row in receipts[:sends[0][0]]):
        raise w.WorkflowError("saved original responsibility: no orphan ACK before original assignment")
    current = _saved_original_dispatch_window(root, snapshot, receipts, sends[0][1], pins, initial=True)
    calls = {(current["source_turn_id"], current["source_call_id"])}
    for _, dispatch in sends[1:]:
        current = _saved_original_dispatch_window(root, snapshot, receipts, dispatch, pins)
        key = (current["source_turn_id"], current["source_call_id"])
        if key in calls:
            raise w.WorkflowError("saved original responsibility: original native call cannot prove another dispatch")
        calls.add(key)
    producer = plan["producer_department"]
    boxes = [row for row in receipts if row.get("department") == producer and row.get("receipt_type") == "outbox_received"]
    candidate = _review_source_document(root, plan["candidate"])
    if (not boxes or plan["candidate"] not in boxes[-1].get("evidence", [])
            or candidate.get("task_id") != snapshot["task_id"] or candidate.get("department") != producer
            or candidate.get("candidate_version") != plan["candidate_version"]
            or plan["candidate_sha256"] != plan["candidate"]["sha256"]
            or producer != _goal(root, snapshot)["primary_owner"] or producer == role):
        raise w.WorkflowError("saved original responsibility: current exact producer outbox/version required")
    queued = [row for row in w._result_handoff_rows(root, snapshot["task_id"]) if row.get("event") == "notification_queued"
              and row.get("outbox") == plan["candidate"] and row.get("sender_department") == producer
              and row.get("candidate_version") == plan["candidate_version"] and row.get("result_sha256") == plan["candidate_sha256"]]
    if len(queued) != 1 or queued[0].get("target_department") != role:
        raise w.WorkflowError("saved original responsibility: one current actual completion queue required")
    w._validate_goal_completed_result(root, queued[0], w.department_registry(root)[producer]["chat_binding"]["task_id"],
        through_receipt_id=boxes[-1]["receipt_id"])
    return current


CONDO_FAQ_ORIGINAL_CHILD_CHAIN = {
    "main_task": "fc-20261010-assistant1-remaining-business-continuation-v2",
    "cms_task": "fc-20261014-condo-faq-v7-cms-publishing-v1",
    "tech_task": "fc-20261014-condo-faq-v7-exact-issuer-compatibility-v1",
    "main_scope": "project:flashcast:assistant1:remaining-original-goals:v2",
    "cms_scope": "company.example:blog_posts/701c2406-ba5b-4bbc-8d47-f985047d5c81:content_en,content_zh",
    "tech_scope": "project:flashcast:condo-faq-v7:exact-issuer-compatibility:v1",
    "authority_sha256": "463bbf764c280221a55e16fb17023dcce94f2041ba3984001cf570a91abe405b",
    "main_contract_sha256": "d793afba09010a68c0657ca93a825ef0a4532437acd7fc105f1df5c83d795b2f",
    "cms_contract_sha256": "fa7aae6bd9791360386c9ffb6eb049ed1e868005993a50536dc2708553219967",
    "tech_contract_sha256": "c0b985417ac034a596d8c87f966ada03025c0b7d7a47787bc55426f5e525a7c1",
    "main_dispatch": "6f4e678b-a691-4b83-80b0-4e7f0554985d",
    "main_ack": "dbf33de9-b256-4464-8eec-9e0b9ef089fa",
    "cms_dispatch": "46b9404a-9b85-47c4-8896-45db0640589d",
    "cms_ack": "fd7d9171-70ab-4334-8eab-6694eb41e52c",
    "cms_outbox": "9697f63c-bf83-43ef-80eb-1b873c292277",
    "tech_dispatch": "17b75e9a-3b31-4cde-b04b-c0c2285c93fc",
    "tech_ack": "61dbfa18-d496-4757-9d53-755ab957b711",
}


def original_condo_faq_child_review_context(root, snapshot, receipts=None, plan=None):
    """Read this original A1 assignment through its two exact child contracts.

    The main assignment remains in the main task. No reviewer dispatch/ACK,
    publication permission, or result is created in either child ledger.
    """
    w = _workflow()
    exact = CONDO_FAQ_ORIGINAL_CHILD_CHAIN
    task = snapshot.get("task_id")
    if task not in {exact["cms_task"], exact["tech_task"]}:
        return None
    cms = task == exact["cms_task"]
    scope = exact["cms_scope"] if cms else exact["tech_scope"]
    producer = "publishing" if cms else "system-development"
    dispatch_id = exact["cms_dispatch"] if cms else exact["tech_dispatch"]
    ack_id = exact["cms_ack"] if cms else exact["tech_ack"]
    reviewer = "operations-assistant"
    fixed = w.department_registry(root)
    reviewer_thread = fixed.get(reviewer, {}).get("chat_binding", {}).get("task_id")
    if (reviewer_thread != "example-native-51808768551cf834"
            or plan is not None and any(plan.get(k) != value for k, value in {
                "task_id": task, "scope": scope, "reviewer_department": reviewer,
                "reviewer_thread_id": reviewer_thread, "producer_department": producer,
            }.items())):
        return None
    child_goal = _goal(root, snapshot)
    parent_task = exact["main_task"] if cms else exact["cms_task"]
    if (not isinstance(child_goal, dict)
            or child_goal.get("parent_task_id") != parent_task
            or child_goal.get("primary_owner") != ("content-organic-website" if cms else producer)
            or child_goal.get("responsible_assistant") != reviewer
            or child_goal.get("producer_departments") != (["content-organic-website", "publishing"] if cms else [producer])
            or child_goal.get("authorized_scope") != [scope]
            or child_goal.get("source_mode") != "approved_dispatch"
            or child_goal.get("authorization_pin", {}).get("sha256") != exact["authority_sha256"]
            or child_goal.get("human_authorization", {}).get("source_thread_id") != reviewer_thread
            or child_goal.get("human_authorization", {}).get("scope") != scope
            or child_goal.get("human_authorization", {}).get("executor") != ("content-organic-website" if cms else producer)):
        return None
    authority = child_goal["authorization_pin"]
    if w.file_digest(root, authority.get("path", "")) != authority:
        return None
    main = w.read_json(w.snapshot_path(root, exact["main_task"]))
    cms_snapshot = snapshot if cms else w.read_json(w.snapshot_path(root, exact["cms_task"]))
    main_goal, cms_goal = _goal(root, main), _goal(root, cms_snapshot)
    if (not isinstance(main_goal, dict) or not isinstance(cms_goal, dict)
            or main_goal.get("responsible_assistant") != reviewer
            or main_goal.get("authorized_scope") != [exact["main_scope"]]
            or main_goal.get("source_mode") != "approved_dispatch"
            or cms_goal.get("parent_task_id") != exact["main_task"]
            or cms_goal.get("responsible_assistant") != reviewer
            or cms_goal.get("authorized_scope") != [exact["cms_scope"]]
            or cms_goal.get("source_mode") != "approved_dispatch"
            or cms_goal.get("authorization_pin") != authority):
        return None
    contracts = ((main, main_goal, exact["main_contract_sha256"]),
                 (cms_snapshot, cms_goal, exact["cms_contract_sha256"]),
                 (snapshot, child_goal, exact["cms_contract_sha256"] if cms else exact["tech_contract_sha256"]))
    for current, goal, expected_sha in contracts:
        pin = current.get("goal_contract")
        if not isinstance(pin, dict) or pin.get("sha256") != expected_sha or w.file_digest(root, pin.get("path", "")) != pin:
            return None
        contract = w.read_json(w.safe_path(root, pin["path"]))
        contract = contract.get("goal_delivery", contract)
        if any(contract.get(key) != goal.get(key) for key in
               ("parent_task_id", "primary_owner", "responsible_assistant", "producer_departments",
                "authorized_scope", "source_mode", "human_authorization")):
            return None
    main_rows, main_invalid = w._validate_receipt_chain(root, exact["main_task"],
                                                          through_receipt_id=exact["main_ack"])
    if main_invalid:
        return None
    main_round = _current_goal_assignment_round(root, main, main_rows, {
        "reviewer_department": reviewer, "reviewer_thread_id": reviewer_thread,
        "scope": exact["main_scope"]})
    if (main_round is None or main_round["dispatch"].get("receipt_id") != exact["main_dispatch"]
            or main_round["ack"].get("receipt_id") != exact["main_ack"]):
        return None
    cms_rows, cms_invalid = w._validate_receipt_chain(root, exact["cms_task"],
                                                        through_receipt_id=exact["cms_outbox"] if not cms else exact["cms_ack"])
    if cms_invalid:
        return None
    if not cms:
        cms_producer = [(i, row) for i, row in enumerate(cms_rows)
                        if row.get("receipt_id") == exact["cms_outbox"]]
        if len(cms_producer) != 1 or cms_producer[0][1].get("department") != "publishing" or cms_producer[0][1].get("receipt_type") != "outbox_received":
            return None
    actual_rows, child_invalid = (cms_rows, []) if cms else w._validate_receipt_chain(
        root, task, through_receipt_id=ack_id)
    if child_invalid:
        return None
    if receipts is not None and receipts[:len(actual_rows)] != actual_rows:
        return None
    pairs = [(i, row) for i, row in enumerate(actual_rows)
             if row.get("receipt_id") in {dispatch_id, ack_id}]
    if len(pairs) != 2 or pairs[0][1].get("receipt_id") != dispatch_id or pairs[1][1].get("receipt_id") != ack_id:
        return None
    dispatch, ack = pairs[0][1], pairs[1][1]
    producer_thread = fixed.get(producer, {}).get("chat_binding", {}).get("task_id")
    expected_action = ("A1-condo-faq-v7-publishing-complete-continuation-20261014" if cms
                       else "A1-condo-faq-v7-system-exact-issuer-compatibility-20261014")
    if (dispatch.get("receipt_type") != "dispatch_sent" or dispatch.get("department") != producer
            or dispatch.get("chat_task_id") != producer_thread or dispatch.get("scope") != scope
            or dispatch.get("action_id") != expected_action
            or ack.get("receipt_type") != "chat_ack" or ack.get("department") != producer
            or ack.get("chat_task_id") != producer_thread or ack.get("ack_nonempty") is not True
            or w._parse_observed_at(dispatch.get("created_at")) > w._parse_observed_at(ack.get("created_at"))):
        return None
    if any(row.get("department") in {reviewer, "qa", "qa-technical"}
           and row.get("receipt_type") in {"dispatch_sent", "dispatch_failed", "chat_ack"}
           for row in (receipts if receipts is not None else w.read_jsonl(w.receipts_path(root, task)))):
        return None
    return {"dispatch": main_round["dispatch"], "ack": main_round["ack"],
            "dispatch_index": -1, "ack_index": -1, "original_main_task_id": exact["main_task"],
            "child_task_id": task, "production_permissions_inherited": False}


def _next12_native_page(root, pin, thread_id):
    """Decode one pinned provider page without losing direct-page failure flags."""
    w = _workflow()
    value = _review_source_document(root, pin)
    page = _review_raw_native_result(value) if "content" in value else value
    _review_native_containers(page)
    binding = next((item.get("chat_binding", {}) for item in w.department_registry(root).values()
                    if item.get("chat_binding", {}).get("task_id") == thread_id), None)
    if (binding is None or page.get("schemaVersion") != 1 or not isinstance(page.get("thread"), dict)
            or any(page["thread"].get(k) != binding.get(v) for k, v in
                   (("id", "task_id"), ("title", "title"), ("cwd", "cwd")))
            or page.get("status") not in (None, "completed", "inProgress")
            or not isinstance(page.get("turns"), list)
            or any(not isinstance(turn, dict) or not isinstance(turn.get("items"), list)
                   or any(not isinstance(item, dict) for item in turn["items"])
                   for turn in page["turns"])):
        raise w.WorkflowError("one exact successful next12 native thread page required")
    return page


def _next12_valid_turn(turn, item=None):
    """An in-progress historical turn is valid; an errored selection is not."""
    if not isinstance(turn, dict) or turn.get("status") not in {"completed", "inProgress"}:
        raise ValueError("successful selected next12 native turn required")
    _review_native_containers(turn)
    if item is not None:
        if not isinstance(item, dict):
            raise ValueError("selected next12 native item required")
        _review_native_containers(item)


def _next12_ack_source(root, ack, dispatch, target_thread, *, observation_suffix=None):
    """Tie one actual recipient message to its original dispatch and UTF-8."""
    w = _workflow()
    pins = ack.get("evidence", [])
    native_pin = None
    text_pin = None
    turn_id = message_id = None
    if observation_suffix:
        observations = [pin for pin in pins if pin.get("path", "").endswith(observation_suffix)]
        if len(observations) != 1:
            raise w.WorkflowError("one actual next12 ACK observation required")
        observation = _review_source_document(root, observations[0])
        if (observation.get("actual_fixed_thread_id") != target_thread
                or observation.get("actual_nonempty_ACK") is not True
                or observation.get("actual_dispatch_receipt") != dispatch.get("receipt_id")):
            raise w.WorkflowError("next12 ACK observation/dispatch mismatch")
        native_pin, text_pin = observation.get("actual_native_source"), observation.get("exact_UTF8")
        turn_id, message_id = observation.get("actual_turn_id"), observation.get("actual_message_id")
        assignment_pin = observation.get("actual_assignment")
        if (native_pin not in pins or text_pin not in pins or assignment_pin not in pins
                or _review_source_document(root, assignment_pin).get("dispatch_receipt_id") != dispatch.get("receipt_id")):
            raise w.WorkflowError("next12 ACK native/UTF8/current assignment source required")
    else:
        native_candidates = [pin for pin in pins if pin.get("path", "").endswith(
            ("a1-actual-ACK-native.json", "Root-real-next12-first-nonempty-reply-native.json"))]
        text_candidates = [pin for pin in pins if pin.get("path", "").endswith("Root-real-first-nonempty-ACK-utf8.txt")]
        if len(native_candidates) != 1 or len(text_candidates) > 1:
            raise w.WorkflowError("one actual next12 initial ACK native source required")
        native_pin = native_candidates[0]
        text_pin = text_candidates[0] if text_candidates else None
    page = _next12_native_page(root, native_pin, target_thread)
    selected = [(turn, item) for turn in page["turns"] for item in turn.get("items", [])
                if item.get("type") == "agentMessage"
                and (turn_id is None or turn.get("id") == turn_id)
                and (message_id is None or item.get("id") == message_id)]
    if len(selected) != 1:
        raise w.WorkflowError("one selected actual next12 ACK message required")
    turn, item = selected[0]
    _next12_valid_turn(turn, item)
    message = item.get("text")
    if (not isinstance(message, str) or not message.strip()
            or item.get("phase") not in {"commentary", "final_answer"}
            or (text_pin is not None and
                (w.file_digest(root, text_pin.get("path", "")) != text_pin
                 or w.safe_path(root, text_pin["path"]).read_bytes() != message.encode("utf-8")))):
        raise w.WorkflowError("nonempty selected next12 ACK exact UTF-8 required")
    sent = w._parse_observed_at(dispatch.get("created_at"))
    acknowledged = w._parse_observed_at(ack.get("created_at"))
    started, completed = turn.get("startedAt"), turn.get("completedAt")
    updated = page["thread"].get("updatedAt")
    if (sent is None or acknowledged is None or sent > acknowledged
            or type(started) not in {int, float}
            or not acknowledged.timestamp() - 600 <= started <= acknowledged.timestamp()
            or type(updated) not in {int, float} or updated < started
            or not acknowledged.timestamp() - 600 <= updated <= acknowledged.timestamp() + 600
            or (completed is not None and
                (type(completed) not in {int, float} or completed < started
                 or not acknowledged.timestamp() - 600 <= completed <= acknowledged.timestamp() + 600))):
        raise w.WorkflowError("causal next12 ACK native time required")
    return {"turn_id": turn.get("id"), "message_id": item.get("id")}


def _next12_source_receipt_prefix(root, task_id, snapshot, plan, supplied=None):
    """Validate source history only through the receipt preceding its first QA."""
    w = _workflow()
    raw = w.read_jsonl(w.receipts_path(root, task_id))
    first_qa = next((i for i, row in enumerate(raw) if row.get("receipt_type") == "qa_verdict"), len(raw))
    if first_qa != len(raw):
        binding = _binding(root, snapshot)
        if (not isinstance(binding, dict) or binding.get("pin") is None
                or _review_source_document(root, binding["pin"]) != plan):
            raise w.WorkflowError("later QA cannot authorize an unbound next12 source")
    prefix = raw[:first_qa]
    if not prefix:
        raise w.WorkflowError("original next12 source receipt prefix required")
    rows, invalid = w._validate_receipt_chain(root, task_id, through_receipt_id=prefix[-1].get("receipt_id"))
    if invalid or rows != prefix or (supplied is not None and supplied[:len(prefix)] != prefix):
        raise w.WorkflowError("exact valid next12 source receipt prefix required")
    return rows


def _next12_relevant_dispatch_still_current(rows, dispatch, *, before_time=None):
    """A later failure/replay of this action invalidates its old success chain."""
    w = _workflow()
    start = rows.index(dispatch)
    for row in rows[start + 1:]:
        if (row.get("department") == dispatch.get("department")
                and row.get("action_id") == dispatch.get("action_id")
                and row.get("receipt_type") in {"dispatch_sent", "dispatch_failed"}
                and not (row.get("receipt_type") == "dispatch_sent"
                         and row.get("supersedes_receipt_id") == dispatch.get("receipt_id"))):
            stamp = w._parse_observed_at(row.get("created_at"))
            if before_time is None or stamp is None or stamp <= before_time:
                return False
    return True


def _next12_exact_native_send(root, dispatch, target_thread, sender_thread, payload_suffix, native_suffix):
    """Check one frozen policy/payload/provider call without re-sending it."""
    w = _workflow()
    pins = dispatch.get("evidence", [])
    payloads = [pin for pin in pins if pin.get("path", "").endswith(payload_suffix)]
    pages = [pin for pin in pins if pin.get("path", "").endswith(native_suffix)]
    if len(payloads) != 1 or len(pages) != 1:
        raise w.WorkflowError("one exact original next12 payload and native send page required")
    payload, page_pin = payloads[0], pages[0]
    if w.file_digest(root, payload["path"]) != payload or w.file_digest(root, page_pin["path"]) != page_pin:
        raise w.WorkflowError("original next12 transport source bytes changed")
    policies = [row for row in w.read_jsonl(Path(root) / w.POLICY_DECISIONS)
                if row.get("decision_id") == dispatch.get("policy_decision_id")]
    registry = w.department_registry(root)
    senders = [(role, item.get("chat_binding", {})) for role, item in registry.items()
               if item.get("chat_binding", {}).get("task_id") == sender_thread]
    targets = [(role, item.get("chat_binding", {})) for role, item in registry.items()
               if item.get("chat_binding", {}).get("task_id") == target_thread]
    if len(senders) != 1 or len(targets) != 1 or len(policies) != 1:
        raise w.WorkflowError("one fixed original next12 send policy identity required")
    sender_role, sender_binding = senders[0]
    _, target_binding = targets[0]
    if (len(policies) != 1
            or any(policies[0].get(k) != value for k, value in (
            ("status", "allow"), ("routing_status", "routing_allowed"),
            ("department", sender_role), ("action_class", "thread_message"),
            ("task_id", dispatch["task_id"]), ("action_id", dispatch["action_id"]),
            ("scope", dispatch["scope"]), ("target_department", dispatch["department"]),
            ("target_thread_id", target_thread), ("payload_sha256", payload["sha256"]),
            ("source_project_id", sender_binding["project_id"]),
            ("target_project_id", target_binding["project_id"]),
            ("target_thread_title", target_binding["title"]),
            ("target_cwd", target_binding["cwd"])))):
        raise w.WorkflowError("exact original next12 send policy required")
    page = _next12_native_page(root, page_pin, sender_thread)
    prompt = w.safe_path(root, payload["path"]).read_text(encoding="utf-8")
    sends = [(turn, item) for turn in page.get("turns", []) for item in turn.get("items", [])
             if item.get("type") == "mcpToolCall" and item.get("server") == "codex_app"
             and item.get("tool") == "send_message_to_thread"
             and item.get("status") == "completed" and item.get("arguments", {}).get("threadId") == target_thread
             and item.get("arguments", {}).get("prompt") == prompt]
    if len(sends) != 1:
        raise w.WorkflowError("one actual native next12 message with exact frozen prompt required")
    _next12_valid_turn(*sends[0])
    return payload


def next12_original_parent_review_context(root, snapshot, receipts=None, plan=None):
    """Consume the actual parent A1 responsibility for this one existing child.

    The parent receipts retain their original task and IDs.  This read-only
    context neither creates a child reviewer send/ACK nor treats producer
    intake as a formal QA verdict.
    """
    w = _workflow()
    child_id = "fc-20261016-industry-keyword-next-twelve-pages-v1"
    parent_id = "fc-20261015-industry-keywords-site-coverage-plan-v1"
    if snapshot.get("task_id") != child_id or not isinstance(plan, dict):
        return None
    proof = plan.get("original_parent_review_source")
    required = {"schema_version", "parent_task_id", "parent_contract", "child_contract",
                "human_authorization", "parent_dispatch_receipt_id", "parent_ack_receipt_id",
                "child_producer_dispatch_receipt_id", "child_producer_ack_receipt_id",
                "v3_intake_record_id"}
    if not isinstance(proof, dict) or set(proof) != required or proof.get("schema_version") != 1:
        return None
    parent = w.read_json(w.snapshot_path(root, parent_id))
    pg, cg = _goal(root, parent), _goal(root, snapshot)
    scope = "project:flashcast:industry-keyword-next-twelve-pages:v1"
    reviewer, producer = "operations-assistant", "content-organic-website"
    registry = w.department_registry(root)
    reviewer_thread = registry[reviewer]["chat_binding"]["task_id"]
    producer_thread = registry[producer]["chat_binding"]["task_id"]
    if (not isinstance(pg, dict) or not isinstance(cg, dict)
            or proof["parent_task_id"] != parent_id or cg.get("parent_task_id") != parent_id
            or parent.get("goal_contract") != proof["parent_contract"]
            or snapshot.get("goal_contract") != proof["child_contract"]
            or cg.get("authorization_pin") != proof["human_authorization"]
            or cg.get("human_authorization", {}).get("scope") != scope
            or cg.get("human_authorization", {}).get("executor") != producer
            or cg.get("human_authorization", {}).get("source_thread_id") != registry["operations"]["chat_binding"]["task_id"]
            or pg.get("responsible_assistant") != reviewer
            or cg.get("responsible_assistant") != reviewer
            or cg.get("primary_owner") != producer or cg.get("producer_departments") != [producer]
            or cg.get("authorized_scope") != [scope] or cg.get("source_mode") != "approved_dispatch"
            or any(cg.get(k, False) is not False for k in ("production_write_allowed", "external_permission_issued"))
            or any(plan.get(k) != v for k, v in (("scope", scope), ("reviewer_department", reviewer),
                                                  ("reviewer_thread_id", reviewer_thread), ("producer_department", producer)))
            or plan.get("candidate_version") != "fc-20261016-next12-content-candidate-v3-20261016"):
        return None
    for pin in (proof["parent_contract"], proof["child_contract"], proof["human_authorization"]):
        if w.file_digest(root, pin.get("path", "")) != pin:
            return None
    contract = w.read_json(w.safe_path(root, proof["child_contract"]["path"]))
    contract = contract.get("goal_delivery", contract)
    if any(contract.get(k) != cg.get(k) for k in ("task_id", "parent_task_id", "primary_owner",
            "responsible_assistant", "producer_departments", "authorized_scope", "human_authorization")):
        return None
    parent_rows, parent_invalid = w._validate_receipt_chain(root, parent_id)
    child_rows = _next12_source_receipt_prefix(root, child_id, snapshot, plan, receipts)
    if parent_invalid:
        return None
    def one(rows, receipt_id, kind, department, thread):
        found = [row for row in rows if row.get("receipt_id") == receipt_id]
        return found[0] if len(found) == 1 and found[0].get("receipt_type") == kind and found[0].get("department") == department and found[0].get("chat_task_id") == thread else None
    dispatch = one(parent_rows, proof["parent_dispatch_receipt_id"], "dispatch_sent", reviewer, reviewer_thread)
    ack = one(parent_rows, proof["parent_ack_receipt_id"], "chat_ack", reviewer, reviewer_thread)
    producer_dispatch = one(child_rows, proof["child_producer_dispatch_receipt_id"], "dispatch_sent", producer, producer_thread)
    producer_ack = one(child_rows, proof["child_producer_ack_receipt_id"], "chat_ack", producer, producer_thread)
    if not all((dispatch, ack, producer_dispatch, producer_ack)):
        return None
    parent_scope = pg.get("authorized_scope", [None])[0]
    if (not parent_rows.index(dispatch) < parent_rows.index(ack)
            or not child_rows.index(producer_dispatch) < child_rows.index(producer_ack)
            or ack.get("ack_nonempty") is not True or producer_ack.get("ack_nonempty") is not True
            or any(row.get("supersedes_receipt_id") in {r["receipt_id"] for r in (dispatch, ack, producer_dispatch, producer_ack)}
                   for row in parent_rows + child_rows)
            or any(row.get("department") in {reviewer, "qa", "qa-technical"}
                   and row.get("receipt_type") in {"dispatch_sent", "dispatch_failed", "chat_ack"} for row in child_rows)
            or dispatch.get("task_id") != parent_id or dispatch.get("scope") != parent_scope
            or dispatch.get("action_id") != "HQ-20261016-industry-A1-real-development-followthrough-v1"
            or any(ack.get(k) != dispatch.get(k) for k in ("task_id", "department", "chat_task_id", "action_id", "scope"))
            or producer_dispatch.get("task_id") != child_id or producer_dispatch.get("scope") != scope
            or producer_dispatch.get("action_id") != "A1-next12-content1-exact-content-dispatch-20261016-v1"
            or any(producer_ack.get(k) != producer_dispatch.get(k) for k in ("task_id", "department", "chat_task_id", "action_id", "scope"))):
        return None
    for row in (dispatch, ack, producer_dispatch, producer_ack):
        if any(w.file_digest(root, pin.get("path", "")) != pin for pin in row.get("evidence", [])):
            return None
    payload = next((p for p in dispatch["evidence"] if p["path"].endswith("assistant1-main-goal-followthrough.txt")), None)
    if payload is None:
        return None
    prompt = w.safe_path(root, payload["path"]).read_text(encoding="utf-8")
    if parent_id not in prompt or "下一20页队列" not in prompt:
        return None
    try:
        _next12_exact_native_send(root, dispatch, reviewer_thread,
            registry["operations"]["chat_binding"]["task_id"],
            "assistant1-main-goal-followthrough.txt", "HQ-actual-five-dispatch-invocations-native.json")
        _next12_exact_native_send(root, producer_dispatch, producer_thread, reviewer_thread,
            "Root-next12-content1-exact-message-v2.txt", "Root-next12-actual-source-invocation-native.json")
        _next12_ack_source(root, ack, dispatch, reviewer_thread)
        _next12_ack_source(root, producer_ack, producer_dispatch, producer_thread)
    except (w.WorkflowError, OSError, ValueError, TypeError, KeyError):
        return None
    sent = next((w.read_json(w.safe_path(root, p["path"])) for p in dispatch["evidence"]
                 if p["path"].endswith("a1-actual-send.json")), {})
    if (sent.get("isError") is not False or sent.get("content") != [{"type": "text", "text": json.dumps({"threadId": reviewer_thread}, separators=(",", ":"))}]):
        return None
    handoffs = w._result_handoff_rows(root, child_id)
    intake = [row for row in handoffs if row.get("record_id") == proof["v3_intake_record_id"]]
    if (len(intake) != 1 or intake[0].get("event") != "controller_received"
            or intake[0].get("sender_department") != producer
            or intake[0].get("candidate_version") != plan["candidate_version"]
            or intake[0].get("outbox") != plan["candidate"]
            or intake[0].get("coordinator_role") != reviewer
            or intake[0].get("source_thread_id") != producer_thread
            or w.file_digest(root, plan["candidate"]["path"]) != plan["candidate"]
            or plan["candidate"] not in intake[0].get("evidence", [])
            or any(w.file_digest(root, pin.get("path", "")) != pin for pin in intake[0].get("evidence", []))):
        return None
    try:
        w.validate_outbox(root, [plan["candidate"]], producer, child_id)
        native_pin, reply_pin = intake[0]["actual_native_completion"], intake[0]["visible_reply"]
        if (w.file_digest(root, native_pin["path"]) != native_pin
                or w.file_digest(root, reply_pin["path"]) != reply_pin):
            return None
        native = _next12_native_page(root, native_pin, producer_thread)
        reply = w.safe_path(root, reply_pin["path"]).read_text(encoding="utf-8")
        selected = [(turn, item) for turn in native.get("turns", [])
                    if turn.get("id") == intake[0].get("source_turn_id")
                    for item in turn.get("items", [])
                    if item.get("id") == intake[0].get("source_message_id") and item.get("type") == "agentMessage"]
        marker = "FLASHCAST_DELIVERY_READY "
        ready = json.loads(reply[len(marker):]) if reply.startswith(marker) else {}
        if len(selected) != 1:
            return None
        _next12_valid_turn(*selected[0])
        if (selected[0][1].get("phase") not in {"commentary", "final_answer"}
                or selected[0][1].get("text") != reply
                or ready.get("task_id") != child_id or ready.get("sender_department") != producer
                or ready.get("candidate_version") != plan["candidate_version"]
                or ready.get("result_sha256") != plan["candidate"]["sha256"]
                or ready.get("outbox_path") != plan["candidate"]["path"]
                or ready.get("batch_complete") is not True):
            return None
    except (w.WorkflowError, OSError, ValueError, KeyError, TypeError):
        return None
    stamps = [w._parse_observed_at(x.get("created_at")) for x in (dispatch, ack, producer_dispatch, producer_ack, intake[0])]
    if (any(t is None for t in stamps) or stamps != sorted(stamps)
            or stamps[-1] > dt.datetime.now(dt.timezone.utc)
            or not _next12_relevant_dispatch_still_current(parent_rows, dispatch, before_time=stamps[-1])
            or not _next12_relevant_dispatch_still_current(child_rows, producer_dispatch, before_time=stamps[-1])):
        return None
    successor = plan.get("business_rework_successor")
    if successor is not None:
        selected_dispatch = [row for row in child_rows if row.get("receipt_id") in {
            successor.get("rework_dispatch_receipt_id"), successor.get("clarification_dispatch_receipt_id")}]
        selected_ack = [row for row in child_rows if row.get("receipt_id") in {
            successor.get("rework_ack_receipt_id"), successor.get("clarification_ack_receipt_id")}]
        if (len(selected_dispatch) != 2 or len(selected_ack) != 2
                or not all(_next12_relevant_dispatch_still_current(
                    child_rows, row, before_time=stamps[-1]) for row in selected_dispatch)):
            return None
        try:
            for dispatch_id, ack_id, suffix in (
                ("rework_dispatch_receipt_id", "rework_ack_receipt_id", "Root-rework-real-nonempty-ACK-observation.json"),
                ("clarification_dispatch_receipt_id", "clarification_ack_receipt_id", "Root-V2-three-prefix-real-ACK-observation.json"),
            ):
                selected_send = next(row for row in selected_dispatch if row["receipt_id"] == successor[dispatch_id])
                selected_reply = next(row for row in selected_ack if row["receipt_id"] == successor[ack_id])
                _next12_ack_source(root, selected_reply, selected_send, producer_thread, observation_suffix=suffix)
        except (w.WorkflowError, OSError, ValueError, TypeError, KeyError, StopIteration):
            return None
    return {"dispatch": dispatch, "ack": ack, "dispatch_index": -1, "ack_index": -1,
            "original_parent_task_id": parent_id, "child_task_id": child_id,
            "production_permissions_inherited": False}


def next12_normal_reviewer_source(root, snapshot, receipts):
    """Admit only this child's real parent reviewer source at receipt entry.

    The original V1 binding remains intact until a legitimate successor bind.
    Source validation is independent of the new receipt being appended, and
    neither fabricates a child dispatch nor grants a QA verdict.
    """
    w = _workflow()
    task = "fc-20261016-industry-keyword-next-twelve-pages-v1"
    if snapshot.get("task_id") != task:
        return None
    binding = _binding(root, snapshot)
    if not isinstance(binding, dict) or not isinstance(binding.get("pin"), dict):
        return None
    current = _review_source_document(root, binding["pin"])
    successor_pin = {
        "path": "drafts/system-development/fc-20261017-assistant1-original-source-recovery-v1/source-candidate-v1/next12-review-plan-v3-source-successor.json",
        "sha256": "01833cd84717b6ec47fed6438d1266f064e1251ce5d21e2cba6b90487284b8ce",
        "size": 4473,
    }
    successor = _review_source_document(root, successor_pin)
    original_pin = successor.get("business_rework_successor", {}).get("prior_plan")
    if (binding["pin"] != original_pin and current != successor):
        return None
    return next12_original_parent_review_context(root, snapshot, receipts, successor)


def _current_goal_assignment_round(root,snapshot,receipts,plan):
    """A real whole-goal reviewer assignment is not a legacy QA-plan send."""
    w=_workflow();goal=_goal(root,snapshot)
    if goal is None:return None
    role=goal['responsible_assistant']
    if (plan.get('reviewer_department')!=role or plan.get('scope') not in goal['authorized_scope']
            or any(row.get('department') in {'qa','qa-technical'} for row in receipts)):return None
    binding=_binding(root,snapshot) or {}
    frozen=binding.get('current_assignment_review_source')
    index=w.read_json(Path(root)/'data/department-current-assignment.json')
    pin=frozen or index.get('assignments',{}).get(role)
    if not isinstance(pin,dict):return None
    import goal_continuity as continuity
    try:
        item=continuity.pin_document(root,pin)
        if item.get('department')!=role:return None
        original,dispatch_source=continuity._dispatch_source(root,item)
        active={'task_id':original['task_id'],'actual_message_delivered':True,
                'dispatch_receipt_id':dispatch_source['receipt_id']}
    except (w.WorkflowError,OSError,ValueError,KeyError,TypeError):
        if frozen:raise w.WorkflowError('frozen whole-goal reviewer assignment changed')
        return None
    if not active or active.get('task_id')!=snapshot['task_id'] or active.get('actual_message_delivered') is not True:return None
    matches=[(i,row) for i,row in enumerate(receipts) if row.get('receipt_id')==active['dispatch_receipt_id']]
    if len(matches)!=1:return None
    dispatch_index,dispatch=matches[0]
    acks=[(i,row) for i,row in enumerate(receipts) if i>dispatch_index and row.get('receipt_type')=='chat_ack'
          and row.get('department')==role and row.get('chat_task_id')==plan['reviewer_thread_id'] and row.get('ack_nonempty') is True]
    if not acks:return None
    ack_index,ack=acks[0]
    if w._parse_observed_at(dispatch['created_at'])>w._parse_observed_at(ack['created_at']):return None
    return {'dispatch':dispatch,'dispatch_index':dispatch_index,'ack':ack,'ack_index':ack_index,
            'current_assignment_review_source':pin,'production_permissions_inherited':False}


def _assigned_review_round(root, snapshot, receipts, plan, *, source_pins=None):
    """Resume the original assignment; never turn a new reviewer into that role.

    Actual dispatch/ACK receipts are already checked by the native receipt
    consumer. A continuation still needs the frozen original goal and an exact
    recorded routing decision. This does not create or replace a result lease.
    """
    w = _workflow()
    goal = _goal(root, snapshot)
    if goal is None:
        return None
    if "adopted_source_continuation" in plan:
        _, _, _, current = _tnew_bound_bootstrap_responsibility(root, snapshot, plan)
        if receipts != _strict_source_rows(root, snapshot["task_id"]):
            raise w.WorkflowError("complete current original responsibility receipts required")
        return current["responsibility_windows"][-1]
    from owner_adopted_pilot_consumer import review_context as adopted_pilot_review
    adopted = adopted_pilot_review(root, snapshot, receipts, plan)
    if adopted is not None:return adopted
    ordinary=_current_goal_assignment_round(root,snapshot,receipts,plan)
    if ordinary is not None:return ordinary
    original_child = original_condo_faq_child_review_context(root, snapshot, receipts, plan)
    if original_child is not None:return original_child
    original_next12 = next12_original_parent_review_context(root, snapshot, receipts, plan)
    if original_next12 is not None:return original_next12
    saved_first = _saved_original_first_binding_round(root, snapshot, receipts, plan)
    if saved_first is not None:
        return saved_first
    default_sources = source_pins is None
    if default_sources:
        source_pins = []
    reviewer = _goal_reviewer(root, snapshot)
    reviewer_thread = w.department_registry(root)[reviewer]["chat_binding"]["task_id"]
    original_review_action = "assign-goal-review:" + snapshot["task_id"]
    if any(row.get("receipt_type") in {"dispatch_sent", "dispatch_failed", "chat_ack"}
           and row.get("department") != reviewer
           and (row.get("chat_task_id") == reviewer_thread or row.get("action_id") == original_review_action)
           for row in receipts):
        # An original reviewer proof with a changed actor is invalid evidence,
        # not an unrelated producer row that may disappear through role filters.
        return None
    if "parent_initial_child_review" in plan:
        inherited_child = _prepare_parent_initial_child_review(root, snapshot, plan["parent_initial_child_review"])
        if (plan.get("reviewer_thread_id") != w.department_registry(root)[reviewer]["chat_binding"]["task_id"]
                or plan.get("scope") != inherited_child["proof"]["scope"]
                or any(row.get("department") in {reviewer, "qa", "qa-technical"}
                       and row.get("receipt_type") in {"dispatch_sent", "dispatch_failed", "chat_ack"}
                       for row in receipts)):
            raise w.WorkflowError("child inherited review cannot replace or fabricate a reviewer send/ACK")
        return inherited_child
    native_proof = plan.get("native_multi_goal_review")
    native = prepare_native_multi_goal_review(root, snapshot, native_proof) if native_proof is not None else None
    if native and (plan.get("reviewer_thread_id") != w.department_registry(root)[reviewer]["chat_binding"]["task_id"]
                   or plan.get("scope") != native_proof.get("scope")):
        raise w.WorkflowError("exact original multi-goal reviewer thread/scope required")
    history = [(i, row) for i, row in enumerate(receipts)
               if row.get("department") in {reviewer, "qa", "qa-technical"}]
    if any(row.get("department") != reviewer for _, row in history):
        return None
    sends = [(i, row) for i, row in history
             if row.get("receipt_type") in {"dispatch_sent", "dispatch_failed"}]
    if not sends:
        return native
    declared_initial = [row for _, row in sends
                        if row.get("action_id") == "assign-goal-review:" + snapshot["task_id"]]
    if len(declared_initial) > 1:
        return None
    initial = [(i, row) for i, row in sends if _initial_assignment(root, snapshot, row, native_proof)]
    if len(initial) != 1:
        return None
    index, current = initial[0]
    if (any(i < index for i, _ in sends)
            or any(row.get("supersedes_receipt_id") == current.get("receipt_id") for row in receipts)):
        return None
    binding = _binding(root, snapshot) or {}
    selected = [(index, current)]
    for send_index, row in sends:
        if send_index <= index:
            continue
        strict_candidate = (binding.get("pin") in row.get("evidence", [])
                            and plan.get("candidate") in row.get("evidence", [])
                            and row.get("scope") == plan.get("scope"))
        if strict_candidate:
            selected.append((send_index, row))
        elif (_saved_original_goal_continuation(root, snapshot, receipts, row, plan) is not None
              or _same_goal_hq_native_continuation(root, snapshot, receipts, row, plan) is not None
              or _actual_original_hq_20261013_notice(root, snapshot, receipts, row, plan) is not None
              or _modern_original_goal_continuation(root, snapshot, receipts, row, plan) is not None
              or _hq_original_goal_continuation(root, snapshot, receipts, row, plan) is not None):
            # Preserve the original assignment while validating this real
            # transport/ACK pair in its own observation window.
            selected.append((send_index, row))
        elif not (_same_original_source_notice(root, snapshot, receipts, row, plan, source_pins=source_pins)
                  or _same_goal_rework_notice(root, snapshot, receipts, row, plan)
                  or _same_goal_functional_result_notice(root, snapshot, receipts, row, plan)):
            if not default_sources:
                return None
            source_pins = _candidate_review_source_pins(root, snapshot, plan)
            if not _same_original_source_notice(root, snapshot, receipts, row, plan, source_pins=source_pins):
                source_pins = _received_review_source_pins(root, snapshot, receipts, binding, plan)
            default_sources = False
            if not _same_original_source_notice(root, snapshot, receipts, row, plan, source_pins=source_pins):
                return None
    allowed_acks = set()
    logical_acks = {}
    for send_index, _ in selected:
        # A successful result notice is not a fresh responsibility window.
        # Later exact observations of that original ACK remain in its group.
        window_end = next((i for i, _ in selected if i > send_index), len(receipts))
        window_acks = [(i, row) for i, row in history if send_index < i < window_end
                       and row.get("receipt_type") == "chat_ack"
                       and row.get("chat_task_id") == plan["reviewer_thread_id"]
                       and row.get("ack_nonempty") is True]
        if len(window_acks) == 1:
            canonical_ack = window_acks[0]
        else:
            canonical_ack = _same_original_ack_group(root, snapshot, receipts,
                                                     receipts[send_index], window_acks, plan)
            if canonical_ack is None:
                canonical_ack = _same_original_responsibility_ack_group(root, snapshot, receipts,
                                                                        receipts[send_index], window_acks, plan)
        if canonical_ack is None:
            return None
        logical_acks[send_index] = canonical_ack
        allowed_acks.update(i for i, _ in window_acks)
    if any(i not in allowed_acks for i, row in history if row.get("receipt_type") == "chat_ack"):
        return None
    index, current = selected[-1]
    if (current.get("receipt_type") != "dispatch_sent"
            or current.get("task_id") != snapshot["task_id"]
            or current.get("chat_task_id") != plan["reviewer_thread_id"]
            or current.get("scope") not in goal["authorized_scope"]
            or plan.get("scope") not in goal["authorized_scope"]):
        return None
    if not _initial_assignment(root, snapshot, current, native_proof):
        policies = [row for row in w.read_jsonl(root / w.POLICY_DECISIONS)
                    if row.get("decision_id") == current.get("policy_decision_id")]
        expected = {"status": "allow", "routing_status": "routing_allowed",
                    "task_id": snapshot["task_id"], "action_id": current.get("action_id"),
                    "action_class": "thread_message", "scope": current.get("scope"),
                    "target_department": reviewer, "target_thread_id": plan["reviewer_thread_id"]}
        if len(policies) != 1 or any(policies[0].get(key) != value for key, value in expected.items()):
            return None
    ack_index, ack = logical_acks[index]
    if any(row.get("supersedes_receipt_id") == ack.get("receipt_id") for row in receipts):
        return None
    dispatch_at, ack_at = [w._parse_observed_at(row.get("created_at")) for row in (current, ack)]
    if dispatch_at is None or ack_at is None or not dispatch_at <= ack_at <= dt.datetime.now(dt.timezone.utc):
        return None
    return {**(native or {}), "dispatch": current, "dispatch_index": index, "ack": ack, "ack_index": ack_index}


def _historical_adopted_source_round(root, snapshot, receipts, plan, *, historical_continuation, successor_plan):
    """Select an adopted original round after validating the complete current round.

    Both plans and the cutoff come from actual bound events and released source
    effects. Later HQ inputs stay in the complete current responsibility check;
    no receipt prefix replaces the caller's ledger or ordinary review policy.
    """
    w = _workflow()
    def require(value, reason):
        if not value:
            raise w.WorkflowError("historical adopted source round: " + reason)
    def unique(pairs):
        value = {}
        for key, item in pairs:
            require(key not in value, "ambiguous current receipt fields rejected")
            value[key] = item
        return value
    try:
        root = Path(root).resolve()
        task = snapshot["task_id"]
        persisted = [json.loads(line, object_pairs_hook=unique,
                               parse_constant=lambda value: (_ for _ in ()).throw(ValueError("finite receipt fields required")))
                     for line in w.receipts_path(root, task).read_text(encoding="utf-8").splitlines()
                     if line.strip()]
        require(isinstance(receipts, list) and receipts and persisted == receipts,
                "the complete exact current receipt ledger is required")
        previous, seen = "", set()
        for row in persisted:
            require(isinstance(row, dict) and row.get("task_id") == task and row.get("receipt_id")
                    and row["receipt_id"] not in seen and row.get("previous_hash") == previous
                    and row.get("receipt_hash") == w.sha256_value(w._receipt_payload_for_hash(row)),
                    "complete current receipt identities and hash chain required")
            seen.add(row["receipt_id"]); previous = row["receipt_hash"]
        require(not w.validate_workflow_events(root, task), "complete actual workflow event chain required")
        events = [row for row in w.read_jsonl(root / w.WORKFLOW_EVENTS) if row.get("task_id") == task]
        bound = [row for row in events if isinstance(row.get("details", {}).get("qa_review_plan_bound"), dict)]
        current_plan = _review_source_document(root, successor_plan)
        current_events = [row for row in bound if row["details"]["qa_review_plan_bound"].get("pin") == successor_plan]
        require(len(current_events) == 1,
                "explicit successor pin must have one actual immutable binding")
        current_binding = current_events[0]["details"]["qa_review_plan_bound"]
        current_snapshot = {**_review_context(root, snapshot), "qa_review_plan": current_binding}
        require(load_plan(root, current_snapshot, current_binding) == current_plan,
                "actual successor binding and exact validated plan required")
        current_round = _assigned_review_round(root, current_snapshot, receipts, current_plan)
        require(current_round is not None, "the entire current assignment and later HQ inputs must remain valid")

        continuation = _review_source_document(root, historical_continuation)
        role, producer = current_plan["reviewer_department"], current_plan["producer_department"]
        require(continuation.get("schema") == "actual_qualified_native_handoff_source_continuation/v1"
                and continuation.get("task_id") == task and continuation.get("scope") == current_plan["scope"]
                and continuation.get("candidate_version") != current_plan["candidate_version"],
                "one distinct actually adopted same-goal source continuation required")
        historical_pin = continuation["review_plan"]
        historical_events = [row for row in bound if row["details"]["qa_review_plan_bound"].get("pin") == historical_pin]
        require(len(historical_events) == 1 and events.index(historical_events[0]) < events.index(current_events[0]),
                "one earlier real historical binding event required")
        historical_binding = historical_events[0]["details"]["qa_review_plan_bound"]
        historical_snapshot = {**current_snapshot, "qa_review_plan": historical_binding}
        require(load_plan(root, historical_snapshot, historical_binding) == plan
                and plan.get("candidate") == continuation["producer_outbox"]
                and plan.get("candidate_sha256") == continuation["producer_outbox"]["sha256"]
                and plan.get("candidate_version") == continuation["candidate_version"]
                and all(plan.get(key) == current_plan.get(key) for key in
                        ("task_id", "action_id", "action_class", "scope", "producer_department", "reviewer_department", "reviewer_thread_id")),
                "unchanged exact historical plan, producer bytes and independent responsibility required")
        producer_rows = [(i, row) for i, row in enumerate(receipts)
                         if row.get("receipt_type") == "outbox_received" and row.get("department") == producer
                         and continuation["producer_outbox"] in row.get("evidence", [])]
        require(len(producer_rows) == 1, "one actual historical producer intake required")
        producer_index, producer_row = producer_rows[0]
        later_sends = [(i, row) for i, row in enumerate(receipts) if i > producer_index
                       and row.get("department") == role and row.get("receipt_type") in {"dispatch_sent", "dispatch_failed"}]
        require(later_sends, "a real later current responsibility window must bound the historical source")
        boundary_index, boundary = later_sends[0]
        before = _review_observed_at(boundary.get("created_at"))
        require(before is not None and (_saved_original_goal_continuation(root, current_snapshot, receipts, boundary, current_plan) is not None
                or _modern_original_goal_continuation(root, current_snapshot, receipts, boundary, current_plan) is not None
                or _hq_original_goal_continuation(root, current_snapshot, receipts, boundary, current_plan) is not None),
                "the first later send must be an authenticated original HQ continuation")
        require(_original_goal_adopted_source(root, current_snapshot, current_plan, [historical_continuation], before)
                == historical_continuation, "actual historical native QA, CAS, committed fences and release required")
        box = _review_source_document(root, continuation["source_qa"])
        bound_at, received_at, reviewed_at = [_review_observed_at(value) for value in
            (historical_events[0].get("created_at"), producer_row.get("created_at"), box.get("created_at"))]
        require(all(value is not None for value in (bound_at, received_at, reviewed_at))
                and received_at <= bound_at <= reviewed_at <= before,
                "real historical intake, binding, independent review and later continuation must be ordered")

        original_sends = [(i, row) for i, row in enumerate(receipts) if i < boundary_index
                          and row.get("department") in {role, "qa", "qa-technical"}
                          and row.get("receipt_type") in {"dispatch_sent", "dispatch_failed"}]
        require(len(original_sends) == 1, "the original historical source must retain its sole actual review assignment")
        dispatch_index, dispatch = original_sends[0]
        require(dispatch_index < producer_index and dispatch.get("department") == role
                and _initial_assignment(root, historical_snapshot, dispatch)
                and _initial_assignment_envelope(root, historical_snapshot, dispatch, historical_snapshot["goal_contract"]),
                "complete original native dispatch and responsibility ACK required")
        acks = [(i, row) for i, row in enumerate(receipts) if dispatch_index < i < boundary_index
                and row.get("department") == role and row.get("receipt_type") == "chat_ack"]
        require(len(acks) == 1, "one exact native original responsibility ACK required")
        ack_index, ack = acks[0]
        require(ack_index < producer_index and ack.get("ack_nonempty") is True
                and all(ack.get(key) == dispatch.get(key) for key in
                        ("task_id", "department", "action_id", "action_class", "scope", "policy_decision_id", "chat_task_id"))
                and not any(row.get("supersedes_receipt_id") in {dispatch["receipt_id"], ack["receipt_id"]} for row in receipts),
                "historical dispatch and ACK identities must remain intact in the entire ledger")
        return {"dispatch": dispatch, "dispatch_index": dispatch_index, "ack": ack, "ack_index": ack_index,
                "historical_continuation": historical_continuation, "historical_plan": historical_pin,
                "successor_plan": successor_plan, "current_round": current_round,
                "producer_receipt_id": producer_row["receipt_id"], "producer_receipt_hash": producer_row["receipt_hash"],
                "historical_binding_event_id": historical_events[0]["event_id"],
                "boundary_receipt_id": boundary["receipt_id"], "boundary_index": boundary_index,
                "full_receipt_count": len(receipts), "full_receipt_hash": receipts[-1]["receipt_hash"]}
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
        raise w.WorkflowError("historical adopted source round: complete exact immutable provenance required") from exc


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


def validate_cms_candidate_acceptance(root, snapshot, target, operation="publish"):
    """Original T3 only: independent candidate proof never calls full-goal PASS."""
    from paid_three_page_bounded_cms import acceptance
    return acceptance(root, snapshot, target, operation)


def _original_paid2_frozen_plan_read(root, snapshot, binding, plan):
    """Validate the original plan only under authenticated historical read identities.

    Returns the original IDs. Context ends before the current consumer resumes;
    historical context prohibits policy, receipt and all control writes.
    """
    from department_rotation import historical_assignment_validator, validation_registry, _records, _id
    task = 'fc-20261019-chatgpt-paid2-execution-followthrough-v1'
    if snapshot.get('task_id') != task or validation_registry(root) is not None:
        return False
    base = 'logs/handoffs/2026-10-19-chatgpt-paid2-task-transfer/'
    plan_pin = {'path': base + 'current-account-prelaunch-v1/A1-review-plan-v3-20261019.json',
                'sha256': '572db3953d568011528ad5f5d99a41719d6c4790bba3e3903df5da6396e1991e', 'size': 1939}
    if binding.get('pin') != plan_pin:
        return False
    w = _workflow()
    contract_pin = {'path': base + 'goal-input.json', 'sha256': 'e4af34666428400f894bcd0644c92b3843477b5aa32c3354550ef883f48b2422', 'size': 2988}
    original = _review_source_document(root, contract_pin)
    goal = _goal(root, snapshot)
    fixed = {'operations-assistant': ('example-native-51808768551cf834', '<LOCAL_TASK_ID>'),
             'paid-growth-data-2': ('example-native-0e339895a5d2c6da', '<LOCAL_TASK_ID>')}
    planned = {x.get('department'): x for x in snapshot.get('departments', [])}
    if (snapshot.get('goal_contract') != contract_pin or plan != _review_source_document(root, plan_pin)
            or goal is None or any(goal.get(k) != original.get(k) for k in (*GOAL_IDENTITY, 'human_authorization') if k != 'responsible_assistant')
            or goal.get('responsible_assistant') != 'operations-assistant'
            or binding.get('goal_identity') != {k: goal[k] for k in GOAL_IDENTITY}
            or any(len([x for x in snapshot.get('departments', []) if x.get('department') == role]) != 1
                   or planned[role].get('chat_task_id') != ids[0] for role, ids in fixed.items())
            or plan.get('reviewer_thread_id') != fixed['operations-assistant'][0]
            or plan.get('controller_thread_id') != fixed['operations-assistant'][0]):
        raise w.WorkflowError('exact original Paid2 frozen plan and four historical identity fields required')
    mappings = [row for row in _records(root) if row['role'] in fixed]
    if (len(mappings) != 2 or any((_id(row['old_binding']), _id(row['new_binding'])) != fixed[row['role']]
                                  for row in mappings)):
        raise w.WorkflowError('two actual trusted same-role Paid2/reviewer rotations required')
    source_pin = {'path': base + 'actual-assignment-input.json', 'sha256': '9be46f67998f3d80e74e139cd777d3603edc297702792573ea692bc562eee22d', 'size': 1146}
    item = _review_source_document(root, source_pin)

    @historical_assignment_validator
    def validate_original(root, item):
        from goal_continuity import _dispatch_source
        from goal_delivery_runtime import _collaboration_native
        if validation_registry(root) is None:
            raise w.WorkflowError('actual frozen assignment rotation context required; read-only only')
        original_snapshot, sent = _dispatch_source(root, item)
        if (original_snapshot.get('goal_contract') != contract_pin
                or sent.get('receipt_id') != '79351c68-0c27-414e-ab3d-0e561fd500fd'
                or sent.get('receipt_hash') != '3693b95b2d9892ce2c61b0f9b8fd240841037044f78e045fc9ba9ec802973bca'):
            raise w.WorkflowError('exact actual original Paid2 dispatch required')
        rows, bad = w._validate_receipt_chain(root, task, through_receipt_id='7e523d8c-d5be-4813-a5ec-0c826fd4cedf')
        acks = [row for row in rows if row.get('receipt_id') == '7e523d8c-d5be-4813-a5ec-0c826fd4cedf']
        if (bad or len(acks) != 1 or sent not in rows or rows.index(sent) >= rows.index(acks[0])
                or acks[0].get('receipt_hash') != '0344d9ad200a3a3bcf056ae1e7fc1cb711f0f3c1bfab7c5ba3b8dba203818689'
                or acks[0].get('ack_nonempty') is not True
                or acks[0].get('chat_task_id') != fixed['paid-growth-data-2'][0]
                or acks[0].get('department') != 'paid-growth-data-2'):
            raise w.WorkflowError('unchanged original Paid2 dispatch/ACK prefix required')
        ack = acks[0]
        native = _collaboration_native(root, ack['evidence'][0])
        replies = [(turn, message) for turn in native.get('turns', [])
                   if turn.get('id') == 'example-native-0ace1340a8febd65'
                   for message in turn.get('items', [])
                   if message.get('id') == 'msg_ab00802bc503f9dcd433bcf97afff8ff2c173a66f96d6272f7e05e2d60789311' and message.get('type') == 'agentMessage']
        if (native.get('thread', {}).get('id') != fixed['paid-growth-data-2'][0] or len(replies) != 1
                or not str(replies[0][1].get('text', '')).strip()):
            raise w.WorkflowError('actual nonempty original Paid2 native ACK required')
        _review_native_containers(replies[0][0]); _review_native_containers(replies[0][1])
        sent_at, ack_at = (_review_observed_at(x.get('created_at')) for x in (sent, ack))
        started = replies[0][0].get('startedAt')
        if (not sent_at or not ack_at or not sent_at <= ack_at <= dt.datetime.now(dt.timezone.utc)
                or type(started) not in {int, float} or started > ack_at.timestamp()):
            raise w.WorkflowError('actual original dispatch/ACK chronology required')
        validate_plan(root, snapshot, plan)

    validate_original(root, item)
    return True


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
    if not _original_paid2_frozen_plan_read(root, snapshot, binding, plan):
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


def _owner_original_pre_verdict_successor(root,snapshot,receipts,old_binding,plan):
    """Admit this actual received same-goal delta before any formal parent QA.

    No blocked/pass receipt is manufactured; the normal changed-scope and exact
    current producer checks in _validate_rework continue to apply.
    """
    if snapshot.get('task_id')!='fc-20261021-owner-delegated-nonpayment-decisions-repair-v1':return False
    w=_workflow()
    try:
        if (any(row.get('receipt_type')=='qa_verdict'for row in receipts)or 'rework_of'in plan
                or old_binding!=snapshot.get('qa_review_plan')):return False
        old=load_plan(root,snapshot,old_binding)
        if any(plan.get(k)!=old.get(k)for k in ('task_id','scope','producer_department','reviewer_department',
                'reviewer_thread_id','controller_department','controller_thread_id','risk_level',
                'single_final_reviewer','production_write_allowed','external_permission_issued')):return False
        notices=[row for row in receipts if row.get('receipt_id')=='1a3ac28a-f06c-42ce-a14b-1b9a1d785b69']
        if len(notices)!=1 or not _owner_original_producer_HQ_resume(root,snapshot,receipts,notices[0],old):return False
        producer=[row for row in receipts if row.get('department')=='system-development'and row.get('receipt_type')=='outbox_received']
        if not producer or receipts.index(producer[-1])<=receipts.index(notices[0]):return False
        pins=[pin for pin in producer[-1].get('evidence',[])if pin.get('path','').endswith('.json')]
        if len(pins)!=1:return False
        pin=pins[0];box=_review_source_document(root,pin)
        if (box.get('candidate_version')!=plan.get('candidate_version')
                or not _producer_candidate_bound(root,plan,pin,box)):return False
        rows=w._result_handoff_rows(root,snapshot['task_id'])
        identity={'task_id':snapshot['task_id'],'sender_department':'system-development',
                  'candidate_version':box['candidate_version'],'result_sha256':pin['sha256']}
        matches=lambda row:all(row.get(k)==v for k,v in identity.items())and row.get('outbox')==pin
        queued=[row for row in rows if matches(row)and row.get('event')=='notification_queued'
                and row.get('target_department')=='operations-assistant-2']
        received=[row for row in rows if matches(row)and row.get('event')=='controller_received'
                  and row.get('coordinator_role')=='operations-assistant-2'
                  and row.get('responsible_assistant')=='operations-assistant-2']
        if len(queued)!=1 or len(received)!=1:return False
        from scoped_candidate_adoption import _committed
        _committed(root,received[0])
        fixed=w.department_registry(root)['system-development']['chat_binding']['task_id']
        w._validate_goal_completed_result(root,queued[0],fixed,through_receipt_id=producer[-1]['receipt_id'])
        observed=_review_observed_at(queued[0].get('reply_observed_at'))
        sent=_review_observed_at(notices[0].get('created_at'));at=_review_observed_at(received[0].get('created_at'))
        if not (sent and observed and at and sent<=observed<=at<=dt.datetime.now(dt.timezone.utc)):
            return False
        return {'schema_version':1, 'prior_plan':old_binding['pin'],
                'producer_outbox_receipt_id':producer[-1]['receipt_id'], 'producer_outbox':pin,
                'notification_queued_record_id':queued[0]['record_id'],
                'notification_queued_record_hash':queued[0]['record_hash'],
                'controller_received_record_id':received[0]['record_id'],
                'controller_received_record_hash':received[0]['record_hash']}
    except (w.WorkflowError,OSError,ValueError,TypeError,KeyError,AttributeError):
        return False


def _fe689_original_pre_verdict_successor(root, snapshot, receipts, old_binding, plan):
    """Read the actual V3→V4 correction, without inventing a formal verdict.

    This exact frozen local candidate keeps its original authorization and A1.
    Queue acceptance alone is insufficient: native receipt, committed intake,
    original rework decision and causal producer dispatch/ACK are all required.
    """
    task = 'fc-20261022-chatgpt-fe689-paused-draft-admission-repair-v1'
    if snapshot.get('task_id') != task:
        return False
    w = _workflow()
    try:
        if (snapshot.get('current_state') in w.TERMINAL_STATES
                or any(row.get('receipt_type') == 'qa_verdict' for row in receipts)
                or 'rework_of' in plan or old_binding != snapshot.get('qa_review_plan')):
            return False
        base = ('logs/handoffs/2026-10-19-chatgpt-paid2-task-transfer/'
                'offer-account-preparation-20261021-v1/resume-20261021-v1/authorized-dispatch-v1/')

        def document(path, digest):
            pin = w.file_digest(root, base + path)
            if pin['sha256'] != digest:
                raise w.WorkflowError('exact original fe689 source bytes required')
            return pin, _review_source_document(root, pin)

        old_pin, old = document('operations-assistant-independent-review-fe689-v3/exact-current-local-review-plan-v1.json',
                               '05560d0039d8772bc060a331d68acde3cc3358db3d857411e416b73fa556ceee')
        new_pin, exact_plan = document('operations-assistant-independent-review-fe689-v4/exact-current-local-review-plan-v1.json',
                                      '7911a7c0e0b43e3bb560fcf33a80a6fe414cb57d4bde2a3bc54b7c45bae66d45')
        contract_pin, _ = document('system-admission-repair-goal-fe689-v31.json',
                                  'c17f2bbc8f28a6dc260b7aa4ee7bea3d66d9e173148f9e67f40e43bedeab7f99')
        auth_pin, _ = document('owner-system-admission-repair-send-authorized-v31.json',
                              'c6a485833e516d7b5e137b925071dcae27312cf15f42d986f75f8e0bc56e4fa4')
        goal = _goal(root, snapshot)
        if (old_binding.get('pin') != old_pin or plan != exact_plan
                or snapshot.get('goal_contract') != contract_pin or goal.get('authorization_pin') != auth_pin
                or goal.get('responsible_assistant') != 'operations-assistant'
                or old_binding.get('goal_identity') != {k: goal[k] for k in GOAL_IDENTITY}
                or any(plan.get(k) != old.get(k) for k in ('task_id', 'action_id', 'action_class', 'scope',
                    'producer_department', 'reviewer_department', 'reviewer_thread_id',
                    'controller_department', 'controller_thread_id', 'risk_level', 'single_final_reviewer',
                    'production_write_allowed', 'external_permission_issued'))):
            return False
        events = [e for e in w.read_jsonl(Path(root) / w.WORKFLOW_EVENTS)
                  if e.get('task_id') == task and e.get('details', {}).get('qa_review_plan_bound') == old_binding]
        if len(events) != 1:
            return False
        review = _assigned_review_round(root, snapshot, receipts, plan)
        if review is None:
            return False

        def one(rows, field, value):
            found = [row for row in rows if row.get(field) == value]
            if len(found) != 1:
                raise w.WorkflowError('one actual original fe689 source required')
            return found[0]

        handoffs = w._result_handoff_rows(root, task)
        decision = one(handoffs, 'record_id', '27a1df52-ae38-4bac-ac96-d71f40723161')
        if (decision.get('event') != 'controller_decision' or decision.get('decision') != 'rework'
                or decision.get('coordinator_role') != 'operations-assistant'
                or decision.get('next_owner') != 'system-development'):
            return False
        from scoped_candidate_adoption import _committed
        _committed(root, decision)
        dispatch = one(receipts, 'receipt_id', 'b2dbe241-918f-4b91-bc9e-7c1a2bc1c231')
        ack = one(receipts, 'receipt_id', '6fca0e8e-237e-4bab-9161-02680a340389')
        fixed = w.department_registry(root)['system-development']['chat_binding']
        if (dispatch.get('receipt_type') != 'dispatch_sent' or ack.get('receipt_type') != 'chat_ack'
                or ack.get('ack_nonempty') is not True or receipts.index(dispatch) >= receipts.index(ack)
                or any(row.get(k) != value for row in (dispatch, ack) for k, value in {
                    'task_id': task, 'department': 'system-development', 'chat_task_id': fixed['task_id'],
                    'scope': plan['scope'], 'action_class': 'thread_message',
                    'action_id': 'A1-fe689-two-current-hooks-CAS-local-rebase-original-SYS-20261022-v1'}.items())
                or any(row.get('supersedes_receipt_id') in {dispatch['receipt_id'], ack['receipt_id']}
                       for row in receipts)):
            return False
        for row in (dispatch, ack):
            for pin in row.get('evidence', []):
                _review_source_document(root, pin)
        prefix = 'operations-assistant-whole-package-review-fe689-v4/'
        prepared_pin, prepared = document(prefix + 'actual-original-SYS-two-hook-normal-prepare-result-v1.json',
                                         '3fb49a016ee160214a258afb0bfaf39761cd80545ab00fea7e1d93296241a347')
        _, request = document(prefix + 'actual-original-SYS-two-hook-normal-prepare-request-v1.json',
                              '8d250b9928f1f03b6194ce2cc6b9ce94cc0ddee35bd76ebd7d2ba12511bb1db8')
        intent_pin, intent = document(prefix + 'original-SYS-two-hook-rebase-official-queue-v1/native-queue-intent.json',
                                     'dce0c1b44bdfe19900f179f64f23a0116adc3e5cc97f1168ee384b9cb5d67ca4')
        transport_pin, transport = document(prefix + 'original-SYS-two-hook-rebase-official-queue-v1/native-queue-result.json',
                                           '327f2f6d4d6dd20fa6d73ce1a6bb4993b473629c694ab11403271cfea1ff7301')
        native_pin, _ = document(prefix + 'actual-original-SYS-rebase-received-ACK-native-v1.json',
                                 'ff13123f6db2a366a11cd8c40eaabe8bffaaca6a44758394c517fa565fd0a1ba')
        policy = one(w.read_jsonl(Path(root) / w.POLICY_DECISIONS), 'decision_id', dispatch['policy_decision_id'])
        payload = prepared.get('payload')
        if (prepared.get('status') != 'ready_to_queue' or prepared.get('policy_decision') != policy
                or request.get('payload') != payload or request.get('authorization_changes') != []
                or prepared.get('authorization_precheck', {}).get('original_authorization') != auth_pin
                or prepared.get('authorization_precheck', {}).get('status') != 'within_original_authorization'
                or any(policy.get(k) != v for k, v in {'status': 'allow', 'task_id': task,
                    'department': 'operations-assistant', 'target_department': 'system-development',
                    'target_thread_id': fixed['task_id'], 'scope': plan['scope'],
                    'action_id': dispatch['action_id'], 'payload_sha256': payload['sha256']}.items())
                or any(p not in dispatch.get('evidence', []) for p in (prepared_pin, intent_pin, transport_pin, native_pin))
                or native_pin not in ack.get('evidence', []) or ack.get('policy_decision_id') != policy['decision_id']
                or transport.get('exit_code') != 0 or transport.get('stderr') != ''
                or transport.get('stdout') != 'Queued message example-native-4bf104b27cee8dc8 for thread ' + fixed['task_id'] + '.\n'
                or any(value.get(k) != v for value in (intent, transport) for k, v in {
                    'thread_id': fixed['task_id'], 'payload_sha256': payload['sha256'],
                    'policy_decision_id': policy['decision_id'], 'transport': 'official_codex_queue'}.items())):
            return False
        if w.file_digest(root, payload.get('path', '')) != payload:
            return False
        from goal_delivery_runtime import _collaboration_native
        native = _collaboration_native(root, native_pin)
        if any(native.get('thread', {}).get(k) != fixed[v] for k, v in {'id': 'task_id', 'title': 'title', 'cwd': 'cwd'}.items()):
            return False
        turn = one(native.get('turns', []), 'id', 'example-native-452bbdf84916283f')
        user = one(turn['items'], 'id', 'example-native-8eb89c171e6da8fc')
        message = one(turn['items'], 'id', 'msg_d97dd9fbe70a5ba00bedcd4bf0c82425bd7d2534154d40a75b8fedcf076ddab2')
        if (turn.get('error') or turn.get('status') not in {'inProgress', 'completed'}
                or user.get('type') != 'userMessage' or user.get('content') != [{'type': 'text',
                    'text': w.safe_path(root, payload['path']).read_text(encoding='utf-8')}]
                or message.get('type') != 'agentMessage' or message.get('phase') != 'commentary'
                or not str(message.get('text', '')).strip() or turn['items'].index(user) >= turn['items'].index(message)):
            return False
        producer = [row for row in receipts if row.get('department') == 'system-development'
                    and row.get('receipt_type') == 'outbox_received'][-1]
        pins = [p for p in producer.get('evidence', []) if p.get('path', '').endswith('.json')]
        if len(pins) != 1 or receipts.index(producer) <= receipts.index(ack):
            return False
        box = _review_source_document(root, pins[0])
        if box.get('candidate_version') != plan['candidate_version'] or not _producer_candidate_bound(root, plan, pins[0], box):
            return False
        identity = {'task_id': task, 'sender_department': 'system-development',
                    'candidate_version': plan['candidate_version'], 'result_sha256': pins[0]['sha256'], 'outbox': pins[0]}
        matching = [row for row in handoffs if all(row.get(k) == v for k, v in identity.items())]
        queued = one(matching, 'event', 'notification_queued')
        intake = one(matching, 'event', 'controller_received')
        if (queued.get('target_department') != 'operations-assistant'
                or intake.get('coordinator_role') != 'operations-assistant'
                or intake.get('responsible_assistant') != 'operations-assistant'):
            return False
        _committed(root, intake)
        w._validate_goal_completed_result(root, queued, fixed['task_id'], through_receipt_id=producer['receipt_id'])
        stamps = [_review_observed_at(x) for x in (events[0]['created_at'], review['dispatch']['created_at'],
            review['ack']['created_at'], decision['created_at'], policy['checked_at'], transport['started_at'],
            transport['finished_at'])]
        stamps += [dt.datetime.fromtimestamp(turn['startedAt'], dt.timezone.utc)]
        stamps += [_review_observed_at(x) for x in (dispatch['created_at'], ack['created_at'], producer['created_at'],
            queued['reply_observed_at'], queued['created_at'], intake['created_at'])]
        if any(x is None for x in stamps) or stamps != sorted(stamps) or stamps[-1] > dt.datetime.now(dt.timezone.utc):
            return False
        return {'schema_version': 1, 'kind': 'original_fe689_V3_V4_pre_verdict', 'prior_plan': old_pin,
                'prior_binding_event_id': events[0]['event_id'], 'review_plan': new_pin,
                'original_rework_record_id': decision['record_id'], 'original_rework_record_hash': decision['record_hash'],
                'producer_dispatch_receipt_id': dispatch['receipt_id'], 'producer_ack_receipt_id': ack['receipt_id'],
                'producer_outbox_receipt_id': producer['receipt_id'], 'producer_outbox': pins[0],
                'notification_queued_record_id': queued['record_id'], 'notification_queued_record_hash': queued['record_hash'],
                'controller_received_record_id': intake['record_id'], 'controller_received_record_hash': intake['record_hash'],
                'actual_native_ACK': native_pin, 'production_permissions_inherited': False}
    except (w.WorkflowError, OSError, ValueError, TypeError, KeyError, IndexError, AttributeError):
        return False


def _validate_rework(root, snapshot, receipts, old_binding, plan):
    w = _workflow()
    goal = _goal(root, snapshot)
    old = load_plan(root, snapshot, old_binding)
    verdicts = [row for row in receipts if row.get("receipt_type") == "qa_verdict"]
    original_pre_verdict = (_owner_original_pre_verdict_successor(root,snapshot,receipts,old_binding,plan)
                            or _fe689_original_pre_verdict_successor(root,snapshot,receipts,old_binding,plan))
    if not original_pre_verdict and (goal is None or not verdicts or verdicts[-1].get("verdict") != "blocked"
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
    if not producer_rows or (not original_pre_verdict and receipts.index(producer_rows[-1]) <= receipts.index(verdicts[-1])):
        raise w.WorkflowError("new producer result after blocked review required for rework binding")
    pin = next((p for p in producer_rows[-1].get("evidence", []) if p.get("path", "").endswith(".json")), None)
    box = w.read_json(w.safe_path(root, pin["path"])) if pin else {}
    if box.get("candidate_version") != plan["candidate_version"] or not _producer_candidate_bound(root, plan, pin, box):
        raise w.WorkflowError("new producer outbox must bind the exact rework candidate/version")
    if any(row.get("department") == plan["reviewer_department"] and row.get("action_id") == "assign-goal-review:" + snapshot["task_id"]
           and row.get("receipt_type") in {"dispatch_sent", "dispatch_failed"} for row in receipts):
        if _assigned_review_round(root, snapshot, receipts, plan) is None:
            raise w.WorkflowError("rework must retain the complete original reviewer dispatch/ACK window")
    return original_pre_verdict


def _validate_next12_business_rework_successor(root, snapshot, receipts, old_binding, plan):
    """Admit only the real unverdicted V1→V3 business correction.

    The original business decision is not renamed as a blocked QA receipt.
    A later formal blocked/pass verdict still uses the ordinary rework guard.
    """
    w = _workflow()
    task = "fc-20261016-industry-keyword-next-twelve-pages-v1"
    proof = plan.get("business_rework_successor")
    required = {"schema_version", "prior_plan", "business_rework_record_id", "rework_dispatch_receipt_id",
                "rework_ack_receipt_id", "clarification_dispatch_receipt_id", "clarification_ack_receipt_id",
                "v3_intake_record_id", "limited_content_report"}
    goal = _goal(root, snapshot)
    old = load_plan(root, snapshot, old_binding)
    if (snapshot.get("task_id") != task or not isinstance(goal, dict) or not isinstance(proof, dict)
            or set(proof) != required or proof.get("schema_version") != 1
            or proof["prior_plan"] != old_binding.get("pin")
            or old_binding.get("pin", {}).get("sha256") != "f4f06fdff234156dbe68a66557c4b156ca571868875647f2b7792838878c8ab5"
            or any(row.get("receipt_type") == "qa_verdict" for row in receipts)
            or "rework_of" in plan or old is None
            or plan.get("candidate_version") != "fc-20261016-next12-content-candidate-v3-20261016"
            or plan.get("candidate", {}).get("sha256") != "fc861ce836a35fff43f7761581f50a3ae0077b7417ec28bc36f8832f94f5f87a"):
        raise w.WorkflowError("one exact next12 business rework successor without formal verdict required")
    same = ("task_id", "action_id", "action_class", "scope", "producer_department", "reviewer_department",
            "reviewer_thread_id", "controller_department", "controller_thread_id", "risk_level",
            "single_final_reviewer", "production_write_allowed", "external_permission_issued")
    if (any(old.get(k) != plan.get(k) for k in same)
            or old_binding.get("goal_identity") != {k: goal[k] for k in GOAL_IDENTITY}
            or plan["candidate"] == old["candidate"]
            or plan.get("original_parent_review_source") is None
            or next12_original_parent_review_context(root, snapshot, receipts, plan) is None):
        raise w.WorkflowError("successor must preserve V1 goal/reviewer and original parent responsibility")
    changed, diff, methods = plan.get("changed_scope"), plan.get("evidence_diff"), plan.get("revalidation_methods")
    if (changed != goal["authorized_scope"] or not isinstance(diff, dict)
            or diff.get("previous_candidate") != old["candidate"] or diff.get("candidate") != plan["candidate"]
            or not isinstance(diff.get("summary"), str) or not diff["summary"].strip()
            or not isinstance(methods, dict) or set(methods) != set(changed)
            or any(not isinstance(value, str) or not value.strip() for value in methods.values())):
        raise w.WorkflowError("exact bounded changed scope and V1/V3 evidence diff required")
    report_pin = proof["limited_content_report"]
    report = _review_source_document(root, report_pin)
    if (report.get("schema") != "Root-next12-V3-bounded-independent-content-decision/v1"
            or report.get("task_id") != task or report.get("identity", {}).get("result_sha256") != plan["candidate"]["sha256"]
            or report.get("changed_V2_to_V3", {}).get("blocks") != 3
            or report.get("changed_V2_to_V3", {}).get("mappings") != 5
            or report.get("original_query_count") != 74 or report.get("assigned_pages") != 12
            or report.get("formal_qa_verdict_issued") is not False
            or report.get("production_write_permission_issued") is not False
            or report.get("Save") != 0 or report.get("push") != 0 or report.get("deploy") != 0):
        raise w.WorkflowError("actual limited three-block/five-mapping V3 source required")
    rows = w._result_handoff_rows(root, task)
    decision = [row for row in rows if row.get("record_id") == proof["business_rework_record_id"]]
    intake = [row for row in rows if row.get("record_id") == proof["v3_intake_record_id"]]
    copied_intake = _review_source_document(root, report.get("actual_intake"))
    if (len(decision) != 1 or len(intake) != 1
            or decision[0].get("event") != "controller_decision" or decision[0].get("decision") != "rework"
            or decision[0].get("outbox") != old["candidate"]
            or decision[0].get("qa_status") != "NOT_VERIFIED"
            or intake[0].get("event") != "controller_received" or intake[0].get("outbox") != plan["candidate"]
            or intake[0].get("candidate_version") != plan["candidate_version"]
            or intake[0].get("sender_department") != plan["producer_department"]
            or intake[0].get("coordinator_role") != plan["reviewer_department"]
            or rows.index(decision[0]) >= rows.index(intake[0])
            or {k: v for k, v in copied_intake.items() if k not in {"result", "controller_handoff"}} != intake[0]
            or copied_intake.get("result") != "recorded"):
        raise w.WorkflowError("one exact original business decision and V3 intake required")
    ids = ("rework_dispatch_receipt_id", "rework_ack_receipt_id", "clarification_dispatch_receipt_id", "clarification_ack_receipt_id")
    selected = []
    for name, kind in zip(ids, ("dispatch_sent", "chat_ack", "dispatch_sent", "chat_ack")):
        matches = [row for row in receipts if row.get("receipt_id") == proof[name]]
        if len(matches) != 1 or matches[0].get("receipt_type") != kind or matches[0].get("department") != plan["producer_department"]:
            raise w.WorkflowError("actual producer rework and clarification send/ACK required")
        selected.append(matches[0])
    if (not all(receipts.index(selected[i]) < receipts.index(selected[i+1]) for i in range(3))
            or selected[1].get("ack_nonempty") is not True or selected[3].get("ack_nonempty") is not True
            or selected[0].get("action_id") != "A1-next12-original74-minimal-three-finding-rework-20261016-v1"
            or selected[2].get("action_id") != "A1-next12-same-rework-three-insert-prefix-clarification-20261016-v1"
            or any(row.get("task_id") != task or row.get("scope") != plan["scope"]
                   or row.get("chat_task_id") != w.department_registry(root)[plan["producer_department"]]["chat_binding"]["task_id"]
                   for row in selected)
            or any(selected[i].get(k) != selected[i+1].get(k) for i in (0, 2)
                   for k in ("task_id", "action_id", "action_class", "scope", "chat_task_id"))
            or any(row.get("supersedes_receipt_id") in {x["receipt_id"] for x in selected} for row in receipts)
            or any(w.file_digest(root, pin.get("path", "")) != pin for row in selected for pin in row.get("evidence", []))):
        raise w.WorkflowError("unaltered ordered producer rework send/ACK chain required")
    producer_thread = w.department_registry(root)[plan["producer_department"]]["chat_binding"]["task_id"]
    reviewer_thread = w.department_registry(root)[plan["reviewer_department"]]["chat_binding"]["task_id"]
    _next12_exact_native_send(root, selected[0], producer_thread, reviewer_thread,
        "Root-next12-exact-minimal-rework-message.txt", "Root-rework-actual-source-invocation-native.json")
    _next12_exact_native_send(root, selected[2], producer_thread, reviewer_thread,
        "three-insert-prefix-clarification-message-PREPARED.txt", "Root-V2-three-prefix-actual-source-invocation-native.json")
    _next12_ack_source(root, selected[1], selected[0], producer_thread,
        observation_suffix="Root-rework-real-nonempty-ACK-observation.json")
    _next12_ack_source(root, selected[3], selected[2], producer_thread,
        observation_suffix="Root-V2-three-prefix-real-ACK-observation.json")
    stamps = [w._parse_observed_at(x.get("created_at")) for x in (decision[0], *selected, intake[0])]
    if any(t is None for t in stamps) or stamps != sorted(stamps) or stamps[-1] > dt.datetime.now(dt.timezone.utc):
        raise w.WorkflowError("actual business rework chronology required")
    if not all(_next12_relevant_dispatch_still_current(receipts, dispatch, before_time=stamps[-1])
               for dispatch in (selected[0], selected[2])):
        raise w.WorkflowError("later related next12 dispatch failure or replay invalidates original success")
    return {"business_rework_successor": proof, "formal_qa_issued": False, "old_plan_preserved": old_binding["pin"]}


def _validate_post_pass_remaining_stage(root, snapshot, receipts, old_binding, plan):
    """Admit one received successor stage while keeping its prior PASS immutable."""
    w = _workflow()
    stage = plan.get("post_pass_remaining_stage")
    goal = _goal(root, snapshot)
    old = load_plan(root, snapshot, old_binding)
    required = {"prior_plan", "prior_pass_receipt_id", "adoption_journal", "hq_barrier",
                "producer_dispatch_id", "producer_ack_id", "reviewer_dispatch_id",
                "reviewer_ack_id", "producer_outbox_receipt_id", "queue_record_id", "intake_record_id"}
    if (not isinstance(stage, dict) or set(stage) not in (required, required | {"successor_adoption_journal"})
            or goal is None or old is None
            or snapshot.get("current_state") != "qa_passed" or stage["prior_plan"] != old_binding["pin"]
            or old_binding not in _bindings(root, snapshot) or "rework_of" in plan
            or any(name in plan for name in ("adopted_source_continuation", "owner_direct_review",
                                              "native_multi_goal_review", "parent_initial_child_review"))):
        raise w.WorkflowError("exact prior PASS and one explicit remaining-stage source required")
    same = ("task_id", "action_class", "scope", "producer_department", "reviewer_department",
            "reviewer_thread_id", "risk_level", "single_final_reviewer",
            "production_write_allowed", "external_permission_issued")
    if (any(plan.get(key) != old.get(key) for key in same)
            or plan["scope"] not in goal["authorized_scope"]
            or plan["candidate_version"] == old["candidate_version"]
            or plan["candidate"] == old["candidate"]
            or plan["action_id"] == old["action_id"]):
        raise w.WorkflowError("remaining stage must preserve the original goal and freeze a distinct result")
    verdicts = [(i, row) for i, row in enumerate(receipts) if row.get("receipt_type") == "qa_verdict"]
    if (not verdicts or verdicts[-1][1].get("verdict") != "pass"
            or verdicts[-1][1].get("receipt_id") != stage["prior_pass_receipt_id"]
            or any(verdicts[-1][1].get(key) != old.get(key) for key in
                   ("task_id", "action_id", "action_class", "scope"))
            or verdicts[-1][1].get("department") != plan["reviewer_department"]):
        raise w.WorkflowError("actual latest prior PASS must remain bound to the old plan")
    try:
        adoption = _review_source_document(root, stage["adoption_journal"])
        barrier = _review_source_document(root, stage["hq_barrier"])
    except (w.WorkflowError, OSError, ValueError, TypeError, KeyError) as exc:
        raise w.WorkflowError("actual prior adoption and HQ stage barrier required") from exc
    operations = adoption.get("source_operations", [])
    if (adoption.get("schema") != "actual-source-adoption-fact-journal/v1"
            or adoption.get("task_id") != snapshot["task_id"]
            or adoption.get("candidate_version") != old["candidate_version"]
            or adoption.get("candidate_manifest") != old["candidate"]
            or adoption.get("state") != "adopted" or adoption.get("actor") != plan["reviewer_department"]
            or adoption.get("business_goal_closed") is not False
            or len(operations) != 1 or operations[0].get("path") != "tools/qa_review_plan.py"
            or barrier.get("schema") != "HQ-remaining-source-scope-actual-continuation-commit-barrier/v1"
            or barrier.get("task_id") != snapshot["task_id"]
            or barrier.get("actual_dispatch_receipt_id") != stage["reviewer_dispatch_id"]
            or barrier.get("old_V2_initial_responsibility_barrier_retained") is not True
            or barrier.get("old_V2_QA_and_actual_adoption_not_repeated") is not True
            or barrier.get("remaining_source_candidate_not_adopted") is not True):
        raise w.WorkflowError("actual adopted predecessor and committed HQ remaining stage required")
    current_sha = w.file_digest(root, "tools/qa_review_plan.py")["sha256"]
    if "successor_adoption_journal" in stage:
        try:
            successor = _review_source_document(root, stage["successor_adoption_journal"])
        except (w.WorkflowError, OSError, ValueError, TypeError, KeyError) as exc:
            raise w.WorkflowError("actual independently adopted successor source required") from exc
        operations_next = successor.get("source_operations", [])
        manifest = _review_source_document(root, plan["candidate"])
        files = manifest.get("files", [])
        if (successor.get("schema") != "actual-source-adoption-fact-journal/v1"
                or successor.get("task_id") != snapshot["task_id"]
                or successor.get("candidate_version") != plan["candidate_version"]
                or successor.get("candidate_manifest") != plan["candidate"]
                or successor.get("state") != "adopted"
                or successor.get("actor") != plan["reviewer_department"]
                or successor.get("business_goal_closed") is not False
                or successor.get("source_readback", {}).get("source_readback_passed") is not True
                or len(files) != 1 or files[0].get("path") != "tools/qa_review_plan.py"
                or len(operations_next) != 1 or operations_next[0].get("path") != "tools/qa_review_plan.py"
                or operations_next[0].get("before_sha256") != operations[0].get("after_sha256")
                or operations_next[0].get("after_sha256") != files[0].get("after", {}).get("sha256")
                or current_sha != operations_next[0]["after_sha256"]):
            raise w.WorkflowError("current source must equal the actually adopted exact successor")
    elif current_sha != operations[0].get("after_sha256"):
        raise w.WorkflowError("pre-adoption stage requires the exact adopted predecessor source")
    indexed = {row.get("receipt_id"): (i, row) for i, row in enumerate(receipts)}
    if len(indexed) != len(receipts):
        raise w.WorkflowError("unique original receipt IDs required")
    labels = ("producer_dispatch_id", "reviewer_dispatch_id", "producer_ack_id", "reviewer_ack_id",
              "producer_outbox_receipt_id")
    if any(stage[key] not in indexed for key in labels):
        raise w.WorkflowError("complete actual remaining-stage receipt chain required")
    pd_i, pd = indexed[stage["producer_dispatch_id"]]
    rd_i, rd = indexed[stage["reviewer_dispatch_id"]]
    pa_i, pa = indexed[stage["producer_ack_id"]]
    ra_i, ra = indexed[stage["reviewer_ack_id"]]
    out_i, out = indexed[stage["producer_outbox_receipt_id"]]
    registry = w.department_registry(root)
    if (not (verdicts[-1][0] < pd_i < pa_i < out_i and verdicts[-1][0] < rd_i < ra_i < out_i)
            or any(row.get("task_id") != snapshot["task_id"] or row.get("scope") != plan["scope"]
                   or row.get("action_class") != "thread_message" or row.get("receipt_type") != "dispatch_sent"
                   or not row.get("policy_decision_id") for row in (pd, rd))
            or pd.get("department") != plan["producer_department"]
            or rd.get("department") != plan["reviewer_department"]
            or pd.get("chat_task_id") != registry[plan["producer_department"]]["chat_binding"]["task_id"]
            or rd.get("chat_task_id") != plan["reviewer_thread_id"]
            or any(ack.get("receipt_type") != "chat_ack" or ack.get("ack_nonempty") is not True
                   or any(ack.get(key) != dispatch.get(key) for key in
                          ("task_id", "department", "chat_task_id", "action_id", "action_class", "scope"))
                   or ack.get("policy_decision_id") not in {"", dispatch["policy_decision_id"]}
                   for ack, dispatch in ((pa, pd), (ra, rd)))):
        raise w.WorkflowError("actual HQ producer/reviewer dispatch and nonempty ACK required")
    policies = w.read_jsonl(root / w.POLICY_DECISIONS)
    for dispatch in (pd, rd):
        matches = [row for row in policies if row.get("decision_id") == dispatch["policy_decision_id"]]
        if (len(matches) != 1 or matches[0].get("status") != "allow"
                or matches[0].get("task_id") != snapshot["task_id"]
                or matches[0].get("action_id") != dispatch["action_id"]
                or matches[0].get("scope") != plan["scope"]
                or matches[0].get("target_department") != dispatch["department"]
                or matches[0].get("target_thread_id") != dispatch["chat_task_id"]):
            raise w.WorkflowError("actual same-goal HQ dispatch policy required")
        try:
            sources = [_review_source_document(root, pin) for pin in dispatch.get("evidence", [])
                       if str(pin.get("path", "")).endswith(".json")]
            wrappers = [source for source in sources if source.get("actual_thread_id") == dispatch["chat_task_id"]
                        and isinstance(source.get("exact_consumed_prompt"), dict)
                        and isinstance(source.get("raw_tool_return"), dict)]
            native_pages = [_review_raw_native_result(source) for source in sources
                            if source.get("isError") is False
                            and any(item.get("type") == "text" and item.get("text", "").startswith("{\"schemaVersion\"")
                                    for item in source.get("content", []))]
            if len(wrappers) != 1 or len(native_pages) != 1:
                raise ValueError("one actual HQ sender source required")
            prompt_pin = wrappers[0]["exact_consumed_prompt"]
            if (prompt_pin not in dispatch["evidence"]
                    or w.file_digest(root, prompt_pin["path"]) != prompt_pin
                    or matches[0].get("payload_sha256") != prompt_pin["sha256"]):
                raise ValueError("exact policy payload required")
            prompt = w.safe_path(root, prompt_pin["path"]).read_text(encoding="utf-8")
            page = native_pages[0]
            hq_thread = w.department_registry(root)["operations"]["chat_binding"]["task_id"]
            calls = [(turn, item) for turn in page.get("turns", []) for item in turn.get("items", [])
                     if item.get("type") == "mcpToolCall" and item.get("tool") == "send_message_to_thread"
                     and item.get("status") == "completed"
                     and item.get("arguments", {}).get("threadId") == dispatch["chat_task_id"]
                     and item.get("arguments", {}).get("prompt") == prompt]
            returned = wrappers[0]["raw_tool_return"]
            reply = _review_raw_native_result(returned)
            if (page.get("thread", {}).get("id") != hq_thread or len(calls) != 1
                    or reply != {"threadId": dispatch["chat_task_id"]}
                    or snapshot["task_id"] not in prompt or plan["scope"] not in prompt):
                raise ValueError("HQ native send does not bind this stage")
            _review_native_containers(page["thread"])
            _review_native_containers(calls[0][0])
            _review_native_containers(calls[0][1])
        except (w.WorkflowError, OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
            raise w.WorkflowError("actual native HQ dispatch, prompt and policy required") from exc
    for ack, dispatch in ((pa, pd), (ra, rd)):
        try:
            sources = [_review_source_document(root, pin) for pin in ack.get("evidence", [])
                       if str(pin.get("path", "")).endswith(".json")]
            def native_reply(source):
                wrapped = source.get("schema") == "actual-fixed-chat-ack/v1"
                if wrapped:
                    if (source.get("source_thread_id") != dispatch["chat_task_id"]
                            or source.get("department") != dispatch["department"]
                            or source.get("task_id") != snapshot["task_id"]
                            or source.get("original_committed_barrier") != stage["hq_barrier"]
                            or source.get("ACK_is_actual_current_nonempty") is not True
                            or source.get("dispatch_is_real") is not True):
                        return False
                    dispatch_pin = source.get("actual_dispatch_receipt")
                    if (_review_source_document(root, dispatch_pin) != dispatch
                            or w.file_digest(root, dispatch_pin["path"]) != dispatch_pin):
                        return False
                    native = _review_raw_native_result(_review_source_document(root, source["actual_native_completion"]))
                else:
                    native = source
                _review_native_containers(native)
                thread = native.get("thread", {})
                fixed = registry[dispatch["department"]]["chat_binding"]
                if (native.get("schemaVersion") != 1 or any(thread.get(key) != value for key, value in
                        {"id": dispatch["chat_task_id"], "kind": "codex", "hostId": "local",
                         "title": fixed["title"], "cwd": fixed["cwd"]}.items())
                        or thread.get("projectId", fixed["project_id"]) != fixed["project_id"]):
                    return False
                _review_native_containers(thread)
                sent, received = (_review_observed_at(row.get("created_at")) for row in (dispatch, ack))
                updated = thread.get("updatedAt")
                if (sent is None or received is None or not sent <= received
                        or type(updated) not in {int, float}
                        or not sent.timestamp() <= updated <= received.timestamp() + 1):
                    return False
                selected = [(turn, index, item) for turn in native.get("turns", [])
                            for index, item in enumerate(turn.get("items", []))
                            if item.get("type") == "agentMessage" and isinstance(item.get("text"), str)
                            and item["text"].strip()]
                if wrapped:
                    message = source.get("message", {})
                    selected = [value for value in selected if value[2] == message]
                    observed = _review_observed_at(source.get("observed_at"))
                    reply_pin = source.get("visible_reply")
                    if (len(selected) != 1 or source.get("turn") != {key: selected[0][0].get(key)
                            for key in ("id", "status", "startedAt")}
                            or observed is None or not sent <= observed <= received + dt.timedelta(seconds=1)
                            or not isinstance(reply_pin, dict)
                            or w.file_digest(root, reply_pin["path"]) != reply_pin
                            or w.safe_path(root, reply_pin["path"]).read_bytes() != message["text"].encode("utf-8")):
                        return False
                elif len(selected) != 1:
                    return False
                turn, index, message = selected[0]
                _review_native_containers(turn)
                _review_native_containers(message)
                start = turn.get("startedAt")
                # Both genuine chats were already active 23-25 seconds before
                # the HQ send. The selected reply must follow that turn's
                # send_message_to_thread output in the same narrow window.
                if (turn.get("status") not in {"inProgress", "completed"} or turn.get("error") is not None
                        or message.get("phase") not in {"commentary", "final_answer"}
                        or type(start) not in {int, float}
                        or not sent.timestamp() - 60 <= start <= received.timestamp()):
                    return False
                before = [item for item in turn["items"][:index]
                          if item.get("type") == "functionCallOutput"
                          and item.get("name") == "send_message_to_thread"
                          and item.get("namespace") == "codex_app"]
                if len(before) != 1 or any(item.get("type") == "agentMessage"
                                           for item in turn["items"][index + 1:]):
                    return False
                _review_native_containers(before[0])
                return True
            if not any(native_reply(source) for source in sources):
                raise ValueError("one native ACK reply required")
        except (w.WorkflowError, OSError, ValueError, TypeError, KeyError, AttributeError, IndexError) as exc:
            raise w.WorkflowError("actual native producer/reviewer ACK required") from exc
    if (out.get("receipt_type") != "outbox_received" or out.get("department") != plan["producer_department"]
            or out.get("task_id") != snapshot["task_id"] or len(out.get("evidence", [])) != 1
            or any(row.get("department") == plan["producer_department"]
                   and row.get("receipt_type") == "outbox_received" for row in receipts[out_i + 1:])):
        raise w.WorkflowError("one exact new producer outbox receipt required")
    pin = out["evidence"][0]
    producer = _review_source_document(root, pin)
    if not _producer_candidate_bound(root, plan, pin, producer):
        raise w.WorkflowError("remaining stage result must bind the new exact candidate")
    identity = (snapshot["task_id"], plan["producer_department"], plan["candidate_version"], pin["sha256"])
    rows = w._result_handoff_rows(root, snapshot["task_id"])
    stage_rows = [row for row in rows if tuple(row.get(field) for field in
                  ("task_id", "sender_department", "candidate_version", "result_sha256")) == identity]
    if (sum(row.get("event") == "notification_queued" for row in stage_rows) != 1
            or sum(row.get("event") == "controller_received" for row in stage_rows) != 1
            or any(row.get("event") in {"controller_decision", "controller_followthrough"}
                   for row in stage_rows)):
        raise w.WorkflowError("remaining stage requires one fresh undecided result intake")
    for event, key in (("notification_queued", "queue_record_id"), ("controller_received", "intake_record_id")):
        matches = [row for row in rows if row.get("event") == event and row.get("record_id") == stage[key]
                   and tuple(row.get(field) for field in
                             ("task_id", "sender_department", "candidate_version", "result_sha256")) == identity
                   and row.get("outbox") == pin]
        if len(matches) != 1:
            raise w.WorkflowError("actual new READY queue and unique assistant intake required")
    if next(i for i, row in enumerate(rows) if row.get("record_id") == stage["queue_record_id"]) >= next(
            i for i, row in enumerate(rows) if row.get("record_id") == stage["intake_record_id"]):
        raise w.WorkflowError("queue must precede the actual assistant intake")
    return {"prior_pass_receipt_id": stage["prior_pass_receipt_id"],
            "producer_outbox_receipt_id": stage["producer_outbox_receipt_id"],
            "queue_record_id": stage["queue_record_id"], "intake_record_id": stage["intake_record_id"]}


def reviewer_department(root: Path, snapshot: dict, *, preparation_only=False) -> str:
    snapshot = _review_context(root, snapshot)
    plan = load_plan(root, snapshot)
    return plan["reviewer_department"] if plan else (_goal_reviewer(root, snapshot, preparation_only=preparation_only) or "qa")


def _tnew_actual_bootstrap_context(root, snapshot, continuation_pin):
    """Authenticate the actual ordered chain through the permanent public consumer."""
    import paid_three_page_bounded_cms as b
    w = _workflow()
    _tnew_source_goal(root, snapshot)
    continuation = _review_source_document(root, continuation_pin)
    predecessors = continuation.get("predecessor_continuations")
    if (continuation.get("schema") != "flashcast-actual-source-bootstrap-successor/v1"
            or not isinstance(predecessors, list) or not predecessors
            or any(not isinstance(value, dict) or set(value) != {"path", "sha256", "size"} for value in predecessors)
            or len({value["path"] for value in predecessors}) != len(predecessors)
            or continuation_pin in predecessors):
        raise w.WorkflowError("one explicit actual bootstrap successor and ordered predecessor pins required")
    first = _review_source_document(root, predecessors[0])
    ordered = [*predecessors, continuation_pin]
    authenticated = b.authenticated_source_successions(root, ordered,
        predecessor_sources=first.get("predecessor_sources"), original_history_pin=first.get("original_history_continuation"))
    layers = authenticated.get("layers", [])
    last = layers[-1] if layers else {}
    if ([row.get("continuation_pin") for row in layers] != ordered
            or last.get("governance_model") != "independent_source_bootstrap"
            or last.get("task_id") != snapshot["task_id"] or last.get("scope") != snapshot["goal_delivery"]["authorized_scope"][0]):
        raise w.WorkflowError("current exact original actual bootstrap chain required")
    contract = _review_source_document(root, last.get("bootstrap_review_contract"))
    return authenticated, last, contract


def _tnew_bound_bootstrap_responsibility(root, snapshot, plan):
    """Resolve current source responsibility from actual adopted bytes only."""
    w = _workflow()
    if ("rework_of" in plan or any(key in plan for key in
            ("owner_direct_review", "native_multi_goal_review", "parent_initial_child_review", "review_delegation"))):
        raise w.WorkflowError("one explicit adopted source responsibility mode required")
    authenticated, last, contract = _tnew_actual_bootstrap_context(root, snapshot, plan.get("adopted_source_continuation"))
    if (plan.get("task_id") != snapshot["task_id"] or plan.get("scope") != last.get("scope")
            or plan.get("producer_department") != "system-development" or plan.get("reviewer_department") != "operations-assistant-2"
            or plan.get("reviewer_thread_id") != w.department_registry(root)["operations-assistant-2"]["chat_binding"]["task_id"]
            or plan.get("candidate_version") != last.get("candidate_version") or plan.get("candidate") != last.get("producer_pin")
            or plan.get("candidate_sha256") != plan.get("candidate", {}).get("sha256")
            or plan.get("original_goal_continuation_sources") != contract.get("original_goal_continuation_sources")):
        raise w.WorkflowError("exact current actually adopted plan/PP and original responsibility identity required")
    current = tnew_entry_bootstrap_responsibility(root, snapshot, last["manifest_pin"], last["bootstrap_review_contract"],
        assignment_backings=authenticated["source_backings"], assignment_fields=authenticated["field_effects"])
    return authenticated, last, contract, current


def _validate_tnew_adopted_source_continuation(root, snapshot, receipts, old_binding, plan):
    """A released real bootstrap successor, never a fabricated blocked verdict."""
    w = _workflow()
    goal = _tnew_source_goal(root, snapshot)
    if ("rework_of" in plan or any(key in plan for key in
            ("owner_direct_review", "native_multi_goal_review", "parent_initial_child_review", "review_delegation"))
            or any(row.get("receipt_type") == "qa_verdict" for row in receipts)):
        raise w.WorkflowError("adopted source continuation and formal verdict rework are separate admissions")
    continuation_pin = plan.get("adopted_source_continuation")
    authenticated, last, contract = _tnew_actual_bootstrap_context(root, snapshot, continuation_pin)
    contract_pin = last["bootstrap_review_contract"]
    if (last.get("candidate_version") != plan["candidate_version"] or last.get("producer_pin") != plan["candidate"]):
        raise w.WorkflowError("current exact original bootstrap adoption must bind this PP/version")
    if (contract.get("historical_review_plan") != old_binding.get("pin")
            or contract.get("producer_outbox") != plan["candidate"]
            or contract.get("candidate_manifest") != last.get("manifest_pin")
            or contract.get("normal_review_plan") is not None
            or contract.get("goal_contract") != snapshot["goal_contract"]
            or contract.get("human_authorization") != goal["authorization_pin"]
            or old_binding not in _bindings(root, snapshot)):
        raise w.WorkflowError("real previous immutable binding and plan-free bootstrap provenance required")
    old = load_plan(root, snapshot, old_binding)
    same = ("task_id", "action_id", "action_class", "scope", "producer_department", "reviewer_department",
        "reviewer_thread_id", "risk_level", "single_final_reviewer", "production_write_allowed", "external_permission_issued")
    if (old is None or any(old.get(key) != plan.get(key) for key in same)
            or plan["candidate_version"] == old["candidate_version"] or plan["candidate"]["path"] == old["candidate"]["path"]
            or plan["candidate"]["sha256"] == old["candidate"]["sha256"]):
        raise w.WorkflowError("source continuation must preserve original responsibility and use new exact producer bytes")
    changed, diff, methods = plan.get("changed_scope"), plan.get("evidence_diff"), plan.get("revalidation_methods")
    if (changed != [plan["scope"]] or plan["scope"] not in goal["authorized_scope"]
            or not isinstance(diff, dict) or diff.get("previous_candidate") != old["candidate"] or diff.get("candidate") != plan["candidate"]
            or not isinstance(diff.get("summary"), str) or not diff["summary"].strip()
            or not isinstance(methods, dict) or set(methods) != set(changed)
            or any(not isinstance(value, str) or not value.strip() for value in methods.values())
            or plan.get("original_goal_continuation_sources") != contract.get("original_goal_continuation_sources")):
        raise w.WorkflowError("exact original source continuation difference and revalidation required")
    manifest = _review_source_document(root, last["manifest_pin"])
    required = {"tools/qa_review_plan.py", "tools/paid_three_page_bounded_cms.py", "tools/workflow_control.py",
                "tools/goal_delivery_runtime.py", "tools/parent_initial_dispatch.py"}
    if (manifest.get("field_changes") != [] or {row.get("path") for row in manifest.get("files", [])} != required
            or len(manifest["files"]) != len(required)):
        raise w.WorkflowError("only actually adopted five-source zero-field entry may replace this binding")
    endpoint = {value["path"]: value for value in authenticated["endpoint"]}
    if any(endpoint.get(row["path"]) != {"path": row["path"], **row["after"]} for row in manifest["files"]):
        raise w.WorkflowError("current normal entry must equal its real adopted exact endpoint")
    # The shared helper uses actual complete receipts, original source windows,
    # physical authenticated backings and fields. It creates no normal plan.
    current = tnew_entry_bootstrap_responsibility(root, snapshot, last["manifest_pin"], contract_pin,
        assignment_backings=authenticated["source_backings"], assignment_fields=authenticated["field_effects"])
    if receipts != _strict_source_rows(root, snapshot["task_id"]):
        raise w.WorkflowError("complete original receipt chain changed during source continuation admission")
    return {"continuation_pin": continuation_pin, "bootstrap_review_contract": contract_pin,
        "historical_review_plan": old_binding["pin"], "producer_receipt_id": current["receipt_id"],
        "queue_record_id": current["queue_record_id"], "intake_record_id": current["intake_record_id"]}


def validate_plan(root: Path, snapshot: dict, plan: dict, *, transfer_from=None) -> None:
    w = _workflow()
    goal = _goal(root, snapshot)
    modern = goal is not None
    if "original_rotation_remaining_stage" in plan:
        if any(key in plan for key in ("rework_of", "adopted_source_continuation", "post_pass_remaining_stage",
                "owner_direct_review", "native_multi_goal_review", "parent_initial_child_review",
                "business_rework_successor", "original_parent_review_source")):
            raise w.WorkflowError("one exact original rotation remaining-stage admission required")
    if "adopted_source_continuation" in plan:
        _tnew_source_goal(root, snapshot)
        if "rework_of" in plan or any(key in plan for key in
                ("owner_direct_review", "native_multi_goal_review", "parent_initial_child_review", "review_delegation")):
            raise w.WorkflowError("one explicit adopted-source admission; formal rework remains separate")
        _review_source_document(root, plan["adopted_source_continuation"])
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
    exact_cms = (scope == CONDO_FAQ_ORIGINAL_CHILD_CHAIN["cms_scope"]
                 and snapshot.get("task_id") == CONDO_FAQ_ORIGINAL_CHILD_CHAIN["cms_task"]
                 and plan.get("action_id") == "publish-condo-faq-v7-current-native-20261014-v1"
                 and plan.get("action_class") == "cms_content_candidate"
                 and plan.get("candidate_version") == "publishing-condo-faq-v7-current-native-v1-20261014"
                 and plan.get("candidate_sha256") == "5a717a01629d62bf5fa161c4c377a0467439edf00c6d47143311dc3e755ee821"
                 and plan.get("candidate") == {
                     "path": "drafts/publishing/fc-20261014-condo-faq-v7-cms-publishing-v1/publishing-condo-v7-current-native-candidate-v1.json",
                     "sha256": "5a717a01629d62bf5fa161c4c377a0467439edf00c6d47143311dc3e755ee821",
                     "size": 16308}
                 and original_condo_faq_child_review_context(root, snapshot, plan=plan) is not None)
    if ((not modern and not scope.startswith("project:")) or scope.endswith((":", "/"))
            or any(c in scope for c in "*?[]|\n\r") or ("," in scope and not exact_cms)):
        raise w.WorkflowError("one exact project scope required")
    reviewer, producer = plan.get("reviewer_department"), plan.get("producer_department")
    registry = w.department_registry(root)
    planned = {row.get("department"): row for row in snapshot.get("departments", [])}
    if modern:
        allowed_reviewer = _goal_reviewer(root, snapshot, transfer_from=transfer_from)
        role_valid = (reviewer == allowed_reviewer and producer in goal["producer_departments"]
                      and not (set(planned) & {"qa", "qa-technical"}))
    else:
        role_valid = reviewer in {"qa", "qa-technical"} and set(planned) & {"qa", "qa-technical"} == {reviewer}
    if (not role_valid or producer not in registry
            or producer in {"qa", "qa-technical"} or producer == reviewer
            or reviewer not in registry or reviewer not in planned or producer not in planned
            ):
        raise w.WorkflowError("one known independent planned reviewer and producer required")
    if producer == "operations":
        _received_native_review_candidate(root, snapshot, plan)
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
    if "owner_direct_review" in plan:
        origin = prepare_owner_direct_review(root, snapshot, plan["owner_direct_review"])
        producer_pin = origin["proof"]["producer_outbox"]
        original = w.read_json(w.safe_path(root, producer_pin["path"]))
        if (origin["proof"]["producer_department"] != producer
                or not _producer_candidate_bound(root, plan, producer_pin, original)):
            raise w.WorkflowError("owner-direct review must bind the exact original producer candidate")
    if "native_multi_goal_review" in plan:
        if "owner_direct_review" in plan:
            raise w.WorkflowError("one original review source mode required")
        prepare_native_multi_goal_review(root, snapshot, plan["native_multi_goal_review"])
    if "parent_initial_child_review" in plan:
        if any(name in plan for name in ("owner_direct_review", "native_multi_goal_review", "review_delegation")):
            raise w.WorkflowError("one exact original child review source required")
        origin = _prepare_parent_initial_child_review(root, snapshot, plan["parent_initial_child_review"])
        producer_pin = origin["proof"]["producer_outbox"]
        original = w.read_json(w.safe_path(root, producer_pin["path"]))
        if (origin["proof"]["producer_department"] != producer
                or plan.get("action_class") != "read_only_candidate"
                or plan.get("risk_level") != "R0"
                or not _producer_candidate_bound(root, plan, producer_pin, original)):
            raise w.WorkflowError("child review must bind its exact read-only producer candidate/version/result")
    if "pre_admission_rework" in plan:
        from owner_adopted_pilot_consumer import admission_rework, _rows as adopted_pilot_rows
        admission_rework(root, snapshot, adopted_pilot_rows(root,snapshot['task_id']),
                         _binding(root,snapshot), plan)
    if "original_parent_review_source" in plan:
        if (any(name in plan for name in ("owner_direct_review", "native_multi_goal_review",
                                          "parent_initial_child_review", "review_delegation"))
                or next12_original_parent_review_context(root, snapshot, plan=plan) is None):
            raise w.WorkflowError("one exact original next12 parent/child reviewer source required")


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
        if ("original_rotation_remaining_stage" in plan
                and coordinator_role != _goal_reviewer(root, snapshot)):
            raise w.WorkflowError("only original assigned assistant binds this remaining completion stage")
        validate_plan(root, snapshot, plan)
        old = _binding(root, snapshot)
        binding = {"pin": pin, "reviewer_department": plan["reviewer_department"]}
        if "adopted_source_continuation" in plan:
            binding["adopted_source_continuation"] = plan["adopted_source_continuation"]
        if "post_pass_remaining_stage" in plan:
            binding["post_pass_remaining_stage"] = plan["post_pass_remaining_stage"]
        if "original_rotation_remaining_stage" in plan:
            binding["original_rotation_remaining_stage"] = plan["original_rotation_remaining_stage"]
        if "owner_direct_review" in plan:
            binding["owner_direct_review"] = plan["owner_direct_review"]
        if "native_multi_goal_review" in plan:
            binding["native_multi_goal_review"] = plan["native_multi_goal_review"]
        if "parent_initial_child_review" in plan:
            binding["parent_initial_child_review"] = plan["parent_initial_child_review"]
        if "original_parent_review_source" in plan:
            binding["original_parent_review_source"] = plan["original_parent_review_source"]
        if "business_rework_successor" in plan:
            binding["business_rework_successor"] = plan["business_rework_successor"]
        if "pre_admission_rework" in plan:
            binding["pre_admission_rework"] = plan["pre_admission_rework"]
        if modern:
            binding["goal_identity"] = {key: _goal(root, snapshot)[key] for key in GOAL_IDENTITY}
        if old is not None:
            if old.get('current_assignment_review_source') and _current_goal_assignment_round(root,snapshot,
                    w._validate_receipt_chain(root,task_id)[0],plan) is None:
                raise w.WorkflowError('frozen whole-goal reviewer assignment no longer valid')
            if old == binding or {k:v for k,v in old.items() if k not in {"review_delegation","current_assignment_review_source"}} == binding:
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
        if modern and not any(name in plan for name in ("native_multi_goal_review", "parent_initial_child_review")) and not any(r.get("department") == plan["reviewer_department"]
                              and r.get("receipt_type") in {"dispatch_sent", "dispatch_failed"} for r in receipts):
            from goal_delivery_runtime import review_delegation
            inherited = review_delegation(root, snapshot)
            if inherited:
                binding["review_delegation"] = inherited["binding"]
        review_history = [(i, r) for i, r in enumerate(receipts) if r.get("department") in
                          ({plan["reviewer_department"], "qa", "qa-technical"} if modern else {"qa", "qa-technical"})]
        if old is not None:
            if "pre_admission_rework" in plan:
                from owner_adopted_pilot_consumer import admission_rework
                admission_stage = admission_rework(root, snapshot, receipts, old, plan)
            elif "adopted_source_continuation" in plan:
                source_continuation = _validate_tnew_adopted_source_continuation(root, snapshot, receipts, old, plan)
            elif "post_pass_remaining_stage" in plan:
                remaining_stage = _validate_post_pass_remaining_stage(root, snapshot, receipts, old, plan)
            elif "original_rotation_remaining_stage" in plan:
                from rotation_completion import remaining_review_stage
                rotation_stage = remaining_review_stage(root, snapshot, receipts, old, plan)
            elif "business_rework_successor" in plan:
                business_successor = _validate_next12_business_rework_successor(root, snapshot, receipts, old, plan)
            else:
                original_pre_verdict = _validate_rework(root, snapshot, receipts, old, plan)
        elif "adopted_source_continuation" in plan:
            raise w.WorkflowError("actual previous immutable source binding required")
        elif "business_rework_successor" in plan:
            raise w.WorkflowError("original frozen next12 V1 plan required")
        elif "original_rotation_remaining_stage" in plan:
            raise w.WorkflowError("original rotation prior PASS binding required")
        elif plan.get("rework_of"):
            raise w.WorkflowError("original frozen plan required for rework")
        elif review_history:
            if (not modern or _assigned_review_round(root, snapshot, receipts, plan) is None
                    or any(r.get("receipt_type") == "qa_verdict" for _, r in review_history)):
                raise w.WorkflowError("cannot change reviewer after QA dispatch or history")
        ordinary=_current_goal_assignment_round(root,snapshot,receipts,plan)
        if ordinary is not None:
            binding['current_assignment_review_source']=ordinary['current_assignment_review_source']
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
            details.update(qa_review_plan_history=history, old_verdict_migrated=False)
            if "pre_admission_rework" in plan:
                details["pre_admission_rework"] = admission_stage
            elif "adopted_source_continuation" in plan:
                details["adopted_source_continuation"] = source_continuation
            elif "post_pass_remaining_stage" in plan:
                details["post_pass_remaining_stage"] = remaining_stage
            elif "original_rotation_remaining_stage" in plan:
                details["original_rotation_remaining_stage"] = rotation_stage
            elif "business_rework_successor" in plan:
                details["business_rework_successor"] = business_successor
            elif original_pre_verdict:
                details["original_pre_verdict_successor"] = original_pre_verdict
            else:
                details["rework_of"] = plan["rework_of"]
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
    from technical_review_backup import review_capable
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
    if (target_role == previous or not review_capable(root, previous, goal, task_id=task_id)
            or not review_capable(root, target_role, goal, task_id=task_id, transfer_from=previous)):
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
    validate_plan(root, target_snapshot, new, transfer_from=previous)
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


_ORIGINAL_CAUSAL_PRODUCER_ACK = {
    "task_id": "fc-20261015-industry-keywords-site-coverage-plan-v1",
    "dispatch_receipt_id": "4a9d7ec9-254f-478b-8275-cf940a75eac5",
    "ack_receipt_id": "648c70be-a1c6-466d-b1f4-c98b707713a3",
    "receipt_snapshot": {
        "path": "logs/handoffs/2026-10-15-industry-keywords-site-coverage-plan-v1/department3-real-nonempty-ACK-receipt.json",
        "sha256": "b8e6e050776e6495eb9250632f6017aa705b1944b5344e0c8c762222b3489162",
        "size": 1279,
    },
}


def _historical_blocked_self_outbox_round(root, snapshot, receipts, box, plan,
                                          producer, producer_pin, producer_index):
    """Authenticate the original result/review prefix before later rework."""
    w = _workflow()
    if (plan is None or plan.get("candidate") != producer_pin
            or box.get("qa_verdict") != "blocked"
            or box.get("candidate_version") != plan.get("candidate_version")
            or not isinstance(box.get("evidence"), list)
            or snapshot.get("task_id") != _ORIGINAL_CAUSAL_PRODUCER_ACK["task_id"]):
        return False
    later = [(i, row) for i, row in enumerate(receipts)
             if i > producer_index and row.get("department") == producer
             and row.get("receipt_type") in {"dispatch_sent", "dispatch_failed"}]
    if not later:
        return False
    fixed = w.department_registry(root)[producer]["chat_binding"]
    dispatches = [(i, row) for i, row in enumerate(receipts[:producer_index])
                  if row.get("department") == producer
                  and row.get("receipt_type") in {"dispatch_sent", "dispatch_failed"}]
    if not dispatches or dispatches[-1][1].get("receipt_type") != "dispatch_sent":
        return False
    dispatch_index, dispatch = dispatches[-1]
    if (dispatch.get("task_id") != snapshot["task_id"]
            or dispatch.get("receipt_id") != _ORIGINAL_CAUSAL_PRODUCER_ACK["dispatch_receipt_id"]
            or dispatch.get("chat_task_id") != fixed["task_id"]
            or dispatch.get("action_class") != "thread_message"
            or dispatch.get("scope") != plan["scope"]
            or not dispatch.get("action_id")
            or not dispatch.get("policy_decision_id")
            or not dispatch.get("evidence")):
        return False
    acks = [(i, row) for i, row in enumerate(receipts)
            if dispatch_index < i < producer_index
            and row.get("department") == producer
            and row.get("receipt_type") == "chat_ack"]
    if (len(acks) != 1 or acks[0][1].get("receipt_id") != _ORIGINAL_CAUSAL_PRODUCER_ACK["ack_receipt_id"]
            or acks[0][1].get("ack_nonempty") is not True
            or any(acks[0][1].get(key) != dispatch.get(key) for key in
                   ("task_id", "department", "chat_task_id", "action_id", "action_class", "scope"))
            or acks[0][1].get("policy_decision_id") not in {"", dispatch["policy_decision_id"]}
            or acks[0][1].get("approval_id") != dispatch.get("approval_id")
            or not acks[0][1].get("evidence")
            or any(row.get("supersedes_receipt_id") in
                   {dispatch.get("receipt_id"), acks[0][1].get("receipt_id")}
                   for row in receipts)):
        return False
    try:
        archive_pin = _ORIGINAL_CAUSAL_PRODUCER_ACK["receipt_snapshot"]
        if w.file_digest(root, archive_pin["path"]) != archive_pin:
            return False
        archived = w.read_json(w.safe_path(root, archive_pin["path"]))
        if (not isinstance(archived, dict)
                or {key: archived.get(key) for key in acks[0][1]} != acks[0][1]
                or set(archived) - set(acks[0][1]) != {"result", "workflow_state"}):
            return False
        for pin in (*dispatch.get("evidence", []), *acks[0][1].get("evidence", [])):
            if w.file_digest(root, pin.get("path", "")) != pin:
                return False
        dispatch_sources = [w.read_json(w.safe_path(root, pin["path"]))
                            for pin in dispatch["evidence"] if pin["path"].endswith(".json")]
        wrappers = [item for item in dispatch_sources if isinstance(item, dict)
                    and item.get("actual_thread_id") == fixed["task_id"]
                    and isinstance(item.get("exact_consumed_prompt"), dict)
                    and isinstance(item.get("raw_tool_return"), dict)]
        if len(wrappers) != 1:
            return False
        wrapper = wrappers[0]
        prompt_pin = wrapper["exact_consumed_prompt"]
        if (prompt_pin not in dispatch["evidence"]
                or w.file_digest(root, prompt_pin["path"]) != prompt_pin):
            return False
        prompt = w.safe_path(root, prompt_pin["path"]).read_text(encoding="utf-8")
        native_sends = [item for source in dispatch_sources if isinstance(source, dict)
                        and source.get("thread", {}).get("id") != fixed["task_id"]
                        for turn in source.get("turns", [])
                        for item in turn.get("items", [])
                        if item.get("type") == "mcpToolCall"
                        and item.get("tool") == "send_message_to_thread"
                        and item.get("status") == "completed"
                        and item.get("arguments", {}).get("threadId") == fixed["task_id"]
                        and item.get("arguments", {}).get("prompt") == prompt]
        returned = wrapper["raw_tool_return"]
        replies = [json.loads(item.get("text", "")) for item in returned.get("content", [])
                   if item.get("type") == "text"]
        if (len(native_sends) != 1 or returned.get("isError") is not False
                or replies != [{"threadId": fixed["task_id"]}]
                or snapshot["task_id"] not in prompt or plan["scope"] not in prompt):
            return False
        policies = [row for row in w.read_jsonl(root / w.POLICY_DECISIONS)
                    if row.get("decision_id") == dispatch["policy_decision_id"]]
        if len(policies) != 1 or any(policies[0].get(key) != value for key, value in (
                ("status", "allow"), ("routing_status", "routing_allowed"),
                ("task_id", snapshot["task_id"]), ("action_id", dispatch["action_id"]),
                ("action_class", dispatch["action_class"]), ("scope", dispatch["scope"]),
                ("target_department", producer), ("target_thread_id", fixed["task_id"]),
                ("target_project_id", fixed["project_id"]),
                ("payload_sha256", prompt_pin["sha256"]))):
            return False
        ack_sources = [w.read_json(w.safe_path(root, pin["path"]))
                       for pin in acks[0][1]["evidence"] if pin["path"].endswith(".json")]
        ack_at = w._parse_observed_at(acks[0][1].get("created_at"))
        if not any(source.get("timedOut") is True
                   and source.get("wake") is None
                   and any(poll.get("schemaVersion") == 1
                           and poll.get("thread", {}).get("id") == fixed["task_id"]
                           and poll.get("thread", {}).get("hostId") == fixed["host_id"]
                           and isinstance(poll.get("cursor"), str) and poll["cursor"]
                           and type(poll.get("revision")) is int and poll["revision"] > 0
                           and poll.get("latestTurn", {}).get("id") == poll.get("latestAssistantMessage", {}).get("turnId")
                           and poll.get("latestAssistantMessage", {}).get("phase") in {"commentary", "final_answer"}
                           and poll.get("latestAssistantMessage", {}).get("text", "").strip()
                           and poll.get("latestAssistantMessageId") == poll["latestAssistantMessage"].get("id")
                           and ack_at is not None
                           and type(poll.get("latestTurn", {}).get("startedAt")) in {int, float}
                           and poll["latestTurn"]["startedAt"] <= ack_at.timestamp()
                           for poll in source.get("polls", []))
                   for source in ack_sources if isinstance(source, dict)):
            return False
    except (w.WorkflowError, OSError, ValueError, TypeError, KeyError, AttributeError):
        return False
    reviewer = plan["reviewer_department"]
    original = [(i, row, pin) for i, row in enumerate(receipts)
                if producer_index < i < later[0][0]
                and row.get("department") == reviewer
                and row.get("receipt_type") == "outbox_received"
                for pin in row.get("evidence", [])
                if pin in box.get("evidence", []) and str(pin.get("path", "")).endswith(".json")]
    if len(original) != 1:
        return False
    original_index, original_receipt, original_pin = original[0]
    if w.file_digest(root, original_pin["path"]) != original_pin:
        return False
    original_box = w.read_json(w.safe_path(root, original_pin["path"]))
    if not isinstance(original_box, dict):
        return False
    if any(original_box.get(key) != box.get(key) for key in
           ("task_id", "department", "candidate_version", "qa_verdict",
            "review_identity", "goal_acceptance", "conclusion")):
        return False
    identity = (snapshot["task_id"], producer, plan["candidate_version"], producer_pin["sha256"])
    handoffs = w._result_handoff_rows(root, snapshot["task_id"])
    queued = [row for row in handoffs if row.get("event") == "notification_queued"
              and tuple(row.get(key) for key in
                        ("task_id", "sender_department", "candidate_version", "result_sha256")) == identity
              and row.get("outbox") == producer_pin]
    received = [row for row in handoffs if row.get("event") == "controller_received"
                and tuple(row.get(key) for key in
                          ("task_id", "sender_department", "candidate_version", "result_sha256")) == identity
                and row.get("outbox") == producer_pin and row.get("intake_mode") == "queue"]
    if len(queued) != 1 or len(received) != 1:
        return False
    source, intake = queued[0], received[0]
    if (source.get("result_source_phase") != "delivery_ready"
            or source.get("batch_delivery_frozen") is not True
            or source.get("source_thread_id") != fixed["task_id"]
            or any(intake.get(key) != source.get(key) for key in
                   ("source_thread_id", "source_turn_id", "source_message_id", "source_reply_sha256"))):
        return False
    from result_coordination import _knowledge_native_reply
    try:
        _knowledge_native_reply(root, source, fixed, completed=False)
    except (w.WorkflowError, OSError, ValueError, TypeError, KeyError):
        return False
    times = [w._parse_observed_at(row.get("created_at")) for row in
             (dispatch, acks[0][1], source, intake, receipts[producer_index], original_receipt, later[0][1])]
    return all(times) and times == sorted(times) and original_index < later[0][0]


def _validate_goal_acceptance(root, snapshot, receipts, box, verdict, *, source_pins=None, plan=None):
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
    plan = load_plan(root, snapshot) if plan is None else plan
    if source_pins is None:
        source_pins = _candidate_review_source_pins(root, snapshot, plan) if plan else []
    for producer in goal["producer_departments"]:
        boxes = [(i, row) for i, row in enumerate(receipts)
                 if row.get("department") == producer and row.get("receipt_type") == "outbox_received"]
        if not boxes:
            raise w.WorkflowError("complete goal producer result missing")
        historical = verdict == "blocked" and plan is not None and plan.get("candidate") == pins[producer]
        if historical:
            boxes = [(i, row) for i, row in boxes if pins[producer] in row.get("evidence", [])]
            if len(boxes) != 1:
                raise w.WorkflowError("one exact historical producer outbox receipt required")
        box_index, receipt = boxes[-1]
        pin = next((p for p in receipt.get("evidence", []) if p.get("path", "").endswith(".json")), None)
        if pin is None or pins[producer] != pin or w.file_digest(root, pin["path"]) != pin:
            raise w.WorkflowError("complete goal producer current result bytes differ")
        if producer == "operations":
            bound_plan = plan
            if (bound_plan is not None and bound_plan.get("producer_department") == producer
                    and bound_plan.get("action_class") == "runtime_control"):
                if (bound_plan.get("task_id") != snapshot["task_id"] or bound_plan.get("scope") != goal["authorized_scope"][0]
                        or bound_plan.get("candidate") != pin or bound_plan.get("candidate_sha256") != pin["sha256"]):
                    raise w.WorkflowError("whole native result must preserve the exact frozen bound plan candidate")
                _received_native_review_candidate(root, snapshot, bound_plan)
            else:
                from native_control_result import received_candidate
                received_candidate(root, snapshot, {"producer_department": producer, "action_class": "runtime_control",
                                                    "scope": goal["authorized_scope"][0], "candidate": pin}, receipts, require_intake=True)
            continue
        # A late historical BLOCKED verdict may use only its authenticated
        # producer/reviewer source prefix, never an arbitrary earlier round.
        historical_blocked = (historical and _historical_blocked_self_outbox_round(
            root, snapshot, receipts, box, plan, producer, pin, box_index))
        dispatches = [i for i, row in enumerate(receipts) if row.get("department") == producer
                      and row.get("receipt_type") in {"dispatch_sent", "dispatch_failed"}
                      and (not historical_blocked or i < box_index)
                      and not (plan and plan.get("producer_department") == producer
                               and _same_original_source_notice(root, snapshot, receipts, row, plan,
                                                               source_pins=source_pins, producer=True))]
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


def _original_owner_direct_authority_notice(root, snapshot, binding, plan, receipts, dispatch):
    """Recognize one original notice without inventing a review round or grant.

    The enclosing load_plan already validates the full owner-direct origin. Do
    not re-enter load_plan, validate_plan or the full receipt consumer here.
    """
    w = _workflow()
    source = _ORIGINAL_OWNER_DIRECT_AUTHORITY_NOTICE
    if (snapshot.get("task_id") != source["task_id"]
            or dispatch.get("receipt_id") != source["dispatch_receipt_id"]):
        return False

    def unique_fields(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate original authority notice source field")
            result[key] = value
        return result

    def document(pin):
        if (not isinstance(pin, dict) or set(pin) != {"path", "sha256", "size"}
                or w.file_digest(root, pin.get("path", "")) != pin):
            raise ValueError("original authority notice source bytes changed")
        value = json.loads(w.safe_path(root, pin["path"]).read_bytes(), object_pairs_hook=unique_fields)
        if not isinstance(value, dict):
            raise ValueError("original authority notice source object required")
        return value

    try:
        goal = snapshot.get("goal_delivery", {})
        role, producer, scope = source["reviewer_department"], source["producer_department"], source["scope"]
        proof = plan.get("owner_direct_review")
        if (not isinstance(goal, dict) or not isinstance(proof, dict)
                or goal.get("source_mode") != "owner_direct" or goal.get("responsible_assistant") != role
                or goal.get("primary_owner") != producer or goal.get("producer_departments") != [producer]
                or goal.get("acceptance_capability") != source["acceptance_capability"]
                or scope not in goal.get("authorized_scope", [])
                or any(plan.get(key) != value for key, value in
                       (("task_id", source["task_id"]), ("reviewer_department", role),
                        ("producer_department", producer), ("scope", scope)))
                or binding.get("owner_direct_review") != proof
                or binding.get("reviewer_department") != role
                or binding.get("goal_identity") != {key: goal[key] for key in GOAL_IDENTITY}
                or document(binding.get("pin")) != plan
                or goal.get("authorization_pin") != source["authority"]
                or snapshot.get("goal_contract") != source["goal_contract"]
                or proof.get("authority") != source["authority"]
                or proof.get("goal_contract") != source["goal_contract"]
                or any(proof.get(key) != value for key, value in
                       (("schema_version", 1), ("task_id", source["task_id"]),
                        ("responsible_assistant", role), ("producer_department", producer), ("scope", scope)))):
            return False
        document(source["authority"])
        contract = document(source["goal_contract"])
        contract = contract.get("goal_delivery", contract)
        identity = GOAL_IDENTITY + ("source_mode", "parent_task_id", "coordination_origin_parent_task_id",
                                    "human_authorization", "required_execution_actions")
        if any(contract.get(key) != goal.get(key) for key in identity):
            return False
        for key in ("original_handoff", "producer_outbox", "producer_native_send", "producer_native_received",
                    "producer_native_input", "producer_send_attempt", "reviewer_native_responsibility",
                    "reviewer_responsibility_input", "reviewer_source_outbox", "reviewer_native_reply"):
            pin = proof.get(key)
            if not isinstance(pin, dict) or w.file_digest(root, pin.get("path", "")) != pin:
                return False
        fixed = w.department_registry(root)
        _owner_direct_responsibility(root, snapshot, goal, proof, fixed)
        target, sender = fixed[role]["chat_binding"], fixed["operations"]["chat_binding"]
        if plan.get("reviewer_thread_id") != target.get("task_id"):
            return False

        raw_rows, previous = [], ""
        for line in w.receipts_path(root, source["task_id"]).read_text(encoding="utf-8").splitlines():
            row = json.loads(line, object_pairs_hook=unique_fields)
            if (not isinstance(row, dict) or row.get("task_id") != source["task_id"]
                    or row.get("previous_hash") != previous
                    or row.get("receipt_hash") != w.sha256_value(w._receipt_payload_for_hash(row))):
                return False
            previous = row["receipt_hash"]
            raw_rows.append(row)
        sent = [row for row in raw_rows if row.get("receipt_id") == source["dispatch_receipt_id"]]
        acks = [row for row in raw_rows if row.get("receipt_id") == source["ack_receipt_id"]]
        if (sent != [dispatch] or len(acks) != 1 or dispatch not in receipts or acks[0] not in receipts
                or dispatch.get("receipt_hash") != source["dispatch_receipt_hash"]
                or acks[0].get("receipt_hash") != source["ack_receipt_hash"]
                or any(row.get("supersedes_receipt_id") == source["dispatch_receipt_id"] for row in raw_rows)):
            return False
        ack = acks[0]
        shared = {"task_id": source["task_id"], "department": role, "chat_task_id": target.get("task_id"),
                  "action_id": source["action_id"], "action_class": "thread_message", "scope": scope,
                  "policy_decision_id": source["policy_decision_id"], "supersedes_receipt_id": "",
                  "replacement_reason": "", "approval_id": ""}
        if (any(row.get(key) != value for row in (dispatch, ack) for key, value in shared.items())
                or dispatch.get("receipt_type") != "dispatch_sent" or ack.get("receipt_type") != "chat_ack"
                or ack.get("ack_nonempty") is not True or dispatch.get("evidence") != [source["payload"]]
                or ack.get("evidence") != [source["native_ack"]]):
            return False
        payload = source["payload"]
        if w.file_digest(root, payload["path"]) != payload:
            return False
        native = document(source["native_send"])
        # This legacy normalized source really has no tool/time/project fields.
        # Exact frozen bytes plus its original policy are the source; do not
        # reinterpret arbitrary actual_native_send wrappers as this notice.
        if (any(native.get(key) != value for key, value in
                (("task_id", source["task_id"]), ("action_id", source["action_id"]), ("sender", "operations"),
                 ("receiver", role), ("dispatch_receipt_id", source["dispatch_receipt_id"]),
                 ("policy_decision_id", source["policy_decision_id"]), ("payload", payload)))
                or native.get("actual_native_send") != {"threadId": target.get("task_id")}
                or any(native.get(key) is not False for key in
                       ("is_new_professional_task", "new_review_responsibility_task_sent",
                        "is_answer_impersonating_human", "new_account_or_platform_permission"))):
            return False
        native_ack = document(source["native_ack"])
        reply = native_ack.get("reply", {})
        if (any(native_ack.get(key) != value for key, value in
                (("task_id", source["task_id"]), ("action_id", source["action_id"]),
                 ("notice_dispatch_receipt_id", source["dispatch_receipt_id"]),
                 ("fixed_chat_task_id", target.get("task_id"))))
                or native_ack.get("ack_nonempty") is not True
                or native_ack.get("is_candidate_result") is not False
                or native_ack.get("is_human_new_permission") is not False
                or native_ack.get("actual_Save_or_deploy_confirmed") is not False
                or not isinstance(reply, dict) or not reply.get("id") or not native_ack.get("native_turn_id")
                or reply.get("turnId") != native_ack["native_turn_id"]
                or reply.get("phase") not in {"commentary", "final_answer"}
                or not isinstance(reply.get("text"), str) or not reply["text"].strip()):
            return False
        policy = document(source["policy_row"])
        policies = [json.loads(line, object_pairs_hook=unique_fields)
                    for line in (Path(root) / w.POLICY_DECISIONS).read_text(encoding="utf-8").splitlines()]
        if (any(not isinstance(row, dict) for row in policies)
                or [row for row in policies if row.get("decision_id") == source["policy_decision_id"]] != [policy]):
            return False
        expected_policy = {"status": "allow", "routing_status": "routing_allowed", "task_id": source["task_id"],
            "department": "operations", "action_id": source["action_id"], "action_class": "thread_message",
            "scope": scope, "payload_sha256": payload["sha256"], "target_department": role,
            "target_thread_id": target.get("task_id"), "target_thread_title": target.get("title"),
            "target_cwd": target.get("cwd"), "target_project_id": target.get("project_id"),
            "source_project_id": sender.get("project_id"), "target_sidebar_section_id": target.get("sidebar_section_id")}
        if any(policy.get(key) != value for key, value in expected_policy.items()):
            return False
        stamps = [w._parse_observed_at(value) for value in
                  (policy.get("checked_at"), dispatch.get("created_at"), ack.get("created_at"))]
        return (all(value is not None for value in stamps)
                and stamps[0] <= stamps[1] <= stamps[2] <= dt.datetime.now(dt.timezone.utc))
    except (OSError, ValueError, TypeError, KeyError, w.WorkflowError):
        return False


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
    source_pins = _verdict_review_source_pins(root, snapshot, receipts, receipt, binding, plan)
    indices = [(i, r) for i, r in enumerate(receipts)
               if r.get("department") == reviewer and r.get("receipt_type") in {"dispatch_sent", "dispatch_failed"}
               and not _original_owner_direct_authority_notice(root, snapshot, binding, plan, receipts, r)]
    inherited = None
    direct = None
    native = None
    inherited_child = None
    adopted_parent = None
    if "parent_initial_child_review" in plan:
        if binding.get("parent_initial_child_review") != plan["parent_initial_child_review"]:
            raise w.WorkflowError("bound original parent-linked child source changed")
        inherited_child = _assigned_review_round(root, snapshot, receipts, plan, source_pins=source_pins)
        if inherited_child is None:
            raise w.WorkflowError("original independent parent-linked child review source required")
        initial_assignment = True
        boxes = [row for row in receipts if row.get("department") == reviewer
                 and row.get("receipt_type") == "outbox_received"]
    elif "native_multi_goal_review" in plan:
        if binding.get("native_multi_goal_review") != plan["native_multi_goal_review"]:
            raise w.WorkflowError("bound original native multi-goal review source changed")
        native = _assigned_review_round(root, snapshot, receipts, plan, source_pins=source_pins)
        if native is None:
            raise w.WorkflowError("current original multi-goal reviewer round required")
        dispatch, ack = native["dispatch"], native["ack"]
        initial_assignment = True
        # F4 has no reviewer dispatch of its own: the source stays the TO send,
        # while the verdict and result remain bound only to the F4 goal.
        start = native["ack_index"] if native["source_task_id"] == snapshot["task_id"] else -1
        boxes = [r for r in receipts[start + 1:] if r.get("department") == reviewer
                 and r.get("receipt_type") == "outbox_received"]
    elif not indices:
        from goal_delivery_runtime import review_delegation
        inherited = review_delegation(root, snapshot)
        if inherited:
            if binding.get("review_delegation") != inherited["binding"]:
                raise w.WorkflowError("latest actual reviewer dispatch required, or exact inherited delegation")
            dispatch, ack = inherited["dispatch"], inherited["ack"]
        else:
            from owner_adopted_pilot_consumer import review_context as adopted_pilot_review
            adopted_parent = adopted_pilot_review(root, snapshot, receipts, plan)
            direct = None if adopted_parent else owner_direct_review_context(root, snapshot, binding)
            if direct is None and adopted_parent is None:
                original_child = (original_condo_faq_child_review_context(root, snapshot, receipts, plan)
                                  or next12_original_parent_review_context(root, snapshot, receipts, plan))
                if original_child is None:
                    raise w.WorkflowError("latest actual reviewer dispatch required, or exact inherited delegation/original owner-direct proof")
                dispatch, ack = original_child["dispatch"], original_child["ack"]
        initial_assignment = True
        boxes = [r for r in receipts if r.get("department") == reviewer and r.get("receipt_type") == "outbox_received"]
    else:
        if not indices or indices[-1][1].get("receipt_type") != "dispatch_sent":
            raise w.WorkflowError("latest actual reviewer dispatch required")
        index, dispatch = indices[-1]
        resumed = _assigned_review_round(root, snapshot, receipts, plan, source_pins=source_pins)
        strict_candidate_dispatch = (binding["pin"] in dispatch.get("evidence", [])
                                     and plan["candidate"] in dispatch.get("evidence", [])
                                     and dispatch.get("scope") == plan["scope"])
        initial_assignment = resumed is not None
        initial_history = any(r.get("department") == reviewer
                              and r.get("receipt_type") in {"dispatch_sent", "dispatch_failed"}
                              and r.get("action_id") == "assign-goal-review:" + snapshot["task_id"]
                              for r in receipts)
        if initial_history and resumed is None:
            raise w.WorkflowError("original single responsibility dispatch/ACK window required")
        if (not (initial_assignment or strict_candidate_dispatch)
                or dispatch.get("chat_task_id") != plan["reviewer_thread_id"]):
            raise w.WorkflowError("dispatch must freeze exact plan/candidate/scope")
        if resumed is not None and not strict_candidate_dispatch:
            index, dispatch = resumed["dispatch_index"], resumed["dispatch"]
            ack_index, ack = resumed["ack_index"], resumed["ack"]
        else:
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
    if receipt.get("verdict") == "blocked":
        historical_boxes = [row for row in boxes
                            if any(pin in receipt.get("evidence", [])
                                   for pin in row.get("evidence", [])
                                   if pin.get("path", "").endswith(".json"))]
        if historical_boxes:
            if len(historical_boxes) != 1:
                raise w.WorkflowError("one exact historical reviewer outbox required")
            boxes = historical_boxes
    now = dt.datetime.now(dt.timezone.utc)
    source = adopted_parent or direct or inherited_child
    stamp_values = ([source["reviewer_source_created_at"], boxes[-1].get("created_at"), receipt.get("created_at")]
                    if source else [r.get("created_at") for r in (dispatch, ack, boxes[-1], receipt)])
    stamps = [w._parse_observed_at(value) for value in stamp_values]
    if any(x is None for x in stamps) or stamps != sorted(stamps) or stamps[-1] > now:
        raise w.WorkflowError("actual reviewer timestamps must be ordered and not future")
    pin = next((p for p in boxes[-1].get("evidence", []) if p.get("path", "").endswith(".json")), None)
    if pin is None or pin not in receipt.get("evidence", []) or w.file_digest(root, pin["path"]) != pin:
        raise w.WorkflowError("verdict must reference current exact reviewer outbox bytes")
    box = w.read_json(w.safe_path(root, pin["path"]))
    w.validate_outbox(root, [pin], reviewer, plan["task_id"])
    if (initial_assignment or plan.get("rework_of") or plan.get("business_rework_successor")) and (binding["pin"] not in box.get("evidence", []) or plan["candidate"] not in box.get("evidence", [])):
        raise w.WorkflowError("initially assigned assistant final outbox must freeze the actual review plan and candidate")
    if (plan.get("rework_of") or plan.get("business_rework_successor")) and box.get("revalidation") != {"changed_scope": plan["changed_scope"], "methods": plan["revalidation_methods"]}:
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
    if direct and box.get("owner_direct_review") != direct["proof"]:
        raise w.WorkflowError("final reviewer outbox must declare the exact original owner-direct proof")
    if native and box.get("native_multi_goal_review") != native["native_multi_goal_review"]:
        raise w.WorkflowError("final reviewer outbox must declare the exact original multi-goal source")
    if inherited_child and box.get("parent_initial_child_review") != inherited_child["proof"]:
        raise w.WorkflowError("final child reviewer outbox must declare the exact original first-send source")
    if "original_parent_review_source" in plan:
        if (binding.get("original_parent_review_source") != plan["original_parent_review_source"]
                or box.get("original_parent_review_source") != plan["original_parent_review_source"]):
            raise w.WorkflowError("final reviewer outbox must declare exact original parent responsibility")
    if "business_rework_successor" in plan:
        if (binding.get("business_rework_successor") != plan["business_rework_successor"]
                or box.get("business_rework_successor") != plan["business_rework_successor"]):
            raise w.WorkflowError("final reviewer outbox must declare exact unverdicted business successor")
    historical_acceptance = box.get("goal_acceptance")
    historical_results = (historical_acceptance.get("producer_results")
                          if isinstance(historical_acceptance, dict) else None)
    if (receipt.get("verdict") == "blocked" and isinstance(historical_results, dict)
            and plan.get("candidate") == historical_results.get(plan["producer_department"])):
        original_index = receipts.index(boxes[-1])
        current_binding = _binding(root, snapshot)
        current_plan = load_plan(root, snapshot, current_binding) if current_binding != binding else plan
        for later in receipts[original_index + 1:]:
            if later.get("department") != reviewer or later.get("receipt_type") not in {"dispatch_sent", "dispatch_failed"}:
                continue
            successor_bound = (current_binding != binding
                               and current_binding["pin"] in later.get("evidence", [])
                               and current_plan["candidate"] in later.get("evidence", [])
                               and later.get("chat_task_id") == current_plan["reviewer_thread_id"]
                               and later.get("scope") == current_plan["scope"])
            if not (successor_bound or _same_goal_rework_notice(root, snapshot, receipts, later, current_plan)
                    or _same_goal_functional_result_notice(root, snapshot, receipts, later, current_plan)):
                raise w.WorkflowError("later reviewer dispatch must retain its own authenticated round")
    _validate_goal_acceptance(root, snapshot, receipts, box, receipt.get("verdict"),
                              source_pins=source_pins, plan=plan)
    if plan.get("producer_department") == "operations":
        from native_control_result import independent_verdict
        independent_verdict(root, snapshot, plan, binding, box, receipt, pin)
    if (snapshot.get("task_id") == "fc-20261010-system-flow-throughput-and-ledger-close-v1"
            and receipt.get("verdict") == "pass"):
        from scoped_candidate_adoption import validate_final_goal_pass
        validate_final_goal_pass(root, snapshot, box)
    producer_boxes = [r for r in receipts if r.get("department") == plan["producer_department"]
                      and r.get("receipt_type") == "outbox_received"]
    if not producer_boxes:
        raise w.WorkflowError("original producer outbox required")
    if (receipt.get("verdict") == "blocked" and plan.get("candidate") in
            [pin for row in producer_boxes for pin in row.get("evidence", [])]):
        producer_boxes = [row for row in producer_boxes if plan["candidate"] in row.get("evidence", [])]
        if len(producer_boxes) != 1:
            raise w.WorkflowError("one exact historical producer result required")
    producer_pin = next((p for p in producer_boxes[-1].get("evidence", []) if p.get("path", "").endswith(".json")), None)
    producer = w.read_json(w.safe_path(root, producer_pin["path"])) if producer_pin else {}
    if producer.get("candidate_version") != plan["candidate_version"] or not _producer_candidate_bound(root, plan, producer_pin, producer):
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
