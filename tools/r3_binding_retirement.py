"""Normal own terminal R3 binding retirement; never authorizes deployment.

Original issuer, carrier history, fresh actual WEB native facts, and a distinct
normal single-use cleanup preflight/policy are all required before any write.
"""
from pathlib import Path
from datetime import datetime,timezone
import argparse,json,os,re
import goal_delivery_runtime as g
import r3_known_zero_recovery as recovery
import workflow_control as w
import department_autonomy as a
import professional_web_execution as web
import r3_platform_binding_transport as carrier
from r3_binding_retirement_plan import exact_retirement_plan

def need(ok,reason): carrier.need(ok,'terminal retirement: '+reason)

def safe_guard_cause(error):
    """Keep safe original guard text, never locals, variable values or secrets."""
    cause=error.__cause__
    value={'error_class':type(error).__name__,'cause_class':type(cause).__name__ if cause else 'NOT_RECORDED',
           'cause_category':'NOT_RECORDED' if cause is None else 'NORMAL_GUARD_REJECTED'}
    if isinstance(cause,w.WorkflowError):
        message=str(cause)
        if (message.startswith('autonomous delivery: ') and re.fullmatch(r'[A-Za-z0-9 ,.:;_()/-]{1,240}',message)
                and not re.search(r'\b[A-Za-z0-9_-]{32,}\b',message)
                and not re.search(r'\b(?:token|secret|password|cookie|credential|bearer|api[ _-]?key)\b',message,re.I)):
            value['guard_message']=message
        else:value['guard_message']='SUPPRESSED_UNSAFE_OR_UNSTRUCTURED'
    elif isinstance(cause,OSError):
        value['cause_category']='FILESYSTEM_OR_OS_ERROR'
        if type(cause.errno) is int:value['errno']=cause.errno
    return value

def retirement_desired(binding):
    return {'repository':binding['repository'],'variable':carrier.VARIABLE,'approval_id':binding['approvalId'],
            'run_id':str(binding['runId']),'run_attempt':binding['runAttempt'],
            'binding_sha256':carrier.digest(binding),'operation':'retire_exact_terminal_binding'}

def absence_result(value):
    if value.get('state')=='NO_EXACT_BINDING_OBSERVED_NOT_A_WRITE_PROOF' and value.get('read_only') is True and value.get('own_binding_counts')=={'repository':0,'environment':0}:
        return {'status':'CURRENT_OWN_BINDING_ABSENT_NO_RETIREMENT_POLICY','actual_action_allowed':False,
                'historical_zero_claimed':False,'new_write':False}
    return None

