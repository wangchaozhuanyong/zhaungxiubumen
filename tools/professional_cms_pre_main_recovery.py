"""Authenticated pre-main / artifact-before-UUID failures -> explicit CMS instances.

This records source facts only. It never edits/consumes a policy or creates a
permit/UUID, calls a database/endpoint, or executes a captured command string.
"""
from pathlib import Path
import argparse,ast,datetime as dt,json,re
from copy import deepcopy
import workflow_control as w
import department_autonomy as a
import professional_cms_execution as src
EVENT='professional_cms_pre_main_recovery'
SCHEMA='professional-cms-consumed-pre-main-zero-effect-recovery/v1'
PREISSUE_EVENT='professional_cms_preissue_recovery'
PREISSUE_SCHEMA='professional-cms-consumed-artifact-preissue-zero-effect-recovery/v1'
def event_pin(event):
    details=event.get('details',{});pins=[details[k]for k in (EVENT,PREISSUE_EVENT)if details.get(k)]
    need(len(pins)==1,'one original recovery event kind');return pins[0]
def recovery_events(root,task):
    return [e for e in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS)if e.get('task_id')==task and any(e.get('details',{}).get(k)for k in (EVENT,PREISSUE_EVENT))]
def ancestors(value):
    return value.get('reconciled_policy_ids',[value['predecessor_policy_id']])
def latest_event(root,task):
    events=recovery_events(root,task)
    if not events:return None
    need(not w.validate_workflow_events(root,task),'real ordered recovery hash chain')
    values=[source(root,event_pin(e))for e in events]
    if len(events)==1:need(values[0]['schema']==SCHEMA,'artifact edge requires original pre-main source');return events[0]
    need(len(events)==2 and values[0]['schema']==SCHEMA and values[1]['schema']==PREISSUE_SCHEMA
         and values[1]['previous_instance']['recovery_event_id']==events[0]['event_id']
         and values[1]['previous_instance']['recovery_source']==event_pin(events[0]),'one append-only original stage successor, no fork/unknown chain')
    return events[-1]
def need(ok,message):a.require(ok,'CMS failed-instance recovery: '+message)
def now():return dt.datetime.now(dt.timezone.utc)
def doc(root,pin):return a.document(root,pin)
def _rows(value):
 need(isinstance(value,dict)and value.get('isError')is False and len(value.get('content',[]))==1,'successful actual authenticated SELECT response')
 text=json.loads(value['content'][0]['text']).get('result','').replace('\\n','\n')
 found=re.findall(r'<untrusted-data-[^>]+>\s*(\[[\s\S]*?\])\s*</untrusted-data-[^>]+>',text)
 need(len(found)==1,'one complete SELECT result, no unknown/ambiguous response');return json.loads(found[0])
def _run_zero(value,name,checked):
 rows=value.get('actual_all_runs');at=w._parse_observed_at(value.get('observed_at'))
 need(isinstance(rows,list)and at and rows,'complete observed workflow listing required')
 times=[w._parse_observed_at(x.get('createdAt'))for x in rows]
 need(all(times)and times==sorted(times,reverse=True)and (len(rows)<100 or times[-1]<=checked),'listing must cover original failure window; truncated/unknown is not zero')
 need(not any(x.get('displayTitle')==name+' | publish'or(x.get('displayTitle')=='Approved website content publish'and t>=checked)for x,t in zip(rows,times)),
      'actual/unknown original publish run exists; read effect, do not recover')
 return at
def _failed_native(root,pin,command,role):
 import goal_delivery_runtime as g
 page=g._native_document(root,pin);fixed=w.department_registry(root)[role]['chat_binding']
 need(all(page.get('thread',{}).get(k)==fixed[v]for k,v in {'id':'task_id','title':'title','cwd':'cwd'}.items())and fixed.get('project_id')==a.PROJECT,'real fixed original PUB/project native')
 pairs=[(t,m)for t in page.get('turns',[])for m in t.get('items',[])if m.get('id')==command];need(len(pairs)==1,'one actual original failed command')
 turn,call=pairs[0];need(not turn.get('error')and call.get('type')=='commandExecution'and call.get('status')=='failed'and call.get('exitCode')==1
  and Path(call.get('cwd','')).resolve()==Path(root).resolve(),'actual failure retained as failure, never successful completion')
 output=call.get('output');need(isinstance(output,dict)and set(output)=={'text','truncated'}and output.get('truncated')is False and isinstance(output.get('text'),str),'complete unmodified failed native output')
 return call,output['text']
