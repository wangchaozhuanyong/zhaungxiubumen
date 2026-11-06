"""Recover real owner/native assignments, without fabricating dispatch or permission.

The existing workflow journal and assignment stack are the only state stores.
Historical transport proves what happened, never a new execution authorization.
"""
from __future__ import annotations

# Direct CLI execution must share opaque classes, seals and ContextVars with
# the canonical imports performed by runtime collaborators later in this file.
if __name__ == '__main__':
    import sys
    sys.modules['goal_source_recovery'] = sys.modules[__name__]

import argparse
from contextlib import contextmanager
from contextvars import ContextVar
import json
import shlex
from pathlib import Path
import re
import workflow_control as w
from department_rotation import historical_assignment_validator

SCHEMA = 'goal-native-source-recovery/v1'

# This frozen original responsibility was queued from its normal prepared RESULT.
# Its actual command never named the request. Keep the original bytes and pins;
# this one history is not a general exemption from invocation/path verification.
_PREPARED_RESULT_QUEUE_SOURCES = {'fc-20261021-a04-kl-source-code-release-readiness-v1': {'scope': 'project:flashcast:a04-kl-source-code-release-readiness:20261021:v1',
                                                         'department': 'operations-assistant',
                                                         'source_call_id': 'exec-767a60b3-9682-4d62-b8ae-8b1e0ecafc77',
                                                         'queue_message_id': 'example-native-20cbadd23dd91374',
                                                         'original_prepare_request': {'path': 'logs/handoffs/2026-10-20-clean-department-window-rotation-v1/operations/unfinished-business-followthrough-20261021-v1/KL-original-owner-source-code-and-release-readiness-v1/operations-assistant-prepare-request-v1.json',
                                                                                      'sha256': '62a7cb856644453c66a139a5c5cc8c81dea86f91875ef67499abf535358eb334',
                                                                                      'size': 1707},
                                                         'original_prepare_result': {'path': 'logs/handoffs/2026-10-20-clean-department-window-rotation-v1/operations/unfinished-business-followthrough-20261021-v1/KL-original-owner-source-code-and-release-readiness-v1/operations-assistant-prepare-result-v1.json',
                                                                                     'sha256': '1e1e5934de6bfdfc376800034a6a0df00bca878f8dac674f39bc33e218e070ad',
                                                                                     'size': 3501},
                                                         'actual_queue_intent': {'path': 'logs/handoffs/2026-10-20-clean-department-window-rotation-v1/operations/unfinished-business-followthrough-20261021-v1/KL-original-owner-source-code-and-release-readiness-v1/A1-KL-review-official-native-queue-v1/native-queue-intent.json',
                                                                                 'sha256': '4ccb3c9537ff563ed40da75f6013ec720af83f35d39f9f9f16deb68ab5fa1d58',
                                                                                 'size': 316},
                                                         'actual_queue_result': {'path': 'logs/handoffs/2026-10-20-clean-department-window-rotation-v1/operations/unfinished-business-followthrough-20261021-v1/KL-original-owner-source-code-and-release-readiness-v1/A1-KL-review-official-native-queue-v1/native-queue-result.json',
                                                                                 'sha256': '7349cac877ad30232001659b2d8b404c0e743170cfc4160fdc5b7995ca654184',
                                                                                 'size': 521},
                                                         'original_native': {'path': 'logs/handoffs/2026-10-20-clean-department-window-rotation-v1/operations/unfinished-business-followthrough-20261021-v1/KL-original-owner-source-code-and-release-readiness-v1/operations-assistant-original-queue-command-native-v1.json',
                                                                             'sha256': '1d673e709d0937cefca65721ab31152e57ed7d8d7d44ead484f9536db29a8023',
                                                                             'size': 3352}}}


def _native_container_valid(value):
    """Preserve the existing native failure semantics through nested results."""
    if not isinstance(value, dict) or value.get('status') == 'failed' or value.get('error'):
        return False
    if any(flag in value and value[flag] is not False
           for flag in ('failed', 'truncated', 'superseded', 'isError')):
        return False
    if 'errors' in value and (not isinstance(value['errors'], list) or value['errors']):
        return False
    return all(_native_container_valid(value[key]) for key in
               ('result', 'output', 'structuredContent', 'actual_tool_result')
               if key in value and isinstance(value[key], dict))


def _selected_native_valid(value, *, statuses=(None, 'inProgress', 'completed')):
    """Check selected turn/item and any nested result, not only its wrapper."""
    return (_native_container_valid(value) and value.get('status') in statuses)


def _queue_receipt_turn_valid(turn):
    """A genuine earlier ACK survives a later failed execution, never a result.

    Only the official-queue receipt reader uses this boundary. The raw native
    source is preserved; caller flags cannot supply receipt or completion.
    Selected user/ACK bytes, identity, order and queue chronology are still
    verified by collaboration_queue_source. Final results stay completed-only.
    """
    if _selected_native_valid(turn):
        return True
    if not isinstance(turn, dict) or turn.get('status') != 'failed':
        return False
    error = turn.get('error')
    if not isinstance(error, dict) or not isinstance(error.get('message'), str) or not error['message'].strip():
        return False
    # Exempt only the explicit execution outcome, retaining every transport,
    # truncation, supersession and nested-container failure check.
    metadata = {key: value for key, value in turn.items() if key not in {'status', 'error'}}
    if not _native_container_valid(metadata):
        return False
    import math
    start, finish = turn.get('startedAt'), turn.get('completedAt')
    if (type(start) not in {int, float} or type(finish) not in {int, float}
            or not math.isfinite(start) or not math.isfinite(finish)):
        return False
    now = w._parse_observed_at(w.utc_timestamp()).timestamp()
    return start <= finish <= now + 1


def _queue_unique_fields(pairs):
    result={}
    for key,value in pairs:
        if key in result:raise ValueError('duplicate official queue source field')
        result[key]=value
    return result


def _strict_queue_document(root, pin):
    """Decode the pinned raw JSON once, rejecting duplicate and failed sources."""
    if not isinstance(pin, dict) or w.file_digest(root, pin.get('path','')) != pin:
        raise w.WorkflowError('exact pinned official queue source required')
    try:
        value=json.loads(w.validation_bytes(w.safe_path(root,pin['path'])),
                         object_pairs_hook=_queue_unique_fields,
                         parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite queue source')))
    except (ValueError,TypeError) as error:
        raise w.WorkflowError('unambiguous raw official queue source required') from error
    def complete(node):
        if isinstance(node, list):return all(complete(child) for child in node)
        if not isinstance(node, dict):return True
        if not _native_container_valid(node):return False
        return all(complete(child) for child in node.values())
    if not isinstance(value, dict) or not complete(value):
        raise w.WorkflowError('successful complete official queue source required')
    return value


def _exact_task_reference(message, task):
    return isinstance(message, str) and re.search(
        r'(?<![A-Za-z0-9_-])' + re.escape(task) + r'(?![A-Za-z0-9_-])', message) is not None


def _prepared_result_queue_invocation(root, item, turn, call):
    """Authenticate the exact original call, while requiring a real ended source turn."""
    expected = _PREPARED_RESULT_QUEUE_SOURCES.get(item.get('task_id'))
    if expected is None:
        return None
    if (turn.get('status') != 'completed'
            or any(item.get(key) != value for key, value in expected.items() if key != 'original_native')):
        return False
    native = _strict_queue_document(root, expected['original_native'])
    originals = [(t, c) for t in native.get('turns', []) for c in t.get('items', [])
                 if c.get('id') == expected['source_call_id'] and c.get('type') == 'commandExecution']
    if len(originals) != 1:
        raise w.WorkflowError('one frozen original prepared-result queue invocation required')
    prior_turn, prior_call = originals[0]
    return (turn.get('id') == prior_turn.get('id') and turn.get('startedAt') == prior_turn.get('startedAt')
            and all(call.get(key) == value for key, value in prior_call.items()))


# This actual HQ call used a literal two-member loop to select frozen request,
# result and directory paths. Authenticate the original call, not caller flags.
_TWO_COMPAT_ORIGINAL_LOOP_SOURCES = {'operations-assistant-2': {'scope': 'project:flashcast:main-runtime-two-compat-closeout:20261022:v1', 'goal_contract': {'path': 'logs/handoffs/2026-10-22-owner-permanent-cleanup-and-runtime-continuation-v1/complete-main-runtime-two-compat-closeout-goal-v1.json', 'sha256': 'a765fecbba62da7391d202df2aaf7109e9ef356556e6e6cc973231d25cb13672', 'size': 4566}, 'authorization_pin': {'path': 'logs/handoffs/2026-10-22-owner-permanent-cleanup-and-runtime-continuation-v1/actual-owner-main-runtime-unfinished-continuation-source.json', 'sha256': '3b457363c88f74f4f442563b57c72cc27d293cbfe96b22fd48826825a8ea9610', 'size': 1484}, 'source_call_id': 'exec-5e322a5e-8f5c-40be-ad04-c0bc8670a67a', 'original_prepare_request': {'path': 'logs/handoffs/2026-10-22-owner-permanent-cleanup-and-runtime-continuation-v1/two-compat-A2-prepare-request.json', 'sha256': '3f8ea55f3c689049e9f4b3733077f8775ac4952da9ff11541910316c50f5d1c5', 'size': 1486}, 'original_prepare_result': {'path': 'logs/handoffs/2026-10-22-owner-permanent-cleanup-and-runtime-continuation-v1/two-compat-A2-prepare-result.json', 'sha256': '8e62166371d53f042f9cc178c845718adec54e3c2494545e84e97bee5c2be9a9', 'size': 4039}, 'actual_queue_intent': {'path': 'logs/handoffs/2026-10-22-owner-permanent-cleanup-and-runtime-continuation-v1/two-compat-A2-official-queue/native-queue-intent.json', 'sha256': 'adb39065c0563353ee9b4e35916d1479299bfb9f86e5d3db6be923f4baf9b9b0', 'size': 316}, 'actual_queue_result': {'path': 'logs/handoffs/2026-10-22-owner-permanent-cleanup-and-runtime-continuation-v1/two-compat-A2-official-queue/native-queue-result.json', 'sha256': 'cc0a0e6279605e9a975dee56150465020f2fa6b06f6ec7570727eabd81357803', 'size': 521}, 'queue_message_id': 'example-native-a1a0b968e844af8b', 'actual_native_invocation': {'path': 'logs/handoffs/2026-10-22-owner-permanent-cleanup-and-runtime-continuation-v1/operations-assistant-2-original-responsibility-intake-v1/actual-HQ-completed-original-queue-invocation-native-v1.json', 'sha256': 'bb1cfadd975eb3c3c19e6fdd70c3f5ec0c85ff068d690c63ac989470d4891697', 'size': 3899}}, 'system-development': {'scope': 'project:flashcast:main-runtime-two-compat-closeout:20261022:v1', 'goal_contract': {'path': 'logs/handoffs/2026-10-22-owner-permanent-cleanup-and-runtime-continuation-v1/complete-main-runtime-two-compat-closeout-goal-v1.json', 'sha256': 'a765fecbba62da7391d202df2aaf7109e9ef356556e6e6cc973231d25cb13672', 'size': 4566}, 'authorization_pin': {'path': 'logs/handoffs/2026-10-22-owner-permanent-cleanup-and-runtime-continuation-v1/actual-owner-main-runtime-unfinished-continuation-source.json', 'sha256': '3b457363c88f74f4f442563b57c72cc27d293cbfe96b22fd48826825a8ea9610', 'size': 1484}, 'source_call_id': 'exec-5e322a5e-8f5c-40be-ad04-c0bc8670a67a', 'original_prepare_request': {'path': 'logs/handoffs/2026-10-22-owner-permanent-cleanup-and-runtime-continuation-v1/two-compat-SYS-prepare-request.json', 'sha256': '56435522f3b8a8e2e43256cd64e491b6e334162e9500a77914bf2bd0395e8441', 'size': 1498}, 'original_prepare_result': {'path': 'logs/handoffs/2026-10-22-owner-permanent-cleanup-and-runtime-continuation-v1/two-compat-SYS-prepare-result.json', 'sha256': '71e6ba3e34caf30db9ea527d8a123bd122d26252c3b4749bec4c1ff1be5619f7', 'size': 4046}, 'actual_queue_intent': {'path': 'logs/handoffs/2026-10-22-owner-permanent-cleanup-and-runtime-continuation-v1/two-compat-SYS-official-queue/native-queue-intent.json', 'sha256': '7e450f13d32e2bc6494f59c45c45221be70265ae93034ffd11425b753503be0d', 'size': 316}, 'actual_queue_result': {'path': 'logs/handoffs/2026-10-22-owner-permanent-cleanup-and-runtime-continuation-v1/two-compat-SYS-official-queue/native-queue-result.json', 'sha256': '5cb8d8bedc7d831945d103c6d1946c7771deeddf1cbff08d50a11b1d1dfa5cac', 'size': 521}, 'queue_message_id': 'example-native-e900029ca7667982', 'actual_native_invocation': {'path': 'logs/handoffs/2026-10-22-owner-permanent-cleanup-and-runtime-continuation-v1/operations-assistant-2-original-responsibility-intake-v1/actual-HQ-completed-original-queue-invocation-native-v1.json', 'sha256': 'bb1cfadd975eb3c3c19e6fdd70c3f5ec0c85ff068d690c63ac989470d4891697', 'size': 3899}}}


def _two_compat_original_loop_invocation(root, item, turn, call):
    if item.get('task_id') != 'fc-20261022-main-runtime-two-compat-closeout-v1':
        return None
    expected = _TWO_COMPAT_ORIGINAL_LOOP_SOURCES.get(item.get('department'))
    if expected is None:
        return None
    if item.get('restore_position') != 'suspended':
        return False
    if any(item.get(key) != value for key, value in expected.items()):
        return False
    original = _strict_queue_document(root, expected['actual_native_invocation'])
    calls = [(t, c) for t in original.get('turns', []) for c in t.get('items', [])
             if c.get('id') == expected['source_call_id'] and c.get('type') == 'commandExecution']
    if len(calls) != 1:
        raise w.WorkflowError('one exact original two-compat loop queue call required')
    prior_turn, prior_call = calls[0]
    return (prior_turn.get('status') == turn.get('status') == 'completed'
            and all(turn.get(key) == prior_turn.get(key) for key in ('id', 'startedAt', 'completedAt'))
            and call == prior_call)


@historical_assignment_validator
def queued_assignment_source(root, item, *, require_dispatch=True):
    """Consume an actual official queue AND recipient ACK, never queue acceptance alone.

    Queue IDs and persisted user-message IDs are different native identities.
    Their link is the original allowed payload, invocation and receiving turn.
    Recovered receipts are appended now; original transport times stay evidence.
    """
    import datetime as dt
    from goal_continuity import _task, pin_document
    from goal_delivery_runtime import _collaboration_native
    task = w.validate_task_id(item.get('task_id', ''))
    if item.get('sender_department') != 'operations':
        from owner_adopted_pilot_consumer import queued_rework_source
        continuation = queued_rework_source(root, item, require_dispatch=require_dispatch)
        if continuation is not None:
            return continuation
    snapshot = _task(root, task); goal = snapshot['goal_delivery']
    role = item.get('department')
    from department_rotation import historical_registry
    registry = historical_registry(root, item)
    if (item.get('schema') != 'goal-current-assignment/v2'
            or item.get('source_kind') != 'official_native_queue'
            or item.get('sender_department') != 'operations'
            or role not in {*goal['producer_departments'], goal['responsible_assistant']}
            or item.get('scope') not in goal['authorized_scope']
            or item.get('goal_contract') != snapshot.get('goal_contract')
            or item.get('authorization_pin') != goal['authorization_pin']
            or w.validate_workflow_events(root, task)):
        raise w.WorkflowError('exact original queued goal participant responsibility required')
    pin_document(root, goal['authorization_pin']); pin_document(root, snapshot['goal_contract'])
    request = pin_document(root, item['original_prepare_request'])
    prepared = pin_document(root, item['original_prepare_result'])
    payload = item['payload']
    if w.file_digest(root, payload.get('path', '')) != payload:
        raise w.WorkflowError('original queued assignment bytes changed')
    body = w.safe_path(root, payload['path']).read_text(encoding='utf-8')
    fixed = registry[role]['chat_binding']; source = registry['operations']['chat_binding']
    reviewer = role == goal['responsible_assistant']
    action_id = 'assign-goal-review:' + task if reviewer else item.get('action_id')
    if (not isinstance(action_id, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9:._+-]{0,199}', action_id)
            or (not reviewer and (goal.get('source_mode') != 'approved_dispatch'
                or action_id.startswith('assign-goal-review:')
                or not _exact_task_reference(body, task)
                or snapshot['goal_contract']['path'] not in body))):
        raise w.WorkflowError('exact approved producer goal and original assignment action required')
    expected = {'task_id': task, 'sender_department': 'operations',
        'action_id': action_id, 'action_class': 'thread_message',
        'scope': item['scope'], 'delivery_mode': 'official_native_queue',
        'payload': payload, 'payload_sha256': payload['sha256'],
        'source_project_id': source['project_id'], 'target_department': role,
        **{name: fixed[key] for name, key in {
            'target_project_id': 'project_id', 'target_thread_id': 'task_id',
            'target_thread_title': 'title', 'target_cwd': 'cwd',
            'target_sidebar_section_id': 'sidebar_section_id'}.items()}}
    if (any(request.get(k) != v for k, v in expected.items())
            or request.get('authorization_changes') != []
            or prepared.get('status') != 'ready_to_queue'
            or prepared.get('payload') != payload
            or (reviewer and not initial_responsibility_payload(root, snapshot, 'operations', role,
                                                  item['scope'], payload['sha256']))
            or (not reviewer and any(prepared.get('authorization_precheck', {}).get(k) != v for k, v in
                {'status': 'within_original_authorization', 'task_id': task,
                 'action_class': 'thread_message', 'scope': item['scope'],
                 'original_authorization': goal['authorization_pin'],
                 'actual_action_allowed': False, 'external_permission_issued': False}.items()))):
        raise w.WorkflowError('original exact queue preparation and frozen responsibility required')
    policy_id = prepared.get('policy_decision', {}).get('decision_id')
    policies = [p for p in w.read_jsonl(Path(root) / w.POLICY_DECISIONS)
                if p.get('decision_id') == policy_id]
    policy_expected = {k: v for k, v in expected.items()
                       if k not in {'sender_department', 'delivery_mode', 'payload'}}
    policy_expected.update(department='operations', status='allow', routing_status='routing_allowed')
    if len(policies) != 1 or any(policies[0].get(k) != v for k, v in policy_expected.items()):
        raise w.WorkflowError('original allowed queued assignment policy differs')
    intent = pin_document(root, item['actual_queue_intent'])
    result = pin_document(root, item['actual_queue_result'])
    transport = {'thread_id': fixed['task_id'], 'payload_sha256': payload['sha256'],
                 'policy_decision_id': policy_id, 'transport': 'official_codex_queue',
                 'intake_claimed': False}
    match = re.fullmatch(r'Queued message ([0-9a-f-]{36}) for thread ([0-9a-f-]{36})\.\s*',
                         result.get('stdout', ''))
    if (any(intent.get(k) != v or result.get(k) != v for k, v in transport.items())
            or result.get('started_at') != intent.get('started_at')
            or type(result.get('exit_code')) is not int or result['exit_code'] != 0
            or result.get('stderr') != '' or not match
            or match[1] != item.get('queue_message_id') or match[2] != fixed['task_id']):
        raise w.WorkflowError('one successful actual official queue effect required')
    sender = _collaboration_native(root, item['actual_native_invocation'])
    receiver = _collaboration_native(root, item['actual_native_recipient'])
    for page, binding in ((sender, source), (receiver, fixed)):
        if any(page.get('thread', {}).get(k) != binding.get(v) for k, v in
               {'id': 'task_id', 'title': 'title', 'cwd': 'cwd'}.items()):
            raise w.WorkflowError('actual fixed queued assignment chat identity differs')
    calls = [(t, c) for t in sender.get('turns', []) for c in t.get('items', [])
             if c.get('id') == item.get('source_call_id') and c.get('type') == 'commandExecution']
    if len(calls) != 1:
        raise w.WorkflowError('original official queue command invocation required')
    turn, call = calls[0]; command = call.get('command', '')
    queue_dir = str(Path(item['actual_queue_result']['path']).parent)
    prepared_invocation = _prepared_result_queue_invocation(root, item, turn, call)
    invocation_source_linked = (prepared_invocation is True if prepared_invocation is not None
                                else Path(item['original_prepare_request']['path']).name in command)
    original_loop = _two_compat_original_loop_invocation(root, item, turn, call)
    evidence_paths_linked = (original_loop if original_loop is not None else (
        Path(queue_dir).name in command and str(Path(queue_dir).parent) in command
        and invocation_source_linked and Path(item['original_prepare_result']['path']).name in command))
    if (turn.get('status') != 'completed' or call.get('status') != 'completed' or call.get('error') or turn.get('error')
            or type(call.get('exitCode')) is not int or call['exitCode'] != 0
            or call.get('truncated', False) is not False or call.get('cwd') != source['cwd']
            or 'OfficialQueueTransport' not in command or '.enqueue(' not in command
            or not evidence_paths_linked):
        raise w.WorkflowError('successful original queue invocation and evidence paths required')
    turns = [t for t in receiver.get('turns', []) if t.get('id') == item.get('receiver_turn_id')]
    if len(turns) != 1 or turns[0].get('error') or turns[0].get('status') not in {'inProgress', 'completed'}:
        raise w.WorkflowError('actual receiving assignment turn required')
    received = turns[0]; messages = received.get('items', [])
    users = [(i, m) for i, m in enumerate(messages) if m.get('id') == item.get('receiver_message_id')
             and m.get('type') == 'userMessage']
    acks = [(i, m) for i, m in enumerate(messages) if m.get('id') == item.get('ack_message_id')
            and m.get('type') == 'agentMessage']
    if (len(users) != 1 or len(acks) != 1 or users[0][0] >= acks[0][0]
            or users[0][1].get('content') != [{'type': 'text', 'text': body}]
            or not str(acks[0][1].get('text', '')).strip()):
        raise w.WorkflowError('actual original message bytes followed by nonempty same-turn ACK required')
    start, finish = (w._parse_observed_at(result.get(k)) for k in ('started_at', 'finished_at'))
    numbers = (turn.get('startedAt'), turn.get('completedAt'), received.get('startedAt'))
    if (not start or not finish or any(type(n) not in {int, float} for n in numbers)
            or not numbers[0] <= start.timestamp() <= finish.timestamp() <= numbers[1] + 1
            or not finish.timestamp() <= numbers[2] <= dt.datetime.now(dt.timezone.utc).timestamp()
            or not w._parse_observed_at(policies[0].get('checked_at'))
            or w._parse_observed_at(policies[0]['checked_at']) > start):
        raise w.WorkflowError('actual policy, queue invocation and recipient chronology required')
    key = 'queue-assignment-' + w.sha256_value([task, role, match[1], policy_id, payload])
    if item.get('dispatch_idempotency_key') != key:
        raise w.WorkflowError('stable original queue assignment identity required')
    if not require_dispatch:
        return snapshot, {'idempotency_key': key, 'policy_decision_id': policy_id,
                          'action_id': expected['action_id'], 'action_class': 'thread_message',
                          'scope': item['scope'], 'chat_task_id': fixed['task_id']}
    rows = [r for r in w.read_jsonl(w.receipts_path(root, task)) if r.get('idempotency_key') == key]
    if len(rows) != 1:
        raise w.WorkflowError('actual queued assignment recovered dispatch receipt required')
    row = rows[0]
    _, bad = w._validate_receipt_chain(root, task, through_receipt_id=row['receipt_id'])
    if (bad or row.get('receipt_type') != 'dispatch_sent' or row.get('department') != role
            or row.get('chat_task_id') != fixed['task_id'] or row.get('policy_decision_id') != policy_id
            or row.get('action_id') != expected['action_id'] or row.get('scope') != item['scope']):
        raise w.WorkflowError('intact actual queued assignment dispatch prefix required')
    return snapshot, row


def recover_queued_assignment(root, input_path):
    """Recover delivered original queue facts now, with no transport or new policy."""
    from goal_continuity import pin_document, record_assignment
    pin = w.file_digest(root, input_path); item = pin_document(root, pin)
    _, source = queued_assignment_source(root, item, require_dispatch=False)
    args = dict(task_id=item['task_id'], department=item['department'], evidence=pin['path'],
                ack_nonempty=False, **source)
    sent, _ = w.record_receipt(root, argparse.Namespace(**args, receipt_type='dispatch_sent'))
    # receipt-record attempts assignment projection too. Repeat is idempotent,
    # and recovers a crash between appending transport and projecting the source.
    assignment = record_assignment(root, item, pin)
    ack_args = {**args, 'idempotency_key': source['idempotency_key'] + '-ack', 'ack_nonempty': True}
    ack, _ = w.record_receipt(root, argparse.Namespace(**ack_args, receipt_type='chat_ack'))
    duplicate = sent.get('result') == ack.get('result') == 'duplicate_ignored'
    return {'result': assignment['result'] if duplicate else 'recorded', 'dispatch_receipt_id': sent['receipt_id'],
            'ack_receipt_id': ack['receipt_id'], 'actual_message_delivered': True,
            'transport_replayed': False, 'external_permission_issued': False,
            'original_queue_message_id': item['queue_message_id']}


def approved_dispatch_lf_source(root, snapshot, item, *, require_record=True):
    """Admit only the original approved 3014-byte send plus one actual LF.

    This is a transport reconciliation, never a new department assignment.
    """
    from goal_delivery_runtime import _collaboration_native
    task='fc-20261017-original204-two-renderer-development-handoff-v1'
    action_id='A1-original204-G01-G03-local-renderer-development-20261017-v1'
    scope='project:flashcast:original204-two-renderer-development-handoff:v1'
    goal=snapshot['goal_delivery']
    from department_rotation import historical_registry
    registry=historical_registry(root,item)
    fixed=registry['operations-assistant']['chat_binding']
    target=w.read_json(Path(root)/'data/department-registry.json')['collaboration_bindings']['designated-development']
    required={'schema':'goal-current-assignment/v2','task_id':task,'original_task_id':task,
              'department':'designated-development','sender_department':'operations-assistant',
              'source_kind':'historical_native_send','scope':scope,'action_id':action_id,
              'authorization_pin':goal['authorization_pin']}
    if (any(item.get(k)!=v for k,v in required.items()) or goal.get('source_mode')!='approved_dispatch'
            or goal.get('primary_owner')!='operations' or goal.get('producer_departments')!=['operations']
            or goal.get('responsible_assistant')!='operations-assistant'
            or goal.get('authorized_scope')!=[scope] or w.validate_workflow_events(root,task)):
        raise w.WorkflowError('exact original approved-dispatch LF identity required')
    actions=[a for a in goal.get('approved_actions',[]) if a.get('action_id')==action_id]
    if len(actions)!=1:raise w.WorkflowError('one frozen original collaboration action required')
    action=actions[0];approved=item.get('approved_payload');actual=item.get('payload')
    if (not isinstance(approved,dict) or not isinstance(actual,dict)
            or approved!=action.get('payload') or approved['size']!=3014 or actual.get('size')!=3015
            or item.get('original_policy_decision_id')!='pol-38387b72fab372e2c381'):
        raise w.WorkflowError('separate frozen approved and actual prompt pins required')
    for pin in (goal['authorization_pin'],approved,actual,item.get('actual_native_invocation'),
                item.get('actual_native_send'),item.get('actual_native_ack'),
                item.get('original_collaboration_record')):
        if not isinstance(pin,dict) or w.file_digest(root,pin.get('path',''))!=pin:
            raise w.WorkflowError('exact original LF source pin changed')
    approved_bytes=w.safe_path(root,approved['path']).read_bytes()
    actual_bytes=w.safe_path(root,actual['path']).read_bytes()
    if actual_bytes!=approved_bytes+b'\n':
        raise w.WorkflowError('only one terminal 0x0A after exact approved bytes is admitted')
    auth=w.read_json(w.safe_path(root,goal['authorization_pin']['path']))
    if (auth.get('source_thread_id')!=goal['human_authorization']['source_thread_id']
            or auth.get('message',{}).get('id')!=goal['human_authorization']['message_id']):
        raise w.WorkflowError('original human source differs')
    policies=[p for p in w.read_jsonl(Path(root)/w.POLICY_DECISIONS)
              if p.get('decision_id')==item['original_policy_decision_id']]
    policy_expected={k:action[k] for k in ('task_id','action_id','scope','payload_sha256',
                                           'target_department','target_thread_id')}
    if (len(policies)!=1 or policies[0].get('status')!='allow'
            or policies[0].get('department')!='operations-assistant'
            or any(policies[0].get(k)!=v for k,v in policy_expected.items())):
        raise w.WorkflowError('original approved 3014-byte policy required')
    source=_collaboration_native(root,item['actual_native_invocation'])
    if any(source.get('thread',{}).get(k)!=fixed.get(v) for k,v in
           {'id':'task_id','title':'title','cwd':'cwd'}.items()):
        raise w.WorkflowError('original fixed sender differs')
    calls=[(t,c) for t in source.get('turns',[]) for c in t.get('items',[])
           if c.get('id')==item.get('source_call_id') and c.get('type')=='mcpToolCall'
           and c.get('server')=='codex_app' and c.get('tool')=='send_message_to_thread']
    if len(calls)!=1:raise w.WorkflowError('one original native send invocation required')
    turn,call=calls[0]
    try:prompt=actual_bytes.decode('utf-8')
    except UnicodeError as exc:raise w.WorkflowError('actual UTF-8 prompt required') from exc
    sent=_collaboration_native(root,item['actual_native_send'])
    ack=_collaboration_native(root,item['actual_native_ack'])
    ack_turn=[t for t in ack.get('turns',[]) if t.get('id')==item.get('ack_turn_id')]
    messages=[m for t in ack_turn for m in t.get('items',[])
              if m.get('id')==item.get('ack_message_id') and m.get('type')=='agentMessage'
              and isinstance(m.get('text'),str) and m['text'].strip()]
    if (not _selected_native_valid(call, statuses=('completed',))
            or not _selected_native_valid(turn, statuses=('inProgress','completed'))
            or call.get('arguments',{}).get('threadId')!=target['thread_id']
            or call.get('arguments',{}).get('prompt')!=prompt or sent.get('threadId')!=target['thread_id']
            or any(ack.get('thread',{}).get(k)!=target.get(v) for k,v in
                   {'id':'thread_id','title':'title','cwd':'cwd'}.items())
            or len(ack_turn)!=1 or not _selected_native_valid(ack_turn[0], statuses=('inProgress','completed'))
            or len(messages)!=1 or not _selected_native_valid(messages[0])
            or messages[0].get('phase') not in {'commentary','final_answer'}
            or not _exact_task_reference(messages[0]['text'],task)
            or type(turn.get('startedAt')) not in {int,float}
            or type(ack_turn[0].get('startedAt')) not in {int,float}
            or turn['startedAt']>ack_turn[0]['startedAt']
            or w._parse_observed_at(policies[0].get('checked_at')).timestamp()>ack_turn[0]['startedAt']):
        raise w.WorkflowError('successful original native send and causal nonempty ACK required')
    records=goal.get('collaboration_records',[])
    if item['original_collaboration_record'] not in records or len([p for p in records if p==item['original_collaboration_record']])!=1:
        raise w.WorkflowError('original sent collaboration record must remain unchanged')
    prior=w.read_json(w.safe_path(root,item['original_collaboration_record']['path']))
    if (prior.get('status')!='sent' or prior.get('action_id')!=action_id
            or prior.get('actual_consumed_payload')!=actual
            or prior.get('payload_sha256')!=approved['sha256']
            or prior.get('policy_decision_id')!=policies[0]['decision_id']
            or prior.get('actual_native_invocation')!=item['actual_native_invocation']
            or prior.get('actual_native_transport')!=item['actual_native_send']
            or prior.get('message_ref')!=item['source_call_id']):
        raise w.WorkflowError('original sent record differs from LF source')
    key=w.sha256_value([task,action_id,approved,actual,item['source_call_id'],
                        item['original_collaboration_record']])
    rows=[r for r in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS)
          if r.get('task_id')==task and r.get('details',{}).get('approved_dispatch_lf_reconciliation_key')==key]
    if require_record:
        if len(rows)!=1:
            raise w.WorkflowError('one actual committed immutable LF reconciliation required')
        pin=rows[0]['details'].get('approved_dispatch_lf_reconciliation',{})
        if (not isinstance(pin,dict) or w.file_digest(root,pin.get('path',''))!=pin
                or w.read_json(w.safe_path(root,pin['path']))!=item):
            raise w.WorkflowError('committed LF reconciliation source changed')
    return snapshot,{'recovery_key':key,'source_turn_id':turn['id'],
                     'ack_turn_id':ack_turn[0]['id'],'ack_message_id':messages[0]['id'],
                     'original_policy_decision_id':policies[0]['decision_id'],
                     'approved_payload':approved,'actual_payload':actual,
                     'recovery_event_id':rows[0]['event_id'] if rows else None,
                     'transport_replayed':False,'old_policy_reissued':False,
                     'external_permission_issued':False}


