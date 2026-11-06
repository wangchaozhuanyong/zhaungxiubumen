"""Owner-delegated routine coordination, on the existing result/SQL ledgers.

The logical recipient is immutable. The handling actor is authenticated by
its own native read, lease, decision and reply; no producer/permit is assigned.
"""
from pathlib import Path
import argparse
import datetime as dt
import json
import re
import uuid
import sys

# Direct documented CLI and imported use share the confirmed project runtime.
_RUNTIME_ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(_RUNTIME_ROOT), str(_RUNTIME_ROOT / "tools")]

import workflow_control as w

ROLE = 'operations-assistant'
HQ = 'operations'
SOURCE = {'path': 'logs/handoffs/2026-10-27-chief-assistant-routine-decision-delegation-v1/operations/ACTUAL-OWNER-NATIVE-DECISION.json',
          'sha256': '324f5c5d37d02fbcf01d299d58b41c7ed26d10be0a9fb40bedf42e32a14b9271', 'size': 1827}
MODEL = 'owner_delegated_routine_coordination_v1'
DECISIONS = {'continue_original_owner', 'acknowledge_completed_scope', 'coordinate_original_scope',
             'wait_exact_dependency', 'escalate_sensitive'}


def require(test, message):
    if not test:
        raise w.WorkflowError('routine coordination: ' + message)


def doc(root, pin):
    require(isinstance(pin, dict) and w.file_digest(root, pin.get('path', '')) == pin, 'exact immutable source pin required')
    value = json.loads(w.safe_path(root, pin['path']).read_text())
    require(isinstance(value, dict), 'object source required')
    return value


def authority(root):
    config = w.read_json(Path(root) / 'data/task-contract.json').get('routine_coordination')
    if config is None:
        return None
    require(config.get('model') == MODEL and config.get('owner_source') == SOURCE
            and config.get('primary') == ROLE and config.get('fallback') == HQ,
            'actual owner source, primary and fallback required')
    raw = doc(root, SOURCE)
    native = doc(root, config.get('actual_owner_native'))
    registry = w.department_registry(root)
    hq, chief = [registry[x]['chat_binding'] for x in (HQ, ROLE)]
    require(raw.get('thread', {}).get('id') == native.get('thread', {}).get('id') == hq['task_id']
            and hq.get('project_id') == chief.get('project_id') == raw['thread'].get('project_id')
            and Path(hq['cwd']).resolve() == Path(chief['cwd']).resolve() == Path(root).resolve()
            and native['thread'].get('cwd') == hq['cwd'], 'real fixed HQ/chief project and native required')
    selected = [(t, m) for t in native.get('turns', []) for m in t.get('items', [])
                if m.get('id') == raw.get('user_message', {}).get('id')]
    require(len(selected) == 1 and selected[0][0].get('id') == raw.get('turn', {}).get('id')
            and selected[0][1] == raw['user_message'] and selected[0][1].get('type') == 'userMessage'
            and selected[0][0].get('status') in {'inProgress', 'completed'} and not selected[0][0].get('error'),
            'actual owner message, never assistant paraphrase or fabricated completion')
    text = ''.join(c.get('text', '') for c in raw['user_message'].get('content', []) if c.get('type') == 'text')
    require(all(x in text for x in ('权限跟你一样', '无需跟你汇报', '审批工作优先安排给他', '忙不过来你接手', '重大'))
            and registry[ROLE].get('new_dispatch_enabled') is True
            and registry[ROLE].get('coordination_authority', {}).get('routine_decisions') is True
            and registry[ROLE].get('production_write_allowed') is False,
            'verified routine delegation and no production executor role required')
    return config



def current_result_transport(root, record):
    """Authenticate a frozen current-chief notice; historical assistants stay frozen."""
    import result_coordination as rc
    import department_autonomy as a
    value = rc.exact_identity(record.get('identity', {}))
    target = record.get('route', {}).get('target_department')
    if target != ROLE or value['sender_department'] in a.ASSISTANTS:
        return False
    queued = rc._validate_queued(root, value)
    if queued.get('routine_route_authorization') != SOURCE:
        return False  # An old A1 label is not the new real human delegation.
    require(authority(root) is not None, 'current actual chief authority required')
    frozen = rc.frozen_notification_route(root, record)
    route = rc.result_lane(root, value)
    require(route.get('lane') == frozen.get('lane') == 'HQ_knowledge'
            and route.get('target_department') == frozen.get('target_department') == ROLE
            and record.get('delivery_identity') == rc.delivery_identity(root, value, route=route)
            and a.professional(root, value['sender_department']),
            'same genuine professional/native source and immutable current-chief route required')
    return True



def notification_task_pause(root, task):
    """A current owner hold only denies wakeup of its exact frozen child scope.

    Index refs locate evidence; they are never a permission or a blanket hold of
    every referenced ancestor/department. Existing completed intake wins first.
    """
    import department_autonomy as a
    snap=w.read_json(w.snapshot_path(root,task))
    if snap.get('current_state') in {'paused','user_paused','suspended'}:
        return {'task_id':task,'state':snap['current_state'],'new_dispatch_allowed':False}
    index=w.read_json(Path(root)/'data/operations-goal-followthrough.json')
    items=index.get('open_goals',[])
    if isinstance(items,dict):items=list(items.values())
    for row in items:
        pause=row.get('paused_by_owner',{})
        exact=pause.get('exact_task_id')
        if not row.get('user_paused') or not exact:continue
        refs=row.get('original_task_refs',[])
        require(exact in refs,'paused exact original task must belong to its real index refs')
        # Follow only immutable child -> parent edges, never all index aliases.
        chain=[];cursor=task
        for _ in range(32):
            if cursor in chain:raise w.WorkflowError('routine coordination: cyclic frozen task lineage')
            chain.append(cursor)
            if cursor==exact:break
            current=w.read_json(w.snapshot_path(root,cursor))
            if not current.get('goal_contract'):break
            frozen=a.document(root,current['goal_contract']);goal=current.get('goal_delivery',{})
            require(goal.get('parent_task_id')==frozen.get('parent_task_id')
                    and goal.get('authorized_scope')==frozen.get('authorized_scope'),
                    'unchanged real frozen parent/scope before applying owner pause')
            cursor=frozen.get('parent_task_id')
            if not cursor:break
        if exact not in chain:continue
        if task!=exact and pause.get('pure_subordinate_scope_only') is not True:continue
        raw=doc(root,pause.get('source'));decision=doc(root,pause.get('decision'))
        selected=raw.get('selected_native',{});human=decision.get('source_human',{})
        messages=selected.get('user_messages',[]);hq=w.department_registry(root)[HQ]['chat_binding']
        require(raw.get('source_tool')=='mcp__codex_app__read_thread'
                and decision.get('schema')=='HQ-current-owner-pause-and-complete-bounded-other-goals/v1'
                and decision.get('pause',{}).get('task_id')==exact
                and human.get('thread_id')==selected.get('thread',{}).get('id')==hq['task_id']
                and selected.get('thread',{}).get('cwd')==hq['cwd']==str(Path(root).resolve())
                and human.get('turn_id')==selected.get('turn',{}).get('id')
                and len(messages)==1 and messages[0].get('type')=='userMessage'
                and messages[0].get('id')==human.get('message_id')
                and ''.join(x.get('text','')for x in messages[0].get('content',[])if x.get('type')=='text').strip()
                    ==human.get('exact_text')==raw.get('user_text_verbatim')
                and Path(human.get('path','')).resolve()==(Path(root)/pause['source']['path']).resolve()
                and pause.get('independent_other_goals_not_paused') is True,
                'actual pinned owner words/HQ scope and pure-parent-only hold required')
        return {'task_id':task,'exact_paused_parent':exact,'frozen_lineage':chain,
                'source':pause['source'],'decision':pause['decision'],
                'pure_subordinate_scope_only':True,'independent_goals_not_paused':True,'new_dispatch_allowed':False}
    return None


def completed_owner_successor_boundary(root, record):
    """Read-only suppression of an unsent intermediate HQ report, never intake.

    The closed original goal, unchanged owner/scope and a later authenticated
    completed report with committed SQL/native intake must all agree.
    """
    import result_coordination as rc
    import department_autonomy as a
    value = rc.exact_identity(record.get('identity', {}))
    target = record.get('route', {}).get('target_department')
    if target != HQ or value['sender_department'] in a.ASSISTANTS:
        return None
    effect = record.get('native_queue_transport') or {}
    if (record.get('delivered') or record.get('state') in {'sending','uncertain','sent'}
            or effect.get('state') in {'sending','uncertain','accepted'}
            or record.get('call_started_at') or record.get('attempts')):
        return None  # Keep every original/unknown transport effect visible.
    snap = w.read_json(w.snapshot_path(root, value['task_id']))
    if snap.get('current_state') != 'closed':
        return None
    goal = snap.get('goal_delivery') or {}
    if goal.get('primary_owner') != value['sender_department'] or not snap.get('goal_contract'):
        return None
    frozen = a.document(root, snap['goal_contract'])
    require(all(goal.get(k) == frozen.get(k) for k in
                ('primary_owner','producer_departments','authorized_scope')),
            'unchanged original owner and scope before historical suppression')
    queued = rc._validate_queued(root, value)
    box = a.document(root, queued['outbox'])
    scope = box.get('scope')
    if (box.get('task_id') != value['task_id'] or box.get('department') != value['sender_department']
            or not scope or scope not in goal.get('authorized_scope', [])
            or box.get('primary_owner', value['sender_department']) != value['sender_department']):
        return None
    history = w._result_handoff_rows(root, value['task_id'])
    own = [i for i,row in enumerate(history) if row.get('event') == 'notification_queued'
           and rc.exact_identity(row) == value]
    require(len(own) == 1, 'one original hash-chained intermediate report required')
    for row in reversed(history[own[0]+1:]):
        if (row.get('event') != 'notification_queued'
                or row.get('task_id') != value['task_id']
                or row.get('sender_department') != value['sender_department']
                or row.get('target_department') != target):
            continue
        successor = rc.exact_identity(row)
        later = rc._validate_queued(root, successor)
        newer = a.document(root, later['outbox'])
        if (newer.get('status') != 'completed'
                or any(newer.get(k) != box.get(k) for k in ('task_id','department','scope'))
                or newer.get('primary_owner', value['sender_department']) != value['sender_department']):
            continue
        later_route = rc._original_intake_notification(root, successor,
                       {'lane':'HQ_knowledge','target_department':target})
        actual = rc._received_delivery(root, successor, later_route)
        if actual is None:
            continue
        require(actual.get('outbox') == later['outbox'] and actual.get('record_id'),
                'completed successor exact outbox and real committed intake required')
        return {'state':'later_received_completed_owner_report', 'successor':successor,
                'successor_outbox':later['outbox'], 'successor_intake_record':actual['record_id'],
                'new_dispatch_allowed':False, 'lease_recovery_required':False,
                'original_record_unchanged':True,
                'original_intake_or_business_completion_inferred':False}
    return None

