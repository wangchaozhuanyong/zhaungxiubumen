"""Append-only current human/HQ release source over existing local custody.

No messaging, platform policy issuance, network call or CMS write lives here.
"""
from pathlib import Path
import datetime as dt
import json
import workflow_control as w
import department_autonomy as a

SCHEMA = 'current-owner-reviewed-WEB-release-source/v1'
EVENT = 'current_owner_reviewed_WEB_release'
STAGES = ('original repo/account exact push', 'original PR create/update',
          'official final-same-head Node22 CI', 'normal merge', 'necessary Pages',
          'own exact R3/environment/Edge load and readiness proof')


def need(ok, message):
    a.require(ok, 'reviewed WEB release: ' + message)


def same(root, left, right):
    return isinstance(left, dict) and isinstance(right, dict) and all(
        left.get(k) == right.get(k) for k in ('sha256', 'size')) and (
        Path(root)/left.get('path', '')).resolve() == (Path(root)/right.get('path', '')).resolve()


def reviewed_multi_body_package(root,snapshot,frozen,goal,base,row,package):
    """Authenticate every already registered body tuple; never issue a permit."""
    from professional_web_execution import git
    meta=package.get('candidate',{}); full=meta.get('full_range',{}); code=package.get('code_vs_CMS',{})
    actor=code.get('WEB_executor',{}); account=code.get('historical_repo_actor_identity',{})
    changes=package.get('CMS_changes'); targets=base.get('registered_protected_body_targets',{}); tuples=base.get('original_PUB_tuples',{})
    need(isinstance(changes,list) and len(changes)==len(targets)==len(tuples)>1
         and package.get('task_id')==snapshot['task_id'] and package.get('business_scope')==base['scope']
         and package.get('original_CMS_parent')==frozen.get('original_business_task_id')==goal.get('parent_task_id')
         and same(root,package.get('source_custody',{}).get('registration'),base['registration'])
         and package['source_custody'].get('event_id')==base.get('event_id')
         and row.get('candidate')==meta.get('head')==base['commit']
         and all(meta.get(k)==base[v] for k,v in {'base':'base','tree':'tree','branch':'branch','worktree':'worktree'}.items())
         and set(full.get('paths',[]))==set(base['paths']) and len(full.get('paths',[]))==full.get('count')==row.get('files')
         and all(actor.get(k)==base['binding'][v] for k,v in {'thread_id':'thread_id','project_id':'project_id','chat_cwd':'cwd'}.items())
         and actor.get('department')==base['role'] and code.get('PUB_executor',{}).get('department')==base['owner']
         and account.get('repository')==base['repository'] and account.get('repository_id')==base['repository_id']
         and account.get('actor_id')==base['actor_id']
         and all(x in code.get('CMS_protocol',[]) for x in ('publish_material_atomic','p_images=null','rollbackfalse','each record own key/policy/permit')),
         'exact original two-body source, owner, parent, actor and Git scope')
    files=meta.get('files',[]);mapped={}
    for f in files:
        p=str(Path(f['path']).resolve().relative_to(Path(base['worktree']).resolve()))
        raw=git(base,'show',base['commit']+':'+p)
        need(p not in mapped and len(raw)==f['size'] and __import__('hashlib').sha256(raw).hexdigest()==f['sha256'], 'exact unique original source file bytes')
        mapped[p]=f['sha256']
    need(mapped==base['paths'], 'all original candidate files exactly retained')
    scopes=[]; records=[]; actions=[]
    for change in changes:
        namespace=change.get('cli_namespace');target=targets.get(namespace);original=tuples.get(namespace);forward=change.get('forward_tuple',{})
        need(isinstance(target,dict) and isinstance(original,dict), 'each body tuple has its own registered target')
        fields=target['changedFields'];scope=target['scope'];record=target['table']+'/'+target['id']
        need(forward=={'task_id':snapshot['task_id'],'action_id':target['actionId'],'scope':scope,'operation':'publish',
                       'candidate_version':target['candidateVersion'],'fields':fields}
             and all(original.get(k)==v for k,v in {'task_id':snapshot['task_id'],'action_id':target['actionId'],
                 'candidate_version':target['candidateVersion'],'scope':scope,'table':target['table'],'record_id':target['id'],
                 'changed_fields':fields,'execution_owner':base['owner']}.items())
             and change.get('scope')==scope and change.get('table')==target['table'] and change.get('record_id')==target['id']
             and change.get('slug')==original['slug'] and set(change.get('before',{}))==set(fields)==set(change.get('desired',{}))
             and w.sha256_value(change['before'])==target['rollbackFieldsSha256']
             and w.sha256_value(change['desired'])==change.get('desired_fields_sha256')==target['desiredFieldsSha256']
             and change.get('baseline_projection_sha256')==target['baselineFieldsSha256']
             and change.get('historical_updated_at')==target['expectedUpdatedAt']
             and change.get('retained_fields_sha256')==target['retainedFieldsSha256']
             and change.get('protected_fields')==target['retainedProjectionFields']
             and change.get('full_fields')==len(target['baselineProjectionFields'])
             and change.get('protected_fields_count')==len(target['retainedProjectionFields'])
             and change.get('MS_fields_count')==len([p for p in target['retainedProjectionFields'] if p.endswith('_ms')])
             and change.get('rollback_allowed') is False and target.get('rollbackAllowed') is False
             and change.get('independent_singleuse_gate_and_effect_key') is True,
             'each original independent scope, action, values, full projection and protected fields')
        scopes.append(scope);records.append(record);actions.append(target['actionId'])
    need(len(set(scopes))==len(set(records))==len(set(actions))==len(changes)
         and set(scopes)==set(package.get('both_independent_scopes',[]))==set(goal['authorized_scope'])
         and set(records)==set(row.get('records',[])) and all(targets[n]['changedFields']==row.get('fields') for n in targets)
         and set(targets)==set(tuples)=={c['cli_namespace'] for c in changes}, 'both independently authorized rows; no missing or borrowed scope')


