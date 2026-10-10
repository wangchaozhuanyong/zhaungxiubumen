"""One original-task execution-only handover. This never grants production rights."""
from __future__ import annotations
import argparse
import copy
import datetime as dt
import hashlib
import json
from pathlib import Path

ROOT = Path('<PROJECT_ROOT>')
TASK = 'fc-20260928-keyword-page-answer-implementation-v1'
CONTROL_TASK = 'fc-20261007-publisher-original-task-execution-only-handover-control-v4'
CONTROL_VERSION = 'publisher-execution-only-handover-control-v4-20261007'
REQUEST_HASH = 'dc81d48c6eca15aaf34a7be9ed5db82cdb14fb35a2a5b680cbfceff9846cae57'
PROJECT = '<LOCAL_PROJECT_ID>'
PUBLISHER = '<LOCAL_TASK_ID>'
QA = '<LOCAL_TASK_ID>'
ASSISTANT = '<LOCAL_TASK_ID>'
ADMISSION = {'path': 'drafts/operations/fc-20261007-owner-publisher-execution-takeover-v1/publisher-production-readiness-control-v2-20261007/final-admission-manifest.json', 'sha256': 'd4cdeb41b19948f4bcec78e501593b456fdd462a1cd976635e7e03f454bbb213', 'size': 11805}
PUBLISHER_ROW = {'department': 'publishing', 'chat_task_id': PUBLISHER, 'execution_wave': 3,
                 'depends_on': ['qa'], 'participant_role': 'execution_only'}
POLICY_KEY = 'original_task_publisher_execution_only_handover'


def _workflow():
    if __package__:
        from . import workflow_control
    else:
        import workflow_control
    return workflow_control


def _admission():
    if __package__:
        from . import publisher_native_sparse_admission
    else:
        import publisher_native_sparse_admission
    return publisher_native_sparse_admission


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def pin(root, value):
    w = _workflow()
    require(isinstance(value, dict) and set(value) == {'path', 'sha256', 'size'}, 'exact local pin required')
    require(w.file_digest(root, value['path']) == value, 'frozen handover evidence changed')
    return w.read_json(w.safe_path(root, value['path']))


def check_root(root):
    require(Path(root).resolve() == ROOT.resolve(), 'fixed FLASH CAST project required')


def validate_request(root, request):
    check_root(root)
    require(set(request) == {'schema_version','task_id','request_hash','admission','original_departments',
                            'owner_authorization','requested_actor','requested_actor_thread',
                            'preserve_original_author','grant_production_write'}, 'exact handover request shape required')
    require(request['schema_version'] == 1 and request['task_id'] == TASK and request['request_hash'] == REQUEST_HASH
            and request['admission'] == ADMISSION and request['requested_actor'] == 'operations-assistant'
            and request['requested_actor_thread'] == ASSISTANT and request['preserve_original_author'] is True
            and request['grant_production_write'] is False, 'exact owner-delegated execution-only request required')
    m = _admission()
    index = m.pinned(root, m.SOURCE_INDEX_PIN)
    require(request['owner_authorization'] == index['owner_authorization'], 'native owner source changed')
    m.owner(root, request['owner_authorization'])
    targets = m.validate_manifest(root, pin(root, ADMISSION))
    original = request['original_departments']
    require(len(original) == 2 and [x['department'] for x in original] == ['content-organic-website','qa']
            and original[0]['chat_task_id'] == '<LOCAL_TASK_ID>'
            and original[1]['chat_task_id'] == QA, 'preserve exact original producer and QA participants')
    return targets


