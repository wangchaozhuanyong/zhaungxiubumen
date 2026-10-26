"""Authenticated external WEB production continuation. No website/network writes."""
from pathlib import Path
import argparse,datetime as dt,hashlib,json,re,subprocess
import workflow_control as w
import department_autonomy as a
import professional_cms_execution as cms
from professional_cms_issuer import external
EVENT='professional_WEB_production_source'
SCHEMA='professional-external-WEB-production-source/v1'
R3='.github/workflows/supabase-content-publish-r3.yml'
PAGES='.github/workflows/cloudflare-pages-deploy.yml'
OPS={'git_push':'site_ci_prepare','pull_request':'site_ci_prepare','official_ci':'site_ci_prepare',
     'merge':'site_ci_prepare','r3_dispatch':'site_ci_prepare','edge_deploy':'site_publish','pages_deploy':'site_publish'}
CHECKS={'furniture-page-pr-checks','interaction-standards','r3-managed-cms-pr-checks'}
def need(ok,message):a.require(ok,'external WEB: '+message)
def git(ctx,*args):
    p=subprocess.run(['git',*args],cwd=ctx['worktree'],capture_output=True,timeout=20)
    need(p.returncode==0,'actual local Git source unavailable');return p.stdout
def _pins(value):
    if isinstance(value,dict):
        if set(value)=={'path','sha256','size'}:yield value
        for child in value.values():yield from _pins(child)
    elif isinstance(value,list):
        for child in value:yield from _pins(child)