OLDHOUSE_TECHNICAL_TASK='fc-20261017-next12-old-house-development-handoff-v1'
OLDHOUSE_TECHNICAL_ACTION='assign-same-task-technical-review:'+OLDHOUSE_TECHNICAL_TASK
OLDHOUSE_TECHNICAL_SCOPE='project:flashcast:next12-old-house-development-handoff:v1'
OLDHOUSE_TECHNICAL_MESSAGE={
    'path':'drafts/system-development/fc-20261017-approved-collaboration-source-adapter-repair-v1/source-candidate-v2/oldhouse-A2-same-task-technical-responsibility-message.txt',
    'sha256':'f4dfd96e4fdb96acec84de95fe63927f60e7c8b1b0487e8e6c7d82a931fe9173','size':1106}
OLDHOUSE_TECHNICAL_APPENDIX={
    'path':'logs/handoffs/2026-10-17-assistant1-internal-followthrough-v1/a2-technical-handoff/same-task-A2-technical-responsibility-appendix-PREPARED.json',
    'sha256':'635fe0eb6f2ca40b816776f27856a394798d113d2b43e523d631d04e7313efec','size':2657}
OLDHOUSE_TECHNICAL_INPUT={
    'path':'logs/handoffs/2026-10-17-assistant1-internal-followthrough-v1/a2-technical-handoff/old-house-six-block-twelve-ID-technical-input-PREPARED.json',
    'sha256':'eedf8525df01ca2da479b0994305fd28453a753507e09f0abc1bb5ddba12f6d2','size':24098}
OLDHOUSE_ORIGINAL_RESULT={
    'task_id':OLDHOUSE_TECHNICAL_TASK,'sender_department':'designated-development',
    'candidate_version':'old-house-six-block-local-v1-20261017',
    'result_sha256':'5d8c0404d8066c0690f09fef1c9a041fcc77e4d2e7e22c977df86597f2d49eee'}
OLDHOUSE_TECHNICAL_QUEUE_ONCE_PATH = (
    'logs/handoffs/2026-10-17-assistant1-internal-followthrough-v1/'
    'a2-technical-handoff/oldhouse-technical-queue-once.json')


def oldhouse_technical_preflight(root, request, *, allow_recorded=False):
    """One same-task technical responsibility; the original A1 owner stays put."""
    from goal_delivery_runtime import restore_goal, collaboration_result_source
    if request.get('action_id')!=OLDHOUSE_TECHNICAL_ACTION:
        return None
    if request.get('task_id')!=OLDHOUSE_TECHNICAL_TASK:
        raise w.WorkflowError('old-house technical action belongs only to its original task')
    required={'action_class':'thread_message','scope':OLDHOUSE_TECHNICAL_SCOPE,
              'sender_department':'operations','target_department':'operations-assistant-2',
              'payload_sha256':OLDHOUSE_TECHNICAL_MESSAGE['sha256']}
    if any(request.get(k)!=v for k,v in required.items()):
        raise w.WorkflowError('exact old-house same-task technical action required')
    registry=w.department_registry(root)
    source=registry['operations']['chat_binding'];target=registry['operations-assistant-2']['chat_binding']
    fixed={'source_project_id':source['project_id'],'target_project_id':target['project_id'],
           'target_thread_id':target['task_id'],'target_thread_title':target['title'],
           'target_cwd':target['cwd'],'target_sidebar_section_id':target['sidebar_section_id']}
    if any(request.get(k)!=v for k,v in fixed.items()):
        raise w.WorkflowError('current exact operations-to-A2 fixed binding required')
    if not allow_recorded and not w._chat_binding_healthy(target,verification_ttl_hours=26):
        raise w.WorkflowError('current healthy fixed A2 technical target required')
    snapshot=restore_goal(root,w.read_json(w.snapshot_path(root,OLDHOUSE_TECHNICAL_TASK)))
    goal=snapshot.get('goal_delivery',{})
    contract=snapshot.get('goal_contract')
    if (snapshot.get('task_id')!=OLDHOUSE_TECHNICAL_TASK
            or goal.get('responsible_assistant')!='operations-assistant'
            or goal.get('primary_owner')!='operations'
            or goal.get('acceptance_capability')!='seo_geo'
            or goal.get('authorized_scope')!=[OLDHOUSE_TECHNICAL_SCOPE]
            or goal.get('producer_departments')!=['operations']
            or not isinstance(contract,dict) or w.validate_workflow_events(root,OLDHOUSE_TECHNICAL_TASK)
            or w._validate_receipt_chain(root,OLDHOUSE_TECHNICAL_TASK)[1]):
        raise w.WorkflowError('unchanged original old-house contract and chains required')
    for pin in (contract,goal['authorization_pin'],OLDHOUSE_TECHNICAL_MESSAGE,
                OLDHOUSE_TECHNICAL_APPENDIX,OLDHOUSE_TECHNICAL_INPUT):
        if w.file_digest(root,pin['path'])!=pin:raise w.WorkflowError('old-house exact frozen source changed')
    appendix=w.read_json(w.safe_path(root,OLDHOUSE_TECHNICAL_APPENDIX['path']))
    if (appendix.get('task_id')!=OLDHOUSE_TECHNICAL_TASK
            or appendix.get('current_original_contract')!=contract
            or appendix.get('exact_input')!=OLDHOUSE_TECHNICAL_INPUT
            or appendix.get('current_original_goal_responsible_assistant')!='operations-assistant'
            or appendix.get('requested_original_local_code_review_responsibility')!='operations-assistant-2'
            or appendix.get('same_existing_result_only')!=OLDHOUSE_ORIGINAL_RESULT):
        raise w.WorkflowError('same-task technical appendix cannot replace original goal')
    source_result=collaboration_result_source(root,OLDHOUSE_ORIGINAL_RESULT)
    if not source_result or source_result.get('candidate_version')!=OLDHOUSE_ORIGINAL_RESULT['candidate_version']:
        raise w.WorkflowError('original proven developer result required')
    rows=w._result_handoff_rows(root,OLDHOUSE_TECHNICAL_TASK)
    exact=[r for r in rows if all(r.get(k)==v for k,v in OLDHOUSE_ORIGINAL_RESULT.items())]
    decisions=[r for r in exact if r.get('event')=='controller_decision']
    if (len([r for r in exact if r.get('event')=='controller_received'
             and r.get('coordinator_role')=='operations-assistant'])!=1
            or len(decisions)!=1 or decisions[0].get('coordinator_role')!='operations-assistant'
            or decisions[0].get('decision')!='send_qa'):
        raise w.WorkflowError('original A1 actual result intake and technical route decision required')
    old=[e for e in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS)
         if e.get('task_id')==OLDHOUSE_TECHNICAL_TASK and
         e.get('details',{}).get('same_task_technical_responsibility_source')]
    if old and not allow_recorded:
        raise w.WorkflowError('same-task technical responsibility already delivered; no resend')
    if not allow_recorded and any(p.get('task_id')==OLDHOUSE_TECHNICAL_TASK
            and p.get('action_id')==OLDHOUSE_TECHNICAL_ACTION and p.get('status')=='allow'
            for p in w.read_jsonl(Path(root)/w.POLICY_DECISIONS)):
        raise w.WorkflowError('same-task technical route already prepared; read actual effect before retry')
    return {'task_id':OLDHOUSE_TECHNICAL_TASK,'action_id':OLDHOUSE_TECHNICAL_ACTION,
            'scope':OLDHOUSE_TECHNICAL_SCOPE,'target_department':'operations-assistant-2',
            'original_assistant':'operations-assistant','original_result':OLDHOUSE_ORIGINAL_RESULT,
            'appendix':OLDHOUSE_TECHNICAL_APPENDIX,'input':OLDHOUSE_TECHNICAL_INPUT,
            'payload':OLDHOUSE_TECHNICAL_MESSAGE,'external_permission_issued':False}


def queue_oldhouse_technical(root, request_path, prepared_path, directory):
    """One auditable normal queue call from an existing exact allowed preparation.

    This is an operations execution entry.  Reading an old queue is separate:
    no consumer invokes this function and no queue result implies recipient ACK.
    """
    with w.workflow_lock(root):
        return _queue_oldhouse_technical_locked(root,request_path,prepared_path,directory)


