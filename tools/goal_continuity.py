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
from department_rotation import historical_assignment_validator

ASSIGNMENT_SCHEMA = 'goal-current-assignment/v2'
READY_MARKER = 'FLASHCAST_DELIVERY_READY '


class SourceRegistrationPending(w.WorkflowError):
    """No delivered effect: await actual causal ACK/source registration."""



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


@historical_assignment_validator
def _dispatch_source(root, item):
    if item.get('source_kind') == 'official_native_queue':
        from goal_source_recovery import queued_assignment_source
        return queued_assignment_source(root, item)
    if item.get('source_kind') in {'owner_direct_native','historical_native_send'}:
        from goal_source_recovery import validate
        return validate(root,item)
    task, role = item['task_id'], item['department']
    snapshot = _task(root, task)
    from department_rotation import historical_registry
    registry = historical_registry(root, item)
    binding = registry.get(role, {}).get('chat_binding', {})
    goal = snapshot['goal_delivery']
    if role not in {*goal['producer_departments'], goal.get('responsible_assistant')}:
        raise w.WorkflowError('assignment department outside original goal')
    sender = item.get('sender_department')
    if sender not in {'operations', goal.get('responsible_assistant'), goal['primary_owner']}:
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
        if item.get('source_kind') == 'official_native_queue' and item.get('restore_position') == 'suspended':
            stack = current.setdefault('suspended_assignments', {}).setdefault(role, [])
            if input_pin in stack:
                return {'result':'duplicate_ignored','actual_message_delivered':True}
            stack.append(input_pin)
            w.atomic_write_json(path, current)
            return {'result':'recorded','restore_position':'suspended','actual_message_delivered':True}
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


_THREE_FAMILY_QUEUE_INTENT = {
    'path': 'logs/handoffs/2026-10-17-assistant1-business-resume-v1/A2-independent/source-candidate-v1-independent/actual-original-SYS-six-findings-native-queue-v1/native-queue-intent.json',
    'sha256': '76c404a0b403e5397dbf227880525a55392ec2a30c5ee8c0e3e9a79f2b31223e',
    'size': 316,
}
_THREE_FAMILY_QUEUE_RESULT = {
    'path': 'logs/handoffs/2026-10-17-assistant1-business-resume-v1/A2-independent/source-candidate-v1-independent/actual-original-SYS-six-findings-native-queue-v1/native-queue-result.json',
    'sha256': 'ab4f2b4767c2364e993cc881a99d323e1a288b2931041cc9b51416ff764f1cbd',
    'size': 521,
}


