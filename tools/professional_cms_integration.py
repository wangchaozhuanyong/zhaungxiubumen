"""Authenticated standing-holder integration, separate from frozen business ownership.

This registers immutable source facts and narrow messages. It is never a platform
permit, runtime target readiness, a transferred standing grant, or a CMS write.
"""
from pathlib import Path
import datetime as dt
import json
import re
import workflow_control as w

SCHEMA = 'professional-standing-CMS-integration-source/v1'


def _single_row(root, source, carrier, item):
    """Read the immutable single-service codec without rewriting its evidence."""
    import department_autonomy as a
    need = a.require
    pub = a.document(root, source.get('original_PUB_result'))
    row = pub.get('record', {}); diff = pub.get('exact_diff', {})
    action = source.get('exact_action', {}); protection = source.get('protected_fields', {})
    fields = action.get('changed_fields')
    before = a.document(root, source['baseline_only']['complete_row'])
    need(source.get('department') == source.get('integration_owner')
         and source.get('original_business_owner') == source.get('original_content_producer')
         and fields == ['content_en', 'content_zh'] and action.get('table') == 'services'
         and row.get('table') == action['table'] and row.get('id') == action.get('record_id')
         and row.get('slug') == action.get('slug') and row.get('field_count') == len(before) == 41
         and set(row.get('authenticated_complete_fields', [])) == set(before)
         and protection.get('stable_business_fields_count') == 37
         and protection.get('nonwrite_fields_count') == 39 and protection.get('MS_fields_count') == 11
         and protection == pub.get('protected_fields')
         and set(protection.get('MS_fields', [])) == {k for k in before if k.endswith('_ms')}
         and source['baseline_only'].get('raw_updated_at') == row.get('raw_updated_at_CAS') == before.get('updated_at')
         and source['baseline_only'].get('version') == row.get('server_version') == before.get('version')
         and diff.get('changed_fields') == fields and diff.get('all_links_unchanged') is True
         and source.get('new_permission_to_other_role_or_account') is False
         and source.get('new_CMS_Save') is False and source.get('new_deploy_or_account_or_fee') is False
         and source.get('original_parent_closed') is False
         and source.get('baseline_only', {}).get('not_execution_time_CAS') is True,
         'exact single-service two-field readonly codec and protected full41 required')
    original = {'authenticated_full41': row['full41_current_copy'], 'backup_full41': row['full41_backup'],
                'forward_values': diff['candidate_forward_values'],
                'conditional_inverse_values': pub['rollback']['inverse_two_field_values']}
    reverse = source['rollback']
    need(reverse.get('task_id') == action.get('task_id') and reverse.get('action_class') == 'cms_write'
         and reverse.get('changed_fields') == fields and reverse.get('new_inverse_policy_required') is True
         and reverse.get('forward_policy_or_other_task_permit_reuse') is False,
         'own exact two-field inverse requires an independent future inverse policy')
    need(carrier.get('schema') == 'exact-existing-service-CMS-channel-registration-input/v1'
         and carrier.get('existing_CMS_renderer_only') is True
         and carrier.get('actual_runtime_loaded') is False and carrier.get('new_permission_issued') is False
         and carrier.get('normal_source_and_runtime_still_required') is True
         and carrier.get('integration_authority') == source['integration_owner']
         and all(carrier.get(k) == action.get(k) for k in ('table', 'record_id', 'slug'))
         and carrier.get('content_fields') == fields and carrier.get('forward_action') == action
         and carrier.get('inverse_action') == reverse and carrier.get('exact_target_name') == action['candidate_version']
         and carrier.get('forward_values') == original['forward_values']
         and carrier.get('inverse_values') == original['conditional_inverse_values']
         and carrier.get('forward_fields_sha256') == source['desired_fields_sha256']
         and carrier.get('before_fields_sha256') == source['baseline_only']['before_fields_sha256'],
         'unchanged single-row carrier/forward/inverse/digests; no runtime or permit claim')
    record = {'exact_action': action, 'exact_target_name': action['candidate_version'],
              'baseline_only': source['baseline_only'], 'desired': source['desired'],
              'desired_fields_sha256': source['desired_fields_sha256'], 'conditional_inverse': reverse,
              'original_PUB_record': original,
              'protected_fields': {'non_write39': protection['nonwrite_fields'],
                 'protected37': protection['stable_fields'], 'MS11': protection['MS_fields'],
                 'updated_at_version_sent_as_values': False}}
    human = source['human_and_frozen_source']
    normalized = {**source, 'publication_integration_owner': source['integration_owner'],
       'original_goal_contract': human['original_goal_contract'],
       'original_human_authorization': human['original_goal_authorization'],
       'latest_HQ_coordination': item.get('original_coordination_action_id'),
       'current_C1_standing': {'authorization': human['standing_authorization']},
       'original_SEO2_inputs': source['original_candidate'], 'original_PUB_complete_result': source['original_PUB_result'],
       'actual_PUB_completed_turn': item.get('executor_completed_identity', {}),
       'Save_or_permit_or_code_deploy': False, 'production_READY': False, 'record_actions': [record]}
    target = {'name': record['exact_target_name'], 'action': action, 'inverse': reverse,
              'forward_values': original['forward_values'], 'inverse_values': original['conditional_inverse_values'],
              'desired_fields_sha256': source['desired_fields_sha256'],
              'before_fields_sha256': source['baseline_only']['before_fields_sha256']}
    return normalized, {**carrier, 'publication_integration_authority': source['integration_owner'],
            'issuer': carrier['issuer_role'], 'channel_executor': carrier['channel_owner'], 'targets': [target]}, {**pub, 'records': [original]}


