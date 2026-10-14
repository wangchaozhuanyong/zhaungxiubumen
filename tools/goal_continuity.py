"""Complete-goal continuation using existing receipts, claims and event journals.

No provider calls, production permissions, invented sends or assistant verdicts.
"""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import time
import workflow_control as w

ASSIGNMENT_SCHEMA = 'goal-current-assignment/v2'
READY_MARKER = 'FLASHCAST_DELIVERY_READY '


def pin_document(root, pin):
    if not isinstance(pin, dict) or w.file_digest(root, pin.get('path', '')) != pin:
        raise w.WorkflowError('exact project-local continuity source changed')
    return w.read_json(w.safe_path(root, pin['path']))


def native(root, pin):
    from goal_delivery_runtime import _collaboration_native
    return _collaboration_native(root, pin)


def _task(root, task):
    from goal_delivery_runtime import restore_goal, enabled
    snapshot = restore_goal(root, w.read_json(w.snapshot_path(root, task)))
    if snapshot.get('task_id') != task or not enabled(root, snapshot):
        raise w.WorkflowError('exact complete goal required')
    return snapshot


def _dispatch_source(root, item):
    if item.get('source_kind') in {'owner_direct_native','historical_native_send'}:
        from goal_source_recovery import validate
        return validate(root,item)
    task, role = item['task_id'], item['department']
    snapshot = _task(root, task)
    registry = w.department_registry(root)
    binding = registry.get(role, {}).get('chat_binding', {})
    goal = snapshot['goal_delivery']
    if role not in {*goal['producer_departments'], goal['responsible_assistant']}:
        raise w.WorkflowError('assignment department outside original goal')
    sender = item.get('sender_department')
    if sender not in {'operations', goal['responsible_assistant'], goal['primary_owner']}:
        raise w.WorkflowError('original authorized assignment sender required')
    payload = item['payload']; pin_document(root, item['actual_native_invocation'])
    if w.file_digest(root, payload.get('path', '')) != payload:
        raise w.WorkflowError('actual consumed assignment bytes changed')
    body = w.safe_path(root, payload['path']).read_text(encoding='utf-8')
    if not re.search(r'(?<![A-Za-z0-9_-])'+re.escape(task)+r'(?![A-Za-z0-9_-])', body):
        raise w.WorkflowError('assignment message must identify original task')
    # Select the actual invocation from its immutable page. Unrelated failed
    # tools in that same turn do not invalidate a successful dispatched call.
    page = pin_document(root,item['actual_native_invocation'])
    if 'content' in page:
        texts=[x['text'] for x in page['content'] if x.get('type')=='text']
        if page.get('isError') or len(texts)!=1:raise w.WorkflowError('successful actual sender page required')
        page=json.loads(texts[0])
    source = registry.get(sender, {}).get('chat_binding', {})
    if any(page.get('thread', {}).get(k) != source.get(v) for k,v in
           {'id':'task_id','title':'title','cwd':'cwd'}.items()):
        raise w.WorkflowError('actual fixed assignment sender identity differs')
    calls = [(t,c) for t in page.get('turns', []) for c in t.get('items', [])
             if c.get('type') == 'mcpToolCall' and c.get('server') == 'codex_app'
             and c.get('tool') == 'send_message_to_thread'
             and c.get('id') == item.get('source_call_id')]
    if (len(calls) != 1 or calls[0][1].get('status') != 'completed'
            or calls[0][1].get('error') or calls[0][0].get('error')
            or calls[0][1].get('truncated',False) is not False
            or calls[0][1].get('arguments', {}).get('threadId') != binding.get('task_id')
            or calls[0][1].get('arguments', {}).get('prompt') != body):
        raise w.WorkflowError('one actual successful original assignment invocation required')
    from qa_review_plan import _review_same_goal_send_wrapper
    sent = _review_same_goal_send_wrapper(pin_document(root,item['actual_native_send']))
    if sent['thread_id'] != binding.get('task_id') or sent['exact_consumed_prompt'] != payload:
        raise w.WorkflowError('assignment successful send and exact bytes differ')
    # Authenticate the dispatch prefix, not future verdicts which themselves
    # depend on this proof. Later task events are checked by their consumers.
    through=item.get('dispatch_receipt_id')
    if not through:
        candidates=[r for r in w.read_jsonl(w.receipts_path(root,task))
                    if r.get('idempotency_key')==item.get('dispatch_idempotency_key')]
        if len(candidates)!=1:raise w.WorkflowError('one original dispatch boundary required')
        through=candidates[0]['receipt_id']
    rows, bad = w._validate_receipt_chain(root, task,through_receipt_id=through)
    selected = [r for r in rows if r.get('receipt_type') == 'dispatch_sent'
                and r.get('department') == role
                and (r.get('receipt_id') == item.get('dispatch_receipt_id')
                     or r.get('idempotency_key') == item.get('dispatch_idempotency_key'))]
    if bad or len(selected) != 1 or selected[0].get('chat_task_id') != binding.get('task_id'):
        raise w.WorkflowError('original actual dispatch receipt required')
    policies = [p for p in w.read_jsonl(Path(root)/w.POLICY_DECISIONS)
                if p.get('decision_id') == selected[0].get('policy_decision_id')]
    approved_payload=item.get('approved_payload',payload)
    if approved_payload!=payload:
        if goal.get('required_execution_actions'):
            raise w.WorkflowError('production assignment payload must remain exact')
        if w.file_digest(root,approved_payload.get('path',''))!=approved_payload:
            raise w.WorkflowError('original approved framing bytes changed')
        approved_body=w.safe_path(root,approved_payload['path']).read_text(encoding='utf-8')
        if approved_body not in {body+'\n',body+'\r\n'}:
            raise w.WorkflowError('only explicit terminal line framing normalization allowed')
    if len(policies) != 1 or any(policies[0].get(k) != v for k,v in
           {'status':'allow','task_id':task,'department':sender,'target_department':role,
            'target_thread_id':binding['task_id'],'payload_sha256':approved_payload['sha256']}.items()):
        raise w.WorkflowError('assignment exact existing allowed policy required')
    if w.file_digest(root, goal['authorization_pin']['path']) != goal['authorization_pin']:
        raise w.WorkflowError('original human authorization changed')
    return snapshot, selected[0]


