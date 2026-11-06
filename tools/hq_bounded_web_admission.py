"""One actual HQ ordinary decision -> original WEB local-code message.

Append-only admission, not a new department permission, production source,
publisher permit, contract change or a readonly disguise for development work.
The ordinary preparation, current native identity, policy and transport remain.
"""
from __future__ import annotations
import datetime as dt
import copy
from pathlib import Path
import workflow_control as w

BASE = 'reports/local-department-system-repair-20261030-v1/AUTONOMOUS-DELIVERY-REPAIR-20261104-v1/'
TASK = 'fc-20261016-industry-keyword-next-eight-pages-v1'
SCOPE = 'project:flashcast:industry-keyword-next-eight-pages:v1'
ACTION = 'HQ-WEB-next8-05971-original-single-field-local-source-carrier-20261104-v2'
SCHEMA = 'hq-next8-singlefield-local-web-admission/v1'
EVENT = 'hq_bounded_local_web_admission'
MARKER = 'hq_bounded_local_web_source'
HQ_MESSAGE = 'msg_1d0ba602c718bde37cd748cd16ee833dcc7fa74de9932ccd2b0896d0a30528da'
HUMAN_MESSAGE = 'example-native-f438de429bc93cd7'
PENDING_EVENT = '032f02d8-0a09-4434-a7d6-65742f4f6090'
CANDIDATE = 'next8-renovation-zh-05971-67e79c93-cms-v1'
PINS = {
    'owner_delegation': {'path': BASE+'ACTUAL-OWNER-DELEGATION-SOURCE.json', 'sha256': '82f03e76d785bef3dd866ee7128b32c2d360a3ba08aff39faa071e37e4e714ec', 'size': 852},
    'hq_decision': {'path': BASE+'ACTUAL-HQ-05971-BOUNDED-LOCAL-CODE-CONTINUATION-DECISION.json', 'sha256': '2059114bec9d87b928dd5cdd9f845ba7072d8edc9f4189d8584fa3d88ce6ec72', 'size': 2142},
    'hq_native': {'path': BASE+'ACTUAL-HQ-05971-DECISION-NATIVE-PROJECTION.json', 'sha256': '5c81f5dd3eaf54cfa9ff1503c84a0190491f8b61b5406dc03fcc8301f7d67fce', 'size': 1585},
    'original_request': {'path': BASE+'WEB-SINGLEFIELD-CODE-REQUEST.json', 'sha256': '48e4a86b115f312dc64f5e2af4abe2e2aa136e89a4cb5986724825bd15c3b5a5', 'size': 1455},
    'prior_rejection': {'path': BASE+'WEB-SINGLEFIELD-CODE-PREPARED.json', 'sha256': '45ceebcc09acf4c45a0855b315de3606a7b5fbb958f7631a9b5557fb2dd3bd51', 'size': 1885},
    'registered_source': {'path': 'backups/fc-20261024-original-flow-recovery-execution-stage-v1/next8-zh05971-source-20261104-v1/SYS-ORIGINAL-SINGLE-FIELD-SOURCE-REGISTRATION-INPUT-v1.json', 'sha256': '793d3c39e9d589a417752ac1b2b4975648d8a3aba75332a9cfaa101b806987ee', 'size': 1679},
    'goal_contract': {'path': 'logs/handoffs/2026-10-16-industry-keyword-continuation-v1/next-eight-complete-goal.json', 'sha256': '8cc2237471c654ddc02779cdc5b4d6b6bc2565b7b607339727e0da74ffa6970b', 'size': 3476},
    'original_authorization': {'path': 'logs/handoffs/2026-10-16-industry-keyword-continuation-v1/next-eight-owner-authorization.json', 'sha256': 'd9f881444a64d7564becbbf8da3651ef0dbaf91ccc9bcdaf3e5d476cb1654137', 'size': 997},
}
IDENTITY_KEYS = ('task_id','scope','action_id','sender_department','action_class','source_project_id',
                 'target_project_id','target_department','target_thread_id','target_thread_title',
                 'target_cwd','target_sidebar_section_id','payload','payload_sha256','delivery_mode',
                 'assignment_record_required','authorization_changes')
FRESH_KEYS = {'actual_target_state','actual_sender_state','actual_live_inventory','live_observed_at'}
FORBIDDEN = {'approval_id','consume_approval','execution_request','professional_execution_source',
             'execution_tuple','execution_tuples','professional_owner_message_source','chief_coordination_source',
             'result_notification','result_identity','routine_delegation','parent_task_id',
             'goal_responsibility_dispatch','production_READY','permit','internal_repairs'}


def need(ok, reason):
    if not ok:
        raise w.WorkflowError('bounded HQ WEB admission: '+reason)


def document(root, pin):
    from qa_review_plan import _review_source_document
    return _review_source_document(root, pin)


