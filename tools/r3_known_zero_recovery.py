"""Exact original WEB recovery of one expired, never-started protected R3 run.

No issuer row is rewritten. Cancellation and replacement have distinct keys.
Provider mutations require the normal WEB preflight and consumed single-use
policy, and are executed only from its original worktree.
"""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import json
import os
import shlex
import subprocess
import sys

import workflow_control as w
import department_autonomy as a

EVENT = 'original_WEB_known_zero_R3_replacement'
SCHEMA = 'original-WEB-known-zero-R3-replacement/v1'
CHAIN_SCHEMA = 'original-WEB-zero-release-isolated-R3-replacement/v2'
STATUSES = ('queued', 'in_progress', 'waiting', 'pending', 'requested')


def need(ok, message):
    a.require(ok, 'exact R3 recovery: ' + message)


def now():
    return datetime.now(timezone.utc)


def base_context(root, ctx, reference):
    import r3_platform_binding_transport as carrier
    old, row, request = carrier.context(root, ctx['task'], reference, effect=False)
    need(ctx.get('approved_ads_test_successor') and old.get('approved_ads_test_successor'),
         'authenticated original test successor only')
    fields = ('task', 'role', 'owner', 'authorization', 'contract', 'decision',
              'registration', 'commit', 'base', 'branch', 'worktree', 'edge_scope')
    need(all(old.get(k) == ctx.get(k) for k in fields), 'same immutable original source')
    binding = row['platform_binding']
    need(row.get('status') == 'active' and row.get('single_use') is True
         and binding.get('singleUse') is True
         and w._parse_observed_at(binding['expiresAt']) <= now(),
         'original unused expired reference; never revive it')
    need(request['state']['candidate_commit'] == ctx['commit'], 'exact candidate')
    permits = [p for p in w.read_jsonl(Path(root) / w.POLICY_DECISIONS)
               if p.get('status') == 'allow' and p.get('task_id') == ctx['task']]
    need(not any(p.get('action_id') == binding['actionId'] for p in permits),
         'old Edge policy must never have been consumed')
    dispatches = []
    import professional_web_execution as web
    for p in permits:
        if p.get('action_id') == web.action_id(old, 'r3_dispatch', ctx['commit'], binding['expectedSha']):
            req = a.document(root, p['exact_request'])
            need(req.get('operation') == 'r3_dispatch'
                 and req.get('desired', {}).get('approval_id') == reference,
                 'actual original consumed dispatch and exact old reference')
            dispatches.append(p)
    need(len(dispatches) == 1, 'one actual original spent dispatch')
    directory = Path(root) / 'backups' / ctx['task'] / 'R3-platform-binding-transport' / reference
    names=('intent.json','attempt.json','readback.jsonl')
    present=[(directory/n).exists() or (directory/n).is_symlink() for n in names]
    if any(present):
        need(all(present) and all((directory/n).is_file() and not (directory/n).is_symlink() for n in names)
             and old.get('r3_replacement_source') is not None,
             'only a registered parent recovery may isolate its own complete unknown carrier history')
        intent=w.read_json(directory/'intent.json');attempt=w.read_json(directory/'attempt.json');reads=w.read_jsonl(directory/'readback.jsonl')
        issued=w._parse_observed_at(binding['issuedAt']);before=w._parse_observed_at(intent.get('at'))
        attempted=w._parse_observed_at(attempt.get('at'));read_at=w._parse_observed_at(reads[0].get('at')) if len(reads)==1 else None
        need(intent.get('binding')==binding and attempt.get('state')=='mutation_intent_durable'
             and attempt.get('attempts')==1 and len(reads)==1 and issued and before and attempted and read_at
             and issued<=before<=attempted<=read_at<=now()
             and reads[0].get('state')=='UNKNOWN_WRITE_EFFECT_NO_RETRY' and reads[0].get('new_write')=='UNKNOWN'
             and reads[0].get('approval_id')==reference and not ((directory/'retry_attempt.json').exists()
                  or (directory/'retry_attempt.json').is_symlink()),
             'one intact original UNKNOWN carrier attempt, never proof of zero API calls')
        level,after,duplicate=carrier.proposal(intent.get('before'),binding,before)
        need(not duplicate and level==intent.get('target_level') and carrier.digest(after)==intent.get('after_sha256'),
             'unchanged normal original variable proposal and whole-value intent')
    return old, row, request, dispatches[0]


def select_cancel(root, ctx, state):
    proof = state.get('r3_cancel')
    if proof is None:
        return ctx
    need(isinstance(proof, dict) and set(proof) in ({'approval_id','native','commands'},
         {'approval_id','native','commands','carrier_native','carrier_command'}), 'exact cancellation proof shape')
    old, row, _, _ = base_context(root, ctx, proof['approval_id'])
    b = row['platform_binding']; parent=old.get('r3_replacement_source')
    need((parent is None and set(proof)=={'approval_id','native','commands'}) or
         (parent is not None and set(proof)=={'approval_id','native','commands','carrier_native','carrier_command'}),
         'isolated unknown requires exact original carrier native proof')
    need(state.get('r3_replacement_source')==parent and state.get('main_sha') == b['expectedSha'],
         'original merged main and actual issuer parent source only')
    return {**ctx, 'r3_parent_source':parent, 'r3_cancel_run_id': int(b['runId']),
            'r3_cancel_reference': b['approvalId'],
            'prefix': ctx['prefix'] + '-cancel-run-' + str(b['runId'])}


def _normal_status_argv(root, ctx, command, reference):
    argv = shlex.split(command)
    if len(argv) == 3 and argv[0] in ('/bin/zsh', '/bin/bash') and argv[1] in ('-lc', '-c'):
        argv = shlex.split(argv[2])
    allowed_env = {'PYTHONDONTWRITEBYTECODE': '1',
                   'PYTHONPATH': str(root) + ':' + str(Path(root) / 'tools')}
    while argv and '=' in argv[0]:
        key, value = argv.pop(0).split('=', 1)
        need(allowed_env.get(key) == value, 'exact trusted runtime environment')
    need(argv and Path(argv[0]).resolve()==Path(sys.executable).resolve(), 'same trusted Python status executable')
    argv.pop(0)
    if argv and argv[0] == '-B':
        argv.pop(0)
    need(argv == [str(Path(root) / 'tools/r3_platform_binding_transport.py'), 'status',
                  '--task-id', ctx['task'], '--approval-id', reference],
         'only exact normal original carrier status')


