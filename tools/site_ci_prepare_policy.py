"""Exact, pre-publication Git/PR/CI guard. Never authorizes main or a deploy."""
from __future__ import annotations

import datetime as dt
import re
from pathlib import Path
from typing import Any

SITE_REPOSITORY = "<WEBSITE_PROJECT_ROOT>"
GITHUB_REPOSITORY = "wangchaozhuanyong/zhuangxiuwangzhan"


def evaluate_context(request: dict[str, Any], binding: dict[str, Any],
                     observed: dict[str, Any], now: dt.datetime) -> list[str]:
    """Validate already hashed, independently reviewed exact context; fail closed."""
    reasons: list[str] = []
    code = request.get("code_identity", {})
    repo = request.get("repository", {})
    if (repo.get("absolute_path") != SITE_REPOSITORY
            or repo.get("github_repository") != GITHUB_REPOSITORY
            or repo.get("remote_name") != "origin" or repo.get("default_branch") != "main"
            or request.get("original_code_risk_level") != "R2"):
        reasons.append("ci_prepare_repository_or_risk_invalid")
    if any(code.get(k) != binding.get(k) for k in
           ("head_sha", "base_sha", "proposed_remote_ref", "worktree", "changed_files")):
        reasons.append("ci_prepare_frozen_code_identity_mismatch")
    ref = str(code.get("proposed_remote_ref") or "")
    head = str(code.get("head_sha") or "")
    if (not re.fullmatch(r"refs/heads/fix/[a-z0-9][a-z0-9/-]{0,150}", ref)
            or ".." in ref or "//" in ref or ref.endswith("/")
            or not re.fullmatch(r"[0-9a-f]{40}", head)):
        reasons.append("ci_prepare_feature_ref_or_head_invalid")
    tree = Path(str(code.get("worktree") or "/"))
    if not tree.is_relative_to(Path(SITE_REPOSITORY) / ".worktrees") or ".." in tree.parts:
        reasons.append("ci_prepare_worktree_out_of_scope")
    commands = [x for x in request.get("proposed_operations_not_executed", [])
                if isinstance(x, dict) and "command_argv" in x]
    if any(command.get("cwd") != code.get("worktree") for command in commands):
        reasons.append("ci_prepare_command_cwd_must_match_frozen_worktree")
    # An empty expected remote value is an atomic create-only lease.
    # A normal push can update a ref created between observation and execution.
    # Do not allow tracking-ref/default leases, generic --force, or other refs.
    expected_push = ["git", "push", f"--force-with-lease={ref}:",
                     "origin", f"{head}:{ref}"]
    if len(commands) != 2 or commands[0].get("command_argv") != expected_push:
        reasons.append("ci_prepare_push_requires_exact_absent_ref_lease")
    else:
        pr = commands[1].get("command_argv", [])
        expected_prefix = ["gh", "pr", "create", "-R", GITHUB_REPOSITORY,
                           "--base", "main", "--head", ref.removeprefix("refs/heads/"),
                           "--draft", "--title"]
        if (pr[:len(expected_prefix)] != expected_prefix or len(pr) != 14
                or pr[12] != "--body-file" or not isinstance(pr[13], str)
                or pr[13] != binding.get("draft_pr_body_absolute_path")):
            reasons.append("ci_prepare_draft_pr_not_exact")
    try:
        seen = dt.datetime.fromisoformat(str(observed.get("observed_at") or "").replace("Z", "+00:00"))
        if seen.tzinfo is None or not 0 <= (now - seen).total_seconds() <= 3600:
            raise ValueError("stale")
    except (ValueError, TypeError):
        reasons.append("ci_prepare_live_repository_hosting_evidence_stale")
    if (observed.get("repository") != GITHUB_REPOSITORY
            or observed.get("head_sha") != head
            or observed.get("main_sha") != code.get("base_sha")
            or observed.get("proposed_remote_ref") != ref
            or observed.get("worktree_clean") is not True
            or observed.get("remote_ref_state") != "ABSENT"
            or observed.get("matching_pr_count") != 0
            or observed.get("changed_files") != code.get("changed_files")):
        reasons.append("ci_prepare_fresh_source_ref_or_pr_state_invalid")
    hosting = observed.get("hosting", {})
    if (hosting.get("site") != "flashcast.com.my" or not hosting.get("project_id")
            or not hosting.get("lawful_keeper") or not hosting.get("redacted_source_path")
            or hosting.get("source_repository") != GITHUB_REPOSITORY
            or hosting.get("source_type") not in {"git", "direct_upload"}
            or hosting.get("production_branch") != "main"
            or hosting.get("feature_ref_can_publish_production") is not False
            or hosting.get("preview_behavior") not in {"disabled", "existing_authorized_preview"}
            or hosting.get("settings_changed") is not False):
        reasons.append("ci_prepare_lawful_hosting_branch_evidence_required")
    if observed.get("main_required_check") != "furniture-page-pr-checks":
        reasons.append("ci_prepare_required_check_identity_invalid")
    return reasons


