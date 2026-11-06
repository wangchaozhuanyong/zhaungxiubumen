"""Bounded original PR 312 R3 recovery from a proven local pre-transport failure."""
import json
import datetime as dt
from pathlib import Path
import shutil
import subprocess

import department_autonomy as a
import workflow_control as w

TASK = 'fc-20261014-two-original-materials-exact-body-publication-v1'
ACTION = TASK + '-original-body-c29b09e4cdc4-r3-dispatch-30781b6b9efa-v1'
OLD_POLICY = 'pol-628e22ad5526671b93ba'
HANDOFF_ACTION = 'PUB-materials-PR312-original-R3-live-launch-20261107-v1'
HANDOFF_SUCCESSOR = 'PUB-materials-PR312-original-R3-receipts-reconciled-20261107-v1'
DIRECTORY = ('logs/handoffs/2026-10-29-two-materials-current-owner-WEB-continuation-v1/designated-development/'
             'actual-PR312-c29b-20261106.5N3xWqMf/r3-dispatch.YKPdoygJ')
REPORT = {'path': DIRECTORY + '/WEB-ACTUAL-PR312-MERGE-PAGES-R3-PRETRANSPORT-ZERO-RESULT.json',
          'sha256': 'ec02f039ca8475759697fcfbb12aabd2c0fe56046b250a1e0dc406aa1aa37157', 'size': 6133}
NATIVE = {'path': DIRECTORY + '/ACTUAL-COMPLETED-WEB-R3-PRETRANSPORT-ZERO.json',
          'sha256': 'd4640b9c53396f9bc4e1e45a9219e41328ab98733cc907ddbd6747e1ecf7d97f', 'size': 7331}


def reconcile_handoff_receipts(root, name, previous, actual):
    """Accept only the original transport acknowledgements appended during preflight."""
    if (Path(name) != (Path(root) / w.WORKFLOW_EVENTS).resolve()
            or not previous.endswith(b'\n') or not actual.startswith(previous) or not actual.endswith(b'\n')):
        return False
    try:
        old_rows = [json.loads(line) for line in previous.splitlines() if line.strip()]
        new_rows = [json.loads(line) for line in actual[len(previous):].splitlines()]
        if not old_rows or not 1 <= len(new_rows) <= 2:
            return False
        prior_goal = next(row['details']['goal_delivery'] for row in reversed(old_rows)
                          if row.get('task_id') == TASK and 'goal_delivery' in row.get('details', {}))
        old_receipts = prior_goal.get('collaboration_records', [])
        previous_hash = old_rows[-1]['event_hash']
        accepted = ('queue_accepted', 'message_received')
        prior_status = handoff_action = None
        for row in new_rows:
            detail = row['details']
            pin = detail['collaboration_receipt']
            status = detail['actual_transport_status']
            if (row['task_id'] != TASK or row['state'] != 'evidence_received'
                    or row['previous_event_hash'] != previous_hash
                    or row['event_hash'] != w.sha256_value({k: v for k, v in row.items() if k != 'event_hash'})
                    or set(detail) != {'actual_transport_status', 'collaboration_receipt', 'external_permission_issued', 'goal_delivery'}
                    or detail['external_permission_issued'] is not False
                    or status not in accepted or (prior_status is not None and (prior_status, status) != accepted)
                    or pin in old_receipts or detail['goal_delivery'] != {**prior_goal, 'collaboration_records': [*old_receipts, pin]}):
                return False
            receipt = a.document(root, pin)
            if (receipt['task_id'] != TASK or receipt['action_id'] not in (HANDOFF_ACTION, HANDOFF_SUCCESSOR)
                    or (handoff_action is not None and receipt['action_id'] != handoff_action)
                    or receipt['status'] != status or receipt['source_kind'] != 'official_native_queue'):
                return False
            old_receipts = [*old_receipts, pin]
            handoff_action = receipt['action_id']
            previous_hash, prior_status = row['event_hash'], status
        return True
    except (OSError, ValueError, TypeError, AttributeError, KeyError, StopIteration, w.WorkflowError):
        return False


def recovery_policy(root, ctx, request, key, issued):
    import professional_web_execution as web
    from goal_delivery_runtime import _native_document

    need = web.need
    need(len(issued) == 1 and issued[0]['decision_id'] == OLD_POLICY,
         'one original spent R3 dispatch policy only; reconcile existing effect before another attempt')
    old = issued[0]
    report = a.document(root, REPORT)
    previous = a.document(root, old['exact_request'])
    need(ctx.get('material_registry_test_successor') and ctx['task'] == request['task_id'] == report['task_id'] == TASK
         and request['operation'] == previous['operation'] == 'r3_dispatch'
         and request['action_id'] == previous['action_id'] == report['r3']['action_id'] == ACTION
         and old['autonomous_action_key'] == key and old['department'] == ctx['role']
         and old.get('original_professional_source') == ctx['decision']
         and request['desired'] == previous['desired']
         and request['state']['main_sha'] == report['actual_main']
         and report['r3']['policy'] == OLD_POLICY and report['r3']['transport_intent_present'] is False
         and report['r3']['transport_launch_observed'] is False
         and report['r3']['remote_same_head_runs'] == {'total_count': 0, 'workflow_runs': []},
         'original material R3 source, action, scope and proven zero-transport result required')
    page = _native_document(root, NATIVE)
    binding = ctx['binding']
    need(all(page['thread'].get(k) == binding[v] for k, v in {'id': 'thread_id', 'title': 'title', 'cwd': 'cwd'}.items())
         and len(page['turns']) == 1 and page['turns'][0]['status'] == 'completed'
         and not page['turns'][0].get('error'), 'actual completed original WEB turn required')
    items = page['turns'][0]['items']
    failed = [item for item in items if item.get('id') == report['r3']['failed_native_command']]
    need(len(failed) == 1 and failed[0]['type'] == 'commandExecution' and failed[0]['status'] == 'failed'
         and failed[0]['exitCode'] == 1 and Path(failed[0]['cwd']).resolve() == Path(ctx['worktree']).resolve(),
         'original failed pre-transport command and bound worktree required')
    captured = failed[0].get('output')
    need(isinstance(captured, dict) and set(captured) == {'text', 'truncated'}
         and captured['truncated'] is False and isinstance(captured['text'], str),
         'complete original failed command output required')
    output = captured['text']
    need(OLD_POLICY in output and 'gate.py", line 59' in output and 'git/ref/heads/main' in output
         and output.rstrip().endswith(report['r3']['failure'])
         and not (Path(root) / DIRECTORY / 'R3-DISPATCH-TRANSPORT-INTENT.json').exists()
         and not (Path(root) / DIRECTORY / 'R3-DISPATCH-TRANSPORT-READBACK.json').exists(),
         'normal client stopped at a read-only main response before recording any dispatch intent')
    return {'recovery_of_policy': OLD_POLICY, 'known_zero_r3_dispatch_source': REPORT,
            'known_zero_r3_dispatch_native': NATIVE, 'recovery_attempt': 1}