def validate(root, snapshot, item, base):
    import goal_delivery_runtime as g
    from professional_web_execution import code_pin
    root = Path(root).resolve(); a.authority(root)
    goal = a.participant(root, snapshot, snapshot['goal_delivery']['primary_owner'])
    frozen = a.document(root, snapshot['goal_contract'])
    keys = {'schema', 'task_id', 'scope', 'goal_contract', 'maintenance_task_id',
            'maintenance_goal_contract', 'original_custody_source', 'human',
            'HQ_decision', 'HQ_completed_native', 'HQ_source_command',
            'reviewed_package', 'owner_message_source'}
    need(set(item) == keys and item['schema'] == SCHEMA
         and item['task_id'] == snapshot['task_id'] == base['task']
         and item['scope'] == base['scope'] in goal['authorized_scope']
         and item['goal_contract'] == snapshot['goal_contract']
         and same(root, item['original_custody_source'], base['registration'])
         and base.get('protected_body_source_custody') is True
         and all(goal.get(k) == frozen.get(k) for k in
                 ('primary_owner', 'producer_departments', 'authorized_scope',
                  'human_authorization', 'required_execution_actions', 'collaboration_scopes')),
         'unchanged original active owner/contract/scope and genuine prior custody')
    repair = g.restore_goal(root, w.read_json(w.snapshot_path(root, item['maintenance_task_id'])))
    need(repair['goal_contract'] == item['maintenance_goal_contract']
         and repair['goal_delivery']['primary_owner'] == 'system-development'
         and repair['current_state'] not in w.TERMINAL_STATES,
         'active original local SYS maintenance authority')
    human_pin = code_pin(root, item['human']); raw = a.document(root, human_pin)
    decision_pin = code_pin(root, item['HQ_decision']); decision = a.document(root, decision_pin)
    page = g._native_document(root, item['HQ_completed_native'])
    hq = w.department_registry(root)['operations']['chat_binding']
    h = decision.get('source_human', {}); selected = raw.get('selected_native', {})
    need(decision.get('schema') == 'HQ-current-owner-pause-and-complete-bounded-other-goals/v1'
         and raw.get('schema') == 'selected-actual-owner-native-directive/v1'
         and raw.get('source_tool') == 'mcp__codex_app__read_thread'
         and all(page.get('thread', {}).get(k) == selected.get('thread', {}).get(k) == hq[v]
                 for k, v in {'id': 'task_id', 'title': 'title', 'cwd': 'cwd'}.items())
         and h.get('thread_id') == hq['task_id']
         and (root/h.get('path', '')).resolve() == (root/human_pin['path']).resolve(),
         'real fixed HQ current human and selected immutable source')
    turns = [t for t in page.get('turns', []) if t.get('id') == h.get('turn_id')]
    need(len(turns) == 1, 'one actual current human turn')
    turn = turns[0]
    messages = [m for m in turn.get('items', []) if m.get('id') == h.get('message_id')]
    need(len(messages) == 1 and messages[0].get('type') == 'userMessage'
         and selected.get('turn', {}).get('id') == turn['id']
         and selected.get('user_messages') == messages
         and ''.join(c.get('text', '') for c in messages[0].get('content', [])
                     if c.get('type') == 'text').strip() == h.get('exact_text') == raw.get('user_text_verbatim')
         and turn.get('status') == 'completed' and not turn.get('error')
         and type(turn.get('startedAt')) in {int, float}
         and type(turn.get('completedAt')) in {int, float},
         'actual human words/message and completed HQ observation; never invented grant')
    commands = [m for m in turn.get('items', []) if m.get('id') == item['HQ_source_command']]
    need(len(commands) == 1, 'one real HQ source readback command')
    call = commands[0]
    need(call.get('type') == 'commandExecution' and call.get('status') == 'completed'
         and call.get('exitCode') == 0 and call.get('output', {}).get('truncated') is False
         and Path(call.get('cwd', '')).resolve() == root,
         'complete successful original HQ command output')
    read = json.loads(w._completion_execution_output(call))
    made = w._parse_observed_at(decision.get('at_UTC'))
    need(same(root, read.get('source'), decision_pin) and same(root, read.get('human'), human_pin)
         and made is not None and turn['startedAt'] <= made.timestamp() <= turn['completedAt']
         <= dt.datetime.now(dt.timezone.utc).timestamp(),
         'actual ordered native output binds exact new human and HQ decision hashes')
    execution = decision.get('ordinary_remaining_execution', {})
    rows = [x for x in execution.get('reviewed_WEB_release_packages', [])
            if x.get('business_task') == snapshot['task_id']]
    need(len(rows) == 1 and tuple(execution.get('WEB_stages_in_current_execution_delegation', [])) == STAGES
         and decision.get('no_new_account_fees_or_destructive_permission') is True
         and decision.get('actual_platform_permit_issued') is False
         and decision.get('production_effect_claimed') is False
         and decision.get('pause', {}).get('task_id') != snapshot['task_id'],
         'unique reviewed original goal and complete bounded stages; no paused or sensitive expansion')
    row = rows[0]; package_pin = code_pin(root, item['reviewed_package'])
    need(code_pin(root, {'path': row['package_path'], 'sha256': row['package_sha256'],
                        'size': package_pin['size']}) == package_pin,
         'exact package selected by actual current HQ decision')
    package = a.document(root, package_pin); meta = package.get('candidate', {})
    code = package.get('code_vs_CMS_boundary', {}); actor = code.get('WEB_executor', {})
    if isinstance(package.get('CMS_changes'),list):
        reviewed_multi_body_package(root,snapshot,frozen,goal,base,row,package)
    else:
      need(package.get('task_id') == snapshot['task_id']
         and package.get('business_scope') == base['scope']
         and package.get('original_website_task_id') == row.get('website_task')
         and row.get('candidate') == meta.get('head') == base['commit']
         and all(meta.get(k) == base[v] for k, v in
                 {'base': 'base', 'tree': 'tree', 'branch': 'branch', 'worktree': 'worktree'}.items())
         and set(meta.get('paths', [])) == set(base['paths'])
         and len(meta.get('paths', [])) == meta.get('count') == row.get('files')
         and same(root, meta.get('source_registration'), base['registration'])
         and all(actor.get(k) == base['binding'][v] for k, v in
                 {'thread_id': 'thread_id', 'project_id': 'project_id', 'chat_cwd': 'cwd'}.items())
         and actor.get('role') == base['role'] + ' / original WEB normal issuer'
         and code.get('CMS_executor', {}).get('role') == base['owner']
         and code.get('repo_identity_historical', {}).get('repo_full_name') == base['repository']
         and code.get('repo_identity_historical', {}).get('repo_id') == base['repository_id']
         and code.get('repo_identity_historical', {}).get('actor_id') == base['actor_id']
         and {str(Path(x['path']).resolve().relative_to(Path(base['worktree']).resolve())): x['sha256']
              for x in meta.get('candidate_files', [])} == base['paths'],
         'same original website child/version/source paths/actor and business parent')
      cms = package.get('CMS_exact_change', {})
      need(cms.get('original_task_id') == snapshot['task_id']
         and cms.get('business_scope') == base['scope']
         and cms.get('fields') == row.get('fields')
         and cms.get('table', '') + '/' + cms.get('record_id', '') == row.get('record')
         and len([target for target in base['registered_protected_body_targets'].values()
                  if target.get('scope') == cms.get('physical_scope')
                  and target.get('id') == cms.get('record_id')
                  and target.get('table') == cms.get('table')
                  and target.get('changedFields') == cms.get('fields')
                  and target.get('rollbackAllowed') is False]) == 1
         and cms.get('CMS_rollback_allowed') is False,
         'unchanged exact original CMS fields/record/physical carrier and no inverse')
    wrapper = a.document(root, item['owner_message_source'])
    need(wrapper.get('schema') == 'professional-owner-result-message-source/v1'
         and wrapper.get('task_id') == snapshot['task_id'] and wrapper.get('scope') == base['scope']
         and wrapper.get('goal_contract') == snapshot['goal_contract']
         and wrapper.get('authorization') == goal['authorization_pin'],
         'unchanged original owner message source, no new producer')
    action = a.document(root, wrapper.get('original_action'))
    result = a.document(root, wrapper.get('professional_result_request'))
    a.native_result(root, result, w.department_registry(root)[base['owner']]['chat_binding']['task_id'])
    report = a.document(root, w.file_digest(root, result['outbox_path']))
    need(report.get('primary_owner') == report.get('department') == base['owner']
         and report.get('scope') == base['scope'] and report.get('delivery_model') == a.MODE
         and wrapper['original_action'] in report.get('evidence', [])
         and action.get('sender_department') == base['owner']
         and action.get('target_department') == base['role']
         and action.get('task_id') == result.get('task_id') == snapshot['task_id']
         and action.get('scope') == base['scope'] and action.get('action_class') == 'thread_message'
         and action.get('source_project_id') == a.PROJECT
         and all(action.get(k) == base['binding'].get(v) for k, v in
                 {'target_project_id':'project_id','target_thread_id':'thread_id',
                  'target_thread_title':'title','target_cwd':'cwd'}.items())
         and action.get('delivery_mode') == 'official_native_queue'
         and action.get('assignment_record_required') is False
         and action.get('authorization_changes') == action.get('internal_repairs') == []
         and not any(action.get(k) for k in ('approval_id', 'consume_approval', 'execution_request')),
         'genuine original professional result binds this exact ordinary owner message')
    payload = w.safe_path(root, action['payload']['path']).read_text()
    need(w.file_digest(root, action['payload']['path']) == action['payload']
         and action.get('payload_sha256') == action['payload']['sha256']
         and all(Path(p['path']).name in payload and p['sha256'] in payload
                 for p in (human_pin, decision_pin, package_pin)),
         'exact unchanged source-bearing body, never caller metadata delegation')
    return {**base, 'authorization': human_pin, 'decision': decision_pin,
            'protected_body_source_custody': False, 'local_source_stage_only': False,
            'current_owner_reviewed_release': True, 'source_custody_registration': base['registration'],
            'reviewed_release_package': package_pin, 'website_task_id': row.get('website_task'),
            'current_owner_message': {'source_thread_id': hq['task_id'], 'message': messages[0]},
            'owner_message_source': item['owner_message_source'], 'exact_owner_action': action,
            'production_authority_dependency': 'Normal original WEB fresh per-stage facts/backup/single-use guards; CMS permission remains independent.'}


def current(root, snapshot, base):
    rows = [(e, e['details'][EVENT]) for e in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS,where={('details',EVENT,'target_task_id'):snapshot['task_id']})
            if e.get('details', {}).get(EVENT, {}).get('target_task_id') == snapshot['task_id']]
    need(len(rows) <= 1, 'one immutable current owner release source')
    if not rows:
        return base
    event, entry = rows[0]; item = a.document(root, entry['source'])
    need(event['task_id'] == item['maintenance_task_id']
         and entry == {'target_task_id': snapshot['task_id'], 'source': entry['source']}
         and event['details'].get('external_permission_issued') is False,
         'real append-only source registration; no invented external effect')
    return {**validate(root, snapshot, item, base), 'registration': entry['source'],
            'event_id': event['event_id']}


