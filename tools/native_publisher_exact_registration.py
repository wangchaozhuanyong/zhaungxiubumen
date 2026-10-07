"""Three pinned publisher handover tuples; registration is never a permit."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

PROJECT = '<LOCAL_PROJECT_ID>'
PUBLISHER = '<LOCAL_TASK_ID>'
BUSINESS_TASK = 'fc-20260928-keyword-page-answer-implementation-v1'
MANIFEST = 'drafts/operations/fc-20261005-publishing-exact-executor-handover-control-v1/publisher-postdeploy-three-row-staged-control-v2-20261006/candidate.json'
MANIFEST_SHA = '091dbf92cd0a2953f15b772fae73e201d8cb12ab53588a3d7fd5472e07f7a870'
EXACT_ROWS = {
    'v17': ('services', 'example-cms-record-1', 'old-house', ('faqs_en', 'faqs_zh')),
    'v18': ('blog_posts', 'example-cms-record-2', 'renovation-quotation-checklist-malaysia', ('content_en', 'content_zh')),
    'v20': ('services', 'example-cms-record-3', 'design', ('faqs_en', 'faqs_zh')),
}


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def pinned(root, pin):
    root = root.resolve()
    rel = Path(pin['path'])
    path = (root / rel).resolve()
    require(not rel.is_absolute() and path.is_relative_to(root) and path.is_file(), 'project-local pin required')
    raw = path.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == pin['sha256'], 'frozen pin changed')
    require('size' not in pin or len(raw) == pin['size'], 'frozen size changed')
    return json.loads(raw)


def value_sha(value):
    raw = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(raw.encode()).hexdigest()


def pointer(value, path):
    for key in path.strip('/').split('/'):
        value = value[key]
    return value


def load_publisher_exact_registration(root):
    root = root.resolve()
    manifest = pinned(root, {'path': MANIFEST, 'sha256': MANIFEST_SHA})
    require(manifest['project_id'] == PROJECT
            and manifest['mode'] == 'REGISTRATION_ONLY_NO_ACTIVE_PATCH_NO_PERMIT'
            and manifest['registration_applied'] is False
            and manifest['production_write_allowed'] is False
            and manifest['old_permits_inherited'] is False, 'registration cannot grant authority')
    pinned(root, manifest['source_outbox'])
    pinned(root, manifest['source_requests'])
    entries = manifest['entries']
    require(len(entries) == 3 and {x['item'] for x in entries} == set(EXACT_ROWS), 'exact three targets only')
    targets = {}
    for entry in entries:
        label = entry['item']
        table, record_id, slug, keys = EXACT_ROWS[label]
        native = entry['actual_native_target']
        owner = entry['proposed_executor']
        require(owner == {'department': 'publishing', 'chat_task_id': PUBLISHER,
                          'project_id': PROJECT, 'cwd': str(root)}, 'exact publisher identity required')
        require(entry['original_business_task_id'] == BUSINESS_TASK
                and (native['table'], native['record_id'], native['slug']) == (table, record_id, slug)
                and native['status'] == 'published' and type(native['version']) is int,
                'exact original task and native row required')
        require([f['native_storage_key'] for f in entry['changed_fields']] == list(keys), 'exact bilingual fields required')
        scope = f'flashcast.com.my:{table}:{record_id}:{",".join(keys)}'
        cv = f'{label}-exact-publishing-native-v2-20261006'
        action = f'publish-{cv}'
        require(entry['future_precise_write_scope'] == scope
                and entry['future_precise_write_action_id'] == action
                and entry['future_precise_write_candidate_version'] == cv,
                'exact future tuple required')
        require(all(entry[k] is False for k in ('source_content_changed', 'registration_applied',
                                              'production_write_allowed', 'permit_issued')), 'no permission upgrade')
        request = pinned(root, entry['source_request_pin'])
        frozen = pinned(root, entry['original_frozen_candidate'])
        require(request['proposed_executor'] == owner
                and request['actual_native_target'] == native
                and request['original_business_task_id'] == BUSINESS_TASK
                and request['old_permits_inherited'] is False
                and request['permission_issued_or_consumed'] is False
                and request['production_write_allowed'] is False,
                'source request cannot broaden execution')
        for field, source in zip(entry['changed_fields'], request['field_source_and_values']):
            before = pinned(root, field['actual_native_source'])['record'][field['native_storage_key']]
            frozen_before = pointer(frozen, field['original_before']['candidate_pointer'])
            frozen_after = pointer(frozen, field['original_after']['candidate_pointer'])
            if field['native_storage_key'].startswith('faqs_'):
                frozen_before = [{'q': f['question'], 'a': f['answer']} for f in frozen_before]
                frozen_after = [{'q': f['question'], 'a': f['answer']} for f in frozen_after]
            require(before == frozen_before == source['raw_native_before']
                    and frozen_after == source['proposed_native_after']
                    and value_sha(before) == field['current_native_before_sha256']
                    and value_sha(frozen_after) == field['proposed_native_after_sha256'],
                    'exact source schema mapping and values required')
        targets[cv] = {'task_id': BUSINESS_TASK, 'action_id': action, 'candidate_version': cv,
                       'scope': scope, 'record_id': record_id, 'slug': slug, 'table': table,
                       'content_type': 'blog' if table == 'blog_posts' else 'service',
                       'changed_fields': list(keys), 'expected_updated_at': native['updated_at'],
                       'observed_version': native['version'], 'execution_owner': 'publishing',
                       'execution_thread_id': PUBLISHER, 'candidate_shape': 'native_publisher_registration',
                       'candidate': (entry['source_request_pin']['path'], entry['source_request_pin']['sha256']),
                       'source_frozen_candidate': (entry['original_frozen_candidate']['path'], entry['original_frozen_candidate']['sha256']),
                       'rollback': (entry['changed_fields'][0]['actual_native_source']['path'], entry['changed_fields'][0]['actual_native_source']['sha256']),
                       'native_registration_only': True, 'release_ready': False, 'production_authorized': False,
                       'qa_outbox': None, 'rollback_allowed': False}
    return targets


def validate_publisher_registration_candidate(root, candidate, target):
    frozen = load_publisher_exact_registration(root).get(target.get('candidate_version'))
    require(frozen is not None and target == frozen, 'immutable registration tuple required')
    require(candidate == pinned(root, {'path': target['candidate'][0], 'sha256': target['candidate'][1]}),
            'exact publisher source request required')


def publisher_registration_reason(root, task_id, action_id, scope):
    rows = load_publisher_exact_registration(root)
    matches = [t for t in rows.values() if (t['task_id'], t['action_id'], t['scope']) == (task_id, action_id, scope)]
    return ('publisher_exact_registration_pending_production_gates' if len(matches) == 1
            else 'publisher_tuple_not_registered')