def validate_source(root,snapshot,item):
    import goal_delivery_runtime as g
    import goal_source_recovery as recovery
    import result_coordination as rc
    goal=a.participant(root,snapshot,snapshot['goal_delivery']['primary_owner']);frozen=a.document(root,snapshot['goal_contract'])
    need(a.autonomous_goal(goal) and all(goal.get(k)==frozen.get(k)for k in
         ('primary_owner','producer_departments','authorized_scope','human_authorization','required_execution_actions','collaboration_scopes')),
         'unchanged original autonomous contract and participants')
    need(item.get('schema')==SCHEMA and item.get('task_id')==snapshot['task_id'],'original task/source registration')
    repair=a.document(root,item.get('repair_source'));decision_pin=repair['original_complete_HQ_production_decision'];decision=a.document(root,decision_pin)
    owner=goal['primary_owner'];scope=repair['scope'];delegation=g._owner_decision_delegation(root)
    need(repair.get('task_id')==snapshot['task_id'] and repair.get('primary_owner')==owner and scope in goal['authorized_scope']
      and decision.get('schema')=='HQ-original-goal-exact-production-continuation-decision/v1'
      and decision.get('task_id')==snapshot['task_id'] and decision.get('scope')==scope
      and decision.get('department')=='operations' and decision.get('original_professional_owner')==owner
      and decision.get('owner_human_authorization')==goal['authorization_pin']
      and decision.get('original_goal_contract')==snapshot['goal_contract']
      and decision.get('owner_nonpayment_delegation')==delegation,'real original human task and HQ delegated exact decision')
    index=decision['original_criterion_index'];need(type(index)is int and 0<=index<len(frozen['completion_criteria'])
      and decision.get('original_criterion')==frozen['completion_criteria'][index], 'unchanged original criterion')
    need({x['action']for x in decision['original_WEB_allowed_actions']}=={'local_commit','push_and_PR','CI_and_merge','necessary_existing_workflow_and_deploy','actual_loaded_version_readback'}
         and decision.get('backup_and_rollback') and decision.get('not_a_platform_permit')is True
         and decision.get('actual_platform_permission_issued')is False,'complete bounded production sequence; no platform permission inferred')
    old=g._native_document(root,repair['actual_HQ_native_source']);fresh=g._native_document(root,item.get('actual_HQ_native'))
    fixed=w.department_registry(root)['operations']['chat_binding']
    need(all(fresh.get('thread',{}).get(k)==fixed[v]for k,v in {'id':'task_id','title':'title','cwd':'cwd'}.items()),'actual original fixed HQ identity')
    pairs=[(t,m)for t in old.get('turns',[])for m in t.get('items',[])if m.get('type')=='agentMessage'and decision_pin['sha256']in m.get('text','')]
    need(len(pairs)==1,'one original HQ statement identifies exact decision SHA')
    turn,message=pairs[0];current=[(t,m)for t in fresh.get('turns',[])if t.get('id')==turn['id']for m in t.get('items',[])if m.get('id')==message['id']]
    need(len(current)==1 and current[0][1]==message and not current[0][0].get('error')
         and current[0][0].get('status')=='completed','real completed first-party HQ decision, not caller labels or rewritten old snapshot')
    decided=w._parse_observed_at(decision.get('decided_at_MYT'));selected_turn=current[0][0]
    need(decided is not None and type(selected_turn.get('completedAt'))in {int,float}
         and selected_turn['startedAt']<=decided.timestamp()<=selected_turn['completedAt']<=dt.datetime.now(dt.timezone.utc).timestamp(),
         'actual HQ decision chronology, no backdated future decision')
    identity_rows=[r for r in w._result_handoff_rows(root,snapshot['task_id'])if r.get('record_id')==decision['actual_original_V9_HQ_intake']]
    need(len(identity_rows)==1,'actual original HQ intake identity')
    identity=rc.exact_identity(identity_rows[0]);intake=rc._received_delivery(root,identity,{'target_department':'operations'})
    need(intake and intake['record_id']==decision['actual_original_V9_HQ_intake'],'real SQL/native original HQ receipt')
    channel=decision['original_technical_producer']['department'];binding=g._collaboration_binding(root,snapshot,channel)
    need(binding and channel==repair['original_WEB_exact_identity']['department']
      and binding['thread_id']==decision['original_technical_producer']['thread_id']==repair['original_WEB_exact_identity']['thread_id']
      and binding['project_id']==decision['original_technical_producer']['website_project']==repair['original_WEB_exact_identity']['execution_project_id']
      and binding['project_id']!=a.PROJECT and channel not in goal['producer_departments'], 'original external WEB remains outside business producers')
    cmssources=[x for x in cms.records(root,snapshot)if x['registration']==repair['registered_professional_execution_source']]
    need(len(cmssources)==1 and cmssources[0]['source']==repair['original_C1_business_source']
         and cmssources[0]['channel']==channel,'same original CMS/WEB source graph')
    records=[a.document(root,p)for p in goal.get('collaboration_records',[])];states=g._collaboration_wait_states(root,snapshot)
    completed=[s for s in states if s.get('department')==channel and s.get('status')=='result_received'and s.get('proof_state')=='PROVEN']
    original_completed=g._native_document(root,repair['actual_completed_safe_stage_native'])
    original_turns={t['id']for t in original_completed.get('turns',[])if t.get('status')=='completed'and not t.get('error')}
    need(original_turns and all(original_completed.get('thread',{}).get(k)==binding[v]for k,v in {'id':'thread_id','title':'title','cwd':'cwd'}.items()),'actual original completed WEB source turn')
    selected=[]
    for state in completed:
        recs=[v for v in records if v.get('action_id')==state['action_id']and v.get('status')=='result_received']
        if len(recs)!=1:continue
        request=a.document(root,recs[0]['original_prepare_request']);body=w.safe_path(root,request['payload']['path']).read_text()
        actual_result=a.document(root,recs[0]['result']);pins=list(_pins(actual_result))
        def same_source(p,q):
            return p.get('sha256')==q.get('sha256')and p.get('size')==q.get('size')and (Path(root)/p.get('path','')).resolve()==(Path(root)/q.get('path','')).resolve()
        if (decision_pin['path']in body and decision_pin['sha256']in body
                and recs[0].get('recipient_turn_id')in original_turns
                and actual_result.get('task_id')==snapshot['task_id']and actual_result.get('commit')==repair['original_WEB_exact_identity']['commit']
                and any(same_source(p,repair['actual_failing_request'])for p in pins)
                and any(same_source(p,repair['actual_failing_request_object']['committed_source'])for p in pins)):
            selected.append((state,recs[0]))
    need(len(selected)==1,'actual exact full-production message/queue/user/ACK/completed result chain')
    recovery.collaboration_queue_source(root,snapshot,selected[0][1])
    source=a.document(root,repair['real_committed_source_custody']);meta=repair['original_WEB_exact_identity'];local=decision['selected_local_version']
    ctx={'root':str(Path(root).resolve()),'task':snapshot['task_id'],'scope':scope,'owner':owner,'role':channel,'binding':binding,'decision':decision_pin,
         'authorization':goal['authorization_pin'],'contract':snapshot['goal_contract'],'repair':item['repair_source'],
         'worktree':local['worktree'],'site':decision['original_technical_producer']['website_git_root'],
         'branch':local['branch'],'commit':meta['commit'],'base':meta['parent'],'tree':meta['tree'],
         'paths':repair['real_selected_12_blob_sha256'],'backup':repair['real_preproduction_backup_receipt'],
         'rollback':repair['real_controlled_rollback_route'],'registered_CMS':cmssources[0]}
    need(Path(ctx['worktree']).resolve().is_relative_to(Path(binding['cwd']).resolve())
      and Path(ctx['site']).resolve().is_relative_to(Path(binding['cwd']).resolve())
      and source.get('commit')==ctx['commit'] and source.get('parent')==ctx['base'] and source.get('tree')==ctx['tree']
      and source.get('file_sha256')==ctx['paths'] and local['candidate_tree']==ctx['tree']
      and source.get('branch')==ctx['branch'],'original real worktree/commit/tree/base and exact reviewed file map')
    need(git(ctx,'show','-s','--format=%H %P %T',ctx['commit']).decode().strip()==' '.join([ctx['commit'],ctx['base'],ctx['tree']]),'actual original Git objects')
    approved={x['path']:x['candidate']['sha256']for x in local['code_files']}
    need(approved==ctx['paths'] and set(git(ctx,'diff','--name-only',ctx['base'],ctx['commit']).decode().splitlines())==set(approved), 'only original exact selected paths')
    for path,sha in approved.items():need(hashlib.sha256(git(ctx,'show',ctx['commit']+':'+path)).hexdigest()==sha,'actual reviewed source blob differs')
    backup=a.document(root,ctx['backup']);need(backup.get('task_id')==ctx['task']and backup.get('function')=='content-publish','original backup is task-bound')
    for pin in backup['runtime_files']+backup['source_build_archives']:
        external(root,pin,binding) if pin['path'].endswith('.json') else _external_bytes(pin,binding)
    need(w.file_digest(root,ctx['rollback']['path'])==ctx['rollback'],'original executable production recovery runbook')
    repo=git(ctx,'config','--get','remote.origin.url').decode().strip();match=re.fullmatch(r'(?:user-3de132cd98be@example.invalid:|https://github.com/)([\w.-]+/[\w.-]+?)(?:\.git)?',repo)
    need(match is not None,'original GitHub repository only');ctx['repository']=match[1]
    first=a.document(root,repair['actual_failing_request']);need(first==repair['actual_failing_request_object']and first['desired']['repository']==ctx['repository'],'unchanged real original failed request')
    prefix=first['action_id'].removesuffix('-'+ctx['commit'][:12]+'-git-push-v1')
    need(prefix!=first['action_id'],'source-derived exact original action prefix');ctx['prefix']=prefix
    # Existing installed protected channel identifiers, never a new account or scope.
    from managed_cms_permit_issuer import SUPABASE_HOST
    domain=cmssources[0]['action']['scope'].split(':',1)[0]
    ctx['edge_scope']=domain+':edge:'+SUPABASE_HOST.split('.')[0]+':content-publish'
    ctx['pages_scope']=domain+':pages:production';ctx['project_ref']=SUPABASE_HOST.split('.')[0]
    need(not w.validate_workflow_events(root,ctx['task']),'intact original append-only workflow')
    return ctx

