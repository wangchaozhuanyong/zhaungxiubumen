"""Exact original external WEB action-source compatibility. No GitHub/website writes.
Uses existing workflow events, policy decisions and approval ledger; no QA or new grant.
"""
from pathlib import Path
import json,hashlib,datetime as dt,re,subprocess,argparse
import workflow_control as w
from tools import shop_office_six_field_execution as cms
TASK=cms.TASK;SCOPE=cms.SCOPE;AUTH=cms.AUTH;CONTRACT=cms.CONTRACT
ROLE='designated-development';OWNER='seo-content-research';REPO='wangchaozhuanyong/zhuangxiuwangzhan';REPO_ID=1248188229
SITE=Path('<WEBSITE_PROJECT_ROOT>')
WORKTREE=SITE/'.worktrees/shop-office-six-and-five-release-20261025-v1'
BRANCH='codex/shop-office-six-and-five-release-20261025-v1';COMMIT='865037f7a8a1a9b4aa5d831f42d40198c032a52c';ORIGINAL_COMMIT='a21e9ea442e8584cbd95f32a79bfffb8281b3fec'
PARENT='1f1c9903601cb9d767239221eb1af69f22310ebe';TREE='4d48e5cc3d9a102c07a530ebae0213b7418e1ba4'
TYPED=SITE/'reports/shop-office-six-and-five-implementation-release-20261025-v1/CANDIDATE-DELIVERY-TYPED-v2.json'
TYPED_SHA='b6d9b04dcbadc1593099779c1f4be1612a40ec14678b0d501b7aed1ad0d0e0e2'
ORIGINAL_REGISTRATION={'path':'logs/handoffs/2026-10-25-shop-office-six-field-execution-wiring-v1/exact-WEB-production-registration-v4/EXACT-ORIGINAL-WEB-PRODUCTION-SOURCE-REGISTRATION.json','sha256':'a7febc0c14c9040ed2f825dd6c25f30beea6b36a60955b0e81f4c2040d11030f','size':3043}
R3_SCOPE='company.example:edge:rbsnyexjifounogswrjp:content-publish'
PAGES_SCOPE='company.example:shop-office:zh-en:four-pages'
R3_WORKFLOW='.github/workflows/supabase-content-publish-r3.yml'
OPS={'git_push':('site_ci_prepare',SCOPE),'pull_request':('site_ci_prepare',SCOPE),'official_ci':('site_ci_prepare',SCOPE),'merge':('site_ci_prepare',SCOPE),'r3_dispatch':('site_ci_prepare',R3_SCOPE),'edge_deploy':('site_publish',R3_SCOPE),'pages_deploy':('site_publish',PAGES_SCOPE)}
ROOT=Path(__file__).resolve().parents[1]
def require(ok,msg):
 if not ok:raise w.WorkflowError('shop/office original WEB execution: '+msg)
def applies(task,action_class):return task==TASK and action_class in {'site_ci_prepare','site_publish'}
def doc(root,pin):return cms.doc(root,pin)
def git(*args):
 c=subprocess.run(['git',*args],cwd=WORKTREE,capture_output=True,timeout=15)
 require(c.returncode==0,'exact local Git object unavailable; no remote write or guessed source');return c.stdout

def candidate():
 raw=TYPED.read_bytes();require(hashlib.sha256(raw).hexdigest()==TYPED_SHA and len(raw)==16190,'unchanged real WEB typed candidate required')
 d=json.loads(raw);require((d.get('task_id'),d.get('scope'),d.get('commit'),d.get('base'),d.get('tree'),d.get('branch'))==(TASK,SCOPE,COMMIT,PARENT,TREE,BRANCH),'exact original stage/candidate/parent/tree/branch')
 require(git('show','-s','--format=%H %P %T',COMMIT).decode().strip()==COMMIT+' '+ORIGINAL_COMMIT+' '+TREE,'real exact Git commit/parent/tree')
 hashes=d.get('file_sha256',{});require(len(hashes)==19 and len(set(hashes))==19,'exact original fourteen plus five causal CI/test paths')
 for p,sha in hashes.items():require(not Path(p).is_absolute()and '..'not in Path(p).parts and hashlib.sha256(git('show',COMMIT+':'+p)).hexdigest()==sha,'actual reviewed Git file differs: '+p)
 patch=SITE/'backups/shop-office-six-and-five-implementation-release-20261025-v1/EXACT-SHOP-OFFICE-CANDIDATE-CI-v2.patch'
 require(hashlib.sha256(patch.read_bytes()).hexdigest()==d['patch_sha256']=='60c9f52c586cbe0b05b9911f9428e3a07990cd2c2dfe9f766f4dd871f30d1882','exact original source patch')
 original_path=TYPED.with_name('CANDIDATE-DELIVERY-TYPED.json');old_raw=original_path.read_bytes()
 require(hashlib.sha256(old_raw).hexdigest()=='62817e4488430684341c42fd9f2ba1b9516daa04868d5a84978864afc08f7500','unchanged original fourteen-file source')
 old=json.loads(old_raw);require(all(hashes.get(p)==sha for p,sha in old['file_sha256'].items()),'causal CI repair cannot change original fourteen production/test bytes')
 expected={'.github/workflows/r3-managed-cms-pr-ci.yml','src/lib/contentPublishOwnerPublisherThree.test.ts','src/lib/contentPublishUnifiedContent.test.ts','src/lib/managedContentPublishWorkflow.test.ts','src/lib/topicClusterBlogRecordsScript.test.ts'}
 require(set(git('diff','--name-only',ORIGINAL_COMMIT,COMMIT).decode().splitlines())==expected,'only the exact five actual CI/test source changes')
 final_raw=TYPED.with_name('OFFICIAL-CI-HEAD865-FINAL.json').read_bytes();require(hashlib.sha256(final_raw).hexdigest()=='c79f187c75b77f2f23890bc1cdf52795e1243305b09046f7fd191b0ac368d5c3','unchanged current-head official check readback')
 final=json.loads(final_raw);checks=final.get('latest_checks_by_name',{})
 require(final.get('head')==COMMIT and set(checks)=={'furniture-page-pr-checks','interaction-standards','r3-managed-cms-pr-checks'}and all(v.get('head_sha')==COMMIT and v.get('status')=='completed'and v.get('conclusion')=='success'for v in checks.values()),'actual latest same-head official CI, never old cancelled or production R3 run')
 return d

