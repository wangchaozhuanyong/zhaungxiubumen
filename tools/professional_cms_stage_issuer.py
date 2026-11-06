"""Validate real WEB contracts for a legacy current stage; never issue a permit."""
from pathlib import Path
import hashlib
import json
import subprocess
import workflow_control as w
import department_autonomy as a
import professional_cms_legacy_stage as stage

SCHEMA='professional-cms-legacy-stage-issuer-source/v1'
EVENT='professional_cms_legacy_stage_issuer_source'

def validate(root, item):
    root=Path(root).resolve()
    a.require(isinstance(item,dict) and set(item)=={'schema','parent_task_id','maintenance_task_id',
       'execution_source_event','WEB_report','WEB_completed_native','contracts'} and item['schema']==SCHEMA,
       'exact current stage issuer source required')
    task=item['parent_task_id']; sources=stage.execution_catalog(root,task)
    a.require(len(sources)==1 and sources[0]['event_id']==item['execution_source_event']
       and sources[0]['maintenance_task_id']==item['maintenance_task_id'], 'one actual current stage event required')
    source=sources[0];report=a.document(root,item['WEB_report']);native=a.document(root,item['WEB_completed_native'])
    binding=w.read_json(root/'data/department-registry.json')['collaboration_bindings']['designated-development']
    turn=native.get('turn',{});finals=stage._final(turn)
    a.require(native.get('capture_kind')=='first_party_read_thread_selected_items_not_full_raw'
       and native.get('thread',{}).get('id')==binding['thread_id'] and native['thread'].get('cwd')==binding['cwd']
       and turn.get('status')=='completed' and len(finals)==1
       and Path(item['WEB_report']['path']).name in finals[0].get('text','')
       and report.get('task_id')==task and report.get('business_owner')=='paid-growth-data'
       and report.get('CMS_executor')=='original publishing' and report.get('WEB_executor')=='designated-development'
       and report.get('production_READY') is False and report.get('CMS_Save_this_turn')==0,
       'actual original WEB completed report and source-only scope required')
    chain=report['preserved_source_chain'];a.require(chain.get('unique_event')==source['event_id']
       and chain.get('execution_source')==source['registration'],'actual original stage lineage required')
    code=report['code'];original_wt=Path(code['worktree'])
    try:
        wt=original_wt.resolve(strict=True)
    except FileNotFoundError:
        from professional_cms_source_custody import repository_for_original
        wt=repository_for_original(root,report['frozen_source'],original_wt,code['head'])
    a.require(original_wt.resolve(strict=False).is_relative_to(Path(binding['cwd']).resolve(strict=True))
       and wt.is_relative_to(Path(binding['cwd']).resolve(strict=True)) and code['head'][:8] in finals[0]['text'],
       'actual original WEB fixed worktree and completed final required')
    raw=subprocess.run(['git','show','-s','--format=%H %P %T',code['head']],cwd=wt,capture_output=True,timeout=20)
    a.require(raw.returncode==0 and raw.stdout.decode().strip().split()==[code['head'],*code['parents'],code['tree']],
       'real original candidate commit, parents and tree required')
    pins=item['contracts'];report_rows=report['rows'];a.require(isinstance(pins,list) and len(pins)==4 and len(report_rows)==4,
       'four exact original issuer contracts required')
    records=[];seen=set()
    for pin in pins:
        contract=a.document(root,pin);matches=[v for v in source['actions'] if v['candidate_version']==contract.get('target_name')]
        a.require(len(matches)==1 and contract.get('schema')=='professional-cms-issuer-contract/v1'
          and contract.get('task_id')==task and contract.get('source_registration')==source['registration'],
          'one registered original stage/action contract required')
        action=matches[0];a.require(action['record_id'] not in seen,'duplicate stage target rejected');seen.add(action['record_id'])
        rr=[v for v in report_rows if v.get('record_id')==action['record_id']]
        a.require(len(rr)==1 and stage._same_pin(root,pin,rr[0].get('normal_issuer_contract_input'))
          and rr[0].get('WEB_delivery')==contract.get('WEB_delivery'),'actual WEB report must pin exact contract and delivery')
        from professional_cms_issuer import external
        delivery=external(root,contract['WEB_delivery'],binding);target=delivery['target']
        datum=external(root,delivery['source_json'],binding)
        a.require(delivery.get('frozen_source')==report.get('frozen_source')
          and delivery.get('owner_source')==source['registration'],'exact original frozen source pin required')
        frozen=external(root,delivery['frozen_source'],binding)
        a.require(frozen.get('task_id')==task and frozen.get('execution_metadata_source')==source['registration']
          and frozen.get('execution_metadata_event')==source['event_id']
          and frozen.get('registration_grants_write_authority') is False,'unchanged original nonexecuting source required')
        req=stage._json(root,action['PUB_request']);before=stage._json(root,action['dated_full41'])
        desired=datum.get('desired');prior={'content_zh':before['content_zh']};stable=sorted(set(before)-{'content_zh','created_at','updated_at','version'})
        a.require(isinstance(desired,dict) and set(desired)=={'content_zh'} and isinstance(desired['content_zh'],str)
          and hashlib.sha256(desired['content_zh'].encode()).hexdigest()==action['desired_sha256']
          and datum.get('before')==before and datum.get('source_registration')==source['registration']
          and datum.get('source_event')==source['event_id'] and datum.get('not_current_CAS_or_permit') is True,
          'exact original dated before and owner-adopted desired bytes required')
        expected={'id':action['record_id'],'slug':action['slug'],'contentType':'service','table':'services',
          'taskId':task,'actionId':action['action_id'],'candidateVersion':action['candidate_version'],
          'scope':action['physical_scope'],'changedFields':['content_zh'],'baselineProjectionFields':sorted(before),
          'baselineFieldsSha256':w.sha256_value(before),'desiredFieldsSha256':w.sha256_value(desired),
          'rollbackFieldsSha256':w.sha256_value(prior),'expectedUpdatedAt':before['updated_at'],
          'retainedProjectionFields':stable,'retainedFieldsSha256':w.sha256_value({k:before[k] for k in stable}),
          'rollbackAllowed':False,'requiresParentRun':True}
        frozen_rows=[x for x in frozen.get('entries',[]) if x.get('runtime_target',{}).get('id')==action['record_id']]
        a.require(len(frozen_rows)==1 and frozen_rows[0].get('runtime_target')==target
          and frozen_rows[0].get('before')==before and frozen_rows[0].get('desired')==desired
          and frozen_rows[0].get('baseline_is_current_CAS') is False
          and frozen_rows[0].get('inverse_authorized') is False and frozen_rows[0].get('original_key_effect')=='UNKNOWN',
          'exact frozen original four-row target/before/desired and unknown effect required')
        expected_tuple={'task_id':task,'action_id':action['action_id'],'candidate_version':action['candidate_version'],
          'operation':'publish','scope':action['physical_scope'],'table':'services','record_id':action['record_id'],
          'slug':action['slug'],'changed_fields':['content_zh'],'execution_owner':'publishing'}
        cli=delivery['Node_CLI'];vers=delivery['actual_version']
        a.require(target==expected and datum.get('task_id')==task and datum.get('forward_tuple')==expected_tuple
          and delivery.get('task_id')==task and delivery.get('scope')==action['physical_scope']
          and delivery.get('producer')=='designated-development' and delivery.get('producer_thread')==binding['thread_id']
          and delivery.get('owner')==source['actions'][0]['owner'] and delivery.get('source_registration')==source['registration']
          and delivery.get('source_metadata_event')==source['event_id'] and delivery.get('original_key_effect')=='UNKNOWN'
          and delivery.get('runtime_loaded') is False and delivery.get('issuer_registered') is False
          and delivery.get('production_READY') is False and delivery.get('permit_or_Save') is False
          and all(vers.get(k)==code.get(k) for k in ('head','base','tree','worktree','branch'))
          and cli.get('target')==action['candidate_version'] and cli.get('scope')==action['physical_scope']
          and cli.get('record_id')==action['record_id'] and cli.get('workflow')=='.github/workflows/content-publish-approved.yml',
          'actual WEB target, complete field projection, CLI, lineage and no release required')
        lookup=delivery.get('lookup_body',{})
        a.require(lookup=={'controlAction':'lookup','taskId':task,'actionId':action['action_id'],
          'candidateVersion':action['candidate_version'],'scope':action['physical_scope'],
          'recordId':action['record_id'],'slug':action['slug']}, 'exact independent read-only issuer lookup tuple required')
        records.append({'action':action,'target':target,'contract':pin,'WEB_delivery':contract['WEB_delivery'],
          'source_registration':source['registration'],'original_key_effect':'UNKNOWN','runtime_loaded':False,
          'actual_action_allowed':False,'permit_issued':False,'production_READY':False})
    a.require(seen=={x['record_id'] for x in source['actions']},'all four unique stage actions required')
    return {'task_id':task,'maintenance_task_id':item['maintenance_task_id'],'records':records,
            'source_only':True,'actual_action_allowed':False,'permit_issued':False,'production_READY':False}