def notification_boundary(root, record):
    """One read-only decision shared by ingest, pump and the current work view.

    Later reports defer an old *notification*, never forge intake or completion.
    Only authenticated full owner reports of the same exact scope are comparable.
    """
    import result_coordination as rc
    import department_autonomy as a
    value = rc.exact_identity(record.get('identity', {}))
    target = record.get('route', {}).get('target_department')
    intake = rc.received_notification(root, record)
    if intake is not None:
        return {'state': 'committed_original_intake', 'intake': intake, 'new_dispatch_allowed': False}
    rc.frozen_notification_route(root,record)
    paused=notification_task_pause(root,value['task_id'])
    if paused:
        return {'state':'original_task_paused','new_dispatch_allowed':False,'pause_source':paused}
    completed = completed_owner_successor_boundary(root, record)
    if completed is not None:
        return completed
    if target in a.ASSISTANTS or value['sender_department'] in a.ASSISTANTS:
        if not current_result_transport(root, record):
            return {'state': 'historical_assistant_transport', 'new_dispatch_allowed': False}
    else:
        return {'state': 'current_original_result', 'new_dispatch_allowed': True}
    # Existing frozen receiver/source authentication remains the source of truth.
    queued = rc._validate_queued(root, value)
    route = rc.result_lane(root, value)
    require(route.get('lane') in {'HQ_knowledge', 'professional_acceptance'}
            and route.get('target_department') == target
            and rc.delivery_identity(root, value, route=route) == record.get('delivery_identity'),
            'exact original source and frozen route required')
    snap = w.read_json(w.snapshot_path(root, value['task_id']))
    paused=notification_task_pause(root,value['task_id'])
    if paused:
        return {'state': 'original_task_paused', 'new_dispatch_allowed': False,'pause_source':paused}
    effect=record.get('native_queue_transport') or {}
    if effect.get('state') in {'sending','uncertain'} or record.get('state') in {'sending','uncertain'}:
        return {'state': 'current_original_result', 'new_dispatch_allowed': True,
                'original_effect_readback_required': True}
    box = a.document(root, queued['outbox'])
    if (target == ROLE and box.get('schema') == 'flashcast-department-outbox/v2'
            and box.get('primary_owner') == snap.get('goal_delivery', {}).get('primary_owner', box.get('primary_owner'))
            and box.get('department') == value['sender_department']
            and box.get('delivery_model') == a.MODE):
        history = w._result_handoff_rows(root, value['task_id'])
        own = [i for i, row in enumerate(history) if row.get('event') == 'notification_queued'
               and rc.exact_identity(row) == value]
        require(len(own) == 1, 'one original hash-chained notification position required')
        for row in reversed(history[own[0]+1:]):
            if (row.get('event') != 'notification_queued'
                    or row.get('sender_department') not in {value['sender_department'],box.get('primary_owner')}
                    or row.get('target_department') != target
                    or row.get('routine_route_authorization') != SOURCE):
                continue
            successor = rc.exact_identity(row)
            later = rc._validate_queued(root, successor)
            newer = a.document(root, later['outbox'])
            fields = ('task_id', 'scope', 'primary_owner')
            if not all(newer.get(k) == box.get(k) for k in fields):continue
            if (row.get('sender_department') == value['sender_department']
                    and all(newer.get(k) == box.get(k) for k in ('schema','delivery_model','department'))):
                return {'state': 'later_original_owner_report', 'successor': successor,
                        'successor_outbox': later['outbox'], 'new_dispatch_allowed': False,
                        'original_intake_or_business_completion_inferred': False}
            if (value['sender_department'] != box['primary_owner']
                    and newer.get('department') == newer.get('primary_owner') == row.get('sender_department')):
                frozen_later=rc._original_intake_notification(root,successor,{'lane':'HQ_knowledge','target_department':target})
                actual=rc._received_delivery(root,successor,frozen_later)
                if actual is not None:
                    return {'state':'later_received_original_owner_report','successor':successor,
                            'successor_outbox':later['outbox'],'successor_intake_record':actual['record_id'],
                            'new_dispatch_allowed':False,'original_intake_or_business_completion_inferred':False}
    return {'state': 'current_original_result', 'new_dispatch_allowed': True, 'route': route}

def default_receiver(root, logical):
    return ROLE if logical == HQ and authority(root) is not None else logical


def actor_allowed(root, identity, logical, role):
    import department_autonomy as a
    config = authority(root)
    if config is None or logical not in {HQ, ROLE} or role not in {HQ, ROLE} or identity.get('sender_department') == role:
        return False
    require(identity.get('sender_department') not in a.ASSISTANTS, 'retired assistant source is not a new routine delivery')
    return True


def rows(root, identity):
    import result_coordination as rc
    return [r for r in w._result_handoff_rows(root, identity['task_id']) if rc.exact_identity(r) == rc.exact_identity(identity)]


def claimable(root, identity, role):
    import result_coordination as rc
    logical = rc.result_lane(root, identity).get('target_department')
    if not actor_allowed(root, identity, logical, role):
        return False
    existing = [r for r in rows(root, identity) if r.get('event') == 'controller_received']
    require(not existing, 'already received original result; read committed effect, never re-intake')
    return True


def decision_claim_source(root,identity,role,owner,received_record_id):
    """Read the original actual receipt; never authorize a second intake."""
    import result_coordination as rc
    authority(root);identity=rc.exact_identity(identity)
    logical=rc.result_lane(root,identity).get('target_department')
    require(role==ROLE and actor_allowed(root,identity,logical,role),'current real delegated routine handler required')
    intake=_committed_intake(root,{**identity,'received_record_id':received_record_id,'coordinator_role':role})
    fixed=w.department_registry(root)[role]['chat_binding']['task_id']
    # An owner suffix is receipt-bound audit metadata, never an actor alias:
    # the entire owner must match the unique already committed receipt.
    require(isinstance(owner,str) and bool(owner) and len(owner)<=200
            and owner.split(':',1)[0]==fixed and (':' not in owner or bool(owner.split(':',1)[1]))
            and intake.get('routine_delegation')==SOURCE and intake.get('coordinator_owner')==owner,
            'same actual original handler and exact committed receipt required')
    existing=[r for r in rows(root,identity)if r.get('event')=='controller_decision']
    for row in existing:rc._committed_result(root,row)
    require(not existing,'ordinary decision already exists; read its committed effect')
    return {'purpose':'ordinary_decision_only','received_record_id':intake['record_id'],
            'outbox':intake['outbox'],'identity':identity,'receipt_commit_fingerprint':rc._committed_result(root,intake),
            'external_permission_issued':False,'no_reintake':True}


def decision_claim_preflight(root,request):
    import result_coordination as rc,sqlite3
    identity=rc.exact_identity(request);source=decision_claim_source(root,identity,request.get('coordinator_role'),
          request.get('coordinator_owner'),request.get('received_record_id'))
    require(type(request.get('ttl_seconds',900))is int and 1<=request.get('ttl_seconds',900)<=900
            and isinstance(request.get('request_id'),str)and request['request_id'].strip()
            and isinstance(request.get('recovery_reason'),str)and request['recovery_reason'].strip(),
            'explicit original decision recovery reason, stable request id and TTL1..900 required')
    database=w.safe_path(root,str(rc.DATABASE));require(database.is_file(),'original coordination database required')
    c=sqlite3.connect(database.as_uri()+'?mode=ro',uri=True)
    try:
        for status,payload in c.execute('SELECT status,payload_json FROM reservations WHERE result_key=?',(rc._key(identity),)):
            original=json.loads(payload).get('request',{})
            require(original.get('event')!='controller_decision','existing/unknown decision reservation; recover its original effect before a new lease')
    finally:c.close()
    return {'state':'EXACT_POSTRECEIPT_DECISION_SOURCE_VALID','source':source,'actual_lease_created':False,
            'actual_decision_recorded':False,'external_permission_issued':False}


def receiver_context(root, request, logical):
    """Real role plus frozen logical receiver, no target alias or new intake."""
    import result_coordination as rc
    role = request.get('coordinator_role', HQ)
    require(actor_allowed(root, request, logical, role), 'authorized routine actor for original logical receiver required')
    require(request.get('routine_delegation') == SOURCE, 'exact current owner delegation required')
    require(request.get('logical_receiver') == logical, 'frozen original logical receiver cannot change')
    fixed = w.department_registry(root)[role]['chat_binding']
    owner = request.get('coordinator_owner')
    require(isinstance(owner, str) and owner.split(':', 1)[0] == fixed['task_id'], 'actual handler fixed thread required')
    return {'logical_receiver': logical, 'handling_actor': role, 'routine_delegation': SOURCE}


