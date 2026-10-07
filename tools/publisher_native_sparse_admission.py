"""Exact three-row publisher sparse candidates; local binding is not a permit.

The existing issuer must still validate fixed QA, AUTO_RELEASE, consumed policy,
fresh GitHub zero-write/OIDC evidence, backup, and protected single-use permits.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path('<PROJECT_ROOT>')
PROJECT = '<LOCAL_PROJECT_ID>'
PUBLISHER = '<LOCAL_TASK_ID>'
QA = '<LOCAL_TASK_ID>'
BUSINESS_TASK = 'fc-20260928-keyword-page-answer-implementation-v1'
CONTROL_TASK = 'fc-20261007-owner-publisher-execution-takeover-v1'
REWORK_TASK = 'fc-20261007-publisher-three-rollback-projection-rework-v1'
SHAPE = 'native_publisher_sparse_admission'
RUNTIME_TARGET_KEYS = set('id slug contentType table taskId actionId candidateVersion scope changedFields baselineProjectionFields baselineFieldsSha256 desiredFieldsSha256 expectedUpdatedAt rollbackFieldsSha256 retainedProjectionFields retainedFieldsSha256 rollbackAllowed requiresParentRun'.split())
CLI_TARGET_KEYS = set('taskId candidateVersion qaEvidenceVersion actionId actionClass scope recordId slug contentType table keyField exactPatchOnly rollbackAllowed expectedUpdatedAt status baselineProjectionFields baselineFieldsSha256 desiredFieldsSha256 rollbackFieldsSha256 changedFields desiredFields sourceCandidatePath sourceCandidateSha256 originalFrozenSourcePath originalFrozenSourceSha256 rollbackRecordPath rollbackRecordSha256 rollbackPackagePath rollbackPackageSha256 publicPaths retainedProjectionFields retainedFieldsSha256'.split())

SOURCE_INDEX_PIN = {
    'path': 'drafts/operations/fc-20261007-owner-publisher-execution-takeover-v1/publisher-production-readiness-control-v1-20261007/source-evidence-index.json',
    'sha256': '2ca189ea0a9245d43f87e3606afc40e62ef7ebcf0d654dd18c0c576b0542cae9',
}
EXACT = {
    'v17': ('services', 'example-cms-record-1', 'old-house', ['faqs_en', 'faqs_zh']),
    'v18': ('blog_posts', 'example-cms-record-2', 'renovation-quotation-checklist-malaysia', ['content_en', 'content_zh']),
    'v20': ('services', 'example-cms-record-3', 'design', ['faqs_en', 'faqs_zh']),
}
OLD_VERSIONS = {label + '-exact-publishing-native-v2-20261006' for label in EXACT}
EXECUTION_VERSIONS = {label: label + '-owner-publisher-native-preparation-v2-20261007' for label in EXACT}
SERVICE_PROJECTION = 'id slug status version updated_at faqs_zh faqs_en title_zh title_en excerpt_zh excerpt_en content_zh content_en image_url alt_zh alt_en suitable_for_zh suitable_for_en common_projects_zh common_projects_en scope_items_zh scope_items_en process_steps_zh process_steps_en seo_title_zh seo_title_en seo_description_zh seo_description_en'.split()
BLOG_PROJECTION = 'id slug status version updated_at content_zh content_en title_zh title_en excerpt_zh excerpt_en seo_title_zh seo_title_en seo_description_zh seo_description_en cover_image_url alt_zh alt_en published_at category tags sort_order'.split()
AUTH_TEXT = '我授权来给你处理这个事情，弄完了你跟总部汇报就行\n'


def require(ok: bool, reason: str) -> None:
    if not ok:
        raise ValueError(reason)


def canonical_sha(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':')).encode('utf-8')).hexdigest()


def field_sha(value: Any) -> str:
    return hashlib.sha256(value.encode('utf-8')).hexdigest() if isinstance(value, str) else canonical_sha(value)


def pin(root: Path, path: str) -> dict[str, Any]:
    rel = Path(path)
    actual = (root / rel).resolve()
    require(not rel.is_absolute() and root.resolve() in actual.parents and actual.is_file(), 'project-local evidence required')
    raw = actual.read_bytes()
    return {'path': rel.as_posix(), 'sha256': hashlib.sha256(raw).hexdigest(), 'size': len(raw)}


def pinned(root: Path, value: dict[str, Any]) -> dict[str, Any]:
    require(isinstance(value, dict) and set(value).issubset({'path', 'sha256', 'size'}), 'exact pin shape required')
    actual = pin(root, value['path'])
    require(actual['sha256'] == value['sha256']
            and ('size' not in value or actual['size'] == value['size']), 'evidence pin changed')
    data = json.loads((root / actual['path']).read_text(encoding='utf-8'))
    require(isinstance(data, dict), 'evidence JSON object required')
    return data


def pointer(value: Any, path: str) -> Any:
    for key in path.strip('/').split('/'):
        value = value[key]
    return value


def owner(root: Path, authorization_pin: dict[str, Any]) -> None:
    auth = pinned(root, authorization_pin)
    exact = {'type': 'NATIVE_OWNER_AUTHORIZATION', 'source_method': 'mcp__codex_app__read_thread',
             'source_thread_id': '<LOCAL_TASK_ID>', 'source_project_id': PROJECT,
             'source_cwd': str(ROOT), 'turn_id': '01a11596-1ea5-73a3-a895-45b59faa384c',
             'message_id': '01a11596-1eff-7fb1-83ac-0f1d938a12ec', 'authorized_sender': 'operations-assistant'}
    require(all(auth.get(k) == v for k, v in exact.items()) and auth.get('production_gates_waived') is False,
            'exact native owner authorization required')
    message = auth.get('user_message', {})
    require(message.get('type') == 'userMessage' and message.get('id') == exact['message_id']
            and message.get('content') == [{'type': 'text', 'text': AUTH_TEXT}], 'native authorization text changed')


def source_entries(root: Path) -> dict[str, dict[str, Any]]:
    require(root.resolve() == ROOT.resolve(), 'fixed project root required')
    index = pinned(root, SOURCE_INDEX_PIN)
    require(index.get('schema_version') == 'publisher_sparse_source_evidence_v1'
            and index.get('publisher_candidate_pins') is None
            and all(index.get(k) is False for k in ['release_ready', 'production_authorized', 'permit_issued']),
            'source observation is not release authority')
    owner(root, index['owner_authorization'])
    rows = index.get('entries', [])
    require(len(rows) == 3 and {x.get('item') for x in rows} == set(EXACT), 'exact three source targets required')
    result = {}
    for row in rows:
        label = row['item']
        table, record_id, slug, fields = EXACT[label]
        native = pinned(root, row['current_native_source'])
        old = pinned(root, row['old_proposed_request'])
        frozen = pinned(root, old['frozen_candidate'])
        before = native.get('record', {})
        projection = SERVICE_PROJECTION if table == 'services' else BLOG_PROJECTION
        require(native.get('source_method') == 'mcp__cua_repl:Network.getResponseBody'
                and native.get('response_status') == 200
                and native.get('owner_authorization_ref') == '01a11596-1eff-7fb1-83ac-0f1d938a12ec'
                and native.get('credential_or_header_capture') is False
                and native.get('production_write_performed') is False
                and native.get('projection') == projection and set(before) == set(projection),
                'actual complete native validation projection required')
        require(before.get('id') == record_id and before.get('slug') == slug and before.get('status') == 'published'
                and type(before.get('version')) is int and before['version'] > 0
                and re.fullmatch(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{6}\+00:00', str(before.get('updated_at', ''))),
                'exact row identity and microsecond CAS required')
        expected_owner = {'department': 'publishing', 'chat_task_id': PUBLISHER, 'project_id': PROJECT, 'cwd': str(ROOT)}
        target = old.get('actual_native_target', {})
        require(old.get('item') == label and old.get('original_business_task_id') == BUSINESS_TASK
                and old.get('proposed_executor') == expected_owner
                and all(old.get(k) is False for k in ['production_write_allowed', 'permission_issued_or_consumed', 'old_permits_inherited'])
                and type(target.get('version')) is int
                and (target.get('table'), target.get('record_id'), target.get('slug'), target.get('version'), target.get('updated_at'))
                == (table, record_id, slug, before['version'], before['updated_at']), 'old frozen source cannot grant new executor permission')
        source_fields = old.get('field_source_and_values', [])
        require([x.get('native_storage_key') for x in source_fields] == fields, 'two exact bilingual fields required')
        desired = {}
        for field in source_fields:
            key = field['native_storage_key']
            original_before = pointer(frozen, field['original_frozen_before']['candidate_pointer'])
            original_after = pointer(frozen, field['original_frozen_after']['candidate_pointer'])
            if key.startswith('faqs_'):
                original_before = [{'q': x['question'], 'a': x['answer']} for x in original_before]
                original_after = [{'q': x['question'], 'a': x['answer']} for x in original_after]
                require(all(set(x) == {'q', 'a'} and all(isinstance(x[k], str) for k in ['q', 'a']) for x in original_after)
                        and original_after[:-1] == original_before and len(original_after) == len(original_before) + 1,
                        'native FAQ q/a must append exactly one frozen item')
            else:
                require(isinstance(original_before, str) and isinstance(original_after, str), 'HTML must remain exact strings')
            require(before[key] == field['raw_native_before'] == original_before
                    and field['proposed_native_after'] == original_after
                    and field_sha(before[key]) == field['raw_native_before_sha256']
                    and field_sha(original_after) == field['proposed_native_after_sha256']
                    and before[key] != original_after, 'before drift or frozen after bytes changed')
            desired[key] = original_after
        retained = [key for key in projection if key not in set(fields) | {'version', 'updated_at'}]
        result[label] = {'source': row, 'native': native, 'old': old, 'before': before, 'desired': desired,
                         'projection': projection, 'retained': retained,
                         'hashes': {'baseline_fields_sha256': canonical_sha(before),
                                    'desired_fields_sha256': canonical_sha(desired),
                                    'rollback_fields_sha256': canonical_sha({k: before[k] for k in fields}),
                                    'retained_fields_sha256': canonical_sha({k: before[k] for k in retained})}}
    return result


def validate_execution_candidate(candidate: dict[str, Any], entry: dict[str, Any], source: dict[str, Any]) -> None:
    table, record_id, slug, fields = EXACT[entry['item']]
    before, desired = source['before'], source['desired']
    cv = entry['candidate_version']
    require(isinstance(cv, str) and cv == EXECUTION_VERSIONS[entry['item']] and cv not in OLD_VERSIONS
            and entry['action_id'] == 'publish-' + cv, 'new exact candidate/action required; old versions remain registration-only')
    scope = 'flashcast.com.my:' + table + ':' + record_id + ':' + ','.join(fields)
    exact = {'task_id': BUSINESS_TASK, 'action_id': entry['action_id'], 'candidate_version': cv, 'scope': scope,
             'table': table, 'record_id': record_id, 'slug': slug, 'changed_fields': fields,
             'execution_owner': 'publishing', 'execution_thread_id': PUBLISHER,
             'action_class': 'cms_content_candidate', 'execution_action_class': 'cms_write'}
    require(all(entry.get(k) == v for k, v in exact.items()), 'publisher admission exact tuple or field boundary changed')
    managed = {'taskId': BUSINESS_TASK, 'actionId': entry['action_id'], 'candidateVersion': cv,
               'scope': scope, 'operation': 'publish'}
    expected_owner = {'department': 'publishing', 'chat_task_id': PUBLISHER, 'project_id': PROJECT, 'cwd': str(ROOT)}
    native_target = {'table': table, 'record_id': record_id, 'slug': slug, 'status': 'published',
                     'observed_version': before['version'], 'expected_updated_at_raw': before['updated_at']}
    require(candidate.get('schema_version') == '1.0' and candidate.get('item') == entry['item']
            and candidate.get('task_id') == BUSINESS_TASK and candidate.get('preparation_task_id') == REWORK_TASK
            and candidate.get('candidate_version') == cv and candidate.get('proposed_managed_identity') == managed
            and candidate.get('actual_native_target') == native_target and candidate.get('execution_owner') == expected_owner
            and candidate.get('changed_fields') == fields and candidate.get('delivery_class') == 'cms_content_candidate'
            and candidate.get('risk_level') == 'R1' and candidate.get('publication_channel') == 'cms_content_candidate -> cms_write',
            'publisher candidate exact tuple, native row, owner or channel changed')
    require(type(candidate['actual_native_target'].get('observed_version')) is int,
            'observed version must be an integer, not a boolean')
    require(all(candidate.get(k) is False for k in ['production_write_allowed', 'old_permits_inherited', 'registration_applied', 'published', 'exact_action_issued'])
            and candidate.get('desired_fields') == desired and set(candidate['desired_fields']) == set(fields),
            'unpublished faithful two-field candidate required')
    require(entry.get('expected_updated_at') == before['updated_at']
            and type(entry.get('observed_version')) is int and entry['observed_version'] == before['version']
            and type(native_target['observed_version']) is int, 'CAS and observed version metadata changed')
    require(entry.get('baseline_projection_fields') == candidate.get('baseline_projection_fields') == source['projection']
            and entry.get('retained_projection_fields') == candidate.get('retained_projection_fields') == source['retained'],
            'complete published validation projection or retained fields changed')
    require(all(entry.get(k) == candidate.get(k) == v for k, v in source['hashes'].items()), 'named projection hashes differ')
    actual_request = pinned(ROOT, candidate['protected_dry_run_request_proposal'])
    sparse_record = {'id': record_id, **desired}
    if 'slug' in actual_request.get('record', {}):
        sparse_record['slug'] = slug  # Existing API permits the unchanged stable slug only.
    request = {'mode': 'dry-run', 'contentType': 'service' if table == 'services' else 'blog', 'nextStatus': 'published',
               'expectedUpdatedAt': before['updated_at'], 'record': sparse_record,
               'managedCandidate': {'taskId': BUSINESS_TASK, 'actionId': entry['action_id'], 'candidateVersion': cv,
                                    'scope': scope, 'operation': 'publish'}}
    require(actual_request == request,
            'existing request schema and exact id/unchanged-slug+two-fields sparse payload required')
    require(pinned(ROOT, candidate['sparse_patch']) == desired and candidate.get('before_fields') == {k: before[k] for k in fields},
            'exact sparse patch and before fields required')
    validation = {**before, **desired}
    validation_source = pinned(ROOT, candidate['validation_source'])
    require(validation_source.get('record') == before and validation_source.get('projection') == source['projection']
            and validation_source.get('retained_projection_fields') == source['retained']
            and validation_source.get('retained_fields_sha256') == source['hashes']['retained_fields_sha256']
            and set(validation) == set(source['projection'])
            and all(validation[k] == before[k] for k in set(source['projection']) - set(fields)),
            'internal validation projection must preserve every unmodified field')
    require(entry.get('current_native_source') == source['source']['current_native_source']
            and entry.get('old_proposed_request') == source['source']['old_proposed_request']
            and candidate.get('native_source') == source['source']['current_native_source']
            and candidate.get('historical_executor_request') == source['source']['old_proposed_request']
            and candidate.get('original_frozen_candidate') == source['old']['frozen_candidate']
            and candidate.get('original_frozen_after_transferred_without_rewriting') is True,
            'immutable before/after provenance changed')
    backup = pinned(ROOT, candidate['before_backup'])
    require(backup.get('record') == before and backup.get('projection') == source['projection']
            and backup.get('table') == table and backup.get('record_id') == record_id
            and backup.get('updated_at_raw') == before['updated_at'] and backup.get('version') == before['version']
            and backup.get('production_write_performed') is False and backup.get('fresh_prewrite_comparison_required') is True,
            'R0 before backup cannot substitute for immediate prewrite comparison')
    rollback = pinned(ROOT, candidate['rollback_plan'])
    require(rollback.get('record_id') == record_id and rollback.get('table') == table
            and rollback.get('forward_candidate_version_proposal') == cv
            and rollback.get('changed_fields') == fields and rollback.get('before_backup') == candidate['before_backup']
            and rollback.get('prior_values_digest') == source['hashes']['rollback_fields_sha256']
            and all(rollback.get(k) is False for k in ['restore_permission_granted', 'native_restore_preview_executed',
                                                      'post_save_CAS_observed', 'automatic_rollback_executable', 'permit_issued']),
            'rollback cannot inherit old permits, stale CAS or an uncompleted parent')
    require(pinned(ROOT, rollback['rollback_sparse_patch']) == {k: before[k] for k in fields}, 'rollback must preserve original two-field values')
    binding = pinned(ROOT, entry['product_binding_request'])
    require(binding.get('candidate') == entry['publisher_candidate'] and binding.get('proposed_managed_identity') == managed,
            'product binding must reference the actual frozen publisher candidate')
    runtime = binding.get('runtime_target_proposal', {})
    require(set(runtime) == RUNTIME_TARGET_KEYS, 'exact runtime target field shape required')
    require(runtime.get('id') == record_id and runtime.get('slug') == slug and runtime.get('table') == table
            and runtime.get('contentType') == request['contentType']
            and all(runtime.get(k) == managed[k] for k in ['taskId', 'actionId', 'candidateVersion', 'scope'])
            and runtime.get('changedFields') == fields and runtime.get('baselineProjectionFields') == source['projection']
            and runtime.get('retainedProjectionFields') == source['retained']
            and runtime.get('expectedUpdatedAt') == before['updated_at']
            and runtime.get('requiresParentRun') is True and runtime.get('rollbackAllowed') is False
            and all(runtime.get(k) == source['hashes'][v] for k, v in {
                'baselineFieldsSha256': 'baseline_fields_sha256', 'desiredFieldsSha256': 'desired_fields_sha256',
                'rollbackFieldsSha256': 'rollback_fields_sha256', 'retainedFieldsSha256': 'retained_fields_sha256'}.items()),
            'new product target must use exact native projection, stable retained hash and completed rollback parent')
    cli = binding.get('CLI_target_proposal', {})
    require(set(cli) == CLI_TARGET_KEYS, 'exact CLI target field shape required')
    require(cli.get('qaEvidenceVersion') == cv
            and cli.get('originalFrozenSourcePath') == candidate['original_frozen_candidate']['path']
            and cli.get('originalFrozenSourceSha256') == candidate['original_frozen_candidate']['sha256']
            and cli.get('rollbackRecordPath') == candidate['before_backup']['path']
            and cli.get('rollbackRecordSha256') == candidate['before_backup']['sha256']
            and cli.get('rollbackPackagePath') == candidate['rollback_plan']['path']
            and cli.get('rollbackPackageSha256') == candidate['rollback_plan']['sha256'],
            'CLI QA version and frozen rollback/source pins changed')
    require(all(cli.get(k) == managed[k] for k in ['taskId', 'actionId', 'candidateVersion', 'scope'])
            and cli.get('recordId') == record_id and cli.get('table') == table and cli.get('slug') == slug
            and cli.get('contentType') == request['contentType'] and cli.get('actionClass') == 'cms_write'
            and cli.get('changedFields') == fields and cli.get('desiredFields') == desired
            and cli.get('baselineProjectionFields') == source['projection'] and cli.get('retainedProjectionFields') == source['retained']
            and cli.get('expectedUpdatedAt') == before['updated_at'] and cli.get('status') == 'published'
            and cli.get('rollbackAllowed') is False and cli.get('exactPatchOnly') is True and cli.get('keyField') == 'id'
            and cli.get('sourceCandidatePath') == entry['publisher_candidate']['path']
            and cli.get('sourceCandidateSha256') == entry['publisher_candidate']['sha256']
            and all(cli.get(k) == source['hashes'][v] for k, v in {
                'baselineFieldsSha256': 'baseline_fields_sha256', 'desiredFieldsSha256': 'desired_fields_sha256',
                'rollbackFieldsSha256': 'rollback_fields_sha256', 'retainedFieldsSha256': 'retained_fields_sha256'}.items()),
            'CLI target must preserve the exact publisher candidate and sparse field/hash boundary')


def validate_manifest(root: Path, manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    sources = source_entries(root)
    require(manifest.get('schema_version') == 'publisher_native_sparse_admission_v1'
            and manifest.get('project_id') == PROJECT and manifest.get('control_task_id') == CONTROL_TASK
            and manifest.get('publisher_preparation_task_id') == REWORK_TASK
            and manifest.get('mode') == 'CANDIDATE_ONLY_NO_PERMIT' and manifest.get('source_evidence_index') == SOURCE_INDEX_PIN
            and all(manifest.get(k) is False for k in ['release_ready', 'production_authorized', 'production_write_allowed', 'old_permits_inherited']),
            'candidate binding cannot self-grant readiness, authority or old permits')
    entries = manifest.get('entries', [])
    require(len(entries) == 3 and {x.get('item') for x in entries} == set(EXACT), 'exact three admitted targets only')
    targets = {}
    for entry in entries:
        require(all(entry.get(k, False) is False for k in ['release_ready', 'production_authorized', 'production_write_allowed', 'old_permits_inherited']),
                'an entry cannot self-grant readiness or execution')
        source = sources[entry['item']]
        candidate = pinned(root, entry['publisher_candidate'])
        validate_execution_candidate(candidate, entry, source)
        cv = entry['candidate_version']
        require(cv not in targets, 'duplicate execution candidate version')
        targets[cv] = {**{k: entry[k] for k in ['task_id', 'action_id', 'candidate_version', 'scope', 'table', 'record_id', 'slug',
                                              'changed_fields', 'expected_updated_at', 'observed_version', 'baseline_projection_fields',
                                              'retained_projection_fields', 'execution_owner', 'execution_thread_id']},
                       **source['hashes'], 'candidate_shape': SHAPE,
                       'content_type': 'service' if entry['table'] == 'services' else 'blog',
                       'candidate': (entry['publisher_candidate']['path'], entry['publisher_candidate']['sha256']),
                       'rollback': (candidate['before_backup']['path'], candidate['before_backup']['sha256']),
                       'source_frozen_candidate': (source['old']['frozen_candidate']['path'], source['old']['frozen_candidate']['sha256']),
                       'native_source_entry': entry, 'native_registration_only': False,
                       'release_ready': False, 'production_authorized': False, 'old_permits_inherited': False,
                       'qa_outbox': None, 'requires_completed_parent': True, 'rollback_allowed': False}
    return targets


def build_entry(root: Path, label: str, publisher_candidate_pin: dict[str, Any]) -> dict[str, Any]:
    require(label in EXACT, 'exact three row labels required')
    candidate = pinned(root, publisher_candidate_pin)
    source = source_entries(root)[label]
    table, record_id, slug, fields = EXACT[label]
    managed = candidate['proposed_managed_identity']
    binding_path = (Path(publisher_candidate_pin['path']).parent / 'product-runtime-CLI-binding-request.json').as_posix()
    entry = {'item': label, 'task_id': BUSINESS_TASK, 'action_id': managed['actionId'],
             'candidate_version': candidate['candidate_version'], 'scope': managed['scope'],
             'table': table, 'record_id': record_id, 'slug': slug, 'changed_fields': fields,
             'execution_owner': 'publishing', 'execution_thread_id': PUBLISHER,
             'action_class': 'cms_content_candidate', 'execution_action_class': 'cms_write',
             'expected_updated_at': source['before']['updated_at'], 'observed_version': source['before']['version'],
             'baseline_projection_fields': source['projection'], 'retained_projection_fields': source['retained'],
             **source['hashes'], **source['source'], 'publisher_candidate': publisher_candidate_pin,
             'product_binding_request': pin(root, binding_path)}
    validate_execution_candidate(candidate, entry, source)
    return entry


def build_manifest(root: Path, publisher_candidate_pins: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Construct only from three real pinned publisher files; no guessed pins."""
    require(set(publisher_candidate_pins) == set(EXACT), 'three real publisher candidate pins required')
    entries = [build_entry(root, label, publisher_candidate_pins[label]) for label in EXACT]
    manifest = {'schema_version': 'publisher_native_sparse_admission_v1', 'project_id': PROJECT,
                'control_task_id': CONTROL_TASK, 'publisher_preparation_task_id': REWORK_TASK, 'mode': 'CANDIDATE_ONLY_NO_PERMIT', 'source_evidence_index': SOURCE_INDEX_PIN,
                'release_ready': False, 'production_authorized': False, 'production_write_allowed': False,
                'old_permits_inherited': False, 'entries': entries}
    validate_manifest(root, manifest)
    return manifest