def catalog(root,task):
    root=Path(root);out=[]
    for event in w.read_jsonl(root/w.WORKFLOW_EVENTS,where={('details',EVENT,'task_id'):task}):
        entry=event['details'][EVENT];val=validate(root,a.document(root,entry['source']))
        a.require(event.get('task_id')==val['maintenance_task_id'],'exact maintenance event required')
        out.append({**val,'registration':entry['source'],'event_id':event['event_id']})
    a.require(len(out)<=1,'ambiguous current-stage issuer registrations');return out

def register(root,path):
    root=Path(root);pin=w.file_digest(root,path);item=a.document(root,pin);val=validate(root,item)
    with w.workflow_lock(root):
        a.require(w.file_digest(root,path)==pin,'issuer source changed before registration');val=validate(root,item)
        old=catalog(root,val['task_id'])
        if old:
            a.require(old[0]['registration']==pin,'different current-stage issuer source already registered')
            return {'result':'duplicate_ignored',**old[0]}
        snap=w.read_json(w.snapshot_path(root,val['maintenance_task_id']))
        event=w.append_workflow_event(root,val['maintenance_task_id'],snap['current_state'],
          {EVENT:{'task_id':val['task_id'],'source':pin},'external_permission_issued':False})
    return {'result':'recorded',**val,'registration':pin,'event_id':event['event_id']}