def run(root, task, path):
    import professional_web_execution as web

    preflight = a.document(root, w.file_digest(root, path))
    request = a.document(root, preflight['request'])
    web.need(task == request['task_id'] == TASK and request['action_id'] == ACTION
             and request['operation'] == 'r3_dispatch', 'only the original bounded PR 312 R3 recovery')
    launch = {}

    def verify(ctx, req, pin, argv):
        web.need(req == request and pin == w.file_digest(root, path)
                 and Path.cwd().resolve() == Path(ctx['worktree']).resolve(),
                 'current exact normal preflight and original WEB worktree required')
        exe = shutil.which(argv[0])
        web.need(exe, 'local GitHub CLI required before policy consumption')
        repo = 'repos/' + ctx['repository']
        desired = req['desired']
        main = desired['expected_main_sha']
        workflow = repo + '/actions/workflows/' + Path(web.R3).name + '/runs'
        head_runs = f'{workflow}?head_sha={main}&per_page=100'
        read = lambda endpoint: web._material_github_read(ctx, endpoint)
        observed = dt.datetime.now(dt.timezone.utc)
        actor, repository = read('user'), read(repo)
        active = [row for row in read(workflow + '?per_page=50')['workflow_runs'] if row['status'] != 'completed']
        exact_runs = read(head_runs)
        pull = read(repo + '/pulls/312')
        public = subprocess.check_output(
            ['curl', '--fail', '--silent', '--show-error', '--max-time', '10', '-H', 'Cache-Control: no-cache',
             'https://company.example/__flashcast/version'], cwd=ctx['worktree'], timeout=12)
        public_version = json.loads(public).get('deploymentVersion')
        web.need(all(actor.get(k) == req['state']['actor'][k] for k in ('id', 'login'))
                 and repository['id'] == ctx['repository_id'] and repository['full_name'] == ctx['repository']
                 and read(repo + '/git/ref/heads/main')['object']['sha'] == main
                 and pull['number'] == 312 and pull['merged'] is True and pull['merge_commit_sha'] == main
                 and pull['head']['sha'] == ctx['commit'] and pull['base']['ref'] == 'main' and public_version == main
                 and exact_runs['total_count'] == 0 and exact_runs['workflow_runs'] == [] and not active,
                 'actual original actor, merged PR, public/main version, zero same-head run and no active competing R3 required')
        web.working_source(ctx, ctx['commit'])
        inputs = {'mode': 'deploy', 'edge_function': 'content-publish', 'expected_sha': main,
                  'approval_id': desired['approval_id'], 'task_id': TASK, 'action_id': desired['release_action_id'],
                  'action_class': desired['release_action_class'], 'scope': desired['release_scope']}
        launch.update(ctx=ctx, argv=[exe, *argv[1:]], inputs=inputs, head_runs=head_runs)
        return {'observed_at': observed.isoformat(), 'repository_id': repository['id'], 'actor_id': actor['id'],
                'pull': 312, 'main': main, 'public_version': public_version,
                'same_head_runs': exact_runs['total_count'], 'competing_active_runs': len(active)}

    fields = {key: request[key] for key in ('task_id', 'department', 'action_id', 'action_class', 'scope', 'source_project_id')}
    decision, _ = web.policy(root, {**fields, 'consume_approval': True,
                                   'payload_sha256': preflight['request']['sha256']}, _material_launch_check=verify)
    if decision['status'] != 'allow':
        return decision
    outcome = {'decision_id': decision['decision_id'], 'action_id': ACTION, 'result': 'transport_effect_unknown'}
    try:
        process = subprocess.run(launch['argv'], input=json.dumps(launch['inputs']), text=True,
                                 cwd=launch['ctx']['worktree'], capture_output=True, timeout=45)
        outcome['exit_code'] = process.returncode
        rows = web._material_github_read(launch['ctx'], launch['head_runs'])['workflow_runs']
        runs = [row for row in rows if row.get('head_sha') == launch['inputs']['expected_sha']
                and row.get('path') == web.R3 and row.get('event') == 'workflow_dispatch'
                and row.get('actor', {}).get('id') == request['state']['actor']['id']]
        if process.returncode == 0 and len(rows) == len(runs) == 1:
            outcome.update(result='dispatched_and_read_back', run_id=runs[0]['id'])
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        outcome['transport_or_readback_error'] = type(error).__name__
    w.atomic_write_json(Path(root) / 'logs' / 'material-r3-dispatch-execution' / (decision['decision_id'] + '.json'), outcome)
    return outcome
