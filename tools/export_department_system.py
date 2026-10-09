#!/usr/bin/env python3
"""Prepare a public source release; never copy live ledgers or run git push."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
import re
import tomllib

ROOT = Path(__file__).resolve().parents[1]
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
PRIVATE_MODULES = {
    "publisher_native_sparse_admission", "managed_cms_permit_issuer",
    "native_cms_admission", "native_cms_admission_v2", "native_cms_issuer_integration",
    "native_remaining186_blog_registration", "native_five_source_projection_registration",
    "native_publisher_exact_registration", "native_repair_faq_registration",
    "original_task_publisher_handover", "publisher_designated_successor_qa",
    "owner_paid_final_qa_route", "owner_paid_completion_policy",
}
LOCAL_PERSONAL_PATHS = re.compile(r"(?:/Users/|/home/)[\w.-]+|[A-Za-z]:\\Users\\[\w.-]+", re.IGNORECASE)
NATIVE_IDS = re.compile(r"\b(?:[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}|msg_[0-9a-f]{16,})\b", re.IGNORECASE)


def private_module(name):
    if name == 'native_inventory':
        return False  # Generic native-shape validator; never an authorization issuer.
    return name in PRIVATE_MODULES or name.startswith(('native_','publisher_','managed_cms_')) or name.startswith('cms_') and 'native' in name



PUBLIC_HANDOVER_FACADE = r'''
TASK = "synthetic-deny-only-publisher-handover"
_TASK_DENY_SHA256 = "ab9519afcf80d18db599b123d167b32f5c42862b4f04147554d460539ebfa11d"
POLICY_KEY = "original_task_publisher_execution_only_handover"


def _private_task(value):
    import hashlib
    return (isinstance(value, str) and (value == TASK
            or hashlib.sha256(value.encode()).hexdigest() == _TASK_DENY_SHA256))


def _has_handover(value):
    if isinstance(value, dict):
        if (POLICY_KEY in value or value.get("publisher_execution_handover")
                or _private_task(value.get("task_id"))):
            return True
        return any(_has_handover(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_has_handover(item) for item in value)
    return False


def _ordinary_context(root, task_id=None, snapshot=None, receipts=None, receipt=None):
    from pathlib import Path
    import workflow_control as workflow
    if _private_task(task_id) or _has_handover([snapshot, receipts, receipt]):
        raise workflow.WorkflowError("public_template_has_no_native_authorization")
    policy = workflow.load_policy(Path(root))
    events = workflow.read_jsonl(Path(root) / workflow.WORKFLOW_EVENTS)
    if _has_handover(policy) or _has_handover(events):
        raise workflow.WorkflowError("public_template_has_no_native_authorization")


def binding(root, task_id, receipts=None):
    _ordinary_context(root, task_id, receipts=receipts)
    return None


def replay(root, snapshot):
    _ordinary_context(root, snapshot=snapshot)
    return None


def legacy_context(root, snapshot, receipts):
    _ordinary_context(root, snapshot=snapshot, receipts=receipts)
    return snapshot, receipts


def validate_new_receipt(root, snapshot, receipts, receipt):
    _ordinary_context(root, snapshot=snapshot, receipts=receipts, receipt=receipt)
    return False


def progress(root, task_id, action_id, scope):
    _ordinary_context(root, task_id)
    return None


def recoverable_dispatch(root, snapshot, receipts, sent):
    _ordinary_context(root, snapshot=snapshot, receipts=receipts, receipt=sent)
    return False


def retry_projection(root, task_id, action_id, scope, receipt_id, approval_id):
    _ordinary_context(root, task_id)
    return None


def dispatch_precheck(root, snapshot, department, thread, action_id, scope):
    _ordinary_context(root, snapshot=snapshot)
    return []


def shadow_projection(root, task_id):
    _ordinary_context(root, task_id)
    return None
'''


def synthetic_auth_values():
    text = "Synthetic example only; not a native authorization.\n"
    return {"AUTH_TURN_ID": "example-turn-not-native",
            "AUTH_MESSAGE_ID": "example-message-not-native",
            "AUTH_TEXT": text, "AUTH_TEXT_SHA256": hashlib.sha256(text.encode()).hexdigest()}


def synthetic_auth_fields(path, tree):
    """Only our exact complete guarded example is public, never native evidence."""
    if path.name != "owner_delegated_publishing_preparation.py":
        return set()
    expected = synthetic_auth_values()
    assignments = {}
    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        for target in targets:
            if isinstance(target, ast.Name) and (target.id.startswith("AUTH_") or target.id == "PUBLIC_TEMPLATE_ONLY"):
                if target.id in assignments:
                    return set()
                try:
                    assignments[target.id] = ast.literal_eval(node.value)
                except (ValueError, TypeError):
                    return set()
    if set(assignments) != set(expected) | {"PUBLIC_TEMPLATE_ONLY"}:
        return set()
    if assignments.pop("PUBLIC_TEMPLATE_ONLY") is not True or assignments != expected:
        return set()
    tracked = set(expected) | {"PUBLIC_TEMPLATE_ONLY"}
    if any(sum(isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store)
               and node.id == name for node in ast.walk(tree)) != 1 for name in tracked):
        return set()
    functions = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
    if any(sum(isinstance(node, ast.FunctionDef) and node.name == name
               for node in tree.body) != 1 for name in ("_frozen_request", "_require")):
        return set()
    entry, require = functions.get("_frozen_request"), functions.get("_require")
    guard = ast.parse('_require(not PUBLIC_TEMPLATE_ONLY, "public_template_has_no_native_authorization")').body[0]
    if entry is None or not entry.body or ast.dump(entry.body[0]) != ast.dump(guard):
        return set()
    if require is None or len(require.body) != 1 or not isinstance(require.body[0], ast.If):
        return set()
    test = require.body[0]
    condition = ast.parse("not condition", mode="eval").body
    if (ast.dump(test.test) != ast.dump(condition) or test.orelse or len(test.body) != 1
            or not isinstance(test.body[0], ast.Raise)):
        return set()
    return set(expected)


def private_literals(root):
    """Actual values stay in memory; audit output uses hashes and locations only."""
    values=set()
    for p in (Path(root)/"tools").glob("*.py"):
        if p.name.startswith("test_"):continue
        tree=ast.parse(p.read_text())
        public_auth = synthetic_auth_fields(p, tree)
        for node in tree.body:
            if not isinstance(node,(ast.Assign,ast.AnnAssign)):continue
            targets=node.targets if isinstance(node,ast.Assign) else [node.target]
            if not any(isinstance(t,ast.Name) and (
                    t.id.startswith("AUTH_") or "SOURCE" in t.id and "PIN" in t.id
                    or "THREAD" in t.id or t.id in {"PROJECT_ID","TARGET_IDS","TARGETS"})
                    for t in targets):continue
            if any(isinstance(t, ast.Name) and t.id in public_auth for t in targets):continue
            try:value=ast.literal_eval(node.value)
            except (ValueError,TypeError):continue
            def collect(v):
                if isinstance(v,str) and len(v)>=16:values.add(v)
                elif isinstance(v,dict):
                    for a,b in v.items():collect(a);collect(b)
                elif isinstance(v,(list,tuple,set)):
                    for x in v:collect(x)
            collect(value)
    return values


def validate_public_tree(root, target):
    forbidden=private_literals(root);hits=[]
    for p in sorted(Path(target).rglob("*")):
        if p.is_symlink():raise ValueError("Public tree symlink blocked")
        rel=str(p.relative_to(target))
        if Path(rel).parts[0] in {"data","logs","accounts","reports","drafts","backups","history"}:
            raise ValueError("Private runtime/business directory blocked: "+rel)
        if not p.is_file():continue
        text=p.read_text();strings=[text]
        if p.suffix.casefold()==".py":
            strings += [n.value for n in ast.walk(ast.parse(text)) if isinstance(n,ast.Constant) and isinstance(n.value,str)]
        elif p.suffix.casefold() in {".json", ".toml"}:
            def flatten(value):
                if isinstance(value,str):strings.append(value)
                elif isinstance(value,dict):
                    for k,v in value.items():flatten(k);flatten(v)
                elif isinstance(value,list):
                    for v in value:flatten(v)
            # TOML basic strings, nested arrays/tables and keys must be read
            # semantically; raw Unicode escapes cannot bypass the gate.
            flatten(tomllib.loads(text) if p.suffix.casefold() == ".toml" else json.loads(text))
        for value in forbidden:
            if any(value in s or (re.fullmatch(r"[a-f0-9]{64}", value)
                                  and value in s.lower()) for s in strings):
                hits.append({"path":rel,"value_sha256":hashlib.sha256(value.encode()).hexdigest()})
        if any(NATIVE_IDS.search(value) for value in strings):hits.append({"path":rel,"kind":"native_identity_pattern"})
        if any(LOCAL_PERSONAL_PATHS.search(value) for value in strings):hits.append({"path":rel,"kind":"local_personal_path"})
        secret_hits=[match for pattern in SECRET_PATTERNS for match in pattern.finditer(text)]
        secret_hits=[match for match in secret_hits if not (p.name.startswith('test_') and text[match.end():].startswith('\\nsynthetic-fixture"'))]
        if secret_hits:hits.append({"path":rel,"kind":"secret_pattern"})
    if hits:raise ValueError("Public privacy gate denied "+str(len(hits))+" private-value/identity occurrences; files="+",".join(sorted({x["path"] for x in hits})))
    return {"status":"PASS","files_scanned":sum(p.is_file() for p in Path(target).rglob("*")),"private_literal_hashes_checked":len(forbidden),"private_values_saved":False}


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def public_text(text, root=None, forbidden=None):
    root = Path(root) if root is not None else ROOT
    # Portable references only; the local source and its evidence are untouched.
    text = text.replace(str(root), "<PROJECT_ROOT>")
    text = re.sub(r"/Users/[^/\s\"']+/\.codex/skills", "<CODEX_HOME>/skills", text)
    text = re.sub(r"/Users/[^/\s\"']+/\.agents/skills", "<AGENTS_HOME>/skills", text)
    text = re.sub(r"/Users/[^/\s\"']+/Desktop/装修网站(?:/zhuangxiuwangzhan-main)?", "<WEBSITE_PROJECT_ROOT>", text)
    registry_path = root / "data/department-registry.json"
    if registry_path.is_file():
        registry = json.loads(registry_path.read_text())
        for role in registry.get("departments", []):
            binding = role.get("chat_binding", {})
            for field in ("task_id", "project_id", "sidebar_section_id"):
                value = binding.get(field)
                if isinstance(value, str) and value:
                    if field == "sidebar_section_id" and value in {"pinned", "chats", "threads", "agents", "projects"}:
                        continue  # Public native UI words are not private bindings.
                    text = text.replace(value, "<LOCAL_" + field.upper() + ">")
    text = text.replace("<WEBSITE_DEVELOPER_THREAD>", "<WEBSITE_DEVELOPER_THREAD>")
    text = text.replace("<LOCAL_PROJECT_ID>", "<WEBSITE_PROJECT_ID>")
    text = re.sub(r"/Users/[^/\s\"']+/Desktop/装修公司虚拟员工", "<PROJECT_ROOT>", text)
    text = text.replace(str(Path.home()), "<USER_HOME>")
    # All historical native IDs are private, including superseded bindings.
    text = NATIVE_IDS.sub("<LOCAL_NATIVE_ID>",text)
    text = re.sub(r"\b[0-9]{3}-[0-9]{3}-[0-9]{4}\b","<LOCAL_ACCOUNT_ID>",text)
    for value in sorted(forbidden if forbidden is not None else private_literals(root),key=len,reverse=True):
        if re.fullmatch(r"[a-f0-9]{64}",value):
            replacement=hashlib.sha256(("public-synthetic-only:"+value).encode()).hexdigest()
        else:replacement="<LOCAL_PRIVATE_EVIDENCE>"
        text=text.replace(value,replacement)
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
    return text


def public_source_text(rel, text):
    """Remove native owner evidence from the public preparation-only example."""
    if private_module(Path(rel).stem):
        tree=ast.parse(text)
        deny='    from workflow_control import WorkflowError\n    raise WorkflowError("public_template_has_no_native_authorization")\n'
        result='"""Private native consumer unavailable in a public source template."""\nPUBLIC_TEMPLATE_ONLY = True\n'
        facade = PUBLIC_HANDOVER_FACADE if Path(rel).stem == 'original_task_publisher_handover' else ''
        public_names = {node.name for node in ast.parse(facade).body if isinstance(node, ast.FunctionDef)}
        for node in tree.body:
            if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)):
                if node.name in public_names or node.name == '__getattr__':continue
                result+="\ndef "+node.name+"(*args, **kwargs):\n"+deny
            elif isinstance(node,ast.ClassDef):
                result+="\nclass "+node.name+":\n    def __init__(self,*args,**kwargs):\n        raise ValueError('public_template_has_no_native_authorization')\n"
        result+=facade
        result+="\ndef __getattr__(name):\n    raise AttributeError(name)\n"
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
    examples = synthetic_auth_values()
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
    recovery_root=root / "backups" / "public-export-withdrawn" / target.name
    if old_manifest.exists():
        recovery_root.mkdir(parents=True,exist_ok=True)
        saved=recovery_root / ("manifest-"+hashlib.sha256(old_manifest.read_bytes()).hexdigest()+".json")
        if saved.exists():
            if saved.read_bytes()!=old_manifest.read_bytes():raise ValueError("Manifest recovery conflict")
            old_manifest.unlink()
        else:old_manifest.rename(saved)
    tracked = []
    forbidden=private_literals(root)

    def copy(rel):
        source = root / rel
        if not source.is_file() or source.is_symlink():
            raise ValueError("Missing or symlink source: " + rel)
        raw = source.read_bytes()
        text = public_text(public_source_text(rel, raw.decode("utf-8")),root,forbidden)
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
    if (root / ".env.example").is_file():
        copy(".env.example")
    for base, suffixes in (("tools", {".py", ".md"}), ("playbooks", {".md"}),
                           ("prompts", {".md"})):
        for source in sorted((root / base).glob("*")):
            if source.is_file() and source.suffix.casefold() in suffixes:
                if source.stem.startswith("test_") and private_module(source.stem[5:]):continue
                copy(str(source.relative_to(root)))
    registry = json.loads((root / "data/department-registry.json").read_text())
    role_rows = {row["id"]: row for row in registry["departments"]}
    roles = list(role_rows)
    if len(roles) != len(registry["departments"]) or any(not re.fullmatch(r"[a-z][a-z0-9-]{0,79}",role) for role in roles):
        raise ValueError("Duplicate or unsafe registered role")
    copy(".codex/config.toml")
    if (root / ".codex/hooks.json").is_file():
        copy(".codex/hooks.json")
    for role in roles:
        for source in sorted((root / "departments" / role).rglob("*")):
            relative = source.relative_to(root / "departments" / role)
            if (source.is_file() and source.suffix.casefold() in {".md", ".py", ".yaml"}
                    and not EXCLUDED_PARTS.intersection(relative.parts)
                    and (str(relative) in {"README.md", "SKILL.md"}
                         or relative.parts[0] in {"agents", "references", "scripts", "tests"})):
                copy(str(source.relative_to(root)))
        agent = role_rows[role]["role_config"]
        agent_path = Path(agent)
        if (agent_path.is_absolute() or ".." in agent_path.parts
                or agent_path.suffix.casefold() != ".toml"
                or agent_path.parts[0] not in {".codex", "departments"}):
            raise ValueError("Unapproved role configuration path")
        copy(agent)
    for skill in ("flashcast-department-learning", "flashcast-cms-publishing"):
        for source in sorted((root / "skills" / skill).rglob("*")):
            if source.is_file() and source.suffix.casefold() in {".md", ".py", ".yaml"}:
                copy(str(source.relative_to(root)))
    for name in ("packet.json", "step-a-result.json", "claim-input.json", "qa2-review-plan.json"):
        if (root / "examples" / name).is_file():
            copy("examples/" + name)
    if (root / "ci/department-system-checks.yml.example").is_file():
        copy("ci/department-system-checks.yml.example")

    examples = target / "examples"
    rows = []
    for item in registry["departments"]:
        if item["id"] not in roles:
            continue
        safe = {key: item[key] for key in (
            "id", "name", "professional_skill", "role_config", "department_readme",
            "approved_subskills", "input_paths", "output_paths", "relationship", "mode",
            "code_source_roots", "permissions_inherited", "production_authority_granted",
        ) if key in item}
        safe = json.loads(public_text(json.dumps(safe, ensure_ascii=False),root))
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
        value = json.loads(public_text((root / "data" / name).read_text(),root))
        # The examples hold contract/method only. Never import executable grants.
        value["public_template"] = True
        write_json(examples / name.replace(".json", ".example.json"), value)
    policy = json.loads(public_text((root / "data/action-policy.json").read_text(),root))
    policy.update(status="setup_required", public_template=True, paid_promotion_enabled=False,
                  standing_authorizations=[])
    routing = policy["routing_policy"]
    routing.update(source_project_id="", source_project_root="", source_project_name="")
    routing.pop("owner_directed_code_handoff", None)
    routing.pop("owner_delegated_publishing_preparation", None)
    routing.pop("owner_delegated_publisher_followthrough", None)
    routing.pop("owner_paid_final_qa", None)
    routing.pop("owner_paid_completion", None)
    # Additional bounded native exceptions remain private, regardless of name.
    for key in list(routing):
        if key.startswith("owner_"):routing.pop(key)
    for key in list(policy):
        if key.startswith("owner_"):policy.pop(key)
    policy.pop("cms_publisher_native_sparse_admission", None)
    policy.pop("original_task_publisher_execution_only_handover", None)
    for value in policy["action_classes"].values():
        if isinstance(value, dict) and "exact_requests" in value:
            value["exact_requests"] = []
    policy["autonomous_site_release_policy"]["enabled"] = False
    policy["department_system_upgrade"] = {"migration_required": True, "admitted": False,
        "adoption": None, "routing_grants": {}, "result_grants": {}, "business_current_index": None,
        "cleanup_admitted": False, "production_authority_granted": False}
    write_json(examples / "action-policy.example.json", policy)
    for name in COMPANY:
        (examples / name).write_text("# " + name.removesuffix(".md") +
            "\n\n请填写本公司的已确认事实及确认日期。未确认内容写待确认；不导入其他公司的价格、案例或授权。\n")
    (target / ".gitignore").write_text(
        "__pycache__/\n*.py[cod]\n.venv/\n.env*\n!.env.example\n"
        "data/\nlogs/\nreports/\ndrafts/\nbackups/\nreleases/\nruntime/\n"
        "accounts/\n*.sqlite*\n*.db\n*.pem\n*.key\n.DS_Store\n" +
        "".join("/" + name + "\n" for name in COMPANY))
    # Withdraw unchanged obsolete generated files before validation. Recovery
    # is private and outside the public tree, never bundled as public backups.
    current={row['path'] for row in tracked}
    for row in old_files:
        if row['path'] in current:continue
        path=(target/row['path']).resolve()
        if target not in path.parents or not path.is_file() or path.is_symlink():raise ValueError('Invalid previous release path')
        if hashlib.sha256(path.read_bytes()).hexdigest()!=row['release_sha256']:
            raise ValueError('Previous generated file was edited; preserve and review: '+row['path'])
        recovery=recovery_root/row['path'];recovery.parent.mkdir(parents=True,exist_ok=True)
        if recovery.exists():
            if recovery.read_bytes()!=path.read_bytes():raise ValueError('Recovery file conflict: '+row['path'])
            path.unlink()
        else:path.rename(recovery)
    privacy=validate_public_tree(root,target)
    write_json(target / "release-manifest.json", {
        "version": "2026.10.09.16", "artifact_type": "department_system_source",
        "roles": roles, "files": tracked,
        "live_bindings_exported": False, "live_ledgers_exported": False,
        "credentials_exported": False, "external_permissions_exported": False,
        "public_templates_require_local_setup": True,
        "native_owner_evidence_exported": False,
        "owner_preparation_helper_is_non_executable_example": True,
        "privacy_gate":privacy,
    })
    return {"files": len(tracked), "roles": len(rows), "target": str(target)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT, help="explicit local source project; never a GitHub target")
    parser.add_argument("--target", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.root, args.target), ensure_ascii=False))
