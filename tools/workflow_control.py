#!/usr/bin/env python3
"""Project-local workflow controls for FLASH CAST.

This module deliberately uses only the Python standard library.  It provides
tamper-evident receipts and recoverable local state, but it is not a digital
signature system and it does not intercept Codex tools globally.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import tempfile
import uuid
from contextlib import contextmanager, nullcontext
from pathlib import Path
from typing import Any, Iterator

try:  # macOS/Linux project runtime
    import fcntl
except ImportError:  # pragma: no cover - defensive fallback for non-POSIX hosts
    fcntl = None  # type: ignore[assignment]


WORKFLOW_EVENTS = Path("logs/workflow-events.jsonl")
WORKFLOW_DIR = Path("data/workflows")
RECEIPTS_DIR = Path("logs/receipts")
RESULT_HANDOFF_DIR = Path("logs/result-handoffs")
APPROVAL_LEDGER = Path("logs/approvals/ledger.jsonl")
POLICY_DECISIONS = Path("logs/policy-decisions.jsonl")
ACTION_POLICY = Path("data/action-policy.json")
DELEGATION_POLICY = Path("data/delegation-policy.json")
DELEGATION_DIR = Path("logs/delegations")
DELEGATION_DECISIONS = Path("logs/delegation-decisions.jsonl")
LOCK_FILE = Path("logs/.workflow-control.lock")

RECEIPT_TYPES = {
    "dispatch_sent",
    "dispatch_failed",
    "chat_ack",
    "outbox_received",
    "qa_verdict",
    "execution_result",
    "postcheck",
    "evidence_replacement",
    "evidence_archive",
}
TERMINAL_STATES = {"closed", "failed", "cancelled"}
EXCEPTION_STATES = {"blocked", "blocked_evidence_invalid", "failed", "cancelled"}
EXTERNAL_ACTION_CLASSES = {
    "ads_write",
    "site_publish",
    "site_ci_prepare",
    "cms_write",
    "site_cache_invalidation",
    "google_business_profile_write",
    "crm_write",
    "customer_contact",
    "payment",
    "price_or_contract_commitment",
}
RELEASE_CANDIDATE_ACTION_ROUTES = {
    "site_ci_preparation_candidate": "site_ci_prepare",
    "site_code_candidate": "site_publish",
    "site_code_rework_candidate": "site_publish",
    "cms_content_candidate": "cms_write",
    "site_cache_candidate": "site_cache_invalidation",
    "google_business_profile_candidate": "google_business_profile_write",
    "site_publish": "site_publish",
    "cms_write": "cms_write",
    "site_cache_invalidation": "site_cache_invalidation",
    "google_business_profile_write": "google_business_profile_write",
}
SPECIALIST_ACTION_CLASSES = EXTERNAL_ACTION_CLASSES | {
    "account_read",
    "specialist_delivery",
    "google_business_profile_candidate",
}
ROUTING_ACTION_CLASSES = {
    "thread_message",
    "automation_create",
    "automation_update",
    "cross_project_access",
}
SENSITIVE_MARKERS = (
    "password",
    "passwd",
    "secret",
    "token",
    "cookie",
    "oauth",
    "private-key",
    "private_key",
    "credentials",
    ".pem",
    ".key",
)
TASK_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{2,100}")
SHA256_PATTERN = re.compile(r"[0-9a-fA-F]{64}")
CONTENT_GROWTH_DAILY_PATTERN = re.compile(r"fc-\d{8}-website-growth-daily")
PROMOTION_GAP_CATEGORIES = {
    "demand_capture",
    "trust_evidence",
    "search_geo",
    "content_expansion",
    "earned_distribution",
    "conversion_feedback",
}
ACTIVE_DELEGATION_STATES = {"started", "progress"}
TERMINAL_DELEGATION_STATES = {"completed", "failed", "timed_out", "cancelled"}
DELEGATION_STATES = ACTIVE_DELEGATION_STATES | TERMINAL_DELEGATION_STATES


class WorkflowError(RuntimeError):
    """Expected workflow validation error."""


def utc_timestamp() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_value(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _final_qa_department(root: Path, snapshot: dict[str, Any]) -> str:
    """Legacy/production remains qa; frozen exact R0 plans may select QA2."""
    from qa_review_plan import reviewer_department
    return reviewer_department(root, snapshot)


def validate_task_id(task_id: str) -> str:
    value = str(task_id or "").strip()
    if not TASK_ID_PATTERN.fullmatch(value):
        raise WorkflowError("task_id 只能包含字母、数字、点、下划线和连字符")
    return value


def safe_path(root: Path, value: str | Path) -> Path:
    path = Path(value)
    resolved = path.resolve() if path.is_absolute() else (root / path).resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise WorkflowError(f"路径超出项目目录，已阻止：{value}") from exc
    return resolved


def rel_path(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError as exc:
        raise WorkflowError(f"路径超出项目目录，已阻止：{path}") from exc


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            rows.append(value)
    return rows


def atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    )
    temporary = Path(handle.name)
    try:
        with handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def atomic_write_json(path: Path, payload: Any) -> None:
    atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def append_jsonl_locked(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


@contextmanager
def workflow_lock(root: Path) -> Iterator[None]:
    lock_path = root / LOCK_FILE
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as handle:
        if fcntl is not None:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            if fcntl is not None:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def snapshot_path(root: Path, task_id: str) -> Path:
    return root / WORKFLOW_DIR / f"{validate_task_id(task_id)}.json"


def receipts_path(root: Path, task_id: str) -> Path:
    return root / RECEIPTS_DIR / f"{validate_task_id(task_id)}.jsonl"


def result_handoff_path(root: Path, task_id: str) -> Path:
    return root / RESULT_HANDOFF_DIR / f"{validate_task_id(task_id)}.jsonl"


def delegations_path(root: Path, task_id: str) -> Path:
    return root / DELEGATION_DIR / f"{validate_task_id(task_id)}.jsonl"


def department_registry(root: Path) -> dict[str, dict[str, Any]]:
    registry = read_json(root / "data/department-registry.json")
    departments = {
        str(item.get("id", "")): item
        for item in registry.get("departments", [])
        if isinstance(item, dict) and item.get("id")
    }
    if not departments:
        raise WorkflowError("缺少有效的 data/department-registry.json")
    return departments


def _parse_observed_at(value: object) -> dt.datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        observed = dt.datetime.fromisoformat(raw)
    except ValueError:
        return None
    if observed.tzinfo is None:
        observed = observed.replace(tzinfo=dt.timezone.utc)
    return observed.astimezone(dt.timezone.utc)


def _chat_binding_healthy(
    binding: dict[str, Any], *, verification_ttl_hours: int = 0, now: dt.datetime | None = None
) -> bool:
    """Treat explicit ineligibility, unhealthy replies and stale live proof as failures."""

    if binding.get("status") != "bound_and_visible" or binding.get("dispatch_eligible") is False:
        return False
    reply_health = str(binding.get("reply_health", "legacy_unspecified")).casefold()
    if reply_health.startswith(("unhealthy", "degraded", "failed", "unavailable", "verification_stale")):
        return False
    if verification_ttl_hours > 0:
        health_stamp = binding.get("last_health_check_at")
        if health_stamp is None or health_stamp == "":
            health_stamp = binding.get("last_verified_at")
        observed = _parse_observed_at(health_stamp)
        current = (now or dt.datetime.now(dt.timezone.utc)).astimezone(dt.timezone.utc)
        if observed is None:
            return False
        age = current - observed
        if not dt.timedelta(0) <= age <= dt.timedelta(hours=verification_ttl_hours):
            return False
    return True


def load_delegation_policy(root: Path) -> dict[str, Any]:
    policy = read_json(root / DELEGATION_POLICY)
    if not policy or policy.get("status") != "active":
        raise WorkflowError("data/delegation-policy.json 不存在、无效或未启用")
    return policy


def _latest_delegations(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for row in rows:
        delegation_id = str(row.get("delegation_id", ""))
        if delegation_id:
            latest[delegation_id] = row
    return latest


def _all_latest_delegations(root: Path) -> list[dict[str, Any]]:
    latest: list[dict[str, Any]] = []
    directory = root / DELEGATION_DIR
    if not directory.exists():
        return latest
    for path in sorted(directory.glob("*.jsonl")):
        latest.extend(_latest_delegations(read_jsonl(path)).values())
    return latest


def _delegation_payload_for_hash(event: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in event.items() if key not in {"event_hash", "result"}}


def _validate_delegation_chain(root: Path, task_id: str) -> tuple[list[dict[str, Any]], list[str]]:
    rows = read_jsonl(delegations_path(root, task_id))
    invalid: list[str] = []
    previous = ""
    for index, row in enumerate(rows, start=1):
        if row.get("previous_hash", "") != previous:
            invalid.append(f"delegation_{index}:previous_hash_mismatch")
        calculated = sha256_value(_delegation_payload_for_hash(row))
        if row.get("event_hash") != calculated:
            invalid.append(f"delegation_{index}:event_hash_mismatch")
        for evidence in row.get("evidence", []):
            try:
                current = file_digest(root, str(evidence.get("path", "")))
            except WorkflowError:
                invalid.append(f"delegation_{index}:evidence_missing:{evidence.get('path', '')}")
                continue
            if current.get("sha256") != evidence.get("sha256") or current.get("size") != evidence.get("size"):
                invalid.append(f"delegation_{index}:evidence_changed:{evidence.get('path', '')}")
        previous = str(row.get("event_hash", ""))
    return rows, invalid


def delegation_check(
    root: Path,
    *,
    task_id: str,
    department: str,
    benefit: str,
    work_class: str,
    scope: str,
    parent_thread_id: str,
    parent_project_id: str,
    parent_cwd: str,
    requested_parallelism: int = 1,
    timeout_seconds: int = 0,
    interdependent_work: bool = False,
    overlapping_write_scope: bool = False,
    external_side_effect: bool = False,
) -> tuple[dict[str, Any], list[Path]]:
    """Check whether a fixed department may spawn bounded ephemeral workers."""

    task_id = validate_task_id(task_id)
    if not scope.strip():
        raise WorkflowError("delegation-check 需要非空的有界 scope")
    if any(marker in scope.casefold() for marker in SENSITIVE_MARKERS):
        raise WorkflowError("委派 scope 不得包含凭据或敏感信息标记")
    policy = load_delegation_policy(root)
    registry = department_registry(root)
    snapshot = read_json(snapshot_path(root, task_id))
    limits = policy.get("limits", {}) if isinstance(policy.get("limits"), dict) else {}
    max_global = int(limits.get("max_concurrent_global", 3))
    max_department = int(limits.get("max_concurrent_per_department", 2))
    default_timeout = int(limits.get("default_timeout_seconds", 900))
    max_timeout = int(limits.get("max_timeout_seconds", 1800))
    requested_timeout = timeout_seconds or default_timeout
    reasons: list[str] = []

    item = registry.get(department)
    if not item:
        reasons.append("department_not_registered")
        binding: dict[str, Any] = {}
    else:
        raw_binding = item.get("chat_binding", {})
        binding = raw_binding if isinstance(raw_binding, dict) else {}
    if department == "operations" and work_class == "specialist_internal":
        reasons.append("operations_controller_cannot_delegate_specialist_delivery")
    if benefit not in policy.get("allowed_benefits", []):
        reasons.append("delegation_benefit_not_allowed")
    if work_class not in policy.get("allowed_work_classes", []):
        reasons.append("delegation_work_class_not_allowed")
    if interdependent_work:
        reasons.append("interdependent_work_must_run_sequentially")
    if overlapping_write_scope:
        reasons.append("overlapping_write_scope_must_not_run_in_parallel")
    if external_side_effect or work_class == "external_action":
        reasons.append("external_side_effect_must_not_be_delegated")
    if requested_parallelism < 1:
        reasons.append("requested_parallelism_must_be_positive")
    if requested_parallelism > max_global or requested_parallelism > max_department:
        reasons.append("requested_parallelism_exceeds_limit")
    if requested_timeout < 1 or requested_timeout > max_timeout:
        reasons.append("timeout_seconds_out_of_range")
    if not snapshot:
        reasons.append("workflow_not_found")
    else:
        planned = {str(row.get("department", "")) for row in snapshot.get("departments", [])}
        if department not in planned:
            reasons.append("department_not_in_workflow_plan")
        receipts = read_jsonl(receipts_path(root, task_id))
        if department not in {"operations", "qa"} and not any(
            row.get("receipt_type") == "chat_ack"
            and row.get("department") == department
            and row.get("ack_nonempty")
            for row in receipts
        ):
            reasons.append("fixed_department_chat_ack_required")
        if department == "qa" and snapshot.get("current_state") not in {"evidence_received", "qa_blocked"}:
            reasons.append("qa_delegation_requires_evidence_received")

    if item and not _chat_binding_healthy(binding):
        reasons.append("fixed_department_window_unhealthy")
    expected_project_id = str(binding.get("project_id") or "")
    expected_cwd = str(binding.get("cwd") or "")
    expected_thread_id = str(binding.get("task_id") or "")
    if not parent_thread_id or parent_thread_id != expected_thread_id:
        reasons.append("parent_thread_id_mismatch")
    if not parent_project_id or parent_project_id != expected_project_id:
        reasons.append("blocked_cross_project:parent_project_id_mismatch")
    if not _same_resolved_path(parent_cwd, expected_cwd):
        reasons.append("blocked_cross_project:parent_cwd_mismatch")
    if not binding.get("sidebar_section_id"):
        reasons.append("fixed_department_sidebar_group_unverified")

    active = [row for row in _all_latest_delegations(root) if row.get("status") in ACTIVE_DELEGATION_STATES]
    active_department = [row for row in active if row.get("department") == department]
    if len(active) + requested_parallelism > max_global:
        reasons.append("global_concurrency_capacity_exceeded")
    if len(active_department) + requested_parallelism > max_department:
        reasons.append("department_concurrency_capacity_exceeded")

    decision = {
        "schema_version": "1.0",
        "decision_id": "dlg-pol-" + sha256_value(
            [
                task_id,
                department,
                benefit,
                work_class,
                hashlib.sha256(scope.strip().encode("utf-8")).hexdigest(),
                parent_thread_id,
                parent_project_id,
                parent_cwd,
                requested_parallelism,
                requested_timeout,
                utc_timestamp(),
            ]
        )[:20],
        "status": "allow" if not reasons else "deny",
        "task_id": task_id,
        "department": department,
        "benefit": benefit,
        "work_class": work_class,
        "scope_sha256": hashlib.sha256(scope.strip().encode("utf-8")).hexdigest(),
        "scope_body_stored": False,
        "parent_thread_id": parent_thread_id,
        "parent_project_id": parent_project_id,
        "parent_cwd": parent_cwd,
        "requested_parallelism": requested_parallelism,
        "timeout_seconds": requested_timeout,
        "reason": reasons or ["bounded_independent_delegation_has_clear_benefit"],
        "limits": {
            "max_concurrent_global": max_global,
            "max_concurrent_per_department": max_department,
            "active_global": len(active),
            "active_department": len(active_department),
        },
        "fixed_department_remains_owner": True,
        "workflow_receipts_satisfied": False,
        "checked_at": utc_timestamp(),
    }
    with workflow_lock(root):
        append_jsonl_locked(root / DELEGATION_DECISIONS, decision)
    return decision, [root / DELEGATION_POLICY, root / DELEGATION_DECISIONS]


def record_delegation(root: Path, args: Any) -> tuple[dict[str, Any], list[Path]]:
    task_id = validate_task_id(str(args.task_id))
    delegation_id = validate_task_id(str(args.delegation_id))
    department = str(args.department).strip()
    status = str(args.status).strip()
    if status not in DELEGATION_STATES:
        raise WorkflowError(f"未知委派状态：{status}")
    policy = load_delegation_policy(root)
    registry = department_registry(root)
    if department not in registry:
        raise WorkflowError(f"部门未登记：{department}")
    if not read_json(snapshot_path(root, task_id)):
        raise WorkflowError(f"工作流不存在：{task_id}")
    evidence_values = [item.strip() for item in str(getattr(args, "evidence", "") or "").split(";") if item.strip()]
    evidence = [file_digest(root, value) for value in evidence_values]
    if status == "completed" and not evidence:
        raise WorkflowError("completed 委派必须提供可校验输出文件")
    idempotency_key = str(args.idempotency_key).strip()
    if not idempotency_key:
        raise WorkflowError("delegation-record 必须提供 --idempotency-key")
    stop_reason = str(getattr(args, "stop_reason", "") or "")
    allowed_stop_reasons = set(str(value) for value in policy.get("stop_reasons", []))
    expected_stop_reason = {
        "completed": {"completed"},
        "failed": {"task_failed", "no_progress", "dependency_blocked", "policy_blocked"},
        "timed_out": {"timeout"},
        "cancelled": {"cancelled", "dependency_blocked", "policy_blocked"},
    }
    if status in TERMINAL_DELEGATION_STATES and stop_reason not in expected_stop_reason.get(status, allowed_stop_reasons):
        raise WorkflowError(f"{status} 必须提供合法 stop_reason")
    if status in ACTIVE_DELEGATION_STATES and stop_reason:
        raise WorkflowError("活动委派不得提前写 stop_reason")

    path = delegations_path(root, task_id)
    with workflow_lock(root):
        rows = read_jsonl(path)
        candidates = [row for row in rows if row.get("idempotency_key") == idempotency_key]
        if candidates:
            existing = candidates[-1]
            if (
                existing.get("delegation_id") != delegation_id
                or existing.get("department") != department
                or existing.get("status") != status
                or existing.get("stop_reason", "") != stop_reason
                or existing.get("evidence", []) != evidence
            ):
                raise WorkflowError("幂等键已绑定不同委派事件")
            return {**existing, "result": "duplicate_ignored"}, [path]

        latest = _latest_delegations(rows).get(delegation_id)
        if status == "started":
            decision_id = str(getattr(args, "decision_id", "") or "")
            decisions = [row for row in read_jsonl(root / DELEGATION_DECISIONS) if row.get("decision_id") == decision_id]
            decision = decisions[-1] if decisions else {}
            if not decision or decision.get("status") != "allow":
                raise WorkflowError("started 委派必须引用已放行的 delegation-check")
            binding = registry[department].get("chat_binding", {})
            if not isinstance(binding, dict) or not _chat_binding_healthy(binding):
                raise WorkflowError("固定部门窗口已不健康，已阻止启动委派")
            scope = str(getattr(args, "scope", "") or "").strip()
            scope_sha256 = hashlib.sha256(scope.encode("utf-8")).hexdigest() if scope else ""
            identity = {
                "task_id": task_id,
                "department": department,
                "scope_sha256": scope_sha256,
            }
            if any(decision.get(key) != value for key, value in identity.items()):
                raise WorkflowError("委派记录与政策预检身份不匹配")
            attempt = int(getattr(args, "attempt", 1) or 1)
            max_attempts = int(policy.get("limits", {}).get("max_attempts", 2))
            if latest is None and attempt != 1:
                raise WorkflowError("首次委派 attempt 必须为 1")
            if latest is not None:
                if latest.get("status") not in TERMINAL_DELEGATION_STATES:
                    raise WorkflowError("委派已在运行，不得重复 started")
                if attempt != int(latest.get("attempt", 1)) + 1:
                    raise WorkflowError("重试 attempt 必须比上一次增加 1")
            if attempt > max_attempts:
                raise WorkflowError("委派重试次数超过上限")
            active = [
                row
                for row in _all_latest_delegations(root)
                if row.get("status") in ACTIVE_DELEGATION_STATES
            ]
            max_global = int(policy.get("limits", {}).get("max_concurrent_global", 3))
            max_department = int(policy.get("limits", {}).get("max_concurrent_per_department", 2))
            if len(active) >= max_global:
                raise WorkflowError("全局委派并发上限已满")
            if sum(1 for row in active if row.get("department") == department) >= max_department:
                raise WorkflowError("当前部门委派并发上限已满")
            timeout_seconds = int(decision.get("timeout_seconds", 900))
            started_at = dt.datetime.now(dt.timezone.utc)
            inherited = {
                "benefit": decision.get("benefit"),
                "work_class": decision.get("work_class"),
                "scope_sha256": decision.get("scope_sha256"),
                "scope_body_stored": False,
                "decision_id": decision_id,
                "parent_thread_id": decision.get("parent_thread_id"),
                "parent_project_id": decision.get("parent_project_id"),
                "parent_cwd": decision.get("parent_cwd"),
                "attempt": attempt,
                "timeout_seconds": timeout_seconds,
                "deadline_at": (started_at + dt.timedelta(seconds=timeout_seconds)).isoformat(timespec="seconds"),
            }
        else:
            if latest is None or latest.get("status") not in ACTIVE_DELEGATION_STATES:
                raise WorkflowError(f"非法委派跳转：{status} 之前必须有 started/progress")
            inherited = {
                key: latest.get(key)
                for key in (
                    "benefit",
                    "work_class",
                    "scope_sha256",
                    "scope_body_stored",
                    "decision_id",
                    "parent_thread_id",
                    "parent_project_id",
                    "parent_cwd",
                    "attempt",
                    "timeout_seconds",
                    "deadline_at",
                )
            }

        event = {
            "schema_version": "1.0",
            "event_id": str(uuid.uuid4()),
            "task_id": task_id,
            "delegation_id": delegation_id,
            "department": department,
            "status": status,
            **inherited,
            "stop_reason": stop_reason,
            "evidence": evidence,
            "idempotency_key": idempotency_key,
            "created_at": utc_timestamp(),
            "fixed_department_remains_owner": True,
            "workflow_receipts_satisfied": False,
            "previous_hash": str(rows[-1].get("event_hash", "")) if rows else "",
        }
        event["event_hash"] = sha256_value(_delegation_payload_for_hash(event))
        append_jsonl_locked(path, event)
    return {**event, "result": "recorded"}, [path, root / DELEGATION_DECISIONS]


def reconcile_delegations(
    root: Path,
    task_id: str,
    *,
    now: dt.datetime | None = None,
) -> tuple[dict[str, Any], list[Path]]:
    task_id = validate_task_id(task_id)
    path = delegations_path(root, task_id)
    current_time = now or dt.datetime.now(dt.timezone.utc)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=dt.timezone.utc)
    with workflow_lock(root):
        rows, invalid = _validate_delegation_chain(root, task_id)
        if not invalid:
            latest = _latest_delegations(rows)
            for delegation_id, row in list(latest.items()):
                if row.get("status") not in ACTIVE_DELEGATION_STATES:
                    continue
                try:
                    deadline = dt.datetime.fromisoformat(str(row.get("deadline_at", "")))
                except ValueError:
                    invalid.append(f"delegation_deadline_invalid:{delegation_id}")
                    continue
                if deadline.tzinfo is None:
                    deadline = deadline.replace(tzinfo=dt.timezone.utc)
                if deadline > current_time:
                    continue
                event = {
                    **{
                        key: row.get(key)
                        for key in (
                            "benefit",
                            "work_class",
                            "scope_sha256",
                            "scope_body_stored",
                            "decision_id",
                            "parent_thread_id",
                            "parent_project_id",
                            "parent_cwd",
                            "attempt",
                            "timeout_seconds",
                            "deadline_at",
                        )
                    },
                    "schema_version": "1.0",
                    "event_id": str(uuid.uuid4()),
                    "task_id": task_id,
                    "delegation_id": delegation_id,
                    "department": row.get("department"),
                    "status": "timed_out",
                    "stop_reason": "timeout",
                    "evidence": [],
                    "idempotency_key": f"auto-timeout:{delegation_id}:{row.get('attempt')}:{row.get('deadline_at')}",
                    "created_at": utc_timestamp(),
                    "fixed_department_remains_owner": True,
                    "workflow_receipts_satisfied": False,
                    "previous_hash": str(rows[-1].get("event_hash", "")) if rows else "",
                }
                event["event_hash"] = sha256_value(_delegation_payload_for_hash(event))
                append_jsonl_locked(path, event)
                rows.append(event)
            latest = _latest_delegations(rows)
        else:
            latest = _latest_delegations(rows)
    active = [row for row in latest.values() if row.get("status") in ACTIVE_DELEGATION_STATES]
    terminal = [row for row in latest.values() if row.get("status") in TERMINAL_DELEGATION_STATES]
    payload = {
        "status": "blocked_delegation_ledger_invalid" if invalid else "delegation_status_ready",
        "task_id": task_id,
        "active_count": len(active),
        "terminal_count": len(terminal),
        "active": sorted(
            [
                {
                    "delegation_id": row.get("delegation_id"),
                    "department": row.get("department"),
                    "status": row.get("status"),
                    "attempt": row.get("attempt"),
                    "deadline_at": row.get("deadline_at"),
                }
                for row in active
            ],
            key=lambda row: str(row.get("delegation_id", "")),
        ),
        "terminal": sorted(
            [
                {
                    "delegation_id": row.get("delegation_id"),
                    "department": row.get("department"),
                    "status": row.get("status"),
                    "attempt": row.get("attempt"),
                    "stop_reason": row.get("stop_reason"),
                }
                for row in terminal
            ],
            key=lambda row: str(row.get("delegation_id", "")),
        ),
        "blockers": invalid,
        "fixed_department_remains_owner": True,
        "workflow_receipts_satisfied": False,
        "ledger": rel_path(root, path),
    }
    artifacts = [root / DELEGATION_POLICY]
    if path.exists():
        artifacts.insert(0, path)
    if (root / DELEGATION_DECISIONS).exists():
        artifacts.append(root / DELEGATION_DECISIONS)
    return payload, artifacts


def append_workflow_event(root: Path, task_id: str, state: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    events_path = root / WORKFLOW_EVENTS
    previous = ""
    for event in reversed(read_jsonl(events_path)):
        if event.get("event_hash"):
            previous = str(event["event_hash"])
            break
    event = {
        "schema_version": "1.0",
        "event_id": str(uuid.uuid4()),
        "task_id": task_id,
        "state": state,
        "created_at": utc_timestamp(),
        "details": details or {},
        "previous_event_hash": previous,
    }
    event["event_hash"] = sha256_value(event)
    append_jsonl_locked(events_path, event)
    return event


def validate_workflow_events(root: Path, task_id: str) -> list[str]:
    events = read_jsonl(root / WORKFLOW_EVENTS)
    invalid: list[str] = []
    previous = ""
    for index, event in enumerate(events, start=1):
        if event.get("previous_event_hash", "") != previous:
            invalid.append(f"event_{index}:previous_hash_mismatch")
        calculated = sha256_value({key: value for key, value in event.items() if key != "event_hash"})
        if event.get("event_hash") != calculated:
            invalid.append(f"event_{index}:event_hash_mismatch")
        previous = str(event.get("event_hash", ""))

    task_events = [event for event in events if event.get("task_id") == task_id]
    from original_task_publisher_handover import binding
    try:
        binding(root, task_id)
    except (ValueError, KeyError, OSError) as error:
        invalid.append(f"publisher_handover_event_invalid:{error}")
    if not task_events:
        return invalid
    if task_events[0].get("state") != "planned":
        invalid.append("event_order:first_state_not_planned")
    rank = {
        state: index
        for index, state in enumerate(
            [
                "planned", "dispatch_ready", "dispatched", "acknowledged", "evidence_received",
                "qa_passed", "waiting_owner_approval", "owner_approved", "execution_completed",
                "verified", "closed",
            ]
        )
    }
    # Older reconciles restarted the whole derived sequence after a repaired
    # evidence block. Recognize only that exact legacy replay, backed by a
    # replacement receipt in the same reconciliation batch. Never rewrite the
    # event log or waive its hash checks (receipt integrity is checked separately).
    reviewer = _final_qa_department(root, read_json(snapshot_path(root, task_id)) or {"task_id": task_id})
    task_receipts = read_jsonl(receipts_path(root, task_id))
    replacement_times = {
        row.get("created_at")
        for row in task_receipts
        if row.get("receipt_type") == "evidence_replacement"
    }
    qa_verdicts = [
        row for row in task_receipts
        if row.get("receipt_type") == "qa_verdict" and row.get("department") == reviewer
    ]

    qa_by_id = {str(row.get("receipt_id")): row for row in qa_verdicts}

    def corrected_release_after_premature_close(index: int, event: dict[str, Any]) -> bool:
        """Accept a legacy internal close only when later QA and owner scope prove a release."""

        if index < 2 or event.get("state") != "owner_approved":
            return False
        closed = task_events[index - 1]
        if (closed.get("state") != "closed"
                or task_events[index - 2].get("state") != "verified"
                or closed.get("details") != {"reconciled": True}):
            return False
        try:
            closed_at = dt.datetime.fromisoformat(str(closed.get("created_at", "")))
            approved_at = dt.datetime.fromisoformat(str(event.get("created_at", "")))
            earlier = [row for row in qa_verdicts
                       if dt.datetime.fromisoformat(str(row.get("created_at", ""))) <= closed_at]
            later = [row for row in qa_verdicts
                     if closed_at < dt.datetime.fromisoformat(str(row.get("created_at", ""))) <= approved_at]
            if not earlier or earlier[-1].get("verdict") != "pass" or _latest_qa_release_route(earlier):
                return False
            if not later or later[-1].get("verdict") != "pass":
                return False
            qa = later[-1]
            action_id, scope = str(qa.get("action_id") or ""), str(qa.get("scope") or "")
            route = _latest_qa_release_route(later)
            if not action_id or not route or not scope:
                return False
            return any(
                approval.get("task_id") == task_id
                and approval.get("action_id") == action_id
                and approval.get("action_class") == route
                and approval.get("scope") == scope
                and approval.get("status") in {"active", "consumed"}
                and closed_at < dt.datetime.fromisoformat(str(approval.get("granted_at", ""))) <= approved_at
                # Event validity is historical: a later revocation must not
                # retroactively corrupt an owner-approved event or re-enable
                # the revoked approval for a future policy check.
                for approval in read_jsonl(root / APPROVAL_LEDGER)
            )
        except ValueError:
            return False

    def matching_qa_verdict(event: dict[str, Any], verdict: str, after: str = "") -> bool:
        try:
            event_time = dt.datetime.fromisoformat(str(event.get("created_at", "")))
            after_time = dt.datetime.fromisoformat(after) if after else None
            details = event.get("details", {}) if isinstance(event.get("details"), dict) else {}
            receipt_id = str(details.get("qa_receipt_id") or "")
            if receipt_id:
                selected = qa_by_id.get(receipt_id)
                if not selected or selected.get("receipt_hash") != details.get("qa_receipt_hash"):
                    return False
            else:
                # Pre-ID events are immutable. Recover their precise stage from
                # the latest QA receipt already present when that event was
                # emitted, rather than an arbitrary wall-clock delay limit.
                eligible = [
                    row for row in qa_verdicts
                    if dt.datetime.fromisoformat(str(row.get("created_at", ""))) <= event_time
                ]
                selected = eligible[-1] if eligible else None
            if not selected or selected.get("verdict") != verdict:
                return False
            receipt_time = dt.datetime.fromisoformat(str(selected.get("created_at", "")))
            return receipt_time <= event_time and (after_time is None or receipt_time >= after_time)
        except ValueError:
            return False

    def corrected_legacy_postcheck_replay(index: int, event: dict[str, Any]) -> bool:
        """Accept one historical terminal replay caused by an exact action-identity correction.

        This is not a general permission to move backwards from closed. The
        earlier unscoped postcheck, the sole successful execution, and the
        correcting postcheck must share immutable evidence and ordered times.
        """
        if (event.get("state") != "verified" or index < 1
                or index + 1 >= len(task_events)
                or task_events[index - 1].get("state") != "closed"):
            return False
        following = task_events[index + 1]
        stamp = str(event.get("created_at") or "")
        if (following.get("state") != "closed" or following.get("created_at") != stamp
                or event.get("details") != {"reconciled": True}
                or following.get("details") != {"reconciled": True}):
            return False
        try:
            replay_at = dt.datetime.fromisoformat(stamp)
            prior_close_at = dt.datetime.fromisoformat(str(task_events[index - 1].get("created_at") or ""))
        except ValueError:
            return False
        if replay_at <= prior_close_at:
            return False
        corrections = [
            row for row in task_receipts
            if row.get("receipt_type") == "postcheck" and row.get("verdict") == "pass"
            and row.get("created_at") == stamp
            and row.get("action_id") and row.get("action_class") and row.get("scope")
        ]
        if len(corrections) != 1:
            return False
        correction = corrections[0]
        successful = [
            row for row in task_receipts
            if row.get("receipt_type") == "execution_result" and row.get("verdict") == "pass"
            and row.get("created_at", "") <= stamp
        ]
        if len(successful) != 1:
            return False
        execution = successful[0]
        if any(
            correction.get(key) != execution.get(key)
            for key in ("department", "action_id", "action_class", "scope")
        ):
            return False
        correction_evidence = {
            (item.get("path"), item.get("sha256"))
            for item in correction.get("evidence", [])
        }
        return any(
            row.get("receipt_type") == "postcheck" and row.get("verdict") == "pass"
            and row.get("department") == execution.get("department")
            and not row.get("action_id") and not row.get("action_class") and not row.get("scope")
            and row.get("created_at", "") >= execution.get("created_at", "")
            and row.get("created_at", "") <= task_events[index - 1].get("created_at", "")
            and correction_evidence.intersection(
                (item.get("path"), item.get("sha256")) for item in row.get("evidence", [])
            )
            for row in task_receipts
        )

    def recovered_historical_qa_postcheck(index: int, event: dict[str, Any]) -> bool:
        """Allow one audited terminal recovery after a closed legacy QA postcheck drifted.

        The original unscoped QA postcheck is preserved. A current, action-bound
        QA postcheck may close the workflow only after both historical evidence
        owners have explicitly replaced their changed evidence baselines.
        """
        if (event.get("state") != "verified" or index < 2
                or index + 1 >= len(task_events)
                or task_events[index - 2].get("state") != "closed"
                or task_events[index - 1].get("state") != "blocked_evidence_invalid"):
            return False
        following = task_events[index + 1]
        stamp = str(event.get("created_at") or "")
        if (following.get("state") != "closed" or following.get("created_at") != stamp
                or event.get("details") != {"reconciled": True}
                or following.get("details") != {"reconciled": True}):
            return False
        try:
            blocked_at = dt.datetime.fromisoformat(str(task_events[index - 1].get("created_at") or ""))
            recovered_at = dt.datetime.fromisoformat(stamp)
            if recovered_at <= blocked_at:
                return False
        except ValueError:
            return False
        corrections = [
            row for row in task_receipts
            if row.get("receipt_type") == "postcheck"
            and row.get("department") == reviewer
            and row.get("verdict") == "pass"
            and row.get("created_at") == stamp
            and all(row.get(key) for key in ("action_id", "action_class", "scope", "evidence"))
        ]
        executions = [
            row for row in task_receipts
            if row.get("receipt_type") == "execution_result"
            and row.get("verdict") in {"", "pass"}
            and row.get("created_at", "") <= stamp
        ]
        if len(corrections) != 1 or len(executions) != 1:
            return False
        correction, execution = corrections[0], executions[0]
        if any(correction.get(key) != execution.get(key)
               for key in ("action_id", "action_class", "scope")):
            return False
        prior_postchecks = [
            row for row in task_receipts
            if row.get("receipt_type") == "postcheck"
            and row.get("department") == reviewer
            and not any(row.get(key) for key in ("action_id", "action_class", "scope"))
            and execution.get("created_at", "") <= row.get("created_at", "")
            <= task_events[index - 2].get("created_at", "")
        ]
        if len(prior_postchecks) != 1:
            return False
        replaced_ids: set[str] = set()
        for row in task_receipts:
            if row.get("receipt_type") != "evidence_replacement":
                continue
            try:
                replacement_at = dt.datetime.fromisoformat(str(row.get("created_at") or ""))
            except ValueError:
                return False
            if blocked_at <= replacement_at <= recovered_at:
                replaced_ids.add(str(row.get("supersedes_receipt_id") or ""))
        return (str(execution.get("receipt_id") or "") in replaced_ids
                and str(prior_postchecks[0].get("receipt_id") or "") in replaced_ids)

    def authorized_qa_only_execution_stage(event: dict[str, Any]) -> bool:
        """Recognize an audited execution handoff, not a second candidate cycle.

        This changes historical event ordering only. Receipt hashes, fixed
        routing, exact QA/approval and execution checks remain independent.
        """
        details = event.get("details", {})
        original = task_events[0].get("details", {})
        if (details.get("refresh_reason") != "qa_only_review_completed_add_exact_authorized_execution_stage"
                or not details.get("plan_refresh")
                or event.get("state") != "waiting_owner_approval"
                or details.get("request_hash") != original.get("request_hash")
                or [row.get("department") for row in original.get("departments", [])] != ["qa"]):
            return False
        new_rows = details.get("departments", [])
        by_department = {row.get("department"): row for row in new_rows}
        if (len(new_rows) != 2 or set(by_department) != {"qa", "content-organic-website"}
                or by_department["qa"] != original["departments"][0]
                or by_department["content-organic-website"].get("execution_wave") != 2
                or by_department["content-organic-website"].get("depends_on") != ["qa"]):
            return False
        stamp = str(event.get("created_at", ""))
        prior_qa = [row for row in qa_verdicts if row.get("created_at", "") <= stamp]
        if not prior_qa or prior_qa[-1].get("verdict") != "pass":
            return False
        qa = prior_qa[-1]
        # This compatibility recovery is only for exact, previously authorized
        # cache execution. It cannot add arbitrary publishing departments.
        if qa.get("action_class") != "site_cache_candidate":
            return False
        policies = read_jsonl(root / "logs/policy-decisions.jsonl")
        routing = next((row for row in policies if row.get("decision_id")
                        == details.get("routing_policy_decision_id")), {})
        if (routing.get("status") != "allow" or routing.get("routing_status") != "routing_allowed"
                or routing.get("task_id") != task_id or routing.get("action_class") != "thread_message"
                or routing.get("target_department") != "content-organic-website"
                or routing.get("target_thread_id") != by_department["content-organic-website"].get("chat_task_id")
                or routing.get("checked_at", "") > stamp):
            return False
        approvals = [row for row in read_jsonl(root / APPROVAL_LEDGER)
                     if row.get("task_id") == task_id and row.get("status") == "consumed"
                     and row.get("action_id") == qa.get("action_id")
                     and row.get("action_class") == "site_cache_invalidation"
                     and row.get("scope") == qa.get("scope")]
        return any(row.get("status") == "allow" and row.get("task_id") == task_id
                   and row.get("department") == "content-organic-website"
                   and row.get("action_id") == qa.get("action_id")
                   and row.get("action_class") == "site_cache_invalidation"
                   and row.get("scope") == qa.get("scope") and row.get("checked_at", "") <= stamp
                   and any(approval.get("approval_id") == row.get("approval_id") for approval in approvals)
                   for row in policies)

    last_rank = -1
    replay_end = -1
    rework_opened_at = ""
    authorized_execution_handoff = False
    def completed_exact_retry_replay(index: int) -> int:
        """Recognize a derived full replay after one audited failed execution.

        An exception is not permission to regress: only a completed execution
        bound to its existing exact retry policy permits this historical batch.
        Receipt integrity and current evidence validation still apply normally.
        """
        if index < 1 or task_events[index - 1].get("state") != "blocked":
            return index
        expected = ["dispatched", "acknowledged", "evidence_received", "qa_passed",
                    "waiting_owner_approval", "owner_approved", "execution_completed"]
        batch = task_events[index:index + len(expected)]
        stamp = str(task_events[index].get("created_at") or "")
        if ([row.get("state") for row in batch] != expected
                or any(row.get("created_at") != stamp for row in batch)
                or any(row.get("details") != {"reconciled": True}
                       for row in batch if row.get("state") != "qa_passed")
                or not matching_qa_verdict(batch[3], "pass")):
            return index
        policies = {row.get("decision_id"): row
                    for row in read_jsonl(root / "logs/policy-decisions.jsonl")}
        by_receipt = {row.get("receipt_id"): row for row in task_receipts}
        for execution in task_receipts:
            if (execution.get("receipt_type") != "execution_result"
                    or execution.get("verdict") != "pass"
                    or execution.get("created_at") != stamp):
                continue
            policy = policies.get(execution.get("policy_decision_id"), {})
            failed = by_receipt.get(policy.get("retry_source_receipt_id"), {})
            exact_keys = ("task_id", "department", "action_id", "action_class", "scope", "approval_id")
            if (policy.get("status") != "allow"
                    or policy.get("approval_basis") != "blocked_execution_retry"
                    or policy.get("approval_status") != "consumed"
                    or not policy.get("checked_at")
                    or not failed.get("created_at")
                    or not failed["created_at"] <= policy["checked_at"] <= stamp
                    or failed.get("receipt_type") != "execution_result"
                    or failed.get("verdict") != "blocked"
                    or any(not execution.get(key) or execution.get(key) != policy.get(key)
                           or execution.get(key) != failed.get(key) for key in exact_keys)):
                continue
            qa = qa_by_id.get(batch[3].get("details", {}).get("qa_receipt_id"), {})
            if (qa.get("action_id") != execution.get("action_id")
                    or qa.get("scope") != execution.get("scope")
                    or RELEASE_CANDIDATE_ACTION_ROUTES.get(qa.get("action_class")) != execution.get("action_class")):
                continue
            return index + len(expected)
        return index

    for index, event in enumerate(task_events):
        state = str(event.get("state", ""))
        if index < replay_end:
            continue
        if state == "qa_blocked":
            authorized_execution_handoff = False
            # A verified QA block opens a new review cycle even if an earlier
            # candidate had already reached owner approval. Repeated blocked
            # snapshots do not create additional cycles.
            if matching_qa_verdict(event, "blocked"):
                rework_opened_at = str(event.get("created_at", ""))
                last_rank = min(last_rank, rank["evidence_received"])
            continue
        if state in EXCEPTION_STATES:
            continue
        if state not in rank:
            invalid.append(f"event_order:unknown_state:{state}")
            continue
        current_rank = rank[state]
        retry_end = completed_exact_retry_replay(index) if current_rank < last_rank else index
        if retry_end > index:
            replay_end = retry_end
            last_rank = rank["execution_completed"]
            continue
        details = event.get("details", {}) if isinstance(event.get("details"), dict) else {}
        if authorized_qa_only_execution_stage(event):
            authorized_execution_handoff = True
        if (authorized_execution_handoff and current_rank < last_rank
                and state in {"dispatched", "acknowledged", "evidence_received", "qa_passed"}
                and (details == {"reconciled": True}
                     or state == "qa_passed" and details.get("reconciled") is True
                     and matching_qa_verdict(event, "pass"))):
            # Preserve the attained approval rank; a delivery ack does not
            # undo QA/approval or claim an execution/postcheck success.
            continue
        if (
            state == "planned"
            and index > 0
            and task_events[index - 1].get("state") == "blocked_evidence_invalid"
            and details == {"reconciled": True}
            and event.get("created_at") in replacement_times
            and last_rank >= rank["evidence_received"]
        ):
            prior_state = next(name for name, value in rank.items() if value == last_rank)
            for approval_required, external_required in ((False, False), (False, True), (True, True)):
                expected = _state_sequence(
                    "blocked_evidence_invalid", prior_state, approval_required, external_required
                )
                replay = task_events[index:index + len(expected)]
                if (
                    expected
                    and [row.get("state") for row in replay] == expected
                    and all(row.get("details") == {"reconciled": True} for row in replay)
                    and all(row.get("created_at") == event.get("created_at") for row in replay)
                ):
                    replay_end = index + len(expected)
                    break
            if index < replay_end:
                continue
        if (
            state == "qa_passed"
            and details.get("reopened_for_external_execution") is True
            and last_rank == rank["closed"]
        ):
            last_rank = current_rank
            continue
        if last_rank == rank["closed"] and (
            corrected_legacy_postcheck_replay(index, event)
            or recovered_historical_qa_postcheck(index, event)
        ):
            replay_end = index + 2
            continue
        if (
            state == "qa_passed"
            and details.get("reopened_for_next_action") is True
            and last_rank == rank["closed"]
        ):
            qa = qa_by_id.get(str(details.get("qa_receipt_id") or ""), {})
            route = RELEASE_CANDIDATE_ACTION_ROUTES.get(str(qa.get("action_class") or ""), "")
            action = str(qa.get("action_id") or "")
            scope = str(qa.get("scope") or "")
            try:
                event_time = dt.datetime.fromisoformat(str(event.get("created_at") or ""))
                prior_other_action = any(
                    row.get("receipt_type") == "postcheck"
                    and row.get("verdict") == "pass"
                    and row.get("action_id") != action
                    and dt.datetime.fromisoformat(str(row.get("created_at") or "")) <= event_time
                    for row in read_jsonl(receipts_path(root, task_id))
                )
                exact_approval = any(
                    row.get("task_id") == task_id
                    and row.get("action_id") == action
                    and row.get("action_class") == route
                    and row.get("scope") == scope
                    and row.get("status") in {"active", "consumed"}
                    and dt.datetime.fromisoformat(str(row.get("granted_at") or "")) <= event_time
                    for row in read_jsonl(root / APPROVAL_LEDGER)
                )
                valid_reopen = (
                    bool(qa) and qa.get("verdict") == "pass"
                    and qa.get("receipt_hash") == details.get("qa_receipt_hash")
                    and dt.datetime.fromisoformat(str(qa.get("created_at") or "")) <= event_time
                    and bool(action and scope and route)
                    and prior_other_action and exact_approval
                )
            except ValueError:
                valid_reopen = False
            if not valid_reopen:
                invalid.append("event_order:unverified_next_action_reopen")
            last_rank = current_rank
            continue
        if current_rank < last_rank and corrected_release_after_premature_close(index, event):
            last_rank = current_rank
            continue
        if state == "qa_passed" and rework_opened_at:
            if not matching_qa_verdict(event, "pass", rework_opened_at):
                invalid.append("event_order:rework_missing_qa_pass_receipt")
            rework_opened_at = ""
        if current_rank < last_rank:
            invalid.append(f"event_order:regression:{state}")
        last_rank = max(last_rank, current_rank)
    return invalid


def initialize_workflow(
    root: Path,
    *,
    task_id: str,
    request: str,
    plan_status: str,
    departments: list[dict[str, Any]],
    owner_approval_required: bool,
    goal_delivery: dict[str, Any] | None = None,
    goal_contract: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], bool]:
    task_id = validate_task_id(task_id)
    from goal_delivery_runtime import enabled, validate_goal
    if goal_delivery is not None:
        goal_delivery = validate_goal(root, goal_delivery)
        if goal_contract is not None and file_digest(root, goal_contract.get("path", "")) != goal_contract:
            raise WorkflowError("frozen complete goal input bytes required")
        if goal_contract is not None and validate_goal(root, read_json(safe_path(root, goal_contract["path"]))) != goal_delivery:
            raise WorkflowError("frozen input must contain this exact complete goal")
    elif enabled(root) and not snapshot_path(root, task_id).exists():
        raise WorkflowError("new runtime tasks require one complete goal and responsible assistant")
    request_hash = hashlib.sha256(request.strip().encode("utf-8")).hexdigest()
    path = snapshot_path(root, task_id)
    selected = []
    for item in departments:
        selected.append(
            {
                "department": str(item.get("department", "")),
                "chat_task_id": str(item.get("chat_task_id") or ""),
                "execution_wave": int(item.get("execution_wave", 1)),
                "depends_on": list(item.get("depends_on", [])),
            }
        )
    if goal_delivery is not None:
        planned_roles = {x["department"] for x in selected}
        if not (set(goal_delivery["producer_departments"]) | {goal_delivery["responsible_assistant"]}) <= planned_roles:
            raise WorkflowError("complete-goal producers and assistant must be planned")
    with workflow_lock(root):
        existing = read_json(path)
        if existing:
            if goal_delivery is not None and existing.get("goal_delivery") != goal_delivery:
                raise WorkflowError("existing task goal differs; bind exact goal without rewriting history")
            if existing.get("request_hash") != request_hash:
                raise WorkflowError(
                    f"任务编号 {task_id} 已绑定不同内容；已阻止覆盖或重新分派"
                )
            receipts, receipt_invalid = _validate_receipt_chain(root, task_id)
            event_invalid = validate_workflow_events(root, task_id)
            definition_changed = (
                existing.get("departments", []) != selected
                or bool(existing.get("owner_approval_required")) != bool(owner_approval_required)
            )
            if definition_changed:
                if receipt_invalid or event_invalid:
                    raise WorkflowError("事件或回执链无效，禁止刷新派工定义")
                selected_departments = {
                    str(item.get("department", "")) for item in selected
                }
                retained_dispatch_only = bool(receipts) and all(
                    row.get("receipt_type") == "dispatch_sent"
                    and str(row.get("department", "")) in selected_departments
                    for row in receipts
                )
                if (
                    (receipts and not retained_dispatch_only)
                    or existing.get("current_state") not in {"planned", "blocked", "dispatch_ready"}
                ):
                    raise WorkflowError("已有派工回执或后续状态，禁止刷新部门路由")
                state = "dispatch_ready" if plan_status == "ready_to_send" else "blocked"
                blockers = [] if state == "dispatch_ready" else [f"dispatch_plan:{plan_status}"]
                append_workflow_event(
                    root,
                    task_id,
                    state,
                    {
                        "plan_refresh": True,
                        "request_hash": request_hash,
                        "plan_status": plan_status,
                        "plan_blockers": blockers,
                        "departments": selected,
                        "owner_approval_required": bool(owner_approval_required),
                        "refresh_reason": (
                            "pre_ack_routing_rules_changed_retained_dispatch"
                            if retained_dispatch_only
                            else "pre_dispatch_routing_rules_changed"
                        ),
                    },
                )
                existing.update(
                    {
                        "departments": selected,
                        "owner_approval_required": bool(owner_approval_required),
                        "plan_status": plan_status,
                        "plan_blockers": blockers,
                        "current_state": state,
                        "resume_from": "planned" if state == "blocked" else "",
                        "updated_at": utc_timestamp(),
                        "blockers": blockers,
                        "missing_receipts": [],
                        "next_legal_actions": ["receipt-record:dispatch_sent"]
                        if state == "dispatch_ready"
                        else ["repair_dispatch_plan"],
                        "event_count": sum(
                            row.get("task_id") == task_id
                            for row in read_jsonl(root / WORKFLOW_EVENTS)
                        ),
                    }
                )
                atomic_write_json(path, existing)
            if existing.get("plan_status") in RECOVERABLE_PLAN_STATES - {"ready_to_send"}:
                existing = _repair_dispatch_plan_locked(root, existing)
            receipt_log = receipts_path(root, task_id)
            if not receipt_log.exists():
                atomic_write_text(receipt_log, "")
            return existing, False
        initial_state = "dispatch_ready" if plan_status == "ready_to_send" else "blocked"
        snapshot = {
            "schema_version": "1.0",
            "task_id": task_id,
            "request_hash": request_hash,
            "request_summary_hash_only": True,
            "created_at": utc_timestamp(),
            "updated_at": utc_timestamp(),
            "current_state": initial_state,
            "resume_from": "planned" if initial_state == "blocked" else "",
            "plan_status": plan_status,
            "departments": selected,
            "owner_approval_required": bool(owner_approval_required),
            "paid_promotion_enabled": False,
            "missing_receipts": [],
            "blockers": [] if initial_state != "blocked" else [f"dispatch_plan:{plan_status}"],
            "next_legal_actions": ["receipt-record:dispatch_sent"] if initial_state != "blocked" else ["repair_dispatch_plan"],
            "last_receipt_hash": "",
            "event_count": 0,
            "receipt_count": 0,
            "integrity_note": "SHA-256 chains detect accidental mutation; they are not digital signatures.",
            "scope_note": "Project-level control only; not a global Codex tool middleware.",
            **({"goal_delivery": goal_delivery} if goal_delivery is not None else {}),
            **({"goal_contract": goal_contract} if goal_contract is not None else {}),
        }
        append_workflow_event(
            root,
            task_id,
            "planned",
            {
                "request_hash": request_hash,
                "plan_status": plan_status,
                "departments": selected,
                "owner_approval_required": bool(owner_approval_required),
                **({"goal_delivery": goal_delivery} if goal_delivery is not None else {}),
                **({"goal_contract": goal_contract} if goal_contract is not None else {}),
            },
        )
        append_workflow_event(root, task_id, initial_state, {"plan_status": plan_status})
        snapshot["event_count"] = 2
        atomic_write_json(path, snapshot)
        atomic_write_text(receipts_path(root, task_id), "")
        return snapshot, True


RECOVERABLE_PLAN_STATES = {
    "blocked_health_stale", "blocked_chat_health", "blocked_ui_visibility",
    "blocked_route_invalid", "ready_to_send",
}


def _apply_plan_refresh(snapshot: dict[str, Any], events: list[dict[str, Any]], root: Path | None = None) -> None:
    """Replay committed route and binding changes in event order."""
    for event in events:
        details = event.get("details", {})
        if event.get("task_id") != snapshot.get("task_id"):
            continue
        if isinstance(details.get("goal_delivery"), dict):
            snapshot["goal_delivery"] = details["goal_delivery"]
        if isinstance(details.get("goal_contract"), dict):
            snapshot["goal_contract"] = details["goal_contract"]
        if isinstance(details.get("workflow_successor_link"), dict):
            snapshot["workflow_successor_link"] = details["workflow_successor_link"]
        if isinstance(details.get("assignment_departments"), list):
            snapshot["departments"] = details["assignment_departments"]
        if details.get("plan_refresh"):
            if details.get("request_hash") != snapshot.get("request_hash"):
                raise WorkflowError("恢复事件的任务内容哈希不匹配")
            snapshot["plan_status"] = details["plan_status"]
            snapshot["plan_blockers"] = details.get("plan_blockers", [])
            if "departments" in details:
                snapshot["departments"] = details["departments"]
            if "owner_approval_required" in details:
                snapshot["owner_approval_required"] = bool(details["owner_approval_required"])
            if snapshot.get("current_state") in {"planned", "blocked", "dispatch_ready"}:
                snapshot["current_state"] = event["state"]
        if details.get("binding_refresh") and details.get("departments"):
            snapshot["departments"] = details["departments"]

    if root is not None:
        from original_task_publisher_handover import replay
        replay(root, snapshot)


def correct_false_positive_route(root: Path, task_id: str, route_id: str) -> tuple[dict[str, Any], list[Path]]:
    """Narrow an erroneous multi-route without inventing or removing receipts.

    Only a route already present in the original matched plan may be retained.
    Every department with a real receipt must remain, and QA/external execution
    must not have reached a verdict. The original dispatch artifact stays intact.
    """
    task_id = validate_task_id(task_id)
    plan_path = safe_path(root, f"logs/dispatch/{task_id}.json")
    plan = read_json(plan_path)
    plan_route = str((plan.get("route") or {}).get("id") or "")
    if not plan_route.startswith("multi:") or route_id not in plan_route[6:].split("+"):
        raise WorkflowError("只能从原始 multi 路由保留其中已命中的一条规则")
    rules = read_json(root / "data/department-routing-rules.json")
    route = next((row for row in rules.get("routes", []) if row.get("id") == route_id), None)
    if not isinstance(route, dict):
        raise WorkflowError("目标路由不在当前规则中")
    selected_ids = set(route.get("required_departments", [])) | set(route.get("follow_up_departments", []))
    selected_ids.update(route.get("parallel_departments", []))
    dependency_map = route.get("department_dependencies", {})
    if not isinstance(dependency_map, dict) or any(not isinstance(deps, list) for deps in dependency_map.values()):
        raise WorkflowError("目标路由依赖格式无效")
    selected_ids.update(dependency_map)
    selected_ids.update(dep for deps in dependency_map.values() for dep in deps)
    if not selected_ids:
        raise WorkflowError("目标路由没有部门")

    path = snapshot_path(root, task_id)
    with workflow_lock(root):
        snapshot = read_json(path)
        if not snapshot or snapshot.get("request_hash") != hashlib.sha256(
            str(plan.get("request") or "").strip().encode("utf-8")
        ).hexdigest():
            raise WorkflowError("原始分派计划与工作流内容不一致")
        event_invalid = validate_workflow_events(root, task_id)
        receipts, receipt_invalid = _validate_receipt_chain(root, task_id)
        if event_invalid or receipt_invalid:
            raise WorkflowError("事件或回执链无效，禁止路由纠偏")
        already_corrected = any(
            row.get("task_id") == task_id
            and (row.get("details") or {}).get("route_correction") == route_id
            for row in read_jsonl(root / WORKFLOW_EVENTS)
        )
        if already_corrected:
            changed = False
        else:
            if snapshot.get("current_state") not in {
                "dispatch_ready", "dispatched", "acknowledged", "evidence_received"
            }:
                raise WorkflowError("当前阶段不允许缩小路由")
            if any(row.get("receipt_type") in {"qa_verdict", "execution_result", "postcheck"} for row in receipts):
                raise WorkflowError("QA 或外部执行已有回执，禁止修改路由")
            old_departments = {str(row.get("department")) for row in snapshot.get("departments", [])}
            if not selected_ids < old_departments:
                raise WorkflowError("纠偏只能删除未分派的误命中部门，不能增加或保持原路由")
            removed = old_departments - selected_ids
            if any(str(row.get("department")) in removed for row in receipts):
                raise WorkflowError("拟移除部门已有真实回执，禁止纠偏")
            selected = []
            for raw in snapshot["departments"]:
                department = str(raw.get("department"))
                if department not in selected_ids:
                    continue
                item = dict(raw)
                item["depends_on"] = list(dependency_map.get(department, []))
                selected.append(item)
            append_workflow_event(root, task_id, str(snapshot["current_state"]), {
                "plan_refresh": True,
                "route_correction": route_id,
                "prior_route": plan_route,
                "reason": "false_positive_multi_route_no_removed_department_receipts",
                "request_hash": snapshot["request_hash"],
                "plan_status": "ready_to_send",
                "plan_blockers": [],
                "departments": selected,
                "owner_approval_required": bool(route.get("approval_required", False)),
                "removed_departments": sorted(removed),
            })
            # The event is authoritative if execution stops before this snapshot write.
            snapshot.update({
                "departments": selected,
                "owner_approval_required": bool(route.get("approval_required", False)),
                "plan_status": "ready_to_send",
                "plan_blockers": [],
                "updated_at": utc_timestamp(),
            })
            atomic_write_json(path, snapshot)
            changed = True
    reconciled, artifacts = reconcile_workflow(root, task_id=task_id)
    return {
        "status": "workflow_route_corrected" if changed else "duplicate_ignored",
        "task_id": task_id,
        "route_id": route_id,
        "current_state": reconciled["current_state"],
        "missing_receipts": reconciled["missing_receipts"],
        "owner_approval_required": reconciled["owner_approval_required"],
    }, [plan_path, *artifacts]


def _repair_dispatch_plan_locked(root: Path, snapshot: dict[str, Any]) -> dict[str, Any]:
    """Refresh only a pre-dispatch plan; never replace identities or create receipts."""
    task_id = str(snapshot["task_id"])
    invalid = validate_workflow_events(root, task_id)
    receipts, receipt_invalid = _validate_receipt_chain(root, task_id)
    if invalid or receipt_invalid:
        raise WorkflowError("事件或回执链无效，禁止恢复分派计划")
    events = read_jsonl(root / WORKFLOW_EVENTS)
    _apply_plan_refresh(snapshot, events, root=root)
    if snapshot.get("workflow_successor_link"):
        raise WorkflowError("original plan has an actual successor; follow its existing delivery, do not redispatch")
    if snapshot.get("plan_status") not in RECOVERABLE_PLAN_STATES:
        raise WorkflowError("该阻断不是可自动恢复的部门健康或路由问题")
    if receipts or snapshot.get("current_state") not in {"planned", "blocked", "dispatch_ready"}:
        raise WorkflowError("只能恢复尚无回执的派工前工作流")
    if any(row.get("task_id") == task_id and row.get("state") not in
           {"planned", "blocked", "dispatch_ready"} for row in events):
        raise WorkflowError("工作流已有派工后事件，禁止重新分派")
    registry = department_registry(root)
    policy = load_policy(root)
    routing = policy.get("routing_policy", {})
    from goal_delivery_runtime import enabled as goal_enabled
    # Recheck the existing complete goal; this plan repair does not send a message.
    goal_scope = snapshot["goal_delivery"]["authorized_scope"][0] if goal_enabled(root, snapshot) else ""
    blockers: list[str] = []
    for item in snapshot.get("departments", []):
        department = str(item.get("department", ""))
        binding = registry.get(department, {}).get("chat_binding", {})
        # Identity remains that of the original task; replacement has its own API.
        reasons, _ = _routing_precheck(
            root, policy=policy, departments=registry, sender_department="operations",
            source_project_id=str(routing.get("source_project_id", "")),
            target_project_id=str(binding.get("project_id", "")),
            target_department=department,
            target_thread_id=str(item.get("chat_task_id", "")),
            target_thread_title=str(binding.get("title", "")),
            target_cwd=str(binding.get("cwd", "")),
            target_sidebar_section_id=str(binding.get("sidebar_section_id", "")),
            payload_sha256=str(snapshot.get("request_hash", "")),
            action_class="thread_message",
            task_id=task_id,
            scope=goal_scope,
        )
        handoff = str(binding.get("handoff_path") or "")
        if not handoff or not safe_path(root, handoff).is_file():
            reasons.append("handoff_missing")
        blockers.extend(f"{department}:{reason}" for reason in reasons)
    if not snapshot.get("departments"):
        blockers.append("departments_missing")
    plan_status = "blocked_route_invalid" if blockers else "ready_to_send"
    if blockers and all(reason.endswith("target_thread_unhealthy_or_dispatch_ineligible") for reason in blockers):
        plan_status = "blocked_chat_health"
    state = "blocked" if blockers else "dispatch_ready"
    if snapshot.get("plan_status") != plan_status or snapshot.get("plan_blockers", []) != blockers:
        append_workflow_event(root, task_id, state, {
            "plan_refresh": True, "request_hash": snapshot["request_hash"],
            "plan_status": plan_status, "plan_blockers": blockers,
        })
    snapshot.update({
        "plan_status": plan_status, "plan_blockers": blockers, "current_state": state,
        "resume_from": "planned" if blockers else "", "updated_at": utc_timestamp(),
        "blockers": blockers, "missing_receipts": [],
        "next_legal_actions": ["repair_dispatch_plan"] if blockers else ["receipt-record:dispatch_sent"],
        "event_count": sum(row.get("task_id") == task_id for row in read_jsonl(root / WORKFLOW_EVENTS)),
    })
    atomic_write_json(snapshot_path(root, task_id), snapshot)
    return snapshot


def link_workflow_successor(root: Path, task_id: str, successor_task_id: str,
                            input_path: str) -> tuple[dict[str, Any], list[Path]]:
    """Associate an already sent recovery; never fabricate an old-plan dispatch."""
    task_id, successor_task_id = validate_task_id(task_id), validate_task_id(successor_task_id)
    if task_id == successor_task_id:
        raise WorkflowError("successor must be a different existing task")
    with workflow_lock(root):
        original = read_json(snapshot_path(root, task_id))
        successor = read_json(snapshot_path(root, successor_task_id))
        source = read_json(safe_path(root, input_path))
        source_pin = file_digest(root, input_path)
        for item in (original, successor):
            if not item or validate_workflow_events(root, item["task_id"]):
                raise WorkflowError("intact existing original and successor event chains required")
        old_receipts, old_invalid = _validate_receipt_chain(root, task_id)
        new_receipts, new_invalid = _validate_receipt_chain(root, successor_task_id)
        if old_invalid or new_invalid or old_receipts or original.get("current_state") not in {"planned", "blocked", "dispatch_ready"}:
            raise WorkflowError("only an unreceived pre-dispatch original may link its existing recovery")
        _apply_plan_refresh(original, read_jsonl(root / WORKFLOW_EVENTS), root=root)
        prior = original.get("workflow_successor_link")
        if prior:
            if prior.get("successor_task_id") == successor_task_id and prior.get("source") == source_pin:
                return {**prior, "status": "duplicate_ignored"}, []
            raise WorkflowError("existing successor association is immutable")
        old_roles = sorted((x.get("department"), x.get("chat_task_id")) for x in original.get("departments", []))
        new_roles = sorted((x.get("department"), x.get("chat_task_id")) for x in successor.get("departments", []))
        if not old_roles or old_roles != new_roles:
            raise WorkflowError("same original fixed role scope required")
        for item, key in ((original, "original_request_hash"), (successor, "successor_request_hash")):
            if source.get(key) != item.get("request_hash"):
                raise WorkflowError("exact original and successor request hashes required")
        if source.get("task_id") != task_id or source.get("successor_task_id") != successor_task_id:
            raise WorkflowError("exact successor association task identity required")
        from goal_delivery_runtime import enabled as goal_enabled, _collaboration_native
        if goal_enabled(root, original) or goal_enabled(root, successor):
            old_goal, new_goal = original.get("goal_delivery", {}), successor.get("goal_delivery", {})
            if any(old_goal.get(k) != new_goal.get(k) for k in
                   ("parent_task_id", "primary_owner", "responsible_assistant", "authorized_scope", "authorization_pin")):
                raise WorkflowError("same complete goal authorization and assigned owner required")
        elif original.get("request_hash") != successor.get("request_hash"):
            raise WorkflowError("legacy successor must preserve the original exact request")
        matches = [row for row in new_receipts if row.get("receipt_type") == "dispatch_sent"
                   and row.get("receipt_id") == source.get("successor_dispatch_receipt_id")]
        if len(matches) != 1:
            raise WorkflowError("actual existing successor dispatch receipt required")
        native_pin = source.get("actual_native_send")
        if native_pin not in matches[0].get("evidence", []):
            raise WorkflowError("successor send pin must already belong to its original dispatch receipt")
        native = _collaboration_native(root, native_pin)
        if native.get("threadId") != matches[0].get("chat_task_id"):
            raise WorkflowError("successor native send must match the existing fixed target")
        owner = str(source.get("recovery_owner") or "")
        if owner not in department_registry(root):
            raise WorkflowError("named registered recovery owner required")
        recheck = _parse_observed_at(source.get("next_check_at"))
        if recheck is None or recheck <= dt.datetime.now(dt.timezone.utc):
            raise WorkflowError("future successor intake recheck required")
        link = {"task_id": task_id, "successor_task_id": successor_task_id,
                "source": source_pin, "actual_native_send": native_pin,
                "successor_dispatch_receipt_id": matches[0]["receipt_id"],
                "recovery_owner": owner, "original_dispatch_sent": False,
                "next_action": "receive_existing_successor_result", "next_check_at": source["next_check_at"],
                "linked_at": utc_timestamp()}
        append_workflow_event(root, task_id, original["current_state"], {"workflow_successor_link": link})
        original["workflow_successor_link"] = link
        original["next_legal_actions"] = ["receive_existing_successor_result:" + successor_task_id]
        atomic_write_json(snapshot_path(root, task_id), original)
        return {**link, "status": "successor_linked"}, [snapshot_path(root, task_id), root / WORKFLOW_EVENTS]


def repair_dispatch_plan(root: Path, task_id: str) -> tuple[dict[str, Any], list[Path]]:
    task_id = validate_task_id(task_id)
    path = snapshot_path(root, task_id)
    if not path.exists():
        reconcile_workflow(root, task_id=task_id)
    with workflow_lock(root):
        snapshot = read_json(path)
        if not snapshot:
            raise WorkflowError("找不到可恢复的工作流")
        snapshot = _repair_dispatch_plan_locked(root, snapshot)
    return {**snapshot, "status": "workflow_plan_repaired" if snapshot["current_state"] == "dispatch_ready"
            else "workflow_plan_still_blocked"}, [path, root / WORKFLOW_EVENTS]


def refresh_workflow_bindings(root: Path, task_id: str) -> tuple[dict[str, Any], list[Path]]:
    """Refresh pre-dispatch fixed thread IDs after a verified department replacement."""

    task_id = validate_task_id(task_id)
    path = snapshot_path(root, task_id)
    with workflow_lock(root):
        snapshot = read_json(path)
        if not snapshot:
            raise WorkflowError(f"工作流不存在：{task_id}")
        if snapshot.get("current_state") != "dispatch_ready":
            raise WorkflowError("固定窗口绑定只可在 dispatch_ready 且尚未派工时刷新")
        receipts, receipt_invalid = _validate_receipt_chain(root, task_id)
        if receipt_invalid:
            raise WorkflowError("回执链无效，禁止刷新固定窗口绑定：" + ", ".join(receipt_invalid))
        if receipts:
            raise WorkflowError("已有工作流回执，禁止改写固定窗口身份")

        registry_document = read_json(root / "data/department-registry.json")
        registry = department_registry(root)
        policy = load_policy(root)
        routing = policy.get("routing_policy", {}) if isinstance(policy, dict) else {}
        expected_project_id = str(routing.get("source_project_id") or "")
        expected_cwd = str(routing.get("source_project_root") or "")
        verification_ttl_hours = int(
            (registry_document.get("health_policy", {}) or {}).get("verification_ttl_hours", 0)
            or routing.get("health_verification_ttl_hours", 0)
            or 0
        )

        refreshed: list[dict[str, Any]] = []
        changes: list[dict[str, str]] = []
        for raw in snapshot.get("departments", []):
            item = dict(raw) if isinstance(raw, dict) else {}
            department = str(item.get("department") or "")
            registered = registry.get(department)
            if not registered:
                raise WorkflowError(f"工作流部门已不在注册表：{department}")
            binding = registered.get("chat_binding", {})
            if not isinstance(binding, dict) or not _chat_binding_healthy(
                binding, verification_ttl_hours=verification_ttl_hours
            ):
                raise WorkflowError(f"固定窗口未通过当前健康门禁：{department}")
            if str(binding.get("project_id") or "") != expected_project_id:
                raise WorkflowError(f"固定窗口项目 ID 不匹配：{department}")
            if not _same_resolved_path(str(binding.get("cwd") or ""), expected_cwd):
                raise WorkflowError(f"固定窗口 cwd 不匹配：{department}")
            new_task_id = str(binding.get("task_id") or "")
            if not new_task_id or not str(binding.get("title") or "") or not str(binding.get("sidebar_section_id") or ""):
                raise WorkflowError(f"固定窗口身份字段不完整：{department}")
            old_task_id = str(item.get("chat_task_id") or "")
            item["chat_task_id"] = new_task_id
            refreshed.append(item)
            if old_task_id != new_task_id:
                changes.append(
                    {
                        "department": department,
                        "old_chat_task_id": old_task_id,
                        "new_chat_task_id": new_task_id,
                    }
                )

        if not changes:
            return {
                "status": "workflow_bindings_current",
                "task_id": task_id,
                "changes": [],
            }, [path, root / WORKFLOW_EVENTS]

        append_workflow_event(
            root,
            task_id,
            "dispatch_ready",
            {
                "binding_refresh": True,
                "departments": refreshed,
                "changes": changes,
            },
        )
        snapshot.update(
            {
                "departments": refreshed,
                "updated_at": utc_timestamp(),
                "event_count": sum(
                    1 for row in read_jsonl(root / WORKFLOW_EVENTS) if row.get("task_id") == task_id
                ),
            }
        )
        atomic_write_json(path, snapshot)
    return {
        "status": "workflow_bindings_refreshed",
        "task_id": task_id,
        "changes": changes,
        "current_state": snapshot.get("current_state"),
    }, [path, root / WORKFLOW_EVENTS]


def rebind_department_after_replacement(
    root: Path, task_id: str, department: str, old_chat_task_id: str, health_event_hash: str
) -> tuple[dict[str, Any], list[Path]]:
    """Preserve prior receipts when an open review moves to a verified fixed window."""

    task_id = validate_task_id(task_id)
    if department not in {"qa", "content-organic-website"}:
        raise WorkflowError("替补后绑定仅支持 QA 或内容/SEO 固定部门")
    path = snapshot_path(root, task_id)
    with workflow_lock(root):
        snapshot = read_json(path)
        state = snapshot.get("current_state") if snapshot else None
        if state not in {"dispatched", "qa_blocked", "evidence_received"}:
            raise WorkflowError("替补绑定只可用于已派工、已有证据或返工中的工作流")
        if state == "dispatched" and department != "content-organic-website":
            raise WorkflowError("未回执派工恢复只支持原内容部门")
        receipts, receipt_invalid = _validate_receipt_chain(root, task_id)
        event_invalid = validate_workflow_events(root, task_id)
        if receipt_invalid or event_invalid:
            raise WorkflowError("事件或回执链无效，禁止替换 QA 绑定")
        department_dispatches = [
            row for row in receipts
            if row.get("receipt_type") == "dispatch_sent" and row.get("department") == department
        ]
        if (state in {"dispatched", "qa_blocked"} and not department_dispatches) or any(
            row.get("chat_task_id") != old_chat_task_id for row in department_dispatches
        ):
            raise WorkflowError("旧部门派工状态与待替换工作流不匹配")
        if state == "dispatched" and any(
            row.get("department") == department
            and row.get("receipt_type") in {"chat_ack", "outbox_received"}
            for row in receipts
        ):
            raise WorkflowError("未回执派工已有部门成功回执，禁止按 dispatched 替补")

        departments = [dict(row) for row in snapshot.get("departments", [])]
        target = next((row for row in departments if row.get("department") == department), None)
        if not target or target.get("chat_task_id") != old_chat_task_id:
            raise WorkflowError("旧部门绑定与工作流快照不匹配")
        registry = department_registry(root)
        binding = registry.get(department, {}).get("chat_binding", {})
        policy = load_policy(root)
        routing = policy.get("routing_policy", {}) if isinstance(policy, dict) else {}
        health_events = read_jsonl(root / "logs/department-health.jsonl")
        historical_qa_pre_dispatch = False
        historical_fixed_rework = False
        historical_unacknowledged_dispatch = False
        if binding.get("replacement_of_task_id") != old_chat_task_id:
            # The registry only retains its latest replacement edge. Recover
            # an older fixed identity only when its historical successful
            # visible reply is hash-verified and the current fixed identity is
            # independently healthy. In QA rework, preserve all old receipts.
            historical_qa_pre_dispatch = (
                department == "qa"
                and snapshot.get("current_state") == "evidence_received"
                and not department_dispatches
            )
            historical_fixed_rework = (
                snapshot.get("current_state") == "qa_blocked"
                and department in {"qa", "content-organic-website"}
                and bool(department_dispatches)
            )
            historical_unacknowledged_dispatch = (
                state == "dispatched"
                and department == "content-organic-website"
                and bool(department_dispatches)
            )
            if not (historical_qa_pre_dispatch or historical_fixed_rework or historical_unacknowledged_dispatch):
                raise WorkflowError("注册表未声明对该旧部门窗口的替换")
            old_health = next((row for row in reversed(health_events)
                if row.get("department") == department
                and row.get("task_id") == old_chat_task_id
                and row.get("project_id") == binding.get("project_id")
                and row.get("title_sha256") == hashlib.sha256(str(binding.get("title") or "").encode("utf-8")).hexdigest()
                and row.get("cwd_sha256") == hashlib.sha256(str(binding.get("cwd") or "").encode("utf-8")).hexdigest()
                and row.get("last_run_status") == "success"
                and row.get("reply_nonempty") is True
                and row.get("event_hash") == sha256_value({key: value for key, value in row.items() if key != "event_hash"})
            ), None)
            if not old_health:
                raise WorkflowError("历史固定部门窗口无可验证健康记录")
        if not _chat_binding_healthy(
            binding, verification_ttl_hours=int(routing.get("health_verification_ttl_hours", 0) or 0)
        ):
            raise WorkflowError("替补部门窗口未通过当前健康门禁")
        if (binding.get("project_id") != routing.get("source_project_id")
                or not _same_resolved_path(str(binding.get("cwd") or ""), str(routing.get("source_project_root") or ""))):
            raise WorkflowError("替补部门项目或目录不匹配")
        health = next(
            (row for row in health_events
             if row.get("event_hash") == health_event_hash), None
        )
        if not health or health.get("event_hash") != sha256_value(
            {key: value for key, value in health.items() if key != "event_hash"}
        ):
            raise WorkflowError("替补部门健康事件不存在或哈希不匹配")
        if any(health.get(key) != value for key, value in {
            "department": department,
            "task_id": binding.get("task_id"),
            "project_id": binding.get("project_id"),
            "sidebar_section_id": binding.get("sidebar_section_id"),
            "last_run_status": "success",
            "reply_nonempty": True,
        }.items()) or health.get("reply_sha256") != binding.get("last_reply_sha256"):
            raise WorkflowError("替补部门健康事件与当前固定窗口不匹配")

        new_chat_task_id = str(binding.get("task_id") or "")
        target["chat_task_id"] = new_chat_task_id
        append_workflow_event(root, task_id, str(snapshot["current_state"]), {
            "binding_refresh": True,
            "replacement_after_dispatch": True,
            "department": department,
            "departments": departments,
            "old_chat_task_id": old_chat_task_id,
            "new_chat_task_id": new_chat_task_id,
            "health_event_hash": health_event_hash,
            "historical_qa_pre_dispatch": historical_qa_pre_dispatch,
            "historical_fixed_rework": historical_fixed_rework,
            "historical_unacknowledged_dispatch": historical_unacknowledged_dispatch,
        })
        snapshot["departments"] = departments
        snapshot["updated_at"] = utc_timestamp()
        snapshot["event_count"] = sum(
            row.get("task_id") == task_id for row in read_jsonl(root / WORKFLOW_EVENTS)
        )
        atomic_write_json(path, snapshot)
    return {
        "status": f"workflow_{department.replace('-', '_')}_binding_replaced",
        "task_id": task_id,
        "old_chat_task_id": old_chat_task_id,
        "new_chat_task_id": new_chat_task_id,
        "current_state": snapshot["current_state"],
    }, [path, root / WORKFLOW_EVENTS]


def rebind_qa_after_replacement(
    root: Path, task_id: str, old_chat_task_id: str, health_event_hash: str
) -> tuple[dict[str, Any], list[Path]]:
    """Compatibility wrapper for existing QA recovery callers."""
    return rebind_department_after_replacement(
        root, task_id, "qa", old_chat_task_id, health_event_hash
    )


def file_digest(root: Path, value: str) -> dict[str, Any]:
    if any(marker in value.casefold() for marker in SENSITIVE_MARKERS):
        raise WorkflowError("证据路径不能指向密码、Token、Cookie、OAuth、私钥或凭据")
    path = safe_path(root, value)
    if not path.exists() or not path.is_file():
        raise WorkflowError(f"证据文件不存在或不是文件：{value}")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return {"path": rel_path(root, path), "sha256": digest.hexdigest(), "size": path.stat().st_size}


def validate_outbox(root: Path, evidence: list[dict[str, Any]], department: str, workflow_task_id: str) -> None:
    json_items = [item for item in evidence if str(item.get("path", "")).endswith(".json")]
    if not json_items:
        raise WorkflowError("outbox_received 至少需要一个 JSON outbox 证据")
    outbox = read_json(root / str(json_items[0]["path"]))
    if not outbox:
        raise WorkflowError("outbox JSON 无法读取")
    if outbox.get("department") != department:
        raise WorkflowError("outbox department 与回执部门不一致")
    outbox_task = str(outbox.get("task_id", ""))
    if not (outbox_task == workflow_task_id or outbox_task.startswith(workflow_task_id + "-")):
        raise WorkflowError("outbox task_id 与工作流任务不一致")
    required = {"status", "conclusion", "evidence", "risks", "next_actions", "handoff", "approval_required"}
    missing = sorted(key for key in required if key not in outbox)
    if missing:
        raise WorkflowError(f"outbox 缺少 V2 必填字段：{', '.join(missing)}")
    learning = outbox.get("learning")
    if not isinstance(learning, dict) or not learning.get("status"):
        raise WorkflowError("outbox 缺少 learning.status（允许明确记录 no_new_learning）")
    if (
        department == "content-organic-website"
        and CONTENT_GROWTH_DAILY_PATTERN.fullmatch(workflow_task_id)
        and str(outbox.get("status", "")).casefold() == "completed"
    ):
        validate_content_growth_daily_output(root, outbox)


def validate_content_growth_daily_output(root: Path, outbox: dict[str, Any]) -> None:
    """Reject a content daily that only reports checks without advancing a growth asset."""
    from goal_delivery_runtime import enabled as goal_enabled
    snapshot = read_json(snapshot_path(root, str(outbox.get("task_id") or "")))
    modern = goal_enabled(root, snapshot)
    handoff_field = "assistant_handoff_status" if modern else "qa_handoff_status"
    matrix = outbox.get("promotion_gap_matrix")
    if not isinstance(matrix, dict):
        raise WorkflowError("内容增长日报 completed 必须包含 promotion_gap_matrix")
    missing_categories = sorted(PROMOTION_GAP_CATEGORIES - set(matrix))
    if missing_categories:
        raise WorkflowError(
            "promotion_gap_matrix 缺少分类：" + ", ".join(missing_categories)
        )

    delivery = outbox.get("growth_delivery")
    if not isinstance(delivery, dict):
        raise WorkflowError("内容增长日报 completed 必须包含 growth_delivery")
    required = {
        "backlog_item_id",
        "previous_status",
        "current_status",
        "artifact_type",
        "artifact_path",
        handoff_field,
    }
    missing = sorted(key for key in required if not str(delivery.get(key, "")).strip())
    if missing:
        raise WorkflowError("growth_delivery 缺少非空字段：" + ", ".join(missing))
    if str(delivery["previous_status"]).strip() == str(delivery["current_status"]).strip():
        raise WorkflowError("内容增长日报不能只检查：growth_delivery 状态必须真实推进")
    expected_status = "ready_for_assistant_acceptance" if modern else "ready_for_qa"
    if str(delivery[handoff_field]).strip() != expected_status:
        raise WorkflowError("内容增长日报 completed 必须把增长资产交到 ready_for_qa")

    artifact_value = str(delivery["artifact_path"]).strip()
    artifact_path = safe_path(root, artifact_value)
    if not artifact_path.exists() or not artifact_path.is_file() or artifact_path.stat().st_size == 0:
        raise WorkflowError("growth_delivery artifact_path 不存在、不是文件或为空")
    evidence_block = outbox.get("evidence")
    if not isinstance(evidence_block, dict) or str(evidence_block.get("growth_artifact", "")).strip() != artifact_value:
        raise WorkflowError("evidence.growth_artifact 必须与 growth_delivery artifact_path 一致")

    handoff = outbox.get("handoff")
    receiver = ""
    if isinstance(handoff, dict):
        receiver = str(handoff.get("receiver") or handoff.get("to") or "").strip()
    expected_receiver = snapshot["goal_delivery"]["responsible_assistant"] if modern else "qa"
    if receiver != expected_receiver:
        raise WorkflowError("内容增长日报 completed 必须明确交接给 qa")


def effective_approvals(root: Path) -> dict[str, dict[str, Any]]:
    approvals: dict[str, dict[str, Any]] = {}
    for row in read_jsonl(root / APPROVAL_LEDGER):
        approval_id = str(row.get("approval_id", ""))
        if approval_id:
            approvals[approval_id] = row
    return approvals


def record_approval(
    root: Path,
    *,
    task_id: str,
    action_id: str,
    action_class: str,
    scope: str,
    approval_id: str = "",
    source_thread_id: str = "",
    source_message_ref: str = "",
    revoke: bool = False,
) -> tuple[dict[str, Any], list[Path]]:
    task_id = validate_task_id(task_id)
    if not action_id.strip() or not action_class.strip() or not scope.strip():
        raise WorkflowError("approval-record 需要精确的 action_id、action_class 和 scope")
    workflow_snapshot = read_json(snapshot_path(root, task_id))
    if not workflow_snapshot:
        raise WorkflowError(f"工作流不存在：{task_id}")
    read_only_account_approval = action_class == "account_read"
    if (
        not revoke
        and not read_only_account_approval
        and workflow_snapshot.get("current_state") != "waiting_owner_approval"
    ):
        raise WorkflowError("批准记录被阻止：工作流必须先通过 QA 并进入 waiting_owner_approval")
    generated_id = approval_id.strip() or "apr-" + sha256_value(
        [task_id, action_id, action_class, scope, source_thread_id, source_message_ref]
    )[:20]
    with workflow_lock(root):
        current_snapshot = read_json(snapshot_path(root, task_id))
        if (
            not revoke
            and not read_only_account_approval
            and current_snapshot.get("current_state") != "waiting_owner_approval"
        ):
            raise WorkflowError("批准记录被阻止：工作流状态在写入前已变更")
        approvals = effective_approvals(root)
        existing = approvals.get(generated_id)
        if revoke:
            if not existing:
                raise WorkflowError(f"找不到待撤销批准：{generated_id}")
            revoke_identity = {
                "task_id": task_id,
                "action_id": action_id,
                "action_class": action_class,
                "scope": scope,
            }
            if any(existing.get(key) != value for key, value in revoke_identity.items()):
                raise WorkflowError("撤销请求与批准的精确动作范围不匹配")
            record = {**existing, "status": "revoked", "changed_at": utc_timestamp()}
        else:
            identity = {
                "task_id": task_id,
                "action_id": action_id,
                "action_class": action_class,
                "scope": scope,
            }
            if existing:
                if any(existing.get(key) != value for key, value in identity.items()):
                    raise WorkflowError("批准编号已绑定不同动作")
                return {**existing, "result": "duplicate_ignored"}, [root / APPROVAL_LEDGER]
            record = {
                "schema_version": "1.0",
                "approval_id": generated_id,
                **identity,
                "granted_by": "owner",
                "granted_at": utc_timestamp(),
                "source_thread_id": source_thread_id,
                "source_message_ref": source_message_ref,
                "status": "active",
                "single_use": True,
                "full_approval_message_stored": False,
            }
        append_jsonl_locked(root / APPROVAL_LEDGER, record)
    result = {**record, "result": "revoked" if revoke else "recorded"}
    return result, [root / APPROVAL_LEDGER]


def load_policy(root: Path) -> dict[str, Any]:
    policy = read_json(root / ACTION_POLICY)
    if not policy:
        raise WorkflowError("data/action-policy.json 不存在或无效")
    return policy


def matching_standing_authorization(
    policy: dict[str, Any], *, department: str, action_class: str, scope: str
) -> dict[str, Any]:
    """Return an active standing authorization only for its exact registered site scope."""

    class_policy = policy.get("action_classes", {}).get(action_class, {})
    if not isinstance(class_policy, dict) or not class_policy.get("standing_owner_authorization_allowed"):
        return {}
    for raw in policy.get("standing_authorizations", []):
        if not isinstance(raw, dict) or raw.get("status") != "active":
            continue
        if raw.get("department") != department or action_class not in raw.get("action_classes", []):
            continue
        prefixes = [str(value) for value in raw.get("allowed_scope_prefixes", []) if str(value)]
        if prefixes and any(scope.startswith(prefix) for prefix in prefixes):
            return raw
    return {}


def _materialize_standing_approval(
    root: Path,
    *,
    authorization: dict[str, Any],
    task_id: str,
    action_id: str,
    action_class: str,
    scope: str,
) -> dict[str, Any]:
    authorization_id = str(authorization.get("authorization_id") or "")
    approval_id = "apr-standing-" + sha256_value(
        [authorization_id, task_id, action_id, action_class, scope]
    )[:20]
    with workflow_lock(root):
        existing = effective_approvals(root).get(approval_id)
        if existing:
            return existing
        approval = {
            "schema_version": "1.1",
            "approval_id": approval_id,
            "task_id": task_id,
            "action_id": action_id,
            "action_class": action_class,
            "scope": scope,
            "granted_by": "owner",
            "granted_at": utc_timestamp(),
            "source_thread_id": "",
            "source_message_ref": str(authorization.get("source_message_ref") or ""),
            "status": "active",
            "single_use": True,
            "full_approval_message_stored": False,
            "approval_basis": "standing_authorization",
            "standing_authorization_id": authorization_id,
        }
        append_jsonl_locked(root / APPROVAL_LEDGER, approval)
    return approval


def _consume_approval(root: Path, approval: dict[str, Any]) -> dict[str, Any]:
    consumed = {**approval, "status": "consumed", "changed_at": utc_timestamp()}
    append_jsonl_locked(root / APPROVAL_LEDGER, consumed)
    return consumed


def _same_resolved_path(left: str, right: str) -> bool:
    if not left or not right or not Path(left).is_absolute() or not Path(right).is_absolute():
        return False
    return Path(left).resolve() == Path(right).resolve()


def _queued_notification_route(root: Path, requested: dict[str, Any]) -> list[str] | None:
    """Admit only a prepared exact-result notice; this is not a work dispatch."""
    scope = requested.get("scope", "")
    sender, task_id = requested.get("sender_department"), requested.get("task_id")
    if scope != f"department_result:{task_id}:{sender}":
        return None
    from result_coordination import notification_plan, result_lane, CoordinationStore
    matches = [row for row in notification_plan(root)["notifications"]
               if row.get("identity", {}).get("task_id") == task_id
               and row.get("identity", {}).get("sender_department") == sender
               and row.get("payload", {}).get("sha256") == requested.get("payload_sha256")]
    # Old historical notification rules keep their exact legacy route only.
    if not matches:
        snapshot = read_json(snapshot_path(root, task_id))
        from goal_delivery_runtime import enabled as goal_enabled
        if not goal_enabled(root, snapshot) and not scheduled_result_source(root, task_id, sender):
            return None
        return ["exact_prepared_result_notification_required"]
    if len(matches) != 1:
        return ["one_exact_result_notification_required"]
    notice = matches[0]
    identity = notice["identity"]
    if any(row.get("event") in {"controller_received", "notification_sent"}
           and _result_identity(row) == tuple(identity[k] for k in ("sender_department", "candidate_version", "result_sha256"))
           for row in _result_handoff_rows(root, task_id)):
        return ["result_already_received_or_notified_no_late_send"]
    route = result_lane(root, identity)
    if route.get("lane") == "legacy_unmapped":
        return ["legacy_result_requires_original_mapping_not_resend"]
    if route.get("lane") == "HQ_knowledge" and route.get("acceptance_proven") is not True:
        return ["accepted_exact_assistant_summary_required"]
    binding = department_registry(root).get(route.get("target_department"), {}).get("chat_binding", {})
    expected = {"target_department": route.get("target_department"),
                "target_thread_id": binding.get("task_id"), "target_thread_title": binding.get("title"),
                "target_project_id": binding.get("project_id"), "target_cwd": binding.get("cwd"),
                "target_sidebar_section_id": binding.get("sidebar_section_id"),
                "action_class": "thread_message", "action_id": "notify-result-" + notice["dedupe_key"]}
    if notice.get("state") != "prepared" or any(requested.get(k) != v for k, v in expected.items()):
        return ["exact_prepared_notification_target_and_action_required"]
    source_binding = department_registry(root).get(sender, {}).get("chat_binding", {})
    if requested.get("source_project_id") != source_binding.get("project_id"):
        return ["notification_original_source_project_required"]
    try:
        if file_digest(root, notice["payload"]["path"]) != notice["payload"]:
            raise WorkflowError("notification payload changed")
        store = CoordinationStore(root)
        try:
            store._lease(identity, route["target_department"], notice["coordinator_owner"], notice["claim"])
        finally:
            store.close()
    except (WorkflowError, ValueError, OSError, KeyError, TypeError) as error:
        return ["notification_exact_current_claim_required:" + str(error)]
    return []


def _routing_precheck(
    root: Path,
    *,
    policy: dict[str, Any],
    departments: dict[str, dict[str, Any]],
    sender_department: str,
    source_project_id: str,
    target_project_id: str,
    target_department: str,
    target_thread_id: str,
    target_thread_title: str,
    target_cwd: str,
    target_sidebar_section_id: str,
    payload_sha256: str,
    action_class: str,
    allow_unhealthy_target_for_quarantine: bool = False,
    task_id: str = "",
    scope: str = "",
    action_id: str = "",
) -> tuple[list[str], list[str]]:
    routing = policy.get("routing_policy", {})
    if not isinstance(routing, dict):
        return ["routing_policy_missing"], ["routing_precheck:exact_live_identity"]
    if action_class == "thread_message":
        notification_route = _queued_notification_route(root, {
            "sender_department": sender_department, "source_project_id": source_project_id,
            "target_project_id": target_project_id, "target_department": target_department,
            "target_thread_id": target_thread_id, "target_thread_title": target_thread_title,
            "target_cwd": target_cwd, "target_sidebar_section_id": target_sidebar_section_id,
            "payload_sha256": payload_sha256, "action_id": action_id, "action_class": action_class,
            "scope": scope, "task_id": task_id})
        if notification_route is not None:
            return notification_route, ["exact_result_notification:current_prepared_claim_and_target"]

    # Native human approval delegates exactly one frozen review message from
    # the actual paid department. No saved controller identity or Ads gate changes.
    if scope in {"owner_paid_final_qa:example-ads-account:v39", "owner_paid_final_qa:example-ads-account:v40"}:
        from owner_paid_final_qa_route import check as check_paid_final_qa
        requested = {"task_id": task_id, "action_id": action_id, "scope": scope,
                     "action_class": action_class, "sender_department": sender_department,
                     "source_project_id": source_project_id, "target_project_id": target_project_id,
                     "target_department": target_department, "target_thread_id": target_thread_id,
                     "target_thread_title": target_thread_title, "target_cwd": target_cwd,
                     "target_sidebar_section_id": target_sidebar_section_id,
                     "payload_sha256": payload_sha256}
        errors = check_paid_final_qa(root, policy, departments, requested, _chat_binding_healthy)
        if errors:
            return errors, ["routing_precheck:owner_paid_final_qa_single_use"]
        # Continue all ordinary project, binding, health and target-mode checks.
        routing = dict(routing, controller_sender_department="paid-growth-data")

    # Exact owner-delegated followthrough preserves the actual assistant sender.
    if scope.startswith("owner_delegated_followthrough:") or scope == "owner_project_handoff:fc-20261007-publisher-three-designated-binding-v1":
        from owner_delegated_publisher_followthrough import check_owner_delegated_followthrough
        requested = {"task_id": task_id, "action_id": action_id, "scope": scope,
                     "action_class": action_class, "sender_department": sender_department,
                     "source_project_id": source_project_id, "target_project_id": target_project_id,
                     "target_department": target_department, "target_thread_id": target_thread_id,
                     "target_thread_title": target_thread_title, "target_cwd": target_cwd,
                     "target_sidebar_section_id": target_sidebar_section_id, "payload_sha256": payload_sha256}
        return check_owner_delegated_followthrough(root, policy=policy, departments=departments,
                                                   requested=requested, validate_receipt_chain=_validate_receipt_chain)

    # One native owner authorization delegates only a frozen R0 publishing
    # preparation message to the actual assistant; no general sender exemption.
    if scope == "owner_delegated_dispatch:fc-20261007-owner-publisher-execution-takeover-v1":
        from owner_delegated_publishing_preparation import check_owner_delegated_preparation
        requested = {"task_id": task_id, "action_id": action_id, "scope": scope,
                     "action_class": action_class, "sender_department": sender_department,
                     "source_project_id": source_project_id, "target_project_id": target_project_id,
                     "target_department": target_department, "target_thread_id": target_thread_id,
                     "target_thread_title": target_thread_title, "target_cwd": target_cwd,
                     "target_sidebar_section_id": target_sidebar_section_id,
                     "payload_sha256": payload_sha256}
        return check_owner_delegated_preparation(
            root, policy=policy, departments=departments, requested=requested,
            validate_receipt_chain=_validate_receipt_chain,
        )

    from goal_delivery_runtime import enabled as goal_enabled, assigned_actor, collaboration_route
    goal_snapshot = read_json(snapshot_path(root, task_id)) if task_id else {}
    if goal_enabled(root, goal_snapshot):
        if action_class == "thread_message" and scope not in goal_snapshot["goal_delivery"]["authorized_scope"]:
            return ["goal_dispatch_scope_outside_contract"], ["goal_delivery:exact_authorized_scope"]
        if action_id == "assign-goal-review:" + task_id:
            contract = goal_snapshot.get("goal_contract")
            if (target_department != goal_snapshot["goal_delivery"]["responsible_assistant"]
                    or not isinstance(contract, dict) or file_digest(root, contract.get("path", "")) != contract
                    or payload_sha256 != contract["sha256"]):
                return ["goal_initial_assistant_assignment_exact_contract_required"], ["goal_delivery:frozen_responsibility_assignment"]
        collaboration = collaboration_route(root, goal_snapshot, {
            "sender_department": sender_department, "source_project_id": source_project_id,
            "target_project_id": target_project_id, "target_department": target_department,
            "target_thread_id": target_thread_id, "target_thread_title": target_thread_title,
            "target_cwd": target_cwd, "target_sidebar_section_id": target_sidebar_section_id,
            "payload_sha256": payload_sha256, "action_id": action_id, "action_class": action_class,
            "scope": scope, "task_id": task_id})
        if collaboration is not None:
            return collaboration, ["goal_delivery:exact_collaboration_binding", "human_authorization:original_scope_only"]

    # An owner-directed project handoff is one exact message, not a new
    # department, publication authority or a general cross-project exemption.
    if action_class == "thread_message" and scope.startswith("owner_project_handoff:"):
        exact = routing.get("owner_directed_code_handoff", {})
        requested = {"task_id": task_id, "action_id": action_id, "scope": scope,
                     "sender_department": sender_department, "source_project_id": source_project_id,
                     "target_project_id": target_project_id, "target_department": target_department,
                     "target_thread_id": target_thread_id, "target_thread_title": target_thread_title,
                     "target_cwd": target_cwd, "target_sidebar_section_id": target_sidebar_section_id,
                     "payload_sha256": payload_sha256}
        failed = ["owner_project_handoff_exact_binding_required"]
        try:
            request_pin = file_digest(root, str(exact.get("request_path") or ""))
            request = read_json(root / request_pin["path"])
            if (exact.get("status") != "approved_single_use"
                    or request_pin["sha256"] != exact.get("request_sha256")
                    or any(request.get(key) != value for key, value in requested.items())
                    or sender_department != "operations"
                    or source_project_id != routing.get("source_project_id")
                    or not _same_resolved_path(str(root.resolve()), str(routing.get("source_project_root") or ""))
                    or target_project_id != "<LOCAL_PROJECT_ID>"
                    or target_thread_id != "<LOCAL_THREAD_ID>"
                    or target_thread_title != "FLASH CAST｜专用开发部｜网站与部门系统"
                    or target_cwd != "<WEBSITE_PROJECT_ROOT>"
                    or target_sidebar_section_id != "threads"
                    or not SHA256_PATTERN.fullmatch(payload_sha256)
                    or not request.get("owner_authorization_ref")
                    or request.get("production_authority_granted") is not False):
                return failed, ["routing_precheck:owner_exact_project_handoff"]
            acceptance_pin = file_digest(root, str(exact.get("control_acceptance_path") or ""))
            accepted = read_json(root / acceptance_pin["path"])
            if file_digest(root, str(request.get("packet_path") or ""))["sha256"] != request.get("packet_sha256"):
                return ["owner_project_handoff_frozen_packet_required"], ["routing_precheck:owner_exact_project_handoff"]
            if (acceptance_pin["sha256"] != exact.get("control_acceptance_sha256")
                    or accepted.get("qa_status") != "PASS_INTERNAL_APPLICATION_ALLOWED"
                    or accepted.get("request_sha256") != request_pin["sha256"]
                    or accepted.get("fixed_qa_thread_id") != departments.get("qa", {}).get("chat_binding", {}).get("task_id")
                    or accepted.get("production_authority_granted") is not False):
                return ["owner_project_handoff_control_acceptance_required"], ["routing_precheck:owner_exact_project_handoff"]
            qa_pin = file_digest(root, str(accepted.get("qa_outbox_path") or ""))
            qa_box = read_json(root / qa_pin["path"])
            chain, invalid_chain = _validate_receipt_chain(root, task_id)
            exact_qa = [row for row in chain if row.get("receipt_id") == accepted.get("qa_receipt_id")
                        and row.get("receipt_type") == "qa_verdict" and row.get("department") == "qa"
                        and row.get("verdict") == "pass" and row.get("action_class") == "analysis"
                        and row.get("action_id") == "qa-owner-directed-code-handoff-control-v1"
                        and row.get("scope") == "project:owner-directed-website-code-handoff-route:single-message:v1"
                        and row.get("chat_task_id") == departments.get("qa", {}).get("chat_binding", {}).get("task_id")]
            if (invalid_chain or len(exact_qa) != 1 or qa_pin["sha256"] != accepted.get("qa_outbox_sha256")
                    or qa_pin not in exact_qa[0].get("evidence", [])
                    or qa_box.get("task_id") != task_id or qa_box.get("department") != "qa"
                    or qa_box.get("risk_level") != "R0" or qa_box.get("production_release_eligible") is not False
                    or qa_box.get("qa_result") != "PASS_INTERNAL_APPLICATION_ALLOWED"
                    or qa_box.get("candidate_sha256") != accepted.get("candidate_sha256")
                    or qa_box.get("candidate_sha256") != file_digest(root, str(accepted.get("candidate_path") or ""))["sha256"]):
                return ["owner_project_handoff_exact_native_control_QA_required"], ["routing_precheck:owner_exact_project_handoff"]
            validate_outbox(root, [qa_pin], "qa", task_id)
            live_pin = file_digest(root, str(request.get("live_identity_path") or ""))
            live = read_json(root / live_pin["path"])
            observed = _parse_observed_at(live.get("observed_at"))
            reply = live.get("completed_target_reply", {})
            reply_time = _parse_observed_at(reply.get("reply_observed_at"))
            now = dt.datetime.now(dt.timezone.utc)
            if (observed is None or not 0 <= (now - observed).total_seconds() <= 300
                    or reply_time is None or not 0 <= (now - reply_time).total_seconds() <= 26 * 3600
                    or reply.get("completed") is not True or reply.get("nonempty") is not True
                    or not SHA256_PATTERN.fullmatch(str(reply.get("reply_sha256") or ""))
                    or reply.get("thread_id") != target_thread_id or reply.get("cwd") != target_cwd):
                return ["owner_project_handoff_fresh_completed_reply_required"], ["routing_precheck:owner_exact_project_handoff"]
            target = [x for x in live.get("threads", []) if x.get("id") == target_thread_id]
            ops_binding = departments.get("operations", {}).get("chat_binding", {})
            source_live = [x for x in live.get("threads", []) if x.get("id") == ops_binding.get("task_id")]
            sections = [x for x in live.get("sections", []) if x.get("sectionId") == "threads"
                        and "codex:project:" + target_project_id in x.get("itemKeys", [])]
            if (len(target) != 1 or len(source_live) != 1 or len(sections) != 1
                    or any(target[0].get(k) != v for k, v in {"projectId": target_project_id,
                        "title": target_thread_title, "cwd": target_cwd, "status": "idle"}.items())
                    or any(source_live[0].get(k) != v for k, v in {"projectId": source_project_id,
                        "title": ops_binding.get("title"), "cwd": str(root.resolve())}.items())):
                return ["owner_project_handoff_live_idle_identity_required"], ["routing_precheck:owner_exact_project_handoff"]
            sent_path = (root / str(request.get("native_send_receipt_path") or "")).resolve()
            attempt_path = (root / str(request.get("native_attempt_receipt_path") or "")).resolve()
            if (not sent_path.is_relative_to(root.resolve()) or sent_path.exists()
                    or not attempt_path.is_relative_to(root.resolve()) or attempt_path.exists()):
                return ["owner_project_handoff_already_sent_or_invalid_receipt_path"], ["routing_precheck:owner_exact_project_handoff"]
            return [], ["routing_precheck:owner_exact_project_handoff", "owner_authorization:exact_message_only"]
        except (WorkflowError, ValueError, TypeError, KeyError, OSError):
            return failed, ["routing_precheck:owner_exact_project_handoff"]

    reasons: list[str] = []
    required_receipts = ["routing_precheck:exact_live_identity"]
    if scope in {"owner_paid_final_qa:example-ads-account:v39", "owner_paid_final_qa:example-ads-account:v40"}:
        required_receipts.append("owner_authorization:paid_final_qa_single_native_message")
    expected_source_project_id = str(routing.get("source_project_id") or "")
    expected_root = str(routing.get("source_project_root") or "")
    expected_sender = str(routing.get("controller_sender_department") or "operations")
    if goal_enabled(root, goal_snapshot) and assigned_actor(root, goal_snapshot, sender_department, scope):
        expected_sender = sender_department
        if sender_department != "operations" and action_class == "thread_message":
            from goal_delivery_runtime import approved_action
            requested = {"sender_department": sender_department, "source_project_id": source_project_id,
                "target_project_id": target_project_id, "target_department": target_department,
                "target_thread_id": target_thread_id, "target_thread_title": target_thread_title,
                "target_cwd": target_cwd, "target_sidebar_section_id": target_sidebar_section_id,
                "payload_sha256": payload_sha256, "action_id": action_id, "action_class": action_class,
                "scope": scope, "task_id": task_id}
            try:
                if approved_action(root, goal_snapshot, requested) is None:
                    reasons.append("goal_assistant_exact_approved_next_message_required")
            except (WorkflowError, ValueError, KeyError, TypeError, OSError):
                reasons.append("goal_assistant_approved_message_bytes_changed")
        sender_binding = departments.get(sender_department, {}).get("chat_binding", {})
        if not _chat_binding_healthy(sender_binding, verification_ttl_hours=int(routing.get("health_verification_ttl_hours", 26))):
            reasons.append("goal_coordinator_health_stale")
    if goal_enabled(root) and departments.get(target_department, {}).get("new_dispatch_enabled") is False:
        reasons.append("retired_role_new_dispatch_disabled")
    self_service_automation_departments = {
        str(item) for item in routing.get("self_service_automation_departments", [])
    }

    self_service_automation = (
        action_class in {"automation_create", "automation_update"}
        and sender_department == target_department
        and sender_department in self_service_automation_departments
    )
    result_rule = routing.get("department_result_notification", {})
    sender_item = departments.get(sender_department, {})
    result_notification = (
        action_class == "thread_message"
        and isinstance(result_rule, dict)
        and result_rule.get("enabled") is True
        and target_department == result_rule.get("target_department") == "operations"
        and sender_department != "operations"
        and str(sender_item.get("mode") or "worker") in result_rule.get("source_modes", [])
        and scope == f"department_result:{task_id}:{sender_department}"
        and action_id.startswith(str(result_rule.get("action_id_prefix") or "notify-operations-"))
    )
    # A cross-thread send can interrupt an active controller between a status
    # check and delivery. Result handoffs now use the durable project inbox.
    if (action_class == "thread_message" and target_department == "operations"
            and sender_department != "operations"
            and scope == f"department_result:{task_id}:{sender_department}"):
        reasons.append("department_result_uses_durable_inbox")
    if sender_department != expected_sender and not self_service_automation and not result_notification:
        reasons.append("routing_sender_must_be_operations_controller")
    if result_notification:
        source_binding = sender_item.get("chat_binding", {})
        if not isinstance(source_binding, dict):
            source_binding = {}
        if source_binding.get("status") != "bound_and_visible":
            reasons.append("result_source_not_bound_and_visible")
        elif not _chat_binding_healthy(
            source_binding,
            verification_ttl_hours=int(routing.get("health_verification_ttl_hours", 0) or 0),
        ):
            reasons.append("result_source_unhealthy_or_dispatch_ineligible")
        if source_binding.get("project_id") != expected_source_project_id:
            reasons.append("blocked_cross_project:result_source_project_id_mismatch")
        if not _same_resolved_path(str(source_binding.get("cwd") or ""), expected_root):
            reasons.append("blocked_cross_project:result_source_cwd_mismatch")
    if not expected_source_project_id or source_project_id != expected_source_project_id:
        reasons.append("source_project_id_mismatch")
    if not _same_resolved_path(str(root.resolve()), expected_root):
        reasons.append("source_project_root_mismatch")
    if not target_project_id or target_project_id != expected_source_project_id:
        reasons.append("blocked_cross_project:target_project_id_mismatch")
    if not _same_resolved_path(target_cwd, expected_root):
        reasons.append("blocked_cross_project:target_cwd_mismatch")

    target_item = departments.get(target_department)
    if not target_item:
        reasons.append("target_department_not_registered")
        binding: dict[str, Any] = {}
    else:
        raw_binding = target_item.get("chat_binding", {})
        binding = raw_binding if isinstance(raw_binding, dict) else {}
    expected_thread_id = str(binding.get("task_id") or "")
    expected_thread_title = str(binding.get("title") or "")
    expected_target_project_id = str(binding.get("project_id") or "")
    expected_target_cwd = str(binding.get("cwd") or "")
    expected_sidebar_section_id = str(binding.get("sidebar_section_id") or "")
    if binding.get("status") != "bound_and_visible":
        reasons.append("target_thread_not_bound_and_visible")
    verification_ttl_hours = int(routing.get("health_verification_ttl_hours", 0) or 0)
    controller_automation_update = (
        action_class == "automation_update"
        and sender_department == "operations"
        and target_department == "operations"
    )
    if not _chat_binding_healthy(
        binding, verification_ttl_hours=verification_ttl_hours
    ) and not (allow_unhealthy_target_for_quarantine or controller_automation_update):
        reasons.append("target_thread_unhealthy_or_dispatch_ineligible")
    if not expected_thread_id or target_thread_id != expected_thread_id:
        reasons.append("target_thread_id_mismatch")
    if not expected_thread_title or target_thread_title != expected_thread_title:
        reasons.append("target_thread_title_mismatch")
    if not expected_target_project_id or target_project_id != expected_target_project_id:
        reasons.append("blocked_cross_project:registry_project_id_mismatch")
    if not _same_resolved_path(expected_target_cwd, expected_root):
        reasons.append("blocked_cross_project:registry_cwd_mismatch")
    if not expected_sidebar_section_id or target_sidebar_section_id != expected_sidebar_section_id:
        reasons.append("target_sidebar_section_id_mismatch")
    target_mode = str(
        target_item.get("mode")
        or ("controller" if target_department == "operations" else "gate" if target_department == "qa" else "worker")
    ) if target_item else ""
    allowed_message_modes = {
        str(item) for item in routing.get("thread_message_target_modes", ["worker", "gate"])
    }
    if (goal_enabled(root, goal_snapshot) and target_department == goal_snapshot["goal_delivery"]["responsible_assistant"]
            and departments.get(target_department, {}).get("coordination_authority", {}).get("routine_decisions") is True):
        allowed_message_modes.add("coordinator")
    if (goal_enabled(root, goal_snapshot) and action_class == "thread_message"
            and sender_department == goal_snapshot["goal_delivery"]["responsible_assistant"]
            and target_department in goal_snapshot["goal_delivery"]["producer_departments"]
            and target_department not in {"operations", sender_department}
            and target_department in {x.get("department") for x in goal_snapshot.get("departments", [])}):
        from goal_delivery_runtime import approved_action
        producer_request = {"sender_department": sender_department, "source_project_id": source_project_id,
            "target_project_id": target_project_id, "target_department": target_department,
            "target_thread_id": target_thread_id, "target_thread_title": target_thread_title,
            "target_cwd": target_cwd, "target_sidebar_section_id": target_sidebar_section_id,
            "payload_sha256": payload_sha256, "action_id": action_id, "action_class": action_class,
            "scope": scope, "task_id": task_id}
        try:
            producer_approved = approved_action(root, goal_snapshot, producer_request) is not None
        except (WorkflowError, ValueError, KeyError, TypeError, OSError):
            producer_approved = False
        if producer_approved:
            allowed_message_modes.add("coordinator")
    if action_class == "thread_message" and target_mode not in allowed_message_modes and not result_notification:
        reasons.append("operations_controller_cannot_be_thread_message_target")
    if result_notification and result_rule.get("requires_original_workflow_assignment"):
        source_workflow = read_json(snapshot_path(root, task_id))
        assigned = any(
            row.get("department") == sender_department
            for row in source_workflow.get("departments", [])
            if isinstance(row, dict)
        )
        if not assigned:
            reasons.append("result_sender_not_assigned_to_original_workflow")
        else:
            receipts, invalid_receipts = _validate_receipt_chain(root, task_id)
            latest_dispatch_index = next(
                (
                    index for index in range(len(receipts) - 1, -1, -1)
                    if receipts[index].get("receipt_type") == "dispatch_sent"
                    and receipts[index].get("department") == sender_department
                    and receipts[index].get("chat_task_id") == source_binding.get("task_id")
                ),
                None,
            )
            current_receipts = receipts[latest_dispatch_index + 1:] if latest_dispatch_index is not None else []
            source_ack = next(
                (
                    row for row in reversed(current_receipts)
                    if row.get("receipt_type") == "chat_ack"
                    and row.get("department") == sender_department
                    and row.get("chat_task_id") == source_binding.get("task_id")
                    and row.get("ack_nonempty") is True
                ),
                None,
            )
            if invalid_receipts or latest_dispatch_index is None or source_ack is None:
                reasons.append("result_source_nonempty_chat_ack_required")
            # The worker writes its V2 result before notifying operations. Requiring
            # operations' outbox_received here would make the notification circular.
            outbox_dir = root / "logs/department-outbox"
            result_outboxes = sorted(outbox_dir.glob(f"{task_id}*.json")) if outbox_dir.is_dir() else []
            prior_outbox_hashes = {
                str(item.get("sha256") or "")
                for row in receipts[:latest_dispatch_index or 0]
                if row.get("receipt_type") == "outbox_received"
                and row.get("department") == sender_department
                for item in row.get("evidence", [])
                if str(item.get("path") or "").endswith(".json")
            }
            try:
                handled_result_hashes = {
                    str(row.get("result_sha256") or "")
                    for row in _result_handoff_rows(root, task_id)
                    if row.get("sender_department") == sender_department
                    and row.get("event") in {"notification_sent", "controller_received"}
                }
            except WorkflowError:
                handled_result_hashes = set()
                reasons.append("result_handoff_ledger_invalid")
            # chat_ack is often recorded after the department has already
            # written its outbox; its ledger timestamp is not the time of the
            # actual nonempty chat reply. Require the result after dispatch,
            # while live reply verification remains a separate caller gate.
            dispatch_at = (
                dt.datetime.fromisoformat(str(receipts[latest_dispatch_index].get("created_at")))
                if latest_dispatch_index is not None else None
            )
            source_result_ready = False
            previously_handled_result = False
            for outbox_path in result_outboxes:
                outbox = read_json(outbox_path)
                if (
                    outbox.get("task_id") != task_id
                    or outbox.get("department") != sender_department
                    or (outbox.get("fixed_chat_task_id") or outbox.get("chat_task_id")) != source_binding.get("task_id")
                    or outbox.get("chat_reply", {}).get("nonempty") is not True
                    or outbox.get("chat_reply", {}).get("in_current_fixed_department_chat") is not True
                    or str(outbox.get("status") or "").lower() in {"", "active", "in_progress", "pending"}
                ):
                    continue
                try:
                    digest = file_digest(root, rel_path(root, outbox_path))
                    validate_outbox(root, [digest], sender_department, task_id)
                except WorkflowError:
                    continue
                if digest["sha256"] in handled_result_hashes:
                    previously_handled_result = True
                    continue
                if (
                    source_ack is None
                    or dispatch_at is None
                    or outbox_path.stat().st_mtime < dispatch_at.timestamp()
                    or digest["sha256"] in prior_outbox_hashes
                ):
                    continue
                source_result_ready = True
                break
            if not source_result_ready:
                reasons.append(
                    "result_already_notified_or_received"
                    if previously_handled_result
                    else "result_source_completed_v2_outbox_required"
                )
    if not SHA256_PATTERN.fullmatch(payload_sha256):
        reasons.append("payload_sha256_required")
    return reasons, required_receipts


def _coordination_responsibility_resume_ready(
    root: Path, snapshot: dict[str, Any], receipts: list[dict[str, Any]], *,
    sender_department: str, target_department: str, target_thread_id: str,
    scope: str, payload_sha256: str,
) -> bool:
    """Recognize an existing prepared-only coordination responsibility.

    Original policy -> native send -> native ACK proves the initial handoff.
    This read-only source check waives only the coordinator's professional
    outbox dependency. It grants no acceptance or production permission.
    """
    from goal_delivery_runtime import restore_goal, validate_goal, _collaboration_native
    try:
        goal = snapshot.get("goal_delivery", {})
        contract = goal.get("coordination_review_contract", {})
        task_id = snapshot["task_id"]
        if (sender_department != "operations" or goal.get("primary_owner") != sender_department
                or goal.get("producer_departments") != [sender_department]
                or goal.get("responsible_assistant") != target_department
                or target_department == sender_department
                or scope not in goal.get("authorized_scope", [])
                or goal.get("required_execution_actions")
                or not SHA256_PATTERN.fullmatch(payload_sha256)
                or contract.get("task_id") != task_id
                or contract.get("producer") != sender_department
                or contract.get("reviewer") != target_department
                or contract.get("not_professional_producer") is not True
                or contract.get("prepared_only") is not True):
            return False
        # Re-read the frozen original contract and its committed event source;
        # mutable snapshot flags alone cannot manufacture this exception.
        events_path = root / WORKFLOW_EVENTS
        events = [json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        if any(not isinstance(row, dict) for row in events) or validate_workflow_events(root, task_id):
            return False
        original_receipts = [json.loads(line) for line in receipts_path(root, task_id).read_text(encoding="utf-8").splitlines() if line.strip()]
        if original_receipts != receipts:
            return False
        restored = restore_goal(root, snapshot)
        _apply_plan_refresh(restored, events, root)
        pin = restored.get("goal_contract")
        if (not isinstance(pin, dict) or pin != snapshot.get("goal_contract")
                or file_digest(root, pin.get("path", "")) != pin
                or not any(row.get("task_id") == task_id and row.get("details", {}).get("goal_contract") == pin
                           for row in events)
                or validate_goal(root, read_json(safe_path(root, pin["path"]))) != goal
                or restored.get("goal_delivery") != goal):
            return False
        fixed = department_registry(root).get(target_department, {}).get("chat_binding", {})
        routing = load_policy(root).get("routing_policy", {})
        if (fixed.get("task_id") != target_thread_id
                or fixed.get("project_id") != routing.get("source_project_id")
                or not _same_resolved_path(str(fixed.get("cwd") or ""), str(root.resolve()))):
            return False
        initial_action = "assign-goal-review:" + task_id
        dispatches = [(i, row) for i, row in enumerate(receipts)
                      if row.get("receipt_type") == "dispatch_sent"
                      and row.get("task_id") == task_id and row.get("department") == target_department
                      and row.get("chat_task_id") == target_thread_id
                      and row.get("action_id") == initial_action and row.get("action_class") == "thread_message"
                      and row.get("scope") == scope]
        if len(dispatches) != 1:
            return False
        di, dispatch = dispatches[0]
        if any(row.get("supersedes_receipt_id") == dispatch["receipt_id"] for row in receipts[di + 1:]):
            return False
        decisions = [row for row in read_jsonl(root / POLICY_DECISIONS)
                     if row.get("decision_id") == dispatch.get("policy_decision_id")]
        expected = {"status": "allow", "routing_status": "routing_allowed", "task_id": task_id,
                    "department": sender_department, "action_class": "thread_message", "action_id": initial_action,
                    "scope": scope, "payload_sha256": pin["sha256"], "target_department": target_department,
                    "target_thread_id": target_thread_id, "target_thread_title": fixed.get("title"),
                    "target_cwd": fixed.get("cwd"), "target_project_id": fixed.get("project_id"),
                    "source_project_id": routing.get("source_project_id"),
                    "target_sidebar_section_id": fixed.get("sidebar_section_id")}
        if len(decisions) != 1 or any(decisions[0].get(k) != v for k, v in expected.items()):
            return False
        policy_at = dt.datetime.fromisoformat(decisions[0]["checked_at"])
        registered_at = dt.datetime.fromisoformat(dispatch["created_at"])
        if policy_at > registered_at:
            return False
        def native_evidence(evidence):
            document = read_json(safe_path(root, evidence.get("path", "")))
            if not any(key in document for key in ("content", "threadId", "thread", "wait", "polls",
                                                    "native_send", "actual_send", "actual_native_send")):
                return {}
            return _collaboration_native(root, evidence)

        sends = [native_evidence(evidence) for evidence in dispatch.get("evidence", [])]
        actual_sends = [native for native in sends if native.get("threadId") == target_thread_id]
        if len(actual_sends) != 1:
            return False
        send = actual_sends[0]
        def received_original_message(turn):
            # Native sends need not expose a timestamp. For a turn that starts
            # before local receipt registration, bind its first received native
            # input to the exact permitted original goal and registered sender.
            # A later input appended to an old health turn is not this ACK.
            items = turn.get("items", [])
            if not isinstance(items, list) or not items or not isinstance(items[0], dict):
                return False
            received = items[0]
            output = received.get("output", {})
            if (received.get("type") != "functionCallOutput" or not received.get("id")
                    or received.get("name") != "send_message_to_thread"
                    or received.get("namespace") != "codex_app" or not isinstance(output, dict)
                    or output.get("truncated") is not False or not isinstance(output.get("text"), str)):
                return False
            message = re.fullmatch(r"<codex_delegation>\s*<source_thread_id>([^<>]+)</source_thread_id>\s*<input>([\s\S]*)</input>\s*</codex_delegation>\s*",
                                   output["text"])
            source = department_registry(root).get(sender_department, {}).get("chat_binding", {})
            return bool(message and message.group(1) == source.get("task_id")
                        and source.get("project_id") == fixed.get("project_id")
                        and _same_resolved_path(str(source.get("cwd") or ""), str(root.resolve()))
                        and message.group(2).encode("utf-8") == safe_path(root, pin["path"]).read_bytes())

        # Receipt registration is an upper bound, not the native send time.
        # A pre-registration turn requires exact native message/turn causality;
        # the old conservative path still handles historical timestamp-less ACKs.
        for ack in receipts[di + 1:]:
            if ack.get("department") != target_department or ack.get("chat_task_id") != target_thread_id:
                continue
            if ack.get("receipt_type") in {"dispatch_sent", "dispatch_failed"}:
                break
            if ack.get("receipt_type") != "chat_ack" or ack.get("ack_nonempty") is not True or ack.get("task_id") != task_id:
                continue
            ack_at = dt.datetime.fromisoformat(ack["created_at"])
            if ack_at < registered_at:
                continue
            for evidence in ack.get("evidence", []):
                native = native_evidence(evidence)
                thread = native.get("thread", {})
                if (thread.get("id") != target_thread_id or thread.get("title") != fixed.get("title")
                        or thread.get("cwd") != fixed.get("cwd")
                        or ("projectId" in thread and thread["projectId"] != fixed.get("project_id"))):
                    continue
                for turn in native.get("turns", []):
                    started = turn.get("startedAt")
                    if (not turn.get("id") or turn.get("status") not in {"inProgress", "completed"}
                            or turn.get("error") or isinstance(started, bool)
                            or not isinstance(started, (int, float))
                            or not policy_at.timestamp() <= started <= ack_at.timestamp()
                            or ("turnId" in send and send["turnId"] != turn["id"])
                            or (started < registered_at.timestamp() and not received_original_message(turn))):
                        continue
                    if any(message.get("type") == "agentMessage" and message.get("id")
                           and isinstance(message.get("text"), str) and message["text"].strip()
                           for message in turn.get("items", []) if isinstance(message, dict)):
                        return True
        return False
    except (WorkflowError, ValueError, TypeError, KeyError, OSError, AttributeError):
        return False


def _ordinary_thread_dispatch_precheck(
    root: Path, *, snapshot: dict[str, Any], task_id: str,
    target_department: str, target_thread_id: str, action_id: str, scope: str,
    sender_department: str = "", payload_sha256: str = "",
) -> list[str]:
    """Reject unreceiptable or already-sent ordinary messages before sending.

    Read the same snapshot and receipt chain used by record_receipt. This
    check creates no workflow, refreshes no binding and grants no authority.
    """
    reasons: list[str] = []
    from original_task_publisher_handover import dispatch_precheck
    reasons.extend(dispatch_precheck(root, snapshot, target_department, target_thread_id, action_id, scope))
    if not snapshot or snapshot.get("task_id") != task_id:
        return ["thread_dispatch_workflow_missing_or_identity_invalid"]
    if snapshot.get("current_state") in TERMINAL_STATES:
        reasons.append("thread_dispatch_workflow_terminal")
    if snapshot.get("workflow_successor_link"):
        reasons.append("thread_dispatch_existing_successor_no_redispatch")
    if snapshot.get("plan_status") != "ready_to_send":
        reasons.append("thread_dispatch_plan_not_ready")
    planned = [item for item in snapshot.get("departments", [])
               if isinstance(item, dict) and item.get("department") == target_department]
    if len(planned) != 1:
        reasons.append("thread_dispatch_target_not_uniquely_planned")
    elif not target_thread_id or planned[0].get("chat_task_id") != target_thread_id:
        reasons.append("thread_dispatch_planned_fixed_chat_mismatch")
    if not action_id or not scope:
        reasons.append("thread_dispatch_exact_action_and_scope_required")
    receipts, invalid = _validate_receipt_chain(root, task_id)
    if invalid:
        reasons.append("thread_dispatch_receipt_chain_invalid")
    from goal_delivery_runtime import enabled as goal_enabled, completion_dependencies
    if goal_enabled(root, snapshot) and len(planned) == 1:
        goal = snapshot["goal_delivery"]
        initial_review_assignment = (target_department == goal["responsible_assistant"]
                                     and action_id == "assign-goal-review:" + task_id and snapshot.get("goal_contract"))
        responsibility_resume = (not invalid and _coordination_responsibility_resume_ready(
            root, snapshot, receipts, sender_department=sender_department,
            target_department=target_department, target_thread_id=target_thread_id,
            scope=scope, payload_sha256=payload_sha256,
        ))
        if not initial_review_assignment:
            for dep in planned[0].get("depends_on", []):
                if responsibility_resume and dep == "operations":
                    continue
                if not any(r.get("receipt_type") == "outbox_received" and r.get("department") == dep for r in receipts):
                    reasons.append("goal_dispatch_dependency_missing:" + dep)
        unmet = completion_dependencies(root, snapshot)
        for dependency in goal["dependencies"]:
            affects = dependency.get("applies_to", [dependency.get("department")])
            if target_department in affects and any(x.startswith("external_dependency:" + dependency.get("id", "") + ":") for x in unmet):
                reasons.append("goal_dispatch_named_dependency_missing:" + dependency["id"])
    decisions = {row.get("decision_id"): row
                 for row in read_jsonl(root / POLICY_DECISIONS)}
    for receipt in receipts:
        if (receipt.get("receipt_type") != "dispatch_sent"
                or receipt.get("department") != target_department
                or receipt.get("chat_task_id") != target_thread_id):
            continue
        # Receipts can describe the delivered work rather than thread_message.
        # Also inspect their referenced routing action; changing a packet hash
        # must not reuse an action already sent successfully.
        decision = decisions.get(receipt.get("policy_decision_id"), {})
        same_receipt_action = (receipt.get("action_id") == action_id
                               and receipt.get("scope") == scope)
        same_routing_action = (
            decision.get("status") == "allow"
            and decision.get("task_id") == task_id
            and decision.get("action_class") == "thread_message"
            and decision.get("target_department") == target_department
            and decision.get("target_thread_id") == target_thread_id
            and decision.get("action_id") == action_id
            and decision.get("scope") == scope
        )
        if same_receipt_action or same_routing_action:
            from original_task_publisher_handover import recoverable_dispatch
            if recoverable_dispatch(root, snapshot, receipts, receipt):
                continue
            reasons.append("thread_dispatch_exact_action_already_sent")
            break
    return reasons


def policy_check(
    root: Path,
    *,
    task_id: str,
    department: str,
    action_id: str,
    action_class: str,
    scope: str,
    approval_id: str = "",
    skill: str = "",
    consume_approval: bool = False,
    source_project_id: str = "",
    target_project_id: str = "",
    target_department: str = "",
    target_thread_id: str = "",
    target_thread_title: str = "",
    target_cwd: str = "",
    target_sidebar_section_id: str = "",
    payload_sha256: str = "",
    target_automation_status: str = "",
    retry_blocked_execution_receipt_id: str = "",
) -> tuple[dict[str, Any], list[Path]]:
    task_id = validate_task_id(task_id)
    policy = load_policy(root)
    departments = department_registry(root)
    department_item = departments.get(department)
    # A separate human-approved Logo channel, pinned to two campaigns and one
    # existing asset. Association still requires the actual fixed QA reply.
    if scope.startswith("owner_paid_logo:example-ads-account:v1:"):
        from owner_paid_logo_policy import check as logo_check
        requested = dict(task_id=task_id, department=department, action_id=action_id,
                         action_class=action_class, scope=scope, skill=skill,
                         consume_approval=consume_approval, source_project_id=source_project_id,
                         target_project_id=target_project_id, target_department=target_department,
                         target_thread_id=target_thread_id, target_thread_title=target_thread_title,
                         target_cwd=target_cwd, target_sidebar_section_id=target_sidebar_section_id,
                         payload_sha256=payload_sha256)
        with workflow_lock(root):
            exact_reasons = logo_check(root, policy, departments, requested, _chat_binding_healthy)
            if any(row.get("status") == "allow" and all(row.get(k) == requested[k]
                   for k in ("task_id", "department", "action_id", "action_class", "scope"))
                   for row in read_jsonl(root / POLICY_DECISIONS)):
                exact_reasons.append("owner_paid_logo_single_use_permit_already_issued")
            allowed = not exact_reasons
            result = {**requested, "status": "allow" if allowed else "deny",
                      "decision_id": "pol-" + sha256_value([requested, utc_timestamp()])[:20],
                      "approval_basis": "owner_exact_paid_logo" if allowed else "not_used",
                      "approval_id": "owner-paid-logo-v1-" + action_id if allowed else "",
                      "approval_status": "consumed" if allowed else "not_used",
                      "routing_status": "routing_allowed" if allowed and action_class == "thread_message"
                                        else "blocked_route_invalid" if action_class == "thread_message" else "not_applicable",
                      "reason": exact_reasons or ["native_owner_exact_logo_channel"],
                      "paid_promotion_enabled": bool(policy.get("paid_promotion_enabled", False)),
                      "exact_logo_exception": allowed, "project_layer_only": True,
                      "checked_at": utc_timestamp()}
            append_jsonl_locked(root / POLICY_DECISIONS, result)
        return result, [root / ACTION_POLICY, root / POLICY_DECISIONS]
    # Human-authorized v42 is a separate bounded completion, not a rewrite of
    # the closed historical planning workflow or a global Ads gate change.
    if scope.startswith("owner_paid_completion:example-ads-account:v42:"):
        from owner_paid_completion_policy import check as completion_check
        requested = dict(task_id=task_id, department=department, action_id=action_id,
                         action_class=action_class, scope=scope, skill=skill,
                         consume_approval=consume_approval, source_project_id=source_project_id,
                         target_project_id=target_project_id, target_department=target_department,
                         target_thread_id=target_thread_id, target_thread_title=target_thread_title,
                         target_cwd=target_cwd, target_sidebar_section_id=target_sidebar_section_id,
                         payload_sha256=payload_sha256)
        with workflow_lock(root):
            exact_reasons = completion_check(root, policy, departments, requested, _chat_binding_healthy)
            if action_class != "local_read" and any(
                row.get("status") == "allow" and all(row.get(k) == requested[k]
                for k in ("task_id", "department", "action_id", "action_class", "scope"))
                for row in read_jsonl(root / POLICY_DECISIONS)
            ):
                exact_reasons.append("owner_paid_completion_single_use_permit_already_issued")
            allowed = not exact_reasons
            result = {**requested, "status": "allow" if allowed else "deny",
                      "decision_id": "pol-" + sha256_value([requested, utc_timestamp()])[:20],
                      "approval_basis": "owner_exact_paid_completion" if allowed else "not_used",
                      "approval_id": "owner-paid-completion-v42-" + action_id if allowed else "",
                      "approval_status": "consumed" if allowed and action_class != "local_read" else "not_used",
                      "routing_status": "routing_allowed" if allowed and action_class in ROUTING_ACTION_CLASSES else
                                        "blocked_route_invalid" if action_class in ROUTING_ACTION_CLASSES else "not_applicable",
                      "reason": exact_reasons or ["native_owner_exact_v42_completion"],
                      "paid_promotion_enabled": bool(policy.get("paid_promotion_enabled", False)),
                      "exact_completion_exception": allowed, "project_layer_only": True,
                      "checked_at": utc_timestamp()}
            append_jsonl_locked(root / POLICY_DECISIONS, result)
        return result, [root / ACTION_POLICY, root / POLICY_DECISIONS]
    reasons: list[str] = []
    required_receipts: list[str] = []
    allow = True
    if not department_item:
        allow = False
        reasons.append("department_not_registered")
    class_policy = policy.get("action_classes", {}).get(action_class)
    if not isinstance(class_policy, dict):
        allow = False
        reasons.append("action_class_not_registered")
    if department == "operations" and action_class in SPECIALIST_ACTION_CLASSES:
        allow = False
        reasons.append("operations_controller_cannot_execute_specialist_delivery")
    if skill and department_item and skill not in department_item.get("approved_subskills", []):
        allow = False
        reasons.append("skill_not_in_department_registry_whitelist")
    cms_goal_context = None
    cms_goal_mode = False
    if action_class == 'cms_write':
        cms_snapshot = read_json(snapshot_path(root, task_id))
        # A frozen modern task stays modern when its switch is disabled.
        # Disabling the runtime must never make historical QA a fallback.
        cms_goal_mode = isinstance(cms_snapshot.get("goal_delivery"), dict)
        if cms_goal_mode:
            from managed_cms_permit_issuer import validate_goal_cms_policy, PermitEvidenceError
            try:
                cms_goal_context = validate_goal_cms_policy(root, task_id, action_id, scope, department, payload_sha256)
                required_receipts.extend(['assistant_acceptance:current_exact_CMS_candidate',
                                          'protected_preview:exact_zero_write',
                                          'owner_authorization:original_exact_single_use'])
            except (WorkflowError, PermitEvidenceError, ValueError, OSError, KeyError, TypeError) as error:
                allow = False
                reasons.append("goal_cms_acceptance_invalid:" + str(error))
        elif department == 'publishing':
        # A new reviewed sparse tuple only removes the registration-only stop.
        # Existing exact QA, fresh protected preview, approval and permit gates remain.
            try:
                from tools.publisher_native_sparse_admission import exact_target_for_action
                sparse_target = exact_target_for_action(root, task_id, action_id, scope)
                if sparse_target is None:
                    from tools.native_publisher_exact_registration import publisher_registration_reason
                    reasons.append(publisher_registration_reason(root, task_id, action_id, scope))
                    allow = False
                else:
                    from original_task_publisher_handover import progress
                    handover = progress(root, task_id, action_id, scope)
                    if not handover or not handover["qa_passed"]:
                        allow = False
                        reasons.append("exact_publisher_native_cycle_and_production_QA_required")
                    required_receipts.extend(['qa_verdict:exact_publisher_sparse_candidate',
                                              'protected_preview:exact_zero_write',
                                              'owner_approval:new_executor_exact_single_use'])
            except (ValueError, OSError, KeyError, TypeError):
                reasons.append('publisher_sparse_admission_evidence_invalid')
                allow = False
    if action_class == "ads_write" and policy.get("paid_promotion_enabled") is False:
        allow = False
        reasons.append("paid_promotion_disabled_hard_gate")
    if action_class == "site_cache_invalidation":
        # Cache repair is not a code/CMS publication and never inherits standing
        # publishing authority. Only a frozen, separately reviewed request can
        # reach the existing single-use approval and QA gates below.
        bindings = (class_policy or {}).get("exact_requests", [])
        binding = next((item for item in bindings if isinstance(item, dict) and all(
            item.get(key) == value for key, value in {
                "task_id": task_id, "action_id": action_id,
                "scope": scope, "department": department,
            }.items()
        )), {})
        request_path = (root / str(binding.get("request_path") or "")).resolve()
        request_valid = bool(binding) and request_path.is_relative_to(root.resolve()) and request_path.is_file()
        if request_valid:
            request_valid = hashlib.sha256(request_path.read_bytes()).hexdigest() == binding.get("request_sha256")
        if not request_valid:
            allow = False
            reasons.append("cache_exact_frozen_request_required")
        else:
            request = read_json(request_path)
            urls = request.get("allowed_urls", [])
            hashes = request.get("expected_sha256_by_url", {})
            if (
                not isinstance(urls, list) or not urls or len(urls) > 50
                or not all(isinstance(url, str) for url in urls)
                or len(set(urls)) != len(urls)
                or not isinstance(hashes, dict) or set(hashes) != set(urls)
                or not all(isinstance(url, str) and re.fullmatch(
                    r"https://flashcast\.com\.my/images/[A-Za-z0-9_./-]+\.webp", url
                ) and ".." not in url and SHA256_PATTERN.fullmatch(str(hashes.get(url) or "")) for url in urls)
            ):
                allow = False
                reasons.append("cache_request_urls_or_expected_hashes_invalid")
    if action_class == "cms_native_read":
        if (task_id == "fc-20260928-keyword-page-answer-implementation-v1"
                and action_id == "read-bathroom-v6-exact-native-projection-20261006"):
            from cms_bathroom_native_read_contract_v1 import policy_reasons as cms_read_reasons
        elif (task_id == "fc-20260928-keyword-page-answer-implementation-v1"
                and action_id == "read-artistic-v7p2-full-array-source-projection-20261007"):
            from cms_artistic_full_array_native_read_contract_v1 import policy_reasons as cms_read_reasons
        elif (task_id == "fc-20260928-keyword-page-answer-implementation-v1"
                and action_id == "read-artistic-v7p2-raw-CAS-five-fields-20261006"):
            from cms_artistic_cas_native_read_contract_v1 import policy_reasons as cms_read_reasons
        elif (task_id == 'fc-20261006-office-answer-cms-source-binding-v1'
                and action_id == 'read-office-Suitable-For-exact-current-source-20261006'):
            from cms_office_source_native_read_contract_v1 import policy_reasons as cms_read_reasons
        elif (task_id == 'fc-20260928-keyword-page-answer-implementation-v1'
                and action_id in ('read-v17-owner-publisher-native-preparation-v2-20261007-source-refresh', 'read-v18-owner-publisher-native-preparation-v2-20261007-source-refresh', 'read-v20-owner-publisher-native-preparation-v2-20261007-source-refresh')):
            from cms_publisher_three_native_read_contract_v1 import policy_reasons as cms_read_reasons
        else:
            from cms_native_read_contract_v2 import policy_reasons as cms_read_reasons
        read_reasons = cms_read_reasons(
            root, class_policy or {}, task_id, action_id, scope, department, payload_sha256
        )
        if read_reasons:
            allow = False
            reasons.extend(read_reasons)
    if action_class == "account_read" and isinstance(class_policy, dict):
        allowed_departments = {
            str(item) for item in class_policy.get("allowed_departments", []) if str(item)
        }
        if allowed_departments and department not in allowed_departments:
            allow = False
            reasons.append("account_read_department_not_allowed")
        allowed_scope_prefixes = [
            str(item) for item in class_policy.get("allowed_scope_prefixes", []) if str(item)
        ]
        if allowed_scope_prefixes and not any(scope.startswith(prefix) for prefix in allowed_scope_prefixes):
            allow = False
            reasons.append("account_read_scope_not_allowed")
    if action_class == "subagent_delegation":
        allow = False
        reasons.append("use_delegation_check_and_delegation_record")
    if action_class == "google_business_profile_write":
        bindings = (class_policy or {}).get("exact_requests", [])
        binding = next((item for item in bindings if isinstance(item, dict) and all(
            item.get(key) == value for key, value in {
                "task_id": task_id, "action_id": action_id, "scope": scope, "department": department,
            }.items()
        )), {})
        request_path = (root / str(binding.get("request_path") or "")).resolve()
        valid = bool(binding) and request_path.is_relative_to(root.resolve()) and request_path.is_file()
        request = {}
        if valid:
            valid = hashlib.sha256(request_path.read_bytes()).hexdigest() == binding.get("request_sha256")
        if valid:
            request = read_json(request_path)
            candidate_path = (root / str(request.get("candidate_path") or "")).resolve()
            valid = (candidate_path.is_relative_to(root.resolve()) and candidate_path.is_file()
                     and hashlib.sha256(candidate_path.read_bytes()).hexdigest() == request.get("candidate_sha256")
                     and payload_sha256 == request.get("candidate_sha256")
                     and scope == request.get("first_scope")
                     and task_id == request.get("original_task_id")
                     and request.get("exact_profile_resource_id") == "00024771737855071264"
                     and request.get("first_allowed_field_request") == (
                         ["description:D01"]
                         if (task_id, action_id, scope) == (
                             "fc-20260927-google-maps-local-growth-v1",
                             "gbp-description-only-exact-before-v4",
                             "google-business-profile:00024771737855071264:description-only:gbp-description-only-v4-exact-before")
                         else ["description:D01", "services:S01,S02,S03,S05,S06,S07,S08,S09"]
                         if (task_id, action_id, scope) == (
                             "fc-20260927-google-maps-local-growth-v1",
                             "gbp-description-and-services-dedup-v3",
                             "google-business-profile:00024771737855071264:description-and-services:gbp-local-growth-fields-v3-service-dedup")
                         else ["description:D01", "services:S01,S02,S03,S04,S05,S06,S07,S08,S09"]))
        if department not in (class_policy or {}).get("allowed_departments", []):
            valid = False
        if not valid:
            allow = False
            reasons.append("gbp_exact_frozen_request_payload_and_field_scope_required")
    quarantine_mode = action_class == "automation_update" and scope.startswith("automation_quarantine:")
    health_probe_mode = (
        action_class == "thread_message"
        and bool(target_department)
        and scope == f"department_health_probe:{target_department}"
    )
    if quarantine_mode and target_automation_status.upper() != "PAUSED":
        allow = False
        reasons.append("automation_quarantine_requires_paused_status")
    if action_class in ROUTING_ACTION_CLASSES:
        routing_reasons, routing_receipts = _routing_precheck(
            root,
            policy=policy,
            departments=departments,
            sender_department=department,
            source_project_id=source_project_id,
            target_project_id=target_project_id,
            target_department=target_department,
            target_thread_id=target_thread_id,
            target_thread_title=target_thread_title,
            target_cwd=target_cwd,
            target_sidebar_section_id=target_sidebar_section_id,
            payload_sha256=payload_sha256,
            action_class=action_class,
            allow_unhealthy_target_for_quarantine=quarantine_mode or health_probe_mode,
            task_id=task_id,
            scope=scope,
            action_id=action_id,
        )
        required_receipts.extend(routing_receipts)
        if action_class == "cross_project_access":
            routing_reasons.append("cross_project_access_hard_deny")
        if routing_reasons:
            allow = False
            reasons.extend(routing_reasons)

    snapshot = read_json(snapshot_path(root, task_id))
    prepared_result_notice = (action_class == "thread_message" and scope == f"department_result:{task_id}:{department}"
                              and action_id.startswith("notify-result-") and not routing_reasons)
    if not snapshot and not prepared_result_notice:
        allow = False
        reasons.append("workflow_not_found")
    from goal_delivery_runtime import enabled as goal_enabled
    # Existing exact health probes and the owner-directed single-message route
    # retain their own gates. A prefix does not waive those routing checks.
    if (action_class == "thread_message" and not health_probe_mode
            and not prepared_result_notice
            and not scope.startswith("owner_project_handoff:")
            and not (goal_enabled(root, snapshot) and target_department in read_json(root / "data/department-registry.json").get("collaboration_bindings", {}) and not routing_reasons)
            and not (scope in {"owner_paid_final_qa:example-ads-account:v39", "owner_paid_final_qa:example-ads-account:v40"} and not routing_reasons)):
        required_receipts.append("dispatch_precheck:planned_fixed_target_and_unsent_action")
        dispatch_reasons = _ordinary_thread_dispatch_precheck(
            root, snapshot=snapshot, task_id=task_id,
            target_department=target_department, target_thread_id=target_thread_id,
            action_id=action_id, scope=scope,
            sender_department=department, payload_sha256=payload_sha256,
        )
        if dispatch_reasons:
            allow = False
            reasons.extend(dispatch_reasons)
    approval: dict[str, Any] = {}
    standing_authorization: dict[str, Any] = {}
    effective_approval_id = approval_id
    qa_risk_level = ""
    retry_receipt_id = retry_blocked_execution_receipt_id.strip()
    retry_requested = bool(retry_receipt_id)
    if retry_requested and (action_class not in EXTERNAL_ACTION_CLASSES or consume_approval):
        allow = False
        reasons.append("blocked_execution_retry_requires_external_action_without_reconsume")
    if (action_class in EXTERNAL_ACTION_CLASSES or action_class == "account_read") and action_class != "site_ci_prepare":
        from goal_delivery_runtime import enabled as goal_enabled, execution_preflight
        goal_preflight = None
        if action_class in EXTERNAL_ACTION_CLASSES and goal_enabled(root, snapshot or {}):
            try:
                from paid_three_page_bounded_cms import MODEL as bounded_model, exact_tuple
                bounded = (cms_goal_context is not None
                           and cms_goal_context.get("acceptance_model") == bounded_model
                           and exact_tuple(task_id, action_id, scope, department, action_class)
                           and all(cms_goal_context.get(k) == v for k, v in {
                               "task_id": task_id, "action_id": action_id, "scope": scope,
                               "department": department, "payload_sha256": payload_sha256}.items()))
                goal_preflight = (cms_goal_context["preflight"] if bounded else
                                  execution_preflight(root, snapshot, action_id, action_class, scope, department))
                qa_risk_level = goal_preflight["risk_level"]
                required_receipts += ["self_check:exact_pass", "facts_backup_rollback:exact_pins",
                                      "assistant_acceptance:bounded_candidate_only" if bounded else
                                      "assistant_acceptance:after_complete_delivery"]
            except WorkflowError as error:
                allow = False
                reasons.append(str(error))
        if cms_goal_mode and cms_goal_context is not None:
            qa_risk_level = cms_goal_context["risk_level"]
        if action_class in EXTERNAL_ACTION_CLASSES and goal_preflight is None and not cms_goal_mode:
            required_receipts.append("qa_verdict:pass")
            receipts = read_jsonl(receipts_path(root, task_id)) if snapshot else []
            exact_cms_qa = False
            if action_class == "cms_write":
                checked, invalid = _validate_receipt_chain(root, task_id)
                exact = [row for row in checked if row.get("receipt_type") == "qa_verdict"
                         and row.get("department") == "qa" and row.get("task_id") == task_id
                         and row.get("action_id") == action_id and row.get("scope") == scope]
                if exact:
                    # Shared task siblings cannot replace this row's latest QA
                    # channel/risk or make an unexecuted exact row disappear.
                    receipts = exact
                    latest = exact[-1]
                    exact_cms_qa = (not invalid and latest.get("verdict") == "pass"
                                    and latest.get("action_class") == "cms_content_candidate"
                                    and latest.get("chat_task_id") == departments.get("qa", {}).get("chat_binding", {}).get("task_id")
                                    and _latest_verified_qa_risk_level(root, task_id, exact) in {"R1", "R2", "R3"})
                    if not exact_cms_qa:
                        allow = False
                        reasons.append("exact_cms_action_qa_invalid")
            qa_risk_level = _latest_verified_qa_risk_level(root, task_id, receipts)
            qa_release_route = _latest_qa_release_route(receipts)
            if action_class == "site_cache_invalidation":
                checked_receipts, invalid = _validate_receipt_chain(root, task_id)
                qa_rows = [row for row in checked_receipts
                           if row.get("receipt_type") == "qa_verdict" and row.get("department") == "qa"]
                qa = qa_rows[-1] if qa_rows else {}
                if invalid or qa_risk_level != "R3" or any(
                    qa.get(key) != value for key, value in {
                        "task_id": task_id, "verdict": "pass", "action_id": action_id,
                        "action_class": "site_cache_candidate", "scope": scope,
                    }.items()
                ):
                    allow = False
                    reasons.append("cache_current_exact_valid_qa_required")
            if action_class == "google_business_profile_write":
                checked_receipts, invalid = _validate_receipt_chain(root, task_id)
                qa_rows = [row for row in checked_receipts if row.get("receipt_type") == "qa_verdict"
                           and row.get("department") == "qa" and row.get("action_id") == action_id
                           and row.get("scope") == scope]
                qa = qa_rows[-1] if qa_rows else {}
                # Risk and candidate must come from this exact latest QA row,
                # never a sibling action or another artifact attached to it.
                qa_risk_level = _latest_verified_qa_risk_level(root, task_id, qa_rows)
                candidate_bound = False
                for evidence in qa.get("evidence", []):
                    if not isinstance(evidence, dict):
                        continue
                    evidence_path = str(evidence.get("path") or "")
                    if not evidence_path.startswith("logs/department-outbox/") or not evidence_path.endswith(".json"):
                        continue
                    try:
                        actual = file_digest(root, evidence_path)
                    except WorkflowError:
                        continue
                    if actual.get("sha256") != evidence.get("sha256") or actual.get("size") != evidence.get("size"):
                        continue
                    outbox = read_json(root / evidence_path)
                    same_qa = all(outbox.get(key) == qa.get(key) for key in
                                  ("task_id", "department", "action_id", "action_class", "scope"))
                    frozen_path = str(request.get("candidate_path") or "")
                    qa_path = str(outbox.get("candidate_path") or "")
                    candidate_bound = (same_qa and outbox.get("risk_level") == "R3"
                                       and bool(request.get("candidate_version"))
                                       and outbox.get("candidate_version") == request.get("candidate_version")
                                       and bool(frozen_path) and bool(qa_path)
                                       and (root / qa_path).resolve() == (root / frozen_path).resolve()
                                       and (root / qa_path).resolve().is_relative_to(root.resolve())
                                       and outbox.get("candidate_sha256") == request.get("candidate_sha256") == payload_sha256)
                    if candidate_bound:
                        break
                if invalid or qa_risk_level != "R3" or not candidate_bound or any(qa.get(key) != value for key, value in {
                    "task_id": task_id, "verdict": "pass", "action_id": action_id,
                    "action_class": "google_business_profile_candidate", "scope": scope,
                    "chat_task_id": departments.get("qa", {}).get("chat_binding", {}).get("task_id"),
                }.items()):
                    allow = False
                    reasons.append("gbp_current_exact_valid_qa_required")
            allowed_states = {"qa_passed", "waiting_owner_approval", "owner_approved", "execution_completed", "verified"}
            if exact_cms_qa:
                allowed_states.add("closed")
                from original_task_publisher_handover import progress
                try:
                    handover_progress = progress(root, task_id, action_id, scope) if department == "publishing" else None
                    if handover_progress and handover_progress["qa_passed"]:
                        allowed_states.add("qa_blocked")
                except (ValueError, KeyError, OSError):
                    allow = False
                    reasons.append("exact_publisher_handover_progress_invalid")
            if retry_requested:
                allowed_states.add("blocked")
            if (snapshot or {}).get("current_state") not in allowed_states:
                allow = False
                reasons.append("qa_pass_and_owner_review_stage_required")
            if qa_release_route and action_class != qa_release_route:
                allow = False
                reasons.append(f"qa_release_route_mismatch:expected_{qa_release_route}")
        approval = effective_approvals(root).get(approval_id, {}) if approval_id else {}
        expected = {
            "task_id": task_id,
            "action_id": action_id,
            "action_class": action_class,
            "scope": scope,
            "status": "consumed" if retry_requested else "active",
        }
        exact_approval_matches = bool(approval) and not any(
            approval.get(key) != value for key, value in expected.items()
        )
        if exact_approval_matches:
            required_receipts.append("owner_approval:consumed_exact_scope" if retry_requested else "owner_approval:exact_scope")
        else:
            if retry_requested:
                allow = False
                reasons.append("blocked_execution_retry_requires_consumed_exact_approval")
            elif qa_risk_level == "R3":
                reasons.append("r3_exact_owner_approval_required")
            if not retry_requested and qa_risk_level != "R3" and action_class != "site_cache_invalidation":
                standing_authorization = matching_standing_authorization(
                    policy,
                    department=department,
                    action_class=action_class,
                    scope=scope,
                )
            if standing_authorization and allow:
                approval = _materialize_standing_approval(
                    root,
                    authorization=standing_authorization,
                    task_id=task_id,
                    action_id=action_id,
                    action_class=action_class,
                    scope=scope,
                )
                effective_approval_id = str(approval.get("approval_id") or "")
                if approval.get("status") != "active":
                    allow = False
                    reasons.append("standing_approval_already_consumed_or_revoked")
                required_receipts.append("owner_approval:standing_scope")
            else:
                if not retry_requested:
                    allow = False
                    reasons.append("exact_active_owner_approval_or_standing_scope_required")

    if action_class == "site_ci_prepare":
        from cms_publisher_three_preview_policy import handles as handles_exact_publisher_preview, evaluate as evaluate_exact_publisher_preview
        if handles_exact_publisher_preview(task_id, action_id):
            stage_reasons = evaluate_exact_publisher_preview(
                root, __import__(__name__), policy, task_id=task_id, department=department,
                action_id=action_id, scope=scope, payload_sha256=payload_sha256,
            )
            if retry_requested or consume_approval or approval_id:
                stage_reasons.append("preview_does_not_consume_or_retry_production_approval")
            if stage_reasons:
                allow = False
                reasons.extend(stage_reasons)
            else:
                qa_risk_level = "R0"
                required_receipts += ["qa_verdict:exact_zero_write_preview_control", "controller_decision:exact_preview_adoption", "preview:dry_run_only_no_permit_no_Save"]
        else:
            # Preparation is an external action with its own exact pre-CI QA;
            # it cannot inherit a production PASS or produce a deploy permission.
            from site_ci_prepare_policy import evaluate as evaluate_ci_preparation
            stage_reasons, authorization = evaluate_ci_preparation(
                root, __import__(__name__), policy, task_id=task_id, department=department,
                action_id=action_id, scope=scope, payload_sha256=payload_sha256,
            )
            if retry_requested:
                stage_reasons.append("ci_prepare_no_blind_write_retry")
            if stage_reasons:
                allow = False
                reasons.extend(stage_reasons)
            elif allow:
                standing_authorization = authorization
                approval = _materialize_standing_approval(
                    root, authorization=authorization, task_id=task_id, action_id=action_id,
                    action_class=action_class, scope=scope,
                )
                effective_approval_id = str(approval.get("approval_id") or "")
                if approval.get("status") != "active":
                    allow = False
                    reasons.append("ci_prepare_exact_stage_approval_consumed_or_revoked")
                qa_risk_level = "R2"
                required_receipts += ["qa_verdict:exact_preparation_only", "lawful_hosting:no_feature_production", "owner_authorization:exact_three_R2_feature_refs"]
    if retry_requested:
        from original_task_publisher_handover import retry_projection
        projected_retry = retry_projection(root, task_id, action_id, scope, retry_receipt_id, approval_id) if department == "publishing" else None
        if projected_retry:
            snapshot = {**snapshot, **{k: projected_retry[k] for k in ("current_state", "blockers", "resume_from")}}
        receipts, invalid = _validate_receipt_chain(root, task_id) if snapshot else ([], ["workflow_not_found"])
        executions = projected_retry["executions"] if projected_retry else [row for row in receipts if row.get("receipt_type") == "execution_result"]
        latest_execution = executions[-1] if executions else {}
        expected_retry = {
            "receipt_id": retry_receipt_id,
            "task_id": task_id,
            "department": department,
            "action_id": action_id,
            "action_class": action_class,
            "scope": scope,
            "approval_id": approval_id,
            "verdict": "blocked",
        }
        prior_decisions = [
            row for row in read_jsonl(root / POLICY_DECISIONS)
            if row.get("decision_id") == latest_execution.get("policy_decision_id")
        ]
        prior_decision = next((row for row in prior_decisions if row.get("status") == "allow"), {})
        expected_prior = {
            "status": "allow", "task_id": task_id, "department": department,
            "action_id": action_id, "action_class": action_class,
            "scope": scope, "approval_id": approval_id,
        }
        prior_completed = any(
            row.get("verdict") != "blocked"
            and row.get("action_id") == action_id
            and row.get("action_class") == action_class
            and row.get("scope") == scope
            and row.get("approval_id") == approval_id
            for row in executions[:-1]
        )
        if (
            invalid
            or (snapshot or {}).get("current_state") != "blocked"
            or (snapshot or {}).get("blockers") != ["execution_result_blocked"]
            or (snapshot or {}).get("resume_from") != "owner_approved"
            or not latest_execution
            or any(latest_execution.get(key) != value for key, value in expected_retry.items())
            or not prior_decision
            or any(prior_decision.get(key) != value for key, value in expected_prior.items())
            or prior_completed
        ):
            allow = False
            reasons.append("blocked_execution_retry_identity_or_evidence_invalid")
        else:
            required_receipts.append("execution_result:blocked_exact_action")

    decision_id = "pol-" + sha256_value(
        [
            task_id, department, action_id, action_class, scope, effective_approval_id,
            source_project_id, target_project_id, target_department, target_thread_id,
            target_thread_title, target_cwd, target_sidebar_section_id, payload_sha256,
            target_automation_status.upper(),
            retry_receipt_id,
            utc_timestamp(),
        ]
    )[:20]
    if allow and consume_approval and approval:
        with workflow_lock(root):
            current = effective_approvals(root).get(str(approval.get("approval_id")), {})
            if current.get("status") != "active":
                allow = False
                reasons.append("approval_already_consumed_or_revoked")
            else:
                approval = _consume_approval(root, current)
    result = {
        "status": "allow" if allow else "deny",
        "decision_id": decision_id,
        "task_id": task_id,
        "department": department,
        "action_id": action_id,
        "action_class": action_class,
        "scope": scope,
        "approval_id": effective_approval_id,
        "approval_status": approval.get("status", "not_used"),
        "approval_basis": "blocked_execution_retry" if retry_requested and allow else approval.get("approval_basis", "single_use_exact" if approval else "not_used"),
        "retry_source_receipt_id": retry_receipt_id,
        "standing_authorization_id": str(standing_authorization.get("authorization_id") or ""),
        "qa_risk_level": qa_risk_level,
        "reason": reasons or ["within_registered_project_local_scope"],
        "required_receipts": required_receipts,
        "routing_status": (
            "not_applicable"
            if action_class not in ROUTING_ACTION_CLASSES
            else "routing_allowed"
            if allow
            else "blocked_cross_project"
            if any("cross_project" in item or "project_id_mismatch" in item or "cwd_mismatch" in item for item in reasons)
            else "blocked_route_invalid"
        ),
        "routing_quarantine_mode": quarantine_mode,
        "routing_health_probe_mode": health_probe_mode,
        "target_automation_status": target_automation_status.upper(),
        "source_project_id": source_project_id,
        "target_project_id": target_project_id,
        "target_department": target_department,
        "target_thread_id": target_thread_id,
        "target_thread_title": target_thread_title,
        "target_cwd": target_cwd,
        "target_sidebar_section_id": target_sidebar_section_id,
        "payload_sha256": payload_sha256.lower(),
        "message_body_stored": False,
        "paid_promotion_enabled": bool(policy.get("paid_promotion_enabled", False)),
        "project_layer_only": True,
        "checked_at": utc_timestamp(),
    }
    if cms_goal_context is not None and cms_goal_context.get("acceptance_model") == "paid_three_page_bounded_cms_candidate_v1":
        result["cms_candidate_acceptance"] = {
            "acceptance_model": cms_goal_context["acceptance_model"],
            "candidate_acceptance_record_id": cms_goal_context["acceptance_receipt_id"],
            "machine_identity": cms_goal_context["preflight"]["machine_identity"]}
    with workflow_lock(root):
        if retry_requested and result["status"] == "allow":
            previous_retry = any(
                row.get("status") == "allow"
                and row.get("retry_source_receipt_id") == retry_receipt_id
                for row in read_jsonl(root / POLICY_DECISIONS)
            )
            from original_task_publisher_handover import retry_projection
            current_exact_retry = retry_projection(root, task_id, action_id, scope, retry_receipt_id, approval_id) if department == "publishing" else None
            if previous_retry or (read_json(snapshot_path(root, task_id)).get("current_state") != "blocked" and not current_exact_retry):
                result["status"] = "deny"
                result["approval_basis"] = "single_use_exact"
                result["reason"] = ["blocked_execution_retry_already_authorized_or_state_changed"]
        append_jsonl_locked(root / POLICY_DECISIONS, result)
    return result, [root / ACTION_POLICY, root / APPROVAL_LEDGER, root / POLICY_DECISIONS]


def _receipt_payload_for_hash(receipt: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in receipt.items() if key not in {"receipt_hash", "result"}}


def _validate_receipt_prerequisite(
    snapshot: dict[str, Any], receipts: list[dict[str, Any]], receipt_type: str, department: str,
    root: Path | None = None,
) -> None:
    if root is not None:
        from original_task_publisher_handover import legacy_context
        snapshot, receipts = legacy_context(root, snapshot, receipts)
    reviewer = _final_qa_department(root, snapshot) if root is not None else "qa"
    latest = _latest_receipts(receipts)
    if receipt_type not in {"dispatch_sent", "dispatch_failed"} and any(
        kind == "dispatch_failed" for kind, _ in latest
    ):
        raise WorkflowError("派工发送失败尚未恢复，不能登记后续成功回执")
    if snapshot.get("plan_status") != "ready_to_send":
        raise WorkflowError("分派计划仍被阻断，不能记录后续回执")
    if receipt_type == "chat_ack":
        dispatch = latest.get(("dispatch_sent", department))
        from goal_delivery_runtime import owner_direct
        direct = root is not None and owner_direct(root, snapshot, department)
        if not dispatch and not direct:
            raise WorkflowError("非法越级：chat_ack 之前必须有同部门 dispatch_sent")
        planned = next(
            (item for item in snapshot.get("departments", []) if item.get("department") == department), {}
        )
        if dispatch and dispatch.get("chat_task_id") != planned.get("chat_task_id"):
            raise WorkflowError("替补窗口必须在当前固定任务重新派工后才能记录 chat_ack")
    from goal_delivery_runtime import review_delegation
    inherited = None
    direct_review = None
    if (root is not None and department == reviewer
            and not any(r.get("department") == reviewer and r.get("receipt_type") in {"dispatch_sent", "dispatch_failed"} for r in receipts)):
        inherited = review_delegation(root, snapshot)
        if not inherited and receipt_type in {"outbox_received", "qa_verdict"}:
            from qa_review_plan import (native_multi_goal_review_context, owner_direct_review_context,
                                        parent_initial_child_review_context)
            direct_review = parent_initial_child_review_context(root, snapshot)
            if direct_review is None:
                direct_review = native_multi_goal_review_context(root, snapshot)
            if direct_review is None:
                direct_review = owner_direct_review_context(root, snapshot)
    if receipt_type == "outbox_received" and ("chat_ack", department) not in latest and not inherited and not direct_review:
        raise WorkflowError("非法越级：outbox_received 之前必须有同部门非空 chat_ack")
    workers = [
        str(item.get("department", ""))
        for item in snapshot.get("departments", [])
        if item.get("department") not in {reviewer, "operations"}
    ]
    if receipt_type == "qa_verdict":
        if department != reviewer:
            raise WorkflowError("QA verdict must come from the exact final reviewer")
        missing = [item for item in workers if ("outbox_received", item) not in latest]
        if missing:
            raise WorkflowError(f"非法越级：QA 前缺少部门 outbox：{', '.join(missing)}")
        qa_dispatches = [
            index for index, row in enumerate(receipts)
            if row.get("receipt_type") == "dispatch_sent" and row.get("department") == reviewer
        ]
        if not qa_dispatches and not inherited and not direct_review:
            raise WorkflowError("非法越级：QA 结论前缺少质检部 dispatch_sent")
        qa_acks = [
            index for index, row in enumerate(receipts)
            if qa_dispatches and index > qa_dispatches[-1]
            and row.get("receipt_type") == "chat_ack"
            and row.get("department") == reviewer
            and row.get("ack_nonempty")
        ]
        if not qa_acks and not inherited and not direct_review:
            raise WorkflowError("非法越级：本次 QA 派工后缺少质检部非空 chat_ack")
        if not any(
            (inherited is not None or direct_review is not None or index > qa_acks[-1])
            and row.get("receipt_type") == "outbox_received"
            and row.get("department") == reviewer
            for index, row in enumerate(receipts)
        ):
            raise WorkflowError("非法越级：本次 QA 回复后缺少质检部 outbox_received")
    if receipt_type == "execution_result":
        from goal_delivery_runtime import enabled as goal_enabled
        qa_pass = any(
            row.get("receipt_type") == "qa_verdict" and row.get("verdict") == "pass"
            for row in receipts
        )
        if not qa_pass and not (root is not None and goal_enabled(root, snapshot)):
            raise WorkflowError("非法越级：execution_result 之前必须有 QA PASS")
    if receipt_type == "postcheck" and not any(row.get("receipt_type") == "execution_result" for row in receipts):
        raise WorkflowError("非法越级：postcheck 之前必须有 execution_result")


def _validate_evidence_replacement(root: Path, receipts: list[dict[str, Any]], receipt: dict[str, Any]) -> None:
    target_id = str(receipt.get("supersedes_receipt_id", ""))
    target = next((row for row in receipts if row.get("receipt_id") == target_id), None)
    if not target:
        raise WorkflowError("evidence_replacement 指向的旧回执不存在")
    if target.get("department") != receipt.get("department"):
        raise WorkflowError("evidence_replacement 必须由原回执所属部门登记")

    changed_paths: set[str] = set()
    for item in target.get("evidence", []):
        path = str(item.get("path", ""))
        try:
            current = file_digest(root, path)
        except WorkflowError:
            raise WorkflowError(f"旧证据仍然缺失，必须先恢复原路径后再登记：{path}")
        if current.get("sha256") != item.get("sha256") or current.get("size") != item.get("size"):
            changed_paths.add(path)
    if not changed_paths:
        raise WorkflowError("目标旧回执当前没有发生证据变化")

    replacement_paths = {str(item.get("path", "")) for item in receipt.get("evidence", [])}
    if replacement_paths != changed_paths:
        raise WorkflowError("evidence_replacement 必须精确覆盖目标回执中全部已变化路径")


def _validate_evidence_archive(receipts: list[dict[str, Any]], receipt: dict[str, Any]) -> None:
    """Preserve a historical evidence version without rebasing its live path."""

    target_id = str(receipt.get("supersedes_receipt_id") or "")
    target = next((row for row in receipts if row.get("receipt_id") == target_id), None)
    if not target or target.get("receipt_type") == "evidence_archive":
        raise WorkflowError("evidence_archive 指向的原回执不存在或不是原始证据回执")
    if target.get("department") != receipt.get("department"):
        raise WorkflowError("evidence_archive 必须由原回执所属部门登记")
    original_path = str(receipt.get("scope") or "")
    originals = [item for item in target.get("evidence", []) if item.get("path") == original_path]
    archive = receipt.get("evidence", [])
    if len(originals) != 1 or len(archive) != 1:
        raise WorkflowError("evidence_archive 必须精确指定一条原证据路径和一个封存文件")
    archived_path = str(archive[0].get("path") or "")
    if not archived_path.startswith("backups/") or archived_path == original_path:
        raise WorkflowError("evidence_archive 封存文件必须位于项目 backups/ 且与活动路径不同")
    if any(archive[0].get(key) != originals[0].get(key) for key in ("sha256", "size")):
        raise WorkflowError("evidence_archive 封存文件与原回执 SHA-256 或大小不匹配")


def record_receipt(root: Path, args: Any) -> tuple[dict[str, Any], list[Path]]:
    task_id = validate_task_id(str(args.task_id))
    receipt_type = str(args.receipt_type)
    if receipt_type not in RECEIPT_TYPES:
        raise WorkflowError(f"未知回执类型：{receipt_type}")
    snapshot = read_json(snapshot_path(root, task_id))
    if not snapshot:
        raise WorkflowError(f"工作流不存在：{task_id}")
    department = str(args.department).strip()
    registry = department_registry(root)
    if department not in registry:
        raise WorkflowError(f"部门未登记：{department}")
    planned = {item.get("department"): item for item in snapshot.get("departments", [])}
    if department not in planned:
        raise WorkflowError(f"部门不在该工作流分派计划中：{department}")
    chat_task_id = str(getattr(args, "chat_task_id", "") or "")
    fixed_task_id = str(registry[department].get("chat_binding", {}).get("task_id") or "")
    if receipt_type in {"dispatch_sent", "dispatch_failed", "chat_ack", "qa_verdict"}:
        if not chat_task_id or chat_task_id != fixed_task_id or chat_task_id != str(planned[department].get("chat_task_id") or ""):
            raise WorkflowError("回执的 chat_task_id 与注册表固定任务不匹配")
    if receipt_type == "chat_ack" and not bool(getattr(args, "ack_nonempty", False)):
        raise WorkflowError("chat_ack 必须明确记录非空聊天回复")
    verdict = str(getattr(args, "verdict", "") or "").lower()
    if receipt_type == "qa_verdict" and verdict not in {"pass", "blocked"}:
        raise WorkflowError("qa_verdict 必须是 pass 或 blocked")

    evidence_values = [item.strip() for item in str(getattr(args, "evidence", "") or "").split(";") if item.strip()]
    evidence = [file_digest(root, value) for value in evidence_values]
    if receipt_type in {"dispatch_failed", "outbox_received", "qa_verdict", "execution_result", "postcheck", "evidence_replacement", "evidence_archive"} and not evidence:
        raise WorkflowError(f"{receipt_type} 必须有可校验的证据文件")
    if receipt_type == "outbox_received":
        validate_outbox(root, evidence, department, task_id)

    idempotency_key = str(args.idempotency_key).strip()
    if not idempotency_key:
        raise WorkflowError("receipt-record 必须提供 --idempotency-key")
    action_id = str(getattr(args, "action_id", "") or "")
    action_class = str(getattr(args, "action_class", "") or "")
    scope = str(getattr(args, "scope", "") or "")
    approval_id = str(getattr(args, "approval_id", "") or "")
    policy_decision_id = str(getattr(args, "policy_decision_id", "") or "")
    supersedes_receipt_id = str(getattr(args, "supersedes_receipt_id", "") or "").strip()
    replacement_reason = str(getattr(args, "replacement_reason", "") or "").strip()
    if receipt_type in {"evidence_replacement", "evidence_archive"}:
        if not supersedes_receipt_id:
            raise WorkflowError(f"{receipt_type} 必须提供 --supersedes-receipt-id")
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{2,80}", replacement_reason):
            raise WorkflowError(f"{receipt_type} 必须提供 3-81 位小写原因代码")
    if receipt_type == "dispatch_sent":
        if not policy_decision_id:
            raise WorkflowError("dispatch_sent 必须引用已放行的 thread_message 路由预检")
        routing_decisions = [
            row
            for row in read_jsonl(root / POLICY_DECISIONS)
            if row.get("decision_id") == policy_decision_id
        ]
        routing_decision = routing_decisions[-1] if routing_decisions else {}
        expected_routing_decision = {
            "status": "allow",
            "task_id": task_id,
            "department": "operations",
            "action_class": "thread_message",
            "target_department": department,
            "target_thread_id": chat_task_id,
            "routing_status": "routing_allowed",
        }
        from goal_delivery_runtime import assigned_actor
        routing_actor = str(routing_decision.get("department") or "")
        if assigned_actor(root, snapshot, routing_actor, str(routing_decision.get("scope") or "")):
            expected_routing_decision["department"] = routing_actor
        # Preserve the real assistant identity on this one frozen preparation
        # decision. Every ordinary dispatch still requires operations as sender.
        if routing_decision.get("department") == "operations-assistant":
            from owner_delegated_publishing_preparation import is_exact_delegated_dispatch_decision
            if is_exact_delegated_dispatch_decision(
                root, policy=load_policy(root), decision=routing_decision, task_id=task_id,
                target_department=department, target_thread_id=chat_task_id,
                action_id=action_id, action_class=action_class, scope=scope,
            ):
                expected_routing_decision["department"] = "operations-assistant"
        if routing_decision.get("department") == "operations-assistant" and scope.startswith("owner_delegated_followthrough:"):
            from owner_delegated_publisher_followthrough import is_exact_followthrough_dispatch_decision
            if is_exact_followthrough_dispatch_decision(root, policy=load_policy(root), decision=routing_decision,
                    task_id=task_id, target_department=department, target_thread_id=chat_task_id,
                    action_id=action_id, action_class=action_class, scope=scope):
                expected_routing_decision["department"] = "operations-assistant"
        if not routing_decision or any(
            routing_decision.get(key) != value
            for key, value in expected_routing_decision.items()
        ):
            raise WorkflowError(
                "dispatch_sent 引用的 policy_decision_id 不存在、未放行或目标任务不匹配"
            )
    if receipt_type == "execution_result":
        if not all([action_id, action_class, scope, policy_decision_id]):
            raise WorkflowError("execution_result 需要 action_id、action_class、scope 和 policy_decision_id")
        if action_class in EXTERNAL_ACTION_CLASSES:
            approval = effective_approvals(root).get(approval_id, {})
            expected = {"task_id": task_id, "action_id": action_id, "action_class": action_class, "scope": scope, "status": "consumed"}
            if not approval or any(approval.get(key) != value for key, value in expected.items()):
                raise WorkflowError("外部执行回执缺少已单次消费的精确批准")
        decisions = [
            row
            for row in read_jsonl(root / POLICY_DECISIONS)
            if row.get("decision_id") == policy_decision_id
        ]
        decision = decisions[-1] if decisions else {}
        expected_decision = {
            "status": "allow",
            "task_id": task_id,
            "department": department,
            "action_id": action_id,
            "action_class": action_class,
            "scope": scope,
        }
        if not decision or any(decision.get(key) != value for key, value in expected_decision.items()):
            raise WorkflowError("execution_result 引用的 policy_decision_id 不存在、未放行或范围不匹配")

    receipt = {
        "schema_version": "1.0",
        "receipt_id": str(uuid.uuid4()),
        "task_id": task_id,
        "receipt_type": receipt_type,
        "department": department,
        "chat_task_id": chat_task_id,
        "ack_nonempty": bool(getattr(args, "ack_nonempty", False)),
        "verdict": verdict,
        "evidence": evidence,
        "idempotency_key": idempotency_key,
        "action_id": action_id,
        "action_class": action_class,
        "scope": scope,
        "approval_id": approval_id,
        "policy_decision_id": policy_decision_id,
        "supersedes_receipt_id": supersedes_receipt_id,
        "replacement_reason": replacement_reason,
        "created_at": utc_timestamp(),
        "chat_body_stored": False,
    }
    # This exact first-send route can complete within one second. Preserve
    # real append order without changing legacy clocks or historical receipts.
    if any(action.get("parent_initial_dispatch") for action in snapshot.get("goal_delivery", {}).get("approved_actions", [])):
        receipt["created_at"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="microseconds")
    path = receipts_path(root, task_id)
    with workflow_lock(root):
        receipts = read_jsonl(path)
        candidates = [row for row in receipts if row.get("idempotency_key") == idempotency_key]
        if candidates:
            existing = candidates[-1]
            comparable_keys = {
                "task_id", "receipt_type", "department", "chat_task_id", "ack_nonempty",
                "verdict", "evidence", "idempotency_key", "action_id", "action_class",
                "scope", "approval_id", "policy_decision_id", "supersedes_receipt_id",
                "replacement_reason", "chat_body_stored",
            }
            if any(existing.get(key) != receipt.get(key) for key in comparable_keys):
                raise WorkflowError("幂等键已绑定不同回执内容")
            return {**existing, "result": "duplicate_ignored"}, [path, snapshot_path(root, task_id)]

        from original_task_publisher_handover import validate_new_receipt
        handover_receipt = validate_new_receipt(root, snapshot, receipts, receipt)
        if handover_receipt:
            if snapshot.get("plan_status") != "ready_to_send":
                raise WorkflowError("分派计划仍被阻断，不能记录后续回执")
            _, handover_invalid = _validate_receipt_chain(root, task_id)
            if handover_invalid:
                raise WorkflowError("精确接管回执链无效，不能追加")
            if receipt_type == "dispatch_failed" and not re.fullmatch(r"[a-z0-9][a-z0-9_-]{2,80}", replacement_reason):
                raise WorkflowError("派工失败更正必须提供原因代码")
        else:
            _validate_receipt_prerequisite(snapshot, receipts, receipt_type, department, root=root)
        if receipt_type == "dispatch_sent":
            from parent_initial_dispatch import validate_sent
            parent_initial = validate_sent(root, snapshot, receipt, routing_decision)
            if parent_initial:
                receipt["parent_initial_dispatch"] = parent_initial
        if receipt_type == "evidence_replacement":
            _validate_evidence_replacement(root, receipts, receipt)
        if receipt_type == "evidence_archive":
            _validate_evidence_archive(receipts, receipt)
        if receipt_type == "qa_verdict":
            from qa_review_plan import validate_verdict
            validate_verdict(root, snapshot, receipts, receipt)
        if receipt_type == "dispatch_failed" and not handover_receipt:
            _, invalid = _validate_receipt_chain(root, task_id)
            if invalid:
                raise WorkflowError("回执链损坏，不能追加派工失败更正")
            sent = _latest_receipts(receipts).get(("dispatch_sent", department), {})
            if not sent or sent.get("receipt_id") != supersedes_receipt_id:
                raise WorkflowError("派工失败更正必须精确引用同部门最新 dispatch_sent")
            if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{2,80}", replacement_reason):
                raise WorkflowError("派工失败更正必须提供原因代码")
            sent_index = next(i for i, row in enumerate(receipts) if row.get("receipt_id") == supersedes_receipt_id)
            if any(row.get("receipt_type") not in {"dispatch_sent", "dispatch_failed"}
                   for row in receipts[sent_index + 1:]):
                raise WorkflowError("派工已有后续回执，不能事后更正为未发送")

        receipt["previous_hash"] = str(receipts[-1].get("receipt_hash", "")) if receipts else ""
        receipt["receipt_hash"] = sha256_value(_receipt_payload_for_hash(receipt))
        append_jsonl_locked(path, receipt)
    reconcile, artifacts = reconcile_workflow(root, task_id=task_id, shadow=False)
    return {**receipt, "result": "recorded", "workflow_state": reconcile.get("current_state")}, [path, *artifacts]


def _validate_receipt_chain(root: Path, task_id: str, *, through_receipt_id: str | None = None) -> tuple[list[dict[str, Any]], list[str]]:
    """Validate the full chain by default, or one exact original receipt prefix.

    A review's original producer provenance must not recurse through its own
    later QA verdict. Prefix selection never grants acceptance or permission.
    """
    receipts = read_jsonl(receipts_path(root, task_id))
    if through_receipt_id is not None:
        if not isinstance(through_receipt_id, str) or not through_receipt_id:
            return [], ["receipt_prefix_id_required"]
        try:
            receipts = [json.loads(line) for line in receipts_path(root, task_id).read_text(encoding="utf-8").splitlines() if line.strip()]
        except (OSError, ValueError, UnicodeError):
            return [], ["receipt_prefix_source_unreadable"]
        if any(not isinstance(row, dict) for row in receipts):
            return [], ["receipt_prefix_source_not_object"]
        matches = [index for index, row in enumerate(receipts) if row.get("receipt_id") == through_receipt_id]
        if len(matches) != 1:
            return [], ["receipt_prefix_id_not_unique"]
        receipts = receipts[:matches[0] + 1]
    invalid: list[str] = []
    replacements: dict[tuple[str, str], list[tuple[int, dict[str, Any], dict[str, Any]]]] = {}
    archives: dict[tuple[str, str], list[tuple[int, dict[str, Any]]]] = {}
    for index, receipt in enumerate(receipts, start=1):
        target_id = str(receipt.get("supersedes_receipt_id", ""))
        if receipt.get("receipt_type") == "evidence_archive" and target_id:
            archive_evidence = receipt.get("evidence") or []
            if len(archive_evidence) != 1:
                invalid.append(f"receipt_{index}:archive_evidence_count_invalid")
                continue
            archives.setdefault((target_id, str(receipt.get("scope") or "")), []).append(
                (index, archive_evidence[0])
            )
        if receipt.get("receipt_type") != "evidence_replacement" or not target_id:
            continue
        for evidence in receipt.get("evidence", []):
            replacements.setdefault((target_id, str(evidence.get("path", ""))), []).append(
                (index, receipt, evidence)
            )

    def has_archive(receipt_id: str, path: str, expected: dict[str, Any], after_index: int) -> bool:
        return any(
            archive_index > after_index
            and archived.get("sha256") == expected.get("sha256")
            and archived.get("size") == expected.get("size")
            for archive_index, archived in archives.get((receipt_id, path), [])
        )

    def has_current_replacement(
        receipt_id: str,
        path: str,
        current: dict[str, Any],
        after_index: int,
        visited: set[str] | None = None,
    ) -> bool:
        """Accept the newest matching evidence across an append-only replacement chain."""

        seen = set(visited or set())
        if receipt_id in seen:
            return False
        seen.add(receipt_id)
        for replacement_index, replacement_receipt, replacement_evidence in replacements.get(
            (receipt_id, path), []
        ):
            if replacement_index <= after_index:
                continue
            if (
                current.get("sha256") == replacement_evidence.get("sha256")
                and current.get("size") == replacement_evidence.get("size")
            ):
                return True
            replacement_id = str(replacement_receipt.get("receipt_id", ""))
            if replacement_id and has_archive(
                replacement_id, path, replacement_evidence, replacement_index
            ):
                return True
            if replacement_id and has_current_replacement(
                replacement_id,
                path,
                current,
                replacement_index,
                seen,
            ):
                return True
        return False

    previous = ""
    review_snapshot = read_json(snapshot_path(root, task_id)) or {"task_id": task_id}
    from original_task_publisher_handover import binding, validate_new_receipt
    handover = binding(root, task_id, receipts)
    for index, receipt in enumerate(receipts, start=1):
        if handover is not None and index > handover["receipt_start"]:
            try:
                validate_new_receipt(root, review_snapshot, receipts[:index-1], receipt)
            except (ValueError, KeyError, OSError) as error:
                invalid.append(f"receipt_{index}:publisher_handover_invalid:{error}")
        if receipt.get("receipt_type") == "qa_verdict":
            try:
                from qa_review_plan import validate_verdict
                validate_verdict(root, review_snapshot, receipts[:index - 1], receipt)
            except (WorkflowError, ValueError, KeyError, OSError) as exc:
                invalid.append(f"receipt_{index}:exact_review_invalid:{exc}")
        if receipt.get("previous_hash", "") != previous:
            invalid.append(f"receipt_{index}:previous_hash_mismatch")
        calculated = sha256_value(_receipt_payload_for_hash(receipt))
        if receipt.get("receipt_hash") != calculated:
            invalid.append(f"receipt_{index}:receipt_hash_mismatch")
        for evidence in receipt.get("evidence", []):
            try:
                current = file_digest(root, str(evidence.get("path", "")))
            except WorkflowError:
                invalid.append(f"receipt_{index}:evidence_missing:{evidence.get('path', '')}")
                continue
            if current.get("sha256") != evidence.get("sha256") or current.get("size") != evidence.get("size"):
                if not has_archive(
                    str(receipt.get("receipt_id", "")),
                    str(evidence.get("path", "")),
                    evidence,
                    index,
                ) and not has_current_replacement(
                    str(receipt.get("receipt_id", "")),
                    str(evidence.get("path", "")),
                    current,
                    index,
                ):
                    invalid.append(f"receipt_{index}:evidence_changed:{evidence.get('path', '')}")
        previous = str(receipt.get("receipt_hash", ""))
    return receipts, invalid


def _latest_receipts(receipts: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    result: dict[tuple[str, str], dict[str, Any]] = {}
    for receipt in receipts:
        kind, department = str(receipt.get("receipt_type", "")), str(receipt.get("department", ""))
        if kind == "dispatch_failed":
            result.pop(("dispatch_sent", department), None)
        elif kind == "dispatch_sent":
            result.pop(("dispatch_failed", department), None)
        result[(kind, department)] = receipt
    return result


def _latest_qa_release_route(receipts: list[dict[str, Any]]) -> str:
    """Return the exact publication channel approved by the latest passing QA receipt."""

    qa_receipts = [
        row
        for row in receipts
        if row.get("receipt_type") == "qa_verdict"
        and row.get("department") == "qa"
        and row.get("verdict") == "pass"
    ]
    if not qa_receipts:
        return ""
    qa = qa_receipts[-1]
    scope = str(qa.get("scope") or "")
    action_class = str(qa.get("action_class") or "")
    if not scope.startswith("flashcast.com.my:"):
        return ""
    return RELEASE_CANDIDATE_ACTION_ROUTES.get(action_class, "")


def _latest_verified_qa_risk_level(
    root: Path, task_id: str, receipts: list[dict[str, Any]]
) -> str:
    """Read risk only from the latest passing QA receipt's unchanged outbox evidence."""

    qa_receipts = [
        row for row in receipts
        if row.get("receipt_type") == "qa_verdict" and row.get("department") == "qa"
    ]
    if not qa_receipts or qa_receipts[-1].get("verdict") != "pass":
        return ""
    qa = qa_receipts[-1]
    for evidence in qa.get("evidence", []):
        if not isinstance(evidence, dict):
            continue
        evidence_path = str(evidence.get("path") or "")
        if not evidence_path.startswith("logs/department-outbox/") or not evidence_path.endswith(".json"):
            continue
        try:
            actual = file_digest(root, evidence_path)
        except WorkflowError:
            continue
        if actual.get("sha256") != evidence.get("sha256") or actual.get("size") != evidence.get("size"):
            continue
        outbox = read_json(root / evidence_path)
        if any(
            outbox.get(key) != expected
            for key, expected in {
                "task_id": task_id,
                "department": "qa",
                "action_id": qa.get("action_id"),
                "action_class": qa.get("action_class"),
                "scope": qa.get("scope"),
            }.items()
        ):
            continue
        risk_level = str(outbox.get("risk_level") or "").upper()
        if risk_level in {"R0", "R1", "R2", "R3"}:
            return risk_level
    return ""


