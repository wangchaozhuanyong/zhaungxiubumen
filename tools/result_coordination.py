"""Exact-result coordination for the real native result-handoff entry.

Actor/owner strings are audit metadata, not authentication. This module grants
no external permission and never executes a message, decision, or publication.
Lock order is coordination flock -> SQLite transaction -> native workflow lock;
transfers hold workflow lock before the SQL transaction through assignment apply.
SQLite transactions finish before invoking the native handoff append.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager, nullcontext
import datetime as dt
import fcntl
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from typing import Any, TypedDict
import uuid

COORDINATION_LOCK = Path("logs/.result-coordination.lock")
DATABASE = Path("logs/result-coordination.sqlite3")
ROLES = {"operations", "operations-assistant"}
FINAL_EVENTS = {"controller_received", "controller_decision", "controller_followthrough", "assistant_conclusion"}
REPORT_STATES = {"completed", "partial", "qa_rework", "external_blocked", "queue_failed", "failed"}
IDENTITY_FIELDS = ("task_id", "sender_department", "candidate_version", "result_sha256")
COORDINATOR_FIELDS = {"coordinator_role", "coordinator_owner", "coordination_claim"}
DELIVERY_PURPOSES = {"professional_acceptance", "HQ_knowledge"}
KNOWLEDGE_CONSUMER_VERSION = "committed-assistant-knowledge/v1"
ORIGINAL_PAID16_TASK = 'fc-20260920-google-ads-rm100-budget-plan'
ORIGINAL_PAID16_COORDINATION_TASK = 'fc-20261010-assistant3-remaining-business-continuation-v2'
ORIGINAL_PAID16_SCOPE = 'project:flashcast:assistant3:remaining-original-goals:v2'
ORIGINAL_PAID16_INDEX = ('logs/handoffs/2026-10-10-goal-delivery-assistant-runtime-v1/'
    'operations-assistant3-business-next-v2/assistant3-continuation/event-followthrough/'
    'oct12-existing-results-intake-205014/control-admission-notice-residual-225247/'
    'current-two-control-rejections-and-reuse-frozen.json')
ORIGINAL_PAID16_INDEX_SHA256 = '6072eccf65677f34e9b1b0e3436ad9d6bec90c0caacdd4a945e02efc0e9d47e0'
ORIGINAL_A3_CONCLUSION = {
    'task_id': 'fc-20261010-assistant3-remaining-business-continuation-v2',
    'sender_department': 'operations-assistant-3',
    'candidate_version': 'A3-existing-paid16-sales-v3-intake-20261012-v1',
    'result_sha256': 'a598046a728a0d81703fb0e3a2814fc581b06d7b13d1b09c96756a037920a628',
}
ORIGINAL_A3_OUTBOX = ('logs/handoffs/2026-10-10-goal-delivery-assistant-runtime-v1/'
    'operations-assistant3-business-next-v2/assistant3-continuation/event-followthrough/'
    'oct12-existing-results-intake-205014/A3-final-existing-results-partial-intake-outbox-v1.json')
ORIGINAL_A3_AUTHORITY = ('logs/handoffs/2026-10-10-goal-delivery-assistant-runtime-v1/'
    'developer/human-authority.json')
ORIGINAL_A3_AUTHORITY_SHA256 = 'aeff0f96bc6ce116b92eb7f0fd1bb8b9258e31b85cf0c97eb8d0bd5537487e31'


def is_original_a3_conclusion_identity(identity):
    """Only the already produced A3 partial result gets a producer conclusion."""
    return exact_identity(identity) == ORIGINAL_A3_CONCLUSION


def _original_a3_live_goal(root, identity):
    """Bound the one A3 partial producer result without creating a new QA owner."""
    if not is_original_a3_conclusion_identity(identity):
        return None
    w = _w(); root = Path(root).resolve()
    snapshot = w.read_json(w.snapshot_path(root, identity['task_id']))
    goal = goal_delivery(root, snapshot=snapshot)
    registry = w.department_registry(root)
    role = identity['sender_department']
    authority = registry.get(role, {}).get('coordination_authority', {})
    binding = registry.get(role, {}).get('chat_binding', {})
    auth_pin = w.file_digest(root, ORIGINAL_A3_AUTHORITY)
    outbox_pin = w.file_digest(root, ORIGINAL_A3_OUTBOX)
    box = w.read_json(w.safe_path(root, ORIGINAL_A3_OUTBOX))
    if (snapshot.get('task_id') != identity['task_id']
            or snapshot.get('current_state') in w.TERMINAL_STATES
            or not isinstance(goal, dict)
            or goal.get('responsible_assistant') != role
            or goal.get('parent_task_id') != 'fc-20261010-goal-delivery-assistant-runtime-v1'
            or goal.get('authorized_scope') != [ORIGINAL_PAID16_SCOPE]
            or goal.get('primary_owner') != 'paid-growth-data'
            or 'paid-growth-data' not in goal.get('producer_departments', [])
            or goal.get('acceptance_capability') != 'paid'
            or auth_pin['sha256'] != ORIGINAL_A3_AUTHORITY_SHA256
            or goal.get('authorization_pin') != auth_pin
            or authority.get('routine_decisions') is not True
            or 'paid' not in authority.get('review_capabilities', [])
            or registry.get(role, {}).get('new_dispatch_enabled') is False
            or not binding.get('task_id')
            or outbox_pin['sha256'] != identity['result_sha256']
            or any(box.get(field) != value for field, value in {
                'task_id': identity['task_id'], 'department': role,
                'candidate_version': identity['candidate_version'],
                'scope': ORIGINAL_PAID16_SCOPE, 'status': 'partial',
                'fixed_chat_task_id': binding['task_id']}.items())
            or box.get('qa_verdict') is not None
            or box.get('formal_whole_goal_QA_performed') is not False
            or box.get('notification_sent') is not False
            or box.get('external_permission_issued') is not False):
        _fail('exact active original A3 non-PASS source, authority and current binding required')
    return {'goal': goal, 'outbox': outbox_pin, 'fixed_chat_task_id': binding['task_id']}


class NotificationAttempt(TypedDict):
    """Internal call reservation; never a provider event or execution receipt."""
    sequence: int
    attempt_id: str
    previous_attempt_id: str
    identity: dict[str, str]
    tool: str
    target_thread_id: str
    payload: dict[str, Any]
    claim: dict[str, Any]
    call_started_at: str


class NativeBoundNotificationAttempt(NotificationAttempt):
    """The native pages are frozen before this reservation, never backfilled."""
    native_before: dict[str, dict[str, Any]]


def goal_delivery_enabled(root):
    """The global switch alone does not migrate an existing task."""
    config = _w().read_json(Path(root) / "data/task-contract.json").get("goal_delivery_runtime", {})
    if isinstance(config,dict) and config.get('model')=='department_autonomous_delivery_v1':
        from department_autonomy import current_mode
        return current_mode(root)
    return (isinstance(config, dict) and config.get("model") == "goal_delivery_assistant_v1"
            and config.get("assistant_decisions_enabled") is True)


def goal_delivery(root, task_id=None, snapshot=None):
    if not goal_delivery_enabled(root):
        return None
    if snapshot is None:
        snapshot = _w().read_json(_w().snapshot_path(Path(root), task_id))
    goal = snapshot.get("goal_delivery") if isinstance(snapshot, dict) else None
    return goal if isinstance(goal, dict) else None


def coordinator_roles(root, *, task_id=None):
    registry = _w().department_registry(root)
    if not goal_delivery_enabled(root) or (task_id is not None and goal_delivery(root, task_id) is None):
        return ROLES & registry.keys()
    return {role for role, item in registry.items()
            if item.get("coordination_authority", {}).get("routine_decisions") is True
            and item.get("new_dispatch_enabled") is not False} | ({"operations"} & registry.keys())


def review_capabilities(root, role):
    authority = _w().department_registry(root).get(role, {}).get("coordination_authority", {})
    values = authority.get("review_capabilities", [])
    return {value for value in values if isinstance(value, str) and value.strip()} if isinstance(values, list) else set()


def _goal_actor(root, identity, role, *, assigned=True):
    """Check routine responsibility without interpreting actor metadata as auth."""
    source = _collaboration_source(root, identity)
    if source is not None and role != source['responsible_assistant']:
        _fail('only original responsible assistant may handle this collaboration result')
    goal = goal_delivery(root, identity["task_id"])
    if goal is None:
        route = result_lane(root, identity)
        if route.get('source_mode') in {'scheduled_run', 'original_paid16'} and role != route.get('target_department'):
            _fail('only exact original source responsible assistant may handle this result')
        return goal
    if is_original_a3_conclusion_identity(identity) and role == identity['sender_department']:
        # A producer may commit its own truthful non-PASS conclusion, but may
        # never turn that event into an independent acceptance or QA verdict.
        source_goal = _original_a3_live_goal(root, identity)['goal']
        if goal != source_goal:
            _fail('original A3 conclusion goal changed')
        return goal
    if role == "operations":
        if identity["sender_department"] == "operations":
            _fail("native control producer cannot accept its own result")
        return goal
    producers = goal.get("producer_departments", [])
    if role == identity["sender_department"] or role in producers:
        _fail("independent assistant required; self review rejected")
    if identity["sender_department"] == "operations":
        from native_control_result import assigned_assistant, matches
        snapshot=_w().read_json(_w().snapshot_path(root, identity["task_id"]))
        if matches(snapshot):assigned_assistant(root,snapshot,role)
    if assigned and role != goal.get("responsible_assistant"):
        _fail("only assigned responsible assistant may handle this result; explicit transfer required")
    capability = goal.get("acceptance_capability")
    from technical_review_backup import review_capable
    if not review_capable(root, role, goal, task_id=identity["task_id"],
                          transfer_from=goal.get("responsible_assistant") if not assigned else None):
        _fail("assistant lacks the task acceptance capability or approved backup methods")
    return goal


def _w():
    import workflow_control
    return workflow_control


def _fail(message):
    raise _w().WorkflowError(message)


def _canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"))


def _sha(value):
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def exact_identity(request):
    identity = {key: request.get(key) for key in IDENTITY_FIELDS}
    if any(not isinstance(value, str) or not value.strip() for value in identity.values()):
        _fail("exact original result identity required")
    _w().validate_task_id(identity["task_id"])
    if not re.fullmatch(r"[0-9a-f]{64}", identity["result_sha256"]):
        _fail("final outbox SHA-256 required")
    return identity


def _key(identity):
    return _sha([identity[name] for name in IDENTITY_FIELDS])


def delivery_identity(root, identity, *, purpose=None, route=None):
    """The sender's delivery obligation is distinct from the review identity."""
    identity = exact_identity(identity)
    route = result_lane(root, identity) if route is None else route
    purpose = route.get('lane') if purpose is None else purpose
    target = route.get('target_department')
    binding = _w().department_registry(root).get(target, {}).get('chat_binding', {})
    if (purpose not in DELIVERY_PURPOSES or purpose != route.get('lane')
            or not target or not binding.get('task_id')):
        _fail('exact current notification target and purpose required')
    return {**identity, 'target_department': target,
            'target_thread_id': binding['task_id'], 'purpose': purpose}


def _delivery_key(identity):
    return 'notification:' + _sha([identity[key] for key in
        (*IDENTITY_FIELDS, 'target_department', 'target_thread_id', 'purpose')])


def _committed_result(root, record):
    """Read an existing exact SQL/native commit without selecting claim tokens."""
    database = _w().safe_path(root, str(DATABASE))
    if not database.is_file():
        _fail('existing committed native result required')
    connection = sqlite3.connect(database.as_uri() + '?mode=ro', uri=True)
    try:
        row = connection.execute(
            'SELECT status,payload_json,native_record_json FROM reservations '
            'WHERE result_key=? AND effect_key=?',
            (_key(exact_identity(record)), _sha([record['event'], record['idempotency_key']]))).fetchone()
    finally:
        connection.close()
    if (not row or row[0] != 'committed' or json.loads(row[2] or 'null') != record
            or _native_readback(root, json.loads(row[1])) != record):
        _fail('exact committed SQL and native result readback required')
    return _sha([record, row[1]])


def committed_original_a3_conclusion(root, identity):
    """Read the one native+SQL A3 partial conclusion; never infer QA PASS."""
    if not is_original_a3_conclusion_identity(identity):
        return None
    source = _original_a3_live_goal(root, identity)
    w = _w(); rows = w._result_handoff_rows(root, identity['task_id'])
    exact = [row for row in rows if w._result_identity(row) ==
             tuple(identity[key] for key in IDENTITY_FIELDS[1:])]
    conclusions = [row for row in exact if row.get('event') == 'assistant_conclusion']
    if not conclusions:
        return None
    if len(conclusions) != 1:
        _fail('one exact original A3 assistant conclusion required')
    row = conclusions[0]
    if (row.get('outbox') != source['outbox']
            or row.get('coordinator_role') != 'operations-assistant-3'
            or row.get('responsible_assistant') != 'operations-assistant-3'
            or not row.get('coordinator_owner')
            or type(row.get('coordination_fence')) is not int
            or row.get('conclusion_status') != 'partial_nonpass'
            or row.get('next_owner') != 'operations-assistant-3'
            or not isinstance(row.get('next_action'), str) or not row['next_action'].strip()
            or row.get('acceptance_proven') is not False
            or row.get('external_permission_issued') is not False
            or row.get('business_goal_closed') is not False
            or any(other.get('event') == 'controller_decision'
                   and other.get('coordinator_role') == 'operations-assistant-3'
                   for other in exact)):
        _fail('original A3 partial conclusion cannot be self acceptance or a closed goal')
    _committed_result(root, row)
    return row


def readback_direct_repair_pilot(root, proof):
    """A genuine root intake and exact native next-action notice, not a fixture.

    Direct ownership of the repair does not impersonate the original assistant
    or grant the underlying paid business task a production permission.
    """
    import direct_system_repair as direct
    from goal_delivery_runtime import _native_document
    from qa_review_plan import _review_same_goal_send_wrapper
    w = _w()
    if (proof.get("task_id") != direct.TASK or proof.get("scope") != direct.SCOPE
            or proof.get("actual_executor") != "operations" or proof.get("external_writes") != 0
            or proof.get("business_goal_closed") is not False
            or proof.get("original_identity") != ORIGINAL_A3_CONCLUSION
            or w.validate_workflow_events(root, direct.TASK)):
        _fail("exact actual internal direct repair pilot required")
    events = [e for e in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS)
              if e.get("task_id") == direct.TASK and e.get("event_id") == proof.get("received_event_id")]
    if len(events) != 1:
        _fail("one committed actual headquarters intake required")
    intake = events[0].get("details",{}).get("direct_recovered_knowledge",{})
    if intake.get("identity") != ORIGINAL_A3_CONCLUSION or intake.get("actual_receiver") != "operations":
        _fail("real original non-PASS source intake required")
    source = direct._doc(root,intake["source"])
    checked = w._validate_goal_completed_result(root,source["request"],source["request"]["source_thread_id"])
    if checked != intake.get("actual_completed_result"):
        _fail("intake does not read back the actual original final")
    actions = direct._doc(root,intake["next_actions"])
    if (actions.get("business_goal_closed") is not False or not actions.get("next_actions")
            or any(not a.get("owner") or not a.get("action") or not a.get("unblock_condition")
                   or w._parse_observed_at(a.get("next_check_at")) is None for a in actions["next_actions"])):
        _fail("partial result must retain named remaining work and dated recovery conditions")
    invocation = _review_same_goal_send_wrapper(direct._doc(root,proof["actual_native_send"]))
    payload = proof["notice_payload"]
    if invocation.get("exact_consumed_prompt") != payload or w.file_digest(root,payload["path"]) != payload:
        _fail("actual notice must consume these exact bytes")
    fixed = w.department_registry(root)["operations-assistant-3"]["chat_binding"]
    after = _native_document(root,proof["actual_recipient_after"])
    thread = after.get("thread",{})
    if invocation.get("thread_id") != fixed["task_id"] or any(thread.get(k)!=fixed[v] for k,v in
            (("id","task_id"),("title","title"),("cwd","cwd"))):
        _fail("notice recipient is not the original fixed A3")
    text = w.safe_path(root,payload["path"]).read_text()
    local_input = proof.get('actual_recipient_input')
    if local_input:
        validate_actual_delegation_input(root,local_input,after,payload)
    matches = []
    for turn in after.get("turns",[]):
        inputs = [i for i in turn.get("items",[]) if i.get("type")=="userMessage"
                  and "".join(c.get("text","") for c in i.get("content",[]) if c.get("type")=="text")==text]
        finals = [i for i in turn.get("items",[]) if i.get("type")=="agentMessage"
                  and i.get("phase")=="final_answer" and i.get("text","").strip()]
        matched_input = len(inputs)==1 or (local_input and turn.get('id')==local_input.get('turn_id'))
        if matched_input and len(finals)==1 and _pilot_final_matches(turn,finals[0]):
            matches.append((turn,finals[0]))
    if len(matches)!=1:
        _fail("exact notice must be delivered once and produce a real completed nonempty reply")
    turn, final = matches[0]
    return {"state":"PROVEN", "received_event_id":events[0]["event_id"],
            "actual_next_action_notice_delivered":True,"actual_native_reply_id":final["id"],
            "actual_turn_id":turn["id"],"business_goal_closed":False,"external_writes":0}


def _pilot_final_matches(turn,final):
    return (turn.get('status')=='completed' and not turn.get('error')
            and final.get('phase')=='final_answer' and isinstance(final.get('text'),str)
            and ORIGINAL_A3_CONCLUSION['task_id'] in final['text']
            and '<heartbeat>' not in final['text'])


def validate_actual_delegation_input(root,locator,native,payload):
    """Read an actual native forwarded FCO without inventing a userMessage."""
    import html
    w=_w();fixed=w.department_registry(root)['operations-assistant-3']['chat_binding']
    source=w.department_registry(root)['operations']['chat_binding']
    session=Path(locator.get('session_path',''))
    if session.is_symlink() or session.resolve().parent.parent.parent != (Path.home()/'.codex/sessions').resolve():
        # Sessions live in YYYY/MM/DD directories beneath the platform root.
        if session.is_symlink() or (Path.home()/'.codex/sessions').resolve() not in session.resolve().parents:
            _fail('actual original platform-owned session required')
    if not session.name.endswith(fixed['task_id']+'.jsonl'):
        _fail('actual fixed recipient session identity required')
    wanted={locator.get('context_line'),locator.get('input_line')};found={};meta=None
    with session.open(encoding='utf-8') as stream:
        for n,line in enumerate(stream,1):
            if n==1:meta=json.loads(line)
            if n in wanted:found[n]=(line,json.loads(line))
            if len(found)==2:break
    if meta is None or meta.get('type')!='session_meta' or meta.get('payload',{}).get('id')!=fixed['task_id'] or len(found)!=2:
        _fail('actual recipient session header and exact source rows required')
    context_line,context=found[locator['context_line']];input_line,item=found[locator['input_line']]
    if (hashlib.sha256(context_line.encode()).hexdigest()!=locator.get('context_sha256')
            or hashlib.sha256(input_line.encode()).hexdigest()!=locator.get('input_sha256')
            or context.get('type')!='turn_context' or context['payload'].get('turn_id')!=locator.get('turn_id')
            or context['payload'].get('cwd')!=fixed['cwd'] or item.get('type')!='response_item'
            or item['payload'].get('type')!='function_call_output'):
        _fail('native source row hash/context/type mismatch')
    fco=item['payload'];output=fco.get('output','');body=re.fullmatch(
        r'<codex_delegation>\s*<source_thread_id>([^<]+)</source_thread_id>\s*<input>([\s\S]*)</input>\s*</codex_delegation>',output)
    raw=w.safe_path(root,payload['path']).read_text()
    if (not body or body[1]!=source['task_id'] or html.unescape(body[2]) not in {raw,raw+'\n'}
            or not any(i.get('type')=='functionCallOutput' and i.get('id')==fco.get('id')
                       and i.get('name')=='send_message_to_thread' and i.get('namespace')=='codex_app'
                       for turn in native.get('turns',[]) if turn.get('id')==locator['turn_id'] for i in turn.get('items',[]))):
        _fail('actual original sender/forwarded bytes/native tool namespace mismatch')
    return {'actual_recipient_turn_id':locator['turn_id'],'actual_forwarded_input_id':fco['id']}


