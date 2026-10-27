"""Typed existing CMS channel delivery -> original WEB consumer and per-row issuer.

No website/API operations, permit creation or receiver substitution occur here.
Business sources and professional standing are re-read through their original
validators; a typed report is not authority by itself.
"""
from pathlib import Path
from copy import deepcopy
import hashlib
import json
import re
import subprocess
import tempfile
import tarfile
import workflow_control as w
import department_autonomy as a
import professional_cms_execution as cms

SCHEMA = 'professional-standing-CMS-WEB-channel-source/v1'


def need(value, message):
    a.require(value, 'CMS channel: ' + message)


def _pins(value):
    if isinstance(value, dict):
        if set(value) == {'path', 'sha256', 'size'}: yield value
        for child in value.values(): yield from _pins(child)
    elif isinstance(value, list):
        for child in value: yield from _pins(child)


def _targets(value):
    if isinstance(value, dict):
        if isinstance(value.get('target'), dict) and value['target'].get('candidateVersion'):
            yield value
        for child in value.values(): yield from _targets(child)
    elif isinstance(value, list):
        for child in value: yield from _targets(child)


def callbacks(root, pin):
    """Only historical completed deliveries are memoized within one request.

Live standing, requests, effects, policies, permits and execution CAS are not
returned from this memo. Any changed local source dependency invalidates it.
"""
    context = w._VALIDATION_CONTEXT.get()
    key = (str(Path(root).resolve()), w.sha256_value(pin))
    memo = getattr(context, '_CMS_channel_completed_deliveries', {}) if context else {}
    cached = memo.get(key)
    if cached:
        for path, version in cached['dependencies'].items():
            context.bytes(path)
            if context.files[path]['version'] != version:
                cached = None; break
        if cached:
            for path, version in cached['external_versions'].items():
                p = Path(path); stat = p.stat()
                if (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns) != version:
                    cached = None; break
        if cached: return deepcopy(cached['value'])
    import goal_delivery_runtime as g
    from professional_cms_issuer import external
    bundle = a.document(root, pin)
    need(bundle.get('schema') == 'C1-original-existing-standing-channel-continuation-input/v6'
         and isinstance(bundle.get('entries'), list) and 0 < len(bundle['entries']) <= 8,
         'one bounded actual completed-channel input required')
    result = []; seen = set(); external_versions = {}
    for entry in bundle['entries']:
        task = entry.get('task_id'); need(task not in seen, 'unique original task entry'); seen.add(task)
        snapshot = g.restore_goal(root, w.read_json(w.snapshot_path(root, task)))
        role = entry.get('original_source_executor')
        binding = w.read_json(Path(root)/'data/department-registry.json')['collaboration_bindings'].get(role)
        need(binding and binding['project_id'] != a.PROJECT and role not in snapshot['goal_delivery']['producer_departments'],
             'original fixed external source executor, never a business producer')
        states = [x for x in g._collaboration_wait_states(root, snapshot, only_action_id=entry.get('original_action_id'))
                  if x.get('action_id') == entry.get('original_action_id')
                  and x.get('department') == role and x.get('status') == 'result_received'
                  and x.get('proof_state') == 'PROVEN' and x.get('result') == entry.get('actual_WEB_result')]
        need(len(states) == 1, 'actual normally received and independently completed original WEB result required')
        report = a.document(root, entry['actual_WEB_result'])
        custody = a.document(root, entry['C1_source_custody'])
        original_pin = custody.get('typed_original')
        original = external(root, original_pin, binding)
        need(original == report and original_pin['sha256'] == entry['actual_WEB_result']['sha256']
             and original_pin['size'] == entry['actual_WEB_result']['size']
             and report.get('task_id') == task and report.get('scope') == entry['scope']
             and report.get('producer') == role and report.get('producer_thread') == binding['thread_id']
             and custody.get('typed_exact_bytes_copy') == entry['actual_WEB_result'],
             'exact original typed bytes, actual receiver custody, task/scope and role required')
        stat = Path(original_pin['path']).stat()
        external_versions[original_pin['path']] = (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns)
        result.append({'entry': entry, 'report': report, 'binding': binding, 'role': role})
    if context:
        memo[key] = {'value': deepcopy(result), 'dependencies': {p:x['version'] for p,x in context.files.items()},
                     'external_versions': external_versions}
        context._CMS_channel_completed_deliveries = memo
    return result


