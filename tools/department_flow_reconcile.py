"""Consume existing health evidence and prepare handoffs; never send or publish.

Health writes require an explicit apply flag. Handoff output is a per-goal CAS
proposal only: its original owner must merge it into the current index.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
from pathlib import Path
import workflow_control as w

HEALTH_SCHEMA = 'department-health-evidence-batch/v1'
HANDOFF_SCHEMA = 'department-handoff-reconcile/v1'
TASK = 'fc-20261011-english-kitchen-actual-publication-goal-v1'
SCOPE = 'cms:services:kitchen:english-two-fields:publication:v1'


def pinned(root, pin):
    if not isinstance(pin, dict) or w.file_digest(root, pin.get('path', '')) != pin:
        raise w.WorkflowError('exact immutable local evidence pin required')
    return w.read_json(w.safe_path(root, pin['path']))


def sync_health(root, manifest_pin, *, check_only=True):
    """No provider calls or health probe. Isolate bad rows; preserve real time."""
    import flashcast_ops as ops
    manifest = pinned(root, manifest_pin)
    observations = manifest.get('observations')
    if (manifest.get('schema') != HEALTH_SCHEMA or not isinstance(observations, list)
            or not observations or len(observations) > 100):
        raise w.WorkflowError('bounded existing health observations manifest required')
    selected, seen = [], set()
    for item in observations:
        if (not isinstance(item, dict) or set(item) != {'department', 'native'}
                or not isinstance(item['department'], str) or not item['department']
                or item['department'] in seen or not isinstance(item['native'], dict)):
            raise w.WorkflowError('one exact observation per department required')
        seen.add(item['department'])
        selected.append(item)
    outcomes = []
    for item in selected:
        try:
            pinned(root, manifest_pin)  # no changed manifest across individual commits
            proof = ops.refresh_department_health(root, item['department'], item['native'],
                                                  check_only=check_only)
            outcomes.append({'department': item['department'], 'result': proof})
        except (w.WorkflowError, ops.OpsError, ValueError, KeyError, OSError, TypeError) as error:
            outcomes.append({'department': item['department'], 'status': 'blocked', 'reason': str(error)})
    changed = any(x.get('result', {}).get('status') == 'department_health_recorded' for x in outcomes)
    return {'schema': 'department-health-evidence-consumption/v1',
            'status': 'partial_blocked' if any(x.get('status') == 'blocked' for x in outcomes) else 'verified',
            'check_only': check_only, 'outcomes': outcomes, 'writes_performed': changed,
            'provider_calls': 0, 'dispatch_performed_by_command': False,
            'may_trigger_existing_registry_watchers': changed,
            'health_time_source': 'original successful latest terminal completedAt; never observation time'}


def plan_en2_handoff(root, manifest_pin):
    """A frozen report plus its real final can prepare, never execute, a handoff."""
    from goal_delivery_runtime import _native_document
    manifest = pinned(root, manifest_pin)
    if (manifest.get('schema') != HANDOFF_SCHEMA or manifest.get('task_id') != TASK
            or set(manifest) != {'schema', 'task_id', 'report', 'native', 'expected_goal_sha256'}):
        raise w.WorkflowError('exact EN2 handoff manifest required')
    report = pinned(root, manifest['report'])
    registry = w.read_json(Path(root) / 'data/department-registry.json')
    if report.get('schema') == 'actual-original-WEB-EN2-protected-preview-readiness-result/v1':
        if (report.get('task_id') != TASK or report.get('scope') != SCOPE
                or report.get('business_owner') != 'publishing'
                or report.get('WEB_executor') != 'designated-development'
                or report.get('normal_preview_request') != 'ACTUAL_REFUSED: autonomous delivery: external WEB: registered operation'
                or report.get('business_goal_closed') is not False
                or report.get('production_READY') is not False or report.get('preview_completed') is not False):
            raise w.WorkflowError('exact original zero-write preview admission failure required')
        effects = report.get('effects', {})
        required = {'workflow_dispatch', 'reserve', 'issue', 'consume', 'preflight_record',
                    'policy_allow_or_consume', 'CMS_Save', 'push_PR_merge_deploy',
                    'cancel_reissue_TTL_change', 'other_thread_message_or_activation'}
        if set(effects) != required or any(type(v) is not int or v != 0 for v in effects.values()):
            raise w.WorkflowError('this exact preparation must have known zero effects; never replay unknown effects')
        probe_path = str(Path(manifest['report']['path']).parent / 'ACTUAL-NORMAL-PREVIEW-ENTRY-READONLY-PROBE.json')
        probe = w.read_json(w.safe_path(root, probe_path))
        module = probe.get('module')
        if (not isinstance(module, dict) or w.safe_path(root, module.get('path', '')) != (Path(root)/'tools/professional_web_execution.py').resolve()
                or any(w.file_digest(root, module['path']).get(key) != module.get(key) for key in ('sha256', 'size'))):
            raise w.WorkflowError('old WEB refusal cannot replace current repaired execution source')
        fixed = registry.get('collaboration_bindings', {}).get('designated-development', {})
        source_time = report.get('at_UTC')
        state = 'EN2_NORMAL_PROTECTED_PREVIEW_OPERATION_ADMISSION_MISSING'
    elif report.get('state') == 'PARTIAL_ADOPTED_FAIL_CLOSED_NOT_EXECUTABLE':
        # The original SYS successor supersedes the old generic refusal, but
        # its local adoption does not turn into a runnable preview or PUB refresh.
        expected_paths = {'tools/professional_web_execution.py', 'tools/en2_preview_entry.py'}
        installed = report.get('installed', {})
        effects = report.get('effects', {})
        if (set(installed) != expected_paths or set(effects) != {'policy_issued','permit_issued','workflow_run','CMS_Save','cross_thread_message'}
                or any(v is not False for v in effects.values()) or not report.get('still_missing')
                or any(w.file_digest(root, name)['sha256'] != sha for name, sha in installed.items())):
            raise w.WorkflowError('exact current partial SYS adoption and zero effects required')
        role = next((x for x in registry.get('departments', []) if x.get('id') == 'system-development'), {})
        fixed = role.get('chat_binding', {})
        fixed = {**fixed, 'thread_id': fixed.get('task_id')}
        source_time = report.get('at_utc')
        state = 'EN2_PROTECTED_PREVIEW_LOCAL_CHAIN_INCOMPLETE'
    else:
        raise w.WorkflowError('one exact current EN2 failure/partial successor report required')
    document = _native_document(root, manifest['native'])
    thread = document.get('thread', {})
    if (any(not fixed.get(b) or thread.get(a) != fixed[b] for a, b in
            [('id', 'thread_id'), ('title', 'title'), ('cwd', 'cwd'), ('hostId', 'host_id')])
            or ('projectId' in thread and thread['projectId'] != fixed.get('project_id'))):
        raise w.WorkflowError('original external WEB fixed identity required')
    turn = w.latest_native_health_completion(document)
    finals = [x for x in turn.get('items', []) if x.get('type') == 'agentMessage'
              and x.get('phase') == 'final_answer' and isinstance(x.get('text'), str) and x['text'].strip()]
    report_path = str(w.safe_path(root, manifest['report']['path']))
    if len(finals) != 1 or report_path not in finals[0]['text']:
        raise w.WorkflowError('original completed WEB final must reference this exact report')
    completed = turn.get('completedAt')
    at = dt.datetime.fromtimestamp(completed, dt.timezone.utc) if type(completed) in {int, float} else w._parse_observed_at(completed)
    reported = w._parse_observed_at(source_time)
    if at is None or reported is None or reported > at or at > dt.datetime.now(dt.timezone.utc):
        raise w.WorkflowError('original report/final ordering required')
    index = w.read_json(Path(root) / 'data/operations-goal-followthrough.json')
    matches = [x for x in index.get('open_goals', []) if TASK in x.get('original_task_refs', [])]
    if len(matches) != 1:
        raise w.WorkflowError('one existing original business goal required')
    goal = matches[0]
    if (w.sha256_value(goal) != manifest['expected_goal_sha256']
            or goal.get('professional_owner') != 'publishing'
            or goal.get('final_goal_closed') is not False or goal.get('user_paused')):
        raise w.WorkflowError('current per-goal CAS, original owner and unpaused open scope required')
    prior = w._parse_observed_at(goal.get('latest_updated_at_UTC'))
    if prior is not None and prior > at:
        raise w.WorkflowError('newer current goal progress must not be overwritten by an old report')
    patch = {'next_actor': 'system-development',
             'observed_state': state,
             'next_action': 'Original SYS completes the exact EN2 dry-run request/intent/scope/selfcheck/readback entry. Only after adopted-readback, original HQ coordinates one original PUB fresh-three-query completion and immediate original WEB preview. No repeated PUB refresh while the entry is missing.',
             'resume_event': 'Original SYS exact preview entry adoption and readback; then one serial PUB-to-WEB freshness handoff',
             'latest_updated_at_UTC': at.isoformat(),
             'latest_handoff_reconciliation': {'source_report': manifest['report'], 'source_native': manifest['native'],
                 'source_turn_id': turn['id'], 'source_message_id': finals[0]['id'],
                 'business_owner': 'publishing', 'next_action_executor': 'system-development',
                 'handoff_state': 'prepared_not_sent', 'original_completedAt': at.isoformat(),
                 'source_is_permission': False, 'business_goal_closed': False}}
    return {'schema': 'department-goal-handoff-CAS-proposal/v1', 'task_id': TASK,
            'goal_key': goal.get('goal_key'), 'expected_goal_sha256': manifest['expected_goal_sha256'],
            'patch': patch, 'writes_performed': False, 'dispatch_performed': False,
            'apply_entry': None, 'merge_owner': 'operations',
            'before_merge': 'HQ rechecks exact per-goal hash and newer progress; preserve all unrelated current index fields. This proposal grants no dispatch or preview permission.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['health', 'handoff-plan'])
    parser.add_argument('--input', required=True)
    parser.add_argument('--apply-health', action='store_true', help='explicit metadata writes only; may trigger existing registry watchers')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    pin = w.file_digest(root, args.input)
    if args.command == 'handoff-plan':
        if args.apply_health:
            parser.error('handoff proposals have no apply operation')
        result = plan_en2_handoff(root, pin)
    else:
        result = sync_health(root, pin, check_only=not args.apply_health)
    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
