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
COMPLETION_KINDS = {"internal_delivery", "production_release", "growth_batch"}
COMPLETION_TYPES = {"accepted_delivery", "execution_postcheck", "source_adoption",
                    "internal_pilot", "result_notification", "growth_batch_followthrough"}
COMPLETION_IDENTITY = ("objective", "completion_criteria", "authorized_scope", "primary_owner",
                       "responsible_assistant", "producer_departments")


def completion_contract_state(goal, *, supplemental=None):
    """Mechanically map every frozen criterion; never infer a kind from prose."""
    contract = goal if supplemental is None else supplemental
    if not isinstance(goal, dict) or not isinstance(contract, dict):
        raise w.WorkflowError("explicit completion contract object required")
    if not any(key in contract for key in ("completion_kind", "completion_requirements")):
        return {"state": "needs_completion_declaration", "completion_kind": None, "requirements": []}
    kind, rows = contract.get("completion_kind"), contract.get("completion_requirements")
    if kind not in COMPLETION_KINDS or not isinstance(rows, list) or not 1 <= len(rows) <= 100:
        raise w.WorkflowError("known completion kind and nonempty bounded frozen requirements required")
    criteria, scopes, producers = (goal.get(name, []) for name in
                                   ("completion_criteria", "authorized_scope", "producer_departments"))
    if not criteria or any(not isinstance(text, str) or not text.strip() for text in criteria):
        raise w.WorkflowError("nonempty original completion criteria required")
    ids, covered, mapped_actions = set(), set(), set()
    declared = {tuple(action.get(k) for k in ("action_id", "action_class", "scope", "department"))
                for action in goal.get("required_execution_actions", [])}
    for row in rows:
        if not isinstance(row, dict):
            raise w.WorkflowError("typed exact completion requirement object required")
        rid, index, requirement_type = row.get("requirement_id"), row.get("criterion_index"), row.get("requirement_type")
        subject = row.get("subject")
        if (not isinstance(rid, str) or not rid.strip() or rid in ids
                or type(index) is not int or not 0 <= index < len(criteria)
                or row.get("scope") not in scopes or requirement_type not in COMPLETION_TYPES
                or not isinstance(subject, dict) or set(subject) != {"mode", "producer_department"}
                or subject.get("mode") != "latest_exact_accepted_result"
                or subject.get("producer_department") not in producers):
            raise w.WorkflowError("unique requirement, original criterion/scope and exact accepted subject required")
        if row.get("proof_type", requirement_type) != requirement_type:
            raise w.WorkflowError("proof type cannot change a completion requirement")
        if "proof_ref" in row and not isinstance(row["proof_ref"], dict):
            raise w.WorkflowError("typed proof selector object required; booleans are not evidence")
        if requirement_type == "execution_postcheck":
            action = tuple(row.get(k) for k in ("action_id", "action_class", "scope", "department"))
            if kind != "production_release" or action not in declared:
                raise w.WorkflowError("production completion must map its original declared action exactly")
            mapped_actions.add(action)
        if requirement_type == "growth_batch_followthrough" and kind != "growth_batch":
            raise w.WorkflowError("growth followthrough requires the frozen growth batch kind")
        ids.add(rid); covered.add(index)
    if covered != set(range(len(criteria))):
        raise w.WorkflowError("all original completion criteria must retain a precise mapping")
    if declared and (kind != "production_release" or mapped_actions != declared):
        raise w.WorkflowError("declared production cannot escape or lose execution/postcheck requirements")
    if kind == "production_release" and not declared:
        raise w.WorkflowError("production release needs its original declared production actions")
    if kind == "growth_batch" and not any(row["requirement_type"] == "growth_batch_followthrough" for row in rows):
        raise w.WorkflowError("growth batch needs an actual batch followthrough requirement")
    return {"state": "declared", "completion_kind": kind, "requirements": copy.deepcopy(rows)}


def _completion_contract(root, snapshot):
    goal = snapshot["goal_delivery"]
    direct = completion_contract_state(goal)
    events = [row for row in w.read_jsonl(Path(root) / w.WORKFLOW_EVENTS) if row.get('task_id') == snapshot['task_id']]
    original = next((row['details']['goal_delivery'] for row in events
                     if isinstance(row.get('details', {}).get('goal_delivery'), dict)), None)
    pins = [row.get("details", {}).get("completion_contract_pin")
            for row in events if row.get("details", {}).get("completion_contract_pin") is not None]
    if direct["state"] == "declared":
        if pins:
            raise w.WorkflowError("an original declared contract cannot be replaced by a supplement")
        return direct
    config = w.read_json(Path(root) / "data/task-contract.json").get("goal_delivery_runtime", {})
    configured = config.get("completion_contracts", {}).get(snapshot["task_id"])
    if not pins:
        return {**direct, "supplement_prepared": configured is not None}
    if any(pin != pins[0] for pin in pins) or pins[0] != configured:
        raise w.WorkflowError("one immutable committed completion supplement and matching configured pin required")
    pin = pins[0]
    if not isinstance(pin, dict) or w.file_digest(root, pin.get("path", "")) != pin:
        raise w.WorkflowError("frozen completion supplement bytes changed")
    document = w.read_json(w.safe_path(root, pin["path"]))
    _validate_completion_supplement(snapshot, document, original_goal=original)
    return {**completion_contract_state(goal, supplemental=document), "contract_pin": pin}


def _validate_completion_supplement(snapshot, document, *, original_goal=None):
    goal = snapshot["goal_delivery"]
    if (not isinstance(original_goal, dict)
            or not isinstance(document, dict) or document.get("schema_version") != "goal-completion-contract-v1"
            or document.get("task_id") != snapshot["task_id"]
            or document.get("authorization_pin") != goal.get("authorization_pin")
            or original_goal.get('authorization_pin') != goal.get('authorization_pin')
            or document.get("goal_identity_sha256") != w.sha256_value({key: original_goal.get(key) for key in COMPLETION_IDENTITY})):
        raise w.WorkflowError("supplement must mechanically preserve the frozen original goal and authorization")
    return completion_contract_state(goal, supplemental=document)


def record_completion_contract(root, task_id, input_path, role):
    """Freeze a prepared mechanical supplement once, without rewriting the goal."""
    task_id = w.validate_task_id(task_id)
    pin = w.file_digest(root, input_path)
    document = w.read_json(w.safe_path(root, input_path))
    with w.workflow_lock(root):
        snapshot = restore_goal(root, w.read_json(w.snapshot_path(root, task_id)))
        goal = snapshot.get("goal_delivery", {})
        if (not enabled(root, snapshot) or role != goal.get("responsible_assistant")
                or role in goal.get("producer_departments", [])
                or w.department_registry(root).get(role, {}).get("coordination_authority", {}).get("routine_decisions") is not True):
            raise w.WorkflowError("original independent responsible assistant must record the completion supplement")
        if w.validate_workflow_events(root, task_id) or w._validate_receipt_chain(root, task_id)[1]:
            raise w.WorkflowError("intact original event/receipt chains required for completion declaration")
        if completion_contract_state(goal)["state"] == "declared":
            raise w.WorkflowError("original completion requirements already frozen")
        original = next((row['details']['goal_delivery'] for row in w.read_jsonl(Path(root) / w.WORKFLOW_EVENTS)
                         if row.get('task_id') == task_id and isinstance(row.get('details', {}).get('goal_delivery'), dict)), None)
        _validate_completion_supplement(snapshot, document, original_goal=original)
        configured = w.read_json(Path(root) / "data/task-contract.json").get("goal_delivery_runtime", {}).get("completion_contracts", {}).get(task_id)
        if configured != pin:
            raise w.WorkflowError("exact prepared supplemental contract pin required")
        current = _completion_contract(root, snapshot)
        if current.get("contract_pin"):
            if current["contract_pin"] != pin:
                raise w.WorkflowError("completion requirements cannot change or shrink after commitment")
            return {"result": "duplicate_ignored", "completion_contract_pin": pin, "goal_rewritten": False}
        w.append_workflow_event(root, task_id, snapshot["current_state"],
                                {"completion_contract_pin": pin, "completion_contract_recorder": role,
                                 "original_authorization_pin": goal["authorization_pin"]})
    return {"result": "recorded", "completion_contract_pin": pin, "goal_rewritten": False,
            "external_permission_issued": False, "business_goal_closed": False}


def enabled(root, snapshot=None):
    # Legacy snapshots have no goal contract; retain their original read path.
    # A real goal or a fresh startup still requires the intact global contract.
    if snapshot is not None:
        if "goal_delivery" not in snapshot and "goal_contract" not in snapshot:
            return False
        if not isinstance(snapshot.get("goal_delivery"), dict):
            raise w.WorkflowError("goal snapshot must retain its goal delivery object")
    try:
        document = json.loads(w.validation_bytes(Path(root) / "data/task-contract.json"))
    except (OSError, ValueError, TypeError) as exc:
        raise w.WorkflowError("intact global task contract required") from exc
    if not isinstance(document, dict):
        raise w.WorkflowError("global task contract object required")
    config = document.get("goal_delivery_runtime", {})
    if not isinstance(config, dict):
        raise w.WorkflowError("goal delivery runtime configuration object required")
    if config.get('model') == 'department_autonomous_delivery_v1':
        from department_autonomy import current_mode
        return current_mode(root) and (snapshot is None or isinstance(snapshot.get('goal_delivery'),dict))
    return (config.get("model") == MODEL and config.get("assistant_decisions_enabled") is True
            and (snapshot is None or isinstance(snapshot.get("goal_delivery"), dict)))


# The current owner delegated decision responsibility, not execution permission.
# Keep its actual human source; caller flags and other project copies cannot grant it.
_OWNER_DECISION_SOURCE = {'pin': {'path': 'logs/handoffs/2026-10-20-clean-department-window-rotation-v1/operations/unfinished-business-followthrough-20261021-v1/owner-delegated-nonpayment-decisions-system-repair-v1/owner-current-human-native-v1.json', 'sha256': '5568a10ef0e63fc7558695704a4e10d500605a7340de31cc35012edc25aab0df', 'size': 1207}, 'source_thread_id': '<LOCAL_TASK_ID>', 'source_turn_id': 'example-native-71a5d7233e137670', 'source_message_id': 'example-native-29f0cb9317eec26b', 'project_id': '<LOCAL_PROJECT_ID>', 'cwd': '<PROJECT_ROOT>'}


def _owner_decision_delegation(root):
    source = _OWNER_DECISION_SOURCE
    if Path(root).resolve() != Path(source['cwd']).resolve():
        return None
    pin = source['pin']
    if w.file_digest(root, pin['path']) != pin:
        raise w.WorkflowError('unchanged actual owner decision delegation source required')
    document = w.read_json(w.safe_path(root, pin['path']))
    message = document.get('message', {})
    native = document.get('actual_native_thread', {})
    binding = w.department_registry(root)['operations']['chat_binding']
    if (document.get('source_thread_id') != source['source_thread_id']
            or document.get('source_turn_id') != source['source_turn_id']
            or message.get('type') != 'userMessage' or message.get('id') != source['source_message_id']
            or native.get('id') != source['source_thread_id'] or native.get('cwd') != source['cwd']
            or binding.get('project_id') != source['project_id'] or binding.get('cwd') != source['cwd']
            or not any(c.get('type') == 'text' and str(c.get('text', '')).strip()
                       for c in message.get('content', []) if isinstance(c, dict))):
        raise w.WorkflowError('actual same-project human decision delegation required')
    return {'source': pin, 'scope': 'current_project_routine_nonpayment_decisions',
            'source_thread_id': source['source_thread_id'], 'source_message_id': source['source_message_id'],
            'payment_owner': 'human_owner', 'execution_authority_unchanged': True}