def official_web_turn(root, binding, turn_id, *, _registration_event_time=None):
    """Read full native history without opening or waking a desktop thread."""
    import department_event_dispatcher as history_api
    rpc=history_api.RPC([history_api.native_queue_capability(root),'app-server','--listen','stdio://'])
    try:
        thread=rpc.call('thread/read',{'threadId':binding['thread_id'],'includeTurns':False})['thread']
        full=rpc.call('thread/turns/list',{'threadId':binding['thread_id'],'limit':20,'sortDirection':'desc','itemsView':'full'})
    finally:rpc.close()
    need(thread.get('id')==binding['thread_id'] and thread.get('cwd')==binding['cwd']
         and thread.get('name')==binding['title'] and 'projectId' in thread,
         'actual official WEB identity/project')
    turns=[t for t in full.get('data',[]) if t.get('id')==turn_id]
    need(len(turns)==1 and not turns[0].get('error'),'one actual full native WEB turn')
    if thread['projectId'] is None:
        # Only the official full same-turn tool result may resolve this legacy
        # null field. Caller supplied maps and historical pins cannot.
        turn=turns[0]
        calls=[x for x in turn.get('items',[]) if x.get('type')=='mcpToolCall'
               and x.get('server')=='codex_app' and x.get('tool')=='list_projects']
        need(calls, 'actual same-turn project inventory required for null metadata')
        # The current path must never fall back to an older successful call.
        # For a previously committed source, only observations actually started
        # by the immutable registration time existed at that point in history.
        checked_at=now()
        if _registration_event_time is not None:
            checked_at=w._parse_observed_at(_registration_event_time)
            need(checked_at and checked_at<=now(), 'actual nonfuture registration time required')
            need(all(type(x.get('startedAtMs')) is int for x in calls),
                 'historical project call ordering must be unambiguous')
            calls=[x for x in calls if x['startedAtMs']<=checked_at.timestamp()*1000]
            need(calls, 'project inventory existed before source registration')
        call=calls[-1]; started=call.get('startedAtMs'); finished=call.get('completedAtMs')
        need(call.get('status')=='completed' and call.get('error') is None and call.get('arguments')=={}
             and type(started) is int and type(finished) is int and started<=finished
             and type(turn.get('startedAt')) in (int,float) and turn['startedAt']*1000<=started
             and 0<=checked_at.timestamp()-finished/1000<=300,
             'fresh actual completed project inventory and timing required')
        result=call.get('result');need(isinstance(result,dict) and result.get('isError',False) is False,
                                       'complete official project inventory required')
        content=result.get('content');need(isinstance(content,list) and len(content)==1
                 and isinstance(content[0],dict) and content[0].get('type')=='text' and isinstance(content[0].get('text'),str),
                 'complete official project inventory text required')
        try: inventory=json.loads(content[0]['text'])
        except (ValueError,TypeError): need(False,'valid official project inventory required')
        need(isinstance(inventory,dict) and inventory.get('schemaVersion')==2
             and isinstance(inventory.get('projects'),list), 'official project inventory schema required')
        rows=inventory['projects'];need(all(isinstance(x,dict) for x in rows),'valid official project rows required')
        by_path=[x for x in rows if x.get('path')==binding['cwd'] and x.get('hostId')==binding['host_id']]
        by_id=[x for x in rows if x.get('projectId')==binding['project_id']]
        need(len(by_path)==len(by_id)==1 and by_path[0]==by_id[0]
             and by_path[0].get('projectKind')=='local' and binding['host_id']=='local'
             and isinstance(binding.get('project_name'),str) and by_path[0].get('label')==binding['project_name'],
             'unique actual registered local project path and host required')
    else:
        need(thread['projectId']==binding['project_id'],'non-null original project identity required')
    return turns[0]


def authenticate_actual_facts(root, ctx, projected_turn, facts_id):
    actual=official_web_turn(root,ctx['binding'],projected_turn.get('id'))
    projected=[m for m in projected_turn.get('items',[]) if m.get('id')==facts_id]
    genuine=[m for m in actual.get('items',[]) if m.get('id')==facts_id]
    need(len(projected)==len(genuine)==1, 'one original facts call in official history')
    p,q=projected[0],genuine[0]
    need(all(p.get(k)==q.get(k) for k in ('id','type','status','exitCode','cwd','command'))
         and w._completion_execution_output(p).decode()==q.get('aggregatedOutput')
         and type(q.get('completedAtMs')) is int, 'facts call exactly matches official native history')
    return True


def authenticate_isolated_unknown(root,ctx,reference,proof,binding):
    """Authenticate original UNKNOWN as history only, never as zero API effect."""
    import goal_delivery_runtime as g
    import professional_web_execution as web
    directory=Path(root)/'backups'/ctx['task']/'R3-platform-binding-transport'/reference
    pins={name:w.file_digest(root,str((directory/name).relative_to(root))) for name in ('intent.json','attempt.json','readback.jsonl')}
    attempt=w.read_json(directory/'attempt.json');at=w._parse_observed_at(attempt.get('at'))
    need(at is not None,'actual original carrier attempt time')
    page=g._native_document(root,proof['carrier_native']);pairs=[(t,m) for t in page.get('turns',[]) for m in t.get('items',[]) if m.get('id')==proof['carrier_command']]
    need(len(pairs)==1,'one actual original carrier install command')
    turn,command=pairs[0];raw=web.native(root,ctx,proof['carrier_native'],proof['carrier_command']);output=json.loads(raw)
    argv=shlex.split(command.get('command',''))
    if len(argv)==3 and argv[0] in ('/bin/zsh','/bin/bash') and argv[1] in ('-lc','-c'):argv=shlex.split(argv[2])
    allowed={'PYTHONDONTWRITEBYTECODE':'1','PYTHONPATH':str(root)+':'+str(Path(root)/'tools')}
    while argv and '=' in argv[0]:
        key,value=argv.pop(0).split('=',1);need(allowed.get(key)==value,'original carrier runtime environment')
    need(argv and Path(argv.pop(0)).resolve()==Path(sys.executable).resolve(),'original trusted Python')
    if argv and argv[0]=='-B':argv.pop(0)
    need(argv==[str(Path(root)/'tools/r3_platform_binding_transport.py'),'install','--task-id',ctx['task'],'--approval-id',reference],
         'exact original normal carrier command')
    facts=output.get('facts',{})
    need(output.get('state')=='UNKNOWN_WRITE_EFFECT_NO_RETRY' and output.get('new_write')=='UNKNOWN'
         and output.get('approval_id')==reference and facts.get('run_id')==int(binding['runId'])
         and facts.get('run_attempt')==1 and facts.get('head')==binding['expectedSha']
         and facts.get('repository')==ctx['repository'] and facts.get('actor',{}).get('id')==ctx['actor_id'],
         'original actual UNKNOWN output and exact run/actor; never infer zero API calls')
    actual=official_web_turn(root,ctx['binding'],turn['id'],_registration_event_time=attempt['at'])
    matches=[m for m in actual.get('items',[]) if m.get('id')==proof['carrier_command']]
    need(len(matches)==1 and all(command.get(k)==matches[0].get(k) for k in ('id','type','status','exitCode','cwd','command'))
         and w._completion_execution_output(command).decode()==matches[0].get('aggregatedOutput')
         and type(matches[0].get('startedAtMs')) is int and type(matches[0].get('completedAtMs')) is int
         and matches[0]['startedAtMs']<=at.timestamp()*1000<=matches[0]['completedAtMs'],
         'actual official original completed carrier command, output and attempt time')
    return {'native':proof['carrier_native'],'command_id':proof['carrier_command'],'files':pins}


