"""Authenticated bounded WEB source discovery; no policy or provider calls.

The registered source preserves the two original tasks and restricted stages.
Discovery does not authorize a request or remove any existing execution gate.
"""
import hashlib
import json
from pathlib import Path
import re
import subprocess

import department_autonomy as a
import goal_delivery_runtime as g
import workflow_control as w

EVENT = 'approved_ads_WEB_production_source'
SCHEMA = 'approved-ads-WEB-production-source/v1'


def need(value, message):
    a.require(value, 'approved ads WEB source: ' + message)


def read_pin(root, pin, website):
    need(isinstance(pin, dict) and set(pin) == {'path', 'sha256', 'size'}, 'exact immutable pin')
    path = Path(pin['path'])
    if not path.is_absolute():
        path = Path(root) / path
    resolved = path.resolve(strict=True)
    need(not path.is_symlink() and (resolved.is_relative_to(Path(root).resolve())
         or resolved.is_relative_to(Path(website).resolve())), 'original project/source path')
    raw = w.validation_bytes(resolved)
    need(len(raw) == pin['size'] and hashlib.sha256(raw).hexdigest() == pin['sha256'], 'immutable source bytes')
    return raw


def document(root, pin, website):
    return json.loads(read_pin(root, pin, website))


def validate(root, source):
    root = Path(root).resolve()
    need(source.get('schema') == SCHEMA, 'typed registered source required')
    binding = w.read_json(root / 'data/department-registry.json')['collaboration_bindings']['designated-development']
    website = Path(binding['cwd']).resolve()
    need(binding['project_id'] != a.PROJECT and binding.get('thread_id') and website.is_dir(), 'fixed external WEB project')
    boundary = document(root, source['boundary'], website)
    evidence = document(root, boundary['WEB_input'], website)
    owner = document(root, boundary['current_owner_approval'], website)
    observation = document(root, boundary['actual_first_party_owner_observation'], website)
    web_observation = document(root, source['WEB_completed_observation'], website)
    need(boundary.get('schema') == 'candidate-two-ad-WEB-production-source-boundary/v1'
         and evidence.get('original_maintenance_task') == boundary.get('maintenance_task_id') == source.get('maintenance_task_id')
         and evidence.get('approval') == boundary.get('current_owner_approval'), 'same original maintenance/approval lineage')
    maintenance = g.restore_goal(root, w.read_json(w.snapshot_path(root, source['maintenance_task_id'])))
    need(maintenance['goal_delivery']['primary_owner'] == 'system-development'
         and maintenance['current_state'] not in w.TERMINAL_STATES
         and not w.validate_workflow_events(root, source['maintenance_task_id']), 'active intact SYS maintenance')
    hq = w.department_registry(root)['operations']['chat_binding']
    item = observation.get('selected_user_item', {})
    need(observation.get('source_tool') == 'mcp__codex_app__read_thread'
         and observation.get('thread', {}).get('id') == owner.get('source_thread') == hq['task_id']
         and observation.get('thread', {}).get('cwd') == hq['cwd']
         and observation.get('turn', {}).get('id') == owner.get('source_turn')
         and item == owner.get('actual_native_user_item') == evidence.get('approval_question_and_answer')
         and item.get('type') == 'userMessage' and item.get('id') == owner.get('source_message_id')
         and owner.get('schema') == 'actual-owner-two-ad-release-authorization/v1', 'actual original human identity and message')
    text = ''.join(x.get('text', '') for x in item.get('content', []) if x.get('type') == 'text')
    match = re.fullmatch(r'<send_user_message_question_reply>\s*(\[.*\])\s*</send_user_message_question_reply>\s*', text, re.S)
    need(match is not None, 'actual human question/answer')
    answers = json.loads(match.group(1))
    need(len(answers) == 1 and answers[0].get('answer') == owner.get('approval') == '批准两项限定发布', 'actual bounded approval')
    web_thread = web_observation.get('thread', {}); turn = web_observation.get('turn', {})
    need(web_observation.get('source_tool') == 'mcp__codex_app__read_thread'
         and all(web_thread.get(k) == binding.get(v) for k, v in [('id','thread_id'),('title','title'),('cwd','cwd')])
         and turn.get('status') == 'completed' and not turn.get('error') and turn.get('completedAt')
         and len(web_observation.get('finals', [])) == 1
         and boundary['WEB_input']['path'] in web_observation['finals'][0].get('text', '')
         and web_observation['finals'][0].get('phase') == 'final_answer', 'actual completed WEB original handback')
    account = document(root, evidence['current_facts']['actor_repo_main_PR'], website)
    repo = json.loads(account['repo']['stdout']); actor = json.loads(account['actor']['stdout'])
    need(account['repo']['exit'] == account['actor']['exit'] == 0 and repo['full_name'].split('/')[0] == actor['login']
         and type(repo['id']) is int and type(actor['id']) is int, 'actual original repo and actor evidence')
    auth_goal = document(root,boundary['Google']['frozen_stage_input'],website)
    auth_pin = w.file_digest(root,auth_goal['human_authorization']['evidence_path'])
    human = a.document(root,auth_pin)
    need(human.get('source_thread_id') == owner['source_thread'] and human.get('message') == item,
         'same actual owner message for both approved releases')
    decision = dict(boundary['current_owner_approval'])
    decision['path'] = str(Path(decision['path']).resolve().relative_to(root))
    need(w.file_digest(root,decision['path']) == decision, 'actual direct human approval pin')
    batches = evidence.get('batches', [])
    need(len(batches) == 2 and evidence.get('release_order') == ['Google', 'ChatGPT']
         and [b.get('batch') for b in batches] == evidence['release_order'], 'exact approved serial batches')
    contexts = []
    for batch in batches:
        name = batch['batch']; selected = owner[name]; version = batch['candidate']; prior = boundary[name]
        need(selected['task_id'] == batch['task_id'] == prior['original_task']
             and selected['candidate_head'] == version['head'] == prior['actual_candidate']
             and version['head'][:8] in answers[0]['question'] and name in answers[0]['question']
             and prior['source_package'] == batch['complete_approved_package'], 'original task/version and human-approved package')
        package = document(root, batch['complete_approved_package'], website)
        role = package.get('business_owner', package.get('original_owner'))
        need(package.get('task_id') == batch['task_id'] and package.get('WEB_executor') == 'designated-development'
             and package.get('CMS_executor') == 'publishing' and a.professional(root, role), 'original owner and executors')
        rows = package.get('four_exact_tuples', package.get('rows')); targets = [r['target'] for r in rows]
        need({t['slug'] for t in targets} == set(selected['objects'].split(',')) and len(targets) == len(set(t['id'] for t in targets))
             and all(t['table'] == 'services' and t['taskId'] == batch['task_id']
                     and t['changedFields'] == selected['CMS_fields']
                     and re.fullmatch('[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}',t['id'])
                     and t['scope'] == 'company.example:services:' + t['id'] + ':' + ','.join(t['changedFields'])
                     for t in targets), 'exact approved objects and fields')
        stage = prior.get('bounded_execution_stage', prior.get('existing_CMS_stage'))
        snap = g.restore_goal(root, w.read_json(w.snapshot_path(root, stage)))
        goal = snap['goal_delivery']; frozen = a.document(root, snap['goal_contract'])
        need(snap['current_state'] not in {'closed', 'failed', 'cancelled'} and not w.validate_workflow_events(root, stage)
             and goal['parent_task_id'] == batch['task_id'] and goal['primary_owner'] == role
             and all(goal.get(k) == frozen.get(k) for k in ('parent_task_id','primary_owner','producer_departments','authorized_scope','human_authorization'))
             and {t['scope'] for t in targets}.issubset(set(goal['authorized_scope'])), 'intact original bounded execution stage')
        if name == 'Google':
            need(snap['goal_contract'] == prior['frozen_stage_input'], 'actual initialized Google stage contract')
        worktree = Path(version['worktree']).resolve(strict=True)
        need(worktree.is_relative_to(website) and worktree.parent.name == '.worktrees', 'original isolated website worktree')
        def git(*args):
            p = subprocess.run(['git', *args], cwd=worktree, capture_output=True, timeout=20)
            need(p.returncode == 0, 'actual original Git objects required')
            return p.stdout
        parents = version.get('parents', [version.get('parent')]); head = version['head']; base = version['base']
        need(re.fullmatch('[0-9a-f]{40}', head) and re.fullmatch('[0-9a-f]{40}', base)
             and git('show','-s','--format=%H %P %T',head).decode().strip() == ' '.join([head,*parents,version['tree']]), 'actual head/parent/tree')
        files = version['files']; paths = [f['path'] for f in files]
        need(len(paths) == len(set(paths)) and set(paths) == set(git('diff','--name-only',base,head).decode().splitlines()), 'exact complete changed paths')
        for f in files:
            path = f['path']; need(not Path(path).is_absolute() and '..' not in Path(path).parts, 'safe relative Git path')
            raw = git('show',head+':'+path)
            need(len(raw) == f['size'] and hashlib.sha256(raw).hexdigest() == f['sha256']
                 and git('ls-tree',head,'--',path).decode().split()[:3] == [f['mode'],'blob',f['blob']], 'exact source bytes/mode/blob')
        for k in ('forward','inverse'): read_pin(root,version[k],website)
        # The approved channel change must not silently alter the shared R3
        # release workflow; bind its real Git bytes before any remote action.
        workflow='.github/workflows/supabase-content-publish-r3.yml'
        release=git('show',head+':'+workflow)
        need(release == git('show',base+':'+workflow)
             and all(token in release for token in (b'workflow_dispatch:', b'production-supabase-content-publish-r3',
                    b'cancel-in-progress: false', b'environment: production-supabase', b'content-publish',
                    b'expected_sha:', b'approval_id:', b'task_id:', b'action_id:', b'action_class:', b'scope:')),
             'unchanged original exact R3 workflow, environment, concurrency and inputs')
        pages='.github/workflows/cloudflare-pages-deploy.yml'; pages_bytes=git('show',head+':'+pages)
        need(pages_bytes==git('show',base+':'+pages) and b'branches: [main]' in pages_bytes
             and b'cancel-in-progress: false' in pages_bytes, 'unchanged original Pages trigger and non-cancelling concurrency')
        for ci in ('furniture-page-pr-ci.yml','interaction-standards-ci.yml','r3-managed-cms-pr-ci.yml'):
            body=git('show',head+':.github/workflows/'+ci).decode()
            need(re.search(r'(?m)^\s*node-version:\s*[\'\"]?22[\'\"]?\s*(?:#.*)?$',body),
                 'each actual approved same-head CI workflow must use Node22')
        remote = git('config','--get','remote.origin.url').decode().strip()
        need(remote in {'https://github.com/'+repo['full_name'], 'https://github.com/'+repo['full_name']+'.git', 'user-3de132cd98be@example.invalid:'+repo['full_name']+'.git'}, 'original repository remote')
        contexts.append({'original_task':batch['task_id'],'task':stage,'owner':role,'role':'designated-development',
          'binding':binding,'commit':head,'base':base,'tree':version['tree'],'branch':version['branch'],
          'worktree':str(worktree),'paths':{f['path']:f['sha256'] for f in files},'target_scopes':[t['scope'] for t in targets],
          'fields':selected['CMS_fields'],'repository':repo['full_name'],'repository_id':repo['id'],'actor_id':actor['id'],
          'contract':snap['goal_contract'],'approval':boundary['current_owner_approval'],'order':name,
          'business_scope':batch['scope'] if name == 'Google' else package['business_scope'],
          'authorization':auth_pin,'decision':decision,'rollback':version['inverse'],
          'source_components':[{'base':base,'head':head,'paths':{f['path']:f['sha256'] for f in files}}],
          'approved_r3_workflow_sha256':hashlib.sha256(release).hexdigest(),
          'approved_ads_source_discovery_only':True,
          'source_registration_grants_execution_authority':False})
    need(len({c['original_task'] for c in contexts}) == len({c['task'] for c in contexts}) == 2, 'distinct original tasks and stages')
    return contexts


