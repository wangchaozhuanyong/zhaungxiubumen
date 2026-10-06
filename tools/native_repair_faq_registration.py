"""Frozen two-field repair FAQ registration; this module never issues permits.

Not imported by the active issuer until its exact integration receives R0 QA.
The target always remains registration-only pending separately reviewed native
capability, legitimate protected preview and actual release readiness.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .workflow_control import sha256_value

MANIFEST_PATH = "drafts/operations/fc-20260927-repair-faq-issuer-registration-v1/registration-manifest.json"
MANIFEST_SHA256 = "9bf3cbbd2edf5729aecadccb92049632fee5995261178663ba8abb26d02e3710"
IDENTITY = {
    "task_id": "fc-20260927-repair-page-optimization-source-bound-v1",
    "action_id": "repair-faq-pair-update-v1",
    "candidate_version": "repair-faq-source-bound-v2",
    "scope": "flashcast.com.my:services:surface-repair:faqs-en-zh:repair-faq-source-bound-v2",
    "table": "services",
    "record_id": "7c9b9e23-025e-4fc9-85c8-de84a5449370",
    "slug": "surface-repair",
}
FIELDS = ["faqs_en", "faqs_zh"]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def pinned_json(root: Path, pin: dict) -> dict:
    path = (root / str(pin.get("path", ""))).resolve()
    require(path.is_relative_to(root.resolve()) and path.is_file(), "Repair source outside project or missing")
    data = path.read_bytes()
    require(hashlib.sha256(data).hexdigest() == pin.get("sha256"), "Repair frozen source changed")
    value = json.loads(data)
    require(isinstance(value, dict), "Repair source must be an object")
    return value


def validate_registration(root: Path, manifest: dict) -> dict:
    require(all(manifest.get(k) == v for k, v in IDENTITY.items()), "Repair manifest identity differs")
    require(manifest.get("schema_version") == "repair_faq_exact_registration_v1"
            and manifest.get("target_name") == IDENTITY["candidate_version"]
            and manifest.get("mode") == "REGISTRATION_ONLY_NO_PERMIT"
            and manifest.get("fields") == FIELDS
            and manifest.get("production_authorized") is False
            and manifest.get("native_registration_only") is True
            and manifest.get("release_ready") is False
            and manifest.get("actual_remote_preview") is None,
            "Repair registration cannot declare capability, readiness or permission")
    pins = manifest.get("sources", {})
    require(set(pins) == {"candidate", "baseline", "before", "after", "preview", "native_proposal", "native_input_validation"},
            "Repair source inventory differs")
    values = {key: pinned_json(root, pin) for key, pin in pins.items()}
    candidate, baseline = values["candidate"], values["baseline"]
    before, after = values["before"], values["after"]
    preview, native = values["preview"], values["native_proposal"]["target"]
    require(all(candidate.get(k) == IDENTITY[k] for k in ("task_id", "action_id", "candidate_version", "scope", "table"))
            and candidate.get("action_class") == "cms_content_candidate"
            and candidate.get("execution_action_class") == "cms_write"
            and candidate.get("allowed_fields") == FIELDS
            and candidate.get("fields") == after
            and set(before) == set(after) == set(FIELDS)
            and candidate.get("writes") == 0 and candidate.get("saved_id") is None
            and candidate.get("published") is False,
            "Repair source identity, exact field set or unexecuted stage differs")
    cas = candidate["cas"]
    require(cas.get("row_id") == baseline.get("id") == IDENTITY["record_id"]
            and cas.get("slug") == baseline.get("slug") == IDENTITY["slug"]
            and cas.get("status") == baseline.get("status") == "published"
            and cas.get("expected_version") == baseline.get("version")
            and cas.get("expected_updated_at") == baseline.get("updated_at")
            and {field: baseline[field] for field in FIELDS} == before
            and cas.get("before_fields_sha256") == sha256_value(before)
            and candidate.get("desired_fields_sha256") == sha256_value(after),
            "Repair baseline, CAS or two-field hash differs")
    for field in FIELDS:
        require(len(before[field]) == 6 and len(after[field]) == 9
                and before[field][1:6] == after[field][1:6]
                and all(isinstance(faq, dict) and set(faq) == {"q", "a"}
                        and all(isinstance(faq[k], str) and faq[k].strip() for k in ("q", "a"))
                        for faq in after[field]),
                "Repair retained or nonempty FAQ pair differs")
    require(preview.get("mode") == "dry-run" and preview.get("contentType") == "service"
            and preview.get("nextStatus") == "published"
            and preview.get("ownerApproved") is False
            and preview.get("explicitExecution") is False
            and preview.get("expectedUpdatedAt") == baseline["updated_at"]
            and preview.get("record") == {**baseline, **after}
            and preview.get("managedCandidate") == {
                "taskId": IDENTITY["task_id"], "actionId": IDENTITY["action_id"],
                "candidateVersion": IDENTITY["candidate_version"],
                "scope": IDENTITY["scope"], "operation": "publish"},
            "Repair local preview input changes retained data, mode or identity")
    retained = native.get("retainedProjectionFields", [])
    require(native.get("id") == IDENTITY["record_id"] and native.get("slug") == IDENTITY["slug"]
            and native.get("table") == IDENTITY["table"] and native.get("contentType") == "service"
            and all(native.get(camel) == IDENTITY[snake] for camel, snake in
                    (("taskId", "task_id"), ("actionId", "action_id"),
                     ("candidateVersion", "candidate_version"), ("scope", "scope")))
            and native.get("changedFields") == FIELDS
            and native.get("expectedUpdatedAt") == baseline["updated_at"]
            and native.get("baselineProjectionFields") == sorted(baseline)
            and native.get("baselineFieldsSha256") == sha256_value(baseline)
            and native.get("desiredFieldsSha256") == sha256_value(after)
            and native.get("rollbackFieldsSha256") == sha256_value(before)
            and set(retained) == set(baseline) - set(FIELDS) - {"version", "updated_at"}
            and native.get("retainedFieldsSha256") == sha256_value({k: baseline[k] for k in retained})
            and native.get("requiresParentRun") is True,
            "Repair native proposal differs from frozen local inputs")
    return {
        **IDENTITY,
        "candidate_shape": "native_repair_faq_registration",
        "changed_fields": FIELDS[:],
        "candidate": (pins["candidate"]["path"], pins["candidate"]["sha256"]),
        "rollback": (pins["before"]["path"], pins["before"]["sha256"]),
        "expected_updated_at": baseline["updated_at"],
        "baseline_fields_sha256": sha256_value(baseline),
        "desired_fields_sha256": sha256_value(after),
        "rollback_fields_sha256": sha256_value(before),
        "source_frozen_candidate": (pins["candidate"]["path"], pins["candidate"]["sha256"]),
        "native_registration_only": True,
        "release_ready": False,
        "production_authorized": False,
        "qa_outbox": None,
        "requires_completed_parent": True,
        "native_source_manifest": MANIFEST_PATH,
    }


def load_repair_faq_registration(root: Path) -> dict:
    manifest = pinned_json(root, {"path": MANIFEST_PATH, "sha256": MANIFEST_SHA256})
    return {IDENTITY["candidate_version"]: validate_registration(root, manifest)}


def validate_repair_faq_candidate(root: Path, candidate: dict, target: dict) -> None:
    frozen_target = load_repair_faq_registration(root)[IDENTITY["candidate_version"]]
    require(target == frozen_target, "Repair issuer target must remain exactly registration-only")
    source = pinned_json(root, {"path": target["candidate"][0], "sha256": target["candidate"][1]})
    require(candidate == source, "Repair candidate differs from exact frozen source")
