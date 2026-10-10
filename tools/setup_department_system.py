#!/usr/bin/env python3
"""Validate the current source package, then install only missing empty files."""
from __future__ import annotations

import argparse
from contextvars import ContextVar
import json
import os
from pathlib import Path

from department_system_package import (
    CONFIG_NAMES, COMPANY_NAMES, _check_routes, _normal_file, parse_json,
    relative_path, validate_model, validate_registry, validate_release,
)

_CREATED_OWNERS = ContextVar("department_setup_created_files", default=None)


def _create_file(path: Path, raw: bytes):
    # Exclusive creation never overwrites a binding or concurrent local edit.
    with path.open("xb") as handle:
        owners = _CREATED_OWNERS.get()
        if owners is not None:
            stat = os.fstat(handle.fileno())
            owners[path] = (stat.st_dev, stat.st_ino)
        handle.write(raw)


def _json(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _target(root, rel):
    path = root / relative_path(rel)
    if path.is_symlink() or any(parent.is_symlink() for parent in path.parents):
        raise ValueError("Symlink installation target blocked: " + rel)
    if path.exists() and not path.is_file():
        raise ValueError("Installation file target is not a file: " + rel)
    for parent in path.parents:
        if parent == root:
            break
        if parent.exists() and not parent.is_dir():
            raise ValueError("Installation parent is not a directory: " + rel)
    return path


def setup(root: Path):
    root = Path(root).absolute()
    manifest = validate_release(root)
    # The five configuration defaults and seven company placeholders are the
    # existing installation inputs. agent-role-policy stays a public method.
    contents = {}
    for name in CONFIG_NAMES:
        rel = "examples/" + name + ".example.json"
        raw = _normal_file(root, rel).read_bytes()
        if not isinstance(parse_json(raw, name), dict):
            raise ValueError("Expected configuration object: " + name)
        contents["data/" + name + ".json"] = raw
    for name in COMPANY_NAMES:
        contents[name + ".md"] = _normal_file(root, "examples/" + name + ".md").read_bytes()

    existing = {}
    effective = {}
    for rel, raw in contents.items():
        path = _target(root, rel)
        if path.exists():
            existing[rel] = path.read_bytes()
        if rel.startswith("data/"):
            effective[Path(rel).stem] = parse_json(existing.get(rel, raw), rel)
    validate_model(effective["task-contract"])
    registry = effective["department-registry"]
    if not isinstance(registry, dict) or not isinstance(registry.get("departments"), list):
        raise ValueError("Invalid current department registry")
    available = {row["path"] for row in manifest["files"]}
    # Existing locally configured external methods remain local. Do not inspect
    # or copy their contents, and do not convert them into package authority.
    role_check = json.loads(json.dumps(registry))
    for row in role_check.get("departments", []):
        if not isinstance(row, dict) or not isinstance(row.get("approved_subskill_paths", []), list):
            raise ValueError("Invalid current dynamic role")
        methods = row.get("approved_subskill_paths", [])
        if any(not isinstance(rel, str) for rel in methods):
            raise ValueError("Invalid approved method path")
        row["approved_subskill_paths"] = [rel for rel in methods if not rel.startswith("/")]
    rows = validate_registry(role_check, available)
    retired = {row["id"] for row in rows if row.get("new_dispatch_enabled") is False}
    _check_routes(effective["department-routing-rules"], retired)
    for name in CONFIG_NAMES:
        if not isinstance(effective[name], dict):
            raise ValueError("Invalid effective configuration: " + name)
        _check_routes(effective[name], retired)

    roles = []
    for role in rows:
        role_id = role["id"]
        memory_path = "data/learning/departments/" + role_id + ".json"
        contents[memory_path] = _json({"department": role_id, "lessons": [], "events": []})
        roles.append({"id": role_id, "name": role.get("name", role_id),
                      "professional_skill": role["professional_skill"], "memory_path": memory_path})
    contents["data/learning/department-learning-registry.json"] = _json({
        "schema_version": "1.0", "departments": roles,
        "skill_path": "skills/flashcast-department-learning/SKILL.md",
        "memory_dir": "data/learning/departments", "event_log_path": "logs/department-learning-events.jsonl",
    })
    contents["data/learning/department-inheritance.json"] = _json({
        "schema_version": "1.0", "confirmed_facts": [], "DATA_MISSING": True,
    })
    contents["data/content/organic-execution-policy.json"] = _json({
        "keyword_content_coverage_acceptance": {"controller_checkpoint": ""},
        "phase": "setup_required", "natural_50_daily_ip": "DATA_MISSING",
    })
    contents["data/content/organic-growth-backlog.json"] = _json({"items": [], "state": "setup_required"})

    planned = {}
    for rel, raw in contents.items():
        path = _target(root, rel)
        if path.exists():
            existing.setdefault(rel, path.read_bytes())
        else:
            planned[rel] = raw
    directories = set()
    for rel in planned:
        parent = (root / rel).parent
        while parent != root:
            directories.add(parent)
            parent = parent.parent
    for name in ("logs", "reports", "drafts", "backups"):
        path = root / name
        if path.is_symlink() or (path.exists() and not path.is_dir()):
            raise ValueError("Invalid installation output directory: " + name)
        directories.add(path)
    # No mkdir or file write has occurred. Protect the effective data read above
    # against a concurrent update before creating any missing installation file.
    for rel, raw in existing.items():
        if _target(root, rel).read_bytes() != raw:
            raise ValueError("Concurrent local installation data changed: " + rel)

    created_files, created_dirs, owners = [], [], {}
    ownership_token = _CREATED_OWNERS.set(owners)
    try:
        for path in sorted(directories, key=lambda item: (len(item.parts), str(item))):
            if not path.exists():
                path.mkdir()
                created_dirs.append(path)
        for rel, raw in planned.items():
            path = _target(root, rel)
            if path.exists():
                raise ValueError("Concurrent installation target appeared: " + rel)
            # Record before calling the creation helper so even a failed partial
            # write can be removed; only this task's missing targets are eligible.
            created_files.append((path, raw))
            _create_file(path, raw)
    except Exception:
        for path, raw in reversed(created_files):
            if path.is_file() and not path.is_symlink():
                stat = path.stat()
                if owners.get(path) != (stat.st_dev, stat.st_ino):
                    continue
                written = path.read_bytes()
                if raw.startswith(written):
                    path.unlink()
        for path in reversed(created_dirs):
            try:
                path.rmdir()
            except OSError:
                pass  # Preserve a directory that received concurrent data.
        raise
    finally:
        _CREATED_OWNERS.reset(ownership_token)
    return {"created": list(planned), "binding_status": "unbound_setup_required" if "data/department-registry.json" in planned else "existing_binding_preserved",
            "chats_created": 0, "automations_created": 0, "external_permissions_issued": 0,
            "package_fingerprint": manifest["fingerprint"], "runtime_model": manifest["runtime_model"],
            "roles": len(rows), "preflight": "PASS_CURRENT_COMPLETE_PACKAGE_AND_EFFECTIVE_INPUTS"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    print(json.dumps(setup(args.root), ensure_ascii=False))
