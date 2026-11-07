"""Original WEB control for the never-started material run on a superseded main."""
import argparse
import datetime as dt
import json
from pathlib import Path
import subprocess

import department_autonomy as a
import workflow_control as w

TASK = 'fc-20261014-two-original-materials-exact-body-publication-v1'
RUN = 42266933185
DISPATCH_POLICY = 'pol-5bc6119ac939e2536e99'
OLD_MAIN = '30781b6b9efa3b02e336afc72e06b014ffe50b09'


def source(root, path):
    import professional_web_execution as web

    envelope = a.document(root, w.file_digest(root, path))
    original = a.document(root, envelope['request'])
    item, request, pin, ctx = web.preflight(root, TASK, original['action_id'],
        original['action_class'], original['scope'], original['department'])
    web.need(request == original and pin == w.file_digest(root, path)
             and request['operation'] == 'r3_dispatch' and request['task_id'] == TASK
             and request['state']['main_sha'] == OLD_MAIN
             and ctx.get('material_registry_test_successor') is True
             and ctx['role'] == 'designated-development'
             and Path.cwd().resolve() == Path(ctx['worktree']).resolve(),
             'registered original material dispatch and original WEB worktree required')
    rows = w.read_jsonl(Path(root) / w.POLICY_DECISIONS, where={'decision_id': DISPATCH_POLICY})
    effect = a.document(root, w.file_digest(root,
        'logs/material-r3-dispatch-execution/' + DISPATCH_POLICY + '.json'))
    web.need(len(rows) == 1 and rows[0]['status'] == 'allow'
             and rows[0]['exact_request'] == item['request']
             and rows[0].get('original_professional_source') == ctx['decision']
             and rows[0].get('consume_approval') is True
             and effect['decision_id'] == DISPATCH_POLICY
             and effect['action_id'] == request['action_id'] and effect['exit_code'] == 0,
             'actual original consumed dispatch and retained unknown-result journal required')
    return ctx, request, pin


def check_zero_release(ctx, request, run, jobs, approvals, main, same_head):
    import professional_web_execution as web

    release = [job for job in jobs['jobs'] if job.get('name') == 'release']
    web.need(run.get('id') == RUN and run.get('head_sha') == OLD_MAIN
             and run.get('status') == 'waiting' and run.get('conclusion') is None
             and run.get('run_attempt') == 1 and run.get('event') == 'workflow_dispatch'
             and run.get('path') == web.R3 and run.get('head_branch') == 'main'
             and run.get('actor', {}).get('id') == request['state']['actor']['id']
             and run.get('repository', {}).get('id') == ctx['repository_id']
             and run.get('repository', {}).get('full_name') == ctx['repository']
             and len(release) == 1 and release[0].get('status') == 'waiting'
             and release[0].get('conclusion') is None and not release[0].get('steps')
             and jobs.get('total_count') == len(jobs['jobs']) and approvals == []
             and main != OLD_MAIN and isinstance(main, str) and len(main) == 40
             and same_head.get('total_count') == 1
             and [row.get('id') for row in same_head.get('workflow_runs', [])] == [RUN],
             'one exact original run, no started release/review, and superseding main required')


