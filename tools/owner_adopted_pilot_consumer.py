"""Read the real adopted-parent pilot lineage; never create reviewer or notice facts."""
from __future__ import annotations
import datetime as dt
import json
from pathlib import Path
import re
import workflow_control as w

TASK = 'fc-20261021-owner-delegated-nonpayment-runtime-pilot-v1'
PARENT = 'fc-20261021-owner-delegated-nonpayment-decisions-repair-v1'
SCOPE = 'project:flashcast:owner-delegated-nonpayment-decisions:20261021:v1'
PRODUCER, ROLE = 'system-development', 'operations-assistant-2'
INITIAL = 'A2-owner-adopted-runtime-real-SYS-pilot-20261021-v1'
REWORK = 'A2-owner-real-pilot-exact-review-consumer-rework-20261021-v1'
FAILURE = '非法越级：outbox_received 之前必须有同部门非空 chat_ack'


def _fail(message):
    raise w.WorkflowError('adopted parent pilot: ' + message)


def _pin(root, pin):
    from goal_continuity import pin_document
    return pin_document(root, pin)


def _rows(root, task, supplied=None):
    # A source reader must not recurse through the very QA verdict consuming
    # it. Validate every raw byte/hash/evidence in the complete child chain;
    # the ordinary outer receipt consumer still validates actual QA semantics.
    if task == TASK:
        from goal_source_recovery import _queue_unique_fields
        try:
            rows = [json.loads(line,object_pairs_hook=_queue_unique_fields)
                    for line in w.receipts_path(root,task).read_text(encoding='utf-8').splitlines() if line.strip()]
        except (OSError,ValueError,UnicodeError) as error:
            _fail('strict original receipt JSON required: '+str(error))
        previous,seen = '',set()
        for row in rows:
            if (not isinstance(row,dict) or row.get('task_id') != task or not row.get('receipt_id')
                    or row['receipt_id'] in seen or row.get('previous_hash','') != previous
                    or row.get('receipt_hash') != w.sha256_value(w._receipt_payload_for_hash(row))):
                _fail('intact complete original receipt byte/hash chain required')
            for evidence in row.get('evidence',[]):
                if w.file_digest(root,evidence.get('path','')) != evidence:
                    _fail('unchanged original receipt evidence required')
            previous=row['receipt_hash'];seen.add(row['receipt_id'])
    else:
        rows,invalid = w._validate_receipt_chain(root, task)
        if invalid:_fail('intact actual parent receipt chain required')
    if supplied is not None and rows[:len(supplied)] != supplied:
        _fail('intact actual receipt prefix required')
    return rows if supplied is None else supplied


def _handoffs(root, task):
    rows = w._result_handoff_rows(root, task)
    previous, seen = '', set()
    for row in rows:
        if (row.get('task_id') != task or not row.get('record_id') or row['record_id'] in seen
                or row.get('previous_hash', '') != previous
                or row.get('record_hash') != w.sha256_value({k:v for k,v in row.items() if k != 'record_hash'})):
            _fail('intact complete original handoff hash chain required')
        previous = row['record_hash']; seen.add(row['record_id'])
    return rows


def _one(rows, predicate, label):
    found = [x for x in rows if predicate(x)]
    if len(found) != 1:
        _fail('one actual ' + label + ' required')
    return found[0]


def _binding(root, role, page=None):
    binding = w.department_registry(root)[role]['chat_binding']
    if (binding.get('cwd') != str(Path(root).resolve()) or not binding.get('project_id')
            or binding['project_id'] != w.department_registry(root)['operations']['chat_binding'].get('project_id')):
        _fail('same original project/cwd required')
    if page is not None and any(page.get('thread', {}).get(k) != binding.get(v) for k,v in
            {'id':'task_id', 'title':'title', 'cwd':'cwd'}.items()):
        _fail('actual fixed native participant identity differs')
    return binding