def authorization_precheck(root, task_id, request):
    """Read existing whole-goal authority before asking again; never issue a permit.

    Identity/health/payload/self-check repairs remain internal. Exact action policy,
    consumed permits and real provider restrictions still govern actual execution.
    A legacy goal without a bound source must recover it, not invent authority.
    """
    task_id = w.validate_task_id(task_id)
    if (not isinstance(request, dict) or request.get("task_id") != task_id
            or any(not isinstance(request.get(k), str) or not request[k].strip()
                   for k in ("sender_department", "action_class", "scope"))):
        raise w.WorkflowError("exact original task/sender/action/scope required")
    sensitive = {"new_scope", "new_department", "new_project", "new_account",
                 "permission_expansion", "new_fee", "budget_exceeded",
                 "irreversible_delete", "major_security_change", "infrastructure_change"}
    changes = request.get("authorization_changes", [])
    repairs = request.get("internal_repairs", [])
    repair_kinds = {"health", "binding", "source_binding", "payload", "receipt",
                    "self_check", "backup", "rollback", "version_update"}
    if (not isinstance(changes, list) or any(not isinstance(x, str) or x not in sensitive for x in changes)
            or not isinstance(repairs, list) or any(not isinstance(x, str) or x not in repair_kinds for x in repairs)):
        raise w.WorkflowError("known authorization changes or internal repairs required")
    if request["action_class"] == "thread_message" and (
            not isinstance(request.get("target_department"), str) or not request["target_department"].strip()):
        raise w.WorkflowError("exact target department required")
    if request["action_class"] in w.EXTERNAL_ACTION_CLASSES and any(
            not isinstance(request.get(k), str) or not request[k].strip() for k in ("action_id", "department")):
        raise w.WorkflowError("exact original production action and executor required")
    result = {"schema": "goal-authorization-precheck/v1", "task_id": task_id,
              "action_class": request["action_class"], "scope": request["scope"],
              "writes_performed": False, "external_permission_issued": False,
              "actual_action_allowed": False, "replaces_policy_check": False,
              "required_internal_checks": ["exact_current_identity_and_health", "exact_policy_check",
                                            "deduplicate_actual_effects", "existing_production_channel"]}

    delegation = None

    def outcome(state, reasons, confirmation=False):
        # Changed authority still blocks actual execution. Route its ordinary
        # nonpayment decision to HQ instead of inventing another owner prompt.
        payment = bool({'new_fee', 'budget_exceeded'}.intersection(reasons))
        needs_human = confirmation and (delegation is None or payment)
        next_owner = ('human_owner' if payment and delegation else 'operations') if confirmation else request['sender_department']
        next_action = ('ask_owner_for_exact_payment' if needs_human and delegation else
                       'escalate_only_changed_scope' if needs_human else
                       'coordinate_exact_nonpayment_change_preserve_action_gates') if confirmation else (
            'read_actual_completion_and_preserve_remaining_scope' if state == 'completed_scope_readback_required'
            else 'repair_internal_binding_then_exact_preflight' if state != 'within_original_authorization'
            else 'continue_original_goal_with_existing_action_gates')
        value = {**result, 'status': state, 'reasons': sorted(set(reasons)),
                 'needs_human_confirmation': needs_human, 'next_owner': next_owner, 'next_action': next_action}
        if delegation is not None:
            value.update(decision_delegation=delegation, decision_owner=next_owner,
                         blocks_only_dependent_action=state != 'within_original_authorization')
        return value

    snapshot = w.read_json(w.snapshot_path(root, task_id))
    if not snapshot or not enabled(root, snapshot):
        return outcome("original_source_binding_required", ["recover_real_original_authority_without_new_dispatch"])
    snapshot = restore_goal(root, snapshot)
    goal = snapshot["goal_delivery"]
    from professional_web_execution import applies as original_external_WEB, authorization_precheck as original_external_authorization
    if original_external_WEB(root, task_id, request.get("action_class")):
        return original_external_authorization(root, request)
    from tools.shop_office_web_execution import applies as exact_WEB_applies, authorization_precheck as exact_WEB_authorization
    if exact_WEB_applies(task_id, request.get("action_class")):
        return exact_WEB_authorization(root, request)
    auth = goal.get("human_authorization", {})
    pin = goal["authorization_pin"]
    source = w.read_json(w.safe_path(root, pin["path"]))
    message = source.get("message", {})
    if (source.get("source_thread_id") != auth.get("source_thread_id")
            or message.get("type") != "userMessage" or message.get("id") != auth.get("message_id")
            or not any(c.get("type") == "text" and str(c.get("text", "")).strip()
                       for c in message.get("content", []) if isinstance(c, dict))):
        raise w.WorkflowError("unchanged original real human source required")
    result["original_authorization"] = pin
    if request.get("action_class") == "cms_write":
        from professional_cms_execution import match
        registered = match(root, snapshot, request)
        if registered is not None:
            if changes:
                return outcome("authorization_change_required", changes, confirmation=True)
            return {**outcome("within_original_authorization", ["authenticated_append_only_professional_CMS_source"]),
                    "source_registration": registered["registration"],
                    "business_scope": registered["business_scope"],
                    "physical_scope": registered["action"]["scope"],
                    "platform_permission_still_required": True}
    registry = w.department_registry(root)
    sender = request["sender_department"]
    producers = goal.get("producer_departments", [])
    from brand_v4_issuer_executor import action_context as brand_action_context
    brand_executor = (brand_action_context(root, snapshot, request.get('action_id'), request.get('action_class'),
                      request.get('scope'), sender) if request.get('action_class') in w.EXTERNAL_ACTION_CLASSES else None)
    from department_autonomy import message_route, readonly_result_return_route
    readonly_return = readonly_result_return_route(root,snapshot,request)
    if sender not in {"operations", goal.get("responsible_assistant"), *producers} and not brand_executor and readonly_return is None:
        raise w.WorkflowError("original goal participant required; no authority delegation by metadata")
    autonomous_route=readonly_return or message_route(root,snapshot,request)
    if autonomous_route is not None:
        if changes:
            return outcome('authorization_change_required',changes,confirmation=True)
        return {**outcome('within_original_authorization',['actual_owner_delegated_original_task_report']), 'current_mode':autonomous_route['mode']}
    delegation = _owner_decision_delegation(root)
    if request.get('action_id') == 'assign-same-task-technical-review:fc-20261017-next12-old-house-development-handoff-v1':
        from goal_source_recovery import oldhouse_technical_preflight
        oldhouse_technical_preflight(root,request)
        if changes:
            return outcome('authorization_change_required',changes,confirmation=True)
        return outcome('within_original_authorization',
                       ['exact_same_task_technical_responsibility_without_business_owner_transfer'])
    is_notice = (request['action_class']=='thread_message'
                 and request['scope']==f'department_result:{task_id}:{sender}'
                 and request.get('action_id','').startswith('notify-result-'))
    if is_notice:
        from result_coordination import exact_identity, _validate_queued, result_lane
        identity=exact_identity(request.get('result_identity',{}))
        if identity['task_id']!=task_id or identity['sender_department']!=sender:
            raise w.WorkflowError('notice must retain its actual original result identity')
        _validate_queued(root,identity)
        route=result_lane(root,identity)
        if request.get('target_department')!=route.get('target_department'):
            raise w.WorkflowError('notice must use its single current actual receiver')
        if changes:
            return outcome('authorization_change_required',changes,confirmation=True)
        # Closing an accepted scope never drops a still-undelivered result.
        return outcome('within_original_authorization',['existing_result_return_only_no_new_assignment'])
    if request["scope"] not in goal["authorized_scope"]:
        changes = changes + ["new_scope"]
    if request["action_class"] == "thread_message":
        target = request.get("target_department")
        declarations = [x for x in execution_collaboration_scopes(root, snapshot)
                        if x.get("target_department") == target and x.get("scope") == request["scope"]
                        and x.get("sender_department") == goal["primary_owner"]
                        and sender in {goal['primary_owner'],goal.get('responsible_assistant')}]
        exact_preapproved = approved_action(root,snapshot,request) if target not in registry else None
        if target not in {*producers, goal.get("responsible_assistant")} and not declarations and not exact_preapproved:
            changes = changes + ["new_department"]
        bindings = w.read_json(Path(root) / "data/department-registry.json").get("collaboration_bindings", {})
        binding = (_collaboration_binding(root, snapshot, target) or {} if declarations or exact_preapproved
                   else registry.get(target, {}).get("chat_binding", {}))
        if request.get("target_project_id") and binding.get("project_id") != request["target_project_id"]:
            return outcome("authorization_change_required", changes, confirmation=True) if changes else outcome(
                "internal_repair_required", ["actual_registered_target_project_mismatch"])
        if not binding or registry.get(target, {}).get("new_dispatch_enabled") is False:
            repairs = repairs + ["binding"]
    elif request["action_class"] in w.EXTERNAL_ACTION_CLASSES:
        declared = [x for x in goal.get("required_execution_actions", [])
                    if all(x.get(k) == request.get(k) for k in
                           ("action_id", "action_class", "scope", "department"))]
        if len(declared) != 1:
            if request.get("draft_admission") is not None:
                from chatgpt_fe689_draft_admission import action_binding
                action_binding(root, snapshot, request)
            else:
                # Cannot infer a new production action from broad prose or a PASS.
                return outcome("original_action_binding_required", ["recover_exact_authorized_production_action"] + changes,
                               confirmation=bool(changes))
        if request.get("department",sender) not in producers and not brand_executor:
            raise w.WorkflowError("original declared production executor required")
    elif request["action_class"] != "internal_control_candidate":
        raise w.WorkflowError("known original action class required")
    if changes:
        return outcome("authorization_change_required", changes, confirmation=True)
    if snapshot.get("current_state") in w.TERMINAL_STATES:
        return outcome("completed_scope_readback_required", ["read_actual_completion_before_resuming_closed_scope"])
    if repairs:
        return outcome("internal_repair_required", repairs)
    return outcome("within_original_authorization", ["same_goal_scope_and_collaborators"])


def validate_goal(root, goal, *, task_id=None):
    from department_autonomy import MODE as autonomous_model, validate_general_goal
    if isinstance(goal,dict) and (goal.get('delivery_model')==autonomous_model or not goal.get('responsible_assistant')):
        return validate_general_goal(root,goal,task_id)
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
    if assistant.get('historical_coordination_authority') is not None:
        assistant={**assistant,'new_dispatch_enabled':assistant.get('historical_new_dispatch_enabled',False),
                   'coordination_authority':assistant.get('historical_coordination_authority',{})}
    authority = assistant.get("coordination_authority", {})
    if (authority.get("routine_decisions") is not True
            or assistant.get("new_dispatch_enabled") is False):
        raise w.WorkflowError("assigned assistant lacks acceptance capability")
    producers = result["producer_departments"]
    if (len(set(producers)) != len(producers) or result["primary_owner"] not in producers
            or any(d not in registry or registry[d].get("new_dispatch_enabled") is False for d in producers)
            or result["responsible_assistant"] in producers):
        raise w.WorkflowError("registered independent producers and reviewer required; no self review")
    if result.get("parent_task_id"):
        w.validate_task_id(result["parent_task_id"])
    mode=result.setdefault('execution_mode','authorized_selfcheck_then_execute')
    if mode not in {'authorized_selfcheck_then_execute','legacy_exact_gate'}:
        raise w.WorkflowError('known execution mode required; goal metadata grants no new platform permission')
    actions = result.setdefault("required_execution_actions", [])
    if not isinstance(actions, list) or len(actions) > 100:
        raise w.WorkflowError("bounded declared production actions required")
    from brand_v4_issuer_executor import context as brand_executor_context
    brand_executor = brand_executor_context(root, result)
    identities = []
    for action in actions:
        if (not isinstance(action, dict) or not action.get("action_id")
                or action.get("action_class") not in w.EXTERNAL_ACTION_CLASSES
                or action.get("scope") not in result["authorized_scope"]
                or (action.get("department") not in producers and not brand_executor)):
            raise w.WorkflowError("declared production action must use exact existing scope/producer/channel")
        if brand_executor:
            brand_executor_context(root, result, action)
        identities.append(tuple(action.get(k) for k in ("action_id", "action_class", "scope", "department")))
    if len(set(identities)) != len(identities):
        raise w.WorkflowError("unique production action identities required")
    next_actions=result.get('continuation_actions', [])
    if not isinstance(next_actions,list) or len(next_actions)>100:
        raise w.WorkflowError('bounded original authorized continuation actions required')
    seen_next=set()
    for action in next_actions:
        if (not isinstance(action,dict) or not action.get('action_id') or action['action_id'] in seen_next
                or action.get('action_class')!='thread_message'
                or action.get('target_department') not in producers
                or action.get('scope') not in result['authorized_scope']
                or not isinstance(action.get('payload'),dict)
                or w.file_digest(root,action['payload'].get('path',''))!=action['payload']):
            raise w.WorkflowError('exact original permitted next action/producer/scope/message required')
        seen_next.add(action['action_id'])
    completion_contract_state(result)
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
    from goal_continuity import shared_capable
    if (not shared_capable(root, result['responsible_assistant'], result)
            and (result["acceptance_capability"] not in authority.get("review_capabilities", [])
            or (result["responsible_assistant"] == "operations-assistant-3"
                and result["acceptance_capability"] == "development"
                and isinstance(authority.get("technical_review_backup"), dict)))):
        from technical_review_backup import qualified_initial_review
        if not qualified_initial_review(root, result["responsible_assistant"], result,
                                        task_id=task_id, require_responsibility=False):
            raise w.WorkflowError("assigned assistant lacks acceptance capability or adopted exact initial review qualification")
    return result


