"""Authenticated external WEB production continuation and guarded material push."""
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
     'merge':'site_ci_prepare','r3_cancel':'site_ci_prepare','r3_retire':'site_ci_prepare','r3_dispatch':'site_ci_prepare','edge_deploy':'site_publish','pages_deploy':'site_publish'}
CHECKS={'furniture-page-pr-checks','interaction-standards','r3-managed-cms-pr-checks'}
def need(ok,message):a.require(ok,'external WEB: '+message)
def _immutable_git_input(args):
    # Cache raw content-addressed inputs only, never HEAD/branch/status/config,
    # remote/native facts, authorization, validator results or execution effects.
    sha = r'[0-9a-f]{40}'
    return bool(
        len(args) == 2 and args[0] in {'show', 'rev-parse'}
        and re.fullmatch(sha + r'(?::[^\x00\n]+|\^\{tree\})', args[1])
        or len(args) == 4 and args[:2] == ('show', '-s')
        and args[2] in {'--format=%H %P %T', '--format=%P'} and re.fullmatch(sha, args[3])
        or len(args) == 4 and args[0] == 'ls-tree' and re.fullmatch(sha, args[1])
        and args[2] == '--' and not args[3].startswith('-'))

def _historical_git_read_only(args):
    """Only immutable-object reads may use the original repository after cleanup."""
    sha=r'[0-9a-f]{40}'
    if _immutable_git_input(args):return True
    if len(args)==3 and args[0]=='merge-base':
        return all(re.fullmatch(sha,x) for x in args[1:]) is True
    if len(args) == 7 and args[:3] == ('diff', '--no-ext-diff', '--unified=0') and args[5] == '--':
        path = Path(args[6])
        return bool(all(re.fullmatch(sha, commit) for commit in args[3:5])
                    and args[6] and not args[6].startswith(':') and not path.is_absolute()
                    and '..' not in path.parts)
    if len(args)>=3 and args[0]=='diff' and all(x in {'--name-only','-z','--no-ext-diff','--binary','--full-index'} for x in args[1:-2]):
        return all(re.fullmatch(sha,x) for x in args[-2:]) is True
    return False


def git(ctx,*args):
    validation=w._VALIDATION_CONTEXT.get()
    from paid_three_page_bounded_cms import historical_material_owner_source_active, _replayable_git, _untracked_historical_input
    historical_material = validation is not None and (
        historical_material_owner_source_active() or ctx.get('historical_material_custody') is True)
    custody_reader = args in {('config','--get','remote.origin.url'), ('rev-parse','--show-toplevel')}
    replay = historical_material and (_historical_git_read_only(args) or custody_reader)

    def run(command, cwd):
        if replay:
            return _replayable_git(command, str(cwd))
        return subprocess.run(command,cwd=cwd,capture_output=True,timeout=20)

    def read_cwd():
        cwd=Path(ctx['worktree'])
        if not cwd.is_dir() and ctx.get('original_source_worktree_missing') is True:
            need(_historical_git_read_only(args), 'missing worktree permits immutable Git reads only')
            original=cwd.resolve(strict=False);allowed=Path(ctx['binding']['cwd']).resolve(strict=True)
            need(original.is_relative_to(allowed) and original.parent.name=='.worktrees' and not original.exists(),
                 'exact absent original project worktree required')
            cwd=original.parent.parent.resolve(strict=True)
            need(cwd.is_relative_to(allowed), 'original repository must remain in WEB project')
            check=run(['git','rev-parse','--show-toplevel'],cwd)
            need(check.returncode==0 and Path(check.stdout.decode().strip()).resolve()==cwd, 'actual original Git repository required')
        return cwd
    def read():
        p=run(['git',*args],read_cwd())
        if replay and p.returncode:
            _untracked_historical_input()
        need(p.returncode==0,'actual local Git source unavailable');return p.stdout
    if validation is None:return read()
    from professional_cms_single_field_admission import base_source_validation_active
    if not (_immutable_git_input(args) or replay):
        return read()
    key=(str(Path(ctx['worktree']).resolve()),args)
    if base_source_validation_active() or historical_material:
        # A request-consistent raw input, never a validator/authority/effect memo.
        # The original policy append and queue-intent locks call recheck(), which
        # actually rereads both repository identity/HEAD and each unique object.
        # Only the exact historical origin binding joins content-addressed reads.
        def source_identity():
            cwd=read_cwd().resolve(strict=True)
            p=run(['git','rev-parse','--show-toplevel','--absolute-git-dir','--git-common-dir',
                   'HEAD','--symbolic-full-name','HEAD'],cwd)
            need(p.returncode==0,'actual immutable Git repository identity required')
            lines=p.stdout.decode().splitlines()
            need(len(lines)==5 and Path(lines[0]).resolve()==cwd,'actual immutable Git repository/HEAD tuple required')
            paths=[cwd,*[(Path(x) if Path(x).is_absolute() else cwd/x).resolve(strict=True) for x in lines[1:3]]]
            identities=[(str(path),path.stat().st_dev,path.stat().st_ino) for path in paths]
            return json.dumps([lines,identities],sort_keys=True,separators=(',',':')).encode()
        identity_key=('professional_base_git_identity',str(Path(ctx['worktree']).resolve()),
                      str(Path(ctx.get('binding',{}).get('cwd',ctx['worktree'])).resolve()))
        if identity_key not in validation.git_object_inputs:
            validation.git_object_inputs[identity_key]={'raw':source_identity(),'reread':source_identity}
        if key in validation.git_object_inputs:return validation.git_object_inputs[key]['raw']
    # Current execution and source consumers still reread on every use.
    actual=read()
    if key not in validation.git_object_inputs:
        evidence = {'raw': actual, 'reread': read}
        if (replay and len(args) == 2 and args[0] == 'show'
                and re.fullmatch(r'[0-9a-f]{40}:[^\x00\r\n]+', args[1])):
            evidence['batch_blob'] = (str(read_cwd().resolve()), args[1])
        validation.git_object_inputs[key] = evidence
    else:
        need(validation.git_object_inputs[key]['raw']==actual,
             'Git object source changed during this request')
    return actual


def recheck_historical_git_blobs(cwd, entries):
    """Replay exact commit:path blob inputs in one Git process."""
    query = b''.join(name.encode('utf-8') + b'\n' for name, _ in entries)
    result = subprocess.run(['git', 'cat-file', '--batch'], cwd=cwd, input=query,
                            capture_output=True, timeout=20)
    need(result.returncode == 0, 'immutable Git batch replay unavailable')
    offset = 0
    for name, expected in entries:
        end = result.stdout.find(b'\n', offset)
        header = result.stdout[offset:end].split() if end >= offset else []
        need(len(header) == 3 and re.fullmatch(rb'[0-9a-f]{40}', header[0])
             and header[1] == b'blob' and header[2] == str(len(expected)).encode(),
             'immutable Git batch blob changed: ' + name)
        start = end + 1
        offset = start + len(expected) + 1
        need(result.stdout[start:offset] == expected + b'\n',
             'immutable Git batch blob changed: ' + name)
    need(offset == len(result.stdout), 'unexpected immutable Git batch bytes')
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
    if item.get('schema') == 'owner-reviewed-brand-WEB-source/v1':
        from owner_reviewed_brand_web_source import validate
        return validate(root,snapshot,item)
    if item.get('schema') in {'original-protected-material-body-WEB-source/v1','original-protected-EN2-fields-WEB-source/v1'}:
        from professional_cms_channel import original_body_context,original_en2_context
        return (original_en2_context if item['schema']=='original-protected-EN2-fields-WEB-source/v1'else original_body_context)(root,snapshot,item)
    if item.get('schema') == 'original-received-CMS-channel-production-source/v1':
        return cms.received_increment_web_context(root,snapshot,item)
    if item.get('schema') == 'builtin-wardrobe-original-WEB-source-registration/v1':
        from builtin_wardrobe_current_binding import web_context
        return web_context(root, snapshot, item)
    if item.get('schema') == 'original-explicit-production-delivery-source/v1':
        from original_production_delivery import contexts
        return contexts(root, snapshot, item)[1]
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
    from direct_owner_frontend_source import EVENT as FRONTEND_EVENT, validate as frontend_validate
    from approved_ads_web_source import records as approved_ads_records
    approved_ads = approved_ads_records(root,task)
    direct=[e for e in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS,where={'task_id':task})
            if e.get('task_id')==task and e.get('details',{}).get(FRONTEND_EVENT)]
    rows=[e for e in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS,where={'task_id':task})if e.get('task_id')==task and EVENT in e.get('details',{})]
    from professional_cms_channel import original_body_records
    body=original_body_records(root,task)
    need(not(rows and body) and not (direct and (rows or body)) and len(direct)<=1
         and not (approved_ads and (direct or rows or body)), 'ambiguous original source catalogs')
    if approved_ads:return approved_ads
    if direct:
        pin=direct[0]['details'][FRONTEND_EVENT]; snapshot=g.restore_goal(root,w.read_json(w.snapshot_path(root,task)))
        return [{**frontend_validate(root,snapshot,a.document(root,pin)),'registration':pin,'event_id':direct[0]['event_id']}]
    if not rows:
        if body:
            from reviewed_web_release import current
            snapshot=g.restore_goal(root,w.read_json(w.snapshot_path(root,task)))
            return [current(root,snapshot,body[0])]
        return body
    need(len(rows)==1,'ambiguous original external execution source')
    pin=rows[0]['details'][EVENT];item=a.document(root,pin);snapshot=g.restore_goal(root,w.read_json(w.snapshot_path(root,task)))
    return [{**validate_source(root,snapshot,item),'registration':pin,'event_id':rows[0]['event_id']}]
def applies(root,task,action_class):
    from professional_cms_channel import ORIGINAL_BODY_EVENT
    from direct_owner_frontend_source import EVENT as FRONTEND_EVENT
    if action_class in {'site_ci_prepare','site_publish','git_push'}:
        from approved_ads_web_source import records as approved_ads_records
        sources=approved_ads_records(root,task)
        if sources:return sources[0]['original_task']==task
    return action_class in {'site_ci_prepare','site_publish','git_push'} and any((e.get('task_id')==task and (EVENT in e.get('details',{}) or FRONTEND_EVENT in e.get('details',{})))or e.get('details',{}).get(ORIGINAL_BODY_EVENT,{}).get('target_task_id')==task for e in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS))
def record_source(root,task,path):
    import goal_delivery_runtime as g
    pin=w.file_digest(root,path);item=a.document(root,pin)
    if item.get('schema')=='approved-ads-WEB-production-source/v1':
        from approved_ads_web_source import record
        return record(root,task,path)
    if item.get('schema')=='approved-ads-WEB-test-ci-successor/v1':
        from approved_ads_web_source import record_test_successor
        return record_test_successor(root,task,path)
    if item.get('schema')=='direct-owner-frontend-WEB-source/v1':
        from direct_owner_frontend_source import record
        return record(root,task,path)
    if item.get('schema')=='current-owner-reviewed-WEB-release-source/v1':
        from reviewed_web_release import record
        return record(root,task,path)
    if item.get('schema')in {'original-protected-material-body-WEB-source/v1','original-protected-EN2-fields-WEB-source/v1'}:
        from professional_cms_channel import record_original_body
        return record_original_body(root,task,path)
    with w.workflow_lock(root):
        snapshot=g.restore_goal(root,w.read_json(w.snapshot_path(root,task)));ctx=validate_source(root,snapshot,item);old=records(root,task)
        if old:need(old[0]['registration']==pin,'immutable source already bound');return {'result':'duplicate_ignored','source':pin,'external_permission_issued':False}
        event=w.append_workflow_event(root,task,snapshot['current_state'],{EVENT:pin})
    return {'result':'recorded','source':pin,'event_id':event['event_id'],'external_permission_issued':False,'business_producers_changed':False}

def action_id(ctx,op,commit,main=None):
    return ctx['prefix']+'-'+commit[:12]+'-'+op.replace('_','-')+('-'+main[:12]if main and op in {'r3_cancel','r3_retire','r3_dispatch','edge_deploy','pages_deploy'}else'')+'-v1'
def scopes(ctx,op):return ctx['edge_scope']if op in {'r3_cancel','r3_retire','edge_deploy','r3_dispatch'}else ctx['pages_scope']if op=='pages_deploy'else ctx['scope']
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
         and rows[0].get('department')==ctx['role']and (rows[0].get('original_professional_source') if ctx.get('owner_received_code_stage') else rows[0].get('delegated_HQ_decision'))==ctx['decision'], 'real original single-use forward policy, not an unrelated grant')
    request=a.document(root,rows[0]['exact_request']);need(request.get('operation')in {'merge','pages_deploy'},'real published/merged own source only')
    output=json.loads(native(root,ctx,proof.get('actual_native'),proof.get('command_id')))
    observed=w._parse_observed_at(output.get('observed_at'));issued=w._parse_observed_at(rows[0].get('checked_at'))
    need(output.get('task_id')==ctx['task']and output.get('repository')==ctx['repository']
         and output.get('policy_decision_id')==rows[0]['decision_id']and output.get('own_candidate_commit')==request['state']['candidate_commit']
         and output.get('current_main_sha')==state['candidate_base']and observed is not None and issued is not None
         and issued<=observed<=dt.datetime.now(dt.timezone.utc),'actual ordered original WEB own-release and current-main readback')
    need(git(ctx,'merge-base',output['own_candidate_commit'],output['current_main_sha']).decode().strip()==output['own_candidate_commit'], 'real own released source ancestry')