def draft(root,report_pin,issuer_pin):
 import goal_delivery_runtime as g
 report=doc(root,report_pin);task=report.get('task_id');snapshot=g.restore_goal(root,w.read_json(w.snapshot_path(root,task)))
 need(report.get('schema')=='actual-professional-CMS-consumed-policy-pre-main-import-failure/v1','known professional pre-main import failure report')
 request_pin=report.get('actual_fresh_preflight',{}).get('request');request=doc(root,request_pin);x=src.match(root,snapshot,request)
 need(x and x['operation']=='publish'and report.get('department')==x['executor']and report.get('scope')==x['business_scope']
  and request.get('professional_execution_source')==x['registration']and request.get('execution_instance')is None,'original first forward request/actor/source only, not arbitrary retry chain')
 pid=report.get('consumed_once_policy',{}).get('decision_id');policies=[p for p in w.read_jsonl(Path(root)/w.POLICY_DECISIONS)if p.get('decision_id')==pid]
 need(len(policies)==1,'one actual original consumed policy');policy=policies[0]
 need(policy==doc(root,report['consumed_once_policy']['actual_row'])and all(policy.get(k)==request.get(k)for k in ('task_id','department','action_id','action_class','scope'))
  and policy.get('status')=='allow'and policy.get('approval_basis')==a.MODE and policy.get('approval_status')=='consumed_for_original_exact_autonomous_action'
  and policy.get('exact_request')==request_pin and policy.get('payload_sha256')==request_pin['sha256']
  and policy.get('original_authority')==snapshot['goal_delivery']['authorization_pin'],'real spent original authority/request, no reset or caller allow')
 events=[e for e in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS)if e.get('task_id')==task and e.get('details',{}).get('professional_cms_preflight',{}).get('request')==request_pin]
 need(len(events)==1 and events[0]['event_id']==report['actual_fresh_preflight']['event_id']and not w.validate_workflow_events(root,task),'exact ordered original preflight/source chain')
 fail=report['failed_once_invocation'];result=doc(root,fail['actual_inner_return']);argv=result.get('argv');act=x['action']
 need(isinstance(argv,list)and len(argv)==15 and argv[2:]==['--target',act['candidate_version'],'--operation','publish','--dry-run-run-id',argv[7],
  '--operations-decision',argv[9],'--policy-decision-id',pid,'--github-actor-id',argv[13],'--issue-and-dispatch']
  and str(argv[7]).isdigit()and str(argv[13]).isdigit()and result.get('exit_code')==1 and result.get('stdout')=='','one actual exact issue invocation, not help/proposal/success')
 call,text=_failed_native(root,fail['actual_native'],fail['command_id'],x['executor'])
 lines=[json.loads(v)for v in text.strip().splitlines()];need(lines[-1]==result and len(lines)>=2
  and pid in lines[-2].get('stdout','')and lines[-2].get('exit_code')==0,'real failed child and preceding successful consumed-policy output')
 checked=w._parse_observed_at(policy['checked_at']);start=w._parse_observed_at(result['started_at']);end=w._parse_observed_at(result['completed_at'])
 need(checked and start and end and checked<=start<end<=now(),'actual native policy then child failure chronology')
 observer_pin=w.file_digest(root,argv[1]);observer=w.safe_path(root,argv[1]).read_text();tree=ast.parse(observer)
 imports=[n for n in tree.body if isinstance(n,ast.ImportFrom)and n.module=='tools'and any(v.name=='managed_cms_permit_issuer'and v.asname=='issuer'for v in n.names)]
 need(len(imports)==1,'actual normal package observer import');boundary=imports[0].lineno
 prefix=[n for n in tree.body if n.lineno<boundary]
 allowed={ast.Import,ast.ImportFrom,ast.Assign,ast.Expr}
 need(all(type(n)in allowed for n in prefix)and all(isinstance(n.func,ast.Name)and n.func.id in {'Path','str'}for n in ast.walk(ast.Module(body=prefix,type_ignores=[]))if isinstance(n,ast.Call)),'no executable HTTP/UUID/business code before observed import')
 source_path=w.safe_path(root,issuer_pin['path']);need(w.file_digest(root,issuer_pin['path'])==issuer_pin and issuer_pin['sha256']==report.get('actual_issuer_source_sha256'),'exact old issuer bytes, never rewrite old execution source')
 issuer=source_path.read_text();main=next(n for n in ast.parse(issuer).body if isinstance(n,ast.FunctionDef)and n.name=='main')
 error=result['stderr'];frames=re.findall(r'File "([^"]+)", line (\d+), in ([^\n]+)',error)
 observer_abs=str(w.safe_path(root,argv[1]));issuer_abs=str(Path(root)/'tools/managed_cms_permit_issuer.py')
 need(frames and frames[0]==(observer_abs,str(boundary),'<module>')and any(p==issuer_abs and name=='<module>'and int(line)<main.lineno for p,line,name in frames)
  and any(name=='_available_shop_office_six_targets'for _,_,name in frames)
  and all(name not in {'main','endpoint_request','validate_policy'}for _,_,name in frames)
  and error.endswith('workflow_control.WorkflowError: shop/office exact execution: open exact new implementation stage required\n')
  and 'HTTP Error'not in error,'verified import boundary before main/permit UUID/HTTP, not a caller stage flag')
 body=issuer.split('def main(',1)[1];need(body.index('policy = validate_policy(')<body.index('"permitId": str(uuid4())')<body.index('issued = endpoint_request('),'verified old policy/UUID/HTTP ordering')
 before=doc(root,request['before']);after=report['actual_after_effects'];row=doc(root,after['full29']);permit=doc(root,after['permit_query'])
 need(row==before and row.get('id')==act['record_id']and row.get('slug')==act['slug']and set(row)==set(x['protected_fields']['not_written_fields'])|set(act['changed_fields'])
  and permit.get('actual_rows')==[]and permit.get('exact_count')==0 and _rows(permit.get('actual_native'))==[],'actual unchanged complete row/CAS and successful zero SELECT, no boolean zero-effect grant')
 queried=w._parse_observed_at(permit.get('observed_at'));runs=doc(root,after['publish_runs']);run_at=_run_zero(runs,act['candidate_version'],checked)
 need(queried and end<queried<=now()and end<run_at<=now(),'ordered post-failure zero-effect observations')
 return {'schema':SCHEMA,'task_id':task,'scope':x['business_scope'],'physical_scope':act['scope'],'action_id':act['action_id'],'department':x['executor'],
  'goal_contract':snapshot['goal_contract'],'original_authority':snapshot['goal_delivery']['authorization_pin'],'source_registration':x['registration'],'candidate_version':act['candidate_version'],
  'failure_report':report_pin,'original_issuer_source':issuer_pin,'observer_source':observer_pin,'predecessor_policy_id':pid,'predecessor_policy_sha256':w.sha256_value(policy),
  'predecessor_request':request_pin,'actual_failure_native':fail['actual_native'],'native_command_id':fail['command_id'],'original_failure_end':result['completed_at'],
  'after_effects':{k:after[k]for k in ('permit_query','publish_runs','full29')},'new_policy_or_permit_issued':False,'old_policy_reset_or_reconsumed':False}