def _workflow_requires_external_execution(
    snapshot: dict[str, Any], receipts: list[dict[str, Any]]
) -> bool:
    if snapshot.get("owner_approval_required"):
        return True
    if _latest_qa_release_route(receipts):
        return True
    return any(row.get("receipt_type") == "execution_result" for row in receipts)


def _derive_state(root: Path, snapshot: dict[str, Any], receipts: list[dict[str, Any]]) -> dict[str, Any]:
    from original_task_publisher_handover import legacy_context
    snapshot, receipts = legacy_context(root, snapshot, receipts)
    reviewer = _final_qa_department(root, snapshot)
    departments = [str(item.get("department", "")) for item in snapshot.get("departments", [])]
    workers = [item for item in departments if item not in {reviewer, "operations"}]
    if not workers:
        workers = [item for item in departments if item != reviewer] or departments
    latest = _latest_receipts(receipts)
    failed = [department for kind, department in latest if kind == "dispatch_failed"]
    if failed:
        prior = [row for row in read_jsonl(root / WORKFLOW_EVENTS)
                 if row.get("task_id") == snapshot.get("task_id")
                 and row.get("state") not in EXCEPTION_STATES]
        return {"state": "blocked", "missing": [f"dispatch_sent:{item}" for item in failed],
                "blockers": [f"dispatch_failed:{item}" for item in failed],
                "next": ["recover_same_fixed_thread_then_policy_check_and_send"],
                "resume_from": prior[-1]["state"] if prior else "dispatch_ready"}
    missing: list[str] = []
    blockers: list[str] = []
    state = "dispatch_ready"
    next_actions = ["receipt-record:dispatch_sent"]

    from goal_delivery_runtime import owner_direct, enabled as goal_enabled
    missing_dispatch = [item for item in workers if ("dispatch_sent", item) not in latest and not owner_direct(root, snapshot, item)]
    if missing_dispatch:
        missing.extend(f"dispatch_sent:{item}" for item in missing_dispatch)
        return {"state": state, "missing": missing, "blockers": blockers, "next": next_actions}
    state = "dispatched"
    next_actions = ["receipt-record:chat_ack"]

    missing_ack = [item for item in workers if ("chat_ack", item) not in latest or not latest[("chat_ack", item)].get("ack_nonempty")]
    if missing_ack:
        missing.extend(f"chat_ack_nonempty:{item}" for item in missing_ack)
        return {"state": state, "missing": missing, "blockers": blockers, "next": next_actions}
    state = "acknowledged"
    next_actions = ["receipt-record:outbox_received"]

    missing_outbox = [item for item in workers if ("outbox_received", item) not in latest]
    if missing_outbox:
        missing.extend(f"outbox_received:{item}" for item in missing_outbox)
        return {"state": state, "missing": missing, "blockers": blockers, "next": next_actions}
    state = "evidence_received"
    next_actions = ["receipt-record:qa_verdict"]

    qa_receipts = [row for row in receipts if row.get("receipt_type") == "qa_verdict" and row.get("department") == reviewer]
    if not qa_receipts:
        missing.append(f"qa_verdict:{reviewer}")
        return {"state": state, "missing": missing, "blockers": blockers, "next": next_actions}
    qa = qa_receipts[-1]
    if qa.get("verdict") == "blocked":
        return {"state": "qa_blocked", "missing": [], "blockers": ["qa_verdict_blocked"], "next": ["repair_and_resubmit_qa"]}
    state = "qa_passed"
    if goal_enabled(root, snapshot):
        from goal_delivery_runtime import completion_dependencies
        unmet_dependencies = completion_dependencies(root, snapshot)
        if unmet_dependencies:
            return {"state": "qa_passed", "missing": unmet_dependencies, "blockers": [],
                    "next": ["collect_exact_dependency_or_collaboration_result"]}
        declared = snapshot["goal_delivery"].get("required_execution_actions", [])
        preflights = snapshot["goal_delivery"].get("execution_preflights", [])
        for action in declared:
            if not any(all(item.get(k) == action.get(k) for k in ("department", "action_id", "action_class", "scope")) for item in preflights):
                return {"state": "qa_passed", "missing": ["production_preflight:" + action["action_id"]],
                        "blockers": [], "next": ["register_exact_production_self_check"]}
        for item in snapshot["goal_delivery"].get("execution_preflights", []):
            execution = [r for r in receipts if r.get("receipt_type") == "execution_result"
                         and all(r.get(k) == item.get(k) for k in ("department", "action_id", "action_class", "scope"))]
            postcheck = [r for r in receipts if r.get("receipt_type") == "postcheck" and r.get("verdict") == "pass"
                         and all(r.get(k) == item.get(k) for k in ("department", "action_id", "action_class", "scope"))]
            if not execution or execution[-1].get("verdict") == "blocked" or not postcheck:
                return {"state": "qa_passed", "missing": ["exact_execution_and_postcheck:" + item["action_id"]],
                        "blockers": [], "next": ["continue_exact_authorized_execution"]}
        return {"state": "closed", "missing": [], "blockers": [], "next": []}
    # A workflow may contain several independently QA-approved CMS rows. A
    # completed action must not close a different, still-unexecuted action.
    qa_action = str(qa.get("action_id") or "")
    qa_scope = str(qa.get("scope") or "")
    qa_write_class = RELEASE_CANDIDATE_ACTION_ROUTES.get(str(qa.get("action_class") or ""), "")
    external_execution_required = _workflow_requires_external_execution(snapshot, receipts)
    if not external_execution_required:
        return {"state": "closed", "missing": [], "blockers": [], "next": []}

    qa_risk_level = _latest_verified_qa_risk_level(root, str(snapshot.get("task_id") or ""), receipts)
    approvals = [
        row for row in effective_approvals(root).values()
        if row.get("task_id") == snapshot.get("task_id")
        and row.get("status") in {"active", "consumed"}
        and (not qa_action or row.get("action_id") == qa_action)
        and (not qa_action or not qa_scope or row.get("scope") == qa_scope)
        and (not qa_action or not qa_write_class or row.get("action_class") == qa_write_class)
        and not (qa_risk_level == "R3" and row.get("approval_basis") == "standing_authorization")
    ]
    if not approvals:
        if snapshot.get("owner_approval_required"):
            missing.append("owner_approval:exact_action_scope")
            return {
                "state": "waiting_owner_approval",
                "missing": missing,
                "blockers": blockers,
                "next": ["approval-record"],
            }
        return {
            "state": "qa_passed",
            "missing": [],
            "blockers": blockers,
            "next": ["policy-check:standing_authorization"],
        }
    state = "owner_approved"
    next_actions = ["policy-check:consume-approval", "receipt-record:execution_result"]

    executions = [
        row for row in receipts if row.get("receipt_type") == "execution_result"
        and (not qa_action or row.get("action_id") == qa_action)
        and (not qa_action or not qa_scope or row.get("scope") == qa_scope)
        and (not qa_action or not qa_write_class or row.get("action_class") == qa_write_class)
    ]
    if not executions:
        missing.append("execution_result")
        return {"state": state, "missing": missing, "blockers": blockers, "next": next_actions}
    latest_execution = executions[-1]
    if latest_execution.get("verdict") == "blocked":
        return {
            "state": "blocked",
            "missing": [],
            "blockers": ["execution_result_blocked"],
            "next": ["resolve_execution_blocker_and_retry"],
            "resume_from": "owner_approved",
        }
    state = "execution_completed"
    next_actions = ["receipt-record:postcheck"]
    successful_executions = [
        row for row in receipts
        if row.get("receipt_type") == "execution_result"
        # Early V2 execution receipts omitted verdict; the existing state
        # machine treated every non-blocked execution as completed.
        and row.get("verdict") in {"", "pass"}
    ]
    latest_execution_index = next(
        index for index in range(len(receipts) - 1, -1, -1)
        if receipts[index] is latest_execution
    )
    postchecks = [
        row for index, row in enumerate(receipts)
        if row.get("receipt_type") == "postcheck"
        and index > latest_execution_index
        and (
            (row.get("action_id") == latest_execution.get("action_id")
             and row.get("action_class") == latest_execution.get("action_class")
             and row.get("scope") == latest_execution.get("scope"))
            or (
                # Legacy releases wrote an unscoped postcheck. It is safe to
                # bind only when there is exactly one successful execution in
                # this workflow and the same department checked it afterwards.
                not row.get("action_id") and not row.get("action_class")
                and not row.get("scope") and row.get("department") == latest_execution.get("department")
                and len(successful_executions) == 1
                and successful_executions[0] is latest_execution
                and index > latest_execution_index
            )
        )
    ]
    if not postchecks:
        missing.append("postcheck")
        return {"state": state, "missing": missing, "blockers": blockers, "next": next_actions}
    if postchecks[-1].get("verdict") == "blocked":
        return {
            "state": "blocked",
            "missing": [],
            "blockers": ["postcheck_blocked"],
            "next": ["repair_postcheck_failure_and_resubmit_qa"],
            "resume_from": "execution_completed",
        }
    return {"state": "closed", "missing": [], "blockers": [], "next": []}


