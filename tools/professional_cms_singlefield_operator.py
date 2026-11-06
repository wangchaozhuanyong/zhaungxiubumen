"""Original PUB evidence assembler. No SQL, Save, permit, dispatch or approval.

Prepare scripts first. Capture actual commands, wait for completion, read the
first-party original native, then finalize. Missing future native is rejected.
All output is new project-owned evidence; business execution stays normal.
"""
from pathlib import Path
import argparse,datetime as dt,json
import workflow_control as w
import professional_cms_single_field_admission as s


def save(root,directory,name,value):
    directory=w.safe_path(root,directory);directory.mkdir(parents=True,exist_ok=True)
    path=directory/name;s.need(not path.exists(),'preserve original evidence; use exact new finite directory')
    w.atomic_write_json(path,value);return w.file_digest(root,str(path.relative_to(Path(root))))


def prepare_admission(root,bridge_pin,bundle,directory):
    ctx=s.bridge_context(root,bridge_pin);s.need(bundle.get('bridge_source')==bridge_pin,'same exact registered workorder')
    s._received(root,ctx,bundle)
    from professional_cms_singlefield_provider import read_actual
    proof=read_actual(root,ctx,bundle['provider_references'],sdk_source=bundle['PUB_native']);s.need(proof.get('preview') is not None,'real completed protected preview required before admission, never a future run')
    proof['provider_checked_at']=dt.datetime.now(dt.timezone.utc).isoformat()
    row=proof['row'];t=ctx['target'];s.need(row==ctx['before'],'drift/NO_CHANGE is not admission; preserve accurate stop')
    before=save(root,directory,'ACTUAL-FULL41-BEFORE.json',row);backup=save(root,directory,'INDEPENDENT-FULL41-BACKUP.json',row)
    pp=save(root,directory,'ACTUAL-PROVIDER-READBACK.json',proof)
    check={'task_id':ctx['task'],'department':'publishing','action_id':t['actionId'],'scope':ctx['scope'],'bridge_source':bridge_pin,'provider_proof':pp,'before':before,'desired_fields_sha256':t['desiredFieldsSha256'],'protected38_fields_sha256':t['retainedFieldsSha256'],'rollback_allowed':False,'production_write_allowed':False}
    cp=save(root,directory,'PUB-OWN-SELF-CHECK.json',check)
    draft={'schema':s.ADMISSION_SCHEMA,'task_id':ctx['task'],'scope':ctx['scope'],'bridge_source':bridge_pin,
      'source_input_path':str(w.safe_path(root,directory)/'EXACT-PUB-PRODUCTION-ADMISSION.json'),
      **({'continuation_source':bundle['continuation_source']} if bundle.get('continuation_source') else {}),
      'PUB_native':None,'provider_references':bundle['provider_references'],'before':before,'backup':backup,'provider_proof':pp,'self_check':cp}
    dp=save(root,directory,'DRAFT-ADMISSION-MISSING-REAL-NATIVE.json',draft)
    return {'self_check':cp,'draft':dp,'status':'AWAIT_ACTUAL_COMMAND_COMPLETION_AND_FIRST_PARTY_NATIVE','not_valid_for_record':True,'permit_issued':False}


def finalize_admission(root,draft_pin,native_pin):
    item=s.document(root,draft_pin);s.need(item.get('PUB_native') is None,'do not replace an already bound actual native')
    item={**item,'PUB_native':native_pin};ctx=s.verify_admission_for_record(root,s.h._snapshot(root),item)
    path=Path(item['source_input_path']);s.need(not path.exists(),'preserve existing exact admission')
    w.atomic_write_json(path,item)
    return {'admission_input':w.file_digest(root,str(path.relative_to(Path(root)))),'status':'PREPARED_NOT_REGISTERED','target':ctx['action']['candidate_version'],'permit_issued':False}


def prepare_execution(root,admission_pin,directory,bundle=None):
    import professional_cms_execution as cms
    snap=s.h._snapshot(root);sources=[x for x in cms.records(root,snap) if x.get('singlefield_forward_admission') and x['registration']==admission_pin]
    s.need(len(sources)==1,'real normal production admission first; do not use a draft/fixture')
    x=sources[0];item=s.document(root,admission_pin);ctx=x['bridge_context'];t=ctx['target']
    from professional_cms_singlefield_provider import read_actual
    refs=item['provider_references']
    if bundle is not None:
        s.need(bundle.get('bridge_source')==item['bridge_source'] and bundle.get('provider_references',{}).get('preview_run_id')==refs['preview_run_id'],'fresh re-read may reuse only the same actual protected preview/workorder')
        s._received(root,ctx,bundle);refs=bundle['provider_references']
    need_cause=(bundle or item).get('continuation_source');s.need(need_cause==item.get('continuation_source'),'same real causal continuation as admission')
    proof=read_actual(root,ctx,refs,sdk_source=(bundle or item)['PUB_native']);s.need(proof['row']==ctx['before'],'fresh original baseline required')
    proof['provider_checked_at']=dt.datetime.now(dt.timezone.utc).isoformat();pp=save(root,directory,'EXECUTION-ACTUAL-PROVIDERS.json',proof)
    req={'task_id':ctx['task'],'department':'publishing','sender_department':'publishing','action_id':t['actionId'],'action_class':'cms_write','scope':ctx['scope'],
      'source_project_id':ctx['pub_binding']['project_id'],'operation':'field_patch','business_scope':ctx['scope'],'physical_scope':t['scope'],
      'table':t['table'],'slug':t['slug'],'object_ids':[t['id']],'changed_fields':['content_zh'],'candidate_version':t['candidateVersion'],
      'professional_execution_source':admission_pin,'before':item['before'],'desired':ctx['desired'],'expected_updated_at':ctx['before']['updated_at'],'expected_version':ctx['before']['version'],
      'observed_at':proof['observed_at'],'authorization_changes':[]}
    intent=w.sha256_value(req)
    summary={**({'continuation_source':need_cause} if need_cause else {}),**{k:req[k] for k in ('task_id','department','action_id','action_class','scope')},'intent_sha256':intent,'current_row':req['before'],
      'provider_proof':pp,'provider_references':refs,'observed_at':proof['observed_at'],'status':'PASS','production_write_allowed':False}
    plan={'schema':'PUB-singlefield-preflight-data-before-native/v1','request_base':req,'native_summary':summary,'bridge_source':item['bridge_source']}
    pin=save(root,directory,'ACTUAL-EXECUTION-DATA-PLAN.json',plan)
    return {'PUB_singlefield_preflight':summary,'data_plan':pin,'status':'AWAIT_ACTUAL_COMMAND_COMPLETION_AND_FIRST_PARTY_NATIVE','permit_issued':False}


