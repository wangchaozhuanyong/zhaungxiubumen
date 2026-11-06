"""Original HQ→PUB conditional work order and independent actual-data admission.

A message is not a permit. Pending/local contracts remain immutable metadata.
Only real PUB provider reads and protected zero-write artifacts can admit the
forward source. Every new policy re-reads providers; no supplied PASS/READY is
trusted. Stored command text is never executed.
"""
from pathlib import Path
from contextlib import contextmanager
from contextvars import ContextVar
import argparse,datetime as dt,hashlib,json,re
import workflow_control as w
import hq_bounded_web_admission as h

BRIDGE_SCHEMA='HQ-original-PUB-singlefield-conditional-workorder/v1'
BRIDGE_EVENT='HQ_original_PUB_singlefield_workorder'
MARKER='HQ_original_PUB_singlefield_source'
ADMISSION_SCHEMA='original-PUB-singlefield-production-admission/v1'
PREVIEW_SCHEMA='original-PUB-singlefield-zero-write-preview-request/v1'
PREVIEW_EVENT='original_PUB_singlefield_preview_request'
_BASE=ContextVar('singlefield_original_source_read_only',default=False)
STABLE=('task_id','title','project_id','cwd','host_id','sidebar_section_id')
FRESH=h.FRESH_KEYS


def need(ok,why):
    if not ok:raise w.WorkflowError('HQ/PUB singlefield: '+why)


def base_source_validation_active():return _BASE.get()


@contextmanager
def base_source_validation():
    """Original032/993 cannot depend on a future source. Never an execution view."""
    token=_BASE.set(True)
    try:yield
    finally:_BASE.reset(token)


def document(root,pin):
    need(isinstance(pin,dict) and set(pin)=={'path','sha256','size'},'exact immutable source pin required')
    path=Path(root,pin['path']).resolve();need(path.is_relative_to(Path(root).resolve()),'project-owned immutable source required')
    return h.document(root,{**pin,'path':str(path.relative_to(Path(root).resolve()))})


def same(root,left,right):
    return isinstance(left,dict) and isinstance(right,dict) and set(left)==set(right)=={'path','sha256','size'} and Path(root,left['path']).resolve()==Path(root,right['path']).resolve() and all(left.get(k)==right.get(k) for k in ('sha256','size'))


def events(root,task,name):
    return [e for e in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS,where={'task_id':task}) if e.get('details',{}).get(name)]


def native(root,pin,binding):
    from qa_review_plan import _review_native_containers
    value=document(root,pin);page=value.get('native',value)
    if 'native' in value:need(value.get('source')=='first_party_read_thread','real first-party native source required')
    _review_native_containers(value);_review_native_containers(page)
    need(all(page.get('thread',{}).get(k) in (None,binding.get('project_id')) for k in ('projectId','project_id')),'explicit native project conflicts with original binding')
    need(page.get('thread',{}).get('kind')=='codex' and all(page.get('thread',{}).get(k)==binding.get(v) for k,v in {'id':'task_id','title':'title','cwd':'cwd','hostId':'host_id'}.items()),'original fixed native thread/host/cwd/title required')
    return page


def action_id(pin):return 'HQ-PUB-singlefield-conditional-'+pin['sha256'][:24]


def payload_document(item,decision):
    return {'schema':'HQ-original-PUB-singlefield-conditional-message/v1','task_id':h.TASK,'scope':h.SCOPE,
      'sender_department':'operations','target_department':'publishing','HQ_decision':item['HQ_decision'],
      'owner_delegation':item['owner_delegation'],'normal_workorder_source_path':item['source_input_path'],
      'object':decision['physical_target'],'WEB_deployed_result':decision['WEB_result'],
      'sequence':decision['approved_conditional_continuation'],
      'normal_entry':'professional_cms_single_field_admission inspect → actual PUB row/key reads → preview-request normal record/policy → actual protected dry-run → production-admission normal record → original PUB fresh preflight/policy/issuer/one Save/public readback',
      'exclusions':decision['not_granted'],'source_or_message_is_execution_permit':False,
      'production_READY':False,'business_parent_closed':False}


