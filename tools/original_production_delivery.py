"""Read an explicit original production contract and its genuine WEB delivery.

The two existing source event kinds are retained. This codec creates no account,
role, approval, runtime readiness or permit and never changes the frozen goal.
"""
from pathlib import Path
import datetime as dt
import hashlib
import json
import re
import subprocess
import tempfile
import workflow_control as w
import department_autonomy as a

SCHEMA = 'original-explicit-production-delivery-source/v1'


def need(value, message):
    a.require(value, 'original production source: ' + message)


def _pin_equal(left, right):
    return isinstance(left, dict) and isinstance(right, dict) and all(left.get(k) == right.get(k) for k in ('sha256', 'size'))


def contexts(root, snapshot, item):
    import goal_delivery_runtime as g
    import professional_web_execution as web
    from professional_cms_issuer import external
    goal = a.participant(root, snapshot, snapshot['goal_delivery']['primary_owner'])
    frozen = a.document(root, snapshot['goal_contract']); owner = frozen['primary_owner']
    need(item.get('schema') == SCHEMA and item.get('task_id') == snapshot['task_id']
         and item.get('goal_contract') == snapshot['goal_contract'] and item.get('authorization') == goal['authorization_pin']
         and all(goal.get(k) == frozen.get(k) for k in ('primary_owner', 'producer_departments', 'authorized_scope',
                    'human_authorization', 'required_execution_actions', 'collaboration_scopes'))
         and frozen.get('production_write_allowed') is True and frozen.get('completion_kind') == 'production_release'
         and frozen.get('execution_mode') == 'authorized_selfcheck_then_execute',
         'unchanged open explicit production contract, participants and original human authorization')
    human = a.document(root, item['authorization']); original_human = frozen['human_authorization']
    need(human.get('source_thread_id') == original_human.get('source_thread_id')
         and human.get('message', {}).get('id') == original_human.get('message_id')
         and human['message'].get('type') == 'userMessage' and human['message'].get('content')
         and original_human.get('executor') == owner, 'actual original human message, not a new helper approval')
    selection = a.document(root, item['owner_selection']); scope = item.get('business_scope')
    need(selection.get('task_id') == snapshot['task_id'] and selection.get('scope') == scope
         and selection.get('professional_owner') == owner and scope in frozen['authorized_scope']
         and selection.get('authority', {}).get('original_full_goal') == item['goal_contract']
         and selection.get('authority', {}).get('original_human') == item['authorization'],
         'same original professional selection and immutable business authority')
    role = item.get('WEB_role'); binding = g._collaboration_binding(root, snapshot, role)
    need(binding and binding['project_id'] != a.PROJECT and role not in goal['producer_departments']
         and {'sender_department': owner, 'target_department': role, 'scope': scope} in frozen['collaboration_scopes'],
         'original declared external source executor; never a new internal department')
    states = [s for s in g._collaboration_wait_states(root, snapshot, only_action_id=item.get('original_WEB_action'))
              if s.get('department') == role and s.get('status') == 'result_received' and s.get('proof_state') == 'PROVEN'
              and s.get('result') == item.get('received_WEB_result')]
    need(len(states) == 1, 'one genuinely received completed original WEB result')
    report = a.document(root, item['received_WEB_result']); original_pin = item.get('WEB_report_original')
    need(_pin_equal(original_pin, item['received_WEB_result']) and external(root, original_pin, binding) == report
         and report.get('task_id') == snapshot['task_id'] and report.get('scope') == scope
         and report.get('action_id') == item['original_WEB_action'] and report.get('producer_thread') == binding['thread_id'],
         'exact original external report bytes and owner custody')
    native = g._native_document(root, item['WEB_completed_native'])
    need(all(native.get('thread', {}).get(k) == binding[v] for k, v in
             {'id': 'thread_id', 'title': 'title', 'cwd': 'cwd'}.items()), 'original fixed WEB identity')
    old_native = g._native_document(root, states[0]['native_result'])
    finals = [(t, m) for t in old_native.get('turns', []) for m in t.get('items', [])
              if m.get('type') == 'agentMessage' and m.get('phase') == 'final_answer']
    calls = [(t, m) for t in native.get('turns', []) for m in t.get('items', []) if m.get('id') == item.get('WEB_source_command')]
    need(len(calls) == len(finals) == 1, 'one exact successful source command and normal completed final')
    turn, command = calls[0]; original_turn, final = finals[0]
    made = w._parse_observed_at(report.get('produced_at'))
    need(turn.get('id') == original_turn.get('id') and turn.get('status') == original_turn.get('status') == 'completed'
         and not turn.get('error') and final in turn.get('items', []) and command.get('type') == 'commandExecution'
         and command.get('status') == 'completed' and command.get('exitCode') == 0
         and Path(command.get('cwd', '')).resolve().is_relative_to(Path(binding['cwd']).resolve())
         and made is not None and type(turn.get('startedAt')) in {int, float}
         and type(turn.get('completedAt')) in {int, float}
         and turn['startedAt'] <= made.timestamp() <= turn['completedAt'] <= dt.datetime.now(dt.timezone.utc).timestamp()
         and json.loads(w._completion_execution_output(command)).get('report') == original_pin,
         'real ordered completed native output must emit the exact selected report')
    # The selected report retains its old delivery; neither original is edited.
    previous = external(root, report['original_v1_report'], binding)
    need(previous.get('task_id') == snapshot['task_id'] and previous.get('scope') == scope
         and previous.get('producer') == role and previous.get('producer_thread') == binding['thread_id'],
         'same original delivery lineage')
    ui = report['selected_UI']; title = report['unchanged_title_channel']
    requested = next((x for x in selection['needed_maintenance'] if x.get('id') == 'WEB-original-production-source'), {})
    need(ui.get('head') == requested.get('selected_UI_candidate', {}).get('head')
         and title == previous.get('title_channel_local_candidate')
         and title.get('head') == requested.get('original_title_candidate', {}).get('head'),
         'only the actual owner-selected sibling sources, not the superseded UI')
    components = []; paths = {}
    for kind, meta in (('UI', ui), ('channel', title)):
        worktree = Path(meta['worktree']).resolve()
        need(worktree.is_relative_to(Path(binding['cwd']).resolve()), 'original website worktree only')
        head = meta['head']; base = meta.get('candidate_base', meta['parent'])
        ctx = {'worktree': str(worktree)}
        need(web.git(ctx, 'show', '-s', '--format=%H %P %T', head).decode().strip() == ' '.join([head, meta['parent'], meta['tree']]),
             'actual immutable Git head/parent/tree')
        files = meta['files']; names = meta.get('cumulative_paths', meta.get('paths'))
        mapped = {f['repo_path']: f.get('immutable_archive', f) for f in files}
        need(len(mapped) == len(files) and set(names) == set(mapped)
             and set(web.git(ctx, 'diff', '--name-only', base, head).decode().splitlines()) == set(mapped)
             and not (set(paths) & set(mapped)), 'complete disjoint original sibling file sets; overlap requires its own real delta')
        for name, pin in mapped.items():
            need(not Path(name).is_absolute() and '..' not in Path(name).parts
                 and hashlib.sha256(web.git(ctx, 'show', head + ':' + name)).hexdigest() == pin['sha256']
                 and len(web.git(ctx, 'show', head + ':' + name)) == pin['size'], 'exact source blob/hash/size')
            paths[name] = pin['sha256']
        if kind == 'UI':
            patches = [p for p in report.get('source_forward_inverse_rehearsals', [])
                       if p.get('from_commit') == base and p.get('to_commit') == head and p.get('scope') == 'cumulative']
            need(len(patches) == 1, 'one exact actual cumulative source patch pair')
            forward, inverse = patches[0]['forward'], patches[0]['inverse_own_source_only']
        else:
            forward, inverse = meta['forward'], meta['inverse']
        delta = web._patch_effect(web._delta({'worktree': str(worktree), 'paths': mapped}, base, head))
        need(web._patch_effect(web._patch_delta(web._external_bytes(forward, binding))) == delta
             and web._patch_effect(web._patch_delta(web._external_bytes(inverse, binding))) == {p: (added, removed) for p, (removed, added) in delta.items()},
             'actual original forward and reverse source effects, not a restore claim')
        components.append({'head': head, 'base': base, 'parent': meta['parent'], 'tree': meta['tree'],
                           'worktree': str(worktree), 'paths': {n: paths[n] for n in mapped}, 'forward': forward, 'inverse': inverse})
    need(len(paths) <= 40 and components[0]['base'] == components[1]['base'], 'bounded same-base sibling integration')
    # Only the exact cms_pages title codec is added. No legacy table/sections alias.
    frozen_pin = item['frozen_CMS_target']; cms_frozen = a.document(root, frozen_pin)
    source_rel = item['frozen_CMS_repo_path']
    raw = web.git({'worktree': title['worktree']}, 'show', title['head'] + ':' + source_rel)
    need(raw == w.safe_path(root, frozen_pin['path']).read_bytes() and source_rel in components[1]['paths']
         and cms_frozen.get('task_id') == snapshot['task_id'] and cms_frozen.get('business_scope') == scope
         and cms_frozen.get('owner') == owner and cms_frozen.get('code_executor') == role
         and cms_frozen.get('registration_grants_write_authority') is False, 'actual frozen target belongs to this exact code source/owner')
    target = cms_frozen['runtime_target']; before = cms_frozen['before']; desired = cms_frozen['desired']; forward = cms_frozen['forward_tuple']
    fields = target['changedFields']; executor = cms_frozen['execution_department']
    declared = [x for x in frozen['required_execution_actions'] if x.get('action_id') == target.get('actionId')]
    need(len(declared) == 1 and declared[0] == {'action_id': target['actionId'], 'action_class': 'cms_write', 'scope': scope, 'department': executor}
         and executor in goal['producer_departments'] and a.professional(root, executor)
         and target.get('taskId') == snapshot['task_id'] and target.get('table') == 'cms_pages'
         and target.get('contentType') == 'site_page' and fields == ['title_zh', 'title_en', 'title_ms']
         and set(desired) == set(fields) and len(before) == 24 and set(before) == set(target['baselineProjectionFields'])
         and type(before.get('version')) is int and isinstance(before.get('updated_at'), str)
         and target.get('id') == before.get('id') and target.get('slug') == before.get('page_key'),
         'original explicit CMS action/executor and full24 title-only row codec')
    physical = 'company.example:cms_pages:' + before['id'] + ':' + ','.join(fields)
    retained = sorted(set(before) - set(fields) - {'updated_at', 'version'})
    need(target['scope'] == physical and len(retained) == 19 and target['retainedProjectionFields'] == retained
         and target['baselineFieldsSha256'] == w.sha256_value(before)
         and target['desiredFieldsSha256'] == w.sha256_value(desired)
         and target['rollbackFieldsSha256'] == w.sha256_value({k: before[k] for k in fields})
         and target['retainedFieldsSha256'] == w.sha256_value({k: before[k] for k in retained})
         and target['expectedUpdatedAt'] == before['updated_at']
         and target.get('rollbackAllowed') is True and target.get('requiresParentRun') is True,
         'both original business and physical scopes, exact field digests and conditional inverse')
    need(forward == {'task_id': snapshot['task_id'], 'action_id': target['actionId'], 'scope': physical,
                    'candidate_version': target['candidateVersion'], 'table': 'cms_pages', 'record_id': before['id'], 'fields': fields, 'operation': 'publish'},
         'unchanged exact frozen forward tuple')
    reverse = cms_frozen['conditional_inverse']
    need(reverse == {'action_id': 'rollback-' + target['candidateVersion'], 'candidate_version': target['candidateVersion'] + '-rollback-v1',
                     'requiresParentRun': True, 'parentPermitId': None, 'parentRunId': None, 'postSaveCAS': None, 'future_values_not_filled': True},
         'own completed-parent inverse only; no fabricated future CAS/run/permit')
    # The owner source is already referenced in the genuine WEB delivery.
    own = [p for p in cms_frozen['source_pins'] if (Path(root)/p['path']).resolve().is_relative_to(Path(root).resolve())]
    need(len(own) == 1, 'one original owner business source, never a different CMS batch')
    original_owner_source = a.document(root, {**own[0], 'path': str((Path(root)/own[0]['path']).resolve().relative_to(Path(root).resolve()))})
    expected = {('title_' + x['language']): x['original_approved_after'] for x in original_owner_source['Contact_original_nine_obligations'] if x['slot'] == 'title'}
    need(original_owner_source.get('task_id') == snapshot['task_id'] and original_owner_source.get('scope') == scope
         and original_owner_source.get('department') == owner and desired == expected,
         'exact existing approved trilingual title values from original professional source')
    baseline = a.document(root, item['baseline']); need(baseline == before, 'exact baseline custody, not an execution-time CAS claim')
    cmsctx = {'action': {'task_id': snapshot['task_id'], 'action_id': target['actionId'], 'action_class': 'cms_write',
                         'scope': physical, 'business_scope': scope, 'candidate_version': target['candidateVersion'],
                         'table': 'cms_pages', 'record_id': before['id'], 'slug': before['page_key'], 'changed_fields': fields, 'execution_department': executor},
              'source': frozen_pin, 'baseline_pin': item['baseline'], 'owner': owner, 'business_scope': scope, 'executor': executor,
              'channel': role, 'carrier': item['owner_selection'], 'desired': desired, 'before': {k: before[k] for k in fields},
              'protected_fields': {'not_written_fields': sorted(set(before)-set(fields)), 'server_CAS_metadata': ['updated_at', 'version'],
                                   'stable_business_readback_fields': retained},
              'owner_result': item['owner_selection'], 'original_explicit_delivery': True, 'physical_target': target}
    account = a.document(root, item['account_source']); repo = web.git({'worktree': title['worktree']}, 'config', '--get', 'remote.origin.url').decode().strip()
    name = account.get('full_name'); actor = account.get('authenticated_actor', {})
    need(isinstance(name, str) and repo in {'user-3de132cd98be@example.invalid:' + name + '.git', 'https://github.com/' + name, 'https://github.com/' + name + '.git'}
         and type(account.get('id')) is int and type(actor.get('id')) is int and actor['id'] > 0
         and actor.get('login') == name.split('/')[0], 'actual existing repository/actor; no identity default')
    # Account facts are transport identity only, not authority borrowed from another task.
    account_native = g._native_document(root, item['account_native']); account_calls = [(t, c) for t in account_native.get('turns', [])
                     for c in t.get('items', []) if c.get('id') == item.get('account_command')]
    need(len(account_calls) == 1 and account_native.get('thread', {}).get('id') == binding['thread_id'], 'genuine same external identity readback')
    at, ac = account_calls[0]
    account_outputs = []
    for line in w._completion_execution_output(ac).decode('utf-8').splitlines():
        try: value = json.loads(line)
        except ValueError: continue
        if isinstance(value, dict): account_outputs.append(value)
    need(at.get('status') == 'completed' and at.get('id') == turn.get('id') and not at.get('error')
         and ac.get('type') == 'commandExecution' and ac.get('status') == 'completed' and ac.get('exitCode') == 0
         and Path(ac.get('cwd', '')).resolve().is_relative_to(Path(binding['cwd']).resolve())
         and account_outputs == [account],
         'complete original native account data, never a caller principal')
    recovery = a.document(root, item['rollback_runbook'])
    need(recovery.get('task_id') == snapshot['task_id'] and recovery.get('goal_contract') == snapshot['goal_contract']
         and recovery.get('source_components') == components and recovery.get('unknown_effect_replay_allowed') is False
         and recovery.get('CMS_inverse_requires_own_completed_parent') is True, 'task-bound executable recovery plan and authentic source components')
    backup = a.document(root, item['source_backup'])
    need(backup.get('task_id') == snapshot['task_id'] and backup.get('source_components') == components
         and backup.get('actual_platform_backup_or_restore_proven') is False,
         'exact original source backup recipe; actual platform backup remains an execution-time fact')
    from managed_cms_permit_issuer import SUPABASE_HOST
    project_ref = SUPABASE_HOST.split('.')[0]
    ctx = {'root': str(Path(root).resolve()), 'task': snapshot['task_id'], 'scope': scope, 'owner': owner, 'role': role,
           'binding': binding, 'decision': item['owner_selection'], 'authorization': item['authorization'], 'contract': snapshot['goal_contract'],
           'worktree': title['worktree'], 'site': str(Path(title['worktree']).resolve().parent.parent), 'branch': title['branch'],
           'commit': title['head'], 'base': title['parent'], 'tree': title['tree'], 'paths': paths, 'source_components': components,
           'backup': item['source_backup'], 'rollback': item['rollback_runbook'], 'registered_CMS': cmsctx,
           'repository': name, 'repository_id': account['id'], 'actor_id': actor['id'],
           'original_production_channel': True, 'prefix': snapshot['task_id'] + '-original-channel',
           'edge_scope': 'company.example:edge:' + project_ref + ':content-publish',
           'pages_scope': 'company.example:pages:production', 'project_ref': project_ref}
    need(not w.validate_workflow_events(root, snapshot['task_id']), 'intact original append-only history')
    return cmsctx, ctx