def current_assignment_for_role(root,role):
    """Expose a proven live assignment after compaction; never infer completion."""
    w=_w();config=w.read_json(Path(root)/'data/department-current-assignment.json')
    pin=config.get('assignments',{}).get(role)
    from goal_continuity import current_assignment
    pending=[];errors=[];seen=[]
    for prior in config.get('suspended_assignments',{}).get(role,[]):
        if prior == pin or prior in seen:continue
        seen.append(prior)
        try:
            # Historical display only; current assignment and every execution
            # still use the uncached original source/identity/permission entry.
            from readonly_work_view_cache import memoized_view
            old=memoized_view(root, 'historical-assignment-view', [role,prior],
                lambda: current_assignment(root,role,prior), required=[Path(root)/prior['path']])
            if old is None:raise w.WorkflowError('unsupported suspended assignment schema')
            if old and old.get('resume_required'):pending.append(old)
        except (w.WorkflowError,OSError,ValueError,KeyError,TypeError,AttributeError) as error:
            errors.append({'source':prior,'reason':str(error),'blocks_other_tasks':False})
    if pin is None:
        if not pending:
            return {'resume_required':False,'assignment_errors':errors} if errors else None
        return {**pending.pop(),'resumed_suspended_assignment':True,
                'unfinished_assignment_queue':pending,'assignment_errors':errors}
    try:
        original = w.safe_path(root,pin['path'])
        source = w.read_json(original)
        snapshot = w.snapshot_path(root,source.get('task_id',''))
        if w.read_json(snapshot).get('current_state') in w.TERMINAL_STATES:
            # A closed historical hold is a display source, not permission to
            # resume execution. The actual current index/snapshot is fresh.
            from readonly_work_view_cache import memoized_view
            generic = memoized_view(root,'historical-assignment-view',[role,pin,'closed-source-hold'],
                lambda: current_assignment(root,role,pin),required=[original,snapshot])
        else:
            generic = current_assignment(root,role,pin)
    except (w.WorkflowError,OSError,ValueError,KeyError,TypeError,AttributeError) as error:
        errors.append({'source':pin,'reason':str(error),'blocks_other_tasks':False})
        if not pending:return {'resume_required':False,'assignment_errors':errors,'current_assignment_invalid':True}
        return {**pending.pop(),'resumed_suspended_assignment':True,'current_assignment_invalid':True,
                'unfinished_assignment_queue':pending,'assignment_errors':errors}
    if generic is not None:
        if not generic.get('resume_required') and pending:
            generic={**pending.pop(),'resumed_suspended_assignment':True}
        return {**generic,'unfinished_assignment_queue':pending,'assignment_errors':errors}
    try:
        import direct_system_repair as direct
        from qa_review_plan import _review_same_goal_send_wrapper
        if direct.context(root,direct.TASK) is None:
            _fail('actual current assignment requires its human authorized source')
        doc=direct._doc(root,pin)
        invocation=_review_same_goal_send_wrapper(direct._doc(root,doc['actual_native_send']))
        binding=w.department_registry(root).get(role,{}).get('chat_binding',{})
        if (role!='operations-assistant-3' or doc.get('task_id')!=ORIGINAL_A3_CONCLUSION['task_id']
                or doc.get('original_identity')!=ORIGINAL_A3_CONCLUSION
                or doc.get('business_goal_closed') is not False
                or invocation['thread_id']!=binding.get('task_id')
                or invocation['exact_consumed_prompt']!=doc.get('payload')
                or w.file_digest(root,doc['payload']['path'])!=doc['payload']):
            _fail('current assignment exact task/recipient/payload/source mismatch')
        return {**doc,'source':pin,'actual_message_delivered':True,
                'unfinished_assignment_queue':pending,'assignment_errors':errors,
                'resume_before_old_automation_or_summary':True,'permissions_inherited':False}
    except (w.WorkflowError,OSError,ValueError,KeyError,TypeError,AttributeError) as error:
        errors.append({'source':pin,'reason':str(error),'blocks_other_tasks':False})
        if not pending:return {'resume_required':False,'assignment_errors':errors,'current_assignment_invalid':True}
        return {**pending.pop(),'resumed_suspended_assignment':True,'current_assignment_invalid':True,
                'unfinished_assignment_queue':pending,'assignment_errors':errors}


def hq_knowledge_source(root, identity, *, require_transport=False):
    from department_autonomy import autonomous_result_route,knowledge_source,MODE
    route=autonomous_result_route(root,identity)
    if route is not None and route.get('source_mode')==MODE:
        return knowledge_source(root,identity,require_transport)
    """Memoize only inside the caller's strict byte-tracked validation request."""
    w = _w()
    context = w._VALIDATION_CONTEXT.get() if hasattr(w, '_VALIDATION_CONTEXT') else None
    key = ('hq_knowledge', str(Path(root).resolve()), KNOWLEDGE_CONSUMER_VERSION,
           _canonical(exact_identity(identity)))
    if context is not None:
        # Stat tracked sources before reusing a request proof. A changed source
        # clears the memo through the shared byte reader, even before commit.
        for path in list(context.files):
            context.bytes(path)
    if context is not None and key in context.proofs:
        proof = context.proofs[key]
    else:
        proof = _hq_knowledge_source(root, identity)
        if context is not None:
            context.proofs[key] = proof
    if require_transport:
        transport_key = (*key, 'transport')
        if context is not None and transport_key in context.proofs:
            return context.proofs[transport_key]
        original = proof
        proof = _knowledge_transport(root, proof)
        if context is not None:
            # First reading the transport adds a tracked dependency and may
            # invalidate memo entries; retain the already verified source too.
            context.proofs[key] = original
            context.proofs[transport_key] = proof
    return proof


def _knowledge_native_reply(root, source, fixed, *, completed):
    """Authenticate existing native message bytes without producer effects replay."""
    from goal_delivery_runtime import _collaboration_native, _collaboration_final_message
    from qa_review_plan import _review_native_containers
    w = _w(); native = _collaboration_native(root, source.get('actual_native_completion'))
    _review_native_containers(native)
    reply = source.get('visible_reply', {})
    if w.file_digest(root, reply.get('path', '')) != reply:
        _fail('original full native conclusion UTF-8 pin required')
    raw = w.validation_bytes(w.safe_path(root, reply['path']))
    thread = native.get('thread', {})
    if (thread.get('id') != fixed.get('task_id')
            or any(thread.get(key) != fixed.get(key) for key in ('cwd', 'title'))):
        _fail('original exact independent fixed native conclusion thread required')
    if isinstance(native.get('turns'), list):
        turns = [turn for turn in native['turns'] if turn.get('id') == source.get('source_turn_id')]
        if len(turns) != 1 or turns[0].get('error') or (completed and turns[0].get('status') != 'completed'):
            _fail('original exact native conclusion turn required')
        turn = turns[0]
        messages = [item for item in turn.get('items', []) if item.get('type') == 'agentMessage'
                    and item.get('id') == source.get('source_message_id')
                    and item.get('phase') in ({'final_answer'} if completed else {'commentary', 'final_answer'})]
        if len(messages) != 1:
            _fail('one original exact native conclusion message required')
        message = messages[0]
    else:
        message = _collaboration_final_message(native, fixed['task_id'])
        turn = native.get('turn', {})
        if not turn:
            turn = {'id': native.get('turn_id'), 'startedAt': native.get('startedAt')}
        if turn.get('id') != source.get('source_turn_id'):
            _fail('original exact completed conclusion turn mismatch')
        if source.get('source_message_id') and message.get('id') != source['source_message_id']:
            _fail('original exact completed conclusion message mismatch')
    _review_native_containers(turn); _review_native_containers(message)
    if (not isinstance(message.get('text'), str) or message['text'].encode('utf-8') != raw
            or (completed and message.get('phase') != 'final_answer')):
        _fail('full original conclusion UTF-8 differs from the native message')
    observed = w._parse_observed_at(source.get('reply_observed_at'))
    if (observed is None or type(turn.get('startedAt')) not in {int, float}
            or not 0 < turn['startedAt'] <= observed.timestamp() <= dt.datetime.now(dt.timezone.utc).timestamp()):
        _fail('original ordered native conclusion observation required')
    if source.get('source_reply_sha256') and source['source_reply_sha256'] != reply['sha256']:
        _fail('original queued conclusion hash mismatch')
    return raw


def _knowledge_events(root, task_id):
    """Authenticate native commits without asking the reviewer to review again."""
    w = _w(); events = w.read_jsonl(Path(root) / w.WORKFLOW_EVENTS)
    previous = ''; seen = set()
    for event in events:
        if (not isinstance(event, dict) or not event.get('event_id') or event['event_id'] in seen
                or event.get('previous_event_hash', '') != previous
                or event.get('event_hash') != w.sha256_value({key: value for key, value in event.items() if key != 'event_hash'})):
            _fail('intact complete native workflow commit hash chain required')
        seen.add(event['event_id']); previous = event['event_hash']
    selected = [event for event in events if event.get('task_id') == task_id]
    if not selected or selected[0].get('state') != 'planned':
        _fail('original planned task and native knowledge source commits required')
    if (any(event.get('details', {}).get('same_state_formal_qa_commit') for event in selected)
            and w.validate_workflow_events(Path(root), task_id)):
        _fail('semantically valid original workflow event order required')
    return selected


def assistant_decision_bundle(root, box, goal, assistant):
    """A partial batch reports real decisions, not an invented whole-goal PASS."""
    pin=box.get('assistant_decision_bundle')
    if pin is None:return None
    w=_w()
    if (box.get('status')!='partial' or box.get('qa_verdict')=='pass'
            or box.get('goal_completion_claimed') is not False
            or box.get('production_write_allowed') is not False
            or box.get('external_permission_issued') is not False
            or pin not in box.get('evidence',[]) or w.file_digest(root,pin.get('path',''))!=pin):
        _fail('partial knowledge must preserve exact non-PASS bundle and no completion/permission claim')
    doc=w.read_json(w.safe_path(root,pin['path']));items=doc.get('items')
    if doc.get('schema')!='assistant-actual-decision-bundle/v1' or not isinstance(items,list) or not 1<=len(items)<=100:
        _fail('bounded existing assistant decision bundle required')
    database=w.safe_path(root,str(DATABASE))
    if not database.is_file():_fail('partial knowledge existing committed coordinator audit required')
    connection=sqlite3.connect(database.as_uri()+'?mode=ro',uri=True)
    try:audit=connection.execute('SELECT payload_json,previous_hash,record_hash FROM coordination_audit ORDER BY seq').fetchall()
    finally:connection.close()
    previous='';actors={}
    for raw,prior,digest in audit:
        event=json.loads(raw)
        if prior!=previous or digest!=_sha([previous,event]):
            _fail('partial knowledge actual coordinator audit changed')
        previous=digest
        if event.get('event')=='effect_reserved':
            key=(_key(exact_identity(event['identity'])),event['details']['effect_key'])
            actors.setdefault(key,set()).add(event['details'].get('role'))
    verified=[];seen=set()
    for item in items:
        identity=exact_identity(item.get('identity',{}));key=_key(identity)
        if key in seen or identity['sender_department'] not in goal['producer_departments']:
            _fail('one original producer result per knowledge bundle item required')
        seen.add(key);route=result_lane(root,identity)
        if route['lane']!='professional_acceptance' or route.get('target_department')!=assistant:
            _fail('knowledge bundle result must belong to this exact responsible assistant')
        _validate_queued(root,identity)
        rows=w._result_handoff_rows(root,identity['task_id'])
        decision=[row for row in rows if row.get('record_id')==item.get('decision_record_id')]
        follow=[row for row in rows if row.get('record_id')==item.get('followthrough_record_id')]
        if (len(decision)!=1 or len(follow)!=1 or decision[0].get('event')!='controller_decision'
                or follow[0].get('event')!='controller_followthrough'):
            _fail('one real decision and actual next action or named waiting record required')
        for row in [decision[0],follow[0]]:
            if exact_identity(row)!=identity:
                _fail('partial knowledge decision/result actor differs')
            _committed_result(root,row)
            # Scheduled native rows used to omit actors; the authenticated
            # original reservation audit retains the actual handling role.
            committed_actors=actors.get((_key(identity),_sha([row['event'],row['idempotency_key']])),set())
            if committed_actors!={assistant} or row.get('coordinator_role',assistant)!=assistant:
                _fail('partial knowledge actual committed coordinator differs')
        if (decision[0].get('decision') not in {'rework','wait_external','continue','accept','release_gate','close_scope'}
                or not decision[0].get('next_owner') or not decision[0].get('next_action')
                or rows.index(follow[0])<=rows.index(decision[0])):
            _fail('partial knowledge needs ordered actual responsibility and followthrough')
        if follow[0].get('followthrough_status') in {'external_wait_registered','blocked_with_owner'}:
            if not follow[0].get('unblock_condition') or w._parse_observed_at(follow[0].get('next_check_at')) is None:
                _fail('named waiting must retain a real release condition and review time')
        elif follow[0].get('followthrough_status') in {None,'pending'}:
            _fail('a decision alone is not an actual next action')
        verified.append({'identity':identity,'decision':decision[0],'followthrough':follow[0]})
    return {'source_kind':'committed_assistant_decision_bundle','bundle':pin,'items':verified,
            'acceptance_proven':False,'parent_goal_closed':False,'external_permission_issued':False}


def _knowledge_current_reviewer(root, plan, fixed):
    """Read-only same-role rotation of a frozen formal plan, never a write alias.

    The caller separately verifies the exact native binding event, plan pin,
    summary evidence, original goal, committed decision and real native reply.
    """
    role = plan.get('reviewer_department')
    if plan.get('reviewer_thread_id') == fixed:
        return []
    from department_rotation import _records, _id
    matches = [row for row in _records(root) if row.get('role') == role
               and _id(row['old_binding']) == plan.get('reviewer_thread_id')
               and _id(row['new_binding']) == fixed]
    if (len(matches) != 1 or plan.get('controller_thread_id') not in
            (None, plan.get('reviewer_thread_id'))):
        _fail('frozen reviewer needs one trusted same-role rotation')
    row = matches[0]
    return [row['history'], *[pin for pin in
        _w().read_json(Path(root)/'data/department-registry.json').get('window_rotation_records', [])
        if _w().read_json(_w().safe_path(root,pin['path'])) == row]]


def _hq_knowledge_source(root, identity, *, require_transport=False):
    """Read a formal assistant conclusion; never execute professional review.

    The original QA receipt and its causal source prefix are authenticated by
    their native commit event, frozen binding and current full pins. Later
    knowledge rows cannot become an input to their own acceptance proof.
    """
    w = _w(); root = Path(root).resolve(); identity = exact_identity(identity)
    snapshot = w.read_json(w.snapshot_path(root, identity['task_id']))
    goal = goal_delivery(root, snapshot=snapshot)
    assistant = goal.get('responsible_assistant') if goal else None
    registry = w.department_registry(root)
    if (assistant != identity['sender_department'] or assistant == 'operations'
            or assistant in goal.get('producer_departments', [])
            or assistant not in coordinator_roles(root, task_id=identity['task_id'])):
        _fail('only the independent original responsible assistant supplies HQ knowledge')
    from technical_review_backup import review_capable
    if not review_capable(root, assistant, goal, task_id=identity['task_id']):
        _fail('current responsible assistant capability required')
    rows = w.read_jsonl(w.receipts_path(root, identity['task_id']))
    previous = ''; seen = set()
    for row in rows:
        if (row.get('task_id') != identity['task_id'] or not row.get('receipt_id')
                or row['receipt_id'] in seen or row.get('previous_hash', '') != previous
                or row.get('receipt_hash') != w.sha256_value(w._receipt_payload_for_hash(row))):
            _fail('intact original receipt hash chain required for knowledge')
        seen.add(row['receipt_id']); previous = row['receipt_hash']
        for pin in row.get('evidence', []):
            if w.file_digest(root, pin.get('path', '')) != pin:
                _fail('knowledge original receipt source pin changed; reconcile exact source')
    handoffs = w._result_handoff_rows(root, identity['task_id'])
    exact = [row for row in handoffs if w._result_identity(row) ==
             tuple(identity[key] for key in IDENTITY_FIELDS[1:])]
    queued = [row for row in exact if row.get('event') == 'notification_queued']
    if len(queued) != 1:
        _fail('one exact native knowledge queue required')
    source = queued[0]; pin = source.get('outbox', {})
    if w.file_digest(root, pin.get('path', '')) != pin or pin.get('sha256') != identity['result_sha256']:
        _fail('exact frozen assistant summary required')
    box = w.read_json(w.safe_path(root, pin['path']))
    fixed = registry[assistant].get('chat_binding', {}).get('task_id')
    if (any(box.get(k) != v for k, v in {'task_id': identity['task_id'], 'department': assistant,
            'candidate_version': identity['candidate_version']}.items())
            or box.get('fixed_chat_task_id', box.get('chat_task_id')) != fixed
            or box.get('scope') not in goal.get('authorized_scope', [])
            or box.get('chat_reply', {}).get('nonempty') is not True
            or box.get('chat_reply', {}).get('in_current_fixed_department_chat') is not True):
        _fail('exact original summary identity, scope and fixed assistant reply required')
    for evidence in [*box.get('evidence', []), *source.get('evidence', [])]:
        if w.file_digest(root, evidence.get('path', '')) != evidence:
            _fail('knowledge summary or queue evidence changed')
    events = _knowledge_events(root, identity['task_id'])
    from qa_review_plan import _binding, GOAL_IDENTITY
    original_goal = events[0].get('details', {}).get('goal_delivery', {})
    if any(original_goal.get(key) != goal.get(key) for key in GOAL_IDENTITY
           if key != 'responsible_assistant'):
        _fail('knowledge must retain the original planned task goal and authorized scope')
    binding = _binding(root, snapshot)
    nonpass_decision = None
    if box.get('qa_verdict') != 'pass':
        bundle=assistant_decision_bundle(root,box,goal,assistant)
        if bundle is not None:
            nonpass_decision=bundle
        elif is_original_a3_conclusion_identity(identity):
            nonpass_decision = committed_original_a3_conclusion(root, identity)
            if nonpass_decision is None:
                _fail('original A3 partial summary requires its exact committed non-PASS conclusion')
        else:
            decisions = [row for row in handoffs if row.get('event') == 'controller_decision'
                         and row.get('coordinator_role') == assistant
                         and row.get('responsible_assistant') == assistant
                         and (pin in row.get('evidence', []) or row.get('outbox') == pin)]
            if not decisions or decisions[-1].get('decision') not in {'rework', 'wait_external', 'continue'}:
                _fail('partial/rework/blocked summary requires its exact committed assistant conclusion')
            nonpass_decision = decisions[-1]
            _committed_result(root, nonpass_decision)
    if binding is None and nonpass_decision is not None:
        # Failure to bind a first review can itself be a truthful conclusion;
        # its committed original assistant decision is not an issued QA PASS.
        binding = {'reviewer_department': assistant,
                   'goal_identity': {key: goal.get(key) for key in GOAL_IDENTITY}, 'pin': None}
    if (not isinstance(binding, dict) or binding.get('reviewer_department') != assistant
            or binding.get('goal_identity') != {key: goal.get(key) for key in GOAL_IDENTITY}):
        _fail('current exact frozen original independent review binding required')
    plan_pin = binding.get('pin')
    if plan_pin is not None:
        if w.file_digest(root, plan_pin.get('path', '')) != plan_pin:
            _fail('original review plan pin changed')
        plan = w.read_json(w.safe_path(root, plan_pin['path']))
    else:
        plan = {'scope': box['scope'], 'task_id': identity['task_id'], 'reviewer_department': assistant,
                'reviewer_thread_id': fixed, 'single_final_reviewer': True}
    reviewer_rotation_pins = _knowledge_current_reviewer(root, plan, fixed)
    bound = [event for event in events if event.get('details', {}).get('qa_review_plan_bound') == binding]
    all_bindings = [event for event in events if event.get('details', {}).get('qa_review_plan_bound')]
    if ((plan_pin is not None and not bound) or plan.get('task_id') != identity['task_id']
            or (plan_pin is not None and all_bindings[-1]['details']['qa_review_plan_bound'] != binding)
            or plan.get('reviewer_department') != assistant
            or (plan.get('reviewer_thread_id') != fixed and not reviewer_rotation_pins)
            or plan.get('single_final_reviewer') is not True
            or plan.get('scope') != box.get('scope')
            or (plan_pin is not None and plan_pin not in box.get('evidence', []))):
        _fail('formal original plan, native binding and summary relation required')
    accepted = [row for row in rows if row.get('receipt_type') == 'qa_verdict'
                and row.get('department') == assistant and row.get('scope') == plan['scope']]
    latest = accepted[-1] if accepted else None
    source_commit = None; qa = None; prefix = None
    if box.get('qa_verdict') == 'pass':
        if (not latest or latest.get('verdict') != 'pass' or pin not in latest.get('evidence', [])
                or latest.get('chat_task_id') != fixed
                or any(latest.get(key) != plan.get(key) for key in ('task_id', 'action_id', 'action_class', 'scope'))
                or any(row.get('supersedes_receipt_id') == latest['receipt_id'] for row in rows)
                or box.get('review_identity') != {key: plan.get(key) for key in
                    ('task_id', 'action_id', 'action_class', 'scope', 'candidate_version', 'candidate_sha256')}):
            _fail('latest exact formal independent acceptance required; revoked/replaced source rejected')
        commits = [event for event in events if (event.get('state') == 'qa_passed'
                   or (event.get('state') == 'closed'
                       and event.get('details', {}).get('same_state_formal_qa_commit') is True))
                   and event.get('details', {}).get('qa_receipt_id') == latest['receipt_id']
                   and event.get('details', {}).get('qa_receipt_hash') == latest['receipt_hash']]
        if not commits:
            _fail('actual native formal QA commit event required')
        bound_at = w._parse_observed_at(bound[-1].get('created_at'))
        accepted_at = w._parse_observed_at(latest.get('created_at'))
        committed_at = w._parse_observed_at(commits[-1].get('created_at'))
        queued_at = w._parse_observed_at(source.get('created_at'))
        ordinary_order = (all(value is not None for value in
                    (bound_at, accepted_at, committed_at, queued_at))
                    and bound_at <= accepted_at <= committed_at <= queued_at <= dt.datetime.now(dt.timezone.utc))
        # One historical V7 queue was frozen after the real PASS but before the
        # missing source event could be recovered. Its original hash and ID are
        # immutable; a real later same-state commit is allowed only for it.
        original_v7_late_commit = (
            identity['task_id'] == 'fc-20261015-schema3-qa-outbox-consumer-repair-v1'
            and source.get('record_id') == '58fd7a4f-bd66-42e6-a9ed-0d9cd62e3321'
            and source.get('record_hash') == '8390a5670909d9e3c692f3791672f29440d1f816c64e648d58abf43971cd6981'
            and source.get('result_sha256') == '8c692d924c900d92f6bd00ec2d4ed29017da5e28871ad0c0b80a1bdc53d60b9b'
            and latest.get('receipt_id') == 'e8bec2bb-152d-4bcc-955e-2ced62516d52'
            and commits[-1].get('state') == 'closed'
            and commits[-1].get('details', {}).get('same_state_formal_qa_commit') is True
            and all(value is not None for value in
                    (bound_at, accepted_at, committed_at, queued_at))
            and bound_at <= accepted_at <= queued_at < committed_at <= dt.datetime.now(dt.timezone.utc))
        if (not (ordinary_order or original_v7_late_commit)
                or events.index(bound[-1]) >= events.index(commits[-1])):
            _fail('original binding, formal acceptance, native commit and knowledge queue must be ordered')
        candidate = plan.get('candidate', {})
        acceptance = box.get('goal_acceptance', {})
        if (candidate not in box.get('evidence', []) or plan.get('candidate_sha256') != candidate.get('sha256')
                or plan.get('producer_department') not in goal.get('producer_departments', [])
                or acceptance.get('responsible_assistant') != assistant
                or acceptance.get('primary_owner') != goal.get('primary_owner')
                or acceptance.get('completion_criteria') != goal.get('completion_criteria')
                or not acceptance.get('accepted_scope')
                or any(scope not in goal.get('authorized_scope', []) for scope in acceptance['accepted_scope'])):
            _fail('original formal acceptance must retain its exact goal and producer identity')
        descriptors = [w.read_json(w.safe_path(root, evidence['path'])) for evidence in latest.get('evidence', [])
                       if evidence != pin]
        native_sources = [document for document in descriptors
                          if document.get('schema') == 'actual_native_control_acceptance/v1']
        if native_sources:
            if len(native_sources) != 1 or native_sources[0].get('task_id') != identity['task_id']:
                _fail('one original exact independent native acceptance source required')
            raw = _knowledge_native_reply(root, native_sources[0], registry[assistant]['chat_binding'], completed=False)
            expected = {'schema': 'actual_native_control_verdict/v1', 'task_id': identity['task_id'],
                        'candidate_version': plan['candidate_version'], 'producer_outbox': candidate,
                        'reviewer_outbox': pin, 'review_plan': plan_pin, 'reviewer': assistant,
                        'verdict': latest['verdict'], 'goal_acceptance': acceptance,
                        'production_write_allowed': False, 'external_permission_issued': False}
            if json.loads(raw) != expected:
                _fail('original actual native formal verdict identity differs')
        else:
            from qa_review_plan import _review_exact_native_reply
            _review_exact_native_reply(root, box, assistant)
        qa = latest; source_commit = commits[-1]
        index = rows.index(latest)
        prefix = {'count': index, 'head': rows[index - 1]['receipt_hash'] if index else '',
                  'qa_receipt_id': latest['receipt_id'], 'qa_receipt_hash': latest['receipt_hash']}
    else:
        source_commit = nonpass_decision
    _knowledge_native_reply(root, source, registry[assistant]['chat_binding'], completed=source.get('result_source_phase')!='delivery_ready')
    dependencies = [w.file_digest(root, str(path)) for path in
        (w.snapshot_path(root, identity['task_id']), w.receipts_path(root, identity['task_id']),
         w.result_handoff_path(root, identity['task_id']),
         root / 'data/department-registry.json', root / 'data/task-contract.json', root / w.WORKFLOW_EVENTS)]
    dependencies += [pin, *([plan_pin] if plan_pin else []), *box.get('evidence', []), *source.get('evidence', [])]
    dependencies += reviewer_rotation_pins
    dependencies += [source[key] for key in ('actual_native_completion', 'visible_reply')
                     if isinstance(source.get(key), dict)]
    if qa is not None:
        for document in native_sources:
            dependencies += [document[key] for key in ('actual_native_completion', 'visible_reply')
                             if isinstance(document.get(key), dict)]
    dependencies = list({item['path']: item for item in dependencies}.values())
    proof = {'consumer_version': KNOWLEDGE_CONSUMER_VERSION, 'identity': identity,
             'outbox': pin, 'review_plan': plan_pin, 'scope': plan['scope'],
             'acceptance_prefix': prefix, 'qa_receipt': qa, 'source_commit': source_commit,
             'queued_source': source, 'dependency_pins': dependencies,
             'acceptance_proven': qa is not None, 'notification_proven': True,
             'HQ_second_review_required': False, 'professional_review_executed': False}
    proof['dependency_fingerprint'] = _sha([KNOWLEDGE_CONSUMER_VERSION, identity, binding,
                                           prefix, source_commit, dependencies])
    return proof


