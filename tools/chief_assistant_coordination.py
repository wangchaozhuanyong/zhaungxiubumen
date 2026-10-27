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




DAILY_REPLY_ROOT = 'logs/handoffs/chief-daily-owner-knowledge'
DAILY_KNOWLEDGE_PURPOSE = 'received_declared_daily_owner_knowledge'
ORDINARY_PURPOSES = {'current_chief_original_owner_followthrough', 'original_professional_report_to_current_chief', DAILY_KNOWLEDGE_PURPOSE}


def ordinary_source_history(root, task):
    """Immutable provenance only; old QA never becomes a new communication gate."""
    events = w.read_jsonl(Path(root) / w.WORKFLOW_EVENTS); previous = ''; own = []
    for event in events:
        require(event.get('previous_event_hash', '') == previous
                and event.get('event_hash') == w.sha256_value({k: v for k, v in event.items() if k != 'event_hash'}),
                'intact original workflow hash chain required')
        previous = event['event_hash']
        if event.get('task_id') == task: own.append(event)
    require(own and own[0].get('state') == 'planned' and not any(e.get('state') == 'closed' for e in own),
            'existing open original task history required; no closed goal reopening')
    previous = ''
    for row in w.read_jsonl(w.receipts_path(root, task)):
        require(row.get('task_id') == task and row.get('previous_hash', '') == previous
                and row.get('receipt_hash') == w.sha256_value(w._receipt_payload_for_hash(row)),
                'intact original receipt hash chain required')
        previous = row['receipt_hash']


def daily_reply_directory(task_id, action_id):
    """One durable original transport key, not a task/workflow or new ledger."""
    w.validate_task_id(task_id)
    require(isinstance(action_id, str) and action_id.strip(), 'exact daily knowledge action required')
    return DAILY_REPLY_ROOT + '/' + task_id + '/' + w.sha256_value([task_id, action_id])


def daily_knowledge_source(root, snapshot, request):
    """Read genuine declared source + committed intake; never invent a goal."""
    marker = request.get('daily_received_knowledge')
    if marker is None:
        return None
    import department_autonomy as a
    import result_coordination as rc
    require(isinstance(marker, dict) and set(marker) == {'schema', 'identity', 'received_record_id'}
            and marker['schema'] == 'received-declared-daily-knowledge/v1', 'exact received daily knowledge source schema required')
    identity = rc.exact_identity(marker['identity'])
    require(marker['identity'] == identity and not snapshot
            and request.get('task_id') == identity['task_id']
            and request.get('sender_department') == ROLE
            and request.get('target_department') == identity['sender_department'],
            'original daily producer is the knowledge recipient, never a substitute goal or actor')
    source = a.scheduled_delivery_source(root, identity)
    require(source is not None and source.get('local_delivery_only') is True
            and source.get('external_upload_authorized') is False and source.get('fees_authorized') is False,
            'existing declared local daily authority required; no release or fee grant')
    lane = rc.result_lane(root, identity)  # Real declaration/automation/READY/native/UTF8 still checked.
    original = rows(root, identity)
    queued = [r for r in original if r.get('event') == 'notification_queued']
    require(len(queued) == 1 and lane.get('target_department') in {HQ, ROLE}, 'one frozen original daily delivery required')
    intake = _committed_intake(root, {**identity, 'coordinator_role': ROLE,
                                      'received_record_id': marker['received_record_id']})
    require(intake.get('routine_delegation') == SOURCE and intake.get('handling_actor') == ROLE
            and intake.get('target_department') == queued[0].get('target_department')
            and intake.get('source_mode') == queued[0].get('source_mode') == 'scheduled_run'
            and intake.get('source_automation_id') == queued[0].get('source_automation_id') == source['automation_id'],
            'actual own committed receipt and unchanged frozen daily receiver/source required')
    box = doc(root, queued[0]['outbox'])
    scope = box.get('owner_authorization', {}).get('scope')
    require(isinstance(scope, str) and scope.strip() and request.get('scope') == scope,
            'exact original outbox authority scope required; no fabricated business scope')
    for key in ('owner_direct_authorization', 'owner_native_source'):
        doc(root, source.get(key))
    return {'declared_source': source, 'original_outbox': queued[0]['outbox'],
            'identity': identity, 'received_record_id': intake['record_id'],
            'committed_receipt_sha256': w.sha256_value(intake), 'scope': scope,
            'original_professional_owner': identity['sender_department'],
            'external_permission_issued': False, 'knowledge_only': True}