def candidate(ctx,state):
    if ctx.get('hq_single_field_code_stage'):
        need(state.get('candidate_commit')==ctx['commit'] and state.get('candidate_base')==ctx['base']
             and state.get('candidate_parent')==ctx['git_parent'] and state.get('candidate_tree')==ctx['tree']
             and state.get('branch')==ctx['branch'] and state.get('worktree')==ctx['worktree']
             and state.get('source_mode','forward')=='forward',
             'actual HQ single-field code stage admits only its exact twelve-file forward commit')
        return ctx['commit'],ctx['base']
    if ctx.get('approved_ads_web_bridge'):
        need(state.get('candidate_commit')==ctx['commit'] and state.get('candidate_base')==ctx['base']
             and state.get('candidate_parent')==ctx.get('git_parent',ctx['base']) and state.get('candidate_tree')==ctx['tree']
             and state.get('branch')==ctx['branch'] and state.get('worktree')==ctx['worktree']
             and state.get('source_mode','forward')=='forward', 'exact approved actual candidate/base/tree and forward only; successor requires separately authenticated source')
        return ctx['commit'],ctx['base']
    if ctx.get('direct_owner_frontend_source') or ctx.get('reviewed_brand_code'):
        need(state.get('candidate_commit')==ctx['commit'] and state.get('candidate_base')==ctx['base']
             and state.get('candidate_parent')==ctx.get('git_parent',ctx['base']) and state.get('candidate_tree')==ctx['tree']
             and state.get('branch')==ctx['branch'] and state.get('worktree')==ctx['worktree']
             and state.get('source_mode','forward')=='forward', 'only the actual registered frontend head and base')
        return ctx['commit'],ctx['base']
    if ctx.get('original_W_channel'):
        need(state.get('source_mode', 'forward') == 'forward', 'original W permits forward source only; no CMS inverse or inferred production rollback')
    if ctx.get('original_production_channel'):
        from original_production_delivery import candidate as original_candidate
        return original_candidate(ctx, state)
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
    if 'hq_singlefield_code_stage_source' in state:
        from hq_bounded_web_admission import code_stage_context
        need('code_only_source_registration' not in state and 'increment_registration' not in state,
             'one explicit original code-stage selector; no mixed source families')
        if 'hq_singlefield_test_successor_source' in state:
            from hq_singlefield_test_successor import execution_context as successor_context
            return successor_context(root,task,state['hq_singlefield_code_stage_source'],state['hq_singlefield_test_successor_source'])
        return code_stage_context(root,task,state['hq_singlefield_code_stage_source'])
    need('hq_singlefield_test_successor_source' not in state, 'reviewed successor requires its exact original base selector')
    from professional_web_increment import select
    if 'code_only_source_registration' in state:
        from original_production_delivery import code_records
        sources=[x for x in code_records(root,task) if x['registration']==state['code_only_source_registration']]
        need(len(sources)==1,'one authenticated explicitly selected code-only source stage')
        return sources[0]
    sources=records(root,task)
    need(len(sources)==1,'one actual registered original WEB production source required; issuer contract/local target alone is not that source')
    if sources[0].get('approved_ads_source_discovery_only'):
        source=sources[0];need(task==source['original_task'],'original business task required; stage is a carrier only')
        from approved_ads_web_source import successor_records
        successors=successor_records(root,source)
        if successors and state.get('candidate_commit')==successors[0]['commit']:
            source=successors[0]
        import ast
        module=ast.parse(w.validation_bytes(Path(root)/'tools/managed_cms_permit_issuer.py'))
        values=[ast.literal_eval(node.value) for node in module.body if isinstance(node,ast.Assign)
                and any(isinstance(target,ast.Name) and target.id=='SUPABASE_HOST' for target in node.targets)]
        need(len(values)==1 and isinstance(values[0],str) and re.fullmatch('[a-z0-9]+\\.supabase\\.co',values[0]),'one literal original platform project source')
        ref=values[0].split('.')[0]
        ctx = {**source,'root':str(Path(root).resolve()),'task':source['original_task'],'execution_stage_id':source['task'],
          'scope':source['business_scope'],'original_production_channel':True,'approved_ads_web_bridge':True,
          'site':source['binding']['cwd'],'prefix':source['original_task']+'-approved-web',
          'edge_scope':'company.example:edge:'+ref+':content-publish','pages_scope':'company.example:pages:production','project_ref':ref}
        from r3_known_zero_recovery import select_cancel,select_replacement
        if state.get('r3_cancel') is not None:return select_cancel(root,ctx,state)
        return select_replacement(root,ctx,state)
    return select(root,sources[0],state)

def static_intent(root,request):
    ctx=execution_context(root,request['task_id'],request.get('state',{}))
    return _static_intent_context(root,request,ctx)

def _static_intent_context(root,request,ctx):
    # A local value from this same builder invocation, never a request field,
    # shared authority memo or permission. All original identity checks follow.
    role=request.get('sender_department',request.get('department'))
    if ctx.get('approved_ads_web_bridge'):
        need(request.get('task_id')==ctx['original_task'] and request.get('execution_stage_id')==ctx['execution_stage_id'],
             'exact original business task and real execution stage required')
    if ctx.get('hq_single_field_code_stage'):
        allowed={'task_id','sender_department','department','action_id','action_class','scope','source_project_id',
                 'execution_project_id','operation','state','observed_at','authorization_changes','desired',
                 'exact_HQ_singlefield_code_stage_source','facts','self_check','backup','rollback'}
        need(set(request)<=allowed and request.get('task_id')==ctx['task']
             and request.get('exact_HQ_singlefield_code_stage_source')==ctx['registration'],
             'exact new single-field source request only; no old production marker or hidden authority')
    need(role==request.get('department',role)==ctx['role']and request.get('source_project_id')==a.PROJECT
      and request.get('execution_project_id')==ctx['binding']['project_id']and request.get('authorization_changes',[])==[]
      and ((request.get('exact_HQ_singlefield_code_stage_source')==ctx['registration'])
           if ctx.get('hq_single_field_code_stage') else (request.get('exact_original_production_source')==ctx['registration'] and not request.get('exact_HQ_production_decision') and not request.get('exact_standing_CMS_channel_source'))
           if ctx.get('original_production_channel') else
           (request.get('exact_standing_CMS_channel_source')==ctx['registration'] and not request.get('exact_HQ_production_decision'))
           if ctx.get('standing_CMS_channel') else request.get('exact_HQ_production_decision')==ctx['decision']),
         'exact actual external WEB/projects/source; no actor substitution, mislabeled HQ decision or expansion')
    need(request.get('exact_original_overlap_source') == (ctx.get('increment_registration') if ctx.get('original_peer_overlap_source') else None),
         'exact registered overlap source must bind this intent; no caller waiver or unrelated source')
    return ctx
def working_source(ctx,head):
    need(git(ctx,'rev-parse','HEAD').decode().strip()==head
         and git(ctx,'branch','--show-current').decode().strip()==ctx['branch']
         and not git(ctx,'status','--porcelain').strip(),
         'fresh real clean worktree/head/branch CAS; preserve parallel WIP and never push another HEAD')

def _approved_ads_gh_response(ctx,state,turn,command,endpoint):
    """Read an exact gh GET's complete HTTP response and server Date, not caller time."""
    import email.utils,shlex
    need(not turn.get('error') and type(turn.get('startedAt')) in (int,float)
         and command.get('type')=='commandExecution' and command.get('status')=='completed' and command.get('exitCode')==0
         and Path(command.get('cwd','')).resolve()==Path(ctx['worktree']).resolve(), 'completed original WEB query required')
    argv=shlex.split(command.get('command',''))
    if len(argv)==3 and argv[0] in ('/bin/zsh','/bin/bash') and argv[1] in ('-lc','-c'):argv=shlex.split(argv[2])
    need(argv==['gh','api','--include','--method','GET',endpoint], 'fixed original read-only GitHub query with response headers required')
    raw=w._completion_execution_output(command).decode('utf-8')
    need('\r' not in raw.replace('\r\n',''), 'valid HTTP response line endings')
    headers,separator,body=raw.replace('\r\n','\n').partition('\n\n')
    lines=headers.split('\n');need(separator and re.fullmatch(r'HTTP/(?:1\.[01]|2(?:\.0)?) 200(?: [^\n]*)?',lines[0]), 'complete successful HTTP 200 response required')
    parsed={}
    for line in lines[1:]:
        match=re.fullmatch(r'([A-Za-z0-9-]+):[ \t]*(.*)',line)
        need(match is not None, 'well-formed HTTP response headers required')
        parsed.setdefault(match.group(1).lower(),[]).append(match.group(2).strip())
    dates=parsed.get('date',[]);types=parsed.get('content-type',[]);ids=parsed.get('x-github-request-id',[])
    need(len(dates)==len(types)==len(ids)==1 and re.fullmatch(r'application/json(?:\s*;[^\n]*)?',types[0],re.I)
         and re.fullmatch(r'[A-Za-z0-9:-]+',ids[0]) is not None, 'one actual GitHub Date, request ID and JSON content type required')
    try:observed=email.utils.parsedate_to_datetime(dates[0])
    except (TypeError,ValueError,OverflowError):raise w.WorkflowError('autonomous delivery: external WEB: valid GitHub HTTP Date required')
    need(observed is not None and observed.tzinfo is not None and observed.utcoffset()==dt.timedelta(0)
         and email.utils.format_datetime(observed,usegmt=True)==dates[0], 'canonical GMT GitHub HTTP Date required')
    now=dt.datetime.now(dt.timezone.utc);facts=w._parse_observed_at(state.get('observed_at'))
    need(facts is not None and turn['startedAt']-1<=observed.timestamp()<=facts.timestamp()
         and 0<=(now-observed).total_seconds()<=300 and facts<=now,
         'actual GitHub response Date must follow original turn, precede facts and remain within 300 seconds')
    return json.loads(body)

def approved_ads_git_facts(root,ctx,state,op=None):
    """Read exact account, repo, main, branch and PR effects from WEB native calls."""
    import goal_delivery_runtime as g, shlex
    keys=('actor','repository','main','branch','pulls')+(('pull_detail',) if state.get('pull_request') else ())
    proof=state.get('git_effect_proof');need(isinstance(proof,dict),'actual native GitHub proof required');commands=proof.get('commands')
    need(set(proof)=={'native','commands'} and isinstance(commands,dict) and set(commands)==set(keys)
         and all(isinstance(v,str) and v for v in commands.values()) and len(set(commands.values()))==len(keys),'five actual native GitHub queries required')
    page=g._native_document(root,proof['native']);binding=ctx['binding']
    need(all(page.get('thread',{}).get(k)==binding[v] for k,v in {'id':'thread_id','title':'title','cwd':'cwd'}.items()),'original WEB GitHub native identity')
    repository=ctx['repository'];branch=ctx['branch'];login=repository.split('/')[0]
    endpoints={'actor':'user','repository':'repos/'+repository,'main':'repos/'+repository+'/git/ref/heads/main',
      'branch':'repos/'+repository+'/git/matching-refs/heads/'+branch,
      'pulls':'repos/'+repository+'/pulls?state=all&head='+login+':'+branch+'&per_page=100'}
    if state.get('pull_request'):
        number=state['pull_request'].get('number');need(type(number) is int and number>0,'actual positive PR number required')
        endpoints['pull_detail']='repos/'+repository+'/pulls/'+str(number)
    values={};turn_id=None
    for key in keys:
        rows=[(t,m) for t in page.get('turns',[]) for m in t.get('items',[]) if m.get('id')==commands[key]]
        need(len(rows)==1,'one actual WEB GitHub query per fact');turn,command=rows[0]
        need(turn_id is None or turn_id==turn.get('id'),'same original WEB turn for GitHub queries')
        turn_id=turn['id'];values[key]=_approved_ads_gh_response(ctx,state,turn,command,endpoints[key])
    need(values['actor'].get('id')==ctx['actor_id'] and values['actor'].get('login')==login
         and values['repository'].get('id')==ctx['repository_id'] and values['repository'].get('full_name')==repository
         and values['main'].get('object',{}).get('sha')==state.get('remote_main_sha'), 'actual original account/repo/main')
    refs=values['branch'];need(isinstance(refs,list) and len(refs)<100 and all(x.get('ref')=='refs/heads/'+branch for x in refs)
         and len(refs)<=1,'complete unambiguous exact branch effect')
    actual_branch=refs[0].get('object',{}).get('sha') if refs else None
    need(actual_branch==state.get('remote_branch_sha'),'actual branch effect, not caller assertion')
    pulls=values['pulls'];need(isinstance(pulls,list) and len(pulls)<100 and all(x.get('head',{}).get('ref')==branch
         and x.get('base',{}).get('ref')=='main' for x in pulls),'complete exact original PR lookup')
    open_pulls=[x for x in pulls if x.get('state')=='open'];need(len(open_pulls)<=1,'ambiguous original PR effect')
    declared=state.get('pull_request')
    need((not open_pulls and not declared) or (len(open_pulls)==1 and isinstance(declared,dict)
         and declared.get('number')==open_pulls[0].get('number') and declared.get('head_sha')==open_pulls[0].get('head',{}).get('sha')),
         'actual original open PR effect, no fabricated or unknown result')
    merged=state.get('merged_pull_request')
    postmerge=((ctx.get('approved_ads_test_successor') or ctx.get('hq_single_field_code_stage'))
               and op in {'r3_cancel','r3_retire','r3_dispatch','edge_deploy','pages_deploy'})
    if postmerge:
        need(not declared and not open_pulls and isinstance(merged,dict), 'post-merge original PR must be closed and uniquely evidenced')
        expected_number=(ctx['existing_pull_number'] if ctx.get('hq_reviewed_test_successor') else merged.get('number') if ctx.get('hq_single_field_code_stage') else ctx['existing_pull_number'])
        need(type(expected_number) is int and expected_number>0,'real original merged PR number required')
        exact=[p for p in pulls if p.get('number')==expected_number]
        need(len(exact)==1, 'one original merged PR in complete native result')
        actual=exact[0]; merge=actual.get('merge_commit_sha'); timestamp=actual.get('merged_at')
        need(actual.get('state')=='closed' and isinstance(timestamp,str) and w._parse_observed_at(timestamp) is not None
             and re.fullmatch('[0-9a-f]{40}',str(merge)) and merged.get('number')==actual.get('number')
             and merged.get('state')=='closed' and merged.get('merged_at')==timestamp
             and merged.get('merge_commit_sha')==merge and merged.get('head_sha')==actual.get('head',{}).get('sha')==ctx['commit']
             and merged.get('head_branch')==actual.get('head',{}).get('ref')==branch
             and merged.get('base_branch')==actual.get('base',{}).get('ref')=='main'
             and actual.get('base',{}).get('repo',{}).get('id')==ctx['repository_id']
             and actual.get('head',{}).get('repo',{}).get('id')==ctx['repository_id'], 'exact original merged PR, source head and repository')
        main=state.get('remote_main_sha')
        need(re.fullmatch('[0-9a-f]{40}',str(main)) and git(ctx,'merge-base',ctx['commit'],merge).decode().strip()==ctx['commit']
             and git(ctx,'merge-base',merge,main).decode().strip()==merge, 'actual merge commit contains candidate and belongs to current main')
    else:
        need(not merged, 'merged PR evidence is restricted to authenticated post-merge operations')
    if declared:
        detail=values['pull_detail'];mergeable={True:'MERGEABLE',False:'CONFLICTING',None:'UNKNOWN'}.get(detail.get('mergeable'))
        need(detail.get('number')==declared['number'] and detail.get('state')=='open'
             and detail.get('head',{}).get('ref')==branch and detail.get('head',{}).get('sha')==declared.get('head_sha')
             and detail.get('base',{}).get('ref')==declared.get('base_branch')=='main'
             and declared.get('head_branch')==branch and declared.get('mergeable')==mergeable
             and declared.get('merge_state')==str(detail.get('mergeable_state','')).upper(),
             'actual current exact PR detail and mergeability, never caller status')
    return True

def approved_ads_ci_facts(root,ctx,state):
    """Bind required check conclusions to one exact same-head GitHub API result."""
    import goal_delivery_runtime as g,shlex
    proof=state.get('ci_effect_proof',{});need(isinstance(proof,dict) and set(proof)=={'native','command_id'},'actual CI query proof required')
    page=g._native_document(root,proof['native']);binding=ctx['binding']
    need(all(page.get('thread',{}).get(k)==binding[v] for k,v in {'id':'thread_id','title':'title','cwd':'cwd'}.items()),'original WEB CI native identity')
    rows=[(t,m) for t in page.get('turns',[]) for m in t.get('items',[]) if m.get('id')==proof['command_id']]
    need(len(rows)==1,'one actual CI query');turn,command=rows[0]
    endpoint='repos/'+ctx['repository']+'/commits/'+state['candidate_commit']+'/check-runs?per_page=100'
    data=_approved_ads_gh_response(ctx,state,turn,command,endpoint);checks=data.get('check_runs')
    need(isinstance(checks,list) and type(data.get('total_count')) is int and data['total_count']==len(checks),'complete CI result, no hidden page')
    selected=[x for x in checks if x.get('name') in CHECKS]
    need(len(selected)==len(CHECKS) and {x.get('name') for x in selected}==CHECKS
         and all(x.get('head_sha')==state['candidate_commit'] and x.get('id') and x.get('status')=='completed'
                 and x.get('conclusion')=='success' for x in selected), 'all actual required same-head CI checks succeeded')
    declared=state.get('checks',[])
    need(all(any(all(x.get(k)==real.get(k) for k in ('name','id','head_sha','status','conclusion')) for x in declared)
             for real in selected),'declared checks exactly match native GitHub result')
    return True