def candidate(ctx, state):
    """Only the exact disjoint original contributions on an actual later base."""
    import professional_web_execution as web
    head, base = state.get('candidate_commit'), state.get('candidate_base', ctx['base'])
    mode = state.get('source_mode', 'forward')
    need(re.fullmatch('[0-9a-f]{40}', str(head)) and re.fullmatch('[0-9a-f]{40}', str(base))
         and mode in {'forward', 'remove_own_delta'}
         and web.git(ctx, 'merge-base', ctx['base'], base).decode().strip() == ctx['base']
         and set(web.git(ctx, 'diff', '--name-only', base, head).decode().splitlines()) <= set(ctx['paths']),
         'real same-lineage combined head/base and only original paths')
    if mode == 'remove_own_delta':
        import goal_delivery_runtime as g
        source = ctx['registered_CMS']; pin = state.get('CMS_recovery_source'); proof = a.document(Path(ctx['root']), pin)
        snapshot = g.restore_goal(Path(ctx['root']), w.read_json(w.snapshot_path(Path(ctx['root']), ctx['task'])))
        actual = [s for s in g._collaboration_wait_states(Path(ctx['root']), snapshot)
                  if s.get('department') == source['executor'] and s.get('status') == 'result_received'
                  and s.get('proof_state') == 'PROVEN' and s.get('result') == pin]
        guard = proof.get('CMS_recovery_guard', {})
        need(len(actual) == 1 and guard.get('task_id') == ctx['task']
             and guard.get('forward_action_id') == source['action']['action_id']
             and guard.get('record_id') == source['action']['record_id']
             and (guard.get('state') == 'NO_OWN_SAVE' and guard.get('publish_runs') == [] and guard.get('permits') == []
                  or guard.get('state') == 'OWN_INVERSE_COMPLETED' and all(guard.get(k) for k in
                         ('original_publish_permit_id', 'original_publish_run_id', 'inverse_permit_id', 'inverse_completed_run_id', 'saved_updated_at'))),
             'actual own PUB completed zero-effect or inverse result before removing the protected channel')
    scratch = Path(ctx['root'])/'logs/professional-CMS-channel-source-checks'; scratch.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=scratch) as folder:
        folder = Path(folder)
        for component in ctx['source_components']:
            for path in component['paths']:
                def blob(commit):
                    x = subprocess.run(['git', 'show', commit+':'+path], cwd=ctx['worktree'], capture_output=True)
                    return x.stdout if x.returncode == 0 else b''
                left, right = (component['base'], component['head']) if mode == 'forward' else (component['head'], component['base'])
                for label, commit in [('current', base), ('ancestor', left), ('own', right)]: (folder/label).write_bytes(blob(commit))
                merged = subprocess.run(['git', 'merge-file', '-p', str(folder/'current'), str(folder/'ancestor'), str(folder/'own')], capture_output=True)
                need(merged.returncode == 0 and merged.stdout == blob(head)
                     and web.git(ctx, 'ls-tree', head, '--', path).split()[:1] == web.git(ctx, 'ls-tree', right, '--', path).split()[:1],
                     'each original source contribution and file mode must survive; a genuine overlap needs exact new source')
    return head, base


def record(root, task, path):
    import goal_delivery_runtime as g
    import professional_cms_execution as cms
    import professional_web_execution as web
    pin = w.file_digest(root, path); item = a.document(root, pin)
    with w.workflow_lock(root):
        snapshot = g.restore_goal(root, w.read_json(w.snapshot_path(root, task))); contexts(root, snapshot, item)
        rows = [e for e in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS) if e.get('task_id') == task
                and (cms.EVENT in e.get('details', {}) or web.EVENT in e.get('details', {}))]
        if rows:
            need(len(rows) == 1 and rows[0]['details'].get(cms.EVENT) == rows[0]['details'].get(web.EVENT) == pin,
                 'existing original source effect must be read; never replace or fork')
            return {'result': 'duplicate_ignored', 'source': pin, 'event_id': rows[0]['event_id'], 'external_permission_issued': False}
        event = w.append_workflow_event(root, task, snapshot['current_state'], {cms.EVENT: pin, web.EVENT: pin, 'frozen_contract_unchanged': True})
    return {'result': 'recorded', 'source': pin, 'event_id': event['event_id'], 'external_permission_issued': False,
            'remote_READY': False, 'business_producers_changed': False}