def draft_artifact(root,report_pin,issuer_pin):
    import goal_delivery_runtime as g
    from managed_cms_permit_issuer import validate_artifact_run_identity
    report=doc(root,report_pin);task=report.get('task_id');snapshot=g.restore_goal(root,w.read_json(w.snapshot_path(root,task)))
    need(report.get('schema')=='actual-professional-CMS-recovery-instance-artifact-run-name-refusal/v1','actual original artifact-stage failure report')
    request_pin=report.get('new_request');req=doc(root,request_pin);x=src.match(root,snapshot,req)
    need(x and x['operation']=='publish'and all(report.get(k)==req.get(k)for k in ('task_id','scope','department')),'same original professional task/forward role/scope')
    previous=req.get('execution_instance');need(isinstance(previous,dict)and set(previous)=={'recovery_event_id','recovery_source','fresh_effects'}and report.get('new_instance')==previous,'actual failed instance, never caller stage flags')
    prior=source(root,previous['recovery_source']);need(prior['schema']==SCHEMA,'only the original pre-main edge can precede this artifact stage')
    edges=[e for e in recovery_events(root,task)if e['event_id']==previous['recovery_event_id']and event_pin(e)==previous['recovery_source']]
    need(len(edges)==1 and not w.validate_workflow_events(root,task),'real preceding source event')
    pid=report['new_distinct_consumed_policy']['id'];rows=[v for v in w.read_jsonl(Path(root)/w.POLICY_DECISIONS)if v.get('decision_id')==pid]
    need(len(rows)==1 and rows[0]==doc(root,report['new_distinct_consumed_policy']['row']),'one original committed spent artifact instance policy')
    row=rows[0];checked=w._parse_observed_at(row.get('checked_at'))
    need(row.get('execution_instance')==previous and row.get('exact_request')==request_pin and row.get('payload_sha256')==request_pin['sha256']
         and all(row.get(k)==req.get(k)for k in ('task_id','department','action_id','action_class','scope'))
         and row.get('status')=='allow'and row.get('approval_basis')==a.MODE and row.get('approval_status')=='consumed_for_original_exact_autonomous_action'
         and row.get('original_authority')==prior['original_authority']and checked,'original real source, role and consumed authority')
    base=w.sha256_value([req[k]for k in ('task_id','department','action_id','action_class','scope')])
    need(row.get('autonomous_action_key')==w.sha256_value([base,previous['recovery_event_id'],previous['recovery_source']]),'exact failed instance key')
    _fresh(root,previous['fresh_effects'],req,prior,reference=checked)
    preflights=[e for e in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS)if e.get('task_id')==task and e.get('details',{}).get('professional_cms_preflight',{}).get('request')==request_pin]
    need(len(preflights)==1 and preflights[0]['event_id']==report['normal_preflight_event']
         and w._parse_observed_at(preflights[0]['created_at'])<=checked and w._parse_observed_at(edges[0]['created_at'])<=checked,'exact ordered failed normal request/preflight and prior source')
    fail=report['actual_failure'];result=doc(root,fail['normal_issuer_return']);argv=result.get('argv',[]);act=x['action'];preview=report['actual_preview']
    need(len(argv)==15 and argv[1:] == ['tools/managed_cms_permit_issuer.py','--target',act['candidate_version'],'--operation','publish','--dry-run-run-id',str(preview['run']),
         '--github-actor-id',argv[9],'--operations-decision',argv[11],'--policy-decision-id',pid,'--issue-and-dispatch']and str(argv[9]).isdigit(), 'actual exact normal issuer invocation')
    call,text=_failed_native(root,fail['actual_native'],fail['command_id'],x['executor'])
    need(w.safe_path(root,fail['complete_output']['path']).read_bytes()==text.encode()and w.file_digest(root,fail['complete_output']['path'])==fail['complete_output'],'complete unmodified actual failure output')
    lines=[json.loads(v)for v in text.strip().splitlines()];need(lines[-1]==result and result.get('exit_code')==1 and result.get('stdout')==''
         and result.get('stderr')=='BLOCKED_MANAGED_CMS_PERMIT: Dry-run workflow identity or conclusion is invalid\n'
         and any(v.get('exit_code')==0 and json.loads(v.get('stdout')or'{}').get('decision_id')==pid for v in lines[:-1]),'exact actual metadata refusal and preceding consumed result')
    start=w._parse_observed_at(result['started_at']);end=w._parse_observed_at(result['completed_at']);need(checked<=start<end<=now(),'actual policy/failure chronology')
    old=w.safe_path(root,issuer_pin['path']);need(w.file_digest(root,issuer_pin['path'])==issuer_pin and issuer_pin['sha256']==fail['current_source']['sha256'],'original failed source bytes preserved outside mutable runtime')
    code=old.read_text();tree=ast.parse(code);main=next(n for n in tree.body if isinstance(n,ast.FunctionDef)and n.name=='_main');art=next(n for n in tree.body if isinstance(n,ast.FunctionDef)and n.name=='artifact_for_run')
    gates=[n for n in ast.walk(art)if isinstance(n,ast.Call)and isinstance(n.func,ast.Name)and n.func.id=='require'and len(n.args)>1 and isinstance(n.args[1],ast.Constant)and n.args[1].value=='Dry-run workflow identity or conclusion is invalid']
    oldlists=[n for n in ast.walk(art)if isinstance(n,ast.Compare)and isinstance(n.left,ast.Name)and n.left.id=='target_name'and len(n.comparators)==1 and isinstance(n.comparators[0],ast.Set)]
    need(len(gates)==1 and gates[0].lineno<=fail['unique_current_issuer_error_line']<=gates[0].end_lineno and len(oldlists)==1
         and act['candidate_version']not in ast.literal_eval(oldlists[0].comparators[0]),'actual unique old metadata guard and excluded registered target')
    calls=[(ast.unparse(n.func),n.lineno)for n in ast.walk(main)if isinstance(n,ast.Call)]
    positions={name:min(line for name2,line in calls if name2==name)for name in ('artifact_for_run','uuid4','endpoint_request')}
    need(positions['artifact_for_run']<positions['uuid4']<positions['endpoint_request'],'known read-only artifact rejection before UUID/CMS issue; not pre-main or HTTP stage')
    run=doc(root,preview['raw_GH_metadata']);workflow=doc(root,preview['normal_active_workflow']);validate_artifact_run_identity(preview['run'],act['candidate_version'],run,workflow)
    need(run.get('name')==act['candidate_version']+' | dry-run'and run.get('head_sha')==preview['main']and run.get('run_attempt')==preview['attempt']
         and run.get('actor',{}).get('id')==int(argv[9]) and start-dt.timedelta(minutes=30)<=w._parse_observed_at(run.get('updated_at'))<=start,'original successful preview identities/time, not a TTL failure')
    before=doc(root,req['before']);after=report['actual_after_effects'];permit=doc(root,after['permit_lookup']);runs=doc(root,after['publish_runs'])
    need(doc(root,after['full29'])==before and permit.get('actual_rows')==[]and permit.get('exact_count')==0 and _rows(permit.get('actual_native'))==[],'actual unchanged row and authenticated zero permits')
    queried=w._parse_observed_at(permit.get('observed_at'));run_at=_run_zero(runs,act['candidate_version'],checked);need(queried and end<queried<=now()and end<run_at<=now(),'post-failure zero effects, never current freshness')
    return {'schema':PREISSUE_SCHEMA,'failure_stage':'main_artifact_identity_before_UUID_and_CMS_issue','readonly_GitHub_GET_occurred':True,
       **{k:prior[k]for k in ('task_id','scope','physical_scope','action_id','department','goal_contract','original_authority','source_registration','candidate_version')},
       'previous_instance':previous,'reconciled_policy_ids':[prior['predecessor_policy_id'],pid],'failure_report':report_pin,'original_issuer_source':issuer_pin,
       'predecessor_policy_id':pid,'predecessor_policy_sha256':w.sha256_value(row),'predecessor_request':request_pin,'actual_failure_native':fail['actual_native'],
       'native_command_id':fail['command_id'],'original_failure_end':result['completed_at'],'after_effects':{k:after[k]for k in ('permit_lookup','publish_runs','full29')},
       'new_policy_or_permit_issued':False,'old_policy_reset_or_reconsumed':False}
