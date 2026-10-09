"""Persistent project-local human pause. Audit metadata is not authentication.

No messages, publication, timers or transcript reads. The trusted caller must
observe the human message; a supplied hash alone cannot authenticate a person.
"""
from __future__ import annotations

from contextlib import contextmanager
import datetime as dt
import fcntl
import json
import os
from pathlib import Path
import re
import threading
import uuid

STATE = "data/human-control-state.json"
_threads = threading.local()


def _w():
    import workflow_control
    return workflow_control


@contextmanager
def control_lock(root):
    root = Path(root).resolve()
    held = getattr(_threads, "held", set())
    key = str(root)
    if key in held:
        yield
        return
    path = _w().safe_path(root, "data/.human-control.lock")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        _threads.held = held | {key}
        try:
            yield
        finally:
            _threads.held = held
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def read_state(root):
    w = _w()
    path = w.safe_path(root, STATE)
    policy_path = Path(root) / "data/action-policy.json"
    policy = w.read_json(policy_path)
    if policy_path.exists() and not policy:
        raise w.WorkflowError("human control policy unreadable; refuse continuation")
    cfg = policy.get("department_system_upgrade", {})
    if not isinstance(cfg, dict):
        raise w.WorkflowError("human control policy malformed; refuse continuation")
    required = cfg.get("require_human_control_state") is True
    if not path.exists():
        # Compatibility is limited to installations not yet migrated. New
        # routine grants always require explicit persistent state regardless.
        return {"paused": required, "revision": 0, "configured": False,
                "reason": "human_state_missing" if required else "legacy_not_migrated"}
    state = w.read_json(path)
    if (state.get("schema_version") != 1 or type(state.get("paused")) is not bool
            or type(state.get("revision")) is not int or state["revision"] < 1
            or state.get("project_root") != str(Path(root).resolve())):
        raise w.WorkflowError("persistent human control state invalid; refuse continuation")
    cancelled = state.get("cancelled_tasks", [])
    if (not isinstance(cancelled, list) or any(not isinstance(t, str) for t in cancelled)
            or len(cancelled) != len(set(cancelled))):
        raise w.WorkflowError("persistent administrative cancellation state invalid")
    for task in cancelled: w.validate_task_id(task)
    return {**state, "configured": True}


def guard(root, task_id=None):
    state = read_state(root)
    if state["paused"]:
        raise _w().WorkflowError("human_pause_active: explicit human resume required")
    if task_id and task_id in state.get("cancelled_tasks", []):
        raise _w().WorkflowError("human_task_cancelled: administrative cancellation preserves history")
    return state


@contextmanager
def action_gate(root, task_id=None):
    # Same ordering for pause and consumers: human control -> coordination ->
    # native receipt lock. A pause cannot race an admitted local append.
    with control_lock(root):
        yield guard(root, task_id)


def administrative_control(root, request, now=None):
    """Exact pause/resume/status, independent of old workflow closure."""
    w = _w(); root = Path(root).resolve()
    if not isinstance(request, dict):
        raise w.WorkflowError("administrative control object required")
    action = request.get("action")
    if action == "status":
        return read_state(root)
    if action not in {"pause", "resume", "cancel"} or request.get("actor") != "operations":
        raise w.WorkflowError("only exact human pause/resume/cancel through operations allowed")
    proof = request.get("human_message", {})
    if not isinstance(proof, dict):
        raise w.WorkflowError("human message object required")
    binding = w.department_registry(root).get("operations", {}).get("chat_binding", {})
    stamp = w._parse_observed_at(proof.get("observed_at"))
    now = now or dt.datetime.now(dt.timezone.utc)
    if (not isinstance(proof, dict) or proof.get("source") != "human_user_message"
            or proof.get("thread_id") != binding.get("task_id")
            or not binding.get("task_id") or not str(proof.get("message_id", "")).strip()
            or not re.fullmatch(r"[a-f0-9]{64}", str(proof.get("reply_sha256", "")))
            or proof.get("explicit_command") != action or stamp is None
            or not 0 <= (now - stamp).total_seconds() <= 300):
        raise w.WorkflowError("fresh explicit human command in fixed controller required")
    cancelled = w.validate_task_id(request.get("task_id")) if action == "cancel" else None
    with control_lock(root):
        old = read_state(root)
        if type(request.get("expected_revision")) is not int or request["expected_revision"] != old["revision"]:
            raise w.WorkflowError("administrative state revision changed")
        value = {"schema_version": 1, "project_root": str(root),
                 "revision": old["revision"] + 1, "paused": old["paused"] if action == "cancel" else action == "pause",
                 "cancelled_tasks": sorted(set(old.get("cancelled_tasks", [])) | ({cancelled} if cancelled else set())),
                 "human_message": proof, "updated_at": now.isoformat(),
                 "reason": str(request.get("reason") or action),
                 "actor_metadata_is_authentication": False}
        path = w.safe_path(root, STATE)
        temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
        try:
            with temporary.open("x", encoding="utf-8") as handle:
                json.dump(value, handle, ensure_ascii=False, indent=2)
                handle.flush(); os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            if temporary.exists(): temporary.unlink()
        return value


def main():
    import argparse
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--input", type=Path, required=True)
    a = p.parse_args()
    # Inputs must belong to this project too.
    request = _w().read_json(_w().safe_path(a.root, a.input))
    print(json.dumps(administrative_control(a.root, request), ensure_ascii=False))


if __name__ == "__main__": main()
