"""Original WEB's bounded R3 binding carrier. No token handling or environment review.

GitHub variables have no conditional-write API. The original sole WEB executor is
serialized locally, reads both effective levels twice, appends one binding without
discarding entries, and verifies the complete result. This is NOT server CAS.
Uncontrolled concurrent remote editors remain outside that local serialization.
"""
from pathlib import Path
import argparse,contextlib,datetime as dt,fcntl,hashlib,json,re,shutil,subprocess
import workflow_control as w
import department_autonomy as a
import professional_web_execution as web
VARIABLE='R3_RELEASE_APPROVAL_ALLOWLIST_JSON'
ENV='production-supabase'
FIELDS=('version','taskId','actionId','actionClass','scope','approvalId','expectedSha',
 'repository','repositoryId','ref','workflowRef','environment','eventName','runId',
 'runAttempt','singleUse','status','issuedAt','expiresAt')
def need(ok,message):web.need(ok,'R3 transport: '+message)
def timestamp():return dt.datetime.now(dt.timezone.utc)
def digest(value):return hashlib.sha256(json.dumps(value,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
def validate_binding(b,now=None,current=True,own=False):
 now=now or timestamp();need(isinstance(b,dict)and set(b)==set(FIELDS)|{'payloadSha256'},'exact binding schema')
 need(b['version']=='r3-release-approval/v1'and b['actionClass']=='site_publish'
  and re.fullmatch(r'fc-\d{8}-[a-z0-9-]+',str(b['taskId']))
  and re.fullmatch(r'[a-z0-9][a-z0-9-]{2,120}',str(b['actionId']))
  and re.fullmatch(r'company\.example:[^*\s]+',str(b['scope']))
  and re.fullmatch(r'apr-[0-9a-f]{20}',str(b['approvalId']))
  and re.fullmatch('[0-9a-f]{40}',str(b['expectedSha'])),'exact original task/action/scope/reference/head')
 need(re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',str(b['repository']))
  and str(b['repositoryId']).isdigit()and b['ref']=='refs/heads/main'
  and b['workflowRef']==b['repository']+'/'+web.R3+'@refs/heads/main'
  and b['environment']==ENV and b['eventName']=='workflow_dispatch'
  and str(b['runId']).isdigit()and b['runAttempt']==1
  and b['singleUse']is True and b['status']=='active','original protected workflow/environment/first single run')
 start=w._parse_observed_at(b['issuedAt']);end=w._parse_observed_at(b['expiresAt'])
 need(start and end and 0<(end-start).total_seconds()<=(900 if own else 1800),'real original short validity; never extend timestamps')
 if current:need(start<=now<end,'binding not currently valid; original issuer must not reuse/extend expired reference')
 need(b['payloadSha256']==digest({k:b[k]for k in FIELDS}),'original canonical platform digest')
 return b

def context(root,task,approval=None,effect=False):
 sources=web.records(root,task);need(len(sources)==1,'one real registered original external WEB source');ctx=sources[0]
 if approval is None:return ctx,None,None
 row=w.effective_approvals(root).get(approval);need(row and row.get('task_id')==task
  and row.get('approval_basis')=='verified_original_goal_external_WEB_source_v1'
  and row.get('original_human_authorization_pin')==ctx['authorization']
  and row.get('delegated_HQ_decision')==ctx['decision']and row.get('execution_department')==ctx['role'],
  'real normal own issuer ledger source, not expected reference or caller binding')
 b=validate_binding(row.get('platform_binding'),current=effect,own=True)
 need(row['approval_id']==b['approvalId']==approval and row.get('action_id')==b['actionId']
  and row.get('scope')==b['scope']==ctx['edge_scope']and b['repository']==ctx['repository']
  and b['taskId']==task,'exact original issuer/task/action/repository/scope')
 envelope=a.document(root,row.get('source_preflight'));req=a.document(root,envelope.get('request'))
 need(req.get('department')==ctx['role']and req.get('operation')=='edge_deploy'
  and req.get('action_id')==b['actionId']and req.get('scope')==b['scope']
  and req.get('state',{}).get('main_sha')==b['expectedSha']
  and str(req['state'].get('r3_run',{}).get('id'))==str(b['runId'])
  and web.reference(ctx,req['state']['candidate_commit'],b['expectedSha'])==approval,
  'unchanged real own preflight/main/run/source; no relabelled binding')
 if effect:
  need(row['status']=='active','actual local reference consumed/revoked; no reissue')
  item,actual,source,_=web.preflight(root,task,b['actionId'],'site_publish',b['scope'],ctx['role'])
  need(source==row['source_preflight']and actual==req,'latest own normal preflight and actual WEB source')
  observed=w._parse_observed_at(req.get('observed_at'));need(observed and 0<=(timestamp()-observed).total_seconds()<=300,'fresh actual WEB facts before transport')
  need(Path.cwd().resolve()==Path(ctx['worktree']).resolve(),'platform mutation only from original WEB worktree; SYS does not execute this')
 return ctx,row,req

class GitHubError(RuntimeError):pass
class GitHub:
 def __init__(self,ctx,before_write=None):self.ctx=ctx;self.before_write=before_write;self.cli=shutil.which('gh');need(self.cli,'original existing GitHub CLI required; do not install/authenticate a substitute')
 def call(self,method,path,value=None):
  repo=self.ctx['repository'];base='repos/'+repo
  allowed=method=='GET'and(path=='user'or path==base or path==base+'/git/ref/heads/main'
   or path==base+'/environments/'+ENV or re.fullmatch(re.escape(base)+r'/actions/runs/\d+(?:/pending_deployments)?',path)
   or path in {base+'/actions/variables?per_page=100',base+'/environments/'+ENV+'/variables?per_page=100'})
  variable_paths={base+'/actions/variables/'+VARIABLE,base+'/environments/'+ENV+'/variables/'+VARIABLE}
  allowed=allowed or method=='PATCH'and path in variable_paths or method=='POST'and path==base+'/environments/'+ENV+'/variables'
  need(allowed,'no arbitrary API/variable/reviewer/account/host operations')
  if method!='GET':
   need(isinstance(value,dict)and set(value)=={'name','value'}and value['name']==VARIABLE,'only the bounded existing variable payload')
   need(self.before_write is not None,'normal actual own issuer context required; no raw adapter mutation')
   self.before_write()
  argv=[self.cli,'api','--hostname','github.com','--method',method,path,'-H','Accept: application/vnd.github+json','-H','X-GitHub-Api-Version: 2022-11-28']
  if value is not None:argv+=['--input','-']
  try:p=subprocess.run(argv,input=json.dumps(value)if value is not None else None,capture_output=True,text=True,timeout=25,cwd=self.ctx['worktree'])
  except (OSError,subprocess.TimeoutExpired)as e:raise GitHubError('original GitHub transport failed/unknown; no replay')from e
  if p.returncode:
   match=re.search(r'HTTP\s+(\d{3})',p.stderr)
   raise GitHubError('GitHub '+method+' failed'+(' HTTP'+match[1]if match else' (status unknown)'))
  if not p.stdout.strip():return None
  try:return json.loads(p.stdout)
  except ValueError as e:raise GitHubError('complete GitHub JSON response required; effect unknown')from e

def levels(api,ctx):
 base='repos/'+ctx['repository'];out={}
 for level,path in [('repository',base+'/actions/variables'),('environment',base+'/environments/'+ENV+'/variables')]:
  # Pagination cannot silently hide the exact variable.
  value=api.call('GET',path+'?per_page=100')
  need(type(value.get('total_count'))is int and value['total_count']<=len(value.get('variables',[])),'complete variables listing required; missing/ambiguous is not zero')
  selected=[x for x in value['variables']if x.get('name')==VARIABLE];need(len(selected)<=1,'ambiguous exact platform variable')
  row=selected[0]if selected else None
  if row is not None:
   need(set(row)>={'name','value','created_at','updated_at'},'real variable value and native timestamps')
   try:entries=json.loads(row['value'])
   except (TypeError,ValueError):need(False,'existing variable malformed; preserve it')
   need(isinstance(entries,list)and len(entries)<=20,'bounded existing array, no replacement default')
  else:entries=[]
  out[level]={'path':path,'exists':row is not None,'entries':entries,'updated_at':row.get('updated_at')if row else None,'raw_sha256':hashlib.sha256(row['value'].encode()).hexdigest()if row else None}
 return out

def platform_facts(api,ctx,run_id,req=None,pending=True):
 base='repos/'+ctx['repository'];user=api.call('GET','user');repo=api.call('GET',base);run=api.call('GET',base+'/actions/runs/'+str(run_id));environment=api.call('GET',base+'/environments/'+ENV)
 need(user.get('login')==ctx['repository'].split('/')[0]and repo.get('full_name')==ctx['repository']and repo.get('id')==1248188229,'same actual original account/repository only')
 need(run.get('id')==int(run_id)and run.get('run_attempt')==1 and run.get('event')=='workflow_dispatch'
  and run.get('path')==web.R3 and run.get('head_branch')=='main'
  and run.get('repository',{}).get('id')==repo['id']and run.get('repository',{}).get('full_name')==ctx['repository']
  and run.get('actor',{}).get('id')==user.get('id'),'same actual run/first attempt/source workflow/actor')
 need(environment.get('name')==ENV and any(x.get('type')=='required_reviewers'and x.get('reviewers')for x in environment.get('protection_rules',[]))
  and environment.get('deployment_branch_policy',{}).get('protected_branches')is True
  and environment.get('deployment_branch_policy',{}).get('custom_branch_policies')is False,'original environment reviewer/branch protections unchanged')
 if req:
  need(run.get('head_sha')==req['state']['main_sha']and user.get('id')==req['state']['actor']['id'],'current original request actor/main/run')
 if pending:
  need(run.get('status')in {'queued','in_progress','waiting','pending'}and run.get('conclusion')is None,'existing run no longer pending; read its effect, do not dispatch another')
  main=api.call('GET',base+'/git/ref/heads/main');need(main.get('object',{}).get('sha')==run.get('head_sha'),'fresh actual remote main changed; preserve existing run and assess real delta')
  matches=[x for x in api.call('GET',base+'/actions/runs/'+str(run_id)+'/pending_deployments')if x.get('environment',{}).get('name')==ENV]
  need(len(matches)==1 and matches[0].get('current_user_can_approve')is True,'original actor actual pending protected environment review capability required')
 return {'actor':{'login':user['login'],'id':user['id']},'repository':ctx['repository'],'run_id':run['id'],'run_attempt':run['run_attempt'],'head':run['head_sha'],'run_status':run['status'],'run_conclusion':run.get('conclusion'),'environment':ENV,'review_performed':False}

def proposal(before,binding,now=None):
 validate_binding(binding,now,own=True)
 level='environment'if before['environment']['exists']or not before['repository']['exists']else'repository';row=before[level];entries=row['entries']
 for b in entries:validate_binding(b,now)
 exact=[b for b in entries if b['approvalId']==binding['approvalId']]
 if exact:
  need(len(exact)==1 and exact[0]==binding,'same reference differs; never overwrite/refresh it')
  return level,entries,True
 need(not any((b['taskId'],b['actionId'],str(b['runId']))==(binding['taskId'],binding['actionId'],str(binding['runId']))for b in entries),'conflicting original run/action binding, preserve existing entry')
 need(len(entries)<20,'existing guard capacity reached; no pruning other issuers')
 return level,[*entries,binding],False

@contextlib.contextmanager
def serialized(root,ctx):
 path=Path(root)/'logs/approvals'/('R3-platform-transport-'+hashlib.sha256((ctx['repository']+VARIABLE).encode()).hexdigest()[:20]+'.lock');path.parent.mkdir(parents=True,exist_ok=True)
 with path.open('a')as f:
  fcntl.flock(f,fcntl.LOCK_EX)
  try:yield
  finally:fcntl.flock(f,fcntl.LOCK_UN)

def transfer(api,ctx,binding,directory):
 """External I/O adapter can be simulated; all planner validators stay real."""
 directory=Path(directory);attempt=directory/'attempt.json';before=levels(api,ctx);level,after,duplicate=proposal(before,binding)
 if duplicate:
  if attempt.exists():
   original=w.read_json(directory/'intent.json');need(original['binding']==binding and original['target_level']==level
    and all(b in before[level]['entries']for b in original['before'][level]['entries']),
    'own echo exists but original other entries differ; unknown concurrent effect, no replay')
  return {'state':'EXACT_BINDING_ALREADY_PRESENT','new_write':False,'approval_id':binding['approvalId'],'effective_level':level}
 if attempt.exists():return {'state':'UNKNOWN_PRIOR_WRITE_EFFECT_NO_RETRY','new_write':False,'approval_id':binding['approvalId'],'next':'read original variable/run/source; never reissue from missing echo'}
 again=levels(api,ctx);need(again==before,'fresh native variable bytes/timestamps changed; no write');validate_binding(binding,own=True)
 directory.mkdir(parents=True,exist_ok=True);intent={'binding':binding,'before':before,'target_level':level,'after_sha256':digest(after),'server_CAS_available':False,'local_serialization_only':True,'at':timestamp().isoformat()}
 if (directory/'intent.json').exists():
  old=w.read_json(directory/'intent.json');need(all(old[k]==intent[k]for k in ('binding','before','target_level','after_sha256')),'unattempted original intent drifted; preserve it')
 else:w.atomic_write_json(directory/'intent.json',intent)
 w.atomic_write_json(attempt,{'state':'mutation_intent_durable','at':timestamp().isoformat(),'attempts':1})
 row=before[level];path=row['path']+'/'+VARIABLE if row['exists']else row['path'];method='PATCH'if row['exists']else'POST'
 try:
  api.call(method,path,{'name':VARIABLE,'value':json.dumps(after,ensure_ascii=False,separators=(',',':'))})
  actual=levels(api,ctx);effective='environment'if actual['environment']['exists']else'repository'
  need(effective==level and actual[level]['entries']==after,'write readback differs/unknown; no restore, overwrite or retry')
  other='repository'if level=='environment'else'environment';need(actual[other]==before[other],'other variable level changed; preserve unknown concurrent effect')
  proposal(actual,binding)
  result={'state':'TRANSPORTED_AND_READ_BACK','approval_id':binding['approvalId'],'new_write':True,'effective_level':level,'preserved_other_entries':len(after)-1,'server_CAS_available':False,'external_edit_race_not_atomic':True,'environment_review_performed':False}
 except (GitHubError,w.WorkflowError,OSError)as e:
  result={'state':'UNKNOWN_WRITE_EFFECT_NO_RETRY','approval_id':binding['approvalId'],'new_write':'UNKNOWN','error_class':type(e).__name__,'safe_error':str(e)if isinstance(e,GitHubError)else'original guard/readback or local evidence error; inspect original state','next':'status original key first; never resend or reset attempt'}
 w.append_jsonl_locked(directory/'readback.jsonl',{**result,'at':timestamp().isoformat()});return result

def inspect(root,task,run_id):
 ctx,_,_=context(root,task);api=GitHub(ctx);facts=platform_facts(api,ctx,run_id);before=levels(api,ctx)
 active=before['environment']if before['environment']['exists']else before['repository']
 for b in active['entries']:validate_binding(b)
 need(len(active['entries'])<20,'original variable capacity; no short token until capacity is real')
 return {'state':'READONLY_CHANNEL_AND_REVIEW_PRECONDITIONS_VERIFIED','facts':facts,'effective_binding_count':len(active['entries']),'variable_exists':active['exists'],'write_permission_not_probed':True,'approval_issued':False,'next':'only original WEB now refreshes facts/normal preflight and issues one short reference, then install; SYS never performs platform mutation','server_CAS_available':False}

def install(root,task,approval):
 ctx,row,req=context(root,task,approval,effect=True);binding=row['platform_binding']
 def before_write():
  current=w.effective_approvals(root).get(approval);need(current==row and current.get('status')=='active','normal own reference changed/consumed/revoked; no transport')
  validate_binding(binding,own=True);at=w._parse_observed_at(req['observed_at']);need(at and 0<=(timestamp()-at).total_seconds()<=300,'fresh facts expired before actual transport')
  need(w.read_json(w.snapshot_path(root,task)).get('current_state')not in w.TERMINAL_STATES,'original task is terminal; no platform mutation')
  need(Path.cwd().resolve()==Path(ctx['worktree']).resolve(),'same original WEB worktree at actual transport');web.working_source(ctx,req['state']['candidate_commit'])
 api=GitHub(ctx,before_write)
 with serialized(root,ctx):
  facts=platform_facts(api,ctx,binding['runId'],req);directory=Path(root)/'backups'/task/'R3-platform-binding-transport'/approval
  result=transfer(api,ctx,binding,directory)
 return {**result,'facts':facts,'binding_newly_issued':False,'local_permission_consumed':False,'platform_review_or_deploy_performed':False}

def status(root,task,approval):
 ctx,row,req=context(root,task,approval,effect=False);api=GitHub(ctx);b=row['platform_binding'];facts=platform_facts(api,ctx,b['runId'],req,pending=False);actual=levels(api,ctx);level='environment'if actual['environment']['exists']else'repository';matches=[x for x in actual[level]['entries']if x.get('approvalId')==approval];need(not matches or matches==[b],'exact original remote reference differs/ambiguous')
 return {'state':'EXACT_REMOTE_BINDING_PRESENT'if matches else'NO_EXACT_BINDING_OBSERVED_NOT_A_WRITE_PROOF','effective_level':level,'facts':facts,'binding_currently_unexpired':w._parse_observed_at(b['expiresAt'])>timestamp(),'read_only':True,'unknown_effect_retry_allowed':False,'local_approval_status':row['status']}

def describe(root,task):
 ctx,_,_=context(root,task)
 return {'state':'LOCAL_NORMAL_CARRIER_INSTALLED_NOT_PLATFORM_EFFECT','task_id':task,'source':ctx['registration'],
  'platform_executor':ctx['role'],'worktree':ctx['worktree'],'repository':ctx['repository'],'environment':ENV,'variable':VARIABLE,
  'commands':['inspect --task-id ORIGINAL --run-id ACTUAL_EXISTING_PENDING_RUN','install --task-id ORIGINAL --approval-id ACTUAL_NORMALLY_ISSUED_REFERENCE','status --task-id ORIGINAL --approval-id SAME_ORIGINAL_REFERENCE'],
  'issuer':'unchanged normal preflight/approval-record; expected apr is not an issued record','SYS_platform_calls_performed':0,
  'server_CAS_available':False,'concurrency':'one original WEB writer, local repository-wide serialization, fresh whole-value/timestamp comparison and append/readback; uncontrolled external editors are not atomically fenced',
  'never':['raw arbitrary variable writes','environment/reviewer protection changes','credential capture','approval reissue/expiry extension','workflow dispatch/cancel/review','overwrite/prune other bindings','unknown-effect replay']}

if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('command',choices=['describe','inspect','install','status']);parser.add_argument('--task-id',required=True);parser.add_argument('--run-id',type=int);parser.add_argument('--approval-id');args=parser.parse_args();root=Path(__file__).resolve().parents[1]
 try:
  if args.command=='describe':out=describe(root,args.task_id)
  elif args.command=='inspect':need(args.run_id and args.run_id>0,'actual existing run required');out=inspect(root,args.task_id,args.run_id)
  else:need(args.approval_id,'genuine normally issued reference required');out=install(root,args.task_id,args.approval_id)if args.command=='install'else status(root,args.task_id,args.approval_id)
  print(json.dumps(out,ensure_ascii=False,indent=2))
 except (w.WorkflowError,GitHubError,KeyError,ValueError,OSError)as e:parser.exit(1,str(e)+'\n')