def _state_sequence(
    previous: str,
    target: str,
    owner_approval_required: bool = True,
    external_execution_required: bool = True,
) -> list[str]:
    sequence = ["planned", "dispatch_ready", "dispatched", "acknowledged", "evidence_received", "qa_passed"]
    if external_execution_required:
        if owner_approval_required:
            sequence.append("waiting_owner_approval")
        sequence.extend(["owner_approved", "execution_completed"])
    sequence.extend(["verified", "closed"])
    if target in {"qa_blocked", "blocked_evidence_invalid", "blocked"}:
        return [target] if previous != target else []
    try:
        start = sequence.index(previous) + 1
    except ValueError:
        start = 0
    try:
        end = sequence.index(target) + 1
    except ValueError:
        return [target] if previous != target else []
    return sequence[start:end] if end >= start else []


def reconcile_workflow(root: Path, *, task_id: str, shadow: bool = False) -> tuple[dict[str, Any], list[Path]]:
    task_id = validate_task_id(task_id)
    if shadow:
        return shadow_replay(root, task_id)
    path = snapshot_path(root, task_id)
    with workflow_lock(root):
        snapshot = read_json(path)
        if not snapshot:
            task_events = [row for row in read_jsonl(root / WORKFLOW_EVENTS) if row.get("task_id") == task_id]
            planned = next((row for row in task_events if row.get("state") == "planned"), {})
            details = planned.get("details", {}) if isinstance(planned.get("details"), dict) else {}
            if not planned or not details.get("departments"):
                raise WorkflowError(f"工作流不存在，且事件不足以重建：{task_id}")
            rebuilt_departments = details.get("departments", [])
            for event in task_events[1:]:
                event_details = event.get("details", {}) if isinstance(event.get("details"), dict) else {}
                if event_details.get("binding_refresh") and event_details.get("departments"):
                    rebuilt_departments = event_details["departments"]
            snapshot = {
                "schema_version": "1.0",
                "task_id": task_id,
                "request_hash": details.get("request_hash", ""),
                "request_summary_hash_only": True,
                "created_at": planned.get("created_at", utc_timestamp()),
                "updated_at": utc_timestamp(),
                "current_state": str(task_events[-1].get("state", "planned")),
                "resume_from": "",
                "plan_status": details.get("plan_status", "blocked"),
                "departments": rebuilt_departments,
                "owner_approval_required": bool(details.get("owner_approval_required")),
                "paid_promotion_enabled": False,
                "missing_receipts": [],
                "blockers": [],
                "next_legal_actions": [],
                "last_receipt_hash": "",
                "event_count": len(task_events),
                "receipt_count": 0,
                "recovered_from_events": True,
                "integrity_note": "SHA-256 chains detect accidental mutation; they are not digital signatures.",
                "scope_note": "Project-level control only; not a global Codex tool middleware.",
            }
        from goal_delivery_runtime import restore_goal
        snapshot = restore_goal(root, snapshot)
        from qa_review_plan import _binding
        restored_review = _binding(root, snapshot)
        if restored_review is not None:
            snapshot["qa_review_plan"] = restored_review
        receipts, receipt_invalid = _validate_receipt_chain(root, task_id)
        event_invalid = validate_workflow_events(root, task_id)
        invalid = event_invalid + receipt_invalid
        if not invalid:
            _apply_plan_refresh(snapshot, read_jsonl(root / WORKFLOW_EVENTS), root=root)
            if _latest_verified_qa_risk_level(root, task_id, receipts) == "R3":
                snapshot["owner_approval_required"] = True
                snapshot["owner_approval_source"] = "verified_qa_risk:R3"
        previous_state = str(snapshot.get("current_state", "planned"))
        if invalid:
            target = "blocked_evidence_invalid"
            derived = {
                "state": target,
                "missing": [],
                "blockers": invalid,
                "next": ["restore_or_replace_evidence_and_record_new_receipt"],
            }
            resume_from = previous_state if previous_state != target else str(snapshot.get("resume_from", "evidence_received"))
        elif snapshot.get("workflow_successor_link"):
            link = snapshot["workflow_successor_link"]
            if file_digest(root, link["source"]["path"]) != link["source"]:
                raise WorkflowError("original successor association evidence changed")
            derived = {"state": "blocked", "missing": [],
                       "blockers": ["existing_successor_result_intake:" + link["successor_task_id"]],
                       "next": ["receive_existing_successor_result:" + link["successor_task_id"]]}
            resume_from = "planned"
        elif snapshot.get("plan_status") != "ready_to_send":
            derived = {
                "state": "blocked",
                "missing": [],
                "blockers": snapshot.get("plan_blockers") or [f"dispatch_plan:{snapshot.get('plan_status', 'blocked')}"],
                "next": ["repair_dispatch_plan"],
            }
            resume_from = "planned"
        else:
            derived = _derive_state(root, snapshot, receipts)
            target = str(derived["state"])
            resume_from = ("evidence_received" if target == "qa_blocked"
                           else str(derived.get("resume_from", "")))

        target = str(derived["state"])
        sequence_previous = previous_state
        if previous_state == "qa_blocked":
            sequence_previous = str(snapshot.get("resume_from") or "evidence_received")
        elif previous_state == "blocked" and snapshot.get("resume_from"):
            sequence_previous = str(snapshot["resume_from"])
        elif previous_state == "blocked_evidence_invalid" and not invalid:
            sequence_previous = str(snapshot.get("resume_from") or "")
            normal_events = [
                row for row in read_jsonl(root / WORKFLOW_EVENTS)
                if row.get("task_id") == task_id
                and row.get("state") not in EXCEPTION_STATES | {"qa_blocked"}
            ]
            if not sequence_previous:
                sequence_previous = str(normal_events[-1]["state"]) if normal_events else "planned"
            if sequence_previous == "qa_blocked":
                # A failed validation may have been detected only after the
                # repaired QA cycle already appended its legal target state.
                # Resume that state instead of replaying a second QA PASS.
                sequence_previous = (
                    target if normal_events and normal_events[-1].get("state") == target
                    else "evidence_received"
                )
        external_execution_required = _workflow_requires_external_execution(snapshot, receipts)
        if previous_state == "blocked_evidence_invalid" and not invalid and sequence_previous == target:
            append_workflow_event(
                root, task_id, target,
                {"reconciled": True, "evidence_revalidated": True, "resume_from": sequence_previous},
            )
        elif previous_state == "closed" and target in {"qa_passed", "waiting_owner_approval", "owner_approved"} and external_execution_required:
            latest_qa_receipt = next(
                (row for row in reversed(receipts)
                 if row.get("receipt_type") == "qa_verdict" and row.get("department") == _final_qa_department(root, snapshot)),
                {},
            )
            other_completed = any(
                row.get("receipt_type") == "postcheck"
                and row.get("verdict") == "pass"
                and row.get("action_id") != latest_qa_receipt.get("action_id")
                for row in receipts
            )
            if target != "qa_passed" and other_completed and latest_qa_receipt.get("verdict") == "pass":
                append_workflow_event(
                    root, task_id, "qa_passed",
                    {"reconciled": True, "reopened_for_next_action": True,
                     "qa_receipt_id": latest_qa_receipt["receipt_id"],
                     "qa_receipt_hash": latest_qa_receipt["receipt_hash"]},
                )
                for state in _state_sequence("qa_passed", target, bool(snapshot.get("owner_approval_required")), True):
                    append_workflow_event(root, task_id, state, {"reconciled": True})
            elif target == "qa_passed":
                append_workflow_event(
                    root, task_id, "qa_passed", {"reconciled": True, "reopened_for_external_execution": True},
                )
            else:
                raise WorkflowError("已关闭工作流缺少经 QA 与精确批准的新动作，禁止重新打开")
        else:
            latest_qa_receipt = next(
                (row for row in reversed(receipts)
                 if row.get("receipt_type") == "qa_verdict" and row.get("department") == _final_qa_department(root, snapshot)),
                None,
            )
            for state in _state_sequence(
                sequence_previous,
                target,
                bool(snapshot.get("owner_approval_required")),
                external_execution_required,
            ):
                details = {"reconciled": True}
                if (latest_qa_receipt
                        and ((state == "qa_blocked" and latest_qa_receipt.get("verdict") == "blocked")
                             or (state == "qa_passed" and latest_qa_receipt.get("verdict") == "pass"))):
                    details["qa_receipt_id"] = latest_qa_receipt["receipt_id"]
                    details["qa_receipt_hash"] = latest_qa_receipt["receipt_hash"]
                append_workflow_event(root, task_id, state, details)
        snapshot.update(
            {
                "updated_at": utc_timestamp(),
                "current_state": target,
                "resume_from": resume_from,
                "missing_receipts": derived["missing"],
                "blockers": derived["blockers"],
                "next_legal_actions": derived["next"],
                "last_receipt_hash": str(receipts[-1].get("receipt_hash", "")) if receipts else "",
                "receipt_count": len(receipts),
                "event_count": sum(1 for row in read_jsonl(root / WORKFLOW_EVENTS) if row.get("task_id") == task_id),
            }
        )
        atomic_write_json(path, snapshot)
    return snapshot, [path, receipts_path(root, task_id), root / WORKFLOW_EVENTS]