def record_assignment(root, item, input_pin):
    if item.get('schema') != ASSIGNMENT_SCHEMA:
        raise w.WorkflowError('known current assignment declaration required')
    if pin_document(root,input_pin)!=item:raise w.WorkflowError('current assignment declaration bytes differ')
    _, dispatch_source = _dispatch_source(root, item)
    path = Path(root)/'data/department-current-assignment.json'
    with w.workflow_lock(root):
        _dispatch_source(root, item)
        current = w.read_json(path) or {'assignments':{}}
        role = item['department']; prior = current.setdefault('assignments', {}).get(role)
        if dispatch_source.get('action_id')=='assign-goal-review:'+item['task_id']:
            sources=[e.get('details',{}).get('initial_responsibility_assignment_source')
                     for e in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS) if e.get('task_id')==item['task_id']
                     and e.get('details',{}).get('initial_responsibility_assignment_source')]
            if sources and sources!=[input_pin]:
                raise w.WorkflowError('initial responsibility source cannot be replaced')
            if not sources:
                w.append_workflow_event(root,item['task_id'],_task(root,item['task_id'])['current_state'],
                    {'initial_responsibility_assignment_source':input_pin,'external_permission_issued':False})
        if prior == input_pin: return {'result':'duplicate_ignored','actual_message_delivered':True}
        if prior:
            old = pin_document(root, prior)
            old_task = old.get('task_id')
            if old_task and old_task != item['task_id']:
                archived = current.setdefault('suspended_assignments', {}).setdefault(role, [])
                if prior not in archived: archived.append(prior)
        current['assignments'][role] = input_pin
        current['schema'] = ASSIGNMENT_SCHEMA
        w.atomic_write_json(path, current)
    return {'result':'recorded','actual_message_delivered':True,'permissions_inherited':False}


def current_assignment(root, role, pin):
    item = pin_document(root, pin)
    if item.get('schema') != ASSIGNMENT_SCHEMA: return None
    snapshot, dispatch = _dispatch_source(root,item)
    if item.get('department') != role: raise w.WorkflowError('current assignment role differs')
    from goal_delivery_runtime import completion_obligations
    if snapshot.get('current_state') == 'closed':
        complete = completion_obligations(root,snapshot)
        if not complete['missing'] and not complete['blockers']:
            return {'task_id':item['task_id'],'state':'completed_exact_scope',
                    'resume_required':False,'business_goal_closed':complete['business_goal_closed']}
    return {**item,'source':pin,'actual_message_delivered':True,'resume_required':True,
            'resume_before_old_automation_or_summary':True,'permissions_inherited':False,
            'native_workflow_state':snapshot.get('current_state'),
            'dispatch_receipt_id':dispatch['receipt_id'],
            'actual_source_receipt':dispatch if dispatch.get('receipt_type')=='native_source_recovered' else None}


