"""Authenticated external WEB production continuation. No website/network writes."""
from pathlib import Path
import argparse,datetime as dt,hashlib,json,re,subprocess
import workflow_control as w
import department_autonomy as a
import professional_cms_execution as cms
from professional_cms_issuer import external
EVENT='professional_WEB_production_source'
SCHEMA='professional-external-WEB-production-source/v1'
CODE_SCHEMA='professional-external-WEB-owner-followon-source/v2'
CODE_OPS=('git_push','pull_request','official_ci','merge','pages_deploy')
CODE_CI_PATHS={
 'furniture-page-pr-checks':'.github/workflows/furniture-page-pr-ci.yml',
 'interaction-standards':'.github/workflows/interaction-standards-ci.yml',
 'r3-managed-cms-pr-checks':'.github/workflows/r3-managed-cms-pr-ci.yml'}
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

def _patch_delta(raw):
    """Compare text patch effects, ignoring only Git context/index formatting."""
    result={};path=None;removed=[];added=[]
    def finish():
        if path is not None and (removed or added):result[path].append((list(removed),list(added)))
    for line in raw.decode('utf-8').splitlines():
        if line.startswith('diff --git '):
            finish();removed=[];added=[]
            pair=re.fullmatch(r'diff --git ([ab])/(.+) ([ab])/(.+)',line);need(pair and pair[1]!=pair[3]and pair[2]==pair[4],'ordinary same-path text patch only')
            path=pair[2];result[path]=[]
        elif line.startswith('@@'):
            finish();removed=[];added=[]
        elif line.startswith('-')and not line.startswith('---'):removed.append(line[1:])
        elif line.startswith('+')and not line.startswith('+++'):added.append(line[1:])
        elif line.startswith(('GIT binary patch','Binary files','rename ','copy ')):need(False,'binary/rename/copy requires its own exact source review')
    finish();return result


def _patch_effect(value):return {p:([line for removed,_ in hunks for line in removed],[line for _,added in hunks for line in added])for p,hunks in value.items()}

def code_pin(root,pin):
    need(isinstance(pin,dict)and set(pin)=={'path','sha256','size'},'exact local source pin')
    path=Path(pin['path']);base=Path(root).resolve();target=(base/path).resolve()
    need(target.is_relative_to(base)and not path.is_symlink()and '..'not in path.parts,'same-project source path only')
    normalized={**pin,'path':str(target.relative_to(base))}
    need(w.file_digest(root,normalized['path'])==normalized,'exact original local source bytes')
    return normalized

def code_document(root,pin):return a.document(root,code_pin(root,pin))
def code_same_pin(root,left,right):return code_pin(root,left)==code_pin(root,right)

