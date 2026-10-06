"""Read exact fixed-thread reply evidence when the app summary omits messages.

Read-only, no provider calls. Return hashes and identifiers, never chat text.
Live project/sidebar identity must still be checked with the Codex app.
"""
from __future__ import annotations

import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import workflow_control as workflow


def _completion_matches(reply: str, completed_reply: str) -> bool:
    if reply == completed_reply:
        return True
    # Codex removes its trailing memory-citation metadata from task_complete.
    # Accept only that structured suffix, never a differing user-facing body.
    marker = "<oai-mem-citation>"
    if marker not in reply:
        return False
    body, suffix = reply.rsplit(marker, 1)
    if not body.strip() or body != completed_reply:
        return False
    try:
        metadata = ET.fromstring(marker + suffix)
    except ET.ParseError:
        return False
    return (metadata.tag == "oai-mem-citation"
            and [child.tag for child in metadata] == ["citation_entries", "rollout_ids"]
            and all(len(child) == 0 for child in metadata)
            and not (metadata.text or "").strip()
            and all(not (child.tail or "").strip() for child in metadata))


def check_reply(root: Path, department: str, turn_id: str, session_path: Path) -> dict[str, Any]:
    binding = workflow.department_registry(root).get(department, {}).get("chat_binding", {})
    policy = workflow.load_policy(root).get("routing_policy", {})
    if (not binding or binding.get("project_id") != policy.get("source_project_id")
            or not workflow._same_resolved_path(str(binding.get("cwd", "")), str(root))):
        raise workflow.WorkflowError("部门项目或目录不匹配")
    path = session_path.resolve()
    try:
        path.relative_to((Path.home() / ".codex/sessions").resolve())
    except ValueError as exc:
        raise workflow.WorkflowError("只允许读取本机 Codex sessions 中的精确会话文件") from exc
    return _read_reply(path, str(binding["task_id"]), str(root), turn_id)


def _read_reply(path: Path, thread_id: str, cwd: str, turn_id: str) -> dict[str, Any]:
    metadata_ok = False
    active_turn = ""
    latest_completed_turn = ""
    reply = ""
    reply_ref = ""
    observed_at = ""
    completion: dict[str, Any] = {}
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)  # Invalid records must not be silently ignored.
            payload = row.get("payload", {})
            kind = row.get("type")
            if kind == "session_meta":
                if payload.get("id") != thread_id or not workflow._same_resolved_path(str(payload.get("cwd", "")), cwd):
                    raise workflow.WorkflowError("会话文件不是该固定部门或 cwd 不匹配")
                metadata_ok = True
            elif kind == "event_msg" and payload.get("type") == "task_started":
                active_turn = str(payload.get("turn_id", ""))
            elif kind == "turn_context":
                active_turn = str(payload.get("turn_id", ""))
                if not workflow._same_resolved_path(str(payload.get("cwd", "")), cwd):
                    raise workflow.WorkflowError("会话轮次 cwd 不匹配")
            elif kind == "event_msg" and payload.get("type") == "task_complete":
                latest_completed_turn = str(payload.get("turn_id", ""))
                if latest_completed_turn == turn_id:
                    completion = payload
            elif active_turn == turn_id:
                if (kind == "response_item" and payload.get("type") == "message"
                        and payload.get("role") == "assistant"
                        and payload.get("phase") != "commentary"):
                    reply = "".join(part.get("text", "") for part in payload.get("content", [])
                                    if part.get("type") in {"output_text", "text"})
                    reply_ref = str(payload.get("id") or turn_id)
                    observed_at = str(row.get("timestamp", ""))
    if not metadata_ok or latest_completed_turn != turn_id:
        raise workflow.WorkflowError("缺少会话身份或请求的不是最新已完成轮次；不能用旧回复恢复健康")
    verified = bool(reply.strip() and completion
                    and _completion_matches(reply, str(completion.get("last_agent_message", ""))))
    return {
        "status": "reply_verified" if verified else "reply_unverified",
        "thread_id": thread_id, "turn_id": turn_id,
        "reply_nonempty": bool(reply.strip()), "completion_matches": verified,
        "reply_ref": reply_ref if verified else "",
        "reply_sha256": hashlib.sha256(reply.encode("utf-8")).hexdigest() if verified else "",
        "reply_observed_at": observed_at if verified else "",
        "chat_body_stored": False,
        "source": "exact_local_session_and_task_complete",
        "live_identity_check_required": True,
    }
