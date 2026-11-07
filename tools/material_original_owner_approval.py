"""HQ's exact routine approval under the existing human material authority.

This materializes a new bounded reference, not a new human message or standing
scope. The actual publisher and ordinary CMS policy/issuer remain unchanged.
"""
import datetime as dt
from pathlib import Path

import workflow_control as w

TASK = 'fc-20261014-two-original-materials-exact-body-publication-v1'
SCHEMA = 'operations-original-material-routine-approval/v1'
PREFIX = 'apr-material-'


def need(ok, message):
    if not ok:
        raise w.WorkflowError('Original material routine approval: ' + message)


def identity(row, requested):
    need(all(row.get(k) == requested.get(k) for k in ('task_id', 'action_id', 'action_class', 'scope'))
         and row.get('task_id') == TASK and row.get('action_class') == 'cms_write'
         and row.get('execution_department') == requested.get('department', 'publishing') == 'publishing'
         and row.get('payload_sha256') == requested.get('payload_sha256'), 'exact original PUB action/body identity')


def active(root, requested, approval_id):
    need(str(approval_id).startswith(PREFIX), 'new exact material reference, not an inherited old permit')
    row = w.effective_approvals(root).get(approval_id, {})
    identity(row, requested)
    now = dt.datetime.now(dt.timezone.utc)
    expires = w._parse_observed_at(row.get('expires_at'))
    need(row.get('status') == 'active' and row.get('single_use') is True
         and row.get('granted_by') == row.get('decision_actor') == 'operations'
         and row.get('approval_basis') == 'existing_owner_goal_and_real_HQ_routine_decision'
         and row.get('not_a_new_human_instruction') is True
         and expires is not None and now < expires,
         'fresh own single-use HQ reference required; consumed/expired approval is not renewed')
    import goal_delivery_runtime as g
    delegation = g._owner_decision_delegation(root)
    need(delegation and row.get('decision_authority_pin') == delegation['source'], 'real HQ decision delegation')
    need(w.file_digest(root, row['source_evidence']['path']) == row['source_evidence'], 'unchanged actual HQ decision')
    snapshot = g.restore_goal(root, w.read_json(w.snapshot_path(root, TASK)))
    need(snapshot['goal_delivery']['authorization_pin'] == row['original_execution_authority_pin']
         and w.read_json(w.safe_path(root, row['execution_preflight']['path']))
             in snapshot['goal_delivery'].get('execution_preflights', [])
         and w.file_digest(root, row['execution_preflight']['path']) == row['execution_preflight'],
         'original authority and current committed execution evidence cannot change')
    return row


@w.request_validation_context()
def record(root, *, task_id, action_id, action_class, scope, source_evidence,
           approval_id='', source_thread_id='', source_message_ref='', revoke=False):
    import department_autonomy as a
    import goal_delivery_runtime as g
    import material_current_pub_admission as current
    import managed_cms_permit_issuer as issuer

    need(task_id == TASK and action_class == 'cms_write' and not revoke,
         'only a new exact original forward material reference')
    pin = w.file_digest(root, source_evidence); decision = a.document(root, pin)
    delegation = g._owner_decision_delegation(root); binding = w.department_registry(root)['operations']['chat_binding']
    need(delegation and source_thread_id == delegation['source_thread_id']
         and source_message_ref == delegation['source_message_id']
         and decision.get('schema') == SCHEMA and decision.get('decision_actor') == 'operations'
         and decision.get('decision_thread_id') == binding['task_id']
         and decision.get('decision_authority_pin') == delegation['source']
         and all(decision.get(k) == v for k, v in
                 {'task_id': TASK, 'action_id': action_id, 'action_class': 'cms_write', 'scope': scope}.items()),
         'actual HQ routine decision and genuine existing human delegation; no invented human source')
    requested = {'task_id': TASK, 'action_id': action_id, 'action_class': action_class, 'scope': scope,
                 'department': 'publishing', 'payload_sha256': decision['payload_sha256'],
                 'source_project_id': binding['project_id'], 'consume_approval': True, 'approval_id': ''}
    admission = current.admit(root, requested)
    context = issuer.validate_goal_cms_policy(root, TASK, action_id, scope, 'publishing', decision['payload_sha256'])
    need(context.get('risk_level') in {'R1', 'R2'}
         and context.get('acceptance_model') == 'goal_authorized_cms_selfcheck_v1'
         and context.get('authorization_pin') == decision['original_execution_authority_pin']
         and context.get('preflight') == a.document(root, decision['execution_preflight'])
         and admission['preflight'] == decision['execution_preflight'],
         'full normal source, actual preview, human execution authority and current PUB selfcheck')
    generated = PREFIX + w.sha256_value([TASK, action_id, scope, decision['payload_sha256'],
                                        decision['execution_preflight'], admission['rotation_source']])[:24]
    need(not approval_id or approval_id == generated, 'reference identity is derived from this exact current evidence')
    with w.workflow_lock(root):
        prior = [row for row in w.effective_approvals(root).values() if all(row.get(k) == requested[k]
                 for k in ('task_id', 'action_id', 'action_class', 'scope'))]
        if prior:
            need(len(prior) == 1 and prior[0].get('approval_id') == generated,
                 'existing action approval must be reconciled, never duplicated')
            return {**active(root, requested, generated), 'result': 'duplicate_ignored'}, [Path(root) / w.APPROVAL_LEDGER]
        policies = w.read_jsonl(Path(root) / w.POLICY_DECISIONS,
                               where={'task_id': TASK, 'action_id': action_id, 'action_class': 'cms_write', 'status': 'allow'})
        need(not policies, 'an issued or unknown Save policy must be reconciled before any approval')
        w._VALIDATION_CONTEXT.get().recheck()
        now = dt.datetime.now(dt.timezone.utc)
        row = {'schema_version': '1.1', 'approval_id': generated,
               **{k: requested[k] for k in ('task_id', 'action_id', 'action_class', 'scope', 'payload_sha256')},
               'status': 'active', 'single_use': True, 'granted_by': 'operations', 'decision_actor': 'operations',
               'granted_at': now.isoformat(), 'expires_at': (now + dt.timedelta(minutes=15)).isoformat(),
               'source_thread_id': source_thread_id, 'source_message_ref': source_message_ref,
               'decision_authority_pin': delegation['source'],
               'original_execution_authority_pin': context['authorization_pin'],
               'execution_department': 'publishing', 'execution_preflight': decision['execution_preflight'],
               'current_PUB_admission': admission, 'source_evidence': pin,
               'approval_basis': 'existing_owner_goal_and_real_HQ_routine_decision',
               'not_a_new_human_instruction': True, 'full_approval_message_stored': False,
               'CMS_permit_issued': False}
        w.append_jsonl_locked(Path(root) / w.APPROVAL_LEDGER, row)
    return {**row, 'result': 'recorded'}, [Path(root) / w.APPROVAL_LEDGER]