def validate_code_source(root,snapshot,item):
    """New real owner/HQ follow-on authority; never rewrite a closed local goal."""
    import goal_delivery_runtime as g
    import xml.etree.ElementTree as ET
    a.authority(root)
    frozen=a.document(root,snapshot.get('goal_contract'));goal=snapshot['goal_delivery']
    need(item.get('schema')==CODE_SCHEMA and item.get('task_id')==snapshot['task_id']
         and item.get('original_goal_contract')==snapshot['goal_contract']
         and snapshot.get('current_state')not in {'failed','cancelled','canceled'}
         and all(goal.get(k)==frozen.get(k)for k in ('primary_owner','producer_departments','authorized_scope','human_authorization')),
         'unchanged original contract/owner/producers; no failed or cancelled goal revival')
    owner=goal['primary_owner'];scope=item.get('scope')
    need(a.professional(root,owner)and scope in goal['authorized_scope']and owner in goal['producer_departments'], 'original professional business owner and frozen scope')
    bundle=a.document(root,item['source_bundle']);decision=code_document(root,bundle['source_decision']);human=g._native_document(root,code_pin(root,bundle['human_source']))
    need(bundle.get('schema')=='WEB-exact-two-original-production-source-consumer-dependency/v1'
         and decision.get('schema')=='HQ-owner-complete-open-goals-bounded-recovery-decision/v1'
         and code_same_pin(root,decision.get('owner_native'),bundle['human_source'])and decision.get('project_root')==str(Path(root).resolve()), 'real bounded HQ follow-on and original human source')
    hq=w.department_registry(root)['operations']['chat_binding'];h=decision['source_human']
    need(all(human.get('thread',{}).get(k)==hq[v]for k,v in {'id':'task_id','title':'title','cwd':'cwd'}.items())
         and h.get('thread_id')==hq['task_id'], 'actual fixed HQ human source identity')
    pairs=[(t,m)for t in human.get('turns',[])if t.get('id')==h.get('turn_id')for m in t.get('items',[])if m.get('id')==h.get('message_id')]
    need(len(pairs)==1 and pairs[0][1].get('type')=='userMessage'
         and ''.join(c.get('text','')for c in pairs[0][1].get('content',[])if c.get('type')=='text').strip()==h.get('exact_text')
         and type(pairs[0][0].get('startedAt'))in {int,float},'real human words/message/chronology, not an assistant approval')
    rows=[x for x in decision.get('work',[])if x.get('key')==item.get('decision_work_key')]
    need(len(rows)==1 and rows[0].get('owner')==owner and rows[0].get('executor')==bundle['WEB_identity']['department']
         and all(token in rows[0].get('scope','')for token in ('commit/push/PR/CI/merge/deploy','回滚')),
         'same original owner, exact HQ code-release work and allowed sequence')
    selected=[x for x in bundle['selected_versions']if x.get('task_id')==snapshot['task_id']]
    need(len(selected)==1 and selected[0].get('business_scope')==scope,'unique exact source task/scope; never another batch item')
    binding=g._collaboration_binding(root,snapshot,bundle['WEB_identity']['department']);b=bundle['WEB_identity']
    need(binding and all(binding.get(k)==b[v]for k,v in {'thread_id':'thread_id','title':'title','cwd':'cwd','project_id':'project_id'}.items())
         and binding['project_id']!=a.PROJECT and b['department']not in goal['producer_departments']
         and any(x.get('scope')==scope and x.get('target_department')==b['department']for x in goal.get('collaboration_scopes',[])),
         'real declared external WEB; never replace a professional producer or project')
    native_page=g._native_document(root,item['actual_WEB_native'])
    need(all(native_page.get('thread',{}).get(k)==binding[v]for k,v in {'id':'thread_id','title':'title','cwd':'cwd'}.items()),'original WEB completed source identity')
    completed=[]
    for turn in native_page.get('turns',[]):
        if turn.get('status')!='completed' or turn.get('error'):continue
        echoes=[];reports=[]
        for msg in turn.get('items',[]):
            output=msg.get('output',{});text=output.get('text','')if isinstance(output,dict)else ''
            if msg.get('type')=='functionCallOutput'and '<codex_delegation>'in text:
                try:xml=ET.fromstring(text)
                except ET.ParseError:continue
                body=xml.findtext('input')or''
                if xml.findtext('source_thread_id')==hq['task_id']and bundle['source_decision']['sha256']in body and snapshot['task_id']in body and scope.split(':')[0]=='project':echoes.append(msg)
            if msg.get('type')=='commandExecution'and msg.get('status')=='completed'and msg.get('exitCode')==0:
                try:raw=w._completion_execution_output(msg)
                except (ValueError,w.WorkflowError):continue
                if item['source_bundle']['sha256'].encode()in raw and Path(msg.get('cwd','')).resolve().is_relative_to(Path(binding['cwd']).resolve()):reports.append(msg)
        if len(echoes)==len(reports)==1 and any(m.get('type')=='agentMessage'and m.get('phase')=='final_answer'and m.get('text','').strip()for m in turn.get('items',[])):completed.append(turn)
    need(len(completed)==1 and pairs[0][0]['startedAt']<=completed[0]['startedAt']<=completed[0]['completedAt']<=dt.datetime.now(dt.timezone.utc).timestamp(),
         'actual HQ delivery then original WEB completed exact version-source report')
    row=selected[0];typed=external(root,row['typed_candidate'],binding);initial=code_document(root,row['request']);denied=code_document(root,row['normal_actual_result'])
    need(initial.get('task_id')==typed.get('task_id')==snapshot['task_id']and initial.get('scope')==scope
         and initial.get('sender_department')==initial.get('department')==b['department']
         and initial.get('action_class')=='git_push'and code_same_pin(root,initial.get('actual_HQ_followon_decision'),bundle['source_decision'])
         and not initial.get('authorization_changes')and denied.get('exit')==1
         and json.loads(denied.get('stdout','{}')).get('reason')=='original goal participant required; no authority delegation by metadata'
         and json.loads(denied.get('stdout','{}')).get('external_permission_issued')is False,'one real exact initial source request/refusal; no permission inferred')
    meta=initial['state'];files=typed.get('files',[]);paths={x['path']:x['sha256']for x in files}
    need(files and len(paths)==len(files)and all(not Path(p).is_absolute()and '..'not in Path(p).parts for p in paths),'complete unique original selected source map')
    ctx={'root':str(Path(root).resolve()),'task':snapshot['task_id'],'scope':scope,'owner':owner,'role':b['department'],'binding':binding,
         'decision':code_pin(root,bundle['source_decision']),'authorization':code_pin(root,bundle['human_source']),'contract':snapshot['goal_contract'],
         'worktree':typed['worktree'],'site':b['website_git_root'],'branch':typed['branch'],'commit':typed['head'],'base':typed['parent'],'tree':typed['tree'],'paths':paths,
         'source_bundle':item['source_bundle'],'initial_request':code_pin(root,row['request']),'code_only_release':True,'allowed_operations':CODE_OPS,
         'repository':bundle['account']['repo'],'repository_id':bundle['account']['repo_id'],'actor_id':bundle['account']['id'],
         'backup':item['source_backup'],'rollback':item['rollback_runbook'],'pages_scope':'company.example:pages:production'}
    need(Path(ctx['worktree']).resolve().is_relative_to(Path(binding['cwd']).resolve())and Path(ctx['site']).resolve().is_relative_to(Path(binding['cwd']).resolve())
         and all(meta.get(k)==ctx[v]for k,v in {'candidate_commit':'commit','candidate_parent':'base','candidate_base':'base','candidate_tree':'tree','branch':'branch','worktree':'worktree'}.items()),'real initial worktree/head/parent/tree/branch')
    need(git(ctx,'show','-s','--format=%H %P %T',ctx['commit']).decode().strip()==' '.join([ctx['commit'],ctx['base'],ctx['tree']])
         and set(git(ctx,'diff','--name-only',ctx['base'],ctx['commit']).decode().splitlines())==set(paths),'actual exact Git objects and changed paths')
    repo=git(ctx,'config','--get','remote.origin.url').decode().strip();need(repo in {'https://github.com/'+ctx['repository']+'.git','https://github.com/'+ctx['repository'],'user-3de132cd98be@example.invalid:'+ctx['repository']+'.git'},'actual original repository only')
    need(bundle['account']['login']==ctx['repository'].split('/')[0]and type(ctx['actor_id'])is int and ctx['actor_id']>0,'original exact account/repository identity')
    for path,sha in paths.items():need(hashlib.sha256(git(ctx,'show',ctx['commit']+':'+path)).hexdigest()==sha,'exact actual typed candidate bytes')
    forward=_external_bytes(typed['forward'],binding);inverse=_external_bytes(typed['inverse'],binding);delta=_delta(ctx,ctx['base'],ctx['commit'])
    need(_patch_effect(_patch_delta(forward))==_patch_effect(delta)and _patch_effect(_patch_delta(inverse))=={p:(added,removed)for p,(removed,added)in _patch_effect(delta).items()},'exact original forward/inverse source effects')
    backup=a.document(root,ctx['backup']);need(backup.get('task_id')==ctx['task']and backup.get('source_commit')==ctx['commit']
         and backup.get('source_base')==ctx['base']and backup.get('source_tree')==ctx['tree']and backup.get('forward')==typed['forward']and backup.get('inverse')==typed['inverse'], 'real original code source backup, never a CMS function backup')
    need(w.file_digest(root,ctx['rollback']['path'])==ctx['rollback'],'immutable exact source recovery runbook')
    suffix='-'+ctx['commit'][:12]+'-git-push-v1';need(initial['action_id'].endswith(suffix),'source-derived original action prefix');ctx['prefix']=initial['action_id'][:-len(suffix)]
    need(not w.validate_workflow_events(root,ctx['task']),'intact original workflow history')
    return ctx


