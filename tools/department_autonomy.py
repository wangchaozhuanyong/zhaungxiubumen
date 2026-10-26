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
 # Mode authority is current live configuration, never a historical validation projection.
 raw=document(root,OWNER);registry=w.read_json(Path(root)/'data/department-registry.json')
 hq=next(x for x in registry['departments']if x['id']=='operations')['chat_binding']
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

RUNTIME_HEALTH_REQUEST_TEXT='本原系统恢复目标的只读健康维护协作：核对本固定角色/项目/目录，运行上列既有只读有效视图一次，非空回复本task_id、action_id、实际输出路径和原工作边界或准确依赖。只在本聊天回复，不注册新业务任务，不改当前/暂停指派，不重做业务成果，不向助理派工，不执行CMS/Ads/账号/费用/部署。'

def _runtime_health_packet(root, snapshot, request, packet, payload):
 """Original SYS maintenance, never a new business producer or execution grant."""
 auth=authority(root);goal=participant(root,snapshot,request.get('sender_department'))
 frozen=document(root,snapshot['goal_contract']);target=request.get('target_department')
 require(request.get('sender_department')==goal.get('primary_owner')=='system-development'
  and target!='system-development'and professional(root,target)
  and all(goal.get(k)==frozen.get(k)for k in ('primary_owner','producer_departments','authorized_scope','authorization_pin')),
  'original frozen SYS responsibility and current professional health target required')
 registry=w.department_registry(root);source=registry['system-development']['chat_binding'];dest=registry[target]['chat_binding']
 expected={'schema':'department-runtime-health-request/v1','task_id':snapshot['task_id'],
  'scope':request.get('scope'),'action_id':request.get('action_id'),'sender_department':'system-development',
  'target_department':target,'target_thread_id':dest['task_id'],'project_id':PROJECT,'cwd':str(Path(root).resolve()),
  'goal_contract':snapshot['goal_contract'],'owner_authorization':OWNER,
  'read_only_entry':['python3','tools/flashcast_ops.py','department-learning-effective','--department',target,'--phase','resume'],
  'request':RUNTIME_HEALTH_REQUEST_TEXT}
 require(request.get('action_class')=='thread_message'and packet==expected and request.get('task_id')==snapshot['task_id']
  and request.get('scope')in goal['authorized_scope'] and request.get('action_id')
  and request.get('payload_sha256')==payload['sha256'] and request.get('assignment_record_required')is False,
  'exact read-only maintenance packet/task/scope/source required; no business or caller flags')
 require(source.get('project_id')==dest.get('project_id')==request.get('source_project_id')==request.get('target_project_id')==PROJECT
  and Path(source.get('cwd','')).resolve()==Path(root).resolve()==Path(dest.get('cwd','')).resolve()
  and all(request.get(k)==dest.get(v)for k,v in {'target_thread_id':'task_id','target_thread_title':'title','target_cwd':'cwd','target_sidebar_section_id':'sidebar_section_id'}.items())
  and w._chat_binding_healthy(source,verification_ttl_hours=26)and w._chat_binding_healthy(dest,verification_ttl_hours=26),
  'actual same-project fixed maintenance identities and current reply health required')
 return {**auth,'source':payload,'report':payload,'scope':request['scope'],'sender_department':'system-development',
  'target_department':target,'purpose':'read_only_registered_role_health','business_producer_added':False,
  'current_assignment_changed':False,'external_permission_issued':False}


def _professional_readonly_coordination(root, snapshot, action):
 """Authenticate one HQ-decided ordinary message; never add a producer or execution grant."""
 import ast, re, shlex
 from goal_delivery_runtime import _owner_decision_delegation
 goal=participant(root,snapshot,action.get('sender_department'))
 frozen=document(root,snapshot['goal_contract']);registry=w.department_registry(root)
 require(autonomous_goal(goal)and autonomous_goal(frozen)
  and all(goal.get(k)==frozen.get(k)for k in ('primary_owner','parent_task_id','producer_departments','authorized_scope','human_authorization','collaboration_scopes')),
  'unchanged frozen autonomous owner, scope, authority and participants required')
 sender=action.get('sender_department');target=action.get('target_department')
 require(sender==frozen.get('primary_owner')and sender!=target and professional(root,sender)and professional(root,target)
  and action.get('schema')=='current-autonomous-readonly-coordination-action/v1'
  and action.get('goal_contract')==snapshot['goal_contract']and action.get('task_id')==snapshot['task_id']
  and action.get('scope')in frozen['authorized_scope']and action.get('action_class')=='thread_message'
  and action.get('action_id')and not action.get('approval_id')and action.get('assignment_record_required')is False,
  'one original professional-owner readonly message within unchanged contract required')
 source=action.get('hq_coordination_source',{});decision_pin=source.get('decision');decision=document(root,decision_pin)
 delegation=_owner_decision_delegation(root)
 require(decision.get('schema')=='HQ-exact-routine-readonly-coordination-decision/v1'
  and all(decision.get(k)==action.get(k)for k in ('task_id','scope'))
  and decision.get('professional_owner')==sender and decision.get('decision_owner')=='operations'
  and decision.get('delegation')==delegation['source']
  and decision.get('decision')=='coordinate_exact_nonpayment_change_preserve_action_gates'
  and decision.get('normal_registration_still_required')is True
  and decision.get('external_permission_issued')is False and decision.get('new_account_or_fees')is False,
  'actual exact delegated HQ readonly decision required; no new authority')
 original=document(root,decision.get('actual_blocked_request'));failed=document(root,decision.get('actual_blocked_result'))
 keys=('task_id','scope','action_id','action_class','sender_department','target_department','source_project_id','target_project_id',
       'target_thread_id','target_thread_title','target_cwd','target_sidebar_section_id','payload','payload_sha256','assignment_record_required')
 require(set(action)==set(original)|{'schema','goal_contract','hq_coordination_source'}
  and all(action.get(k)==original.get(k)for k in keys)
  and action.get('authorization_changes')==original.get('authorization_changes',[])
  and action.get('internal_repairs')==original.get('internal_repairs',[])
  and failed.get('status')=='blocked'and failed.get('message_sent')is False
  and failed.get('authorization_precheck',{}).get('reasons')==['new_department']
  and failed['authorization_precheck'].get('needs_human_confirmation')is False
  and failed['authorization_precheck'].get('decision_owner')=='operations'
  and not original.get('authorization_changes')and not original.get('internal_repairs'),
  'only the exact original ordinary coordination refusal may be recovered')
 payload=action['payload'];require(w.file_digest(root,payload['path'])==payload
  and payload['sha256']==action['payload_sha256'],'unchanged original readonly payload required')
 body=(Path(root)/payload['path']).read_text()
 require(all(re.search(r'(?m)^'+k+'='+re.escape(str(action[k]))+r'\s*$',body)for k in ('task_id','scope','action_id','sender_department','target_department')),
  'original readonly payload identity required')
 fixed=registry[target]['chat_binding'];owner=registry[sender]['chat_binding'];hq=registry['operations']['chat_binding']
 require(all(action.get(k)==fixed[v]for k,v in {'target_thread_id':'task_id','target_thread_title':'title','target_cwd':'cwd','target_sidebar_section_id':'sidebar_section_id'}.items())
  and all(b.get('project_id')==PROJECT and b.get('cwd')==str(Path(root).resolve())for b in (fixed,owner,hq))
  and action.get('source_project_id')==action.get('target_project_id')==PROJECT,
  'exact current fixed professional parties and original project required')
 notice=document(root,source.get('notice_request'));prepared=document(root,source.get('notice_prepared'))
 from goal_source_recovery import _strict_queue_document
 intent=_strict_queue_document(root,source.get('queue_intent'));result=_strict_queue_document(root,source.get('queue_result'))
 policy=prepared.get('policy_decision',{});notice_payload=notice.get('payload',{})
 require(notice.get('sender_department')=='operations'and notice.get('target_department')==sender
  and notice.get('target_thread_id')==owner['task_id']and notice.get('target_cwd')==str(Path(root).resolve())
  and notice.get('source_project_id')==notice.get('target_project_id')==PROJECT
  and notice.get('task_id')==snapshot['task_id']and notice.get('scope')==action['scope']
  and notice.get('action_class')=='thread_message'and notice.get('assignment_record_required')is False
  and prepared.get('status')=='ready_to_queue'and policy.get('status')=='allow'
  and policy.get('department')=='operations'and policy.get('approval_basis')==MODE
  and policy.get('external_permission_issued')is False
  and all(policy.get(k)==notice.get(k)for k in ('task_id','scope','action_id','action_class','target_department','target_thread_id','payload_sha256'))
  and len([p for p in w.read_jsonl(Path(root)/w.POLICY_DECISIONS)if p==policy])==1,
  'actual normal HQ-to-original-owner policy and prepared source required')
 require(w.file_digest(root,notice_payload.get('path',''))==notice_payload
  and notice_payload['sha256']==notice.get('payload_sha256'),'unchanged actual HQ notice required')
 notice_body=(Path(root)/notice_payload['path']).read_text()
 require(decision_pin['path']in notice_body and decision_pin['sha256']in notice_body
  and all(re.search(r'(?m)^'+k+'='+re.escape(str(action[k]))+r'\s*$',notice_body)for k in ('task_id','scope')),
  'real HQ notice must bind full exact decision hash and original task context')
 turn,call,output=native_execution(root,source.get('native'),source.get('command_id'),'operations')
 match=re.fullmatch(r'Queued message ([0-9a-f-]{36}) for thread ([0-9a-f-]{36})\.\s*',result.get('stdout',''))
 require(turn.get('status')=='completed'and not turn.get('error')and match and match[2]==owner['task_id']
  and result.get('exit_code')==0 and result.get('thread_id')==intent.get('thread_id')==owner['task_id']
  and all(intent.get(k)==result.get(k)==v for k,v in {'payload_sha256':notice_payload['sha256'],'policy_decision_id':policy['decision_id'],'transport':'official_codex_queue'}.items())
  and match[1].encode()in output,'real completed successful official HQ notice transport required')
 at=w._parse_observed_at(decision.get('decided_at'));start=w._parse_observed_at(intent.get('started_at'));end=w._parse_observed_at(result.get('finished_at'))
 require(at and start and end and type(turn.get('startedAt'))in {int,float}and type(turn.get('completedAt'))in {int,float}
  and at<=start<=end and turn['startedAt']<=start.timestamp()<=end.timestamp()<=turn['completedAt']
  and end<=dt.datetime.now(dt.timezone.utc),'real original HQ decision/send chronology required')
 # Parse only literal source bytes. Never execute any native command or caller expression.
 try:
  shell=shlex.split(call['command'])[-1];script=shell.split("<<'PY'\n",1)[1].rsplit('\nPY',1)[0]
  literals=[n.value for n in ast.walk(ast.parse(script))if isinstance(n,ast.Constant)and isinstance(n.value,str)]
 except (ValueError,IndexError,SyntaxError)as error:raise w.WorkflowError('actual literal original HQ notice command required')from error
 require(literals.count(notice_body)==1 and 'OfficialQueueTransport' in call['command']and '.enqueue('in call['command']
  and Path(source['notice_request']['path']).name in call['command']
  and Path(source['notice_prepared']['path']).name in call['command'],
  'successful native call must contain this exact immutable HQ notice and normal transport inputs')
 return {**authority(root),'source':payload,'report':payload,'scope':action['scope'],
  'sender_department':sender,'target_department':target,'purpose':'exact_HQ_decided_readonly_coordination',
  'business_producer_added':False,'current_assignment_changed':False,'external_permission_issued':False}


def owner_result_message_source(root,snapshot,item):
 """An authenticated owner's exact ordinary collaboration, never a permit.

 A caller label is insufficient: the complete real native result must bind the
 unchanged action file and its payload. External actions retain their own gates.
 """
 import re
 goal=participant(root,snapshot,snapshot['goal_delivery']['primary_owner'])
 frozen=document(root,snapshot['goal_contract']);owner=goal['primary_owner']
 require(current_mode(root)and item.get('schema')=='professional-owner-result-message-source/v1'
  and item.get('task_id')==snapshot['task_id']and item.get('goal_contract')==snapshot['goal_contract']
  and item.get('authorization')==goal['authorization_pin']
  and all(goal.get(k)==frozen.get(k)for k in ('primary_owner','producer_departments','authorized_scope','human_authorization')),
  'unchanged original professional message contract and authority required')
 action=document(root,item.get('original_action'));source=document(root,item.get('professional_result_request'))
 native_result(root,source,w.department_registry(root)[owner]['chat_binding']['task_id'])
 report=document(root,w.file_digest(root,source['outbox_path']))
 require(source.get('task_id')==snapshot['task_id']and source.get('sender_department')==owner
  and report.get('primary_owner')==report.get('department')==owner
  and report.get('scope')==item.get('scope')in goal['authorized_scope']
  and item['original_action']in report.get('evidence',[])and report.get('delivery_model')==MODE,
  'actual complete original owner result must bind this exact action source')
 target=action.get('target_department');registry=w.department_registry(root)
 require(action.get('task_id')==snapshot['task_id']and action.get('scope')==item['scope']
  and action.get('sender_department')==owner and target!=owner and professional(root,target)
  and action.get('action_class')=='thread_message'and action.get('assignment_record_required')is False
  and action.get('action_id')and not action.get('authorization_changes')and not action.get('internal_repairs')
  and not any(action.get(k)for k in ('approval_id','consume_approval','execution_request','goal_responsibility_dispatch','parent_task_id')),
  'ordinary same-goal professional message only; no new responsibility, execution or authority')
 payload=action.get('payload');require(w.file_digest(root,payload.get('path',''))==payload
  and payload['sha256']==action.get('payload_sha256'),'unchanged original professional message bytes required')
 text=(Path(root)/payload['path']).read_text()
 require(all(re.search(r'(?m)^'+k+'='+re.escape(str(action[k]))+r'\s*$',text)for k in ('task_id','scope','action_id','sender_department','target_department')),
  'exact source payload task/scope/participants required')
 dest=registry[target]['chat_binding'];sender=registry[owner]['chat_binding']
 require(dest.get('project_id')==sender.get('project_id')==action.get('source_project_id')==action.get('target_project_id')==PROJECT
  and Path(dest.get('cwd','')).resolve()==Path(root).resolve()==Path(sender.get('cwd','')).resolve()
  and all(action.get(k)==dest[v]for k,v in {'target_thread_id':'task_id','target_thread_title':'title','target_cwd':'cwd','target_sidebar_section_id':'sidebar_section_id'}.items()),
  'exact current professional role/project/directory/message target required')
 return action,{'mode':MODE,'source':payload,'report':w.file_digest(root,source['outbox_path']),
  'scope':item['scope'],'sender_department':owner,'target_department':target,
  'purpose':'original_professional_collaboration_transport_only','external_permission_issued':False,
  'business_producer_added':False,'current_assignment_changed':False}


