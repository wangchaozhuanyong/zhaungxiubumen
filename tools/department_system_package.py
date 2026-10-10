"""Validate current portable rules and package bytes before setup or startup.

The manifest fingerprint detects inconsistent input, not a trusted signature.
Local business data and original authorizations are never package defaults.
"""
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sys

MODEL = "goal_delivery_assistant_v1"
SCHEMA = "department-system-package-v1"
CONFIG_NAMES = ("department-registry", "department-routing-rules", "task-contract", "action-policy", "delegation-policy")
COMPANY_NAMES = ("company-context", "service-area", "services-and-pricing", "customer-personas", "brand-guidelines", "case-studies", "faq")
REQUIRED_FILES = frozenset({
    "AGENTS.md", "README.md", ".codex/config.toml",
    "tools/export_department_system.py", "tools/setup_department_system.py",
    "tools/department_system_package.py", "tools/flashcast_ops.py",
    "tools/department_reply.py", "tools/workflow_control.py", "tools/goal_delivery_runtime.py",
    "playbooks/department-system-current.md",
    "skills/flashcast-department-learning/SKILL.md", "skills/flashcast-cms-publishing/SKILL.md",
    "examples/agent-role-policy.example.json",
} | {"examples/" + name + ".example.json" for name in CONFIG_NAMES}
  | {"examples/" + name + ".md" for name in COMPANY_NAMES})
LOCAL_DIRS = frozenset({"data", "logs", "reports", "drafts", "backups", "accounts", "runtime", "learning", ".git", ".venv", ".test-tmp"})
QA = r"(?:QA[12]?(?![A-Za-z0-9_-])|质检(?:部门|部)?|qa-technical(?![A-Za-z0-9_-]))"
POSITIVE_OLD_CHAIN = re.compile(
    r"(?:→|->|⇒)\s*" + QA + r"|(?:交|进入|转交|提交给)\s*(?:固定)?" + QA
    + r"|" + QA + r".{0,50}(?:→|->|⇒|转交|交)\s*(?:老板|总部|HQ|总控)"
    r"|最后一个专业波次结束后才进入\s*QA|总部采用决定|总部二审", re.I)
NEGATIVE_OLD_CHAIN = re.compile(
    r"(?:禁止|不得|不能|不再|不要)(?:再|重新)?(?:恢复|回到|沿用|沿|使用|采用|执行|重建|加入|重加|启用|走|要求|进入|提交给|交|复制|加载)"
    r"|不恢复|不启用|废弃|退出|已退役|停用|拒绝(?:正向)?旧|must\s+not|do\s+not|no\s+longer", re.I)
DIRECT_NEGATIVE_OLD_CHAIN = re.compile(
    r"(?:禁止|不得|不能|不要)\s*(?:(?:专业(?:部门|结果)?\s*(?:→|->|⇒)\s*)?" + QA
    + r"|(?:提交给|转交|交|进入)\s*(?:固定)?" + QA + r"|总部二审)"
    r"|(?:不继承|不再派|不要求)\s*(?:固定QA路由|QA1/QA2|qa/qa-technical)(?:、|或)总部二审"
    r"|不(?:交|提交给|进入)\s*(?:固定)?" + QA, re.I)


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key: " + key)
        result[key] = value
    return result


def parse_json(raw, name):
    try:
        return json.loads(raw, object_pairs_hook=_unique)
    except (ValueError, UnicodeError) as exc:
        raise ValueError("Invalid JSON input: " + name) from exc


def relative_path(value):
    if not isinstance(value, str) or not value or "\\" in value or ":" in value:
        raise ValueError("Invalid package path")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or path.as_posix() != value or value == ".":
        raise ValueError("Invalid package path: " + value)
    return value


def _normal_file(root, rel):
    path = root / relative_path(rel)
    if path.is_symlink() or any(parent.is_symlink() for parent in path.parents):
        raise ValueError("Symlink package input blocked: " + rel)
    if not path.is_file():
        raise ValueError("Missing package input: " + rel)
    return path


def validate_model(contract):
    current = contract.get("goal_delivery_runtime", {}) if isinstance(contract, dict) else {}
    if not isinstance(current, dict):
        raise ValueError("Current goal/assistant runtime contract required")
    if current.get("model") != MODEL or current.get("assistant_decisions_enabled") is not True:
        raise ValueError("Current goal/assistant runtime contract required")
    for name, expected in (("HQ_second_review_required", False), ("producer_self_review_allowed", False),
                           ("fixed_qa_new_dispatch_enabled", False), ("single_acceptance_owner", True)):
        if name in current and current[name] is not expected:
            raise ValueError("Obsolete or self-review runtime setting: " + name)