def lease(root, store, request):
    import result_coordination as rc
    identity = rc.exact_identity(request)
    logical = rc.result_lane(root, identity)['target_department']
    proof = receiver_context(root, request, logical)
    row=store._lease(identity, request['coordinator_role'], request['coordinator_owner'], request.get('coordination_claim'))
    marker=json.loads(row['precheck_json'])if row['precheck_json']else{}
    if marker.get('purpose')=='ordinary_decision_only':
        require(request.get('event')=='controller_decision'and marker.get('received_record_id')==request.get('received_record_id'),
                'postreceipt lease only continues this exact ordinary decision; never re-intake')
        intake=_committed_intake(root,request)
        require(marker.get('identity')==identity and marker.get('outbox')==intake['outbox']
                and marker.get('receipt_commit_fingerprint')==rc._committed_result(root,intake),
                'original committed receipt source must remain exact')
    return proof


def intake_readback(root, payload, row):
    import department_autonomy as a
    if not row.get('routine_delegation'):
        return False
    request = payload['request']
    require(request.get('event') == row.get('event') == 'controller_received', 'routine intake schema required')
    proof = receiver_context(root, {**request, 'coordinator_role': row.get('coordinator_role'),
                              'coordinator_owner': row.get('coordinator_owner')}, row.get('target_department'))
    require(all(row.get(k) == v for k, v in proof.items()), 'original logical receiver and real actor cannot be aliased')
    actual = a.received_knowledge(root, {**request, 'coordinator_role': row['coordinator_role'],
                                        'coordinator_owner': row.get('coordinator_owner')})
    require(all(row.get(k) == v for k, v in actual.items()), 'real actor native read must remain exact')
    return True


def _committed_intake(root, request):
    import result_coordination as rc
    matches = [r for r in rows(root, request) if r.get('event') == 'controller_received']
    require(len(matches) == 1, 'one actual original committed intake before routine decision')
    intake = matches[0]
    rc._committed_result(root, intake)
    require(intake.get('coordinator_role') == request.get('coordinator_role')
            and request.get('received_record_id') == intake['record_id'], 'actual handling actor and exact intake required')
    return intake


def decision(root, request):
    """A routine decision does not create scope, permit, QA or production rights."""
    import goal_delivery_runtime as g
    import result_coordination as rc
    require(request.get('event') == 'controller_decision' and request.get('decision') in DECISIONS,
            'known bounded routine decision required')
    intake = _committed_intake(root, request)
    box = doc(root, intake['outbox'])
    snapshot = g.restore_goal(root, w.read_json(w.snapshot_path(root, request['task_id'])))
    goal = snapshot.get('goal_delivery', {})
    scope = box.get('scope')
    if scope is None and len(goal.get('authorized_scope', [])) == 1:
        scope = goal['authorized_scope'][0]
    require(isinstance(scope, str) and request.get('scope') == scope,
            'exact original result scope required')
    next_owner = request.get('next_owner')
    require(next_owner == (HQ if request['decision'] == 'escalate_sensitive' else goal.get('primary_owner', request['sender_department']))
            and isinstance(request.get('next_action'), str) and request['next_action'].strip(),
            'return to original professional owner; sensitive actions go to HQ')
    require(not any(request.get(k) for k in ('approval_id', 'consume_approval', 'execution_request',
                'permission_issued', 'production_write_allowed', 'business_goal_closed', 'qa_verdict', 'authorization_changes')),
            'routine decision cannot expand scope or issue production approval')
    evidence = doc(root, request.get('decision_source'))
    require(evidence.get('schema') == 'routine-original-result-decision/v1'
            and all(evidence.get(k) == request.get(k) for k in (*rc.IDENTITY_FIELDS, 'scope', 'decision', 'next_owner', 'next_action'))
            and evidence.get('outbox') == intake['outbox'] and evidence.get('owner_delegation') == SOURCE
            and evidence.get('external_permission_issued') is False,
            'exact immutable ordinary decision evidence required')
    page = g._native_document(root, request.get('actual_decision_native'))
    fixed = w.department_registry(root)[request['coordinator_role']]['chat_binding']
    pairs = [(t, m) for t in page.get('turns', []) for m in t.get('items', [])
             if m.get('id') == request.get('actual_decision_message_id')]
    require(all(page.get('thread', {}).get(k) == fixed[v] for k, v in {'id': 'task_id', 'title': 'title', 'cwd': 'cwd'}.items())
            and len(pairs) == 1 and not pairs[0][0].get('error') and pairs[0][1].get('type') == 'agentMessage'
            and request['decision_source']['path'] in pairs[0][1].get('text', '')
            and request['decision_source']['sha256'] in pairs[0][1].get('text', ''),
            'real handling actor must name its exact decision source')
    row = {**request, 'record_id': str(uuid.uuid4()), 'created_at': w.utc_timestamp(),
           'outbox': intake['outbox'], 'target_department': intake['target_department'],
           'evidence': [w.file_digest(root, p) for p in request.get('evidence_paths', [])],
           'handling_actor': request['coordinator_role'], 'logical_receiver': intake['target_department'],
           'mode_authorization': a_owner(), 'routine_delegation': SOURCE, 'acceptance_proven': False,
           'external_permission_issued': False, 'business_goal_closed': False,
           'qa_status': 'NOT_VERIFIED', 'execution_status': 'NOT_EXECUTED', 'public_postcheck_status': 'NOT_VERIFIED'}
    for k in ('coordination_claim', 'outbox_path', 'evidence_paths'):
        row.pop(k, None)
    return row


def a_owner():
    from department_autonomy import OWNER
    return OWNER


def record_decision(root, request):
    import department_autonomy as a
    import result_coordination as rc
    identity = rc.exact_identity(request)
    with rc.coordination_lock(root):
        store = rc.CoordinationStore(root)
        try:
            lease(root, store, request)
            existing = [r for r in rows(root, identity) if r.get('event') == 'controller_decision']
            if existing:
                require(len(existing) == 1 and existing[0].get('idempotency_key') == request.get('idempotency_key'),
                        'one routine decision; read original effect before a changed decision')
                rc._committed_result(root, existing[0])
                return {**existing[0], 'result': 'duplicate_ignored'}, [w.result_handoff_path(root, identity['task_id'])]
            row = decision(root, request)
            require(request.get('outbox_path')in {None,row['outbox']['path']},'ordinary decision outbox must be its actual original receipt source')
            request={**request,'outbox_path':row['outbox']['path']}
            payload = rc._payload(root, request)
            effect = rc._sha([request['event'], request.get('idempotency_key')])
            require(isinstance(request.get('idempotency_key'), str) and request['idempotency_key'], 'stable effect key required')
            store._begin()
            prior = store.conn.execute('SELECT status FROM reservations WHERE result_key=? AND effect_key=?',
                                       (rc._key(identity), effect)).fetchone()
            require(prior is None, 'existing/unknown decision effect: recover original reservation, never reappend')
            store.conn.execute("INSERT INTO reservations VALUES(?,?,?,'uncertain',NULL)",
                               (rc._key(identity), effect, rc._canonical(payload)))
            store.conn.commit()
            a.append_result_record(root, identity['task_id'], row)
            rc.HandoffAdmission(store, identity, effect, payload).complete(row)
            return {**row, 'result': 'recorded'}, [w.result_handoff_path(root, identity['task_id'])]
        finally:
            store.close()




DAILY_REPLY_ROOT = 'logs/handoffs/chief-daily-owner-knowledge'
DAILY_KNOWLEDGE_PURPOSE = 'received_declared_daily_owner_knowledge'
ORDINARY_PURPOSES = {'current_chief_original_owner_followthrough', 'original_professional_report_to_current_chief', DAILY_KNOWLEDGE_PURPOSE, 'hq_original_queued_result_intake_followthrough'}


def ordinary_source_history(root, task):
    """Validate immutable history once per exact request snapshot and task."""
    context = w._VALIDATION_CONTEXT.get()
    if context is None:
        return _ordinary_source_history_uncached(root, task)
    root = Path(root).resolve()
    event_path = root / w.WORKFLOW_EVENTS
    receipt_path = w.receipts_path(root, task)
    # bytes() checks file identity/version on every invocation; both digests
    # key only the immutable history, never current routes, policy or effects.
    events = context.bytes(event_path)
    receipt = context.bytes(receipt_path) if receipt_path.exists() else None
    import hashlib, copy
    key = (str(root), task, hashlib.sha256(events).hexdigest(),
           None if receipt is None else hashlib.sha256(receipt).hexdigest())
    cache = getattr(context, '_ordinary_history_inputs', None)
    if cache is None:
        cache = context._ordinary_history_inputs = {}
    if key not in cache:
        cache[key] = copy.deepcopy(_ordinary_source_history_uncached(root, task))
    return copy.deepcopy(cache[key])


def _ordinary_source_history_uncached(root, task):
    """Immutable provenance only; old QA never becomes a new communication gate."""
    events = w.read_jsonl(Path(root) / w.WORKFLOW_EVENTS); previous = ''; own = []
    for event in events:
        require(event.get('previous_event_hash', '') == previous
                and event.get('event_hash') == w.sha256_value({k: v for k, v in event.items() if k != 'event_hash'}),
                'intact original workflow hash chain required')
        previous = event['event_hash']
        if event.get('task_id') == task: own.append(event)
    require(own and own[0].get('state') == 'planned' and not any(e.get('state') == 'closed' for e in own),
            'existing open original task history required; no closed goal reopening')
    previous = ''
    for row in w.read_jsonl(w.receipts_path(root, task)):
        require(row.get('task_id') == task and row.get('previous_hash', '') == previous
                and row.get('receipt_hash') == w.sha256_value(w._receipt_payload_for_hash(row)),
                'intact original receipt hash chain required')
        previous = row['receipt_hash']
    return own


