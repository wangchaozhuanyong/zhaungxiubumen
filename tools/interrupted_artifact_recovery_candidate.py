"""Local-only candidate: derive an interrupted artifact-stage source.

No registry/event writer, endpoint, SQL connection, permit or executable
instance is provided. The existing recovery protocol must separately admit a
source, recheck fresh effects and issue its own single-use policy.
"""
from pathlib import Path
import ast,datetime as dt,json,re,shlex
import workflow_control as w
import department_autonomy as a
import goal_delivery_runtime as g
import professional_cms_execution as src
import professional_cms_pre_main_recovery as old

SCHEMA='professional-cms-interrupted-artifact-local-evidence/v1'
RESULT='professional-cms-interrupted-artifact-local-source-candidate/v1'
FIELDS={'schema','failure_report','request','policy','issuer_source','issuer_source_native',
        'issuer_source_command_id','failure_native','failure_command_id','fresh_effects'}

def need(ok,msg):
 if not ok:raise w.WorkflowError('interrupted artifact candidate: '+msg)

def command_words(command):
 parts=shlex.split(command)
 if len(parts)==3 and parts[0] in ('/bin/zsh','zsh','/bin/bash','bash') and parts[1]=='-lc':parts=shlex.split(parts[2])
 while parts and re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*=.*',parts[0]):
  need(parts[0].startswith('SUPABASE_URL=https://') and len(parts[0].split('=',1)[1])>8,'only original fixed endpoint environment')
  parts.pop(0)
 return parts

def _native_failed(root,pin,command,role):
 page=g._native_document(root,pin);fixed=w.department_registry(root)[role]['chat_binding'];thread=page.get('thread',{})
 need(all(thread.get(k)==fixed[v] for k,v in {'id':'task_id','title':'title','cwd':'cwd'}.items()) and fixed.get('project_id')==a.PROJECT,'original fixed role/project/directory')
 hits=[(t,c) for t in page.get('turns',[]) for c in t.get('items',[]) if c.get('id')==command]
 need(len(hits)==1,'one original native failed invocation');turn,call=hits[0];out=call.get('output')
 need(turn.get('status')=='completed' and not turn.get('error') and type(turn.get('startedAt')) in (int,float) and type(turn.get('completedAt')) in (int,float)
      and turn['startedAt']<=turn['completedAt']<=dt.datetime.now(dt.timezone.utc).timestamp()
      and call.get('type')=='commandExecution' and call.get('status')=='failed' and call.get('exitCode')==130
      and Path(call.get('cwd','')).resolve()==Path(root).resolve() and isinstance(out,dict)
      and out.get('truncated') is False and isinstance(out.get('text'),str),'complete real original interrupted command')
 return turn,call,out['text']

def _all_policy_query(query, req):
    """Only an exhaustive exact namespace, with no policy/status/time filter."""
    match=re.fullmatch(r"\s*SELECT\s+\*\s+FROM\s+public\.managed_cms_release_permits\s+WHERE\s+(.+?)\s*;?\s*",query,re.I)
    need(match is not None,'canonical complete permit query required')
    pairs=re.split(r'\s+AND\s+',match.group(1),flags=re.I);found={}
    for term in pairs:
        m=re.fullmatch(r"\s*(task_id|action_id|record_id|slug)\s*=\s*'([A-Za-z0-9_.:/-]+)'\s*",term,re.I)
        need(m is not None and m.group(1).lower() not in found,'no extra, duplicate or policy-filtering clauses')
        found[m.group(1).lower()]=m.group(2)
    need(found=={'task_id':req['task_id'],'action_id':req['action_id'],'record_id':req['object_ids'][0],'slug':req['slug']},'full original key across all policies required')
    return True

def _native_turn(root,pin,role,call_id):
    page=g._native_document(root,pin);fixed=w.department_registry(root)[role]['chat_binding'];thread=page.get('thread',{})
    need(all(thread.get(k)==fixed[v] for k,v in {'id':'task_id','title':'title','cwd':'cwd'}.items()) and fixed.get('project_id')==a.PROJECT,'exact original publisher native identity')
    pairs=[(t,c) for t in page.get('turns',[]) for c in t.get('items',[]) if c.get('id')==call_id]
    need(len(pairs)==1 and pairs[0][0].get('status')=='completed' and not pairs[0][0].get('error'),'one completed original publisher call')
    return pairs[0]