def dependency_supplement(root, selected, item):
    """Keep a delivered candidate immutable while authenticating later source facts.

    This is not a replacement business result. The original committed callback,
    its actual completed turn, the command's exact emitted pin and unchanged Git
    candidate all have to agree before these extra dependency pins can be used.
    """
    pin = item.get('source_dependency_supplement')
    if pin is None:
        need(item.get('supplement_native') is None and item.get('supplement_command_id') is None,
             'supplement metadata requires its exact immutable source')
        return None
    import goal_delivery_runtime as g
    from professional_cms_issuer import external
    report, entry, binding = selected['report'], selected['entry'], selected['binding']
    custody = a.document(root, entry['C1_source_custody'])
    original_pin = custody.get('actual_supplement_original')
    supplement = a.document(root, pin)
    need(custody.get('actual_supplement_copy') == pin and external(root, original_pin, binding) == supplement
         and all(pin[k] == original_pin[k] for k in ('sha256', 'size')),
         'actual receiver byte custody of the exact external supplement required')
    local = report.get('local_candidate', report.get('local_version', {}))
    need(supplement.get('schema') in {'original-WEB-immutable-current-source-dependency-supplement/v1',
                                    'original-WEB-wardrobe15-immutable-current-source-dependency-supplement/v3'}
         and all(supplement.get(k) == report.get(k) for k in ('task_id', 'scope', 'action_id', 'producer', 'producer_thread'))
         and supplement.get('original_local_delivery') == custody.get('typed_original')
         and supplement.get('source_registration') == item.get('source_registration') == report.get('source_registration')
         and all(supplement.get('original_local_' + k) == local.get(k) for k in ('head', 'parent', 'tree'))
         and supplement.get('original_local_12_source_files', supplement.get('original_local_source_files')) == local.get('paths')
         and type(supplement.get('current_edge_version')) is int and supplement['current_edge_version'] > 0,
         'same original delivered task/role/scope/action/registered source and unchanged full candidate required')
    native = g._native_document(root, item.get('supplement_native'))
    need(all(native.get('thread', {}).get(k) == binding[v] for k, v in
             {'id': 'thread_id', 'title': 'title', 'cwd': 'cwd'}.items()), 'original fixed external source identity')
    states = [s for s in g._collaboration_wait_states(root,
              g.restore_goal(root, w.read_json(w.snapshot_path(root, entry['task_id']))),
              only_action_id=entry['original_action_id'])
              if s.get('status') == 'result_received' and s.get('proof_state') == 'PROVEN'
              and s.get('result') == entry['actual_WEB_result'] and s.get('department') == selected['role']]
    need(len(states) == 1, 'one original committed completed delivery for the supplement')
    old_native = g._native_document(root, states[0]['native_result'])
    old_finals = [(t, m) for t in old_native.get('turns', []) for m in t.get('items', [])
                  if m.get('type') == 'agentMessage' and m.get('phase') == 'final_answer']
    calls = [(t, m) for t in native.get('turns', []) for m in t.get('items', [])
             if m.get('id') == item.get('supplement_command_id')]
    need(len(calls) == len(old_finals) == 1, 'one real successful source command and original final required')
    turn, command = calls[0]; old_turn, final = old_finals[0]
    made = w._parse_observed_at(supplement.get('produced_at'))
    need(turn.get('id') == old_turn.get('id') and turn.get('status') == old_turn.get('status') == 'completed'
         and not turn.get('error') and command.get('type') == 'commandExecution'
         and command.get('status') == 'completed' and command.get('exitCode') == 0
         and Path(command.get('cwd', '')).resolve().is_relative_to(Path(binding['cwd']).resolve())
         and final in turn.get('items', []) and made is not None
         and type(turn.get('startedAt')) in {int, float} and type(turn.get('completedAt')) in {int, float}
         and turn['startedAt'] <= made.timestamp() <= turn['completedAt'],
         'same real completed WEB turn/final and ordered supplement command; no caller completion flag')
    output = json.loads(w._completion_execution_output(command))
    need(output.get('report') == original_pin, 'actual complete native output must emit this exact supplement pin')
    return supplement


def baseline(root, source):
    if source.get('baseline_pin') is not None:
        # This context came from the authenticated source validator, not the caller.
        a.document(root, source['baseline_pin'])
        return source['baseline_pin']
    original = a.document(root, source['source'])
    if 'original_source_baseline_only' in original:
        return original['original_source_baseline_only']['complete_row']
    rows = [r for r in original.get('record_actions', []) if r.get('exact_action') == source['action']]
    need(len(rows) == 1, 'one exact original per-row baseline carrier required')
    return rows[0]['baseline_only']['complete_row']