def record(root, task, path):
    import goal_delivery_runtime as g
    from professional_cms_channel import original_body_records
    pin = w.file_digest(root, path); item = a.document(root, pin)
    with w.workflow_lock(root):
        snapshot = g.restore_goal(root, w.read_json(w.snapshot_path(root, task)))
        sources = original_body_records(root, task)
        need(len(sources) == 1, 'one genuine existing local source custody')
        validate(root, snapshot, item, sources[0])
        previous = current(root, snapshot, sources[0])
        if previous.get('current_owner_reviewed_release'):
            need(previous['registration'] == pin, 'immutable current source already bound')
            return {'result': 'duplicate_ignored', 'source': pin, 'external_permission_issued': False}
        action = a.document(root, a.document(root, item['owner_message_source'])['original_action'])
        a._owner_message_transport_not_started(root, snapshot, action)
        repair = w.read_json(w.snapshot_path(root, item['maintenance_task_id']))
        event = w.append_workflow_event(root, item['maintenance_task_id'], repair['current_state'],
                    {EVENT: {'target_task_id': task, 'source': pin}, 'external_permission_issued': False})
    return {'result': 'recorded_current_owner_source', 'source': pin, 'event_id': event['event_id'],
            'external_permission_issued': False, 'business_contract_unchanged': True,
            'message_sent': False, 'production_READY': False}


def _clean_custody_history(ctx,state):
    """Verify immutable Git history only; never authorize a current action."""
    import re
    import professional_web_execution as web
    head=state.get('candidate_commit');base=state.get('candidate_base')
    need(ctx.get('increment_source_mode')=='current_reviewed_causal_custody_successor'
         and ctx.get('increment_registration') and ctx.get('reviewed_peer_successor')
         and all(re.fullmatch('[0-9a-f]{40}',str(x or '')) for x in (head,base))
         and state.get('source_mode','forward')=='forward'
         and state.get('candidate_parent')==ctx['commit']
         and state.get('candidate_parents')==[ctx['commit'],base]
         and state.get('branch')==ctx['branch'] and state.get('worktree')==ctx['worktree'],
         'exact historical clean successor of the adopted source required')
    info=web.git(ctx,'show','-s','--format=%H %P %T',head).decode().strip().split()
    need(info==[head,ctx['commit'],base,state.get('candidate_tree')]
         and web.git(ctx,'merge-base',ctx['base'],base).decode().strip()==ctx['base']
         and base!=ctx['base'], 'actual historical tree, ordered parents and later base required')
    def changed(left,right):
        raw=web.git(ctx,'diff','--name-only','-z',left,right)
        return set(raw.decode('utf-8').split('\0')[:-1]) if raw else set()
    own=set(ctx['paths']); peer=changed(ctx['base'],base)
    need(bool(own) and bool(peer) and not (own & peer)
         and changed(ctx['base'],ctx['commit'])==own
         and changed(base,head)==own and changed(ctx['commit'],head)==peer,
         'exact complete own delta and disjoint peer paths required')
    for path in own:
        old=web.git(ctx,'ls-tree',ctx['commit'],'--',path)
        new=web.git(ctx,'ls-tree',head,'--',path)
        need(old==new and old.split()[:2] in ([b'100644',b'blob'],[b'100755',b'blob']),
             'all original own blobs and modes must remain identical')
    oldpatch=web.git(ctx,'diff','--no-ext-diff','--binary','--full-index',ctx['base'],ctx['commit'])
    newpatch=web.git(ctx,'diff','--no-ext-diff','--binary','--full-index',base,head)
    need(oldpatch==newpatch, 'exact original full binary patch required')
    return head,base


def _derived_custody_owner_message(root, snapshot, action, wrapper, ctx, result, report, prepared):
    """Authenticate an owner's real message about an adopted clean derivation."""
    import re
    import professional_web_increment as inc
    def local(pin):
        need(isinstance(pin,dict) and set(pin)=={'path','sha256','size'}, 'exact project pin required')
        path=Path(pin['path'])
        if not path.is_absolute():
            return pin
        need(path.resolve().is_relative_to(Path(root).resolve()) and not path.is_symlink(),
             'absolute historical pin must remain inside the original project')
        return {**pin,'path':w.rel_path(Path(root),path.resolve())}
    if 'SYS_adoption' not in prepared or 'WEB_original_result' not in prepared:
        return False
    need(result.get('task_id')==report.get('task_id')==prepared.get('task_id')==ctx['task']
         and result.get('sender_department')==report.get('primary_owner')==report.get('department')==ctx['owner']
         and report.get('scope')==prepared.get('scope')==ctx['scope']
         and report.get('delivery_model')==a.MODE and report.get('production_READY') is False
         and report.get('primary_deliverable') in report.get('evidence',[]),
         'exact genuine professional result, producer and original scope required')
    need(set(prepared)=={'task_id','scope','SYS_adoption','WEB_original_result',
         'original_owner_source','action','payload','status','external_permission_issued','production_ready'}
         and prepared.get('task_id')==snapshot['task_id']==ctx['task']
         and prepared.get('scope')==ctx['scope'] and prepared.get('status')=='PREPARED_NOT_SENT'
         and prepared.get('external_permission_issued') is False and prepared.get('production_ready') is False
         and prepared.get('action')==wrapper['original_action'] and prepared.get('payload')==action['payload']
         and same(root,prepared.get('original_owner_source'),ctx['registration'])
         and all(prepared[k] in report.get('evidence',[]) for k in
                 ('SYS_adoption','WEB_original_result','original_owner_source','action','payload')),
         'exact original owner prepared action and pinned source evidence required')
    adopted=a.document(root,prepared['SYS_adoption']);web_report=a.document(root,prepared['WEB_original_result'])
    need(adopted.get('schema')=='system-development-actual-clean-causal-derivation-result/v1'
         and adopted.get('task_id')==ctx['task'] and adopted.get('status')=='installed_and_normal_request_base_diagnostic_pass'
         and adopted.get('original_source_mutated') is False and adopted.get('new_source_event_registered') is False
         and same(root,adopted.get('producer_report'),prepared['WEB_original_result'])
         and web_report.get('task_id')==ctx['task'] and web_report.get('scope')==ctx['scope']
         and web_report.get('owner')==ctx['owner'] and web_report.get('WEB_executor')==ctx['role'],
         'same actual SYS result and original WEB owner source required')
    source=a.document(root,local(adopted['producer_source']));native_meta=adopted.get('real_WEB_native',{})
    need(source.get('schema')=='WEB-exact-clean-causal-successor-source-input/v1'
         and source.get('task_id')==ctx['task'] and source.get('scope')==ctx['scope']
         and native_meta.get('thread_id')==ctx['binding']['thread_id']
         and native_meta.get('actual_status')=='completed' and bool(native_meta.get('turn_id'))
         and source.get('parent_event')==adopted.get('original_source_event'),
         'original WEB source and real prior event identity required')
    parents=[x for x in inc.sources(root,ctx) if x.get('increment_event_id')==source['parent_event']
             and same(root,x.get('increment_registration'),source.get('parent_adopted_source'))]
    need(len(parents)==1,'one fully revalidated original parent source and committed event required')
    parent=parents[0];state=a.document(root,local(source['actual_state']));meta=source['actual_local_successor']
    need(state.get('candidate_commit')==meta.get('head')==adopted.get('git',{}).get('head')
         and state.get('candidate_base')==meta.get('base') and state.get('candidate_parents')==meta.get('parents')
         and state.get('candidate_tree')==meta.get('tree') and state.get('repository')==ctx['repository']
         and state.get('actor',{}).get('id')==ctx['actor_id'],
         'same real historical Git state, repository and original actor required')
    _clean_custody_history(parent,state)
    journal=a.document(root,local(adopted['cas_journal']));installed=adopted.get('installed',[])
    need(journal.get('state')=='installed' and journal.get('inverse_backup_hash_verified') is True
         and len(installed)==2, 'actual original CAS journal required')
    for pin in installed:
        rows=[x for x in journal.get('changes',[]) if x.get('path')==w.rel_path(root,Path(pin['path']))
              and x.get('after')==pin['sha256']]
        need(len(rows)==1 and w.file_digest(root,rows[0]['candidate'])['sha256']==pin['sha256']
             and w.file_digest(root,rows[0]['backup'])['sha256']==rows[0]['before'],
             'immutable applied candidate and inverse backup must match original CAS history')
    diagnostic=a.document(root,local(adopted['installed_diagnostic']))
    need(diagnostic.get('status')=='pass' and diagnostic.get('head')==state['candidate_commit']
         and diagnostic.get('historical_state_only') is True and diagnostic.get('policy_issued') is False
         and diagnostic.get('external_action') is False,'real source diagnostic only, not a production effect')
    payload=action['payload'];need(w.file_digest(root,payload.get('path',''))==payload
         and action.get('payload_sha256')==payload['sha256'],'exact original action payload bytes required')
    text=w.safe_path(root,payload['path']).read_text()
    need(all(re.search(r'(?m)^'+key+'='+re.escape(str(action[key]))+r'\s*$',text)
             for key in ('task_id','scope','action_id','sender_department','target_department'))
         and all(prepared[k]['sha256'] in text for k in ('SYS_adoption','WEB_original_result','original_owner_source')),
         'actual source-bearing original body required')
    if not any(x.get('action_id')==action['action_id'] for x in snapshot['goal_delivery'].get('approved_actions',[])):
        a._owner_message_transport_not_started(root,snapshot,action)
    return True