def load_targets(root: Path, manifest_pin: dict[str, Any] | None = None) -> dict[str, dict[str, Any]]:
    release_qa = {}
    if manifest_pin is None:
        policy_path = root / 'data/action-policy.json'
        policy = json.loads(policy_path.read_text(encoding='utf-8')) if policy_path.is_file() else {}
        control = policy.get('cms_publisher_native_sparse_admission', {})
        if not control:
            return {}
        require(control.get('status') == 'reviewed_candidate_binding' and control.get('production_authority_granted') is False,
                'exact reviewed candidate binding required')
        manifest_pin = control.get('manifest')
        release_qa = control.get('release_qa_outboxes', {})
    targets = validate_manifest(root, pinned(root, manifest_pin))
    require(isinstance(release_qa, dict) and set(release_qa).issubset(targets), 'QA bindings cannot add execution targets')
    for cv, qa_pin in release_qa.items():
        require(qa_outbox_matches(pinned(root, qa_pin), targets[cv]), 'exact structured production QA binding required')
        targets[cv]['qa_outbox'] = (qa_pin['path'], qa_pin['sha256'])
    return targets


def exact_target_for_action(root: Path, task_id: str, action_id: str, scope: str) -> dict[str, Any] | None:
    matches = [x for x in load_targets(root).values() if (x['task_id'], x['action_id'], x['scope']) == (task_id, action_id, scope)]
    require(len(matches) <= 1, 'ambiguous publisher sparse action')
    return matches[0] if matches else None


