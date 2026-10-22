"""Pinned window rotations: historical evidence lookup, never production authority.

Only read-side source validators may use historical_registry/result_binding.
Dispatch, account writes and new receipts continue to use the current registry.
"""
from __future__ import annotations
import argparse
import copy
from contextlib import contextmanager
from contextvars import ContextVar
import datetime as dt
import hashlib
from functools import wraps
import json
from pathlib import Path
import workflow_control as w

SCHEMA = 'department-window-rotation/v1'
REGISTRY = 'data/department-registry.json'
BASE = 'logs/handoffs/2026-10-20-clean-department-window-rotation-v1'
OUTPUT = BASE + '/runtime-migration'
_VALIDATION = ContextVar('rotation_historical_receipt_validation', default=None)


def validation_registry(root):
    state = _VALIDATION.get()
    return copy.deepcopy(state[1]) if state and state[0] == str(Path(root).resolve()) else None


def prohibit_validation_write():
    if _VALIDATION.get() is not None:
        raise w.WorkflowError('historical rotation validation is read-only; no policy, receipt or write allowed')


@contextmanager
def historical_receipt_validation(root, receipt):
    """Run the ORIGINAL semantic validator with its pinned original identities.

    This does not skip any proof, plan, hash-chain or evidence check. The scope
    is task-local (ContextVar), and all control writers/policy are guarded.
    """
    if _VALIDATION.get() is not None:
        yield
        return
    registry = historical_registry(root, receipt, receipt_only=True)
    token = _VALIDATION.set((str(Path(root).resolve()), registry)) if registry is not None else None
    try:
        yield
    finally:
        if token is not None:
            _VALIDATION.reset(token)


def historical_assignment_validator(function):
    """Only exact frozen assignment validation; the scope ends before recording."""
    @wraps(function)
    def validated(root, item, *args, **kwargs):
        if _VALIDATION.get() is not None:
            return function(root, item, *args, **kwargs)
        registry = historical_registry(root, item, require_match=True)
        token = _VALIDATION.set((str(Path(root).resolve()), registry)) if registry is not None else None
        try:
            return function(root, item, *args, **kwargs)
        finally:
            if token is not None:
                _VALIDATION.reset(token)
    return validated


def _pin(root, pin):
    if not isinstance(pin, dict) or w.file_digest(root, pin.get('path', '')) != pin:
        raise w.WorkflowError('rotation evidence pin changed')
    return w.read_json(w.safe_path(root, pin['path']))


def _binding(document, role):
    rows = [x for x in document.get('departments', []) if x.get('id') == role]
    if len(rows) > 1:
        raise w.WorkflowError('ambiguous rotation role')
    return (rows[0].get('chat_binding', {}) if rows else
            document.get('collaboration_bindings', {}).get(role, {}))


def _id(binding):
    return binding.get('task_id', binding.get('thread_id'))


def _identity(binding):
    return {'task_id': _id(binding), **{k: binding.get(k) for k in
            ('title', 'project_id', 'cwd', 'host_id', 'sidebar_section_id')}}


# Actual same-thread sidebar recovery, frozen independently from old rotation.
# It proves metadata equivalence only, never health or production authority.
_CURRENT_SIDEBAR_RECOVERY = {"path": "backups/fc-20261021-owner-delegated-nonpayment-decisions-repair-v1/current-sidebar-metadata-recovery-v1/journal.json",
    "sha256": "ba9f5242f6c79c7eacd718d2eec4f8d2eca10c97b2e15718f2a11a46c3019352", "size": 7547}


def _current_metadata_identity(root, role, current, original):
    if _identity(current) == _identity(original):
        return True
    keys = ('task_id','title','project_id','cwd','host_id')
    if any(_identity(current).get(k) != _identity(original).get(k) for k in keys):
        return False
    try:
        journal = _pin(root, _CURRENT_SIDEBAR_RECOVERY)
        backup = _pin(root, journal['backup'])
        inventory = _pin(root, journal['inventory'])
        changes = [x for x in journal.get('changes', []) if x.get('role') == role]
        if (journal.get('schema') != 'exact-current-sidebar-metadata-CAS/v1'
                or journal.get('state') != 'applied' or journal.get('only_sidebar_metadata_changed') is not True
                or len(changes) != 1 or _identity(_binding(backup,role)) != _identity(original)):
            return False
        change = changes[0]
        rows = [x for x in inventory.get('threads',[])+inventory.get('pinnedThreads',[]) if x.get('id') == _id(current)]
        memberships = [x['sectionId'] for x in inventory.get('sections',[]) if 'codex:thread:local:'+str(_id(current)) in x.get('itemKeys',[])]
        return (len(rows) == 1 and memberships == [change['after']]
                and change['before'] == original.get('sidebar_section_id')
                and current.get('sidebar_section_id') == change['after']
                and all(current.get(k) == v for k,v in change['fixed_identity'].items())
                and all(rows[0].get(k) == current.get(v) for k,v in
                        {'id':'task_id','title':'title','cwd':'cwd','projectId':'project_id'}.items()))
    except (w.WorkflowError,KeyError,TypeError,ValueError,OSError):
        return False


def _records(root):
    document = w.read_json(Path(root) / REGISTRY)
    seen = set()
    for pin in document.get('window_rotation_records', []):
        row = _pin(root, pin)
        validate_record(root, row, pin)
        role = row.get('role')
        if (row.get('schema') != SCHEMA or role in seen
                or row.get('production_permission_inherited') is not False
                or row.get('old_binding', {}).get('project_id') != row.get('new_binding', {}).get('project_id')
                or row.get('old_binding', {}).get('cwd') != row.get('new_binding', {}).get('cwd')
                or _id(row.get('old_binding', {})) == _id(row.get('new_binding', {}))
                or not _current_metadata_identity(root, role, _binding(document, role), row.get('new_binding', {}))
                or _binding(document, role).get('rotation_record') != pin):
            raise w.WorkflowError('untrusted, wrong-role or inactive rotation mapping')
        seen.add(role)
        yield row