def input_document():
    return {'schema': SCHEMA, 'task_id': TASK, 'scope': SCOPE,
            **{k: copy.deepcopy(PINS[k]) for k in ('owner_delegation','hq_decision','hq_native','original_request',
                                   'prior_rejection','registered_source')}, 'source_event_id': PENDING_EVENT}


def _snapshot(root):
    import goal_delivery_runtime as g
    import department_autonomy as a
    from chief_assistant_coordination import notification_task_pause
    snap = g.restore_goal(root, w.read_json(w.snapshot_path(root, TASK)))
    need(snap.get('task_id') == TASK and snap.get('goal_contract') == PINS['goal_contract'], 'original frozen goal contract required')
    need(snap.get('current_state') not in w.TERMINAL_STATES | {'paused','user_paused','suspended'}
         and not notification_task_pause(root, TASK), 'original task paused/terminal; no new local work')
    need(not w.validate_workflow_events(root, TASK), 'intact original append-only workflow required')
    goal = snap.get('goal_delivery', {}); frozen = document(root, PINS['goal_contract'])
    need(all(goal.get(k) == frozen.get(k) for k in ('primary_owner','producer_departments','authorized_scope','human_authorization')),
         'original owner/producers/authority must remain unchanged')
    if goal.get('responsible_assistant') != frozen.get('responsible_assistant'):
        need(a.historical_professional_workflow_reviewer(root, snap) == goal.get('responsible_assistant'),
             'existing recipient transfer needs its original normal SQL/native history; never replace it')
    need(goal.get('authorization_pin') == PINS['original_authorization'] and SCOPE in goal.get('authorized_scope', []),
         'unchanged original human pin and exact original scope required')
    document(root, PINS['original_authorization']); a.authority(root)
    return snap


def _unused(root, snap):
    import department_autonomy as a
    a._owner_message_transport_not_started(root, snap, {'task_id': TASK, 'action_id': ACTION})
    for e in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS, where={'task_id': TASK}):
        for name, value in e.get('details', {}).items():
            if isinstance(value, dict) and value.get('action_id') == ACTION and any(
                    token in name for token in ('intent','transport','dispatch','queue','consum')):
                need(False, 'original action has an intent/UNKNOWN/consumed effect; inspect original key')
    for row in w.read_jsonl(Path(root)/w.APPROVAL_LEDGER):
        if row.get('task_id') == TASK and row.get('action_id') == ACTION:
            need(False, 'an old production approval cannot authorize or renew this local-code message')