def approved_ads_shared_r3(root,ctx,state,op):
    """Verify complete live R3 status lists from the original WEB native turn."""
    import goal_delivery_runtime as g, shlex
    statuses=('queued','in_progress','waiting','pending','requested')
    proof=state.get('shared_r3_proof');need(isinstance(proof,dict),'actual native shared R3 proof required');commands=proof.get('commands')
    need(set(proof)=={'native','commands'} and isinstance(commands,dict) and set(commands)==set(statuses)
         and all(isinstance(v,str) and v for v in commands.values()) and len(set(commands.values()))==len(statuses),'five original complete shared R3 native observations required')
    page=g._native_document(root,proof.get('native'));binding=ctx['binding']
    need(all(page.get('thread',{}).get(k)==binding[v] for k,v in {'id':'thread_id','title':'title','cwd':'cwd'}.items()),'original WEB shared R3 native identity')
    turn_id=None;allowed=state.get('r3_run',{}).get('id');own_head=state.get('main_sha')
    for status in statuses:
        items=[(t,m) for t in page.get('turns',[]) for m in t.get('items',[]) if m.get('id')==commands[status]]
        need(len(items)==1,'one actual native R3 status query per status');turn,command=items[0]
        need(turn_id is None or turn_id==turn.get('id'), 'same original WEB turn for R3 queries')
        turn_id=turn['id']
        endpoint='repos/'+ctx['repository']+'/actions/workflows/'+R3.split('/')[-1]+'/runs?per_page=100&status='+status
        output=_approved_ads_gh_response(ctx,state,turn,command,endpoint);runs=output.get('workflow_runs')
        need(isinstance(runs,list) and type(output.get('total_count')) is int and output['total_count']==len(runs), 'complete untruncated status page required')
        for run in runs:
            need(run.get('repository',{}).get('id')==ctx['repository_id'] and run.get('path')==R3 and run.get('status')==status,
                 'same original repository/workflow and actual status')
            need(allowed is not None and run.get('id')==allowed and run.get('head_sha')==own_head
                 and run.get('head_branch')=='main' and run.get('event')=='workflow_dispatch'
                 and run.get('run_attempt')==1 and run.get('actor',{}).get('id')==ctx['actor_id'],
                 'another shared R3 run is active or effect is unknown; no cancellation or replay')
            declared=state['r3_run']
            need(declared.get('status')==status and declared.get('path')==R3 and declared.get('head_sha')==own_head
                 and declared.get('run_attempt')==1 and declared.get('actor',{}).get('id')==ctx['actor_id'],
                 'same real active R3 run must be represented exactly; no duplicate dispatch')
    return True

def approved_ads_pages_effect(root,ctx,state):
    """Prove no competing Pages run and read any same-main existing effect."""
    import goal_delivery_runtime as g,shlex
    statuses=('queued','in_progress','waiting','pending','requested','completed')
    proof=state.get('pages_effect_proof');need(isinstance(proof,dict),'actual native Pages proof required');commands=proof.get('commands')
    need(set(proof)=={'native','commands'} and isinstance(commands,dict) and set(commands)==set(statuses)
         and all(isinstance(v,str) and v for v in commands.values()) and len(set(commands.values()))==len(statuses),'six complete native Pages effect observations required')
    page=g._native_document(root,proof['native']);binding=ctx['binding'];turn_id=None;found=[]
    need(all(page.get('thread',{}).get(k)==binding[v] for k,v in {'id':'thread_id','title':'title','cwd':'cwd'}.items()),'original WEB Pages native identity')
    for status in statuses:
        rows=[(t,m) for t in page.get('turns',[]) for m in t.get('items',[]) if m.get('id')==commands[status]]
        need(len(rows)==1,'one actual Pages status query');turn,command=rows[0]
        need(turn_id is None or turn_id==turn.get('id'),'same original WEB turn for Pages queries')
        turn_id=turn['id'];endpoint='repos/'+ctx['repository']+'/actions/workflows/'+PAGES.split('/')[-1]+'/runs?per_page=100&status='+status
        if status=='completed':endpoint+='&head_sha='+state['main_sha']
        output=_approved_ads_gh_response(ctx,state,turn,command,endpoint);runs=output.get('workflow_runs')
        need(isinstance(runs,list) and type(output.get('total_count')) is int and output['total_count']==len(runs),'complete Pages status page')
        for run in runs:
            need(run.get('repository',{}).get('id')==ctx['repository_id'] and run.get('path')==PAGES
                 and run.get('status')==status and run.get('head_sha')==state['main_sha'],
                 'other Pages run or unknown effect blocks manual dispatch')
            found.append(run)
    need(len(found)<=1,'multiple Pages effects require original readback, no replay')
    declared=state.get('pages_run')
    need((not found and not declared) or (len(found)==1 and isinstance(declared,dict)
         and all(declared.get(k)==found[0].get(k) for k in ('id','status','head_sha','path'))),
         'actual Pages effect must match declared state')
    return True
def intent(root,req,check_desired=True):
    if req.get('operation')=='protected_preview':
        from en2_preview_normal import context
        from en2_preview_entry import intent as preview_intent
        return preview_intent(root,req,context(root),check_desired)
    return _intent_context(root,req,static_intent(root,req),check_desired)

def _intent_context(root,req,ctx,check_desired=True):
    op=req.get('operation')
    if op=='protected_preview':
        from en2_preview_entry import intent as en2_preview_intent
        return en2_preview_intent(root,req,ctx,check_desired)
    need(op in OPS,'only registered complete-stage operations')
    if ctx.get('hq_single_field_code_stage'):
        need(op in ctx['allowed_operations'],'exact code stage excludes CMS/Pages/cancel/retire/DB/auth/account operations')
    if ctx.get('code_only_release'):need(op in ctx['allowed_operations'],'code-only source excludes CMS/R3/Edge/DB/account operations')
    if ctx.get('increment_registration'):need(op in ctx['increment_allowed_operations'],'metadata increment needs no CMS/Edge/R3/manual Pages action')
    state=req.get('state',{});head,base=candidate(ctx,state);main=state.get('main_sha')if op in {'r3_cancel','r3_retire','edge_deploy','r3_dispatch','pages_deploy'}else None
    if op=='r3_retire':need(ctx.get('approved_ads_web_bridge') and ctx.get('approved_ads_test_successor') and ctx.get('r3_replacement_source'),'own authenticated replacement terminal binding retirement only')
    working_source(ctx,head)
    if ctx.get('r3_cancel_run_id'):need(op=='r3_cancel','cancellation context cannot authorize another operation')
    if ctx.get('r3_replacement_source'):need(op in {'r3_dispatch','edge_deploy','r3_retire'},'exact replacement dispatch, Edge and own terminal binding retirement only; no Git/PR/Pages/CMS authority')
    if op=='r3_cancel':need(ctx.get('r3_cancel_run_id'),'authenticated cancellation context required')
    if ctx.get('approved_ads_web_bridge') or ctx.get('hq_single_field_code_stage'):approved_ads_git_facts(root,ctx,state,op)
    if op in {'r3_cancel','r3_retire','edge_deploy','r3_dispatch','pages_deploy'}:
        need(re.fullmatch('[0-9a-f]{40}',str(main))is not None,'actual final main is required at this stage, never future or missing SHA')
    need(req.get('action_class')==OPS[op]and req.get('scope')==scopes(ctx,op)
      and req.get('action_id')==action_id(ctx,op,head,main),'exact source-derived operation/action/business or physical scope')
    need(state.get('repository')==ctx['repository'] and state.get('repository_id')==ctx.get('repository_id',1248188229)
      and state.get('branch')==ctx['branch'],'actual original repository/branch')
    if ctx.get('increment_registration'):
        need(state.get('worktree',ctx['worktree'])==ctx['worktree'],'current native/source worktree, never caller old-context fill')
        need(state.get('actor',{}).get('id')==ctx['increment_actor_id'],'exact authenticated original actor')
    if ctx.get('existing_pull_number'):
        need(not (ctx.get('ordinary_increment') or ctx.get('approved_ads_test_successor') or ctx.get('hq_reviewed_test_successor')) or op!='pull_request','existing original PR is reused; never create a duplicate PR')
        postmerge=(ctx.get('approved_ads_test_successor') or ctx.get('hq_reviewed_test_successor')) and op in {'r3_cancel','r3_retire','r3_dispatch','edge_deploy','pages_deploy'}
        pr=state.get('merged_pull_request',{}) if postmerge else state.get('pull_request',{})
        allowed_heads={ctx['git_parent'],head,ctx['commit']}
        if ctx.get('increment_source_mode')=='registered_protected_alias_CI_repair':
            allowed_heads.add(ctx['previous_actual_PR_head'])
        need(pr.get('number')==ctx['existing_pull_number']and pr.get('base_branch')=='main'and pr.get('head_branch')==ctx['branch']
             and pr.get('head_sha')in ({head} if postmerge else allowed_heads)
             and (not postmerge or pr.get('state')=='closed'), 'same actual existing PR only; no creation or replacement')
        if op=='git_push':need(state.get('remote_branch_sha')in allowed_heads,'fresh original branch effect/CAS; unknown head must be read back')
    actor=state.get('actor',{});need(not (ctx.get('code_only_release') or ctx.get('standing_CMS_channel') or ctx.get('original_production_channel')) or actor.get('id')==ctx['actor_id'],'original exact source actor ID')
    need(actor.get('login')==ctx['repository'].split('/')[0]and type(actor.get('id'))is int and actor['id']>0,'original authenticated repository account, no substituted actor')
    desired={'repository':ctx['repository'],'branch':ctx['branch'],'head':head,'force':False,'admin_bypass':False}
    if op=='git_push':need(state.get('remote_main_sha')==base,'fresh main advanced; same-semantic source rebase required before first push')
    if ctx.get('hq_single_field_code_stage') and op=='git_push':
        need(state.get('remote_branch_sha') in ((ctx['git_parent'],head) if ctx.get('hq_reviewed_test_successor') else (None,head)),'different original remote branch effect blocks new code-stage push')
    if ctx.get('approved_ads_web_bridge') and op=='git_push':
        need(state.get('remote_branch_sha') in ((ctx['git_parent'],head) if ctx.get('approved_ads_test_successor') else (None,head)),'different existing branch effect requires explicit recovery/readback')
    if (ctx.get('approved_ads_web_bridge') or ctx.get('hq_single_field_code_stage')) and op=='pull_request':
        need(state.get('remote_branch_sha')==head,'actual same-head pushed branch required before PR')
    if ctx.get('hq_reviewed_test_successor') and op=='official_ci':
        need(state.get('pull_request',{}).get('head_sha')==head, 'actual existing original PR must contain the reviewed successor before CI acceptance')
    if op in {'pull_request','merge'}:desired['base_branch']='main'
    if op in {'official_ci','merge'} or (ctx.get('approved_ads_web_bridge') or ctx.get('hq_single_field_code_stage')) and op in {'r3_cancel','r3_retire','r3_dispatch','edge_deploy','pages_deploy'}:
        checks=state.get('checks',[]);need({x.get('name')for x in checks}>=CHECKS
          and all(x.get('head_sha')==head and x.get('status')=='completed'and x.get('conclusion')=='success'and x.get('id')for x in checks), 'all real required exact-head official checks must succeed')
        if ctx.get('approved_ads_web_bridge') or ctx.get('hq_single_field_code_stage'):approved_ads_ci_facts(root,ctx,state)
    if ((ctx.get('code_only_release')or ctx.get('current_owner_reviewed_release') or ctx.get('hq_single_field_code_stage')) and op in {'official_ci','merge'}
        or ctx.get('approved_ads_web_bridge') and op in {'official_ci','merge','r3_cancel','r3_retire','r3_dispatch','edge_deploy','pages_deploy'}):
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
    if (ctx.get('approved_ads_web_bridge') or ctx.get('hq_single_field_code_stage')) and op in {'r3_dispatch','edge_deploy'}:
        approved_ads_shared_r3(root,ctx,state,op)
    if ctx.get('approved_ads_web_bridge') and op=='pages_deploy':approved_ads_pages_effect(root,ctx,state)
    if op=='r3_cancel':
        from r3_known_zero_recovery import validate_zero
        zero=validate_zero(root,ctx,state)
        desired.update(workflow=R3,run_id=zero['old_run'],run_attempt=1,old_reference=zero['old_reference'],cancel_only=True)
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
    if op=='r3_retire':
        from r3_binding_retirement import validate_observation, retirement_desired
        binding=validate_observation(root,ctx,state)
        desired=retirement_desired(binding)
    if state.get('known_zero_push_recovery'):desired=_recovery_intent(root,ctx,req)
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
    if req.get('operation')=='protected_preview':
        from en2_preview_normal import validate_request as preview_validate
        return preview_validate(root,req)
    ctx=execution_context(root,req['task_id'],req.get('state',{}))
    return _validate_request_context(root,req,ctx)

