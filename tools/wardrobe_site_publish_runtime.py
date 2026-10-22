"""One original wardrobe R3 site release identity, without a platform permit.

The frozen W goal declared the CMS write but omitted the preceding Edge release.
This exact source-backed compatibility route does not rewrite that goal or grant
the website's separate, short-lived environment/run approval.
"""

import datetime as dt
import hashlib
import json
import re
import subprocess
from pathlib import Path

import workflow_control as w


TASK = "fc-20261014-builtin-wardrobe-layout-cms-publication-v1"
AUTH = ("logs/handoffs/2026-10-14-builtin-wardrobe-registration-v1/"
        "system-development-candidate-v1/selected-original-human-authority.json")
AUTH_SHA = "71d5180f60975924f5f2af0b8e558d753b693dc8557c784c2acd689c61b495bf"
GOAL_SHA = "3a8ba4375bdae2e7bce3f589c3fe49d7c6aba00a0ab9a0d19b6fe04d166aa99b"
ORIGINAL_REVIEW = ("logs/handoffs/2026-10-15-real-delivery-followthrough-v1/"
                   "assistant2-independent-review-v1/"
                   "A2-independent-builtin-wardrobe-channel-code-review-bd4eac47-v1.json")
ORIGINAL_REVIEW_SHA = "d2d53165fb0dc2a188d7c173610cda0c35265cd68fda29c783e32a33d2fb9d5b"
ORIGINAL_INDEX_REL = ("reports/builtin-wardrobe-protected-channel-20261015-v1/"
                      "release-v2/frozen-result-index.json")
ORIGINAL_INDEX_SHA = "854fe35aa810d19331c5652f077a9716ce0b41df257a55feadfeaff34639f63a"
SOURCE_THREAD = "example-native-0bec6d516b372cb9"
SOURCE_MESSAGE = "example-native-8b2eedaf7db63344"
WEB = "designated-development"
WEB_THREAD = "example-native-25e4a2ebb5d53084"
WEB_TITLE = "FLASH CAST｜专用开发部｜网站与部门系统"
WEB_CWD = "<WEBSITE_PROJECT_ROOT>"
SELF_CHECK_MARKER = "FLASHCAST_WARDROBE_R3_SELFCHECK_READY "
A2 = "operations-assistant-2"
OBJECT = "rbsnyexjifounogswrjp/content-publish"
SCOPE = "company.example:edge:rbsnyexjifounogswrjp:content-publish"
REPOSITORY = "wangchaozhuanyong/zhuangxiuwangzhan"
WEBSITE_ROOT = Path("<WEBSITE_PROJECT_ROOT>")
CMS_ACTION = {"action_class": "cms_write", "action_id": "publish-builtin-wardrobe-layout-20261014-v1",
              "department": "publishing",
              "scope": "company.example:services/b401a610-a4dc-4a0b-a7e0-efcac6c81d71:content_zh"}


def applies(task_id, action_class):
    return task_id == TASK and action_class == "site_publish"


def action_for(sha):
    if not re.fullmatch(r"[0-9a-f]{40}", str(sha)):
        raise w.WorkflowError("current reviewed main SHA required")
    return "publish-builtin-wardrobe-edge-r3-" + sha[:12]


def _pinned_file(root, pin, *, website=False):
    if not isinstance(pin, dict) or set(pin) != {"path", "sha256", "size"}:
        raise w.WorkflowError("exact evidence path, SHA and size required")
    path = Path(pin["path"])
    if website:
        path = path.resolve()
        if not path.is_relative_to(WEBSITE_ROOT.resolve()):
            raise w.WorkflowError("website self-check evidence outside original repository")
    else:
        path = w.safe_path(root, str(path))
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise w.WorkflowError("exact source-backed evidence file missing") from error
    if not raw or hashlib.sha256(raw).hexdigest() != pin["sha256"] or len(raw) != pin["size"]:
        raise w.WorkflowError("exact source-backed evidence bytes changed")
    return path