def validate_registry(registry, available):
    rows = registry.get("departments") if isinstance(registry, dict) else None
    if not isinstance(rows, list) or not rows:
        raise ValueError("Current dynamic departments required")
    ids = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Invalid dynamic role")
        role = row.get("id")
        if not isinstance(role, str) or not re.fullmatch(r"[a-z][a-z0-9-]{0,63}", role) or role in ids:
            raise ValueError("Invalid or duplicate dynamic role")
        ids.append(role)
        if role in {"qa", "qa-technical"} and (row.get("new_dispatch_enabled") is not False or row.get("mode") != "retired_history"):
            raise ValueError("Legacy fixed QA route must be retired")
        for field in ("role_config", "professional_skill", "department_readme"):
            rel = relative_path(row.get(field))
            if PurePosixPath(rel).parts[0] not in {".codex", "departments", "skills"} or rel not in available:
                raise ValueError("Missing dynamic role source: " + role + ":" + field)
        paths = row.get("approved_subskill_paths", [])
        if not isinstance(paths, list):
            raise ValueError("Invalid approved method paths: " + role)
        for rel in paths:
            if not isinstance(rel, str):
                raise ValueError("Invalid approved method path: " + role)
            # External approved methods need local setup; never import machine skills.
            if rel.startswith(("<CODEX_HOME>/", "<AGENTS_HOME>/", "<USER_HOME>/")):
                continue
            if rel.startswith("/"):
                raise ValueError("Nonportable approved method path: " + role)
            if relative_path(rel) not in available:
                raise ValueError("Missing approved local method: " + role)
    return rows


def _check_routes(value, retired):
    if isinstance(value, list):
        for child in value:
            _check_routes(child, retired)
    elif isinstance(value, dict):
        if "goal_delivery_runtime" in value:
            current = value["goal_delivery_runtime"]
            if not isinstance(current, dict) or current.get("model") != MODEL:
                raise ValueError("Obsolete declared default runtime model")
            if "assistant_decisions_enabled" in current and current["assistant_decisions_enabled"] is not True:
                raise ValueError("Obsolete assistant runtime flag")
        if "runtime_model" in value and value["runtime_model"] != MODEL:
            raise ValueError("Obsolete default runtime model")
        if value.get("reviewer_department") in retired:
            raise ValueError("Default input would revive retired fixed QA reviewer")
        if value.get("HQ_second_review_required") is True or value.get("fixed_qa_new_dispatch_enabled") is True:
            raise ValueError("Default input would revive obsolete QA/HQ chain")
        for key, child in value.items():
            if key in {"required_departments", "parallel_departments", "follow_up_departments"} and isinstance(child, list) and retired.intersection(child):
                raise ValueError("Default input would revive retired fixed QA route")
            if not key.startswith(("retired_", "historical_", "legacy_")) and key != "backward_compatibility":
                _check_routes(child, retired)


def current_markdown(text):
    """Keep current instructions; explicit legacy method sections are readable.

    A history heading alone is insufficient: it must also declare that the
    section is not a current runtime/template, in its title or first paragraph.
    """
    lines = text.splitlines()
    result, history_level, fenced = [], None, False
    for index, line in enumerate(lines):
        if line.lstrip().startswith(("```", "~~~")):
            fenced = not fenced
        heading = re.match(r"^(#{1,6})\s+(.+)$", line) if not fenced else None
        if heading:
            level, title = len(heading[1]), heading[2]
            if history_level is not None and level <= history_level:
                history_level = None
            following = next((value.strip() for value in lines[index + 1:] if value.strip()), "")
            declaration = title + " " + following
            if "历史兼容" in title and re.search(r"非当前|非运行|非现行|不作为现行", declaration):
                history_level = level if history_level is None else history_level
        if history_level is None:
            result.append(line)
    return "\n".join(result)


def _check_text(text, rel):
    if PurePosixPath(rel).suffix == ".md":
        text = current_markdown(text)
    for clause in re.split(r"[\n。；;，,]|但是|但|并把|并将|并且|且|而|\band\b", text):
        for match in POSITIVE_OLD_CHAIN.finditer(clause):
            # Only a negation before this instruction suppresses this match.
            prefix = clause[max(0, match.start() - 60):match.end()]
            if not (NEGATIVE_OLD_CHAIN.search(prefix) or DIRECT_NEGATIVE_OLD_CHAIN.search(prefix)):
                raise ValueError("Positive obsolete QA/HQ chain in current input: " + rel)
        for match in re.finditer(r"(?:现行模式|当前模式|runtime_model|current model).{0,35}(?P<obsolete>legacy|fixed[_-]qa|qa[_-]hq|goal_delivery_assistant_v[02-9])", clause, re.I):
            prefix = clause[max(0, match.start("obsolete") - 60):match.start("obsolete")]
            if not NEGATIVE_OLD_CHAIN.search(prefix):
                raise ValueError("Obsolete default runtime model: " + rel)


