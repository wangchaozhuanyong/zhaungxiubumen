"""Owner-approved independent delivery. Scope checks grant no external operation."""
from pathlib import Path
import json, datetime as dt
import workflow_control as w
MODE='department_autonomous_delivery_v1'
OWNER = {'path': 'logs/local-setup/owner-autonomous-authority.json', 'sha256': '0000000000000000000000000000000000000000000000000000000000000000', 'size': 0}
PROJECT='<LOCAL_PROJECT_ID>'
OWNER_TURN = 'example-local-owner-turn'
OWNER_MESSAGE = 'example-local-owner-message'
OWNER_TEXT = 'Synthetic example only; local native owner authorization required.\n'
SOURCE_PROOF = {'path': 'logs/local-setup/original-completed-proof.json', 'sha256': '0000000000000000000000000000000000000000000000000000000000000000', 'size': 0}
JOURNAL = 'backups/local-setup/original-source-adoption/journal.json'
ASSISTANTS={'operations-assistant','operations-assistant-2','operations-assistant-3','qa','qa-technical','qa-evidence','quality-assurance'}

def require(test,reason):
 if not test:raise w.WorkflowError('autonomous delivery: '+reason)

def document(root,pin):
 from chatgpt_fe689_draft_admission import document as read
 return read(root,pin)

PUBLIC_TEMPLATE_ONLY = True

def authority(root):
 require(not PUBLIC_TEMPLATE_ONLY,'public template has no local native owner authorization')
 raw=document(root,OWNER);registry=w.department_registry(root);hq=registry['operations']['chat_binding']
 require(raw.get('thread',{}).get('id')==hq.get('task_id') and hq.get('project_id')==PROJECT
  and Path(raw['thread'].get('cwd','')).resolve()==Path(root).resolve()==Path(hq['cwd']).resolve(), 'actual fixed same-project owner source required')
 turns=[t for t in raw.get('turns',[])if t.get('id')==OWNER_TURN]
 require(len(turns)==1 and type(turns[0].get('startedAt'))in {int,float}
  and turns[0]['startedAt']<=dt.datetime.now(dt.timezone.utc).timestamp(), 'real ordered original owner turn required')
 rows=[m for m in turns[0].get('items',[])if m.get('id')==OWNER_MESSAGE and m.get('type')=='userMessage']
 require(len(rows)==1 and rows[0].get('content')==[{'type':'text','text':OWNER_TEXT}], 'unchanged actual owner words required; caller labels are not authority')
 return {'mode':MODE,'owner_source':OWNER,'source_message_id':OWNER_MESSAGE,
  'sensitive_actions_require_exact_owner_decision':True,'external_permission_issued':False}

def participant(root,snapshot,sender,allow_completed_report=False):
 authority(root);g=snapshot.get('goal_delivery',{});contract=snapshot.get('goal_contract')
 require(contract and document(root,contract), 'unchanged frozen original contract required')
 require(allow_completed_report or snapshot.get('current_state')not in w.TERMINAL_STATES, 'closed goal cannot create a new action')
 require(sender not in ASSISTANTS and sender in {'operations',g.get('primary_owner'),*g.get('producer_departments',[])}, 'actual original professional participant required')
 return g

def message_route(root,snapshot,request):
 if not isinstance(request,dict)or request.get('action_class')!='thread_message':return None
 payload=request.get('payload')
 if not isinstance(payload,dict):return None
 require(w.file_digest(root,payload.get('path',''))==payload,'exact payload bytes required')
 text=(Path(root)/payload['path']).read_text()
 try:obj=json.loads(text)
 except (ValueError,UnicodeError):obj=None
 structured=isinstance(obj,dict)and obj.get('schema')=='department-autonomous-task-message/v1'
 if structured:
  obj=document(root,payload)
 else:
  # A report is transport, never a permit or a new assignment. Accept the
  # existing exact task/scope format; departments need not repackage it.
  if request.get('target_department')not in {'operations',snapshot.get('goal_delivery',{}).get('primary_owner'),*snapshot.get('goal_delivery',{}).get('producer_departments',[]),*[c.get('target_department')for c in snapshot.get('goal_delivery',{}).get('collaboration_scopes',[])]}:return None
  import re
  if not all(re.search(r'(?m)^'+key+r'='+re.escape(str(request.get(key,'')))+r'\s*$',text)for key in ('task_id','scope')):return None
  obj={'schema':'department-autonomous-task-message/v1','task_id':request['task_id'],'scope':request['scope'],
   'sender_department':request['sender_department'],'target_department':request['target_department'],
   'goal_contract':snapshot.get('goal_contract'),'owner_authorization':OWNER,'report':payload,
   'next_action':'read original professional report; no execution permission issued'}
 auth=authority(root);sender=request['sender_department'];g=participant(root,snapshot,sender,allow_completed_report=request.get('target_department')=='operations');task=snapshot['task_id']
 target=request.get('target_department');registry=w.department_registry(root)
 require(target not in ASSISTANTS and ((sender in g.get('producer_departments',[]) and target=='operations')
  or(sender=='operations' and target in g.get('producer_departments',[]))
  or(sender==g.get('primary_owner') and any(c.get('target_department')==target and c.get('scope')==request.get('scope')for c in g.get('collaboration_scopes',[])))
  or(sender in g.get('producer_departments',[]) and target==g.get('primary_owner') and sender!=target)), 'only original department report/HQ coordination/collaboration return')
 require(set(obj)=={'schema','task_id','scope','sender_department','target_department','goal_contract','owner_authorization','report','next_action'}
  and all(obj.get(k)==request.get(k)for k in ('task_id','scope','sender_department','target_department'))
  and request['task_id']==task and request['scope']in g['authorized_scope']
  and obj['goal_contract']==snapshot['goal_contract'] and obj['owner_authorization']==OWNER
  and isinstance(obj['next_action'],str)and obj['next_action'].strip()
  and request.get('payload_sha256')==payload['sha256'], 'exact original task/scope/contract/payload required')
 if structured:
  report=document(root,obj['report'])
  require(report.get('task_id')==task and report.get('department')==sender, 'real original sender report required')
 source=registry[sender]['chat_binding'];dest=registry[target]['chat_binding']
 require(source.get('project_id')==dest.get('project_id')==request.get('source_project_id')==request.get('target_project_id')==PROJECT
  and Path(source.get('cwd','')).resolve()==Path(root).resolve()==Path(dest.get('cwd','')).resolve()
  and all(request.get(k)==dest.get(v)for k,v in {'target_thread_id':'task_id','target_thread_title':'title','target_cwd':'cwd','target_sidebar_section_id':'sidebar_section_id'}.items()), 'exact fixed role/project/directory/target required')
 require(registry[sender].get('new_dispatch_enabled')is True and registry[target].get('new_dispatch_enabled')is True
  and w._chat_binding_healthy(source,verification_ttl_hours=26) and w._chat_binding_healthy(dest,verification_ttl_hours=26), 'current exact sender/target health required')
 return {**auth,'source':payload,'report':obj['report'],'scope':request['scope'],'sender_department':sender,'target_department':target}

def message_policy(root,request):
 route=message_route(root,w.read_json(w.snapshot_path(root,request['task_id'])),request)
 require(route is not None,'authenticated task message required')
 from goal_delivery_runtime import _collaboration_native
 page=_collaboration_native(root,request.get('actual_target_state'));binding=w.department_registry(root)[request['target_department']]['chat_binding']
 require(all(page.get('thread',{}).get(k)==binding[v]for k,v in {'id':'task_id','title':'title','cwd':'cwd'}.items()), 'actual native target identity required')
 rows=w.read_jsonl(Path(root)/w.POLICY_DECISIONS)
 same=lambda x: all(x.get(k)==request.get(k)for k in ('task_id','action_id','scope','payload_sha256','target_thread_id'))
 existing=[x for x in rows if same(x)and x.get('approval_basis')==MODE]
 require(len(existing)<=1, 'ambiguous original transport policy')
 if existing:return existing[0]
 fields=('task_id','action_id','action_class','scope','source_project_id','target_project_id','target_department','target_thread_id','target_thread_title','target_cwd','target_sidebar_section_id','payload_sha256')
 value={k:request[k]for k in fields};value.update(department=request['sender_department'],status='allow',approval_basis=MODE,
  decision_id='pol-'+w.sha256_value([value,w.utc_timestamp()])[:20],checked_at=w.utc_timestamp(),approval_id='',consume_approval=False,
  reason=['actual_owner_delegation_original_task_report_only'],routing_status='routing_allowed',required_receipts=['normal_fixed_native_transport_and_effect_readback'],external_permission_issued=False)
 with w.workflow_lock(root):w.append_jsonl_locked(Path(root)/w.POLICY_DECISIONS,value)
 return value

