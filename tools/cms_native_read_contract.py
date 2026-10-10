"""Exact one-service CMS read validation; not an account or write permission.

This module is inert until the independently reviewed policy patch is activated.
It never contacts CMS, reads authentication, or changes policy by itself.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

TASK = 'fc-20260928-keyword-page-answer-implementation-v1'
ACTION = 'read-artistic-coating-v7p2-exact-native-source-v2-20261006'
SCOPE = 'flashcast.com.my:cms-native-read:services:artistic-coating:v7p2:two-step-descriptions'
QA_TASK = 'fc-20261006-v7p2-cms-native-read-control-v1'
QA_ACTION = 'qa-artistic-coating-exact-native-read-control-20261006'
QA_SCOPE = 'project:artistic-coating:cms-native-read-control-only:20261006'
FIELDS = []
METADATA = []


def validate_request(request: dict) -> list[str]:
    expected = {
        'task_id': TASK, 'action_id': ACTION, 'action_class': 'cms_native_read',
        'scope': SCOPE, 'department': 'content-organic-website',
        'table': 'services', 'slug': 'artistic-coating',
        'field_pointers': FIELDS, 'metadata_fields': METADATA,
        'lookup': {'slug_equals': 'artistic-coating', 'require_exactly_one_row': True},
        'read_only': True, 'production_write_allowed': False,
        'protected_preview_allowed': False, 'login_or_account_change_allowed': False,
        'credential_capture_allowed': False, 'full_row_export_allowed': False,
        'source_method': 'existing_owner_signed_in_chrome_native_service_view',
    }
    if not isinstance(request, dict) or any(request.get(k) != v for k, v in expected.items()):
        return ['cms_native_read_request_scope_or_method_invalid']
    return []


def check_binding(root: Path, binding: dict, task_id: str, action_id: str,
                  scope: str, department: str, payload_sha256: str) -> list[str]:
    expected = dict(task_id=TASK, action_id=ACTION, scope=SCOPE,
                    department='content-organic-website')
    actual = dict(task_id=task_id, action_id=action_id, scope=scope, department=department)
    if actual != expected or any(binding.get(k) != v for k, v in expected.items()):
        return ['cms_native_read_exact_binding_required']
    rel = Path(str(binding.get('request_path') or ''))
    path = (root / rel).resolve()
    if rel.is_absolute() or not path.is_relative_to(root.resolve()) or not path.is_file():
        return ['cms_native_read_request_missing_or_outside_project']
    raw = path.read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    if sha != binding.get('request_sha256') or payload_sha256 != sha:
        return ['cms_native_read_exact_payload_required']
    try:
        return validate_request(json.loads(raw))
    except (ValueError, TypeError):
        return ['cms_native_read_request_invalid_json']


def policy_reasons(root: Path, policy: dict, task_id: str, action_id: str,
                   scope: str, department: str, payload_sha256: str) -> list[str]:
    raise ValueError("public_template_has_no_native_authorization")
    import workflow_control as workflow
    bindings = policy.get('exact_requests', [])
    matches = [x for x in bindings if isinstance(x, dict) and all(x.get(k) == v for k, v in
        dict(task_id=task_id, action_id=action_id, scope=scope, department=department).items())]
    if len(matches) != 1:
        return ['cms_native_read_exact_binding_required']
    binding = matches[0]
    reasons = check_binding(root, binding, task_id, action_id, scope, department, payload_sha256)
    if reasons:
        return reasons
    registered = workflow.department_registry(root)
    if not workflow._chat_binding_healthy(registered[department]['chat_binding'],
                                          verification_ttl_hours=26):
        return ['cms_native_read_current_fixed_health_required']
    rows, invalid = workflow._validate_receipt_chain(root, QA_TASK)
    results = [x for x in rows if x.get('receipt_type') == 'qa_verdict'
               and x.get('department') == 'qa' and x.get('action_id') == QA_ACTION
               and x.get('scope') == QA_SCOPE]
    if invalid or not results or results[-1].get('verdict') != 'pass':
        return ['cms_native_read_exact_independent_control_QA_required']
    latest = results[-1]
    if latest.get('chat_task_id') != registered['qa']['chat_binding']['task_id']:
        return ['cms_native_read_fixed_QA_required']
    approved_request = {'path': binding['request_path'], 'sha256': binding['request_sha256'],
                        'size': (root / binding['request_path']).stat().st_size}
    exact_outbox = False
    for receipt in rows:
        if (receipt.get('receipt_type') != 'outbox_received' or receipt.get('department') != 'qa'
                or receipt.get('action_id') != QA_ACTION or receipt.get('scope') != QA_SCOPE):
            continue
        for pin in receipt.get('evidence', []):
            if not str(pin.get('path', '')).startswith('logs/department-outbox/'):
                continue
            try:
                workflow.validate_outbox(root, [pin], 'qa', QA_TASK)
                outbox = json.loads((root / pin['path']).read_text())
                if (outbox.get('action_id') == QA_ACTION and outbox.get('scope') == QA_SCOPE
                        and outbox.get('qa_verdict') == 'pass'
                        and approved_request in outbox.get('evidence', [])
                        and outbox.get('production_write_allowed') is False):
                    exact_outbox = True
            except (ValueError, OSError, KeyError, TypeError):
                continue
    return [] if exact_outbox else ['cms_native_read_frozen_request_in_verified_QA_outbox_required']