def validate_source(root, item):
    """Pure real-root diagnostic; it never appends or pretends native completion."""
    import department_autonomy as a
    from qa_review_plan import _review_native_containers
    need(item == input_document(), 'only the exact new human/HQ/source/request pins are admitted')
    snap = _snapshot(root); goal = snap['goal_delivery']; registry = w.department_registry(root)
    hq = registry['operations']['chat_binding']
    target = w.read_json(Path(root)/'data/department-registry.json').get('collaboration_bindings', {}).get('designated-development')
    need(isinstance(target, dict) and target.get('generic_cross_project_access_allowed') is False
         and target.get('runtime_goal_authorization_required') is True, 'original fixed external WEB binding required')
    owner = document(root, item['owner_delegation']); decision = document(root, item['hq_decision'])
    request = document(root, item['original_request']); rejected = document(root, item['prior_rejection'])
    need(owner.get('schema') == 'actual-first-party-owner-directive/v1' and owner.get('source') == 'first_party_read_thread'
         and owner.get('role') == 'human' and owner.get('not_a_synthetic_authorization') is True
         and owner.get('message_id') == HUMAN_MESSAGE and owner.get('source_thread_id') == hq.get('task_id')
         and Path(owner.get('project_root', '')).resolve() == Path(root).resolve()
         and owner.get('original_message') and all(c.get('type') == 'text' and c.get('text', '').strip() for c in owner['original_message']),
         'actual Nov4 owner delegation required; old human/actor substitutes are not admitted')
    need(decision.get('schema') == 'actual-HQ-owner-delegated-source-continuation-decision/v1'
         and decision.get('decision_actor') == 'operations' and decision.get('decision_thread_id') == hq.get('task_id')
         and decision.get('owner_delegation_source') == item['owner_delegation']
         and decision.get('same_original_task_owner_and_producer_retained') is True
         and decision.get('new_project_account_fee_or_scope') is False
         and decision.get('no_Save_permit_push_deploy_from_this_decision') is True
         and decision.get('normal_admission_and_fresh_policy_required') is True
         and decision.get('prior_rejection_preserved') == item['prior_rejection']['path'], 'real single ordinary HQ decision required')
    exact = decision.get('exact_request')
    need(isinstance(exact, dict) and all(request.get(k) == v for k, v in exact.items())
         and all(k in request for k in IDENTITY_KEYS)
         and request['task_id'] == TASK and request['scope'] == SCOPE and request['action_id'] == ACTION
         and request['sender_department'] == 'operations' and request['action_class'] == 'thread_message'
         and request['target_department'] == 'designated-development'
         and request['assignment_record_required'] is False and request['authorization_changes'] == []
         and request['delivery_mode'] == 'mcp_direct_send', 'exact operations actor and one original local-code message required')
    payload = request['payload']
    need(w.file_digest(root, payload.get('path', '')) == payload and payload['sha256'] == request['payload_sha256'], 'original exact local-code payload bytes required')
    need(request['source_project_id'] == hq.get('project_id') == a.PROJECT
         and Path(hq.get('cwd', '')).resolve() == Path(root).resolve()
         and all(request.get(k) == target.get(v) for k, v in {
             'target_project_id':'project_id','target_thread_id':'thread_id','target_thread_title':'title',
             'target_cwd':'cwd','target_sidebar_section_id':'sidebar_section_id'}.items()), 'current exact HQ and original WEB project/chat/title/cwd required')
    auth = rejected.get('authorization_precheck', {})
    need(rejected.get('status') == 'blocked' and rejected.get('message_sent') is False
         and auth.get('task_id') == TASK and auth.get('scope') == SCOPE
         and auth.get('status') == 'authorization_change_required' and auth.get('reasons') == ['new_department']
         and auth.get('decision_owner') == 'operations' and auth.get('needs_human_confirmation') is False,
         'original refusal must remain exact and preserved')
    projection = document(root, item['hq_native']); page = projection.get('native', {})
    _review_native_containers(projection); _review_native_containers(page)
    need(projection.get('source') == 'first_party_read_thread'
         and all(page.get('thread', {}).get(k) == hq.get(v) for k, v in {'id':'task_id','title':'title','cwd':'cwd','hostId':'host_id'}.items())
         and page['thread'].get('kind') == 'codex', 'actual HQ native decision identity required')
    pairs = [(t,m) for t in page.get('turns', []) if t.get('id') == owner.get('source_turn_id')
             for m in t.get('items', []) if m.get('id') == HQ_MESSAGE]
    need(len(pairs) == 1, 'one actual HQ decision message required')
    turn, message = pairs[0]; observed = w._parse_observed_at(projection.get('observed_at_UTC'))
    decided = w._parse_observed_at(decision.get('at_UTC')); human_at = w._parse_observed_at(owner.get('observed_at_UTC'))
    need(turn.get('status') == 'inProgress' and turn.get('completedAt') is None and not turn.get('error')
         and type(turn.get('startedAt')) in {int,float} and observed and decided and human_at
         and turn['startedAt'] <= human_at.timestamp() <= decided.timestamp() <= observed.timestamp() <= dt.datetime.now(dt.timezone.utc).timestamp()
         and message.get('type') == 'agentMessage' and message.get('phase') == 'commentary'
         and item['hq_decision']['sha256'] in message.get('text', '')
         and item['hq_decision']['path'] in message.get('text', ''), 'real in-progress HQ commentary binds the exact decision; never invent completed')
    from professional_cms_single_field_pending import pending_targets
    targets = pending_targets(root, TASK); selected = targets.get(CANDIDATE)
    need(isinstance(selected, dict) and selected.get('source_registration') == item['registered_source']
         and selected.get('source_event_id') == item['source_event_id'] == PENDING_EVENT
         and selected.get('task_id') == TASK and selected.get('scope') == SCOPE
         and selected.get('owner') == goal.get('primary_owner') and selected.get('execution_owner') == 'publishing'
         and selected.get('changed_fields') == ['content_zh']
         and selected.get('record_id') == '0d947129-0595-43ef-baa1-0fd9d8b870e6'
         and selected.get('table') == 'services' and selected.get('slug') == 'renovation', 'one normally registered original one-field source and intact C1 standing lineage required')
    _unused(root, snap)
    action = {k: request[k] for k in IDENTITY_KEYS}
    return {'snapshot': snap, 'action': action, 'sender_binding': hq,
            'target_binding': {**target, 'task_id': target['thread_id']},
            'source_event_id': selected['source_event_id'], 'hq_turn_status': turn['status'],
            'local_code_work_authorized': True, 'external_permission_issued': False,
            'production_READY': False, 'original_key_effect': selected.get('original_key_effect')}