def adopted_save_source(root):
 """Preserve the old completed proof and its exact CAS successor separately."""
 authority(root);source=document(root,SOURCE_PROOF);accepted=source['accepted'];proof=source['proof']
 require(accepted.get('state')==proof.get('state')=='PROVEN'and accepted.get('identity')==proof.get('identity'), 'actual historical completed Save source required')
 for pin in source['guards']:
  if not pin['path'].startswith('tools/'):require(w.file_digest(root,pin['path'])==pin,'original source history changed')
 actual=document(root,proof['evidence'][0]);prior=document(root,actual['journal'])
 w._completion_native_stage(root,actual,actual['journal'],'operations-assistant')
 require(prior.get('state')=='adopted'and prior['candidate_manifest']==accepted['candidate'], 'original completed adoption journal required')
 if not (Path(root)/JOURNAL).exists():
  from chatgpt_fe689_draft_admission import _unsaved_adopted_stage
  return _unsaved_adopted_stage(root)
 journal=w.read_json(Path(root)/JOURNAL);manifest=document(root,journal.get('candidate_manifest'))
 require(journal.get('schema')=='owner-autonomous-source-adoption/v1'and journal.get('task_id')=='fc-20261024-original-flow-recovery-execution-stage-v1'
  and journal.get('actor')=='system-development'and journal.get('owner_authorization')==OWNER and journal.get('state')=='adopted'
  and manifest.get('candidate_fingerprint')==w.sha256_value({k:v for k,v in manifest.items()if k!='candidate_fingerprint'})
  and manifest.get('owner_authorization')==OWNER and manifest.get('original_completed_source')==SOURCE_PROOF,
  'actual owner-authorized SYS CAS successor required')
 ops=[x for x in journal.get('source_operations',[])if x.get('path')=='tools/chatgpt_fe689_draft_admission.py']
 old=[x for x in prior['source_operations']if x.get('path')=='tools/chatgpt_fe689_draft_admission.py']
 changes=[x for x in manifest['changes']if x['path']=='tools/chatgpt_fe689_draft_admission.py']
 require(len(ops)==len(old)==len(changes)==1,'one exact original module successor')
 op=ops[0];change=changes[0];current=w.file_digest(root,op['path'])
 require(op['before_sha256']==old[0]['after_sha256']==change['expected_source']['sha256']
  and document_bytes(root,op['backup'])and op['backup']['sha256']==op['before_sha256']
  and current['sha256']==op['after_sha256']==change['candidate']['sha256']
  and (Path(root)/op['path']).stat().st_mode&0o777==op['mode']==change['mode'], 'actual continuous before/backup/after/mode CAS required')
 return {'accepted':accepted,'proof':proof,'guards':[SOURCE_PROOF,OWNER,*[p for p in source['guards']if not p['path'].startswith('tools/')],w.file_digest(root,JOURNAL),current]}

def document_bytes(root,pin):
 require(w.file_digest(root,pin.get('path',''))==pin,'exact backup bytes required');return True

def known_original_save(root):
 native=document(root,{'path': 'logs/handoffs/2026-10-24-department-autonomous-delivery-migration-v1/P0-existing-four-legacy-save-gate-v1/system-development-v1/ACTUAL-FIRST-PARTY-Paid2-NATIVE.json', 'sha256': '54f8ceb783463e222d9b003f3f28d36fa513819cf68a057fd290537f9d29b6c6', 'size': 23065});after={'path': 'logs/handoffs/2026-10-19-chatgpt-paid2-task-transfer/offer-account-preparation-20261021-v1/resume-20261021-v1/authorized-dispatch-v1/execution-continuation-v83/native-ui-launch-20261024-v1/save-as-draft-settled-result.txt', 'sha256': '8adfacee2028fc5fc2da97e419c4726740e95a7560279502c7d2eaac23a578f1', 'size': 6119}
 require(w.file_digest(root,after['path'])==after,'actual native Save readback bytes changed')
 require(native.get('thread',{}).get('id')==w.department_registry(root)['paid-growth-data-2']['chat_binding']['task_id'], 'original native Save executor required')
 rows=[(t,m)for t in native.get('turns',[])for m in t.get('items',[])if m.get('id')=='call_0057467883e34750ac7e3f74325839ca']
 require(len(rows)==1,'one actual original Save effect')
 turn,call=rows[0];completed=turn.get('completedAt')
 require(type(completed)in {int,float},'real completed original effect turn')
 if completed>dt.datetime.now(dt.timezone.utc).timestamp():return None
 require(turn.get('status')=='completed'and not turn.get('error')and call.get('status')=='completed'
  and call.get('server')=='cua_repl'and call.get('tool')=='js'and not call.get('error')
  and ".getByRole('button',{name:'Save as draft',exact:true}).click()"in call.get('arguments',{}).get('code',''), 'actual successful first-party Save invocation')
 text=(Path(root)/after['path']).read_text()
 require('adacct_example_3620baed04d9c3e5'in text and 'EXAMPLE_EXISTING_CAMPAIGN'in text
  and 'button Draft'in text and 'Oct 24, 2026'in text and 'Oct 31, 2026'in text,'actual original account/campaign/draft/date readback required')
 return {'state':'OBSERVED_NATIVE_SAVE_ALREADY_EXECUTED','actual_native':{'path': 'logs/handoffs/2026-10-24-department-autonomous-delivery-migration-v1/P0-existing-four-legacy-save-gate-v1/system-development-v1/ACTUAL-FIRST-PARTY-Paid2-NATIVE.json', 'sha256': '54f8ceb783463e222d9b003f3f28d36fa513819cf68a057fd290537f9d29b6c6', 'size': 23065},'actual_readback':after,
  'actual_saved_effect':True,'retry_authorized':False,'permission_issued_by_this_reader':False,
  'final_enhancement_and_publish_state':'REQUIRES_CURRENT_NATIVE_READBACK','next_owner':'paid-growth-data-2'}

# Ordinary tasks use professional self-delivery; these checks never grant a
# platform capability, a new account, or a sensitive financial/security action.
SENSITIVE = {'new_payment','purchase','renewal','budget_increase','paid_deadline_extension',
 'new_account_fee','irreversible_delete','destructive_migration','production_resource_destroy',
 'security_permission_change','authentication_change','secret_change','payment_logic_change',
 'new_project','new_account','legal_commitment','financial_commitment','platform_personal_step'}

def current_mode(root):
 if PUBLIC_TEMPLATE_ONLY:return False  # unbound read-only installation, no inherited authority
 config=w.read_json(Path(root)/'data/task-contract.json').get('goal_delivery_runtime',{})
 if config.get('model')!=MODE:return False
 require(config.get('mode_authorization')==OWNER,'current autonomous mode must retain actual owner authorization')
 authority(root)
 return True

def autonomous_goal(goal):
 return isinstance(goal,dict)and goal.get('delivery_model')==MODE

def effective_mode(root,snapshot):
 if autonomous_goal(snapshot.get('goal_delivery')):return current_mode(root)
 # Historical closed contracts remain on their exact original reader. An open
 # task inherits the new process, never new business objects or permissions.
 return bool(current_mode(root)and snapshot.get('current_state')not in w.TERMINAL_STATES
  and isinstance(snapshot.get('goal_delivery'),dict))

def professional(root,role):
 item=w.department_registry(root).get(role,{})
 return role not in ASSISTANTS|{'operations'} and bool(item)and item.get('new_dispatch_enabled')is not False

def required_roles(goal):
 return set(goal['producer_departments']) if autonomous_goal(goal)else set(goal['producer_departments'])|{goal['responsible_assistant']}

