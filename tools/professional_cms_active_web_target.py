"""Authenticate a completed WEB candidate for a source-only active CMS stage.

Discovery is not production admission, an effect lookup, or a permit.
"""
from pathlib import Path
import hashlib
import json
import re
import shutil
import subprocess
import workflow_control as w
import department_autonomy as a
import professional_cms_active_stage as active

SCHEMA = 'professional-cms-active-stage-web-target-source/v1'
EVENT = 'professional_cms_active_stage_web_target_source'


def _local_pin(root, pin):
    a.require(isinstance(pin,dict) and set(pin)=={'path','sha256','size'}
              and w.file_digest(root,pin['path'])==pin,'exact local immutable source pin required')
    return json.loads(w.safe_path(root,pin['path']).read_bytes())


def _web_pin(pin, web_root):
    a.require(isinstance(pin,dict) and set(pin)=={'path','sha256','size'},'exact WEB pin required')
    p=Path(pin['path']);a.require(p.is_absolute() and p.resolve(strict=True).is_relative_to(web_root)
                                and not p.is_symlink(),'fixed WEB project source required')
    b=p.read_bytes();a.require(len(b)==pin['size'] and hashlib.sha256(b).hexdigest()==pin['sha256'],
                              'exact WEB source bytes required')
    return b