def _validate_request_context(root,req,ctx):
    ctx,op,state,desired=_intent_context(root,req,_static_intent_context(root,req,ctx));digest=w.sha256_value({k:v for k,v in req.items()if k not in {'facts','self_check','backup','rollback'}})
    for name in ('facts','self_check','backup','rollback'):
        value=a.document(root,req.get(name));need(all(value.get(k)==req.get(k)for k in ('task_id','department','action_id','action_class','scope'))and value.get('intent_sha256')==digest,'exact current request-bound '+name)
        if name=='facts':need(json.loads(native(root,ctx,value.get('actual_native'),value.get('command_id'))).get('state')==state and state.get('observed_at')==req.get('observed_at'),'actual native complete Git/GitHub/runtime facts, no caller observation label')
        if name=='self_check':
            out=native(root,ctx,value.get('actual_native'),value.get('command_id'));need(value.get('status')=='PASS'and digest.encode()in out and ctx['decision']['sha256'].encode()in out,'real professional selfcheck binds intent/source; reuse unaffected tests')
        source_backup_only=(ctx.get('code_only_release') or ctx.get('hq_single_field_code_stage')
                            and op in {'git_push','pull_request','official_ci','merge'})
        if name=='backup'and source_backup_only:
            backup=a.document(root,value.get('source_backup'));need(backup.get('task_id')==ctx['task']and backup.get('source_commit')==head_value(req)and backup.get('source_base')==state.get('candidate_base',ctx['base']), 'actual current code-only source backup/head/base')
            need(_patch_effect(_patch_delta(_backup_bytes(root,backup['forward'],ctx)))==_patch_effect(_delta(ctx,backup['source_base'],backup['source_commit'])),'actual current source forward backup')
            expected=_delta(ctx,backup['source_base'],backup['source_commit']);need(_patch_effect(_patch_delta(_backup_bytes(root,backup['inverse'],ctx)))=={p:(added,removed)for p,(removed,added)in _patch_effect(expected).items()},'actual current source inverse backup')
        if name=='backup'and not source_backup_only:
            pin=value.get('source_backup');need(isinstance(pin,dict),'actual production backup pin');backup=external(root,pin,ctx['binding']) if Path(pin['path']).is_absolute() else a.document(root,pin)
            need(backup.get('task_id')==ctx['task']and backup.get('function')=='content-publish'and backup.get('runtime_files')and backup.get('source_build_archives'),'full actual source/build backup, not local reverse alone')
            for item in backup['runtime_files']+backup['source_build_archives']:_external_bytes(item,ctx['binding'])
            if op in {'r3_cancel','r3_retire','r3_dispatch','edge_deploy','pages_deploy'}:need(backup.get('version')==state.get('runtime_version'),'fresh actual function/version backup CAS')
        if name=='rollback':need(value.get('production_recovery')==ctx['rollback']and value.get('unknown_effect_replay_allowed')is False,'original executable own-delta recovery; unknown effects are not retries')
    if ctx.get('approved_ads_web_bridge') or ctx.get('hq_single_field_code_stage'):
        import goal_delivery_runtime as g
        facts=a.document(root,req['facts']);actual=g._native_document(root,facts['actual_native'])
        fid=facts['command_id'];pairs=[(t,i) for t in actual.get('turns',[]) for i,m in enumerate(t.get('items',[])) if m.get('id')==fid]
        need(len(pairs)==1,'one actual WEB facts call after GitHub readback');turn,index=pairs[0]
        proofs=[state['git_effect_proof']]+([state['shared_r3_proof']] if op in {'r3_dispatch','edge_deploy'} else [])
        for proof in proofs:
            observed=g._native_document(root,proof['native']); observed_turns=[t for t in observed.get('turns',[]) if t.get('id')==turn.get('id')]
            need(len(observed_turns)==1,'same original WEB turn for facts and effect readback')
            ids=set(proof['commands'].values());prior=[i for i,m in enumerate(turn.get('items',[])) if m.get('id') in ids]
            need(len(prior)==len(ids) and len(ids) in (5,6) and all(i<index for i in prior),'all actual effect queries precede exact facts')
            original={m['id']:m for m in observed_turns[0].get('items',[]) if m.get('id') in ids}
            need(len(original)==len(ids) and all(all(turn['items'][i].get(k)==original[turn['items'][i]['id']].get(k)
                 for k in ('id','type','status','exitCode','cwd','command','output')) for i in prior),
                 'identical original completed native query/output in both same-turn snapshots')
        if op=='r3_retire':
            proof=state['r3_retirement']; observed=g._native_document(root,proof['native'])
            matches=[t for t in observed.get('turns',[]) if t.get('id')==turn.get('id')]
            need(len(matches)==1,'same actual WEB turn for terminal retirement facts')
            ids=set(proof['commands'].values()); prior=[i for i,m in enumerate(turn.get('items',[])) if m.get('id') in ids]
            need(len(prior)==len(ids) and all(i<index for i in prior),'all actual retirement reads precede facts')
            from r3_known_zero_recovery import authenticate_actual_facts
            authenticate_actual_facts(root,ctx,turn,fid)
            original={m['id']:m for m in matches[0].get('items',[]) if m.get('id') in ids}
            need(len(original)==len(ids) and all(all(turn['items'][i].get(k)==original[turn['items'][i]['id']].get(k) for k in ('id','type','status','exitCode','cwd','command','output')) for i in prior),'identical actual retirement queries across same-turn snapshots')
        if op=='r3_cancel':
            proof=state['r3_cancel']; observed=g._native_document(root,proof['native'])
            matches=[t for t in observed.get('turns',[]) if t.get('id')==turn.get('id')]
            need(len(matches)==1,'same original WEB turn for cancellation facts')
            ids=set(proof['commands'].values()); prior=[i for i,m in enumerate(turn.get('items',[])) if m.get('id') in ids]
            need(len(prior)==len(ids) and all(i<index for i in prior),'all actual cancellation reads precede facts')
            from r3_known_zero_recovery import authenticate_actual_facts
            authenticate_actual_facts(root,ctx,turn,fid)
            original={m['id']:m for m in matches[0].get('items',[]) if m.get('id') in ids}
            need(len(original)==len(ids) and all(all(turn['items'][i].get(k)==original[turn['items'][i]['id']].get(k)
                 for k in ('id','type','status','exitCode','cwd','command','output')) for i in prior),
                 'identical original cancellation native query/output in both same-turn snapshots')
        if op=='pages_deploy':
            proof=state['pages_effect_proof'];observed=g._native_document(root,proof['native']);ids=set(proof['commands'].values())
            pages_turns=[t for t in observed.get('turns',[]) if t.get('id')==turn.get('id')]
            pages_items=[m for i,m in enumerate(turn.get('items',[])) if i<index and m.get('id') in ids]
            need(len(pages_turns)==1 and len(ids)==6 and len(pages_items)==6,
                 'all six actual Pages queries in same WEB turn precede exact facts')
            original={m['id']:m for m in pages_turns[0].get('items',[]) if m.get('id') in ids}
            need(len(original)==6 and all(all(m.get(k)==original[m['id']].get(k) for k in
                 ('id','type','status','exitCode','cwd','command','output')) for m in pages_items),
                 'identical original Pages query/output across native snapshots')
        if op in {'official_ci','merge','r3_cancel','r3_retire','r3_dispatch','edge_deploy','pages_deploy'}:
            proof=state['ci_effect_proof'];observed=g._native_document(root,proof['native'])
            ci_turns=[t for t in observed.get('turns',[]) if t.get('id')==turn.get('id')]
            actual_ci=[m for i,m in enumerate(turn.get('items',[])) if i<index and m.get('id')==proof['command_id']]
            need(len(ci_turns)==len(actual_ci)==1,
                 'actual CI query in same WEB turn precedes exact facts')
            original=[m for m in ci_turns[0].get('items',[]) if m.get('id')==proof['command_id']]
            need(len(original)==1 and all(actual_ci[0].get(k)==original[0].get(k) for k in
                 ('id','type','status','exitCode','cwd','command','output')),'identical original CI native query/output')
    return ctx,op,state

# Source text inserted into the existing WEB consumer; no platform write operation.
RECOVERY_EVENT='professional_WEB_known_zero_push_recovery'
RECOVERY_SCHEMA='professional-WEB-known-zero-push-recovery/v1'

def _recovery_command(root,ctx,pin,command,failed=False,repository_read=False,*,controller_admission=False):
    import goal_delivery_runtime as g
    page=g._native_document(root,pin);binding=ctx['binding']
    need(all(page.get('thread',{}).get(k)==binding[v]for k,v in {'id':'thread_id','title':'title','cwd':'cwd'}.items()),'original WEB completed recovery native identity')
    matches=[(turn,index,item)for turn in page.get('turns',[])for index,item in enumerate(turn.get('items',[]))if item.get('id')==command]
    need(len(matches)==1,'one actual original recovery command')
    turn,index,item=matches[0];allowed_cwds={Path(root).resolve()} if controller_admission else {Path(ctx['worktree']).resolve()}
    if repository_read:
        common=Path(git(ctx,'rev-parse','--git-common-dir').decode().strip());common=(Path(ctx['worktree'])/common).resolve()if not common.is_absolute()else common.resolve()
        need(common.name=='.git','actual original repository common Git directory');allowed_cwds.add(common.parent)
    need(turn.get('status')=='completed'and not turn.get('error')and type(turn.get('startedAt'))in {int,float}
         and type(turn.get('completedAt'))in {int,float}and turn['startedAt']<=turn['completedAt']<=dt.datetime.now(dt.timezone.utc).timestamp()
         and item.get('type')=='commandExecution'and Path(item.get('cwd','')).resolve()in allowed_cwds, 'real completed WEB turn/original repository cwd and ordered times')
    if not failed:
        need(item.get('status')=='completed'and item.get('exitCode')==0,'successful original recovery readback command')
        raw=w._completion_execution_output(item)
        need(not any(item.get(k)not in (None,raw.decode('utf-8'))for k in ('aggregatedOutput','stdout'))and not item.get('stderr'),'conflicting successful recovery native outputs')
        return turn,index,item,raw
    # A failed command is evidence of failure, never successful execution proof.
    need(item.get('status')=='failed'and type(item.get('exitCode'))is int and item['exitCode']!=0,'explicit nonzero failed transport command required')
    out=item.get('output')
    if isinstance(out,str):raw=out
    else:
        need(isinstance(out,dict)and set(out)=={'text','truncated'}and out.get('truncated')is False and isinstance(out.get('text'),str),'complete untruncated failed native output')
        raw=out['text']
    need(not any(item.get(k)not in (None,raw)for k in ('aggregatedOutput','stdout'))and not item.get('stderr'),'conflicting failed native output representations')
    return turn,index,item,raw.encode('utf-8')

def _output_document(raw,expected):
    text=raw.decode('utf-8');decoder=json.JSONDecoder();found=[];offset=0
    while offset<len(text):
        if text[offset]not in '[{':offset+=1;continue
        try:value,end=decoder.raw_decode(text,offset)
        except ValueError:offset+=1;continue
        if value==expected:found.append(value)
        offset=end
    need(len(found)==1,'one complete exact original evidence JSON in actual native output')

def recovery_source(root,pin):
    import result_coordination as rc
    from material_push_expiry import SCHEMA as MATERIAL_EXPIRY_SCHEMA, source as material_expiry_source
    doc=a.document(root,pin)
    if doc.get('schema')==MATERIAL_EXPIRY_SCHEMA:
        return material_expiry_source(root,pin,doc)
    need(doc.get('schema')==RECOVERY_SCHEMA,'known-zero recovery source schema')
    packet=a.document(root,doc.get('original_input'));task=packet.get('task_id');prior=packet.get('original_policy',{})
    old=a.document(root,prior.get('exact_request'));ctx=static_intent(root,old);head,base=candidate(ctx,old['state'])
    need(task==ctx['task']and packet.get('scope')==ctx['scope']and packet.get('source_owner')==ctx['owner']
         and packet.get('executor')==ctx['role']and old.get('operation')=='git_push'
         and old.get('action_id')==action_id(ctx,'git_push',head)and old.get('action_class')==OPS['git_push']
         and old.get('scope')==scopes(ctx,'git_push')and packet.get('exact_original_execution_action')==old['action_id']
         and packet.get('exact_head')==head and packet.get('exact_branch')==ctx['branch']and packet.get('repository')==ctx['repository']
         and packet.get('original_actor')==old['state'].get('actor'),'same original authorized owner/executor/action/head/branch/account')
    original_desired={'repository':ctx['repository'],'branch':ctx['branch'],'head':head,'force':False,'admin_bypass':False}
    need(old.get('desired')==original_desired,'original exact non-force push intent')
    key=w.sha256_value([task,ctx['role'],old['action_id'],old['action_class'],old['scope']])
    policies=[p for p in w.read_jsonl(Path(root)/w.POLICY_DECISIONS)if p.get('decision_id')==prior.get('decision_id')]
    need(len(policies)==1 and policies[0]==prior and prior.get('status')=='allow'and prior.get('actual_action_allowed')is True
         and prior.get('consume_approval')is True and prior.get('autonomous_action_key')==key==packet.get('original_autonomous_action_key')
         and prior.get('payload_sha256')==prior['exact_request']['sha256']and not prior.get('known_zero_push_recovery'),'real original consumed policy/key, never a reset or recovered permission')
    events=[e for e in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS)if e.get('event_id')==packet.get('previous_preflight_event')]
    need(len(events)==1 and events[0].get('task_id')==task,'actual original preflight event')
    pre=events[0].get('details',{}).get('professional_WEB_preflight',{})
    need(pre.get('input')==prior.get('source_preflight')and pre.get('request')==prior.get('exact_request')and pre.get('action_id')==old['action_id']
         and a.document(root,prior['source_preflight']).get('request')==prior['exact_request']
         and packet.get('previous_intent')==w.sha256_value({k:v for k,v in old.items()if k not in {'facts','self_check','backup','rollback'}}),'original immutable request/intent/preflight relation')
    # The actual committed owner result authenticates the source container. It is not a new production authorization.
    identity=doc.get('owner_result_identity',{});received=rc._received_delivery(root,identity,{'target_department':'operations'})
    need(received and received.get('record_id')==doc.get('actual_owner_intake_record_id')and identity.get('task_id')==task
         and received.get('scope')==ctx['scope']and identity.get('sender_department')==ctx['owner'],'actual same-task owner committed SQL/native source custody')
    box=a.document(root,received['outbox']);need(doc['original_input']in list(_pins(box)),'actual received complete owner result must pin this exact input')
    custody=a.document(root,packet.get('C1_custody'));result=a.document(root,packet.get('producer_result'))
    need(custody.get('task_id')==task and custody.get('scope')==ctx['scope']and custody.get('owner')==ctx['owner']
         and custody.get('producer')==ctx['role']and custody.get('exact_typed_copy')==packet.get('producer_result')
         and result.get('task_id')==task and result.get('scope')==ctx['scope']and result.get('producer')==ctx['role']
         and result.get('producer_thread')==ctx['binding']['thread_id']and result.get('recipient')==ctx['owner'],'real original professional result and owner custody, no actor substitution')
    send_intents=[]
    for evidence in result.get('evidence',[]):
        if isinstance(evidence,dict)and str(evidence.get('path','')).endswith('.json')and type(evidence.get('size'))is int and evidence['size']<=8192 and Path(evidence['path']).is_absolute()and Path(evidence['path']).resolve().is_relative_to(Path(ctx['binding']['cwd']).resolve()):
            value=external(root,evidence,ctx['binding'])
            if isinstance(value,dict)and value.get('effect')=='ABOUT_TO_SEND_ONCE':send_intents.append(value)
    need(len(send_intents)==1,'one frozen actual original send intent, not a caller retry declaration')
    sent=send_intents[0];sent_at=w._parse_observed_at(sent.get('at'))
    need(set(sent)=={'at','head','branch','policy','argv','force','effect'}and sent.get('head')==head and sent.get('branch')==ctx['branch']
         and sent.get('policy')==prior['decision_id']and sent.get('force')is False
         and sent.get('argv')==['git','-c','credential.helper=','-c','credential.helper=!gh auth git-credential','push','https://github.com/'+ctx['repository']+'.git','HEAD:refs/heads/'+ctx['branch']],
         'one exact original non-force ref only; no other remote/head/action')
    failure=external(root,packet.get('actual_failure_evidence'),ctx['binding']);zero=external(root,packet.get('actual_zero_effect_source'),ctx['binding'])
    need(failure==packet.get('actual_push_attempt')and zero==packet.get('actual_two_stage_zero_effect_readback'),'exact unchanged failed effect files')
    need(failure.get('exit_code')==1 and failure.get('stdout')==''and failure.get('head')==head and failure.get('policy')==prior['decision_id']
         and failure.get('push_attempts')==1 and failure.get('force')is False and failure.get('retry_unknown_effect')is False,'single explicit failed original transport only')
    expected_error=("To https://github.com/"+ctx['repository']+".git\n ! [remote rejected]   HEAD -> "+ctx['branch']+
        " (refusing to allow an OAuth App to create or update workflow `.github/workflows/content-publish-approved.yml` without `workflow` scope)\nerror: failed to push some refs to 'https://github.com/"+ctx['repository']+".git'\n")
    need(failure.get('stderr')==expected_error,'explicit remote rejected original ref; unknown/network/partial failure is not zero effect')
    nativepin=doc.get('actual_completed_native');commands=doc.get('commands',{})
    admit=_recovery_command(root,ctx,nativepin,commands.get('admission'));failed=_recovery_command(root,ctx,nativepin,commands.get('failure'),True)
    lookup=_recovery_command(root,ctx,nativepin,commands.get('zero_effect'),repository_read=True);ssh=_recovery_command(root,ctx,nativepin,commands.get('ssh_authentication'))
    need(len({x[0]['id']for x in (admit,failed,lookup,ssh)})==1 and admit[1]<failed[1]<ssh[1]<lookup[1],'actual completed original admission/failure/SSH/readback chronology')
    import goal_delivery_runtime as g
    historical=g._native_document(root,packet.get('actual_WEB_native'))
    originals=[t for t in historical.get('turns',[])if t.get('id')==admit[0]['id']and t.get('startedAt')==admit[0]['startedAt']]
    need(historical.get('thread',{}).get('id')==ctx['binding']['thread_id']and len(originals)==1
         and {commands.get('admission'),commands.get('failure'),commands.get('ssh_authentication')}<={m.get('id')for m in originals[0].get('items',[])},'same frozen original native turn/start/commands; later completed readback cannot substitute a new source round')
    admission=json.loads(admit[3]);need(admission.get('policy')==prior and admission.get('record_preflight',{}).get('event_id')==events[0]['event_id'],'actual successful original policy command output')
    _output_document(failed[3],failure);_output_document(lookup[3],zero)
    query=zero.get('exact_branch_query',{});endpoint='repos/'+ctx['repository']+'/git/ref/heads/'+ctx['branch']
    need(query.get('argv')==['gh','api',endpoint]and query.get('exit_code')==1
         and json.loads(query.get('safe_body','null'))=={'message':'Not Found','documentation_url':'https://docs.github.com/rest/git/refs#get-a-reference','status':'404'}
         and query.get('safe_stderr')=='gh: Not Found (HTTP 404)\n'and endpoint.encode()in failed[3]
         and zero.get('same_branch_PRs')==[]and zero.get('actual_main')==base and zero.get('new_push_or_PR_attempt_performed')is False,'two actual same-key ref404 observations, empty PRs and original main')
    # Do not execute command strings. Check that the authenticated completed readback actually queried this original PR key.
    command=str(lookup[2].get('command',''))
    need('/pulls?state=all&head='+ctx['repository'].split('/')[0]+':'in command and ctx['branch']in command and 'check_output'in command,'original completed authenticated exact branch PR query')
    auth=json.loads(ssh[3]);need(auth==packet.get('existing_original_SSH_identity')and auth.get('exit')==1 and auth.get('stdout')==''
         and auth.get('argv')==['ssh','-T','-o','BatchMode=yes','-o','ConnectTimeout=10','-o','ConnectionAttempts=1','user-3de132cd98be@example.invalid']
         and auth.get('stderr')=="Hi "+old['state']['actor']['login']+"! You've successfully authenticated, but GitHub does not provide shell access.\n",'existing same-user SSH authentication only; no write capability assertion')
    issued=w._parse_observed_at(prior.get('checked_at'));at=w._parse_observed_at(zero.get('observed_at'))
    need(issued and at and sent_at and admit[0]['startedAt']<=issued.timestamp()<=sent_at.timestamp()<=at.timestamp()<=admit[0]['completedAt'],'real original policy/failure/readback times')
    return {'ctx':ctx,'original_request':old,'original_policy':prior,'key':key,'source':pin}