def record(root, task_id, input_path):
    """Normal record entry, append exact action only; no production permit."""
    from department_rotation import prohibit_validation_write
    prohibit_validation_write()
    pin = w.file_digest(root, input_path); item = document(root, pin)
    if item.get('schema') == CODE_SCHEMA:
        return record_code_stage(root, task_id, input_path)
    need(task_id == TASK, 'same original task required')
    with w.workflow_lock(root), w.request_validation_context() as ctx:
        result = validate_source(root, item); snap = result['snapshot']; goal = snap['goal_delivery']
        old = [e for e in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS, where={'task_id': TASK}) if e.get('details', {}).get(EVENT)]
        action = {**result['action'], MARKER: pin}
        if old:
            need(len(old) == 1 and old[0]['details'][EVENT] == pin
                 and [a for a in goal.get('approved_actions', []) if a.get('action_id') == ACTION] == [action], 'immutable one-item admission already bound to another source')
            return {'result':'duplicate_ignored','source':pin,'external_permission_issued':False}
        need(not any(a.get('action_id') == ACTION for a in goal.get('approved_actions', [])), 'original action exists; reconcile exact original source without replacement')
        ctx.recheck()
        snap['goal_delivery'] = {**goal, 'approved_actions': [*goal.get('approved_actions', []), action]}
        w.append_workflow_event(root, TASK, snap['current_state'], {EVENT:pin,'goal_delivery':snap['goal_delivery'],
                               'actual_actor':'operations','frozen_contract_unchanged':True,'external_permission_issued':False})
        w.atomic_write_json(w.snapshot_path(root, TASK), snap)
    return {'result':'recorded','source':pin,'local_code_work_authorized':True,'actual_actor':'operations',
            'message_sent':False,'external_permission_issued':False,'production_READY':False}


def registered(root, snap, requested):
    # The independently registered reviewed test successor is the same
    # normal HQ-to-original-WEB source family, not arbitrary owner metadata.
    if isinstance(requested,dict) and ('hq_singlefield_test_successor_source' in requested
            or str(requested.get('action_id','')).startswith('HQ-WEB-next8-test-successor-')):
        from hq_singlefield_test_successor import registered as reviewed_successor
        return reviewed_successor(root,snap,requested)
    if isinstance(requested, dict) and requested.get('action_id') == CODE_ACTION:
        return registered_code_stage(root, snap, requested)
    if not isinstance(requested, dict) or requested.get('action_id') != ACTION:
        return None
    need(not any(k in requested for k in FORBIDDEN), 'production, old permits or owner/readonly impersonation are forbidden')
    need(set(requested) <= set(IDENTITY_KEYS) | FRESH_KEYS | {MARKER}, 'unrecognized request field cannot expand this one-item admission')
    entries = [e['details'][EVENT] for e in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS, where={'task_id': TASK}) if e.get('details', {}).get(EVENT)]
    if not entries:
        return None
    need(len(entries) == 1 and snap.get('task_id') == TASK, 'one original normal admission event required')
    result = validate_source(root, document(root, entries[0])); action = {**result['action'], MARKER: entries[0]}
    need(all(requested[k] == action[k] for k in requested if k not in FRESH_KEYS)
         and [a for a in result['snapshot']['goal_delivery'].get('approved_actions', []) if a.get('action_id') == ACTION] == [action], 'exact registered action/task/scope/target/payload and actual operations actor required')
    return {**result, 'action':action,'registration':entries[0]}


def approved_action(root, snap, requested):
    result = registered(root, snap, requested)
    return result['action'] if result is not None else None


def binding(root, snap, requested):
    result = registered(root, snap, requested)
    return (result['sender_binding'], {**result['target_binding'], 'thread_id':result['target_binding']['task_id']}) if result else None

# Independent ordinary code-stage admission.  The old local-only source above
# and the original production catalog remain immutable and are never fallback
# authority for this new source family.
CODE_SCHEMA = 'hq-next8-singlefield-code-stage-web-admission/v1'
CODE_KIND = 'actual_HQ_delegated_single_field_code_stage_v1'
CODE_EVENT = 'hq_singlefield_code_stage_web_admission'
CODE_MARKER = 'hq_singlefield_code_stage_source'
CODE_ACTION = 'HQ-WEB-next8-05971-exact-code-stage-663bd167976a-20261104-v1'
CODE_MESSAGE = 'msg_bb92b3d3079605e686cc2e94f0db73f1363a3c1030718d9e8ffefe3fcb86031d'
CODE_TURN = 'example-native-2bb898bc56866b49'
CODE_HEAD = '663bd167976a97ff915802122ca5087ac58dd8b5'
CODE_BASE = 'd6c011ba6d71bf3c691e297343175a7d5aa1a861'
CODE_TREE = 'afad2696fbf945938ffdb82e7f0eca5037db12d9'
CODE_OPS = ('git_push','pull_request','official_ci','merge','r3_dispatch','edge_deploy')
CODE_PINS = {'owner_delegation': {'path': 'reports/local-department-system-repair-20261030-v1/AUTONOMOUS-DELIVERY-REPAIR-20261104-v1/ACTUAL-OWNER-DELEGATION-SOURCE.json', 'sha256': '82f03e76d785bef3dd866ee7128b32c2d360a3ba08aff39faa071e37e4e714ec', 'size': 852}, 'hq_decision': {'path': 'reports/local-department-system-repair-20261030-v1/AUTONOMOUS-DELIVERY-REPAIR-20261104-v1/HQ-05971-EXACT-NORMAL-CODE-LOADING-DECISION.json', 'sha256': '4ccc67e962eafdfd125b54fec0bd87bf517cd40fbc9ad7407949bdfe44f520ae', 'size': 3500}, 'hq_native': {'path': 'reports/local-department-system-repair-20261030-v1/AUTONOMOUS-DELIVERY-REPAIR-20261104-v1/HQ-EXACT-CODE-LOADING-DECISION-NATIVE.json', 'sha256': '333aec31e02421eec5cb7ec6d42e3063e0002ca09de37516a95c97245018f0bc', 'size': 1449}, 'issuer_local_input': {'path': 'reports/local-department-system-repair-20261030-v1/AUTONOMOUS-DELIVERY-REPAIR-20261104-v1/SINGLEFIELD-ACTUAL-ISSUER-CANDIDATE-v1/PREPARED-ISSUER-CONTRACT-INPUT.json', 'sha256': '59c52c6471b8d167e2c1a2110f3d884704a6ef376f19f3b8b4e9743598757af9', 'size': 1685}, 'request': {'path': 'reports/local-department-system-repair-20261030-v1/AUTONOMOUS-DELIVERY-REPAIR-20261104-v1/HQ-SINGLEFIELD-WEB-CODE-STAGE-CANDIDATE-v1/EXACT-WEB-CODE-STAGE-REQUEST.json', 'sha256': '7b9c3ded804495e596d1f83d06674ee4be5d7554a9d49f1f924e524c9bd7f8a5', 'size': 1212}, 'recovery_runbook': {'path': 'reports/local-department-system-repair-20261030-v1/AUTONOMOUS-DELIVERY-REPAIR-20261104-v1/HQ-SINGLEFIELD-WEB-CODE-STAGE-CANDIDATE-v1/EXACT-CODE-RECOVERY-RUNBOOK.json', 'sha256': '93db977d9d46d6c983e57156373826d3202bb0ce7fccc51de7e9c371144dd051', 'size': 1428}}


