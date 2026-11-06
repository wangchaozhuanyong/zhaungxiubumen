"""Same original PUB technical continuation, authenticated transport only.
Original A, production/preview action and all execution gates stay unchanged.
"""
from pathlib import Path
import datetime as dt,re,shlex
import workflow_control as w
import professional_cms_single_field_admission as s
SCHEMA='same-original-PUB-technical-continuation-source/v1'
EVENT='original_PUB_singlefield_technical_continuation'
MARKER='HQ_original_PUB_singlefield_continuation_source'
PREFIX='HQ-PUB-singlefield-continuation-'
AFTER_RECEIPT_LOCK_SCHEMA='same-original-PUB-after-receipt-lock-continuation-source/v1'
SOURCE_SCHEMAS=frozenset({SCHEMA,AFTER_RECEIPT_LOCK_SCHEMA})

def need(ok,why):s.need(ok,'continuation: '+why)
def rows(root):return s.events(root,s.h.TASK,EVENT)
def refusal_output(call):
 out=call.get('output')
 need(isinstance(out,dict) and set(out)=={'text','truncated'} and isinstance(out['text'],str) and out['truncated'] is False,'actual untruncated failed-command output; never relabel failure as success')
 return out['text'].encode('utf-8')
def stop_key(root,item):
 if item.get('schema')==AFTER_RECEIPT_LOCK_SCHEMA:return _after_receipt_lock_stop_key(root,item)
 decision=s.document(root,item['HQ_recovery_decision']);refusal=s.document(root,decision['actual_partial_provider_refusal'])
 return {'task_id':s.h.TASK,'PUB_thread':decision['original_PUB_thread'],'A_action':decision['original_A_action'],'previous_turn_id':decision['previous_actual_PUB_turn'],'remaining_operation':refusal['action_id'],'remaining_phase':refusal['actual_refusal']['stage']}
def aid(root,item):return PREFIX+w.sha256_value(stop_key(root,item))[:28]
def payload(item,decision):
 if item.get('schema')==AFTER_RECEIPT_LOCK_SCHEMA:return _after_receipt_lock_payload(item,decision)
 return {'schema':'same-original-PUB-technical-continuation-message/v1','task_id':s.h.TASK,'scope':s.h.SCOPE,'sender_department':'operations','target_department':'publishing','normal_continuation_source_path':item['source_input_path'],'original_A_source':item['bridge_source'],'original_A_received':item['original_A_received'],'previous_completed_native':item['previous_completed_native'],'actual_provider_refusal':decision['actual_partial_provider_refusal'],'HQ_recovery_decision':item['HQ_recovery_decision'],'physical_target':decision['physical_target'],'sequence':decision['required_boundaries'],'remaining':'Freshly capture original full41/CAS/version/protect38/MS11/keys plus actual SDK. Preserve original preview/action/key and first inspect existing effects. Continue normal zero-write preview/admission/own fresh one-use permit/forward Save/public only if its original gates pass.','previous_RPC_failure_status':'NOT_PROVEN','old_A_input_must_not_be_replayed':True,'transport_is_execution_permit':False,'parent_closed':False}

