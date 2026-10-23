"""Exact HQ-delegated brand/PUB read-only coordination, never production authority."""
from pathlib import Path
import argparse
import copy
import hashlib
import json
import re
import workflow_control as w

SOURCE = {}

BACKUP = 'backups/fc-20261021-owner-delegated-nonpayment-decisions-repair-v1/HQ-readonly-coordination-registration-v1'
ACTION = 'C1-original-brand-stage-PUB-code-only-version-tracking-20261022-v1'


def document(root, pin):
    if not isinstance(pin, dict) or w.file_digest(root, pin.get('path', '')) != pin:
        raise w.WorkflowError('exact original coordination source bytes required')
    return w.read_json(w.safe_path(root, pin['path']))


def original_source(root):
    import goal_delivery_runtime as g
    delegation = g._owner_decision_delegation(root)
    if delegation is None: raise w.WorkflowError('actual same-project owner decision delegation required')
    source = SOURCE
    request, prepared, body = (document(root, source[x]) if x != 'decision' else
        w.safe_path(root, source[x]['path']).read_text(encoding='utf-8') for x in ['request', 'prepared', 'decision'])
    if w.file_digest(root, source['decision']['path']) != source['decision']:
        raise w.WorkflowError('original HQ decision changed')
    registry = w.department_registry(root); hq = registry['operations']['chat_binding']; a1 = registry['operations-assistant']['chat_binding']
    policy = prepared['policy_decision']; auth = prepared['authorization_precheck']
    expected = {'task_id': source['parent_task_id'], 'department': 'operations', 'action_class': 'thread_message',
        'action_id': 'HQ-brand-actual-PUB-readonly-tracking-nonpayment-decision-A1-20261022-v1',
        'scope': 'project:flashcast:brand-main-name-preservation-dual-query:20261021:v1',
        'source_project_id': hq['project_id'], 'target_project_id': a1['project_id'],
        'target_department': 'operations-assistant', 'target_thread_id': a1['task_id'],
        'payload_sha256': source['decision']['sha256'], 'status': 'allow', 'routing_status': 'routing_allowed'}
    if (any(policy.get(k) != v for k, v in expected.items())
            or prepared.get('status') != 'ready_to_queue' or prepared.get('payload') != source['decision']
            or request.get('payload') != source['decision'] or request.get('sender_department') != 'operations'
            or auth.get('status') != 'within_original_authorization'
            or auth.get('decision_delegation', {}).get('source') != delegation['source']
            or [p for p in w.read_jsonl(Path(root) / w.POLICY_DECISIONS)
                if p.get('decision_id') == 'pol-4a928c7c940123a297a4'] != [policy]
            or source['parent_task_id'] not in body or '不新增CMS Save、账号、费用或生产许可' not in body):
        raise w.WorkflowError('actual exact HQ nonpayment read-only decision required')
    native = g._collaboration_native(root, source['HQ_native'])
    if any(native['thread'].get(k) != hq[v] for k, v in {'id': 'task_id', 'title': 'title', 'cwd': 'cwd'}.items()):
        raise w.WorkflowError('actual fixed HQ native issuer required')
    for command in source['native_commands']:
        calls = [c for t in native.get('turns', []) for c in t.get('items', []) if c.get('id') == command['id']]
        if (len(calls) != 1 or calls[0].get('type') != 'commandExecution'
                or calls[0].get('status') != 'completed' or calls[0].get('exitCode') != 0
                or calls[0].get('output', {}).get('truncated') is not False
                or hashlib.sha256(calls[0]['command'].encode()).hexdigest() != command['sha256']):
            raise w.WorkflowError('successful exact original HQ preparation and queue invocation required')
    queued = document(root, source['queue_result'])
    if (queued.get('exit_code') != 0 or queued.get('policy_decision_id') != policy['decision_id']
            or queued.get('payload_sha256') != source['decision']['sha256']
            or queued.get('thread_id') != a1['task_id'] or queued.get('transport') != 'official_codex_queue'
            or queued.get('stdout', '').strip() != 'Queued message ' + source['queue_message_id'] + ' for thread ' + a1['task_id'] + '.'):
        raise w.WorkflowError('actual exact official queue outcome required; queue is not recipient receipt')
    document(root, source['contract'])
    return source