def _external_bytes(pin,binding):
    p=Path(pin['path']);need(p.is_absolute()and p.resolve().is_relative_to(Path(binding['cwd']).resolve())and not p.is_symlink(),'external report/backup path')
    b=p.read_bytes();need(len(b)==pin['size']and hashlib.sha256(b).hexdigest()==pin['sha256'],'real source backup bytes');return b

def records(root,task):
    import goal_delivery_runtime as g
    rows=[e for e in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS)if e.get('task_id')==task and EVENT in e.get('details',{})]
    if not rows:return []
    need(len(rows)==1,'ambiguous original external execution source')
    pin=rows[0]['details'][EVENT];item=a.document(root,pin);snapshot=g.restore_goal(root,w.read_json(w.snapshot_path(root,task)))
    return [{**validate_source(root,snapshot,item),'registration':pin,'event_id':rows[0]['event_id']}]
def applies(root,task,action_class):
    return action_class in {'site_ci_prepare','site_publish'} and any(e.get('task_id')==task and EVENT in e.get('details',{})for e in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS))
def record_source(root,task,path):
    import goal_delivery_runtime as g
    pin=w.file_digest(root,path);item=a.document(root,pin)
    with w.workflow_lock(root):
        snapshot=g.restore_goal(root,w.read_json(w.snapshot_path(root,task)));ctx=validate_source(root,snapshot,item);old=records(root,task)
        if old:need(old[0]['registration']==pin,'immutable source already bound');return {'result':'duplicate_ignored','source':pin,'external_permission_issued':False}
        event=w.append_workflow_event(root,task,snapshot['current_state'],{EVENT:pin})
    return {'result':'recorded','source':pin,'event_id':event['event_id'],'external_permission_issued':False,'business_producers_changed':False}

def action_id(ctx,op,commit,main=None):
    return ctx['prefix']+'-'+commit[:12]+'-'+op.replace('_','-')+('-'+main[:12]if main and op in {'r3_dispatch','edge_deploy','pages_deploy'}else'')+'-v1'
def scopes(ctx,op):return ctx['edge_scope']if op in {'edge_deploy','r3_dispatch'}else ctx['pages_scope']if op=='pages_deploy'else ctx['scope']
def reference(ctx,commit,main):return 'apr-'+w.sha256_value([ctx['task'],ctx['decision'],ctx['role'],action_id(ctx,'edge_deploy',commit,main),ctx['edge_scope'],main])[:20]
def _delta(ctx,base,head):
    out={}
    for path in ctx['paths']:
        lines=git(ctx,'diff','--no-ext-diff','--unified=0',base,head,'--',path).decode().splitlines()
        hunks=[];removed=[];added=[]
        for line in lines:
            if line.startswith('@@'):
                if removed or added:hunks.append((removed,added))
                removed=[];added=[]
            elif line.startswith('-')and not line.startswith('---'):removed.append(line[1:])
            elif line.startswith('+')and not line.startswith('+++'):added.append(line[1:])
        if removed or added:hunks.append((removed,added))
        out[path]=hunks
    return out