def validate_bridge(root,item):
    keys={'schema','task_id','scope','source_input_path','owner_delegation','HQ_decision','HQ_native','request'}
    need(isinstance(item,dict) and set(item)==keys and item.get('schema')==BRIDGE_SCHEMA and item.get('task_id')==h.TASK and item.get('scope')==h.SCOPE,'exact typed original conditional work order required')
    snap=h._snapshot(root);goal=snap['goal_delivery'];reg=w.department_registry(root)
    HQ=reg['operations']['chat_binding'];PUB=reg['publishing']['chat_binding']
    owner=document(root,item['owner_delegation']);decision=document(root,item['HQ_decision'])
    need(item['owner_delegation']==h.CODE_PINS['owner_delegation']
      and owner.get('source_thread_id')==HQ['task_id'] and owner.get('role')=='human' and owner.get('message_id')==h.HUMAN_MESSAGE
      and decision.get('schema')=='actual-HQ-single-field-publication-object-ordinary-decision/v1'
      and decision.get('decision_actor')=='operations' and decision.get('decision_thread_id')==HQ['task_id']
      and decision.get('owner_delegation_source')==item['owner_delegation']
      and decision.get('task_id')==h.TASK and decision.get('scope')==h.SCOPE
      and decision.get('professional_owner')==goal['primary_owner'] and decision.get('content_integrator') in goal['producer_departments']
      and decision.get('execution_department')=='publishing' and all(decision.get('original_PUB_binding',{}).get(k)==PUB.get(k) for k in STABLE)
      and decision.get('source_or_decision_is_execution_permit') is False and decision.get('business_parent_closed') is False,
      'real owner-delegated operations decision and stable original PUB identity only')
    page=native(root,item['HQ_native'],HQ)
    pairs=[(t,m) for t in page.get('turns',[]) for m in t.get('items',[]) if m.get('type')=='agentMessage' and m.get('phase')=='commentary' and item['HQ_decision']['sha256'] in m.get('text','') and item['HQ_decision']['path'] in m.get('text','')]
    need(len(pairs)==1,'one actual HQ native commentary names this exact new decision')
    turn,_=pairs[0];at=w._parse_observed_at(decision.get('at_UTC'))
    need(turn.get('status')=='inProgress' and turn.get('completedAt') is None and not turn.get('error') and at and type(turn.get('startedAt')) in {int,float} and turn['startedAt']<=at.timestamp()<=dt.datetime.now(dt.timezone.utc).timestamp(),'actual decision chronology, never invented human/completed')
    import professional_cms_single_field_pending as pending,professional_cms_issuer as issuer
    with base_source_validation():
        pe=[e for e in events(root,h.TASK,pending.EVENT) if e['event_id']==decision.get('source_pending_event')]
        ie=[e for e in events(root,h.TASK,issuer.EVENT) if e['event_id']==decision.get('original_local_issuer_event')]
        need(len(pe)==len(ie)==1 and same(root,pe[0]['details'][pending.EVENT]['source'],decision.get('original_registration')) and same(root,ie[0]['details'][issuer.EVENT],decision.get('original_local_issuer_contract')),'actual original pending+local issuer events and pins required')
        pending_value=pending.validate(root,snap,document(root,decision['original_registration']))
        old_contract=document(root,decision['original_local_issuer_contract'])
        local,_,target=issuer.validate_contract(root,snap,old_contract)
    need(local.get('source_only_single_field_contract') is True and pending_value['candidate_version']==target['candidateVersion']
      and target['changedFields']==['content_zh'] and target['rollbackAllowed'] is False
      and len(target['baselineProjectionFields'])==41 and len(target['retainedProjectionFields'])==38 and sum(k.endswith('_ms') for k in target['retainedProjectionFields'])==11,
      'original authenticated full41/protect38/MS11/single field/false inverse only')
    candidate=document(root,pending_value['candidate'])
    need(decision.get('reviewed_exact_added_paragraph')==candidate.get('exact_insert_text') and isinstance(decision.get('approved_conditional_continuation'),list) and len(decision['approved_conditional_continuation'])==5 and isinstance(decision.get('not_granted'),list) and 'inverse or rollback execution' in decision['not_granted'] and 'EN or MS edits' in decision['not_granted'],'real HQ exact content review and forward-only conditional completion scope required')
    obj=decision.get('physical_target',{})
    need(all(obj.get(k)==v for k,v in {'name':target['candidateVersion'],'table':target['table'],'record_id':target['id'],'slug':target['slug'],'scope':target['scope'],'action_id':target['actionId'],'candidate_version':target['candidateVersion'],'changed_fields':target['changedFields'],'baseline_fields_count':41,'protected_fields_count':38,'MS_fields_count':11,'desired_fields_sha256':target['desiredFieldsSha256'],'rollback_fields_sha256':target['rollbackFieldsSha256'],'rollback_allowed':False}.items()),'HQ object tuple must exactly match original target, no new object/EN/MS')
    result=document(root,decision['WEB_result']);nxt=document(root,decision['WEB_next_input'])
    need(result.get('schema')=='WEB-actual-05971-code-release-and-Edge90-loaded-result/v2'
      and result.get('task_id')==h.TASK and result.get('scope')==h.SCOPE and result.get('producer')=='designated-development'
      and same(root,nxt.get('WEB_result'),decision['WEB_result']) and same(root,nxt.get('source_registration'),decision['original_registration'])
      and same(root,nxt.get('issuer_contract'),decision['original_local_issuer_contract'])
      and same(root,nxt.get('actual_loading_proof'),decision.get('actual_loading_proof')),
      'actual original WEB completion/loading next-input chain required')
    from hq_singlefield_test_successor import execution_context as web_context
    with base_source_validation():
        wc=web_context(root,h.TASK,result['original_HQ_base_source'],result['actual_successor_source'])
    webbinding={**wc['binding'],'task_id':wc['binding']['thread_id']}
    wp=native(root,decision['WEB_completed_native'],webbinding)
    turns=[t for t in wp.get('turns',[]) if t.get('id')==result.get('actual_WEB_turn')]
    need(len(turns)==1 and turns[0].get('status')=='completed' and not turns[0].get('error'),'actual original WEB completed finite turn required')
    final=[m for m in turns[0].get('items',[]) if m.get('type')=='agentMessage' and m.get('phase') in {'final','final_answer'} and m.get('text','').strip()]
    need(len(final)==1 and all(str(Path(root,decision[k]['path']).resolve()) in final[0]['text'] for k in ('WEB_result','WEB_next_input')),'actual WEB final names exact result and next input')
    edge=result['Edge'];main=decision['actual_main'];r3=result['actual_effects']['R3']
    need(re.fullmatch('[0-9a-f]{40}',str(main)) and main==result['Git']['actual_main']==nxt['actual_main']
      and r3.get('id')==decision['actual_R3_run']==nxt['R3_run'] and r3.get('run_attempt')==decision['actual_R3_attempt']==nxt['run_attempt']==1
      and r3.get('head_sha')==main and r3.get('status')=='completed' and r3.get('conclusion')=='success'
      and r3.get('path')=='.github/workflows/supabase-content-publish-r3.yml'
      and edge['actual_loaded_version']==decision['actual_Edge_version']==nxt['Edge_version']
      and same(root,edge['exact_target_and_all_files_proof'],decision['actual_loading_proof']), 'actual same-main successful R3 attempt and loaded Edge, not future release')
    from professional_cms_issuer import external
    from professional_web_execution import git
    proof=external(root,decision['actual_loading_proof'],wc['binding']);raw=external(root,edge['source_readback'],wc['binding'])
    need(raw.get('status')=='ACTIVE' and raw.get('slug')==proof.get('function')=='content-publish'
      and raw.get('version')==proof.get('version')==decision['actual_Edge_version']
      and raw.get('ezbr_sha256')==proof.get('ezbr_sha256')==edge['ezbr_sha256']
      and proof.get('actual_main')==main and proof.get('project')==wc['project_ref'] and proof.get('target')==target,
      'actual complete deployed runtime/target bytes bind exact source and project')
    files=raw.get('files');protected=proof.get('files')
    need(isinstance(files,list) and isinstance(protected,list) and len(files)==len(protected)==proof.get('runtime_source_count')==edge['complete_runtime_source_files'] and len(files)>0 and len({x.get('name') for x in files})==len(files),'complete unique runtime source closure required')
    # Only deployed immutable bytes; no current provider/preview/permit state.
    with base_source_validation():
        for entry in files:
            name=entry.get('name');need(isinstance(name,str) and name.startswith('functions/') and '..' not in Path(name).parts,'only original bounded runtime paths')
            content=entry.get('content');need(isinstance(content,str),'actual raw runtime source bytes required')
            blob=git(wc,'show',main+':supabase/'+name)
            matches=[f for f in protected if f.get('runtime_name')==name]
            need(len(matches)==1 and blob==content.encode() and hashlib.sha256(blob).hexdigest()==matches[0].get('sha256') and len(blob)==matches[0].get('size'),'every deployed runtime byte must equal immutable actual main')
    # Independently decode the exact target from real loaded source, not proof booleans.
    texts=[x['content'] for x in files if x['name'].endswith('/next8-renovation-zh05971-target.ts')]
    need(len(texts)==1,'one actual original singlefield runtime selector')
    start=re.search(r'=\s*(\[)',texts[0]);need(start is not None,'actual target array required')
    values,_=json.JSONDecoder().raw_decode(texts[0][start.start(1):]);need(values==[target],'loaded selector contains exactly original false-inverse target')
    request=document(root,item['request']);payload=request.get('payload',{})
    need(set(request)==set(h.IDENTITY_KEYS) and all(request.get(k)==v for k,v in {'task_id':h.TASK,'scope':h.SCOPE,'action_id':action_id(item['HQ_decision']),'sender_department':'operations','target_department':'publishing','action_class':'thread_message','source_project_id':HQ['project_id'],'target_project_id':PUB['project_id'],'target_thread_id':PUB['task_id'],'target_thread_title':PUB['title'],'target_cwd':PUB['cwd'],'target_sidebar_section_id':PUB['sidebar_section_id'],'delivery_mode':'official_native_queue','assignment_record_required':False,'authorization_changes':[]}.items())
      and w.file_digest(root,payload.get('path',''))==payload and payload.get('sha256')==request.get('payload_sha256') and document(root,payload)==payload_document(item,decision),'one exact genuine HQ-to-original-PUB conditional message, no actor substitution')
    need(Path(item['source_input_path']).is_absolute() and Path(item['source_input_path']).resolve().is_relative_to(Path(root).resolve()),'normal source path belongs to original project')
    return {'snapshot':snap,'decision':decision,'target':target,'pending':pending_value,'local':local,'pub_binding':PUB,'sender_binding':HQ,
      'action':request,'web_context':{**wc,'commit':main},'task':h.TASK,'scope':h.SCOPE,'project_ref':wc['project_ref'],
      'before':document(root,pending_value['dated_baseline']),'desired':local['desired'],'source':pending_value['candidate'],
      'external_permission_issued':False,'production_READY':False}