def _ordinary_original_task(root, snapshot, frozen, history):
    """Legacy CLI init binds the task; never add an identity to frozen bytes."""
    task = w.validate_task_id(snapshot.get('task_id'))
    if 'task_id' in frozen:
        require(frozen['task_id'] == task, 'explicit original contract task cannot change')
        return task
    # Only the original committed init can supply an omitted legacy identity.
    # A caller snapshot or a later transport record cannot create this binding.
    stored = w.read_json(w.snapshot_path(root, task))
    first = history[0]
    detail = first.get('details', {})
    original = detail.get('goal_delivery', {})
    fields = ('primary_owner', 'producer_departments', 'authorized_scope',
              'human_authorization', 'required_execution_actions')
    require(stored.get('task_id') == first.get('task_id') == task
            and first.get('state') == 'planned'
            and stored.get('current_state') == snapshot.get('current_state')
            and stored.get('current_state') not in w.TERMINAL_STATES
            and bool(detail.get('request_hash'))
            and stored.get('request_hash') == snapshot.get('request_hash') == detail['request_hash']
            and stored.get('goal_contract') == snapshot.get('goal_contract') == detail.get('goal_contract')
            and all(e.get('details', {}).get('goal_contract', detail['goal_contract']) == detail['goal_contract']
                    for e in history)
            and all(original.get(k) == stored.get('goal_delivery', {}).get(k) == frozen.get(k) for k in fields),
            'legacy task requires exact original init/frozen pin, current owner, authority and scope')
    auth = frozen.get('human_authorization', {})
    pin = original.get('authorization_pin')
    source = doc(root, pin)
    message = source.get('message', {})
    require(isinstance(auth, dict) and pin['path'] == auth.get('evidence_path')
            and stored.get('goal_delivery', {}).get('authorization_pin') == pin
            and auth.get('executor') == frozen.get('primary_owner')
            and auth.get('scope') in frozen.get('authorized_scope', [])
            and source.get('source_thread_id') == auth.get('source_thread_id')
            and message.get('type') == 'userMessage' and message.get('id') == auth.get('message_id')
            and any(c.get('type') == 'text' and str(c.get('text', '')).strip()
                    for c in message.get('content', []) if isinstance(c, dict)),
            'legacy task requires intact original real human authorization')
    return task


def daily_reply_directory(task_id, action_id):
    """One durable original transport key, not a task/workflow or new ledger."""
    w.validate_task_id(task_id)
    require(isinstance(action_id, str) and action_id.strip(), 'exact daily knowledge action required')
    return DAILY_REPLY_ROOT + '/' + task_id + '/' + w.sha256_value([task_id, action_id])


def daily_knowledge_source(root, snapshot, request):
    """Read genuine declared source + committed intake; never invent a goal."""
    marker = request.get('daily_received_knowledge')
    if marker is None:
        return None
    import department_autonomy as a
    import result_coordination as rc
    require(isinstance(marker, dict) and set(marker) == {'schema', 'identity', 'received_record_id'}
            and marker['schema'] == 'received-declared-daily-knowledge/v1', 'exact received daily knowledge source schema required')
    identity = rc.exact_identity(marker['identity'])
    require(marker['identity'] == identity and not snapshot
            and request.get('task_id') == identity['task_id']
            and request.get('sender_department') == ROLE
            and request.get('target_department') == identity['sender_department'],
            'original daily producer is the knowledge recipient, never a substitute goal or actor')
    source = a.scheduled_delivery_source(root, identity)
    require(source is not None and source.get('local_delivery_only') is True
            and source.get('external_upload_authorized') is False and source.get('fees_authorized') is False,
            'existing declared local daily authority required; no release or fee grant')
    lane = rc.result_lane(root, identity)  # Real declaration/automation/READY/native/UTF8 still checked.
    original = rows(root, identity)
    queued = [r for r in original if r.get('event') == 'notification_queued']
    require(len(queued) == 1 and lane.get('target_department') in {HQ, ROLE}, 'one frozen original daily delivery required')
    intake = _committed_intake(root, {**identity, 'coordinator_role': ROLE,
                                      'received_record_id': marker['received_record_id']})
    require(intake.get('routine_delegation') == SOURCE and intake.get('handling_actor') == ROLE
            and intake.get('target_department') == queued[0].get('target_department')
            and intake.get('source_mode') == queued[0].get('source_mode') == 'scheduled_run'
            and intake.get('source_automation_id') == queued[0].get('source_automation_id') == source['automation_id'],
            'actual own committed receipt and unchanged frozen daily receiver/source required')
    box = doc(root, queued[0]['outbox'])
    scope = box.get('owner_authorization', {}).get('scope')
    require(isinstance(scope, str) and scope.strip() and request.get('scope') == scope,
            'exact original outbox authority scope required; no fabricated business scope')
    for key in ('owner_direct_authorization', 'owner_native_source'):
        doc(root, source.get(key))
    return {'declared_source': source, 'original_outbox': queued[0]['outbox'],
            'identity': identity, 'received_record_id': intake['record_id'],
            'committed_receipt_sha256': w.sha256_value(intake), 'scope': scope,
            'original_professional_owner': identity['sender_department'],
            'external_permission_issued': False, 'knowledge_only': True}


def _hq_original_queued_intake(root, snapshot, request, goal, *, require_pending=True):
    """Exact HQ transport for queued original results; never an execution grant."""
    import result_coordination as rc
    source = doc(root, request.get('hq_pending_result_source'))
    require(source.get('schema') == 'hq-original-queued-result-intake/v1'
            and source.get('goal_contract') == snapshot.get('goal_contract')
            and source.get('routine_delegation') == SOURCE
            and source.get('task_id') == snapshot.get('task_id') == request.get('task_id')
            and source.get('scope') == request.get('scope')
            and source.get('action_id') == request.get('action_id')
            and request.get('sender_department') == HQ and request.get('target_department') == ROLE,
            'exact authentic HQ original-result intake coordination source required')
    human_pin = {'path':'reports/local-department-system-repair-20261030-v1/AUTONOMOUS-DELIVERY-REPAIR-20261104-v1/ACTUAL-OWNER-DELEGATION-SOURCE.json',
                 'sha256':'82f03e76d785bef3dd866ee7128b32c2d360a3ba08aff39faa071e37e4e714ec', 'size': w.safe_path(root,'reports/local-department-system-repair-20261030-v1/AUTONOMOUS-DELIVERY-REPAIR-20261104-v1/ACTUAL-OWNER-DELEGATION-SOURCE.json').stat().st_size}
    require(source.get('owner_delegation') == human_pin, 'exact actual human continuation source pin required')
    human = doc(root, human_pin)
    require(human.get('schema') == 'actual-first-party-owner-directive/v1'
            and human.get('role') == 'human' and human.get('source') == 'first_party_read_thread'
            and human.get('project_root') == str(Path(root).resolve())
            and human.get('source_thread_id') == w.department_registry(root)[HQ]['chat_binding']['task_id']
            and human.get('source_turn_id') and human.get('message_id')
            and all(word in ''.join(x.get('text','') for x in human.get('original_message',[]) if x.get('type')=='text')
                    for word in ('修复', '没完成', '继续', '授权')),
            'actual original human continuation delegation required')
    original = doc(root, source.get('original_hq_request'))
    require(all(original.get(k) == request.get(k) for k in ('task_id', 'scope', 'sender_department', 'target_department'))
            and original.get('sender_department') == HQ and original.get('target_department') == ROLE
            and w.file_digest(root, original.get('payload',{}).get('path','')) == original.get('payload')
            and original.get('payload_sha256') == original['payload']['sha256'],
            'unchanged original HQ request and payload required')
    body = w.safe_path(root, original['payload']['path']).read_text()
    start = body.find('\n[')
    require(start >= 0, 'original result identity list required')
    try:
        recorded, _ = json.JSONDecoder().raw_decode(body[start+1:])
    except (TypeError, ValueError):
        require(False, 'valid original result identity list required')
    results = source.get('results')
    require(isinstance(recorded, list) and isinstance(results, list) and 1 <= len(results) <= 8,
            'bounded original queued results required')
    seen = set()
    for entry in results:
        require(isinstance(entry, dict) and set(entry) == {'identity','outbox'}, 'exact result and outbox pin required')
        identity = rc.exact_identity(entry['identity']); key = tuple(identity[k] for k in rc.IDENTITY_FIELDS)
        require(key not in seen and identity['task_id'] == snapshot['task_id']
                and identity['sender_department'] in goal.get('producer_departments', [])
                and any(isinstance(old, dict) and old.get('identity') == identity and old.get('outbox') == entry['outbox'] for old in recorded),
                'unique original producer result in actual HQ source required')
        seen.add(key); queued = rc._validate_queued(root, identity); route = rc.result_lane(root, identity)
        require(queued.get('outbox') == entry['outbox'] and w.file_digest(root, entry['outbox'].get('path','')) == entry['outbox']
                and queued.get('target_department') == ROLE and route.get('target_department') == ROLE
                and (not require_pending or rc._received_delivery(root, identity, route) is None),
                'one unreceived exact frozen original queue to current chief required')
    text = ('task_id=' + request['task_id'] + '\nscope=' + request['scope'] + '\naction_id=' + request['action_id']
            + '\nsender_department=operations\ntarget_department=operations-assistant\n'
            + '只按原正常入口逐项核验并收取以下既有结果；已收只读回，不重复收取。'
              '不得执行生产、发布、费用或新增业务动作。\n'
            + json.dumps(results, ensure_ascii=False, sort_keys=True, separators=(',', ':')) + '\n')
    require(w.safe_path(root, request['payload']['path']).read_text() == text,
            'exact nonexecuting canonical original-result payload required')
    return source


