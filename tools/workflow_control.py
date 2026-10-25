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
from contextvars import ContextVar
from copy import deepcopy
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
    "health_reconciled",
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


def _final_qa_department(root: Path, snapshot: dict[str, Any], *, preparation_only=False) -> str:
    """Legacy/production remains qa; frozen exact R0 plans may select QA2."""
    from qa_review_plan import reviewer_department
    return reviewer_department(root, snapshot, preparation_only=preparation_only)


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


# Validation is shared only for one request. No disk cache or time-based PASS.
_VALIDATION_CONTEXT = ContextVar("flashcast_validation_context", default=None)


class RequestValidationContext:
    def __init__(self):
        self.files = {}
        self.parsed = {}
        self.proofs = {}
        self.read_counts = {}
        self.strict_unchanged = False

    def bytes(self, path):
        path = Path(path).resolve()
        key = str(path)
        stat = path.stat()
        version = (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)
        old = self.files.get(key)
        if old is None or old["version"] != version:
            if old is not None and self.strict_unchanged:
                raise WorkflowError("original condo approval validation dependency changed")
            raw = path.read_bytes()
            final = path.stat()
            if version != (final.st_dev, final.st_ino, final.st_size, final.st_mtime_ns, final.st_ctime_ns):
                raise WorkflowError("validation dependency changed while reading")
            self.files[key] = {"version": version, "raw": raw, "sha256": hashlib.sha256(raw).hexdigest()}
            self.read_counts[key] = self.read_counts.get(key, 0) + 1
            self.parsed.pop(key, None)
            self.proofs.clear()
        return self.files[key]["raw"]

    def json(self, path, *, lines=False):
        key = str(Path(path).resolve())
        raw = self.bytes(path)
        mode = "jsonl" if lines else "json"
        cached = self.parsed.setdefault(key, {})
        if mode not in cached:
            if lines:
                rows = []
                for line in raw.decode("utf-8").splitlines():
                    if not line.strip():
                        continue
                    value = json.loads(line)
                    if not isinstance(value, dict):
                        raise WorkflowError("strict request JSONL object required")
                    rows.append(value)
                cached[mode] = rows
            else:
                value = json.loads(raw)
                if not isinstance(value, dict):
                    raise WorkflowError("strict request JSON object required")
                cached[mode] = value
        return deepcopy(cached[mode])

    def recheck(self):
        # Under the original commit lock, hash each dependency once. Parsing
        # and professional review are not repeated when bytes are unchanged.
        for name, entry in list(self.files.items()):
            raw = Path(name).read_bytes()
            if hashlib.sha256(raw).hexdigest() != entry["sha256"] or len(raw) != len(entry["raw"]):
                raise WorkflowError("request dependency changed before commit: " + name)
        return True


@contextmanager
def request_validation_context():
    current = _VALIDATION_CONTEXT.get()
    if current is not None:
        yield current
        return
    current = RequestValidationContext()
    token = _VALIDATION_CONTEXT.set(current)
    try:
        yield current
    finally:
        _VALIDATION_CONTEXT.reset(token)


def validation_bytes(path):
    from readonly_work_view_cache import note_read
    note_read(path)
    current = _VALIDATION_CONTEXT.get()
    return current.bytes(path) if current is not None else Path(path).read_bytes()