def restore_goal(root, snapshot):
    result = copy.deepcopy(snapshot)
    frozen_completion = None
    for row in w.read_jsonl(Path(root) / w.WORKFLOW_EVENTS):
        if row.get("task_id") != snapshot.get("task_id"):
            continue
        detail = row.get("details", {})
        if isinstance(detail.get("goal_delivery"), dict):
            candidate = detail["goal_delivery"]
            completion = {key: candidate.get(key) for key in
                          ("completion_criteria", "completion_kind", "completion_requirements")}
            if frozen_completion is not None and completion != frozen_completion:
                raise w.WorkflowError("original completion criteria, kind and requirements are immutable")
            frozen_completion = completion
            result["goal_delivery"] = detail["goal_delivery"]
    if enabled(root, result):
        goal = result["goal_delivery"]
        if w.file_digest(root, goal["authorization_pin"]["path"]) != goal["authorization_pin"]:
            raise w.WorkflowError("frozen human authorization changed")
    return result


def bind_goal(root, task_id, goal):
    task_id = w.validate_task_id(task_id)
    goal = validate_goal(root, goal, task_id=task_id)
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
        from department_autonomy import required_roles
        if not required_roles(goal) <= planned:
            raise w.WorkflowError("complete-goal producers and assistant must be planned")
        w.append_workflow_event(root, task_id, snapshot["current_state"], {"goal_delivery": goal, "goal_delivery_bound": True})
        snapshot["goal_delivery"] = goal
        snapshot["updated_at"] = w.utc_timestamp()
        w.atomic_write_json(w.snapshot_path(root, task_id), snapshot)
    return {"result": "bound", "goal_delivery": goal, "external_permission_issued": False}



def _native_document(root, pin):
    from qa_review_plan import _review_source_document, _review_native_containers, _review_raw_native_result
    try:
        value = _review_source_document(root, pin)
        _review_native_containers(value)
        if "content" in value and not value.get("thread"):
            value = _review_raw_native_result(value)
        _review_native_containers(value)
        return value
    except (ValueError, TypeError, KeyError) as exc:
        raise w.WorkflowError("successful complete native delegation evidence required: " + str(exc)) from exc


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
    from technical_review_backup import review_capable
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
            or not review_capable(root, role, goal, task_id=snapshot["task_id"])):
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
    from department_autonomy import autonomous_goal, professional
    if autonomous_goal(goal):
        return (role=='operations' or role in goal['producer_departments'] and professional(root,role)) and (scope is None or scope in goal['authorized_scope'])
    authority = w.department_registry(root).get(role, {}).get("coordination_authority", {})
    authorized_owner=(role==goal['primary_owner'] and any(a.get('scope')==scope for a in goal.get('continuation_actions',[])))
    return (role in {"operations", goal["responsible_assistant"]} or authorized_owner) and (
            (scope is None or scope in goal['authorized_scope'])) and (role=='operations' or authorized_owner or authority.get('dispatch_approved_next') is True)


def approved_action(root, snapshot, requested):
    """A scoped goal does not authorize an arbitrary next message payload."""
    goal = snapshot["goal_delivery"]
    rows = [x for x in goal.get("approved_actions", []) if isinstance(x, dict)
            and all(x.get(k) == requested.get(k) for k in requested)]
    if len(rows) != 1 or not w.SHA256_PATTERN.fullmatch(str(requested.get("payload_sha256", ""))):
        return None
    row = rows[0]
    _readonly_coordination_action(root, snapshot, row, "read")
    pin = row.get("payload")
    if (not isinstance(pin, dict) or w.file_digest(root, pin.get("path", "")) != pin
            or pin["sha256"] != requested["payload_sha256"]):
        return None
    if row.get("goal_responsibility_dispatch"):
        from parent_initial_dispatch import validate_responsibility_action
        validate_responsibility_action(root, snapshot, row, phase="policy")
    elif row.get("parent_task_id"):
        from parent_initial_dispatch import validate_action
        validate_action(root, snapshot, row, phase="policy")
    elif row.get("action_id") == CONDO_FAQ_V7_POST_CANDIDATE_ACTION:
        _condo_faq_v7_post_candidate_action(root, snapshot, row)
    return row


def _readonly_coordination_action(root, snapshot, action, phase):
    if action.get('professional_execution_source') is not None:
        from professional_cms_execution import validate_message
        validate_message(root, snapshot, action)
    if (snapshot.get("task_id") == "fc-20261021-brand-corrected-v4-site-production-stage-v1"
            and action.get("target_department") == "publishing"):
        from owner_nonpayment_coordination import validate_action
        validate_action(root, snapshot, action, phase=phase)


def execution_collaboration_scopes(root, snapshot):
    """Frozen declarations plus verified append-only execution-source collaboration."""
    from professional_cms_execution import collaboration_scopes
    return collaboration_scopes(root, snapshot)


def _collaboration_binding(root, snapshot, role):
    binding = w.read_json(Path(root) / "data/department-registry.json").get("collaboration_bindings", {}).get(role)
    if not binding and snapshot.get("task_id") == "fc-20261021-brand-corrected-v4-site-production-stage-v1" and role == "publishing":
        from owner_nonpayment_coordination import binding as readonly_binding
        binding = readonly_binding(root, snapshot, role)
    if not binding:
        appended = [d for d in execution_collaboration_scopes(root, snapshot)
                    if d.get('target_department') == role
                    and d not in snapshot['goal_delivery'].get('collaboration_scopes', [])]
        fixed = w.department_registry(root).get(role, {}).get('chat_binding')
        if appended and fixed:
            binding = {**fixed, 'thread_id': fixed['task_id']}
    return binding