def record_owner_result_message(root,task,input_path):
 import goal_delivery_runtime as g
 pin=w.file_digest(root,input_path);item=document(root,pin)
 with w.workflow_lock(root):
  snapshot=g.restore_goal(root,w.read_json(w.snapshot_path(root,task)))
  require(task==item.get('task_id'),'exact original message registration task required')
  action,route=owner_result_message_source(root,snapshot,item)
  prepared={**action,'professional_owner_message_source':pin}
  previous=[a for a in snapshot['goal_delivery'].get('approved_actions',[])if a.get('action_id')==action['action_id']]
  if previous:
   require(previous==[prepared],'original message action already frozen to different bytes')
   return {'result':'duplicate_ignored','actual_message_sent':False,'external_permission_issued':False}
  snapshot['goal_delivery']={**snapshot['goal_delivery'],'approved_actions':snapshot['goal_delivery'].get('approved_actions',[])+[prepared]}
  w.append_workflow_event(root,task,snapshot['current_state'],{'goal_delivery':snapshot['goal_delivery'],
   'professional_owner_message_source':pin,'approved_message_prepared':item['original_action'],'actual_message_sent':False,'external_permission_issued':False})
  w.atomic_write_json(w.snapshot_path(root,task),snapshot)
 return {'result':'recorded','actual_message_sent':False,'external_permission_issued':False,'route':route}


def _registered_owner_result_message(root,snapshot,request):
 keys=('task_id','scope','action_id','action_class','sender_department','target_department','payload','payload_sha256')
 rows=[a for a in snapshot.get('goal_delivery',{}).get('approved_actions',[])if a.get('professional_owner_message_source')
  and all(a.get(k)==request.get(k)for k in keys)]
 if not rows:return None
 require(len(rows)==1,'one original registered professional message required')
 action=rows[0];pin=action['professional_owner_message_source'];original,route=owner_result_message_source(root,snapshot,document(root,pin))
 require(action=={**original,'professional_owner_message_source':pin}
  and all(request.get(k)==v for k,v in original.items()),'unchanged registered message and exact transport inputs required')
 events=[e for e in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS)if e.get('task_id')==snapshot['task_id']
  and e.get('details',{}).get('professional_owner_message_source')==pin]
 require(len(events)==1,'one real normal professional coordination registration required')
 return route


def _registered_professional_readonly_route(root,snapshot,request):
 actions=[a for a in snapshot.get('goal_delivery',{}).get('approved_actions',[])
  if a.get('schema')=='current-autonomous-readonly-coordination-action/v1'
  and a.get('hq_coordination_source',{}).get('decision')
  and all(a.get(k)==request.get(k)for k in ('task_id','scope','action_id','action_class','sender_department','target_department','payload','payload_sha256'))]
 if not actions:return None
 require(len(actions)==1,'one exact registered professional readonly coordination required')
 action=actions[0];route=_professional_readonly_coordination(root,snapshot,action)
 events=[e for e in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS)if e.get('task_id')==snapshot['task_id']
  and e.get('details',{}).get('action_id')==action['action_id']
  and e.get('details',{}).get('actual_HQ_coordination_source')==action['hq_coordination_source']['native']
  and e.get('details',{}).get('approved_message_prepared')]
 require(len(events)==1 and document(root,events[0]['details']['approved_message_prepared'])==action,
  'one real normal readonly registration event with exact source required')
 return route


def validate_readonly_coordination(root, snapshot, action):
 if action.get('hq_coordination_source',{}).get('decision'):
  return _professional_readonly_coordination(root,snapshot,action)
 import re
 from goal_delivery_runtime import _collaboration_native
 require(current_mode(root)and action.get('schema')=='current-autonomous-readonly-coordination-action/v1',
  'actual current autonomous readonly coordination required')
 payload=action.get('payload');packet=document(root,payload)
 route=_runtime_health_packet(root,snapshot,action,packet,payload)
 require(action.get('goal_contract')==snapshot.get('goal_contract'),'unchanged original coordination contract required')
 source=action.get('hq_coordination_source',{});page=_collaboration_native(root,source.get('native'))
 registry=w.department_registry(root);hq=registry['operations']['chat_binding'];owner=registry[snapshot['goal_delivery']['primary_owner']]['chat_binding']
 require(all(page.get('thread',{}).get(k)==hq[v]for k,v in {'id':'task_id','title':'title','cwd':'cwd'}.items())
  and hq.get('project_id')==PROJECT,'actual current same-project HQ decision source required')
 selected=[]
 for turn in page.get('turns',[]):
  items=turn.get('items',[])
  anchors=[(i,m)for i,m in enumerate(items)if m.get('id')==source.get('anchor_call_id')]
  decisions=[(i,m)for i,m in enumerate(items)if m.get('id')==source.get('decision_call_id')]
  if len(anchors)==len(decisions)==1:selected.append((turn,anchors[0],decisions[0]))
 require(len(selected)==1,'one ordered real HQ original-task/decision pair required')
 turn,(before,anchor),(after,decision)=selected[0]
 require(before<after and not turn.get('error')and type(turn.get('startedAt'))in {int,float}
  and turn['startedAt']<=dt.datetime.now(dt.timezone.utc).timestamp()
  and all(c.get('type')=='mcpToolCall'and c.get('server')=='codex_app'
   and c.get('tool')=='send_message_to_thread'and c.get('status')=='completed'and not c.get('error')
   and c.get('arguments',{}).get('threadId')==owner['task_id']for c in (anchor,decision)),
  'actual successful HQ ordinary coordination calls to original owner required')
 original=anchor.get('arguments',{}).get('prompt','');body=decision.get('arguments',{}).get('prompt','')
 require(all(re.search(r'(?m)^'+k+'='+re.escape(str(action[k]))+r'\s*$',original)for k in ('task_id','scope'))
  and action['target_thread_id']in body and action['target_department']in body
  and Path(payload['path']).name in body,'HQ decision must bind exact original task context, frozen payload and target')
 human=_collaboration_native(root,source.get('owner_continuation'))
 require(human.get('thread',{}).get('id')==hq['task_id'],'actual original owner continuation source required')
 humans=[m for t in human.get('turns',[])if t.get('id')==turn['id']for m in t.get('items',[])if m.get('type')=='userMessage']
 require(len(humans)==1 and humans[0]in turn.get('items',[])and humans[0].get('content'),
  'unchanged actual human continuation in original HQ decision turn required')
 failed_request=document(root,source.get('original_prepare_request'));failed=document(root,source.get('original_prepare_result'))
 keys=('task_id','scope','action_id','action_class','sender_department','target_department','target_thread_id','payload','payload_sha256')
 require(all(failed_request.get(k)==action.get(k)for k in keys)
  and failed.get('status')=='blocked'and failed.get('authorization_precheck',{}).get('reasons')==['new_department']
  and failed['authorization_precheck'].get('next_owner')=='operations'
  and failed['authorization_precheck'].get('needs_human_confirmation')is False,
  'exact original readonly request and real HQ-coordination refusal required; sensitive/source errors cannot be overridden')
 return route


def record_readonly_coordination(root, task, input_path):
 from goal_delivery_runtime import restore_goal
 pin=w.file_digest(root,input_path);action=document(root,pin)
 require(action.get('task_id')==task,'original coordination task required')
 with w.workflow_lock(root):
  snapshot=restore_goal(root,w.read_json(w.snapshot_path(root,task)))
  validate_readonly_coordination(root,snapshot,action)
  goal=snapshot['goal_delivery'];previous=[x for x in goal.get('approved_actions',[])if x.get('action_id')==action['action_id']]
  if previous:
   require(len(previous)==1 and previous[0]==action,'original coordination action identity already differs')
   return {'result':'duplicate_ignored','task_id':task,'action_id':action['action_id'],'actual_message_sent':False}
  snapshot['goal_delivery']={**goal,'approved_actions':goal.get('approved_actions',[])+[action]}
  w.atomic_write_json(w.snapshot_path(root,task),snapshot)
  w.append_workflow_event(root,task,snapshot['current_state'],{'goal_delivery':snapshot['goal_delivery'],'action_id':action['action_id'],
   'approved_message_prepared':pin,'actual_HQ_coordination_source':action['hq_coordination_source']['native'],
   'actual_message_sent':False,'new_business_producer_added':False})
 return {'result':'recorded','task_id':task,'action_id':action['action_id'],'input':pin,
  'actual_message_sent':False,'external_permission_issued':False}


def runtime_health_route(root,snapshot,request,packet,payload):
 expected=[x for x in snapshot.get('goal_delivery',{}).get('approved_actions',[])
  if x.get('schema')=='current-autonomous-readonly-coordination-action/v1'
  and all(x.get(k)==request.get(k)for k in ('task_id','scope','action_id','sender_department','target_department','target_thread_id','payload','payload_sha256'))]
 require(len(expected)==1,'normal actual HQ authorized appended readonly action required')
 action=expected[0];route=validate_readonly_coordination(root,snapshot,action)
 events=[x for x in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS)if x.get('task_id')==request.get('task_id')
  and x.get('details',{}).get('action_id')==request.get('action_id')
  and isinstance(x.get('details',{}).get('goal_delivery'),dict)
  and x.get('details',{}).get('actual_HQ_coordination_source')==action['hq_coordination_source']['native']]
 require(len(events)==1 and document(root,events[0]['details']['approved_message_prepared'])==action,
  'one genuine normal appended action event and unchanged input required')
 require(packet==document(root,action['payload']),'same registered readonly packet required')
 return route


def _hq_readonly_result_return(root,snapshot,request):
 """A real HQ invitation and completed peer return do not add a producer."""
 import re
 import goal_delivery_runtime as g
 proof=request.get('hq_readonly_result_return')
 if proof is None:return None
 authority(root);goal=snapshot.get('goal_delivery',{});frozen=document(root,snapshot['goal_contract'])
 owner=goal.get('primary_owner');sender=request.get('sender_department');registry=w.department_registry(root)
 require(current_mode(root)and snapshot.get('current_state')not in w.TERMINAL_STATES
  and all(goal.get(k)==frozen.get(k)for k in ('primary_owner','producer_departments','authorized_scope','human_authorization'))
  and professional(root,sender)and sender!=owner and request.get('target_department')==owner
  and request.get('task_id')==snapshot['task_id']and request.get('scope')in frozen['authorized_scope']
  and request.get('action_class')=='thread_message'and request.get('assignment_record_required')is False
  and not request.get('authorization_changes')and not any(request.get(k)for k in ('execution_request','approval_id','consume_approval')),
  'same original open task readonly peer return only; no participant or execution grant')
 hq=registry['operations']['chat_binding'];peer=registry[sender]['chat_binding'];dest=registry[owner]['chat_binding']
 source=g._native_document(root,proof.get('invitation_native'))
 require(all(source.get('thread',{}).get(k)==hq[v]for k,v in {'id':'task_id','title':'title','cwd':'cwd'}.items()),'real original fixed HQ collaboration caller required')
 pairs=[(t,m)for t in source.get('turns',[])for m in t.get('items',[])if m.get('id')==proof.get('invitation_call_id')]
 require(len(pairs)==1,'one real HQ collaboration invocation required');original,call=pairs[0];body=call.get('arguments',{}).get('prompt','')
 require(not original.get('error')and call.get('type')=='mcpToolCall'and call.get('server')=='codex_app'
  and call.get('tool')=='send_message_to_thread'and call.get('status')=='completed'and not call.get('error')
  and call.get('truncated',False)is False and call.get('arguments',{}).get('threadId')==peer['task_id']
  and all(re.search(r'(?m)^'+k+'='+re.escape(v)+r'\s*$',body)for k,v in {'task_id':snapshot['task_id'],'scope':request['scope'],
   'sender_department':'operations','target_department':sender,'action_id':proof.get('invitation_action_id','')}.items()),
  'actual successful HQ invitation with unchanged task/scope/executor required')
 page=g._native_document(root,proof.get('completed_native'));turn,message=w._completion_actual_final(root,page,sender,
  turn_id=proof.get('source_turn_id'),message_id=proof.get('source_message_id'))
 require(all(page.get('thread',{}).get(k)==peer[v]for k,v in {'id':'task_id','title':'title','cwd':'cwd'}.items()),'actual fixed peer completion identity required')
 expected='<codex_delegation>\n  <source_thread_id>'+hq['task_id']+'</source_thread_id>\n  <input>'+body+'</input>\n</codex_delegation>'
 users=[i for i,m in enumerate(turn.get('items',[]))if (m.get('type')=='userMessage'and m.get('content')==[{'type':'text','text':body}])
  or(m.get('type')=='functionCallOutput'and m.get('namespace')=='codex_app'and m.get('name')=='send_message_to_thread'
   and m.get('output')=={'text':expected,'truncated':False})]
 items=turn.get('items',[]);end=items.index(message)
 require(len(users)==1 and users[0]<end and any(m.get('type')=='agentMessage'and m.get('text','').strip()for m in items[users[0]+1:end])
  and type(original.get('startedAt'))in {int,float}and original['startedAt']<=turn['startedAt']<=turn['completedAt']<=dt.datetime.now(dt.timezone.utc).timestamp(),
  'exact delivered invitation, nonempty ACK and real completed peer result required')
 pin=proof.get('report');report=document(root,pin)
 require(pin['path']in message['text']and pin['sha256']in message['text']
  and all(report.get(k)==v for k,v in {'task_id':snapshot['task_id'],'scope':request['scope'],'primary_owner':owner,
   'actual_executor':sender,'received_action_id':proof['invitation_action_id']}.items()),'exact native completed report and original owner required')
 payload=request.get('payload');require(w.file_digest(root,payload.get('path',''))==payload and payload['sha256']==request.get('payload_sha256'),'exact peer return payload bytes required')
 text=(Path(root)/payload['path']).read_text()
 require(pin['path']in text and pin['sha256']in text and all(re.search(r'(?m)^'+k+'='+re.escape(str(request[k]))+r'\s*$',text)
  for k in ('task_id','scope','action_id','sender_department','target_department')),'unchanged peer return task/scope/report required')
 require(peer.get('project_id')==dest.get('project_id')==hq.get('project_id')==request.get('source_project_id')==request.get('target_project_id')==PROJECT
  and all(Path(b.get('cwd','')).resolve()==Path(root).resolve()for b in (peer,dest,hq))
  and all(request.get(k)==dest[v]for k,v in {'target_thread_id':'task_id','target_thread_title':'title','target_cwd':'cwd','target_sidebar_section_id':'sidebar_section_id'}.items()),
  'original professional receiver and exact current project/directory/target required')
 return {**authority(root),'source':payload,'report':pin,'scope':request['scope'],'sender_department':sender,'target_department':owner,
  'readonly_collaboration_return':True,'actual_owner_knowledge_proven':False,'formal_result_received_proven':False,
  'business_producer_added':False,'external_permission_issued':False}