def finalize_execution(root,plan_pin,native_pin,command_id,directory):
    plan=s.document(root,plan_pin);req=plan['request_base'];summary=plan['native_summary'];ctx=s.bridge_context(root,plan['bridge_source'])
    item=s.document(root,req['professional_execution_source']);bundle={**item,'PUB_native':native_pin,'provider_references':summary['provider_references']}
    turn=s._received(root,ctx,bundle);matches=[m for m in turn['items'] if m.get('id')==command_id]
    s.need(len(matches)==1 and matches[0].get('type')=='commandExecution' and matches[0].get('status')=='completed' and matches[0].get('exitCode')==0,'actual completed original PUB capture command required, never future/native printed PASS')
    output=json.loads(w._completion_execution_output(matches[0]));s.need(output.get('PUB_singlefield_preflight')==summary,'actual original command output differs from data plan')
    common={k:summary[k] for k in ('task_id','department','action_id','action_class','scope','intent_sha256')}
    facts={**({'continuation_source':summary['continuation_source']} if summary.get('continuation_source') else {}),**common,'current_row':req['before'],'provider_proof':summary['provider_proof'],'provider_references':summary['provider_references'],
      'PUB_native':native_pin,'source_command_id':command_id,'observed_at':summary['observed_at']}
    check={**common,'status':'PASS','production_write_allowed':False}
    backup={**common,'complete_row':req['before']}
    for key,doc in [('facts',facts),('self_check',check),('backup',backup)]:req[key]=save(root,directory,key+'.json',doc)
    req['rollback']=None
    rp=save(root,directory,'EXACT-PUB-FRESH-EXECUTION-REQUEST.json',req)
    s.validate_execution_request(root,s.h._snapshot(root),rp)
    envelope={'schema':'professional-cms-fresh-preflight/v1','task_id':ctx['task'],'request':rp}
    ep=save(root,directory,'EXACT-PUB-PREFLIGHT-RECORD-INPUT.json',envelope)
    return {'request':rp,'preflight_record_input':ep,'status':'PREPARED_NOT_PREFLIGHT_REGISTERED','permit_issued':False}


def own_decision(root,name,path):
    import professional_cms_issuer as issuer
    target=issuer.targets(root,task_id=s.h.TASK).get(name);s.need(target and target.get('singlefield_forward_admission'),'this authenticated original singlefield target only')
    accepted=issuer.acceptance(root,target,'publish');now=w.utc_timestamp()
    value={'department':'publishing','decision':'EXECUTE_ORIGINAL_AUTHORIZED_ACTION','task_id':target['task_id'],'action_id':accepted['action_id'],'action_class':'cms_write','scope':target['scope'],'candidate_version':accepted['candidate_version'],'record_id':target['record_id'],'payload_sha256':target['payload_sha256'],'authorization_pin':accepted['authorization_pin'],'execution_preflight':accepted['execution_preflight'],'execution_preflight_event_id':accepted['execution_preflight_event_id'],'decided_at':now,'decision_id':'pub-own-'+w.sha256_value([accepted,now])[:20]}
    out=w.safe_path(root,path);s.need(not out.exists(),'preserve prior own readiness')
    w.atomic_write_json(out,value);return {'own_decision':w.file_digest(root,path),'status':'OWN_READINESS_NOT_A_PERMIT','permit_issued':False}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=['prepare-admission','finalize-admission','prepare-execution','finalize-execution','own-decision'])
    for name in ['bridge-source','input','native','command-id','directory','output','target','references']:p.add_argument('--'+name)
    a=p.parse_args();root=Path(__file__).resolve().parents[1]
    try:
        with w.request_validation_context():
            pin=lambda value:w.file_digest(root,value)
            if a.command=='prepare-admission':value=prepare_admission(root,pin(a.bridge_source),s.document(root,pin(a.input)),a.directory)
            elif a.command=='finalize-admission':value=finalize_admission(root,pin(a.input),pin(a.native))
            elif a.command=='prepare-execution':value=prepare_execution(root,pin(a.input),a.directory,s.document(root,pin(a.references)) if a.references else None)
            elif a.command=='finalize-execution':value=finalize_execution(root,pin(a.input),pin(a.native),a.command_id,a.directory)
            else:value=own_decision(root,a.target,a.output)
        print(json.dumps(value,ensure_ascii=False,indent=2))
    except (w.WorkflowError,ValueError,KeyError,OSError) as error:p.exit(1,str(error)+'\n')

if __name__=='__main__':main()