def _knowledge_transport(root, original):
    w = _w(); root = Path(root).resolve(); proof = dict(original)
    identity = proof['identity']; registry = w.department_registry(root)
    exact = [row for row in w._result_handoff_rows(root, identity['task_id'])
             if w._result_identity(row) == tuple(identity[key] for key in IDENTITY_FIELDS[1:])]
    sent = [row for row in exact if row.get('event') == 'notification_sent']
    observed=[row for row in exact if row.get('event')=='controller_received'
              and row.get('result_lane')=='HQ_knowledge' and row.get('actual_recipient_read')]
    if not sent and len(observed)==1:
        from goal_continuity import actual_knowledge_read
        return actual_knowledge_read(root,observed[0],proof)
    if len(sent) != 1 or sent[0].get('target_department') != 'operations':
        _fail('exact actual HQ knowledge transport required')
    transport = sent[0].get('actual_native_transport', {})
    if w.file_digest(root, transport.get('path', '')) != transport:
        _fail('HQ knowledge transport source pin changed')
    target = registry.get('operations', {}).get('chat_binding', {}).get('task_id')
    policies = [row for row in w.read_jsonl(root / w.POLICY_DECISIONS)
                if row.get('decision_id') == sent[0].get('policy_decision_id')]
    delivery = sent[0].get('delivery_identity')
    if delivery is not None and delivery != delivery_identity(root, identity, route={
            'lane': 'HQ_knowledge', 'target_department': 'operations'}):
        _fail('original HQ notification delivery identity changed')
    action_key = _delivery_key(delivery).split(':', 1)[1] if delivery is not None else _key(identity)
    expected = {'status': 'allow', 'routing_status': 'routing_allowed', 'task_id': identity['task_id'],
                'department': identity['sender_department'], 'action_id': 'notify-result-' + action_key,
                'action_class': 'thread_message', 'scope': 'department_result:' + identity['task_id'] + ':' + identity['sender_department'],
                'target_department': 'operations', 'target_thread_id': target,
                'payload_sha256': sent[0].get('message_sha256')}
    if (len(policies) != 1 or any(policies[0].get(key) != value for key, value in expected.items())
            or not re.fullmatch(r'[0-9a-f]{64}', str(sent[0].get('message_sha256') or ''))):
        _fail('original exact HQ knowledge send policy required')
    checked = w._parse_observed_at(policies[0].get('checked_at'))
    recorded = w._parse_observed_at(sent[0].get('created_at'))
    if checked is None or recorded is None or not checked <= recorded <= dt.datetime.now(dt.timezone.utc):
        _fail('original ordered HQ knowledge policy and transport receipt required')
    effect_dependencies = []
    if delivery is not None:
        current = w.read_json(_notification_path(root, identity))
        if (current.get('identity') != identity or current.get('delivery_identity') != delivery
                or current.get('delivered') is not True or current.get('native_transport') != transport
                or current.get('policy_decision_id') != sent[0].get('policy_decision_id')
                or current.get('payload', {}).get('sha256') != sent[0].get('message_sha256')):
            _fail('readback_required: original bound HQ notification state and source required')
        invocation = sent[0].get('actual_native_invocation')
        effect = _notification_native_effect(root, current, {
            'actual_native_transport': transport, 'actual_native_invocation': invocation})
        if (sent[0].get('notification_attempt_id') != effect['attempt_id']
                or current.get('native_invocation') != invocation
                or current.get('native_effect') != effect or sent[0].get('native_effect') != effect):
            _fail('readback_required: HQ notification original invocation/effect/attempt binding changed')
        effect_dependencies = [invocation, *effect['native_before'].values(),
                               effect['payload'], w.file_digest(root, str(_notification_path(root, identity)))]
        proof.update(native_effect=effect, transport_binding='original_current_native_attempt_and_recipient_effect')
    else:
        # Original schema-1 rows have no current attempt. Preserve their exact
        # historical read path; it cannot discharge a new reserved delivery.
        from goal_delivery_runtime import _collaboration_native
        from qa_review_plan import _review_native_containers
        native = _collaboration_native(root, transport); _review_native_containers(native)
        native = native.get('actual_native_send', native)
        if (native.get('threadId') != target or native.get('isError') is True
                or ('status' in native and native['status'] not in {'sent', 'queued', 'running'})):
            _fail('successful exact historical HQ knowledge native transport required')
        existing = w.read_json(_notification_path(root, identity))
        if existing.get('schema_version') == '2.0' or existing.get('attempts'):
            _fail('readback_required: current HQ attempt cannot use the historical transport contract')
        proof.update(transport_binding='historical_original_schema_without_current_attempt')
    dependencies = [*proof['dependency_pins'], transport,
                    w.file_digest(root, str(root / w.POLICY_DECISIONS)),
                    w.file_digest(root, str(w.result_handoff_path(root, identity['task_id']))), *effect_dependencies]
    proof.update(transport=transport, notification_sent=sent[0], dependency_pins=dependencies)
    proof['dependency_fingerprint'] = _sha([KNOWLEDGE_CONSUMER_VERSION, proof['identity'],
                                           original['dependency_fingerprint'], sent[0], dependencies])
    return proof


@contextmanager
def coordination_lock(root):
    root = Path(root).resolve()
    path = _w().safe_path(root, str(COORDINATION_LOCK))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _collaboration_source(root, identity):
    """A declared fixed collaborator is a distinct source, never a department alias."""
    if identity['sender_department'] in _w().department_registry(root):
        return None
    from goal_delivery_runtime import collaboration_result_source
    return collaboration_result_source(root, identity)


def supplemental_owner_return_source(root, identity):
    """Read exact admitted old owner results; no reopening or execution rights."""
    w=_w();contract=w.read_json(Path(root)/'data/task-contract.json')
    entries=contract.get('result_handoff_contract',{}).get('owner_direct_return_sources',[])
    matches=[item for item in entries if item.get('identity')==identity]
    if not matches:return None
    if len(matches)!=1:_fail('one exact original owner return admission required')
    item=matches[0]
    if item.get('execution_rights_granted') is not False:_fail('owner return cannot grant execution rights')
    pins={}
    for name in ['outbox','actual_reply','actual_owner_command']:
        pin=item.get(name)
        if not isinstance(pin,dict) or w.file_digest(root,pin.get('path',''))!=pin:
            _fail('exact owner return source changed')
        pins[name]=pin
    snapshot=w.read_json(w.snapshot_path(root,item['original_coordination_task_id']))
    goal=goal_delivery(root,snapshot=snapshot);registry=w.department_registry(root)
    assistant=item.get('responsible_assistant');sender=identity['sender_department']
    if (not goal or goal['responsible_assistant']!=assistant or sender not in goal['producer_departments']
            or registry.get(assistant,{}).get('coordination_authority',{}).get('routine_decisions') is not True):
        _fail('original independent assistant responsibility required for owner return')
    box=w.read_json(w.safe_path(root,pins['outbox']['path']));reply=box.get('chat_reply',{})
    w.validate_outbox(root,[pins['outbox']],sender,identity['task_id'])
    if pins['outbox']['sha256']!=identity['result_sha256'] or box.get('candidate_version')!=identity['candidate_version']:
        _fail('owner return exact result bytes differ')
    source=w.read_json(w.safe_path(root,pins['actual_reply']['path']));records=source.get('records',[])
    if len(records)!=1:_fail('one actual old frozen result source required')
    record=records[0];original=record['original_row']['payload']
    body=''.join(c.get('text','') for c in original.get('content',[]))
    fixed=registry[sender]['chat_binding']
    if (original.get('role')!='assistant' or original.get('id')!=reply.get('message_id')
            or original.get('phase')!=reply.get('phase') or record.get('source_turn_id')!=reply.get('turn_id')
            or source.get('source_thread_id')!=fixed['task_id'] or reply.get('thread_id')!=fixed['task_id']
            or body!=reply.get('body_utf8') or hashlib.sha256(body.encode()).hexdigest()!=reply.get('body_sha256')):
        _fail('owner return must bind original fixed turn/message/UTF8, not a fabricated completion')
    owner=w.read_json(w.safe_path(root,pins['actual_owner_command']['path']));owner_rows=owner.get('records',[])
    if len(owner_rows)!=1 or owner.get('source_thread_id')!=fixed['task_id'] or owner_rows[0]['original_row']['payload'].get('role')!='user':
        _fail('actual original human owner source required')
    queued=[row for row in w._result_handoff_rows(root,identity['task_id']) if row.get('event')=='notification_queued'
            and exact_identity(row)==identity and row.get('outbox')==pins['outbox']]
    if len(queued)!=1 or queued[0].get('record_id')!=item['original_queue_record_id']:
        _fail('original immutable owner queue required; no new history manufactured')
    return {'identity':identity,'outbox':pins['outbox'],'responsible_assistant':assistant,
            'source_mode':'original_paid16','source_kind':'admitted_original_owner_return',
            'original_coordination_task_id':item['original_coordination_task_id'],
            'execution_rights_granted':False,'original_reply':{
                'source_thread_id':fixed['task_id'],'source_turn_id':reply['turn_id'],
                'source_message_id':reply['message_id'],'source_reply_sha256':reply['body_sha256'],
                'reply_observed_at':record['source_timestamp'],'source_phase':reply['phase']}}


def original_paid16_source(root, identity):
    """Admit only sixteen frozen original Paid results to their existing A3 owner.

    This reads the actual old queue and original human/A3 task evidence. It does
    not migrate the closed Paid workflow, infer a new goal, or accept later
    results merely because they share its task ID.
    """
    identity = exact_identity(identity)
    supplement=supplemental_owner_return_source(root,identity)
    if supplement is not None:return supplement
    if (identity['task_id'] != ORIGINAL_PAID16_TASK
            or identity['sender_department'] != 'paid-growth-data'):
        return None
    w = _w(); root = Path(root).resolve()
    index_pin = w.file_digest(root, ORIGINAL_PAID16_INDEX)
    if (index_pin['sha256'] != ORIGINAL_PAID16_INDEX_SHA256
            or index_pin['size'] != 21269):
        _fail('frozen original Paid16 mapping changed')
    index = w.read_json(w.safe_path(root, ORIGINAL_PAID16_INDEX))
    if (index.get('original_task_id') != ORIGINAL_PAID16_COORDINATION_TASK
            or index.get('scope') != ORIGINAL_PAID16_SCOPE
            or index.get('original_system_repair_task_id') != 'fc-20261011-goal-publication-notice-followthrough-repair-v1'):
        _fail('original Paid16 coordination task/scope mapping changed')
    cases = index.get('case1_original_paid_identity_admission')
    if (not isinstance(cases, list) or len(cases) != 16
            or len({_key(row.get('identity', {})) for row in cases}) != 16):
        _fail('one intact sixteen-result original Paid identity set required')
    matches = [row for row in cases if row.get('identity') == identity]
    if not matches:
        return None
    case = matches[0]
    if (case.get('received_or_decision_written_this_run') is not False
            or case.get('current_route', {}).get('lane') != 'legacy_unmapped'
            or case.get('outbox', {}).get('sha256') != identity['result_sha256']):
        _fail('original Paid result must retain its actual historical admission state')
    source_pins = index.get('original_business_reused_pins')
    if not isinstance(source_pins, list) or len(source_pins) < 9:
        _fail('frozen original business evidence set required')
    for pin in source_pins:
        if w.file_digest(root, pin.get('path', '')) != pin:
            _fail('original Paid16 human authority or independent readback changed')
    authority_pin = next((pin for pin in source_pins if pin.get('path') ==
        'logs/handoffs/2026-10-10-goal-delivery-assistant-runtime-v1/developer/human-authority.json'), None)
    reviewed_pin = next((pin for pin in source_pins if pin.get('path', '').endswith(
        '/paid16-current-V2-evidence-and-exact-admission-readback.json')), None)
    native_pin = next((pin for pin in source_pins if pin.get('path', '').endswith(
        '/paid16-original-native-reply-hash-readback.json')), None)
    if authority_pin is None or reviewed_pin is None or native_pin is None:
        _fail('original human authority and independent native result source pins required')
    authority = w.read_json(w.safe_path(root, authority_pin['path']))
    if (authority.get('source_thread_id') != 'example-native-0d0689f4e3a4c895'
            or authority.get('message', {}).get('type') != 'userMessage'
            or authority.get('message', {}).get('id') != 'example-native-9cd231a5daaebe45'):
        _fail('original Paid16 native human authority mismatch')
    coordination = w.read_json(w.snapshot_path(root, ORIGINAL_PAID16_COORDINATION_TASK))
    goal = coordination.get('goal_delivery', {})
    registry = w.department_registry(root)
    assistant = goal.get('responsible_assistant')
    paid_binding = registry.get('paid-growth-data', {}).get('chat_binding', {})
    assistant_binding = registry.get(assistant, {}).get('chat_binding', {})
    assistant_authority = registry.get(assistant, {}).get('coordination_authority', {})
    if (coordination.get('task_id') != ORIGINAL_PAID16_COORDINATION_TASK
            or not coordination.get('current_state')
            or coordination['current_state'] in w.TERMINAL_STATES
            or assistant != 'operations-assistant-3'
            or goal.get('parent_task_id') != 'fc-20261010-goal-delivery-assistant-runtime-v1'
            or goal.get('authorization_pin') != authority_pin
            or goal.get('human_authorization', {}).get('message_id') != authority['message']['id']
            or goal.get('human_authorization', {}).get('source_thread_id') != authority['source_thread_id']
            or goal.get('human_authorization', {}).get('scope') != ORIGINAL_PAID16_SCOPE
            or goal.get('human_authorization', {}).get('executor') != 'paid-growth-data'
            or goal.get('human_authorization', {}).get('evidence_path') != authority_pin['path']
            or goal.get('authorized_scope') != [ORIGINAL_PAID16_SCOPE]
            or goal.get('primary_owner') != 'paid-growth-data'
            or 'paid-growth-data' not in goal.get('producer_departments', [])
            or goal.get('acceptance_capability') != 'paid'
            or assistant_authority.get('routine_decisions') is not True
            or 'paid' not in assistant_authority.get('review_capabilities', [])
            or registry.get(assistant, {}).get('new_dispatch_enabled') is False
            or not assistant_binding.get('task_id') or not paid_binding.get('task_id')
            or assistant_binding.get('project_id') != paid_binding.get('project_id')
            or assistant_binding.get('cwd') != paid_binding.get('cwd')
            or assistant_binding.get('host_id') != paid_binding.get('host_id')):
        _fail('original A3 Paid responsibility, capability or fixed project binding changed')
    old = w.read_json(w.snapshot_path(root, ORIGINAL_PAID16_TASK))
    if (old.get('task_id') != ORIGINAL_PAID16_TASK
            or old.get('current_state') != 'closed' or old.get('goal_delivery') is not None
            or not any(row.get('department') == 'paid-growth-data' for row in old.get('departments', []))):
        _fail('original Paid legacy task state or producer changed')
    outbox_pin = case['outbox']
    if w.file_digest(root, outbox_pin['path']) != outbox_pin:
        _fail('original Paid result outbox bytes changed')
    box = w.read_json(w.safe_path(root, outbox_pin['path']))
    if (box.get('task_id') != ORIGINAL_PAID16_TASK
            or box.get('department') != 'paid-growth-data'
            or box.get('candidate_version') != identity['candidate_version']
            or box.get('fixed_chat_task_id', box.get('chat_task_id')) != paid_binding['task_id']
            or box.get('chat_reply', {}).get('nonempty') is not True
            or box.get('chat_reply', {}).get('in_current_fixed_department_chat') is not True):
        _fail('original Paid fixed-chat V2 result mismatch')
    reviewed = w.read_json(w.safe_path(root, reviewed_pin['path']))
    reviewed_rows = [row for row in reviewed.get('original_queued_results', [])
                     if row.get('identity') == identity]
    native = w.read_json(w.safe_path(root, native_pin['path']))
    native_rows = [row for row in native.get('records', []) if row.get('identity') == identity]
    reply = box['chat_reply']
    observed_at = reply.get('observed_at') or native.get('observed_at')
    if (len(reviewed_rows) != 1 or reviewed_rows[0].get('outbox') != outbox_pin
            or reviewed_rows[0].get('V2_validation') != 'PASS'
            or len(native_rows) != 1 or native_rows[0].get('exact_UTF8_hash_match') is not True
            or reply.get('thread_id') != paid_binding['task_id']
            or w._parse_observed_at(observed_at) is None
            or not re.fullmatch(r'[0-9a-f]{64}', str(reply.get('body_sha256') or ''))
            or native_rows[0].get('turn_id') != reply.get('turn_id')
            or native_rows[0].get('message_id') != reply.get('message_id')
            or native_rows[0].get('phase') != reply.get('phase')
            or native_rows[0].get('reply_sha256') != reply.get('body_sha256')
            or reviewed_rows[0].get('source_reply_locator', {}).get('thread_id') != paid_binding['task_id']):
        _fail('original A3 reviewed V2 and actual native Paid reply do not bind this identity')
    rows = w._result_handoff_rows(root, ORIGINAL_PAID16_TASK)
    queued = [row for row in rows if row.get('event') == 'notification_queued'
              and w._result_identity(row) == tuple(identity[key] for key in IDENTITY_FIELDS[1:])]
    if (len(queued) != 1 or queued[0].get('outbox') != outbox_pin
            or queued[0].get('source_mode') is not None
            or queued[0].get('target_department') != 'operations'
            or w._parse_observed_at(queued[0].get('created_at')) is None):
        _fail('one exact original Paid native legacy queue required')
    return {'identity': identity, 'outbox': outbox_pin,
            'responsible_assistant': assistant, 'source_mode': 'original_paid16',
            'original_coordination_task_id': ORIGINAL_PAID16_COORDINATION_TASK,
            'authority': authority_pin, 'frozen_mapping': index_pin,
            'original_reply': {'source_thread_id': paid_binding['task_id'],
                'source_turn_id': reply['turn_id'], 'source_message_id': reply['message_id'],
                'source_reply_sha256': reply['body_sha256'],
                'reply_observed_at': observed_at, 'source_phase': reply['phase'],
                'reply_observation_source': 'original_outbox' if reply.get('observed_at')
                                             else 'frozen_A3_native_readback'}}


