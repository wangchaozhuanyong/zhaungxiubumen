"""Prepare original PUB evidence and record it through the existing EN2 gate."""

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

import department_autonomy as a
import goal_delivery_runtime as g
import professional_cms_execution as cms
import workflow_control as w
from en2_preview_origin import _read_provider
from en2_supabase_origin import read_actual

TASK = cms._EN2_FORWARD_TASK
IDENTITY = ('task_id', 'department', 'action_id', 'action_class', 'scope')


def save(root, directory, name, value):
    path = directory / (name + '.json')
    with path.open('x', encoding='utf-8') as output:
        json.dump(value, output, ensure_ascii=False)
        output.write('\n')
    return w.file_digest(root, str(path.relative_to(root)))


def load(directory, name):
    return w.read_json(directory / (name + '.json'))


def observe(root, directory, refs):
    snapshot = g.restore_goal(root, w.read_json(w.snapshot_path(root, TASK)))
    source, target = cms._en2_forward_source(root, snapshot)
    sql = read_actual(root, refs['turn_id'], refs['row_call'], refs['key_call'],
                      refs['same_row_call'], live_publisher=True, include_row=True)
    origin, artifacts = _read_provider(root, refs['preview_run_id'],
                                       historical=False, include_artifacts=True)
    before = sql['verified_full_row']
    response = artifacts['dry-run.json']
    desired = response['payload_preview']
    a.require(sql['fresh_within_300_seconds'] and sql['original_key_count'] == 0
              and sql['same_row_effect'] == 'NO_BLOCKING_ROW_OBSERVED'
              and origin['expected_updated_at'] == before['updated_at']
              and artifacts['backup.json']['record'] == before,
              'original key and exact fresh full-row baseline must match zero-write preview')
    scope = source['scope']
    candidate = {'taskId': TASK, 'actionId': target['actionId'], 'operation': 'publish',
                 'scope': target['scope'], 'candidateVersion': target['candidateVersion']}
    preview = {
        'request': {'contentType': 'service', 'mode': 'dry-run', 'record': {**before, **desired},
                    'nextStatus': 'published', 'expectedUpdatedAt': before['updated_at'],
                    'managedCandidate': candidate},
        'response': response, 'url': 'https://exampleproject000000.supabase.co/functions/v1/content-publish',
        'http_status': artifacts['locked-dry-run-receipt.json']['http_status'],
    }
    effects = {'lookup_scope': {'task_id': TASK, 'action_id': target['actionId'],
                               'candidate_version': target['candidateVersion'], 'record_id': target['id'],
                               'scope': target['scope']},
               'rows': [], 'unknown_effect': False, 'same_row_conflict': False}
    before_pin = save(root, directory, 'fresh-before', before)
    req = {'task_id': TASK, 'department': 'publishing', 'sender_department': 'publishing',
           'action_id': target['actionId'], 'action_class': 'cms_write', 'scope': scope,
           'source_project_id': a.PROJECT, 'operation': 'field_patch', 'business_scope': scope,
           'physical_scope': target['scope'], 'table': target['table'], 'slug': target['slug'],
           'object_ids': [target['id']], 'changed_fields': target['changedFields'],
           'candidate_version': target['candidateVersion'],
           'professional_execution_source': source['registration'],
           'before': before_pin, 'desired': desired, 'expected_updated_at': before['updated_at'],
           'expected_version': before['version']}
    save(root, directory, 'base', {'request': req, 'refs': refs, 'preview': preview,
                                   'effects': effects, 'observed_at': sql['server_observed_at']})
    return {**preview, **effects}


def native_binding(root, native_path, command_id, values):
    pin = w.file_digest(root, native_path)
    turn, _, output = a.native_execution(root, pin, command_id, 'publishing')
    actual = json.loads(output)
    a.require(all(actual.get(key) == value for key, value in values.items()),
              'exact complete original PUB command output required')
    return {'actual_native': pin, 'command_id': command_id}, turn['id']


def assemble(root, directory, native_path, command_id):
    base = load(directory, 'base')
    req, preview, effects = (base[k] for k in ('request', 'preview', 'effects'))
    binding, turn = native_binding(root, native_path, command_id, {**preview, **effects})
    a.require(turn == base['refs']['turn_id'], 'original queries and command must belong to one PUB turn')
    identity = {key: req[key] for key in IDENTITY}
    identity['intent_sha256'] = w.sha256_value(req)
    facts = {**identity, 'current_row': req['before'], 'observed_at': base['observed_at'],
             'protected_preview': save(root, directory, 'preview', {**preview, **binding}),
             'original_key_effect_lookup': save(root, directory, 'effects', {**effects, **binding})}
    check = {**identity, 'status': 'PASS', 'production_write_allowed': False}
    backup = save(root, directory, 'backup', {**identity, 'complete_row': req['before']})
    save(root, directory, 'assembly', {'facts': facts, 'check': check, 'backup': backup})
    return {**facts, **check}


def record(root, directory, native_path, command_id):
    base, prepared = load(directory, 'base'), load(directory, 'assembly')
    facts, check = prepared['facts'], prepared['check']
    binding, turn = native_binding(root, native_path, command_id, {**facts, **check})
    a.require(turn == base['refs']['turn_id'], 'original PUB same-turn assembled evidence required')
    req = {**base['request'], 'facts': save(root, directory, 'facts', {**facts, **binding}),
           'self_check': save(root, directory, 'self-check', {**check, **binding}),
           'backup': prepared['backup']}
    envelope = save(root, directory, 'preflight', {'schema': 'professional-cms-fresh-preflight/v1',
                    'task_id': TASK, 'request': save(root, directory, 'request', req),
                    'provider_sources': base['refs']})
    return cms._record_en2_forward_preflight(root, TASK, envelope['path'])