def _queue_oldhouse_technical_locked(root, request_path, prepared_path, directory):
    """Reserve one original effect before enqueue, regardless of output directory."""
    import os
    from department_event_dispatcher import OfficialQueueTransport
    request_pin=w.file_digest(root,request_path)
    prepared_pin=w.file_digest(root,prepared_path)
    request=_strict_queue_document(root,request_pin)
    prepared=_strict_queue_document(root,prepared_pin)
    expected=oldhouse_technical_preflight(root,request,allow_recorded=True)
    source=w.department_registry(root)['operations']['chat_binding']
    target=w.department_registry(root)['operations-assistant-2']['chat_binding']
    if (not expected or request.get('delivery_mode')!='official_native_queue'
            or request.get('authorization_changes')!=[]
            or request.get('payload')!=OLDHOUSE_TECHNICAL_MESSAGE
            or request.get('payload_sha256')!=OLDHOUSE_TECHNICAL_MESSAGE['sha256']
            or any(request.get(k)!=v for k,v in
                   {'source_project_id':source['project_id'],'target_project_id':target['project_id'],
                    'target_thread_id':target['task_id'],'target_thread_title':target['title'],
                    'target_cwd':target['cwd'],'target_sidebar_section_id':target['sidebar_section_id']}.items())
            or not isinstance(prepared.get('policy_decision'),dict)
            or w.file_digest(root,OLDHOUSE_TECHNICAL_MESSAGE['path'])!=OLDHOUSE_TECHNICAL_MESSAGE):
        raise w.WorkflowError('one exact old-house official queue preparation required')
    policy_id=prepared['policy_decision'].get('decision_id')
    policies=[p for p in w.read_jsonl(Path(root)/w.POLICY_DECISIONS)
              if p.get('decision_id')==policy_id]
    if (len(policies)!=1 or not _oldhouse_prepared_valid(prepared,policies[0])
            or any(policies[0].get(k)!=v for k,v in
            {'status':'allow','routing_status':'routing_allowed','department':'operations',
             'task_id':OLDHOUSE_TECHNICAL_TASK,'action_id':OLDHOUSE_TECHNICAL_ACTION,
             'scope':OLDHOUSE_TECHNICAL_SCOPE,'target_department':'operations-assistant-2',
             'target_thread_id':target['task_id'],'payload_sha256':OLDHOUSE_TECHNICAL_MESSAGE['sha256'],
             'source_project_id':source['project_id'],'target_project_id':target['project_id'],
             'target_thread_title':target['title'],'target_cwd':target['cwd'],
             'target_sidebar_section_id':target['sidebar_section_id']}.items())):
        raise w.WorkflowError('actual allowed old-house queue policy required')
    queue_dir=Path(directory)
    if (queue_dir.is_absolute() or '..' in queue_dir.parts or queue_dir.parts[:2]!=('logs','handoffs')):
        raise w.WorkflowError('project-owned old-house queue directory required')
    actual_dir=w.safe_path(root,str(queue_dir))
    if (actual_dir.is_symlink() or os.path.lexists(actual_dir/'native-queue-intent.json')
            or os.path.lexists(actual_dir/'native-queue-result.json')):
        raise w.WorkflowError('existing official queue attempt must be recovered, not repeated')
    once_rel=Path(OLDHOUSE_TECHNICAL_QUEUE_ONCE_PATH)
    once_raw=Path(root)/once_rel
    if (once_rel.is_absolute() or '..' in once_rel.parts
            or any(path.is_symlink() for path in (once_raw,*once_raw.parents)
                   if path != Path(root).parent)):
        raise w.WorkflowError('project-owned non-symlink original queue reservation required')
    once_path=w.safe_path(root,str(once_rel))
    identity={'task_id':OLDHOUSE_TECHNICAL_TASK,'action_id':OLDHOUSE_TECHNICAL_ACTION,
              'scope':OLDHOUSE_TECHNICAL_SCOPE,'request':request_pin,
              'prepared':prepared_pin,'policy_decision_id':policy_id,
              'payload':OLDHOUSE_TECHNICAL_MESSAGE,'target_thread_id':target['task_id']}
    if os.path.lexists(once_path):
        try:
            prior=json.loads(w.validation_bytes(once_path),object_pairs_hook=_queue_unique_fields)
        except (ValueError,TypeError) as error:
            raise w.WorkflowError('existing original queue attempt requires manual recovery') from error
        if not isinstance(prior,dict) or prior.get('identity')!=identity:
            raise w.WorkflowError('different original queue attempt already reserved; no resend')
        raise w.WorkflowError('original queue attempt already reserved at '
                              +str(prior.get('directory','unknown'))+'; recover its effect, no resend')
    actual_dir.mkdir(parents=True,exist_ok=True)
    if os.path.lexists(actual_dir/'native-queue-intent.json') or os.path.lexists(actual_dir/'native-queue-result.json'):
        raise w.WorkflowError('existing official queue effect requires recovery')
    body=w.safe_path(root,OLDHOUSE_TECHNICAL_MESSAGE['path']).read_bytes().decode('utf-8')
    reservation={'schema':'oldhouse-technical-original-queue-once/v1','identity':identity,
                 'directory':str(queue_dir),'state':'reserved','created_at':w.utc_timestamp(),
                 'queue_acceptance_is_delivery':False,'recipient_ACK_claimed':False}
    once_path.parent.mkdir(parents=True,exist_ok=True)
    reserved_bytes=(json.dumps(reservation,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
    try:
        fd=os.open(once_path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    except FileExistsError as error:
        raise w.WorkflowError('original queue attempt reserved concurrently; no resend') from error
    with os.fdopen(fd,'wb') as stream:
        stream.write(reserved_bytes)
        stream.flush()
        os.fsync(stream.fileno())
    def update_reserved_once():
        if once_path.is_symlink() or once_path.read_bytes()!=reserved_bytes:
            raise w.WorkflowError('original queue reservation changed; preserve effect for recovery')
        w.atomic_write_json(once_path,reservation)
    try:
        result=OfficialQueueTransport(root,None).enqueue({
            'thread_id':target['task_id'],'message':body,'directory':actual_dir,
            'payload_sha256':OLDHOUSE_TECHNICAL_MESSAGE['sha256'],
            'policy_decision_id':policy_id})
    except Exception:
        reservation['state']='uncertain'
        reservation['updated_at']=w.utc_timestamp()
        for name in ('intent','result'):
            path=actual_dir/('native-queue-'+name+'.json')
            if path.is_file():reservation['actual_queue_'+name]=w.file_digest(root,str(path.relative_to(root)))
        update_reserved_once()
        raise
    reservation.update(state='accepted',updated_at=w.utc_timestamp(),
                       native_message_id=result['message_id'],
                       actual_queue_intent=w.file_digest(root,str((actual_dir/'native-queue-intent.json').relative_to(root))),
                       actual_queue_result=w.file_digest(root,str((actual_dir/'native-queue-result.json').relative_to(root))))
    update_reserved_once()
    return {'message_id':result['message_id'],'thread_id':target['task_id'],
            'policy_decision_id':policy_id,'payload_sha256':OLDHOUSE_TECHNICAL_MESSAGE['sha256']}


def _oldhouse_exact_queue_command(command, item, queue_dir):
    """Only the fixed CLI actually consumes both preparation files and queues."""
    try:
        parts=shlex.split(command)
        if len(parts)==3 and parts[:2] in (['/bin/zsh','-lc'],['zsh','-lc']):
            parts=shlex.split(parts[2])
    except ValueError:
        return False
    return (len(parts)==10 and Path(parts[0]).name in {'python3','python3.11','python3.12'}
            and parts[1:5]==['-B','tools/goal_source_recovery.py','queue-oldhouse-technical','--request']
            and parts[5:]==[item['original_prepare_request']['path'],'--prepared',
                            item['original_prepare_result']['path'],'--directory',queue_dir])


def _oldhouse_prepared_valid(prepared, policy):
    return (prepared.get('status')=='ready_to_queue'
            and prepared.get('payload')==OLDHOUSE_TECHNICAL_MESSAGE
            and prepared.get('policy_decision')==policy
            and isinstance(prepared.get('authorization_precheck'),dict)
            and prepared['authorization_precheck'].get('status')=='within_original_authorization'
            and prepared.get('delivery_mode')=='official_native_queue'
            and prepared.get('ordinary_send_allowed') is False
            and prepared.get('message_sent') is False
            and prepared.get('external_permission_issued') is False)


def _oldhouse_queue_effect(root,item,sender,target,body,sent_turn,call,policy):
    """An official queue becomes evidence only with its exact later user/ACK turn."""
    import datetime as dt
    names=('original_prepare_request','original_prepare_result','actual_queue_intent','actual_queue_result')
    if any(not isinstance(item.get(name),dict) for name in names):
        raise w.WorkflowError('four real official queue source pins required')
    request,prepared,intent,result=(_strict_queue_document(root,item[name]) for name in names)
    fields={'task_id':OLDHOUSE_TECHNICAL_TASK,'action_id':OLDHOUSE_TECHNICAL_ACTION,
            'scope':OLDHOUSE_TECHNICAL_SCOPE,'sender_department':'operations',
            'target_department':'operations-assistant-2','payload':OLDHOUSE_TECHNICAL_MESSAGE,
            'payload_sha256':OLDHOUSE_TECHNICAL_MESSAGE['sha256'],
            'source_project_id':sender['project_id'],'target_project_id':target['project_id'],
            'target_thread_id':target['task_id'],'target_thread_title':target['title'],
            'target_cwd':target['cwd'],'target_sidebar_section_id':target['sidebar_section_id']}
    expected_transport={'thread_id':target['task_id'],
                        'payload_sha256':OLDHOUSE_TECHNICAL_MESSAGE['sha256'],
                        'policy_decision_id':policy.get('decision_id'),
                        'transport':'official_codex_queue','intake_claimed':False}
    match=re.fullmatch(r'Queued message ([0-9a-f-]{36}) for thread ([0-9a-f-]{36})\.\s*',
                       result.get('stdout',''))
    command=call.get('command','');queue_dir=str(Path(item['actual_queue_result']['path']).parent)
    try:
        command_result=json.loads(call.get('aggregatedOutput',''),
            object_pairs_hook=lambda pairs: _queue_unique_fields(pairs))
    except (ValueError,TypeError):
        command_result={}
    start=w._parse_observed_at(result.get('started_at'))
    finish=w._parse_observed_at(result.get('finished_at'))
    if (any(request.get(k)!=v for k,v in fields.items())
            or request.get('action_class')!='thread_message'
            or request.get('delivery_mode')!='official_native_queue'
            or request.get('authorization_changes')!=[]
            or not _oldhouse_prepared_valid(prepared,policy)
            or any(intent.get(k)!=v or result.get(k)!=v for k,v in expected_transport.items())
            or result.get('started_at')!=intent.get('started_at')
            or type(result.get('exit_code')) is not int or result.get('exit_code')!=0
            or result.get('stderr')!=''
            or not match or match[1]!=item.get('queue_message_id') or match[2]!=target['task_id']
            or command_result!={'message_id':match[1],'thread_id':target['task_id'],
                                'policy_decision_id':policy.get('decision_id'),
                                'payload_sha256':OLDHOUSE_TECHNICAL_MESSAGE['sha256']}
            or type(call.get('exitCode')) is not int or call.get('exitCode')!=0
            or call.get('cwd')!=sender['cwd']
            or not _oldhouse_exact_queue_command(command,item,queue_dir)
            or start is None or finish is None or
            type(sent_turn.get('startedAt')) not in {int,float} or
            type(sent_turn.get('completedAt')) not in {int,float} or
            not sent_turn['startedAt']<=start.timestamp()<=finish.timestamp()<=sent_turn['completedAt']+1
            or not w._parse_observed_at(policy.get('checked_at'))
            or w._parse_observed_at(policy['checked_at'])>start):
        raise w.WorkflowError('exact allowed old-house official queue invocation required')
    return start.timestamp()


def oldhouse_technical_source(root, item, *, require_record=True):
    """Read a future genuine operations send and A2 ACK; never create either."""
    from goal_delivery_runtime import _collaboration_native
    if item.get('schema')!='same-task-technical-responsibility-source/v1':
        raise w.WorkflowError('known same-task technical source format required')
    registry=w.department_registry(root)
    sender=registry['operations']['chat_binding'];target=registry['operations-assistant-2']['chat_binding']
    request={**item,'sender_department':'operations','target_department':'operations-assistant-2',
             'action_class':'thread_message','payload_sha256':OLDHOUSE_TECHNICAL_MESSAGE['sha256'],
             'source_project_id':sender['project_id'],'target_project_id':target['project_id'],
             'target_thread_id':target['task_id'],'target_thread_title':target['title'],
             'target_cwd':target['cwd'],'target_sidebar_section_id':target['sidebar_section_id']}
    source=oldhouse_technical_preflight(root,request,allow_recorded=True)
    if (item.get('task_id')!=OLDHOUSE_TECHNICAL_TASK
            or item.get('action_id')!=OLDHOUSE_TECHNICAL_ACTION
            or item.get('scope')!=OLDHOUSE_TECHNICAL_SCOPE
            or item.get('payload')!=OLDHOUSE_TECHNICAL_MESSAGE
            or item.get('appendix')!=OLDHOUSE_TECHNICAL_APPENDIX
            or item.get('technical_input')!=OLDHOUSE_TECHNICAL_INPUT
            or item.get('original_result')!=OLDHOUSE_ORIGINAL_RESULT):
        raise w.WorkflowError('future technical source must bind original task and frozen exact packet')
    queue_mode=item.get('delivery_mode')=='official_native_queue'
    if item.get('delivery_mode') not in (None,'mcp_direct_send','official_native_queue'):
        raise w.WorkflowError('known actual old-house transport required')
    source_names=('actual_native_invocation','actual_native_recipient') if queue_mode else (
        'actual_native_invocation','actual_native_send','actual_native_recipient')
    pins=[item.get(k) for k in source_names]
    if any(not isinstance(p,dict) or w.file_digest(root,p.get('path',''))!=p for p in pins):
        raise w.WorkflowError('three genuine native technical source pins required')
    page=_collaboration_native(root,item['actual_native_invocation'])
    actual=None if queue_mode else _collaboration_native(root,item['actual_native_send'])
    received=_collaboration_native(root,item['actual_native_recipient'])
    for native,binding in ((page,sender),(received,target)):
        if any(native.get('thread',{}).get(k)!=binding.get(v) for k,v in
               {'id':'task_id','title':'title','cwd':'cwd'}.items()):
            raise w.WorkflowError('same-task native sender or receiver identity differs')
    body=w.safe_path(root,OLDHOUSE_TECHNICAL_MESSAGE['path']).read_bytes().decode('utf-8')
    calls=[(t,c) for t in page.get('turns',[]) for c in t.get('items',[])
           if c.get('id')==item.get('source_call_id') and (
               c.get('type')=='commandExecution' if queue_mode else
               c.get('type')=='mcpToolCall' and c.get('server')=='codex_app'
               and c.get('tool')=='send_message_to_thread')]
    if len(calls)!=1:raise w.WorkflowError('one actual operations send call required')
    sent_turn,call=calls[0]
    selected=[t for t in received.get('turns',[]) if t.get('id')==item.get('recipient_turn_id')]
    if len(selected)!=1:raise w.WorkflowError('one actual A2 receiving turn required')
    turn=selected[0];messages=turn.get('items',[])
    users=[(i,m) for i,m in enumerate(messages) if m.get('id')==item.get('recipient_message_id')
           and m.get('type')=='userMessage']
    acks=[(i,m) for i,m in enumerate(messages) if m.get('id')==item.get('ack_message_id')
          and m.get('type')=='agentMessage' and isinstance(m.get('text'),str) and m['text'].strip()]
    policies=[p for p in w.read_jsonl(Path(root)/w.POLICY_DECISIONS)
              if p.get('decision_id')==item.get('policy_decision_id')]
    expected={'status':'allow','department':'operations','task_id':OLDHOUSE_TECHNICAL_TASK,
              'action_id':OLDHOUSE_TECHNICAL_ACTION,'action_class':'thread_message',
              'scope':OLDHOUSE_TECHNICAL_SCOPE,'target_department':'operations-assistant-2',
              'target_thread_id':target['task_id'],'payload_sha256':OLDHOUSE_TECHNICAL_MESSAGE['sha256'],
              'source_project_id':sender['project_id'],'target_project_id':target['project_id'],
              'target_thread_title':target['title'],'target_cwd':target['cwd'],
              'target_sidebar_section_id':target['sidebar_section_id']}
    exact_user=(len(users)==1 and len(acks)==1 and users[0][1].get('content')==
                [{'type':'text','text':body}] and users[0][0]<acks[0][0]
                and _selected_native_valid(users[0][1]) and _selected_native_valid(acks[0][1])
                and acks[0][1].get('phase') in {'commentary','final_answer'})
    policy_at=w._parse_observed_at(policies[0].get('checked_at')) if len(policies)==1 else None
    if queue_mode:
        transport_at=_oldhouse_queue_effect(root,item,sender,target,body,sent_turn,call,policies[0] if len(policies)==1 else {})
    else:
        transport_at=sent_turn.get('startedAt')
    if (len(policies)!=1 or any(policies[0].get(k)!=v for k,v in expected.items())
            or policies[0].get('routing_status')!='routing_allowed'
            or not _selected_native_valid(call,statuses=('completed',))
            or not _selected_native_valid(sent_turn,statuses=('inProgress','completed'))
            or (not queue_mode and (not _native_container_valid(call.get('result'))
                or call.get('arguments',{}).get('threadId')!=target['task_id']
                or call.get('arguments',{}).get('prompt')!=body
                or call.get('result',{}).get('threadId')!=target['task_id']
                or actual.get('threadId')!=target['task_id']))
            or not _selected_native_valid(turn,statuses=('inProgress','completed'))
            or not exact_user or not _exact_task_reference(acks[0][1]['text'],OLDHOUSE_TECHNICAL_TASK)
            or type(sent_turn.get('startedAt')) not in {int,float}
            or type(turn.get('startedAt')) not in {int,float}
            or sent_turn['startedAt']>turn['startedAt']
            or (queue_mode and turn['startedAt']<w._parse_observed_at(
                w.read_json(w.safe_path(root,item['actual_queue_result']['path'])).get('finished_at')).timestamp())
            or policy_at is None or type(transport_at) not in {int,float}
            or policy_at.timestamp()>transport_at):
        raise w.WorkflowError('actual allowed same-task send and nonempty causal A2 ACK required')
    key=w.sha256_value([OLDHOUSE_TECHNICAL_TASK,OLDHOUSE_TECHNICAL_ACTION,
                        OLDHOUSE_TECHNICAL_MESSAGE,item['source_call_id'],item['recipient_message_id']])
    events=[e for e in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS)
            if e.get('task_id')==OLDHOUSE_TECHNICAL_TASK and
            e.get('details',{}).get('same_task_technical_responsibility_source')]
    if any(e.get('details',{}).get('same_task_technical_responsibility_key')!=key for e in events):
        raise w.WorkflowError('different old-house technical delivery already committed')
    if require_record:
        if len(events)!=1:raise w.WorkflowError('one committed same-task technical source required')
        pin=events[0]['details'].get('same_task_technical_responsibility_source',{})
        if (not isinstance(pin,dict) or w.file_digest(root,pin.get('path',''))!=pin
                or w.read_json(w.safe_path(root,pin['path']))!=item):
            raise w.WorkflowError('committed same-task technical source changed')
    return {'task_id':OLDHOUSE_TECHNICAL_TASK,'original_assistant':'operations-assistant',
            'technical_reviewer':'operations-assistant-2','scope':OLDHOUSE_TECHNICAL_SCOPE,
            'original_result':OLDHOUSE_ORIGINAL_RESULT,'source_key':key,
            'source_event_id':events[0]['event_id'] if events else None,
            'actual_delivery_and_ack':True,'business_owner_transferred':False,
            'technical_QA_passed':False,'production_permission_issued':False}


def record_oldhouse_technical_source(root, input_path):
    pin=w.file_digest(root,input_path)
    item=w.read_json(w.safe_path(root,input_path))
    proof=oldhouse_technical_source(root,item,require_record=False)
    with w.workflow_lock(root):
        proof=oldhouse_technical_source(root,item,require_record=False)
        events=[e for e in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS)
                if e.get('task_id')==OLDHOUSE_TECHNICAL_TASK and
                e.get('details',{}).get('same_task_technical_responsibility_source')]
        if events:
            if (len(events)!=1 or events[0]['details'].get('same_task_technical_responsibility_key')!=proof['source_key']
                    or events[0]['details'].get('same_task_technical_responsibility_source')!=pin):
                raise w.WorkflowError('one immutable real same-task technical source required')
            state='duplicate_ignored'
        else:
            snapshot=w.read_json(w.snapshot_path(root,OLDHOUSE_TECHNICAL_TASK))
            w.append_workflow_event(root,OLDHOUSE_TECHNICAL_TASK,snapshot['current_state'],
                {'same_task_technical_responsibility_key':proof['source_key'],
                 'same_task_technical_responsibility_source':pin,
                 'original_responsible_assistant':'operations-assistant',
                 'technical_reviewer':'operations-assistant-2',
                 'business_owner_transferred':False,'external_permission_issued':False})
            state='recorded'
    return {'result':state,'source':oldhouse_technical_source(root,item),
            'old_message_resent':False,'contract_changed':False,'external_permission_issued':False}


def read_oldhouse_technical_source(root):
    """Normal readback of the one append-only same-task technical handoff."""
    events=[e for e in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS)
            if e.get('task_id')==OLDHOUSE_TECHNICAL_TASK and
            e.get('details',{}).get('same_task_technical_responsibility_source')]
    if not events:return None
    if len(events)!=1 or w.validate_workflow_events(root,OLDHOUSE_TECHNICAL_TASK):
        raise w.WorkflowError('one intact same-task technical handoff event required')
    pin=events[0]['details']['same_task_technical_responsibility_source']
    if w.file_digest(root,pin.get('path',''))!=pin:
        raise w.WorkflowError('same-task technical handoff source changed')
    return oldhouse_technical_source(root,w.read_json(w.safe_path(root,pin['path'])))


