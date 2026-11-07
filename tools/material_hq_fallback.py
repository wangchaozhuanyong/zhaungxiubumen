"""HQ transport of the original material continuation after a real owner platform failure."""
from pathlib import Path
import copy

import department_autonomy as a
import workflow_control as w

TASK = 'fc-20261014-two-original-materials-exact-body-publication-v1'
ACTION = 'HQ-WEB-materials-original-stale-cancel-current-main-20261107-v1'
SCHEMA = 'original-materials-HQ-owner-platform-failure-message/v1'
EVENT = 'original_materials_HQ_platform_failure_continuation'
MARKER = 'original_materials_HQ_continuation'


def validate(root, source):
    """Reuse only this request's unchanged source proof, never a send permit."""
    context = w._VALIDATION_CONTEXT.get()
    from paid_three_page_bounded_cms import _HISTORICAL_SOURCE_EVENT
    key = ('original-material-HQ-source', str(Path(root).resolve()),
           w.sha256_value(source), _HISTORICAL_SOURCE_EVENT.get())
    if context is not None:
        # Reobserve every input version before looking up a proof. Any new
        # workflow/queue/policy/identity bytes invalidate the request memo.
        for name in list(context.files):
            context.bytes(name)
        cached = context.proofs.get(key)
        if cached is not None:
            context.recheck()
            return copy.deepcopy(cached)
    result = _validate(root, source)
    if context is not None:
        context.proofs[key] = copy.deepcopy(result)
    return result


def _validate(root, source, *, metadata_only=False):
    import goal_delivery_runtime as g

    a.require(source.get('schema') == SCHEMA and source.get('task_id') == TASK,
              'one original material HQ coordination source required')
    snapshot = g.restore_goal(root, w.read_json(w.snapshot_path(root, TASK)))
    goal = snapshot['goal_delivery']
    a.require(snapshot['current_state'] not in w.TERMINAL_STATES
              and goal['primary_owner'] == 'publishing' and g._owner_decision_delegation(root),
              'active original owner and actual ordinary HQ delegation required')
    owner_source = a.document(root, source['original_owner_message_source'])
    if metadata_only:
        # This branch authenticates only a neutral historical goal delta.
        # It cannot enter registered()/prepare/policy or authorize transport.
        # Production source checks must not recursively authorize every old
        # coordination message; actual message use still calls validate().
        frozen = a.document(root, snapshot['goal_contract'])
        a.require(owner_source.get('schema') == 'professional-owner-result-message-source/v1'
                  and owner_source.get('task_id') == TASK
                  and owner_source.get('goal_contract') == snapshot['goal_contract']
                  and owner_source.get('authorization') == goal['authorization_pin']
                  and all(goal.get(k) == frozen.get(k) for k in
                      ('primary_owner', 'producer_departments', 'authorized_scope', 'human_authorization')),
                  'neutral metadata must retain the original professional contract and authority')
        original = a.document(root, owner_source['original_action'])
        a.require(original.get('sender_department') == goal['primary_owner']
                  and original.get('action_class') == 'thread_message'
                  and original.get('scope') == owner_source.get('scope') in goal['authorized_scope']
                  and not original.get('authorization_changes') and not original.get('internal_repairs'),
                  'neutral original owner collaboration source only')
        route = None
    else:
        original, route = a.owner_result_message_source(root, snapshot, owner_source)
        a._owner_message_transport_not_started(root, snapshot, original)
    failed = g._native_document(root, source['owner_failed_native'])
    binding = w.department_registry(root)['publishing']['chat_binding']
    a.require(all(failed['thread'].get(k) == binding[v] for k, v in
              {'id': 'task_id', 'cwd': 'cwd', 'title': 'title', 'hostId': 'host_id'}.items())
              and failed['thread'].get('kind') == 'codex' and len(failed['turns']) == 1,
              'actual original publisher platform failure native identity required')
    turn = failed['turns'][0]
    a.require(turn.get('status') == 'failed' and 'usage limit' in str(turn.get('error', {})).lower(),
              'an actual original owner capacity failure, never idle or a caller label, required')
    request = a.document(root, source['HQ_request'])
    rejection = a.document(root, source['prior_rejection'])
    auth = rejection.get('authorization_precheck', {})
    a.require(rejection.get('status') == 'blocked' and rejection.get('message_sent') is False
              and auth.get('status') == 'authorization_change_required'
              and auth.get('reasons') == ['new_department'] and auth.get('needs_human_confirmation') is False
              and auth.get('next_owner') == 'operations' and auth.get('original_authorization') == goal['authorization_pin'],
              'preserved exact ordinary-coordination rejection and original authority required')
    from hq_bounded_web_admission import IDENTITY_KEYS, FRESH_KEYS
    a.require(set(request) <= set(IDENTITY_KEYS) | FRESH_KEYS
              and all(k in request for k in IDENTITY_KEYS)
              and request['task_id'] == original['task_id'] == TASK and request['action_id'] == ACTION
              and request['sender_department'] == 'operations' and request['action_class'] == 'thread_message'
              and request['assignment_record_required'] is False and request['authorization_changes'] == []
              and request['delivery_mode'] == 'mcp_direct_send'
              and all(request.get(k) == original.get(k) for k in
                  ('scope', 'target_department', 'target_project_id', 'target_thread_id',
                   'target_thread_title', 'target_cwd', 'target_sidebar_section_id'))
              and original['target_department'] == 'designated-development'
              and request['scope'] in goal['authorized_scope']
              and (metadata_only or route['external_permission_issued'] is False),
              'actual operations actor and unchanged originally declared material collaborator/scope required')
    payload = request['payload']
    a.require(w.file_digest(root, payload['path']) == payload and request['payload_sha256'] == payload['sha256'],
              'frozen exact HQ continuation payload required')
    registry = w.department_registry(root)
    sender = registry['operations']['chat_binding']
    target = g._collaboration_binding(root, snapshot, original['target_department'])
    a.require(sender['project_id'] == request['source_project_id'] == a.PROJECT
              and Path(sender['cwd']).resolve() == Path(root).resolve()
              and all(request[k] == target[v] for k, v in
                  {'target_project_id': 'project_id', 'target_thread_id': 'thread_id',
                   'target_thread_title': 'title', 'target_cwd': 'cwd'}.items()),
              'real fixed HQ and original external WEB binding required')
    return {'snapshot': snapshot, 'action': {k: request[k] for k in IDENTITY_KEYS},
            'sender_binding': sender, 'target_binding': {**target, 'task_id': target['thread_id']},
            'external_permission_issued': False, 'business_owner_changed': False,
            'actual_actor': 'operations'}