def registered_bridge(root,snapshot,request):
    if not isinstance(request,dict):return None
    if request.get('HQ_original_PUB_singlefield_continuation_source') is not None or str(request.get('action_id','')).startswith('HQ-PUB-singlefield-continuation-'):
        from professional_cms_singlefield_continuation import registered
        from goal_source_recovery import _normal_prepare_registered_source
        return _normal_prepare_registered_source(root,snapshot,request,
            lambda: registered(root,snapshot,request))
    pin=request.get(MARKER)
    if pin is None:
        aid=request.get('action_id','')
        if not str(aid).startswith('HQ-PUB-singlefield-conditional-'):return None
        found=[]
        for e in events(root,h.TASK,BRIDGE_EVENT):
            p=e['details'][BRIDGE_EVENT];item=document(root,p)
            if action_id(item['HQ_decision'])==aid:found.append(p)
        need(len(found)==1,'one actual normally registered original PUB workorder source required');pin=found[0]
    need(set(request)<=set(h.IDENTITY_KEYS)|FRESH|{MARKER},'workorder cannot carry permit/execution/foreign fields')
    rows=[e for e in events(root,h.TASK,BRIDGE_EVENT) if e['details'][BRIDGE_EVENT]==pin]
    need(snapshot.get('task_id')==h.TASK and len(rows)==1,'one original append-only PUB workorder event required')
    item=document(root,pin);need(Path(root,pin['path']).resolve()==Path(item['source_input_path']).resolve(),'original source self path changed')
    ctx=validate_bridge(root,item);action={**ctx['action'],MARKER:pin}
    need(all(request[k]==action[k] for k in request if k not in FRESH) and [x for x in ctx['snapshot']['goal_delivery'].get('approved_actions',[]) if x.get('action_id')==action['action_id']]==[action],'exact registered conditional workorder action/payload/actor/target')
    return {**ctx,'registration':pin,'action':action,'event_id':rows[0]['event_id']}