def _remote_main():
    try:
        origin = subprocess.run(["git", "remote", "get-url", "origin"], cwd=WEBSITE_ROOT,
                                capture_output=True, text=True, timeout=5, check=True).stdout.strip()
    except (OSError, subprocess.SubprocessError) as error:
        raise w.WorkflowError("current original website repository unavailable") from error
    if origin not in {"git@github.com:wangchaozhuanyong/zhuangxiuwangzhan.git",
                      "https://github.com/wangchaozhuanyong/zhuangxiuwangzhan.git"}:
        raise w.WorkflowError("original website repository remote required")
    try:
        result = subprocess.run(["git", "ls-remote", "origin", "refs/heads/main"],
                                cwd=WEBSITE_ROOT, capture_output=True, text=True, timeout=12, check=True)
    except (OSError, subprocess.SubprocessError) as error:
        raise w.WorkflowError("current remote main source unavailable") from error
    fields = result.stdout.strip().split()
    if len(fields) != 2 or fields[1] != "refs/heads/main":
        raise w.WorkflowError("one current remote main source required")
    return fields[0]


def _reviewed_files(sha):
    """Check the original 13 reviewed bytes in the exact current commit."""
    raw = (WEBSITE_ROOT / ORIGINAL_INDEX_REL).read_bytes()
    if hashlib.sha256(raw).hexdigest() != ORIGINAL_INDEX_SHA:
        raise w.WorkflowError("original 13-file reviewed source index changed")
    index = json.loads(raw)
    rows = index.get("source_files", [])
    if (index.get("task_id") != TASK or len(rows) != 13
            or len({row.get("relative_path") for row in rows}) != 13):
        raise w.WorkflowError("one original reviewed 13-file source index required")
    for row in rows:
        path = str(row.get("relative_path") or "")
        if (not path or path.startswith("/") or ".." in Path(path).parts
                or not re.fullmatch(r"[0-9a-f]{64}", str(row.get("sha256") or ""))):
            raise w.WorkflowError("safe exact reviewed source path and hash required")
        try:
            item = subprocess.run(["git", "show", sha + ":" + path], cwd=WEBSITE_ROOT,
                                  capture_output=True, timeout=8, check=True)
        except (OSError, subprocess.SubprocessError) as error:
            raise w.WorkflowError("current reviewed source commit unavailable locally") from error
        if hashlib.sha256(item.stdout).hexdigest() != row["sha256"]:
            raise w.WorkflowError("current main changed an original reviewed wardrobe source file")
    return True


def _native_web_self_check(root, evidence, sha, action_id):
    """Bind the dated self-check bytes to one actual original WEB chat reply."""
    source = evidence.get("native_web_source")
    if not isinstance(source, dict) or set(source) != {"page", "turn_id", "message_id"}:
        raise w.WorkflowError("actual original WEB native self-check source required")
    from goal_delivery_runtime import _native_document
    from qa_review_plan import _review_native_containers
    try:
        page = _native_document(root, source["page"])
        _review_native_containers(page)
    except (w.WorkflowError, ValueError, TypeError, KeyError, OSError) as error:
        raise w.WorkflowError("successful complete original WEB native source required") from error
    thread = page.get("thread", {})
    if (any(thread.get(key) != value for key, value in {
            "id": WEB_THREAD, "title": WEB_TITLE, "cwd": WEB_CWD}.items())
            or page.get("errors") or page.get("truncated") is True):
        raise w.WorkflowError("original WEB fixed chat identity and complete native source required")
    matches = [(turn, item) for turn in page.get("turns", [])
               for item in turn.get("items", [])
               if turn.get("id") == source["turn_id"]
               and item.get("id") == source["message_id"]
               and item.get("type") == "agentMessage"]
    if len(matches) != 1 or matches[0][0].get("error") or matches[0][0].get("status") not in {"inProgress", "completed"}:
        raise w.WorkflowError("one successful original WEB native self-check declaration required")
    try:
        _review_native_containers(matches[0][0])
        _review_native_containers(matches[0][1])
    except ValueError as error:
        raise w.WorkflowError("successful original WEB native turn and message required") from error
    if (matches[0][0].get("truncated") is True or matches[0][1].get("truncated") is True):
        raise w.WorkflowError("complete original WEB native self-check required")
    lines = [line[len(SELF_CHECK_MARKER):] for line in matches[0][1].get("text", "").splitlines()
             if line.startswith(SELF_CHECK_MARKER)]
    if len(lines) != 1:
        raise w.WorkflowError("one original WEB frozen self-check declaration required")
    try:
        declared = json.loads(lines[0])
    except ValueError as error:
        raise w.WorkflowError("valid original WEB self-check declaration required") from error
    expected = {"task_id": TASK, "department": WEB, "action_id": action_id,
                "scope": SCOPE, "object": OBJECT, "expected_main_sha": sha,
                "checked_at": evidence["checked_at"],
                "self_check": evidence["self_check"],
                "facts": evidence["facts"], "backup": evidence["backup"],
                "rollback": evidence["rollback"],
                "reviewed_source": evidence["reviewed_source"]}
    if any(declared.get(key) != value for key, value in expected.items()):
        raise w.WorkflowError("original WEB native self-check bytes and source differ")
    return source


