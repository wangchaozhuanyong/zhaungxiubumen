"""Read-only staged native CMS admission; never issues or activates a permit.

The production issuer remains unchanged. This validates the exact 18 source
bindings and their independent QA before a separate capability release review.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from . import workflow_control as wc

QA_THREAD = "<LOCAL_TASK_ID>"
PROJECT_ID = "<LOCAL_PROJECT_ID>"
FIELDS = {"content_en", "content_zh"}
IDENTITY = ("task_id", "action_id", "candidate_version", "record_id", "slug",
            "scope", "table", "content_type", "expected_updated_at", "expected_version")


class AdmissionError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AdmissionError(message)


def pinned_json(root: Path, pin: dict) -> dict:
    relative = Path(pin["path"])
    path = (root / relative).resolve()
    require(not relative.is_absolute() and path.is_relative_to(root.resolve()),
            "Evidence escapes the control project")
    require(path.is_file(), "Pinned evidence is missing")
    require(hashlib.sha256(path.read_bytes()).hexdigest() == pin["sha256"],
            "Pinned evidence hash differs")
    return json.loads(path.read_text())


def validate_entry(root: Path, entry: dict) -> dict:
    binding = pinned_json(root, entry["binding"])
    source = pinned_json(root, entry["source"])
    baseline = pinned_json(root, entry["baseline"])
    rollback = pinned_json(root, entry["rollback"])
    qa = pinned_json(root, entry["qa"])
    original_qa = pinned_json(root, entry["original_qa"])
    require(all(binding.get(k) == entry.get(k) for k in IDENTITY), "Binding identity differs")
    require(binding.get("schema_version") == "native_bilingual_body_binding_v1"
            and binding.get("candidate_type") == "cms_content_candidate"
            and binding.get("action_class") == "cms_write"
            and binding.get("original_task_id") == entry["original_task_id"]
            and binding.get("risk_level") == "R1"
            and binding.get("published") is False and binding.get("saved_id") is None
            and binding.get("permit") is None, "Binding channel, origin or stage differs")
    require(set(binding.get("changed_fields", [])) == FIELDS
            and len(binding["changed_fields"]) == 2
            and binding.get("scope", "").startswith("flashcast.com.my:")
            and (entry["table"], entry["content_type"]) in
            {("services", "service"), ("blog_posts", "blog")}, "Non-body field or type")
    require(binding["original_frozen_source_path"] == entry["source"]["path"]
            and binding["original_frozen_source_sha256"] == entry["source"]["sha256"]
            and binding["original_qa"]["path"] == entry["original_qa"]["path"]
            and binding["original_qa"]["sha256"] == entry["original_qa"]["sha256"],
            "Original frozen provenance differs")
    desired = source.get(binding["original_body_source_key"], {})
    require(set(desired) == FIELDS and all(isinstance(v, str) and v.strip()
                                           for v in desired.values()), "Invalid bilingual body")
    source_row = (source.get("record_id") or source.get("observed_record_key", {}).get("id")
                  or source.get("record_selector", {}).get("id"))
    require(source.get("task_id") == entry["task_id"]
            and source.get("candidate_version") == entry["candidate_version"]
            and source_row == entry["record_id"], "Original source identity differs")
    require(baseline.get("id") == entry["record_id"]
            and baseline.get("slug") == entry["slug"]
            and baseline.get("status") == "published"
            and baseline.get("updated_at") == entry["expected_updated_at"]
            and baseline.get("version") == entry["expected_version"], "Baseline CAS differs")
    projection = binding["baseline_projection_fields"]
    retained = binding["retained_projection_fields"]
    require(len(projection) == len(set(projection)) and set(projection) == set(baseline)
            and len(retained) == len(set(retained))
            and set(retained) == set(projection) - FIELDS - {"updated_at", "version"},
            "Baseline or retained projection omits fields")
    checks = {
        "baseline_fields_sha256": wc.sha256_value({k: baseline[k] for k in projection}),
        "desired_fields_sha256": wc.sha256_value(desired),
        "rollback_fields_sha256": wc.sha256_value({k: baseline[k] for k in FIELDS}),
        "retained_fields_sha256": wc.sha256_value({k: baseline[k] for k in retained}),
    }
    require(all(binding.get(k) == v and entry.get(k) == v for k, v in checks.items()),
            "Body, baseline, retained or rollback digest differs")
    if binding["original_body_source_key"] == "desired_fields":
        rollback_identity = all(rollback.get(k) == entry[k] for k in
                                ("task_id", "action_id", "candidate_version", "record_id"))
        rollback_guards = (rollback.get("expected_current_updated_at") is None
                           and rollback.get("expected_current_version") is None
                           and rollback.get("fill_only_from_actual_saved_receipt") is True
                           and rollback.get("never_overwrite_later_record") is True)
    else:
        require(binding["original_body_source_key"] == "candidate_values", "Unknown body source shape")
        rollback_identity = (rollback.get("original_task_id") == entry["original_task_id"]
                             and all(rollback.get(k) == entry[k] for k in
                                     ("candidate_version", "record_id")))
        rollback_guards = (rollback.get("expected_postsave_updated_at") is None
                           and rollback.get("expected_postsave_version") is None
                           and rollback.get("fill_from_actual_saved_receipt_only") is True)
    require(rollback_identity and rollback_guards
            and rollback.get("restore_fields") == {k: baseline[k] for k in FIELDS}
            and rollback.get("separate_protected_rollback_permit_required") is True
            and rollback.get("applied") is False, "Rollback template differs")
    producer = binding["website_producer"]
    producer_identity = {"taskId": "task_id", "originalTaskId": "original_task_id",
                         "actionId": "action_id", "candidateVersion": "candidate_version",
                         "recordId": "record_id", "slug": "slug", "scope": "scope",
                         "table": "table", "contentType": "content_type",
                         "expectedUpdatedAt": "expected_updated_at", "expectedVersion": "expected_version"}
    require(all(producer.get(k) == entry[v] for k, v in producer_identity.items())
            and producer.get("actionClass") == "cms_write"
            and producer.get("changedFields") == binding["changed_fields"]
            and producer.get("requiresParentRun") is True
            and producer.get("rollbackAllowed") is True
            and producer.get("originalFrozenSourcePath") == entry["source"]["path"]
            and producer.get("originalFrozenSourceSha256") == entry["source"]["sha256"]
            and producer.get("sourceCandidateSha256") == entry["source"]["sha256"]
            and producer.get("rollbackRecordSha256") == entry["baseline"]["sha256"]
            and producer.get("rollbackPackageSha256") == entry["rollback"]["sha256"]
            and producer.get("desiredFieldsSourceKey") == binding["original_body_source_key"]
            and producer.get("baselineProjectionFields") == projection
            and producer.get("retainedProjectionFields") == retained
            and producer.get("baselineFieldsSha256") == checks["baseline_fields_sha256"]
            and producer.get("desiredFieldsSha256") == checks["desired_fields_sha256"]
            and producer.get("rollbackFieldsSha256") == checks["rollback_fields_sha256"]
            and producer.get("retainedFieldsSha256") == checks["retained_fields_sha256"],
            "Website producer or completed-parent guard differs")
    require(qa.get("department") == "qa" and qa.get("chat_task_id") == QA_THREAD
            and qa.get("project_id") == PROJECT_ID
            and qa.get("status") == "completed"
            and qa.get("gate_status") == qa.get("qa_result") == "PASS_FOR_AUTO_RELEASE"
            and qa.get("qa_verdict") == qa.get("verdict") == "pass"
            and qa.get("action_class") == "cms_content_candidate"
            and qa.get("execution_action_class") == "cms_write"
            and qa.get("risk_level") == "R1"
            and qa.get("channel_locked_by_independent_qa") is True
            and qa.get("review_scope") == "binding_only_plus_unchanged_original_editorial_QA"
            and qa.get("release_ready") is False
            and qa.get("published") is False and qa.get("blockers") == []
            and all(qa.get(k) == entry[k] for k in IDENTITY)
            and qa.get("candidate_path") == entry["binding"]["path"]
            and qa.get("candidate_sha256") == entry["binding"]["sha256"]
            and qa.get("source_candidate_path") == entry["source"]["path"]
            and qa.get("source_candidate_sha256") == entry["source"]["sha256"]
            and qa.get("allowed_fields") == binding["changed_fields"]
            and qa.get("original_qa", {}).get("path") == entry["original_qa"]["path"]
            and qa.get("original_qa", {}).get("sha256") == entry["original_qa"]["sha256"]
            and all(qa.get(k) == v for k, v in checks.items()),
            "Exact fixed QA binding-only PASS is missing")
    require(original_qa.get("department") == "qa"
            and original_qa.get("task_id") == entry["task_id"]
            and original_qa.get("candidate_version") == entry["candidate_version"]
            and original_qa.get("candidate_sha256") == entry["source"]["sha256"]
            and qa.get("editorial_review_reused") is True
            and qa.get("source_text_unchanged") is True, "Original editorial QA provenance differs")
    return {"candidate_version": entry["candidate_version"], "source_admission": "PASS",
            "production_authorized": False, "permit_issued": False}


def validate_manifest(root: Path, manifest: dict) -> list[dict]:
    require(manifest.get("project_id") == PROJECT_ID
            and manifest.get("owner") == "operations"
            and manifest.get("status") == "STAGED_PENDING_INDEPENDENT_CONTROL_QA"
            and manifest.get("production_authorized") is False
            and manifest.get("issuer_integration_executed") is False
            and manifest.get("permit_issued") is False, "Staged admission is not a release permit")
    entries = manifest.get("entries", [])
    parent = pinned_json(root, manifest["qa_parent"])
    require(parent.get("department") == "qa" and parent.get("chat_task_id") == QA_THREAD
            and parent.get("task_id") == "fc-20260927-cms-native-admission-contract-v1"
            and parent.get("gate_status") == "HOLD_NEEDS_WORK"
            and parent.get("release_ready") is False, "Capability HOLD must remain separate")
    reviewed = {(d["path"], d["sha256"]) for d in parent.get("deliveries", [])
                if d.get("gate_status") == "PASS_FOR_AUTO_RELEASE"}
    require({(e["qa"]["path"], e["qa"]["sha256"]) for e in entries} == reviewed,
            "Staged QA pins differ from the 18 actual independent results")
    require(len(entries) == 18
            and len({e["candidate_version"] for e in entries}) == 18
            and len({(e["table"], e["record_id"]) for e in entries}) == 18
            and len({(e["task_id"], e["action_id"], e["scope"]) for e in entries}) == 18,
            "Native admission must contain exactly 18 unique original bindings")
    return [validate_entry(root, entry) for entry in entries]