def non_runtime_paths(payloads, registry):
    """Classify explicit history, never let a manifest exempt current rules."""
    result = set()
    for row in registry["departments"]:
        if row.get("new_dispatch_enabled") is False:
            prefix = "departments/" + row["id"] + "/"
            result.update(path for path in payloads if path.startswith(prefix))
            result.add(row["role_config"])
    for rel, raw in payloads.items():
        if rel.startswith("examples/") and rel.endswith(".json") and rel not in REQUIRED_FILES:
            value = parse_json(raw, rel)
            if isinstance(value, dict) and value.get("historical_only") is True and value.get("operational_template") is False:
                result.add(rel)
    return sorted(result)


def validate_payloads(payloads, roles, retired_roles, non_runtime_files):
    if sys.version_info < (3, 9):
        raise ValueError("Python 3.9 or later required")
    for rel in payloads:
        relative_path(rel)
    missing = REQUIRED_FILES.difference(payloads)
    if missing:
        raise ValueError("Missing required package input: " + ", ".join(sorted(missing)))
    registry = parse_json(payloads["examples/department-registry.example.json"], "registry")
    rows = validate_registry(registry, payloads)
    ids = [row["id"] for row in rows]
    retired = {row["id"] for row in rows if row.get("new_dispatch_enabled") is False}
    if roles != ids or retired_roles != [row["id"] for row in rows if row["id"] in retired]:
        raise ValueError("Manifest dynamic role inventory mismatch")
    historical = non_runtime_paths(payloads, registry)
    if sorted(non_runtime_files) != historical or len(set(non_runtime_files)) != len(non_runtime_files):
        raise ValueError("Manifest non-runtime classification mismatch")
    validate_model(parse_json(payloads["examples/task-contract.example.json"], "task-contract"))
    for name in CONFIG_NAMES + ("agent-role-policy",):
        value = parse_json(payloads["examples/" + name + ".example.json"], name)
        if not isinstance(value, dict):
            raise ValueError("Expected configuration object: " + name)
        _check_routes(value, retired)
    policy = parse_json(payloads["examples/action-policy.example.json"], "action-policy")
    if policy.get("status") != "setup_required" or policy.get("paid_promotion_enabled") is not False or policy.get("standing_authorizations") != []:
        raise ValueError("Public defaults must have empty external authority")
    def permissions(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key in {"standing_authorizations", "exact_requests"} and child != []:
                    raise ValueError("Public defaults contain external permission")
                permissions(child)
        elif isinstance(value, list):
            for child in value:
                permissions(child)
    permissions(policy)
    for row in rows:
        binding = row.get("chat_binding", {})
        if binding.get("status") != "unbound" or binding.get("dispatch_eligible") is not False or any(binding.get(key) for key in ("task_id", "thread_id", "project_id", "cwd", "title", "sidebar_section_id", "handoff_path")):
            raise ValueError("Public defaults contain live chat binding")
    for rel, raw in payloads.items():
        suffix = PurePosixPath(rel).suffix
        if suffix == ".json":
            value = parse_json(raw, rel)
            if rel not in historical:
                _check_routes(value, retired)
        elif suffix == ".py":
            ast.parse(raw.decode("utf-8"), filename=rel)
        elif suffix in {".md", ".toml", ".yaml", ".yml"} and rel not in historical:
            _check_text(raw.decode("utf-8"), rel)
    # Required startup/install tools may only import an available local module.
    for rel in ("tools/flashcast_ops.py", "tools/setup_department_system.py", "tools/export_department_system.py"):
        for node in ast.walk(ast.parse(payloads[rel].decode("utf-8"))):
            if isinstance(node, ast.ImportFrom) and node.module:
                module = node.module.split(".")[0]
                if module in {"workflow_control", "department_reply", "goal_delivery_runtime", "department_system_package"} and "tools/" + module + ".py" not in payloads:
                    raise ValueError("Missing startup module: " + module)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    module = alias.name.split(".")[0]
                    if module in {"workflow_control", "department_reply", "goal_delivery_runtime", "department_system_package"} and "tools/" + module + ".py" not in payloads:
                        raise ValueError("Missing startup module: " + module)
    return registry


def seal_manifest(manifest):
    result = {key: value for key, value in manifest.items() if key != "fingerprint"}
    raw = json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    result["fingerprint"] = hashlib.sha256(raw).hexdigest()
    return result


def validate_release(root, allow_local=True):
    root = Path(root).absolute()
    if root.is_symlink() or any(parent.is_symlink() for parent in root.parents):
        raise ValueError("Symlink package root blocked")
    manifest = parse_json(_normal_file(root, "release-manifest.json").read_bytes(), "release-manifest.json")
    if not isinstance(manifest, dict) or manifest.get("schema_version") != SCHEMA or manifest.get("runtime_model") != MODEL:
        raise ValueError("Current declared package/runtime model required")
    if seal_manifest(manifest) != manifest:
        raise ValueError("Package manifest fingerprint mismatch")
    for flag in ("live_bindings_exported", "live_health_exported", "live_ledgers_exported", "credentials_exported", "external_permissions_exported", "candidate_admission_exported", "native_owner_evidence_exported"):
        if manifest.get(flag) is not False:
            raise ValueError("Package private/authority boundary missing: " + flag)
    files = manifest.get("files")
    if not isinstance(files, list):
        raise ValueError("Package file inventory required")
    payloads = {}
    for row in files:
        if not isinstance(row, dict):
            raise ValueError("Invalid manifest file entry")
        rel = relative_path(row.get("path"))
        if rel in payloads or rel == "release-manifest.json" or PurePosixPath(rel).parts[0] in LOCAL_DIRS or rel in {name + ".md" for name in COMPANY_NAMES}:
            raise ValueError("Invalid or duplicate manifest package file: " + rel)
        raw = _normal_file(root, rel).read_bytes()
        if type(row.get("bytes")) is not int or row["bytes"] != len(raw) or row.get("release_sha256") != hashlib.sha256(raw).hexdigest():
            raise ValueError("Package file fingerprint mismatch: " + rel)
        payloads[rel] = raw
    for path in root.rglob("*"):
        rel = path.relative_to(root).as_posix()
        parts = path.relative_to(root).parts
        local = allow_local and (parts[0] in LOCAL_DIRS or "__pycache__" in parts or rel in {name + ".md" for name in COMPANY_NAMES} or parts[0].startswith(".env") or path.name == ".DS_Store")
        if local:
            continue
        if path.is_symlink():
            raise ValueError("Symlink package file blocked: " + rel)
        if path.is_file() and rel != "release-manifest.json" and rel not in payloads:
            raise ValueError("Unknown package input: " + rel)
    validate_payloads(payloads, manifest.get("roles"), manifest.get("retired_roles"), manifest.get("non_runtime_files", []))
    return manifest


def validate_current(root):
    root = Path(root)
    contract = parse_json(_normal_file(root, "data/task-contract.json").read_bytes(), "current task-contract")
    validate_model(contract)
    registry = parse_json(_normal_file(root, "data/department-registry.json").read_bytes(), "current registry")
    if not isinstance(registry, dict) or not isinstance(registry.get("departments"), list):
        raise ValueError("Invalid current dynamic departments")
    available = set()
    for row in registry.get("departments", []) if isinstance(registry, dict) else []:
        if not isinstance(row, dict):
            raise ValueError("Invalid current dynamic role")
        for field in ("role_config", "professional_skill", "department_readme"):
            rel = relative_path(row.get(field))
            _normal_file(root, rel); available.add(rel)
        methods = row.get("approved_subskill_paths", [])
        if not isinstance(methods, list) or any(not isinstance(rel, str) for rel in methods):
            raise ValueError("Invalid approved current method paths")
        for rel in methods:
            if isinstance(rel, str) and not rel.startswith(("/", "<")):
                _normal_file(root, rel); available.add(rel)
    # Current company machine paths are legitimate existing methods, not exports.
    local_registry = json.loads(json.dumps(registry))
    for row in local_registry.get("departments", []):
        row["approved_subskill_paths"] = [rel for rel in row.get("approved_subskill_paths", []) if not rel.startswith("/")]
    rows = validate_registry(local_registry, available)
    retired = {row["id"] for row in rows if row.get("new_dispatch_enabled") is False}
    routing = parse_json(_normal_file(root, "data/department-routing-rules.json").read_bytes(), "current routing")
    _check_routes(routing, retired)
    return registry


def validate_startup(root):
    root = Path(root)
    if (root / "release-manifest.json").exists():
        validate_release(root)
    return validate_current(root)