def validate_general_goal(root,goal,task_id=None):
 import copy
 authority(root);result=copy.deepcopy(goal);registry=w.department_registry(root)
 require(isinstance(result,dict),'whole goal object required')
 result.setdefault('delivery_model',MODE)
 require(result['delivery_model']==MODE and result.get('responsible_assistant')in {None,''},'ordinary autonomous goal must not assign an assistant')
 result.pop('responsible_assistant',None);result.pop('acceptance_capability',None)
 require(all(isinstance(result.get(k),str)and result[k].strip()for k in ('objective','primary_owner')),'nonempty objective and professional owner required')
 for key in ('completion_criteria','authorized_scope','producer_departments'):
  value=result.get(key);require(isinstance(value,list)and 0<len(value)<=100 and len(set(value))==len(value)
   and all(isinstance(x,str)and x.strip()for x in value),'bounded unique nonempty '+key)
 require(all(not any(c in scope for c in '*?[]|\n\r')for scope in result['authorized_scope']),'exact scopes required')
 require(result['primary_owner']in result['producer_departments'] and all(professional(root,x)for x in result['producer_departments']),'registered professional producers only')
 for key in ('existing_results','dependencies','required_execution_actions','collaboration_scopes'):
  result.setdefault(key,[]);require(isinstance(result[key],list)and len(result[key])<=100,'bounded '+key)
 for pin in result['existing_results']:require(w.file_digest(root,pin.get('path',''))==pin,'existing result bytes changed')
 auth=result.get('human_authorization',{})
 require(isinstance(auth,dict)and all(auth.get(k)for k in ('source_thread_id','message_id','executor','scope','evidence_path'))
  and auth['executor']==result['primary_owner']and auth['scope']in result['authorized_scope'],'original human task authority/executor/scope required')
 pin=w.file_digest(root,auth['evidence_path']);original=document(root,pin);msg=original.get('message',{})
 require(original.get('source_thread_id')==auth['source_thread_id']and msg.get('type')=='userMessage'and msg.get('id')==auth['message_id']
  and any(c.get('type')=='text'and isinstance(c.get('text'),str)and c['text'].strip()for c in msg.get('content',[])), 'real original nonempty human task authority required')
 result['authorization_pin']=pin;result['mode_authorization']=OWNER
 result.setdefault('source_mode','approved_dispatch');result.setdefault('execution_mode','authorized_selfcheck_then_execute')
 require(result['source_mode']in {'approved_dispatch','owner_direct'}and result['execution_mode']=='authorized_selfcheck_then_execute','normal authorized selfcheck execution only')
 if result.get('parent_task_id'):
  w.validate_task_id(result['parent_task_id']);require(result['parent_task_id']!=task_id,'no self-parent')
 seen=set()
 for action in result['required_execution_actions']:
  require(isinstance(action,dict)and all(isinstance(action.get(k),str)and action[k].strip()for k in ('action_id','action_class','scope','department'))
   and action['scope']in result['authorized_scope']and action['department']in result['producer_departments'],'declared exact action/role/scope required')
  key=tuple(action[k]for k in ('action_id','action_class','scope','department'));require(key not in seen,'duplicate action');seen.add(key)
  require(isinstance(action.get('request'),dict),'each execution action binds its exact original request bytes')
  request=document(root,action['request']);require(all(request.get(k)==action[k]for k in ('action_id','action_class','scope','department')),'declared request identity differs')
 for dep in result['dependencies']:
  require(isinstance(dep,dict),'named dependency object required')
  if 'depends_on'in dep:
   require(dep.get('department')in result['producer_departments']and isinstance(dep['depends_on'],list)
    and all(x in result['producer_departments']for x in dep['depends_on']),'actual producer dependency graph required')
  else:require(all(dep.get(k)for k in ('id','owner','scope','unblock_condition'))and dep['scope']in result['authorized_scope'],'named exact dependency/owner required')
 for dep in result['collaboration_scopes']:
  require(dep.get('sender_department')==result['primary_owner']and dep.get('scope')in result['authorized_scope']
   and (professional(root,dep.get('target_department'))or dep.get('target_department')in w.read_json(Path(root)/'data/department-registry.json').get('collaboration_bindings',{})), 'exact professional collaboration only')
 result.setdefault('result_receiver','operations');require(result['result_receiver']=='operations','ordinary final result goes to HQ knowledge, not technical approval')
 # A deterministic criterion map adds no new business demand or approval.
 if not result.get('completion_requirements'):
  require(len(result['authorized_scope'])==1,'multiple scopes require explicit criterion mapping')
  result['completion_requirements']=[{'requirement_id':'criterion-'+str(i+1),'criterion_index':i,'scope':result['authorized_scope'][0],
    'requirement_type':'department_effect','producer_department':result['primary_owner']}for i in range(len(result['completion_criteria']))]
 requirement_rows(result)
 return result

def requirement_rows(goal):
 rows=goal.get('completion_requirements',[]);require(isinstance(rows,list)and rows,'actual frozen criteria map required')
 covered=set();ids=set();answer=[]
 for row in rows:
  producer=row.get('producer_department',row.get('subject',{}).get('producer_department',goal['primary_owner']))
  require(isinstance(row,dict)and isinstance(row.get('requirement_id'),str)and row['requirement_id']not in ids
   and type(row.get('criterion_index'))is int and 0<=row['criterion_index']<len(goal['completion_criteria'])
   and row.get('scope')in goal['authorized_scope']and producer in goal['producer_departments'],'unique original criterion/scope/producer mapping required')
  ids.add(row['requirement_id']);covered.add(row['criterion_index']);answer.append({**row,'producer_department':producer})
 require(covered==set(range(len(goal['completion_criteria']))),'all original criteria need actual effect proof')
 return answer

def sensitive_state(root,snapshot,request):
 """A changed exact request is never covered by the unchanged task grant."""
 goal=snapshot['goal_delivery'];changes=request.get('authorization_changes',[])
 require(isinstance(changes,list)and all(x in SENSITIVE for x in changes),'known sensitive boundaries required')
 if changes:return {'state':'WAIT_EXACT_OWNER_DECISION','owner':'operations / human_owner','sensitive_changes':changes,'blocks_only_this_action':True,'actual_action_allowed':False}
 if request.get('action_class')in {'payment','price_or_contract_commitment'}:
  return {'state':'WAIT_EXACT_OWNER_DECISION','owner':'operations / human_owner','sensitive_changes':['new_payment'if request['action_class']=='payment'else'financial_commitment'],'blocks_only_this_action':True,'actual_action_allowed':False}
 return {'state':'within_original_authorization','actual_action_allowed':False,'owner':goal['primary_owner']}

def action_authority(root,snapshot,requested):
 authority(root);goal=snapshot['goal_delivery'];require(effective_mode(root,snapshot),'current autonomous task required')
 department=requested['department'];original_assignment_ready(root,snapshot,department);require(department in goal['producer_departments']and professional(root,department)
  and requested['scope']in goal['authorized_scope'],'exact original professional/scope required')
 declared=[x for x in goal.get('required_execution_actions',[])if all(x.get(k)==requested.get(k)for k in ('action_id','action_class','scope','department'))]
 require(len(declared)==1,'only an original declared action may execute')
 action=declared[0];pin=action.get('request');require(isinstance(pin,dict)and pin['sha256']==requested.get('payload_sha256'),'exact original authorized request bytes required')
 request=document(root,pin);require(all(request.get(k)==requested.get(k)for k in ('task_id','action_id','action_class','scope','department')),'request task/role/action mismatch')
 require(request.get('source_project_id')==requested.get('source_project_id')==PROJECT,'same original project only')
 bounds=goal.get('execution_bounds',{});observed=request.get('observed',{});desired=request.get('desired',{})
 for key in ('account_id','object_ids'):
  if key in bounds:require(request.get(key)==bounds[key],'exact original '+key+' required')
 if 'average_daily_budget'in bounds:
  require(observed.get('budget_type')==desired.get('budget_type')=='average_daily'and observed.get('currency')==desired.get('currency')==bounds.get('currency')
   and type(desired.get('average_daily_budget'))in {int,float}and desired['average_daily_budget']<=bounds['average_daily_budget'],'no budget/type/currency expansion')
 if 'paid_end'in bounds:
  end=w._parse_observed_at(desired.get('end'));limit=w._parse_observed_at(bounds['paid_end']);start=w._parse_observed_at(desired.get('start'))
  require(end is not None and limit is not None and start is not None and dt.datetime.now(dt.timezone.utc)<start<end<=limit,'accurate future interval within original paid deadline required')
 if 'expected_version'in request:
  before=request.get('before');require(isinstance(before,dict)and before.get('sha256')==request['expected_version'],'current exact version/CAS pin required');document(root,before)
 for name in ('facts','self_check','backup','rollback'):
  value=document(root,request.get(name));require(all(value.get(k)==request.get(k)for k in ('task_id','department','action_id','action_class','scope'))
   and value.get('intent_sha256')==w.sha256_value({k:v for k,v in request.items()if k not in {'facts','self_check','backup','rollback'}}), 'actual exact facts/selfcheck/backup/rollback required')
  if name=='self_check':require(value.get('status')=='PASS','actual successful professional selfcheck')
 boundary=sensitive_state(root,snapshot,request);require(boundary['state']=='within_original_authorization', 'sensitive action needs its exact original owner decision; unrelated work continues')
 return {'action':action,'request':request,'pin':pin,'authorization':goal['authorization_pin'],'mode_authorization':OWNER,'department':department}