def authority(root):
 snap=cms.authority(root);goal=snap['goal_delivery'];raw=w.read_json(Path(root)/'data/department-registry.json');b=raw.get('collaboration_bindings',{}).get(ROLE,{})
 exact=goal['execution_bounds']['website_executor']
 require(goal['primary_owner']==OWNER and any(d=={'sender_department':OWNER,'target_department':ROLE,'scope':SCOPE}for d in goal['collaboration_scopes'])
  and b.get('thread_id')==exact['task_id']and b.get('title')==exact['title']and b.get('cwd')==exact['project_cwd']
  and Path(exact['Git_root']).resolve()==SITE and Path(b.get('cwd','')).resolve()==SITE.parent,'unchanged original declared external WEB identity/project/directory')
 require(set(goal['execution_bounds']['approved_necessary_actions'])=={'exact_target_wiring','bounded_website_code_change','commit_push_CI_deploy','exact_CMS_six_fields_Save','four_URL_public_readback'},'original complete owner-approved action scope')
 require(b.get('project_id')and b['project_id']!=cms.PROJECT,'external WEB project cannot be substituted by SEO2/SYS')
 return snap,b,candidate()

def _legacy_registration_document(root):
 snap,b,c=authority(root)
 return {'schema':'shop-office-original-WEB-execution-registration/v1','task_id':TASK,'scope':SCOPE,'action_class':'site_ci_prepare','original_owner':OWNER,'execution_department':ROLE,'executor_binding':{k:b.get(k)for k in ['thread_id','title','project_id','cwd']},'goal_contract':CONTRACT,'authorization_pin':AUTH,'candidate_delivery':{'path':str(TYPED),'sha256':TYPED_SHA,'size':16190},'candidate_commit':COMMIT,'candidate_parent':ORIGINAL_COMMIT,'complete_diff_base':PARENT,'causal_predecessor':ORIGINAL_REGISTRATION,'original_fourteen_file_bytes_unchanged':True,'candidate_tree':TREE,'branch':BRANCH,'operations':{k:{'action_class':v[0],'scope':v[1]}for k,v in OPS.items()},'future_main_or_run_authorized':False,'external_write_or_permission_issued':False}

def _legacy_registration(root):
 rows=[e for e in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS)if e.get('task_id')==TASK and e.get('details',{}).get('shop_office_WEB_execution_registration')]
 require(len(rows)>=2 and not w.validate_workflow_events(root,TASK),'original plus one authentic causal WEB source registration required')
 require(rows[0]['details']['shop_office_WEB_execution_registration']==ORIGINAL_REGISTRATION and rows[1]['details'].get('supersedes_WEB_registration')==ORIGINAL_REGISTRATION,'preserve original append-only source, not replacement')
 doc(root,ORIGINAL_REGISTRATION);pin=rows[1]['details']['shop_office_WEB_execution_registration'];require(doc(root,pin)==_legacy_registration_document(root),'registered current causal candidate/identity/authorization differs');return pin


def action_id(op,main=None,source_commit=None):
 require(op in OPS,'known original operation');suffix='-'+main[:12]if op in {'r3_dispatch','edge_deploy','pages_deploy'}and isinstance(main,str)else''
 return 'shop-office-'+(source_commit or CURRENT_COMMIT)[:12]+'-'+op.replace('_','-')+suffix

def reference(main,source_commit=None):return 'apr-'+w.sha256_value([TASK,AUTH,ROLE,action_id('edge_deploy',main,source_commit),R3_SCOPE,main])[:20]

def _source_context(root,req):
 _,b,_=authority(root);op=req.get('operation');require(op in OPS,'exact original registered operation only');state=req.get('state',{});c=_source_candidate(root,state.get('candidate_commit'));COMMIT=c['commit'];BRANCH=c['branch']
 require(req.get('task_id')==TASK and req.get('department')==ROLE and req.get('scope')==OPS[op][1]and req.get('action_class')==OPS[op][0]
  and req.get('source_project_id')==cms.PROJECT and req.get('execution_project_id')==b['project_id']and req.get('authorization_changes',[])==[], 'exact original external actor/projects/action/scope; no expansion')
 require(state.get('repository')==REPO and state.get('repository_id')==REPO_ID and state.get('candidate_commit')==COMMIT
  and state.get('branch')==BRANCH,'actual repository/candidate/branch facts required')
 main=None
 if op in {'r3_dispatch','edge_deploy','pages_deploy'}:
  main=state.get('main_sha');require(re.fullmatch('[0-9a-f]{40}',str(main))and state.get('remote_main_sha')==main,'actual current remote/main SHA, never candidate guessed as main')
  for p,sha in c['file_sha256'].items():require(hashlib.sha256(git('show',main+':'+p)).hexdigest()==sha,'actual final main changed the reviewed candidate; exact causal successor needed')
 else:require(state.get('head_sha')==COMMIT,'current original candidate head required')
 require(req.get('action_id')==action_id(op,main,source_commit=COMMIT),'exact operation/current-version action identity')
 desired={'operation':op,'repository':REPO,'candidate_commit':COMMIT,'branch':BRANCH,'force':False,'admin_bypass':False}
 if main:desired['expected_main_sha']=main
 if op in {'pull_request','merge'}:desired['base_branch']='main'
 if op=='merge':
  ci=state.get('ci_run',{});require(type(ci.get('id'))is int and ci['id']>0 and ci.get('head_sha')==COMMIT and ci.get('conclusion')=='success'and ci.get('path')=='.github/workflows/r3-managed-cms-pr-ci.yml','actual successful official managed-CMS CI for this exact candidate required')
  pr=state.get('pull_request',{});require(type(pr.get('number'))is int and pr['number']>0 and pr.get('head_sha')==COMMIT and pr.get('base_branch')=='main'and pr.get('mergeable')=='MERGEABLE'and pr.get('merge_state')=='CLEAN','actual exact clean PR/official checks before merge');desired.update(pull_number=pr['number'],merge_method='merge')
 if op=='official_ci':require(type(state.get('ci_run',{}).get('id'))is int and state['ci_run']['id']>0 and state['ci_run'].get('head_sha')==COMMIT and state['ci_run'].get('conclusion')=='success'and state['ci_run'].get('path')=='.github/workflows/r3-managed-cms-pr-ci.yml','actual successful same-candidate official CI required; do not invent or rerun')
 if op=='r3_dispatch':desired.update(workflow=R3_WORKFLOW,mode='deploy',edge_function='content-publish',approval_id=reference(main,source_commit=COMMIT),task_id=TASK,release_action_id=action_id('edge_deploy',main,source_commit=COMMIT),release_action_class='site_publish',release_scope=R3_SCOPE)
 if op=='edge_deploy':
  run=state.get('r3_run',{});require(type(run.get('id'))is int and run['id']>0 and run.get('run_attempt')==1 and run.get('event')=='workflow_dispatch'
   and run.get('head_sha')==main and run.get('head_branch')=='main'and run.get('path')==R3_WORKFLOW
   and run.get('repository',{}).get('full_name')==REPO and run['repository'].get('id')==REPO_ID
   and run.get('status')in {'queued','in_progress','waiting','pending'}and run.get('conclusion')is None,'actual first pending R3 run for exact current main/repository required')
  desired.update(workflow=R3_WORKFLOW,edge_function='content-publish',run_id=run['id'],run_attempt=1,approval_id=reference(main,source_commit=COMMIT))
 if op=='pages_deploy':desired.update(workflow='.github/workflows/cloudflare-pages-deploy.yml',manual_only_if_no_successful_same_head_run=True)
 return op,state,b,desired

