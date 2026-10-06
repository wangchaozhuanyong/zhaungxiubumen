"""Exact single-reviewer R0 admission. Metadata is not authentication or permission."""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path

R0_CLASSES = {"internal_control_candidate", "read_only_candidate"}
IDENTITY = ("task_id", "action_id", "action_class", "scope", "candidate_version", "candidate_sha256")


def _workflow():
    import workflow_control
    return workflow_control


def _binding(root, snapshot):
    """Recover the frozen binding from append-only events if snapshot was lost."""
    w = _workflow()
    binding = snapshot.get("qa_review_plan")
    if binding is None:
        events = [row for row in w.read_jsonl(root / w.WORKFLOW_EVENTS)
                  if row.get("task_id") == snapshot.get("task_id")
                  and row.get("details", {}).get("qa_review_plan_bound")]
        binding = events[-1]["details"]["qa_review_plan_bound"] if events else None
    return binding


def load_plan(root: Path, snapshot: dict) -> dict | None:
    w = _workflow()
    binding = _binding(root, snapshot)
    if binding is None:
        return None
    if not isinstance(binding, dict) or not isinstance(binding.get("pin"), dict):
        raise w.WorkflowError("invalid exact QA review-plan binding")
    pin = binding["pin"]
    if w.file_digest(root, pin.get("path", "")) != pin:
        raise w.WorkflowError("frozen QA review plan changed")
    plan = w.read_json(w.safe_path(root, pin["path"]))
    if not snapshot.get("departments"):
        events = [row for row in w.read_jsonl(root / w.WORKFLOW_EVENTS)
                  if row.get("task_id") == snapshot.get("task_id")]
        original = next((row.get("details", {}) for row in events if row.get("state") == "planned"), {})
        snapshot = {**snapshot, "departments": original.get("departments", []),
                    "owner_approval_required": original.get("owner_approval_required", False)}
        for row in events:
            details = row.get("details", {})
            if (details.get("plan_refresh") or details.get("binding_refresh")) and details.get("departments"):
                snapshot["departments"] = details["departments"]
                if "owner_approval_required" in details:
                    snapshot["owner_approval_required"] = details["owner_approval_required"]
    validate_plan(root, snapshot, plan)
    if binding.get("reviewer_department") != plan["reviewer_department"]:
        raise w.WorkflowError("reviewer binding differs from frozen plan")
    return plan


def reviewer_department(root: Path, snapshot: dict) -> str:
    plan = load_plan(root, snapshot)
    return plan["reviewer_department"] if plan else "qa"


def validate_plan(root: Path, snapshot: dict, plan: dict) -> None:
    w = _workflow()
    if (plan.get("schema_version") != 1 or plan.get("task_id") != snapshot.get("task_id")
            or plan.get("risk_level") != "R0" or plan.get("single_final_reviewer") is not True
            or plan.get("action_class") not in R0_CLASSES
            or any(plan.get(k) is not False for k in ("production_write_allowed", "external_permission_issued"))
            or snapshot.get("owner_approval_required")):
        raise w.WorkflowError("exact single-reviewer internal R0 plan required")
    if any(not isinstance(plan.get(k), str) or not plan[k].strip() for k in IDENTITY):
        raise w.WorkflowError("complete exact QA identity required")
    scope = plan["scope"]
    if (not scope.startswith("project:") or scope.endswith((":", "/"))
            or any(c in scope for c in "*?[]|,\n\r")):
        raise w.WorkflowError("one exact project scope required")
    reviewer, producer = plan.get("reviewer_department"), plan.get("producer_department")
    registry = w.department_registry(root)
    planned = {row.get("department"): row for row in snapshot.get("departments", [])}
    if (reviewer not in {"qa", "qa-technical"} or producer not in registry
            or producer in {"operations", "qa", "qa-technical"} or producer == reviewer
            or reviewer not in registry or reviewer not in planned or producer not in planned
            or set(planned) & {"qa", "qa-technical"} != {reviewer}):
        raise w.WorkflowError("one known independent planned reviewer and producer required")
    producer_bind, review_bind = [registry[d].get("chat_binding", {}) for d in (producer, reviewer)]
    ops_bind = registry.get("operations", {}).get("chat_binding", {})
    if (plan.get("reviewer_thread_id") != review_bind.get("task_id")
            or planned[reviewer].get("chat_task_id") != review_bind.get("task_id")
            or planned[producer].get("chat_task_id") != producer_bind.get("task_id")
            or producer_bind.get("task_id") == review_bind.get("task_id")
            or plan.get("controller_department") != "operations"
            or plan.get("controller_thread_id") != ops_bind.get("task_id")):
        raise w.WorkflowError("exact fixed reviewer/producer/controller required")
    if any(not b.get("project_id") or b.get("project_id") != ops_bind.get("project_id")
           or b.get("cwd") != str(root.resolve()) for b in (producer_bind, review_bind, ops_bind)):
        raise w.WorkflowError("same project and cwd required")
    pin = plan.get("candidate")
    if not isinstance(pin, dict) or w.file_digest(root, pin.get("path", "")) != pin:
        raise w.WorkflowError("exact immutable candidate file pin required")
    candidate = w.read_json(w.safe_path(root, pin["path"]))
    if (pin.get("sha256") != plan["candidate_sha256"]
            or candidate.get("task_id") != plan["task_id"]
            or candidate.get("candidate_version") != plan["candidate_version"]
            or candidate.get("department") != producer):
        raise w.WorkflowError("candidate task/version/producer/hash mismatch")