def validate_zero(root, ctx, state, terminal=False):
    import professional_web_execution as web
    import goal_delivery_runtime as g
    proof = state['r3_cancel']
    old, row, request, dispatch = base_context(root, ctx, proof['approval_id'])
    b = row['platform_binding']; rid = int(b['runId']); repo = 'repos/' + ctx['repository']
    endpoints = {'run': repo + '/actions/runs/' + str(rid),
                 'jobs': repo + '/actions/runs/' + str(rid) + '/jobs?per_page=100',
                 'reviews': repo + '/actions/runs/' + str(rid) + '/approvals',
                 'runtime_before': repo + '/git/ref/heads/main',
                 'runtime_after': repo + '/git/ref/heads/main'}
    for status in STATUSES:
        endpoints['shared_' + status] = (repo + '/actions/workflows/' + web.R3.split('/')[-1]
                                         + '/runs?per_page=100&status=' + status)
    need(set(proof['commands']) == set(endpoints) | {'carrier_status','runtime_tool'}, 'complete bounded proof')
    page = g._native_document(root, proof['native']); binding = ctx['binding']
    need(all(page.get('thread', {}).get(k) == binding[v]
             for k, v in {'id': 'thread_id', 'title': 'title', 'cwd': 'cwd'}.items()),
         'actual original WEB native identity')
    values = {}; turn_id = None
    for name, cid in proof['commands'].items():
        rows = [(t, m) for t in page.get('turns', []) for m in t.get('items', []) if m.get('id') == cid]
        need(len(rows) == 1, 'one actual native command per query')
        turn, command = rows[0]
        need(turn_id is None or turn_id == turn.get('id'), 'same true WEB turn')
        turn_id = turn['id']
        if name == 'runtime_tool':
            need(command.get('type')=='mcpToolCall' and command.get('status')=='completed'
                 and command.get('server')=='codex_apps' and command.get('tool')=='supabase.list_edge_functions'
                 and command.get('arguments')=={'project_id':ctx['project_ref']}, 'original WEB runtime tool marker')
            values[name] = command
        elif name == 'carrier_status':
            _normal_status_argv(root, ctx, command['command'], proof['approval_id'])
            values[name] = json.loads(web.native(root, ctx, proof['native'], cid))
        else:
            values[name] = web._approved_ads_gh_response(ctx, state, turn, command, endpoints[name])
    # Use the official read-only app-server history for full provider output and
    # native per-call times; the desktop projection intentionally omits result.
    original=official_web_turn(root,binding,turn_id).get('items',[]); positions={m.get('id'):i for i,m in enumerate(original)}
    need(all(cid in positions for cid in proof['commands'].values()), 'all exact native commands exist in official turn')
    for name,cid in proof['commands'].items():
        if name=='runtime_tool':continue
        projected=[m for t in page.get('turns',[]) for m in t.get('items',[]) if m.get('id')==cid][0];actual=original[positions[cid]]
        need(all(projected.get(k)==actual.get(k) for k in ('id','type','status','exitCode','cwd','command'))
             and w._completion_execution_output(projected).decode()==actual.get('aggregatedOutput'),
             'exact native command and complete output match official history')
    runtime=original[positions[proof['commands']['runtime_tool']]]
    need(runtime.get('type')=='mcpToolCall' and runtime.get('server')=='codex_apps'
         and runtime.get('tool')=='supabase.list_edge_functions' and runtime.get('status')=='completed'
         and runtime.get('error') is None and runtime.get('arguments')=={'project_id':ctx['project_ref']}
         and type(runtime.get('startedAtMs')) is int and type(runtime.get('completedAtMs')) is int
         and runtime['startedAtMs']<=runtime['completedAtMs'], 'actual original provider call and precise times')
    result=runtime.get('result');need(isinstance(result,dict) and result.get('isError',False) is False, 'actual complete provider result')
    content=result.get('content');need(isinstance(content,list) and len(content)==1 and content[0].get('type')=='text', 'one actual provider content')
    functions=json.loads(content[0]['text']).get('functions');need(isinstance(functions,list), 'actual full provider functions')
    oldbackup=a.document(root,request['backup']);pin=oldbackup['source_backup']
    backup=web.external(root,pin,ctx['binding']) if Path(pin['path']).is_absolute() else a.document(root,pin)
    baseline=web.external(root,backup['runtime_files'][0],ctx['binding'])['functions']
    def select(rows):return [x for x in rows if x.get('name')=='content-publish' and x.get('slug')=='content-publish']
    current,prior=select(functions),select(baseline);fields=('id','name','slug','status','version','updated_at','ezbr_sha256')
    need(len(current)==len(prior)==1 and all(current[0].get(k)==prior[0].get(k) for k in fields)
         and type(state.get('runtime_version')) is int and current[0].get('version')==state['runtime_version']
         and state.get('project_ref')==ctx['project_ref'] and state.get('function')=='content-publish',
         'actual provider runtime matches original backup and current state')
    import email.utils
    def response_date(cid):
        raw=original[positions[cid]]['aggregatedOutput'].replace('\r\n','\n').partition('\n\n')[0]
        dates=[line[5:].strip() for line in raw.splitlines()[1:] if line.lower().startswith('date:')]
        need(len(dates)==1,'one authenticated HTTP Date');return email.utils.parsedate_to_datetime(dates[0]).timestamp()
    pre=proof['commands']['runtime_before'];post=proof['commands']['runtime_after'];tool=proof['commands']['runtime_tool']
    need(positions[pre]<positions[tool]<positions[post]
         and response_date(pre)*1000<=runtime['startedAtMs']<=runtime['completedAtMs']<=(response_date(post)+1)*1000,
         'actual provider call bracketed by fresh same-turn HTTP Date')
    need(values['runtime_before'].get('object',{}).get('sha')==values['runtime_after'].get('object',{}).get('sha')==b['expectedSha'],
         'same actual main across runtime read')
    statuscall=original[positions[proof['commands']['carrier_status']]]
    observed=w._parse_observed_at(state['observed_at']);now_at=now().timestamp()
    need(type(statuscall.get('startedAtMs')) is int and type(statuscall.get('completedAtMs')) is int
         and statuscall['startedAtMs']<=statuscall['completedAtMs']<=observed.timestamp()*1000
         and 0<=now_at-statuscall['startedAtMs']/1000<=300, 'original carrier status actual time is fresh and precedes facts')
    # Git/CI and cancellation facts must belong to the same actual WEB turn.
    gitpage = g._native_document(root, state['git_effect_proof']['native'])
    gitids = set(state['git_effect_proof']['commands'].values())
    gitturns = {t['id'] for t in gitpage.get('turns', [])
                if any(m.get('id') in gitids for m in t.get('items', []))}
    need(gitturns == {turn_id}, 'same-turn original Git and recovery observations')
    run = values['run']
    need(run.get('id') == rid and run.get('run_attempt') == 1
         and run.get('event') == 'workflow_dispatch' and run.get('path') == web.R3
         and run.get('head_sha') == b['expectedSha'] == state['main_sha']
         and run.get('head_branch') == 'main'
         and run.get('repository', {}).get('id') == ctx['repository_id']
         and run.get('actor', {}).get('id') == ctx['actor_id'], 'exact original actual run')
    need((run.get('status') == 'completed' and run.get('conclusion') == 'cancelled') if terminal
         else (run.get('status') == 'waiting' and run.get('conclusion') is None),
         'cancelled terminal' if terminal else 'protected unstarted waiting run only')
    jobs = values['jobs']; rows = jobs.get('jobs', [])
    need(type(jobs.get('total_count')) is int and jobs['total_count'] == len(rows), 'complete jobs')
    release = [j for j in rows if j.get('name') == 'release']
    need(len(release) == 1 and release[0].get('steps') == []
         and (release[0].get('status') == 'completed' if terminal else release[0].get('status') == 'waiting'),
         'release must never have executed any step')
    need(values['reviews'] == [], 'no environment review')
    active = []
    for status in STATUSES:
        data = values['shared_' + status]; runs = data.get('workflow_runs', [])
        need(type(data.get('total_count')) is int and data['total_count'] == len(runs),
             'complete shared run queue')
        for item in runs:
            need(item.get('status') == status and item.get('path') == web.R3, 'exact shared queue')
        active.extend(runs)
    need(active == [] if terminal else len(active) == 1 and active[0].get('id') == rid
         and active[0].get('run_attempt') == 1, 'no concurrent or unknown shared run')
    status = values['carrier_status']; facts = status.get('facts', {})
    need(status.get('state') == 'NO_EXACT_BINDING_OBSERVED_NOT_A_WRITE_PROOF'
         and status.get('read_only') is True and status.get('binding_currently_unexpired') is False
         and status.get('local_approval_status') == 'active'
         and status.get('own_binding_counts') == {'repository': 0, 'environment': 0}
         and int(facts.get('run_id', 0)) == rid and facts.get('run_attempt') == 1
         and facts.get('head') == b['expectedSha']
         and facts.get('actor', {}).get('id') == ctx['actor_id'], 'actual expired untransported reference')
    result={'old_reference': b['approvalId'], 'old_run': rid, 'main': b['expectedSha'],
            'candidate': ctx['commit'], 'old_dispatch_decision': dispatch['decision_id'],
            'old_dispatch_key': dispatch['autonomous_action_key'], 'terminal': terminal}
    if old.get('r3_replacement_source') is not None:
        evidence=authenticate_isolated_unknown(root,ctx,proof['approval_id'],proof,b)
        result.update(parent_replacement_source=old['r3_replacement_source'],
                      carrier_effect='UNKNOWN_PRESERVED_NOT_A_ZERO_API_CLAIM',carrier_unknown_evidence=evidence)
    return result