def source_state(root,req):
 op,state,b,desired=_source_context(root,req)
 require(req.get('desired')==desired,'exact requested effects only; no additional field/branch/workflow/force bypass')
 return op,state,b,desired

def request_base(root,op,state):
 require(op in OPS and state.get('candidate_commit')==CURRENT_COMMIT,'new requests require the current real causal head')
 _,b,_=authority(root);main=state.get('main_sha')if op in {'r3_dispatch','edge_deploy','pages_deploy'}else None
 req={'task_id':TASK,'department':ROLE,'action_id':action_id(op,main),'action_class':OPS[op][0],'scope':OPS[op][1],'source_project_id':cms.PROJECT,'execution_project_id':b['project_id'],'operation':op,'state':state,'observed_at':state.get('observed_at'),'authorization_changes':[]}
 req['desired']=_source_context(root,req)[3];return req

def native(root,pin,command):
 import goal_delivery_runtime as g
 _,b,_=authority(root);page=g._native_document(root,pin);thread=page.get('thread',{})
 require(all(thread.get(k)==b[v]for k,v in {'id':'thread_id','title':'title','cwd':'cwd'}.items()),'actual original external WEB native identity required; no borrowed SYS/SEO2 source')
 calls=[(t,m)for t in page.get('turns',[])for m in t.get('items',[])if m.get('id')==command]
 require(len(calls)==1,'one actual WEB native command');t,m=calls[0]
 require(not t.get('error')and type(t.get('startedAt'))in {int,float}and t['startedAt']<=dt.datetime.now(dt.timezone.utc).timestamp()and m.get('type')=='commandExecution'and m.get('status')=='completed'and m.get('exitCode')==0 and Path(m.get('cwd','')).resolve()==WORKTREE,'real successful original WEB worktree command')
 return w._source_continuation_execution_output(m)

def external_source(pin,parse=True):
 require(isinstance(pin,dict)and set(pin)=={'path','sha256','size'},'exact external source pin')
 p=Path(pin['path']);require(p.is_absolute()and not p.is_symlink()and (p.resolve().is_relative_to(SITE/'reports')or p.resolve().is_relative_to(SITE/'backups')),'only original website report/backup source')
 raw=p.read_bytes();require(hashlib.sha256(raw).hexdigest()==pin['sha256']and len(raw)==pin['size'],'external source bytes changed')
 return json.loads(raw)if parse else raw

def validate_request(root,req):
 op,state,b,desired=source_state(root,req);c=_source_candidate(root,state['candidate_commit']);is_current=state['candidate_commit']==CURRENT_COMMIT;is_fa6=state['candidate_commit']==FA6_COMMIT;delivery_sha=CURRENT_TYPED['sha256']if is_current else(_fa6_module(root).CURRENT_TYPED['sha256']if is_fa6 else TYPED_SHA);intent=w.sha256_value({k:v for k,v in req.items()if k not in {'facts','self_check','backup','rollback'}})
 for k in ['facts','self_check','backup','rollback']:
  d=doc(root,req.get(k));require(all(d.get(v)==req.get(v)for v in ['task_id','department','action_id','action_class','scope'])and d.get('intent_sha256')==intent,'exact request-bound '+k)
  if k=='facts':
   require(d.get('state')==state and state.get('observed_at')==req.get('observed_at'),'actual current state, no synthetic observation date')
   raw=native(root,d.get('actual_native'),d.get('command_id'));require(json.loads(raw).get('state')==state,'native full GitHub/Git factual readback must equal frozen state')
  if k=='self_check':
   require(d.get('status')=='PASS','actual WEB selfcheck required');raw=native(root,d.get('actual_native'),d.get('command_id'));require(intent.encode()in raw and delivery_sha.encode()in raw,'actual selfcheck binds exact candidate and request intent')
  if k=='backup':
   raw=external_source(d.get('source_backup'),False);require(hashlib.sha256(raw).hexdigest()==c['patch_sha256'],'exact actual fourteen-file rollback patch, not another backup')
  if k=='rollback':
   rehearsal=external_source(d.get('source_recovery'))
   if is_current or is_fa6:
    runbook=doc(root,d.get('production_recovery'));require(runbook==(current_production_recovery(root)if is_current else _fa6_module(root).current_production_recovery(root)),'exact current physical source/CMS recovery carrier, not old invalid scope')
    require(rehearsal.get('base')==c['base'] and rehearsal.get('candidate_file_sha256')==c['causal_diff_file_sha256']and rehearsal.get('commit')==c['commit'] and rehearsal.get('actual_forward_reverse_byte_exact')is True,'actual current three-file inverse rehearsal')
   else:
    runbook=external_source(d.get('production_recovery'))
    require(rehearsal.get('base')==PARENT and rehearsal.get('candidate_sha256')==c['file_sha256']and rehearsal.get('actual_forward_reverse_byte_exact')is True and rehearsal.get('commit')==COMMIT,'actual source inverse rehearsal for same fourteen files')
    require(runbook.get('task_id')==TASK and runbook.get('candidate_commit')==ORIGINAL_COMMIT and runbook.get('source_recovery',{}).get('R3_source_restore'),'actual original production recovery plan')
   require(d.get('unknown_effect_replay_allowed')is False,'unknown effects cannot be replayed')
   require({v['row_id']:v['fields']for v in runbook.get('CMS_recovery',{}).get('exact_targets',[])}=={v[0]:v[2]for v in cms.ROWS.values()},'exact two-row six-field recovery only')
 return op,state,b

