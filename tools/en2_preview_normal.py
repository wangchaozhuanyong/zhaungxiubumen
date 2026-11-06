"""Exact EN2 zero-write preview: normal evidence, policy and fenced transport."""
from pathlib import Path
import datetime as dt, hashlib, json, os, subprocess
import workflow_control as w
import department_autonomy as a
import en2_preview_entry as entry
import en2_preview_history as history

SCHEMA='en2-original-WEB-protected-preview-preflight/v1'
TASK=entry.TASK
SCOPE='cms:services:kitchen:english-two-fields:publication:v1'
ROLE='designated-development'
CLASS='site_ci_prepare'

def need(ok,msg):a.require(ok,'EN2 preview: '+msg)

def context(root):
 return entry._reviewed_context(root)

def request(root,state,allowed_policy=None):
 return entry.request_base(root,TASK,state,allowed_policy=allowed_policy)

def _official_web_selfcheck(root,req,request_pin,turn_id,command_id,identity,pub,ctx):
 """Read actual original WEB command directly through first-party history RPC."""
 from en2_preview_web_identity import read_native_turn
 binding=ctx['binding'];ref=req['state']['original_web_inventory']
 need(ref['turn_id']==turn_id and isinstance(command_id,str) and command_id,'same actual WEB inventory turn and selfcheck required')
 turn=read_native_turn(root,binding,turn_id,command_id)
 calls=[x for x in turn.get('items',[]) if x.get('id')==command_id];need(len(calls)==1,'one actual WEB selfcheck command');c=calls[0]
 need(c.get('type')=='commandExecution' and c.get('status')=='completed' and c.get('exitCode')==0 and type(c.get('startedAtMs')) is int and type(c.get('completedAtMs')) is int and c['startedAtMs']<=c['completedAtMs'] and Path(c.get('cwd','')).resolve().is_relative_to(Path(binding['cwd']).resolve()),'actual completed original WEB selfcheck')
 now=dt.datetime.now(dt.timezone.utc).timestamp()*1000;need(0<=now-c['completedAtMs']<=300000,'fresh original WEB selfcheck required')
 need(identity.get('state')=='WEB_IDENTITY_ATTESTED_ONLY' and type(identity.get('inventory_completed_at_ms')) is int
      and type(pub.get('same_row_completed_at_ms')) is int and c['startedAtMs']>=max(identity['inventory_completed_at_ms'],pub['same_row_completed_at_ms']),
      'WEB selfcheck must follow original actual PUB same-row query and WEB inventory')
 import shlex
 argv=shlex.split(c.get('command',''))
 if len(argv)==3 and argv[0] in ('/bin/zsh','/bin/bash') and argv[1] in ('-lc','-c'):argv=shlex.split(argv[2])
 canonical=argv[3:] == ['selfcheck','--request',request_pin['path']]
 if len(argv)==8 and argv[3:5]==['prepare-and-selfcheck','--state'] and argv[6:]==['--request',request_pin['path']]:
  canonical=w.read_json(w.safe_path(root,argv[5]))==req['state']
 need(canonical and Path(argv[0]).name.startswith('python') and argv[1]=='-B'
      and Path(argv[2]).resolve()==(Path(root)/'tools/en2_preview_normal.py').resolve(),
      'canonical original WEB selfcheck command required; arbitrary printed PASS is not evidence')
 raw=w._source_continuation_execution_output(c)
 try:value=json.loads(raw)
 except (ValueError,TypeError) as exc:raise w.WorkflowError('EN2 preview: complete selfcheck JSON required') from exc
 expected={'state':'EN2_PREVIEW_SELFCHECK_PASS_NOT_PERMISSION','task_id':TASK,'request_sha256':request_pin['sha256'],
           'decision_sha256':ctx['decision']['sha256'],'runtime_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
           'permission_issued':False}
 need(value==expected,'actual canonical selfcheck must bind exact request, runtime and original decision')
 return {'turn_id':turn_id,'command_id':command_id,'request_sha256':request_pin['sha256'],'completed_at_ms':c['completedAtMs']}

def _verify(root,item,allowed_policy=None):
 need(isinstance(item,dict) and item.get('schema')==SCHEMA and item.get('task_id')==TASK and set(item)=={'schema','task_id','request','web_turn_id','web_selfcheck_command'},'exact original preview preflight envelope')
 req=a.document(root,item['request'])
 rebuilt,identity,pub,ctx=entry._verified_request(root,TASK,req['state'],allowed_policy=allowed_policy)
 need(req==rebuilt,'exact recomputed verified original preview request')
 proof=_official_web_selfcheck(root,req,item['request'],item['web_turn_id'],item['web_selfcheck_command'],identity,pub,ctx)
 return req,proof,ctx

@w.request_validation_context()
def selfcheck(root,request_path):
 pin=w.file_digest(root,request_path);req=a.document(root,pin)
 rebuilt,_,_,ctx=entry._verified_request(root,TASK,req['state'])
 need(req==rebuilt,'exact independently revalidated original preview request required')
 w._VALIDATION_CONTEXT.get().recheck()
 return _selfcheck_result(pin,ctx)

@w.request_validation_context()
def prepare_and_selfcheck(root,state_path,request_path):
 from department_rotation import prohibit_validation_write
 prohibit_validation_write()
 state=w.read_json(w.safe_path(root,state_path))
 req,_,_,ctx=entry._verified_request(root,TASK,state)
 out=w.safe_path(root,request_path)
 w._VALIDATION_CONTEXT.get().recheck()
 with out.open('x',encoding='utf-8') as handle:
  json.dump(req,handle,ensure_ascii=False,indent=2)
  handle.write('\n')
 pin=w.file_digest(root,request_path)
 need(a.document(root,pin)==req,'exact written preview request required')
 return _selfcheck_result(pin,ctx)

def _selfcheck_result(pin,ctx):
 w._VALIDATION_CONTEXT.get().recheck()
 return {'state':'EN2_PREVIEW_SELFCHECK_PASS_NOT_PERMISSION','task_id':TASK,'request_sha256':pin['sha256'],
         'decision_sha256':ctx['decision']['sha256'],'runtime_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
         'permission_issued':False}