def ordinary_message_route(root, snapshot, request):
    """Current owner-delegated communication, separate from old execution actors."""
    import department_autonomy as a
    import goal_delivery_runtime as g
    sender, target = request.get('sender_department'), request.get('target_department')
    if request.get('action_class') != 'thread_message' or ROLE not in {sender, target}:
        return None
    if request.get('result_notification') is not None or request.get('result_identity') is not None:
        return None  # Formal result delivery retains its own authenticated transport.
    require(authority(root) is not None, 'genuine current chief owner delegation required')
    a.authority(root)
    require(request.get('routine_delegation', SOURCE) == SOURCE
            and (sender != ROLE or request.get('routine_delegation') == SOURCE),
            'explicit authentic current chief source required; caller labels are not delegation')
    require(request.get('delivery_mode') == 'official_native_queue' and not request.get('assignment_record_required') and not any(request.get(k) for k in (
        'authorization_changes', 'approval_id', 'consume_approval', 'execution_request', 'permission_issued',
        'production_write_allowed', 'qa_verdict', 'result_notification', 'routine_decision_reply')),
        'ordinary communication cannot assign a task, impersonate a receipt or issue execution authority')
    daily = daily_knowledge_source(root, snapshot, request)
    if daily is not None:
        owner = daily['original_professional_owner']
        purpose = DAILY_KNOWLEDGE_PURPOSE
        goal = {}
    else:
        frozen = doc(root, snapshot.get('goal_contract'))
        require(snapshot.get('current_state') not in w.TERMINAL_STATES
                and all(snapshot.get('goal_delivery', {}).get(k) == frozen.get(k) for k in
                    ('primary_owner', 'producer_departments', 'authorized_scope', 'human_authorization', 'required_execution_actions')),
                'supplied original state and frozen participants cannot change')
        history = ordinary_source_history(root, snapshot['task_id'])
        original_task = _ordinary_original_task(root, snapshot, frozen, history)
        snapshot = g.restore_goal(root, snapshot); goal = snapshot.get('goal_delivery', {})
        require(snapshot.get('task_id') == request.get('task_id') == original_task
                and snapshot.get('current_state') not in w.TERMINAL_STATES
                and all(goal.get(k) == frozen.get(k) for k in ('primary_owner', 'producer_departments',
                         'authorized_scope', 'human_authorization', 'required_execution_actions'))
                and request.get('scope') in goal.get('authorized_scope', [])
    ,
                'active unchanged original task, authority, owner, scope and intact history required')
        owner = goal.get('primary_owner')
        if sender == ROLE:
            require(target == owner and a.professional(root, target), 'ordinary followthrough returns only to the real original professional owner')
            purpose = 'current_chief_original_owner_followthrough'
        elif sender == HQ and target == ROLE:
            _hq_original_queued_intake(root, snapshot, request, goal)
            purpose = 'hq_original_queued_result_intake_followthrough'
        else:
            require(target == ROLE and sender not in a.ASSISTANTS
                    and sender in {owner, *goal.get('producer_departments', [])} and a.professional(root, sender),
                    'original professional report only; retired actors cannot become current senders')
            purpose = 'original_professional_report_to_current_chief'
    payload = request.get('payload')
    require(isinstance(payload, dict) and w.file_digest(root, payload.get('path', '')) == payload
            and request.get('payload_sha256') == payload['sha256'], 'unchanged exact ordinary message bytes required')
    body = w.safe_path(root, payload['path']).read_text()
    keys = ('task_id', 'scope', 'action_id', 'sender_department', 'target_department') if sender == ROLE else ('task_id', 'scope')
    require(all(re.search(r'(?m)^' + key + '=' + re.escape(str(request.get(key, ''))) + r'\s*$', body) for key in keys),
            'original task/scope and real sender/receiver/action payload relation required')
    if daily is not None:
        require(all(re.search(r'(?m)^' + key + '=' + re.escape(value) + r'\s*$', body) for key, value in
                    {'received_record_id': daily['received_record_id'],
                     'result_sha256': daily['identity']['result_sha256'], 'no_execution_permission': 'true'}.items()),
                'receipt knowledge payload must retain original receipt/result and no execution grant')
    registry = w.department_registry(root); source, dest = [registry[x]['chat_binding'] for x in (sender, target)]
    require(source.get('project_id') == dest.get('project_id') == request.get('source_project_id') == request.get('target_project_id') == a.PROJECT
            and Path(source.get('cwd', '')).resolve() == Path(dest.get('cwd', '')).resolve() == Path(root).resolve()
            and all(request.get(k) == dest[v] for k, v in {'target_thread_id': 'task_id', 'target_thread_title': 'title',
                'target_cwd': 'cwd', 'target_sidebar_section_id': 'sidebar_section_id'}.items())
            and registry[sender].get('new_dispatch_enabled') is True and registry[target].get('new_dispatch_enabled') is True,
            'exact current fixed sender/receiver/project/directory/sidebar required; no role alias')
    return {'mode': a.MODE, 'purpose': purpose, 'source': payload, 'report': payload, 'scope': request['scope'],
            'sender_department': sender, 'target_department': target, 'owner_source': SOURCE,
            **({'daily_received_source': daily} if daily is not None else {'goal_contract': snapshot['goal_contract']}),
            'original_professional_owner': owner,
            'historical_responsible_assistant_unchanged': goal.get('responsible_assistant'),
            'external_permission_issued': False, 'business_producer_added': False}


def ordinary_message_facts(root, snapshot, request, route):
    """Fresh sending facts are checked at policy, not written into old sources."""
    import department_autonomy as a
    import goal_delivery_runtime as g
    require(route.get('purpose') in ORDINARY_PURPOSES and ordinary_message_route(root, snapshot, request) == route,
            'same authentic ordinary coordination route required')
    observed = w._parse_observed_at(request.get('live_observed_at')); now = dt.datetime.now(dt.timezone.utc)
    require(observed is not None and 0 <= (now - observed).total_seconds() <= 300,
            'fresh ordinary sender/receiver observation required before queue; preserve old report bytes')
    registry = w.department_registry(root)
    pins = {}
    for key, role in (('actual_sender_state', request['sender_department']), ('actual_target_state', request['target_department'])):
        page = g._collaboration_native(root, request.get(key)); fixed = registry[role]['chat_binding']
        require(all(page.get('thread', {}).get(k) == fixed[v] for k, v in
                    {'id': 'task_id', 'title': 'title', 'cwd': 'cwd', 'hostId': 'host_id'}.items())
                and page['thread'].get('kind') == 'codex' and page['thread'].get('status', {}).get('type') in {'active', 'idle', 'notLoaded'} and page.get('turns')
                and not page['turns'][0].get('error') and page['turns'][0].get('status') in {'completed', 'inProgress', 'pending'}
                and type(page['turns'][0].get('startedAt')) in {int, float}
                and page['turns'][0]['startedAt'] <= now.timestamp(),
                'real current fixed native identity/turn; unknown, failed or substituted role rejected')
        pins[key] = request[key]
    return {**({'daily_received_source': route['daily_received_source']} if route.get('daily_received_source') else
               {'goal_contract': route['goal_contract']}), 'routine_delegation': SOURCE, 'payload': request['payload'],
            'live_observed_at': request['live_observed_at'], **pins, 'external_permission_issued': False}


def message_route(root, snapshot, request):
    source = request.get('routine_decision_reply')
    if source is None:
        return ordinary_message_route(root, snapshot, request)
    import result_coordination as rc
    require(request.get('action_class') == 'thread_message' and not request.get('assignment_record_required')
            and not any(request.get(k) for k in ('authorization_changes', 'approval_id', 'consume_approval', 'execution_request')),
            'ordinary decision reply is transport only')
    identity = rc.exact_identity(source)
    selected = [r for r in rows(root, identity) if r.get('event') == 'controller_decision'
                and r.get('record_id') == source.get('decision_record_id')]
    require(len(selected) == 1 and selected[0].get('routine_delegation') == SOURCE,
            'one exact committed delegated decision for this reply required')
    row = selected[0]
    rc._committed_result(root, row)
    role = request.get('sender_department')
    require(role == row.get('coordinator_role') and actor_allowed(root, identity, row['target_department'], role)
            and request.get('task_id') == identity['task_id'] == snapshot.get('task_id')
            and request.get('scope') == row['scope'] and request.get('target_department') == row['next_owner'],
            'real decision actor/task/scope/original next owner required')
    registry = w.department_registry(root)
    sender, target = registry[role]['chat_binding'], registry[request['target_department']]['chat_binding']
    require(sender['project_id'] == target['project_id'] == request.get('source_project_id') == request.get('target_project_id')
            and Path(sender['cwd']).resolve() == Path(target['cwd']).resolve() == Path(root).resolve()
            and all(request.get(k) == target[v] for k, v in {'target_thread_id': 'task_id', 'target_thread_title': 'title',
                    'target_cwd': 'cwd', 'target_sidebar_section_id': 'sidebar_section_id'}.items()),
            'exact fixed current actor/receiver/project/cwd required')
    payload = request.get('payload')
    require(w.file_digest(root, payload.get('path', '')) == payload and payload['sha256'] == request.get('payload_sha256'),
            'exact decision reply payload required')
    body = w.safe_path(root, payload['path']).read_text()
    require(all(re.search(r'(?m)^' + key + '=' + re.escape(str(request[key])) + r'\s*$', body)
                for key in ('task_id', 'scope', 'action_id', 'sender_department', 'target_department'))
            and row['result_sha256'] in body and row['decision_source']['path'] in body
            and row['decision_source']['sha256'] in body,
            'reply must bind actual original result and decision, not a new generic approval')
    return {'mode': 'department_autonomous_delivery_v1', 'purpose': 'routine_decision_direct_reply',
            'source': payload, 'scope': row['scope'], 'sender_department': role,
            'target_department': row['next_owner'], 'decision_record_id': row['record_id'],
            'owner_source': SOURCE, 'external_permission_issued': False}