def exact_target(root, source, delivery, binding):
    from professional_cms_issuer import external
    action = source['action']; row = a.document(root, baseline(root, source))
    retained = source['protected_fields']['stable_business_readback_fields']
    content_type = {'services': 'service', 'blog_posts': 'blog'}.get(action['table'])
    need(content_type is not None, 'existing supported content table only')
    expected = {'id':action['record_id'], 'slug':action['slug'], 'contentType':content_type,
      'table':action['table'], 'taskId':action['task_id'], 'actionId':action['action_id'],
      'candidateVersion':action['candidate_version'], 'scope':action['scope'],
      'changedFields':action['changed_fields'], 'baselineProjectionFields':sorted(row),
      'baselineFieldsSha256':w.sha256_value(row), 'desiredFieldsSha256':w.sha256_value(source['desired']),
      'rollbackFieldsSha256':w.sha256_value(source['before']), 'expectedUpdatedAt':row['updated_at'],
      'retainedProjectionFields':sorted(retained),
      'retainedFieldsSha256':w.sha256_value({k:row[k] for k in retained}),
      'rollbackAllowed':True, 'requiresParentRun':True}
    need(delivery.get('target') == expected, 'every WEB target field/digest/scope must equal the registered row source')
    frozen = external(root, delivery.get('source_json'), binding)
    need(frozen.get('task_id') == action['task_id'] and frozen.get('business_scope') == source['business_scope']
         and frozen.get('owner_source') == source['source']
         and frozen.get('registration_input') == source['carrier']
         and frozen.get('execution_department') == source['executor']
         and frozen.get('original_professional_owner') == source['owner']
         and frozen.get('registration_grants_write_authority') is False,
         'unchanged original frozen source and participants, never a write grant')
    candidates = [x for x in frozen.get('entries', []) if x.get('runtime_target') == expected]
    need(len(candidates) == 1 and candidates[0].get('before') == row
         and candidates[0].get('desired') == source['desired']
         and candidates[0].get('forward_tuple') == action,
         'actual frozen full-row before/desired/tuple, not a metadata-only target')
    cli = delivery.get('Node_CLI', {})
    need(cli.get('target') == action['candidate_version'] and cli.get('record_id') == action['record_id']
         and cli.get('scope') == action['scope'] and cli.get('workflow') == '.github/workflows/content-publish-approved.yml'
         and cli.get('entrypoint') == 'scripts/publish-content-trust-fixes.mjs'
         and delivery.get('inverse_action') == 'rollback-' + action['candidate_version']
         and delivery.get('inverse_candidate') == action['candidate_version'] + '-rollback-v1',
         'same normal CLI/workflow and own conditional inverse namespace required')
    return expected


