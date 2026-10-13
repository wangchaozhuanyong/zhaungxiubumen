"""Owner-authorized direct execution of this one internal system repair.

This reads real human/native and source journals. It creates no account or
publication permission, assistant verdict, historical send or replacement goal.
Ordinary business tasks retain their original sole-assistant acceptance path.
"""
from __future__ import annotations

from pathlib import Path
import datetime as dt

import workflow_control as w

TASK = "fc-20261011-goal-publication-notice-followthrough-repair-v1"
SCOPE = "project:flashcast:goal-publication-notice-followthrough-repair:v1"
MODEL = "owner_direct_internal_system_repair_v1"


def _doc(root, pin):
    from qa_review_plan import _review_source_document
    try:
        return _review_source_document(root, pin)
    except (ValueError, KeyError, TypeError, OSError) as exc:
        raise w.WorkflowError("exact direct-repair evidence required: " + str(exc)) from exc


def _human(root, authorization):
    from qa_review_plan import _review_raw_native_result, _review_native_containers
    native = _doc(root, authorization["native"])
    if "content" in native:
        native = _review_raw_native_result(native)
    _review_native_containers(native)
    binding = w.department_registry(root)["operations"]["chat_binding"]
    thread = native.get("thread", {})
    if any(thread.get(k) != binding[v] for k, v in
           (("id", "task_id"), ("title", "title"), ("cwd", "cwd"))):
        raise w.WorkflowError("direct repair requires its actual fixed headquarters human source")
    messages = [(turn, item) for turn in native.get("turns", []) for item in turn.get("items", [])
                if item.get("type") == "userMessage" and item.get("id") == authorization.get("message_id")
                and turn.get("id") == authorization.get("turn_id")]
    if len(messages) != 1:
        raise w.WorkflowError("one actual human plan approval required")
    turn, item = messages[0]
    _review_native_containers(item)
    content = item.get("content")
    if (turn.get("error") or not isinstance(content, list) or not content
            or any(x.get("type") != "text" or not isinstance(x.get("text"), str) for x in content)):
        raise w.WorkflowError("complete genuine human text required")
    text = "".join(x["text"] for x in content)
    if (w.hashlib.sha256(text.encode("utf-8")).hexdigest() != authorization.get("text_sha256")
            or not all(value in text for value in
                       ("PLEASE IMPLEMENT THIS PLAN", TASK, "直接完成", "不再交开发部门返工",
                        "真实接续试点", "不扩大日常权限"))):
        raise w.WorkflowError("exact approved internal direct-repair plan required")
    return {"source_thread_id": thread["id"], "turn_id": turn["id"], "message_id": item["id"]}


def source_chain(root, reports, task_id, *, verify_live=True):
    """Validate actual contiguous file effects, not an all-history QA replay."""
    from source_patch_transaction import fingerprint
    if not isinstance(reports, list) or not reports:
        raise w.WorkflowError("actual direct source adoption reports required")
    endpoints, journals = {}, []
    for report_pin in reports:
        report = _doc(root, report_pin)
        journal = _doc(root, report["journal"])
        if (report.get("state") != "adopted" or journal.get("state") != "adopted"
                or journal.get("task_id") != task_id or journal.get("executor") != "operations"
                or journal.get("external_writes") != 0 or journal.get("assistant_verdict_created") is not False
                or not w._parse_observed_at(journal.get("completed_at"))):
            raise w.WorkflowError("actual scoped operations source adoption required")
        seen = set()
        for row in journal.get("source_operations", []):
            path = row.get("path", "")
            if not path.startswith("tools/") or path in seen or row.get("applied") is not True:
                raise w.WorkflowError("exact applied internal source operations required")
            seen.add(path)
            before, after, backup = row["before"], row["after"], row["backup"]
            if (path in endpoints and before != endpoints[path]
                    or fingerprint(root, backup["path"]) != backup
                    or any(backup[k] != before[k] for k in ("sha256", "size", "mode"))):
                raise w.WorkflowError("source successor or recoverable before bytes differ")
            endpoints[path] = after
        if not seen:
            raise w.WorkflowError("empty source adoption cannot prove execution")
        for row in report.get("created_files", []):
            path = row.get("path", "")
            if not path.startswith("tools/") or path in endpoints:
                raise w.WorkflowError("created source identity overlaps existing adoption")
            endpoints[path] = row
        journals.append(report["journal"])
    changed = []
    for path, expected in endpoints.items():
        if fingerprint(root, path) != expected:
            changed.append(path)
            if verify_live:
                raise w.WorkflowError("direct repair live source differs from its latest actual adoption: " + path)
    return {"state": "adopted", "historical_adoption_proven": True,
            "source_readback_passed": not changed, "current_source_differences": changed,
            "files": len(endpoints), "sources": list(endpoints.values()), "journals": journals}