def cancellation_directory(root, ctx):
    return Path(root) / 'backups' / ctx['task'] / 'R3-known-zero-cancel' / str(ctx['r3_cancel_run_id'])


def _read_api(ctx, method, endpoint):
    # No arbitrary URL, workflow, account, environment review or variable writes.
    import professional_web_execution as web
    repo = 'repos/' + ctx['repository']; rid = str(ctx['r3_cancel_run_id'])
    allowed_get = {repo + '/actions/runs/' + rid,
                   repo + '/actions/runs/' + rid + '/jobs?per_page=100',
                   repo + '/actions/runs/' + rid + '/approvals'}
    need((method == 'GET' and endpoint in allowed_get)
         or (method == 'POST' and endpoint == repo + '/actions/runs/' + rid + '/cancel'),
         'bounded exact original run transport only')
    result = subprocess.run(['gh', 'api', '--hostname', 'github.com', '--method', method,
                             endpoint, '-H', 'Accept: application/vnd.github+json'],
                            cwd=ctx['worktree'], capture_output=True, text=True, timeout=25)
    need(result.returncode == 0, 'provider response failed/unknown; no automatic replay')
    return json.loads(result.stdout) if result.stdout.strip() else None


def fresh_cancel_continuation(root,task,original,continuation_path):
    """Authenticate one unattempted consumed cancellation using new WEB facts."""
    import professional_web_execution as web
    doc=a.document(root,w.file_digest(root,continuation_path))
    need(set(doc)=={'schema','original_request','fresh_request','failure_input','failure_turn'}
         and doc['schema']=='original-WEB-unattempted-R3-cancel-fresh/v1', 'exact continuation shape')
    old=a.document(root,doc['original_request']);fresh=a.document(root,doc['fresh_request'])
    need(old==original and old.get('task_id')==task and old.get('operation')=='r3_cancel', 'one exact original immutable cancellation')
    packet=web.external(root,doc['failure_input'],web.execution_context(root,task,fresh['state'])['binding'])
    need(packet.get('schema')=='original-SYS-exact-unattempted-cancel-fresh-continuation-input/v10'
         and packet.get('actual_request')==doc['original_request'], 'original WEB failure input and request pin')
    policy=packet.get('actual_policy',{}); rows=[p for p in w.read_jsonl(Path(root)/w.POLICY_DECISIONS) if p.get('decision_id')==policy.get('decision_id')]
    need(len(rows)==1 and rows[0]==policy and policy.get('status')=='allow' and policy.get('actual_action_allowed') is True
         and policy.get('consume_approval') is True and policy.get('approval_status')=='consumed_for_original_exact_autonomous_action'
         and policy.get('exact_request')==doc['original_request'] and policy.get('payload_sha256')==doc['original_request']['sha256'],
         'one actual consumed original cancellation policy')
    fixed=('task_id','sender_department','department','action_id','action_class','scope','source_project_id','execution_project_id','operation','authorization_changes','execution_stage_id','exact_original_production_source','desired')
    mutable={'state','observed_at','facts','self_check','backup','rollback'}
    need(set(old)==set(fresh) and all(old.get(k)==fresh.get(k) for k in set(old)-mutable)
         and all(old.get(k)==fresh.get(k) for k in fixed) and fresh.get('operation')=='r3_cancel', 'same exact action/authority/desired; no new permission')
    before=old.get('state',{});after=fresh.get('state',{})
    fields=('candidate_commit','candidate_parent','candidate_base','candidate_tree','branch','worktree','repository','repository_id','actor','main_sha','main_local_sha','remote_main_sha','project_ref','function','merged_pull_request','r3_replacement_source')
    need(all(before.get(k)==after.get(k) for k in fields)
         and before.get('r3_cancel',{}).get('approval_id')==after.get('r3_cancel',{}).get('approval_id')
         and before.get('r3_cancel',{}).get('carrier_native')==after.get('r3_cancel',{}).get('carrier_native')
         and before.get('r3_cancel',{}).get('carrier_command')==after.get('r3_cancel',{}).get('carrier_command'),
         'same candidate, actor, run reference, parent and original UNKNOWN evidence')
    ctx,op,state=web.validate_request(root,fresh)
    need(op=='r3_cancel' and ctx['task']==task and policy.get('department')==ctx['role']
         and all(policy.get(k)==old.get(k) for k in ('task_id','action_id','action_class','scope')), 'fresh original WEB validator and exact consumed policy')
    failure=packet.get('actual_refusal',{});need(failure.get('status')=='failed' and failure.get('exitCode')==1
         and type(failure.get('startedAtMs')) is int and type(failure.get('completedAtMs')) is int
         and failure['startedAtMs']<=failure['completedAtMs'], 'one real failed command')
    observed=w._parse_observed_at(fresh.get('observed_at'))
    need(observed and observed.timestamp()*1000>failure['completedAtMs'], 'new real observations must follow original failure')
    ts=datetime.fromtimestamp(failure['startedAtMs']/1000,timezone.utc).isoformat()
    turn=official_web_turn(root,ctx['binding'],doc['failure_turn'],_registration_event_time=ts)
    items=[x for x in turn.get('items',[]) if x.get('id')==failure.get('id')]
    need(len(items)==1 and all(items[0].get(k)==failure.get(k) for k in ('id','type','status','exitCode','cwd','command','aggregatedOutput','startedAtMs','completedAtMs')),
         'actual official original failure command and full output')
    call=items[0];argv=shlex.split(call.get('command',''))
    if len(argv)==3 and argv[0] in ('/bin/zsh','/bin/bash') and argv[1] in ('-lc','-c'):argv=shlex.split(argv[2])
    allowed={'PYTHONDONTWRITEBYTECODE':'1','PYTHONPATH':str(root)+':'+str(Path(root)/'tools')}
    while argv and '=' in argv[0]:
        key,value=argv.pop(0).split('=',1);need(allowed.get(key)==value,'exact trusted failure environment')
    need(argv and Path(argv.pop(0)).resolve()==Path(sys.executable).resolve(),'original trusted interpreter')
    if argv and argv[0]=='-B':argv.pop(0)
    need(argv==[str(Path(root)/'tools/r3_known_zero_recovery.py'),'cancel','--task-id',task,'--request',doc['original_request']['path']]
         and Path(call.get('cwd','')).resolve()==Path(ctx['worktree']).resolve(), 'exact original normal cancellation command')
    output=call.get('aggregatedOutput','')
    need('web.intent(root, req)' in output and 'fresh actual completed project inventory and timing required' in output
         and 'CANCEL_INTENT_DURABLE_NO_REPLAY' not in output, 'exact original pre-attempt freshness refusal only')
    directory=cancellation_directory(root,ctx);attempt=directory/'attempt.json'
    need(not attempt.exists() and not attempt.is_symlink(), 'original cancellation attempt remains absent; no replay')
    return ctx,state,policy,doc