def validate(root, snapshot, item):
    import professional_web_execution as web
    import goal_delivery_runtime as g
    need(item.get('schema') == SCHEMA and item.get('task_id') == snapshot['task_id']
         and snapshot.get('current_state') not in w.TERMINAL_STATES,
         'active original task and normal channel source required')
    selected = [x for x in callbacks(root, item.get('channel_input')) if x['entry']['task_id'] == snapshot['task_id']]
    need(len(selected) == 1, 'one exact original task entry required')
    selected = selected[0]; entry = selected['entry']; report = selected['report']; binding = selected['binding']
    sources = [x for x in cms.records(root, snapshot) if x['registration'] == item.get('source_registration')]
    need(sources and all(x['business_scope'] == entry['scope'] and x['owner'] == entry['original_business_owner']
          and x.get('message_owner',x['owner']) == entry['publication_integrator']
          and x['executor'] == entry['original_CMS_executor'] and x['channel'] == selected['role'] for x in sources),
         'same already-registered professional source/standing holder/business owner/executors')
    names = {x['action']['candidate_version'] for x in sources}; actual = list(_targets(report))
    targets = {x['target']['candidateVersion']:x for x in actual}
    need(len(actual) == len(targets) == len(sources) and set(targets) == names
         and sorted(entry['exact_targets'], key=lambda x:x['target']['candidateVersion']) == sorted(actual,key=lambda x:x['target']['candidateVersion']),
         'complete exact independently delivered target set, no omitted/extra/ambiguous row')
    physical = {x['action']['candidate_version']:exact_target(root,x,targets[x['action']['candidate_version']],binding) for x in sources}
    local = report.get('local_candidate', report.get('local_version')); meta = entry['real_local_candidate']
    need(local and all(meta.get(k) == local.get(k) for k in ('head','parent','tree','branch','paths','forward','inverse')),
         'unchanged real original local candidate metadata and full path map')
    paths = {x['path']:x['sha256'] for x in meta['paths']}
    need(len(paths) == len(meta['paths']) and 0 < len(paths) <= 40
         and all(not Path(p).is_absolute() and '..' not in Path(p).parts for p in paths), 'bounded unique same-project selected source paths')
    ctx = {'root':str(Path(root).resolve()), 'task':snapshot['task_id'], 'scope':entry['scope'],
      'owner':entry['original_business_owner'], 'role':selected['role'], 'binding':binding,
      'decision':item['source_registration'], 'authorization':snapshot['goal_delivery']['authorization_pin'],
      'contract':snapshot['goal_contract'], 'worktree':local['worktree'],
      'site':str(Path(local['worktree']).resolve().parent.parent), 'branch':meta['branch'],
      'commit':meta['head'], 'base':meta['parent'], 'tree':meta['tree'], 'paths':paths,
      'prefix':snapshot['task_id']+'-cms-channel', 'backup':item.get('source_backup'),
      'rollback':item.get('rollback_runbook'), 'standing_CMS_channel':True,
      'authority_department':sources[0].get('message_owner',sources[0]['owner']),
      'standing_authorization_id':sources[0]['standing_authorization_id'],
      'registered_CMS_sources':sources, 'CMS_targets':physical,
      'WEB_delivery':entry['actual_WEB_result'], 'channel_input':item['channel_input']}
    need(Path(ctx['worktree']).resolve().is_relative_to(Path(binding['cwd']).resolve()), 'original fixed WEB worktree only')
    need(web.git(ctx,'show','-s','--format=%H %P %T',ctx['commit']).decode().strip() == ' '.join([ctx['commit'],ctx['base'],ctx['tree']])
         and set(web.git(ctx,'diff','--name-only',ctx['base'],ctx['commit']).decode().splitlines()) == set(paths),
         'real immutable Git commit/parent/tree and complete exact delta paths required')
    for path, sha in paths.items():
        need(hashlib.sha256(web.git(ctx,'show',ctx['commit']+':'+path)).hexdigest() == sha, 'actual candidate source blob differs')
    forward = web._external_bytes(meta['forward'],binding); inverse = web._external_bytes(meta['inverse'],binding)
    delta = web._patch_effect(web._delta(ctx,ctx['base'],ctx['commit']))
    need(web._patch_effect(web._patch_delta(forward)) == delta
         and web._patch_effect(web._patch_delta(inverse)) == {p:(added,removed) for p,(removed,added) in delta.items()},
         'real exact forward/inverse source effects; not a platform restoration proof')
    repo = web.git(ctx,'config','--get','remote.origin.url').decode().strip()
    match = re.fullmatch(r'(?:user-3de132cd98be@example.invalid:|https://github.com/)([\w.-]+/[\w.-]+?)(?:\.git)?',repo)
    need(match, 'original GitHub repository only'); ctx['repository'] = match[1]
    account = a.document(root,item.get('account_source'))
    supplement = dependency_supplement(root, selected, item)
    all_pins = [p for x in callbacks(root,item['channel_input']) for p in _pins(x['report'])]
    if supplement is not None:
        all_pins.extend(_pins(supplement))
        ctx['source_dependency_supplement'] = item['source_dependency_supplement']
    original_account = item.get('account_original')
    need(original_account in all_pins and web._external_bytes(original_account,binding) == w.safe_path(root,item['account_source']['path']).read_bytes()
         and account.get('full_name') == ctx['repository'] and type(account.get('id')) is int,
         'actual original WEB repository/account readback, no caller identity default')
    actor = account.get('authenticated_actor', {})
    need(actor.get('login') == ctx['repository'].split('/')[0] and type(actor.get('id')) is int and actor['id'] > 0,
         'actual original authenticated account identity')
    ctx.update(repository_id=account['id'],actor_id=actor['id'])
    backup = a.document(root,ctx['backup'])
    need(backup.get('task_id') == ctx['task'] and backup.get('function') == 'content-publish'
         and backup.get('version') == (supplement['current_edge_version'] if supplement is not None else report.get('current_edge_version'))
         and backup.get('original_WEB_delivery') == entry['actual_WEB_result']
         and backup.get('runtime_files') and backup.get('source_build_archives'), 'real original full source/build backup, not an inverse-only claim')
    for pin in backup['runtime_files']+backup['source_build_archives']:web._external_bytes(pin,binding)
    proof_pin=backup.get('actual_source_proof');need(proof_pin in all_pins,'actual completed WEB runtime snapshot proof required')
    from professional_cms_issuer import external
    proof=external(root,proof_pin,binding);manifest=external(root,backup.get('source_manifest_original'),binding)
    need(manifest.get('version')==backup['version'] and manifest.get('project_ref')==backup.get('project_ref')
         and manifest.get('function')=='content-publish' and manifest.get('ezbr_sha256')==backup.get('ezbr_sha256'),
         'same original complete function/version/source manifest')
    expected_files=manifest.get('files',[]);folder=Path(backup['source_manifest_original']['path']).parent/'source'
    need(len(expected_files)==len(backup['runtime_files']) and len(expected_files)>0,'complete runtime source, no subset')
    mapped={str(folder/f['name']):f for f in expected_files}
    for p in backup['runtime_files']:
        need(p['path']in mapped and p['sha256']==mapped[p['path']]['sha256'] and p['size']==mapped[p['path']]['bytes'],
             'each original archived runtime file and exact byte/hash required')
    versions=[proof.get(k) for k in ('version','function_version') if k in proof]
    need(versions and all(v==backup['version']for v in versions),'real original function source observation version')
    if proof.get('archive') is not None:
        need(proof['archive']in backup['source_build_archives'],'original WEB archive proof, never caller replacement')
    else:
        need({(f['name'],f['sha256'],f['bytes'])for f in proof.get('runtime_files',[])}==
             {(f['name'],f['sha256'],f['bytes'])for f in expected_files},'actual full source comparison proves this original archive material')
    for archive in backup['source_build_archives']:
        with tarfile.open(archive['path'])as tar:
            files={m.name:m for m in tar.getmembers()if m.isfile()}
            need(all(not Path(m.name).is_absolute()and '..'not in Path(m.name).parts and not m.issym()and not m.islnk()for m in tar.getmembers()),'safe source-only archive')
            for name,f in mapped.items():
                rel='source/'+str(Path(name).relative_to(folder));need(rel in files and hashlib.sha256(tar.extractfile(files[rel]).read()).hexdigest()==f['sha256'],
                     'archive contains every exact original function source byte')
    runbook = a.document(root,ctx['rollback'])
    need(runbook.get('task_id') == ctx['task'] and runbook.get('source_registration') == item['source_registration']
         and runbook.get('WEB_delivery') == entry['actual_WEB_result']
         and runbook.get('source_backup') == ctx['backup']
         and runbook.get('unknown_effect_replay_allowed') is False
         and runbook.get('all_rows_own_effect_or_inverse_required') is True,
         'task/source-bound production recovery recipe; no current restore permission')
    from managed_cms_permit_issuer import SUPABASE_HOST
    project = SUPABASE_HOST.split('.')[0]; need(backup.get('project_ref') == project,'same existing protected function/project')
    ctx.update(project_ref=project,edge_scope='company.example:edge:'+project+':content-publish',pages_scope='company.example:pages:production')
    # Frozen legacy QA eligibility is not a new standing-channel prerequisite.
    # Keep its immutable event/receipt bytes and order verifiable, while the
    # current professional authority above is checked at its original entry.
    previous = ''
    for event in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS):
        need(event.get('previous_event_hash','') == previous
             and event.get('event_hash') == w.sha256_value({k:v for k,v in event.items() if k != 'event_hash'}),
             'intact append-only event hash chain')
        previous = event['event_hash']
    _, invalid = w._validate_receipt_chain(root,ctx['task'])
    need(not invalid, 'intact original receipt hash chain')
    return ctx