def validate_observation(root,ctx,state):
    """Authenticate the original issuer and fresh terminal observations only."""
    proof=state.get('r3_retirement',{})
    need(set(proof)=={'approval_id','native','commands'} and set(proof['commands'])=={'run','status'},
         'complete bounded terminal run and own binding status proof')
    original,row,issued,policy=original_chain(root,ctx['task'],proof['approval_id'])
    fields=('task','role','owner','authorization','contract','decision','registration','commit','base',
            'branch','worktree','edge_scope','prefix','r3_replacement_source')
    need(all(original.get(k)==ctx.get(k) for k in fields),'same actual immutable issuer source, actor and parent')
    binding=row['platform_binding'];page=g._native_document(root,web.code_pin(root,proof['native']))
    need(all(page.get('thread',{}).get(k)==ctx['binding'][v] for k,v in {'id':'thread_id','title':'title','cwd':'cwd'}.items()),
         'actual original WEB terminal native identity')
    selected={};turn=None
    for key,cid in proof['commands'].items():
        pairs=[(t,m) for t in page.get('turns',[]) for m in t.get('items',[]) if m.get('id')==cid]
        need(len(pairs)==1 and (turn is None or turn['id']==pairs[0][0]['id']),'same single actual WEB proof turn')
        turn,command=pairs[0]
        need(command.get('type')=='commandExecution' and command.get('status')=='completed' and command.get('exitCode')==0
             and Path(command.get('cwd','')).resolve()==Path(ctx['worktree']).resolve(),'successful original worktree terminal read')
        selected[key]=command
    actual=recovery.official_web_turn(root,ctx['binding'],turn['id'])
    for command in selected.values():
        items=[m for m in actual.get('items',[]) if m.get('id')==command['id']]
        need(len(items)==1 and all(items[0].get(k)==command.get(k) for k in ('id','type','status','exitCode','cwd','command'))
             and w._completion_execution_output(command).decode()==items[0].get('aggregatedOutput')
             and type(items[0].get('startedAtMs')) is int and type(items[0].get('completedAtMs')) is int
             and turn['startedAt']*1000<=items[0]['startedAtMs']<=items[0]['completedAtMs']
             and 0<=carrier.timestamp().timestamp()-items[0]['startedAtMs']/1000<=300,
             'fresh official actual completed terminal read and full output')
    run=web._approved_ads_gh_response(ctx,state,turn,selected['run'],
                  'repos/'+ctx['repository']+'/actions/runs/'+str(binding['runId']))
    need(str(run.get('id'))==str(binding['runId']) and run.get('run_attempt')==1
         and run.get('status')=='completed' and run.get('conclusion')=='success'
         and run.get('head_sha')==binding['expectedSha']==state.get('main_sha')
         and run.get('path')==web.R3 and run.get('event')=='workflow_dispatch'
         and run.get('head_branch')=='main' and run.get('repository',{}).get('id')==binding['repositoryId']
         and run.get('repository',{}).get('full_name')==ctx['repository']
         and run.get('actor',{}).get('id')==state.get('actor',{}).get('id'),
         'own actual successful first workflow run and exact main/actor only')
    recovery._normal_status_argv(root,ctx,selected['status']['command'],binding['approvalId'])
    value=json.loads(web.native(root,ctx,proof['native'],proof['commands']['status']));facts=value.get('facts',{})
    counts=value.get('own_binding_counts',{})
    need(value.get('read_only') is True and value.get('local_approval_status')==row['status']=='consumed'
         and value.get('state') in {'EXACT_REMOTE_BINDING_PRESENT','NO_EXACT_BINDING_OBSERVED_NOT_A_WRITE_PROOF'}
         and counts in ({'repository':0,'environment':1},{'repository':1,'environment':0},{'repository':0,'environment':0})
         and ((value.get('state')=='NO_EXACT_BINDING_OBSERVED_NOT_A_WRITE_PROOF' and counts=={'repository':0,'environment':0})
              or (value.get('state')=='EXACT_REMOTE_BINDING_PRESENT' and value.get('effective_level') in ('repository','environment')
                  and counts[value['effective_level']]==1 and sum(counts.values())==1))
         and str(facts.get('run_id'))==str(binding['runId']) and facts.get('run_attempt')==1
         and facts.get('head')==binding['expectedSha'] and facts.get('repository')==ctx['repository']
         and facts.get('actor')==state.get('actor') and facts.get('run_status')=='completed'
         and facts.get('run_conclusion')=='success' and facts.get('environment')==carrier.ENV,
         'fresh normal own consumed binding status and successful terminal, never unknown past API inference')
    need(policy is not None,'actual consumed own Edge policy is prerequisite, not borrowed cleanup authority')
    return binding