@w.request_validation_context()
def record(root, task, path):
    from department_rotation import prohibit_validation_write

    prohibit_validation_write()
    a.require(task == TASK, 'same original material task required')
    pin = w.file_digest(root, path)
    with w.workflow_lock(root):
        checked = validate(root, a.document(root, pin))
        snapshot = checked['snapshot']; goal = snapshot['goal_delivery']
        old = [e for e in w.read_jsonl(Path(root) / w.WORKFLOW_EVENTS, where={'task_id': TASK})
               if EVENT in e.get('details', {})]
        if old:
            a.require(len(old) == 1 and old[0]['details'][EVENT] == pin,
                      'original immutable HQ continuation already registered')
            return {'result': 'duplicate_ignored', 'external_permission_issued': False}
        action = {**checked['action'], MARKER: pin}
        a.require(not any(x.get('action_id') == ACTION for x in goal.get('approved_actions', [])),
                  'original HQ action already exists; reconcile original effect')
        w._VALIDATION_CONTEXT.get().recheck()
        snapshot['goal_delivery'] = {**goal, 'approved_actions': [*goal.get('approved_actions', []), action]}
        w.append_workflow_event(root, TASK, snapshot['current_state'],
            {EVENT: pin, 'goal_delivery': snapshot['goal_delivery'], 'actual_message_sent': False,
             'external_permission_issued': False})
        w.atomic_write_json(w.snapshot_path(root, TASK), snapshot)
    return {'result': 'recorded', 'external_permission_issued': False, 'actual_actor': 'operations'}