def context(root, task_id):
    if task_id != TASK:
        return None
    config = w.read_json(Path(root) / "data/task-contract.json").get("goal_delivery_runtime", {})
    pin = config.get("direct_execution_takeovers", {}).get(task_id)
    if pin is None:
        return None
    document = _doc(root, pin)
    if (document.get("model") != MODEL or document.get("task_id") != TASK
            or document.get("scope") != SCOPE or document.get("executor") != "operations"
            or document.get("external_permission_issued") is not False
            or document.get("business_permissions_changed") is not False):
        raise w.WorkflowError("only this exact internal direct-execution takeover is allowed")
    _human(root, document["human_authorization"])
    snapshot = w.read_json(w.snapshot_path(root, task_id))
    original = snapshot.get("goal_delivery", {})
    if (original.get("authorized_scope") != [SCOPE]
            or original.get("primary_owner") != "system-development"
            or original.get("required_execution_actions")):
        raise w.WorkflowError("frozen internal goal scope cannot expand through takeover")
    if w.validate_workflow_events(root, task_id):
        raise w.WorkflowError("intact original workflow events required")
    events = [row for row in w.read_jsonl(Path(root) / w.WORKFLOW_EVENTS)
              if row.get("task_id") == task_id and row.get("details", {}).get("owner_direct_execution") == pin]
    if len(events) != 1:
        raise w.WorkflowError("one actual committed direct takeover event required")
    reports = list(document["source_adoptions"])
    for event in w.read_jsonl(Path(root) / w.WORKFLOW_EVENTS):
        extension = event.get("details", {}).get("direct_source_adoption")
        if event.get("task_id") == TASK and isinstance(extension, dict) and extension.get("takeover") == pin:
            reports.append(extension["report"])
    closed = any(e.get("task_id") == TASK and e.get("state") == "closed"
                 and e.get("details", {}).get("owner_direct_completion") == pin
                 and e.get("details", {}).get("closed_scope_only") is True
                 for e in w.read_jsonl(Path(root) / w.WORKFLOW_EVENTS))
    adopted = source_chain(root, reports, task_id, verify_live=not closed)
    return {"pin": pin, "document": document, "original_goal": original,
            "executor": "operations", "historical_responsible_assistant": original["responsible_assistant"],
            "adoption": adopted, "source_adoptions": reports, "event_id": events[0]["event_id"]}


def owners(root):
    try:
        active = context(root, TASK)
        return {TASK: "operations"} if active else {}
    except (w.WorkflowError, ValueError, KeyError, TypeError, OSError):
        # Inventory reports this exact task error. A failed historical repair
        # reader must not prevent unrelated goals from finding their owners.
        return {}


