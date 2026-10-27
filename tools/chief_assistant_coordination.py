"""Owner-delegated routine coordination, on the existing result/SQL ledgers.

The logical recipient is immutable. The handling actor is authenticated by
its own native read, lease, decision and reply; no producer/permit is assigned.
"""
from pathlib import Path
import argparse
import datetime as dt
import json
import re
import uuid
import sys

# Direct documented CLI and imported use share the confirmed project runtime.
_RUNTIME_ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(_RUNTIME_ROOT), str(_RUNTIME_ROOT / "tools")]

import workflow_control as w

ROLE = 'operations-assistant'
HQ = 'operations'
SOURCE = {'path': 'logs/handoffs/2026-10-27-chief-assistant-routine-decision-delegation-v1/operations/ACTUAL-OWNER-NATIVE-DECISION.json',
          'sha256': '324f5c5d37d02fbcf01d299d58b41c7ed26d10be0a9fb40bedf42e32a14b9271', 'size': 1827}
MODEL = 'owner_delegated_routine_coordination_v1'
DECISIONS = {'continue_original_owner', 'acknowledge_completed_scope', 'coordinate_original_scope',
             'wait_exact_dependency', 'escalate_sensitive'}


def require(test, message):
    if not test:
        raise w.WorkflowError('routine coordination: ' + message)


def doc(root, pin):
    require(isinstance(pin, dict) and w.file_digest(root, pin.get('path', '')) == pin, 'exact immutable source pin required')
    value = json.loads(w.safe_path(root, pin['path']).read_text())
    require(isinstance(value, dict), 'object source required')
    return value


def authority(root):
    config = w.read_json(Path(root) / 'data/task-contract.json').get('routine_coordination')
    if config is None:
        return None
    require(config.get('model') == MODEL and config.get('owner_source') == SOURCE
            and config.get('primary') == ROLE and config.get('fallback') == HQ,
            'actual owner source, primary and fallback required')
    raw = doc(root, SOURCE)
    native = doc(root, config.get('actual_owner_native'))
    registry = w.department_registry(root)
    hq, chief = [registry[x]['chat_binding'] for x in (HQ, ROLE)]
    require(raw.get('thread', {}).get('id') == native.get('thread', {}).get('id') == hq['task_id']
            and hq.get('project_id') == chief.get('project_id') == raw['thread'].get('project_id')
            and Path(hq['cwd']).resolve() == Path(chief['cwd']).resolve() == Path(root).resolve()
            and native['thread'].get('cwd') == hq['cwd'], 'real fixed HQ/chief project and native required')
    selected = [(t, m) for t in native.get('turns', []) for m in t.get('items', [])
                if m.get('id') == raw.get('user_message', {}).get('id')]
    require(len(selected) == 1 and selected[0][0].get('id') == raw.get('turn', {}).get('id')
            and selected[0][1] == raw['user_message'] and selected[0][1].get('type') == 'userMessage'
            and selected[0][0].get('status') in {'inProgress', 'completed'} and not selected[0][0].get('error'),
            'actual owner message, never assistant paraphrase or fabricated completion')
    text = ''.join(c.get('text', '') for c in raw['user_message'].get('content', []) if c.get('type') == 'text')
    require(all(x in text for x in ('权限跟你一样', '无需跟你汇报', '审批工作优先安排给他', '忙不过来你接手', '重大'))
            and registry[ROLE].get('new_dispatch_enabled') is True
            and registry[ROLE].get('coordination_authority', {}).get('routine_decisions') is True
            and registry[ROLE].get('production_write_allowed') is False,
            'verified routine delegation and no production executor role required')
    return config


def default_receiver(root, logical):
    return ROLE if logical == HQ and authority(root) is not None else logical


def actor_allowed(root, identity, logical, role):
    import department_autonomy as a
    config = authority(root)
    if config is None or logical not in {HQ, ROLE} or role not in {HQ, ROLE} or identity.get('sender_department') == role:
        return False
    require(identity.get('sender_department') not in a.ASSISTANTS, 'retired assistant source is not a new routine delivery')
    return True