def validate_candidate_binding(root: Path, candidate: dict[str, Any], target: dict[str, Any]) -> None:
    require(target.get('candidate_shape') == SHAPE and target.get('candidate_version') not in OLD_VERSIONS,
            'old registration is never a sparse permit candidate')
    entry = target['native_source_entry']
    require(all(target.get(k) == entry.get(k) for k in ['task_id', 'action_id', 'candidate_version', 'scope', 'table', 'record_id',
                'slug', 'changed_fields', 'expected_updated_at', 'observed_version', 'baseline_projection_fields',
                'retained_projection_fields', 'execution_owner', 'execution_thread_id'])
            and target.get('native_registration_only') is False
            and all(target.get(k) is False for k in ['release_ready', 'production_authorized', 'old_permits_inherited', 'rollback_allowed'])
            and target.get('requires_completed_parent') is True, 'immutable sparse target descriptor required')
    require(candidate == pinned(root, {'path': target['candidate'][0], 'sha256': target['candidate'][1]}), 'exact publisher candidate required')
    validate_execution_candidate(candidate, entry, source_entries(root)[entry['item']])


def qa_outbox_matches(row: dict[str, Any], target: dict[str, Any]) -> bool:
    """A structural condition only; the existing issuer must validate native QA receipts."""
    return (row.get('department') == 'qa' and row.get('fixed_chat_task_id') == QA
            and row.get('task_id') == BUSINESS_TASK and row.get('status') == 'completed'
            and row.get('gate_status') == 'PASS_FOR_AUTO_RELEASE' and row.get('verdict', row.get('qa_verdict')) == 'pass'
            and row.get('risk_level') == 'R1' and row.get('review_scope') == 'exact_publisher_sparse_release_with_protected_zero_write_preview'
            and row.get('action_id') == target['action_id'] and row.get('candidate_version') == target['candidate_version']
            and row.get('candidate_sha256') == target['candidate'][1] and row.get('scope') == target['scope']
            and row.get('record_id') == target['record_id'] and row.get('table') == target['table']
            and row.get('allowed_fields') == target['changed_fields'] and row.get('execution_owner') == 'publishing'
            and row.get('execution_thread_id') == PUBLISHER
            and not any(isinstance(x, dict) and str(x.get('priority', '')).upper() in {'P0', 'P1'} for x in row.get('blockers', [])))


