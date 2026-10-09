"""Read-only QA work selection. Never dispatches, grants release, or wakes a chat."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import workflow_control as workflow

QUEUE = "data/qa-dispatch-priority.json"


def _pinned(root: Path, pin: dict) -> dict:
    path = root / pin["path"]
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("priority evidence outside project")
    if hashlib.sha256(path.read_bytes()).hexdigest() != pin["sha256"]:
        raise ValueError("priority evidence hash mismatch")
    return json.loads(path.read_text()) if path.suffix == ".json" else {}


def _qa_result_outbox(root: Path, receipts: list[dict], result: dict, pin: dict) -> dict:
    """Resolve only explicit replacements in an already validated native chain.

    The verdict remains the original QA receipt's verdict. An archive alone
    cannot authorize using the changed bytes at the original outbox path.
    """
    try:
        return _pinned(root, pin)
    except ValueError as exc:
        if str(exc) != "priority evidence hash mismatch":
            raise
    start = receipts.index(result)
    reachable = {result["receipt_id"]}
    for replacement in receipts[start + 1:]:
        if (replacement.get("receipt_type") != "evidence_replacement"
                or replacement.get("supersedes_receipt_id") not in reachable
                or replacement.get("department") != result.get("department")):
            continue
        for updated_pin in replacement.get("evidence", []):
            if updated_pin.get("path") != pin["path"]:
                continue
            reachable.add(replacement["receipt_id"])
            try:
                return _pinned(root, updated_pin)
            except ValueError as exc:
                if str(exc) != "priority evidence hash mismatch":
                    raise
    raise ValueError("priority QA result changed without matching explicit replacement")


def _received_result_matches(root: Path, receipts: list[dict], start: int,
                             result: dict, item: dict, qa_thread: str) -> bool:
    """Resolve report-only verdicts through their exact native outbox receipt.

    A filename, cached queue status, or another candidate's PASS is insufficient.
    This only marks the QA round reviewed; it grants no release permission.
    """
    if not result.get("scope") or not result.get("action_class"):
        return False
    try:
        verdict_index = receipts.index(result)
    except ValueError:
        return False
    if verdict_index <= start:
        return False
    for received in receipts[start + 1:verdict_index]:
        if (received.get("receipt_type") != "outbox_received"
                or received.get("department") != "qa"
                or received.get("chat_task_id") != qa_thread
                or any(received.get(key) != result.get(key)
                       for key in ("task_id", "action_id", "action_class", "scope"))):
            continue
        for pin in received.get("evidence", []):
            if not str(pin.get("path", "")).startswith("logs/department-outbox/"):
                continue
            candidate = _qa_result_outbox(root, receipts, received, pin)
            if (candidate.get("department") != "qa"
                    or candidate.get("task_id") != item["task_id"]
                    or candidate.get("candidate_version") != item["candidate_version"]
                    or any(candidate.get(key) != result.get(key)
                           for key in ("action_id", "action_class", "scope"))
                    or candidate.get("qa_verdict", candidate.get("verdict")) != result["verdict"]):
                continue
            chat = candidate.get("chat_reply", {})
            if not isinstance(chat, dict):
                continue
            # Accept the canonical fixed-chat key as well as historical aliases;
            # every supplied identifier must name the same registered QA chat.
            threads = [chat.get(key) for key in ("fixed_chat_task_id", "source_thread_id",
                                                "thread_id", "chat_task_id") if chat.get(key)]
            if (not threads or any(thread != qa_thread for thread in threads)
                    or chat.get("nonempty") is not True
                    or chat.get("in_current_fixed_department_chat") is not True):
                continue
            workflow.validate_outbox(root, [pin], "qa", item["task_id"])
            return True
    return False


def inspect(root: Path, queue: dict | None = None, *, full_audit: bool = False) -> dict:
    """Select only registered original tasks with pinned received evidence."""
    try:
        from human_control import guard
        guard(root)
        queue = queue if queue is not None else json.loads((root / QUEUE).read_text())
        registry = workflow.department_registry(root)
        reviewer = queue.get("qa_department", "qa")
        if reviewer not in {"qa", "qa-technical"}:
            raise ValueError("unknown fixed reviewer")
        qa = registry[reviewer]["chat_binding"]
        source = registry["operations"]["chat_binding"]
        if (queue["schema_version"] != "1.0"
                or queue["project_id"] != source["project_id"]
                or queue["project_id"] != qa["project_id"]
                or queue["controller_thread_id"] != source["task_id"]
                or queue["qa_thread_id"] != qa["task_id"]
                or Path(queue["cwd"]).resolve() != root.resolve()):
            raise ValueError("priority queue identity mismatch")
        waiting, dispatched, reviewed, seen, quarantined = [], [], [], set(), []
        for item in queue["items"]:
            try:
                if not isinstance(item, dict):
                    raise ValueError("priority row must be object")
                identity = (item["task_id"], item["candidate_version"], item["action_id"])
                if identity in seen:
                    raise ValueError("duplicate priority item")
                seen.add(identity)
                if reviewer == "qa-technical":
                    import qa_review_plan
                    snapshot = workflow.read_json(workflow.snapshot_path(root, item["task_id"]))
                    plan = qa_review_plan.load_plan(root, snapshot)
                    if (not plan or plan.get("reviewer_department") != reviewer or plan.get("risk_level") != "R0"
                            or plan.get("action_class") not in qa_review_plan.R0_CLASSES
                            or plan.get("action_id") != item["action_id"]
                            or plan.get("candidate_version") != item["candidate_version"]
                            or plan.get("candidate") not in _pinned(root, item["source_outbox"]).get("evidence", [])
                            or plan.get("producer_department") == reviewer):
                        raise ValueError("QA2 exact single-reviewer R0 admission required")
                outbox = _pinned(root, item["source_outbox"])
                decision = _pinned(root, item["controller_decision"])
                _pinned(root, item["packet"])
                if (outbox["task_id"] != item["task_id"]
                        or outbox["candidate_version"] != item["candidate_version"]
                        or decision["task_id"] != item["task_id"]
                        or decision["candidate_version"] != item["candidate_version"]
                        or not decision.get("controller_received")
                        or not decision.get("controller_decision")):
                    raise ValueError("priority original result/decision mismatch")
                receipts, invalid = workflow._validate_receipt_chain(root, item["task_id"])
                if invalid:
                    raise ValueError("priority native chain invalid")
                sends = [r for r in receipts if r.get("receipt_type") == "dispatch_sent"
                         and r.get("department") == reviewer and r.get("chat_task_id") == qa["task_id"]
                         and r.get("action_id") == item["action_id"]
                         and (not item.get("require_exact_packet_dispatch")
                              or any(pin.get("path") == item["packet"]["path"]
                                     and pin.get("sha256") == item["packet"]["sha256"]
                                     for pin in r.get("evidence", [])))]
                row = {k: item[k] for k in ("task_id", "candidate_version", "action_id", "packet")}
                if not sends:
                    waiting.append(row)
                    continue
                start = receipts.index(sends[-1])
                done = False
                for result in receipts[start + 1:]:
                    if (result.get("department") != reviewer
                            or result.get("receipt_type") != "qa_verdict"
                            or result.get("chat_task_id") != qa["task_id"]
                            or result.get("action_id") != item["action_id"]
                            or result.get("verdict") not in {"pass", "blocked"}):
                        continue
                    for pin in result.get("evidence", []):
                        if not str(pin.get("path", "")).startswith("logs/department-outbox/"):
                            continue
                        candidate = _qa_result_outbox(root, receipts, result, pin)
                        if (candidate.get("department") == reviewer
                                and candidate.get("task_id") == item["task_id"]
                                and candidate.get("candidate_version") == item["candidate_version"]):
                            done = True
                    if reviewer == "qa" and not done and _received_result_matches(root, receipts, start, result, item, qa["task_id"]):
                        done = True
                (reviewed if done else dispatched).append(row)
            except (OSError, ValueError, KeyError, TypeError, workflow.WorkflowError) as exc:
                quarantined.append({"task_id": item.get("task_id") if isinstance(item,dict) else None,
                                    "reason": str(exc), "row_quarantined": True})
        mode = ("BLOCKED_INVALID_PRIORITY_EVIDENCE" if quarantined and not (waiting or dispatched or reviewed) else
                "RESUME_DISPATCHED_QA" if dispatched else
                "DEFER_DAILY_AWAIT_CONTROLLER_DISPATCH" if waiting else "DAILY_CHECK_ALLOWED")
        limit = None if full_audit else 10
        return {"mode": mode, "reason": "all priority rows quarantined" if mode == "BLOCKED_INVALID_PRIORITY_EVIDENCE" else "",
                "waiting_dispatch": waiting[:limit], "dispatched_without_result": dispatched[:limit],
                "reviewed": reviewed[:limit], "waiting_dispatch_count": len(waiting),
                "dispatched_without_result_count": len(dispatched), "reviewed_count": len(reviewed),
                "total_control_rows": len(queue["items"]), "quarantined_rows": quarantined, "quarantined_count": len(quarantined), "detail_limit": limit,
                "full_audit": full_audit, "full_audit_option": "--full-audit",
                "details_truncated": not full_audit and any(len(rows) > 10 for rows in (waiting, dispatched, reviewed)),
                "business_complete": False, "production_release_eligible": False,
                "app_scheduler_lock": False, "external_actions": 0}
    except (OSError, ValueError, KeyError, TypeError, workflow.WorkflowError) as exc:
        return {"mode": "BLOCKED_INVALID_PRIORITY_EVIDENCE", "reason": str(exc),
                "business_complete": False, "production_release_eligible": False,
                "app_scheduler_lock": False, "external_actions": 0}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Bounded priority summary; immutable full history on demand")
    parser.add_argument("--full-audit", action="store_true")
    args = parser.parse_args()
    project = Path(__file__).resolve().parents[1]
    result = inspect(project, full_audit=args.full_audit)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(2 if result["mode"] == "BLOCKED_INVALID_PRIORITY_EVIDENCE" else 0)