def ordinary_message_route(root, snapshot, request):
    """Current owner-delegated communication, separate from old execution actors."""
    import department_autonomy as a
    import goal_delivery_runtime as g
    sender, target = request.get('sender_department'), request.get('target_department')
    if request.get('action_class') != 'thread_message' or ROLE not in {sender, target}:
        return None
    if request.get('result_notification') is not None or request.get('result_identity') is not None:
        return None  # Formal result delivery retains its own authenticated transport.
    require(authority(root) is not None, 'genuine current chief owner delegation required')
    a.authority(root)
    require(request.get('routine_delegation', SOURCE) == SOURCE
            and (sender != ROLE or request.get('routine_delegation') == SOURCE),
            'explicit authentic current chief source required; caller labels are not delegation')
    require(request.get('delivery_mode') == 'official_native_queue' and not request.get('assignment_record_required') and not any(request.get(k) for k in (
        'authorization_changes', 'approval_id', 'consume_approval', 'execution_request', 'permission_issued',
        'production_write_allowed', 'qa_verdict', 'result_notification', 'routine_decision_reply')),
        'ordinary communication cannot assign a task, impersonate a receipt or issue execution authority')
    daily = daily_knowledge_source(root, snapshot, request)
    if daily is not None:
        owner = daily['original_professional_owner']
        purpose = DAILY_KNOWLEDGE_PURPOSE
        goal = {}
    else:
        frozen = doc(root, snapshot.get('goal_contract'))
        require(snapshot.get('current_state') not in w.TERMINAL_STATES
                and all(snapshot.get('goal_delivery', {}).get(k) == frozen.get(k) for k in
                    ('primary_owner', 'producer_departments', 'authorized_scope', 'human_authorization', 'required_execution_actions')),
                'supplied original state and frozen participants cannot change')
        snapshot = g.restore_goal(root, snapshot); goal = snapshot.get('goal_delivery', {})
        require(snapshot.get('task_id') == request.get('task_id') == frozen.get('task_id')
                and snapshot.get('current_state') not in w.TERMINAL_STATES
                and all(goal.get(k) == frozen.get(k) for k in ('primary_owner', 'producer_departments',
                         'authorized_scope', 'human_authorization', 'required_execution_actions'))
                and request.get('scope') in goal.get('authorized_scope', [])
    ,
                'active unchanged original task, authority, owner, scope and intact history required')
        ordinary_source_history(root, snapshot['task_id'])
        owner = goal.get('primary_owner')
        if sender == ROLE:
            require(target == owner and a.professional(root, target), 'ordinary followthrough returns only to the real original professional owner')
            purpose = 'current_chief_original_owner_followthrough'
        else:
            require(target == ROLE and sender not in a.ASSISTANTS
                    and sender in {owner, *goal.get('producer_departments', [])} and a.professional(root, sender),
                    'original professional report only; retired actors cannot become current senders')
            purpose = 'original_professional_report_to_current_chief'
    payload = request.get('payload')
    require(isinstance(payload, dict) and w.file_digest(root, payload.get('path', '')) == payload
            and request.get('payload_sha256') == payload['sha256'], 'unchanged exact ordinary message bytes required')
    body = w.safe_path(root, payload['path']).read_text()
    keys = ('task_id', 'scope', 'action_id', 'sender_department', 'target_department') if sender == ROLE else ('task_id', 'scope')
    require(all(re.search(r'(?m)^' + key + '=' + re.escape(str(request.get(key, ''))) + r'\s*$', body) for key in keys),
            'original task/scope and real sender/receiver/action payload relation required')
    if daily is not None:
        require(all(re.search(r'(?m)^' + key + '=' + re.escape(value) + r'\s*$', body) for key, value in
                    {'received_record_id': daily['received_record_id'],
                     'result_sha256': daily['identity']['result_sha256'], 'no_execution_permission': 'true'}.items()),
                'receipt knowledge payload must retain original receipt/result and no execution grant')
    registry = w.department_registry(root); source, dest = [registry[x]['chat_binding'] for x in (sender, target)]
    require(source.get('project_id') == dest.get('project_id') == request.get('source_project_id') == request.get('target_project_id') == a.PROJECT
            and Path(source.get('cwd', '')).resolve() == Path(dest.get('cwd', '')).resolve() == Path(root).resolve()
            and all(request.get(k) == dest[v] for k, v in {'target_thread_id': 'task_id', 'target_thread_title': 'title',
                'target_cwd': 'cwd', 'target_sidebar_section_id': 'sidebar_section_id'}.items())
            and registry[sender].get('new_dispatch_enabled') is True and registry[target].get('new_dispatch_enabled') is True,
            'exact current fixed sender/receiver/project/directory/sidebar required; no role alias')
    return {'mode': a.MODE, 'purpose': purpose, 'source': payload, 'report': payload, 'scope': request['scope'],
            'sender_department': sender, 'target_department': target, 'owner_source': SOURCE,
            **({'daily_received_source': daily} if daily is not None else {'goal_contract': snapshot['goal_contract']}),
            'original_professional_owner': owner,
            'historical_responsible_assistant_unchanged': goal.get('responsible_assistant'),
            'external_permission_issued': False, 'business_producer_added': False}


