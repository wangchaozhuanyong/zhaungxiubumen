"""Read-only inspection of a dispatched R0 workpack; no messages or permits."""
from __future__ import annotations
import argparse
import datetime as dt
import json
from pathlib import Path
import workflow_control as w

KINDS = {"public_source_check", "local_candidate", "local_validation", "handoff_metadata_repair"}

def make_step_binding(root: Path, packet: dict, step: dict, workpack_sha256: str) -> dict:
    """Bind a result to the exact dispatched packet and immutable step inputs."""
    inputs = step.get("inputs", [])
    if not isinstance(inputs, list):
        raise w.WorkflowError("step inputs must be a frozen file-pin array")
    pins, paths = [], set()
    for pin in inputs:
        if (not isinstance(pin, dict) or set(pin) != {"path", "sha256", "size"}
                or not isinstance(pin["path"], str) or not pin["path"]
                or not isinstance(pin["size"], int) or isinstance(pin["size"], bool)):
            raise w.WorkflowError("exact input path/hash/size required")
        actual = w.file_digest(root, pin["path"])
        if actual != pin or actual["path"] in paths:
            raise w.WorkflowError("step input bytes changed or duplicate input pin")
        paths.add(actual["path"]); pins.append(actual)
    identity = {
        "task_id": packet["task_id"], "department": packet["department"],
        "project_id": packet["project_id"], "fixed_chat_task_id": packet["fixed_chat_task_id"],
        "step_id": step["step_id"], "candidate_version": step["candidate_version"],
        "scope": step["scope"], "kind": step["kind"], "inputs": pins,
        "output_dir": w.rel_path(root, w.safe_path(root, step["output_dir"])),
        "depends_on": step.get("depends_on", []), "subskills": step.get("subskills", []),
        "requires_controller_gate": step["requires_controller_gate"],
    }
    return {"schema_version": 1, "workpack_sha256": workpack_sha256,
            "step_sha256": w.sha256_value(identity), "step_identity": identity}