def _fixed(page, binding, root):
    import department_autonomy as a
    a.require(all(page.get('thread', {}).get(k) == binding.get(v) for k, v in
                  {'id': 'task_id', 'title': 'title', 'cwd': 'cwd'}.items())
              and binding.get('project_id') == a.PROJECT
              and Path(binding.get('cwd', '')).resolve() == Path(root).resolve(),
              'actual fixed same-project professional native required')


def validate(root, snapshot, item):
    import department_autonomy as a
    import goal_delivery_runtime as g
    import result_coordination as rc
    need = a.require
    frozen = a.document(root, snapshot['goal_contract'])
    goal = a.participant(root, snapshot, frozen['primary_owner'])
    source_pin = item.get('integration_source'); source = a.document(root, source_pin)
    carrier_pin = item.get('target_input'); carrier = a.document(root, carrier_pin)
    single = source.get('schema') == 'C1-standing-original-owner-CMS-integration-source/v1'
    owner = goal['primary_owner']; role = item.get('integration_department')
    need(a.current_mode(root) and item.get('schema') == SCHEMA
         and item.get('task_id') == snapshot['task_id']
         and item.get('goal_contract') == snapshot['goal_contract']
         and item.get('authorization') == goal['authorization_pin']
         and all(goal.get(k) == frozen.get(k) for k in
                 ('primary_owner', 'producer_departments', 'authorized_scope', 'human_authorization',
                  'required_execution_actions', 'collaboration_scopes'))
         and (role in frozen['producer_departments'] or single) and a.professional(root, role),
         'unchanged original owner/producer/contract and actual professional integrator required')
    single_pub = None
    if single:
        source, carrier, single_pub = _single_row(root, source, carrier, item)
    owner_source = source.get('schema')=='C1-standing-original-next12-five-record-CMS-integration-carrier/v1'
    if owner_source:
        need(role==owner and source.get('primary_owner')==owner, 'own complete-result codec cannot delegate another role')
        source={**source,'original_business_owner':source['primary_owner'],'publication_integration_owner':source['department'],
                'Save_or_permit_or_code_deploy':not source['no_new_CMS_Save_preview_permit_policy_consumption_deploy_account_or_fee'],
                'original_PUB_complete_result':source['original_PUB_completed_source'],
                'actual_PUB_completed_turn':{'thread_id':w.department_registry(root)['publishing']['chat_binding']['task_id'],
                  'turn_id':source['actual_completed_PUB_turn'],'final_message_id':item.get('executor_final_message_id')}}
        carrier={**carrier,'original_business_owner':carrier['professional_owner'],
                 'publication_integration_authority':carrier['standing_authority_department'],
                 'execution_source':carrier['source'],'issuer':'publishing','channel_executor':'designated-development'}
    scope = item.get('business_scope')
    need(scope in frozen['authorized_scope'] and source.get('task_id') == snapshot['task_id']
         and source.get('scope') == scope and source.get('department') == role
         and source.get('original_business_owner') == owner
         and source.get('publication_integration_owner') == role
         and source.get('original_goal_contract') == snapshot['goal_contract']
         and source.get('original_human_authorization') == goal['authorization_pin']
         and source.get('Save_or_permit_or_code_deploy') is False
         and source.get('production_READY') is False,
         'exact original integration source; no changed contract, production effect or caller grant')
    registry = w.department_registry(root); fixed = registry[role]['chat_binding']
    hq = registry['operations']['chat_binding']
    native = g._native_document(root, item.get('integration_native')); _fixed(native, fixed, root)
    calls = [(t, c) for t in native.get('turns', []) for c in t.get('items', [])
             if c.get('id') == item.get('source_command_id')]
    need(len(calls) == 1, 'one actual integrator source command required')
    turn, command = calls[0]
    need(turn.get('status') == command.get('status') == 'completed' and not turn.get('error')
         and command.get('type') == 'commandExecution' and command.get('exitCode') == 0
         and Path(command.get('cwd', '')).resolve() == Path(root).resolve(),
         'real completed successful source creation, not a caught inner rejection')
    output = json.loads(w._source_continuation_execution_output(command))
    target_outputs=[output[k] for k in ('exact_target_input','exact_target_carrier') if k in output]
    need(output.get('exact_source') == source_pin and target_outputs and all(p==carrier_pin for p in target_outputs),
         'actual complete native command must bind exact source and target bytes')
    decided = w._parse_observed_at(source.get('decided_at_UTC'))
    need(decided and type(turn.get('startedAt')) in {int, float}
         and type(turn.get('completedAt')) in {int, float}
         and turn['startedAt'] <= decided.timestamp() <= turn['completedAt'] <= dt.datetime.now(dt.timezone.utc).timestamp(),
         'real ordered decision and completed source time required')
    body=''
    if not owner_source:
        invite = g._native_document(root, item.get('coordination_native')); _fixed(invite, hq, root)
        selected = [(t, c) for t in invite.get('turns', []) for c in t.get('items', [])
                    if c.get('id') == item.get('coordination_call_id')]
        need(len(selected) == 1, 'one actual HQ coordination invocation required')
        original, call = selected[0]; body = call.get('arguments', {}).get('prompt', '')
        need(original.get('status') == 'completed' and not original.get('error')
             and call.get('type') == 'mcpToolCall' and call.get('server') == 'codex_app'
             and call.get('tool') == 'send_message_to_thread' and call.get('status') == 'completed'
             and not call.get('error') and not call.get('truncated', False)
             and call.get('arguments', {}).get('threadId') == fixed['task_id']
             and all(re.search(r'(?m)^' + k + '=' + re.escape(str(v)) + r'\s*$', body)
                     for k, v in {'task_id': snapshot['task_id'], 'scope': scope,
                                  'sender_department': 'operations', 'target_department': role,
                                  'action_id': source.get('latest_HQ_coordination')}.items()),
             'real same-task HQ coordination to this original professional, not metadata')
        expected = '<codex_delegation>\n  <source_thread_id>' + hq['task_id'] + '</source_thread_id>\n  <input>' + body + '</input>\n</codex_delegation>'
        received_turn = turn
        if single:
            delivered = g._native_document(root, item.get('delegation_received_native')); _fixed(delivered, fixed, root)
            matching = [t for t in delivered.get('turns', []) if t.get('id') == item.get('delegation_received_turn_id')]
            need(len(matching) == 1, 'one actual original delegated receipt turn required')
            received_turn = matching[0]
            need(received_turn.get('status') == 'completed' and not received_turn.get('error')
                 and type(received_turn.get('completedAt')) in {int, float}
                 and received_turn['completedAt'] <= decided.timestamp(),
                 'original actual delegated ACK precedes later source creation; no backdated current ACK')
        items = received_turn.get('items', [])
        received = [i for i, m in enumerate(items) if
                    (m.get('type') == 'userMessage' and m.get('content') == [{'type': 'text', 'text': body}]) or
                    (m.get('type') == 'functionCallOutput' and m.get('namespace') == 'codex_app'
                     and m.get('name') == 'send_message_to_thread' and m.get('output') == {'text': expected, 'truncated': False})]
        end = len(items) if single else items.index(command)
        need(len(received) == 1 and received[0] < end
             and any(m.get('type') == 'agentMessage' and m.get('text', '').strip()
                     for m in items[received[0]+1:end])
             and original.get('startedAt', float('inf')) <= decided.timestamp(),
             'actual exact delivered coordination and nonempty professional ACK before source creation required')
    standing = source.get('current_C1_standing', {}).get('authorization', {})
    policy = w.read_json(Path(root) / 'data/action-policy.json')
    live = [x for x in policy.get('standing_authorizations', []) if x.get('authorization_id') == item.get('standing_authorization_id')]
    need(len(live) == 1 and live[0] == standing and standing.get('department') == role
         and standing.get('site') == 'company.example' and standing.get('status') == 'active'
         and standing.get('granted_by') == 'owner' and standing.get('valid_until_revoked') is True
         and 'cms_write' in standing.get('action_classes', [])
         and (owner_source or standing['authorization_id'] in body),
         'current own standing must remain active for the exact role/site/action; never transfer it')
    # The completed business source can predate this append. Never rewrite its report.
    identity = rc.exact_identity(item.get('business_result_identity', {}))
    need(identity['task_id'] == snapshot['task_id'] and identity['sender_department'] == owner,
         'actual original business-owner result identity required')
    queued = [q for q in w._result_handoff_rows(root, snapshot['task_id'])
              if q.get('event') == 'notification_queued'
              and w._result_identity(q) == tuple(identity[k] for k in rc.IDENTITY_FIELDS[1:])]
    need(len(queued) == 1 and queued[0].get('target_department') == 'operations', 'one actual business result notification required')
    q = queued[0]; a.native_result(root, q, registry[owner]['chat_binding']['task_id'])
    intake = rc._received_delivery(root, identity, {'target_department': 'operations'})
    need(intake and intake['record_id'] == item.get('business_result_received_record_id'), 'real committed SQL/native original business result required')
    report = a.document(root, q['outbox'])
    content_pins = source['original_C1_content_input'] if owner_source else [source.get('original_SEO2_inputs')]
    for content_pin in content_pins:a.document(root,content_pin)
    evidence = report.get('evidence', [])
    evidence = list(evidence.values()) if isinstance(evidence, dict) else evidence
    if owner_source:
        need(source_pin in evidence and carrier_pin in evidence, 'actual committed own complete result must bind this exact source and carrier')
    elif single:
        request_pin = item.get('original_business_request'); request = a.document(root, request_pin)
        deliveries = report.get('deliveries', [])
        need(request_pin in deliveries and source['original_SEO2_inputs'] in deliveries
             and request.get('task_id') == snapshot['task_id'] and request.get('scope') == scope
             and request.get('professional_owner') == owner
             and request.get('content_candidate') == source['original_SEO2_inputs']
             and request_pin['path'] in body and request_pin['sha256'] in body,
             'actual committed original owner request/candidate and exact HQ request pin required')
    else:
        need(all(p in evidence and p['path']in body and p['sha256']in body for p in content_pins),
             'real business result and HQ coordination must bind the same unchanged content input')
    pub_pin = source.get('original_PUB_complete_result'); pub = single_pub or a.document(root, pub_pin)
    pub_native = g._native_document(root, item.get('executor_completed_native'))
    details = source.get('actual_PUB_completed_turn', {}); executor = pub.get('actual_executor')
    pt, pm = w._completion_actual_final(root, pub_native, executor, turn_id=details.get('turn_id'), message_id=details.get('final_message_id'))
    need(executor == 'publishing' and details.get('thread_id') == registry[executor]['chat_binding']['task_id']
         and pub_pin['path'] in pm['text'] and pub_pin['sha256'] in pm['text']
         and pub.get('task_id') == snapshot['task_id'] and pub.get('scope') == scope
         and pub.get('primary_owner') == owner and not any(pub.get(k) for k in
          ('new_CMS_Save', 'new_preview', 'new_permit', 'new_policy_consumption', 'new_account_or_fee_or_deploy', 'business_parent_closed')),
         'actual completed original readonly executor result required, not a production permission')
    records = source.get('record_actions', []); originals = pub.get('records', [])
    need(0 < len(records) <= 8 and len(records) == len(originals)
         and carrier.get('task_id') == snapshot['task_id'] and carrier.get('business_scope') == scope
         and carrier.get('original_business_owner') == owner
         and carrier.get('publication_integration_authority') == role and carrier.get('execution_source') == source_pin
         and carrier.get('issuer') in {executor, 'original '+executor}
         and carrier.get('channel_executor') in {'designated-development', 'original designated-development'}
         and len(carrier.get('targets', [])) == len(records), 'bounded exact original CMS rows and carrier required')
    contexts = []; seen = set()
    for record, target in zip(records, carrier['targets']):
        action = record['exact_action']; fields = action.get('changed_fields', [])
        physical = 'company.example:' + action['table'] + ':' + action['record_id'] + ':' + ','.join(fields)
        need(fields == sorted(set(fields)) and 0 < len(fields) <= 8
             and all(re.fullmatch(r'content_(en|zh|ms)', f) for f in fields)
             and all(action.get(k) == v for k, v in {'task_id': snapshot['task_id'], 'action_class': 'cms_write',
                 'business_scope': scope, 'business_policy_scope': scope, 'scope': physical, 'physical_target_scope': physical,
                 'original_professional_owner': owner, 'content_integration_department': role, 'authority_department': role,
                 'execution_department': executor}.items())
             and action['action_id'] == 'publish-' + action['candidate_version']
             and action['candidate_version'] == record['exact_target_name']
             and action['record_id'] not in seen
             and w.matching_standing_authorization(policy, department=role, action_class='cms_write', scope=physical) == standing,
             'exact original tuple/fields, business and physical scopes and own active standing required')
        seen.add(action['record_id']); original = record['original_PUB_record']
        need(original in originals, 'each row must be an unchanged original executor result')
        row = a.document(root, record['baseline_only']['complete_row']); before = {f: row[f] for f in fields}; desired = record['desired']
        forward = a.document(root, original['forward_values']); inverse = a.document(root, original['conditional_inverse_values'])
        need(row == a.document(root, original.get('authenticated_full41',original.get('before')))
             and a.document(root, original.get('backup_full41',original.get('backup'))) == row
             and row['id'] == action['record_id'] and row['slug'] == action['slug']
             and before == record['baseline_only']['before'] and set(desired) == set(fields)
             and desired == forward and before == inverse
             and record['baseline_only']['before_fields_sha256'] == w.sha256_value(before)
             and record['desired_fields_sha256'] == w.sha256_value(desired),
             'unchanged complete baseline, precise before/desired field bytes and inverse required')
        protected = record['protected_fields'] if not owner_source else {
          'non_write39':record['protection']['nonwrite_payload_fields'],
          'protected37':record['protection']['stable_business_fields'],
          'MS11':record['protection']['MS_fields'],
          'updated_at_version_sent_as_values':original.get('updated_at_version_sent_as_values')}
        rest = set(row) - set(fields)
        need(set(protected['non_write39']) == rest
             and set(protected['protected37']) == rest - {'updated_at', 'version'}
             and all(f.endswith('_ms') for f in protected['MS11']) and set(protected['MS11']) <= rest
             and protected.get('updated_at_version_sent_as_values') is False,
             'all original non-target/MS fields and server-owned CAS remain protected')
        reverse = record['conditional_inverse']
        need(reverse.get('restore_only_original_two_fields') == before and reverse.get('requiresParentRun') is True
             and reverse.get('scope') == physical and reverse.get('action_id') == 'rollback-' + action['candidate_version']
             and reverse.get('candidate_version') == action['candidate_version'] + '-rollback-v1'
             and all(reverse.get(k) is None for k in ('parentPermitId', 'parentRunId', 'saved_updated_at', 'current_post_Save_complete_row'))
             and target == ({'name':record['exact_target_name'],'task_id':snapshot['task_id'],
                             'exact_action':action,'conditional_inverse':reverse,'forward_values':original['forward_values'],
                             'inverse_values':original['conditional_inverse_values'],'forward_fields_sha256':w.sha256_value(desired),
                             'before_fields_sha256':w.sha256_value(before)} if owner_source else
                           {'name': record['exact_target_name'], 'action': action, 'inverse': reverse,
                           'forward_values': original['forward_values'], 'inverse_values': original['conditional_inverse_values'],
                           'desired_fields_sha256': w.sha256_value(desired), 'before_fields_sha256': w.sha256_value(before)}),
             'same exact target carrier and conditional own-parent inverse; no invented execution facts')
        contexts.append({'action': action, 'source': source_pin, 'owner': owner, 'message_owner': role,
                         'authority_department': role, 'standing_authorization_id': standing['authorization_id'],
                         'business_scope': scope, 'executor': executor, 'channel': 'designated-development',
                         'carrier': carrier_pin, 'desired': desired, 'before': before,
                         'protected_fields': {'not_written_fields': sorted(rest), 'server_CAS_metadata': ['updated_at', 'version'],
                          'stable_business_readback_fields': sorted(rest-{'updated_at','version'})},
                         'owner_result': q['outbox'], 'actual_HQ_intake': intake['record_id'],
                         'baseline_pin': record['baseline_only']['complete_row']})
    if owner_source and item.get('original_message_action') is None:
        return contexts, None
    action = a.document(root, item.get('original_message_action')); payload = action.get('payload', {})
    need(action.get('task_id') == snapshot['task_id'] and action.get('scope') == scope
         and action.get('sender_department') == role and action.get('target_department') == 'designated-development'
         and action.get('action_class') == 'thread_message' and action.get('assignment_record_required') is False
         and not action.get('authorization_changes') and payload['sha256'] == action.get('payload_sha256')
         and w.file_digest(root, payload['path']) == payload, 'same exact non-executing integrator message required')
    binding = w.read_json(Path(root)/'data/department-registry.json')['collaboration_bindings']['designated-development']
    need(action.get('source_project_id') == fixed['project_id']
         and all(action.get(k) == binding[v] for k, v in {'target_thread_id': 'thread_id', 'target_thread_title': 'title',
                  'target_project_id': 'project_id', 'target_cwd': 'cwd'}.items()), 'fixed original external channel identity required')
    text = (Path(root)/payload['path']).read_text()
    need(all(p['path'] in text and p['sha256'] in text for p in (source_pin, carrier_pin))
         and all(x['action']['record_id'] in text and x['action']['candidate_version'] in text for x in contexts),
         'unchanged message must bind full exact sources and all target tuples')
    return contexts, action