def control_qa(root, approval):
    """Actual independent R0 control QA, never a production QA substitute."""
    w = _workflow()
    request = pin(root, approval['request'])
    targets = validate_request(root, request)
    candidate = pin(root, approval['control_candidate'])
    require(candidate.get('task_id') == CONTROL_TASK and candidate.get('candidate_version') == CONTROL_VERSION
            and candidate.get('department') == 'operations-assistant'
            and candidate.get('request') == approval['request'], 'QA must bind this exact new control candidate')
    outbox = pin(root, approval['control_qa_outbox'])
    require(outbox.get('task_id') == CONTROL_TASK and outbox.get('department') == 'qa'
            and outbox.get('fixed_chat_task_id') == QA and outbox.get('status') == 'completed'
            and outbox.get('verdict',outbox.get('qa_verdict')) == 'pass' and outbox.get('risk_level') == 'R0'
            and outbox.get('review_scope') == 'exact_original_task_execution_only_handover_control'
            and outbox.get('candidate_version') == CONTROL_VERSION
            and outbox.get('candidate_sha256') == approval['control_candidate']['sha256']
            and outbox.get('handover_request_sha256') == approval['request']['sha256']
            and outbox.get('production_write_allowed') is False
            and outbox.get('chat_reply',{}).get('nonempty') is True
            and outbox.get('chat_reply',{}).get('reported_before_outbox') is True,
            'actual independent exact R0 control QA outbox required')
    rows, invalid = w._validate_receipt_chain(root, CONTROL_TASK)
    require(not invalid and not w.validate_workflow_events(root,CONTROL_TASK), 'control QA chains invalid')
    verdict = next((x for x in rows if x['receipt_id'] == approval['control_qa_receipt_id']),{})
    require(verdict.get('receipt_type') == 'qa_verdict' and verdict.get('department') == 'qa'
            and verdict.get('chat_task_id') == QA and verdict.get('verdict') == 'pass'
            and approval['control_qa_outbox'] in verdict.get('evidence',[]), 'actual precise control QA receipt required')
    before = rows[:rows.index(verdict)]
    dispatches = [(i,x) for i,x in enumerate(before) if x.get('department')=='qa' and x.get('receipt_type')=='dispatch_sent']
    require(dispatches, 'control QA native dispatch missing')
    i,dispatch = dispatches[-1]
    acks = [(j,x) for j,x in enumerate(before) if j>i and x.get('department')=='qa'
            and x.get('receipt_type')=='chat_ack' and x.get('chat_task_id')==QA and x.get('ack_nonempty') is True]
    require(acks and any(j>acks[-1][0] and x.get('receipt_type')=='outbox_received'
                        and x.get('department')=='qa' and approval['control_qa_outbox'] in x.get('evidence',[])
                        for j,x in enumerate(before)), 'control QA native ACK/outbox chain missing')
    return request, targets


def live_adopter(root, proof_pin, stamp):
    w = _workflow(); proof = pin(root,proof_pin)
    observed = dt.datetime.fromisoformat(proof['observed_at'].replace('Z','+00:00'))
    now = dt.datetime.fromisoformat(stamp.replace('Z','+00:00'))
    require(proof.get('source_method')=='mcp__codex_app__list_threads' and dt.timedelta()<=now-observed<=dt.timedelta(minutes=5),
            'fresh native five-minute adoption identity required')
    registry = w.department_registry(root)
    for department,thread in [('operations-assistant',ASSISTANT),('publishing',PUBLISHER)]:
        binding = registry[department]['chat_binding']
        matching = [x for x in proof['threads'] if x.get('id')==thread]
        require(len(matching)==1 and all(matching[0].get(k)==v for k,v in {
            'projectId':PROJECT,'cwd':str(ROOT),'title':binding['title']}.items())
            and (department!='publishing' or matching[0].get('status')=='idle')
            and w._chat_binding_healthy(binding,verification_ttl_hours=26,now=now), 'exact healthy native adopter/publisher required')
        sections = [x for x in proof['sections'] if thread in x.get('threadIds',[])]
        require(len(sections)==1 and sections[0].get('name')=='装修公司部门'
                and sections[0].get('id')==binding['sidebar_section_id'], 'unique exact department section required')


def validate_event(root,event,receipts):
    w = _workflow(); details = event.get('details',{})
    if not details.get('publisher_execution_handover'):
        return None
    require(event.get('task_id')==TASK and event.get('state')=='qa_blocked'
            and event.get('event_hash')==w.sha256_value({k:v for k,v in event.items() if k!='event_hash'}), 'invalid handover event')
    approval = details['approval']
    require(approval.get('status')=='reviewed_exact_execution_only_handover'
            and approval.get('production_authority_granted') is False, 'handover has no production authority')
    request,targets = control_qa(root,approval)
    pin(root,approval['adoption_live_identity'])
    require(details.get('request_hash')==REQUEST_HASH and details.get('publisher_row')==PUBLISHER_ROW
            and details.get('original_departments')==request['original_departments']
            and details.get('adopted_by')=='operations-assistant' and details.get('adopted_by_thread')==ASSISTANT
            and details.get('production_authority_granted') is False, 'handover participant boundary changed')
    count = details['receipt_prefix_count']
    require(type(count) is int and count>0 and len(receipts)>=count
            and receipts[count-1].get('receipt_hash')==details['receipt_tip'], 'handover historical receipt prefix changed')
    require(w.sha256_value(receipts[:count])==details['receipt_prefix_sha256'], 'handover history rewritten')
    raw_prefix=b''.join(w.receipts_path(root,TASK).read_bytes().splitlines(keepends=True)[:count])
    require(hashlib.sha256(raw_prefix).hexdigest()==details['receipt_prefix_bytes_sha256'], 'historical receipt prefix bytes changed')
    return {'event':event,'request':request,'targets':targets,'receipt_start':count}