def _effect_native_sources(root,effects,req,repository,failure_end):
    from en2_supabase_origin import _provider_result
    permit=a.document(root,effects['permit_lookup']);query=permit.get('query','');_all_policy_query(query,req)
    turn,call=_native_turn(root,effects['permit_query_native'],'publishing',effects['permit_query_call_id']);args=call.get('arguments')
    oldreq=a.document(root,req['facts']);oldread=a.document(root,oldreq['actual_authenticated_read'])
    need(call.get('type')=='mcpToolCall' and call.get('server')=='codex_apps' and call.get('tool')=='supabase.execute_sql'
         and call.get('status')=='completed' and not call.get('error') and isinstance(args,dict)
         and set(args)=={'project_id','query'} and args['project_id']==oldread.get('project_id')
         and args['query']==query and _provider_result(call)==[] and old._rows(permit['actual_native'])==[],
         'actual complete same-project unfiltered first-party permit query required')
    rowread=a.document(root,effects['authenticated_row_read']);row=a.document(root,req['before'])
    table=req.get('table');record=req['object_ids'][0];slug=req['slug']
    need(isinstance(table,str) and re.fullmatch(r'[a-z_]+',table) and re.fullmatch(r'[A-Za-z0-9_.:/-]+',record)
         and re.fullmatch(r'[A-Za-z0-9_.:/-]+',slug),'valid original record identity')
    row_query="SELECT row_to_json(t) AS record FROM (SELECT * FROM public."+table+" WHERE id='"+record+"' AND slug='"+slug+"') t;"
    rturn,readcall=_native_turn(root,effects['row_query_native'],'publishing',effects['row_query_call_id']);rargs=readcall.get('arguments')
    need(readcall.get('type')=='mcpToolCall' and readcall.get('server')=='codex_apps' and readcall.get('tool')=='supabase.execute_sql'
         and readcall.get('status')=='completed' and not readcall.get('error') and isinstance(rargs,dict)
         and set(rargs)=={'project_id','query'} and rargs['project_id']==oldread.get('project_id')
         and rargs['query']==row_query and rowread.get('query')==row_query
         and _provider_result(readcall)==[{'record':row}] and old._rows(a.document(root,rowread['actual_native']))==[{'record':row}],
         'actual complete same-project native full-row query and raw CAS required')
    runs=a.document(root,effects['publish_runs']);rt,rc=_native_turn(root,effects['run_history_native'],'publishing',effects['run_history_command_id'])
    expected=['gh','api','--paginate','--slurp','repos/'+repository+'/actions/workflows/content-publish-approved.yml/runs?per_page=100']
    need(rc.get('type')=='commandExecution' and rc.get('status')=='completed' and rc.get('exitCode')==0
         and Path(rc.get('cwd','')).resolve()==Path(root).resolve() and command_words(rc.get('command',''))==expected,
         'actual unfiltered paginated workflow history command required')
    output=rc.get('output');need(isinstance(output,dict) and output.get('truncated') is False and isinstance(output.get('text'),str),'complete workflow output required')
    pages=json.loads(output['text']);need(isinstance(pages,list) and pages and all(isinstance(p,dict) and type(p.get('total_count')) is int and isinstance(p.get('workflow_runs'),list) for p in pages),'complete workflow pages required')
    flat=[row for page in pages for row in page['workflow_runs']];total=pages[0]['total_count']
    need(all(p['total_count']==total for p in pages) and total==len(flat) and len({x.get('id') for x in flat})==len(flat)
         and all(type(x.get('id')) is int and isinstance(x.get('display_title'),str) and isinstance(x.get('created_at'),str) for x in flat),
         'all workflow pages and unique IDs required, no first-page zero inference')
    observed=[{'displayTitle':x['display_title'],'createdAt':x['created_at']} for x in flat]
    need(runs.get('actual_all_runs')==observed,'exact actual full workflow history, not caller summary')
    now=dt.datetime.now(dt.timezone.utc);failed=w._parse_observed_at(failure_end)
    for source, actual_turn in ((permit,turn),(rowread,rturn),(runs,rt)):
        observed_at=w._parse_observed_at(source.get('completed_at',source.get('observed_at')))
        start=actual_turn.get('startedAt');end=actual_turn.get('completedAt')
        need(failed and observed_at and type(start) in (int,float) and type(end) in (int,float)
             and failed<observed_at<=now and 0<=(now-observed_at).total_seconds()<=300
             and start<=observed_at.timestamp()<=end<=now.timestamp(),
             'actual native read timing after failure and within 300 seconds required')
    return True


def _metadata_checksum(call,output,expected):
 """Accept only the exact historic two-file checksum, never a shell program."""
 parts=shlex.split(call.get('command',''))
 if len(parts)==3 and parts[0] in ('/bin/zsh','zsh','/bin/bash','bash') and parts[1]=='-lc':
  parts=shlex.split(parts[2])
 targets=['tools/en2_forward_issuer.py','tools/managed_cms_permit_issuer.py']
 need(parts==['shasum','-a','256',*targets],'exact original two-file checksum command required')
 try:text=output.decode('utf-8')
 except (AttributeError,UnicodeDecodeError) as exc:raise w.WorkflowError('interrupted artifact candidate: complete checksum UTF8 required') from exc
 lines=text.splitlines()
 need(len(lines)==2 and all(re.fullmatch(r'[0-9a-f]{64}  '+re.escape(target),line) for target,line in zip(targets,lines))
      and lines[1][:64]==expected,'two unique exact output paths and original issuer digest required')
 return True