def rows(root, identity):
    import result_coordination as rc
    return [r for r in w._result_handoff_rows(root, identity['task_id']) if rc.exact_identity(r) == rc.exact_identity(identity)]


def claimable(root, identity, role):
    import result_coordination as rc
    logical = rc.result_lane(root, identity).get('target_department')
    if not actor_allowed(root, identity, logical, role):
        return False
    existing = [r for r in rows(root, identity) if r.get('event') == 'controller_received']
    require(not existing, 'already received original result; read committed effect, never re-intake')
    return True


def receiver_context(root, request, logical):
    """Real role plus frozen logical receiver, no target alias or new intake."""
    import result_coordination as rc
    role = request.get('coordinator_role', HQ)
    require(actor_allowed(root, request, logical, role), 'authorized routine actor for original logical receiver required')
    require(request.get('routine_delegation') == SOURCE, 'exact current owner delegation required')
    require(request.get('logical_receiver') == logical, 'frozen original logical receiver cannot change')
    fixed = w.department_registry(root)[role]['chat_binding']
    owner = request.get('coordinator_owner')
    require(isinstance(owner, str) and owner.split(':', 1)[0] == fixed['task_id'], 'actual handler fixed thread required')
    return {'logical_receiver': logical, 'handling_actor': role, 'routine_delegation': SOURCE}


def lease(root, store, request):
    import result_coordination as rc
    identity = rc.exact_identity(request)
    logical = rc.result_lane(root, identity)['target_department']
    proof = receiver_context(root, request, logical)
    store._lease(identity, request['coordinator_role'], request['coordinator_owner'], request.get('coordination_claim'))
    return proof


def intake_readback(root, payload, row):
    import department_autonomy as a
    if not row.get('routine_delegation'):
        return False
    request = payload['request']
    require(request.get('event') == row.get('event') == 'controller_received', 'routine intake schema required')
    proof = receiver_context(root, {**request, 'coordinator_role': row.get('coordinator_role'),
                              'coordinator_owner': row.get('coordinator_owner')}, row.get('target_department'))
    require(all(row.get(k) == v for k, v in proof.items()), 'original logical receiver and real actor cannot be aliased')
    actual = a.received_knowledge(root, {**request, 'coordinator_role': row['coordinator_role'],
                                        'coordinator_owner': row.get('coordinator_owner')})
    require(all(row.get(k) == v for k, v in actual.items()), 'real actor native read must remain exact')
    return True


def _committed_intake(root, request):
    import result_coordination as rc
    matches = [r for r in rows(root, request) if r.get('event') == 'controller_received']
    require(len(matches) == 1, 'one actual original committed intake before routine decision')
    intake = matches[0]
    rc._committed_result(root, intake)
    require(intake.get('coordinator_role') == request.get('coordinator_role')
            and request.get('received_record_id') == intake['record_id'], 'actual handling actor and exact intake required')
    return intake