def _core(root, snapshot):
    if snapshot.get('task_id') != TASK:
        return None
    from parent_initial_child_review import _snapshot
    import goal_delivery_runtime as g
    import qa_review_plan as q
    def original(value):
        frozen = g.validate_goal(root,_pin(root,value.get('goal_contract')))
        for key in (*g.REQUIRED,'parent_task_id','source_mode','human_authorization','authorization_pin',
                    'required_execution_actions','production_write_allowed','external_permission_issued'):
            if value.get('goal_delivery',{}).get(key) != frozen.get(key):
                _fail('supplied original role/parent/scope/authority must match frozen contract')
        return _snapshot(root,value)
    child = original(snapshot)
    parent = original(w.read_json(w.snapshot_path(root, PARENT)))
    goal, original = child['goal_delivery'], parent['goal_delivery']
    for value in (goal, original):
        if (value.get('primary_owner') != PRODUCER or value.get('producer_departments') != [PRODUCER]
                or value.get('responsible_assistant') != ROLE or value.get('authorized_scope') != [SCOPE]
                or value.get('required_execution_actions') or value.get('source_mode') != 'approved_dispatch'
                or any(value.get(k) is not None and value.get(k) is not False
                       for k in ('production_write_allowed','external_permission_issued'))):
            _fail('original no-external-write producer/reviewer/scope required')
    if (any(goal.get(k) is not False for k in ('production_write_allowed','external_permission_issued'))
            or goal.get('parent_task_id') != PARENT or goal['authorization_pin'] != original['authorization_pin']
            or goal.get('human_authorization') != original.get('human_authorization')):
        _fail('actual original same-parent/human authority required')
    for role in (ROLE, PRODUCER):
        _binding(root, role)
    parent_rows = _rows(root, PARENT)
    requirement = _one(original['completion_requirements'], lambda x:x.get('requirement_id') == 'autonomy-3'
        and x.get('requirement_type') == 'source_adoption', 'parent adoption criterion')
    registrations = [x['details']['completion_evidence'] for x in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS)
        if x.get('task_id') == PARENT and x.get('details', {}).get('completion_evidence', {}).get('requirement_id') == 'autonomy-3']
    registration = _one(registrations, lambda x:True, 'formally registered adoption')
    accepted = w.goal_completion_subject(root, parent, parent_rows, {**requirement['subject'], 'scope':SCOPE})
    adoption = w.goal_typed_completion_proof(root, parent, parent_rows, requirement, accepted,
                                           proof_pin=registration['proof_pin'])
    if accepted.get('state') != 'PROVEN' or adoption.get('state') != 'PROVEN':
        _fail('real current independently accepted/adopted parent source required')
    parent_plan = q.load_plan(root, parent)
    parent_round = q._assigned_review_round(root, parent, parent_rows, parent_plan)
    if not parent_round or not parent_round.get('dispatch') or not parent_round.get('ack'):
        _fail('actual original parent reviewer dispatch/ACK required')
    rows = _rows(root, TASK)
    index = w.read_json(Path(root)/'data/department-current-assignment.json')
    pins = list(index.get('suspended_assignments', {}).get(PRODUCER, []))
    if index.get('assignments', {}).get(PRODUCER):
        pins.append(index['assignments'][PRODUCER])
    originals = {}
    for pin in pins:
        item = _pin(root, pin)
        if (item.get('task_id') == TASK and item.get('department') == PRODUCER
                and item.get('sender_department') == ROLE and item.get('action_id') == INITIAL):
            originals[pin['path']] = (pin,item)
    source_pin, source = _one(list(originals.values()), lambda x:True, 'existing original SYS assignment')
    from goal_continuity import _dispatch_source
    _, dispatch = _dispatch_source(root, source)
    ack = _one(rows, lambda x:x.get('receipt_type') == 'chat_ack' and x.get('department') == PRODUCER
        and x.get('action_id') == INITIAL and x.get('ack_nonempty') is True, 'original SYS nonempty ACK')
    if (dispatch.get('action_id') != INITIAL or dispatch.get('department') != PRODUCER
            or ack.get('chat_task_id') != dispatch.get('chat_task_id')
            or ack.get('policy_decision_id') != dispatch.get('policy_decision_id')
            or rows.index(dispatch) >= rows.index(ack)):
        _fail('original SYS assignment/dispatch/ACK identity and order differ')
    from goal_delivery_runtime import _collaboration_native
    actual_acks = []
    for pin in ack.get('evidence', []):
        if not pin.get('path', '').endswith('.json'):
            continue
        doc = _pin(root, pin)
        if doc.get('thread', {}).get('id') != dispatch['chat_task_id']:
            continue
        page = _collaboration_native(root, pin); _binding(root, PRODUCER, page)
        if any(t.get('status') in {'inProgress','completed'} and not t.get('error')
               and any(m.get('type') == 'agentMessage' and m.get('id') and str(m.get('text', '')).strip()
                       for m in t.get('items', [])) for t in page.get('turns', [])):
            actual_acks.append(pin)
    if len(actual_acks) != 1:
        _fail('one real original SYS native nonempty ACK required')
    return {'child':child, 'parent':parent, 'parent_adoption':registration['proof_pin'],
            'parent_dispatch':parent_round['dispatch'], 'parent_ack':parent_round['ack'],
            'producer_assignment':source_pin, 'producer_dispatch':dispatch, 'producer_ack':ack}


