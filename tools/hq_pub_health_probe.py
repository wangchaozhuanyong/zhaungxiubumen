"""One owner-confirmed, read-only recovery for the original EN2 publisher."""
import datetime as dt
from pathlib import Path

import workflow_control as w
from hq_en2_readonly_source import TASK, IDENTITY, digest

ACTION = 'HQ-PUB-EN2-original-fixed-identity-health-probe-20261105-v1'
PURPOSE = 'hq_original_pub_readonly_health_probe'
HQ = '<LOCAL_TASK_ID>'
PUB = '<LOCAL_TASK_ID>'
FAILED = 'example-native-e273c1e3df2f1eea'
OWNER_TURN = 'example-native-28a0b3325e2518b6'
OWNER_MESSAGE = 'example-native-c16eabb494d1be25'
OWNER_TEXT = '请允许我只为当前固定后台发布部增加一次只读身份探测。 允许'
SCOPE = 'cms:services:kitchen:english-two-fields:publication:v1'
BODY = (f'task_id={TASK}\nscope={SCOPE}\naction_id={ACTION}\n'
        'sender_department=operations\ntarget_department=publishing\nassignment_record_required=false\n\n'
        '仅做当前后台发布部固定窗口的只读身份核验。请非空回复当前项目、工作目录、固定角色及是否可接续。'
        '本轮只回复，不执行 EN2 或其他业务，不读取生产后台，不改文件，不做预演、签发、保存、发布或派送。')


def route(root, snapshot, request):
    if request.get('action_id') != ACTION:
        return None
    import department_autonomy as a
    from goal_delivery_runtime import _collaboration_native

    a.require(set(request) == set(IDENTITY) | {'owner_native', 'actual_target_state', 'live_observed_at'},
              'exact PUB health-only fields required')
    goal = a.participant(root, snapshot, 'operations')
    registry = w.department_registry(root)
    sender = registry['operations']['chat_binding']
    target = registry['publishing']['chat_binding']
    expected = {'task_id': TASK, 'scope': SCOPE, 'action_id': ACTION, 'action_class': 'thread_message',
                'sender_department': 'operations', 'target_department': 'publishing',
                'source_project_id': sender['project_id'], 'target_project_id': target['project_id'],
                'target_thread_id': PUB, 'target_thread_title': target['title'], 'target_cwd': target['cwd'],
                'target_sidebar_section_id': target['sidebar_section_id'], 'delivery_mode': 'mcp_direct_send',
                'assignment_record_required': False, 'authorization_changes': []}
    a.require(snapshot['task_id'] == TASK and goal.get('primary_owner') == 'publishing'
              and SCOPE in goal['authorized_scope'] and sender['task_id'] == HQ and target['task_id'] == PUB
              and sender['project_id'] == target['project_id'] == a.PROJECT
              and all(Path(b['cwd']).resolve() == Path(root).resolve() and b.get('host_id') == 'local'
                      for b in (sender, target))
              and registry['publishing'].get('new_dispatch_enabled') is True
              and w._chat_binding_healthy(sender, verification_ttl_hours=26)
              and all(request[k] == v for k, v in expected.items())
              and request['payload_sha256'] == request['payload']['sha256']
              and digest(root, request['payload']) == BODY.encode(),
              'exact current PUB health-only body and original fixed binding required')
    observed = w._parse_observed_at(request['live_observed_at'])
    a.require(observed is not None and 0 <= (dt.datetime.now(dt.timezone.utc) - observed).total_seconds() <= 300,
              'fresh original PUB observation required')
    owner = _collaboration_native(root, request['owner_native'])
    page = _collaboration_native(root, request['actual_target_state'])
    for document, fixed in ((owner, sender), (page, target)):
        thread = document.get('thread', {})
        a.require(thread.get('kind') == 'codex' and all(thread.get(k) == fixed[v] for k, v in
                  {'id': 'task_id', 'title': 'title', 'cwd': 'cwd', 'hostId': 'host_id'}.items()),
                  'actual original native HQ/PUB identity required')
    messages = [m for t in owner.get('turns', []) if t.get('id') == OWNER_TURN
                for m in t.get('items', []) if m.get('id') == OWNER_MESSAGE]
    a.require(len(messages) == 1 and messages[0].get('type') == 'userMessage'
              and len(messages[0].get('content', [])) == 1
              and messages[0]['content'][0].get('type') == 'text'
              and messages[0]['content'][0].get('text', '').strip() == OWNER_TEXT,
              'exact first-party owner approval for one PUB health probe required')
    turns = page.get('turns') or [{}]
    head = turns[0]
    a.require(page.get('page', {}).get('order') == 'newest_first'
              and page['thread'].get('status', {}).get('type') in {'idle', 'notLoaded'}
              and head.get('id') == FAILED and head.get('status') == 'failed'
              and 'usage limit' in (head.get('error') or {}).get('message', ''),
              'original PUB usage failure must still be the exact current terminal turn')
    return {**a.authority(root), 'purpose': PURPOSE, 'source': request['owner_native'], 'report': request['payload'],
            'scope': SCOPE, 'sender_department': 'operations', 'target_department': 'publishing',
            'external_permission_issued': False}