def source(root,pin):
    # Immutable historical derivation only, within one normal request. Current
    # effects/age, policy, instance and final CAS are never cached here.
    context=w._VALIDATION_CONTEXT.get();key=('professional_CMS_failure_source',str(Path(root).resolve()),w.sha256_value(pin))
    if context is None:return _source_uncached(root,pin)
    cache=getattr(context,'_professional_cms_failure_proofs',{});cached=cache.get(key)
    if cached is not None:
        for path,version in cached['dependencies'].items():
            context.bytes(path)
            if context.files[path]['version']!=version:cached=None;break
        if cached is not None:return deepcopy(cached['value'])
    value=_source_uncached(root,pin)
    cache[key]={'value':deepcopy(value),'dependencies':{p:x['version']for p,x in context.files.items()}}
    context._professional_cms_failure_proofs=cache
    return value
def _source_uncached(root,pin):
    value=doc(root,pin);schema=value.get('schema');need(schema in {SCHEMA,PREISSUE_SCHEMA},'known exact failure-stage source')
    derived=draft(root,value.get('failure_report'),value.get('original_issuer_source'))if schema==SCHEMA else draft_artifact(root,value.get('failure_report'),value.get('original_issuer_source'))
    need(value==derived,'immutable authenticated recovery source, not caller flags');return value