def _successor_owner_message(root, snapshot, action, wrapper, ctx):
    """An actual owner result may carry an already committed source dependency.

    This supplements transport only. The original current human, release source
    and all execution stages are still validated by current()/normal consumers.
    """
    import re
    from professional_web_increment import ORD_EVENT
    goal = snapshot['goal_delivery']; owner = ctx['owner']
    need(isinstance(wrapper, dict) and wrapper.get('schema') == 'professional-owner-result-message-source/v1'
         and wrapper.get('task_id') == snapshot['task_id'] == ctx['task']
         and wrapper.get('scope') == ctx['scope'] in goal['authorized_scope']
         and wrapper.get('goal_contract') == snapshot['goal_contract']
         and wrapper.get('authorization') == goal['authorization_pin']
         and goal['primary_owner'] == owner and snapshot['current_state'] not in w.TERMINAL_STATES,
         'exact active original owner message source and unchanged authority required')
    need(a.document(root, wrapper.get('original_action')) == action,
         'real immutable owner action, not a caller successor flag')
    stable = set(ctx['exact_owner_action']) - {'action_id', 'payload', 'payload_sha256'}
    need(set(action) == set(ctx['exact_owner_action'])
         and all(action.get(k) == ctx['exact_owner_action'].get(k) for k in stable)
         and action.get('sender_department') == owner and action.get('action_class') == 'thread_message'
         and action.get('scope') == ctx['scope'] and action.get('task_id') == ctx['task']
         and action.get('target_department') == ctx['role'] and action.get('delivery_mode') == 'official_native_queue'
         and action.get('assignment_record_required') is False
         and action.get('authorization_changes') == action.get('internal_repairs') == []
         and re.fullmatch(r'[A-Za-z0-9_.-]+', action.get('action_id', '')),
         'same exact original WEB/owner/projects/transport only; no new role or production action')
    result = a.document(root, wrapper.get('professional_result_request'))
    a.native_result(root, result, w.department_registry(root)[owner]['chat_binding']['task_id'])
    report = a.document(root, w.file_digest(root, result['outbox_path']))
    prepared_pin = report.get('primary_deliverable'); prepared = a.document(root, prepared_pin)
    if 'SYS_adoption' in prepared:
        need(result.get('task_id') == report.get('task_id') == prepared.get('task_id') == ctx['task']
             and result.get('sender_department') == report.get('primary_owner') == report.get('department') == owner
             and report.get('scope') == prepared.get('scope') == ctx['scope']
             and report.get('delivery_model') == a.MODE and report.get('production_READY') is False
             and prepared_pin in report.get('evidence', []), 'exact real original professional owner result required')
        if _derived_custody_owner_message(root,snapshot,action,wrapper,ctx,result,report,prepared):
            return
    need(result.get('task_id') == report.get('task_id') == prepared.get('task_id') == ctx['task']
         and result.get('sender_department') == report.get('primary_owner') == report.get('department') == owner
         and report.get('scope') == prepared.get('scope') == ctx['scope']
         and report.get('delivery_model') == a.MODE and report.get('production_READY') is False
         and prepared_pin in report.get('evidence', [])
         and wrapper['original_action'] == prepared.get('action') in report['evidence']
         and prepared.get('body') == action.get('payload') in report['evidence']
         and prepared.get('actual_sent') is False,
         'complete genuine professional result binds this dependency body/action; never infer a send')
    if 'material_rebase_request_base' in prepared:
        _material_rebase_owner_continuation(root, snapshot, action, ctx, report, prepared)
        return
    verified_pin = prepared.get('adoption_verified'); verified = a.document(root, verified_pin)
    need(verified_pin in report['evidence'] and prepared.get('source_event') == verified.get('source_event'),
         'same original professional adopted-source observation required')
    rows = [e for e in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS, where={'task_id': ctx['task']})
            if e.get('event_id') == prepared.get('source_event') and e.get('details', {}).get(ORD_EVENT)]
    need(len(rows) == 1 and not w.validate_workflow_events(root, ctx['task']),
         'one real committed original successor event and intact history, not a proposed source')
    event = rows[0]; source_pin = event['details'][ORD_EVENT]; source = a.document(root, source_pin)
    need(source_pin in verified.get('pins', []) and source.get('schema') == PEER_SCHEMA
         and source.get('task_id') == ctx['task'] and source.get('scope') == ctx['scope']
         and source.get('original_source_registration') == ctx['registration'],
         'actual adopted peer successor of this exact reviewed release source; no borrowed goal')
    observed = w._parse_observed_at(report.get('reported_at_myt'))
    committed = w._parse_observed_at(event.get('created_at'))
    need(observed is not None and committed is not None and committed <= observed <= dt.datetime.now(dt.timezone.utc),
         'source must really be committed before the original professional report')
    payload = action['payload']; need(w.file_digest(root, payload.get('path', '')) == payload
         and action['payload_sha256'] == payload['sha256'], 'unchanged exact successor body bytes')
    text = w.safe_path(root, payload['path']).read_text()
    need(all(re.search(r'(?m)^' + key + '=' + re.escape(str(action[key])) + r'\s*$', text)
             for key in ('task_id', 'scope', 'action_id', 'sender_department', 'target_department'))
         and Path(source_pin['path']).name in text and source_pin['sha256'] in text and event['event_id'] in text,
         'exact body must carry its actual adopted source and event, not generic continuation metadata')
    # Registration cannot outrun a previously unknown/sent transport. Once the
    # exact source is registered, ordinary policy/queue/readback guards own it.
    registered = [x for x in goal.get('approved_actions', []) if x.get('action_id') == action['action_id']]
    if not registered:
        a._owner_message_transport_not_started(root, snapshot, action)


def _material_rebase_owner_continuation(root, snapshot, action, ctx, report, prepared):
    """Transport a verified rebase back to the already bound material WEB."""
    import professional_web_execution as web
    from paid_three_page_bounded_cms import MATERIAL_PUBLICATION_TASK
    from professional_web_increment import select

    keys = ('material_rebase_request_base', 'original_C36_result_receipt')
    need(ctx['task'] == MATERIAL_PUBLICATION_TASK
         and all(prepared.get(key) in report['evidence'] for key in keys),
         'exact original material owner result and both continuation evidence pins required')
    request = a.document(root, prepared[keys[0]])
    receipt_pin = prepared[keys[1]]
    receipt = a.document(root, receipt_pin)
    source = a.document(root, request['state']['material_reviewed_rebase_source'])
    producer_report = a.document(root, source['report'])
    original_action = receipt.get('action_id')
    registered = [row for row in snapshot['goal_delivery'].get('approved_actions', [])
                  if row.get('action_id') == original_action and row.get('professional_owner_message_source')
                  and row.get('sender_department') == ctx['owner'] and row.get('target_department') == ctx['role']
                  and row.get('scope') == ctx['scope']]
    need(receipt_pin in snapshot['goal_delivery'].get('collaboration_records', [])
         and receipt.get('source_kind') == 'official_native_queue'
         and receipt.get('status') == 'result_received'
         and receipt.get('task_id') == ctx['task'] and receipt.get('scope') == ctx['scope']
         and len(registered) == 1 and original_action == producer_report.get('action_id')
         and receipt.get('target_thread_id') == ctx['binding']['thread_id']
         and receipt.get('result') == source['report'],
         'same formally received original WEB result and its registered owner action required')
    events = w.read_jsonl(Path(root) / w.WORKFLOW_EVENTS, where={
        'task_id': ctx['task'], ('details', 'collaboration_receipt'): receipt_pin,
        ('details', 'actual_transport_status'): 'result_received',
    })
    need(len(events) == 1 and events[0].get('details', {}).get('external_permission_issued') is False,
         'one actual original result intake event required')
    state = request['state']
    need(not any(key in state for key in ('hq_singlefield_code_stage_source',
             'hq_singlefield_test_successor_source', 'code_only_source_registration')),
         'only the original material continuation source can be transported')
    # The caller already authenticated the original material catalog and
    # reviewed release. Reuse that context and validate the exact increment.
    selected = select(root, ctx, state)
    web._static_intent_context(root, request, selected)
    need(request.get('operation') == 'git_push' and request.get('task_id') == ctx['task']
         and selected.get('increment_registration') == request['state']['material_reviewed_rebase_source']
         and request.get('action_id') == web.action_id(selected, 'git_push', selected['commit'], None),
         'exact normal material rebase request identity required; transport only')
    text = w.safe_path(root, action['payload']['path']).read_text()
    need(all(prepared[key]['sha256'] in text for key in keys),
         'actual owner continuation body must name both immutable sources')
    if not any(x.get('action_id') == action['action_id'] for x in snapshot['goal_delivery'].get('approved_actions', [])):
        a._owner_message_transport_not_started(root, snapshot, action)