def workflow_status(root: Path, task_id: str) -> tuple[dict[str, Any], list[Path]]:
    snapshot, artifacts = reconcile_workflow(root, task_id=task_id, shadow=False)
    handoff = result_handoff_status(root, task_id)
    payload = {
        "status": "workflow_status_ready",
        "task_id": task_id,
        "current_state": snapshot.get("current_state"),
        "missing_receipts": snapshot.get("missing_receipts", []),
        "blockers": snapshot.get("blockers", []),
        "next_legal_actions": snapshot.get("next_legal_actions", []),
        "owner_approval_required": bool(snapshot.get("owner_approval_required")),
        "owner_approval_pending": snapshot.get("current_state") == "waiting_owner_approval",
        "paid_promotion_enabled": False,
        "snapshot": rel_path(root, snapshot_path(root, task_id)),
        "controller_handoff": handoff,
        "business_goal_status": "not_inferred_from_workflow_state",
    }
    return payload, [*artifacts, result_handoff_path(root, task_id)]


RESULT_HANDOFF_EVENTS = {
    "notification_queued", "notification_sent", "notification_blocked",
    "controller_received", "controller_decision", "controller_followthrough"
}
RESULT_DECISIONS = {
    "send_qa", "rework", "release_gate", "continue", "wait_external", "close_scope", "accept"
}
RESULT_FOLLOWTHROUGH_STATUSES = {
    "dispatch_sent", "execution_verified", "external_wait_registered",
    "blocked_with_owner", "internal_control_completed", "prior_action_verified", "dependency_resolved",
    "inflight_result_verified", "subsequent_action_verified", "no_executable_work"
}