def _validate_queued(root, identity):
    from department_autonomy import autonomous_result_route,queued_source,MODE
    route=autonomous_result_route(root,identity)
    if route is not None and route.get('source_mode')==MODE:
        return queued_source(root,identity)
    """Claim one exact native queue or strict declared collaboration return."""
    w = _w()
    registry = w.department_registry(root)
    sender = identity["sender_department"]
    collaboration = _collaboration_source(root, identity)
    if collaboration is not None:
        return collaboration
    if sender not in registry:
        _fail("registered result sender required")
    if sender == "operations":
        from native_control_result import context, matches
        snapshot=w.read_json(w.snapshot_path(root,identity['task_id']))
        if matches(snapshot):context(root,snapshot)
        else:
            from goal_delivery_runtime import enabled, owner_direct
            if (not enabled(root,snapshot) or not owner_direct(root,snapshot,sender)
                    or snapshot.get('goal_delivery',{}).get('completion_kind')!='internal_delivery'
                    or snapshot['goal_delivery'].get('required_execution_actions')):
                _fail('OPS result requires exact owner-direct internal goal or native control task')
    rows = w._result_handoff_rows(root, identity["task_id"])
    current = [row for row in rows if w._result_identity(row) ==
               (sender, identity["candidate_version"], identity["result_sha256"])]
    queued = [row for row in current if row.get("event") == "notification_queued"]
    if len(queued) != 1:
        _fail("claim requires one existing exact native queued result")
    pin = queued[0].get("outbox")
    if not isinstance(pin, dict) or w.file_digest(root, str(pin.get("path") or "")) != pin:
        _fail("queued frozen outbox bytes changed")
    w.validate_outbox(root, [pin], sender, identity["task_id"])
    box = w.read_json(w.safe_path(root, pin["path"]))
    from department_rotation import result_binding
    fixed = result_binding(root, identity, pin).get("task_id")
    from department_rotation import continued_result_source
    continued = (continued_result_source(root, {**identity, 'event': 'controller_received'}, fixed)
                 if queued[0].get('original_rotation_continuation') else None)
    original = (continued or {}).get('original_rotation_continuation')
    chat = box.get("fixed_chat_task_id", box.get("chat_task_id"))
    if (box.get("task_id") != identity["task_id"] or box.get("department") != sender
            or box.get("candidate_version") != identity["candidate_version"]
            or not fixed or (chat != fixed and (not original or chat not in {None, "", original["original_thread_id"]}))):
        _fail("queued outbox original task/version/registered chat mismatch")
    if pin["sha256"] != identity["result_sha256"]:
        _fail("queued result hash mismatch")
    if sender == "operations":
        from native_control_result import completion, matches
        if matches(snapshot):completion(root,queued[0],fixed)
    return box


def _role(root, role, owner, identity=None):
    original_target = (result_lane(root, identity).get('target_department')
                       if identity and goal_delivery(root, identity['task_id']) is None else None)
    if role not in coordinator_roles(root, task_id=identity["task_id"] if identity else None) and role != original_target:
        _fail("registered coordinator role required")
    if not isinstance(owner, str) or not owner.strip() or len(owner) > 200:
        _fail("nonempty coordinator owner audit metadata required")


class CoordinationStore:
    """One connection per caller; all public mutations use shared flock."""

    def __init__(self, root, clock=None):
        self.root = Path(root).resolve()
        self.clock = clock or (lambda: dt.datetime.now(dt.timezone.utc))
        path = _w().safe_path(self.root, str(DATABASE))
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path), isolation_level=None, timeout=15)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript("""
          CREATE TABLE IF NOT EXISTS claims (
            result_key TEXT PRIMARY KEY, identity_json TEXT NOT NULL,
            role TEXT NOT NULL, owner TEXT NOT NULL, token TEXT NOT NULL,
            fence INTEGER NOT NULL, expires REAL NOT NULL, request_id TEXT NOT NULL,
            precheck_json TEXT
          );
          CREATE TABLE IF NOT EXISTS reservations (
            result_key TEXT NOT NULL, effect_key TEXT NOT NULL, payload_json TEXT NOT NULL,
            status TEXT NOT NULL, native_record_json TEXT,
            PRIMARY KEY(result_key,effect_key)
          );
          CREATE TABLE IF NOT EXISTS coordination_audit (
            seq INTEGER PRIMARY KEY AUTOINCREMENT, payload_json TEXT NOT NULL,
            previous_hash TEXT NOT NULL, record_hash TEXT NOT NULL
          );
        """)

    def close(self):
        self.conn.close()

    def _now(self):
        value = self.clock()
        if value.tzinfo is None:
            _fail("timezone-aware coordination clock required")
        return value.timestamp()

    def _audit(self, identity, event, details):
        previous = self.conn.execute("SELECT record_hash FROM coordination_audit ORDER BY seq DESC LIMIT 1").fetchone()
        prior = previous[0] if previous else ""
        payload = {"identity": identity, "event": event, "details": details, "at": self._now()}
        self.conn.execute("INSERT INTO coordination_audit(payload_json,previous_hash,record_hash) VALUES(?,?,?)",
                          (_canonical(payload), prior, _sha([prior, payload])))

    def _begin(self):
        self.conn.execute("BEGIN IMMEDIATE")
        previous = ""
        try:
            for row in self.conn.execute("SELECT * FROM coordination_audit ORDER BY seq"):
                payload = json.loads(row["payload_json"])
                if row["previous_hash"] != previous or row["record_hash"] != _sha([previous, payload]):
                    _fail("coordination audit changed; explicit reconciliation required")
                previous = row["record_hash"]
        except BaseException:
            self.conn.rollback()
            raise

    def _row(self, identity):
        return self.conn.execute("SELECT * FROM claims WHERE result_key=?", (_key(identity),)).fetchone()

    @staticmethod
    def _view(row, duplicate=False):
        if row is None:
            return {"claimed": False, "external_permission_issued": False}
        return {name: row[name] for name in ("result_key", "role", "owner", "token", "fence", "expires")} | {
            "claimed": bool(row["owner"]), "duplicate": duplicate, "external_permission_issued": False,
            "actor_metadata_is_authentication": False,
            "precheck": json.loads(row["precheck_json"]) if row["precheck_json"] else None}

    def _lease(self, identity, role, owner, claim):
        _role(self.root, role, owner, identity)
        row = self._row(identity)
        if (not isinstance(claim, dict) or not row or row["role"] != role or row["owner"] != owner
                or claim.get("result_key") != _key(identity) or claim.get("token") != row["token"]
                or type(claim.get("fence")) is not int or claim["fence"] != row["fence"]
                or row["expires"] <= self._now()):
            _fail("stale, expired or foreign coordination claim")
        return row

    def readback(self, identity):
        identity = exact_identity(identity)
        with coordination_lock(self.root):
            _validate_queued(self.root, identity)
            self._begin()
            try:
                result = self._view(self._row(identity))
                self.conn.commit()
                return result
            except BaseException:
                self.conn.rollback()
                raise

    def claim(self, identity, role, owner, request_id, ttl_seconds=900, recovery_reason=""):
        identity = exact_identity(identity)
        _role(self.root, role, owner, identity)
        if type(ttl_seconds) is not int or not 1 <= ttl_seconds <= 900 or not str(request_id).strip():
            _fail("claim request id and TTL 1..900 seconds required")
        with coordination_lock(self.root):
            _goal_actor(self.root, identity, role)
            _validate_queued(self.root, identity)
            self._begin()
            try:
                old = self._row(identity)
                if old and old["owner"] and old["expires"] > self._now():
                    if (old["owner"], old["role"], old["request_id"]) == (owner, role, request_id):
                        self.conn.commit()
                        return self._view(old, True)
                    _fail("result already claimed; explicit release/transfer required")
                if old and old["owner"] and not recovery_reason.strip():
                    _fail("expired/interrupted claim requires explicit recovery reason")
                fence = old["fence"] + 1 if old else 1
                self.conn.execute("""INSERT INTO claims VALUES(?,?,?,?,?,?,?,?,NULL)
                  ON CONFLICT(result_key) DO UPDATE SET role=excluded.role,owner=excluded.owner,
                  token=excluded.token,fence=excluded.fence,expires=excluded.expires,
                  request_id=excluded.request_id,precheck_json=NULL""",
                  (_key(identity), _canonical(identity), role, owner, uuid.uuid4().hex,
                   fence, self._now() + ttl_seconds, request_id))
                self._audit(identity, "recover_expired" if old and old["owner"] else "claim",
                            {"role": role, "owner": owner, "fence": fence, "reason": recovery_reason})
                result = self._view(self._row(identity))
                self.conn.commit()
                return result
            except BaseException:
                self.conn.rollback()
                raise

    def recover(self, identity, role, owner, request_id, reason, ttl_seconds=900):
        if not isinstance(reason, str) or not reason.strip():
            _fail("explicit interruption recovery reason required")
        return self.claim(identity, role, owner, request_id, ttl_seconds, reason)

    def _change(self, identity, role, owner, claim, event, mutate, after_commit=None,
                lock_workflow=False):
        identity = exact_identity(identity)
        with coordination_lock(self.root), (_w().workflow_lock(self.root) if lock_workflow else nullcontext()):
            box = _validate_queued(self.root, identity)
            self._begin()
            try:
                row = self._lease(identity, role, owner, claim)
                details = mutate(row, box)
                self._audit(identity, event, details)
                result = self._view(self._row(identity))
                self.conn.commit()
                if after_commit is not None:
                    result.update(after_commit(result))
                return result
            except BaseException:
                self.conn.rollback()
                raise

    def renew(self, identity, role, owner, claim, ttl_seconds=900):
        if type(ttl_seconds) is not int or not 1 <= ttl_seconds <= 900:
            _fail("lease TTL must be 1..900 seconds")
        def mutate(row, box):
            self.conn.execute("UPDATE claims SET expires=? WHERE result_key=?", (self._now()+ttl_seconds, row["result_key"]))
            return {"fence": row["fence"], "ttl_seconds": ttl_seconds}
        return self._change(identity, role, owner, claim, "renew", mutate)

    def release(self, identity, role, owner, claim, reason):
        if not isinstance(reason, str) or not reason.strip():
            _fail("release reason required")
        def mutate(row, box):
            self.conn.execute("UPDATE claims SET role='',owner='',token='',expires=0,fence=fence+1 WHERE result_key=?", (row["result_key"],))
            return {"previous_owner": owner, "reason": reason}
        return self._change(identity, role, owner, claim, "release", mutate)

    def transfer(self, identity, role, owner, claim, target_role, target_owner, request_id, ttl_seconds=900,
                 review_plan_path=""):
        identity = exact_identity(identity)
        if original_paid16_source(self.root, identity) is not None:
            _fail('original Paid16 has one fixed A3 owner; no legacy assignment transfer')
        _role(self.root, target_role, target_owner, identity)
        if type(ttl_seconds) is not int or not 1 <= ttl_seconds <= 900 or not str(request_id).strip():
            _fail("transfer request id and TTL 1..900 seconds required")
        assignment = {}
        def mutate(row, box):
            if not row["precheck_json"]:
                _fail("precheck and unfinished scope required before explicit transfer")
            goal = _goal_actor(self.root, identity, role)
            if goal is not None:
                _goal_actor(self.root, identity, target_role, assigned=False)
                capability = goal.get("acceptance_capability")
                from technical_review_backup import review_capable
                if (target_role == "operations" or not review_capable(self.root, target_role, goal,
                            task_id=identity["task_id"], transfer_from=goal["responsible_assistant"])
                        or (role != "operations" and not review_capable(self.root, role, goal, task_id=identity["task_id"]))
                        or (role == "operations" and target_role != goal.get("responsible_assistant"))):
                    _fail("explicit transfer requires the same task review capability")
                assignment.update(previous_assistant=goal["responsible_assistant"], target_assistant=target_role,
                                  result_identity=identity, fence=row["fence"] + 1, snapshot_binding_required=True)
                from qa_review_plan import _binding, transfer_plan
                snapshot = _w().read_json(_w().snapshot_path(self.root, identity["task_id"]))
                if _binding(self.root, snapshot) is not None and target_role != goal["responsible_assistant"]:
                    if not isinstance(review_plan_path, str) or not review_plan_path.strip():
                        _fail("new frozen review plan required before assignment transfer")
                    assignment["review_plan_transfer"] = transfer_plan(self.root, task_id=identity["task_id"],
                        plan_path=review_plan_path, target_role=target_role, prepare_only=True)
                from goal_delivery_runtime import prepare_assignment_transfer
                prepare_assignment_transfer(self.root, identity, assignment)
            self.conn.execute("UPDATE claims SET role=?,owner=?,token=?,fence=fence+1,expires=?,request_id=? WHERE result_key=?",
                              (target_role, target_owner, uuid.uuid4().hex, self._now()+ttl_seconds, request_id, row["result_key"]))
            return {"previous_owner": owner, "previous_role": role, "target_role": target_role,
                    "target_owner": target_owner, "acceptance_capability": goal.get("acceptance_capability") if goal else None,
                    "assignment_change": assignment or None}
        def after_commit(result):
            if not assignment:
                return {}
            from goal_delivery_runtime import record_assignment_transfer
            applied = record_assignment_transfer(self.root, identity, assignment, _workflow_locked=True)
            return {"responsible_assistant": target_role, "assignment_change": assignment,
                    "assignment_receipt": applied}
        return self._change(identity, role, owner, claim, "transfer", mutate, after_commit,
                            lock_workflow=True)

    def precheck(self, identity, role, owner, claim, status, next_owner, next_action, unblock_condition, scope=""):
        if status not in REPORT_STATES or any(not isinstance(value, str) or not value.strip()
                                             for value in (next_owner, next_action, unblock_condition)):
            _fail("actual status, next owner/action and unblock condition required")
        def mutate(row, box):
            if scope and (not box.get("scope") or scope != box["scope"]):
                _fail("precheck scope must already exist in exact frozen outbox")
            draft = {"status": status, "next_owner": next_owner, "next_action": next_action,
                     "unblock_condition": unblock_condition, "scope": scope, "fence": row["fence"],
                     "draft_only": True, "controller_decision_recorded": False,
                     "external_permission_issued": False}
            self.conn.execute("UPDATE claims SET precheck_json=? WHERE result_key=?", (_canonical(draft), row["result_key"]))
            return draft
        return self._change(identity, role, owner, claim, "precheck_draft", mutate)


class DeliveryStore(CoordinationStore):
    """Sender lease in existing tables; never reads or mutates a review claim."""

    def _row(self, identity):
        return self.conn.execute('SELECT * FROM claims WHERE result_key=?',
                                 (_delivery_key(identity),)).fetchone()

    def _sender(self, identity, role, owner):
        original = exact_identity(identity)
        expected = delivery_identity(self.root, original, purpose=identity.get('purpose'))
        if (identity != expected or role != original['sender_department']
                or role not in _w().department_registry(self.root)
                or not isinstance(owner, str) or not owner.strip() or len(owner) > 200):
            _fail('only the exact registered result sender owns this delivery lease')

    def _lease(self, identity, role, owner, claim):
        self._sender(identity, role, owner)
        row = self._row(identity)
        if (not isinstance(claim, dict) or not row or row['role'] != role or row['owner'] != owner
                or claim.get('result_key') != _delivery_key(identity)
                or claim.get('token') != row['token'] or type(claim.get('fence')) is not int
                or claim['fence'] != row['fence'] or row['expires'] <= self._now()):
            _fail('stale, expired or foreign notification delivery lease')
        return row

    def readback(self, identity, role, owner):
        self._sender(identity, role, owner)
        with coordination_lock(self.root):
            self._begin()
            try:
                result = self._view(self._row(identity)); result.pop('token', None)
                self.conn.commit(); return result
            except BaseException:
                self.conn.rollback(); raise

    def claim(self, identity, role, owner, request_id, ttl_seconds=900, recovery_reason=''):
        self._sender(identity, role, owner)
        if type(ttl_seconds) is not int or not 1 <= ttl_seconds <= 900 or not str(request_id).strip():
            _fail('delivery request id and TTL 1..900 seconds required')
        with coordination_lock(self.root):
            _validate_queued(self.root, exact_identity(identity))
            self._begin()
            try:
                old = self._row(identity)
                if old and old['owner'] and old['expires'] > self._now():
                    if (old['role'], old['owner'], old['request_id']) != (role, owner, request_id):
                        _fail('notification already has a sender lease; explicit release/recovery required')
                    result = self._view(old, True)
                else:
                    if old and old['owner'] and not recovery_reason.strip():
                        _fail('expired delivery lease requires explicit native-effect recovery reason')
                    fence = old['fence'] + 1 if old else 1
                    self.conn.execute('''INSERT INTO claims VALUES(?,?,?,?,?,?,?,?,NULL)
                        ON CONFLICT(result_key) DO UPDATE SET role=excluded.role,owner=excluded.owner,
                        token=excluded.token,fence=excluded.fence,expires=excluded.expires,
                        request_id=excluded.request_id,precheck_json=NULL''',
                        (_delivery_key(identity), _canonical(identity), role, owner, uuid.uuid4().hex,
                         fence, self._now() + ttl_seconds, request_id))
                    self._audit(identity, 'delivery_recover' if old and old['owner'] else 'delivery_claim',
                                {'sender': role, 'owner': owner, 'fence': fence, 'reason': recovery_reason})
                    result = self._view(self._row(identity))
                self.conn.commit()
                return {**result, 'claim_kind': 'notification_delivery'}
            except BaseException:
                self.conn.rollback(); raise

    def renew(self, identity, role, owner, claim, ttl_seconds=900):
        if type(ttl_seconds) is not int or not 1 <= ttl_seconds <= 900:
            _fail('delivery lease TTL must be 1..900 seconds')
        with coordination_lock(self.root):
            self._begin()
            try:
                row = self._lease(identity, role, owner, claim)
                self.conn.execute('UPDATE claims SET expires=? WHERE result_key=?',
                                  (self._now() + ttl_seconds, row['result_key']))
                self._audit(identity, 'delivery_renew', {'fence': row['fence'], 'ttl_seconds': ttl_seconds})
                result = self._view(self._row(identity)); self.conn.commit(); return result
            except BaseException:
                self.conn.rollback(); raise

    def release(self, identity, role, owner, claim, reason):
        if not isinstance(reason, str) or not reason.strip():
            _fail('explicit delivery lease release reason required')
        with coordination_lock(self.root):
            self._begin()
            try:
                row = self._lease(identity, role, owner, claim)
                self.conn.execute("UPDATE claims SET role='',owner='',token='',expires=0,fence=fence+1 WHERE result_key=?",
                                  (row['result_key'],))
                self._audit(identity, 'delivery_release', {'previous_owner': owner, 'reason': reason})
                result = self._view(self._row(identity)); self.conn.commit(); return result
            except BaseException:
                self.conn.rollback(); raise


