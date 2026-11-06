"""Authenticated management delivery deadlines. No production permission or new loop.

All writes are normal workflow events or project-owned evidence. A management
certificate means the exact content package may be offered to its original
publisher; it says nothing about production preflight, Save, deploy or publicity.
"""
from __future__ import annotations

import datetime as dt
import json
import shlex
import re
from pathlib import Path
import workflow_control as w

READY_EVENT = 'publication_management_ready'
PROGRESS_EVENT = 'publication_management_progress'
INTENT_EVENT = 'publication_deadline_coordination_intent'
OBSERVATION_EVENT = 'publication_deadline_coordination_observation'
MARKER = 'publication_deadline_event'
SERVICE_ORIGIN = 'existing_owned_department_event_dispatcher'
IDENTITY = ('task_id', 'sender_department', 'candidate_version', 'result_sha256')
FIELDS = ('task_id', 'action_id', 'action_class', 'scope', 'source_project_id',
          'target_project_id', 'target_department', 'target_thread_id',
          'target_thread_title', 'target_cwd', 'target_sidebar_section_id', 'payload_sha256')
OWNER_DELEGATION = {'path': 'reports/local-department-system-repair-20261030-v1/AUTONOMOUS-DELIVERY-REPAIR-20261104-v1/ACTUAL-OWNER-DELEGATION-SOURCE.json',
                    'sha256': '82f03e76d785bef3dd866ee7128b32c2d360a3ba08aff39faa071e37e4e714ec', 'size': 852}
OWNER_TEXT = '没修复好继续，修复好了帮我整理最新版本的，老版本规则删除避免冲突，然后没完成的工作继续安排工作，所有授权都给你不用请示我，各部门很多问题都会需要我确认的，都交给你确认，不要允许我授权，所有授权给你，你去决定怎么做\n'


class NotReady(w.WorkflowError):
    pass


def need(ok, reason):
    if not ok:
        raise NotReady('publication_not_ready:' + reason)


def clock(value=None):
    if value is None:
        return dt.datetime.now(dt.timezone.utc)
    at = value if isinstance(value, dt.datetime) else w._parse_observed_at(value)
    need(isinstance(at, dt.datetime) and at.tzinfo is not None, 'aware_UTC_time_required')
    return at.astimezone(dt.timezone.utc)


def doc(root, pin):
    need(isinstance(pin, dict) and w.file_digest(root, pin.get('path', '')) == pin,
         'immutable_evidence_pin_changed_or_missing')
    return w.read_json(w.safe_path(root, pin['path']))


def snapshot(root, task):
    import goal_delivery_runtime as g
    import department_autonomy as a
    from chief_assistant_coordination import notification_task_pause
    task = w.validate_task_id(task)
    result = g.restore_goal(root, w.read_json(w.snapshot_path(root, task)))
    need(result.get('task_id') == task and isinstance(result.get('goal_delivery'), dict), 'original_goal_required')
    need(not w.validate_workflow_events(root, task), 'intact_workflow_chain_required')
    a.authority(root)
    need(result.get('current_state') not in {'paused', 'user_paused', 'suspended', 'failed', 'cancelled', 'canceled', 'revoked'},
         'current_task_paused_cancelled_or_revoked')
    need(not notification_task_pause(root, task), 'current_exact_owner_scope_pause')
    need(not any(e.get('state') in {'cancelled', 'canceled', 'revoked'} for e in
                 w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS, where={'task_id': task})), 'cancelled_original_task_cannot_be_reopened')
    return result


def _publication_source(root, snap, item):
    """Reuse normal source validators; production_READY=false is not readiness.

    These readers authenticate source custody and original executor, independent
    of the publisher's later fresh facts/backup/CAS/permit/preflight.
    """
    if item.get('publication_kind') == 'cms':
        from professional_cms_execution import records
        rows = [r for r in records(root, snap) if r.get('registration') == item.get('publication_source')
                and r.get('action', {}).get('action_id') == item.get('publication_action_id')]
        need(len(rows) == 1, 'one_existing_normal_CMS_publication_source_required')
        ctx = rows[0]; action = ctx['action']; desired = ctx.get('desired')
        need(not ctx.get('revoked') and not ctx.get('withdrawn')
             and ctx.get('status') not in {'revoked', 'withdrawn', 'cancelled', 'canceled', 'suspended'}, 'current_CMS_source_withdrawn')
        fields = action.get('changed_fields')
        need(isinstance(desired, dict) and desired and isinstance(fields, list)
             and fields == sorted(set(fields)) == sorted(desired), 'complete_exact_CMS_fields_required')
        obj = {'kind': 'cms', 'table': action.get('table'), 'record_id': action.get('record_id'),
               'slug': action.get('slug'), 'physical_scope': action.get('scope')}
        need(all(isinstance(v, str) and v for v in obj.values()), 'unique_CMS_object_required')
        role = ctx.get('executor'); fixed = w.department_registry(root).get(role, {}).get('chat_binding')
        return {'owner': ctx.get('owner'), 'scope': ctx.get('business_scope'), 'publisher': role,
                'publisher_binding': fixed, 'object': obj, 'fields': fields,
                'content_sha256': w.sha256_value(desired), 'source_event_id': ctx['event_id']}
    if item.get('publication_kind') == 'web':
        from professional_web_execution import records
        from original_production_delivery import code_records
        rows = records(root, snap['task_id']) + code_records(root, snap['task_id'])
        rows = [r for r in rows if r.get('registration') == item.get('publication_source')]
        need(len(rows) == 1, 'one_existing_normal_WEB_publication_source_required')
        ctx = rows[0]; paths = ctx.get('paths')
        need(not ctx.get('revoked') and not ctx.get('withdrawn')
             and ctx.get('status') not in {'revoked', 'withdrawn', 'cancelled', 'canceled', 'suspended'}, 'current_WEB_source_withdrawn')
        need(isinstance(paths, dict) and paths and all(isinstance(p, str) and not Path(p).is_absolute()
             and '..' not in Path(p).parts and w.SHA256_PATTERN.fullmatch(str(sha)) for p, sha in paths.items()),
             'complete_exact_WEB_path_SHA_map_required')
        obj = {'kind': 'web', 'repository': ctx.get('repository'), 'commit': ctx.get('commit'), 'tree': ctx.get('tree')}
        need(all(isinstance(v, str) and v for v in obj.values()), 'exact_WEB_repository_commit_tree_required')
        return {'owner': ctx.get('owner'), 'scope': ctx.get('scope'), 'publisher': ctx.get('role'),
                'publisher_binding': ctx.get('binding'), 'object': obj, 'fields': sorted(paths),
                'content_sha256': w.sha256_value(paths), 'source_event_id': ctx['event_id'],
                'execution_stage_id': ctx.get('execution_stage_id'),
                'execution_source_aliases': [p for p in (ctx.get('registration'), ctx.get('decision')) if isinstance(p, dict)]}
    raise NotReady('publication_not_ready:known_existing_publication_kind_required')


def _native(root, pin, fixed, role):
    from goal_delivery_runtime import _native_document
    page = _native_document(root, pin)
    need(isinstance(fixed, dict) and all(page.get('thread', {}).get(k) == fixed.get(v)
         for k, v in {'id': 'task_id', 'title': 'title', 'cwd': 'cwd'}.items()),
         'actual_fixed_native_identity_required:' + str(role))
    need(page.get('thread', {}).get('projectId', fixed.get('project_id')) == fixed.get('project_id')
         and fixed.get('project_id'), 'actual_native_project_required')
    return page


def _binding(ctx):
    fixed = dict(ctx.get('publisher_binding') or {})
    fixed['task_id'] = fixed.get('task_id', fixed.get('thread_id'))
    need(all(fixed.get(k) for k in ('task_id', 'title', 'cwd', 'project_id')), 'original_publisher_binding_required')
    return fixed


def _contains_pin(value, pin):
    return value == pin or isinstance(value, dict) and any(_contains_pin(v, pin) for v in value.values()) \
        or isinstance(value, list) and any(_contains_pin(v, pin) for v in value)