@historical_assignment_validator
def validate(root, item, *, require_record=True):
    from goal_delivery_runtime import restore_goal, enabled, _collaboration_native
    from goal_continuity import pin_document
    task = w.validate_task_id(item.get('task_id', ''))
    snapshot = restore_goal(root, w.read_json(w.snapshot_path(root, task)))
    if not enabled(root, snapshot) or item.get('schema') != 'goal-current-assignment/v2':
        raise w.WorkflowError('bound complete goal and existing assignment schema required')
    if w.validate_workflow_events(root,task):
        raise w.WorkflowError('intact original source recovery event chain required')
    if task == 'fc-20261017-original204-two-renderer-development-handoff-v1':
        return approved_dispatch_lf_source(root, snapshot, item, require_record=require_record)
    goal = snapshot['goal_delivery']
    if goal.get('source_mode') != 'owner_direct' or item.get('source_kind') not in {
            'owner_direct_native', 'historical_native_send'}:
        raise w.WorkflowError('original owner-direct source required')
    role = item.get('department')
    if role not in goal['producer_departments'] or item.get('scope') not in goal['authorized_scope']:
        raise w.WorkflowError('recovery must retain original exact producer/scope')
    if item.get('authorization_pin') != goal['authorization_pin']:
        raise w.WorkflowError('recovery original authorization differs')
    human = pin_document(root, goal['authorization_pin'])
    page = _collaboration_native(root, item['actual_native_invocation'])
    sender = item.get('sender_department')
    from department_rotation import historical_registry
    registry = historical_registry(root, item)
    binding = registry.get(sender, {}).get('chat_binding', {})
    if any(page.get('thread', {}).get(k) != binding.get(v) for k, v in
           {'id':'task_id', 'title':'title', 'cwd':'cwd'}.items()):
        raise w.WorkflowError('real fixed source identity required')
    auth = goal['human_authorization']
    if auth['source_thread_id']!=page.get('thread',{}).get('id'):
        raise w.WorkflowError('original human authorization must belong to the real source chat')
    messages = [(t, m) for t in page.get('turns', []) for m in t.get('items', [])
                if m.get('type') == 'userMessage' and m.get('id') == auth['message_id']]
    if len(messages) != 1 or messages[0][1] != human.get('message'):
        raise w.WorkflowError('one original native human authorization required')
    original = item.get('original_task_id')
    if original != (goal.get('original_parent_reference_task_id') or task):
        raise w.WorkflowError('original task reference cannot be rewritten')
    if item['source_kind'] == 'owner_direct_native':
        if role != sender or role != goal['primary_owner']:
            raise w.WorkflowError('owner-direct intake only restores the real primary executor')
        source_id = auth['message_id']
        source_turn = messages[0][0]
    else:
        if sender != goal['primary_owner']:
            raise w.WorkflowError('real original primary collaboration sender required')
        calls = [(t, c) for t in page.get('turns', []) for c in t.get('items', [])
                 if c.get('type') == 'mcpToolCall' and c.get('id') == item.get('source_call_id')
                 and c.get('server') == 'codex_app' and c.get('tool') == 'send_message_to_thread']
        if len(calls) != 1:
            raise w.WorkflowError('one original native invocation required')
        source_turn, call = calls[0]
        target = registry[role]['chat_binding']['task_id']
        payload = item.get('payload', {})
        if w.file_digest(root, payload.get('path','')) != payload:
            raise w.WorkflowError('historical exact message bytes changed')
        body = w.safe_path(root, payload['path']).read_text(encoding='utf-8')
        sent = _collaboration_native(root, item['actual_native_send'])
        if (call.get('status') != 'completed' or call.get('error')
                or call.get('truncated', False) is not False or source_turn.get('error')
                or call.get('arguments', {}).get('threadId') != target
                or call['arguments'].get('prompt') != body or sent.get('threadId') != target
                or not re.search(r'(?<![A-Za-z0-9_-])'+re.escape(original)+r'(?![A-Za-z0-9_-])',body)):
            raise w.WorkflowError('successful exact original transport required')
        source_id = call['id']
    identity = {k:item[k] for k in ('task_id','department','scope','source_kind','original_task_id')}
    identity.update(authorization_pin=goal['authorization_pin'], source_id=source_id)
    key = w.sha256_value(identity)
    rows = [r for r in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS)
            if r.get('task_id') == task and r.get('details',{}).get('native_source_recovery_key') == key]
    if require_record:
        if len(rows) != 1 or rows[0]['details'].get('native_source_recovery') != item:
            raise w.WorkflowError('one committed real source recovery required; no substituted proof')
    return snapshot, {'receipt_id': None, 'receipt_type':'native_source_recovered',
        'actual_source_id':source_id, 'source_turn_id':source_turn.get('id'),
        'source_turn_started_at':source_turn.get('startedAt'),
        'original_task_id':original, 'recovery_key':key,
        'recovery_event_id':rows[0]['event_id'] if rows else None,
        'created_at':rows[0]['created_at'] if rows else None,
        'dispatch_fabricated':False, 'policy_fabricated':False,
        'external_permission_issued':False}


def record(root, input_path):
    from goal_continuity import record_assignment
    pin = w.file_digest(root, input_path)
    item = w.read_json(w.safe_path(root,input_path))
    with w.workflow_lock(root):
        snapshot, proof = validate(root,item,require_record=False)
        if item['task_id'] == 'fc-20261017-original204-two-renderer-development-handoff-v1':
            existing = [r for r in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS)
                        if r.get('task_id') == item['task_id'] and
                        r.get('details',{}).get('approved_dispatch_lf_reconciliation_key') == proof['recovery_key']]
            if existing:
                if len(existing) != 1 or existing[0]['details'].get('approved_dispatch_lf_reconciliation') != pin:
                    raise w.WorkflowError('one immutable approved-dispatch LF reconciliation required')
                state = 'duplicate_ignored'
            else:
                w.append_workflow_event(root,item['task_id'],snapshot['current_state'],
                    {'approved_dispatch_lf_reconciliation_key':proof['recovery_key'],
                     'approved_dispatch_lf_reconciliation':pin,'old_send_replayed':False,
                     'old_policy_reissued':False,'external_permission_issued':False})
                state = 'recorded'
            return {'result':state,'source_reconciliation':validate(root,item)[1],
                    'actual_message_delivered':True,'transport_replayed':False,
                    'historical_task_reopened':False,'external_permission_issued':False}
        rows = [r for r in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS)
                if r.get('task_id') == item['task_id'] and
                r.get('details',{}).get('native_source_recovery_key') == proof['recovery_key']]
        if rows:
            if len(rows) != 1 or rows[0]['details'].get('native_source_recovery') != item:
                raise w.WorkflowError('existing recovery is immutable; retain its original bytes')
        else:
            w.append_workflow_event(root,item['task_id'],snapshot['current_state'],
                {'native_source_recovery_key':proof['recovery_key'],'native_source_recovery':item,
                 'dispatch_fabricated':False,'external_permission_issued':False})
    if item.get('restore_position')=='suspended':
        with w.workflow_lock(root):
            validate(root,item)
            path=Path(root)/'data/department-current-assignment.json'
            current=w.read_json(path)
            stack=current.setdefault('suspended_assignments',{}).setdefault(item['department'],[])
            duplicate=pin in stack
            if not duplicate:
                stack.append(pin);w.atomic_write_json(path,current)
            assignment={'result':'duplicate_ignored' if duplicate else 'recorded',
                        'restore_position':'suspended','actual_message_delivered':True}
    else:
        if item.get('restore_position') not in {None,'current'}:
            raise w.WorkflowError('explicit current or suspended recovery position required')
        assignment = record_assignment(root,item,pin)
    return {**assignment,'source_recovery':validate(root,item)[1],
            'historical_task_reopened':False,'external_permission_issued':False}


def adoption_notice_message(root, request):
    """A frozen factual return to the original producer, never a new task grant."""
    from goal_delivery_runtime import restore_goal
    from result_coordination import _committed_result
    task = w.validate_task_id(request.get('task_id', ''))
    snapshot = restore_goal(root, w.read_json(w.snapshot_path(root, task)))
    goal = snapshot['goal_delivery']
    source = request.get('post_adoption_notice', {})
    if (request.get('sender_department') not in {'operations', goal['responsible_assistant']}
            or request.get('target_department') != goal['primary_owner']
            or request.get('action_class') != 'thread_message'
            or request.get('scope') not in goal['authorized_scope']
            or not isinstance(source, dict)):
        raise w.WorkflowError('same-goal factual return to original producer required')
    pin = source.get('journal', {})
    if not isinstance(pin, dict) or w.file_digest(root, pin.get('path', '')) != pin:
        raise w.WorkflowError('exact actual adoption journal required')
    journal = w.read_json(w.safe_path(root, pin['path']))
    if (journal.get('task_id') != task or journal.get('actor') != goal['responsible_assistant']
            or journal.get('status') != 'complete' or journal.get('direction') != 'forward'
            or type(journal.get('external_writes')) is not int or journal['external_writes'] != 0
            or journal.get('effect_uncertain') is not False or journal.get('permissions_issued') is not False
            or not journal.get('execution_id')):
        raise w.WorkflowError('actual zero-external-write adoption fact required')
    operations = journal.get('source_operations', [])
    if (not isinstance(operations, list) or not 1 <= len(operations) <= 32
            or len({o.get('path') for o in operations if isinstance(o, dict)}) != len(operations)):
        raise w.WorkflowError('bounded actual adopted source operations required')
    for op in operations:
        if (not isinstance(op, dict) or not op.get('path')
                or op.get('write_attempted') is not True or op.get('verified_after') is not True
                or op.get('after_expected') != op.get('after_actual')
                or {k:w.file_digest(root, op['path'])[k] for k in ('sha256','size')} != op.get('after_actual')
                or w.file_digest(root, op.get('backup', {}).get('path', '')) != op.get('backup')
                or {k:op['backup'][k] for k in ('sha256','size')} != op.get('before')):
            raise w.WorkflowError('actual current adopted source and physical backup readback required')
    rows = w._result_handoff_rows(root, task)
    decisions = [r for r in rows if r.get('event') == 'controller_decision'
                 and r.get('record_id') == journal.get('decision_record_id')]
    follows = [r for r in rows if r.get('event') == 'controller_followthrough'
               and r.get('record_id') == source.get('followthrough_record_id')]
    if (len(decisions) != 1 or len(follows) != 1
            or decisions[0].get('decision') != 'continue'
            or any(r.get('coordinator_role') != goal['responsible_assistant'] for r in (decisions[0], follows[0]))
            or decisions[0].get('sender_department') != goal['primary_owner']
            or any(decisions[0].get(k) != follows[0].get(k) for k in
                   ('task_id', 'sender_department', 'candidate_version', 'result_sha256'))
            or decisions[0].get('candidate_version') != journal.get('candidate_version')
            or pin not in follows[0].get('evidence', [])
            or not str(follows[0].get('unblock_condition', '')).startswith(
                'source-adopted:' + journal['execution_id'] + ';')):
        raise w.WorkflowError('exact committed adoption decision and followthrough required')
    for row in (decisions[0], follows[0]):
        _committed_result(root, row)
    expected_id = 'notify-adoption-' + w.sha256_value(
        [task, request['sender_department'], request['target_department'], pin])
    if request.get('action_id') != expected_id:
        raise w.WorkflowError('deterministic original adoption notice identity required')
    return {'task_id': task, 'purpose': 'same_goal_source_adoption_notice',
            'sender_department': request['sender_department'],
            'target_department': goal['primary_owner'], 'scope': request['scope'],
            'source_adoption': pin, 'execution_id': journal['execution_id'],
            'candidate_version': journal['candidate_version'],
            'decision_record_id': decisions[0]['record_id'],
            'followthrough_record_id': follows[0]['record_id'],
            'source_adopted': True, 'business_goal_completed': False,
            'external_permission_issued': False, 'new_assignment_authorized': False,
            'next_action': '读取已采用证据和本部门真实当前／暂停指派，继续已获授权的未完范围；不重做已采用源码，不重复保存或派工。本通知不新增任务、账号、费用或生产权限。'}


def _prepare_adoption_notice(root, request):
    """Reuse approved_actions/event storage for an exact factual callback."""
    from goal_delivery_runtime import restore_goal
    body = adoption_notice_message(root, request)
    expected = (json.dumps(body, ensure_ascii=False, sort_keys=True, indent=2) + '\n').encode('utf-8')
    if w.safe_path(root, request['payload']['path']).read_bytes() != expected:
        raise w.WorkflowError('factual adoption notice cannot contain arbitrary new instructions')
    fields = ('task_id', 'sender_department', 'action_id', 'action_class', 'scope',
              'source_project_id', 'target_project_id', 'target_department', 'target_thread_id',
              'target_thread_title', 'target_cwd', 'target_sidebar_section_id',
              'payload_sha256', 'payload', 'post_adoption_notice')
    action = {k: request[k] for k in fields}
    registry = w.department_registry(root)
    binding = registry[request['target_department']]['chat_binding']
    source_binding = registry[request['sender_department']]['chat_binding']
    if request.get('source_project_id') != source_binding.get('project_id'):
        raise w.WorkflowError('exact original callback sender project required before preparation')
    if any(request.get(k) != binding.get(v) for k,v in
           {'target_thread_id':'task_id','target_thread_title':'title','target_project_id':'project_id',
            'target_cwd':'cwd','target_sidebar_section_id':'sidebar_section_id'}.items()):
        raise w.WorkflowError('exact original producer callback binding required')
    with w.workflow_lock(root):
        # Recheck the committed fact immediately before the existing preparation event.
        if adoption_notice_message(root, request) != body:
            raise w.WorkflowError('adoption callback source changed during preparation')
        snapshot = restore_goal(root, w.read_json(w.snapshot_path(root, request['task_id'])))
        goal = snapshot['goal_delivery']
        # One factual return is owned once across HQ and its responsible assistant.
        # A prepared uncertain call also blocks another sender; it must be recovered,
        # not delivered twice with a different sender-specific action identifier.
        same_fact = [a for a in goal.get('approved_actions', [])
                     if a.get('target_department') == request['target_department']
                     and a.get('post_adoption_notice', {}).get('journal') ==
                         request['post_adoption_notice']['journal']]
        action_ids = {a['action_id'] for a in same_fact}
        sent = [row for row in w.read_jsonl(w.receipts_path(root, request['task_id']))
                if row.get('receipt_type') == 'dispatch_sent' and row.get('action_id') in action_ids
                and row.get('department') == request['target_department']]
        if sent:
            return {'status':'duplicate_ignored','actual_message_sent':True,
                    'actual_receipt_ids':[row['receipt_id'] for row in sent],
                    'historical_notice_count':len(sent),'message_sent':False}
        different_owner = [a for a in same_fact if a.get('action_id') != request['action_id']]
        if different_owner:
            return {'status':'waiting_existing_callback_effect','message_sent':False,
                    'recovery_owner':different_owner[0]['sender_department'],
                    'notification_responsibility_retained':True}
        old = [a for a in goal.get('approved_actions', []) if a.get('action_id') == action['action_id']]
        if old:
            if old != [action]:
                raise w.WorkflowError('original adoption notice already frozen to different bytes')
            return
        snapshot['goal_delivery'] = {**goal, 'approved_actions': goal.get('approved_actions', []) + [action]}
        w.append_workflow_event(root, request['task_id'], snapshot['current_state'],
                                {'goal_delivery': snapshot['goal_delivery'],
                                 'post_adoption_notice_prepared': request['payload'],
                                 'actual_message_sent': False, 'external_permission_issued': False})
        w.atomic_write_json(w.snapshot_path(root, request['task_id']), snapshot)


def _record_original_result_continuation_prepared(root, request, data, policy):
    """Append the verified normal preparation to the existing event journal.

    This records only the finite read/source/ACK command and its actual policy.
    It neither sends the message nor alters an assignment, permit or plan.
    """
    from goal_delivery_runtime import restore_goal
    item = data['intent']
    frozen = {**data, 'action_id': item['action_id'], 'policy_decision_id': policy['decision_id']}
    with w.workflow_lock(root):
        snapshot = restore_goal(root, w.read_json(w.snapshot_path(root, item['task_id'])))
        if (snapshot.get('current_state') in w.TERMINAL_STATES
                or snapshot.get('goal_contract') != item['goal_contract']
                or snapshot['goal_delivery']['authorization_pin'] != item['authorization_pin']
                or any(w.file_digest(root, pin['path']) != pin for pin in
                       (item['goal_contract'], item['authorization_pin'], item['original_plan'], item['original_result'], data['payload']))):
            raise w.WorkflowError('original result continuation changed during normal preparation')
        events = [e for e in w.read_jsonl(Path(root) / w.WORKFLOW_EVENTS)
                  if e.get('task_id') == item['task_id'] and e.get('details', {}).get(
                      'original_result_continuation_prepared', {}).get('action_id') == item['action_id']]
        if events:
            if len(events) != 1 or events[0]['details']['original_result_continuation_prepared'] != frozen:
                raise w.WorkflowError('original continuation action already frozen to different bytes/policy')
            return
        w.append_workflow_event(root, item['task_id'], snapshot['current_state'],
                                {'original_result_continuation_prepared': frozen,
                                 'actual_message_sent': False, 'external_permission_issued': False})


# Request-local source data handoff, never a route/policy/permission result.
_PREPARE_SOURCE = ContextVar('normal_prepare_typed_source_handoff', default=None)
_PREPARE_SOURCE_SEAL = object()
_PREPARE_AFTER_LOCK = 'same-original-PUB-after-receipt-lock-continuation-source/v1'
_PREPARE_MARKER = 'HQ_original_PUB_singlefield_continuation_source'
_PREPARE_KEYS = ('task_id','sender_department','action_id','action_class','scope','source_project_id',
                 'target_project_id','target_department','target_thread_id','target_thread_title',
                 'target_cwd','target_sidebar_section_id','payload_sha256')


def _normal_prepare_sql_scope(root):
    scope = _PREPARE_SOURCE.get()
    if type(scope) is _NormalPrepareSource and scope.root == Path(root).resolve():
        scope.identity(root)
        return scope
    return None


def _normal_prepare_input_bytes(root,path):
    scope=_normal_prepare_sql_scope(root)
    if scope is None:return Path(path).read_bytes()
    logical=Path(path).absolute()
    state=(str(logical.resolve()),logical.exists(),logical.is_symlink())
    old=scope.pin_paths.setdefault(str(logical),state)
    if old!=state:raise w.WorkflowError('normal prepare direct input path changed')
    return scope.validation.bytes(logical)


def _normal_prepare_note_sql(root, kind, arguments, result):
    scope = _normal_prepare_sql_scope(root)
    if scope is not None: scope.note_sql(kind, arguments, result)