def head_value(request):return request['state']['candidate_commit']
def _backup_bytes(root,pin,ctx):
    if Path(pin['path']).is_absolute():return _external_bytes(pin,ctx['binding'])
    need(w.file_digest(root,pin['path'])==pin,'real project-local backup bytes');return w.safe_path(root,pin['path']).read_bytes()

def validate_source(root,snapshot,item):
    import goal_delivery_runtime as g
    import goal_source_recovery as recovery
    import result_coordination as rc
    if item.get('schema')=='professional-standing-CMS-WEB-channel-source/v1':
        from professional_cms_channel import validate
        return validate(root,snapshot,item)
    if item.get('schema')==CODE_SCHEMA:return validate_code_source(root,snapshot,item)
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
    return action_class in {'site_ci_prepare','site_publish','git_push'} and any(e.get('task_id')==task and EVENT in e.get('details',{})for e in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS))
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
def validate_code_recovery(ctx,state):
    root=Path(ctx['root']);proof=a.document(root,state.get('code_recovery_source'))
    need(proof.get('schema')=='professional-own-code-release-effect-recovery/v1'and proof.get('task_id')==ctx['task']
         and proof.get('department')==ctx['role']and proof.get('source_registration')==ctx['registration'], 'same real own code release recovery source')
    rows=[r for r in w.read_jsonl(root/w.POLICY_DECISIONS)if r.get('decision_id')==proof.get('forward_policy_decision_id')]
    need(len(rows)==1 and rows[0].get('status')=='allow'and rows[0].get('task_id')==ctx['task']
         and rows[0].get('department')==ctx['role']and rows[0].get('delegated_HQ_decision')==ctx['decision'], 'real original single-use forward policy, not an unrelated grant')
    request=a.document(root,rows[0]['exact_request']);need(request.get('operation')in {'merge','pages_deploy'},'real published/merged own source only')
    output=json.loads(native(root,ctx,proof.get('actual_native'),proof.get('command_id')))
    observed=w._parse_observed_at(output.get('observed_at'));issued=w._parse_observed_at(rows[0].get('checked_at'))
    need(output.get('task_id')==ctx['task']and output.get('repository')==ctx['repository']
         and output.get('policy_decision_id')==rows[0]['decision_id']and output.get('own_candidate_commit')==request['state']['candidate_commit']
         and output.get('current_main_sha')==state['candidate_base']and observed is not None and issued is not None
         and issued<=observed<=dt.datetime.now(dt.timezone.utc),'actual ordered original WEB own-release and current-main readback')
    need(git(ctx,'merge-base',output['own_candidate_commit'],output['current_main_sha']).decode().strip()==output['own_candidate_commit'], 'real own released source ancestry')