def validate(root, source):
    root=Path(root).resolve(strict=True)
    keys={'schema','maintenance_task_id','parent_task_id','execution_stage_task_id','stage_event_id',
          'stage_contract','web_candidate','web_completed_native','web_result'}
    a.require(isinstance(source,dict) and set(source)==keys and source['schema']==SCHEMA,
              'exact active-stage WEB source schema required')
    parent=w.validate_task_id(source['parent_task_id']);stage=w.validate_task_id(source['execution_stage_task_id'])
    maint=w.validate_task_id(source['maintenance_task_id']);a.require(len({parent,stage,maint})==3,'distinct original tasks required')
    previous=active.stage_catalog(root,maint,parent)
    a.require(len(previous)==1 and previous[0]['event_id']==source['stage_event_id'], 'one exact original source event required')
    prior=previous[0];snapshot=w.read_json(w.snapshot_path(root,stage));contract=_local_pin(root,source['stage_contract'])
    a.require(snapshot and snapshot.get('goal_contract')==source['stage_contract'] and snapshot.get('current_state') not in w.TERMINAL_STATES
              and contract.get('task_id')==stage and contract.get('parent_task_id')==parent
              and contract.get('primary_owner')=='paid-growth-data-2' and 'publishing' in contract.get('producer_departments',[])
              and len(contract.get('required_execution_actions',[]))==2,'unchanged active stage and original owner/actions required')
    goal=snapshot.get('goal_delivery',{})
    a.require(all(goal.get(k)==contract.get(k) for k in ('parent_task_id','primary_owner','producer_departments',
              'authorized_scope','human_authorization','required_execution_actions')),'unchanged frozen stage contract required')
    reg=w.read_json(root/'data/department-registry.json');binding=reg['collaboration_bindings']['designated-development']
    webroot=Path(binding['cwd']).resolve(strict=True);raw=_web_pin(source['web_candidate'],webroot);candidate=json.loads(raw)
    native=_local_pin(root,source['web_completed_native']);turn=native.get('turn',{});thread=native.get('thread',{})
    a.require(native.get('capture_kind')=='first_party_read_thread_selected_items_not_full_raw'
              and thread.get('id')==binding['thread_id'] and thread.get('cwd')==binding['cwd']
              and thread.get('hostId')==binding['host_id'] and turn.get('status')=='completed',
              'actual fixed original WEB completed native required')
    done=[x for x in turn.get('items',[]) if x.get('type')=='commandExecution' and x.get('status')=='completed'
          and x.get('exitCode')==0 and not x.get('output',{}).get('truncated')
          and source['web_candidate']['sha256'] in x.get('output',{}).get('text','')]
    a.require(len(done)==1,'one actual WEB command must pin exact candidate bytes')
    output=json.loads(done[0]['output']['text']);a.require(output.get('SYS_input')==source['web_candidate'],
          'WEB native source output must match exact candidate pin')
    result=json.loads(_web_pin(source['web_result'],webroot));finals=[x for x in turn.get('items',[]) if x.get('type')=='agentMessage' and x.get('phase')=='final_answer']
    a.require(len(finals)==1 and candidate['local_version']['head'][:8] in finals[0].get('text','')
              and Path(source['web_result']['path']).name in json.dumps(turn,ensure_ascii=False),
              'actual completed WEB final and original report source required')
    a.require(candidate.get('schema')=='WEB-proposed-exact-two-excerpt-channel-input/v1'
              and candidate.get('task_id')==parent and candidate.get('original_owner')=='paid-growth-data-2'
              and candidate.get('CMS_executor')=='publishing' and candidate.get('WEB_executor')=='designated-development'
              and candidate.get('source_stage_event')==prior['event_id'] and candidate.get('automatic_remote_authority_granted_by_this_input') is False,
              'exact original source stage, roles and nonexecuting WEB candidate required')
    source_stage=candidate['source_stage'];a.require(source_stage['sha256']==prior['registration']['sha256']
              and source_stage['size']==prior['registration']['size'],'unchanged original stage bytes required')
    version=candidate['local_version'];wt=Path(version['worktree']).resolve(strict=True)
    a.require(result.get('schema')=='WEB-actual-two-excerpt-discovery-local-delivery/v1'
              and result.get('task_id')==parent and result.get('local_head')==version['head']
              and result.get('base')==version['base'] and result.get('tree')==version['tree']
              and result.get('files')==len(version['files']) and result.get('remote_READY') is False
              and result.get('inputs',{}).get('SYS_exact_local_candidate')==source['web_candidate'],
              'exact actual WEB report and nonexecuting candidate source required')
    a.require(wt.is_relative_to(webroot) and len(version['parents'])==1 and version['parents'][0]==version['base'],
              'one exact original WEB worktree/base/parent required')
    def git(*args):
        x=subprocess.run(['git',*args],cwd=wt,capture_output=True,timeout=20)
        a.require(x.returncode==0,'actual immutable WEB git source unavailable');return x.stdout
    a.require(git('show','-s','--format=%H %P %T',version['head']).decode().strip().split()
              ==[version['head'],*version['parents'],version['tree']],'actual commit, parent, tree required')
    files=version['files'];paths=[x['path'] for x in files]
    a.require(len(paths)==len(set(paths))==9 and set(git('diff','--name-only',version['base'],version['head']).decode().splitlines())==set(paths),
              'exact complete original changed source paths required')
    for f in files:
        blob=git('show',version['head']+':'+f['path']);entry=git('ls-tree',version['head'],'--',f['path']).decode().strip().split()
        a.require(entry==[f['mode'],'blob',f['blob'],f['path']] and len(blob)==f['size']
                  and hashlib.sha256(blob).hexdigest()==f['sha256'],'actual file bytes, blob and mode required')
    frozen_raw=_web_pin(candidate['frozen_channel_source'],webroot);frozen=json.loads(frozen_raw)
    frozen_rel=Path(candidate['frozen_channel_source']['path']).resolve().relative_to(wt).as_posix()
    a.require(frozen_rel in paths and git('show',version['head']+':'+frozen_rel)==frozen_raw
              and frozen.get('source_stage_event')==prior['event_id'] and frozen.get('task_id')==parent
              and frozen.get('owner')=='paid-growth-data-2' and frozen.get('executor')=='publishing'
              and frozen.get('registration_grants_write_authority') is False and frozen.get('remote_loaded') is False
              and frozen.get('production_READY') is False and frozen.get('CMS_Save')==0,
              'exact committed frozen original channel, source and nonexecution boundary required')
    forward=git('diff','--binary','--full-index',version['base'],version['head'])
    inverse=git('diff','--binary','--full-index','-R',version['base'],version['head'])
    a.require(_web_pin(version['forward'],webroot)==forward and _web_pin(version['inverse'],webroot)==inverse,
              'exact original forward/inverse source patch required')
    a.require(len(candidate['rows'])==2 and len(prior['rows'])==2,'two independent original rows required')
    stage_doc=_local_pin(root,prior['registration']);pub_requests=[_local_pin(root,x) for x in stage_doc['pub_requests']]
    result_rows=[];seen=set()
    for row in candidate['rows']:
        target=row['target'];found=[x for x in prior['rows'] if x['action_id']==target['actionId'] and x['record_id']==target['id']]
        a.require(len(found)==1 and target['id'] not in seen,'one exact original action and unique record required');seen.add(target['id']);p=found[0]
        requirements=[x for x in contract['required_execution_actions'] if x['action_id']==p['action_id']]
        a.require(len(requirements)==1 and requirements[0]['scope']==p['scope'] and requirements[0]['department']=='publishing'
                  and requirements[0]['action_class']=='cms_write','one frozen original PUB action per record required')
        request=_local_pin(root,requirements[0]['request']);baseline=row['dated_full41'];desired=row['desired_fields'];fields=['excerpt_zh','excerpt_en','excerpt_ms']
        stable=sorted(set(baseline)-set(fields)-{'created_at','updated_at','version'})
        expected={'id':p['record_id'],'slug':request['slug'],'contentType':'service','table':'services','taskId':parent,
          'actionId':p['action_id'],'candidateVersion':p['candidate_version'],'scope':p['scope'],'changedFields':fields,
          'baselineProjectionFields':sorted(baseline),'baselineFieldsSha256':w.sha256_value(baseline),
          'desiredFieldsSha256':w.sha256_value(desired),'rollbackFieldsSha256':w.sha256_value({k:baseline[k] for k in fields}),
          'expectedUpdatedAt':baseline['updated_at'],'retainedProjectionFields':stable,
          'retainedFieldsSha256':w.sha256_value({k:baseline[k] for k in stable}),'rollbackAllowed':False,'requiresParentRun':True}
        a.require(target==expected and request['task_id']==stage and request['parent_task_id']==parent
                  and request['candidate_version']==p['candidate_version'] and request['record_id']==p['record_id']
                  and request['scope']==p['scope'] and request['write_payload_only']==desired
                  and w.sha256_value(desired)==p['payload_sha256'] and len(baseline)==41 and len(stable)==35
                  and len([x for x in baseline if x.endswith('_ms')])==11
                  and row['dated_baseline_is_execution_CAS'] is False and row['inverse']['allowed'] is False
                  and row['CLI_target_option']==p['candidate_version']
                  and row['workflow']=='.github/workflows/content-publish-approved.yml',
                  'exact dated target, payload, independent PUB stage and protected full41 required')
        a.require(row['runtime_source_file'] in paths and row['CLI_source_file'] in paths and row['workflow'] in paths,
                  'actual committed target/CLI/workflow contribution required')
        pub_matches=[(pin,req) for pin,req in zip(stage_doc['pub_requests'],pub_requests) if req.get('record_id')==p['record_id']]
        pub_pins={x.get('kind'):x for x in row.get('original_PUB_sources',[])}
        a.require(len(pub_matches)==1 and set(pub_pins)=={'PUB_request_source','PUB_before_source'},
                  'one original PUB request and dated full41 per record required')
        pub_pin,pub_req=pub_matches[0]
        for key,actual in [('PUB_request_source',pub_pin),('PUB_before_source',pub_req['PUB_full41_raw'])]:
            observed=pub_pins[key];actual_path=Path(actual['path'])
            if not actual_path.is_absolute():actual_path=root/actual_path
            a.require(Path(observed['path']).resolve()==actual_path.resolve()
                      and observed['sha256']==actual['sha256'] and observed['size']==actual['size'],
                      'unchanged original PUB source path and bytes required')
        a.require(baseline==json.loads((root/pub_req['PUB_full41_raw']['path']).read_bytes()),
                  'dated target baseline equals actual original PUB source bytes')
        frozen_rows=[x for x in frozen.get('entries',[]) if x.get('runtime_target',{}).get('id')==p['record_id']]
        a.require(len(frozen_rows)==1 and frozen_rows[0].get('runtime_target')==target
                  and frozen_rows[0].get('before')==baseline and frozen_rows[0].get('desired')==desired
                  and frozen_rows[0].get('baseline_is_execution_CAS') is False,
                  'exact committed frozen row, target and dated values required')
        baseline_path=Path(pub_req['PUB_full41_raw']['path']).resolve(strict=True)
        a.require(baseline_path.is_relative_to(root),'original PUB baseline project boundary')
        baseline_pin=w.file_digest(root,str(baseline_path.relative_to(root)))
        a.require(baseline_pin['sha256']==pub_req['PUB_full41_raw']['sha256']
                  and baseline_pin['size']==pub_req['PUB_full41_raw']['size'],'original PUB baseline pin required')
        result_rows.append({'action':p,'target':target,'baseline_pin':baseline_pin,'execution_stage_task_id':stage,
                            'WEB_head':version['head'],'runtime_loaded':'NOT_OBSERVED',
                            'original_key_effect':'UNKNOWN','permit_issued':False,'production_READY':False})
    a.require(seen=={x['record_id'] for x in prior['rows']},'all and only original two rows required')
    runtime_paths={x['runtime_source_file'] for x in candidate['rows']};cli_paths={x['CLI_source_file'] for x in candidate['rows']}
    workflow_paths={x['workflow'] for x in candidate['rows']}
    a.require(len(runtime_paths)==len(cli_paths)==len(workflow_paths)==1,'one exact shared channel implementation required')
    runtime_path=next(iter(runtime_paths));cli_path=next(iter(cli_paths));workflow_path=next(iter(workflow_paths))
    runtime_bytes=git('show',version['head']+':'+runtime_path);runtime=runtime_bytes.decode('utf-8')
    parsed=re.search(r'export\s+const\s+PAID2_CRO_EXCERPT_TARGETS\s*:\s*readonly\s+ManagedTarget\[\]\s*=\s*(\[[\s\S]*?\]);',runtime)
    a.require(parsed is not None and json.loads(parsed.group(1))==[x['target'] for x in candidate['rows']],
              'actual committed runtime target objects equal both authenticated tuples')
    workflow=git('show',version['head']+':'+workflow_path).decode('utf-8')
    a.require(all(re.search(r'(?m)^\s*-\s*'+re.escape(x['action']['candidate_version'])+r'\s*$',workflow) for x in result_rows),
              'actual committed workflow exposes both exact target options')
    # Run the inspected, committed read-only CLI source against its exact frozen
    # source. No network, policy, permit, preview or production action occurs.
    for p in (runtime_path,cli_path,frozen_rel):
        a.require((wt/p).is_file() and (wt/p).read_bytes()==git('show',version['head']+':'+p),
                  'actual local CLI source inputs remain byte-identical to commit')
    node=shutil.which('node');a.require(node is not None,'existing local Node needed for source-only CLI read')
    js='import {lockedPaid2CroCandidates as x} from "./'+cli_path+'";process.stdout.write(JSON.stringify(x));'
    proc=subprocess.run([node,'--input-type=module','-e',js],cwd=wt,capture_output=True,timeout=30)
    a.require(proc.returncode==0,'actual original CLI source-only read must succeed')
    cli=json.loads(proc.stdout);a.require(set(cli)=={x['action']['candidate_version'] for x in result_rows},
              'CLI exposes both and only original independent versions')
    for x in result_rows:
        entry=cli[x['action']['candidate_version']]
        a.require(all(entry.get(k)==v for k,v in x['target'].items()) and entry.get('recordId')==x['action']['record_id']
                  and entry.get('actionClass')=='cms_write' and entry.get('exactPatchOnly') is True
                  and entry.get('sourceCandidateSha256')==candidate['frozen_channel_source']['sha256'],
                  'actual CLI target matches every authenticated runtime tuple and frozen source')
    return {'parent_task_id':parent,'maintenance_task_id':maint,'execution_stage_task_id':stage,
            'original_source_event':prior['event_id'],'rows':result_rows,'WEB_head':version['head'],
            'formal_PUB_result_receipt':'NOT_PROVEN','remote_loaded':False,'permit_issued':False,'actual_action_allowed':False}