class _NormalPrepareSource:
    """Only normal prepare creates/owns this in-memory, exact-generation scope."""
    def __init__(self, seal, root, request, validation, connections, *, mode='prepare'):
        if seal is not _PREPARE_SOURCE_SEAL or validation is not w._VALIDATION_CONTEXT.get():
            raise w.WorkflowError('internal normal prepare source factory required')
        import copy
        if mode not in {'prepare','queue'}:raise w.WorkflowError('internal source scope mode required')
        self.mode=mode; self.queue_bound=False
        self.seal=seal; self.logical_root=Path(root).absolute(); self.root=Path(root).resolve()
        stat=self.root.stat(); self.root_inode=(stat.st_dev,stat.st_ino)
        self.validation=validation; self.request=request; self.request_hash=w.sha256_value(request)
        self.marker=copy.deepcopy(request[_PREPARE_MARKER]); self.connections=connections
        self.generation=0; self.verified=None; self.building=False; self.finalizing=False
        self.sql_reads={}; self.final_checked=False; self.closed=False; self.owned_write=False
        self.snapshot_file=w.snapshot_path(self.root,request['task_id'])
        from goal_delivery_runtime import restore_goal
        self.snapshot=restore_goal(self.root,w.read_json(self.snapshot_file))
        self.snapshot_hash=w.sha256_value(self.snapshot)
        self.pin_paths={}
        self._pin_paths(request)

    def __copy__(self): raise TypeError('normal prepare scope cannot be copied')
    def __deepcopy__(self,memo): raise TypeError('normal prepare scope cannot be copied')
    def __reduce__(self): raise TypeError('normal prepare scope cannot be serialized')

    @staticmethod
    def _version(path):
        stat=path.stat()
        return (stat.st_dev,stat.st_ino,stat.st_size,stat.st_mtime_ns,stat.st_ctime_ns)

    def _pin_paths(self, value):
        if isinstance(value,dict):
            if set(value)=={'path','sha256','size'} and isinstance(value['path'],str):
                logical=Path(value['path'])
                if not logical.is_absolute(): logical=self.root/logical
                key=str(logical.absolute())
                state=(str(logical.resolve()),logical.exists(),logical.is_symlink())
                old=self.pin_paths.setdefault(key,state)
                if old!=state: raise w.WorkflowError('normal prepare pinned path changed')
            for child in value.values(): self._pin_paths(child)
        elif isinstance(value,(list,tuple)):
            for child in value: self._pin_paths(child)

    def identity(self,root):
        if (self.closed or self.seal is not _PREPARE_SOURCE_SEAL or _PREPARE_SOURCE.get() is not self
            or w._VALIDATION_CONTEXT.get() is not self.validation
            or self.logical_root.resolve()!=self.root or Path(root).resolve()!=self.root
            or (self.root.stat().st_dev,self.root.stat().st_ino)!=self.root_inode
            or w.sha256_value(self.request)!=self.request_hash
            or w.sha256_value(self.snapshot)!=self.snapshot_hash):
            raise w.WorkflowError('same normal prepare request/context/root required')
        if self.verified is not None and w.sha256_value(self.verified)!=self.source_hash:
            raise w.WorkflowError('normal prepare private source context changed')
        for logical,state in self.pin_paths.items():
            path=Path(logical)
            if (str(path.resolve()),path.exists(),path.is_symlink())!=state:
                raise w.WorkflowError('normal prepare source path identity changed')

    def sql_check(self):
        for logical,path,inode,connection,version,wal_identity in self.connections:
            if logical.is_symlink() or logical.resolve()!=path:
                raise w.WorkflowError('normal prepare SQL path identity changed')
            stat=path.stat(); wal=Path(str(path)+'-wal')
            if wal.is_symlink(): raise w.WorkflowError('normal prepare SQL WAL symlink changed')
            ws=wal.stat() if wal.exists() else None
            wi=(ws.st_dev,ws.st_ino) if ws else None
            if ((stat.st_dev,stat.st_ino,stat.st_ctime_ns)!=inode or wi!=wal_identity
                or connection.execute('PRAGMA data_version').fetchone()[0]!=version):
                raise w.WorkflowError('normal prepare SQL generation changed')

    def inputs(self,root):
        self.identity(root); self.sql_check()
        for name,entry in self.validation.files.items():
            if self._version(Path(name))!=entry['version']:
                raise w.WorkflowError('normal prepare dependency identity changed: '+name)
        self.validation.recheck()  # actual file bytes and original Git rereads

    def note_sql(self,kind,arguments,result):
        if self.building and not self.finalizing:
            import copy
            key=(kind,w.sha256_value(arguments)); item=(copy.deepcopy(arguments),copy.deepcopy(result))
            if key in self.sql_reads and self.sql_reads[key]!=item:
                raise w.WorkflowError('normal prepare SQL reader changed within source validation')
            self.sql_reads[key]=item

    def source(self,root,snapshot,requested,reader):
        if requested.get('action_id')!=self.request['action_id']:
            return reader()
        self.identity(root)
        from hq_bounded_web_admission import IDENTITY_KEYS,FRESH_KEYS
        allowed=set(IDENTITY_KEYS)|FRESH_KEYS|{_PREPARE_MARKER}
        if (not set(_PREPARE_KEYS)<=set(requested) or not set(requested)<=allowed
            or any(value!=self.request.get(key) for key,value in requested.items())
            or w.sha256_value(snapshot)!=self.snapshot_hash):
            raise w.WorkflowError('exact complete normal prepare source projection/generation required')
        if self.building: raise w.WorkflowError('recursive same-source normal prepare validation')
        self.sql_check()
        if self.verified is None:
            self.building=True
            try: verified=reader()
            finally: self.building=False
            if (not isinstance(verified,dict) or verified.get('continuation_input',{}).get('schema')!=_PREPARE_AFTER_LOCK
                or verified.get('registration')!=self.marker or not verified.get('event_id')
                or verified.get('action',{}).get('action_id')!=self.request['action_id']
                or any(value!=verified['action'].get(key) for key,value in requested.items() if key not in FRESH_KEYS)
                or w.sha256_value(verified.get('snapshot'))!=self.snapshot_hash):
                raise w.WorkflowError('fully validated exact after-lock source context required')
            import copy
            self.verified=copy.deepcopy(verified); self.source_hash=w.sha256_value(self.verified)
            self._pin_paths(self.verified)
            self.inputs(root)
        if w.sha256_value(self.verified)!=self.source_hash:
            raise w.WorkflowError('normal prepare source handoff mutated')
        # Clone source inputs. No caller can mutate the private registered source.
        import copy
        return copy.deepcopy(self.verified)

    def observation(self,root,snapshot,live_pin,write):
        if self.mode!='prepare' or self.verified is None or self.generation!=0 or self.owned_write:
            raise w.WorkflowError('one normal prepare observation generation required')
        self.inputs(root)
        if w.sha256_value(snapshot)!=self.snapshot_hash:
            raise w.WorkflowError('normal prepare observation base generation changed')
        import copy,hashlib
        previous=copy.deepcopy(snapshot); expected=copy.deepcopy(snapshot)
        goal=expected['goal_delivery'];goal['current_route_observations']={**goal.get('current_route_observations',{}),self.request['action_id']:live_pin}
        event_path=self.root/w.WORKFLOW_EVENTS
        before_event=w.validation_bytes(event_path); before_snapshot=w.validation_bytes(self.snapshot_file)
        entries={str(path.resolve()):copy.deepcopy(self.validation.files[str(path.resolve())]) for path in (event_path,self.snapshot_file)}
        event,actual_snapshot=write()
        expected_details={'goal_delivery':expected['goal_delivery'],'actual_route_observation':live_pin,'external_permission_issued':False}
        if (actual_snapshot!=expected or event.get('task_id')!=self.request['task_id']
            or event.get('state')!=previous['current_state'] or event.get('details')!=expected_details
            or event.get('event_hash')!=w.sha256_value({k:v for k,v in event.items() if k!='event_hash'})):
            raise w.WorkflowError('normal observation produced an unexpected delta')
        expected_raw={str(event_path.resolve()):before_event+(json.dumps(event,ensure_ascii=False,sort_keys=True)+'\n').encode(),
                      str(self.snapshot_file.resolve()):(json.dumps(expected,ensure_ascii=False,indent=2)+'\n').encode()}
        # Compare exact old-prefix plus this exact returned event, never MAX(seq).
        prior_rows=[json.loads(line) for line in before_event.splitlines() if line.strip()]
        if event.get('previous_event_hash')!=(prior_rows[-1].get('event_hash','') if prior_rows else ''):
            raise w.WorkflowError('normal observation event predecessor changed')
        for name,entry in entries.items():
            if self.validation.files.get(name)!=entry or Path(name).read_bytes()!=expected_raw[name]:
                raise w.WorkflowError('concurrent change during exact normal observation')
        # Only these two known own outputs may advance. Preserve every other dependency.
        for name,raw in expected_raw.items():
            self.validation.files[name]={'version':self._version(Path(name)),'raw':raw,'sha256':hashlib.sha256(raw).hexdigest()}
            self.validation.parsed.pop(name,None)
        self.validation.proofs.clear()  # discard input-derived views at this exact generation boundary
        self.snapshot=expected;self.snapshot_hash=w.sha256_value(expected);self.generation=1;self.owned_write=True
        self.inputs(root)

    def final(self,root,request):
        required_generation=1 if self.mode=='prepare' else 0
        if (request is not self.request or self.verified is None or self.generation!=required_generation
            or self.final_checked or (self.mode=='queue' and not self.queue_bound)):
            raise w.WorkflowError('one original normal prepare final reader required')
        self.inputs(root);self.finalizing=True
        try:
            import result_coordination as rc
            import department_autonomy as a
            readers={'committed_result':rc._committed_result,'intake_actor':rc._committed_intake_actor,
                     'historical_selection':a._historical_selection_sql}
            for (kind,_),(arguments,expected) in tuple(self.sql_reads.items()):
                actual=readers[kind](root,*arguments)
                if actual!=expected: raise w.WorkflowError('normal prepare final SQL/native fact changed')
        finally: self.finalizing=False
        from department_autonomy import _owner_message_transport_not_started
        _owner_message_transport_not_started(root,self.snapshot,request)
        self.inputs(root);self.final_checked=True


@contextmanager
def _queue_readset_scope(root,request,connections,enabled):
    # New scope per queue request. No source data survives normal prepare.
    if not enabled:
        yield None
        return
    if _PREPARE_SOURCE.get() is not None:raise w.WorkflowError('source scopes cannot cross requests')
    scope=_NormalPrepareSource(_PREPARE_SOURCE_SEAL,root,request,w._VALIDATION_CONTEXT.get(),connections,mode='queue')
    token=_PREPARE_SOURCE.set(scope)
    try:yield scope
    finally:scope.closed=True;_PREPARE_SOURCE.reset(token)


def _normal_prepare_registered_source(root,snapshot,request,reader):
    scope=_normal_prepare_sql_scope(root)
    return scope.source(root,snapshot,request,reader) if scope is not None else reader()


@contextmanager
def _normal_prepare_sql_observation(root):
    import sqlite3
    logical=Path(root)/'logs/result-coordination.sqlite3'
    if logical.is_symlink(): raise w.WorkflowError('original normal prepare SQL cannot be symlinked')
    path=logical.resolve();stat=path.stat()
    connection=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)
    try:
        version=connection.execute('PRAGMA data_version').fetchone()[0]
        wal=Path(str(path)+'-wal')
        if wal.is_symlink(): raise w.WorkflowError('original normal prepare WAL cannot be symlinked')
        ws=wal.stat() if wal.exists() else None
        yield [(logical,path,(stat.st_dev,stat.st_ino,stat.st_ctime_ns),connection,version,(ws.st_dev,ws.st_ino) if ws else None)]
    finally: connection.close()


@w.request_validation_context()
def prepare_message(root,request,*,identity_input_fifo=None):
    """Only an exact after-lock source can open this one normal prepare scope."""
    marker=request.get(_PREPARE_MARKER) if isinstance(request,dict) else None
    if marker is None or _strict_queue_document(root,marker).get('schema')!=_PREPARE_AFTER_LOCK:
        with _material_queue_source_scope(request.get('task_id'), request.get('action_id')):
            return _prepare_message(root, request, identity_input_fifo=identity_input_fifo)
    if identity_input_fifo is not None:
        raise w.WorkflowError('fresh material identity input cannot replace an existing source-proof mode')
    if _PREPARE_SOURCE.get() is not None:
        raise w.WorkflowError('normal prepare source handoff cannot cross requests')
    with w.request_validation_context() as validation, _normal_prepare_sql_observation(root) as connections:
        scope=_NormalPrepareSource(_PREPARE_SOURCE_SEAL,root,request,validation,connections)
        token=_PREPARE_SOURCE.set(scope);previous=validation.strict_unchanged;validation.strict_unchanged=True
        try:
            result=_prepare_message(root,request)
            if result.get('status') in {'ready_to_send','ready_to_queue'} and not scope.final_checked:
                from department_autonomy import _owner_message_commit_freshness
                _owner_message_commit_freshness(root,request)
            return result
        finally:
            scope.closed=True;validation.strict_unchanged=previous;_PREPARE_SOURCE.reset(token)


def _prepare_message(root, request, *, identity_input_fifo=None):
    """The real preparation entry consumes authorization and exact policy checks."""
    if request.get('scheduled_queue_resume') is not None:
        from department_event_dispatcher import prepare_scheduled_activation
        return prepare_scheduled_activation(root, request)
    if request.get('task_id') is None and request.get('pre_goal_source') is not None:
        from chief_assistant_coordination import pre_goal_prepare
        return pre_goal_prepare(root,request)
    if request.get('result_notification') is not None:
        # Delivery of an authenticated existing result is not a new business
        # assignment. Keep the original sender's notification lease/policy.
        import result_coordination as rc
        value=rc.exact_identity(request['result_notification'])
        if (request.get('delivery_mode')!='official_native_queue'
                or request.get('task_id')!=value['task_id']
                or request.get('sender_department')!=value['sender_department']):
            raise w.WorkflowError('exact original sender and admitted native result-notification mode required')
        route=rc.result_lane(root,value);fixed=w.department_registry(root).get(route.get('target_department'),{}).get('chat_binding',{})
        source=w.department_registry(root).get(value['sender_department'],{}).get('chat_binding',{})
        action='notify-result-'+rc._delivery_key(rc.delivery_identity(root,value,route=route)).split(':',1)[-1]
        expected={'source_project_id':source.get('project_id'),'target_project_id':fixed.get('project_id'),
            'target_department':route.get('target_department'),'target_thread_id':fixed.get('task_id'),
            'target_thread_title':fixed.get('title'),'target_cwd':fixed.get('cwd'),
            'target_sidebar_section_id':fixed.get('sidebar_section_id')}
        if (not fixed or any(request.get(k)!=v for k,v in expected.items())
                or request.get('payload_sha256')!=request.get('payload',{}).get('sha256')
                or request.get('action_class','thread_message')!='thread_message'
                or request.get('action_id',action)!=action
                or request.get('scope',f"department_result:{value['task_id']}:{value['sender_department']}")
                    !=f"department_result:{value['task_id']}:{value['sender_department']}"):
            raise w.WorkflowError('exact original notification identity, scope, fixed recipient and payload SHA required')
        prepared=rc.notification_claim(root,value,value['sender_department'],
            'official-event-dispatcher:'+value['sender_department'],
            request['notification_request_id'],request['actual_target_state'],request['payload'],
            delivery_mode='official_native_queue')
        if prepared.get('result')!='ready':
            return {'status':prepared['result'],'notification':prepared,'message_sent':False}
        keys=('task_id','action_id','action_class','scope','source_project_id','target_project_id',
              'target_department','target_thread_id','target_thread_title','target_cwd',
              'target_sidebar_section_id','payload_sha256')
        policy,_=w.policy_check(root,department=value['sender_department'],**{k:prepared[k] for k in keys})
        return {'status':'ready_to_queue' if policy['status']=='allow' else 'blocked',
                'policy_decision':policy,'notification':prepared,'payload':request['payload'],
                'delivery_mode':'official_native_queue','ordinary_send_allowed':False,
                'message_sent':False,'external_permission_issued':False}
    from goal_delivery_runtime import authorization_precheck, _collaboration_native
    checked = authorization_precheck(root,request['task_id'],request)
    if checked['status'] != 'within_original_authorization':
        return {'status':'blocked','authorization_precheck':checked,'message_sent':False}
    # The normal authority/policy checks still run. A caller-provided label has
    # no effect: only an exact command for already received immutable bytes can
    # acquire an observation-only event, never a fresh production exemption.
    from goal_delivery_runtime import restore_goal
    from qa_review_plan import original_result_continuation_intent
    from department_autonomy import message_route
    autonomous_route=message_route(root,restore_goal(root,w.read_json(w.snapshot_path(root,request['task_id']))),request)
    if autonomous_route and autonomous_route.get('readonly_collaboration_return') and autonomous_route.get('actual_owner_knowledge_proven'):
        return {'status':'already_read_by_original_owner','authorization_precheck':checked,
                'readonly_result_source':autonomous_route,'message_sent':False,'queue_accepted':False,
                'formal_result_received_proven':False,'repeat_transport_required':False,
                'next_action':'original owner continues with the already read immutable source; no duplicate intake or readonly request',
                'external_permission_issued':False}
    ordinary_snapshot = restore_goal(root, w.read_json(w.snapshot_path(root, request['task_id'])))
    ordinary_continuation = None if autonomous_route else original_result_continuation_intent(root, ordinary_snapshot, request)
    native_queue = request.get('delivery_mode') == 'official_native_queue'
    if native_queue:
        from department_event_dispatcher import native_queue_capability
        native_queue_capability(root)
    payload = request['payload']
    if w.file_digest(root,payload.get('path','')) != payload or payload['sha256'] != request.get('payload_sha256'):
        raise w.WorkflowError('exact prepared message required')
    if request.get('assignment_record_required'):
        body=w.safe_path(root,payload['path']).read_text(encoding='utf-8')
        if not re.search(r'(?<![A-Za-z0-9_-])'+re.escape(request['task_id'])+r'(?![A-Za-z0-9_-])',body):
            raise w.WorkflowError('assignment message must identify original task before policy or send')
    if identity_input_fifo is not None:
        request = _material_identity_at_prepare(root, request, identity_input_fifo)
    page = _collaboration_native(root,request['actual_target_state'])
    registry=w.department_registry(root)
    binding=registry.get(request['target_department'],{}).get('chat_binding')
    external_target=binding is None
    if external_target:
        snapshot=restore_goal(root,w.read_json(w.snapshot_path(root,request['task_id'])))
        goal=snapshot['goal_delivery'];contract=snapshot.get('goal_contract')
        if not isinstance(contract,dict) or w.file_digest(root,contract.get('path','')) != contract:
            raise w.WorkflowError('unchanged original external collaboration contract required')
        original=w.read_json(w.safe_path(root,contract['path']))
        from goal_delivery_runtime import execution_collaboration_scopes
        declared=[x for x in execution_collaboration_scopes(root,snapshot) if all(
            x.get(k)==request.get(k) for k in ('sender_department','target_department','scope'))]
        from professional_cms_integration import message_context as standing_message
        integration=standing_message(root,snapshot,request)
        from hq_bounded_web_admission import registered as bounded_HQ_WEB
        bounded_hq_web=bounded_HQ_WEB(root,snapshot,request)
        from hq_en2_readonly_source import registered as hq_en2_readonly
        hq_en2=hq_en2_readonly(root,snapshot,request)
        from hq_web_health_probe import registered as hq_web_health_probe
        hq_probe=hq_web_health_probe(root,snapshot,request)
        from goal_delivery_runtime import owner_result_collaboration_binding
        exact_owner_binding=owner_result_collaboration_binding(root,snapshot,request)
        if ((len(declared)!=1 and exact_owner_binding is None)or original.get('primary_owner')!=goal.get('primary_owner')
                or (request['sender_department']!=original.get('primary_owner') and integration is None and bounded_hq_web is None and hq_en2 is None and hq_probe is None)
                or request['scope'] not in original.get('authorized_scope',[])
                or original.get('human_authorization')!=goal.get('human_authorization')):
            raise w.WorkflowError('exact original owner, human source and declared external collaboration required')
    if binding is None:
        external=w.read_json(Path(root)/'data/department-registry.json').get('collaboration_bindings',{}).get(request['target_department'])
        if not external or (exact_owner_binding is None and request['target_department'] not in {
                d.get('target_department') for d in execution_collaboration_scopes(root,snapshot)}):
            raise w.WorkflowError('original explicitly declared collaboration target required')
        binding={**external,'task_id':external['thread_id']}
    if any(page.get('thread',{}).get(k) != binding.get(v) for k,v in
           {'id':'task_id','title':'title','cwd':'cwd'}.items()):
        raise w.WorkflowError('actual target fixed identity differs')
    if external_target and (page.get('thread',{}).get('kind') != 'codex'
            or not binding.get('host_id')
            or page.get('thread',{}).get('hostId') != binding['host_id']):
        raise w.WorkflowError('actual external collaboration host and native kind differ')
    turns = page.get('turns',[])
    if not turns:
        raise w.WorkflowError('real latest target turn required; notLoaded is not idle')
    if turns[0].get('status') in {'inProgress','pending'} and not native_queue:
        return {'status':'waiting_target_completion','message_sent':False,
                'notification_responsibility_retained':True,'authorization_precheck':checked}
    if 'post_adoption_notice' in request:
        existing = _prepare_adoption_notice(root, request)
        if existing is not None:
            return {**existing, 'authorization_precheck':checked,'external_permission_issued':False}
    registered_collaboration = any(a.get('action_id') == request['action_id']
        and (a.get('professional_execution_source') or a.get('professional_owner_message_source')
             or a.get('HQ_original_PUB_singlefield_source') or a.get('HQ_original_PUB_singlefield_continuation_source')) for a in ordinary_snapshot.get('goal_delivery', {}).get('approved_actions', []))
    if external_target or registered_collaboration:
        from goal_delivery_runtime import restore_goal, approved_action
        snapshot=restore_goal(root,w.read_json(w.snapshot_path(root,request['task_id'])))
        action_keys=('task_id','sender_department','action_id','action_class','scope','source_project_id',
                     'target_project_id','target_department','target_thread_id','target_thread_title',
                     'target_cwd','target_sidebar_section_id','payload_sha256')
        action=approved_action(root,snapshot,{k:request[k] for k in action_keys})
        if not action:raise w.WorkflowError('existing exact approved collaboration action required')
        inventory_pin=request.get('actual_live_inventory')
        observed=w._parse_observed_at(request.get('live_observed_at'))
        import datetime as dt
        if not inventory_pin or observed is None or not 0<=(dt.datetime.now(dt.timezone.utc)-observed).total_seconds()<=300:
            return {'status':'fresh_collaboration_observation_required','message_sent':False,
                    'next_action':'read_actual_fixed_sender_and_target_inventory_then_prepare_same_action',
                    'authorization_precheck':checked,'new_human_approval_required':False}
        inventory=_collaboration_native(root,inventory_pin)
        source=registry[request['sender_department']]['chat_binding']
        selected=[]
        for fixed in [source,binding]:
            rows=[x for x in [*inventory.get('threads',[]),*inventory.get('pinnedThreads',[])] if x.get('id')==fixed['task_id']]
            if len(rows)!=1 or any(rows[0].get(k)!=fixed[v] for k,v in
                    {'projectId':'project_id','title':'title','cwd':'cwd','hostId':'host_id'}.items()):
                raise w.WorkflowError('fresh actual collaboration sender and target identities required')
            selected.append(rows[0])
        live={'observed_at':request['live_observed_at'],'threads':selected,'actual_native_observation':inventory_pin,
              'native_receipt_ref':inventory_pin['path'],
              'actual_native_target_turns':{binding['task_id']:request['actual_target_state']},
              'target_sidebar_section_id':request['target_sidebar_section_id'],
              'delivery_mode':request.get('delivery_mode', 'mcp_direct_send')}
        path=Path(root)/'logs/goal-delivery-observations'/request['task_id']/(w.sha256_value(live)+'.json')
        if not path.exists():w.atomic_write_json(path,live)
        live_pin=w.file_digest(root,str(path.relative_to(root)))
        with w.workflow_lock(root):
            snapshot=restore_goal(root,w.read_json(w.snapshot_path(root,request['task_id'])))
            def write_observation():
                goal=snapshot['goal_delivery'];observations={**goal.get('current_route_observations',{}),request['action_id']:live_pin}
                snapshot['goal_delivery']={**goal,'current_route_observations':observations}
                event=w.append_workflow_event(root,request['task_id'],snapshot['current_state'],
                    {'goal_delivery':snapshot['goal_delivery'],'actual_route_observation':live_pin,'external_permission_issued':False})
                w.atomic_write_json(w.snapshot_path(root,request['task_id']),snapshot)
                return event,snapshot
            scope=_normal_prepare_sql_scope(root)
            if scope is None: write_observation()
            else: scope.observation(root,snapshot,live_pin,write_observation)
    if request['action_id']=='assign-goal-review:'+request['task_id']:
        from goal_delivery_runtime import restore_goal
        with w.workflow_lock(root):
            snapshot=restore_goal(root,w.read_json(w.snapshot_path(root,request['task_id'])))
            goal=snapshot['goal_delivery'];contract=snapshot.get('goal_contract')
            body=w.safe_path(root,payload['path']).read_text()
            if (request['sender_department']!='operations'
                    or request['target_department']!=goal['responsible_assistant']
                    or not contract or w.file_digest(root,contract['path'])!=contract
                    or request['task_id'] not in body or contract['path'] not in body):
                raise w.WorkflowError('original contract-linked initial responsibility message required')
            rows=[e for e in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS) if e.get('task_id')==request['task_id']
                  and e.get('details',{}).get('initial_responsibility_message')]
            source={'payload':payload,'goal_contract':contract,'sender_department':'operations',
                    'target_department':goal['responsible_assistant'],'scope':request['scope'],
                    'external_permission_issued':False}
            if rows and (len(rows)!=1 or rows[0]['details']['initial_responsibility_message']!=source):
                raise w.WorkflowError('initial responsibility message already frozen; no replacement or resend')
            if not rows:
                w.append_workflow_event(root,request['task_id'],snapshot['current_state'],
                                        {'initial_responsibility_message':source})
    fields = {k:request[k] for k in ('task_id','action_id','action_class','scope','source_project_id',
        'target_project_id','target_department','target_thread_id','target_thread_title','target_cwd',
        'target_sidebar_section_id','payload_sha256')}
    policy,_ = w.policy_check(root,department=request['sender_department'],**fields,
                             delivery_mode=request.get('delivery_mode', ''),
                             **({'original_message':request} if ordinary_continuation is not None or autonomous_route else {}))
    if ordinary_continuation is not None and policy['status'] == 'allow':
        _record_original_result_continuation_prepared(root, request, ordinary_continuation, policy)
    return {'status':('ready_to_queue' if native_queue else 'ready_to_send') if policy['status']=='allow' else 'blocked',
            'authorization_precheck':checked,'policy_decision':policy,
            'payload':payload,'message_sent':False,'external_permission_issued':False,
            **({'delivery_mode':'official_native_queue','ordinary_send_allowed':False} if native_queue else {})}