@w.request_validation_context()
def build_preflight(root,base_path,web_turn_id,web_selfcheck_command,out_path):
 pin=w.file_digest(root,base_path);item={'schema':SCHEMA,'task_id':TASK,'request':pin,'web_turn_id':web_turn_id,'web_selfcheck_command':web_selfcheck_command}
 req,_,_=_verify(root,item);w._VALIDATION_CONTEXT.get().recheck();out=w.safe_path(root,out_path);need(not out.exists(),'new exact preflight output only');w.atomic_write_json(out,item)
 return {'state':'prepared_not_a_permission','input':w.file_digest(root,out_path),'request':pin,'external_permission_issued':False}

@w.request_validation_context()
def record_preflight(root,task,path):
 need(task==TASK,'original task required');pin=w.file_digest(root,path);item=a.document(root,pin);req,_,_=_verify(root,item)
 return _commit_preflight(root,pin,item,req)

@w.request_validation_context()
def build_and_record_preflight(root,base_path,web_turn_id,web_selfcheck_command,out_path,*,consume_preview_policy=False):
 from department_rotation import prohibit_validation_write
 prohibit_validation_write()
 request_pin=w.file_digest(root,base_path)
 item={'schema':SCHEMA,'task_id':TASK,'request':request_pin,'web_turn_id':web_turn_id,'web_selfcheck_command':web_selfcheck_command}
 req,_,ctx=_verify(root,item)
 out=w.safe_path(root,out_path);need(not out.exists(),'new exact preflight output only')
 w._VALIDATION_CONTEXT.get().recheck()
 with out.open('x',encoding='utf-8') as handle:
  json.dump(item,handle,ensure_ascii=False,indent=2)
  handle.write('\n')
 pin=w.file_digest(root,out_path)
 need(a.document(root,pin)==item,'exact written preflight input required')
 if consume_preview_policy:
  return _commit_preflight(root,pin,item,req,policy_context=ctx)
 return _commit_preflight(root,pin,item,req)

def _commit_preflight(root,pin,item,req,*,policy_context=None):
 import goal_delivery_runtime as g
 with w.workflow_lock(root):
  rows=[x for x in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS,where={'task_id':TASK}) if x.get('task_id')==TASK and x.get('details',{}).get('en2_preview_preflight',{}).get('action_id')==history.ACTION]
  prior=history.unresolved_preview_policies(root)
  need(not prior and not history.intent_path(root).exists(),'issued or unknown original preview blocks preflight')
  if rows:
   last=rows[-1]['details']['en2_preview_preflight']
   if last['input']==pin:return {'result':'duplicate_ignored','permission_issued':False}
   # A fresh immutable preflight may supersede an expired one only while no
   # original policy or transport intent exists; all old source pins survive.
   for e in rows:
    previous=e['details']['en2_preview_preflight'];old_item=a.document(root,previous['input']);old_req=a.document(root,previous['request'])
    need(old_item.get('schema')==SCHEMA and old_item.get('request')==previous['request'] and all(old_req.get(k)==req.get(k) for k in ('task_id','department','action_id','action_class','scope','operation')),
         'original earlier preflight source or identity changed')
  snap=g.restore_goal(root,w.read_json(w.snapshot_path(root,TASK)));need(snap.get('current_state') not in w.TERMINAL_STATES | {'paused','suspended','blocked'},'open original task required')
  now=dt.datetime.now(dt.timezone.utc);observed=w._parse_observed_at(req.get('observed_at'))
  need(observed and 0<=(now-observed).total_seconds()<=300,'original PUB observation expired before preflight registration')
  if policy_context is not None:
   need(not w.validate_workflow_events(root,TASK) and not w._validate_receipt_chain(root,TASK)[1],
        'intact original workflow and receipt chain required before preview policy')
   need((dt.datetime.now(dt.timezone.utc)-observed).total_seconds()<=265,
        'insufficient original PUB freshness remaining to dispatch safely')
  w._VALIDATION_CONTEXT.get().recheck()
  event=w.append_workflow_event(root,TASK,snap['current_state'],{'en2_preview_preflight':{'action_id':history.ACTION,'input':pin,'request':item['request']},'external_permission_issued':False})
  result={'result':'recorded','event_id':event['event_id'],'permission_issued':False}
  if policy_context is not None:
   row={'request':item['request'],'input':pin}
   value=_preview_policy_value(row,policy_context)
   result.update(_consume_preview_policy(root,value,observed))
 return result

def _current_preflight(root,allowed_policy=None):
 rows=[x for x in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS,where={'task_id':TASK}) if x.get('task_id')==TASK and x.get('details',{}).get('en2_preview_preflight',{}).get('action_id')==history.ACTION]
 need(bool(rows) and not w.validate_workflow_events(root,TASK) and not w._validate_receipt_chain(root,TASK)[1],'intact original committed preview preflight')
 row=rows[-1]['details']['en2_preview_preflight'];item=a.document(root,row['input']);need(item.get('request')==row.get('request'),'preflight request source pin')
 req,proof,ctx=_verify(root,item,allowed_policy=allowed_policy);return row,item,req,proof,ctx

def validate_request(root,req):
 row,item,actual,proof,ctx=_current_preflight(root)
 need(req==actual,'actual committed exact original preview preflight request required')
 return ctx,entry.OP,req['state']

def preflight(root,task,action,action_class,scope,department):
 row,item,req,proof,ctx=_current_preflight(root)
 need((task,action,action_class,scope,department)==(TASK,history.ACTION,CLASS,SCOPE,ROLE),'exact original preview preflight identity')
 return {**item,'risk_level':'R2','task_id':TASK,'department':ROLE,'action_id':history.ACTION,'action_class':CLASS,'scope':SCOPE,'external_permission_issued':False},req,row['input'],ctx

def _preview_policy_identity(row):
 return {'task_id':TASK,'department':ROLE,'action_id':history.ACTION,'action_class':CLASS,'scope':SCOPE,'source_project_id':a.PROJECT,'payload_sha256':row['request']['sha256']}

