"""Fresh provider facts after immutable material source validation, never a permit."""
import datetime as dt
import argparse
import json
import subprocess
from pathlib import Path

import department_autonomy as a
import workflow_control as w

TASK = 'fc-20261014-two-original-materials-exact-body-publication-v1'


def pending(root, ctx, request):
    import professional_web_execution as web
    import r3_platform_binding_transport as carrier

    state = request['state']
    main = state['main_sha']
    run_id = state['r3_run']['id']
    web.need(ctx.get('material_registry_test_successor') is True
             and ctx['task'] == request['task_id'] == TASK
             and ctx['role'] == request['department'] == 'designated-development'
             and request['operation'] == 'edge_deploy' and request['action_class'] == 'site_publish'
             and request['scope'] == ctx['edge_scope']
             and request['action_id'] == web.action_id(ctx, 'edge_deploy', ctx['commit'], main)
             and Path.cwd().resolve() == Path(ctx['worktree']).resolve(),
             'fresh checks belong only to the normal original material WEB Edge source')
    dispatch = web.action_id(ctx, 'r3_dispatch', ctx['commit'], main)
    rows = w.read_jsonl(Path(root) / w.POLICY_DECISIONS,
                       where={'task_id': TASK, 'action_id': dispatch, 'status': 'allow'})
    web.need(len(rows) == 1 and rows[0].get('consume_approval') is True
             and rows[0].get('original_professional_source') == ctx['decision']
             and rows[0].get('external_execution_department') == ctx['role'],
             'one actual normal consumed dispatch for this exact current material main required')
    original = a.document(root, rows[0]['exact_request'])
    web.need(original['operation'] == 'r3_dispatch' and original['state']['main_sha'] == main
             and original['state']['actor'] == state['actor']
             and original['desired']['approval_id'] == request['desired']['approval_id']
             and original['desired']['release_action_id'] == request['action_id'],
             'same real dispatch actor/head/reference and exact Edge action required')
    observed = dt.datetime.now(dt.timezone.utc)
    api = carrier.GitHub(ctx)
    facts = carrier.platform_facts(api, ctx, run_id, request)
    base = 'repos/' + ctx['repository']
    old = api.call('GET', base + '/actions/runs/42266933185')
    same = web._material_github_read(ctx, base + '/actions/workflows/' + Path(web.R3).name
                                     + '/runs?head_sha=' + main + '&per_page=100')
    web.need(old.get('status') == 'completed' and old.get('conclusion') == 'cancelled'
             and same.get('total_count') == 1
             and [row.get('id') for row in same.get('workflow_runs', [])] == [run_id],
             'actual old cancellation and one original same-head run required')
    web.working_source(ctx, ctx['commit'])
    web.need(not web.git(ctx, 'diff', '--name-only', ctx['commit'], main, '--', *ctx['paths'],
                        'supabase/functions', web.R3, 'scripts/supabase-content-publish-release.mjs',
                        'package-lock.json').strip(), 'current main must preserve exact approved material release source')
    web.need(0 <= (dt.datetime.now(dt.timezone.utc) - observed).total_seconds() <= 60,
             'provider facts expired during the bounded live check')
    return {**facts, 'observed_at': observed.isoformat(), 'dispatch_policy': rows[0]['decision_id'],
            'external_permission_issued': False, 'source_request_timestamp_changed': False}


