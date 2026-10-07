"""Exact Wave234 service body registrations. Never grants a production permit.

Proposed control helper only; not loaded by the active issuer until R0 review.
Future preview/readiness requires a separately reviewed explicit successor.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from tools.workflow_control import sha256_value

MANIFEST_PATH = "drafts/operations/fc-20260927-wave234-body-issuer-registration-v1/registration-manifest.json"
MANIFEST_SHA256 = "887851956dda8b3b3d6fc3e16ea2c649efccdf7aa8ddb448a4c6e63fc8687226"
FIELDS = ["content_en", "content_zh"]
EXPECTED = {
    "builtin": "b401a610-a4dc-4a0b-a7e0-efcac6c81d71",
    "kitchen": "ce4156db-9034-42c8-ba29-b35724ea7d6d",
    "design": "example-cms-record-3",
}
TASK = "fc-20260927-keyword-answer-wave2-source-merge-v2"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def pinned_json(root: Path, pin: dict) -> dict:
    path = (root / str(pin.get("path", ""))).resolve()
    require(path.is_relative_to(root.resolve()) and path.is_file(), "Wave234 source outside project or missing")
    data = path.read_bytes()
    require(hashlib.sha256(data).hexdigest() == pin.get("sha256"), "Wave234 frozen source changed")
    value = json.loads(data)
    require(isinstance(value, dict), "Wave234 source must be an object")
    return value


def validate_registration(root: Path, manifest: dict) -> dict:
    require(manifest.get("schema_version") == "wave234_body_exact_registration_v1"
            and manifest.get("mode") == "REGISTRATION_ONLY_NO_PERMIT"
            and manifest.get("production_authorized") is False
            and manifest.get("native_registration_only") is True
            and manifest.get("release_ready") is False
            and manifest.get("actual_remote_preview") is None
            and manifest.get("fields") == FIELDS,
            "Wave234 registration cannot declare capability, readiness or permission")
    rows = manifest.get("targets", [])
    require(isinstance(rows, list) and len(rows) == 3, "Wave234 must contain exactly three targets")
    targets = {}
    for row in rows:
        identity = row.get("identity", {})
        slug = identity.get("slug")
        require(slug in EXPECTED, "Wave234 slug outside frozen scope")
        version = f"{slug}-wave234-answer-source-merge-v4"
        expected = {
            "task_id": TASK, "action_id": f"publish-{version}",
            "candidate_version": version, "table": "services",
            "record_id": EXPECTED[slug], "slug": slug,
            "scope": f"flashcast.com.my:services/{EXPECTED[slug]}:content_en,content_zh:{version}",
        }
        require(identity == expected and version not in targets, "Wave234 identity differs or duplicates")
        pins = row.get("sources", {})
        require(set(pins) == {"candidate", "baseline", "request", "native_proposal", "rollback"},
                "Wave234 source inventory differs")
        values = {key: pinned_json(root, pin) for key, pin in pins.items()}
        candidate, baseline = values["candidate"], values["baseline"]
        request, native = values["request"], values["native_proposal"]["target"]
        rollback = values["rollback"]
        after = candidate.get("desired_fields")
        before = {key: baseline.get(key) for key in FIELDS}
        require(all(candidate.get(k) == v for k, v in expected.items())
                and candidate.get("action_class") == "cms_content_candidate"
                and candidate.get("execution_action_class") == "cms_write"
                and candidate.get("changed_fields") == FIELDS
                and isinstance(after, dict) and set(after) == set(FIELDS)
                and all(isinstance(after[k], str) and after[k].strip() for k in FIELDS)
                and candidate.get("performed_write") is False
                and candidate.get("published") is False and candidate.get("saved_id") is None,
                "Wave234 candidate identity, fields or unexecuted stage differs")
        cas = candidate.get("cas", {})
        retained = sorted(set(baseline) - set(FIELDS) - {"version", "updated_at"})
        require(baseline.get("id") == expected["record_id"] and baseline.get("slug") == slug
                and baseline.get("status") == "published"
                and cas.get("expected_updated_at") == baseline.get("updated_at")
                and cas.get("expected_version") == baseline.get("version")
                and cas.get("baseline_projection_fields") == sorted(baseline)
                and cas.get("full_row_sha256") == sha256_value(baseline)
                and cas.get("desired_fields_sha256") == sha256_value(after)
                and cas.get("retained_projection_fields") == retained
                and cas.get("retained_fields_sha256") == sha256_value({k: baseline[k] for k in retained}),
                "Wave234 full baseline, retained fields or CAS differs")
        require(request.get("mode") == "dry-run" and request.get("contentType") == "service"
                and request.get("nextStatus") == "published"
                and request.get("ownerApproved") is False and request.get("explicitExecution") is False
                and request.get("expectedUpdatedAt") == baseline["updated_at"]
                and request.get("record") == {**baseline, **after}
                and request.get("managedCandidate") == {
                    "taskId": TASK, "actionId": expected["action_id"],
                    "candidateVersion": version, "scope": expected["scope"], "operation": "publish"},
                "Wave234 local dry-run input or retained data differs")
        require(native.get("id") == expected["record_id"] and native.get("slug") == slug
                and native.get("table") == "services" and native.get("contentType") == "service"
                and all(native.get(a) == expected[b] for a, b in
                        (("taskId", "task_id"), ("actionId", "action_id"),
                         ("candidateVersion", "candidate_version"), ("scope", "scope")))
                and native.get("changedFields") == FIELDS
                and native.get("expectedUpdatedAt") == baseline["updated_at"]
                and native.get("baselineProjectionFields") == sorted(baseline)
                and native.get("baselineFieldsSha256") == sha256_value(baseline)
                and native.get("desiredFieldsSha256") == sha256_value(after)
                and native.get("retainedProjectionFields") == retained
                and native.get("retainedFieldsSha256") == cas["retained_fields_sha256"]
                and native.get("rollbackAllowed") is True and native.get("requiresParentRun") is True
                and native.get("rollbackFieldsSha256") == sha256_value(before),
                "Wave234 native proposal differs from exact frozen inputs")
        require(rollback.get("task_id") == TASK and rollback.get("parent_action_id") == expected["action_id"]
                and rollback.get("record_id") == expected["record_id"] and rollback.get("table") == "services"
                and rollback.get("restore_fields") == before and rollback.get("expected_current_fields") == after
                and rollback.get("retained_fields_sha256") == cas["retained_fields_sha256"]
                and rollback.get("parent_success_saved_id_and_new_updated_at_required") is True
                and rollback.get("fresh_full_row_match_required") is True
                and rollback.get("new_exact_rollback_permission_required") is True
                and rollback.get("performed_write") is False,
                "Wave234 rollback lacks exact completed-parent safeguards")
        targets[version] = {
            **expected, "candidate_shape": "native_wave234_body_registration",
            "changed_fields": FIELDS[:],
            "candidate": (pins["candidate"]["path"], pins["candidate"]["sha256"]),
            "rollback": (pins["baseline"]["path"], pins["baseline"]["sha256"]),
            "source_frozen_candidate": (pins["candidate"]["path"], pins["candidate"]["sha256"]),
            "expected_updated_at": baseline["updated_at"],
            "baseline_fields_sha256": sha256_value(baseline),
            "desired_fields_sha256": sha256_value(after),
            "rollback_fields_sha256": sha256_value(before),
            "native_registration_only": True, "release_ready": False,
            "production_authorized": False, "qa_outbox": None,
            "requires_completed_parent": True, "native_source_manifest": MANIFEST_PATH,
        }
    require({t["slug"] for t in targets.values()} == set(EXPECTED), "Wave234 exact three slugs missing")
    return targets


def load_wave234_body_registration(root: Path) -> dict:
    manifest = pinned_json(root, {"path": MANIFEST_PATH, "sha256": MANIFEST_SHA256})
    return validate_registration(root, manifest)


def validate_wave234_body_candidate(root: Path, candidate: dict, target: dict) -> None:
    frozen = load_wave234_body_registration(root).get(target.get("candidate_version"))
    require(frozen is not None and target == frozen, "Wave234 target must remain registration-only")
    source = pinned_json(root, {"path": target["candidate"][0], "sha256": target["candidate"][1]})
    require(candidate == source, "Wave234 candidate differs from exact frozen source")