def records(root, task):
    rows = [e for e in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS)
            if task in e.get('details', {}).get(EVENT, {}).get('tasks', [])]
    matches = []
    for e in rows:
        entry = e['details'][EVENT]; pin = entry['source']; source = a.document(root, pin)
        contexts = validate(root, source)
        need(e.get('task_id') == source['maintenance_task_id']
             and entry['tasks'] == [c[k] for c in contexts for k in ('original_task','task')],
             'original registered maintenance event and complete task routing')
        for ctx in contexts:
            if task in (ctx['task'], ctx['original_task']):
                matches.append({**ctx, 'registration':pin, 'event_id':e['event_id']})
    need(len(matches) <= 1, 'one actual immutable source per original task/stage')
    return matches


def record(root, task, path):
    pin = w.file_digest(root, path); source = a.document(root, pin)
    need(task == source.get('maintenance_task_id'), 'record under original SYS maintenance only')
    with w.workflow_lock(root):
        contexts = validate(root, source)
        for ctx in contexts:
            previous = records(root, ctx['original_task'])
            if previous:
                need(previous[0]['registration'] == pin, 'existing actual source must not be replaced')
        rows = [e for e in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS) if e.get('details', {}).get(EVENT, {}).get('source') == pin]
        if rows:
            need(len(rows) == 1, 'unique source registration'); return {'result':'duplicate_ignored','event_id':rows[0]['event_id'],'source':pin}
        snap = g.restore_goal(root, w.read_json(w.snapshot_path(root, task)))
        entry = {'source':pin, 'tasks':[c[k] for c in contexts for k in ('original_task','task')]}
        event = w.append_workflow_event(root, task, snap['current_state'], {EVENT:entry})
    return {'result':'recorded','event_id':event['event_id'],'source':pin,'permission_issued':False}

