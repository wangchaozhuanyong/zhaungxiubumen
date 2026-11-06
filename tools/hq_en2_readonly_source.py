"""Uninstalled source validation candidate; never grants a policy or sends a message."""
from pathlib import Path
import hashlib
import json


def digest(root, pin):
    path = (Path(root) / pin['path']).resolve(strict=True)
    if not path.is_relative_to(Path(root).resolve()):
        raise ValueError('source outside project')
    import workflow_control as w
    data = w.validation_bytes(path)
    if len(data) != pin['size'] or hashlib.sha256(data).hexdigest() != pin['sha256']:
        raise ValueError('immutable source changed')
    return data


def validate(root, decision_pin, native_pin, request, hq_native_pin=None):
    if (decision_pin.get('sha256') != '63367c9b6dce305b51012d4b261439b4ad354bc9281c54a9c88a9106a92d4378'
            or not hq_native_pin or hq_native_pin.get('sha256') != '61e14fc75bc839c096f2c7ec14b8adee469a4c124444d9981c2f9b81b06e1458'
            or native_pin.get('sha256') != '740968988a652bdd01bc047f2f36020a64aa190fc838d576f33e0b64296c8845'):
        raise ValueError('exact authentic HQ source pins required')
    decision = json.loads(digest(root, decision_pin))
    native = json.loads(digest(root, native_pin))
    call = native['actual_call']
    prompt = call['arguments']['prompt']
    if not (native['source'] == 'first_party_read_thread'
            and native['thread']['id'] == decision['decision_thread']
            and native['thread']['hostId'] == 'local'
            and Path(native['thread']['cwd']).resolve() == Path(root).resolve()
            and call['server'] == 'codex_app' and call['tool'] == 'send_message_to_thread'
            and call['status'] == 'completed'
            and call['arguments']['threadId'] == '<LOCAL_TASK_ID>'
            and decision_pin['path'] in prompt and decision_pin['sha256'] in prompt):
        raise ValueError('real original HQ decision transport required')
    original = json.loads(digest(root, decision['exact_original_request']))
    failure = json.loads(digest(root, decision['exact_actual_refusal']))
    digest(root, decision['actual_owner_delegation'])
    payload = digest(root, decision['exact_payload'])
    page = json.loads(digest(root, hq_native_pin))
    turns = [t for t in page.get('turns', []) if t.get('id') == 'example-native-5b300addd34744fb']
    messages = [m for t in turns for m in t.get('items', [])
                if m.get('id') == 'msg_b6ae65cfb2444eee1cd556c6391c30175cb179132336e10d66da78e1e4c9c2f0']
    if not (page.get('thread', {}).get('id') == decision['decision_thread']
            and page['thread'].get('hostId') == 'local'
            and Path(page['thread'].get('cwd', '')).resolve() == Path(root).resolve()
            and len(turns) == len(messages) == 1 and turns[0].get('error') is None
            and messages[0].get('type') == 'agentMessage'
            and messages[0].get('phase') == 'commentary'
            and decision_pin['sha256'] in messages[0].get('text', '')
            and decision['target_thread_id'] in messages[0].get('text', '')):
        raise ValueError('exact HQ native decision required')
    import sys
    sys.path.insert(0, str(Path(root) / 'tools'))
    import workflow_control as w
    import department_autonomy as a
    import goal_delivery_runtime as g
    snap = g.restore_goal(root, w.read_json(w.snapshot_path(root, original['task_id'])))
    goal = snap['goal_delivery']
    contract = json.loads(digest(root, snap['goal_contract']))
    for field in ('primary_owner', 'producer_departments', 'authorized_scope',
                  'human_authorization', 'required_execution_actions', 'collaboration_scopes'):
        if goal.get(field) != contract.get(field):
            raise ValueError('frozen original contract changed')
    if not (snap.get('current_state') not in w.TERMINAL_STATES
            and goal.get('primary_owner') == 'publishing'
            and goal.get('producer_departments') == ['publishing']
            and original['scope'] in goal.get('authorized_scope', [])):
        raise ValueError('open original PUB task required')
    human = json.loads(digest(root, goal['authorization_pin']))
    auth = goal['human_authorization']
    if not (human.get('message', {}).get('type') == 'userMessage'
            and human['message'].get('id') == auth.get('message_id')
            and human.get('source_thread_id') == auth.get('source_thread_id')
            and human['message'].get('content')):
        raise ValueError('original human authorization required')
    a.authority(root)
    registry = w.read_json(Path(root) / 'data/department-registry.json')
    target = registry['collaboration_bindings']['designated-development']
    if not (target.get('generic_cross_project_access_allowed') is False
            and target.get('runtime_goal_authorization_required') is True
            and all(original.get(k) == target.get(v) for k, v in {
                'target_project_id':'project_id','target_thread_id':'thread_id',
                'target_thread_title':'title','target_cwd':'cwd',
                'target_sidebar_section_id':'sidebar_section_id'}.items())):
        raise ValueError('exact fixed external WEB identity required')
    keys = ('task_id', 'scope', 'action_id', 'sender_department', 'action_class',
            'source_project_id', 'target_project_id', 'target_department', 'target_thread_id',
            'target_thread_title', 'target_cwd', 'target_sidebar_section_id', 'payload',
            'payload_sha256', 'delivery_mode', 'assignment_record_required', 'authorization_changes')
    fresh = {'actual_target_state', 'actual_sender_state', 'actual_live_inventory', 'live_observed_at'}
    if not (set(request) <= set(keys) | fresh and all(k in request for k in keys)
            and all(request.get(k) == original.get(k) for k in keys)
            and all(decision.get(k) == original.get(k) for k in ('task_id','scope','action_id','sender_department','target_department','target_project_id','target_thread_id'))
            and original['action_class'] == 'thread_message' and original['sender_department'] == 'operations'
            and original['assignment_record_required'] is False and original['authorization_changes'] == []
            and original['payload'] == decision['exact_payload']
            and hashlib.sha256(payload).hexdigest() == original['payload_sha256']
            and decision['decision'] == 'coordinate_exact_nonpayment_change_preserve_action_gates'
            and decision['external_permission_issued'] is False
            and decision['production_permission_issued'] is False
            and decision['new_business_scope'] is False
            and failure['status'] == 'blocked' and failure['message_sent'] is False
            and failure['authorization_precheck']['reasons'] == ['new_department']
            and failure['authorization_precheck']['needs_human_confirmation'] is False):
        raise ValueError('exact original readonly decision, request and refusal required')
    return {'readonly_source_validated': True, 'policy_issued': False, 'message_sent': False}