def _pre_goal_metadata_dependency(root, request, fixed, old_key, old_body):
    """One real newly completed refusal + actual repair, not a replayed heartbeat."""
    import goal_delivery_runtime as g
    import department_rotation as rotation
    source=request['pre_goal_dependency_release']
    require(isinstance(source,dict) and set(source)=={'metadata_journal','actual_blocked_native','blocked_turn_id',
        'blocked_user_message_id','blocked_ACK_message_id','blocked_final_message_id'}, 'exact real dependency-release source only')
    require(source['metadata_journal'] in rotation._SIDEBAR_METADATA_SUCCESSORS,
            'actual adopted current metadata journal, never a caller release flag')
    edge=rotation._sidebar_metadata_edge(root,source['metadata_journal'],request['target_department'])
    journal=doc(root,source['metadata_journal'])
    require(edge is not None and len(journal['changes'])==1 and edge['after']==fixed['sidebar_section_id']
            and journal.get('source_dependency')==source['actual_blocked_native'],
            'this actual same-role metadata repair must release this exact original refusal')
    old_directory=w.safe_path(root,DAILY_REPLY_ROOT+'/pre-goal/'+old_key)
    old_intent=doc(root,w.file_digest(root,str((old_directory/'pre-goal-resume-intent.json').relative_to(root))))
    old_request=doc(root,old_intent['request']);old_result=doc(root,w.file_digest(root,str((old_directory/'actual-return.json').relative_to(root))))
    old_route=old_intent.get('route',{})
    require(old_route.get('pre_goal_key')==old_key and old_route.get('body')==old_body
            and old_request.get('pre_goal_source')==request['pre_goal_source']
            and old_request.get('pre_goal_dependency_release') is None
            and old_request.get('task_id') is None and old_request.get('scope') is None
            and all(old_request.get(k)==request.get(k)for k in ('source_automation_id','source_turn_id','source_message_id',
                'sender_department','target_department','target_thread_id','source_project_id','target_project_id'))
            and old_request.get('target_sidebar_section_id')==edge['before']
            and doc_bytes(root,old_request['payload'])==old_body.encode()
            and old_result.get('state')=='official_queue_accepted_not_received',
            'original consumed intent/body/key and exact actual queue effect required; do not replay old recovery')
    policy=old_intent.get('policy',{});rows=[p for p in w.read_jsonl(Path(root)/w.POLICY_DECISIONS)if p.get('decision_id')==policy.get('decision_id')]
    require(rows==[policy] and policy.get('pre_goal_key')==old_key and policy.get('status')=='allow'
            and policy.get('routing_status')=='routing_allowed' and policy.get('payload_sha256')==old_request['payload_sha256'],
            'actual immutable original pre-goal policy and payload binding')
    native=g._collaboration_native(root,source['actual_blocked_native'])
    require(all(native.get('thread',{}).get(k)==fixed[v] for k,v in
        {'id':'task_id','title':'title','cwd':'cwd','hostId':'host_id'}.items()), 'exact current original professional refusal identity')
    selected=[t for t in native.get('turns',[])if t.get('id')==source['blocked_turn_id']]
    require(len(selected)==1 and selected[0].get('status')=='completed' and not selected[0].get('error'), 'genuine newly completed refusal turn required')
    turn=selected[0];users=[m for m in turn.get('items',[])if m.get('id')==source['blocked_user_message_id'] and m.get('type')=='userMessage']
    acks=[m for m in turn.get('items',[])if m.get('id')==source['blocked_ACK_message_id'] and m.get('type')=='agentMessage' and m.get('text','').strip()]
    finals=[m for m in turn.get('items',[])if m.get('id')==source['blocked_final_message_id'] and m.get('type')=='agentMessage' and 'STALE_SIDEBAR_BINDING'in m.get('text','')]
    require(len(users)==len(acks)==len(finals)==1 and ''.join(x.get('text','')for x in users[0].get('content',[])if x.get('type')=='text').encode()==old_body.encode(),
            'real original same UTF8 user/nonempty ACK/new sidebar refusal, never human or business ACK fabrication')
    queued=doc(root,w.file_digest(root,str((old_directory/'native-queue-result.json').relative_to(root))))
    finish=w._parse_observed_at(queued.get('finished_at'));start=w._parse_observed_at(queued.get('started_at'));when=w._parse_observed_at(journal.get('observed_at'))
    reserved=w._parse_observed_at(old_intent.get('reserved_at'));checked=w._parse_observed_at(policy.get('checked_at'))
    require(queued.get('policy_decision_id')==policy['decision_id'] and queued.get('thread_id')==fixed['task_id']
            and queued.get('payload_sha256')==old_request['payload_sha256'] and queued.get('exit_code')==0
            and queued.get('stdout')==f"Queued message {old_result['effect']['message_id']} for thread {fixed['task_id']}.\n"
            and not queued.get('stderr') and all(x is not None for x in (start,finish,reserved,checked,when))
            and type(turn.get('startedAt'))in {int,float} and type(turn.get('completedAt'))in {int,float}
            and checked<=reserved<=start<=finish and (start-checked).total_seconds()<=300
            and start.timestamp()<turn['startedAt']+1 and turn['startedAt']<=turn['completedAt']<=when.timestamp()
            and finish.timestamp()<turn['completedAt']+1,
            'actual original queue, new refusal completion and later metadata repair chronology')
    key=w.sha256_value([old_key,turn['id'],source['metadata_journal']['sha256']])
    body=('source_automation_id='+request['source_automation_id']+'\nsource_turn_id='+request['source_turn_id']
        +'\nsource_message_id='+request['source_message_id']+'\ndependency_blocked_turn_id='+turn['id']
        +'\nsender_department='+ROLE+'\ntarget_department='+request['target_department']+'\n'
        +'本次真实新依赖STALE_SIDEBAR_BINDING已按同线程元数据CAS解除。原已消费恢复键不重放；'
        +'本接续仅绑定该新完成阻断轮和下面真实metadata journal，不是新heartbeat、daytask或业务授权。\n'
        +'metadata_journal='+source['metadata_journal']['path']+' SHA256='+source['metadata_journal']['sha256']+'\n'
        +'请原专业窗口鲜读5分钟内单目标快照，再自检并沿原heartbeat合法每日入口继续；'
        +'只有原专业入口决定task/scope。查已有效果并保持每日一首、去重、真实音频/catalog/verify、'
        +'Chrome只读、不存秘密、不装依赖、不发布、不费用及所有原边界。\n')
    return key, DAILY_REPLY_ROOT+'/pre-goal/'+key, body