HOSTING_FACT_FIELDS = (
    "site", "project_id", "lawful_keeper", "source_repository", "source_type",
    "production_branch", "feature_ref_can_publish_production", "preview_behavior",
    "settings_changed",
)


def _source_pointer(document: Any, pointer: Any) -> Any:
    """Read an explicit JSON Pointer; no fuzzy search or inferred source values."""
    if not isinstance(pointer, str) or not pointer.startswith("/"):
        raise ValueError("source fact pointer required")
    value = document
    for token in pointer[1:].split("/"):
        if re.search(r"~(?![01])", token):
            raise ValueError("invalid pointer escape")
        token = token.replace("~1", "/").replace("~0", "~")
        if isinstance(value, dict):
            value = value[token]
        elif isinstance(value, list) and re.fullmatch(r"0|[1-9][0-9]*", token):
            value = value[int(token)]
        else:
            raise ValueError("source fact not addressable")
    return value


def hosting_source_reasons(hosting: dict[str, Any], source: Any,
                           now: dt.datetime) -> list[str]:
    """Compare each normalized fact to an explicit location in hashed evidence."""
    try:
        locators = hosting.get("source_fact_locators", {})
        for field in HOSTING_FACT_FIELDS:
            actual = _source_pointer(source, locators.get(field))
            expected = hosting.get(field)
            if type(actual) is not type(expected) or actual != expected:
                return ["ci_prepare_hosting_source_projection_mismatch"]
        timestamp = _source_pointer(source, hosting.get("source_observed_at_locator"))
        seen = dt.datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
        if seen.tzinfo is None or not 0 <= (now - seen).total_seconds() <= 3600:
            return ["ci_prepare_hosting_original_source_stale"]
        return []
    except (KeyError, IndexError, ValueError, TypeError, AttributeError):
        return ["ci_prepare_hosting_source_fact_locators_required"]