def original_chain(root,task,approval):
    ctx,row,issued=carrier.context(root,task,approval,effect=False)
    binding=row['platform_binding'];carrier.validate_binding(binding,current=False,own=True)
    expired=w._parse_observed_at(binding['expiresAt'])<=carrier.timestamp()
    need(row.get('status')=='consumed' or (row.get('status')=='active' and expired),
         'only consumed issuer or actually expired unused issuer')
    policies=[p for p in w.read_jsonl(Path(root)/w.POLICY_DECISIONS) if p.get('task_id')==task
              and p.get('action_id')==binding['actionId'] and p.get('status')=='allow']
    need(len(policies)==(1 if row['status']=='consumed' else 0),'original consumed edge policy or no policy for expired unused reference')
    p=policies[0] if policies else None;envelope=a.document(root,row['source_preflight'])
    need(p is None or (p.get('department')==ctx['role'] and p.get('action_class')=='site_publish'
         and p.get('scope')==binding['scope'] and p.get('consume_approval') is True
         and p.get('approval_status')=='consumed_for_original_exact_autonomous_action'
         and p.get('exact_request')==envelope.get('request') and p.get('source_preflight')==row['source_preflight']
         and p.get('payload_sha256')==envelope['request']['sha256']), 'exact original consumed policy/request, not a cleanup authorization')
    directory=Path(root)/'backups'/task/'R3-platform-binding-transport'/approval
    paths=[directory/x for x in ('intent.json','attempt.json','boundary.jsonl','readback.jsonl')]
    need(all(x.is_file() and not x.is_symlink() for x in paths),'complete original carrier history')
    intent=w.read_json(paths[0]);attempt=w.read_json(paths[1]);boundary=w.read_jsonl(paths[2]);reads=w.read_jsonl(paths[3])
    need(intent.get('binding')==binding and attempt.get('state')=='mutation_intent_durable'
         and attempt.get('attempts')==1 and len(boundary)==len(reads)==1
         and boundary[0].get('schema')=='original-R3-carrier-call-boundary/v1'
         and boundary[0].get('state')=='PROVIDER_CALL_STARTED' and boundary[0].get('approval_id')==approval
         and boundary[0].get('binding_sha256')==carrier.digest(binding)
         and boundary[0].get('attempt_sha256')==carrier._file_hash(paths[1])
         and boundary[0].get('intent_sha256')==carrier._file_hash(paths[0])
         and reads[0].get('approval_id')==approval and reads[0].get('effective_level')==intent.get('target_level')
         and reads[0].get('state')=='TRANSPORTED_AND_READ_BACK' and reads[0].get('new_write') is True,
         'one genuine transported carrier result; unknown histories cannot be relabelled')
    times=[w._parse_observed_at(x) for x in (binding['issuedAt'],intent.get('at'),attempt.get('at'),
                                             boundary[0].get('at'),reads[0].get('at'))]
    times.append(w._parse_observed_at(row.get('consumed_at')) if p else carrier.timestamp())
    need(all(times) and all(x<=y for x,y in zip(times,times[1:])), 'original issuer/carrier/policy chronology')
    level,after,duplicate=carrier.proposal(intent.get('before'),binding,times[1])
    need(not duplicate and level==intent.get('target_level') and carrier.digest(after)==intent.get('after_sha256'),
         'original exact whole-value carrier intent')
    return ctx,row,issued,p

def retirement_policy(root,task,ctx,binding,request_path):
    pin=w.file_digest(root,request_path);request=a.document(root,pin)
    actual,op,state=web.validate_request(root,request)
    need(op=='r3_retire' and actual['role']==ctx['role'] and actual['registration']==ctx['registration']
         and state.get('r3_retirement',{}).get('approval_id')==binding['approvalId'], 'normal authenticated own retirement request')
    expected=retirement_desired(binding)
    need(request.get('desired')==expected and request.get('scope')==binding['scope']
         and request.get('action_id')!=binding['actionId'], 'distinct exact own-row cleanup action and scope')
    item,current,preflight,_=web.preflight(root,task,request['action_id'],request['action_class'],request['scope'],ctx['role'])
    need(current==request and item.get('request')==pin, 'exact latest original WEB retirement preflight')
    key=w.sha256_value([task,ctx['role'],request['action_id'],request['action_class'],request['scope']])
    policies=[p for p in w.read_jsonl(Path(root)/w.POLICY_DECISIONS) if p.get('task_id')==task and p.get('action_id')==request['action_id'] and p.get('status')=='allow']
    need(len(policies)==1 and policies[0].get('actual_action_allowed') is True
         and policies[0].get('consume_approval') is True and policies[0].get('approval_status')=='consumed_for_original_exact_autonomous_action'
         and policies[0].get('department')==ctx['role'] and policies[0].get('action_class')==request['action_class']
         and policies[0].get('scope')==request['scope'] and policies[0].get('exact_request')==pin
         and policies[0].get('source_preflight')==preflight and policies[0].get('autonomous_action_key')==key,
         'one distinct consumed exact retirement policy; never borrow edge/install policy')
    return request,policies[0],pin