def collaboration_route(root, snapshot, requested):
    binding = _collaboration_binding(root, snapshot, requested.get("target_department"))
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
            if prior.get("action_id") == requested.get("action_id") and prior.get("status") in {"sent", "queue_accepted", "message_received", "result_received"}:
                reasons.append("goal_collaboration_already_dispatched_read_before_retry")
        if w.file_digest(root, goal["authorization_pin"]["path"]) != goal["authorization_pin"]:
            reasons.append("goal_collaboration_original_human_provenance_changed")
        action = approved_action(root, snapshot, {k:v for k,v in requested.items() if k != "delivery_mode"})
        if action is None:
            reasons.append("goal_collaboration_frozen_approved_message_required")
        else:
            _readonly_coordination_action(root, snapshot, action, "policy")
            pin = goal.get('current_route_observations',{}).get(action['action_id']) or action.get("live_identity")
            if not isinstance(pin, dict) or w.file_digest(root, pin.get("path", "")) != pin:
                raise w.WorkflowError("exact live proof required")
            live = w.read_json(w.safe_path(root, pin["path"]))
            observed = w._parse_observed_at(live.get("observed_at"))
            targets = [x for x in live.get("threads", []) if x.get("id") == binding["thread_id"]]
            sources = [x for x in live.get("threads", []) if x.get("id") == source.get("task_id")]
            from goal_source_recovery import actual_target_turn_status
            target_state = (actual_target_turn_status(root, live, targets[0],
                            {**binding, 'task_id': binding['thread_id']})
                            if len(targets) == 1 else 'unknown_target')
            now = dt.datetime.now(dt.timezone.utc)
            queue_mode = requested.get('delivery_mode') == 'official_native_queue'
            if queue_mode:
                if snapshot.get('current_state') in w.TERMINAL_STATES:
                    raise w.WorkflowError('terminal original collaboration cannot queue')
                intents = [e for e in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS)
                           if e.get('task_id') == snapshot['task_id'] and e.get('details', {}).get(
                               'collaboration_queue_intent', {}).get('action_id') == action['action_id']]
                if intents:
                    raise w.WorkflowError('original queue intent exists; read its effect before retry')
                from goal_source_recovery import collaboration_queue_binding
                collaboration_queue_binding(root, snapshot, action)
                from department_event_dispatcher import native_queue_capability
                native_queue_capability(root)
                if live.get('delivery_mode') != 'official_native_queue':
                    raise w.WorkflowError('same normal official queue observation required')
                inventory = _collaboration_native(root, live.get('actual_native_observation'))
                for fixed, selected in ((source, sources), ({**binding, 'task_id':binding['thread_id']}, targets)):
                    actual = [x for x in [*inventory.get('threads', []), *inventory.get('pinnedThreads', [])] if x.get('id') == fixed['task_id']]
                    if len(actual) != 1 or len(selected) != 1 or actual[0] != selected[0]:
                        raise w.WorkflowError('original native inventory rows required for queue')
                target_page = _collaboration_native(root, live.get('actual_native_target_turns', {}).get(binding['thread_id']))
                if (target_page.get('thread', {}).get('kind') != 'codex' or
                        target_page.get('thread', {}).get('hostId') != binding.get('host_id')):
                    raise w.WorkflowError('original native external kind/host required')
            if (observed is None or not 0 <= (now - observed).total_seconds() <= 300
                    or len(targets) != 1 or len(sources) != 1
                    or any(targets[0].get(k) != v for k, v in {"projectId": binding["project_id"],
                           "title": binding["title"], "cwd": binding["cwd"]}.items())
                    or target_state not in ({'idle', 'active', *({'notLoaded'} if action.get('professional_execution_source') else set())} if queue_mode else {'idle'})
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
    from technical_review_backup import review_capable
    if not review_capable(root, assignment_change.get("target_assistant"), goal,
                          task_id=identity["task_id"], transfer_from=assignment_change.get("previous_assistant")):
        raise w.WorkflowError("target assistant lacks task capability or approved backup methods")
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
    if action_class == "cms_write":
        from professional_cms_execution import execution_context
        context = execution_context(root, snapshot, {"task_id":snapshot["task_id"], "action_id":action_id,
                    "action_class":action_class, "scope":scope, "department":department})
        if context is not None:
            return context["preflight"]
    from professional_web_execution import applies as original_external_WEB, preflight as original_external_preflight
    if original_external_WEB(root, snapshot["task_id"], action_class):
        return original_external_preflight(root, snapshot["task_id"], action_id, action_class, scope, department)[0]
    from tools.shop_office_web_execution import applies as exact_WEB_applies, preflight as exact_WEB_preflight
    if exact_WEB_applies(snapshot.get("task_id"), action_class):
        return exact_WEB_preflight(root, action_id, action_class, scope, department)[0]
    if snapshot.get('task_id') == 'fc-20261025-shop-office-existing-six-and-five-implementation-release-v1' and action_class == 'cms_write':
        from tools.shop_office_six_field_execution import preflight as exact_cms_preflight
        return exact_cms_preflight(root, snapshot, action_id, action_class, scope, department)[0]
    from paid_three_page_bounded_cms import exact_tuple, preflight
    if exact_tuple(snapshot.get("task_id"), action_id, scope, department, action_class):
        return preflight(root, snapshot, action_id, action_class, scope, department)
    from brand_v4_issuer_executor import action_context as brand_action_context
    brand_executor = brand_action_context(root, snapshot, action_id, action_class, scope, department)
    if scope not in goal["authorized_scope"] or (department not in goal["producer_departments"] and not brand_executor):
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
    if brand_executor:
        from brand_v4_issuer_executor import preflight as brand_preflight
        brand_preflight(root, snapshot, item)
    return item


def status(root, task_id):
    from department_autonomy import current_mode,autonomous_goal,legacy_status
    original=w.read_json(w.snapshot_path(root,task_id))
    if current_mode(root) and isinstance(original.get('goal_delivery'),dict) and not autonomous_goal(original['goal_delivery']):
        return legacy_status(root,original)

    snapshot, _ = w.reconcile_workflow(root, task_id=task_id)
    if not enabled(root, snapshot):
        raise w.WorkflowError("bound complete goal required")
    goal = snapshot["goal_delivery"]
    from department_autonomy import autonomous_goal,completion as autonomous_completion
    if autonomous_goal(goal):
        proof=autonomous_completion(root,snapshot)
        return {'task_id':task_id,'state':'completed_scope' if proof['state']=='PROVEN' else 'executing',
                'primary_owner':goal['primary_owner'],'completion_obligations':proof,'responsible_assistant':None,
                'HQ_second_review_required':False,'business_goal_closed':False,'delivery_model':goal['delivery_model']}
    from direct_system_repair import context as direct_context, completion_view
    takeover = direct_context(root, task_id)
    if takeover is not None:
        complete = completion_view(root, snapshot, takeover)
        return {"task_id": task_id, "state": "completed_scope" if complete["control_scope_completed"]
                else "direct_execution_followthrough", "native_workflow_state": snapshot["current_state"],
                "primary_owner": "operations", "actual_executor": "operations",
                "responsible_assistant": None,
                "historical_responsible_assistant": takeover["historical_responsible_assistant"],
                "completion_criteria": goal["completion_criteria"], "completion_obligations": complete,
                "source_adopted": True, "HQ_second_review_required": False,
                "business_goal_closed": False, "control_scope_completed": complete["control_scope_completed"]}
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


def _current_goal_owners(root):
    owners = {}
    for row in w.read_jsonl(Path(root) / w.WORKFLOW_EVENTS):
        goal = row.get('details', {}).get('goal_delivery')
        if isinstance(goal, dict):
            owners[row.get('task_id')] = goal.get('responsible_assistant')
    from direct_system_repair import owners as direct_owners
    owners.update(direct_owners(root))
    return owners


def pending(root, role):
    registry = w.department_registry(root)
    if registry.get(role, {}).get("coordination_authority", {}).get("routine_decisions") is not True:
        raise w.WorkflowError("registered assistant coordinator required")
    # Registry and global model failures are not downgraded to per-task errors.
    enabled(root)
    from result_coordination import result_lane, notification_plan
    categories = {key: [] for key in ("pending", "followthrough_pending", "collaboration_pending",
                    "technical_review_pending",
                    "collaboration_not_proven", "HQ_knowledge_pending", "named_due_dependencies",
                    "named_waiting_dependencies", "historical_resolved_control_records", "completion_followthrough")}
    owned, errors, completion_status = [], [], {}
    current_owners = _current_goal_owners(root)
    for path in sorted((Path(root) / w.WORKFLOW_DIR).glob("*.json")):
        try:
            raw = w.read_json(path)
            if not isinstance(raw, dict):
                raise w.WorkflowError("current task snapshot must be an object")
            if raw.get('task_id') != path.stem:
                raise w.WorkflowError("current task snapshot identity differs from its exact path")
            if current_owners.get(path.stem, raw.get("goal_delivery", {}).get("responsible_assistant")) == role:
                owned.append(path.stem)
            elif (role == 'operations-assistant-2'
                  and path.stem == 'fc-20261017-next12-old-house-development-handoff-v1'):
                from goal_source_recovery import read_oldhouse_technical_source
                if read_oldhouse_technical_source(root) is not None:
                    owned.append(path.stem)
        except (w.WorkflowError, ValueError, OSError, KeyError, TypeError, AttributeError) as exc:
            errors.append(_task_block(path.stem, "ownership_unresolved", exc))
    for path in sorted((Path(root) / w.RESULT_HANDOFF_DIR).glob('*.jsonl')):
        if path.stem in owned:
            continue
        try:
            admitted = [w.scheduled_result_source(root, path.stem, department) for department in registry]
            if not any(source and source.get('responsible_assistant') == role for source in admitted):
                continue
            for row in w._result_handoff_rows(root, path.stem):
                if row.get('event') != 'notification_queued':
                    continue
                lane = result_lane(root, row)
                if lane.get('source_mode') == 'scheduled_run' and lane.get('target_department') == role:
                    owned.append(path.stem)
                    break
        except (w.WorkflowError, ValueError, OSError, KeyError, TypeError, AttributeError) as exc:
            errors.append(_task_block(path.stem, role, exc))
    for task_id in sorted(set(owned)):
        local = {key: [] for key in categories}
        try:
            rows = w._result_handoff_rows(root, task_id)
            grouped = {}
            for row in rows:
                key = w._result_identity(row)
                entry = grouped.setdefault(key, {"task_id": task_id, "sender_department": key[0],
                            "candidate_version": key[1], "result_sha256": key[2], "received": False,
                            "decided": False, "queued": False, "controller_followthrough": "pending"})
                if row["event"] == "notification_queued": entry["queued"] = True
                elif row["event"] == "controller_received": entry["received"] = True
                elif row["event"] == "controller_decision":
                    entry.update(decided=True, controller_decision=row.get("decision"), next_owner=row.get("next_owner"),
                                 next_action=row.get("next_action"), unblock_condition=row.get("unblock_condition"),
                                 remaining_scope=row.get("remaining_scope", []), accepted_scope=row.get("accepted_scope", []))
                elif row["event"] == "controller_followthrough":
                    entry.update(controller_followthrough=row.get("followthrough_status"), next_check_at=row.get("next_check_at"),
                                 unblock_condition=row.get("unblock_condition", entry.get("unblock_condition")))
            for entry in grouped.values():
                lane = result_lane(root, entry)
                entry.update(result_lane=lane['lane'], target_department=lane.get('target_department'))
                if lane.get('source_mode') == 'collaboration':
                    if entry['decided'] and entry.get('controller_decision') == 'close_scope':
                        from collaboration_scope_close import readback_collaboration_scope_close
                        decision = next(row for row in reversed(rows) if row.get('event') == 'controller_decision'
                                        and w._result_identity(row) == w._result_identity(entry))
                        closed = readback_collaboration_scope_close(root, decision, rows)
                        local['historical_resolved_control_records'].append({**entry, 'closed_collaboration_scope': closed['acceptance_scope'],
                                                                           'business_goal_closed': False})
                    continue
                if lane['lane'] == 'HQ_knowledge':
                    entry['acceptance_proven'] = lane.get('acceptance_proven', False)
                    if not entry['received']:
                        local['HQ_knowledge_pending'].append(entry)
                    continue
                if lane['lane'] != 'professional_acceptance' or lane.get('target_department') != role:
                    continue
                if not entry['decided'] and (entry['queued'] or entry['received']):
                    local['pending'].append(entry)
                if entry['decided'] and w._followthrough_due(entry):
                    local['followthrough_pending'].append(entry)
                    if entry.get('controller_decision') == 'wait_external':
                        local['named_due_dependencies'].append(entry)
                if entry['decided'] and w._followthrough_waiting(entry):
                    local['named_waiting_dependencies'].append(entry)
                if entry['decided'] and (entry.get('controller_decision') == 'close_scope'
                        or entry.get('controller_followthrough') not in {None, 'pending', 'external_wait_registered', 'blocked_with_owner'}):
                    local['historical_resolved_control_records'].append({**entry, 'business_goal_closed': False})
            raw = w.read_json(w.snapshot_path(root, task_id))
            if raw:
                if raw.get('task_id') != task_id:
                    raise w.WorkflowError("current task snapshot identity differs from its exact path")
                snapshot = restore_goal(root, raw)
                if (role == 'operations-assistant-2'
                        and task_id == 'fc-20261017-next12-old-house-development-handoff-v1'):
                    from goal_source_recovery import read_oldhouse_technical_source
                    technical=read_oldhouse_technical_source(root)
                    if technical is not None:
                        local['technical_review_pending'].append({**technical,
                            'status':'awaiting_independent_technical_review',
                            'business_decision_owner':'operations-assistant',
                            'technical_verdict_recorded':False,
                            'production_permission_issued':False})
                if enabled(root, snapshot) and snapshot['goal_delivery']['responsible_assistant'] == role:
                    receipts, invalid = w._validate_receipt_chain(root, task_id)
                    if invalid or w.validate_workflow_events(root, task_id):
                        raise w.WorkflowError("owned goal exact current receipt/event chain requires recovery")
                    local['collaboration_pending'].extend(_collaboration_pending(root, snapshot, role))
                    if snapshot.get('current_state') not in w.TERMINAL_STATES:
                        local['collaboration_not_proven'].extend(state for state in _collaboration_wait_states(root, snapshot)
                                                                 if state['proof_state'] == 'NOT_PROVEN')
                    completion = completion_obligations(root, snapshot, receipts)
                    local['completion_followthrough'].extend(remaining_followthrough(root, snapshot, receipts, completion=completion))
            # Publish a task's projection only after all its readers pass.
            for key in categories:
                categories[key].extend(local[key])
            if raw and enabled(root, snapshot) and snapshot['goal_delivery']['responsible_assistant'] == role:
                completion_status[task_id] = completion
        except (w.WorkflowError, ValueError, OSError, KeyError, TypeError, AttributeError) as exc:
            errors.append(_task_block(task_id, role, exc))
    deliveries = notification_plan(root, None)
    notifications = [row for row in deliveries['notifications']
                     if row.get('delivery_owner') == role or row.get('delivery_identity', row.get('identity', {})).get('target_department') == role
                     or row.get('route', {}).get('target_department') == role]
    delivery_errors = [error for error in deliveries.get('errors', [])
                       if error.get('owner') in {None, role} or error.get('delivery_owner') == role
                       or error.get('task_id') in owned]
    errors.extend(delivery_errors)
    from goal_continuity import shared_pending
    shared_pool=shared_pending(root,role)
    result = {key: deduplicate_records(rows) for key, rows in categories.items()}
    result['shared_pool_pending']=shared_pool['results']
    result['shared_pool_errors']=shared_pool['errors']
    for key in categories:
        result[key + '_count'] = len(result[key])
    result.update(coordinator_role=role, control_records_are_business_jobs=False,
                  professional_pending_count=len(result['pending']),
                  historical_resolved_control_count=len(result['historical_resolved_control_records']),
                  named_waiting_dependency_count=len(result['named_waiting_dependencies']),
                  named_due_dependency_count=len(result['named_due_dependencies']),
                  notification_delivery_pending=deduplicate_records(notifications, delivery=True),
                  notification_errors=deduplicate_records(delivery_errors),
                  task_errors=deduplicate_records(errors), completion_status=completion_status,
                  durable_inbox_does_not_wake_ended_chat=True,
                  review_timing={"active_review_seconds": "NOT_MEASURED", "dependency_wait_seconds": "NOT_MEASURED",
                                 "administrative_seconds": "NOT_MEASURED", "wall_clock_is_active_review": False,
                                 "reason": "no recorded actual activity intervals; queue age is not review time"})
    result['shared_pool_pending_count']=len(result['shared_pool_pending'])
    result['notification_delivery_pending_count'] = len(result['notification_delivery_pending'])
    result['followthrough_pending_count'] = len(result['followthrough_pending'])
    result['total_actionable_count'] = len(deduplicate_records(result['pending'] + result['followthrough_pending']
              + result['collaboration_pending'] + result['collaboration_not_proven']
              + [row for row in result['completion_followthrough'] if row.get('actionable')] + result['shared_pool_pending'])) + len(
                  [row for row in result['notification_delivery_pending'] if row.get('actionable')])
    return result


def record_preflight(root, task_id, input_path):
    from department_autonomy import autonomous_goal,register_preflight
    if autonomous_goal(w.read_json(w.snapshot_path(root,task_id)).get('goal_delivery')):
        return register_preflight(root,task_id,input_path)
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


CONDO_FAQ_V7_POST_CANDIDATE_ACTION = "A1-condo-faq-v7-post-candidate-publishing-selfcheck-20261014-v1"
CONDO_FAQ_V7_POST_CANDIDATE_SCHEMA = "condo-faq-v7-post-candidate-publishing-resume/v1"


def _condo_faq_v7_post_candidate_message(action, source, target):
    """One finite message: ask publishing to run its original gates, grant nothing."""
    return {"schema": CONDO_FAQ_V7_POST_CANDIDATE_SCHEMA,
            "task_id": target["task_id"], "sender_department": "operations-assistant",
            "target_department": "publishing", "original_cms_action_id": target["action_id"],
            "scope": target["scope"], "candidate_version": target["candidate_version"],
            "candidate_acceptance_record_id": source["receipt_id"],
            "candidate_acceptance_record_hash": source["receipt_hash"],
            "bounded_report": source["bounded_report"],
            "candidate": source["candidate"],
            "next_step": "original_publishing_selfcheck_then_existing_protected_execution_gates",
            "production_write_allowed": False, "external_permission_issued": False,
            "CMS_Save_claimed": False, "business_goal_closed": False}


def _condo_faq_v7_post_candidate_action(root, snapshot, action):
    """Authenticate the one adopted candidate-only receipt before a new message."""
    from managed_cms_permit_issuer import (CONDO_FAQ_V7_TARGET, CONDO_FAQ_PARENT_TASK,
                                           validate_goal_cms_acceptance)
    root = Path(root).resolve()
    target = CONDO_FAQ_V7_TARGET
    goal = snapshot.get("goal_delivery", {})
    source = action.get("condo_faq_v7_post_candidate_source")
    if (snapshot.get("task_id") != target["task_id"]
            or snapshot.get("current_state") in w.TERMINAL_STATES
            or goal.get("parent_task_id") != CONDO_FAQ_PARENT_TASK
            or goal.get("responsible_assistant") != "operations-assistant"
            or goal.get("producer_departments") != ["content-organic-website", "publishing"]
            or goal.get("authorized_scope") != [target["scope"]]
            or action.get("task_id") != target["task_id"]
            or action.get("action_id") != CONDO_FAQ_V7_POST_CANDIDATE_ACTION
            or action.get("action_class") != "thread_message"
            or action.get("scope") != target["scope"]
            or action.get("sender_department") != "operations-assistant"
            or action.get("target_department") != "publishing"
            or action.get("decision_record_id")
            or not isinstance(source, dict)
            or set(source) != {"receipt_id", "receipt_hash", "review_outbox",
                               "source_sidecar", "bounded_report", "candidate",
                               "producer_outbox", "review_plan", "human_authorization"}):
        raise w.WorkflowError("exact adopted condo FAQ post-candidate message identity required")
    registry = w.department_registry(root)
    sender = registry["operations-assistant"]["chat_binding"]
    receiver = registry["publishing"]["chat_binding"]
    if (action.get("source_project_id") != sender.get("project_id")
            or any(action.get(k) != receiver.get(v) for k, v in
                   {"target_project_id": "project_id", "target_thread_id": "task_id",
                    "target_thread_title": "title", "target_cwd": "cwd",
                    "target_sidebar_section_id": "sidebar_section_id"}.items())
            or sender.get("cwd") != str(root) or receiver.get("cwd") != str(root)):
        raise w.WorkflowError("original fixed A1 to publishing project binding required")
    accepted = validate_goal_cms_acceptance(root, target, "publish")
    rows, invalid = w._validate_receipt_chain(root, target["task_id"])
    matches = [row for row in rows if row.get("receipt_id") == accepted.get("candidate_acceptance_record_id")]
    if invalid or len(matches) != 1 or matches[0].get("receipt_hash") != accepted.get("candidate_acceptance_record_hash"):
        raise w.WorkflowError("one authentic adopted A1 bounded receipt required")
    receipt = matches[0]
    evidence = receipt.get("evidence", [])
    expected = {"receipt_id": receipt["receipt_id"], "receipt_hash": receipt["receipt_hash"],
                "review_outbox": accepted["review_outbox"],
                "source_sidecar": evidence[1] if len(evidence) == 2 else None,
                "bounded_report": accepted["bounded_report"],
                "candidate": accepted["candidate"],
                "producer_outbox": accepted["producer_outbox"],
                "review_plan": accepted["review_plan"],
                "human_authorization": accepted["authorization_pin"]}
    if (source != expected or evidence != [source["review_outbox"], source["source_sidecar"]]
            or accepted.get("acceptance_model") != "condo_faq_v7_candidate_scope_only_v1"
            or accepted.get("verdict") != "pass_candidate_only"
            or accepted.get("goal_completion_claimed") is not False
            or accepted.get("production_write_allowed") is not False):
        raise w.WorkflowError("exact bounded receipt, source or candidate-only conclusion changed")
    for item in (source["review_outbox"], source["source_sidecar"], source["bounded_report"],
                 source["candidate"], source["producer_outbox"], source["review_plan"],
                 source["human_authorization"]):
        if w.file_digest(root, item["path"]) != item:
            raise w.WorkflowError("original condo FAQ continuation source bytes changed")
    payload = action.get("payload")
    if (not isinstance(payload, dict) or w.file_digest(root, payload.get("path", "")) != payload
            or payload.get("sha256") != action.get("payload_sha256")):
        raise w.WorkflowError("exact post-candidate publishing message bytes required")
    expected_message = _condo_faq_v7_post_candidate_message(action, source, target)
    canonical = (json.dumps(expected_message, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
    if w.safe_path(root, payload["path"]).read_bytes() != canonical:
        raise w.WorkflowError("one bounded post-candidate publishing instruction required")
    return accepted


def _condo_faq_v7_post_candidate_preflight(root, task_id, input_path, action):
    """Complete source proof outside the write lock; freeze validation-used bytes."""
    from managed_cms_permit_issuer import CONDO_FAQ_V7_BASE, CONDO_FAQ_V7_TARGET
    root = Path(root).resolve()
    with w.request_validation_context() as validation:
        validation.strict_unchanged = True
        if validation.json(w.safe_path(root, input_path)) != action:
            raise w.WorkflowError("post-candidate action changed before validation")
        validation.bytes(w.snapshot_path(root, task_id))
        for spec in (CONDO_FAQ_V7_TARGET["candidate"], CONDO_FAQ_V7_TARGET["rollback"]):
            validation.bytes(w.safe_path(root, spec[0]))
        for path in (root / CONDO_FAQ_V7_BASE).glob("*.json"):
            validation.bytes(path)
        for name in ("data/department-registry.json", "data/task-contract.json", w.WORKFLOW_EVENTS):
            path = root / name
            if path.is_file():
                validation.bytes(path)
        snapshot = restore_goal(root, w.read_json(w.snapshot_path(root, task_id)))
        _condo_faq_v7_post_candidate_action(root, snapshot, action)
        validation.recheck()
    return validation


def record_approved_action(root, task_id, input_path):
    """Freeze a precise routine decision, or owner action in an original declared collaboration scope."""
    action = w.read_json(w.safe_path(root, input_path))
    if action.get("schema") == "professional-external-WEB-production-source/v1":
        from professional_web_execution import record_source
        return record_source(root, task_id, input_path)
    if action.get("schema") == "professional-cms-issuer-contract/v1":
        from professional_cms_issuer import record_contract
        return record_contract(root, task_id, input_path)
    if action.get("schema") == "professional-cms-execution-source-registration/v1":
        from professional_cms_execution import record
        return record(root, task_id, input_path)
    if action.get("schema") == "current-autonomous-readonly-coordination-action/v1":
        from department_autonomy import record_readonly_coordination
        return record_readonly_coordination(root, task_id, input_path)
    if action.get("schema") == "shop-office-original-WEB-execution-registration/v1":
        from tools.shop_office_web_execution import record_registration
        return record_registration(root, task_id, input_path)
    special = action.get("action_id") == CONDO_FAQ_V7_POST_CANDIDATE_ACTION or "condo_faq_v7_post_candidate_source" in action
    validation = (_condo_faq_v7_post_candidate_preflight(root, task_id, input_path, action)
                  if special else None)
    with w.workflow_lock(root):
        if validation is not None:
            validation.recheck()
        snapshot = restore_goal(root, w.read_json(w.snapshot_path(root, task_id)))
        if not enabled(root, snapshot):
            raise w.WorkflowError("complete original goal required")
        goal = snapshot["goal_delivery"]
        _readonly_coordination_action(root, snapshot, action, "bind")
        responsibility_initial = bool(action.get("goal_responsibility_dispatch"))
        parent_linked_initial = bool(action.get("parent_task_id"))
        if responsibility_initial:
            from parent_initial_dispatch import validate_responsibility_action
            validate_responsibility_action(root, snapshot, action, phase="prepare")
        elif parent_linked_initial:
            from parent_initial_dispatch import validate_action
            validate_action(root, snapshot, action, phase="prepare")
        assistant = goal.get('responsible_assistant')
        authorized_senders = {goal['primary_owner']} | ({assistant} if assistant else set())
        declarations = [d for d in execution_collaboration_scopes(root, snapshot) if isinstance(d, dict)
                        and d.get('target_department') == action.get('target_department')
                        and d.get('scope') == action.get('scope')
                        and d.get('sender_department') == goal['primary_owner']
                        and action.get('sender_department') in authorized_senders]
        preauthorized = [a for a in goal.get('continuation_actions', [])
                         if all(a.get(k)==action.get(k) for k in ('action_id','action_class','scope','target_department','payload'))]
        batch_authorized=(len(preauthorized)==1 and action.get('sender_department') in
                          authorized_senders)
        declared = len(declarations) == 1 or batch_authorized
        original_declarations = snapshot['goal_delivery'].get('collaboration_scopes', [])
        if len(declarations) == 1 and declarations[0] not in original_declarations:
            from professional_cms_execution import validate_message
            validate_message(root, snapshot, action)
        decisions = ([] if special else [row for row in w._result_handoff_rows(root, task_id)
                     if row.get("event") == "controller_decision" and row.get("record_id") == action.get("decision_record_id")])
        if not special and not declared and not parent_linked_initial and not responsibility_initial and (not assistant or len(decisions) != 1 or decisions[0].get("decision") not in {"rework", "continue", "accept"}
                or decisions[0].get("coordinator_role") != assistant
                or action.get("sender_department") != assistant
                or action.get("target_department") != decisions[0].get("next_owner")
                or action.get("target_department") not in goal["producer_departments"]
                or action.get("action_class") != "thread_message" or action.get("task_id") != task_id
                or action.get("scope") not in goal["authorized_scope"] or not action.get("action_id")):
            raise w.WorkflowError("actual assigned routine decision and original producer/scope required")
        if declared and (action.get('action_class') != 'thread_message' or action.get('task_id') != task_id
                         or not action.get('action_id') or snapshot.get('current_state') in w.TERMINAL_STATES
                         or w.file_digest(root, goal['authorization_pin']['path']) != goal['authorization_pin']):
            raise w.WorkflowError('active same goal original owner authorization required')
        if special and (action.get("action_id") != CONDO_FAQ_V7_POST_CANDIDATE_ACTION
                        or snapshot.get("current_state") in w.TERMINAL_STATES
                        or w.file_digest(root, goal["authorization_pin"]["path"]) != goal["authorization_pin"]):
            raise w.WorkflowError("post-candidate message cannot change original human authority")
        pin = action.get("payload")
        if (not isinstance(pin, dict) or w.file_digest(root, pin.get("path", "")) != pin
                or pin["sha256"] != action.get("payload_sha256")):
            raise w.WorkflowError("exact prepared approved message bytes required")
        binding = (_collaboration_binding(root, snapshot, action['target_department']) or {}
                   if declared and not batch_authorized else w.department_registry(root)[action["target_department"]].get("chat_binding", {}))
        mapping = {"target_thread_id": "thread_id" if declared and not batch_authorized else "task_id", "target_thread_title": "title", "target_cwd": "cwd",
                   "target_project_id": "project_id", "target_sidebar_section_id": "sidebar_section_id"}
        if declared and not batch_authorized:
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


def _completion_subject_proven(root, snapshot, requirement, accepted):
    """Accept only the trusted current receipt reader's fully bound subject."""
    identity = accepted.get("identity", {}) if isinstance(accepted, dict) else {}
    fingerprint = accepted.get("source_fingerprint") if isinstance(accepted, dict) else None
    fingerprint_valid = (isinstance(fingerprint, str) and w.SHA256_PATTERN.fullmatch(fingerprint)
                         or isinstance(fingerprint, dict) and w.file_digest(root, fingerprint.get("path", "")) == fingerprint)
    if (not isinstance(accepted, dict) or accepted.get("state") != "PROVEN"
            or identity.get("task_id") != snapshot["task_id"]
            or identity.get("sender_department") != requirement["subject"]["producer_department"]
            or not isinstance(identity.get("candidate_version"), str) or not identity["candidate_version"].strip()
            or not w.SHA256_PATTERN.fullmatch(str(identity.get("result_sha256", "")))
            or not fingerprint_valid or not accepted.get("source_turn_id")
            or not accepted.get("acceptance_receipt") or accepted.get("scope") != requirement["scope"]):
        return False
    evidence = accepted.get("evidence")
    return (isinstance(evidence, list) and bool(evidence)
            and all(isinstance(pin, dict) and w.file_digest(root, pin.get("path", "")) == pin for pin in evidence))


def tnew_internal_pilot_requirements(root, snapshot):
    """Select only the original source-adoption and read-only-pilot obligations."""
    task = "fc-20261011-goal-publication-notice-followthrough-repair-v1"
    scope = "project:flashcast:goal-publication-notice-followthrough-repair:v1"
    goal = validate_goal(root, snapshot.get("goal_delivery"), task_id=task)
    original = snapshot.get("goal_contract")
    prefix = "logs/handoffs/2026-10-11-goal-publication-notice-followthrough-repair-v1/HQ-prepared/"
    if (snapshot.get("task_id") != task or not isinstance(original, dict)
            or original.get("path") != prefix + "goal-input-PREPARED-v1.json"
            or original.get("sha256") != "c1ef5c9395c36b5838f945a9d57f579a2bea6654c09135b58188509a6ec8c194"
            or original.get("size") != 10977 or w.file_digest(root, original.get("path", "")) != original
            or goal.get("authorization_pin", {}).get("sha256") != "6492c4032ab17a65cab6dda864a159a0cb8957d842d70bb283acb1eb5ceb217f"
            or goal.get("authorization_pin", {}).get("path") != prefix + "human-authorization-native.json"
            or goal.get("authorization_pin", {}).get("size") != 1010
            or snapshot.get("goal_delivery", {}).get("authorization_pin") != goal.get("authorization_pin")
            or goal.get("primary_owner") != "system-development"
            or goal.get("producer_departments") != ["system-development"]
            or goal.get("responsible_assistant") != "operations-assistant-2"
            or goal.get("acceptance_capability") != "development"
            or goal.get("authorized_scope") != [scope] or goal.get("required_execution_actions")):
        raise w.WorkflowError("only the original authorized internal TNEW pilot parent is allowed")
    contract = _completion_contract(root, snapshot)
    requirements = contract.get("requirements", [])
    source = [row for row in requirements if row.get("requirement_id") == "original-criterion-11"
              and row.get("criterion_index") == 10 and row.get("requirement_type") == "source_adoption"
              and row.get("scope") == scope]
    pilot = [row for row in requirements if row.get("requirement_id") == "original-criterion-12"
             and row.get("criterion_index") == 11 and row.get("requirement_type") == "internal_pilot"
             and row.get("scope") == scope]
    if (contract.get("state") != "declared" or len(requirements) != 13
            or len(source) != 1 or len(pilot) != 1
            or any(row.get("subject", {}).get("producer_department") != "system-development" for row in source + pilot)):
        raise w.WorkflowError("unchanged original thirteen standards and exact proof11/pilot selectors required")
    return {"source_adoption": source[0], "internal_pilot": pilot[0],
            "business_goal_closed": False, "external_permission_issued": False}


def completion_obligations(root, snapshot, receipts=None, accepted=None):
    """Project frozen standards through actual readers; never write or grant authority."""
    snapshot = restore_goal(root, snapshot)
    task_id = snapshot["task_id"]
    from department_autonomy import autonomous_goal,completion as autonomous_completion
    if autonomous_goal(snapshot.get('goal_delivery')):return autonomous_completion(root,snapshot)
    from department_autonomy import migrated_local_completion,professional_local_completion_view
    if migrated_local_completion(root,snapshot):return professional_local_completion_view(root,snapshot)
    from direct_system_repair import completion_view
    direct = completion_view(root, snapshot)
    if direct is not None:
        return direct
    if receipts is None:
        receipts, invalid = w._validate_receipt_chain(root, task_id)
        if invalid:
            raise w.WorkflowError("completion requires the intact actual receipt chain")
    if w.validate_workflow_events(root, task_id):
        raise w.WorkflowError("completion requires the intact actual workflow event chain")
    contract = _completion_contract(root, snapshot)
    output = {"contract_state": contract["state"], "state": contract["state"],
              "completion_kind": contract["completion_kind"], "contract_pin": contract.get("contract_pin"),
              "supplement_prepared": contract.get("supplement_prepared", False),
              "requirements": [], "missing": [], "blockers": [], "closed_scope_only": False,
              "business_goal_closed": False}
    if contract["state"] != "declared":
        legacy = getattr(w, "goal_legacy_scope_completion", None)
        proof = legacy(root, snapshot, receipts) if legacy and snapshot.get("current_state") == "closed" else {}
        if proof.get("state") == "PROVEN":
            output.update(contract_state="legacy_exact_scope", state="legacy_exact_scope", closed_scope_only=True,
                          legacy_scope_proof=proof)
        else:
            output["missing"].append("needs_completion_declaration")
        return output
    output["missing"].extend(completion_dependencies(root, snapshot))
    subject_reader = getattr(w, "goal_completion_subject", None)
    subjects = {}
    for requirement in contract["requirements"]:
        item = {"requirement_id": requirement["requirement_id"], "criterion_index": requirement["criterion_index"],
                "scope": requirement["scope"], "requirement_type": requirement["requirement_type"],
                "next_owner": requirement["subject"]["producer_department"], "state": "MISSING", "evidence": []}
        selector = (requirement["subject"]["producer_department"], requirement["scope"])
        if selector not in subjects:
            subjects[selector] = (subject_reader(root, snapshot, receipts, {**requirement["subject"], "scope": requirement["scope"]})
                                  if subject_reader else {"state": "BLOCKED", "reason": "actual_completion_subject_reader_unavailable"})
        current = subjects[selector]
        if not _completion_subject_proven(root, snapshot, requirement, current):
            item.update(state=current.get("state") if current.get("state") in {"MISSING", "BLOCKED"} else "BLOCKED",
                        reason=current.get("reason", "latest_exact_independent_acceptance_missing"))
        else:
            kind = requirement["requirement_type"]
            if kind == "accepted_delivery":
                proof = current
            elif kind == "execution_postcheck":
                reader = getattr(w, "goal_execution_completion", None)
                action = {key: requirement[key] for key in ("action_id", "action_class", "scope", "department")}
                proof = (reader(root, snapshot, receipts, action, accepted=current) if reader else
                         {"state": "BLOCKED", "reason": "actual_execution_completion_reader_unavailable"})
            else:
                reader = getattr(w, "goal_typed_completion_proof", None)
                proof = (reader(root, snapshot, receipts, requirement, current) if reader else
                         {"state": "BLOCKED", "reason": "actual_typed_completion_reader_unavailable"})
            if not isinstance(proof, dict) or proof.get("state") not in {"PROVEN", "MISSING", "BLOCKED"}:
                raise w.WorkflowError("trusted typed completion reader must return a precise proof state")
            if proof.get("state") == "PROVEN" and (proof.get("identity") != current["identity"]
                    or proof.get("source_fingerprint") != current["source_fingerprint"]
                    or proof.get("source_turn_id") != current["source_turn_id"]
                    or proof.get("scope") != requirement["scope"] or not proof.get("evidence")):
                raise w.WorkflowError("typed completion proof must retain the exact accepted source identity")
            item.update(state=proof["state"], reason=proof.get("reason"), evidence=proof.get("evidence", []),
                        wait_dependency=proof.get("wait_dependency"),
                        identity=current["identity"], source_fingerprint=current["source_fingerprint"],
                        source_turn_id=current["source_turn_id"])
        output["requirements"].append(item)
        if item["state"] != "PROVEN":
            output["blockers" if item["state"] == "BLOCKED" else "missing"].append(
                "completion_requirement:" + item["requirement_id"] + ":" + str(item.get("reason") or item["state"]))
    output["business_goal_closed"] = not output["missing"] and not output["blockers"]
    return output


def remaining_followthrough(root, snapshot, receipts=None, now=None, *, completion=None):
    """Closing one accepted scope leaves all other declared obligations visible."""
    proof = completion_obligations(root, snapshot, receipts) if completion is None else completion
    goal = snapshot["goal_delivery"]; task_id = snapshot["task_id"]
    rows = []
    if proof["state"] == "needs_completion_declaration":
        rows.append({"task_id": task_id, "requirement_id": "completion_declaration", "status": "needs_completion_declaration",
                     "next_owner": goal["responsible_assistant"], "next_action": "冻结原标准的准确机械映射，不改写原目标或扩大许可",
                     "unblock_condition": "原完成标准全部精确映射并首次提交 pinned 完成声明", "next_check_at": None,
                     "declaration_state": "prepared_not_committed" if proof.get('supplement_prepared') else "waiting_declaration_input",
                     "actionable": proof.get('supplement_prepared', False), "business_goal_closed": False})
    for item in proof["requirements"]:
        if item["state"] == "PROVEN":
            continue
        wait = item.get("wait_dependency")
        revisit = w._parse_observed_at(wait.get("next_check_at")) if isinstance(wait, dict) else None
        moment = now or dt.datetime.now(dt.timezone.utc)
        if isinstance(wait, dict) and (wait.get("requirement_id") != item["requirement_id"]
                or wait.get("scope") != item["scope"] or not all(wait.get(key) for key in
                    ("owner", "next_action", "unblock_condition", "record_id")) or revisit is None):
            raise w.WorkflowError("exact committed requirement dependency owner/condition/revisit required")
        deferred = bool(revisit is not None and revisit > moment)
        rows.append({**item, "task_id": task_id, "status": "named_completion_dependency_wait" if deferred else "completion_followthrough_required",
                     "next_action": wait['next_action'] if isinstance(wait, dict) else "落实原范围的 " + item["requirement_type"] + " 准确实际证明",
                     "unblock_condition": wait['unblock_condition'] if isinstance(wait, dict) else "本准确当前版本、来源指纹、原 turn 的真实执行/采用/试点/通知证明",
                     "next_check_at": wait.get("next_check_at") if isinstance(wait, dict) else None,
                     "next_owner": wait["owner"] if isinstance(wait, dict) else item['next_owner'],
                     "actionable": not deferred and snapshot.get("current_state") in {"qa_passed", "closed", "qa_blocked"},
                     "business_goal_closed": False})
    for reason in proof["missing"] + proof["blockers"]:
        if reason.startswith("completion_requirement:") or reason == "needs_completion_declaration":
            continue
        rows.append({"task_id": task_id, "requirement_id": reason, "status": "completion_dependency_required",
                     "next_owner": goal["responsible_assistant"], "next_action": "沿原目标补齐 " + reason,
                     "unblock_condition": reason, "next_check_at": None, "actionable": True,
                     "business_goal_closed": False})
    return rows


def completion_proof_selector(requirement):
    """Resolve an omitted typed-effect reference without rewriting its contract."""
    kind, rid = requirement.get('requirement_type'), requirement.get('requirement_id')
    committed = {'mode': 'committed_completion_evidence', 'requirement_id': rid}
    if 'proof_ref' in requirement:
        selector = requirement['proof_ref']
        if not isinstance(selector, dict):
            raise w.WorkflowError('typed proof selector object required')
        if selector == {'mode': 'committed_completion_evidence'}:
            if (not isinstance(kind, str)
                    or kind not in COMPLETION_TYPES - {'accepted_delivery', 'execution_postcheck'}
                    or not isinstance(rid, str) or not rid.strip()):
                raise w.WorkflowError('one original typed completion requirement required')
            return committed
        if selector.get('mode') == 'committed_completion_evidence' and selector != committed:
            raise w.WorkflowError('committed completion selector must retain its original requirement')
        return selector
    if (kind in COMPLETION_TYPES - {'accepted_delivery', 'execution_postcheck'}
            and isinstance(rid, str) and rid.strip()):
        return committed
    return None


def record_completion_evidence(root, task_id, input_path, role, requirement_id):
    """Append a verified new actual proof; the frozen standard remains unchanged."""
    from department_autonomy import (autonomous_goal,record_completion,migrated_local_completion,
                                     record_professional_local_completion)
    current = restore_goal(root, w.read_json(w.snapshot_path(root,task_id)))
    if autonomous_goal(current.get('goal_delivery')):
        return record_completion(root,task_id,input_path,role,requirement_id)
    if migrated_local_completion(root,current):
        return record_professional_local_completion(root,task_id,input_path,role,requirement_id)
    task_id = w.validate_task_id(task_id)
    pin = w.file_digest(root, input_path)
    with w.workflow_lock(root):
        snapshot = restore_goal(root, w.read_json(w.snapshot_path(root, task_id)))
        goal = snapshot.get("goal_delivery", {})
        if (not enabled(root, snapshot) or role != goal.get("responsible_assistant")
                or role in goal.get("producer_departments", [])
                or w.department_registry(root).get(role, {}).get("coordination_authority", {}).get("routine_decisions") is not True):
            raise w.WorkflowError("original independent responsible assistant must record actual completion evidence")
        receipts, invalid = w._validate_receipt_chain(root, task_id)
        if invalid or w.validate_workflow_events(root, task_id):
            raise w.WorkflowError("intact original chains required for completion evidence")
        contract = _completion_contract(root, snapshot)
        matches = [row for row in contract['requirements'] if row['requirement_id'] == requirement_id]
        if contract['state'] != 'declared' or len(matches) != 1:
            raise w.WorkflowError("one original frozen completion requirement required")
        requirement = matches[0]
        if (completion_proof_selector(requirement) != {'mode': 'committed_completion_evidence', 'requirement_id': requirement_id}
                or requirement['requirement_type'] in {'accepted_delivery', 'execution_postcheck'}):
            raise w.WorkflowError("original typed committed-evidence selector required; no replacement of frozen proof refs")
        subject_reader, proof_reader = (getattr(w, name, None) for name in
                                       ('goal_completion_subject', 'goal_typed_completion_proof'))
        if subject_reader is None or proof_reader is None:
            raise w.WorkflowError("actual subject and typed completion readers required")
        accepted = subject_reader(root, snapshot, receipts, {**requirement['subject'], 'scope': requirement['scope']})
        if not _completion_subject_proven(root, snapshot, requirement, accepted):
            raise w.WorkflowError("latest exact independent accepted source required before recording completion evidence")
        proof = proof_reader(root, snapshot, receipts, requirement, accepted, proof_pin=pin)
        if (not isinstance(proof, dict) or proof.get('state') != 'PROVEN'
                or any(proof.get(key) != accepted.get(key) for key in
                       ('identity', 'source_fingerprint', 'source_turn_id', 'scope'))
                or not proof.get('evidence')
                or not all(w.file_digest(root, item.get('path', '')) == item for item in proof['evidence'])):
            raise w.WorkflowError("actual typed completion proof must match the current accepted source")
        evidence = {'requirement_id': requirement_id, 'proof_pin': pin}
        prior = [row.get('details', {}).get('completion_evidence') for row in
                 w.read_jsonl(Path(root) / w.WORKFLOW_EVENTS) if row.get('task_id') == task_id
                 and row.get('details', {}).get('completion_evidence', {}).get('requirement_id') == requirement_id]
        if evidence in prior:
            return {'result': 'duplicate_ignored', 'completion_evidence': evidence, 'contract_rewritten': False}
        w.append_workflow_event(root, task_id, snapshot['current_state'],
                                {'completion_evidence': evidence, 'completion_evidence_recorder': role,
                                 'original_authorization_pin': goal['authorization_pin']})
    return {'result': 'recorded', 'completion_evidence': evidence, 'contract_rewritten': False,
            'external_permission_issued': False, 'business_goal_closed': False}


def deduplicate_records(rows, *, delivery=False):
    """Count business/result identities, never the number of control journal rows."""
    result, seen = [], set()
    for row in rows:
        identity = row.get("delivery_identity", row.get("identity", row)) if delivery else row
        if delivery and isinstance(identity, dict) and all(identity.get(key) for key in
                ("task_id", "sender_department", "candidate_version", "result_sha256", "target_department", "target_thread_id", "purpose")):
            key = tuple(identity[name] for name in ("task_id", "sender_department", "candidate_version", "result_sha256",
                                                   "target_department", "target_thread_id", "purpose"))
        elif all(row.get(key) for key in ("task_id", "sender_department", "candidate_version", "result_sha256")):
            key = tuple(row[name] for name in ("task_id", "sender_department", "candidate_version", "result_sha256"))
        elif row.get("task_id") and (row.get("requirement_id") or row.get("action_id")):
            key = (row["task_id"], row.get("requirement_id"), row.get("action_id"), row.get("scope"), row.get("target_department"))
        else:
            key = w.sha256_value(row)
        if key not in seen:
            seen.add(key); result.append(row)
    return result


def _task_block(task_id, role, reason):
    return {"task_id": task_id, "owner": role, "next_owner": role, "state": "blocked_evidence_invalid",
            "block_reason": str(reason), "next_action": "恢复本 task 的准确原来源和完整守卫，其他合法任务继续",
            "unblock_condition": "本 task 来源指纹、事件链和原身份准确回读通过", "next_check_at": "next_existing_legal_opportunity",
            "actionable": False, "business_goal_closed": False}


def record_collaboration(root, task_id, input_path):
    """An audit of actual native transport; no fake registered department ACK."""
    pin = w.file_digest(root, input_path)
    record = w.read_json(w.safe_path(root, input_path))
    with w.workflow_lock(root):
        snapshot = restore_goal(root, w.read_json(w.snapshot_path(root, task_id)))
        if not enabled(root, snapshot) or record.get("task_id") != task_id:
            raise w.WorkflowError("exact parent complete goal required")
        goal = snapshot["goal_delivery"]
        if record.get('source_kind') == 'official_native_queue':
            from goal_source_recovery import record_collaboration_queue
            return record_collaboration_queue(root, snapshot, record, pin)
        if record.get('source_kind')=='historical_native_collaboration':
            from goal_source_recovery import collaboration_source
            collaboration_source(root,record)
            prior=goal.get('collaboration_records',[])
            declaration={'scope':record['scope'],'sender_department':goal['primary_owner'],
                         'target_department':record['sender_department']}
            declared=declaration in goal.get('collaboration_scopes',[])
            if pin in prior and declared:return {'result':'duplicate_ignored','parent_closed':False}
            existing=[w.read_json(w.safe_path(root,p['path'])) for p in prior]
            if pin not in prior and any(x.get('action_id')==record.get('action_id') for x in existing):
                raise w.WorkflowError('historical collaboration recovery cannot replace a previous source')
            snapshot['goal_delivery']={**goal,'collaboration_records':prior if pin in prior else prior+[pin],
                'collaboration_scopes':goal.get('collaboration_scopes',[]) if declared else
                                      goal.get('collaboration_scopes',[])+[declaration]}
            w.append_workflow_event(root,task_id,snapshot['current_state'],
                {'goal_delivery':snapshot['goal_delivery'],'collaboration_receipt':pin,
                 'historical_source_recovered':True,'prior_policy_fabricated':False})
            w.atomic_write_json(w.snapshot_path(root,task_id),snapshot)
            return {'result':'recorded','parent_closed':False,'new_permissions':0}
        action = [x for x in goal.get("approved_actions", []) if x.get("action_id") == record.get("action_id")]
        if len(action) != 1 or record.get("scope") != action[0].get("scope"):
            raise w.WorkflowError("one frozen approved parent collaboration action required")
        _readonly_coordination_action(root, snapshot, action[0], "read")
        binding = _collaboration_binding(root, snapshot, action[0].get("target_department")) or {}
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
    goal = validate_goal(root, w.read_json(w.safe_path(root, input_path)), task_id=task_id)
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
        original = json.loads(w.validation_bytes(w.safe_path(root, pin["path"])), object_pairs_hook=unique_fields)
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
            if record.get('source_kind') == 'official_native_queue':
                from goal_source_recovery import collaboration_queue_source
                current = collaboration_queue_source(root, snapshot, record)
                state = states.get(record['action_id'])
                rank = {'queue_accepted':0, 'message_received':1, 'result_received':2}
                if ((not state and current['status'] != 'queue_accepted') or
                        (state and (state.get('queue_identity') != current['queue_identity'] or
                                    rank.get(current['status'], -1) != rank.get(state.get('status'), -2) + 1))):
                    raise CollaborationProofError('queue_order_or_identity_invalid', 'one original queue -> actual receipt -> final result sequence required')
                current.update(collaboration=pin, result_receipt=pin)
                states[record['action_id']] = current
                continue
            if record.get('source_kind')=='historical_native_collaboration':
                from goal_source_recovery import collaboration_source
                recovered=collaboration_source(root,record)
                recovered.update(collaboration=pin,result_receipt=pin)
                states[record['action_id']]=recovered
                continue
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
                if (snapshot.get('task_id') == 'fc-20261017-original204-two-renderer-development-handoff-v1'
                        and action['action_id'] == 'A1-original204-G01-G03-local-renderer-development-20261017-v1'):
                    from goal_source_recovery import validate as validate_lf_source
                    reconciliations=[e.get('details',{}).get('approved_dispatch_lf_reconciliation')
                        for e in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS)
                        if e.get('task_id')==snapshot['task_id'] and
                        e.get('details',{}).get('approved_dispatch_lf_reconciliation')]
                    if len(reconciliations)!=1:
                        raise CollaborationProofError('approved_dispatch_lf_reconciliation_missing',
                            'one real original LF source reconciliation required')
                    source_pin=reconciliations[0]
                    if w.file_digest(root,source_pin.get('path',''))!=source_pin:
                        raise CollaborationProofError('approved_dispatch_lf_reconciliation_changed',
                            'frozen original LF reconciliation changed')
                    source=w.read_json(w.safe_path(root,source_pin['path']))
                    validate_lf_source(root,source)
                    if source.get('original_collaboration_record')!=pin:
                        raise CollaborationProofError('approved_dispatch_lf_record_mismatch',
                            'reconciliation must bind this original sent record')
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
                "responsible_assistant": goal.get("responsible_assistant"), "proof_state": "NOT_PROVEN",
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
        if received and decision and decision.get("decision") == "close_scope":
            from collaboration_scope_close import readback_collaboration_scope_close
            readback_collaboration_scope_close(root, decision, rows)
            continue
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


def _original_markdown_candidate_version(root, snapshot, state, returned, result_path):
    """Read the two original developer returns without minting a new identity.

    This is deliberately limited to the frozen 316/About collaboration tasks.
    A Markdown SHA is only useful when the original receipt and completed final
    independently identify the same local candidate.
    """
    exact_tasks = {
        "fc-20261016-industry-product-316-development-handoff-v1": "本地候选",
        "fc-20261016-industry-about-development-handoff-v1": "本地候选提交",
    }
    task_id = snapshot["task_id"]
    label = exact_tasks.get(task_id)
    if label is None or result_path.suffix.lower() != ".md":
        return None
    receipt_pin = state["result_receipt"]
    final_pin = state["visible_reply"]
    native_pin = state["native_result"]
    if (w.file_digest(root, receipt_pin["path"]) != receipt_pin
            or w.file_digest(root, final_pin["path"]) != final_pin
            or w.file_digest(root, native_pin["path"]) != native_pin
            or returned.get("task_id") != task_id
            or returned.get("action_id") != state["action_id"]
            or returned.get("scope") != state["approved_action"]["scope"]
            or returned.get("status") != "result_received"
            or returned.get("target_thread_id") != state["threadId"]
            or returned.get("policy_decision_id") != state["policy_decision_id"]
            or returned.get("result") != state["result"]
            or returned.get("visible_reply") != final_pin
            or returned.get("actual_native_result") != native_pin
            or returned.get("result_origin_sha256") != state["result"]["sha256"]
            or returned.get("independent_acceptance_completed") is not False
            or returned.get("production_deployed") is not False
            or returned.get("parent_goal_closed") is not False):
        raise w.WorkflowError("original Markdown collaboration receipt and frozen native source required")
    version = returned.get("local_candidate_sha")
    if not isinstance(version, str) or not re.fullmatch(r"[0-9a-f]{40}", version):
        raise w.WorkflowError("one exact original local candidate SHA required")
    try:
        markdown = result_path.read_text(encoding="utf-8")
        final = w.safe_path(root, final_pin["path"]).read_text(encoding="utf-8")
        native = w.read_json(w.safe_path(root, native_pin["path"]))
    except (UnicodeError, OSError, ValueError) as exc:
        raise w.WorkflowError("complete original Markdown and native final required") from exc
    matches = re.findall(r"(?m)^\s*-\s*" + re.escape(label) + r"：`([0-9a-f]{40})`", markdown)
    message = native.get("message", {})
    selection = native.get("source_selection", {})
    raw_pin = returned.get("raw_source")
    if (not isinstance(raw_pin, dict) or native.get("raw_source") != raw_pin
            or w.file_digest(root, raw_pin.get("path", "")) != raw_pin):
        raise w.WorkflowError("original complete native collaboration page pin required")
    raw = _collaboration_native(root, raw_pin)
    selected_turns = [turn for turn in raw.get("turns", [])
                      if turn.get("id") == returned.get("source_turn_id")]
    selected_messages = [item for turn in selected_turns for item in turn.get("items", [])
                         if item.get("id") == returned.get("source_message_id")]
    if (matches != [version] or final.count(version[:8]) != 1
            or any(document.get("isError") is not False for document in (native, raw) if "isError" in document)
            or any(document.get(flag) is True for document in (native, raw, message, selection)
                   for flag in ("failed", "superseded", "truncated"))
            or any(document.get(flag) is True for document in (*selected_turns, *selected_messages)
                   for flag in ("failed", "superseded", "truncated"))
            or native.get("status") != "completed" or native.get("error") is not None
            or message.get("phase") != "final_answer" or message.get("text") != final
            or message.get("id") != returned.get("source_message_id")
            or native.get("turn_id") != returned.get("source_turn_id")
            or selection.get("selected_source_turn_id") != returned.get("source_turn_id")
            or selection.get("selected_source_message_id") != returned.get("source_message_id")
            or selection.get("source_thread_id") != state["threadId"]
            or raw.get("thread", {}).get("id") != state["threadId"]
            or len(selected_turns) != 1 or selected_turns[0].get("status") != "completed"
            or selected_turns[0].get("error") is not None
            or len(selected_messages) != 1 or selected_messages[0].get("phase") != "final_answer"
            or selected_messages[0].get("text") != final):
        raise w.WorkflowError("Markdown candidate SHA must agree with original completed final")
    return version


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
    markdown_version = _original_markdown_candidate_version(root, snapshot, state, returned, result_path)
    version = returned.get("candidate_version") or result.get("candidate_version") or markdown_version
    if (not isinstance(version, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9+._-]{0,199}", version)
            or version != identity.get("candidate_version")
            or (returned.get("candidate_version") and result.get("candidate_version")
                and returned["candidate_version"] != result["candidate_version"])
            or (markdown_version is not None and version != markdown_version)):
        raise w.WorkflowError("candidate version must come from the original frozen collaboration result")
    allowed_task=(returned.get('original_task_id') if state.get('source_recovered') else snapshot['task_id'])
    if result.get("task_id", allowed_task) != allowed_task or result.get("department", sender) != sender:
        raise w.WorkflowError("original collaboration result task and sender required")
    action = state["approved_action"]
    policies = [row for row in w.read_jsonl(Path(root) / w.POLICY_DECISIONS)
                if row.get("decision_id") == state["policy_decision_id"]]
    if not state.get('source_recovered') and (len(policies) != 1 or policies[0].get("status") != "allow"
            or any(policies[0].get(k) != action.get(k) for k in
                   ("task_id", "action_id", "scope", "payload_sha256", "target_thread_id"))):
        raise w.WorkflowError("original exact collaboration policy receipt required")
    return {"task_id": snapshot["task_id"], "department": sender, "candidate_version": version,
            "scope": action["scope"], "status": "completed", "source_mode": "collaboration",
            "fixed_chat_task_id": binding["thread_id"], "result": state["result"], "state": state,
            "responsible_assistant": snapshot["goal_delivery"]["responsible_assistant"],
            "batch_has_outcome":True,"business_goal_closed":False,"independent_acceptance":False}


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


def wait_plan(root, role, cursors=None, *, queue=None):
    registry = w.department_registry(root)
    if role != "operations" and registry.get(role, {}).get("coordination_authority", {}).get("routine_decisions") is not True:
        raise w.WorkflowError("registered coordinator required")
    enabled(root)
    if cursors is None:
        cursors = w.read_json(Path(root) / "logs/goal-delivery-waits" / f"{role}.json").get("cursors", {})
    if not isinstance(cursors, dict) or any(not isinstance(value, str) or not value.strip() for value in cursors.values()):
        raise w.WorkflowError("exact recorded native cursor values required")
    queue = pending(root, role) if queue is None and role != 'operations' else (queue or {})
    ready = deduplicate_records(queue.get('pending', []) + queue.get('followthrough_pending', [])
                    + queue.get('collaboration_pending', []) + queue.get('collaboration_not_proven', [])
                    + [row for row in queue.get('completion_followthrough', []) if row.get('actionable')])
    ready.extend(row for row in queue.get('notification_delivery_pending', []) if row.get('actionable'))
    ready.extend(queue.get('shared_pool_pending', []))
    targets, tasks, collaboration_states, errors = {}, [], [], []
    current_owners = _current_goal_owners(root)
    for notice in queue.get('notification_delivery_pending', []):
        if notice.get('waiting_for_native_completion'):
            tid = notice.get('delivery_identity', {}).get('target_thread_id', notice.get('target_thread_id'))
            if tid:
                targets[tid] = {'threadId': tid, **({'afterCursor': cursors[tid]} if cursors.get(tid) else {})}
                tasks.append({'task_id': notice.get('identity', {}).get('task_id'),
                              'threadId': tid, 'wait_source': 'busy_result_recipient'})
    for path in sorted((Path(root) / w.WORKFLOW_DIR).glob("*.json")):
        exact_owner = 'ownership_unresolved'
        try:
            raw = w.read_json(path)
            if raw.get('task_id') != path.stem:
                raise w.WorkflowError("current task snapshot identity differs from its exact path")
            if current_owners.get(path.stem, raw.get("goal_delivery", {}).get("responsible_assistant")) != role:
                continue
            exact_owner = role
            snapshot = restore_goal(root, raw)
            if not enabled(root, snapshot) or snapshot.get("current_state") in w.TERMINAL_STATES:
                continue
            goal = snapshot["goal_delivery"]
            if goal["responsible_assistant"] != role:
                continue
            rows, invalid = w._validate_receipt_chain(root, snapshot["task_id"])
            if invalid or w.validate_workflow_events(root, snapshot['task_id']):
                raise w.WorkflowError("wait requires intact actual receipt/event chains")
            results = w._result_handoff_rows(root, snapshot["task_id"])
            local_targets, local_tasks = {}, []
            for dep in goal["producer_departments"]:
                sent = next((r for r in reversed(rows) if r.get("department") == dep and r.get("receipt_type") == "dispatch_sent"), None)
                if not sent or any(r.get("sender_department") == dep and r.get("event") == "notification_queued"
                                   and r.get("created_at", "") >= sent["created_at"] for r in results):
                    continue
                tid = sent.get("chat_task_id")
                if tid:
                    local_targets[tid] = {"threadId": tid, **({"afterCursor": cursors[tid]} if cursors.get(tid) else {})}
                    local_tasks.append({"task_id": snapshot["task_id"], "department": dep, "threadId": tid,
                                        "dispatch": {k: sent[k] for k in ("receipt_id", "receipt_hash")}})
            states = _collaboration_wait_states(root, snapshot)
            for state in states:
                if state.get("proof_state") != "PROVEN" or state["status"] != "sent":
                    continue
                tid = state["threadId"]
                local_targets[tid] = {"threadId": tid, **({"afterCursor": cursors[tid]} if cursors.get(tid) else {})}
                local_tasks.append({**state, "wait_source": "collaboration"})
            sent_actions = {row.get('action_id') for row in rows if row.get('receipt_type') == 'dispatch_sent'}
            for action in goal.get('approved_actions', []):
                if (action.get('required_for_completion', True) and action.get('action_class') == 'thread_message'
                        and action.get('action_id') not in sent_actions
                        and not any(state.get('action_id') == action.get('action_id') for state in states)):
                    ready.append({'task_id': snapshot['task_id'], 'action_id': action['action_id'],
                                  'next_owner': role, 'status': 'prepared_not_sent', 'actionable': True})
            targets.update(local_targets); tasks.extend(local_tasks); collaboration_states.extend(states)
        except (w.WorkflowError, ValueError, OSError, KeyError, TypeError, AttributeError) as exc:
            errors.append(_task_block(path.stem, exact_owner, exc))
    ordered = sorted(targets.values(), key=lambda x: x["threadId"])
    return {"coordinator_role": role, "tool": "mcp__codex_app__wait_threads", "timeoutMs": 60000,
            "batches": [] if ready else [ordered[i:i+8] for i in range(0, len(ordered), 8)],
            "inflight_targets": ordered, "tasks": deduplicate_records(tasks),
            "collaboration_state": deduplicate_records(collaboration_states), "task_errors": deduplicate_records(errors),
            "ready_before_wait": deduplicate_records(ready), "wait_deferred_for_ready_work": bool(ready),
            "cursor_record_required": True, "HQ_may_end_coordination": role == 'operations',
            "native_wakeup_guaranteed": False, "creates_automation": False,
            "state": "ready_work_before_wait" if ready else "inflight_event_wait" if ordered else "temporarily_no_executable_work"}


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
    for name in ("preflight-record", "collaboration-record", "dependency-record", "approved-action-record", "coordination-decision-register"):
        command = sub.add_parser(name); command.add_argument("--task-id", required=True); command.add_argument("--input", required=True)
    bind = sub.add_parser("bind"); bind.add_argument("--task-id", required=True); bind.add_argument("--input", required=True)
    auth = sub.add_parser("authorization-precheck")
    auth.add_argument("--task-id", required=True); auth.add_argument("--input", required=True)
    show = sub.add_parser("status"); show.add_argument("--task-id", required=True)
    wait = sub.add_parser("wait-plan"); wait.add_argument("--role", required=True)
    begin = sub.add_parser("wait-begin"); begin.add_argument("--role", required=True); begin.add_argument("--input", required=True)
    inherit = sub.add_parser("delegation-bind"); inherit.add_argument("--task-id", required=True); inherit.add_argument("--role", required=True); inherit.add_argument("--input", required=True)
    save = sub.add_parser("wait-record"); save.add_argument("--role", required=True); save.add_argument("--input", required=True)
    for name in ('wait-call-start', 'wait-recover'):
        command = sub.add_parser(name); command.add_argument('--role', required=True); command.add_argument('--input', required=True)
    initial = sub.add_parser("parent-initial-dispatch-begin"); initial.add_argument("--input", required=True)
    initial_goal = sub.add_parser("goal-initial-dispatch-begin"); initial_goal.add_argument("--input", required=True)
    completion = sub.add_parser("completion-contract-record")
    completion.add_argument("--task-id", required=True); completion.add_argument("--input", required=True); completion.add_argument("--role", required=True)
    evidence = sub.add_parser("completion-evidence-record")
    evidence.add_argument("--task-id", required=True); evidence.add_argument("--input", required=True)
    evidence.add_argument("--role", required=True); evidence.add_argument("--requirement-id", required=True)
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
        elif args.command == "coordination-decision-register":
            from owner_nonpayment_coordination import register
            result = register(root, args.task_id, args.input)
        elif args.command == "bind": result = bind_goal(root, args.task_id, w.read_json(w.safe_path(root, args.input)))
        elif args.command == "authorization-precheck":
            result = authorization_precheck(root, args.task_id, w.read_json(w.safe_path(root, args.input)))
        elif args.command == "status": result = status(root, args.task_id)
        elif args.command == "delegation-bind": result = bind_review_delegation(root, args.task_id, args.input, args.role)
        elif args.command == "wait-begin": result = begin_wait(root, args.role, args.input)
        elif args.command == "wait-record": result = record_wait(root, args.role, args.input)
        elif args.command == 'wait-call-start': result = wait_call_started(root, args.role, args.input)
        elif args.command == 'wait-recover': result = recover_wait(root, args.role, args.input)
        elif args.command == 'completion-contract-record':
            result = record_completion_contract(root, args.task_id, args.input, args.role)
        elif args.command == 'completion-evidence-record':
            result = record_completion_evidence(root, args.task_id, args.input, args.role, args.requirement_id)
        elif args.command in {'parent-initial-dispatch-begin', 'goal-initial-dispatch-begin'}:
            from parent_initial_dispatch import begin
            result = begin(root, args.input)
        else:
            cursor_file = root / "logs/goal-delivery-waits" / f"{args.role}.json"
            result = wait_plan(root, args.role, w.read_json(cursor_file).get("cursors", {}))
        print(json.dumps(result, ensure_ascii=False, indent=2)); return 0
    except (w.WorkflowError, ValueError, KeyError, OSError) as error:
        print(json.dumps({"status": "blocked", "reason": str(error), "external_permission_issued": False})); return 1


if __name__ == "__main__":
    raise SystemExit(main())