def message_binding(root, snapshot, action, message_source=None):
    from professional_cms_channel import original_body_records
    sources = original_body_records(root, snapshot['task_id'])
    if not sources:
        return None
    need(len(sources) == 1, 'unique original external custody')
    ctx = current(root, snapshot, sources[0])
    if not ctx.get('current_owner_reviewed_release'):
        return None
    if action != ctx['exact_owner_action']:
        _successor_owner_message(root, snapshot, action, message_source, ctx)
    return {**ctx['binding'], 'task_id': ctx['binding']['thread_id']}


PEER_SCHEMA = 'current-owner-reviewed-WEB-peer-successor/v1'


def _peer_resolution(path, ancestor, left, right, combined):
    """Recognize source-derived registration unions or an additive count assertion."""
    import re
    from original_production_delivery import _additive_registration_hunk
    if path.endswith('.test.ts'):
        pattern = r'(\s*expect\([A-Za-z_$][\w$]*\)\.toHaveLength\()(\d+)(\);)(?: //[^\r\n]*)?\n'
        parts = [re.fullmatch(pattern, value) for value in (left, right, combined)]
        need(all(parts) and len({p[1] for p in parts}) == len({p[3] for p in parts}) == 1,
             'only the same literal registry length assertion may combine')
        old = re.findall(re.escape(parts[0][1]) + r'(\d+)' + re.escape(parts[0][3]), ancestor)
        need(len(old) == 1 and int(parts[0][2]) > int(old[0]) and int(parts[1][2]) > int(old[0])
             and int(parts[2][2]) == int(parts[0][2]) + int(parts[1][2]) - int(old[0]),
             'registry count is the two original positive increments, not a caller count')
        return
    imports = r'(?:import \{ [A-Za-z0-9_$, ]+ \} from "[A-Za-z0-9_./-]+";\n)+'
    if path.endswith('.ts') and all(re.fullmatch(imports, x) for x in (left, right, combined)):
        rows = [x.splitlines(True) for x in (left, right, combined)]
        need(all(len(set(x)) == len(x) for x in rows) and set(rows[2]) == set(rows[0]) | set(rows[1])
             and all([x for x in rows[2] if x in values] == values for values in rows[:2]),
             'only the two original ordered imports may combine')
        return
    need(path.endswith(('.yml', '.yaml', '.mjs')), 'unsupported source conflict kind')
    _additive_registration_hunk(left, right, combined)


def _peer_bytes(root, base, meta):
    """Reconstruct whole files from both real parents without changing the website."""
    import hashlib
    import re
    import subprocess
    import tempfile
    import professional_web_execution as web
    head, later = meta['head'], meta['base']; ctx = {**base, 'worktree': meta['worktree']}
    need(len(base['source_components']) == 1, 'one original reviewed source component')
    component = base['source_components'][0]
    need(component['head'] == base['commit'] and set(component['paths']) == set(base['paths']),
         'complete original contribution set')
    def blob(commit, path):
        try:
            return web.git(ctx, 'show', commit + ':' + path)
        except w.WorkflowError:
            return b''
    scratch = Path(root)/'logs/professional-CMS-channel-source-checks'; scratch.mkdir(parents=True, exist_ok=True)
    conflicts = []; paths = {}
    with tempfile.TemporaryDirectory(dir=scratch) as folder:
        folder = Path(folder)
        for row in meta['files']:
            path = row['path']; actual = blob(head, path)
            need(hashlib.sha256(actual).hexdigest() == row['sha256'] and len(actual) == row['size']
                 and web.git(ctx, 'rev-parse', head + ':' + path).decode().strip() == row['blob'],
                 'exact actual candidate blob/size/Git identity')
            modes = [web.git(ctx, 'ls-tree', c, '--', path).split()[:1] for c in (head, component['head'], later)]
            need(modes[0] == modes[1] == [row['mode'].encode()] and (not modes[2] or modes[2] == modes[0]),
                 'both original and current peer file modes must survive')
            ancestor, current, own = [blob(c, path) for c in (component['base'], later, component['head'])]
            for label, raw in [('current', current), ('ancestor', ancestor), ('own', own)]:
                (folder/label).write_bytes(raw)
            merged = subprocess.run(['git', 'merge-file', '-p', str(folder/'current'), str(folder/'ancestor'), str(folder/'own')], capture_output=True)
            if merged.returncode == 0:
                need(merged.stdout == actual, 'all non-conflicting source bytes must survive')
            else:
                need(merged.returncode == 1, 'one supported actual conflict per original path')
                pattern = rb'^<<<<<<<[^\n]*\n(.*?)^=======\n(.*?)^>>>>>>>[^\n]*\n'
                matches = list(re.finditer(pattern, merged.stdout, re.M | re.S))
                need(len(matches) == 1, 'one bounded actual paired conflict block')
                match = matches[0]; prefix, suffix = merged.stdout[:match.start()], merged.stdout[match.end():]
                need(actual.startswith(prefix) and actual.endswith(suffix) and len(actual) >= len(prefix)+len(suffix),
                     'no candidate edit outside the exact conflicting hunk')
                combined = actual[len(prefix):len(actual)-len(suffix) if suffix else None]
                _peer_resolution(path, ancestor.decode(), match[1].decode(), match[2].decode(), combined.decode())
                conflicts.append(path)
            paths[path] = row['sha256']
    need(set(conflicts) == set(meta['conflict_paths']) and len(conflicts) == len(meta['conflict_paths']),
         'all and only actual declared conflicts')
    return paths