def _metadata_assignment_projection(root, subject, registry):
    """Read one actually registered pre-CAS queue source; no identity/rights transfer."""
    role=subject.get('department')
    if (subject.get('schema')!='goal-current-assignment/v2'or subject.get('source_kind')!='official_native_queue'
            or role not in registry):return False
    if not (Path(root)/_CURRENT_SIDEBAR_RECOVERY['path']).is_file():return False
    index=w.read_json(Path(root)/'data/department-current-assignment.json')
    pins=[index.get('assignments',{}).get(role),*index.get('suspended_assignments',{}).get(role,[])]
    if not any(pin and _pin(root,pin)==subject for pin in pins):return False
    journal=_pin(root,_CURRENT_SIDEBAR_RECOVERY);backup=_pin(root,journal['backup'])
    old=_binding(backup,role);current=registry[role]['chat_binding']
    if not _current_metadata_identity(root,role,current,old):return False
    request=_pin(root,subject.get('original_prepare_request'))
    if (current.get('sidebar_section_id')==old.get('sidebar_section_id')
            or any(request.get(k)!=old.get(v)for k,v in
                {'target_thread_id':'task_id','target_thread_title':'title','target_project_id':'project_id',
                 'target_cwd':'cwd','target_sidebar_section_id':'sidebar_section_id'}.items())):return False
    # Preserve current identity and health; only source validation sees its real prior sidebar.
    registry[role]['chat_binding']['sidebar_section_id']=old['sidebar_section_id']
    return True


def historical_registry(root, subject, *, receipt_only=False, require_match=False):
    """Resolve a previously frozen assignment only; never a new execution request."""
    registry = copy.deepcopy(w.department_registry(root))
    subject_hash = w.sha256_value(subject)
    matched = (not receipt_only and _metadata_assignment_projection(root,subject,registry))
    for row in _records(root):
        history = _pin(root, row['history'])
        entry = history.get('receipts' if receipt_only else 'assignments', {}).get(subject_hash)
        if entry is None:
            continue
        if ((not receipt_only and _pin(root, entry['pin']) != subject)
                or subject.get('department') != entry['department'] or subject.get('task_id') != entry['task_id']):
            raise w.WorkflowError('historical rotation assignment differs')
        role = row['role']
        matched = True
        if role in registry:
            registry[role]['chat_binding'] = copy.deepcopy(row['old_binding'])
    return registry if matched or not (receipt_only or require_match) else None


def result_binding(root, identity, outbox):
    """The exact already-queued result may retain its original producer chat."""
    role = identity['sender_department']
    binding = w.department_registry(root).get(role, {}).get('chat_binding', {})
    for row in _records(root):
        if row['role'] != role:
            continue
        history = _pin(root, row['history'])
        entry = history.get('results', {}).get(w.sha256_value(identity))
        if entry is not None:
            if entry['outbox'] != outbox:
                raise w.WorkflowError('historical queued result pin differs')
            box = _pin(root, outbox)
            original_thread = entry.get('source_thread_id') or box.get('fixed_chat_task_id', box.get('chat_task_id'))
            if original_thread != _id(row['old_binding']):
                raise w.WorkflowError('historical queued sender differs from rotation')
            binding = row['old_binding']
    return binding


def frozen_ready_binding(root, source, fixed_id):
    """Read one exact pre-rotation READY queue; never admit a new queue source."""
    keys = ('task_id', 'sender_department', 'candidate_version', 'result_sha256')
    if (source.get('event') != 'notification_queued'
            or source.get('result_source_phase') != 'delivery_ready'
            or any(not source.get(k) for k in keys)):
        raise w.WorkflowError('exact frozen queued READY source required')
    identity = {k: source[k] for k in keys}
    queues = [row for row in w._result_handoff_rows(root, identity['task_id'])
              if row.get('event') == 'notification_queued'
              and all(row.get(k) == v for k, v in identity.items())]
    if len(queues) != 1 or queues[0] != source:
        raise w.WorkflowError('original frozen queued READY provenance differs')
    for rotation in _records(root):
        if rotation['role'] != identity['sender_department']:
            continue
        entry = _pin(root, rotation['history']).get('results', {}).get(w.sha256_value(identity))
        if (entry is None or any(source.get(k) != entry.get(k) for k in
                                  ('record_id', 'record_hash', 'outbox', 'source_thread_id'))
                or source.get('source_thread_id') != fixed_id
                or _id(rotation['old_binding']) != fixed_id):
            raise w.WorkflowError('READY source was not frozen in the trusted rotation')
        _pin(root, source['outbox'])
        return copy.deepcopy(rotation['old_binding'])
    raise w.WorkflowError('trusted same-role queued READY rotation required')