def require_actual_release_qa_pin(root: Path, target: dict[str, Any]) -> None:
    """Pre-issuer structural check; never replaces validate_qa/artifact_for_run."""
    require(target.get('candidate_shape') == SHAPE and target.get('candidate_version') not in OLD_VERSIONS,
            'old registration cannot issue a sparse permit')
    validate_candidate_binding(root, pinned(root, {'path': target['candidate'][0], 'sha256': target['candidate'][1]}), target)
    qa_pin = target.get('qa_outbox')
    require(isinstance(qa_pin, (list, tuple)) and len(qa_pin) == 2, 'actual fixed production QA outbox is missing')
    require(qa_outbox_matches(pinned(root, {'path': qa_pin[0], 'sha256': qa_pin[1]}), target),
            'actual fixed QA outbox is not this exact sparse production candidate')


def local_readiness_report(target: dict[str, Any], *, fixed_qa_present: bool = False,
                           protected_preview_present: bool = False) -> dict[str, Any]:
    """Never make a production claim from local flags or loose artifact presence."""
    reasons = []
    if not fixed_qa_present:
        reasons.append('actual_fixed_production_QA_missing')
    if not protected_preview_present:
        reasons.append('actual_GitHub_zero_write_preview_missing')
    reasons.extend(['existing_issuer_native_QA_chain_required', 'existing_AUTO_RELEASE_and_consumed_policy_required',
                    'existing_fresh_GitHub_OIDC_and_backup_checks_required', 'protected_single_use_permit_required'])
    return {'status': 'DENY', 'candidate_version': target.get('candidate_version'), 'reasons': reasons,
            'release_ready': False, 'production_authorized': False, 'permit_issued': False}