def code_input_document():
    return {'schema':CODE_SCHEMA,'task_id':TASK,'scope':SCOPE,'source_kind':CODE_KIND,
            'source_event_id':PENDING_EVENT,**copy.deepcopy(CODE_PINS)}


def _code_unused(root, snapshot):
    import department_autonomy as a
    a._owner_message_transport_not_started(root,snapshot,{'task_id':TASK,'action_id':CODE_ACTION})
    for event in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS,where={'task_id':TASK}):
        for name,value in event.get('details',{}).items():
            if isinstance(value,dict) and value.get('action_id')==CODE_ACTION and any(
                    token in name for token in ('intent','transport','dispatch','queue','consum')):
                need(False,'code-stage original key has an intent/UNKNOWN/effect; observe it, never re-admit')
    need(not any(row.get('task_id')==TASK and row.get('action_id')==CODE_ACTION
                 for row in w.read_jsonl(Path(root)/w.APPROVAL_LEDGER)),
         'no old approval can renew this independent ordinary message')


def validate_code_stage_source(root,item,*,new_admission=False):
    """Read actual new HQ/native and original pending/WEB/Git inputs only.

    new_admission is internal call-site control, never an input/source flag.
    Registered reads deliberately retain used/UNKNOWN keys for effect readback.
    The normal routing/policy and per-action execution still decide any send.
    """
    import hashlib
    import department_autonomy as a
    import goal_delivery_runtime as g
    import professional_cms_issuer as issuer
    from qa_review_plan import _review_native_containers
    need(item==code_input_document(),'exact new code-stage source pins; no old-source or caller substitution')
    snapshot=_snapshot(root);goal=snapshot['goal_delivery'];registry=w.department_registry(root)
    hq=registry['operations']['chat_binding']
    target=w.read_json(Path(root)/'data/department-registry.json').get('collaboration_bindings',{}).get('designated-development')
    need(isinstance(target,dict) and target.get('generic_cross_project_access_allowed') is False
         and target.get('runtime_goal_authorization_required') is True
         and target.get('thread_id')=='<LOCAL_THREAD_ID>'
         and target.get('project_id')=='<LOCAL_PROJECT_ID>'
         and target.get('host_id')==hq.get('host_id')=='local'
         and Path(target.get('cwd','')).resolve()==Path('<WEBSITE_PROJECT_ROOT>').resolve(),
         'original fixed WEB host/project/root only; registration never creates a new department')
    owner=document(root,item['owner_delegation']);decision=document(root,item['hq_decision'])
    need(owner.get('schema')=='actual-first-party-owner-directive/v1'
         and owner.get('source')=='first_party_read_thread' and owner.get('role')=='human'
         and owner.get('not_a_synthetic_authorization') is True and owner.get('message_id')==HUMAN_MESSAGE
         and owner.get('source_thread_id')==hq.get('task_id')=='<LOCAL_TASK_ID>'
         and Path(owner.get('project_root','')).resolve()==Path(root).resolve()
         and isinstance(owner.get('original_message'),list) and owner['original_message']
         and all(x.get('type')=='text' and x.get('text','').strip() for x in owner['original_message']),
         'real latest human ordinary-decision delegation; never fabricate the old human')
    need(decision.get('schema')=='actual-HQ-original-single-field-code-loading-decision/v1'
         and decision.get('decision_actor')=='operations' and decision.get('decision_thread_id')==hq['task_id']
         and decision.get('owner_delegation_source')==item['owner_delegation']
         and decision.get('task_id')==TASK and decision.get('scope')==SCOPE
         and decision.get('actual_producer')=='designated-development'
         and decision.get('producer_thread')==target['thread_id']
         and decision.get('producer_turn')=='example-native-fe04ff569f062dc6'
         and decision.get('business_parent_closed') is False,
         'this actual HQ decision, task, scope and completed original producer only')
    projection=document(root,item['hq_native']);page=projection.get('native',{})
    _review_native_containers(projection);_review_native_containers(page)
    need(projection.get('source')=='first_party_read_thread' and page.get('thread',{}).get('kind')=='codex'
         and all(page.get('thread',{}).get(k)==hq.get(v) for k,v in
                 {'id':'task_id','title':'title','cwd':'cwd','hostId':'host_id'}.items()),
         'actual current original HQ native identity required')
    pairs=[(t,m) for t in page.get('turns',[]) if t.get('id')==CODE_TURN
           for m in t.get('items',[]) if m.get('id')==CODE_MESSAGE]
    need(len(pairs)==1,'one actual current HQ code-stage decision message required')
    turn,message=pairs[0];observed=w._parse_observed_at(projection.get('observed_at_UTC'))
    decided=w._parse_observed_at(decision.get('at_UTC'));human_at=w._parse_observed_at(owner.get('observed_at_UTC'))
    need(turn.get('status')=='inProgress' and turn.get('completedAt') is None and not turn.get('error')
         and type(turn.get('startedAt')) in {int,float} and observed and decided and human_at
         and human_at.timestamp()<=turn['startedAt']<=decided.timestamp()<=observed.timestamp()
         <=dt.datetime.now(dt.timezone.utc).timestamp()
         and message.get('type')=='agentMessage' and message.get('phase')=='commentary'
         and item['hq_decision']['sha256'] in message.get('text','')
         and item['hq_decision']['path'] in message.get('text',''),
         'real in-progress commentary names this exact decision; never label it completed or human')
    local=document(root,item['issuer_local_input'])
    need(callable(getattr(issuer,'_single_field_contract',None)),
         'normal single-field local issuer compatibility must actually be adopted first')
    contracts=[e for e in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS,where={'task_id':TASK})
               if e.get('details',{}).get(issuer.EVENT)==item['issuer_local_input']]
    need(len(contracts)==1,'one actually registered normal local issuer contract is required first')
    validated=issuer.validate_contract(root,snapshot,local);selected,_,physical=validated
    need(selected.get('source_only_single_field_contract') is True
         and selected.get('registration')==PINS['registered_source']
         and selected.get('pending_target',{}).get('source_event_id')==item['source_event_id']==PENDING_EVENT
         and selected.get('owner')==goal.get('primary_owner')
         and selected.get('executor')=='publishing' and physical.get('changedFields')==['content_zh']
         and physical.get('rollbackAllowed') is False and len(physical.get('baselineProjectionFields',[]))==41
         and len(physical.get('retainedProjectionFields',[]))==38,
         'actual original pending event/local issuer one-field/full41/protect38 binding required')
    need(local.get('WEB_delivery')==decision.get('WEB_delivery')
         and local.get('WEB_completed_result')==decision.get('WEB_result'),
         'ordinary decision must name the exact completed original WEB delivery/result')
    result=issuer.external(root,local['WEB_completed_result'],target);meta=result.get('git',{})
    need(decision.get('exact_git')==meta and meta.get('root')=='<WEBSITE_PROJECT_ROOT>'
         and meta.get('worktree')==meta['root']+'/.worktrees/next8-renovation-zh05971-channel-20261104-v1'
         and meta.get('branch')=='codex/next8-renovation-zh05971-channel-20261104-v1'
         and meta.get('head')==CODE_HEAD and meta.get('tree')==CODE_TREE
         and meta.get('base')==meta.get('parent')==CODE_BASE and meta.get('path_count')==12,
         'exact real 663bd167/afad2696 twelve-file source, no causal successor inferred')
    from professional_web_execution import git
    gitctx={'worktree':meta['worktree'],'binding':target}
    need(git(gitctx,'show','-s','--format=%H %P %T',CODE_HEAD).decode().strip()
         ==' '.join((CODE_HEAD,CODE_BASE,CODE_TREE)),'actual immutable candidate parent/tree required')
    files=result.get('changed_files',[]);paths={x.get('relative_path'):x.get('sha256') for x in files}
    need(len(files)==len(paths)==12 and set(git(gitctx,'diff','--name-only',CODE_BASE,CODE_HEAD).decode().splitlines())==set(paths),
         'exact complete original twelve-file Git delta required')
    for entry in files:
        path=entry['relative_path'];need(isinstance(path,str) and not Path(path).is_absolute()
            and '..' not in Path(path).parts and Path(entry.get('path','')).resolve()==Path(meta['worktree'],path).resolve(),
            'only exact original worktree relative paths')
        raw=git(gitctx,'show',CODE_HEAD+':'+path)
        tree=git(gitctx,'ls-tree',CODE_HEAD,'--',path).decode().split()
        need(hashlib.sha256(raw).hexdigest()==entry['sha256'] and len(raw)==entry['size']
             and len(tree)==4 and tree[0]==entry.get('git_mode') and tree[2]==entry.get('git_blob'),
             'every actual selected blob/mode/SHA must match the completed WEB source')
    remote=git(gitctx,'config','--get','remote.origin.url').decode().strip()
    need(remote in {'https://github.com/example-owner/example-website.git',
                    'https://github.com/example-owner/example-website',
                    'user-3de132cd98be@example.invalid:example-owner/example-website.git'},'original website repository only')
    request=document(root,item['request']);payload=request.get('payload',{})
    need(set(request)==set(IDENTITY_KEYS) and request.get('task_id')==TASK and request.get('scope')==SCOPE
         and request.get('action_id')==CODE_ACTION and request.get('sender_department')=='operations'
         and request.get('action_class')=='thread_message' and request.get('target_department')=='designated-development'
         and request.get('delivery_mode')=='mcp_direct_send' and request.get('assignment_record_required') is False
         and request.get('authorization_changes')==[] and w.file_digest(root,payload.get('path',''))==payload
         and payload.get('sha256')==request.get('payload_sha256')
         and request.get('source_project_id')==hq.get('project_id')==a.PROJECT
         and Path(hq.get('cwd','')).resolve()==Path(root).resolve()
         and all(request.get(k)==target.get(v) for k,v in {'target_project_id':'project_id',
             'target_thread_id':'thread_id','target_thread_title':'title','target_cwd':'cwd',
             'target_sidebar_section_id':'sidebar_section_id'}.items()),
         'one exact actual operations-to-original-WEB message and immutable payload only')
    payload_doc=document(root,payload);runbook=document(root,item['recovery_runbook'])
    need(payload_doc.get('schema')=='HQ-original-single-field-code-stage-message/v1'
         and payload_doc.get('source_kind')==CODE_KIND and payload_doc.get('HQ_decision')==item['hq_decision']
         and payload_doc.get('normal_source_input_path')==str((Path(root)/BASE/'HQ-SINGLEFIELD-WEB-CODE-STAGE-CANDIDATE-v1/EXACT-NORMAL-SOURCE-INPUT.json').resolve())
         and payload_doc.get('owner_delegation')==item['owner_delegation']
         and payload_doc.get('source_registration_grants_execution_authority') is False
         and payload_doc.get('CMS_permission_issued') is False and payload_doc.get('business_parent_closed') is False
         and runbook.get('task_id')==TASK and runbook.get('scope')==SCOPE
         and runbook.get('source_commit')==CODE_HEAD and runbook.get('source_tree')==CODE_TREE
         and runbook.get('source_base')==CODE_BASE and runbook.get('forward_only_source') is True
         and runbook.get('unknown_effect_replay_allowed') is False,
         'exact code-only message/recovery boundary; no CMS permission or future effect claim')
    if new_admission:_code_unused(root,snapshot)
    return {'snapshot':snapshot,'action':request,'sender_binding':hq,'target_binding':{**target,'task_id':target['thread_id']},
            'source_event_id':PENDING_EVENT,'hq_turn_status':turn['status'],'code_stage_requested':True,
            'external_permission_issued':False,'production_READY':False,'original_key_effect':selected['pending_target'].get('original_key_effect'),
            'source_kind':CODE_KIND,'WEB_git':meta,'paths':paths,'actual_owner_source':owner,'registered_pending':selected}