def binding(root, task_id, receipts=None):
    if task_id!=TASK: return None
    w = _workflow()
    events = w.read_jsonl(root/w.WORKFLOW_EVENTS)
    handovers = [x for x in events if x.get('task_id')==TASK and x.get('details',{}).get('publisher_execution_handover')]
    require(len(handovers)<=1, 'duplicate original-task handover events')
    if not handovers: return None
    return validate_event(root,handovers[0],receipts if receipts is not None else w.read_jsonl(w.receipts_path(root,TASK)))


def replay(root,snapshot,events=None):
    b = binding(root,snapshot.get('task_id'))
    if b is None: return
    require(snapshot.get('request_hash')==REQUEST_HASH and snapshot.get('owner_approval_required') is False,
            'handover replay request or owner-approval flag changed')
    original = b['request']['original_departments']
    require(snapshot.get('departments') in [original,original+[PUBLISHER_ROW]], 'handover replay cannot replace original participants')
    snapshot['departments']=copy.deepcopy(original+[PUBLISHER_ROW])
    snapshot['publisher_execution_only_event_hash']=b['event']['event_hash']


def _entry(b,receipt):
    return next((t for t in b['targets'].values() if receipt.get('action_id')==t['action_id'] and receipt.get('scope')==t['scope']),None)


def legacy_context(root,snapshot,receipts):
    b = binding(root,snapshot.get('task_id'),receipts)
    if b is None: return snapshot,receipts
    result = copy.deepcopy(snapshot); result['departments']=copy.deepcopy(b['request']['original_departments'])
    return result,[x for i,x in enumerate(receipts) if i<b['receipt_start'] or
                   not (x.get('department')=='publishing' or _entry(b,x) is not None and x.get('department')=='qa')]


