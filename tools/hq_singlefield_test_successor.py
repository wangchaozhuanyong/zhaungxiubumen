"""Append-only reviewed test-only child of the original single-field code stage.

Data-derived successor; no new human, production permission, CMS grant, status
or effect. Every read revalidates actual decision/native, original admission,
completed original WEB input/result and immutable Git. Used keys remain readable.
"""
from pathlib import Path
import datetime as dt
import hashlib
import re
import xml.etree.ElementTree as ET
import workflow_control as w
import hq_bounded_web_admission as h

SCHEMA = 'HQ-singlefield-reviewed-test-successor/v1'
KIND = 'actual_HQ_reviewed_singlefield_test_successor_v1'
EVENT = 'HQ_singlefield_reviewed_test_successor'
MARKER = 'hq_singlefield_test_successor_source'
OPS = ('git_push', 'official_ci', 'merge', 'r3_dispatch', 'edge_deploy')
TEST_PATH = 'src/lib/managedContentPublishWorkflow.test.ts'
KEYS = {'schema','task_id','scope','base_registration','owner_delegation','hq_decision','hq_native',
        'WEB_completed_native','WEB_result','WEB_successor','WEB_next_input','request','recovery_runbook','source_input_path'}


def need(ok, reason):
    if not ok: raise w.WorkflowError('reviewed singlefield test successor: '+reason)


def document(root, pin):
    need(isinstance(pin,dict) and set(pin)=={'path','sha256','size'}, 'exact immutable source pin required')
    path=Path(root,pin['path']).resolve()
    need(path.is_relative_to(Path(root).resolve()), 'source belongs to the original coordination project')
    return h.document(root,{**pin,'path':str(path.relative_to(Path(root).resolve()))})


def same_pin(root, left, right):
    return (isinstance(left,dict) and isinstance(right,dict)
            and set(left)==set(right)=={'path','sha256','size'}
            and Path(root,left['path']).resolve()==Path(root,right['path']).resolve()
            and left['sha256']==right['sha256'] and left['size']==right['size'])


def _page(root, pin, binding, *, wrapped):
    from qa_review_plan import _review_native_containers
    value=document(root,pin)
    if wrapped:
        need(value.get('source')=='first_party_read_thread' and w._parse_observed_at(value.get('observed_at_UTC')),
             'actual first-party native projection required')
        page=value.get('native',{})
    else: page=value
    _review_native_containers(value); _review_native_containers(page)
    need(page.get('thread',{}).get('kind')=='codex' and all(page.get('thread',{}).get(k)==binding.get(v)
         for k,v in {'id':'task_id','title':'title','cwd':'cwd','hostId':'host_id'}.items()),
         'original fixed host/chat/title/cwd native identity required')
    return value,page


def _action_id(decision_pin, meta):
    return 'HQ-WEB-next8-test-successor-'+decision_pin['sha256'][:16]+'-'+meta['head'][:12]


def payload_document(item, meta):
    return {'schema':'HQ-original-singlefield-reviewed-test-successor-message/v1','source_kind':KIND,
            'task_id':h.TASK,'scope':h.SCOPE,'HQ_decision':item['hq_decision'],
            'owner_delegation':item['owner_delegation'],'base_registration':item['base_registration'],
            'normal_source_input_path':item['source_input_path'], 'exact_successor':meta,
            'selector':{'hq_singlefield_code_stage_source':item['base_registration'],
                        MARKER:{'normal_registered_source_path':item['source_input_path']}},
            'allowed_operations':list(OPS),'reuse_original_PR':meta['remote_PR'],
            'execution':'Read registered source pin, select both original base and this successor. Fresh exact original branch/PR/head/native effects, original normal per-action preflight/policy/once are mandatory. Continue existing PR only. Read unknown original effects before any retry. After real CI/merge load content-publish via normal R3/Edge issuer only.',
            'protection':'Original twelve production blobs/modes unchanged; no new PR, force, admin bypass, Pages, cancel/retire, CMS Save/rollback, account, fee, or new project. Preserve original failed CI/source/once and parent OPEN. PUB remains original full41/protect38/CAS owner.',
            'source_registration_grants_execution_authority':False,'CMS_permission_issued':False,
            'production_READY':False,'business_parent_closed':False}


