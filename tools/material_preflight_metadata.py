"""Authenticate neutral original PUB selfcheck registration, never a Save grant."""
from pathlib import Path
import copy

import workflow_control as w

TASK = 'fc-20261014-two-original-materials-exact-body-publication-v1'


def need(ok, message):
    if not ok:
        raise w.WorkflowError('Material selfcheck metadata: ' + message)


def goal_delta(before, after, item):
    expected = copy.deepcopy(before)
    prior = expected.get('execution_preflights', [])
    need(isinstance(prior, list), 'original selfcheck list required')
    matches = [i for i, row in enumerate(prior) if all(row.get(k) == item.get(k) for k in
                                                    ('action_id', 'action_class', 'scope', 'department'))]
    if matches:
        need(len(matches) == 1 and isinstance(item.get('replaces_preflight'), dict),
             'existing evidence requires an exact authenticated zero-preview successor')
        updated = copy.deepcopy(prior); updated[matches[0]] = item
        expected['execution_preflights'] = updated
    else:
        need('replaces_preflight' not in item, 'cannot replace an absent original selfcheck')
        expected['execution_preflights'] = prior + [item]
    need(after == expected, 'only append this selfcheck; no owner, scope, authority or other goal change')
    declared = before.get('required_execution_actions', [])
    keys = ('task_id', 'action_id', 'action_class', 'scope', 'department', 'candidate_version')
    need(item.get('task_id') == TASK and item.get('department') == 'publishing'
         and item.get('action_class') == 'cms_write' and item.get('risk_level') in {'R1', 'R2'}
         and sum(all(row.get(k) == item.get(k) for k in keys) for row in declared) == 1,
         'one frozen original publisher Save tuple; metadata grants no execution permission')


def metadata(root, formal, event):
    detail = event.get('details', {})
    if set(detail) != {'goal_delivery', 'production_preflight_registered', 'external_permission_issued'}:
        return False
    need(event.get('task_id') == formal.get('task_id') == TASK
         and event.get('state') == formal.get('current_state')
         and detail['external_permission_issued'] is False, 'same-state original selfcheck event only')
    rows = w.read_jsonl(Path(root) / w.WORKFLOW_EVENTS, where={'task_id': TASK})
    indexes = [i for i, row in enumerate(rows) if row.get('event_id') == event.get('event_id')]
    need(len(indexes) == 1 and rows[indexes[0]] == event, 'exact committed original event required')
    earlier = [row['details']['goal_delivery'] for row in rows[:indexes[0]]
               if isinstance(row.get('details', {}).get('goal_delivery'), dict)]
    need(bool(earlier), 'original preceding frozen goal required')
    import paid_three_page_bounded_cms as cms

    item = cms.doc(root, detail['production_preflight_registered'])
    goal_delta(earlier[-1], detail['goal_delivery'], item)
    if item.get('replaces_preflight'):
        old = cms.doc(root, item['replaces_preflight'])
        from material_preview_refresh import validate_preflight_refresh
        validate_preflight_refresh(root, old, item, cutoff=event['created_at'])
    docs = {name: cms.doc(root, item[name]) for name in ('facts', 'self_check', 'backup', 'rollback')}
    check = docs['self_check']
    need(check.get('status') == 'PASS' and check.get('production_write_allowed') is False
         and check.get('executor_department') == 'publishing'
         and all(check.get(k) == item.get(k) for k in
                 ('task_id', 'department', 'action_id', 'action_class', 'scope', 'payload_sha256')),
         'exact original PUB selfcheck evidence; PASS is not a permit')
    candidate = cms.doc(root, check['candidate'])
    need(check.get('record_id') == candidate.get('id') == docs['backup'].get('record', {}).get('id')
         and check.get('changed_fields') == ['content_en', 'content_zh']
         and cms.digest({key: candidate[key] for key in check['changed_fields']}) == item['payload_sha256']
         and w.SHA256_PATTERN.fullmatch(item['payload_sha256']) is not None,
         'unchanged per-record candidate and exact two-field body digest')
    for pin in check.get('evidence', []):
        cms.doc(root, pin)
    need(check.get('source_verification') in check.get('evidence', [])
         and check.get('actual_machine') in check.get('evidence', []),
         'source and actual preview machine pins must remain in original evidence')
    # The normal issuer still checks the full deployment, provider, CAS, TTL,
    # actor and own once-only policy. Do not recurse into that gate to read it.
    return True
