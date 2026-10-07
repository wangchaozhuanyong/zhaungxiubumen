"""Two literal native R0 review contracts; no route or production permission."""
from pathlib import Path
import hashlib
import re
import importlib.util
import workflow_control as w

BASE='drafts/operations/fc-20261007-owner-publisher-execution-takeover-v1/'
CONTRACT='publisher-three-successor-v2-and-handover-v4'
QA='<LOCAL_TASK_ID>'
TASK='fc-20261007-publisher-three-execution-admission-qa-v2'
CV='publisher-three-execution-admission-control-v2-20261007'
ACTION='qa-publisher-three-execution-admission-v2'
SCOPE='project:publisher-three:execution-admission-control:v2'
V4TASK='fc-20261007-publisher-original-task-execution-only-handover-control-v4'
REVIEW={'path':BASE+'fixed-QA-v2/candidate.json','sha256':'a7571e4bcca2eebac23a71c6b3a6272634de259a581ab48e060b302887b459bb','size':21805}
V4={'path':BASE+'original-task-publisher-handover-control-v4/candidate.json','sha256':'bd76e1e44a5aedd7d98ca81da2693de51ee30d8b22125be866b9868a04178cd7','size':5594}
V4HELPER={'path':BASE+'original-task-publisher-handover-control-v4/candidate-original_task_publisher_handover.py','sha256':'486008dc4c291d86c91b1baa4934481a97da36b3db1ee5eb753fd250a4ad3598','size':26476}
ADMISSION={'path':BASE+'publisher-production-readiness-control-v2-20261007/candidate-publisher_native_sparse_admission.py','sha256':'84b797a2bb1cc7196eac8b3478f0ed26546c65ef145c3fd1688052fd88425de3','size':32588}


def require(value,reason):
    if not value:raise ValueError(reason)


def pin(root,pin):
    require(isinstance(pin,dict) and set(pin)=={'path','sha256','size'},'successor_exact_pin_required')
    require(w.file_digest(root,pin['path'])==pin,'successor_evidence_pin_changed')
    return w.read_json(w.safe_path(root,pin['path']))


def load_frozen(root,pin,name):
    require(w.file_digest(root,pin['path'])==pin,'successor_frozen_verifier_changed')
    spec=importlib.util.spec_from_file_location(name,w.safe_path(root,pin['path']))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def native_review(root,accepted,validate_receipt_chain):
    require(accepted.get('qa_contract')==CONTRACT and accepted.get('candidate_path')==REVIEW['path']
        and accepted.get('candidate_sha256')==REVIEW['sha256'] and bool(re.fullmatch(r'[0-9a-f-]{36}',str(accepted.get('qa_receipt_id',''))))
        and accepted.get('production_authority_granted') is False,'exact_successor_contract_required')
    reviewed=pin(root,REVIEW)
    require(reviewed.get('task_id')==TASK and reviewed.get('candidate_version')==CV
        and reviewed.get('production_write_allowed') is False,'successor_review_identity_invalid')
    rows,invalid=validate_receipt_chain(root,TASK)
    require(not invalid and not w.validate_workflow_events(root,TASK),'successor_native_review_chain_invalid')
    verdicts=[r for r in rows if r.get('receipt_id')==accepted['qa_receipt_id']]
    require(len(verdicts)==1,'successor_exact_pass_receipt_missing');verdict=verdicts[0]
    expected={'task_id':TASK,'receipt_type':'qa_verdict','department':'qa','chat_task_id':QA,
        'action_id':ACTION,'action_class':'analysis','scope':SCOPE,'verdict':'pass'}
    require(all(verdict.get(k)==v for k,v in expected.items()),'successor_native_QA_contract_mismatch')
    outbox=w.file_digest(root,str(accepted.get('qa_outbox_path') or ''))
    require(outbox['sha256']==accepted.get('qa_outbox_sha256') and outbox in verdict.get('evidence',[]),
        'successor_native_QA_outbox_pin_required')
    box=pin(root,outbox)
    require(all(box.get(k)==v for k,v in {'task_id':TASK,'department':'qa','fixed_chat_task_id':QA,
        'candidate_version':CV,'candidate_sha256':REVIEW['sha256'],'status':'completed','qa_verdict':'pass',
        'qa_result':'PASS_FOR_OWNER_REVIEW','risk_level':'R0','production_release_eligible':False}.items()),
        'successor_owner_review_is_not_production_or_old_QA')
    before=rows[:rows.index(verdict)]
    sends=[(i,r) for i,r in enumerate(before) if r.get('receipt_type')=='dispatch_sent' and r.get('department')=='qa'
        and r.get('chat_task_id')==QA and r.get('task_id')==TASK and r.get('action_id')==ACTION
        and r.get('action_class')=='analysis' and r.get('scope')==SCOPE]
    require(sends,'successor_native_dispatch_missing');index,dispatch=sends[-1]
    acks=[(i,r) for i,r in enumerate(before) if i>index and r.get('receipt_type')=='chat_ack' and r.get('department')=='qa'
        and r.get('chat_task_id')==QA and r.get('ack_nonempty') is True]
    require(acks and any(i>acks[-1][0] and r.get('receipt_type')=='outbox_received' and r.get('department')=='qa'
        and r.get('chat_task_id') in {'',QA} and outbox in r.get('evidence',[]) for i,r in enumerate(before)),
        'successor_native_ACK_outbox_missing')
    stamps=[w._parse_observed_at(r.get('created_at')) for r in [dispatch,acks[-1][1],verdict]]
    require(all(stamps) and stamps==sorted(stamps),'successor_native_times_invalid')
    w.validate_outbox(root,[outbox],'qa',TASK)
    return reviewed,outbox