def decision(root, request):
    """A routine decision does not create scope, permit, QA or production rights."""
    import goal_delivery_runtime as g
    import result_coordination as rc
    require(request.get('event') == 'controller_decision' and request.get('decision') in DECISIONS,
            'known bounded routine decision required')
    intake = _committed_intake(root, request)
    box = doc(root, intake['outbox'])
    snapshot = g.restore_goal(root, w.read_json(w.snapshot_path(root, request['task_id'])))
    goal = snapshot.get('goal_delivery', {})
    scope = box.get('scope')
    if scope is None and len(goal.get('authorized_scope', [])) == 1:
        scope = goal['authorized_scope'][0]
    require(isinstance(scope, str) and request.get('scope') == scope,
            'exact original result scope required')
    next_owner = request.get('next_owner')
    require(next_owner == (HQ if request['decision'] == 'escalate_sensitive' else goal.get('primary_owner', request['sender_department']))
            and isinstance(request.get('next_action'), str) and request['next_action'].strip(),
            'return to original professional owner; sensitive actions go to HQ')
    require(not any(request.get(k) for k in ('approval_id', 'consume_approval', 'execution_request',
                'permission_issued', 'production_write_allowed', 'business_goal_closed', 'qa_verdict', 'authorization_changes')),
            'routine decision cannot expand scope or issue production approval')
    evidence = doc(root, request.get('decision_source'))
    require(evidence.get('schema') == 'routine-original-result-decision/v1'
            and all(evidence.get(k) == request.get(k) for k in (*rc.IDENTITY_FIELDS, 'scope', 'decision', 'next_owner', 'next_action'))
            and evidence.get('outbox') == intake['outbox'] and evidence.get('owner_delegation') == SOURCE
            and evidence.get('external_permission_issued') is False,
            'exact immutable ordinary decision evidence required')
    page = g._native_document(root, request.get('actual_decision_native'))
    fixed = w.department_registry(root)[request['coordinator_role']]['chat_binding']
    pairs = [(t, m) for t in page.get('turns', []) for m in t.get('items', [])
             if m.get('id') == request.get('actual_decision_message_id')]
    require(all(page.get('thread', {}).get(k) == fixed[v] for k, v in {'id': 'task_id', 'title': 'title', 'cwd': 'cwd'}.items())
            and len(pairs) == 1 and not pairs[0][0].get('error') and pairs[0][1].get('type') == 'agentMessage'
            and request['decision_source']['path'] in pairs[0][1].get('text', '')
            and request['decision_source']['sha256'] in pairs[0][1].get('text', ''),
            'real handling actor must name its exact decision source')
    row = {**request, 'record_id': str(uuid.uuid4()), 'created_at': w.utc_timestamp(),
           'outbox': intake['outbox'], 'target_department': intake['target_department'],
           'evidence': [w.file_digest(root, p) for p in request.get('evidence_paths', [])],
           'handling_actor': request['coordinator_role'], 'logical_receiver': intake['target_department'],
           'mode_authorization': a_owner(), 'routine_delegation': SOURCE, 'acceptance_proven': False,
           'external_permission_issued': False, 'business_goal_closed': False,
           'qa_status': 'NOT_VERIFIED', 'execution_status': 'NOT_EXECUTED', 'public_postcheck_status': 'NOT_VERIFIED'}
    for k in ('coordination_claim', 'outbox_path', 'evidence_paths'):
        row.pop(k, None)
    return row


def a_owner():
    from department_autonomy import OWNER
    return OWNER


def record_decision(root, request):
    import department_autonomy as a
    import result_coordination as rc
    identity = rc.exact_identity(request)
    with rc.coordination_lock(root):
        store = rc.CoordinationStore(root)
        try:
            lease(root, store, request)
            existing = [r for r in rows(root, identity) if r.get('event') == 'controller_decision']
            if existing:
                require(len(existing) == 1 and existing[0].get('idempotency_key') == request.get('idempotency_key'),
                        'one routine decision; read original effect before a changed decision')
                rc._committed_result(root, existing[0])
                return {**existing[0], 'result': 'duplicate_ignored'}, [w.result_handoff_path(root, identity['task_id'])]
            row = decision(root, request)
            payload = rc._payload(root, request)
            effect = rc._sha([request['event'], request.get('idempotency_key')])
            require(isinstance(request.get('idempotency_key'), str) and request['idempotency_key'], 'stable effect key required')
            store._begin()
            prior = store.conn.execute('SELECT status FROM reservations WHERE result_key=? AND effect_key=?',
                                       (rc._key(identity), effect)).fetchone()
            require(prior is None, 'existing/unknown decision effect: recover original reservation, never reappend')
            store.conn.execute("INSERT INTO reservations VALUES(?,?,?,'uncertain',NULL)",
                               (rc._key(identity), effect, rc._canonical(payload)))
            store.conn.commit()
            a.append_result_record(root, identity['task_id'], row)
            rc.HandoffAdmission(store, identity, effect, payload).complete(row)
            return {**row, 'result': 'recorded'}, [w.result_handoff_path(root, identity['task_id'])]
        finally:
            store.close()