SUCCESSOR_SCHEMA = 'approved-ads-WEB-test-ci-successor/v1'
SUCCESSOR_EVENT = 'approved_ads_WEB_test_ci_successor'


def validate_test_successor(root, source, base):
    """Authenticate one actual producer test-only CI repair; never authorizes execution."""
    import professional_web_execution as web
    need(set(source) == {'schema', 'maintenance_task_id', 'original_task', 'original_source', 'input', 'completed_native'}, 'exact successor source shape')
    need(source['schema'] == SUCCESSOR_SCHEMA and source['original_task'] == base['original_task']
         and base['order'] == 'Google' and source['original_source'] == base['registration'], 'original Google source and task only')
    site = base['binding']['cwd']; data = document(root, source['input'], site)
    native = document(root, source['completed_native'], site)
    need(data.get('original_business_task') == base['original_task']
         and data.get('original_execution_stage') == base['task']
         and data.get('original_SYS_maintenance_task') == source['maintenance_task_id']
         and data.get('unique_original_production_source_event') == base['event_id']
         and data.get('human_approval') == base['approval'], 'source/authority/task/stage linkage')
    thread = native.get('thread', {}); binding = base['binding']
    need(all(thread.get(k) == binding[v] for k,v in [('id','thread_id'),('title','title'),('cwd','cwd')]), 'fixed original WEB native')
    completed = [t for t in native.get('turns', []) if t.get('status') == 'completed' and not t.get('error')
                 and any(m.get('type') == 'agentMessage' and m.get('phase') == 'final_answer'
                         and source['input']['path'] in m.get('text','') for m in t.get('items', []))]
    need(len(completed) == 1 and completed[0].get('completedAt'), 'original WEB completed result references exact source')
    items = completed[0].get('items', [])
    failure = data['actual_normal_request_base_refusal']['argv_native']
    found = [m for m in items if m.get('id') == failure.get('id')]
    need(len(found) == 1 and found[0].get('type') == 'commandExecution' and found[0].get('status') == 'failed'
         and found[0].get('exitCode') == 1 and found[0].get('command') == failure.get('command')
         and found[0].get('cwd') == base['worktree'], 'actual original WEB exact failed source gate')
    ci = data['actual_parent_official_CI']; rows = {c['name']: c for c in ci}
    need(set(rows) == {'furniture-page-pr-checks','interaction-standards','r3-managed-cms-pr-checks'}
         and all(c.get('head_sha') == base['commit'] and c.get('status') == 'completed' for c in ci)
         and rows['furniture-page-pr-checks']['conclusion'] == 'success'
         and rows['interaction-standards']['conclusion'] == rows['r3-managed-cms-pr-checks']['conclusion'] == 'failure', 'real parent CI outcomes')
    # Authenticate the claimed official checks against the original WEB native HTTP response.
    endpoint='repos/'+base['repository']+'/commits/'+base['commit']+'/check-runs?per_page=100'
    calls=[m for m in items if m.get('type')=='commandExecution' and m.get('status')=='completed'
           and m.get('exitCode')==0 and endpoint in m.get('command','') and m.get('cwd')==base['worktree']]
    need(len(calls)==1 and calls[0].get('output',{}).get('truncated') is False, 'actual complete original WEB CI call')
    response=calls[0]['output']['text'].replace('\r\n','\n'); headers,sep,body=response.partition('\n\n')
    need(sep and re.match(r'HTTP/\S+ 200 ',headers) is not None, 'actual successful GitHub CI response')
    result=json.loads(body); actual={c['name']:c for c in result['check_runs'] if c.get('name') in rows}
    need(len(actual)==3 and all(all(actual[k].get(f)==rows[k].get(f) for f in ('id','head_sha','status','conclusion','details_url')) for k in rows), 'official CI exact response lineage')
    tests=[m for m in items if m.get('type')=='commandExecution' and m.get('status')=='completed'
           and m.get('exitCode')==0 and m.get('cwd')==base['worktree'] and 'vitest' in m.get('command','')
           and 'topicClusterBlogRecordsScript.test.ts' in m.get('command','') and 'locks exact publish' in m.get('command','')]
    need(len(tests)==1 and not tests[0].get('output',{}).get('truncated')
         and '1 passed' in tests[0]['output']['text'], 'actual bounded completed WEB test command')
    for pin in data['failure_cause']['full_original_logs']:
        need(b'topicClusterBlogRecordsScript.test.ts' in read_pin(root,pin,site), 'actual failing-test logs')
    for k in ('failed_assertion_local_native','eslint'):
        check = document(root,data['verification'][k],site)
        need(check.get('exit') == 0 and not check.get('stderr'), 'actual original local test and lint evidence')
    v = data['actual_local_successor']; head=v['head']; test='src/lib/topicClusterBlogRecordsScript.test.ts'
    need(v.get('parent') == base['commit'] and v.get('cumulative_base') == base['base']
         and v.get('worktree') == base['worktree'] and v.get('branch') == base['branch']
         and v.get('new_paths') == [test] and test not in base['paths']
         and re.fullmatch('[0-9a-f]{40}',head) and re.fullmatch('[0-9a-f]{40}',v['tree']), 'only exact test successor on original parent')
    need(web.git(base,'show','-s','--format=%H %P %T',head).decode().strip() == ' '.join([head,base['commit'],v['tree']])
         and web.git(base,'diff','--name-only',base['commit'],head).decode().splitlines() == [test]
         and set(web.git(base,'diff','--name-only',base['base'],head).decode().splitlines()) == set(base['paths']) | {test}, 'actual parent/tree and cumulative paths')
    for path, sha in base['paths'].items():
        need(web.git(base,'ls-tree',base['commit'],'--',path) == web.git(base,'ls-tree',head,'--',path)
             and hashlib.sha256(web.git(base,'show',head+':'+path)).hexdigest() == sha, 'all original production and test blobs/modes unchanged')
    files = v['files']; need(len(files) == len(base['paths'])+1 and len({f['path'] for f in files}) == len(files)
         and {f['path'] for f in files} == set(base['paths']) | {test}, 'exact complete source files')
    for f in files:
        raw=web.git(base,'show',head+':'+f['path'])
        need(hashlib.sha256(raw).hexdigest()==f['sha256'] and len(raw)==f['size']
             and web.git(base,'ls-tree',head,'--',f['path']).decode().split()[:3] == [f['mode'],'blob',f['blob']], 'candidate source blob and mode')
    for name,left,right in [('forward',base['commit'],head),('inverse',head,base['commit'])]:
        need(web._patch_delta(read_pin(root,v[name],site))==web._patch_delta(web.git(base,'diff','--binary','--full-index',left,right)), 'exact local forward/inverse patch effects')
    old=web.git(base,'show',base['commit']+':'+test).decode(); new=web.git(base,'show',head+':'+test).decode()
    # All unchanged old text outside the one original case test is immutable.
    start='    const cases = [...workflow.matchAll('; end='    expect(workflow).toContain(\'"$APPROVAL_ID" != "owner-authorized-content-link-repair-20261024"\');'
    need(old.count(start)==new.count(start)==old.count(end)==new.count(end)==1, 'one bounded original workflow assertion')
    oldpre, oldtail=old.split(start); newpre,newtail=new.split(start)
    marker='    const currentFourTargets = '
    need(marker in newpre and newpre.split(marker)[0]==oldpre and oldtail.split(end,1)[1].replace('cases[0]','cases[1]')==newtail.split(end,1)[1], 'no unrelated test changes; original trailing assertions retained')
    for token in ('expect(cases).toHaveLength(3)', 'expect(cases[0]).toEqual(currentFourTargets)', 'expect(cases[1]).toEqual([...shopOfficeTargets, ...paidThreeTargets, ...rollbackTargets])', 'expect(cases[2]).toEqual(publishTargets)', 'test "$MANAGED_OPERATION" = "publish" || exit 1', 'test -z "$PARENT_RUN_ID" || exit 1', 'expect(cases[1]).not.toContain(target)', 'expect(cases[2]).not.toContain(target)'):
        need(token in new, 'original and four-target protective assertions')
    pr=data['existing_PR']; need(type(pr.get('number')) is int and pr['number']>0 and pr.get('branch')==base['branch']
         and pr.get('observed_remote_head')==base['commit'] and pr.get('base_main_observed')==base['base'] and pr.get('state')=='open', 'real original existing PR predecessor')
    return {**base,'commit':head,'git_parent':base['commit'],'tree':v['tree'],
            'paths':{f['path']:f['sha256'] for f in files},'existing_pull_number':pr['number'],
            'approved_ads_test_successor':True,'successor_source':source}