def contract(root,snapshot,item):
    rows=catalog(root,snapshot['task_id']);matches=[]
    for group in rows:
        for row in group['records']:
            if a.document(root,row['contract'])==item:matches.append((group,row))
    a.require(len(matches)==1,'one actual registered current-stage WEB issuer contract required')
    group,row=matches[0];x={'action':row['action'],'owner':'paid-growth-data','executor':'publishing',
       'business_scope':row['action']['physical_scope'],'registration':row['source_registration'],
       'source_only':True,'actual_action_allowed':False,'stage_issuer_source':group['registration']}
    return x,a.document(root,row['source_registration']),row['target']

def current_execution_context(root, request):
    """Authenticate a historical stage source; never infer current effects or permission."""
    root=Path(root).resolve()
    def local_document(pin):
        a.require(isinstance(pin,dict) and set(pin)=={'path','sha256','size'},'exact local source pin required')
        path=Path(pin['path']);path=(root/path).resolve()
        a.require(path.is_relative_to(root) and path.is_file(),'source must remain in original project')
        relative=str(path.relative_to(root));actual=w.file_digest(root,relative)
        a.require(all(actual[k]==pin[k] for k in ('sha256','size')),'exact original source bytes required')
        return a.document(root,actual)
    keys={'task_id','stage_task_id','action_id','candidate_version','scope','record_id','department',
          'source_registration','issuer_contract','context_input','web_result','web_completed_native'}
    a.require(isinstance(request,dict) and set(request)==keys,'exact original stage context input required')
    parent=request['task_id'];stage_task=request['stage_task_id']
    w.validate_task_id(parent);w.validate_task_id(stage_task)
    snapshot=w.read_json(w.snapshot_path(root,stage_task));contract=a.document(root,snapshot['goal_contract'])
    goal=snapshot.get('goal_delivery',{})
    a.require(snapshot.get('task_id')==stage_task and snapshot.get('current_state') not in w.TERMINAL_STATES
      and snapshot.get('current_state') not in {'paused','suspended'}
      and contract.get('task_id')==stage_task and contract.get('parent_task_id')==parent
      and all(goal.get(k)==contract.get(k) for k in ('parent_task_id','primary_owner','producer_departments',
                                                       'authorized_scope','human_authorization','required_execution_actions'))
      and request['department']=='publishing' and request['department'] in goal.get('producer_departments',[])
      and request['scope'] in goal.get('authorized_scope',[]), 'active original stage, owner, executor and scope required')
    groups=catalog(root,parent)
    a.require(len(groups)==1,'one original stage issuer registration required')
    group=groups[0]; found=[x for x in group['records'] if x['action']['action_id']==request['action_id']]
    a.require(len(found)==1,'one exact original action required');row=found[0];act=row['action']
    a.require(all(request[k]==v for k,v in {'task_id':act['parent_task_id'],'candidate_version':act['candidate_version'],
      'scope':act['physical_scope'],'record_id':act['record_id'],'department':act['department'],
      'source_registration':row['source_registration'],'issuer_contract':row['contract']}.items())
      and goal['primary_owner']==act['owner'],'exact source, owner, actor, row and namespace required')
    context=local_document(request['context_input']);report=local_document(request['web_result']);native=local_document(request['web_completed_native'])
    lineage=context.get('existing_source_lineage',{});thread=native.get('thread',{});turn=native.get('turn',{})
    binding=w.read_json(root/'data/department-registry.json')['collaboration_bindings']['designated-development']
    a.require(context.get('schema')=='WEB-original-four-readonly-observation-and-current-stage-context-input/v1'
      and context.get('task_id')==parent and context.get('producer')=='designated-development'
      and context.get('original_WEB_thread')==binding['thread_id']
      and lineage.get('issuer_stage_event')==group['event_id'] and lineage.get('issuer_stage_registration')==group['registration']
      and lineage.get('execution_source')==row['source_registration']
      and report.get('task_id')==parent and report.get('exact_context_input')==request['context_input']
      and native.get('capture_kind')=='first_party_read_thread_selected_items_not_full_raw'
      and all(thread.get(k)==binding[v] for k,v in {'id':'thread_id','title':'title','cwd':'cwd','hostId':'host_id'}.items())
      and turn.get('id')==context.get('actual_current_turn') and turn.get('status')=='completed' and not turn.get('error')
      and any(x.get('type')=='agentMessage' and x.get('phase')=='final_answer'
              and str((root/Path(request['context_input']['path'])).resolve()) in x.get('text','')
              and str((root/Path(request['web_result']['path'])).resolve()) in x.get('text','') for x in turn.get('items',[])),
      'actual completed original WEB source, report, lineage and actor required')
    entries=[x for x in context.get('rows',[]) if x.get('action_id')==act['action_id']]
    a.require(len(entries)==1,'one exact observed original row required');entry=entries[0]
    a.require(entry.get('actually_loaded_runtime_target')==row['target']
      and entry.get('existing_source_registration')==row['source_registration']
      and entry.get('existing_issuer_contract')==row['contract']
      and entry.get('existing_stage_registration')==group['registration']
      and entry.get('existing_stage_event')==group['event_id'], 'exact runtime target and original sources required')
    # A dated source records what was seen; it is never a current key/effect assertion.
    lookup=local_document(entry['actual_lookup']['proof']);body=entry['lookup_body'];response=lookup.get('response',{})
    a.require(lookup.get('request_body')==body and lookup.get('http_status')==200
      and body=={'controlAction':'lookup','taskId':parent,'actionId':act['action_id'],
        'candidateVersion':act['candidate_version'],'scope':act['physical_scope'],
        'recordId':act['record_id'],'slug':act['slug']}
      and response.get('ok') is True and response.get('performed_write') is False
      and all(response.get(k)==body[k] for k in ('taskId','actionId','candidateVersion','scope','recordId','slug')),
      'exact original task and record lookup response required')
    return {'schema':'original-registered-CMS-stage-context/v1','task_id':parent,'stage_task_id':stage_task,
      'action_id':act['action_id'],'candidate_version':act['candidate_version'],'scope':act['physical_scope'],
      'record_id':act['record_id'],'slug':act['slug'],'department':act['department'],'owner':act['owner'],
      'source_registration':row['source_registration'],'issuer_contract':row['contract'],
      'stage_issuer_event':group['event_id'],'context_input':request['context_input'],
      'historical_WEB_lookup_observed_at':lookup.get('at'),'current_effect':'UNKNOWN',
      'required_next':['PUB fresh full41 and microsecond CAS','own backup and original-key effect readback',
        'zero-write preview and native selfcheck','independent fresh policy and single-use permit'],
      'actual_action_allowed':False,'permit_issued':False,'production_READY':False}