def validate(root,item):
 if isinstance(item,dict) and item.get('schema')==AFTER_RECEIPT_LOCK_SCHEMA:return _validate_after_receipt_lock(root,item)
 keys={'schema','task_id','scope','source_input_path','bridge_source','original_A_received','previous_completed_native','previous_provider_bundle','HQ_recovery_decision','HQ_native','request'}
 need(set(item)==keys and item.get('schema')==SCHEMA and item.get('task_id')==s.h.TASK and item.get('scope')==s.h.SCOPE,'exact technical continuation source')
 ctx=s.bridge_context(root,item['bridge_source']);A=s.document(root,item['bridge_source']);decision=s.document(root,item['HQ_recovery_decision']);reg=w.department_registry(root);hq=reg['operations']['chat_binding'];pub=ctx['pub_binding']
 need(decision.get('schema')=='actual-HQ-same-original-PUB-provider-recovery-decision/v1' and decision.get('decision_actor')=='operations' and decision.get('decision_thread_id')==hq['task_id'] and decision.get('owner_delegation_source')==A['owner_delegation'] and decision.get('task_id')==s.h.TASK and decision.get('scope')==s.h.SCOPE and decision.get('professional_owner')==ctx['snapshot']['goal_delivery']['primary_owner'] and decision.get('executor')=='publishing' and decision.get('original_PUB_thread')==pub['task_id'] and decision.get('original_conditional_decision')==A['HQ_decision'] and decision.get('original_A_source')==item['bridge_source'] and decision.get('original_A_action')==ctx['action']['action_id'] and decision.get('actual_A_message_received')==item['original_A_received'] and decision.get('previous_actual_completed_native')==item['previous_completed_native'] and decision.get('source_or_decision_is_execution_permit') is False and decision.get('content_reapproval_required') is False and decision.get('production_Save_performed') is False and decision.get('business_parent_closed') is False and decision.get('required_boundaries'),'real same-object ordinary HQ repair decision, never new content approval/permit')
 t=ctx['target'];physical={'name':t['candidateVersion'],'table':t['table'],'record_id':t['id'],'slug':t['slug'],'scope':t['scope'],'action_id':t['actionId'],'candidate_version':t['candidateVersion'],'changed_fields':['content_zh'],'baseline_fields_count':41,'protected_fields_count':38,'MS_fields_count':11,'desired_fields_sha256':t['desiredFieldsSha256'],'rollback_fields_sha256':t['rollbackFieldsSha256'],'rollback_allowed':False}
 need(decision.get('physical_target')==physical,'same full41/protect38/MS11 forward-only object; no scope expansion')
 page=s.native(root,item['HQ_native'],hq);named=[(turn,m) for turn in page.get('turns',[]) for m in turn.get('items',[]) if m.get('type')=='agentMessage' and m.get('phase') in {'commentary','final_answer'} and item['HQ_recovery_decision']['sha256'] in m.get('text','') and Path(item['HQ_recovery_decision']['path']).name in m.get('text','')]
 need(len(named)==1,'real HQ assistant message names exact decision path/SHA; not a fabricated human')
 turn,message=named[0];decided=w._parse_observed_at(decision.get('at_UTC'))
 need(not turn.get('error') and turn.get('status') in {'inProgress','completed'} and type(turn.get('startedAt')) in {int,float} and decided and turn['startedAt']<=decided.timestamp()<=dt.datetime.now(dt.timezone.utc).timestamp() and (turn.get('status')!='completed' or type(turn.get('completedAt')) in {int,float} and decided.timestamp()<=turn['completedAt']) and ('不是保存许可' in message.get('text','') or 'not' in message.get('text','').lower()),'actual HQ decision turn/time and no-Save statement required')
 # Independently consume the normal committed A receipt, not its file claims.
 receipt=s.document(root,item['original_A_received'])
 need(item['original_A_received'] in ctx['snapshot']['goal_delivery'].get('collaboration_records',[]) and receipt.get('status')=='message_received' and receipt.get('action_id')==ctx['action']['action_id'],'original A normal receipt must actually be committed')
 bundle=s.document(root,item['previous_provider_bundle']);need(bundle.get('bridge_source')==item['bridge_source'] and bundle.get('provider_references',{}).get('turn_id')==decision.get('previous_actual_PUB_turn')==receipt.get('recipient_turn_id'),'same original received finite turn/data references')
 previous=s._received(root,ctx,{**bundle,'PUB_native':item['previous_completed_native']})
 need(previous.get('status')=='completed' and not previous.get('error') and type(previous.get('completedAt')) in {int,float} and previous['completedAt']>=previous['startedAt'],'previous genuine finite PUB turn completed, not failed or maintenance-only')
 finals=[m for m in previous['items'] if m.get('type')=='agentMessage' and m.get('phase')=='final_answer' and m.get('text','').strip()]
 refusal=s.document(root,decision['actual_partial_provider_refusal'])
 need(len(finals)==1 and Path(decision['actual_partial_provider_refusal']['path']).name in finals[0]['text'] and refusal.get('schema')=='original-PUB-singlefield-real-provider-refusal-result/v1' and refusal.get('task_id')==s.h.TASK and refusal.get('action_id')==t['actionId'] and refusal.get('physical_scope')==t['scope'] and refusal.get('owner_HQ_exact_source')==item['bridge_source']['sha256'] and all(refusal.get(k) is False for k in ('preview_dispatched','new_policy_issued','new_permit_issued','save','business_parent_closed')),'actual previous partial/no-Save result names exact remaining phase')
 calls=[m for m in previous['items'] if m.get('id')==refusal.get('actual_refusal',{}).get('command_id')]
 need(len(calls)==1 and calls[0].get('type')=='commandExecution' and calls[0].get('status') in {'completed','failed'} and calls[0].get('exitCode')==1 and Path(calls[0].get('cwd','')).resolve()==Path(root).resolve() and refusal['actual_refusal']['message'].encode() in refusal_output(calls[0]),'actual provider refusal command/effect; exact cause remains unproven')
 request=s.document(root,item['request']);body=request.get('payload',{})
 expected={'task_id':s.h.TASK,'scope':s.h.SCOPE,'action_id':aid(root,item),'sender_department':'operations','action_class':'thread_message','source_project_id':hq['project_id'],'target_project_id':pub['project_id'],'target_department':'publishing','target_thread_id':pub['task_id'],'target_thread_title':pub['title'],'target_cwd':pub['cwd'],'target_sidebar_section_id':pub['sidebar_section_id'],'delivery_mode':'official_native_queue','assignment_record_required':False,'authorization_changes':[]}
 need(set(request)==set(s.h.IDENTITY_KEYS) and all(request.get(k)==v for k,v in expected.items()) and w.file_digest(root,body.get('path',''))==body and body.get('sha256')==request.get('payload_sha256') and s.document(root,body)==payload(item,decision),'one exact normal HQ-to-original-PUB continuation; no actor/payload/channel replacement')
 need(Path(item['source_input_path']).is_absolute() and Path(item['source_input_path']).resolve().is_relative_to(Path(root).resolve()),'project-owned immutable source self path')
 return {**ctx,'action':request,'continuation_input':item,'previous_turn_id':previous['id'],'registration':None}