def message_precheck(root, request):
    """Exact authorized role-health recovery and the original A3 pilot message.

    An unloaded native chat is not an active chat. Its fresh native completion
    snapshot is required; never turn a cached status into permission to send.
    """
    if request.get("task_id") != TASK or not request.get("action_id", "").startswith("direct-system-"):
        return None
    active = context(root, TASK)
    if active is None:
        return ["direct_execution_not_admitted"]
    if w.read_json(w.snapshot_path(root,TASK)).get("current_state") in w.TERMINAL_STATES:
        return ["closed_direct_repair_no_new_message_permission"]
    config = w.read_json(Path(root) / "data/task-contract.json")["goal_delivery_runtime"]
    pin = config.get("direct_message_packets", {}).get(request["action_id"])
    if not pin:
        return ["exact_direct_message_packet_required"]
    packet = _doc(root, pin)
    from goal_delivery_runtime import _native_document
    expected = packet.get("request", {})
    if any(expected.get(k) != v for k, v in request.items()):
        return ["exact_direct_message_identity_or_payload_changed"]
    registry = w.department_registry(root)
    role = request.get("target_department")
    if role not in registry or role == "operations" or registry[role].get("new_dispatch_enabled") is False:
        return ["direct_recovery_requires_active_registered_fixed_role"]
    target = registry[role]["chat_binding"]
    source = registry["operations"]["chat_binding"]
    if (request.get("sender_department") != "operations"
            or request.get("scope") != SCOPE or request.get("action_class") != "thread_message"
            or request.get("source_project_id") != source["project_id"]
            or any(request.get(k) != target[v] for k, v in
                   (("target_project_id", "project_id"), ("target_thread_id", "task_id"),
                    ("target_thread_title", "title"), ("target_cwd", "cwd"),
                    ("target_sidebar_section_id", "sidebar_section_id")))):
        return ["direct_message_only_original_fixed_A3_same_project"]
    at = w._parse_observed_at(packet.get("observed_at"))
    if at is None or not 0 <= (dt.datetime.now(dt.timezone.utc)-at).total_seconds() <= 300:
        return ["fresh_direct_message_native_identity_required"]
    live = _native_document(root, packet["actual_list"])
    rows = [t for t in live.get("threads", []) + live.get("pinnedThreads", []) if t.get("id") == target["task_id"]]
    groups = [g for g in live.get("sections", []) if g.get("sectionId") == target["sidebar_section_id"]
              and "codex:thread:local:" + target["task_id"] in g.get("itemKeys", [])]
    actual = _native_document(root, packet["actual_wait"])
    polls = [p for p in actual.get("polls", []) if p.get("thread", {}).get("id") == target["task_id"]]
    if (len(rows) != 1 or len(groups) != 1 or len(polls) != 1
            or rows[0].get("status") not in {"idle", "notLoaded"}
            or polls[0].get("thread", {}).get("status", {}).get("type") not in {"idle", "notLoaded"}
            or polls[0].get("latestTurn", {}).get("status") != "completed"
            or polls[0].get("latestTurn", {}).get("error")
            or any(rows[0].get(k) != target[v] for k,v in
                   (("projectId","project_id"),("title","title"),("cwd","cwd")))):
        return ["actual_fixed_A3_not_busy_completion_required"]
    payload = packet["payload"]
    if w.file_digest(root, payload["path"]) != payload or payload["sha256"] != request["payload_sha256"]:
        return ["direct_message_exact_bytes_required"]
    effect_path = packet.get("native_send_receipt_path", "")
    if not effect_path.startswith("logs/") or w.safe_path(root, effect_path).exists():
        return ["direct_message_already_attempted_readback_required"]
    if packet.get("purpose") == "pure_health_recovery":
        expected_text = health_message(registry[role])
        if (w.safe_path(root, payload["path"]).read_text() != expected_text
                or packet.get("health_text") != expected_text):
            return ["pure_health_message_changed"]
        if not all(v in packet["health_text"] for v in ("仅确认", "不执行业务", "不改文件", target["task_id"])):
            return ["pure_health_no_business_required"]
    elif packet.get("purpose") == "original_A3_result_continuation":
        if role != "operations-assistant-3":
            return ["result_pilot_only_original_A3"]
        if not all(w._chat_binding_healthy(b, verification_ttl_hours=26) for b in (source,target)):
            return ["direct_result_continuation_fresh_reply_health_required"]
    else:
        return ["direct_message_purpose_outside_authorization"]
    return []


def health_message(item):
    b=item["chat_binding"]
    return ("本轮仅确认固定" + item["name"] + "身份与可工作状态。准确聊天" + b["task_id"]
            + "，项目" + b["project_id"] + "，cwd " + b["cwd"]
            + "。请在自己的固定聊天非空回复：身份一致且可接续，或说明真实中断原因。"
              "本轮不执行业务、不改文件、不写代码、不修改账号、不向其他聊天发送消息；"
              "这不是业务接单，不需要逐层审核。")