def message_route(root, snapshot, request):
    source = request.get('routine_decision_reply')
    if source is None:
        return None
    import result_coordination as rc
    require(request.get('action_class') == 'thread_message' and not request.get('assignment_record_required')
            and not any(request.get(k) for k in ('authorization_changes', 'approval_id', 'consume_approval', 'execution_request')),
            'ordinary decision reply is transport only')
    identity = rc.exact_identity(source)
    selected = [r for r in rows(root, identity) if r.get('event') == 'controller_decision'
                and r.get('record_id') == source.get('decision_record_id')]
    require(len(selected) == 1 and selected[0].get('routine_delegation') == SOURCE,
            'one exact committed delegated decision for this reply required')
    row = selected[0]
    rc._committed_result(root, row)
    role = request.get('sender_department')
    require(role == row.get('coordinator_role') and actor_allowed(root, identity, row['target_department'], role)
            and request.get('task_id') == identity['task_id'] == snapshot.get('task_id')
            and request.get('scope') == row['scope'] and request.get('target_department') == row['next_owner'],
            'real decision actor/task/scope/original next owner required')
    registry = w.department_registry(root)
    sender, target = registry[role]['chat_binding'], registry[request['target_department']]['chat_binding']
    require(sender['project_id'] == target['project_id'] == request.get('source_project_id') == request.get('target_project_id')
            and Path(sender['cwd']).resolve() == Path(target['cwd']).resolve() == Path(root).resolve()
            and all(request.get(k) == target[v] for k, v in {'target_thread_id': 'task_id', 'target_thread_title': 'title',
                    'target_cwd': 'cwd', 'target_sidebar_section_id': 'sidebar_section_id'}.items()),
            'exact fixed current actor/receiver/project/cwd required')
    payload = request.get('payload')
    require(w.file_digest(root, payload.get('path', '')) == payload and payload['sha256'] == request.get('payload_sha256'),
            'exact decision reply payload required')
    body = w.safe_path(root, payload['path']).read_text()
    require(all(re.search(r'(?m)^' + key + '=' + re.escape(str(request[key])) + r'\s*$', body)
                for key in ('task_id', 'scope', 'action_id', 'sender_department', 'target_department'))
            and row['result_sha256'] in body and row['decision_source']['path'] in body
            and row['decision_source']['sha256'] in body,
            'reply must bind actual original result and decision, not a new generic approval')
    return {'mode': 'department_autonomous_delivery_v1', 'purpose': 'routine_decision_direct_reply',
            'source': payload, 'scope': row['scope'], 'sender_department': role,
            'target_department': row['next_owner'], 'decision_record_id': row['record_id'],
            'owner_source': SOURCE, 'external_permission_issued': False}