def cancel(root, task, request_path, continuation_path=None):
    import professional_web_execution as web
    import r3_platform_binding_transport as carrier
    req = a.document(root, w.file_digest(root, request_path))
    if continuation_path:
        ctx,state,prior,continuation=fresh_cancel_continuation(root,task,req,continuation_path)
        fresh=a.document(root,continuation['fresh_request']);op='r3_cancel'
    else:
        ctx, op, state = web.validate_request(root, req);fresh=req
    need(op == 'r3_cancel' and task == ctx['task'], 'exact normal cancellation request')
    need(Path.cwd().resolve() == Path(ctx['worktree']).resolve(), 'original WEB working directory')
    if continuation_path:
        from approved_ads_web_source import records as approved_ads_records
        ads=approved_ads_records(root,task);holder=ads[0]['task'] if len(ads)==1 else task
        rows=[e['details']['professional_WEB_preflight'] for e in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS,where={'task_id':holder}) if e.get('task_id')==holder and e.get('details',{}).get('professional_WEB_preflight',{}).get('action_id')==req['action_id']]
        need(rows and rows[-1].get('input')==prior.get('source_preflight') and rows[-1].get('request')==continuation['original_request'], 'latest original registered preflight and policy')
        item=a.document(root,rows[-1]['input']);pin=rows[-1]['input']
        need(item.get('request')==continuation['original_request'], 'unchanged preflight request pin')
    else:
        item, current, pin, _ = web.preflight(root, task, req['action_id'], req['action_class'], req['scope'], ctx['role'])
        need(current == req, 'actual latest normal preflight')
    policies = [p for p in w.read_jsonl(Path(root) / w.POLICY_DECISIONS)
                if p.get('status') == 'allow' and p.get('task_id') == task
                and p.get('action_id') == req['action_id']]
    key=w.sha256_value([ctx['task'],ctx['role'],req['action_id'],req['action_class'],req['scope']])
    need(len(policies) == 1 and policies[0].get('actual_action_allowed') is True
         and policies[0].get('consume_approval') is True and policies[0].get('approval_status')=='consumed_for_original_exact_autonomous_action'
         and policies[0].get('department')==ctx['role'] and policies[0].get('action_class')==req['action_class']
         and policies[0].get('scope')==req['scope'] and policies[0].get('source_preflight')==pin
         and policies[0].get('autonomous_action_key')==key and policies[0].get('exact_request') == item['request'],
         'own consumed single-use cancellation policy')
    proof = validate_zero(root, ctx, state)
    directory = cancellation_directory(root, ctx)
    with carrier.serialized(root, ctx):
        attempt = directory / 'attempt.json'
        need(not attempt.exists() and not attempt.is_symlink(), 'prior cancellation attempt: read actual effect, never replay')
        # Revalidate provider values at the last safe boundary, beyond stored native.
        base = 'repos/' + ctx['repository'] + '/actions/runs/' + str(proof['old_run'])
        run = _read_api(ctx, 'GET', base)
        jobs = _read_api(ctx, 'GET', base + '/jobs?per_page=100')
        reviews = _read_api(ctx, 'GET', base + '/approvals')
        need(run.get('status') == 'waiting' and run.get('run_attempt') == 1
             and run.get('head_sha') == proof['main'] and run.get('conclusion') is None
             and reviews == [] and jobs.get('total_count') == len(jobs.get('jobs', [])),
             'actual unchanged unreviewed run before cancellation')
        release = [j for j in jobs['jobs'] if j.get('name') == 'release']
        need(len(release) == 1 and release[0].get('status') == 'waiting'
             and release[0].get('steps') == [], 'release still unstarted')
        api = carrier.GitHub(ctx)
        carrier.platform_facts(api, ctx, proof['old_run'], fresh, pending=True)
        bindings = carrier.levels(api, ctx)
        need(all(not any(e.get('approvalId') == proof['old_reference']
                         or str(e.get('runId')) == str(proof['old_run'])
                         for e in level['entries']) for level in bindings.values()),
             'fresh provider bindings still absent before cancellation')
        web.intent(root, fresh)
        directory.mkdir(parents=True, exist_ok=True)
        value = {**proof, 'policy_decision_id': policies[0]['decision_id'], 'request': item['request'],
                 'observed_at': now().isoformat(), 'state': 'CANCEL_INTENT_DURABLE_NO_REPLAY'}
        if continuation_path:value['fresh_continuation']=w.file_digest(root,continuation_path)
        # Exclusive create prevents even accidental overwrite of an unknown attempt.
        with attempt.open('x') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.flush(); os.fsync(stream.fileno())
        # Persist both directory entries before any provider call; if this
        # fails, the retained attempt prevents a blind retry.
        for folder in (directory, directory.parent):
            descriptor=os.open(folder,os.O_RDONLY | os.O_DIRECTORY)
            try:os.fsync(descriptor)
            finally:os.close(descriptor)
        try:
            _read_api(ctx, 'POST', base + '/cancel')
            result = {**value, 'state': 'CANCEL_REQUEST_ACCEPTED_TERMINAL_NOT_YET_PROVEN'}
        except (Exception,):
            w.atomic_write_json(directory / 'response.json', {**value, 'state': 'CANCEL_EFFECT_UNKNOWN_READBACK_REQUIRED'})
            raise
        w.atomic_write_json(directory / 'response.json', result)
    return result