def readonly_result_return_route(root,snapshot,request):
 peer=_hq_readonly_result_return(root,snapshot,request)
 if peer is not None:return peer
 """Authenticate a return of the original readonly collaboration, never a producer."""
 source=request.get('readonly_result_return')
 if source is None:return None
 import re
 import goal_delivery_runtime as g
 require(isinstance(source,dict)and current_mode(root)and autonomous_goal(snapshot.get('goal_delivery'))
  and snapshot.get('current_state')not in w.TERMINAL_STATES and request.get('action_class')=='thread_message'
  and request.get('assignment_record_required')is False and not request.get('authorization_changes')
  and not any(request.get(k)for k in ('execution_request','approval_id','consume_approval')),
  'only an original open readonly collaboration result may return; no execution or delegated authority')
 goal=snapshot['goal_delivery'];owner=goal['primary_owner'];sender=request.get('sender_department')
 require(sender!=owner and professional(root,sender)and request.get('target_department')==owner
  and request.get('task_id')==snapshot['task_id']and request.get('scope')in goal['authorized_scope'],
  'exact original professional collaborator, owner and task/scope required')
 actions=[a for a in goal.get('approved_actions',[])if a.get('action_id')==source.get('original_action_id')
  and a.get('sender_department')==owner and a.get('target_department')==sender and a.get('scope')==request['scope']]
 require(len(actions)==1,'one actual registered original readonly invitation required');action=actions[0]
 require(_registered_professional_readonly_route(root,snapshot,action)is not None,'normal original readonly source registration required')
 registry=w.department_registry(root);fixed=registry[sender]['chat_binding'];dest=registry[owner]['chat_binding']
 require(all(b.get('project_id')==PROJECT and Path(b.get('cwd','')).resolve()==Path(root).resolve()for b in (fixed,dest))
  and request.get('source_project_id')==request.get('target_project_id')==PROJECT
  and all(request.get(k)==dest.get(v)for k,v in {'target_thread_id':'task_id','target_thread_title':'title','target_cwd':'cwd','target_sidebar_section_id':'sidebar_section_id'}.items()),
  'same original project and frozen original result receiver required')
 old=document(root,source.get('original_prepare_request'));prepared=document(root,source.get('original_prepare_result'))
 keys=('task_id','scope','action_id','action_class','sender_department','target_department','payload','payload_sha256','target_thread_id')
 require(all(old.get(k)==action.get(k)for k in keys)and old.get('delivery_mode')=='official_native_queue'
  and prepared.get('status')=='ready_to_queue'and prepared.get('payload')==action['payload'],'exact original prepared readonly request required')
 policy=prepared.get('policy_decision',{});actual=[p for p in w.read_jsonl(Path(root)/w.POLICY_DECISIONS)if p.get('decision_id')==policy.get('decision_id')]
 require(len(actual)==1 and actual[0]==policy and policy.get('status')=='allow'
  and all(policy.get(k)==old.get(k)for k in keys if k not in {'payload','sender_department'})and policy.get('department')==owner
  and policy.get('external_permission_issued')is False,'real original normal readonly policy, not caller metadata')
 from goal_source_recovery import _strict_queue_document
 intent=_strict_queue_document(root,source.get('queue_intent'));effect=_strict_queue_document(root,source.get('queue_result'))
 match=re.fullmatch(r'Queued message ([0-9a-f-]{36}) for thread ([0-9a-f-]{36})\.\s*',effect.get('stdout',''))
 require(effect.get('exit_code')==0 and match and match[2]==fixed['task_id']
  and all(intent.get(k)==effect.get(k)==v for k,v in {'thread_id':fixed['task_id'],'payload_sha256':action['payload_sha256'],'policy_decision_id':policy['decision_id'],'transport':'official_codex_queue'}.items()),
  'one actual original successful readonly queue effect required')
 invocation=g._native_document(root,source.get('actual_queue_invocation'))
 require(all(invocation.get('thread',{}).get(k)==dest[v]for k,v in {'id':'task_id','title':'title','cwd':'cwd'}.items()),'real original owner queue caller required')
 if set(invocation)=={'thread','turn','actual_command'}:
  turn,command=invocation['turn'],invocation['actual_command']
 else:
  pairs=[(t,m)for t in invocation.get('turns',[])for m in t.get('items',[])if m.get('id')==source.get('queue_command_id')]
  require(len(pairs)==1,'one original readonly queue command required');turn,command=pairs[0]
 require(not turn.get('error')and command.get('id')==source.get('queue_command_id')and command.get('type')=='commandExecution'
  and command.get('status')=='completed'and command.get('exitCode')==0 and Path(command.get('cwd','')).resolve()==Path(root).resolve(),
  'successful actual same-project readonly queue invocation required')
 output=json.loads(w._source_continuation_execution_output(command))
 require(output.get('state')=='accepted'and output.get('message_id')==match[1]and output.get('target_thread_id')==fixed['task_id']
  and output.get('payload_sha256')==action['payload_sha256']and output.get('policy')==policy['decision_id'],
  'actual original command output must bind the same queue/policy/payload; never execute supplied commands')
 page=g._native_document(root,source.get('actual_completed_result'))
 require(all(page.get('thread',{}).get(k)==fixed[v]for k,v in {'id':'task_id','title':'title','cwd':'cwd'}.items()),'actual original readonly executor source required')
 turns=[t for t in page.get('turns',[])if t.get('id')==source.get('source_turn_id')]
 require(len(turns)==1 and turns[0].get('status')=='completed'and not turns[0].get('error'),'actual successfully completed collaborator turn required')
 turn=turns[0];items=turn.get('items',[]);body=(Path(root)/action['payload']['path']).read_text()
 users=[(i,m)for i,m in enumerate(items)if m.get('type')=='userMessage'and m.get('content')==[{'type':'text','text':body}]]
 finals=[(i,m)for i,m in enumerate(items)if m.get('id')==source.get('source_message_id')and m.get('type')=='agentMessage'and m.get('phase')=='final_answer']
 at=w._parse_observed_at(effect.get('finished_at'))
 require(len(users)==len(finals)==1 and users[0][0]<finals[0][0]and any(m.get('type')=='agentMessage'and m.get('text','').strip()for m in items[users[0][0]+1:finals[0][0]])
  and at is not None and type(turn.get('startedAt'))in {int,float}and type(turn.get('completedAt'))in {int,float}
  and at.timestamp()<=turn['startedAt']<=turn['completedAt']<=dt.datetime.now(dt.timezone.utc).timestamp(),
  'actual exact invitation, nonempty ACK and ordered completed readonly result required')
 pin=source.get('result');report=document(root,pin);payload=request.get('payload');require(w.file_digest(root,payload.get('path',''))==payload
  and payload['sha256']==request.get('payload_sha256'),'exact return payload bytes required')
 returned=(Path(root)/payload['path']).read_text()
 require(all(re.search(r'(?m)^'+k+'='+re.escape(str(request[k]))+r'\s*$',returned)for k in ('task_id','scope','action_id','sender_department','target_department'))
  and pin['path']in finals[0][1]['text']and pin['path']in returned and pin['sha256']in returned
  and all(report.get(k)==v for k,v in {'task_id':snapshot['task_id'],'scope':request['scope'],'primary_owner':owner,'actual_executor':sender,'received_action_id':action['action_id']}.items())
  and not any(report.get(k)for k in ('new_CMS_Save','new_preview','new_permit','new_policy_consumption','new_account_or_fee_or_deploy','business_parent_closed')),
  'native readonly result and its exact return hash/task/scope/action required; no production effects')
 knowledge=source.get('owner_knowledge');known=False
 if knowledge is not None:
  native=g._native_document(root,knowledge.get('native'))
  require(all(native.get('thread',{}).get(k)==dest[v]for k,v in {'id':'task_id','title':'title','cwd':'cwd'}.items()),'real original result owner knowledge source required')
  pairs=[(t,m)for t in native.get('turns',[])for m in t.get('items',[])if m.get('id')==knowledge.get('message_id')]
  require(len(pairs)==1 and not pairs[0][0].get('error')and pairs[0][1].get('type')=='agentMessage'
   and pin['sha256']in pairs[0][1].get('text','')and type(pairs[0][0].get('startedAt'))in {int,float}
   and turn['completedAt']<=pairs[0][0]['startedAt']<=dt.datetime.now(dt.timezone.utc).timestamp(),'actual owner read of this exact source after completion required')
  known=True
 else:require(pin['sha256']in finals[0][1]['text'],'completed source must itself identify full result SHA when no actual owner knowledge exists')
 return {**authority(root),'source':payload,'report':pin,'scope':request['scope'],'sender_department':sender,'target_department':owner,
  'readonly_collaboration_return':True,'original_action_id':action['action_id'],'original_queue_message_id':match[1],
  'actual_owner_knowledge_proven':known,'formal_result_received_proven':False,'business_producer_added':False,'external_permission_issued':False}


def message_route(root,snapshot,request):
 if not isinstance(request,dict)or request.get('action_class')!='thread_message':return None
 # External collaborators retain the original complete-goal path. It checks
 # the declared collaboration, exact approved payload, original authority and
 # fresh native identity; the internal autonomous lane grants none of these.
 if request.get('target_department')not in w.department_registry(root):return None
 payload=request.get('payload')
 if not isinstance(payload,dict):return None
 require(w.file_digest(root,payload.get('path',''))==payload,'exact payload bytes required')
 ordinary=_registered_owner_result_message(root,snapshot,request)
 if ordinary is not None:return ordinary
 returned=readonly_result_return_route(root,snapshot,request)
 if returned is not None:return returned
 readonly=_registered_professional_readonly_route(root,snapshot,request)
 if readonly is not None:return readonly
 text=(Path(root)/payload['path']).read_text()
 try:obj=json.loads(text)
 except (ValueError,UnicodeError):obj=None
 if isinstance(obj,dict)and obj.get('schema')=='department-runtime-health-request/v1':
  return runtime_health_route(root,snapshot,request,obj,payload)
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
 # A fresh real final can repair a stale health cache before the normal gate.
 from flashcast_ops import refresh_department_health
 for key,role in (('actual_sender_state',request.get('sender_department')),('actual_target_state',request.get('target_department'))):
  if request.get(key):refresh_department_health(root,role,request[key],only_if_stale=True)
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
 if requested.get('action_class')=='ads_write':
  from professional_ads_execution import execution_context
  registered=execution_context(root,snapshot,requested)
  if registered is not None:return registered
 from professional_web_execution import applies as original_WEB,preflight as original_preflight
 if original_WEB(root,snapshot.get('task_id'),requested.get('action_class')):
  item,req,pin,ctx=original_preflight(root,snapshot['task_id'],requested['action_id'],requested['action_class'],requested['scope'],requested['department'])
  require(requested.get('payload_sha256')==item['request']['sha256'],'exact original external WEB request bytes')
  return {'action':{k:req[k]for k in ['task_id','department','action_id','action_class','scope']},'request':req,'pin':item['request'],'authorization':ctx['authorization'],'department':ctx['role']}
 if requested.get('action_class')=='cms_write':
  from professional_cms_execution import execution_context
  registered=execution_context(root,snapshot,requested)
  if registered is not None:return registered
 from tools.shop_office_web_execution import applies as web_applies, preflight as web_preflight, AUTH as web_auth
 if web_applies(snapshot.get("task_id"),requested.get("action_class")):
  item,req,_=web_preflight(root,requested.get("action_id"),requested.get("action_class"),requested.get("scope"),requested.get("department"))
  require(requested.get("payload_sha256")==item["request"]["sha256"],"exact external WEB request hash")
  return {"action":{k:req[k]for k in ["task_id","department","action_id","action_class","scope"]},"request":req,"pin":item["request"],"authorization":web_auth,"department":req["department"]}
 if snapshot.get('task_id')=='fc-20261025-shop-office-existing-six-and-five-implementation-release-v1'and requested.get('action_class')=='cms_write':
  from tools.shop_office_six_field_execution import action_authority as exact_cms_authority
  return exact_cms_authority(root,snapshot,requested)
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