def terminal_now(api,ctx,binding,request):
    facts=carrier.platform_facts(api,ctx,binding['runId'],request,pending=False)
    need(facts['run_status']=='completed' and facts['run_conclusion']=='success','own run must be actually completed and successful')
    main=api.call('GET','repos/'+ctx['repository']+'/git/ref/heads/main')
    need(main.get('object',{}).get('sha')==binding['expectedSha'],'original current main still matches; no stale target')
    return facts

def preapi_history(root,ctx,binding,original,original_pin,packet,turn_id):
    """Authenticate the single original pre-API rejection; never infer its cause."""
    approval=binding['approvalId'];directory=Path(root)/'backups'/ctx['task']/'R3-terminal-binding-retirement'/approval
    names=('intent.json','attempt.json','boundary.jsonl','readback.jsonl')
    paths=[directory/n for n in names]
    need(all(p.is_file() and not p.is_symlink() for p in paths),'complete original immutable retirement history required')
    pins={}
    for p in paths:pins[p.name]=w.file_digest(root,str(p.relative_to(root)))
    supplied={Path(x['path']).name:x for x in packet.get('evidence_pins',[]) if isinstance(x,dict) and Path(x.get('path','')).parent==directory}
    need(set(supplied)==set(names) and all(supplied[n].get('sha256')==pins[n]['sha256'] and supplied[n].get('size')==pins[n]['size'] for n in names), 'original historical source pins unchanged')
    intent=w.read_json(paths[0]);attempt=w.read_json(paths[1]);boundaries=w.read_jsonl(paths[2]);reads=w.read_jsonl(paths[3])
    need(intent.get('schema')=='original-WEB-terminal-binding-retirement-intent/v1' and intent.get('binding')==binding
         and intent.get('cleanup_request')==original_pin and attempt.get('state')=='RETIRE_INTENT_DURABLE_NO_REPLAY'
         and len(boundaries)==len(reads)==1 and boundaries[0].get('schema')=='original-R3-carrier-call-boundary/v1'
         and boundaries[0].get('state')=='PRE_API_GUARD_REJECTED' and boundaries[0].get('approval_id')==approval
         and boundaries[0].get('attempt_sha256')==pins['attempt.json']['sha256'] and boundaries[0].get('intent_sha256')==pins['intent.json']['sha256']
         and boundaries[0].get('binding_sha256')==carrier.digest(binding)
         and reads[0].get('state')=='PRE_API_REJECTED_ATTEMPT_RETAINED_NO_REPLAY'
         and reads[0].get('new_write') is False and reads[0].get('approval_id')==approval,
         'one original PRE_API rejection, no provider-start or unknown')
    times=[w._parse_observed_at(x) for x in (intent.get('at'),attempt.get('at'),boundaries[0].get('at'),reads[0].get('at'))]
    need(all(times) and all(x<=y for x,y in zip(times,times[1:])), 'original durable intent/attempt/boundary/readback chronology')
    original_plan=exact_retirement_plan(intent.get('before'),binding)
    need(original_plan.get('state')=='EXACT_OWN_ROW_PLAN_ONLY' and original_plan.get('effective_level')==intent.get('effective_level')
         and carrier.digest(original_plan['after_entries'])==intent.get('after_sha256')
         and intent.get('cleanup_policy')==packet.get('independent_cleanup_policy')
         and packet.get('actual_result',{}).get('state')==reads[0]['state']
         and packet.get('actual_result',{}).get('new_write') is False
         and packet.get('actual_result',{}).get('approval_id')==approval, 'unchanged exact original own-row proposal and rejection')
    rawpins=[p for p in packet.get('evidence_pins',[]) if isinstance(p,dict) and str(p.get('path','')).endswith('/refusal-raw-turns-list.json')]
    need(len(rawpins)==1,'one original full native failure source')
    rawpin={**rawpins[0],'path':str(Path(rawpins[0]['path']).relative_to(root))};raw=a.document(root,rawpin)
    rows=[(t,m) for t in raw.get('data',[]) for m in t.get('items',[]) if m.get('id')==packet.get('failed_native_command')]
    need(len(rows)==1 and rows[0][0].get('id')==turn_id,'one original WEB failure command')
    snap,cmd=rows[0];actual=recovery.official_web_turn(root,ctx['binding'],turn_id,_registration_event_time=attempt['at'])
    matches=[m for m in actual.get('items',[]) if m.get('id')==cmd.get('id')]
    need(len(matches)==1 and all(matches[0].get(k)==cmd.get(k) for k in ('id','type','status','exitCode','cwd','command','aggregatedOutput','startedAtMs','completedAtMs'))
         and cmd.get('type')=='commandExecution' and cmd.get('status')=='failed' and cmd.get('exitCode')==1
         and Path(cmd.get('cwd','')).resolve()==Path(ctx['worktree']).resolve()
         and type(cmd.get('startedAtMs')) is int and type(cmd.get('completedAtMs')) is int
         and cmd['startedAtMs']<=times[1].timestamp()*1000<=times[3].timestamp()*1000<=cmd['completedAtMs'],
         'actual full original WEB command and durable rejection occurred inside it')
    result={'state':'PRE_API_REJECTED_ATTEMPT_RETAINED_NO_REPLAY','new_write':False,'approval_id':approval}
    output=cmd.get('aggregatedOutput','');web._output_document(output.encode(),result)
    need(packet.get('original_pre_api_exception_detail')=='NOT_RECORDED_BY_NORMAL_EXECUTOR; no retrospective invention',
         'original exception remains NOT_RECORDED')
    return {'pins':pins,'original_policy':intent.get('cleanup_policy'),'original_result':result,
            'original_exception':'NOT_RECORDED','failure_command':cmd['id'],'failure_turn':turn_id,
            'original_completed_at_ms':cmd['completedAtMs']}