def pre_goal_context(root, request, *, payload_required=True, fresh=False, recovering=False):
    """An existing declared heartbeat may resume before its owner creates a goal."""
    import goal_delivery_runtime as g
    import department_autonomy as a
    authority(root); a.authority(root)
    require(request.get('task_id') is None and request.get('scope') is None
            and request.get('action_class') == 'thread_message'
            and request.get('sender_department') == ROLE
            and request.get('routine_delegation') == SOURCE
            and request.get('delivery_mode') == 'official_native_queue'
            and not any(request.get(k) for k in ('authorization_changes','approval_id','consume_approval',
                'execution_request','permission_issued','production_write_allowed','assignment_record_required',
                'qa_verdict','result_notification','routine_decision_reply')),
            'pre-goal is original heartbeat transport only; no task/scope or execution grant')
    w.validate_task_id(request.get('action_id'))
    role = request.get('target_department'); registry = w.department_registry(root)
    require(a.professional(root, role) and registry[role].get('new_dispatch_enabled') is True,
            'original active professional heartbeat owner required')
    fixed = registry[role]['chat_binding']; sender = registry[ROLE]['chat_binding']
    require(fixed['project_id'] == sender['project_id'] == a.PROJECT
            and Path(fixed['cwd']).resolve() == Path(sender['cwd']).resolve() == Path(root).resolve()
            and all(request.get(k) == v for k,v in {'target_thread_id':fixed['task_id'],
                'source_project_id':a.PROJECT,'target_project_id':a.PROJECT}.items()),
            'exact original fixed pre-goal project and professional chat required')
    page = g._collaboration_native(root, request.get('pre_goal_source'))
    require(all(page.get('thread',{}).get(k) == fixed[v] for k,v in
                {'id':'task_id','title':'title','cwd':'cwd','hostId':'host_id'}.items())
            and page['thread'].get('kind') == 'codex'
            and all(page['thread'].get(k, a.PROJECT) == a.PROJECT for k in ('project_id','projectId')),
            'original native identity must agree; missing project uses actual inventory, never a guessed value')
    pairs = [(t,m) for t in page.get('turns',[]) for m in t.get('items',[])
             if m.get('id') == request.get('source_message_id')]
    require(len(pairs) == 1 and pairs[0][0].get('id') == request.get('source_turn_id')
            and pairs[0][0].get('status') == 'completed' and not pairs[0][0].get('error')
            and pairs[0][1].get('type') == 'userMessage', 'one real completed original heartbeat turn required')
    turn,message = pairs[0]; text = ''.join(x.get('text','') for x in message.get('content',[]) if x.get('type')=='text')
    require('<!DOCTYPE' not in text.upper() and '<!ENTITY' not in text.upper(), 'plain native heartbeat XML only')
    # The real heartbeat instructions contain literal CLI placeholders such as
    # <作品ID>; they are opaque text, not XML child elements.
    heartbeat = re.fullmatch(r'\s*<heartbeat>\s*<automation_id>([^<>]+)</automation_id>\s*'
        r'<current_time_iso>([^<>]+)</current_time_iso>\s*<instructions>([\s\S]+)</instructions>\s*</heartbeat>\s*', text)
    automation = request.get('source_automation_id')
    require(heartbeat is not None and heartbeat[1] == automation and bool(heartbeat[3].strip()),
            'complete original declared heartbeat envelope and nonempty opaque instructions required')
    declared = [x for x in w.read_json(Path(root)/'data/task-contract.json').get('result_handoff_contract',{}).get('scheduled_daily_sources',[])
                if x.get('automation_id') == automation and x.get('department') == role]
    require(len(declared) == 1 and declared[0].get('delivery_model') == a.MODE,
            'one existing unchanged autonomous daily declaration required')
    started = w._parse_observed_at(heartbeat[2])
    now = dt.datetime.now(dt.timezone.utc)
    require(started is not None and started <= now and type(turn.get('startedAt')) in {int,float}
            and abs(turn['startedAt']-started.timestamp()) <= 60
            and type(turn.get('completedAt')) in {int,float} and turn['startedAt'] <= turn['completedAt'] <= now.timestamp()
            and (recovering or started.astimezone(dt.timezone(dt.timedelta(hours=8))).date() == now.astimezone(dt.timezone(dt.timedelta(hours=8))).date()),
            'same real daily heartbeat date and original completion chronology required')
    finals = [m for m in turn.get('items',[]) if m.get('type')=='agentMessage' and 'BLOCKED_CROSS_PROJECT' in m.get('text','')]
    require(len(finals) == 1, 'real original project-context refusal required; do not replay successful or unknown work')
    for path in (Path(root)/'data/workflows').glob('*.json'):
        task = w.read_json(path).get('task_id',''); match = re.fullmatch(declared[0]['task_id_pattern'],task)
        require(recovering or not (match and match.groupdict().get('date') == started.astimezone(dt.timezone(dt.timedelta(hours=8))).strftime('%Y%m%d')),
                'daily goal already exists; resume its real task instead of pre-goal replay')
    key = w.sha256_value([automation,role,fixed['task_id'],turn['id'],message['id']])
    directory = DAILY_REPLY_ROOT + '/pre-goal/' + key
    body = ('source_automation_id='+automation+'\nsource_turn_id='+turn['id']+'\nsource_message_id='+message['id']
            +'\nsender_department='+ROLE+'\ntarget_department='+role+'\n'
            +'原轮项目归属证明已补齐：真实list_threads的projectId与注册表、固定聊天、标题、cwd、host一致。'
            +'read_thread缺project_id不能冒作跨项目；若两个真实视图显式冲突仍停止。\n'
            +'仅恢复所引原heartbeat的同一专业日作业，原指令和全部安全/去重/费用/发布边界保持。'
            +'尚无业务task/scope；仅由原专业每日入口确定它们，不创建替身，不重采已完成成果。\n'
            +'原始来源='+request['pre_goal_source']['path']+' SHA256='+request['pre_goal_source']['sha256']+'\n')
    if request.get('pre_goal_dependency_release') is not None:
        key,directory,body=_pre_goal_metadata_dependency(root,request,fixed,key,body)
    if payload_required:
        payload = request.get('payload'); require(isinstance(payload,dict) and doc_bytes(root,payload) == body.encode()
            and request.get('payload_sha256') == payload['sha256'], 'exact source-derived resume body; no caller additions or production commands')
    if fresh:
        observed = w._parse_observed_at(request.get('live_observed_at'))
        require(observed is not None and 0 <= (now-observed).total_seconds() <= 300, 'fresh current pre-goal observations required')
        inventory = g._collaboration_native(root,request.get('actual_live_inventory'))
        for field,binding in (('actual_sender_state',sender),('actual_target_state',fixed)):
            current = g._collaboration_native(root,request.get(field))
            matches = [x for x in inventory.get('threads',[])+inventory.get('pinnedThreads',[]) if x.get('id')==binding['task_id']]
            require(len(matches)==1 and all(matches[0].get(k)==binding[v] for k,v in
                {'id':'task_id','projectId':'project_id','title':'title','cwd':'cwd','hostId':'host_id'}.items())
                and matches[0].get('status') in {'idle','active'}
                and all(current.get('thread',{}).get(k)==binding[v] for k,v in
                    {'id':'task_id','title':'title','cwd':'cwd','hostId':'host_id'}.items())
                and all(current['thread'].get(k,binding['project_id'])==binding['project_id'] for k in ('project_id','projectId'))
                and current['thread'].get('kind')=='codex' and current['thread'].get('status',{}).get('type') in {'idle','active'}
                and current.get('turns') and type(current['turns'][0].get('startedAt')) in {int,float}
                and current['turns'][0]['startedAt'] <= now.timestamp()
                and current['turns'][0].get('status') in {'completed','inProgress','pending'} and not current['turns'][0].get('error'),
                'fresh actual native and camelCase inventory must agree; unknown is not idle')
        require(all(request.get(k)==fixed[v] for k,v in {'target_thread_title':'title','target_cwd':'cwd',
                'target_sidebar_section_id':'sidebar_section_id'}.items()), 'unchanged current fixed pre-goal target metadata required')
    return {'pre_goal_key':key,'directory':directory,'body':body,'task_id':None,'scope':None,
            'declared_daily':declared[0],'original_native':request['pre_goal_source'],'owner_delegation':SOURCE,
            'external_permission_issued':False,'creates_goal':False}


def doc_bytes(root, pin):
    require(isinstance(pin,dict) and w.file_digest(root,pin.get('path',''))==pin, 'exact immutable message bytes required')
    return w.safe_path(root,pin['path']).read_bytes()


def pre_goal_policy(root, request):
    with w.workflow_lock(root):
        route = pre_goal_context(root,request,fresh=True)
        directory = w.safe_path(root,route['directory'])
        require(not directory.exists(), 'original pre-goal intent/effect exists; read it, never retry blindly')
        rows = [x for x in w.read_jsonl(Path(root)/w.POLICY_DECISIONS) if x.get('pre_goal_key')==route['pre_goal_key']]
        identity = {k:request.get(k) for k in ('task_id','scope','action_id','action_class','source_project_id','target_project_id',
            'target_department','target_thread_id','target_thread_title','target_cwd','target_sidebar_section_id','payload_sha256','delivery_mode')}
        now = dt.datetime.now(dt.timezone.utc)
        for index,row in enumerate(rows):
            require(all(row.get(k)==v for k,v in identity.items()) and row.get('department')==ROLE and row.get('status')=='allow'
                    and row.get('pre_goal_source')==route['original_native'] and row.get('message_policy_generation')==index
                    and row.get('external_permission_issued') is False and w._parse_observed_at(row.get('checked_at')) is not None,
                    'immutable original pre-goal policy lineage required')
            require(w._parse_observed_at(row['checked_at']) <= now and row.get('routing_status')=='routing_allowed'
                    and row.get('routine_delegation')==SOURCE and row.get('approval_id')=='' and row.get('consume_approval') is False
                    and (not row.get('supersedes_message_policy') if index==0 else
                        row.get('supersedes_message_policy')=={'decision_id':rows[index-1]['decision_id'],'sha256':w.sha256_value(rows[index-1])}
                        and w._parse_observed_at(row['checked_at']) > w._parse_observed_at(rows[index-1]['checked_at'])),
                    'one ordered original pre-goal policy lineage; no revival or ambiguous successor')
        if rows and 0 <= (now-w._parse_observed_at(rows[-1]['checked_at'])).total_seconds() <= 300: return rows[-1]
        value={**identity,'department':ROLE,'status':'allow','routing_status':'routing_allowed','checked_at':w.utc_timestamp(),
            'approval_basis':'authenticated_declared_heartbeat_pre_goal_resume','pre_goal_key':route['pre_goal_key'],
            'pre_goal_source':route['original_native'],'routine_delegation':SOURCE,'external_permission_issued':False,
            'approval_id':'','consume_approval':False,'message_policy_generation':len(rows)}
        if rows:value['supersedes_message_policy']={'decision_id':rows[-1]['decision_id'],'sha256':w.sha256_value(rows[-1])}
        value['decision_id']='pol-'+w.sha256_value(value)[:20]
        w.append_jsonl_locked(Path(root)/w.POLICY_DECISIONS,value)
        return value


def pre_goal_prepare(root, request):
    from department_event_dispatcher import native_queue_capability
    pre_goal_context(root,request,fresh=True);native_queue_capability(root)
    keys=('task_id','action_id','action_class','scope','source_project_id','target_project_id','target_department',
        'target_thread_id','target_thread_title','target_cwd','target_sidebar_section_id','payload_sha256','delivery_mode')
    policy,_=w.policy_check(root,department=request['sender_department'],**{k:request.get(k)for k in keys},original_message=request)
    return {'status':'ready_to_queue','policy_decision':policy,'payload':request['payload'],
            'delivery_mode':'official_native_queue','message_sent':False,'external_permission_issued':False,'task_id':None,'scope':None}


def pre_goal_reply(root, request_path):
    from department_event_dispatcher import OfficialQueueTransport
    request=doc(root,w.file_digest(root,request_path)); prepared=pre_goal_prepare(root,request)
    with w.workflow_lock(root):
        route=pre_goal_context(root,request,fresh=True);directory=w.safe_path(root,route['directory'])
        require(not directory.exists(), 'same original pre-goal intent reserved; inspect actual effect')
        directory.mkdir(parents=True)
        intent={'request':w.file_digest(root,request_path),'route':route,'policy':prepared['policy_decision'],
                'reserved_at':w.utc_timestamp(),'message_sent':False,'unknown_until_actual_readback':True}
        w.atomic_write_json(directory/'pre-goal-resume-intent.json',intent)
    effect=OfficialQueueTransport(root,None).enqueue({'thread_id':request['target_thread_id'],'message':route['body'],
        'directory':directory,'payload_sha256':request['payload_sha256'],'policy_decision_id':prepared['policy_decision']['decision_id']})
    result={'state':'official_queue_accepted_not_received','effect':effect,'received':False,'external_permission_issued':False}
    w.atomic_write_json(directory/'actual-return.json',result);return result


def pre_goal_effect(root, request):
    route=pre_goal_context(root,request,recovering=True);directory=w.safe_path(root,route['directory'])
    intent=w.read_json(directory/'pre-goal-resume-intent.json')
    require(intent and doc(root,intent.get('request'))==request and intent.get('route')==route,
            'one original immutable pre-goal intent and request required')
    result=w.read_json(directory/'actual-return.json')
    return {'intent':intent,'actual_result':result,'state':result.get('state','UNKNOWN_NO_RETRY'),
            'received':False,'ACK':'actual original recipient native must be independently observed','external_permission_issued':False}