def lookup_request(root, request):
    """Derive the server's read-only lookup body from the exact registered row.

    Preparing this body makes no remote call and proves neither an effect nor
    authority to issue. The endpoint itself requires its existing issuer identity.
    """
    import professional_cms_issuer as issuer
    a.require(isinstance(request, dict), 'exact current-stage request required')
    task=request.get('task_id')
    a.require(isinstance(task,str) and task, 'exact current-stage task required')
    targets=issuer.targets(root,task_id=task)
    target=targets.get(request.get('candidate_version'))
    a.require(target is not None,'one exact registered current-stage target required')
    issuer.pending_stage_preflight(root,target,'publish',request)
    body={'controlAction':'lookup','taskId':target['task_id'],'actionId':target['action_id'],
          'candidateVersion':target['candidate_version'],'scope':target['execution_scope'],
          'recordId':target['record_id'],'slug':target['slug']}
    return {'lookup_body':body,'lookup_scope':'original_task_and_record_only',
            'other_namespace_effects':'UNKNOWN','remote_call_performed':False,
            'actual_action_allowed':False,'permit_issued':False,'production_READY':False}

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=['check','register','status','target-status','preflight-check','lookup-request','context-check'])
    parser.add_argument('--input');parser.add_argument('--task-id')
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1]);args=parser.parse_args()
    root=args.root.resolve()
    try:
        if args.command=='check':result=validate(root,a.document(root,w.file_digest(root,args.input)))
        elif args.command=='register':result=register(root,args.input)
        elif args.command=='target-status':
            import professional_cms_issuer as issuer
            targets=issuer.targets(root,task_id=args.task_id)
            result={'task_id':args.task_id,'targets':[x for x in targets.values()
                    if x.get('candidate_shape')==issuer.PENDING_STAGE_MODEL],
                    'actual_action_allowed':False,'permit_issued':False}
        elif args.command=='context-check':
            result=current_execution_context(root,a.document(root,w.file_digest(root,args.input)))
        elif args.command=='lookup-request':
            result=lookup_request(root,a.document(root,w.file_digest(root,args.input)))
        elif args.command=='preflight-check':
            import professional_cms_issuer as issuer
            request=a.document(root,w.file_digest(root,args.input));task=request.get('task_id')
            targets=issuer.targets(root,task_id=task);target=targets.get(request.get('candidate_version'))
            a.require(target is not None,'exact registered current-stage target required')
            result=issuer.pending_stage_preflight(root,target,'publish',request)
        else:result={'task_id':args.task_id,'current_stage_contracts':catalog(root,args.task_id),
                     'actual_action_allowed':False,'permit_issued':False}
        print(json.dumps(result,ensure_ascii=False,indent=2))
    except (w.WorkflowError,ValueError,KeyError,OSError) as error:parser.exit(1,str(error)+'\n')
