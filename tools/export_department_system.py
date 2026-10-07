#!/usr/bin/env python3
"""Prepare a public source release; never copy live ledgers or run git push."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
ROLES = (
    "operations", "operations-assistant", "paid-growth-data",
    "content-organic-website", "seo-content-research", "local-seo-maps",
    "visual-design-video", "sales", "qa", "qa-technical", "publishing",
)
POLICIES = (
    "department-routing-rules.json", "task-contract.json", "delegation-policy.json",
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


def public_text(text):
    # Portable references only; the local source and its evidence are untouched.
    text = text.replace(str(ROOT), "<PROJECT_ROOT>")
    text = re.sub(r"/Users/[^/\s\"']+/\.codex/skills", "<CODEX_HOME>/skills", text)
    text = re.sub(r"/Users/[^/\s\"']+/\.agents/skills", "<AGENTS_HOME>/skills", text)
    text = re.sub(r"/Users/[^/\s\"']+/Desktop/装修网站(?:/zhuangxiuwangzhan-main)?", "<WEBSITE_PROJECT_ROOT>", text)
    registry_path = ROOT / "data/department-registry.json"
    if registry_path.is_file():
        registry = json.loads(registry_path.read_text())
        for role in registry.get("departments", []):
            binding = role.get("chat_binding", {})
            for field in ("task_id", "project_id", "sidebar_section_id"):
                value = binding.get(field)
                if isinstance(value, str) and value:
                    text = text.replace(value, "<LOCAL_" + field.upper() + ">")
    text = text.replace("<WEBSITE_DEVELOPER_THREAD>", "<WEBSITE_DEVELOPER_THREAD>")
    text = text.replace("<WEBSITE_PROJECT_ID>", "<WEBSITE_PROJECT_ID>")
    text = text.replace(str(Path.home()), "<USER_HOME>")
    # The same exact CMS record/source pin may occur in several method modules.
    # Replace those local identities consistently, without changing live files.
    followthrough = ROOT / "tools/owner_delegated_publisher_followthrough.py"
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
    return text


def public_source_text(rel, text):
    """Remove native owner evidence from the public preparation-only example."""
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


def prepare(root: Path, target: Path):
    root, target = root.resolve(), target.resolve()
    if root not in target.parents or target == root:
        raise ValueError("Release output must be inside the source project")
    target.mkdir(parents=True, exist_ok=True)
    old_manifest = target / "release-manifest.json"
    old_files = json.loads(old_manifest.read_text()).get("files", []) if old_manifest.exists() else []
    tracked = []

    def copy(rel):
        source = root / rel
        if not source.is_file() or source.is_symlink():
            raise ValueError("Missing or symlink source: " + rel)
        raw = source.read_bytes()
        text = public_source_text(rel, public_text(raw.decode("utf-8")))
        hits = [match for pattern in SECRET_PATTERNS for match in pattern.finditer(text)]
        # Existing scanner tests intentionally contain a header with this exact
        # non-key fixture. A PEM body or any different credential still blocks.
        hits = [m for m in hits if not (
            Path(rel).name.startswith("test_")
            and text[m.end():].startswith("\\nsynthetic-fixture\""))]
        if hits:
            raise ValueError("Potential secret detected; output blocked: " + rel)
        dest = target / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text)
        tracked.append({"path": rel, "source_sha256": hashlib.sha256(raw).hexdigest(),
                        "release_sha256": hashlib.sha256(dest.read_bytes()).hexdigest()})

    # Source allowlist. Do not recursively copy the business workspace.
    for name in ("AGENTS.md", "README.md"):
        copy(name)
    for base, suffixes in (("tools", {".py", ".md"}), ("playbooks", {".md"}),
                           ("prompts", {".md"})):
        for source in sorted((root / base).glob("*")):
            if source.is_file() and source.suffix in suffixes:
                copy(str(source.relative_to(root)))
    registry = json.loads((root / "data/department-registry.json").read_text())
    role_rows = {row["id"]: row for row in registry["departments"]}
    copy(".codex/config.toml")
    if (root / ".codex/hooks.json").is_file():
        copy(".codex/hooks.json")
    for role in ROLES:
        for source in sorted((root / "departments" / role).rglob("*")):
            relative = source.relative_to(root / "departments" / role)
            if (source.is_file() and source.suffix in {".md", ".py", ".yaml"}
                    and not EXCLUDED_PARTS.intersection(relative.parts)
                    and (str(relative) in {"README.md", "SKILL.md"}
                         or relative.parts[0] in {"agents", "references", "scripts", "tests"})):
                copy(str(source.relative_to(root)))
        agent = role_rows[role]["role_config"]
        agent_path = Path(agent)
        if (agent_path.is_absolute() or ".." in agent_path.parts
                or agent_path.suffix != ".toml"
                or agent_path.parts[0] not in {".codex", "departments"}):
            raise ValueError("Unapproved role configuration path")
        copy(agent)
    for skill in ("flashcast-department-learning", "flashcast-cms-publishing"):
        for source in sorted((root / "skills" / skill).rglob("*")):
            if source.is_file() and source.suffix in {".md", ".py", ".yaml"}:
                copy(str(source.relative_to(root)))
    for name in ("packet.json", "step-a-result.json", "claim-input.json", "qa2-review-plan.json"):
        if (root / "examples" / name).is_file():
            copy("examples/" + name)
    if (root / "ci/department-system-checks.yml.example").is_file():
        copy("ci/department-system-checks.yml.example")

    examples = target / "examples"
    rows = []
    for item in registry["departments"]:
        if item["id"] not in ROLES:
            continue
        safe = {key: item[key] for key in (
            "id", "name", "professional_skill", "role_config", "department_readme",
            "approved_subskills", "input_paths", "output_paths",
        ) if key in item}
        safe = json.loads(public_text(json.dumps(safe, ensure_ascii=False)))
        safe["chat_binding"] = {"status": "unbound", "task_id": "", "project_id": "",
            "cwd": "", "title": "", "sidebar_section_id": "", "sidebar_section_name": "",
            "reply_health": "not_verified", "dispatch_eligible": False, "handoff_path": ""}
        rows.append(safe)
    write_json(examples / "department-registry.example.json", {
        "schema_version": "2.0", "project": {"project_id": "", "cwd": ""},
        "total_role_count": len(rows), "departments": rows,
        "health_policy": {"verification_ttl_hours": 26},
        "public_template": True,
    })
    for name in POLICIES:
        value = json.loads(public_text((root / "data" / name).read_text()))
        # The examples hold contract/method only. Never import executable grants.
        value["public_template"] = True
        write_json(examples / name.replace(".json", ".example.json"), value)
    policy = json.loads(public_text((root / "data/action-policy.json").read_text()))
    policy.update(status="setup_required", public_template=True, paid_promotion_enabled=False,
                  standing_authorizations=[])
    routing = policy["routing_policy"]
    routing.update(source_project_id="", source_project_root="", source_project_name="")
    routing.pop("owner_directed_code_handoff", None)
    routing.pop("owner_delegated_publishing_preparation", None)
    routing.pop("owner_delegated_publisher_followthrough", None)
    for value in policy["action_classes"].values():
        if isinstance(value, dict) and "exact_requests" in value:
            value["exact_requests"] = []
    policy["autonomous_site_release_policy"]["enabled"] = False
    write_json(examples / "action-policy.example.json", policy)
    for name in COMPANY:
        (examples / name).write_text("# " + name.removesuffix(".md") +
            "\n\n请填写本公司的已确认事实及确认日期。未确认内容写待确认；不导入其他公司的价格、案例或授权。\n")
    (target / ".gitignore").write_text(
        "__pycache__/\n*.py[cod]\n.venv/\n.env*\n!.env.example\n"
        "data/\nlogs/\nreports/\ndrafts/\nbackups/\nreleases/\nruntime/\n"
        "accounts/\n*.sqlite*\n*.db\n*.pem\n*.key\n.DS_Store\n" +
        "".join("/" + name + "\n" for name in COMPANY))
    write_json(target / "release-manifest.json", {
        "version": "2026.10.07.2", "artifact_type": "department_system_source",
        "roles": list(ROLES), "files": tracked,
        "live_bindings_exported": False, "live_ledgers_exported": False,
        "credentials_exported": False, "external_permissions_exported": False,
        "public_templates_require_local_setup": True,
        "native_owner_evidence_exported": False,
        "owner_preparation_helper_is_non_executable_example": True,
    })
    # Withdraw only unchanged files from the previous generated release. Keep
    # edited or unknown files for explicit review instead of deleting user WIP.
    current = {row["path"] for row in tracked}
    for row in old_files:
        if row["path"] in current:
            continue
        path = (target / row["path"]).resolve()
        if target not in path.parents or not path.is_file() or path.is_symlink():
            raise ValueError("Invalid previous release path")
        if hashlib.sha256(path.read_bytes()).hexdigest() != row["release_sha256"]:
            raise ValueError("Previous generated file was edited; preserve and review: " + row["path"])
        recovery = target / "backups" / "withdrawn-source" / row["path"]
        recovery.parent.mkdir(parents=True, exist_ok=True)
        if recovery.exists():
            if recovery.read_bytes() != path.read_bytes():
                raise ValueError("Recovery file conflict: " + row["path"])
            path.unlink()
        else:
            path.rename(recovery)
    return {"files": len(tracked), "roles": len(rows), "target": str(target)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(ROOT, args.target), ensure_ascii=False))
