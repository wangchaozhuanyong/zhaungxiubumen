"""Exact owner-authorized shop/office six-field wiring; no network or permit issue.

Registration and execution observations append to the existing workflow journal.
The original protected CMS issuer still verifies GitHub, dry-run, policy, one-use
permit, current row CAS and actual outcome. This module never saves CMS content.
"""
from pathlib import Path
import argparse, datetime as dt, hashlib, json
import workflow_control as w

TASK='fc-20261025-shop-office-existing-six-and-five-implementation-release-v1'
SCOPE='project:flashcast:shop-office:existing-six-fields-and-five-blocks:20261025:v1'
SHAPE='owner_authorized_shop_office_six_field_v4'
PROJECT='<LOCAL_PROJECT_ID>'
REF='rbsnyexjifounogswrjp'
BASE='logs/handoffs/2026-10-25-shop-office-autonomous-followthrough-v1/owner-authorized-complete-implementation-release-v1/'
AUTH={'path':BASE+'actual-owner-full-implementation-approval.json','sha256':'ad391f2e16894b1d5ebc533cc4ca28030c9e0a7e3a002b250c2228b26a333940','size':1936}
CONTRACT={'path':BASE+'COMPLETE-OWNER-AUTHORIZED-SIX-AND-FIVE-IMPLEMENTATION-RELEASE-GOAL-v1.json','sha256':'2532584b3bae6120ff350aa3af8696221dcf789b6b11f731f9cbe86ba99c8622','size':9815}
V4={'path':'drafts/seo/fc-20261010-assistant1-remaining-business-continuation-v2/seo-content-research/shop-office-authenticated-source-candidate-20261022-v4/six-field-current-local-candidate-v4.json','sha256':'9b5feee055a470094de1b6fc50549d934aadae23538fca646593274f3c6ba610','size':68381}
ROWS={'shop':('32f5374f-9919-41ea-80c7-00b5ac917532','shop-renovation',['content_en','faqs_en','faqs_zh']),
      'office':('a87541ac-1cba-4f1a-972d-428dccdbcc0f','office-renovation',['content_zh','faqs_en','faqs_zh'])}
ROOT=Path(__file__).resolve().parents[1]

def require(ok,message):
 if not ok:raise w.WorkflowError('shop/office exact execution: '+message)

def doc(root,pin):
 require(isinstance(pin,dict)and w.file_digest(root,pin.get('path',''))==pin,'unchanged project-local source pin required')
 return w.read_json(w.safe_path(root,pin['path']))

def sha(value):
 return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()

def authority(root):
 import department_autonomy as a,goal_delivery_runtime as g
 a.authority(root);snapshot=g.restore_goal(root,w.read_json(w.snapshot_path(root,TASK)))
 require(snapshot.get('goal_contract')==CONTRACT and snapshot.get('current_state')not in w.TERMINAL_STATES,'open exact new implementation stage required')
 goal=snapshot['goal_delivery'];require(goal.get('authorization_pin')==AUTH and goal.get('primary_owner')=='seo-content-research'
  and goal.get('authorized_scope')==[SCOPE]and set(goal['producer_departments'])=={'seo-content-research','publishing','system-development'},'original owner/producers/scope unchanged')
 approved=doc(root,AUTH);doc(root,CONTRACT);doc(root,V4)
 native=g._native_document(root,w.file_digest(root,approved['actual_native_path']))
 messages=[m for t in native.get('turns',[])if t.get('id')==approved['source_turn_id']for m in t.get('items',[])if m.get('id')==approved['message']['id']]
 require(len(messages)==1 and messages[0]==approved['message']and approved.get('approval_text')=='授权这批完整实施发布'
  and native.get('thread',{}).get('id')==approved['source_thread_id']==w.department_registry(root)['operations']['chat_binding']['task_id'],'real original human question/reply, not a caller grant')
 bounds=goal['execution_bounds']['exact_CMS_changes'];require(bounds.get('project_ref')==REF and bounds.get('function')=='content-publish'
  and bounds.get('unchanged_V4_content_candidate')==V4,'exact original CMS project/function/content')
 require({x['id']:(x['slug'],x['fields'])for x in bounds['rows']}=={v[0]:(v[1],v[2])for v in ROWS.values()},'only the original two rows and three fields each')
 return snapshot