def receive_original_knowledge(root, source_pin, next_action_pin, idempotency_key):
    """HQ receives an existing partial conclusion, without impersonating A3."""
    from result_coordination import ORIGINAL_A3_CONCLUSION, ORIGINAL_A3_OUTBOX
    source = _doc(root, source_pin)
    fixed = w.department_registry(root)["operations-assistant-3"]["chat_binding"]["task_id"]
    checked = w._validate_goal_completed_result(root, source["request"], fixed)
    action = _doc(root, next_action_pin)
    if (source.get("passed") is not True or action.get("original_identity") != ORIGINAL_A3_CONCLUSION
            or action.get("business_goal_closed") is not False or not action.get("next_actions")
            or w.file_digest(root, ORIGINAL_A3_OUTBOX)["sha256"] != ORIGINAL_A3_CONCLUSION["result_sha256"]):
        raise w.WorkflowError("actual original A3 partial conclusion and explicit remaining actions required")
    details = {"direct_recovered_knowledge": {"identity": ORIGINAL_A3_CONCLUSION,
               "source": source_pin, "actual_completed_result": checked,
               "next_actions": next_action_pin, "actual_receiver": "operations",
               "intake_mode": "fallback", "notification_sent": False,
               "assistant_verdict_created": False, "business_goal_closed": False,
               "idempotency_key": idempotency_key}}
    with w.workflow_lock(root):
        if context(root, TASK) is None:
            raise w.WorkflowError("human direct repair admission required")
        prior = [e for e in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS) if e.get("task_id")==TASK
                 and e.get("details",{}).get("direct_recovered_knowledge",{}).get("identity")==ORIGINAL_A3_CONCLUSION]
        if prior:
            if len(prior)!=1 or prior[0]["details"]!=details:
                raise w.WorkflowError("original recovered knowledge already has different effects")
            return {**prior[0], "result":"duplicate_ignored"}
        return w.append_workflow_event(root,TASK,w.read_json(w.snapshot_path(root,TASK))["current_state"],details)


def received_original_knowledge(root, identity):
    from result_coordination import ORIGINAL_A3_CONCLUSION
    if identity != ORIGINAL_A3_CONCLUSION or context(root,TASK) is None:
        return None
    events=[e for e in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS) if e.get("task_id")==TASK
            and e.get("details",{}).get("direct_recovered_knowledge",{}).get("identity")==identity]
    if not events:return None
    if len(events)!=1:raise w.WorkflowError("one actual original result intake required")
    event=events[0];entry=event["details"]["direct_recovered_knowledge"]
    source=_doc(root,entry["source"])
    checked=w._validate_goal_completed_result(root,source["request"],source["request"]["source_thread_id"])
    if (checked!=entry.get("actual_completed_result") or entry.get("actual_receiver")!="operations"
            or entry.get("business_goal_closed") is not False):
        raise w.WorkflowError("original actual HQ intake source changed")
    actions=_doc(root,entry["next_actions"])
    return {"record_id":event["event_id"],"identity":identity,"actual_receiver":"operations",
            "intake_mode":"fallback","source_mode":"human_direct_repair_exact_recovery",
            "next_actions":actions["next_actions"],"decision":"continue_original_partial_scope",
            "business_goal_closed":False,"native_notification_sent":False}


def existing_result_resolution(root,identity):
    """Associate an old blocked record to its already real successor, not PASS."""
    from result_coordination import ORIGINAL_A3_CONCLUSION, _committed_result, IDENTITY_FIELDS
    if identity.get('task_id')!=ORIGINAL_A3_CONCLUSION['task_id']:
        return None
    if identity.get('candidate_version') not in {'assistant3-remaining-business-continuation-v2-20261010',
                                                 'sales-original-goals-actual-continuation-v2-20261011'}:
        return None
    if context(root,TASK) is None:return None
    events=[e for e in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS) if e.get('task_id')==TASK
            and e.get('details',{}).get('direct_existing_result_associations')]
    matches=[]
    for event in events:
        doc=_doc(root,event['details']['direct_existing_result_associations'])
        matches.extend(x for x in doc.get('associations',[]) if x.get('identity')==identity)
    if not matches:return None
    if len(matches)!=1:raise w.WorkflowError('one exact original result association required')
    entry=matches[0];successor=entry['successor']
    if (successor['task_id']!=identity['task_id'] or successor['sender_department']!=identity['sender_department']
            or entry.get('business_goal_closed') is not False
            or w.file_digest(root,entry['original_outbox']['path'])!=entry['original_outbox']):
        raise w.WorkflowError('original result association source changed')
    if successor==ORIGINAL_A3_CONCLUSION:
        received=received_original_knowledge(root,successor)
        if not received or received['record_id']!=entry['proof']['received_event_id']:
            raise w.WorkflowError('actual successor HQ intake required')
    else:
        rows=w._result_handoff_rows(root,successor['task_id']);actual=[x for x in rows
             if x.get('record_id') in entry['proof']['actual_record_ids']]
        if (len(actual)!=3 or {x['event'] for x in actual}!={'controller_received','controller_decision','controller_followthrough'}
                or any(w._result_identity(x)!=tuple(successor[k] for k in IDENTITY_FIELDS[1:]) for x in actual)):
            raise w.WorkflowError('actual same original successor lifecycle required')
        for row in actual:_committed_result(root,row)
    return {'resolution':'already_handled_by_verified_successor','successor':successor,
            'original_notification_sent':False,'original_verdict_unchanged':True,'business_goal_closed':False}


