#!/usr/bin/env python3
"""Prepare a public source release; never copy live ledgers or run git push."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
import re

from department_system_package import (
    MODEL, SCHEMA, non_runtime_paths, seal_manifest, validate_model,
    validate_payloads, validate_release,
)

ROOT = Path(__file__).resolve().parents[1]
POLICIES = (
    "department-routing-rules.json", "task-contract.json", "delegation-policy.json",
    "agent-role-policy.json",
)
COMPANY = (
    "company-context.md", "service-area.md", "services-and-pricing.md",
    "customer-personas.md", "brand-guidelines.md", "case-studies.md", "faq.md",
)
EXCLUDED_PARTS = {"assets", "library", "runtime", "learning", "__pycache__", ".git"}
SECRET_PATTERNS = (
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\b(?:ghp_|github_pat_|sk-proj-)[A-Za-z0-9_]{20,}"),
    re.compile(r"\bBearer\s+[A-Za-z0-9_.-]{25,}"),
    re.compile(r"(?i)(?:password|access_token|api_key)\s*[=:]\s*[\"'][^\"']{16,}[\"']"),
)


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def public_numeric_identifiers(text):
    """Keep public identifier comparisons consistent without real destinations."""
    def synthetic(value):
        if value.startswith("000"):
            return value
        width = len(value) - 3
        number = int(hashlib.sha256(value.encode()).hexdigest(), 16) % (10 ** width)
        return "000" + str(number).zfill(width)

    text = re.sub(r"(?P<quote>[\"'])(?P<identifier>[0-9]{10,22})(?P=quote)",
                  lambda match: match["quote"] + synthetic(match["identifier"]) + match["quote"], text)
    text = re.sub(r"\bAW-([0-9]{10,22})\b",
                  lambda match: "AW-" + synthetic(match[1]), text)
    text = re.sub(r"\b(locations|customers|accounts|campaigns|adGroups|assets)/([0-9]{10,22})\b",
                  lambda match: match[1] + "/" + synthetic(match[2]), text)
    text = re.sub(r"\b(campaigns?|assets?|google-business-profile)[:/-]([0-9]{10,22}(?:\+[0-9]{10,22})*)\b",
                  lambda match: match[1] + match[0][len(match[1])] + "+".join(synthetic(value) for value in match[2].split("+")), text)
    # Conversion-action CSV rows put the identifier immediately before AW-.
    text = re.sub(r"(?<=,)([0-9]{10,22})(?=,AW-[0-9]{10,22}\b)",
                  lambda match: synthetic(match[1]), text)
    return text



def public_text(text, root=None):
    root = (root or ROOT).resolve()
    # Portable references only; the local source and its evidence are untouched.
    text = text.replace(str(root), "<PROJECT_ROOT>")
    text = re.sub(r"/Users/[^/\s\"']+/\.codex/skills", "<CODEX_HOME>/skills", text)
    text = re.sub(r"/Users/[^/\s\"']+/\.agents/skills", "<AGENTS_HOME>/skills", text)
    text = re.sub(r"/Users/[^/\s\"']+/\.codex/plugins", "<CODEX_HOME>/plugins", text)
    text = re.sub(r"/Users/[^/\s\"']+/Desktop/装修网站(?:/zhuangxiuwangzhan-main)?", "<WEBSITE_PROJECT_ROOT>", text)
    registry_path = root / "data/department-registry.json"
    if registry_path.is_file():
        registry = json.loads(registry_path.read_text())
        def identities(value):
            if isinstance(value, dict):
                for field, child in value.items():
                    if field in {"task_id", "thread_id", "project_id", "sidebar_section_id", "cwd", "handoff_path"} and isinstance(child, str) and child:
                        yield field, child
                    elif isinstance(child, (dict, list)):
                        yield from identities(child)
            elif isinstance(value, list):
                for child in value:
                    yield from identities(child)
        bindings = [role.get("chat_binding", {}) for role in registry.get("departments", [])]
        bindings.extend([registry.get("project", {}), registry.get("collaboration_bindings", {})])
        for field, value in identities(bindings):
            text = text.replace(value, "<LOCAL_" + field.upper() + ">")
    text = text.replace("<WEBSITE_DEVELOPER_THREAD>", "<WEBSITE_DEVELOPER_THREAD>")
    text = text.replace("<LOCAL_PROJECT_ID>", "<WEBSITE_PROJECT_ID>")
    text = text.replace(str(Path.home()), "<USER_HOME>")
    # Native message/turn/thread IDs and the local Ads account are never a
    # portable authority. Synthetic values cannot bind to a real chat.
    text = re.sub(r"\b01a[0-9a-f]{5}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
                  lambda match: "example-native-" + hashlib.sha256(match[0].encode()).hexdigest()[:16], text)
    text = re.sub(r"\b[0-9]{3}-[0-9]{3}-[0-9]{4}\b", "example-ads-account", text)
    # The same exact CMS record/source pin may occur in several method modules.
    # Replace those local identities consistently, without changing live files.
    followthrough = root / "tools/owner_delegated_publisher_followthrough.py"
    if followthrough.is_file():
        values = {}
        for node in ast.parse(followthrough.read_text()).body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id in {"TARGET_IDS", "SOURCE_PINS"}:
                        values[target.id] = ast.literal_eval(node.value)
        for index, value in enumerate(values.get("TARGET_IDS", [])):
            text = text.replace(value, "example-cms-record-" + str(index + 1))
        for name, pins in values.get("SOURCE_PINS", {}).items():
            for index, value in enumerate(pins):
                example = hashlib.sha256(("example-only-" + name + "-" + str(index)).encode()).hexdigest()
                text = text.replace(value, example)
    return public_numeric_identifiers(text)


def public_source_text(rel, text):
    """Remove native owner evidence from the public preparation-only example."""
    if rel in {"tools/owner_paid_logo_policy.py", "tools/owner_paid_completion_policy.py", "tools/owner_paid_final_qa_route.py"}:
        tree = ast.parse(text)
        lines = text.splitlines(keepends=True)
        for node in sorted(tree.body, key=lambda item: item.lineno, reverse=True):
            if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
                name = node.targets[0].id
                if name.startswith("AUTH") or name == "FUNDS_AUTH" or name.startswith("HISTORICAL_"):
                    if not isinstance(node.value, (ast.Dict, ast.List, ast.Constant)):
                        raise ValueError("Unexpected native evidence expression; export blocked")
                    replacement = {} if isinstance(node.value, ast.Dict) else [] if isinstance(node.value, ast.List) else "synthetic-evidence-not-native"
                    lines[node.lineno - 1:node.end_lineno] = [name + " = " + repr(replacement) + "\n"]
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in {"check", "policy_reasons"}:
                first = node.body[0]
                line = first.end_lineno if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str) else first.lineno - 1
                lines[line:line] = ['    raise ValueError("public_template_has_no_native_authorization")\n']
        result = "".join(lines)
        ast.parse(result)
        return result
    if rel == "tools/owner_delegated_publisher_followthrough.py":
        tree = ast.parse(text)
        replacements = {
            "TARGET_IDS": ["example-old-house", "example-quotation-checklist", "example-design"],
            "SOURCE_PINS": {name: tuple(hashlib.sha256(("example-only-" + name + "-" + str(i)).encode()).hexdigest()
                                        for i in range(2)) for name in ("v17", "v18", "v20")},
        }
        nodes = {target.id: node for node in tree.body if isinstance(node, ast.Assign)
                 for target in node.targets if isinstance(target, ast.Name) and target.id in replacements}
        if set(nodes) != set(replacements):
            raise ValueError("Followthrough private-data fields changed; export blocked")
        lines = text.splitlines(keepends=True)
        for name, node in sorted(nodes.items(), key=lambda item: item[1].lineno, reverse=True):
            lines[node.lineno - 1:node.end_lineno] = [name + " = " + repr(replacements[name]) + "\n"]
        result = "".join(lines)
        ast.parse(result)
        return result
    if rel != "tools/owner_delegated_publishing_preparation.py":
        return text
    tree = ast.parse(text)
    expected = {"AUTH_TURN_ID", "AUTH_MESSAGE_ID", "AUTH_TEXT", "AUTH_TEXT_SHA256"}
    assignments = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id.startswith("AUTH_"):
                if target.id in assignments:
                    raise ValueError("Duplicate owner-evidence field; export blocked")
                assignments[target.id] = node
    if set(assignments) != expected:
        raise ValueError("Unexpected owner-evidence fields; export blocked")
    example_text = "Synthetic example only; not a native authorization.\n"
    examples = {
        "AUTH_TURN_ID": "example-turn-not-native",
        "AUTH_MESSAGE_ID": "example-message-not-native",
        "AUTH_TEXT": example_text,
        "AUTH_TEXT_SHA256": hashlib.sha256(example_text.encode()).hexdigest(),
    }
    lines = text.splitlines(keepends=True)
    for name, node in sorted(assignments.items(), key=lambda item: item[1].lineno, reverse=True):
        lines[node.lineno - 1:node.end_lineno] = [name + " = " + repr(examples[name]) + "\n"]
    text = "".join(lines)
    signature = "def _frozen_request(root: Path, policy: dict[str, Any]) -> dict[str, Any]:\n"
    guard = '    _require(not PUBLIC_TEMPLATE_ONLY, "public_template_has_no_native_authorization")\n'
    if text.count(signature) != 1:
        raise ValueError("Preparation entrypoint changed; export blocked")
    if "PUBLIC_TEMPLATE_ONLY" not in text:
        text = text.replace("AUTH_TURN_ID = ", "PUBLIC_TEMPLATE_ONLY = True\nAUTH_TURN_ID = ", 1)
        text = text.replace(signature, signature + guard, 1)
    elif text.count("PUBLIC_TEMPLATE_ONLY = True") != 1 or text.count(signature + guard) != 1:
        raise ValueError("Public preparation guard missing; export blocked")
    ast.parse(text)
    return text


def public_policy(value):
    """Keep methods; remove this company's native candidates and grants."""
    if isinstance(value, list):
        return [public_policy(item) for item in value]
    if not isinstance(value, dict):
        return value
    result = {}
    for key, child in value.items():
        if (key.startswith("owner_") or key in {"collaboration_bindings", "chat_binding",
                "health_evidence", "expansion_history", "system_rebuild_authorization"}
                or "admission" in key or "handover" in key or key.endswith("_packet")):
            continue
        if key in {"standing_authorizations", "exact_requests"}:
            result[key] = []
        else:
            result[key] = public_policy(child)
    return result