def evaluate(root: Path, workflow: Any, policy: dict[str, Any], *, task_id: str,
             department: str, action_id: str, scope: str, payload_sha256: str
             ) -> tuple[list[str], dict[str, Any]]:
    """Read native receipts and frozen bytes; no subprocess, network, or writes."""
    rules = policy.get("action_classes", {}).get("site_ci_prepare", {})
    binding = next((x for x in rules.get("exact_requests", []) if all(
        x.get(k) == v for k, v in {"task_id": task_id, "department": department,
                                  "action_id": action_id, "scope": scope}.items())), {})
    reasons: list[str] = []
    if department != "content-organic-website" or not binding:
        return ["ci_prepare_exact_registered_executor_and_request_required"], {}
    try:
        registry = workflow.department_registry(root)
        fixed = registry[department]["chat_binding"]
        if (fixed.get("project_id") != policy.get("routing_policy", {}).get("source_project_id")
                or Path(str(fixed.get("cwd") or "/")).resolve() != root.resolve()
                or not workflow._chat_binding_healthy(fixed, verification_ttl_hours=26)):
            reasons.append("ci_prepare_fixed_executor_identity_or_health_invalid")
        frozen = workflow.file_digest(root, binding["request_path"])
        if frozen["sha256"] != binding["request_sha256"] or payload_sha256 != frozen["sha256"]:
            return ["ci_prepare_request_payload_hash_mismatch"], {}
        request = workflow.read_json(root / binding["request_path"])
        if request.get("task_id") != task_id or request.get("candidate_version") != binding.get("candidate_version"):
            reasons.append("ci_prepare_request_task_version_mismatch")
        observed_ref = binding.get("current_observation", {})
        observation_digest = workflow.file_digest(root, observed_ref["path"])
        if observation_digest["sha256"] != observed_ref["sha256"]:
            reasons.append("ci_prepare_current_observation_hash_mismatch")
        observed = workflow.read_json(root / observed_ref["path"])
        if not observed.get("hosting", {}).get("redacted_source_path"):
            reasons.append("ci_prepare_hosting_source_missing")
        else:
            source = observed["hosting"]
            if workflow.file_digest(root, source["redacted_source_path"])["sha256"] != source.get("redacted_source_sha256"):
                reasons.append("ci_prepare_hosting_source_hash_mismatch")
            original = workflow.read_json(root / source["redacted_source_path"])
            reasons += hosting_source_reasons(source, original, dt.datetime.now(dt.timezone.utc))
        reasons += evaluate_context(request, binding, observed, dt.datetime.now(dt.timezone.utc))
        receipts, invalid = workflow._validate_receipt_chain(root, task_id)
        if invalid:
            reasons.append("ci_prepare_native_receipt_chain_invalid")
        local_ref = request.get("source_qa", {}).get("ref", {})
        local_digest = workflow.file_digest(root, local_ref["path"])
        local_qa = workflow.read_json(root / local_ref["path"])
        if (local_digest["sha256"] != local_ref.get("sha256")
                or local_qa.get("candidate_version") != request.get("original_code_candidate_version")
                or local_qa.get("risk_level") != "R2"
                or local_qa.get("qa_result") != "PASS_LOCAL_CHECKS_HOLD_RELEASE_SAME_HEAD_REQUIRED_CI"
                or not any(x.get("receipt_type") == "qa_verdict" and x.get("department") == "qa"
                           and local_digest in x.get("evidence", []) for x in receipts)):
            reasons.append("ci_prepare_exact_original_local_qa_required")
        stages = [x for x in receipts if x.get("receipt_type") == "qa_verdict"
                  and x.get("department") == "qa" and x.get("action_id") == action_id
                  and x.get("scope") == scope]
        stage = stages[-1] if stages else {}
        valid_stage = False
        for evidence in stage.get("evidence", []):
            path = str(evidence.get("path") or "")
            if not path.startswith("logs/department-outbox/") or not path.endswith(".json"):
                continue
            digest = workflow.file_digest(root, path)
            qa = workflow.read_json(root / path)
            if (digest == evidence and qa.get("task_id") == task_id
                    and qa.get("candidate_version") == binding["candidate_version"]
                    and qa.get("qa_result") == "PASS_EXACT_GIT_PR_CI_PREPARATION_ONLY"
                    and qa.get("risk_level") == "R2" and qa.get("production_release_eligible") is False
                    and qa.get("candidate_sha256") == frozen["sha256"]
                    and qa.get("observation_sha256") == observation_digest["sha256"]
                    and qa.get("action_class") == "site_ci_preparation_candidate"
                    and qa.get("action_id") == action_id and qa.get("scope") == scope):
                valid_stage = True
        fixed_qa = workflow.department_registry(root)["qa"]["chat_binding"]["task_id"]
        if (not valid_stage or stage.get("verdict") != "pass"
                or stage.get("action_class") != "site_ci_preparation_candidate"
                or stage.get("chat_task_id") != fixed_qa):
            reasons.append("ci_prepare_current_exact_independent_stage_qa_required")
        author = rules.get("owner_authorization", {})
        if (author.get("status") != "active" or author.get("department") != department
                or author.get("source_repository") != SITE_REPOSITORY
                or author.get("action_classes") != ["site_ci_prepare"]
                or scope not in author.get("allowed_scopes", []) or not author.get("source_message_ref")):
            reasons.append("ci_prepare_exact_prior_owner_stage_authorization_required")
        return reasons, author
    except (KeyError, OSError, ValueError, workflow.WorkflowError):
        return ["ci_prepare_missing_or_invalid_frozen_evidence"], {}