def candidate(ctx,state):
    if ctx.get('standing_CMS_channel'):
        from professional_cms_channel import candidate as channel_candidate
        return channel_candidate(ctx,state)
    head=state.get('candidate_commit');base=state.get('candidate_base',ctx['base']);need(re.fullmatch('[0-9a-f]{40}',str(head)),'real full candidate head')
    need(state.get('source_mode','forward')in {'forward','remove_own_delta'},'known exact source mode only')
    if ctx.get('ordinary_increment'):
        parents=git(ctx,'show','-s','--format=%P',head).decode().split()
        need(parents and state.get('candidate_parent')==parents[0],'actual ordinary successor parent, separate from cumulative base')
        if state.get('source_mode','forward')=='forward':
            for path in ctx['paths']:
                need(git(ctx,'ls-tree',head,'--',path).split()[:1]==git(ctx,'ls-tree',ctx['commit'],'--',path).split()[:1], 'ordinary source file modes remain exact')
    if ctx.get('increment_registration')and not ctx.get('ordinary_increment'):
        if ctx.get('git_parent'):need(state.get('candidate_parent')==ctx['git_parent'],'actual Git parent is required separately from cumulative integration base')
        need(head==ctx['commit']and base==ctx['base']and state.get('source_mode','forward')=='forward','exact actually adopted metadata increment only');return head,base
    if head==ctx['commit']:
        need(base==ctx['base']and state.get('source_mode','forward')=='forward','original candidate base; recovery needs a real inverse commit');return head,base
    need(re.fullmatch('[0-9a-f]{40}',str(base))and set(git(ctx,'diff','--name-only',base,head).decode().splitlines())<=set(ctx['paths']), 'same original paths only in causal successor')
    need(git(ctx,'merge-base',ctx['base'],base).decode().strip()==ctx['base'],'real later base ancestry')
    actual=_delta(ctx,base,head);original=_delta(ctx,ctx['base'],ctx['commit'])
    tests=set()if ctx.get('ordinary_increment')else {p for p in ctx['paths']if '.test.'in p or p=='.github/workflows/r3-managed-cms-pr-ci.yml'}
    recovery=state.get('source_mode')=='remove_own_delta'
    expected={p:[(added,removed)for removed,added in hunks]if recovery else hunks for p,hunks in original.items()}
    need(all(actual[p]==expected[p]for p in ctx['paths']if p not in tests),
         'same exact production patch, or its own inverse; only related CI/test compatibility may differ')
    if recovery and ctx.get('code_only_release'):
        validate_code_recovery(ctx,state)
    if recovery and not ctx.get('code_only_release'):
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
      and ((request.get('exact_standing_CMS_channel_source')==ctx['registration'] and not request.get('exact_HQ_production_decision'))
           if ctx.get('standing_CMS_channel') else request.get('exact_HQ_production_decision')==ctx['decision']),
         'exact actual external WEB/projects/source; no actor substitution, mislabeled HQ decision or expansion')
    return ctx