def read_json(path: Path) -> dict[str, Any]:
    from readonly_work_view_cache import note_read
    note_read(path)
    if not path.exists():
        return {}
    try:
        current = _VALIDATION_CONTEXT.get()
        value = current.json(path) if current is not None else json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    from readonly_work_view_cache import note_read
    note_read(path)
    if not path.exists():
        return []
    current = _VALIDATION_CONTEXT.get()
    if current is not None:
        return current.json(path, lines=True)
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
    from department_rotation import prohibit_validation_write
    prohibit_validation_write()
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
    from department_rotation import prohibit_validation_write
    prohibit_validation_write()
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
    from department_rotation import validation_registry
    historical = validation_registry(root)
    if historical is not None:
        return historical
    registry = read_json(root / "data/department-registry.json")
    departments = {
        str(item.get("id", "")): item
        for item in registry.get("departments", [])
        if isinstance(item, dict) and item.get("id")
    }
    if not departments:
        raise WorkflowError("缺少有效的 data/department-registry.json")
    from department_autonomy import HistoricalRegistry
    return HistoricalRegistry(departments,registry.get('historical_departments',{}))


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
    from department_autonomy import autonomous_goal
    original_snapshot=read_json(snapshot_path(root,task_id)) or {'task_id':task_id}
    if autonomous_goal(original_snapshot.get('goal_delivery')):
        for i,event in enumerate(task_events):
            if event.get('state')=='closed' and i!=len(task_events)-1:
                if any(e.get('state')!='closed'for e in task_events[i+1:]):invalid.append('autonomous_closed_task_cannot_reopen')
        return invalid
    reviewer = _final_qa_department(root, original_snapshot, preparation_only=True)
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
        if details.get("same_state_formal_qa_commit"):
            earlier = task_events[:index]
            prior_formal = next((row for row in reversed(earlier)
                                 if row.get("state") == "qa_passed"
                                 and row.get("details", {}).get("qa_receipt_id")), None)
            qa_source = qa_by_id.get(str(details.get("qa_receipt_id") or ""), {})
            prior_close = next((row for row in reversed(earlier)
                                if row.get("state") == "closed"), None)
            if (state not in {"qa_passed", "closed"} or last_rank != rank[state]
                    or details.get("reconciled") is not True
                    or not matching_qa_verdict(event, "pass")
                    or not prior_formal or not qa_source
                    or _parse_observed_at(prior_formal.get("created_at")) is None
                    or _parse_observed_at(qa_source.get("created_at")) is None
                    or _parse_observed_at(prior_formal["created_at"])
                    >= _parse_observed_at(qa_source["created_at"])
                    or (state == "closed" and (not prior_close
                        or _parse_observed_at(prior_close.get("created_at")) is None
                        or _parse_observed_at(qa_source["created_at"])
                        > _parse_observed_at(prior_close["created_at"])))
                    or any(row.get("state") == "qa_passed"
                           and row.get("details", {}).get("qa_receipt_id") == details.get("qa_receipt_id")
                           for row in earlier)
                    or any(row.get("details", {}).get("same_state_formal_qa_commit")
                           and row.get("details", {}).get("qa_receipt_id") == details.get("qa_receipt_id")
                           for row in earlier)):
                invalid.append("event_order:unverified_same_state_qa_commit")
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
        raise WorkflowError("new runtime tasks require one complete professional goal")
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
        from department_autonomy import autonomous_goal,required_roles,current_mode,ASSISTANTS
        if not snapshot_path(root,task_id).exists() and current_mode(root):
            if not autonomous_goal(goal_delivery) or any(x['department']in ASSISTANTS for x in selected):
                raise WorkflowError('new ordinary tasks use professional autonomous delivery; no assistant assignment')
        planned_roles = {x["department"] for x in selected}
        if not required_roles(goal_delivery) <= planned_roles:
            raise WorkflowError("complete-goal original producers must be planned")
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
        payload_sha256 = str(snapshot.get("request_hash", ""))
        if goal_scope == "department_health_probe:" + department:
            # A workflow request hash describes the original request. The
            # transport policy checks the bytes of the actual health packet.
            payload_sha256 = _health_probe_packet_hash(root, snapshot, department, goal_scope)
        reasons, _ = _routing_precheck(
            root, policy=policy, departments=registry, sender_department="operations",
            source_project_id=str(routing.get("source_project_id", "")),
            target_project_id=str(binding.get("project_id", "")),
            target_department=department,
            target_thread_id=str(item.get("chat_task_id", "")),
            target_thread_title=str(binding.get("title", "")),
            target_cwd=str(binding.get("cwd", "")),
            target_sidebar_section_id=str(binding.get("sidebar_section_id", "")),
            payload_sha256=payload_sha256,
            action_class="thread_message",
            task_id=task_id,
            scope=goal_scope,
            allow_unhealthy_target_for_quarantine=(
                goal_scope == "department_health_probe:" + department
                and exact_health_probe(root, snapshot, sender="operations", target=department,
                                       scope=goal_scope, payload_sha256=payload_sha256)
            ),
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
        from department_autonomy import historical_source_bytes
        raw=historical_source_bytes(root,rel_path(root,path))
        if raw is not None:return {'path':rel_path(root,path),'sha256':hashlib.sha256(raw).hexdigest(),'size':len(raw)}
        raise WorkflowError(f"证据文件不存在或不是文件：{value}")
    raw = validation_bytes(path)
    return {"path": rel_path(root, path), "sha256": hashlib.sha256(raw).hexdigest(), "size": len(raw)}


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
    from department_autonomy import autonomous_goal
    autonomous = autonomous_goal(snapshot.get("goal_delivery"))
    handoff_field = "professional_handoff_status" if autonomous else "assistant_handoff_status" if modern else "qa_handoff_status"
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
    expected_status = "ready_for_operations_intake" if autonomous else "ready_for_assistant_acceptance" if modern else "ready_for_qa"
    if str(delivery[handoff_field]).strip() != expected_status:
        raise WorkflowError("内容增长日报 completed 的真实交接状态与当前模式不匹配")

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
    expected_receiver = "operations" if autonomous else snapshot["goal_delivery"]["responsible_assistant"] if modern else "qa"
    if receiver != expected_receiver:
        raise WorkflowError("内容增长日报 completed 的接收者与当前模式不匹配")


def effective_approvals(root: Path) -> dict[str, dict[str, Any]]:
    approvals: dict[str, dict[str, Any]] = {}
    for row in read_jsonl(root / APPROVAL_LEDGER):
        approval_id = str(row.get("approval_id", ""))
        if approval_id:
            approvals[approval_id] = row
    return approvals


def _exact_condo_faq_original_publishing_approval(root, snapshot, task_id, action_id,
                                                    action_class, scope, source_thread_id,
                                                    source_message_ref, cas_validation=None):
    """Map the actual human CMS instruction to one publisher action after real gates.

    This never creates a standing authorization or a reviewer PASS. The normal
    active single-use approval ledger and protected permit consumer remain.
    """
    if task_id != "fc-20261014-condo-faq-v7-cms-publishing-v1" or action_class != "cms_write":
        return None
    from managed_cms_permit_issuer import CONDO_FAQ_V7_TARGET, validate_goal_cms_policy
    target = CONDO_FAQ_V7_TARGET
    if (action_id != target["action_id"] or scope != target["scope"]
            or source_thread_id != "example-native-51808768551cf834"
            or source_message_ref != "example-native-bb806d191c30327d"):
        raise WorkflowError("original condo FAQ approval requires its exact action and human source")
    goal = snapshot.get("goal_delivery", {})
    authority = goal.get("authorization_pin", {})
    if (goal.get("parent_task_id") != "fc-20261010-assistant1-remaining-business-continuation-v2"
            or goal.get("primary_owner") != "content-organic-website"
            or goal.get("responsible_assistant") != "operations-assistant"
            or goal.get("producer_departments") != ["content-organic-website", "publishing"]
            or goal.get("authorized_scope") != [scope]
            or goal.get("source_mode") != "approved_dispatch"
            or goal.get("required_execution_actions") != [{"action_id": action_id,
                "action_class": action_class, "scope": scope, "department": "publishing"}]
            or goal.get("target_reference", {}).get("record_id") != target["record_id"]
            or goal.get("target_reference", {}).get("changed_fields") != target["changed_fields"]
            or snapshot.get("goal_contract", {}).get("sha256") != "fa7aae6bd9791360386c9ffb6eb049ed1e868005993a50536dc2708553219967"
            or authority.get("sha256") != "463bbf764c280221a55e16fb17023dcce94f2041ba3984001cf570a91abe405b"
            or file_digest(root, authority.get("path", "")) != authority):
        raise WorkflowError("original condo FAQ goal, exact publisher and authority bytes required")
    human = read_json(safe_path(root, authority["path"]))
    if (human.get("source_thread_id") != source_thread_id
            or human.get("message", {}).get("id") != source_message_ref
            or goal.get("human_authorization", {}).get("source_thread_id") != source_thread_id
            or goal.get("human_authorization", {}).get("message_id") != source_message_ref
            or goal.get("human_authorization", {}).get("executor") != "content-organic-website"
            or goal.get("human_authorization", {}).get("scope") != scope
            or goal.get("publication_authority_context", {}).get("standing_grantee") != "content-organic-website"
            or goal.get("publication_authority_context", {}).get("new_account_or_spend_authority_added") is not False):
        raise WorkflowError("original human CMS instruction cannot be transferred as standing publisher authority")
    context = validate_goal_cms_policy(root, task_id, action_id, scope, "publishing",
                                       target["payload_sha256"])
    if (context.get("acceptance_model") != "condo_faq_v7_candidate_scope_only_v1"
            or context.get("goal_completion_claimed") is not False
            or context.get("preflight", {}).get("payload_sha256") != target["payload_sha256"]):
        raise WorkflowError("real A1 candidate-only acceptance and publisher self-check required")
    if cas_validation is None:
        raise WorkflowError("original condo approval must start from a pre-validation byte baseline")
    cas_pins = _exact_condo_approval_cas_pins(root, cas_validation, context)
    return {"authorization_pin": authority, "candidate_acceptance_record_id": context["acceptance_receipt_id"],
            "cas_pins": cas_pins}


def _exact_condo_approval_cas_pins(root, validation, context=None):
    """Use the same request byte cache before review, after review and in-lock."""
    from managed_cms_permit_issuer import (CONDO_FAQ_PARENT_RESULT, CONDO_FAQ_PARENT_REVIEW,
                                           CONDO_FAQ_PUBLISHER_RESULT, CONDO_FAQ_V7_TARGET,
                                           CONDO_FAQ_V7_BASE)
    task = "fc-20261014-condo-faq-v7-cms-publishing-v1"
    parent = "fc-20261010-assistant1-remaining-business-continuation-v2"
    paths = {snapshot_path(root,task), receipts_path(root,task), result_handoff_path(root,task),
             snapshot_path(root,parent), receipts_path(root,parent), result_handoff_path(root,parent),
             root/WORKFLOW_EVENTS, root/POLICY_DECISIONS, root/APPROVAL_LEDGER,
             root/"data/department-registry.json", root/"data/action-policy.json",
             root/"data/department-current-assignment.json",
             *(root/"tools"/name for name in ("managed_cms_permit_issuer.py",
                 "workflow_control.py", "goal_continuity.py", "qa_review_plan.py",
                 "goal_delivery_runtime.py", "result_coordination.py"))}
    paths.update(path for path in (root/CONDO_FAQ_V7_BASE).glob("*.json") if path.is_file())
    for path in paths:
        validation.bytes(path)

    def source(pin):
        if not isinstance(pin,dict) or not all(key in pin for key in ("path","sha256","size")):
            raise WorkflowError("exact condo approval source pin required")
        path = safe_path(root,pin["path"])
        raw = validation.bytes(path)
        if hashlib.sha256(raw).hexdigest()!=pin["sha256"] or len(raw)!=pin["size"]:
            raise WorkflowError("exact condo approval source changed before validation")
        return path

    for pin in (CONDO_FAQ_PARENT_RESULT, CONDO_FAQ_PARENT_REVIEW, CONDO_FAQ_PUBLISHER_RESULT):
        source(pin)
    goal_snapshot = validation.json(snapshot_path(root,task))
    authorization = goal_snapshot.get("goal_delivery",{}).get("authorization_pin")
    source(authorization)
    for value in (CONDO_FAQ_V7_TARGET["candidate"], CONDO_FAQ_V7_TARGET["rollback"]):
        source({"path":value[0],"sha256":value[1],
                "size":safe_path(root,value[0]).stat().st_size})
    if context is None:
        # Only the current genuine A1 receipt is expanded. Historical outboxes
        # may contain old pins that are not this approval's validation inputs.
        rows = validation.json(receipts_path(root,task),lines=True)
        a1 = [row for row in rows if row.get("receipt_type")=="outbox_received"
              and row.get("department")=="operations-assistant"]
        if a1:
            evidence = a1[-1].get("evidence",[])
            for pin in evidence:
                path = source(pin)
                if path.suffix==".json":
                    value = validation.json(path)
                    def leaves(item):
                        if isinstance(item,dict):
                            if all(key in item for key in ("path","sha256","size")):
                                source(item)
                            for child in item.values():leaves(child)
                        elif isinstance(item,list):
                            for child in item:leaves(child)
                    leaves(value)
        # The publisher outbox itself is current, so capture its direct pins.
        publisher = validation.json(safe_path(root,CONDO_FAQ_PUBLISHER_RESULT["path"]))
        for item in publisher.get("evidence",{}).values() if isinstance(publisher.get("evidence"),dict) else []:
            if isinstance(item,dict) and all(key in item for key in ("path","sha256","size")):
                source(item)
    else:
        def required(item):
            if isinstance(item,dict):
                if all(key in item for key in ("path","sha256","size")):
                    path = safe_path(root,item["path"])
                    entry = validation.files.get(str(path.resolve()))
                    if entry is None or entry["sha256"]!=item["sha256"] or len(entry["raw"])!=item["size"]:
                        raise WorkflowError("approval validation used an unfrozen evidence leaf")
                for child in item.values():required(child)
            elif isinstance(item,list):
                for child in item:required(child)
        required(context)
    validation.recheck()
    if len(validation.files)>500:
        raise WorkflowError("exact condo approval validation dependency set unexpectedly enlarged")
    return [{"path":rel_path(root,Path(path)),"sha256":entry["sha256"],"size":len(entry["raw"])}
            for path,entry in sorted(validation.files.items())]

def _record_approval_impl(
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
    cas_validation=None,
    source_evidence: str = "",
) -> tuple[dict[str, Any], list[Path]]:
    task_id = validate_task_id(task_id)
    if not action_id.strip() or not action_class.strip() or not scope.strip():
        raise WorkflowError("approval-record 需要精确的 action_id、action_class 和 scope")
    if source_evidence:
        from wardrobe_site_publish_runtime import applies as wardrobe_applies
        if not wardrobe_applies(task_id, action_class) or revoke:
            raise WorkflowError("source evidence is only for the original active wardrobe site release")
    workflow_snapshot = read_json(snapshot_path(root, task_id))
    if not workflow_snapshot:
        raise WorkflowError(f"工作流不存在：{task_id}")
    read_only_account_approval = action_class == "account_read"
    exact_condo = None if revoke else _exact_condo_faq_original_publishing_approval(
        root, workflow_snapshot, task_id, action_id, action_class, scope,
        source_thread_id, source_message_ref, cas_validation)
    from wardrobe_site_publish_runtime import applies as wardrobe_applies, validate as validate_wardrobe
    exact_wardrobe = (validate_wardrobe(root, workflow_snapshot, action_id, scope,
                       source_thread_id, source_message_ref, source_evidence)
                      if not revoke and wardrobe_applies(task_id, action_class) else None)
    if (
        not revoke
        and not read_only_account_approval
        and exact_condo is None
        and exact_wardrobe is None
        and workflow_snapshot.get("current_state") != "waiting_owner_approval"
    ):
        raise WorkflowError("批准记录被阻止：工作流必须先通过 QA 并进入 waiting_owner_approval")
    generated_id = approval_id.strip() or "apr-" + sha256_value(
        [task_id, action_id, action_class, scope, source_thread_id, source_message_ref]
    )[:20]
    if exact_condo is not None or exact_wardrobe is not None:
        expected_id = "apr-" + sha256_value(
            [task_id, action_id, action_class, scope, source_thread_id, source_message_ref]
        )[:20]
        if generated_id != expected_id:
            raise WorkflowError("original exact approval ID must be source-derived and single-use")
    with workflow_lock(root):
        current_snapshot = read_json(snapshot_path(root, task_id))
        if exact_condo is not None:
            if (current_snapshot != workflow_snapshot or cas_validation is None):
                raise WorkflowError("original condo FAQ approval source changed before single-use CAS")
            cas_validation.recheck()
        if exact_wardrobe is not None:
            if current_snapshot != workflow_snapshot:
                raise WorkflowError("original wardrobe goal changed before issuance")
            if validate_wardrobe(root, current_snapshot, action_id, scope,
                    source_thread_id, source_message_ref, source_evidence) != exact_wardrobe:
                raise WorkflowError("original wardrobe source changed before issuance")
        if (
            not revoke
            and not read_only_account_approval
            and exact_condo is None
            and exact_wardrobe is None
            and current_snapshot.get("current_state") != "waiting_owner_approval"
        ):
            raise WorkflowError("批准记录被阻止：工作流状态在写入前已变更")
        approvals = effective_approvals(root)
        if exact_condo is not None and any(
            row.get("task_id") == task_id and row.get("action_id") == action_id
            and row.get("action_class") == action_class and row.get("scope") == scope
            and row.get("approval_id") != generated_id for row in approvals.values()
        ):
            raise WorkflowError("original condo FAQ already has another single-use approval identity")
        if exact_wardrobe is not None and any(
            row.get("task_id") == task_id and row.get("action_class") == "site_publish"
            and row.get("status") in {"active", "consumed"}
            and row.get("approval_id") != generated_id for row in approvals.values()
        ):
            raise WorkflowError("original wardrobe already has an active or used site approval")
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
                if exact_wardrobe is not None and existing.get("status") != "active":
                    raise WorkflowError("original wardrobe site approval already used or revoked")
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
            if exact_condo is not None:
                record.update(approval_basis="original_exact_condo_publishing_v1",
                              original_human_authorization_pin=exact_condo["authorization_pin"],
                              candidate_acceptance_record_id=exact_condo["candidate_acceptance_record_id"])
            if exact_wardrobe is not None:
                record.update(approval_basis="original_wardrobe_r3_source_preflight_v1",
                              original_human_authorization_pin=exact_wardrobe["authorization_pin"],
                              source_preflight=exact_wardrobe["request"],
                              expected_main_sha=exact_wardrobe["expected_main_sha"],
                              deployment_object=exact_wardrobe["object"],
                              execution_department=exact_wardrobe["department"],
                              platform_run_permission_issued=False)
        append_jsonl_locked(root / APPROVAL_LEDGER, record)
    result = {**record, "result": "revoked" if revoke else "recorded"}
    return result, [root / APPROVAL_LEDGER]


def record_approval(
    root: Path, *, task_id: str, action_id: str, action_class: str, scope: str,
    approval_id: str = "", source_thread_id: str = "", source_message_ref: str = "",
    revoke: bool = False, source_evidence: str = "",
) -> tuple[dict[str, Any], list[Path]]:
    """For the exact condo action, preserve one read baseline through commit."""
    kwargs = dict(task_id=task_id, action_id=action_id, action_class=action_class,
                  scope=scope, approval_id=approval_id,
                  source_thread_id=source_thread_id,
                  source_message_ref=source_message_ref, revoke=revoke,
                  source_evidence=source_evidence)
    if (not revoke and task_id == "fc-20261014-condo-faq-v7-cms-publishing-v1"
            and action_class == "cms_write"):
        with request_validation_context() as validation:
            validation.strict_unchanged = True
            _exact_condo_approval_cas_pins(root, validation)
            return _record_approval_impl(root, **kwargs, cas_validation=validation)
    return _record_approval_impl(root, **kwargs)


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
    executor_binding: dict[str, Any] | None = None,
) -> dict[str, Any]:
    authorization_id = str(authorization.get("authorization_id") or "")
    approval_id = "apr-standing-" + sha256_value(
        [authorization_id, task_id, action_id, action_class, scope] + ([executor_binding] if executor_binding else [])
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
        if executor_binding:
            approval['issuer_executor_binding'] = executor_binding
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
    from result_coordination import notification_plan, result_lane, validate_notification_delivery
    # Modern notices name their exact frozen delivery key. Authenticate that
    # source directly; an unrelated historical result cannot block its policy.
    matches = None
    match = re.fullmatch(r'notify-result-([0-9a-f]{64})',str(requested.get('action_id','')))
    if match:
        original=read_json(safe_path(root,'logs/result-notifications/'+match[1]+'.json'))
        if original:
            from result_coordination import exact_identity, _validate_queued
            from department_autonomy import MODE
            identity=exact_identity(original.get('identity',{}));route=result_lane(root,identity)
            if route.get('source_mode')==MODE:
                if (identity['task_id']!=task_id or identity['sender_department']!=sender
                        or original.get('payload',{}).get('sha256')!=requested.get('payload_sha256')):
                    return ['exact_original_notification_identity_required']
                _validate_queued(root,identity)
                matches=[original]
    if matches is None:
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
    if route.get("lane") == "HQ_knowledge" and route.get("notification_proven") is not True:
        from department_autonomy import MODE, authority
        if route.get('source_mode') != MODE:
            return ["accepted_exact_assistant_summary_required"]
        authority(root)  # Real owner mode source; exact queue/lease checks follow.
    binding = department_registry(root).get(route.get("target_department"), {}).get("chat_binding", {})
    expected = {"target_department": route.get("target_department"),
                "target_thread_id": binding.get("task_id"), "target_thread_title": binding.get("title"),
                "target_project_id": binding.get("project_id"), "target_cwd": binding.get("cwd"),
                "target_sidebar_section_id": binding.get("sidebar_section_id"),
                "action_class": "thread_message", "action_id": "notify-result-" + notice["dedupe_key"].split(":",1)[-1]}
    if notice.get("state") != "prepared" or any(requested.get(k) != v for k, v in expected.items()):
        return ["exact_prepared_notification_target_and_action_required"]
    source_binding = department_registry(root).get(sender, {}).get("chat_binding", {})
    if requested.get("source_project_id") != source_binding.get("project_id"):
        return ["notification_original_source_project_required"]
    try:
        if file_digest(root, notice["payload"]["path"]) != notice["payload"]:
            raise WorkflowError("notification payload changed")
        validate_notification_delivery(root,identity)
    except (WorkflowError, ValueError, OSError, KeyError, TypeError) as error:
        return ["notification_exact_current_claim_required:" + str(error)]
    return []




def _completion_actual_final(root, native, role, *, turn_id=None, message_id=None, reply_ref=None):
    import qa_review_plan as q
    from goal_delivery_runtime import _collaboration_final_message
    q._review_native_containers(native)
    fixed = department_registry(root)[role]["chat_binding"]
    thread = native.get("thread", {})
    if (thread.get("id") != fixed["task_id"]
            or any(thread.get(k) != fixed[v] for k,v in (("title","title"),("cwd","cwd")))
            or ("projectId" in thread and thread["projectId"] != fixed["project_id"])):
        raise WorkflowError("actual completed final fixed identity differs")
    if isinstance(native.get("turns"),list):
        matches=[]
        for turn in native["turns"]:
            q._review_native_containers(turn)
            for message in turn.get("items",[]):
                if (message.get("type")=="agentMessage" and message.get("phase")=="final_answer"
                        and (turn_id is None or turn.get("id")==turn_id)
                        and (message_id is None or message.get("id")==message_id)
                        and (reply_ref is None or reply_ref in {message.get("id"),turn.get("id")})):
                    matches.append((turn,message))
        if len(matches)!=1:
            raise WorkflowError("one exact native completed final message required")
        turn,message=matches[0]
    else:
        message=_collaboration_final_message(native,fixed["task_id"])
        turn=native.get("turn") or {"id":native.get("turn_id"),"status":native.get("status"),
                                  "completedAt":native.get("completedAt")}
        if ((turn_id is not None and turn.get("id")!=turn_id)
                or (message_id is not None and message.get("id")!=message_id)
                or (reply_ref is not None and reply_ref not in {message.get("id"),turn.get("id")})):
            raise WorkflowError("exact original final selector required")
    q._review_native_containers(turn);q._review_native_containers(message)
    if (turn.get("status")!="completed" or turn.get("error")
            or message.get("phase")!="final_answer" or not isinstance(message.get("text"),str)
            or not message["text"].strip()):
        raise WorkflowError("actual completed nonempty final required")
    return turn,message


def validate_health_reply(root, *, department, native_pin, reply_ref, reply_sha256, reply_observed_at):
    from goal_delivery_runtime import _native_document, _collaboration_final_message
    if not isinstance(native_pin,dict):
        raise WorkflowError("actual original native health reply pin required")
    document = _native_document(root,native_pin)
    fixed = department_registry(root)[department]["chat_binding"]
    thread = document.get("thread",{})
    if any(thread.get(k)!=fixed[v] for k,v in (("id","task_id"),("title","title"),("cwd","cwd"))):
        raise WorkflowError("actual native health fixed identity differs")
    turn,message = _completion_actual_final(root,document,department,reply_ref=reply_ref)
    completed = turn.get("completedAt")
    actual_time = (dt.datetime.fromtimestamp(completed,dt.timezone.utc)
                   if isinstance(completed,(int,float)) and not isinstance(completed,bool)
                   else _parse_observed_at(completed))
    observed = _parse_observed_at(reply_observed_at)
    if (actual_time is None or observed != actual_time
            or hashlib.sha256(message["text"].encode("utf-8")).hexdigest()!=reply_sha256):
        raise WorkflowError("health reply hash and original completion time required; no cache refresh")
    return {"native_reply":native_pin,"reply_observed_at":actual_time.isoformat(),
            "source_turn_id":turn["id"],"source_message_id":message["id"]}


def _health_probe_packet_hash(root, snapshot, target, scope):
    """Resolve transport bytes without changing the immutable request hash."""
    try:
        fixed = department_registry(root)[target]["chat_binding"]
        expected = {"schema_version": "goal-health-probe-v1", "task_id": snapshot["task_id"],
                    "target_department": target, "target_thread_id": fixed["task_id"],
                    "scope": scope, "request": "请仅确认当前项目、目录、固定身份是否一致及是否可接续。"}
        contract = read_json(root / "data/task-contract.json").get("goal_delivery_runtime", {})
        pins = [contract.get("health_probe_packets", {}).get(snapshot["task_id"])]
        pins.extend(action.get("payload") for action in snapshot.get("goal_delivery", {}).get("approved_actions", [])
                    if action.get("scope") == scope)
        valid = {pin["sha256"] for pin in pins if isinstance(pin, dict)
                 and file_digest(root, pin["path"]) == pin
                 and read_json(safe_path(root, pin["path"])) == expected}
        return next(iter(valid)) if len(valid) == 1 else ""
    except (WorkflowError, OSError, ValueError, TypeError, KeyError):
        return ""


def exact_health_probe(root, snapshot, *, sender, target, scope, payload_sha256):
    from goal_delivery_runtime import enabled, validate_goal
    if (not enabled(root, snapshot) or scope != "department_health_probe:" + target
            or scope not in snapshot["goal_delivery"].get("authorized_scope", [])
            or snapshot["goal_delivery"].get("producer_departments") != [target]
            or snapshot["goal_delivery"].get("required_execution_actions")
            or sender not in {"operations", snapshot["goal_delivery"]["responsible_assistant"]}):
        return False
    try:
        contract=validate_goal(root, read_json(safe_path(root, snapshot["goal_contract"]["path"])))
        import goal_delivery_runtime as g
        if (file_digest(root, snapshot["goal_contract"]["path"]) != snapshot["goal_contract"]
                or any(snapshot["goal_delivery"].get(key)!=contract.get(key) for key in
                       (*g.REQUIRED,"human_authorization","authorization_pin","required_execution_actions"))):
            return False
        registry = department_registry(root)
        row = registry[target]
        if (row.get("new_dispatch_enabled") is False
                or row.get("mode") not in {"worker", "coordinator"}
                or (row.get("mode") == "coordinator"
                    and row.get("coordination_authority", {}).get("routine_decisions") is not True)):
            return False
        pins = [action["payload"] for action in snapshot["goal_delivery"].get("approved_actions", [])
                if action.get("payload_sha256") == payload_sha256 and action.get("scope") == scope]
        config = read_json(root / "data/task-contract.json").get("goal_delivery_runtime", {}).get("health_probe_packets", {})
        if snapshot["task_id"] in config:
            pins.append(config[snapshot["task_id"]])
        pins = {pin["path"]:pin for pin in pins if isinstance(pin,dict)}
        valid = []
        for pin in pins.values():
            if file_digest(root,pin["path"]) != pin or pin["sha256"] != payload_sha256:
                continue
            packet = read_json(safe_path(root,pin["path"]))
            expected = {"schema_version":"goal-health-probe-v1", "task_id":snapshot["task_id"],
                        "target_department":target,"target_thread_id":row["chat_binding"]["task_id"],
                        "scope":scope,"request":"请仅确认当前项目、目录、固定身份是否一致及是否可接续。"}
            if packet == expected:
                valid.append(pin)
        if len(valid)!=1:
            return False
        actions=[action for action in snapshot["goal_delivery"].get("approved_actions",[])
                 if action.get("payload_sha256")==payload_sha256 and action.get("scope")==scope]
        live_pins=[action.get("live_identity") for action in actions if action.get("live_identity")]
        current=read_json(root / "data/task-contract.json").get("goal_delivery_runtime",{}).get("health_probe_live_identities",{}).get(snapshot["task_id"])
        if current:live_pins.append(current)
        if len(live_pins)!=1:
            return False
        live=_completion_pin(root,live_pins[0]);at=_parse_observed_at(live.get("observed_at"))
        if at is None or not 0 <= (dt.datetime.now(dt.timezone.utc)-at).total_seconds() <= 300:
            return False
        fixed=row["chat_binding"]
        targets=[item for item in live.get("threads",[]) if item.get("id")==fixed["task_id"]]
        groups=[item for item in live.get("sections",[]) if item.get("sectionId")==fixed["sidebar_section_id"]]
        return (len(targets)==1 and len(groups)==1 and targets[0].get("status")=="idle"
                and all(targets[0].get(k)==fixed[v] for k,v in (("projectId","project_id"),("title","title"),("cwd","cwd")))
                and "codex:thread:local:"+fixed["task_id"] in groups[0].get("itemKeys",[]))
    except (WorkflowError, OSError, ValueError, TypeError, KeyError):
        return False


_A1_HEALTH_HISTORY_TASK = "fc-20261011-assistant1-original-goal-health-recovery-v1"
_A1_HEALTH_HISTORY_REPORT = {
    "path": "logs/handoffs/2026-10-12-daily-result-recovery-2040/assistant2-owned/"
            "readonly-A1-original-health-child-control-residual-v1/"
            "REPORT-A1-original-pure-health-child-actual-evidence-and-bounded-control-residual-diagnosis-v1.json",
    "sha256": "bc66b7d06f1762fb13579a6e5dd1a9ead822673ef1beb07cbe5e4163334c2e7d",
    "size": 69247,
}


def _original_history_row(index: list[dict[str, Any]], number: int) -> dict[str, Any]:
    """Read an exact native session row; the advisory index is never authority alone."""
    matches = [entry for entry in index if entry.get("line") == number]
    if len(matches) != 1:
        raise WorkflowError("one indexed original native source row required")
    entry = matches[0]
    path = Path(str(entry.get("source_session_path") or ""))
    if (not path.is_absolute() or path.suffix != ".jsonl"
            or not path.as_posix().startswith("<USER_HOME>/.codex/sessions/")):
        raise WorkflowError("original native session path required")
    try:
        with path.open("rb") as source:
            raw = next((line for line_no, line in enumerate(source, 1) if line_no == number), None)
        if (raw is None or len(raw) != entry.get("row_bytes")
                or hashlib.sha256(raw).hexdigest() != entry.get("row_sha256")):
            raise WorkflowError("original native row changed or truncated")
        row = json.loads(raw)
    except (OSError, ValueError, TypeError) as error:
        raise WorkflowError("original native row unreadable") from error
    if (row.get("timestamp") != entry.get("timestamp")
            or row.get("type") != entry.get("row_type", entry.get("type"))
            or row.get("payload", {}).get("type") != entry.get("payload_type")):
        raise WorkflowError("original native row identity mismatch")
    return row


def _original_a1_health_history(root: Path, snapshot: dict[str, Any],
                                receipt: dict[str, Any], *, new: bool) -> dict[str, Any]:
    """Authenticate one already completed health action; never qualify a new send."""
    task = _A1_HEALTH_HISTORY_TASK
    target = "operations-assistant"
    scope = "department_health_probe:" + target
    if snapshot.get("task_id") != task or receipt.get("receipt_type") != "health_reconciled":
        raise WorkflowError("only the original A1 pure-health child may reconcile history")
    if file_digest(root, _A1_HEALTH_HISTORY_REPORT["path"]) != _A1_HEALTH_HISTORY_REPORT:
        raise WorkflowError("frozen original A1 diagnosis pin required")
    report = read_json(safe_path(root, _A1_HEALTH_HISTORY_REPORT["path"]))
    policy = report["exact_successful_policy"]["unique_exact_decision"]
    packet_pin = report["exact_packet_and_actual_original_live_identity"]["packet"]
    live_pin = report["exact_packet_and_actual_original_live_identity"]["live"]
    reply_pin = report["actual_completed_native_reply"]["full_source"]
    registry = department_registry(root)
    fixed = registry[target]["chat_binding"]
    source = registry["operations-assistant-2"]["chat_binding"]
    expected = {
        "department": target, "chat_task_id": fixed["task_id"],
        "action_id": policy["action_id"], "action_class": "thread_message",
        "scope": scope, "policy_decision_id": policy["decision_id"],
        "ack_nonempty": False, "verdict": "", "approval_id": "",
        "evidence": [_A1_HEALTH_HISTORY_REPORT],
        "idempotency_key": "original-a1-health:" + policy["decision_id"],
    }
    if any(receipt.get(key) != value for key, value in expected.items()):
        raise WorkflowError("exact historical health receipt identity and idempotency required")
    if (receipt.get("supersedes_receipt_id") or receipt.get("replacement_reason")
            or snapshot.get("request_hash") != report["original_child"]["request_hash"]
            or snapshot.get("goal_delivery", {}).get("producer_departments") != [target]
            or snapshot.get("goal_delivery", {}).get("responsible_assistant") != "operations-assistant-2"
            or snapshot.get("goal_delivery", {}).get("authorized_scope") != [scope]
            or snapshot.get("goal_delivery", {}).get("required_execution_actions")
            or snapshot.get("goal_delivery", {}).get("parent_task_id")
               != "fc-20261010-assistant1-remaining-business-continuation-v2"
            or snapshot.get("owner_approval_required") is not False):
        raise WorkflowError("original pure-health child contract must remain unchanged")
    from goal_delivery_runtime import validate_goal
    contract_pin = snapshot.get("goal_contract")
    if (not isinstance(contract_pin, dict) or file_digest(root, contract_pin["path"]) != contract_pin
            or validate_goal(root, read_json(safe_path(root, contract_pin["path"])))
               != snapshot["goal_delivery"]):
        raise WorkflowError("original complete goal and human authorization required")
    if (fixed.get("task_id") != policy["target_thread_id"]
            or fixed.get("project_id") != policy["target_project_id"]
            or fixed.get("cwd") != policy["target_cwd"]
            or fixed.get("title") != policy["target_thread_title"]
            or fixed.get("sidebar_section_id") != policy["target_sidebar_section_id"]
            or source.get("project_id") != policy["source_project_id"]):
        raise WorkflowError("original fixed health identities changed")
    selected = [row for row in read_jsonl(root / POLICY_DECISIONS)
                if row.get("decision_id") == policy["decision_id"]]
    if len(selected) != 1 or selected[0] != policy or policy.get("status") != "allow":
        raise WorkflowError("unique original allowed policy required")
    if (policy.get("department") != "operations" or policy.get("task_id") != task
            or policy.get("routing_status") != "routing_allowed"
            or policy.get("routing_health_probe_mode") is not True
            or policy.get("payload_sha256") != packet_pin["sha256"]):
        raise WorkflowError("original exact health policy identity required")
    configured = read_json(root / "data/task-contract.json").get("goal_delivery_runtime", {})
    configured_pin = configured.get("health_probe_packets", {}).get(task)
    if (file_digest(root, packet_pin["path"]) != packet_pin
            or not isinstance(configured_pin, dict)
            or file_digest(root, configured_pin["path"]) != configured_pin
            or (configured_pin["sha256"], configured_pin["size"])
               != (packet_pin["sha256"], packet_pin["size"])):
        raise WorkflowError("original complete packet bytes required")
    packet_bytes = safe_path(root, packet_pin["path"]).read_bytes()
    packet = json.loads(packet_bytes)
    if packet != report["exact_packet_and_actual_original_live_identity"]["packet_body"]:
        raise WorkflowError("original pure-health packet body differs")
    live = _completion_pin(root, live_pin)
    observed = _parse_observed_at(live.get("observed_at"))
    checked = _parse_observed_at(policy["checked_at"])
    if observed is None or checked is None or not 0 <= (checked - observed).total_seconds() <= 300:
        raise WorkflowError("original policy was outside its actual live 300-second window")
    targets = [row for row in live.get("threads", []) if row.get("id") == fixed["task_id"]]
    groups = [row for row in live.get("sections", []) if row.get("sectionId") == fixed["sidebar_section_id"]]
    if (len(targets) != 1 or len(groups) != 1 or targets[0].get("status") != "idle"
            or any(targets[0].get(key) != fixed[value] for key, value in
                   (("projectId", "project_id"), ("title", "title"), ("cwd", "cwd")))
            or "codex:thread:local:" + fixed["task_id"] not in groups[0].get("itemKeys", [])):
        raise WorkflowError("original observed fixed target was not idle and exact")
    sender_index = report["actual_sender_native_source_index"]
    receiver_index = report["actual_receiver_FCO_and_final_source_index"]
    policy_call = _original_history_row(sender_index, 85202)["payload"]
    sent = _original_history_row(sender_index, 85208)["payload"]
    fco_row = _original_history_row(receiver_index, 18085)
    final_row = _original_history_row(receiver_index, 18099)
    completed_row = _original_history_row(receiver_index, 18102)
    fco, final, completed = fco_row["payload"], final_row["payload"], completed_row["payload"]
    call = policy_call.get("item", {})
    try:
        policy_output = json.loads(call.get("aggregated_output", ""))
        returned = json.loads(policy_output["return"]["stdout"])
    except (ValueError, TypeError, KeyError) as error:
        raise WorkflowError("original native policy return unreadable") from error
    if (call.get("status") != "completed" or call.get("exit_code") != 0
            or policy_output.get("packet_text") != packet_bytes.decode("utf-8")
            or policy_output.get("payload_sha256") != packet_pin["sha256"]
            or policy_output.get("return", {}).get("exit_code") != 0
            or returned.get("decision_id") != policy["decision_id"]
            or returned.get("status") != "allow"
            or returned.get("routing_health_probe_mode") is not True):
        raise WorkflowError("original native policy call must match allowed packet")
    item = sent.get("item", {})
    send_start = dt.datetime.fromtimestamp(sent.get("started_at_ms", -1) / 1000, dt.timezone.utc)
    send_end = dt.datetime.fromtimestamp(sent.get("completed_at_ms", -1) / 1000, dt.timezone.utc)
    result = item.get("result", {})
    try:
        returned_thread = json.loads(result["content"][0]["text"])["threadId"]
    except (ValueError, KeyError, IndexError, TypeError) as error:
        raise WorkflowError("original native send return unreadable") from error
    if (sent.get("type") != "item_completed"
            or sent.get("thread_id") != report["original_child"]["human_authorization"]["source_thread_id"]):
        raise WorkflowError("original native sender identity required")
    if (item.get("type") != "McpToolCall" or item.get("server") != "codex_app"
            or item.get("tool") != "send_message_to_thread" or item.get("status") != "completed"
            or result.get("isError") is not False
            or item.get("arguments") != {"threadId": fixed["task_id"], "hostId": "local",
                                          "prompt": packet_bytes.decode("utf-8")}
            or returned_thread != fixed["task_id"]
            or not checked <= send_start <= send_end
            or not 0 <= (send_start - observed).total_seconds() <= 300):
        raise WorkflowError("original successful native health send and 300-second window required")
    expected_fco = ("<codex_delegation>\n  <source_thread_id>"
                    + sent["thread_id"] + "</source_thread_id>\n  <input>"
                    + packet_bytes.decode("utf-8") + "</input>\n</codex_delegation>")
    if (fco.get("type") != "function_call_output" or fco.get("name") != "send_message_to_thread"
            or fco.get("namespace") != "codex_app" or fco.get("output") != expected_fco
            or not send_end <= _parse_observed_at(fco_row["timestamp"])
               <= _parse_observed_at(final_row["timestamp"])
               <= _parse_observed_at(completed_row["timestamp"])):
        raise WorkflowError("exact original receiver FCO delivery required")
    content = final.get("content", [])
    reply = content[0].get("text") if len(content) == 1 and isinstance(content[0], dict) else ""
    original = report["actual_completed_native_reply"]
    if (final.get("type") != "message" or final.get("role") != "assistant"
            or final.get("phase") != "final_answer" or final.get("id") != original["final_id"]
            or not isinstance(reply, str) or not reply.strip()
            or hashlib.sha256(reply.encode("utf-8")).hexdigest() != original["reply_sha256"]
            or completed.get("type") != "task_complete"
            or completed.get("turn_id") != original["turn_id"]
            or completed.get("completed_at") != original["completedAt"]):
        raise WorkflowError("genuine original completed nonempty final required")
    checked_reply = validate_health_reply(root, department=target, native_pin=reply_pin,
                                         reply_ref=original["final_id"],
                                         reply_sha256=original["reply_sha256"],
                                         reply_observed_at=report["actual_unique_health_event"]["exact_event"]["reply_observed_at"])
    if (checked_reply["source_turn_id"] != original["turn_id"]
            or checked_reply["source_message_id"] != original["final_id"]
            or send_end > _parse_observed_at(checked_reply["reply_observed_at"])):
        raise WorkflowError("original send, final, and health reply chronology required")
    health = report["actual_unique_health_event"]["exact_event"]
    matching = [row for row in read_jsonl(root / "logs/department-health.jsonl")
                if row.get("event_hash") == health["event_hash"]]
    if (len(matching) != 1 or matching[0] != health
            or sha256_value({key: value for key, value in health.items() if key != "event_hash"})
               != health["event_hash"]
            or health.get("native_reply") != reply_pin or health.get("department") != target
            or health.get("task_id") != fixed["task_id"]
            or health.get("reply_nonempty") is not True
            or health.get("last_run_status") != "success"
            or health.get("reply_ref") != original["final_id"]):
        raise WorkflowError("one unchanged original healthy reply event required")
    event_time = _parse_observed_at(health.get("checked_at"))
    if event_time is None or event_time < _parse_observed_at(checked_reply["reply_observed_at"]):
        raise WorkflowError("health registration must follow the actual final reply")
    if new:
        if (snapshot.get("current_state") != "blocked"
                or snapshot.get("plan_status") != "blocked_route_invalid"
                or read_jsonl(receipts_path(root, task))
                or validate_workflow_events(root, task)):
            raise WorkflowError("original blocked child and empty intact receipt chain required")
        original_events = report["original_child"]["events_exact_selected"]
        present = read_jsonl(root / WORKFLOW_EVENTS)
        for event in original_events:
            if len([row for row in present if row.get("event_id") == event["event_id"]
                    and row.get("event_hash") == event["event_hash"]]) != 1:
                raise WorkflowError("original blocked workflow event history required")
    return {"source_report": _A1_HEALTH_HISTORY_REPORT,
            "packet_sha256": packet_pin["sha256"], "policy_decision_id": policy["decision_id"],
            "native_send_completed_at": send_end.isoformat(),
            "native_reply_completed_at": checked_reply["reply_observed_at"],
            "native_final_id": original["final_id"], "health_event_hash": health["event_hash"],
            "closed_scope_only": True, "business_goal_closed": False}


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
    if action_id == 'assign-same-task-technical-review:fc-20261017-next12-old-house-development-handoff-v1':
        from goal_source_recovery import oldhouse_technical_preflight
        oldhouse_technical_preflight(root,{
            'task_id':task_id,'action_id':action_id,'action_class':action_class,'scope':scope,
            'sender_department':sender_department,'source_project_id':source_project_id,
            'target_project_id':target_project_id,'target_department':target_department,
            'target_thread_id':target_thread_id,'target_thread_title':target_thread_title,
            'target_cwd':target_cwd,'target_sidebar_section_id':target_sidebar_section_id,
            'payload_sha256':payload_sha256})
        return [],['same_task_technical_responsibility:exact_original_sources']
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
    from direct_system_repair import message_precheck as direct_message_precheck
    direct_routing = direct_message_precheck(root, {
        "task_id": task_id, "action_id": action_id, "action_class": action_class, "scope": scope,
        "sender_department": sender_department, "source_project_id": source_project_id,
        "target_project_id": target_project_id, "target_department": target_department,
        "target_thread_id": target_thread_id, "target_thread_title": target_thread_title,
        "target_cwd": target_cwd, "target_sidebar_section_id": target_sidebar_section_id,
        "payload_sha256": payload_sha256})
    if direct_routing is not None:
        return direct_routing, ["human_authorization:exact_direct_internal_repair", "native_identity:fixed_A3_not_busy"]
    if goal_enabled(root, goal_snapshot):
        if action_class == "thread_message" and scope not in goal_snapshot["goal_delivery"]["authorized_scope"]:
            return ["goal_dispatch_scope_outside_contract"], ["goal_delivery:exact_authorized_scope"]
        if action_id == "assign-goal-review:" + task_id:
            contract = goal_snapshot.get("goal_contract")
            from goal_source_recovery import initial_responsibility_payload
            exact_message = initial_responsibility_payload(root,goal_snapshot,sender_department,
                                                          target_department,scope,payload_sha256)
            if (target_department != goal_snapshot["goal_delivery"]["responsible_assistant"]
                    or not isinstance(contract, dict) or file_digest(root, contract.get("path", "")) != contract
                    or payload_sha256 != contract["sha256"] and not exact_message):
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
                    or target_thread_id != "example-native-25e4a2ebb5d53084"
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
            and sender_department in {goal_snapshot["goal_delivery"]["responsible_assistant"], goal_snapshot["goal_delivery"]["primary_owner"]}
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
    if (action_class == "thread_message" and exact_health_probe(root, goal_snapshot,
            sender=sender_department, target=target_department, scope=scope, payload_sha256=payload_sha256)):
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
        original_receipts = [json.loads(line) for line in validation_bytes(receipts_path(root, task_id)).decode("utf-8").splitlines() if line.strip()]
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


_WEEKLY_CLARIFICATION_SOURCE = {
    "task_id": "fc-20261010-weekly-safe-cleanup-native-enablement-v1",
    "scope": "project:flashcast:weekly-safe-cleanup-native-enablement:v1",
    "action_id": "clarify-existing-system-repair-authority-and-bounded-continuation-v1",
    "payload": {
        "path": "logs/handoffs/2026-10-10-weekly-safe-cleanup-native-enablement-v1/actual-native-configuration-v1/HQ-existing-repair-authority-clarification-for-A2-v1.txt",
        "sha256": "5747965e3e976ec5526eb29c444b72dba8d2bf21a29ef7f9721a82fbaae93133", "size": 1416,
    },
    "execution_id": "aba6cc9a-8248-43fd-b546-dbfc72c8e1e4",
    "execution_hash": "7d6a427f8a9f5223e46514e5514486b6dbe59c7e636fc90329460df4e3f0b473",
    "policy_id": "pol-b18670a21481f16f45c2",
    "responsibility_dispatch_id": "c9ba1411-b2b7-4514-a7fe-449f1ade0d15",
    "source_evidence": {
        "path": "logs/handoffs/2026-10-10-weekly-safe-cleanup-native-enablement-v1/actual-native-configuration-v1/native-response-shape-compatibility-rework-needed-v1.json",
        "sha256": "4e57bfc2ab67e8d406dc45159d0783b3463dac5089d1faf4504a07c3e1e45177", "size": 7420,
    },
    "source_manifest": {
        "path": "logs/handoffs/2026-10-10-weekly-safe-cleanup-native-enablement-v1/actual-native-configuration-v1/native-response-shape-source-raw-v1/source-raw-package-manifest.json",
        "sha256": "3680cf28ea6d1108981d9426ba1975f6d3662b9794583b76624955cb913d9f20", "size": 3827,
    },
    "execution_native": {
        "path": "logs/handoffs/2026-10-10-weekly-safe-cleanup-native-enablement-v1/actual-native-configuration-v1/native-response-shape-source-raw-v1/actual-HQ-successful-no-match-policy-create-view-and-notice-session-v1.json",
        "sha256": "7da8b48da86acafe1f5dd422d407049cf62e162182a241b2f7ffaf293125d7a6", "size": 36491,
    },
    "original_thread": {
        "path": "logs/handoffs/2026-10-10-weekly-safe-cleanup-native-enablement-v1/actual-native-configuration-v1/native-response-shape-source-raw-v1/actual-HQ-read-thread-after-create-view-v1.json",
        "sha256": "1136cc677878d8cca1849c0a844e5e9b2ebef0fc665385035e60d46226eed0e3", "size": 1098033,
    },
    "automation_id": "flash-cast-20-00",
}


def _weekly_existing_authority_clarification_ready(
    root: Path, snapshot: dict[str, Any], receipts: list[dict[str, Any]], *,
    sender_department: str, target_department: str, target_thread_id: str,
    action_id: str, scope: str, payload_sha256: str,
) -> bool:
    """Only the original weekly owner's exact existing-authority clarification.

    Read original responsibility and one actual native execution. This is not
    a new assignment, configuration acceptance, external permission or send.
    """
    source = _WEEKLY_CLARIFICATION_SOURCE
    goal = snapshot.get("goal_delivery", {})
    if not (snapshot.get("task_id") == source["task_id"]
            and sender_department == "operations" and target_department == "operations-assistant-2"
            and action_id == source["action_id"] and scope == source["scope"]
            and payload_sha256 == source["payload"]["sha256"]
            and goal.get("source_mode") == "owner_direct" and goal.get("primary_owner") == "operations"
            and goal.get("producer_departments") == ["operations"]
            and goal.get("responsible_assistant") == "operations-assistant-2"
            and goal.get("acceptance_capability") == "functional"
            and goal.get("authorized_scope") == [source["scope"]]
            and not goal.get("assignment_history") and not goal.get("required_execution_actions")):
        return False
    import native_control_result as n
    from goal_delivery_runtime import owner_direct
    _, original_goal, config, registry = n.context(root, snapshot)
    fixed = registry["operations"]["chat_binding"]
    if (target_thread_id != registry[target_department]["chat_binding"]["task_id"]
            or not owner_direct(root, snapshot, "operations")):
        return False
    n.pin(root, source["payload"])
    n.assigned_assistant(root, snapshot, target_department)
    assignments = [row for row in receipts if row.get("receipt_type") == "dispatch_sent"
                   and row.get("department") == target_department
                   and row.get("action_id") == "assign-goal-review:" + source["task_id"]]
    if len(assignments) != 1 or assignments[0].get("receipt_id") != source["responsibility_dispatch_id"]:
        return False
    executions = [row for row in receipts if row.get("receipt_type") == "execution_result"
                  and row.get("department") == "operations"]
    if len(executions) != 1:
        return False
    execution = executions[0]
    expected = config["policy_inputs_only_after_native_exact_no_match"]
    if not (execution.get("receipt_id") == source["execution_id"]
            and execution.get("receipt_hash") == source["execution_hash"]
            and execution.get("policy_decision_id") == source["policy_id"]
            and execution.get("action_id") == expected["action_id"]
            and execution.get("action_class") == "automation_create"
            and execution.get("scope") == source["scope"]
            and execution.get("chat_task_id") == fixed["task_id"]
            and execution.get("evidence") == [source["source_evidence"]]):
        return False
    evidence = n.document(root, source["source_evidence"])
    if (evidence.get("task_id") != source["task_id"] or evidence.get("scope") != source["scope"]
            or evidence.get("source_raw_package_manifest") != source["source_manifest"]):
        return False
    bundle = n.document(root, source["source_manifest"])
    if (bundle.get("schema") != "actual_native_response_shape_source_raw_package/v1"
            or source["execution_native"] not in bundle.get("files", [])
            or source["original_thread"] not in bundle.get("files", [])):
        return False
    # Both raw original call/output and its real fixed thread are required.
    executed = n.native_call(root, source["execution_native"], fixed, "create", thread_source=source["original_thread"])
    viewed = n.native_call(root, source["execution_native"], fixed, "view",
                          automation_id=source["automation_id"], thread_source=source["original_thread"])
    args = executed["args"]
    if not (executed.get("create_receipt") == {"automationId": source["automation_id"], "mode": "create", "status": "ACTIVE"}
            and executed["turn_id"] == viewed["turn_id"] and executed["output_index"] < viewed["index"]
            and viewed["args"] == {"mode": "view", "id": source["automation_id"]}
            and args.get("kind") == "heartbeat" and args.get("status") == "ACTIVE"
            and args.get("targetThreadId") == expected["target_thread_id"]
            and isinstance(args.get("prompt"), str)
            and args["prompt"].encode("utf-8") == safe_path(root, n.pin(root, config["prompt"])["path"]).read_bytes()):
        return False
    n.weekly_rule(args.get("rrule"))
    policies = [row for row in read_jsonl(root / POLICY_DECISIONS) if row.get("decision_id") == source["policy_id"]]
    if len(policies) != 1:
        return False
    policy = policies[0]
    if not (policy.get("status") == "allow" and policy.get("routing_status") == "routing_allowed"
            and all(policy.get(key) == value for key, value in expected.items())):
        return False
    policy_at, executed_at = _parse_observed_at(policy.get("checked_at")), _parse_observed_at(execution.get("created_at"))
    if not (policy_at is not None and executed_at is not None
            and policy_at.timestamp() <= executed["started"] <= executed["output_time"] <= executed_at.timestamp()
            and executed_at <= dt.datetime.now(dt.timezone.utc)):
        return False
    matches = []
    for index, item in enumerate(executed["items"][:executed["index"]]):
        if item.get("type") == "custom_tool_call_output" and item.get("call_id"):
            value = n._session_output(item)
            if n._weekly_policy_output_matches(root, snapshot, config, policy, executed, index, value):
                matches.append(index)
    return len(matches) == 1


def _responsibility_initial_ready(root, snapshot, sender, target, action_id, scope, payload_sha256):
    from parent_initial_dispatch import validate_responsibility_action
    rows = [row for row in snapshot.get("goal_delivery", {}).get("approved_actions", [])
            if row.get("goal_responsibility_dispatch") and all(row.get(k)==v for k,v in
                {"sender_department":sender,"target_department":target,"action_id":action_id,
                 "scope":scope,"payload_sha256":payload_sha256}.items())]
    if len(rows)!=1:
        return False
    try:
        validate_responsibility_action(root,snapshot,rows[0],phase="policy")
        return True
    except (WorkflowError,OSError,ValueError,TypeError,KeyError):
        return False


def _target_dispatch_plan_ready(root, snapshot, department):
    """A stale unrelated lane must not stop an otherwise ready goal participant.

    This only scopes the plan-status check. Routing, source authority,
    dependency and actual action/receipt checks remain at their existing gates.
    """
    if snapshot.get("plan_status") == "ready_to_send":
        return True
    if (root is None or not isinstance(snapshot.get("goal_delivery"), dict)
            or snapshot.get("plan_status") not in {"blocked_health_stale", "blocked_chat_health"}):
        return False
    rows = [r for r in snapshot.get("departments", []) if r.get("department") == department]
    roles = department_registry(root)
    role = roles.get(department, {})
    binding = role.get("chat_binding", {})
    ttl = int(read_json(root / "data/department-registry.json").get("health_policy", {}).get("verification_ttl_hours", 26))
    return (len(rows) == 1 and role.get("new_dispatch_enabled") is not False
            and rows[0].get("chat_task_id") == binding.get("task_id")
            and _chat_binding_healthy(binding, verification_ttl_hours=ttl))


def _ordinary_thread_dispatch_precheck(
    root: Path, *, snapshot: dict[str, Any], task_id: str,
    target_department: str, target_thread_id: str, action_id: str, scope: str,
    sender_department: str = "", payload_sha256: str = "", original_message: dict | None = None,
) -> list[str]:
    """Reject unreceiptable or already-sent ordinary messages before sending.

    Read the same snapshot and receipt chain used by record_receipt. This
    check creates no workflow, refreshes no binding and grants no authority.
    """
    if action_id == 'assign-same-task-technical-review:fc-20261017-next12-old-house-development-handoff-v1':
        from goal_source_recovery import oldhouse_technical_preflight
        registry=department_registry(root)
        source=registry[sender_department]['chat_binding']
        target=registry[target_department]['chat_binding']
        oldhouse_technical_preflight(root,{
            'task_id':task_id,'action_id':action_id,'action_class':'thread_message','scope':scope,
            'sender_department':sender_department,'source_project_id':source['project_id'],
            'target_project_id':target['project_id'],'target_department':target_department,
            'target_thread_id':target_thread_id,'target_thread_title':target['title'],
            'target_cwd':target['cwd'],'target_sidebar_section_id':target['sidebar_section_id'],
            'payload_sha256':payload_sha256})
        return []
    reasons: list[str] = []
    from original_task_publisher_handover import dispatch_precheck
    reasons.extend(dispatch_precheck(root, snapshot, target_department, target_thread_id, action_id, scope))
    if not snapshot or snapshot.get("task_id") != task_id:
        return ["thread_dispatch_workflow_missing_or_identity_invalid"]
    from department_rotation import current_dispatch_snapshot
    original_targets = {item.get("chat_task_id") for item in snapshot.get("departments", [])
                        if item.get("department") == target_department}
    snapshot = current_dispatch_snapshot(root, snapshot, target_department, action_id=action_id)
    equivalent_targets = {item.get("chat_task_id") for item in snapshot.get("departments", [])
                          if item.get("department") == target_department}
    if equivalent_targets == {target_thread_id}:
        equivalent_targets |= original_targets
    else:
        equivalent_targets = {target_thread_id}
    if not snapshot or snapshot.get("task_id") != task_id:
        return ["thread_dispatch_workflow_missing_or_identity_invalid"]
    if snapshot.get("current_state") in TERMINAL_STATES:
        reasons.append("thread_dispatch_workflow_terminal")
    if snapshot.get("workflow_successor_link"):
        reasons.append("thread_dispatch_existing_successor_no_redispatch")
    if not _target_dispatch_plan_ready(root, snapshot, target_department):
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
    observation = None
    if original_message is not None:
        from qa_review_plan import original_result_continuation_intent
        expected = {'task_id': task_id, 'sender_department': sender_department, 'target_department': target_department,
                    'target_thread_id': target_thread_id, 'action_id': action_id, 'scope': scope,
                    'payload_sha256': payload_sha256, 'action_class': 'thread_message'}
        if (invalid or not isinstance(original_message, dict)
                or any(original_message.get(k) != v for k, v in expected.items())):
            raise WorkflowError('exact original observation message and routing required')
        observation = original_result_continuation_intent(root, snapshot, original_message)
        if observation is None:
            raise WorkflowError('only a verified finite original-result observation has scoped dependencies')
    from goal_delivery_runtime import enabled as goal_enabled, completion_dependencies
    if goal_enabled(root, snapshot) and len(planned) == 1:
        goal = snapshot["goal_delivery"]
        initial_review_assignment = (target_department == goal["responsible_assistant"]
                                     and action_id == "assign-goal-review:" + task_id and snapshot.get("goal_contract"))
        # A prior ACK does not replace the producer result dependency.
        responsibility_resume = (not invalid and _coordination_responsibility_resume_ready(
            root, snapshot, receipts, sender_department=sender_department,
            target_department=target_department, target_thread_id=target_thread_id,
            scope=scope, payload_sha256=payload_sha256,
        ))
        if not invalid and not responsibility_resume:
            from department_rotation import frozen_responsibility_continuation
            responsibility_resume = frozen_responsibility_continuation(
                root, snapshot, receipts, sender_department=sender_department,
                target_department=target_department, target_thread_id=target_thread_id, scope=scope)
        original_weekly_clarification = (not invalid and _weekly_existing_authority_clarification_ready(
            root, snapshot, receipts, sender_department=sender_department,
            target_department=target_department, target_thread_id=target_thread_id,
            action_id=action_id, scope=scope, payload_sha256=payload_sha256,
        ))
        if not initial_review_assignment:
            for dep in planned[0].get("depends_on", []):
                if observation is not None:
                    # Existing immutable bytes have already been received.
                    # Other professional outputs gate their business actions,
                    # never this strictly non-executing read/source/ACK input.
                    continue
                if (responsibility_resume or original_weekly_clarification or _responsibility_initial_ready(
                        root, snapshot, sender_department, target_department, action_id, scope, payload_sha256)) and dep == "operations":
                    continue
                delivered=any(r.get("receipt_type") == "outbox_received" and r.get("department") == dep for r in receipts)
                if not delivered:
                    from goal_continuity import frozen_dependency_available
                    delivered=frozen_dependency_available(root,task_id,dep)
                if not delivered:
                    reasons.append("goal_dispatch_dependency_missing:" + dep)
        unmet = completion_dependencies(root, snapshot)
        for dependency in goal["dependencies"]:
            if observation is not None:
                continue
            affects = dependency.get("applies_to", [dependency.get("department")])
            if target_department in affects and any(x.startswith("external_dependency:" + dependency.get("id", "") + ":") for x in unmet):
                reasons.append("goal_dispatch_named_dependency_missing:" + dependency["id"])
    decisions = {row.get("decision_id"): row
                 for row in read_jsonl(root / POLICY_DECISIONS)}
    for receipt in receipts:
        if (receipt.get("receipt_type") != "dispatch_sent"
                or receipt.get("department") != target_department
                or receipt.get("chat_task_id") not in equivalent_targets):
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
            and decision.get("target_thread_id") in equivalent_targets
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
    draft_admission: dict | None = None,
    original_message: dict | None = None,
) -> tuple[dict[str, Any], list[Path]]:
    from department_rotation import prohibit_validation_write
    prohibit_validation_write()
    task_id = validate_task_id(task_id)
    if original_message is not None and action_class != 'thread_message':
        raise WorkflowError('original-result observation cannot authorize an execution action')
    if original_message is not None and action_class == 'thread_message':
        from department_autonomy import message_route,message_policy
        if message_route(root,read_json(snapshot_path(root,task_id)),original_message) is not None:
            expected=dict(task_id=task_id,sender_department=department,action_id=action_id,action_class=action_class,scope=scope,source_project_id=source_project_id,target_project_id=target_project_id,target_department=target_department,target_thread_id=target_thread_id,target_thread_title=target_thread_title,target_cwd=target_cwd,target_sidebar_section_id=target_sidebar_section_id,payload_sha256=payload_sha256)
            if any(original_message.get(k)!=v for k,v in expected.items()):
                raise WorkflowError('autonomous exact normal policy input differs')
            return message_policy(root,original_message),[root/POLICY_DECISIONS]
    if draft_admission is not None:
        from chatgpt_fe689_draft_admission import policy as exact_draft_policy
        return exact_draft_policy(root, dict(task_id=task_id, department=department,
            action_id=action_id, action_class=action_class, scope=scope, approval_id=approval_id,
            skill=skill, consume_approval=consume_approval, source_project_id=source_project_id,
            payload_sha256=payload_sha256, target_project_id=target_project_id,
            target_department=target_department, target_thread_id=target_thread_id,
            target_thread_title=target_thread_title, target_cwd=target_cwd,
            target_sidebar_section_id=target_sidebar_section_id,
            target_automation_status=target_automation_status,
            retry_blocked_execution_receipt_id=retry_blocked_execution_receipt_id), draft_admission)
    if action_class=='thread_message' or action_class in SPECIALIST_ACTION_CLASSES:
        from department_autonomy import ASSISTANTS,current_mode
        if current_mode(root) and (department in ASSISTANTS or target_department in ASSISTANTS):
            raise WorkflowError('assistant roles are historical-only; no new dispatch, approval or wakeup')
    from department_autonomy import policy as autonomous_policy
    autonomous_requested=dict(task_id=task_id,department=department,action_id=action_id,action_class=action_class,scope=scope,approval_id=approval_id,skill=skill,consume_approval=consume_approval,source_project_id=source_project_id,target_project_id=target_project_id,target_department=target_department,payload_sha256=payload_sha256)
    autonomous_decision=autonomous_policy(root,autonomous_requested)
    if autonomous_decision is not None:return autonomous_decision
    if action_class in EXTERNAL_ACTION_CLASSES:
        from department_rotation import external_write_blocked
        if external_write_blocked(root, department):
            from brand_v4_issuer_executor import TASK as brand_stage_task, preflight as brand_fresh_preflight
            exact_snapshot = read_json(snapshot_path(root,task_id))
            if task_id != brand_stage_task or department != 'designated-development' or action_class != 'site_publish':
                raise WorkflowError('rotated window requires fresh exact production admission; old permits cannot transfer')
            from goal_delivery_runtime import execution_preflight as exact_goal_preflight
            fresh = exact_goal_preflight(root,exact_snapshot,action_id,action_class,scope,department)
            brand_fresh_preflight(root,exact_snapshot,fresh,require_all=True)
    policy = load_policy(root)
    departments = department_registry(root)
    department_item = departments.get(department)
    from brand_v4_issuer_executor import TASK as brand_task, action_context as brand_action_context
    brand_executor = None
    if task_id == brand_task and department == 'designated-development' and action_class == 'site_publish':
        brand_executor = brand_action_context(root, read_json(snapshot_path(root,task_id)), action_id,action_class,scope,department)
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
    if not department_item and not brand_executor and not (task_id == "fc-20261014-builtin-wardrobe-layout-cms-publication-v1"
            and department == "designated-development" and action_class == "site_publish"):
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
                required_receipts.extend(['self_check:current_exact_CMS_candidate' if
                                          cms_goal_context.get('acceptance_model')=='goal_authorized_cms_selfcheck_v1' else
                                          'assistant_acceptance:current_exact_CMS_candidate',
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
                    r"https://company\.example/images/[A-Za-z0-9_./-]+\.webp", url
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
    if health_probe_mode and not exact_health_probe(root, read_json(snapshot_path(root,task_id)),
            sender=department,target=target_department,scope=scope,payload_sha256=payload_sha256):
        allow = False
        reasons.append("exact_authorized_nonbusiness_health_probe_required")
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
    if (action_class=='thread_message' and goal_enabled(root,snapshot) and not prepared_result_notice
            and not health_probe_mode and not scope.startswith('owner_project_handoff:')
            and 'human_authorization:exact_direct_internal_repair' not in required_receipts):
        from goal_delivery_runtime import authorization_precheck
        required_receipts.append('authorization_precheck:consumed_original_goal_source')
        try:
            authority=authorization_precheck(root,task_id,{'task_id':task_id,'sender_department':department,
                'action_class':action_class,'action_id':action_id,'scope':scope,
                'target_department':target_department,'target_project_id':target_project_id,
                'source_project_id':source_project_id,'target_thread_id':target_thread_id,
                'target_thread_title':target_thread_title,'target_cwd':target_cwd,
                'target_sidebar_section_id':target_sidebar_section_id,'payload_sha256':payload_sha256})
            if authority['status']!='within_original_authorization':
                allow=False;reasons.append('original_goal_authority:'+authority['status'])
        except (WorkflowError,ValueError,KeyError,OSError) as error:
            allow=False;reasons.append('original_goal_authority_invalid:'+str(error))
    # Existing exact health probes and the owner-directed single-message route
    # retain their own gates. A prefix does not waive those routing checks.
    if (action_class == "thread_message" and not health_probe_mode
            and not prepared_result_notice
            and not scope.startswith("owner_project_handoff:")
            and not ("human_authorization:exact_direct_internal_repair" in required_receipts and not routing_reasons)
            and not (goal_enabled(root, snapshot) and "goal_delivery:exact_collaboration_binding" in required_receipts and not routing_reasons)
            and not (scope in {"owner_paid_final_qa:example-ads-account:v39", "owner_paid_final_qa:example-ads-account:v40"} and not routing_reasons)):
        required_receipts.append(
            "same_task_technical_responsibility:exact_target_and_unsent_action"
            if action_id == 'assign-same-task-technical-review:fc-20261017-next12-old-house-development-handoff-v1'
            else "dispatch_precheck:planned_fixed_target_and_unsent_action")
        dispatch_reasons = _ordinary_thread_dispatch_precheck(
            root, snapshot=snapshot, task_id=task_id,
            target_department=target_department, target_thread_id=target_thread_id,
            action_id=action_id, scope=scope,
            sender_department=department, payload_sha256=payload_sha256,
            original_message=original_message,
        )
        if dispatch_reasons:
            allow = False
            reasons.extend(dispatch_reasons)
    approval: dict[str, Any] = {}
    standing_authorization: dict[str, Any] = {}
    effective_approval_id = approval_id
    qa_risk_level = ""
    wardrobe_approval_valid = False
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
                from wardrobe_site_publish_runtime import applies as wardrobe_applies, validate_issued as validate_wardrobe_issued
                from paid_three_page_bounded_cms import MODEL as bounded_model, exact_tuple
                bounded = (cms_goal_context is not None
                           and cms_goal_context.get("acceptance_model") == bounded_model
                           and exact_tuple(task_id, action_id, scope, department, action_class)
                           and all(cms_goal_context.get(k) == v for k, v in {
                               "task_id": task_id, "action_id": action_id, "scope": scope,
                               "department": department, "payload_sha256": payload_sha256}.items()))
                condo_candidate = (cms_goal_context is not None
                    and cms_goal_context.get("acceptance_model") == "condo_faq_v7_candidate_scope_only_v1"
                    and task_id == "fc-20261014-condo-faq-v7-cms-publishing-v1"
                    and department == "publishing" and action_class == "cms_write"
                    and cms_goal_context.get("action_id") == action_id
                    and cms_goal_context.get("scope") == scope
                    and cms_goal_context.get("payload_sha256") == payload_sha256
                    and cms_goal_context.get("goal_completion_claimed") is False)
                if wardrobe_applies(task_id, action_class):
                    exact_issued = effective_approvals(root).get(approval_id, {}) if approval_id else {}
                    if (department != "designated-development"
                            or exact_issued.get("status") != "active"):
                        raise WorkflowError("original wardrobe WEB active approval required")
                    goal_preflight = validate_wardrobe_issued(root, snapshot, exact_issued, action_id, scope)
                    wardrobe_approval_valid = True
                else:
                    goal_preflight = (cms_goal_context["preflight"] if bounded or condo_candidate else
                                      execution_preflight(root, snapshot, action_id, action_class, scope, department))
                qa_risk_level = goal_preflight["risk_level"]
                if brand_executor:
                    from brand_v4_issuer_executor import preflight as brand_preflight
                    brand_preflight(root,snapshot,goal_preflight,require_all=True)
                required_receipts += ["self_check:exact_pass", "facts_backup_rollback:exact_pins",
                                      "assistant_acceptance:bounded_candidate_only" if bounded else
                                      "assistant_acceptance:condo_faq_candidate_only" if condo_candidate else
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
            if wardrobe_approval_valid:
                allowed_states.add("dispatched")
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
        if brand_executor and exact_approval_matches:
            from brand_v4_issuer_executor import approval_binding
            exact_approval_matches = approval.get('issuer_executor_binding') == approval_binding(brand_executor)
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
                    department=brand_executor['issuer_department'] if brand_executor else department,
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
                    executor_binding=__import__('brand_v4_issuer_executor').approval_binding(brand_executor) if brand_executor else None,
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
    if allow and consume_approval and approval and brand_executor:
        from brand_v4_issuer_executor import require_complete_permit_set
        require_complete_permit_set(root,snapshot,brand_executor)
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
    if cms_goal_context is not None and cms_goal_context.get("acceptance_model") == "condo_faq_v7_candidate_scope_only_v1":
        result["cms_candidate_acceptance"] = {
            "acceptance_model": cms_goal_context["acceptance_model"],
            "candidate_acceptance_record_id": cms_goal_context["acceptance_receipt_id"],
            "candidate_acceptance_record_hash": cms_goal_context["candidate_acceptance_record_hash"],
            "source_fingerprint": cms_goal_context["source_fingerprint"],
            "bounded_report": cms_goal_context["bounded_report"],
            "producer_outbox": cms_goal_context["producer_outbox"],
            "goal_completion_claimed": False}
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
    from department_autonomy import autonomous_goal,receipt_prerequisite
    if autonomous_goal(snapshot.get('goal_delivery')):
        return receipt_prerequisite(root,snapshot,receipts,receipt_type,department)
    if root is not None:
        from original_task_publisher_handover import legacy_context
        snapshot, receipts = legacy_context(root, snapshot, receipts)
    reviewer = _final_qa_department(root, snapshot, preparation_only=receipt_type in {"dispatch_sent", "dispatch_failed", "chat_ack", "outbox_received"}) if root is not None else "qa"
    latest = _latest_receipts(receipts)
    if receipt_type not in {"dispatch_sent", "dispatch_failed"} and any(
        kind == "dispatch_failed" for kind, _ in latest
    ):
        raise WorkflowError("派工发送失败尚未恢复，不能登记后续成功回执")
    if not _target_dispatch_plan_ready(root, snapshot, department):
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
            from owner_adopted_pilot_consumer import review_context as adopted_pilot_review
            direct_review = adopted_pilot_review(root, snapshot, receipts)
            if direct_review is None:
                direct_review = parent_initial_child_review_context(root, snapshot)
            if direct_review is None:
                direct_review = native_multi_goal_review_context(root, snapshot)
            if direct_review is None:
                direct_review = owner_direct_review_context(root, snapshot)
            if direct_review is None:
                from qa_review_plan import original_condo_faq_child_review_context
                direct_review = original_condo_faq_child_review_context(root, snapshot, receipts)
            if direct_review is None and snapshot.get("task_id") == "fc-20261016-industry-keyword-next-twelve-pages-v1":
                from qa_review_plan import next12_normal_reviewer_source
                direct_review = next12_normal_reviewer_source(root, snapshot, receipts)
    control_producer = False
    if root is not None and department == "operations" and receipt_type == "outbox_received":
        from native_control_result import context
        context(root, snapshot)
        control_producer = True
    recovered_delivery=False
    if root is not None and receipt_type=='outbox_received' and ('chat_ack',department) not in latest:
        from goal_source_recovery import recovered_producer_source
        source=recovered_producer_source(root,snapshot,department)
        recovered_delivery=bool(source and any(r.get('event')=='notification_queued'
            and r.get('sender_department')==department and r.get('actual_native_completion')
            and r.get('visible_reply') and r.get('source_reply_sha256')
            for r in _result_handoff_rows(root,snapshot['task_id'])))
    if receipt_type == "outbox_received" and ("chat_ack", department) not in latest and not inherited and not direct_review and not control_producer and not recovered_delivery:
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
        if root is not None and qa_dispatches:
            from qa_review_plan import _assigned_review_round, load_plan
            review_plan = load_plan(root, snapshot)
            if review_plan is not None:
                assigned_round = _assigned_review_round(root, snapshot, receipts, review_plan)
                initial_history = any(row.get("department") == reviewer
                                      and row.get("receipt_type") in {"dispatch_sent", "dispatch_failed"}
                                      and row.get("action_id") == "assign-goal-review:" + snapshot["task_id"]
                                      for row in receipts)
                if initial_history and assigned_round is None:
                    raise WorkflowError("original single responsibility dispatch/ACK window required")
                if assigned_round is not None:
                    from qa_review_plan import _prepared_original_result_continuation
                    last_dispatch = receipts[qa_dispatches[-1]]
                    if _prepared_original_result_continuation(root, snapshot, receipts, last_dispatch, review_plan) is not None:
                        # A real observation-only input/late ACK does not demand
                        # a new review outbox. The full normal reader above
                        # already authenticated every responsibility window.
                        qa_acks = [assigned_round["ack_index"]]
                    elif not qa_acks:
                        qa_acks = [assigned_round["ack_index"]]
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
    snapshot_before = (file_digest(root, rel_path(root, snapshot_path(root, task_id)))
                       if receipt_type == "health_reconciled" else None)
    department = str(args.department).strip()
    registry = department_registry(root)
    from department_autonomy import autonomous_goal
    from department_autonomy import current_mode,ASSISTANTS
    if current_mode(root) and department in ASSISTANTS:
        raise WorkflowError('retired/standby assistants cannot append new execution or approval receipts')
    if autonomous_goal(snapshot.get('goal_delivery')) and receipt_type=='qa_verdict':
        raise WorkflowError('autonomous departments do not create assistant QA verdicts')
    external_execution = None
    if department not in registry and receipt_type in {'execution_result','postcheck'}:
        from brand_v4_issuer_executor import action_context as brand_action_context
        external_execution = brand_action_context(root,snapshot,str(getattr(args,'action_id','')),
            str(getattr(args,'action_class','')),str(getattr(args,'scope','')),department)
    if department not in registry and not external_execution:
        raise WorkflowError(f"部门未登记：{department}")
    if (receipt_type == "chat_ack" or (receipt_type in {"dispatch_sent", "dispatch_failed"}
            and str(getattr(args, "action_class", "") or "") == "thread_message")):
        from department_rotation import current_dispatch_snapshot
        snapshot = current_dispatch_snapshot(root, snapshot, department, action_id=str(getattr(args, 'action_id', '') or ''))
    planned = {item.get("department"): item for item in snapshot.get("departments", [])}
    if department not in planned and not external_execution:
        raise WorkflowError(f"部门不在该工作流分派计划中：{department}")
    chat_task_id = str(getattr(args, "chat_task_id", "") or "")
    fixed_task_id = str(external_execution['executor_binding']['thread_id'] if external_execution else registry[department].get("chat_binding", {}).get("task_id") or "")
    if external_execution and chat_task_id != fixed_task_id:
        raise WorkflowError('exact real original external execution chat required')
    if receipt_type in {"dispatch_sent", "dispatch_failed", "chat_ack", "qa_verdict", "health_reconciled"}:
        if not chat_task_id or chat_task_id != fixed_task_id or chat_task_id != str(planned[department].get("chat_task_id") or ""):
            raise WorkflowError("回执的 chat_task_id 与注册表固定任务不匹配")
    if receipt_type == "chat_ack" and not bool(getattr(args, "ack_nonempty", False)):
        raise WorkflowError("chat_ack 必须明确记录非空聊天回复")
    verdict = str(getattr(args, "verdict", "") or "").lower()
    if receipt_type == "qa_verdict" and verdict not in {"pass", "blocked"}:
        raise WorkflowError("qa_verdict 必须是 pass 或 blocked")

    evidence_values = [item.strip() for item in str(getattr(args, "evidence", "") or "").split(";") if item.strip()]
    evidence = [file_digest(root, value) for value in evidence_values]
    if receipt_type in {"dispatch_failed", "outbox_received", "qa_verdict", "execution_result", "postcheck", "evidence_replacement", "evidence_archive", "health_reconciled"} and not evidence:
        raise WorkflowError(f"{receipt_type} 必须有可校验的证据文件")
    from department_autonomy import autonomous_goal,validate_native_ack
    if autonomous_goal(snapshot.get('goal_delivery')) and receipt_type=='chat_ack':
        validate_native_ack(root,snapshot,department,evidence)
    if receipt_type == "outbox_received":
        validate_outbox(root, evidence, department, task_id)
        if department == "operations":
            from native_control_result import received_candidate
            received_candidate(root, snapshot, {"producer_department": department, "action_class": "runtime_control",
                                                "scope": snapshot.get("goal_delivery", {}).get("authorized_scope", [""])[0],
                                                "candidate": evidence[0]},
                               [{"receipt_type": "outbox_received", "department": department, "evidence": evidence}])

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
    if any(action.get("parent_initial_dispatch") or action.get("goal_responsibility_dispatch") for action in snapshot.get("goal_delivery", {}).get("approved_actions", [])):
        receipt["created_at"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="microseconds")
    from native_control_result import matches as native_control_task
    if (native_control_task(snapshot)
            or isinstance(snapshot.get("goal_delivery", {}).get("qualified_assistant_selection"), dict)):
        receipt["created_at"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="microseconds")
    path = receipts_path(root, task_id)
    with workflow_lock(root):
        if snapshot_before is not None and file_digest(
                root, rel_path(root, snapshot_path(root, task_id))) != snapshot_before:
            raise WorkflowError("original health child snapshot changed before receipt commit")
        receipts = read_jsonl(path)
        candidates = [row for row in receipts if row.get("idempotency_key") == idempotency_key]
        if receipt_type == "health_reconciled":
            receipt["historical_health"] = _original_a1_health_history(
                root, snapshot, receipt, new=not candidates,
            )
        if candidates:
            existing = candidates[-1]
            comparable_keys = {
                "task_id", "receipt_type", "department", "chat_task_id", "ack_nonempty",
                "verdict", "evidence", "idempotency_key", "action_id", "action_class",
                "scope", "approval_id", "policy_decision_id", "supersedes_receipt_id",
                "replacement_reason", "chat_body_stored", "historical_health",
            }
            if any(existing.get(key) != receipt.get(key) for key in comparable_keys):
                raise WorkflowError("幂等键已绑定不同回执内容")
            return {**existing, "result": "duplicate_ignored"}, [path, snapshot_path(root, task_id)]

        from original_task_publisher_handover import validate_new_receipt
        handover_receipt = None if receipt_type == "health_reconciled" else validate_new_receipt(root, snapshot, receipts, receipt)
        if receipt_type == "health_reconciled":
            # This is evidence reconciliation, not a new dispatch, ACK, QA, or
            # permission to reuse the old observed live state.
            pass
        elif handover_receipt:
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
        if (receipt_type == "outbox_received"
                and task_id == "fc-20261014-condo-faq-v7-cms-publishing-v1"
                and department == "operations-assistant"):
            from qa_review_plan import load_plan
            if read_json(snapshot_path(root, task_id)) != snapshot:
                raise WorkflowError("bounded A1 receipt goal changed before append")
            plan = load_plan(root, snapshot)
            box = read_json(safe_path(root, evidence[0]["path"])) if evidence else {}
            report_pin = box.get("bounded_candidate_acceptance")
            if not isinstance(plan, dict) or not isinstance(report_pin, dict):
                raise WorkflowError("bounded A1 receipt needs its original plan and report")
            _condo_faq_bounded_ready_stage(root, snapshot, receipt, evidence[0],
                                           box, report_pin, plan)
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
    assignment_status = None
    if receipt_type == 'dispatch_sent':
        from goal_continuity import ASSIGNMENT_SCHEMA, record_assignment
        for source in evidence:
            if not source['path'].endswith('.json'):continue
            item=read_json(safe_path(root,source['path']))
            if item.get('schema') == ASSIGNMENT_SCHEMA:
                # The actual dispatch is already appended. Failed registration
                # is a recoverable missing projection, never a reason to resend.
                try:assignment_status=record_assignment(root,item,source)
                except (WorkflowError,ValueError,OSError,KeyError) as error:
                    assignment_status={'result':'assignment_readback_required','next_action':'recover_existing_actual_dispatch_without_resend','reason':str(error)}
    return {**receipt, "result": "recorded", "workflow_state": reconcile.get("current_state"),
            **({'current_assignment':assignment_status} if assignment_status else {})}, [path, *artifacts]


def _validate_receipt_chain(root: Path, task_id: str, *, through_receipt_id: str | None = None):
    context = _VALIDATION_CONTEXT.get()
    if context is None:
        return _validate_receipt_chain_uncached(root, task_id, through_receipt_id=through_receipt_id)
    # Include the exact receipt bytes and prefix in the request key.
    if not receipts_path(root, task_id).is_file():
        return _validate_receipt_chain_uncached(root, task_id, through_receipt_id=through_receipt_id)
    receipt_pin = file_digest(root, rel_path(root, receipts_path(root, task_id)))
    key = ("receipt_chain", str(Path(root).resolve()), task_id, through_receipt_id, receipt_pin["sha256"])
    if key not in context.proofs:
        value = _validate_receipt_chain_uncached(root, task_id, through_receipt_id=through_receipt_id)
        context.proofs[key] = deepcopy(value)
    return deepcopy(context.proofs[key])


def _validate_receipt_chain_uncached(root: Path, task_id: str, *, through_receipt_id: str | None = None) -> tuple[list[dict[str, Any]], list[str]]:
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
                from department_rotation import historical_receipt_validation
                with historical_receipt_validation(root, receipt):
                    validate_verdict(root, review_snapshot, receipts[:index - 1], receipt)
            except (WorkflowError, ValueError, KeyError, OSError) as exc:
                invalid.append(f"receipt_{index}:exact_review_invalid:{exc}")
        if receipt.get("receipt_type") == "health_reconciled":
            if any(row.get("receipt_type") == "health_reconciled" for row in receipts[:index - 1]):
                invalid.append(f"receipt_{index}:duplicate_historical_health")
            else:
                try:
                    provenance = _original_a1_health_history(
                        root, review_snapshot, receipt, new=False,
                    )
                    if receipt.get("historical_health") != provenance:
                        raise WorkflowError("historical health provenance differs")
                except (WorkflowError, ValueError, KeyError, TypeError, OSError) as error:
                    invalid.append(f"receipt_{index}:historical_health_invalid:{error}")
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
    if not scope.startswith("company.example:"):
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



def _completion_execution_output(executed):
    """Read only the original complete native UTF-8 command output."""
    from qa_review_plan import _review_native_containers
    try:
        _review_native_containers(executed)
    except ValueError as error:
        raise WorkflowError("successful complete native execution container required") from error
    output = executed.get("output")
    if isinstance(output, str):
        return output.encode("utf-8")
    if (isinstance(output, dict) and set(output) == {"text", "truncated"}
            and isinstance(output.get("text"), str) and output.get("truncated") is False):
        return output["text"].encode("utf-8")
    raise WorkflowError("complete native command output string or untruncated text object required")


def _completion_pin(root, pin):
    if not isinstance(pin, dict) or file_digest(root, str(pin.get("path") or "")) != pin:
        raise WorkflowError("exact completion evidence full pin required")
    return read_json(safe_path(root, pin["path"]))


def goal_legacy_scope_completion(root, snapshot, receipts):
    task = snapshot["task_id"]
    if validate_workflow_events(root, task):
        return {"state": "BLOCKED", "reason": "legacy workflow event chain invalid"}
    qa = [row for row in receipts if row.get("receipt_type") == "qa_verdict"]
    events = [row for row in read_jsonl(root / WORKFLOW_EVENTS) if row.get("task_id") == task]
    closed = [row for row in events if row.get("state") == "closed"]
    if not qa or qa[-1].get("verdict") != "pass" or not closed:
        return {"state": "MISSING", "reason": "no actual legacy exact close"}
    close_at = _parse_observed_at(closed[-1].get("created_at"))
    qa_at = _parse_observed_at(qa[-1].get("created_at"))
    if close_at is None or qa_at is None or close_at < qa_at:
        return {"state": "BLOCKED", "reason": "legacy close predates current acceptance"}
    return {"state": "PROVEN", "closed_scope_only": True, "business_goal_closed": False,
            "scope": qa[-1].get("scope"), "acceptance_receipt": qa[-1],
            "closed_event_id": closed[-1].get("event_id"), "evidence": qa[-1].get("evidence", [])}



def _bounded_acceptance_source_fact(root, snapshot, receipts, plan, producer, row):
    """Authenticate an adopted-source fact without replacing candidate acceptance."""
    try:
        role = snapshot['goal_delivery']['responsible_assistant']
        evidence = row.get('evidence', [])
        if (row.get('task_id') != snapshot['task_id'] or row.get('department') != role
                or row.get('receipt_type') != 'outbox_received' or len(evidence) != 1
                or not str(evidence[0].get('path', '')).endswith('.json')
                or len([r for r in receipts if evidence[0] in r.get('evidence', [])]) != 1):
            return False
        pin = evidence[0]
        report = _completion_pin(root, pin)
        if (report.get('schema') != 'independently-adopted-internal-source-continuation/v1'
                or any(key in report for key in ('bounded_candidate_acceptance', 'qa_verdict', 'goal_acceptance'))):
            return False
        effect = report['actual_source_continuation']
        required = [pin, effect['candidate_manifest'], effect['journal'], effect['independent_review_report']]
        manifest = _completion_pin(root, effect['candidate_manifest'])
        if (manifest.get('task_id') != snapshot['task_id'] or manifest.get('scope') != plan['scope']
                or manifest.get('primary_owner') != producer or manifest.get('responsible_assistant') != role
                or manifest.get('normal_plan') != snapshot['qa_review_plan']['pin']
                or manifest.get('goal_contract') != snapshot.get('goal_contract')
                or manifest.get('human_authorization') != snapshot['goal_delivery']['authorization_pin']):
            return False
        sources = [r for r in receipts if r.get('receipt_type') == 'outbox_received'
                   and r.get('department') == producer]
        if not sources or manifest.get('primary_producer_outbox') not in sources[-1].get('evidence', []):
            return False
        # This existing reader validates the whole actual independent CAS/native
        # source report, committed packet, chronology, modes and backup chain.
        # A path is usable only if its current unique edge contains this exact
        # report/manifest/journal/review, never merely a caller source-only label.
        for change in manifest.get('changes', []):
            expected = change.get('expected_source', {})
            if type(expected.get('mode')) is not int:
                return False
            actual = _internal_source_continuation_readback(
                root, change['path'], expected['sha256'], expected['mode'])
            if actual and all(p in actual['evidence'] for p in required):
                return True
        return False
    except (WorkflowError, OSError, ValueError, TypeError, KeyError, AttributeError):
        return False


def _goal_bounded_candidate_subject(root, snapshot, receipts, plan, producer):
    """Candidate-only independent acceptance precedes adoption, without full-goal PASS."""
    goal = snapshot["goal_delivery"]; role = goal["responsible_assistant"]
    selected = [row for row in receipts if row.get("receipt_type") == "outbox_received" and row.get("department")==role]
    if not selected:
        return {"state":"MISSING","reason":"bounded independent candidate acceptance missing"}
    for row in reversed(selected):
        if not _bounded_acceptance_source_fact(root, snapshot, receipts, plan, producer, row):
            break
    else:
        return {"state":"MISSING","reason":"bounded independent candidate acceptance missing"}
    boxes=[]
    for pin in row.get("evidence",[]):
        if str(pin.get("path","")).endswith(".json"):
            box=_completion_pin(root,pin)
            if box.get("department")==role and box.get("candidate_version")==plan["candidate_version"]:
                boxes.append((pin,box))
    if len(boxes)!=1:
        return {"state":"MISSING","reason":"current bounded candidate conclusion missing"}
    pin,box=boxes[0]; report_pin=box.get("bounded_candidate_acceptance")
    if not isinstance(report_pin,dict):
        return {"state":"MISSING","reason":"explicit independent candidate-only declaration missing"}
    report=_completion_pin(root,report_pin)
    expected={"schema_version":"goal-candidate-scope-acceptance-v1","task_id":snapshot["task_id"],
              "reviewer":role,"producer_department":producer,"scope":plan["scope"],
              "candidate_version":plan["candidate_version"],"candidate":plan["candidate"],
              "review_plan":snapshot["qa_review_plan"]["pin"],"verdict":"PASS_CANDIDATE_SCOPE_ONLY",
              "goal_completion_claimed":False,"external_permission_issued":False}
    if any(report.get(k)!=v for k,v in expected.items()):
        raise WorkflowError("bounded acceptance must retain exact current candidate/independent plan without full-goal claim")
    if report_pin not in box.get("evidence",[]) or plan["candidate"] not in box.get("evidence",[]):
        raise WorkflowError("bounded independent outbox must pin reviewed report and candidate")
    qa=[item for item in receipts if item.get("receipt_type")=="qa_verdict" and item.get("department")==role]
    if qa and receipts.index(qa[-1])>=receipts.index(row) and qa[-1].get("verdict")!="pass":
        raise WorkflowError("latest formal blocked acceptance supersedes bounded conclusion")
    producer_pin=report.get("producer_outbox");source=_completion_pin(root,producer_pin)
    source_rows=[item for item in receipts if item.get("receipt_type")=="outbox_received" and item.get("department")==producer]
    if (not source_rows or producer_pin not in source_rows[-1].get("evidence",[])
            or source.get("candidate_version")!=plan["candidate_version"]):
        raise WorkflowError("bounded acceptance must refer to latest producer bytes")
    candidate=_completion_pin(root,plan["candidate"])
    fingerprint=candidate.get("candidate_fingerprint",candidate.get("source_fingerprint",plan["candidate_sha256"]))
    if report.get("source_fingerprint")!=fingerprint:
        raise WorkflowError("bounded reviewed source fingerprint differs")
    bounded_ready = None
    if (snapshot["task_id"]=="fc-20261014-condo-faq-v7-cms-publishing-v1"
            and role=="operations-assistant" and producer=="publishing"):
        bounded_ready = _condo_faq_bounded_ready_stage(root,snapshot,row,pin,box,report_pin,plan)
    else:
        _completion_native_stage(root,box,report_pin,role)
    queued=[item for item in _result_handoff_rows(root,snapshot["task_id"])
            if item.get("event")=="notification_queued" and item.get("outbox")==producer_pin]
    if len(queued)!=1 or not queued[0].get("source_turn_id"):
        raise WorkflowError("actual latest producer final source required")
    return {"state":"PROVEN","identity":{"task_id":snapshot["task_id"],"sender_department":producer,
            "candidate_version":plan["candidate_version"],"result_sha256":producer_pin["sha256"]},
            "source_fingerprint":fingerprint,"source_turn_id":queued[0]["source_turn_id"],
            "scope":plan["scope"],"acceptance_receipt":row,"acceptance_outbox":pin,
            "producer_outbox":producer_pin,"candidate":plan["candidate"],"review_plan":snapshot["qa_review_plan"]["pin"],
            "evidence":[*row.get("evidence",[]),report_pin,producer_pin,plan["candidate"]],
            "bounded_ready_source": bounded_ready,
            "acceptance_scope":"candidate_source_only","business_goal_closed":False}


def _condo_faq_bounded_ready_stage(root,snapshot,receipt,outbox_pin,box,report_pin,plan):
    """Consume an actual A1 READY sidecar attached to its genuine outbox receipt."""
    from goal_continuity import ready_source, native
    task="fc-20261014-condo-faq-v7-cms-publishing-v1"
    role="operations-assistant"
    fixed=department_registry(root)[role]["chat_binding"]["task_id"]
    evidence=receipt.get("evidence",[])
    if (receipt.get("department")!=role or len(evidence)!=2
            or evidence[0]!=outbox_pin
            or box.get("task_id")!=task or box.get("department")!=role
            or box.get("candidate_version")!=plan["candidate_version"]):
        raise WorkflowError("one real A1 candidate outbox and one READY source sidecar required")
    sidecar_pin=evidence[1]
    sidecar=_completion_pin(root,sidecar_pin)
    expected={"schema":"condo-faq-v7-bounded-ready-source/v1","task_id":task,
              "sender_department":role,"candidate_version":plan["candidate_version"],
              "outbox":outbox_pin,"bounded_report":report_pin,
              "candidate":plan["candidate"],"review_plan":snapshot["qa_review_plan"]["pin"]}
    if (set(sidecar)!=set(expected)|{"source_request"}
            or any(sidecar.get(key)!=value for key,value in expected.items())
            or not isinstance(sidecar.get("source_request"),dict)):
        raise WorkflowError("exact typed A1 READY sidecar and original review identity required")
    request=sidecar["source_request"]
    required={"task_id","sender_department","candidate_version","result_sha256",
              "outbox_path","source_mode","result_source_phase","source_thread_id",
              "source_turn_id","source_message_id","source_reply_sha256",
              "reply_observed_at","actual_native_completion","visible_reply"}
    if (set(request)!=required or any(request.get(key)!=value for key,value in
            {"task_id":task,"sender_department":role,
             "candidate_version":plan["candidate_version"],"result_sha256":outbox_pin["sha256"],
             "outbox_path":outbox_pin["path"],"source_mode":"approved_dispatch",
             "result_source_phase":"delivery_ready","source_thread_id":fixed}.items())):
        raise WorkflowError("A1 READY sidecar does not bind the frozen bounded candidate")
    proof=ready_source(root,request,fixed)
    if proof.get("result_source_phase")!="delivery_ready" or proof.get("batch_delivery_frozen") is not True:
        raise WorkflowError("A1 candidate READY declaration failed exact native verification")
    page=native(root,request["actual_native_completion"])
    messages=[item for turn in page.get("turns",[]) if turn.get("id")==request.get("source_turn_id")
              for item in turn.get("items",[]) if item.get("type")=="agentMessage"
              and item.get("id")==request.get("source_message_id")]
    if (len(messages)!=1 or messages[0].get("phase") not in {"commentary","final_answer"}
            or report_pin["path"] not in messages[0].get("text","")
            or report_pin["sha256"] not in messages[0].get("text","")
            or request.get("source_reply_sha256")!=request.get("visible_reply",{}).get("sha256")):
        raise WorkflowError("actual A1 READY message must pin the exact bounded report")
    return {"sidecar":sidecar_pin,"source_turn_id":request["source_turn_id"],
            "source_message_id":request["source_message_id"],
            "actual_native_completion":request["actual_native_completion"],
            "visible_reply":request["visible_reply"]}


def goal_completion_subject(root, snapshot, receipts, subject):
    """Resolve a frozen selector to the actual latest independently accepted bytes."""
    import qa_review_plan as q
    goal = snapshot["goal_delivery"]
    try:
        if (not isinstance(subject, dict) or subject.get("mode") != "latest_exact_accepted_result"
                or subject.get("producer_department") not in goal["producer_departments"]):
            raise WorkflowError("exact registered producer selector required")
        plan = q.load_plan(root, snapshot)
        if not plan or plan.get("producer_department") != subject["producer_department"]:
            return {"state": "MISSING", "reason": "current exact independent plan missing"}
        role = goal["responsible_assistant"]
        if plan.get("reviewer_department") != role or role in goal["producer_departments"]:
            raise WorkflowError("current independent assistant required")
        qa = [row for row in receipts if row.get("receipt_type") == "qa_verdict"
              and row.get("department") == role]
        bounded = _goal_bounded_candidate_subject(root,snapshot,receipts,plan,subject["producer_department"])
        if bounded.get("state")=="PROVEN":
            return bounded
        if not qa:
            return {"state": "MISSING", "reason": "current independently accepted result missing"}
        current = qa[-1]
        if (current.get("verdict") != "pass" or any(current.get(k) != plan.get(k)
                for k in ("action_id", "action_class", "scope"))):
            raise WorkflowError("latest exact QA is blocked or differs from bound plan")
        boxes = [(pin, _completion_pin(root, pin)) for pin in current.get("evidence", [])
                 if str(pin.get("path", "")).endswith(".json")]
        matched = [(pin, box) for pin, box in boxes if box.get("department") == role
                   and box.get("candidate_version") == plan["candidate_version"]
                   and box.get("qa_verdict") == "pass"]
        if len(matched) != 1:
            raise WorkflowError("one current formal independent outbox required")
        qa_pin, box = matched[0]
        producer_pin = box.get("goal_acceptance", {}).get("producer_results", {}).get(subject["producer_department"])
        producer = _completion_pin(root, producer_pin)
        source_rows = [row for row in receipts if row.get("receipt_type") == "outbox_received"
                       and row.get("department") == subject["producer_department"]]
        if (not source_rows or producer_pin not in source_rows[-1].get("evidence", [])
                or producer.get("candidate_version") != plan["candidate_version"]):
            raise WorkflowError("current acceptance cannot reuse an earlier producer result")
        candidate = _completion_pin(root, plan["candidate"])
        fingerprint = candidate.get("candidate_fingerprint", candidate.get("source_fingerprint", plan["candidate_sha256"]))
        if not SHA256_PATTERN.fullmatch(str(fingerprint or "")):
            raise WorkflowError("current accepted source/content fingerprint required")
        queued = [row for row in _result_handoff_rows(root, snapshot["task_id"])
                  if row.get("event") == "notification_queued" and row.get("outbox") == producer_pin]
        if len(queued) != 1 or not queued[0].get("source_turn_id"):
            raise WorkflowError("actual exact current producer completed source required")
        return {"state": "PROVEN", "identity": {"task_id": snapshot["task_id"],
                "sender_department": subject["producer_department"], "candidate_version": plan["candidate_version"],
                "result_sha256": producer_pin["sha256"]}, "source_fingerprint": fingerprint,
                "source_turn_id": queued[0]["source_turn_id"], "scope": plan["scope"],
                "acceptance_receipt": current, "acceptance_outbox": qa_pin, "producer_outbox": producer_pin,
                "candidate": plan["candidate"], "review_plan": snapshot["qa_review_plan"]["pin"],
                "evidence": current.get("evidence", []) + [producer_pin, plan["candidate"]]}
    except (WorkflowError, ValueError, KeyError, TypeError, OSError) as error:
        return {"state": "BLOCKED", "reason": str(error)}


def goal_execution_completion(root, snapshot, receipts, action, accepted=None):
    """The latest action outcome and latest following verification are decisive."""
    try:
        from brand_v4_issuer_executor import conditional_completion
        conditional = conditional_completion(root,snapshot,action,accepted)
        if conditional is not None:return conditional
        keys = ("department", "action_id", "action_class", "scope")
        matching = [row for row in receipts if row.get("receipt_type") in {"execution_result", "postcheck"}
                    and all(row.get(k) == action.get(k) for k in keys)]
        executions = [row for row in matching if row.get("receipt_type") == "execution_result"]
        if not executions:
            return {"state": "MISSING", "reason": "actual execution missing", "evidence": []}
        execution = executions[-1]
        if execution.get("verdict") != "pass":
            raise WorkflowError("latest execution failed, blocked or effect unknown")
        checks = [row for row in matching if row.get("receipt_type") == "postcheck"]
        if not checks:
            return {"state": "MISSING", "reason": "current postcheck missing", "evidence": []}
        check = checks[-1]
        ex_at, ck_at = [_parse_observed_at(row.get("created_at")) for row in (execution, check)]
        if (check.get("verdict") != "pass" or ex_at is None or ck_at is None or ck_at < ex_at
                or receipts.index(check) <= receipts.index(execution)):
            raise WorkflowError("latest postcheck is not PASS after the latest execution")
        proof_pairs = []
        for row, kind in ((execution, "execution"), (check, "postcheck")):
            proofs = [_completion_pin(root, pin) for pin in row.get("evidence", [])
                      if str(pin.get("path", "")).endswith(".json")]
            proofs = [doc for doc in proofs if doc.get("schema_version") == "goal-execution-completion-proof-v1"
                      and doc.get("proof_type") == kind]
            if len(proofs) != 1:
                raise WorkflowError("latest effect requires explicit exact version/fingerprint/native evidence")
            proof = proofs[0]
            if (any(proof.get(k) != row.get(k) for k in ("task_id", *keys))
                    or not proof.get("production_version")
                    or not SHA256_PATTERN.fullmatch(str(proof.get("source_fingerprint") or ""))
                    or not isinstance(proof.get("identity"), dict)):
                raise WorkflowError("action/executor/scope/content/production identity differs")
            effect = _completion_pin(root, proof.get("actual_native_effect"))
            if (effect.get("isError") is True or effect.get("failed") is True
                    or effect.get("truncated") is True or not effect.get("actual_tool_result")):
                raise WorkflowError("intact actual native execution/readback evidence required")
            import qa_review_plan as q
            q._review_native_containers(effect)
            native_effect=q._review_raw_native_result(effect["actual_tool_result"])
            expected_effect={"task_id":snapshot["task_id"],**{k:action[k] for k in keys},
                             "identity":proof["identity"],"source_fingerprint":proof["source_fingerprint"],
                             "production_version":proof["production_version"],"proof_type":kind,"verdict":"pass"}
            if any(native_effect.get(k)!=v for k,v in expected_effect.items()):
                raise WorkflowError("raw actual effect/readback must prove the exact action/version/content outcome")
            if kind == "postcheck" and proof.get("execution_receipt_id") != execution["receipt_id"]:
                raise WorkflowError("verification must identify this exact latest execution")
            proof_pairs.append(proof)
        left, right = proof_pairs
        if any(left.get(k) != right.get(k) for k in ("identity", "source_fingerprint", "production_version")):
            raise WorkflowError("verification candidate/content/production version differs from execution")
        if accepted is not None and (accepted.get("state") != "PROVEN"
                or left["identity"] != accepted.get("identity")
                or left["source_fingerprint"] != accepted.get("source_fingerprint")):
            raise WorkflowError("latest execution does not publish the exact current accepted candidate")
        return {"state": "PROVEN", "identity": left["identity"], "source_fingerprint": left["source_fingerprint"],
                "source_turn_id": accepted.get("source_turn_id") if accepted else left.get("source_turn_id"),
                "scope": action["scope"], "production_version": left["production_version"], "execution_receipt": execution,
                "postcheck_receipt": check, "evidence": execution["evidence"] + check["evidence"]}
    except (WorkflowError, ValueError, KeyError, TypeError, OSError) as error:
        return {"state": "BLOCKED", "reason": str(error), "evidence": []}


def _completion_native_stage(root, proof, stage_pin, role):
    """An actual fixed assistant reply pins an effect; a boolean is insufficient."""
    import goal_delivery_runtime as g
    native = g._native_document(root, proof.get("actual_native_completion"))
    fixed = department_registry(root)[role]["chat_binding"]["task_id"]
    _,message = _completion_actual_final(root,native,role,turn_id=proof.get("source_turn_id"),message_id=proof.get("source_message_id"))
    reply = proof.get("visible_reply")
    _completion_pin(root, stage_pin)
    if not isinstance(reply, dict) or file_digest(root, reply.get("path", "")) != reply:
        raise WorkflowError("exact native completion UTF-8 pin required")
    if (validation_bytes(safe_path(root, reply["path"])) != message.get("text", "").encode("utf-8")
            or stage_pin["path"] not in message["text"] or stage_pin["sha256"] not in message["text"]):
        raise WorkflowError("actual completion must pin the exact stage bytes")


def _tnew_accepted_source_manifest(root, snapshot, accepted):
    """Keep the accepted producer outbox identity; select its one exact source MP."""
    import qa_review_plan as q
    task = "fc-20261011-goal-publication-notice-followthrough-repair-v1"
    scope = "project:flashcast:goal-publication-notice-followthrough-repair:v1"
    goal = snapshot.get("goal_delivery", {})
    pp = accepted.get("producer_outbox")
    if (snapshot.get("task_id") != task or accepted.get("state") != "PROVEN"
            or accepted.get("candidate") != pp or accepted.get("scope") != scope
            or accepted.get("identity", {}).get("task_id") != task
            or accepted.get("identity", {}).get("sender_department") != "system-development"
            or accepted.get("acceptance_scope") != "candidate_source_only"
            or accepted.get("business_goal_closed") is not False
            or goal.get("responsible_assistant") != "operations-assistant-2"
            or goal.get("acceptance_capability") != "development"):
        raise WorkflowError("only the original independently accepted TNEW producer identity may select a source manifest")
    box = _completion_pin(root, pp)
    q._review_native_containers(box)
    validate_outbox(root, [pp], "system-development", task)
    if (box.get("department") != "system-development" or box.get("task_id") != task
            or box.get("candidate_version") != accepted["identity"].get("candidate_version")
            or pp.get("sha256") != accepted["identity"].get("result_sha256")
            or box.get("candidate_fingerprint") != accepted.get("source_fingerprint")
            or box.get("prepared_only") is not False
            or any(box.get(key) is not False for key in ("production_write_allowed", "production_release_eligible",
                "external_permission_issued", "goal_completion_claimed", "final_goal_verdict", "pilot_complete"))):
        raise WorkflowError("accepted producer outbox identity cannot be replaced by a manifest")
    evidence = box.get("evidence")
    if isinstance(evidence, dict):
        values = list(evidence.values())
    elif isinstance(evidence, list):
        values = evidence
    else:
        raise WorkflowError("exact producer evidence dictionary or list required")
    if not values or any(not isinstance(value, dict) or set(value) != {"path", "sha256", "size"}
                         or type(value.get("size")) is not int for value in values):
        raise WorkflowError("complete direct producer evidence pins required")
    if len({value["path"] for value in values}) != len(values):
        raise WorkflowError("ambiguous producer evidence paths refused")
    manifests = []
    for value in values:
        if file_digest(root, value["path"]) != value:
            raise WorkflowError("accepted producer evidence changed")
        if value["path"].endswith(".json"):
            document = q._review_source_document(root, value)
            if document.get("schema") == "flashcast-exact-source-candidate/v1":
                manifests.append((value, document))
    if len(manifests) != 1:
        raise WorkflowError("one unique independently accepted source manifest required")
    mp, manifest = manifests[0]
    if (isinstance(evidence, dict) and evidence.get("candidate_manifest") != mp
            or manifest.get("task_id") != task or manifest.get("scope") != scope
            or manifest.get("candidate_version") != box["candidate_version"]
            or manifest.get("candidate_fingerprint") != accepted["source_fingerprint"]
            or manifest.get("goal_contract") != snapshot.get("goal_contract")
            or manifest.get("human_authorization") != goal.get("authorization_pin")):
        raise WorkflowError("source manifest must retain exact PP version, fingerprint, goal and human authority")
    plan = q.load_plan(root, snapshot)
    if (not plan or plan.get("candidate") != pp
            or plan.get("candidate_version") != box["candidate_version"]
            or accepted.get("review_plan") != snapshot.get("qa_review_plan", {}).get("pin")):
        raise WorkflowError("actual accepted source plan must preserve the producer outbox")
    q._review_manifest_source_pins(root, snapshot, plan, mp,
        candidate_version=box["candidate_version"], fingerprint=accepted["source_fingerprint"])
    return mp, manifest


def _tnew_actual_source_adoption(root, snapshot, accepted, proof, journal_pin, journal):
    """Read actual certain journals through the authenticated permanent source chain."""
    import paid_three_page_bounded_cms as b
    mp, manifest = _tnew_accepted_source_manifest(root, snapshot, accepted)
    successors = proof.get("actual_source_successors")
    if not isinstance(successors, list) or not successors:
        raise WorkflowError("actual permanent source successors required")
    first = _completion_pin(root, successors[0])
    authenticated = b.authenticated_source_successions(root, successors,
        predecessor_sources=first.get("predecessor_sources"),
        original_history_pin=first.get("original_history_continuation"))
    layers = authenticated.get("layers", [])
    if (not layers or layers[-1].get("manifest_pin") != mp
            or layers[-1].get("journal_pin") != journal_pin
            or journal.get("candidate_manifest") != mp
            or journal.get("task_id") != snapshot["task_id"]
            or journal.get("candidate_version") != accepted["identity"]["candidate_version"]
            or journal.get("candidate_fingerprint") != accepted["source_fingerprint"]
            or journal.get("actor") != snapshot["goal_delivery"]["responsible_assistant"]
            or journal.get("authorized_source") != snapshot["goal_delivery"]["authorization_pin"]
            or journal.get("status") != "complete" or journal.get("direction") != "forward"
            or journal.get("source_effect_state") != "ALL_REVIEWED_AFTER_VERIFIED"
            or type(journal.get("external_writes")) is not int or journal["external_writes"] != 0
            or journal.get("permissions_issued") is not False or journal.get("effect_uncertain") is not False):
        raise WorkflowError("typed source proof must bind the latest actual permanent journal and exact accepted MP")
    continuation = _completion_pin(root, successors[-1])
    if continuation.get("producer_outbox") != accepted["producer_outbox"]:
        raise WorkflowError("actual permanent source successor must retain accepted PP identity")
    changes = manifest.get("files")
    operations = journal.get("source_operations")
    if (not isinstance(changes, list) or not changes or not isinstance(operations, list)
            or [row.get("path") for row in changes] != [row.get("path") for row in operations]):
        raise WorkflowError("exact source operations must match the independently accepted manifest")
    endpoints = {row["path"]: row for row in authenticated["endpoint"]}
    for change, operation in zip(changes, operations):
        target = file_digest(root, change["path"])
        before, after = change.get("before"), change.get("after")
        backup = operation.get("backup")
        mode = change.get("after_mode")
        if (type(mode) is not int or mode != change.get("before_mode")
                or target != {"path": change["path"], **after} or endpoints.get(change["path"]) != target
                or operation.get("before") != before or operation.get("after_expected") != after
                or operation.get("after_actual") != after or operation.get("verified_after") is not True
                or operation.get("before_mode") != mode
                or safe_path(root, change["path"]).stat().st_mode & 0o777 != mode
                or file_digest(root, backup.get("path", "")) != backup
                or {key: backup[key] for key in ("sha256", "size")} != before
                or safe_path(root, backup["path"]).stat().st_mode & 0o777 != mode):
            raise WorkflowError("actual source effects require exact before/after bytes, recoverable backup and retained modes")
    migrations = manifest.get("field_changes")
    field_journals = journal.get("field_adoptions", [])
    if (not isinstance(migrations, list) or not isinstance(field_journals, list)
            or field_journals != continuation.get("field_adoptions")
            or len(migrations) != len(field_journals)):
        raise WorkflowError("every accepted field operation must be an actual authenticated field journal")
    from goal_delivery_runtime import _native_document
    native = _native_document(root, proof.get("actual_native_execution"))
    role = snapshot["goal_delivery"]["responsible_assistant"]
    if native.get("thread", {}).get("id") != department_registry(root)[role]["chat_binding"]["task_id"]:
        raise WorkflowError("actual CAS execution must originate from the assigned assistant")
    items = [item for turn in native.get("turns", []) for item in turn.get("items", [])
             if item.get("type") == "commandExecution" and item.get("id") == proof.get("native_execution_id")]
    output = proof.get("execution_output")
    if len(items) != 1 or not isinstance(output, dict) or file_digest(root, output.get("path", "")) != output:
        raise WorkflowError("one actual native CAS execution and exact output required")
    executed = items[0]
    raw = validation_bytes(safe_path(root, output["path"]))
    if (executed.get("status") != "completed" or executed.get("exitCode") != 0
            or executed.get("cwd") != str(Path(root).resolve())
            or not proof.get("execution_command") or executed.get("command") != proof["execution_command"]
            or _completion_execution_output(executed) != raw
            or any(value.encode("utf-8") not in raw for value in (journal_pin["path"], journal_pin["sha256"], mp["sha256"]))):
        raise WorkflowError("actual successful source execution output must pin its journal and separate reviewed MP")
    return {"candidate_manifest": mp, "permanent_source_successors": successors}


def tnew_adopted_completion_context(root, parent, adoption):
    """Authorize only this original criterion-12 child from real criterion-11 evidence."""
    import goal_delivery_runtime as g
    task = "fc-20261011-goal-publication-notice-followthrough-repair-v1"
    scope = "project:flashcast:goal-publication-notice-followthrough-repair:v1"
    fields = {"mode", "producer_outbox", "typed_source_adoption", "actual_source_successors"}
    if (parent.get("task_id") != task or not isinstance(adoption, dict) or set(adoption) != fields
            or adoption.get("mode") != "tnew_source_only_adopted"):
        raise WorkflowError("only exact original TNEW source-only adopted child provenance is allowed")
    requirements = g.tnew_internal_pilot_requirements(root, parent)
    source = requirements["source_adoption"]
    receipts, invalid = _validate_receipt_chain(root, task)
    if invalid or validate_workflow_events(root, task):
        raise WorkflowError("intact original parent receipt and workflow chains required")
    accepted = goal_completion_subject(root, parent, receipts, {**source["subject"], "scope": scope})
    if (accepted.get("state") != "PROVEN" or accepted.get("acceptance_scope") != "candidate_source_only"
            or accepted.get("business_goal_closed") is not False
            or accepted.get("producer_outbox") != adoption["producer_outbox"]):
        raise WorkflowError("real current independent source-only parent acceptance required")
    proof = _completion_pin(root, adoption["typed_source_adoption"])
    if proof.get("actual_source_successors") != adoption["actual_source_successors"]:
        raise WorkflowError("child adoption must retain the same actual permanent successors as proof11")
    proven = goal_typed_completion_proof(root, parent, receipts, source, accepted,
        proof_pin=adoption["typed_source_adoption"])
    if proven.get("state") != "PROVEN":
        raise WorkflowError("actual original proof11 is not proven: " + str(proven.get("reason")))
    mp, _ = _tnew_accepted_source_manifest(root, parent, accepted)
    evidence = list({pin["path"]: pin for pin in [*accepted["evidence"], *proven["evidence"],
        mp, *adoption["actual_source_successors"]]}.values())
    return {"control_qa": accepted["acceptance_outbox"],
            "control_applied_proof": adoption["typed_source_adoption"],
            "producer_outbox": accepted["producer_outbox"], "candidate_manifest": mp,
            "required_evidence": evidence, "acceptance_scope": "candidate_source_only",
            "business_goal_closed": False, "external_permission_issued": False}


def _wardrobe_original_w_pilot(root, w_pilot):
    """Re-read the original A2 native W pilot and its current WEB source."""
    import wardrobe_site_publish_runtime as wardrobe
    from goal_delivery_runtime import _native_document
    if not isinstance(w_pilot, dict) or w_pilot.get("task_id") != wardrobe.TASK:
        raise WorkflowError("original W identity required")
    preflight = _completion_pin(root, w_pilot.get("source_preflight"))
    sha = preflight.get("expected_main_sha")
    action = wardrobe.action_for(sha)
    w_snapshot = read_json(snapshot_path(root, wardrobe.TASK))
    context = wardrobe.validate(root, w_snapshot, action, wardrobe.SCOPE,
                                wardrobe.SOURCE_THREAD, wardrobe.SOURCE_MESSAGE,
                                w_pilot["source_preflight"]["path"])
    if context.get("request") != w_pilot["source_preflight"]:
        raise WorkflowError("current original WEB source differs")
    base = "logs/handoffs/2026-10-16-wardrobe-issuer-runtime-continuation-v1/A2-independent/"
    facts_pin = {"path": base + "actual-W-fresh-source-normal-pilot-native-execution-facts-v1.json",
                 "sha256": "55f794fe066ec639b3b25d15749459cd04fa7149cfe2defb0a65f20bc523e0da", "size": 4098}
    result_pin = {"path": base + "actual-installed-normal-W-fresh-real-source-zero-write-pilot-v1.json",
                  "sha256": "7049a34f3057f6880e1d955295c7bd2949059b5d81121c5a913d57c4deb423d4", "size": 2864}
    if (w_pilot.get("execution_facts") != facts_pin or w_pilot.get("normal_pilot_result") != result_pin
            or w_pilot["source_preflight"] != {"path": base + "actual-original-WEB-fresh-R3-source-preflight-envelope-v1.json",
                    "sha256": "c807c5e26dadee51080ae221ff4c534adebc2151fde9bc3b2a80c7fe13657e12", "size": 2630}):
        raise WorkflowError("exact existing A2 W pilot source pins required")
    facts = _completion_pin(root, facts_pin)
    result = _completion_pin(root, result_pin)
    if (facts.get("schema") != "actual-installed-readonly-W-pilot-native-execution-facts/v1"
            or facts.get("normal_pilot_result") != result_pin
            or facts.get("actual_native_execution") != w_pilot.get("actual_native_execution")
            or facts.get("native_execution_id") != w_pilot.get("native_execution_id")
            or facts.get("execution_output") != w_pilot.get("execution_output")
            or facts.get("external_writes") != 0 or facts.get("real_apr_or_run_id_generated") is not False
            or facts.get("formal_N_completion_claimed") is not False):
        raise WorkflowError("authentic original A2 W pilot execution facts required")
    native = _native_document(root, facts["actual_native_execution"])
    from qa_review_plan import _review_native_containers
    _review_native_containers(native)
    fixed = department_registry(root)["operations-assistant-2"]["chat_binding"]
    if (native.get("thread", {}).get("id") != fixed["task_id"]
            or any(native.get("thread", {}).get(key) != fixed[key] for key in ("title", "cwd"))):
        raise WorkflowError("actual original A2 fixed W pilot execution required")
    executions = [(turn, item) for turn in native.get("turns", []) for item in turn.get("items", [])
                  if item.get("type") == "commandExecution" and item.get("id") == facts["native_execution_id"]]
    output = facts["execution_output"]
    if len(executions) != 1 or not isinstance(output, dict):
        raise WorkflowError("one real complete W pilot execution required")
    turn, executed = executions[0]
    raw = validation_bytes(safe_path(root, output.get("path", "")))
    if (file_digest(root, output["path"]) != output or executed.get("status") != "completed"
            or executed.get("exitCode") != 0 or executed.get("cwd") != str(Path(root).resolve())
            or turn.get("id") != facts.get("execution_turn_id")
            or executed.get("command") != facts.get("execution_command")
            or _completion_execution_output(executed) != raw):
        raise WorkflowError("actual successful no-write W command and full output required")
    try:
        returned = json.loads(raw)
    except ValueError as error:
        raise WorkflowError("one exact W pilot JSON result required") from error
    if (returned.get("report") != result_pin or returned.get("outcome") != result
            or result.get("schema") != "A2-actual-normal-installed-W-fresh-source-readonly-pilot/v1"
            or result.get("status") != "PASS_ZERO_WRITE_SOURCE_READINESS"
            or result.get("context") != context
            or result.get("source_envelope") != context["request"]
            or result.get("installed_runtime") != file_digest(root, "tools/wardrobe_site_publish_runtime.py")
            or result.get("ledgers_before") != result.get("ledgers_after")
            or result.get("ledger_sizes_unchanged") is not True
            or result.get("permissions_issued") is not False
            or result.get("external_writes") != 0 or result.get("CMS_Save") != 0):
        raise WorkflowError("original W read-only result must match current source and no-write facts")
    follow_pin = {"path": base + "actual-W-real-fresh-WEB-source-PASS-original-operations-exact-issuer-next-followthrough-v1-record.json",
                  "sha256": "75b9a721c46cf202c067acd0b692a8d43139b37246cec99c27a283f3f7fa5c0c", "size": 10753}
    if w_pilot.get("next_action_record") != follow_pin:
        raise WorkflowError("actual original W named next action required")
    follow = _completion_pin(root, follow_pin)
    rows = _result_handoff_rows(root, wardrobe.TASK)
    matches = [row for row in rows if row.get("record_id") == follow.get("record_id")]
    if (len(matches) != 1 or matches[0].get("record_hash") != follow.get("record_hash")
            or matches[0].get("event") != "controller_followthrough"
            or matches[0].get("followthrough_status") != "blocked_with_owner"
            or result_pin not in matches[0].get("evidence", [])
            or not matches[0].get("unblock_condition")
            or not matches[0].get("next_check_at")
            or matches[0].get("business_goal_closed") is not False):
        raise WorkflowError("original W next issuer/platform dependency has no actual followthrough")



def _wardrobe_existing_w_t_pilot(root, snapshot, requirement, accepted, journal):
    """The frozen N criterion 2: prove the two original tasks, not a fabricated child."""
    import result_coordination as coordination

    task = "fc-20261016-wardrobe-issuer-and-receipt-runtime-v1"
    scope = "project:flashcast:wardrobe-issuer-and-receipt-runtime:v1"
    contract = {"path": "logs/handoffs/2026-10-16-wardrobe-issuer-runtime-continuation-v1/complete-runtime-goal.json",
                "sha256": "51b75fe1bcf29756de10c4aa39dd4ca36f9c36db505c159751d5cfa2c807c5e3", "size": 4693}
    authority = {"path": "logs/handoffs/2026-10-16-wardrobe-issuer-runtime-continuation-v1/actual-original-runtime-plan-human-authorization.json",
                 "sha256": "e3024e819f8b3858390af62ca5400c1ef34115ac6fb56d93b17797685f6eb6fc", "size": 9573}
    if (snapshot.get("task_id") != task or snapshot.get("goal_contract") != contract
            or snapshot.get("goal_delivery", {}).get("authorization_pin") != authority
            or snapshot["goal_delivery"].get("responsible_assistant") != "operations-assistant-2"
            or requirement != next((row for row in _completion_pin(root, contract)["completion_requirements"]
                                    if row.get("requirement_id") == "wardrobe-runtime-internal_pilot"), None)
            or requirement.get("criterion_index") != 2 or requirement.get("scope") != scope
            or accepted.get("identity", {}).get("task_id") != task
            or accepted["identity"].get("sender_department") != "system-development"
            or journal.get("schema") != "wardrobe-existing-W-T-readonly-pilot/v1"
            or journal.get("task_id") != task or journal.get("scope") != scope
            or journal.get("identity") != accepted["identity"]
            or journal.get("source_fingerprint") != accepted["source_fingerprint"]
            or journal.get("external_writes") != 0
            or journal.get("permissions_issued") is not False
            or journal.get("business_goal_closed") is not False):
        raise WorkflowError("exact frozen N existing-W-and-T pilot contract required")
    _completion_pin(root, authority)

    # The first installation and the current accepted successor must both be real CAS effects.
    v4_pin = {"path": "backups/fc-20261016-wardrobe-issuer-and-receipt-runtime-v1/A2-V4-85466589-eea6-4c9f-9e74-eae865a4995b/journal.json",
              "sha256": "b0b982a939e0627842c6004f2bb7be7e396784290bf33d81856a7e66984fb95a", "size": 2986}
    if journal.get("v4_adoption_journal") != v4_pin:
        raise WorkflowError("exact original V4 adoption journal required")
    original = _completion_pin(root, v4_pin)
    if (original.get("schema") != "wardrobe-four-file-source-adoption/v1"
            or original.get("state") != "adopted"
            or original.get("actor") != "operations-assistant-2"
            or original.get("candidate_fingerprint") != "ebb3f3bda2bce79c6274d3ffe94dfc7beedad49078065aea33d7f5c2c4c8359a"
            or original.get("authorized_source") != authority
            or original.get("external_writes") != 0 or original.get("permissions_issued") is not False
            or {row.get("path") for row in original.get("source_operations", [])} != {
                "tools/workflow_control.py", "tools/result_coordination.py", "tools/flashcast_ops.py",
                "tools/wardrobe_site_publish_runtime.py"}):
        raise WorkflowError("actual original V4 four-file adoption required")
    for operation in original["source_operations"]:
        if operation.get("applied") is not True:
            raise WorkflowError("original V4 CAS operation incomplete")
        if operation["path"] != "tools/workflow_control.py":
            if file_digest(root, operation["path"])["sha256"] != operation.get("after_sha256"):
                raise WorkflowError("original V4 installed runtime has changed")
    current = _completion_pin(root, journal.get("current_adoption_journal"))
    manifest = _completion_pin(root, journal.get("current_manifest"))
    accepted_box = _completion_pin(root, accepted.get("producer_outbox"))
    if (current.get("state") != "adopted" or current.get("actor") != "operations-assistant-2"
            or current.get("authorized_source") != authority
            or current.get("candidate_manifest") != journal["current_manifest"]
            or current.get("candidate_fingerprint") != accepted["source_fingerprint"]
            or current.get("external_writes") != 0 or current.get("permissions_issued") is not False
            or manifest.get("candidate_fingerprint") != accepted["source_fingerprint"]
            or manifest.get("task_id") != task or manifest.get("scope") != scope
            or manifest.get("changes") is None
            or accepted.get("candidate") != journal["current_manifest"]
            or accepted_box.get("evidence", {}).get("manifest") != journal["current_manifest"]
            or accepted_box.get("candidate_fingerprint") != accepted["source_fingerprint"]):
        raise WorkflowError("current independently accepted source adoption missing")
    changes = manifest["changes"]
    operations = current.get("source_operations")
    if (not isinstance(changes, list) or not changes or not isinstance(operations, list)
            or [row.get("path") for row in changes] != [row.get("path") for row in operations]):
        raise WorkflowError("current exact reviewed CAS change set required")
    for change, operation in zip(changes, operations):
        if (operation.get("applied") is not True
                or operation.get("after_sha256") != change.get("candidate", {}).get("sha256")
                or file_digest(root, operation["path"])["sha256"] != operation["after_sha256"]):
            raise WorkflowError("current accepted source live readback differs")
    source_requirement = next((row for row in _completion_pin(root, contract)["completion_requirements"]
                               if row.get("requirement_id") == "wardrobe-runtime-source_adoption"), None)
    source_proof = goal_typed_completion_proof(root, snapshot, [], source_requirement, accepted,
                                               proof_pin=journal.get("source_adoption_proof"))
    if (source_proof.get("state") != "PROVEN"
            or journal.get("current_adoption_journal") not in source_proof.get("evidence", [])):
        raise WorkflowError("current source must have real native independently adopted proof")

    t = journal.get("T")
    t_task = "fc-20261015-schema3-qa-outbox-consumer-repair-v1"
    if not isinstance(t, dict) or t.get("task_id") != t_task:
        raise WorkflowError("original T identity required")
    t_snapshot = read_json(snapshot_path(root, t_task))
    rows, invalid = _validate_receipt_chain(root, t_task)
    if invalid or validate_workflow_events(root, t_task) or t_snapshot.get("current_state") != "closed":
        raise WorkflowError("actual original T closed source chain required")
    qa = [row for row in rows if row.get("receipt_id") == t.get("qa_receipt_id")
          and row.get("receipt_type") == "qa_verdict" and row.get("verdict") == "pass"]
    events = [row for row in read_jsonl(root / WORKFLOW_EVENTS)
              if row.get("task_id") == t_task and row.get("event_id") == t.get("marker_event_id")]
    if (t.get("qa_receipt_id") != "e8bec2bb-152d-4bcc-955e-2ced62516d52"
            or t.get("qa_receipt_hash") != "8c97547842255adaaa2af7ddd0136198492c01f62abf3c54bdc172b0dbded384"
            or t.get("marker_event_id") != "e722d993-7ed4-4c54-a4a6-d762bf8aee03"
            or t.get("marker_event_hash") != "001ce21db913edb4342c3f867251bad4f9b6002d7c28676e56b17aab6796e468"
            or t.get("original_queue_id") != "58fd7a4f-bd66-42e6-a9ed-0d9cd62e3321"
            or t.get("original_queue_hash") != "8390a5670909d9e3c692f3791672f29440d1f816c64e648d58abf43971cd6981"
            or len(qa) != 1 or qa[0].get("receipt_hash") != t.get("qa_receipt_hash")
            or len(events) != 1 or events[0].get("event_hash") != t.get("marker_event_hash")
            or events[0].get("state") != "closed"
            or events[0].get("details") != {"qa_receipt_id": qa[0]["receipt_id"],
                                               "qa_receipt_hash": qa[0]["receipt_hash"],
                                               "reconciled": True, "same_state_formal_qa_commit": True}):
        raise WorkflowError("actual original T PASS and same-state marker required")
    identity = coordination.exact_identity(t.get("notification_identity", {}))
    knowledge = coordination.hq_knowledge_source(root, identity)
    queue = knowledge.get("queued_source", {})
    if (identity.get("task_id") != t_task or identity.get("sender_department") != "operations-assistant-2"
            or identity.get("result_sha256") != "8c692d924c900d92f6bd00ec2d4ed29017da5e28871ad0c0b80a1bdc53d60b9b"
            or knowledge.get("acceptance_proven") is not True
            or knowledge.get("notification_proven") is not True
            or knowledge.get("HQ_second_review_required") is not False
            or knowledge.get("qa_receipt") != qa[0]
            or knowledge.get("source_commit") != events[0]
            or queue.get("record_id") != t.get("original_queue_id")
            or queue.get("record_hash") != t.get("original_queue_hash")
            or queue.get("event") != "notification_queued"
            or queue.get("outbox") != knowledge.get("outbox")):
        raise WorkflowError("original T queue source or QA recovery differs")

    _wardrobe_original_w_pilot(root, journal.get("W"))


def _fe689_remaining_context(root, manifest_pin, *, allow_closed=False):
    """A source-only continuation of the accepted V4, never a new goal QA."""
    import result_coordination as c
    task = 'fc-20261023-chatgpt-fe689-runtime-adoption-stage-v1'
    scope = 'project:flashcast:chatgpt-fe689:runtime-adoption-stage:20261023:v1'
    m = _completion_pin(root, manifest_pin)
    if (m.get('schema') != 'fe689-accepted-V4-remaining-source/v1'
            or m.get('task_id') != task or m.get('scope') != scope
            or m.get('department') != 'system-development'
            or m.get('reviewer') != 'operations-assistant'
            or m.get('external_writes') != 0 or m.get('permissions_issued') is not False):
        raise WorkflowError('one original fe689 internal remaining-source manifest required')
    snapshot = read_json(snapshot_path(root, task))
    rows, bad = _validate_receipt_chain(root, task)
    goal = snapshot.get('goal_delivery', {})
    if (bad or validate_workflow_events(root, task)
            or (snapshot.get('current_state') in TERMINAL_STATES and not (allow_closed and snapshot.get('current_state') == 'closed'))
            or goal.get('responsible_assistant') != 'operations-assistant'
            or goal.get('primary_owner') != 'system-development'
            or goal.get('authorized_scope') != [scope]
            or goal.get('authorization_pin') != m.get('authorized_source')
            or m.get('authorized_source', {}).get('sha256') != '5568a10ef0e63fc7558695704a4e10d500605a7340de31cc35012edc25aab0df'
            or m.get('goal_contract', {}).get('sha256') != 'f06f371a593adcf8002eaa312e6dfaf6c9baa9d03df2055bcd5b422d8c17c725'
            or m.get('normal_plan', {}).get('sha256') != '9c277681df8e94537fd5ac3e404f37ecfe5987387cda4e39e58a0759b89d2c08'
            or snapshot.get('qa_review_plan', {}).get('pin') != m.get('normal_plan')):
        raise WorkflowError('intact nonterminal original goal, authorization and unchanged V4 plan required')
    for key in ('authorized_source', 'goal_contract', 'normal_plan', 'original_candidate'):
        _completion_pin(root, m.get(key))
    import goal_delivery_runtime as g
    expected = g.validate_goal(root, _completion_pin(root, m['goal_contract']), task_id=task)
    if (snapshot.get('goal_contract') != m['goal_contract']
            or {k:v for k,v in goal.items() if k != 'approved_actions'} != expected
            or snapshot.get('qa_review_plan', {}).get('current_assignment_review_source', {}).get('sha256')
                != '30ba080ee5fb7f63165dd358603889f69a06abe87e4e223d5aafe901fb3a9f11'):
        raise WorkflowError('original immutable contract and actual sole A1 responsibility source required')
    helper_pin = m.get('original_contract_helper')
    if not isinstance(helper_pin,dict) or helper_pin.get('sha256') != 'ecdb0d541b4c5b962b47fdb3ea93cda45bf37ce82f63c8dcc7462919e681abc1':
        raise WorkflowError('original independently reviewed registered-action validator required')
    if file_digest(root,helper_pin['path']) != helper_pin:
        raise WorkflowError('original contract validator changed')
    if snapshot.get('current_state') not in TERMINAL_STATES:
        import importlib.util
        spec = importlib.util.spec_from_file_location('original_fe689_contract_guard', safe_path(root,helper_pin['path']))
        helper = importlib.util.module_from_spec(spec); spec.loader.exec_module(helper)
        helper.validate_registered_contract(root,snapshot,g.restore_goal(root,snapshot)['goal_delivery'],expected,rows)
    subject = goal_completion_subject(root, snapshot, rows, {'mode': 'latest_exact_accepted_result', 'producer_department': 'system-development', 'scope': scope})
    if (subject.get('state') != 'PROVEN' or subject.get('candidate') != m.get('original_candidate')
            or subject.get('candidate', {}).get('sha256') != '4b6664f76b4e638ed8f88ee104dd7cefa4970ae93cd309032285c9c8ab7fd80d'
            or subject.get('identity', {}).get('result_sha256') != 'd8d732ff62bba31739411b4e3957d0557fb93c4074854f2234bcef379badb9ab'
            or subject.get('source_fingerprint') != m.get('original_source_fingerprint')):
        raise WorkflowError('the original independently PROVEN whole-stage identity must remain current')
    qa = [row for row in rows if row.get('receipt_type') == 'qa_verdict']
    if not qa or qa[-1].get('receipt_id') != '09b41c36-f634-4987-8a1d-eab7da55b1d4' or qa[-1].get('verdict') != 'pass':
        raise WorkflowError('exact original formal PASS required; this entry cannot reopen QA')
    original = _completion_pin(root, m.get('original_adoption'))
    if (m['original_adoption']['sha256'] != '80474c36ef4892650ce7ccda059b1c8e13ba170444ae109f1601bcf9caa0e8d3'
            or original.get('state') != 'adopted' or original.get('actor') != 'operations-assistant'
            or original.get('candidate_manifest') != subject['candidate']
            or original.get('authorized_source') != goal['authorization_pin']):
        raise WorkflowError('actual original three-file adoption journal required')
    report = _completion_pin(root, m.get('selector_independent_review'))
    reviewed = _completion_pin(root, m.get('selector_reviewed_manifest'))
    if (m['selector_independent_review']['sha256'] != '3208dd8c170cb8ac1a1ded72552d971886c6c98c248162310e584fb6456734cb'
            or report.get('compatible_new_candidate') != m['selector_reviewed_manifest']
            or report.get('reviewer') != 'operations-assistant' or report.get('new_independent_helper_checks') != 20
            or report.get('verdict') != 'PASS_LOCAL_NEW_DELTA_ONLY'):
        raise WorkflowError('actual independently reviewed identical selector source required')
    changes = m.get('changes', [])
    consumer = m.get('consumer_changes', [])
    if (len(changes) != 1 or len(consumer) != 1
            or changes[0].get('path') != 'tools/goal_delivery_runtime.py'
            or changes[0].get('expected_source', {}).get('sha256') != '22ce98d3275637a5c1cdf91b9d435f2919e1004f53ce6e2b37ffc0ec41aadee6'
            or changes[0].get('candidate', {}).get('sha256') != '234d861e74c92b018555b9731a1e8197656496f057ba6d490fbc2d24f4fef524'
            or changes[0].get('mode') != '0600'
            or consumer[0].get('path') != 'tools/workflow_control.py'
            or consumer[0].get('expected_source', {}).get('sha256') != '17a5ccb1d840fe7a3e5e193d42b263204d5584a4ae4655532a75194042c41d74'
            or consumer[0].get('mode') != '0644'):
        raise WorkflowError('one exact selector delta and its separately reviewed source consumer only')
    for change in changes + consumer:
        pin = change['candidate']
        if file_digest(root, pin['path']) != pin:
            raise WorkflowError('immutable remaining-source candidate changed')
    prior = [item for item in reviewed.get('changes', []) if item.get('path') == changes[0]['path']]
    if len(prior) != 1 or prior[0]['candidate']['sha256'] != changes[0]['candidate']['sha256']:
        raise WorkflowError('selector bytes must be exactly those already independently reviewed')
    intake = [row for row in _result_handoff_rows(root, task)
              if row.get('record_id') == report.get('actual_result_intake')]
    if (len(intake) != 1 or intake[0].get('event') != 'controller_received'
            or intake[0].get('coordinator_role') != 'operations-assistant'
            or intake[0].get('result_sha256') != 'd60e342933784976855c20f4eab00686eb617cb3cc6b88642b2c4703564ed03d'):
        raise WorkflowError('actual unique original A1 selector intake required')
    c._committed_result(root, intake[0])
    for key in ('checks', 'reused_evidence'):
        for pin in m.get(key, []):
            if file_digest(root, pin['path']) != pin:
                raise WorkflowError('remaining-source check or reused evidence changed')
    return snapshot, rows, subject, m


def _fe689_remaining_review(root, input_pin, *, allow_closed=False):
    """Authenticate new consumer review through real A1 command then pinned reply."""
    import goal_delivery_runtime as g
    import result_coordination as c
    import qa_review_plan as q
    item = _completion_pin(root, input_pin)
    snapshot, rows, subject, m = _fe689_remaining_context(root, item.get('manifest'), allow_closed=allow_closed)
    report = _completion_pin(root, item.get('independent_review_report'))
    delivery = item.get('delivery', {})
    box = _completion_pin(root, delivery.get('outbox'))
    intake = [row for row in _result_handoff_rows(root, snapshot['task_id'])
              if row.get('record_id') == delivery.get('received_record_id')]
    if (len(intake) != 1 or intake[0].get('event') != 'controller_received'
            or intake[0].get('coordinator_role') != 'operations-assistant'
            or intake[0].get('outbox') != delivery.get('outbox')
            or box.get('task_id') != snapshot['task_id'] or box.get('department') != 'system-development'
            or box.get('candidate_manifest') != item.get('manifest')
            or box.get('candidate_fingerprint') != m.get('candidate_fingerprint')
            or item['manifest'] not in (list(box['evidence'].values()) if isinstance(box.get('evidence'),dict) else (box.get('evidence') or []))):
        raise WorkflowError('real current complete source supplement and unique A1 committed intake required')
    c._committed_result(root, intake[0])
    if (report.get('schema') != 'fe689-remaining-source-independent-review/v1'
            or report.get('task_id') != snapshot['task_id'] or report.get('scope') != m['scope']
            or report.get('reviewer') != 'operations-assistant' or report.get('verdict') != 'PASS_LOCAL'
            or report.get('manifest') != item['manifest'] or report.get('delivery') != delivery
            or report.get('original_QA_unchanged') is not True
            or report.get('external_writes') != 0 or report.get('permissions_issued') is not False
            or _parse_observed_at(report.get('created_at')) is None
            or _parse_observed_at(m.get('created_at')) is None
            or _parse_observed_at(report['created_at']) < _parse_observed_at(m['created_at'])):
        raise WorkflowError('actual original A1 bounded source review required, never SYS self-review')
    checks = _completion_pin(root, report.get('actual_checks'))
    review_root = Path(root)/'logs/handoffs/2026-10-23-chatgpt-launch-critical-path-recovery-v1/system-development-fe689-runtime-adoption-stage-v1/A1-actual-stage-responsibility-and-adoption-resume-20261023-v1'
    if (not safe_path(root,item['independent_review_report']['path']).is_relative_to(review_root)
            or not safe_path(root,report['actual_checks']['path']).is_relative_to(review_root)
            or checks.get('manifest') != item['manifest']
            or checks.get('candidate_workflow') != m['consumer_changes'][0]['candidate']
            or checks.get('reused_selector') != m['changes'][0]['candidate']
            or checks.get('failures') != 0 or checks.get('errors') != 0 or checks.get('tests', 0) < 16
            or checks.get('business_validators_mocked') is not False
            or checks.get('state_writes_isolated') is not True
            or checks.get('normal_stage_writer_readback_duplicate') is not True):
        raise WorkflowError('actual isolated normal source writer and boundary checks required')
    native = g._collaboration_native(root, item.get('actual_A1_native'))
    q._review_native_containers(native)
    fixed = department_registry(root)['operations-assistant']['chat_binding']
    if (any(native.get('thread', {}).get(k) != fixed.get(v)
            for k, v in {'id':'task_id', 'title':'title', 'cwd':'cwd'}.items())
            or native['thread'].get('projectId') not in {None, fixed['project_id']}
            or fixed['cwd'] != str(Path(root).resolve())):
        raise WorkflowError('actual fixed same-project A1 native required')
    turns = [t for t in native.get('turns', []) if t.get('id') == item.get('source_turn_id')]
    if len(turns) != 1 or turns[0].get('status') not in {'completed', 'inProgress'}:
        raise WorkflowError('one actual independent A1 source turn required')
    found = {x.get('id'): (i,x) for i,x in enumerate(turns[0].get('items', []))}
    ci, command = found.get(item.get('source_command_id'), (-1, {}))
    mi, message = found.get(item.get('source_message_id'), (-1, {}))
    if (ci < 0 or ci >= mi or command.get('type') != 'commandExecution'
            or command.get('status') != 'completed' or command.get('exitCode') != 0
            or command.get('cwd') != str(Path(root).resolve())
            or str(safe_path(root, m['test_runner']['path'])) not in command.get('command', '')
            or str(safe_path(root, report['actual_checks']['path']).parent) not in command.get('command', '')
            or message.get('type') != 'agentMessage' or message.get('phase') not in {'commentary','final_answer'}
            or item['independent_review_report']['sha256'] not in message.get('text', '')
            or snapshot['task_id'] not in message.get('text', '')):
        raise WorkflowError('successful actual A1 test command then exact pinned independent conclusion required')
    return item, m, snapshot, subject


def record_fe689_remaining_source(root, input_path, role):
    """Append independent source acceptance without changing the PASS/plan/producer."""
    if role != 'operations-assistant':
        raise WorkflowError('original sole A1 source acceptance required')
    pin = file_digest(root, input_path)
    with workflow_lock(root):
        item = _completion_pin(root, pin)
        snapshot, _, _, m = _fe689_remaining_context(root, item.get('manifest'))
        if item.get('selector_independent_review') != m['selector_independent_review']:
            raise WorkflowError('exact already independently reviewed one-file selector acceptance required')
        events = [row for row in read_jsonl(root / WORKFLOW_EVENTS)
                  if row.get('task_id') == snapshot['task_id']
                  and row.get('details', {}).get('fe689_remaining_source')]
        if events:
            prior = events[-1]
            if prior['details']['fe689_remaining_source']['input'] != pin:
                raise WorkflowError('one immutable exact remaining-source acceptance; differing source refused')
            return {'state': 'duplicate_ignored', 'event_id': prior['event_id'], 'event_hash': prior['event_hash']}
        event = append_workflow_event(root, snapshot['task_id'], snapshot['current_state'],
            {'fe689_remaining_source': {'input': pin, 'manifest': item['manifest'],
             'reviewer': role, 'whole_goal_QA_unchanged': True}})
        return {'state': 'SOURCE_ACCEPTED_NOT_ADOPTED', 'event_id': event['event_id'],
                'event_hash': event['event_hash'], 'manifest': item['manifest']}


def _fe689_source_successor_operation(root, journal, change):
    """Check an exact permanent CAS successor without rewriting the old operation."""
    ops = journal.get('source_operations', [])
    if (journal.get('state') != 'adopted' or journal.get('actor') != 'operations-assistant'
            or journal.get('executor') != 'operations-assistant'
            or journal.get('external_writes') != 0 or journal.get('permissions_issued') is not False
            or journal.get('task_id') != 'fc-20261023-chatgpt-fe689-runtime-adoption-stage-v1'
            or len(ops) != 1 or journal.get('fixture_only') is not False):
        raise WorkflowError('one real original A1 permanent source CAS journal required')
    op = ops[0]; mode = int(change['mode'], 8)
    if (op.get('path') != change['path'] or op.get('before_sha256') != change['expected_source']['sha256']
            or op.get('after_sha256') != change['candidate']['sha256'] or op.get('mode') != mode
            or op.get('applied') is not True or file_digest(root, op['backup']['path']) != op['backup']
            or op['backup']['sha256'] != op['before_sha256']
            or safe_path(root, op['backup']['path']).stat().st_mode & 0o777 != mode
            or safe_path(root, op['path']).stat().st_mode & 0o777 != mode):
        raise WorkflowError('exact successor before/after/current mode and recoverable backup required')
    if (file_digest(root,op['path'])['sha256'] != op['after_sha256']
            and _congestion_lifecycle_preserved_fe689_source(root,op['path'],op['after_sha256'],mode) is None):
        raise WorkflowError('exact original source or real independently completed C10 successor required')
    return op


def _fe689_remaining_effect_chain(root, snapshot, accepted, proof):
    """Old three-file journal plus explicit real source successors, never relabelled."""
    import goal_delivery_runtime as g
    chain = proof.get('remaining_source')
    if not isinstance(chain, dict):
        raise WorkflowError('actual remaining-source chain required')
    events = [row for row in read_jsonl(root / WORKFLOW_EVENTS)
              if row.get('event_id') == chain.get('event_id') and row.get('task_id') == snapshot['task_id']]
    if len(events) != 1 or events[0].get('event_hash') != chain.get('event_hash'):
        raise WorkflowError('actual committed immutable source-stage event required')
    source = events[0].get('details', {}).get('fe689_remaining_source', {})
    item = _completion_pin(root, source.get('input'))
    current, _, subject, m = _fe689_remaining_context(root, item.get('manifest'), allow_closed=True)
    review_input = chain.get('independent_review_input')
    review, _, _, _ = _fe689_remaining_review(root, review_input, allow_closed=True)
    if review.get('manifest') != item.get('manifest'):
        raise WorkflowError('same exact separately reviewed consumer and selector source required')
    if (source.get('manifest') != item['manifest'] or current['task_id'] != snapshot['task_id']
            or accepted.get('identity') != subject['identity'] or proof.get('journal') != m['original_adoption']):
        raise WorkflowError('successors must retain the original entire three-file journal and accepted identity')
    evidence = [source['input'], item['manifest'], review_input, review['independent_review_report'], review['actual_A1_native']]
    endpoints = {}
    previous = _parse_observed_at(_completion_pin(root, m['original_adoption']).get('completed_at'))
    for key, change in (('consumer',m['consumer_changes'][0]), ('selector',m['changes'][0])):
        layer = chain.get(key, {}); jp = layer.get('journal'); journal = _completion_pin(root, jp)
        if (safe_path(root,jp['path']).parent/'rollback-journal.json').exists():
            raise WorkflowError('revoked successor journal cannot prove current source adoption')
        if (journal.get('candidate_manifest') != item['manifest']
                or journal.get('authorized_source') != m['authorized_source']
                or journal.get('independent_review_input') != review_input):
            raise WorkflowError('exact independently accepted successor source and authorization required')
        started = _parse_observed_at(journal.get('started_at')); ended = _parse_observed_at(journal.get('completed_at'))
        if previous is None or started is None or ended is None or not previous <= started <= ended:
            raise WorkflowError('real original adoption then ordered successor chronology required')
        if key == 'consumer' and _parse_observed_at(events[0]['created_at']) < ended:
            raise WorkflowError('normal source acceptance must follow actual consumer bootstrap')
        if key == 'selector' and _parse_observed_at(events[0]['created_at']) > started:
            raise WorkflowError('selector adoption must follow actual source-stage acceptance')
        op = _fe689_source_successor_operation(root, journal, change)
        native = g._native_document(root, layer.get('actual_native_execution'))
        items = [x for t in native.get('turns', []) for x in t.get('items', [])
                 if x.get('type') == 'commandExecution' and x.get('id') == layer.get('native_execution_id')]
        output = layer.get('execution_output')
        if not isinstance(output, dict) or file_digest(root, output.get('path', '')) != output:
            raise WorkflowError('exact native successor execution output required')
        raw = validation_bytes(safe_path(root, output['path']))
        if (native.get('thread', {}).get('id') != department_registry(root)['operations-assistant']['chat_binding']['task_id']
                or len(items) != 1 or items[0].get('status') != 'completed' or items[0].get('exitCode') != 0
                or items[0].get('cwd') != str(Path(root).resolve())
                or not layer.get('execution_command') or items[0].get('command') != layer['execution_command']
                or str(safe_path(root,m['execution_helper']['path'])) not in items[0].get('command','')
                or ('apply --kind '+key) not in items[0].get('command','')
                or review_input['path'] not in items[0].get('command','')
                or _completion_execution_output(items[0]) != raw
                or any(v.encode() not in raw for v in (jp['path'], jp['sha256'], item['manifest']['sha256']))):
            raise WorkflowError('actual A1 successful successor command and exact pinned output required')
        _completion_native_stage(root, proof, jp, 'operations-assistant')
        endpoints[op['path']] = op['after_sha256']
        evidence.extend([jp, layer['actual_native_execution'], output]); previous = ended
    _completion_native_stage(root, proof, item['manifest'], 'operations-assistant')
    return endpoints, evidence



def _completion_reviewed_source_mode(change):
    """Read the already accepted CAS mode without silently changing permissions."""
    expected = change.get('expected_source')
    has_source_mode = isinstance(expected, dict) and 'mode' in expected
    source_mode = expected.get('mode') if has_source_mode else None
    if has_source_mode and (type(source_mode) is not int or not 0 <= source_mode <= 0o777):
        raise WorkflowError('exact reviewed integer source mode required')
    if 'mode' in change:
        try:
            mode = int(str(change['mode']), 8)
        except (ValueError, TypeError) as error:
            raise WorkflowError('valid explicit reviewed source mode required') from error
        if not 0 <= mode <= 0o777 or (source_mode is not None and mode != source_mode):
            raise WorkflowError('explicit and exact reviewed source modes differ')
        return mode
    return source_mode if has_source_mode else 0o644


def goal_typed_completion_proof(root, snapshot, receipts, requirement, accepted, *, proof_pin=None):
    """Read actual typed effect journals; never infer adoption or pilot from PASS."""
    try:
        if not accepted or accepted.get("state") != "PROVEN":
            return {"state": "MISSING", "reason": "exact candidate acceptance missing"}
        current_identity=accepted["identity"]
        decisions=[row for row in _result_handoff_rows(root,snapshot["task_id"])
                   if row.get("event")=="controller_decision" and row.get("coordinator_role")==snapshot["goal_delivery"]["responsible_assistant"]
                   and _result_identity(row)==tuple(current_identity[k] for k in ("sender_department","candidate_version","result_sha256"))
                   and row.get("remaining_requirement_id")==requirement["requirement_id"]]
        from goal_delivery_runtime import completion_proof_selector
        selector = completion_proof_selector(requirement)
        if (proof_pin is not None and selector is not None
                and selector.get("mode") != "committed_completion_evidence" and proof_pin != selector):
            raise WorkflowError("a frozen explicit completion proof cannot be replaced")
        pin = proof_pin if proof_pin is not None else selector
        if isinstance(pin,dict) and pin.get("mode") == "committed_completion_evidence":
            rows = [row.get("details",{}).get("completion_evidence") for row in read_jsonl(root / WORKFLOW_EVENTS)
                    if row.get("task_id") == snapshot["task_id"]
                    and row.get("details",{}).get("completion_evidence",{}).get("requirement_id") == requirement["requirement_id"]]
            pin = rows[-1].get("proof_pin") if rows else None
        if not pin and decisions and decisions[-1].get("decision")=="wait_external":
            row=decisions[-1]
            follows=[item for item in _result_handoff_rows(root,snapshot["task_id"])
                     if item.get("event")=="controller_followthrough" and item.get("decision_record_id")==row["record_id"]
                     and item.get("followthrough_status") in {"external_wait_registered","blocked_with_owner"}]
            if follows:
                from scoped_candidate_adoption import _committed
                follow=follows[-1];_committed(root,row);_committed(root,follow)
                return {"state":"MISSING","reason":"actual named completion dependency wait",
                        "wait_dependency":{"owner":row["next_owner"],"next_action":row["next_action"],
                            "unblock_condition":follow["unblock_condition"],"next_check_at":follow["next_check_at"],
                            "record_id":follow["record_id"],"scope":requirement["scope"],
                            "requirement_id":requirement["requirement_id"]}}
        if not pin:
            return {"state": "MISSING", "reason": "actual " + requirement["requirement_type"] + " evidence missing"}
        proof = _completion_pin(root, pin)
        kind = requirement["requirement_type"]
        if (proof.get("proof_type") != kind or proof.get("identity") != accepted["identity"]
                or proof.get("source_fingerprint") != accepted["source_fingerprint"]
                or proof.get("scope") != requirement["scope"]):
            raise WorkflowError("typed proof must identify exact accepted task/scope/version/fingerprint")
        role = snapshot["goal_delivery"]["responsible_assistant"]
        journal_pin = proof.get("journal")
        journal = _completion_pin(root, journal_pin)
        effect_evidence = []
        if journal.get("schema") in {"flashcast-rotation-SYS-adoption-chain/v1",
                                     "flashcast-rotation-original-business-pilot/v1"}:
            from rotation_completion import effect
            evidence = effect(root, snapshot, receipts, requirement, accepted, journal)
            # Reuse an actual current independent QA outbox that explicitly pins
            # this real effect journal; otherwise retain the native-final gate.
            confirmation_pin = accepted.get("acceptance_outbox")
            confirmation = _completion_pin(root, confirmation_pin) if confirmation_pin else {}
            if (confirmation.get("department") == role and confirmation.get("qa_verdict") == "pass"
                    and confirmation.get("candidate_version") == accepted["identity"]["candidate_version"]
                    and journal_pin in confirmation.get("evidence", [])
                    and confirmation_pin in accepted.get("acceptance_receipt", {}).get("evidence", [])):
                evidence.append(confirmation_pin)
            else:
                _completion_native_stage(root, proof, journal_pin, role)
            return {"state": "PROVEN", "identity": accepted["identity"],
                    "source_fingerprint": accepted["source_fingerprint"], "source_turn_id": accepted["source_turn_id"],
                    "scope": requirement["scope"], "evidence": [pin, journal_pin, *evidence],
                    "closed_scope_only": True, "business_goal_closed": False}
        exact_source_outbox = (kind == "source_adoption"
            and snapshot.get("task_id") == "fc-20261011-goal-publication-notice-followthrough-repair-v1"
            and accepted.get("candidate") == accepted.get("producer_outbox")
            and _completion_pin(root, accepted["candidate"]).get("schema_version") == "2.0")
        if exact_source_outbox:
            source_context = _tnew_actual_source_adoption(root, snapshot, accepted, proof, journal_pin, journal)
            _completion_native_stage(root, proof, journal_pin, role)
            return {"state": "PROVEN", "identity": accepted["identity"],
                    "source_fingerprint": accepted["source_fingerprint"], "source_turn_id": accepted["source_turn_id"],
                    "scope": requirement["scope"], "evidence": [pin, journal_pin, source_context["candidate_manifest"],
                        *source_context["permanent_source_successors"]],
                    "closed_scope_only": True, "business_goal_closed": False}
        permanent_source_endpoints, permanent_source_evidence = {}, []
        if kind == "source_adoption" and "remaining_source" in proof:
            if snapshot.get("task_id") != "fc-20261023-chatgpt-fe689-runtime-adoption-stage-v1":
                raise WorkflowError("remaining-source proof belongs only to its original fe689 stage")
            permanent_source_endpoints, permanent_source_evidence = _fe689_remaining_effect_chain(root, snapshot, accepted, proof)
        if kind == "source_adoption":
            if (journal.get("state") != "adopted" or journal.get("actor") != role
                    or journal.get("authorized_source") != snapshot["goal_delivery"]["authorization_pin"]
                    or journal.get("candidate_fingerprint") != accepted["source_fingerprint"]
                    or journal.get("external_writes") != 0 or journal.get("permissions_issued") is not False):
                raise WorkflowError("real independently adopted scoped CAS journal required")
            manifest_pin = accepted["candidate"]
            if snapshot.get("task_id") == "fc-20261022-department-flow-congestion-optimization-v1":
                manifest_pin = _congestion_accepted_source_manifest(root, snapshot, accepted)
                if (accepted.get("identity",{}).get("candidate_version") == "department-flow-current-fe689-lifecycle-compatible-v10-20261024"
                        and journal.get("fixture_only") is not False):
                    raise WorkflowError("a physical fixture cannot prove actual C10 runtime adoption")
                effect_evidence.append(manifest_pin)
            manifest = _completion_pin(root, manifest_pin)
            field_operations=journal.get("field_operations",[])
            migrations=manifest.get("field_changes",[])
            if not isinstance(field_operations,list) or len(field_operations)!=len(migrations):
                raise WorkflowError("every exact reviewed configuration field needs an actual CAS effect")
            for field_pin,operation in zip(migrations,field_operations):
                migration=_completion_pin(root,field_pin)
                path,field=migration.get("source"),migration.get("field")
                if (migration.get("task_id")!=snapshot["task_id"] or migration.get("mode")!="field_CAS_only"
                        or path!="data/task-contract.json" or field!="goal_delivery_runtime"
                        or operation.get("path")!=path or operation.get("field")!=field
                        or operation.get("before_sha256")!=sha256_value(migration.get("expected"))
                        or operation.get("after_sha256")!=sha256_value(migration.get("replacement"))
                        or read_json(safe_path(root,path)).get(field)!=migration.get("replacement")):
                    raise WorkflowError("actual field CAS must preserve the exact reviewed expected/replacement")
                original=_completion_pin(root,operation.get("backup"))
                if original.get(field)!=migration.get("expected"):
                    raise WorkflowError("exact full original configuration backup required")
            changes = manifest.get("changes",[])
            operations = journal.get("source_operations")
            if (not changes or not isinstance(operations,list)
                    or [item.get("path") for item in operations] != [item.get("path") for item in changes]
                    or journal.get("candidate_manifest") != manifest_pin):
                raise WorkflowError("exact independently reviewed CAS operation set required")
            from goal_delivery_runtime import _native_document
            native = _native_document(root,proof.get("actual_native_execution"))
            if native.get("thread",{}).get("id") != department_registry(root)[role]["chat_binding"]["task_id"]:
                raise WorkflowError("actual adoption execution must originate from assigned assistant")
            execution_items = [item for turn in native.get("turns",[]) for item in turn.get("items",[])
                if item.get("type")=="commandExecution" and item.get("id")==proof.get("native_execution_id")]
            output = proof.get("execution_output")
            if (len(execution_items)!=1 or not isinstance(output,dict)
                    or file_digest(root,output.get("path","")) != output):
                raise WorkflowError("one real native CAS execution and exact output pin required")
            executed=execution_items[0]
            raw=validation_bytes(safe_path(root,output["path"]))
            if (executed.get("status")!="completed" or executed.get("exitCode")!=0
                    or executed.get("cwd")!=str(Path(root).resolve())
                    or (not proof.get("execution_command") or executed.get("command")!=proof.get("execution_command"))
                    or _completion_execution_output(executed)!=raw
                    or any(value.encode("utf-8") not in raw for value in
                        (journal_pin["path"],journal_pin["sha256"],manifest_pin["sha256"]))):
                raise WorkflowError("actual successful CAS command/output must pin journal and reviewed manifest")
            for change,operation in zip(changes,operations):
                candidate=change.get("candidate")
                if not isinstance(candidate,dict) or file_digest(root,candidate.get("path",""))!=candidate:
                    raise WorkflowError("exact reviewed source bytes pin required")
                expected=change.get("expected_source")
                if (candidate is None or operation.get("after_sha256")!=change["candidate"]["sha256"]
                        or (isinstance(expected,dict) and operation.get("before_sha256")!=expected.get("sha256"))
                        or (expected=="ABSENT" and operation.get("before_sha256")!="ABSENT")):
                    raise WorkflowError("actual CAS before/after must match exact reviewed operation")
            if not isinstance(operations, list) or not operations:
                raise WorkflowError("actual source CAS operations missing")
            for operation in operations:
                target = file_digest(root, operation["path"])
                change=next(item for item in changes if item["path"]==operation["path"])
                expected_mode=_completion_reviewed_source_mode(change)
                if (isinstance(change.get("expected_source"),dict)
                        and "mode" in change["expected_source"] and operation.get("mode") != expected_mode):
                    raise WorkflowError("actual CAS journal mode differs from exact reviewed source")
                expected_endpoint = permanent_source_endpoints.get(operation["path"], operation.get("after_sha256"))
                current_effect = None
                if target["sha256"] != expected_endpoint:
                    current_effect = _internal_source_continuation_readback(root, operation['path'], expected_endpoint, expected_mode)
                    if current_effect is not None:
                        permanent_source_evidence.extend(current_effect['evidence'])
                if (target["sha256"] != expected_endpoint
                        and current_effect is None
                        and snapshot.get("task_id") == "fc-20261023-chatgpt-fe689-runtime-adoption-stage-v1"):
                    current_effect = _congestion_lifecycle_preserved_fe689_source(root,operation["path"],expected_endpoint,expected_mode)
                    if current_effect is not None:
                        permanent_source_evidence.extend(current_effect["evidence"])
                if ((target["sha256"] != expected_endpoint and current_effect is None)
                        or safe_path(root,operation["path"]).stat().st_mode & 0o777 != expected_mode):
                    raise WorkflowError("adopted source actual readback or reviewed mode differs")
                baseline = operation.get("backup")
                if operation.get("before_sha256") != "ABSENT":
                    backup = file_digest(root, baseline["path"])
                    if backup != baseline or backup["sha256"] != operation["before_sha256"]:
                        raise WorkflowError("exact recoverable CAS before backup required")
        elif kind == "internal_pilot":
            if (snapshot.get("task_id") == "fc-20261022-department-flow-congestion-optimization-v1"
                    and journal.get("pilot_task_id") == snapshot["task_id"]):
                effect_evidence.extend(_congestion_original_queue_pilot(root,snapshot,receipts,requirement,accepted,journal))
            elif journal.get("schema") == "wardrobe-existing-W-T-readonly-pilot/v1":
                _wardrobe_existing_w_t_pilot(root, snapshot, requirement, accepted, journal)
            else:
                import result_coordination as c
                task = validate_task_id(journal.get("pilot_task_id", ""))
                pilot = read_json(snapshot_path(root, task))
                if (pilot.get("goal_delivery", {}).get("parent_task_id") != snapshot["task_id"]
                        or pilot["goal_delivery"].get("required_execution_actions")
                        or pilot["goal_delivery"].get("responsible_assistant") != role):
                    raise WorkflowError("real no-external-write same-parent pilot contract required")
                rows, invalid = _validate_receipt_chain(root, task)
                if invalid:
                    raise WorkflowError("actual pilot source chain invalid")
                for kind_name, id_key in (("outbox_received", "producer_receipt_id"), ("qa_verdict", "qa_receipt_id")):
                    matches = [row for row in rows if row.get("receipt_id") == journal.get(id_key)
                               and row.get("receipt_type") == kind_name]
                    if len(matches) != 1 or (kind_name == "qa_verdict" and matches[0].get("verdict") != "pass"):
                        raise WorkflowError("real pilot delivered and independently accepted evidence missing")
                handoffs = _result_handoff_rows(root, task)
                by_id = {row["record_id"]: row for row in handoffs}
                for key, event in (("received_record_id", "controller_received"),
                                   ("decision_record_id", "controller_decision")):
                    record = by_id.get(journal.get(key), {})
                    if record.get("event") != event:
                        raise WorkflowError("real pilot intake/decision/notification required")
                    from scoped_candidate_adoption import _committed
                    if event in c.FINAL_EVENTS:
                        _committed(root, record)
                decision = by_id[journal["decision_record_id"]]
                notice = by_id.get(journal.get("notification_record_id"), {})
                if notice.get("event") == "controller_received":
                    if (notice.get("record_id") != journal.get("received_record_id")
                            or _result_identity(decision) != _result_identity(notice)):
                        raise WorkflowError("exact same pilot intake/decision notification identity required")
                    from owner_adopted_pilot_consumer import received_notification
                    received_notification(root, pilot, notice, journal.get("notification_delivery"))
                elif notice.get("event") != "notification_sent":
                    raise WorkflowError("real pilot actual sent or received official queue notice required")
                if decision.get("decision") != "close_scope":
                    follow = by_id.get(journal.get("followthrough_record_id"), {})
                    if follow.get("followthrough_status") != "dispatch_sent":
                        raise WorkflowError("actual exact pilot next send or accepted scope close required")
                    _validate_collaboration_followthrough_receipt(root, task, decision, follow)
                recovery_pin=journal.get("duplicate_recovery_native")
                recovery=_completion_pin(root,recovery_pin)
                import qa_review_plan as q
                q._review_native_containers(recovery)
                result=q._review_raw_native_result(recovery.get("actual_tool_result",{}))
                original=by_id.get(journal.get("duplicate_recovery_record_id"),{})
                if (not original or result.get("record_id")!=original.get("record_id")
                        or result.get("result")!="duplicate_ignored" or result.get("task_id")!=task
                        or result.get("event")!=original.get("event")):
                    raise WorkflowError("actual duplicate recovery must return the original effect without another append")
                _committed(root,original)
        elif kind == "result_notification":
            import result_coordination as c
            identity = c.exact_identity(journal.get("notification_identity", {}))
            route = c.result_lane(root,identity)
            if identity["task_id"] != snapshot["task_id"]:
                raise WorkflowError("result notification must be same original task")
            if identity["sender_department"] == accepted["identity"]["sender_department"]:
                if identity != accepted["identity"]:
                    raise WorkflowError("notification must bind exact accepted producer outbox")
            elif identity["sender_department"] != role or route.get("lane") != "HQ_knowledge":
                raise WorkflowError("only exact producer delivery or assigned assistant HQ knowledge allowed")
            rows = _result_handoff_rows(root,snapshot["task_id"])
            sent = [row for row in rows if row.get("record_id") == journal.get("notification_record_id")
                    and row.get("event") in {"notification_sent","controller_received"}
                    and _result_identity(row) == tuple(identity[k] for k in ("sender_department","candidate_version","result_sha256"))]
            if len(sent)!=1:
                raise WorkflowError("actual exact sent or intake notification receipt required")
            if sent[0]["event"]=="controller_received":
                from scoped_candidate_adoption import _committed
                _committed(root,sent[0])
            else:
                _completion_pin(root,sent[0].get("actual_native_transport"))
            if route.get("lane")=="HQ_knowledge":
                c.hq_knowledge_source(root,identity,require_transport=True)
        elif kind == "growth_batch_followthrough":
            if (journal.get("task_id") != snapshot["task_id"]
                    or not isinstance(journal.get("findings"), list) or not journal["findings"]):
                raise WorkflowError("real growth batch finding/action mapping required")
            for finding in journal["findings"]:
                if finding.get("kind") == "external_wait":
                    if (not all(finding.get(k) for k in ("owner", "unblock_condition", "next_check_at"))
                            or _parse_observed_at(finding.get("next_check_at")) is None):
                        raise WorkflowError("named external wait missing")
                    linked = _result_handoff_rows(root,validate_task_id(finding.get("task_id","")))
                    record = next((row for row in linked if row.get("record_id")==finding.get("record_id")),{})
                    if (record.get("followthrough_status") not in {"external_wait_registered","blocked_with_owner"}
                            or record.get("next_check_at") != finding["next_check_at"]
                            or record.get("unblock_condition") != finding["unblock_condition"]):
                        raise WorkflowError("finding named wait needs its actual precise registered dependency")
                    from scoped_candidate_adoption import _committed
                    _committed(root,record)
                else:
                    linked = _result_handoff_rows(root, validate_task_id(finding.get("task_id", "")))
                    record = next((row for row in linked if row.get("record_id") == finding.get("record_id")),{})
                    child=read_json(snapshot_path(root,finding["task_id"]))
                    if (child.get("goal_delivery",{}).get("parent_task_id")!=snapshot["task_id"]
                            or (record.get("event"),record.get("decision"),record.get("followthrough_status"))
                            not in {("controller_decision","close_scope",None),
                                    ("controller_followthrough",None,"dispatch_sent"),
                                    ("controller_followthrough",None,"execution_verified")}):
                        raise WorkflowError("real same-parent finding action or exact accepted scope close required")
                    from scoped_candidate_adoption import _committed
                    _committed(root,record)
        else:
            raise WorkflowError("unsupported typed effect proof")
        _completion_native_stage(root, proof, journal_pin, role)
        return {"state": "PROVEN", "identity": accepted["identity"],
                "source_fingerprint": accepted["source_fingerprint"], "source_turn_id": accepted["source_turn_id"],
                "scope": requirement["scope"], "evidence": [pin, journal_pin, *permanent_source_evidence, *effect_evidence],
                "closed_scope_only": True, "business_goal_closed": False}
    except (WorkflowError, ValueError, KeyError, TypeError, OSError) as error:
        return {"state": "BLOCKED", "reason": str(error), "evidence": []}


def _derive_state(root: Path, snapshot: dict[str, Any], receipts: list[dict[str, Any]]) -> dict[str, Any]:
    from original_task_publisher_handover import legacy_context
    snapshot, receipts = legacy_context(root, snapshot, receipts)
    reviewer = _final_qa_department(root, snapshot, preparation_only=True)
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
    if missing_ack == ["operations"]:
        from native_control_result import matches, received_candidate
        if matches(snapshot) and ("outbox_received", "operations") in latest:
            candidate = latest[("outbox_received", "operations")]["evidence"][0]
            received_candidate(root, snapshot, {"producer_department": "operations", "action_class": "runtime_control",
                                                "scope": snapshot["goal_delivery"]["authorized_scope"][0], "candidate": candidate}, receipts)
            missing_ack = []
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
        from goal_delivery_runtime import completion_obligations
        obligations = completion_obligations(root, snapshot, receipts=receipts)
        if obligations["missing"] or obligations["blockers"]:
            # An already committed exact historical close remains historical.
            # New goal closure always requires the declared evidence contract.
            historical = (obligations["contract_state"] == "legacy_exact_scope"
                          and goal_legacy_scope_completion(root, snapshot, receipts).get("state") == "PROVEN")
            if not historical:
                return {"state": "qa_passed", "missing": obligations["missing"],
                        "blockers": obligations["blockers"],
                        "next": ["continue_exact_completion_requirements"],
                        "completion_obligations": obligations}
        return {"state": "closed", "missing": [], "blockers": [], "next": [],
                "closed_scope_only": obligations.get("closed_scope_only", True),
                "business_goal_closed": obligations.get("business_goal_closed", False)}
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


def _same_state_formal_qa_commit(receipts, task_events, reviewer, current_state="qa_passed"):
    """Return a commit only for a newer actual PASS absent from the event log."""
    latest = next((row for row in reversed(receipts)
                   if row.get("receipt_type") == "qa_verdict"
                   and row.get("department") == reviewer), None)
    prior = next((row for row in reversed(task_events)
                  if row.get("state") == "qa_passed"
                  and row.get("details", {}).get("qa_receipt_id")), None)
    if not latest or latest.get("verdict") != "pass" or not prior:
        return None
    if any(row.get("details", {}).get("qa_receipt_id") == latest.get("receipt_id")
           and row.get("details", {}).get("qa_receipt_hash") == latest.get("receipt_hash")
           for row in task_events):
        return None
    earlier = _parse_observed_at(prior.get("created_at"))
    new = _parse_observed_at(latest.get("created_at"))
    if earlier is None or new is None or earlier >= new:
        return None
    if current_state == "closed":
        prior_close = next((row for row in reversed(task_events)
                            if row.get("state") == "closed"), None)
        closed_at = _parse_observed_at(prior_close.get("created_at")) if prior_close else None
        if closed_at is None or new > closed_at:
            return None
    return {"reconciled": True, "same_state_formal_qa_commit": True,
            "qa_receipt_id": latest["receipt_id"], "qa_receipt_hash": latest["receipt_hash"]}


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
        from department_autonomy import autonomous_goal,reconcile as autonomous_reconcile
        if autonomous_goal(snapshot.get('goal_delivery')):
            return autonomous_reconcile(root,snapshot)
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
        from direct_system_repair import context as direct_context, completion_view as direct_completion
        direct = direct_context(root, task_id) if not invalid else None
        if invalid:
            target = "blocked_evidence_invalid"
            derived = {
                "state": target,
                "missing": [],
                "blockers": invalid,
                "next": ["restore_or_replace_evidence_and_record_new_receipt"],
            }
            resume_from = previous_state if previous_state != target else str(snapshot.get("resume_from", "evidence_received"))
        elif direct is not None:
            completion = direct_completion(root, snapshot, direct)
            derived = {"state": "closed" if completion["control_scope_completed"] else "evidence_received",
                       "missing": completion["missing"], "blockers": completion["blockers"],
                       "next": [] if completion["control_scope_completed"] else ["operations:finish_direct_internal_repair"],
                       "owner_direct_execution": direct["pin"], "completion": completion,
                       "closed_scope_only": completion["control_scope_completed"], "business_goal_closed": False}
            resume_from = ""
        elif snapshot.get("workflow_successor_link"):
            link = snapshot["workflow_successor_link"]
            if file_digest(root, link["source"]["path"]) != link["source"]:
                raise WorkflowError("original successor association evidence changed")
            derived = {"state": "blocked", "missing": [],
                       "blockers": ["existing_successor_result_intake:" + link["successor_task_id"]],
                       "next": ["receive_existing_successor_result:" + link["successor_task_id"]]}
            resume_from = "planned"
        elif (task_id == _A1_HEALTH_HISTORY_TASK
              and len(receipts) == 1
              and receipts[0].get("receipt_type") == "health_reconciled"):
            derived = {
                "state": "closed", "missing": [], "blockers": [], "next": [],
                "historical_health_reconciled": receipts[0]["receipt_id"],
                "closed_scope_only": True, "business_goal_closed": False,
            }
            resume_from = ""
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
        if derived.get("owner_direct_execution"):
            if previous_state != target:
                append_workflow_event(root, task_id, target,
                    {"reconciled": True, "owner_direct_completion": derived["owner_direct_execution"],
                     "actual_executor": "operations", "source_adopted": True,
                     "closed_scope_only": derived["closed_scope_only"], "business_goal_closed": False,
                     "assistant_verdict_created": False})
        elif derived.get("historical_health_reconciled"):
            if previous_state != "closed":
                append_workflow_event(
                    root, task_id, "closed",
                    {"reconciled": True, "historical_pure_health_scope_only": True,
                     "health_receipt_id": receipts[0]["receipt_id"],
                     "health_receipt_hash": receipts[0]["receipt_hash"],
                     "original_reply_completed_at": receipts[0]["historical_health"]["native_reply_completed_at"],
                     "business_goal_closed": False},
                )
        elif previous_state == "blocked_evidence_invalid" and not invalid and sequence_previous == target:
            append_workflow_event(
                root, task_id, target,
                {"reconciled": True, "evidence_revalidated": True, "resume_from": sequence_previous},
            )
        elif previous_state == "closed" and target in {"qa_passed", "waiting_owner_approval", "owner_approved"} and external_execution_required:
            latest_qa_receipt = next(
                (row for row in reversed(receipts)
                 if row.get("receipt_type") == "qa_verdict" and row.get("department") == _final_qa_department(root, snapshot, preparation_only=True)),
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
        elif previous_state == target and target in {"qa_passed", "closed"} and not invalid:
            # A new formal PASS may arrive while the goal is already waiting
            # at qa_passed for other completion obligations. Commit that real
            # receipt once; a state transition is not required to establish
            # the native QA source for downstream knowledge delivery.
            reviewer = _final_qa_department(root, snapshot, preparation_only=True)
            task_events = [row for row in read_jsonl(root / WORKFLOW_EVENTS)
                           if row.get("task_id") == task_id]
            commit = _same_state_formal_qa_commit(receipts, task_events, reviewer, target)
            if commit:
                append_workflow_event(root, task_id, target, commit)
        else:
            latest_qa_receipt = next(
                (row for row in reversed(receipts)
                 if row.get("receipt_type") == "qa_verdict" and row.get("department") == _final_qa_department(root, snapshot, preparation_only=True)),
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
        if derived.get("historical_health_reconciled"):
            snapshot["closed_scope_only"] = True
            snapshot["business_goal_closed"] = False
        if derived.get("owner_direct_execution"):
            snapshot.update(actual_executor="operations", source_adopted=True,
                            historical_responsible_assistant=direct["historical_responsible_assistant"],
                            direct_execution_takeover=direct["pin"],
                            closed_scope_only=derived["closed_scope_only"], business_goal_closed=False,
                            direct_completion=derived["completion"])
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
    "controller_received", "controller_decision", "controller_followthrough", "assistant_conclusion"
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
    context=_VALIDATION_CONTEXT.get()
    raw=validation_bytes(path)
    memo=("result_handoff_chain",str(Path(root).resolve()),task_id,hashlib.sha256(raw).hexdigest())
    if context is not None and memo in context.proofs:
        return deepcopy(context.proofs[memo])
    rows: list[dict[str, Any]] = []
    previous_hash = ""
    def unique(pairs):
        result={}
        for key,value in pairs:
            if key in result: raise WorkflowError("ambiguous result handoff JSON fields")
            result[key]=value
        return result
    for index, line in enumerate(raw.decode("utf-8").splitlines(), start=1):
        try:
            row = json.loads(line,object_pairs_hook=unique)
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
    if context is not None: context.proofs[memo]=deepcopy(rows)
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
    from direct_system_repair import received_original_knowledge
    for identity,entry in results.items():
        recovered=received_original_knowledge(root,{"task_id":task_id,"sender_department":identity[0],
                   "candidate_version":identity[1],"result_sha256":identity[2]})
        if recovered:
            entry.update(controller_received=True,intake_mode="fallback",controller_decision=recovered["decision"],
                         controller_followthrough="named_remaining_actions_registered",
                         actual_intake_event_id=recovered["record_id"],business_goal_closed=False)
    from direct_system_repair import existing_result_resolution
    for identity,entry in results.items():
        resolution=existing_result_resolution(root,{"task_id":task_id,"sender_department":identity[0],
                   "candidate_version":identity[1],"result_sha256":identity[2]})
        if resolution:entry["verified_successor_resolution"]=resolution
    pending = [entry for entry in results.values() if entry["controller_decision"] == "pending"
               and not entry.get("verified_successor_resolution")]
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
            from direct_system_repair import received_original_knowledge
            for identity,entry in by_identity.items():
                recovered=received_original_knowledge(root,{"task_id":task_id,"sender_department":identity[0],
                           "candidate_version":identity[1],"result_sha256":identity[2]})
                if recovered:
                    entry.update(received=True,decided=True,controller_decision=recovered["decision"],
                                 controller_followthrough="named_remaining_actions_registered",
                                 next_actions=recovered["next_actions"],actual_intake_event_id=recovered["record_id"],
                                 business_goal_closed=False,notification_sent=False)
            from direct_system_repair import existing_result_resolution
            for identity,entry in by_identity.items():
                resolution=existing_result_resolution(root,{"task_id":task_id,"sender_department":identity[0],
                           "candidate_version":identity[1],"result_sha256":identity[2]})
                if resolution:entry["verified_successor_resolution"]=resolution
            tracked[task_id] = by_identity
            pending.extend(entry for entry in by_identity.values() if not entry["decided"]
                and not entry.get("verified_successor_resolution") and (
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
        if request.get('result_source_phase')=='delivery_ready':
            from goal_continuity import ready_source
            proof=ready_source(root,request,fixed_id,scheduled=True)
            return {**source,'frozen_delivery_source':proof}
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


def _original_a3_partial_final(root: Path, request: dict[str, Any], native: dict[str, Any],
                               fixed_id: str) -> tuple[dict[str, Any], dict[str, Any]] | None:
    """Read one original A3 final linked to its frozen report and partial V2 outbox."""
    task = "fc-20261010-assistant3-remaining-business-continuation-v2"
    if (request.get("task_id") != task or request.get("sender_department") != "operations-assistant-3"
            or request.get("candidate_version") != "A3-existing-paid16-sales-v3-intake-20261012-v1"):
        return None
    base = ("logs/handoffs/2026-10-10-goal-delivery-assistant-runtime-v1/"
            "operations-assistant3-business-next-v2/assistant3-continuation/"
            "event-followthrough/oct12-existing-results-intake-205014/")
    report = {"path": base + "REPORT.md",
              "sha256": "6735f761b38d0feef176996e05e6f6bd772d9bcf94cf5ba5b3abfb41a069566a",
              "size": 4801}
    outbox_path = base + "A3-final-existing-results-partial-intake-outbox-v1.json"
    outbox_sha = "a598046a728a0d81703fb0e3a2814fc581b06d7b13d1b09c96756a037920a628"
    native_pin = {"path": ("logs/handoffs/2026-10-11-goal-publication-notice-followthrough-repair-v1/"
                           "HQ-continuation-20261012-1057/A3-original-completed-result-actual-native-read.json"),
                  "sha256": "03cffbe293d58923cf27a53966dcd2cc65264a9f5108b34fdde2568bd208a43e",
                  "size": 133626}
    final_pin = {"path": ("logs/handoffs/2026-10-11-goal-publication-notice-followthrough-repair-v1/"
                          "developer/source-candidate-v21/inputs/A3-original-completed-final-exact-UTF8-v21.txt"),
                 "sha256": "e5e343e438bb6f42b74f357aeb29245d15dc70757ec760465c097882809da916",
                 "size": 814}
    actual_outbox = file_digest(root, outbox_path)
    if (actual_outbox["sha256"] != outbox_sha
            or request.get("result_sha256") != outbox_sha
            or request.get("outbox_path") != outbox_path
            or request.get("actual_native_completion") != native_pin
            or request.get("visible_reply") != final_pin
            or file_digest(root, native_pin["path"]) != native_pin
            or file_digest(root, final_pin["path"]) != final_pin
            or file_digest(root, report["path"]) != report):
        raise WorkflowError("original A3 partial final needs exact native, reply, report and outbox pins")
    box = read_json(safe_path(root, outbox_path))
    if (box.get("task_id") != task or box.get("scope") != "project:flashcast:assistant3:remaining-original-goals:v2"
            or box.get("department") != "operations-assistant-3"
            or box.get("candidate_version") != "A3-existing-paid16-sales-v3-intake-20261012-v1"
            or box.get("status") != "partial" or report not in box.get("evidence", [])
            or box.get("notification_sent") is not False):
        raise WorkflowError("original A3 partial result does not bind the frozen report")
    if (not isinstance(native, dict) or native.get("thread", {}).get("id") != fixed_id
            or fixed_id != "example-native-a3c4bc41389e9461"
            or native.get("thread", {}).get("kind") != "codex"
            or native.get("thread", {}).get("hostId") != "local"
            or native.get("thread", {}).get("cwd") != department_registry(root)["operations-assistant-3"]["chat_binding"]["cwd"]
            or native.get("thread", {}).get("title") != "FLASH CAST｜总部助理3｜2026-10"
            or len(native.get("turns", [])) != 1):
        raise WorkflowError("original A3 fixed native thread and one completed turn required")
    turn = native["turns"][0]
    finals = [item for item in turn.get("items", []) if item.get("type") == "agentMessage"
              and item.get("phase") == "final_answer"]
    if (turn.get("id") != "example-native-9e9489261707de0d"
            or turn.get("status") != "completed" or turn.get("error") is not None
            or type(turn.get("completedAt")) not in {int, float}
            or len(finals) != 1
            or finals[0].get("id") != "msg_1bd595aea8b988981ae0e8ef51c223e555266b2d55ebd7177b6bd5296fe112ae"
            or finals[0].get("text", "").encode("utf-8") != safe_path(root, final_pin["path"]).read_bytes()
            or request.get("source_turn_id") != turn["id"]
            or request.get("source_reply_sha256") != final_pin["sha256"]):
        raise WorkflowError("original A3 completed final turn and exact UTF-8 reply required")
    native_cwd = department_registry(root)["operations-assistant-3"]["chat_binding"]["cwd"]
    link = "[报告](" + str(Path(native_cwd) / report["path"]) + ")"
    if finals[0]["text"].count(link) != 1:
        raise WorkflowError("original A3 final must link its one frozen report exactly")
    return {**finals[0], "turnId": turn["id"]}, turn


def _validate_goal_completed_result(root: Path, request: dict[str, Any], fixed_id: str,
                                    *, through_receipt_id: str | None = None) -> dict[str, Any]:
    """Bind a new goal result to its actual completed final, never an ACK."""
    from department_autonomy import autonomous_goal,native_result
    if autonomous_goal(read_json(snapshot_path(root,request['task_id'])).get('goal_delivery')):
        return native_result(root,request,fixed_id)
    if request.get('result_source_phase') == 'delivery_ready':
        from goal_continuity import ready_source
        return ready_source(root, request, fixed_id, through_receipt_id=through_receipt_id)
    if request.get("sender_department") == "operations":
        from native_control_result import completion
        return completion(root, request, fixed_id)
    from goal_delivery_runtime import _collaboration_native, _collaboration_final_message
    completion_pin, reply_pin = request.get("actual_native_completion"), request.get("visible_reply")
    completion = _collaboration_native(root, completion_pin)
    original_a3 = _original_a3_partial_final(root, request, completion, fixed_id)
    exact_native_turn=None
    if isinstance(completion.get('turns'),list):
        turns=[t for t in completion['turns'] if t.get('id')==request.get('source_turn_id')]
        if (completion.get('thread',{}).get('id')!=fixed_id or len(turns)!=1
                or turns[0].get('status')!='completed' or turns[0].get('error')):
            raise WorkflowError('one exact successfully completed source turn required')
        finals=[m for m in turns[0].get('items',[]) if m.get('type')=='agentMessage' and m.get('phase')=='final_answer']
        if len(finals)!=1:raise WorkflowError('one exact native final in the selected source turn required')
        exact_native_turn=turns[0];message={**finals[0],'turnId':turns[0]['id']}
    else:message = original_a3[0] if original_a3 is not None else _collaboration_final_message(completion, fixed_id)
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
    native_turn = exact_native_turn or completion
    document = completion.get("wait", completion)
    if isinstance(document.get("polls"), list):
        native_turn = next(row.get("latestTurn", {}) for row in document["polls"]
                           if row.get("thread", {}).get("id") == fixed_id)
    if original_a3 is not None:
        native_turn = original_a3[1]
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
    ordinary_source_ids = set()
    if original_a3 is None:
        from qa_review_plan import load_plan, ordinary_original_source_receipt_ids
        from goal_delivery_runtime import restore_goal
        snapshot = restore_goal(root, read_json(snapshot_path(root, task)))
        if snapshot.get('goal_delivery') and snapshot.get('qa_review_plan'):
            plan = load_plan(root, snapshot)
            if plan is not None:
                ordinary_source_ids = ordinary_original_source_receipt_ids(root, snapshot, receipts, plan)
                from goal_continuity import _ready_receipt_prefix
                causal_rows = [r for r in receipts if r.get('department') == request['sender_department']
                               and r.get('chat_task_id') == fixed_id and r.get('receipt_type') in
                               {'dispatch_sent','dispatch_failed','chat_ack'}]
                pair, chronology_bad = _ready_receipt_prefix(causal_rows, observed,
                    root=root, snapshot=snapshot, receipts=receipts, plan=plan,
                    source_request=request, source_page=completion)
                if pair is not None:
                    for row in pair:
                        if row not in scoped: scoped.append(row)
                if causal_rows and (pair is None or chronology_bad):
                    raise WorkflowError('completed source requires its real acknowledged responsibility prefix')
                scoped = [r for r in scoped if r.get('receipt_id') not in ordinary_source_ids]
    if original_a3 is not None:
        original_ids = {"dcac7384-e552-4b3d-a0bf-c2cc37435e6d": "dispatch_sent",
                        "e2bab580-acc2-4a69-8d27-47e551b48a09": "chat_ack"}
        original_rows = [row for row in scoped if row.get("receipt_id") in original_ids]
        if (len(original_rows) != 2
                or any(row.get("receipt_type") != original_ids[row["receipt_id"]] for row in original_rows)
                or not all(row.get("action_id") == "A3-original-actual-current-day-result-intake-recovery-20261012"
                           for row in original_rows)):
            raise WorkflowError("original A3 final requires its exact preceding dispatch and ACK")
        starts = [_parse_observed_at(row["created_at"]) for row in original_rows]
    else:
        starts=[]
        for row in scoped:
            if row.get('receipt_type') not in {'dispatch_sent','chat_ack'}:continue
            recorded=_parse_observed_at(row['created_at'])
            proven_late_ack=False
            if row.get('receipt_type')=='chat_ack' and completed_at is not None and recorded>completed_at and exact_native_turn:
                from goal_continuity import _registered_native_pair
                causal = [r for r in receipts if r.get('department') == request['sender_department']
                          and r.get('chat_task_id') == fixed_id and r.get('receipt_type') in
                          {'dispatch_sent','dispatch_failed','chat_ack'}]
                proven_pair = _registered_native_pair(root,request,receipts,causal,completed_at,completion)
                proven_late_ack = bool(proven_pair and proven_pair[1].get('receipt_id') == row.get('receipt_id'))
                items=exact_native_turn.get('items',[]);final_index=next(i for i,m in enumerate(items) if m.get('id')==message.get('id'))
                for pin in row.get('evidence',[]):
                    ack=read_json(safe_path(root,pin['path']))
                    selected=ack.get('message',{})
                    if (file_digest(root,pin['path'])==pin and ack.get('source_thread_id',ack.get('thread',{}).get('id'))==fixed_id
                            and ack.get('task_id')==task and ack.get('department')==request['sender_department']
                            and ack.get('turn',{}).get('id')==exact_native_turn['id']
                            and selected.get('phase')=='commentary' and selected.get('text','').strip()
                            and task in selected['text'] and any(m.get('id')==selected.get('id')
                               and m.get('text')==selected['text'] for m in items[:final_index])):
                        proven_late_ack=True;break
            # Original message order proves the ACK preceded this final; its
            # later ledger timestamp is preserved, never backdated.
            starts.append(completed_at if proven_late_ack else recorded)
    if not starts and original_a3 is None:
        from goal_source_recovery import recovered_producer_source
        recovered=recovered_producer_source(root,read_json(snapshot_path(root,task)),request['sender_department'])
        if recovered:
            for proof in recovered['actual_sources']:
                value=proof.get('source_turn_started_at')
                if type(value) in {int,float}: starts.append(dt.datetime.fromtimestamp(value,dt.timezone.utc))
    if invalid or not starts or completed_at is None or not max(starts) <= completed_at <= observed:
        raise WorkflowError("actual native completedAt must follow exact task dispatch/ACK and precede observation")
    outbox_path = request.get("outbox_path") or request.get("outbox", {}).get("path", "")
    task_mentioned = re.search(r"(?<![A-Za-z0-9_-])" + re.escape(task) + r"(?![A-Za-z0-9_-])", message["text"])
    path_mentioned = bool(outbox_path) and re.search(re.escape(outbox_path) + r"(?![A-Za-z0-9_./-])", message["text"])
    if not (task_mentioned or path_mentioned or original_a3 is not None):
        raise WorkflowError("completed final must explicitly bind this exact task or frozen outbox path")
    result = {"source_turn_id": turn, "source_thread_id": fixed_id,
              "source_reply_sha256": request["source_reply_sha256"], "reply_observed_at": request["reply_observed_at"],
              "actual_native_completion": completion_pin, "visible_reply": reply_pin}
    if original_a3 is not None:
        result["source_message_id"] = message["id"]
    return result


def _validate_scheduled_acceptance(root: Path, request: dict[str, Any]) -> dict[str, Any]:
    """Independent daily-report acceptance; no synthetic dispatch or production permit."""
    task_id, sender = request["task_id"], request["sender_department"]
    source = scheduled_result_source(root, task_id, sender)
    if not source or source.get("legacy_contract"):
        raise WorkflowError("current admitted daily source required for assistant report acceptance")
    from goal_continuity import daily_selected_assistant, shared_capable
    role = daily_selected_assistant(root,{k:request[k] for k in ('task_id','sender_department','candidate_version','result_sha256')},source["responsible_assistant"])
    if role == sender or role == "operations" or request.get("coordinator_role") != role:
        raise WorkflowError("unique independent daily assistant required; no self review or HQ acceptance")
    registry = department_registry(root)
    authority = registry.get(role, {}).get("coordination_authority", {})
    if (authority.get("routine_decisions") is not True or registry.get(role, {}).get("new_dispatch_enabled") is False
            or (source.get("acceptance_capability") not in authority.get("review_capabilities", [])
                and not shared_capable(root,role,{'producer_departments':[sender],'acceptance_capability':source.get('acceptance_capability')}))):
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
        if _VALIDATION_CONTEXT.get() is not None:
            _VALIDATION_CONTEXT.get().recheck()
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


def _record_result_handoff_uncoordinated(root: Path, request: dict[str, Any], *, knowledge_source=None) -> tuple[dict[str, Any], list[Path]]:
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
    snapshot = read_json(snapshot_path(root, task_id))
    if sender == "operations":
        from native_control_result import context, matches
        if matches(snapshot):
            context(root, snapshot)
        else:
            from goal_delivery_runtime import enabled, owner_direct
            if (not enabled(root,snapshot) or not owner_direct(root,snapshot,sender)
                    or snapshot.get('goal_delivery',{}).get('completion_kind')!='internal_delivery'
                    or snapshot['goal_delivery'].get('required_execution_actions')):
                raise WorkflowError('OPS result requires exact owner-direct internal goal or native control task')
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
    if event in {"controller_received", "controller_decision", "controller_followthrough"}:
        from department_rotation import result_binding
        identity = {"task_id": task_id, "sender_department": sender,
                    "candidate_version": candidate, "result_sha256": result_sha}
        fixed_id = str(result_binding(root, identity, outbox_digest).get("task_id") or "")
    from department_rotation import continued_result_source
    continued_source = continued_result_source(root, request, fixed_id)
    continued_original = (continued_source or {}).get("original_rotation_continuation")
    outbox_chat_id = str(outbox.get("fixed_chat_task_id") or outbox.get("chat_task_id") or "")
    if (outbox.get("task_id") != task_id or outbox.get("department") != sender
            or (outbox_chat_id and outbox_chat_id != fixed_id
                and (not continued_original or outbox_chat_id != continued_original["original_thread_id"]))
            or str(outbox.get("status") or "").lower() in {"", "active", "in_progress", "pending"}):
        raise WorkflowError("部门 outbox 的任务、固定聊天或结果状态不匹配")
    if not outbox_chat_id and continued_original is None:
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
        goal_completed_source = continued_source or _validate_goal_completed_result(root, request, fixed_id)
    if event == "notification_queued":
        if continued_original is not None:
            pass  # Actual new READY + frozen original assignment/dispatch/ACK already revalidated.
        elif is_scheduled_queue:
            scheduled_source = _validate_scheduled_result(root, request, outbox, fixed_id)
        elif is_owner_direct_queue:
            direct_rows, invalid = _validate_receipt_chain(root, task_id)
            from goal_source_recovery import recovered_producer_source
            recovered_source=recovered_producer_source(root,snapshot,sender)
            if (invalid or (sender != "operations" and not any(r.get("receipt_type") == "chat_ack" and r.get("department") == sender
                                   and r.get("chat_task_id") == fixed_id and r.get("ack_nonempty") is True for r in direct_rows)
                                   and not (recovered_source and goal_completed_source))
                    or outbox.get("chat_reply", {}).get("nonempty") is not True
                    or outbox.get("chat_reply", {}).get("in_current_fixed_department_chat") is not True
                    or request.get("source_thread_id") != fixed_id
                    or not re.fullmatch(r"[0-9a-f]{64}", str(request.get("source_reply_sha256") or ""))
                    or _parse_observed_at(request.get("reply_observed_at")) is None):
                raise WorkflowError("owner direct result requires actual fixed chat ACK/reply provenance")
        else:
            receipts, invalid = _validate_receipt_chain(root, task_id)
            original_a3_queue = (task_id == "fc-20261010-assistant3-remaining-business-continuation-v2"
                                 and sender == "operations-assistant-3" and goal_completed_source is not None
                                 and outbox_digest["sha256"] ==
                                 "a598046a728a0d81703fb0e3a2814fc581b06d7b13d1b09c96756a037920a628")
            if original_a3_queue:
                latest_dispatch_index = next((index for index, row in enumerate(receipts)
                                              if row.get("receipt_id") ==
                                              "dcac7384-e552-4b3d-a0bf-c2cc37435e6d"
                                              and row.get("receipt_type") == "dispatch_sent"), None)
                current_receipts = [row for row in receipts if row.get("receipt_id") ==
                                    "e2bab580-acc2-4a69-8d27-47e551b48a09"]
            else:
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
    original_a3_conclusion = None
    if event == "assistant_conclusion":
        from result_coordination import is_original_a3_conclusion_identity
        identity = {"task_id": task_id, "sender_department": sender,
                    "candidate_version": candidate, "result_sha256": result_sha}
        if (not is_original_a3_conclusion_identity(identity)
                or outbox.get("status") != "partial"
                or request.get("conclusion_status") != "partial_nonpass"
                or request.get("next_owner") != sender
                or not isinstance(request.get("next_action"), str)
                or not request["next_action"].strip()
                or request.get("qa_status") not in {None, "NOT_VERIFIED"}):
            raise WorkflowError("only the exact original A3 partial result may record its non-PASS producer conclusion")
        matching = [row for row in _result_handoff_rows(root, task_id)
                    if row.get("event") == "notification_queued"
                    and _result_identity(row) == scheduled_identity]
        if len(matching) != 1 or matching[0].get("outbox") != outbox_digest:
            raise WorkflowError("original A3 conclusion requires its one exact queued result")
        original_a3_conclusion = _validate_goal_completed_result(
            root, {**matching[0], "outbox_path": outbox_digest["path"]}, fixed_id)
        report = next((pin for pin in outbox.get("evidence", [])
                       if pin.get("path", "").endswith("/oct12-existing-results-intake-205014/REPORT.md")), None)
        required = [outbox_digest, report, original_a3_conclusion["actual_native_completion"],
                    original_a3_conclusion["visible_reply"]]
        if report is None or any(pin not in evidence for pin in required):
            raise WorkflowError("original A3 conclusion must retain exact outbox, report, native and final pins")
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
    if (task_id == "fc-20260920-google-ads-rm100-budget-plan"
            and event in {"controller_received", "controller_decision", "controller_followthrough"}):
        from result_coordination import result_lane
        lane = result_lane(root, {"task_id": task_id, "sender_department": sender,
                                  "candidate_version": candidate, "result_sha256": result_sha})
        if lane.get("source_mode") == "original_paid16":
            claim = request.get("coordination_claim", {})
            if (request.get("coordinator_role") != "operations-assistant-3"
                    or not request.get("coordinator_owner")
                    or not isinstance(claim, dict) or not claim.get("fence")):
                raise WorkflowError("original Paid result needs its current A3 fenced claim")
            record.update(source_mode="original_paid16", coordinator_role="operations-assistant-3",
                          coordinator_owner=request["coordinator_owner"],
                          coordination_fence=claim["fence"], decision_actor="operations-assistant-3",
                          responsible_assistant="operations-assistant-3",
                          original_coordination_task_id=lane["original_coordination_task_id"],
                          HQ_second_review_required=False)
    if event == "assistant_conclusion":
        claim = request.get("coordination_claim", {})
        if (request.get("coordinator_role") != sender
                or not request.get("coordinator_owner")
                or not isinstance(claim, dict) or not claim.get("fence")):
            raise WorkflowError("original A3 producer conclusion needs its current fenced owner")
        record.update(conclusion_status="partial_nonpass", next_owner=sender,
                      next_action=request["next_action"], qa_status="NOT_VERIFIED",
                      acceptance_proven=False, professional_review_executed=False,
                      external_permission_issued=False, HQ_second_review_required=False,
                      coordinator_role=sender, coordinator_owner=request["coordinator_owner"],
                      coordination_fence=claim["fence"], decision_actor=sender,
                      responsible_assistant=sender,
                      source_turn_id=original_a3_conclusion["source_turn_id"],
                      source_thread_id=original_a3_conclusion["source_thread_id"],
                      source_reply_sha256=original_a3_conclusion["source_reply_sha256"],
                      actual_native_completion=original_a3_conclusion["actual_native_completion"],
                      visible_reply=original_a3_conclusion["visible_reply"])
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
                record.update(scheduled_source.get('frozen_delivery_source',{}))
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
            native_effect = delivered.get("native_effect")
            if not isinstance(native_effect, dict):
                raise WorkflowError("readback_required: current notification needs its original native invocation and recipient effect")
            record.update(target_department=lane["target_department"], result_lane=lane["lane"],
                          policy_decision_id=request["policy_decision_id"], message_sha256=request["message_sha256"],
                          message_ref=request["message_ref"], actual_native_transport=delivered["native_transport"],
                          delivery_identity=delivered.get("delivery_identity"),
                          delivery_owner=delivered.get("delivery_owner"),
                          delivery_fence=delivered.get("delivery_fence"),
                          purpose=delivered.get("purpose"),
                          actual_native_invocation=delivered["native_invocation"],
                          notification_attempt_id=native_effect["attempt_id"],
                          native_effect=native_effect)
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
        if (task_id == "fc-20260920-google-ads-rm100-budget-plan"
                and sender == "paid-growth-data"):
            from result_coordination import original_paid16_source
            original_paid = original_paid16_source(root, {"task_id": task_id,
                "sender_department": sender, "candidate_version": candidate,
                "result_sha256": result_sha})
            if original_paid is not None:
                original_reply = original_paid["original_reply"]
                original_at = _parse_observed_at(original_reply["reply_observed_at"])
                if (reply_sha != original_reply["source_reply_sha256"]
                        or reply_thread != original_reply["source_thread_id"]
                        or observed_at != original_reply["reply_observed_at"]
                        or original_at is None or original_at > dt.datetime.now(dt.timezone.utc)):
                    raise WorkflowError("original Paid16 intake must bind its exact verified native reply and source observation")
                record.update(source_turn_id=original_reply["source_turn_id"],
                              source_message_id=original_reply["source_message_id"],
                              source_phase=original_reply["source_phase"],
                              reply_observation_source=original_reply["reply_observation_source"])
        record.update(intake_mode=intake_mode, source_reply_sha256=reply_sha,
                      source_thread_id=reply_thread, reply_observed_at=observed_at)
        original_goal_queue = next((row for row in _result_handoff_rows(root, task_id)
                                    if row.get("event") == "notification_queued" and _result_identity(row) == scheduled_identity
                                    and row.get("actual_native_completion") and row.get("source_mode") in {"owner_direct", "approved_dispatch"}), None)
        if knowledge_source is not None:
            original = knowledge_source["queued_source"]
            read_intake=knowledge_source.get('transport_binding')=='actual_recipient_native_read'
            if (intake_mode != ('queue' if read_intake else 'notification') or reply_sha != original.get("source_reply_sha256")
                    or reply_thread != original.get("source_thread_id")
                    or _parse_observed_at(observed_at) < _parse_observed_at(original.get("reply_observed_at"))):
                raise WorkflowError("HQ knowledge must retain exact original final reply and actual transport")
            record.update({k: original[k] for k in ("source_turn_id", "source_thread_id", "source_reply_sha256",
                         "actual_native_completion", "visible_reply") if k in original})
            record.update(result_lane="HQ_knowledge", HQ_second_review_required=False,
                          acceptance_proof=knowledge_source.get("dependency_fingerprint"),
                          source_completion_observed_at=original.get("reply_observed_at"))
            if read_intake:
                record.update(actual_recipient_read=knowledge_source['actual_recipient_read'],
                              native_notification_sent=False,native_conclusion_received=True)
        if original_goal_queue:
            source = (knowledge_source["queued_source"] if knowledge_source is not None
                      else _validate_goal_completed_result(root, original_goal_queue, fixed_id))
            if reply_sha != source["source_reply_sha256"]:
                raise WorkflowError("goal intake must retain the original completed final, not a later ACK")
            # Copy provenance, never the queue's event, record ID, receipt time
            # or idempotency key into this distinct intake event.
            record.update({k:source[k] for k in ('source_turn_id','source_thread_id','source_message_id',
                'source_reply_sha256','actual_native_completion','visible_reply','result_source_phase',
                'batch_delivery_frozen','source_turn_completed') if k in source})
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
        if (task_id == "fc-20260920-google-ads-rm100-budget-plan"
                and sender == "paid-growth-data"):
            from result_coordination import original_paid16_source
            if original_paid16_source(root, {"task_id": task_id,
                    "sender_department": sender, "candidate_version": candidate,
                    "result_sha256": result_sha}) is not None and decision not in {
                        "continue", "rework", "wait_external"}:
                raise WorkflowError("original Paid16 bounded intake cannot reuse historical QA PASS to close or accept")
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
        if request.get("remaining_requirement_id"):
            from goal_delivery_runtime import _completion_contract
            declarations=_completion_contract(root,snapshot).get("requirements",[])
            exact=[item for item in declarations if item.get("requirement_id")==request["remaining_requirement_id"]]
            if len(exact)!=1:
                raise WorkflowError("remaining decision must bind one frozen completion requirement")
            record["remaining_requirement_id"]=exact[0]["requirement_id"]
        if decision == "wait_external":
            unlock = str(request.get("unblock_condition") or "")
            if not unlock:
                raise WorkflowError("外部阻断必须写明解除条件")
            record["unblock_condition"] = unlock
        if decision == "close_scope":
            acceptance_scope = str(request.get("acceptance_scope") or "")
            if not acceptance_scope or record["qa_status"] != "pass":
                raise WorkflowError("关闭单项范围须写明范围并有准确 QA PASS")
            if not daily_modern:
                current=qa_rows[-1]
                if goal_enabled(root,snapshot):
                    authorized=snapshot["goal_delivery"]["authorized_scope"]
                    boxes=[_completion_pin(root,pin) for pin in current.get("evidence",[]) if str(pin.get("path","")).endswith(".json")]
                    accepted=[box["goal_acceptance"]["accepted_scope"] for box in boxes
                              if isinstance(box.get("goal_acceptance"),dict) and box.get("qa_verdict")=="pass"]
                    if len(accepted)!=1 or acceptance_scope not in authorized or acceptance_scope not in accepted[0]:
                        raise WorkflowError("close_scope must match the current independently accepted authorized scope")
                elif acceptance_scope != current.get("scope"):
                    raise WorkflowError("close_scope must match the exact current QA scope")
            record["acceptance_scope"] = acceptance_scope
            record["closed_scope_only"]=True
            record["parent_goal_closed"]=False
    elif event == "assistant_conclusion":
        # The exact producer conclusion is already authenticated above. It is
        # neither a controller intake/decision nor an independent QA verdict.
        pass
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
            if decision_row is not None and decision_row.get("remaining_requirement_id"):
                record["decision_record_id"]=decision_row["record_id"]
                record["remaining_requirement_id"]=decision_row["remaining_requirement_id"]
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
        if event in {"controller_received", "controller_decision", "controller_followthrough"}:
            # handoff_guard already authenticated this actual coordinator lease.
            # Preserve responsible_assistant's historical meaning; normalize new actors.
            record["coordinator_role"] = request.get("coordinator_role", "operations")
        record["previous_hash"] = rows[-1]["record_hash"] if rows else ""
        record["record_hash"] = sha256_value({key: value for key, value in record.items() if key != "record_hash"})
        append_jsonl_locked(path, record)
    # Commit authentic SQL/native intake before an unrelated read-only status view.
    return {**record, "result": "recorded"}, [path, snapshot_path(root, task_id)]


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
    from department_autonomy import autonomy_record_applies,record_autonomous_result
    if autonomy_record_applies(root,request):return record_autonomous_result(root,request)
    from goal_continuity import SourceRegistrationPending, defer_result_registration
    try:
        return _record_result_handoff_registered(root,request)
    except SourceRegistrationPending:
        # Preserve the refusal and original request; an event may later resume
        # this same identity. No fabricated queue, send, ACK or intake.
        defer_result_registration(root,request)
        raise


def _record_result_handoff_registered(root: Path, request: dict[str, Any]) -> tuple[dict[str, Any], list[Path]]:
    """Native final handoff entry, coordinated without changing historical ledgers."""
    from result_coordination import handoff_guard, notification_enqueue, coordination_lock, FINAL_EVENTS
    notification_lock = coordination_lock(root) if request.get("event") not in FINAL_EVENTS else nullcontext()
    with request_validation_context(), notification_lock, handoff_guard(root, request) as admission:
        if admission.replay_record is not None:
            if request.get("event") == "notification_queued":
                notification_enqueue(root, request, _coordination_locked=True)
            return {**admission.replay_record, "result": "duplicate_ignored"}, [result_handoff_path(root, request["task_id"])]
        record, artifacts = _record_result_handoff_uncoordinated(
            root, request, knowledge_source=getattr(admission, "knowledge_source", None))
        if request.get("event") == "notification_queued":
            notification_enqueue(root, request, _coordination_locked=True)
        admission.complete(record)
    try:
        record['controller_handoff'] = result_handoff_status(root, request['task_id'])
    except (WorkflowError, OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        # Do not erase a committed effect or silently discard its diagnostic.
        record['postcommit_read_status'] = {'state': 'blocked', 'reason': str(error),
            'next_owner': 'system-development', 'effect_committed': True,
            'effect_replay_allowed': False, 'business_completion_claimed': False}
    if request.get('event') == 'notification_queued' and request.get('assistant_selection_live'):
        from goal_continuity import select_result
        selection=select_result(root,{**request,'actor':request['sender_department'],
                     'request_id':request['idempotency_key']+'-select',
                     'live_identity':request['assistant_selection_live']})
        record={**record,'resource_selection':selection}
    return record, artifacts


def _congestion_accepted_source_manifest(root, snapshot, accepted):
    """Follow the accepted outbox's immutable manifest; keep its source identity."""
    task = 'fc-20261022-department-flow-congestion-optimization-v1'
    scope = 'project:flashcast:department-flow-congestion-optimization:20261022:v1'
    contract = snapshot.get('goal_contract', {})
    goal = snapshot.get('goal_delivery', {})
    if (snapshot.get('task_id') != task or contract.get('sha256') !=
            'a4724b2d4ed1167100fdcde502aca4f3dbfec4cc25177285c2d3a78e293e5943'
            or goal.get('authorized_scope') != [scope] or goal.get('primary_owner') != 'system-development'
            or goal.get('responsible_assistant') != 'operations-assistant-2'
            or goal.get('producer_departments') != ['system-development']
            or goal.get('required_execution_actions') or accepted.get('state') != 'PROVEN'
            or accepted.get('scope') != scope or accepted.get('candidate') != accepted.get('producer_outbox')
            or accepted.get('identity', {}).get('task_id') != task
            or accepted.get('identity', {}).get('sender_department') != 'system-development'):
        raise WorkflowError('original accepted congestion goal/source/sole A2 required')
    _completion_pin(root, contract)
    box = _completion_pin(root, accepted['producer_outbox'])
    if (box.get('task_id') != task or box.get('department') != 'system-development'
            or box.get('scope') != scope or box.get('candidate_version') != accepted['identity']['candidate_version']
            or accepted['producer_outbox']['sha256'] != accepted['identity']['result_sha256']
            or box.get('source_fingerprint') != accepted.get('source_fingerprint')):
        raise WorkflowError('exact independently accepted outbox source differs')
    pin = box.get('candidate_manifest')
    manifest = _completion_pin(root, pin)
    if (manifest.get('task_id') != task or manifest.get('scope') != scope
            or manifest.get('department') != 'system-development'
            or manifest.get('candidate_version') != box['candidate_version']
            or manifest.get('candidate_fingerprint') != accepted['source_fingerprint']
            or not manifest.get('changes') or manifest.get('field_changes') != []):
        raise WorkflowError('exact accepted outbox to immutable source manifest required')
    return pin

def _congestion_original_queue_pilot(root, snapshot, receipts, requirement, accepted, journal):
    """The original goal's real queue/intake/adoption trial needs no new child."""
    _congestion_accepted_source_manifest(root, snapshot, accepted)
    import result_coordination as c
    import department_event_dispatcher as d
    task = snapshot['task_id']; role = 'operations-assistant-2'
    if (journal.get('schema') != 'actual-original-result-to-intake-next-action-and-adoption-pilot/v1'
            or journal.get('task_id') != task or journal.get('pilot_task_id') != task
            or journal.get('identity') != accepted['identity']
            or requirement.get('scope') != accepted.get('scope')):
        raise WorkflowError('actual original same-goal pilot identity and scope required')
    # A real completed adoption proof is independently registered first. Read it
    # through the normal typed consumer, including native final and current CAS.
    requirements = [v for v in snapshot['goal_delivery']['completion_requirements']
                    if v.get('requirement_type') == 'source_adoption']
    if len(requirements) != 1:
        raise WorkflowError('one original source-adoption completion requirement required')
    adopted = goal_typed_completion_proof(root, snapshot, receipts, requirements[0], accepted)
    adoption_pin = journal.get('actual_adoption_journal')
    if adopted.get('state') != 'PROVEN' or adoption_pin not in adopted.get('evidence', []):
        raise WorkflowError('normal current completed source-adoption proof required before queue pilot')
    adoption = _completion_pin(root, adoption_pin)
    source_rows, bad = _validate_receipt_chain(root, task)
    if bad or source_rows != receipts:
        raise WorkflowError('actual same-goal receipt chain required')
    for id_key, kind, department in [('producer_receipt_id', 'outbox_received', 'system-development'),
                                    ('bounded_acceptance_receipt_id', 'outbox_received', role)]:
        found = [v for v in receipts if v.get('receipt_id') == journal.get(id_key)
                 and v.get('receipt_type') == kind and v.get('department') == department]
        expected = accepted['producer_outbox'] if department == 'system-development' else accepted.get('acceptance_outbox')
        if len(found) != 1 or expected not in found[0].get('evidence', []):
            raise WorkflowError('pilot must use exact actual producer and sole A2 acceptance receipts')
        if department == role and found[0] != accepted.get('acceptance_receipt'):
            raise WorkflowError('pilot independent acceptance is not current')
    record, intake = d._accepted_queue(root, accepted['identity'])
    transport = d._original_queue_acceptance(root, accepted['identity'], record)
    if (not intake or intake.get('record_id') != journal.get('received_record_id')
            or journal.get('original_queue_event') != d.key(accepted['identity'])
            or transport.get('native_message_id') != journal.get('original_native_message_id')):
        raise WorkflowError('real original official queue and committed intake differ')
    rows = _result_handoff_rows(root, task)
    decisions = [v for v in rows if v.get('event') == 'controller_decision'
                 and c.exact_identity(v) == accepted['identity']]
    selected = [v for v in decisions if v.get('record_id') == journal.get('decision_record_id')]
    if (len(selected) != 1 or selected[0].get('coordinator_role') != role
            or selected[0].get('next_owner') != role or not selected[0].get('next_action')
            or selected[0].get('decision') != 'continue'):
        raise WorkflowError('one exact actual sole A2 next-adoption decision required')
    decision = selected[0]; c._committed_result(root, decision)
    start = _parse_observed_at(adoption.get('started_at'))
    for later in decisions[decisions.index(decision) + 1:]:
        at = _parse_observed_at(later.get('created_at'))
        if start is None or at is None:
            raise WorkflowError('actual pilot decision chronology required')
        if at <= start and later.get('decision') in {'rework', 'wait_external'} and not later.get('remaining_requirement_id'):
            c._committed_result(root, later)
            raise WorkflowError('original next-adoption decision was superseded before execution')
    times = [_parse_observed_at(v) for v in (intake.get('created_at'), decision.get('created_at'),
             accepted['acceptance_receipt'].get('created_at'), adoption.get('started_at'), adoption.get('completed_at'))]
    if any(v is None for v in times) or times != sorted(times):
        raise WorkflowError('original queue/intake/decision/acceptance/adoption order differs')
    return adopted['evidence']


def _ordered_source_observations(values):
    """Order evidence at its encoded precision; never rewrite or backdate it."""
    cursor = None
    for value in values:
        if type(value) in {int, float}:
            import math
            if not math.isfinite(value) or value < 0:return False
            at = dt.datetime.fromtimestamp(value, dt.timezone.utc)
            upper = at
        else:
            at = _parse_observed_at(value)
            if at is None:return False
            # Native project writers encode whole seconds. That field denotes
            # its one-second interval, not a manufactured fractional instant.
            coarse = isinstance(value, str) and re.fullmatch(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:Z|[+-]\d\d:\d\d)', value) is not None
            upper = at + dt.timedelta(seconds=1) if coarse else at
        if at > dt.datetime.now(dt.timezone.utc):return False
        cursor = at if cursor is None else max(cursor, at)
        if cursor > upper or upper != at and cursor == upper:return False
    return True


def _source_continuation_execution_output(command):
    """Decode supported complete native output without changing its evidence."""
    if 'aggregatedOutput' not in command:
        return _completion_execution_output(command)
    legacy = command['aggregatedOutput']
    if not isinstance(legacy, str):
        raise WorkflowError('complete original source command output required')
    raw = _completion_execution_output({**command, 'output': legacy})
    if 'output' in command and _completion_execution_output(command) != raw:
        raise WorkflowError('original source command output representations disagree')
    return raw


def _internal_source_continuation_readback(root, path, prior_sha256, mode):
    """Explain later internal CAS bytes using normal, independent actual effects.

    The old operation and PASS are never edited. Only an original-A2 received
    partial source report, real native independent review and completed CAS
    final can add an edge. No receipt/transport/permission is created here.
    """
    task = 'fc-20261022-department-flow-congestion-optimization-v1'
    try:
        import goal_delivery_runtime as g
        import qa_review_plan as q
        snapshot = g.restore_goal(root, read_json(snapshot_path(root, task)))
        goal = snapshot['goal_delivery']; role = goal['responsible_assistant']
        if (goal['primary_owner'] != 'system-development' or role != 'operations-assistant-2'
                or goal['producer_departments'] != ['system-development'] or not path.startswith('tools/')
                or file_digest(root, snapshot['goal_contract']['path']) != snapshot['goal_contract']
                or file_digest(root, goal['authorization_pin']['path']) != goal['authorization_pin']):
            return None
        # Raw committed receipt chain, not recursive QA/source proof selection.
        rows = read_jsonl(receipts_path(root, task)); previous = ''; seen = set()
        for row in rows:
            if (row.get('task_id') != task or not row.get('receipt_id') or row['receipt_id'] in seen
                    or row.get('previous_hash') != previous
                    or row.get('receipt_hash') != sha256_value(_receipt_payload_for_hash(row))):
                return None
            previous = row['receipt_hash']; seen.add(row['receipt_id'])
        if validate_workflow_events(root, task):return None
        edges = {}
        flags = ('production_write_allowed', 'production_release_eligible', 'external_permission_issued',
                 'goal_completion_claimed', 'final_goal_verdict', 'pilot_complete')
        for receipt in rows:
            if receipt.get('department') != role or receipt.get('receipt_type') != 'outbox_received':continue
            for pin in receipt.get('evidence', []):
                if not pin.get('path', '').endswith('.json'):continue
                report = _completion_pin(root, pin)
                if report.get('schema') != 'independently-adopted-internal-source-continuation/v1':continue
                effect = report.get('actual_source_continuation', {})
                mp, jp, rp = [effect[k] for k in ('candidate_manifest', 'journal', 'independent_review_report')]
                mf, journal, review = [_completion_pin(root, p) for p in (mp, jp, rp)]
                if not any(c.get('path') == path for c in mf.get('changes', [])):continue
                plan = _completion_pin(root, mf['normal_plan'])
                q._review_manifest_source_pins(root, snapshot, plan, mp,
                    candidate_version=mf['candidate_version'], fingerprint=mf['candidate_fingerprint'])
                intakes = [r for r in _result_handoff_rows(root, task)
                           if r.get('record_id') == report.get('source_packet_intake_id') and r.get('event') == 'controller_received']
                if len(intakes) != 1 or intakes[0].get('sender_department') != 'system-development' or intakes[0].get('coordinator_role') != role:return None
                packet = _completion_pin(root, intakes[0]['outbox'])
                if (packet.get('candidate_manifest') != mp or packet.get('candidate_version') != mf['candidate_version']
                        or packet.get('source_fingerprint') != mf['candidate_fingerprint']
                        or packet.get('not_a_new_whole_goal_producer') is not True
                        or packet.get('task_id') != task or packet.get('department') != 'system-development'
                        or packet.get('fixture_only') is not False):return None
                from result_coordination import _committed_result
                _committed_result(root, intakes[0])
                expected = {'task_id': task, 'department': role, 'sender_department': role,
                            'candidate_version': mf['candidate_version'], 'scope': mf['scope']}
                if (any(report.get(k) != v or review.get(k) != v for k, v in expected.items())
                        or mf.get('scope') not in goal['authorized_scope'] or mf.get('field_changes') != []
                        or any(report.get(k) is not False or review.get(k) is not False for k in flags)
                        or report.get('fixture_only') is not False or report.get('qa_verdict') == 'pass'
                        or report.get('goal_acceptance') or review.get('goal_acceptance')
                        or review.get('candidate_review') != {'actor': role, 'phase': 'candidate_source_only',
                            'direction': 'forward', 'verdict': 'PASS_SOURCE_CANDIDATE_ONLY',
                            'candidate_manifest': mp, 'candidate_fingerprint': mf['candidate_fingerprint'],
                            'review_plan': mf['normal_plan'], 'producer_outbox': mf['primary_producer_outbox'],
                            'goal_contract': snapshot['goal_contract'], 'human_authorization': goal['authorization_pin']}):return None
                q._review_exact_native_reply(root, review, role,
                    [task, mp['sha256'], mf['candidate_fingerprint'], 'PASS_SOURCE_CANDIDATE_ONLY'])
                q._review_exact_native_reply(root, report, role, [task, mp['sha256'], jp['sha256']])
                if (journal.get('schema') != 'exact-internal-source-bootstrap/v1' or journal.get('task_id') != task
                        or journal.get('state') != 'adopted' or journal.get('actor') != role or journal.get('executor') != role
                        or journal.get('candidate_manifest') != mp or journal.get('independent_review_report') != rp
                        or journal.get('authorized_source') != goal['authorization_pin']
                        or journal.get('field_operations') != [] or journal.get('fixture_only') is not False
                        or type(journal.get('external_writes')) is not int or journal['external_writes'] != 0
                        or journal.get('permissions_issued') is not False
                        or (safe_path(root, jp['path']).parent / 'rollback-journal.json').exists()):return None
                from goal_delivery_runtime import _collaboration_native
                native = _collaboration_native(root, report['actual_native_reply'])
                turns = [t for t in native.get('turns', []) if t.get('id') == report['source_turn_id']]
                if len(turns) != 1 or turns[0].get('status') != 'completed' or turns[0].get('error'):return None
                items = turns[0].get('items', [])
                commands = [(i, c) for i, c in enumerate(items) if c.get('id') == effect.get('execution_command_id')]
                finals = [(i, m) for i, m in enumerate(items) if m.get('id') == report['source_message_id']]
                if len(commands) != 1 or len(finals) != 1:return None
                ci, command = commands[0]; fi, final = finals[0]
                if (ci >= fi or final.get('phase') != 'final_answer' or command.get('type') != 'commandExecution'
                        or command.get('status') != 'completed' or type(command.get('exitCode')) is not int or command['exitCode'] != 0
                        or command.get('cwd') != str(Path(root).resolve())
                        or str(safe_path(root, mf['adoption_helper']['path'])) not in command.get('command', '')
                        or ' apply ' not in command.get('command', '') or '--review-input' not in command.get('command', '')
                        or any(v.encode('ascii') not in _source_continuation_execution_output(command) for v in (mp['sha256'], jp['sha256']))):return None
                times = [_parse_observed_at(v) for v in (review.get('created_at'), journal.get('started_at'),
                         journal.get('completed_at'), report.get('reply_observed_at'), report.get('created_at'), receipt.get('created_at'))]
                if (not all(times) or not _ordered_source_observations([
                        intakes[0].get('created_at'), review.get('reply_observed_at'), review.get('created_at'),
                        journal.get('started_at'), journal.get('completed_at'), turns[0].get('completedAt'),
                        report.get('reply_observed_at'), report.get('created_at'), receipt.get('created_at')])
                        or type(turns[0].get('completedAt')) not in {int, float}
                        ):return None
                ops, changes = journal.get('source_operations', []), mf['changes']
                if len(ops) != len(changes) or len({op.get('path') for op in ops}) != len(changes):return None
                for change in changes:
                    found = [op for op in ops if op.get('path') == change['path']]
                    if len(found) != 1:return None
                    op = found[0]
                    if (op.get('applied') is not True or op.get('before_sha256') != change['expected_source']['sha256']
                            or op.get('after_sha256') != change['candidate']['sha256'] or op.get('mode') != change['expected_source']['mode']
                            or file_digest(root, op['backup']['path']) != op['backup']
                            or op['backup']['sha256'] != op['before_sha256']):return None
                    if op['path'] == path and op['mode'] == mode:
                        edge = {'after': op['after_sha256'], 'started': times[1], 'completed': times[2],
                                'evidence': [pin, mp, jp, rp, report['actual_native_reply'], review['actual_native_reply']]}
                        edges.setdefault(op['before_sha256'], {})[jp['sha256']] = edge
        current = file_digest(root, path)['sha256']; at = None; evidence = []; visited = set(); cursor = prior_sha256
        while cursor != current:
            if cursor in visited or len(visited) >= 8:return None
            visited.add(cursor); found = list(edges.get(cursor, {}).values())
            if len(found) != 1 or at is not None and found[0]['started'] < at:return None
            edge = found[0]; cursor = edge['after']; at = edge['completed']; evidence.extend(edge['evidence'])
        if not evidence or safe_path(root, path).stat().st_mode & 0o777 != mode:return None
        return {'current_sha256': current, 'evidence': list({p['path']: p for p in evidence}.values())}
    except (WorkflowError, OSError, ValueError, TypeError, KeyError, AttributeError):
        return None


def _congestion_lifecycle_preserved_fe689_source(root, path, prior_sha256, mode):
    """Read a separately accepted/adopted C10 source, never extend F authority.

    The old A1 journal keeps its original after SHA. Only the actual original
    A2 current-source adoption proof can explain this one later shared file.
    Missing final, rollback, another version, actor or scope stays blocked.
    """
    prior = 'a071b277d13b421abff229d1a6652367994d7b79b05102d085bb0c5038fb1a94'
    task = 'fc-20261022-department-flow-congestion-optimization-v1'
    scope = 'project:flashcast:department-flow-congestion-optimization:20261022:v1'
    version = 'department-flow-current-fe689-lifecycle-compatible-v10-20261024'
    if path != 'tools/workflow_control.py' or prior_sha256 != prior or mode != 0o644:
        return None
    try:
        import goal_delivery_runtime as g
        import qa_review_plan as q
        mf_pin = file_digest(root,'logs/handoffs/2026-10-22-department-flow-congestion-optimization-v1/system-development-v1/lifecycle-current-fe689-baseline-v10/CANDIDATE-CONGESTION-v10.json')
        mf = _completion_pin(root,mf_pin)
        snapshot = g.restore_goal(root,read_json(snapshot_path(root,task)))
        goal = snapshot.get('goal_delivery',{})
        if (snapshot.get('goal_contract',{}).get('sha256') != 'a4724b2d4ed1167100fdcde502aca4f3dbfec4cc25177285c2d3a78e293e5943'
                or goal.get('authorization_pin',{}).get('sha256') != '8443335e7d4adc76dce710225c0ebca9fba8e09b92fc43c1801469299263cc7d'
                or goal.get('primary_owner') != 'system-development' or goal.get('producer_departments') != ['system-development']
                or goal.get('responsible_assistant') != 'operations-assistant-2' or goal.get('authorized_scope') != [scope]
                or goal.get('required_execution_actions') or mf.get('candidate_version') != version
                or mf.get('field_changes') != []):return None
        rows,bad = _validate_receipt_chain(root,task)
        if bad or validate_workflow_events(root,task):return None
        accepted = goal_completion_subject(root,snapshot,rows,{'mode':'latest_exact_accepted_result','producer_department':'system-development'})
        if (accepted.get('state') != 'PROVEN' or accepted.get('scope') != scope
                or accepted.get('identity',{}).get('task_id') != task
                or accepted['identity'].get('candidate_version') != version
                or accepted['identity'].get('sender_department') != 'system-development'
                or accepted.get('source_fingerprint') != mf.get('candidate_fingerprint')
                or accepted.get('candidate') != accepted.get('producer_outbox')):return None
        box = _completion_pin(root,accepted['producer_outbox'])
        if (box.get('candidate_manifest') != mf_pin or box.get('source_fingerprint') != accepted['source_fingerprint']
                or box.get('candidate_version') != version):return None
        plan = q.load_plan(root,snapshot)
        q._review_manifest_source_pins(root,snapshot,plan,mf_pin,candidate_version=version,fingerprint=accepted['source_fingerprint'])
        changes = [v for v in mf['changes'] if v.get('path') == path]
        if len(changes) != 1:return None
        change = changes[0]
        successor = None
        if file_digest(root,path)['sha256'] != change['candidate']['sha256']:
            successor = _internal_source_continuation_readback(root,path,change['candidate']['sha256'],mode)
        if (change.get('expected_source',{}).get('sha256') != prior
                or int(change.get('mode','0'),8) != mode
                or (file_digest(root,path)['sha256'] != change['candidate']['sha256'] and successor is None)
                or safe_path(root,path).stat().st_mode & 0o777 != mode):return None
        requirements = [v for v in goal['completion_requirements'] if v.get('requirement_type') == 'source_adoption']
        if len(requirements) != 1:return None
        # This requires the real independent C10 execution AND completed native
        # final. It cannot turn a local PASS or prepared journal into adoption.
        actual = goal_typed_completion_proof(root,snapshot,rows,requirements[0],accepted)
        if actual.get('state') != 'PROVEN':return None
        jp = file_digest(root,'backups/'+task+'/A2-exact-current-fe689-lifecycle-v10/journal.json')
        journal = _completion_pin(root,jp)
        if (jp not in actual.get('evidence',[]) or journal.get('state') != 'adopted'
                or journal.get('task_id') != task or journal.get('actor') != journal.get('executor')
                or journal.get('actor') != 'operations-assistant-2' or journal.get('candidate_manifest') != mf_pin
                or journal.get('authorized_source') != goal['authorization_pin']
                or type(journal.get('external_writes')) is not int or journal['external_writes'] != 0
                or journal.get('permissions_issued') is not False or journal.get('field_operations') != []
                or (safe_path(root,jp['path']).parent/'rollback-journal.json').exists()):return None
        ops = [v for v in journal['source_operations'] if v.get('path') == path]
        if (len(ops) != 1 or ops[0].get('applied') is not True or ops[0].get('before_sha256') != prior
                or ops[0].get('after_sha256') != change['candidate']['sha256'] or ops[0].get('mode') != mode
                or file_digest(root,ops[0]['backup']['path']) != ops[0]['backup']
                or ops[0]['backup']['sha256'] != prior):return None
        old = _completion_pin(root,{'path':'backups/fc-20261023-chatgpt-fe689-runtime-adoption-stage-v1/A1-exact-remaining-source-consumer-v9/journal.json',
                  'sha256':'52216dc1b76042ce7a2d61d1f2e43a229e7d2448b07f0ba73259476e6120d74c','size':2218})
        times = [_parse_observed_at(v) for v in (old.get('completed_at'),journal.get('started_at'),journal.get('completed_at'))]
        if any(t is None for t in times) or times != sorted(times):return None
        return {'current_sha256':successor['current_sha256'] if successor else change['candidate']['sha256'],
                'evidence':[mf_pin,*actual['evidence'],*(successor['evidence'] if successor else [])]}
    except (WorkflowError,OSError,ValueError,TypeError,KeyError,AttributeError):return None