def ready_source(root, request, fixed_id, *, scheduled=False):
    """A frozen batch declaration can be handed off before its turn terminates."""
    task=request['task_id'];sender=request['sender_department']
    if scheduled:
        source=w.scheduled_result_source(root,task,sender)
        if (not source or source.get('legacy_contract') or request.get('source_automation_id')!=source['automation_id']):
            raise w.WorkflowError('exact admitted current daily source required')
        goal={'producer_departments':[sender],'responsible_assistant':source['responsible_assistant']}
    else:
        snapshot=_task(root,task)
        goal=snapshot['goal_delivery']
    if sender not in {*goal['producer_departments'],goal['responsible_assistant']}:
        raise w.WorkflowError('ready source outside original goal')
    page=native(root,request['actual_native_completion'])
    binding=w.department_registry(root)[sender]['chat_binding']
    if any(page.get('thread',{}).get(k)!=binding.get(v) for k,v in
           {'id':'task_id','title':'title','cwd':'cwd'}.items()):
        raise w.WorkflowError('ready fixed source identity differs')
    selected=[(t,m) for t in page.get('turns',[]) if t.get('id')==request.get('source_turn_id')
              for m in t.get('items',[]) if m.get('type')=='agentMessage'
              and m.get('id')==request.get('source_message_id')]
    if len(selected)!=1:raise w.WorkflowError('one actual original ready declaration required')
    turn,message=selected[0];text=message.get('text','')
    if (turn.get('status') not in {'inProgress','completed'} or turn.get('error')
            or (task == 'fc-20261014-condo-faq-v7-cms-publishing-v1'
                and sender == 'operations-assistant'
                and message.get('phase') not in {'commentary','final_answer'})):
        raise w.WorkflowError('successful actual ready source turn required')
    raw=w.safe_path(root,request['visible_reply']['path']).read_bytes()
    if (w.file_digest(root,request['visible_reply']['path'])!=request['visible_reply']
            or raw!=text.encode('utf-8') or hashlib.sha256(raw).hexdigest()!=request.get('source_reply_sha256')):
        raise w.WorkflowError('exact ready declaration original UTF-8 required')
    declarations=[line[len(READY_MARKER):] for line in text.splitlines() if line.startswith(READY_MARKER)]
    if len(declarations)!=1:raise w.WorkflowError('explicit frozen complete-batch declaration required, not ACK/progress')
    try: declaration=json.loads(declarations[0])
    except ValueError as e:raise w.WorkflowError('valid exact ready declaration required') from e
    expected={k:request[k] for k in ('task_id','sender_department','candidate_version','result_sha256')}
    if any(declaration.get(k)!=v for k,v in expected.items()) or declaration.get('batch_complete') is not True:
        raise w.WorkflowError('ready declaration must bind complete batch and exact frozen result')
    outbox=request.get('outbox_path') or request.get('outbox',{}).get('path')
    pin=w.file_digest(root,outbox)
    if pin['sha256']!=request['result_sha256'] or declaration.get('outbox_path')!=outbox:
        raise w.WorkflowError('frozen ready outbox differs')
    box=w.read_json(w.safe_path(root,outbox))
    if box.get('status') in {'active','in_progress','pending',''} or not box.get('status'):
        raise w.WorkflowError('finite actual batch outcome required')
    observed=w._parse_observed_at(request.get('reply_observed_at'))
    start=turn.get('startedAt')
    rows,bad=w._validate_receipt_chain(root,task)
    prior=[r for r in rows if r.get('department')==sender and r.get('chat_task_id')==fixed_id
           and r.get('receipt_type') in {'dispatch_sent','chat_ack'}]
    prior_ok=bool(prior)
    if not scheduled and not prior_ok:
        assignment=w.read_json(Path(root)/'data/department-current-assignment.json')
        pins=[assignment.get('assignments',{}).get(sender),
              *assignment.get('suspended_assignments',{}).get(sender,[])]
        for pin in pins:
            if not pin: continue
            item=pin_document(root,pin)
            if item.get('task_id')==task and item.get('source_kind') in {'owner_direct_native','historical_native_send'}:
                _,actual_source=_dispatch_source(root,item)
                prior_ok=True
                break
    if (not scheduled and task=='fc-20261014-condo-faq-v7-cms-publishing-v1'
            and sender=='operations-assistant'):
        from qa_review_plan import load_plan, original_condo_faq_child_review_context
        plan=load_plan(root,snapshot)
        inherited=(original_condo_faq_child_review_context(root,snapshot,rows,plan)
                   if isinstance(plan,dict) and fixed_id=='<LOCAL_TASK_ID>'
                   else None)
        prior_ok=bool(observed is not None and inherited
                      and inherited.get('production_permissions_inherited') is False
                      and all(w._parse_observed_at(inherited[k]['created_at']) <= observed
                              for k in ('dispatch','ack')))
    if (bad or (not scheduled and not prior_ok) or observed is None or observed>dt.datetime.now(dt.timezone.utc)
            or type(start) not in {int,float} or start>observed.timestamp()
            or any(w._parse_observed_at(r['created_at'])>observed for r in prior)):
        raise w.WorkflowError('ready declaration requires preceding actual task dispatch/ACK')
    return {**{k:request[k] for k in ('source_turn_id','source_thread_id','source_message_id',
                'source_reply_sha256','reply_observed_at','actual_native_completion','visible_reply')},
            'result_source_phase':'delivery_ready','batch_delivery_frozen':True,
            'source_turn_completed':turn.get('status')=='completed'}


def daily_selected_assistant(root,identity,default):
    """Use the existing committed resource audit, without inventing a daily goal."""
    import result_coordination as rc
    path=w.safe_path(root,str(rc.DATABASE))
    if not path.exists():return default
    conn=sqlite3.connect('file:'+str(path)+'?mode=ro',uri=True)
    try:rows=conn.execute('SELECT payload_json FROM coordination_audit ORDER BY seq').fetchall()
    finally:conn.close()
    target=default
    for raw in rows:
        event=json.loads(raw[0]);detail=event.get('details',{})
        if (event.get('event')=='initial_assistant_selection' and event.get('identity')==identity
                and detail.get('scheduled_report_only') is True):
            if detail.get('previous_assistant')!=target:raise w.WorkflowError('daily resource assignment sequence differs')
            pin_document(root,detail['notification_source'])
            target=detail['target_assistant']
    return target


def actual_knowledge_read(root,request,proof):
    """HQ has genuinely read the conclusion; never claim a message was sent."""
    pin=request.get('actual_recipient_read');observation=pin_document(root,pin)
    def page(source):
        data=pin_document(root,source)
        if 'content' in data:
            texts=[item['text'] for item in data['content'] if item.get('type')=='text']
            if data.get('isError') or len(texts)!=1:raise w.WorkflowError('successful original native read required')
            data=json.loads(texts[0])
        return data
    invocation=page(observation['native_invocation']);source=page(observation['actual_read_result'])
    actor=w.department_registry(root)['operations']['chat_binding']
    sender=w.department_registry(root)[proof['identity']['sender_department']]['chat_binding']
    if (any(invocation.get('thread',{}).get(k)!=actor.get(v) for k,v in
            {'id':'task_id','title':'title','cwd':'cwd'}.items()) or source.get('thread',{}).get('id')!=sender['task_id']):
        raise w.WorkflowError('actual HQ reader and exact original assistant source required')
    calls=[call for turn in invocation.get('turns',[]) for call in turn.get('items',[])
           if call.get('id')==observation.get('source_call_id') and call.get('type')=='mcpToolCall'
           and call.get('server')=='codex_app' and call.get('tool')=='read_thread']
    if (len(calls)!=1 or calls[0].get('status')!='completed' or calls[0].get('error')
            or calls[0].get('arguments',{}).get('threadId')!=sender['task_id']):
        raise w.WorkflowError('one actual successful original HQ read invocation required')
    original=proof['queued_source'];raw=w.safe_path(root,original['visible_reply']['path']).read_bytes()
    messages=[message for turn in source.get('turns',[]) if turn.get('id')==original['source_turn_id']
              and turn.get('status') in {'inProgress','completed'} and not turn.get('error')
              for message in turn.get('items',[]) if message.get('type')=='agentMessage'
              and (not original.get('source_message_id') or message.get('id')==original['source_message_id'])
              and message.get('text','').encode('utf-8')==raw]
    if (len(messages)!=1 or w.file_digest(root,original['visible_reply']['path'])!=original['visible_reply']
            or hashlib.sha256(raw).hexdigest()!=original['source_reply_sha256']):
        raise w.WorkflowError('HQ must actually read this one exact frozen conclusion, not a summary/ACK')
    return {**proof,'transport_binding':'actual_recipient_native_read','actual_recipient_read':pin,
            'native_notification_sent':False,'native_conclusion_received':True,
            'dependency_pins':[*proof['dependency_pins'],pin,observation['native_invocation'],observation['actual_read_result']]}