def record_preflight(root,path):
 pin=w.file_digest(root,path);item=doc(root,pin);req=doc(root,item.get('request'));op,_,_=validate_request(root,req);require_current_request(root,req)
 require(all(item.get(k)==req.get(k)for k in ['task_id','department','action_id','action_class','scope'])and item.get('payload_sha256')==item['request']['sha256']
  and item.get('risk_level')==('R3'if op in {'r3_dispatch','edge_deploy'}else'R2'),'actual action/request/risk preflight')
 with w.workflow_lock(root):
  snap,_,_=authority(root);rows=[e for e in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS)if e.get('task_id')==TASK and e.get('details',{}).get('shop_office_WEB_preflight',{}).get('action_id')==req['action_id']]
  if rows and rows[-1]['details']['shop_office_WEB_preflight']['input']==pin:return {'result':'duplicate_ignored','input':pin,'permission_issued':False}
  require(not any(p.get('task_id')==TASK and p.get('action_id')==req['action_id']and p.get('status')=='allow'for p in w.read_jsonl(Path(root)/w.POLICY_DECISIONS)),'issued/unknown original action cannot be refreshed or replayed')
  if rows:
   prior=doc(root,rows[-1]['details']['shop_office_WEB_preflight']['request']);require(all(prior.get(k)==req.get(k)for k in ['task_id','department','action_id','action_class','scope','operation','desired']),'refresh only observations, not approved effect')
  ev=w.append_workflow_event(root,TASK,snap['current_state'],{'shop_office_WEB_preflight':{'action_id':req['action_id'],'input':pin,'request':item['request'],'original_authority':AUTH}})
 return {'result':'recorded','event_id':ev['event_id'],'input':pin,'permission_issued':False}

def preflight(root,action,action_class,scope,department):
 require(department==ROLE,'original WEB only');rows=[e for e in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS)if e.get('task_id')==TASK and e.get('details',{}).get('shop_office_WEB_preflight',{}).get('action_id')==action]
 require(rows and not w.validate_workflow_events(root,TASK),'normal exact registered current WEB preflight required')
 pin=rows[-1]['details']['shop_office_WEB_preflight']['input'];item=doc(root,pin);req=doc(root,item['request']);validate_request(root,req)
 require((req['action_class'],req['scope'],req['department'])==(action_class,scope,department),'exact preflight caller identity');return item,req,pin

def authorization_precheck(root,request):
 snap,_,_=authority(root);registration(root);role=request.get('sender_department');require(role==request.get('department',role)==ROLE,'actual WEB authorization precheck, no substituted owner')
 item,req,pin=preflight(root,request.get('action_id'),request.get('action_class'),request.get('scope'),ROLE);require_current_request(root,req)
 require(request.get('payload_sha256')==item['request']['sha256'],'exact current request digest')
 return {'schema':'goal-authorization-precheck/v1','task_id':TASK,'status':'within_original_authorization','reasons':['actual_original_full_stage_external_WEB_action_source'],'original_authorization':AUTH,'needs_human_confirmation':False,'actual_action_allowed':False,'external_permission_issued':False,'next_owner':ROLE,'next_action':'fresh normal policy and original protected platform gates','preflight':pin}

def policy(root,requested):
 require(not requested.get('approval_id')and not requested.get('target_department')and not requested.get('target_project_id'),'no borrowed approvals or target route')
 item,req,pin=preflight(root,requested.get('action_id'),requested.get('action_class'),requested.get('scope'),requested.get('department'));require_current_request(root,req)
 require(requested.get('source_project_id')==cms.PROJECT and requested.get('payload_sha256')==item['request']['sha256'],'exact original action request/project')
 op,state,_=validate_request(root,req);observed=w._parse_observed_at(req.get('observed_at'));require(observed and 0<=(dt.datetime.now(dt.timezone.utc)-observed).total_seconds()<=300,'fresh actual execution state required; report itself does not expire')
 if op=='git_push'and state.get('remote_branch_sha')==CURRENT_COMMIT:
  return {'status':'actual_same_head_no_new_push','actual_action_allowed':False,'task_id':TASK,'source_request':item['request']},[]
 if op=='r3_dispatch'and state.get('r3_run',{}).get('head_sha')==state.get('main_sha'):
  require(state['r3_run'].get('path')==R3_WORKFLOW and state['r3_run'].get('run_attempt')==1,'existing exact first R3 run must be read back, not substituted')
  return {'status':'actual_existing_R3_run_readback_no_new_dispatch','actual_action_allowed':False,'task_id':TASK,'source_request':item['request']},[]
 if op=='official_ci' or op=='pages_deploy'and state.get('pages_run',{}).get('head_sha')==state.get('main_sha')and state['pages_run'].get('conclusion')=='success':
  return {'status':'actual_same_head_readback_no_new_dispatch','actual_action_allowed':False,'task_id':TASK,'action_id':req['action_id'],'source_request':item['request'],'permission_issued':False},[]
 key=w.sha256_value([TASK,ROLE,req['action_id'],req['action_class'],req['scope']])
 with w.workflow_lock(root):
  require(not any(v.get('autonomous_action_key')==key and v.get('status')=='allow'for v in w.read_jsonl(Path(root)/w.POLICY_DECISIONS)),'actual or unknown action already issued; original readback, no replay')
  row={**requested,'status':'preflight_ready_not_a_permit','actual_action_allowed':False,'approval_basis':'department_autonomous_delivery_v1','original_authority':AUTH,'exact_request':item['request'],'autonomous_action_key':key,'checked_at':w.utc_timestamp(),'assistant_approval_required':False,'external_execution_department':ROLE,'platform_permission_issued':False}
  if requested.get('consume_approval'):
   if op=='edge_deploy':
    apr=w.effective_approvals(root).get(reference(state['main_sha']));require(apr and apr.get('status')=='active'and apr.get('source_preflight')==pin,'actual current exact R3 approval reference required')
    w.append_jsonl_locked(Path(root)/w.APPROVAL_LEDGER,{**apr,'status':'consumed','consumed_at':w.utc_timestamp()})
   row.update(status='allow',actual_action_allowed=True,approval_status='consumed_for_original_exact_autonomous_action',decision_id='pol-'+w.sha256_value([row,key])[:20]);w.append_jsonl_locked(Path(root)/w.POLICY_DECISIONS,row)
 return row,[Path(root)/w.POLICY_DECISIONS]