def record_bridge(root,task,path):
    from department_rotation import prohibit_validation_write
    prohibit_validation_write();need(not base_source_validation_active() and task==h.TASK,'normal original task record only')
    pin=w.file_digest(root,path);item=document(root,pin)
    need(Path(root,path).resolve()==Path(item.get('source_input_path','')).resolve(),'actual workorder source path required')
    with w.workflow_lock(root),w.request_validation_context() as validation:
        ctx=validate_bridge(root,item);snap=ctx['snapshot'];goal=snap['goal_delivery'];action={**ctx['action'],MARKER:pin}
        rows=events(root,task,BRIDGE_EVENT);old=[x for x in goal.get('approved_actions',[]) if x.get('action_id')==action['action_id']]
        if rows:
            need(len(rows)==1 and rows[0]['details'][BRIDGE_EVENT]==pin and old==[action],'original object workorder is immutable; inspect old key')
            return {'result':'duplicate_ignored','source':pin,'message_sent':False}
        need(not old,'existing action cannot be renewed')
        import department_autonomy as a
        a._owner_message_transport_not_started(root,snap,action);validation.recheck()
        snap['goal_delivery']={**goal,'approved_actions':[*goal.get('approved_actions',[]),action]}
        event=w.append_workflow_event(root,task,snap['current_state'],{BRIDGE_EVENT:pin,'goal_delivery':snap['goal_delivery'],'actual_actor':'operations','frozen_contract_unchanged':True,'external_permission_issued':False})
        w.atomic_write_json(w.snapshot_path(root,task),snap)
    return {'result':'recorded','source':pin,'event_id':event['event_id'],'message_sent':False,'external_permission_issued':False}


def approved_action(root,snapshot,request):
    ctx=registered_bridge(root,snapshot,request);return ctx['action'] if ctx else None


def binding(root,snapshot,request):
    ctx=registered_bridge(root,snapshot,request)
    return (ctx['sender_binding'],{**ctx['pub_binding'],'thread_id':ctx['pub_binding']['task_id']}) if ctx else None


def message_route(root,snapshot,request):
    ctx=registered_bridge(root,snapshot,request)
    if ctx is None:return None
    import department_autonomy as a
    # Common normal message policy still verifies fresh original identity,
    # source, serial intent, queue and one-use effects; source is transport only.
    return {**a.authority(root),'source':ctx['action']['payload'],'report':ctx['registration'],'scope':h.SCOPE,
      'sender_department':'operations','target_department':'publishing','purpose':'original_professional_collaboration_transport_only',
      'registered_execution_message_source':None,'external_permission_issued':False}


def bridge_context(root,pin):
    return registered_bridge(root,{'task_id':h.TASK},{MARKER:pin})


def _received(root,ctx,refs):
    import goal_delivery_runtime as g
    states=g._collaboration_wait_states(root,ctx['snapshot'],only_action_id=ctx['action']['action_id'])
    need(len(states)==1 and states[0].get('received') is True and states[0].get('status') in {'message_received','result_received'} and states[0].get('approved_action',{}).get('payload_sha256')==ctx['action']['payload_sha256'],'real original normal workorder queue/input+nonempty PUB ACK required; old readonly receipt is insufficient')
    actual_receipt=document(root,states[0].get('result_receipt'))
    need(actual_receipt.get('source_kind')=='official_native_queue' and actual_receipt.get('status') in {'message_received','result_received'} and actual_receipt.get('action_id')==ctx['action']['action_id'] and actual_receipt.get('target_thread_id')==ctx['pub_binding']['task_id'],'real original A recipient record independently authenticated by normal queue source')
    current=ctx
    if refs.get('continuation_source') is not None:
        from professional_cms_singlefield_continuation import current_receipt
        current=current_receipt(root,ctx,refs)
        actual_receipt=current['actual_received_record']
    need(actual_receipt.get('recipient_turn_id')==refs['provider_references']['turn_id'],'provider data must be the exact actually received turn; copied input in a later turn is not causal proof')
    page=native(root,refs['PUB_native'],ctx['pub_binding']);tid=refs['provider_references']['turn_id']
    turns=[t for t in page.get('turns',[]) if t.get('id')==tid]
    need(len(turns)==1 and not turns[0].get('error') and turns[0].get('status') in {'inProgress','completed'},'actual same original PUB receipt/read turn required')
    turn=turns[0];body=w.safe_path(root,current['action']['payload']['path']).read_text()
    original_body=w.safe_path(root,ctx['action']['payload']['path']).read_text()
    # SDK may expose direct user content or exact original delegation bytes.
    import xml.etree.ElementTree as ET
    incoming=[]
    for m in turn.get('items',[]):
        if current is not ctx and m.get('type')=='userMessage':
            need(''.join(x.get('text','') for x in m.get('content',[]) if x.get('type')=='text')!=original_body,'old A input cannot be copied into a continuation turn')
        if m.get('type')=='userMessage' and ''.join(x.get('text','') for x in m.get('content',[]) if x.get('type')=='text')==body:incoming.append(m)
        if m.get('type')=='functionCallOutput' and m.get('name')=='send_message_to_thread' and m.get('namespace')=='codex_app':
            value=m.get('output',{});text=value.get('text') if isinstance(value,dict) else value
            if isinstance(text,str):
                try:
                    xml=ET.fromstring(text)
                    if current is not ctx and xml.tag=='codex_delegation':need(xml.findtext('input')!=original_body,'old A delegation cannot be replayed in a continuation turn')
                    if xml.tag=='codex_delegation' and xml.findtext('source_thread_id')==current['sender_binding']['task_id'] and xml.findtext('input')==body:incoming.append(m)
                except ET.ParseError:pass
    need(len(incoming)==1 and incoming[0].get('id')==actual_receipt.get('recipient_message_id'),'exact original queue receiving message ID/body; copied input is not a new receipt')
    call_ids=[refs['provider_references'][k] for k in ('row_call','key_call','same_row_call')]
    order=[m.get('id') for m in turn['items']]
    need(all(x in order for x in call_ids) and order.index(incoming[0]['id'])<min(order.index(x) for x in call_ids),'PUB provider actions must follow the actual exact workorder')
    need(any(m.get('type')=='agentMessage' and m.get('id')==actual_receipt.get('ack_message_id') and m.get('text','').strip() and order.index(incoming[0]['id'])<i<min(order.index(x) for x in call_ids) for i,m in enumerate(turn['items'])),'real nonempty PUB ACK must follow current causal input and precede provider actions')
    return turn