def _start_time(root, cert, item, turn, action, observed_at, ctx):
    """Recognize only an exact normal preflight registration and its actual CLI.
    A provider startedAt is a clock, never evidence that an echo was preflight.
    """
    holders = {cert['task_id'], ctx.get('execution_stage_id')}
    events = [e for e in _events(root) if e.get('event_id') == item.get('normal_start_event_id') and e.get('task_id') in holders]
    need(len(events) == 1, 'existing_normal_publisher_preflight_event_required')
    entry = events[0].get('details', {}).get('professional_cms_preflight' if cert['publication_kind'] == 'cms' else 'professional_WEB_preflight')
    need(isinstance(entry, dict), 'normal_start_event_type_required')
    request = doc(root, entry.get('request'))
    need(request.get('task_id') == cert['task_id'] and request.get('department') == cert['publisher_department']
         and any(_contains_pin([entry, request], p) for p in [cert['publication_source'], *ctx.get('execution_source_aliases', [])]),
         'normal_start_same_source_task_original_publisher_required')
    if cert['publication_kind'] == 'cms':
        need(entry.get('action_id') == cert['publication_action_id'] == request.get('action_id')
             and request.get('scope') in {cert['scope'], cert['object']['physical_scope']}
             and request.get('table') == cert['object']['table'] and request.get('object_ids') == [cert['object']['record_id']]
             and request.get('slug') == cert['object']['slug'] and request.get('changed_fields') == cert['fields']
             and request.get('professional_execution_source') == cert['publication_source']
             and w.sha256_value(request.get('desired')) == cert['content_sha256'], 'normal_CMS_start_exact_action_object_SHA_required')
    else:
        state = request.get('state', {})
        need(state.get('candidate_commit') == cert['object']['commit'] and state.get('candidate_tree') == cert['object']['tree']
             and request.get('repository', cert['object']['repository']) == cert['object']['repository'], 'normal_WEB_start_exact_repository_commit_tree_required')
    need(action.get('type') == 'commandExecution' and action.get('status') == 'completed' and action.get('exitCode') == 0,
         'actual_successful_normal_preflight_command_required')
    args = shlex.split(action.get('command', ''))
    if len(args) == 3 and Path(args[0]).name in {'zsh', 'bash', 'sh'} and args[1] in {'-lc', '-c'}:
        args = shlex.split(args[2])
    need(args and re.fullmatch(r'python(?:3(?:\.\d+)?)?', Path(args[0]).name), 'actual_python_normal_entry_required')
    args = args[1:]
    if args and args[0] == '-B':
        args = args[1:]
    need(len(args) == 8 and args[1:5] == ['--project-root', str(Path(root).resolve()), 'preflight-record', '--task-id']
         and args[5] == cert['task_id'] and args[6] == '--input', 'exact_normal_preflight_argv_required')
    # args length is script + 2 root args + command + 2 task args + 2 input args.
    # No shell operators, extra flags, arbitrary code or scripts are admitted.
    cwd = Path(action.get('cwd', ''))
    script = Path(args[0]); script = script if script.is_absolute() else cwd/script
    need(script.resolve() == (Path(root)/'tools/goal_delivery_runtime.py').resolve(), 'exact_existing_preflight_script_required')
    input_path = Path(args[7]); input_path = input_path if input_path.is_absolute() else cwd/input_path
    need(input_path.resolve().is_relative_to(Path(root).resolve()), 'project_owned_normal_preflight_envelope_required')
    envelope = doc(root, w.file_digest(root, str(input_path.resolve().relative_to(Path(root).resolve()))))
    schema = 'professional-cms-fresh-preflight/v1' if cert['publication_kind'] == 'cms' else 'professional-external-WEB-fresh-preflight/v1'
    need(envelope.get('schema') == schema and envelope.get('task_id', cert['task_id']) == cert['task_id']
         and envelope.get('request') == entry['request'], 'native_CLI_input_must_equal_registered_preflight_request')
    output = json.loads(w._completion_execution_output(action))
    need(output.get('result') in {'recorded', 'duplicate_ignored'} and output.get('external_permission_issued', output.get('permission_issued')) is False
         and (output.get('request') == entry['request'] if cert['publication_kind'] == 'cms' else output.get('event_id') == events[0]['event_id']),
         'actual_normal_preflight_command_result_required')
    value = action.get('startedAt')
    if type(value) in {int, float}:
        result = dt.datetime.fromtimestamp(value, dt.timezone.utc)
        need(type(turn.get('startedAt')) in {int, float} and turn['startedAt'] <= value <= observed_at.timestamp(), 'real_command_start_order_required')
    else:
        ordered = _events(root)
        need(next(i for i, e in enumerate(ordered) if e['event_id'] == cert['certificate_id'])
             < next(i for i, e in enumerate(ordered) if e['event_id'] == events[0]['event_id']), 'normal_start_event_must_follow_ready_event')
        # Normal event time is second precision. Use its conservative upper
        # bound, capped by the real management observation, never backdate.
        result = min(clock(events[0]['created_at']) + dt.timedelta(seconds=1), observed_at)
    need(clock(cert['ready_at']) <= result <= observed_at, 'real_normal_start_must_follow_ready_and_precede_observation')
    return result


def _selection(page, turn_id, item_id):
    rows = [(t, m) for t in page.get('turns', []) if t.get('id') == turn_id
            for m in t.get('items', []) if m.get('id') == item_id]
    need(len(rows) == 1 and not rows[0][0].get('error')
         and rows[0][0].get('status') in {'completed', 'inProgress'}, 'one_real_native_item_required')
    return rows[0]


def _native_time(turn, now):
    value = turn.get('completedAt') if turn.get('status') == 'completed' else turn.get('startedAt')
    need(type(value) in {int, float} and type(turn.get('startedAt')) in {int, float}
         and turn['startedAt'] <= value <= now.timestamp(), 'real_ordered_native_time_required')
    return dt.datetime.fromtimestamp(value, dt.timezone.utc)


def _provider_time(item, names=('createdAt', 'timestamp')):
    values = []
    for key in names:
        if key not in item:
            continue
        value = item[key]
        if type(value) in {int, float}:
            value = dt.datetime.fromtimestamp(value, dt.timezone.utc)
        else:
            value = clock(value)
        values.append(value)
    need(not values or all(v == values[0] for v in values), 'ambiguous_provider_item_time')
    return values[0] if values else None


def _message_time(turn, message, observed_at):
    """No turn start/end is an ACK timestamp. Missing message clocks are
    explicitly measured at the first successful management registration.
    """
    observed = clock(observed_at)
    need(observed <= clock(), 'management_observation_cannot_be_future')
    provider = _provider_time(message)
    if provider is None:
        return observed, 'first_successful_management_observation'
    need(type(turn.get('startedAt')) in {int, float}
         and turn['startedAt'] <= provider.timestamp() <= observed.timestamp(), 'ordered_provider_message_time_required')
    if type(turn.get('completedAt')) in {int, float}:
        need(provider.timestamp() <= turn['completedAt'], 'provider_message_after_turn_completion')
    return provider, 'provider_message_time'


