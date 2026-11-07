"""Original publisher's two registered zero-write previews; no CMS Save grant."""
import argparse
import copy
import datetime as dt
import hashlib
import json
import os
import select
import subprocess
import sys
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

if __name__ == '__main__':
    sys.modules['material_preview_execution'] = sys.modules[__name__]

import department_autonomy as a
import workflow_control as w

TASK = 'fc-20261014-two-original-materials-exact-body-publication-v1'
REPO = 'example-owner/example-website'
WORKFLOW = '.github/workflows/content-publish-approved.yml'
PREFIX = 'PUB-zero-write-two-material-body-'
SCHEMA = 'original-PUB-two-material-zero-write-request/v1'
SLUGS = ('sintered-stone-grey', 'solid-surface-warm-white')
_SOURCE_PHASE = ContextVar('original_material_preview_source_phase', default=None)
_PREVIOUS_PREVIEW = ContextVar('original_material_previous_zero_preview', default=None)


@contextmanager
def previous_preview(root, run_id):
    need(run_id is None or type(run_id) is int and run_id > 0, 'exact prior zero-write run ID')
    token = _PREVIOUS_PREVIEW.set(None if run_id is None else (Path(root).resolve(), run_id))
    try:
        yield
    finally:
        _PREVIOUS_PREVIEW.reset(token)


@contextmanager
def source_phase():
    token = _SOURCE_PHASE.set({})
    try:
        yield
    finally:
        _SOURCE_PHASE.reset(token)


def need(ok, message):
    a.require(ok, 'Material preview: ' + message)


def action(slug):
    need(slug in SLUGS, 'one of the two original material objects only')
    prior = _PREVIOUS_PREVIEW.get()
    return PREFIX + slug + (('-after-zero-' + str(prior[1])) if prior else '')


def parse_action(value):
    for slug in SLUGS:
        base = PREFIX + slug
        if value == base:
            return slug, None
        suffix = str(value).removeprefix(base + '-after-zero-')
        if str(value).startswith(base + '-after-zero-') and suffix.isdigit() and int(suffix) > 0:
            return slug, int(suffix)
    need(False, 'exact original material preview action or its own zero-effect successor')


def directory(root, slug):
    return Path(root) / 'logs/material-zero-write-preview' / action(slug)


def request_path(root, slug, sha):
    need(isinstance(sha, str) and w.SHA256_PATTERN.fullmatch(sha) is not None,
         'exact immutable request digest required')
    return directory(root, slug) / 'requests' / (sha + '.json')


def gh(*args):
    return json.loads(subprocess.check_output(['gh', 'api', *args], text=True, timeout=30))


def dispatch_argv(slug):
    action(slug)
    return ['gh', 'workflow', 'run', Path(WORKFLOW).name, '-R', REPO, '--ref', 'main',
            '-f', 'mode=dry-run', '-f', 'target=two-original-material-body-' + slug,
            '-f', 'managed_operation=publish']


@w.request_validation_context()
def context(root, request):
    value = verified_source(root, request)
    # Executor identity is always live, even when static inputs are unchanged.
    publisher_live(root, request, value[1])
    return value


def verified_source(root, request):
    validation = w._VALIDATION_CONTEXT.get()
    phase = _SOURCE_PHASE.get()
    if phase is not None:
        key = (str(Path(root).resolve()), w.sha256_value({k: v for k, v in request.items() if k != 'PUB_native'}))
        if key not in phase:
            phase[key] = copy.deepcopy(_source_context(root, request))
        # This process owns the proof only until it exits. Every dependency,
        # including later-added identity inputs, is fenced before each use.
        validation.recheck()
        return copy.deepcopy(phase[key])
    for name in list(validation.files):
        validation.bytes(name)
    key = ('material-preview-source-only', str(Path(root).resolve()), w.sha256_value(request))
    if key not in validation.proofs:
        value = _source_context(root, request)
        validation.recheck()
        validation.proofs[key] = copy.deepcopy(value)
    value = copy.deepcopy(validation.proofs[key])
    return value


