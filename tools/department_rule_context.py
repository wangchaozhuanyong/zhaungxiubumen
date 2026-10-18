"""Select current instructions by phase; references never become task actions.

Read reuse concerns instruction text only. Assignments, result queues, health,
authorization, execution and publication must still use their live consumers.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath

SCHEMA = "department-rule-context/v1"
MODEL = "conditional_rule_context_v1"
PHASES = ("startup", "resume", "work", "dispatch", "delivery", "acceptance",
          "production", "recovery", "finish", "daily", "maintenance")
WORK_TYPES = ("general", "system", "content", "website", "cms", "paid", "maps",
              "visual", "sales", "data")
FACTS = ("company-context.md", "service-area.md", "services-and-pricing.md",
         "customer-personas.md", "brand-guidelines.md", "case-studies.md", "faq.md")
REFERENCE = "playbooks/department-system-runtime-reference.md"
PHASE_SECTIONS = {
    "dispatch": "messages", "delivery": "delivery", "acceptance": "acceptance",
    "production": "production", "recovery": "recovery", "finish": "finish",
    "daily": "daily", "maintenance": "maintenance",
}
EXCEPTIONS = {
    "target_not_loaded": "target-state", "delivery_unconfirmed": "notice-recovery",
    "source_binding_error": "recovery", "interrupted": "recovery",
    "authorization_changed": "authority-change",
}


def _file(root, rel):
    if (not isinstance(rel, str) or not rel or "\\" in rel
            or PurePosixPath(rel).is_absolute() or ".." in PurePosixPath(rel).parts):
        raise ValueError("project-relative rule source required")
    path = root / rel
    if path.is_symlink() or any(p.is_symlink() for p in path.parents if p != root.parent):
        raise ValueError("symlink rule source blocked")
    if root not in path.resolve().parents:
        raise ValueError("rule source outside project")
    return path


def _pin(root, rel):
    raw = _file(root, rel).read_bytes()
    return {"path": rel, "sha256": hashlib.sha256(raw).hexdigest(), "size": len(raw)}


def _known(root, department, path):
    if not path:
        return {}, set()
    value = json.loads(_file(root, path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("previous rule context object required")
    value = value.get("rule_context", value)
    if (not isinstance(value, dict) or value.get("schema") != SCHEMA
            or value.get("project_root") != str(root) or value.get("department") != department):
        raise ValueError("previous rule context belongs to another project or role")
    sources = value.get("read_receipt_sources", value.get("sources", []))
    if not isinstance(sources, list):
        raise ValueError("previous rule source list required")
    result = {}
    for item in sources:
        if (not isinstance(item, dict) or set(item) != {"path", "sha256", "size"}
                or not isinstance(item["sha256"], str) or len(item["sha256"]) != 64
                or any(c not in "0123456789abcdef" for c in item["sha256"])
                or type(item["size"]) is not int or item["size"] < 0):
            raise ValueError("invalid previous instruction source pin")
        _file(root, item["path"])
        if item["path"] in result:
            raise ValueError("duplicate previous instruction source")
        result[item["path"]] = item
    sections = value.get("read_sections", value.get("reference_sections", []))
    allowed = {REFERENCE + "#" + section for section in {*PHASE_SECTIONS.values(), *EXCEPTIONS.values()}}
    if not isinstance(sections, list) or any(section not in allowed for section in sections):
        raise ValueError("invalid previous reference sections")
    return result, set(sections)


def build(root, department, skill, *, phase="startup", work_type="general",
          known_rules="", triggers=()):
    root = Path(root).resolve()
    if phase not in PHASES or work_type not in WORK_TYPES:
        raise ValueError("known rule phase and work type required")
    if not isinstance(triggers, (list, tuple)) or any(x not in EXCEPTIONS for x in triggers):
        raise ValueError("known exceptional condition required")
    previous, previous_sections = _known(root, department, known_rules)
    base = ["AGENTS.md", "playbooks/department-system-current.md", skill]
    optional = ["README.md"] if phase == "startup" else []
    if phase == "startup" or work_type not in {"general", "system"}:
        optional.extend(FACTS)
    if phase in {"startup", "dispatch", "acceptance", "production"}:
        optional.extend(["data/task-contract.json", "data/department-registry.json",
                         "data/action-policy.json", "data/department-routing-rules.json",
                         "data/delegation-policy.json"])
    sources = [_pin(root, rel) for rel in dict.fromkeys(base)]
    missing = []
    for rel in dict.fromkeys(optional):
        if rel in base:
            continue
        path = _file(root, rel)
        if path.is_file():
            sources.append(_pin(root, rel))
        else:
            missing.append(rel)
    sections = list(dict.fromkeys([*([PHASE_SECTIONS[phase]] if phase in PHASE_SECTIONS else []),
                                  *(EXCEPTIONS[x] for x in triggers)]))
    reference = _file(root, REFERENCE)
    if sections and reference.is_file():
        sources.append(_pin(root, REFERENCE))
    elif sections:
        missing.append(REFERENCE)
    changed = [item for item in sources if previous.get(item["path"]) != item]
    unchanged = [item["path"] for item in sources if previous.get(item["path"]) == item]
    ref_pin = next((item for item in sources if item["path"] == REFERENCE), None)
    if ref_pin and previous.get(REFERENCE) != ref_pin:
        previous_sections = set()
    current_sections = [REFERENCE + "#" + section for section in sections]
    new_sections = [section for section in current_sections if section not in previous_sections]
    if ref_pin and new_sections and ref_pin not in changed:
        changed.append(ref_pin)
        unchanged.remove(REFERENCE)
    receipt_sources = {**previous, **{item["path"]: item for item in sources}}
    return {
        "schema": SCHEMA, "model": MODEL, "project_root": str(root),
        "department": department, "phase": phase, "work_type": work_type,
        "sources": sources, "sources_to_read": changed, "sources_unchanged": unchanged,
        "optional_sources_missing": missing,
        "reference_sections": current_sections, "reference_sections_to_read": new_sections,
        "read_sections": sorted(previous_sections.union(current_sections)),
        "read_receipt_sources": list(receipt_sources.values()),
        "triggered_exceptions": list(dict.fromkeys(triggers)),
        "normal_next_step": "read_changed_current_instructions_then_continue_assignment"
            if changed else "continue_current_assignment",
        "constraints_are_actions": False, "historical_discussion_is_instruction": False,
        "instruction_read_reuse_only": True, "cached_permissions": False,
        "live_assignment_and_result_checks_required": True,
        "external_permission_issued": False, "writes_performed": False,
    }


def reference_index(entry, *, details=False):
    """Current freshness is not promotion of a task anecdote to a standing rule."""
    if details:
        result = {k: v for k, v in entry.items() if k != "next_action"}
    else:
        result = {k: v for k, v in entry.items()
                  if k in {"lesson_id", "source_ref", "freshness_status", "status"}}
    result.update(record_kind="knowledge_reference", executable_instruction=False,
                  grants_execution_authority=False)
    return result


def normalize_automation_prompt(text, department):
    """Replace only known duplicated common preambles; preserve business scope."""
    if not isinstance(text, str) or not isinstance(department, str) or not department:
        raise ValueError("exact automation text and registered department required")
    header = ("运行入口：按本项目 playbooks/department-system-current.md 的读取时机执行。"
              "先运行 department-learning-effective --department " + department
              + " --phase daily，恢复实际当前指派及新鲜工作边界；已读未变规则复用，历史经验按需读取。"
              "仅在匹配动作或异常发生时查运行参考。以下为本自动任务的专业范围与原排程边界。")
    paragraphs = text.strip().split("\n\n")
    if paragraphs and paragraphs[0].startswith("运行入口：按本项目 playbooks/department-system-current.md"):
        paragraphs.pop(0)
    if paragraphs and paragraphs[0].startswith("先读取本项目唯一共同规则 playbooks/department-system-current.md"):
        paragraphs.pop(0)
    if paragraphs and paragraphs[0].startswith("现行交付接续：完整目标或完整业务批次结束才一次交付；"):
        paragraphs.pop(0)
    for index, paragraph in enumerate(paragraphs):
        if paragraph.startswith("启动先读唯一共同规则playbooks/department-system-current.md"):
            _, separator, remainder = paragraph.partition("。")
            if separator:
                paragraphs[index] = ("启动和续办使用上方阶段入口；按本次任务读取专业方法、原任务CURRENT及唯一主账。"
                                     + remainder)
    return header + ("\n\n" + "\n\n".join(paragraphs) if paragraphs else "")
