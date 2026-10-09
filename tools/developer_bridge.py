"""Human-designated single developer bridge. Candidate review is not routing activation."""
from pathlib import Path
import datetime as dt
import native_inventory
import workflow_control as w

DEVELOPER = {'target_project_id':'<LOCAL_PROJECT_ID>',
    'target_thread_id':'<LOCAL_TASK_ID>',
    'target_thread_title':'FLASH CAST｜专用开发部｜网站与部门系统','target_cwd':'<WEBSITE_PROJECT_ROOT>'}


def review_candidate(root, request_pin, live, policy=None):
    """Read-only control review; does not require prior QA, activation or actual send."""
    policy=policy or w.load_policy(root)
    if not isinstance(request_pin,dict) or w.file_digest(root,request_pin.get('path',''))!=request_pin:
        raise w.WorkflowError('frozen exact developer request required')
    request=w.read_json(w.safe_path(root,request_pin['path']))
    routing=policy['routing_policy']
    if (any(request.get(k)!=v for k,v in DEVELOPER.items())
            or request.get('source_project_id')!=routing.get('source_project_id')
            or str(Path(routing.get('source_project_root','')).resolve())!=str(Path(root).resolve())
            or request.get('sender_department') not in {'operations','operations-assistant-2'}
            or not str(request.get('scope','')).startswith('owner_project_handoff:')
            or request.get('production_authority_granted') is not False):
        raise w.WorkflowError('only exact human-designated developer project/chat/scope allowed')
    authority=w.file_digest(root,str(request.get('owner_authorization_ref','')))
    if authority['sha256']!=request.get('owner_authorization_sha256'):
        raise w.WorkflowError('exact human authorization reference required')
    auth=w.read_json(w.safe_path(root,authority['path']))
    if auth.get('source') not in {'current_human_message','human_user_message'}:
        raise w.WorkflowError('agent delegation alone is not human authorization')
    code_root=request.get('code_source_root')
    if code_root is None and auth.get('original_software_task_id')=='fc-20261008-department-system-upgrade-v1':
        code_root='<PROJECT_ROOT>'
    native_inventory.validate_code_source(code_root,legacy_website_only=False)
    packet=w.file_digest(root,str(request.get('packet_path','')))
    if packet['sha256']!=request.get('packet_sha256') or packet['sha256']!=request.get('payload_sha256'):
        raise w.WorkflowError('frozen developer payload bytes required')
    stamp=w._parse_observed_at(live.get('observed_at'));now=dt.datetime.now(dt.timezone.utc)
    rows=native_inventory.threads(live)
    target=[row for row in rows if row.get('id')==DEVELOPER['target_thread_id']]
    member='codex:project:'+DEVELOPER['target_project_id']
    groups=[group for group in native_inventory.sections(live) if member in group.get('itemKeys',[])]
    if (stamp is None or not 0<=(now-stamp).total_seconds()<=300 or len(target)!=1 or len(groups)!=1
            or groups[0].get('sectionId',groups[0].get('id'))!=request.get('target_sidebar_section_id')
            or any(target[0].get(k)!=v for k,v in {'projectId':DEVELOPER['target_project_id'],
                'title':DEVELOPER['target_thread_title'],'cwd':DEVELOPER['target_cwd']}.items())):
        raise w.WorkflowError('fresh actual group and exact developer identity required')
    source=w.department_registry(root).get(request['sender_department'],{}).get('chat_binding',{})
    sources=[row for row in rows if row.get('id')==source.get('task_id')]
    if len(sources)!=1 or any(sources[0].get(k)!=v for k,v in {
        'projectId':source.get('project_id'),'title':source.get('title'),'cwd':str(Path(root).resolve())}.items()):
        raise w.WorkflowError('fresh fixed actual sender required')
    return {'read_only':True,'qa_review_eligible':True,'request':request,'request_pin':request_pin,
            'authority':authority,'packet':packet,'target_status':target[0].get('status'),
            'code_source_root':code_root,'activated':False,'sent':False,'production_authority_granted':False}


