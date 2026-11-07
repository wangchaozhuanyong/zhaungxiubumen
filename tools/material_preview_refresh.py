"""One successor to an expired, provider-proven zero-write material preview.

No existing Save policy, permit or unknown transport can be replayed here.
"""
import datetime as dt
import hashlib
import io
import json
import subprocess
import zipfile
from pathlib import Path

import workflow_control as w
import material_preview_execution as m


def validate_parent(parent, target, main, docs, now):
    receipt = docs['locked-dry-run-receipt.json']; probe = docs['managed-identity-probe.json']
    payload = docs['managed-payload-digest.json']; backup = docs['backup.json']
    m.need(parent.get('event') == 'workflow_dispatch' and parent.get('status') == 'completed'
           and parent.get('conclusion') == 'success' and parent.get('run_attempt') == 1
           and parent.get('head_sha') == main and parent.get('head_branch') == 'main'
           and parent.get('path') == m.WORKFLOW and parent.get('actor', {}).get('id') == 276684684
           and parent.get('repository', {}).get('id') == 1248188229,
           'exact completed first-attempt original zero preview provider identity')
    expected = {'task_id': m.TASK, 'action_id': target['action_id'], 'scope': target['scope'],
                'candidate_version': target['candidate_version'], 'operation': 'publish',
                'http_status': 200, 'dry_run': True, 'performed_write': False,
                'external_writes': 0, 'row_unchanged_after_dry_run': True}
    m.need(all(receipt.get(k) == v for k, v in expected.items()),
           'original provider artifact must prove exact per-object zero CMS writes')
    checked = w._parse_observed_at(receipt.get('checked_at'))
    m.need(checked is not None and (now - checked).total_seconds() > 1800,
           'only an actually expired original preview; never refresh a still-usable run')
    identity = probe.get('identity', {})
    m.need(probe.get('ok') is True and probe.get('dry_run') is True and probe.get('performed_write') is False
           and identity.get('runId') == parent['id'] and identity.get('runAttempt') == 1
           and identity.get('actorId') == 276684684 and identity.get('repositoryId') == 1248188229
           and identity.get('workflowSha') == main
           and identity.get('workflowRef') == m.REPO + '/' + m.WORKFLOW + '@refs/heads/main'
           and payload.get('task_id') == m.TASK and payload.get('operation') == 'publish'
           and payload.get('payload_sha256') == target['payload_sha256']
           and backup.get('table') == 'materials' and backup.get('record', {}).get('id') == target['record_id']
           and backup.get('record', {}).get('slug') == target['slug']
           and len(backup.get('record', {})) == 59
           and receipt.get('expected_updated_at') == backup['record'].get('updated_at')
           and payload.get('expected_updated_at') == receipt.get('expected_updated_at'),
           'real OIDC, unchanged exact body digest and original full59 CAS backup')
    return checked


def verify(root, parent_id, target, main, runs):
    namespace = 'two-original-material-body-' + target['slug']
    same = [row for row in runs if namespace in str(row.get('display_title', ''))]
    m.need(len(same) == 1 and same[0].get('id') == parent_id
           and same[0].get('display_title') == namespace + ' | dry-run',
           'one real original predecessor; no other run, Save or UNKNOWN successor')
    base_action = m.PREFIX + target['slug']
    policies = w.read_jsonl(Path(root) / w.POLICY_DECISIONS, where={'task_id': m.TASK, 'status': 'allow'})
    original = [row for row in policies if row.get('action_id') == base_action
                and row.get('action_class') == 'site_ci_prepare' and row.get('department') == 'publishing']
    m.need(len(original) == 1 and not any(row.get('action_id') == target['action_id']
           and row.get('action_class') == 'cms_write' for row in policies),
           'original own preview and no issued/consumed Save policy; reconcile such effects first')
    effect = w.read_json(Path(root) / 'logs/material-zero-write-preview' / base_action / 'result.json')
    m.need(effect.get('decision_id') == original[0]['decision_id'] and effect.get('exit_code') == 0,
           'known original accepted dispatch, never an unknown send replay')
    parent = m.gh('repos/' + m.REPO + '/actions/runs/' + str(parent_id))
    artifacts = m.gh('repos/' + m.REPO + '/actions/runs/' + str(parent_id) + '/artifacts?per_page=100')
    found = [row for row in artifacts.get('artifacts', [])
             if row.get('name') == 'approved-content-publish-' + str(parent_id) and row.get('expired') is False]
    m.need(len(found) == 1 and found[0].get('workflow_run', {}).get('id') == parent_id
           and found[0]['workflow_run'].get('head_sha') == main, 'exact original unexpired provider artifact')
    raw = subprocess.check_output(['gh', 'api', 'repos/' + m.REPO + '/actions/artifacts/'
                                   + str(found[0]['id']) + '/zip'], timeout=60)
    m.need(len(raw) <= 50 * 1024 * 1024, 'bounded original provider archive')
    docs = {}
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        for name in ('locked-dry-run-receipt.json', 'managed-identity-probe.json',
                     'managed-payload-digest.json', 'backup.json'):
            entries = [row for row in archive.infolist() if row.filename == namespace + '/' + name]
            m.need(len(entries) == 1 and not entries[0].is_dir()
                   and entries[0].file_size <= 2 * 1024 * 1024, 'one bounded exact artifact document')
            docs[name] = json.loads(archive.read(entries[0]))
    checked = validate_parent(parent, target, main, docs, dt.datetime.now(dt.timezone.utc))
    return {'run_id': parent_id, 'artifact_id': found[0]['id'],
            'archive_sha256': hashlib.sha256(raw).hexdigest(), 'original_receipt_checked_at': checked.isoformat(),
            'actual_zero_writes': True, 'Save_policy_exists': False,
            'permitted_successor': m.action(target['slug']), 'original_receipt_extended': False}