def candidate(ctx,state):
    head=state.get('candidate_commit');base=state.get('candidate_base',ctx['base']);need(re.fullmatch('[0-9a-f]{40}',str(head)),'real full candidate head')
    need(state.get('source_mode','forward')in {'forward','remove_own_delta'},'known exact source mode only')
    if ctx.get('increment_registration'):
        need(head==ctx['commit']and base==ctx['base']and state.get('source_mode','forward')=='forward','exact actually adopted metadata increment only');return head,base
    if head==ctx['commit']:
        need(base==ctx['base']and state.get('source_mode','forward')=='forward','original candidate base; recovery needs a real inverse commit');return head,base
    need(re.fullmatch('[0-9a-f]{40}',str(base))and set(git(ctx,'diff','--name-only',base,head).decode().splitlines())<=set(ctx['paths']), 'same original paths only in causal successor')
    need(git(ctx,'merge-base',ctx['base'],base).decode().strip()==ctx['base'],'real later base ancestry')
    actual=_delta(ctx,base,head);original=_delta(ctx,ctx['base'],ctx['commit'])
    tests={p for p in ctx['paths']if '.test.'in p or p=='.github/workflows/r3-managed-cms-pr-ci.yml'}
    recovery=state.get('source_mode')=='remove_own_delta'
    expected={p:[(added,removed)for removed,added in hunks]if recovery else hunks for p,hunks in original.items()}
    need(all(actual[p]==expected[p]for p in ctx['paths']if p not in tests),
         'same exact production patch, or its own inverse; only related CI/test compatibility may differ')
    if recovery:
        import goal_delivery_runtime as g
        snapshot=g.restore_goal(Path(ctx['root']),w.read_json(w.snapshot_path(Path(ctx['root']),ctx['task'])))
        proof=state.get('CMS_recovery_source');doc=a.document(Path(ctx['root']),proof)
        matching=[s for s in g._collaboration_wait_states(Path(ctx['root']),snapshot)if s.get('department')==ctx['registered_CMS']['executor']
                  and s.get('status')=='result_received'and s.get('proof_state')=='PROVEN'and s.get('result')==proof]
        guard=doc.get('CMS_recovery_guard',{})
        need(len(matching)==1 and guard.get('task_id')==ctx['task']
          and guard.get('forward_action_id')==ctx['registered_CMS']['action']['action_id']
          and guard.get('record_id')==ctx['registered_CMS']['action']['record_id'],
          'actual original PUB completed recovery/effect report, never caller no-Save flags')
        need(guard.get('state')=='NO_OWN_SAVE'and guard.get('publish_runs')==[]and guard.get('permits')==[]
          or guard.get('state')=='OWN_INVERSE_COMPLETED'and guard.get('original_publish_permit_id')and guard.get('original_publish_run_id')
          and guard.get('inverse_permit_id')and guard.get('inverse_completed_run_id')and guard.get('saved_updated_at'),
          'unknown Save blocks channel removal; own completed inverse or verified zero effect required')
    return head,base

def execution_context(root,task,state):
    from professional_web_increment import select
    return select(root,records(root,task)[0],state)

def static_intent(root,request):
    ctx=execution_context(root,request['task_id'],request.get('state',{}));role=request.get('sender_department',request.get('department'))
    need(role==request.get('department',role)==ctx['role']and request.get('source_project_id')==a.PROJECT
      and request.get('execution_project_id')==ctx['binding']['project_id']and request.get('authorization_changes',[])==[]
      and request.get('exact_HQ_production_decision')==ctx['decision'],'exact actual external WEB/projects/HQ source; no actor substitution or expansion')
    return ctx
def working_source(ctx,head):
    need(git(ctx,'rev-parse','HEAD').decode().strip()==head
         and git(ctx,'branch','--show-current').decode().strip()==ctx['branch']
         and not git(ctx,'status','--porcelain').strip(),
         'fresh real clean worktree/head/branch CAS; preserve parallel WIP and never push another HEAD')