def terminal_readback(root, task, state_path):
    import professional_web_execution as web
    state = a.document(root, w.file_digest(root, state_path))
    ctx = web.execution_context(root, task, state)
    need(ctx.get('r3_cancel_run_id') and Path.cwd().resolve() == Path(ctx['worktree']).resolve(),
         'original cancellation executor and worktree')
    web.candidate(ctx, state); web.working_source(ctx, state['candidate_commit'])
    web.approved_ads_git_facts(root, ctx, state, 'r3_cancel')
    web.approved_ads_ci_facts(root, ctx, state)
    zero = validate_zero(root, ctx, state, terminal=True)
    directory = cancellation_directory(root, ctx)
    attempt = w.read_json(directory / 'attempt.json')
    need(isinstance(attempt, dict) and attempt.get('state') == 'CANCEL_INTENT_DURABLE_NO_REPLAY'
         and all(attempt.get(k) == zero[k] for k in ('old_reference', 'old_run', 'main', 'candidate',
                                                     'old_dispatch_decision', 'old_dispatch_key')),
         'actual durable original cancellation attempt')
    policies = [p for p in w.read_jsonl(Path(root) / w.POLICY_DECISIONS)
                if p.get('decision_id') == attempt.get('policy_decision_id')]
    need(len(policies) == 1 and policies[0].get('status') == 'allow'
         and policies[0].get('actual_action_allowed') is True
         and policies[0].get('task_id') == task and policies[0].get('department') == ctx['role']
         and policies[0].get('exact_request') == attempt.get('request'),
         'actual original single-use cancellation policy')
    value = {**zero, 'schema': 'original-WEB-R3-zero-cancel-terminal/v1', 'task_id': task,
             'department': ctx['role'], 'policy_decision_id': policies[0]['decision_id'],
             'cancellation_attempt': w.file_digest(root, str((directory / 'attempt.json').relative_to(root))),
             'observed_at': now().isoformat(), 'cancelled_zero_release_steps': True,
             'proof_state': w.file_digest(root, state_path)}
    target = directory / 'terminal.json'
    if target.exists():
        old = w.read_json(target)
        need(all(old.get(k) == value[k] for k in ('old_reference', 'old_run', 'main', 'candidate',
                                                  'policy_decision_id', 'cancellation_attempt')),
             'preserve original terminal receipt')
    else:
        w.atomic_write_json(target, value)
    return {**value, 'terminal_receipt': w.file_digest(root, str(target.relative_to(root))),
            'new_dispatch_or_reference_issued': False}