def native_execution(root,pin,command_id,role):
 import goal_delivery_runtime as g
 page=g._native_document(root,pin);fixed=w.department_registry(root)[role]['chat_binding']
 require(all(page.get('thread',{}).get(k)==fixed[v]for k,v in {'id':'task_id','title':'title','cwd':'cwd'}.items())
  and fixed.get('project_id')==PROJECT,'actual original executor/project/directory native required')
 matches=[(t,m)for t in page.get('turns',[])for m in t.get('items',[])if m.get('id')==command_id]
 require(len(matches)==1,'one actual native execution required');turn,call=matches[0]
 require(not turn.get('error')and call.get('type')=='commandExecution'and call.get('status')=='completed'
  and call.get('exitCode')==0 and Path(call.get('cwd','')).resolve()==Path(root).resolve(),'actual successful same-project command required')
 raw=w._source_continuation_execution_output(call)
 return turn,call,raw

def validate_effect(root,snapshot,requirement,proof_pin):
 proof=document(root,proof_pin);role=requirement['producer_department'];goal=snapshot['goal_delivery']
 require(proof.get('schema')=='department-autonomous-actual-effect/v1'and all(proof.get(k)==v for k,v in {
  'task_id':snapshot['task_id'],'department':role,'scope':requirement['scope'],'requirement_id':requirement['requirement_id']}.items())
  and proof.get('goal_contract')==snapshot['goal_contract']and proof.get('original_authority')==goal['authorization_pin']
  and proof.get('mode_authorization')==OWNER,'exact original criterion/role/contract/authority required')
 check=document(root,proof.get('self_check'));require(check.get('task_id')==snapshot['task_id']and check.get('department')==role
  and check.get('scope')==requirement['scope']and check.get('status')=='PASS','actual professional selfcheck required')
 turn,call,output=native_execution(root,proof.get('actual_native_execution'),proof.get('native_execution_id'),role)
 observed=w._parse_observed_at(proof.get('observed_at'));require(observed is not None and observed<=dt.datetime.now(dt.timezone.utc)
  and type(turn.get('startedAt'))in {int,float}and turn['startedAt']<=observed.timestamp(),'real ordered operation/readback time required')
 output_pin=proof.get('execution_output');require(w.file_digest(root,output_pin.get('path',''))==output_pin
  and (Path(root)/output_pin['path']).read_bytes()==output,'exact untruncated native output bytes required')
 effects=proof.get('actual_effects');require(isinstance(effects,list)and effects,'actual persisted effect/readback required')
 for pin in effects:
  require(w.file_digest(root,pin.get('path',''))==pin and pin['sha256'].encode()in output,'actual output must bind complete readback SHA; success flag is insufficient')
 if requirement.get('action_class')in w.EXTERNAL_ACTION_CLASSES:
  require(proof.get('policy_decision_id'),'original external action permit required')
  permits=[x for x in w.read_jsonl(Path(root)/w.POLICY_DECISIONS)if x.get('decision_id')==proof['policy_decision_id']]
  require(len(permits)==1 and permits[0].get('status')=='allow'and all(permits[0].get(k)==requirement.get(k)for k in ('action_id','action_class','scope'))
   and permits[0].get('department')==role,'actual original scoped permit required')
 return {'state':'PROVEN','evidence':[proof_pin,*effects],'actual_native_execution':proof['actual_native_execution'],
  'self_check':proof['self_check'],'next_owner':role,'external_permission_issued':False,'QA_required':False}

def record_completion(root,task,input_path,role,rid):
 import goal_delivery_runtime as g
 proof_pin=w.file_digest(root,input_path)
 with w.workflow_lock(root):
  snapshot=g.restore_goal(root,w.read_json(w.snapshot_path(root,task)));require(effective_mode(root,snapshot),'open autonomous task required')
  rows=requirement_rows(snapshot['goal_delivery']);matches=[x for x in rows if x['requirement_id']==rid]
  require(len(matches)==1 and matches[0]['producer_department']==role,'original professional records its own actual effect only')
  original_assignment_ready(root,snapshot,role)
  checked=validate_effect(root,snapshot,matches[0],proof_pin)
  events=[e['details']['autonomous_completion_proof']for e in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS)
   if e.get('task_id')==task and e.get('details',{}).get('autonomous_completion_proof',{}).get('requirement_id')==rid]
  if events:
   require(events[-1]['proof']==proof_pin,'criterion already has an actual proof; preserve history');return {'result':'duplicate_ignored','proof':proof_pin}
  w.append_workflow_event(root,task,snapshot['current_state'],{'autonomous_completion_proof':{'requirement_id':rid,'producer_department':role,'proof':proof_pin,'mode_authorization':OWNER}})
 return {'result':'recorded','proof':proof_pin,'actual_effect':checked,'assistant_approval_required':False}

def completion(root,snapshot):
 rows=requirement_rows(snapshot['goal_delivery']);events=w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS);results=[]
 for requirement in rows:
  matching=[e['details']['autonomous_completion_proof']for e in events if e.get('task_id')==snapshot['task_id']
   and e.get('details',{}).get('autonomous_completion_proof',{}).get('requirement_id')==requirement['requirement_id']]
  result={**requirement,'state':'MISSING','next_owner':requirement['producer_department']}
  if len(matching)>1:result.update(state='BLOCKED',reason='ambiguous actual criterion proof')
  elif matching:
   try:result.update(validate_effect(root,snapshot,requirement,matching[0]['proof']))
   except (w.WorkflowError,ValueError,KeyError,OSError)as error:result.update(state='BLOCKED',reason=str(error))
  results.append(result)
 missing=[x['requirement_id']for x in results if x['state']=='MISSING'];blocked=[x['requirement_id']for x in results if x['state']=='BLOCKED']
 return {'state':'PROVEN'if not missing and not blocked else'BLOCKED'if blocked else'MISSING','requirements':results,
  'missing':missing,'blockers':blocked,'business_goal_closed':False,'closed_scope_only':not missing and not blocked,'HQ_technical_review_required':False}

def receipt_prerequisite(root,snapshot,rows,kind,role):
 goal=snapshot['goal_delivery'];require(role in goal['producer_departments'],'original professional receipt only')
 require(kind!='qa_verdict','assistant QA is historical only; ordinary tasks do not create QA verdicts')
 if kind in {'dispatch_sent','dispatch_failed'}:return
 if kind=='chat_ack':require(any(r.get('receipt_type')=='dispatch_sent'and r.get('department')==role for r in rows),'actual original dispatch before ACK required');return
 if kind=='outbox_received':
  require(goal.get('source_mode')=='owner_direct'or any(r.get('receipt_type')=='chat_ack'and r.get('department')==role for r in rows),'real acknowledged initial responsibility required');return
 if kind in {'execution_result','postcheck'}:return
 raise w.WorkflowError('autonomous task receipt requires a normal exact supported effect')

def reconcile(root,snapshot):
 task=snapshot['task_id'];rows,bad=w._validate_receipt_chain(root,task);bad+=w.validate_workflow_events(root,task)
 proof=completion(root,snapshot)if not bad else {'state':'BLOCKED','requirements':[],'missing':[],'blockers':bad}
 old=snapshot.get('current_state');state='closed'if proof['state']=='PROVEN'else'blocked_evidence_invalid'if bad else'evidence_received'if any(r['receipt_type']=='outbox_received'for r in rows)else'acknowledged'if any(r['receipt_type']=='chat_ack'for r in rows)else'dispatched'if any(r['receipt_type']=='dispatch_sent'for r in rows)else old
 require(old not in w.TERMINAL_STATES or old==state,'closed original goal cannot reopen')
 if state!=old:w.append_workflow_event(root,task,state,{'autonomous_reconciled':True,'actual_effects_proven':proof['state']=='PROVEN','mode_authorization':OWNER})
 snapshot.update(current_state=state,missing_receipts=proof['missing'],blockers=proof['blockers'],next_legal_actions=[]if state=='closed'else[snapshot['goal_delivery']['primary_owner']+':continue_original_task'],updated_at=w.utc_timestamp(),delivery_model=MODE)
 w.atomic_write_json(w.snapshot_path(root,task),snapshot)
 return snapshot,[w.snapshot_path(root,task),Path(root)/w.WORKFLOW_EVENTS]

