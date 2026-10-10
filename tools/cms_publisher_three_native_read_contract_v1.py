"""Three frozen native editor projections. Read-only admission; no network or writes."""
from pathlib import Path
import workflow_control as w
import original_task_publisher_handover as handover
ROOT=Path('<PROJECT_ROOT>')
TASK='fc-20260928-keyword-page-answer-implementation-v1'
PUBLISHER='<LOCAL_TASK_ID>'
QA='<LOCAL_TASK_ID>'
PROJECT='<LOCAL_PROJECT_ID>'
QA_TASK='fc-20261007-publisher-three-native-read-control-qa-v1'
QA_ACTION='qa-publisher-three-native-read-control-v1'
QA_SCOPE='project:publisher-three:exact-native-source-read-control:v1:R0:20261007'
CV='publisher-three-native-read-control-v1-20261007'
OUTBOX_PREFIX='logs/department-outbox/'
CONTROL_PATH='drafts/operations/fc-20261007-owner-publisher-execution-takeover-v1/native-three-read-control-v1/candidate.json'
REQUESTS = []
MANIFEST = {}
PACKET = {}
EXPECTED_REQUESTS = {}


def require(ok,reason):
    if not ok:raise ValueError(reason)


def pinned(root,value):
    require(isinstance(value,dict) and set(value)=={'path','sha256','size'},'native_three_exact_pin_required')
    require(w.file_digest(root,value['path'])==value,'native_three_current_bytes_pin_required')
    return w.read_json(w.safe_path(root,value['path']))


def validate_request(request,item):
    expected=EXPECTED_REQUESTS[item]
    require(isinstance(request,dict) and set(request)==set(expected) and request==expected,
            'native_three_complete_frozen_request_shape_required')
    flags=[k for k,v in expected.items() if type(v) is bool]
    require(all(type(request[k]) is bool and request[k] is expected[k] for k in flags)
            and type(request['lookup']['require_exactly_one_row']) is bool,
            'native_three_exact_boolean_flags_required')


def current_handover(root,request,item):
    manifest=pinned(root,MANIFEST);entry=next(e for e in manifest['entries'] if e['item']==item)
    require(request['projection_fields']==entry['baseline_projection_fields']
        and request['candidate_sha256']==entry['publisher_candidate']['sha256']
        and request['candidate_version']==entry['candidate_version']
        and all(request[k]==entry[k] for k in ['table','record_id','slug']),
        'native_three_manifest_target_projection_required')
    pinned(root,entry['publisher_candidate']);pinned(root,PACKET)
    rows,invalid=w._validate_receipt_chain(root,TASK)
    require(not invalid and not w.validate_workflow_events(root,TASK),'native_three_original_chain_invalid')
    bound=handover.binding(root,TASK,rows)
    target=(bound or {}).get('targets',{}).get(entry['candidate_version'])
    require(target and all(target.get(k)==entry[k] for k in ['task_id','action_id','scope','table','record_id','slug','candidate_version'])
        and target.get('candidate')==(entry['publisher_candidate']['path'],entry['publisher_candidate']['sha256']),
        'native_three_installed_exact_execution_only_handover_required')
    # Reuse the installed verifier: owner proof, old-history prefix, and native ACK evidence.
    stages=handover._sequence(root,bound,target,rows)
    require(len(stages)>=2,'native_three_current_exact_publisher_dispatch_ACK_required')