def selection_context(root,identity):
    from goal_delivery_runtime import enabled
    snapshot=w.read_json(w.snapshot_path(root,identity['task_id']))
    if enabled(root,snapshot):return _task(root,identity['task_id'])
    import result_coordination as rc
    rc._validate_queued(root,identity)
    source=w.scheduled_result_source(root,identity['task_id'],identity['sender_department'])
    queued=[row for row in w._result_handoff_rows(root,identity['task_id'])
            if row.get('event')=='notification_queued' and rc.exact_identity(row)==identity]
    if (not source or source.get('legacy_contract') or len(queued)!=1
            or queued[0].get('source_mode')!='scheduled_run'
            or queued[0].get('source_automation_id')!=source['automation_id']):
        raise w.WorkflowError('current complete goal or exact admitted daily result required')
    return {'task_id':identity['task_id'],'current_state':'evidence_received','scheduled_report_only':True,
            'goal_delivery':{'primary_owner':identity['sender_department'],
             'producer_departments':[identity['sender_department']],
             'responsible_assistant':daily_selected_assistant(root,identity,source['responsible_assistant']),
             'acceptance_capability':source['acceptance_capability']}}


def record_turn_completion(root, identity, native_pin):
    """Append the real end event without replacing the original ready statement."""
    from result_coordination import exact_identity
    identity=exact_identity(identity)
    rows=[r for r in w._result_handoff_rows(root,identity['task_id'])
          if r.get('event')=='notification_queued' and all(r.get(k)==v for k,v in identity.items())]
    if len(rows)!=1:raise w.WorkflowError('one original frozen ready result required')
    source=rows[0];page=native(root,native_pin)
    binding=w.department_registry(root)[identity['sender_department']]['chat_binding']
    if page.get('thread',{}).get('id')!=binding['task_id']:
        raise w.WorkflowError('original ready recipient identity differs')
    turns=[t for t in page.get('turns',[]) if t.get('id')==source['source_turn_id']]
    if len(turns)!=1 or turns[0].get('status')!='completed' or turns[0].get('error'):
        raise w.WorkflowError('actual original ready turn not successfully completed')
    declarations=[m for m in turns[0].get('items',[]) if m.get('id')==source.get('source_message_id')]
    if (source.get('result_source_phase')=='delivery_ready' and
            (len(declarations)!=1 or hashlib.sha256(declarations[0].get('text','').encode()).hexdigest()!=source['source_reply_sha256'])):
        raise w.WorkflowError('original frozen declaration changed before completion')
    with w.workflow_lock(root):
        events=w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS)
        duplicate=[r for r in events if r.get('details',{}).get('delivery_turn_completed',{}).get('identity')==identity]
        if duplicate:return {'result':'duplicate_ignored','source_turn_completed':True}
        snap=w.read_json(w.snapshot_path(root,identity['task_id']))
        proof={'identity':identity,'source_turn_id':source['source_turn_id'],'native':native_pin}
        state=snap.get('current_state') or ('evidence_received' if source.get('source_mode')=='scheduled_run' else None)
        if state is None:raise w.WorkflowError('original result state required for completion event')
        w.append_workflow_event(root,identity['task_id'],state,{'delivery_turn_completed':proof})
    return {'result':'recorded','source_turn_completed':True,'extra_acceptance_required':False}


def shared_capable(root,role,goal):
    item=w.department_registry(root).get(role,{})
    config=item.get('coordination_authority',{}).get('shared_review_methods')
    if not config:return False
    if role in goal.get('producer_departments',[]) or item.get('new_dispatch_enabled') is False:return False
    doc=pin_document(root,config)
    capability=goal.get('acceptance_capability')
    selected=doc.get('methods',{}).get(capability)
    if not selected or doc.get('production_permissions_inherited') is not False:return False
    if 'resources' in doc:
        names=item.get('approved_subskills',[]);paths=item.get('approved_subskill_paths',[])
        needed=doc.get('method_skill_requirements',{}).get(capability)
        if len(names)!=len(paths) or not needed:return False
        for name in needed:
            resource=doc.get('resources',{}).get(name,{})
            if name not in names or paths[names.index(name)]!=resource.get('path'):return False
            path=Path(resource.get('path',''))
            if not path.is_absolute() or path.name!='SKILL.md' or not path.is_file():return False
            raw=path.read_bytes()
            if len(raw)!=resource.get('size') or hashlib.sha256(raw).hexdigest()!=resource.get('sha256'):return False
    return (all(w.file_digest(root,p['path'])==p for p in selected)
            and item.get('coordination_authority',{}).get('routine_decisions') is True)


def frozen_dependency_available(root,task_id,department):
    """A verified full-batch handoff satisfies delivery, never acceptance."""
    import result_coordination as rc
    for row in reversed(w._result_handoff_rows(root,task_id)):
        if (row.get('sender_department')!=department or row.get('event')!='notification_queued'
                or row.get('batch_delivery_frozen') is not True):continue
        try:
            identity=rc.exact_identity(row)
            rc._validate_queued(root,identity)
            path=row.get('outbox_path') or row.get('outbox',{}).get('path','')
            if w.file_digest(root,path)['sha256']!=identity['result_sha256']:continue
            ready_source(root,row,row['source_thread_id'])
            return True
        except (w.WorkflowError,OSError,ValueError,KeyError,TypeError):continue
    return False