def intent(root,req,check_desired=True):
    ctx=static_intent(root,req);op=req.get('operation');need(op in OPS,'only registered complete-stage operations')
    if ctx.get('increment_registration'):need(op in ctx['increment_allowed_operations'],'metadata increment needs no CMS/Edge/R3/manual Pages action')
    state=req.get('state',{});head,base=candidate(ctx,state);main=state.get('main_sha')if op in {'edge_deploy','r3_dispatch','pages_deploy'}else None
    working_source(ctx,head)
    if op in {'edge_deploy','r3_dispatch','pages_deploy'}:
        need(re.fullmatch('[0-9a-f]{40}',str(main))is not None,'actual final main is required at this stage, never future or missing SHA')
    need(req.get('action_class')==OPS[op]and req.get('scope')==scopes(ctx,op)
      and req.get('action_id')==action_id(ctx,op,head,main),'exact source-derived operation/action/business or physical scope')
    need(state.get('repository')==ctx['repository'] and state.get('repository_id')==1248188229
      and state.get('branch')==ctx['branch'],'actual original repository/branch')
    if ctx.get('increment_registration'):
        need(state.get('worktree',ctx['worktree'])==ctx['worktree'],'current native/source worktree, never caller old-context fill')
        need(state.get('actor',{}).get('id')==ctx['increment_actor_id'],'exact authenticated original actor')
    actor=state.get('actor',{});need(actor.get('login')==ctx['repository'].split('/')[0]and type(actor.get('id'))is int and actor['id']>0,'original authenticated repository account, no substituted actor')
    desired={'repository':ctx['repository'],'branch':ctx['branch'],'head':head,'force':False,'admin_bypass':False}
    if op=='git_push':need(state.get('remote_main_sha')==base,'fresh main advanced; same-semantic source rebase required before first push')
    if op in {'pull_request','merge'}:desired['base_branch']='main'
    if op in {'official_ci','merge'}:
        checks=state.get('checks',[]);need({x.get('name')for x in checks}>=CHECKS
          and all(x.get('head_sha')==head and x.get('status')=='completed'and x.get('conclusion')=='success'and x.get('id')for x in checks), 'all real required exact-head official checks must succeed')
    if op=='merge':
        pr=state.get('pull_request',{});need(type(pr.get('number'))is int and pr['number']>0 and pr.get('head_sha')==head and pr.get('base_branch')=='main'
          and pr.get('mergeable')=='MERGEABLE'and pr.get('merge_state')=='CLEAN','actual exact clean PR; no CI bypass')
        desired.update(pull_number=pr['number'],merge_method='merge')
    if main:
        need(re.fullmatch('[0-9a-f]{40}',str(main))and state.get('remote_main_sha')==main and state.get('main_local_sha')==main,'actual local/remote final main, not a predicted merge SHA')
        need(git(ctx,'merge-base',head,main).decode().strip()==head,'actual final main includes exact candidate')
        changed=set(git(ctx,'diff','--name-only',head,main,'--',*ctx['paths']).decode().splitlines());need(not changed,'merged version changed selected paths; verify real new delta')
        desired['expected_main_sha']=main
    if op=='r3_dispatch':desired.update(workflow=R3,mode='deploy',edge_function='content-publish',approval_id=reference(ctx,head,main),task_id=ctx['task'],release_action_id=action_id(ctx,'edge_deploy',head,main),release_action_class='site_publish',release_scope=ctx['edge_scope'])
    if op=='edge_deploy':
        run=state.get('r3_run',{});need(type(run.get('id'))is int and run['id']>0 and run.get('run_attempt')==1
          and run.get('event')=='workflow_dispatch'and run.get('path')==R3 and run.get('head_sha')==main and run.get('head_branch')=='main'
          and run.get('repository',{}).get('full_name')==ctx['repository']and run.get('repository',{}).get('id')==1248188229
          and run.get('actor',{}).get('id')==actor['id']and run.get('status')in {'queued','in_progress','waiting','pending'}and run.get('conclusion')is None,
          'real first pending original-actor R3 run/attempt/environment for current main')
        need(state.get('project_ref')==ctx['project_ref']and state.get('function')=='content-publish','exact original Edge function/project')
        desired.update(workflow=R3,edge_function='content-publish',run_id=run['id'],run_attempt=1,approval_id=reference(ctx,head,main))
    if op=='pages_deploy':
        need(state.get('pages_project')=='flashcast-website','exact original Pages project')
        desired.update(workflow=PAGES,manual_only_if_no_successful_same_head_run=True)
    if check_desired:need(req.get('desired')==desired,'only exact registered effects; no hidden force, branch, account, workflow or target')
    return ctx,op,state,desired

def native(root,ctx,pin,command):
    import goal_delivery_runtime as g
    page=g._native_document(root,pin);b=ctx['binding'];need(all(page.get('thread',{}).get(k)==b[v]for k,v in {'id':'thread_id','title':'title','cwd':'cwd'}.items()),'actual original WEB native, never SYS/PUB/HQ impersonation')
    pairs=[(t,m)for t in page.get('turns',[])for m in t.get('items',[])if m.get('id')==command];need(len(pairs)==1,'one genuine external WEB command')
    t,m=pairs[0];need(not t.get('error')and m.get('type')=='commandExecution'and m.get('status')=='completed'and m.get('exitCode')==0
      and type(t.get('startedAt'))in {int,float}and Path(m.get('cwd','')).resolve()==Path(ctx['worktree']).resolve(),'real successful original worktree command')
    return w._completion_execution_output(m)
def validate_request(root,req):
    ctx,op,state,desired=intent(root,req);digest=w.sha256_value({k:v for k,v in req.items()if k not in {'facts','self_check','backup','rollback'}})
    for name in ('facts','self_check','backup','rollback'):
        value=a.document(root,req.get(name));need(all(value.get(k)==req.get(k)for k in ('task_id','department','action_id','action_class','scope'))and value.get('intent_sha256')==digest,'exact current request-bound '+name)
        if name=='facts':need(json.loads(native(root,ctx,value.get('actual_native'),value.get('command_id'))).get('state')==state and state.get('observed_at')==req.get('observed_at'),'actual native complete Git/GitHub/runtime facts, no caller observation label')
        if name=='self_check':
            out=native(root,ctx,value.get('actual_native'),value.get('command_id'));need(value.get('status')=='PASS'and digest.encode()in out and ctx['decision']['sha256'].encode()in out,'real professional selfcheck binds intent/source; reuse unaffected tests')
        if name=='backup':
            pin=value.get('source_backup');need(isinstance(pin,dict),'actual production backup pin');backup=external(root,pin,ctx['binding']) if Path(pin['path']).is_absolute() else a.document(root,pin)
            need(backup.get('task_id')==ctx['task']and backup.get('function')=='content-publish'and backup.get('runtime_files')and backup.get('source_build_archives'),'full actual source/build backup, not local reverse alone')
            for item in backup['runtime_files']+backup['source_build_archives']:_external_bytes(item,ctx['binding'])
            if op in {'r3_dispatch','edge_deploy','pages_deploy'}:need(backup.get('version')==state.get('runtime_version'),'fresh actual function/version backup CAS')
        if name=='rollback':need(value.get('production_recovery')==ctx['rollback']and value.get('unknown_effect_replay_allowed')is False,'original executable own-delta recovery; unknown effects are not retries')
    return ctx,op,state