def headquarters(root,accepted,outbox):
    rows=w._result_handoff_rows(root,TASK)
    exact=[r for r in rows if r.get('task_id')==TASK and r.get('sender_department')=='qa'
        and r.get('candidate_version')==CV and r.get('result_sha256')==outbox['sha256'] and r.get('outbox')==outbox]
    def stage(key,event):
        values=[r for r in exact if r.get('record_id')==accepted.get(key) and r.get('event')==event]
        require(len(values)==1,'successor_actual_HQ_'+event+'_missing');return values[0]
    received=stage('controller_received_record_id','controller_received')
    decision=stage('controller_decision_record_id','controller_decision')
    require(received.get('intake_mode')=='queue' and any(r.get('event')=='notification_queued' for r in exact[:exact.index(received)])
        and rows.index(received)<rows.index(decision) and decision.get('decision')=='continue'
        and decision.get('next_owner') in {'operations','operations-assistant'} and bool(decision.get('next_action'))
        and (outbox in decision.get('evidence',[]) or REVIEW in decision.get('evidence',[])),
        'successor_exact_HQ_internal_continue_required')
    # sender_department is the original QA result source, not the HQ actor.
    # These IDs must come from the existing native HQ handoff API, never booleans.


def handover(root,accepted,validate_receipt_chain):
    approval=accepted.get('handover_control',{})
    require(set(approval)=={'request','control_candidate','control_qa_outbox','control_qa_receipt_id'}
        and approval.get('control_candidate')==V4 and bool(re.fullmatch(r'[0-9a-f-]{36}',str(approval.get('control_qa_receipt_id','')))),
        'successor_exact_V4_control_required')
    v4=pin(root,V4);require(approval.get('request')==v4.get('request'),'successor_V4_request_changed')
    reviewed=pin(root,REVIEW)
    require(V4 in reviewed.get('input_pins',[]),'successor_V4_not_in_frozen_51_inputs')
    helper=load_frozen(root,V4HELPER,'successor_readonly_V4_control_verifier')
    admission=load_frozen(root,ADMISSION,'successor_readonly_sparse_verifier')
    helper._workflow=lambda:w;helper._admission=lambda:admission
    helper.control_qa(root,approval)  # Missing exact V4 fields remain DENY.
    box=pin(root,approval['control_qa_outbox'])
    require(box.get('qa_result')=='PASS_FOR_OWNER_REVIEW' and box.get('qa_verdict')=='pass'
        and box.get('production_release_eligible') is False,'successor_V4_owner_review_only_required')
    rows,invalid=validate_receipt_chain(root,V4TASK)
    verdict=next((r for r in rows if r.get('receipt_id')==approval['control_qa_receipt_id']),{})
    require(not invalid and all(verdict.get(k)==v for k,v in {
        'task_id':V4TASK,'action_id':'qa-publisher-original-task-execution-only-handover-control-v4',
        'action_class':'internal_control_candidate','scope':'project:publisher-three:original-task-execution-only-handover:control-v4:R0:20261007'}.items()),
        'successor_V4_native_action_scope_required')


def validate(root,req,accepted,validate_receipt_chain):
    require(req.get('task_id')=='fc-20261007-publisher-three-designated-binding-v1'
        and req.get('sender_department')=='operations-assistant' and req.get('target_department')=='designated-website-developer',
        'successor_only_existing_assistant_developer_stage')
    reviewed,outbox=native_review(root,accepted,validate_receipt_chain)
    handover(root,accepted,validate_receipt_chain)
    headquarters(root,accepted,outbox)
    packet=w.read_json(w.safe_path(root,req['packet_path']))
    require(len(packet.get('input_pins',[]))==6 and len(packet.get('content_candidates',[]))==3
        and packet.get('targets')==reviewed.get('targets')
        and all(p in reviewed.get('input_pins',[]) for p in packet['input_pins'])
        and all(p in reviewed.get('content_candidates',[]) for p in packet['content_candidates']),
        'successor_three_targets_six_inputs_not_QA_reviewed')
    for p in packet['input_pins']:pin(root,p)
