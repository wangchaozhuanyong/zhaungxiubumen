"""Consume exact native scheduler readback for any registered executing department.

The caller must collect native readback; this validates its frozen metadata,
never authenticates a user, copies a chat body, dispatches or changes schedules.
"""
import datetime as dt
import re
import workflow_control as w


def validate(root, request, box):
    role = request.get('sender_department')
    entry = w.department_registry(root).get(role, {})
    bind = entry.get('chat_binding', {})
    pin = request.get('native_run')
    if (role == 'operations' or not bind.get('task_id') or not isinstance(pin, dict)
            or w.file_digest(root, pin.get('path', '')) != pin):
        raise w.WorkflowError('registered daily executor and exact native run pin required')
    run = w.read_json(w.safe_path(root, pin['path']))
    now = dt.datetime.now(dt.timezone.utc)
    stamp = w._parse_observed_at(run.get('observed_at'))
    reply = w._parse_observed_at(request.get('reply_observed_at'))
    expected = dict(task_id=request.get('task_id'), department=role,
        thread_id=bind['task_id'], project_id=bind['project_id'], cwd=bind['cwd'],
        automation_id=request.get('source_automation_id'), turn_id=request.get('source_turn_id'),
        reply_sha256=request.get('source_reply_sha256'))
    if (run.get('source') != 'native_automation_run_readback' or run.get('completed') is not True
            or run.get('trusted_native_readback') is not True
            or any(run.get(k) != v or not v for k,v in expected.items())
            or request.get('source_thread_id') != bind['task_id']
            or not re.fullmatch('[a-f0-9]{64}', str(expected['reply_sha256']))
            or stamp is None or reply is None or not 0 <= (now-stamp).total_seconds() <= 300
            or not reply <= stamp <= now
            or box.get('fixed_chat_task_id') != bind['task_id']
            or box.get('chat_reply',{}).get('nonempty') is not True
            or box.get('chat_reply',{}).get('in_current_fixed_department_chat') is not True
            or box.get('chat_reply',{}).get('sha256') != expected['reply_sha256']
            or not box.get('chat_reply',{}).get('ref')
            or box.get('chat_reply',{}).get('ref') != run.get('reply_ref')
            or box.get('candidate_version') != request.get('candidate_version')
            or run.get('outbox') != w.file_digest(root, request['outbox_path'])):
        raise w.WorkflowError('exact completed native run and fixed-chat result required')
    return pin