def _received(root, rows, box_pin):
    from scoped_candidate_adoption import _committed
    received = _one(rows, lambda x:x.get('event') == 'controller_received' and x.get('outbox') == box_pin
        and x.get('sender_department') == PRODUCER and x.get('coordinator_role') == ROLE
        and x.get('responsible_assistant') == ROLE, 'unique exact original A2 intake')
    _committed(root, received)
    return received


def review_context(root, snapshot, receipts=None, plan=None):
    if snapshot.get('task_id') != TASK:
        return None
    import qa_review_plan as q
    core = _core(root, snapshot)
    if plan is None:
        binding = q._binding(root, snapshot)
        if not binding:
            _fail('original frozen normal review plan required')
        plan = _pin(root, binding['pin'])
    if (plan.get('task_id') != TASK or plan.get('reviewer_department') != ROLE
            or plan.get('producer_department') != PRODUCER or plan.get('scope') != SCOPE
            or plan.get('reviewer_thread_id') != _binding(root, ROLE)['task_id']
            or any(plan.get(k) is not False for k in ('production_write_allowed','external_permission_issued'))):
        _fail('original independent normal plan identity required')
    rows = _rows(root, TASK, receipts)
    if any(x.get('department') in {ROLE,'qa','qa-technical'} and x.get('receipt_type') in
           {'dispatch_sent','dispatch_failed','chat_ack'} for x in rows):
        _fail('inherited source cannot replace another reviewer window')
    producer = [x for x in rows if x.get('department') == PRODUCER and x.get('receipt_type') == 'outbox_received']
    if not producer:
        _fail('actual SYS complete delivery required')
    pin = next((p for p in producer[-1].get('evidence', []) if p.get('path','').endswith('.json')), None)
    box = _pin(root, pin)
    if not q._producer_candidate_bound(root, plan, pin, box):
        _fail('current exact delivered candidate/version required')
    intake = _received(root, _handoffs(root, TASK), pin)
    return {'source_kind':'adopted_parent_pilot_review', 'reviewer_source_created_at':intake['created_at'],
            'parent_adoption':core['parent_adoption'], 'parent_dispatch':core['parent_dispatch'],
            'parent_ack':core['parent_ack'], 'producer_dispatch':core['producer_dispatch'],
            'producer_ack':core['producer_ack'], 'controller_received_record_id':intake['record_id'],
            'reviewer_dispatch_fabricated':False, 'parent_goal_completed':False}