def _sequence(root,b,entry,receipts):
    rows = [(i,x) for i,x in enumerate(receipts) if i>=b['receipt_start'] and _entry(b,x)==entry]
    for _,row in rows:
        for evidence in row.get('evidence',[]): pin(root,evidence)
    stages = []
    index = -1
    for department,kind in [('publishing','dispatch_sent'),('publishing','chat_ack'),('publishing','outbox_received'),
                            ('qa','dispatch_sent'),('qa','chat_ack'),('qa','outbox_received'),('qa','qa_verdict'),
                            ('publishing','execution_result'),('publishing','postcheck')]:
        matches=[(i,x) for i,x in rows if i>index and x.get('department')==department and x.get('receipt_type')==kind]
        if kind=='dispatch_sent':
            failed=max([i for i,x in rows if x.get('department')==department and x.get('receipt_type')=='dispatch_failed'],default=-1)
            matches=[(i,x) for i,x in matches if i>failed]
        if not matches: break
        index,row=matches[-1]
        require(row.get('chat_task_id')==(QA if department=='qa' else PUBLISHER), 'exact native receipt thread required')
        if kind=='chat_ack':
            proofs=[pin(root,p) for p in row.get('evidence',[])]
            prior=stages[-1]
            require(row.get('ack_nonempty') is True and any(x.get('source_method')=='mcp__codex_app__read_thread'
                    and x.get('source_thread_id')==row['chat_task_id'] and x.get('task_id')==TASK
                    and x.get('action_id')==entry['action_id'] and x.get('scope')==entry['scope']
                    and x.get('dispatch_receipt_id')==prior['receipt_id'] and x.get('nonempty') is True
                    and bool(x.get('turn_id')) and bool(x.get('message_id')) and bool(x.get('reply_sha256'))
                    for x in proofs), 'fresh original-task native ACK proof required')
        if kind=='outbox_received' and department=='publishing':
            outboxes=[pin(root,p) for p in row.get('evidence',[])]
            require(any(x.get('task_id')==TASK and x.get('department')=='publishing'
                        and x.get('fixed_chat_task_id')==PUBLISHER and x.get('candidate_version')==entry['candidate_version']
                        and x.get('candidate_sha256')==entry['candidate'][1]
                        and x.get('action_id')==entry['action_id'] and x.get('scope')==entry['scope']
                        and x.get('chat_reply',{}).get('nonempty') is True for x in outboxes), 'exact publisher original-task outbox required')
        if kind=='qa_verdict':
            received = stages[-1].get('evidence',[]) if stages else []
            outbox_pins = [p for p in row.get('evidence',[])
                           if str(p.get('path','')).startswith('logs/department-outbox/') and p in received]
            require(outbox_pins, 'QA verdict must bind the current exact received QA JSON pin')
            outboxes = [pin(root,p) for p in outbox_pins]
            require(row.get('verdict') in {'pass','blocked'} and row.get('action_class')=='cms_content_candidate', 'exact QA verdict required')
            if row['verdict']=='pass':
                require(any(_admission().qa_outbox_matches(x,entry) for x in outboxes), 'exact fixed production QA candidate/owner required')
            else:
                require(any(all(x.get(k)==v for k,v in {'task_id':TASK,'department':'qa','fixed_chat_task_id':QA,
                    'candidate_version':entry['candidate_version'],'candidate_sha256':entry['candidate'][1],
                    'action_id':entry['action_id'],'scope':entry['scope'],'execution_thread_id':PUBLISHER}.items())
                    and x.get('verdict',x.get('qa_verdict'))=='blocked' for x in outboxes), 'exact blocked QA binding required')
        if kind in {'execution_result','postcheck'}: require(row.get('verdict') in {'pass','blocked'}, 'exact execution/postcheck outcome required')
        stages.append(row)
        if kind in {'qa_verdict','execution_result','postcheck'} and row.get('verdict')=='blocked': break
    return stages


def validate_new_receipt(root,snapshot,receipts,receipt):
    b = binding(root,snapshot.get('task_id'),receipts)
    if b is None: return False
    entry=_entry(b,receipt)
    if receipt.get('department')=='publishing': require(entry is not None, 'publisher execution-only cannot touch sibling tuple')
    if entry is None: return False
    require(receipt.get('task_id')==TASK and receipt.get('department') in {'publishing','qa'}, 'exact original-task publisher/QA receipt required')
    if receipt.get('receipt_type')=='dispatch_failed':
        rows=[x for i,x in enumerate(receipts) if i>=b['receipt_start'] and _entry(b,x)==entry
              and x.get('department')==receipt['department']]
        require(rows and rows[-1].get('receipt_type')=='dispatch_sent'
                and receipt.get('supersedes_receipt_id')==rows[-1]['receipt_id']
                and receipt.get('chat_task_id')==rows[-1].get('chat_task_id')
                and bool(receipt.get('replacement_reason')), 'exact unacknowledged dispatch failure required')
        return True
    kinds=[('publishing','dispatch_sent'),('publishing','chat_ack'),('publishing','outbox_received'),('qa','dispatch_sent'),
           ('qa','chat_ack'),('qa','outbox_received'),('qa','qa_verdict'),('publishing','execution_result'),('publishing','postcheck')]
    pair=(receipt.get('department'),receipt.get('receipt_type'))
    require(pair in kinds, 'unsupported execution-only receipt kind')
    required=kinds.index(pair)
    stages=_sequence(root,b,entry,receipts)
    require(len(stages)>=required, 'current exact tuple native prerequisite missing')
    if required>=7: require(stages[6].get('verdict')=='pass', 'latest exact QA is blocked')
    if required>=8: require(stages[7].get('verdict')=='pass', 'latest exact execution is blocked')
    # Evaluate the incoming stage's semantics as well as its predecessors.
    trial=_sequence(root,b,entry,receipts+[receipt])
    require(len(trial)>=required+1, 'incoming exact execution stage invalid')
    if receipt.get('receipt_type')=='execution_result':
        prior=[x for i,x in enumerate(receipts) if i>=b['receipt_start'] and _entry(b,x)==entry and x.get('receipt_type')=='execution_result']
        if prior:
            require(prior[-1].get('verdict')=='blocked', 'completed exact publisher action cannot execute twice')
            w=_workflow()
            decisions=[x for x in w.read_jsonl(root/w.POLICY_DECISIONS) if x.get('decision_id')==receipt.get('policy_decision_id')]
            require(decisions and all(decisions[-1].get(k)==v for k,v in {
                'status':'allow','department':'publishing','task_id':TASK,'action_id':entry['action_id'],
                'action_class':'cms_write','scope':entry['scope'],'approval_basis':'blocked_execution_retry',
                'approval_status':'consumed','approval_id':prior[-1].get('approval_id'),
                'retry_source_receipt_id':prior[-1]['receipt_id']}.items()), 'exact consumed policy retry required')
    return True