def record_source(root, task, path):
    """Append source facts only. The integrator records/sends its own message later."""
    import department_autonomy as a
    import goal_delivery_runtime as g
    from professional_cms_execution import records, EVENT
    pin = w.file_digest(root, path); item = a.document(root, pin)
    with w.workflow_lock(root):
        snapshot = g.restore_goal(root, w.read_json(w.snapshot_path(root, task)))
        contexts, _ = validate(root, snapshot, item)
        ids = {x['action']['action_id'] for x in contexts}
        bound = [x for x in records(root, snapshot) if x['action']['action_id'] in ids]
        if bound:
            a.require(len(bound) == len(contexts) and all(x['registration'] == pin for x in bound),
                      'immutable original integration source conflict')
            return {'result': 'duplicate_ignored', 'registration': pin, 'actual_message_sent': False}
        w.append_workflow_event(root, task, snapshot['current_state'], {EVENT: pin,
          'original_business_owner_unchanged': True, 'external_permission_issued': False})
    return {'result': 'recorded', 'registration': pin, 'exact_CMS_actions': [x['action'] for x in contexts],
            'actual_message_sent': False, 'production_READY': False, 'external_permission_issued': False}


def record(root, task, path):
    import department_autonomy as a
    import goal_delivery_runtime as g
    pin = w.file_digest(root, path); item = a.document(root, pin)
    with w.workflow_lock(root):
        snapshot = g.restore_goal(root, w.read_json(w.snapshot_path(root, task)))
        contexts, original = validate(root, snapshot, item)
        action = ({**original, 'professional_execution_source': pin, 'execution_tuples': [x['action'] for x in contexts]} if original else None)
        if action is None:
            from professional_cms_execution import records, EVENT
            existing=records(root,snapshot)
            bound=[x for x in existing if x['action']['action_id']in {c['action']['action_id']for c in contexts}]
            if bound:
                a.require(len(bound)==len(contexts)and all(x['registration']==pin for x in bound),'immutable own source action conflict')
                return {'result':'duplicate_ignored','registration':pin,'actual_message_sent':False}
            w.append_workflow_event(root,task,snapshot['current_state'],{EVENT:pin,'original_business_owner_unchanged':True,'external_permission_issued':False})
            return {'result':'recorded','registration':pin,'exact_CMS_actions':[x['action']for x in contexts],
                    'actual_message_sent':False,'production_READY':False,'external_permission_issued':False}
        old = [x for x in snapshot['goal_delivery'].get('approved_actions', []) if x.get('action_id') == action['action_id']]
        if old:
            a.require(old == [action], 'original integration action already bound to different source')
            return {'result': 'duplicate_ignored', 'registration': pin, 'actual_message_sent': False}
        from professional_cms_execution import records, EVENT
        existing = records(root, snapshot)
        bound = [x for x in existing if x['action']['action_id'] in {c['action']['action_id'] for c in contexts}]
        a.require(not bound or (len(bound) == len(contexts) and all(x['registration'] == pin for x in bound)),
                  'ambiguous existing execution action')
        snapshot['goal_delivery']['approved_actions'] = snapshot['goal_delivery'].get('approved_actions', []) + [action]
        w.append_workflow_event(root, task, snapshot['current_state'], {**({} if bound else {EVENT: pin}), 'goal_delivery': snapshot['goal_delivery'],
          'approved_message_prepared': item['original_message_action'], 'original_business_owner_unchanged': True,
          'external_permission_issued': False})
        w.atomic_write_json(w.snapshot_path(root, task), snapshot)
    return {'result': 'recorded', 'registration': pin, 'action_id': action['action_id'],
            'exact_CMS_actions': [x['action'] for x in contexts], 'actual_message_sent': False,
            'production_READY': False, 'external_permission_issued': False}


