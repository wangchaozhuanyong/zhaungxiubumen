#!/usr/bin/env python3
"""Fail-closed identity check for one live FLASH CAST music-scout task."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

ROOT = Path("<PROJECT_ROOT>")
PROJECT_ID = "<LOCAL_PROJECT_ID>"
THREAD_ID = "<LOCAL_TASK_ID>"
DEPARTMENT = "visual-design-video"


def validate(registry: dict, snapshot: dict, cwd: Path, now: datetime) -> dict:
    reasons: list[str] = []
    items = [d for d in registry.get("departments", []) if d.get("id") == DEPARTMENT]
    binding = items[0].get("chat_binding", {}) if len(items) == 1 else {}
    if len(items) != 1 or binding.get("status") != "bound_and_visible":
        reasons.append("registry_binding_missing_or_not_visible")
    if snapshot.get("source_tool") != "list_threads":
        reasons.append("complete_live_list_required")
    try:
        observed = datetime.fromisoformat(snapshot["observed_at"].replace("Z", "+00:00"))
        age = (now - observed).total_seconds()
        if not 0 <= age <= 300:
            reasons.append("live_snapshot_stale_or_future")
    except (KeyError, ValueError, TypeError):
        reasons.append("live_observed_at_missing_or_invalid")
    threads = snapshot.get("threads", [])
    target = threads[0] if len(threads) == 1 and isinstance(threads[0], dict) else {}
    if len(threads) != 1:
        reasons.append("single_target_snapshot_required")
    for live_key, registry_key, fixed in (
        ("id", "task_id", THREAD_ID),
        ("projectId", "project_id", PROJECT_ID),
        ("hostId", "host_id", "local"),
    ):
        if target.get(live_key) != fixed or binding.get(registry_key) != fixed:
            reasons.append(f"{live_key}_missing_or_mismatch")
    if not target.get("title") or target.get("title") != binding.get("title"):
        reasons.append("title_missing_or_mismatch")
    if target.get("kind") != "codex" or target.get("status") not in {
        "active", "idle", "completed", "needsAttention", "needs_attention", "waiting"
    }:
        reasons.append("live_task_not_usable")
    for name, value in (("live_cwd", target.get("cwd")), ("registry_cwd", binding.get("cwd")), ("actual_cwd", str(cwd))):
        if not value or not Path(value).is_absolute() or Path(value).resolve() != ROOT.resolve():
            reasons.append(f"{name}_missing_or_mismatch")
    key = f"codex:thread:local:{THREAD_ID}"
    sections = snapshot.get("sections", [])
    matches = [s for s in sections if isinstance(s, dict) and key in s.get("itemKeys", [])]
    section = matches[0] if len(matches) == 1 else {}
    if len(sections) != 1 or len(matches) != 1 or section.get("name") != "装修公司部门" or not section.get("sectionId"):
        reasons.append("sidebar_group_missing_or_ambiguous")
    drift = not reasons and section.get("sectionId") != binding.get("sidebar_section_id")
    status = "BLOCKED_CROSS_PROJECT" if reasons else "STALE_SIDEBAR_BINDING" if drift else "PASS"
    return {
        "schema_version": "1.0", "status": status,
        "reasons": reasons or (["sidebar_id_drift_requires_operations_recovery"] if drift else []),
        "checked_at": now.isoformat(timespec="seconds"),
        "source_tool": snapshot.get("source_tool"),
        "observed_at": snapshot.get("observed_at"),
        "department": DEPARTMENT, "expected_thread_id": THREAD_ID,
        "business_writes_allowed": status == "PASS",
        "registry_modified": False,
    }


def project_path(value: str) -> Path:
    path = Path(value).resolve()
    if not path.is_relative_to(ROOT.resolve()):
        raise argparse.ArgumentTypeError("Evidence paths must belong to the FLASH CAST project.")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live-snapshot", type=project_path, required=True)
    parser.add_argument("--output", type=project_path, required=True)
    args = parser.parse_args()
    try:
        registry = json.loads((ROOT / "data/department-registry.json").read_text())
        snapshot = json.loads(args.live_snapshot.read_text())
        result = validate(registry, snapshot, Path.cwd(), datetime.now(timezone.utc))
    except (OSError, ValueError, TypeError, AttributeError):
        result = {"status": "BLOCKED_CROSS_PROJECT", "reasons": ["identity_input_unreadable"], "business_writes_allowed": False}
    if args.output == args.live_snapshot or args.output.exists():
        parser.error("Output must be a new evidence file, not an existing file or snapshot.")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "PASS" else 4


if __name__ == "__main__":
    raise SystemExit(main())
