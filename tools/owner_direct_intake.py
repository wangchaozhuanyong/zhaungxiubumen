"""Exact owner-origin intake. Trusted native observations are inputs, never authentication.

No chat transcript is stored; no headquarters dispatch or ACK is synthesized.
"""
from pathlib import Path
import datetime as dt
import hashlib
import json
import re
import human_control
import workflow_control as w

DIRECTORY = 'data/owner-direct-intake'
DEVELOPER = 'designated-website-developer'


def native_time(value):
    """Native observations must state their timezone, not silently assume UTC."""
    if not isinstance(value,str):return None
    try:parsed=dt.datetime.fromisoformat(value[:-1]+'+00:00' if value.endswith('Z') else value)
    except ValueError:return None
    return parsed.astimezone(dt.timezone.utc) if parsed.tzinfo is not None else None


def path_for(root, task_id):
    return w.safe_path(root, DIRECTORY + '/' + w.validate_task_id(task_id) + '.json')


def intake(root, request):
    with human_control.action_gate(root, request.get('task_id')):
        task = w.validate_task_id(request.get('task_id', ''))
        role = request.get('executor_role')
        human = request.get('human_message', {})
        scope = request.get('authorized_scope')
        observed = native_time(human.get('observed_at'))
        authorized = native_time(human.get('authorized_at'))
        now = dt.datetime.now(dt.timezone.utc)
        if (human.get('source') != 'human_user_message' or not human.get('message_id')
                or not human.get('thread_id') or not human.get('authorized_at')
                or authorized is None
                or not re.fullmatch('[a-f0-9]{64}', str(human.get('message_sha256', '')))
                or human.get('explicit_task_id') != task or human.get('explicit_scope') != scope
                or not isinstance(scope, str) or not scope.strip()
                or observed is None or not 0 <= (now - observed).total_seconds() <= 300
                or not authorized <= observed <= now
                or human.get('trusted_native_readback') is not True):
            raise w.WorkflowError('exact actual human message/scope/time and fresh native readback required')
        registry = w.department_registry(root)
        if role == DEVELOPER and role not in registry:
            import developer_bridge
            pin = request.get('bridge_request')
            if not isinstance(pin, dict) or w.file_digest(root, pin.get('path', '')) != pin:
                raise w.WorkflowError('external developer requires original frozen authorized bridge')
            bridge = w.read_json(w.safe_path(root, pin['path']))
            if bridge.get('original_software_task_id', task) != task:
                raise w.WorkflowError('bridge original task differs')
            send_pin = request.get('native_send')
            if not isinstance(send_pin, dict) or w.file_digest(root, send_pin.get('path', '')) != send_pin:
                raise w.WorkflowError('actual original native developer send required')
            sent = w.read_json(w.safe_path(root, send_pin['path']))
            decisions=[r for r in w.read_jsonl(Path(root)/w.POLICY_DECISIONS) if r.get('decision_id')==sent.get('policy_decision_id')]
            if ((sent.get('message_sent') is not True and not (sent.get('status')=='ACTUALLY_SENT' and sent.get('native_success') is True and sent.get('native_result')))
                    or sent.get('original_software_task_id',task)!=task
                    or len(decisions)!=1 or decisions[0].get('status')!='allow'
                    or any(decisions[0].get(k)!=bridge.get(k) for k in ('task_id','action_id','scope','target_thread_id','payload_sha256'))
                    or sent.get('payload_sha256') != bridge.get('payload_sha256')
                    or any(bridge.get(k) != v for k,v in developer_bridge.DEVELOPER.items())
                    or sent.get('target_thread_id') != bridge['target_thread_id']):
                raise w.WorkflowError('external completion must bind actual original send and exact developer')
            binding = {'task_id': bridge['target_thread_id'], 'title': bridge['target_thread_title'],
                'project_id': bridge['target_project_id'], 'cwd': bridge['target_cwd']}
        else:
            binding = registry.get(role, {}).get('chat_binding', {})
            if role == 'operations' or not binding.get('task_id'):
                raise w.WorkflowError('registered fixed executor role required')
            if human['thread_id'] != binding['task_id']:
                raise w.WorkflowError('owner message must be observed in exact executing fixed chat')
        if request.get('executor_binding') != {k: binding.get(k) for k in ('task_id','title','project_id','cwd')}:
            raise w.WorkflowError('owner intake executor identity mismatch')
        value = {'schema_version': 1, 'task_id': task, 'executor_role': role,
            'executor_binding': request['executor_binding'], 'authorized_scope': scope,
            'human_message': human, 'source_mode': 'owner_direct',
            'external_authority_granted': False, 'headquarters_dispatch_synthesized': False,
            'chat_ack_synthesized': False, 'bridge_request': request.get('bridge_request'),
            'native_send': request.get('native_send')}
        path = path_for(root, task)
        if path.exists():
            old = w.read_json(path)
            # Re-observing a message cannot replace an existing authorized task.
            a=json.loads(json.dumps(old));b=json.loads(json.dumps(value))
            for row in (a,b):row['human_message'].pop('observed_at',None)
            if a != b:raise w.WorkflowError('owner task exists with different binding; preserve original')
            return {'status':'already_registered','intake':w.file_digest(root,str(path.relative_to(root)))}
        w.atomic_write_json(path, value)
        w.append_jsonl_locked(Path(root)/'logs/owner-direct-intake.jsonl', {
            'task_id':task,'intake':w.file_digest(root,str(path.relative_to(root))),
            'source_mode':'owner_direct','headquarters_dispatch_synthesized':False})
        return {'status':'owner_direct_registered','intake':w.file_digest(root,str(path.relative_to(root))),
                'dispatch_sent_created':False,'chat_ack_created':False}