def peer_successor(root, base, item):
    """An exact source successor under the already authenticated current human/HQ."""
    import hashlib
    import io
    import tarfile
    import re
    import professional_web_execution as web
    from original_production_delivery import _source_pin
    keys = {'schema','task_id','scope','original_source_registration','producer_native','report',
            'metadata','facts_command','failed_command','test_command'}
    need(set(item) == keys and item['schema'] == PEER_SCHEMA and base.get('current_owner_reviewed_release')
         and item['task_id'] == base['task'] and item['scope'] == base['scope']
         and same(root, item['original_source_registration'], base['registration']),
         'same actual current human/HQ reviewed source/task/scope, never a new permission')
    report = json.loads(_source_pin(root, item['report'], base['binding']))
    meta = json.loads(_source_pin(root, item['metadata'], base['binding']))
    need(report.get('task_id') == base['task'] and report.get('scope') == base['scope']
         and report.get('new_source_authority', {}).get('current_source') == base['registration']
         and report.get('actual_local_successor') == meta
         and meta.get('worktree') == base['worktree'] and meta.get('branch') == base['branch']
         and meta.get('parents') == [base['commit'], meta.get('base')]
         and set(x['path'] for x in meta['files']) == set(base['paths'])
         and len(meta['files']) == len(base['paths']) and meta.get('clean') is True,
         'original WEB exact report, actual parents/branch/worktree and unchanged path set')
    meta = {**meta, 'conflict_paths': report['four_peer_overlap_files']}
    need(all(re.fullmatch('[0-9a-f]{40}', str(meta.get(k))) for k in ('head','base','tree')),
         'real full immutable Git version only')
    need(web.git(base,'show','-s','--format=%H %P %T',meta['head']).decode().strip()
         == ' '.join([meta['head'], *meta['parents'], meta['tree']])
         and web.git(base,'merge-base',base['base'],meta['base']).decode().strip() == base['base']
         and set(web.git(base,'diff','--name-only',meta['base'],meta['head']).decode().splitlines()) == set(base['paths']),
         'real Git lineage/tree and original cumulative scope only')
    facts = web.native(root,base,item['producer_native'],item['facts_command']).decode()
    decoder = json.JSONDecoder(); found = []
    for match in re.finditer(r'\{"head"\s*:', facts):
        try: value, _ = decoder.raw_decode(facts[match.start():]); found.append(value)
        except ValueError: continue
    need(len(found) == 1 and all(found[0].get(k) == meta.get(k) for k in ('head','parents','base','tree'))
         and set(found[0].get('paths', [])) == set(base['paths'])
         and set(found[0].get('four_exact_conflict_resolutions', [])) == set(meta['conflict_paths']),
         'actual completed original WEB fact call binds this real version and conflicts')
    failed = json.loads(web.native(root,base,item['producer_native'],item['failed_command']))
    captured = json.loads(_source_pin(root, report['normal_gate']['request_base'], base['binding']))
    need(failed == captured and failed.get('exit_code') == 1 and failed.get('stdout') == ''
         and 'each original source contribution and file mode must survive' in failed.get('stderr', '')
         and failed.get('output_exists') is False,
         'real failed request-base wrapper, never a fabricated successful intent')
    argv = failed.get('argv', []); request = json.loads(_source_pin(root,report['normal_gate']['actual_input'],base['binding']))
    need(len(argv) == 12 and argv[1:5] == ['-B',str(Path(root)/'tools/professional_web_execution.py'),'request-base','--task-id']
         and argv[5:10] == [base['task'],'--operation','git_push','--state',failed['input_state']]
         and argv[10] == '--output' and request['candidate_commit'] == meta['head']
         and request['candidate_base'] == meta['base'] and request['candidate_parents'] == meta['parents']
         and request['candidate_tree'] == meta['tree'] and request['actor']['id'] == base['actor_id']
         and request['repository'] == base['repository'], 'canonical original argv/request/actor and version')
    tests = web.native(root,base,item['producer_native'],item['test_command'])
    passed = report['validation']['new_successor_affected_tests']
    need(passed['native_command'] == item['test_command'] and passed['exit'] == 0
         and re.search(rb'Tests\s+'+str(passed['passed']).encode()+rb' passed', tests),
         'actual original completed affected tests, not SYS-signed production selfcheck')
    paths = _peer_bytes(root,base,meta)
    for key, left, right in [('forward',meta['base'],meta['head']),('inverse',meta['head'],meta['base'])]:
        need(web._patch_effect(web._patch_delta(_source_pin(root,meta[key],base['binding'])))
             == web._patch_effect(web._patch_delta(web.git(base,'diff','--no-ext-diff','--binary','--full-index',left,right))),
             'exact current own source-only forward and reverse bytes')
    archive = _source_pin(root,meta['source_archive'],base['binding'])
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        files = [m for m in tar.getmembers() if m.isfile()]
        need(len(files) == len(paths) and {m.name for m in files} == set(paths)
             and all((m.isfile() or m.isdir()) and not m.issym() and not m.islnk() for m in tar.getmembers()),
             'complete exact nine-path source archive, not a Functions restore claim')
        need(all(hashlib.sha256(tar.extractfile(m).read()).hexdigest() == paths[m.name] for m in files),
             'every archived source blob equals the actual candidate')
    component = {'head':meta['head'],'base':meta['base'],'paths':paths}
    return {**base,'commit':meta['head'],'base':meta['base'],'tree':meta['tree'],'paths':paths,
            'git_parent':meta['parents'][0],'git_parents':meta['parents'],'ordinary_increment':True,
            'reviewed_peer_successor':item,'original_peer_overlap_source':item,
            'increment_actor_id':base['actor_id'],'increment_allowed_operations':sorted(web.OPS),
            'increment_source_mode':'current_reviewed_exact_peer_successor',
            'source_components':[component], 'increment_forward_patch':meta['forward'],
            'increment_inverse_patch':meta['inverse']}


def peer_candidate(ctx, state):
    need(state.get('candidate_commit') == ctx['commit'] and state.get('candidate_base',ctx['base']) == ctx['base']
         and state.get('candidate_parent') == ctx['git_parent'] and state.get('candidate_parents') == ctx['git_parents']
         and state.get('candidate_tree') == ctx['tree'] and state.get('source_mode','forward') == 'forward',
         'only this exact authenticated peer successor, real full parents/tree; no inverse or future head')
    return ctx['commit'], ctx['base']

CLEAN_SCHEMA = 'current-owner-reviewed-WEB-clean-successor/v1'


def _clean_git(parent, meta, files):
    """A clean merge preserves every own blob/mode and all later-base peers."""
    import hashlib
    import re
    import professional_web_execution as web
    need(all(re.fullmatch('[0-9a-f]{40}', str(meta.get(k))) for k in ('head', 'base', 'tree'))
         and meta.get('parents') == [parent['commit'], meta['base']]
         and meta['base'] != parent['base'] and meta.get('clean') is True
         and meta.get('worktree') == parent['worktree'] and meta.get('branch') == parent['branch'],
         'exact clean two-parent causal source and original worktree')
    own = set(parent['paths']); peers = meta.get('peer_paths_preserved', [])
    need(len(meta.get('own_paths', [])) == len(own) and set(meta['own_paths']) == own
         and len(files) == len(own) and {f['path'] for f in files} == own
         and peers and len(peers) == len(set(peers)) and not own.intersection(peers),
         'all original contributions and only disjoint real peer paths')
    def paths(left, right):
        return set(web.git(parent, 'diff', '--name-only', left, right).decode().splitlines())
    need(web.git(parent, 'show', '-s', '--format=%H %P %T', meta['head']).decode().strip()
         == ' '.join([meta['head'], *meta['parents'], meta['tree']])
         and web.git(parent, 'merge-base', parent['base'], meta['base']).decode().strip() == parent['base']
         and paths(meta['base'], meta['head']) == own
         and paths(parent['commit'], meta['head']) == set(peers)
         and paths(parent['base'], meta['base']) == set(peers),
         'actual complete Git tree/parents/base; no new own edit or overlap')
    for row in files:
        path = row['path']; raw = web.git(parent, 'show', meta['head'] + ':' + path)
        entry = web.git(parent, 'ls-tree', meta['head'], '--', path)
        need(entry == web.git(parent, 'ls-tree', parent['commit'], '--', path)
             and entry.split()[:3] == [row['mode'].encode(), b'blob', row['blob'].encode()]
             and row['mode'] in {'100644', '100755'}
             and hashlib.sha256(raw).hexdigest() == row['sha256'] == parent['paths'][path]
             and len(raw) == row['size'], 'every own Git blob/size/mode survives exactly')
    need(all(web.git(parent, 'ls-tree', meta['head'], '--', p)
             == web.git(parent, 'ls-tree', meta['base'], '--', p) for p in peers),
         'all peer bytes and modes equal their actual later base')
    return dict(parent['paths'])