def _git_successor(ctx, meta, successor):
    from professional_web_execution import git
    need(isinstance(meta,dict) and set(meta)=={'head','parent','base','tree','branch','worktree','remote_PR','own_delta','cumulative_paths'},
         'exact typed reviewed immutable successor tuple required')
    need(all(re.fullmatch('[0-9a-f]{40}',str(meta.get(k))) for k in ('head','parent','base','tree'))
         and meta['parent']==ctx['commit'] and meta['base']==ctx['base'] and meta['head']!=meta['parent']
         and meta['branch']==ctx['branch'] and meta['worktree']==ctx['worktree']
         and type(meta['remote_PR']) is int and meta['remote_PR']>0,
         'one child of original head on original branch/worktree/PR only')
    need(git(ctx,'show','-s','--format=%H %P %T',meta['head']).decode().strip()
         ==' '.join((meta['head'],meta['parent'],meta['tree'])), 'actual single-parent head/tree required')
    delta=meta['own_delta']
    need(set(delta)=={'files','insertions','deletions','line_added','blob','source_pin'}
         and delta['files']==[TEST_PATH] and type(delta['insertions']) is int and delta['insertions']==1
         and type(delta['deletions']) is int and delta['deletions']==0
         and delta['line_added']=='        "'+h.CANDIDATE+'",',
         'only the exact existing target expectation line may be added')
    need(git(ctx,'diff','--name-only',meta['parent'],meta['head']).decode().splitlines()==[TEST_PATH]
         and git(ctx,'diff','--numstat',meta['parent'],meta['head']).decode().strip()=='1\t0\t'+TEST_PATH,
         'exact one test file +1/-0; production deltas forbidden')
    before=git(ctx,'show',meta['parent']+':'+TEST_PATH)
    after=git(ctx,'show',meta['head']+':'+TEST_PATH)
    need(after.splitlines(keepends=True).count((delta['line_added']+'\n').encode())==1
         and after.replace((delta['line_added']+'\n').encode(),b'',1)==before,
         'existing test assertions/entries remain byte-identical')
    old_test=git(ctx,'ls-tree',meta['parent'],'--',TEST_PATH).decode().split()
    new_test=git(ctx,'ls-tree',meta['head'],'--',TEST_PATH).decode().split()
    pin=delta['source_pin']
    need(len(old_test)==len(new_test)==4 and old_test[0]==new_test[0] and new_test[2]==delta['blob']
         and Path(pin.get('path','')).resolve()==Path(ctx['worktree'],TEST_PATH).resolve()
         and pin.get('sha256')==hashlib.sha256(after).hexdigest() and pin.get('size')==len(after),
         'actual source SHA/blob/mode/path required')
    # Pin means current source too, not an unverifiable caller annotation.
    from professional_web_execution import _external_bytes
    _external_bytes(pin, ctx['binding'])
    unchanged=successor.get('unchanged_original_12_paths')
    need(isinstance(unchanged,list) and len(unchanged)==len(ctx['paths'])==12
         and len({x.get('path') for x in unchanged})==12 and {x.get('path') for x in unchanged}==set(ctx['paths']),
         'complete original twelve-path producer protection required')
    for entry in unchanged:
        path=entry['path']; old=git(ctx,'ls-tree',meta['parent'],'--',path).decode().split()
        new=git(ctx,'ls-tree',meta['head'],'--',path).decode().split()
        need(len(old)==len(new)==4 and old==new and old[2]==entry.get('blob'),
             'all original production source blobs and modes must remain unchanged')
    paths=set(git(ctx,'diff','--name-only',meta['base'],meta['head']).decode().splitlines())
    need(type(meta['cumulative_paths']) is int and meta['cumulative_paths']==13
         and paths==set(ctx['paths'])|{TEST_PATH},'complete thirteen-path cumulative delta required')
    return {**ctx['paths'],TEST_PATH:pin['sha256']}