def registered(root, snapshot):
    if snapshot.get('task_id') != SOURCE['task_id']: return None
    rows = [e['details']['readonly_coordination_decision'] for e in w.read_jsonl(Path(root) / w.WORKFLOW_EVENTS)
            if e.get('task_id') == SOURCE['task_id'] and e.get('details', {}).get('readonly_coordination_decision')]
    if not rows: return None
    if len(rows) != 1 or w.validate_workflow_events(root, SOURCE['task_id']):
        raise w.WorkflowError('one intact exact HQ coordination decision registration required')
    original_source(root)
    value = document(root, rows[0]); expected = {'schema': 'exact-HQ-readonly-coordination/v1',
        'task_id': SOURCE['task_id'], 'decision_source': SOURCE['decision'], 'HQ_native': SOURCE['HQ_native']}
    goal = snapshot['goal_delivery']
    if (value != expected or snapshot.get('goal_contract') != SOURCE['contract']
            or goal.get('parent_task_id') != SOURCE['parent_task_id']
            or goal.get('primary_owner') != 'content-organic-website'
            or goal.get('producer_departments') != ['content-organic-website']
            or goal.get('responsible_assistant') != 'operations-assistant'
            or goal.get('authorized_scope') != [SOURCE['scope']]):
        raise w.WorkflowError('original brand stage identity/scope/ownership required')
    return rows[0]


def applies(snapshot, role):
    return snapshot.get('task_id') == SOURCE['task_id'] and role == 'publishing'


def binding(root, snapshot, role):
    if role != 'publishing' or registered(root, snapshot) is None: return None
    current = w.department_registry(root)['publishing']['chat_binding']
    if current.get('project_id') != w.department_registry(root)['operations']['chat_binding']['project_id']:
        raise w.WorkflowError('same-project registered PUB required')
    return {**current, 'thread_id': current['task_id']}


def register(root, task_id, input_path):
    import goal_delivery_runtime as g
    from department_rotation import prohibit_validation_write
    prohibit_validation_write()
    source = original_source(root)
    pin = w.file_digest(root, input_path); value = document(root, pin)
    expected = {'schema': 'exact-HQ-readonly-coordination/v1', 'task_id': source['task_id'],
        'decision_source': source['decision'], 'HQ_native': source['HQ_native']}
    if task_id != source['task_id'] or value != expected:
        raise w.WorkflowError('exact original HQ decision registration input required')
    with w.workflow_lock(root):
        path = w.snapshot_path(root, task_id); before = w.file_digest(root, str(path.relative_to(root)))
        raw = path.read_bytes(); snapshot = g.restore_goal(root, w.read_json(path)); goal = snapshot['goal_delivery']
        if snapshot.get('current_state') in w.TERMINAL_STATES or registered(root, snapshot):
            raise w.WorkflowError('decision already registered/consumed or stage closed; do not replay')
        if snapshot.get('goal_contract') != source['contract'] or goal.get('parent_task_id') != source['parent_task_id']:
            raise w.WorkflowError('same original stage and parent required')
        backup_path = Path(root) / BACKUP / (before['sha256'] + '-snapshot.json')
        if backup_path.exists():
            if backup_path.read_bytes() != raw: raise w.WorkflowError('original backup mismatch')
        else: w.atomic_write_text(backup_path, raw.decode('utf-8'))
        declaration = {'scope': source['scope'], 'sender_department': 'content-organic-website', 'target_department': 'publishing'}
        declarations = list(goal.get('collaboration_scopes', []))
        if declaration in declarations: raise w.WorkflowError('preexisting PUB scope needs exact reconciliation')
        declarations.append(declaration)
        snapshot['goal_delivery'] = {**goal, 'collaboration_scopes': declarations}
        w.append_workflow_event(root, task_id, snapshot['current_state'],
            {'goal_delivery': snapshot['goal_delivery'], 'readonly_coordination_decision': pin,
             'external_permission_issued': False, 'recipient_received_claimed': False})
        w.atomic_write_json(path, snapshot)
        after = w.file_digest(root, str(path.relative_to(root)))
        journal = {'schema': 'exact-HQ-coordination-registration-journal/v1', 'state': 'registered',
            'task_id': task_id, 'source': pin, 'before': before, 'after': after,
            'backup': w.file_digest(root, str(backup_path.relative_to(root))),
            'goal_contract_unchanged': source['contract'], 'new_production_permission': False,
            'new_dispatch_or_ACK': False, 'assignee_or_claim_changed': False}
        w.atomic_write_json(Path(root) / BACKUP / 'journal.json', journal)
    return journal