def admission_rework(root, snapshot, receipts, old_binding, plan):
    if snapshot.get('task_id') != TASK:
        _fail('this unverdicted pilot only; no PASS reopen')
    import qa_review_plan as q
    proof = plan.get('pre_admission_rework')
    if (not isinstance(proof, dict) or set(proof) != {'mode','previous_plan','diagnosis','decision_record_id'}
            or proof['mode'] != 'same_original_adopted_pilot_admission_repair'):
        _fail('exact real pre-admission failure source required')
    old = _pin(root, proof['previous_plan']); diagnosis = _pin(root, proof['diagnosis'])
    if (diagnosis.get('task_id') != TASK or diagnosis.get('formal_QA_PASS_written') is not False
            or diagnosis.get('normal_bound_plan') != proof['previous_plan']):
        _fail('real original unverdicted normal admission diagnosis required')
    failure = _pin(root, diagnosis.get('actual_normal_entry_failure'))
    if failure != {'exit_code':2,'stdout':'','stderr':'ERROR: '+FAILURE+'\n'}:
        _fail('exact actual normal reviewer admission refusal required')
    identity = ('task_id','action_id','action_class','scope','producer_department','reviewer_department',
                'reviewer_thread_id','controller_department','controller_thread_id','risk_level',
                'single_final_reviewer','production_write_allowed','external_permission_issued')
    if (any(old.get(k) != plan.get(k) for k in identity)
            or plan.get('rework_of') or any(k in plan for k in ('post_pass_remaining_stage','adopted_source_continuation'))
            or any(plan.get(k) == old.get(k) for k in ('candidate_version','candidate_sha256'))
            or plan['candidate'].get('path') == old['candidate'].get('path')):
        _fail('immutable new candidate with original identity required')
    changed, diff, methods = plan.get('changed_scope'), plan.get('evidence_diff'), plan.get('revalidation_methods')
    if (changed != [SCOPE] or not isinstance(diff, dict) or diff.get('previous_candidate') != old['candidate']
            or diff.get('candidate') != plan['candidate'] or not str(diff.get('summary','')).strip()
            or not isinstance(methods, dict) or set(methods) != {SCOPE} or not str(methods[SCOPE]).strip()):
        _fail('accurate bounded delta and revalidation method required')
    events = [x for x in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS) if x.get('task_id') == TASK]
    original = [i for i,x in enumerate(events) if x.get('details',{}).get('qa_review_plan_bound',{}).get('pin') == proof['previous_plan']]
    if len(original) != 1:
        _fail('one actually bound original plan required')
    bound = [(i,x) for i,x in enumerate(events) if x.get('details',{}).get('qa_review_plan_bound',{}).get('pin') != proof['previous_plan']
        and x.get('details',{}).get('qa_review_plan_bound',{}).get('pre_admission_rework') == proof]
    if len(bound) > 1:
        _fail('one immutable actual pre-admission transition required')
    prefix = receipts
    if bound:
        metadata = bound[0][1].get('details',{}).get('pre_admission_rework',{})
        count = metadata.get('receipt_prefix_length')
        if type(count) is not int or not 0 < count <= len(receipts):
            _fail('actual before-binding receipt boundary required')
        prefix = receipts[:count]
        if prefix[-1].get('receipt_hash') != metadata.get('receipt_tail_hash'):
            _fail('unchanged actual before-binding source prefix required')
    if any(x.get('department') == ROLE and x.get('receipt_type') in {'qa_verdict','outbox_received'} for x in prefix):
        _fail('real pre-verdict admission failure required; no PASS reopen')
    if not bound and old_binding.get('pin') != proof['previous_plan']:
        _fail('exact current predecessor plan required')
    handoffs = _handoffs(root,TASK)
    decision = _one(handoffs, lambda x:x.get('record_id') == proof['decision_record_id'] and x.get('event') == 'controller_decision'
        and x.get('coordinator_role') == ROLE and x.get('decision') == 'rework', 'original actual rework decision')
    from scoped_candidate_adoption import _committed
    _committed(root, decision)
    if proof['diagnosis'] not in decision.get('evidence', []):
        _fail('actual rework must pin the exact admission diagnosis')
    source = review_context(root,snapshot,prefix,plan)
    return {'source':source, 'pre_admission_rework':proof, 'old_verdict_migrated':False,
            'receipt_prefix_length':len(prefix),'receipt_tail_hash':prefix[-1]['receipt_hash']}