def _preview_policy_value(row,ctx):
 return {**_preview_policy_identity(row),'status':'preflight_ready_not_a_permit','actual_action_allowed':False,'approval_basis':a.MODE,'original_authority':ctx['authorization'],'mode_authorization':a.OWNER,'exact_request':row['request'],'source_preflight':row['input'],'autonomous_action_key':w.sha256_value([TASK,ROLE,history.ACTION,CLASS,SCOPE]),'checked_at':w.utc_timestamp(),'external_execution_department':ROLE,'assistant_approval_required':False,'platform_permission_issued':False,'operation':'protected_preview'}

def _consume_preview_policy(root,value,observed):
 need(0<=(dt.datetime.now(dt.timezone.utc)-observed).total_seconds()<=265,'insufficient original PUB freshness remaining to dispatch safely')
 value.update(status='allow',actual_action_allowed=True,approval_status='consumed_for_original_exact_autonomous_action',decision_id='pol-'+w.sha256_value([value,'en2-dry-run'])[:20])
 w.append_jsonl_locked(Path(root)/w.POLICY_DECISIONS,value)
 return value

@w.request_validation_context()
def policy(root,requested):
 row,item,req,proof,ctx=_current_preflight(root)
 expected=_preview_policy_identity(row)
 need(all(requested.get(k)==v for k,v in expected.items()) and not requested.get('approval_id') and not requested.get('target_department') and not requested.get('target_project_id') and not requested.get('skill') and requested.get('consume_approval') in (None,False,True) and (requested.get('consume_approval') is None or type(requested.get('consume_approval')) is bool),'exact independent zero-write preview policy identity')
 with w.workflow_lock(root):
  need(not history.unresolved_preview_policies(root) and not history.intent_path(root).exists(),'original preview already issued or unknown')
  now=dt.datetime.now(dt.timezone.utc);observed=w._parse_observed_at(req['observed_at']);need(observed and 0<=(now-observed).total_seconds()<=300,'fresh original PUB observation')
  w._VALIDATION_CONTEXT.get().recheck()
  value=_preview_policy_value(row,ctx)
  if requested.get('consume_approval') is True:
   _consume_preview_policy(root,value,observed)
 return value,[Path(root)/w.POLICY_DECISIONS]