# This schema is transport-only. It does not grant WEB or CMS execution.
SCHEMA = 'hq-en2-original-web-readonly-source/v1'
EVENT = 'hq_en2_original_web_readonly_source'
MARKER = 'hq_en2_readonly_source'
TASK = 'fc-20261011-english-kitchen-actual-publication-goal-v1'
ACTION = 'HQ-WEB-EN2-original-runtime-readback-after-SYS50-20261105-v1'
ROOTDIR = 'reports/local-department-system-repair-20261030-v1/OPEN-SOURCE-REFERENCE-REVIEW-20261105-v1/IMPLEMENTATION-CONTINUATION-v1/'
IDENTITY = ('task_id','scope','action_id','sender_department','action_class','source_project_id',
            'target_project_id','target_department','target_thread_id','target_thread_title','target_cwd',
            'target_sidebar_section_id','payload','payload_sha256','delivery_mode',
            'assignment_record_required','authorization_changes')
FRESH = {'actual_target_state','actual_sender_state','actual_live_inventory','live_observed_at'}


def _pins(root):
    import workflow_control as w
    names = {'decision':'HQ-EN2-EXACT-ORDINARY-READONLY-DECISION-HB1001-v1.json',
             'native':'SYS51-HQ-ACTUAL-DECISION-TRANSPORT-NATIVE-v1.json',
             'hq_native':'HQ-EN2-EXACT-ORDINARY-DECISION-NATIVE-HB1001-v2.json',
             'request':'HQ-WEB-EN2-HB0559-READONLY-REQUEST-v1.json'}
    return {k:w.file_digest(root,ROOTDIR+v) for k,v in names.items()}


def source_input(root):
    return {'schema':SCHEMA,'task_id':TASK,**_pins(root)}


def _check(root, source):
    import workflow_control as w
    if source != source_input(root):
        raise w.WorkflowError('exact immutable HQ EN2 readonly source required')
    request = json.loads(digest(root, source['request']))
    validate(root, source['decision'], source['native'], request, source['hq_native'])
    if request['task_id'] != TASK or request['action_id'] != ACTION:
        raise w.WorkflowError('exact original EN2 action required')
    return {k:request[k] for k in IDENTITY}


def registered(root, snapshot, request):
    import workflow_control as w
    if not isinstance(request,dict) or request.get('action_id') != ACTION:
        return None
    if set(request) - set(IDENTITY) - FRESH - {MARKER}:
        raise w.WorkflowError('readonly source cannot carry execution parameters')
    events = [e for e in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS,where={'task_id':TASK})
              if e.get('details',{}).get(EVENT)]
    if not events:
        return None
    if len(events) != 1 or snapshot.get('task_id') != TASK or w.validate_workflow_events(root,TASK):
        raise w.WorkflowError('one intact original readonly source event required')
    pin = events[0]['details'][EVENT]
    source = json.loads(digest(root,pin))
    action = {**_check(root,source),MARKER:pin}
    rows = [a for a in snapshot['goal_delivery'].get('approved_actions',[]) if a.get('action_id') == ACTION]
    if rows != [action] or any(request[k] != action[k] for k in request if k not in FRESH):
        raise w.WorkflowError('exact original registered action required')
    return {'action':action,'registration':pin,'readonly_only':True,'external_permission_issued':False}