def working_source(ctx,head):
    need(git(ctx,'rev-parse','HEAD').decode().strip()==head
         and git(ctx,'branch','--show-current').decode().strip()==ctx['branch']
         and not git(ctx,'status','--porcelain').strip(),
         'fresh real clean worktree/head/branch CAS; preserve parallel WIP and never push another HEAD')
def intent(root,req,check_desired=True):
    ctx=static_intent(root,req);op=req.get('operation');need(op in OPS,'only registered complete-stage operations')
    if ctx.get('code_only_release'):need(op in ctx['allowed_operations'],'code-only source excludes CMS/R3/Edge/DB/account operations')
    if ctx.get('increment_registration'):need(op in ctx['increment_allowed_operations'],'metadata increment needs no CMS/Edge/R3/manual Pages action')
    state=req.get('state',{});head,base=candidate(ctx,state);main=state.get('main_sha')if op in {'edge_deploy','r3_dispatch','pages_deploy'}else None
    working_source(ctx,head)
    if op in {'edge_deploy','r3_dispatch','pages_deploy'}:
        need(re.fullmatch('[0-9a-f]{40}',str(main))is not None,'actual final main is required at this stage, never future or missing SHA')
    need(req.get('action_class')==OPS[op]and req.get('scope')==scopes(ctx,op)
      and req.get('action_id')==action_id(ctx,op,head,main),'exact source-derived operation/action/business or physical scope')
    need(state.get('repository')==ctx['repository'] and state.get('repository_id')==ctx.get('repository_id',1248188229)
      and state.get('branch')==ctx['branch'],'actual original repository/branch')
    if ctx.get('increment_registration'):
        need(state.get('worktree',ctx['worktree'])==ctx['worktree'],'current native/source worktree, never caller old-context fill')
        need(state.get('actor',{}).get('id')==ctx['increment_actor_id'],'exact authenticated original actor')
    if ctx.get('existing_pull_number'):
        need(not ctx.get('ordinary_increment')or op!='pull_request','existing original PR is reused; never create a duplicate PR')
        pr=state.get('pull_request',{})
        allowed_heads={ctx['git_parent'],head,ctx['commit']}
        need(pr.get('number')==ctx['existing_pull_number']and pr.get('base_branch')=='main'and pr.get('head_branch')==ctx['branch']
             and pr.get('head_sha')in allowed_heads,'same actual existing PR only; no creation or replacement')
        if op=='git_push':need(state.get('remote_branch_sha')in allowed_heads,'fresh original branch effect/CAS; unknown head must be read back')
    actor=state.get('actor',{});need(not (ctx.get('code_only_release') or ctx.get('standing_CMS_channel')) or actor.get('id')==ctx['actor_id'],'original exact source actor ID')
    need(actor.get('login')==ctx['repository'].split('/')[0]and type(actor.get('id'))is int and actor['id']>0,'original authenticated repository account, no substituted actor')
    desired={'repository':ctx['repository'],'branch':ctx['branch'],'head':head,'force':False,'admin_bypass':False}
    if op=='git_push':need(state.get('remote_main_sha')==base,'fresh main advanced; same-semantic source rebase required before first push')
    if op in {'pull_request','merge'}:desired['base_branch']='main'
    if op in {'official_ci','merge'}:
        checks=state.get('checks',[]);need({x.get('name')for x in checks}>=CHECKS
          and all(x.get('head_sha')==head and x.get('status')=='completed'and x.get('conclusion')=='success'and x.get('id')for x in checks), 'all real required exact-head official checks must succeed')
    if ctx.get('code_only_release')and op in {'official_ci','merge'}:
        for path in CODE_CI_PATHS.values():
            config=git(ctx,'show',head+':'+path).decode();need(re.search(r"(?m)^\s*node-version:\s*['\"]?22['\"]?\s*(?:#.*)?$",config),'actual same-head official CI must retain Node22')
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
        if name=='backup'and ctx.get('code_only_release'):
            backup=a.document(root,value.get('source_backup'));need(backup.get('task_id')==ctx['task']and backup.get('source_commit')==head_value(req)and backup.get('source_base')==state.get('candidate_base',ctx['base']), 'actual current code-only source backup/head/base')
            need(_patch_effect(_patch_delta(_backup_bytes(root,backup['forward'],ctx)))==_patch_effect(_delta(ctx,backup['source_base'],backup['source_commit'])),'actual current source forward backup')
            expected=_delta(ctx,backup['source_base'],backup['source_commit']);need(_patch_effect(_patch_delta(_backup_bytes(root,backup['inverse'],ctx)))=={p:(added,removed)for p,(removed,added)in _patch_effect(expected).items()},'actual current source inverse backup')
        if name=='backup'and not ctx.get('code_only_release'):
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
    ctx0=records(root,request['task_id'])[0]
    if ctx0.get('code_only_release')and request==a.document(root,ctx0['initial_request']):
        return {'schema':'goal-authorization-precheck/v1','task_id':ctx0['task'],'status':'within_original_authorization','reasons':['real_owner_HQ_code_only_followon_source'],'source_registration':ctx0['registration'],'original_authorization':ctx0['authorization'],'needs_human_confirmation':False,'actual_action_allowed':False,'external_permission_issued':False,'next_owner':ctx0['role'],'next_action':'use normal request-base with original-executor fresh facts and single-use policy'}
    ctx=static_intent(root,request);op=request.get('operation');need(op in OPS,'known original production operation')
    if request.get('state'):intent(root,request)
    else:
        need(not ctx.get('code_only_release') and not ctx.get('standing_CMS_channel'),'exact source request, or use normal current-state request-base')
        repair=a.document(root,ctx['repair']);original=a.document(root,repair['actual_failing_request'])
        need(all(request.get(k)==original.get(k)for k in ('action_id','action_class','scope','operation','desired','committed_source')),'exact initial source intent, or use normal current-state request for later stages')
    return {'schema':'goal-authorization-precheck/v1','task_id':ctx['task'],'status':'within_original_authorization',
      'reasons':['verified_original_external_WEB_full_production_source'],'original_authorization':ctx['authorization'],
      **({'standing_CMS_authority':ctx['decision'],'authority_department':ctx['authority_department']} if ctx.get('standing_CMS_channel')
         else {'HQ_delegated_decision':ctx['decision']}),'source_registration':ctx['registration'],'needs_human_confirmation':False,
      'actual_action_allowed':False,'external_permission_issued':False,'next_owner':ctx['role'],
      'next_action':'fresh normal original-executor preflight/policy and exact actual platform stage; no general approval repeat'}