def _payload(root, request):
    """Freeze all request semantics plus exact bytes used by native append."""
    w = _w()
    raw = {key: value for key, value in request.items() if key not in COORDINATOR_FIELDS}
    paths = raw.get("evidence_paths") or []
    if not isinstance(paths, list):
        _fail("native evidence_paths must be an array")
    pins = {"outbox": w.file_digest(root, str(raw.get("outbox_path") or "")),
            "evidence": [w.file_digest(root, str(path)) for path in paths]}
    if raw.get("linked_outbox_path"):
        pins["linked_outbox"] = w.file_digest(root, raw["linked_outbox_path"])
    return {"request": raw, "pins": pins}


def _queued_source_pin_equivalence(root, payload, row, rows):
    """Compare only equivalent copies of an already frozen READY queue source.

    No reservation, native receipt, source pin or time is rewritten. The normal
    recovery lease/role checks remain outside this pure readback projection.
    """
    w = _w()
    request, pins = payload['request'], payload['pins']
    if (request.get('event') != 'controller_received'
            or request.get('intake_mode') != 'queue'
            or request.get('result_source_phase') != 'delivery_ready'
            or row.get('event') != 'controller_received' or row.get('intake_mode') != 'queue'
            or row.get('result_source_phase') != 'delivery_ready'):
        _fail('source alias recovery requires an original frozen READY queue intake')
    identity = exact_identity(request)
    same = [item for item in rows if all(item.get(k) == v for k, v in identity.items())]
    queues = [item for item in same if item.get('event') == 'notification_queued']
    received = [item for item in same if item.get('event') == 'controller_received']
    if (len(queues) != 1 or len(received) != 1 or received[0] != row
            or rows.index(queues[0]) >= rows.index(row)):
        _fail('one original preceding queue and one exact native intake required')
    queued = queues[0]
    if (queued.get('source_mode') not in {'owner_direct', 'approved_dispatch'}
            or queued.get('result_source_phase') != 'delivery_ready'
            or queued.get('batch_delivery_frozen') is not True
            or row.get('batch_delivery_frozen') is not True
            or queued.get('outbox') != pins['outbox'] or row.get('outbox') != pins['outbox']
            or w.file_digest(root, pins['outbox'].get('path', '')) != pins['outbox']):
        _fail('unchanged original frozen queue and outbox required')
    box = w.read_json(w.safe_path(root, pins['outbox']['path']))
    target = row.get('responsible_assistant')
    if (not isinstance(target, str) or row.get('coordinator_role') != target
            or box.get('handoff', {}).get('receiver') != target
            or box.get('task_id') != identity['task_id']
            or box.get('department') != identity['sender_department']
            or box.get('candidate_version') != identity['candidate_version']
            or pins['outbox']['sha256'] != identity['result_sha256']):
        _fail('exact original producer, receiver, task and result required')
    for key in ('source_thread_id', 'source_turn_id', 'source_message_id', 'source_reply_sha256'):
        if not queued.get(key) or queued[key] != row.get(key) or request.get(key) != row.get(key):
            _fail('source alias cannot change the original thread, turn, message or bytes')
    stamps = [w._parse_observed_at(value) for value in
              (queued.get('reply_observed_at'), queued.get('created_at'),
               row.get('reply_observed_at'), row.get('created_at'))]
    if (any(value is None for value in stamps) or stamps != sorted(stamps)
            or stamps[-1] > dt.datetime.now(dt.timezone.utc)
            or row.get('source_completion_observed_at') != queued.get('reply_observed_at')):
        _fail('original queue and actual intake chronology required')
    from goal_delivery_runtime import _collaboration_native
    projections = []
    for original in (queued, request):
        native = _collaboration_native(root, original.get('actual_native_completion'))
        thread = native.get('thread', {})
        turns = [turn for turn in native.get('turns', [])
                 if turn.get('id') == queued['source_turn_id']]
        if (thread.get('id') != queued['source_thread_id']
                or thread.get('kind') != 'codex' or thread.get('hostId') != 'local'
                or len(turns) != 1 or turns[0].get('status') not in {'inProgress', 'completed'}
                or turns[0].get('error')):
            _fail('one successful original local native READY source required')
        turn = turns[0]
        messages = [item for item in turn.get('items', [])
                    if item.get('id') == queued['source_message_id']]
        if (len(messages) != 1 or messages[0].get('type') != 'agentMessage'
                or messages[0].get('phase') not in {'commentary', 'final_answer'}
                or not isinstance(messages[0].get('text'), str)
                or type(turn.get('startedAt')) not in {int, float}
                or turn['startedAt'] > stamps[0].timestamp()):
            _fail('exact actual READY message and original source time required')
        reply = original.get('visible_reply')
        if not isinstance(reply, dict) or w.file_digest(root, reply.get('path', '')) != reply:
            _fail('frozen original reply copy changed')
        raw = w.safe_path(root, reply['path']).read_bytes()
        if (raw != messages[0]['text'].encode('utf-8')
                or hashlib.sha256(raw).hexdigest() != queued['source_reply_sha256']):
            _fail('source alias must retain identical original READY UTF-8')
        declarations = [line[len('FLASHCAST_DELIVERY_READY '):] for line in
                        messages[0]['text'].splitlines() if line.startswith('FLASHCAST_DELIVERY_READY ')]
        if len(declarations) != 1:
            _fail('one original exact complete-batch READY required')
        try:
            declared = json.loads(declarations[0])
        except (TypeError, ValueError) as error:
            raise w.WorkflowError('valid original READY declaration required') from error
        if (not isinstance(declared, dict) or any(declared.get(k) != v for k, v in identity.items())
                or declared.get('batch_complete') is not True
                or declared.get('outbox_path') != pins['outbox']['path']):
            _fail('source alias cannot change the frozen READY result')
        projections.append({'thread': {k: thread.get(k) for k in
                            ('id', 'kind', 'hostId', 'title', 'cwd', 'projectId')},
                            'turn': {k: turn.get(k) for k in
                            ('id', 'status', 'error', 'startedAt', 'completedAt')},
                            'message': messages[0]})
    if projections[0] != projections[1]:
        _fail('independent source copy differs from original queued native identity')
    normalized = {key: queued.get(key) for key in ('actual_native_completion', 'visible_reply')}
    if any(row.get(key) != value for key, value in normalized.items()):
        _fail('native intake must retain original queued source pins')
    return normalized


def _native_readback(root, payload):
    w = _w()
    request, pins = payload["request"], payload["pins"]
    from readonly_work_view_cache import inventory_handoff_rows
    rows = inventory_handoff_rows(root, request["task_id"])
    matches = [row for row in rows if row.get("idempotency_key") == request.get("idempotency_key")]
    if not matches:
        return None
    if len(matches) != 1:
        _fail("native idempotency key is ambiguous")
    row = matches[0]
    expected = {key: request.get(key) for key in (*IDENTITY_FIELDS, "event", "idempotency_key")}
    expected.update(pins)
    # All native preserved request fields are compared; path inputs map to pins.
    skipped = {"evidence_paths", "outbox_path", "linked_outbox_path", *IDENTITY_FIELDS, "event", "idempotency_key"}
    # The native operations verifier converts this path input into a digest.
    # Compare the same frozen bytes, rather than a path string with a pin dict.
    if "control_applied_proof" in request and "control_applied_proof" in row:
        expected["control_applied_proof"] = w.file_digest(root, request["control_applied_proof"])
        skipped.add("control_applied_proof")
    for key, value in request.items():
        if key not in skipped and key in row:
            expected[key] = value
    defaults = {"qa_status": "NOT_VERIFIED", "execution_status": "NOT_EXECUTED",
                "public_postcheck_status": "NOT_VERIFIED"}
    event = request.get("event")
    required_fields = {
        "controller_received": ("intake_mode", "source_reply_sha256", "source_thread_id", "reply_observed_at"),
        "controller_decision": ("decision", "next_owner", "next_action"),
        "controller_followthrough": ("followthrough_status",),
        "assistant_conclusion": ("conclusion_status", "next_owner", "next_action"),
    }
    expected.update({key: str(request.get(key) or "") for key in required_fields[event]})
    if event == "controller_received":
        expected["source_reply_sha256"] = expected["source_reply_sha256"].lower()
        if request.get("intake_mode") == "fallback":
            expected["fallback_reason"] = str(request.get("fallback_reason") or "")
    if event == "controller_decision":
        expected.update({key: request.get(key) or value for key, value in defaults.items()})
        if request.get("decision") == "wait_external":
            expected["unblock_condition"] = str(request.get("unblock_condition") or "")
        if request.get("decision") == "close_scope":
            expected["acceptance_scope"] = str(request.get("acceptance_scope") or "")
    if event == "controller_followthrough":
        status = request.get("followthrough_status")
        if status in {"external_wait_registered", "blocked_with_owner"}:
            expected.update({key: str(request.get(key) or "") for key in ("next_check_at", "unblock_condition")})
        elif status in {"dispatch_sent", "execution_verified", "prior_action_verified", "inflight_result_verified", "subsequent_action_verified"}:
            expected.update({key: str(request.get(key) or "") for key in ("linked_task_id", "action_receipt_id")})
            if status in {"inflight_result_verified", "subsequent_action_verified"}:
                expected["linked_dispatch_receipt_id"] = str(request.get("linked_dispatch_receipt_id") or "")
        elif status == "dependency_resolved":
            expected["resolution_record_id"] = str(request.get("resolution_record_id") or "")
        else:
            expected["action_reference"] = str(request.get("action_reference") or "")
    if event == 'assistant_conclusion':
        expected.update(coordinator_role='operations-assistant-3',
                        responsible_assistant='operations-assistant-3',
                        acceptance_proven=False, external_permission_issued=False,
                        business_goal_closed=False)
    changed = {key for key, value in expected.items() if row.get(key) != value}
    if changed and changed <= {'actual_native_completion', 'visible_reply'}:
        expected.update(_queued_source_pin_equivalence(root, payload, row, rows))
    if any(row.get(key) != value for key, value in expected.items()):
        _fail("native readback payload/evidence differs from reserved effect")
    return row


class HandoffAdmission:
    def __init__(self, store, identity, effect, payload, replay_record=None):
        self.store, self.identity, self.effect, self.payload = store, identity, effect, payload
        self.replay_record = replay_record
        self.completed = replay_record is not None
        self.knowledge_source = None

    def complete(self, record):
        if self.store is None:
            return
        native = _native_readback(self.store.root, self.payload)
        if native is None or native.get("record_id") != record.get("record_id"):
            _fail("native append readback missing or mismatched")
        self.store._begin()
        try:
            self.store.conn.execute("UPDATE reservations SET status='committed',native_record_json=? WHERE result_key=? AND effect_key=?",
                                    (_canonical(native), _key(self.identity), self.effect))
            self.store._audit(self.identity, "effect_readback_committed", {"effect_key": self.effect, "native_record_id": native["record_id"]})
            self.store.conn.commit()
            self.completed = True
        except BaseException:
            self.store.conn.rollback()
            raise


@contextmanager
def handoff_guard(root, request):
    """Native wrapper guard. Exceptions retain uncertain intent until readback."""
    if not isinstance(request, dict) or request.get("event") not in FINAL_EVENTS:
        yield HandoffAdmission(None, None, None, None)
        return
    root = Path(root).resolve()
    role = request.get("coordinator_role", "operations")
    identity = exact_identity(request)
    route = result_lane(root, identity)
    own_conclusion = request['event'] == 'assistant_conclusion'
    if own_conclusion:
        if not is_original_a3_conclusion_identity(identity) or role != 'operations-assistant-3':
            _fail('only exact original A3 may commit its partial producer conclusion')
    elif is_original_a3_conclusion_identity(identity) and role == 'operations-assistant-3':
        _fail('original A3 producer conclusion is not self acceptance or controller intake')
    modern = (goal_delivery(root, identity["task_id"]) is not None
              or route.get('source_mode') in {'scheduled_run', 'original_paid16'})
    if route['lane'] == 'HQ_knowledge' and not own_conclusion and (role != 'operations'
            or request['event'] != 'controller_received' or request.get('intake_mode') not in {'notification','queue'}):
        _fail('HQ knowledge only; no self review or HQ second acceptance')
    knowledge=None
    if route['lane']=='HQ_knowledge' and not own_conclusion:
        if request.get('intake_mode')=='queue':
            from goal_continuity import actual_knowledge_read
            knowledge=actual_knowledge_read(root,request,hq_knowledge_source(root,identity))
        else:knowledge=hq_knowledge_source(root,identity,require_transport=True)
    if not modern and role != "operations":
        _fail("assistant precheck cannot record final controller events")
    with coordination_lock(root):
        context = _w()._VALIDATION_CONTEXT.get() if hasattr(_w(), '_VALIDATION_CONTEXT') else None
        if context is not None:
            context.recheck()
        store = CoordinationStore(root)
        try:
            row = store._row(identity)
            if modern:
                _goal_actor(root, identity, role)
                _validate_queued(root, identity)
                store._lease(identity, role, request.get("coordinator_owner"), request.get("coordination_claim"))
            if row and row["owner"]:
                _validate_queued(root, identity)
                store._lease(identity, role, request.get("coordinator_owner"), request.get("coordination_claim"))
            elif request.get("coordination_claim"):
                _fail("claim was released or does not own this exact result")
            payload = _payload(root, request)
            effect = _sha([request["event"], request.get("idempotency_key")])
            store._begin()
            reservation = store.conn.execute("SELECT * FROM reservations WHERE result_key=? AND effect_key=?", (_key(identity), effect)).fetchone()
            if reservation and json.loads(reservation["payload_json"]) != payload:
                store.conn.rollback()
                _fail("reserved effect already binds different semantic payload/evidence")
            native = _native_readback(root, payload)
            if reservation and reservation["status"] == "committed" and native is None:
                store.conn.rollback()
                _fail("committed native effect is missing; reconcile")
            if reservation and reservation["status"] == "uncertain" and native is None:
                store.conn.rollback()
                _fail("uncertain native effect absent; explicit recover_reservation required before retry")
            if not reservation:
                store.conn.execute("INSERT INTO reservations VALUES(?,?,?,'uncertain',NULL)", (_key(identity), effect, _canonical(payload)))
                store._audit(identity, "effect_reserved", {"effect_key": effect, "role": role,
                             "owner": request.get("coordinator_owner", "legacy-operations")})
            elif reservation["status"] == "retry_ready":
                store.conn.execute("UPDATE reservations SET status='uncertain' WHERE result_key=? AND effect_key=?", (_key(identity), effect))
            store.conn.commit()
            admission = HandoffAdmission(store, identity, effect, payload, native)
            admission.knowledge_source = knowledge
            if native:
                admission.complete(native)
            native_path=_w().result_handoff_path(root,identity['task_id'])
            before_bytes=native_path.read_bytes() if native_path.exists() else None
            try:
                yield admission
            except _w().WorkflowError:
                # A native validation refusal is recoverable without changing
                # legacy caller behavior, but only after exact append readback
                # proves this effect is absent. Crashes and divergent records
                # keep their uncertain reservation and require reconciliation.
                after_bytes=native_path.read_bytes() if native_path.exists() else None
                if after_bytes==before_bytes and _native_readback(root, payload) is None:
                    store._begin()
                    store.conn.execute("DELETE FROM reservations WHERE result_key=? AND effect_key=?",
                                       (_key(identity), effect))
                    store._audit(identity, "native_validation_refused_append_absent", {"effect_key": effect})
                    store.conn.commit()
                raise
        finally:
            if store.conn.in_transaction:
                store.conn.rollback()
            store.close()


def recover_reservation(root, request, reason):
    """Explicitly reconcile an uncertain append, never execute its side effect."""
    if not isinstance(reason, str) or not reason.strip() or request.get("event") not in FINAL_EVENTS:
        _fail("explicit uncertain-effect recovery reason required")
    root = Path(root).resolve()
    identity = exact_identity(request)
    role = request.get("coordinator_role", "operations")
    route = result_lane(root, identity)
    own_conclusion = request['event'] == 'assistant_conclusion'
    if own_conclusion:
        if not is_original_a3_conclusion_identity(identity) or role != 'operations-assistant-3':
            _fail('only exact original A3 may recover its partial producer conclusion')
    elif is_original_a3_conclusion_identity(identity) and role == 'operations-assistant-3':
        _fail('original A3 producer conclusion is not self acceptance or controller intake')
    modern = (goal_delivery(root, identity["task_id"]) is not None
              or route.get('source_mode') in {'scheduled_run', 'original_paid16'})
    if route['lane'] == 'HQ_knowledge' and not own_conclusion and (role != 'operations'
            or request['event'] != 'controller_received' or request.get('intake_mode') not in {'notification','queue'}):
        _fail('HQ knowledge only; no self review or HQ second acceptance')
    if route['lane'] == 'HQ_knowledge' and not own_conclusion:
        if request.get('intake_mode')=='queue':
            from goal_continuity import actual_knowledge_read
            actual_knowledge_read(root,request,hq_knowledge_source(root,identity))
        else:hq_knowledge_source(root, identity, require_transport=True)
    if not modern and role != "operations":
        _fail("assistant cannot recover final controller effects")
    with coordination_lock(root):
        context = _w()._VALIDATION_CONTEXT.get() if hasattr(_w(), '_VALIDATION_CONTEXT') else None
        if context is not None:
            context.recheck()
        store = CoordinationStore(root)
        try:
            row = store._row(identity)
            if modern:
                _goal_actor(root, identity, role)
                _validate_queued(root, identity)
                store._lease(identity, role, request.get("coordinator_owner"), request.get("coordination_claim"))
            if row and row["owner"]:
                _validate_queued(root, identity)
                store._lease(identity, role, request.get("coordinator_owner"), request.get("coordination_claim"))
            payload = _payload(root, request)
            effect = _sha([request["event"], request.get("idempotency_key")])
            store._begin()
            reserved = store.conn.execute("SELECT * FROM reservations WHERE result_key=? AND effect_key=?", (_key(identity), effect)).fetchone()
            if not reserved or json.loads(reserved["payload_json"]) != payload:
                _fail("exact existing reservation required for recovery")
            native = _native_readback(root, payload)
            if reserved["status"] == "committed" and native is None:
                _fail("committed native effect is missing; reconcile")
            status = "committed" if native else "retry_ready"
            store.conn.execute("UPDATE reservations SET status=?,native_record_json=? WHERE result_key=? AND effect_key=?",
                               (status, _canonical(native) if native else None, _key(identity), effect))
            store._audit(identity, "effect_recovery_readback", {"effect_key": effect, "status": status, "reason": reason})
            store.conn.commit()
            return {"status": status, "native_record": native, "side_effect_executed": False}
        finally:
            if store.conn.in_transaction:
                store.conn.rollback()
            store.close()