def readiness(root, directory):
    request_pin = w.file_digest(root, str((directory / 'request.json').relative_to(root)))
    events = w.read_jsonl(root / w.WORKFLOW_EVENTS, where={
        'task_id': TASK, ('details', 'professional_cms_preflight', 'request'): request_pin,
        ('details', 'professional_cms_preflight', 'external_origin_state'): 'VERIFIED_PROTECTED_PROVIDER_RECEIPTS',
    })
    a.require(len(events) == 1, 'one recorded original PUB preflight required for readiness')
    snapshot = g.restore_goal(root, w.read_json(w.snapshot_path(root, TASK)))
    req = a.document(root, request_pin)
    value = {key: req[key] for key in (*IDENTITY, 'candidate_version')}
    value.update(decision='EXECUTE_ORIGINAL_AUTHORIZED_ACTION', decision_id=str(uuid4()),
                 decided_at=dt.datetime.now(dt.timezone.utc).isoformat(),
                 record_id=req['object_ids'][0], payload_sha256=w.sha256_value(req['desired']),
                 authorization_pin=snapshot['goal_delivery']['authorization_pin'],
                 execution_preflight=request_pin, execution_preflight_event_id=events[0]['event_id'])
    save(root, directory, 'readiness-native-value', value)
    return value


def bind_readiness(root, directory, native_path, command_id):
    value = load(directory, 'readiness-native-value')
    binding, turn = native_binding(root, native_path, command_id, value)
    a.require(turn == load(directory, 'base')['refs']['turn_id'],
              'original PUB same-turn readiness required')
    return {'readiness': save(root, directory, 'readiness', {**value, **binding}),
            'permission_issued': False}


def apply_original_policy_and_issue(root, directory, readiness_pin):
    """Run the original policy and issuer in sequence within the publisher's turn."""
    from en2_forward_issuer import project_url
    project_url(os.environ.get('SUPABASE_URL', ''))
    decision = a.document(root, readiness_pin)
    request_pin = w.file_digest(root, str((directory / 'request.json').relative_to(root)))
    req = a.document(root, request_pin)
    run_id = load(directory, 'base')['refs']['preview_run_id']
    events = w.read_jsonl(root / w.WORKFLOW_EVENTS, where={
        'task_id': TASK, 'event_id': decision.get('execution_preflight_event_id'),
        ('details', 'professional_cms_preflight', 'request'): request_pin,
        ('details', 'professional_cms_preflight', 'provider_origin_evidence', 'preview_run_id'): run_id,
    })
    a.require(decision.get('execution_preflight') == request_pin and type(run_id) is int and run_id > 0
              and len(events) == 1
              and req.get('task_id') == TASK and req.get('department') == 'publishing'
              and req.get('action_id') == 'save-kitchen-english-two-fields-v1'
              and req.get('action_class') == 'cms_write',
              'exact bound original EN2 publisher readiness required')
    policy, _ = w.policy_check(root, **{key: req[key] for key in IDENTITY},
                              source_project_id=req['source_project_id'],
                              payload_sha256=request_pin['sha256'], consume_approval=True)
    a.require(policy.get('status') == 'allow' and policy.get('actual_action_allowed') is True
              and policy.get('exact_request') == request_pin and policy.get('decision_id'),
              'one actual original EN2 policy must be consumed before issuer transport')
    command = [sys.executable, '-B', str(root / 'tools/managed_cms_permit_issuer.py'),
               '--target', 'english-kitchen-en2-exact-v1', '--operation', 'publish',
               '--dry-run-run-id', str(run_id), '--operations-decision', readiness_pin['path'],
               '--policy-decision-id', policy['decision_id'], '--github-actor-id', '276684684',
               '--issue-and-dispatch']
    # Preserve the issuer's own native output and every final recheck. If it
    # fails, leave the policy and any intent in place for original-key readback.
    subprocess.run(command, cwd=root, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('observe', 'assemble', 'record', 'record-and-readiness',
                                          'readiness', 'bind-readiness'))
    parser.add_argument('--directory', required=True, help='Existing project-local fresh EN2 evidence directory')
    parser.add_argument('--preview-run-id', type=int)
    parser.add_argument('--issue-after-policy', action='store_true')
    for key in ('turn-id', 'row-call', 'key-call', 'same-row-call', 'native', 'command-id'):
        parser.add_argument('--' + key)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    directory = w.safe_path(root, args.directory)
    if not directory.is_dir():
        parser.error('existing fresh evidence directory required')
    if args.issue_after_policy and args.action != 'bind-readiness':
        parser.error('issue requires original native readiness binding')
    with w.request_validation_context():
        if args.action == 'observe':
            refs = {k: getattr(args, k) for k in
                    ('turn_id', 'row_call', 'key_call', 'same_row_call', 'preview_run_id')}
            if not all(refs.values()):
                parser.error('original provider call IDs and new run ID required')
            result = observe(root, directory, refs)
        elif args.action == 'readiness':
            result = readiness(root, directory)
        else:
            if not args.native or not args.command_id:
                parser.error('original complete native readback and command ID required')
            if args.action == 'record-and-readiness':
                record(root, directory, args.native, args.command_id)
                result = readiness(root, directory)
            else:
                action = {'assemble': assemble, 'record': record,
                          'bind-readiness': bind_readiness}[args.action]
                result = action(root, directory, args.native, args.command_id)
    if args.issue_after_policy:
        apply_original_policy_and_issue(root, directory, result['readiness'])
        return
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