def ordinary_message_facts(root, snapshot, request, route):
    """Fresh sending facts are checked at policy, not written into old sources."""
    import department_autonomy as a
    import goal_delivery_runtime as g
    require(route.get('purpose') in ORDINARY_PURPOSES and ordinary_message_route(root, snapshot, request) == route,
            'same authentic ordinary coordination route required')
    observed = w._parse_observed_at(request.get('live_observed_at')); now = dt.datetime.now(dt.timezone.utc)
    require(observed is not None and 0 <= (now - observed).total_seconds() <= 300,
            'fresh ordinary sender/receiver observation required before queue; preserve old report bytes')
    registry = w.department_registry(root)
    pins = {}
    for key, role in (('actual_sender_state', request['sender_department']), ('actual_target_state', request['target_department'])):
        page = g._collaboration_native(root, request.get(key)); fixed = registry[role]['chat_binding']
        require(all(page.get('thread', {}).get(k) == fixed[v] for k, v in
                    {'id': 'task_id', 'title': 'title', 'cwd': 'cwd', 'hostId': 'host_id'}.items())
                and page['thread'].get('kind') == 'codex' and page['thread'].get('status', {}).get('type') in {'active', 'idle', 'notLoaded'} and page.get('turns')
                and not page['turns'][0].get('error') and page['turns'][0].get('status') in {'completed', 'inProgress', 'pending'}
                and type(page['turns'][0].get('startedAt')) in {int, float}
                and page['turns'][0]['startedAt'] <= now.timestamp(),
                'real current fixed native identity/turn; unknown, failed or substituted role rejected')
        pins[key] = request[key]
    return {**({'daily_received_source': route['daily_received_source']} if route.get('daily_received_source') else
               {'goal_contract': route['goal_contract']}), 'routine_delegation': SOURCE, 'payload': request['payload'],
            'live_observed_at': request['live_observed_at'], **pins, 'external_permission_issued': False}


def message_route(root, snapshot, request):
    source = request.get('routine_decision_reply')
    if source is None:
        return ordinary_message_route(root, snapshot, request)
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
    daily = route.get('purpose') == DAILY_KNOWLEDGE_PURPOSE
    if daily:
        require(directory == daily_reply_directory(request['task_id'], request['action_id']), 'one original daily reply directory required')
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
                  'decision_record_id': route.get('decision_record_id'), 'ordinary_message_source': route.get('daily_received_source', route.get('goal_contract')), 'routine_delegation': SOURCE, 'directory': directory,
                  'payload': request['payload'], 'policy_decision_id': prepared['policy_decision']['decision_id'],
                  'handling_actor': request['sender_department'], 'target_department': request['target_department']}
        if daily:
            # Existing reply intent/result files are transport facts, not a synthetic business workflow.
            w.atomic_write_json(destination / 'routine-reply-intent.json', intent)
        else:
            w.append_workflow_event(root, request['task_id'], snapshot['current_state'],
                                    {'routine_decision_reply_intent': intent, 'external_permission_issued': False})
    effect = OfficialQueueTransport(root, None).enqueue({'thread_id': request['target_thread_id'],
        'message': w.safe_path(root, request['payload']['path']).read_text(), 'directory': destination,
        'payload_sha256': request['payload_sha256'], 'policy_decision_id': intent['policy_decision_id']})
    result = {'state': 'official_queue_accepted_not_received', 'effect': effect, 'intent': intent,
              'received': False, 'external_permission_issued': False}
    w.atomic_write_json(destination / 'actual-return.json', result)
    return result