def _official_web_policy(root,req,ctx,pol,proof,command_id):
 """Bind the consumed row to the original WEB's actual normal policy command."""
 import shlex
 from en2_preview_web_identity import read_native_turn
 need(isinstance(command_id,str) and command_id,'actual original WEB policy command ID required')
 binding=ctx['binding'];turn_id=req['state']['original_web_inventory']['turn_id']
 turn=read_native_turn(root,binding,turn_id,command_id)
 calls=[x for x in turn.get('items',[]) if x.get('id')==command_id];need(len(calls)==1,'one actual original WEB policy command required');c=calls[0]
 need(c.get('type')=='commandExecution' and c.get('status')=='completed' and c.get('exitCode')==0 and type(c.get('startedAtMs')) is int and type(c.get('completedAtMs')) is int and c['startedAtMs']<=c['completedAtMs'] and type(proof.get('completed_at_ms')) is int and c['startedAtMs']>=proof['completed_at_ms'] and Path(c.get('cwd','')).resolve().is_relative_to(Path(binding['cwd']).resolve()),'completed original WEB policy command after selfcheck required')
 argv=shlex.split(c.get('command',''))
 if len(argv)==3 and argv[0] in ('/bin/zsh','/bin/bash') and argv[1] in ('-lc','-c'):argv=shlex.split(argv[2])
 expected=['policy-check','--task-id',TASK,'--department',ROLE,'--action-id',history.ACTION,'--action-class',CLASS,'--scope',SCOPE,'--source-project-id',a.PROJECT,'--payload-sha256',pol['payload_sha256'],'--consume-approval']
 source=pol['source_preflight']
 item=a.document(root,source)
 combined=['build-and-record-preflight','--request',pol['exact_request']['path'],
           '--web-turn',turn_id,'--selfcheck-command',item['web_selfcheck_command'],
           '--output',source['path'],'--consume-preview-policy']
 need(len(argv)>=3 and Path(argv[0]).name.startswith('python') and argv[1]=='-B'
      and ((Path(argv[2]).resolve()==(Path(root)/'tools/flashcast_ops.py').resolve() and argv[3:]==expected)
           or (Path(argv[2]).resolve()==(Path(root)/'tools/en2_preview_normal.py').resolve() and argv[3:]==combined)),
      'canonical exact original WEB normal policy command required')
 try:output=json.loads(w._source_continuation_execution_output(c))
 except (ValueError,TypeError) as exc:raise w.WorkflowError('EN2 preview: complete actual policy output required') from exc
 checked=w._parse_observed_at(pol.get('checked_at'));now=dt.datetime.now(dt.timezone.utc)
 need(output.get('status')=='allow' and output.get('decision_id')==pol.get('decision_id') and checked and c['startedAtMs']//1000<=int(checked.timestamp())<=c['completedAtMs']//1000 and 0<=(now-checked).total_seconds()<=300,'actual normal consumed policy output and timing required')
 return True

@w.request_validation_context()
def dispatch(root,policy_id,policy_command):
 """Future original WEB one-shot; attempt persists before provider call."""
 root=Path(root).resolve();matches=[p for p in w.read_jsonl(root/w.POLICY_DECISIONS) if p.get('decision_id')==policy_id]
 need(len(matches)==1,'one real original preview policy required');pol=matches[0]
 need(pol.get('status')=='allow' and pol.get('task_id')==TASK and pol.get('department')==ROLE and pol.get('action_id')==history.ACTION and pol.get('action_class')==CLASS and pol.get('scope')==SCOPE and pol.get('operation')=='protected_preview' and pol.get('actual_action_allowed') is True and pol.get('approval_status')=='consumed_for_original_exact_autonomous_action','one exact consumed preview policy required')
 at=w._parse_observed_at(pol.get('checked_at'));now=dt.datetime.now(dt.timezone.utc);need(at and 0<=(now-at).total_seconds()<=300,'original preview policy expired')
 with w.workflow_lock(root):
  need(history.unresolved_preview_policies(root)==[pol], 'original preview policy changed or was reconciled')
  row,_,req,proof,ctx=_current_preflight(root,allowed_policy=pol)
  need(pol.get('exact_request')==row['request'] and pol.get('source_preflight')==row['input'] and pol.get('original_authority')==ctx['authorization'] and pol.get('payload_sha256')==row['request']['sha256'],'policy must bind exact original preflight')
  _official_web_policy(root,req,ctx,pol,proof,policy_command)
  inputs=req['desired']['inputs'];argv=['gh','workflow','run','content-publish-approved.yml','--repo','example-owner/example-website','--ref','main','-f','mode=dry-run','-f','target=english-kitchen-en2-exact-v1','-f','approval_id='+inputs['approval_id'],'-f','managed_operation=publish','-f','managed_permit_id=','-f','parent_run_id=']
  observed=w._parse_observed_at(req['observed_at']);now=dt.datetime.now(dt.timezone.utc)
  need(observed and 0<=(now-observed).total_seconds()<=300 and 0<=(now-at).total_seconds()<=300,'fresh facts/policy at transport boundary')
  w._VALIDATION_CONTEXT.get().recheck()
  from en2_preview_github_evidence import _get,REPO
  current_main=_get(f'repos/{REPO}/git/ref/heads/main')
  need(current_main.get('object',{}).get('sha')==req['desired']['head'],
       'GitHub main changed before transport; original WEB must verify the new source')
  now=dt.datetime.now(dt.timezone.utc)
  need(0<=(now-observed).total_seconds()<=300 and 0<=(now-at).total_seconds()<=300,'fresh facts/policy at transport boundary')
  path=history.intent_path(root);record={'schema':'en2-original-preview-once/v1','task_id':TASK,'action_id':history.ACTION,'policy_id':policy_id,'request':row['request'],'main_sha':req['desired']['head'],'argv_sha256':w.sha256_value(argv),'at':now.isoformat(),'state':'DISPATCH_INTENT_EFFECT_UNKNOWN'}
  try:fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
  except FileExistsError as exc:raise w.WorkflowError('EN2 preview: existing intent; investigate original key, never resend') from exc
  with os.fdopen(fd,'w',encoding='utf-8') as f:json.dump(record,f,sort_keys=True);f.flush();os.fsync(f.fileno())
 # A failed/timeout command leaves intent unknown. Never synthesize run ID.
 p=subprocess.run(argv,cwd=ctx['binding']['cwd'],capture_output=True,text=True,timeout=60)
 need(p.returncode==0,'dispatch result unknown; original intent remains fenced')
 return {'state':'DISPATCH_REQUESTED_ACTUAL_RUN_NOT_YET_VERIFIED','policy_id':policy_id,'intent':w.file_digest(root,str(path.relative_to(root))),'run_id':None,'production_write':False}


@w.request_validation_context()
def reconcile_expired_policy(root,policy_id,failed_command_id):
 """Append a no-dispatch reconciliation after verifying original native and hosted evidence."""
 import shlex
 import goal_delivery_runtime as g
 from en2_preview_web_identity import read_native_turn
 root=Path(root).resolve();policies=history.unresolved_preview_policies(root)
 need(len(policies)==1 and policies[0].get('decision_id')==policy_id,'exact unreconciled preview policy required')
 pol=policies[0];ctx=context(root);request_pin=pol['exact_request'];req=a.document(root,request_pin)
 at=w._parse_observed_at(pol.get('checked_at'));observed=w._parse_observed_at(req.get('observed_at'));now=dt.datetime.now(dt.timezone.utc)
 need(at and observed and (now-at).total_seconds()>300 and (now-observed).total_seconds()>300
      and pol.get('original_authority')==ctx['authorization'] and pol.get('operation')==entry.OP
      and pol.get('platform_permission_issued') is False
      and all(req.get(key)==pol.get(key) for key in ('task_id','action_id','action_class','department','scope'))
      and not history.intent_path(root).exists(),'expired original preview policy, unchanged source and no durable intent required')
 preflight=a.document(root,pol['source_preflight'])
 need(preflight.get('request')==request_pin,'exact original preflight pin required')
 turn_id=req['state']['original_web_inventory']['turn_id']
 turn=read_native_turn(root,ctx['binding'],turn_id,failed_command_id)
 calls=[item for item in turn.get('items',[]) if item.get('id')==failed_command_id]
 need(turn.get('status')=='completed' and len(calls)==1,'completed original WEB turn and exact failed command required')
 command=calls[0];argv=shlex.split(command.get('command',''))
 if len(argv)==3 and argv[0] in ('/bin/zsh','/bin/bash') and argv[1] in ('-lc','-c'):argv=shlex.split(argv[2])
 need(command.get('type')=='commandExecution' and command.get('status')=='failed' and command.get('exitCode')==1
      and type(command.get('startedAtMs')) is int and type(command.get('completedAtMs')) is int
      and at.timestamp()*1000<=command['startedAtMs']<=command['completedAtMs']
      and command['completedAtMs']>(observed.timestamp()+300)*1000
      and Path(command.get('cwd','')).resolve().is_relative_to(Path(ctx['binding']['cwd']).resolve())
      and len(argv)==8 and Path(argv[0]).name.startswith('python') and argv[1]=='-B'
      and Path(argv[2]).resolve()==root/'tools/en2_preview_normal.py'
      and argv[3:7]==['dispatch','--policy-id',policy_id,'--policy-command']
      and command.get('aggregatedOutput')
          =='autonomous delivery: EN2 preview: authentic fresh original PUB full-row/key/same-row evidence required\n',
      'original canonical dispatch must have failed before the durable intent')
 hosted=history.read_actual(root,allowed_policy=pol)
 with w.workflow_lock(root):
  need(history.unresolved_preview_policies(root)==[pol] and not history.intent_path(root).exists(),
       'original policy or transport changed before reconciliation')
  need(not w.validate_workflow_events(root,TASK),'intact original workflow required')
  snap=g.restore_goal(root,w.read_json(w.snapshot_path(root,TASK)))
  need(snap['current_state'] not in w.TERMINAL_STATES | {'paused','suspended','blocked'},'open original task required')
  w._VALIDATION_CONTEXT.get().recheck()
  event=w.append_workflow_event(root,TASK,snap['current_state'],{history.RECONCILED:{
       'policy_id':policy_id,'policy_sha256':w.sha256_value(pol),'original_request':request_pin,
       'original_web_turn':turn_id,'failed_command_id':failed_command_id,'hosted':hosted,
       'effect':'NO_DISPATCH_INTENT_AND_NO_HOSTED_RUN','external_permission_issued':False}})
 return {'state':'EXPIRED_PREVIEW_POLICY_RECONCILED_NO_DISPATCH','policy_id':policy_id,
         'event_id':event['event_id'],'production_write':False,'external_permission_issued':False}

def inspect_unknown(root):
 """Read possible post-intent runs; never mark zero as safe to replay."""
 import en2_preview_github_evidence as gh
 root=Path(root).resolve();path=history.intent_path(root);need(path.is_file(),'no original preview intent recorded')
 intent=w.read_json(path);need(intent.get('schema')=='en2-original-preview-once/v1' and intent.get('task_id')==TASK and intent.get('action_id')==history.ACTION and intent.get('state')=='DISPATCH_INTENT_EFFECT_UNKNOWN','exact original pending intent required')
 start=w._parse_observed_at(intent.get('at'));need(start is not None,'actual intent timestamp required')
 prefix='repos/'+gh.REPO
 actor=gh._get('user');repository=gh._get(prefix);workflow=gh._get(prefix+'/actions/workflows/content-publish-approved.yml')
 need(actor.get('id')==276684684 and actor.get('login')=='example-owner' and repository.get('id')==1248188229 and repository.get('full_name')==gh.REPO and workflow.get('path')==gh.WORKFLOW and workflow.get('name')=='Approved website content publish','exact original account/repository/workflow required for readback')
 page=1;total=0;expected=None;found=[]
 while True:
  need(page<=20,'original run list exceeds bounded complete inspection')
  result=gh._get(prefix+'/actions/workflows/content-publish-approved.yml/runs?per_page=100&page='+str(page)+'&event=workflow_dispatch')
  runs=result.get('workflow_runs');count=result.get('total_count');need(type(count) is int and isinstance(runs,list) and len(runs)<=100 and (expected is None or expected==count),'original run list incomplete/changed')
  expected=count;total+=len(runs)
  for run in runs:
   if run.get('display_title')!='english-kitchen-en2-exact-v1 | dry-run':continue
   created=w._parse_observed_at(run.get('created_at'))
   need(created is not None and type(run.get('id')) is int and run.get('path')==gh.WORKFLOW and run.get('event')=='workflow_dispatch' and run.get('repository',{}).get('id')==1248188229,'ambiguous original run identity')
   if created>=start:found.append({'run_id':run['id'],'head_sha':run.get('head_sha'),'status':run.get('status'),'run_attempt':run.get('run_attempt'),'actor_id':run.get('actor',{}).get('id')})
  if total>=expected:break
  need(len(runs)==100,'truncated original run list');page+=1
 need(total==expected,'incomplete original run list')
 return {'state':'AMBIGUOUS_MULTIPLE_MATCHES' if len(found)>1 else 'ONE_POSSIBLE_MATCH_OWNER_MUST_VERIFY' if found else 'UNKNOWN_NO_RUN_OBSERVED',
         'matches':found,'replay_allowed':False,'intent':w.file_digest(root,str(path.relative_to(root))),'permission_issued':False}


def _verified_preissue_expiry(root):
 """Exact actual original PUB failure and subsequent official zero-key read."""
 from en2_preview_web_identity import read_native_turn
 from en2_supabase_origin import _official_call,KEY_SQL
 fixed=w.department_registry(root)['publishing']['chat_binding']
 turn_id='example-native-3b619a7108f70809'
 failure_id='exec-cc001b1f-a5c1-4c99-9c9d-d5b357b3e9e0'
 key_id='exec-96e7eaed-973c-4644-a9b2-5a0758eb3e92'
 turn=read_native_turn(root,{**fixed,'thread_id':fixed['task_id']},turn_id,failure_id)
 need(turn.get('status')=='completed','actual original PUB failure turn must have ended')
 failed=[x for x in turn['items'] if x.get('id')==failure_id]
 need(len(failed)==1,'one real original failed issuer command required')
 fail=failed[0];out=fail.get('aggregatedOutput')
 projected=fail.get('output')
 if projected is not None:
  if isinstance(projected,dict):
   need(projected.get('truncated') is False,'complete original issuer error required')
   projected=projected.get('text')
  need(out is None or out==projected,'native issuer error representations must agree')
  out=projected
 need(fail.get('type')=='commandExecution' and fail.get('status')=='failed' and fail.get('exitCode')==1
      and fail.get('cwd')==str(root) and isinstance(out,str)
      and out.rstrip().endswith('workflow_control.WorkflowError: autonomous delivery: fresh official PUB row, original key and complete same-row effects must bind exact request')
      and '_selected_en2_target' in out and 'en2_current_forward_evidence' in out
      and 'endpoint_request' not in out and history.PREISSUE_POLICY in fail.get('command','')
      and str(history.PREISSUE_RUN) in fail.get('command',''),
      'actual original current-target refusal before issuer transport required')
 key,rows=_official_call(turn,key_id,KEY_SQL)
 need(not rows and fail['completedAtMs']<=key['startedAtMs'],'actual postfailure original key must be empty')
 policies=history.live_cms_policy_rows(root)
 need(len(policies)==1 and policies[0].get('decision_id')==history.PREISSUE_POLICY,
      'one exact spent original CMS policy required')
 pol=policies[0]
 events=w.read_jsonl(root/w.WORKFLOW_EVENTS,where={'task_id':TASK,
          ('details','professional_cms_preflight','request'):pol['exact_request']})
 need(len(events)==1,'original exact committed forward preflight required')
 evidence=events[0]['details']['professional_cms_preflight']['provider_origin_evidence']
 observed=w._parse_observed_at(evidence['server_observed_at'])
 need(evidence['preview_run_id']==history.PREISSUE_RUN and observed
      and fail['completedAtMs']>(observed.timestamp()+300)*1000,
      'actual official row expired before issue completion')
 return pol,{'original_pub_turn':turn_id,'failed_issuer_command':failure_id,'zero_key_call':key_id,
             'preflight_event_id':events[0]['event_id'],'failure_output_sha256':hashlib.sha256(out.encode()).hexdigest()}


def _verified_policy_timing_refusal(root):
 """Authenticate the exact original refusal before policy consumption and the post-refusal key read."""
 import shlex
 from en2_preview_web_identity import read_native_turn
 from en2_supabase_origin import _official_call,KEY_SQL
 turn_id='example-native-ae03f22a21ef8360'
 failed_id='exec-66bdc3a5-271b-4d82-a0bf-17ddf6d82974'
 key_id='exec-6830cff9-4d20-4e10-91be-dad7f8723ad9'
 fixed=w.department_registry(root)['publishing']['chat_binding']
 turn=read_native_turn(root,{**fixed,'thread_id':fixed['task_id']},turn_id,failed_id)
 failed=[item for item in turn['items'] if item.get('id')==failed_id]
 need(turn.get('status')=='completed' and len(failed)==1,'one completed original PUB policy refusal required')
 call=failed[0];output=call.get('aggregatedOutput');projected=call.get('output')
 if isinstance(projected,dict):
  need(projected.get('truncated') is False,'complete original policy refusal output required')
  projected=projected.get('text')
 if projected is not None:
  need(output is None or output==projected,'native policy refusal outputs must agree')
  output=projected
 events=w.read_jsonl(root/w.WORKFLOW_EVENTS,where={'task_id':TASK,'event_id':history.POLICY_TIMING_PREFLIGHT})
 need(len(events)==1,'one exact committed policy timing preflight required')
 preflight=events[0]['details']['professional_cms_preflight'];request=a.document(root,preflight['request'])
 argv=shlex.split(call.get('command',''))
 if len(argv)==3 and argv[:2]==['/bin/zsh','-lc']:argv=shlex.split(argv[2])
 expected=['policy-check','--task-id',TASK,'--department','publishing','--action-id',request['action_id'],
           '--action-class','cms_write','--scope',request['scope'],'--source-project-id',a.PROJECT,
           '--payload-sha256',preflight['request']['sha256'],'--consume-approval']
 need(call.get('type')=='commandExecution' and call.get('status')=='failed' and call.get('exitCode')==2
      and call.get('cwd')==str(root) and len(argv)==5+len(expected)
      and argv[:2]==['env','PYTHONPATH=$PWD:$PWD/tools'] and Path(argv[2]).name.startswith('python')
      and argv[3:5]==['-B','tools/flashcast_ops.py'] and argv[5:]==expected
      and isinstance(output,str) and output.rstrip()=='ERROR: autonomous delivery: EN2 needs 75 seconds remaining before consuming the original single-write policy',
      'canonical original policy must have refused before consuming or issuing')
 origin=preflight['provider_origin_evidence'];key,rows=_official_call(turn,key_id,KEY_SQL)
 dates=[w._parse_observed_at(origin[k]) for k in ('server_observed_at','preview_receipt_checked_at')]
 need(all(dates) and origin['preview_run_id']==history.POLICY_TIMING_RUN and not rows
      and (min(dates).timestamp()+225)*1000<call['completedAtMs']<=key['startedAtMs']
      and history.live_cms_policy_rows(root)==[], 'no new policy and actual original key empty after refusal required')
 return {'original_pub_turn':turn_id,'failed_policy_command':failed_id,'zero_key_call':key_id,
         'preflight_event_id':events[0]['event_id'],'failure_output_sha256':hashlib.sha256(output.encode()).hexdigest()}


def _verified_issuer_project_refusal(root):
 """Reconcile only the v13 local validation rejection before network transport."""
 from en2_preview_web_identity import read_native_turn
 from en2_supabase_origin import _official_call,KEY_SQL
 turn_id='example-native-a3b4d36338cc8304'
 command_id='exec-9c7eca4f-1228-4bb7-b2e2-50d4225ce309'
 key_id='exec-38749453-c54c-4ead-a054-c21d9cc1f85a'
 fixed=w.department_registry(root)['publishing']['chat_binding']
 turn=read_native_turn(root,{**fixed,'thread_id':fixed['task_id']},turn_id,command_id)
 calls=[item for item in turn['items'] if item.get('id')==command_id]
 need(turn.get('status')=='completed' and len(calls)==1,'completed original PUB issuer command required')
 call=calls[0];output=call.get('aggregatedOutput')
 projected=call.get('output')
 if isinstance(projected,dict):
  need(projected.get('truncated') is False,'complete issuer refusal output required')
  projected=projected.get('text')
 if projected is not None:
  need(output is None or output==projected,'native issuer refusal outputs must agree')
  output=projected
 command=call.get('command','')
 need(call.get('type')=='commandExecution' and call.get('status')=='failed' and call.get('exitCode')==1
      and call.get('cwd')==str(root) and isinstance(output,str)
      and output.startswith('BLOCKED_MANAGED_CMS_PERMIT: Wrong Supabase project\n')
      and all(part in output for part in ('managed_cms_permit_issuer.py',history.NO_TRANSPORT_POLICY,str(history.NO_TRANSPORT_RUN),'--issue-and-dispatch'))
      and all(part in command for part in ('en2_forward_preflight_prepare.py bind-readiness',str(history.NO_TRANSPORT_RUN),'--issue-after-policy')),
      'original issuer must have refused at local project validation before HTTP')
 sql=KEY_SQL.replace('expected_updated_at,github_run_id,github_run_attempt','github_run_id').replace('issued_at,expires_at,status','issued_at,status')
 key,rows=_official_call(turn,key_id,sql)
 need(not rows and call['completedAtMs']<=key['startedAtMs'],'actual original key must be empty after local refusal')
 policies=history.live_cms_policy_rows(root)
 need(len(policies)==1 and policies[0].get('decision_id')==history.NO_TRANSPORT_POLICY,
      'one exact spent v13 CMS policy required')
 policy=policies[0]
 events=w.read_jsonl(root/w.WORKFLOW_EVENTS,where={'task_id':TASK,'event_id':history.NO_TRANSPORT_PREFLIGHT,
                       ('details','professional_cms_preflight','request'):policy['exact_request']})
 need(len(events)==1 and events[0]['details']['professional_cms_preflight']['provider_origin_evidence']['preview_run_id']==history.NO_TRANSPORT_RUN,
      'one original v13 preflight bound to the consumed policy required')
 pin=w.file_digest(root,history.ORIGINAL_ISSUER_INTENT);intent=a.document(root,pin)
 stamp=w._parse_observed_at(intent.get('created_at'))
 need(intent.get('schema')=='en2-forward-issuer-once/v1' and intent.get('state')=='ISSUE_INTENT_EFFECT_UNKNOWN'
      and all(intent.get(k)==policy.get(k) for k in ('task_id','action_id'))
      and intent.get('policy_decision_id')==policy['decision_id'] and intent.get('business_scope')==policy['scope']
      and stamp and call['startedAtMs']<=stamp.timestamp()*1000<=call['completedAtMs'],
      'original immutable v13 reservation must match the same refusal')
 return policy,{'issuer_intent':pin,'original_pub_turn':turn_id,'failed_issuer_command':command_id,
                'zero_key_call':key_id,'preflight_event_id':events[0]['event_id'],
                'failure_output_sha256':hashlib.sha256(output.encode()).hexdigest()}


@w.request_validation_context()
def register_expired_zero_write_refresh(root,run_id,*,after_forward_repair=False,after_preissue_expiry=False,after_policy_timing=False,after_issuer_project_refusal=False,after_main_move=False):
 """Retain completed previews and admit the exact bounded zero-write successor."""
 import goal_delivery_runtime as g
 from en2_preview_origin import read_historical_zero_write
 root=Path(root).resolve();ctx=context(root);records=history.retired_receipts(root)
 count=5 if after_main_move else 4 if after_issuer_project_refusal else 3 if after_policy_timing else 2 if after_preissue_expiry else 1 if after_forward_repair else 0
 need(len(records)==count,'exact unconsumed zero-write recovery stage required')
 old=history._intent_path(root,count)
 need(old.is_file(),'existing original zero-write intent required')
 if after_forward_repair:
  need(run_id==history.REFUSAL_RUN,'exact refused forward preview required')
  refusal=a.document(root,history.REFUSAL)
  need(refusal.get('task_id')==TASK and refusal.get('actual_response_action')=='publish'
       and refusal.get('validator_expected_action')=='update' and refusal.get('actual_response_dry_run') is True
       and all(refusal.get(k) is False for k in ('preflight_registered','new_policy','permit','save')),
       'exact original PUB refusal before any production action required')
 if after_preissue_expiry:
  need(run_id==history.PREISSUE_RUN,'exact verified preissue expiry run required')
  spent,expiry=_verified_preissue_expiry(root)
 if after_policy_timing:
  need(run_id==history.POLICY_TIMING_RUN,'exact verified non-consuming policy timing run required')
  timing_proof=_verified_policy_timing_refusal(root)
 if after_issuer_project_refusal:
  need(run_id==history.NO_TRANSPORT_RUN,'exact original pre-transport refusal run required')
  spent,refusal_proof=_verified_issuer_project_refusal(root)
 if after_main_move:
  need(run_id==history.MAIN_MOVE_RUN and not history.live_cms_policy_rows(root),
       'exact original main-move run and no new CMS policy required')
  entry._verify_local_git(root,ctx,{'worktree':str(Path(ctx['binding']['cwd'])/'zhuangxiuwangzhan-main'),
                                  'main_sha':history.MAIN_MOVE_TO})
 original=w.file_digest(root,str(old.relative_to(root)))
 intent=a.document(root,original);policies=history.unresolved_preview_policies(root)
 need(len(policies)==1 and policies[0]['decision_id']==intent.get('policy_id')
      and policies[0].get('exact_request')==intent.get('request')
      and policies[0].get('original_authority')==ctx['authorization'],'original intent must bind its preserved policy')
 pol=policies[0]
 observed=inspect_unknown(root)
 expected_head=intent['main_sha']
 if after_main_move:
  need(expected_head==history.MAIN_MOVE_FROM,'original v14 intent must bind the displaced main')
  expected_head=history.MAIN_MOVE_TO
 need(len(observed['matches'])==1 and observed['matches'][0]['run_id']==run_id
      and observed['matches'][0]['head_sha']==expected_head,'one exact hosted run for original intent required')
 preview=read_historical_zero_write(root,run_id)
 at=w._parse_observed_at(preview.get('receipt_checked_at'))
 need(preview.get('preview_origin')=='VERIFIED_HISTORICAL_ZERO_WRITE' and at
      and (dt.datetime.now(dt.timezone.utc)-at).total_seconds()>300,
      'verified completed zero-write receipt must be expired')
 if after_main_move:
  need(preview.get('head_sha')==history.MAIN_MOVE_TO and preview.get('artifact_id')==13479895807,
       'original v14 official mismatched run and original zero-write artifact required')
 human=a.document(root,ctx['authorization']);epoch=human['selected_native']['turn']['startedAt']
 registration=a.document(root,ctx['registration'])
 created=w._parse_observed_at(a.document(root,registration['goal_contract']).get('created_at'))
 need(created is not None and created.timestamp()<=epoch,'unchanged original goal and authority required')
 if after_forward_repair:
  need(preview.get('artifact_id')==refusal.get('preview_artifact')
       and preview.get('receipt_checked_at')==refusal.get('preview_receipt_checked_at'),
       'exact previously refused official provider artifact required')
 hosted=history._read_hosted_history(created,epoch,(*[row['preview']['run_id'] for row in records],run_id))
 with w.workflow_lock(root):
  cms_policies=w.read_jsonl(root/w.POLICY_DECISIONS,where={'task_id':TASK,'action_class':'cms_write','status':'allow'})
  expected_cms=([spent] if after_preissue_expiry else [])
  if after_policy_timing or after_issuer_project_refusal or after_main_move:
   expected_cms=[row for row in cms_policies if row.get('decision_id')==history.PREISSUE_POLICY
                 and w.sha256_value(row)==records[2]['retired_cms_policy_sha256']]
   need(len(expected_cms)==1,'the only historical CMS policy must remain unchanged')
  expected_intents=set()
  if after_issuer_project_refusal:
   expected_cms.append(spent)
   expected_intents.add(root/history.ORIGINAL_ISSUER_INTENT)
   need(w.file_digest(root,history.ORIGINAL_ISSUER_INTENT)==refusal_proof['issuer_intent'],'original v13 intent changed')
  if after_main_move:
   prior=[row for row in cms_policies if row.get('decision_id')==history.NO_TRANSPORT_POLICY
          and w.sha256_value(row)==records[4]['retired_cms_policy_sha256']]
   need(len(prior)==1,'immutable spent v13 CMS policy required')
   expected_cms.extend(prior)
   expected_intents.add(root/history.ORIGINAL_ISSUER_INTENT)
  need(history.retired_receipts(root)==records and history.unresolved_preview_policies(root)==[pol]
       and cms_policies==expected_cms
       and set((root/'logs').glob('en2-forward-issuer-once-*.json'))==expected_intents,
       'no other original refresh, CMS policy or issuer intent permitted')
  snap=g.restore_goal(root,w.read_json(w.snapshot_path(root,TASK)))
  need(snap['current_state'] not in w.TERMINAL_STATES | {'paused','suspended','blocked'}
       and not w.validate_workflow_events(root,TASK),'open intact original workflow required')
  w._VALIDATION_CONTEXT.get().recheck()
  key=history.MAIN_MOVE_RETRY if after_main_move else history.NO_TRANSPORT_RETRY if after_issuer_project_refusal else history.POLICY_TIMING_RETRY if after_policy_timing else history.PREISSUE_RETRY if after_preissue_expiry else history.SUCCESSOR if after_forward_repair else history.REFRESH
  proof={'forward_refusal':history.REFUSAL} if after_forward_repair else {}
  if after_preissue_expiry:
   proof.update(expiry,retired_cms_policy_id=spent['decision_id'],retired_cms_policy_sha256=w.sha256_value(spent))
  if after_policy_timing:
   proof.update(timing_proof)
  if after_issuer_project_refusal:
   proof.update(refusal_proof,retired_cms_policy_id=spent['decision_id'],retired_cms_policy_sha256=w.sha256_value(spent))
  if after_main_move:
   proof.update(review_event_id=history.MAIN_MOVE_REVIEW,requested_head=history.MAIN_MOVE_FROM)
  event=w.append_workflow_event(root,TASK,snap['current_state'],{key:{
        'policy_id':pol['decision_id'],'policy_sha256':w.sha256_value(pol),'original_intent':original,
        'preview':preview,'hosted':hosted,'effect':'COMPLETED_ZERO_WRITE_RECEIPT_EXPIRED',
        'external_permission_issued':False,**proof}})
 return {'state':'ONE_ZERO_WRITE_REFRESH_REGISTERED','event_id':event['event_id'],
         'original_run_id':run_id,'external_permission_issued':False,'production_write':False}


if __name__=='__main__':
 import argparse
 registrations={'register-zero-write-refresh','register-forward-repair-preview','register-preissue-expiry-preview','register-policy-timing-preview','register-issuer-project-refusal-preview','register-reviewed-main-move-preview'}
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('command',choices=['selfcheck','prepare-and-selfcheck','dispatch','inspect-unknown','build-and-record-preflight','reconcile-expired-policy',*sorted(registrations)]);parser.add_argument('--policy-id');parser.add_argument('--policy-command');parser.add_argument('--failed-command');parser.add_argument('--run-id',type=int);parser.add_argument('--request');parser.add_argument('--state');parser.add_argument('--web-turn');parser.add_argument('--selfcheck-command');parser.add_argument('--output');parser.add_argument('--consume-preview-policy',action='store_true');args=parser.parse_args();root=Path(__file__).resolve().parents[1]
 try:
  prep=(args.web_turn,args.selfcheck_command,args.output)
  need(args.command=='build-and-record-preflight' or not any(prep),'preflight options only apply to build-and-record-preflight')
  need(args.command=='build-and-record-preflight' or not args.consume_preview_policy,'combined preview policy requires exact preflight')
  need(args.command=='prepare-and-selfcheck' or args.state is None,'state option only applies to prepare-and-selfcheck')
  need(args.command=='reconcile-expired-policy' or args.failed_command is None,'failed-command is only for expired-policy reconciliation')
  need(args.command in registrations or args.run_id is None,'run-id is only for zero-write refresh registration')
  if args.command=='selfcheck':
   need(isinstance(args.request,str) and args.request and args.policy_id is None and args.policy_command is None,'exact original preview request path required');result=selfcheck(root,args.request)
  elif args.command=='prepare-and-selfcheck':
   need(args.request and args.state and args.policy_id is None and args.policy_command is None,'exact fresh state and new request output required')
   result=prepare_and_selfcheck(root,args.state,args.request)
  elif args.command=='build-and-record-preflight':
   need(args.request and all(prep) and args.policy_id is None and args.policy_command is None,'exact request, WEB turn, native selfcheck and new output required')
   result=build_and_record_preflight(root,args.request,*prep,consume_preview_policy=args.consume_preview_policy)
  elif args.command=='dispatch':
   need(isinstance(args.policy_id,str) and args.policy_id and isinstance(args.policy_command,str) and args.policy_command and args.request is None,'original policy ID and native command ID required');result=dispatch(root,args.policy_id,args.policy_command)
  elif args.command=='reconcile-expired-policy':
   need(args.policy_id and args.failed_command and args.policy_command is None and args.request is None,'original policy and failed dispatch command required')
   result=reconcile_expired_policy(root,args.policy_id,args.failed_command)
  elif args.command in registrations:
   need(args.run_id and args.policy_id is None and args.policy_command is None and args.request is None,'exact original run ID required')
   result=register_expired_zero_write_refresh(root,args.run_id,after_forward_repair=args.command=='register-forward-repair-preview',
                                             after_preissue_expiry=args.command=='register-preissue-expiry-preview',
                                             after_policy_timing=args.command=='register-policy-timing-preview',
                                             after_issuer_project_refusal=args.command=='register-issuer-project-refusal-preview',
                                             after_main_move=args.command=='register-reviewed-main-move-preview')
  else:
   need(args.policy_id is None and args.policy_command is None and args.request is None,'read-only unknown inspection does not consume a policy');result=inspect_unknown(root)
  print(json.dumps(result,ensure_ascii=False,indent=2))
 except (w.WorkflowError,ValueError,KeyError,OSError,subprocess.SubprocessError) as error:parser.exit(1,str(error)+'\n')