def validate_source(root,item):
    need(isinstance(item,dict) and set(item)==KEYS and item.get('schema')==SCHEMA
         and item.get('task_id')==h.TASK and item.get('scope')==h.SCOPE,'exact typed original task/scope source required')
    ctx=h.code_stage_context(root,h.TASK,item['base_registration'])
    snap=h._snapshot(root);hq=w.department_registry(root)['operations']['chat_binding']
    need(item['owner_delegation']==ctx['authorization'],'original actual human delegation must remain unchanged')
    owner=document(root,item['owner_delegation']);decision=document(root,item['hq_decision'])
    need(decision.get('schema')=='actual-HQ-original-single-field-reviewed-test-successor-decision/v1'
         and decision.get('decision_actor')=='operations' and decision.get('decision_thread_id')==hq['task_id']
         and decision.get('task_id')==h.TASK and decision.get('scope')==h.SCOPE
         and decision.get('owner_delegation_source')==item['owner_delegation']
         and decision.get('original_code_decision')==ctx['decision']
         and same_pin(root,decision.get('original_registration'),item['base_registration'])
         and decision.get('actual_producer')==ctx['role'] and decision.get('producer_thread')==ctx['binding']['thread_id']
         and decision.get('allowed_operations')==list(OPS)
         and all(decision.get(k) is False for k in ('business_parent_closed','CMS_permission_issued','new_account_or_fee_authority')),
         'actual delegated HQ ordinary test-only decision; no new actor/production grant')
    for key,dkey in [('WEB_result','actual_WEB_result'),('WEB_successor','actual_WEB_successor'),('WEB_next_input','actual_WEB_next_input')]:
        need(same_pin(root,item[key],decision.get(dkey)),'actual reviewed WEB source pin required: '+key)
    projection,page=_page(root,item['hq_native'],hq,wrapped=True)
    texts=[(t,m) for t in page.get('turns',[]) for m in t.get('items',[])
           if m.get('type')=='agentMessage' and m.get('phase')=='commentary'
           and item['hq_decision']['sha256'] in m.get('text','') and item['hq_decision']['path'] in m.get('text','')]
    need(len(texts)==1,'one real HQ commentary names exact decision path and SHA')
    turn,_=texts[0];at=w._parse_observed_at(decision.get('at_UTC'));observed=w._parse_observed_at(projection.get('observed_at_UTC'))
    delegated=w._parse_observed_at(owner.get('observed_at_UTC'))
    need(turn.get('status')=='inProgress' and turn.get('completedAt') is None and not turn.get('error')
         and type(turn.get('startedAt')) in {int,float} and at and observed and delegated
         and delegated.timestamp()<=at.timestamp() and turn['startedAt']<=at.timestamp()<=observed.timestamp()
         <=dt.datetime.now(dt.timezone.utc).timestamp(), 'honest current HQ decision native, never fake completed human')
    result=document(root,item['WEB_result']);successor=document(root,item['WEB_successor']);nxt=document(root,item['WEB_next_input'])
    need(result.get('schema')=='WEB-actual-singlefield-code-stage-push-PR-CI-partial-result/v1'
         and successor.get('schema')=='WEB-exact-CI-registry-causal-successor/v1'
         and nxt.get('schema')=='WEB-exact-official-CI-one-line-causal-source-next-input/v1'
         and all(x.get('task_id')==h.TASK and x.get('scope')==h.SCOPE for x in (result,nxt))
         and same_pin(root,result.get('original_source_registration'),item['base_registration'])
         and same_pin(root,nxt.get('original_source_registration'),item['base_registration'])
         and same_pin(root,nxt.get('actual_successor'),item['WEB_successor'])
         and result.get('local_repair')==successor,
         'original completed producer result/successor/next-input chain required')
    meta=decision.get('exact_successor');need(isinstance(meta,dict),'reviewed exact successor data required')
    need(all(successor.get(k)==v for k,v in meta.items())
         and decision.get('reuse_original_PR')==meta.get('remote_PR')
         and result.get('PR',{}).get('number')==nxt.get('existing_PR',{}).get('number')==meta.get('remote_PR')
         and result.get('PR',{}).get('head')==ctx['commit']
         and nxt.get('existing_PR',{}).get('head')==ctx['commit'], 'same original actually-created PR, never a replacement')
    native_pin=nxt.get('WEB_native',{}).get('projection')
    need(same_pin(root,result.get('native',{}).get('projection'),native_pin),'one original WEB input source pin')
    binding={**ctx['binding'],'task_id':ctx['binding']['thread_id']}
    original,original_page=_page(root,native_pin,binding,wrapped=False)
    completed,completed_page=_page(root,item['WEB_completed_native'],binding,wrapped=True)
    tid=decision.get('producer_completed_turn')
    olds=[t for t in original_page.get('turns',[]) if t.get('id')==tid]
    news=[t for t in completed_page.get('turns',[]) if t.get('id')==tid]
    need(isinstance(tid,str) and tid and len(olds)==len(news)==1,'one exact original completed WEB turn required')
    old,new=olds[0],news[0]
    completed_at=w._parse_observed_at(completed.get('observed_at_UTC'))
    need(new.get('status')=='completed' and not new.get('error')
         and type(new.get('startedAt')) in {int,float} and type(new.get('completedAt')) in {int,float}
         and new['completedAt']>=new['startedAt']==old.get('startedAt')
         and old.get('status')=='inProgress' and old.get('completedAt') is None and not old.get('error')
         and completed_at and new['completedAt']<=completed_at.timestamp()<=dt.datetime.now(dt.timezone.utc).timestamp()
         and new['completedAt']<=at.timestamp(), 'actual finite WEB completion precedes the reviewed decision')
    incoming=[m for m in old.get('items',[]) if m.get('type')=='functionCallOutput' and m.get('name')=='send_message_to_thread'
              and m.get('namespace')=='codex_app']
    need(len(incoming)==1,'one complete original transport input required')
    entry=incoming[0];matches=[m for m in new.get('items',[]) if m.get('id')==entry.get('id')]
    need(len(matches)==1 and all(matches[0].get(k)==entry.get(k) for k in ('type','name','namespace')),
         'completed source must preserve exact original incoming native item identity')
    # SDK compact completion may omit output; if it carries bytes they must
    # equal the already pinned complete original input, never maintenance.
    need('output' not in matches[0] or matches[0]['output']==entry.get('output'),
         'completed source incoming bytes contradict the full original input')
    output=entry.get('output',{});need(output.get('truncated') is False and isinstance(output.get('text'),str),'untruncated real original input bytes required')
    try: delegation=ET.fromstring(output['text'])
    except (ET.ParseError,ValueError): need(False,'invalid original delegation bytes')
    base_item=document(root,item['base_registration']);base_request=document(root,base_item['request'])
    expected=w.validation_bytes(Path(root,base_request['payload']['path'])).decode('utf-8')
    need(delegation.tag=='codex_delegation' and delegation.findtext('source_thread_id')==hq['task_id']
         and delegation.findtext('input')==expected,'actual original HQ queue input bytes, no maintenance substitution')
    ack=[m for m in new.get('items',[]) if m.get('type')=='agentMessage' and m.get('phase')=='commentary' and m.get('text','').strip()]
    finals=[m for m in new.get('items',[]) if m.get('type')=='agentMessage' and m.get('phase') in {'final','final_answer'} and m.get('text','').strip()]
    need(ack and len(finals)==1 and all(str(Path(root,item[k]['path']).resolve()) in finals[0]['text'] for k in ('WEB_result','WEB_next_input')),
         'nonempty actual ACK and finite result final bind this exact source, not mere accepted/maintenance')
    paths=_git_successor(ctx,meta,successor)
    runbook=document(root,item['recovery_runbook'])
    need(runbook=={'schema':'singlefield-reviewed-test-successor-recovery/v1','task_id':h.TASK,'scope':h.SCOPE,
         'source_commit':meta['head'],'source_parent':meta['parent'],'source_tree':meta['tree'],'source_base':meta['base'],
         'existing_PR':meta['remote_PR'],'forward_only_source':True,'unknown_effect_replay_allowed':False,
         'CMS_rollback_execution_allowed':False,'recovery':'Read original branch/PR/action/run keys first. Preserve original source and failed CI. No force, new PR, cancel/retire or blind replay. Runtime requires fresh actual main/full source backup and own normal per-action issuer; CMS remains original PUB scope.'},
         'exact source-specific forward recovery, no new inverse/CMS permission')
    source_path=Path(item['source_input_path']);need(source_path.is_absolute() and source_path.resolve().is_relative_to(Path(root).resolve()),'source input belongs to this project')
    request=document(root,item['request']);payload=request.get('payload',{})
    need(set(request)==set(h.IDENTITY_KEYS) and request.get('task_id')==h.TASK and request.get('scope')==h.SCOPE
         and request.get('action_id')==_action_id(item['hq_decision'],meta)
         and request.get('sender_department')=='operations' and request.get('action_class')=='thread_message'
         and request.get('target_department')==ctx['role'] and request.get('assignment_record_required') is False
         and request.get('authorization_changes')==[] and request.get('delivery_mode')=='mcp_direct_send'
         and request.get('source_project_id')==hq.get('project_id')
         and all(request.get(k)==ctx['binding'].get(v) for k,v in {'target_project_id':'project_id','target_thread_id':'thread_id',
             'target_thread_title':'title','target_cwd':'cwd','target_sidebar_section_id':'sidebar_section_id'}.items())
         and w.file_digest(root,payload.get('path',''))==payload and payload.get('sha256')==request.get('payload_sha256')
         and document(root,payload)==payload_document(item,meta),'exact source-derived normal HQ-to-original-WEB payload only')
    return {'snapshot':snap,'base_context':ctx,'meta':meta,'paths':paths,'action':request,
            'sender_binding':hq,'target_binding':ctx['binding'],'code_stage_requested':True,
            'source_kind':KIND,'external_permission_issued':False,'production_READY':False}