def completion_view(root, snapshot, active=None):
    active = active or context(root, snapshot["task_id"])
    if active is None:
        return None
    from goal_delivery_runtime import _completion_contract
    contract = _completion_contract(root, snapshot)
    requirements, missing, blockers = [], [], []
    # Admission is immutable. Progress is appended to the original event log.
    proofs = dict(active["document"].get("completion_evidence", {}))
    for event in w.read_jsonl(Path(root) / w.WORKFLOW_EVENTS):
        update = event.get("details", {}).get("direct_completion_evidence")
        if (event.get("task_id") == TASK and isinstance(update, dict)
                and update.get("takeover") == active["pin"]):
            for rid, pin in update.get("proofs", {}).items():
                supersedes = update.get("supersedes", {})
                if rid in proofs and proofs[rid] != pin and supersedes.get(rid) != proofs[rid]:
                    raise w.WorkflowError("direct completion proof cannot silently replace an earlier proof")
                proofs[rid] = pin
    for requirement in contract.get("requirements", []):
        rid, kind = requirement["requirement_id"], requirement["requirement_type"]
        pin = proofs.get(rid)
        state, reason, evidence = "MISSING", "actual_direct_execution_evidence_missing", []
        if kind == "source_adoption":
            state, reason = "PROVEN", None
            evidence = active.get("source_adoptions", active["document"]["source_adoptions"])
        elif pin:
            proof = _doc(root, pin)
            if (proof.get("task_id") != TASK or proof.get("scope") != SCOPE
                    or proof.get("requirement_id") != rid or proof.get("proof_type") != kind
                    or proof.get("actual_executor") != "operations" or proof.get("external_writes") != 0
                    or proof.get("business_goal_closed") is not False):
                raise w.WorkflowError("direct completion evidence must retain each original exact standard")
            if kind == "internal_pilot":
                from result_coordination import readback_direct_repair_pilot
                readback_direct_repair_pilot(root, proof)
            else:
                checks = _doc(root, proof["check_report"])
                if not checks.get("successful") or checks.get("verified_sources") != active["adoption"]["sources"]:
                    raise w.WorkflowError("affected checks must bind the actual installed source version")
            state, reason, evidence = "PROVEN", None, [pin]
        row = {**requirement, "state": state, "reason": reason, "evidence": evidence,
               "next_owner": "operations"}
        requirements.append(row)
        if state != "PROVEN":
            missing.append("completion_requirement:" + rid + ":" + reason)
    if not requirements:
        missing.append("needs_completion_declaration")
    return {"contract_state": contract["state"], "completion_kind": contract["completion_kind"],
            "contract_pin": contract.get("contract_pin"), "state": "direct_owner_completion",
            "requirements": requirements, "missing": missing, "blockers": blockers,
            "actual_executor": "operations", "source_adopted": True, "closed_scope_only": not missing,
            "business_goal_closed": False, "control_scope_completed": not missing}