def initial_responsibility_payload(root, snapshot, sender, target, scope, payload_sha256):
    rows=[e for e in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS) if e.get('task_id')==snapshot.get('task_id')
          and e.get('details',{}).get('initial_responsibility_message')]
    if len(rows)!=1 or w.validate_workflow_events(root,snapshot['task_id']):return False
    record=rows[0]['details']['initial_responsibility_message'];pin=record['payload']
    goal=snapshot['goal_delivery'];contract=snapshot.get('goal_contract')
    return (sender=='operations' and target==goal['responsible_assistant']
            and scope in goal['authorized_scope'] and record['scope']==scope
            and record['sender_department']==sender and record['target_department']==target
            and record['goal_contract']==contract and w.file_digest(root,contract['path'])==contract
            and w.file_digest(root,pin['path'])==pin and pin['sha256']==payload_sha256
            and record['external_permission_issued'] is False)


def initial_assignment_source(root,snapshot,dispatch,contract):
    """Consume a committed actual assignment; no new QA or dispatch reconstruction."""
    from goal_continuity import pin_document, _dispatch_source
    rows=[e.get('details',{}).get('initial_responsibility_assignment_source')
          for e in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS) if e.get('task_id')==snapshot['task_id']
          and e.get('details',{}).get('initial_responsibility_assignment_source')]
    if not rows:return False
    if len(rows)!=1:raise w.WorkflowError('one original responsibility assignment source required')
    item=pin_document(root,rows[0]);_,actual=_dispatch_source(root,item)
    if actual!=dispatch:return False
    return (item['department']==snapshot['goal_delivery']['responsible_assistant']
            and initial_responsibility_payload(root,snapshot,item['sender_department'],item['department'],
                    dispatch['scope'],item['payload']['sha256'])
            and contract==snapshot.get('goal_contract'))


def actual_target_turn_status(root, live, inventory_row, binding):
    """Resolve a notLoaded/cache label only with a newer real fixed-thread read."""
    from goal_delivery_runtime import _collaboration_native
    pins=live.get('actual_native_target_turns',{})
    if not isinstance(pins,dict):raise w.WorkflowError('exact native target turns must be a mapping')
    pin=pins.get(binding.get('task_id'),live.get('actual_native_target_turn'))
    status=inventory_row.get('status')
    status=status.get('type') if isinstance(status,dict) else status
    if pin is None:return status
    page=_collaboration_native(root,pin)
    if any(page.get('thread',{}).get(k)!=binding.get(v) for k,v in
           {'id':'task_id','title':'title','cwd':'cwd'}.items()):
        raise w.WorkflowError('exact native notification target turn identity required')
    native_status=page.get('thread',{}).get('status',{})
    native_status=native_status.get('type') if isinstance(native_status,dict) else native_status
    if status=='notLoaded' and native_status=='notLoaded':return 'notLoaded'
    turns=page.get('turns',[])
    if not turns:return 'unknown_target'
    turn=turns[0]
    if turn.get('status') in {'inProgress','pending'}:return 'active'
    previous,current=inventory_row.get('updatedAt'),page['thread'].get('updatedAt')
    if (status=='idle' and turn.get('status') in {'completed','interrupted','failed'}
            and previous is None and current is None):
        return 'idle'
    if (type(previous) not in {int,float} or type(current) not in {int,float} or current<previous):
        return 'unknown_target'
    if turn.get('status') in {'completed','interrupted','failed'}:
        # Idle means no active turn, not successful completion or healthy source.
        return 'idle'
    return 'unknown_target'


def recovered_producer_source(root,snapshot,role):
    """Real restored assignment replaces missing local ACK metadata, not QA."""
    if role not in snapshot.get('goal_delivery',{}).get('producer_departments',[]):return None
    records=[e.get('details',{}).get('native_source_recovery')
             for e in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS) if e.get('task_id')==snapshot['task_id']
             and e.get('details',{}).get('native_source_recovery',{}).get('department')==role]
    if not records:return None
    proofs=[validate(root,item)[1] for item in records]
    return {'actual_sources':proofs,'dispatch_or_ACK_fabricated':False,'external_permission_issued':False}


def collaboration_source(root, record):
    """Admit an already performed collaboration as facts, never as a new permit."""
    from goal_delivery_runtime import restore_goal, _collaboration_native, enabled
    task=record.get('task_id');snapshot=restore_goal(root,w.read_json(w.snapshot_path(root,task)))
    if not enabled(root,snapshot) or record.get('source_kind')!='historical_native_collaboration':
        raise w.WorkflowError('exact historical complete-goal collaboration required')
    goal=snapshot['goal_delivery'];owner=goal['primary_owner'];sender=record['sender_department']
    binding=w.read_json(Path(root)/'data/department-registry.json').get('collaboration_bindings',{}).get(sender,{})
    if not binding or record.get('scope') not in goal['authorized_scope']:
        raise w.WorkflowError('original exact collaboration binding and scope required')
    base={**record,'schema':'goal-current-assignment/v2','department':owner,'sender_department':owner,
          'source_kind':'owner_direct_native','authorization_pin':goal['authorization_pin']}
    validate(root,base,require_record=False)
    human=w.read_json(w.safe_path(root,goal['authorization_pin']['path']))
    human_text=''.join(x.get('text','') for x in human['message'].get('content',[]) if x.get('type')=='text')
    if binding.get('title','') not in human_text:
        raise w.WorkflowError('original human source must explicitly name the existing collaborator')
    page=_collaboration_native(root,record['actual_native_invocation'])
    calls=[c for t in page.get('turns',[]) for c in t.get('items',[])
           if c.get('id')==record.get('source_call_id') and c.get('type')=='mcpToolCall'
           and c.get('server')=='codex_app' and c.get('tool')=='send_message_to_thread']
    payload=record['payload'];body=w.safe_path(root,payload['path']).read_text()
    versions=set(re.findall(r'''(?<![A-Za-z0-9_-])(?:candidate_version|候选(?:版本)?)[`"']?\s*[:=：]?\s*[`"']?\s*([A-Za-z0-9][A-Za-z0-9+._-]{0,199})''',body))
    if versions!={record['candidate_version']}:
        raise w.WorkflowError('one explicit original candidate-version identity required, not an ordinary word')
    sent=_collaboration_native(root,record['actual_native_send'])
    if (len(calls)!=1 or calls[0].get('status')!='completed' or calls[0].get('error')
            or calls[0].get('truncated',False) is not False or w.file_digest(root,payload['path'])!=payload
            or calls[0]['arguments'].get('threadId')!=binding['thread_id']
            or calls[0]['arguments'].get('prompt')!=body or sent.get('threadId')!=binding['thread_id']
            or not re.search(r'(?<![A-Za-z0-9+._-])'+re.escape(record['original_task_id'])+r'(?![A-Za-z0-9+._-])',body)
            or not re.search(r'(?<![A-Za-z0-9+._-])'+re.escape(record['candidate_version'])+r'(?![A-Za-z0-9+._-])',body)):
        raise w.WorkflowError('original exact successful collaboration send required')
    final=_collaboration_native(root,record['actual_native_result'])
    if any(final.get('thread',{}).get(k)!=binding.get(v) for k,v in
           {'id':'thread_id','title':'title','cwd':'cwd'}.items()):
        raise w.WorkflowError('real completed collaborator identity differs')
    turns=[t for t in final.get('turns',[]) if t.get('id')==record.get('source_turn_id')
           and t.get('status')=='completed' and not t.get('error')]
    messages=[m for t in turns for m in t.get('items',[]) if m.get('id')==record.get('source_message_id')
              and m.get('type')=='agentMessage' and m.get('phase')=='final_answer']
    reply=record['visible_reply'];result=record['result']
    if (len(messages)!=1 or w.file_digest(root,reply['path'])!=reply
            or w.safe_path(root,reply['path']).read_bytes()!=messages[0]['text'].encode()
            or w.file_digest(root,result['path'])!=result):
        raise w.WorkflowError('original frozen collaborator final and result bytes required')
    origin=Path(record['result_origin_path']).resolve();project=Path(binding['cwd']).resolve()
    if (not origin.is_relative_to(project) or 'reports' not in origin.relative_to(project).parts
            or str(origin) not in messages[0]['text']
            or origin.read_bytes()!=w.safe_path(root,result['path']).read_bytes()):
        raise w.WorkflowError('only the actual explicitly linked collaborator report can be recovered')
    action={'task_id':task,'action_id':record['action_id'],'action_class':'thread_message',
            'scope':record['scope'],'target_department':sender,'target_thread_id':binding['thread_id'],
            'payload_sha256':payload['sha256'],'source_recovered':True,'new_permissions':0}
    return {'task_id':task,'action_id':record['action_id'],'department':sender,'threadId':binding['thread_id'],
            'proof_state':'PROVEN','status':'result_received','approved_action':action,
            'result':result,'visible_reply':reply,'native_result':record['actual_native_result'],
            'native_transport':record['actual_native_send'],'original_invocation':record['actual_native_invocation'],
            'policy_decision_id':None,'historical_policy_fabricated':False,'source_recovered':True,
            'proves_completion':False,'proves_next_action':False}


def observe_post_qa_source_continuation(root, input_path):
    """Append verified source facts; never replace a dispatch/ACK/goal/QA row."""
    from goal_delivery_runtime import restore_goal
    import qa_review_plan as q
    root = Path(root).resolve()
    pin = w.file_digest(root, input_path)
    with w.workflow_lock(root):
        item = q._review_source_document(root, pin)
        snapshot = restore_goal(root, w.read_json(w.snapshot_path(root, item['task_id'])))
        rows, bad = w._validate_receipt_chain(root, item['task_id'])
        if bad:
            raise w.WorkflowError('intact original receipts required before source observation')
        plan = q.load_plan(root, snapshot)
        facts = q.post_qa_source_continuation(root, snapshot, rows, plan, item)
        proof = {'input':pin, 'dispatch_receipt_id':facts['dispatch_receipt_id'],
                 'facts_sha256':w.sha256_value(facts)}
        events = [e for e in w.read_jsonl(root / w.WORKFLOW_EVENTS)
                  if e.get('task_id') == item['task_id'] and e.get('details', {}).get(
                      'post_qa_source_continuation', {}).get('dispatch_receipt_id') == facts['dispatch_receipt_id']]
        if events:
            if len(events) != 1 or events[0]['details']['post_qa_source_continuation'] != proof:
                raise w.WorkflowError('original source observation already frozen; no replacement')
            return {'status':'duplicate_ignored', 'event_id':events[0]['event_id'], 'ACK_created':False}
        event = w.append_workflow_event(root, item['task_id'], snapshot['current_state'],
            {'post_qa_source_continuation':proof, 'external_permission_issued':False})
        return {'status':'source_facts_observed', 'event_id':event['event_id'],
                'ACK_created':False, 'responsibility_or_candidate_or_QA_changed':False}


def collaboration_queue_binding(root, snapshot, action):
    """Original external declaration or authenticated internal owner-result message."""
    from goal_delivery_runtime import approved_action, _collaboration_binding, owner_result_collaboration_binding
    internal=owner_result_collaboration_binding(root,snapshot,action)
    if internal is not None:return internal
    goal=snapshot.get('goal_delivery',{});contract=_strict_queue_document(root,snapshot.get('goal_contract'))
    keys=('task_id','sender_department','action_id','action_class','scope','source_project_id',
          'target_project_id','target_department','target_thread_id','target_thread_title',
          'target_cwd','target_sidebar_section_id','payload_sha256')
    expected={k:action.get(k)for k in keys}
    binding=_collaboration_binding(root,snapshot,action.get('target_department'))
    source=w.department_registry(root).get(action.get('sender_department'),{}).get('chat_binding',{})
    from goal_delivery_runtime import execution_collaboration_scopes
    # A completed original queue must not depend on a later source that itself
    # consumes that queue. Prefer only an exact immutable contract declaration;
    # genuinely appended collaborations retain their full source validation.
    declared=[d for d in contract.get('collaboration_scopes',[])if all(d.get(k)==action.get(k)
              for k in ('sender_department','target_department','scope'))]
    if not declared:
        declared=[d for d in execution_collaboration_scopes(root,snapshot)if all(d.get(k)==action.get(k)
                  for k in ('sender_department','target_department','scope'))]
    from professional_cms_integration import message_context as standing_message
    integration=standing_message(root,snapshot,action)
    if (len(declared)!=1
            or contract.get('primary_owner')!=goal.get('primary_owner')
            or (action.get('sender_department')!=contract.get('primary_owner') and integration is None)
            or contract.get('human_authorization')!=goal.get('human_authorization')
            or w.file_digest(root,contract.get('human_authorization',{}).get('evidence_path',''))!=goal.get('authorization_pin')
            or action.get('task_id')!=snapshot.get('task_id') or action.get('action_class')!='thread_message'
            or action.get('scope')not in contract.get('authorized_scope',[]) or not binding
            or any(action.get(k)!=binding.get(v)for k,v in {'target_project_id':'project_id',
                'target_thread_id':'thread_id','target_thread_title':'title','target_cwd':'cwd'}.items())
            or source.get('project_id')!=action.get('source_project_id')
            or approved_action(root,snapshot,expected) is None):
        raise w.WorkflowError('exact frozen declared external collaboration/owner/authorization required')
    _strict_queue_document(root,goal.get('authorization_pin'))
    return source,binding


def _collaboration_queue_preparation(root, snapshot, request_pin, prepared_pin, *, _capture_source=None):
    request=_strict_queue_document(root,request_pin);prepared=_strict_queue_document(root,prepared_pin)
    if _capture_source is not None and request.get('HQ_original_PUB_singlefield_continuation_source') is not None:
        from professional_cms_single_field_admission import registered_bridge
        verified = registered_bridge(root, snapshot, request)
        if verified is None: raise w.WorkflowError('exact original registered continuation source required')
        source = verified['sender_binding']
        target = {**verified['pub_binding'], 'thread_id': verified['pub_binding']['task_id']}
        _capture_source.append(verified)
    else:
        source,target=collaboration_queue_binding(root,snapshot,request)
    rows = w.read_jsonl(Path(root) / w.POLICY_DECISIONS, where={
        'decision_id': prepared.get('policy_decision', {}).get('decision_id'),
    })
    fields=('task_id','action_id','action_class','scope','source_project_id','target_project_id',
            'target_department','target_thread_id','target_thread_title','target_cwd',
            'target_sidebar_section_id','payload_sha256')
    auth=prepared.get('authorization_precheck',{})
    if (len(rows)!=1 or rows[0]!=prepared.get('policy_decision') or rows[0].get('status')!='allow'
            or rows[0].get('routing_status')!='routing_allowed'
            or rows[0].get('department')!=request.get('sender_department')
            or any(rows[0].get(k)!=request.get(k)for k in fields)
            or rows[0].get('delivery_mode',request.get('delivery_mode'))!=request.get('delivery_mode')
            or request.get('delivery_mode')!='official_native_queue' or request.get('authorization_changes',[])!=[]
            or prepared.get('status')!='ready_to_queue' or prepared.get('delivery_mode')!='official_native_queue'
            or prepared.get('ordinary_send_allowed') is not False or prepared.get('message_sent') is not False
            or prepared.get('external_permission_issued') is not False
            or auth.get('status')!='within_original_authorization'
            or auth.get('original_authorization')!=snapshot['goal_delivery']['authorization_pin']
            or prepared.get('payload')!=request.get('payload')
            or w.file_digest(root,request['payload']['path'])!=request['payload']
            or request['payload']['sha256']!=request.get('payload_sha256')):
        raise w.WorkflowError('actual exact allowed normal official queue preparation required')
    return request,prepared,rows[0],source,target


def _queue_commit_freshness(root, snapshot, request, policy, *, refreshed=None):
    """Only clocks/pinned observations are reread here; no cached route PASS."""
    import datetime as dt
    action_id=request['action_id'];goal=snapshot['goal_delivery']
    rows=[x for x in goal.get('approved_actions',[])if x.get('action_id')==action_id]
    if len(rows)!=1:raise w.WorkflowError('one exact original queue action before commit required')
    pin = refreshed['live'] if refreshed else (goal.get('current_route_observations',{}).get(action_id) or rows[0].get('live_identity'))
    if not isinstance(pin,dict)or w.file_digest(root,pin.get('path',''))!=pin:
        raise w.WorkflowError('exact original live observation before queue intent required')
    live=w.read_json(w.safe_path(root,pin['path']))
    stamps=[w._parse_observed_at(policy.get('checked_at')),w._parse_observed_at(refreshed['observed_at'] if refreshed else request.get('live_observed_at')),
            w._parse_observed_at(live.get('observed_at'))]
    now=dt.datetime.now(dt.timezone.utc)
    if any(at is None or not 0<=(now-at).total_seconds()<=300 for at in stamps):
        raise w.WorkflowError('fresh original policy/request/route required immediately before queue intent')


# In-process capability, never accepted from JSON or persisted across requests.
_QUEUE_ROUTE_KEYS=('task_id','sender_department','action_id','action_class','scope','source_project_id',
                   'target_project_id','target_department','target_thread_id','target_thread_title',
                   'target_cwd','target_sidebar_section_id','payload_sha256','delivery_mode')
_QUEUE_PROOF_SEAL = object()
_ACTIVE_QUEUE_PROOF = ContextVar("original_normal_queue_source_proof", default=None)
_MATERIAL_FRESH_QUEUE_ACTIONS = frozenset({
    'PUB-materials-PR312-original-R3-proven-zero-recovery-20261107-v1',
    'PUB-materials-PR312-original-R3-live-launch-20261107-v1',
    'PUB-materials-PR312-original-R3-receipts-reconciled-20261107-v1',
})
_MATERIAL_IDENTITY_FIELDS = {'actual_sender_state', 'actual_target_state', 'actual_live_inventory', 'live_observed_at'}


def _material_refreshed_request(root, request, path):
    from material_r3_dispatch import TASK
    import datetime as dt

    pin = w.file_digest(root, path)
    fresh = _strict_queue_document(root, pin)
    if ({k: v for k, v in fresh.items() if k not in _MATERIAL_IDENTITY_FIELDS}
            != {k: v for k, v in request.items() if k not in _MATERIAL_IDENTITY_FIELDS}
            or request.get('task_id') != TASK or request.get('action_id') not in _MATERIAL_FRESH_QUEUE_ACTIONS):
        raise w.WorkflowError('only the exact original R3 material queue may refresh its identity observations')
    observed = w._parse_observed_at(fresh.get('live_observed_at'))
    prior = w._parse_observed_at(request.get('live_observed_at'))
    if not observed or not prior or not prior < observed or not 0 <= (dt.datetime.now(dt.timezone.utc)-observed).total_seconds() <= 300:
        raise w.WorkflowError('fresh actual updated sender and target observation required')
    return fresh, pin


def _material_identity_at_prepare(root, request, fifo):
    """Wait once for original live evidence after immutable authorization checks."""
    import os
    import select
    import sys
    from material_r3_dispatch import TASK

    channel = w.safe_path(root, fifo)
    if (request.get('task_id') != TASK or request.get('action_id') not in _MATERIAL_FRESH_QUEUE_ACTIONS
            or request.get('delivery_mode') != 'official_native_queue'
            or channel.is_symlink() or not channel.is_fifo()):
        raise w.WorkflowError('exact material owner action and bounded local FIFO required')
    fd = os.open(channel, os.O_RDWR | os.O_NONBLOCK)
    try:
        print('READY_FOR_ACTUAL_MATERIAL_IDENTITY', file=sys.stderr, flush=True)
        if not select.select([fd], [], [], 120)[0]:
            raise w.WorkflowError('actual fresh material identity was not supplied before the bounded timeout')
        line = os.read(fd, 4096).decode('utf-8')
    finally:
        os.close(fd)
    if not line.endswith('\n') or len(line.splitlines()) != 1:
        raise w.WorkflowError('one exact fresh identity request path required')
    return _material_refreshed_request(root, request, line.strip())[0]


@contextmanager
def _material_queue_source_scope(task, action):
    from material_push_expiry import TASK
    from department_autonomy import _MATERIAL_QUEUE_SOURCE_MEMO
    enabled=task==TASK and action in (_MATERIAL_FRESH_QUEUE_ACTIONS | {
        'PUB-materials-1f92-owner-additional-once-original-WEB-20261106-v1',
        'PUB-materials-PR312-two-test-assertions-original-WEB-20261106-v1',
    })
    token=_MATERIAL_QUEUE_SOURCE_MEMO.set({} if enabled else None)
    try:
        yield
    finally:
        _MATERIAL_QUEUE_SOURCE_MEMO.reset(token)