def _static_evidence(root,ctx,item):
    fields={'schema','task_id','scope','bridge_source','source_input_path','PUB_native','provider_references','before','backup','provider_proof','self_check'}
    need(set(item) in (fields,fields|{'continuation_source'}),'exact complete PUB admission source fields required')
    refs=item['provider_references'];need(set(refs)=={'turn_id','row_call','key_call','same_row_call','preview_run_id'} and type(refs['preview_run_id']) is int and refs['preview_run_id']>0,'actual original provider call/run IDs required, not caller completion flags')
    turn=_received(root,ctx,item)
    from professional_cms_singlefield_provider import validate_sql_turn,validate_preview
    proof=document(root,item['provider_proof']);now=dt.datetime.now(dt.timezone.utc)
    # Historical catalog validates immutable provider facts without expiry.
    checked=w._parse_observed_at(proof.get('provider_checked_at'));need(checked and checked<=now,'provider proof observation required')
    if proof.get('sdk_metadata_supplement') is not None:
        from professional_cms_singlefield_provider import validate_supplement_proof
        validate_supplement_proof(root,ctx,refs,proof)
    provider_turn=proof.get('native_turn');need(isinstance(provider_turn,dict) and provider_turn.get('id')==turn.get('id') and provider_turn.get('startedAt')==turn.get('startedAt'), 'actual SDK receipt and full provider native turn must be the same original turn')
    sql=validate_sql_turn(ctx,provider_turn,refs,checked)
    preview=proof['preview'];value=validate_preview(ctx,refs['preview_run_id'],preview['run'],preview['workflow'],preview['ref'],preview['artifact'],preview['docs'],checked)
    policies=[p for p in w.read_jsonl(Path(root)/w.POLICY_DECISIONS) if p.get('task_id')==h.TASK and p.get('action_id')==_preview_action(ctx) and p.get('status')=='allow']
    need(len(policies)==1 and all(policies[0].get(k)==v for k,v in {'department':'publishing','action_class':'site_ci_prepare','scope':h.SCOPE,'workorder_source':item['bridge_source'],'approval_basis':'actual_HQ_original_PUB_zero_write_preview_only','allowed_mode':'dry-run','Save_allowed':False,'CMS_permit_issued':False}.items()),'one real original PUB normal zero-write preview policy, not old readonly or WEB permission')
    policy=policies[0];policy_at=w._parse_observed_at(policy.get('checked_at'));run_at=w._parse_observed_at(preview['run'].get('run_started_at'))
    need(policy_at and run_at and policy_at<=run_at,'actual protected preview must follow original PUB zero-write policy')
    import shlex
    expected=['gh','workflow','run','content-publish-approved.yml','--repo',ctx['web_context']['repository'],'--ref','main','-f','mode=dry-run','-f','target='+ctx['target']['candidateVersion'],'-f','managed_operation=publish','-f','approval_id='+policy['decision_id']]
    dispatches=[]
    for command in turn['items']:
        if command.get('type')!='commandExecution' or command.get('status')!='completed' or command.get('exitCode')!=0 or Path(command.get('cwd','')).resolve()!=Path(root).resolve():continue
        try:
            argv=shlex.split(command.get('command',''))
            if len(argv)==3 and argv[0] in {'/bin/zsh','/bin/bash'} and argv[1] in {'-lc','-c'}:argv=shlex.split(argv[2])
        except (ValueError,TypeError):continue
        if argv==expected:dispatches.append(command)
    need(len(dispatches)==1,'actual original PUB successful exact protected dry-run command with own normal policy required; no caller run flag')
    need(proof.get('row')==sql['row'] and proof.get('observed_at')==sql['observed_at'],'pinned provider proof must equal the real embedded PUB SQL facts')
    row=document(root,item['before']);backup=document(root,item['backup']);t=ctx['target']
    need(row==sql['row'] and backup==row and len(row)==41 and len(t['retainedProjectionFields'])==38 and sum(k.endswith('_ms') for k in row)==11,'actual complete row, independent full backup and all38/MS11 required')
    if row.get('content_zh')==ctx['desired']['content_zh']:
        need(False,'NO_CHANGE: desired effect already present; read public proof, do not admit or issue another permit')
    need(row==ctx['before'] and w.sha256_value(row)==t['baselineFieldsSha256'] and row.get('updated_at')==t['expectedUpdatedAt'] and type(row.get('version')) is int
      and w.sha256_value({k:row[k] for k in t['retainedProjectionFields']})==t['retainedFieldsSha256'], 'baseline/business/metadata drift; exact rebase required, never fill fresh CAS into old source')
    check=document(root,item['self_check']);need(check=={'task_id':h.TASK,'department':'publishing','action_id':t['actionId'],'scope':h.SCOPE,'bridge_source':item['bridge_source'],'provider_proof':item['provider_proof'],'before':item['before'],'desired_fields_sha256':t['desiredFieldsSha256'],'protected38_fields_sha256':t['retainedFieldsSha256'],'rollback_allowed':False,'production_write_allowed':False},'exact request-bound own PUB selfcheck without execution grant')
    # The selfcheck file must be emitted by a successful original PUB command,
    # not accepted merely because it contains a PASS boolean.
    commands=[m for m in turn['items'] if m.get('type')=='commandExecution' and m.get('status')=='completed' and m.get('exitCode')==0 and Path(m.get('cwd','')).resolve()==Path(root).resolve()]
    need(any(item['self_check']['sha256'].encode() in w._completion_execution_output(m) and item['self_check']['path'].encode() in w._completion_execution_output(m) for m in commands),'actual PUB command must name exact selfcheck path/SHA')
    return sql,proof