def register(root,path):
    import goal_delivery_runtime as g
    pin=w.file_digest(root,path);value=source(root,pin)
    with w.workflow_lock(root):
        events=recovery_events(root,value['task_id']);matches=[e for e in events if source(root,event_pin(e)).get('predecessor_policy_id')==value['predecessor_policy_id']]
        if matches:need(len(matches)==1 and event_pin(matches[0])==pin,'one immutable source for this predecessor');return {'result':'duplicate_ignored','event_id':matches[0]['event_id'],'permit_issued':False}
        previous=latest_event(root,value['task_id'])
        if value['schema']==SCHEMA:need(previous is None,'no unverified additional recovery chain')
        else:need(previous is not None and previous['event_id']==value['previous_instance']['recovery_event_id']and event_pin(previous)==value['previous_instance']['recovery_source'],'exact current prior source, no fork')
        allowed=[p for p in w.read_jsonl(Path(root)/w.POLICY_DECISIONS)if p.get('task_id')==value['task_id']and p.get('action_id')==value['action_id']and p.get('status')=='allow']
        need(len(allowed)==len(ancestors(value))and {v['decision_id']for v in allowed}==set(ancestors(value)),'another issued/unknown policy exists; no new instance')
        snap=g.restore_goal(root,w.read_json(w.snapshot_path(root,value['task_id'])));need(snap.get('current_state')not in w.TERMINAL_STATES,'closed original goal cannot register new recovery')
        event=w.append_workflow_event(root,value['task_id'],snap['current_state'],{EVENT if value['schema']==SCHEMA else PREISSUE_EVENT:pin,'old_policy_unchanged':True,'permit_issued':False})
    return {'result':'recorded','event_id':event['event_id'],'source':pin,'permit_issued':False,'fresh_effects_required':True}