def continued_ready_prefix(root, request, fixed_id, observed, receipts):
    """Read a real frozen original assignment for a current same-role READY.

    This proves result provenance only. It never creates dispatch/ACK, rewrites
    old metadata, or inherits a production permit. Later receipts cannot replace
    the actual prefix that preceded the immutable declaration.
    """
    from goal_continuity import _dispatch_source, _task
    if (request.get('result_source_phase') != 'delivery_ready' or observed is None
            or request.get('source_thread_id') != fixed_id):
        return None
    role, task = request['sender_department'], request['task_id']
    rotations = [row for row in _records(root) if row['role'] == role
                 and _id(row['new_binding']) == fixed_id]
    if not rotations:
        return None
    rotation = rotations[0]
    snapshot = _task(root, task); goal = snapshot['goal_delivery']
    if (role not in goal['producer_departments'] or snapshot.get('current_state') in w.TERMINAL_STATES
            or not any(row.get('department') == role and row.get('chat_task_id') == _id(rotation['old_binding'])
                       for row in snapshot.get('departments', []))):
        return None
    prior = [row for row in receipts if w._parse_observed_at(row.get('created_at')) is not None
             and w._parse_observed_at(row['created_at']) <= observed]
    # A real newer dispatch before this READY keeps its own ordinary ACK gate.
    if any(row.get('department') == role and row.get('chat_task_id') == fixed_id
           and row.get('receipt_type') in {'dispatch_sent', 'dispatch_failed'} for row in prior):
        return None
    assignments = [entry for entry in _pin(root, rotation['history']).get('assignments', {}).values()
                   if entry['task_id'] == task and entry['department'] == role]
    from sales_original_assignment import recorded_entries as restored_sales_entries
    assignments += restored_sales_entries(root,task,role)
    authenticated = []
    for entry in assignments:
        item = _pin(root, entry['pin'])
        if item.get('schema') == 'restored-original-sales-assignment-source/v1':
            from sales_original_assignment import validate as validate_original_sales
            _, dispatch = validate_original_sales(root,item)
        else:
            _, dispatch = _dispatch_source(root, item)
        if dispatch in prior and dispatch.get('chat_task_id') == _id(rotation['old_binding']):
            authenticated.append((entry['pin'], dispatch))
    if not authenticated:
        return None
    old = rotation['old_binding']
    original = [row for row in prior if row.get('department') == role
                and row.get('chat_task_id') == _id(old)]
    sends = [(index, row) for index, row in enumerate(original)
             if row.get('receipt_type') in {'dispatch_sent', 'dispatch_failed'}]
    if not sends or sends[-1][1]['receipt_type'] != 'dispatch_sent':
        return None
    index, dispatch = sends[-1]
    policies = [row for row in w.read_jsonl(Path(root)/w.POLICY_DECISIONS)
                if row.get('decision_id') == dispatch.get('policy_decision_id')]
    if len(policies) != 1:
        return None
    policy = policies[0]
    expected = {'status': 'allow', 'routing_status': 'routing_allowed', 'task_id': task,
                'target_department': role, 'target_thread_id': _id(old), 'target_cwd': old['cwd'],
                'source_project_id': old['project_id'], 'target_project_id': old['project_id'],
                'action_class': 'thread_message', 'scope': dispatch.get('scope'),
                'action_id': dispatch.get('action_id')}
    if (any(policy.get(key) != value for key, value in expected.items())
            or policy.get('department') not in {'operations', goal['responsible_assistant'], goal['primary_owner']}
            or dispatch.get('scope') not in goal['authorized_scope']):
        return None
    acknowledgments = [row for row in original[index+1:] if row.get('receipt_type') == 'chat_ack'
                       and row.get('ack_nonempty') is True
                       and w._parse_observed_at(dispatch['created_at']) <= w._parse_observed_at(row['created_at'])]
    if not acknowledgments:
        return None
    ack = acknowledgments[0]
    if any(row.get('supersedes_receipt_id') in {dispatch['receipt_id'], ack['receipt_id']}
           for row in receipts if row.get('supersedes_receipt_id')):
        return None
    for row in (dispatch, ack):
        if not row.get('evidence'):
            return None
        for pin in row['evidence']:
            if w.file_digest(root, pin.get('path', '')) != pin:
                raise w.WorkflowError('original continuation dispatch/ACK evidence changed')
    assignment = max(authenticated, key=lambda item: w._parse_observed_at(item[1]['created_at']))[0]
    return {'schema': 'rotation-original-READY-provenance/v1',
            'rotation': w.department_registry(root)[role]['chat_binding']['rotation_record'],
            'assignment': assignment, 'task_id': task, 'department': role,
            'original_thread_id': _id(old), 'current_thread_id': fixed_id,
            'dispatch_receipt_id': dispatch['receipt_id'], 'dispatch_receipt_hash': dispatch['receipt_hash'],
            'ack_receipt_id': ack['receipt_id'], 'ack_receipt_hash': ack['receipt_hash'],
            'production_permission_inherited': False}


def continued_result_source(root, request, fixed_id):
    """Revalidate one real current READY or its committed queue, never a caller flag."""
    from goal_continuity import ready_source
    if request.get('event') == 'notification_queued':
        source = request
    else:
        keys = ('sender_department', 'candidate_version', 'result_sha256')
        queues = [row for row in w._result_handoff_rows(root, request['task_id'])
                  if row.get('event') == 'notification_queued' and row.get('original_rotation_continuation')
                  and all(row.get(key) == request.get(key) for key in keys)]
        if not queues:
            return None
        if len(queues) != 1:
            raise w.WorkflowError('one exact committed original continuation queue required')
        source = {**queues[0], 'outbox_path': queues[0]['outbox']['path']}
    if source.get('result_source_phase') != 'delivery_ready':
        return None
    receipts, invalid = w._validate_receipt_chain(root, request['task_id'])
    if invalid:
        raise w.WorkflowError('intact original continuation receipt chain required')
    prefix = continued_ready_prefix(root, source, fixed_id,
                                    w._parse_observed_at(source.get('reply_observed_at')), receipts)
    if prefix is None:
        return None
    checked = ready_source(root, source, fixed_id)
    if checked.get('original_rotation_continuation') != prefix:
        raise w.WorkflowError('actual continued READY source proof differs')
    if request.get('event') != 'notification_queued' and source['original_rotation_continuation'] != prefix:
        raise w.WorkflowError('committed original continuation provenance changed')
    return checked


def _frozen_queue(root, history, queued):
    identity = {k: queued[k] for k in ('task_id', 'sender_department', 'candidate_version', 'result_sha256')}
    entry = history.get('results', {}).get(w.sha256_value(identity))
    if (entry is None or any(queued.get(k) != entry.get(k) for k in
                            ('record_id', 'record_hash', 'outbox', 'source_thread_id'))):
        return False
    box = _pin(root, queued['outbox'])
    original = queued.get('source_thread_id') or box.get('fixed_chat_task_id', box.get('chat_task_id'))
    return any(r['role'] == identity['sender_department'] and _id(r['old_binding']) == original
               for r in _records(root))