def clean_successor(root, base, parent, item):
    """Admit a pinned, actually received WEB result, never arbitrary descendants."""
    import hashlib
    import io
    import tarfile
    import goal_delivery_runtime as g
    import professional_web_execution as web
    from original_production_delivery import _source_pin
    keys = {'schema', 'task_id', 'scope', 'parent_increment_source', 'report',
            'frozen_manifest', 'owner_result_receipt', 'native_custody'}
    need(set(item) == keys and item['schema'] == CLEAN_SCHEMA
         and item['task_id'] == base['task'] == parent['task']
         and item['scope'] == base['scope'] == parent['scope']
         and base.get('current_owner_reviewed_release') and parent.get('reviewed_peer_successor')
         and same(root, item['parent_increment_source'], parent['increment_registration'])
         and same(root, parent['registration'], base['registration']),
         'original registered reviewed parent and unchanged human/HQ/task/scope')
    report = a.document(root, item['report']); frozen = a.document(root, item['frozen_manifest'])
    receipt = a.document(root, item['owner_result_receipt'])
    snap = g.restore_goal(root, w.read_json(w.snapshot_path(root, base['task'])))
    states = g._collaboration_wait_states(root, snap, only_action_id=receipt.get('action_id'))
    matched = [s for s in states if s.get('status') == 'result_received' and s.get('proof_state') == 'PROVEN'
               and same(root, s.get('result_receipt'), item['owner_result_receipt'])
               and same(root, s.get('result'), item['report'])]
    need(len(matched) == 1 and receipt.get('task_id') == base['task']
         and receipt.get('scope') == base['scope'] and receipt.get('target_thread_id') == base['binding']['thread_id']
         and receipt.get('source_kind') == 'official_native_queue'
         and report.get('task_id') == base['task'] and report.get('scope') == base['scope']
         and report.get('action_id') == receipt.get('action_id'),
         'one real original WEB result with complete normal durable receipt lineage')
    pins = frozen.get('pins', [])
    reports = [p for p in pins if all(p.get(k) == item['report'].get(k) for k in ('sha256', 'size'))]
    need(frozen.get('schema') == 'frozen-exact-pins/v1' and len(reports) == 1
         and _source_pin(root, reports[0], base['binding']) == _source_pin(root, item['report'], base['binding']),
         'immutable original WEB frozen report and exact custody copy, not caller metadata')
    def pinned_path(path):
        rows = [p for p in pins if p.get('path') == path]
        need(len(rows) == 1, 'one actual frozen original source path')
        return rows[0]
    custody = a.document(root, item['native_custody']); original = pinned_path(report['native']['path'])
    need(custody.get('origin') == original and custody.get('modified_native_status') is False
         and _source_pin(root, original, base['binding']) == _source_pin(root, custody['exact_byte_copy'], base['binding']),
         'unmodified original native bytes; never rewrite turn completion')
    old = g._native_document(root, custody['exact_byte_copy'])
    completed = g._native_document(root, receipt['actual_native_result'])
    native = report['native']; turn_id = native['turn_id']
    turns = [[t for t in page.get('turns', []) if t.get('id') == turn_id] for page in (old, completed)]
    need(all(len(t) == 1 for t in turns) and turns[1][0].get('status') == 'completed'
         and not turns[1][0].get('error') and receipt.get('recipient_turn_id') == turn_id
         and all(all(page.get('thread', {}).get(k) == base['binding'][v]
                     for k, v in {'id':'thread_id', 'title':'title', 'cwd':'cwd', 'hostId':'host_id'}.items())
                 for page in (old, completed)),
         'real later same original WEB completed turn; earlier status remains historical')
    outputs = {}
    for key in ('merge_command', 'facts_command', 'refusal_wrapper_command'):
        cid = native[key]
        calls = [[c for c in t[0].get('items', []) if c.get('id') == cid] for t in turns]
        need(all(len(c) == 1 for c in calls)
             and all(calls[0][0].get(k) == calls[1][0].get(k)
                     for k in ('id', 'type', 'status', 'exitCode', 'cwd', 'command'))
             and calls[0][0].get('output', {}).get('truncated') is False,
             'same actual completed original command and untruncated historical output')
        outputs[key] = json.loads(web.native(root, parent, custody['exact_byte_copy'], cid))
    meta = report['actual_local_successor']
    need(outputs['merge_command'] == meta, 'real completed merge command binds exact candidate')
    paths = _clean_git(parent, meta, report['actual_nine_blobs'])
    failed = outputs['refusal_wrapper_command']; argv = failed.get('argv', [])
    need(failed == report['new_refusal'] and failed.get('exit_code') == 1
         and failed.get('stdout') == '' and failed.get('output_exists') is False
         and 'each original source contribution and file mode must survive' in failed.get('stderr', '')
         and len(argv) == 12 and argv[1:5] == ['-B', str(Path(root)/'tools/professional_web_execution.py'), 'request-base', '--task-id']
         and argv[5:9] == [base['task'], '--operation', 'git_push', '--state'] and argv[10] == '--output'
         and failed.get('cwd') == parent['worktree'], 'genuine canonical failed request, no invented intent')
    state = json.loads(_source_pin(root, pinned_path(argv[9]), base['binding']))
    need(outputs['facts_command'].get('state') == state
         and state.get('candidate_commit') == meta['head'] and state.get('candidate_base') == meta['base']
         and state.get('candidate_parents') == meta['parents'] and state.get('candidate_parent') == meta['parents'][0]
         and state.get('candidate_tree') == meta['tree'] and state.get('actor', {}).get('id') == base['actor_id']
         and state.get('repository') == base['repository'], 'actual original native state/account/version')
    patches = {}
    for key, left, right in [('forward', meta['base'], meta['head']), ('inverse', meta['head'], meta['base'])]:
        rows = [p for p in pins if Path(p['path']).name.endswith('-' + key + '.patch')]
        need(len(rows) == 1, 'one frozen exact own source patch per direction')
        patches[key] = rows[0]
        need(web._patch_effect(web._patch_delta(_source_pin(root, rows[0], base['binding'])))
             == web._patch_effect(web._patch_delta(web.git(parent, 'diff', '--no-ext-diff', '--binary', '--full-index', left, right))),
             'exact source forward/inverse patch, never production rollback permission')
    need(report['archive'] in pins, 'original frozen source archive')
    with tarfile.open(fileobj=io.BytesIO(_source_pin(root, report['archive'], base['binding']))) as tar:
        members = tar.getmembers(); files = [m for m in members if m.isfile()]
        need(len(files) == len(paths) and {m.name for m in files} == set(paths)
             and all(m.isfile() or m.isdir() for m in members)
             and all(hashlib.sha256(tar.extractfile(m).read()).hexdigest() == paths[m.name] for m in files),
             'complete exact source archive, no compiled/runtime recovery claim')
    return {**parent, 'commit': meta['head'], 'base': meta['base'], 'tree': meta['tree'],
            'git_parent': meta['parents'][0], 'git_parents': meta['parents'],
            'clean_reviewed_successor': item, 'increment_source_mode': 'current_reviewed_clean_causal_successor',
            'source_components': [{'head': meta['head'], 'base': meta['base'], 'paths': paths}],
            'increment_forward_patch': patches['forward'], 'increment_inverse_patch': patches['inverse']}

REGISTRY_TEST_SCHEMA = 'current-owner-reviewed-WEB-registry-test-successor/v1'


def registry_test_delta(before, after, names):
    """Exact registry expectation repair; no test body/subject/guard removal."""
    import difflib
    import re
    counts = []; added = []
    left = before.splitlines(True); right = after.splitlines(True)
    for tag, i, j, k, l in difflib.SequenceMatcher(a=left, b=right, autojunk=False).get_opcodes():
        if tag == 'equal':
            continue
        old = ''.join(left[i:j]); new = ''.join(right[k:l])
        if tag == 'replace' and j-i == l-k == 1:
            a0 = old.split('//', 1)[0].rstrip(); a1 = new.split('//', 1)[0].rstrip()
            pattern = r'expect\(([A-Za-z_$][\w$]*)\)\.toHaveLength\((\d+)\);'
            pairs = [(a,b) for a in re.finditer(pattern,a0) for b in re.finditer(pattern,a1)
                     if a[1] == b[1] and a0[:a.start()] == a1[:b.start()]
                     and a0[a.end():] == a1[b.end():] and int(b[2]) == int(a[2])+len(names)]
            need(len(pairs) == 1, 'only actual registry count expectation, no changed subject/other assertion')
            a,b = pairs[0]
            declaration = 'const '+a[1]+' = MANAGED_TARGETS.filter((target) => target.contentType !== "translation_patch");'
            need(before.count(declaration) == after.count(declaration) == 1,
                 'exact original historical registry projection remains unchanged')
            counts.append((int(a[2]),int(b[2])))
        elif tag == 'insert' and all(re.fullmatch(r'\s*"[\w.-]+",\s*',line) for line in right[k:l]):
            values = [json.loads(line.strip().rstrip(',')) for line in right[k:l]]
            prefix = ''.join(left[:i]); suffix = ''.join(left[i:])
            anchor = prefix.rfind('.toEqual([')
            need(anchor >= 0 and 'Object.keys(targetConfigs)' in prefix[max(0,anchor-160):anchor]
                 and '].sort());' in suffix and all('"'+name+'"' not in before for name in values),
                 'only missing exact target literal inside original sorted complete registry expectation')
            need(set(values) <= set(names), 'target name must come from unchanged frozen original business source')
            added.extend(values)
        else:
            need(False, 'only registry count/literal addition; no skip/remove/production/test-logic delta')
    need(counts or added, 'real registry expectation delta')
    return counts, added