@w.request_validation_context()
def execute(root, path):
    """One original WEB process; source first, live checks at each effect boundary."""
    import professional_web_execution as web
    import r3_platform_binding_transport as carrier

    pin = w.file_digest(root, path)
    envelope = a.document(root, pin)
    request = a.document(root, envelope['request'])
    item, actual, registered, ctx = web.preflight(root, TASK, request['action_id'],
        request['action_class'], request['scope'], request['department'])
    web.need(registered == pin and request == actual and item['request'] == envelope['request'],
             'one actual registered original WEB Edge preflight required')
    pending(root, ctx, request)
    reference = web.reference(ctx, request['state']['candidate_commit'], request['state']['main_sha'])
    api = carrier.GitHub(ctx)
    run_path = 'repos/' + ctx['repository'] + '/actions/runs/' + str(request['state']['r3_run']['id'])
    directory = Path(root) / 'logs/material-edge-execution' / reference
    if (directory / 'intent.json').exists():
        observed = api.call('GET', run_path)
        return {'state': 'EXISTING_REVIEW_INTENT_READ_ONLY_NO_REPLAY', 'run_id': observed['id'],
                'run_status': observed['status'], 'run_conclusion': observed.get('conclusion')}
    old = w.effective_approvals(root).get(reference)
    web.need(old is None or old.get('status') == 'active',
             'consumed/revoked reference requires original effect reconciliation, never another execution')
    human = ctx.get('current_owner_message') or a.document(root, ctx['authorization'])
    fields = {key: request[key] for key in ('task_id', 'action_id', 'action_class', 'scope')}
    issued, _ = web.record_approval(root, **fields, source_thread_id=human['source_thread_id'],
        source_message_ref=human['message']['id'], source_evidence=path)
    web.need(issued['approval_id'] == reference and issued['result'] in {'recorded', 'duplicate_ignored'},
             'actual normal own short-lived reference required')
    carried = carrier.install(root, TASK, reference)
    web.need(carried['state'] in {'TRANSPORTED_AND_READ_BACK', 'EXACT_BINDING_ALREADY_PRESENT'},
             'actual original run binding must be read back; unknown transport is not retried')
    policy, _ = web.policy(root, {**fields, 'department': request['department'],
        'source_project_id': request['source_project_id'], 'payload_sha256': item['request']['sha256'],
        'consume_approval': True})
    web.need(policy.get('status') == 'allow' and policy.get('actual_action_allowed') is True,
             'normal exact once-only Edge policy must be consumed before environment review')
    facts = pending(root, ctx, request)
    current = w.effective_approvals(root).get(reference)
    web.need(current and current['status'] == 'consumed'
             and current['platform_binding'] == issued['platform_binding'], 'original consumed reference required')
    carrier.validate_binding(current['platform_binding'], own=True)
    environments = api.call('GET', run_path + '/pending_deployments')
    matches = [row for row in environments if row.get('environment', {}).get('name') == carrier.ENV]
    web.need(len(matches) == 1 and matches[0].get('current_user_can_approve') is True,
             'actual original environment is still pending for this exact original actor')
    body = {'environment_ids': [matches[0]['environment']['id']], 'state': 'approved',
            'comment': 'Original materials PR 312 run-bound Edge release ' + reference}
    with w.workflow_lock(root):
        web.need(not (directory / 'intent.json').exists(), 'original review intent exists; no repeated review')
        w._VALIDATION_CONTEXT.get().recheck()
        carrier.validate_binding(current['platform_binding'], own=True)
        web.need(0 <= (dt.datetime.now(dt.timezone.utc) -
                      w._parse_observed_at(facts['observed_at'])).total_seconds() <= 60,
                 'actual provider facts expired before review transport')
        directory.mkdir(parents=True, exist_ok=True)
        w.atomic_write_json(directory / 'intent.json', {'task_id': TASK, 'source_preflight': pin,
            'policy_decision_id': policy['decision_id'], 'approval_id': reference, 'body': body,
            'run_id': facts['run_id'], 'at': w.utc_timestamp()})
    try:
        result = subprocess.run([api.cli, 'api', '--hostname', 'github.com', '--method', 'POST',
            run_path + '/pending_deployments', '--input', '-'], input=json.dumps(body), text=True,
            capture_output=True, cwd=ctx['worktree'], timeout=25)
        receipt = {'state': 'REVIEW_REQUEST_ACCEPTED' if result.returncode == 0 else 'UNKNOWN_REVIEW_EFFECT_NO_REPLAY',
                   'run_id': facts['run_id'], 'exit_code': result.returncode,
                   'response': result.stdout, 'at': w.utc_timestamp(), 'deployment_completed': False}
    except (OSError, subprocess.SubprocessError) as error:
        receipt = {'state': 'UNKNOWN_REVIEW_EFFECT_NO_REPLAY', 'run_id': facts['run_id'],
                   'error_type': type(error).__name__, 'at': w.utc_timestamp(), 'deployment_completed': False}
    w.atomic_write_json(directory / 'result.json', receipt)
    return {key: value for key, value in receipt.items() if key != 'response'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['run'])
    parser.add_argument('--preflight', required=True)
    args = parser.parse_args()
    print(json.dumps(execute(Path(__file__).resolve().parents[1], args.preflight), ensure_ascii=False))
