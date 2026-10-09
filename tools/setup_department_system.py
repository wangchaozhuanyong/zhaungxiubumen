#!/usr/bin/env python3
"""Install empty local templates without creating chats or enabling permissions."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def setup(root: Path):
    root = root.resolve()
    examples = root / "examples"
    if not examples.is_dir():
        raise ValueError("Run this command in the exported department-system repository")
    config_names = ("department-registry", "department-routing-rules", "task-contract", "action-policy", "delegation-policy")
    company_names = ("company-context", "service-area", "services-and-pricing", "customer-personas", "brand-guidelines", "case-studies", "faq")
    # Validate the complete installation input before creating local files.
    contents = {}
    for name in config_names:
        content = (examples / (name + ".example.json")).read_text()
        if not isinstance(json.loads(content), dict):
            raise ValueError("Expected configuration object: " + name)
        contents["data/" + name + ".json"] = content
    for name in company_names:
        contents[name + ".md"] = (examples / (name + ".md")).read_text()
    proposed = json.loads(contents["data/department-registry.json"])
    rows = proposed.get("departments", [])
    identifiers = [row.get("id", "") for row in rows]
    if len(identifiers) != len(set(identifiers)) or any(not re.fullmatch(r"[a-z][a-z0-9-]{0,79}",x) for x in identifiers):
        raise ValueError("Duplicate or unsafe registered role")
    created = []

    def put(rel, content):
        path = root / rel
        if path.exists():
            return  # Preserve bindings, history and local edits on repeated setup.
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        created.append(rel)

    for rel, content in contents.items():
        put(rel, content)
    registry = json.loads((root / "data/department-registry.json").read_text())
    roles = []
    for role in registry.get("departments", []):
        role_id = role["id"]
        memory_path = "data/learning/departments/" + role_id + ".json"
        put(memory_path, json.dumps({"department": role_id, "lessons": [], "events": []}, ensure_ascii=False, indent=2) + "\n")
        roles.append({"id": role_id, "name": role.get("name", role_id),
                      "professional_skill": role["professional_skill"], "memory_path": memory_path})
    put("data/learning/department-learning-registry.json", json.dumps({
        "schema_version": "1.0", "departments": roles,
        "skill_path": "skills/flashcast-department-learning/SKILL.md",
        "memory_dir": "data/learning/departments", "event_log_path": "logs/department-learning-events.jsonl",
    }, ensure_ascii=False, indent=2) + "\n")
    put("data/learning/department-inheritance.json", json.dumps({
        "schema_version": "1.0", "confirmed_facts": [], "DATA_MISSING": True,
    }) + "\n")
    put("data/content/organic-execution-policy.json", json.dumps({
        "keyword_content_coverage_acceptance": {"controller_checkpoint": ""},
        "phase": "setup_required", "natural_50_daily_ip": "DATA_MISSING",
    }) + "\n")
    put("data/content/organic-growth-backlog.json", json.dumps({"items": [], "state": "setup_required"}) + "\n")
    for name in ("logs", "reports", "drafts", "backups"):
        (root / name).mkdir(exist_ok=True)
    return {"created": created, "binding_status": "unbound_setup_required",
            "chats_created": 0, "automations_created": 0, "external_permissions_issued": 0}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    print(json.dumps(setup(args.root), ensure_ascii=False))