def record_preflight(root,task,path):
    import goal_delivery_runtime as g
    pin=w.file_digest(root,path);item=a.document(root,pin);req=a.document(root,item.get('request'));validate_request(root,req)
    need(item.get('schema')=='professional-external-WEB-fresh-preflight/v1'and req.get('task_id')==task,'normal external WEB preflight envelope')
    with w.workflow_lock(root):
        rows=[e['details']['professional_WEB_preflight']for e in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS)if e.get('task_id')==task and e.get('details',{}).get('professional_WEB_preflight',{}).get('action_id')==req['action_id']]
        if rows and rows[-1]['request']==item['request']:return {'result':'duplicate_ignored','permission_issued':False}
        need(not any(p.get('task_id')==task and p.get('action_id')==req['action_id']and p.get('status')=='allow'for p in w.read_jsonl(Path(root)/w.POLICY_DECISIONS)),'actual/unknown action already issued; read effect without replay')
        if rows:
            old=a.document(root,rows[-1]['request']);need(all(old.get(k)==req.get(k)for k in ('task_id','department','action_id','action_class','scope','operation','desired')),'refresh exact same action observations only')
        s=g.restore_goal(root,w.read_json(w.snapshot_path(root,task)));e=w.append_workflow_event(root,task,s['current_state'],{'professional_WEB_preflight':{'action_id':req['action_id'],'request':item['request'],'input':pin}})
    return {'result':'recorded','event_id':e['event_id'],'input':pin,'permission_issued':False}
def preflight(root,task,action,action_class,scope,department):
    rows=[e['details']['professional_WEB_preflight']for e in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS)if e.get('task_id')==task and e.get('details',{}).get('professional_WEB_preflight',{}).get('action_id')==action]
    need(rows,'current actual original WEB preflight required');item=a.document(root,rows[-1]['input']);req=a.document(root,rows[-1]['request']);ctx,op,state=validate_request(root,req)
    need(req.get('department')==ctx['role']==department and req.get('scope')==scope and req.get('action_class')==action_class,'exact preflight executor/action/scope')
    return {**item,'risk_level':'R3'if op=='edge_deploy'else'R2',**{k:req[k]for k in ('task_id','department','action_id','action_class','scope','facts','self_check','backup','rollback')}},req,rows[-1]['input'],ctx

def authorization_precheck(root,request):
    ctx=static_intent(root,request);op=request.get('operation');need(op in OPS,'known original production operation')
    if request.get('state'):intent(root,request)
    else:
        repair=a.document(root,ctx['repair']);original=a.document(root,repair['actual_failing_request'])
        need(all(request.get(k)==original.get(k)for k in ('action_id','action_class','scope','operation','desired','committed_source')),'exact initial source intent, or use normal current-state request for later stages')
    return {'schema':'goal-authorization-precheck/v1','task_id':ctx['task'],'status':'within_original_authorization',
      'reasons':['verified_original_external_WEB_full_production_source'],'original_authorization':ctx['authorization'],
      'HQ_delegated_decision':ctx['decision'],'source_registration':ctx['registration'],'needs_human_confirmation':False,
      'actual_action_allowed':False,'external_permission_issued':False,'next_owner':ctx['role'],
      'next_action':'fresh normal original-executor preflight/policy and exact actual platform stage; no general approval repeat'}

def policy(root,requested):
    item,req,pin,ctx=preflight(root,requested['task_id'],requested['action_id'],requested['action_class'],requested['scope'],requested['department'])
    need(requested.get('source_project_id')==a.PROJECT and requested.get('payload_sha256')==item['request']['sha256']and not requested.get('target_department')and not requested.get('approval_id'),'exact request hash and original action, no borrowed approval/role')
    state=req['state'];op=req['operation'];observed=w._parse_observed_at(req.get('observed_at'))
    need(observed and 0<=(dt.datetime.now(dt.timezone.utc)-observed).total_seconds()<=300,'fresh real execution facts; stored authority does not expire')
    if op=='official_ci' or op=='git_push'and state.get('remote_branch_sha')==state['candidate_commit'] or op=='pull_request'and state.get('pull_request',{}).get('head_sha')==state['candidate_commit']:
        return {'status':'actual_same_effect_readback_no_new_write','actual_action_allowed':False,'task_id':ctx['task'],'source_request':item['request']},[]
    if op in {'r3_dispatch','pages_deploy'}:
        run=state.get('r3_run'if op=='r3_dispatch'else'pages_run',{})
        if run.get('head_sha')==state.get('main_sha') and run.get('path')==(R3 if op=='r3_dispatch'else PAGES)and run.get('status')in {'queued','in_progress','waiting','pending','completed'}:
            return {'status':'existing_same_head_run_readback_no_new_dispatch','actual_action_allowed':False,'source_request':item['request']},[]
    need(state.get('effect_state')=='NOT_STARTED','unknown or issued effect must be read back, never blindly retried')
    key=w.sha256_value([ctx['task'],ctx['role'],req['action_id'],req['action_class'],req['scope']])
    with w.workflow_lock(root):
        need(not any(row.get('autonomous_action_key')==key and row.get('status')=='allow'for row in w.read_jsonl(Path(root)/w.POLICY_DECISIONS)),'single original actual action already issued; read unknown effect')
        value={**requested,'status':'preflight_ready_not_a_permit','actual_action_allowed':False,'approval_basis':a.MODE,'original_authority':ctx['authorization'],'delegated_HQ_decision':ctx['decision'],'exact_request':item['request'],'source_preflight':pin,'autonomous_action_key':key,'checked_at':w.utc_timestamp(),'external_execution_department':ctx['role'],'assistant_approval_required':False,'platform_permission_issued':False}
        if requested.get('consume_approval'):
            if op=='edge_deploy':
                apr=w.effective_approvals(root).get(reference(ctx,state['candidate_commit'],state['main_sha']));need(apr and apr.get('status')=='active'and apr.get('source_preflight')==pin,'one exact current unconsumed R3 run-bound approval reference')
                need(w._parse_observed_at(apr['platform_binding']['expiresAt'])>dt.datetime.now(dt.timezone.utc),'R3 approval expired, do not extend old permission')
                w.append_jsonl_locked(Path(root)/w.APPROVAL_LEDGER,{**apr,'status':'consumed','consumed_at':w.utc_timestamp()})
            value.update(status='allow',actual_action_allowed=True,approval_status='consumed_for_original_exact_autonomous_action',decision_id='pol-'+w.sha256_value([value,key])[:20]);w.append_jsonl_locked(Path(root)/w.POLICY_DECISIONS,value)
    return value,[Path(root)/w.POLICY_DECISIONS]