def _code_entries(root):
    return [e for e in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS,where={'task_id':TASK})
            if e.get('details',{}).get(CODE_EVENT)]


def record_code_stage(root,task_id,input_path):
    from department_rotation import prohibit_validation_write
    prohibit_validation_write();need(task_id==TASK,'same original code-stage task required')
    pin=w.file_digest(root,input_path);item=document(root,pin)
    with w.workflow_lock(root),w.request_validation_context() as validation:
        entries=_code_entries(root)
        result=validate_code_stage_source(root,item,new_admission=not entries);snapshot=result['snapshot'];goal=snapshot['goal_delivery']
        action={**result['action'],CODE_MARKER:pin}
        if entries:
            need(len(entries)==1 and entries[0]['details'][CODE_EVENT]==pin
                 and [x for x in goal.get('approved_actions',[]) if x.get('action_id')==CODE_ACTION]==[action],
                 'immutable code-stage admission already exists; inspect its original effect')
            return {'result':'duplicate_ignored','source':pin,'message_sent':False,'external_permission_issued':False}
        need(not any(x.get('action_id')==CODE_ACTION for x in goal.get('approved_actions',[])),
             'existing action cannot be replaced or renewed by another source')
        validation.recheck()
        snapshot['goal_delivery']={**goal,'approved_actions':[*goal.get('approved_actions',[]),action]}
        event=w.append_workflow_event(root,TASK,snapshot['current_state'],{CODE_EVENT:pin,
              'goal_delivery':snapshot['goal_delivery'],'actual_actor':'operations','source_kind':CODE_KIND,
              'frozen_contract_unchanged':True,'external_permission_issued':False})
        w.atomic_write_json(w.snapshot_path(root,TASK),snapshot)
    return {'result':'recorded','source':pin,'event_id':event['event_id'],'source_kind':CODE_KIND,
            'message_sent':False,'external_permission_issued':False,'production_READY':False}