def policy(root,requested):
    item,req,pin,ctx=preflight(root,requested['task_id'],requested['action_id'],requested['action_class'],requested['scope'],requested['department'])
    need(requested.get('source_project_id')==a.PROJECT and requested.get('payload_sha256')==item['request']['sha256']and not requested.get('target_department')and not requested.get('approval_id'),'exact request hash and original action, no borrowed approval/role')
    state=req['state'];op=req['operation'];observed=w._parse_observed_at(req.get('observed_at'))
    need(observed and 0<=(dt.datetime.now(dt.timezone.utc)-observed).total_seconds()<=300,'fresh real execution facts; stored authority does not expire')
    if op=='pull_request'and ctx.get('existing_pull_number'):
        return {'status':'existing_original_PR_readback_no_new_create','pull_number':ctx['existing_pull_number'],'actual_action_allowed':False,'source_request':item['request']},[]
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
        if ctx.get('standing_CMS_channel'):
            value.pop('delegated_HQ_decision');value.update(standing_CMS_authority=ctx['decision'],authority_department=ctx['authority_department'],standing_authorization_id=ctx['standing_authorization_id'])
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
            need(old and old.get('status')=='active'and old.get('approval_basis')==('verified_professional_standing_CMS_WEB_source_v1' if ctx.get('standing_CMS_channel') else 'verified_original_goal_external_WEB_source_v1')
              and old.get('standing_CMS_authority' if ctx.get('standing_CMS_channel') else 'delegated_HQ_decision')==ctx['decision']and all(old.get(k)==kwargs.get(k)for k in ('task_id','action_id','action_class','scope')),'exact original still-active own reference only')
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
        if ctx.get('standing_CMS_channel'):
            value.pop('delegated_HQ_decision');value.update(approval_basis='verified_professional_standing_CMS_WEB_source_v1',granted_by=ctx['authority_department'],standing_CMS_authority=ctx['decision'],authority_department=ctx['authority_department'],standing_authorization_id=ctx['standing_authorization_id'])
        w.append_jsonl_locked(Path(root)/w.APPROVAL_LEDGER,value)
    return {**value,'result':'recorded'},[Path(root)/w.APPROVAL_LEDGER]