def record_approval(root,**kwargs):
    if kwargs.get('revoke'):
        ctx=records(root,kwargs['task_id'])[0]
        with w.workflow_lock(root):
            old=w.effective_approvals(root).get(kwargs.get('approval_id'))
            need(old and old.get('status')=='active'and old.get('approval_basis')=='verified_original_goal_external_WEB_source_v1'
              and old.get('delegated_HQ_decision')==ctx['decision']and all(old.get(k)==kwargs.get(k)for k in ('task_id','action_id','action_class','scope')),'exact original still-active own reference only')
            value={**old,'status':'revoked','changed_at':w.utc_timestamp()};w.append_jsonl_locked(Path(root)/w.APPROVAL_LEDGER,value)
        return {**value,'result':'revoked','platform_allowlist_changed':False},[Path(root)/w.APPROVAL_LEDGER]
    pin=w.file_digest(root,kwargs['source_evidence']);item=a.document(root,pin);req=a.document(root,item.get('request'));ctx,op,state=validate_request(root,req)
    need(op=='edge_deploy'and all(kwargs.get(k)==req[k]for k in ('task_id','action_id','action_class','scope')),'only current exact external WEB pending R3 action')
    selected,_,registered,_=preflight(root,req['task_id'],req['action_id'],req['action_class'],req['scope'],ctx['role']);need(selected['request']==item['request']and registered==pin,'normal genuine preflight event')
    human=a.document(root,ctx['authorization']);need(kwargs.get('source_thread_id')==human['source_thread_id']and kwargs.get('source_message_ref')==human['message']['id'],'real original human grant and verified HQ decision, not a new owner signature')
    now=dt.datetime.now(dt.timezone.utc);at=w._parse_observed_at(req.get('observed_at'));need(at and 0<=(now-at).total_seconds()<=300,'fresh actual pending run')
    apr=reference(ctx,state['candidate_commit'],state['main_sha']);need(kwargs.get('approval_id','')in {'',apr},'source-derived reference only')
    with w.workflow_lock(root):
        old=w.effective_approvals(root).get(apr)
        if old:need(old.get('status')=='active'and old.get('source_preflight')==pin,'consumed/revoked/unknown reference cannot be reissued');return {**old,'result':'duplicate_ignored'},[Path(root)/w.APPROVAL_LEDGER]
        binding={'version':'r3-release-approval/v1','taskId':ctx['task'],'actionId':req['action_id'],'actionClass':'site_publish','scope':ctx['edge_scope'],'approvalId':apr,'expectedSha':state['main_sha'],'repository':ctx['repository'],'repositoryId':1248188229,'ref':'refs/heads/main','workflowRef':ctx['repository']+'/'+R3+'@refs/heads/main','environment':'production-supabase','eventName':'workflow_dispatch','runId':str(state['r3_run']['id']),'runAttempt':1,'singleUse':True,'status':'active','issuedAt':now.isoformat(),'expiresAt':(now+dt.timedelta(minutes=15)).isoformat()}
        binding['payloadSha256']=hashlib.sha256(json.dumps(binding,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
        value={'schema_version':'1.0','approval_id':apr,'task_id':ctx['task'],'action_id':req['action_id'],'action_class':'site_publish','scope':ctx['edge_scope'],'status':'active','single_use':True,'granted_by':'operations','granted_at':w.utc_timestamp(),'source_thread_id':human['source_thread_id'],'source_message_ref':human['message']['id'],'approval_basis':'verified_original_goal_external_WEB_source_v1','original_human_authorization_pin':ctx['authorization'],'delegated_HQ_decision':ctx['decision'],'source_preflight':pin,'execution_department':ctx['role'],'platform_binding':binding,'platform_permission_issued':False}
        w.append_jsonl_locked(Path(root)/w.APPROVAL_LEDGER,value)
    return {**value,'result':'recorded'},[Path(root)/w.APPROVAL_LEDGER]

def request_base(root,task,op,state):
    ctx=execution_context(root,task,state);need(op in OPS,'registered operation')
    head=state.get('candidate_commit');main=state.get('main_sha')if op in {'edge_deploy','r3_dispatch','pages_deploy'}else None
    need(re.fullmatch('[0-9a-f]{40}',str(head))is not None,'real full candidate head required, no missing or predicted value')
    req={'task_id':task,'sender_department':ctx['role'],'department':ctx['role'],'action_id':action_id(ctx,op,head,main),
      'action_class':OPS[op],'scope':scopes(ctx,op),'source_project_id':a.PROJECT,'execution_project_id':ctx['binding']['project_id'],
      'operation':op,'state':state,'observed_at':state.get('observed_at'),'authorization_changes':[],
      'exact_HQ_production_decision':ctx['decision']}
    req['desired']=intent(root,req,check_desired=False)[3];return req

def build_preflight(root,base_path,facts_native,facts_command,self_native,self_command,backup_path,out_path):
    base=a.document(root,w.file_digest(root,base_path));ctx,op,state,_=intent(root,base)
    need(not any(k in base for k in ('facts','self_check','backup','rollback')),'intent source before evidence, no circular hash')
    raw=native(root,ctx,w.file_digest(root,facts_native),facts_command);need(json.loads(raw).get('state')==state,'actual original WEB facts must equal this request')
    digest=w.sha256_value(base);actual_self=native(root,ctx,w.file_digest(root,self_native),self_command)
    need(digest.encode()in actual_self and ctx['decision']['sha256'].encode()in actual_self,'real current WEB selfcheck, not SYS signature')
    out=w.safe_path(root,out_path);need(not out.exists(),'preserve prior preflight');directory=out.parent/(out.stem+'-evidence');need(not directory.exists(),'new exact evidence directory');directory.mkdir(parents=True)
    request=dict(base);identity={k:base[k]for k in ('task_id','department','action_id','action_class','scope')};identity['intent_sha256']=digest
    docs={'facts':{**identity,'state':state,'actual_native':w.file_digest(root,facts_native),'command_id':facts_command},
      'self_check':{**identity,'status':'PASS','actual_native':w.file_digest(root,self_native),'command_id':self_command},
      'backup':{**identity,'source_backup':w.file_digest(root,backup_path)},
      'rollback':{**identity,'production_recovery':ctx['rollback'],'unknown_effect_replay_allowed':False}}
    for key,value in docs.items():
        path=directory/(key+'.json');w.atomic_write_json(path,value);request[key]=w.file_digest(root,str(path.relative_to(root)))
    path=directory/'request.json';w.atomic_write_json(path,request);validate_request(root,request)
    item={'schema':'professional-external-WEB-fresh-preflight/v1','task_id':ctx['task'],'request':w.file_digest(root,str(path.relative_to(root)))}
    w.atomic_write_json(out,item);return {'state':'prepared_actual_preflight_input_not_a_permission','input':w.file_digest(root,out_path),'request':item['request']}

def describe(root,task):
    ctx=records(root,task)[0]
    return {'task_id':task,'registered_source':ctx['registration'],'role':ctx['role'],'binding':ctx['binding'],
      'decision':ctx['decision'],'original_real_head':ctx['commit'],'branch':ctx['branch'],'source_paths':ctx['paths'],
      'operations':{op:{'action_class':kind,'scope':scopes(ctx,op),'facts_required_at_actual_stage':True}for op,kind in OPS.items()},
      'minimum_platform_guards':{'all_exact_head_required_CI':sorted(CHECKS),'R3_workflow':R3,'Pages_workflow':PAGES,'R3_run_attempt':1,'environment':'production-supabase','approval_TTL_minutes':15,'single_use':True},
      'adopted_increments':[{'commit':x['commit'],'base':x['base'],'tree':x['tree'],'branch':x['branch'],'worktree':x['worktree'],'source':x['increment_registration'],'operations':x['increment_allowed_operations']}for x in __import__('professional_web_increment').sources(root,ctx)],
      'future_PR_merge_SHA_run_or_version_provided':False,'actual_external_action_performed':False}

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=['describe','request-base','build-preflight']);parser.add_argument('--task-id',required=True)
    parser.add_argument('--operation',choices=sorted(OPS));parser.add_argument('--state');parser.add_argument('--base');parser.add_argument('--facts-native');parser.add_argument('--facts-command');parser.add_argument('--self-native');parser.add_argument('--self-command');parser.add_argument('--backup');parser.add_argument('--output')
    args=parser.parse_args();root=Path(__file__).resolve().parents[1]
    try:
        with w.request_validation_context():
            if args.command=='describe':result=describe(root,args.task_id)
            elif args.command=='request-base':
                result=request_base(root,args.task_id,args.operation,a.document(root,w.file_digest(root,args.state)));need(args.output,'new project input output path required');out=w.safe_path(root,args.output);need(not out.exists(),'preserve original request');w.atomic_write_json(out,result);result={'state':'request_base_prepared_no_permission','input':w.file_digest(root,args.output),'intent_sha256':w.sha256_value(result)}
            else:result=build_preflight(root,args.base,args.facts_native,args.facts_command,args.self_native,args.self_command,args.backup,args.output)
        print(json.dumps(result,ensure_ascii=False,indent=2))
    except (w.WorkflowError,ValueError,KeyError,OSError)as error:parser.exit(1,str(error)+'\n')