def _fresh(root,value,req,recovery,reference=None):
 reference=now()if reference is None else reference
 effects=doc(root,value);need(effects.get('schema')=='professional-cms-original-key-fresh-zero-effects/v1'
  and all(effects.get(k)==req.get(k)for k in ('task_id','department','action_id','scope'))
  and effects.get('predecessor_policy_id')==recovery['predecessor_policy_id']and effects.get('current_row')==req['before'],'exact fresh original effect namespace and row')
 old=doc(root,recovery['predecessor_request']);need(doc(root,req['before'])==doc(root,old['before']),'complete original row/CAS changed; no recovery')
 permit=doc(root,effects.get('permit_lookup'));query=permit.get('query','');need(query.lstrip().upper().startswith('SELECT ')and 'public.managed_cms_release_permits'in query
  and not re.search(r'\b(?:OR|UNION|INSERT|UPDATE|DELETE|LIMIT)\b|--|/\*',query,re.I)
  and all(re.search(r"\b"+key+r"\s*=\s*'"+re.escape(val)+r"'",query)for key,val in [('task_id',req['task_id']),('action_id',req['action_id']),('record_id',req['object_ids'][0]),('slug',req['slug'])])
  and permit.get('actual_rows')==[]and _rows(permit.get('actual_native'))==[],'actual complete original-key SELECT across policies; unknown/nonzero never qualifies')
 checked=w._parse_observed_at(recovery['original_failure_end']);at=w._parse_observed_at(permit.get('completed_at',permit.get('observed_at')))
 runs=doc(root,effects.get('publish_runs'));run_at=_run_zero(runs,recovery['candidate_version'],checked)
 read=doc(root,effects.get('authenticated_row_read'));oldfacts=doc(root,old['facts']);oldread=doc(root,oldfacts['actual_authenticated_read']);rowtime=w._parse_observed_at(read.get('observed_at'))
 need(read.get('complete_row')==req['before']and read.get('project_id')==oldread.get('project_id')and _rows(doc(root,read.get('actual_native')))==[{'record':doc(root,req['before'])}], 'actual same-project authenticated full-row SELECT')
 need(all(t and checked<t<=reference and (reference-t).total_seconds()<=300 for t in (at,run_at,rowtime)),'fresh permit/run/full-row checks required before new instance; history is not freshness')
 turn,_,output=a.native_execution(root,effects.get('actual_native'),effects.get('command_id'),req['department'])
 need(type(turn.get('startedAt'))in {int,float}and all(t.timestamp()>=turn['startedAt']for t in (at,run_at,rowtime))
  and all(pin['sha256'].encode()in output for pin in (effects['permit_lookup'],effects['publish_runs'],effects['current_row'],effects['authenticated_row_read']))
  and req['task_id'].encode()in output,'real PUB readback command must bind all current files and original task')
 return effects