def existing(root, task_id):
    path=path_for(root,task_id)
    if not path.exists():return None
    value=w.read_json(path)
    rows=[r for r in w.read_jsonl(Path(root)/'logs/owner-direct-intake.jsonl') if r.get('task_id')==task_id]
    if len(rows)!=1 or rows[0].get('intake')!=w.file_digest(root,str(path.relative_to(root))):
        raise w.WorkflowError('owner intake absent, ambiguous or changed from original recorded bytes')
    if value.get('task_id')!=task_id or value.get('source_mode')!='owner_direct':
        raise w.WorkflowError('invalid owner intake')
    return value


def verify_result(root, request, outbox, intake_record):
    binding=intake_record['executor_binding'];human=intake_record['human_message']
    reply=native_time(request.get('reply_observed_at'))
    authorized=native_time(human.get('authorized_at'))
    observed=native_time(human.get('observed_at'))
    now=dt.datetime.now(dt.timezone.utc)
    if (request.get('source_thread_id')!=binding['task_id'] or reply is None
            or authorized is None or observed is None
            or not authorized <= observed <= reply <= now
            or not 0 <= (now-reply).total_seconds() <= 300
            or request.get('authorized_scope')!=intake_record['authorized_scope']
            or not re.fullmatch('[a-f0-9]{64}',str(request.get('source_reply_sha256','')))
            or outbox.get('fixed_chat_task_id',outbox.get('chat_task_id'))!=binding['task_id']
            or outbox.get('chat_reply',{}).get('nonempty') is not True
            or outbox.get('chat_reply',{}).get('in_current_fixed_department_chat') is not True
            or outbox.get('owner_authorization_message_id')!=human['message_id']):
        raise w.WorkflowError('owner-direct result requires actual fixed reply and original authorization link')
    return w.file_digest(root, str(path_for(root, request['task_id']).relative_to(root)))


def queued_origin(root, task_id, role, evidence=None):
    record=existing(root,task_id)
    if not record or record.get('executor_role')!=role:return None
    pin=w.file_digest(root,str(path_for(root,task_id).relative_to(root)))
    rows=[r for r in w._result_handoff_rows(root,task_id) if r.get('event')=='notification_queued'
          and r.get('source_mode')=='owner_direct' and r.get('sender_department')==role
          and r.get('owner_intake')==pin]
    matches=[]
    for row in rows:
        outbox=row.get('outbox')
        if not isinstance(outbox,dict) or w.file_digest(root,outbox.get('path',''))!=outbox:
            raise w.WorkflowError('owner result bytes changed')
        if evidence is None or outbox in evidence:matches.append(row)
    if len(matches)!=1:raise w.WorkflowError('one exact real owner-origin queued result required')
    return matches[0]


def prepare_review(root, task_id):
    """Attach actual owner delivery to its original professional QA workflow, no fake send/ACK."""
    with human_control.action_gate(root,task_id):
        record=existing(root,task_id)
        if not record:raise w.WorkflowError('owner intake required')
        role=record['executor_role'];queue=queued_origin(root,task_id,role)
        binding=record['executor_binding'];reviewer='qa'
        qa=w.department_registry(root).get(reviewer,{}).get('chat_binding',{})
        if not qa.get('task_id'):raise w.WorkflowError('fixed independent QA1 required')
        snapshot=w.read_json(w.snapshot_path(root,task_id))
        planned=[{'department':role,'chat_task_id':binding['task_id']},
                 {'department':reviewer,'chat_task_id':qa['task_id']}]
        if snapshot:
            current={r.get('department'):r.get('chat_task_id') for r in snapshot.get('departments',[])}
            if any(current.get(r['department'])!=r['chat_task_id'] for r in planned):
                raise w.WorkflowError('existing original workflow differs; preserve it')
        else:
            w.initialize_workflow(root,task_id=task_id,request='owner-origin exact authorized scope: '+record['authorized_scope'],
                plan_status='ready_to_send',departments=planned,owner_approval_required=False)
        from argparse import Namespace
        result,_=w.record_receipt(root,Namespace(task_id=task_id,receipt_type='outbox_received',department=role,
            evidence=queue['outbox']['path'],idempotency_key='owner-result-'+queue['result_sha256'],
            chat_task_id='',ack_nonempty=False,verdict=''))
        return {'status':'original_owner_task_ready_for_independent_qa','receipt':result,
            'reviewer_department':reviewer,'dispatch_sent_created':False,'chat_ack_created':False}


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True)
    p.add_argument('--input',required=True);a=p.parse_args()
    print(json.dumps(intake(a.root,w.read_json(w.safe_path(a.root,a.input))),ensure_ascii=False))