def reply(root, request_path, directory):
    """Normal policy, durable original effect intent, then one official queue call."""
    import goal_delivery_runtime as g
    import goal_source_recovery as recovery
    from department_event_dispatcher import OfficialQueueTransport
    request_pin = w.file_digest(root, request_path)
    request = doc(root, request_pin)
    snapshot = g.restore_goal(root, w.read_json(w.snapshot_path(root, request['task_id'])))
    route = message_route(root, snapshot, request)
    require(route is not None and request.get('delivery_mode') == 'official_native_queue', 'exact normal routine official reply required')
    destination = w.safe_path(root, directory)
    require(Path(directory).parts[:2] == ('logs', 'handoffs') and not destination.is_symlink(), 'project-owned reply directory required')
    with w.workflow_lock(root):
        previous = [e for e in w.read_jsonl(Path(root) / w.WORKFLOW_EVENTS)
                    if e.get('task_id') == request['task_id']
                    and e.get('details', {}).get('routine_decision_reply_intent', {}).get('action_id') == request['action_id']]
        require(not previous and not destination.exists(), 'existing/unknown reply effect: read original intent, never resend')
    prepared = recovery.prepare_message(root, request)
    require(prepared.get('status') == 'ready_to_queue', 'normal actual fixed-target reply preparation required: ' + str(prepared.get('status')))
    with w.workflow_lock(root):
        # Recheck inside the serial effect boundary; preparation does not own intent.
        message_route(root, g.restore_goal(root, w.read_json(w.snapshot_path(root, request['task_id']))), request)
        previous = [e for e in w.read_jsonl(Path(root) / w.WORKFLOW_EVENTS)
                    if e.get('task_id') == request['task_id']
                    and e.get('details', {}).get('routine_decision_reply_intent', {}).get('action_id') == request['action_id']]
        require(not previous and not destination.exists(), 'reply intent already exists; inspect its actual effect')
        destination.mkdir(parents=True)
        w.atomic_write_json(destination / 'normal-preparation.json', prepared)
        intent = {'action_id': request['action_id'], 'request': request_pin,
                  'decision_record_id': route['decision_record_id'], 'directory': directory,
                  'payload': request['payload'], 'policy_decision_id': prepared['policy_decision']['decision_id'],
                  'handling_actor': request['sender_department'], 'target_department': request['target_department']}
        w.append_workflow_event(root, request['task_id'], snapshot['current_state'],
                                {'routine_decision_reply_intent': intent, 'external_permission_issued': False})
    effect = OfficialQueueTransport(root, None).enqueue({'thread_id': request['target_thread_id'],
        'message': w.safe_path(root, request['payload']['path']).read_text(), 'directory': destination,
        'payload_sha256': request['payload_sha256'], 'policy_decision_id': intent['policy_decision_id']})
    result = {'state': 'official_queue_accepted_not_received', 'effect': effect, 'intent': intent,
              'received': False, 'external_permission_issued': False}
    w.atomic_write_json(destination / 'actual-return.json', result)
    return result


def reply_effect(root, task_id, action_id):
    """Read original effect, including unknown; never sends or changes a receipt."""
    events = [e for e in w.read_jsonl(Path(root) / w.WORKFLOW_EVENTS) if e.get('task_id') == task_id
              and e.get('details', {}).get('routine_decision_reply_intent', {}).get('action_id') == action_id]
    require(len(events) == 1, 'one original routine reply intent required')
    intent = events[0]['details']['routine_decision_reply_intent']
    request = doc(root, intent['request'])
    import goal_delivery_runtime as g
    message_route(root, g.restore_goal(root, w.read_json(w.snapshot_path(root, task_id))), request)
    path = w.safe_path(root, intent['directory']) / 'native-queue-result.json'
    if not path.exists():
        return {'state': 'effect_unknown', 'repeat_allowed': False, 'intent': intent}
    result = json.loads(path.read_text())
    match = re.fullmatch(r'Queued message ([0-9a-f-]{36}) for thread ([0-9a-f-]{36})\.\s*', result.get('stdout', ''))
    require(result.get('exit_code') == 0 and match and match[2] == request['target_thread_id']
            and result.get('payload_sha256') == request['payload_sha256']
            and result.get('policy_decision_id') == intent['policy_decision_id'], 'original exact queue effect differs; do not resend')
    return {'state': 'official_queue_accepted_not_received', 'message_id': match[1], 'intent': intent,
            'received': False, 'repeat_allowed': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['authority', 'preflight', 'reply', 'reply-effect'])
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--input')
    parser.add_argument('--directory')
    parser.add_argument('--task-id')
    parser.add_argument('--action-id')
    args = parser.parse_args()
    if args.command == 'authority':
        result = authority(args.root)
    elif args.command == 'reply':
        result = reply(args.root, args.input, args.directory)
    elif args.command == 'reply-effect':
        result = reply_effect(args.root, args.task_id, args.action_id)
    else:
        import result_coordination as rc
        request = json.loads(w.safe_path(args.root, args.input).read_text())
        result = {'route': rc.result_lane(args.root, rc.exact_identity(request)),
                  'authority': authority(args.root), 'actual_write': False}
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
