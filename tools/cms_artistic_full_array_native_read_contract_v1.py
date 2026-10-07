"""Exact new Artistic complete-array native-read control candidate.

No CMS/network/credential access. Inert until exact internal review/adoption.
Existing leaf requests and publishing/write permissions are independent.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path

TASK = 'fc-20260928-keyword-page-answer-implementation-v1'

ACTION = 'read-artistic-v7p2-full-array-source-projection-20261007'

SCOPE = 'flashcast.com.my:cms-native-read:services:artistic-coating:v7p2:exact-full-array-five-field-projection'

QA_TASK = 'fc-20261007-artistic-full-array-source-control-v1'

QA_ACTION = 'qa-artistic-full-array-source-control-v1-20261007'

QA_SCOPE = 'project:publishing:artistic-v7p2:exact-full-array-source-control:20261007'

QA_CANDIDATE = 'artistic-full-array-five-field-read-control-v1-20261007'

FIELDS = ['process_steps_en', 'process_steps_zh']

METADATA = ['id', 'slug', 'updated_at']

RECORD_ID = 'd862312d-d5f3-4bb7-9bf0-137ed71c87be'

PUBLISHER = '<LOCAL_TASK_ID>'

REQUEST_PATH = 'drafts/operations/fc-20261007-artistic-full-array-source-control-v1/artistic-full-array-five-field-read-control-v1-20261007/exact-native-read-request.json'

REQUEST_SHA256 = 'a14180a382dffea6ce4383cf04e1a99da7d34a228619573addca0990e875555a'

REQUEST_SIZE = 3357

EXPECTED_REQUEST = {'task_id': 'fc-20260928-keyword-page-answer-implementation-v1',
 'action_id': 'read-artistic-v7p2-full-array-source-projection-20261007',
 'action_class': 'cms_native_read',
 'scope': 'flashcast.com.my:cms-native-read:services:artistic-coating:v7p2:exact-full-array-five-field-projection',
 'department': 'publishing',
 'fixed_executor_chat_task_id': '<LOCAL_TASK_ID>',
 'table': 'services',
 'record_id': 'd862312d-d5f3-4bb7-9bf0-137ed71c87be',
 'slug': 'artistic-coating',
 'field_pointers': ['process_steps_en', 'process_steps_zh'],
 'metadata_fields': ['id', 'slug', 'updated_at'],
 'lookup': {'record_id_equals': 'd862312d-d5f3-4bb7-9bf0-137ed71c87be',
            'slug_equals': 'artistic-coating',
            'require_exactly_one_row': True},
 'read_only': True,
 'production_write_allowed': False,
 'protected_preview_allowed': False,
 'full_row_export_allowed': False,
 'credential_capture_allowed': False,
 'login_or_account_change_allowed': False,
 'source_method': 'existing_owner_signed_in_chrome_native_service_view',
 'current_values': 'NOT_READ',
 'candidate_version': 'artistic-full-array-five-field-read-control-v1-20261007',
 'require_raw_updated_at': True,
 'same_snapshot_required': True,
 'require_complete_native_arrays': True,
 'snapshot_contract': {'all_five_values_from_one_successful_native_read_response': True,
                       'arrays_returned_as_complete_native_column_values': True,
                       'preserve_json_types_nulls_array_order_and_all_elements_in_response': True,
                       'no_trim_filter_slice_default_coercion_date_roundtrip_or_key_reordering_before_evidence_hash': True,
                       'updated_at': 'retain exact source string including available PostgreSQL '
                                     'microseconds; do not convert through JavaScript Date',
                       'no_second_query_join_or_full_row_export': True},
 'source_plan': {'path': 'drafts/seo/fc-20260928-keyword-page-answer-implementation-v1/artistic-v7p2-full-array-hash-projection-source-plan-v2-20261006/exact-minimum-native-read-projection-v2.json',
                 'sha256': '018247872e4eea26c66675d90708f36ad583f6ca90f99432a3242384674cd5c2',
                 'size': 3234},
 'prerequisite_draft_qa': {'task_id': 'fc-20261007-cms-control-current-remaining-v1',
                           'action_id': 'qa-cms-control-current-remaining-v1-20261007',
                           'scope': 'project:operations:cms-control-current-remaining-v1:20261007',
                           'candidate_version': 'cms-control-current-rebase-and-artistic-contract-draft-v1-20261007',
                           'packet': {'path': 'logs/handoffs/2026-10-07-department-system-expansion/remaining-control-exact-QA1-packet-v1.json',
                                      'sha256': 'e422f271916284ec891cb97b485640e03aa17be4288bb494882e8854357dd02a',
                                      'size': 3524},
                           'source_pins': [{'path': 'drafts/operations/fc-20261007-cms-control-current-remaining-v1/cms-control-current-rebase-and-artistic-contract-draft-v1-20261007/candidate.json',
                                            'sha256': 'f9e57dc4cdcbdfdb05166a4ee4d75d653af0c462708237774d01ab1bfcbb4d09',
                                            'size': 14326},
                                           {'path': 'logs/department-outbox/fc-20261007-cms-control-current-remaining-v1-operations-assistant-cms-control-current-rebase-and-artistic-contract-draft-v1-20261007-v2.json',
                                            'sha256': '7e785d0ee40608878f46588f208a46f148d1f6402410bb8e15cadbbba3baa4e5',
                                            'size': 10179}]}}

DRAFT_QA_TASK = 'fc-20261007-cms-control-current-remaining-v1'

DRAFT_QA_ACTION = 'qa-cms-control-current-remaining-v1-20261007'

DRAFT_QA_SCOPE = 'project:operations:cms-control-current-remaining-v1:20261007'

DRAFT_QA_CANDIDATE = 'cms-control-current-rebase-and-artistic-contract-draft-v1-20261007'

DRAFT_QA_PACKET_PIN = {'path': 'logs/handoffs/2026-10-07-department-system-expansion/remaining-control-exact-QA1-packet-v1.json',
 'sha256': 'e422f271916284ec891cb97b485640e03aa17be4288bb494882e8854357dd02a',
 'size': 3524}

DRAFT_SOURCE_PINS = [{'path': 'drafts/operations/fc-20261007-cms-control-current-remaining-v1/cms-control-current-rebase-and-artistic-contract-draft-v1-20261007/candidate.json',
  'sha256': 'f9e57dc4cdcbdfdb05166a4ee4d75d653af0c462708237774d01ab1bfcbb4d09',
  'size': 14326},
 {'path': 'logs/department-outbox/fc-20261007-cms-control-current-remaining-v1-operations-assistant-cms-control-current-rebase-and-artistic-contract-draft-v1-20261007-v2.json',
  'sha256': '7e785d0ee40608878f46588f208a46f148d1f6402410bb8e15cadbbba3baa4e5',
  'size': 10179}]


def _same_typed(actual, expected) -> bool:
    """JSON booleans and integers are distinct; missing/extra keys are not aliases."""
    if type(actual) is not type(expected):
        return False
    if isinstance(expected, dict):
        return actual.keys() == expected.keys() and all(_same_typed(actual[k], v) for k, v in expected.items())
    if isinstance(expected, list):
        return len(actual) == len(expected) and all(_same_typed(a, e) for a, e in zip(actual, expected))
    return actual == expected


def validate_request(request: dict) -> list[str]:
    return [] if _same_typed(request, EXPECTED_REQUEST) else ['artistic_full_array_exact_request_and_types_required']


def _object_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate JSON request key')
        result[key] = value
    return result


def _non_json_number(value):
    raise ValueError('non-JSON numeric constant')


def check_binding(root: Path, binding: dict, task_id: str, action_id: str,
                  scope: str, department: str, payload_sha256: str) -> list[str]:
    expected = dict(task_id=TASK, action_id=ACTION, scope=SCOPE, department='publishing',
                    request_path=REQUEST_PATH, request_sha256=REQUEST_SHA256)
    identity = dict(task_id=task_id, action_id=action_id, scope=scope, department=department)
    if identity != {k: expected[k] for k in identity} or not _same_typed(binding, expected):
        return ['artistic_full_array_exact_binding_required']
    relative = Path(binding['request_path'])
    path = (root / relative).resolve()
    if relative.is_absolute() or not path.is_relative_to(root.resolve()) or not path.is_file():
        return ['artistic_full_array_request_missing_or_outside_project']
    try:
        raw = path.read_bytes()
        if len(raw) != REQUEST_SIZE or hashlib.sha256(raw).hexdigest() != REQUEST_SHA256 or payload_sha256 != REQUEST_SHA256:
            return ['artistic_full_array_exact_payload_required']
        request = json.loads(raw, object_pairs_hook=_object_pairs, parse_constant=_non_json_number)
        return validate_request(request)
    except (OSError, ValueError, TypeError):
        return ['artistic_full_array_request_unreadable_or_invalid_json']


def _contains_pin(value, pin: dict) -> bool:
    if isinstance(value, dict):
        return all(value.get(k) == v for k, v in pin.items()) or any(_contains_pin(v, pin) for v in value.values())
    return isinstance(value, list) and any(_contains_pin(v, pin) for v in value)


def _current_pins(workflow, root: Path, pins: list[dict]) -> bool:
    return all(workflow.file_digest(root, pin['path']) == pin for pin in pins)


def _verified_qa(workflow, root: Path, registered: dict, *, task: str, action: str,
                 scope: str, candidate: str, required_pins: list[dict]) -> bool:
    """Require exact current outbox in a real native chain, after dispatch+ACK.

    Reply metadata is audit evidence; legal caller identity is still an app gate.
    A previous action's verdict, a planning file or QA2 is never substituted.
    """
    if not _current_pins(workflow, root, required_pins):
        return False
    rows, invalid = workflow._validate_receipt_chain(root, task)
    if invalid:
        return False
    fixed_qa = registered['qa']['chat_binding']['task_id']
    matching = lambda row: all(row.get(k) == v for k, v in {'department': 'qa', 'action_id': action, 'scope': scope}.items())
    verdicts = [(i, row) for i, row in enumerate(rows) if row.get('receipt_type') == 'qa_verdict' and matching(row)]
    if not verdicts:
        return False
    verdict_index, verdict = verdicts[-1]
    if (verdict.get('verdict') != 'pass' or verdict.get('action_class') != 'internal_control_candidate'
            or verdict.get('chat_task_id') != fixed_qa):
        return False
    # A new exact review round invalidates reuse of an earlier PASS until its
    # own dispatch/ACK/outbox/verdict has completed. Do not inspect only history
    # preceding the chosen verdict and accidentally ignore newer work.
    if any(i > verdict_index and matching(row) and row.get('receipt_type') in
           {'dispatch_sent', 'dispatch_failed', 'chat_ack', 'outbox_received'}
           for i, row in enumerate(rows)):
        return False
    preceding = rows[:verdict_index]
    dispatches = [i for i, row in enumerate(preceding) if row.get('receipt_type') == 'dispatch_sent'
                  and matching(row) and row.get('chat_task_id') == fixed_qa]
    if not dispatches:
        return False
    dispatch_index = dispatches[-1]
    if any(i > dispatch_index and matching(row) and row.get('receipt_type') == 'dispatch_failed'
           for i, row in enumerate(rows)):
        return False
    acknowledgements = [i for i, row in enumerate(preceding) if i > dispatch_index
                        and row.get('receipt_type') == 'chat_ack' and matching(row)
                        and row.get('chat_task_id') == fixed_qa and row.get('ack_nonempty') is True]
    if not acknowledgements:
        return False
    ack_index = acknowledgements[-1]
    for index, receipt in enumerate(preceding):
        if index <= ack_index or receipt.get('receipt_type') != 'outbox_received' or not matching(receipt):
            continue
        times = [workflow._parse_observed_at(row.get('created_at')) for row in
                 (rows[dispatch_index], rows[ack_index], receipt, verdict)]
        now = workflow.dt.datetime.now(workflow.dt.timezone.utc)
        if any(t is None or t > now for t in times) or times != sorted(times):
            continue
        for pin in receipt.get('evidence', []):
            if not str(pin.get('path', '')).startswith('logs/department-outbox/'):
                continue
            if pin not in verdict.get('evidence', []) or workflow.file_digest(root, pin['path']) != pin:
                continue
            workflow.validate_outbox(root, [pin], 'qa', task)
            box = workflow.read_json(root / pin['path'])
            expected = {'task_id': task, 'department': 'qa', 'fixed_chat_task_id': fixed_qa,
                        'candidate_version': candidate, 'action_id': action, 'scope': scope,
                        'action_class': 'internal_control_candidate', 'qa_verdict': 'pass',
                        'production_write_allowed': False}
            if any(not _same_typed(box.get(k), v) for k, v in expected.items()):
                continue
            if any(key in box and box[key] is not False for key in
                   ('protected_preview_allowed', 'external_permission_issued', 'CMS_write_allowed', 'production_release_allowed')):
                continue
            reply = box.get('chat_reply')
            if not isinstance(reply, dict) or reply.get('nonempty') is not True:
                continue
            if (reply.get('thread_id') or reply.get('source_thread_id')) != fixed_qa:
                continue
            if not (reply.get('turn_id') or reply.get('source_turn_id')) or not (reply.get('message_id') or reply.get('source_message_id')):
                continue
            if not workflow.SHA256_PATTERN.fullmatch(str(reply.get('reply_sha256') or '')):
                continue
            if all(_contains_pin(box.get('evidence'), required) for required in required_pins):
                return True
    return False


def policy_reasons(root: Path, policy: dict, task_id: str, action_id: str,
                   scope: str, department: str, payload_sha256: str) -> list[str]:
    import workflow_control as workflow
    try:
        if not isinstance(policy, dict) or not isinstance(policy.get('exact_requests'), list):
            return ['artistic_full_array_exact_binding_required']
        expected = dict(task_id=task_id, action_id=action_id, scope=scope, department=department)
        matches = [x for x in policy['exact_requests'] if isinstance(x, dict)
                   and all(x.get(k) == v for k, v in expected.items())]
        if len(matches) != 1:
            return ['artistic_full_array_unique_exact_binding_required']
        reasons = check_binding(root, matches[0], task_id, action_id, scope, department, payload_sha256)
        if reasons:
            return reasons
        registered = workflow.department_registry(root)
        if registered['publishing']['chat_binding'].get('task_id') != PUBLISHER:
            return ['artistic_full_array_exact_fixed_publishing_executor_required']
        health = registered['publishing']['chat_binding']
        observed = workflow._parse_observed_at(health.get('last_health_check_at') or health.get('last_verified_at'))
        if observed is None or observed > workflow.dt.datetime.now(workflow.dt.timezone.utc):
            return ['artistic_full_array_current_fixed_health_required']
        if not workflow._chat_binding_healthy(registered['publishing']['chat_binding'], verification_ttl_hours=26):
            return ['artistic_full_array_current_fixed_health_required']
        if not _current_pins(workflow, root, [EXPECTED_REQUEST['source_plan']]):
            return ['artistic_full_array_frozen_full_array_source_plan_required']
        if not _current_pins(workflow, root, [DRAFT_QA_PACKET_PIN]):
            return ['artistic_full_array_frozen_draft_QA_packet_required']
        if not _verified_qa(workflow, root, registered, task=DRAFT_QA_TASK, action=DRAFT_QA_ACTION,
                            scope=DRAFT_QA_SCOPE, candidate=DRAFT_QA_CANDIDATE, required_pins=DRAFT_SOURCE_PINS):
            return ['artistic_full_array_prerequisite_exact_draft_QA_required']
        request_pin = dict(path=REQUEST_PATH, sha256=REQUEST_SHA256, size=REQUEST_SIZE)
        if not _verified_qa(workflow, root, registered, task=QA_TASK, action=QA_ACTION,
                            scope=QA_SCOPE, candidate=QA_CANDIDATE, required_pins=[request_pin]):
            return ['artistic_full_array_new_exact_control_QA_and_frozen_request_required']
        return []
    except (workflow.WorkflowError, OSError, ValueError, KeyError, TypeError, AttributeError):
        return ['artistic_full_array_control_evidence_invalid_or_missing']
