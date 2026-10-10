"""Bounded technical backup eligibility; no route, lease or permission writes."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3

PRIMARY_METHOD = "web-dev-toolkit:code-reviewer"


def _resource_pin(path):
    path = Path(path)
    if not path.is_absolute() or not path.is_file() or path.is_symlink():
        return None
    raw = path.read_bytes()
    return {"path": str(path), "sha256": hashlib.sha256(raw).hexdigest(), "size": len(raw)}


def _methods_ready(root, role, config):
    import workflow_control as w
    skill = role.get("professional_skill")
    if not isinstance(skill, str) or not skill:
        return False
    skill_path = w.safe_path(root, skill)
    if (not skill_path.is_file() or skill_path.is_symlink()
            or hashlib.sha256(skill_path.read_bytes()).hexdigest() != config.get("professional_skill_sha256")):
        return False
    pin = config.get("method_manifest")
    if not isinstance(pin, dict) or w.file_digest(root, pin.get("path", "")) != pin:
        return False
    manifest = w.read_json(w.safe_path(root, pin["path"]))
    if (manifest.get("department") != role.get("id")
            or manifest.get("capability") != "development_backup"
            or manifest.get("mapped_acceptance_capability") != "development"
            or manifest.get("use_scope") != "independent_acceptance_only"
            or any(manifest.get(key) is not False for key in
                   ("production_write_allowed", "account_permissions_granted", "producer_implementation_allowed"))):
        return False
    names, paths = role.get("approved_subskills", []), role.get("approved_subskill_paths", [])
    if not isinstance(names, list) or not isinstance(paths, list) or len(names) != len(paths):
        return False
    approved = dict(zip(names, paths))
    required, methods = manifest.get("required_methods"), manifest.get("methods")
    if not isinstance(required, list) or PRIMARY_METHOD not in required or not isinstance(methods, list):
        return False
    seen = set()
    for method in methods:
        if (not isinstance(method, dict) or method.get("name") in seen
                or not isinstance(method.get("use"), str) or not method["use"].strip()
                or method.get("production_tool_invocation_granted") is not False):
            return False
        name, path = method.get("name"), method.get("path")
        if not isinstance(name, str) or not isinstance(path, str) or approved.get(name) != path:
            return False
        expected = {key: method.get(key) for key in ("path", "sha256", "size")}
        if _resource_pin(path) != expected:
            return False
        seen.add(name)
    return set(required) <= seen


def _committed_transfer(root, task_id, role, config, goal):
    """Only an existing fenced SQL transfer plus original task event can activate."""
    import workflow_control as w
    history = goal.get("assignment_history", [])
    if not isinstance(history, list) or not history or not task_id:
        return False
    change = history[-1]
    if (not isinstance(change, dict) or change.get("target_assistant") != role
            or change.get("previous_assistant") not in config["transfer_from"]
            or type(change.get("fence")) is not int or change["fence"] < 1
            or change.get("result_identity", {}).get("task_id") != task_id):
        return False
    database = Path(root) / "logs/result-coordination.sqlite3"
    if not database.is_file() or database.is_symlink():
        return False
    with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True) as connection:
        matches = []
        for raw, previous, recorded in connection.execute(
                "SELECT payload_json,previous_hash,record_hash FROM coordination_audit ORDER BY seq"):
            payload = json.loads(raw)
            if (payload.get("event") == "transfer"
                    and payload.get("identity") == change["result_identity"]
                    and payload.get("details", {}).get("assignment_change") == change):
                digest = hashlib.sha256(json.dumps([previous, payload], sort_keys=True,
                    ensure_ascii=True, separators=(",", ":")).encode()).hexdigest()
                if recorded != digest:
                    return False
                matches.append(payload)
    if len(matches) != 1:
        return False
    events = w.read_jsonl(Path(root) / w.WORKFLOW_EVENTS)
    # Check provenance hashes without recursively selecting the reviewer again.
    # The existing workflow consumer separately validates state/receipt rules.
    previous = ""
    for event in events:
        if (event.get("previous_event_hash", "") != previous
                or event.get("event_hash") != w.sha256_value(
                    {key: value for key, value in event.items() if key != "event_hash"})):
            return False
        previous = event["event_hash"]
    return any(event.get("task_id") == task_id
               and event.get("details", {}).get("assignment_transfer") == change for event in events)


def review_capable(root, role, goal, *, task_id=None, transfer_from=None, allow_backup=True):
    """Normal capabilities stay exact; a backup never becomes a default reviewer.

    transfer_from is a read-only preparation context supplied by the existing
    explicit transfer consumer. Ordinary claims require its committed evidence.
    """
    import workflow_control as w
    try:
        root = Path(root).resolve()
        item = w.department_registry(root).get(role, {})
        authority = item.get("coordination_authority", {})
        capability = goal.get("acceptance_capability")
        producers = goal.get("producer_departments", [])
        if (not isinstance(capability, str) or not isinstance(producers, list) or role in producers
                or authority.get("routine_decisions") is not True or item.get("new_dispatch_enabled") is False):
            return False
        capabilities = authority.get("review_capabilities", [])
        if capability in capabilities and capability != "development_backup":
            return True
        config = authority.get("technical_review_backup", {})
        if (not allow_backup or capability != "development" or not isinstance(config, dict)
                or config.get("enabled") is not True or "development_backup" not in capabilities
                or config.get("capability") != "development_backup"
                or config.get("mapped_acceptance_capability") != capability
                or config.get("default_assistant") != "operations-assistant-2"
                or config.get("transfer_from") != ["operations-assistant-2"]
                or config.get("explicit_transfer_required") is not True
                or config.get("production_write_allowed") is not False
                or item.get("production_write_allowed") is not False
                or goal.get("required_execution_actions")):
            return False
        permitted = config.get("allowed_producer_departments", [])
        scopes, prefixes = goal.get("authorized_scope", []), config.get("allowed_scope_prefixes", [])
        if (not producers or not isinstance(permitted, list) or not set(producers) <= set(permitted)
                or not isinstance(scopes, list) or not scopes or not isinstance(prefixes, list) or not prefixes
                or any(not isinstance(prefix, str) or not prefix.startswith("project:flashcast:") for prefix in prefixes)
                or any(not isinstance(scope, str) or not any(scope.startswith(prefix) for prefix in prefixes) for scope in scopes)
                or not _methods_ready(root, item, config)):
            return False
        if transfer_from is not None:
            return transfer_from in config["transfer_from"]
        return (goal.get("responsible_assistant") == role
                and _committed_transfer(root, task_id, role, config, goal))
    except (OSError, ValueError, TypeError, KeyError, sqlite3.Error, w.WorkflowError):
        return False
