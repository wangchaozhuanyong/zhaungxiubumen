"""One genuine HQ-decided, read-only fixed-WEB health bootstrap; no execution grant."""
from pathlib import Path
import datetime as dt
import json
import workflow_control as w
import hq_en2_readonly_source as origin

TASK=origin.TASK
ACTION='HQ-WEB-EN2-original-fixed-identity-health-probe-20261105-v1'
SCHEMA='hq-en2-original-web-health-probe-source/v1'
EVENT='hq_en2_original_web_health_probe_source'
DIRECT_INTENT='hq_web_health_probe_direct_intent'
MARKER='hq_en2_web_health_probe_source'
ROOTDIR=origin.ROOTDIR+'SYS51-web-health-probe-stage-v1/'
IDENTITY=origin.IDENTITY
FRESH=origin.FRESH
BODY=('task_id=fc-20261011-english-kitchen-actual-publication-goal-v1\n'
      'scope=cms:services:kitchen:english-two-fields:publication:v1\n'
      'action_id=HQ-WEB-EN2-original-fixed-identity-health-probe-20261105-v1\n'
      'sender_department=operations\ntarget_department=designated-development\nassignment_record_required=false\n\n'
      '仅作固定窗口健康核验：请非空简短回复当前真实项目、目录、固定角色和安全状态。'
      '本消息不交付或执行尚未发送的 EN2 业务正文；不修改代码，不操作 CMS、部署、账号或费用。\n')


def source_input(root):
    base=origin.ROOTDIR
    names={'decision':base+'HQ-EN2-ORIGINAL-WEB-HEALTH-PROBE-DECISION-HB1157-v1.json',
           'native':base+'HQ-EN2-HEALTH-PROBE-DECISION-NATIVE-HB1157-v1.json',
           'payload':ROOTDIR+'health-probe-payload-v1.txt'}
    return {'schema':SCHEMA,'task_id':TASK,**{k:w.file_digest(root,v) for k,v in names.items()}}


def _check(root, source, snapshot):
    if source != source_input(root) or source['decision']['sha256']!='e09241aa26987a34cb3df5a55d368690849d73a760db8ca98899151855644442' or source['native']['sha256']!='93d657f00693cd52f322d08cda70c903a35cb0e4a1b6b36d0d82fbeefeb7dcff':
        raise w.WorkflowError('exact genuine HQ health decision and native source required')
    decision=json.loads(origin.digest(root,source['decision']));page=json.loads(origin.digest(root,source['native']))
    payload=origin.digest(root,source['payload'])
    if payload!=BODY.encode():raise w.WorkflowError('canonical health-only body required')
    turns=[t for t in page.get('turns',[]) if t.get('id')=='example-native-b8cf756cce6e1ec6']
    messages=[m for t in turns for m in t.get('items',[]) if m.get('id')=='msg_1e3dea3fa975f30f09130afe2451050318e203d274543338c0236977f7624819']
    if not (page.get('thread',{}).get('id')==decision['decision_thread'] and page['thread'].get('hostId')=='local'
            and Path(page['thread'].get('cwd','')).resolve()==Path(root).resolve() and len(turns)==len(messages)==1
            and turns[0].get('error') is None and messages[0].get('type')=='agentMessage'
            and source['decision']['sha256'] in messages[0].get('text','')):
        raise w.WorkflowError('real original HQ decision message required')
    owner=json.loads(origin.digest(root,decision['owner_delegation']))
    failure=json.loads(origin.digest(root,decision['actual_business_refusal']))
    opened=json.loads(origin.digest(root,decision['actual_one_open_readback']))
    original=json.loads(origin.digest(root,decision['actual_business_request']))
    if not (owner.get('source')=='first_party_read_thread' and owner.get('role')=='human'
            and owner.get('not_a_synthetic_authorization') is True and owner.get('original_message')
            and failure.get('exit_code')==1 and 'actual external reply expired' in failure.get('stderr','')
            and opened.get('fresh_health_reply_not_created_by_navigation') is True
            and opened.get('message_sent') is False and opened.get('native',{}).get('thread',{}).get('id')==decision['target_thread_id']
            and opened['native']['thread'].get('status',{}).get('type')=='idle'
            and all(decision.get(k) is True for k in ('normal_health_probe_registration_and_policy_required','require_fresh_exact_target_identity_and_actual_idle','only_target_reply_freshness_may_be_bootstrapped_for_the_probe','no_health_row_or_reply_time_fabrication','business_message_gates_unchanged','professional_owner_and_frozen_contract_unchanged'))
            and all(decision.get(k) is False for k in ('production_permission_issued','message_sent','external_write_or_fees','business_parent_closed'))):
        raise w.WorkflowError('real expired business refusal and idle-open evidence required')
    original_source=origin.registered(root,snapshot,original)
    if not original_source:raise w.WorkflowError('original exact EN2 readonly registration required')
    request={k:original[k] for k in IDENTITY}
    request.update(action_id=ACTION,payload=source['payload'],payload_sha256=source['payload']['sha256'])
    if not (decision['task_id']==TASK==request['task_id'] and decision['scope']==request['scope']
            and decision['source_actor']==request['sender_department']=='operations'
            and decision['new_health_action_id']==ACTION and decision['target_thread_id']==request['target_thread_id']
            and decision['target_project_id']==request['target_project_id'] and decision['target_cwd']==request['target_cwd']):
        raise w.WorkflowError('exact original actor, target, action and scope required')
    return request


