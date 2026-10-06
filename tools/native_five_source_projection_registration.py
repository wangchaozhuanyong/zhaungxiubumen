"""Frozen five-row projection evidence; only three new registrations, no permits."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path

ROOT = Path('<PROJECT_ROOT>')
PROJECT = '<LOCAL_PROJECT_ID>'
VERSION = 'five-native-registration-projection-control-v1-20261002'
MANIFEST_PATH = 'drafts/operations/fc-20261002-five-native-registration-projection-control-v1/registration-manifest.json'
MANIFEST_SHA256 = '8e39d258172de92b5f943af6b893c2fe989a8224f688c691b4d1316c2dca9987'
INDEX_PIN = {'path': 'logs/handoffs/fc-20261002-approved-rawang-seri-warehouse-source-binding-v1/approved-rawang-seri-warehouse-native-adapter-rework-v2-20261002/native-capability-candidate.json', 'sha256': '29b30223b67aa55d6e3e14c4a57fe36280b8930f79a05fb521bb4f863ee7f305', 'size': 21313}
LABELS = ['rawang', 'seri-kembangan', 'warehouse', 'shop', 'children']
NEW_LABELS = LABELS[:3]
SERVICE_FIELDS = set('id slug title_zh title_en excerpt_zh excerpt_en content_zh content_en image_url alt_zh alt_en suitable_for_zh suitable_for_en common_projects_zh common_projects_en process_steps_zh process_steps_en scope_items_zh scope_items_en faqs_zh faqs_en seo_title_zh seo_title_en seo_description_zh seo_description_en status sort_order created_at updated_at version'.split())
AREA_FIELDS = set('id slug title_zh title_en excerpt_zh excerpt_en content_zh content_en area_name seo_title_zh seo_title_en seo_description_zh seo_description_en status sort_order created_at updated_at property_types common_needs construction_notes_zh construction_notes_en projects faqs_zh faqs_en version'.split())

def require(ok, reason):
    if not ok:
        raise ValueError(reason)

def canonical(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()

def pinned(root, pin):
    root = root.resolve()
    rel = Path(pin['path'])
    p = (root / rel).resolve()
    require(root == ROOT and not rel.is_absolute() and p.is_relative_to(root) and p.is_file(), 'exact project boundary')
    raw = p.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == pin['sha256'], 'source pin changed')
    size = pin.get('size', pin.get('bytes'))
    require(size is None or len(raw) == size, 'source byte count changed')
    return json.loads(raw)

def validate_entry(root, row):
    req = pinned(root, row['original_admission'])
    candidate = pinned(root, row['original_candidate'])
    before = pinned(root, row['original_source'])
    after = pinned(root, req['desired'])
    preview = pinned(root, row['protected_preview_original_request'])
    identity = {k: row[k] for k in ('action_id', 'candidate_version', 'scope', 'record_id', 'slug', 'table', 'content_type')}
    identity['task_id'] = row['original_task_id']
    require(all(req.get(k) == v and candidate.get(k) == v for k, v in identity.items()), 'original task/action/version/row/scope binding')
    expected_table = 'service_areas' if row['label'] in LABELS[:2] else 'services'
    expected_type = 'service_area' if expected_table == 'service_areas' else 'service'
    changed = ['content_en', 'content_zh'] + (['faqs_en', 'faqs_zh'] if expected_table == 'service_areas' else [])
    require(row['table'] == expected_table and row['content_type'] == expected_type, 'table/type binding')
    require(row['changed_fields'] == req['changed_fields'] == candidate['changed_fields'] == changed, 'exact fields only')
    require(row['scope'] == 'flashcast.com.my:' + expected_table + '/' + row['record_id'] + ':' + ','.join(changed) + ':' + row['candidate_version'], 'scope cannot broaden')
    schema = AREA_FIELDS if expected_table == 'service_areas' else SERVICE_FIELDS
    require(set(before) == set(after) == schema and len(schema) == row['complete_source_field_count'], 'complete native row schema')
    require(before['id'] == after['id'] == row['record_id'] and before['slug'] == after['slug'] == row['slug'], 'row identity')
    require(before['updated_at'] == after['updated_at'] == row['expected_updated_at'] == req['expected_updated_at'] == candidate['expected_updated_at'], 'exact microsecond CAS')
    require(type(before['version']) is int and before['version'] == after['version'] == row['observed_version'] == req['observed_version'] == candidate['expected_version'], 'exact observed version')
    require(req['source']['path'] == row['original_source']['path'] and req['source']['sha256'] == row['original_source']['sha256'], 'original source pin')
    require(req['preview_request']['path'] == row['protected_preview_original_request']['path'] and req['preview_request']['sha256'] == row['protected_preview_original_request']['sha256'], 'original zero-write preview pin')
    if row['label'] in NEW_LABELS:
        require(candidate.get('kind') == 'cms_content_candidate' and candidate.get('risk') == 'R1', 'original R1 CMS channel')
        require(candidate['source'] == req['source'] and candidate['after'] == req['desired'], 'candidate source and after pins')
    else:
        require(candidate.get('artifact_type') == 'cms_content_candidate' and candidate.get('risk_class') == 'R1' and candidate.get('release_channel') == 'cms_content_candidate -> cms_write', 'original registered CMS channel')
        require(candidate['source_baseline'] == req['source']['path'] and candidate['after_full_row'] == req['desired']['path'], 'registered source and after paths')
    require(all(after[k] == before[k] for k in schema - set(changed)), 'all unmodified fields preserved including CAS')
    require(candidate.get('desired_fields') == {k: after[k] for k in changed}, 'exact desired bytes without normalization')
    projection = {
        'original_changed_baseline': canonical({k: before[k] for k in changed}),
        'native_full_row_baseline': canonical(before),
        'original_retained_including_CAS': canonical({k: before[k] for k in schema - set(changed)}),
        'native_stable_retained_excluding_CAS': canonical({k: before[k] for k in schema - set(changed) - {'updated_at', 'version'}}),
    }
    require(row['hash_projection_mapping'] == projection, 'four differently named projections must recompute from original source')
    require(req['baseline_fields_sha256'] == req['rollback_fields_sha256'] == row['rollback_fields_sha256'] == projection['original_changed_baseline'], 'original changed/rollback projection')
    require(req['retained_fields_sha256'] == projection['original_retained_including_CAS'], 'original retained projection includes CAS')
    require(req['desired_fields_sha256'] == row['desired_fields_sha256'] == canonical({k: after[k] for k in changed}), 'desired fields projection')
    require(canonical({k: after[k] for k in schema - set(changed) - {'updated_at', 'version'}}) == projection['native_stable_retained_excluding_CAS'], 'native stable retained projection')
    if 'baseline_projection_fields' in req:
        require(req['baseline_projection_fields'] == changed and req['retained_projection_fields'] == sorted(schema - set(changed)), 'named projection field sets')
    require(req.get('source_role') == 'super_admin' and req.get('source_http_status') == 200 and req.get('apply_to_active_issuer') is False and req.get('production_authorized') is False, 'historical authenticated read is not write authority')
    require(row.get('protected_preview_executed') is False and row.get('server_CAS_proven') is False and row.get('CMS_Save') is False, 'no fabricated preview/save')
    require(preview == {'mode': 'dry-run', 'contentType': expected_type, 'nextStatus': 'published', 'expectedUpdatedAt': row['expected_updated_at'], 'record': after, 'managedCandidate': {'taskId': row['original_task_id'], 'actionId': row['action_id'], 'candidateVersion': row['candidate_version'], 'scope': row['scope'], 'operation': 'publish'}}, 'exact existing protected preview request only')
    return projection

def validate_registration(root, manifest):
    require(manifest.get('schema_version') == 'five_native_projection_registration_only_v1'
        and manifest.get('project_id') == PROJECT and manifest.get('candidate_version') == VERSION
        and manifest.get('execution_owner') == 'content-organic-website'
        and manifest.get('mode') == 'REGISTRATION_ONLY_NO_PERMIT'
        and manifest.get('release_ready') is False and manifest.get('production_authorized') is False
        and manifest.get('native_registration_only') is True and manifest.get('actual_remote_preview') is None,
        'registration must remain non-executable')
    require(manifest.get('native_source_index') == INDEX_PIN, 'only frozen native source index')
    index = pinned(root, INDEX_PIN)
    rows = manifest.get('entries')
    require(rows == index['targets'] and [r['label'] for r in rows] == LABELS, 'five frozen tuples only, no substitution')
    require(manifest.get('new_target_labels') == NEW_LABELS and manifest.get('existing_targets_preserved') == LABELS[3:], 'only three new targets and two untouched registrations')
    targets = {}
    for row in rows:
        projections = validate_entry(root, row)
        if row['label'] not in NEW_LABELS:
            continue
        cv = row['candidate_version']
        require(cv not in targets, 'duplicate candidate identity')
        targets[cv] = {**{k: row[k] for k in ('action_id', 'candidate_version', 'record_id', 'slug', 'scope', 'table', 'content_type', 'changed_fields', 'expected_updated_at')},
            'task_id': row['original_task_id'], 'candidate_shape': 'native_five_projection_registration',
            'candidate': (row['original_candidate']['path'], row['original_candidate']['sha256']),
            'source_frozen_candidate': (row['original_candidate']['path'], row['original_candidate']['sha256']),
            'rollback': (row['original_source']['path'], row['original_source']['sha256']),
            'baseline_fields_sha256': projections['original_changed_baseline'],
            'retained_fields_sha256': projections['original_retained_including_CAS'],
            'desired_fields_sha256': row['desired_fields_sha256'], 'rollback_fields_sha256': row['rollback_fields_sha256'],
            'hash_projection_mapping': projections, 'observed_version': row['observed_version'],
            'native_registration_only': True, 'release_ready': False, 'production_authorized': False,
            'qa_outbox': None, 'requires_completed_parent': True, 'native_source_manifest': MANIFEST_PATH}
    return targets

def load_five_source_projection_registration(root):
    return validate_registration(root, pinned(root, {'path': MANIFEST_PATH, 'sha256': MANIFEST_SHA256}))

def validate_five_source_projection_candidate(root, candidate, target):
    frozen = load_five_source_projection_registration(root).get(target.get('candidate_version'))
    require(frozen is not None and target == frozen, 'frozen registration only target')
    require(candidate == pinned(root, {'path': target['candidate'][0], 'sha256': target['candidate'][1]}), 'exact original content candidate required')