def _verify_inflight_followthrough(root: Path, record: dict[str, Any],
                                  decision: dict[str, Any]) -> dict[str, Any]:
    """Reconcile an exact dispatched result arriving after the decision.

    This closes only a controller action link. It grants no release permission
    and does not change the original decision, timestamps or business status.
    """
    linked_task = record["linked_task_id"]
    try:
        for line in receipts_path(root, linked_task).read_text(encoding="utf-8").splitlines():
            if not isinstance(json.loads(line), dict):
                raise ValueError("non-object receipt")
    except (OSError, ValueError, TypeError) as exc:
        raise WorkflowError("后续原始回执必须是完整严格JSONL，不得跳过损坏行") from exc
    if validate_workflow_events(root, linked_task):
        raise WorkflowError("后续原任务事件链损坏，不得关闭旧控制记录")
    receipts, invalid = _validate_receipt_chain(root, linked_task)
    result_index = next((i for i, row in enumerate(receipts)
                         if row.get("receipt_id") == record["action_receipt_id"]), None)
    owner = decision.get("next_owner")
    registry = department_registry(root)
    binding = registry.get(str(owner), {}).get("chat_binding", {})
    fixed_id = str(binding.get("task_id") or "")
    if invalid or result_index is None or not fixed_id:
        raise WorkflowError("在途结果须有有效原始回执链和固定下一负责人")
    result_receipt = receipts[result_index]
    dispatch_index = next((i for i in range(result_index - 1, -1, -1)
                           if receipts[i].get("receipt_type") == "dispatch_sent"
                           and receipts[i].get("department") == owner), None)
    dispatch = receipts[dispatch_index] if dispatch_index is not None else {}
    if decision.get("initial_dispatch") and (
            linked_task != decision.get("next_task_id")
            or dispatch.get("action_id") != decision.get("next_action_id")
            or dispatch.get("scope") != decision.get("next_scope")
            or dispatch.get("parent_initial_dispatch", {}).get("decision_record_id") != decision.get("record_id")):
        raise WorkflowError("parent initial dispatch followthrough must retain the exact child/action/scope/decision")
    dispatch_at = _parse_observed_at(dispatch.get("created_at"))
    decision_at = _parse_observed_at(decision.get("created_at"))
    result_at = _parse_observed_at(result_receipt.get("created_at"))
    acknowledgments = receipts[dispatch_index + 1:result_index] if dispatch_index is not None else []
    if (result_receipt.get("department") != owner
            or dispatch.get("receipt_id") != record["linked_dispatch_receipt_id"]
            or dispatch.get("chat_task_id") != fixed_id
            or dispatch_at is None or decision_at is None or result_at is None
            or not (decision_at < dispatch_at <= result_at if record.get("followthrough_status") == "subsequent_action_verified"
                    else dispatch_at <= decision_at < result_at)
            or not any(row.get("receipt_type") == "chat_ack"
                       and row.get("department") == owner
                       and row.get("chat_task_id") == fixed_id
                       and row.get("ack_nonempty") is True
                       and (ack_at := _parse_observed_at(row.get("created_at"))) is not None
                       and dispatch_at <= ack_at <= result_at for row in acknowledgments)):
        raise WorkflowError("在途结果须绑定决策前最后一次真实派工、非空接单和决策后交付")
    digest = record["linked_outbox"]
    validate_outbox(root, [digest], str(owner), record["linked_task_id"])
    outbox = read_json(safe_path(root, digest["path"]))
    chat_id = outbox.get("fixed_chat_task_id") or outbox.get("chat_task_id")
    if (outbox.get("task_id") != record["linked_task_id"] or outbox.get("department") != owner
            or (chat_id and chat_id != fixed_id)
            or str(outbox.get("status") or "").lower() in {"", "active", "in_progress", "pending"}):
        raise WorkflowError("在途交付的任务、固定聊天或完成状态不匹配")
    if record["linked_task_id"] == record["task_id"]:
        reviewer = _final_qa_department(root, read_json(snapshot_path(root, record["task_id"])))
        if (owner != reviewer or outbox.get("candidate_version") != record["candidate_version"]
                or not any(row.get("receipt_type") == "qa_verdict"
                           and row.get("department") == reviewer
                           and row.get("verdict") in {"pass", "blocked", "fail"}
                           and digest in row.get("evidence", []) for row in receipts[result_index:])):
            raise WorkflowError("同原任务在途 QA 须匹配准确候选版本及独立 QA 结果回执")
    else:
        # Producer and source-only publisher envelopes use these two explicit
        # parent keys. A loose references list is not a parent binding, and
        # conflicting explicit keys must never reconcile unrelated work.
        parents = [outbox[key] for key in ("parent_task_id", "original_business_task_id")
                   if outbox.get(key)]
        if (decision.get("decision") not in ({"continue", "rework", "accept"} if record.get("followthrough_status") == "subsequent_action_verified" else {"continue"}) or not parents
                or any(parent != record["task_id"] for parent in parents)):
            raise WorkflowError("跨任务在途结果须明确引用原父任务，不得关联无关业务")
    return {"dispatch_before_decision": dispatch_at <= decision_at,
            "dispatch_after_decision": decision_at < dispatch_at, "result_after_decision": True,
            "linked_dispatch_at": dispatch["created_at"],
            "linked_result_at": result_receipt["created_at"]}