def instance(root,req):
 value=req.get('execution_instance')
 if value is None:return None
 need(w.read_json(w.snapshot_path(root,req['task_id'])).get('current_state')not in w.TERMINAL_STATES,'closed original goal cannot execute a new instance')
 need(isinstance(value,dict)and set(value)=={'recovery_event_id','recovery_source','fresh_effects'},'only exact registered recovery/source/fresh effects')
 recovery=source(root,value['recovery_source']);need(all(req.get(k)==recovery.get(k)for k in ('task_id','department','action_id','scope')),'original instance task/actor/action/scope')
 events=[e for e in recovery_events(root,req['task_id'])if e.get('event_id')==value['recovery_event_id']and event_pin(e)==value['recovery_source']]
 need(len(events)==1 and not w.validate_workflow_events(root,req['task_id']),'one real append-only recovery edge')
 latest=latest_event(root,req['task_id']);need(latest and latest['event_id']==value['recovery_event_id'],'superseded recovery instance stays spent')
 old=doc(root,recovery['predecessor_request']);need(all(req.get(k)==old.get(k)for k in ('professional_execution_source','business_scope','physical_scope','source_project_id','table','slug','object_ids','changed_fields','operation','desired','expected_updated_at','expected_version')),'same original authorized object/fields/CAS/effect only')
 _fresh(root,value['fresh_effects'],req,recovery)
 issued=[p for p in w.read_jsonl(Path(root)/w.POLICY_DECISIONS)if p.get('task_id')==req['task_id']and p.get('action_id')==req['action_id']and p.get('status')=='allow']
 current=[p for p in issued if p.get('decision_id')not in ancestors(recovery)]
 need({v['decision_id']for v in issued if v['decision_id']in ancestors(recovery)}==set(ancestors(recovery)),'all exact predecessor policies remain committed')
 base=w.sha256_value([req[k]for k in ('task_id','department','action_id','action_class','scope')]);key=w.sha256_value([base,value['recovery_event_id'],value['recovery_source']])
 need(len(current)<=1 and all(p.get('execution_instance')==value and all(p.get(k)==req.get(k)for k in ('task_id','department','action_id','action_class','scope'))
  and p.get('original_authority')==recovery['original_authority']and p.get('approval_basis')==a.MODE
  and p.get('approval_status')=='consumed_for_original_exact_autonomous_action'and p.get('autonomous_action_key')==key
  and isinstance(p.get('exact_request'),dict)and p['exact_request']==w.file_digest(root,p['exact_request']['path'])
  and p.get('payload_sha256')==p['exact_request']['sha256']and doc(root,p['exact_request'])==req for p in current),
  'another issued/unknown/wrong-role instance blocks continuation')
 return value