def _three_family_original_queue_document(root, pin, fields):
    """Strictly read the original, frozen raw queue artifact, including flags."""
    if w.file_digest(root, pin['path']) != pin:
        raise w.WorkflowError('original three-family queue bytes changed')
    def unique(pairs):
        row = {}
        for key, value in pairs:
            if key in row:
                raise ValueError('duplicate original queue field')
            row[key] = value
        return row
    try:
        value = json.loads(w.validation_bytes(w.safe_path(root, pin['path'])),
                           object_pairs_hook=unique,
                           parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite queue value')))
    except (TypeError, ValueError) as error:
        raise w.WorkflowError('unambiguous original queue JSON required') from error
    if (not isinstance(value, dict) or set(value) != fields
            or any(value.get(flag) is not None for flag in ('error', 'errors'))
            or any(flag in value and value[flag] is not False
                   for flag in ('failed', 'truncated', 'superseded', 'isError'))):
        raise w.WorkflowError('complete original queue artifact required')
    return value


def _three_family_late_registered_source(root, request, fixed_id, observed, prior, rows):
    """Authenticate the one original queue/ACK whose receipts were registered later.

    The exception is about receipt registration time only.  The original send,
    recipient turn and ACK must all precede the frozen V2 READY declaration.
    """
    task = 'fc-20261017-assistant1-original-source-recovery-v1'
    if (request.get('task_id') != task or fixed_id != 'example-native-66fec1ff8ab60fd7'
            or request.get('candidate_version') != 'assistant1-three-family-source-recovery-v2-20261017'
            or request.get('result_sha256') != '17990308ffd05675e953eb6481bf1b1a1b73b5570b40d27c8554c9ab9ed4b0ca'
            or request.get('source_turn_id') != 'example-native-0b26ee911b581d91'
            or request.get('source_message_id') != 'msg_dd72e912662084235c829af3350462d3e199f1a032ae49ec2877f2598f844b60'
            or observed != w._parse_observed_at('2026-10-17T11:26:18.793148+00:00')):
        return False
    queue_time = w._parse_observed_at(request.get('created_at'))
    if request.get('record_id') != '4755e642-e547-48ee-a610-bfaa49355b29' or queue_time is None:
        return False
    late = [r for r in prior if w._parse_observed_at(r.get('created_at')) > observed]
    ids = {'e81c834c-5165-4d76-8e48-b5944fa4813a',
           '2d8be56f-6197-4941-873a-1a91550e0ac4'}
    original = [r for r in late if r.get('receipt_id') in ids]
    future = [r for r in late if r.get('receipt_id') not in ids]
    if (len(original) != 2 or {r.get('receipt_id') for r in original} != ids
            or any(w._parse_observed_at(r.get('created_at')) <= queue_time or
                   r.get('action_id') == 'A2-three-family-v1-six-findings-original-SYS-rework-20261017-v1'
                   for r in future)):
        return False
    dispatch, ack = original
    scope = 'project:flashcast:assistant1-original-source-recovery:v1'
    action = 'A2-three-family-v1-six-findings-original-SYS-rework-20261017-v1'
    # This narrow late-registration exception cannot reuse an older success if
    # the same action failed or was sent again before the frozen READY.
    if any(row.get('department') == 'system-development'
           and row.get('chat_task_id') == fixed_id and row.get('action_id') == action
           and row.get('receipt_type') in {'dispatch_failed', 'dispatch_sent'}
           and row.get('receipt_id') not in ids
           and (stamp := w._parse_observed_at(row.get('created_at'))) is not None
           and stamp <= observed for row in rows):
        return False
    if (dispatch.get('receipt_id') != 'e81c834c-5165-4d76-8e48-b5944fa4813a'
            or ack.get('receipt_id') != '2d8be56f-6197-4941-873a-1a91550e0ac4'
            or dispatch.get('receipt_type') != 'dispatch_sent' or ack.get('receipt_type') != 'chat_ack'
            or ack.get('ack_nonempty') is not True
            or any(row.get(k) != value for row in (dispatch, ack) for k, value in
                   {'task_id':task,'department':'system-development','chat_task_id':fixed_id,
                    'scope':scope,'action_id':action,'policy_decision_id':'pol-06dc64236bfb49a78f93'}.items())
            or dispatch.get('evidence') != ack.get('evidence')
            or any(w.file_digest(root, p.get('path','')) != p for p in dispatch['evidence'])):
        return False
    evidence = {p['sha256']:p for p in dispatch['evidence']}
    if set(evidence) != {
            '51346f461d10b0028c1f3ddf3b95702c20fb671ec79e9e75d25352b08813aef0',
            '59413b59022ebdb30172559ffcb75d03b4242c687d4838764242a25f162aa917',
            '2747eb597239b7b2444b6877e41cfd217e120fc7b07959eadd63881a7c17f52c'}:
        return False
    source = pin_document(root,evidence['51346f461d10b0028c1f3ddf3b95702c20fb671ec79e9e75d25352b08813aef0'])
    action_source = pin_document(root,evidence['2747eb597239b7b2444b6877e41cfd217e120fc7b07959eadd63881a7c17f52c'])
    payload = source.get('payload')
    if (source.get('task_id') != task or source.get('action_id') != action
            or source.get('message_resent') is not False
            or source.get('actual_receiving_turn') != request['source_turn_id']
            or source.get('actual_userMessage_id') != 'example-native-53bf67606361950b'
            or source.get('actual_nonempty_ACK_id') != 'msg_1018be03882170dcbf2d42f309191a4b5486c741bf7e8867922a29eac1af6ab6'
            or not isinstance(source.get('actual_nonempty_ACK_UTF8'),str)
            or not source['actual_nonempty_ACK_UTF8'].strip()
            or not isinstance(payload,dict) or w.file_digest(root,payload.get('path','')) != payload
            or action_source.get('payload') != payload
            or any(action_source.get(k) != value for k,value in
                   {'task_id':task,'action_id':action,'scope':scope,
                    'target_thread_id':fixed_id,'target_department':'system-development',
                    'decision_record_id':'983445f4-27df-4353-8bb3-8366f6207ee8'}.items())):
        return False
    intent = _three_family_original_queue_document(root, _THREE_FAMILY_QUEUE_INTENT,
        {'started_at', 'thread_id', 'payload_sha256', 'policy_decision_id', 'transport', 'intake_claimed'})
    result = _three_family_original_queue_document(root, _THREE_FAMILY_QUEUE_RESULT,
        {'started_at', 'thread_id', 'payload_sha256', 'policy_decision_id', 'transport',
         'intake_claimed', 'finished_at', 'exit_code', 'stdout', 'stderr'})
    start = w._parse_observed_at(intent.get('started_at'))
    finish = w._parse_observed_at(result.get('finished_at'))
    if (intent.get('thread_id') != fixed_id or intent.get('payload_sha256') != payload['sha256']
            or intent.get('policy_decision_id') != dispatch['policy_decision_id']
            or intent.get('transport') != 'official_codex_queue' or intent.get('intake_claimed') is not False
            or result.get('thread_id') != fixed_id or result.get('payload_sha256') != payload['sha256']
            or result.get('policy_decision_id') != dispatch['policy_decision_id']
            or result.get('started_at') != intent.get('started_at')
            or result.get('transport') != intent.get('transport')
            or result.get('intake_claimed') is not False
            or type(result.get('exit_code')) is not int or result.get('exit_code') != 0
            or result.get('stderr') != ''
            or result.get('stdout') != 'Queued message example-native-e1b2c472568d116b for thread '+fixed_id+'.\n'
            or start is None or finish is None or start > finish or finish > observed):
        return False
    sender_page = native(root,evidence['59413b59022ebdb30172559ffcb75d03b4242c687d4838764242a25f162aa917'])
    receiver_page = native(root,source['actual_native_recipient'])
    registry = w.department_registry(root)
    source_binding = registry['operations-assistant-2']['chat_binding']
    target_binding = registry['system-development']['chat_binding']
    policies = [p for p in w.read_jsonl(Path(root) / w.POLICY_DECISIONS)
                if p.get('decision_id') == dispatch['policy_decision_id']]
    if len(policies) != 1:
        return False
    policy = policies[0]
    checked_at = w._parse_observed_at(policy.get('checked_at'))
    expected_policy = {
        'status': 'allow', 'routing_status': 'routing_allowed',
        'action_class': 'thread_message', 'task_id': task,
        'department': 'operations-assistant-2', 'target_department': 'system-development',
        'action_id': action, 'scope': scope, 'payload_sha256': payload['sha256'],
        'source_project_id': source_binding['project_id'],
        'target_project_id': target_binding['project_id'],
        'target_thread_id': fixed_id, 'target_thread_title': target_binding['title'],
        'target_cwd': target_binding['cwd'],
        'target_sidebar_section_id': target_binding['sidebar_section_id'],
    }
    if (any(policy.get(key) != value for key, value in expected_policy.items())
            or checked_at is None or start is None or checked_at > start):
        return False
    for page, role in ((sender_page,'operations-assistant-2'),(receiver_page,'system-development')):
        binding = registry[role]['chat_binding']
        if any(page.get('thread',{}).get(k) != binding.get(v) for k,v in
               {'id':'task_id','title':'title','cwd':'cwd'}.items()):
            return False
    calls = [(turn,item) for turn in sender_page.get('turns',[]) for item in turn.get('items',[])
             if item.get('id') == 'exec-58330fd9-4e3d-4858-9e2c-40f00bf2c0ea']
    if (len(calls) != 1 or calls[0][0].get('status') not in {'completed','inProgress'}
            or calls[0][0].get('error') or calls[0][1].get('type') != 'commandExecution'
            or calls[0][1].get('status') != 'completed' or calls[0][1].get('exitCode') != 0
            or calls[0][1].get('cwd') != action_source.get('target_cwd')
            or type(calls[0][0].get('startedAt')) not in {int,float}
            or not calls[0][0]['startedAt'] <= checked_at.timestamp() <= start.timestamp()
            or not start <= finish):
        return False
    turns = [turn for turn in receiver_page.get('turns',[])
             if turn.get('id') == source['actual_receiving_turn']]
    if len(turns) != 1 or turns[0].get('status') not in {'completed','inProgress'} or turns[0].get('error'):
        return False
    turn = turns[0]
    messages = [(i,item) for i,item in enumerate(turn.get('items',[]))
                if item.get('id') in {source['actual_userMessage_id'],source['actual_nonempty_ACK_id'],
                                      request['source_message_id']}]
    if (len(messages) != 3 or [item.get('id') for _,item in messages] !=
            [source['actual_userMessage_id'],source['actual_nonempty_ACK_id'],request['source_message_id']]
            or messages[0][1].get('type') != 'userMessage'
            or messages[0][1].get('content') != [{'type':'text','text':w.safe_path(root,payload['path']).read_text(encoding='utf-8')}]
            or messages[1][1].get('type') != 'agentMessage'
            or messages[1][1].get('phase') not in {'commentary','final_answer'}
            or messages[1][1].get('text') != source['actual_nonempty_ACK_UTF8']
            or messages[2][1].get('type') != 'agentMessage'
            or type(turn.get('startedAt')) not in {int,float}
            or not finish.timestamp() <= turn['startedAt'] <= observed.timestamp()):
        return False
    return True


def _registered_native_pair(root, request, rows, source_rows, observed, page):
    """Prove effect order in the original native turn, never by backdating rows.

    An ACK appended after the result is usable only with its authenticated
    original send/assignment and one unchanged native ACK before that result.
    Unknown or newly assigned responsibility is not an ordinary continuation.
    """
    if not isinstance(request, dict) or not isinstance(page, dict) or observed is None:
        return None
    role, task = request.get('sender_department'), request.get('task_id')
    fixed = w.department_registry(root).get(role, {}).get('chat_binding', {})
    if (request.get('source_thread_id') != fixed.get('task_id')
            or any(page.get('thread', {}).get(k) != fixed.get(v) for k,v in
                   {'id':'task_id','title':'title','cwd':'cwd'}.items())
            or page.get('thread', {}).get('hostId', 'local') != 'local'
            or page.get('thread', {}).get('projectId', fixed.get('project_id')) != fixed.get('project_id')):
        raise w.WorkflowError('causal source requires the real original fixed project/role')
    selected = [t for t in page.get('turns', []) if t.get('id') == request.get('source_turn_id')]
    if len(selected) != 1:
        raise w.WorkflowError('one exact native source turn required for registration')
    turn = selected[0]; items = turn.get('items', [])
    results = [(i,m) for i,m in enumerate(items) if m.get('id') == request.get('source_message_id')]
    if (page.get('truncated',False) or turn.get('truncated',False)
            or any(m.get('truncated',False) for m in items)
            or turn.get('status') not in {'completed','inProgress'} or turn.get('error')
            or type(turn.get('startedAt')) not in {int,float} or turn['startedAt'] > observed.timestamp()
            or len(results) != 1 or results[0][1].get('type') != 'agentMessage'
            or results[0][1].get('phase') not in {'commentary','final_answer'}
            or hashlib.sha256(results[0][1].get('text','').encode()).hexdigest() != request.get('source_reply_sha256')):
        raise w.WorkflowError('unchanged actual result message and original native chronology required')
    # Select the same responsibility that existed at result observation time.
    sends = [r for r in source_rows if r.get('receipt_type') in {'dispatch_sent','dispatch_failed'}
             and w._parse_observed_at(r.get('created_at')) <= observed]
    if not sends or sends[-1].get('receipt_type') != 'dispatch_sent':
        return None
    dispatch = sends[-1]
    acks = [r for r in source_rows if r.get('receipt_type') == 'chat_ack' and r.get('ack_nonempty') is True
            and rows.index(r) > rows.index(dispatch)
            and all(r.get(k) == dispatch.get(k) for k in
                    ('task_id','department','chat_task_id','action_id','action_class','scope','policy_decision_id'))]
    if len(acks) != 1:
        return None
    ack = acks[0]
    if (any(r.get('supersedes_receipt_id') in {dispatch.get('receipt_id'),ack.get('receipt_id')} for r in rows)
            or ack.get('approval_id') or ack.get('replacement_reason')
            or len(ack.get('evidence', [])) != 1):
        raise w.WorkflowError('one intact unreplaced actual ACK registration required')
    current = w.read_json(Path(root)/'data/department-current-assignment.json')
    pins = [current.get('assignments', {}).get(role), *current.get('suspended_assignments', {}).get(role, [])]
    assignments = []
    for pin in pins:
        if not pin: continue
        item = pin_document(root,pin)
        if (item.get('task_id') != task or item.get('department') != role
                or item.get('action_id') != dispatch.get('action_id') or item.get('scope') != dispatch.get('scope')):
            continue
        _, sent = _dispatch_source(root,item)
        if sent.get('receipt_id') == dispatch.get('receipt_id') and pin not in [v[0] for v in assignments]:
            assignments.append((pin,item))
    if len(assignments) != 1:
        return None
    ack_page = native(root,ack['evidence'][0])
    if any(ack_page.get('thread', {}).get(k) != fixed.get(v) for k,v in
           {'id':'task_id','title':'title','cwd':'cwd'}.items()):
        raise w.WorkflowError('ACK evidence must retain the actual original role')
    actual = [t for t in ack_page.get('turns', []) if t.get('id') == turn['id']]
    if (len(actual) != 1 or actual[0].get('error') or actual[0].get('status') not in {'inProgress','completed'}
            or actual[0].get('startedAt') != turn['startedAt']):
        raise w.WorkflowError('ACK and result must share the unchanged original receiving turn')
    replies = [m for m in actual[0].get('items', []) if m.get('type') == 'agentMessage'
               and m.get('phase') in {'commentary','final_answer'} and m.get('text','').strip()]
    # The earliest observed nonempty receiving reply is the actual ACK, not a
    # later result/progress message chosen by the caller.
    if not replies: return None
    matching = [(i,m) for i,m in enumerate(items) if m.get('id') == replies[0].get('id')]
    if len(matching) != 1 or matching[0][1] != replies[0] or matching[0][0] >= results[0][0]:
        raise w.WorkflowError('actual nonempty native ACK must precede this exact frozen result')
    return dispatch, ack


def _registration_observation(root, request, rows, source_rows, observed):
    """Read one append-only causal observation without rewriting the request."""
    expected = {k:request.get(k) for k in ('task_id','sender_department','candidate_version','result_sha256',
                                          'source_thread_id','source_turn_id','source_message_id','source_reply_sha256')}
    observations = [e['details']['original_result_registration_observed']
        for e in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS)
        if e.get('task_id') == request.get('task_id') and
        e.get('details', {}).get('original_result_registration_observed', {}).get('identity') == expected]
    if not observations: return None
    if w.validate_workflow_events(root,request['task_id']):
        raise w.WorkflowError('intact source-registration event chain required')
    if len(observations) != 1:
        raise w.WorkflowError('one immutable registration observation required')
    event = observations[0]; original = pin_document(root,event['original_request'])
    if any(original.get(k) != v for k,v in expected.items()):
        raise w.WorkflowError('registration cannot replace original result identity')
    pair = _registered_native_pair(root,original,rows,source_rows,observed,native(root,event['native_observation']))
    if pair is None or [r['receipt_id'] for r in pair] != event.get('receipt_ids'):
        raise w.WorkflowError('registration observation no longer matches the original source facts')
    return pair