def registered(root,snapshot,request):
 if not isinstance(request,dict):return None
 pin=request.get(MARKER)
 if pin is None:
  if not str(request.get('action_id','')).startswith(PREFIX):return None
  found=[e['details'][EVENT] for e in rows(root) if aid(root,s.document(root,e['details'][EVENT]))==request['action_id']]
  need(len(found)==1,'one original continuation source event');pin=found[0]
 need(set(request)<=set(s.h.IDENTITY_KEYS)|s.FRESH|{MARKER},'transport-only continuation fields')
 events=[e for e in rows(root) if e['details'][EVENT]==pin]
 need(snapshot.get('task_id')==s.h.TASK and len(events)==1,'one normal append-only continuation registration')
 item=s.document(root,pin);need(Path(root,pin['path']).resolve()==Path(item['source_input_path']).resolve(),'exact continuation self path')
 ctx=validate(root,item);action={**ctx['action'],MARKER:pin}
 need(all(request[k]==action[k] for k in request if k not in s.FRESH) and [a for a in ctx['snapshot']['goal_delivery'].get('approved_actions',[]) if a.get('action_id')==action['action_id']]==[action],'unchanged registered continuation action/source/fixed target')
 return {**ctx,'action':action,'registration':pin,'event_id':events[0]['event_id']}

def record(root,task,path):
 from department_rotation import prohibit_validation_write
 prohibit_validation_write();pin=w.file_digest(root,path);item=s.document(root,pin)
 need(task==s.h.TASK and Path(root,path).resolve()==Path(item['source_input_path']).resolve(),'same original task/source registration')
 with w.workflow_lock(root),w.request_validation_context() as validation:
  ctx=validate(root,item);snap=ctx['snapshot'];action={**ctx['action'],MARKER:pin};previous=[e for e in rows(root) if stop_key(root,s.document(root,e['details'][EVENT]))==stop_key(root,item)]
  if previous:
   need(len(previous)==1 and previous[0]['details'][EVENT]==pin,'one continuation per original finite stop; never fork or reset')
   return {'result':'duplicate_ignored','message_sent':False,'source':pin}
  import department_autonomy as a
  a._owner_message_transport_not_started(root,snap,action);need(not any(x.get('action_id')==action['action_id'] for x in snap['goal_delivery'].get('approved_actions',[])),'original continuation action already exists')
  validation.recheck();snap['goal_delivery']={**snap['goal_delivery'],'approved_actions':[*snap['goal_delivery'].get('approved_actions',[]),action]}
  event=w.append_workflow_event(root,task,snap['current_state'],{EVENT:pin,'goal_delivery':snap['goal_delivery'],'actual_actor':'operations','original_A_preserved':True,'external_permission_issued':False});w.atomic_write_json(w.snapshot_path(root,task),snap)
 return {'result':'recorded','event_id':event['event_id'],'source':pin,'action_id':action['action_id'],'message_sent':False,'permit_issued':False}