def record_push_recovery(root,task,path):
    import goal_delivery_runtime as g
    pin=w.file_digest(root,path);proof=recovery_source(root,pin);need(proof['ctx']['task']==task,'recovery task')
    with w.workflow_lock(root):
        rows=[e for e in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS,where={'task_id':task})if e.get('task_id')==task and e.get('details',{}).get(RECOVERY_EVENT,{}).get('autonomous_action_key')==proof['key']]
        if rows:
            need(len(rows)==1 and rows[0]['details'][RECOVERY_EVENT]['source']==pin,'one immutable recovery source per original action; no new retry container')
            return {'result':'duplicate_ignored','event_id':rows[0]['event_id'],'source':pin,'permission_issued':False}
        need(len([p for p in w.read_jsonl(Path(root)/w.POLICY_DECISIONS)if p.get('autonomous_action_key')==proof['key']and p.get('status')=='allow'])==1,'only the one original consumed action may acquire a recovery source')
        snapshot=g.restore_goal(root,w.read_json(w.snapshot_path(root,task)));need(snapshot.get('current_state')not in w.TERMINAL_STATES,'closed goal cannot recover an external action')
        e=w.append_workflow_event(root,task,snapshot['current_state'],{RECOVERY_EVENT:{'source':pin,'autonomous_action_key':proof['key'],'original_policy':proof['original_policy']['decision_id']}})
    return {'result':'recorded','event_id':e['event_id'],'source':pin,'permission_issued':False,'SSH_write_capability':'NOT_PROVEN'}

def _registered_push_recovery(root,ctx,state):
    pin=state.get('known_zero_push_recovery');proof=recovery_source(root,pin)
    need(proof['ctx']['registration']==ctx['registration']and proof['ctx']['task']==ctx['task'],'same original registered source')
    rows=[e for e in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS)if e.get('task_id')==ctx['task']and e.get('details',{}).get(RECOVERY_EVENT,{}).get('autonomous_action_key')==proof['key']]
    need(len(rows)==1 and rows[0]['details'][RECOVERY_EVENT]['source']==pin,'normal append-only recovery registration required')
    proof['registered_at']=rows[0]['created_at'];return proof

def _validate_recovery_probe(ctx,state,proof):
    probe=state.get('push_recovery_probe',{});now=dt.datetime.now(dt.timezone.utc)
    at=w._parse_observed_at(probe.get('observed_at'));start=w._parse_observed_at(state.get('observed_at'));registered=w._parse_observed_at(proof['registered_at'])
    need(probe.get('schema')=='professional-WEB-known-zero-push-probe/v1'and probe.get('source')==proof['source']and at and start and registered
         and registered<=start<=at<=now and (now-start).total_seconds()<=300,'fresh actual post-registration execution/probe times')
    old=proof['original_request'];need(state.get('effect_state')=='FAILED_KNOWN_ZERO'and state.get('remote_branch_sha')is None
         and state.get('pull_request')is None and state.get('candidate_commit')==old['state']['candidate_commit']
         and state.get('candidate_base')==old['state']['candidate_base']and state.get('actor')==old['state']['actor'],'same original failed-zero head/base/actor only; unknown or partial effects reject')
    queries=probe.get('queries',{});repo=ctx['repository'];login=state['actor']['login'];ref='repos/'+repo+'/git/ref/heads/'
    expected={'actor':('user',{'login':login,'id':state['actor']['id']}),'repository':('repos/'+repo,{'full_name':repo,'id':ctx.get('repository_id',1248188229)}),
              'main':(ref+'main',{'sha':state['candidate_base']}),'branch':(ref+ctx['branch'],{'message':'Not Found','status':'404'}),
              'pulls':('repos/'+repo+'/pulls?state=all&head='+login+':'+ctx['branch'],[])}
    need(set(queries)==set(expected),'complete authenticated recovery observations only')
    for name,(endpoint,body)in expected.items():
        q=queries[name];need(q=={'argv':['gh','api','--hostname','github.com',endpoint],'exit_code':1 if name=='branch'else 0,'body':body},'exact authenticated recovery query '+name)
    need(state.get('remote_main_sha')==state['candidate_base']and probe.get('ssh')=={'argv':['ssh','-T','-o','BatchMode=yes','-o','ConnectTimeout=10','-o','ConnectionAttempts=1','user-3de132cd98be@example.invalid'],'exit_code':1,
         'authenticated_login':login,'write_capability':'NOT_PROVEN'},'same original main and existing SSH identity; no new key/account permission')
    return proof

def push_recovery_probe(root,task,state):
    """Original WEB runs fixed read-only identity/ref queries. No Git push or credential output."""
    ctx=execution_context(root,task,state);need(Path.cwd().resolve()==Path(ctx['worktree']).resolve(),'probe must run in original WEB worktree, not SYS')
    proof=_registered_push_recovery(root,ctx,state);candidate(ctx,state);working_source(ctx,state.get('candidate_commit'))
    from material_push_expiry import TASK, ACTION
    if task==TASK and proof['original_request']['action_id']==ACTION:
        # The timestamp starts with the actual new observations, after the
        # immutable source audit and immediately before the GitHub queries.
        state={**state,'observed_at':dt.datetime.now(dt.timezone.utc).isoformat()}
    repo=ctx['repository'];login=proof['original_request']['state']['actor']['login'];queries={}
    def query(name,endpoint):
        argv=['gh','api','--hostname','github.com',endpoint];p=subprocess.run(argv,cwd=ctx['worktree'],capture_output=True,text=True,timeout=30)
        try:body=json.loads(p.stdout)
        except ValueError:raise w.WorkflowError('external WEB: unreadable authenticated '+name+' response; effect remains unknown')
        if name=='actor':body={k:body.get(k)for k in ('login','id')}
        elif name=='repository':body={k:body.get(k)for k in ('full_name','id')}
        elif name=='main':body={'sha':body.get('object',{}).get('sha')}
        elif name=='branch':body={k:body.get(k)for k in ('message','status')}
        queries[name]={'argv':argv,'exit_code':p.returncode,'body':body}
    for name,endpoint in [('actor','user'),('repository','repos/'+repo),('main','repos/'+repo+'/git/ref/heads/main'),('branch','repos/'+repo+'/git/ref/heads/'+ctx['branch']),('pulls','repos/'+repo+'/pulls?state=all&head='+login+':'+ctx['branch'])]:query(name,endpoint)
    argv=['ssh','-T','-o','BatchMode=yes','-o','ConnectTimeout=10','-o','ConnectionAttempts=1','user-3de132cd98be@example.invalid'];p=subprocess.run(argv,cwd=ctx['worktree'],capture_output=True,text=True,timeout=20)
    need(p.returncode==1 and p.stdout==''and p.stderr=="Hi "+login+"! You've successfully authenticated, but GitHub does not provide shell access.\n",'same existing SSH identity authentication not proven')
    value={**state,'effect_state':'FAILED_KNOWN_ZERO','remote_branch_sha':None,'pull_request':None,
           'push_recovery_probe':{'schema':'professional-WEB-known-zero-push-probe/v1','source':proof['source'],'observed_at':w.utc_timestamp(),'queries':queries,
           'ssh':{'argv':argv,'exit_code':p.returncode,'authenticated_login':login,'write_capability':'NOT_PROVEN'}}}
    _validate_recovery_probe(ctx,value,proof);return {'state':value}

def _recovery_intent(root,ctx,req):
    state=req.get('state',{});proof=_validate_recovery_probe(ctx,state,_registered_push_recovery(root,ctx,state));old=proof['original_request']
    need(req.get('operation')=='git_push'and all(req.get(k)==old.get(k)for k in ('task_id','department','action_id','action_class','scope')),'same original push action only')
    return {**old['desired'],'transport':'existing_ssh','remote_url':'user-3de132cd98be@example.invalid:'+ctx['repository']+'.git'}

def _recovery_policy_history(root,ctx,req,key):
    proof=_registered_push_recovery(root,ctx,req['state']);rows=[p for p in w.read_jsonl(Path(root)/w.POLICY_DECISIONS)if p.get('status')=='allow'and (p.get('autonomous_action_key')==key or p.get('task_id')==ctx['task']and p.get('action_id')==req['action_id'])]
    from material_push_expiry import TASK, ACTION, OWNER_DISPOSITION, additional_policy
    if proof['key']==key and ctx['task']==TASK and req['action_id']==ACTION and len(rows)==2 and (Path(root)/OWNER_DISPOSITION).is_file():
        return additional_policy(root,proof,rows)
    need(proof['key']==key and rows==[proof['original_policy']],'one recovery maximum; consumed or unknown recovery cannot be replayed')
    return {'known_zero_push_recovery':proof['source'],'recovery_of_policy':proof['original_policy']['decision_id'],'recovery_attempt':1}


def material_push_transport(ctx, request):
    """Derive the exact command for an already validated material push request."""
    state=request['state']; desired=request['desired']
    expected={'repository':ctx['repository'],'branch':ctx['branch'],'head':ctx['commit'],
              'force':False,'admin_bypass':False}
    remote='origin'
    if state.get('known_zero_push_recovery'):
        remote='user-3de132cd98be@example.invalid:'+ctx['repository']+'.git'
        expected.update(transport='existing_ssh',remote_url=remote)
    need(request['operation']=='git_push' and desired==expected
         and state['candidate_commit']==ctx['commit'] and state['branch']==ctx['branch'],
         'original material push request and exact admitted transport required')
    return ['git','push','--porcelain',remote,ctx['commit']+':refs/heads/'+ctx['branch']]


def _material_github_read(ctx, endpoint):
    raw=subprocess.check_output(
        ['gh','api','--hostname','github.com','--method','GET',endpoint],
        cwd=ctx['worktree'],timeout=10,stderr=subprocess.DEVNULL)
    return json.loads(raw)


def _material_launch_checks(ctx, request, argv):
    import shutil
    from urllib.parse import quote, urlencode

    state=request['state'];repo='repos/'+ctx['repository']
    ref=repo+'/git/matching-refs/heads/'+quote(ctx['branch'],safe='/')
    pulls=repo+'/pulls?'+urlencode({'state':'all','head':state['actor']['login']+':'+ctx['branch']})
    need(Path.cwd().resolve()==Path(ctx['worktree']).resolve(),
         'material push must run from its exact original WEB worktree')
    executable=shutil.which(argv[0])
    need(executable is not None,'local Git executable required before policy consumption')
    actor=_material_github_read(ctx,'user')
    repository=_material_github_read(ctx,repo)
    main=_material_github_read(ctx,repo+'/git/ref/heads/main')
    branches = _material_github_read(ctx, ref)
    pull_requests = _material_github_read(ctx, pulls)
    if ctx.get('material_registry_test_successor'):
        expected_branch = 'refs/heads/' + ctx['branch']
        need(len(branches) == len(pull_requests) == 1
             and branches[0].get('ref') == expected_branch
             and branches[0].get('object', {}).get('sha') == state.get('remote_branch_sha') == ctx['git_parent'],
             'existing material branch must still equal the original pushed predecessor')
        pull = pull_requests[0]
        need(pull.get('number') == ctx['existing_pull_number'] and pull.get('state') == 'open'
             and pull.get('base', {}).get('ref') == 'main' and pull.get('base', {}).get('sha') == ctx['base']
             and pull.get('head', {}).get('ref') == ctx['branch'] and pull.get('head', {}).get('sha') == ctx['git_parent']
             and pull.get('head', {}).get('repo', {}).get('id') == ctx['repository_id'],
             'only the actual existing open material PR at the predecessor may be updated')
    else:
        need(branches == [] and pull_requests == [], 'empty original branch and PR required for initial material push')
    need(all(actor.get(key)==state['actor'][key] for key in ('id','login'))
         and repository.get('id')==ctx['repository_id'] and repository.get('full_name')==ctx['repository']
         and main.get('object',{}).get('sha')==state['candidate_base'],
         'actual original GitHub identity and main required before policy consumption')
    working_source(ctx,ctx['commit'])
    expected_remote='user-3de132cd98be@example.invalid:'+ctx['repository']+'.git'
    remotes=git(ctx,'remote','get-url','--push','--all','origin').decode().splitlines()
    need(remotes==[expected_remote] or argv[3]=='origin' and remotes==['https://github.com/'+ctx['repository']+'.git'],
         'only the original GitHub push remote is allowed')
    return executable,ref