def validate_preflight_refresh(root, old, new, *, cutoff=None):
    """Same action/body/CAS; only execution evidence follows its real zero run."""
    import paid_three_page_bounded_cms as cms

    m.need(old.get('task_id') == new.get('task_id') == m.TASK
           and old.get('department') == new.get('department') == 'publishing'
           and all(old.get(k) == new.get(k) for k in
                   ('action_id', 'action_class', 'scope', 'candidate_version', 'risk_level', 'payload_sha256')),
           'original preflight identity, authority, risk and body cannot change')
    previous = cms.doc(root, new['replaces_preflight'])
    m.need(previous == old, 'exact immutable original preflight pin required')
    a = cms.doc(root, old['self_check']); b = cms.doc(root, new['self_check'])
    m.need(all(a.get(k) == b.get(k) for k in
               ('candidate', 'record_id', 'changed_fields', 'expected_updated_at', 'payload_sha256',
                'source_verification', 'executor_department')),
           'only new machine/facts evidence; original candidate, source and CAS remain')
    old_machine = cms.doc(root, a['actual_machine']); new_machine = cms.doc(root, b['actual_machine'])
    before = cms.doc(root, old_machine['run_snapshot']); after = cms.doc(root, new_machine['run_snapshot'])
    slug = next((row[0] for row in cms.MATERIAL_ROWS if row[2] == old['action_id']), None)
    m.need(slug is not None and before['id'] != after['id'] and after.get('status') == 'completed'
           and after.get('conclusion') == 'success' and after.get('run_attempt') == 1
           and after.get('head_sha') == before.get('head_sha')
           and after.get('path') == before.get('path') == m.WORKFLOW
           and after.get('display_title') == 'two-original-material-body-' + slug + ' | dry-run',
           'actual distinct successful original zero-preview successor')
    action = m.PREFIX + slug + '-after-zero-' + str(before['id'])
    policies = w.read_jsonl(Path(root) / w.POLICY_DECISIONS, where={'task_id': m.TASK, 'status': 'allow'})
    successors = [p for p in policies if p.get('action_id') == action and p.get('department') == 'publishing'
                  and p.get('action_class') == 'site_ci_prepare' and p.get('Save_allowed') is False]
    m.need(len(successors) == 1
           and successors[0].get('provider_facts', {}).get('verified_zero_write_predecessor', {}).get('run_id') == before['id'],
           'one normal verified-zero successor policy, never an arbitrary preflight replacement')
    limit = w._parse_observed_at(cutoff) if cutoff else None
    writes = [p for p in policies if p.get('action_id') == old['action_id'] and p.get('action_class') == 'cms_write'
              and (limit is None or w._parse_observed_at(p['checked_at']) <= limit)]
    m.need(not writes, 'issued or unknown Save policy must be reconciled before replacing evidence')
    return True


def record_preflight_refresh(root, snapshot, old, item, input_path):
    from goal_delivery_runtime import execution_preflight
    import material_preflight_metadata as metadata

    validate_preflight_refresh(root, old, item)
    goal = snapshot['goal_delivery']; updated = dict(goal)
    updated['execution_preflights'] = [item if row == old else row for row in goal['execution_preflights']]
    metadata.goal_delta(goal, updated, item)
    candidate = {**snapshot, 'goal_delivery': updated}
    execution_preflight(root, candidate, item['action_id'], item['action_class'], item['scope'], item['department'])
    w.append_workflow_event(root, snapshot['task_id'], snapshot['current_state'], {
        'goal_delivery': updated, 'production_preflight_registered': w.file_digest(root, input_path),
        'external_permission_issued': False})
    w.atomic_write_json(w.snapshot_path(root, snapshot['task_id']), candidate)
    return {'result': 'recorded', 'external_permission_issued': False, 'original_preflight_preserved': True}