def registry_test_successor(root, base, parent, item):
    import hashlib,io,re,tarfile
    import goal_delivery_runtime as g
    import professional_web_execution as web
    from original_production_delivery import _source_pin
    keys={'schema','task_id','scope','parent_increment_source','report','typed','frozen_manifest',
          'owner_result_receipt','native_custody','candidate_command','checks_command'}
    need(set(item)==keys and item['schema']==REGISTRY_TEST_SCHEMA
         and item['task_id']==base['task']==parent['task'] and item['scope']==base['scope']==parent['scope']
         and base.get('current_owner_reviewed_release') and parent.get('clean_reviewed_successor')
         and same(root,item['parent_increment_source'],parent['increment_registration'])
         and same(root,parent['registration'],base['registration']), 'unchanged original reviewed authority and registered clean parent')
    report=a.document(root,item['report']);typed=a.document(root,item['typed']);frozen=a.document(root,item['frozen_manifest'])
    receipt=a.document(root,item['owner_result_receipt']);snapshot=g.restore_goal(root,w.read_json(w.snapshot_path(root,base['task'])))
    states=g._collaboration_wait_states(root,snapshot,only_action_id=receipt.get('action_id'))
    matched=[s for s in states if s.get('status')=='result_received' and s.get('proof_state')=='PROVEN'
             and same(root,s.get('result_receipt'),item['owner_result_receipt']) and same(root,s.get('result'),item['report'])]
    need(len(matched)==1 and receipt.get('task_id')==base['task'] and receipt.get('scope')==base['scope']
         and receipt.get('target_thread_id')==base['binding']['thread_id'] and receipt.get('source_kind')=='official_native_queue'
         and all(v.get('task_id')==base['task'] and v.get('scope')==base['scope'] for v in (report,typed))
         and report.get('in_reply_to_action_id')==receipt['action_id'], 'actual original WEB result received on its durable normal owner route')
    pins=frozen.get('pins',[])
    need(frozen.get('schema')=='frozen-exact-core-evidence-pins/v2' and pins
         and len({p['path']for p in pins})==len(pins),'complete unique original immutable core manifest')
    for p in pins:_source_pin(root,p,base['binding'])
    for pin in (item['report'],item['typed']):
        hits=[p for p in pins if p['sha256']==pin['sha256'] and p['size']==pin['size']]
        need(len(hits)==1 and _source_pin(root,hits[0],base['binding'])==_source_pin(root,pin,base['binding']),
             'original WEB bytes and unchanged owner custody agree')
    need(report.get('local_successor')==typed.get('candidate')
         and _source_pin(root,report['local_successor_owner_input'],base['binding'])==_source_pin(root,item['typed'],base['binding']),
         'same actual full WEB result and exact typed local successor')
    custody=a.document(root,item['native_custody']);original=typed['native']['snapshot']
    need(custody.get('origin')==original and custody.get('modified_native_status')is False
         and original in pins and _source_pin(root,original,base['binding'])==_source_pin(root,custody['exact_byte_copy'],base['binding']),
         'unmodified original command snapshot, not rewritten completion')
    native_item={'original_native_custody':custody['exact_byte_copy'],'actual_completed_native':receipt['actual_native_result']}
    from professional_web_increment import ordinary_native
    meta=json.loads(ordinary_native(root,base,native_item,item['candidate_command']))
    need(meta==typed['candidate'] and typed['native']['thread_id']==base['binding']['thread_id']
         and typed['native']['turn_id']==receipt['recipient_turn_id'], 'real same completed WEB command binds full candidate')
    checks=[json.loads(line)for line in ordinary_native(root,base,native_item,item['checks_command']).splitlines()if line.strip()]
    need(checks==typed['local_checks'] and len(checks)>=2 and all(x.get('exit_code')==0 and x.get('cwd')==parent['worktree']for x in checks)
         and any(x['argv'][:3]==['npm','test','--']and set(x['argv'][3:])==set(meta['new_delta_paths']) for x in checks),
         'actual original producer affected test/check outputs; local Node is not official CI')
    ctx={**parent,'commit':meta['head'],'git_parent':parent['commit'],'git_parents':[parent['commit']], 'tree':meta['tree']}
    need(meta['parents']==[parent['commit']] and meta['base']==parent['base'] and meta['clean']is True
         and meta['worktree']==parent['worktree'] and meta['branch']==parent['branch']
         and web.git(ctx,'show','-s','--format=%H %P %T',meta['head']).decode().strip()==' '.join([meta['head'],parent['commit'],meta['tree']]),
         'real single parent/tree and unchanged cumulative base/worktree/branch')
    paths=set(web.git(ctx,'diff','--name-only',parent['commit'],meta['head']).decode().splitlines())
    need(paths and paths.isdisjoint(parent['paths']) and paths==set(meta['new_delta_paths'])
         and all(re.fullmatch(r'src/[\w/.-]+\.test\.tsx?',p)for p in paths)
         and set(meta['cumulative_paths'])==set(parent['paths'])|paths
         ==set(web.git(ctx,'diff','--name-only',parent['base'],meta['head']).decode().splitlines()),
         'only precise existing test delta; exact cumulative original scope')
    blobs=meta['blobs'];need(len(blobs)==len(parent['paths'])+len(paths) and len({x['path']for x in blobs})==len(blobs),'complete actual cumulative blobs and modes')
    names=[]
    for p in parent['paths']:
        if not p.endswith('.json'):continue
        try:value=json.loads(web.git(ctx,'show',parent['commit']+':'+p))
        except (ValueError,UnicodeDecodeError):continue
        if value.get('task_id')==base['task'] and value.get('business_scope')==base['scope']:
            names += [row['cli_namespace']for row in value.get('entries',[])if isinstance(row.get('cli_namespace'),str)]
    need(names and len(names)==len(set(names)), 'target namespace derived from original unchanged frozen business source')
    counts=[];added=[];outpaths={}
    for row in blobs:
        p=row['path'];raw=web.git(ctx,'show',meta['head']+':'+p);entry=web.git(ctx,'ls-tree',meta['head'],'--',p).split()
        need(hashlib.sha256(raw).hexdigest()==row['sha256'] and len(raw)==row['size'] and entry[:3]==[row['mode'].encode(),b'blob',row['blob'].encode()]
             and row['mode'].encode()==web.git(ctx,'ls-tree',parent['commit'],'--',p).split()[0], 'every real cumulative source blob/mode exact')
        outpaths[p]=row['sha256']
        if p in parent['paths']:need(row['sha256']==parent['paths'][p], 'original production source bytes remain unchanged')
        else:
            c,n=registry_test_delta(web.git(ctx,'show',parent['commit']+':'+p).decode(),raw.decode(),names);counts+=c;added+=n
    need(counts and len(set(counts))==1 and sorted(added)==sorted(names), 'all exact count fixes agree with only missing original namespaces')
    cause=typed['actual_CI_cause'];pr=typed['existing_PR'];official=cause['official_checks']
    need(cause['source_head']==parent['commit'] and pr==report['actual_PR'] and pr['head_sha']==parent['commit'] and pr['merged']is False
         and {x['name']for x in official}==web.CHECKS and len(official)==len(web.CHECKS)
         and all(x['head_sha']==parent['commit'] and x['status']=='completed'for x in official)
         and any(x['conclusion']=='failure'for x in official), 'real predecessor PR/official failure, not new-head CI or production R3')
    log=re.sub(r'\x1b\[[0-9;]*m','',_source_pin(root,cause['Interaction_full_log_original_HTTP_body'],base['binding']).decode())
    failed=set(re.findall(r'FAIL\s+(src/[^\s]+\.test\.tsx?)',log))
    need(failed==paths and set((int(a),int(b))for a,b in re.findall(r'to have a length of (\d+) but got (\d+)',log))==set(counts),
         'exact official failed paths and observed registry counts; not a caller expected number')
    patches=typed['exact_new_test_delta']
    for key,left,right in [('forward',parent['commit'],meta['head']),('inverse',meta['head'],parent['commit']),('cumulative_forward',meta['base'],meta['head']),('cumulative_inverse',meta['head'],meta['base'])]:
        need(patches[key]in pins and web._patch_effect(web._patch_delta(_source_pin(root,patches[key],base['binding'])))
             ==web._patch_effect(web._patch_delta(web.git(ctx,'diff','--no-ext-diff','--binary','--full-index',left,right))), 'exact incremental/cumulative source patch and inverse')
    with tarfile.open(fileobj=io.BytesIO(_source_pin(root,meta['archive'],base['binding'])))as tar:
        files=[m for m in tar.getmembers()if m.isfile()]
        need(len(files)==len(outpaths)and {m.name for m in files}==set(outpaths)
             and all(m.isfile()or m.isdir()for m in tar.getmembers())
             and all(hashlib.sha256(tar.extractfile(m).read()).hexdigest()==outpaths[m.name]for m in files), 'complete immutable exact cumulative source archive')
    return {**ctx,'paths':outpaths,'existing_pull_number':pr['number'],'registry_test_successor':item,
            'increment_source_mode':'reviewed_registry_expectation_test_successor','increment_forward_patch':patches['cumulative_forward'],
            'increment_inverse_patch':patches['cumulative_inverse']}