def validate_ready(root, item, *, at=None):
    """Authenticate complete management package; callers cannot select the clock."""
    import department_autonomy as a
    import result_coordination as rc
    now = clock(at)
    need(isinstance(item, dict) and item.get('schema') == 'publication-management-ready-input/v1', 'ready_input_schema_required')
    need(not any(k in item for k in ('ready_at', 'registered_at', 'deadline', 'production_READY', 'permit', 'native_time')),
         'caller_readiness_clock_or_production_flag_forbidden')
    ident = rc.exact_identity(item.get('identity', {})); snap = snapshot(root, ident['task_id']); goal = snap['goal_delivery']
    frozen = doc(root, snap.get('goal_contract')); a.authority(root)
    need(all(goal.get(k) == frozen.get(k) for k in ('primary_owner', 'producer_departments', 'authorized_scope')),
         'unchanged_frozen_owner_producers_scope_required')
    owner = goal.get('primary_owner'); producer = ident['sender_department']; scope = item.get('scope')
    need(item.get('owner_department_id') == owner and a.professional(root, owner)
         and producer in goal.get('producer_departments', []) and a.professional(root, producer), 'original_owner_and_legal_producer_required')
    need(scope in frozen.get('authorized_scope', []), 'same_original_scope_required')
    ctx = _publication_source(root, snap, item)
    need(ctx['owner'] == owner and ctx['scope'] == scope and item.get('publisher_department') == ctx['publisher'],
         'publication_source_owner_scope_executor_mismatch')
    need(item.get('object') == ctx['object'] and item.get('fields') == ctx['fields']
         and item.get('content_sha256') == ctx['content_sha256'], 'exact_object_fields_content_SHA_required')
    outbox = item.get('outbox'); box = doc(root, outbox)
    need(box.get('status') in {'completed', 'partial'}
         and outbox['sha256'] == ident['result_sha256'] and box.get('task_id') == ident['task_id']
         and box.get('department') == producer and box.get('candidate_version') == ident['candidate_version']
         and box.get('scope') == scope and box.get('primary_owner') == owner, 'complete_V2_identity_owner_scope_required')
    w.validate_outbox(root, [outbox], producer, ident['task_id'])
    evidence = box.get('evidence')
    need(isinstance(evidence, list) and evidence and all(isinstance(p, dict)
         and w.file_digest(root, p.get('path', '')) == p for p in evidence), 'all_frozen_V2_evidence_required')
    manifest_pin = item.get('manifest'); manifest = doc(root, manifest_pin)
    expected = {'schema': 'publication-management-content-manifest/v1', 'task_id': ident['task_id'],
                'scope': scope, 'primary_owner': owner, 'producer_department': producer,
                'publisher_department': ctx['publisher'], 'publication_source': item['publication_source'],
                'publication_action_id': item.get('publication_action_id'), 'object': ctx['object'],
                'fields': ctx['fields'], 'content_sha256': ctx['content_sha256']}
    need(manifest == expected and manifest_pin in evidence and item.get('self_check') in evidence,
         'complete_frozen_publication_manifest_and_selfcheck_required')
    check = doc(root, item.get('self_check'))
    need(check.get('task_id') == ident['task_id'] and check.get('scope') == scope
         and check.get('department') == producer and check.get('status') == 'PASS'
         and check.get('manifest') == manifest_pin and check.get('content_sha256') == ctx['content_sha256'],
         'own_exact_content_selfcheck_required')
    source = item.get('delivery_source')
    need(isinstance(source, dict) and all(source.get(k) == v for k, v in ident.items())
         and source.get('scope') == scope and source.get('outbox') == outbox, 'full_original_delivery_source_required')
    fixed = w.department_registry(root)[producer]['chat_binding']
    w._validate_goal_completed_result(root, source, fixed['task_id'])
    page = _native(root, source.get('actual_native_completion'), fixed, producer)
    turn, message = _selection(page, source.get('source_turn_id'), source.get('source_message_id'))
    source_at = _native_time(turn, now)
    commands = [m for m in turn.get('items', []) if m.get('id') == item.get('self_check_command_id')]
    need(len(commands) == 1 and turn['items'].index(commands[0]) < turn['items'].index(message),
         'actual_selfcheck_must_precede_delivery_message')
    command = commands[0]
    need(command.get('type') == 'commandExecution' and command.get('status') == 'completed'
         and command.get('exitCode') == 0 and Path(command.get('cwd', '')).resolve() == Path(fixed['cwd']).resolve(),
         'real_successful_own_selfcheck_command_required')
    output = w._completion_execution_output(command)
    need(item['self_check']['sha256'].encode() in output and manifest_pin['sha256'].encode() in output,
         'native_selfcheck_output_must_bind_exact_manifest_and_check_SHA')
    need(snap.get('current_state') not in {'failed', 'cancelled', 'canceled'}, 'cancelled_task_cannot_become_ready')
    return {'identity': ident, 'task_id': ident['task_id'], 'scope': scope, 'owner_department_id': owner,
            'publisher_department': ctx['publisher'], 'publication_kind': item['publication_kind'],
            'publication_source': item['publication_source'], 'publication_action_id': item.get('publication_action_id'),
            'object': ctx['object'], 'object_identity': w.sha256_value(ctx['object']), 'fields': ctx['fields'],
            'content_sha256': ctx['content_sha256'], 'native_source_at': source_at.isoformat(),
            'source_fingerprint': w.sha256_value(item), 'goal_contract': snap['goal_contract'],
            'management_ready': True, 'production_READY': False, 'external_permission_issued': False}


def _events(root, task=None):
    need(not w.workflow_global_chain_errors(root), 'intact_global_event_chain_required')
    rows = w.read_jsonl(Path(root) / w.WORKFLOW_EVENTS)
    return [e for e in rows if task is None or e.get('task_id') == task]


def record_ready(root, task_id, input_path):
    root = Path(root); pin = w.file_digest(root, input_path); item = doc(root, pin)
    try:
        with w.workflow_lock(root):
            proof = validate_ready(root, item)
            need(task_id == proof['task_id'], 'CLI_same_task_required')
            rows = [e for e in _events(root, task_id) if e.get('details', {}).get(READY_EVENT, {}).get('proof', {}).get('identity') == proof['identity']
                    and e['details'][READY_EVENT]['proof']['object_identity'] == proof['object_identity']]
            if rows:
                need(len(rows) == 1 and rows[0]['details'][READY_EVENT].get('input') == pin
                     and rows[0]['details'][READY_EVENT].get('proof') == proof, 'original_ready_is_immutable')
                event = rows[0]; result = 'duplicate_ignored'
            else:
                snap = snapshot(root, task_id)
                event = w.append_workflow_event(root, task_id, snap['current_state'],
                        {READY_EVENT: {'input': pin, 'proof': proof, 'validated_at': clock().isoformat()}})
                result = 'recorded'
        return {'result': result, 'certificate': _certificate(event), 'production_READY': False, 'external_permission_issued': False}
    except (w.WorkflowError, ValueError, OSError, KeyError, TypeError) as exc:
        return {'result': 'not_ready', 'reason': str(exc), 'production_READY': False, 'external_permission_issued': False}


def _certificate(event):
    proof = event['details'][READY_EVENT]['proof']
    ready_at = clock(event['details'][READY_EVENT]['validated_at'])
    # Existing workflow created_at has second precision and its ledger scan
    # can complete after validation. Keep both real values; the code-generated
    # high precision validation clock must precede the append's upper bound.
    registered = clock(event['created_at'])
    need(ready_at < registered + dt.timedelta(seconds=1)
         and clock(proof['native_source_at']) <= ready_at, 'registration_cannot_predate_native_source')
    return {**proof, 'certificate_id': event['event_id'], 'certificate_event_hash': event['event_hash'],
            'ready_at': ready_at.isoformat(), 'clock_basis': 'normal_validated_management_registration',
            'ack_deadline': (ready_at + dt.timedelta(minutes=15)).isoformat(),
            'start_deadline': (ready_at + dt.timedelta(hours=2)).isoformat()}


def certificates(root, *, errors=None):
    result = []
    for event in _events(root):
        entry = event.get('details', {}).get(READY_EVENT)
        if not entry:
            continue
        try:
            proof = validate_ready(root, doc(root, entry['input']))
            need(proof == entry.get('proof'), 'registered_ready_source_changed')
            result.append(_certificate(event))
        except (w.WorkflowError, ValueError, OSError, KeyError, TypeError) as exc:
            if errors is None:
                raise
            errors.append({'event_key': 'publication-invalid-source:' + event['event_id'],
                           'task_id': event['task_id'], 'certificate_id': event['event_id'],
                           'state': 'not_ready', 'reason': str(exc), 'next_owner': 'system-development',
                           'actionable': False, 'external_permission_issued': False})
    return result