def native_result(root,request,fixed_id):
 import goal_delivery_runtime as g
 role=request['sender_department'];snapshot=g.restore_goal(root,w.read_json(w.snapshot_path(root,request['task_id'])))
 require(role in snapshot['goal_delivery']['producer_departments']and role not in ASSISTANTS,'actual original professional result required')
 original_assignment_ready(root,snapshot,role)
 require(request.get('source_thread_id')==fixed_id,'exact actual result source thread')
 page=g._native_document(root,request.get('actual_native_completion'))
 if request.get('result_source_phase')=='delivery_ready':
  fixed=w.department_registry(root)[role]['chat_binding'];require(page.get('thread',{}).get('id')==fixed_id==fixed['task_id'],'actual READY author identity')
  pairs=[(t,m)for t in page.get('turns',[])if t.get('id')==request.get('source_turn_id')for m in t.get('items',[])
   if m.get('id')==request.get('source_message_id')and m.get('type')=='agentMessage'and m.get('phase')in {'commentary','final_answer'}]
  require(len(pairs)==1 and pairs[0][0].get('status')in {'inProgress','completed'}and not pairs[0][0].get('error'),'one actual valid ready message')
  turn,message=pairs[0]
 else:turn,message=w._completion_actual_final(root,page,role,turn_id=request.get('source_turn_id'),message_id=request.get('source_message_id'))
 raw=request.get('visible_reply');require(isinstance(raw,dict)and w.file_digest(root,raw.get('path',''))==raw
  and (Path(root)/raw['path']).read_bytes()==message['text'].encode()and request.get('source_reply_sha256')==raw['sha256'],'original UTF8 result bytes required')
 pin=request.get('outbox')or(w.file_digest(root,request['outbox_path'])if request.get('outbox_path')else None)
 require(pin and pin['sha256']==request['result_sha256']and pin['path']in message['text']and pin['sha256']in message['text'],'actual source must identify the exact result bytes')
 observed=w._parse_observed_at(request.get('reply_observed_at'));now=dt.datetime.now(dt.timezone.utc)
 require(observed is not None and observed<=now,'real source observation timestamp required')
 native_time=turn.get('completedAt')if request.get('result_source_phase')!='delivery_ready'else turn.get('startedAt')
 require(type(native_time)in {int,float}and native_time<=observed.timestamp(),'native source event must precede observation')
 w.validate_outbox(root,[pin],role,request['task_id']);box=document(root,pin)
 require(box.get('candidate_version')==request['candidate_version'],'exact candidate version required')
 return {'actual_native_completion':request['actual_native_completion'],'visible_reply':raw,'source_turn_id':turn['id'],
  'source_message_id':message['id'],'source_reply_sha256':raw['sha256'],'result_source_phase':request.get('result_source_phase','completed_final'),
  'mode_authorization':OWNER,'assistant_approval_required':False}

def autonomous_result_route(root,identity):
 snapshot=w.read_json(w.snapshot_path(root,identity['task_id']))
 if not current_mode(root)or not snapshot.get('goal_delivery'):return None
 if identity['sender_department']in ASSISTANTS:return {'lane':'historical_read_only','target_department':None,'automatic_wakeup_allowed':False,'reason':'retired assistant history only'}
 if identity['sender_department']not in snapshot['goal_delivery']['producer_departments']:return None
 rows=w._result_handoff_rows(root,identity['task_id']);same=[r for r in rows if all(r.get(k)==identity[k]for k in ('task_id','sender_department','candidate_version','result_sha256'))]
 queued=[r for r in same if r.get('event')=='notification_queued']
 # Never reinterpret a committed old recipient. Suppress its new activation;
 # actual original SQL/native intake remains readable before this classification.
 if queued and (queued[0].get('target_department')or queued[0].get('responsible_assistant'))in ASSISTANTS:
  return {'lane':'historical_read_only','target_department':None,'automatic_wakeup_allowed':False,'reason':'original assistant transport retained without new wakeup'}
 target='operations';source={}
 parent_id=snapshot['goal_delivery'].get('parent_task_id')
 if parent_id:
  parent=w.read_json(w.snapshot_path(root,w.validate_task_id(parent_id)));owner=parent.get('goal_delivery',{}).get('primary_owner')
  require(parent and owner and professional(root,owner),'real original parent professional owner required')
  target=owner
 if queued:source=document(root,queued[0]['outbox'])
 else:
  producer=[r for r in w.read_jsonl(w.receipts_path(root,identity['task_id']))if r.get('receipt_type')=='outbox_received'and r.get('department')==identity['sender_department']and any(p.get('sha256')==identity['result_sha256']for p in r.get('evidence',[]))]
  if producer:
   pins=[p for p in producer[-1]['evidence']if p.get('sha256')==identity['result_sha256']];require(len(pins)==1,'exact original producer outbox');source=document(root,pins[0])
 collab=source.get('collaboration_return')
 if isinstance(collab,dict):
  parent=w.read_json(w.snapshot_path(root,collab.get('parent_task_id','')));owner=parent.get('goal_delivery',{}).get('primary_owner')
  require(parent and owner==collab.get('primary_owner')and professional(root,owner)and snapshot['goal_delivery'].get('parent_task_id')==parent['task_id'], 'actual original parent owner for collaboration return')
  target=owner
 return {'lane':'HQ_knowledge'if target=='operations'else'professional_acceptance','target_department':target,'source_mode':MODE,
  'acceptance_proven':False,'notification_proven':False,'HQ_second_review_required':False,'automatic_wakeup_allowed':True,'knowledge_only':target=='operations'}

def register_preflight(root,task,input_path):
 import goal_delivery_runtime as g
 pin=w.file_digest(root,input_path);item=document(root,pin)
 with w.workflow_lock(root):
  snapshot=g.restore_goal(root,w.read_json(w.snapshot_path(root,task)));goal=snapshot['goal_delivery']
  require(autonomous_goal(goal)and snapshot.get('current_state')not in w.TERMINAL_STATES,'open original autonomous task required')
  req=document(root,item.get('request'));require(all(item.get(k)==req.get(k)for k in ('task_id','department','action_id','action_class','scope')),'fresh exact preflight request identity')
  declared=[x for x in goal['required_execution_actions']if all(x.get(k)==req.get(k)for k in ('department','action_id','action_class','scope'))]
  require(len(declared)==1,'only declared original action can refresh observations')
  original=document(root,declared[0]['request']);stable=('task_id','department','action_id','action_class','scope','source_project_id','account_id','object_ids','operation','desired')
  require(all(req.get(k)==original.get(k)for k in stable),'fresh source cannot change authorized objects, fields or desired business effect')
  for name in ('facts','self_check','backup','rollback'):
   value=document(root,req.get(name));require(value.get('task_id')==task and value.get('department')==req['department'],'exact task-bound source evidence')
   if name=='self_check':require(value.get('status')=='PASS','successful professional selfcheck')
  previous=[e['details']['autonomous_action_preflight']for e in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS)
    if e.get('task_id')==task and e.get('details',{}).get('autonomous_action_preflight',{}).get('action_id')==req['action_id']]
  if previous and previous[-1]['input']==pin:return {'result':'duplicate_ignored','input':pin,'assistant_approval_required':False}
  w.append_workflow_event(root,task,snapshot['current_state'],{'autonomous_action_preflight':{'action_id':req['action_id'],'input':pin,'request':item['request'],'original_authority':goal['authorization_pin']}})
 return {'result':'recorded','input':pin,'assistant_approval_required':False,'external_permission_issued':False}