def _entries(root):
    return [e for e in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS,where={'task_id':h.TASK}) if e.get('details',{}).get(EVENT)]


def _unused(root,snap,action):
    import department_autonomy as a
    a._owner_message_transport_not_started(root,snap,action)
    for e in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS,where={'task_id':h.TASK}):
        for key,value in e.get('details',{}).items():
            if isinstance(value,dict) and value.get('action_id')==action['action_id'] and any(x in key for x in ('intent','transport','dispatch','queue','consum')):
                need(False,'original successor key has intent/UNKNOWN/effect; read original key, never re-admit')
    need(not any(x.get('task_id')==h.TASK and x.get('action_id')==action['action_id'] for x in w.read_jsonl(Path(root)/w.APPROVAL_LEDGER)),
         'existing production approval cannot renew message admission')


def record(root,task,input_path):
    from department_rotation import prohibit_validation_write
    prohibit_validation_write();need(task==h.TASK,'same original task required')
    pin=w.file_digest(root,input_path);item=document(root,pin)
    need(Path(root,input_path).resolve()==Path(item.get('source_input_path','')).resolve(),'source input self path must match actual registration')
    with w.workflow_lock(root),w.request_validation_context() as validation:
        result=validate_source(root,item);snap=result['snapshot'];goal=snap['goal_delivery'];action={**result['action'],MARKER:pin}
        same=[e for e in _entries(root) if e['details'][EVENT]==pin]
        collision=[x for x in goal.get('approved_actions',[]) if x.get('action_id')==action['action_id']]
        if same:
            need(len(same)==1 and collision==[action],'immutable admission/action must remain exact')
            return {'result':'duplicate_ignored','source':pin,'message_sent':False,'external_permission_issued':False}
        need(not collision,'existing action may not be replaced/renewed')
        for old in _entries(root):
            previous=document(root,old['details'][EVENT])
            reviewed=document(root,previous['hq_decision'])
            need(reviewed.get('exact_successor',{}).get('head')!=result['meta']['head']
                 and previous['hq_decision']!=item['hq_decision'],
                 'same actual successor/decision already admitted; changed source cannot renew its once key')
        _unused(root,snap,action);validation.recheck()
        snap['goal_delivery']={**goal,'approved_actions':[*goal.get('approved_actions',[]),action]}
        event=w.append_workflow_event(root,task,snap['current_state'],{EVENT:pin,'goal_delivery':snap['goal_delivery'],
            'actual_actor':'operations','source_kind':KIND,'frozen_contract_unchanged':True,'external_permission_issued':False})
        w.atomic_write_json(w.snapshot_path(root,task),snap)
    return {'result':'recorded','source':pin,'event_id':event['event_id'],'message_sent':False,'external_permission_issued':False,'production_READY':False}