def reply(root, request_path, directory):
    """Normal policy, durable original effect intent, then one official queue call."""
    import goal_delivery_runtime as g
    import goal_source_recovery as recovery
    from department_event_dispatcher import OfficialQueueTransport
    request_pin = w.file_digest(root, request_path)
    request = doc(root, request_pin)
    if request.get('task_id') is None and request.get('pre_goal_source') is not None:
        return pre_goal_reply(root, request_path)
    snapshot = g.restore_goal(root, w.read_json(w.snapshot_path(root, request['task_id'])))
    route = message_route(root, snapshot, request)
    require(route is not None and request.get('delivery_mode') == 'official_native_queue', 'exact normal routine official reply required')
    destination = w.safe_path(root, directory)
    require(Path(directory).parts[:2] == ('logs', 'handoffs') and not destination.is_symlink(), 'project-owned reply directory required')
    daily = route.get('purpose') == DAILY_KNOWLEDGE_PURPOSE
    decision_id = (route.get('decision_record_id')
                   if not daily and route.get('purpose') == 'routine_decision_direct_reply' else None)
    if daily:
        require(directory == daily_reply_directory(request['task_id'], request['action_id']), 'one original daily reply directory required')
    with w.workflow_lock(root):
        previous = [e for e in w.read_jsonl(Path(root) / w.WORKFLOW_EVENTS)
                    if e.get('task_id') == request['task_id']
                    and (e.get('details', {}).get('routine_decision_reply_intent', {}).get('action_id') == request['action_id']
                         or decision_id is not None and e.get('details', {}).get('routine_decision_reply_intent', {}).get('decision_record_id') == decision_id)]
        require(not previous and not destination.exists(), 'existing/unknown reply effect: read original intent, never resend')
    prepared = recovery.prepare_message(root, request)
    require(prepared.get('status') == 'ready_to_queue', 'normal actual fixed-target reply preparation required: ' + str(prepared.get('status')))
    with w.workflow_lock(root):
        # Recheck inside the serial effect boundary; preparation does not own intent.
        message_route(root, g.restore_goal(root, w.read_json(w.snapshot_path(root, request['task_id']))), request)
        previous = [e for e in w.read_jsonl(Path(root) / w.WORKFLOW_EVENTS)
                    if e.get('task_id') == request['task_id']
                    and (e.get('details', {}).get('routine_decision_reply_intent', {}).get('action_id') == request['action_id']
                         or decision_id is not None and e.get('details', {}).get('routine_decision_reply_intent', {}).get('decision_record_id') == decision_id)]
        require(not previous and not destination.exists(), 'reply intent already exists; inspect its actual effect')
        destination.mkdir(parents=True)
        w.atomic_write_json(destination / 'normal-preparation.json', prepared)
        intent = {'action_id': request['action_id'], 'request': request_pin,
                  'decision_record_id': route.get('decision_record_id'), 'ordinary_message_source': route.get('daily_received_source', route.get('goal_contract')), 'routine_delegation': SOURCE, 'directory': directory,
                  'payload': request['payload'], 'policy_decision_id': prepared['policy_decision']['decision_id'],
                  'handling_actor': request['sender_department'], 'target_department': request['target_department']}
        if daily:
            # Existing reply intent/result files are transport facts, not a synthetic business workflow.
            w.atomic_write_json(destination / 'routine-reply-intent.json', intent)
        else:
            w.append_workflow_event(root, request['task_id'], snapshot['current_state'],
                                    {'routine_decision_reply_intent': intent, 'external_permission_issued': False})
    effect = OfficialQueueTransport(root, None).enqueue({'thread_id': request['target_thread_id'],
        'message': w.safe_path(root, request['payload']['path']).read_text(), 'directory': destination,
        'payload_sha256': request['payload_sha256'], 'policy_decision_id': intent['policy_decision_id']})
    result = {'state': 'official_queue_accepted_not_received', 'effect': effect, 'intent': intent,
              'received': False, 'external_permission_issued': False}
    w.atomic_write_json(destination / 'actual-return.json', result)
    return result


def _daily_reply_intent_readback(root, intent, request, route):
    """Authenticate file-only daily intent against its actual normal policy."""
    require(route.get('purpose') == DAILY_KNOWLEDGE_PURPOSE
            and intent.get('directory') == daily_reply_directory(request['task_id'], request['action_id'])
            and intent.get('ordinary_message_source') == route['daily_received_source']
            and intent.get('payload') == request['payload'] and intent.get('routine_delegation') == SOURCE
            and intent.get('handling_actor') == request['sender_department'] == ROLE
            and intent.get('target_department') == request['target_department'],
            'unchanged authenticated daily intent/source/payload/actor and original directory required')
    policies = [p for p in w.read_jsonl(Path(root) / w.POLICY_DECISIONS)
                if p.get('decision_id') == intent.get('policy_decision_id')]
    fields = ('task_id', 'action_id', 'action_class', 'scope', 'source_project_id', 'target_project_id',
              'target_department', 'target_thread_id', 'target_thread_title', 'target_cwd',
              'target_sidebar_section_id', 'payload_sha256')
    require(len(policies) == 1 and all(policies[0].get(k) == request.get(k) for k in fields)
            and policies[0].get('department') == ROLE and policies[0].get('status') == 'allow'
            and policies[0].get('external_permission_issued') is False
            and not policies[0].get('consume_approval') and not policies[0].get('approval_id')
            and policies[0].get('routine_message_source', {}).get('daily_received_source') == route['daily_received_source'],
            'real exact normal daily policy and committed source required; no caller grant')
    directory = w.safe_path(root, intent['directory'])
    prepared = w.read_json(directory / 'normal-preparation.json')
    require(prepared.get('status') == 'ready_to_queue' and prepared.get('policy_decision') == policies[0]
            and prepared.get('payload') == request['payload'], 'original normal prepared policy/payload required')
    native = w.read_json(directory / 'native-queue-intent.json')
    if native:
        started = w._parse_observed_at(native.get('started_at'))
        checked = w._parse_observed_at(policies[0].get('checked_at'))
        require(native.get('thread_id') == request['target_thread_id']
                and native.get('payload_sha256') == request['payload_sha256']
                and native.get('policy_decision_id') == intent['policy_decision_id']
                and native.get('transport') == 'official_codex_queue'
                and started is not None and checked is not None
                and checked <= started <= dt.datetime.now(dt.timezone.utc),
                'real original daily transport intent identity/hash/policy/time required')
    return native


def reply_effect(root, task_id, action_id):
    """Read original effect, including unknown; never sends or changes a receipt."""
    events = w.read_jsonl(Path(root) / w.WORKFLOW_EVENTS,
        where={'task_id': task_id, ('details','routine_decision_reply_intent','action_id'): action_id})
    daily_path = w.safe_path(root, daily_reply_directory(task_id, action_id)) / 'routine-reply-intent.json'
    require(len(events) + int(daily_path.exists()) == 1, 'one original routine reply intent required')
    intent = json.loads(daily_path.read_text()) if daily_path.exists() else events[0]['details']['routine_decision_reply_intent']
    require(intent.get('action_id') == action_id, 'original reply action cannot change')
    request = doc(root, intent['request'])
    import goal_delivery_runtime as g
    route = message_route(root, g.restore_goal(root, w.read_json(w.snapshot_path(root, task_id))), request)
    require(request.get('task_id') == task_id and request.get('action_id') == action_id,
            'original reply request identity required')
    native = _daily_reply_intent_readback(root, intent, request, route) if daily_path.exists() else None
    path = w.safe_path(root, intent['directory']) / 'native-queue-result.json'
    if not path.exists():
        return {'state': 'effect_unknown', 'repeat_allowed': False, 'intent': intent}
    result = json.loads(path.read_text())
    if daily_path.exists():
        finished = w._parse_observed_at(result.get('finished_at'))
        require(native and all(result.get(k) == native.get(k) for k in native)
                and finished is not None and w._parse_observed_at(native['started_at']) <= finished <= dt.datetime.now(dt.timezone.utc),
                'original complete daily transport chronology and intent fields required')
    match = re.fullmatch(r'Queued message ([0-9a-f-]{36}) for thread ([0-9a-f-]{36})\.\s*', result.get('stdout', ''))
    require(result.get('exit_code') == 0 and match and match[2] == request['target_thread_id']
            and result.get('payload_sha256') == request['payload_sha256']
            and result.get('policy_decision_id') == intent['policy_decision_id'], 'original exact queue effect differs; do not resend')
    return {'state': 'official_queue_accepted_not_received', 'message_id': match[1], 'intent': intent,
            'received': False, 'repeat_allowed': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['authority', 'preflight', 'reply', 'reply-effect', 'decision-claim-check', 'decision-claim', 'pre-goal-check', 'pre-goal-effect'])
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--input')
    parser.add_argument('--directory')
    parser.add_argument('--task-id')
    parser.add_argument('--action-id')
    args = parser.parse_args()
    if args.command == 'authority':
        result = authority(args.root)
    elif args.command in {'pre-goal-check','pre-goal-effect'}:
        request=doc(args.root,w.file_digest(args.root,args.input))
        result=pre_goal_context(args.root,request,payload_required=False) if args.command=='pre-goal-check' else pre_goal_effect(args.root,request)
    elif args.command in {'decision-claim-check','decision-claim'}:
        import result_coordination as rc
        request=json.loads(w.safe_path(args.root,args.input).read_text())
        result=decision_claim_preflight(args.root,request)
        if args.command=='decision-claim':
            store=rc.CoordinationStore(args.root)
            try:result=store.claim_decision(rc.exact_identity(request),request['coordinator_role'],request['coordinator_owner'],request['request_id'],request['received_record_id'],request['recovery_reason'],request.get('ttl_seconds',900))
            finally:store.close()
    elif args.command == 'reply':
        result = reply(args.root, args.input, args.directory)
    elif args.command == 'reply-effect':
        result = reply_effect(args.root, args.task_id, args.action_id)
    else:
        import result_coordination as rc
        request = json.loads(w.safe_path(args.root, args.input).read_text())
        result = {'route': rc.result_lane(args.root, rc.exact_identity(request)),
                  'authority': authority(args.root), 'actual_write': False}
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