def defer_result_registration(root, request):
    """Keep the exact failed request in existing events; never queue or send it."""
    if request.get('event') != 'notification_queued' or request.get('result_source_phase') != 'delivery_ready':
        raise w.WorkflowError('only the original exact READY request can await registration')
    from result_coordination import exact_identity
    identity = exact_identity(request); task = identity['task_id']; snapshot = _task(root,task)
    if snapshot.get('current_state') in w.TERMINAL_STATES:
        raise w.WorkflowError('closed goal cannot defer a new result')
    key = w.sha256_value(identity)
    path = Path(root)/'logs/department-event-dispatcher/prepared'/('source-registration-'+key)/'original-request.json'
    with w.workflow_lock(root):
        old = w.read_json(path)
        if old and old != request: raise w.WorkflowError('preserve original frozen pending source request')
        if not old: w.atomic_write_json(path,request)
        proof = {'identity':identity,'original_request':w.file_digest(root,str(path.relative_to(root))),
                 'next_owner':identity['sender_department'],'state':'await_actual_source_registration',
                 'notification_queued':False,'execution_authority_added':False}
        prior = [e for e in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS) if e.get('task_id') == task and
                 e.get('details', {}).get('original_result_registration_pending', {}).get('identity') == identity]
        if prior:
            if len(prior) != 1 or prior[0]['details']['original_result_registration_pending'] != proof:
                raise w.WorkflowError('one immutable pending original result required')
            return {'state':'duplicate_ignored','event_id':prior[0]['event_id']}
        event = w.append_workflow_event(root,task,snapshot['current_state'],
            {'original_result_registration_pending':proof,'external_permission_issued':False})
    return {'state':'pending_source_registration','event_id':event['event_id'],'message_sent':False}