def catalog(root, parent):
    root=Path(root).resolve();w.validate_task_id(parent);items=[]
    for event in w.read_jsonl(root/w.WORKFLOW_EVENTS):
        detail=event.get('details',{}).get(EVENT)
        if detail is None or detail.get('parent_task_id')!=parent:continue
        source=_local_pin(root,detail['source']);value=validate(root,source)
        a.require(event.get('task_id')==value['maintenance_task_id'] and value['parent_task_id']==parent,
                  'actual registered original WEB source event required')
        items.append({**value,'registration':detail['source'],'event_id':event['event_id']})
    a.require(len(items)<=1,'ambiguous WEB source for the original active stage')
    return items


def register(root, source_path):
    root=Path(root).resolve();pin=w.file_digest(root,source_path);source=_local_pin(root,pin);value=validate(root,source)
    with w.workflow_lock(root):
        a.require(w.file_digest(root,source_path)==pin,'WEB source changed before append')
        value=validate(root,source);previous=catalog(root,value['parent_task_id'])
        if previous:
            a.require(previous[0]['registration']==pin,'different WEB source already registered')
            return {'result':'duplicate_ignored',**previous[0]}
        a.require(not w.validate_workflow_events(root,value['parent_task_id'])
                  and not w.validate_workflow_events(root,value['execution_stage_task_id'])
                  and not w.validate_workflow_events(root,value['maintenance_task_id']),
                  'original parent, execution stage and maintenance event chains must be intact')
        snapshot=w.read_json(w.snapshot_path(root,value['maintenance_task_id']))
        event=w.append_workflow_event(root,value['maintenance_task_id'],snapshot['current_state'],
                 {EVENT:{'parent_task_id':value['parent_task_id'],'source':pin},'external_permission_issued':False})
    return {'result':'recorded',**value,'registration':pin,'event_id':event['event_id']}


