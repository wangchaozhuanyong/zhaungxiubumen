"""Project the latest exact direct handoff to the assigned window, read-only."""
import hashlib
from pathlib import Path
from xml.sax.saxutils import escape

import workflow_control as w


def native_effect(page, *, source_thread, body, since):
    expected = (f'<codex_delegation>\n  <source_thread_id>{source_thread}</source_thread_id>\n'
                f'  <input>{escape(body)}</input>\n</codex_delegation>')
    matches = [(turn, index, item) for turn in page.get('data', [])
               for index, item in enumerate(turn.get('items', []))
               if item.get('type') == 'functionCallOutput' and item.get('namespace') == 'codex_app'
               and item.get('name') == 'send_message_to_thread'
               and item.get('output') in (expected, {'text': expected, 'truncated': False})]
    if len(matches) != 1:
        return {'state': 'direct_effect_unknown', 'reason': 'missing or duplicate exact native input'}
    turn, index, item = matches[0]
    started = turn.get('startedAt')
    if not turn.get('id') or not item.get('id') or type(started) not in {int, float} or started < since:
        return {'state': 'direct_effect_unknown', 'reason': 'invalid native effect identity or chronology'}
    result = {'state': 'direct_input_observed', 'turn_id': turn['id'], 'input_message_id': item['id'],
              'turn_status': turn.get('status')}
    replies = [m for m in turn['items'][index + 1:] if m.get('type') == 'agentMessage'
               and m.get('id') and isinstance(m.get('text'), str) and m['text'].strip()]
    if turn.get('error') or turn.get('status') in {'failed', 'interrupted'}:
        return {**result, 'state': 'direct_turn_failed'}
    finals = [m for m in replies if m.get('phase') == 'final_answer']
    completed = turn.get('completedAt')
    if turn.get('status') == 'completed' and type(completed) in {int, float} and completed >= started and len(finals) == 1:
        return {**result, 'state': 'direct_final_observed', 'final_message_id': finals[0]['id'],
                'final_sha256': hashlib.sha256(finals[0]['text'].encode()).hexdigest()}
    if replies and turn.get('status') == 'inProgress':
        return {**result, 'state': 'direct_reply_in_progress', 'reply_message_id': replies[-1]['id']}
    return result


def observe(root, assigned_window, history):
    """No sends, business receipts, serial releases or permissions are issued."""
    if not assigned_window or history is None:
        return None
    from receipt_obligation_consumer import doc, require

    root = Path(root)
    try:
        candidates = w.read_jsonl(root / w.WORKFLOW_EVENTS,
                                  where={('details', 'dispatch_intent', 'target_thread_id'): assigned_window})
        if not candidates:
            return None
        event = candidates[-1]
        intent = event['details']['dispatch_intent']
        if not intent.get('request') or not intent.get('preparation'):
            return None
        context = {'task_id': event['task_id'], 'action_id': intent['action_id'], 'target_thread_id': assigned_window,
                   'intent_event_id': event['event_id'], 'business_goal_closed': False, 'permission_issued': False}
        request = doc(root, intent['request'])
        if request.get('delivery_mode') != 'mcp_direct_send':
            return None
        prepared = doc(root, intent['preparation'])
        policy = prepared['policy_decision']
        policies = w.read_jsonl(root / w.POLICY_DECISIONS, where={'decision_id': intent['policy_decision_id']})
        require(event.get('event_hash') == w.sha256_value({k: v for k, v in event.items() if k != 'event_hash'})
                and all(request.get(k) == context[k] for k in ('task_id', 'action_id', 'target_thread_id'))
                and prepared.get('status') == 'ready_to_send' and prepared.get('payload') == request.get('payload')
                and policies == [policy] and policy.get('status') == 'allow' and policy.get('external_permission_issued') is False
                and policy.get('department') == request.get('sender_department')
                and all(policy.get(k) == request.get(k) for k in ('task_id', 'action_id', 'scope', 'action_class',
                    'target_department', 'target_thread_id', 'source_project_id', 'target_project_id', 'payload_sha256')),
                'exact direct intent, prepared request and original policy required')
        registry = w.department_registry(root)
        source = registry[request['sender_department']]['chat_binding']
        target = registry[request['target_department']]['chat_binding']
        require(source['project_id'] == request['source_project_id'] and target['project_id'] == request['target_project_id']
                and target['task_id'] == assigned_window and target['title'] == request['target_thread_title']
                and target['cwd'] == request['target_cwd'], 'original direct sender and receiver binding required')
        thread = history.call('thread/read', {'threadId': assigned_window, 'includeTurns': False})['thread']
        require(thread.get('id') == assigned_window and thread.get('name', thread.get('title')) == target['title']
                and thread.get('cwd') == target['cwd']
                and thread.get('projectId') in (None, target['project_id']), 'actual exact native receiver required')
        payload = request['payload']
        body = w.safe_path(root, payload['path']).read_bytes()
        require(payload['size'] == len(body) and payload['sha256'] == request['payload_sha256']
                == hashlib.sha256(body).hexdigest(), 'unchanged original direct payload required')
        when = w._parse_observed_at(event.get('created_at'))
        require(when is not None, 'actual direct intent time required')
        page = history.call('thread/turns/list', {'threadId': assigned_window, 'limit': 6,
                            'sortDirection': 'desc', 'itemsView': 'full'})
        return {**context, **native_effect(page, source_thread=source['task_id'],
                body=body.decode(), since=when.timestamp())}
    except (w.WorkflowError, ValueError, OSError, KeyError, TypeError, AttributeError, RuntimeError) as error:
        return {'state': 'direct_readback_blocked', 'target_thread_id': assigned_window,
                'reason': str(error), 'business_goal_closed': False, 'permission_issued': False}