def selection_plan(root,identity,live_pin,available_self=None):
    import result_coordination as rc
    from technical_review_backup import review_capable
    identity=rc.exact_identity(identity);snap=selection_context(root,identity);goal=snap['goal_delivery']
    if snap.get('current_state') in w.TERMINAL_STATES:
        return {'state':'retain_completed_scope','selected':goal['responsible_assistant'],'requires_transfer':False}
    prior=[row for row in w._result_handoff_rows(root,identity['task_id']) if all(row.get(k)==v for k,v in identity.items())]
    if any(row.get('event') in {'controller_received','controller_decision'} for row in prior):
        return {'state':'retain_started_acceptance','selected':goal['responsible_assistant'],'requires_transfer':False}
    live=pin_document(root,live_pin);stamp=w._parse_observed_at(live.get('observed_at'))
    if stamp is None or not 0<=(dt.datetime.now(dt.timezone.utc)-stamp).total_seconds()<=300:
        raise w.WorkflowError('fresh actual native assistant observation required')
    observed=native(root,live['actual_native_observation'])
    threads=[*observed.get('threads',[]),*observed.get('pinnedThreads',[])]
    path=w.safe_path(root,str(rc.DATABASE));claims=[]
    if path.exists():
        conn=sqlite3.connect('file:'+str(path)+'?mode=ro',uri=True)
        try:claims=conn.execute('SELECT identity_json,role,owner,expires FROM claims').fetchall()
        finally:conn.close()
    # Historical claims stay as evidence, but only a live lease reserves a
    # reviewer. Match CoordinationStore's lease validity; never delete a claim
    # just to make a busy reviewer appear free.
    now=time.time()
    held=[row for row in claims if row[2] and row[3]>now]
    same=[row for row in held if json.loads(row[0])==identity]
    if same:return {'state':'already_owned','selected':same[0][1],'requires_transfer':False}
    receipts,bad=w._validate_receipt_chain(root,identity['task_id'])
    if bad:raise w.WorkflowError('intact original selection receipt chain required')
    if any(r.get('receipt_type')=='qa_verdict' for r in receipts):
        return {'state':'retain_started_acceptance','selected':goal['responsible_assistant'],'requires_transfer':False}
    candidates=[]
    for index,(role,item) in enumerate(w.department_registry(root).items()):
        binding=item.get('chat_binding',{});rows=[t for t in threads if t.get('id')==binding.get('task_id')]
        if (role==identity['sender_department'] or role in goal['producer_departments']
                or not review_capable(root,role,goal,task_id=identity['task_id'],transfer_from=goal['responsible_assistant'])
                or not w._chat_binding_healthy(binding,verification_ttl_hours=26)
                or len(rows)!=1 or any(rows[0].get(k)!=binding.get(v) for k,v in
                   {'projectId':'project_id','title':'title','cwd':'cwd'}.items())):continue
        active_claims=sum(1 for row in held if row[1]==role)
        queued=0
        for task_path in (Path(root)/w.WORKFLOW_DIR).glob('*.json'):
            try:
                task_row=w.read_json(task_path)
                queued+=int(task_row.get('goal_delivery',{}).get('responsible_assistant')==role
                            and task_row.get('current_state') not in w.TERMINAL_STATES)
            except (w.WorkflowError,ValueError,OSError,TypeError,AttributeError):continue
        status=rows[0].get('status');status=status.get('type') if isinstance(status,dict) else status
        candidates.append({'role':role,'available':(status=='idle' or role==available_self and status=='active') and active_claims==0,
                           'score':(0 if role==goal['responsible_assistant'] else 1,queued,index)})
    available=[r for r in candidates if r['available']]
    return {'state':'ready' if available else 'shared_waiting','selected':min(available,key=lambda r:r['score'])['role'] if available else None,
            'eligible':candidates,'requires_transfer':bool(available and min(available,key=lambda r:r['score'])['role']!=goal['responsible_assistant']),
            'native_messages_sent':0}