@w.request_validation_context()
def cancel(root, path):
    import professional_web_execution as web
    from r3_known_zero_recovery import _read_api

    ctx, request, pin = source(root, path)
    ctx = {**ctx, 'r3_cancel_run_id': RUN}
    repo = 'repos/' + ctx['repository']
    run_path = repo + '/actions/runs/' + str(RUN)
    directory = Path(root) / 'logs/material-r3-stale-controls' / str(RUN)
    result_path = directory / 'result.json'
    intent_path = directory / 'intent.json'
    run = web._material_github_read(ctx, run_path)
    if intent_path.exists():
        intent = w.read_json(intent_path)
        web.need(intent.get('run_id') == RUN and intent.get('source_preflight') == pin,
                 'preserve original cancellation identity and unknown effect')
        result = {'run_id': RUN, 'status': run['status'], 'conclusion': run.get('conclusion'),
                  'new_cancel_request': False, 'prior_intent': w.file_digest(root, str(intent_path.relative_to(root)))}
        w.atomic_write_json(result_path, result)
        return result
    action = TASK + '-cancel-stale-r3-' + str(RUN) + '-v1'
    key = w.sha256_value([TASK, ctx['role'], action, 'site_ci_prepare', ctx['edge_scope']])
    with w.workflow_lock(root):
        prior = w.read_jsonl(Path(root) / w.POLICY_DECISIONS,
                            where={'autonomous_action_key': key, 'status': 'allow'})
        web.need(not prior, 'original cancel already issued; read its exact effect')
        validation = w._VALIDATION_CONTEXT.get()
        from material_r3_dispatch import reconcile_handoff_receipts
        validation.recheck(reconcile_change=lambda name, old, actual:
            reconcile_handoff_receipts(root, name, old, actual))
        observed = dt.datetime.now(dt.timezone.utc)
        read = lambda suffix: web._material_github_read(ctx, suffix)
        main = read(repo + '/git/ref/heads/main')['object']['sha']
        run = read(run_path)
        jobs = read(run_path + '/jobs?per_page=100')
        reviews = read(run_path + '/approvals')
        same_head = read(repo + '/actions/workflows/' + Path(web.R3).name +
                         '/runs?head_sha=' + OLD_MAIN + '&per_page=100')
        check_zero_release(ctx, request, run, jobs, reviews, main, same_head)
        actor = read('user')
        web.need(all(actor.get(k) == request['state']['actor'][k] for k in ('id', 'login')),
                 'original actor at cancellation boundary required')
        web.git(ctx, 'merge-base', '--is-ancestor', OLD_MAIN, main)
        web.need(not web.git(ctx, 'diff', '--name-only', OLD_MAIN, main, '--',
                            *ctx['paths'], 'supabase/functions', '.github/workflows/' + Path(web.R3).name,
                            'scripts/supabase-content-publish-release.mjs').strip(),
                 'superseding main must retain original material and protected release source')
        web.working_source(ctx, ctx['commit'])
        apr = web.reference(ctx, ctx['commit'], OLD_MAIN)
        web.need(not w.read_jsonl(Path(root) / w.APPROVAL_LEDGER, where={'approval_id': apr}),
                 'old Edge reference must never have been issued')
        web.need(not (Path(root) / 'backups' / TASK / 'R3-platform-binding-transport' / apr).exists(),
                 'existing or unknown platform binding attempt must be reconciled first')
        elapsed = (dt.datetime.now(dt.timezone.utc) - observed).total_seconds()
        web.need(0 <= elapsed <= 60, 'fresh same-run zero-effect checks required before cancellation')
        cancel_request = {'task_id': TASK, 'department': ctx['role'], 'action_id': action,
                          'action_class': 'site_ci_prepare', 'scope': ctx['edge_scope'],
                          'operation': 'r3_cancel', 'run_id': RUN, 'run_attempt': 1,
                          'old_head': OLD_MAIN, 'current_main': main, 'source_preflight': pin,
                          'observed_at': observed.isoformat(), 'release_steps_started': False,
                          'environment_approved': False, 'new_run_allowed': False}
        directory.mkdir(parents=True, exist_ok=False)
        w.atomic_write_json(directory / 'request.json', cancel_request)
        cancel_pin = w.file_digest(root, str((directory / 'request.json').relative_to(root)))
        decision = {'task_id': TASK, 'department': ctx['role'], 'action_id': action,
                    'action_class': 'site_ci_prepare', 'scope': ctx['edge_scope'],
                    'source_project_id': a.PROJECT, 'autonomous_action_key': key,
                    'approval_basis': a.MODE, 'original_authority': ctx['authorization'],
                    'original_professional_source': ctx['decision'], 'source_preflight': pin,
                    'exact_request': cancel_pin, 'payload_sha256': cancel_pin['sha256'],
                    'consume_approval': True, 'status': 'allow',
                    'approval_status': 'consumed_for_original_exact_autonomous_action',
                    'actual_action_allowed': True, 'checked_at': w.utc_timestamp(),
                    'run_id': RUN, 'current_main': main, 'release_steps_started': False,
                    'environment_approved': False, 'new_run_allowed_by_this_policy': False}
        decision['decision_id'] = 'pol-' + w.sha256_value(decision)[:20]
        w.atomic_write_json(intent_path, {'task_id': TASK, 'run_id': RUN, 'source_preflight': pin,
                            'policy_decision_id': decision['decision_id'], 'at': w.utc_timestamp()})
        w.append_jsonl_locked(Path(root) / w.POLICY_DECISIONS, decision)
    try:
        _read_api(ctx, 'POST', run_path + '/cancel')
        actual = _read_api(ctx, 'GET', run_path)
        result = {'run_id': RUN, 'status': actual['status'], 'conclusion': actual.get('conclusion'),
                  'new_cancel_request': True, 'decision_id': decision['decision_id']}
    except (w.WorkflowError, OSError, ValueError, subprocess.SubprocessError) as error:
        result = {'run_id': RUN, 'state': 'UNKNOWN_CANCEL_EFFECT_READ_EXACT_RUN_FIRST',
                  'new_cancel_request': 'UNKNOWN', 'error_type': type(error).__name__,
                  'decision_id': decision['decision_id']}
    w.atomic_write_json(result_path, result)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['cancel-stale'])
    parser.add_argument('--preflight', required=True)
    arguments = parser.parse_args()
    print(json.dumps(cancel(Path(__file__).resolve().parents[1], arguments.preflight), ensure_ascii=False))