def current_receipt(root,ctx,bundle):
 pin=bundle.get('continuation_source');need(isinstance(pin,dict),'later data turn needs real normal continuation source')
 c=registered(root,{'task_id':s.h.TASK},{MARKER:pin});need(c and c['continuation_input']['bridge_source']==bundle['bridge_source'] and all(c['pub_binding'].get(k)==ctx['pub_binding'].get(k) for k in s.STABLE),'same initial A/owner/recipient context; no source substitution')
 import goal_delivery_runtime as g
 states=g._collaboration_wait_states(root,c['snapshot'],only_action_id=c['action']['action_id'])
 need(len(states)==1 and states[0].get('received') is True and states[0].get('status') in {'message_received','result_received'} and states[0].get('approved_action',{}).get('payload_sha256')==c['action']['payload_sha256'],'real normal continuation receipt required; accepted is insufficient')
 receipt=s.document(root,states[0].get('result_receipt'))
 need(receipt.get('source_kind')=='official_native_queue' and receipt.get('status') in {'message_received','result_received'} and receipt.get('action_id')==c['action']['action_id'] and receipt.get('target_thread_id')==ctx['pub_binding']['task_id'] and receipt.get('recipient_turn_id')==bundle['provider_references']['turn_id'] and receipt.get('recipient_message_id') and receipt.get('ack_message_id'),'exact continuation receipt turn/message/ACK, not copied later-turn input')
 return {**c,'actual_received_record':receipt}


def _after_receipt_lock_stop_key(root,item):
 decision=s.document(root,item['HQ_recovery_decision']);stop=s.document(root,item['previous_lock_stop'])
 return {'task_id':s.h.TASK,'PUB_thread':decision['original_PUB_thread'],
  'A_action':decision['original_A_action'],'previous_turn_id':stop['actual_recipient_turn'],
  'remaining_operation':stop['action_id'],'remaining_phase':'fresh_provider_capture_before_original_preview'}


def _after_receipt_lock_payload(item,decision):
 return {'schema':'same-original-PUB-after-receipt-lock-continuation-message/v1',
  'task_id':s.h.TASK,'scope':s.h.SCOPE,'sender_department':'operations','target_department':'publishing',
  'normal_continuation_source_path':item['source_input_path'],'original_A_source':item['bridge_source'],
  'original_A_received':item['original_A_received'],'previous_continuation_source':item['previous_continuation_source'],
  'previous_continuation_received':item['previous_continuation_received'],
  'previous_completed_native':item['previous_completed_native'],'actual_receipt_lock_stop':item['previous_lock_stop'],
  'HQ_recovery_decision':item['HQ_recovery_decision'],'physical_target':decision['physical_target'],
  'sequence':decision['required_boundaries'],'remaining_phase':decision['remaining_phase'],
  'remaining':'The previous original continuation is actually received. Do not replay A/C or their receipts. First read original action/key effects. Freshly capture full41/raw CAS/version/protect38/MS11/keys and actual native, then continue original zero-write preview/admission/own fresh one-use forward permit/Save/public only through unchanged gates.',
  'normal_transport_receipt_writer':'operations original sender only',
  'receipt_coordination':['operations alone handles the official queue and normal queue_accepted/message_received records; original PUB must not start duplicate concurrent self-registration',
   'PUB first gives a real nonempty ACK and necessary read-only checks, then reads this exact original action receipt; only after real message_received is readable freshly capture production data under original TTL and execute independently',
   'a short metadata wait is not business completion: keep the same object/remaining phase and resume on the original committed-receipt/completion event; no new approval, duplicate send, daemon or polling schedule'],
  'old_A_or_C_input_must_not_be_replayed':True,'transport_is_execution_permit':False,'parent_closed':False}