def record_from_parent(root, task_id, path):
    source=w.read_json(w.safe_path(root,path))
    a.require(source.get('schema')==SCHEMA and source.get('parent_task_id')==task_id,
              'exact original parent WEB source required')
    return register(root,path)


def pending_targets(root, parent):
    """Expose authenticated local WEB tuples as non-executable discovery only."""
    from professional_cms_issuer import PENDING_STAGE_MODEL
    result={}
    for group in catalog(root,parent):
        source=active.stage_catalog(root,group['maintenance_task_id'],parent)
        a.require(len(source)==1 and source[0]['event_id']==group['original_source_event'],
                  'one original source stage required for pending discovery')
        stage=source[0]
        for row in group['rows']:
            x=row['action'];t=row['target'];name=x['candidate_version'];baseline=row['baseline_pin']
            a.require(name not in result,'ambiguous active-stage source candidate')
            result[name]={'candidate_shape':PENDING_STAGE_MODEL,'task_id':parent,
                'execution_stage_task_id':group['execution_stage_task_id'],
                'action_id':x['action_id'],'candidate_version':name,'scope':x['scope'],
                'execution_scope':x['scope'],'execution_owner':'publishing','owner':'paid-growth-data-2',
                'record_id':x['record_id'],'slug':t['slug'],'table':'services','content_type':'service',
                'changed_fields':t['changedFields'],'candidate':(stage['registration']['path'],stage['registration']['sha256']),
                'rollback':(baseline['path'],baseline['sha256']),'payload_sha256':t['desiredFieldsSha256'],
                'baseline_projection_fields':t['baselineProjectionFields'],'baseline_fields_sha256':t['baselineFieldsSha256'],
                'desired_fields_sha256':t['desiredFieldsSha256'],'retained_fields_sha256':t['retainedFieldsSha256'],
                'rollback_fields_sha256':t['rollbackFieldsSha256'],'expected_updated_at':t['expectedUpdatedAt'],
                'rollback_allowed':False,'source_registration':stage['registration'],'issuer_contract':None,
                'stage_registration':stage['registration'],'stage_event_id':stage['event_id'],
                'WEB_source_registration':group['registration'],'WEB_source_event_id':group['event_id'],
                'WEB_candidate_head':group['WEB_head'],'physical_target':t,
                'runtime_loaded':'NOT_OBSERVED','original_key_effect':'UNKNOWN',
                'actual_action_allowed':False,'permit_issued':False,'production_READY':False}
    return result
