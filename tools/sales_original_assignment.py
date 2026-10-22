"""Restore only a real missing Sales source mapping; never replay transport or ACK."""
from pathlib import Path
import datetime as dt,json
import workflow_control as w
TASK='fc-20261010-assistant3-remaining-business-continuation-v2';ROLE='sales'
SCOPE='project:flashcast:assistant3:remaining-original-goals:v2'
SEND='ca19b47d-11a6-494f-84f0-7781d6fd5ac6';ACK='4bbf7847-d329-48c3-abfb-2e224b7e20d4'
ACTION='assistant3-sales-original-goal-actual-continuation-v3'
BASE='logs/handoffs/2026-10-10-goal-delivery-assistant-runtime-v1/operations-assistant3-business-next-v2/assistant3-continuation'
PAYLOAD={'path':BASE+'/event-followthrough/sales-actual-continuation-v3/exact-message.md','sha256':'80a531b5d88bb623bcbb9b5b26d3c565f9be022cbb9a2a7eb725f8a133e2229b','size':5817}
NATIVE_SEND={'path':BASE+'/event-followthrough/sales-actual-continuation-v3/actual-native-send-receipt.json','sha256':'8d65e39ad502f98f4810b8d497549daaeed2ee95131a02b25eebcc8c768de346','size':586}
ACK_SUMMARY={'path':BASE+'/sales-actual-continuation-v1/native-reply-proof.json','sha256':'e74096b29b0c472e75ed018351ef9b01e7c4d6a0f5ba891a2b0be316a1ef54d2','size':1124}


def _fail(message):raise w.WorkflowError('original Sales source: '+message)

def _pin(root,pin):
    if not isinstance(pin,dict)or w.file_digest(root,pin.get('path',''))!=pin:_fail('exact original evidence changed')
    return w.read_json(w.safe_path(root,pin['path']))