def successor_records(root, base):
    events=[e for e in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS) if e.get('details',{}).get(SUCCESSOR_EVENT,{}).get('original_source')==base['registration']]
    need(len(events)<=1, 'one original test successor; no ambiguous registration')
    if not events:return []
    entry=events[0]['details'][SUCCESSOR_EVENT]; item=a.document(root,entry['source'])
    need(events[0]['task_id']==item['maintenance_task_id'], 'original maintenance event')
    return [{**validate_test_successor(root,item,base),'successor_registration':entry['source'],'successor_event_id':events[0]['event_id']}]


def record_test_successor(root, task, path):
    pin=w.file_digest(root,path);item=a.document(root,pin)
    need(task==item['maintenance_task_id'], 'original maintenance task')
    with w.workflow_lock(root):
        old=records(root,item['original_task']);need(len(old)==1,'one original approved ads source')
        existing=successor_records(root,old[0])
        if existing:
            need(existing[0]['successor_registration']==pin,'existing successor cannot be replaced')
            return {'result':'duplicate_ignored','event_id':existing[0]['successor_event_id'],'source':pin}
        validate_test_successor(root,item,old[0])
        snap=g.restore_goal(root,w.read_json(w.snapshot_path(root,task)))
        need(snap['current_state'] not in w.TERMINAL_STATES and not w.validate_workflow_events(root,task),'active intact maintenance')
        event=w.append_workflow_event(root,task,snap['current_state'],{SUCCESSOR_EVENT:{'source':pin,'original_source':old[0]['registration']}})
    return {'result':'recorded','event_id':event['event_id'],'source':pin,'permission_issued':False}