def bind_plan(root: Path, *, task_id: str, plan_path: str, coordinator_role: str = "operations") -> dict:
    w = _workflow()
    if coordinator_role != "operations":
        raise w.WorkflowError("only operations records final reviewer plan")
    task_id = w.validate_task_id(task_id)
    pin = w.file_digest(root, plan_path)
    with w.workflow_lock(root):
        snapshot = w.read_json(w.snapshot_path(root, task_id))
        if not snapshot:
            raise w.WorkflowError("original workflow required")
        plan = w.read_json(w.safe_path(root, plan_path))
        validate_plan(root, snapshot, plan)
        old = _binding(root, snapshot)
        binding = {"pin": pin, "reviewer_department": plan["reviewer_department"]}
        if old is not None:
            if old != binding:
                raise w.WorkflowError("reviewer plan is frozen; cannot replace/reopen")
            return {"result": "duplicate_ignored", **binding}
        receipts, invalid = w._validate_receipt_chain(root, task_id)
        if invalid or w.validate_workflow_events(root, task_id):
            raise w.WorkflowError("valid original chains required for reviewer admission")
        if any(r.get("department") in {"qa", "qa-technical"} for r in receipts):
            raise w.WorkflowError("cannot change reviewer after QA dispatch or history")
        now = dt.datetime.now(dt.timezone.utc)
        if any(not w._chat_binding_healthy(w.department_registry(root)[d].get("chat_binding", {}),
                                          verification_ttl_hours=26, now=now)
               for d in ("operations", plan["producer_department"], plan["reviewer_department"])):
            raise w.WorkflowError("fresh fixed-role health required")
        snapshot["qa_review_plan"] = binding
        w.append_workflow_event(root, task_id, snapshot["current_state"], {"qa_review_plan_bound": binding})
        snapshot["updated_at"] = w.utc_timestamp()
        snapshot["event_count"] = sum(row.get("task_id") == task_id for row in w.read_jsonl(root / w.WORKFLOW_EVENTS))
        w.atomic_write_json(w.snapshot_path(root, task_id), snapshot)
    return {"result": "recorded", **binding, "production_write_allowed": False}


