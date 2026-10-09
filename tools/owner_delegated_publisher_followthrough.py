"""Three frozen coordination messages for the owner's first-three takeover.

No production permission, QA verdict, controller decision or generic route.
"""
from __future__ import annotations
import datetime as dt
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Callable
from owner_delegated_publishing_preparation import (
    _require, _read, _path, _sha, _fresh, _frozen_request, PreparationDenied,
    PROJECT_ID, PROJECT_ROOT, SOURCE_ID, SOURCE_TITLE, BUSINESS_TASK_ID,
)

PREFIX = "owner_delegated_followthrough:"
MARKER = "owner_authorization:publisher_first_three_coordination_only"
REQUIRED = ["routing_precheck:owner_delegated_publisher_followthrough", MARKER]
STAGES = {
    "fc-20261007-publisher-three-rollback-projection-rework-v1":
        ("publishing", "<LOCAL_TASK_ID>", "FLASH CAST｜后台发布部｜2026-10", PROJECT_ID, PROJECT_ROOT, "装修公司部门"),
    "fc-20261007-publisher-three-execution-admission-qa-v1":
        ("qa", "<LOCAL_TASK_ID>", "FLASH CAST｜质检与Reality Checker部｜2026-09", PROJECT_ID, PROJECT_ROOT, "装修公司部门"),
    "fc-20261007-publisher-three-designated-binding-v1":
        ("designated-website-developer", "<WEBSITE_DEVELOPER_THREAD>", "同步管理后台与客户端功能", "<LOCAL_PROJECT_ID>", "<WEBSITE_PROJECT_ROOT>", "threads"),
}
TARGET_IDS = ['example-old-house', 'example-quotation-checklist', 'example-design']
TARGETS = [
    {"item": "v17", "table": "services", "record_id": TARGET_IDS[0], "slug": "old-house", "changed_fields": ["faqs_en", "faqs_zh"]},
    {"item": "v18", "table": "blog_posts", "record_id": TARGET_IDS[1], "slug": "renovation-quotation-checklist-malaysia", "changed_fields": ["content_en", "content_zh"]},
    {"item": "v20", "table": "services", "record_id": TARGET_IDS[2], "slug": "design", "changed_fields": ["faqs_en", "faqs_zh"]},
]
SOURCE_PINS = {'v17': ('3a551d55e564e48f08fcf916865c1929a7a4282916f3747248f8f2dbf24abbaa', '0c58a1305473a71e909197851e7a4842c272cff368df563ac7dbff497cf675b0'), 'v18': ('2632bafe1c0678a84e1a0c321260f4f3a49b22fcad3bda5c931ba3f6fd528a5c', 'ec349082004e9a42abfc207ef65b10954a905032e3157492a72de93739452b76'), 'v20': ('152c828c38381ecf3a9dbfa80621596f11ded42b72082969555e90bf04051773', '1029838ba1ec8e64692e6d04e573a97177027542a6553d2404f4b9d63edca7ba')}