def observe_result_registration(root, input_path):
    """Register true ACK/result order only; no send, intake, QA or permission."""
    pin = w.file_digest(root,input_path); item = pin_document(root,pin)
    if set(item) != {'schema','original_request','native_observation'} or item.get('schema') != 'original-result-registration-observation/v1':
        raise w.WorkflowError('finite original registration observation required')
    request = pin_document(root,item['original_request']); page = native(root,item['native_observation'])
    if request.get('event') != 'notification_queued' or request.get('result_source_phase') != 'delivery_ready':
        raise w.WorkflowError('only one original frozen READY result registration is representable')
    # Validate the original declaration/outbox/role/contract and timestamps via
    # the normal READY consumer using this genuine fuller observation. The
    # immutable original request remains untouched.
    ready_source(root,{**request,'actual_native_completion':item['native_observation']},request['source_thread_id'])
    task, role = request['task_id'], request['sender_department']; snapshot = _task(root,task)
    if snapshot.get('current_state') in w.TERMINAL_STATES:
        raise w.WorkflowError('closed goal cannot append a new causal registration')
    if role not in {*snapshot['goal_delivery']['producer_departments'],snapshot['goal_delivery']['responsible_assistant']}:
        raise w.WorkflowError('actual original goal participant required for source registration')
    rows,bad = w._validate_receipt_chain(root,task)
    if bad or w.validate_workflow_events(root,task): raise w.WorkflowError('intact original registration receipt and event chains required')
    source_rows = [r for r in rows if r.get('department') == role
        and r.get('chat_task_id') == request.get('source_thread_id')
        and r.get('receipt_type') in {'dispatch_sent','chat_ack','dispatch_failed'}]
    observed = w._parse_observed_at(request.get('reply_observed_at'))
    pair = _registered_native_pair(root,request,rows,source_rows,observed,page)
    if pair is None: raise w.WorkflowError('real registered original send/ACK and native result order required')
    identity = {k:request.get(k) for k in ('task_id','sender_department','candidate_version','result_sha256',
        'source_thread_id','source_turn_id','source_message_id','source_reply_sha256')}
    facts = {'identity':identity, **{k:item[k] for k in ('original_request','native_observation')},
             'receipt_ids':[r['receipt_id'] for r in pair], 'execution_authority_added':False}
    with w.workflow_lock(root):
        old = [e for e in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS) if e.get('task_id') == task
               and e.get('details', {}).get('original_result_registration_observed', {}).get('identity') == identity]
        if old:
            if len(old) != 1 or old[0]['details']['original_result_registration_observed'] != facts:
                raise w.WorkflowError('original causal registration already frozen; no replacement')
            return {'state':'duplicate_ignored','event_id':old[0]['event_id'],'result_identity_unchanged':True}
        # Recheck every native/request pin and source proof under the normal lock.
        if pin_document(root,pin) != item or pin_document(root,item['original_request']) != request:
            raise w.WorkflowError('original registration input changed during append')
        check,bad = w._validate_receipt_chain(root,task)
        if bad or check != rows: raise w.WorkflowError('original receipt source changed during append')
        if _registered_native_pair(root,request,check,source_rows,observed,native(root,item['native_observation'])) != pair:
            raise w.WorkflowError('native registration source changed during append')
        event = w.append_workflow_event(root,task,snapshot['current_state'],
            {'original_result_registration_observed':facts,'external_permission_issued':False})
    return {'state':'source_registered','event_id':event['event_id'],'result_identity_unchanged':True,
            'notification_sent':False,'result_received':False,'QA_written':False,'permissions_issued':False}


