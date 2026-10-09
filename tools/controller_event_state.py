"""Derive a bounded controller wait plan from current receipts, never send tools.

The checkpoint is a reference, not proof that a department is still running.
This reader replaces the stale, manually maintained event-continuation cache.
It does not wake an ended chat, grant permissions or mutate business history.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path

import workflow_control as workflow


def derive(root: Path, now: dt.datetime | None = None) -> tuple[dict, dict]:
    root = root.resolve()
    from human_control import read_state
    human = read_state(root)
    if human["paused"]:
        registry = workflow.department_registry(root)
        binding = registry.get("operations", {}).get("chat_binding", {})
        return ({"project_id": binding.get("project_id"), "controller_thread_id": binding.get("task_id"),
                 "cwd": str(root), "human_paused": True, "human_control_revision": human["revision"],
                 "watched_tasks": [], "ready_internal_actions": [], "validation_errors": [],
                 "updated_at": (now or dt.datetime.now(dt.timezone.utc)).isoformat()},
                {"pending_count": 0, "followthrough_pending_count": 0,
                 "paused_view_only": True, "original_queue_preserved": True})
    now = now or dt.datetime.now(dt.timezone.utc)
    registry = workflow.department_registry(root)
    binding = registry.get("operations", {}).get("chat_binding", {})
    policy = workflow.load_policy(root).get("routing_policy", {})
    if (not binding.get("task_id") or not binding.get("project_id")
            or binding.get("project_id") != policy.get("source_project_id")
            or Path(binding.get("cwd", "")).resolve() != root):
        raise ValueError("current controller identity is incomplete")
    execution = workflow.read_json(root / "data/content/organic-execution-policy.json")
    checkpoint_path = execution["keyword_content_coverage_acceptance"]["controller_checkpoint"]
    checkpoint = json.loads(workflow.safe_path(root, checkpoint_path).read_text(encoding="utf-8"))
    if (not isinstance(checkpoint, dict) or not isinstance(checkpoint.get("active_tasks"), list)
           ):
        raise ValueError("current checkpoint requires an explicit active task list")
    from routine_authority import partition_queue
    queue = partition_queue(root, workflow.result_handoff_pending(root))
    watched, resolved, errors = [], [], []
    seen = set()
    for item in checkpoint.get("active_tasks", []):
        try:
            if not isinstance(item, dict):
                raise ValueError("active task row must be object")
            task, department = item.get("task_id"), item.get("department")
            candidate, receipt_id = item.get("candidate_version"), item.get("dispatch_receipt_id")
            key = (task, department, candidate, receipt_id)
            if key in seen:
                continue
            seen.add(key)
            # Owner-designated external projects have their own route. They cannot
            # become an ordinary fixed-department watch or an inferred permission.
            if department not in registry or department == "operations":
                errors.append({"task_id": task, "reason": "not_a_fixed_execution_department"})
                continue
            target = registry[department].get("chat_binding", {})
            if (not all(key) or (registry[department].get("relationship") != "associated_code_department"
                        and (target.get("project_id") != binding["project_id"]
                             or Path(target.get("cwd", "")).resolve() != root))):
                errors.append({"task_id": task, "reason": "incomplete_or_cross_project_watch"})
                continue
            receipts, invalid = workflow._validate_receipt_chain(root, task)
            sent = next((row for row in receipts if row.get("receipt_id") == receipt_id), {})
            if (invalid or sent.get("receipt_type") != "dispatch_sent"
                    or sent.get("department") != department
                    or sent.get("chat_task_id") != target.get("task_id")):
                errors.append({"task_id": task, "reason": "dispatch_receipt_or_pins_invalid"})
                continue
            pos = receipts.index(sent)
            ack = next((row for row in receipts[pos + 1:] if row.get("receipt_type") == "chat_ack"
                        and row.get("department") == department
                        and row.get("chat_task_id") == target["task_id"]
                        and row.get("ack_nonempty") is True
                        and (sent.get("action_class") not in {"cms_content_candidate", "site_code_candidate", "site_code_rework_candidate"}
                             or (row.get("action_id") == sent.get("action_id")
                                 and row.get("scope") == sent.get("scope")))), None)
            if not ack:
                errors.append({"task_id": task, "reason": "nonempty_ACK_missing"})
                continue
            # Exact candidate, sender and current outbox bytes must match; workflow
            # closed, native idle, old candidates and ACKs cannot close this watch.
            rows = workflow._result_handoff_rows(root, task)
            grouped = {}
            for row in rows:
                if (row.get("sender_department") == department
                        and row.get("candidate_version") == candidate
                        and row.get("created_at", "") >= sent["created_at"]):
                    grouped.setdefault(row["result_sha256"], []).append(row)
            settled = None
            for result_hash, events in grouped.items():
                intake = next((r for r in events if r["event"] == "controller_received"), None)
                decision = next((r for r in events if r["event"] == "controller_decision"), None)
                follow = next((r for r in reversed(events) if r["event"] == "controller_followthrough"), None)
                if not intake or not decision:
                    continue
                # Persisted records store the pinned outbox under `outbox`; the
                # input request uses outbox_path. Never mistake request shape for
                # the actual ledger, or crash before reporting a recovery error.
                pin = intake.get("outbox", {})
                if pin is None:
                    pin = {}
                if not isinstance(pin, dict):
                    errors.append({"task_id": task, "reason": "settled_result_outbox_not_object"})
                    continue
                path = pin.get("path") or intake.get("outbox_path")
                try:
                    if not path or (pin.get("sha256") and pin["sha256"] != result_hash):
                        raise ValueError("result_outbox_pin_missing_or_mismatched")
                    outbox = workflow.safe_path(root, path)
                    actual_hash = workflow.file_digest(root, str(outbox.relative_to(root)))["sha256"]
                except (workflow.WorkflowError, OSError, ValueError, TypeError):
                    errors.append({"task_id": task, "reason": "settled_result_outbox_unavailable"})
                    continue
                if actual_hash != result_hash:
                    errors.append({"task_id": task, "reason": "settled_result_hash_changed"})
                    continue
                if decision.get("decision") == "close_scope" or follow:
                    settled = {"task_id": task, "department": department,
                               "candidate_version": candidate, "result_sha256": result_hash,
                               "controller_received": intake["record_id"],
                               "controller_decision": decision["record_id"],
                               "controller_followthrough": follow["record_id"] if follow else None,
                               "business_goal_closed": False}
            if settled:
                resolved.append(settled)
            else:
                watched.append({"task_id": task, "department": department,
                                "candidate_version": candidate, "dispatch_receipt_id": receipt_id,
                                "ack_receipt_id": ack["receipt_id"], "thread_id": target["task_id"],
                                "turn_id": item.get("turn_id", ""),
                                "event_cursor": item.get("event_cursor", ""),
                                "mode": "WAIT_OR_COLLECT_EXACT_RESULT",
                                "requires_fresh_native_identity_before_tool": True})
        except (workflow.WorkflowError, ValueError, TypeError, KeyError, OSError) as exc:
            errors.append({"task_id": item.get("task_id") if isinstance(item, dict) else None,
                           "reason": str(exc), "row_quarantined": True})
    targets = []
    for thread in sorted({row["thread_id"] for row in watched}):
        tasks = [row for row in watched if row["thread_id"] == thread]
        cursors = {row["event_cursor"] for row in tasks}
        target = {"thread_id": thread, "host_id": "local"}
        if len(cursors) == 1 and "" not in cursors:
            target["after_cursor"] = next(iter(cursors))
        # Mixed or absent cursors require a fresh snapshot, never a guessed ID.
        targets.append(target)
    for item in watched:
        item["holds_headquarters_open"] = False
        item["continuation_state"] = "durable_result_pending"
    return {"schema_version": "2.0", "project_id": binding["project_id"],
            "controller_thread_id": binding["task_id"], "cwd": str(root),
            "updated_at": now.isoformat(), "controller_checkpoint": checkpoint_path,
            "source": "current_checkpoint_and_validated_native_receipts",
            "ordinary_inflight_is_stop_blocker": False, "headquarters_single_task_wait": False,
            "durable_queue_preserved": True,
            "watched_tasks": watched, "resolved_watches": resolved,
            "ready_internal_actions": __import__("routine_authority").classify_ready_tasks(root, checkpoint.get("prepared_waiting_qa", [])),
            "validation_errors": errors, "event_wait_targets": targets,
            "max_wait_ms_per_call": 60000, "polling_or_scheduler_created": False,
            "result_queue_auto_wakes_ended_controller": False,
            "messages_sent": 0, "permissions_issued": 0, "business_goal_closed": False}, queue


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", help="Optional derived cache, inside this project only")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    state, queue = derive(root)
    if args.output:
        path = workflow.safe_path(root, args.output)
        workflow.atomic_write_json(path, state)
    print(json.dumps({"state": state, "queue_counts": {k: queue.get(k, 0) for k in (
        "pending_count", "followthrough_pending_count", "total_actionable_count")}}, ensure_ascii=False))
    return 3 if state["validation_errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