def registered_code_stage(root,snapshot,requested):
    if not isinstance(requested,dict) or requested.get('action_id')!=CODE_ACTION:return None
    need(not any(k in requested for k in FORBIDDEN),'new ordinary source cannot carry production permission or another actor')
    need(set(requested)<=set(IDENTITY_KEYS)|FRESH_KEYS|{CODE_MARKER},'unknown code-stage message input')
    entries=_code_entries(root)
    if not entries:return None
    need(len(entries)==1 and snapshot.get('task_id')==TASK,'one exact original code-stage registration')
    pin=entries[0]['details'][CODE_EVENT];result=validate_code_stage_source(root,document(root,pin))
    action={**result['action'],CODE_MARKER:pin}
    need(all(requested[k]==action[k] for k in requested if k not in FRESH_KEYS)
         and [x for x in result['snapshot']['goal_delivery'].get('approved_actions',[])if x.get('action_id')==CODE_ACTION]==[action],
         'exact registered code-stage task/scope/sender/target/payload required')
    return {**result,'action':action,'registration':pin,'event_id':entries[0]['event_id']}


def code_stage_context(root,task_id,registration):
    """Selector is checked against the one actual append-only event/action.

    This returns source context only.  It is not a permit, READY, live runtime,
    successful CI, received message, or proof of an external action.
    """
    need(task_id==TASK,'code-stage selector cannot revive another task')
    entries=_code_entries(root);need(len(entries)==1 and entries[0]['details'][CODE_EVENT]==registration,
         'normal current exact code-stage source registration required; no caller selector authority')
    result=validate_code_stage_source(root,document(root,registration));meta=result['WEB_git']
    action={**result['action'],CODE_MARKER:registration}
    need([x for x in result['snapshot']['goal_delivery'].get('approved_actions',[])if x.get('action_id')==CODE_ACTION]==[action],
         'registered current source action must remain unchanged')
    # The project is fixed by both real source and the immutable Git origin.
    # Each actual stage separately proves this existing account/repo via native
    # authenticated queries and verifies current clean worktree/HEAD/CAS.
    import ast,re
    module=ast.parse(w.validation_bytes(Path(root)/'tools/managed_cms_permit_issuer.py'))
    hosts=[ast.literal_eval(node.value) for node in module.body if isinstance(node,ast.Assign)
           and any(isinstance(t,ast.Name) and t.id=='SUPABASE_HOST' for t in node.targets)]
    need(len(hosts)==1 and isinstance(hosts[0],str) and re.fullmatch('[a-z0-9]+\\.supabase\\.co',hosts[0]),
         'one actual original project host, never supplied by the request')
    project=hosts[0].split('.')[0]
    return {'root':str(Path(root).resolve()),'task':TASK,'scope':SCOPE,'owner':result['snapshot']['goal_delivery']['primary_owner'],
            'role':'designated-development','binding':result['target_binding'],'contract':PINS['goal_contract'],
            'authorization':CODE_PINS['owner_delegation'],'decision':CODE_PINS['hq_decision'],'registration':registration,
            'event_id':entries[0]['event_id'],'hq_single_field_code_stage':True,'source_kind':CODE_KIND,
            'worktree':meta['worktree'],'site':meta['root'],'branch':meta['branch'],'commit':CODE_HEAD,'base':CODE_BASE,
            'git_parent':CODE_BASE,'tree':CODE_TREE,'paths':result['paths'],'prefix':'next8-zh05971-code-stage-4ccc67e9',
            'repository':'example-owner/example-website','repository_id':1248188229,'actor_id':276684684,
            'project_ref':project,'edge_scope':'company.example:edge:'+project+':content-publish',
            'pages_scope':'company.example:pages:production','rollback':CODE_PINS['recovery_runbook'],
            'allowed_operations':CODE_OPS,'actual_owner_source':result['actual_owner_source'],
            'external_permission_issued':False,'production_READY':False}