def late_identity(root, request, fifo):
    from goal_delivery_runtime import _native_document

    channel = w.safe_path(root, fifo)
    need(channel.resolve().is_relative_to(Path(root).resolve() / 'logs')
         and not channel.is_symlink() and channel.is_fifo(), 'one existing project-local FIFO only')
    fd = os.open(channel, os.O_RDWR | os.O_NONBLOCK)
    try:
        print('READY_FOR_ACTUAL_MATERIAL_PUB_IDENTITY', file=sys.stderr, flush=True)
        need(bool(select.select([fd], [], [], 120)[0]), 'fresh actual PUB identity timeout; no policy or transport')
        line = os.read(fd, 4096).decode('utf-8')
    finally:
        os.close(fd)
    need(line.endswith('\n') and len(line.splitlines()) == 1, 'one fresh request path required')
    fresh = a.document(root, w.file_digest(root, line.strip()))
    return validate_identity_refresh(root, request, fresh)


def validate_identity_refresh(root, request, fresh):
    from goal_delivery_runtime import _native_document

    need(set(fresh) == set(request)
         and {k: v for k, v in fresh.items() if k != 'PUB_native'}
             == {k: v for k, v in request.items() if k != 'PUB_native'},
         'only actual PUB identity can refresh; exact task/source/object/payload stay immutable')
    old = _native_document(root, request['PUB_native'])
    new = _native_document(root, fresh['PUB_native'])
    need(len(old['turns']) == len(new['turns']) == 1
         and old['turns'][0]['id'] == new['turns'][0]['id'], 'fresh self-read belongs to the same original PUB turn')
    return fresh


def native_anchor(turn):
    anchors = [item['id'] for item in turn.get('items', [])
               if item.get('id') and item.get('type') in ('commandExecution', 'mcpToolCall')
               and item.get('status') == 'completed' and not item.get('error')]
    need(bool(anchors), 'actual same-turn completed publisher command/self-read anchor required')
    return anchors[-1]


def publisher_live(root, request, binding):
    from goal_delivery_runtime import _native_document
    from en2_preview_web_identity import read_native_turn

    page = _native_document(root, request['PUB_native'])
    thread = page['thread']; turns = page['turns']
    need(all(thread.get(k) == binding[v] for k, v in
             {'id': 'task_id', 'title': 'title', 'cwd': 'cwd', 'hostId': 'host_id'}.items())
         and thread.get('kind') == 'codex' and thread.get('status', {}).get('type') == 'active'
         and len(turns) == 1 and turns[0].get('status') == 'inProgress'
         and not turns[0].get('error'), 'actual active original PUB self-read required')
    anchor = native_anchor(turns[0])
    actual = read_native_turn(root, {**binding, 'thread_id': binding['task_id']}, turns[0]['id'], anchor)
    hits = [item for item in actual.get('items', []) if item.get('id') == anchor]
    need(actual.get('id') == turns[0]['id'] and actual.get('completedAt') is None
         and actual.get('status') in ('inProgress', 'interrupted')
         and len(hits) == 1 and hits[0].get('status') == 'completed' and not hits[0].get('error'),
         'live original publisher turn and actual completed anchor; desktop timestamp omission is not a denial')


def _source_context(root, request):
    import paid_three_page_bounded_cms as cms

    fields = {'schema', 'task_id', 'slug', 'source_verification', 'PUB_native'}
    need(set(request) in (fields, fields | {'superseded_preview_run_id'})
         and request['schema'] == SCHEMA and request['task_id'] == TASK,
         'exact source request; no command, mode or permission override')
    prior = _PREVIOUS_PREVIEW.get()
    need(request.get('superseded_preview_run_id') == (prior[1] if prior else None),
         'request must bind the same exact verified previous zero preview')
    # Include the immutable desktop snapshot before memoizing source inputs.
    # Its current live status is verified separately on every boundary.
    a.document(root, request['PUB_native'])
    slug = request['slug']; action(slug)
    target = cms.two_original_material_targets(root)['two-original-material-body-' + slug]
    binding = w.department_registry(root)['publishing']['chat_binding']
    need(target['execution_owner'] == 'publishing'
         and target['execution_thread_id'] == binding['task_id']
         and Path.cwd().resolve() == Path(root).resolve() == Path(binding['cwd']).resolve(),
         'original rotated publisher and original project only')
    source = a.document(root, request['source_verification'])
    need(source.get('schema') == cms.MATERIAL_CURRENT_PROOF
         and source.get('source_issuer') == 'designated-development'
         and source.get('registration_grants_CMS_write_authority') is False
         and source.get('status') == 'DEPLOYED_SOURCE_VERIFIED'
         and all(source.get(k) == target[k] for k in
                 ('task_id', 'action_id', 'candidate_version', 'scope', 'record_id')),
         'actual original WEB deployed source and unchanged per-object tuple')
    deployed = cms._material_site_doc(source['website_deployment'])
    main = deployed['production_website_sha']
    run = cms._material_site_doc(deployed['run_proof'])['run']
    need(main == cms._material_source_production_sha(source, deployed)
         and deployed.get('status') == 'PASS_ACTUAL_PRODUCTION_EDGE_SOURCE_AND_RECOVERY_BACKUP'
         and run.get('id') == deployed.get('run_id')
         and run.get('head_sha') == main and run.get('status') == 'completed'
         and run.get('conclusion') == 'success', 'actual completed deployed material carrier')
    cms._current_material_deployment(root, deployed, main, run, source['source_candidate_head'])
    cms.material_current_row(source, target, a.document(root, {
        'path': target['candidate'][0], 'sha256': target['candidate'][1],
        'size': (Path(root) / target['candidate'][0]).stat().st_size}))
    return target, binding, main