def fresh_retirement_continuation(root,task,approval,original,continuation_path):
    doc=a.document(root,w.file_digest(root,continuation_path))
    need(set(doc)=={'schema','original_request','fresh_request','failure_input','failure_turn'}
         and doc.get('schema')=='original-WEB-retirement-preapi-fresh-continuation/v1', 'exact continuation source shape')
    need(isinstance(doc.get('failure_input'),dict)
         and doc['failure_input'].get('sha256')=='2be4b904b756e2b005d43300889c72a76b5e9efb1ab44f683b442ef15178de87'
         and doc['failure_input'].get('size')==15133
         and doc.get('failure_turn')=='example-native-28e80615693adaf2'
         and doc.get('original_request',{}).get('sha256')=='754e5ec174a272c4ddf9e1ae71a5ea2b3d6b6e3531524485bebe2fb1f4387e10',
         'only the specifically authenticated original v15 source, request and WEB turn')
    old=a.document(root,doc['original_request']);fresh=a.document(root,doc['fresh_request'])
    need(old==original and old.get('task_id')==task and old.get('operation')=='r3_retire','exact immutable original cleanup request')
    ctx,row,issued,edge=original_chain(root,task,approval);binding=row['platform_binding']
    packet=web.external(root,doc['failure_input'],ctx['binding']);rawpin=packet.get('request_pin',{})
    need(packet.get('schema')=='original-WEB-terminal-binding-cleanup-pre-api-safe-stop/v15'
         and str(Path(rawpin.get('path','')).relative_to(root))==doc['original_request']['path']
         and rawpin.get('sha256')==doc['original_request']['sha256'] and rawpin.get('size')==doc['original_request']['size']
         and packet.get('reference')==approval and str(packet.get('run_id'))==str(binding['runId'])
         and packet.get('turn')==doc['failure_turn']
         and packet.get('failed_native_command')=='exec-b4720011-4fee-413b-bda1-1c48a5dc0207', 'exact original own pre-API source')
    history=preapi_history(root,ctx,binding,old,doc['original_request'],packet,doc['failure_turn'])
    policies=[p for p in w.read_jsonl(Path(root)/w.POLICY_DECISIONS) if p.get('decision_id')==history['original_policy']]
    need(len(policies)==1,'one original exact consumed cleanup policy');policy=policies[0]
    key=w.sha256_value([task,ctx['role'],old['action_id'],old['action_class'],old['scope']])
    need(policy.get('status')=='allow' and policy.get('actual_action_allowed') is True and policy.get('consume_approval') is True
         and policy.get('approval_status')=='consumed_for_original_exact_autonomous_action' and policy.get('department')==ctx['role']
         and policy.get('task_id')==task and policy.get('action_id')==old['action_id'] and policy.get('action_class')==old['action_class']
         and policy.get('scope')==old['scope'] and policy.get('exact_request')==doc['original_request']
         and policy.get('autonomous_action_key')==key and policy.get('payload_sha256')==doc['original_request']['sha256']
         and policy.get('decision_id')==packet.get('independent_cleanup_policy')
         and policy.get('original_authority')==ctx.get('authorization')
         and policy.get('original_production_authority')==ctx.get('contract')
         and policy.get('original_professional_source')==ctx.get('decision'), 'same exact consumed cleanup policy, never new consumption')
    mutable={'state','observed_at','facts','self_check','backup','rollback'}
    need(set(old)==set(fresh) and all(old.get(k)==fresh.get(k) for k in set(old)-mutable)
         and old.get('desired')==fresh.get('desired')==retirement_desired(binding), 'same original action/source/authority and exact desired effect')
    before=old.get('state',{});after=fresh.get('state',{})
    fixed=('candidate_commit','candidate_parent','candidate_base','candidate_tree','branch','worktree','repository','repository_id','actor','main_sha','main_local_sha','remote_main_sha','project_ref','function','merged_pull_request','r3_replacement_source')
    need(all(before.get(k)==after.get(k) for k in fixed)
         and before.get('r3_retirement',{}).get('approval_id')==after.get('r3_retirement',{}).get('approval_id')==approval,
         'same original candidate, main, actor, parent and own reference')
    current,op,state=web.validate_request(root,fresh)
    need(op=='r3_retire' and current.get('registration')==ctx.get('registration') and current.get('role')==ctx['role'],
         'complete fresh normal WEB facts/selfcheck/backup/rollback validator')
    observed=w._parse_observed_at(fresh.get('observed_at'))
    need(observed and observed.timestamp()*1000>history['original_completed_at_ms'],'fresh evidence must follow original rejection')
    from approved_ads_web_source import records as approved_ads_records
    ads=approved_ads_records(root,task);holder=ads[0]['task'] if len(ads)==1 else task
    pre=[e for e in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS,where={'task_id':holder})
         if e.get('task_id')==holder and e.get('details',{}).get('professional_WEB_preflight',{}).get('action_id')==old['action_id']]
    need(pre and pre[-1].get('event_id')==packet.get('preflight_event')
         and pre[-1]['details']['professional_WEB_preflight'].get('request')==doc['original_request']
         and pre[-1]['details']['professional_WEB_preflight'].get('input')==policy.get('source_preflight')
         and a.document(root,policy['source_preflight']).get('request')==doc['original_request'], 'unchanged latest original preflight; no replacement registration')
    return ctx,row,issued,edge,fresh,policy,doc,history