def migrated_local_completion(root, snapshot):
 """Only open, pre-migration internal accepted-delivery standards change recorder.

 Frozen criteria/authority and actual effects remain mandatory. Production,
 typed adoptions, closed history and new autonomous contracts keep their readers.
 """
 goal=snapshot.get('goal_delivery',{})
 return bool(not autonomous_goal(goal)and effective_mode(root,snapshot)
  and professional(root,goal.get('primary_owner'))and goal.get('completion_kind')=='internal_delivery'
  and not goal.get('required_execution_actions')and goal.get('completion_requirements')
  and all(r.get('requirement_type')=='accepted_delivery'and r.get('subject',{}).get('producer_department')==goal.get('primary_owner')
   for r in goal['completion_requirements']))

def professional_local_public_continuation(root,snapshot,pin,base,row,box,anchors):
 """An authenticated public follow-on does not replace its completed local source.

 This checks the actual registered owner/code authority and original version
 proofs. Labels such as source_only or ordinary_progress never grant an exception.
 """
 import professional_web_execution as web
 role=snapshot['goal_delivery']['primary_owner'];task=snapshot['task_id'];goal=snapshot['goal_delivery'];frame=box.get('goal_delivery',{})
 fields={'objective','primary_owner','producer_departments','authorized_scope','frozen_original_completion_contract',
  'authorization_pin','current_additive_followon_decision','original_local_completion','dependencies','existing_results','code_executor'}
 require(set(frame)==fields and all(frame.get(k)==goal.get(k)for k in ('primary_owner','producer_departments','authorized_scope','authorization_pin'))
  and frame.get('frozen_original_completion_contract')==snapshot['goal_contract']
  and all(box.get(k)==v for k,v in {'task_id':task,'scope':base['scope'],'primary_owner':role,'sender_department':role,'department':role}.items())
  and row.get('scope')==base['scope']and row.get('target_department')=='operations',
  'public continuation retains the exact frozen local contract, owner/producers and scope')
 contexts=web.records(root,task)
 require(len(contexts)==1 and contexts[0].get('code_only_release')and contexts[0]['contract']==snapshot['goal_contract']
  and contexts[0]['owner']==role and contexts[0]['scope']==base['scope']
  and contexts[0]['decision']==frame['current_additive_followon_decision'],
  'actual independently authenticated owner-authorized public source, not a replacement local candidate')
 ctx=contexts[0];links=frame.get('existing_results')
 require(isinstance(links,list)and any(x in anchors for x in links), 'actual chronological link to original business result or preceding authenticated follow-on')
 events=[e for e in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS)if e.get('task_id')==task and e.get('details',{}).get('professional_completion_evidence')]
 expected={r['requirement_id']for r in requirement_rows(goal)};details=[e['details']['professional_completion_evidence']for e in events]
 observed=w._parse_observed_at(row.get('reply_observed_at'))
 require(len(events)==len(expected)and {d.get('requirement_id')for d in details}==expected and observed is not None
  and all(w._parse_observed_at(e.get('created_at'))is not None and w._parse_observed_at(e['created_at'])<=observed for e in events),
  'real complete local evidence set must precede the public transport')
 versions=[]
 for d in details:
  proof=document(root,d.get('proof'))
  require(d.get('recorder')==role and d.get('goal_contract')==snapshot['goal_contract']and d.get('mode_authorization')==OWNER
   and proof.get('exact_original_owner_result')==pin and proof.get('requirement_id')==d['requirement_id']
   and proof.get('task_id')==task and proof.get('scope')==base['scope']and proof.get('department')==role
   and proof.get('original_goal_contract')==snapshot['goal_contract']and proof.get('original_authority')==goal['authorization_pin'],
   'original local proof identity/criterion/authority remains unchanged')
  if proof.get('exact_version_input'):
   version=document(root,proof['exact_version_input']).get('candidate',{})
   require(version.get('task_id')==task and version.get('commit')==proof.get('actual_local_candidate')
    and version.get('file_sha256')==ctx['paths']and set(version.get('files',[]))==set(ctx['paths']),
    'original proven local Git version must be the registered public source bytes')
   versions.append(version)
 require(versions,'original local version proof required, no caller candidate equality')
 native_result(root,row,w.department_registry(root)[role]['chat_binding']['task_id'])
 # Only transport anchors advance. No completion event, candidate, QA or receipt
 # is manufactured or replaced here; the original effect reader continues below.
 return [row['outbox'],box['primary_deliverable']]

def professional_local_business_source(root,snapshot,pin):
 """Only authenticated completion archival can follow a still-current business source.

 Later unknown or substantive results still supersede it. No receipt is deleted,
 reordered, re-received or promoted to business authority by a caller label.
 """
 role=snapshot['goal_delivery']['primary_owner'];task=snapshot['task_id']
 queued=[r for r in w._result_handoff_rows(root,task)if r.get('event')=='notification_queued'and r.get('sender_department')==role]
 originals=[r for r in queued if r.get('outbox')==pin]
 require(len(originals)==1,'one exact original professional result source required')
 source=originals[0];base=document(root,pin);scope=base.get('scope');identity={
  'task_id':task,'sender_department':role,'candidate_version':base.get('candidate_version'),'result_sha256':pin['sha256']}
 later=queued[queued.index(source)+1:];anchors=[pin]
 for row in later:
  box=document(root,row.get('outbox'))
  if not(box.get('archive_only')is True and box.get('metadata_transport_only')is True):
   anchors.extend(professional_local_public_continuation(root,snapshot,pin,base,row,box,anchors));continue
  require(box.get('archive_only')is True and box.get('metadata_transport_only')is True,
   'latest exact original professional result and scope required; no superseded candidate')
  metadata={'candidate_version','reported_at_MYT','status','state','risk_level','current_execution_route','conclusion',
   'primary_deliverable','deliveries','evidence','professional_self_check','next_actions','risks','handoff','chat_reply','effects','recheck'}
  archival={'closed_scope_only','archive_only','metadata_transport_only','original_owner_result_identity',
   'original_owner_result_HQ_received_record_id','completion_kind'}
  require(set(box)==set(base)|archival and all(box[k]==base[k]for k in set(base)-metadata)
   and row.get('task_id')==task and row.get('scope')==scope and row.get('target_department')=='operations'
   and box.get('original_owner_result_identity')==identity and box.get('status')=='completed'
   and box.get('state')=='completed_scope'and box.get('closed_scope_only')is True
   and box.get('completion_kind')=='internal_delivery'and box.get('goal_delivery')==base.get('goal_delivery'),
   'archive must retain every original business field/contract/owner/scope; unknown archive or new content is not exempt')
  native_result(root,row,w.department_registry(root)[role]['chat_binding']['task_id'])
  events=[e for e in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS)if e.get('task_id')==task and e.get('details',{}).get('professional_completion_evidence')]
  expected={r['requirement_id']for r in requirement_rows(snapshot['goal_delivery'])};details=[e['details']['professional_completion_evidence']for e in events]
  evidence=box.get('evidence',[]);require(isinstance(evidence,list)and pin in evidence,'archive must embed the unchanged original business source pin')
  require(len(events)==len(expected)and {d.get('requirement_id')for d in details}==expected,
   'one real original completed proof per frozen criterion before archive required')
  received=box.get('original_owner_result_HQ_received_record_id');observed=w._parse_observed_at(row.get('reply_observed_at'))
  require(isinstance(received,str)and received and observed is not None and all(
   w._parse_observed_at(e.get('created_at'))is not None and w._parse_observed_at(e['created_at'])<=observed for e in events),
   'archive observation must follow every actual original completion event')
  for d in details:
   proof=document(root,d.get('proof'))
   require(d.get('recorder')==role and d.get('goal_contract')==snapshot['goal_contract']and d.get('mode_authorization')==OWNER
    and d['proof']in evidence and proof.get('exact_original_owner_result')==pin
    and proof.get('requirement_id')==d['requirement_id']and proof.get('task_id')==task and proof.get('scope')==scope
    and proof.get('department')==role and proof.get('original_goal_contract')==snapshot['goal_contract']
    and proof.get('original_authority')==snapshot['goal_delivery']['authorization_pin']and proof.get('HQ_actual_received_record')==received
    and ('exact_version_input'not in proof or proof['exact_version_input']in evidence),
    'archive cannot replace the original criterion, proof, receipt or business version pin')
  # The archive contains the actual hash-chained event readback and the prior
  # normal completed view. Compare them to live facts, without recursively
  # invoking this same effect reader through completion/status.
  documents=[document(root,p)for p in evidence if p.get('path','').endswith('.json')]
  audits=[x for x in documents if x.get('task_id')==task and x.get('scope')==scope and x.get('events')==events]
  statuses=[x for x in documents if x.get('task_id')==task and x.get('state')=='completed_scope'and isinstance(x.get('completion_obligations'),dict)]
  require(len(audits)==len(statuses)==1,'one exact original completion-event audit and normal completed status required')
  requirements=statuses[0]['completion_obligations'].get('requirements',[])
  require(statuses[0]['completion_obligations'].get('state')=='PROVEN'and statuses[0].get('business_goal_closed')is False
   and len(requirements)==len(expected)and {r.get('requirement_id')for r in requirements}==expected
   and all(r.get('state')=='PROVEN'and r.get('identity')==identity and r.get('scope')==scope
    and r.get('actual_received_record_id')==received and pin in r.get('evidence',[])
    and next(d['proof']for d in details if d['requirement_id']==r['requirement_id'])in r.get('evidence',[])for r in requirements),
   'pure archive must preserve the actual completed view of the same business result, not manufacture a replacement PASS')
  effects=box.get('effects',{})
  require(isinstance(effects,dict)and effects.get('new_professional_completion_evidence_events')==len(events)
   and all(type(v)is int and v==0 for k,v in effects.items()if k!='new_professional_completion_evidence_events'),
   'only original completion-registration effects may be reported by this archive; new business changes supersede old proof')
  anchors.extend([row['outbox'],box['primary_deliverable']])
 return source


def professional_local_effect(root,snapshot,requirement,proof_pin):
 """Reuse authentic owner selfchecks and committed original result, not old QA."""
 import result_coordination as rc
 import goal_delivery_runtime as g
 require(migrated_local_completion(root,snapshot),'open migrated internal accepted-delivery goal required')
 goal=snapshot['goal_delivery'];role=goal['primary_owner'];proof=document(root,proof_pin)
 require(all(proof.get(k)==v for k,v in {'task_id':snapshot['task_id'],'scope':requirement['scope'],
  'department':role,'requirement_id':requirement['requirement_id'],'original_goal_contract':snapshot['goal_contract'],
  'original_authority':goal.get('authorization_pin')}.items()),'exact original professional criterion/contract/authority required')
 pin=proof.get('exact_original_owner_result');box=document(root,pin)
 require(not any(proof.get(k)for k in ('public_business_parent_closed','new_production_permission_or_effect','authorization_changes','approval_id','execution_request')),
  'local completion cannot add a parent claim, permission or external execution')
 if 'actual_local_candidate'in proof:
  require(isinstance(proof['actual_local_candidate'],str)and len(proof['actual_local_candidate'])in {40,64} and all(c in '0123456789abcdef'for c in proof['actual_local_candidate'])
   and proof['actual_local_candidate']in json.dumps(box,ensure_ascii=False),'original complete local candidate must remain bound in native owner result')
 identity={'task_id':snapshot['task_id'],'sender_department':role,'candidate_version':box.get('candidate_version'),'result_sha256':pin['sha256']}
 source=professional_local_business_source(root,snapshot,pin)
 require(source.get('scope')==requirement['scope'],'exact original professional business scope required')
 require(_legacy_parent_owner_report(root,snapshot,identity,[source])=='operations','original frozen professional route required')
 require(not w.validate_workflow_events(root,snapshot['task_id'])and not w._validate_receipt_chain(root,snapshot['task_id'])[1],
  'intact original contract and receipt chains required')
 frozen=document(root,snapshot['goal_contract'])
 require(all(goal.get(k)==frozen.get(k)for k in ('objective','completion_criteria','completion_kind','completion_requirements','human_authorization','responsible_assistant'))
  and all(box.get('goal_delivery',{}).get(k)==frozen.get(k)for k in ('objective','completion_criteria','primary_owner','producer_departments','authorized_scope','human_authorization')),
  'all frozen local standards and source owner/scope must match; history is not rewritten')
 require(box.get('department')==box.get('sender_department')==box.get('primary_owner')==role
  and box.get('scope')==requirement['scope']and box.get('frozen_original_goal_contract')==snapshot['goal_contract']
  and box.get('batch_complete')is True and box.get('status')in {'partial','completed'}
  and not any(box.get(k)for k in ('business_parent_closed','production_write_allowed','external_permission_issued','approval_required','collaboration_return')),
  'complete original internal-scope owner report only; parent/production effects are separate')
 native=native_result(root,source,w.department_registry(root)[role]['chat_binding']['task_id'])
 received=rc._received_delivery(root,identity,{'target_department':'operations'})
 require(received and received.get('record_id')==proof.get('HQ_actual_received_record')and received.get('outbox')==pin,
  'original exact SQL/native committed HQ knowledge required, not a supplied receipt label')
 observed=w._parse_observed_at(proof.get('at_UTC'));intake=w._parse_observed_at(received.get('created_at'))
 require(observed is not None and intake is not None and intake<=observed<=dt.datetime.now(dt.timezone.utc),
  'actual original knowledge then professional completion observation required')
 check_pin=proof.get('professional_existing_selfcheck');check=document(root,check_pin)
 require(check_pin==box.get('professional_self_check')and check_pin in box.get('evidence',[])
  and check.get('task_id')==snapshot['task_id']and check.get('scope')==requirement['scope']
  and check.get('department',check.get('primary_owner'))==role
  and not any(str(check.get(k,'')).upper()in {'FAIL','FAILED','BLOCKED','MISSING','ERROR'}for k in ('status','result')),
  'unaltered native-bound professional selfcheck required; no new technical PASS is inferred')
 for item in box.get('evidence',[]):document(root,item)if item['path'].endswith('.json')else require(w.file_digest(root,item['path'])==item,'source evidence bytes changed')
 collaborations=g._collaboration_wait_states(root,snapshot)
 require(all(x.get('proof_state')=='PROVEN'and x.get('status')=='result_received'for x in collaborations),
  'every original collaboration must have real normal returned-result proof')
 for value in proof.values():
  if isinstance(value,dict)and {'path','sha256','size'}<=set(value):require(w.file_digest(root,value['path'])==value,'original completion evidence bytes changed')
 return {'state':'PROVEN','evidence':[proof_pin,pin,check_pin,*box.get('evidence',[])],
  'identity':identity,'source_turn_id':native['source_turn_id'],'source_fingerprint':w.sha256_value([snapshot['goal_contract'],pin,native,received['record_id']]),
  'scope':requirement['scope'],'actual_received_record_id':received['record_id'],'next_owner':role,
  'closed_scope_only':True,'business_goal_closed':False,'external_permission_issued':False,'assistant_approval_required':False}