def issuer_context(root,snapshot,item):
    import professional_web_execution as web
    need(item.get('schema') == 'professional-cms-issuer-contract/v1' and item.get('task_id') == snapshot['task_id'], 'normal per-row issuer contract')
    contexts = [x for x in web.records(root,snapshot['task_id']) if x.get('standing_CMS_channel')
                and x['registration'] == item.get('channel_source_registration')]
    need(len(contexts) == 1,'real registered completed WEB channel source required')
    ctx = contexts[0]; name = item.get('target_name')
    sources = [x for x in ctx['registered_CMS_sources'] if x['registration'] == item.get('source_registration')
               and x['action']['candidate_version'] == name]
    need(len(sources) == 1 and name in ctx['CMS_targets'], 'one exact task/action/row namespace; no borrowed target')
    x = sources[0]
    return x, {'original_source_baseline_only':{'complete_row':baseline(root,x)}}, ctx['CMS_targets'][name]


def _edit_pattern(base, own, peer, tokens=False):
    """An exact union of authenticated source edits, not arbitrary conflict text.

    Independent edits keep their complete original bytes. Overlapping changes
    must reduce to insertions at the same original tokens; both original orders
    are allowed, never new tokens, deletion, or a changed common statement.
    """
    import difflib
    split = (lambda s: re.findall(r'\w+|\s+|[^\w\s]',s)) if tokens else (lambda s:s.splitlines(keepends=True))
    b,o,p = map(split,(base,own,peer)); edits=[]
    for side,version in enumerate((o,p)):
        for tag,i,j,k,l in difflib.SequenceMatcher(None,b,version,autojunk=False).get_opcodes():
            if tag=='equal':continue
            need(not tokens or tag=='insert','overlapping source replacement/deletion is not an additive integration')
            edits.append((i,j,side,version[k:l]))
    groups=[]
    for e in sorted(edits,key=lambda e:(e[0],e[1],e[2])):
        if groups and e[0]<=groups[-1][1]:
            groups[-1][1]=max(groups[-1][1],e[1]);groups[-1][2].append(e)
        else:groups.append([e[0],e[1],[e]])
    parts=[];cursor=0
    def segment(start,end,rows,side):
        out=[];at=start
        for i,j,s,add in rows:
            if s!=side:continue
            out+=b[at:i]+add;at=j
        return ''.join(out+b[at:end])
    for start,end,rows in groups:
        parts.append(re.escape(''.join(b[cursor:start])));left=segment(start,end,rows,0);right=segment(start,end,rows,1);original=''.join(b[start:end])
        if left==right:parts.append(re.escape(left))
        elif left==original:parts.append(re.escape(right))
        elif right==original:parts.append(re.escape(left))
        elif start==end:parts.append('(?:'+re.escape(left+right)+'|'+re.escape(right+left)+')')
        else:
            need(not tokens,'unexpected overlapping insertion intervals')
            parts.append(_edit_pattern(original,left,right,tokens=True))
        cursor=end
    parts.append(re.escape(''.join(b[cursor:])))
    return ''.join(parts)