def render(root, tracking):
    import goal_delivery_runtime as g
    if set(tracking) != {'web_native', 'turn_id', 'message_id', 'commit_sha', 'running_fact_excerpt'}:
        raise w.WorkflowError('only exact WEB factual source selectors allowed')
    if not re.fullmatch('[0-9a-f]{40}', str(tracking['commit_sha'])):
        raise w.WorkflowError('full actual WEB commit SHA required; prefixes cannot be final version')
    page = g._collaboration_native(root, tracking['web_native'])
    web = w.read_json(Path(root) / 'data/department-registry.json')['collaboration_bindings']['designated-development']
    if any(page.get('thread', {}).get(k) != web[v] for k, v in {'id': 'thread_id', 'title': 'title', 'cwd': 'cwd'}.items()):
        raise w.WorkflowError('actual original fixed WEB source required')
    turns = [t for t in page.get('turns', []) if t.get('id') == tracking['turn_id']]
    messages = [m for t in turns for m in t.get('items', []) if m.get('id') == tracking['message_id']]
    if (len(turns) != 1 or turns[0].get('status') not in {'inProgress', 'completed'}
            or turns[0].get('error') or len(messages) != 1 or messages[0].get('type') != 'agentMessage'):
        raise w.WorkflowError('one actual complete WEB factual reply required')
    text = messages[0].get('text', ''); excerpt = tracking['running_fact_excerpt']
    if (not re.search(r'(?<![0-9a-f])' + tracking['commit_sha'] + r'(?![0-9a-f])', text)
            or not isinstance(excerpt, str) or not 1 <= len(excerpt) <= 500 or excerpt not in text):
        raise w.WorkflowError('full SHA and actual running facts must match original WEB reply')
    return (f"task_id={SOURCE['task_id']}\nparent_task_id={SOURCE['parent_task_id']}\nscope={SOURCE['scope']}\n"
        'assignment_record_required=false\n【原品牌批次PUB只读跟踪；协作记录，不转移当前指派】\n'
        f"原WEB实际完整SHA：{tracking['commit_sha']}\n"
        f"WEB原生运行事实引用（来源引用，不是动作许可）：{json.dumps(excerpt, ensure_ascii=False)}\n"
        f"原件：{tracking['web_native']['path']} SHA256={tracking['web_native']['sha256']}\n"
        '仅跟踪原代码版本、执行进展、代码/CMS依赖和结果归回原C1。原WEB继续独立合法工作，A1仍唯一完整业务验收。\n'
        '本条不授CMS Save、提交/merge/push/deploy、Ads/账号、预算/付款或任何生产许可；不新增CMS字段。\n'
        '当前PUB指派与暂停工作保持。实际收取、跟踪和返回沿原协作记录分别记实；没有真实结果不声称上线。\n')


def validate_action(root, snapshot, action, *, phase='read'):
    source_pin = registered(root, snapshot)
    if source_pin is None or action.get('readonly_coordination_source') != source_pin:
        raise w.WorkflowError('registered actual HQ read-only decision source required')
    registry = w.department_registry(root); sender = registry['content-organic-website']['chat_binding']; target = registry['publishing']['chat_binding']
    expected = {'task_id': SOURCE['task_id'], 'scope': SOURCE['scope'], 'action_id': ACTION,
        'action_class': 'thread_message', 'sender_department': 'content-organic-website',
        'target_department': 'publishing', 'source_project_id': sender['project_id'],
        'target_project_id': target['project_id'], 'target_thread_id': target['task_id'],
        'target_thread_title': target['title'], 'target_cwd': target['cwd'],
        'target_sidebar_section_id': target['sidebar_section_id'], 'required_for_completion': False,
        'assignment_record_required': False}
    if any(action.get(k) != v for k, v in expected.items()) or sender['project_id'] != target['project_id']:
        raise w.WorkflowError('only the exact same-project C1-to-PUB read-only tracking action is allowed')
    body = render(root, action.get('readonly_tracking', {})); payload = action.get('payload', {})
    if (w.file_digest(root, payload.get('path', '')) != payload
            or payload.get('sha256') != action.get('payload_sha256')
            or w.safe_path(root, payload['path']).read_bytes() != body.encode('utf-8')):
        raise w.WorkflowError('canonical read-only payload and real WEB full-SHA/facts required')
    if phase == 'bind' and any(a.get('readonly_coordination_source') == source_pin
                               for a in snapshot['goal_delivery'].get('approved_actions', [])):
        raise w.WorkflowError('HQ decision is already bound to its exact action; duplicate/new-ID replay refused')
    if phase == 'policy' and any(p.get('task_id') == SOURCE['task_id'] and p.get('action_id') == ACTION
            and p.get('status') == 'allow' for p in w.read_jsonl(Path(root) / w.POLICY_DECISIONS)):
        raise w.WorkflowError('read-only action already prepared/consumed; recover actual effect, no replay')
    return True