def live(target, main):
    observed = dt.datetime.now(dt.timezone.utc)
    actor = gh('user')
    current = gh('repos/' + REPO + '/git/ref/heads/main')
    workflow = gh('repos/' + REPO + '/actions/workflows/' + Path(WORKFLOW).name)
    runs = gh('repos/' + REPO + '/actions/workflows/' + Path(WORKFLOW).name
              + '/runs?head_sha=' + main + '&per_page=100')
    need(actor.get('id') == 276684684 and current.get('object', {}).get('sha') == main
         and workflow.get('path') == WORKFLOW and workflow.get('state') == 'active'
         and runs.get('total_count', 101) <= 100,
         'actual original account/current main/active protected workflow and complete bounded run inventory')
    rows = runs.get('workflow_runs', [])
    namespace = 'two-original-material-body-' + target['slug']
    prior = _PREVIOUS_PREVIEW.get()
    parent_proof = None
    if prior is None:
        need(not any(namespace in str(row.get('display_title', '')) for row in rows),
             'an original same-target run exists; reconcile its exact effect, never redispatch')
    else:
        from material_preview_refresh import verify
        parent_proof = verify(prior[0], prior[1], target, main, rows)
    need(not any(row.get('status') != 'completed' for row in rows),
         'protect an existing content workflow before starting the next object')
    need(0 <= (dt.datetime.now(dt.timezone.utc) - observed).total_seconds() <= 60,
         'provider facts expired during zero-write preparation')
    return {'observed_at': observed.isoformat(), 'actor_id': actor['id'],
            'main_sha': main, 'prior_run_ids': [row['id'] for row in rows],
            **({'verified_zero_write_predecessor': parent_proof} if parent_proof else {})}


def policy(root, requested):
    aid = requested.get('action_id', '')
    if not str(aid).startswith(PREFIX):
        return None
    slug, parent = parse_action(aid)
    with previous_preview(root, parent):
        return _policy(root, requested, slug)


def _policy(root, requested, slug):
    aid = requested['action_id']
    need(aid == action(slug), 'own exact predecessor action')
    need(requested.get('task_id') == TASK and requested.get('department') == 'publishing'
         and requested.get('action_class') == 'site_ci_prepare'
         and requested.get('consume_approval') is True
         and not any(requested.get(k) for k in ('approval_id', 'target_project_id', 'target_department')),
         'only the original PUB zero-write policy; no borrowed Save or cross-project grant')
    with w.workflow_lock(root), w.request_validation_context() as validation:
        path = request_path(root, slug, requested.get('payload_sha256'))
        if not path.exists():
            # Preserve the first installed reader's already-prepared input.
            # It must still match the exact requested digest; the same action
            # policy and transport-intent checks below prevent any replay.
            legacy = directory(root, slug) / 'request.json'
            need(legacy.is_file() and w.file_digest(root, str(legacy.relative_to(root)))['sha256']
                 == requested.get('payload_sha256'), 'exact immutable original preview request required')
            path = legacy
        pin = w.file_digest(root, str(path.relative_to(root)))
        request = a.document(root, pin)
        target, binding, main = context(root, request)
        need(requested.get('scope') == target['scope']
             and requested.get('source_project_id') == binding['project_id']
             and requested.get('payload_sha256') == pin['sha256'], 'own exact source and object scope')
        prior = w.read_jsonl(Path(root) / w.POLICY_DECISIONS,
                            where={'task_id': TASK, 'action_id': aid, 'status': 'allow'})
        need(not prior and not (directory(root, slug) / 'intent.json').exists(),
             'original policy or transport intent exists; read its effect without replay')
        facts = live(target, main)
        validation.recheck(); now = w.utc_timestamp()
        row = {**{k: requested[k] for k in ('task_id', 'department', 'action_id', 'action_class', 'scope')},
               'source_project_id': binding['project_id'], 'payload_sha256': pin['sha256'],
               'decision_id': 'pol-' + w.sha256_value([requested, now])[:20],
               'status': 'allow', 'checked_at': now, 'single_use': True, 'consume_approval': True,
               'approval_basis': 'original_PUB_registered_material_necessary_zero_write_preview',
               'exact_request': pin, 'provider_facts': facts,
               'allowed_workflow': WORKFLOW, 'allowed_mode': 'dry-run',
               'target': 'two-original-material-body-' + slug,
               'head_sha': main, 'actual_action_allowed': True,
               'Save_allowed': False, 'CMS_permit_issued': False}
        ledger = Path(root) / w.POLICY_DECISIONS
        before = validation.bytes(ledger) if ledger.exists() else b''
        w.append_jsonl_locked(ledger, row)
        expected = before + (json.dumps(row, ensure_ascii=False, sort_keys=True) + '\n').encode()
        need(ledger.read_bytes() == expected, 'policy append raced another writer; preserve intent and reconcile')
        # Reconcile only this exact append under the original workflow lock.
        # All other source dependencies keep their original commit fence.
        validation.bytes(ledger)
    return row, [Path(root) / w.POLICY_DECISIONS]


