"""Fresh admission of the original PUB's newly registered two-material actions.

No old permit transfers and no rotation flag changes. The normal CMS policy,
source/preview checks and single-use issuer still run after this admission.
"""
import datetime as dt
import json
import shlex
from pathlib import Path

import workflow_control as w

TASK = 'fc-20261014-two-original-materials-exact-body-publication-v1'


def need(ok, message):
    if not ok:
        raise w.WorkflowError('Current material PUB admission: ' + message)


def canonical_registration(root, command, path):
    try:
        argv = shlex.split(command)
        if len(argv) == 3 and argv[:2] in (['/bin/zsh', '-lc'], ['/bin/bash', '-lc']):
            argv = shlex.split(argv[2])
        return (len(argv) == 8 and Path(argv[0]).name.startswith('python') and argv[1] == '-B'
                and Path(root, argv[2]).resolve() == Path(root, 'tools/goal_delivery_runtime.py').resolve()
                and argv[3:] == ['preflight-record', '--task-id', TASK, '--input', path])
    except (ValueError, TypeError):
        return False


def registration_proof(root, binding, preflight, event):
    import department_event_dispatcher as dispatcher

    rpc = dispatcher.RPC([dispatcher.native_queue_capability(Path(root)), 'app-server', '--listen', 'stdio://'])
    try:
        thread = rpc.call('thread/read', {'threadId': binding['task_id'], 'includeTurns': False})['thread']
        page = rpc.call('thread/turns/list', {'threadId': binding['task_id'], 'limit': 8,
                        'sortDirection': 'desc', 'itemsView': 'full'})
    finally:
        rpc.close()
    need(thread.get('id') == binding['task_id'] and thread.get('name') == binding['title']
         and Path(thread.get('cwd', '')).resolve() == Path(binding['cwd']).resolve()
         and thread.get('projectId') in (None, binding['project_id']), 'actual original current PUB identity')
    at = w._parse_observed_at(event['created_at'])
    need(at is not None and 0 <= (dt.datetime.now(dt.timezone.utc) - at).total_seconds() <= 86400,
         'fresh new registration, not a transferred old permit')
    found = []
    for turn in page.get('data', []):
        for item in turn.get('items', []):
            if not canonical_registration(root, item.get('command', ''), preflight['path']):
                continue
            if item.get('status') != 'completed' or item.get('exitCode') != 0:
                continue
            value = json.loads(w._source_continuation_execution_output(item))
            if value.get('result') == 'duplicate_ignored' and value.get('external_permission_issued') is False:
                continue
            start, end = item.get('startedAtMs'), item.get('completedAtMs')
            need(item.get('type') == 'commandExecution' and item.get('status') == 'completed'
                 and item.get('exitCode') == 0 and type(start) is int and type(end) is int
                 and Path(item.get('cwd', '')).resolve() == Path(root).resolve()
                 and start <= at.timestamp() * 1000 + 1000 <= end + 1000
                 and end <= at.timestamp() * 1000 + 60000,
                 'actual successful normal PUB registration command and journal chronology')
            need(value.get('result') == 'recorded' and value.get('external_permission_issued') is False,
                 'actual registration receipt, never a printed permission')
            found.append({'thread_id': binding['task_id'], 'turn_id': turn['id'],
                          'command_id': item['id'], 'completed_at_ms': end})
    need(len(found) == 1, 'one real current PUB normal registration command in bounded relevant history')
    return found[0]


@w.request_validation_context()
def admit(root, requested):
    import paid_three_page_bounded_cms as cms
    import department_rotation as rotation
    import material_preflight_metadata as metadata
    from goal_delivery_runtime import restore_goal

    need(requested.get('task_id') == TASK and requested.get('department') == 'publishing'
         and requested.get('action_class') == 'cms_write' and requested.get('consume_approval') is True
         and (not requested.get('approval_id') or str(requested['approval_id']).startswith('apr-material-')),
         'new own policy for an original material action only')
    if requested.get('approval_id'):
        from material_original_owner_approval import active
        active(root, requested, requested['approval_id'])
    expected = [cms._material_tuple(*row) for row in cms.MATERIAL_ROWS]
    need(sum((requested['task_id'], requested.get('action_id'), entry[2], requested.get('scope'),
              requested['department'], requested['action_class']) == entry for entry in expected) == 1,
         'exact original two-body scope, actor and forward action')
    binding = w.department_registry(root)['publishing']['chat_binding']
    meta = cms._current_original_publisher_metadata(root, 'example-native-f4ba16119c32b000')
    need(rotation.validation_registry(root) is None and meta.get('execution_thread_id') == binding['task_id']
         and meta.get('production_permission_inherited') is False
         and Path(binding['cwd']).resolve() == Path(root).resolve()
         and requested.get('source_project_id') == binding['project_id'], 'actual same-role current rotation only')
    snapshot = restore_goal(root, w.read_json(w.snapshot_path(root, TASK)))
    active = [item for item in snapshot['goal_delivery'].get('execution_preflights', [])
              if all(item.get(k) == requested.get(k) for k in
                     ('task_id', 'action_id', 'action_class', 'scope', 'department', 'payload_sha256'))]
    need(len(active) == 1, 'one current effective original selfcheck required')
    events = w.read_jsonl(Path(root) / w.WORKFLOW_EVENTS, where={'task_id': TASK})
    matches = []
    for event in events:
        pin = event.get('details', {}).get('production_preflight_registered')
        if not pin:
            continue
        item = cms.doc(root, pin)
        if item == active[0] and all(item.get(k) == requested.get(k) for k in
               ('task_id', 'action_id', 'action_class', 'scope', 'department', 'payload_sha256')):
            need(metadata.metadata(root, snapshot, event), 'exact normal current PUB selfcheck event')
            matches.append((event, pin))
    need(len(matches) == 1, 'one newly registered exact selfcheck; old permits cannot transfer')
    event, pin = matches[0]
    native = registration_proof(root, binding, pin, event)
    w._VALIDATION_CONTEXT.get().recheck()
    return {'model': 'original_current_PUB_material_selfcheck_admission/v1',
            'rotation_source': meta['execution_binding_source'], 'preflight': pin,
            'event_id': event['event_id'], 'actual_normal_registration': native,
            'old_permit_transferred': False, 'policy_or_permit_issued': False}