def inspect(root: Path, packet_path: str, live: dict, now: dt.datetime | None = None) -> dict:
    now = now or dt.datetime.now(dt.timezone.utc)
    packet = w.read_json(w.safe_path(root, packet_path))
    task = w.validate_task_id(packet.get("task_id"))
    department = packet.get("department")
    registry = w.department_registry(root)
    if department not in registry or department == "operations":
        raise w.WorkflowError("fixed executing department required")
    bind = registry[department]["chat_binding"]
    if packet.get("fixed_chat_task_id") != bind["task_id"] or packet.get("project_id") != bind["project_id"]:
        raise w.WorkflowError("packet fixed identity mismatch")
    stamp = w._parse_observed_at(live.get("observed_at"))
    if stamp is None or not 0 <= (now - stamp).total_seconds() <= 300:
        raise w.WorkflowError("fresh live identity required")
    threads = [t for t in live.get("threads", []) if t.get("id") == bind["task_id"]]
    groups = [s for s in live.get("sections", []) if "codex:thread:local:" + bind["task_id"] in s.get("itemKeys", [])]
    if (len(threads) != 1 or len(groups) != 1 or groups[0].get("name") != "装修公司部门"
            or groups[0].get("id") != bind["sidebar_section_id"]
            or any(threads[0].get(a) != bind.get(b) for a,b in (
                ("projectId","project_id"), ("title","title"), ("cwd","cwd")))):
        raise w.WorkflowError("live fixed identity or section mismatch")
    health = w._parse_observed_at(bind.get("last_health_check_at"))
    if health is None or health > now or not w._chat_binding_healthy(bind, verification_ttl_hours=26, now=now):
        raise w.WorkflowError("current reply health required")
    plan = packet.get("continuation_plan", {})
    if (plan.get("version") != 1 or plan.get("mode") != "same_task_local_r0_only"
            or plan.get("external_actions_allowed") is not False):
        raise w.WorkflowError("explicit local R0 workpack required")
    digest = w.file_digest(root, packet_path)
    receipts, invalid = w._validate_receipt_chain(root, task)
    sent = [(i,r) for i,r in enumerate(receipts) if r.get("receipt_type") == "dispatch_sent"
            and r.get("department") == department and r.get("chat_task_id") == bind["task_id"]]
    if not sent or invalid:
        raise w.WorkflowError("valid original dispatch chain required")
    index, dispatch = sent[-1]
    at = w._parse_observed_at(dispatch.get("created_at"))
    if at is None or at > now:
        raise w.WorkflowError("latest actual dispatch timestamp required and cannot be in the future")
    expires = w._parse_observed_at(plan.get("expires_at"))
    if (digest not in dispatch.get("evidence", []) or at is None or expires is None
            or not at < expires <= at + dt.timedelta(hours=26)):
        raise w.WorkflowError("workpack must be bound to latest dispatch with bounded expiry")
    if expires <= now:
        raise w.WorkflowError("workpack expired; controller renewal required")
    acknowledgements = [r for r in receipts[index+1:]
                        if r.get("receipt_type") == "chat_ack" and r.get("department") == department
                        and r.get("chat_task_id") == bind["task_id"] and r.get("ack_nonempty") is True]
    if not acknowledgements:
        raise w.WorkflowError("actual nonempty fixed-chat ACK required")
    ack_at = w._parse_observed_at(acknowledgements[-1].get("created_at"))
    if ack_at is None or not at <= ack_at <= now:
        raise w.WorkflowError("latest nonempty ACK timestamp must be dispatch_at <= ack_at <= now")
    steps = plan.get("steps")
    if not isinstance(steps,list) or not steps:
        raise w.WorkflowError("bounded explicit steps required")
    ids, versions, directories, by_id, bindings = set(), set(), [], {}, {}
    for step in steps:
        if not isinstance(step,dict):
            raise w.WorkflowError("step must be object")
        sid, cv = step.get("step_id"), step.get("candidate_version")
        if (not isinstance(sid,str) or not sid or sid in ids or not isinstance(cv,str)
                or not cv or cv in versions or step.get("kind") not in KINDS
                or not step.get("scope") or step.get("requires_controller_gate") is not False):
            raise w.WorkflowError("unique scoped R0 step required; gated actions cannot auto-continue")
        deps = step.get("depends_on", [])
        if not isinstance(deps,list) or any(dep not in ids for dep in deps):
            raise w.WorkflowError("dependencies must refer to earlier steps")
        directory = w.safe_path(root, step.get("output_dir",""))
        if (not w.rel_path(root,directory).startswith("drafts/") or task not in directory.parts
                or any(directory == d or directory in d.parents or d in directory.parents for d in directories)):
            raise w.WorkflowError("distinct project-local task candidate directories required")
        subs = step.get("subskills", [])
        if not isinstance(subs,list) or any(sub not in registry[department].get("approved_subskills",[]) for sub in subs):
            raise w.WorkflowError("unapproved subskill")
        ids.add(sid); versions.add(cv); directories.append(directory); by_id[sid] = step
        bindings[sid] = make_step_binding(root, packet, step, digest["sha256"])
    rows = w._result_handoff_rows(root,task)
    state = {}
    for sid,step in by_id.items():
        queued = [r for r in rows if r.get("event") == "notification_queued"
                  and r.get("sender_department") == department and r.get("candidate_version") == step["candidate_version"]]
        if not queued:
            state[sid] = "not_reported"; continue
        row = queued[-1]
        proof = row.get("outbox", {})
        box = w.read_json(w.safe_path(root,proof.get("path","")))
        if (w.file_digest(root,proof.get("path","")) != proof or row.get("result_sha256") != proof.get("sha256")
                or box.get("task_id") != task or box.get("department") != department
                or box.get("candidate_version") != step["candidate_version"] or box.get("fixed_chat_task_id") != bind["task_id"]
                or box.get("chat_reply",{}).get("nonempty") is not True
                or box.get("chat_reply",{}).get("in_current_fixed_department_chat") is not True):
            raise w.WorkflowError("queued result identity or frozen bytes mismatch")
        w.validate_outbox(root,[proof],department,task)
        if box.get("step_binding") != bindings[sid]:
            raise w.WorkflowError("queued result does not prove the exact dispatched packet and immutable step identity")
        state[sid] = "done" if box.get("status") == "completed" else "blocked_or_partial"
    ready, waits = [], []
    for sid,step in by_id.items():
        if state[sid] != "not_reported": continue
        missing = [dep for dep in step.get("depends_on",[]) if state[dep] != "done"]
        if missing: waits.append({"step_id":sid,"waiting_on":missing})
        else: ready.append(step)
    recovering = bool(ready and w.safe_path(root,ready[0]["output_dir"]).exists())
    return {"mode":"RECOVER_EXISTING_OUTPUT" if recovering else "CONTINUE_SCOPED_R0" if ready else "RETURN_FOR_CONTROLLER_DECISION",
            "task_id":task,"department":department,"packet":digest,
            "next_step":ready[0] if ready else None,"step_states":state,"dependency_waits":waits,
            "step_bindings":bindings,
            "source_queued_results_require_controller_decision":True,"native_wakeup_available":False,
            "external_permission_issued":False,"sends_message":False,"business_goal_closed":False}

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root",default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--packet",required=True)
    parser.add_argument("--live-proof",required=True)
    args = parser.parse_args(); root = Path(args.project_root).resolve()
    try:
        result = inspect(root,args.packet,w.read_json(w.safe_path(root,args.live_proof)))
    except (w.WorkflowError,ValueError,TypeError,KeyError,OSError) as exc:
        print(json.dumps({"mode":"BLOCKED","reason":str(exc),"external_permission_issued":False,
                          "business_goal_closed":False},ensure_ascii=False)); return 2
    print(json.dumps(result,ensure_ascii=False,indent=2)); return 0

if __name__ == "__main__":
    raise SystemExit(main())