def _terminal_source(root, ctx, document, registered_at=None, authenticate_current=False):
    """Authenticate historical cancellation, never use it as current provider facts."""
    import professional_web_execution as web
    import goal_delivery_runtime as g
    chained=document.get('schema')==CHAIN_SCHEMA
    expected={'schema','task_id','terminal_native','terminal_command'} | ({'parent_source'} if chained else set())
    need(set(document)==expected and document['schema'] in (SCHEMA,CHAIN_SCHEMA) and document['task_id']==ctx['task'],
         'exact immutable replacement source shape')
    raw = web.native(root, ctx, document['terminal_native'], document['terminal_command'])
    output = json.loads(raw)
    need(output.get('schema') == 'original-WEB-R3-zero-cancel-terminal/v1'
         and output.get('task_id') == ctx['task'] and output.get('department') == ctx['role']
         and output.get('terminal') is True and output.get('cancelled_zero_release_steps') is True
         and output.get('new_dispatch_or_reference_issued') is False,
         'actual normal original terminal readback')
    page = g._native_document(root, document['terminal_native'])
    pairs = [(t,m) for t in page.get('turns',[]) for m in t.get('items',[])
             if m.get('id') == document['terminal_command']]
    need(len(pairs) == 1, 'one original completed readback command')
    turn, command = pairs[0]
    if authenticate_current or registered_at is not None:
        actual=official_web_turn(root,ctx['binding'],turn['id'],_registration_event_time=registered_at)
        items=[m for m in actual.get('items',[]) if m.get('id')==command.get('id')]
        need(len(items)==1 and all(command.get(k)==items[0].get(k) for k in
             ('id','type','status','exitCode','cwd','command'))
             and w._completion_execution_output(command).decode()==items[0].get('aggregatedOutput')
             and type(items[0].get('completedAtMs')) is int,
             'actual official terminal command and complete output required')
        finished_at=items[0]['completedAtMs']/1000
    else:
        finished_at=None
    argv = shlex.split(command['command'])
    if len(argv) == 3 and argv[0] in ('/bin/zsh','/bin/bash') and argv[1] in ('-lc','-c'):
        argv = shlex.split(argv[2])
    allowed_env = {'PYTHONDONTWRITEBYTECODE':'1', 'PYTHONPATH':str(root)+':'+str(Path(root)/'tools')}
    while argv and '=' in argv[0]:
        key,value = argv.pop(0).split('=',1)
        need(allowed_env.get(key)==value, 'exact original readback runtime')
    need(argv and Path(argv.pop(0)).resolve()==Path(sys.executable).resolve(), 'same trusted Python readback interpreter')
    if argv and argv[0]=='-B': argv.pop(0)
    state_pin = web.code_pin(root, output.get('proof_state'))
    need(len(argv)==6 and argv[:5]==[str(Path(root)/'tools/r3_known_zero_recovery.py'),
          'readback','--task-id',ctx['task'],'--state']
         and w.safe_path(root,argv[5])==w.safe_path(root,state_pin['path']),
         'only exact normal cancellation readback command')
    parent_ctx, row, _, dispatch = base_context(root, ctx, output.get('old_reference'))
    parent=parent_ctx.get('r3_replacement_source')
    need((not chained and parent is None) or (chained and document.get('parent_source')==parent and parent is not None
         and output.get('parent_replacement_source')==parent and output.get('carrier_effect')=='UNKNOWN_PRESERVED_NOT_A_ZERO_API_CLAIM'),
         'exact registered parent and preserved unknown carrier lineage')
    binding = row['platform_binding']; rid = int(binding['runId'])
    need(output.get('old_run')==rid and output.get('main')==binding['expectedSha']
         and output.get('candidate')==ctx['commit']
         and output.get('old_dispatch_decision')==dispatch['decision_id']
         and output.get('old_dispatch_key')==dispatch['autonomous_action_key'],
         'exact original expired reference and spent dispatch chain')
    receipt_pin = web.code_pin(root, output.get('terminal_receipt'))
    expected = Path(root)/'backups'/ctx['task']/'R3-known-zero-cancel'/str(rid)/'terminal.json'
    need(w.safe_path(root,receipt_pin['path']) == expected, 'actual canonical terminal receipt')
    receipt = a.document(root,receipt_pin)
    fields = ('schema','task_id','department','old_reference','old_run','main','candidate',
              'old_dispatch_decision','old_dispatch_key','policy_decision_id',
              'cancellation_attempt','cancelled_zero_release_steps','terminal','observed_at','proof_state')
    if chained:fields=fields+('parent_replacement_source','carrier_effect','carrier_unknown_evidence')
    need(all(receipt.get(k)==output.get(k) for k in fields), 'unchanged real terminal receipt')
    attempt = a.document(root,web.code_pin(root,output['cancellation_attempt']))
    need(attempt.get('state')=='CANCEL_INTENT_DURABLE_NO_REPLAY'
         and attempt.get('policy_decision_id')==output['policy_decision_id']
         and all(attempt.get(k)==output.get(k) for k in ('old_reference','old_run','main','candidate','old_dispatch_decision','old_dispatch_key'))
         and (not chained or (attempt.get('parent_replacement_source')==parent
              and attempt.get('carrier_effect')=='UNKNOWN_PRESERVED_NOT_A_ZERO_API_CLAIM'
              and attempt.get('carrier_unknown_evidence')==output.get('carrier_unknown_evidence'))),
         'original durable cancel attempt binds exact run and provenance')
    policies = [p for p in w.read_jsonl(Path(root)/w.POLICY_DECISIONS)
                if p.get('decision_id')==output['policy_decision_id']]
    need(len(policies)==1 and policies[0].get('status')=='allow'
         and policies[0].get('actual_action_allowed') is True
         and policies[0].get('task_id')==ctx['task'] and policies[0].get('department')==ctx['role']
         and policies[0].get('exact_request')==attempt.get('request'), 'real single-use cancellation policy')
    cancel_request = a.document(root,policies[0]['exact_request'])
    preflight_pin=web.code_pin(root,policies[0].get('source_preflight'))
    preflight=a.document(root,preflight_pin)
    matches=[e for e in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS,where={'task_id':ctx['execution_stage_id']})
             if e.get('task_id')==ctx['execution_stage_id']
             and e.get('details',{}).get('professional_WEB_preflight',{}).get('input')==preflight_pin
             and e.get('details',{}).get('professional_WEB_preflight',{}).get('request')==policies[0]['exact_request']
             and e.get('details',{}).get('professional_WEB_preflight',{}).get('action_id')==cancel_request.get('action_id')]
    need(preflight.get('schema')=='professional-external-WEB-fresh-preflight/v1'
         and preflight.get('task_id')==ctx['task'] and preflight.get('request')==policies[0]['exact_request']
         and len(matches)==1, 'one original committed matching cancellation preflight')
    key=w.sha256_value([ctx['task'],ctx['role'],cancel_request.get('action_id'),cancel_request.get('action_class'),cancel_request.get('scope')])
    need(cancel_request.get('operation')=='r3_cancel' and cancel_request.get('task_id')==ctx['task']
         and cancel_request.get('department')==ctx['role'] and cancel_request.get('action_class')=='site_ci_prepare'
         and cancel_request.get('scope')==ctx['edge_scope'] and policies[0].get('action_id')==cancel_request.get('action_id')
         and policies[0].get('action_class')==cancel_request.get('action_class') and policies[0].get('scope')==cancel_request.get('scope')
         and policies[0].get('autonomous_action_key')==key and policies[0].get('consume_approval') is True
         and policies[0].get('approval_status')=='consumed_for_original_exact_autonomous_action'
         and policies[0].get('payload_sha256')==policies[0]['exact_request']['sha256']
         and cancel_request.get('desired',{}).get('run_id')==rid
         and cancel_request.get('desired',{}).get('old_reference')==binding['approvalId'],
         'policy was consumed for this exact cancellation request, scope and actor')
    if chained:
        evidence=output.get('carrier_unknown_evidence');need(isinstance(evidence,dict) and set(evidence)=={'native','command_id','files'}, 'original unknown evidence pins required')
        nativeproof={'carrier_native':evidence['native'],'carrier_command':evidence['command_id']}
        need(authenticate_isolated_unknown(root,ctx,binding['approvalId'],nativeproof,binding)==evidence,
             'immutable original carrier history and real native required')
        cancel_ctx={**ctx,'prefix':ctx['prefix']+'-cancel-run-'+str(rid)}
        cancel_state=cancel_request.get('state',{})
        need(cancel_state.get('r3_replacement_source')==parent
             and cancel_state.get('r3_cancel',{}).get('approval_id')==binding['approvalId']
             and cancel_request.get('action_id')==web.action_id(cancel_ctx,'r3_cancel',ctx['commit'],binding['expectedSha']),
             'one normal parent-bound cancellation action, never a caller-supplied source or key')
    observed = w._parse_observed_at(output.get('observed_at'))
    recorded = w._parse_observed_at(registered_at) if registered_at else now()
    need(observed and recorded and turn['startedAt']<=observed.timestamp()
         and (finished_at is None or observed.timestamp()<=finished_at<=recorded.timestamp())
         and 0 <= (recorded-observed).total_seconds() <= 300 and recorded<=now(),
         'source was registered from a fresh real completed readback; no future or fabricated time')
    result={'old_reference':binding['approvalId'],'old_run':rid,'main':binding['expectedSha'],
            'candidate':ctx['commit'],'cancel_policy':policies[0]['decision_id'],
            'terminal_receipt':receipt_pin,'terminal_observed_at':output['observed_at'],'terminal_turn_id':turn['id']}
    if chained:result.update(parent_replacement_source=parent,carrier_effect='UNKNOWN_PRESERVED_NOT_A_ZERO_API_CLAIM',carrier_unknown_evidence=output['carrier_unknown_evidence'])
    return result