def record_professional_local_completion(root,task,input_path,role,rid):
 import goal_delivery_runtime as g
 pin=w.file_digest(root,input_path)
 with w.workflow_lock(root):
  snapshot=g.restore_goal(root,w.read_json(w.snapshot_path(root,task)));goal=snapshot.get('goal_delivery',{})
  require(migrated_local_completion(root,snapshot)and role==goal.get('primary_owner'),'original professional records its own local completion only')
  requirements=requirement_rows(goal);matched=[r for r in requirements if r['requirement_id']==rid]
  require(len(matched)==1,'one unchanged local criterion required')
  effect=professional_local_effect(root,snapshot,matched[0],pin)
  prior=[e['details']['professional_completion_evidence']for e in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS)
   if e.get('task_id')==task and e.get('details',{}).get('professional_completion_evidence',{}).get('requirement_id')==rid]
  if prior:
   require(len(prior)==1 and prior[0].get('proof')==pin and prior[0].get('recorder')==role,'existing actual completion cannot be replaced')
   return {'result':'duplicate_ignored','proof':pin,'requirement_id':rid}
  w.append_workflow_event(root,task,snapshot['current_state'],{'professional_completion_evidence':{
   'requirement_id':rid,'recorder':role,'proof':pin,'goal_contract':snapshot['goal_contract'],'mode_authorization':OWNER}})
 return {'result':'recorded','proof':pin,'requirement_id':rid,'actual_effect':effect,'contract_rewritten':False,'business_goal_closed':False}

def professional_local_completion_view(root,snapshot):
 results=[];events=w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS)
 for requirement in requirement_rows(snapshot['goal_delivery']):
  rid=requirement['requirement_id'];matching=[e['details']['professional_completion_evidence']for e in events
   if e.get('task_id')==snapshot['task_id']and e.get('details',{}).get('professional_completion_evidence',{}).get('requirement_id')==rid]
  result={**requirement,'state':'MISSING','next_owner':requirement['producer_department']}
  if matching:
   try:
    require(len(matching)==1 and matching[0].get('recorder')==requirement['producer_department']
     and matching[0].get('goal_contract')==snapshot['goal_contract']and matching[0].get('mode_authorization')==OWNER,'one original professional completion registration required')
    result.update(professional_local_effect(root,snapshot,requirement,matching[0]['proof']))
   except (w.WorkflowError,ValueError,KeyError,OSError,TypeError)as error:result.update(state='BLOCKED',reason=str(error))
  results.append(result)
 missing=[x['requirement_id']for x in results if x['state']=='MISSING'];blocked=[x['requirement_id']for x in results if x['state']=='BLOCKED']
 return {'contract_state':'declared','completion_kind':'internal_delivery','state':'BLOCKED'if blocked else'MISSING'if missing else'PROVEN',
  'requirements':results,'missing':missing,'blockers':blocked,'business_goal_closed':False,'closed_scope_only':not missing and not blocked,'assistant_approval_required':False}


def historical_professional_workflow_reviewer(root, snapshot):
 """Frozen history identity only; never qualifies a new reviewer or verdict."""
 goal=snapshot.get('goal_delivery',{})
 if (autonomous_goal(goal)or not current_mode(root)or not goal
  or not snapshot.get('goal_contract')or not professional(root,goal.get('primary_owner'))):return None
 from qa_review_plan import _binding
 if _binding(root,snapshot)is not None:return None  # Existing bound history keeps its exact reviewer.
 frozen=document(root,snapshot.get('goal_contract'))
 reviewer=frozen.get('responsible_assistant')
 if reviewer not in ASSISTANTS or goal.get('responsible_assistant')!=reviewer:return None
 require(all(goal.get(k)==frozen.get(k)for k in ('primary_owner','producer_departments','authorized_scope','human_authorization')),
  'unchanged professional contract required for historical workflow reading')
 return reviewer


def original_professional_transport_receipt(root, snapshot, rows, receipt):
 """Only new authenticated transport on an open migrated legacy professional goal."""
 kind=receipt.get('receipt_type');goal=snapshot.get('goal_delivery',{})
 if kind not in {'dispatch_sent','chat_ack'}or autonomous_goal(goal)or not current_mode(root):return None
 role=receipt.get('department')
 if role in ASSISTANTS or role not in goal.get('producer_departments',[]):return None
 require(snapshot.get('current_state')not in w.TERMINAL_STATES,'closed original goal cannot append a continuation')
 frozen=document(root,snapshot.get('goal_contract'));participant(root,snapshot,role)
 require(all(goal.get(k)==frozen.get(k)for k in ('primary_owner','producer_departments','authorized_scope','human_authorization','parent_task_id')),
  'original professional transport cannot change frozen goal/owner/authority/scope')
 require(professional(root,role)and goal.get('primary_owner')not in ASSISTANTS
  and receipt.get('scope')in frozen['authorized_scope']and receipt.get('action_class')=='thread_message'
  and not receipt.get('approval_id')and not receipt.get('verdict')
  and receipt.get('action_id')and not receipt['action_id'].startswith('assign-goal-review:'),
  'only original professional ordinary transport; no new assistant, execution or verdict')
 fixed=w.department_registry(root)[role]['chat_binding']
 require(receipt.get('chat_task_id')==fixed['task_id']and fixed.get('project_id')==PROJECT
  and fixed.get('cwd')==str(Path(root).resolve()),'exact current original professional target required')
 _,bad=w._validate_receipt_chain(root,snapshot['task_id'])
 require(not bad and not w.validate_workflow_events(root,snapshot['task_id']),'intact original transport and workflow history required')
 original_assignment_ready(root,snapshot,role)
 if kind=='chat_ack':
  candidates=[r for r in rows if r.get('receipt_type')=='dispatch_sent'
   and all(r.get(k)==receipt.get(k)for k in ('department','chat_task_id','action_id','scope','action_class'))
   and r.get('autonomous_transport_continuation',{}).get('mode_authorization')==OWNER]
  require(len(candidates)==1,'one exact recorded professional continuation dispatch required before ACK')
  sent=candidates[0];validate_native_ack(root,snapshot,role,receipt.get('evidence',[]))
  ackpins=[p for p in receipt['evidence']if document(root,p).get('schema')=='department-native-ack/v1']
  proof=document(root,ackpins[0])
  import goal_delivery_runtime as g
  page=g._native_document(root,proof['actual_native'])
  turn=next(t for t in page['turns']if t['id']==proof['source_turn_id'])
  index=next(i for i,m in enumerate(turn['items'])if m.get('id')==proof['source_message_id'])
  original=sent['autonomous_transport_continuation'];body=(Path(root)/original['payload']['path']).read_text()
  users=[m for m in turn['items'][:index]if m.get('type')=='userMessage'and m.get('content')==[{'type':'text','text':body}]]
  at=w._parse_observed_at(original['queue_finished_at'])
  require(len(users)==1 and type(turn.get('startedAt'))in {int,float}and at
   and at.timestamp()<=turn['startedAt']<=dt.datetime.now(dt.timezone.utc).timestamp(),
   'real original queued payload followed by this nonempty professional ACK required')
  require(not any(r.get('receipt_type')=='chat_ack'and r.get('autonomous_transport_continuation',{}).get('dispatch_receipt_id')==sent['receipt_id']
   for r in rows),'actual continuation ACK already recorded; recover original key, never duplicate')
  return {'schema':'original-autonomous-professional-transport/v1','mode_authorization':OWNER,
   'goal_contract':snapshot['goal_contract'],'kind':'chat_ack','dispatch_receipt_id':sent['receipt_id'],
   'actual_ack':ackpins[0],'queue_message_id':original['queue_message_id'],'payload':original['payload'],
   'policy_decision_id':sent['policy_decision_id'],'transport_only':True,'external_permission_issued':False}
 policies=[p for p in w.read_jsonl(Path(root)/w.POLICY_DECISIONS)if p.get('decision_id')==receipt.get('policy_decision_id')]
 require(len(policies)==1,'one original normal transport policy required');policy=policies[0]
 expected={'status':'allow','task_id':snapshot['task_id'],'action_id':receipt['action_id'],
  'action_class':'thread_message','scope':receipt['scope'],'target_department':role,
  'target_thread_id':fixed['task_id'],'target_project_id':PROJECT,'target_cwd':str(Path(root).resolve()),
  'target_thread_title':fixed['title'],'target_sidebar_section_id':fixed['sidebar_section_id'],
  'source_project_id':PROJECT,'routing_status':'routing_allowed','approval_basis':MODE}
 require(all(policy.get(k)==v for k,v in expected.items())and policy.get('department')=='operations'
  and policy.get('external_permission_issued')is False,'actual original autonomous HQ policy/task/action/recipient required')
 evidence=receipt.get('evidence',[])
 payloads=[p for p in evidence if p.get('sha256')==policy.get('payload_sha256')]
 require(len(payloads)==1,'one exact original policy-bound payload required');payload=payloads[0]
 require(w.file_digest(root,payload['path'])==payload,'unchanged original transport bytes required')
 body=(Path(root)/payload['path']).read_text()
 import re
 require(all(re.search(r'(?m)^'+k+'='+re.escape(str(v))+r'\s*$',body)for k,v in [('task_id',snapshot['task_id']),('scope',receipt['scope'])]),
  'original task/scope text required; caller role labels grant no authority')
 from goal_source_recovery import _strict_queue_document
 documents=[(p,_strict_queue_document(root,p))for p in evidence if p['path'].endswith('.json')]
 prepared=[(p,x)for p,x in documents if x.get('status')=='ready_to_queue'and x.get('policy_decision')==policy]
 intents=[(p,x)for p,x in documents if x.get('transport')=='official_codex_queue'and 'exit_code'not in x]
 results=[(p,x)for p,x in documents if x.get('transport')=='official_codex_queue'and 'exit_code'in x]
 require(len(prepared)==len(intents)==len(results)==1,'one actual original prepare/queue intent/result chain required')
 prep_pin,prep=prepared[0];intent_pin,intent=intents[0];result_pin,result=results[0]
 require(Path(intent_pin['path']).name=='native-queue-intent.json'
  and Path(result_pin['path']).name=='native-queue-result.json'
  and Path(intent_pin['path']).parent==Path(result_pin['path']).parent
  and Path(result_pin['path']).parent.parent==Path(prep_pin['path']).parent==Path(payload['path']).parent,
  'original normal prepare/payload and canonical owned queue artifacts required; no substitute effect file')
 require(prep.get('payload')==payload and prep.get('delivery_mode')=='official_native_queue'
  and prep.get('message_sent')is False and prep.get('external_permission_issued')is False
  and all(prep.get('authorization_precheck',{}).get(k)==v for k,v in {'status':'within_original_authorization','task_id':snapshot['task_id'],
   'scope':receipt['scope'],'action_class':'thread_message','original_authorization':goal['authorization_pin'],
   'actual_action_allowed':False,'external_permission_issued':False}.items()),
  'original full-goal authority and normal exact queue preparation required')
 expected_queue={'thread_id':fixed['task_id'],'payload_sha256':payload['sha256'],'policy_decision_id':policy['decision_id'],
  'transport':'official_codex_queue','intake_claimed':False}
 match=re.fullmatch(r'Queued message ([0-9a-f-]{36}) for thread ([0-9a-f-]{36})\.\s*',result.get('stdout',''))
 require(all(intent.get(k)==v and result.get(k)==v for k,v in expected_queue.items())
  and type(result.get('exit_code'))is int and result['exit_code']==0 and result.get('stderr')==''
  and match and match[2]==fixed['task_id']and intent.get('started_at')==result.get('started_at'),
  'actual one successful original queue effect required; unknown effects are not dispatch')
 start=w._parse_observed_at(result.get('started_at'));finish=w._parse_observed_at(result.get('finished_at'));checked=w._parse_observed_at(policy.get('checked_at'))
 require(start and finish and checked and checked<=start<=finish<=dt.datetime.now(dt.timezone.utc),
  'actual original policy-before-queue chronology required; never backdate')
 require(not any(r.get('receipt_type')=='dispatch_sent'and r.get('policy_decision_id')==policy['decision_id']
  and r.get('action_id')==receipt['action_id']for r in rows),
  'original dispatch effect already recorded; recover its original key')
 return {'schema':'original-autonomous-professional-transport/v1','mode_authorization':OWNER,
  'goal_contract':snapshot['goal_contract'],'kind':'dispatch_sent','policy_decision_id':policy['decision_id'],
  'payload':payload,'normal_prepare':prep_pin,'queue_intent':intent_pin,'queue_result':result_pin,
  'queue_message_id':match[1],'queue_finished_at':result['finished_at'],'transport_only':True,'external_permission_issued':False}


