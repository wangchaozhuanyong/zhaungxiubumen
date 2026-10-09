"""Exact Codex inventory handling. Pinned is a location, not an authorization."""
from pathlib import Path

CODE_ROOTS = {
    "<WEBSITE_PROJECT_ROOT>",
    "<PROJECT_ROOT>",
}


def sections(live):
    """Normalize the actual Codex sectionId carrier; conflicting aliases fail closed."""
    from workflow_control import WorkflowError
    if not isinstance(live, dict) or not isinstance(live.get("sections"), list):
        raise WorkflowError("native section inventory required")
    rows, seen = [], set()
    for value in live["sections"]:
        if not isinstance(value, dict):
            raise WorkflowError("native section must be object")
        sid, old = value.get("sectionId"), value.get("id")
        if sid is not None and old is not None and sid != old:
            raise WorkflowError("conflicting native section aliases")
        key = sid if sid is not None else old
        members = value.get("itemKeys")
        if (not isinstance(key, str) or not key or key in seen
                or not isinstance(value.get("name"), str)
                or not isinstance(members, list)
                or any(not isinstance(item, str) for item in members)
                or len(set(members)) != len(members)):
            raise WorkflowError("native section identity ambiguous")
        seen.add(key)
        rows.append({**value, "id": key, "sectionId": key})
    return rows


def fixed_binding(root, department, live):
    """Verify an ordinary thread or explicitly registered associated project."""
    import workflow_control as w
    entry = w.department_registry(root).get(department, {})
    bind = entry.get("chat_binding", {})
    matches = [row for row in threads(live) if row.get("id") == bind.get("task_id")]
    member = ("codex:project:" + str(bind.get("project_id"))
              if entry.get("relationship") == "associated_code_department"
              else "codex:thread:local:" + str(bind.get("task_id")))
    groups = [row for row in sections(live) if member in row["itemKeys"]]
    if (len(matches) != 1 or len(groups) != 1
            or groups[0]["sectionId"] != bind.get("sidebar_section_id")
            or (entry.get("relationship") != "associated_code_department"
                and groups[0].get("name") != ("装修公司总控" if department == "operations" else "装修公司部门"))
            or any(matches[0].get(a) != bind.get(b) for a, b in
                   (("projectId", "project_id"), ("title", "title"), ("cwd", "cwd")))):
        raise w.WorkflowError("exact native fixed identity and registered section required")
    return matches[0]


def threads(live):
    from workflow_control import WorkflowError
    if not isinstance(live, dict):
        raise WorkflowError("native inventory object required")
    rows = []
    for key in ("pinnedThreads", "threads"):
        part = live.get(key, [])
        if not isinstance(part, list) or any(not isinstance(row, dict) for row in part):
            raise WorkflowError("native thread inventory invalid")
        rows.extend(part)
    ids = [row.get("id") for row in rows]
    if any(not isinstance(x, str) or not x for x in ids) or len(set(ids)) != len(ids):
        raise WorkflowError("native thread inventory ambiguous")
    return rows


def validate_code_source(value, *, legacy_website_only=False):
    from workflow_control import WorkflowError
    if value is None and legacy_website_only:
        return "<WEBSITE_PROJECT_ROOT>"
    if not isinstance(value, str) or str(Path(value).resolve()) not in CODE_ROOTS:
        raise WorkflowError("only two human-designated exact code roots allowed")
    return str(Path(value).resolve())
