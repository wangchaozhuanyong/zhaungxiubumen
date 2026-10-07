"""Project-local Stop hook: continue the fixed controller, never message or publish.

Installing this file does not trust or activate a Codex hook. The exact hook
definition must be reviewed in Codex. An Interrupt or model-capacity failure
cannot be restarted by a Stop hook.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
try:
    _registry = json.loads((ROOT / 'data/department-registry.json').read_text())
    _binding = next(row['chat_binding'] for row in _registry['departments'] if row['id'] == 'operations')
except (OSError, ValueError, KeyError, TypeError, StopIteration):
    _binding = {}
CONTROLLER = _binding.get('task_id', '')
PROJECT = _binding.get('project_id', '')
STATE = 'data/controller-event-continuation.json'


def _matching_event(event: dict) -> bool:
    if not isinstance(event, dict):
        raise ValueError('event must be an object')
    return (bool(CONTROLLER and PROJECT) and event.get('hook_event_name') == 'Stop'
            and event.get('session_id') == CONTROLLER
            and event.get('cwd') == str(ROOT))


def decide(event: dict, state: dict, pending: dict, now: dt.datetime) -> dict:
    """Use only this controller's current internal dependencies, not traffic goals."""
    if not _matching_event(event):
        return {}
    # The app has already continued this Stop chain. Never block it again.
    if event.get('stop_hook_active') is True:
        return {}
    if event.get('stop_hook_active', False) is not False:
        raise ValueError('stop_hook_active must be a boolean')
    if not isinstance(state, dict) or not isinstance(pending, dict):
        raise ValueError('state and pending must be objects')
    if (state.get('project_id') != PROJECT
            or state.get('controller_thread_id') != CONTROLLER
            or state.get('cwd') != str(ROOT)):
        return {'systemMessage': '总控接续状态身份不完整；未启动自动接续。请恢复本项目状态证明。'}
    reasons = []
    if state.get('validation_errors'):
        reasons.append('当前派工回执或结果证据需恢复；不沿旧缓存派工')
    if pending.get('pending_count', 0):
        reasons.append('存在尚未收取或决策的真实部门结果')
    if pending.get('followthrough_pending_count', 0):
        reasons.append('存在决策后尚未落实的到期待办')
    watched = state.get('watched_tasks', [])
    ready = state.get('ready_internal_actions', [])
    if any(not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows)
           for rows in (watched, ready)):
        raise ValueError('watched and ready must be object lists')
    if watched:
        reasons.append('本轮已派任务仍需核实完成事件及准确结果')
    if ready:
        reasons.append('本轮还有已准备、依赖齐全的内部动作')
    if not reasons:
        # External facts, future daily reviews and 50 IP do not keep a turn alive.
        return {}
    try:
        stamp = dt.datetime.fromisoformat(state['updated_at'].replace('Z', '+00:00'))
        age = (now - stamp).total_seconds()
        if not 0 <= age <= 300:
            reasons.append('现场/接续状态过期，先重新核实，不能沿缓存派工')
    except (KeyError, TypeError, ValueError):
        reasons.append('接续观测时间缺失，先恢复准确检查点')
    tasks = sorted({str(x.get('task_id', '')) for x in watched + ready if x.get('task_id')})
    return {
        'decision': 'block',
        'reason': 'FLASH CAST固定总控本轮不能普通收工：' + '；'.join(reasons)
        + '。从data/controller-event-continuation.json和最新controller_checkpoint恢复。'
        + '先收原固定聊天/最终outbox，核QA并登记收取、决策、真实后续。'
        + '本轮在途用原生wait_threads事件等待，单次不超过60秒并保存cursor；'
        + '完成后沿原任务继续，禁止给active聊天普通消息、重复派工或恢复五分钟轮询。'
        + '当前原任务：' + ', '.join(tasks[:8])
        + '。仅此控制范围闭环或具名真实外部等待齐全后清除对应watch/ready记录；'
        + '50自然IP和未来日检不要求本轮达成。停止前更新固定未完成清单。',
    }


def _load_context() -> tuple[dict, dict]:
    from controller_event_state import derive
    state, pending = derive(ROOT)
    if any(state.get(k) != v for k, v in {
        'controller_thread_id': CONTROLLER, 'project_id': PROJECT, 'cwd': str(ROOT)
    }.items()):
        raise ValueError('controller registry identity mismatch')
    return state, pending


def evaluate(event, load_context=_load_context, now=None) -> dict:
    """Expected local failures must not trap the user or emit a traceback."""
    try:
        if not _matching_event(event) or event.get('stop_hook_active') is True:
            return {}
        state, pending = load_context()
        return decide(event, state, pending, now or dt.datetime.now(dt.timezone.utc))
    except (ValueError, OSError, KeyError, TypeError, RuntimeError, ImportError) as error:
        return {'systemMessage': '总控停止检查未执行，需恢复项目控制证据：' + type(error).__name__}


def main() -> int:
    try:
        event = json.load(sys.stdin)
        # Do not read other projects' files, transcripts, messages or credentials.
        output = evaluate(event)
    except (ValueError, OSError, KeyError, TypeError) as error:
        # A broken local hook must not trap the user or hide the cause.
        output = {'systemMessage': '总控停止检查未执行，需恢复项目控制证据：' + type(error).__name__}
    print(json.dumps(output, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