def _frozen_dispatched_role(root, snapshot, rotation, receipts, results):
    """Use actual old dispatch/ACK and a frozen queued result, never an assignment stub."""
    role = rotation['role']; old = _id(rotation['old_binding']); goal = snapshot['goal_delivery']
    history = _pin(root, rotation['history'])
    queues = [q for q in results if q.get('event') == 'notification_queued'
              and q.get('sender_department') == role and _frozen_queue(root, history, q)]
    policies = w.read_jsonl(Path(root) / w.POLICY_DECISIONS)
    for index, sent in enumerate(receipts):
        if (sent.get('receipt_type') != 'dispatch_sent' or sent.get('department') != role
                or sent.get('chat_task_id') != old or sent.get('scope') not in goal['authorized_scope']):
            continue
        allowed = [p for p in policies if p.get('decision_id') == sent.get('policy_decision_id')]
        if len(allowed) != 1:
            continue
        policy = allowed[0]
        expected = {'status': 'allow', 'routing_status': 'routing_allowed', 'task_id': snapshot['task_id'],
                    'department': goal['responsible_assistant'], 'target_department': role,
                    'target_thread_id': old, 'action_id': sent.get('action_id'),
                    'action_class': 'thread_message', 'scope': sent.get('scope')}
        if any(policy.get(k) != v for k, v in expected.items()):
            continue
        project = rotation['old_binding'].get('project_id')
        if policy.get('source_project_id') != project or policy.get('target_project_id') != project:
            continue
        actions = [a for a in goal.get('approved_actions', []) if all(a.get(k) == policy.get(k)
                   for k in ('task_id', 'target_department', 'target_thread_id', 'action_id',
                             'action_class', 'scope', 'payload_sha256'))]
        if (len(actions) != 1 or actions[0].get('sender_department') != goal['responsible_assistant']
                or actions[0].get('source_project_id') != project
                or actions[0].get('target_project_id') != project
                or w.file_digest(root, actions[0]['payload']['path']) != actions[0]['payload']):
            continue
        for ack in receipts[index + 1:]:
            if ack.get('department') != role or ack.get('chat_task_id') != old:
                continue
            if ack.get('receipt_type') in {'dispatch_sent', 'dispatch_failed'}:
                break
            if ack.get('receipt_type') == 'chat_ack' and ack.get('ack_nonempty') is True:
                if any(r.get('supersedes_receipt_id') in {sent.get('receipt_id'), ack.get('receipt_id')}
                       for r in receipts if r.get('supersedes_receipt_id')):
                    continue
                ack_at = w._parse_observed_at(ack.get('created_at'))
                if ack_at is not None and any(w._parse_observed_at(q.get('created_at')) is not None
                        and ack_at <= w._parse_observed_at(q['created_at']) for q in queues):
                    return True
    return False


def _planned_action_source(root, snapshot, role, rotation, planned):
    """Authenticate an original planned participant without inventing assignment.

    This only projects the plan. Ordinary routing still requires the requested
    exact approved action, current identity, dependencies and unsent action.
    The same proof remains usable for its later current dispatch/ACK receipts.
    """
    from goal_delivery_runtime import restore_goal, approved_action
    try:
        task = snapshot['task_id']; goal = snapshot['goal_delivery']
        original = _pin(root, snapshot['goal_contract'])
        if (role not in original.get('producer_departments', [])
                or any(original.get(k) != goal.get(k) for k in
                       ('producer_departments', 'responsible_assistant', 'authorized_scope'))
                or restore_goal(root, snapshot).get('goal_delivery') != goal
                or w.file_digest(root, goal['authorization_pin']['path']) != goal['authorization_pin']
                or w.validate_workflow_events(root, task)):
            return False
        events = [e for e in w.read_jsonl(Path(root) / w.WORKFLOW_EVENTS) if e.get('task_id') == task]
        origins = [e['details'] for e in events if e.get('details', {}).get('goal_contract')
                   == snapshot['goal_contract'] and isinstance(e.get('details', {}).get('departments'), list)
                   and e['details'].get('request_hash') == snapshot.get('request_hash')]
        if len(origins) != 1 or [p for p in origins[0]['departments'] if p.get('department') == role] != [planned]:
            return False
        receipts, invalid = w._validate_receipt_chain(root, task)
        if invalid:
            return False
        results = w._result_handoff_rows(root, task)
        old_sent = any(r.get('department') == role and r.get('receipt_type') == 'dispatch_sent'
                       and r.get('chat_task_id') == _id(rotation['old_binding']) for r in receipts)
        if old_sent and not _frozen_dispatched_role(root, snapshot, rotation, receipts, results):
            return False
        assistant = goal['responsible_assistant']
        source = w.department_registry(root).get(assistant, {}).get('chat_binding', {})
        fixed = rotation['new_binding']
        if (source.get('project_id') != fixed.get('project_id')
                or not w._same_resolved_path(str(source.get('cwd') or ''), str(Path(root).resolve()))):
            return False
        for event in events:
            pin = event.get('details', {}).get('approved_message_prepared')
            if not pin:
                continue
            action = _pin(root, pin)
            expected = {'task_id': task, 'sender_department': assistant, 'target_department': role,
                        'action_class': 'thread_message', 'source_project_id': source.get('project_id'),
                        **{name: fixed[key] for name, key in {
                            'target_thread_id': 'task_id', 'target_thread_title': 'title',
                            'target_project_id': 'project_id', 'target_cwd': 'cwd',
                            'target_sidebar_section_id': 'sidebar_section_id'}.items()}}
            if (any(action.get(k) != v for k, v in expected.items())
                    or action.get('scope') not in goal['authorized_scope']
                    or not action.get('action_id') or approved_action(root, snapshot, action) != action):
                continue
            decisions = [(i, r) for i, r in enumerate(results)
                         if r.get('event') == 'controller_decision'
                         and r.get('record_id') == action.get('decision_record_id')]
            if len(decisions) != 1:
                continue
            index, decision = decisions[0]
            if (decision.get('decision') not in {'continue', 'rework', 'accept'}
                    or decision.get('coordinator_role') != assistant or decision.get('next_owner') != role
                    or decision.get('sender_department') not in original['producer_departments']):
                continue
            keys = ('task_id', 'sender_department', 'candidate_version', 'result_sha256')
            if not any(r.get('event') == 'controller_received' and r.get('coordinator_role') == assistant
                       and all(r.get(k) == decision.get(k) for k in keys) for r in results[:index]):
                continue
            if decision.get('coordinator_owner') not in {_id(source), assistant + ':' + str(_id(source))}:
                old_owners = [_id(r['old_binding']) for r in _records(root)
                              if r['role'] == assistant and _id(r['new_binding']) == _id(source)]
                if (len(old_owners) != 1 or decision.get('coordinator_owner') not in
                        {old_owners[0], assistant + ':' + str(old_owners[0])}
                        or not any(q.get('event') == 'notification_queued'
                                   and all(q.get(k) == decision.get(k) for k in keys)
                                   and _frozen_queue(root, _pin(root, rotation['history']), q)
                                   for q in results[:index])):
                    continue
            _pin(root, decision['outbox'])
            return True
        return False
    except (w.WorkflowError, OSError, ValueError, TypeError, KeyError, AttributeError):
        return False