def result_lane(root, identity, *, source=None):
    """Read current evidence; assistant summaries never enter their own review."""
    identity = exact_identity(identity)
    from department_autonomy import autonomous_result_route
    autonomous=autonomous_result_route(root,identity)
    if autonomous is not None:return autonomous
    from direct_system_repair import context as direct_context
    takeover = direct_context(root, identity['task_id'])
    if takeover is not None:
        return {'lane': 'historical_direct_repair_input', 'target_department': 'operations',
                'source_mode': 'owner_direct_repair', 'actual_executor': 'operations',
                'original_result_preserved': True, 'acceptance_proven': False,
                'HQ_second_review_required': False, 'notification_proven': False,
                'reason': 'human_direct_execution_supersedes_old_candidate_dispatch_pipeline'}
    collaboration = _collaboration_source(root, identity)
    if collaboration is not None:
        return {'lane': 'professional_acceptance',
                'target_department': collaboration['responsible_assistant'],
                'source_mode': 'collaboration', 'acceptance_proven': False,
                'HQ_second_review_required': False}
    goal = goal_delivery(root, identity['task_id'])
    sender = identity['sender_department']
    if goal:
        assistant = goal['responsible_assistant']
        if sender == assistant:
            if is_original_a3_conclusion_identity(identity):
                _original_a3_live_goal(root, identity)
                if committed_original_a3_conclusion(root, identity) is None:
                    # The original queue may be recorded first. This preview
                    # can route a durable notice, but cannot prepare/send it.
                    return {'lane': 'HQ_knowledge', 'target_department': 'operations',
                            'source_mode': 'original_a3_partial',
                            'acceptance_proven': False, 'notification_proven': False,
                            'HQ_second_review_required': False,
                            'reason': 'exact_original_a3_conclusion_not_committed'}
            proof = hq_knowledge_source(root, identity)
            return {'lane': 'HQ_knowledge', 'target_department': 'operations',
                    'acceptance_proven': proof['acceptance_proven'],
                    'notification_proven': proof['notification_proven'],
                    'HQ_second_review_required': False,
                    'reason': 'exact_formal_assistant_conclusion',
                    'knowledge_dependency_fingerprint': proof['dependency_fingerprint']}
        if sender in goal.get('producer_departments', []):
            return {'lane': 'professional_acceptance', 'target_department': assistant,
                    'acceptance_proven': False, 'HQ_second_review_required': False}
        return {'lane': 'legacy_unmapped', 'target_department': None,
                'reason': 'sender_not_bound_to_current_goal'}
    original_paid = original_paid16_source(root, identity)
    if original_paid is not None:
        return {'lane': 'professional_acceptance',
                'target_department': original_paid['responsible_assistant'],
                'source_mode': 'original_paid16', 'acceptance_proven': False,
                'HQ_second_review_required': False,
                'original_coordination_task_id': original_paid['original_coordination_task_id']}
    rows = _w()._result_handoff_rows(root, identity['task_id'])
    queued = [r for r in rows if _w()._result_identity(r) == tuple(identity[k] for k in IDENTITY_FIELDS[1:])
              and r.get('event') == 'notification_queued']
    if not queued and isinstance(source, dict):
        # The native admission caller has already verified these source pins;
        # this preview classifies routing and never grants claim/admission.
        queued = [source]
    from department_rotation import result_binding
    routes = _w().read_json(Path(root) / 'data/task-contract.json').get('result_handoff_contract', {}).get('scheduled_daily_sources', [])
    matches = [route for route in routes if isinstance(route, dict)
               and route.get('department') == sender
               and re.fullmatch(route.get('task_id_pattern', '(?!)'), identity['task_id'])
               and len(queued) == 1 and queued[0].get('source_mode') == 'scheduled_run'
               and queued[0].get('source_automation_id') == route.get('automation_id')
               and queued[0].get('source_thread_id') == result_binding(root, identity, queued[0].get('outbox')).get('task_id')]
    if len(matches) == 1 and matches[0].get('responsible_assistant') in coordinator_roles(root):
        from goal_continuity import daily_selected_assistant
        target=daily_selected_assistant(root,identity,matches[0]['responsible_assistant'])
        return {'lane': 'professional_acceptance', 'target_department': target,
                'source_mode': 'scheduled_run', 'HQ_second_review_required': False}
    return {'lane': 'legacy_unmapped', 'target_department': None,
            'reason': 'original_evidence_mapping_required_no_redispatch'}


def _notification_path(root, identity):
    exact = delivery_identity(root, identity)
    path = _w().safe_path(root, 'logs/result-notifications/' + _delivery_key(exact).split(':', 1)[1] + '.json')
    legacy = _w().safe_path(root, 'logs/result-notifications/' + _key(identity) + '.json')
    if not path.exists() and legacy.exists():
        old = _w().read_json(legacy)
        if (old.get('route', {}).get('target_department') == exact['target_department']
                and old.get('route', {}).get('lane') == exact['purpose']):
            return legacy
    return path


# Inserted into result_coordination, not a second receipt writer.
_INTAKE_ACTOR_MEMO = {}