def _daily_reply_intent_readback(root, intent, request, route):
    """Authenticate file-only daily intent against its actual normal policy."""
    require(route.get('purpose') == DAILY_KNOWLEDGE_PURPOSE
            and intent.get('directory') == daily_reply_directory(request['task_id'], request['action_id'])
            and intent.get('ordinary_message_source') == route['daily_received_source']
            and intent.get('payload') == request['payload'] and intent.get('routine_delegation') == SOURCE
            and intent.get('handling_actor') == request['sender_department'] == ROLE
            and intent.get('target_department') == request['target_department'],
            'unchanged authenticated daily intent/source/payload/actor and original directory required')
    policies = [p for p in w.read_jsonl(Path(root) / w.POLICY_DECISIONS)
                if p.get('decision_id') == intent.get('policy_decision_id')]
    fields = ('task_id', 'action_id', 'action_class', 'scope', 'source_project_id', 'target_project_id',
              'target_department', 'target_thread_id', 'target_thread_title', 'target_cwd',
              'target_sidebar_section_id', 'payload_sha256')
    require(len(policies) == 1 and all(policies[0].get(k) == request.get(k) for k in fields)
            and policies[0].get('department') == ROLE and policies[0].get('status') == 'allow'
            and policies[0].get('external_permission_issued') is False
            and not policies[0].get('consume_approval') and not policies[0].get('approval_id')
            and policies[0].get('routine_message_source', {}).get('daily_received_source') == route['daily_received_source'],
            'real exact normal daily policy and committed source required; no caller grant')
    directory = w.safe_path(root, intent['directory'])
    prepared = w.read_json(directory / 'normal-preparation.json')
    require(prepared.get('status') == 'ready_to_queue' and prepared.get('policy_decision') == policies[0]
            and prepared.get('payload') == request['payload'], 'original normal prepared policy/payload required')
    native = w.read_json(directory / 'native-queue-intent.json')
    if native:
        started = w._parse_observed_at(native.get('started_at'))
        checked = w._parse_observed_at(policies[0].get('checked_at'))
        require(native.get('thread_id') == request['target_thread_id']
                and native.get('payload_sha256') == request['payload_sha256']
                and native.get('policy_decision_id') == intent['policy_decision_id']
                and native.get('transport') == 'official_codex_queue'
                and started is not None and checked is not None
                and checked <= started <= dt.datetime.now(dt.timezone.utc),
                'real original daily transport intent identity/hash/policy/time required')
    return native


def reply_effect(root, task_id, action_id):
    """Read original effect, including unknown; never sends or changes a receipt."""
    events = [e for e in w.read_jsonl(Path(root) / w.WORKFLOW_EVENTS) if e.get('task_id') == task_id
              and e.get('details', {}).get('routine_decision_reply_intent', {}).get('action_id') == action_id]
    daily_path = w.safe_path(root, daily_reply_directory(task_id, action_id)) / 'routine-reply-intent.json'
    require(len(events) + int(daily_path.exists()) == 1, 'one original routine reply intent required')
    intent = json.loads(daily_path.read_text()) if daily_path.exists() else events[0]['details']['routine_decision_reply_intent']
    require(intent.get('action_id') == action_id, 'original reply action cannot change')
    request = doc(root, intent['request'])
    import goal_delivery_runtime as g
    route = message_route(root, g.restore_goal(root, w.read_json(w.snapshot_path(root, task_id))), request)
    require(request.get('task_id') == task_id and request.get('action_id') == action_id,
            'original reply request identity required')
    native = _daily_reply_intent_readback(root, intent, request, route) if daily_path.exists() else None
    path = w.safe_path(root, intent['directory']) / 'native-queue-result.json'
    if not path.exists():
        return {'state': 'effect_unknown', 'repeat_allowed': False, 'intent': intent}
    result = json.loads(path.read_text())
    if daily_path.exists():
        finished = w._parse_observed_at(result.get('finished_at'))
        require(native and all(result.get(k) == native.get(k) for k in native)
                and finished is not None and w._parse_observed_at(native['started_at']) <= finished <= dt.datetime.now(dt.timezone.utc),
                'original complete daily transport chronology and intent fields required')
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