class _QueueSourceProof:
    def __init__(self, seal, root, snapshot, request, verified, connections, request_pin, prepared_pin):
        if seal is not _QUEUE_PROOF_SEAL or w._VALIDATION_CONTEXT.get() is None:
            raise w.WorkflowError('internal exact queue proof factory required')
        self.seal=seal; self.validation=w._VALIDATION_CONTEXT.get(); self.root=Path(root).resolve()
        root_stat=self.root.stat(); self.root_inode=(root_stat.st_dev,root_stat.st_ino)
        self.snapshot=snapshot; self.snapshot_hash=w.sha256_value(snapshot); self.request=request
        self.request_hash=w.sha256_value(request); self.request_pin=request_pin; self.prepared_pin=prepared_pin
        self.pins_hash=w.sha256_value([request_pin,prepared_pin]); self.action=verified['action']
        self.action_hash=w.sha256_value(self.action); self.registration=verified['registration']; self.event_id=verified['event_id']
        self.route_consumed=False
        self.binding=(verified['sender_binding'], {**verified['pub_binding'], 'thread_id':verified['pub_binding']['task_id']})
        self.binding_hash=w.sha256_value(self.binding)
        self.dependencies=tuple((name,entry['sha256'],len(entry['raw'])) for name,entry in self.validation.files.items())
        self.dependencies_hash=w.sha256_value(self.dependencies)
        self.connections=tuple(connections)
        self.sql_identity_hash=w.sha256_value([(str(logical),str(path),inode,version,wal) for logical,path,inode,_,version,wal in self.connections])

    def __copy__(self): raise TypeError('queue source proof cannot be copied')
    def __deepcopy__(self, memo): raise TypeError('queue source proof cannot be copied')
    def __reduce__(self): raise TypeError('queue source proof cannot be serialized')

    def verify(self, root, snapshot, thin, request, *, commit=False):
        if (self.seal is not _QUEUE_PROOF_SEAL or _ACTIVE_QUEUE_PROOF.get() is not self or w._VALIDATION_CONTEXT.get() is not self.validation
            or Path(root).resolve()!=self.root or (self.root.stat().st_dev,self.root.stat().st_ino)!=self.root_inode
            or snapshot is not self.snapshot or request is not self.request
            or w.sha256_value(snapshot)!=self.snapshot_hash or w.sha256_value(request)!=self.request_hash
            or w.sha256_value([self.request_pin,self.prepared_pin])!=self.pins_hash
            or w.file_digest(root,self.request_pin.get('path',''))!=self.request_pin
            or w.file_digest(root,self.prepared_pin.get('path',''))!=self.prepared_pin
            or w.sha256_value(self.action)!=self.action_hash or w.sha256_value(self.binding)!=self.binding_hash
            or w.sha256_value(self.dependencies)!=self.dependencies_hash
            or w.sha256_value([(str(logical),str(path),inode,version,wal) for logical,path,inode,_,version,wal in self.connections])!=self.sql_identity_hash
            or len(self.connections)!=1
            or not isinstance(thin,dict) or set(thin)!=set(_QUEUE_ROUTE_KEYS)
            or any(request.get(k)!=thin[k] for k in _QUEUE_ROUTE_KEYS)):
            raise w.WorkflowError('same-request bound source proof required')
        for name, digest, size in self.dependencies:
            entry=self.validation.files.get(name)
            if entry is None or (entry['sha256'],len(entry['raw']))!=(digest,size):
                raise w.WorkflowError('source proof dependency version changed')
            if commit:
                raw=Path(name).read_bytes()
                import hashlib
                if len(raw)!=size or hashlib.sha256(raw).hexdigest()!=digest:
                    raise w.WorkflowError('source proof dependency changed before intent')
        for logical, path, inode, connection, version, wal_identity in self.connections:
            if logical.is_symlink() or logical.resolve()!=path: raise w.WorkflowError('source SQL database path changed')
            stat=path.stat(); wal=Path(str(path)+'-wal')
            if wal.is_symlink(): raise w.WorkflowError('source SQL WAL path changed')
            wal_stat=wal.stat() if wal.exists() else None
            current_wal=(wal_stat.st_dev,wal_stat.st_ino) if wal_stat else None
            if (stat.st_dev,stat.st_ino,stat.st_ctime_ns)!=inode or current_wal!=wal_identity or connection.execute('PRAGMA data_version').fetchone()[0]!=version:
                raise w.WorkflowError('source proof SQL database changed before intent: '+str(path))
        if commit:
            if not self.route_consumed: raise w.WorkflowError('source proof must be consumed exactly once by route')
            scope=_normal_prepare_sql_scope(root)
            if scope is not None:
                if (scope.mode!='queue' or scope.request is not request or scope.verified is None
                    or scope.snapshot_hash!=self.snapshot_hash or scope.verified.get('registration')!=self.registration
                    or scope.verified.get('event_id')!=self.event_id or scope.verified.get('action')!=self.action):
                    raise w.WorkflowError('exact current queue source readset required')
                scope.final(root,request)  # original SQL/native readers + real file/Git rereads
            else:
                # Non-scoped readers retain the original conservative full verification.
                from professional_cms_single_field_admission import registered_bridge
                import result_coordination as rc
                rc._INTAKE_ACTOR_MEMO.clear()
                final=registered_bridge(root,snapshot,request)
                if (final is None or final.get('registration')!=self.registration or final.get('event_id')!=self.event_id
                    or final.get('action')!=self.action or final.get('sender_binding')!=self.binding[0]
                    or {**final.get('pub_binding',{}),'thread_id':final.get('pub_binding',{}).get('task_id')}!=self.binding[1]):
                    raise w.WorkflowError('fresh final original source verification changed')
            for logical, path, inode, connection, version, wal_identity in self.connections:
                if logical.is_symlink() or logical.resolve()!=path: raise w.WorkflowError('source SQL database path changed')
                stat=path.stat(); wal=Path(str(path)+'-wal')
                if wal.is_symlink(): raise w.WorkflowError('source SQL WAL path changed')
                wal_stat=wal.stat() if wal.exists() else None
                current_wal=(wal_stat.st_dev,wal_stat.st_ino) if wal_stat else None
                if (stat.st_dev,stat.st_ino,stat.st_ctime_ns)!=inode or current_wal!=wal_identity or connection.execute('PRAGMA data_version').fetchone()[0]!=version:
                    raise w.WorkflowError('source proof SQL database changed during final verification: '+str(path))
        return self

def _verify_queue_source_proof(proof, root, snapshot, thin, request):
    if type(proof) is not _QueueSourceProof:
        raise w.WorkflowError('internal queue source proof required')
    if proof.route_consumed: raise w.WorkflowError('queue source proof already consumed')
    proof.verify(root,snapshot,thin,request)
    proof.route_consumed=True
    return proof

@contextmanager
def _queue_source_sql_observation(root, enabled):
    if not enabled:
        yield []
        return
    import sqlite3
    validation=w._VALIDATION_CONTEXT.get()
    if validation is None: raise w.WorkflowError('normal queue validation context required')
    previous_strict=validation.strict_unchanged
    validation.strict_unchanged=True
    connections=[]
    try:
        for relative in ('logs/result-coordination.sqlite3',):
            logical=Path(root)/relative
            if logical.is_symlink(): raise w.WorkflowError('original SQL database cannot be a symlink')
            path=logical.resolve(); stat=path.stat()
            connection=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)
            try:
                version=connection.execute('PRAGMA data_version').fetchone()[0]
                wal=Path(str(path)+'-wal')
                if wal.is_symlink(): raise w.WorkflowError('original SQL WAL cannot be a symlink')
                wal_stat=wal.stat() if wal.exists() else None
                wal_identity=(wal_stat.st_dev,wal_stat.st_ino) if wal_stat else None
                connections.append((logical,path,(stat.st_dev,stat.st_ino,stat.st_ctime_ns),connection,version,wal_identity))
            except BaseException:
                connection.close()
                raise
        import result_coordination as rc
        rc._INTAKE_ACTOR_MEMO.clear()  # force first source audit to use current SQL
        yield connections
    finally:
        for _,_,_,connection,_,_ in connections: connection.close()
        validation.strict_unchanged=previous_strict

def _refresh_material_queue_observation(root, request, source, target, path):
    """Refresh only the real identities after the slow original authorization check."""
    from goal_delivery_runtime import _collaboration_native
    fresh, pin = _material_refreshed_request(root, request, path)
    inventory = _collaboration_native(root, fresh['actual_live_inventory'])
    matches = []
    for fixed, key in ((source, 'actual_sender_state'), (target, 'actual_target_state')):
        thread_id = fixed.get('task_id') or fixed['thread_id']
        rows = [row for row in [*inventory.get('threads', []), *inventory.get('pinnedThreads', [])] if row.get('id') == thread_id]
        if len(rows) != 1 or any(rows[0].get(k) != fixed[v] for k, v in
                                  {'projectId': 'project_id', 'title': 'title', 'cwd': 'cwd', 'hostId': 'host_id'}.items()):
            raise w.WorkflowError('actual unchanged original sender/target/project/host inventory required')
        page = _collaboration_native(root, fresh[key]); thread = page['thread']
        if any(thread.get(k) != rows[0].get(k) for k in ('id', 'title', 'cwd', 'hostId')) or not page['turns']:
            raise w.WorkflowError('actual original sender/target turns must bind the fresh inventory')
        matches.append(rows[0])
    live = {'observed_at': fresh['live_observed_at'], 'threads': matches,
            'actual_native_observation': fresh['actual_live_inventory'], 'native_receipt_ref': fresh['actual_live_inventory']['path'],
            'actual_native_target_turns': {request['target_thread_id']: fresh['actual_target_state']},
            'target_sidebar_section_id': request['target_sidebar_section_id'], 'delivery_mode': request['delivery_mode']}
    location = Path(root) / 'logs' / 'goal-delivery-observations' / request['task_id'] / (w.sha256_value(live) + '.json')
    if not location.exists():
        w.atomic_write_json(location, live)
    return {'fresh_request': pin, 'live': w.file_digest(root, str(location.relative_to(root))),
            'observed_at': fresh['live_observed_at']}


@w.request_validation_context()
def queue_collaboration(root, request_path, prepared_path, directory, *, fresh_observation=None):
    """Reserve the one task/action before the official call; never activate a busy window."""
    from goal_delivery_runtime import restore_goal,collaboration_route
    from department_event_dispatcher import OfficialQueueTransport
    from department_autonomy import _MATERIAL_QUEUE_SOURCE_MEMO
    request_pin=w.file_digest(root,request_path);prepared_pin=w.file_digest(root,prepared_path)
    request=_strict_queue_document(root,request_pin);task=request.get('task_id')
    actual_dir=w.safe_path(root,directory)
    if Path(directory).parts[:2]!=('logs','handoffs') or actual_dir.is_symlink():
        raise w.WorkflowError('project-owned original queue directory required')
    marker=request.get('HQ_original_PUB_singlefield_continuation_source')
    after_lock=bool(marker is not None and _strict_queue_document(root,marker).get('schema')=='same-original-PUB-after-receipt-lock-continuation-source/v1')
    with w.workflow_lock(root), _material_queue_source_scope(task,request.get('action_id')), _queue_source_sql_observation(root, after_lock) as sql_observation, _queue_readset_scope(root,request,sql_observation,after_lock) as readset:
        snapshot=restore_goal(root,w.read_json(w.snapshot_path(root,task)))
        capture=[]
        request,prepared,policy,source,target=_collaboration_queue_preparation(root,snapshot,request_pin,prepared_pin,_capture_source=capture if after_lock else None)
        if readset is not None:
            if readset.queue_bound or w.sha256_value(request)!=readset.request_hash or w.sha256_value(snapshot)!=readset.snapshot_hash:
                raise w.WorkflowError('exact queue preparation request materialization required')
            readset.request=request;readset.queue_bound=True
        proof=(_QueueSourceProof(_QUEUE_PROOF_SEAL,root,snapshot,request,capture[0],sql_observation,request_pin,prepared_pin)
               if capture and capture[0].get('continuation_input',{}).get('schema')=='same-original-PUB-after-receipt-lock-continuation-source/v1' else None)
        prior=[e for e in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS,where={'task_id':task})if e.get('task_id')==task
               and e.get('details',{}).get('collaboration_queue_intent',{}).get('action_id')==request['action_id']]
        if prior:raise w.WorkflowError('original queue intent exists; read original effect, never resend')
        keys=_QUEUE_ROUTE_KEYS
        checked=w._parse_observed_at(policy.get('checked_at'))
        if not checked or not 0<=(w._parse_observed_at(w.utc_timestamp())-checked).total_seconds()<=300:
            raise w.WorkflowError('fresh normal queue policy required before enqueue')
        refreshed = None
        if fresh_observation is not None:
            if proof is not None or after_lock:
                raise w.WorkflowError('a distinct authenticated source mode cannot substitute refreshed identities')
            refreshed = _refresh_material_queue_observation(root, request, source, target, fresh_observation)
        thin={k:request.get(k)for k in keys}
        if proof:
            token=_ACTIVE_QUEUE_PROOF.set(proof)
            try: reasons=collaboration_route(root,snapshot,thin,_queue_proof=proof,_queue_request=request)
            finally: _ACTIVE_QUEUE_PROOF.reset(token)
        elif refreshed:
            reasons = collaboration_route(root, snapshot, thin, _refreshed_live_pin=refreshed['live'])
        else: reasons=collaboration_route(root,snapshot,thin)
        if reasons!=[]:
            raise w.WorkflowError('fresh normal official queue route required before enqueue: '+str(reasons))
        validation=w._VALIDATION_CONTEXT.get()
        if validation is not None:validation.recheck()
        if _MATERIAL_QUEUE_SOURCE_MEMO.get() is not None:
            from paid_three_page_bounded_cms import _historical_proofs_recheck
            _historical_proofs_recheck(validation)
        _queue_commit_freshness(root,snapshot,request,policy,refreshed=refreshed)
        if proof:
            token=_ACTIVE_QUEUE_PROOF.set(proof)
            try: proof.verify(root,snapshot,thin,request,commit=True)
            finally: _ACTIVE_QUEUE_PROOF.reset(token)
            from department_autonomy import _owner_message_transport_not_started
            _owner_message_transport_not_started(root,snapshot,request)
            if validation is not None: validation.recheck()
            _queue_commit_freshness(root,snapshot,request,policy)
            token=_ACTIVE_QUEUE_PROOF.set(proof)
            try: proof.verify(root,snapshot,thin,request)
            finally: _ACTIVE_QUEUE_PROOF.reset(token)
        if actual_dir.exists():raise w.WorkflowError('existing original queue directory: read effect')
        actual_dir.mkdir(parents=True)
        if refreshed:
            w.atomic_write_json(actual_dir / 'native-queue-freshness.json', refreshed)
        intent={'action_id':request['action_id'],'request':request_pin,'prepared':prepared_pin,
                'directory':directory,'payload':request['payload'],'policy_decision_id':policy['decision_id'],
                'target_thread_id':target['thread_id'],'accepted_is_received':False}
        w.append_workflow_event(root,task,snapshot['current_state'],{'collaboration_queue_intent':intent,
                                'external_permission_issued':False})
    # The durable reservation remains even on disconnect/unknown output.
    result=OfficialQueueTransport(root,None).enqueue({'directory':actual_dir,'thread_id':target['thread_id'],
        'message':w.safe_path(root,request['payload']['path']).read_bytes().decode('utf-8'),
        'payload_sha256':request['payload_sha256'],'policy_decision_id':policy['decision_id']})
    return {'state':'queue_accepted','message_id':result['message_id'],'thread_id':target['thread_id'],
            'policy_decision_id':policy['decision_id'],'payload_sha256':request['payload_sha256'],
            'received':False,'sent_or_mcp_claimed':False}


def _collaboration_queue_subprocess_source(root, call, argv, turn, queue_start, queue_finish):
    """Read the bounded static subprocess wrapper, never execute its source.

    Both the complete AST and emitted argv/cwd/times must bind the same normal
    CLI. Arbitrary Python, shell tails, extra calls and partial output reject.
    """
    import ast
    import hashlib
    native_command=call.get('command','')
    material_prepare_and_queue = {
        'exec-ad49bda9-9967-4ec9-99ab-de6211f59283': 'dfad3a1cf16d5340892e509158dc49751713adb6ab4e077cce757f5efba92a2e',
        'exec-fd7b517c-06bd-47f9-9257-da04c93b7302': '48caf563b3c057c761df6b84bde24bfaf216e72a3a1f3552ee92227ab21d224b',
    }
    if material_prepare_and_queue.get(call.get('id')) == hashlib.sha256(native_command.encode()).hexdigest():
        # The original publisher ran an exact prepare-then-enqueue shell.
        # Accept its recorded output only for its actual trailing CLI.
        shell=shlex.split(native_command)
        tail=shlex.split(shell[2].rsplit(' && ',1)[-1])
        if len(tail)!=10 or tail[1:]!=['-B',*argv]:
            raise w.WorkflowError('exact original material prepare-and-queue CLI required')
        output=json.loads(w._source_continuation_execution_output(call),object_pairs_hook=_queue_unique_fields)
        return {'parts':tail,'output':output,'source_format':'exact_original_material_prepare_then_queue'}
    parts=shlex.split(call.get('command',''))
    if len(parts)!=3 or parts[:2]not in (['/bin/zsh','-lc'],['zsh','-lc']):return None
    body=parts[2]
    marker=re.search(r"<<'([A-Za-z_][A-Za-z_0-9]*)'\n",body)
    if marker is None:return None
    prefix=shlex.split(body[:marker.start()]);tail=body[marker.end():];ending='\n'+marker[1]
    if not tail.rstrip().endswith(ending):raise w.WorkflowError('exact static queue wrapper heredoc required')
    script=tail.rstrip()[:-len(ending)]
    if prefix and prefix[0]in {'env','/usr/bin/env'}:prefix.pop(0)
    allowed={'PYTHONDONTWRITEBYTECODE=1','PYTHONPATH=.:tools','PYTHONPATH='+str(Path(root))+':'+str(Path(root)/'tools')};seen=set()
    while prefix and prefix[0]in allowed:
        name=prefix.pop(0).split('=',1)[0]
        if name in seen:raise w.WorkflowError('duplicate static wrapper environment')
        seen.add(name)
    if prefix==['python3','-']:
        return _collaboration_compact_queue_wrapper(root,script,call,argv,turn,queue_start,queue_finish)
    if len(prefix)!=3 or prefix[1:]!=['-B','-']:raise w.WorkflowError('exact original Python wrapper interpreter required')
    interpreter=prefix[0]
    try:
        if isinstance(ast.parse(script).body[3].value,ast.Call):
            return _collaboration_relative_queue_wrapper(root,script,call,argv,turn,queue_start,queue_finish,interpreter)
    except (SyntaxError,IndexError,AttributeError):
        raise w.WorkflowError('exact static original queue subprocess AST required')
    # AST matching is a structural allowlist. No eval, exec, subprocess or
    # dynamic expression from the stored command is called by this reader.
    try:
        tree=ast.parse(script)
        node=tree.body[10]
        output_name=node.items[0].context_expr.func.value.right.value
        newline=node.body[1].value.args[0].value
        if (len(tree.body)!=12 or not isinstance(output_name,str)or Path(output_name).name!=output_name
                or not output_name.endswith('.json')or not isinstance(newline,str)
                or newline not in {'\n','\\n','\\\\n'}):raise ValueError('unknown wrapper output structure')
        request=Path(argv[3]);prepared=Path(argv[5]);directory=argv[7]
        if request.parent!=prepared.parent:raise ValueError('same original request/prepared directory required')
        expected=f"""from pathlib import Path
import subprocess,json,datetime
r=Path({str(Path(root).resolve())!r})
d=r/{str(request.parent)!r}
out={directory!r}
assert not(r/out).exists()
cmd=[{interpreter!r},'-B','tools/goal_source_recovery.py','queue-collaboration','--request',str((d/{request.name!r}).relative_to(r)),'--prepared',str((d/{prepared.name!r}).relative_to(r)),'--directory',out]
start=datetime.datetime.now(datetime.timezone.utc).isoformat()
p=subprocess.run(cmd,cwd=r,capture_output=True,text=True)
j={{'argv':cmd,'started_at':start,'completed_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'exit_code':p.returncode,'stdout':p.stdout,'stderr':p.stderr}}
with(d/{output_name!r}).open('x')as f:
 json.dump(j,f,ensure_ascii=False,indent=2)
 f.write({newline!r})
print(json.dumps(j,ensure_ascii=False))
"""
        if ast.dump(tree,include_attributes=False)!=ast.dump(ast.parse(expected),include_attributes=False):raise ValueError('not the static original queue wrapper')
    except (SyntaxError,ValueError,IndexError,TypeError,AttributeError)as error:
        raise w.WorkflowError('exact static original queue subprocess AST required')from error
    def unique(pairs):
        value={}
        for key,item in pairs:
            if key in value:raise w.WorkflowError('ambiguous queue wrapper output field')
            value[key]=item
        return value
    if turn.get('status')!='completed' or turn.get('error'):raise w.WorkflowError('actual completed original wrapper turn required')
    value=json.loads(w._source_continuation_execution_output(call),object_pairs_hook=unique)
    started,finished=(w._parse_observed_at(value.get(k))for k in ('started_at','completed_at'))
    expected_argv=[interpreter,'-B',*argv]
    if (set(value)!={'argv','started_at','completed_at','exit_code','stdout','stderr'}or value.get('argv')!=expected_argv
            or type(value.get('exit_code'))is not int or value['exit_code']!=0 or value.get('stderr')!=''
            or not isinstance(value.get('stdout'),str)or not value['stdout'].strip()or not started or not finished
            or not turn.get('startedAt',float('inf'))<=started.timestamp()
            or not started<=queue_start<=queue_finish<=finished
            or finished.timestamp()>w._parse_observed_at(w.utc_timestamp()).timestamp()+1
            or turn.get('status')=='completed'and finished.timestamp()>turn.get('completedAt',0)+1):
        raise w.WorkflowError('complete successful original wrapper argv/output/time required')
    output=json.loads(value['stdout'],object_pairs_hook=unique)
    if not isinstance(output,dict):raise w.WorkflowError('one complete original queue output object required')
    return {'parts':[interpreter,*argv],'output':output,'source_format':'static_python_subprocess_wrapper'}