def reconcile_professional_transport(root, task, receipt):
 """Only commit the existing receipt cursor; preserve frozen goal, QA and work state."""
 with w.workflow_lock(root):
  snapshot=w.read_json(w.snapshot_path(root,task));rows,bad=w._validate_receipt_chain(root,task)
  require(not bad and any(r.get('receipt_id')==receipt['receipt_id']for r in rows),'actual recorded transport chain required')
  require(receipt['autonomous_transport_continuation']['goal_contract']==snapshot.get('goal_contract'),
   'original transport contract changed before cursor readback')
  event=w.append_workflow_event(root,task,snapshot['current_state'],{
   'autonomous_professional_transport_recorded':{'receipt_id':receipt['receipt_id'],'receipt_type':receipt['receipt_type'],
    'mode_authorization':OWNER,'goal_contract':snapshot['goal_contract'],'business_stage_changed':False}})
  snapshot.update(last_receipt_hash=rows[-1]['receipt_hash'],receipt_count=len(rows),
   event_count=len([e for e in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS)if e.get('task_id')==task]),
   updated_at=w.utc_timestamp())
  w.atomic_write_json(w.snapshot_path(root,task),snapshot)
 return snapshot,[w.snapshot_path(root,task),Path(root)/w.WORKFLOW_EVENTS]


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

def scheduled_delivery_source(root,identity):
 """A declared autonomous daily report is transport, never a synthetic goal."""
 if w.snapshot_path(root,identity['task_id']).exists():return None
 source=w.scheduled_result_source(root,identity['task_id'],identity['sender_department'])
 if not source or source.get('delivery_model')!=MODE:return None
 require(current_mode(root)and source.get('result_receiver')=='operations'
  and professional(root,identity['sender_department']),'declared current professional daily source and HQ receiver required')
 for role in (identity['sender_department'],'operations'):
  binding=w.department_registry(root)[role]['chat_binding']
  require(binding.get('project_id')==PROJECT and Path(binding.get('cwd','')).resolve()==Path(root).resolve(),
   'same fixed daily professional/HQ project and directory required')
 return source

def native_result(root,request,fixed_id):
 import goal_delivery_runtime as g
 role=request['sender_department'];snapshot=g.restore_goal(root,w.read_json(w.snapshot_path(root,request['task_id'])))
 daily=scheduled_delivery_source(root,request)
 if daily is None:
  require(role in snapshot['goal_delivery']['producer_departments']and role not in ASSISTANTS,'actual original professional result required')
  original_assignment_ready(root,snapshot,role)
  if autonomous_goal(snapshot['goal_delivery'])and 'scope'in request:require(request['scope']in snapshot['goal_delivery']['authorized_scope'],'exact original result scope required')
 else:
  require(request.get('source_mode')=='scheduled_run'and request.get('source_automation_id')==daily['automation_id']
   and request.get('coordinator_role','operations')=='operations'and request.get('action_class')in {None,'thread_message'}
   and not any(request.get(k)for k in ('approval_id','consume_approval','execution_request','authorization_changes')),
   'exact declared daily transport only; no execution or changed receiver')
 require(request.get('source_thread_id')==fixed_id,'exact actual result source thread')
 page=g._native_document(root,request.get('actual_native_completion'))
 fixed=w.department_registry(root)[role]['chat_binding']
 require(page.get('thread',{}).get('cwd')==str(Path(root).resolve())==fixed.get('cwd')
  and fixed.get('project_id')==PROJECT,'actual result must remain in its fixed original project/directory')
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
 identified=bool(pin and pin['path']in message['text']and pin['sha256']in message['text'])
 if not identified and request.get('result_source_phase')=='delivery_ready':
  # The existing text READY form binds the same four-part identity. Never
  # infer a path from an arbitrary progress message or an incomplete digest.
  import shlex
  marker='FLASHCAST_DELIVERY_READY '
  declarations=[line[len(marker):]for line in message['text'].splitlines()if line.startswith(marker)]
  if len(declarations)==1:
   try:
    fields=[part.split('=',1)for part in shlex.split(declarations[0])]
    expected={k:request[k]for k in ('task_id','sender_department','candidate_version','result_sha256')}
    identified=len(fields)==len(expected)and all(len(x)==2 for x in fields)and dict(fields)==expected and len(dict(fields))==len(fields)
   except ValueError:identified=False
 require(pin and pin['sha256']==request['result_sha256']and identified,'actual source must identify the exact result bytes')
 observed=w._parse_observed_at(request.get('reply_observed_at'));now=dt.datetime.now(dt.timezone.utc)
 require(observed is not None and observed<=now,'real source observation timestamp required')
 native_time=turn.get('completedAt')if request.get('result_source_phase')!='delivery_ready'else turn.get('startedAt')
 require(type(native_time)in {int,float}and native_time<=observed.timestamp(),'native source event must precede observation')
 w.validate_outbox(root,[pin],role,request['task_id']);box=document(root,pin)
 require(box.get('candidate_version')==request['candidate_version'],'exact candidate version required')
 daily_proof={}
 if daily is not None:
  series=w._scheduled_series_local_delivery(root,request,box,daily)if box.get('source_automation_id')is None else None
  require(box.get('delivery_model')==MODE and box.get('fixed_chat_task_id')==fixed_id
   and (box.get('source_automation_id')==daily['automation_id']or series is not None and series.get('source_kind')=='unchanged_local_delivery_metadata')
   and box.get('status')not in {None,'','active','in_progress','pending'},'same original declared daily V2 result identity and finite scope required')
  require(isinstance(box.get('evidence'),list)and box['evidence']
   and all(isinstance(p,dict)and w.file_digest(root,p.get('path',''))==p for p in box['evidence']),
   'complete original daily result evidence pins required')
  require(page.get('thread',{}).get('projectId',PROJECT)==PROJECT
   and page.get('thread',{}).get('hostId',fixed.get('host_id'))==fixed.get('host_id'),
   'actual daily native project/host must match the original fixed identity')
  daily_proof=w._validate_scheduled_result(root,request,box,fixed_id).get('frozen_delivery_source',{})
 return {**daily_proof,'actual_native_completion':request['actual_native_completion'],'visible_reply':raw,'source_turn_id':turn['id'],
  'source_message_id':message['id'],'source_reply_sha256':raw['sha256'],'result_source_phase':request.get('result_source_phase','completed_final'),
  'mode_authorization':OWNER,'assistant_approval_required':False}

def _legacy_parent_owner_report(root,snapshot,identity,queued):
 """A frozen legacy ancestry link does not replace this task's real owner."""
 role=identity['sender_department'];goal=participant(root,snapshot,role,allow_completed_report=bool(queued))
 frozen=document(root,snapshot['goal_contract']);human=frozen.get('human_authorization',{})
 require(not autonomous_goal(goal)and professional(root,role)
  and role==goal.get('primary_owner')==frozen.get('primary_owner')
  and all(goal.get(k)==frozen.get(k)for k in ('parent_task_id','producer_departments','authorized_scope')),
  'original frozen professional owner, scope and historical parent required')
 auth=document(root,goal.get('authorization_pin'));message=auth.get('message',{})
 require(human.get('executor')==role and human.get('scope')in goal['authorized_scope']
  and human.get('evidence_path')==goal['authorization_pin']['path']
  and auth.get('source_thread_id')==human.get('source_thread_id')
  and message.get('id')==human.get('message_id')and message.get('type')=='userMessage',
  'unchanged actual original professional human authority required')
 mode=document(root,OWNER);started=next(t['startedAt']for t in mode['turns']if t['id']==OWNER_TURN)
 bindings=[e for e in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS)if e.get('task_id')==snapshot['task_id']
  and e.get('details',{}).get('goal_contract')==snapshot['goal_contract']]
 require(len(bindings)==1 and w._parse_observed_at(bindings[0].get('created_at'))is not None
  and w._parse_observed_at(bindings[0]['created_at']).timestamp()<started
  and all(bindings[0]['details'].get('goal_delivery',{}).get(k)==frozen.get(k)
   for k in ('primary_owner','parent_task_id','producer_departments','authorized_scope')),
  'actual unchanged pre-migration goal binding required; no new business authority')
 original_assignment_ready(root,snapshot,role)
 require(not queued or len(queued)==1 and queued[0].get('target_department')=='operations',
  'a historical original recipient cannot be replaced')
 for actor in (role,'operations'):
  fixed=w.department_registry(root)[actor]['chat_binding']
  require(fixed.get('project_id')==PROJECT and Path(fixed.get('cwd','')).resolve()==Path(root).resolve(),
   'same original project and fixed professional/HQ directory required')
 return 'operations'

def _autonomous_result_current_owner(root,snapshot,identity):
 """A new professional subtask retains its own frozen owner and ancestry."""
 role=identity['sender_department']
 # A read-only route is not admission of a new business action. Actual closed
 # result registration must additionally pass completed_result_archive below.
 completed_owner=(snapshot.get('current_state')=='closed'and role==snapshot.get('goal_delivery',{}).get('primary_owner'))
 goal=participant(root,snapshot,role,allow_completed_report=completed_owner)
 frozen=document(root,snapshot['goal_contract'])
 require(autonomous_goal(goal)and autonomous_goal(frozen)and frozen.get('task_id')==snapshot['task_id']==identity['task_id']
  and all(goal.get(k)==frozen.get(k)for k in ('primary_owner','parent_task_id','producer_departments','authorized_scope','human_authorization','collaboration_scopes')),
  'unchanged original autonomous task/owner/scope/parent/source required')
 owner=goal['primary_owner'];require(professional(root,owner)and professional(root,role)and role in frozen['producer_departments'], 'current original professional owner and producer required')
 human=frozen['human_authorization'];auth=document(root,goal['authorization_pin']);message=auth.get('message',{})
 require(human.get('executor')==owner and human.get('scope')in frozen['authorized_scope']
  and human.get('evidence_path')==goal['authorization_pin']['path']
  and auth.get('source_thread_id')==human.get('source_thread_id')and message.get('id')==human.get('message_id')
  and message.get('type')=='userMessage','actual frozen autonomous human authority required')
 require(not w.validate_workflow_events(root,snapshot['task_id']),'intact original autonomous binding chain required')
 bindings=[e for e in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS)if e.get('task_id')==snapshot['task_id']and e.get('details',{}).get('goal_contract')==snapshot['goal_contract']]
 require(len(bindings)==1 and all(bindings[0]['details'].get('goal_delivery',{}).get(k)==frozen.get(k)for k in ('primary_owner','parent_task_id','producer_departments','authorized_scope','human_authorization','delivery_model')),'one real unchanged original autonomous binding required')
 for actor in (owner,role):
  fixed=w.department_registry(root)[actor]['chat_binding']
  require(fixed.get('project_id')==PROJECT and Path(fixed.get('cwd','')).resolve()==Path(root).resolve(),'original same-project owner/producer required')
 if role!=owner:return owner
 # A task owner reports this task to HQ. An ancestry link alone is not a
 # specialist-return contract; explicit authenticated collaboration follows below.
 return 'operations'

def autonomous_result_route(root,identity):
 snapshot=w.read_json(w.snapshot_path(root,identity['task_id']))
 daily=scheduled_delivery_source(root,identity)
 if daily is not None:
  queued=[r for r in w._result_handoff_rows(root,identity['task_id'])if r.get('event')=='notification_queued'
   and all(r.get(k)==identity[k]for k in ('task_id','sender_department','candidate_version','result_sha256'))]
  require(len(queued)<=1 and all(r.get('target_department')=='operations'and r.get('mode_authorization')==OWNER
   and r.get('source_mode')=='scheduled_run'and r.get('source_automation_id')==daily['automation_id']for r in queued),
   'one immutable declared daily receiver and original source required')
  return {'lane':'HQ_knowledge','target_department':'operations','source_mode':MODE,'scheduled_report_only':True,
   'acceptance_proven':False,'notification_proven':False,'HQ_second_review_required':False,
   'automatic_wakeup_allowed':True,'knowledge_only':True}
 if not current_mode(root)or not snapshot.get('goal_delivery'):return None
 if identity['sender_department']in ASSISTANTS:return {'lane':'historical_read_only','target_department':None,'automatic_wakeup_allowed':False,'reason':'retired assistant history only'}
 if identity['sender_department']not in snapshot['goal_delivery']['producer_departments']:return None
 rows=w._result_handoff_rows(root,identity['task_id']);same=[r for r in rows if all(r.get(k)==identity[k]for k in ('task_id','sender_department','candidate_version','result_sha256'))]
 queued=[r for r in same if r.get('event')=='notification_queued']
 require(len(queued)<=1,'one immutable original queued result recipient required')
 # Never reinterpret a committed old recipient. Suppress its new activation;
 # actual original SQL/native intake remains readable before this classification.
 if queued and (queued[0].get('target_department')or queued[0].get('responsible_assistant'))in ASSISTANTS:
  return {'lane':'historical_read_only','target_department':None,'automatic_wakeup_allowed':False,'reason':'original assistant transport retained without new wakeup'}
 if queued:
  # The hash-chained exact queue has already frozen this delivery's receiver.
  # Parent/producer routing is only for a result that has not been queued yet.
  target=queued[0].get('target_department')or queued[0].get('responsible_assistant')
  require(queued[0].get('outbox',{}).get('sha256')==identity['result_sha256']
   and(target=='operations'or professional(root,target)), 'exact frozen original professional result recipient required')
  return {'lane':'HQ_knowledge'if target=='operations'else'professional_acceptance','target_department':target,'source_mode':MODE,
   'acceptance_proven':False,'notification_proven':False,'HQ_second_review_required':False,'automatic_wakeup_allowed':True,'knowledge_only':target=='operations'}
 target='operations';source={}
 parent_id=snapshot['goal_delivery'].get('parent_task_id')
 if autonomous_goal(snapshot['goal_delivery']):
  target=_autonomous_result_current_owner(root,snapshot,identity)
 elif parent_id:
  original_owner=document(root,snapshot['goal_contract']).get('primary_owner')
  if identity['sender_department']==original_owner:
   target=_legacy_parent_owner_report(root,snapshot,identity,queued)
  else:
   parent=w.read_json(w.snapshot_path(root,w.validate_task_id(parent_id)));owner=parent.get('goal_delivery',{}).get('primary_owner')
   target=owner if parent and owner and professional(root,owner)else _legacy_parent_owner_report(root,snapshot,identity,queued)
 producer=[r for r in w.read_jsonl(w.receipts_path(root,identity['task_id']))if r.get('receipt_type')=='outbox_received'and r.get('department')==identity['sender_department']and any(p.get('sha256')==identity['result_sha256']for p in r.get('evidence',[]))]
 if producer:
  pins=[p for p in producer[-1]['evidence']if p.get('sha256')==identity['result_sha256']];require(len(pins)==1,'exact original producer outbox');source=document(root,pins[0])
 collab=source.get('collaboration_return')
 if isinstance(collab,dict):
  require(not autonomous_goal(snapshot['goal_delivery'])or identity['sender_department']==snapshot['goal_delivery']['primary_owner'],'a specialist result returns to this task owner, not an arbitrary parent')
  parent=w.read_json(w.snapshot_path(root,collab.get('parent_task_id','')));owner=parent.get('goal_delivery',{}).get('primary_owner')
  require(parent and owner==collab.get('primary_owner')and professional(root,owner)and snapshot['goal_delivery'].get('parent_task_id')==parent['task_id'], 'actual original parent owner for collaboration return')
  target=owner
 # A full business owner reporting inside its own parent business is not a
 # child specialist returning work to another owner. Never retarget an
 # already frozen transport, which was returned above.
 if target==identity['sender_department']==snapshot['goal_delivery']['primary_owner']:
  target='operations'
 return {'lane':'HQ_knowledge'if target=='operations'else'professional_acceptance','target_department':target,'source_mode':MODE,
  'acceptance_proven':False,'notification_proven':False,'HQ_second_review_required':False,'automatic_wakeup_allowed':True,'knowledge_only':target=='operations'}