def registered(root,snapshot,requested):
    if not isinstance(requested,dict):return None
    if MARKER not in requested:
        aid=requested.get('action_id')
        if not isinstance(aid,str) or not aid.startswith('HQ-WEB-next8-test-successor-'):return None
        selected=[]
        for event in _entries(root):
            source=event['details'][EVENT];entry=document(root,source)
            decision=document(root,entry['hq_decision'])
            if _action_id(entry['hq_decision'],decision['exact_successor'])==aid:selected.append(source)
        need(len(selected)==1,'one real registered source for this exact successor action required')
        requested={**requested,MARKER:selected[0]}
    need(set(requested)<=set(h.IDENTITY_KEYS)|h.FRESH_KEYS|{MARKER}
         and not any(k in requested for k in h.FORBIDDEN),'no production fields or actor substitution in source message')
    pin=requested[MARKER];entries=[e for e in _entries(root) if e['details'][EVENT]==pin]
    need(len(entries)==1 and snapshot.get('task_id')==h.TASK,'one real normal typed successor registration required')
    item=document(root,pin);need(Path(root,pin['path']).resolve()==Path(item['source_input_path']).resolve(),'registered self path changed')
    result=validate_source(root,item);action={**result['action'],MARKER:pin}
    need(all(requested[k]==action[k] for k in requested if k not in h.FRESH_KEYS)
         and [x for x in result['snapshot']['goal_delivery'].get('approved_actions',[]) if x.get('action_id')==action['action_id']]==[action],
         'exact real registered message source/action/target/payload required')
    return {**result,'action':action,'registration':pin,'event_id':entries[0]['event_id']}


def approved_action(root,snapshot,requested):
    result=registered(root,snapshot,requested);return result['action'] if result else None


def binding(root,snapshot,requested):
    result=registered(root,snapshot,requested)
    return (result['sender_binding'],result['target_binding']) if result else None


def execution_context(root,task,base_registration,registration):
    need(task==h.TASK,'same original successor task only')
    result=registered(root,{'task_id':task},{MARKER:registration})
    ctx=result['base_context'];meta=result['meta']
    need(ctx['registration']==base_registration,'both selectors must authenticate the same actual base source')
    item=document(root,registration)
    return {**ctx,'registration':registration,'event_id':result['event_id'],'decision':item['hq_decision'],
            'hq_reviewed_test_successor':True,'successor_base_registration':base_registration,'source_kind':KIND,'commit':meta['head'],'git_parent':meta['parent'],
            'tree':meta['tree'],'base':meta['base'],'paths':result['paths'],'existing_pull_number':meta['remote_PR'],
            'prefix':'next8-test-successor-'+item['hq_decision']['sha256'][:16],
            'rollback':item['recovery_runbook'],'allowed_operations':OPS}