def make_candidate(root,label,before_pin):
 require(label in ROWS,'exact shop/office label');row=doc(root,before_pin);identity,slug,fields=ROWS[label]
 require(row.get('id')==identity and row.get('slug')==slug and row.get('status')=='published'
  and type(row.get('version'))is int and row['version']>=1 and w._parse_observed_at(row.get('updated_at'))is not None,'complete actual published row/version, no defaults')
 require(len(row)==41 and len([k for k in row if k.endswith('_ms')])==11,'complete 41-field native row including all 11 current MS fields')
 frozen=doc(root,V4);delta=[x for x in frozen['deltas']if x['record_id']==identity]
 require(len(delta)==3 and {x['field']for x in delta}==set(fields),'exact original six-field content source')
 desired={x['field']:x['after']for x in delta}
 require(all(row[x['field']]==x['before']for x in delta),'target is already AFTER or has another change; read actual effect/rebase, never overwrite')
 before_hash=sha(row);version='shop-office-'+label+'-six-v4-'+before_hash[:12]+'-20261025-v1';action='publish-'+version
 projection=list(row);retained=[k for k in projection if k not in set(fields)|{'updated_at','version'}]
 request={'mode':'dry-run','contentType':'service','nextStatus':'published','expectedUpdatedAt':row['updated_at'],
  'record':{'id':identity,'slug':slug,**desired},'managedCandidate':{'taskId':TASK,'actionId':action,'candidateVersion':version,'scope':SCOPE,'operation':'publish'}}
 return {'schema':'owner-authorized-shop-office-sparse-candidate/v1','task_id':TASK,'action_id':action,'action_class':'cms_content_candidate','execution_action_class':'cms_write','scope':SCOPE,'candidate_version':version,'label':label,'record_id':identity,'slug':slug,'table':'services','project_ref':REF,'changed_fields':fields,'execution_owner':'publishing','execution_thread_id':w.department_registry(root)['publishing']['chat_binding']['task_id'],'goal_contract':CONTRACT,'authorization_pin':AUTH,'original_V4_content':V4,'before':before_pin,'expected_updated_at':row['updated_at'],'observed_version':row['version'],'baseline_projection_fields':projection,'retained_projection_fields':retained,'baseline_fields_sha256':before_hash,'desired_fields':desired,'before_fields':{k:row[k]for k in fields},'desired_fields_sha256':sha(desired),'rollback_fields_sha256':sha({k:row[k]for k in fields}),'retained_fields_sha256':sha({k:row[k]for k in retained}),'request':request,'production_write_executed':False,'old_permits_inherited':False,'fresh_remote_CAS_and_protected_preview_required':True}

def validate_candidate(root,candidate,target=None):
 authority(root);expected=make_candidate(root,candidate.get('label'),candidate.get('before'))
 require(candidate==expected,'exact sparse candidate/version/fields/baseline/authority differ')
 if target is not None:require(target==as_target(root,candidate,target['candidate']),'current issuer tuple differs')
 return candidate

def as_target(root,candidate,pin):
 return {k:candidate[k]for k in ['task_id','action_id','candidate_version','scope','record_id','slug','table','changed_fields','execution_owner','execution_thread_id','expected_updated_at','observed_version','baseline_projection_fields','retained_projection_fields','baseline_fields_sha256','desired_fields_sha256','rollback_fields_sha256','retained_fields_sha256']}|{'candidate_shape':SHAPE,'content_type':'service','candidate':tuple(pin),'rollback':(candidate['before']['path'],candidate['before']['sha256']),'payload_sha256':candidate['desired_fields_sha256'],'evidence_root':Path(root),'rollback_allowed':False,'qa_outbox':None,'old_permits_inherited':False}

def registration(root,pin):
 authority(root);obj=doc(root,pin);require(obj.get('schema')=='owner-authorized-shop-office-six-targets/v1'and obj.get('task_id')==TASK and obj.get('goal_contract')==CONTRACT and obj.get('authorization_pin')==AUTH,'exact bounded registration source')
 require(len(obj.get('candidates',[]))==2,'two complete original target candidates')
 result={}
 for candidate_pin in obj['candidates']:
  candidate=doc(root,candidate_pin);validate_candidate(root,candidate);name=candidate['candidate_version'];require(name not in result,'unique target identity')
  result[name]=as_target(root,candidate,(candidate_pin['path'],candidate_pin['sha256']))
 require({t['record_id']for t in result.values()}=={v[0]for v in ROWS.values()},'both original rows, no duplicate row')
 return result

def registration_rows(root):
 return [e for e in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS)if e.get('task_id')==TASK and e.get('details',{}).get('shop_office_six_field_registration')]

def targets(root):
 events=registration_rows(root)
 if not events:return {}
 require(not w.validate_workflow_events(root,TASK),'intact original registration event chain')
 return registration(root,events[-1]['details']['shop_office_six_field_registration'])