def record_replacement(root, task, input_path):
    import professional_web_execution as web
    import goal_delivery_runtime as g
    pin = web.code_pin(root,w.file_digest(root,input_path))
    source = a.document(root,pin)
    # The fixed terminal proof yields the original candidate state; no caller
    # source selector or fabricated future run ID is accepted here.
    records = web.records(root,task)
    need(len(records)==1 and records[0].get('approved_ads_source_discovery_only'), 'one original business source')
    from approved_ads_web_source import successor_records
    successors=successor_records(root,records[0]);need(len(successors)==1,'one original actual test successor')
    ctx=web.execution_context(root,task,{'candidate_commit':successors[0]['commit']})
    need(Path.cwd().resolve()==Path(ctx['worktree']).resolve(),'source registration by original WEB only')
    effect=_terminal_source(root,ctx,source,authenticate_current=True)
    with w.workflow_lock(root):
        registered=now().isoformat()
        observed=w._parse_observed_at(effect['terminal_observed_at'])
        need(observed and 0 <= (now()-observed).total_seconds() <= 300,
             'terminal evidence must remain fresh at source commit')
        need(web.code_pin(root,w.file_digest(root,input_path))==pin, 'source unchanged at commit')
        context=w._VALIDATION_CONTEXT.get()
        if context:context.recheck()
        events=[e for e in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS)
                if e.get('details',{}).get(EVENT,{}).get('original_source')==ctx['registration']]
        need(len(events)<=2,'bounded non-forking original recovery chain only')
        duplicates=[e for e in events if e['details'][EVENT].get('source')==pin]
        if duplicates:
            need(len(duplicates)==1,'one immutable original replacement identity')
            return {'state':'DUPLICATE_SOURCE_NO_NEW_AUTHORITY','source':pin,'event_id':duplicates[0]['event_id']}
        if not events:
            need(source.get('schema')==SCHEMA,'first replacement requires original source')
        else:
            need(len(events)==1 and source.get('schema')==CHAIN_SCHEMA
                 and source.get('parent_source')==events[0]['details'][EVENT].get('source')
                 and effect.get('parent_replacement_source')==source['parent_source']
                 and effect.get('old_run')!=events[0]['details'][EVENT].get('old_run'),
                 'one actual distinct child of current original recovery; no fork or third recovery')
        snapshot=g.restore_goal(root,w.read_json(w.snapshot_path(root,ctx['execution_stage_id'])))
        need(snapshot['current_state'] not in w.TERMINAL_STATES
             and not w.validate_workflow_events(root,ctx['execution_stage_id']), 'active intact original stage')
        registered=now().isoformat()
        need(0 <= (now()-observed).total_seconds() <= 300, 'terminal evidence fresh immediately before append')
        if context:context.recheck()
        need(0 <= (now()-observed).total_seconds() <= 300, 'terminal evidence fresh after dependency recheck')
        # Re-read latest official same-turn project observation at the locked
        # commit boundary; validation work must not consume its freshness.
        official_web_turn(root,ctx['binding'],effect['terminal_turn_id'])
        need(0 <= (now()-observed).total_seconds() <= 300, 'terminal evidence fresh at actual append')
        registered=now().isoformat()
        event=w.append_workflow_event(root,ctx['execution_stage_id'],snapshot['current_state'],
              {EVENT:{'source':pin,'original_source':ctx['registration'],'registered_at':registered,**effect}})
    return {'state':'EXACT_ZERO_REPLACEMENT_SOURCE_RECORDED_NO_PERMISSION','source':pin,
            'event_id':event['event_id'],'platform_write':False,'new_reference_issued':False}


def select_replacement(root, ctx, state):
    pin=state.get('r3_replacement_source')
    if pin is None:return ctx
    import professional_web_execution as web
    need('r3_cancel' not in state and ctx.get('approved_ads_test_successor'), 'distinct replacement stage only')
    pin=web.code_pin(root,pin)
    need(not w.validate_workflow_events(root,ctx['execution_stage_id']), 'intact original workflow history required')
    events=[e for e in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS)
            if e.get('details',{}).get(EVENT,{}).get('original_source')==ctx['registration']]
    need(1<=len(events)<=2 and all(e.get('task_id')==ctx['execution_stage_id'] for e in events),
         'bounded registered original recovery chain')
    if len(events)==2:
        first=events[0]['details'][EVENT];second=events[1]['details'][EVENT]
        need(second.get('parent_replacement_source')==first.get('source')
             and second.get('carrier_effect')=='UNKNOWN_PRESERVED_NOT_A_ZERO_API_CLAIM'
             and second.get('old_run')!=first.get('old_run'), 'one linear no-fork preserved-unknown successor')
    matches=[e for e in events if e['details'][EVENT].get('source')==pin]
    need(len(matches)==1, 'one exact registered source pin, never caller waiver')
    selected=matches[0];entry=selected['details'][EVENT]
    event_time=w._parse_observed_at(selected.get('created_at'))
    registered=w._parse_observed_at(entry.get('registered_at'))
    need(event_time and registered and event_time<=now() and registered<=now()
         and abs((registered-event_time).total_seconds()) < 2,
         'original committed event binds actual registration time')
    effect=_terminal_source(root,ctx,a.document(root,pin),entry['registered_at'])
    need(all(entry.get(k)==v for k,v in effect.items())
         and state.get('main_sha')==effect['main'] and state.get('candidate_commit')==effect['candidate'],
         'same actual main/candidate and immutable cancelled-run lineage')
    return {**ctx,'r3_replacement_source':pin,'r3_replacement_old_run':effect['old_run'],
            'r3_replacement_old_reference':effect['old_reference'],
            'prefix':ctx['prefix']+'-r3r-'+pin['sha256'][:16]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['cancel', 'readback', 'record-replacement-source'])
    parser.add_argument('--task-id', required=True)
    parser.add_argument('--request')
    parser.add_argument('--state')
    parser.add_argument('--input')
    parser.add_argument('--continuation')
    args = parser.parse_args(); root = Path(__file__).resolve().parents[1]
    with w.request_validation_context():
        if args.command == 'cancel':
            need(args.request, 'exact request path required')
            value = cancel(root, args.task_id, args.request,args.continuation)
        elif args.command == 'readback':
            need(args.state, 'actual fresh terminal state required')
            value = terminal_readback(root, args.task_id, args.state)
        else:
            need(args.input, 'exact actual replacement source input required')
            value = record_replacement(root,args.task_id,args.input)
    print(json.dumps(value, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