def _progress(root, cert, item, *, observed_at=None, frozen_timing=None):
    need(item.get('schema') == 'publication-management-progress/v1'
         and all(item.get(k) == cert[k] for k in ('task_id', 'scope', 'certificate_id', 'object_identity', 'content_sha256')),
         'progress_same_certificate_task_scope_object_SHA_required')
    need(not any(k in item for k in ('observed_at', 'ready_at', 'occurred_at', 'native_time', 'deadline',
             'management_observed_at', 'message_at', 'time_basis', 'validated_at')), 'caller_progress_clock_forbidden')
    event = next(e for e in _events(root, cert['task_id']) if e['event_id'] == cert['certificate_id'])
    ready = doc(root, event['details'][READY_EVENT]['input']); snap = snapshot(root, cert['task_id'])
    ctx = _publication_source(root, snap, ready); fixed = _binding(ctx)
    need(item.get('actor_department') == ctx['publisher'], 'only_original_publisher_can_ack_or_start')
    page = _native(root, item.get('actual_native'), fixed, ctx['publisher'])
    turn, message = _selection(page, item.get('source_turn_id'), item.get('source_message_id'))
    observed_at = clock(observed_at)
    at, time_basis = _message_time(turn, message, observed_at)
    if frozen_timing is not None:
        need(frozen_timing.get('message_sha256') == w.sha256_value(message.get('text')),
             'same_original_message_bytes_required_for_frozen_observation')
        at = clock(frozen_timing['message_at']); time_basis = frozen_timing['time_basis']
        observed_at = clock(frozen_timing['management_observed_at'])
    message_at = at
    need(clock(cert['ready_at']) <= at, 'progress_must_follow_management_ready')
    state = item.get('state')
    allowed = {'acknowledged', 'started', 'external_wait', 'dependency_resolved', 'unknown', 'inflight', 'executed_pending_public', 'completed'}
    need(state in allowed and message.get('type') == 'agentMessage' and message.get('text', '').strip(), 'actual_publisher_state_message_required')
    packet = {k: item[k] for k in ('task_id', 'scope', 'certificate_id', 'object_identity', 'content_sha256', 'state')}
    if state == 'external_wait':
        need(all(isinstance(item.get(k), str) and item[k].strip() for k in ('dependency_holder', 'unblock_input', 'next_check_at')),
             'named_external_holder_unblock_input_next_check_required')
        need(clock(item['next_check_at']) > clock(cert['ready_at']), 'real_post_ready_dependency_check_required')
        packet.update({k: item[k] for k in ('dependency_holder', 'unblock_input', 'next_check_at')})
    lines = [s[len('FLASHCAST_PUBLICATION_STATE '):] for s in message['text'].splitlines() if s.startswith('FLASHCAST_PUBLICATION_STATE ')]
    need(len(lines) == 1 and json.loads(lines[0]) == packet, 'exact_native_publisher_state_packet_required')
    index = turn['items'].index(message)
    if state in {'acknowledged', 'started'}:
        follow = [m for m in turn['items'][index+1:] if m.get('id') == item.get('followup_item_id')]
        need(len(follow) == 1 and follow[0].get('type') in {'commandExecution', 'mcpToolCall', 'functionCall'}
             and follow[0].get('status') in {'completed', 'inProgress'}, 'ACK_requires_actual_followup_action_not_accepted')
        action = follow[0]
        text = json.dumps(action, ensure_ascii=False)
        if state == 'started':
            need(item.get('start_kind') == 'preflight', 'normal_preflight_start_source_required')
            need(action.get('status') != 'completed' or action.get('exitCode', 0) == 0, 'failed_command_is_not_start_evidence')
            at = _start_time(root, cert, item, turn, action, observed_at, ctx)
            need(clock(cert['ready_at']) <= at, 'real_start_must_follow_management_ready')
        else:
            need(all(token in text for token in (cert['task_id'], cert['object_identity'], cert['content_sha256'])),
                 'followup_must_bind_actual_object_and_content_SHA')
    if state == 'completed':
        import goal_delivery_runtime as g
        proof = g.completion_obligations(root, snap)
        rows = [r for r in proof.get('requirements', []) if r.get('requirement_id') == item.get('completion_requirement_id')
                and r.get('scope') == cert['scope'] and r.get('state') == 'PROVEN']
        need(len(rows) == 1, 'normal_actual_completion_proof_required')
        bound = doc(root, item.get('completion_object_proof'))
        need(all(bound.get(k) == cert[k] for k in ('task_id', 'scope', 'object_identity', 'content_sha256', 'publication_source'))
             and item['completion_object_proof'] in rows[0].get('evidence', []), 'normal_completion_must_prove_exact_object_and_source')
    if state == 'executed_pending_public':
        receipts, invalid = w._validate_receipt_chain(root, cert['task_id'])
        matches = [r for r in receipts if r.get('receipt_id') == item.get('execution_receipt_id')
                   and r.get('receipt_hash') == item.get('execution_receipt_hash')
                   and r.get('receipt_type') == 'execution_result' and r.get('department') == ctx['publisher']]
        need(not invalid and len(matches) == 1, 'normal_original_execution_receipt_required')
        receipt = matches[0]; proof_pin = item.get('execution_object_proof'); bound = doc(root, proof_pin)
        policies = [r for r in w.read_jsonl(Path(root)/w.POLICY_DECISIONS)
                    if r.get('decision_id') == receipt.get('policy_decision_id')]
        need(len(policies) == 1 and policies[0].get('status') == 'allow'
             and all(policies[0].get(k) == receipt.get(k) for k in ('task_id', 'department', 'action_id', 'action_class', 'scope')),
             'real_normal_exact_execution_policy_required')
        need(proof_pin in receipt.get('evidence', [])
             and all(bound.get(k) == cert[k] for k in ('task_id', 'scope', 'object_identity', 'content_sha256', 'publication_source'))
             and receipt.get('action_id') == bound.get('action_id')
             and receipt.get('policy_decision_id') == bound.get('policy_decision_id')
             and receipt.get('scope') in {cert['scope'], cert['object'].get('physical_scope')}
             and (bool(bound.get('saved_id')) and bool(bound.get('revision')) or bool(bound.get('deployment_version'))),
             'exact_saved_revision_or_deployment_normal_proof_required')
        request_pin = bound.get('execution_request'); execution_request = doc(root, request_pin)
        need(request_pin['sha256'] == policies[0].get('payload_sha256')
             and all(execution_request.get(k) == receipt.get(k) for k in ('task_id', 'department', 'action_id', 'action_class', 'scope')),
             'normal_execution_request_policy_receipt_binding_required')
        if cert['publication_kind'] == 'cms':
            need(receipt.get('action_id') == cert['publication_action_id'] and receipt.get('action_class') == 'cms_write'
                 and execution_request.get('professional_execution_source') == cert['publication_source']
                 and execution_request.get('table') == bound.get('table') == cert['object']['table']
                 and execution_request.get('object_ids') == [cert['object']['record_id']]
                 and bound.get('record_id') == bound.get('saved_id') == cert['object']['record_id']
                 and w.sha256_value(execution_request.get('desired')) == cert['content_sha256'],
                 'execution_must_be_exact_certificate_CMS_action_table_record_saved_id')
        else:
            need(receipt.get('action_class') == 'site_publish'
                 and bound.get('repository') == cert['object']['repository']
                 and bound.get('commit') == execution_request.get('state', {}).get('candidate_commit') == cert['object']['commit']
                 and bound.get('tree') == execution_request.get('state', {}).get('candidate_tree') == cert['object']['tree']
                 and any(_contains_pin(execution_request, p) for p in [cert['publication_source'], *ctx.get('execution_source_aliases', [])]),
                 'exact_WEB_repo_commit_tree_deploy_source_required')
        # Reuse the existing typed normal execution/native-effect contract. A
        # local Saved/deploy claim or an echo of its digest is insufficient.
        import qa_review_plan as q
        normal_pin = bound.get('normal_execution_proof'); normal = doc(root, normal_pin)
        need(normal_pin in receipt.get('evidence', [])
             and normal.get('schema_version') == 'goal-execution-completion-proof-v1'
             and normal.get('proof_type') == 'execution'
             and all(normal.get(k) == receipt.get(k) for k in ('task_id', 'department', 'action_id', 'action_class', 'scope'))
             and normal.get('identity') == cert['object'] and normal.get('source_fingerprint') == cert['content_sha256']
             and normal.get('production_version'), 'normal_typed_exact_execution_proof_required')
        native_effect = doc(root, normal.get('actual_native_effect')); q._review_native_containers(native_effect)
        actual = q._review_raw_native_result(native_effect.get('actual_tool_result'))
        expected_actual = {k: receipt[k] for k in ('task_id', 'department', 'action_id', 'action_class', 'scope')}
        expected_actual.update(identity=cert['object'], source_fingerprint=cert['content_sha256'],
                               production_version=normal['production_version'], proof_type='execution', verdict='pass')
        if cert['publication_kind'] == 'cms':
            expected_actual.update(table=cert['object']['table'], record_id=cert['object']['record_id'],
                                   saved_id=cert['object']['record_id'], revision=bound['revision'])
        else:
            expected_actual.update(repository=cert['object']['repository'], commit=cert['object']['commit'],
                                   tree=cert['object']['tree'], deployment_version=bound['deployment_version'])
        need(all(actual.get(k) == v for k, v in expected_actual.items()), 'actual_normal_native_execution_effect_must_match_certificate')
        calls = [m for m in turn['items'] if m.get('id') == item.get('execution_command_id')]
        need(len(calls) == 1 and calls[0].get('type') == 'commandExecution'
             and calls[0].get('status') == 'completed' and calls[0].get('exitCode') == 0
             and proof_pin['sha256'].encode() in w._completion_execution_output(calls[0]),
             'actual_original_execution_output_must_bind_saved_proof')
        output = json.loads(w._completion_execution_output(calls[0]))
        needed = {'task_id': cert['task_id'], 'action_id': receipt['action_id'], 'content_sha256': cert['content_sha256'],
                  'proof_sha256': proof_pin['sha256']}
        if cert['publication_kind'] == 'cms':
            needed.update(table=cert['object']['table'], record_id=cert['object']['record_id'], saved_id=cert['object']['record_id'], revision=bound['revision'])
        else:
            needed.update(repository=cert['object']['repository'], commit=cert['object']['commit'], tree=cert['object']['tree'], deployment_version=bound['deployment_version'])
        need(all(output.get(k) == v for k, v in needed.items()), 'actual_native_saved_or_deployed_readback_exact_object_required')
    return {**packet, 'native_at': at.isoformat(), 'actor_department': ctx['publisher'], 'source': item['actual_native'],
            'source_message_id': message['id'], 'source_fingerprint': w.sha256_value(item),
            'message_sha256': w.sha256_value(message['text']), 'message_at': message_at.isoformat(),
            'time_basis': time_basis, 'management_observed_at': observed_at.isoformat(),
            'effective_time_basis': 'provider_action_or_normal_start_event' if state == 'started' else time_basis}