def record_approval(root,**kwargs):
 if kwargs.get('revoke'):
  authority(root)
  with w.workflow_lock(root):
   old=w.effective_approvals(root).get(kwargs.get('approval_id'));require(old and old.get('status')=='active'and old.get('approval_basis')=='original_shop_office_full_stage_actual_WEB_R3_source'and all(old.get(k)==kwargs.get(k)for k in ['task_id','action_id','action_class','scope']),'one exact still-active original approval; consumed/unknown effects need readback')
   row={**old,'status':'revoked','changed_at':w.utc_timestamp()};w.append_jsonl_locked(Path(root)/w.APPROVAL_LEDGER,row)
  return {**row,'result':'revoked','platform_allowlist_not_changed':True},[Path(root)/w.APPROVAL_LEDGER]
 require(kwargs.get('source_evidence'),'exact active R3 source evidence required; no synthetic approval')
 item=doc(root,w.file_digest(root,kwargs['source_evidence']));req=doc(root,item.get('request'));op,state,_=validate_request(root,req);require_current_request(root,req)
 require(op=='edge_deploy'and all(kwargs.get(k)==req[k]for k in ['task_id','action_id','action_class','scope']),'only exact current pending R3 action')
 selected,_,pin=preflight(root,req['action_id'],req['action_class'],req['scope'],ROLE);require(selected==item,'normal preflight event required')
 human=doc(root,AUTH);require(kwargs.get('source_thread_id')==human['source_thread_id']and kwargs.get('source_message_ref')==human['message']['id'],'actual original human grant, not new owner/A1 signature')
 main=state['main_sha'];apr=reference(main);require(kwargs.get('approval_id','')in {'',apr},'source-derived exact approval reference')
 now=dt.datetime.now(dt.timezone.utc);observed=w._parse_observed_at(req.get('observed_at'));require(observed and 0<=(now-observed).total_seconds()<=300,'fresh pending run before short-lived approval')
 with w.workflow_lock(root):
  existing=w.effective_approvals(root).get(apr)
  if existing:
   require(existing.get('status')=='active'and existing.get('source_preflight')==pin,'used/revoked/other source cannot reissue');return {**existing,'result':'duplicate_ignored'},[Path(root)/w.APPROVAL_LEDGER]
  binding={'version':'r3-release-approval/v1','taskId':TASK,'actionId':req['action_id'],'actionClass':'site_publish','scope':R3_SCOPE,'approvalId':apr,'expectedSha':main,'repository':REPO,'repositoryId':REPO_ID,'ref':'refs/heads/main','workflowRef':REPO+'/'+R3_WORKFLOW+'@refs/heads/main','environment':'production-supabase','eventName':'workflow_dispatch','runId':str(state['r3_run']['id']),'runAttempt':1,'singleUse':True,'status':'active','issuedAt':now.isoformat(),'expiresAt':(now+dt.timedelta(minutes=15)).isoformat()}
  binding['payloadSha256']=hashlib.sha256(json.dumps(binding,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
  row={'schema_version':'1.0','approval_id':apr,'task_id':TASK,'action_id':req['action_id'],'action_class':'site_publish','scope':R3_SCOPE,'granted_by':'owner','granted_at':w.utc_timestamp(),'source_thread_id':human['source_thread_id'],'source_message_ref':human['message']['id'],'status':'active','single_use':True,'approval_basis':'original_shop_office_full_stage_actual_WEB_R3_source','original_human_authorization_pin':AUTH,'source_preflight':pin,'expected_main_sha':main,'actual_R3_run_id':state['r3_run']['id'],'execution_department':ROLE,'platform_binding':binding,'platform_permission_issued':False}
  w.append_jsonl_locked(Path(root)/w.APPROVAL_LEDGER,row)
 return {**row,'result':'recorded'},[Path(root)/w.APPROVAL_LEDGER]

def describe(root):
 d=registration_document(root);return {'registration_input':d,'registration_command':['python3','tools/goal_delivery_runtime.py','approved-action-record','--task-id',TASK,'--input','<frozen registration JSON>'],'preflight_command':['python3','tools/goal_delivery_runtime.py','preflight-record','--task-id',TASK,'--input','<actual WEB preflight JSON>'],'task_and_delivery_scope':SCOPE,'site_scopes':{'edge_deploy':R3_SCOPE,'pages_deploy':PAGES_SCOPE},'operations':OPS,'R3_reference':'only after actual final main: reference(main); public audit reference before run is not approval','future_main_run_placeholder_is_permission':False,'actual_permission_issued':False}
def build_preflight(root,base_path,facts_native,facts_command,self_native,self_command,out_path):
 base=doc(root,w.file_digest(root,base_path));require_current_request(root,base);source_state(root,base);c=current_candidate(root);intent=w.sha256_value(base)
 out=w.safe_path(root,out_path);require(not out.exists(),'immutable original WEB input directory');out.mkdir(parents=True)
 ext=lambda p:{'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'size':p.stat().st_size}
 meta={k:base[k]for k in ['task_id','department','action_id','action_class','scope']}|{'intent_sha256':intent}
 reports=SITE/'reports/shop-office-six-and-five-implementation-release-20261025-v1'
 docs={'facts':meta|{'state':base['state'],'actual_native':w.file_digest(root,facts_native),'command_id':facts_command},'self_check':meta|{'status':'PASS','actual_native':w.file_digest(root,self_native),'command_id':self_command},'backup':meta|{'source_backup':c['source_patch']},'rollback':meta|{'source_recovery':c['source_recovery_rehearsal'],'production_recovery':w.file_digest(root,CURRENT_RECOVERY_PATH),'unknown_effect_replay_allowed':False}}
 req=dict(base)
 for k,v in docs.items():w.atomic_write_json(out/(k+'.json'),v);req[k]=w.file_digest(root,str((out/(k+'.json')).relative_to(root)))
 validate_request(root,req);w.atomic_write_json(out/'request.json',req)
 item={k:req[k]for k in ['task_id','department','action_id','action_class','scope']}|{'request':w.file_digest(root,str((out/'request.json').relative_to(root))),'payload_sha256':w.file_digest(root,str((out/'request.json').relative_to(root)))['sha256'],'risk_level':'R3'if req['operation']in {'edge_deploy','r3_dispatch'}else'R2'}
 w.atomic_write_json(out/'preflight.json',item);return {'preflight':w.file_digest(root,str((out/'preflight.json').relative_to(root))),'external_permission_issued':False}


CURRENT_COMMIT='035b08ea42dec08a71bb8d0e6ad2f8971e58e741'
CURRENT_PARENT='a60c1a454bf565e814aa4141a2d6f0fb4b8f52aa'
CURRENT_TREE='bbf6155dd490e173c92d391b4e80db59a1d5c801'
CURRENT_BRANCH='codex/shop-office-physical-cms-scope-current-20261025-v3'
CURRENT_TYPED={'path':str(TYPED.with_name('CANDIDATE-DELIVERY-TYPED-v5-CURRENT-BASE.json')),'sha256':'f0d2b40a7c6fda1bc12b5b1d155906df20d3f048fc992e92c5e92658e9c3dce5','size':10505}
PRECEDING_PRODUCTION={'path':str(TYPED.with_name('ACTUAL-CURRENT-A60-PRODUCTION-BASE-v5.json')),'sha256':'8c25ecbd4c3723cf3fba0117a3f0d5f295e430c6c5b120644b2ae03ca4494b48','size':1513}
LEGACY_PRODUCTION_RECOVERY={'path':str(TYPED.with_name('PRODUCTION-RECOVERY-RUNBOOK.json')),'sha256':'961c57a8948c670f507d3cf9bd953f658fd75a246b245cddc3010afb7a0bf02f','size':4087}
CURRENT_RECOVERY_PATH='logs/handoffs/2026-10-25-shop-office-six-field-execution-wiring-v1/exact-WEB-current-head035b-source-v10/EXACT-CURRENT-MATERIAL-SOURCE-PRODUCTION-RECOVERY-v10.json'
PHYSICAL_DIFF_PATHS=frozenset({'scripts/managed-cms-targets-shop-office-six-field-v4.mjs','src/lib/contentPublishShopOfficeSixFields.test.ts','supabase/functions/_shared/shop-office-six-field-targets.ts'})

FA6_COMMIT='fa6b611fbf9e07b1d2d22a6c6f8f3f2cd3870825'
FA6_MODULE={'path':'logs/handoffs/2026-10-25-shop-office-six-field-execution-wiring-v1/exact-WEB-physical-head-fa6b-source-v9/shop_office_web_execution.py','sha256':'8815c175ae12816f5b5a794835c8d5dd5a485141ca5da77e0e91ca6ecf3ea078','size':40658}
MATERIAL_PATH='supabase/functions/content-publish/service.ts'
MATERIAL_BEFORE='5105497782b0c082dbdc4f91321be80e6e56fa77eb09fb1de19fa367f53be5b1'
MATERIAL_CURRENT='8bfc6c7b8f709ed8d3236b49ccc4951ae5e2fbbccf72860877cc50bdda5641f3'

def _fa6_module(root):
 """Reuse the actually adopted immutable predecessor solely as its historical reader."""
 import importlib.util,sys
 require(w.file_digest(root,FA6_MODULE['path'])==FA6_MODULE,'unchanged actually adopted fa6 source required')
 name='_shop_office_adopted_fa6_8815c175'
 if name not in sys.modules:
  spec=importlib.util.spec_from_file_location(name,w.safe_path(root,FA6_MODULE['path']))
  module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);sys.modules[name]=module
 return sys.modules[name]

def _fa6_registration(root):
 old=_fa6_module(root)
 rows=[e for e in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS)if e.get('task_id')==TASK and e.get('details',{}).get('shop_office_WEB_execution_registration')]
 require(len(rows)>=3 and not w.validate_workflow_events(root,TASK),'actual intact original fa6 registration prefix required')
 original=rows[0]['details']['shop_office_WEB_execution_registration'];previous=rows[1]['details']['shop_office_WEB_execution_registration'];row=rows[2]
 pin={'path':'logs/handoffs/2026-10-25-shop-office-six-field-execution-wiring-v1/exact-WEB-physical-head-fa6b-source-v9/EXACT-FA6B-NORMAL-WEB-SOURCE-REGISTRATION.json','sha256':'b538803c3163a4986e86afaad779673741aceb7956c68150c18065f3e345b77d','size':6693}
 frozen=doc(root,pin);prior=doc(root,previous);doc(root,original)
 require(original==ORIGINAL_REGISTRATION and rows[1]['details'].get('supersedes_WEB_registration')==original
  and row['details'].get('supersedes_WEB_registration')==previous and row['details'].get('shop_office_WEB_execution_registration')==pin
  and frozen.get('causal_predecessor')==previous and prior.get('causal_predecessor')==original
  and all(frozen.get(k)==v for k,v in {'task_id':TASK,'scope':SCOPE,'goal_contract':CONTRACT,'authorization_pin':AUTH,
    'candidate_commit':FA6_COMMIT,'candidate_delivery':old.CURRENT_TYPED,'original_owner':OWNER,'execution_department':ROLE}.items()),
  'exact frozen accepted fa6 registration/authority/source prefix; no revalidation or rewrite of old production')
 return pin


def current_candidate(root):
 """Read the genuine local causal head; local tests never stand for official CI."""
 d=external_source(CURRENT_TYPED)
 require((d.get('schema'),d.get('task_id'),d.get('scope'),d.get('commit'),d.get('parent'),d.get('base'),d.get('tree'),d.get('branch'))==('shop-office-physical-CMS-scope-current-base-causal-candidate/v5',TASK,SCOPE,CURRENT_COMMIT,CURRENT_PARENT,CURRENT_PARENT,CURRENT_TREE,CURRENT_BRANCH),'exact real physical-scope candidate/parent/tree/branch')
 require(d.get('proposed_exact_physical_CMS_execution_scope')==cms.EXECUTION_SCOPE,'physical execution scope equals the adopted two-target carrier')
 cms.scope_carrier(root)
 require(git('show','-s','--format=%H %P %T',CURRENT_COMMIT).decode().strip()==CURRENT_COMMIT+' '+CURRENT_PARENT+' '+CURRENT_TREE,'actual real Git causal object')
 require(set(git('diff','--name-only',CURRENT_PARENT,CURRENT_COMMIT).decode().splitlines())==PHYSICAL_DIFF_PATHS,'only original exact three scope/test paths')
 oldpin={'path':str(TYPED),'sha256':TYPED_SHA,'size':16190};require(d.get('predecessor_reviewed_delivery')==oldpin and d.get('predecessor_actual_production_delivery')==PRECEDING_PRODUCTION,'original source and real production predecessor pins')
 old=external_source(oldpin);production=external_source(PRECEDING_PRODUCTION)
 require(production.get('schema')=='shop-office-current-production-base-readback/v5'
  and production.get('main_sha')==production.get('remote_main_sha')==production.get('public_deployment_version')==CURRENT_PARENT
  and production.get('material_service_source_sha256')==MATERIAL_CURRENT and production.get('material_successor_release_preserved')is True,
  'exact actual current material production baseline required, never old Edge82')
 for key,path in [('existing_Pages_run','.github/workflows/cloudflare-pages-deploy.yml'),('existing_R3_run',R3_WORKFLOW)]:
  run=production.get(key,{})
  require(type(run.get('id'))is int and run['id']>0 and run.get('head_sha')==CURRENT_PARENT
   and run.get('path')==path and run.get('run_attempt')==1 and run.get('status')=='completed'and run.get('conclusion')=='success',
   'actual preceding same-a60 production run; never a future035b run')
 prior=external_source(_fa6_module(root).CURRENT_TYPED)
 require(d.get('predecessor_physical_scope_candidate')==_fa6_module(root).CURRENT_TYPED,
  'actual prior fa6 physical-scope source retained')
 expected_material=[{'path':MATERIAL_PATH,'prior_fa6_sha256':MATERIAL_BEFORE,
  'actual_a60_base_sha256':MATERIAL_CURRENT,'actual_successor_sha256':MATERIAL_CURRENT}]
 require(d.get('legitimate_material_successor_inherited')==expected_material,
  'only the one accurately inherited material service hash may differ')
 full=d.get('full_batch_file_sha256',{});changed=d.get('file_sha256',{})
 require(set(full)==set(old.get('file_sha256',{}))and len(full)==19 and set(changed)==PHYSICAL_DIFF_PATHS,'exact prior19 and three-file causal delta')
 for p,sha in full.items():
  require(not Path(p).is_absolute()and '..'not in Path(p).parts and hashlib.sha256(git('show',CURRENT_COMMIT+':'+p)).hexdigest()==sha,'actual causal Git blob differs: '+p)
  base=hashlib.sha256(git('show',CURRENT_PARENT+':'+p)).hexdigest()
  expected=MATERIAL_CURRENT if p==MATERIAL_PATH else old['file_sha256'][p]
  require(base==expected and(p in PHYSICAL_DIFF_PATHS or sha==base),'current base/other16 changed outside exact inherited material')
  require((p==MATERIAL_PATH and prior['full_batch_file_sha256'][p]==MATERIAL_BEFORE and sha==MATERIAL_CURRENT)
   or(p!=MATERIAL_PATH and sha==prior['full_batch_file_sha256'][p]),'one inherited material delta only; retain all other18 fa6 bytes')
  if p in PHYSICAL_DIFF_PATHS:require(changed[p]==sha,'exact changed-path digest')
 patch=d.get('source_patch');raw=external_source(patch,False)
 require(patch=={'path':str(SITE/'backups/shop-office-six-and-five-implementation-release-20261025-v1/PHYSICAL-CMS-SCOPE-CURRENT-035b08ea.patch'),'sha256':'5bf587e697d4a32dc05f1b3e35577f4d52c325161acd5715f814fc782f537dd5','size':7022},'exact immutable causal patch')
 require(hashlib.sha256(git('diff','--binary',CURRENT_PARENT,CURRENT_COMMIT)).hexdigest()==hashlib.sha256(raw).hexdigest(),'patch must equal actual Git diff')
 for p in d.get('check_logs',[]):external_source(p,False)
 actual=[p for p in d.get('check_logs',[])if p.get('sha256')=='7fee9cbd54df6dd6717a6ff765eb3c2a22624b73e34eb053129f69149fb8629e']
 require(len(actual)==1 and b'132 passed'in external_source(actual[0],False)
  and d.get('tests',{}).get('new_current_base',{}).get('tests')==132,'actual current-base132 log; old16/171 are historical only')
 rehearsal=external_source(d.get('source_recovery_rehearsal'))
 require(rehearsal.get('base')==CURRENT_PARENT and rehearsal.get('commit')==CURRENT_COMMIT and rehearsal.get('patch')==patch and rehearsal.get('candidate_file_sha256')==changed and rehearsal.get('actual_forward_reverse_byte_exact')is True,'actual three-file inverse rehearsal')
 for p,sha in rehearsal.get('before_file_sha256',{}).items():require(p in changed and hashlib.sha256(git('show',CURRENT_PARENT+':'+p)).hexdigest()==sha,'actual inverse before bytes')
 return {**d,'causal_diff_file_sha256':changed,'file_sha256':full,'patch_sha256':patch['sha256']}

def registration_document(root):
 _,b,_=authority(root);c=current_candidate(root);previous=_fa6_registration(root)
 return {'schema':'shop-office-original-WEB-execution-registration/v1','source_generation':'actual-current-material-base035b-v5','task_id':TASK,'scope':SCOPE,'action_class':'site_ci_prepare','original_owner':OWNER,'execution_department':ROLE,'executor_binding':{k:b.get(k)for k in ['thread_id','title','project_id','cwd']},'goal_contract':CONTRACT,'authorization_pin':AUTH,'candidate_delivery':CURRENT_TYPED,'candidate_commit':CURRENT_COMMIT,'candidate_parent':CURRENT_PARENT,'complete_diff_base':CURRENT_PARENT,'candidate_tree':CURRENT_TREE,'branch':CURRENT_BRANCH,'causal_predecessor':previous,'predecessor_actual_production':PRECEDING_PRODUCTION,'physical_execution_carrier':cms.scope_carrier(root),'changed_paths':sorted(PHYSICAL_DIFF_PATHS),'full_batch_file_sha256':c['file_sha256'],'operations':{k:{'action_class':v[0],'scope':v[1]}for k,v in OPS.items()},'future_main_or_run_authorized':False,'external_write_or_permission_issued':False}

def registration(root):
 _fa6_registration(root)
 rows=[e for e in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS)if e.get('task_id')==TASK and e.get('details',{}).get('shop_office_WEB_execution_registration')]
 require(len(rows)==4,'current exact causal physical source must be normally registered')
 previous=rows[2]['details']['shop_office_WEB_execution_registration'];last=rows[3]
 require(last['details'].get('supersedes_WEB_registration')==previous and doc(root,last['details']['shop_office_WEB_execution_registration'])==registration_document(root),'append-only actual current source relation, not old head permission')
 return last['details']['shop_office_WEB_execution_registration']

