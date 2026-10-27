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
    if ctx.get('owner_received_code_stage'):
        parents = web.git(ctx, 'show', '-s', '--format=%P', head).decode().split()
        need(len(parents) == 1 and state.get('candidate_parent') == parents[0],
             'true current linear parent is mandatory and never inferred from cumulative base')
    if mode == 'remove_own_delta' and ctx.get('code_only_release'):
        web.validate_code_recovery(ctx, state)
    elif mode == 'remove_own_delta':
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


CODE_SCHEMA = 'original-received-code-only-source/v1'
CODE_EVENT = 'professional_WEB_received_code_only_source'


def code_context(root, snapshot, item):
    """An authenticated professional source stage, separate from existing CMS."""
    import professional_web_execution as web
    import goal_delivery_runtime as g
    import result_coordination as rc
    import xml.etree.ElementTree as ET
    base_sources = web.records(root, snapshot['task_id'])
    need(len(base_sources) == 1 and item.get('schema') == CODE_SCHEMA
         and item.get('task_id') == snapshot['task_id']
         and item.get('original_source_registration') == base_sources[0]['registration'],
         'one original authority lineage; code-only stage never replaces CMS source')
    base = base_sources[0]; owner = base['owner']; binding = base['binding']
    goal = a.participant(root, snapshot, owner); data = a.document(root, item['owner_input'])
    need(data.get('task_id') == snapshot['task_id'] and data.get('scope') == base['scope']
         and data.get('primary_owner') == data.get('department') == owner
         and data.get('original_goal_contract') == snapshot['goal_contract']
         and data.get('original_executor') == data.get('actual_source_producer') == base['role']
         and data.get('actual_source_producer_thread_id') == binding['thread_id']
         and goal['primary_owner'] == owner, 'same frozen task/scope/owner/original external executor')
    # The committed receipt proves custody only; it is not a technical approval.
    decision = a.document(root, item['actual_custody_decision']); identity = rc.exact_identity(decision)
    intake = rc._received_delivery(root, identity, {'target_department': 'operations-assistant'})
    report = a.document(root, decision['outbox'])
    need(intake and intake['record_id'] == decision.get('actual_intake_record_id')
         and identity['task_id'] == snapshot['task_id'] and identity['sender_department'] == owner
         and decision.get('scope') == base['scope'] and report.get('primary_owner') == owner
         and item['owner_input'] in report.get('evidence', []), 'actual same-result SQL/native custody of complete professional input')
    business = a.document(root, data['actual_original_business_input'])
    selection = a.document(root, data['actual_C1_ordinary_compatibility_decision'])
    need(selection.get('task_id') == business.get('task_id') == snapshot['task_id']
         and selection.get('scope') == business.get('scope') == base['scope']
         and selection.get('professional_business_owner') == business.get('primary_owner') == owner
         and selection.get('original_code_executor') == business.get('original_code_executor') == base['role']
         and web.code_same_pin(root, selection['original_exact_input'], data['actual_original_business_input']),
         'actual original professional scope/selection, not a new permission')
    original_pin = data['actual_typed_producer_original']; typed = web.external(root, original_pin, binding)
    need(a.document(root, data['actual_exact_C1_typed_copy']) == typed
         and typed.get('task_id') == snapshot['task_id'] and typed.get('scope') == base['scope']
         and typed.get('producer') == base['role'] and typed.get('producer_thread') == binding['thread_id']
         and typed.get('original_action_id') == data['actual_original_action_id']
         and web.code_same_pin(root, typed['professional_decision'], data['actual_C1_ordinary_compatibility_decision'])
         and web.code_same_pin(root, typed['original_business_input'], data['actual_original_business_input']),
         'unmodified original complete producer report and exact professional custody')
    native = g._native_document(root, item['actual_WEB_native'])
    need(all(native.get('thread', {}).get(k) == binding[v] for k, v in
             {'id':'thread_id','title':'title','cwd':'cwd','hostId':'host_id'}.items()), 'actual original WEB identity/project host')
    matches = [(t,c) for t in native.get('turns', []) for c in t.get('items', []) if c.get('id') == item.get('source_command')]
    need(len(matches) == 1, 'one actual completed source-emitting command')
    turn, command = matches[0]; raw = json.loads(w._completion_execution_output(command))
    finals = [m for m in turn.get('items', []) if m.get('type') == 'agentMessage' and m.get('phase') == 'final_answer']
    source_final = g._native_document(root, data['actual_producer_completed_native'])
    original_turns = [t for t in source_final.get('turns', []) if t.get('id') == turn.get('id')]
    echoes = []
    for m in turn.get('items', []):
        if m.get('type') != 'functionCallOutput': continue
        output = m.get('output', {}); text = output.get('text', '') if isinstance(output, dict) else ''
        try: doc = ET.fromstring(text)
        except ET.ParseError: continue
        payload = doc.findtext('input') or ''
        if (doc.tag == 'codex_delegation' and doc.findtext('source_thread_id') == w.department_registry(root)['operations']['chat_binding']['task_id']
            and all(s in payload for s in (snapshot['task_id'], base['scope'], data['actual_original_action_id'],
                   data['actual_C1_ordinary_compatibility_decision']['sha256']))): echoes.append(m)
    made = w._parse_observed_at(typed.get('produced_at'))
    need(turn.get('status') == 'completed' and not turn.get('error')
         and command.get('type') == 'commandExecution' and command.get('status') == 'completed' and command.get('exitCode') == 0
         and Path(command.get('cwd', '')).resolve().is_relative_to(Path(binding['cwd']).resolve())
         and raw.get('report') == original_pin and len(finals) == len(echoes) == len(original_turns) == 1
         and original_turns[0].get('status') == 'completed' and finals[0] in original_turns[0]['items']
         and turn['items'].index(echoes[0]) < turn['items'].index(command) < turn['items'].index(finals[0])
         and made is not None and turn['startedAt'] <= made.timestamp() <= turn['completedAt'] <= dt.datetime.now(dt.timezone.utc).timestamp()
         and w.safe_path(root, data['actual_final_UTF8']['path']).read_bytes() == finals[0]['text'].encode('utf-8')
         and w.file_digest(root, data['actual_final_UTF8']['path']) == data['actual_final_UTF8'],
         'real ordered original HQ source delivery, successful report command and unchanged completed final')
    meta = typed['actual_candidate']; paths = {x['repo_path']:x['sha256'] for x in typed['current_cumulative_files']}
    need(typed['current_cumulative_files'] == data['actual_cumulative_three_file_map'] and len(paths) == 3
         and all(p.startswith('src/') and '..' not in Path(p).parts and p.endswith(('.ts','.tsx')) for p in paths)
         and all(meta.get(k) == data[v] for k,v in {'head':'actual_final_head','parent':'actual_linear_parent',
             'candidate_base':'actual_candidate_integration_base','tree':'actual_tree','branch':'actual_branch','worktree':'actual_worktree'}.items()),
         'complete bounded source map and true linear parent separate from cumulative base')
    ctx = {**base, 'decision':data['actual_C1_ordinary_compatibility_decision'], 'worktree':meta['worktree'],
           'branch':meta['branch'],'commit':meta['head'],'git_parent':meta['parent'],'base':meta['candidate_base'],
           'tree':meta['tree'],'paths':paths,'code_only_release':True,'allowed_operations':web.CODE_OPS,
           'original_production_channel':True,'owner_received_code_stage':True,
           'prefix':snapshot['task_id']+'-owner-code','backup':item['source_backup'],'rollback':item['source_backup']}
    for key in ('registered_CMS','repair','standing_CMS_channel','standing_authorization_id','authority_department','registered_CMS_sources','CMS_targets','channel_input','WEB_delivery'):
        ctx.pop(key,None)
    ctx['local_source_stage_only']=True
    need(Path(ctx['worktree']).resolve().is_relative_to(Path(binding['cwd']).resolve())
         and web.git(ctx, 'show','-s','--format=%H %P %T',ctx['commit']).decode().strip() == ' '.join([ctx['commit'],ctx['git_parent'],ctx['tree']])
         and web.git(ctx,'merge-base',ctx['base'],ctx['git_parent']).decode().strip() == ctx['base']
         and set(web.git(ctx,'diff','--name-only',ctx['base'],ctx['commit']).decode().splitlines()) == set(paths),
         'real immutable cumulative Git objects; never fake parent=base')
    for f in typed['current_cumulative_files']:
        blob = web.git(ctx,'show',ctx['commit']+':'+f['repo_path'])
        need(hashlib.sha256(blob).hexdigest() == f['sha256'] and len(blob) == f['size']
             and web.git(ctx,'rev-parse',ctx['commit']+':'+f['repo_path']).decode().strip() == f['blob'], 'exact complete producer blobs')
    dictionary = data['actual_dictionary_base_equality']; relative = str(Path(dictionary['path']).relative_to(Path(ctx['worktree'])))
    old = web.git(ctx,'show',ctx['base']+':'+relative); new = web.git(ctx,'show',ctx['commit']+':'+relative)
    need(old == new and hashlib.sha256(new).hexdigest() == dictionary['sha256'] and len(new) == dictionary['size'],
         'shared dictionary/MS preserved at actual baseline bytes')
    backup = a.document(root, item['source_backup'])
    need(web.code_same_pin(root,item['source_backup'],data['actual_source_backup_C1_copy'])
         and web.external(root, typed['real_own_source_backup'],binding) == backup
         and backup.get('task_id') == snapshot['task_id'] and backup.get('source_commit') == ctx['commit']
         and backup.get('source_base') == ctx['base'] and backup.get('git_parent') == ctx['git_parent']
         and backup.get('unknown_effect_replay_allowed') is False, 'own cumulative source backup, not defective-parent/platform restore')
    for p in backup['files'] + [backup['source_archive']]: web._external_bytes(p,binding)
    delta = web._patch_effect(web._delta(ctx,ctx['base'],ctx['commit']))
    need(web._patch_effect(web._patch_delta(web._external_bytes(backup['forward'],binding))) == delta
         and web._patch_effect(web._patch_delta(web._external_bytes(backup['inverse'],binding))) == {p:(v[1],v[0]) for p,v in delta.items()},
         'cumulative exact forward/inverse; historical linear inverse is not production recovery')
    ctx['source_components'] = [{'base':ctx['base'],'head':ctx['commit'],'paths':paths}]
    account = a.document(root,item['account_source']); account_native = g._native_document(root,item['account_native'])
    calls=[(t,c) for t in account_native.get('turns',[]) for c in t.get('items',[]) if c.get('id')==item['account_command']]
    need(len(calls)==1 and account_native.get('thread',{}).get('id')==binding['thread_id'],'actual original account read identity')
    at,ac=calls[0]; outputs=[]
    for line in w._completion_execution_output(ac).decode().splitlines():
        try: value=json.loads(line)
        except ValueError: continue
        if isinstance(value,dict):outputs.append(value)
    need(at.get('status')=='completed' and not at.get('error') and ac.get('status')=='completed' and ac.get('exitCode')==0
         and outputs==[account] and account['full_name']==base['repository']
         and type(account['id']) is int and type(account['authenticated_actor']['id']) is int
         and account['authenticated_actor']['login']==base['repository'].split('/')[0], 'same repository and actual actor; no principal default')
    ctx.update(repository_id=account['id'],actor_id=account['authenticated_actor']['id'])
    previous=''
    for event in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS):
        need(event.get('previous_event_hash','')==previous and event.get('event_hash')==w.sha256_value({k:v for k,v in event.items() if k!='event_hash'}), 'intact original append-only event hash chain')
        previous=event['event_hash']
    need(not w._validate_receipt_chain(root,snapshot['task_id'])[1], 'intact original receipt chain')
    return ctx