def record_progress(root, task_id, input_path):
    pin = w.file_digest(root, input_path); item = doc(root, pin)
    try:
        with w.workflow_lock(root):
            matches = [c for c in certificates(root) if c['certificate_id'] == item.get('certificate_id')]
            need(len(matches) == 1 and task_id == matches[0]['task_id'], 'one_original_management_certificate_required')
            old = [e for e in _events(root, task_id) if all(e.get('details', {}).get(PROGRESS_EVENT, {}).get('proof', {}).get(k) == item.get(k)
                   for k in ('certificate_id', 'actor_department', 'source_message_id', 'state'))]
            need(len(old) <= 1, 'one_original_progress_message_registration_required')
            original = old[0]['details'][PROGRESS_EVENT] if old else None
            observed_at = original['proof']['management_observed_at'] if original else clock().isoformat()
            proof = _progress(root, matches[0], item, observed_at=observed_at, frozen_timing=original['proof'] if original else None)
            if old:
                invariant = ('certificate_id', 'state', 'actor_department', 'source_message_id', 'message_sha256', 'message_at', 'time_basis', 'native_at', 'management_observed_at')
                need(all(proof[k] == original['proof'][k] for k in invariant), 'same_message_cannot_change_registered_timing_or_state')
                return {'result': 'duplicate_ignored', 'proof': original['proof'], 'external_permission_issued': False}
            snap = snapshot(root, task_id)
            w.append_workflow_event(root, task_id, snap['current_state'],
                    {PROGRESS_EVENT: {'input': pin, 'proof': proof, 'validated_at': clock().isoformat()}})
        return {'result': 'recorded', 'proof': proof, 'external_permission_issued': False}
    except (w.WorkflowError, ValueError, OSError, KeyError, TypeError) as exc:
        return {'result': 'not_ready', 'reason': str(exc), 'external_permission_issued': False}


def status(root, cert, *, now=None):
    at = clock(now); progress = []
    events = _events(root, cert['task_id'])
    for event in events:
        entry = event.get('details', {}).get(PROGRESS_EVENT)
        if not entry or entry.get('proof', {}).get('certificate_id') != cert['certificate_id']:
            continue
        proof = _progress(root, cert, doc(root, entry['input']), observed_at=entry['proof']['management_observed_at'], frozen_timing=entry['proof'])
        registered = clock(event['created_at']); validated = clock(entry.get('validated_at'))
        need(proof == entry.get('proof') and clock(proof['native_at']) <= validated
             and validated < registered + dt.timedelta(seconds=1), 'immutable_ordered_progress_required')
        if clock(proof['native_at']) <= at:
            progress.append(proof)
    progress.sort(key=lambda p: clock(p['native_at']))
    states = {p['state'] for p in progress}; latest = progress[-1] if progress else {}
    terminal = 'completed' if 'completed' in states else 'executed_pending_public' if 'executed_pending_public' in states else None
    waiting = latest.get('state') == 'external_wait'
    uncertain = latest.get('state') in {'unknown', 'inflight'}
    pending = []
    if not terminal and not uncertain:
        if waiting:
            pending.append(('dependency_check', latest['next_check_at']))
        else:
            if not states.intersection({'acknowledged', 'started'}):
                pending.append(('acknowledgement', cert['ack_deadline']))
            if 'started' not in states:
                pending.append(('publication_start', cert['start_deadline']))
    follow = {'controller_decision': 'continue', 'controller_followthrough': 'external_wait_registered' if waiting else 'pending',
              'next_check_at': latest.get('next_check_at') if waiting else None}
    # Reuse the existing due semantics. An explicit read-only test clock is
    # evaluated equivalently without replacing the production wall clock.
    follow_due = (w._followthrough_due(follow) if now is None else
                  not waiting or clock(follow['next_check_at']) <= at)
    ack_times = [clock(p['native_at']) for p in progress if p['state'] in {'acknowledged', 'started'}]
    start_times = [clock(p['native_at']) for p in progress if p['state'] == 'started']
    ack_sample = next((p for p in progress if ack_times and clock(p['native_at']) == min(ack_times)
                       and p['state'] in {'acknowledged', 'started'}), {})
    start_sample = next((p for p in progress if start_times and clock(p['native_at']) == min(start_times)
                         and p['state'] == 'started'), {})
    return {'certificate': cert, 'state': terminal or ('external_wait' if waiting else 'original_effect_unknown_or_inflight' if uncertain else 'started' if 'started' in states else 'acknowledged' if 'acknowledged' in states else 'ready_awaiting_ack'),
            'pending_deadlines': [{'phase': phase, 'deadline': deadline, 'overdue': clock(deadline) <= at} for phase, deadline in pending],
            'controller_followthrough': follow['controller_followthrough'], 'next_check_at': follow['next_check_at'],
            'acknowledged_at': min(ack_times).isoformat() if ack_times else None,
            'started_at': min(start_times).isoformat() if start_times else None,
            'ack_time_basis': ack_sample.get('effective_time_basis'),
            'start_time_basis': start_sample.get('effective_time_basis'),
            'ack_target_met': min(ack_times) <= clock(cert['ack_deadline']) if ack_times else None,
            'start_target_met': min(start_times) <= clock(cert['start_deadline']) if start_times else None,
            'followthrough_due': follow_due, 'dependency': latest if waiting else None, 'progress': progress, 'business_goal_closed': False}


def _dependency_generation(dependency):
    if dependency is None:
        return None
    need(dependency.get('state') == 'external_wait'
         and all(dependency.get(k) for k in ('source_fingerprint', 'next_check_at', 'dependency_holder', 'unblock_input')),
         'authenticated_dependency_progress_generation_required')
    return w.sha256_value({k: dependency[k] for k in
                          ('source_fingerprint', 'next_check_at', 'dependency_holder', 'unblock_input')})


def _event_key(cert, phase, dependency=None):
    identity = [cert['task_id'], cert['identity'], cert['object_identity'], cert['content_sha256'], phase]
    if phase == 'dependency_check' and dependency is not None:
        identity.append(_dependency_generation(dependency))
    return 'publication-deadline:' + w.sha256_value(identity)


def _intents(root, cert):
    return [e['details'][INTENT_EVENT] for e in _events(root, cert['task_id'])
            if e.get('details', {}).get(INTENT_EVENT, {}).get('certificate_id') == cert['certificate_id']]


_UNFILTERED_DEPENDENCY = object()


def _covered_phases(cert, intent, *, dependency=_UNFILTERED_DEPENDENCY):
    phases = intent.get('covered_phases')
    if phases is None:
        phases = [phase for phase in ('acknowledgement', 'publication_start', 'dependency_check')
                  if _event_key(cert, phase) == intent.get('event_key')]
    need(isinstance(phases, list) and phases and set(phases) <= {'acknowledgement', 'publication_start', 'dependency_check'},
         'exact_intent_phase_coverage_required')
    covered = set(phases)
    if dependency is not _UNFILTERED_DEPENDENCY and 'dependency_check' in covered:
        # A real new publisher wait is a new obligation. A legacy phase-only
        # intent cannot permanently cover every later dependency generation.
        current = _dependency_generation(dependency)
        if not current or intent.get('dependency_generation') != current:
            covered.remove('dependency_check')
    return covered