def current_dispatch_snapshot(root, snapshot, role):
    """Project one frozen same-role plan onto its verified current message target.

    Callers use this only for ordinary thread messages and their transport
    receipts. The original snapshot, authority and production permits stay intact.
    """
    if (not isinstance(snapshot, dict) or not isinstance(snapshot.get('goal_delivery'), dict)
            or snapshot.get('current_state') in w.TERMINAL_STATES
            or snapshot.get('workflow_successor_link')):
        return snapshot
    planned = [x for x in snapshot.get('departments', []) if x.get('department') == role]
    if len(planned) != 1:
        return snapshot
    for row in _records(root):
        if row['role'] != role or planned[0].get('chat_task_id') != _id(row['old_binding']):
            continue
        history = _pin(root, row['history'])
        sources = [entry for entry in history.get('assignments', {}).values()
                   if entry['task_id'] == snapshot.get('task_id') and entry['department'] == role]
        if not sources and not _planned_action_source(root, snapshot, role, row, planned[0]):
            return snapshot
        for entry in sources:
            original = _pin(root, entry['pin'])
            if original.get('task_id') != entry['task_id'] or original.get('department') != role:
                raise w.WorkflowError('frozen same-role dispatch task differs')
        projected = copy.deepcopy(snapshot)
        next(x for x in projected['departments'] if x['department'] == role)['chat_task_id'] = _id(row['new_binding'])
        return projected
    return snapshot


def external_write_blocked(root, role):
    # This rotation intentionally creates no account/channel admission. A future
    # admission must be a separately reviewed exact interface, not an editable flag.
    return any(row['role'] == role for row in _records(root))


def frozen_responsibility_continuation(root, snapshot, receipts, *, sender_department,
                                      target_department, target_thread_id, scope):
    """Retain an actually assigned coordination responsibility across one rotation.

    A frozen assignment must still pass its original native-send validator, and
    an original same-task ACK must have real native content. This is only an
    operations dependency source; it creates no producer result or new receipt.
    """
    from goal_continuity import _dispatch_source
    from goal_delivery_runtime import _collaboration_native
    try:
        goal = snapshot.get('goal_delivery', {})
        task = snapshot['task_id']
        contract = goal.get('coordination_review_contract', {})
        if (sender_department != 'operations' or goal.get('primary_owner') != sender_department
                or goal.get('producer_departments') != [sender_department]
                or goal.get('responsible_assistant') != target_department
                or scope not in goal.get('authorized_scope', []) or goal.get('required_execution_actions')
                or contract.get('task_id') != task or contract.get('producer') != sender_department
                or contract.get('reviewer') != target_department
                or contract.get('not_professional_producer') is not True
                or contract.get('prepared_only') is not True):
            return False
        original_goal = _pin(root, snapshot['goal_contract'])
        if (original_goal.get('required_execution_actions')
                or any(original_goal.get(k) != goal.get(k) for k in (
                'primary_owner', 'producer_departments', 'responsible_assistant',
                'authorized_scope', 'coordination_review_contract'))
                or w.validate_workflow_events(root, task)
                or not any(e.get('task_id') == task and e.get('details', {}).get('goal_contract')
                           == snapshot['goal_contract'] for e in w.read_jsonl(Path(root) / w.WORKFLOW_EVENTS))):
            return False
        for rotation in _records(root):
            if rotation['role'] != target_department or _id(rotation['new_binding']) != target_thread_id:
                continue
            old = rotation['old_binding']
            sources = [e for e in _pin(root, rotation['history']).get('assignments', {}).values()
                       if e['task_id'] == task and e['department'] == target_department]
            assigned = False
            for entry in sources:
                item = _pin(root, entry['pin'])
                if item.get('sender_department') != sender_department:
                    continue
                _, dispatch = _dispatch_source(root, item)
                if dispatch in receipts and dispatch.get('chat_task_id') == _id(old) and dispatch.get('scope') == scope:
                    assigned = True
            if not assigned:
                return False
            policies = {p.get('decision_id'): p for p in w.read_jsonl(Path(root) / w.POLICY_DECISIONS)}
            previous_dispatch = None
            for receipt in receipts:
                if receipt.get('department') != target_department or receipt.get('chat_task_id') != _id(old):
                    continue
                if receipt.get('receipt_type') in {'dispatch_sent', 'dispatch_failed'}:
                    previous_dispatch = receipt if receipt['receipt_type'] == 'dispatch_sent' else None
                    continue
                if (not previous_dispatch or receipt.get('receipt_type') != 'chat_ack'
                        or receipt.get('ack_nonempty') is not True):
                    continue
                if any(r.get('supersedes_receipt_id') in {
                        previous_dispatch.get('receipt_id'), receipt.get('receipt_id')}
                       for r in receipts if r.get('supersedes_receipt_id')):
                    continue
                policy = policies.get(previous_dispatch.get('policy_decision_id'), {})
                if any(policy.get(k) != v for k, v in {
                        'status': 'allow', 'routing_status': 'routing_allowed', 'task_id': task,
                        'department': sender_department, 'action_class': 'thread_message', 'scope': scope,
                        'target_department': target_department, 'target_thread_id': _id(old)}.items()):
                    continue
                if (previous_dispatch.get('scope') != scope
                        or previous_dispatch.get('action_class') != 'thread_message'
                        or policy.get('source_project_id') != old.get('project_id')
                        or policy.get('target_project_id') != old.get('project_id')):
                    continue
                policy_at = w._parse_observed_at(policy.get('checked_at'))
                ack_at = w._parse_observed_at(receipt.get('created_at'))
                if policy_at is None or ack_at is None or policy_at > ack_at:
                    continue
                for evidence in receipt.get('evidence', []):
                    page = _collaboration_native(root, evidence)
                    if any(page.get('thread', {}).get(k) != old.get(v) for k, v in
                           {'id': 'task_id', 'title': 'title', 'cwd': 'cwd'}.items()):
                        continue
                    for turn in page.get('turns', []):
                        started = turn.get('startedAt')
                        if (turn.get('id') and turn.get('status') in {'inProgress', 'completed'}
                                and not turn.get('error') and type(started) in {int, float}
                                and policy_at.timestamp() <= started <= ack_at.timestamp()
                                and any(m.get('type') == 'agentMessage' and m.get('id')
                                        and isinstance(m.get('text'), str) and m['text'].strip()
                                        for m in turn.get('items', []) if isinstance(m, dict))):
                            return True
        return False
    except (w.WorkflowError, OSError, ValueError, TypeError, KeyError, AttributeError):
        return False