def _queue_effect(root, payload, policy_id, intent, result, target, message_id):
    shared = {'thread_id':target['task_id'], 'payload_sha256':payload['sha256'],
              'policy_decision_id':policy_id,'transport':'official_codex_queue','intake_claimed':False}
    match = re.fullmatch(r'Queued message ([0-9a-f-]{36}) for thread ([0-9a-f-]{36})\.\s*', result.get('stdout',''))
    if (any(intent.get(k) != v or result.get(k) != v for k,v in shared.items())
            or intent.get('started_at') != result.get('started_at') or type(result.get('exit_code')) is not int
            or result['exit_code'] != 0 or result.get('stderr') != '' or not match
            or match[1] != message_id or match[2] != target['task_id']):
        _fail('actual successful exact official queue effect required')
    start, finish = (w._parse_observed_at(result.get(k)) for k in ('started_at','finished_at'))
    if not start or not finish or not start <= finish <= dt.datetime.now(dt.timezone.utc):
        _fail('actual original queue effect chronology required')
    return start,finish


def queued_rework_source(root, item, *, require_dispatch=True):
    if item.get('task_id') != TASK:
        return None
    from goal_source_recovery import _strict_queue_document
    snapshot = w.read_json(w.snapshot_path(root,TASK)); core = _core(root,snapshot)
    if (item.get('schema') != 'goal-current-assignment/v2' or item.get('source_kind') != 'official_native_queue'
            or item.get('sender_department') != ROLE or item.get('department') != PRODUCER
            or item.get('scope') != SCOPE or item.get('action_id') != REWORK
            or item.get('goal_contract') != snapshot['goal_contract']
            or item.get('authorization_pin') != snapshot['goal_delivery']['authorization_pin']):
        _fail('exact same-original reviewer-to-SYS queued continuation required')
    request = _pin(root,item['original_prepare_request']); prepared = _pin(root,item['original_prepare_result'])
    if (set(prepared) != {'exit_code','stdout','stderr'} or prepared['exit_code'] != 0 or prepared['stderr'] != ''):
        _fail('actual successful original normal prepare output required')
    prepared = json.loads(prepared['stdout']); payload = item['payload']; _pin_bytes(root,payload)
    source,target = _binding(root,ROLE),_binding(root,PRODUCER)
    expected = {'task_id':TASK,'sender_department':ROLE,'action_id':REWORK,'action_class':'thread_message',
        'scope':SCOPE,'payload':payload,'payload_sha256':payload['sha256'],'delivery_mode':'official_native_queue',
        'source_project_id':source['project_id'],'target_department':PRODUCER,
        **{k:target[v] for k,v in {'target_project_id':'project_id','target_thread_id':'task_id','target_thread_title':'title',
                                'target_cwd':'cwd','target_sidebar_section_id':'sidebar_section_id'}.items()}}
    precheck = prepared.get('authorization_precheck',{})
    if (any(request.get(k) != v for k,v in expected.items()) or request.get('authorization_changes') != []
            or request.get('assignment_record_required') is not True or prepared.get('status') != 'ready_to_queue'
            or prepared.get('payload') != payload or precheck.get('status') != 'within_original_authorization'
            or precheck.get('original_authorization') != item['authorization_pin']
            or precheck.get('actual_action_allowed') is not False or precheck.get('external_permission_issued') is not False):
        _fail('original exact allowed prepare and unchanged authority required')
    action = _one(snapshot['goal_delivery']['approved_actions'], lambda x:x.get('action_id') == REWORK, 'frozen rework action')
    if any(action.get(k) != v for k,v in expected.items() if k != 'delivery_mode') or action.get('decision_record_id') != request.get('decision_record_id'):
        _fail('exact approved continuation action required')
    decision = _one(_handoffs(root,TASK),lambda x:x.get('record_id') == request.get('decision_record_id')
        and x.get('event') == 'controller_decision' and x.get('decision') == 'rework' and x.get('coordinator_role') == ROLE,'committed actual rework')
    from scoped_candidate_adoption import _committed
    _committed(root,decision)
    policy_id = prepared.get('policy_decision',{}).get('decision_id')
    policy = _one(w.read_jsonl(Path(root)/w.POLICY_DECISIONS), lambda x:x.get('decision_id') == policy_id,'allowed original queue policy')
    policy_expected = {k:v for k,v in expected.items() if k not in {'sender_department','payload','delivery_mode'}}
    if any(policy.get(k) != v for k,v in {**policy_expected,'department':ROLE,'status':'allow','routing_status':'routing_allowed'}.items()):
        _fail('original policy identity differs')
    intent,result = (_strict_queue_document(root,item[k]) for k in ('actual_queue_intent','actual_queue_result'))
    start,finish = _queue_effect(root,payload,policy_id,intent,result,target,item.get('queue_message_id'))
    sender = _strict_queue_document(root,item['actual_native_invocation']); _binding(root,ROLE,sender)
    receiver = _strict_queue_document(root,item['actual_native_recipient']); _binding(root,PRODUCER,receiver)
    turn,call = _one([(t,c) for t in sender.get('turns',[]) for c in t.get('items',[])
        if c.get('id') == item.get('source_call_id') and c.get('type') == 'commandExecution'],lambda x:True,'original queue command')
    directory = str(Path(item['actual_queue_result']['path']).parent); command = call.get('command','')
    if (turn.get('status') != 'completed' or call.get('status') != 'completed' or call.get('exitCode') != 0
            or call.get('cwd') != source['cwd'] or not turn.get('completedAt')
            or any(token not in command for token in ('OfficialQueueTransport','.enqueue(',Path(directory).name,
                str(Path(directory).parent),Path(item['original_prepare_request']['path']).name,
                Path(item['original_prepare_result']['path']).name))):
        _fail('actual ended original successful queue command and original paths required')
    received = _one(receiver.get('turns',[]),lambda x:x.get('id') == item.get('receiver_turn_id'),'real SYS receiving turn')
    messages = received.get('items',[]); body = w.safe_path(root,payload['path']).read_text()
    user = _one(messages,lambda x:x.get('type') == 'userMessage' and x.get('id') == item.get('receiver_message_id'),'original queued SYS input')
    ack = _one(messages,lambda x:x.get('type') == 'agentMessage' and x.get('id') == item.get('ack_message_id'),'actual same-turn SYS ACK')
    if (received.get('status') not in {'inProgress','completed'} or received.get('error')
            or user.get('content') != [{'type':'text','text':body}] or not str(ack.get('text','')).strip()
            or messages.index(user) >= messages.index(ack)
            or not turn['startedAt'] <= start.timestamp() <= finish.timestamp() <= turn['completedAt']+1
            or not finish.timestamp() <= received.get('startedAt',0) <= dt.datetime.now(dt.timezone.utc).timestamp()
            or not w._parse_observed_at(policy.get('checked_at')) or w._parse_observed_at(policy['checked_at']) > start):
        _fail('actual original queue/recipient/ACK chronology required')
    if not require_dispatch:
        _fail('ordinary queued continuation resumes its existing original assignment; use assignment-record, not another dispatch/ACK')
    return snapshot,core['producer_dispatch']