def _resolved_intent(root, intent):
    observations = [e['details'][OBSERVATION_EVENT] for e in _events(root)
                    if e.get('details', {}).get(OBSERVATION_EVENT, {}).get('event_key') == intent['event_key']]
    for entry in reversed(observations):
        proof = doc(root, entry['projection'])
        need(proof.get('schema') == 'publication-coordination-effect-observation/v1'
             and proof.get('intent_request') == intent.get('request') and proof.get('event_key') == intent['event_key']
             and proof.get('observation_only') is True and entry.get('service_origin') == SERVICE_ORIGIN,
             'exact_original_coordination_observation_required')
        if proof.get('state') == 'original_owner_followthrough_observed':
            need(proof.get('ack') and proof.get('followup') and proof.get('original_input'), 'real_owner_followup_observation_required')
            return proof
    return None


def _known_original_input(root, intent):
    entries = [e['details'][OBSERVATION_EVENT] for e in _events(root)
               if e.get('details', {}).get(OBSERVATION_EVENT, {}).get('event_key') == intent['event_key']]
    for entry in reversed(entries):
        proof = doc(root, entry['projection'])
        need(proof.get('intent_request') == intent.get('request')
             and proof.get('event_key') == intent['event_key'] and proof.get('observation_only') is True
             and entry.get('service_origin') == SERVICE_ORIGIN, 'exact_original_delivery_observation_required')
        if proof.get('original_input'):
            return True
    return False


def due_work(root, now=None):
    """Phase-specific obligations share one object case, never one permanent skip."""
    errors = []; result = []
    for cert in certificates(root, errors=errors):
        try:
            view = status(root, cert, now=now); intents = _intents(root, cert)
            dependency = view['dependency']
            coverage = set().union(*[_covered_phases(cert, x, dependency=dependency) for x in intents]) if intents else set()
            unresolved = [x for x in intents if not _resolved_intent(root, x)]
            overdue = [p for p in view['pending_deadlines'] if p['overdue']]
            unhandled = [p for p in overdue if p['phase'] not in coverage]
            # Covered stages remain readable until their original effect is known.
            pending = (unhandled or overdue)[:1]
            if not pending and unresolved:
                pending = [{'phase': next(iter(_covered_phases(cert, unresolved[0]))), 'deadline': cert['ack_deadline']}]
            for item in pending:
                actionable = bool(unhandled) and not unresolved
                key = _event_key(cert, item['phase'], dependency)
                generation = _dependency_generation(dependency) if item['phase'] == 'dependency_check' else None
                result.append({'type': 'publication_deadline_overdue', 'event_key': key, 'identity': cert['identity'],
                    'task_id': cert['task_id'], 'scope': cert['scope'], 'scope_fingerprint': w.sha256_value(cert['scope']),
                    'certificate_id': cert['certificate_id'], 'object_identity': cert['object_identity'], 'object': cert['object'],
                    'content_sha256': cert['content_sha256'], 'owner_department_id': cert['owner_department_id'],
                    'next_owner': cert['owner_department_id'], 'publisher_department': cert['publisher_department'],
                    'logical_receiver': 'operations-assistant', 'handling_actor': 'operations',
                    'source': cert['publication_source'],
                    'source_fingerprint': w.sha256_value([cert['source_fingerprint'], generation]) if generation else cert['source_fingerprint'],
                    'deadline': item['deadline'], 'phase': item['phase'], 'covered_phases': sorted(p['phase'] for p in unhandled),
                    'dependency_generation': generation,
                    'deadline_obligations': view['pending_deadlines'], 'dependency': view['dependency'],
                    'actionable': actionable, 'original_intent': unresolved[0] if unresolved else None,
                    'original_event_key': unresolved[0]['event_key'] if unresolved else None,
                    'state': 'original_coordination_inflight_or_unknown' if unresolved else 'coordination_due' if actionable else 'phase_already_coordinated',
                    'external_permission_issued': False})
        except (w.WorkflowError, ValueError, OSError, KeyError, TypeError) as exc:
            errors.append({'event_key': 'publication-invalid-progress:' + cert['certificate_id'],
                'task_id': cert['task_id'], 'certificate_id': cert['certificate_id'], 'scope': cert['scope'],
                'state': 'not_ready', 'reason': str(exc), 'next_owner': 'system-development', 'actionable': False,
                'external_permission_issued': False})
    return result + errors


def next_deadline(root, now=None):
    at = clock(now); values = []
    for cert in certificates(root, errors=[]):
        try:
            intents = _intents(root, cert)
            view = status(root, cert, now=at)
            coverage = set().union(*[_covered_phases(cert, x, dependency=view['dependency']) for x in intents]) if intents else set()
            for pending in view['pending_deadlines']:
                if pending['phase'] not in coverage and clock(pending['deadline']) > at:
                    values.append(clock(pending['deadline']))
        except (w.WorkflowError, ValueError, OSError, KeyError, TypeError):
            continue
    return min(values).isoformat() if values else None


def task_status(root, task_id):
    errors = []
    values = [status(root, c) for c in certificates(root, errors=errors) if c['task_id'] == task_id]
    return {'task_id': task_id, 'publications': values, 'errors': [e for e in errors if e['task_id'] == task_id],
            'production_permission_issued': False, 'business_goal_closed': False}


def _delegation(root):
    import department_autonomy as a
    a.authority(root)
    source = doc(root, OWNER_DELEGATION)
    fixed = w.department_registry(root)['operations']['chat_binding']
    need(source.get('schema') == 'actual-first-party-owner-directive/v1'
         and source.get('source') == 'first_party_read_thread' and source.get('role') == 'human'
         and source.get('source_thread_id') == fixed.get('task_id')
         and source.get('source_turn_id') == 'example-native-8e7e2fa7499f8158'
         and source.get('message_id') == 'example-native-f438de429bc93cd7'
         and source.get('original_message') == [{'type': 'text', 'text': OWNER_TEXT}]
         and Path(source.get('project_root', '')).resolve() == Path(root).resolve(), 'actual_current_owner_routine_delegation_required')
    return OWNER_DELEGATION


def _shared_serial_guard(root, target_thread_id, transport=None, original_intent=None):
    """Use the same original root intent guard as receipt dispatch, never a
    second allowance. Missing/inconsistent/active/UNKNOWN is fail-closed.
    Original-key effect observations deliberately do not enter this gate.
    """
    from receipt_obligation_consumer import shared_serial_guard
    guard = shared_serial_guard(root, target_thread_id=target_thread_id, transport=transport, original_intent=original_intent)
    need(isinstance(guard, dict), 'shared_original_root_serial_guard_document_required')
    allowed = (guard.get('new_activation_allowed') is True if original_intent is None else
               guard.get('original_intent_commit_allowed') is True and guard.get('new_activation_allowed') is False
               and guard.get('slot', {}).get('request') == original_intent)
    need(allowed and isinstance(guard.get('source'), dict),
         'shared_original_root_serial_guard:' + str({'state': guard.get('state'), 'reasons': guard.get('reasons')}))
    need(w.file_digest(root, guard['source'].get('path', '')) == guard['source'], 'current_root_serial_source_changed')
    return guard


def body(row):
    return ('【同原目标发布时限普通协调；不是新增生产许可】\n'
            + 'service_origin=' + SERVICE_ORIGIN + '\n'
            + json.dumps({**{k: row[k] for k in ('task_id', 'scope', 'event_key', 'certificate_id', 'object',
                         'object_identity', 'content_sha256', 'publisher_department', 'phase', 'deadline', 'source', 'dependency_generation')},
                         'dependency': {k: row['dependency'][k] for k in
                            ('source_fingerprint', 'dependency_holder', 'unblock_input', 'next_check_at')} if row.get('dependency') else None},
                         ensure_ascii=False, sort_keys=True)
            + '\n由原专业owner沿原task核原发布者及原键：确认真实接单和后续动作、核真实preflight/执行启动，或交清具名依赖持有人、解除输入与下次事件。'
              '先核原UNKNOWN/在途效果；只处理准确对象；不得重复Save/发布，不扩大账号、预算、费用或TTL；原生产门禁照常。')