def _ready_receipt_prefix(source_rows, observed, *, root=None, snapshot=None, receipts=None, plan=None, source_request=None, source_page=None):
    """Select the causal source before READY from the intact full receipt chain.

    A later continuation cannot change this prefix. Its timestamps must still be
    valid and ordered; no late row may be backdated into the original prefix.
    """
    if observed is None:
        return None, False
    previous = None
    prefix = []
    now = dt.datetime.now(dt.timezone.utc)
    for row in source_rows:
        stamp = w._parse_observed_at(row.get('created_at'))
        if stamp is None or stamp > now or (previous is not None and stamp < previous):
            return None, True
        previous = stamp
        if stamp <= observed:
            prefix.append(row)
    ordinary = set()
    if root is not None and snapshot is not None and plan is not None:
        from qa_review_plan import ordinary_original_source_receipt_ids
        ordinary = ordinary_original_source_receipt_ids(root, snapshot, receipts, plan)
    dispatch, pair = None, None
    for row in prefix:
        if row.get('receipt_id') in ordinary:
            continue  # A proven transport observation is not a new responsibility.

        kind = row.get('receipt_type')
        if kind == 'dispatch_sent':
            dispatch, pair = row, None
        elif kind == 'dispatch_failed':
            dispatch, pair = None, None
        elif kind == 'chat_ack' and dispatch is not None and row.get('ack_nonempty') is True:
            # Original task ACKs may omit action labels. If supplied, their
            # exact action/policy/scope must belong to this preceding dispatch.
            if all(not row.get(key) or row.get(key) == dispatch.get(key)
                   for key in ('action_id', 'action_class', 'scope', 'policy_decision_id')):
                pair = dispatch, row
    if pair is None and root is not None and source_request is not None:
        candidates = [r for r in source_rows if r.get('receipt_id') not in ordinary]
        pair = _registration_observation(root,source_request,receipts,candidates,observed)
        if pair is None and source_page is not None:
            pair = _registered_native_pair(root,source_request,receipts,candidates,observed,source_page)
    return pair, False