def message_context(root, snapshot, request):
    """Only a normally appended exact integrator message, never an arbitrary producer."""
    import department_autonomy as a
    candidates = [x for x in snapshot.get('goal_delivery', {}).get('approved_actions', [])
                  if x.get('execution_tuples') and x.get('professional_execution_source')
                  and all(x.get(k) == request.get(k) for k in
                   ('task_id','scope','action_id','action_class','sender_department','target_department','payload_sha256'))]
    if not candidates: return None
    a.require(len(candidates) == 1, 'one exact standing integrator message required')
    stored = candidates[0]; pin = stored['professional_execution_source']; item = a.document(root, pin)
    contexts, original = validate(root, snapshot, item)
    if stored.get('schema')=='professional-standing-CMS-message/v1':
        validate_followup_message(root,snapshot,stored)
        a.require(all(request.get(k)==v for k,v in stored.items()if k in request),'exact registered follow-up message required')
        return contexts[0]
    a.require(stored == {**original, 'professional_execution_source': pin, 'execution_tuples': [x['action'] for x in contexts]}
              and all(request.get(k) == v for k, v in original.items() if k in request), 'same original integrator action bytes required')
    events = [e for e in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS) if e.get('task_id') == snapshot['task_id']
              and e.get('details', {}).get('professional_cms_execution_source') == pin]
    a.require(len(events) == 1, 'one real append-only integration source event required')
    return contexts[0]