def run_material_push(root, task, path):
    """Use the existing one-use gate and immediately launch its checked command."""
    from paid_three_page_bounded_cms import MATERIAL_PUBLICATION_TASK

    envelope=a.document(root,w.file_digest(root,path))
    request=a.document(root,envelope['request'])
    need(task==request['task_id']==MATERIAL_PUBLICATION_TASK and request['operation']=='git_push'
         and request['state'].get('material_reviewed_rebase_source'),
         'only the original reviewed material Git push can use this entry')
    launch={}

    def check(ctx, req, preflight_pin, argv):
        need(req==request and preflight_pin==w.file_digest(root,path),
             'the exact requested preflight must still be current')
        executable,ref=_material_launch_checks(ctx,req,argv)
        launch.update(ctx=ctx,argv=[executable,*argv[1:]],ref=ref)

    from department_rotation import prohibit_validation_write
    prohibit_validation_write()
    fields={name:request[name] for name in ('task_id','department','action_id','action_class','scope','source_project_id')}
    decision,_=policy(root,{**fields,'consume_approval':True,
                            'payload_sha256':envelope['request']['sha256']},_material_launch_check=check)
    if decision['status']!='allow':
        return decision
    outcome={'decision_id':decision['decision_id'],'action_id':request['action_id'],
             'result':'transport_effect_unknown'}
    try:
        pushed=subprocess.run(launch['argv'],cwd=launch['ctx']['worktree'],timeout=90,
                              stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        outcome['exit_code']=pushed.returncode
        rows=_material_github_read(launch['ctx'],launch['ref'])
        head=request['state']['candidate_commit'];ref='refs/heads/'+request['state']['branch']
        if (pushed.returncode==0 and isinstance(rows,list) and len(rows)==1
                and rows[0].get('ref')==ref and rows[0].get('object',{}).get('sha')==head):
            outcome.update(result='pushed_and_read_back',remote_head=head)
    except (OSError,ValueError,AttributeError,subprocess.SubprocessError) as error:
        outcome['transport_or_readback_error']=type(error).__name__
    result_path=Path(root)/'logs'/'material-push-execution'/(decision['decision_id']+'.json')
    w.atomic_write_json(result_path,outcome)
    return outcome


def record_preflight(root,task,path):
    item=w.read_json(w.safe_path(root,path))
    if item.get('schema')=='en2-original-WEB-protected-preview-preflight/v1':
        from en2_preview_normal import record_preflight as preview_record
        return preview_record(root,task,path)
    import goal_delivery_runtime as g
    pin=w.file_digest(root,path);item=a.document(root,pin);req=a.document(root,item.get('request'));ctx,_,_=validate_request(root,req)
    need(item.get('schema')=='professional-external-WEB-fresh-preflight/v1'and req.get('task_id')==task,'normal external WEB preflight envelope')
    from material_r3_dispatch import ACTION as material_r3_action, recovery_policy as material_r3_recovery
    material_r3 = req.get('operation') == 'r3_dispatch' and req['action_id'] == material_r3_action and ctx.get('material_registry_test_successor')
    with w.workflow_lock(root):
        if req['state'].get('known_zero_push_recovery'):
            observed=w._parse_observed_at(req.get('observed_at'));need(observed and 0<=(dt.datetime.now(dt.timezone.utc)-observed).total_seconds()<=300,'recovery observations expired during validation; no stale preflight commit')
        holder=ctx.get('execution_stage_id',task)
        rows=[e['details']['professional_WEB_preflight']for e in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS,where={'task_id':holder})if e.get('task_id')==holder and e.get('details',{}).get('professional_WEB_preflight',{}).get('action_id')==req['action_id']]
        if rows and rows[-1]['request']==item['request']:return {'result':'duplicate_ignored','permission_issued':False}
        issued=[p for p in w.read_jsonl(Path(root)/w.POLICY_DECISIONS)if p.get('task_id')==task and p.get('action_id')==req['action_id']and p.get('status')=='allow']
        if req['state'].get('known_zero_push_recovery'):
            ctx=static_intent(root,req);_recovery_policy_history(root,ctx,req,w.sha256_value([task,ctx['role'],req['action_id'],req['action_class'],req['scope']]))
        elif material_r3:
            key = w.sha256_value([task,ctx['role'],req['action_id'],req['action_class'],req['scope']])
            material_r3_recovery(root,ctx,req,key,issued)
        else:need(not issued,'actual/unknown action already issued; read effect without replay')
        if rows:
            old=a.document(root,rows[-1]['request']);fields=('task_id','department','action_id','action_class','scope','operation')
            need(all(old.get(k)==req.get(k)for k in fields)and (old.get('desired')==req.get('desired')or bool(req['state'].get('known_zero_push_recovery'))),'refresh exact same action observations only')
        s=g.restore_goal(root,w.read_json(w.snapshot_path(root,holder)))
        if ctx.get('approved_ads_web_bridge'):need(s['current_state']not in w.TERMINAL_STATES,'active original execution stage required')
        detail={'action_id':req['action_id'],'request':item['request'],'input':pin}
        if ctx.get('approved_ads_web_bridge'):detail['original_business_task_id']=task
        e=w.append_workflow_event(root,holder,s['current_state'],{'professional_WEB_preflight':detail})
    return {'result':'recorded','event_id':e['event_id'],'input':pin,'permission_issued':False}
def preflight(root,task,action,action_class,scope,department):
    if task=='fc-20261011-english-kitchen-actual-publication-goal-v1' and action=='fc-20261011-english-kitchen-actual-publication-goal-v1-original-protected-preview-dry-run-v1':
        from en2_preview_normal import preflight as preview_preflight
        return preview_preflight(root,task,action,action_class,scope,department)
    from approved_ads_web_source import records as approved_ads_records
    ads=approved_ads_records(root,task);holder=ads[0]['task'] if len(ads)==1 else task
    rows=[e['details']['professional_WEB_preflight']for e in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS,where={'task_id':holder})if e.get('task_id')==holder and e.get('details',{}).get('professional_WEB_preflight',{}).get('action_id')==action]
    need(rows,'current actual original WEB preflight required');item=a.document(root,rows[-1]['input']);req=a.document(root,rows[-1]['request']);ctx,op,state=validate_request(root,req)
    need(req.get('department')==ctx['role']==department and req.get('scope')==scope and req.get('action_class')==action_class,'exact preflight executor/action/scope')
    return {**item,'risk_level':'R3'if op=='edge_deploy'else'R2',**{k:req[k]for k in ('task_id','department','action_id','action_class','scope','facts','self_check','backup','rollback')}},req,rows[-1]['input'],ctx

def authorization_precheck(root,request):
    if 'hq_singlefield_code_stage_source' in request.get('state',{}):
        ctx0=execution_context(root,request['task_id'],request['state'])
    else:
        sources=records(root,request['task_id'])
        need(len(sources)==1,'one actual registered original WEB production source required; issuer contract/local target alone is not that source')
        ctx0=sources[0]
    if ctx0.get('protected_body_source_custody'):
        return {'schema':'goal-authorization-precheck/v1','task_id':ctx0['task'],'status':'authorization_change_required','reasons':['exact_original_WEB_per_stage_authority_source_required'],'source_registration':ctx0['registration'],'original_authorization':ctx0['authorization'],'needs_human_confirmation':False,'actual_action_allowed':False,'external_permission_issued':False,'next_owner':ctx0['role'],'next_action':ctx0['production_authority_dependency']}
    if ctx0.get('code_only_release') and ctx0.get('initial_request') and request==a.document(root,ctx0['initial_request']):
        return {'schema':'goal-authorization-precheck/v1','task_id':ctx0['task'],'status':'within_original_authorization','reasons':['real_owner_HQ_code_only_followon_source'],'source_registration':ctx0['registration'],'original_authorization':ctx0['authorization'],'needs_human_confirmation':False,'actual_action_allowed':False,'external_permission_issued':False,'next_owner':ctx0['role'],'next_action':'use normal request-base with original-executor fresh facts and single-use policy'}
    ctx=static_intent(root,request);op=request.get('operation');need(op in OPS,'known original production operation')
    if request.get('state'):intent(root,request)
    else:
        need(not ctx.get('code_only_release') and not ctx.get('standing_CMS_channel') and not ctx.get('original_production_channel'),'exact source request, or use normal current-state request-base')
        repair=a.document(root,ctx['repair']);original=a.document(root,repair['actual_failing_request'])
        need(all(request.get(k)==original.get(k)for k in ('action_id','action_class','scope','operation','desired','committed_source')),'exact initial source intent, or use normal current-state request for later stages')
    return {'schema':'goal-authorization-precheck/v1','task_id':ctx['task'],'status':'within_original_authorization',
      'reasons':['verified_original_external_WEB_full_production_source'],'original_authorization':ctx['authorization'],
      **({'original_production_authority':ctx['contract'],'original_professional_source':ctx['decision']} if ctx.get('original_production_channel') else
         {'standing_CMS_authority':ctx['decision'],'authority_department':ctx['authority_department']} if ctx.get('standing_CMS_channel')
         else {'HQ_delegated_decision':ctx['decision']}),'source_registration':ctx['registration'],'needs_human_confirmation':False,
      'actual_action_allowed':False,'external_permission_issued':False,'next_owner':ctx['role'],
      'next_action':'fresh normal original-executor preflight/policy and exact actual platform stage; no general approval repeat'}

def reference_fresh_preflight(root, row, fresh_pin, fresh_req, ctx, phase):
    """Bind a fresh same-action preflight to an unchanged, still-live issuer row.

    Called only after normal preflight validated original WEB native, CI, shared
    R3 and request bytes; no approval or mutation is created by this check.
    """
    need(ctx.get('approved_ads_web_bridge') and ctx.get('approved_ads_test_successor')
         or ctx.get('hq_single_field_code_stage'), 'same authorized successor or exact registered HQ code stage only')
    need(isinstance(row,dict) and row.get('status')=='active', 'original issuer active and unconsumed')
    import r3_platform_binding_transport as carrier
    binding=carrier.validate_binding(row.get('platform_binding'),current=True,own=True)
    prior=a.document(root,row.get('source_preflight')); old=a.document(root,prior.get('request'))
    need(prior.get('task_id')==old.get('task_id')==fresh_req.get('task_id')==ctx['task']
         and fresh_pin!=row['source_preflight'] and fresh_req.get('operation')==old.get('operation')=='edge_deploy',
         'one newer exact original edge preflight and immutable original issuer source')
    fields=('task_id','sender_department','department','action_id','action_class','scope','source_project_id',
            'execution_project_id','operation','authorization_changes','execution_stage_id','exact_original_production_source','exact_HQ_singlefield_code_stage_source','desired')
    need(all(old.get(k)==fresh_req.get(k) for k in fields) and fresh_req.get('department')==ctx['role']
         and fresh_req.get('action_id')==binding['actionId'] and fresh_req.get('scope')==binding['scope']==ctx['edge_scope']
         and row.get('task_id')==ctx['task']==binding['taskId'] and row.get('action_id')==binding['actionId']
         and row.get('scope')==binding['scope']
         and row.get('original_human_authorization_pin')==ctx['authorization']
         and ((row.get('approval_basis')=='verified_original_goal_external_WEB_source_v1'
               and row.get('granted_by')=='operations' and row.get('delegated_HQ_decision')==ctx['decision']
               and not row.get('original_professional_source') and not row.get('original_production_authority'))
              if ctx.get('hq_single_field_code_stage') else
              (row.get('approval_basis')=='verified_frozen_original_production_delivery_v1'
               and row.get('granted_by')==ctx['owner'] and row.get('original_production_authority')==ctx['contract']
               and row.get('original_professional_source')==ctx['decision']))
         and row.get('execution_department')==ctx['role'] and row.get('approval_id')==binding['approvalId'],
         'same original source, authority, role and exact desired action')
    before=old.get('state',{});after=fresh_req.get('state',{})
    fixed=('candidate_commit','candidate_parent','candidate_base','candidate_tree','branch','worktree','repository',
           'repository_id','actor','main_sha','main_local_sha','remote_main_sha','project_ref','function','merged_pull_request')
    need(all(before.get(k)==after.get(k) for k in fixed)
         and after.get('candidate_commit')==ctx['commit'] and after.get('main_sha')==binding['expectedSha']
         and after.get('effect_state')=='NOT_STARTED', 'same exact candidate/main/actor/target and known unexecuted action')
    br=before.get('r3_run',{});ar=after.get('r3_run',{})
    runkeys=('id','run_attempt','event','path','head_sha','head_branch','repository','actor')
    need(all(br.get(k)==ar.get(k) for k in runkeys) and str(ar.get('id'))==str(binding['runId'])
         and ar.get('run_attempt')==binding['runAttempt']==1 and ar.get('status') in {'queued','in_progress','waiting','pending'}
         and ar.get('conclusion') is None, 'same real pending run/attempt and original repository actor')
    need(reference(ctx,after['candidate_commit'],after['main_sha'])==binding['approvalId'], 'unchanged issuer reference')
    # A WEB-owned same-turn normal status read checks the exact original key.
    # The channel's own durable attempt is written before any provider mutation;
    # a missing attempt plus absent remote binding is required at revalidation.
    proof=after.get('r3_reference_readback');need(isinstance(proof,dict) and set(proof)=={'native','command_id'}, 'actual original reference status proof')
    import goal_delivery_runtime as g, shlex
    page=g._native_document(root,proof['native']);pairs=[(t,m) for t in page.get('turns',[]) for m in t.get('items',[]) if m.get('id')==proof['command_id']]
    need(len(pairs)==1,'one actual reference status command');turn,cmd=pairs[0]
    argv=shlex.split(cmd.get('command',''))
    if len(argv)==3 and argv[0] in ('/bin/zsh','/bin/bash') and argv[1] in ('-lc','-c'):argv=shlex.split(argv[2])
    need(len(argv)==7 and Path(argv[0]).name.startswith('python') and Path(argv[1]).resolve()==(Path(root)/'tools/r3_platform_binding_transport.py').resolve()
         and argv[2:]==['status','--task-id',ctx['task'],'--approval-id',binding['approvalId']], 'only original normal reference status command')
    actual=json.loads(native(root,ctx,proof['native'],proof['command_id']))
    facts=actual.get('facts',{})
    need(actual.get('state')=='NO_EXACT_BINDING_OBSERVED_NOT_A_WRITE_PROOF' and actual.get('read_only') is True
         and actual.get('binding_currently_unexpired') is True and actual.get('local_approval_status')=='active'
         and str(facts.get('run_id'))==str(binding['runId']) and facts.get('run_attempt')==1
         and facts.get('head')==binding['expectedSha'] and facts.get('repository')==ctx['repository']
         and facts.get('actor',{}).get('id')==after['actor']['id'] and facts.get('run_status') in {'queued','in_progress','waiting','pending'}
         and facts.get('run_conclusion') is None and facts.get('environment')=='production-supabase', 'actual original key/run remote readback')
    factsdoc=a.document(root,fresh_req.get('facts'));factpage=g._native_document(root,factsdoc['actual_native'])
    factturns=[t for t in factpage.get('turns',[]) if any(m.get('id')==factsdoc['command_id'] for m in t.get('items',[]))]
    need(len(factturns)==1 and factturns[0].get('id')==turn.get('id') and turn.get('startedAt')==factturns[0].get('startedAt'), 'status and fresh facts from same actual WEB turn')
    items=factturns[0].get('items',[]);status_items=[(i,m) for i,m in enumerate(items) if m.get('id')==proof['command_id']]; fact_items=[i for i,m in enumerate(items) if m.get('id')==factsdoc['command_id']]
    need(len(status_items)==len(fact_items)==1 and status_items[0][0]<fact_items[0]
         and all(status_items[0][1].get(k)==cmd.get(k) for k in ('id','type','status','exitCode','cwd','command','output')),
         'original complete status precedes same-turn facts without source substitution')
    directory=Path(root)/'backups'/ctx['task']/'R3-platform-binding-transport'/binding['approvalId']
    attempt=directory/'attempt.json';readback=directory/'readback.jsonl'
    import r3_platform_binding_transport as carrier
    if phase=='transport':
        need((not attempt.exists() and not readback.exists()) or carrier.authenticated_pre_api_failure(root,ctx,after,directory,binding),
             'no prior attempt or one durably proven pre-provider failure required')
    else:
        need(phase=='policy' and attempt.is_file() and readback.is_file(), 'real original transport required before consuming policy')
        intent=w.read_json(directory/'intent.json');rows=w.read_jsonl(readback)
        normal=(intent and intent.get('binding')==binding and len(rows)==1
             and rows[0].get('state')=='TRANSPORTED_AND_READ_BACK' and rows[0].get('approval_id')==binding['approvalId']
             and rows[0].get('new_write') is True)
        need(normal or carrier.authenticated_pre_api_failure(root,ctx,after,directory,binding,after_success=True),
             'one exact known transported original binding; unknown effects reject')
    observed=w._parse_observed_at(fresh_req.get('observed_at'));now=dt.datetime.now(dt.timezone.utc)
    need(observed and turn['startedAt']<=observed.timestamp() and 0<=(now-observed).total_seconds()<=300,
         'real same-turn current observation within original 300 seconds')
    return True