def validate(root,source):
    if (source.get('schema')!='restored-original-sales-assignment-source/v1'or source.get('task_id')!=TASK
            or source.get('department')!=ROLE or source.get('scope')!=SCOPE
            or source.get('dispatch_receipt_id')!=SEND or source.get('ack_receipt_id')!=ACK
            or source.get('payload')!=PAYLOAD or source.get('actual_original_send')!=NATIVE_SEND
            or source.get('original_ACK_summary')!=ACK_SUMMARY):_fail('one exact real sparse original source only')
    import department_rotation as rotation
    records=[x for x in rotation._records(root)if x['role']==ROLE]
    if len(records)!=1:_fail('trusted original same-role rotation required')
    record=records[0];old=record['old_binding'];current=w.department_registry(root)[ROLE]['chat_binding']
    if (old['task_id']!='example-native-285d606d62467104'or current['task_id']!=record['new_binding']['task_id']
            or old['project_id']!=current['project_id']or old['cwd']!=current['cwd']):_fail('same original role/project/cwd and current fixed identity required')
    rows,bad=w._validate_receipt_chain(root,TASK)
    if bad:_fail('intact full original receipt chain required')
    sent=[x for x in rows if x.get('receipt_id')==SEND];acks=[x for x in rows if x.get('receipt_id')==ACK]
    if len(sent)!=1 or len(acks)!=1:_fail('one actual original dispatch and nonempty ACK required')
    sent,ack=sent[0],acks[0]
    if (sent.get('receipt_hash')!=source.get('dispatch_receipt_hash')or ack.get('receipt_hash')!=source.get('ack_receipt_hash')
            or sent.get('receipt_type')!='dispatch_sent'or ack.get('receipt_type')!='chat_ack'
            or any(x.get('department')!=ROLE or x.get('chat_task_id')!=old['task_id']for x in [sent,ack])
            or ack.get('ack_nonempty')is not True or sent.get('action_id')!=ACTION or sent.get('scope')!=SCOPE
            or rows.index(sent)>=rows.index(ack)or sent.get('evidence')!=[PAYLOAD,NATIVE_SEND]
            or ack.get('evidence')!=[ACK_SUMMARY]or any(x.get('supersedes_receipt_id')in {SEND,ACK}for x in rows)):
        _fail('original exact sparse dispatch/ACK identities/hashes/order required')
    _pin(root,source['goal_contract']);snapshot=w.read_json(w.snapshot_path(root,TASK))
    if snapshot.get('goal_contract')!=source['goal_contract']or ROLE not in snapshot.get('goal_delivery',{}).get('producer_departments',[])or SCOPE not in snapshot['goal_delivery']['authorized_scope']:
        _fail('original task contract/producer/scope required')
    if w.file_digest(root,PAYLOAD['path'])!=PAYLOAD:_fail('original dispatched bytes changed')
    effect=_pin(root,NATIVE_SEND)
    if (effect.get('source_tool')!='mcp__codex_app__send_message_to_thread'or effect.get('actual_sent')is not True
            or effect.get('payload')!=PAYLOAD or effect.get('result')!={'content':[{'type':'text','text':'{"threadId":"'+old['task_id']+'"}'}],'isError':False}):
        _fail('original recorded actual native transport effect required')
    policy=[x for x in w.read_jsonl(Path(root)/w.POLICY_DECISIONS)if x.get('decision_id')==sent['policy_decision_id']]
    expected={'status':'allow','routing_status':'routing_allowed','task_id':TASK,'department':'operations-assistant-3',
        'target_department':ROLE,'target_thread_id':old['task_id'],'target_thread_title':old['title'],
        'target_cwd':old['cwd'],'target_project_id':old['project_id'],'source_project_id':old['project_id'],
        'action_id':ACTION,'action_class':'thread_message','scope':SCOPE,'payload_sha256':PAYLOAD['sha256']}
    if len(policy)!=1 or any(policy[0].get(k)!=v for k,v in expected.items()):_fail('real existing original allowed exact sender/action policy required')
    summary=_pin(root,ACK_SUMMARY)
    from goal_delivery_runtime import _collaboration_native
    native=_collaboration_native(root,source.get('actual_original_ACK_native'))
    if any(native.get('thread',{}).get(k)!=old.get(v)for k,v in {'id':'task_id','title':'title','cwd':'cwd'}.items()):_fail('real original fixed Sales native identity required')
    messages=[(t,m)for t in native.get('turns',[])if t.get('id')==summary['source_turn_id']for m in t.get('items',[])if m.get('id')==summary['source_reply_ref']and m.get('type')=='agentMessage']
    if len(messages)!=1:_fail('one real original nonempty Sales report/ACK required')
    turn,message=messages[0];raw=message.get('text','').encode('utf-8')
    if (turn.get('status')!='completed'or turn.get('error')or not raw.strip()
            or w.hashlib.sha256(raw).hexdigest()!=summary.get('reply_sha256_utf8')or len(raw)!=summary.get('reply_bytes_utf8')):
        _fail('actual original nonempty ACK/report exact UTF8 required')
    stamps=[w._parse_observed_at(x)for x in [policy[0]['checked_at'],sent['created_at'],summary['reply_observed_at_utc'],ack['created_at']]]
    if any(x is None for x in stamps)or stamps!=sorted(stamps)or stamps[-1]>dt.datetime.now(dt.timezone.utc):_fail('original actual policy/send/observed reply/ACK chronology required')
    return snapshot,sent


def recorded_entries(root,task,role):
    if task!=TASK or role!=ROLE:return []
    entries=[x['details']['restored_original_sales_READY_source']for x in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS)
             if x.get('task_id')==TASK and x.get('details',{}).get('restored_original_sales_READY_source')]
    if not entries:return []
    unique={x['path']:x for x in entries}
    if len(unique)!=1 or len(entries)!=1:_fail('one append-only restored source mapping required')
    pin=next(iter(unique.values()));validate(root,_pin(root,pin))
    return [{'task_id':TASK,'department':ROLE,'pin':pin}]


def record(root,input_path):
    pin=w.file_digest(root,input_path);source=_pin(root,pin);validate(root,source)
    with w.workflow_lock(root):
        existing=recorded_entries(root,TASK,ROLE)
        if existing:
            if existing[0]['pin']!=pin:_fail('original restored source cannot be replaced')
            return {'result':'duplicate_ignored','source':pin,'transport_or_ACK_replayed':False}
        snapshot=w.read_json(w.snapshot_path(root,TASK));w.append_workflow_event(root,TASK,snapshot['current_state'],
            {'restored_original_sales_READY_source':pin,'source_recovery_executor':'system-development','dispatch_fabricated':False,'ACK_fabricated':False,'external_permission_issued':False})
        snapshot['updated_at']=w.utc_timestamp();snapshot['event_count']=sum(x.get('task_id')==TASK for x in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS));w.atomic_write_json(w.snapshot_path(root,TASK),snapshot)
    return {'result':'recorded','source':pin,'transport_or_ACK_replayed':False,'historical_rotation_files_rewritten':False}
