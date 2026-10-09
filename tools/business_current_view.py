"""One frozen original-business view. Never infer supersession from names or age."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import workflow_control as w


def inspect(root, index_pin):
    if not isinstance(index_pin, dict) or w.file_digest(root, index_pin.get("path", "")) != index_pin:
        raise w.WorkflowError("frozen explicit current-business index required")
    index = w.read_json(w.safe_path(root, index_pin["path"]))
    rows = index.get("businesses")
    if index.get("schema_version") != 1 or not isinstance(rows, list):
        raise w.WorkflowError("current-business index schema invalid")
    seen, selected, views = set(), set(), []
    for item in rows:
        if not isinstance(item, dict):
            raise w.WorkflowError("current business object required")
        business = item.get("original_business_id")
        task = w.validate_task_id(item.get("task_id"))
        if not isinstance(business, str) or not business.strip() or business in seen:
            raise w.WorkflowError("one exact current row per original business required")
        seen.add(business)
        pin = item.get("outbox")
        if not isinstance(pin, dict) or w.file_digest(root, pin.get("path", "")) != pin:
            raise w.WorkflowError("current business frozen outbox changed")
        box = w.read_json(w.safe_path(root, pin["path"]))
        sender = box.get("department")
        w.validate_outbox(root, [pin], sender, task)
        identity = (sender, box.get("candidate_version"), pin["sha256"])
        key = (task, *identity)
        if key in selected:
            raise w.WorkflowError("one result cannot masquerade as two businesses")
        selected.add(key)
        matches = [r for r in w.result_handoff_status(root, task)["results"]
                   if w._result_identity(r) == identity]
        if len(matches) != 1:
            raise w.WorkflowError("one actual exact result required for current view")
        for field in ("phase", "owner", "next_action", "blocker", "unblock_condition"):
            if not isinstance(item.get(field), str) or not item[field].strip():
                raise w.WorkflowError("current phase/owner/next action/blocker/unblock required")
        evidence = item.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            raise w.WorkflowError("current business evidence required")
        if any(not isinstance(pin, dict) or w.file_digest(root, pin.get("path", "")) != pin for pin in evidence):
            raise w.WorkflowError("current business evidence changed")
        import human_control
        state = human_control.read_state(root)
        views.append({**item, "actual_result": matches[0], "business_goal_closed": False,
                      "human_paused": state["paused"], "human_cancelled": task in state.get("cancelled_tasks", [])})
    return {"read_only": True, "current_business_count": len(views), "businesses": views,
            "history_modified": False, "historical_queue_reopened": False,
            "current_index": index_pin, "external_permission_issued": False}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--index", required=True)
    a = p.parse_args()
    print(json.dumps(inspect(a.root, w.file_digest(a.root, a.index)), ensure_ascii=False))


if __name__ == "__main__": main()