def build_action(root, input_path, output_dir):
    """Freeze C1's refreshed factual body; no policy, assignment or delivery write."""
    import goal_delivery_runtime as g
    snapshot = g.restore_goal(root, w.read_json(w.snapshot_path(root, SOURCE['task_id'])))
    source_pin = registered(root, snapshot)
    if source_pin is None: raise w.WorkflowError('adopted source and actual HQ decision registration required first')
    value = w.read_json(w.safe_path(root, input_path))
    if set(value) != {'readonly_tracking', 'live_identity'}: raise w.WorkflowError('exact factual tracking and fresh identity only')
    live = document(root, value['live_identity'])
    output = w.safe_path(root, output_dir)
    if output.exists() and any(output.iterdir()): raise w.WorkflowError('immutable new C1 output directory required')
    output.mkdir(parents=True, exist_ok=True)
    payload = output / 'C1-refreshed-PUB-readonly-message.txt'
    w.atomic_write_text(payload, render(root, value['readonly_tracking']))
    registry = w.department_registry(root); target = registry['publishing']['chat_binding']
    action = {'task_id': SOURCE['task_id'], 'scope': SOURCE['scope'], 'action_id': ACTION,
        'action_class': 'thread_message', 'sender_department': 'content-organic-website',
        'target_department': 'publishing', 'source_project_id': registry['content-organic-website']['chat_binding']['project_id'],
        'target_project_id': target['project_id'], 'target_thread_id': target['task_id'],
        'target_thread_title': target['title'], 'target_cwd': target['cwd'],
        'target_sidebar_section_id': target['sidebar_section_id'], 'required_for_completion': False,
        'assignment_record_required': False, 'payload': w.file_digest(root, str(payload.relative_to(root))),
        'live_identity': value['live_identity'], 'readonly_tracking': value['readonly_tracking'],
        'readonly_coordination_source': source_pin}
    action['payload_sha256'] = action['payload']['sha256']
    validate_action(root, snapshot, action, phase='bind')
    w.atomic_write_json(output / 'approved-action-input.json', action)
    request = {k: v for k, v in action.items() if k not in {'required_for_completion', 'readonly_tracking', 'readonly_coordination_source'}}
    request['actual_target_state'] = live.get('actual_native_target_turns', {}).get(target['task_id'])
    if not request['actual_target_state']: raise w.WorkflowError('fresh actual PUB target native source required')
    document(root, request['actual_target_state'])
    request.update(authorization_changes=[], internal_repairs=[])
    w.atomic_write_json(output / 'prepare-message-request.json', request)
    return {'action_input': str((output / 'approved-action-input.json').relative_to(root)),
        'prepare_request': str((output / 'prepare-message-request.json').relative_to(root)),
        'actual_message_sent': False}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--project-root', default=str(Path(__file__).resolve().parents[1]))
    sub = parser.add_subparsers(dest='command', required=True)
    register_parser = sub.add_parser('register'); register_parser.add_argument('--input', required=True)
    build = sub.add_parser('build-action'); build.add_argument('--input', required=True); build.add_argument('--output', required=True)
    args = parser.parse_args(); root = Path(args.project_root).resolve()
    result = (register(root, SOURCE['task_id'], args.input) if args.command == 'register' else
              build_action(root, args.input, args.output))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