def code_records(root, task):
    import goal_delivery_runtime as g
    snapshot=g.restore_goal(root,w.read_json(w.snapshot_path(root,task))); values=[]
    for e in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS):
        pin=e.get('details',{}).get(CODE_EVENT)
        if e.get('task_id')==task and pin:
            need(not any(x['registration']==pin for x in values),'one committed code-source effect')
            values.append({**code_context(root,snapshot,a.document(root,pin)),'registration':pin,'event_id':e['event_id']})
    return values


def record_code(root, task, path):
    import goal_delivery_runtime as g
    pin=w.file_digest(root,path)
    with w.workflow_lock(root):
        snapshot=g.restore_goal(root,w.read_json(w.snapshot_path(root,task)));ctx=code_context(root,snapshot,a.document(root,pin))
        old=code_records(root,task)
        if old:
            need(len(old)==1 and old[0]['registration']==pin,'existing code-stage effect must be read; never replace it')
            return {'result':'duplicate_ignored','source':pin,'event_id':old[0]['event_id'],'permission_issued':False}
        e=w.append_workflow_event(root,task,snapshot['current_state'],{CODE_EVENT:pin})
    return {'result':'recorded','source':pin,'event_id':e['event_id'],'permission_issued':False,'primary_CMS_source_unchanged':True}


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