def policy(root,requested,*,_material_launch_check=None):
    if requested.get('task_id')=='fc-20261011-english-kitchen-actual-publication-goal-v1' and requested.get('action_id')=='fc-20261011-english-kitchen-actual-publication-goal-v1-original-protected-preview-dry-run-v1':
        from en2_preview_normal import policy as preview_policy
        return preview_policy(root,requested)
    item,req,pin,ctx=preflight(root,requested['task_id'],requested['action_id'],requested['action_class'],requested['scope'],requested['department'])
    need(requested.get('source_project_id')==a.PROJECT and requested.get('payload_sha256')==item['request']['sha256']and not requested.get('target_department')and not requested.get('approval_id'),'exact request hash and original action, no borrowed approval/role')
    state=req['state'];op=req['operation'];observed=w._parse_observed_at(req.get('observed_at'))
    from material_r3_dispatch import ACTION as material_r3_action, recovery_policy as material_r3_recovery
    material_r3 = op == 'r3_dispatch' and ctx.get('material_registry_test_successor')
    material_edge_facts = None
    if op == 'edge_deploy' and ctx.get('material_registry_test_successor'):
        from material_edge_live import pending as current_material_pending
        material_edge_facts = current_material_pending(root, ctx, req)
        observed = w._parse_observed_at(material_edge_facts['observed_at'])
    if ctx.get('approved_ads_web_bridge'):
        stage=w.read_json(w.snapshot_path(root,ctx['execution_stage_id']))
        stale_only=(stage and stage.get('current_state')=='blocked' and stage.get('plan_status')=='blocked_health_stale'
                    and stage.get('blockers')==['dispatch_plan:blocked_health_stale']
                    and stage.get('missing_receipts')==[]
                    and {x.get('department') for x in stage.get('departments',[])} == {ctx['owner'],'publishing'})
        need(stage and stage.get('current_state') not in w.TERMINAL_STATES
             and (stage.get('current_state')!='blocked' or stale_only),
             'original execution stage active; only unrelated stale owner/PUB routing may remain blocked')
    if ctx.get('approved_ads_web_bridge') and ctx.get('order')=='ChatGPT':
        need(False,'Google must first actually merge and load; original WEB must return an authenticated same-scope successor against actual resulting main')
    if not (material_r3 and _material_launch_check is not None and requested.get('consume_approval')):
        need(observed and 0<=(dt.datetime.now(dt.timezone.utc)-observed).total_seconds()<=300,'fresh real execution facts; stored authority does not expire')
    if op=='r3_retire':
        from r3_binding_retirement import absence_result
        proof=state['r3_retirement']; status=json.loads(native(root,ctx,proof['native'],proof['commands']['status']))
        no_op=absence_result(status)
        if no_op is not None:return {**no_op,'source_request':item['request']},[]
    if op=='pull_request'and ctx.get('existing_pull_number'):
        return {'status':'existing_original_PR_readback_no_new_create','pull_number':ctx['existing_pull_number'],'actual_action_allowed':False,'source_request':item['request']},[]
    if op=='official_ci' or op=='git_push'and state.get('remote_branch_sha')==state['candidate_commit'] or op=='pull_request'and state.get('pull_request',{}).get('head_sha')==state['candidate_commit']:
        return {'status':'actual_same_effect_readback_no_new_write','actual_action_allowed':False,'task_id':ctx['task'],'source_request':item['request']},[]
    if op in {'r3_dispatch','pages_deploy'}:
        run=state.get('r3_run'if op=='r3_dispatch'else'pages_run',{})
        if ctx.get('approved_ads_web_bridge') and run.get('id'):
            return {'status':'existing_same_head_run_readback_no_new_dispatch','actual_action_allowed':False,'source_request':item['request']},[]
        if run.get('head_sha')==state.get('main_sha') and run.get('path')==(R3 if op=='r3_dispatch'else PAGES)and run.get('status')in {'queued','in_progress','waiting','pending','completed'}:
            return {'status':'existing_same_head_run_readback_no_new_dispatch','actual_action_allowed':False,'source_request':item['request']},[]
    recovery=bool(state.get('known_zero_push_recovery'))
    need(state.get('effect_state')==('FAILED_KNOWN_ZERO'if recovery else'NOT_STARTED'),'unknown or issued effect must be read back, never blindly retried')
    transport={}
    if op=='git_push' and state.get('material_reviewed_rebase_source'):
        transport={'operation':op,'exact_transport_argv':material_push_transport(ctx,req)}
        if requested.get('consume_approval'):
            need(_material_launch_check is not None,'use run-material-push to prepare transport before consuming its policy')
    if material_r3:
        transport = {'operation': op, 'exact_transport_argv': ['gh', 'workflow', 'run', Path(R3).name,
                     '--repo', ctx['repository'], '--ref', 'main', '--json']}
        if requested.get('consume_approval'):
            need(_material_launch_check is not None, 'use run-material-r3-dispatch to bind fresh GitHub checks before consumption')
    key=w.sha256_value([ctx['task'],ctx['role'],req['action_id'],req['action_class'],req['scope']])
    with w.workflow_lock(root):
        recovery_fields=_recovery_policy_history(root,ctx,req,key)if recovery else{}
        if not recovery:
            issued = w.read_jsonl(Path(root) / w.POLICY_DECISIONS, where={'autonomous_action_key': key, 'status': 'allow'})
            if material_r3:
                if req['action_id'] == material_r3_action:
                    recovery_fields = material_r3_recovery(root, ctx, req, key, issued)
                else:
                    need(not issued, 'single current-main material dispatch already issued; read its effect')
            else:
                need(not issued, 'single original actual action already issued; read unknown effect')
        value={**requested,'status':'preflight_ready_not_a_permit','actual_action_allowed':False,'approval_basis':a.MODE,'original_authority':ctx['authorization'],'delegated_HQ_decision':ctx['decision'],'exact_request':item['request'],'source_preflight':pin,'autonomous_action_key':key,'checked_at':w.utc_timestamp(),'external_execution_department':ctx['role'],'assistant_approval_required':False,'platform_permission_issued':False,**recovery_fields,**transport}
        if material_edge_facts is not None:
            value['material_edge_live_pending'] = material_edge_facts
        if ctx.get('standing_CMS_channel'):
            value.pop('delegated_HQ_decision');value.update(standing_CMS_authority=ctx['decision'],authority_department=ctx['authority_department'],standing_authorization_id=ctx['standing_authorization_id'])
        if ctx.get('original_production_channel'):
            value.pop('delegated_HQ_decision');value.update(original_production_authority=ctx['contract'],original_professional_source=ctx['decision'])
        if requested.get('consume_approval'):
            need(not ctx.get('local_source_stage_only'),'local compatible code source is registered; this source-only stage does not supply original WEB per-action production authority; no five-CMS permission inheritance')
            if transport:
                validation=w._VALIDATION_CONTEXT.get()
                if validation is not None:
                    if material_r3:
                        from material_r3_dispatch import reconcile_handoff_receipts
                        validation.recheck(reconcile_change=lambda name, old, actual:
                            reconcile_handoff_receipts(root, name, old, actual))
                    else:
                        validation.recheck()
                checked_launch = _material_launch_check(ctx,req,pin,transport['exact_transport_argv'])
                if material_r3:
                    observed = w._parse_observed_at(checked_launch['observed_at'])
                    need(observed is not None, 'actual fresh original material R3 launch checks required')
                    value['material_r3_live_launch'] = checked_launch
                value.update(checked_at=w.utc_timestamp(),material_transport_intent=True)
            age=(dt.datetime.now(dt.timezone.utc)-observed).total_seconds()
            need(0<=age<=(290 if transport else 300),'execution observations expired or lack dispatch time; no stale policy consumption')
            if op=='edge_deploy':
                apr=w.effective_approvals(root).get(reference(ctx,state['candidate_commit'],state['main_sha']));need(apr and apr.get('status')=='active','one exact current unconsumed R3 run-bound approval reference')
                if apr.get('source_preflight')!=pin:reference_fresh_preflight(root,apr,pin,req,ctx,'policy')
                need(w._parse_observed_at(apr['platform_binding']['expiresAt'])>dt.datetime.now(dt.timezone.utc),'R3 approval expired, do not extend old permission')
                w.append_jsonl_locked(Path(root)/w.APPROVAL_LEDGER,{**apr,'status':'consumed','consumed_at':w.utc_timestamp()})
            value.update(status='allow',actual_action_allowed=True,approval_status='consumed_for_original_exact_autonomous_action',decision_id='pol-'+w.sha256_value([value,key])[:20]);w.append_jsonl_locked(Path(root)/w.POLICY_DECISIONS,value)
    return value,[Path(root)/w.POLICY_DECISIONS]

def issuer_source_context(root,task,row):
    # Only an actual immutable issuer row may select the appended source for
    # R3 or revocation. Caller flags and a guessed approval ID grant nothing.
    if isinstance(row,dict) and row.get('task_id')==task and row.get('source_preflight'):
        envelope=a.document(root,row['source_preflight']);request=a.document(root,envelope.get('request'))
        if 'hq_singlefield_code_stage_source' in request.get('state',{}):
            ctx=execution_context(root,task,request['state'])
            need(ctx.get('hq_single_field_code_stage') is True and envelope.get('task_id')==task
                 and request.get('task_id')==task and request.get('operation')=='edge_deploy',
                 'actual issuer pinned exact original code-stage preflight required')
            _static_intent_context(root,request,ctx);candidate(ctx,request['state'])
            return ctx
        if 'material_reviewed_rebase_source' in request.get('state',{}):
            from paid_three_page_bounded_cms import MATERIAL_PUBLICATION_TASK
            need(task == envelope.get('task_id') == request.get('task_id') == MATERIAL_PUBLICATION_TASK
                 and request.get('operation') == 'edge_deploy', 'exact original material issuer preflight required')
            ctx=execution_context(root,task,request['state'])
            need(ctx.get('current_owner_reviewed_release') and ctx.get('increment_registration') ==
                 request['state']['material_reviewed_rebase_source'], 'exact original material reviewed issuer source')
            _static_intent_context(root,request,ctx);candidate(ctx,request['state'])
            return ctx
    sources=records(root,task);need(len(sources)==1,'one real original external WEB issuer source')
    return sources[0]

