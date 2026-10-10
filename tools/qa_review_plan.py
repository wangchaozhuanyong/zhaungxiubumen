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


def _goal_reviewer(root, snapshot, *, transfer_from=None):
    from result_coordination import coordinator_roles
    from technical_review_backup import review_capable
    w = _workflow()
    goal = _goal(root, snapshot)
    if goal is None:
        return None
    reviewer = goal.get("responsible_assistant")
    producers = goal.get("producer_departments", [])
    if (reviewer == "operations" or reviewer not in coordinator_roles(root)
            or not isinstance(producers, list) or not producers or reviewer in producers
            or not isinstance(goal.get("acceptance_capability"), str)
            or not review_capable(root, reviewer, goal, task_id=snapshot.get("task_id"), transfer_from=transfer_from)):
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


def _initial_assignment(root, snapshot, dispatch, native_proof=None):
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
            and pin in dispatch.get("evidence", []))


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
    # A real original V2 outbox is itself a complete immutable candidate identity.
    # Its evidence cannot contain its own final hash; no synthetic adapter needed.
    return (isinstance(producer_pin, dict)
            and w.file_digest(root, producer_pin.get("path", "")) == producer_pin
            and producer.get("schema_version") == "2.0"
            and producer.get("task_id") == plan.get("task_id")
            and producer.get("department") == plan.get("producer_department")
            and producer.get("candidate_version") == plan.get("candidate_version")
            and producer.get("fixed_chat_task_id") == w.department_registry(root).get(
                plan.get("producer_department"), {}).get("chat_binding", {}).get("task_id")
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


def _owner_direct_responsibility(root, snapshot, goal, proof, registry):
    """Use the real original receipt and current complete goal, never a new grant."""
    w = _workflow()
    reviewer, producer = goal["responsible_assistant"], proof["producer_department"]
    if proof.get("scope") != goal["human_authorization"]["scope"]:
        raise w.WorkflowError("original owner-direct exact task/scope required")
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
    send = _native_document(root, proof["producer_native_send"])
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
    from parent_initial_child_review import prepare
    return prepare(root, snapshot, proof)


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
    if "parent_initial_child_review" in plan:
        from parent_initial_child_review import prepare
        inherited_child = prepare(root, snapshot, plan["parent_initial_child_review"])
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
    if not any(_initial_assignment(root, snapshot, row, native_proof) for _, row in sends):
        return None
    index, current = sends[-1]
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
    return {**(native or {}), "dispatch": current, "dispatch_index": index, "ack": ack, "ack_index": ack_index}


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
    if box.get("candidate_version") != plan["candidate_version"] or not _producer_candidate_bound(root, plan, pin, box):
        raise w.WorkflowError("new producer outbox must bind the exact rework candidate/version")


def reviewer_department(root: Path, snapshot: dict) -> str:
    snapshot = _review_context(root, snapshot)
    plan = load_plan(root, snapshot)
    return plan["reviewer_department"] if plan else (_goal_reviewer(root, snapshot) or "qa")


def validate_plan(root: Path, snapshot: dict, plan: dict, *, transfer_from=None) -> None:
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
        allowed_reviewer = _goal_reviewer(root, snapshot, transfer_from=transfer_from)
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
        from parent_initial_child_review import prepare
        origin = prepare(root, snapshot, plan["parent_initial_child_review"])
        producer_pin = origin["proof"]["producer_outbox"]
        original = w.read_json(w.safe_path(root, producer_pin["path"]))
        if (origin["proof"]["producer_department"] != producer
                or plan.get("action_class") != "read_only_candidate"
                or plan.get("risk_level") != "R0"
                or not _producer_candidate_bound(root, plan, producer_pin, original)):
            raise w.WorkflowError("child review must bind its exact read-only producer candidate/version/result")


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
        if "owner_direct_review" in plan:
            binding["owner_direct_review"] = plan["owner_direct_review"]
        if "native_multi_goal_review" in plan:
            binding["native_multi_goal_review"] = plan["native_multi_goal_review"]
        if "parent_initial_child_review" in plan:
            binding["parent_initial_child_review"] = plan["parent_initial_child_review"]
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
        if modern and not any(name in plan for name in ("native_multi_goal_review", "parent_initial_child_review")) and not any(r.get("department") == plan["reviewer_department"]
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
    direct = None
    native = None
    inherited_child = None
    if "parent_initial_child_review" in plan:
        if binding.get("parent_initial_child_review") != plan["parent_initial_child_review"]:
            raise w.WorkflowError("bound original parent-linked child source changed")
        inherited_child = _assigned_review_round(root, snapshot, receipts, plan)
        if inherited_child is None:
            raise w.WorkflowError("original independent parent-linked child review source required")
        initial_assignment = True
        boxes = [row for row in receipts if row.get("department") == reviewer
                 and row.get("receipt_type") == "outbox_received"]
    elif "native_multi_goal_review" in plan:
        if binding.get("native_multi_goal_review") != plan["native_multi_goal_review"]:
            raise w.WorkflowError("bound original native multi-goal review source changed")
        native = _assigned_review_round(root, snapshot, receipts, plan)
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
            direct = owner_direct_review_context(root, snapshot, binding)
            if direct is None:
                raise w.WorkflowError("latest actual reviewer dispatch required, or exact inherited delegation/original owner-direct proof")
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
    source = direct or inherited_child
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
    if direct and box.get("owner_direct_review") != direct["proof"]:
        raise w.WorkflowError("final reviewer outbox must declare the exact original owner-direct proof")
    if native and box.get("native_multi_goal_review") != native["native_multi_goal_review"]:
        raise w.WorkflowError("final reviewer outbox must declare the exact original multi-goal source")
    if inherited_child and box.get("parent_initial_child_review") != inherited_child["proof"]:
        raise w.WorkflowError("final child reviewer outbox must declare the exact original first-send source")
    _validate_goal_acceptance(root, snapshot, receipts, box, receipt.get("verdict"))
    if (snapshot.get("task_id") == "fc-20261010-system-flow-throughput-and-ledger-close-v1"
            and receipt.get("verdict") == "pass"):
        from scoped_candidate_adoption import validate_final_goal_pass
        validate_final_goal_pass(root, snapshot, box)
    producer_boxes = [r for r in receipts if r.get("department") == plan["producer_department"]
                      and r.get("receipt_type") == "outbox_received"]
    if not producer_boxes:
        raise w.WorkflowError("original producer outbox required")
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