def register_preflight(root,task,input_path):
 from tools.shop_office_web_execution import applies as web_applies, record_preflight as web_record
 incoming=w.read_json(w.safe_path(root,input_path))
 if incoming.get('schema')=='professional-external-WEB-fresh-preflight/v1':
  from professional_web_execution import record_preflight as original_WEB_preflight
  return original_WEB_preflight(root,task,input_path)
 if incoming.get('schema')=='professional-cms-fresh-preflight/v1':
  from professional_cms_execution import record_preflight
  return record_preflight(root,task,input_path)
 if web_applies(task,incoming.get("action_class")):return web_record(root,input_path)
 if task=='fc-20261025-shop-office-existing-six-and-five-implementation-release-v1'and incoming.get('action_class')=='cms_write':
  from tools.shop_office_six_field_execution import record_preflight as exact_cms_preflight
  return exact_cms_preflight(root,input_path)
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
 from professional_web_execution import applies as original_WEB,policy as original_WEB_policy
 if original_WEB(root,requested.get('task_id'),requested.get('action_class')):return original_WEB_policy(root,requested)
 from tools.shop_office_web_execution import applies as web_applies, policy as web_policy
 if web_applies(requested.get("task_id"),requested.get("action_class")):return web_policy(root,requested)
 snapshot=w.read_json(w.snapshot_path(root,requested['task_id']))
 if not autonomous_goal(snapshot.get('goal_delivery')):
  from professional_ads_execution import match
  if match(root,snapshot,requested)is None:return None
 if requested['action_class']not in w.EXTERNAL_ACTION_CLASSES:return None
 require(not requested.get('approval_id')and not requested.get('target_project_id')and not requested.get('target_department'), 'ordinary exact task execution, not a borrowed permit or cross-project route')
 context=action_authority(root,snapshot,requested);role=context['department']
 if requested.get('actual_executor_state'):
  from flashcast_ops import refresh_department_health
  refresh_department_health(root,role,requested['actual_executor_state'],only_if_stale=True)
 binding=w.department_registry(root)[role]['chat_binding']
 require(binding.get('project_id')==PROJECT and Path(binding.get('cwd','')).resolve()==Path(root).resolve()
  and w._chat_binding_healthy(binding,verification_ttl_hours=26),'current professional executor identity/health required')
 request=context['request'];observed=w._parse_observed_at(request.get('observed_at'))
 require(observed is not None and 0<=(dt.datetime.now(dt.timezone.utc)-observed).total_seconds()<=300,'fresh actual execution observation required; reports do not expire')
 key=w.sha256_value([requested[k]for k in ('task_id','department','action_id','action_class','scope')])
 instance=None
 if requested.get('task_id')=='fc-20261025-shop-office-existing-six-and-five-implementation-release-v1'and requested.get('action_class')=='cms_write':
  from tools.shop_office_six_field_execution import policy_instance
  instance=policy_instance(root,context)
  require('execution_instance'not in requested or requested['execution_instance']==instance,'instance derives only from the authenticated current preflight')
 if requested.get('action_class')=='cms_write'and context.get('request',{}).get('professional_execution_source')is not None:
  from professional_cms_pre_main_recovery import instance as original_pre_main_instance
  instance=original_pre_main_instance(root,request)
  require('execution_instance'not in requested or requested['execution_instance']==instance,'instance derives only from authenticated current professional request')
 if instance is not None:key=w.sha256_value([key,instance['recovery_event_id'],instance['recovery_source']])
 with w.workflow_lock(root):
  prior=[x for x in w.read_jsonl(Path(root)/w.POLICY_DECISIONS)if x.get('autonomous_action_key')==key and x.get('status')=='allow']
  require(not prior,'original exact action already issued; read actual/unknown effect before any recovery, never replay')
  value={**requested,'status':'preflight_ready_not_a_permit','actual_action_allowed':False,'approval_basis':MODE,
   'original_authority':context['authorization'],'mode_authorization':OWNER,'exact_request':context['pin'],
   'autonomous_action_key':key,'checked_at':w.utc_timestamp(),'assistant_approval_required':False,'retry_authorized':False}
  if instance is not None:value['execution_instance']=instance
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


def existing_receiver_result_knowledge(root,source):
 """Actual professional knowledge can suppress a redundant notice, not sign intake."""
 proof=source.get('actual_existing_receiver_knowledge')
 if proof is None:return None
 require(isinstance(proof,dict)and set(proof)=={'actual_receiver_native','actual_receiver_message_id'},'exact existing receiver native source, never caller flags')
 snapshot=w.read_json(w.snapshot_path(root,source['task_id']));role=source['sender_department']
 route=autonomous_result_route(root,source);owner=snapshot['goal_delivery']['primary_owner']
 require(autonomous_goal(snapshot['goal_delivery'])and route.get('target_department')==owner
  and role!=owner and professional(root,owner),'only this actual autonomous professional owner can have prior specialist knowledge')
 import result_coordination as rc
 require(not w.read_json(rc._notification_path(root,source)),'existing notification effect must be recovered by its original key, not reclassified')
 original_assignment_ready(root,snapshot,owner)
 import goal_delivery_runtime as g
 page=g._native_document(root,proof['actual_receiver_native'])
 pairs=[(t,m)for t in page.get('turns',[])for m in t.get('items',[])if m.get('id')==proof['actual_receiver_message_id']]
 require(len(pairs)==1 and any(source['task_id']in m.get('text','')for m in pairs[0][0].get('items',[])if m.get('type')in {'agentMessage','userMessage'}),'actual receiver task context required')
 observed=w._parse_observed_at(source.get('reply_observed_at'));updated=page.get('thread',{}).get('updatedAt')
 require(observed is not None and type(updated)in {int,float}and observed.timestamp()<=updated<=dt.datetime.now(dt.timezone.utc).timestamp(),'actual receiver knowledge after original result source required')
 checked=received_knowledge(root,{**source,**proof,'coordinator_role':owner})
 return {**checked,'receiver_department':owner,'knowledge_proven':True,'formal_intake_proven':False,'native_transport_proven':False,'repeat_transport_required':False}

def recovered_report_delivery(root,source):
 """Recover a real prior first-party report, never backfill a send/claim."""
 observation=source.get('recovered_native_report')
 if observation is None:return None
 import re
 import goal_delivery_runtime as g
 proof=document(root,observation);original=document(root,proof.get('original_queue_request'))
 require(all(source.get(k)==v for k,v in original.items()if k not in {'outbox_path','evidence_paths'})
  and(source.get('outbox_path')or source.get('outbox',{}).get('path'))==original['outbox_path'],
  'unchanged original queued request and idempotency required')
 req=document(root,proof.get('normal_report_request'));prepared=document(root,proof.get('normal_report_result'))
 intent=document(root,proof.get('original_send_intent'));payload=req.get('payload')
 require(isinstance(payload,dict)and w.file_digest(root,payload.get('path',''))==payload,'original normal report payload required')
 body=(Path(root)/payload['path']).read_text();snap=g.restore_goal(root,w.read_json(w.snapshot_path(root,source['task_id'])))
 route=message_route(root,snap,req)
 require(route and route['target_department']=='operations'and req.get('sender_department')==source['sender_department']
  and req.get('task_id')==source['task_id']and source['result_sha256']in body and original['outbox_path']in body,
  'same original professional result and normal HQ report required')
 require('scope'not in source or source['scope']==req['scope'],'same original report scope required')
 evidence=source.get('evidence_paths')
 require(evidence==original.get('evidence_paths')if evidence is not None else source.get('evidence')==[w.file_digest(root,p)for p in original.get('evidence_paths',[])],
  'original queue evidence must remain unchanged')
 policy=prepared.get('policy_decision',{});fields=('task_id','action_id','action_class','scope','department','source_project_id','target_project_id','target_department','target_thread_id','payload_sha256')
 actual=[x for x in w.read_jsonl(Path(root)/w.POLICY_DECISIONS)if x.get('decision_id')==policy.get('decision_id')]
 require(prepared.get('status')=='ready_to_send'and policy.get('status')=='allow'and len(actual)==1
  and all(actual[0].get(k)==policy.get(k)for k in fields)
  and all(policy.get(k)==req.get(k)for k in fields if k!='department')
  and policy.get('department')==source['sender_department']and intent.get('payload')==payload
  and intent.get('policy_decision_id')==policy.get('decision_id'),
  'genuine original exact normal report policy/intent required')
 started=w._parse_observed_at(intent.get('started_at'));checked=w._parse_observed_at(policy.get('checked_at'))
 require(started is not None and checked is not None and checked<=started<=dt.datetime.now(dt.timezone.utc),
  'original policy then actual send chronology required')
 sender=g._native_document(root,proof.get('sender_after'));receiver=g._native_document(root,proof.get('receiver_after'))
 before_sender=g._native_document(root,intent.get('actual_before_sender'));before_receiver=g._native_document(root,intent.get('actual_before_receiver'))
 registry=w.department_registry(root);fixed=registry[source['sender_department']]['chat_binding'];hq=registry['operations']['chat_binding']
 for page,expected in ((sender,fixed),(before_sender,fixed),(receiver,hq),(before_receiver,hq)):
  require(all(page.get('thread',{}).get(k)==expected[v]for k,v in {'id':'task_id','cwd':'cwd','title':'title'}.items()),
   'original fixed professional/HQ before/after native identities required')
 previous={m['id']for t in before_sender.get('turns',[])for m in t.get('items',[])}
 calls=[m for t in sender.get('turns',[])if not t.get('error')for m in t.get('items',[])
  if m.get('type')=='mcpToolCall'and m.get('tool')=='send_message_to_thread'
  and m.get('arguments',{}).get('threadId')==hq['task_id']and m.get('arguments',{}).get('prompt')==body]
 require(len(calls)==1 and calls[0]['id']not in previous and calls[0].get('server')=='codex_app'
  and calls[0].get('status')=='completed'and not calls[0].get('error'), 'one actual new successful original report invocation required')
 from qa_review_plan import _review_native_containers
 _review_native_containers(calls[0])
 before_ids={m['id']for t in before_receiver.get('turns',[])for m in t.get('items',[])}
 pattern=r'\A<codex_delegation>\s*<source_thread_id>([^<\s]+)</source_thread_id>\s*<input>([\s\S]*)</input>\s*</codex_delegation>\Z';effects=[]
 for turn in receiver.get('turns',[]):
  for item in turn.get('items',[]):
   output=item.get('output',{});match=re.fullmatch(pattern,output.get('text',''))if isinstance(output,dict)else None
   if item.get('type')=='functionCallOutput'and item['id']not in before_ids and output.get('truncated')is False and match and match[1]==fixed['task_id']and match[2]==body:effects.append(item)
 require(len(effects)==1,'one real newly received exact UTF8 report effect required')
 return {'source':observation,'payload':payload,'policy_decision_id':policy['decision_id'],
  'actual_sender_call_id':calls[0]['id'],'actual_recipient_effect_id':effects[0]['id'],
  'actual_native_delivery_proven':True,'HQ_intake_proven':False,'notification_sent_backfilled':False}