def progress(root,task_id,action_id,scope):
    w=_workflow(); b=binding(root,task_id)
    if b is None: return None
    entry=_entry(b,{'action_id':action_id,'scope':scope})
    if entry is None: return None
    receipts,invalid=w._validate_receipt_chain(root,TASK)
    require(not invalid and not w.validate_workflow_events(root,TASK), 'exact handover production chains invalid')
    stages=_sequence(root,b,entry,receipts)
    return {'qa_passed':len(stages)>=7 and stages[6].get('verdict')=='pass',
            'executed':len(stages)>=8 and stages[7].get('verdict')=='pass',
            'verified':len(stages)>=9 and stages[8].get('verdict')=='pass',
            'qa_receipt_id':stages[6]['receipt_id'] if len(stages)>=7 else None,
            'candidate_version':entry['candidate_version'],'production_authority_granted':False}


def recoverable_dispatch(root,snapshot,receipts,sent):
    b=binding(root,snapshot.get('task_id'),receipts)
    if b is None or _entry(b,sent) is None or sent.get('department') not in {'publishing','qa'}: return False
    rows=[x for i,x in enumerate(receipts) if i>=b['receipt_start'] and _entry(b,x)==_entry(b,sent)
          and x.get('department')==sent['department']]
    return bool(rows and rows[-1].get('receipt_type')=='dispatch_failed'
                and rows[-1].get('supersedes_receipt_id')==sent.get('receipt_id'))


def retry_projection(root,task_id,action_id,scope,receipt_id,approval_id):
    b=binding(root,task_id)
    if b is None: return None
    entry=_entry(b,{'action_id':action_id,'scope':scope})
    if entry is None: return None
    w=_workflow();rows=w.read_jsonl(w.receipts_path(root,TASK))
    executions=[x for i,x in enumerate(rows) if i>=b['receipt_start'] and _entry(b,x)==entry and x.get('receipt_type')=='execution_result']
    if not executions or any(x.get('verdict')!='blocked' for x in executions): return None
    latest=executions[-1]
    stages=_sequence(root,b,entry,rows)
    if (latest.get('receipt_id')!=receipt_id or latest.get('approval_id')!=approval_id
            or latest.get('department')!='publishing' or latest.get('verdict')!='blocked'
            or len(stages)<7 or stages[6].get('verdict')!='pass'): return None
    return {'latest':latest,'executions':executions,'current_state':'blocked',
            'blockers':['execution_result_blocked'],'resume_from':'owner_approved'}


def dispatch_precheck(root,snapshot,department,thread,action_id,scope):
    if snapshot.get('task_id')!=TASK: return []
    b=binding(root,TASK)
    if department=='publishing':
        if b is None: return ['exact_publisher_handover_event_required']
        if thread!=PUBLISHER or _entry(b,{'action_id':action_id,'scope':scope}) is None:
            return ['publisher_execution_only_exact_three_tuple_required']
    elif department=='qa' and b is not None:
        entry=_entry(b,{'action_id':action_id,'scope':scope})
        if entry is not None and len(_sequence(root,b,entry,_workflow().read_jsonl(_workflow().receipts_path(root,TASK))))<3:
            return ['exact_publisher_native_handover_outbox_required_before_QA_dispatch']
    return []


def shadow_projection(root,task_id):
    b=binding(root,task_id)
    if b is None: return None
    w=_workflow()
    snapshot={'task_id':TASK,'request_hash':REQUEST_HASH,'owner_approval_required':False,
              'plan_status':'ready_to_send','departments':copy.deepcopy(b['request']['original_departments']),
              'current_state':'qa_blocked'}
    replay(root,snapshot)
    receipts,invalid=w._validate_receipt_chain(root,TASK)
    require(not invalid and not w.validate_workflow_events(root,TASK), 'shadow projection chains invalid')
    return {'status':'readonly_exact_execution_only_projection','task_id':TASK,
            'legacy_state':w._derive_state(root,snapshot,receipts)['state'],'departments':snapshot['departments'],
            'tuple_progress':{cv:progress(root,TASK,t['action_id'],t['scope']) for cv,t in b['targets'].items()},
            'production_authority_granted':False}