def register(root,path):
 pin=w.file_digest(root,path);new=registration(root,pin)
 import department_autonomy as a
 with w.workflow_lock(root):
  snapshot=authority(root);a.original_assignment_ready(root,snapshot,'system-development');rows=registration_rows(root)
  if rows and rows[-1]['details']['shop_office_six_field_registration']==pin:return {'result':'duplicate_ignored','targets':sorted(new),'permit_issued':False}
  if rows:
   previous=rows[-1]['details']['shop_office_six_field_registration'];old=registration(root,previous)
   require(doc(root,pin).get('supersedes')==previous and set(new)!=set(old),'exact immutable baseline successor relation required')
   require(not any(p.get('task_id')==TASK and p.get('action_id')in {t['action_id']for t in old.values()}and p.get('status')=='allow'for p in w.read_jsonl(Path(root)/w.POLICY_DECISIONS)),'old issued/unknown action must be read back before any baseline successor')
  event=w.append_workflow_event(root,TASK,snapshot['current_state'],{'shop_office_six_field_registration':pin,'local_issuer_owner':'system-development','actual_CMS_write':False,'permit_issued':False})
 return {'result':'recorded','event_id':event['event_id'],'targets':sorted(new),'permit_issued':False,'remote_target_deployed':False}

def target_for(root,action):
 found=[x for x in targets(root).values()if x['action_id']==action];require(len(found)==1,'one current registered exact action, not historical targets')
 return found[0]

def validate_request(root,req,target):
 import department_autonomy as a
 snapshot=authority(root);a.original_assignment_ready(root,snapshot,'publishing');candidate=doc(root,w.file_digest(root,target['candidate'][0]));validate_candidate(root,candidate,target)
 expected={'task_id':TASK,'department':'publishing','action_id':target['action_id'],'action_class':'cms_write','scope':SCOPE,'source_project_id':PROJECT,'account_id':REF,'object_ids':[target['record_id']],'operation':'publish','desired':candidate['desired_fields']}
 require(all(req.get(k)==v for k,v in expected.items())and req.get('authorization_changes',[])==[],'exact authorized executor/project/row/fields/effect; no expansion')
 require(req.get('before')==candidate['before']and req.get('expected_version')==candidate['before']['sha256'],'actual full baseline pin and projection are not a fabricated server CAS')
 intent=w.sha256_value({k:v for k,v in req.items()if k not in {'facts','self_check','backup','rollback'}})
 for name in ['facts','self_check','backup','rollback']:
  obj=doc(root,req.get(name));require(all(obj.get(k)==expected[k]for k in ['task_id','department','action_id','action_class','scope'])and obj.get('intent_sha256')==intent,'exact request-bound '+name)
  if name=='self_check':
   require(obj.get('status')=='PASS'and obj.get('candidate')==w.file_digest(root,target['candidate'][0])and obj.get('payload_sha256')==target['payload_sha256'],'actual publisher candidate selfcheck, not assistant approval')
   _,_,output=a.native_execution(root,obj.get('actual_native'),obj.get('command_id'),'publishing')
   if isinstance(output,bytes):output=output.decode('utf-8')
   require(isinstance(output,str)and target['candidate'][1]in output and target['payload_sha256']in output,'real complete successful selfcheck output names both exact hashes')
  elif name=='backup':require(obj.get('complete_before')==candidate['before'],'full actual 41-field backup required')
  elif name=='rollback':require(obj.get('before_fields')==candidate['before_fields']and obj.get('post_write_CAS_required')is True and obj.get('unknown_effect_replay_allowed')is False,'executable reverse patch only with actual post-write CAS; unknown effects never replay')
  elif name=='facts':
   require(obj.get('raw_updated_at')==target['expected_updated_at']and obj.get('version')==target['observed_version']and obj.get('baseline_sha256')==target['baseline_fields_sha256'],'exact native timestamp/version and full projection')
   context=doc(root,obj.get('actual_read_context'));require(context.get('observed_at')==req.get('observed_at')and context.get('credentials_or_headers_exported')is False,'real original authenticated row-read context/time, never synthesized freshness')
 return candidate

def record_preflight(root,path):
 pin=w.file_digest(root,path);item=doc(root,pin);target=target_for(root,item.get('action_id'));req=doc(root,item.get('request'));validate_request(root,req,target)
 require(all(item.get(k)==req.get(k)for k in ['task_id','department','action_id','action_class','scope'])and item.get('risk_level')=='R2'and item.get('payload_sha256')==target['payload_sha256']and all(item.get(k)==req.get(k)for k in ['facts','self_check','backup','rollback']),'exact ordinary CMS preflight source')
 with w.workflow_lock(root):
  snapshot=authority(root);rows=[e for e in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS)if e.get('task_id')==TASK and e.get('details',{}).get('shop_office_six_field_preflight',{}).get('action_id')==target['action_id']]
  if rows:
   previous=rows[-1]['details']['shop_office_six_field_preflight']
   if previous['input']==pin:return {'result':'duplicate_ignored','input':pin,'permit_issued':False}
   original=doc(root,doc(root,previous['input'])['request'])
   require(all(req.get(k)==original.get(k)for k in ('task_id','department','action_id','action_class','scope','source_project_id','account_id','object_ids','operation','desired','before','expected_version')),'fresh observation must retain the exact effect and baseline')
   require(not any(p.get('task_id')==TASK and p.get('action_id')==target['action_id']and p.get('status')=='allow'for p in w.read_jsonl(Path(root)/w.POLICY_DECISIONS)),'issued or unknown effect cannot refresh into another execution request')
  event=w.append_workflow_event(root,TASK,snapshot['current_state'],{'shop_office_six_field_preflight':{'action_id':target['action_id'],'input':pin,'request':item['request'],'original_authority':AUTH}})
 return {'result':'recorded','event_id':event['event_id'],'input':pin,'permit_issued':False}