def completed_result_archive(root,request,route):
 """Authenticate final owner-result metadata after real scope completion.

 No caller flag, new participant or permission can turn a closed task into an
 executable one. Native READY, exact bytes and every original completion proof
 are read by the same normal validators used for the open task.
 """
 import goal_delivery_runtime as g
 snapshot=g.restore_goal(root,w.read_json(w.snapshot_path(root,request['task_id'])))
 if snapshot.get('current_state')not in w.TERMINAL_STATES:return {}
 goal=snapshot.get('goal_delivery',{});role=request.get('sender_department')
 require(snapshot.get('current_state')=='closed'and autonomous_goal(goal)
  and request.get('event')=='notification_queued'and role==goal.get('primary_owner')and professional(root,role)
  and route.get('lane')=='HQ_knowledge'and route.get('target_department')=='operations'
  and route.get('source_mode')==MODE,'only the original completed professional-owner result to HQ may be archived')
 frozen=document(root,snapshot.get('goal_contract'))
 require(all(goal.get(k)==frozen.get(k)for k in ('primary_owner','parent_task_id','producer_departments','authorized_scope','human_authorization'))
  and goal.get('source_mode')==frozen.get('source_mode','approved_dispatch')
  and request.get('scope')in frozen.get('authorized_scope',[])and request.get('action_class')in {None,'thread_message'}
  and not any(request.get(k)for k in ('approval_id','consume_approval','execution_request','authorization_changes')),'archive retains the frozen task/scope/source; no execution or expanded authority')
 fixed=w.department_registry(root)[role]['chat_binding']['task_id']
 source=native_result(root,request,fixed)  # Actual business validator, never a supplied READY boolean.
 pin=request.get('outbox')or w.file_digest(root,request.get('outbox_path',''));box=document(root,pin)
 require(box.get('status')=='completed'and box.get('scope')==request['scope']and box.get('primary_owner',role)==role
  and not box.get('collaboration_return')and not box.get('remaining_this_completed_scope')
  and not box.get('business_parent_closed',False),'one complete original owner report, not partial work or a new parent/business action')
 proof=completion(root,snapshot)
 require(proof.get('state')=='PROVEN'and proof.get('requirements')and not proof.get('missing')and not proof.get('blockers')
  and all(x.get('state')=='PROVEN'for x in proof['requirements']),'every actual frozen completion proof must remain PROVEN before final archival')
 events=[e for e in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS)if e.get('task_id')==snapshot['task_id']and e.get('details',{}).get('autonomous_completion_proof')]
 expected={x['requirement_id']for x in requirement_rows(goal)}
 require(len(events)==len(expected)and {e['details']['autonomous_completion_proof']['requirement_id']for e in events}==expected,'one actual proof per original criterion; no hard-coded count or substitute')
 observed=w._parse_observed_at(request.get('reply_observed_at'))
 require(observed is not None and all(w._parse_observed_at(e.get('created_at'))is not None and w._parse_observed_at(e['created_at'])<=observed for e in events),'final source observation must follow actual completion registration')
 pins=[e['details']['autonomous_completion_proof']for e in events]
 return {'schema':'completed-original-owner-result-archive/v1','goal_contract':snapshot['goal_contract'],'scope':request['scope'],
  'original_owner':role,'outbox':pin,'actual_completion_proofs':pins,'source_fingerprint':w.sha256_value([snapshot['goal_contract'],pin,source,pins]),
  'business_reopened':False,'external_permission_issued':False}

def record_autonomous_result(root,request):
 import result_coordination as rc,uuid
 task=w.validate_task_id(request['task_id']);identity=rc.exact_identity(request);event=request['event']
 require(event in {'notification_queued','controller_received'},'ordinary delivery has no assistant QA/technical decision stage')
 role=identity['sender_department'];fixed=w.department_registry(root)[role]['chat_binding']['task_id']
 rows=w._result_handoff_rows(root,task);same=[x for x in rows if all(x.get(k)==v for k,v in identity.items())]
 existing=[x for x in same if x.get('event')==event]
 if existing:
  require(len(existing)==1 and existing[0].get('idempotency_key')==request.get('idempotency_key'),'one exact original result event only')
  if existing[0].get('completed_result_archive'):
   prior=existing[0];pin=request.get('outbox')or w.file_digest(root,request.get('outbox_path',''))
   require(pin==prior.get('outbox')and all(request.get(k)==prior.get(k)for k in ('scope','source_thread_id','source_turn_id','source_message_id','result_source_phase','actual_native_completion','visible_reply','source_reply_sha256','reply_observed_at'))
    and [w.file_digest(root,p)for p in request.get('evidence_paths',[])]==prior.get('evidence',[]),'duplicate archive must retain its original complete identity, source and evidence')
  return {**existing[0],'result':'duplicate_ignored'},[w.result_handoff_path(root,task)]
 source=native_result(root,request,fixed)if event=='notification_queued'else None
 if event=='notification_queued':
  recovered_report_delivery(root,request)
  existing_receiver_result_knowledge(root,request)
 queued=[x for x in same if x.get('event')=='notification_queued']
 if event!='notification_queued':require(len(queued)==1,'one original queued source before intake/transport')
 route=autonomous_result_route(root,identity);require(route and route.get('automatic_wakeup_allowed'),'current professional result route required')
 archive=completed_result_archive(root,request,route)if event=='notification_queued'else{}
 pin=w.file_digest(root,request['outbox_path'])if request.get('outbox_path')else request.get('outbox')or queued[0]['outbox']
 require(pin['sha256']==identity['result_sha256'],'exact original result pin')
 if queued:require(pin==queued[0]['outbox'],'result intake must retain original queued bytes')
 knowledge=received_knowledge(root,request)if event=='controller_received'else{}
 row={**request,**identity,**(source or {}),**knowledge,'record_id':str(uuid.uuid4()),'schema_version':'1.0','created_at':w.utc_timestamp(),
  'outbox':pin,'evidence':[w.file_digest(root,p)for p in request.get('evidence_paths',[])],
  'target_department':route['target_department'],'coordinator_role':request.get('coordinator_role','operations'),
  'mode_authorization':OWNER,'business_goal_closed':False,'assistant_approval_required':False}
 if archive:row['completed_result_archive']=archive
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
 if (request.get('event')in {'notification_queued','controller_received'}
  and scheduled_delivery_source(root,request)is not None):return True
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

def _rotated_original_professional_assignment(root,snapshot,role,rows):
 """Read an original native responsibility across a verified role rotation.

 The old registry is scoped to the existing read-only validator. No receipt,
 new ACK, assignment or production authority is created by this projection.
 """
 import copy
 import goal_continuity as gc
 import goal_delivery_runtime as g
 import department_rotation as rotation
 frozen=document(root,snapshot['goal_contract']);goal=snapshot['goal_delivery']
 verified,bad=w._validate_receipt_chain(root,snapshot['task_id'])
 require(not bad and rows==verified,'intact exact original historical receipt chain required')
 require(current_mode(root)and not autonomous_goal(frozen)and professional(root,role)
  and role in frozen.get('producer_departments',[])
  and all(goal.get(k)==frozen.get(k)for k in ('primary_owner','producer_departments','authorized_scope','human_authorization')),
  'unchanged historical professional responsibility required')
 records=list(rotation._records(root));current=w.department_registry(root)
 links=[r for r in records if r['role']==role and r['new_binding']['task_id']==current[role]['chat_binding']['task_id']]
 planned=[p for p in snapshot.get('departments',[])if p.get('department')==role]
 require(len(links)==len(planned)==1 and planned[0].get('chat_task_id')==links[0]['old_binding']['task_id'],
  'one original planned responsibility and actual same-role rotation required')
 old=links[0]['old_binding'];registry=copy.deepcopy(current)
 for record in records:
  if record['role']in registry:registry[record['role']]['chat_binding']=record['old_binding']
 for index,ack in enumerate(rows):
  if not(ack.get('receipt_type')=='chat_ack'and ack.get('department')==role
   and ack.get('chat_task_id')==old['task_id']and ack.get('ack_nonempty')is True):continue
  sources=[];pages=[];texts=[]
  for pin in ack.get('evidence',[]):
   require(w.file_digest(root,pin.get('path',''))==pin,'original historical ACK evidence changed')
   if not pin['path'].endswith('.json'):texts.append((Path(root)/pin['path']).read_bytes());continue
   obj=document(root,pin)
   if obj.get('schema')=='goal-current-assignment/v2':sources.append(obj)
   page=g._native_document(root,pin)
   if page.get('thread'):pages.append(page)
  dispatches=[r for r in rows[:index]if r.get('receipt_type')=='dispatch_sent'and r.get('department')==role
   and r.get('chat_task_id')==old['task_id']and r.get('action_id')==ack.get('action_id')and r.get('scope')==ack.get('scope')]
  if not dispatches:continue
  require(len(dispatches)==1,'one original exact dispatch before native ACK required')
  dispatch=dispatches[0];sent=w._parse_observed_at(dispatch.get('created_at'));at=w._parse_observed_at(ack.get('created_at'))
  policies=[p for p in w.read_jsonl(Path(root)/w.POLICY_DECISIONS)if p.get('decision_id')==dispatch.get('policy_decision_id')]
  require(len(policies)==1,'one original dispatch policy required');policy=policies[0]
  require(all(policy.get(k)==v for k,v in {'status':'allow','task_id':snapshot['task_id'],'scope':ack['scope'],
   'action_id':ack['action_id'],'action_class':'thread_message','target_department':role,'target_thread_id':old['task_id'],
   'source_project_id':PROJECT,'target_project_id':PROJECT,'target_cwd':str(Path(root).resolve())}.items())
   and policy.get('department')in {'operations',frozen.get('responsible_assistant'),frozen.get('primary_owner')},
   'unchanged exact original allowed dispatch policy and project required')
  sender=registry[policy['department']]['chat_binding'];calls=[];returns=[];payloads=[]
  for pin in dispatch.get('evidence',[]):
   require(w.file_digest(root,pin.get('path',''))==pin,'original native dispatch evidence changed')
   if pin['sha256']==policy.get('payload_sha256'):payloads.append((Path(root)/pin['path']).read_text())
   if not pin['path'].endswith('.json'):continue
   page=g._native_document(root,pin)
   if page.get('threadId')==old['task_id']:returns.append(page)
   if not all(page.get('thread',{}).get(k)==sender[v]for k,v in {'id':'task_id','title':'title','cwd':'cwd'}.items()):continue
   for turn in page.get('turns',[]):
    if turn.get('error'):continue
    calls.extend((turn,m)for m in turn.get('items',[])if m.get('type')=='mcpToolCall'and m.get('server')=='codex_app'
     and m.get('tool')=='send_message_to_thread'and m.get('status')=='completed'and not m.get('error')
     and m.get('truncated',False)is False and m.get('arguments',{}).get('threadId')==old['task_id'])
  # Older wrappers bind exact_consumed_prompt instead of a naked threadId.
  if not returns:
   from qa_review_plan import _review_same_goal_send_wrapper
   for pin in dispatch.get('evidence',[]):
    if not pin['path'].endswith('.json'):continue
    obj=document(root,pin)
    if obj.get('actual_tool')=='mcp__codex_app__send_message_to_thread':
     wrapper=_review_same_goal_send_wrapper(obj)
     if wrapper.get('thread_id')==old['task_id']and wrapper.get('exact_consumed_prompt',{}).get('sha256')==policy['payload_sha256']:returns.append(wrapper)
  calls=[(t,m)for t,m in calls if m['arguments'].get('prompt')in payloads and snapshot['task_id']in m['arguments']['prompt']]
  require(len(calls)==len(returns)==1 and len(payloads)==1,'one exact actual successful native send, body and return required')
  checked=w._parse_observed_at(policy.get('checked_at'));start=calls[0][0].get('startedAt')
  require(sent and at and checked and checked<=sent<=at and type(start)in {int,float}and start<=sent.timestamp(),
   'real original policy/send/ACK chronology required')
  messages=[]
  for page in pages:
   if not all(page.get('thread',{}).get(k)==old[v]for k,v in {'id':'task_id','title':'title','cwd':'cwd'}.items()):continue
   for turn in page.get('turns',[]):
    if turn.get('status')not in {'inProgress','completed'}or turn.get('error'):continue
    started=turn.get('startedAt')
    if not(type(started)in {int,float}and sent.timestamp()-600<=started<=at.timestamp()):continue
    for message in turn.get('items',[]):
     text=message.get('text')
     if message.get('type')=='agentMessage'and message.get('id')and isinstance(text,str)and text.strip()and(not texts or text.encode()in texts):
      messages.append((turn.get('id'),message['id']))
  require(len(set(messages))==1,'one real original nonempty native ACK and unchanged UTF8 required')
  return True
 require(False,'original rotated native dispatch/ACK source missing')


def original_assignment_ready(root,snapshot,role):
 if snapshot['goal_delivery'].get('source_mode')=='owner_direct':return True
 rows=w.read_jsonl(w.receipts_path(root,snapshot['task_id']));fixed=w.department_registry(root)[role]['chat_binding']['task_id']
 sent=[r for r in rows if r.get('receipt_type')=='dispatch_sent'and r.get('department')==role and r.get('chat_task_id')==fixed]
 if not sent:return _rotated_original_professional_assignment(root,snapshot,role,rows)
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
  if target in ASSISTANTS or identity.get('sender_department')in ASSISTANTS:
   historical.append({**identity,'kind':'historical_assistant_transport','target_department':target,
    'source':w.file_digest(root,w.rel_path(root,path)),'delivery_state':record.get('native_queue_transport',{}).get('state'),
    'not_current_work':True,'new_dispatch_allowed':False,'receipt_status':'read original committed ledger; not inferred here'})
   continue
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
 import goal_delivery_runtime as g
 snapshot=g.restore_goal(root,snapshot)
 if migrated_local_completion(root,snapshot):
  proof=professional_local_completion_view(root,snapshot)
  return {'task_id':snapshot['task_id'],'state':'completed_scope'if proof['state']=='PROVEN'else'executing',
   'primary_owner':snapshot['goal_delivery']['primary_owner'],'native_workflow_state':snapshot['current_state'],
   'completion_obligations':proof,'responsible_assistant':None,'historical_responsible_assistant':snapshot['goal_delivery'].get('responsible_assistant'),
   'delivery_model':MODE,'business_goal_closed':False,'HQ_second_review_required':False}
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