def _write_once(root, relative, value):
    path = w.safe_path(root, relative)
    if path.exists():
        if w.read_json(path) != value:
            raise w.WorkflowError('immutable rotation artifact already exists with different bytes: ' + str(relative))
    else:
        w.atomic_write_json(path, value)
    return w.file_digest(root, relative)


def validate_record(root, row, pin):
    """Authenticate semantic fields again at apply/read time, not just a file hash."""
    role = row.get('role')
    if (row.get('schema') != SCHEMA or row.get('production_permission_inherited') is not False
            or row.get('old_permits_reusable_by_new_window') is not False
            or pin.get('path') != OUTPUT + '/records/' + str(role) + '-v2.json'
            or row.get('manifest', {}).get('path') != OUTPUT + '/manifest-frozen.json'
            or row.get('handoff', {}).get('path') != OUTPUT + '/native/handoff-' + str(role) + '.json'):
        raise w.WorkflowError('trusted exact rotation record location and scope required')
    manifest = _pin(root, row['manifest'])
    entries = [x for x in manifest.get('records', []) if x.get('role') == role]
    if len(entries) != 1:
        raise w.WorkflowError('one owner-manifest role required')
    entry = entries[0]
    old, new = row['old_binding'], row['new_binding']
    handoff = _pin(root, row['handoff'])
    if (handoff.get('role') != role or _id(handoff.get('old_binding', {})) != _id(old)
            or _id(entry['old_binding']) != _id(old) or entry.get('new_thread_id') != _id(new)
            or _id(new) == _id(old) or not _id(new)
            or any(old.get(k) != new.get(k) or old.get(k) != entry['old_binding'].get(k)
                   for k in ('project_id', 'cwd'))):
        raise w.WorkflowError('same-role/project/cwd rotation identity required')
    inventory = _pin(root, row['inventory'])
    candidates = [x for x in inventory.get('threads', []) + inventory.get('pinnedThreads', [])
                  if x.get('id') == _id(new)]
    if (len(candidates) != 1 or any(candidates[0].get(k) != new.get(v) for k, v in
            (('id', 'task_id'), ('title', 'title'), ('projectId', 'project_id'), ('cwd', 'cwd')))):
        raise w.WorkflowError('new actual inventory identity differs')
    native = _pin(root, row['new_native'])
    prior = _pin(root, row['old_native'])
    if any(native.get('thread', {}).get(k) != new.get(v) for k, v in
           (('id', 'task_id'), ('title', 'title'), ('cwd', 'cwd'))):
        raise w.WorkflowError('new actual native identity differs')
    if any(prior.get('thread', {}).get(k) != _identity(old).get(v) for k, v in
           (('id', 'task_id'), ('title', 'title'), ('cwd', 'cwd'))):
        raise w.WorkflowError('old actual native identity differs')
    status = prior['thread'].get('status', {})
    status = status.get('type') if isinstance(status, dict) else status
    if (status not in ('idle', 'notLoaded') or not prior.get('turns')
            or any(t.get('status') not in ('completed', 'failed', 'interrupted') for t in prior['turns'])):
        raise w.WorkflowError('old native window is not terminal')
    finals = [m for t in native.get('turns', []) if t.get('id') == row['completed_handoff_turn']
              and t.get('status') == 'completed' and not t.get('error')
              for m in t.get('items', []) if m.get('type') == 'agentMessage'
              and m.get('phase') == 'final_answer' and isinstance(m.get('text'), str) and m['text'].strip()]
    if (len(finals) != 1 or finals[0].get('id') != new.get('last_reply_ref')
            or hashlib.sha256(finals[0]['text'].encode()).hexdigest() != new.get('last_reply_sha256')):
        raise w.WorkflowError('actual new nonempty final reply required')
    _pin(root, row['history'])


