"""Recover real owner/native assignments, without fabricating dispatch or permission.

The existing workflow journal and assignment stack are the only state stores.
Historical transport proves what happened, never a new execution authorization.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import re
import workflow_control as w

SCHEMA = 'goal-native-source-recovery/v1'


def validate(root, item, *, require_record=True):
    from goal_delivery_runtime import restore_goal, enabled, _collaboration_native
    from goal_continuity import pin_document
    task = w.validate_task_id(item.get('task_id', ''))
    snapshot = restore_goal(root, w.read_json(w.snapshot_path(root, task)))
    if not enabled(root, snapshot) or item.get('schema') != 'goal-current-assignment/v2':
        raise w.WorkflowError('bound complete goal and existing assignment schema required')
    if w.validate_workflow_events(root,task):
        raise w.WorkflowError('intact original source recovery event chain required')
    goal = snapshot['goal_delivery']
    if goal.get('source_mode') != 'owner_direct' or item.get('source_kind') not in {
            'owner_direct_native', 'historical_native_send'}:
        raise w.WorkflowError('original owner-direct source required')
    role = item.get('department')
    if role not in goal['producer_departments'] or item.get('scope') not in goal['authorized_scope']:
        raise w.WorkflowError('recovery must retain original exact producer/scope')
    if item.get('authorization_pin') != goal['authorization_pin']:
        raise w.WorkflowError('recovery original authorization differs')
    human = pin_document(root, goal['authorization_pin'])
    page = _collaboration_native(root, item['actual_native_invocation'])
    sender = item.get('sender_department')
    registry = w.department_registry(root)
    binding = registry.get(sender, {}).get('chat_binding', {})
    if any(page.get('thread', {}).get(k) != binding.get(v) for k, v in
           {'id':'task_id', 'title':'title', 'cwd':'cwd'}.items()):
        raise w.WorkflowError('real fixed source identity required')
    auth = goal['human_authorization']
    if auth['source_thread_id']!=page.get('thread',{}).get('id'):
        raise w.WorkflowError('original human authorization must belong to the real source chat')
    messages = [(t, m) for t in page.get('turns', []) for m in t.get('items', [])
                if m.get('type') == 'userMessage' and m.get('id') == auth['message_id']]
    if len(messages) != 1 or messages[0][1] != human.get('message'):
        raise w.WorkflowError('one original native human authorization required')
    original = item.get('original_task_id')
    if original != (goal.get('original_parent_reference_task_id') or task):
        raise w.WorkflowError('original task reference cannot be rewritten')
    if item['source_kind'] == 'owner_direct_native':
        if role != sender or role != goal['primary_owner']:
            raise w.WorkflowError('owner-direct intake only restores the real primary executor')
        source_id = auth['message_id']
        source_turn = messages[0][0]
    else:
        if sender != goal['primary_owner']:
            raise w.WorkflowError('real original primary collaboration sender required')
        calls = [(t, c) for t in page.get('turns', []) for c in t.get('items', [])
                 if c.get('type') == 'mcpToolCall' and c.get('id') == item.get('source_call_id')
                 and c.get('server') == 'codex_app' and c.get('tool') == 'send_message_to_thread']
        if len(calls) != 1:
            raise w.WorkflowError('one original native invocation required')
        source_turn, call = calls[0]
        target = registry[role]['chat_binding']['task_id']
        payload = item.get('payload', {})
        if w.file_digest(root, payload.get('path','')) != payload:
            raise w.WorkflowError('historical exact message bytes changed')
        body = w.safe_path(root, payload['path']).read_text(encoding='utf-8')
        sent = _collaboration_native(root, item['actual_native_send'])
        if (call.get('status') != 'completed' or call.get('error')
                or call.get('truncated', False) is not False or source_turn.get('error')
                or call.get('arguments', {}).get('threadId') != target
                or call['arguments'].get('prompt') != body or sent.get('threadId') != target
                or not re.search(r'(?<![A-Za-z0-9_-])'+re.escape(original)+r'(?![A-Za-z0-9_-])',body)):
            raise w.WorkflowError('successful exact original transport required')
        source_id = call['id']
    identity = {k:item[k] for k in ('task_id','department','scope','source_kind','original_task_id')}
    identity.update(authorization_pin=goal['authorization_pin'], source_id=source_id)
    key = w.sha256_value(identity)
    rows = [r for r in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS)
            if r.get('task_id') == task and r.get('details',{}).get('native_source_recovery_key') == key]
    if require_record:
        if len(rows) != 1 or rows[0]['details'].get('native_source_recovery') != item:
            raise w.WorkflowError('one committed real source recovery required; no substituted proof')
    return snapshot, {'receipt_id': None, 'receipt_type':'native_source_recovered',
        'actual_source_id':source_id, 'source_turn_id':source_turn.get('id'),
        'source_turn_started_at':source_turn.get('startedAt'),
        'original_task_id':original, 'recovery_key':key,
        'recovery_event_id':rows[0]['event_id'] if rows else None,
        'created_at':rows[0]['created_at'] if rows else None,
        'dispatch_fabricated':False, 'policy_fabricated':False,
        'external_permission_issued':False}


def record(root, input_path):
    from goal_continuity import record_assignment
    pin = w.file_digest(root, input_path)
    item = w.read_json(w.safe_path(root,input_path))
    with w.workflow_lock(root):
        snapshot, proof = validate(root,item,require_record=False)
        rows = [r for r in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS)
                if r.get('task_id') == item['task_id'] and
                r.get('details',{}).get('native_source_recovery_key') == proof['recovery_key']]
        if rows:
            if len(rows) != 1 or rows[0]['details'].get('native_source_recovery') != item:
                raise w.WorkflowError('existing recovery is immutable; retain its original bytes')
        else:
            w.append_workflow_event(root,item['task_id'],snapshot['current_state'],
                {'native_source_recovery_key':proof['recovery_key'],'native_source_recovery':item,
                 'dispatch_fabricated':False,'external_permission_issued':False})
    if item.get('restore_position')=='suspended':
        with w.workflow_lock(root):
            validate(root,item)
            path=Path(root)/'data/department-current-assignment.json'
            current=w.read_json(path)
            stack=current.setdefault('suspended_assignments',{}).setdefault(item['department'],[])
            duplicate=pin in stack
            if not duplicate:
                stack.append(pin);w.atomic_write_json(path,current)
            assignment={'result':'duplicate_ignored' if duplicate else 'recorded',
                        'restore_position':'suspended','actual_message_delivered':True}
    else:
        if item.get('restore_position') not in {None,'current'}:
            raise w.WorkflowError('explicit current or suspended recovery position required')
        assignment = record_assignment(root,item,pin)
    return {**assignment,'source_recovery':validate(root,item)[1],
            'historical_task_reopened':False,'external_permission_issued':False}


def adoption_notice_message(root, request):
    """A frozen factual return to the original producer, never a new task grant."""
    from goal_delivery_runtime import restore_goal
    from result_coordination import _committed_result
    task = w.validate_task_id(request.get('task_id', ''))
    snapshot = restore_goal(root, w.read_json(w.snapshot_path(root, task)))
    goal = snapshot['goal_delivery']
    source = request.get('post_adoption_notice', {})
    if (request.get('sender_department') not in {'operations', goal['responsible_assistant']}
            or request.get('target_department') != goal['primary_owner']
            or request.get('action_class') != 'thread_message'
            or request.get('scope') not in goal['authorized_scope']
            or not isinstance(source, dict)):
        raise w.WorkflowError('same-goal factual return to original producer required')
    pin = source.get('journal', {})
    if not isinstance(pin, dict) or w.file_digest(root, pin.get('path', '')) != pin:
        raise w.WorkflowError('exact actual adoption journal required')
    journal = w.read_json(w.safe_path(root, pin['path']))
    if (journal.get('task_id') != task or journal.get('actor') != goal['responsible_assistant']
            or journal.get('status') != 'complete' or journal.get('direction') != 'forward'
            or type(journal.get('external_writes')) is not int or journal['external_writes'] != 0
            or journal.get('effect_uncertain') is not False or journal.get('permissions_issued') is not False
            or not journal.get('execution_id')):
        raise w.WorkflowError('actual zero-external-write adoption fact required')
    operations = journal.get('source_operations', [])
    if (not isinstance(operations, list) or not 1 <= len(operations) <= 32
            or len({o.get('path') for o in operations if isinstance(o, dict)}) != len(operations)):
        raise w.WorkflowError('bounded actual adopted source operations required')
    for op in operations:
        if (not isinstance(op, dict) or not op.get('path')
                or op.get('write_attempted') is not True or op.get('verified_after') is not True
                or op.get('after_expected') != op.get('after_actual')
                or {k:w.file_digest(root, op['path'])[k] for k in ('sha256','size')} != op.get('after_actual')
                or w.file_digest(root, op.get('backup', {}).get('path', '')) != op.get('backup')
                or {k:op['backup'][k] for k in ('sha256','size')} != op.get('before')):
            raise w.WorkflowError('actual current adopted source and physical backup readback required')
    rows = w._result_handoff_rows(root, task)
    decisions = [r for r in rows if r.get('event') == 'controller_decision'
                 and r.get('record_id') == journal.get('decision_record_id')]
    follows = [r for r in rows if r.get('event') == 'controller_followthrough'
               and r.get('record_id') == source.get('followthrough_record_id')]
    if (len(decisions) != 1 or len(follows) != 1
            or decisions[0].get('decision') != 'continue'
            or any(r.get('coordinator_role') != goal['responsible_assistant'] for r in (decisions[0], follows[0]))
            or decisions[0].get('sender_department') != goal['primary_owner']
            or any(decisions[0].get(k) != follows[0].get(k) for k in
                   ('task_id', 'sender_department', 'candidate_version', 'result_sha256'))
            or decisions[0].get('candidate_version') != journal.get('candidate_version')
            or pin not in follows[0].get('evidence', [])
            or not str(follows[0].get('unblock_condition', '')).startswith(
                'source-adopted:' + journal['execution_id'] + ';')):
        raise w.WorkflowError('exact committed adoption decision and followthrough required')
    for row in (decisions[0], follows[0]):
        _committed_result(root, row)
    expected_id = 'notify-adoption-' + w.sha256_value(
        [task, request['sender_department'], request['target_department'], pin])
    if request.get('action_id') != expected_id:
        raise w.WorkflowError('deterministic original adoption notice identity required')
    return {'task_id': task, 'purpose': 'same_goal_source_adoption_notice',
            'sender_department': request['sender_department'],
            'target_department': goal['primary_owner'], 'scope': request['scope'],
            'source_adoption': pin, 'execution_id': journal['execution_id'],
            'candidate_version': journal['candidate_version'],
            'decision_record_id': decisions[0]['record_id'],
            'followthrough_record_id': follows[0]['record_id'],
            'source_adopted': True, 'business_goal_completed': False,
            'external_permission_issued': False, 'new_assignment_authorized': False,
            'next_action': '读取已采用证据和本部门真实当前／暂停指派，继续已获授权的未完范围；不重做已采用源码，不重复保存或派工。本通知不新增任务、账号、费用或生产权限。'}


def _prepare_adoption_notice(root, request):
    """Reuse approved_actions/event storage for an exact factual callback."""
    from goal_delivery_runtime import restore_goal
    body = adoption_notice_message(root, request)
    expected = (json.dumps(body, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode('utf-8')
    if w.safe_path(root, request['payload']['path']).read_bytes() != expected:
        raise w.WorkflowError('factual adoption notice cannot contain arbitrary new instructions')
    fields = ('task_id', 'sender_department', 'action_id', 'action_class', 'scope',
              'source_project_id', 'target_project_id', 'target_department', 'target_thread_id',
              'target_thread_title', 'target_cwd', 'target_sidebar_section_id',
              'payload_sha256', 'payload', 'post_adoption_notice')
    action = {k: request[k] for k in fields}
    registry = w.department_registry(root)
    binding = registry[request['target_department']]['chat_binding']
    source_binding = registry[request['sender_department']]['chat_binding']
    if request.get('source_project_id') != source_binding.get('project_id'):
        raise w.WorkflowError('exact original callback sender project required before preparation')
    if any(request.get(k) != binding.get(v) for k,v in
           {'target_thread_id':'task_id','target_thread_title':'title','target_project_id':'project_id',
            'target_cwd':'cwd','target_sidebar_section_id':'sidebar_section_id'}.items()):
        raise w.WorkflowError('exact original producer callback binding required')
    with w.workflow_lock(root):
        # Recheck the committed fact immediately before the existing preparation event.
        if adoption_notice_message(root, request) != body:
            raise w.WorkflowError('adoption callback source changed during preparation')
        snapshot = restore_goal(root, w.read_json(w.snapshot_path(root, request['task_id'])))
        goal = snapshot['goal_delivery']
        # One factual return is owned once across HQ and its responsible assistant.
        # A prepared uncertain call also blocks another sender; it must be recovered,
        # not delivered twice with a different sender-specific action identifier.
        same_fact = [a for a in goal.get('approved_actions', [])
                     if a.get('target_department') == request['target_department']
                     and a.get('post_adoption_notice', {}).get('journal') ==
                         request['post_adoption_notice']['journal']]
        action_ids = {a['action_id'] for a in same_fact}
        sent = [row for row in w.read_jsonl(w.receipts_path(root, request['task_id']))
                if row.get('receipt_type') == 'dispatch_sent' and row.get('action_id') in action_ids
                and row.get('department') == request['target_department']]
        if sent:
            return {'status':'duplicate_ignored','actual_message_sent':True,
                    'actual_receipt_ids':[row['receipt_id'] for row in sent],
                    'historical_notice_count':len(sent),'message_sent':False}
        different_owner = [a for a in same_fact if a.get('action_id') != request['action_id']]
        if different_owner:
            return {'status':'waiting_existing_callback_effect','message_sent':False,
                    'recovery_owner':different_owner[0]['sender_department'],
                    'notification_responsibility_retained':True}
        old = [a for a in goal.get('approved_actions', []) if a.get('action_id') == action['action_id']]
        if old:
            if old != [action]:
                raise w.WorkflowError('original adoption notice already frozen to different bytes')
            return
        snapshot['goal_delivery'] = {**goal, 'approved_actions': goal.get('approved_actions', []) + [action]}
        w.append_workflow_event(root, request['task_id'], snapshot['current_state'],
                                {'goal_delivery': snapshot['goal_delivery'],
                                 'post_adoption_notice_prepared': request['payload'],
                                 'actual_message_sent': False, 'external_permission_issued': False})
        w.atomic_write_json(w.snapshot_path(root, request['task_id']), snapshot)


def prepare_message(root, request):
    """The real preparation entry consumes authorization and exact policy checks."""
    from goal_delivery_runtime import authorization_precheck, _collaboration_native
    checked = authorization_precheck(root,request['task_id'],request)
    if checked['status'] != 'within_original_authorization':
        return {'status':'blocked','authorization_precheck':checked,'message_sent':False}
    payload = request['payload']
    if w.file_digest(root,payload.get('path','')) != payload or payload['sha256'] != request.get('payload_sha256'):
        raise w.WorkflowError('exact prepared message required')
    if request.get('assignment_record_required'):
        body=w.safe_path(root,payload['path']).read_text(encoding='utf-8')
        if not re.search(r'(?<![A-Za-z0-9_-])'+re.escape(request['task_id'])+r'(?![A-Za-z0-9_-])',body):
            raise w.WorkflowError('assignment message must identify original task before policy or send')
    page = _collaboration_native(root,request['actual_target_state'])
    registry=w.department_registry(root)
    binding=registry.get(request['target_department'],{}).get('chat_binding')
    external_target=binding is None
    if binding is None:
        external=w.read_json(Path(root)/'data/department-registry.json').get('collaboration_bindings',{}).get(request['target_department'])
        if not external or request['target_department'] not in {
                d.get('target_department') for d in w.read_json(w.snapshot_path(root,request['task_id']))
                .get('goal_delivery',{}).get('collaboration_scopes',[])}:
            raise w.WorkflowError('original explicitly declared collaboration target required')
        binding={**external,'task_id':external['thread_id']}
    if any(page.get('thread',{}).get(k) != binding.get(v) for k,v in
           {'id':'task_id','title':'title','cwd':'cwd'}.items()):
        raise w.WorkflowError('actual target fixed identity differs')
    turns = page.get('turns',[])
    if not turns:
        raise w.WorkflowError('real latest target turn required; notLoaded is not idle')
    if turns[0].get('status') in {'inProgress','pending'}:
        return {'status':'waiting_target_completion','message_sent':False,
                'notification_responsibility_retained':True,'authorization_precheck':checked}
    if 'post_adoption_notice' in request:
        existing = _prepare_adoption_notice(root, request)
        if existing is not None:
            return {**existing, 'authorization_precheck':checked,'external_permission_issued':False}
    if external_target:
        from goal_delivery_runtime import restore_goal, approved_action
        snapshot=restore_goal(root,w.read_json(w.snapshot_path(root,request['task_id'])))
        action_keys=('task_id','sender_department','action_id','action_class','scope','source_project_id',
                     'target_project_id','target_department','target_thread_id','target_thread_title',
                     'target_cwd','target_sidebar_section_id','payload_sha256')
        action=approved_action(root,snapshot,{k:request[k] for k in action_keys})
        if not action:raise w.WorkflowError('existing exact approved collaboration action required')
        inventory_pin=request.get('actual_live_inventory')
        observed=w._parse_observed_at(request.get('live_observed_at'))
        import datetime as dt
        if not inventory_pin or observed is None or not 0<=(dt.datetime.now(dt.timezone.utc)-observed).total_seconds()<=300:
            return {'status':'fresh_collaboration_observation_required','message_sent':False,
                    'next_action':'read_actual_fixed_sender_and_target_inventory_then_prepare_same_action',
                    'authorization_precheck':checked,'new_human_approval_required':False}
        inventory=_collaboration_native(root,inventory_pin)
        source=registry[request['sender_department']]['chat_binding']
        selected=[]
        for fixed in [source,binding]:
            rows=[x for x in [*inventory.get('threads',[]),*inventory.get('pinnedThreads',[])] if x.get('id')==fixed['task_id']]
            if len(rows)!=1 or any(rows[0].get(k)!=fixed[v] for k,v in
                    {'projectId':'project_id','title':'title','cwd':'cwd'}.items()):
                raise w.WorkflowError('fresh actual collaboration sender and target identities required')
            selected.append(rows[0])
        live={'observed_at':request['live_observed_at'],'threads':selected,'actual_native_observation':inventory_pin,
              'native_receipt_ref':inventory_pin['path'],
              'target_sidebar_section_id':request['target_sidebar_section_id']}
        path=Path(root)/'logs/goal-delivery-observations'/request['task_id']/(w.sha256_value(live)+'.json')
        if not path.exists():w.atomic_write_json(path,live)
        live_pin=w.file_digest(root,str(path.relative_to(root)))
        with w.workflow_lock(root):
            snapshot=restore_goal(root,w.read_json(w.snapshot_path(root,request['task_id'])))
            goal=snapshot['goal_delivery'];observations={**goal.get('current_route_observations',{}),request['action_id']:live_pin}
            snapshot['goal_delivery']={**goal,'current_route_observations':observations}
            w.append_workflow_event(root,request['task_id'],snapshot['current_state'],
                {'goal_delivery':snapshot['goal_delivery'],'actual_route_observation':live_pin,'external_permission_issued':False})
            w.atomic_write_json(w.snapshot_path(root,request['task_id']),snapshot)
    if request['action_id']=='assign-goal-review:'+request['task_id']:
        from goal_delivery_runtime import restore_goal
        with w.workflow_lock(root):
            snapshot=restore_goal(root,w.read_json(w.snapshot_path(root,request['task_id'])))
            goal=snapshot['goal_delivery'];contract=snapshot.get('goal_contract')
            body=w.safe_path(root,payload['path']).read_text()
            if (request['sender_department']!='operations'
                    or request['target_department']!=goal['responsible_assistant']
                    or not contract or w.file_digest(root,contract['path'])!=contract
                    or request['task_id'] not in body or contract['path'] not in body):
                raise w.WorkflowError('original contract-linked initial responsibility message required')
            rows=[e for e in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS) if e.get('task_id')==request['task_id']
                  and e.get('details',{}).get('initial_responsibility_message')]
            source={'payload':payload,'goal_contract':contract,'sender_department':'operations',
                    'target_department':goal['responsible_assistant'],'scope':request['scope'],
                    'external_permission_issued':False}
            if rows and (len(rows)!=1 or rows[0]['details']['initial_responsibility_message']!=source):
                raise w.WorkflowError('initial responsibility message already frozen; no replacement or resend')
            if not rows:
                w.append_workflow_event(root,request['task_id'],snapshot['current_state'],
                                        {'initial_responsibility_message':source})
    fields = {k:request[k] for k in ('task_id','action_id','action_class','scope','source_project_id',
        'target_project_id','target_department','target_thread_id','target_thread_title','target_cwd',
        'target_sidebar_section_id','payload_sha256')}
    policy,_ = w.policy_check(root,department=request['sender_department'],**fields)
    return {'status':'ready_to_send' if policy['status']=='allow' else 'blocked',
            'authorization_precheck':checked,'policy_decision':policy,
            'payload':payload,'message_sent':False,'external_permission_issued':False}


def initial_responsibility_payload(root, snapshot, sender, target, scope, payload_sha256):
    rows=[e for e in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS) if e.get('task_id')==snapshot.get('task_id')
          and e.get('details',{}).get('initial_responsibility_message')]
    if len(rows)!=1 or w.validate_workflow_events(root,snapshot['task_id']):return False
    record=rows[0]['details']['initial_responsibility_message'];pin=record['payload']
    goal=snapshot['goal_delivery'];contract=snapshot.get('goal_contract')
    return (sender=='operations' and target==goal['responsible_assistant']
            and scope in goal['authorized_scope'] and record['scope']==scope
            and record['sender_department']==sender and record['target_department']==target
            and record['goal_contract']==contract and w.file_digest(root,contract['path'])==contract
            and w.file_digest(root,pin['path'])==pin and pin['sha256']==payload_sha256
            and record['external_permission_issued'] is False)


def initial_assignment_source(root,snapshot,dispatch,contract):
    """Consume a committed actual assignment; no new QA or dispatch reconstruction."""
    from goal_continuity import pin_document, _dispatch_source
    rows=[e.get('details',{}).get('initial_responsibility_assignment_source')
          for e in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS) if e.get('task_id')==snapshot['task_id']
          and e.get('details',{}).get('initial_responsibility_assignment_source')]
    if not rows:return False
    if len(rows)!=1:raise w.WorkflowError('one original responsibility assignment source required')
    item=pin_document(root,rows[0]);_,actual=_dispatch_source(root,item)
    if actual!=dispatch:return False
    return (item['department']==snapshot['goal_delivery']['responsible_assistant']
            and initial_responsibility_payload(root,snapshot,item['sender_department'],item['department'],
                    dispatch['scope'],item['payload']['sha256'])
            and contract==snapshot.get('goal_contract'))


def actual_target_turn_status(root, live, inventory_row, binding):
    """Resolve a notLoaded/cache label only with a newer real fixed-thread read."""
    from goal_delivery_runtime import _collaboration_native
    pins=live.get('actual_native_target_turns',{})
    if not isinstance(pins,dict):raise w.WorkflowError('exact native target turns must be a mapping')
    pin=pins.get(binding.get('task_id'),live.get('actual_native_target_turn'))
    status=inventory_row.get('status')
    status=status.get('type') if isinstance(status,dict) else status
    if pin is None:return status
    page=_collaboration_native(root,pin)
    if any(page.get('thread',{}).get(k)!=binding.get(v) for k,v in
           {'id':'task_id','title':'title','cwd':'cwd'}.items()):
        raise w.WorkflowError('exact native notification target turn identity required')
    turns=page.get('turns',[])
    if not turns:return 'unknown_target'
    turn=turns[0]
    if turn.get('status') in {'inProgress','pending'}:return 'active'
    previous,current=inventory_row.get('updatedAt'),page['thread'].get('updatedAt')
    if (status=='idle' and turn.get('status') in {'completed','interrupted','failed'}
            and previous is None and current is None):
        return 'idle'
    if (type(previous) not in {int,float} or type(current) not in {int,float} or current<previous):
        return 'unknown_target'
    if turn.get('status') in {'completed','interrupted','failed'}:
        # Idle means no active turn, not successful completion or healthy source.
        return 'idle'
    return 'unknown_target'


def recovered_producer_source(root,snapshot,role):
    """Real restored assignment replaces missing local ACK metadata, not QA."""
    if role not in snapshot.get('goal_delivery',{}).get('producer_departments',[]):return None
    records=[e.get('details',{}).get('native_source_recovery')
             for e in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS) if e.get('task_id')==snapshot['task_id']
             and e.get('details',{}).get('native_source_recovery',{}).get('department')==role]
    if not records:return None
    proofs=[validate(root,item)[1] for item in records]
    return {'actual_sources':proofs,'dispatch_or_ACK_fabricated':False,'external_permission_issued':False}


def collaboration_source(root, record):
    """Admit an already performed collaboration as facts, never as a new permit."""
    from goal_delivery_runtime import restore_goal, _collaboration_native, enabled
    task=record.get('task_id');snapshot=restore_goal(root,w.read_json(w.snapshot_path(root,task)))
    if not enabled(root,snapshot) or record.get('source_kind')!='historical_native_collaboration':
        raise w.WorkflowError('exact historical complete-goal collaboration required')
    goal=snapshot['goal_delivery'];owner=goal['primary_owner'];sender=record['sender_department']
    binding=w.read_json(Path(root)/'data/department-registry.json').get('collaboration_bindings',{}).get(sender,{})
    if not binding or record.get('scope') not in goal['authorized_scope']:
        raise w.WorkflowError('original exact collaboration binding and scope required')
    base={**record,'schema':'goal-current-assignment/v2','department':owner,'sender_department':owner,
          'source_kind':'owner_direct_native','authorization_pin':goal['authorization_pin']}
    validate(root,base,require_record=False)
    human=w.read_json(w.safe_path(root,goal['authorization_pin']['path']))
    human_text=''.join(x.get('text','') for x in human['message'].get('content',[]) if x.get('type')=='text')
    if binding.get('title','') not in human_text:
        raise w.WorkflowError('original human source must explicitly name the existing collaborator')
    page=_collaboration_native(root,record['actual_native_invocation'])
    calls=[c for t in page.get('turns',[]) for c in t.get('items',[])
           if c.get('id')==record.get('source_call_id') and c.get('type')=='mcpToolCall'
           and c.get('server')=='codex_app' and c.get('tool')=='send_message_to_thread']
    payload=record['payload'];body=w.safe_path(root,payload['path']).read_text()
    versions=set(re.findall(r'''(?<![A-Za-z0-9_-])(?:candidate_version|候选(?:版本)?)[`"']?\s*[:=：]?\s*[`"']?\s*([A-Za-z0-9][A-Za-z0-9+._-]{0,199})''',body))
    if versions!={record['candidate_version']}:
        raise w.WorkflowError('one explicit original candidate-version identity required, not an ordinary word')
    sent=_collaboration_native(root,record['actual_native_send'])
    if (len(calls)!=1 or calls[0].get('status')!='completed' or calls[0].get('error')
            or calls[0].get('truncated',False) is not False or w.file_digest(root,payload['path'])!=payload
            or calls[0]['arguments'].get('threadId')!=binding['thread_id']
            or calls[0]['arguments'].get('prompt')!=body or sent.get('threadId')!=binding['thread_id']
            or not re.search(r'(?<![A-Za-z0-9+._-])'+re.escape(record['original_task_id'])+r'(?![A-Za-z0-9+._-])',body)
            or not re.search(r'(?<![A-Za-z0-9+._-])'+re.escape(record['candidate_version'])+r'(?![A-Za-z0-9+._-])',body)):
        raise w.WorkflowError('original exact successful collaboration send required')
    final=_collaboration_native(root,record['actual_native_result'])
    if any(final.get('thread',{}).get(k)!=binding.get(v) for k,v in
           {'id':'thread_id','title':'title','cwd':'cwd'}.items()):
        raise w.WorkflowError('real completed collaborator identity differs')
    turns=[t for t in final.get('turns',[]) if t.get('id')==record.get('source_turn_id')
           and t.get('status')=='completed' and not t.get('error')]
    messages=[m for t in turns for m in t.get('items',[]) if m.get('id')==record.get('source_message_id')
              and m.get('type')=='agentMessage' and m.get('phase')=='final_answer']
    reply=record['visible_reply'];result=record['result']
    if (len(messages)!=1 or w.file_digest(root,reply['path'])!=reply
            or w.safe_path(root,reply['path']).read_bytes()!=messages[0]['text'].encode()
            or w.file_digest(root,result['path'])!=result):
        raise w.WorkflowError('original frozen collaborator final and result bytes required')
    origin=Path(record['result_origin_path']).resolve();project=Path(binding['cwd']).resolve()
    if (not origin.is_relative_to(project) or 'reports' not in origin.relative_to(project).parts
            or str(origin) not in messages[0]['text']
            or origin.read_bytes()!=w.safe_path(root,result['path']).read_bytes()):
        raise w.WorkflowError('only the actual explicitly linked collaborator report can be recovered')
    action={'task_id':task,'action_id':record['action_id'],'action_class':'thread_message',
            'scope':record['scope'],'target_department':sender,'target_thread_id':binding['thread_id'],
            'payload_sha256':payload['sha256'],'source_recovered':True,'new_permissions':0}
    return {'task_id':task,'action_id':record['action_id'],'department':sender,'threadId':binding['thread_id'],
            'proof_state':'PROVEN','status':'result_received','approved_action':action,
            'result':result,'visible_reply':reply,'native_result':record['actual_native_result'],
            'native_transport':record['actual_native_send'],'original_invocation':record['actual_native_invocation'],
            'policy_decision_id':None,'historical_policy_fabricated':False,'source_recovered':True,
            'proves_completion':False,'proves_next_action':False}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',default=str(Path(__file__).resolve().parents[1]))
    p.add_argument('command',choices=['recover-source','prepare-message'])
    p.add_argument('--input',required=True)
    a=p.parse_args();root=Path(a.root).resolve()
    result=record(root,a.input) if a.command=='recover-source' else prepare_message(root,w.read_json(w.safe_path(root,a.input)))
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__ == '__main__': main()