def validate_followup_message(root, snapshot, action):
    """Normal same-source narrow PUB/WEB follow-up after registration, no new grant."""
    import department_autonomy as a
    pin=action.get('professional_execution_source');item=a.document(root,pin)
    contexts,_=validate(root,snapshot,item)
    events=[e for e in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS)if e.get('task_id')==snapshot['task_id']
            and e.get('details',{}).get('professional_cms_execution_source')==pin]
    x=contexts[0];role=x['message_owner'];target=action.get('target_department')
    a.require(len(events)==1 and action.get('schema')=='professional-standing-CMS-message/v1'
     and action.get('task_id')==snapshot['task_id']and action.get('scope')==x['business_scope']
     and action.get('sender_department')==role and target in {x['executor'],x['channel']}
     and action.get('action_class')=='thread_message'and action.get('assignment_record_required')is False
     and action.get('execution_tuples')==[c['action']for c in contexts]
     and not any(action.get(k)for k in ('authorization_changes','execution_request','approval_id','consume_approval')),
     'only this registered integrator and exact PUB/WEB source tuples may continue')
    registry=w.department_registry(root);binding=(registry[target]['chat_binding']if target in registry else
      {**w.read_json(Path(root)/'data/department-registry.json')['collaboration_bindings'][target]})
    mapping={'target_thread_id':'task_id'if target in registry else'thread_id','target_thread_title':'title',
             'target_project_id':'project_id','target_cwd':'cwd'}
    a.require(action.get('source_project_id')==registry[role]['chat_binding']['project_id']
      and all(action.get(k)==binding[v]for k,v in mapping.items()),'fixed original source and recipient only')
    payload=action.get('payload',{});a.require(w.file_digest(root,payload.get('path',''))==payload
     and payload['sha256']==action.get('payload_sha256'),'exact follow-up body bytes required')
    text=(Path(root)/payload['path']).read_text()
    a.require(all(p['path']in text and p['sha256']in text for p in (pin,x['source']))
      and all(c['action']['action_id']in text and c['action']['scope']in text for c in contexts),
      'follow-up must bind actual registration, full source and all exact action/physical tuples')
    return contexts