@w.request_validation_context()
def record_approval(root,**kwargs):
    if kwargs.get('revoke'):
        old=w.effective_approvals(root).get(kwargs.get('approval_id'))
        ctx=issuer_source_context(root,kwargs['task_id'],old)
        with w.workflow_lock(root):
            old=w.effective_approvals(root).get(kwargs.get('approval_id'))
            basis=('verified_current_owner_reviewed_release_v1' if ctx.get('current_owner_reviewed_release') else 'verified_frozen_original_production_delivery_v1' if ctx.get('original_production_channel') else 'verified_professional_standing_CMS_WEB_source_v1' if ctx.get('standing_CMS_channel') else 'verified_original_goal_external_WEB_source_v1')
            source_key=('original_professional_source' if ctx.get('original_production_channel') else 'standing_CMS_authority' if ctx.get('standing_CMS_channel') else 'delegated_HQ_decision')
            need(old and old.get('status')=='active'and old.get('approval_basis')==basis
              and old.get(source_key)==ctx['decision']and all(old.get(k)==kwargs.get(k)for k in ('task_id','action_id','action_class','scope')),'exact original still-active own reference only')
            value={**old,'status':'revoked','changed_at':w.utc_timestamp()};w.append_jsonl_locked(Path(root)/w.APPROVAL_LEDGER,value)
        return {**value,'result':'revoked','platform_allowlist_changed':False},[Path(root)/w.APPROVAL_LEDGER]
    pin=w.file_digest(root,kwargs['source_evidence']);item=a.document(root,pin);source=a.document(root,item.get('request'))
    need(source.get('operation')=='edge_deploy'and all(kwargs.get(k)==source[k]for k in ('task_id','action_id','action_class','scope')),'only current exact external WEB pending R3 action')
    selected,req,registered,ctx=preflight(root,source['task_id'],source['action_id'],source['action_class'],source['scope'],source['department'])
    need(selected['request']==item['request']and registered==pin and req==source,'normal genuine preflight event')
    state=req['state']
    human=ctx['current_owner_message']if ctx.get('current_owner_reviewed_release')else a.document(root,ctx['authorization'])
    human_thread=human['source_thread_id']
    human_message=(human['message_id'] if ctx.get('hq_single_field_code_stage') else human['message']['id'])
    need(kwargs.get('source_thread_id')==human_thread and kwargs.get('source_message_ref')==human_message,
         'real original human grant and verified HQ decision, not a new owner signature')
    material_edge_facts = None
    if ctx.get('material_registry_test_successor'):
        from material_edge_live import pending as current_material_pending
        material_edge_facts = current_material_pending(root, ctx, req)
    now=dt.datetime.now(dt.timezone.utc);at=w._parse_observed_at(
        material_edge_facts['observed_at'] if material_edge_facts is not None else req.get('observed_at'))
    need(at and 0<=(now-at).total_seconds()<=300,'fresh actual pending run')
    apr=reference(ctx,state['candidate_commit'],state['main_sha']);need(kwargs.get('approval_id','')in {'',apr},'source-derived reference only')
    with w.workflow_lock(root):
        now=dt.datetime.now(dt.timezone.utc)
        need(0<=(now-at).total_seconds()<=300,'pending run observations expired before approval commit; no stale reference')
        old=w.effective_approvals(root).get(apr)
        if old:need(old.get('status')=='active'and old.get('source_preflight')==pin,'consumed/revoked/unknown reference cannot be reissued');return {**old,'result':'duplicate_ignored'},[Path(root)/w.APPROVAL_LEDGER]
        binding={'version':'r3-release-approval/v1','taskId':ctx['task'],'actionId':req['action_id'],'actionClass':'site_publish','scope':ctx['edge_scope'],'approvalId':apr,'expectedSha':state['main_sha'],'repository':ctx['repository'],'repositoryId':1248188229,'ref':'refs/heads/main','workflowRef':ctx['repository']+'/'+R3+'@refs/heads/main','environment':'production-supabase','eventName':'workflow_dispatch','runId':str(state['r3_run']['id']),'runAttempt':1,'singleUse':True,'status':'active','issuedAt':now.isoformat(),'expiresAt':(now+dt.timedelta(minutes=15)).isoformat()}
        binding['payloadSha256']=hashlib.sha256(json.dumps(binding,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
        # This writer accepts only edge_deploy. Push recovery metadata belongs
        # to the separately validated git_push policy, never this R3 reference.
        value={'schema_version':'1.0','approval_id':apr,'task_id':ctx['task'],'action_id':req['action_id'],'action_class':'site_publish','scope':ctx['edge_scope'],'status':'active','single_use':True,'granted_by':'operations','granted_at':w.utc_timestamp(),'source_thread_id':human_thread,'source_message_ref':human_message,'approval_basis':'verified_original_goal_external_WEB_source_v1','original_human_authorization_pin':ctx['authorization'],'delegated_HQ_decision':ctx['decision'],'source_preflight':pin,'execution_department':ctx['role'],'platform_binding':binding,'platform_permission_issued':False}
        if material_edge_facts is not None:
            value['material_edge_live_pending'] = material_edge_facts
        if ctx.get('standing_CMS_channel'):
            value.pop('delegated_HQ_decision');value.update(approval_basis='verified_professional_standing_CMS_WEB_source_v1',granted_by=ctx['authority_department'],standing_CMS_authority=ctx['decision'],authority_department=ctx['authority_department'],standing_authorization_id=ctx['standing_authorization_id'])
        if ctx.get('original_production_channel'):
            value.pop('delegated_HQ_decision');value.update(approval_basis='verified_current_owner_reviewed_release_v1'if ctx.get('current_owner_reviewed_release')else'verified_frozen_original_production_delivery_v1',granted_by='operations'if ctx.get('current_owner_reviewed_release')else ctx['owner'],original_production_authority=ctx['contract'],original_professional_source=ctx['decision'])
        w.append_jsonl_locked(Path(root)/w.APPROVAL_LEDGER,value)
    return {**value,'result':'recorded'},[Path(root)/w.APPROVAL_LEDGER]

@w.request_validation_context()
def request_base(root,task,op,state):
    if op=='protected_preview':
        from en2_preview_entry import request_base as en2_preview_request_base
        return en2_preview_request_base(root,task,state)
    ctx=execution_context(root,task,state);need(op in OPS,'registered operation')
    need(not ctx.get('protected_body_source_custody'),'original source custody is registered; exact original WEB per-stage authority source required; frozen CMS contract grants no code deployment/site_publish')
    if ctx.get('code_only_release'):need(op in ctx['allowed_operations'],'code-only release excludes R3/Edge/CMS')
    if ctx.get('hq_single_field_code_stage'):need(op in ctx['allowed_operations'],'exact code stage excludes CMS/Pages/cancel/retire')
    head=state.get('candidate_commit');main=state.get('main_sha')if op in {'r3_cancel','r3_retire','edge_deploy','r3_dispatch','pages_deploy'}else None
    need(re.fullmatch('[0-9a-f]{40}',str(head))is not None,'real full candidate head required, no missing or predicted value')
    req={'task_id':task,'sender_department':ctx['role'],'department':ctx['role'],'action_id':action_id(ctx,op,head,main),
      'action_class':OPS[op],'scope':scopes(ctx,op),'source_project_id':a.PROJECT,'execution_project_id':ctx['binding']['project_id'],
      'operation':op,'state':state,'observed_at':state.get('observed_at'),'authorization_changes':[],
      **({'execution_stage_id':ctx['execution_stage_id']} if ctx.get('approved_ads_web_bridge') else {}),
      **({'exact_HQ_singlefield_code_stage_source':ctx['registration']} if ctx.get('hq_single_field_code_stage') else
         {'exact_original_production_source':ctx['registration']} if ctx.get('original_production_channel') else
         {'exact_standing_CMS_channel_source':ctx['registration']} if ctx.get('standing_CMS_channel')
         else {'exact_HQ_production_decision':ctx['decision']})}
    if ctx.get('original_peer_overlap_source'):req['exact_original_overlap_source']=ctx['increment_registration']
    req['desired']=_intent_context(root,req,_static_intent_context(root,req,ctx),check_desired=False)[3]
    # Authenticate all input bytes/raw immutable Git again before output;
    # current HEAD/branch/clean checks still run inside the complete intent.
    w._VALIDATION_CONTEXT.get().recheck()
    return req

@w.request_validation_context()
def build_preflight(root,base_path,facts_native,facts_command,self_native,self_command,backup_path,out_path):
    base=a.document(root,w.file_digest(root,base_path))
    if base.get('operation')=='protected_preview':
        from en2_preview_normal import build_preflight as preview_build
        return preview_build(root,base_path,base['state']['original_web_inventory']['turn_id'],self_command,out_path)
    ctx,op,state,_=intent(root,base)
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
    path=directory/'request.json';w.atomic_write_json(path,request);_validate_request_context(root,request,ctx)
    item={'schema':'professional-external-WEB-fresh-preflight/v1','task_id':ctx['task'],'request':w.file_digest(root,str(path.relative_to(root)))}
    w._VALIDATION_CONTEXT.get().recheck()
    w.atomic_write_json(out,item);return {'state':'prepared_actual_preflight_input_not_a_permission','input':w.file_digest(root,out_path),'request':item['request']}

def source_backup(root,task,state,out_path):
    ctx=execution_context(root,task,state);need(ctx.get('code_only_release') or ctx.get('original_production_channel') or ctx.get('hq_single_field_code_stage'),'exact original code source backup entry')
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

def describe(root,task,state=None):
    sources=[execution_context(root,task,state)] if state and ('code_only_source_registration' in state or 'candidate_commit' in state or 'hq_singlefield_code_stage_source' in state or 'hq_singlefield_test_successor_source' in state) else records(root,task)
    need(len(sources)==1,'one actual registered original WEB production source required; issuer contract/local target alone is not that source')
    ctx=sources[0]
    if ctx.get('hq_single_field_code_stage'):
        return {'task_id':task,'registered_source':ctx['registration'],'source_kind':ctx['source_kind'],
          'HQ_decision':ctx['decision'],'actual_owner_delegation':ctx['authorization'],
          'role':ctx['role'],'binding':ctx['binding'],'original_real_head':ctx['commit'],'original_base':ctx['base'],
          'original_tree':ctx['tree'],'branch':ctx['branch'],'worktree':ctx['worktree'],'source_paths':ctx['paths'],
          'state_selector':({'hq_singlefield_code_stage_source':ctx['successor_base_registration'],
                            'hq_singlefield_test_successor_source':ctx['registration']} if ctx.get('hq_reviewed_test_successor')
                            else {'hq_singlefield_code_stage_source':ctx['registration']}),
          'request_source_marker':{'exact_HQ_singlefield_code_stage_source':ctx['registration']},
          'operations':{op:{'action_class':OPS[op],'scope':scopes(ctx,op),'fresh_original_native_facts_required':True}
                        for op in ctx['allowed_operations']},
          'source_backup':'normal source-backup supports this exact forward source; R3 also needs real current runtime/version backup',
          'excluded_operations':['CMS_Save','CMS_preview','CMS_rollback','Pages','r3_cancel','r3_retire','DB','auth','Ads','account','fees'],
          'minimum_platform_guards':{'fresh_execution_seconds':300,'all_exact_head_required_CI':sorted(CHECKS),
             'R3_workflow':R3,'environment':'production-supabase','R3_run_attempt':1,'approval_TTL_minutes':15,'single_use':True},
          'source_registration_grants_execution_authority':False,'actual_external_action_performed':False}
    if ctx.get('approved_ads_source_discovery_only'):
        import shlex,sys
        repository=ctx['repository'];branch=ctx['branch'];owner=repository.split('/')[0]
        git_endpoints={'actor':'user','repository':'repos/'+repository,'main':'repos/'+repository+'/git/ref/heads/main',
          'branch':'repos/'+repository+'/git/matching-refs/heads/'+branch,
          'pulls':'repos/'+repository+'/pulls?state=all&head='+owner+':'+branch+'&per_page=100'}
        statuses=('queued','in_progress','waiting','pending','requested')
        return {'task_id':task,'original_task_id':ctx['original_task'],'restricted_execution_stage':ctx.get('execution_stage_id',ctx['task']),
          'registered_source':ctx['registration'],'source_event_id':ctx['event_id'],'human_approval':ctx['approval'],
          **({'successor_source':ctx['successor_registration'],'successor_event_id':ctx['successor_event_id'],'actual_parent':ctx['git_parent'],'existing_pull_number':ctx['existing_pull_number']} if ctx.get('approved_ads_test_successor') else {}),
          'role':ctx['role'],'binding':ctx['binding'],'original_real_head':ctx['commit'],'original_base':ctx['base'],
          'original_tree':ctx['tree'],'branch':ctx['branch'],'worktree':ctx['worktree'],'source_paths':ctx['paths'],
          'exact_target_scopes':ctx['target_scopes'],'exact_fields':ctx['fields'],'repository':ctx['repository'],
          'request_base_command':'PYTHONPATH='+shlex.quote(str(Path(root).resolve())+':'+str(Path(root).resolve()/'tools'))+' '+shlex.quote(sys.executable)+' '+shlex.quote(str(Path(root).resolve()/'tools/professional_web_execution.py'))+' request-base --task-id '+shlex.quote(ctx['original_task'])+' --operation git_push --state <project-relative-fresh-state.json> --output <new-project-relative-request.json>',
          'state_fields':['candidate_commit','candidate_parent','candidate_base','candidate_tree','branch','worktree','repository','repository_id','actor','remote_main_sha','remote_branch_sha','effect_state','observed_at','git_effect_proof'],
          'git_effect_proof':{'native':'<original-WEB-native-pin>','commands':{k:'<actual-command-id>' for k in git_endpoints},
             'exact_readonly_argv':{k:['gh','api','--include','--method','GET',v] for k,v in git_endpoints.items()},
             'if_open_PR':'add pull_detail command: gh api --include --method GET repos/<repository>/pulls/<actual-number>'},
          'later_same_head_CI':'gh api --include --method GET repos/<repository>/commits/<actual-head>/check-runs?per_page=100',
          'later_R3_status_argv':{s:['gh','api','--include','--method','GET','repos/'+repository+'/actions/workflows/'+R3.split('/')[-1]+'/runs?per_page=100&status='+s] for s in statuses},
          'later_Pages_status_argv':{s:['gh','api','--include','--method','GET','repos/'+repository+'/actions/workflows/'+PAGES.split('/')[-1]+'/runs?per_page=100&status='+s+('&head_sha=<actual-main>' if s=='completed' else '')] for s in (*statuses,'completed')},
          'proof_rule':'Each exact gh --include GET must preserve complete HTTP status, single GitHub Date/request ID and JSON body. Each server Date must follow turn start, precede the subsequent actual facts and be within 300 seconds. Real completed commands and facts must be in the same original WEB turn; existing per-action single-use gates remain.',
          'serial_order':ctx['order'],'next':'WEB must independently read fresh facts, original effects and full backup. R3 stages need five complete same-turn native shared-run queries. ChatGPT requires the actual post-Google successor.',
          'request_base_status':'AVAILABLE_WITH_EXACT_STAGE_AND_REAL_FACTS',
          'production_policy_status':'NORMAL_INDEPENDENT_PER_ACTION_GATES' if ctx['order']=='Google' else 'WAIT_GOOGLE_ACTUAL_AND_AUTHENTICATED_SUCCESSOR',
          'external_permission_issued':False,
          'source_registration_grants_execution_authority':False,'actual_external_action_performed':False}
    return {'task_id':task,'registered_source':ctx['registration'],'role':ctx['role'],'binding':ctx['binding'],
      **({'original_production_authority':ctx['contract'],'original_professional_source':ctx['decision'],'required_source_components':ctx['source_components']} if ctx.get('original_production_channel') else
         {'standing_CMS_authority':ctx['decision'],'authority_department':ctx['authority_department'],'standing_authorization_id':ctx['standing_authorization_id']} if ctx.get('standing_CMS_channel') else {'decision':ctx['decision']}),
      'original_real_head':ctx['commit'],'branch':ctx['branch'],'source_paths':ctx['paths'],
      'operations':{op:{'action_class':kind,'scope':scopes(ctx,op),'facts_required_at_actual_stage':True}for op,kind in OPS.items()if not ctx.get('code_only_release')or op in ctx['allowed_operations']},
      'minimum_platform_guards':({'all_exact_head_required_CI':sorted(CHECKS),'Pages_workflow':PAGES,'fresh_execution_seconds':300,'single_use':True,'excluded_operations':['CMS','R3','Edge','DB','auth','account','Ads']}if ctx.get('code_only_release')else{'all_exact_head_required_CI':sorted(CHECKS),'R3_workflow':R3,'Pages_workflow':PAGES,'R3_run_attempt':1,'environment':'production-supabase','approval_TTL_minutes':15,'single_use':True}),
      'registered_code_only_stages':[{'source':x['registration'],'commit':x['commit'],'linear_parent':x['git_parent'],'cumulative_base':x['base'],'paths':x['paths'],'operations':list(x['allowed_operations'])} for x in __import__('original_production_delivery').code_records(root,task)],
      'adopted_increments':[{'commit':x['commit'],'base':x['base'],'tree':x['tree'],'branch':x['branch'],'worktree':x['worktree'],'source':x['increment_registration'],'operations':x['increment_allowed_operations'],
                            **{k:x[k]for k in ('git_parent','existing_pull_number','increment_source_mode')if k in x}}for x in __import__('professional_web_increment').sources(root,ctx)],
      **({k:ctx[k]for k in ('registered_protected_body_targets','original_PUB_tuples','current_source_backup','normal_recovery_runbook','production_authority_dependency')}if ctx.get('protected_body_source_custody')else{}),
      **({'current_owner_release_authority':{'human':ctx['authorization'],'HQ_decision':ctx['decision'],'reviewed_package':ctx['reviewed_release_package'],'original_custody_source':ctx['source_custody_registration'],'website_task_id':ctx['website_task_id'],'frozen_business_contract_unchanged':True,'per_stage_single_use_gates_required':True}}if ctx.get('current_owner_reviewed_release')else{}),
      'local_source_stage_only':ctx.get('local_source_stage_only',False),'source_registration_grants_execution_authority':False,
      'future_PR_merge_SHA_run_or_version_provided':False,'actual_external_action_performed':False}

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=['describe','request-base','build-preflight','source-backup','record-push-recovery','push-recovery-probe','run-material-push','run-material-r3-dispatch']);parser.add_argument('--task-id',required=True)
    parser.add_argument('--input');parser.add_argument('--operation',choices=sorted(set(OPS)|{'protected_preview'}));parser.add_argument('--state');parser.add_argument('--base');parser.add_argument('--facts-native');parser.add_argument('--facts-command');parser.add_argument('--self-native');parser.add_argument('--self-command');parser.add_argument('--backup');parser.add_argument('--output')
    args=parser.parse_args();root=Path(__file__).resolve().parents[1]
    try:
        with w.request_validation_context():
            if args.command=='describe':result=describe(root,args.task_id,a.document(root,w.file_digest(root,args.state))if args.state else None)
            elif args.command=='run-material-push':result=run_material_push(root,args.task_id,args.input)
            elif args.command=='run-material-r3-dispatch':
                from material_r3_dispatch import run
                result = run(root, args.task_id, args.input)
            elif args.command=='record-push-recovery':result=record_push_recovery(root,args.task_id,args.input)
            elif args.command=='push-recovery-probe':
                result=push_recovery_probe(root,args.task_id,a.document(root,w.file_digest(root,args.state)))
                need(args.output,'new project output path required');out=w.safe_path(root,args.output);need(not out.exists(),'preserve original probe');w.atomic_write_json(out,result['state']);result['state_file']=w.file_digest(root,args.output)
            elif args.command=='source-backup':result=source_backup(root,args.task_id,a.document(root,w.file_digest(root,args.state)),args.output)
            elif args.command=='request-base':
                result=request_base(root,args.task_id,args.operation,a.document(root,w.file_digest(root,args.state)));need(args.output,'new project input output path required');out=w.safe_path(root,args.output);need(not out.exists(),'preserve original request');w.atomic_write_json(out,result);result={'state':'request_base_prepared_no_permission','input':w.file_digest(root,args.output),'intent_sha256':w.sha256_value(result)}
            else:result=build_preflight(root,args.base,args.facts_native,args.facts_command,args.self_native,args.self_command,args.backup,args.output)
        print(json.dumps(result,ensure_ascii=False,indent=2))
    except (w.WorkflowError,ValueError,KeyError,OSError,subprocess.SubprocessError)as error:parser.exit(1,str(error)+'\n')