def freeze_history(root):
    path = OUTPUT + '/history-v2.json'
    if w.safe_path(root, path).exists():
        return w.file_digest(root, path)
    sources = w.read_json(Path(root) / 'data/department-current-assignment.json')
    history = {'schema': 'rotation-historical-evidence/v2', 'assignments': {}, 'results': {}, 'receipts': {}}
    pins = list(sources.get('assignments', {}).values())
    pins += [p for stack in sources.get('suspended_assignments', {}).values() for p in stack]
    for pin in pins:
        item = _pin(root, pin)
        history['assignments'][w.sha256_value(item)] = {
            'pin': pin, 'department': item['department'], 'task_id': item['task_id']}
    for task in {entry['task_id'] for entry in history['assignments'].values()}:
        for receipt in w.read_jsonl(w.receipts_path(root, task)):
            if receipt.get('receipt_type') in ('qa_verdict', 'health_reconciled'):
                history['receipts'][w.sha256_value(receipt)] = {
                    'department': receipt.get('department'), 'task_id': receipt.get('task_id')}
    for ledger in sorted((Path(root) / 'logs/result-handoffs').glob('*.jsonl')):
        for row in w.read_jsonl(ledger):
            if row.get('event') != 'notification_queued' or not row.get('outbox'):
                continue
            identity = {k: row[k] for k in ('task_id', 'sender_department', 'candidate_version', 'result_sha256')}
            entry = {k: row.get(k) for k in ('outbox', 'source_thread_id', 'record_hash', 'record_id')}
            key = w.sha256_value(identity)
            if key in history['results'] and history['results'][key] != entry:
                raise w.WorkflowError('ambiguous historical result queue')
            history['results'][key] = entry
    return _write_once(root, path, history)


def prepare(root, manifest_path, inventory_path):
    """Freeze an auditable plan; no registry or authority mutation."""
    frozen_path = OUTPUT + '/manifest-frozen.json'
    if w.safe_path(root, frozen_path).exists():
        manifest_pin = w.file_digest(root, frozen_path)
    else:
        manifest_pin = _write_once(root, frozen_path, w.read_json(w.safe_path(root, manifest_path)))
    manifest = _pin(root, manifest_pin)
    inventory_pin = w.file_digest(root, inventory_path)
    inventory = _pin(root, inventory_pin)
    rows = inventory.get('threads', []) + inventory.get('pinnedThreads', [])
    document = w.read_json(Path(root) / REGISTRY)
    history = freeze_history(root)
    records, blocked = [], []
    if manifest.get('schema') != 'flashcast-clean-window-rotation/v1' or not manifest.get('owner_request'):
        raise w.WorkflowError('owner-requested rotation manifest required')
    seen_roles, seen_threads = set(), set()
    for item in manifest['records']:
        role = item['role']
        if role in seen_roles or item.get('new_thread_id') in seen_threads:
            raise w.WorkflowError('unique role and new window required')
        seen_roles.add(role); seen_threads.add(item.get('new_thread_id'))
        try:
            existing = Path(root) / OUTPUT / 'records' / (role + '-v2.json')
            if existing.exists():
                pin = w.file_digest(root, str(existing.relative_to(root)))
                validate_record(root, _pin(root, pin), pin)
                records.append(pin)
                continue
            native_pin = w.file_digest(root, BASE + '/' + role + '/new-handoff-native-readback.json')
            native = _pin(root, native_pin)
            old_pin = w.file_digest(root, OUTPUT + '/native/old-' + role + '.json')
            old_native = _pin(root, old_pin)
            handoff_pin = _write_once(root, OUTPUT + '/native/handoff-' + role + '.json',
                                      w.read_json(Path(root) / BASE / role / 'HANDOFF.json'))
            handoff = _pin(root, handoff_pin)
            old = _binding(document, role)
            old_id = _id(item['old_binding'])
            if not old:
                # One explicitly named associated website window had no runtime
                # binding. Register identity only, with no execution capability.
                if role != 'malay-original-owner' or handoff.get('old_binding') != item['old_binding']:
                    raise w.WorkflowError('existing exact role binding required')
                old = item['old_binding']
            if (_id(old) != old_id or old.get('project_id') != item['old_binding'].get('project_id')
                    or old.get('cwd') != item['old_binding'].get('cwd')
                    or handoff.get('role') != role or _id(handoff['old_binding']) != old_id):
                raise w.WorkflowError('same role, original project and cwd required')
            selected = [x for x in rows if x.get('id') == item.get('new_thread_id')]
            if (len(selected) != 1 or selected[0].get('projectId') != old.get('project_id')
                    or selected[0].get('cwd') != old.get('cwd')):
                raise w.WorkflowError('actual new window project/cwd identity required')
            new = selected[0]
            if any(native.get('thread', {}).get(k) != new.get(k) for k in ('id', 'title', 'cwd')):
                raise w.WorkflowError('new native readback identity differs')
            turns = native.get('turns', [])
            finals = [(t, m) for t in turns if t.get('status') == 'completed' and not t.get('error')
                      for m in t.get('items', []) if m.get('type') == 'agentMessage'
                      and m.get('phase') == 'final_answer' and isinstance(m.get('text'), str) and m['text'].strip()]
            if len(finals) != 1:
                raise w.WorkflowError('one actual completed nonempty new handoff reply required')
            old_thread = old_native.get('thread', {})
            status = old_thread.get('status', {})
            status = status.get('type') if isinstance(status, dict) else status
            if (old_thread.get('id') != old_id or old_thread.get('cwd') != old.get('cwd')
                    or old_thread.get('title') != old.get('title') or status not in ('idle', 'notLoaded')
                    or not old_native.get('turns')
                    or any(t.get('status') not in ('completed', 'failed', 'interrupted') for t in old_native['turns'])):
                raise w.WorkflowError('old native window still active or lacks terminal evidence')
            turn, message = finals[0]
            memberships = [s['sectionId'] for s in inventory.get('sections', [])
                           if 'codex:thread:local:' + new['id'] in s.get('itemKeys', [])]
            if len(memberships) > 1 or (not memberships and role in w.department_registry(root)):
                raise w.WorkflowError('one actual new sidebar membership required')
            new_binding = {'task_id': new['id'], 'title': new['title'], 'project_id': old['project_id'],
                'cwd': old['cwd'], 'host_id': new.get('hostId', 'local'),
                'sidebar_section_id': memberships[0] if memberships else None,
                'status': 'bound_and_visible', 'reply_health': 'healthy_visible_reply_verified',
                'dispatch_eligible': True, 'last_reply_ref': message['id'],
                'last_reply_sha256': hashlib.sha256(message['text'].encode()).hexdigest(),
                'last_verified_at': dt.datetime.now(dt.timezone.utc).isoformat(),
                'last_health_check_at': dt.datetime.now(dt.timezone.utc).isoformat(),
                'last_run_status': 'success', 'consecutive_empty_reply_turns': 0, 'consecutive_failures': 0}
            row = {'schema': SCHEMA, 'role': role, 'old_binding': old,
                'new_binding': new_binding, 'manifest': manifest_pin, 'handoff': handoff_pin,
                'old_native': old_pin, 'new_native': native_pin, 'inventory': inventory_pin,
                'history': history, 'production_permission_inherited': False,
                'old_permits_reusable_by_new_window': False, 'completed_handoff_turn': turn['id'],
                'expected_binding_hash': w.sha256_value(_binding(document, role))}
            existing = Path(root) / OUTPUT / 'records' / (role + '-v2.json')
            if existing.exists():
                row = w.read_json(existing)
            pin = _write_once(root, OUTPUT + '/records/' + role + '-v2.json', row)
            validate_record(root, row, pin)
            records.append(pin)
        except (w.WorkflowError, OSError, KeyError, TypeError, ValueError) as error:
            blocked.append({'role': role, 'reason': str(error), 'next_action':
                'refresh exact old/new native identity evidence and rerun prepare; no messages or permission inherited'})
    plan = {'schema': SCHEMA, 'records': records, 'blocked': blocked,
            'cutover_observations': { _pin(root, pin)['role']: _pin(root, pin)['old_native'] for pin in records },
            'historical_sources_rewritten': False, 'production_permission_inherited': False}
    w.atomic_write_json(Path(root) / OUTPUT / 'plan.json', plan)
    return plan