def policy(root,requested):
 snapshot=w.read_json(w.snapshot_path(root,requested['task_id']))
 if not autonomous_goal(snapshot.get('goal_delivery')):return None
 if requested['action_class']not in w.EXTERNAL_ACTION_CLASSES:return None
 require(not requested.get('approval_id')and not requested.get('target_project_id')and not requested.get('target_department'), 'ordinary exact task execution, not a borrowed permit or cross-project route')
 context=action_authority(root,snapshot,requested);role=context['department'];binding=w.department_registry(root)[role]['chat_binding']
 require(binding.get('project_id')==PROJECT and Path(binding.get('cwd','')).resolve()==Path(root).resolve()
  and w._chat_binding_healthy(binding,verification_ttl_hours=26),'current professional executor identity/health required')
 request=context['request'];observed=w._parse_observed_at(request.get('observed_at'))
 require(observed is not None and 0<=(dt.datetime.now(dt.timezone.utc)-observed).total_seconds()<=300,'fresh actual execution observation required; reports do not expire')
 key=w.sha256_value([requested[k]for k in ('task_id','department','action_id','action_class','scope')])
 with w.workflow_lock(root):
  prior=[x for x in w.read_jsonl(Path(root)/w.POLICY_DECISIONS)if x.get('autonomous_action_key')==key and x.get('status')=='allow']
  require(not prior,'original exact action already issued; read actual/unknown effect before any recovery, never replay')
  value={**requested,'status':'preflight_ready_not_a_permit','actual_action_allowed':False,'approval_basis':MODE,
   'original_authority':context['authorization'],'mode_authorization':OWNER,'exact_request':context['pin'],
   'autonomous_action_key':key,'checked_at':w.utc_timestamp(),'assistant_approval_required':False,'retry_authorized':False}
  if not requested.get('consume_approval'):return value,[Path(root)/w.ACTION_POLICY]
  value.update(status='allow',actual_action_allowed=True,decision_id='pol-'+w.sha256_value([value,key])[:20],approval_status='consumed_for_original_exact_autonomous_action')
  w.append_jsonl_locked(Path(root)/w.POLICY_DECISIONS,value)
 return value,[Path(root)/w.POLICY_DECISIONS]


def task_status(root,snapshot):
 proof=completion(root,snapshot);return {'task_id':snapshot['task_id'],'delivery_model':MODE,'primary_owner':snapshot['goal_delivery']['primary_owner'],
  'state':'completed_scope'if proof['state']=='PROVEN'else'specific_dependency_wait'if proof['blockers']else'executing',
  'responsible_assistant':None,'completion_obligations':proof,'HQ_second_review_required':False,'business_goal_closed':False}


def received_knowledge(root,request):
 """Knowledge intake proves an actual receiver read, not another technical review."""
 import goal_delivery_runtime as g
 role=request.get('coordinator_role','operations');page=g._native_document(root,request.get('actual_receiver_native'))
 target=autonomous_result_route(root,request).get('target_department');require(role==target,'one exact current result receiver')
 fixed=w.department_registry(root)[role]['chat_binding'];require(all(page.get('thread',{}).get(k)==fixed[v]for k,v in {'id':'task_id','title':'title','cwd':'cwd'}.items()),'actual receiver native identity')
 pairs=[(t,m)for t in page.get('turns',[])for m in t.get('items',[])if m.get('id')==request.get('actual_receiver_message_id')]
 require(len(pairs)==1 and not pairs[0][0].get('error')and pairs[0][1].get('type')=='agentMessage'
  and request['result_sha256']in pairs[0][1].get('text',''),'receiver must actually name this exact result SHA')
 return {'actual_receiver_native':request['actual_receiver_native'],'actual_receiver_message_id':request['actual_receiver_message_id'],
  'acceptance_proven':False,'HQ_second_review_required':False}


def record_autonomous_result(root,request):
 import result_coordination as rc,uuid
 task=w.validate_task_id(request['task_id']);identity=rc.exact_identity(request);event=request['event']
 require(event in {'notification_queued','controller_received'},'ordinary delivery has no assistant QA/technical decision stage')
 role=identity['sender_department'];fixed=w.department_registry(root)[role]['chat_binding']['task_id']
 rows=w._result_handoff_rows(root,task);same=[x for x in rows if all(x.get(k)==v for k,v in identity.items())]
 existing=[x for x in same if x.get('event')==event]
 if existing:
  require(len(existing)==1 and existing[0].get('idempotency_key')==request.get('idempotency_key'),'one exact original result event only')
  return {**existing[0],'result':'duplicate_ignored'},[w.result_handoff_path(root,task)]
 source=native_result(root,request,fixed)if event=='notification_queued'else None
 queued=[x for x in same if x.get('event')=='notification_queued']
 if event!='notification_queued':require(len(queued)==1,'one original queued source before intake/transport')
 route=autonomous_result_route(root,identity);require(route and route.get('automatic_wakeup_allowed'),'current professional result route required')
 pin=w.file_digest(root,request['outbox_path'])if request.get('outbox_path')else request.get('outbox')or queued[0]['outbox']
 require(pin['sha256']==identity['result_sha256'],'exact original result pin')
 if queued:require(pin==queued[0]['outbox'],'result intake must retain original queued bytes')
 knowledge=received_knowledge(root,request)if event=='controller_received'else{}
 row={**request,**identity,**(source or {}),**knowledge,'record_id':str(uuid.uuid4()),'schema_version':'1.0','created_at':w.utc_timestamp(),
  'outbox':pin,'evidence':[w.file_digest(root,p)for p in request.get('evidence_paths',[])],
  'target_department':route['target_department'],'coordinator_role':request.get('coordinator_role','operations'),
  'mode_authorization':OWNER,'business_goal_closed':False,'assistant_approval_required':False}
 row.pop('outbox_path',None);row.pop('evidence_paths',None)
 require(isinstance(row.get('idempotency_key'),str)and row['idempotency_key'],'normal stable effect idempotency key')
 if event=='controller_received':
  # Use the same SQL reservation table and native readback as historical result
  # effects. No alternate business ledger or synthetic claim/assistant is made.
  payload=rc._payload(root,request);effect=rc._sha([event,row['idempotency_key']])
  with rc.coordination_lock(root):
   store=rc.CoordinationStore(root)
   try:
    store._begin();old=store.conn.execute('SELECT status,payload_json FROM reservations WHERE result_key=? AND effect_key=?',(rc._key(identity),effect)).fetchone()
    require(old is None,'existing/unknown original intake must be recovered, not reappended')
    store.conn.execute("INSERT INTO reservations VALUES(?,?,?,'uncertain',NULL)",(rc._key(identity),effect,rc._canonical(payload)));store.conn.commit()
    append_result_record(root,task,row)
    admission=rc.HandoffAdmission(store,identity,effect,payload);admission.complete(row)
   finally:store.close()
 else:
  append_result_record(root,task,row)
  if event=='notification_queued':rc.notification_enqueue(root,request)
 return {**row,'result':'recorded'},[w.result_handoff_path(root,task)]

def queued_source(root,identity):
 rows=[r for r in w._result_handoff_rows(root,identity['task_id'])if all(r.get(k)==identity[k]for k in ('task_id','sender_department','candidate_version','result_sha256'))and r.get('event')=='notification_queued']
 require(len(rows)==1,'one actual original queued result source required');row=rows[0]
 require(row.get('mode_authorization')==OWNER,'actual current-mode queued source required')
 native_result(root,row,w.department_registry(root)[identity['sender_department']]['chat_binding']['task_id'])
 return row

def knowledge_source(root,identity,require_transport=False):
 row=queued_source(root,identity);require(not require_transport or any(r.get('event')=='notification_sent'and all(r.get(k)==identity[k]for k in ('task_id','sender_department','candidate_version','result_sha256'))for r in w._result_handoff_rows(root,identity['task_id'])),'actual notification transport not yet proven')
 return {'identity':identity,'source_mode':MODE,'acceptance_proven':False,'notification_proven':False,
  'source_reply_sha256':row['source_reply_sha256'],'source_thread_id':row['source_thread_id'],'source_turn_id':row['source_turn_id'],
  'outbox':row['outbox'],'dependency_fingerprint':w.sha256_value([identity,row['outbox'],row['actual_native_completion'],OWNER]),
  'HQ_second_review_required':False,'actual_source':row}


def autonomy_record_applies(root,request):
 snapshot=w.read_json(w.snapshot_path(root,request.get('task_id','')))
 return bool(current_mode(root)and isinstance(snapshot.get('goal_delivery'),dict)
  and request.get('sender_department')in snapshot.get('goal_delivery',{}).get('producer_departments',[])
  and request.get('event')in {'notification_queued','controller_received'})