def record_message(root,task,path):
    import department_autonomy as a
    import goal_delivery_runtime as g
    pin=w.file_digest(root,path);action=a.document(root,pin)
    with w.workflow_lock(root):
        snapshot=g.restore_goal(root,w.read_json(w.snapshot_path(root,task)))
        validate_followup_message(root,snapshot,action)
        old=[x for x in snapshot['goal_delivery'].get('approved_actions',[])if x.get('action_id')==action.get('action_id')]
        if old:
            a.require(old==[action],'same integration message cannot be rebound')
            return {'result':'duplicate_ignored','actual_message_sent':False}
        snapshot['goal_delivery']['approved_actions']=snapshot['goal_delivery'].get('approved_actions',[])+[action]
        w.append_workflow_event(root,task,snapshot['current_state'],{'goal_delivery':snapshot['goal_delivery'],
         'approved_message_prepared':pin,'actual_message_sent':False,'external_permission_issued':False})
        w.atomic_write_json(w.snapshot_path(root,task),snapshot)
    return {'result':'recorded','action_id':action['action_id'],'actual_message_sent':False,'external_permission_issued':False}


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['source-check', 'source-record'])
    parser.add_argument('--task-id', required=True); parser.add_argument('--input', required=True)
    args = parser.parse_args(); root = Path(__file__).resolve().parents[1]
    try:
        if args.command == 'source-record':
            result = record_source(root, args.task_id, args.input)
        else:
            import department_autonomy as a
            import goal_delivery_runtime as g
            snapshot = g.restore_goal(root, w.read_json(w.snapshot_path(root, args.task_id)))
            contexts, _ = validate(root, snapshot, a.document(root, w.file_digest(root, args.input)))
            result = {'result': 'validated', 'exact_CMS_actions': [x['action'] for x in contexts],
                      'actual_message_sent': False, 'production_READY': False}
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (w.WorkflowError, KeyError, ValueError) as error:
        parser.exit(1, str(error) + '\n')