def _common(root,item,fields,*,metadata_only=False):
 root=Path(root).resolve();need(isinstance(item,dict) and set(item)==fields and item.get('schema')==SCHEMA,'exact evidence fields required')
 report=a.document(root,item['failure_report']);req=a.document(root,item['request']);policy=a.document(root,item['policy'])
 task=req.get('task_id');snapshot=g.restore_goal(root,w.read_json(w.snapshot_path(root,task)));match=src.match(root,snapshot,req)
 need(match and match.get('operation')=='publish' and req.get('department')==match.get('executor')=='publishing'
      and req.get('task_id')==report.get('task_id') and req.get('action_id')==report.get('action_id')
      and report.get('object')==req.get('table','')+'/'+str(req.get('object_ids',[''])[0])
      and set(report.get('fields',[]))==set(req.get('changed_fields',[]))
      and req.get('candidate_version')==match.get('action',{}).get('candidate_version')
      and req.get('professional_execution_source')==match.get('registration')
      and req.get('execution_instance') is None,'same original publisher/task/object/candidate/source')
 policy_rows=w.read_jsonl(root/w.POLICY_DECISIONS)
 rows=[p for p in policy_rows if p.get('decision_id')==policy.get('decision_id')]
 allowed=[p for p in policy_rows if p.get('task_id')==req.get('task_id') and p.get('action_id')==req.get('action_id') and p.get('status')=='allow']
 need(len(allowed)==1 and allowed[0]==policy,'another allow or unknown execution blocks a new candidate')
 need(len(rows)==1 and rows[0]==policy and report.get('policy',{}).get('id')==policy.get('decision_id')
      and policy.get('status')=='allow' and policy.get('approval_status')=='consumed_for_original_exact_autonomous_action'
      and policy.get('approval_basis')==a.MODE and policy.get('exact_request')==item['request']
      and policy.get('payload_sha256')==item['request']['sha256']
      and policy.get('original_authority')==snapshot.get('goal_delivery',{}).get('authorization_pin')
      and isinstance(policy.get('original_authority'),dict)
      and all(policy.get(k)==req.get(k) for k in ('task_id','department','action_id','scope','action_class')),
      'exact original spent policy and immutable request required')
 need(not old.recovery_events(root,task) and not w.validate_workflow_events(root,task),
      'no duplicate or unverified recovery; intact event chain required')
 source_pin=item['issuer_source'];need(w.file_digest(root,source_pin['path'])==source_pin,'immutable original issuer bytes')
 capture_turn,capture_call,capture_output=a.native_execution(root,item['issuer_source_native'],item['issuer_source_command_id'],'publishing')
 need(capture_call.get('status')=='completed' and capture_call.get('exitCode')==0 and not capture_turn.get('error'), 'successful original source-capture command')
 single=(command_words(capture_call.get('command',''))==['shasum','-a','256','tools/managed_cms_permit_issuer.py'] and capture_output.decode('utf-8').strip()==source_pin['sha256']+'  tools/managed_cms_permit_issuer.py')
 if not single:
  need(metadata_only,'original executable recovery requires strict single-source capture')
  _metadata_checksum(capture_call,capture_output,source_pin['sha256'])
 tree=ast.parse(w.safe_path(root,source_pin['path']).read_text());main=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='_main')
 repos=[ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and len(n.targets)==1 and isinstance(n.targets[0],ast.Name) and n.targets[0].id=='REPOSITORY']
 hosts=[ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and len(n.targets)==1 and isinstance(n.targets[0],ast.Name) and n.targets[0].id=='SUPABASE_HOST']
 need(len(hosts)==1 and isinstance(hosts[0],str) and re.fullmatch(r'[a-z0-9]+\.supabase\.co',hosts[0]),'actual original issuer endpoint source')
 need(len(repos)==1 and isinstance(repos[0],str) and re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',repos[0]),'actual original issuer repository source')
 calls=[(ast.unparse(n.func),n.lineno) for n in ast.walk(main) if isinstance(n,ast.Call)]
 artifacts=[n for name,n in calls if name=='artifact_for_run'];issues=[n for name,n in calls if name=='endpoint_request']
 need(len(artifacts)==1 and issues and artifacts[0]<min(issues),'immutable issuer call ordering')
 turn,call,text=_native_failed(root,item['failure_native'],item['failure_command_id'],'publishing')
 need(capture_turn.get('status')=='completed' and type(capture_turn.get('completedAt')) in (int,float) and capture_turn['completedAt']<=turn['startedAt'], 'actual source capture predates failure')
 outer=shlex.split(call['command']);inner=shlex.split(outer[2]) if len(outer)==3 and outer[0] in ('/bin/zsh','zsh','/bin/bash','bash') and outer[1]=='-lc' else outer
 env=[x for x in inner if x.startswith('SUPABASE_URL=')]
 need(env==['SUPABASE_URL=https://'+hosts[0]],'actual original issuer target endpoint required')
 parts=command_words(call['command']);need(len(parts)==15 and (parts[0]=='python3' or Path(parts[0]).resolve() in {Path('/usr/bin/python3').resolve(),(Path.home()/'.local/bin/python3.11').resolve()}) and parts[1]=='tools/managed_cms_permit_issuer.py' and parts[-1]=='--issue-and-dispatch','exact documented original issuer command')
 flags=parts[2:-1];need(len(flags)==12 and len(set(flags[::2]))==6,'six unique exact issuer options')
 opts=dict(zip(flags[::2],flags[1::2]));need(set(opts)=={'--target','--operation','--dry-run-run-id','--operations-decision','--policy-decision-id','--github-actor-id'} and opts['--github-actor-id'].isdigit() and int(opts['--github-actor-id'])>0 and opts['--target']==req['candidate_version'] and opts['--operation']=='publish' and opts['--policy-decision-id']==policy['decision_id'] and opts['--dry-run-run-id']==str(report.get('preview_run')) and opts['--operations-decision']==report.get('readiness',{}).get('path'),'exact original target/preview/readiness/policy')
 frames=re.findall(r'File "([^"]+)", line (\d+), in ([^\n]+)',text)
 need(text.rstrip().endswith('KeyboardInterrupt') and any(name=='artifact_for_run' for _,_,name in frames) and any(name=='validate_workflow_events' for _,_,name in frames) and not any(name=='endpoint_request' for _,_,name in frames),'only observed interrupted artifact catalog stack; never infer remote zero')
 ended=dt.datetime.fromtimestamp(turn['completedAt'],dt.timezone.utc).isoformat();recovery={'task_id':task,'department':req['department'],'action_id':req['action_id'],'scope':req['scope'],'candidate_version':req['candidate_version'],'predecessor_policy_id':policy['decision_id'],'predecessor_request':item['request'],'original_failure_end':ended}
 return req,policy,source_pin,recovery,ended,repos[0]

def draft_metadata(root,item):
 req,policy,source_pin,recovery,ended,repository=_common(root,item,FIELDS-{'fresh_effects'},metadata_only=True)
 return {'schema':'professional-cms-interrupted-artifact-metadata-source/v1',
  'evidence':item,'task_id':req['task_id'],'scope':req['scope'],'department':req['department'],
  'action_id':req['action_id'],'candidate_version':req['candidate_version'],
  'object':{'table':req['table'],'id':req['object_ids'][0],'slug':req['slug'],'fields':req['changed_fields']},
  'predecessor_policy_id':policy['decision_id'],'predecessor_request':item['request'],
  'original_failure_end':ended,'issuer_source':source_pin,'issuer_source_time_semantics':'prior checksum only; failure-moment bytes unproven','effect_state':'UNKNOWN',
  'dependency_owner':'publishing','required_next_evidence':['complete original-key across-policy permit read',
   'complete original workflow history','fresh authenticated full-row/CAS'],
  'permission_issued':False,'execution_instance_created':False,'actual_action_allowed':False}

def draft(root,item):
 req,policy,source_pin,recovery,ended,repository=_common(root,item,FIELDS)
 task=req['task_id']
 # This validates fresh cross-policy permit rows, full run-window coverage,
 # same-row actual response/native chronology and unknown-effect rejection.
 effects=a.document(root,item['fresh_effects'])
 row_read=a.document(root,effects.get('authenticated_row_read'))
 need(isinstance(row_read.get('actual_native'),dict),'actual fresh same-row native proof required')
 _effect_native_sources(root,effects,req,repository,ended)
 old._fresh(root,item['fresh_effects'],req,recovery)
 return {'schema':RESULT,'task_id':task,'action_id':req['action_id'],'candidate_version':req['candidate_version'],'predecessor_policy_id':policy['decision_id'],'failure_native':item['failure_native'],'issuer_source':source_pin,'fresh_effects':item['fresh_effects'],'permission_issued':False,'event_recorded':False,'execution_instance_created':False,'actual_action_allowed':False,'requires_normal_registered_recovery_and_fresh_gates':True}