def _managed_count_normalization(path, texts, own_count, peer_count):
    """Only existing test registry-count assertions may combine two row deltas.

    A whole-line grammar excludes executable suffixes. Exact authorized row
    counts determine the arithmetic; trailing comments have no execution effect.
    Production paths and all other source bytes stay in the exact edit proof.
    """
    if not path.endswith('.test.ts'):return texts
    pattern=re.compile(r'^([ \t]*(?:expect\([A-Za-z_][A-Za-z0-9_.]*\)\.toHaveLength\([0-9]+\);[ \t]*)?)expect\(historicalTargets\)\.toHaveLength\(([0-9]+)\);[ \t]*(?://[^\r\n]*)?(\r?\n|$)',re.M)
    found=[list(pattern.finditer(s))for s in texts]
    need(len({len(v)for v in found})==1,'same original registry-count assertions only')
    for rows in zip(*found):
        b,o,p,m=[int(x[2])for x in rows]
        need(o-b in {0,own_count}and p-b in {0,peer_count}and m==o+p-b,
             'test count must equal the exact two registered target additions')
        need(len({x[1]for x in rows})==1,'unchanged original count assertion prefix')
    return [pattern.sub(lambda m:m[1]+'expect(historicalTargets).toHaveLength(EXACT_REGISTERED_COUNT);'+m[3],s)for s in texts]