def _after_lock_received_turn(root,context,page,receipt,*,completed=False):
 turns=[t for t in page.get('turns',[]) if t.get('id')==receipt.get('recipient_turn_id')]
 need(len(turns)==1 and not turns[0].get('error') and turns[0].get('status') in ({'completed'} if completed else {'inProgress','completed'}),
  'actual previous continuation receiving turn, never a copied later page')
 turn=turns[0];body=w.safe_path(root,context['action']['payload']['path']).read_text()
 users=[(i,m) for i,m in enumerate(turn.get('items',[])) if m.get('type')=='userMessage' and m.get('id')==receipt.get('recipient_message_id')]
 acks=[(i,m) for i,m in enumerate(turn.get('items',[])) if m.get('type')=='agentMessage' and m.get('id')==receipt.get('ack_message_id')]
 need(len(users)==len(acks)==1 and users[0][0]<acks[0][0]
  and users[0][1].get('content')==[{'type':'text','text':body}]
  and acks[0][1].get('phase') in {'commentary','final_answer'} and isinstance(acks[0][1].get('text'),str) and acks[0][1]['text'].strip(),
  'exact previously committed input/message/ACK IDs and original continuation bytes required')
 return turn


def _after_receipt_lock_previous(root,item,ctx):
 """Real prior receipt + completed native lock stop; no future execution proof."""
 predecessor=s.document(root,item['previous_continuation_source'])
 need(predecessor.get('schema')==SCHEMA and Path(root,item['previous_continuation_source']['path']).resolve()!=Path(item['source_input_path']).resolve(),
  'one registered original technical continuation predecessor, never a new-source cycle')
 import goal_delivery_runtime as g
 need(predecessor.get('bridge_source')==item['bridge_source'] and predecessor.get('original_A_received')==item['original_A_received'],
  'same original A/receipt in the previous technical continuation')
 events=[e for e in rows(root) if e['details'][EVENT]==item['previous_continuation_source']]
 action=aid(root,predecessor)
 need(len(events)==1,'one original append-only predecessor registration')
 # This exact reader already authenticates every original C native queue
 # source, including registered(C)/validate(C). Consume its returned proof
 # once; do not repeat an extra full predecessor validation before the reader.
 states=g._collaboration_wait_states(root,ctx['snapshot'],only_action_id=action)
 need(len(states)==1 and states[0].get('received') is True
  and states[0].get('status') in {'message_received','result_received'}
  and states[0].get('proof_state') in {'RECEIVED','PROVEN'}
  and states[0].get('approved_action',{}).get(MARKER)==item['previous_continuation_source'],
  'actual normally authenticated predecessor receipt, accepted/claimed is insufficient')
 state=states[0];receipt=s.document(root,item['previous_continuation_received'])
 need(item['previous_continuation_received'] in ctx['snapshot']['goal_delivery'].get('collaboration_records',[])
  and receipt.get('source_kind')=='official_native_queue' and receipt.get('status')=='message_received'
  and receipt.get('action_id')==action and receipt.get('target_thread_id')==ctx['pub_binding']['task_id'],
  'the exact previous message receipt must be in the normally verified action history')
 latest=s.document(root,state['result_receipt'])
 stable=('task_id','action_id','scope','payload_sha256','target_thread_id','policy_decision_id',
  'original_prepare_request','original_prepare_result','actual_queue_intent','actual_queue_result',
  'queue_message_id','recipient_turn_id','recipient_message_id','ack_message_id')
 need(all(receipt.get(k)==latest.get(k) for k in stable)
  and state['approved_action'].get('payload_sha256')==receipt.get('payload_sha256'),
  'original receiving input/ACK/queue identity persists through any later real result receipt')
 prior={**ctx,'action':state['approved_action'],'continuation_input':predecessor}
 page=s.native(root,item['previous_completed_native'],ctx['pub_binding'])
 previous=_after_lock_received_turn(root,prior,page,receipt,completed=True)
 need(type(previous.get('startedAt')) in {int,float} and type(previous.get('completedAt')) in {int,float}
  and previous['startedAt']<=previous['completedAt'],'actual completed finite original PUB turn times required')
 stop=s.document(root,item['previous_lock_stop']);target=ctx['target']
 need(stop.get('schema')=='original-pub-singlefield-continuation-actual-stop/v1'
  and stop.get('task_id')==s.h.TASK and stop.get('action_id')==target['actionId'] and stop.get('record_id')==target['id']
  and stop.get('actual_recipient_turn')==previous['id'] and stop.get('actual_message_id')==receipt['recipient_message_id']
  and all(stop.get(k) is False for k in ('preview_dispatched','production_permit_issued','save','parent_closed')),
  'actual same-object before-preview/permit/Save stop, never caller business completion')
 finals=[m for m in previous.get('items',[]) if m.get('type')=='agentMessage' and m.get('phase')=='final_answer' and m.get('text','').strip()]
 need(len(finals)==1 and Path(item['previous_lock_stop']['path']).name in finals[0]['text'],
  'actual completed final names this exact finite lock-stop artifact')
 # The interrupted local request may contain a different genuine recipient
 # native export. All other original queue/turn/message/ACK fields stay exact.
 interrupted=s.document(root,item['interrupted_receipt_request'])
 need({k:v for k,v in interrupted.items() if k!='actual_native_recipient'}=={k:v for k,v in receipt.items() if k!='actual_native_recipient'},
  'interrupted receipt request must retain the exact normally committed original queue identity')
 alias=_after_lock_received_turn(root,prior,s.native(root,interrupted['actual_native_recipient'],ctx['pub_binding']),receipt)
 committed=_after_lock_received_turn(root,prior,s.native(root,receipt['actual_native_recipient'],ctx['pub_binding']),receipt)
 for mid in (receipt['recipient_message_id'],receipt['ack_message_id']):
  original=next(m for m in previous['items'] if m.get('id')==mid)
  need([m for m in alias['items'] if m.get('id')==mid]==[original]
   and [m for m in committed['items'] if m.get('id')==mid]==[original],
   'independent native exports must retain exact original input and ACK bytes/fields')
 return prior,receipt,previous,stop