def validate_admission(root,snapshot,item):
    need(not base_source_validation_active() and item.get('schema')==ADMISSION_SCHEMA and item.get('task_id')==snapshot.get('task_id')==h.TASK and item.get('scope')==h.SCOPE,'same original typed singlefield admission only')
    ctx=bridge_context(root,item['bridge_source']);sql,proof=_static_evidence(root,ctx,item)
    t=ctx['target'];p=ctx['pending'];stable=t['retainedProjectionFields']
    return {'action':{'task_id':h.TASK,'action_id':t['actionId'],'candidate_version':t['candidateVersion'],'action_class':'cms_write','scope':t['scope'],'table':t['table'],'record_id':t['id'],'slug':t['slug'],'changed_fields':['content_zh'],'execution_department':'publishing'},
      'source':p['candidate'],'owner':ctx['snapshot']['goal_delivery']['primary_owner'],'message_owner':'operations','executor':'publishing','channel':'designated-development','business_scope':h.SCOPE,
      'before':{'content_zh':ctx['before']['content_zh']},'desired':ctx['desired'],'protected_fields':{'not_written_fields':sorted(set(ctx['before'])-{'content_zh'}),'stable_business_readback_fields':stable},
      'baseline_pin':p['dated_baseline'],'owner_result':item['provider_proof'],'singlefield_forward_admission':True,'rollback_allowed':False,
      'physical_target':t,'pending_source_registration':ctx['decision']['original_registration'],'pending_source_event_id':ctx['decision']['source_pending_event'],
      'local_issuer_contract':ctx['decision']['original_local_issuer_contract'],'bridge_registration':item['bridge_source'],'actual_PUB_receipt':ctx['action']['action_id'],
      'admission_input':item,'bridge_context':ctx}


def _same_provider(live,stored,refs):
    if not all(live.get(k)==stored.get(k) for k in ('row','observed_at','keys','same_row','preview')):return False
    a,b=live.get('native_turn',{}),stored.get('native_turn',{})
    if not a.get('id') or any(a.get(k)!=b.get(k) for k in ('id','startedAt')):return False
    # Later real commands/completion are allowed; immutable completed provider
    # calls themselves must still be byte-identical. Do not forge old latest.
    for key in ('row_call','key_call','same_row_call'):
        aa=[x for x in a.get('items',[]) if x.get('id')==refs[key]]
        bb=[x for x in b.get('items',[]) if x.get('id')==refs[key]]
        if len(aa)!=1 or aa!=bb:return False
    return True


def verify_admission_for_record(root,snapshot,item):
    ctx=validate_admission(root,snapshot,item)
    from professional_cms_singlefield_provider import read_actual
    live=read_actual(root,ctx['bridge_context'],item['provider_references'],sdk_source=item['PUB_native'])
    recorded=document(root,item['provider_proof'])
    need(_same_provider(live,recorded,item['provider_references']),'actual providers differ from submitted original PUB data; not attested by caller PASS')
    need(0<=(dt.datetime.now(dt.timezone.utc)-w._parse_observed_at(live['observed_at'])).total_seconds()<=300,'fresh original PUB execution data required at admission')
    return ctx