def request_base(root,task,op,state):
    ctx=execution_context(root,task,state);need(op in OPS,'registered operation')
    if ctx.get('code_only_release'):need(op in ctx['allowed_operations'],'code-only release excludes R3/Edge/CMS')
    head=state.get('candidate_commit');main=state.get('main_sha')if op in {'edge_deploy','r3_dispatch','pages_deploy'}else None
    need(re.fullmatch('[0-9a-f]{40}',str(head))is not None,'real full candidate head required, no missing or predicted value')
    req={'task_id':task,'sender_department':ctx['role'],'department':ctx['role'],'action_id':action_id(ctx,op,head,main),
      'action_class':OPS[op],'scope':scopes(ctx,op),'source_project_id':a.PROJECT,'execution_project_id':ctx['binding']['project_id'],
      'operation':op,'state':state,'observed_at':state.get('observed_at'),'authorization_changes':[],
      **({'exact_standing_CMS_channel_source':ctx['registration']} if ctx.get('standing_CMS_channel')
         else {'exact_HQ_production_decision':ctx['decision']})}
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

def source_backup(root,task,state,out_path):
    ctx=execution_context(root,task,state);need(ctx.get('code_only_release'),'code-only source backup entry')
    head,base=candidate(ctx,state);working_source(ctx,head)
    directory=w.safe_path(root,out_path);need(not directory.exists(),'preserve original source backups; new actual source directory')
    directory.mkdir(parents=True)
    pins={}
    for name,left,right in [('forward',base,head),('inverse',head,base)]:
        path=directory/(name+'.patch');path.write_bytes(git(ctx,'diff','--binary',left,right,'--',*ctx['paths']));pins[name]=w.file_digest(root,str(path.relative_to(root)))
    value={'schema':'professional-code-release-source-backup/v1','task_id':task,'source_commit':head,'source_base':base,
           'source_tree':git(ctx,'rev-parse',head+'^{tree}').decode().strip(),**pins,'source_registration':ctx['registration'],
           'coverage':'exact current source Git objects/patch only; actual platform before-version remains in executor facts',
           'platform_permission_issued':False}
    path=directory/'SOURCE-BACKUP.json';w.atomic_write_json(path,value)
    return {'source_backup':w.file_digest(root,str(path.relative_to(root))),'external_permission_issued':False}