def _collaboration_compact_queue_wrapper(root, script, call, argv, turn, queue_start, queue_finish):
    """Authenticate the original compact wrapper as static evidence, never execute it."""
    import ast
    def unique(pairs):
        value={}
        for key,item in pairs:
            if key in value:raise w.WorkflowError('ambiguous queue wrapper output field')
            value[key]=item
        return value
    try:
        value=json.loads(w._source_continuation_execution_output(call),object_pairs_hook=unique)
        command=value['command']; interpreter=command[0]
        if not isinstance(interpreter,str) or command!=[interpreter,'-B',*argv]:raise ValueError('wrong inner argv')
        tree=ast.parse(script)
        output_name=tree.body[4].value.right.value
        if not isinstance(output_name,str) or Path(output_name).name!=output_name or not output_name.endswith('.json'):
            raise ValueError('invalid output name')
        request=Path(argv[3]);prepared=Path(argv[5]);directory=argv[7]
        if request.parent!=prepared.parent:raise ValueError('wrong request directory')
        expected=f'''from pathlib import Path
import subprocess,json,datetime,os
r=Path.cwd();d=r/{str(request.parent)!r};o=d/{output_name!r};assert not o.exists();cmd=[{interpreter!r},'-B','tools/goal_source_recovery.py','queue-collaboration','--request',str((d/{request.name!r}).relative_to(r)),'--prepared',str((d/{prepared.name!r}).relative_to(r)),'--directory',{directory!r}];env=os.environ.copy();env['PYTHONPATH']='.:tools';x=subprocess.run(cmd,cwd=r,env=env,capture_output=True,text=True);v={{'at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'command':cmd,'exit_code':x.returncode,'stdout':x.stdout,'stderr':x.stderr}};o.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\\n');print(json.dumps(v,ensure_ascii=False)[:5000])
'''
        if ast.dump(tree,include_attributes=False)!=ast.dump(ast.parse(expected),include_attributes=False):raise ValueError('unexpected wrapper AST')
        at=w._parse_observed_at(value.get('at_utc'))
        if (set(value)!={'at_utc','command','exit_code','stdout','stderr'} or type(value['exit_code']) is not int
            or value['exit_code']!=0 or value['stderr']!='' or not isinstance(value['stdout'],str)
            or not at or not queue_start<=queue_finish<=at
            or turn.get('status')!='completed' or turn.get('error')
            or not isinstance(turn.get('startedAt'),(int,float)) or not isinstance(turn.get('completedAt'),(int,float))
            or turn['startedAt']>queue_start.timestamp() or at.timestamp()>turn['completedAt']+1
            or at.timestamp()>w._parse_observed_at(w.utc_timestamp()).timestamp()+1):raise ValueError('invalid actual chronology')
        output=json.loads(value['stdout'],object_pairs_hook=unique)
        if not isinstance(output,dict):raise ValueError('missing output')
    except (KeyError,IndexError,TypeError,ValueError,SyntaxError,AttributeError) as error:
        raise w.WorkflowError('exact completed compact original wrapper AST/output/time required') from error
    return {'parts':[interpreter,*argv],'output':output,'source_format':'static_compact_queue_wrapper'}


def _collaboration_relative_queue_wrapper(root,script,call,argv,turn,queue_start,queue_finish,interpreter):
    """Authenticate the observed relative-path wrapper; never run stored code."""
    import ast
    def unique(pairs):
        result={}
        for key,value in pairs:
            if key in result:raise w.WorkflowError('ambiguous queue wrapper output field')
            result[key]=value
        return result
    try:
        tree=ast.parse(script);output_name=tree.body[4].value.right.value
        request=Path(argv[3]);prepared=Path(argv[5]);directory=argv[7]
        if request.parent!=prepared.parent or not isinstance(output_name,str)or Path(output_name).name!=output_name or not output_name.endswith('.json'):
            raise ValueError('exact original paths required')
        expected=f'''from pathlib import Path
import subprocess,json,os,datetime
r=Path.cwd();d=Path({str(request.parent)!r});o=d/{output_name!r};assert not o.exists();cmd=[{interpreter!r},'-B','tools/goal_source_recovery.py','queue-collaboration','--request',str(d/{request.name!r}),'--prepared',str(d/{prepared.name!r}),'--directory',{directory!r}];env=os.environ.copy();env['PYTHONPATH']='.:tools';x=subprocess.run(cmd,cwd=r,env=env,capture_output=True,text=True);z={{'at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'command':cmd,'exit_code':x.returncode,'stdout':x.stdout,'stderr':x.stderr}};o.write_text(json.dumps(z,ensure_ascii=False,indent=2)+'\\n');print(json.dumps(z,ensure_ascii=False)[:4000])
'''
        if ast.dump(tree,include_attributes=False)!=ast.dump(ast.parse(expected),include_attributes=False):raise ValueError('unexpected wrapper AST')
        value=json.loads(w._source_continuation_execution_output(call),object_pairs_hook=unique)
        at=w._parse_observed_at(value.get('at_utc'))
        if (set(value)!={'at_utc','command','exit_code','stdout','stderr'} or value['command']!=[interpreter,'-B',*argv]
            or type(value['exit_code']) is not int or value['exit_code']!=0 or value['stderr']!=''
            or not isinstance(value['stdout'],str) or not at or not queue_start<=queue_finish<=at
            or turn.get('status')!='completed' or turn.get('error')
            or type(turn.get('startedAt'))not in {int,float} or type(turn.get('completedAt'))not in {int,float}
            or turn['startedAt']>queue_start.timestamp() or at.timestamp()>turn['completedAt']+1
            or at.timestamp()>w._parse_observed_at(w.utc_timestamp()).timestamp()+1):raise ValueError('invalid original chronology')
        output=json.loads(value['stdout'],object_pairs_hook=unique)
        if not isinstance(output,dict):raise ValueError('original output required')
    except (KeyError,IndexError,TypeError,ValueError,SyntaxError,AttributeError)as error:
        raise w.WorkflowError('exact completed relative original wrapper AST/output/time required')from error
    return {'parts':[interpreter,*argv],'output':output,'source_format':'static_relative_queue_wrapper'}


def collaboration_queue_source(root, snapshot, record):
    """Read genuine CLI/accepted effect, then exact native user/ACK and final independently."""
    from goal_delivery_runtime import _collaboration_native,_collaboration_final_message
    request,prepared,policy,source,target=_collaboration_queue_preparation(root,snapshot,
        record.get('original_prepare_request'),record.get('original_prepare_result'))
    for k in ('task_id','action_id','scope','payload_sha256','target_thread_id'):
        if record.get(k)!=request.get(k):raise w.WorkflowError('exact queue record/action identity required')
    if record.get('source_kind')!='official_native_queue' or record.get('policy_decision_id')!=policy['decision_id']:
        raise w.WorkflowError('actual official queue policy and source kind required')
    status=record.get('status')
    if status not in {'queue_accepted','message_received','result_received'}:
        raise w.WorkflowError('queue acceptance is not sent/received/completed')
    intent=_strict_queue_document(root,record.get('actual_queue_intent'))
    result=_strict_queue_document(root,record.get('actual_queue_result'))
    expected={'thread_id':target['thread_id'],'payload_sha256':request['payload_sha256'],
              'policy_decision_id':policy['decision_id'],'transport':'official_codex_queue','intake_claimed':False}
    match=re.fullmatch(r'Queued message ([0-9a-f-]{36}) for thread ([0-9a-f-]{36})\.\s*',result.get('stdout',''))
    start,finish,checked=(w._parse_observed_at(x)for x in (result.get('started_at'),result.get('finished_at'),policy.get('checked_at')))
    if (any(intent.get(k)!=v or result.get(k)!=v for k,v in expected.items())
            or intent.get('started_at')!=result.get('started_at') or result.get('exit_code')!=0
            or type(result.get('exit_code'))is not int or result.get('stderr')!='' or not match
            or match[1]!=record.get('queue_message_id') or match[2]!=target['thread_id']
            or not start or not finish or not checked or not checked<=start<=finish<=w._parse_observed_at(w.utc_timestamp())+__import__('datetime').timedelta(seconds=1) or (start-checked).total_seconds()>300):
        raise w.WorkflowError('exact successful original official queue effect and chronology required')
    qdir=str(Path(record['actual_queue_result']['path']).parent)
    if record['actual_queue_intent']['path']!=qdir+'/native-queue-intent.json' or record['actual_queue_result']['path']!=qdir+'/native-queue-result.json':
        raise w.WorkflowError('same original queue directory required')
    reservation_events = w.read_jsonl(Path(root) / w.WORKFLOW_EVENTS, where={
        'task_id': snapshot['task_id'],
        ('details', 'collaboration_queue_intent', 'action_id'): record['action_id'],
    })
    reservations = [event['details']['collaboration_queue_intent'] for event in reservation_events]
    frozen={'action_id':record['action_id'],'request':record['original_prepare_request'],
            'prepared':record['original_prepare_result'],'directory':qdir,'payload':request['payload'],
            'policy_decision_id':policy['decision_id'],'target_thread_id':target['thread_id'],'accepted_is_received':False}
    if reservations!=[frozen]:raise w.WorkflowError('one original durable official queue intent required')
    page=_collaboration_native(root,record.get('actual_native_invocation'))
    if any(page.get('thread',{}).get(k)!=source.get(v)for k,v in {'id':'task_id','title':'title','cwd':'cwd'}.items()):
        raise w.WorkflowError('actual original owner queue invocation identity required')
    calls=[(t,c)for t in page.get('turns',[])for c in t.get('items',[])if c.get('id')==record.get('queue_command_id')]
    if len(calls)!=1:raise w.WorkflowError('one real original owner queue command required')
    turn,call=calls[0]
    argv=['tools/goal_source_recovery.py','queue-collaboration','--request',record['original_prepare_request']['path'],
          '--prepared',record['original_prepare_result']['path'],'--directory',qdir]
    freshness_path = w.safe_path(root, qdir + '/native-queue-freshness.json')
    if freshness_path.is_file():
        freshness = _strict_queue_document(root, w.file_digest(root, qdir + '/native-queue-freshness.json'))
        fresh = _strict_queue_document(root, freshness['fresh_request'])
        live = _strict_queue_document(root, freshness['live'])
        observed = w._parse_observed_at(freshness['observed_at'])
        same_keys = set(request) - {'actual_sender_state', 'actual_target_state', 'actual_live_inventory', 'live_observed_at'}
        if (request['action_id'] not in _MATERIAL_FRESH_QUEUE_ACTIONS
                or set(fresh) != set(request) or any(fresh[key] != request[key] for key in same_keys)
                or not observed or not 0 <= (start-observed).total_seconds() <= 300
                or live.get('observed_at') != freshness['observed_at'] or fresh['live_observed_at'] != freshness['observed_at']
                or live.get('actual_native_observation') != fresh['actual_live_inventory']
                or live.get('actual_native_target_turns') != {request['target_thread_id']: fresh['actual_target_state']}):
            raise w.WorkflowError('same original queue freshness proof and actual dispatch chronology required')
        argv += ['--fresh-observation', freshness['fresh_request']['path']]
    wrapper=_collaboration_queue_subprocess_source(root,call,argv,turn,start,finish)
    parts=wrapper['parts']if wrapper else shlex.split(call.get('command',''))
    if len(parts)==3 and parts[:2]in (['/bin/zsh','-lc'],['zsh','-lc']):parts=shlex.split(parts[2])
    if parts and parts[0] in {'env','/usr/bin/env'}:parts.pop(0)
    allowed_environment={'PYTHONDONTWRITEBYTECODE=1', 'PYTHONPATH=.:tools',
                         'PYTHONPATH='+str(Path(root))+':'+str(Path(root)/'tools')}
    seen_environment=set()
    while parts and parts[0] in allowed_environment:
        key=parts[0].split('=',1)[0]
        if key in seen_environment:raise w.WorkflowError('ambiguous duplicate queue environment')
        seen_environment.add(key);parts.pop(0)
    if parts and len(parts)>1 and parts[1]=='-B':parts.pop(1)
    # Parse only the documented CLI; environment values and command strings are never executed.
    approved_python={Path(__import__('sys').executable).resolve(),Path('/usr/bin/python3').resolve(),
                     (Path.home()/'.local/bin/python3.11').resolve()}
    interpreter=parts[0] if parts else ''
    if (len(parts)!=len(argv)+1 or Path(interpreter).name not in {'python3','python3.11','python3.12'}
            or (('/' in interpreter) and Path(interpreter).resolve() not in approved_python) or parts[1:]!=argv
            or call.get('type')!='commandExecution' or not _selected_native_valid(call,statuses=('completed',))
            or call.get('exitCode')!=0 or type(call.get('exitCode'))is not int
            or not _selected_native_valid(turn,statuses=('inProgress','completed'))
            or Path(call.get('cwd','')).resolve()!=Path(root).resolve()
            or type(turn.get('startedAt'))not in {int,float} or turn['startedAt']>start.timestamp()
            or (turn.get('status')=='completed' and (type(turn.get('completedAt'))not in {int,float}or finish.timestamp()>turn['completedAt']+1))):
        raise w.WorkflowError('real successful same-owner exact queue CLI and time required')
    output=wrapper['output']if wrapper else json.loads(w._source_continuation_execution_output(call))
    if any(output.get(k)!=v for k,v in {'state':'queue_accepted','message_id':match[1],
            'thread_id':target['thread_id'],'policy_decision_id':policy['decision_id'],
            'payload_sha256':request['payload_sha256'],'received':False,'sent_or_mcp_claimed':False}.items()):
        raise w.WorkflowError('actual complete queue CLI output must bind original effect')
    state={'task_id':snapshot['task_id'],'action_id':record['action_id'],'department':request['target_department'],
           'threadId':target['thread_id'],'proof_state':'ACCEPTED','status':status,'approved_action':request,
           'queue_identity':w.sha256_value(frozen|{'message_id':match[1]}),'native_transport':record['actual_native_invocation'],
           'policy_decision_id':policy['decision_id'],'received':False,'proves_completion':False,'proves_next_action':False}
    if status=='queue_accepted':return state
    recipient=_collaboration_native(root,record.get('actual_native_recipient'))
    if any(recipient.get('thread',{}).get(k)!=target.get(v)for k,v in {'id':'thread_id','title':'title','cwd':'cwd'}.items()):
        raise w.WorkflowError('actual original recipient identity required')
    turns=[t for t in recipient.get('turns',[])if t.get('id')==record.get('recipient_turn_id')]
    if len(turns)!=1 or not _queue_receipt_turn_valid(turns[0]):raise w.WorkflowError('actual recipient turn required')
    received=turns[0];users=[(i,m)for i,m in enumerate(received.get('items',[]))if m.get('id')==record.get('recipient_message_id')and m.get('type')=='userMessage']
    acks=[(i,m)for i,m in enumerate(received.get('items',[]))if m.get('id')==record.get('ack_message_id')and m.get('type')=='agentMessage']
    body=w.safe_path(root,request['payload']['path']).read_bytes().decode('utf-8')
    if (len(users)!=1 or len(acks)!=1 or users[0][0]>=acks[0][0] or users[0][1].get('content')!=[{'type':'text','text':body}]
            or not _selected_native_valid(users[0][1]) or not _selected_native_valid(acks[0][1])
            or not str(acks[0][1].get('text','')).strip() or acks[0][1].get('phase')not in {'commentary','final_answer'}
            or type(received.get('startedAt'))not in {int,float} or not finish.timestamp()<=received['startedAt']<=w._parse_observed_at(w.utc_timestamp()).timestamp()+1):
        raise w.WorkflowError('real exact original body then nonempty recipient ACK after queue required')
    state.update(proof_state='RECEIVED',received=True,native_recipient=record['actual_native_recipient'])
    if status=='result_received':
        native=_collaboration_native(root,record.get('actual_native_result'))
        finals=[(t,m)for t in native.get('turns',[])for m in t.get('items',[])
                if m.get('id')==record.get('message_ref') and m.get('type')=='agentMessage']
        if (native.get('thread',{}).get('id')!=target['thread_id']or len(finals)!=1
                or not _selected_native_valid(finals[0][0],statuses=('completed',))
                or not _selected_native_valid(finals[0][1])
                or type(finals[0][0].get('startedAt'))not in {int,float}
                or type(finals[0][0].get('completedAt'))not in {int,float}
                or not received['startedAt']<=finals[0][0]['startedAt']<=finals[0][0]['completedAt']<=w._parse_observed_at(w.utc_timestamp()).timestamp()+1):
            raise w.WorkflowError('actual completed original recipient turn and exact final required')
        final=finals[0][1]
        reply=record.get('visible_reply',{});result_pin=record.get('result',{})
        if (final.get('id')!=record.get('message_ref')or final.get('phase')!='final_answer'
                or w.file_digest(root,reply.get('path',''))!=reply or not isinstance(final.get('text'),str)
                or w.safe_path(root,reply['path']).read_bytes()!=final['text'].encode('utf-8')
                or w.file_digest(root,result_pin.get('path',''))!=result_pin
                or w.read_json(w.safe_path(root,result_pin['path'])).get('task_id')!=snapshot['task_id']):
            raise w.WorkflowError('real independently completed exact final/result bytes required')
        state.update(proof_state='PROVEN',result=result_pin,visible_reply=reply,native_result=record['actual_native_result'])
    return state


def record_collaboration_queue(root, snapshot, record, pin):
    from goal_delivery_runtime import _collaboration_wait_states
    validation=w._VALIDATION_CONTEXT.get()
    if validation is None:raise w.WorkflowError('official queue receipt requires the normal request validation context')
    state=collaboration_queue_source(root,snapshot,record);goal=snapshot['goal_delivery']
    prior=goal.get('collaboration_records',[])
    if snapshot.get('current_state') in w.TERMINAL_STATES and pin not in prior:
        raise w.WorkflowError('terminal collaboration is historical read-only; no new receipt')
    if pin in prior:return {'result':'duplicate_ignored','status':state['status'],'parent_closed':False}
    current=next((s for s in _collaboration_wait_states(root,snapshot,only_action_id=record['action_id'])if s.get('action_id')==record['action_id']),None)
    rank={'queue_accepted':0,'message_received':1,'result_received':2}
    if ((current is None and state['status']!='queue_accepted')or(current is not None and
        (current.get('queue_identity')!=state['queue_identity']or rank.get(state['status'],-1)!=rank.get(current.get('status'),-2)+1))):
        raise w.WorkflowError('original accepted -> real recipient -> real result order; no replay/replacement')
    validation.recheck()
    snapshot['goal_delivery']={**goal,'collaboration_records':prior+[pin]}
    w.append_workflow_event(root,snapshot['task_id'],snapshot['current_state'],{'goal_delivery':snapshot['goal_delivery'],
         'collaboration_receipt':pin,'actual_transport_status':state['status'],'external_permission_issued':False})
    w.atomic_write_json(w.snapshot_path(root,snapshot['task_id']),snapshot)
    return {'result':'recorded','status':state['status'],'received':state['received'],'parent_closed':False,'does_not_grant_permission':True}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',default=str(Path(__file__).resolve().parents[1]))
    p.add_argument('command',choices=['recover-source','recover-queued-assignment',
                                      'prepare-message','record-technical-responsibility',
                                      'queue-oldhouse-technical','queue-collaboration','observe-post-qa-source'])
    p.add_argument('--input')
    p.add_argument('--request')
    p.add_argument('--prepared')
    p.add_argument('--directory')
    p.add_argument('--fresh-observation')
    p.add_argument('--identity-input-fifo')
    a=p.parse_args();root=Path(a.root).resolve()
    if a.command == 'queue-collaboration':
        if a.input or not all((a.request,a.prepared,a.directory)):
            p.error('exact request, prepared result and project queue directory required')
        result=queue_collaboration(root,a.request,a.prepared,a.directory,fresh_observation=a.fresh_observation)
    elif a.command == 'queue-oldhouse-technical':
        if a.input or not all((a.request,a.prepared,a.directory)):
            p.error('exact old-house queue request, prepared result and directory required')
        result=queue_oldhouse_technical(root,a.request,a.prepared,a.directory)
    elif not a.input:
        p.error('--input is required for this command')
    elif a.command == 'recover-queued-assignment':
        result = recover_queued_assignment(root, a.input)
    elif a.command == 'observe-post-qa-source':
        result = observe_post_qa_source_continuation(root,a.input)
    elif a.command == 'record-technical-responsibility':
        result = record_oldhouse_technical_source(root,a.input)
    else:
        result=record(root,a.input) if a.command=='recover-source' else prepare_message(
            root,w.read_json(w.safe_path(root,a.input)),identity_input_fifo=a.identity_input_fifo)
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__ == '__main__':
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    main()