def independent_QA(root,control_pin):
    control=pinned(root,control_pin)
    require(control_pin['path']==CONTROL_PATH and control.get('task_id')==QA_TASK
        and control.get('candidate_version')==CV and control.get('department')=='operations-assistant'
        and control.get('risk_level')=='R0' and control.get('production_write_allowed') is False
        and control.get('requests')==[x['request'] for x in REQUESTS],
        'native_three_exact_new_control_candidate_required')
    rows,invalid=w._validate_receipt_chain(root,QA_TASK)
    require(not invalid and not w.validate_workflow_events(root,QA_TASK),'native_three_control_QA_chain_invalid')
    verdicts=[r for r in rows if r.get('receipt_type')=='qa_verdict' and r.get('department')=='qa']
    require(verdicts,'native_three_new_independent_QA_missing');latest=verdicts[-1]
    expected={'task_id':QA_TASK,'department':'qa','chat_task_id':QA,'receipt_type':'qa_verdict',
       'action_id':QA_ACTION,'action_class':'internal_control_candidate','scope':QA_SCOPE,'verdict':'pass'}
    require(all(latest.get(k)==v for k,v in expected.items()),'native_three_exact_canonical_QA_pass_required')
    before=rows[:rows.index(latest)]
    sends=[(i,r) for i,r in enumerate(before) if all(r.get(k)==v for k,v in {
       'receipt_type':'dispatch_sent','department':'qa','chat_task_id':QA,'task_id':QA_TASK,
       'action_id':QA_ACTION,'action_class':'internal_control_candidate','scope':QA_SCOPE}.items())]
    require(sends,'native_three_control_QA_native_dispatch_required');i,sent=sends[-1]
    acks=[(j,r) for j,r in enumerate(before) if j>i and r.get('receipt_type')=='chat_ack'
       and r.get('department')=='qa' and r.get('chat_task_id')==QA and r.get('ack_nonempty') is True]
    require(acks,'native_three_control_QA_nonempty_ACK_required')
    for j,received in enumerate(before):
        if j<=acks[-1][0] or received.get('receipt_type')!='outbox_received' or received.get('department')!='qa':continue
        require(received.get('task_id')==QA_TASK and received.get('chat_task_id') in {'',QA},
            'native_three_current_QA_received_identity_required')
        for p in received.get('evidence',[]):
            if p not in latest.get('evidence',[]) or not str(p.get('path','')).startswith(OUTBOX_PREFIX):continue
            box=pinned(root,p)  # Same current JSON digest, not merely a historical path or latest PASS.
            w.validate_outbox(root,[p],'qa',QA_TASK)
            require(all(box.get(k)==v for k,v in {'task_id':QA_TASK,'department':'qa','fixed_chat_task_id':QA,
                'status':'completed','action_id':QA_ACTION,'action_class':'internal_control_candidate','scope':QA_SCOPE,
                'candidate_version':CV,'candidate_sha256':control_pin['sha256'],'candidate_path':CONTROL_PATH,
                'qa_verdict':'pass','risk_level':'R0','production_write_allowed':False,
                'production_release_eligible':False}.items()) and box.get('verdict',box.get('qa_verdict'))=='pass',
                'native_three_same_current_QA_JSON_contract_required')
            reply=box.get('chat_reply',{})
            require(reply.get('thread_id')==QA and reply.get('nonempty') is True
                and reply.get('reported_before_outbox') is True,'native_three_real_report_before_outbox_required')
            require(control_pin in box.get('evidence',[]) and all(x['request'] in box.get('evidence',[]) for x in REQUESTS),
                'native_three_all_requests_and_exact_candidate_in_QA_required')
            return
    raise ValueError('native_three_current_same_outbox_received_and_PASS_pin_required')


def policy_reasons(root,policy,task_id,action_id,scope,department,payload_sha256):
    raise ValueError("public_template_has_no_native_authorization")
    try:
        require(Path(root).resolve()==ROOT,'native_three_fixed_project_required')
        matches=[x for x in REQUESTS if x['action_id']==action_id and x['scope']==scope]
        require(task_id==TASK and department=='publishing' and len(matches)==1,'native_three_exact_read_tuple_required')
        entry=matches[0];request=pinned(root,entry['request']);validate_request(request,entry['item'])
        exact={'task_id':TASK,'action_id':action_id,'scope':scope,'department':'publishing',
               'request_path':entry['request']['path'],'request_sha256':entry['request']['sha256']}
        bindings=[b for b in policy.get('exact_requests',[]) if isinstance(b,dict)
            and all(b.get(k)==v for k,v in exact.items())]
        require(len(bindings)==1 and set(bindings[0])==set(exact)|{'control_candidate'},'native_three_exact_policy_binding_required')
        require(payload_sha256==entry['request']['sha256'],'native_three_exact_payload_required')
        registry=w.department_registry(root);binding=registry['publishing']['chat_binding']
        require(all(binding.get(k)==v for k,v in {'task_id':PUBLISHER,'project_id':PROJECT,'cwd':str(ROOT),
             'status':'bound_and_visible','reply_health':'healthy_visible_reply_verified','dispatch_eligible':True}.items())
             and w._chat_binding_healthy(binding,verification_ttl_hours=26),'native_three_fixed_healthy_publisher_required')
        require(registry['qa']['chat_binding'].get('task_id')==QA,'native_three_fixed_independent_QA_required')
        current_handover(root,request,entry['item'])
        independent_QA(root,bindings[0]['control_candidate'])
        return []
    except (ValueError,OSError,KeyError,TypeError,AttributeError,w.WorkflowError) as error:
        return [str(error)]