def describe(root,task):
    ctx=records(root,task)[0]
    return {'task_id':task,'registered_source':ctx['registration'],'role':ctx['role'],'binding':ctx['binding'],
      **({'standing_CMS_authority':ctx['decision'],'authority_department':ctx['authority_department'],'standing_authorization_id':ctx['standing_authorization_id']} if ctx.get('standing_CMS_channel') else {'decision':ctx['decision']}),
      'original_real_head':ctx['commit'],'branch':ctx['branch'],'source_paths':ctx['paths'],
      'operations':{op:{'action_class':kind,'scope':scopes(ctx,op),'facts_required_at_actual_stage':True}for op,kind in OPS.items()if not ctx.get('code_only_release')or op in ctx['allowed_operations']},
      'minimum_platform_guards':({'all_exact_head_required_CI':sorted(CHECKS),'Pages_workflow':PAGES,'fresh_execution_seconds':300,'single_use':True,'excluded_operations':['CMS','R3','Edge','DB','auth','account','Ads']}if ctx.get('code_only_release')else{'all_exact_head_required_CI':sorted(CHECKS),'R3_workflow':R3,'Pages_workflow':PAGES,'R3_run_attempt':1,'environment':'production-supabase','approval_TTL_minutes':15,'single_use':True}),
      'adopted_increments':[{'commit':x['commit'],'base':x['base'],'tree':x['tree'],'branch':x['branch'],'worktree':x['worktree'],'source':x['increment_registration'],'operations':x['increment_allowed_operations'],
                            **{k:x[k]for k in ('git_parent','existing_pull_number','increment_source_mode')if k in x}}for x in __import__('professional_web_increment').sources(root,ctx)],
      'future_PR_merge_SHA_run_or_version_provided':False,'actual_external_action_performed':False}

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=['describe','request-base','build-preflight','source-backup']);parser.add_argument('--task-id',required=True)
    parser.add_argument('--operation',choices=sorted(OPS));parser.add_argument('--state');parser.add_argument('--base');parser.add_argument('--facts-native');parser.add_argument('--facts-command');parser.add_argument('--self-native');parser.add_argument('--self-command');parser.add_argument('--backup');parser.add_argument('--output')
    args=parser.parse_args();root=Path(__file__).resolve().parents[1]
    try:
        with w.request_validation_context():
            if args.command=='describe':result=describe(root,args.task_id)
            elif args.command=='source-backup':result=source_backup(root,args.task_id,a.document(root,w.file_digest(root,args.state)),args.output)
            elif args.command=='request-base':
                result=request_base(root,args.task_id,args.operation,a.document(root,w.file_digest(root,args.state)));need(args.output,'new project input output path required');out=w.safe_path(root,args.output);need(not out.exists(),'preserve original request');w.atomic_write_json(out,result);result={'state':'request_base_prepared_no_permission','input':w.file_digest(root,args.output),'intent_sha256':w.sha256_value(result)}
            else:result=build_preflight(root,args.base,args.facts_native,args.facts_command,args.self_native,args.self_command,args.backup,args.output)
        print(json.dumps(result,ensure_ascii=False,indent=2))
    except (w.WorkflowError,ValueError,KeyError,OSError)as error:parser.exit(1,str(error)+'\n')