def _actual_lock_interrupt_output(call):
 output=call.get('output')
 need(isinstance(output,dict) and set(output)=={'text','truncated'} and isinstance(output['text'],str)
  and output['truncated'] is False,'actual untruncated receipt lock-interruption output required')
 return output['text'].encode('utf-8').decode('utf-8')


def _validate_after_receipt_lock(root,item):
 keys={'schema','task_id','scope','source_input_path','bridge_source','original_A_received',
  'previous_continuation_source','previous_continuation_received','previous_completed_native',
  'previous_lock_stop','interrupted_receipt_request','HQ_recovery_decision','HQ_native','request'}
 need(set(item)==keys and item.get('schema')==AFTER_RECEIPT_LOCK_SCHEMA
  and item.get('task_id')==s.h.TASK and item.get('scope')==s.h.SCOPE,'exact after-receipt-lock original continuation source')
 ctx=s.bridge_context(root,item['bridge_source']);A=s.document(root,item['bridge_source'])
 decision=s.document(root,item['HQ_recovery_decision']);hq=w.department_registry(root)['operations']['chat_binding'];pub=ctx['pub_binding']
 need(decision.get('schema')=='actual-HQ-same-original-PUB-after-receipt-lock-recovery-decision/v1'
  and decision.get('decision_actor')=='operations' and decision.get('decision_thread_id')==hq['task_id']
  and decision.get('owner_delegation_source')==A['owner_delegation'] and decision.get('task_id')==s.h.TASK and decision.get('scope')==s.h.SCOPE
  and decision.get('professional_owner')==ctx['snapshot']['goal_delivery']['primary_owner'] and decision.get('executor')=='publishing'
  and decision.get('original_PUB_thread')==pub['task_id'] and decision.get('original_conditional_decision')==A['HQ_decision']
  and decision.get('original_A_source')==item['bridge_source'] and decision.get('original_A_action')==ctx['action']['action_id']
  and decision.get('actual_A_message_received')==item['original_A_received']
  and all(decision.get(k)==item[v] for k,v in {'previous_continuation_source':'previous_continuation_source',
    'previous_continuation_received':'previous_continuation_received','previous_actual_completed_native':'previous_completed_native',
    'actual_receipt_lock_stop':'previous_lock_stop','actual_interrupted_receipt_request':'interrupted_receipt_request'}.items())
  and decision.get('remaining_phase')=='fresh_provider_capture_before_original_preview'
  and all(decision.get(k) is False for k in ('source_or_decision_is_execution_permit','content_reapproval_required',
    'production_preview_dispatched','production_permit_issued','production_Save_performed','business_parent_closed'))
  and decision.get('required_boundaries'),'actual ordinary same-object after-lock decision, no new execution grant')
 t=ctx['target'];physical={'name':t['candidateVersion'],'table':t['table'],'record_id':t['id'],'slug':t['slug'],
  'scope':t['scope'],'action_id':t['actionId'],'candidate_version':t['candidateVersion'],'changed_fields':['content_zh'],
  'baseline_fields_count':41,'protected_fields_count':38,'MS_fields_count':11,'desired_fields_sha256':t['desiredFieldsSha256'],
  'rollback_fields_sha256':t['rollbackFieldsSha256'],'rollback_allowed':False}
 need(decision.get('physical_target')==physical,'same original full41/protect38/MS11/false-inverse target')
 page=s.native(root,item['HQ_native'],hq)
 named=[(turn,m) for turn in page.get('turns',[]) for m in turn.get('items',[]) if m.get('type')=='agentMessage'
  and m.get('phase') in {'commentary','final_answer'} and item['HQ_recovery_decision']['sha256'] in m.get('text','')
  and Path(item['HQ_recovery_decision']['path']).name in m.get('text','')]
 need(len(named)==1,'actual HQ assistant message names this exact ordinary decision path/SHA')
 turn,message=named[0];decided=w._parse_observed_at(decision.get('at_UTC'))
 need(not turn.get('error') and turn.get('status') in {'inProgress','completed'} and type(turn.get('startedAt')) in {int,float}
  and decided and turn['startedAt']<=decided.timestamp()<=dt.datetime.now(dt.timezone.utc).timestamp()
  and (turn.get('status')!='completed' or type(turn.get('completedAt')) in {int,float} and decided.timestamp()<=turn['completedAt'])
  and ('不是保存许可' in message.get('text','') or 'not' in message.get('text','').lower()),'real HQ decision chronology and no-Save statement required')
 prior,receipt,previous,stop=_after_receipt_lock_previous(root,item,ctx)
 need(decision.get('previous_actual_PUB_turn')==previous['id'],'decision binds the actual previous finite continuation turn')
 calls=[m for m in previous['items'] if m.get('id')==decision.get('interrupted_command_id')]
 need(len(calls)==1 and calls[0].get('type')=='commandExecution' and calls[0].get('status')=='failed'
  and type(calls[0].get('exitCode')) is int and calls[0]['exitCode']==130
  and Path(calls[0].get('cwd','')).resolve()==Path(root).resolve(),'actual interrupted original receipt command required')
 call=calls[0];parts=shlex.split(call.get('command',''))
 need(len(parts)==3 and parts[:2] in (['/bin/zsh','-lc'],['zsh','-lc']),'one original static receipt CLI command')
 argv=shlex.split(parts[2]);need(len(argv)==7 and Path(argv[0]).name in {'python3','python3.11'}
  and argv[1:]==['tools/goal_delivery_runtime.py','collaboration-record','--task-id',s.h.TASK,'--input',item['interrupted_receipt_request']['path']],
  'same original interrupted receipt input, not a wrapper or production command')
 output=_actual_lock_interrupt_output(call)
 need('in record_collaboration' in output and 'with w.workflow_lock(root)' in output
  and 'in workflow_lock' in output and output.rstrip().endswith('fcntl.flock(handle.fileno(), fcntl.LOCK_EX)\nKeyboardInterrupt')
  and previous['items'].index(call)<previous['items'].index(next(m for m in previous['items'] if m.get('type')=='agentMessage' and m.get('phase')=='final_answer')),
  'actual untruncated interruption at lock acquisition; no inferred post-lock write result')
 request=s.document(root,item['request']);body=request.get('payload',{})
 expected={'task_id':s.h.TASK,'scope':s.h.SCOPE,'action_id':aid(root,item),'sender_department':'operations',
  'action_class':'thread_message','source_project_id':hq['project_id'],'target_project_id':pub['project_id'],
  'target_department':'publishing','target_thread_id':pub['task_id'],'target_thread_title':pub['title'],
  'target_cwd':pub['cwd'],'target_sidebar_section_id':pub['sidebar_section_id'],'delivery_mode':'official_native_queue',
  'assignment_record_required':False,'authorization_changes':[]}
 need(set(request)==set(s.h.IDENTITY_KEYS) and all(request.get(k)==v for k,v in expected.items())
  and w.file_digest(root,body.get('path',''))==body and body.get('sha256')==request.get('payload_sha256')
  and s.document(root,body)==payload(item,decision),'one exact normal HQ-to-original-PUB next continuation, no replaced actor/channel')
 need(Path(item['source_input_path']).is_absolute() and Path(item['source_input_path']).resolve().is_relative_to(Path(root).resolve()),
  'project-owned exact continuation source self path')
 return {**ctx,'action':request,'continuation_input':item,'previous_turn_id':previous['id'],'registration':None}
