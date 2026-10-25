"""Recover real owner/native assignments, without fabricating dispatch or permission.

The existing workflow journal and assignment stack are the only state stores.
Historical transport proves what happened, never a new execution authorization.
"""
from __future__ import annotations
import argparse
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


def prepare_message(root, request):
    """The real preparation entry consumes authorization and exact policy checks."""
    if request.get('result_notification') is not None:
        # Delivery of an authenticated existing result is not a new business
        # assignment. Keep the original sender's notification lease/policy.
        import result_coordination as rc
        value=rc.exact_identity(request['result_notification'])
        if (request.get('delivery_mode')!='official_native_queue'
                or request.get('task_id')!=value['task_id']
                or request.get('sender_department')!=value['sender_department']):
            raise w.WorkflowError('exact original sender and admitted native result-notification mode required')
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
        declared=[x for x in original.get('collaboration_scopes',[]) if all(
            x.get(k)==request.get(k) for k in ('sender_department','target_department','scope'))]
        if (len(declared)!=1 or original.get('primary_owner')!=goal.get('primary_owner')
                or request['sender_department']!=original.get('primary_owner')
                or request['scope'] not in original.get('authorized_scope',[])
                or original.get('human_authorization')!=goal.get('human_authorization')):
            raise w.WorkflowError('exact original owner, human source and declared external collaboration required')
    if binding is None:
        external=w.read_json(Path(root)/'data/department-registry.json').get('collaboration_bindings',{}).get(request['target_department'])
        if not external or request['target_department'] not in {
                d.get('target_department') for d in w.read_json(w.snapshot_path(root,request['task_id']))
                .get('goal_delivery',{}).get('collaboration_scopes',[])}:
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
    if external_target:
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
              'target_sidebar_section_id':request['target_sidebar_section_id']}
        path=Path(root)/'logs/goal-delivery-observations'/request['task_id']/(w.sha256_value(live)+'.json')
        if not path.exists():w.atomic_write_json(path,live)
        live_pin=w.file_digest(root,str(path.relative_to(root)))
        with w.workflow_lock(root):
            snapshot=restore_goal(root,w.read_json(w.snapshot_path(root,request['task_id'])))
            goal=snapshot['goal_delivery'];observations={**goal.get('current_route_observations',{}),request['action_id']:live_pin}
            snapshot['goal_delivery']={**goal,'current_route_observations':observations}
            w.append_workflow_event(root,request['task_id'],snapshot['current_state'],
                {'goal_delivery':snapshot['goal_delivery'],'actual_route_observation':live_pin,'external_permission_issued':False})
            w.atomic_write_json(w.snapshot_path(root,request['task_id']),snapshot)
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


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',default=str(Path(__file__).resolve().parents[1]))
    p.add_argument('command',choices=['recover-source','recover-queued-assignment',
                                      'prepare-message','record-technical-responsibility',
                                      'queue-oldhouse-technical','observe-post-qa-source'])
    p.add_argument('--input')
    p.add_argument('--request')
    p.add_argument('--prepared')
    p.add_argument('--directory')
    a=p.parse_args();root=Path(a.root).resolve()
    if a.command == 'queue-oldhouse-technical':
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
        result=record(root,a.input) if a.command=='recover-source' else prepare_message(root,w.read_json(w.safe_path(root,a.input)))
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__ == '__main__': main()