def precheck(root, requested, policy=None):
    policy=policy or w.load_policy(root)
    try:
        exact=policy['routing_policy'].get('owner_directed_code_handoff',{})
        request_pin=w.file_digest(root,str(exact.get('request_path','')))
        if exact.get('status')!='approved_single_use' or request_pin['sha256']!=exact.get('request_sha256'):
            raise w.WorkflowError('exact request activation required after independent control QA')
        request=w.read_json(w.safe_path(root,request_pin['path']))
        fields={k:v for k,v in requested.items() if k!='action_class'}
        if requested.get('action_class')!='thread_message' or any(request.get(k)!=v for k,v in fields.items()):
            raise w.WorkflowError('frozen developer request differs from actual route')
        live=w.read_json(w.safe_path(root,str(request.get('live_identity_path',''))))
        review=review_candidate(root,request_pin,live,policy)
        if review['target_status']!='idle':raise w.WorkflowError('active developer stays queued')
        acceptance=w.file_digest(root,str(exact.get('control_acceptance_path','')))
        if acceptance['sha256']!=exact.get('control_acceptance_sha256'):
            raise w.WorkflowError('frozen independent control acceptance required')
        accepted=w.read_json(w.safe_path(root,acceptance['path']))
        qa_task=accepted.get('qa_task_id',accepted.get('task_id'))
        qa_pin=w.file_digest(root,str(accepted.get('qa_outbox_path','')))
        box=w.read_json(w.safe_path(root,qa_pin['path']))
        rows,invalid=w._validate_receipt_chain(root,qa_task)
        qa_role=accepted.get('qa_department','qa')
        matches=[row for row in rows if row.get('receipt_id')==accepted.get('qa_receipt_id')
            and row.get('receipt_type')=='qa_verdict' and row.get('verdict')=='pass'
            and row.get('department')==qa_role and qa_pin in row.get('evidence',[])
            and row.get('chat_task_id')==w.department_registry(root).get(qa_role,{}).get('chat_binding',{}).get('task_id')]
        if (qa_role not in {'qa','qa-technical'} or invalid or len(matches)!=1
                or qa_pin['sha256']!=accepted.get('qa_outbox_sha256')
                or box.get('department')!=qa_role or box.get('task_id')!=qa_task or box.get('risk_level')!='R0'
                or box.get('production_release_eligible') is not False
                or box.get('qa_result')!='PASS_INTERNAL_APPLICATION_ALLOWED'
                or box.get('candidate_sha256')!=accepted.get('candidate_sha256')
                or w.file_digest(root,str(accepted.get('candidate_path','')))['sha256']!=box.get('candidate_sha256')):
            raise w.WorkflowError('exact independent R0 control QA required; version prefixes do not authorize')
        w.validate_outbox(root,[qa_pin],qa_role,qa_task)
        candidate=w.read_json(w.safe_path(root,accepted['candidate_path']))
        candidate_request=candidate.get('request',{})
        if not isinstance(candidate_request,dict) or candidate_request.get('path')!=request_pin['path'] or candidate_request.get('sha256')!=request_pin['sha256']:
            raise w.WorkflowError('control QA must bind this exact request, not an earlier version')
        if request['sender_department']!='operations':
            import routine_grants
            grant=routine_grants.validate(root,request.get('coordinator_grant'),'operations-assistant-2')
            if grant.get('routing')!=requested:raise w.WorkflowError('exact developer routing grant required')
        for field in ('native_send_receipt_path','native_attempt_receipt_path'):
            path=w.safe_path(root,str(request.get(field,'')))
            if path==Path(root).resolve() or path.exists():raise w.WorkflowError('sent or uncertain; native readback before retry')
        return [],['routing_precheck:human_exact_developer','independent_control_QA:exact_request','native_send_reservation:required']
    except (w.WorkflowError,KeyError,TypeError,ValueError,OSError):
        return ['owner_project_handoff_exact_binding_required'],['routing_precheck:human_exact_developer']


if __name__=='__main__':
    import argparse,json
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True)
    p.add_argument('--request',required=True);p.add_argument('--live',required=True)
    a=p.parse_args();result=review_candidate(a.root,w.file_digest(a.root,a.request),w.read_json(w.safe_path(a.root,a.live)))
    print(json.dumps({k:result[k] for k in ('read_only','qa_review_eligible','activated','sent','production_authority_granted')},ensure_ascii=False))