def _canonical_sha(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _request(root: Path, policy: dict[str, Any], task_id: str) -> dict[str, Any]:
    # Reuse the exact native owner proof, pinned to this actual assistant.
    _frozen_request(root, policy)
    _require(_read(root / "data/workflows" / (BUSINESS_TASK_ID + ".json")).get("task_id") == BUSINESS_TASK_ID, "original_business_workflow_missing")
    _require(task_id in STAGES, "stage_not_authorized")
    config = policy.get("routing_policy", {}).get("owner_delegated_publisher_followthrough", {})
    entries = config.get("requests", {})
    _require(config.get("status") == "approved_exact_coordination_only" and isinstance(entries, dict), "route_not_enabled")
    pin = entries.get(task_id, {})
    path = _path(root, pin.get("path"))
    _require(_sha(path) == pin.get("sha256"), "exact_request_pin_mismatch")
    req = _read(path)
    dep, thread, title, project, cwd, group = STAGES[task_id]
    exact_scope = ("owner_project_handoff:" if dep == "designated-website-developer" else PREFIX) + task_id
    exact = {"task_id": task_id, "action_id": "send-" + task_id, "scope": exact_scope,
             "action_class": "thread_message", "sender_department": "operations-assistant",
             "source_project_id": PROJECT_ID, "target_project_id": project,
             "target_department": dep, "target_thread_id": thread, "target_thread_title": title,
             "target_cwd": cwd, "target_group_name": group,
             "original_business_task_id": BUSINESS_TASK_ID, "target_record_ids": TARGET_IDS,
             "targets": TARGETS,
             "production_authority_granted": False, "coordination_only": True}
    _require(all(req.get(k) == v for k, v in exact.items()), "exact_stage_binding_mismatch")
    _require(req.get("production_authority_granted") is False and req.get("coordination_only") is True, "exact_boolean_coordination_required")
    for key in ("production_write_allowed", "cms_write_allowed", "site_publish_allowed", "qa_verdict_allowed", "production_decision_allowed", "production_gates_waived"):
        _require(req.get(key, False) is False, "coordination_does_not_grant_production_authority")
    for name in ("packet", "payload"):
        path = _path(root, req.get(name + "_path"))
        _require(path.stat().st_size > 0 and _sha(path) == req.get(name + "_sha256"), name + "_pin_mismatch")
    packet = _read(_path(root, req["packet_path"]))
    _require(packet.get("original_business_task_id") == BUSINESS_TASK_ID
             and packet.get("target_record_ids") == TARGET_IDS
             and packet.get("targets") == TARGETS
             and packet.get("production_authority_granted") is False, "packet_scope_mismatch")
    pins = packet.get("input_pins", [])
    _require(isinstance(pins, list) and bool(pins), "input_pins_required")
    for pin in pins:
        path = _path(root, pin.get("path"))
        _require(_sha(path) == pin.get("sha256") and path.stat().st_size == pin.get("size"), "input_pin_mismatch")
    candidates = packet.get("content_candidates", [])
    _require(isinstance(candidates, list) and len(candidates) == 3, "exact_three_candidate_pins_required")
    for expected, pin in zip(TARGETS, candidates):
        path = _path(root, pin.get("path"))
        _require(_sha(path) == pin.get("sha256") and path.stat().st_size == pin.get("size"), "candidate_pin_mismatch")
        candidate = _read(path)
        target = candidate.get("actual_native_target", {})
        _require(all(target.get(k) == expected[k] for k in ("table", "record_id", "slug"))
                 and candidate.get("changed_fields") == expected["changed_fields"]
                 and candidate.get("task_id") == BUSINESS_TASK_ID
                 and candidate.get("execution_owner", {}).get("department") == "publishing", "candidate_exact_target_mismatch")
        version = "v1" if dep == "publishing" else "v2"
        _require(candidate.get("candidate_version") == expected["item"] + "-owner-publisher-native-preparation-" + version + "-20261007", "candidate_version_mismatch")
        proposed_pin = candidate.get("historical_executor_request", {})
        proposed_path = _path(root, proposed_pin.get("path"))
        native_pin = candidate.get("native_source", {})
        native_path = _path(root, native_pin.get("path"))
        _require(_sha(native_path) == native_pin.get("sha256") == SOURCE_PINS[expected["item"]][0]
                 and _sha(proposed_path) == proposed_pin.get("sha256") == SOURCE_PINS[expected["item"]][1], "original_frozen_request_pin_mismatch")
        native = _read(native_path)
        row = native.get("record", {})
        proposed = _read(proposed_path)
        desired = {x["native_storage_key"]: x["proposed_native_after"] for x in proposed.get("field_source_and_values", [])}
        _require(candidate.get("desired_fields") == desired, "frozen_content_changed")
        identity = candidate.get("proposed_managed_identity", {})
        _require(identity == {"taskId": BUSINESS_TASK_ID, "actionId": "publish-" + candidate["candidate_version"],
                 "candidateVersion": candidate["candidate_version"], "operation": "publish",
                 "scope": "flashcast.com.my:" + expected["table"] + ":" + expected["record_id"] + ":" + ",".join(expected["changed_fields"])}
                 and candidate.get("baseline_projection_fields") == native.get("projection"), "managed_identity_or_validation_projection_changed")
        _require(candidate.get("before_fields") == {k: row[k] for k in expected["changed_fields"]}
                 and target.get("expected_updated_at_raw") == row.get("updated_at")
                 and target.get("observed_version") == row.get("version")
                 and candidate.get("desired_fields_sha256") == _canonical_sha(desired)
                 and candidate.get("baseline_fields_sha256") == _canonical_sha({k: row[k] for k in candidate.get("baseline_projection_fields", [])}), "native_before_CAS_or_payload_hash_mismatch")
    _require(req.get("native_attempt_receipt_path") != req.get("native_send_receipt_path"), "distinct_send_markers_required")
    return req


def check_owner_delegated_followthrough(root: Path, *, policy: dict[str, Any], departments: dict[str, dict[str, Any]], requested: dict[str, Any], validate_receipt_chain: Callable[..., Any]) -> tuple[list[str], list[str]]:
    try:
        task_id = requested.get("task_id", "")
        req = _request(root, policy, task_id)
        _require(all(req.get(k) == v for k, v in requested.items()), "requested_identity_mismatch")
        now = dt.datetime.now(dt.timezone.utc)
        live = _read(_path(root, req.get("live_identity_path")))
        _require(live.get("source_method") == "mcp__codex_app__list_threads" and _fresh(live.get("observed_at"), 300, now), "fresh_native_identity_required")
        dep, target_id, title, project, cwd, group = STAGES[task_id]
        for role, thread_id, expected_title, expected_project, expected_cwd in [
            ("operations-assistant", SOURCE_ID, SOURCE_TITLE, PROJECT_ID, PROJECT_ROOT),
            (dep, target_id, title, project, cwd),
        ]:
            rows = [x for x in live.get("threads", []) if x.get("id") == thread_id]
            _require(len(rows) == 1, "live_identity_missing_or_ambiguous")
            row = rows[0]
            _require(all(row.get(k) == v for k, v in {"title": expected_title, "projectId": expected_project, "cwd": expected_cwd, "hostId": "local"}.items()), "live_identity_mismatch")
            _require(row.get("status") == ("active" if role == "operations-assistant" else "idle"), "active_target_or_inactive_source")
            if role != "designated-website-developer":
                binding = departments.get(role, {}).get("chat_binding", {})
                _require(all(binding.get(k) == v for k, v in {"task_id": thread_id, "title": expected_title, "project_id": expected_project, "cwd": expected_cwd, "status": "bound_and_visible", "dispatch_eligible": True, "reply_health": "healthy_visible_reply_verified"}.items()), "registered_identity_or_health_mismatch")
                _require(_fresh(binding.get("last_health_check_at") or binding.get("last_verified_at"), 26 * 3600, now), "registered_health_stale")
                expected_group = "装修公司部门"
                sections = [x for x in live.get("sections", []) if x.get("name") == expected_group]
                _require(len(sections) == 1 and sections[0].get("sectionId") == binding.get("sidebar_section_id")
                         and "codex:thread:local:" + thread_id in sections[0].get("itemKeys", []), "registered_group_mismatch")
        if dep == "designated-website-developer":
            groups = [x for x in live.get("sections", []) if x.get("sectionId") == "threads"]
            _require(len(groups) == 1 and "codex:project:" + project in groups[0].get("itemKeys", [])
                     and req.get("target_sidebar_section_id") == "threads", "designated_developer_group_mismatch")
            reply = live.get("completed_target_reply", {})
            _require(reply.get("thread_id") == target_id and reply.get("completed") is True
                     and reply.get("nonempty") is True and _fresh(reply.get("reply_observed_at"), 26 * 3600, now)
                     and reply.get("source_method") == "mcp__codex_app__read_thread"
                     and reply.get("project_id") == project and reply.get("cwd") == cwd
                     and re.fullmatch(r"[0-9a-f]{64}", reply.get("reply_sha256", ""))
                     and reply.get("host_id") == "local", "designated_developer_fresh_completed_reply_required")
            accepted = _read(_path(root, req.get("control_acceptance_path")))
            _require(_sha(_path(root, req["control_acceptance_path"])) == req.get("control_acceptance_sha256")
                     and accepted.get("production_authority_granted") is False, "fixed_QA_acceptance_required")
            if accepted.get("qa_contract") == "publisher-three-successor-v2-and-handover-v4":
                from publisher_designated_successor_qa import validate as validate_successor_developer_QA
                validate_successor_developer_QA(root, req, accepted, validate_receipt_chain)
            else:
                qa_task = "fc-20261007-publisher-three-execution-admission-qa-v1"
                qa_chain, qa_invalid = validate_receipt_chain(root, qa_task)
                qa = [x for x in qa_chain if x.get("receipt_id") == accepted.get("qa_receipt_id")
                      and x.get("receipt_type") == "qa_verdict" and x.get("department") == "qa"
                      and x.get("chat_task_id") == STAGES[qa_task][1] and x.get("verdict") == "pass"
                      and x.get("action_class") == "analysis"]
                outbox_path = _path(root, accepted.get("qa_outbox_path"))
                _require(not qa_invalid and len(qa) == 1 and _sha(outbox_path) == accepted.get("qa_outbox_sha256")
                         and any(p.get("path") == str(outbox_path.relative_to(root)) and p.get("sha256") == accepted.get("qa_outbox_sha256") for p in qa[0].get("evidence", [])), "exact_fixed_QA_receipt_required")
                qa_box = _read(outbox_path)
                reviewed_path = _path(root, accepted.get("candidate_path"))
                reviewed = _read(reviewed_path)
                _require(_sha(reviewed_path) == accepted.get("candidate_sha256")
                         and qa_box.get("candidate_sha256") == accepted.get("candidate_sha256")
                         and qa_box.get("task_id") == qa_task and qa_box.get("department") == "qa"
                         and (qa_box.get("fixed_chat_task_id") or qa_box.get("chat_task_id")) == STAGES[qa_task][1]
                         and qa_box.get("risk_level") == "R0" and qa_box.get("production_release_eligible") is False
                         and qa_box.get("status") == "completed" and qa_box.get("qa_verdict") == "pass"
                         and qa_box.get("qa_result") == "PASS_INTERNAL_APPLICATION_ALLOWED"
                         and qa_box.get("candidate_version") == "publisher-three-execution-admission-control-v1-20261007"
                         and reviewed.get("task_id") == qa_task
                         and reviewed.get("candidate_version") == qa_box.get("candidate_version")
                         and qa[0].get("action_id") == "qa-publisher-three-execution-admission-v1"
                         and qa[0].get("scope") == "project:publisher-three:execution-admission-control:v1", "fixed_QA_not_this_candidate")
                packet = _read(_path(root, req["packet_path"]))
                _require(all(pin in reviewed.get("input_pins", []) for pin in packet["input_pins"])
                         and all(pin in reviewed.get("content_candidates", []) for pin in packet["content_candidates"]), "developer_inputs_not_exactly_QA_reviewed")
        else:
            _require(req.get("target_sidebar_section_id") == departments[dep]["chat_binding"]["sidebar_section_id"], "target_sidebar_mismatch")
        snapshot = _read(root / "data/workflows" / (task_id + ".json"))
        _require(snapshot.get("task_id") == task_id and snapshot.get("plan_status") == "ready_to_send" and snapshot.get("current_state") not in {"closed", "failed", "cancelled"}, "workflow_not_dispatchable")
        plan_dep, plan_thread = ("operations-assistant", SOURCE_ID) if dep == "designated-website-developer" else (dep, target_id)
        selected = [x for x in snapshot.get("departments", []) if x.get("department") == plan_dep]
        _require(len(selected) == 1 and selected[0].get("chat_task_id") == plan_thread, "target_not_exact_plan_participant")
        chain, invalid = validate_receipt_chain(root, task_id)
        _require(not invalid and not any(x.get("receipt_type") == "dispatch_sent" for x in chain), "invalid_chain_or_stage_already_sent")
        for key in ("native_attempt_receipt_path", "native_send_receipt_path"):
            _require(not _path(root, req[key]).exists(), "stage_send_already_attempted")
        return [], list(REQUIRED)
    except (PreparationDenied, OSError, ValueError, TypeError, KeyError, AttributeError) as error:
        return ["owner_delegated_followthrough:" + (str(error) if isinstance(error, PreparationDenied) else "missing_or_invalid_evidence")], list(REQUIRED)


def is_exact_followthrough_dispatch_decision(root: Path, *, policy: dict[str, Any], decision: dict[str, Any], task_id: str, target_department: str, target_thread_id: str, action_id: str, action_class: str, scope: str) -> bool:
    try:
        req = _request(root, policy, task_id)
        _require((target_department, target_thread_id, action_id, action_class, scope) == (req["target_department"], req["target_thread_id"], req["action_id"], "thread_message", req["scope"]), "receipt_binding_mismatch")
        expected = {"status": "allow", "routing_status": "routing_allowed", "department": "operations-assistant"}
        for key in ("task_id", "action_id", "action_class", "scope", "source_project_id", "target_project_id", "target_department", "target_thread_id", "target_thread_title", "target_cwd", "target_sidebar_section_id", "payload_sha256"):
            expected[key] = req.get(key)
        _require(all(decision.get(k) == v for k, v in expected.items()) and all(x in decision.get("required_receipts", []) for x in REQUIRED), "decision_not_exact_coordination")
        return True
    except (PreparationDenied, OSError, ValueError, TypeError, KeyError, AttributeError):
        return False