def apply(root, plan_path, *, dry_run=True):
    plan = w.read_json(w.safe_path(root, plan_path))
    if plan.get('schema') != SCHEMA:
        raise w.WorkflowError('known rotation plan required')
    observation_file = Path(root) / OUTPUT / 'native/cutover.json'
    observations = (w.read_json(observation_file) if observation_file.exists()
                    else plan.get('cutover_observations', {}))
    results = []
    for pin in plan['records']:
        row = _pin(root, pin)
        validate_record(root, row, pin)
        for key in ('manifest', 'handoff', 'inventory', 'old_native', 'new_native', 'history'):
            _pin(root, row[key])
        role = row['role']
        with w.workflow_lock(root):
            document = w.read_json(Path(root) / REGISTRY)
            before = _binding(document, role)
            installed = before.get('rotation_record') == pin
            if installed:
                list(_records(root))
                status = 'duplicate_ignored'
            else:
                fresh_observation = _pin(root, observations.get(role))
                observed_at = dt.datetime.fromisoformat(fresh_observation.get('observed_at', '').replace('Z', '+00:00'))
                age = (dt.datetime.now(dt.timezone.utc) - observed_at).total_seconds()
                old_thread = fresh_observation.get('thread', {})
                old_status = old_thread.get('status', {})
                old_status = old_status.get('type') if isinstance(old_status, dict) else old_status
                if (not 0 <= age <= 300 or old_status not in ('idle', 'notLoaded')
                        or any(old_thread.get(k) != _identity(row['old_binding']).get(v) for k, v in
                               (('id', 'task_id'), ('title', 'title'), ('cwd', 'cwd')))
                        or not fresh_observation.get('turns')
                        or any(t.get('status') not in ('completed', 'failed', 'interrupted')
                               for t in fresh_observation['turns'])):
                    raise w.WorkflowError('fresh terminal old native observation within 300 seconds required: ' + role)
                if w.sha256_value(before) != row['expected_binding_hash']:
                    raise w.WorkflowError('exact role binding CAS conflict: ' + role)
                if before and before != row['old_binding']:
                    raise w.WorkflowError('rotation cannot substitute old identity or health')
                if dry_run:
                    results.append({'role': role, 'status': 'ready', 'record': pin}); continue
                backup = OUTPUT + '/backups/registry-before-' + role + '.json'
                _write_once(root, backup, document)
                fresh = {**row['new_binding'], 'rotation_record': pin}
                departments = [x for x in document.get('departments', []) if x.get('id') == role]
                if departments:
                    departments[0]['chat_binding'] = fresh
                    departments[0]['production_write_allowed'] = False
                else:
                    if 'thread_id' in before or role == 'malay-original-owner':
                        fresh['thread_id'] = fresh['task_id']
                    document.setdefault('collaboration_bindings', {})[role] = {
                        **before, **fresh, 'production_write_allowed': False,
                        'company_role_health_inherited': False, 'runtime_goal_authorization_required': True}
                document.setdefault('window_rotation_records', []).append(pin)
                w.atomic_write_json(Path(root) / REGISTRY, document)
                status = 'applied'
            result = {'role': role, 'status': status, 'record': pin,
                      'active_binding': _identity(_binding(document, role)),
                      'production_permission_inherited': False}
            if not dry_run:
                w.atomic_write_json(Path(root) / OUTPUT / 'records' / (role + '-applied.json'), result)
            results.append(result)
    return {'results': results, 'blocked': plan.get('blocked', []), 'dry_run': dry_run}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('command', choices=('prepare', 'preview', 'apply'))
    parser.add_argument('--manifest', default=BASE + '/rotation-manifest.json')
    parser.add_argument('--inventory', default=OUTPUT + '/native/thread-inventory.json')
    parser.add_argument('--plan', default=OUTPUT + '/plan.json')
    args = parser.parse_args()
    value = (prepare(args.root, args.manifest, args.inventory) if args.command == 'prepare'
             else apply(args.root, args.plan, dry_run=args.command != 'apply'))
    print(json.dumps(value, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