def registered(root,snapshot,request):
    if not isinstance(request,dict) or request.get('action_id')!=ACTION:return None
    if set(request)-set(IDENTITY)-FRESH-{MARKER}:raise w.WorkflowError('health-only probe forbids additional effects or approval fields')
    events=[e for e in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS,where={'task_id':TASK}) if e.get('details',{}).get(EVENT)]
    if not events:return None
    if len(events)!=1 or snapshot.get('task_id')!=TASK or w.validate_workflow_events(root,TASK):raise w.WorkflowError('one intact registered health probe required')
    pin=events[0]['details'][EVENT];source=json.loads(origin.digest(root,pin));action={**_check(root,source,snapshot),MARKER:pin}
    rows=[x for x in snapshot['goal_delivery'].get('approved_actions',[]) if x.get('action_id')==ACTION]
    if rows!=[action] or any(request[k]!=action[k] for k in request if k not in FRESH):raise w.WorkflowError('exact registered health probe required')
    return {'action':action,'registration':pin,'external_permission_issued':False}


def approved_action(root,snapshot,request):
    result=registered(root,snapshot,request);return result['action'] if result else None


def binding(root,snapshot,request):
    if not registered(root,snapshot,request):return None
    source=w.department_registry(root)['operations']['chat_binding']
    target=w.read_json(Path(root)/'data/department-registry.json')['collaboration_bindings']['designated-development']
    return source,{**target,'task_id':target['thread_id']}


def message_route(root,snapshot,request):
    import department_autonomy as a
    if request.get('action_id')==ACTION and not all(k in request for k in IDENTITY):raise w.WorkflowError('complete exact health probe required')
    result=registered(root,snapshot,request)
    if not result:return None
    return {**a.authority(root),'source':result['registration'],'report':result['action']['payload'],'scope':result['action']['scope'],
            'sender_department':'operations','target_department':'designated-development','purpose':'hq_external_health_probe_transport',
            'external_permission_issued':False,'current_assignment_changed':False,'business_producer_added':False}


def renewal_source(root, snapshot, request, previous, registration):
    """Renew the original direct probe only with its unchanged native target head."""
    from goal_delivery_runtime import _collaboration_native

    observation = snapshot['goal_delivery']['current_route_observations'][ACTION]
    live = json.loads(origin.digest(root, observation))
    target = request['actual_target_state']
    observed = w._parse_observed_at(request['live_observed_at'])
    checked = w._parse_observed_at(previous['checked_at'])
    if not (request['action_id'] == ACTION and request['delivery_mode'] == 'mcp_direct_send'
            and checked is not None and observed is not None and observed > checked
            and live['observed_at'] == request['live_observed_at']
            and live['delivery_mode'] == 'mcp_direct_send'
            and live['actual_native_observation'] == request['actual_live_inventory']
            and live['actual_native_target_turns'] == {request['target_thread_id']: target}):
        raise w.WorkflowError('new normal direct probe observation must bind the original target and inventory')
    page = _collaboration_native(root, target)
    original = json.loads(origin.digest(root, registration))
    decision = json.loads(origin.digest(root, original['decision']))
    opened = json.loads(origin.digest(root, decision['actual_one_open_readback']))['native']
    turns = page.get('turns') or []
    prior_turns = opened.get('turns') or []
    fixed = page.get('thread', {})
    head = turns[0] if turns else {}
    original_head = prior_turns[0] if prior_turns else {}
    completed = head.get('completedAt')
    if not (fixed.get('kind') == 'codex' and fixed.get('hostId') == 'local'
            and fixed.get('status', {}).get('type') == 'idle'
            and page.get('page', {}).get('order') == 'newest_first'
            and head.get('id') and head['id'] == original_head.get('id')
            and head.get('status') == 'completed' and head.get('error') is None
            and type(completed) in {int, float} and completed == original_head.get('completedAt')
            and 0 < completed < checked.timestamp()):
        raise w.WorkflowError('original WEB head changed or direct probe effect is unknown; no renewal')
    return {'registered_message_source': registration, 'payload': request['payload'],
            'actual_route_observation': observation, 'actual_target_state': target,
            'actual_live_inventory': request['actual_live_inventory'], 'original_target_turn': head['id']}