def select_result(root,request):
    """Before acceptance starts, commit one resource assignment, never a verdict."""
    import result_coordination as rc
    identity=rc.exact_identity(request);rc._validate_queued(root,identity)
    if not isinstance(request.get('request_id'),str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,199}',request['request_id']):
        raise w.WorkflowError('nonempty resource selection idempotency identity required')
    store=rc.CoordinationStore(root)
    try:
        with rc.coordination_lock(root),w.workflow_lock(root):
            snap=selection_context(root,identity);goal=snap['goal_delivery']
            actor=request['actor']
            actor_authority=w.department_registry(root).get(actor,{}).get('coordination_authority',{})
            capable_dispatcher=(actor_authority.get('routine_decisions') is True and
                                actor_authority.get('dispatch_approved_next') is True and shared_capable(root,actor,goal))
            if actor not in {'operations',goal['primary_owner'],goal['responsible_assistant']} and not capable_dispatcher:
                raise w.WorkflowError('authorized original resource dispatcher required')
            available_self=actor if request.get('at_work_boundary') is True and actor_authority.get('routine_decisions') is True else None
            plan=selection_plan(root,identity,request['live_identity'],available_self=available_self)
            if plan['state']!='ready' or plan['selected']==goal['responsible_assistant']:return plan
            current=w.read_json(rc._notification_path(root,identity))
            if current.get('state') not in {'queued','deferred','unknown_target'} or current.get('attempts') or current.get('delivered'):
                raise w.WorkflowError('started delivery cannot silently change accepting assistant')
            review_transfer=None
            if snap.get('qa_review_plan'):
                from qa_review_plan import load_plan, transfer_plan
                old_plan=load_plan(root,snap);new_plan=dict(old_plan)
                target=plan['selected'];tb=w.department_registry(root)[target]['chat_binding']
                new_plan.update(reviewer_department=target,reviewer_thread_id=tb['task_id'])
                if old_plan.get('controller_department')==goal['responsible_assistant']:
                    new_plan.update(controller_department=target,controller_thread_id=tb['task_id'])
                review_path='logs/assistant-selections/'+rc._key(identity)+'-'+target+'-plan.json'
                existing=w.read_json(Path(root)/review_path)
                if existing and existing!=new_plan:raise w.WorkflowError('preserve changed reviewer plan')
                w.atomic_write_json(Path(root)/review_path,new_plan)
                review_transfer=transfer_plan(root,task_id=identity['task_id'],plan_path=review_path,target_role=target,prepare_only=True)
            original_notice_path=rc._notification_path(root,identity)
            archived='logs/assistant-selections/'+rc._key(identity)+'-'+request['request_id']+'-notice-before.json'
            if w.read_json(Path(root)/archived) and w.read_json(Path(root)/archived)!=current:
                raise w.WorkflowError('preserve original notification resource source')
            w.atomic_write_json(Path(root)/archived,current)
            notice_source=w.file_digest(root,archived)
            store._begin()
            try:
                row=store._row(identity)
                if row and row['owner'] and row['expires']>time.time():
                    raise w.WorkflowError('started acceptance requires existing explicit transfer')
                event={'identity':identity,'actor':actor,'previous_assistant':goal['responsible_assistant'],
                       'target_assistant':plan['selected'],'request_id':request['request_id'],
                       'live_identity':request['live_identity'],'acceptance_created':False,
                       'review_plan_transfer':review_transfer,
                       'notification_source':notice_source,
                       'notification_original_path':w.rel_path(root,original_notice_path)}
                if snap.get('scheduled_report_only'):event['scheduled_report_only']=True
                store._audit(identity,'initial_assistant_selection',event)
                store.conn.commit()
            except BaseException:store.conn.rollback();raise
            _apply_selection(root,event)
            return {**plan,'assignment_committed':True,'accepted':False}
    finally:store.close()


def _apply_selection(root,event):
    """Recover SQL-committed selection without creating another acceptance."""
    import result_coordination as rc
    identity=event['identity'];snap=selection_context(root,identity);goal=snap['goal_delivery']
    if goal['responsible_assistant'] not in {event['previous_assistant'],event['target_assistant']}:
        raise w.WorkflowError('a newer responsibility change must be preserved')
    target=event['target_assistant'];binding=w.department_registry(root)[target]['chat_binding']
    history=goal.setdefault('assignment_history',[]);already=event in history
    goal['responsible_assistant']=target
    if not already:history.append(event)
    snap['goal_delivery']=goal
    transfer=event.get('review_plan_transfer')
    if transfer:snap['qa_review_plan']=transfer['new_binding']
    rows=snap.setdefault('departments',[])
    for row in rows:
        if row.get('department')==event['previous_assistant']:
            row.update(department=target,chat_task_id=binding['task_id'])
    if not any(row.get('department')==target for row in rows):
        rows.append({'department':target,'chat_task_id':binding['task_id'],'execution_wave':2,'depends_on':goal['producer_departments']})
    if not already and not event.get('scheduled_report_only'):
        w.append_workflow_event(root,identity['task_id'],snap['current_state'],{
            'goal_delivery':goal,'assignment_departments':rows,'resource_selection':event,
            **({'qa_review_plan_bound':transfer['new_binding']} if transfer else {})})
    if not event.get('scheduled_report_only'):
        w.atomic_write_json(w.snapshot_path(root,identity['task_id']),snap)
    path=rc._notification_path(root,identity)
    old_path=w.safe_path(root,event['notification_original_path'])
    current=w.read_json(old_path if old_path.exists() else path)
    original=pin_document(root,event['notification_source'])
    if current.get('identity')!=identity:
        raise w.WorkflowError('recover only the exact existing notification source')
    if old_path.exists() and current!=original:
        raise w.WorkflowError('preserve changed original notification before selection recovery')
    if current.get('delivered') or current.get('attempts'):
        if current.get('target_thread_id')!=binding['task_id']:
            raise w.WorkflowError('started notification must retain its actual recipient')
        return
    route=rc.result_lane(root,identity);exact=rc.delivery_identity(root,identity,route=route)
    current.update(route=route,delivery_identity=exact,target_thread_id=binding['task_id'],
                   dedupe_key=rc._delivery_key(exact),state='queued')
    if event not in current.setdefault('assignment_history',[]):current['assignment_history'].append(event)
    if old_path!=path and old_path.exists():
        if path.exists():raise w.WorkflowError('preserve an existing new recipient notification')
        os.replace(old_path,path)
    w.atomic_write_json(path,current)


def recover_selection(root,request):
    import result_coordination as rc
    identity=rc.exact_identity(request);store=rc.CoordinationStore(root)
    try:
        with rc.coordination_lock(root),w.workflow_lock(root):
            audits=[json.loads(row[0]) for row in store.conn.execute('SELECT payload_json FROM coordination_audit ORDER BY seq')]
            selected=[row['details'] for row in audits if row.get('event')=='initial_assistant_selection'
                      and row.get('identity')==identity and row.get('details',{}).get('request_id')==request.get('request_id')]
            if len(selected)!=1:raise w.WorkflowError('one actual committed original selection required')
            event=selected[0];goal=selection_context(root,identity)['goal_delivery']
            if request.get('actor') not in {'operations',goal['primary_owner'],goal['responsible_assistant']}:
                raise w.WorkflowError('original authorized selection recovery actor required')
            row=store._row(identity)
            if row and row['owner'] and row['role']!=event['target_assistant']:
                raise w.WorkflowError('started other acceptance requires explicit transfer')
            _apply_selection(root,event)
            return {'result':'recovered_exact_selection','selected':event['target_assistant'],
                    'accepted':False,'native_messages_sent':0}
    finally:store.close()