def approved_action(root, snapshot, request):
    value = registered(root, snapshot, request)
    return value['action'] if value else None


def binding(root, snapshot, request):
    import workflow_control as w
    value = registered(root, snapshot, request)
    if not value:
        return None
    registry = w.department_registry(root)
    sender = registry['operations']['chat_binding']
    target = w.read_json(Path(root)/'data/department-registry.json')['collaboration_bindings']['designated-development']
    return sender, {**target,'task_id':target['thread_id']}


def message_route(root, snapshot, request):
    import department_autonomy as a
    import workflow_control as w
    if request.get('action_id') == ACTION and not all(k in request for k in IDENTITY):
        raise w.WorkflowError('complete exact HQ EN2 readonly message required')
    value = registered(root, snapshot, request)
    if not value:
        return None
    return {**a.authority(root),'source':value['registration'],'report':value['action']['payload'],
            'scope':value['action']['scope'],'sender_department':'operations',
            'target_department':'designated-development','purpose':'hq_en2_registered_readonly_transport',
            'business_producer_added':False,'current_assignment_changed':False,
            'external_permission_issued':False}


def record(root, task_id, input_path):
    import department_autonomy as a
    import goal_delivery_runtime as g
    import workflow_control as w
    from department_rotation import prohibit_validation_write
    prohibit_validation_write()
    pin = w.file_digest(root,input_path)
    source = json.loads(digest(root,pin))
    if task_id != TASK:
        raise w.WorkflowError('original EN2 task required')
    with w.workflow_lock(root), w.request_validation_context() as ctx:
        path = w.snapshot_path(root,TASK)
        before = w.file_digest(root,str(path.relative_to(root)))
        raw = path.read_bytes()
        snapshot = g.restore_goal(root,w.read_json(path))
        action = {**_check(root,source),MARKER:pin}
        old = [e for e in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS,where={'task_id':TASK})
               if e.get('details',{}).get(EVENT)]
        rows = [x for x in snapshot['goal_delivery'].get('approved_actions',[]) if x.get('action_id') == ACTION]
        if old or rows:
            if len(old) == 1 and old[0]['details'][EVENT] == pin and rows == [action]:
                return {'result':'duplicate_ignored','source':pin,'message_sent':False,'external_permission_issued':False}
            raise w.WorkflowError('existing original action requires effect reconciliation')
        a._owner_message_transport_not_started(root,snapshot,action)
        if any(x.get('task_id') == TASK and x.get('action_id') == ACTION
               for x in w.read_jsonl(Path(root)/w.POLICY_DECISIONS)):
            raise w.WorkflowError('existing original policy requires effect reconciliation')
        if w.validate_workflow_events(root,TASK):
            raise w.WorkflowError('intact original workflow history required')
        ctx.recheck()
        if w.file_digest(root,str(path.relative_to(root))) != before:
            raise w.WorkflowError('snapshot changed before registration')
        backup = Path(root)/'backups/fc-20261024-original-flow-recovery-execution-stage-v1/SYS51-EN2-readonly-registration-v1'/('snapshot-'+before['sha256']+'.json')
        if backup.exists():
            if backup.read_bytes() != raw: raise w.WorkflowError('snapshot backup mismatch')
        else: w.atomic_write_text(backup,raw.decode('utf-8'))
        goal = snapshot['goal_delivery']
        snapshot['goal_delivery'] = {**goal,'approved_actions':[*goal.get('approved_actions',[]),action]}
        event = w.append_workflow_event(root,TASK,snapshot['current_state'],
                   {EVENT:pin,'goal_delivery':snapshot['goal_delivery'],'actual_actor':'operations',
                    'frozen_contract_unchanged':True,'external_permission_issued':False,'message_sent':False})
        w.atomic_write_json(path,snapshot)
        after = w.file_digest(root,str(path.relative_to(root)))
        journal = {'schema':'hq-en2-readonly-registration-journal/v1','source':pin,'snapshot_before':before,
                   'snapshot_after':after,'backup':w.file_digest(root,str(backup.relative_to(root))),
                   'event':event,'message_sent':False,'external_permission_issued':False}
        w.atomic_write_json(backup.parent/'journal.json',journal)
    return {'result':'recorded','source':pin,'snapshot_before':before,'snapshot_after':after,
            'journal':w.file_digest(root,str((backup.parent/'journal.json').relative_to(root))),
            'message_sent':False,'external_permission_issued':False}
