"""Exact registration-only integration candidate for the 18 native body targets.

No credential, network, permit issue or active issuer mutation happens here.
Release readiness must be separately pinned and independently reviewed later.
"""
from __future__ import annotations

import copy
from pathlib import Path

from .native_cms_admission import FIELDS, IDENTITY, pinned_json, require, validate_entry
from .native_cms_admission_v2 import validate_staged_native_manifest

INDEX_PIN = {
    "path": "drafts/operations/fc-20260927-cms-native-issuer-integration-v1/registration-index.json",
    "sha256": "f051e5626f27158c920a103b26bb7c34edd47aaa7f07d22ceba33c0893ae09eb",
}
MANIFEST_PIN = {
    "path": "drafts/operations/fc-20260927-cms-native-staged-admission-v2/admission-manifest.json",
    "sha256": "2aa64dfdeeb5ea0b8bfa71a3b4bc558e1d0b7504d83857f9482656ec37184489",
}
DIGESTS = ("baseline_fields_sha256", "desired_fields_sha256",
           "rollback_fields_sha256", "retained_fields_sha256")


def load_native_issuer_targets(root: Path) -> dict:
    index = pinned_json(root, INDEX_PIN)
    require(index.get("schema_version") == "native_issuer_registration_candidate_v1"
            and index.get("mode") == "REGISTRATION_ONLY_NO_PERMIT"
            and index.get("production_authorized") is False
            and index.get("applied_to_active_issuer") is False
            and index.get("release_readiness_qa") is None
            and index.get("protected_remote_preview") is None
            and index.get("staged_admission_manifest") == MANIFEST_PIN,
            "Registration stage or exact source pin changed")
    manifest = pinned_json(root, MANIFEST_PIN)
    validate_staged_native_manifest(root, manifest)
    by_name = {e["candidate_version"]: e for e in manifest["entries"]}
    adapters = index.get("entries", [])
    require(index.get("entry_count") == len(adapters) == len(by_name) == 18
            and {e.get("target_name") for e in adapters} == set(by_name),
            "Registration differs from the exact 18 source identities")
    targets = {}
    for row in adapters:
        name = row["target_name"]
        e = copy.deepcopy(by_name[name])
        require(row.get("binding_candidate_sha256") == e["binding"]["sha256"],
                "Original source binding digest changed")
        target = {k: e[k] for k in IDENTITY + ("original_task_id",) + DIGESTS}
        target.update({
            "candidate_shape": "native_bilingual_body",
            "changed_fields": ["content_en", "content_zh"],
            "candidate": (row["execution_adapter"]["path"], row["execution_adapter"]["sha256"]),
            "source_frozen_candidate": (e["source"]["path"], e["source"]["sha256"]),
            "rollback": (e["rollback"]["path"], e["rollback"]["sha256"]),
            "qa_outbox": (e["qa"]["path"], e["qa"]["sha256"]),
            "native_source_entry": e,
            "native_registration_only": True,
            "release_ready": False,
            "requires_completed_parent": True,
        })
        validate_native_issuer_candidate(root, pinned_json(root, row["execution_adapter"]), target)
        targets[name] = target
    return targets


def validate_native_issuer_candidate(root: Path, candidate: dict, target: dict) -> None:
    e = target["native_source_entry"]
    validate_entry(root, e)
    require(all(candidate.get(k) == e[k] and target.get(k) == e[k]
                for k in IDENTITY + ("original_task_id",) + DIGESTS),
            "Native adapter or issuer tuple differs from the original source")
    require(candidate.get("schema_version") == "native_issuer_execution_adapter_v1"
            and candidate.get("action_class") == "cms_content_candidate"
            and candidate.get("execution_action_class") == "cms_write"
            and candidate.get("production_write_executed") is False
            and candidate.get("changed_fields") == target.get("changed_fields")
            == ["content_en", "content_zh"]
            and candidate.get("source_frozen_candidate") == e["source"]
            and candidate.get("source_binding") == e["binding"],
            "Native adapter channel, fields, stage or provenance differs")
    binding = pinned_json(root, e["binding"])
    baseline = pinned_json(root, e["baseline"])
    source = pinned_json(root, e["source"])
    desired = source[binding["original_body_source_key"]]
    record = {**baseline, **desired}
    expected = {
        "mode": "dry-run", "contentType": e["content_type"],
        "nextStatus": "published", "expectedUpdatedAt": e["expected_updated_at"],
        "record": record,
        "managedCandidate": {
            "taskId": e["task_id"], "actionId": e["action_id"],
            "candidateVersion": e["candidate_version"], "scope": e["scope"],
            "operation": "publish",
        },
    }
    require(set(desired) == FIELDS and candidate.get("request") == expected,
            "Native request changed CAS, row, retained values, body or managed identity")


def native_release_qa_matches(row: dict, target: dict) -> bool:
    """Binding-only PASS never substitutes for actual target release readiness."""
    e = target["native_source_entry"]
    return (row.get("release_ready") is True
            and row.get("review_scope") == "exact_body_release_with_protected_zero_write_preview"
            and row.get("source_candidate_path") == e["source"]["path"]
            and row.get("source_candidate_sha256") == e["source"]["sha256"]
            and row.get("allowed_fields") == ["content_en", "content_zh"]
            and row.get("record_id") == e["record_id"]
            and row.get("table") == e["table"])