def _committed_intake_actor(root, record):
    """Authenticate historical handling role from the original SQL audit chain."""
    database = _w().safe_path(root, str(DATABASE))
    def version(path):
        if not path.exists():
            return None
        s = path.stat()
        return (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
    stamp = (str(database), version(database), version(Path(str(database) + '-wal')))
    if stamp not in _INTAKE_ACTOR_MEMO:
        connection = sqlite3.connect(database.as_uri() + '?mode=ro', uri=True)
        try:
            audit = connection.execute('SELECT payload_json,previous_hash,record_hash FROM coordination_audit ORDER BY seq').fetchall()
        finally:
            connection.close()
        previous = ''; actors = {}; pending = {}
        for raw, prior, digest in audit:
            event = json.loads(raw)
            if prior != previous or digest != _sha([previous, event]):
                _fail('original intake actor SQL audit chain differs')
            previous = digest
            if event.get('event') in {'effect_reserved','native_validation_refused_append_absent','effect_readback_committed'}:
                token = (_key(exact_identity(event['identity'])), event['details']['effect_key'])
                if event['event']=='effect_reserved':
                    actor=(event['details'].get('role'),event['details'].get('owner'))
                    pending.setdefault(token,set()).add(actor)
                elif event['event']=='native_validation_refused_append_absent':
                    pending.pop(token,None)
                else:
                    native_id=event['details'].get('native_record_id')
                    if native_id:
                        actors.setdefault((*token,native_id),set()).update(pending.get(token,set()))
        if stamp != (str(database), version(database), version(Path(str(database) + '-wal'))):
            _fail('intake actor SQL changed during read; retry fresh read')
        _INTAKE_ACTOR_MEMO.clear()
        _INTAKE_ACTOR_MEMO[stamp] = actors
    token = (_key(exact_identity(record)), _sha([record['event'], record['idempotency_key']]), record['record_id'])
    actors = _INTAKE_ACTOR_MEMO[stamp].get(token, set())
    if len(actors) != 1:
        _fail('one original committed intake actor required')
    return next(iter(actors))


def frozen_notification_route(root, record):
    from readonly_work_view_cache import inventory_active, memoized_view
    if inventory_active(root):
        return memoized_view(root,'historical-intake-route',
            [record.get('identity'),record.get('delivery_identity'),record.get('route')],
            lambda: _frozen_notification_route(root,record))
    return _frozen_notification_route(root,record)


def _frozen_notification_route(root, record):
    """Only a historical receipt projection; never routes a new send or claim."""
    identity = exact_identity(record.get('identity', {}))
    exact = record.get('delivery_identity')
    route = record.get('route', {})
    if (not isinstance(exact, dict) or not isinstance(route, dict)
            or any(exact.get(k) != identity[k] for k in IDENTITY_FIELDS)
            or exact.get('purpose') not in DELIVERY_PURPOSES
            or exact.get('purpose') != route.get('lane')
            or not exact.get('target_department')
            or exact.get('target_department') != route.get('target_department')
            or not isinstance(exact.get('target_thread_id'), str)
            or not exact['target_thread_id']):
        _fail('original frozen notification recipient and purpose required')
    registry=_w().department_registry(root)
    receiver=registry.get(exact['target_department'],{}).get('chat_binding',{})
    producer=registry.get(identity['sender_department'],{}).get('chat_binding',{})
    if (not receiver.get('project_id') or receiver.get('project_id')!=producer.get('project_id')
            or receiver.get('cwd')!=str(Path(root).resolve()) or producer.get('cwd')!=str(Path(root).resolve())):
        _fail('frozen intake must remain in its actual registered project')
    if receiver.get('task_id')!=exact['target_thread_id']:
        from department_rotation import _records, _id
        original=next((r for r in _records(root) if r.get('role')==exact['target_department']
            and _id(r['old_binding'])==exact['target_thread_id']
            and _id(r['new_binding'])==receiver.get('task_id')),None)
        if original is None:
            _fail('frozen original recipient is not this exact role or trusted rotation')
    return {'lane': exact['purpose'], 'target_department': exact['target_department'],
            'frozen_target_thread_id': exact['target_thread_id'],
            'historical_receipt_projection_only': True}


def _original_intake_notification(root, identity, route):
    """Find the immutable original delivery identity, without current source replay."""
    base = Path(root) / 'logs/result-notifications'
    exact = delivery_identity(root, identity, route=route)
    candidates = [base / (_delivery_key(exact).split(':', 1)[1] + '.json'), base / (_key(identity) + '.json')]
    found = []
    for path in dict.fromkeys(candidates):
        if path.is_file():
            item = _w().read_json(path)
            if item.get('identity') == identity:
                found.append(item)
    if not found:
        # Rotation may change today's fixed thread. Read old notices, never edit.
        for path in base.glob('*.json'):
            item = _w().read_json(path)
            if item.get('identity') == identity:
                found.append(item)
    if len(found) != 1:
        _fail('one original frozen intake notification required')
    return frozen_notification_route(root, found[0])


def _received_delivery(root, identity, route):
    """Consume committed original intake; later production cannot undo that fact."""
    w = _w(); identity = exact_identity(identity)
    from readonly_work_view_cache import inventory_handoff_rows
    rows = inventory_handoff_rows(root, identity['task_id'])
    exact = [r for r in rows if w._result_identity(r) == tuple(identity[k] for k in IDENTITY_FIELDS[1:])]
    matches = [r for r in exact if r.get('event') == 'controller_received']
    if len(matches) > 1:
        _fail('exact notification consumer intake is ambiguous')
    if matches:
        row = matches[0]
        queued = [r for r in exact if r.get('event') == 'notification_queued']
        if len(queued) != 1 or rows.index(queued[0]) >= rows.index(row):
            _fail('one preceding original queued intake source required')
        q = queued[0]; target = route.get('target_department')
        frozen_target = q.get('target_department') or q.get('responsible_assistant')
        if frozen_target != target:
            _fail('original queued recipient differs from intake consumer')
        original_pin = q.get('outbox')
        if (row.get('outbox') != original_pin or not isinstance(original_pin, dict)
                or original_pin.get('sha256') != identity['result_sha256']
                or w.file_digest(root, original_pin.get('path', '')) != original_pin):
            _fail('original exact intake/outbox bytes differ')
        box = w.read_json(w.safe_path(root, original_pin['path']))
        if (box.get('task_id') != identity['task_id'] or box.get('department') != identity['sender_department']
                or box.get('candidate_version') != identity['candidate_version']):
            _fail('original intake candidate version differs')
        # Always fresh SQL/native readback; the role alias alone proves nothing.
        _committed_result(root, row)
        role = row.get('coordinator_role')
        if role is None:
            actor, owner = _committed_intake_actor(root, row)
            if row.get('responsible_assistant') != target:
                _fail('legacy intake requires its original responsible assistant')
            frozen = route if route.get('frozen_target_thread_id') else _original_intake_notification(root, identity, route)
            fixed_thread = frozen.get('frozen_target_thread_id')
            owner_thread = owner.split(':',1)[0] if isinstance(owner,str) else None
            same_thread = bool(fixed_thread and owner_thread==fixed_thread)
            if not same_thread and actor==target and owner_thread and fixed_thread:
                from department_rotation import _records, _id
                mapping=next((r for r in _records(root) if r.get('role')==target
                    and _id(r['old_binding'])==fixed_thread and _id(r['new_binding'])==owner_thread),None)
                same_thread=bool(mapping and mapping['old_binding'].get('cwd')==str(Path(root).resolve())
                                 and mapping['new_binding'].get('cwd')==str(Path(root).resolve()))
            if actor != target or not same_thread:
                _fail('legacy committed intake fixed recipient differs')
            if row.get('coordinator_owner') and row['coordinator_owner'] != owner:
                _fail('native intake owner differs from original SQL reservation')
            role = row['responsible_assistant']
        if role != target:
            _fail('actual committed intake role differs from frozen recipient')
        return row
    if identity == ORIGINAL_A3_CONCLUSION and route.get('target_department') == 'operations':
        from direct_system_repair import received_original_knowledge
        return received_original_knowledge(root, identity)
    return None


def received_notification(root, record):
    """A verified receipt can resolve a notice without current goal revalidation."""
    identity = exact_identity(record.get('identity', {}))
    from readonly_work_view_cache import inventory_handoff_rows
    rows = inventory_handoff_rows(root,identity['task_id'])
    if not any(r.get('event')=='controller_received' and exact_identity(r)==identity for r in rows):
        return None
    route = frozen_notification_route(root, record)
    return _received_delivery(root, identity, route)


def inventory_result_lane(root, identity, notice_path):
    from readonly_work_view_cache import memoized_view
    return memoized_view(root,'dispatcher-source-error',[identity,'inventory-route'],
                         lambda: result_lane(root,identity), required=[notice_path],failures_only=True)


def _native_queue_identity(root, pin, identity, exact):
    """Queue delivery needs canonical identities, never history-derived idle."""
    w = _w()
    from department_event_dispatcher import native_queue_capability
    from goal_delivery_runtime import _collaboration_native
    native_queue_capability(root)
    if not isinstance(pin, dict) or w.file_digest(root, pin.get('path', '')) != pin:
        _fail('exact native queue identity observation required')
    observed = w.read_json(w.safe_path(root, pin['path']))
    at = w._parse_observed_at(observed.get('observed_at'))
    if (observed.get('schema') != 'official-native-queue-identities/v1'
            or at is None or not 0 <= (dt.datetime.now(dt.timezone.utc)-at).total_seconds() <= 300
            or observed.get('identity') != identity or observed.get('target_thread_id') != exact['target_thread_id']):
        _fail('fresh original result-specific queue identities required')
    registry = w.department_registry(root)
    for role in (identity['sender_department'], exact['target_department']):
        binding = registry[role]['chat_binding']
        page = _collaboration_native(root, observed.get('canonical_sources', {}).get(role))
        thread = page.get('thread', {})
        if (page.get('source_transport') != 'official_app_server_readonly_history'
                or any(thread.get(k) != binding.get(v) for k,v in
                       {'id':'task_id','title':'title','cwd':'cwd'}.items())
                or Path(binding.get('cwd','')).resolve() != Path(root).resolve()
                or thread.get('projectId') not in {None, binding.get('project_id')}
                or not page.get('turns')):
            _fail('original fixed sender/recipient queue identity differs')
    return observed


def validate_notification_delivery(root, identity):
    """Internal policy hook verifies the lease; public inventory omits its token."""
    identity = exact_identity(identity); route = result_lane(root, identity)
    if route.get('lane') == 'HQ_knowledge':
        hq_knowledge_source(root, identity)
    current = _w().read_json(_notification_path(root, identity))
    if current.get('native_queue_transport', {}).get('state') in {'sending', 'uncertain', 'accepted'}:
        _fail('official queue already owns this exact notice; recover original effect, never send twice')
    exact = delivery_identity(root, identity, route=route)
    if (current.get('state') != 'prepared' or current.get('delivery_identity') != exact
            or current.get('delivery_owner') != identity['sender_department']
            or _received_delivery(root, identity, route) or current.get('delivered')):
        _fail('one exact unresolved prepared sender notification required')
    if _w().file_digest(root, current.get('payload', {}).get('path', '')) != current.get('payload'):
        _fail('prepared sender notification payload changed')
    live_pin = current.get('live_identity', {})
    if _w().file_digest(root, live_pin.get('path', '')) != live_pin:
        _fail('prepared sender live identity changed')
    if current.get('delivery_mode') == 'official_native_queue':
        _native_queue_identity(root, live_pin, identity, exact)
    else:
        live = _w().read_json(_w().safe_path(root, live_pin['path']))
        observed = _w()._parse_observed_at(live.get('observed_at'))
        from goal_delivery_runtime import _collaboration_native
        from qa_review_plan import _review_native_containers
        _review_native_containers(live)
        native = _collaboration_native(root, live.get('actual_native_observation'))
        _review_native_containers(native)
        targets = [row for row in [*native.get('threads', []), *native.get('pinnedThreads', [])]
                   if row.get('id') == exact['target_thread_id']]
        binding = _w().department_registry(root)[exact['target_department']]['chat_binding']
        if (observed is None or not 0 <= (dt.datetime.now(dt.timezone.utc)-observed).total_seconds() <= 300
                or len(targets) != 1
                or any(targets[0].get(k) != binding.get(v) for k, v in
                       {'projectId':'project_id','title':'title','cwd':'cwd'}.items())):
            _fail('current fresh exact native idle target required before policy or send')
        from goal_source_recovery import actual_target_turn_status
        if actual_target_turn_status(root,live,targets[0],binding) != 'idle':
            _fail('current fresh exact native idle target required before policy or send')
        _review_native_containers(targets[0])
    store = DeliveryStore(root)
    try:
        store._lease(exact, identity['sender_department'], current.get('coordinator_owner'), current.get('delivery_claim'))
    finally:
        store.close()
    return {'delivery_identity': exact, 'dedupe_key': _delivery_key(exact),
            'delivery_owner': identity['sender_department'], 'state': 'prepared', 'route': route,
            'payload': current['payload'], 'claim_valid': True, 'external_permission_issued': False}


def notification_enqueue(root, identity, *, _coordination_locked=False):
    """Persist sender responsibility; a queue neither sends nor accepts a result."""
    identity = exact_identity(identity)
    source = _validate_queued(root, identity)
    if source.get('source_mode') == 'collaboration':
        _fail('formal collaboration return does not create an ordinary notification queue')
    route = result_lane(root, identity)
    if route['lane'] == 'historical_direct_repair_input':
        return {'identity': identity, 'route': route, 'state': 'superseded_execution_pipeline',
                'delivered': False, 'queue_is_delivery': False, 'native_send_executed': False,
                'actionable': False, 'delivery_owner': identity['sender_department'],
                'recovery_owner': 'operations', 'original_notification_store_unchanged': True}
    if route['lane'] == 'legacy_unmapped':
        # The old native queue is already a fact. Missing a current recipient
        # is a named mapping block, never a rollback of that fact or a target.
        return {'identity': identity, 'route': route, 'state': 'mapping_required',
                'delivery_owner': identity['sender_department'], 'recovery_owner': identity['sender_department'],
                'native_queued_source_verified': True, 'delivered': False, 'queue_is_delivery': False,
                'actionable': False, 'block_reason': route.get('reason'),
                'next_action': 'restore_exact_original_evidence_mapping',
                'native_send_executed': False, 'legacy_notification_store_unchanged': True}
    exact = delivery_identity(root, identity, route=route)
    with (nullcontext() if _coordination_locked else coordination_lock(root)):
        path = _notification_path(root, identity)
        old = _w().read_json(path)
        if old:
            if (old.get('identity') != identity
                    or any(old.get('route', {}).get(key) != route.get(key) for key in ('lane', 'target_department'))
                    or old.get('delivery_identity', exact) != exact):
                _fail('frozen notification identity/target/purpose changed')
            return old
        payload = {'schema_version': '2.0', 'identity': identity, 'delivery_identity': exact,
                   'purpose': exact['purpose'], 'route': route, 'dedupe_key': _delivery_key(exact),
                   'state': 'queued', 'delivered': False, 'delivery_owner': identity['sender_department'],
                   'recovery_owner': identity['sender_department'],
                   'defer_reason': 'fresh_actual_target_idle_or_completion_event_required',
                   'recovery_condition': 'original sender reads exact native effect/status then sends once when legally idle',
                   'native_wakeup_guaranteed': False, 'queued_at': _w().utc_timestamp(), 'attempts': []}
        _w().atomic_write_json(path, payload)
        return payload


def notification_plan(root, role=None):
    # Global route/configuration faults are never hidden as one task error.
    _w().department_registry(root)
    if not _w().read_json(Path(root) / 'data/task-contract.json'):
        _fail('current global task contract required for notification inventory')
    pending = []; received = []; errors = []; seen = set()
    for path in sorted((Path(root) / 'logs/result-notifications').glob('*.json')):
        record = {}; identity = {}
        try:
            record = _w().read_json(path)
            if not isinstance(record, dict):
                _fail('notification record must be an object')
            identity = exact_identity(record.get('identity', {}))
            queue_recovery_owned = (role == 'operations' and record.get('native_queue_transport', {}).get('state')
                                    in {'sending', 'uncertain', 'accepted'})
            if (role is not None and record.get('route', {}).get('target_department') != role
                    and identity['sender_department'] != role and not queue_recovery_owned):
                continue
            # Committed original intake is checked before mutable later sources.
            intake = received_notification(root, record)
            if intake is not None:
                frozen_route = frozen_notification_route(root, record)
                exact = record['delivery_identity']; key = _delivery_key(exact)
                if key in seen:
                    _fail('notification delivery identity appears more than once')
                seen.add(key)
                received.append({'identity': identity, 'delivery_identity': exact, 'dedupe_key': key,
                                 'resolution': 'exact_responsible_native_intake_committed',
                                 'record_id': intake['record_id'], 'native_notification_sent': record.get('delivered', False)})
                continue
            route = inventory_result_lane(root, identity, path)
            if route['lane']=='historical_read_only':
                received.append({'identity':identity,'resolution':'historical_source_preserved_no_new_assistant_wakeup','native_notification_sent':record.get('delivered',False)})
                continue
            if route['lane'] == 'historical_direct_repair_input':
                received.append({'identity': identity, 'resolution': 'superseded_execution_pipeline_not_delivery',
                                 'actual_executor': 'operations', 'native_notification_sent': False,
                                 'original_notification_store_unchanged': True})
                continue
            exact = delivery_identity(root, identity, route=route); key = _delivery_key(exact)
            if record.get('delivery_identity', exact) != exact or any(
                    record.get('route', {}).get(k) != route.get(k) for k in ('lane', 'target_department')):
                _fail('notification original recipient or purpose changed')
            if key in seen:
                pending = [row for row in pending if row.get('dedupe_key') != key]
                received = [row for row in received if row.get('dedupe_key') != key]
                _fail('notification delivery identity appears more than once')
            seen.add(key)
            intake = _received_delivery(root, identity, route)
            if intake is not None:
                received.append({'identity': identity, 'delivery_identity': exact, 'dedupe_key': key,
                                 'resolution': 'exact_responsible_native_intake_committed',
                                 'record_id': intake['record_id'], 'native_notification_sent': record.get('delivered', False)})
                continue
            if record.get('delivered'):
                continue
            _validate_queued(root, identity)
            public = {k: v for k, v in record.items() if k not in {'claim', 'delivery_claim', 'attempts'}}
            # The durable queue can predate a committed assistant conclusion;
            # expose the currently proven route without rewriting that fact.
            public['route'] = route
            public['attempts'] = [{k: v for k, v in attempt.items() if k != 'claim'}
                                  for attempt in record.get('attempts', [])]
            due = _w()._parse_observed_at(record.get('next_check_at')) if record.get('next_check_at') else None
            if record.get('next_check_at') and due is None:
                _fail('notification next check time must be an exact timestamp')
            state = record.get('state')
            native_queue = record.get('native_queue_transport', {})
            queue_owned = native_queue.get('state') in {'sending', 'uncertain', 'accepted'}
            queue_at = _w()._parse_observed_at(native_queue.get('updated_at', native_queue.get('started_at')))
            queue_recovery_due = (queue_owned and (native_queue.get('state') != 'accepted'
                or queue_at is None or (dt.datetime.now(dt.timezone.utc)-queue_at).total_seconds() >= 900))
            busy_wait = state == 'deferred' and record.get('defer_reason') == 'actual_target_busy'
            actionable = (not busy_wait and (due is None or due <= dt.datetime.now(dt.timezone.utc))
                          and (state != 'deferred' or due is not None
                               or record.get('defer_reason') == 'actual_target_busy')
                          and (route.get('lane') != 'HQ_knowledge' or route.get('notification_proven') is True))
            if queue_owned:
                actionable = queue_recovery_due
            activation = {}
            if queue_owned:
                from department_event_dispatcher import activation_recovery_view
                activation = {'activation_recovery': activation_recovery_view(root, record)}
            pending.append({**public, **activation, 'delivery_identity': exact, 'dedupe_key': key,
                            'delivery_owner': identity['sender_department'],
                            'recovery_owner': 'operations' if queue_owned else identity['sender_department'],
                            'purpose': exact['purpose'], 'actionable': actionable,
                            'waiting_for_native_completion': busy_wait,
                            'waiting_for_actual_intake': queue_owned,
                            'queue_acceptance_is_intake': False,
                            'next_action': 'read_exact_native_queue_effect_then_resume_existing_once_if_actually_idle'
                                           if queue_owned and queue_recovery_due
                                           else 'await_original_queue_intake_no_resend'
                                           if queue_owned
                                           else 'record_exact_original_assistant_conclusion'
                                           if route.get('lane') == 'HQ_knowledge' and not route.get('notification_proven')
                                           else 'read_actual_native_effect' if state == 'sending'
                                           else 'refresh_busy_target_at_next_legal_opportunity'
                                           if state == 'deferred' and record.get('defer_reason') == 'actual_target_busy'
                                           else 'read_fresh_native_target_then_prepare_exact_send'})
        except (_w().WorkflowError, ValueError, KeyError, OSError, TypeError, AttributeError) as error:
            safe_record = record if isinstance(record, dict) else {}
            safe_identity = identity if isinstance(identity, dict) and identity else safe_record.get('identity', {})
            safe_identity = safe_identity if isinstance(safe_identity, dict) else {}
            errors.append({'task_id': safe_identity.get('task_id'),
                           'identity': safe_identity, 'path': _w().rel_path(root, path),
                           'owner': safe_identity.get('sender_department'), 'block_reason': str(error),
                           'unblock_condition': 'repair this exact source/identity; preserve other valid results',
                           'next_check_at': safe_record.get('next_check_at', 'next_existing_legal_opportunity')})
    return {'notifications': pending, 'pending_count': len(pending), 'errors': errors,
            'resolved_by_actual_intake': received,
            'native_entry': 'read actual fixed target then sender notification_claim; send only if ready',
            'native_wakeup_guaranteed': False, 'queue_is_delivery': False, 'no_new_polling_or_automation': True}


def notification_claim(root, identity, role, owner, request_id, live_identity, payload, *, recovery_reason='', ttl_seconds=900,
                       delivery_mode='ordinary'):
    """Only the actual sender prepares delivery; the receiver keeps its review claim."""
    identity = exact_identity(identity); w = _w()
    route = result_lane(root, identity); exact = delivery_identity(root, identity, route=route)
    if role != identity['sender_department']:
        _fail('notification role must be its actual sender, not the accepting assistant')
    if delivery_mode not in {'ordinary', 'official_native_queue'}:
        _fail('unknown notification delivery mode')
    queued = notification_enqueue(root, identity)
    intake = _received_delivery(root, identity, route)
    if intake:
        return {'result': 'duplicate_ignored', 'resolved_by_actual_intake': True,
                'native_record_id': intake['record_id'], 'delivered': queued.get('delivered', False)}
    if queued.get('delivered'):
        return {'result': 'duplicate_ignored', 'delivered': True, 'native_transport': queued['native_transport']}
    native_queue = queued.get('native_queue_transport', {})
    if native_queue.get('state') in {'sending', 'uncertain', 'accepted'}:
        return {'result': 'native_queue_pending', 'delivered': False,
                'recovery_owner': 'department_event_dispatcher',
                'native_message_id': native_queue.get('native_message_id'),
                'notification_responsibility_retained': True, 'native_send_executed': False}
    if route['lane'] == 'HQ_knowledge' and not route.get('notification_proven') and route.get('source_mode')!='department_autonomous_delivery_v1':
        _fail('exact formal assistant conclusion required before HQ knowledge delivery')
    if (not isinstance(live_identity, dict) or w.file_digest(root, live_identity.get('path', '')) != live_identity
            or not isinstance(payload, dict) or w.file_digest(root, payload.get('path', '')) != payload):
        _fail('frozen native live identity and exact message bytes required')
    binding = w.department_registry(root).get(exact['target_department'], {}).get('chat_binding', {})
    native_queue = delivery_mode == 'official_native_queue'
    if native_queue:
        _native_queue_identity(root, live_identity, identity, exact)
    else:
        live = w.read_json(w.safe_path(root, live_identity['path']))
        observed = w._parse_observed_at(live.get('observed_at')); native_pin = live.get('actual_native_observation')
        if not isinstance(native_pin, dict) or w.file_digest(root, native_pin.get('path', '')) != native_pin:
            _fail('original actual native observation pin required')
        from goal_delivery_runtime import _collaboration_native
        from qa_review_plan import _review_native_containers
        _review_native_containers(live)
        native = _collaboration_native(root, native_pin)
        _review_native_containers(native)
        target = [row for row in [*native.get('threads', []), *native.get('pinnedThreads', [])]
                  if row.get('id') == exact['target_thread_id']]
        if (observed is None or not 0 <= (dt.datetime.now(dt.timezone.utc)-observed).total_seconds() <= 300
                or len(target) != 1 or any(target[0].get(k) != binding.get(v) for k,v in
                     {'projectId':'project_id','title':'title','cwd':'cwd'}.items())
                or ('sidebarSectionId' in target[0] and target[0]['sidebarSectionId'] != binding.get('sidebar_section_id'))):
            _fail('fresh exact actual native fixed target identity required')
        _review_native_containers(target[0])
    with coordination_lock(root):
        current = w.read_json(_notification_path(root, identity))
        if _received_delivery(root, identity, route):
            return {'result': 'duplicate_ignored', 'resolved_by_actual_intake': True, 'delivered': current.get('delivered', False)}
        if current.get('delivered'):
            return {'result': 'duplicate_ignored', 'delivered': True, 'native_transport': current['native_transport']}
        if current.get('native_queue_transport', {}).get('state') in {'sending', 'uncertain', 'accepted'}:
            return {'result': 'native_queue_pending', 'delivered': False,
                    'recovery_owner': 'department_event_dispatcher',
                    'notification_responsibility_retained': True, 'native_send_executed': False}
        if current.get('state') in {'sending', 'sent'} or current.get('call_started_at') or current.get('attempts'):
            _fail('native send effect uncertain/already sent; read its original actual effect before retry')
        if current.get('state') == 'prepared' and current.get('schema_version') != '2.0':
            _fail('legacy prepared send effect requires original native readback; no lease migration retry')
        if current.get('payload') and current['payload'] != payload:
            _fail('prepared notification exact message cannot be replaced')
        from goal_source_recovery import actual_target_turn_status
        status = 'native_queue' if native_queue else actual_target_turn_status(root,live,target[0],binding)
        if not native_queue and status != 'idle':
            known_busy = status in {'active', 'inProgress', 'running', 'busy'}
            current.update(state='deferred' if known_busy else 'unknown_target', route=route,
                           live_identity=live_identity,
                           delivery_identity=exact, delivery_owner=role, recovery_owner=role,
                           defer_reason='actual_target_busy' if known_busy else 'actual_target_effect_readback_required',
                           recovery_condition='read exact actual fixed target status/effect before any native send')
            w.atomic_write_json(_notification_path(root, identity), current)
            return {'result': 'deferred' if known_busy else 'readback_required', 'delivered': False,
                    'interrupts_active_thread': False, 'recovery_owner': role, 'target_thread_id': exact['target_thread_id']}
    store = DeliveryStore(root)
    try:
        claim = store.claim(exact, role, owner, request_id, ttl_seconds, recovery_reason)
    finally:
        store.close()
    with coordination_lock(root):
        current = w.read_json(_notification_path(root, identity))
        if _received_delivery(root, identity, route) or current.get('delivered'):
            return {'result': 'duplicate_ignored', 'delivered': current.get('delivered', False)}
        if current.get('native_queue_transport', {}).get('state') in {'sending', 'uncertain', 'accepted'}:
            return {'result': 'native_queue_pending', 'delivered': False,
                    'recovery_owner': 'department_event_dispatcher',
                    'notification_responsibility_retained': True, 'native_send_executed': False}
        if current.get('state') in {'sending', 'sent'} or current.get('call_started_at'):
            _fail('native send effect requires actual readback before retry')
        current.update(schema_version='2.0', state='prepared', route=route, delivery_identity=exact,
                       dedupe_key=_delivery_key(exact), purpose=exact['purpose'], live_identity=live_identity,
                       payload=payload, delivery_claim=claim, claim=claim, delivery_owner=role, recovery_owner=role,
                       coordinator_owner=owner, target_thread_id=exact['target_thread_id'], defer_reason='')
        if native_queue:
            current['delivery_mode'] = 'official_native_queue'
        w.atomic_write_json(_notification_path(root, identity), current)
    source = w.department_registry(root).get(role, {}).get('chat_binding', {})
    return {'result': 'ready', 'identity': identity, 'delivery_identity': exact,
            'delivery_claim': claim, 'claim': claim, 'payload': payload,
            'tool': 'mcp__codex_app__send_message_to_thread', 'threadId': exact['target_thread_id'],
            'action_id': 'notify-result-' + _delivery_key(exact).split(':', 1)[1], 'action_class': 'thread_message',
            'scope': 'department_result:' + identity['task_id'] + ':' + role,
            'department': role, 'task_id': identity['task_id'], 'source_project_id': source.get('project_id'),
            'target_department': exact['target_department'], 'target_project_id': binding.get('project_id'),
            'target_thread_id': exact['target_thread_id'], 'target_thread_title': binding.get('title'),
            'target_cwd': binding.get('cwd'), 'target_sidebar_section_id': binding.get('sidebar_section_id'),
            'payload_sha256': payload['sha256'], 'purpose': exact['purpose'],
            'delivered': False, 'requires_existing_exact_message_policy': True}


def _notification_native_page(root, source, department):
    """Read a real full native page; message bodies remain opaque UTF-8 text."""
    w = _w()
    if (not isinstance(source, dict) or set(source) != {'path', 'sha256', 'size'}
            or w.file_digest(root, source.get('path', '')) != source):
        _fail('readback_required: exact original native notification page pin required')

    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError('duplicate native notification field')
            value[key] = item
        return value

    try:
        value = json.loads(w.validation_bytes(w.safe_path(root, source['path'])),
                           object_pairs_hook=unique,
                           parse_constant=lambda value: (_ for _ in ()).throw(ValueError('finite native source required')))
        from qa_review_plan import _review_native_containers, _review_raw_native_result
        _review_native_containers(value)
        if 'content' in value:
            value = _review_raw_native_result(value)
        _review_native_containers(value)
    except (ValueError, TypeError, KeyError):
        _fail('readback_required: one successful complete original native page required')
    binding = w.department_registry(root).get(department, {}).get('chat_binding', {})
    thread = value.get('thread', {}); page = value.get('page', {}); turns = value.get('turns')
    if (value.get('schemaVersion') != 1 or not isinstance(thread, dict)
            or any(thread.get(key) != binding.get(field) for key, field in
                   {'id': 'task_id', 'title': 'title', 'cwd': 'cwd'}.items())
            or ('hostId' in thread and thread['hostId'] != 'local')
            or not isinstance(page, dict) or page.get('order') != 'newest_first'
            or not isinstance(turns, list) or any(not isinstance(turn, dict) for turn in turns)
            or type(page.get('limit')) is not int or page['limit'] < len(turns)
            or type(page.get('hasMore')) is not bool
            or (not turns and page['hasMore'])):
        _fail('readback_required: exact fixed native notification thread and complete turn page required')
    turn_ids = []; item_ids = []
    for turn in turns:
        if (not isinstance(turn.get('id'), str) or not turn['id']
                or not isinstance(turn.get('items'), list)
                or any(not isinstance(item, dict) or not isinstance(item.get('id'), str)
                       or not item['id'] for item in turn['items'])
                or turn.get('truncated', False) is not False):
            _fail('readback_required: complete actual native turn/item boundary required')
        turn_ids.append(turn['id']); item_ids.extend(item['id'] for item in turn['items'])
    if len(set(turn_ids)) != len(turn_ids) or len(set(item_ids)) != len(item_ids):
        _fail('readback_required: unambiguous actual native turn/item boundary required')
    return value


def _notification_before(root, current, native_before):
    """Both actual source and idle recipient pages precede the immutable attempt."""
    if not isinstance(native_before, dict) or set(native_before) != {'sender', 'receiver'}:
        _fail('readback_required: original sender and receiver native-before boundaries required')
    sender = _notification_native_page(root, native_before['sender'], current['identity']['sender_department'])
    receiver = _notification_native_page(root, native_before['receiver'], current['route']['target_department'])
    turns = sender['turns']
    from goal_source_recovery import actual_target_turn_status
    binding=_w().department_registry(root)[current['route']['target_department']]['chat_binding']
    live_pin=current.get('live_identity',{})
    if _w().file_digest(root,live_pin.get('path',''))!=live_pin:
        _fail('readback_required: frozen notification live identity changed')
    live=_w().read_json(_w().safe_path(root,live_pin['path']))
    from goal_delivery_runtime import _collaboration_native
    inventory=_collaboration_native(root,live['actual_native_observation'])
    targets=[row for row in [*inventory.get('threads',[]),*inventory.get('pinnedThreads',[])]
             if row.get('id')==binding['task_id']]
    if len(targets)!=1:_fail('readback_required: one original frozen target boundary required')
    baseline=targets[0].copy()
    pins=live.get('actual_native_target_turns',{})
    prepared=pins.get(binding['task_id'],live.get('actual_native_target_turn'))
    if prepared is not None:
        prepared_page=_collaboration_native(root,prepared)
        if actual_target_turn_status(root,live,targets[0],binding)!='idle':
            _fail('readback_required: prepared actual target is not idle')
        newer=prepared_page['thread'].get('updatedAt')
        known=baseline.get('updatedAt')
        if type(newer) in {int,float} and (type(known) not in {int,float} or newer>known):
            baseline['updatedAt']=newer
    receiver_status=actual_target_turn_status(root,{'actual_native_target_turn':native_before['receiver']},
                                             baseline,binding)
    if (not turns or turns[0].get('status') != 'inProgress' or turns[0].get('error')
            or receiver_status != 'idle'):
        _fail('readback_required: actual current sender turn and idle recipient boundary required')
    # Existing sender calls to this recipient must retain actual arguments.
    # An old incomplete page cannot certify that this exact call was not made.
    prior_calls = [item for turn in turns for item in turn['items']
                   if item.get('type') == 'mcpToolCall' and item.get('tool') == 'send_message_to_thread']
    payload = current.get('payload', {})
    if _w().file_digest(root, payload.get('path', '')) != payload:
        _fail('readback_required: original immutable notification payload changed')
    body = _w().validation_bytes(_w().safe_path(root, payload['path']))
    for item in prior_calls:
        args = item.get('arguments')
        if (item.get('server') != 'codex_app' or not isinstance(args, dict)
                or not isinstance(args.get('threadId'), str) or not isinstance(args.get('prompt'), str)
                or item.get('truncated', False) is not False):
            _fail('readback_required: original prior native invocation arguments required')
        if args.get('threadId') == current['target_thread_id'] and args['prompt'].encode('utf-8') == body:
            _fail('readback_required: this exact native invocation already exists before reservation')
    return sender, receiver


def _notification_native_effect(root, current, request):
    """Bind one new real invocation and recipient effect to the reserved pages.

    Native read_thread exposes invocation arguments and recipient delegation
    items, but not a paired raw send response. We certify the observed new
    recipient effect, not an unexposed provider response or a caller summary.
    """
    attempts = _notification_attempts(current)
    if not attempts or 'native_before' not in attempts[-1]:
        _fail('readback_required: original immutable attempt native-before boundaries missing; no backfill')
    attempt = attempts[-1]
    before_sender, before_receiver = _notification_before(root, current, attempt['native_before'])
    invocation = request.get('actual_native_invocation')
    transport = request.get('actual_native_transport')
    after_sender = _notification_native_page(root, invocation, current['identity']['sender_department'])
    after_receiver = _notification_native_page(root, transport, current['route']['target_department'])
    payload = current.get('payload', {})
    if _w().file_digest(root, payload.get('path', '')) != payload:
        _fail('readback_required: original immutable notification payload changed')
    try:
        body = _w().validation_bytes(_w().safe_path(root, payload['path'])).decode('utf-8')
    except UnicodeError:
        _fail('readback_required: exact native notification UTF-8 required')

    def preserve_boundary(before, after):
        after_turns = {turn['id']: turn for turn in after['turns']}
        positions = []
        for old in before['turns']:
            new = after_turns.get(old['id'])
            if new is None or new.get('startedAt') != old.get('startedAt'):
                _fail('readback_required: original full native turn boundary absent or changed')
            ids = [item['id'] for item in old['items']]
            if [item['id'] for item in new['items'][:len(ids)]] != ids:
                _fail('readback_required: original complete native item prefix changed')
            # Existing call arguments cannot change when a turn completes.
            for old_item, new_item in zip(old['items'], new['items']):
                fields = ('id', 'type') if old_item.get('type') != 'mcpToolCall' else ('id', 'type', 'server', 'tool', 'arguments')
                if any(old_item.get(key) != new_item.get(key) for key in fields):
                    _fail('readback_required: original native invocation boundary changed')
            positions.append(next(index for index, turn in enumerate(after['turns']) if turn['id'] == old['id']))
        if positions != sorted(positions):
            _fail('readback_required: actual native turn boundary order changed')
        return positions

    preserve_boundary(before_sender, after_sender)
    receiver_positions = preserve_boundary(before_receiver, after_receiver)
    source_turn = before_sender['turns'][0]
    current_turn = next(turn for turn in after_sender['turns'] if turn['id'] == source_turn['id'])
    if current_turn.get('status') not in {'inProgress', 'completed'} or current_turn.get('error'):
        _fail('readback_required: successful actual sender turn required')
    original_ids = {item['id'] for turn in before_sender['turns'] for item in turn['items']}
    for other_turn in after_sender['turns']:
        if other_turn['id'] == source_turn['id']:
            continue
        for item in other_turn['items']:
            args = item.get('arguments', {})
            if (item.get('type') == 'mcpToolCall' and item.get('tool') == 'send_message_to_thread'
                    and isinstance(args, dict) and args.get('threadId') == current['target_thread_id']
                    and args.get('prompt') == body):
                _fail('readback_required: another native turn contains this same target/body invocation')
    calls = []
    for item in current_turn['items']:
        if item.get('type') != 'mcpToolCall' or item.get('tool') != 'send_message_to_thread':
            continue
        args = item.get('arguments', {})
        if not isinstance(args, dict):
            _fail('readback_required: actual native invocation arguments required')
        if args.get('threadId') != current['target_thread_id'] or args.get('prompt') != body:
            continue
        if (item['id'] in original_ids or item.get('server') != 'codex_app'
                or item.get('status') != 'completed' or item.get('error')
                or item.get('truncated', False) is not False
                or set(args) - {'threadId', 'prompt', 'hostId'}
                or ('hostId' in args and args['hostId'] != 'local')):
            _fail('readback_required: a new exact completed original native invocation required')
        from qa_review_plan import _review_native_containers
        try:
            _review_native_containers(item)
        except ValueError:
            _fail('readback_required: successful complete actual native invocation required')
        calls.append(item)
    if len(calls) != 1:
        _fail('readback_required: one new exact actual invocation after the immutable boundary required')
    # Recipient effect must occur in a genuinely new turn before the previous
    # latest turn, not merely in an old turn holding an identical message.
    new_turns = after_receiver['turns'][:receiver_positions[0]] if receiver_positions else after_receiver['turns']
    old_receiver_ids = {item['id'] for turn in before_receiver['turns'] for item in turn['items']}
    old_receiver_turns = {turn['id'] for turn in before_receiver['turns']}
    effects = []
    source_id = before_sender['thread']['id']
    pattern = r'\A<codex_delegation>\s*<source_thread_id>([^<\s]+)</source_thread_id>\s*<input>([\s\S]*)</input>\s*</codex_delegation>\Z'
    for turn in new_turns:
        if turn['id'] in old_receiver_turns:
            _fail('readback_required: new recipient effect reuses the original native turn')
        for item in turn['items']:
            if (item.get('type') != 'functionCallOutput' or item.get('namespace') != 'codex_app'
                    or item.get('name') != 'send_message_to_thread'):
                continue
            output = item.get('output')
            if (not isinstance(output, dict) or not isinstance(output.get('text'), str)
                    or output.get('truncated') is not False):
                _fail('readback_required: complete original recipient delegation output required')
            match = re.fullmatch(pattern, output['text'])
            if not match or match[1] != source_id or match[2] != body:
                continue
            if (item['id'] in old_receiver_ids or turn.get('status') not in {'inProgress', 'completed'}
                    or turn.get('error') or item.get('truncated', False) is not False):
                _fail('readback_required: new successful actual recipient effect required')
            from qa_review_plan import _review_native_containers
            try:
                _review_native_containers(item); _review_native_containers(output)
            except ValueError:
                _fail('readback_required: complete successful original recipient effect required')
            effects.append((turn, item))
    if len(effects) != 1:
        _fail('readback_required: one new exact recipient effect after the immutable boundary required')
    turn, effect = effects[0]
    started = _w()._parse_observed_at(attempt['call_started_at'])
    # A seconds-only provider timestamp describes an interval. Full before
    # boundaries plus one new exact invocation/effect prove order; a same-second
    # integer is compatible, without rewriting or inventing subsecond time.
    effect_started = turn.get('startedAt')
    sender_started = source_turn.get('startedAt')
    if (started is None or type(effect_started) not in {int, float}
            or type(sender_started) not in {int, float}
            or not sender_started <= started.timestamp()
            or not (effect_started > started.timestamp()
                    or (type(effect_started) is int and effect_started == int(started.timestamp())))
            or effect_started > dt.datetime.now(dt.timezone.utc).timestamp()):
        _fail('readback_required: provider recipient effect must start strictly after the immutable reservation')
    return {'schema_version': 'native-notification-effect-readback/v1',
            'attempt_id': attempt['attempt_id'], 'native_before': attempt['native_before'],
            'native_invocation': invocation, 'native_transport': transport,
            'source_thread_id': source_id, 'source_turn_id': source_turn['id'],
            'source_call_id': calls[0]['id'], 'target_thread_id': current['target_thread_id'],
            'recipient_turn_id': turn['id'], 'recipient_effect_id': effect['id'],
            'payload': dict(payload), 'paired_raw_send_response': 'NOT_EXPOSED_BY_NATIVE_READ_THREAD',
            'effect_basis': 'new_original_recipient_delegation_after_both_frozen_native_boundaries'}


def _notification_attempts(current) -> list[NotificationAttempt]:
    """Read the append-only local reservation chain without repairing old data."""
    attempts = current.get('attempts', [])
    if not isinstance(attempts, list):
        _fail('exact internal notification attempt history required')
    previous = ''
    for sequence, attempt in enumerate(attempts, 1):
        if (not isinstance(attempt, dict)
                or set(attempt) not in (set(NotificationAttempt.__annotations__), set(NativeBoundNotificationAttempt.__annotations__))
                or type(attempt.get('sequence')) is not int or attempt['sequence'] != sequence
                or attempt.get('previous_attempt_id') != previous
                or attempt.get('identity') != current.get('identity')
                or attempt.get('tool') != 'mcp__codex_app__send_message_to_thread'
                or attempt.get('target_thread_id') != current.get('target_thread_id')
                or attempt.get('payload') != current.get('payload')
                or _w()._parse_observed_at(attempt.get('call_started_at')) is None):
            _fail('exact internal notification attempt history required; no historical backfill')
        lease = attempt.get('claim')
        if (not isinstance(lease, dict)
                or set(lease) != {'result_key', 'role', 'owner', 'token', 'fence', 'expires'}
                or lease.get('result_key') != (_delivery_key(current['delivery_identity']) if current.get('schema_version') == '2.0' else _key(current['identity']))
                or type(lease.get('fence')) is not int or lease['fence'] < 1
                or (current.get('schema_version') == '2.0' and lease.get('role') != current['identity']['sender_department'])
                or any(not isinstance(lease.get(key), str) or not lease[key]
                       for key in ('role', 'owner', 'token'))):
            _fail('exact original notification attempt lease snapshot required')
        unsigned = {key: value for key, value in attempt.items() if key != 'attempt_id'}
        if attempt.get('attempt_id') != _sha(unsigned):
            _fail('internal notification attempt event changed')
        previous = attempt['attempt_id']
    if current.get('active_attempt_id', '') != previous:
        _fail('exact current internal notification attempt required')
    if attempts and current.get('call_started_at') != attempts[-1]['call_started_at']:
        _fail('current native call time must equal its original immutable attempt')
    return attempts


def notification_send_started(root, identity, claim, *, native_before=None):
    """Reserve before the native call, so interruption never silently re-sends."""
    identity = exact_identity(identity)
    with coordination_lock(root):
        validate_notification_delivery(root, identity)
        current = _w().read_json(_notification_path(root, identity))
        rows = [row for row in _w()._result_handoff_rows(root, identity['task_id'])
                if _w()._result_identity(row) == tuple(identity[key] for key in IDENTITY_FIELDS[1:])]
        if any(row.get('event') == 'controller_received' for row in rows):
            _fail('actual result already received; do not send an old notification')
        if (current.get('delivered')
                or any(row.get('event') == 'notification_sent' for row in rows)):
            _fail('native notification already sent; recover its actual receipt before retry')
        if (current.get('state') != 'prepared' or not isinstance(claim, dict)
                or any(current.get('claim', {}).get(key) != claim.get(key)
                       for key in ('result_key', 'role', 'owner', 'token', 'fence'))):
            _fail('exact prepared existing lease required before native send')
        if current.get('effect_observation') == 'absent' or current.get('actual_native_failure'):
            _validate_absent_notification_failure(root, current, current.get('actual_native_failure'))
        store = DeliveryStore(root)
        try:
            lease = store._lease(current['delivery_identity'], identity['sender_department'], current['coordinator_owner'], claim)
        finally:
            store.close()
        payload = current.get('payload')
        if (not isinstance(payload, dict)
                or _w().file_digest(root, payload.get('path', '')) != payload):
            _fail('frozen exact notification payload required before native call reservation')
        attempts = _notification_attempts(current)
        if attempts or 'call_started_at' in current:
            _fail('native send effect uncertain; original started call requires actual effect readback, no attempt backfill')
        if native_before is None:
            return {'result': 'readback_required', 'identity': identity, 'delivered': False,
                    'native_send_executed': False, 'original_record_unchanged': True,
                    'block_reason': 'original_sender_and_receiver_native_before_boundaries_required',
                    'next_action': 'freeze_actual_current_sender_and_idle_recipient_native_pages_before_reservation'}
        _notification_before(root, current, native_before)
        started = dt.datetime.now(dt.timezone.utc)
        started_at = started.isoformat()
        attempt: NativeBoundNotificationAttempt = {
            'sequence': len(attempts) + 1,
            'previous_attempt_id': attempts[-1]['attempt_id'] if attempts else '',
            'identity': identity,
            'tool': 'mcp__codex_app__send_message_to_thread',
            'target_thread_id': current['target_thread_id'],
            'payload': dict(payload),
            'claim': {key: lease[key]
                      for key in ('result_key', 'role', 'owner', 'token', 'fence', 'expires')},
            'call_started_at': started_at,
            'attempt_id': '',
            'native_before': native_before,
        }
        attempt['attempt_id'] = _sha({key: value for key, value in attempt.items() if key != 'attempt_id'})
        current.update(state='sending', call_started_at=started_at,
                       active_attempt_id=attempt['attempt_id'], attempts=[*attempts, attempt],
                       effect_observation='unknown')
        _w().atomic_write_json(_notification_path(root, identity), current)
        return {**current, 'native_send_not_before': dt.datetime.fromtimestamp(
                    int(started.timestamp()) + 1, dt.timezone.utc).isoformat(),
                'native_effect_readback_required': True,
                'next_action': 'send_once_after_native_send_not_before_then_read_exact_original_sender_and_recipient_pages'}


def notification_record(root, identity, request, *, _coordination_locked=False):
    """Commit only an original pinned successful native send plus exact policy."""
    identity = exact_identity(identity)
    if result_lane(root, identity).get('lane') == 'HQ_knowledge':
        hq_knowledge_source(root, identity)
    with (nullcontext() if _coordination_locked else coordination_lock(root)):
        w = _w(); current = w.read_json(_notification_path(root, identity))
        native_pin = request.get('actual_native_transport')
        if not isinstance(native_pin, dict) or w.file_digest(root, native_pin.get('path', '')) != native_pin:
            _fail('original actual native send pin required; no missing-pin fallback')
        rows = [row for row in w._result_handoff_rows(root, identity['task_id'])
                if w._result_identity(row) == tuple(identity[key] for key in IDENTITY_FIELDS[1:])]
        intake = _received_delivery(root, identity, current.get('route', {}))
        if intake is not None:
            return {**current, 'result': 'duplicate_ignored', 'resolved_by_actual_intake': True,
                    'native_record_id': intake['record_id']}
        prior_sent = [row for row in rows if row.get('event') == 'notification_sent']
        if prior_sent and (len(prior_sent) != 1 or prior_sent[0].get('actual_native_transport') != native_pin):
            _fail('existing notification send cannot replace its exact original transport')
        if current.get('delivered'):
            if current.get('native_transport') != native_pin:
                _fail('already delivered notification cannot replace actual transport')
            return current
        if current.get('schema_version') != '2.0' or current.get('state') != 'sending' or not _notification_attempts(current):
            _fail('exact prepared original notification required')
        native_effect = _notification_native_effect(root, current, request)
        message_ref = request.get('message_ref')
        if (not isinstance(message_ref, str) or not message_ref
                or w.safe_path(root, message_ref.split('#', 1)[0]) != w.safe_path(root, native_pin['path'])):
            _fail('native send reference must point to its original frozen transport file')
        store = DeliveryStore(root)
        try:
            claim = request.get('delivery_claim', current.get('delivery_claim'))
            lease = store._lease(current['delivery_identity'], identity['sender_department'], current['coordinator_owner'], claim)
            attempts = _notification_attempts(current)
            if lease['fence'] < attempts[-1]['claim']['fence']:
                _fail('current sender lease cannot predate the original native attempt fence')
        finally:
            store.close()
        payload = current.get('payload', {})
        if w.file_digest(root, payload.get('path', '')) != payload or request.get('message_sha256') != payload.get('sha256'):
            _fail('frozen exact notification message bytes required')
        decisions = [r for r in w.read_jsonl(Path(root) / w.POLICY_DECISIONS)
                     if r.get('decision_id') == request.get('policy_decision_id')]
        if len(decisions) != 1 or any(decisions[0].get(k) != v for k,v in
                {'status':'allow','routing_status':'routing_allowed','task_id':identity['task_id'],
                 'department':identity['sender_department'], 'action_id':'notify-result-' + _delivery_key(current['delivery_identity']).split(':', 1)[1],
                 'scope':'department_result:' + identity['task_id'] + ':' + identity['sender_department'],
                 'action_class':'thread_message','target_department':current['route']['target_department'],
                 'target_thread_id':current['target_thread_id'],'payload_sha256':payload['sha256']}.items()):
            _fail('exact existing permitted native notification policy required')
        checked = w._parse_observed_at(decisions[0].get('checked_at'))
        started = w._parse_observed_at(current.get('call_started_at'))
        if checked is None or started is None or not checked <= started <= dt.datetime.now(dt.timezone.utc):
            _fail('actual exact message policy must precede the reserved native call')
        current.update(state='sent', delivered=True, native_transport=native_pin, claim=claim,
                       native_invocation=request['actual_native_invocation'], native_effect=native_effect,
                       native_receipt_ref=request.get('message_ref'), policy_decision_id=request['policy_decision_id'],
                       sent_at=w.utc_timestamp(), queue_is_delivery=False)
        w.atomic_write_json(_notification_path(root, identity), current)
        return current


def notification_recover(root, identity, role, owner, request_id, reason, request, ttl_seconds=900):
    """Read a successful original attempt, renew sender ownership, never re-send."""
    if not isinstance(reason, str) or not reason.strip():
        _fail('explicit original send-effect recovery reason required')
    identity = exact_identity(identity)
    with coordination_lock(root):
        current = _w().read_json(_notification_path(root, identity))
        route = result_lane(root, identity)
        intake = _received_delivery(root, identity, route)
        if intake or current.get('delivered'):
            return {'result': 'duplicate_ignored', 'delivered': current.get('delivered', False),
                    'resolved_by_actual_intake': intake is not None, 'native_send_executed': False}
        if (current.get('schema_version') != '2.0' or current.get('state') != 'sending'
                or not _notification_attempts(current)):
            _fail('original started sender attempt required; no backfill or unknown-effect retry')
        if role != identity['sender_department']:
            _fail('only the original actual sender may recover notification ownership')
        try:
            _notification_native_effect(root, current, request)
        except _w().WorkflowError as error:
            return {'result': 'readback_required', 'identity': identity, 'delivered': False,
                    'native_send_executed': False, 'original_record_unchanged': True,
                    'recovery_owner': identity['sender_department'], 'block_reason': str(error),
                    'next_action': 'read_exact_original_native_boundaries_invocation_and_recipient_effect_no_resend'}
    store = DeliveryStore(root)
    try:
        claim = store.claim(current['delivery_identity'], role, owner, request_id, ttl_seconds, reason)
    finally:
        store.close()
    with coordination_lock(root):
        current = _w().read_json(_notification_path(root, identity))
        current.update(delivery_claim=claim, claim=claim, coordinator_owner=owner,
                       delivery_owner=role, recovery_owner=role)
        _w().atomic_write_json(_notification_path(root, identity), current)
        result = notification_record(root, identity, {**request, 'delivery_claim': claim}, _coordination_locked=True)
    return {**result, 'native_send_executed': False, 'recovered_original_effect': True}


def notification_lease(root, command, **request):
    if command not in {'renew', 'release', 'readback'}:
        _fail('delivery lease command must be renew/release/readback')
    store = DeliveryStore(root)
    try:
        return getattr(store, command)(**request)
    finally:
        store.close()


def _validate_absent_notification_failure(root, current, actual_native_failure):
    """No observed native failure format currently proves call-specific absence.

    A digest pins bytes, and the internal reservation identifies a local start.
    Neither authenticates a provider event or proves that dispatch had no effect.
    Do not infer absence from isError, timing, copied files, or caller labels.
    """
    if (not isinstance(actual_native_failure, dict)
            or _w().file_digest(root, actual_native_failure.get('path', '')) != actual_native_failure):
        _fail('original exact native failure pin required to prove send absent')
    attempts = _notification_attempts(current)
    if not attempts:
        _fail('current call has no original internal attempt; native absence contract missing, no backfill')
    _fail('verified call-specific native no-effect contract missing; errors or attempt labels cannot prove absent')


def notification_failed(root, identity, reason, effect='unknown', actual_native_failure=None):
    identity = exact_identity(identity)
    if not isinstance(reason, str) or not reason.strip() or effect not in {'absent', 'unknown'}:
        _fail('actual failure reason and explicit effect required')
    with coordination_lock(root):
        current = _w().read_json(_notification_path(root, identity))
        rows = [row for row in _w()._result_handoff_rows(root, identity['task_id'])
                if _w()._result_identity(row) == tuple(identity[key] for key in IDENTITY_FIELDS[1:])]
        if (current.get('delivered') or current.get('state') == 'sent'
                or any(row.get('event') in {'notification_sent', 'controller_received'} for row in rows)):
            _fail('delivered effect cannot become failed')
        if effect == 'absent':
            _validate_absent_notification_failure(root, current, actual_native_failure)
            current['actual_native_failure'] = actual_native_failure
        current.update(state='failed' if effect == 'absent' else 'sending', defer_reason=reason,
                       effect_observation=effect, recovery_condition='read actual send receipt first; unknown is never permission to resend')
        _w().atomic_write_json(_notification_path(root, identity), current)
        return current


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("claim", "readback", "renew", "release", "transfer", "recover", "precheck", "recover-reservation", 'notification-enqueue', 'notification-plan', 'notification-claim', 'notification-call-start', 'notification-record', 'notification-failed', 'notification-recover', 'delivery-renew', 'delivery-release', 'delivery-readback', 'knowledge-source'))
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--input", type=Path, required=True)
    args = parser.parse_args(argv)
    request = json.loads(args.input.read_text(encoding="utf-8"))
    with _w().request_validation_context():
        if args.command.startswith('notification-'):
            functions = {'notification-enqueue': notification_enqueue, 'notification-plan': notification_plan,
                         'notification-claim': notification_claim, 'notification-call-start': notification_send_started,
                         'notification-record': notification_record, 'notification-failed': notification_failed,
                         'notification-recover': notification_recover}
            result = functions[args.command](args.root, **request)
        elif args.command.startswith('delivery-'):
            result = notification_lease(args.root, args.command.split('-', 1)[1], **request)
        elif args.command == 'knowledge-source':
            result = hq_knowledge_source(args.root, **request)
        elif args.command == "recover-reservation":
            result = recover_reservation(args.root, request["handoff_request"], request["reason"])
        else:
            store = CoordinationStore(args.root)
            try:
                result = getattr(store, args.command)(**request)
            finally:
                store.close()
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