def _bounded_shared_candidate(ctx, state, head, base):
    import goal_delivery_runtime as g
    import professional_web_execution as web
    from professional_cms_issuer import external
    root=Path(ctx['root']);pin=state.get('bounded_shared_source');item=a.document(root,pin)
    need(item.get('schema')=='C1-original-normal-bounded-shared-source-compatibility-input/v2'
         and item.get('task_id')==ctx['task']and item.get('scope')==ctx['scope']
         and item.get('source_owner')==ctx['authority_department']and item.get('executor')==ctx['role']
         and item.get('original_normal_source')=={'path':ctx['registration']['path'],'sha256':ctx['registration']['sha256'],'event':ctx['event_id']}
         and item.get('original_business_source_registration_sha256')==ctx['decision']['sha256'],
         'same original registered task/scope/professional source; no caller waiver')
    snapshot=g.restore_goal(root,w.read_json(w.snapshot_path(root,ctx['task'])))
    need(snapshot.get('current_state')not in w.TERMINAL_STATES,'closed original task cannot adopt a bounded source')
    rows=[v for v in g._collaboration_wait_states(root,snapshot,only_action_id=item.get('original_WEB_action_id'))if v.get('action_id')==item.get('original_WEB_action_id')
          and v.get('department')==ctx['role']and v.get('status')=='result_received'and v.get('proof_state')=='PROVEN'
          and v.get('result')==item.get('producer_result')]
    need(len(rows)==1,'normally received real independently completed WEB integration source required')
    report=a.document(root,item['producer_result']);custody=a.document(root,item.get('C1_custody'))
    receiver=w.department_registry(root)[ctx['authority_department']]['chat_binding']
    need(custody.get('task_id')==ctx['task']and custody.get('scope')==ctx['scope']
         and custody.get('owner')==ctx['authority_department']and custody.get('producer')==ctx['role']
         and receiver.get('project_id')==a.PROJECT and Path(receiver.get('cwd','')).resolve()==root.resolve()
         and report.get('recipient_thread')==receiver['task_id'],'same exact original professional receiver/project/custody')
    need(custody.get('typed_exact_bytes')==item['producer_result']
         and external(root,custody.get('typed_original'),ctx['binding'])==report
         and report.get('task_id')==ctx['task']and report.get('scope')==ctx['scope']
         and report.get('producer')==ctx['role']and report.get('producer_thread')==ctx['binding']['thread_id']
         and report.get('recipient')==ctx['authority_department']
         and report.get('action_id')==item['original_WEB_action_id']
         and report.get('source_registration')==item['original_normal_source'],
         'exact original typed bytes/custody/receiver and source relation required')
    meta=report.get('actual_causal_integration_version',{});obj=item.get('actual_new_object',{})
    need(meta.get('head')==obj.get('head')==head and meta.get('integration_base')==obj.get('integration_base')==base
         and all(meta.get(k)==obj.get(k)for k in ('parents','tree','branch','worktree','forward','inverse'))
         and meta.get('branch')==ctx['branch']and meta.get('worktree')==ctx['worktree']
         and set(meta.get('parents',[]))=={ctx['commit'],base}and len(meta['parents'])==2,
         'actual same-source merge head/parents/base/tree/branch/worktree, never a named exception')
    need(web.git(ctx,'show','-s','--format=%H %P %T',head).decode().strip()==' '.join([head,*meta['parents'],meta['tree']])
         and web.git(ctx,'merge-base',ctx['base'],base).decode().strip()==ctx['base'],
         'real immutable Git lineage required')
    paths=meta.get('paths',[]);pathmap={p['path']:p for p in paths}
    need(len(pathmap)==len(paths)==obj.get('paths')and set(pathmap)==set(ctx['paths'])
         and set(web.git(ctx,'diff','--name-only',base,head).decode().splitlines())<=set(ctx['paths']),
         'complete original declared paths; no additional source change')
    for path,row in pathmap.items():
        raw=web.git(ctx,'show',head+':'+path)
        need(hashlib.sha256(raw).hexdigest()==row.get('sha256')and len(raw)==row.get('size')
             and web.git(ctx,'rev-parse',head+':'+path).decode().strip()==row.get('blob'),
             'actual full candidate source bytes/blob/size')
    delta=web._patch_effect(web._delta(ctx,base,head))
    need(web._patch_effect(web._patch_delta(web._external_bytes(meta['forward'],ctx['binding'])))==delta
         and web._patch_effect(web._patch_delta(web._external_bytes(meta['inverse'],ctx['binding'])))=={p:(added,removed)for p,(removed,added)in delta.items()},
         'exact original forward and inverse source effect')
    proofpin=obj.get('semantic_proof');need(proofpin in list(_pins(report)),'actual reported immutable bounded proof pin required')
    proof=external(root,proofpin,ctx['binding'])
    need(proof.get('task_id')==ctx['task']and proof==report.get('exact_semantic_integration')and proof.get('head')==head
         and proof.get('base')==base and proof.get('original')==ctx['commit'],
         'actual reported proof source, not caller true flags')
    peers=[]
    for v in callbacks(root,ctx['channel_input']):
        if v['entry']['task_id']==ctx['task']:continue
        for peer in web.records(root,v['entry']['task_id']):
            if peer.get('standing_CMS_channel')and peer['binding']==ctx['binding']and peer['base']==ctx['base']:
                if web.git(ctx,'merge-base',peer['commit'],base).decode().strip()==peer['commit']:peers.append(peer)
    need(len(peers)==1,'one real already-registered original same-channel peer integrated in this base')
    peer=peers[0];shared=set(ctx['paths'])&set(peer['paths']);need(shared,'actual shared source paths required')
    def blob(commit,path):
        p=subprocess.run(['git','show',commit+':'+path],cwd=ctx['worktree'],capture_output=True)
        return p.stdout if p.returncode==0 else None
    for path in ctx['paths']:
        mode=web.git(ctx,'ls-tree',ctx['commit'],'--',path).split()[:1]
        need(mode in ([b'100644'],[b'100755'])and web.git(ctx,'ls-tree',head,'--',path).split()[:1]==mode,
             'original source modes, never a symlink/submodule')
        merged=blob(head,path);own=blob(ctx['commit'],path)
        if path not in shared:need(merged==own,'own exclusive targets/frozen source/test bytes unchanged');continue
        previous=blob(ctx['base'],path);other=blob(base,path)
        need(previous is not None and other==blob(peer['commit'],path)
             and web.git(ctx,'ls-tree',base,'--',path).split()[:1]==web.git(ctx,'ls-tree',peer['commit'],'--',path).split()[:1],
             'same authentic peer contribution; unrelated current source cannot be replaced')
        texts=[s.decode('utf-8')for s in (previous,own,other,merged)]
        texts=_managed_count_normalization(path,texts,len(ctx['CMS_targets']),len(peer['CMS_targets']))
        need(re.fullmatch(_edit_pattern(*texts[:3]),texts[3])is not None,
             'shared source must be exactly the original two contributions; new logic/content is not a proof')
    return head,base