def preflight(root,snapshot,action,action_class,scope,department):
 require(snapshot.get('task_id')==TASK and (action_class,scope,department)==('cms_write',SCOPE,'publishing'),'exact new stage CMS action, no other namespace')
 target=target_for(root,action);rows=[e for e in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS)if e.get('task_id')==TASK and e.get('details',{}).get('shop_office_six_field_preflight',{}).get('action_id')==action]
 require(rows and not w.validate_workflow_events(root,TASK),'one real current publisher selfcheck preflight in intact original chain; registration is not permission')
 pin=rows[-1]['details']['shop_office_six_field_preflight']['input'];item=doc(root,pin);validate_request(root,doc(root,item['request']),target)
 return item,pin,rows[-1]

def action_authority(root,snapshot,requested):
 item,_,_=preflight(root,snapshot,requested.get('action_id'),requested.get('action_class'),requested.get('scope'),requested.get('department'));target=target_for(root,requested.get('action_id'));req=doc(root,item['request'])
 require(requested.get('payload_sha256')==target['payload_sha256']and requested.get('source_project_id')==PROJECT,'exact desired-fields hash and original project')
 return {'action':{k:req[k]for k in ['task_id','action_id','action_class','scope','department']}|{'request':item['request']},'request':req,'pin':item['request'],'authorization':AUTH,'department':'publishing'}

def acceptance(root,target,operation):
 snapshot=authority(root);require(operation=='publish'and target==target_for(root,target['action_id']),'only exact forward target; no borrowed rollback permit')
 item,pin,event=preflight(root,snapshot,target['action_id'],'cms_write',SCOPE,'publishing')
 return {'acceptance_model':'goal_authorized_cms_selfcheck_v1','verdict':'selfcheck_ready','task_id':TASK,'action_id':target['action_id'],'scope':SCOPE,'candidate_version':target['candidate_version'],'candidate':w.file_digest(root,target['candidate'][0]),'risk_level':'R2','authorization_pin':AUTH,'execution_preflight':pin,'execution_preflight_event_id':event['event_id'],'receipt_id':event['event_id'],'receipt_hash':event['event_hash'],'created_at':event['created_at'],'review_plan':None,'review_outbox':None,'goal_completion_claimed':False,'production_write_allowed':False,'final_assistant_acceptance_required':False}

def consumed_policy(root,row,target,operation,payload,decision,now):
 snapshot=authority(root);require(operation=='publish'and payload==target['payload_sha256'],'exact forward payload')
 context=action_authority(root,snapshot,row)
 require(row.get('status')=='allow'and row.get('approval_basis')=='department_autonomous_delivery_v1'and row.get('approval_status')=='consumed_for_original_exact_autonomous_action'
  and row.get('original_authority')==AUTH and row.get('exact_request')==context['pin']and row.get('decision_id'),'actual original normal consumed policy, not caller allow')
 matches=[p for p in w.read_jsonl(Path(root)/w.POLICY_DECISIONS)if p.get('decision_id')==row['decision_id']];require(matches==[row],'one unchanged normal policy row')
 at=w._parse_observed_at(row.get('checked_at'));decided=w._parse_observed_at(decision.get('decided_at'));require(at and decided and decided<=at<=now and now-at<=dt.timedelta(minutes=30),'actual chronological current execution policy')
 return row

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=['register','readiness','preflight-record']);p.add_argument('--root',default=str(ROOT));p.add_argument('--input');args=p.parse_args();root=Path(args.root).resolve()
 if args.command=='register':result=register(root,args.input)
 elif args.command=='preflight-record':result=record_preflight(root,args.input)
 else:result={'task_id':TASK,'targets':targets(root),'CMS_write_executed':False,'permit_issued':False,'protected_execution_still_required':True}
 print(json.dumps(result,ensure_ascii=False,indent=2,default=str))
if __name__=='__main__':main()