def apply(root, *, expected_snapshot_sha, expected_receipt_tip, expected_event_tip, mutate=False):
    check_root(root); w=_workflow()
    approval=w.load_policy(root).get(POLICY_KEY,{})
    require(approval.get('status')=='reviewed_exact_execution_only_handover'
            and approval.get('production_authority_granted') is False, 'exact reviewed adoption policy binding missing')
    request,targets=control_qa(root,approval)
    with w.workflow_lock(root):
        snapshot=w.read_json(w.snapshot_path(root,TASK)); receipts,invalid=w._validate_receipt_chain(root,TASK)
        events=w.read_jsonl(root/w.WORKFLOW_EVENTS)
        require(not invalid and not w.validate_workflow_events(root,TASK), 'original history chains invalid')
        old=binding(root,TASK,receipts)
        if old:
            require(old['event']['details']['approval']==approval, 'different handover already committed')
            replay(root,snapshot)
            if mutate: w.atomic_write_json(w.snapshot_path(root,TASK),snapshot)
            return {'status':'duplicate_ignored','production_authority_granted':False}
        require(snapshot.get('request_hash')==REQUEST_HASH and snapshot.get('current_state')=='qa_blocked'
                and snapshot.get('plan_status')=='ready_to_send' and snapshot.get('departments')==request['original_departments']
                and snapshot.get('owner_approval_required') is False, 'preserve nonterminal original blocked workflow required')
        require(hashlib.sha256(w.snapshot_path(root,TASK).read_bytes()).hexdigest()==expected_snapshot_sha
                and receipts[-1]['receipt_hash']==expected_receipt_tip
                and events[-1]['event_hash']==expected_event_tip, 'concurrent snapshot/receipt/event tip changed')
        live_adopter(root,approval['adoption_live_identity'],w.utc_timestamp())
        result={'status':'dry_run_validated','production_authority_granted':False,'targets':list(targets)}
        if not mutate: return result
        details={'publisher_execution_handover':True,'request_hash':REQUEST_HASH,'approval':approval,
                 'original_departments':request['original_departments'],'publisher_row':PUBLISHER_ROW,
                 'receipt_prefix_count':len(receipts),'receipt_tip':expected_receipt_tip,
                 'receipt_prefix_sha256':w.sha256_value(receipts),'before_snapshot_sha256':expected_snapshot_sha,
                 'receipt_prefix_bytes_sha256':hashlib.sha256(w.receipts_path(root,TASK).read_bytes()).hexdigest(),
                 'adopted_by':'operations-assistant','adopted_by_thread':ASSISTANT,'production_authority_granted':False}
        event=w.append_workflow_event(root,TASK,snapshot['current_state'],details)
        replay(root,snapshot); snapshot['updated_at']=w.utc_timestamp()
        snapshot['event_count']=sum(x.get('task_id')==TASK for x in w.read_jsonl(root/w.WORKFLOW_EVENTS))
        w.atomic_write_json(w.snapshot_path(root,TASK),snapshot)
        return {**result,'status':'execution_only_handover_recorded','event_hash':event['event_hash']}


def main():
    import sys
    sys.path.insert(0,str(ROOT/'tools'))
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply',action='store_true')
    parser.add_argument('--expected-snapshot-sha',required=True)
    parser.add_argument('--expected-receipt-tip',required=True)
    parser.add_argument('--expected-event-tip',required=True)
    args=parser.parse_args()
    try: result=apply(ROOT,expected_snapshot_sha=args.expected_snapshot_sha,expected_receipt_tip=args.expected_receipt_tip,
                      expected_event_tip=args.expected_event_tip,mutate=args.apply)
    except (ValueError,KeyError,OSError,ImportError) as error: result={'status':'DENY','reason':str(error),'production_authority_granted':False}
    print(json.dumps(result,ensure_ascii=False))
    return 0 if result['status']!='DENY' else 1


if __name__=='__main__': raise SystemExit(main())