def record_completion(root, proofs, idempotency_key, supersedes=None):
    """Append actual executor evidence, not an assistant verdict."""
    if not isinstance(proofs, dict) or not proofs or not idempotency_key:
        raise w.WorkflowError("bounded exact completion proofs and idempotency key required")
    with w.workflow_lock(root):
        active = context(root, TASK)
        if active is None:
            raise w.WorkflowError("actual admitted owner direct execution required")
        from goal_delivery_runtime import _completion_contract
        snapshot = w.read_json(w.snapshot_path(root, TASK))
        allowed = {row["requirement_id"] for row in _completion_contract(root, snapshot)["requirements"]}
        if not set(proofs) <= allowed:
            raise w.WorkflowError("completion proof cannot add a new goal or standard")
        for pin in proofs.values():
            _doc(root, pin)
        details = {"direct_completion_evidence": {"takeover": active["pin"], "proofs": proofs,
                   "supersedes": supersedes or {},
                   "idempotency_key": idempotency_key, "actual_executor": "operations",
                   "assistant_verdict_created": False, "business_goal_closed": False}}
        previous = [e for e in w.read_jsonl(Path(root) / w.WORKFLOW_EVENTS)
                    if e.get("task_id") == TASK and e.get("details", {}).get("direct_completion_evidence", {}).get(
                        "idempotency_key") == idempotency_key]
        if previous:
            if len(previous) != 1 or previous[0]["details"] != details:
                raise w.WorkflowError("completion idempotency key already binds another proof")
            return {**previous[0], "result": "duplicate_ignored"}
        # Validate each proposed proof before commit. Historical events stay
        # immutable; a changed installed source needs an explicit replacement.
        for rid,pin in proofs.items():
            proof=_doc(root,pin)
            if proof.get("requirement_id") != rid or proof.get("task_id") != TASK or proof.get("scope") != SCOPE:
                raise w.WorkflowError("completion proof exact original requirement required")
            if proof.get("proof_type") == "internal_pilot":
                from result_coordination import readback_direct_repair_pilot
                readback_direct_repair_pilot(root,proof)
            elif proof.get("proof_type") != "source_adoption":
                checks=_doc(root,proof["check_report"])
                if not checks.get("successful") or checks.get("verified_sources") != active["adoption"]["sources"]:
                    raise w.WorkflowError("completion checks must match current installed sources")
        return w.append_workflow_event(root, TASK, snapshot["current_state"], details)


def record_source_adoption(root, report_pin, idempotency_key):
    """Append a real later source transaction without rewriting prior adoption."""
    with w.workflow_lock(root):
        config=w.read_json(Path(root)/"data/task-contract.json")["goal_delivery_runtime"]
        pin=config.get("direct_execution_takeovers",{}).get(TASK)
        document=_doc(root,pin);_human(root,document["human_authorization"])
        events=w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS)
        extensions=[e for e in events if e.get("task_id")==TASK
                    and e.get("details",{}).get("direct_source_adoption",{}).get("takeover")==pin]
        existing=[e for e in extensions if e["details"]["direct_source_adoption"].get("idempotency_key")==idempotency_key]
        if existing:
            if len(existing)!=1 or existing[0]["details"]["direct_source_adoption"]["report"]!=report_pin:
                raise w.WorkflowError("source adoption idempotency conflict")
            return {**existing[0],"result":"duplicate_ignored"}
        reports=document["source_adoptions"]+[e["details"]["direct_source_adoption"]["report"] for e in extensions]+[report_pin]
        source_chain(root,reports,TASK)
        if w.validate_workflow_events(root,TASK):raise w.WorkflowError("intact source event history required")
        return w.append_workflow_event(root,TASK,w.read_json(w.snapshot_path(root,TASK))["current_state"],
                {"direct_source_adoption":{"takeover":pin,"report":report_pin,"idempotency_key":idempotency_key}})


def inventory(root):
    active = context(root, TASK)
    if active is None:
        return []
    snapshot = w.read_json(w.snapshot_path(root, TASK))
    completion = completion_view(root, snapshot, active)
    return [{"task_id": TASK, "department": "operations", "primary_owner": "operations",
             "next_owner": "operations", "actual_executor": "operations",
             "historical_responsible_assistant": active["historical_responsible_assistant"],
             "status": "formally_closed_scope" if completion["control_scope_completed"] else "direct_execution_followthrough",
             "native_workflow_state": snapshot["current_state"],
             "requires_action": not completion["control_scope_completed"],
             "next_action": "close_verified_internal_scope" if completion["control_scope_completed"] else "complete_exact_direct_repair_requirements",
             "completion_obligations": completion, "completion_criteria": active["original_goal"]["completion_criteria"],
             "source_adopted": True, "business_goal_closed": False,
             "formally_closed_scope": completion["control_scope_completed"]}]