def validate(root, snapshot, action_id, scope, source_thread_id, source_message_ref,
             evidence_path, *, current_sha=None):
    """Read every authority and current source prerequisite before a ledger write."""
    root = Path(root).resolve()
    goal = snapshot.get("goal_delivery", {})
    authority = goal.get("authorization_pin", {})
    if (snapshot.get("task_id") != TASK or snapshot.get("current_state") not in
            {"dispatched", "acknowledged", "evidence_received", "qa_passed"}
            or goal.get("primary_owner") != "paid-growth-data"
            or goal.get("source_mode") != "owner_direct"
            or goal.get("responsible_assistant") != A2
            or goal.get("producer_departments") != ["paid-growth-data", "publishing"]
            or goal.get("required_execution_actions") != [CMS_ACTION]
            or goal.get("authorized_scope") != [CMS_ACTION["scope"]]
            or authority.get("path") != AUTH or authority.get("sha256") != AUTH_SHA
            or w.file_digest(root, AUTH) != authority
            or snapshot.get("goal_contract", {}).get("sha256") != GOAL_SHA
            or w.file_digest(root, snapshot["goal_contract"]["path"]) != snapshot["goal_contract"]
            or source_thread_id != SOURCE_THREAD or source_message_ref != SOURCE_MESSAGE
            or goal.get("human_authorization", {}).get("source_thread_id") != SOURCE_THREAD
            or goal.get("human_authorization", {}).get("message_id") != SOURCE_MESSAGE
            or goal.get("human_authorization", {}).get("executor") != "paid-growth-data"
            or goal.get("human_authorization", {}).get("scope") != CMS_ACTION["scope"]
            or scope != SCOPE):
        raise w.WorkflowError("original W goal, owner, A2 and human source required")
    human = w.read_json(root / AUTH)
    if (human.get("source_thread_id") != SOURCE_THREAD
            or human.get("message", {}).get("id") != SOURCE_MESSAGE
            or human.get("registration_authorization", {}).get("id") != "example-native-052c3570db5757e7"
            or human.get("no_new_permissions") is not True):
        raise w.WorkflowError("original two-page human authorization changed")
    evidence = w.read_json(w.safe_path(root, evidence_path))
    sha = str(evidence.get("expected_main_sha") or "")
    if (evidence.get("schema") != "wardrobe-site-publish-source-preflight/v1"
            or evidence.get("task_id") != TASK or evidence.get("department") != WEB
            or evidence.get("reviewer") != A2 or evidence.get("object") != OBJECT
            or evidence.get("repository") != REPOSITORY
            or evidence.get("action_id") != action_id or action_id != action_for(sha)
            or evidence.get("action_class") != "site_publish"
            or evidence.get("scope") != SCOPE
            or evidence.get("status") != "PASS"
            or evidence.get("risk_level") != "R3"
            or evidence.get("production_write_allowed") is not False
            or evidence.get("external_permission_issued") is not False):
        raise w.WorkflowError("one exact original WEB R3 self-check request required")
    try:
        checked_at = dt.datetime.fromisoformat(evidence["checked_at"])
        age = dt.datetime.now(dt.timezone.utc) - checked_at.astimezone(dt.timezone.utc)
    except (KeyError, ValueError, TypeError):
        raise w.WorkflowError("current dated WEB self-check required")
    if not dt.timedelta(0) <= age <= dt.timedelta(hours=24):
        raise w.WorkflowError("stale or future WEB self-check")
    for name in ("facts", "self_check", "backup", "rollback", "reviewed_source"):
        _pinned_file(root, evidence.get(name), website=True)
    try:
        reviewed = json.loads(_pinned_file(root, evidence["reviewed_source"], website=True).read_text())
    except (KeyError, ValueError, OSError) as error:
        raise w.WorkflowError("valid reviewed source binding JSON required") from error
    original = reviewed.get("original_review", {})
    if (reviewed.get("schema") != "wardrobe-current-reviewed-site-source/v1"
            or reviewed.get("task_id") != TASK or reviewed.get("object") != OBJECT
            or reviewed.get("expected_main_sha") != sha
            or reviewed.get("reviewed_wardrobe_files_unchanged") is not True
            or reviewed.get("r3_guard_checked") is not True
            or original.get("path") != ORIGINAL_REVIEW
            or original.get("sha256") != ORIGINAL_REVIEW_SHA
            or w.file_digest(root, ORIGINAL_REVIEW) != original):
        raise w.WorkflowError("current source must retain exact original independent review")
    review = w.read_json(root / ORIGINAL_REVIEW)
    if (review.get("result") != "NO_ACTIONABLE_CODE_FINDING_IN_BOUNDED_COMMIT_DIFF"
            or review.get("formal_source_intake_or_final_acceptance") is not False):
        raise w.WorkflowError("original review conclusion changed")
    try:
        self_check = json.loads(_pinned_file(root, evidence["self_check"], website=True).read_text())
    except (KeyError, ValueError, OSError) as error:
        raise w.WorkflowError("valid exact WEB self-check JSON required") from error
    _native_web_self_check(root, evidence, sha, action_id)
    try:
        inner_checked = dt.datetime.fromisoformat(self_check["checked_at"])
        if inner_checked.tzinfo is None or checked_at.tzinfo is None:
            raise ValueError("timezone required")
        inner_utc = inner_checked.astimezone(dt.timezone.utc)
        outer_utc = checked_at.astimezone(dt.timezone.utc)
    except (KeyError, ValueError, TypeError) as error:
        raise w.WorkflowError("dated original WEB inner self-check required") from error
    if inner_utc != outer_utc or not dt.timedelta(0) <= dt.datetime.now(dt.timezone.utc)-inner_utc <= dt.timedelta(hours=24):
        raise w.WorkflowError("stale or rewrapped original WEB inner self-check")
    if (self_check.get("status") != "PASS"
            or any(self_check.get(key) != value for key, value in {
                "task_id": TASK, "department": WEB, "action_id": action_id,
                "action_class": "site_publish", "scope": SCOPE,
                "object": OBJECT, "expected_main_sha": sha}.items())
            or self_check.get("r3_guard_pass") is not True
            or self_check.get("backup_ready") is not True
            or self_check.get("rollback_ready") is not True):
        raise w.WorkflowError("exact current R3 guard, backup and rollback self-check required")
    remote = current_sha if current_sha is not None else _remote_main()
    if remote != sha:
        raise w.WorkflowError("reviewed website SHA no longer equals remote main")
    _reviewed_files(sha)
    return {"request": w.file_digest(root, evidence_path), "expected_main_sha": sha,
            "native_web_source": evidence["native_web_source"],
            "authorization_pin": authority, "risk_level": "R3", "department": WEB,
            "object": OBJECT, "scope": SCOPE, "action_id": action_id}


def validate_issued(root, snapshot, approval, action_id, scope):
    if (approval.get("approval_basis") != "original_wardrobe_r3_source_preflight_v1"
            or approval.get("task_id") != TASK or approval.get("action_id") != action_id
            or approval.get("action_class") != "site_publish" or approval.get("scope") != scope
            or approval.get("single_use") is not True
            or approval.get("source_thread_id") != SOURCE_THREAD
            or approval.get("source_message_ref") != SOURCE_MESSAGE):
        raise w.WorkflowError("original wardrobe exact single-use approval required")
    context = validate(root, snapshot, action_id, scope, SOURCE_THREAD, SOURCE_MESSAGE,
                       approval.get("source_preflight", {}).get("path", ""))
    if approval.get("source_preflight") != context["request"]:
        raise w.WorkflowError("issued wardrobe self-check bytes changed")
    return context