def _verify_external_dependency_resolution(root: Path, record: dict[str, Any],
                                           decision: dict[str, Any],
                                           rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Resolve only an old wait using an already accepted, same-task QA result."""
    if decision.get("decision") != "wait_external" or not decision.get("unblock_condition"):
        raise WorkflowError("依赖解除仅用于已有具名条件的外部等待")
    reviewer = _final_qa_department(root, read_json(snapshot_path(root, record["task_id"])))
    ref = str(record.get("resolution_record_id") or "")
    accepted = next((row for row in rows if row.get("record_id") == ref), None)
    if (not accepted or accepted.get("event") != "controller_decision"
            or accepted.get("task_id") != record.get("task_id")
            or accepted.get("sender_department") != reviewer
            or accepted.get("decision") != "close_scope" or accepted.get("qa_status") != "pass"
            or accepted.get("candidate_version") == record.get("candidate_version")
            or not accepted.get("acceptance_scope")):
        raise WorkflowError("依赖解除须引用同原任务新候选的已收取独立QA有限验收")
    if not any(row.get("event") == "controller_received"
               and _result_identity(row) == _result_identity(accepted) for row in rows):
        raise WorkflowError("新QA结果尚未实际收取")
    digest = file_digest(root, str(accepted.get("outbox", {}).get("path") or ""))
    if digest != accepted.get("outbox"):
        raise WorkflowError("新QA冻结结果字节变化")
    qa = read_json(root / digest["path"])
    if (qa.get("task_id") != record.get("task_id") or qa.get("department") != reviewer
            or qa.get("candidate_version") != accepted.get("candidate_version")
            or qa.get("qa_verdict") != "pass" or qa.get("production_release_eligible") is not False
            or qa.get("whole_business_task_complete") is not False):
        raise WorkflowError("依赖解除不得代替生产或全业务验收")
    native, invalid = _validate_receipt_chain(root, record["task_id"])
    exact = [row for row in native if row.get("receipt_type") == "qa_verdict"
                  and row.get("department") == reviewer and row.get("verdict") == "pass"
             and digest in row.get("evidence", [])]
    if invalid or not exact:
        raise WorkflowError("缺少绑定新QA准确字节的有效独立回执")
    source = qa.get("source_original_outbox")
    if not isinstance(source, dict) or file_digest(root, str(source.get("path") or "")) != source:
        raise WorkflowError("缺少新QA冻结的原专业来源")
    producer = read_json(root / source["path"])
    if (producer.get("task_id") != record.get("task_id")
            or producer.get("department") != record.get("sender_department")
            or producer.get("candidate_version") != accepted.get("candidate_version")
            or producer.get("source_binding", {}).get("original_wait_ref") != record.get("candidate_version")
            or producer.get("published") is not False or producer.get("business_goal_closed") is not False):
        raise WorkflowError("新专业证据须准确引用旧等待，且不得声称业务或发布完成")
    observed = _parse_observed_at(str(producer.get("reported_at_myt") or ""))
    previous = _parse_observed_at(str(decision.get("created_at") or ""))
    if (observed is None or previous is None or observed <= previous
            or not dt.timedelta(minutes=-5) <= dt.datetime.now(dt.timezone.utc) - observed <= dt.timedelta(hours=26)):
        raise WorkflowError("依赖解除须有原等待之后26小时内的真实新证据")
    return {"resolution_qa_outbox": digest, "resolution_source_outbox": source,
            "resolution_qa_receipt_id": exact[-1]["receipt_id"],
            "resolution_scope": accepted["acceptance_scope"], "business_goal_closed": False}


def _followthrough_due(entry: dict[str, Any]) -> bool:
    if entry.get("controller_decision") in {None, "pending", "close_scope"}:
        return False
    status = entry.get("controller_followthrough")
    if status in {None, "pending"}:
        return True
    if status in {"external_wait_registered", "blocked_with_owner"}:
        check_at = _parse_observed_at(str(entry.get("next_check_at") or ""))
        return check_at is None or check_at <= dt.datetime.now(dt.timezone.utc)
    return False


def _followthrough_waiting(entry: dict[str, Any]) -> bool:
    return (entry.get("controller_followthrough") in {"external_wait_registered", "blocked_with_owner"}
            and not _followthrough_due(entry))


def _result_handoff_rows(root: Path, task_id: str) -> list[dict[str, Any]]:
    """Read the sidecar strictly; a damaged ledger must not be silently skipped."""
    path = result_handoff_path(root, task_id)
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    previous_hash = ""
    for index, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise WorkflowError(f"结果交接第 {index} 行不是 JSON") from exc
        if not isinstance(row, dict) or row.get("task_id") != task_id:
            raise WorkflowError(f"结果交接第 {index} 行任务身份无效")
        if row.get("previous_hash") != previous_hash:
            raise WorkflowError(f"结果交接第 {index} 行哈希链断裂")
        expected_hash = sha256_value({key: value for key, value in row.items() if key != "record_hash"})
        if row.get("record_hash") != expected_hash:
            raise WorkflowError(f"结果交接第 {index} 行哈希不匹配")
        previous_hash = expected_hash
        rows.append(row)
    return rows


def _result_identity(row: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(row.get("sender_department") or ""),
        str(row.get("candidate_version") or ""),
        str(row.get("result_sha256") or ""),
    )


def result_handoff_status(root: Path, task_id: str) -> dict[str, Any]:
    rows = _result_handoff_rows(root, validate_task_id(task_id))
    results: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in rows:
        identity = _result_identity(row)
        entry = results.setdefault(identity, {
            "sender_department": identity[0], "candidate_version": identity[1],
            "result_sha256": identity[2], "notification": "not_recorded",
            "controller_received": False, "controller_decision": "pending",
            "controller_followthrough": "pending",
        })
        event = row["event"]
        if event == "notification_queued" and entry["notification"] not in {"sent", "received"}:
            entry["notification"] = "queued"
        elif event == "notification_sent":
            entry["notification"] = "sent"
        elif event == "notification_blocked" and entry["notification"] not in {"sent", "queued"}:
            entry["notification"] = "blocked"
        elif event == "controller_received":
            entry["controller_received"] = True
            entry["intake_mode"] = row.get("intake_mode")
        elif event == "controller_decision":
            entry["controller_decision"] = row.get("decision")
            entry["next_owner"] = row.get("next_owner")
            entry["next_action"] = row.get("next_action")
        elif event == "controller_followthrough":
            entry["controller_followthrough"] = row.get("followthrough_status")
            entry["next_check_at"] = row.get("next_check_at")
    pending = [entry for entry in results.values() if entry["controller_decision"] == "pending"]
    followthrough_pending = [entry for entry in results.values() if _followthrough_due(entry)]
    waiting = [entry for entry in results.values() if _followthrough_waiting(entry)]
    return {
        "status": "not_recorded" if not rows else "pending_controller_intake_or_decision" if pending else "decided_followthrough_pending" if followthrough_pending else "waiting_followthrough_review" if waiting else "decided_scope_only",
        "result_count": len(results),
        "pending_count": len(pending),
        "followthrough_pending_count": len(followthrough_pending),
        "waiting_followthrough_count": len(waiting),
        "results": list(results.values()),
        "ledger": rel_path(root, result_handoff_path(root, task_id)),
        "business_goal_closed": False,
    }


def result_handoff_pending(root: Path, task_ids: list[str] | None = None) -> dict[str, Any]:
    """List queued handoffs and verified legacy deliveries missing a handoff record.

    Legacy discovery is deliberately derived from the immutable dispatch/ack/outbox
    receipt chain. It does not claim a fresh live-chat read or mark the result as
    received; operations must still verify the fixed chat before recording fallback
    intake and a controller decision.
    """
    selected = {validate_task_id(task) for task in task_ids} if task_ids is not None else None
    directory = root / RESULT_HANDOFF_DIR
    pending: list[dict[str, Any]] = []
    tracked: dict[str, dict[tuple[str, str, str], dict[str, Any]]] = {}
    if directory.is_dir():
        for path in sorted(directory.glob("*.jsonl")):
            if selected is not None and path.stem not in selected:
                continue
            task_id = validate_task_id(path.stem)
            rows = _result_handoff_rows(root, task_id)
            by_identity: dict[tuple[str, str, str], dict[str, Any]] = {}
            for row in rows:
                identity = _result_identity(row)
                outbox_pin = row.get("outbox")
                if not isinstance(outbox_pin, dict):
                    raise WorkflowError(f"结果交接 outbox 固定值不是对象，须恢复原证据：{task_id}")
                entry = by_identity.setdefault(identity, {
                    "task_id": task_id, "sender_department": identity[0],
                    "candidate_version": identity[1], "result_sha256": identity[2],
                    "outbox_path": outbox_pin.get("path"),
                    "queued": False, "sent": False, "notification_blocked": False,
                    "received": False, "decided": False,
                    "controller_followthrough": "pending",
                })
                if row["event"] == "notification_queued":
                    entry["queued"] = True
                elif row["event"] == "notification_sent":
                    entry["sent"] = True
                elif row["event"] == "notification_blocked":
                    entry["notification_blocked"] = True
                elif row["event"] == "controller_received":
                    entry["received"] = True
                elif row["event"] == "controller_decision":
                    if row.get("source_mode") == "collaboration" and row.get("decision") == "close_scope":
                        from collaboration_scope_close import readback_collaboration_scope_close
                        closed = readback_collaboration_scope_close(root, row, rows)
                        entry["closed_collaboration_scope"] = closed["acceptance_scope"]
                    entry["decided"] = True
                    entry["controller_decision"] = row.get("decision")
                    entry["next_owner"] = row.get("next_owner")
                    entry["next_action"] = row.get("next_action")
                    entry["unblock_condition"] = row.get("unblock_condition")
                elif row["event"] == "controller_followthrough":
                    entry["controller_followthrough"] = row.get("followthrough_status")
                    entry["next_check_at"] = row.get("next_check_at")
                    entry["unblock_condition"] = row.get("unblock_condition", entry.get("unblock_condition"))
            tracked[task_id] = by_identity
            pending.extend(entry for entry in by_identity.values() if not entry["decided"] and (
                entry["queued"] or entry["received"]
                or (entry.get("sent") and not entry["received"])
                or (entry.get("notification_blocked") and not entry["received"])
            ))

    recovery_candidates = _legacy_result_recovery_candidates(root, tracked, selected)
    recovery_identities = {
        (item.get("task_id"), item.get("sender_department"), item.get("candidate_version"), item.get("result_sha256"))
        for item in recovery_candidates
    }
    pending = [item for item in pending if (
        item.get("recovery_required")
        or (item.get("task_id"), item.get("sender_department"), item.get("candidate_version"),
            item.get("result_sha256")) not in recovery_identities
    )]
    pending.extend(recovery_candidates)
    followthrough_pending = [
        entry for entries in tracked.values() for entry in entries.values()
        if entry.get("decided") and _followthrough_due(entry)
    ]
    named_waits = [entry for entries in tracked.values() for entry in entries.values()
                   if entry.get("decided") and _followthrough_waiting(entry)]
    resolved = [entry for entries in tracked.values() for entry in entries.values()
                if entry.get("decided") and (entry.get("controller_decision") == "close_scope"
                    or entry.get("controller_followthrough") not in {None, "pending", "external_wait_registered", "blocked_with_owner"})]
    return {
        "scope_task_ids": sorted(selected) if selected is not None else None,
        "control_records_are_business_jobs": False,
        "named_waiting_dependencies": named_waits, "named_waiting_dependency_count": len(named_waits),
        "historical_resolved_control_records": resolved, "historical_resolved_control_count": len(resolved),
        "status": "recovery_required" if recovery_candidates else "followthrough_required" if followthrough_pending else "pending_results_ready",
        "pending_count": len(pending),
        "queued_pending_count": sum(1 for item in pending if item.get("queued")),
        "legacy_recovery_count": len(recovery_candidates),
        "followthrough_pending_count": len(followthrough_pending),
        "followthrough_results": followthrough_pending,
        "total_actionable_count": len(pending) + len(followthrough_pending),
        "results": pending,
        "business_goal_closed": False,
    }


def _legacy_result_recovery_candidates(
    root: Path,
    tracked: dict[str, dict[tuple[str, str, str], dict[str, Any]]],
    selected: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Find current-scope completed department outboxes missing from the result inbox."""
    snapshots = root / WORKFLOW_DIR
    receipts_directory = root / RECEIPTS_DIR
    if not snapshots.is_dir() or not receipts_directory.is_dir():
        return []
    recovery_scope = _current_recovery_task_scope(root)
    registry = department_registry(root)
    found: list[dict[str, Any]] = []
    for snapshot_file in sorted(snapshots.glob("*.json")):
        if selected is not None and snapshot_file.stem not in selected:
            continue
        task_id = validate_task_id(snapshot_file.stem)
        if recovery_scope is not None and task_id not in recovery_scope:
            continue
        snapshot = read_json(snapshot_file)
        if not snapshot:
            continue
        receipts, invalid = _validate_receipt_chain(root, task_id)
        if invalid:
            continue
        planned = {
            str(item.get("department")): item
            for item in snapshot.get("departments", [])
            if isinstance(item, dict)
        }
        departments = [name for name in planned if name != "operations" and name in registry]
        for department in departments:
            fixed_chat_id = str(registry[department].get("chat_binding", {}).get("task_id") or "")
            planned_chat_id = str(planned[department].get("chat_task_id") or "")
            if not fixed_chat_id or fixed_chat_id != planned_chat_id:
                continue
            dispatches = [
                (index, row) for index, row in enumerate(receipts)
                if row.get("receipt_type") == "dispatch_sent"
                and row.get("department") == department
                and row.get("chat_task_id") == fixed_chat_id
            ]
            if not dispatches:
                continue
            dispatch_index, dispatch = dispatches[-1]
            later = receipts[dispatch_index + 1:]
            ack_indexes = [
                index for index, row in enumerate(later)
                if row.get("receipt_type") == "chat_ack"
                and row.get("department") == department
                and row.get("chat_task_id") == fixed_chat_id
                and row.get("ack_nonempty") is True
            ]
            if not ack_indexes:
                continue
            ack_index = ack_indexes[-1]
            post_ack = later[ack_index + 1:]
            outbox_receipts = [
                row for row in post_ack
                if row.get("receipt_type") == "outbox_received"
                and row.get("department") == department
            ]
            candidates: list[tuple[str, dict[str, Any] | None, dict[str, Any] | None]] = []
            for receipt in reversed(outbox_receipts):
                evidence = receipt.get("evidence") or []
                outbox_evidence = next((item for item in evidence
                                        if str(item.get("path", "")).endswith(".json")), None)
                if isinstance(outbox_evidence, dict) and outbox_evidence.get("path"):
                    candidates.append((str(outbox_evidence["path"]), outbox_evidence, receipt))
            fallback_paths: list[Path] = []
            planned_path = str(planned[department].get("outbox_evidence") or "")
            if planned_path:
                try:
                    fallback_paths.append(safe_path(root, planned_path))
                except WorkflowError:
                    pass
            outbox_dir = root / "logs/department-outbox"
            if outbox_dir.is_dir():
                fallback_paths.extend(sorted(
                    outbox_dir.glob(f"{task_id}*{department}*.json"),
                    key=lambda item: item.stat().st_mtime,
                    reverse=True,
                ))
            known_paths = {path for path, _, _ in candidates}
            candidates.extend((rel_path(root, path), None, None)
                              for path in fallback_paths if path.is_file()
                              and rel_path(root, path) not in known_paths)

            dispatch_time = _parse_observed_at(str(dispatch.get("created_at") or ""))
            ack_time = _parse_observed_at(str(later[ack_index].get("created_at") or ""))
            for outbox_path, receipt_evidence, source_receipt in candidates:
                try:
                    current_digest = file_digest(root, outbox_path)
                    if receipt_evidence and any(current_digest.get(key) != receipt_evidence.get(key)
                                                for key in ("path", "sha256", "size")):
                        continue
                    validate_outbox(root, [current_digest], department, task_id)
                    outbox = read_json(safe_path(root, outbox_path))
                    if not source_receipt:
                        modified_at = dt.datetime.fromtimestamp(
                            safe_path(root, outbox_path).stat().st_mtime, tz=dt.timezone.utc
                        )
                        if (not dispatch_time or not ack_time or modified_at < dispatch_time
                                or modified_at < ack_time
                                or outbox.get("chat_reply", {}).get("nonempty") is not True
                                or outbox.get("chat_reply", {}).get("in_current_fixed_department_chat") is not True):
                            continue
                except (WorkflowError, OSError):
                    continue
                outbox_task = str(outbox.get("task_id", ""))
                if ((outbox_task != task_id and not outbox_task.startswith(task_id + "-"))
                        or str(outbox.get("status") or "").lower()
                        in {"", "active", "in_progress", "pending"}):
                    continue
                candidate = str(outbox.get("candidate_version") or "legacy-unspecified")
                identity = (department, candidate, str(current_digest["sha256"]))
                existing = tracked.get(task_id, {}).get(identity)
                if existing and (existing.get("queued") or existing.get("received") or existing.get("decided")):
                    break
                if existing and existing.get("sent"):
                    # A real historical send is already represented as pending intake.
                    break
                if existing and not existing.get("notification_blocked"):
                    # A prior non-queue event already represents this result.
                    break
                found.append({
                    "task_id": task_id,
                    "sender_department": department,
                    "candidate_version": candidate,
                    "result_sha256": str(current_digest["sha256"]),
                    "outbox_path": outbox_path,
                    "queued": False,
                    "received": False,
                    "decided": False,
                    "recovery_required": True,
                    "recovery_reason": (
                        "legacy_outbox_receipts_without_result_queue_entry"
                        if source_receipt else "legacy_v2_outbox_without_result_queue_receipt"
                    ),
                    "intake_mode": "fallback",
                    "requires_live_reply_verification": True,
                    "next_owner": "operations",
                    "next_action": "verify the exact fixed-chat result and outbox hash, then record fallback intake and one controller decision",
                    "source_dispatch_receipt_id": dispatch.get("receipt_id"),
                    "source_outbox_receipt_id": source_receipt.get("receipt_id") if source_receipt else "",
                    "business_goal_closed": False,
                })
                break
    return found


def _current_recovery_task_scope(root: Path) -> set[str] | None:
    """Limit legacy recovery to the live checkpoint and unresolved sole-backlog items.

    ``None`` is reserved for small standalone/test workspaces without these project
    state sources. In the real project, a present state source creates a bounded
    scope so old, already-resolved campaign history does not flood today's inbox.
    """
    scope: set[str] = set()
    state_source_found = False
    policy = read_json(root / "data/content/organic-execution-policy.json")
    acceptance = policy.get("keyword_content_coverage_acceptance", {})
    checkpoint_ref = acceptance.get("controller_checkpoint") if isinstance(acceptance, dict) else ""
    if checkpoint_ref:
        state_source_found = True
        try:
            checkpoint = read_json(safe_path(root, str(checkpoint_ref)))
        except WorkflowError:
            checkpoint = {}
        for key in ("active_department_tasks", "pending_qa"):
            values = checkpoint.get(key, []) if isinstance(checkpoint, dict) else []
            if isinstance(values, list):
                scope.update(str(value) for value in values
                             if isinstance(value, str) and TASK_ID_PATTERN.fullmatch(value))

    backlog_path = root / "data/content/organic-growth-backlog.json"
    backlog = read_json(backlog_path)
    if backlog_path.exists():
        state_source_found = True

        def collect_task_ids(value: Any, key: str = "") -> None:
            if isinstance(value, dict):
                for child_key, child in value.items():
                    collect_task_ids(child, str(child_key))
            elif isinstance(value, list):
                for child in value:
                    collect_task_ids(child, key)
            elif isinstance(value, str) and ("task_id" in key or key.endswith("tasks")):
                if TASK_ID_PATTERN.fullmatch(value):
                    scope.add(value)

        terminal_statuses = {"closed", "verified", "verified_production"}
        for item in backlog.get("items", []) if isinstance(backlog.get("items"), list) else []:
            if not isinstance(item, dict) or str(item.get("status") or "") in terminal_statuses:
                continue
            collect_task_ids(item)
    return scope if state_source_found else None


def _verify_operations_rework_completion(root: Path, request: dict[str, Any], task_id: str) -> dict[str, Any]:
    """Verify applied internal control only; never grants external execution authority."""
    qa_path = str(request.get("control_qa_outbox_path") or "")
    applied_path = str(request.get("control_applied_proof") or "")
    qa_digest = file_digest(root, qa_path)
    reviewer = _final_qa_department(root, read_json(snapshot_path(root, task_id)))
    validate_outbox(root, [qa_digest], reviewer, task_id)
    qa = read_json(safe_path(root, qa_path))
    applied_digest = file_digest(root, applied_path)
    applied = read_json(safe_path(root, applied_path))
    rows, invalid = _validate_receipt_chain(root, task_id)
    receipt = next((row for row in rows if row.get("receipt_id") == request.get("control_qa_receipt_id")), None)
    if (invalid or not receipt or receipt.get("receipt_type") != "qa_verdict"
            or receipt.get("department") != reviewer or receipt.get("verdict") != "pass"
            or receipt.get("action_class") != "internal_control_candidate"
            or qa_digest not in receipt.get("evidence", [])):
        raise WorkflowError("Applied control requires its exact independent internal QA receipt")
    qa_reference = applied.get("qa_outbox")
    qa_reference_path = qa_reference.get("path") if isinstance(qa_reference, dict) else qa_reference
    qa_reference_sha = qa_reference.get("sha256") if isinstance(qa_reference, dict) else applied.get("qa_outbox_sha256")
    if (qa.get("task_id") != task_id or applied.get("task_id") != task_id
            or not qa.get("candidate_version")
            or applied.get("candidate_version") != qa.get("candidate_version")
            or qa_reference_path != qa_path or qa_reference_sha != qa_digest["sha256"]):
        raise WorkflowError("Applied control proof must bind the exact task, QA version and bytes")
    permission_flags = {"no_external_permission_issued": True, "production_permission_issued": False}
    observed_flags = [(key, expected) for key, expected in permission_flags.items() if key in applied]
    if (applied.get("external_writes") != 0 or not observed_flags
            or any(applied[key] is not expected for key, expected in observed_flags)):
        raise WorkflowError("Internal completion requires consistent explicit no-permission flags")
    tests = applied.get("postapply_tests", applied.get("tests", {}))
    if (not isinstance(tests, dict) or not isinstance(tests.get("run"), int) or tests["run"] < 1
            or tests.get("failures") != 0 or tests.get("errors") != 0):
        raise WorkflowError("Applied control requires successful actual postapply checks")
    allowed = {"tools/workflow_control.py", "tools/site_ci_prepare_policy.py",
               "data/task-contract.json", "data/action-policy.json"}
    if task_id == "fc-20261002-qa-dispatch-priority-control-v1":
        allowed.add("tools/qa_dispatch_priority.py")
    if task_id == "fc-20261008-publisher-three-preview-call-binding-control-qa-v1":
        allowed.add("tools/cms_publisher_three_preview_policy.py")
    from goal_delivery_runtime import enabled as goal_enabled
    snapshot = read_json(snapshot_path(root, task_id))
    if goal_enabled(root, snapshot):
        manifest_pin = applied.get("candidate_manifest")
        if (not isinstance(manifest_pin, dict) or file_digest(root, str(manifest_pin.get("path") or "")) != manifest_pin
                or manifest_pin not in qa.get("evidence", [])):
            raise WorkflowError("applied full-goal control requires independently reviewed exact candidate manifest")
        manifest = read_json(safe_path(root, manifest_pin["path"]))
        if (manifest.get("task_id") != task_id or manifest.get("external_writes") is not False
                or applied.get("candidate_fingerprint") != manifest.get("candidate_fingerprint")):
            raise WorkflowError("applied full-goal candidate fingerprint differs")
        changes = manifest.get("changes", [])
        allowed = {entry.get("path") for entry in changes if isinstance(entry, dict)}
        if any(not isinstance(name, str) or name.startswith(("accounts/", "logs/", "backups/")) for name in allowed):
            raise WorkflowError("reviewed candidate contains non-source scope")
    files = applied.get("applied_files", [])
    if not isinstance(files, list) or not files:
        raise WorkflowError("Applied control must contain current runtime file pins")
    if goal_enabled(root, snapshot) and {pin.get("path") for pin in files if isinstance(pin, dict)} != allowed:
        raise WorkflowError("applied full-goal source must cover every exact reviewed change")
    for pin in files:
        if not isinstance(pin, dict) or pin.get("path") not in allowed:
            raise WorkflowError("Applied control file is outside the internal controller scope")
        if file_digest(root, pin["path"])["sha256"] != pin.get("sha256"):
            raise WorkflowError("Applied controller bytes have drifted")
    return {"control_qa": qa_digest, "control_applied_proof": applied_digest,
            "control_qa_receipt_id": receipt["receipt_id"],
            "control_candidate_version": qa["candidate_version"],
            "external_authority_granted": False, "business_goal_closed": False}


def scheduled_result_source(root: Path, task_id: str, department: str) -> dict[str, Any] | None:
    """Resolve one admitted daily source without constructing a business workflow."""
    contract = read_json(root / "data/task-contract.json")
    sources = contract.get("result_handoff_contract", {}).get("scheduled_daily_sources")
    if sources is None:
        # The pre-existing website intake remains readable for old contracts.
        old = contract.get("department_output_gates", {}).get("content_organic_website_daily", {})
        if (old.get("task_id_pattern") == "fc-YYYYMMDD-website-growth-daily"
                and department == "content-organic-website"
                and re.fullmatch(r"fc-\d{8}-website-growth-daily", task_id)):
            return {"automation_id": "flash-cast-4", "department": department,
                    "task_id_pattern": r"fc-(?P<date>\d{8})-website-growth-daily",
                    "responsible_assistant": "operations", "legacy_contract": True}
        return None
    if not isinstance(sources, list):
        raise WorkflowError("structured admitted daily sources required")
    matches = []
    for source in sources:
        if not isinstance(source, dict) or source.get("department") != department:
            continue
        try:
            match = re.fullmatch(str(source.get("task_id_pattern") or ""), task_id)
        except re.error as error:
            raise WorkflowError("valid exact daily task pattern required") from error
        if match:
            matches.append(source)
    if len(matches) > 1:
        raise WorkflowError("daily source must have one unique responsible assistant")
    return matches[0] if matches else None


def _validate_scheduled_result(root: Path, request: dict[str, Any], outbox: dict[str, Any],
                               fixed_id: str) -> dict[str, Any]:
    source = scheduled_result_source(root, request["task_id"], request["sender_department"])
    if not source:
        raise WorkflowError("daily source is not admitted by the current task contract")
    reply_at = _parse_observed_at(request.get("reply_observed_at"))
    report_at = _parse_observed_at(outbox.get("reported_at_myt"))
    match = re.fullmatch(source["task_id_pattern"], request["task_id"])
    local_tz = dt.timezone(dt.timedelta(hours=8))
    day = (match.groupdict().get("date") if match else None)
    if day is None and match and report_at is not None:
        day = report_at.astimezone(local_tz).strftime("%Y%m%d")
    if (not day or request.get("source_automation_id") != source.get("automation_id")
            or request.get("source_thread_id") != fixed_id
            or not re.fullmatch(r"[0-9a-f]{64}", str(request.get("source_reply_sha256") or ""))
            or not re.fullmatch(r"[0-9a-f-]{36}", str(request.get("source_turn_id") or ""))
            or reply_at is None or report_at is None or reply_at < report_at
            or reply_at > dt.datetime.now(dt.timezone.utc)
            or reply_at.astimezone(local_tz).strftime("%Y%m%d") != day
            or report_at.astimezone(local_tz).strftime("%Y%m%d") != day
            or outbox.get("chat_reply", {}).get("nonempty") is not True
            or outbox.get("chat_reply", {}).get("in_current_fixed_department_chat") is not True):
        raise WorkflowError("daily intake requires the exact admitted automation, fixed completed turn and same-day V2 result")
    if not source.get("legacy_contract"):
        receiver = source.get("responsible_assistant")
        authority = department_registry(root).get(receiver, {}).get("coordination_authority", {})
        if authority.get("routine_decisions") is not True or outbox.get("handoff", {}).get("receiver") != receiver:
            raise WorkflowError("daily result must target its unique current responsible assistant")
        capability = source.get("acceptance_capability")
        if capability and capability not in authority.get("review_capabilities", []):
            raise WorkflowError("daily receiver lacks the exact source acceptance capability")
        from goal_delivery_runtime import _native_document, _collaboration_final_message
        completion = _native_document(root, request.get("actual_native_completion"))
        message = _collaboration_final_message(completion, fixed_id)
        reply_pin = request.get("visible_reply")
        if not isinstance(reply_pin, dict) or file_digest(root, reply_pin.get("path", "")) != reply_pin:
            raise WorkflowError("original frozen daily final reply pin required")
        raw = safe_path(root, reply_pin["path"]).read_bytes()
        if (message.get("phase") != "final_answer" or not message.get("id")
                or message.get("turnId") != request["source_turn_id"]
                or not isinstance(message.get("text"), str) or not raw
                or raw != message["text"].encode("utf-8")
                or hashlib.sha256(raw).hexdigest() != request["source_reply_sha256"]):
            raise WorkflowError("actual daily final thread/turn/message and exact UTF-8 reply required; commentary is not completion")
    return source


def _validate_goal_completed_result(root: Path, request: dict[str, Any], fixed_id: str,
                                    *, through_receipt_id: str | None = None) -> dict[str, Any]:
    """Bind a new goal result to its actual completed final, never an ACK."""
    from goal_delivery_runtime import _collaboration_native, _collaboration_final_message
    completion_pin, reply_pin = request.get("actual_native_completion"), request.get("visible_reply")
    completion = _collaboration_native(root, completion_pin)
    message = _collaboration_final_message(completion, fixed_id)
    turn = request.get("source_turn_id")
    if (not isinstance(reply_pin, dict) or file_digest(root, reply_pin.get("path", "")) != reply_pin
            or not isinstance(turn, str) or not turn.strip()
            or request.get("source_thread_id") != fixed_id or message.get("turnId") != turn
            or message.get("phase") != "final_answer" or not message.get("id")
            or not isinstance(message.get("text"), str) or not message["text"].strip()):
        raise WorkflowError("new goal result requires exact completed fixed thread/turn/final message pins")
    raw = safe_path(root, reply_pin["path"]).read_bytes()
    observed = _parse_observed_at(request.get("reply_observed_at"))
    if (raw != message["text"].encode("utf-8") or hashlib.sha256(raw).hexdigest() != request.get("source_reply_sha256")
            or observed is None or observed > dt.datetime.now(dt.timezone.utc)):
        raise WorkflowError("new goal result requires original exact UTF-8 final reply and actual observation time")
    # Completion time comes from the pinned provider document, not caller observation.
    native_turn = completion
    document = completion.get("wait", completion)
    if isinstance(document.get("polls"), list):
        native_turn = next(row.get("latestTurn", {}) for row in document["polls"]
                           if row.get("thread", {}).get("id") == fixed_id)
    completed_value = native_turn.get("completedAt")
    if isinstance(completed_value, (int, float)) and not isinstance(completed_value, bool):
        try:
            completed_at = dt.datetime.fromtimestamp(completed_value, dt.timezone.utc)
        except (ValueError, OverflowError, OSError):
            completed_at = None
    else:
        completed_at = _parse_observed_at(completed_value)
    task = validate_task_id(request["task_id"])
    try:
        for line in receipts_path(root, task).read_text(encoding="utf-8").splitlines():
            if not isinstance(json.loads(line), dict):
                raise ValueError("non-object receipt")
    except (OSError, ValueError, TypeError) as exc:
        raise WorkflowError("completed source requires strict original receipt JSONL") from exc
    receipts, invalid = _validate_receipt_chain(root, task, through_receipt_id=through_receipt_id)
    scoped = [row for row in receipts if row.get("department") == request["sender_department"]
              and row.get("chat_task_id") == fixed_id
              and (at := _parse_observed_at(row.get("created_at"))) is not None and at <= observed]
    starts = [_parse_observed_at(row["created_at"]) for row in scoped
              if row.get("receipt_type") in {"dispatch_sent", "chat_ack"}]
    if invalid or not starts or completed_at is None or not max(starts) <= completed_at <= observed:
        raise WorkflowError("actual native completedAt must follow exact task dispatch/ACK and precede observation")
    outbox_path = request.get("outbox_path") or request.get("outbox", {}).get("path", "")
    task_mentioned = re.search(r"(?<![A-Za-z0-9_-])" + re.escape(task) + r"(?![A-Za-z0-9_-])", message["text"])
    path_mentioned = bool(outbox_path) and re.search(re.escape(outbox_path) + r"(?![A-Za-z0-9_./-])", message["text"])
    if not (task_mentioned or path_mentioned):
        raise WorkflowError("completed final must explicitly bind this exact task or frozen outbox path")
    return {"source_turn_id": turn, "source_thread_id": fixed_id,
            "source_reply_sha256": request["source_reply_sha256"], "reply_observed_at": request["reply_observed_at"],
            "actual_native_completion": completion_pin, "visible_reply": reply_pin}


def _validate_scheduled_acceptance(root: Path, request: dict[str, Any]) -> dict[str, Any]:
    """Independent daily-report acceptance; no synthetic dispatch or production permit."""
    task_id, sender = request["task_id"], request["sender_department"]
    source = scheduled_result_source(root, task_id, sender)
    if not source or source.get("legacy_contract"):
        raise WorkflowError("current admitted daily source required for assistant report acceptance")
    role = source["responsible_assistant"]
    if role == sender or role == "operations" or request.get("coordinator_role") != role:
        raise WorkflowError("unique independent daily assistant required; no self review or HQ acceptance")
    registry = department_registry(root)
    authority = registry.get(role, {}).get("coordination_authority", {})
    if (authority.get("routine_decisions") is not True or registry.get(role, {}).get("new_dispatch_enabled") is False
            or source.get("acceptance_capability") not in authority.get("review_capabilities", [])):
        raise WorkflowError("daily acceptance capability is not current")
    identity = tuple(request[k] for k in ("sender_department", "candidate_version", "result_sha256"))
    queued = [row for row in _result_handoff_rows(root, task_id)
              if row.get("event") == "notification_queued" and _result_identity(row) == identity]
    if (len(queued) != 1 or queued[0].get("source_mode") != "scheduled_run"
            or queued[0].get("source_automation_id") != source["automation_id"]):
        raise WorkflowError("exact actually queued daily result required")
    pin = request.get("scheduled_acceptance")
    if not isinstance(pin, dict) or file_digest(root, pin.get("path", "")) != pin:
        raise WorkflowError("current frozen independent daily acceptance pin required")
    accepted = read_json(safe_path(root, pin["path"]))
    expected = {"task_id": task_id, "sender_department": sender, "candidate_version": request["candidate_version"],
                "result_sha256": request["result_sha256"], "reviewer": role, "verdict": "pass",
                "acceptance_kind": "daily_report_scope", "external_permission_issued": False}
    if any(accepted.get(k) != value for k, value in expected.items()):
        raise WorkflowError("daily acceptance must bind this exact report and independent current assistant")
    if accepted.get("external_permission_issued") is not False:
        raise WorkflowError("daily report acceptance cannot issue production permission")
    result = queued[0]["outbox"]
    if accepted.get("reviewed_outbox") != result or file_digest(root, result["path"]) != result:
        raise WorkflowError("daily acceptance reviewed result bytes changed")
    checks = accepted.get("review_evidence", [])
    if (not isinstance(checks, list) or not checks or not accepted.get("acceptance_scope")
            or not isinstance(accepted.get("methods_used"), list) or not accepted["methods_used"]
            or any(not isinstance(item, dict) or file_digest(root, item.get("path", "")) != item for item in checks)):
        raise WorkflowError("nonempty independent method, scope and unchanged review evidence required")
    from goal_delivery_runtime import _native_document, _collaboration_final_message
    native = _native_document(root, accepted.get("actual_native_completion"))
    message = _collaboration_final_message(native, registry[role]["chat_binding"]["task_id"])
    reply = accepted.get("visible_reply")
    if not isinstance(reply, dict) or file_digest(root, reply.get("path", "")) != reply:
        raise WorkflowError("original independent assistant final reply pin required")
    raw = safe_path(root, reply["path"]).read_bytes()
    if (message.get("phase") != "final_answer" or not message.get("id") or not isinstance(message.get("text"), str)
            or not raw or raw != message["text"].encode("utf-8") or pin["path"] not in message["text"]):
        raise WorkflowError("actual assistant completed final must identify this acceptance with exact UTF-8 bytes")
    return {"pin": pin, "acceptance_scope": accepted["acceptance_scope"], "reviewer": role,
            "actual_native_completion": accepted["actual_native_completion"], "business_goal_closed": False}


def _validate_legacy_result_notification(root, request, record, registry, sender, task_id):
    decision_id = str(request.get("policy_decision_id") or "")
    message_sha = str(request.get("message_sha256") or "").lower()
    message_ref = str(request.get("message_ref") or "")
    matches = [item for item in read_jsonl(root / POLICY_DECISIONS) if item.get("decision_id") == decision_id]
    routing = matches[-1] if matches else {}
    controller_id = str(registry["operations"].get("chat_binding", {}).get("task_id") or "")
    if (routing.get("status") != "allow" or routing.get("routing_status") != "routing_allowed"
            or routing.get("task_id") != task_id or routing.get("department") != sender
            or routing.get("action_class") != "thread_message"
            or not str(routing.get("action_id") or "").startswith("notify-operations-")
            or routing.get("target_department") != "operations"
            or routing.get("target_thread_id") != controller_id
            or routing.get("scope") != f"department_result:{task_id}:{sender}"
            or routing.get("payload_sha256") != message_sha
            or not message_ref):
        raise WorkflowError("通知送达缺少准确放行决定、消息哈希或真实发送引用")
    record.update(policy_decision_id=decision_id, message_sha256=message_sha, message_ref=message_ref)


def _validate_collaboration_followthrough_receipt(root, task_id, decision, follow):
    """One next action frozen by this decision, never an unrelated true receipt."""
    linked_id = validate_task_id(follow.get("linked_task_id", ""))
    rows, invalid = _validate_receipt_chain(root, linked_id)
    matching = [row for row in rows if row.get("receipt_id") == follow.get("action_receipt_id")
                and row.get("receipt_type") == "dispatch_sent"]
    parent = read_json(snapshot_path(root, task_id))
    child = read_json(snapshot_path(root, linked_id))
    if invalid or validate_workflow_events(root, linked_id) or len(matching) != 1:
        raise WorkflowError("one intact actual next dispatch receipt required")
    action = matching[0]
    action_time, decision_time = _parse_observed_at(action.get("created_at")), _parse_observed_at(decision.get("created_at"))
    if (decision.get("decision") == "wait_external" or not action_time or not decision_time or action_time <= decision_time
            or linked_id != decision.get("next_task_id") or action.get("department") != decision.get("next_owner")
            or action.get("action_id") != decision.get("next_action_id") or action.get("scope") != decision.get("next_scope")
            or action.get("scope") not in parent.get("goal_delivery", {}).get("authorized_scope", [])
            or not child.get("goal_delivery")
            or (linked_id != task_id and child["goal_delivery"].get("parent_task_id") != task_id)):
        raise WorkflowError("next dispatch must match the current decision's exact task/action/owner/scope and parent")
    return action


def _record_collaboration_result_handoff(root: Path, request: dict[str, Any], source: dict[str, Any]):
    """Formal intake of an exact collaboration source; no synthetic queue or ACK."""
    task_id = validate_task_id(request["task_id"])
    event = request["event"]
    key = request.get("idempotency_key")
    if not isinstance(key, str) or not key or len(key) > 200:
        raise WorkflowError("exact collaboration intake idempotency key required")
    paths = request.get("evidence_paths")
    if not isinstance(paths, list) or any(not isinstance(path, str) for path in paths):
        raise WorkflowError("collaboration intake frozen evidence paths required")
    evidence = [file_digest(root, path) for path in paths]
    state = source["state"]
    required = [state[k] for k in ("collaboration", "native_transport", "result_receipt", "result", "visible_reply", "native_result")]
    if any(pin not in evidence for pin in required):
        raise WorkflowError("formal intake must retain the original strict sent and returned source pins")
    claim = request.get("coordination_claim", {})
    record = {"schema_version": "1.0", "record_id": str(uuid.uuid4()),
              **{k: request[k] for k in ("task_id", "event", "sender_department", "candidate_version", "result_sha256")},
              "outbox": source["result"], "evidence": evidence, "idempotency_key": key, "created_at": utc_timestamp(),
              "source_mode": "collaboration", "action_id": state["action_id"], "scope": source["scope"],
              "collaboration_source": state["result_receipt"], "message_body_stored": False,
              "business_goal_closed": False, "external_permission_issued": False,
              "coordinator_role": source["responsible_assistant"], "coordinator_owner": request.get("coordinator_owner"),
              "coordination_fence": claim.get("fence"), "decision_actor": source["responsible_assistant"],
              "responsible_assistant": source["responsible_assistant"], "HQ_second_review_required": False}
    if event == "controller_received":
        if (request.get("intake_mode") != "collaboration"
                or request.get("source_reply_sha256") != state["visible_reply"]["sha256"]
                or request.get("source_thread_id") != source["fixed_chat_task_id"]
                or _parse_observed_at(request.get("reply_observed_at")) is None):
            raise WorkflowError("formal collaboration intake must identify the original actual completed final reply")
        record.update({k: request[k] for k in ("intake_mode", "source_reply_sha256", "source_thread_id", "reply_observed_at")})
    elif event == "controller_decision":
        # Delivery alone never implies acceptance. Exact prior fenced independent
        # release proof may close this scope without parent closure or permission.
        if (request.get("decision") not in {"continue", "rework", "send_qa", "wait_external", "close_scope"}
                or not isinstance(request.get("next_action"), str) or not request["next_action"].strip()
                or not isinstance(request.get("next_owner"), str)
                or request.get("next_owner") not in (set(department_registry(root)) | set(read_json(root / "data/department-registry.json").get("collaboration_bindings", {})))):
            raise WorkflowError("collaboration intake requires a bounded continuation decision, not inferred acceptance")
        record.update({k: request[k] for k in ("decision", "next_owner", "next_action")})
        if record["decision"] == "close_scope":
            record.update({k: request.get(k) for k in (
                "acceptance_scope", "collaboration_acceptance_mode", "collaboration_acceptance",
                "acceptance_intake_record_id", "collaboration_release_outcome",
                "collaboration_remote_readback", "collaboration_public_manifest")})
        elif record["decision"] != "wait_external":
            parent = read_json(snapshot_path(root, task_id))
            if (not isinstance(request.get("next_action_id"), str) or not request["next_action_id"].strip()
                    or request.get("next_scope") not in parent["goal_delivery"]["authorized_scope"]):
                raise WorkflowError("next collaboration action and authorized scope must be frozen in the decision")
            record.update(next_task_id=validate_task_id(request.get("next_task_id", "")),
                          next_action_id=request["next_action_id"], next_scope=request["next_scope"])
        record.update({k: str(request.get(k) or default) for k, default in
                       {"qa_status": "NOT_VERIFIED", "execution_status": "NOT_EXECUTED", "public_postcheck_status": "NOT_VERIFIED"}.items()})
        if record["decision"] == "wait_external":
            if not request.get("unblock_condition"):
                raise WorkflowError("exact collaboration wait unblock condition required")
            record["unblock_condition"] = request["unblock_condition"]
    else:
        status = request.get("followthrough_status")
        if status not in {"dispatch_sent", "blocked_with_owner", "external_wait_registered"}:
            raise WorkflowError("collaboration continuation requires an actual dispatch or named bounded wait")
        record["followthrough_status"] = status
        if status == "dispatch_sent":
            linked_id = validate_task_id(request.get("linked_task_id", ""))
            linked, invalid = _validate_receipt_chain(root, linked_id)
            found = [row for row in linked if row.get("receipt_id") == request.get("action_receipt_id")
                     and row.get("receipt_type") == "dispatch_sent"]
            if invalid or validate_workflow_events(root, linked_id) or len(found) != 1:
                raise WorkflowError("one intact actual next dispatch receipt required")
            record.update(linked_task_id=linked_id, action_receipt_id=found[0]["receipt_id"])
        else:
            next_check = _parse_observed_at(request.get("next_check_at"))
            if not next_check or next_check <= dt.datetime.now(dt.timezone.utc) or not request.get("unblock_condition"):
                raise WorkflowError("named recovery owner, future recheck and unblock condition required")
            record.update(next_check_at=request["next_check_at"], unblock_condition=request["unblock_condition"])
    path = result_handoff_path(root, task_id)
    with workflow_lock(root):
        rows = _result_handoff_rows(root, task_id)
        if event == "controller_decision" and record.get("decision") == "close_scope":
            from collaboration_scope_close import verify_collaboration_scope_close
            record.update(verify_collaboration_scope_close(root, request, source, evidence, rows))
        current = [row for row in rows if _result_identity(row) == _result_identity(record)]
        comparable = {k: v for k, v in record.items() if k not in {"record_id", "created_at"}}
        duplicate = next((row for row in rows if row.get("idempotency_key") == key), None)
        if duplicate:
            if any(duplicate.get(k) != v for k, v in comparable.items()):
                raise WorkflowError("collaboration idempotency key binds different content")
            return {**duplicate, "result": "duplicate_ignored"}, [path]
        if read_json(snapshot_path(root, task_id)).get("current_state") in TERMINAL_STATES:
            raise WorkflowError("closed collaboration scope cannot append a new formal stage")
        if event != "controller_followthrough" and any(row.get("event") == event for row in current):
            raise WorkflowError("exact collaboration stage already recorded")
        if event == "controller_decision" and not any(row.get("event") == "controller_received" for row in current):
            raise WorkflowError("actual formal collaboration intake required before decision")
        if event == "controller_followthrough":
            decision = next((row for row in reversed(current) if row.get("event") == "controller_decision"), None)
            if not decision:
                raise WorkflowError("actual current assistant decision required before followthrough")
            if decision.get("decision") == "close_scope":
                raise WorkflowError("exact collaboration scope is already closed; no followthrough or repeated execution")
            previous = next((row for row in reversed(current) if row.get("event") == event), None)
            if previous:
                if previous.get("followthrough_status") not in {"blocked_with_owner", "external_wait_registered"}:
                    raise WorkflowError("actual collaboration next action cannot be replayed")
                if previous.get("evidence") == evidence:
                    raise WorkflowError("collaboration wait recovery requires new actual evidence")
                if (record["followthrough_status"] == previous["followthrough_status"]
                        and _parse_observed_at(record["next_check_at"]) <= _parse_observed_at(previous["next_check_at"])):
                    raise WorkflowError("collaboration wait recheck must move forward")
            if record["followthrough_status"] == "dispatch_sent":
                _validate_collaboration_followthrough_receipt(root, task_id, decision, record)
            elif record["followthrough_status"] == "external_wait_registered" and decision["decision"] != "wait_external":
                raise WorkflowError("external wait must follow the accurate wait decision")
        record["previous_hash"] = rows[-1]["record_hash"] if rows else ""
        record["record_hash"] = sha256_value(record)
        append_jsonl_locked(path, record)
    return {**record, "result": "recorded", "controller_handoff": result_handoff_status(root, task_id)}, [path]


def _record_result_handoff_uncoordinated(root: Path, request: dict[str, Any]) -> tuple[dict[str, Any], list[Path]]:
    """Record delivery and controller decisions without changing historical workflow states.

    The caller must verify live Codex messages. This project-local ledger records
    that verification; it cannot intercept or prove a Codex tool call by itself.
    """
    if not isinstance(request, dict):
        raise WorkflowError("结果交接输入必须是 JSON 对象")
    task_id = validate_task_id(str(request.get("task_id") or ""))
    event = str(request.get("event") or "")
    if event not in RESULT_HANDOFF_EVENTS:
        raise WorkflowError("结果交接事件类型无效")
    sender = str(request.get("sender_department") or "")
    registry = department_registry(root)
    if sender not in registry:
        from goal_delivery_runtime import validate_collaboration_result_handoff
        source = validate_collaboration_result_handoff(root, request)
        return _record_collaboration_result_handoff(root, request, source)
    if sender == "operations" or sender not in registry:
        raise WorkflowError("结果来源必须是注册固定执行部门")
    snapshot = read_json(snapshot_path(root, task_id))
    from goal_delivery_runtime import enabled as goal_enabled, owner_direct
    candidate = str(request.get("candidate_version") or "")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9+._-]{0,199}", candidate):
        raise WorkflowError("候选版本格式无效")
    result_sha = str(request.get("result_sha256") or "").lower()
    if not re.fullmatch(r"[0-9a-f]{64}", result_sha):
        raise WorkflowError("结果 SHA-256 无效")
    key = str(request.get("idempotency_key") or "")
    if not key or len(key) > 200:
        raise WorkflowError("结果交接必须提供长度不超过 200 的幂等键")
    outbox_path = str(request.get("outbox_path") or "")
    outbox_digest = file_digest(root, outbox_path)
    if outbox_digest["sha256"] != result_sha:
        raise WorkflowError("结果哈希必须匹配当前部门 outbox")
    validate_outbox(root, [outbox_digest], sender, task_id)
    outbox = read_json(safe_path(root, outbox_path))
    fixed_id = str(registry[sender].get("chat_binding", {}).get("task_id") or "")
    outbox_chat_id = str(outbox.get("fixed_chat_task_id") or outbox.get("chat_task_id") or "")
    if (outbox.get("task_id") != task_id or outbox.get("department") != sender
            or (outbox_chat_id and outbox_chat_id != fixed_id)
            or str(outbox.get("status") or "").lower() in {"", "active", "in_progress", "pending"}):
        raise WorkflowError("部门 outbox 的任务、固定聊天或结果状态不匹配")
    if not outbox_chat_id:
        # Older validated V2 outboxes lack a chat-id field. They may be taken
        # into a historical fallback, or continue an already received result,
        # only when the original receipt chain ties the exact outbox bytes to
        # a nonempty ack in the registered chat.
        receipts, invalid = _validate_receipt_chain(root, task_id)
        has_ack = any(row.get("receipt_type") == "chat_ack"
                      and row.get("department") == sender
                      and row.get("chat_task_id") == fixed_id
                      and row.get("ack_nonempty") is True for row in receipts)
        has_outbox_receipt = any(row.get("receipt_type") == "outbox_received"
                      and row.get("department") == sender
                      and outbox_digest in row.get("evidence", []) for row in receipts)
        prior_result = [row for row in _result_handoff_rows(root, task_id)
                        if _result_identity(row) == (sender, candidate, result_sha)]
        prior_received = any(row.get("event") == "controller_received" for row in prior_result)
        prior_decided = any(row.get("event") == "controller_decision" for row in prior_result)
        historical_continuation = (event == "controller_followthrough"
                                   and prior_received and prior_decided)
        if (not historical_continuation and event not in {"controller_received", "controller_decision"}
                or (event == "controller_received" and request.get("intake_mode") != "fallback")
                or invalid or not has_ack or not has_outbox_receipt):
            raise WorkflowError("旧 outbox 缺固定聊天绑定，仅准确历史兜底收取可用")
    if outbox.get("candidate_version") and candidate != outbox["candidate_version"]:
        raise WorkflowError("候选版本必须与原部门 outbox 一致")
    scheduled_identity = (sender, candidate, result_sha)
    scheduled_queue = any(
        row.get("event") == "notification_queued"
        and row.get("source_mode") == "scheduled_run"
        and _result_identity(row) == scheduled_identity
        for row in _result_handoff_rows(root, task_id)
    )
    is_scheduled_queue = event == "notification_queued" and request.get("source_mode") == "scheduled_run"
    is_owner_direct_queue = event == "notification_queued" and owner_direct(root, snapshot, sender)
    if (not snapshot or not any(item.get("department") == sender for item in snapshot.get("departments", []))):
        if not (is_scheduled_queue or scheduled_queue):
            raise WorkflowError("结果来源部门未列入原任务工作流")
    goal_completed_source = None
    if event == "notification_queued" and goal_enabled(root, snapshot) and not is_scheduled_queue:
        if str(outbox.get("status") or "").lower() in {"", "active", "in_progress", "pending"}:
            raise WorkflowError("new goal final outbox requires a finite delivered result status")
        goal_completed_source = _validate_goal_completed_result(root, request, fixed_id)
    if event == "notification_queued":
        if is_scheduled_queue:
            scheduled_source = _validate_scheduled_result(root, request, outbox, fixed_id)
        elif is_owner_direct_queue:
            direct_rows, invalid = _validate_receipt_chain(root, task_id)
            if (invalid or not any(r.get("receipt_type") == "chat_ack" and r.get("department") == sender
                                   and r.get("chat_task_id") == fixed_id and r.get("ack_nonempty") is True for r in direct_rows)
                    or outbox.get("chat_reply", {}).get("nonempty") is not True
                    or outbox.get("chat_reply", {}).get("in_current_fixed_department_chat") is not True
                    or request.get("source_thread_id") != fixed_id
                    or not re.fullmatch(r"[0-9a-f]{64}", str(request.get("source_reply_sha256") or ""))
                    or _parse_observed_at(request.get("reply_observed_at")) is None):
                raise WorkflowError("owner direct result requires actual fixed chat ACK/reply provenance")
        else:
            receipts, invalid = _validate_receipt_chain(root, task_id)
            latest_dispatch_index = next((index for index in range(len(receipts) - 1, -1, -1)
                                          if receipts[index].get("receipt_type") == "dispatch_sent"
                                          and receipts[index].get("department") == sender
                                          and receipts[index].get("chat_task_id") == fixed_id), None)
            current_receipts = receipts[latest_dispatch_index + 1:] if latest_dispatch_index is not None else []
            has_ack = any(row.get("receipt_type") == "chat_ack"
                          and row.get("department") == sender
                          and row.get("chat_task_id") == fixed_id
                          and row.get("ack_nonempty") is True for row in current_receipts)
            dispatch_at = (_parse_observed_at(str(receipts[latest_dispatch_index].get("created_at")))
                           if latest_dispatch_index is not None else None)
            if (invalid or not has_ack or dispatch_at is None
                    or safe_path(root, outbox_path).stat().st_mtime < dispatch_at.timestamp()
                    or outbox.get("chat_reply", {}).get("nonempty") is not True
                    or outbox.get("chat_reply", {}).get("in_current_fixed_department_chat") is not True):
                raise WorkflowError("入队须有当前轮次派工、非空固定聊天回复和派工后的V2结果")
    evidence_paths = request.get("evidence_paths") or []
    if not isinstance(evidence_paths, list) or any(not isinstance(item, str) for item in evidence_paths):
        raise WorkflowError("evidence_paths 必须是项目内路径数组")
    evidence = [file_digest(root, path) for path in evidence_paths]
    record: dict[str, Any] = {
        "schema_version": "1.0", "record_id": str(uuid.uuid4()),
        "task_id": task_id, "event": event, "sender_department": sender,
        "candidate_version": candidate, "result_sha256": result_sha,
        "outbox": outbox_digest, "evidence": evidence,
        "idempotency_key": key, "created_at": utc_timestamp(),
        "message_body_stored": False, "business_goal_closed": False,
    }
    child_goal = snapshot.get("goal_delivery", {})
    if (child_goal.get("parent_task_id") == "fc-20261010-system-flow-throughput-and-ledger-close-v1"
            and child_goal.get("initial_dispatch_mode") == "read_only"
            and any(action.get("parent_initial_dispatch")
                    for action in child_goal.get("approved_actions", []))):
        record["created_at"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="microseconds")
    if goal_enabled(root, snapshot) and event in {"controller_received", "controller_decision", "controller_followthrough"}:
        claim = request.get("coordination_claim", {})
        record.update(coordinator_role=request.get("coordinator_role"),
                      coordinator_owner=request.get("coordinator_owner"),
                      coordination_fence=claim.get("fence"),
                      decision_actor=request.get("coordinator_role"),
                      responsible_assistant=snapshot["goal_delivery"]["responsible_assistant"],
                      HQ_second_review_required=False)
    if event == "notification_queued":
        record["delivery_mode"] = "durable_inbox"
        record["target_department"] = snapshot["goal_delivery"]["responsible_assistant"] if goal_enabled(root, snapshot) else "operations"
        if goal_enabled(root, snapshot) and sender == snapshot["goal_delivery"]["responsible_assistant"]:
            record.update(result_lane="HQ_knowledge", target_department="operations", HQ_second_review_required=False)
        record["interrupts_active_thread"] = False
        if is_scheduled_queue:
            record.update(source_mode="scheduled_run",
                          source_automation_id=scheduled_source["automation_id"],
                          responsible_assistant=scheduled_source["responsible_assistant"],
                          target_department=scheduled_source["responsible_assistant"],
                          source_turn_id=request["source_turn_id"],
                          source_thread_id=fixed_id,
                          source_reply_sha256=request["source_reply_sha256"],
                          reply_observed_at=request["reply_observed_at"])
            if not scheduled_source.get("legacy_contract"):
                record.update(actual_native_completion=request["actual_native_completion"],
                              visible_reply=request["visible_reply"])
        elif is_owner_direct_queue:
            record.update(source_mode="owner_direct", authorization_pin=snapshot["goal_delivery"]["authorization_pin"],
                          source_thread_id=fixed_id, source_reply_sha256=request["source_reply_sha256"],
                          reply_observed_at=request["reply_observed_at"])
        if goal_completed_source is not None:
            record.update(goal_completed_source)
            record.setdefault("source_mode", "approved_dispatch")
    elif event == "notification_sent":
        from result_coordination import result_lane, notification_record
        identity = {"task_id": task_id, "sender_department": sender,
                    "candidate_version": candidate, "result_sha256": result_sha}
        lane = result_lane(root, identity)
        if lane.get("lane") != "legacy_unmapped":
            delivered = notification_record(root, identity, request, _coordination_locked=True)
            record.update(target_department=lane["target_department"], result_lane=lane["lane"],
                          policy_decision_id=request["policy_decision_id"], message_sha256=request["message_sha256"],
                          message_ref=request["message_ref"], actual_native_transport=delivered["native_transport"])
        else:
            _validate_legacy_result_notification(root, request, record, registry, sender, task_id)
    elif event == "notification_blocked":
        reason = str(request.get("block_reason") or "")
        if not reason:
            raise WorkflowError("通知失败必须记录准确阻断原因")
        record["block_reason"] = reason
    elif event == "controller_received":
        intake_mode = str(request.get("intake_mode") or "")
        reply_sha = str(request.get("source_reply_sha256") or "").lower()
        reply_thread = str(request.get("source_thread_id") or "")
        observed_at = str(request.get("reply_observed_at") or "")
        if (intake_mode not in {"notification", "fallback", "queue"}
                or not re.fullmatch(r"[0-9a-f]{64}", reply_sha)
                or reply_thread != fixed_id or _parse_observed_at(observed_at) is None):
            raise WorkflowError("总控收取须记录固定聊天的非空回复哈希、时间和实际收取方式")
        record.update(intake_mode=intake_mode, source_reply_sha256=reply_sha,
                      source_thread_id=reply_thread, reply_observed_at=observed_at)
        original_goal_queue = next((row for row in _result_handoff_rows(root, task_id)
                                    if row.get("event") == "notification_queued" and _result_identity(row) == scheduled_identity
                                    and row.get("actual_native_completion") and row.get("source_mode") in {"owner_direct", "approved_dispatch"}), None)
        if original_goal_queue:
            source = _validate_goal_completed_result(root, original_goal_queue, fixed_id)
            if reply_sha != source["source_reply_sha256"]:
                raise WorkflowError("goal intake must retain the original completed final, not a later ACK")
            record.update(source)
            record.update(reply_observed_at=observed_at, source_completion_observed_at=source["reply_observed_at"])
        if scheduled_queue:
            source = scheduled_result_source(root, task_id, sender)
            if source and not source.get("legacy_contract"):
                original = next(row for row in _result_handoff_rows(root, task_id)
                                if row.get("event") == "notification_queued" and _result_identity(row) == scheduled_identity)
                if reply_sha != original.get("source_reply_sha256") or reply_thread != original.get("source_thread_id"):
                    raise WorkflowError("daily intake must retain the original exact completed reply, not a later ACK")
                _validate_scheduled_result(root, original, outbox, fixed_id)
                record.update(source_turn_id=original["source_turn_id"], actual_native_completion=original["actual_native_completion"],
                              visible_reply=original["visible_reply"], responsible_assistant=source["responsible_assistant"])
        if intake_mode == "fallback":
            fallback_reason = str(request.get("fallback_reason") or "")
            if not fallback_reason:
                raise WorkflowError("兜底收取须说明通知未送达的原因，不得冒充已发送")
            record["fallback_reason"] = fallback_reason
    elif event == "controller_decision":
        decision = str(request.get("decision") or "")
        next_owner = str(request.get("next_owner") or "")
        next_action = str(request.get("next_action") or "")
        if decision not in RESULT_DECISIONS or not next_owner or not next_action or not evidence:
            raise WorkflowError("总控决策须有类型、唯一负责人、下一动作和证据")
        daily_source = scheduled_result_source(root, task_id, sender)
        daily_modern = bool(daily_source and not daily_source.get("legacy_contract") and scheduled_queue)
        if decision in {"accept", "close_scope"} and daily_modern and not goal_enabled(root, snapshot):
            accepted = _validate_scheduled_acceptance(root, request)
            if request.get("qa_status") != "pass":
                raise WorkflowError("accepted daily report must carry its accurate pass status")
            record.update(scheduled_acceptance=accepted["pin"], responsible_assistant=accepted["reviewer"],
                          acceptance_scope=accepted["acceptance_scope"], HQ_second_review_required=False)
        if decision == "accept" and not goal_enabled(root, snapshot) and not daily_modern:
            raise WorkflowError("accept requires one assigned complete-goal assistant")
        if decision in {"release_gate", "close_scope", "accept"} and not (daily_modern and decision != "release_gate"):
            qa_rows = [row for row in read_jsonl(receipts_path(root, task_id))
                       if row.get("receipt_type") == "qa_verdict" and row.get("department") ==
                       ("qa" if decision == "release_gate" and not goal_enabled(root, snapshot) else _final_qa_department(root, snapshot))]
            if not qa_rows or qa_rows[-1].get("verdict") != "pass" or request.get("qa_status") != "pass":
                raise WorkflowError("发布门禁或关闭范围须引用原工作流的当前 QA PASS")
            if decision == "release_gate" and not goal_enabled(root, snapshot) and qa_rows[-1].get("action_class") not in {
                "cms_content_candidate", "site_code_candidate", "site_code_rework_candidate"
            }:
                raise WorkflowError("发布门禁须有准确网站候选的发布级 QA；只读或内部候选 PASS 不适用")
        record.update(decision=decision, next_owner=next_owner, next_action=next_action,
                      qa_status=str(request.get("qa_status") or "NOT_VERIFIED"),
                      execution_status=str(request.get("execution_status") or "NOT_EXECUTED"),
                      public_postcheck_status=str(request.get("public_postcheck_status") or "NOT_VERIFIED"))
        from parent_initial_dispatch import freeze_next
        initial_next = freeze_next(root, snapshot, request, evidence)
        record.update(initial_next)
        if initial_next:
            record["created_at"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="microseconds")
        if decision == "wait_external":
            unlock = str(request.get("unblock_condition") or "")
            if not unlock:
                raise WorkflowError("外部阻断必须写明解除条件")
            record["unblock_condition"] = unlock
        if decision == "close_scope":
            acceptance_scope = str(request.get("acceptance_scope") or "")
            if not acceptance_scope or record["qa_status"] != "pass":
                raise WorkflowError("关闭单项范围须写明范围并有准确 QA PASS")
            record["acceptance_scope"] = acceptance_scope
    else:
        followthrough_status = str(request.get("followthrough_status") or "")
        if followthrough_status not in RESULT_FOLLOWTHROUGH_STATUSES or not evidence:
            raise WorkflowError("总控后续动作须有有效状态和项目内证据")
        record["followthrough_status"] = followthrough_status
        if followthrough_status in {"dispatch_sent", "execution_verified", "prior_action_verified",
                                    "inflight_result_verified", "subsequent_action_verified"}:
            linked_task_id = validate_task_id(str(request.get("linked_task_id") or ""))
            if followthrough_status == "execution_verified" and linked_task_id != task_id:
                raise WorkflowError("发布后续复核必须引用原任务的执行回执")
            receipt_id = str(request.get("action_receipt_id") or "")
            linked_receipts, invalid = _validate_receipt_chain(root, linked_task_id)
            expected_type = {"dispatch_sent": "dispatch_sent", "execution_verified": "postcheck",
                             "prior_action_verified": "outbox_received",
                             "inflight_result_verified": "outbox_received", "subsequent_action_verified": "outbox_received"}[followthrough_status]
            matches = [row for row in linked_receipts if row.get("receipt_id") == receipt_id
                       and row.get("receipt_type") == expected_type]
            if invalid or len(matches) != 1 or (followthrough_status == "execution_verified"
                                                 and matches[0].get("verdict") != "pass"):
                raise WorkflowError("总控后续动作须引用已核实的派工或公开复核回执")
            record.update(linked_task_id=linked_task_id, action_receipt_id=receipt_id)
            if followthrough_status in {"prior_action_verified", "inflight_result_verified", "subsequent_action_verified"}:
                linked_outbox = file_digest(root, str(request.get("linked_outbox_path") or ""))
                if linked_outbox not in matches[0].get("evidence", []):
                    raise WorkflowError("既有后续工作须绑定准确 outbox 字节与收取回执")
                record["linked_outbox"] = linked_outbox
            if followthrough_status in {"inflight_result_verified", "subsequent_action_verified"}:
                record["linked_dispatch_receipt_id"] = str(request.get("linked_dispatch_receipt_id") or "")
        elif followthrough_status in {"external_wait_registered", "blocked_with_owner"}:
            next_check_at = str(request.get("next_check_at") or "")
            unblock_condition = str(request.get("unblock_condition") or "")
            if _parse_observed_at(next_check_at) is None or not unblock_condition:
                raise WorkflowError("外部等待或后续阻断须有解除条件和下次检查时间")
            record.update(next_check_at=next_check_at, unblock_condition=unblock_condition)
        elif followthrough_status == "dependency_resolved":
            record["resolution_record_id"] = str(request.get("resolution_record_id") or "")
            if not record["resolution_record_id"]:
                raise WorkflowError("依赖解除须引用准确有限验收记录")
        elif followthrough_status == "no_executable_work":
            if not goal_enabled(root, snapshot):
                raise WorkflowError("explicit assistant complete goal required for no-work outcome")
            notice = file_digest(root, str(request.get("department_notice_path") or ""))
            data = read_json(safe_path(root, notice["path"]))
            if (notice not in evidence or data.get("task_id") != task_id or data.get("department") != sender
                    or data.get("thread_id") != fixed_id or not data.get("native_receipt_ref")
                    or not data.get("message_ref") or data.get("state") != "temporarily_no_executable_work"):
                raise WorkflowError("actual fixed-department no-work notice receipt required")
            record["department_notice"] = notice
        else:
            action_reference = str(request.get("action_reference") or "")
            if not action_reference:
                raise WorkflowError("内部控制完成须有准确动作引用")
            record["action_reference"] = action_reference

    path = result_handoff_path(root, task_id)
    with workflow_lock(root):
        rows = _result_handoff_rows(root, task_id)
        identity = _result_identity(record)
        current = [row for row in rows if _result_identity(row) == identity]
        prior_same_key = next((row for row in rows if row["idempotency_key"] == key), None)
        comparable = {key: value for key, value in record.items() if key not in {"record_id", "created_at"}}
        if prior_same_key:
            prior_comparable = {key: prior_same_key.get(key) for key in comparable}
            if prior_comparable != comparable:
                raise WorkflowError("幂等键已绑定不同结果交接内容")
            return {**prior_same_key, "result": "duplicate_ignored"}, [path]
        if event != "controller_followthrough" and any(row["event"] == event for row in current):
            raise WorkflowError("同一候选结果的该交接阶段已记录，不能重复通知或决策")
        events = {row["event"] for row in current}
        if event == "notification_sent" and "controller_received" in events:
            raise WorkflowError("总控已兜底收取此结果，不再补发旧通知")
        if event == "notification_queued" and ("notification_sent" in events or "controller_received" in events):
            raise WorkflowError("旧通知已送达或总控已收取，不重复入队")
        if event == "controller_received":
            if record["intake_mode"] == "notification" and "notification_sent" not in events:
                raise WorkflowError("通知收取前必须有真实 notification_sent 回执")
            if record["intake_mode"] == "queue" and "notification_queued" not in events:
                raise WorkflowError("队列收取前必须有真实 notification_queued 回执")
        if event == "controller_decision" and "controller_received" not in events:
            raise WorkflowError("总控未核验收取，不能先写决策")
        if event == "controller_followthrough":
            decision_row = next((row for row in reversed(current)
                                 if row["event"] == "controller_decision"), None)
            if decision_row is None or decision_row.get("decision") == "close_scope":
                raise WorkflowError("总控后续动作须先有未关闭范围的准确决策")
            previous_followthrough = next((row for row in reversed(current)
                                           if row["event"] == "controller_followthrough"), None)
            if previous_followthrough:
                previous_status = previous_followthrough.get("followthrough_status")
                if previous_status not in {"external_wait_registered", "blocked_with_owner"}:
                    raise WorkflowError("已落实的总控后续动作不能重复登记")
                if previous_followthrough.get("evidence") == record.get("evidence"):
                    raise WorkflowError("等待或阻断复查须提供新的项目内证据")
                if (record["followthrough_status"] == previous_status
                        and _parse_observed_at(record.get("next_check_at")) <=
                        _parse_observed_at(previous_followthrough.get("next_check_at"))):
                    raise WorkflowError("再次等待须设置晚于上次的复查时间")
            allowed_followthrough = {
                "accept": {"dispatch_sent", "execution_verified", "external_wait_registered", "blocked_with_owner",
                           "prior_action_verified", "inflight_result_verified", "no_executable_work"},
                "send_qa": {"dispatch_sent", "blocked_with_owner", "prior_action_verified",
                            "inflight_result_verified"},
                "rework": {"dispatch_sent", "blocked_with_owner"},
                "continue": {"dispatch_sent", "blocked_with_owner", "internal_control_completed",
                             "prior_action_verified", "inflight_result_verified"},
                "release_gate": {"execution_verified", "blocked_with_owner"},
                "wait_external": {"external_wait_registered", "blocked_with_owner", "dependency_resolved"},
            }
            if goal_enabled(root, snapshot):
                allowed_followthrough.setdefault("continue", set()).add("no_executable_work")
            if decision_row["decision"] == "rework" and decision_row.get("next_owner") == "operations":
                allowed_followthrough["rework"] = allowed_followthrough["rework"] | {"internal_control_completed"}
                if record["followthrough_status"] == "internal_control_completed":
                    record.update(_verify_operations_rework_completion(root, request, task_id))
            for decision_kind in ("accept", "send_qa", "rework", "continue"):
                allowed_followthrough[decision_kind].add("subsequent_action_verified")
            if record["followthrough_status"] not in allowed_followthrough.get(decision_row["decision"], set()):
                raise WorkflowError("总控后续动作状态与原决策不匹配")
            if (record["followthrough_status"] == "internal_control_completed"
                    and decision_row.get("next_owner") != "operations"):
                raise WorkflowError("专业部门下一动作不能以总控内部记录冒充派工")
            if record["followthrough_status"] == "dependency_resolved":
                record.update(_verify_external_dependency_resolution(root, record, decision_row, rows))
            if record["followthrough_status"] in {"inflight_result_verified", "subsequent_action_verified"}:
                record.update(_verify_inflight_followthrough(root, record, decision_row))
            if record["followthrough_status"] == "dispatch_sent":
                linked_receipts, invalid = _validate_receipt_chain(root, record["linked_task_id"])
                action_receipt = next((row for row in linked_receipts
                                       if row.get("receipt_id") == record["action_receipt_id"]), None)
                if decision_row.get("initial_dispatch") and (
                        record["linked_task_id"] != decision_row.get("next_task_id") or not action_receipt
                        or action_receipt.get("action_id") != decision_row.get("next_action_id")
                        or action_receipt.get("scope") != decision_row.get("next_scope")
                        or action_receipt.get("parent_initial_dispatch", {}).get("decision_record_id") != decision_row.get("record_id")):
                    raise WorkflowError("parent initial dispatch followthrough must retain the exact child/action/scope/decision")
                action_at = _parse_observed_at(action_receipt.get("created_at") if action_receipt else None)
                decision_at = _parse_observed_at(decision_row.get("created_at"))
                if (invalid or not action_receipt or action_receipt.get("department") != decision_row.get("next_owner")
                        or action_at is None or decision_at is None or action_at <= decision_at):
                    raise WorkflowError("派工后续回执须晚于决策且命中准确下一负责人")
            elif record["followthrough_status"] == "execution_verified":
                linked_receipts, invalid = _validate_receipt_chain(root, record["linked_task_id"])
                action_receipt = next((row for row in linked_receipts
                                       if row.get("receipt_id") == record["action_receipt_id"]), None)
                action_at = _parse_observed_at(action_receipt.get("created_at") if action_receipt else None)
                decision_at = _parse_observed_at(decision_row.get("created_at"))
                if (invalid or not action_receipt or action_at is None or decision_at is None
                        or action_at <= decision_at or not any(row.get("receipt_type") == "execution_result"
                                                              for row in linked_receipts)):
                    raise WorkflowError("发布后续须有决策后的执行及公开复核回执")
            elif record["followthrough_status"] == "prior_action_verified":
                linked_receipts, invalid = _validate_receipt_chain(root, record["linked_task_id"])
                action_receipt = next((row for row in linked_receipts
                                       if row.get("receipt_id") == record["action_receipt_id"]), None)
                action_at = _parse_observed_at(action_receipt.get("created_at") if action_receipt else None)
                decision_at = _parse_observed_at(decision_row.get("created_at"))
                if record["linked_task_id"] == task_id:
                    linked_outbox = read_json(root / record["linked_outbox"]["path"])
                    if (decision_row.get("decision") != "send_qa"
                            or action_receipt is None or action_receipt.get("department") != _final_qa_department(root, snapshot)
                            or linked_outbox.get("task_id") != task_id
                            or linked_outbox.get("department") != _final_qa_department(root, snapshot)
                            or linked_outbox.get("candidate_version") != record["candidate_version"]):
                        raise WorkflowError("同原任务既有 QA 须匹配准确候选版本、部门和真实 outbox 回执")
                elif decision_row.get("decision") == "send_qa":
                    raise WorkflowError("同原任务 QA 对账不得引用其他业务任务")
                if (invalid or not action_receipt or action_receipt.get("department") != decision_row.get("next_owner")
                        or action_at is None or decision_at is None or action_at >= decision_at):
                    raise WorkflowError("既有后续工作必须是原负责人在当前决策前已交付的准确结果")
                record["action_before_decision"] = True
        record["previous_hash"] = rows[-1]["record_hash"] if rows else ""
        record["record_hash"] = sha256_value({key: value for key, value in record.items() if key != "record_hash"})
        append_jsonl_locked(path, record)
    return {**record, "result": "recorded", "controller_handoff": result_handoff_status(root, task_id)}, [path, snapshot_path(root, task_id)]