def public_exact_helper(rel, text):
    """Retain exact-action method source without its private frozen payload."""
    name = Path(rel).name
    exact_helper = (name.startswith("owner_") or name == "native_publisher_exact_registration.py"
                    or name.startswith("cms_") and "native_read_contract" in name)
    if not exact_helper or not rel.startswith("tools/") or not rel.endswith(".py"):
        return text
    tree = ast.parse(text)
    lines = text.splitlines(keepends=True)
    for node in sorted(tree.body, key=lambda item: item.lineno, reverse=True):
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name) and isinstance(node.value, (ast.Dict, ast.List)):
            replacement = {} if isinstance(node.value, ast.Dict) else []
            lines[node.lineno - 1:node.end_lineno] = [node.targets[0].id + " = " + repr(replacement) + "\n"]
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in {
                "check", "policy_reasons", "publisher_registration_reason", "check_owner_delegated_followthrough"}:
            first = node.body[0]
            line = first.end_lineno if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str) else first.lineno - 1
            lines[line:line] = ['    raise ValueError("public_template_has_no_native_authorization")\n']
    result = "".join(lines)
    ast.parse(result)
    return result


def validate_public_runtime(root, registry):
    """Legacy evidence remains readable, but cannot become a new public route."""
    retired = {row["id"] for row in registry["departments"] if row.get("new_dispatch_enabled") is False}
    if any(row["id"] in {"qa", "qa-technical"} and row.get("new_dispatch_enabled") is not False for row in registry["departments"]):
        raise ValueError("Legacy fixed QA route must be retired before export")
    contract = json.loads((root / "data/task-contract.json").read_text())
    validate_model(contract)

    def check(value):
        if isinstance(value, list):
            for item in value:
                check(item)
        elif isinstance(value, dict):
            if value.get("new_dispatch_enabled") is False or value.get("historical_only") is True:
                return
            if value.get("reviewer_department") in retired:
                raise ValueError("Public template would revive retired fixed QA reviewer")
            for key, child in value.items():
                if key in {"required_departments", "parallel_departments", "follow_up_departments"} and isinstance(child, list) and retired.intersection(child):
                    raise ValueError("Public template would revive retired fixed QA route")
                if not key.startswith(("retired_", "historical_", "legacy_")):
                    check(child)
    check(json.loads((root / "data/department-routing-rules.json").read_text()))
    for source in (root / "examples").rglob("*.json"):
        check(json.loads(source.read_text()))
    for source in (root / "templates").rglob("*.json"):
        check(json.loads(source.read_text()))