def validate_verdict(root: Path, snapshot: dict, receipts: list, receipt: dict) -> None:
    w = _workflow()
    plan = load_plan(root, snapshot)
    if plan is None:
        if receipt.get("department") != "qa":
            raise w.WorkflowError("legacy and production reviewer remains fixed qa")
        return
    expected = {key: plan[key] for key in IDENTITY}
    reviewer = plan["reviewer_department"]
    if (receipt.get("department") != reviewer or receipt.get("chat_task_id") != plan["reviewer_thread_id"]
            or any(receipt.get(k) != plan[k] for k in ("task_id", "action_id", "action_class", "scope"))):
        raise w.WorkflowError("verdict differs from exact single-reviewer R0 identity")
    indices = [(i, r) for i, r in enumerate(receipts)
               if r.get("department") == reviewer and r.get("receipt_type") in {"dispatch_sent", "dispatch_failed"}]
    if not indices or indices[-1][1].get("receipt_type") != "dispatch_sent":
        raise w.WorkflowError("latest actual reviewer dispatch required")
    index, dispatch = indices[-1]
    binding = _binding(root, snapshot)
    if (binding["pin"] not in dispatch.get("evidence", []) or plan["candidate"] not in dispatch.get("evidence", [])
            or dispatch.get("chat_task_id") != plan["reviewer_thread_id"]
            or dispatch.get("scope") != plan["scope"]):
        raise w.WorkflowError("dispatch must freeze exact plan/candidate/scope")
    acknowledgements = [(i, r) for i, r in enumerate(receipts[index + 1:], index + 1)
                        if r.get("department") == reviewer and r.get("receipt_type") == "chat_ack"
                        and r.get("chat_task_id") == plan["reviewer_thread_id"] and r.get("ack_nonempty") is True]
    if not acknowledgements:
        raise w.WorkflowError("current nonempty fixed-reviewer ACK required")
    ack_index, ack = acknowledgements[-1]
    boxes = [r for r in receipts[ack_index + 1:] if r.get("department") == reviewer
             and r.get("receipt_type") == "outbox_received"]
    if not boxes:
        raise w.WorkflowError("current exact reviewer outbox required")
    now = dt.datetime.now(dt.timezone.utc)
    stamps = [w._parse_observed_at(r.get("created_at")) for r in (dispatch, ack, boxes[-1], receipt)]
    if any(x is None for x in stamps) or not stamps[0] <= stamps[1] <= stamps[2] <= stamps[3] <= now:
        raise w.WorkflowError("actual reviewer timestamps must be ordered and not future")
    pin = next((p for p in boxes[-1].get("evidence", []) if p.get("path", "").endswith(".json")), None)
    if pin is None or pin not in receipt.get("evidence", []) or w.file_digest(root, pin["path"]) != pin:
        raise w.WorkflowError("verdict must reference current exact reviewer outbox bytes")
    box = w.read_json(w.safe_path(root, pin["path"]))
    w.validate_outbox(root, [pin], reviewer, plan["task_id"])
    reply = box.get("chat_reply", {})
    if (box.get("task_id") != plan["task_id"] or box.get("department") != reviewer
            or box.get("fixed_chat_task_id") != plan["reviewer_thread_id"]
            or box.get("candidate_version") != plan["candidate_version"]
            or box.get("review_identity") != expected or box.get("qa_verdict") != receipt.get("verdict")
            or box.get("risk_level") != "R0"
            or any(box.get(k) is not False for k in ("production_write_allowed", "external_permission_issued", "production_release_eligible"))
            or reply.get("nonempty") is not True or reply.get("in_current_fixed_department_chat") is not True
            or not reply.get("ref") or not w.SHA256_PATTERN.fullmatch(str(reply.get("sha256", "")))):
        raise w.WorkflowError("exact real reply metadata and R0 reviewer outbox identity required")
    producer_boxes = [r for r in receipts if r.get("department") == plan["producer_department"]
                      and r.get("receipt_type") == "outbox_received"]
    if not producer_boxes:
        raise w.WorkflowError("original producer outbox required")
    producer_pin = next((p for p in producer_boxes[-1].get("evidence", []) if p.get("path", "").endswith(".json")), None)
    producer = w.read_json(w.safe_path(root, producer_pin["path"])) if producer_pin else {}
    if producer.get("candidate_version") != plan["candidate_version"] or plan["candidate"] not in producer.get("evidence", []):
        raise w.WorkflowError("original producer must bind the reviewed candidate/version")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--plan", required=True)
    args = parser.parse_args()
    try:
        result = bind_plan(args.project_root.resolve(), task_id=args.task_id, plan_path=args.plan)
    except (ValueError, OSError, _workflow().WorkflowError) as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc), "production_write_allowed": False})); return 2
    print(json.dumps(result)); return 0


if __name__ == "__main__":
    raise SystemExit(main())
