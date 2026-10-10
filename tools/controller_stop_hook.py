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


def _event_coordinator(event: dict) -> tuple[str, str, str] | None:
    if not isinstance(event, dict):
        raise ValueError('event must be an object')
    if event.get('hook_event_name') != 'Stop' or event.get('cwd') != str(ROOT):
        return None
    if CONTROLLER and PROJECT and event.get('session_id') == CONTROLLER:
        return 'operations', CONTROLLER, PROJECT
    from goal_delivery_runtime import enabled
    from workflow_control import department_registry
    if not enabled(ROOT):
        return None
    matches = [(role, item.get('chat_binding', {})) for role, item in department_registry(ROOT).items()
               if role != 'operations' and item.get('coordination_authority', {}).get('routine_decisions') is True
               and item.get('chat_binding', {}).get('task_id') == event.get('session_id')]
    if len(matches) == 1:
        role, binding = matches[0]
        if binding.get('project_id') and binding.get('cwd') == str(ROOT):
            return role, binding['task_id'], binding['project_id']
    return None


def _matching_event(event: dict) -> bool:
    return _event_coordinator(event) is not None


def decide(event: dict, state: dict, pending: dict, now: dt.datetime) -> dict:
    """Use only this controller's current internal dependencies, not traffic goals."""
    coordinator = _event_coordinator(event)
    if coordinator is None:
        return {}
    role, thread, project = coordinator
    # The app has already continued this Stop chain. Never block it again.
    if event.get('stop_hook_active') is True:
        return {}
    if event.get('stop_hook_active', False) is not False:
        raise ValueError('stop_hook_active must be a boolean')
    if not isinstance(state, dict) or not isinstance(pending, dict):
        raise ValueError('state and pending must be objects')
    if (state.get('project_id') != project
            or state.get('controller_thread_id') != thread
            or state.get('cwd') != str(ROOT)):
        return {'systemMessage': '总控接续状态身份不完整；未启动自动接续。请恢复本项目状态证明。'}
    if (state.get('coordination_model') == 'goal_delivery_assistant_v1'
            and role == 'operations' and state.get('HQ_may_end_coordination') is True):
        return {}
    reasons = []
    if state.get('validation_errors'):
        reasons.append('当前派工回执或结果证据需恢复；不沿旧缓存派工')
    if pending.get('pending_count', 0):
        reasons.append('存在尚未收取或决策的真实部门结果')
    if pending.get('followthrough_pending_count', 0):
        reasons.append('存在决策后尚未落实的到期待办')
    if pending.get('collaboration_pending_count', 0):
        reasons.append('存在已返回、仍须正式收取/验收或落实真实接续的协作结果')
    if pending.get('collaboration_not_proven_count', 0):
        reasons.append('存在 NOT_PROVEN 协作证据；先恢复准确原生 pin/身份/原文，不称完成或重复派工')
    watched = state.get('watched_tasks', [])
    ready = state.get('ready_internal_actions', [])
    if any(not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows)
           for rows in (watched, ready)):
        raise ValueError('watched and ready must be object lists')
    if watched:
        reasons.append('本轮已派任务仍需核实完成事件及准确结果')
    if ready:
        reasons.append('本轮还有待恢复证据或待落实的内部动作' if state.get('coordination_model') == 'goal_delivery_assistant_v1'
                       else '本轮还有已准备、依赖齐全的内部动作')
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
    if state.get('coordination_model') == 'goal_delivery_assistant_v1':
        return {'decision': 'block', 'reason': 'FLASH CAST当前负责助理（' + role + '）仍有本轮动作：'
                + '；'.join(reasons) + '。从当前 owned goal snapshot、真实原任务回执与该助理 '
                + 'logs/goal-delivery-waits/' + role + '.json 恢复，忽略旧 HQ cache/checkpoint。'
                + '结果返回后由唯一负责助理验收整项标准并登记真实后续；ACK/prepared/idle/空队列不算完成。'
                + '在途只沿冻结批次使用原生 wait_threads，单次不超过60秒，保存真实 cursor；'
                + '调用前登记 wait-call-start；中断用 wait-recover 区分未调用、调用无返回和返回未提交，保留原批与游标。'
                + '专业结果只交负责助理，准确已验收助理总结交 HQ 知悉；通知忙时持久暂缓，真实 idle 后沿现有 lease 准备并提交原生发送回执。'
                + '禁止重复派工、向 active 聊天普通消息或新增轮询。队列不能唤醒已结束聊天。'
                + '停止前列明已完成/未完成范围、负责人、下一动作、解除条件和复查时间。当前原任务：'
                + ', '.join(tasks[:8])}
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


def _load_context(event=None) -> tuple[dict, dict]:
    from controller_event_state import derive
    role, thread, project = _event_coordinator(event) if event is not None else ('operations', CONTROLLER, PROJECT)
    state, pending = derive(ROOT, coordinator_role=role)
    if any(state.get(k) != v for k, v in {
        'controller_thread_id': thread, 'project_id': project, 'cwd': str(ROOT)
    }.items()):
        raise ValueError('controller registry identity mismatch')
    return state, pending


def evaluate(event, load_context=None, now=None) -> dict:
    """Expected local failures must not trap the user or emit a traceback."""
    try:
        if not _matching_event(event) or event.get('stop_hook_active') is True:
            return {}
        state, pending = _load_context(event) if load_context is None else load_context()
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