def prepare(root: Path, target: Path):
    if target.is_symlink() or any(item.is_symlink() for item in target.parents):
        raise ValueError("Symlink release target blocked")
    root, target = root.resolve(), target.resolve()
    if root not in target.parents or target == root:
        raise ValueError("Release output must be inside the source project")
    if target.is_symlink() or any(item.is_symlink() for item in target.parents if item != root.parent):
        raise ValueError("Symlink release target blocked")
    registry = json.loads((root / "data/department-registry.json").read_text())
    roles = registry.get("departments", [])
    ids = [row.get("id") for row in roles]
    if not all(isinstance(role, str) and re.fullmatch(r"[a-z][a-z0-9-]*", role) for role in ids) or len(set(ids)) != len(ids):
        raise ValueError("Invalid or duplicate dynamic role")
    validate_public_runtime(root, registry)
    payloads, tracked = {}, []

    def add(rel, text, source_raw=None):
        path = Path(rel)
        if path.is_absolute() or ".." in path.parts or not path.parts:
            raise ValueError("Invalid export path")
        hits = [match for pattern in SECRET_PATTERNS for match in pattern.finditer(text)]
        hits = [m for m in hits if not (
            path.name.startswith("test_")
            and text[m.end():].startswith("\\nsynthetic-fixture\""))]
        if hits:
            raise ValueError("Potential secret detected; output blocked: " + rel)
        raw = text.encode("utf-8")
        if rel in payloads and payloads[rel] != raw:
            raise ValueError("Conflicting generated export path: " + rel)
        if rel in payloads:
            return
        payloads[rel] = raw
        tracked.append({"path": rel, "source_sha256": hashlib.sha256(source_raw).hexdigest() if source_raw is not None else None,
                        "release_sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)})

    def copy(rel):
        source = root / rel
        if not source.is_file() or source.is_symlink() or any(item.is_symlink() for item in source.parents if item != root.parent):
            raise ValueError("Missing or symlink source: " + rel)
        raw = source.read_bytes()
        text = raw.decode("utf-8")
        if source.suffix == ".json" and Path(rel).parts[0] in {"templates", "examples"}:
            value = public_policy(json.loads(text))
            if rel in {"examples/packet.json", "examples/step-a-result.json"} and isinstance(value, dict) and value.get("synthetic_example_only") is True:
                value.update(historical_only=True, operational_template=False)
            text = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
        text = public_source_text(rel, public_text(text, root))
        add(rel, public_exact_helper(rel, text), raw)

    for name in ("AGENTS.md", "README.md"):
        copy(name)
    # Recursion includes new consumer tools, automation prompts and templates.
    # Runtime/assets/business data remain outside the source allowlist.
    for base, suffixes in (("tools", {".py", ".md"}), ("playbooks", {".md"}),
                           ("prompts", {".md"}), ("templates", {".md", ".json", ".yaml", ".yml"})):
        for source in sorted((root / base).rglob("*")):
            relative = source.relative_to(root / base)
            if source.is_file() and source.suffix in suffixes and not EXCLUDED_PARTS.intersection(relative.parts):
                copy(source.relative_to(root).as_posix())
    copy(".codex/config.toml")
    if (root / ".codex/hooks.json").is_file():
        copy(".codex/hooks.json")
    for row in roles:
        role = row["id"]
        for source in sorted((root / "departments" / role).rglob("*")):
            relative = source.relative_to(root / "departments" / role)
            if (source.is_file() and source.suffix in {".md", ".py", ".yaml", ".yml"}
                    and not EXCLUDED_PARTS.intersection(relative.parts)
                    and (str(relative) in {"README.md", "SKILL.md"}
                         or relative.parts[0] in {"agents", "references", "scripts", "tests"})):
                copy(source.relative_to(root).as_posix())
        for field in ("role_config", "professional_skill", "department_readme"):
            rel = row.get(field)
            if not isinstance(rel, str):
                raise ValueError("Missing dynamic role source: " + role + ":" + field)
            path = Path(rel)
            if path.is_absolute() or ".." in path.parts or path.parts[0] not in {".codex", "departments", "skills"}:
                raise ValueError("Unapproved role source path")
            copy(rel)
    for skill in ("flashcast-department-learning", "flashcast-cms-publishing"):
        for source in sorted((root / "skills" / skill).rglob("*")):
            relative = source.relative_to(root / "skills" / skill)
            if source.is_file() and source.suffix in {".md", ".py", ".yaml", ".yml"} and not EXCLUDED_PARTS.intersection(relative.parts):
                copy(source.relative_to(root).as_posix())
    for source in sorted((root / "examples").rglob("*")):
        if source.is_file() and source.suffix in {".json", ".md", ".yaml", ".yml"}:
            copy(source.relative_to(root).as_posix())
    if (root / "ci/department-system-checks.yml.example").is_file():
        copy("ci/department-system-checks.yml.example")

    def example(rel, value):
        text = public_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", root)
        add("examples/" + rel, text)

    rows = []
    for row in roles:
        safe = {key: row[key] for key in (
            "id", "name", "professional_skill", "role_config", "department_readme",
            "approved_subskills", "approved_subskill_paths", "input_paths", "output_paths",
            "mode", "new_dispatch_enabled", "coordination_authority", "capabilities",
            "result_report_contract", "result_report_entrypoint",
        ) if key in row}
        safe["chat_binding"] = {"status": "unbound", "task_id": "", "project_id": "", "cwd": "", "title": "",
            "sidebar_section_id": "", "sidebar_section_name": "", "reply_health": "not_verified", "dispatch_eligible": False, "handoff_path": ""}
        rows.append(safe)
    example("department-registry.example.json", {
        "schema_version": registry.get("schema_version", "2.0"), "project": {"project_id": "", "cwd": ""},
        "departments": rows, "total_role_count": len(rows),
        "active_department_count": sum(row.get("new_dispatch_enabled", True) is not False for row in rows),
        "health_policy": {"verification_ttl_hours": 26}, "public_template": True,
        "runtime_bindings_require_local_setup": True,
    })
    for name in POLICIES:
        value = public_policy(json.loads((root / "data" / name).read_text()))
        value["public_template"] = True
        example(name.replace(".json", ".example.json"), value)
    policy = public_policy(json.loads((root / "data/action-policy.json").read_text()))
    policy.update(status="setup_required", public_template=True, paid_promotion_enabled=False, standing_authorizations=[])
    routing = policy.get("routing_policy", {})
    routing.update(source_project_id="", source_project_root="", source_project_name="")
    if "autonomous_site_release_policy" in policy:
        policy["autonomous_site_release_policy"]["enabled"] = False
    example("action-policy.example.json", policy)
    for name in COMPANY:
        add("examples/" + name, "# " + name.removesuffix(".md") +
            "\n\n请填写本公司的已确认事实及确认日期。未确认内容写待确认；不导入其他公司的价格、案例或授权。\n")
    add(".gitignore", "__pycache__/\n*.py[cod]\n.venv/\n.env*\n!.env.example\n"
        "data/\nlogs/\nreports/\ndrafts/\nbackups/\nreleases/\nruntime/\n"
        "accounts/\n*.sqlite*\n*.db\n*.pem\n*.key\n.DS_Store\n" + "".join("/" + name + "\n" for name in COMPANY))
    public_registry = json.loads(payloads["examples/department-registry.example.json"])
    retired_roles = [row["id"] for row in rows if row.get("new_dispatch_enabled") is False]
    historical = non_runtime_paths(payloads, public_registry)
    validate_payloads(payloads, ids, retired_roles, historical)
    manifest = seal_manifest({
        "schema_version": SCHEMA, "runtime_model": MODEL, "non_runtime_files": historical,
        "version": "2026.10.10.goal-delivery-assistant-v1", "artifact_type": "department_system_source",
        "roles": ids, "files": sorted(tracked, key=lambda row: row["path"]),
        "retired_roles": retired_roles,
        "live_bindings_exported": False, "live_health_exported": False, "live_ledgers_exported": False,
        "credentials_exported": False, "external_permissions_exported": False,
        "candidate_admission_exported": False, "public_templates_require_local_setup": True,
        "native_owner_evidence_exported": False, "owner_preparation_helper_is_non_executable_example": True,
        "runtime_model_source": "examples/task-contract.example.json#goal_delivery_runtime",
    })
    old_manifest = target / "release-manifest.json"
    if old_manifest.exists():
        validate_release(target)
    old_files = json.loads(old_manifest.read_text()).get("files", []) if old_manifest.exists() else []
    old = {row["path"]: row for row in old_files}
    # Preflight every output and withdrawal before writing any generated byte.
    for rel, raw in payloads.items():
        dest = target / rel
        if dest.is_symlink() or any(item.is_symlink() for item in dest.parents if item != target.parent):
            raise ValueError("Symlink generated path blocked: " + rel)
        if dest.exists() and dest.read_bytes() != raw:
            if rel not in old or hashlib.sha256(dest.read_bytes()).hexdigest() != old[rel]["release_sha256"]:
                raise ValueError("Edited or unknown output preserved: " + rel)
    withdrawn = []
    for rel, row in old.items():
        if rel in payloads:
            continue
        path = (target / rel).resolve()
        if target not in path.parents or not path.is_file() or path.is_symlink():
            raise ValueError("Invalid previous release path")
        if hashlib.sha256(path.read_bytes()).hexdigest() != row["release_sha256"]:
            raise ValueError("Previous generated file was edited; preserve and review: " + rel)
        recovery = target / "backups/withdrawn-source" / rel
        if recovery.exists() and recovery.read_bytes() != path.read_bytes():
            raise ValueError("Recovery file conflict: " + rel)
        withdrawn.append((path, recovery))
    target.mkdir(parents=True, exist_ok=True)
    for rel, raw in payloads.items():
        dest = target / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(raw)
    for path, recovery in withdrawn:
        recovery.parent.mkdir(parents=True, exist_ok=True)
        if not recovery.exists():
            path.rename(recovery)
        else:
            # Existing identical recovery preserves the only removed generated copy.
            path.unlink()
    write_json(old_manifest, manifest)
    return {"files": len(tracked), "roles": len(rows), "target": str(target), "external_writes": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(ROOT, args.target), ensure_ascii=False))