def registered(root, snapshot, request):
    if request.get('action_id') != ACTION:
        return None
    entries = [e['details'][EVENT] for e in w.read_jsonl(Path(root) / w.WORKFLOW_EVENTS,
               where={'task_id': TASK}) if EVENT in e.get('details', {})]
    if not entries:
        return None
    from hq_bounded_web_admission import FRESH_KEYS
    a.require(len(entries) == 1 and snapshot['task_id'] == TASK, 'one original HQ continuation event required')
    result = validate(root, a.document(root, entries[0]))
    action = {**result['action'], MARKER: entries[0]}
    a.require(set(request) <= set(action) | FRESH_KEYS
              and all(request[k] == action[k] for k in request if k not in FRESH_KEYS)
              and action in result['snapshot']['goal_delivery'].get('approved_actions', []),
              'registered exact HQ action and unchanged request required')
    return {**result, 'action': action, 'registration': entries[0]}


def route(root, snapshot, request):
    result = registered(root, snapshot, request)
    if result is None:
        return None
    return {'mode': a.MODE, 'purpose': 'original_professional_collaboration_transport_only',
            'source': result['action']['payload'], 'scope': result['action']['scope'],
            'sender_department': 'operations', 'target_department': 'designated-development',
            'external_permission_issued': False, 'business_producer_added': False}


def metadata(root, formal, event):
    detail = event.get('details', {})
    registration = EVENT in detail
    observation = (set(detail) == {'goal_delivery', 'actual_route_observation', 'external_permission_issued'}
                   and detail['goal_delivery'].get('current_route_observations', {}).get(ACTION)
                   == detail['actual_route_observation'])
    if not registration and not observation:
        return False
    a.require(event['task_id'] == formal['task_id'] == TASK and event['state'] == formal['current_state']
              and detail['external_permission_issued'] is False, 'same-state original HQ message metadata only')
    events = w.read_jsonl(Path(root) / w.WORKFLOW_EVENTS, where={'task_id': TASK})
    positions = [i for i, row in enumerate(events) if row.get('event_id') == event.get('event_id')]
    a.require(len(positions) == 1 and events[positions[0]] == event, 'actual immutable committed metadata required')
    earlier = events[:positions[0]]
    goals = [row['details']['goal_delivery'] for row in earlier
             if isinstance(row.get('details', {}).get('goal_delivery'), dict)]
    a.require(bool(goals), 'actual preceding original goal required')
    goal = goals[-1]
    if registration:
        a.require(set(detail) == {EVENT, 'goal_delivery', 'actual_message_sent', 'external_permission_issued'}
                  and detail['actual_message_sent'] is False, 'one ordinary HQ registration required')
        result = _validate(root, a.document(root, detail[EVENT]), metadata_only=True)
        action = {**result['action'], MARKER: detail[EVENT]}
        a.require(not any(x.get('action_id') == ACTION for x in goal.get('approved_actions', []))
                  and detail['goal_delivery'] == {**goal, 'approved_actions': [*goal.get('approved_actions', []), action]},
                  'only one exact HQ action may be appended to original goal')
    else:
        import goal_delivery_runtime as g
        actions = [x for x in goal.get('approved_actions', []) if x.get('action_id') == ACTION and MARKER in x]
        a.require(len(actions) == 1, 'original registered HQ action required')
        action = actions[0]
        checked = _validate(root, a.document(root, action[MARKER]), metadata_only=True)
        a.require(action == {**checked['action'], MARKER: action[MARKER]}, 'immutable actual HQ action required')
        pin = detail['actual_route_observation']; live = a.document(root, pin)
        inventory = g._collaboration_native(root, live.get('actual_native_observation'))
        rows = [*inventory.get('threads', []), *inventory.get('pinnedThreads', [])]
        a.require(live.get('delivery_mode') == 'mcp_direct_send'
                  and w._parse_observed_at(live.get('observed_at')) is not None
                  and len(live.get('threads', [])) == 2 and all(row in rows for row in live['threads'])
                  and {row.get('id') for row in live['threads']} == {
                      checked['sender_binding']['task_id'], checked['target_binding']['task_id']}
                  and detail['goal_delivery'] == {**goal, 'current_route_observations': {
                      **goal.get('current_route_observations', {}), ACTION: pin}},
                  'actual original sender/target observation only, with unchanged goal')
    return True