def record_registration(root,task,path):
 import department_autonomy as a
 require(task==TASK,'same original stage');pin=w.file_digest(root,path);require(doc(root,pin)==registration_document(root),'exact real035b source/current material base and original authorization')
 with w.workflow_lock(root):
  snap,_,_=authority(root);a.original_assignment_ready(root,snap,'system-development')
  rows=[e for e in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS)if e.get('task_id')==TASK and e.get('details',{}).get('shop_office_WEB_execution_registration')]
  if len(rows)==4:
   require(registration(root)==pin,'current source already registered with another pin');return {'result':'duplicate_ignored','registration':pin,'permission_issued':False}
  previous=_fa6_registration(root);require(len(rows)==3,'one actual causal predecessor before new source')
  event=w.append_workflow_event(root,TASK,snap['current_state'],{'shop_office_WEB_execution_registration':pin,'supersedes_WEB_registration':previous,'original_versions_and_consumed_effects_preserved':True,'permission_issued':False})
 return {'result':'recorded','event_id':event['event_id'],'registration':pin,'permission_issued':False}

def _source_candidate(root,commit):
 if commit==COMMIT:
  _legacy_registration(root);return candidate()
 if commit==FA6_COMMIT:
  _fa6_registration(root);return _fa6_module(root).current_candidate(root)
 require(commit==CURRENT_COMMIT,'unknown source is not a valid old or current causal version')
 registration(root);return current_candidate(root)