def shadow_replay(root: Path, task_id: str) -> tuple[dict[str, Any], list[Path]]:
    from original_task_publisher_handover import shadow_projection
    handover_projection = shadow_projection(root, task_id)
    if handover_projection is not None:
        return handover_projection, []
    dispatch_path = root / "logs/dispatch" / f"{task_id}.json"
    dispatch = read_json(dispatch_path)
    if not dispatch:
        raise WorkflowError(f"找不到历史分派证据：{rel_path(root, dispatch_path)}")
    departments = [str(item) for item in dispatch.get("parallel_departments", [])]
    if not departments:
        departments = [
            str(item.get("department", ""))
            for item in dispatch.get("departments", [])
            if isinstance(item, dict) and item.get("department") not in {"qa", "operations"}
        ]
    sent = {
        str(item.get("department"))
        for item in dispatch.get("dispatch_events", [])
        if isinstance(item, dict) and item.get("status") == "sent"
    }
    plan_by_department = {
        str(item.get("department")): item
        for item in dispatch.get("departments", [])
        if isinstance(item, dict)
    }
    outboxes: dict[str, str] = {}
    learning: dict[str, str] = {}
    invalid_evidence: list[str] = []
    for department in departments:
        candidate = str(plan_by_department.get(department, {}).get("outbox_evidence", ""))
        candidates = [safe_path(root, candidate)] if candidate else sorted((root / "logs/department-outbox").glob(f"{task_id}*{department}*.json"))
        existing = next((path for path in candidates if path.exists() and path.is_file()), None)
        if not existing:
            continue
        outboxes[department] = rel_path(root, existing)
        value = read_json(existing)
        learning_value = value.get("learning") if isinstance(value.get("learning"), dict) else {}
        learning[department] = str(learning_value.get("status", "missing"))
        if value.get("department") != department:
            invalid_evidence.append(f"outbox_department_mismatch:{department}")

    missing_dispatch = [f"dispatch_sent:{item}" for item in departments if item not in sent]
    missing_chat = [f"chat_ack_nonempty:{item}" for item in departments]
    missing_outbox = [f"outbox_received:{item}" for item in departments if item not in outboxes]
    missing_learning = [f"learning_status:{item}" for item in departments if learning.get(item) in {None, "", "missing"}]
    qa_candidates = sorted((root / "logs/department-outbox").glob(f"{task_id}*qa*.json"))
    missing_qa = [] if qa_candidates else ["qa_verdict:qa"]
    if missing_dispatch:
        state = "dispatch_ready"
    elif missing_chat:
        state = "dispatched"
    elif missing_outbox or missing_learning:
        state = "acknowledged"
    elif missing_qa:
        state = "evidence_received"
    else:
        state = "waiting_owner_approval"
    missing = missing_dispatch + missing_chat + missing_outbox + missing_learning + missing_qa
    payload = {
        "status": "shadow_replay_blocked" if missing or invalid_evidence else "shadow_replay_ready_for_owner_review",
        "task_id": task_id,
        "current_state": "blocked_evidence_invalid" if invalid_evidence else state,
        "source_schema_version": dispatch.get("schema_version", "legacy"),
        "dispatch_status": dispatch.get("status", "unknown"),
        "departments": departments,
        "dispatch_sent": sorted(sent),
        "outboxes": outboxes,
        "learning_status": learning,
        "missing_receipts": missing,
        "blockers": invalid_evidence + ([str(dispatch.get("status"))] if str(dispatch.get("status", "")).startswith("blocked") else []),
        "next_legal_actions": ["record_nonempty_chat_ack"] if missing_chat else ["obtain_independent_qa_verdict"],
        "owner_approval_required": False,
        "shadow_only": True,
        "writes_performed": False,
        "legacy_files_unchanged": True,
        "interpretation": "department outbox completed is department delivery only, not workflow completion",
    }
    artifacts = [dispatch_path, *[root / value for value in outboxes.values()], *qa_candidates]
    return payload, artifacts


def record_result_handoff(root: Path, request: dict[str, Any]) -> tuple[dict[str, Any], list[Path]]:
    """Native final handoff entry, coordinated without changing historical ledgers."""
    from result_coordination import handoff_guard, notification_enqueue, coordination_lock, FINAL_EVENTS
    notification_lock = coordination_lock(root) if request.get("event") not in FINAL_EVENTS else nullcontext()
    with notification_lock, handoff_guard(root, request) as admission:
        if admission.replay_record is not None:
            if request.get("event") == "notification_queued":
                notification_enqueue(root, request, _coordination_locked=True)
            return {**admission.replay_record, "result": "duplicate_ignored"}, [result_handoff_path(root, request["task_id"])]
        record, artifacts = _record_result_handoff_uncoordinated(root, request)
        if request.get("event") == "notification_queued":
            notification_enqueue(root, request, _coordination_locked=True)
        admission.complete(record)
        return record, artifacts