def _pin_bytes(root,pin):
    if not isinstance(pin,dict) or w.file_digest(root,pin.get('path','')) != pin:
        _fail('exact original payload bytes required')
    return w.safe_path(root,pin['path']).read_bytes()


def received_notification(root, pilot, received, proof):
    """An accepted queue plus its real native input AND committed intake; no sent alias."""
    if pilot.get('task_id') != TASK or pilot.get('goal_delivery',{}).get('parent_task_id') != PARENT:
        _fail('exact original real same-parent pilot required')
    _core(root,pilot)
    if (not isinstance(proof,dict) or set(proof) != {'mode','native_recipient','receiver_turn_id','receiver_message_id'}
            or proof.get('mode') != 'official_queue_received'):
        _fail('actual original queue native input proof required')
    from goal_source_recovery import _strict_queue_document
    import result_coordination as c
    identity = c.exact_identity(received)
    if (identity['task_id'] != TASK or identity['sender_department'] != PRODUCER
            or received.get('event') != 'controller_received' or received.get('intake_mode') != 'queue'
            or received.get('coordinator_role') != ROLE or received.get('responsible_assistant') != ROLE):
        _fail('actual original A2 committed queue intake required')
    rows = _handoffs(root,TASK)
    if _received(root,rows,received.get('outbox')) != received:
        _fail('exact unique committed queue intake required')
    queued = _one(rows,lambda x:x.get('event') == 'notification_queued' and c.exact_identity(x) == identity,'original exact queued source')
    if rows.index(queued) >= rows.index(received):
        _fail('queued source must precede actual intake')
    notification = w.read_json(c._notification_path(root,identity)); transport = notification.get('native_queue_transport',{})
    if (notification.get('identity') != identity or transport.get('state') != 'accepted' or transport.get('thread_id') != _binding(root,ROLE)['task_id']
            or not transport.get('event_key') or not transport.get('native_message_id')):
        _fail('exact official queue transport readback required')
    if not re.fullmatch(r'[0-9a-f]{64}',transport['event_key']):
        _fail('exact stable original queue event identity required')
    directory = w.safe_path(root,'logs/department-event-dispatcher/prepared/'+transport['event_key'])
    def actual(name):
        return _strict_queue_document(root,w.file_digest(root,str((directory/name).relative_to(root))))
    request,prepared = actual('actual-prepare-request.json'),actual('actual-prepare-result.json')
    payload = transport.get('payload'); body = _pin_bytes(root,payload).decode('utf-8')
    from department_event_dispatcher import OfficialQueueTransport
    if (body != OfficialQueueTransport.message(None,ROLE,transport['event_key'],identity)
            or request.get('result_notification') != identity or request.get('payload') != payload
            or request.get('target_department') != ROLE or request.get('delivery_mode') != 'official_native_queue'
            or prepared.get('status') != 'ready_to_queue' or prepared.get('payload') != payload
            or prepared.get('policy_decision',{}).get('decision_id') != transport.get('policy_decision_id')):
        _fail('normal exact queue preparation and original notice bytes required')
    target = _binding(root,ROLE)
    if any(request.get(k) != v for k,v in {'task_id':TASK,'sender_department':PRODUCER,
            'notification_request_id':'native-queue:'+transport['event_key'],
            'source_project_id':target['project_id'],'target_project_id':target['project_id'],
            'target_thread_id':target['task_id'],'target_thread_title':target['title'],
            'target_cwd':target['cwd'],'target_sidebar_section_id':target['sidebar_section_id'],
            'payload_sha256':payload['sha256'],'authorization_changes':[]}.items()):
        _fail('normal original exact notice route/project/target required')
    policy = _one(w.read_jsonl(Path(root)/w.POLICY_DECISIONS),lambda x:x.get('decision_id') == transport.get('policy_decision_id'),'original notice policy')
    if any(policy.get(k) != v for k,v in {'status':'allow','department':PRODUCER,'task_id':TASK,
            'payload_sha256':payload['sha256'],'target_department':ROLE,'target_thread_id':target['task_id'],
            'source_project_id':target['project_id'],'target_project_id':target['project_id'],'target_cwd':target['cwd']}.items()):
        _fail('exact original notice policy identity required')
    intent,result = actual('native-queue-intent.json'),actual('native-queue-result.json')
    if intent.get('started_at') != transport.get('started_at'):
        _fail('original reserved notification transport time required')
    start,finish = _queue_effect(root,payload,transport['policy_decision_id'],intent,result,target,transport['native_message_id'])
    page = _strict_queue_document(root,proof['native_recipient']); _binding(root,ROLE,page)
    turn = _one(page.get('turns',[]),lambda x:x.get('id') == proof['receiver_turn_id'],'actual A2 notice receiving turn')
    user = _one(turn.get('items',[]),lambda x:x.get('type') == 'userMessage' and x.get('id') == proof['receiver_message_id'],'actual original A2 notice input')
    intake_at = w._parse_observed_at(received.get('created_at'))
    if (turn.get('status') not in {'inProgress','completed'} or turn.get('error')
            or user.get('content') != [{'type':'text','text':body}] or not intake_at
            or not finish.timestamp() <= turn.get('startedAt',0) <= intake_at.timestamp()+1
            or not w._parse_observed_at(policy.get('checked_at')) or w._parse_observed_at(policy['checked_at']) > start):
        _fail('real notice native input and committed intake chronology required')
    return {'notification_representation':'actual_official_queue_received', 'record_id':received['record_id'],
            'native_recipient':proof['native_recipient'], 'notification_sent_fabricated':False}