def require_current_request(root,req):
 require(req.get('state',{}).get('candidate_commit')==CURRENT_COMMIT,'historical source is read-only; new action requires the current exact causal head')
 registration(root)

def current_production_recovery(root):
 import copy
 c=current_candidate(root);old=external_source(LEGACY_PRODUCTION_RECOVERY)
 require(old.get('task_id')==TASK and old.get('candidate_commit')==ORIGINAL_COMMIT and old.get('source_recovery',{}).get('R3_source_restore'),'original actual production recovery source')
 mapped=copy.deepcopy(old);mapped.update(schema='shop-office-physical-scope-production-recovery/v2',candidate_commit=CURRENT_COMMIT,business_scope=SCOPE,predecessor_runbook=LEGACY_PRODUCTION_RECOVERY,physical_scope_carrier=cms.scope_carrier(root))
 mapped['source_recovery'].update(rehearsal_receipt=c['source_recovery_rehearsal']['path'],source_patch=c['source_patch'],actual_forward_reverse_byte_exact=True,prior_Edge82_is_a_usable_CMS_permit_fallback=False)
 actual={t['record_id']:t for t in cms.targets(root).values()}
 require({v['row_id']:v['fields']for v in mapped['CMS_recovery']['exact_targets']}=={k:v['changed_fields']for k,v in actual.items()},'only original two rows/six fields in production recovery')
 for row in mapped['CMS_recovery']['exact_targets']:
  t=actual[row['row_id']];inverse=row['normal_inverse'];require(inverse.get('taskId')==TASK and inverse.get('scope')==SCOPE and inverse.get('actionId')=='rollback-'+t['candidate_version']and inverse.get('candidateVersion')==t['candidate_version']+'-rollback-v1','exact original inverse antecedent')
  inverse.update(business_scope=SCOPE,scope=cms.physical_scope(root,t))
 mapped['source_recovery'].update(minimum_known_pre_candidate_main=CURRENT_PARENT,
  inherited_material_service={'path':MATERIAL_PATH,'sha256':MATERIAL_CURRENT,'must_not_revert_to_fa6_or_Edge82':True},
  predecessor_production_source=PRECEDING_PRODUCTION,
  R3_source_restore='Before any new R3 execution capture the then-current complete verified source/build dependency closure and actual Edge facts. Restore only that authorized closure retaining the a60 material successor or later independently authorized changes; never use old Edge82 or its incomplete source. Unknown effects require original-key readback first.')
 mapped['current_remote_effects']={'snapshot_source':PRECEDING_PRODUCTION,'observed_predecessor_main':CURRENT_PARENT,
  'actual_Edge_function_version':'NOT_READ_NOT_INFERRED','new_candidate_remote_effects':'NOT_EXECUTED_AT_FROZEN_READY',
  'fresh_actual_main_and_complete_Edge_source_build_backup_required_before_effect':True}
 mapped['before_source_rollback_after_CMS_Save']=c['recovery_boundary']
 mapped['production_or_CMS_rollback_executed']=False
 return mapped


if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('command',choices=['describe','request-base','build-preflight']);p.add_argument('--root',default=str(ROOT))
 for name in ['operation','state','output','base','facts-native','facts-command','selfcheck-native','selfcheck-command']:p.add_argument('--'+name)
 args=p.parse_args();root=Path(args.root).resolve()
 if args.command=='describe':result=describe(root)
 elif args.command=='request-base':
  require(args.state and args.operation and args.output,'actual operation/state and project output path required');state=w.read_json(w.safe_path(root,args.state));base=request_base(root,args.operation,state);out=w.safe_path(root,args.output);require(not out.exists(),'preserve original input');w.atomic_write_json(out,base);result={'base':w.file_digest(root,args.output),'intent_sha256':w.sha256_value(base),'candidate_delivery_sha256':CURRENT_TYPED['sha256'],'external_permission_issued':False}
 else:
  require(all([args.base,args.facts_native,args.facts_command,args.selfcheck_native,args.selfcheck_command,args.output]),'real original WEB native facts/selfcheck sources required');result=build_preflight(root,args.base,args.facts_native,args.facts_command,args.selfcheck_native,args.selfcheck_command,args.output)
 print(json.dumps(result,ensure_ascii=False,indent=2))