def reserve_direct_send(root, request_pin, preparation_pin):
    """Persist the one exact attempt before calling the authorized first-party tool."""
    import department_autonomy as a
    import goal_delivery_runtime as g
    from receipt_obligation_consumer import shared_serial_guard

    with w.workflow_lock(root), w.request_validation_context() as context:
        request = json.loads(origin.digest(root, request_pin))
        prepared = json.loads(origin.digest(root, preparation_pin))
        snapshot = g.restore_goal(root, w.read_json(w.snapshot_path(root, TASK)))
        probe = registered(root, snapshot, request)
        a._owner_message_transport_not_started(root, snapshot, request)
        rows = [row for row in w.read_jsonl(Path(root) / w.POLICY_DECISIONS)
                if row.get('task_id') == TASK and row.get('action_id') == ACTION]
        policy = rows[-1] if rows else {}
        checked = w._parse_observed_at(policy.get('checked_at'))
        if not (probe and len(rows) > 1 and prepared.get('policy_decision') == policy
                and policy.get('status') == 'allow' and policy.get('department') == 'operations'
                and policy.get('delivery_mode') == 'mcp_direct_send'
                and policy.get('external_permission_issued') is False
                and prepared.get('status') == 'ready_to_send' and prepared.get('message_sent') is False
                and prepared.get('payload') == request['payload'] and checked is not None
                and 0 <= (dt.datetime.now(dt.timezone.utc) - checked).total_seconds() <= 300
                and policy.get('message_policy_source') == renewal_source(root, snapshot, request, rows[-2], probe['registration'])
                and g.collaboration_route(root, snapshot, request) == []):
            raise w.WorkflowError('fresh renewed policy and exact original direct preparation required')
        guard = shared_serial_guard(root, target_thread_id=request['target_thread_id'])
        if guard.get('new_activation_allowed') is not True:
            raise w.WorkflowError('original serial boundary blocks direct probe: ' + str(guard.get('reasons')))
        context.recheck()
        a._owner_message_commit_freshness(root, request)
        intent = {'action_id': ACTION, 'request': request_pin, 'preparation': preparation_pin,
                  'policy_decision_id': policy['decision_id'], 'target_thread_id': request['target_thread_id'],
                  'serial_source': guard['source'], 'delivery_mode': 'mcp_direct_send',
                  'state': 'attempt_reserved', 'message_sent': False, 'external_permission_issued': False}
        w.append_workflow_event(root, TASK, snapshot['current_state'], {DIRECT_INTENT: intent})
        return intent


def record(root,task_id,input_path):
    import department_autonomy as a,goal_delivery_runtime as g
    from department_rotation import prohibit_validation_write
    prohibit_validation_write();pin=w.file_digest(root,input_path);source=json.loads(origin.digest(root,pin))
    if task_id!=TASK:raise w.WorkflowError('original EN2 task required')
    with w.workflow_lock(root),w.request_validation_context() as ctx:
        path=w.snapshot_path(root,TASK);before=w.file_digest(root,str(path.relative_to(root)));raw=path.read_bytes();snap=g.restore_goal(root,w.read_json(path))
        action={**_check(root,source,snap),MARKER:pin}
        old=[e for e in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS,where={'task_id':TASK}) if e.get('details',{}).get(EVENT)]
        rows=[x for x in snap['goal_delivery'].get('approved_actions',[]) if x.get('action_id')==ACTION]
        if old or rows:
            if len(old)==1 and old[0]['details'][EVENT]==pin and rows==[action]:return {'result':'duplicate_ignored','source':pin,'message_sent':False}
            raise w.WorkflowError('health probe identity already exists; reconcile original key')
        a._owner_message_transport_not_started(root,snap,action)
        if any(x.get('task_id')==TASK and x.get('action_id')==ACTION for x in w.read_jsonl(Path(root)/w.POLICY_DECISIONS)) or w.validate_workflow_events(root,TASK):raise w.WorkflowError('prior policy or invalid original history')
        ctx.recheck()
        if w.file_digest(root,str(path.relative_to(root)))!=before:raise w.WorkflowError('snapshot changed before registration')
        backup=Path(root)/'backups/fc-20261024-original-flow-recovery-execution-stage-v1/SYS51-web-health-probe-registration-v1'/('snapshot-'+before['sha256']+'.json')
        if backup.exists():
            if backup.read_bytes()!=raw:raise w.WorkflowError('backup mismatch')
        else:w.atomic_write_text(backup,raw.decode())
        goal=snap['goal_delivery'];snap['goal_delivery']={**goal,'approved_actions':[*goal.get('approved_actions',[]),action]}
        event=w.append_workflow_event(root,TASK,snap['current_state'],{EVENT:pin,'goal_delivery':snap['goal_delivery'],'actual_actor':'operations','external_permission_issued':False,'message_sent':False})
        w.atomic_write_json(path,snap)
        journal={'schema':'hq-web-health-probe-registration-journal/v1','source':pin,'before':before,'after':w.file_digest(root,str(path.relative_to(root))),'backup':w.file_digest(root,str(backup.relative_to(root))),'event':event,'message_sent':False,'external_permission_issued':False}
        w.atomic_write_json(backup.parent/'journal.json',journal)
    return {'result':'recorded','source':pin,'journal':w.file_digest(root,str((backup.parent/'journal.json').relative_to(root))),'message_sent':False,'external_permission_issued':False}