def verify_policy(root,row):
 req=doc(root,row['exact_request']);events=recovery_events(root,req['task_id'])
 need(not any(source(root,event_pin(e)).get('predecessor_policy_id')==row['decision_id']for e in events),'reconciled predecessor stays spent; never execute/reset/reconsume it')
 value=instance(root,req);need(row.get('execution_instance')==value,'normal consumed policy must bind actual derived instance')
 if value is not None:
  rows=[p for p in w.read_jsonl(Path(root)/w.POLICY_DECISIONS)if p.get('decision_id')==row['decision_id']];need(rows==[row],'actual single policy changed before UUID/HTTP')
 return value
def status(root,task):
 events=recovery_events(root,task)
 if not events:return {'task_id':task,'state':'NOT_REGISTERED','permit_issued':False}
 event=latest_event(root,task);pin=event_pin(event);s=source(root,pin)
 return {'task_id':task,'state':'REGISTERED_SOURCE_ONLY','event_id':event['event_id'],'source':pin,
  'spent_policy_preserved':s['predecessor_policy_id'],'all_spent_policies_preserved':ancestors(s),'failure_stage':s.get('failure_stage','pre_main_import'),'execution_instance':{'recovery_event_id':event['event_id'],'recovery_source':pin,'fresh_effects':'ACTUAL_FRESH_EFFECTS_PIN_REQUIRED'},
  'fresh_effects_schema':{'schema':'professional-cms-original-key-fresh-zero-effects/v1',**{k:s[k]for k in ('task_id','department','action_id','scope')},'predecessor_policy_id':s['predecessor_policy_id']},
  'fresh_effects_required_pins':['current_row','permit_lookup','publish_runs','authenticated_row_read','actual_native'],
  'fresh_effects_command_id':'real successful same-project PUB hash/readback command; complete output binds all four files and original task',
  'sequence':'fresh original-key SELECT/native zero, complete row/CAS and workflow readback; add execution_instance before intent/four-doc hashes; normal new preflight/readiness and distinct policy once; issuer only by original PUB',
  'historical_preview_is_not_future_freshness':True,'permit_issued':False,'old_policy_reset_or_reconsumed':False}
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('command',choices=['draft','draft-artifact','record','status']);p.add_argument('--failure-report');p.add_argument('--issuer-source');p.add_argument('--input');p.add_argument('--output');p.add_argument('--task-id');args=p.parse_args();root=Path(__file__).resolve().parents[1]
 try:
  if args.command in {'draft','draft-artifact'}:
   result=(draft if args.command=='draft'else draft_artifact)(root,w.file_digest(root,args.failure_report),w.file_digest(root,args.issuer_source));need(args.output,'new project-local immutable output required');q=w.safe_path(root,args.output);need(not q.exists(),'preserve prior recovery source');w.atomic_write_json(q,result);result={'source':w.file_digest(root,args.output),'permit_issued':False}
  elif args.command=='record':result=register(root,args.input)
  else:result=status(root,w.validate_task_id(args.task_id))
  print(json.dumps(result,ensure_ascii=False,indent=2))
 except (w.WorkflowError,ValueError,KeyError,OSError,TypeError)as e:p.exit(1,str(e)+'\n')
