"""Build a bounded, deterministic key from an exact frozen result identity.

This helper reads an outbox and emits metadata only. It cannot queue, notify,
dispatch, approve, publish, or mutate a workflow.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

EVENTS = {
    "notification_queued", "notification_sent", "notification_blocked",
    "controller_received", "controller_decision", "controller_followthrough",
}


def result_key(event: str, task_id: str, department: str,
               candidate_version: str, result_sha256: str) -> str:
    if event not in EVENTS:
        raise ValueError("Unknown result handoff event")
    if not all(isinstance(x, str) and x.strip() for x in
               (task_id, department, candidate_version)):
        raise ValueError("Missing original task, department, or candidate version")
    if len(result_sha256) != 64 or any(c not in "0123456789abcdef" for c in result_sha256):
        raise ValueError("Expected the final outbox SHA-256")
    identity = [event, task_id, department, candidate_version, result_sha256]
    digest = hashlib.sha256(json.dumps(identity, ensure_ascii=True,
                                     separators=(",", ":")).encode()).hexdigest()
    return f"rh-{event}-{digest}"


def describe_outbox(path: Path, event: str) -> dict[str, str]:
    raw = path.read_bytes()
    outbox = json.loads(raw)
    if not isinstance(outbox, dict):
        raise ValueError("Expected a frozen outbox object")
    identity = {
        "task_id": outbox.get("task_id", ""),
        "sender_department": outbox.get("department", ""),
        "candidate_version": outbox.get("candidate_version", ""),
        "result_sha256": hashlib.sha256(raw).hexdigest(),
    }
    key = result_key(event, identity["task_id"], identity["sender_department"],
                     identity["candidate_version"], identity["result_sha256"])
    return {"event": event, **identity, "idempotency_key": key}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outbox", type=Path, required=True)
    parser.add_argument("--event", choices=sorted(EVENTS), default="notification_queued")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    value = describe_outbox(args.outbox, args.event)
    print(json.dumps(value, ensure_ascii=False) if args.json else value["idempotency_key"])


if __name__ == "__main__":
    main()