def validate_execution_request(root,snapshot,pin):
    import professional_cms_execution as cms
    req=document(root,pin);sources=[x for x in cms.records(root,snapshot) if x.get('singlefield_forward_admission') and x['registration']==req.get('professional_execution_source')]
    need(len(sources)==1,'one normally registered original PUB execution admission')
    x=sources[0];t=x['physical_target'];item=document(root,x['registration']);ctx=x['bridge_context']
    expected={'task_id':h.TASK,'department':'publishing','action_id':t['actionId'],'action_class':'cms_write','scope':h.SCOPE,'business_scope':h.SCOPE,'physical_scope':t['scope'],'source_project_id':ctx['pub_binding']['project_id'],'operation':'field_patch','object_ids':[t['id']],'table':t['table'],'slug':t['slug'],'changed_fields':['content_zh'],'candidate_version':t['candidateVersion'],'desired':x['desired'],'expected_updated_at':ctx['before']['updated_at'],'expected_version':ctx['before']['version']}
    need(all(req.get(k)==v for k,v in expected.items()) and req.get('sender_department','publishing')=='publishing' and not req.get('authorization_changes') and req.get('rollback') is None and not req.get('execution_instance'),'exact original PUB single forward request only; inverse/EN/MS/other object forbidden')
    need(document(root,req['before'])==ctx['before'],'exact current complete row/raw microsecond CAS/version')
    intent=w.sha256_value({k:v for k,v in req.items() if k not in {'facts','self_check','backup','rollback'}})
    facts=document(root,req['facts']);check=document(root,req['self_check']);backup=document(root,req['backup'])
    identity=('task_id','department','action_id','action_class','scope')
    need(all(all(d.get(k)==req[k] for k in identity) and d.get('intent_sha256')==intent for d in (facts,check,backup)) and check.get('status')=='PASS' and check.get('production_write_allowed') is False and facts.get('current_row')==backup.get('complete_row')==req['before'],'exact PUB own request-bound facts/selfcheck/backup, not free PASS')
    need(isinstance(facts.get('provider_references'),dict) and facts['provider_references'].get('preview_run_id')==item['provider_references']['preview_run_id'] and isinstance(facts.get('PUB_native'),dict) and isinstance(facts.get('provider_proof'),dict),'same protected preview and genuine new PUB execution source required')
    from professional_cms_singlefield_provider import read_actual
    live=read_actual(root,ctx,facts['provider_references'],sdk_source=facts['PUB_native']);proof=document(root,facts['provider_proof'])
    need(_same_provider(live,proof,facts['provider_references']) and live['row']==ctx['before'],'new policy must re-read exact live protected providers and same original keys')
    observed=w._parse_observed_at(live['observed_at']);now=dt.datetime.now(dt.timezone.utc)
    need(observed and facts.get('observed_at')==req.get('observed_at')==live['observed_at'] and 0<=(now-observed).total_seconds()<=300,'fresh actual server observation, no timestamp relabel')
    need(facts.get('continuation_source')==item.get('continuation_source'),'execution facts retain the same actual causal continuation')
    turn=_received(root,ctx,{**item,'PUB_native':facts['PUB_native'],'provider_references':facts['provider_references']})
    summary={**({'continuation_source':facts['continuation_source']} if facts.get('continuation_source') else {}),**{k:req[k] for k in identity},'intent_sha256':intent,'current_row':req['before'],'provider_proof':facts['provider_proof'],'provider_references':facts['provider_references'],'observed_at':facts['observed_at'],'status':'PASS','production_write_allowed':False}
    calls=[m for m in turn['items'] if m.get('id')==facts.get('source_command_id')]
    need(len(calls)==1 and calls[0].get('type')=='commandExecution' and calls[0].get('status')=='completed' and calls[0].get('exitCode')==0 and Path(calls[0].get('cwd','')).resolve()==Path(root).resolve(),'one actual PUB preflight summary command required')
    try:printed=json.loads(w._completion_execution_output(calls[0]))
    except (ValueError,TypeError):need(False,'actual structured PUB preflight command output required')
    need(printed.get('PUB_singlefield_preflight')==summary,'native preflight command must emit the exact request-bound facts; no self-hash/native cycle')
    return {**x,'operation':'publish','request':req,'pin':pin,'authorization':snapshot['goal_delivery']['authorization_pin'],'department':'publishing','preflight':{**{k:req[k] for k in identity},'risk_level':'R2','request':pin,'source_registration':x['registration'],'facts':req['facts'],'self_check':req['self_check'],'backup':req['backup'],'rollback':None}}


def inspect(root,bridge_pin):
    ctx=bridge_context(root,bridge_pin)
    from professional_cms_singlefield_provider import sql_queries
    return {'task_id':h.TASK,'scope':h.SCOPE,'bridge_source':bridge_pin,'PUB_binding':{k:ctx['pub_binding'][k] for k in STABLE},'target':ctx['target'],'SQL_queries':sql_queries(ctx),
      'actual_PUB_data':'DATA_MISSING_UNTIL_ORIGINAL_PUB_RUNS_REAL_CURRENT_QUERIES',
      'zero_write_preview':'Use preview-request normal record and exact site_ci_prepare policy before original protected workflow mode=dry-run; never issue permit at this phase.',
      'preview_action_id':_preview_action(ctx),'preview_request_schema':PREVIEW_SCHEMA,'admission_schema':ADMISSION_SCHEMA,'external_permission_issued':False,'permit_issued':False}


def _preview_action(ctx):return 'PUB-zero-write-preview-'+ctx['action']['action_id']


def record_preview(root,task,path):
    from department_rotation import prohibit_validation_write
    prohibit_validation_write();need(not base_source_validation_active() and task==h.TASK,'normal original PUB preview request only')
    pin=w.file_digest(root,path);item=document(root,pin)
    fields={'schema','task_id','scope','bridge_source','source_input_path','PUB_native','provider_references'}
    need(set(item) in (fields,fields|{'continuation_source'}) and item['schema']==PREVIEW_SCHEMA and item['task_id']==task and item['scope']==h.SCOPE and Path(item['source_input_path']).resolve()==Path(root,path).resolve(),'exact PUB-only zero-write preview request source')
    need(item['provider_references'].get('preview_run_id') is None,'preview preparation cannot invent future run ID')
    with w.workflow_lock(root),w.request_validation_context() as validation:
        ctx=bridge_context(root,item['bridge_source']);_received(root,ctx,item)
        from professional_cms_singlefield_provider import read_actual
        current=read_actual(root,ctx,item['provider_references'],sdk_source=item['PUB_native'])
        need(current['row']==ctx['before'] and current.get('preview') is None,'fresh original baseline needed before zero-write dispatch; never a Save source')
        prior=events(root,task,PREVIEW_EVENT)
        if prior:
            need(len(prior)==1 and prior[0]['details'][PREVIEW_EVENT]==pin,'original preview intent exists; read original run/policy effect before retry')
            return {'result':'duplicate_ignored','source':pin,'action_id':_preview_action(ctx),'permit_issued':False}
        validation.recheck();event=w.append_workflow_event(root,task,ctx['snapshot']['current_state'],{PREVIEW_EVENT:pin,'execution_department':'publishing','zero_write_only':True,'external_permission_issued':False})
    return {'result':'recorded','source':pin,'event_id':event['event_id'],'action_id':_preview_action(ctx),'permit_issued':False,'Save_allowed':False}