def shared_pending(root,role):
    """Cheap candidate inventory; claim/select still validate every exact source."""
    import result_coordination as rc
    from technical_review_backup import review_capable
    result=[];errors=[]
    registry=w.department_registry(root)
    if registry.get(role,{}).get('coordination_authority',{}).get('routine_decisions') is not True:
        return {'results':[],'errors':[],'inventory_is_permission':False}
    for path in sorted((Path(root)/w.WORKFLOW_DIR).glob('*.json')):
        try:
            snap=w.read_json(path);goal=snap.get('goal_delivery',{})
            if (not goal or snap.get('current_state') in w.TERMINAL_STATES
                    or goal.get('responsible_assistant')==role or role in goal.get('producer_departments',[])
                    or not review_capable(root,role,goal,task_id=path.stem,transfer_from=goal.get('responsible_assistant'))):continue
            rows=w.read_jsonl(w.result_handoff_path(root,path.stem));groups={}
            for row in rows:
                identity=rc.exact_identity(row)
                if identity['sender_department'] not in goal['producer_departments']:continue
                groups.setdefault(rc._key(identity),{'identity':identity,'events':[]})['events'].append(row.get('event'))
            for item in groups.values():
                if 'notification_queued' in item['events'] and 'controller_decision' not in item['events']:
                    result.append({**item['identity'],'current_assistant':goal['responsible_assistant'],
                                   'next_action':'select_exact_result_at_work_boundary_then_claim','inventory_is_permission':False})
        except (w.WorkflowError,ValueError,OSError,KeyError,TypeError,AttributeError) as exc:
            errors.append({'task_id':path.stem,'reason':str(exc),'blocks_other_tasks':False})
    # Daily batches may legitimately have no headquarters dispatch snapshot.
    # Include their existing exact queues without manufacturing one.
    for path in sorted((Path(root)/w.RESULT_HANDOFF_DIR).glob('*.jsonl')):
        try:
            groups={}
            for row in w.read_jsonl(path):
                if row.get('source_mode')!='scheduled_run':continue
                identity=rc.exact_identity(row)
                groups.setdefault(rc._key(identity),{'identity':identity,'source':row})
            for item in groups.values():
                identity=item['identity']
                if any(row.get('event') in {'controller_received','controller_decision'} and rc.exact_identity(row)==identity
                       for row in w.read_jsonl(path)):continue
                context=selection_context(root,identity);goal=context['goal_delivery']
                if (not context.get('scheduled_report_only') or goal['responsible_assistant']==role
                        or role in goal['producer_departments'] or not review_capable(root,role,goal,
                            task_id=identity['task_id'],transfer_from=goal['responsible_assistant'])):continue
                result.append({**identity,'current_assistant':goal['responsible_assistant'],
                    'next_action':'select_exact_result_at_work_boundary_then_claim','inventory_is_permission':False})
        except (w.WorkflowError,ValueError,OSError,KeyError,TypeError,AttributeError) as exc:
            errors.append({'task_id':path.stem,'reason':str(exc),'blocks_other_tasks':False})
    return {'results':result,'errors':errors,'inventory_is_permission':False,'messages_sent':0}


def pending_intake(root, task_ids=None):
    """Compatibility inventory: received HQ knowledge is not a second review."""
    import result_coordination as rc
    queue=w.result_handoff_pending(root,task_ids)
    remaining=[];resolved=[];errors=[]
    registry=w.department_registry(root)
    for item in queue['results']:
        if item.get('received') and registry.get(item.get('sender_department'),{}).get('coordination_authority',{}).get('routine_decisions') is True:
            try:
                route=rc.result_lane(root,item)
                if route['lane']=='HQ_knowledge':
                    rc.hq_knowledge_source(root,item,require_transport=True)
                    intake=rc._received_delivery(root,rc.exact_identity(item),route)
                    if intake:
                        resolved.append({**item,'knowledge_received_record_id':intake['record_id'],
                            'HQ_second_review_required':False,'formal_decision_fabricated':False})
                        continue
            except (w.WorkflowError,OSError,ValueError,KeyError,TypeError) as exc:
                errors.append({'task_id':item['task_id'],'reason':str(exc),'blocks_other_tasks':False})
        remaining.append(item)
    return {**queue,'results':remaining,'pending_count':len(remaining),
            'queued_pending_count':sum(bool(row.get('queued')) for row in remaining),
            'total_actionable_count':len(remaining)+len(queue.get('followthrough_results',[])),
            'received_HQ_knowledge_without_second_review':resolved,'knowledge_source_errors':errors}