def candidate(ctx,state):
    """Own source on a real later base; clean merge or authenticated additive proof."""
    import professional_web_execution as web
    head = state.get('candidate_commit'); base = state.get('candidate_base',ctx['base'])
    need(re.fullmatch('[0-9a-f]{40}',str(head)) and re.fullmatch('[0-9a-f]{40}',str(base)), 'real current candidate/base required')
    mode = state.get('source_mode','forward'); need(mode in {'forward','remove_own_delta'},'known own source mode')
    if state.get('bounded_shared_source') is not None:
        need(mode=='forward','bounded additive proof does not authorize inverse or unknown modes')
        return _bounded_shared_candidate(ctx,state,head,base)
    if head == ctx['commit'] and mode == 'forward':
        need(base == ctx['base'],'exact original base'); return head,base
    need(web.git(ctx,'merge-base',ctx['base'],base).decode().strip() == ctx['base']
         and set(web.git(ctx,'diff','--name-only',base,head).decode().splitlines()) <= set(ctx['paths']),
         'real causal base and original selected paths only')
    if mode == 'remove_own_delta':
        import goal_delivery_runtime as g
        snapshot = g.restore_goal(Path(ctx['root']),w.read_json(w.snapshot_path(Path(ctx['root']),ctx['task'])))
        pins = state.get('CMS_recovery_sources',[]); need(len(pins) == len(ctx['registered_CMS_sources']), 'all own row effects must be proved before removing channel')
        proven = [s for s in g._collaboration_wait_states(Path(ctx['root']),snapshot) if s.get('department') == ctx['registered_CMS_sources'][0]['executor'] and s.get('status') == 'result_received' and s.get('proof_state') == 'PROVEN']
        for source,pin in zip(ctx['registered_CMS_sources'],pins):
            doc = a.document(Path(ctx['root']),pin); guard = doc.get('CMS_recovery_guard',{})
            need(any(s.get('result') == pin for s in proven) and guard.get('task_id') == ctx['task']
                 and guard.get('forward_action_id') == source['action']['action_id'] and guard.get('record_id') == source['action']['record_id']
                 and (guard.get('state') == 'NO_OWN_SAVE' and guard.get('publish_runs') == [] and guard.get('permits') == []
                   or guard.get('state') == 'OWN_INVERSE_COMPLETED' and all(guard.get(k) for k in ('original_publish_permit_id','original_publish_run_id','inverse_permit_id','inverse_completed_run_id','saved_updated_at'))),
                 'each original PUB completed own inverse or real zero-effect guard; unknown is held')
    left,right = (ctx['base'],ctx['commit']) if mode == 'forward' else (ctx['commit'],ctx['base'])
    scratch = Path(ctx['root'])/'logs/professional-CMS-channel-source-checks'; scratch.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=scratch) as directory:
        temp = Path(directory)
        for path in ctx['paths']:
            def blob(commit):
                p=subprocess.run(['git','show',commit+':'+path],cwd=ctx['worktree'],capture_output=True)
                return p.stdout if p.returncode==0 else b''
            for name,commit in (('current',base),('ancestor',left),('own',right)):(temp/name).write_bytes(blob(commit))
            p=subprocess.run(['git','merge-file','-p',str(temp/'current'),str(temp/'ancestor'),str(temp/'own')],capture_output=True)
            need(p.returncode==0 and blob(head)==p.stdout,'real shared-path conflict/new content needs exact bounded source-difference proof; no HQ approval inferred')
            need(web.git(ctx,'ls-tree',head,'--',path).split()[:1] == web.git(ctx,'ls-tree',right,'--',path).split()[:1], 'same own source file mode/deletion only')
    return head,base