def event_route(root, snap, request):
    """Strict separate normal-policy route; never pretends a producer receipt."""
    marker = request.get(MARKER)
    if marker is None:
        return None
    snapshot(root, request['task_id'])
    _delegation(root)
    need(isinstance(marker, dict) and set(marker) == {'event_key', 'certificate_id', 'source_fingerprint'}, 'exact_deadline_marker_required')
    matches = [r for r in due_work(root) if r['event_key'] == marker.get('event_key')]
    need(len(matches) == 1, 'real_authenticated_overdue_object_required')
    row = matches[0]; need(row['actionable'], 'original_coordination_UNKNOWN_or_inflight_never_repeat')
    registry = w.department_registry(root); source = registry['operations']['chat_binding']; target = registry[row['next_owner']]['chat_binding']
    shared = _shared_serial_guard(root, target['task_id'])
    expected = {'task_id': row['task_id'], 'scope': row['scope'], 'sender_department': 'operations',
                'target_department': row['next_owner'], 'action_id': row['event_key'], 'action_class': 'thread_message',
                'source_project_id': source['project_id'], 'target_project_id': target['project_id'],
                'target_thread_id': target['task_id'], 'target_thread_title': target['title'], 'target_cwd': target['cwd'],
                'target_sidebar_section_id': target['sidebar_section_id'], 'owner_delegation': OWNER_DELEGATION,
                'service_origin': SERVICE_ORIGIN,
                'covered_phases': row['covered_phases'],
                'dependency_generation': row['dependency_generation'],
                'root_serial_source': shared['source'],
                'authorization_changes': [], 'assignment_record_required': False, 'delivery_mode': 'official_native_queue'}
    need(all(request.get(k) == v for k, v in expected.items()) and snap.get('task_id') == row['task_id']
         and marker == {k: row[k] for k in marker}, 'exact_original_scope_owner_payload_route_required')
    need(source['project_id'] == target['project_id'] and Path(source['cwd']).resolve() == Path(root).resolve() == Path(target['cwd']).resolve(),
         'same_project_only_no_account_or_scope_expansion')
    for role in ('operations', row['next_owner']):
        need(registry[role].get('new_dispatch_enabled') is True
             and w._chat_binding_healthy(registry[role]['chat_binding'], verification_ttl_hours=26), 'fresh_real_fixed_role_health_required')
    need(not any(request.get(k) for k in ('approval_id', 'consume_approval', 'execution_request', 'result_notification', 'routine_delegation')),
         'coordination_only_no_production_or_receipt_replay')
    pin = request.get('payload'); need(isinstance(pin, dict) and w.file_digest(root, pin.get('path', '')) == pin
         and pin['sha256'] == request.get('payload_sha256')
         and w.safe_path(root, pin['path']).read_text() == body(row), 'immutable_exact_deadline_message_required')
    return {'purpose': 'publication_deadline_ordinary_coordination', 'source': pin, 'report': row['source'],
            'scope': row['scope'], 'sender_department': 'operations', 'target_department': row['next_owner'],
            'service_origin': SERVICE_ORIGIN,
            'owner_delegation': OWNER_DELEGATION, 'event_key': row['event_key'], 'external_permission_issued': False}


def prepare_message(root, request):
    """Normal action-policy entry; no hard-coded allow response or new permit."""
    event_route(root, snapshot(root, request['task_id']), request)
    policy, _ = w.policy_check(root, department=request['sender_department'],
            **{k: request[k] for k in FIELDS}, delivery_mode='official_native_queue', original_message=request)
    return {'status': 'ready_to_queue' if policy['status'] == 'allow' else 'blocked',
            'policy_decision': policy, 'payload': request['payload'], 'message_sent': False,
            'external_permission_issued': False}


def _minimal_item(turn, item):
    # Deliberately omit text, content, arguments, command and output. This is an
    # effect observation, never a replacement full native source or authority.
    return {'turn_id': turn.get('id'), 'item_id': item.get('id'), 'type': item.get('type'),
            'sha256': w.sha256_value(item),
            'provider_at': _provider_time(item).isoformat() if _provider_time(item) else None}


def observe_original(root, transport, intent):
    """Bounded native read, minimal exact-object effect projection only."""
    request = doc(root, intent['request'])
    need(transport.history is not None, 'original_native_readback_connection_required')
    wanted = w.safe_path(root, request['payload']['path']).read_text()
    marker = request[MARKER]; cert = next(c for c in certificates(root) if c['certificate_id'] == marker['certificate_id'])
    tokens = (request['task_id'], request['action_id'], cert['object_identity'], cert['content_sha256'])
    previous_entries = [e['details'][OBSERVATION_EVENT] for e in _events(root, cert['task_id'])
                        if e.get('details', {}).get(OBSERVATION_EVENT, {}).get('event_key') == intent['event_key']]
    previous = doc(root, previous_entries[-1]['projection']) if previous_entries else {}
    known_turn = (previous.get('original_input') or {}).get('turn_id')
    cursor = None; found = []; pages = 0
    # The existing history adapter exposes turns/list, not a documented single
    # turn read. Reuse that route with small bounded pages and stop on the known
    # exact turn; never persist the received pages.
    for _ in range(3):
        args = {'threadId': request['target_thread_id'], 'limit': 5, 'sortDirection': 'desc', 'itemsView': 'full'}
        if cursor is not None:
            args['cursor'] = cursor
        page = transport.history.call('thread/turns/list', args); pages += 1
        need(isinstance(page, dict) and isinstance(page.get('data'), list), 'complete_native_effect_read_page_required')
        for turn in page['data']:
            if known_turn and turn.get('id') != known_turn:
                continue
            for index, message in enumerate(turn.get('items', [])):
                if message.get('type') != 'userMessage':
                    continue
                fragments = [c.get('text', '') for c in message.get('content', []) if c.get('type') == 'text']
                if ''.join(fragments) != wanted and '\n'.join(fragments) != wanted:
                    continue
                ack = None; followup = None
                for item in turn['items'][index+1:]:
                    if item.get('type') == 'agentMessage' and all(token in item.get('text', '') for token in tokens):
                        ack = item
                    elif ack is not None and item.get('type') in {'commandExecution', 'mcpToolCall', 'functionCall'}:
                        encoded = json.dumps(item, ensure_ascii=False)
                        if all(token in encoded for token in tokens) and item.get('status') == 'completed' and item.get('exitCode', 0) == 0:
                            followup = item; break
                found.append((turn, message, ack, followup))
        if found or known_turn and any(t.get('id') == known_turn for t in page['data']):
            break
        next_cursor = page.get('nextCursor')
        if not next_cursor or next_cursor == cursor:
            break
        cursor = next_cursor
    need(len(found) <= 1, 'duplicate_original_coordination_effect_inspect_original_key')
    proof = {'schema': 'publication-coordination-effect-observation/v1', 'observation_only': True,
             'not_a_full_native_source': True, 'authorization_issued': False, 'event_key': intent['event_key'],
             'intent_request': intent['request'], 'task_id': cert['task_id'], 'scope': cert['scope'],
             'certificate_id': cert['certificate_id'], 'object_identity': cert['object_identity'],
             'content_sha256': cert['content_sha256'], 'target_thread_id': request['target_thread_id'],
             'source_transport': 'existing_official_readonly_history', 'original_input': None, 'ack': None, 'followup': None,
             'state': 'original_coordination_effect_unknown', 'repeat_allowed': False, 'publisher_ack_proven': False,
             'business_goal_closed': False}
    if found:
        turn, original, ack, action = found[0]
        proof.update(original_input=_minimal_item(turn, original), ack=_minimal_item(turn, ack) if ack else None,
                     followup=_minimal_item(turn, action) if action else None,
                     state='original_owner_followthrough_observed' if ack and action and turn.get('status') == 'completed' and not turn.get('error')
                     else 'original_owner_ACK_observed_not_publisher_ACK' if ack else 'original_owner_message_received')
    fingerprint = w.sha256_value(proof)
    directory = w.safe_path(root, intent['directory']); path = directory / ('effect-observation-' + fingerprint + '.json')
    if not path.exists():
        proof['management_observed_at'] = clock().isoformat()
        w.atomic_write_json(path, proof)
    stored = doc(root, w.file_digest(root, str(path.relative_to(root))))
    if not previous_entries or previous_entries[-1].get('projection', {}).get('path') != str(path.relative_to(root)):
        with w.workflow_lock(root):
            fresh = snapshot(root, cert['task_id'])
            w.append_workflow_event(root, cert['task_id'], fresh['current_state'], {OBSERVATION_EVENT: {
                'event_key': intent['event_key'], 'projection': w.file_digest(root, str(path.relative_to(root))),
                'service_origin': SERVICE_ORIGIN, 'observation_only': True}})
    return {**stored, 'effect_readback': w.file_digest(root, str(path.relative_to(root))), 'bounded_pages_read': pages}