def execute(root, input_path, *, identity_input_fifo=None):
    request = a.document(root, w.file_digest(root, input_path))
    with previous_preview(root, request.get('superseded_preview_run_id')):
        return _execute(root, input_path, identity_input_fifo=identity_input_fifo)


@source_phase()
@w.request_validation_context()
def _execute(root, input_path, *, identity_input_fifo=None):
    request = a.document(root, w.file_digest(root, input_path))
    slug = request['slug']; action(slug)
    folder = directory(root, slug)
    verified_source(root, request)
    if identity_input_fifo is not None:
        request = late_identity(root, request, identity_input_fifo)
    target, binding, main = context(root, request)
    raw = (json.dumps(request, ensure_ascii=False, indent=2) + '\n').encode()
    path = request_path(root, slug, hashlib.sha256(raw).hexdigest())
    if path.exists():
        need(path.read_bytes() == raw, 'preserve immutable original preview request')
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('xb') as handle:
            handle.write(raw)
    pin = w.file_digest(root, str(path.relative_to(root)))
    decision, _ = w.policy_check(root, task_id=TASK, department='publishing',
        action_id=action(slug), action_class='site_ci_prepare', scope=target['scope'],
        consume_approval=True, source_project_id=binding['project_id'], payload_sha256=pin['sha256'])
    need(decision.get('status') == 'allow' and decision.get('actual_action_allowed') is True
         and decision.get('Save_allowed') is False, 'normal own zero-write policy required')
    facts = live(target, main)
    w._VALIDATION_CONTEXT.get().recheck()
    argv = dispatch_argv(slug)
    with w.workflow_lock(root):
        intent = folder / 'intent.json'
        need(not intent.exists(), 'unknown original dispatch intent must not be repeated')
        with intent.open('x', encoding='utf-8') as handle:
            json.dump({'task_id': TASK, 'decision_id': decision['decision_id'],
                       'request': pin, 'argv': argv, 'provider_facts': facts,
                       'status': 'INTENT_PERSISTED_BEFORE_TRANSPORT'}, handle, ensure_ascii=False, indent=2)
    outcome = subprocess.run(argv, capture_output=True, text=True, timeout=60)
    result = {'task_id': TASK, 'decision_id': decision['decision_id'], 'exit_code': outcome.returncode,
              'status': 'DISPATCH_ACCEPTED_NOT_ACK' if outcome.returncode == 0 else 'UNKNOWN_READ_ORIGINAL_KEY',
              'stdout': outcome.stdout, 'stderr': outcome.stderr, 'Save_allowed': False}
    w.atomic_write_json(folder / 'result.json', result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['run'])
    parser.add_argument('--input', required=True)
    parser.add_argument('--identity-input-fifo')
    args = parser.parse_args()
    try:
        print(json.dumps(execute(Path(__file__).resolve().parents[1], args.input,
            identity_input_fifo=args.identity_input_fifo), ensure_ascii=False, indent=2))
    except (w.WorkflowError, ValueError, KeyError, OSError, subprocess.SubprocessError) as error:
        parser.exit(1, str(error) + '\n')


if __name__ == '__main__':
    main()