def work_boundary(root, role, *, assignment=None, read_assignment=True):
    """Read current work before maintenance/NO_CHANGE; never send or grant rights.

    Inventory uses authenticated ledger bytes, not a full historical re-review.
    Each action still uses the existing exact claim/source/policy consumers.
    """
    import result_coordination as rc
    registry=w.department_registry(root)
    if role not in registry:raise w.WorkflowError('registered work-boundary role required')
    ready=[];waiting=[];errors=[];groups={}
    if read_assignment:
        try:assignment=rc.current_assignment_for_role(root,role)
        except (w.WorkflowError,OSError,ValueError,KeyError,TypeError) as exc:
            errors.append({'owner':role,'stage':'current_assignment_recovery','reason':str(exc)})
    for path in sorted((Path(root)/w.RESULT_HANDOFF_DIR).glob('*.jsonl')):
        try:
            snap=w.read_json(w.snapshot_path(root,path.stem));goal=snap.get('goal_delivery',{})
            sources=w.read_json(Path(root)/'data/task-contract.json').get('result_handoff_contract',{}).get('scheduled_daily_sources',[])
            scheduled=[s for s in sources if isinstance(s,dict) and re.fullmatch(s.get('task_id_pattern','(?!)'),path.stem)]
            relevant=(goal and (role in goal.get('producer_departments',[]) or role==goal.get('responsible_assistant')
                               or role=='operations')) or any(role in {s.get('department'),s.get('responsible_assistant')} for s in scheduled)
            if not relevant:continue
            rows=w._result_handoff_rows(root,path.stem)
            for row in rows:
                identity=rc.exact_identity(row);sender=identity['sender_department']
                target=goal.get('responsible_assistant') if sender in goal.get('producer_departments',[]) else None
                owner_returns=w.read_json(Path(root)/'data/task-contract.json').get('result_handoff_contract',{}).get('owner_direct_return_sources',[])
                exact_returns=[s for s in owner_returns if s.get('identity')==identity]
                if len(exact_returns)==1:target=exact_returns[0]['responsible_assistant']
                knowledge=bool(goal and sender==goal.get('responsible_assistant'))
                if knowledge:target='operations'
                if not goal and row.get('source_mode')=='scheduled_run':
                    source=w.scheduled_result_source(root,path.stem,sender)
                    if source and row.get('source_automation_id')==source['automation_id']:
                        target=daily_selected_assistant(root,identity,source['responsible_assistant'])
                if target!=role and sender!=role:continue
                key=rc._key(identity)
                item=groups.setdefault(key,{**identity,'target_department':target,
                    'knowledge_only':knowledge,'events':[], 'controller_followthrough':'pending'})
                item['events'].append(row['event'])
                if row['event']=='controller_decision':item['controller_decision']=row.get('decision')
                elif row['event']=='controller_followthrough':
                    item.update(controller_followthrough=row.get('followthrough_status'),next_check_at=row.get('next_check_at'))
            # A historical task is isolated; it cannot hide other valid work.
        except (w.WorkflowError,OSError,ValueError,KeyError,TypeError,AttributeError) as exc:
            errors.append({'task_id':path.stem,'reason':str(exc),'blocks_other_tasks':False})
    for item in groups.values():
        if item['target_department']!=role:continue
        events=item['events']
        if 'notification_queued' not in events and 'controller_received' not in events:continue
        if item['knowledge_only']:
            if 'controller_received' not in events:
                ready.append({**item,'next_action':'receive_exact_HQ_knowledge_without_second_review'})
            continue
        if 'controller_decision' not in events:
            ready.append({**item,'next_action':'claim_and_receive_original_frozen_result'})
        elif w._followthrough_due(item):
            ready.append({**item,'next_action':'execute_original_decision_followthrough'})
        elif w._followthrough_waiting(item):waiting.append({**item,'next_action':'wait_named_dependency'})
    deliveries=rc.notification_plan(root,role)
    for notice in deliveries['notifications']:
        # Only the sender owns delivery. Receiving assistants can intake the
        # original frozen result independently instead of impersonating sender.
        if notice.get('delivery_owner')!=role:continue
        (ready if notice.get('actionable') else waiting).append({
            **notice.get('identity',{}),'next_action':notice['next_action'],
            'kind':'actual_notification_delivery','queue_is_delivery':False})
    errors.extend(deliveries.get('errors',[]))
    if assignment and assignment.get('resume_required'):
        task=assignment['task_id']
        own=[item for item in groups.values() if item['task_id']==task and item['sender_department']==role]
        delivered_batch=any('notification_queued' in item['events'] for item in own)
        dependency_wait=any(item['task_id']==task for item in waiting)
        if not any(item['task_id']==task for item in ready):
            item={'task_id':task,'owner':role,'kind':'original_current_assignment',
                  'parent_goal_closed':False,'next_action':'reconcile_original_unfinished_scope'}
            if delivered_batch or dependency_wait:
                waiting.append({**item,'next_action':'retain_original_goal_until_exact_intake_or_dependency_event'})
            else:ready.insert(0,item)
    return {'schema':'goal-work-boundary/v1','department':role,
            'actual_current_assignment':assignment,'ready_actions':ready,'waiting_actions':waiting,
            'source_errors':errors,'actionable_count':len(ready),
            'can_report_no_change':not ready and not errors,
            'resume_before_maintenance':bool(ready),'inventory_is_permission':False,
            'native_wakeup_guaranteed':False,'messages_sent':0,'writes_performed':False,
            'HQ_continuous_watch_required':False}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['assignment-record','result-select','selection-recover','turn-completed','shared-pending','work-boundary'])
    parser.add_argument('--root',default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument('--input')
    parser.add_argument('--role')
    args=parser.parse_args();root=Path(args.root).resolve()
    if args.command=='work-boundary':
        result=work_boundary(root,args.role)
        print(json.dumps(result,ensure_ascii=False,indent=2));return 0
    if args.command=='shared-pending':
        print(json.dumps(shared_pending(root,args.role),ensure_ascii=False,indent=2));return 0
    if not args.input:parser.error('--input required')
    item=w.read_json(w.safe_path(root,args.input))
    if args.command=='assignment-record':result=record_assignment(root,item,w.file_digest(root,args.input))
    elif args.command=='result-select':result=select_result(root,item)
    elif args.command=='selection-recover':result=recover_selection(root,item)
    else:result=record_turn_completion(root,item,item['actual_native_completion'])
    print(json.dumps(result,ensure_ascii=False,indent=2));return 0


if __name__=='__main__':raise SystemExit(main())
