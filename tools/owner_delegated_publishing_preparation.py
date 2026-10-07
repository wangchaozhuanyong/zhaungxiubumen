"""One owner-authorized assistant -> publishing preparation message only.

The pins and native observations are auditable local evidence, not signatures.
This module does not authorize CMS writes, production QA, or publication.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path
from typing import Any, Callable

TASK_ID = "fc-20261007-owner-publisher-execution-takeover-v1"
BUSINESS_TASK_ID = "fc-20260928-keyword-page-answer-implementation-v1"
SCOPE = "owner_delegated_dispatch:" + TASK_ID
ACTION_ID = "send-owner-authorized-publisher-preparation-v1"
PROJECT_ID = "<LOCAL_PROJECT_ID>"
PROJECT_ROOT = "<PROJECT_ROOT>"
SOURCE_ID = "<LOCAL_TASK_ID>"
SOURCE_TITLE = "FLASH CAST｜总部助理｜2026-10"
TARGET_ID = "<LOCAL_TASK_ID>"
TARGET_TITLE = "FLASH CAST｜后台发布部｜2026-10"
SECTION_NAME = "装修公司部门"
PUBLIC_TEMPLATE_ONLY = True
AUTH_TURN_ID = 'example-turn-not-native'
AUTH_MESSAGE_ID = 'example-message-not-native'
AUTH_TEXT = 'Synthetic example only; not a native authorization.\n'
AUTH_TEXT_SHA256 = 'e6ad84a08c6efca5802c9cb62c400a034556ba457b65e982cefe2612e434cb16'
RECEIPT_MARKER = "owner_authorization:publisher_preparation_only"
REQUIRED = ["routing_precheck:owner_delegated_publisher_preparation", RECEIPT_MARKER]


class PreparationDenied(ValueError):
    pass


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise PreparationDenied(reason)


def _path(root: Path, value: Any) -> Path:
    _require(isinstance(value, str) and bool(value.strip()), "path_required")
    path = (root / value).resolve()
    _require(path != root.resolve() and root.resolve() in path.parents, "path_outside_project")
    return path


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    _require(isinstance(value, dict), "json_object_required")
    return value


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _time(value: Any) -> dt.datetime:
    _require(isinstance(value, str), "timestamp_required")
    result = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    _require(result.tzinfo is not None, "timezone_required")
    return result.astimezone(dt.timezone.utc)


def _fresh(value: Any, seconds: int, now: dt.datetime) -> bool:
    return 0 <= (now - _time(value)).total_seconds() <= seconds


def _frozen_request(root: Path, policy: dict[str, Any]) -> dict[str, Any]:
    _require(not PUBLIC_TEMPLATE_ONLY, "public_template_has_no_native_authorization")
    routing = policy.get("routing_policy", {})
    _require(isinstance(routing, dict), "routing_policy_missing")
    control = routing.get("owner_delegated_publishing_preparation", {})
    _require(isinstance(control, dict) and control.get("status") == "approved_single_use",
             "exact_request_not_enabled")
    _require(str(root.resolve()) == PROJECT_ROOT
             and routing.get("source_project_root") == PROJECT_ROOT
             and routing.get("source_project_id") == PROJECT_ID, "project_identity_mismatch")
    path = _path(root, control.get("request_path"))
    _require(_sha(path) == control.get("request_sha256"), "request_pin_mismatch")
    request = _read(path)
    exact = {"task_id": TASK_ID, "action_id": ACTION_ID, "scope": SCOPE,
             "action_class": "thread_message", "sender_department": "operations-assistant",
             "source_project_id": PROJECT_ID, "target_project_id": PROJECT_ID,
             "target_department": "publishing", "target_thread_id": TARGET_ID,
             "target_thread_title": TARGET_TITLE, "target_cwd": PROJECT_ROOT,
             "original_business_task_id": BUSINESS_TASK_ID,
             "preparation_only": True, "production_authority_granted": False}
    _require(all(request.get(k) == v for k, v in exact.items()), "request_exact_scope_mismatch")
    _require(request.get("preparation_only") is True
             and request.get("production_authority_granted") is False, "preparation_boolean_scope_required")
    for key in ("cms_write_allowed", "site_publish_allowed", "production_write_allowed",
                "qa_verdict_allowed", "production_decision_allowed", "production_gates_waived"):
        _require(request.get(key, False) is False, "production_authority_not_allowed")
    auth_path = _path(root, request.get("owner_authorization_path"))
    _require(_sha(auth_path) == request.get("owner_authorization_sha256"), "authorization_pin_mismatch")
    auth = _read(auth_path)
    expected_auth = {"type": "NATIVE_OWNER_AUTHORIZATION",
                     "source_method": "mcp__codex_app__read_thread", "source_thread_id": SOURCE_ID,
                     "source_project_id": PROJECT_ID, "source_cwd": PROJECT_ROOT,
                     "turn_id": AUTH_TURN_ID, "message_id": AUTH_MESSAGE_ID,
                     "authorized_sender": "operations-assistant", "production_gates_waived": False}
    _require(all(auth.get(k) == v for k, v in expected_auth.items()), "native_owner_authorization_mismatch")
    _require(auth.get("production_gates_waived") is False, "native_owner_authorization_mismatch")
    message = auth.get("user_message", {})
    _require(isinstance(message, dict) and message.get("type") == "userMessage"
             and message.get("id") == AUTH_MESSAGE_ID
             and message.get("content") == [{"type": "text", "text": AUTH_TEXT}]
             and hashlib.sha256(AUTH_TEXT.encode("utf-8")).hexdigest() == AUTH_TEXT_SHA256,
             "native_owner_authorization_content_mismatch")
    packet_path = _path(root, request.get("packet_path"))
    _require(_sha(packet_path) == request.get("packet_sha256"), "packet_pin_mismatch")
    payload_path = _path(root, request.get("payload_path"))
    _require(payload_path.stat().st_size > 0 and _sha(payload_path) == request.get("payload_sha256"),
             "payload_pin_mismatch")
    return request


def check_owner_delegated_preparation(
    root: Path, *, policy: dict[str, Any], departments: dict[str, dict[str, Any]],
    requested: dict[str, Any], validate_receipt_chain: Callable[..., Any],
) -> tuple[list[str], list[str]]:
    """Called only for the exact scope; failures never fall back to a broad route."""
    try:
        request = _frozen_request(root, policy)
        _require(all(request.get(k) == v for k, v in requested.items()), "requested_binding_mismatch")
        now = dt.datetime.now(dt.timezone.utc)
        for department, thread_id, title in (
            ("operations-assistant", SOURCE_ID, SOURCE_TITLE), ("publishing", TARGET_ID, TARGET_TITLE)
        ):
            item = departments.get(department, {})
            binding = item.get("chat_binding", {})
            _require(isinstance(binding, dict), "registered_binding_missing")
            identity = {"task_id": thread_id, "title": title, "project_id": PROJECT_ID,
                        "cwd": PROJECT_ROOT, "status": "bound_and_visible", "dispatch_eligible": True}
            _require(all(binding.get(k) == v for k, v in identity.items()), "registered_binding_mismatch")
            _require(binding.get("dispatch_eligible") is True, "registered_binding_mismatch")
            _require(binding.get("reply_health") == "healthy_visible_reply_verified"
                     and _fresh(binding.get("last_health_check_at") or binding.get("last_verified_at"),
                                26 * 3600, now), "registered_health_stale_or_unhealthy")
            _require(binding.get("sidebar_section_id") == request.get("target_sidebar_section_id"),
                     "registered_section_mismatch")
        live = _read(_path(root, request.get("live_identity_path")))
        _require(live.get("source_method") == "mcp__codex_app__list_threads"
                 and _fresh(live.get("observed_at"), 300, now), "live_identity_stale_or_non_native")
        threads = live.get("threads", [])
        sections = live.get("sections", [])
        _require(isinstance(threads, list) and isinstance(sections, list), "live_identity_shape_invalid")
        for thread_id, title in ((SOURCE_ID, SOURCE_TITLE), (TARGET_ID, TARGET_TITLE)):
            matches = [x for x in threads if isinstance(x, dict) and x.get("id") == thread_id]
            _require(len(matches) == 1, "live_thread_missing_or_ambiguous")
            expected = {"id": thread_id, "title": title, "projectId": PROJECT_ID,
                        "cwd": PROJECT_ROOT, "hostId": "local"}
            _require(all(matches[0].get(k) == v for k, v in expected.items()), "live_thread_identity_mismatch")
            if thread_id == TARGET_ID:
                _require(matches[0].get("status") == "idle", "publishing_target_not_idle")
            else:
                _require(matches[0].get("status") == "active", "assistant_source_not_active")
        matching_sections = [x for x in sections if isinstance(x, dict)
                             and x.get("name") == SECTION_NAME]
        _require(len(matching_sections) == 1, "live_section_missing_or_ambiguous")
        section = matching_sections[0]
        _require(section.get("sectionId") == request.get("target_sidebar_section_id")
                 and "codex:thread:local:" + SOURCE_ID in section.get("itemKeys", [])
                 and "codex:thread:local:" + TARGET_ID in section.get("itemKeys", []), "live_section_membership_mismatch")
        snapshot = _read(root / "data/workflows" / (TASK_ID + ".json"))
        _require(snapshot.get("task_id") == TASK_ID and snapshot.get("plan_status") == "ready_to_send"
                 and snapshot.get("current_state") not in {"closed", "failed", "cancelled"},
                 "workflow_not_ready_or_terminal")
        planned = [x for x in snapshot.get("departments", [])
                   if isinstance(x, dict) and x.get("department") == "publishing"]
        _require(len(planned) == 1 and planned[0].get("chat_task_id") == TARGET_ID,
                 "publishing_not_exact_workflow_participant")
        original = _read(root / "data/workflows" / (BUSINESS_TASK_ID + ".json"))
        _require(original.get("task_id") == BUSINESS_TASK_ID, "original_business_task_missing")
        chain, invalid = validate_receipt_chain(root, TASK_ID)
        _require(not invalid, "receipt_chain_invalid")
        _require(not any(x.get("receipt_type") == "dispatch_sent" and x.get("department") == "publishing"
                         for x in chain), "publisher_preparation_already_dispatched")
        for key in ("native_attempt_receipt_path", "native_send_receipt_path"):
            _require(not _path(root, request.get(key)).exists(), "publisher_preparation_send_already_attempted")
        _require(request["native_attempt_receipt_path"] != request["native_send_receipt_path"],
                 "attempt_and_send_receipts_must_differ")
        return [], list(REQUIRED)
    except (PreparationDenied, OSError, ValueError, TypeError, KeyError, AttributeError) as error:
        reason = str(error) if isinstance(error, PreparationDenied) else "evidence_invalid_or_missing"
        return ["owner_delegated_publisher_preparation:" + reason], list(REQUIRED)


def is_exact_delegated_dispatch_decision(
    root: Path, *, policy: dict[str, Any], decision: dict[str, Any], task_id: str,
    target_department: str, target_thread_id: str, action_id: str, action_class: str, scope: str,
) -> bool:
    """Preserve an assistant sender only on this frozen preparation decision.

    Live freshness is checked before sending, not again after the native send.
    The attempt/sent markers therefore do not prevent recording its actual receipt.
    """
    try:
        request = _frozen_request(root, policy)
        _require((task_id, target_department, target_thread_id, action_id, action_class, scope)
                 == (TASK_ID, "publishing", TARGET_ID, ACTION_ID, "thread_message", SCOPE),
                 "dispatch_receipt_identity_mismatch")
        expected = {"status": "allow", "routing_status": "routing_allowed",
                    "department": "operations-assistant"}
        for key in ("task_id", "action_id", "action_class", "scope", "source_project_id",
                    "target_project_id", "target_department", "target_thread_id", "target_thread_title",
                    "target_cwd", "target_sidebar_section_id", "payload_sha256"):
            expected[key] = request.get(key)
        _require(all(decision.get(k) == v for k, v in expected.items())
                 and all(x in decision.get("required_receipts", []) for x in REQUIRED),
                 "dispatch_decision_not_exact_owner_preparation")
        return True
    except (PreparationDenied, OSError, ValueError, TypeError, KeyError, AttributeError):
        return False