def preview_policy(root,requested):
    aid=requested.get('action_id','')
    if not str(aid).startswith('PUB-zero-write-preview-HQ-PUB-singlefield-conditional-'):return None
    need(not base_source_validation_active() and requested.get('task_id')==h.TASK and requested.get('department')=='publishing' and requested.get('action_class')=='site_ci_prepare' and requested.get('scope')==h.SCOPE and requested.get('consume_approval') is True
      and not any(requested.get(k) for k in ('approval_id','target_project_id','target_department')),'one original PUB zero-write-only dispatch policy; no production grant')
    rows=events(root,h.TASK,PREVIEW_EVENT);need(len(rows)==1,'one normally registered current PUB preview source required')
    pin=rows[0]['details'][PREVIEW_EVENT];item=document(root,pin);ctx=bridge_context(root,item['bridge_source'])
    need(requested.get('action_id')==_preview_action(ctx) and requested.get('source_project_id')==ctx['pub_binding']['project_id'] and requested.get('payload_sha256')==pin['sha256'],'exact preview action/source/actor/project only')
    with w.workflow_lock(root),w.request_validation_context() as validation:
        _received(root,ctx,item)
        from professional_cms_singlefield_provider import read_actual
        current=read_actual(root,ctx,item['provider_references'],sdk_source=item['PUB_native'])
        need(current['row']==ctx['before'] and current.get('preview') is None,'fresh exact current data before original protected zero-write workflow')
        need(w._chat_binding_healthy(w.department_registry(root)['publishing']['chat_binding'],verification_ttl_hours=26),'original PUB healthy fixed identity required; use normal actual health refresh')
        key=('task_id','department','action_id','action_class','scope')
        need(not any(p.get('status')=='allow' and all(p.get(k)==requested.get(k) for k in key) for p in w.read_jsonl(Path(root)/w.POLICY_DECISIONS)), 'original zero-write policy already issued/UNKNOWN; inspect original run, never redispatch blindly')
        validation.recheck();now=w.utc_timestamp()
        value={**{k:requested[k] for k in key},'source_project_id':requested['source_project_id'],'payload_sha256':pin['sha256'],'status':'allow','decision_id':'pol-'+w.sha256_value([requested,now])[:20],
          'approval_basis':'actual_HQ_original_PUB_zero_write_preview_only','approval_id':'','approval_status':'not_used','checked_at':now,'single_use':True,
          'allowed_workflow':'.github/workflows/content-publish-approved.yml','allowed_mode':'dry-run','target':ctx['target']['candidateVersion'],'operation':'publish','head_sha':ctx['web_context']['commit'],
          'workorder_source':item['bridge_source'],'HQ_decision':document(root,item['bridge_source'])['HQ_decision'],
          'actual_action_allowed':True,'Save_allowed':False,'CMS_permit_issued':False,'external_permission_issued':False,'reason':['original PUB exact protected zero-write preview only; normal Save gates remain']}
        w.append_jsonl_locked(Path(root)/w.POLICY_DECISIONS,value)
    return value,[Path(root)/w.POLICY_DECISIONS]


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('command',choices=['inspect','observe-read','provider-read','validate-admission']);parser.add_argument('--bridge-source');parser.add_argument('--input');parser.add_argument('--output')
    args=parser.parse_args();root=Path(__file__).resolve().parents[1]
    try:
        with w.request_validation_context():
            if args.command=='validate-admission':
                item=document(root,w.file_digest(root,args.input));value=verify_admission_for_record(root,h._snapshot(root),item);value={'status':'VERIFIED_NOT_REGISTERED','task_id':h.TASK,'action_id':value['action']['action_id'],'permit_issued':False}
            else:
                pin=w.file_digest(root,args.bridge_source)
                if args.command=='inspect':value=inspect(root,pin)
                else:
                    bundle=document(root,w.file_digest(root,args.input));ctx=bridge_context(root,pin);need(bundle.get('bridge_source')==pin,'same exact bridge source')
                    _received(root,ctx,bundle)
                    from professional_cms_singlefield_provider import read_actual, observe_actual
                    reader=observe_actual if args.command=='observe-read' else read_actual
                    value=reader(root,ctx,bundle['provider_references'],sdk_source=bundle['PUB_native']);value['provider_checked_at']=dt.datetime.now(dt.timezone.utc).isoformat()
            if args.output:
                out=w.safe_path(root,args.output);need(not out.exists(),'preserve existing actual evidence/output')
                w.atomic_write_json(out,value);value={'result':'actual_readback_saved_not_permission','source':w.file_digest(root,args.output),'permit_issued':False}
        print(json.dumps(value,ensure_ascii=False,indent=2))
    except (w.WorkflowError,ValueError,KeyError,OSError) as error:
        diagnostic=getattr(error,'provider_diagnostic',None)
        if isinstance(diagnostic,dict) and args.output:
            original=w.safe_path(root,args.output)
            out=original.with_name(original.stem+'-PROVIDER-FAILURE.json')
            if not out.exists():
                w.atomic_write_json(out,{'schema':'original-PUB-provider-failure-diagnostic/v1','error':str(error),'actual_provider_diagnostic':diagnostic,'provider_PASS':False,'permit_issued':False})
                parser.exit(1,json.dumps({'status':'PROVIDER_FAILED_DIAGNOSTIC_SAVED','error':str(error),'diagnostic':w.file_digest(root,str(out.relative_to(root))),'provider_PASS':False,'permit_issued':False},ensure_ascii=False)+'\n')
        parser.exit(1,str(error)+'\n')

if __name__=='__main__':main()