def validate_native_ack(root,snapshot,role,pins):
 import goal_delivery_runtime as g
 candidates=[]
 for pin in pins:
  obj=document(root,pin)
  if obj.get('schema')=='department-native-ack/v1':candidates.append(obj)
 require(len(candidates)==1,'one actual native ACK source, never just a boolean')
 obj=candidates[0];require(obj.get('task_id')==snapshot['task_id']and obj.get('department')==role,'exact original ACK task/role')
 page=g._native_document(root,obj.get('actual_native'));fixed=w.department_registry(root)[role]['chat_binding']
 require(all(page.get('thread',{}).get(k)==fixed[v]for k,v in {'id':'task_id','title':'title','cwd':'cwd'}.items()),'actual fixed ACK sender')
 matches=[(t,m)for t in page.get('turns',[])if t.get('id')==obj.get('source_turn_id')for m in t.get('items',[])if m.get('id')==obj.get('source_message_id')]
 require(len(matches)==1 and not matches[0][0].get('error')and matches[0][1].get('type')=='agentMessage'
  and snapshot['task_id']in matches[0][1].get('text',''),'real nonempty original task ACK')
 reply=obj.get('visible_reply');require(w.file_digest(root,reply.get('path',''))==reply
  and (Path(root)/reply['path']).read_bytes()==matches[0][1]['text'].encode(),'actual ACK UTF8 differs')
 return obj

def original_assignment_ready(root,snapshot,role):
 if snapshot['goal_delivery'].get('source_mode')=='owner_direct':return True
 rows=w.read_jsonl(w.receipts_path(root,snapshot['task_id']));fixed=w.department_registry(root)[role]['chat_binding']['task_id']
 sent=[r for r in rows if r.get('receipt_type')=='dispatch_sent'and r.get('department')==role and r.get('chat_task_id')==fixed]
 require(sent,'original actual professional dispatch required')
 acks=[r for r in rows if r.get('receipt_type')=='chat_ack'and r.get('department')==role and r.get('chat_task_id')==fixed
  and r.get('ack_nonempty')and rows.index(r)>rows.index(sent[0])]
 require(acks,'original actual professional ACK required')
 if autonomous_goal(snapshot['goal_delivery']):validate_native_ack(root,snapshot,role,acks[0]['evidence'])
 return True


def append_result_record(root,task,row):
 with w.workflow_lock(root):
  rows=w._result_handoff_rows(root,task)
  require(not any(r.get('idempotency_key')==row.get('idempotency_key')for r in rows),'existing exact result effect; read it instead of replay')
  row['previous_hash']=rows[-1]['record_hash']if rows else''
  row['record_hash']=w.sha256_value({k:v for k,v in row.items()if k!='record_hash'})
  w.append_jsonl_locked(w.result_handoff_path(root,task),row)

class HistoricalRegistry(dict):
 """Iteration is current roles only; explicit old actor lookup is read-only."""
 def __init__(self,current,historical):
  super().__init__(current);self.historical=historical
 def __contains__(self,key):return dict.__contains__(self,key)or key in self.historical
 def __deepcopy__(self,memo):
  import copy
  return HistoricalRegistry(copy.deepcopy(dict(self),memo),copy.deepcopy(self.historical,memo))
 def __missing__(self,key):
  if key in self.historical:return self.historical[key]
  raise KeyError(key)
 def get(self,key,default=None):
  return dict.get(self,key,self.historical.get(key,default))


def work_boundary(root,role,assignment=None,read_assignment=True):
 registry=w.department_registry(root);item=registry.get(role,{})
 require(item,'registered current or historical role')
 if role in ASSISTANTS:
  return {'schema':'goal-work-boundary/v1','department':role,'role_state':'standby'if role=='operations-assistant'else'retired_history',
   'grouped_work':{'current_blockers':[],'current_execution':[],'historical_anomalies':[]},'actual_current_assignment':None,
   'ready_actions':[],'waiting_actions':[],'source_errors':[],'actionable_count':0,'can_report_no_change':True,
   'resume_before_maintenance':False,'inventory_is_permission':False,'messages_sent':0,'writes_performed':False,
   'automatic_wakeup_allowed':False,'explicit_auxiliary_task_required':role=='operations-assistant'}
 assignments=w.read_json(Path(root)/'data/department-current-assignment.json');current_pin=assignments.get('assignments',{}).get(role)
 ready=[];waiting=[];errors=[];historical=[];completed=[];current=None;seen=set()
 entries=[('current',current_pin)]+[('suspended',p)for p in assignments.get('suspended_assignments',{}).get(role,[])]
 for position,pin in entries:
  if not pin:continue
  try:
   source=document(root,pin);task=source.get('task_id');require(task and source.get('department')==role,'original task assignment identity')
   if task in seen:continue
   seen.add(task);snapshot=w.read_json(w.snapshot_path(root,task));goal=snapshot.get('goal_delivery',{})
   view={'task_id':task,'owner':goal.get('primary_owner',role),'position':position,'source':pin,'state':snapshot.get('current_state'),'source_verified_for_execution':False}
   if position=='current':
    from goal_continuity import _dispatch_source
    _dispatch_source(root,source);view['source_verified_for_execution']=True;current={**source,'source':pin,'resume_required':snapshot.get('current_state')not in w.TERMINAL_STATES}
   if snapshot.get('current_state')in w.TERMINAL_STATES:completed.append(view)
   elif position=='suspended':waiting.append({**view,'kind':'original_suspended_assignment','next_action':'resume only at original work boundary with fresh exact execution source'})
   else:ready.append({**view,'kind':'original_current_assignment','next_action':'continue_authorized_original_professional_goal'})
  except (w.WorkflowError,ValueError,KeyError,OSError,TypeError)as error:
   errors.append({'source':pin,'owner':role,'position':position,'reason':str(error),'blocks_other_tasks':False})
 # A retired assistant's residual handoff belongs to its frozen professional
 # owner. This is a visible continuation, not a fabricated dispatch/ACK.
 for assistant in ASSISTANTS:
  inherited=[assignments.get('assignments',{}).get(assistant),*assignments.get('suspended_assignments',{}).get(assistant,[])]
  for pin in inherited:
   if not pin:continue
   try:
    original=document(root,pin);task=original.get('task_id')
    if not task or task in seen:continue
    snap=w.read_json(w.snapshot_path(root,task));goal=snap.get('goal_delivery',{})
    if goal.get('primary_owner')!=role or snap.get('current_state')in w.TERMINAL_STATES:continue
    seen.add(task);ready.append({'task_id':task,'owner':role,'kind':'original_owner_after_assistant_retirement','source':pin,'position':'original_owner_continuation','source_verified_for_execution':False,'next_action':'continue_original_authorized_goal_with_fresh_execution_checks_no_new_assistant'})
   except (w.WorkflowError,ValueError,KeyError,OSError,TypeError)as error:errors.append({'source':pin,'owner':role,'reason':str(error),'blocks_other_tasks':False})
 # Queue state is a distinct live input. A committed intake is checked against
 # its original frozen route; historical assistant queues never become new work.
 for path in sorted((Path(root)/'logs/result-notifications').glob('*.json')):
  if path.is_symlink():continue
  record=w.read_json(path);identity=record.get('identity',{});target=record.get('route',{}).get('target_department')
  if role not in {identity.get('sender_department'),target}:continue
  if target in ASSISTANTS:continue
  try:
   import result_coordination as rc
   intake=rc.received_notification(root,record)
   if intake is not None:
    completed.append({**identity,'kind':'committed_original_intake','record_id':intake['record_id']});continue
   if record.get('delivered'):continue
   state=record.get('native_queue_transport',{}).get('state')
   detail={**identity,'owner':role,'kind':'original_result_transport','queue_acceptance_is_receipt':False}
   if state in {'sending','uncertain','accepted'}:waiting.append({**detail,'next_action':'read_original_native_effect_no_resend'})
   elif role==identity.get('sender_department'):ready.append({**detail,'next_action':'normal_exact_sender_notification_prepare'})
   elif role==target:ready.append({**detail,'next_action':'actually_read_original_department_result_no_technical_review'})
  except (w.WorkflowError,ValueError,KeyError,OSError,TypeError)as error:errors.append({**identity,'owner':role,'reason':str(error),'blocks_other_tasks':False})
 grouped={'current_execution':[x for x in ready if x.get('kind')=='original_current_assignment'],
  'valid_unfinished':ready+waiting,'ready':ready,'waiting':waiting,'historical_anomalies':historical,
  'completed_scope':completed,'current_blockers':[e for e in errors if e.get('position')=='current']}
 return {'schema':'goal-work-boundary/v1','department':role,'delivery_model':MODE,'grouped_work':grouped,
  'actual_current_assignment':current,'ready_actions':ready,'waiting_actions':waiting,'source_errors':errors,
  'actionable_count':len(ready),'can_report_no_change':not ready and not grouped['current_blockers'],
  'source_error_fingerprint':w.sha256_value(errors),'resume_before_maintenance':bool(ready),
  'inventory_is_permission':False,'native_wakeup_guaranteed':False,'messages_sent':0,'writes_performed':False,
  'HQ_continuous_watch_required':False}