def serial_pending(root):
    """Shared existing-loop slot projection. ACK alone does not release it."""
    events = _events(root)
    pending = [event for event in events if event.get('details', {}).get(INTENT_EVENT)]
    if not pending:
        return None
    certs = {c['certificate_id']: c for c in certificates(root, errors=[])}
    for e in pending:
        intent = e['details'][INTENT_EVENT]
        try:
            if _resolved_intent(root, intent):
                continue
        except (w.WorkflowError, ValueError, OSError, KeyError, TypeError):
            pass
        cert = certs.get(intent['certificate_id'])
        if cert:
            try:
                view = status(root, cert)
            except (w.WorkflowError, ValueError, OSError, KeyError, TypeError):
                view = {'state': 'unknown'}
            if view['state'] in {'completed', 'executed_pending_public'}:
                continue
            if (view['state'] == 'external_wait' and view.get('next_check_at') and clock(view['next_check_at']) > clock()
                    and _known_original_input(root, intent)):
                continue
        return {'event_key': intent['event_key'], 'certificate_id': intent['certificate_id'],
                'task_id': e['task_id'], 'state': 'publication_original_inflight_or_unknown',
                'ack_releases_slot': False, 'intent': intent}
    return None


def _consume_one(root, row, transport):
    import department_event_dispatcher as dispatcher
    need(isinstance(transport, dispatcher.OfficialQueueTransport), 'existing_official_native_transport_only')
    _delegation(root)
    directory = Path('logs/department-event-dispatcher/publication-deadlines') / row['event_key'].split(':')[-1]
    dest = w.safe_path(root, str(directory)); dest.mkdir(parents=True, exist_ok=True)
    path = dest / 'message.txt'; text = body(row)
    need(not path.exists() or path.read_text() == text, 'frozen_coordination_bytes_changed')
    path.write_text(text)
    source = dispatcher.binding(root, 'operations'); target = dispatcher.binding(root, row['next_owner'])
    shared = _shared_serial_guard(root, target['task_id'], transport)
    pin = w.file_digest(root, str(path.relative_to(root)))
    request = {'task_id': row['task_id'], 'action_id': row['event_key'], 'scope': row['scope'],
               'action_class': 'thread_message', 'sender_department': 'operations', 'target_department': row['next_owner'],
               'source_project_id': source['project_id'], 'target_project_id': target['project_id'],
               'target_thread_id': target['task_id'], 'target_thread_title': target['title'], 'target_cwd': target['cwd'],
               'target_sidebar_section_id': target['sidebar_section_id'], 'payload': pin, 'payload_sha256': pin['sha256'],
               'owner_delegation': OWNER_DELEGATION, 'authorization_changes': [], 'assignment_record_required': False,
               'service_origin': SERVICE_ORIGIN,
               'covered_phases': row['covered_phases'],
               'dependency_generation': row['dependency_generation'],
               'root_serial_source': shared['source'],
               'delivery_mode': 'official_native_queue', MARKER: {k: row[k] for k in ('event_key', 'certificate_id', 'source_fingerprint')}}
    for field, role in (('actual_sender_state', 'operations'), ('actual_target_state', row['next_owner'])):
        native = dest / (field + '.json'); w.atomic_write_json(native, transport._read(role))
        request[field] = w.file_digest(root, str(native.relative_to(root)))
    request['live_observed_at'] = w.utc_timestamp()
    request_path = dest / 'request.json'; w.atomic_write_json(request_path, request)
    prepared = prepare_message(root, request); w.atomic_write_json(dest / 'normal-preparation.json', prepared)
    need(prepared.get('status') == 'ready_to_queue' and prepared.get('policy_decision', {}).get('status') == 'allow'
         and prepared.get('external_permission_issued') is False, 'normal_policy_blocked')
    with w.workflow_lock(root):
        _shared_serial_guard(root, request['target_thread_id'], transport)
        event_route(root, snapshot(root, row['task_id']), request)
        need(serial_pending(root) is None, 'existing_shared_new_window_slot_owned_by_original_effect')
        checked = clock(prepared['policy_decision'].get('checked_at'))
        need(0 <= (clock()-checked).total_seconds() <= 300, 'fresh_normal_policy_required')
        intent = {'event_key': row['event_key'], 'action_id': row['event_key'], 'certificate_id': row['certificate_id'],
                  'source_fingerprint': row['source_fingerprint'], 'covered_phases': row['covered_phases'],
                  'dependency_generation': row['dependency_generation'], 'request': w.file_digest(root, str(request_path.relative_to(root))),
                  'directory': str(directory), 'policy_decision_id': prepared['policy_decision']['decision_id'],
                  'original_owner': row['next_owner'], 'publisher_department': row['publisher_department'],
                  'state': 'original_effect_unknown_until_native_readback', 'external_permission_issued': False}
        intent.update(service_origin=SERVICE_ORIGIN, owner_delegation=OWNER_DELEGATION)
        snap = snapshot(root, row['task_id'])
        w.append_workflow_event(root, row['task_id'], snap['current_state'], {INTENT_EVENT: intent})
        from receipt_obligation_consumer import reserve_root_serial
        reserve_root_serial(root, request, intent, transport=transport, already_locked=True)
    # Re-read the real current pause/scope/source after intent and before queue.
    certificates_now = certificates(root, errors=[])
    need(any(c['certificate_id'] == row['certificate_id'] for c in certificates_now), 'current_ready_certificate_required_before_queue')
    snapshot(root, row['task_id'])
    final_shared = _shared_serial_guard(root, request['target_thread_id'], transport, original_intent=intent['request'])
    need(final_shared['source'] == request['root_serial_source'], 'root_serial_source_changed_before_queue')
    effect = transport.enqueue({'directory': dest, 'thread_id': request['target_thread_id'], 'message': text,
                                'payload_sha256': pin['sha256'], 'policy_decision_id': intent['policy_decision_id']})
    return {**row, 'state': 'coordination_queue_accepted_not_publisher_ACK', 'message_id': effect['message_id'],
                     'actionable': False, 'message_sent': True, 'business_goal_closed': False}


def consume_due(root, transport=None, now=None):
    """Per-object failures stay scoped. One shared new-window slot, never a burst."""
    from readonly_work_view_cache import inventory_active
    need(not inventory_active(root), 'effects_require_uncached_normal_context')
    need(transport is None or now is None, 'caller_effect_clock_forbidden')
    outcomes = []; activated = False
    for original_row in due_work(root, now=now):
        row = original_row
        try:
            if row.get('original_intent') and transport is not None:
                observed = observe_original(root, transport, row['original_intent'])
                fresh = next((r for r in due_work(root, now=now) if r.get('certificate_id') == row.get('certificate_id')), row)
                row = {**fresh, 'original_effect': observed}
            if not row['actionable'] or transport is None:
                outcomes.append({**row, 'message_sent': False}); continue
            blocking = serial_pending(root)
            if activated or blocking:
                outcomes.append({**row, 'state': 'waiting_serial', 'serial_owner': blocking,
                                 'actionable': False, 'message_sent': False}); continue
            outcome = _consume_one(root, row, transport)
            outcomes.append(outcome); activated = True
        except Exception as exc:
            # No source/policy/health refusal escapes and starves independent
            # items. An intent already persisted retains the shared slot even
            # when the transport raised or returned UNKNOWN.
            blocked = serial_pending(root)
            outcomes.append({**row, 'state': 'original_effect_unknown' if blocked and blocked.get('certificate_id') == row.get('certificate_id')
                             else 'publication_coordination_blocked', 'reason': str(exc),
                             'actionable': False, 'message_sent': False, 'serial_owner': blocked,
                             'external_permission_issued': False})
    return outcomes