def ready_source(root, request, fixed_id, *, scheduled=False, through_receipt_id=None):
    """A frozen batch declaration can be handed off before its turn terminates."""
    task=request['task_id'];sender=request['sender_department']
    if scheduled:
        source=w.scheduled_result_source(root,task,sender)
        if (not source or source.get('legacy_contract') or request.get('source_automation_id')!=source['automation_id']):
            raise w.WorkflowError('exact admitted current daily source required')
        allowed_senders={sender}
    else:
        snapshot=_task(root,task)
        goal=snapshot['goal_delivery']
        allowed_senders={*goal['producer_departments'],goal.get('responsible_assistant')}
    if sender not in allowed_senders:
        raise w.WorkflowError('ready source outside original goal')
    page=native(root,request['actual_native_completion'])
    binding=w.department_registry(root)[sender]['chat_binding']
    if fixed_id != binding.get('task_id'):
        from department_rotation import frozen_ready_binding
        binding=frozen_ready_binding(root,request,fixed_id)
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
    rows,bad=w._validate_receipt_chain(root,task,through_receipt_id=through_receipt_id)
    source_rows=[r for r in rows if r.get('department')==sender and r.get('chat_task_id')==fixed_id
                 and r.get('receipt_type') in {'dispatch_sent','chat_ack','dispatch_failed'}]
    prior=[r for r in source_rows if r.get('receipt_type') != 'dispatch_failed']
    plan = None
    if not scheduled:
        from qa_review_plan import load_plan
        plan = load_plan(root, snapshot)
    prefix, source_chronology_bad = _ready_receipt_prefix(source_rows, observed,
        root=root, snapshot=None if scheduled else snapshot, receipts=rows, plan=plan,
        source_request=None if scheduled else request, source_page=page)
    prior_ok=bool(prefix)
    if not scheduled and not prior_ok and not source_rows:
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
                   if isinstance(plan,dict) and fixed_id=='example-native-51808768551cf834'
                   else None)
        prior_ok=bool(observed is not None and inherited
                      and inherited.get('production_permissions_inherited') is False
                      and all(w._parse_observed_at(inherited[k]['created_at']) <= observed
                              for k in ('dispatch','ack')))
    late_prior = (not prefix and any((stamp := w._parse_observed_at(r.get('created_at'))) is not None
                                   and stamp > observed for r in prior)) if observed else True
    from department_rotation import continued_ready_prefix
    continuation = (continued_ready_prefix(root,request,fixed_id,observed,rows)
                    if not scheduled and not bad else None)
    if continuation is not None:
        prior_ok, late_prior = True, False
    recovered = (not scheduled and late_prior and not bad and bool(prior) and
                 _three_family_late_registered_source(root,request,fixed_id,observed,prior,rows))
    if recovered:
        prior_ok = True  # This existing narrow path authenticates the real original native prefix.
    if (bad or source_chronology_bad or observed is None or observed>dt.datetime.now(dt.timezone.utc)
            or type(start) not in {int,float} or start>observed.timestamp()):
        raise w.WorkflowError('ready declaration requires preceding actual task dispatch/ACK')
    if (not scheduled and not prior_ok) or (late_prior and not recovered):
        raise SourceRegistrationPending('exact original READY awaits actual causal dispatch/ACK registration')
    return {**({'original_rotation_continuation':continuation} if continuation is not None else {}),
            **{k:request[k] for k in ('source_turn_id','source_thread_id','source_message_id',
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
        from goal_source_recovery import actual_target_turn_status
        # A single-recipient pin cannot be reused for every assistant.
        role_live={**live};role_live.pop('actual_native_target_turn',None)
        status=actual_target_turn_status(root,role_live,rows[0],binding)
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


def grouped_work_projection(role,assignment,groups,ready,waiting,errors):
    def aggregate(rows,stage):
        buckets={}
        for row in rows:
            task=row.get('task_id')
            if not task:continue
            key=(task,role,stage)
            item=buckets.setdefault(key,{'task_id':task,'department':role,'stage':stage,'items':[],
                                        'inventory_is_permission':False})
            if row not in item['items']:item['items'].append(row)
        return list(buckets.values())
    raw=[]
    if assignment:
        if assignment.get('resume_required'):raw.append(assignment)
        raw.extend(assignment.get('unfinished_assignment_queue',[]))
    current=assignment.get('task_id') if assignment and assignment.get('resume_required') else None
    current_errors=[e for e in errors if (current and e.get('task_id')==current)
                    or e.get('stage')=='current_assignment_recovery']
    historical=[e for e in errors if e not in current_errors]
    completed=[item for item in groups.values() if item.get('target_department')==role
               and item.get('controller_decision')=='close_scope' and item.get('committed_stage_verified') is True
               and item.get('controller_followthrough') not in {None,'pending'}]
    return {'schema':'task-department-stage-projection/v1',
        'current_execution':aggregate([assignment] if current else [],'current_execution'),
        'effective_unfinished':aggregate(raw,'original_responsibility'),
        'executable':aggregate(ready,'next_legal_action'),
        'pending_review':aggregate([v for v in ready if v.get('next_action') in {
            'claim_and_receive_original_frozen_result','review_received_exact_result'}],'independent_review'),
        'named_waiting':aggregate(waiting,'named_waiting'),
        'historical_anomalies':historical,'current_blockers':current_errors,
        'completed_result_scopes':aggregate(completed,'result_scope_completed'),
        'raw_suspended_source_versions':max(0,len(raw)-(1 if current else 0)),
        'paused_versions_are_separate_todos':False,'business_parent_completion_inferred':False,
        'cache_is_rebuildable':True,'permission_cache':False}


def work_boundary(root, role, *, assignment=None, read_assignment=True):
    from department_autonomy import current_mode,work_boundary as autonomous_work_boundary
    if current_mode(root):return autonomous_work_boundary(root,role,assignment,read_assignment)
    from readonly_work_view_cache import inventory_session
    with w.request_validation_context(), inventory_session(root):
        return _work_boundary_view(root,role,assignment=assignment,read_assignment=read_assignment)


def _work_boundary_view(root, role, *, assignment=None, read_assignment=True):
    """Read current work before maintenance/NO_CHANGE; never send or grant rights.

    Inventory uses authenticated ledger bytes, not a full historical re-review.
    Each action still uses the existing exact claim/source/policy consumers.
    """
    import result_coordination as rc
    from readonly_work_view_cache import inventory_handoff_rows
    registry=w.department_registry(root)
    if role not in registry:raise w.WorkflowError('registered work-boundary role required')
    ready=[];waiting=[];errors=[];groups={}
    if read_assignment:
        try:assignment=rc.current_assignment_for_role(root,role)
        except (w.WorkflowError,OSError,ValueError,KeyError,TypeError) as exc:
            errors.append({'owner':role,'stage':'current_assignment_recovery','reason':str(exc)})
    if assignment:
        errors.extend({'owner':role,'stage':'assignment_record_recovery',**item}
                      for item in assignment.get('assignment_errors',[]))
    for path in sorted((Path(root)/w.RESULT_HANDOFF_DIR).glob('*.jsonl')):
        try:
            snap=w.read_json(w.snapshot_path(root,path.stem));goal=snap.get('goal_delivery',{})
            sources=w.read_json(Path(root)/'data/task-contract.json').get('result_handoff_contract',{}).get('scheduled_daily_sources',[])
            scheduled=[s for s in sources if isinstance(s,dict) and re.fullmatch(s.get('task_id_pattern','(?!)'),path.stem)]
            relevant=(goal and (role in goal.get('producer_departments',[]) or role==goal.get('responsible_assistant')
                               or role=='operations' or role=='operations-assistant' and __import__('chief_assistant_coordination').authority(root) is not None)) or any(role in {s.get('department'),s.get('responsible_assistant')} for s in scheduled)
            if not relevant and not scheduled:continue
            rows=inventory_handoff_rows(root,path.stem)
            # Scheduled routing belongs to the frozen result identity. Intake
            # and decision events need not repeat the original source fields.
            daily_targets={}
            if not goal:
                for row in rows:
                    if row.get('event')!='notification_queued' or row.get('source_mode')!='scheduled_run':continue
                    identity=rc.exact_identity(row)
                    source=w.scheduled_result_source(root,path.stem,identity['sender_department'])
                    if source and row.get('source_automation_id')==source['automation_id']:
                        daily_targets[rc._key(identity)]=daily_selected_assistant(root,identity,source['responsible_assistant'])
            if not relevant and role not in daily_targets.values():continue
            for row in rows:
                identity=rc.exact_identity(row);sender=identity['sender_department']
                target=goal.get('responsible_assistant') if sender in goal.get('producer_departments',[]) else None
                owner_returns=w.read_json(Path(root)/'data/task-contract.json').get('result_handoff_contract',{}).get('owner_direct_return_sources',[])
                exact_returns=[s for s in owner_returns if s.get('identity')==identity]
                if len(exact_returns)==1:target=exact_returns[0]['responsible_assistant']
                knowledge=bool(goal and sender==goal.get('responsible_assistant'))
                if knowledge:target='operations'
                if not goal:target=daily_targets.get(rc._key(identity),target)
                delegated=(target=='operations' and role=='operations-assistant' and __import__('chief_assistant_coordination').authority(root) is not None)
                if target!=role and sender!=role and not delegated:continue
                key=rc._key(identity)
                item=groups.setdefault(key,{**identity,'target_department':target,
                    'knowledge_only':knowledge,'events':[], 'controller_followthrough':'pending'})
                item['events'].append(row['event'])
                if row['event'] in {'controller_decision','controller_followthrough'}:
                    item.setdefault('final_record_refs',[]).append({'record_id':row['record_id'],
                        'record_hash':row['record_hash']})
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
            if 'controller_received' in events:
                try:
                    received=rc._received_delivery(root,rc.exact_identity(item),
                        {'lane':'HQ_knowledge','target_department':role})
                    if received is None:raise w.WorkflowError('committed original HQ intake required')
                except (w.WorkflowError,OSError,ValueError,KeyError,TypeError,AttributeError) as exc:
                    errors.append({'task_id':item['task_id'],'identity':rc.exact_identity(item),
                        'stage':'committed_HQ_intake','reason':str(exc),'blocks_other_tasks':False})
            else:
                try:
                    rc.hq_knowledge_source(root,rc.exact_identity(item))
                except (w.WorkflowError,OSError,ValueError,KeyError,TypeError,AttributeError) as exc:
                    errors.append({'task_id':item['task_id'],'identity':rc.exact_identity(item),'owner':role,
                        'stage':'HQ_knowledge_source','block_reason':str(exc),'actionable':False,
                        'next_action':'recover_exact_original_conclusion_or_verified_successor',
                        'unblock_condition':'original conclusion proof or verified successor evidence restored',
                        'next_check_at':'original_source_changed','blocks_other_tasks':False})
                else:ready.append({**item,'next_action':'receive_exact_HQ_knowledge_without_second_review'})
            continue
        if 'controller_received' in events:
            try:
                intake = rc._received_delivery(root,rc.exact_identity(item),
                    {'lane':'professional_acceptance','target_department':role})
                if intake is None:raise w.WorkflowError('original committed intake required')
            except (w.WorkflowError,OSError,ValueError,KeyError,TypeError,AttributeError) as exc:
                errors.append({'task_id':item['task_id'],'identity':rc.exact_identity(item),
                    'stage':'original_intake_projection','reason':str(exc),'blocks_other_tasks':False})
                continue
        if item.get('final_record_refs'):
            try:
                source_rows=inventory_handoff_rows(root,item['task_id'])
                for ref in item['final_record_refs']:
                    found=[r for r in source_rows if r.get('record_id')==ref['record_id']
                           and r.get('record_hash')==ref['record_hash']]
                    if len(found)!=1:raise w.WorkflowError('one exact original decision/followthrough required')
                    rc._committed_result(root,found[0])
                    actor=found[0].get('coordinator_role')
                    if actor is None:actor=rc._committed_intake_actor(root,found[0])[0]
                    if actor!=role:raise w.WorkflowError('committed decision/followthrough role differs')
                item['committed_stage_verified']=True
            except (w.WorkflowError,OSError,ValueError,KeyError,TypeError,AttributeError) as exc:
                errors.append({'task_id':item['task_id'],'identity':rc.exact_identity(item),
                    'stage':'original_decision_projection','reason':str(exc),'blocks_other_tasks':False})
                continue
        if 'controller_decision' not in events:
            ready.append({**item,'next_action':'review_received_exact_result' if 'controller_received' in events
                          else 'claim_and_receive_original_frozen_result'})
        elif w._followthrough_due(item):
            ready.append({**item,'next_action':'execute_original_decision_followthrough'})
        elif w._followthrough_waiting(item):waiting.append({**item,'next_action':'wait_named_dependency'})
    deliveries=rc.notification_plan(root,role)
    for notice in deliveries['notifications']:
        # Sending stays with the producer; only original HQ owns activation
        # of an accepted/uncertain queue. This is the same existing work view.
        recovery = notice.get('activation_recovery')
        recovery_owned = bool(recovery and recovery.get('recovery_owner') == role)
        if notice.get('delivery_owner') != role and not recovery_owned:continue
        state = recovery.get('state', {}) if recovery_owned else {}
        due = notice.get('actionable') and not state.get('intent_reserved')
        (ready if due else waiting).append({
            **notice.get('identity',{}),'next_action':notice['next_action'],
            'kind':'original_queue_activation' if recovery_owned else 'actual_notification_delivery',
            'activation_recovery':recovery if recovery_owned else None,
            'queue_is_delivery':False})
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
    projection = grouped_work_projection(role,assignment,groups,ready,waiting,errors)
    return {'schema':'goal-work-boundary/v1','department':role,
            'grouped_work':projection,
            'actual_current_assignment':assignment,'ready_actions':ready,'waiting_actions':waiting,
            'source_errors':errors,'actionable_count':len(ready),
            'can_report_no_change':not ready and not projection['current_blockers'],
            'source_error_fingerprint':w.sha256_value(errors),
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