def historical_source_bytes(root,relative):
 """Only byte-identical moved role definitions, never a current rule alias."""
 from pathlib import PurePosixPath
 require(isinstance(relative,str)and not PurePosixPath(relative).is_absolute()and '..'not in PurePosixPath(relative).parts,'relative historical source only')
 registry=w.read_json(Path(root)/'data/department-registry.json');mapping=registry.get('historical_role_source_moves',{})
 entry=mapping.get(relative)
 if entry is None:return None
 require(registry.get('mode_authorization')==OWNER and entry.get('retired_role')in {'operations-assistant-2','operations-assistant-3'},'only authenticated retired role source movement')
 authority(root);target=Path(root)/entry['target'];require(target.resolve().is_relative_to(Path(root).resolve())and target.is_file()
  and not target.is_symlink(),'real project-local historical bytes required')
 import hashlib
 raw=target.read_bytes();require(hashlib.sha256(raw).hexdigest()==entry['sha256']and len(raw)==entry['size'],'moved historical bytes changed')
 return raw


def historical_registry_view(registry):
 import copy
 result={k:copy.deepcopy(v)for k,v in registry.items()}
 for key,item in getattr(registry,'historical',{}).items():result[key]=copy.deepcopy(item)
 for item in result.values():
  if 'historical_coordination_authority'in item:
   item['new_dispatch_enabled']=item.get('historical_new_dispatch_enabled',False)
   item['coordination_authority']=copy.deepcopy(item['historical_coordination_authority'])
 return result


def legacy_status(root,snapshot):
 """Read frozen history without requiring a retired assistant to qualify anew.

 Stored QA remains a historical fact, never a new permission or a current
 actual-effect proof. The original frozen contract and whole receipt hash chain
 must still be exact. No snapshot, receipt, claim or action is written here.
 """
 import goal_delivery_runtime as g
 snapshot=g.restore_goal(root,snapshot);goal=snapshot['goal_delivery']
 document(root,snapshot['goal_contract']);previous='';verdicts=[]
 for row in w.read_jsonl(w.receipts_path(root,snapshot['task_id'])):
  require(row.get('task_id')==snapshot['task_id']and row.get('previous_hash')==previous
   and row.get('receipt_hash')==w.sha256_value(w._receipt_payload_for_hash(row)),'intact original historical receipt chain required')
  previous=row['receipt_hash']
  if row.get('receipt_type')=='qa_verdict':
   require(row.get('department')==goal.get('responsible_assistant'),'historical verdict actor differs from frozen contract')
   for pin in row.get('evidence',[]):document(root,pin)
   verdicts.append({k:row.get(k)for k in ('receipt_id','department','scope','verdict','created_at','evidence')})
 return {'task_id':snapshot['task_id'],'state':'completed_scope'if snapshot.get('current_state')=='closed'else'original_professional_continuation',
  'native_workflow_state':snapshot.get('current_state'),'primary_owner':goal['primary_owner'],
  'delivery_model':MODE,'responsible_assistant':None,'historical_responsible_assistant':goal.get('responsible_assistant'),
  'historical_QA':verdicts,'historical_receipt_chain':w.file_digest(root,w.rel_path(root,w.receipts_path(root,snapshot['task_id']))),
  'historical_QA_is_current_permission':False,'current_effect_proof':'use original actual effect reader; no new PASS synthesized',
  'historical_read_only':True,'current_permission_issued':False,'HQ_second_review_required':False,'business_goal_closed':False}


def maintenance_preflight(root):
 """Original weekly maintenance wiring only; no cleanup or borrowed A3 grant."""
 authority(root);config=w.read_json(Path(root)/'data/department-autonomy-maintenance.json')
 require(current_mode(root)and config.get('schema')=='autonomous-original-maintenance-wiring/v1'
  and config.get('owner_authorization')==OWNER and config.get('original_automation_id')=='flash-cast-20-00'
  and config.get('professional_owner')=='system-development'and config.get('old_A3_grant_inherited')is False,
  'exact current original maintenance owner/source required')
 source=document(root,config['HQ_explicit_maintenance_assignment'])
 fixed=w.department_registry(root)['operations']['chat_binding'];require(source.get('thread',{}).get('id')==fixed['task_id']
  and Path(source['thread']['cwd']).resolve()==Path(root).resolve(),'actual HQ maintenance instruction source')
 calls=[m for t in source.get('turns',[])for m in t.get('items',[])if m.get('id')==config['assignment_native_call_id']]
 require(len(calls)==1 and calls[0].get('status')=='completed'and calls[0].get('tool')=='send_message_to_thread'
  and calls[0].get('arguments',{}).get('threadId')==w.department_registry(root)['system-development']['chat_binding']['task_id']
  and 'HQ指定由system-development承接'in calls[0].get('arguments',{}).get('prompt',''),'real bounded professional maintenance assignment')
 current=w.department_registry(root)['system-development']['chat_binding']
 require(all(current.get(k)==v for k,v in config['executor_binding'].items())and professional(root,'system-development'),'fresh actual maintenance executor binding')
 from safe_cleanup import ALLOWED,PROTECTED
 require(set(config['allowed_inspection_roots'])==ALLOWED and config['irreversible_deletion_requires_exact_owner_list_confirmation']is True
  and config['inspection_is_deletion_permission']is False,'original narrow inspection/deletion boundaries')
 active=config.get('current_status')=='ACTIVE'
 if active:
  activation=document(root,config.get('actual_activation_receipt'));binding=activation.get('weekly_maintenance',{}).get('local_TOML_readback',{})
  require(activation.get('task_id')=='fc-20261024-original-flow-recovery-execution-stage-v1'
   and activation.get('receiver')=='operations'and activation.get('professional_owner')=='system-development'
   and binding.get('id')==config['original_automation_id']and binding.get('status')=='ACTIVE'
   and binding.get('target_thread_id')==current['task_id']and binding.get('old_A3_target_present')is False,
   'real HQ original maintenance activation receipt and exact SYS target required')
 return {'schema':config['schema'],'state':'PROFESSIONAL_PREFLIGHT_READY_ORIGINAL_WEEKLY_BINDING_ACTIVE' if active else 'PROFESSIONAL_PREFLIGHT_READY_HQ_REBIND_ORIGINAL_PAUSED_SCHEDULE',
  'last_verified_automation_status':config.get('current_status'),'real_scheduled_run_verified':False,
  'automation_id':config['original_automation_id'],'professional_owner':'system-development','executor_binding':config['executor_binding'],
  'actual_current_mode':MODE,'same_schedule_source':config['original_schedule_source'],'allowed_inspection_roots':sorted(ALLOWED),
  'protected_directory_names':sorted(PROTECTED),'read_only_scan_entry':'python3 tools/flashcast_ops.py safe-cleanup --mode scan --usage <fresh actual usage JSON> --output data/maintenance/cleanup-plans/<exact immutable plan>.json',
  'next_owner':'system-development' if active else 'operations','next_action':'await original weekly trigger; inspect exact current use/references and authority before any cleanup; do not rebind or inherit A3 permit' if active else 'rebind exact original automation target and professional prompt, retain original weekly schedule; do not inherit A3 permit',
  'fresh_usage_and_exact_plan_required':True,'deletion_executed':False,'cleanup_goal_completed':False,'assistant_approval_required':False,
  'new_external_permission_issued':False,'automatic_wakeup_verified':False}

if __name__=='__main__':
 import argparse
 parser=argparse.ArgumentParser(description='Current autonomous department runtime entry')
 parser.add_argument('command',choices=['maintenance-preflight']);parser.add_argument('--root',default=str(Path(__file__).resolve().parents[1]))
 args=parser.parse_args()
 try:print(json.dumps(maintenance_preflight(Path(args.root).resolve()),ensure_ascii=False,indent=2))
 except (w.WorkflowError,ValueError,OSError,KeyError)as error:
  print(json.dumps({'state':'BLOCKED_EXACT_MAINTENANCE_SOURCE','reason':str(error),'deletion_executed':False},ensure_ascii=False));raise SystemExit(1)