def continuation_boundary(directory,state,binding,attempt_path):
    directory=Path(directory);intent=directory/'continuation-intent.json'
    event={'schema':'original-R3-retirement-continuation-boundary/v1','state':state,'approval_id':binding['approvalId'],
           'binding_sha256':carrier.digest(binding),'attempt_sha256':carrier._file_hash(attempt_path),
           'intent_sha256':carrier._file_hash(intent),'at':carrier.timestamp().isoformat()}
    w.append_jsonl_locked(directory/'continuation-boundary.jsonl',event)
    fd=os.open(directory,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)

def retire(root,task,approval,request_path,continuation_path=None):
    if continuation_path:
        original_pin=w.file_digest(root,request_path);original=a.document(root,original_pin)
        ctx,row,issued,edge_policy,request,policy,doc,history=fresh_retirement_continuation(root,task,approval,original,continuation_path)
        need(doc['original_request']==original_pin,'exact originally consumed request path and bytes')
        pin=original_pin
    else:
        ctx,row,issued,edge_policy=original_chain(root,task,approval)
        request,policy,pin=retirement_policy(root,task,ctx,row['platform_binding'],request_path)
    binding=row['platform_binding']
    need(Path.cwd().resolve()==Path(ctx['worktree']).resolve(),'only original WEB worktree')
    directory=Path(root)/'backups'/task/'R3-terminal-binding-retirement'/approval
    with carrier.serialized(root,ctx):
        attempt=directory/('continuation-attempt.json' if continuation_path else 'attempt.json')
        names=('continuation-intent.json','continuation-attempt.json','continuation-boundary.jsonl','continuation-readback.jsonl',
               'retry_intent.json','retry_attempt.json','retry_boundary.jsonl','retry_readback.jsonl') if continuation_path else ('intent.json','attempt.json','boundary.jsonl','readback.jsonl')
        need(not any((directory/n).exists() or (directory/n).is_symlink() for n in names),
             'prior retirement/continuation effect: inspect original key, never replay')
        api=carrier.GitHub(ctx);facts=terminal_now(api,ctx,binding,request);before=carrier.levels(api,ctx)
        plan=exact_retirement_plan(before,binding)
        if not plan['write'] and plan['state'].startswith('NO_OWN_ROW'):
            return {'state':plan['state'],'new_write':False,'historical_zero_claimed':False,'facts':facts}
        need(plan['state']=='EXACT_OWN_ROW_PLAN_ONLY','one own row required')
        need(carrier.levels(api,ctx)==before,'both complete raw hashes and timestamps stable before intent')
        need(terminal_now(api,ctx,binding,request)==facts,'terminal run and identity stable before intent')
        directory.mkdir(parents=True,exist_ok=True)
        intent={'schema':'original-WEB-terminal-binding-retirement-continuation-intent/v1' if continuation_path else 'original-WEB-terminal-binding-retirement-intent/v1','binding':binding,'before':before,
                'effective_level':plan['effective_level'],'after_sha256':carrier.digest(plan['after_entries']),
                'cleanup_request':pin,'cleanup_policy':policy['decision_id'],'edge_policy':edge_policy['decision_id'] if edge_policy else None,
                'at':carrier.timestamp().isoformat(),'server_CAS_available':False}
        if continuation_path:intent.update(continuation_source=w.file_digest(root,continuation_path),fresh_request=doc['fresh_request'],original_history=history)
        intentpath=directory/('continuation-intent.json' if continuation_path else 'intent.json');need(not intentpath.exists() and not intentpath.is_symlink(),'previous retirement intent needs effect inspection')
        with intentpath.open('x') as f:json.dump(intent,f,ensure_ascii=False,indent=2);f.flush();os.fsync(f.fileno())
        with attempt.open('x') as f:json.dump({'state':'RETIRE_INTENT_DURABLE_NO_REPLAY','at':carrier.timestamp().isoformat()},f);f.flush();os.fsync(f.fileno())
        for folder in (directory,directory.parent):
            fd=os.open(folder,os.O_RDONLY|os.O_DIRECTORY)
            try:os.fsync(fd)
            finally:os.close(fd)
        def before_write():
            current=w.effective_approvals(root).get(approval);need(current==row,'original issuer ledger changed')
            carrier.require_active_stage(root,ctx,task)
            checked_ctx,checked_row,checked_issued,checked_edge=original_chain(root,task,approval)
            need(checked_ctx==ctx and checked_row==row and checked_issued==issued and checked_edge==edge_policy,
                 'immutable original issuer, preflight, policy and carrier history must still match')
            if continuation_path:
                _,_,_,_,latest,latest_policy,latest_doc,latest_history=fresh_retirement_continuation(root,task,approval,original,continuation_path)
                need(latest_doc==doc and latest_history==history,'same immutable original rejection and fresh continuation')
                latest_pin=doc['original_request']
            else:latest,latest_policy,latest_pin=retirement_policy(root,task,ctx,binding,request_path)
            need(latest==request and latest_policy==policy and latest_pin==pin,'same cleanup policy and request')
            web.intent(root,request)
            need(terminal_now(api,ctx,binding,request)==facts and carrier.levels(api,ctx)==before,
                 'fresh actual terminal and both whole variable values/timestamps required at write')
            validation=w._VALIDATION_CONTEXT.get()
            if validation is not None:validation.recheck()
        api.before_write=before_write
        api.boundary=(lambda state:continuation_boundary(directory,state,binding,attempt)) if continuation_path else (lambda state:carrier._durable_boundary(directory,state,binding,attempt))
        level=plan['effective_level'];target=before[level]
        try:
            api.call('PATCH',target['path']+'/'+carrier.VARIABLE,{'name':carrier.VARIABLE,'value':json.dumps(plan['after_entries'],ensure_ascii=False,separators=(',',':'))})
            actual=carrier.levels(api,ctx);other='repository' if level=='environment' else 'environment'
            need(actual[other]==before[other] and actual[level]['exists'] and actual[level]['entries']==plan['after_entries'],
                 'complete two-level exact readback; ambiguity is UNKNOWN')
            result={'state':'OWN_TERMINAL_BINDING_RETIRED_AND_READ_BACK','new_write':True,'approval_id':approval,'facts':facts,
                    'server_CAS_available':False,'external_edit_race_not_atomic':True}
        except carrier.PreAPIGuardRejected as error:
            result={'state':'PRE_API_REJECTED_ATTEMPT_RETAINED_NO_REPLAY','new_write':False,'approval_id':approval,
                    **safe_guard_cause(error)}
        except Exception as error:
            result={'state':'RETIREMENT_EFFECT_UNKNOWN_NO_REPLAY','new_write':'UNKNOWN','approval_id':approval,'error_class':type(error).__name__}
        w.append_jsonl_locked(directory/('continuation-readback.jsonl' if continuation_path else 'readback.jsonl'),{**result,'at':carrier.timestamp().isoformat()})
        return result

if __name__=='__main__':
    parser=argparse.ArgumentParser(description='Normal original WEB terminal own binding retirement.')
    parser.add_argument('command',choices=['retire']);parser.add_argument('--task-id',required=True)
    parser.add_argument('--approval-id',required=True);parser.add_argument('--request',required=True)
    parser.add_argument('--continuation')
    args=parser.parse_args();root=Path(__file__).resolve().parents[1]
    with w.request_validation_context():result=retire(root,args.task_id,args.approval_id,args.request,args.continuation)
    print(json.dumps(result,ensure_ascii=False,indent=2))
