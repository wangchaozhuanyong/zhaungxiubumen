"""Proposed exact Blog target registration. This helper cannot issue permits."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

MANIFEST_PATH = "drafts/operations/fc-20260928-remaining186-blog-native-issuer-registration-v1/registration-candidate.json"
MANIFEST_SHA256 = "003f00ec6a06dfda8c394a98c4992183830e465ceebf88767b894c54a57ab46b"
TASK_ID = "fc-20260928-remaining186-existing-url-source-binding-v2"
FIELDS = ("content_en", "content_zh")
IDENTITIES = {
    "NO07": ("5a0322a0-0f58-4c28-a370-569428c13508", "modern-warm-minimalist-home-design-malaysia", "remaining186-no07-existing-url-bind-v2", "remaining186-no07-cms-combined-v2"),
    "NO08": ("9914e1fc-c475-42e0-8d11-9e92117a5e4f", "how-to-choose-renovation-contractor-kl", "remaining186-no08-existing-url-bind-v2", "remaining186-no08-cms-combined-v2"),
    "NO10": ("46faa278-295f-486d-9b90-263954993153", "renovation-materials-malaysia", "remaining186-no10-existing-url-bind-v2", "remaining186-no10-cms-combined-v2"),
}


def require(ok: bool, reason: str) -> None:
    if not ok:
        raise ValueError(reason)


def pinned_json(root: Path, pin: dict) -> dict:
    path = (root / str(pin.get("path", ""))).resolve()
    require(path.is_relative_to(root.resolve()) and path.is_file(), "Blog source outside project or missing")
    raw = path.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == pin.get("sha256"), "Blog frozen source changed")
    value = json.loads(raw)
    require(isinstance(value, dict), "Blog frozen source must be an object")
    return value


def load_remaining186_blog_registration(root: Path) -> dict:
    manifest = pinned_json(root, {"path": MANIFEST_PATH, "sha256": MANIFEST_SHA256})
    require(manifest.get("schema_version") == "remaining186_blog_native_issuer_registration_candidate_v1"
            and manifest.get("original_task_id") == TASK_ID
            and manifest.get("mode") == "REGISTRATION_ONLY_NO_PERMIT"
            and manifest.get("entry_count") == 3
            and manifest.get("production_authorized") is False
            and manifest.get("active_issuer_modified") is False
            and manifest.get("actual_edge_source_verified") is False
            and manifest.get("actual_native_admission") is False
            and manifest.get("release_ready") is False
            and manifest.get("protected_remote_preview") is None,
            "Blog manifest cannot declare native capability or permission")
    entries = manifest.get("entries")
    require(isinstance(entries, list) and len(entries) == 3, "Blog registration requires exactly three entries")
    targets = {}
    seen = set()
    for entry in entries:
        module = entry.get("module_id")
        require(module in IDENTITIES and module not in seen, "Blog module unknown or duplicate")
        seen.add(module)
        record_id, slug, action_id, version = IDENTITIES[module]
        expected = {
            "task_id": TASK_ID, "action_id": action_id, "candidate_version": version,
            "scope": f"flashcast.com.my:blog_posts:{record_id}:content_zh,content_en",
            "record_id": record_id, "slug": slug, "table": "blog_posts",
            "changed_fields": list(FIELDS),
        }
        require(entry.get("identity") == expected
                and entry.get("native_registration_only") is True
                and entry.get("actual_native_admission") is False
                and entry.get("release_ready") is False
                and entry.get("protected_preview") is None
                and entry.get("cms_save") is False,
                "Blog target identity or deny flags differ")
        pins = entry.get("sources")
        require(isinstance(pins, dict) and set(pins) == {"proposal", "candidate", "qa_blocked_outbox"},
                "Blog frozen source inventory differs")
        proposal = pinned_json(root, pins["proposal"])
        candidate = pinned_json(root, pins["candidate"])
        qa = pinned_json(root, pins["qa_blocked_outbox"])
        native = proposal.get("target", {})
        require(proposal.get("status") == "LOCAL_PROPOSAL_NOT_REGISTERED"
                and proposal.get("protected_preview_status") == "NOT_EXECUTED"
                and proposal.get("candidate_path") == pins["candidate"]["path"]
                and native.get("id") == record_id and native.get("slug") == slug
                and native.get("table") == "blog_posts" and native.get("contentType") == "blog"
                and native.get("taskId") == TASK_ID and native.get("actionId") == action_id
                and native.get("candidateVersion") == version and native.get("scope") == expected["scope"]
                and native.get("changedFields") == list(FIELDS)
                and native.get("sourceCandidateSha256") == pins["candidate"]["sha256"]
                and native.get("rollbackAllowed") is False,
                "Blog native proposal differs from frozen target")
        require(all(candidate.get(key) == expected[key] for key in
                    ("task_id", "action_id", "candidate_version", "scope", "record_id", "slug", "table"))
                and candidate.get("action_class") == "cms_content_candidate"
                and candidate.get("locked_channel_after_QA") == "cms_write"
                and candidate.get("modified_fields") == list(reversed(FIELDS))
                and candidate.get("execution", {}).get("cms_saved") is False
                and candidate.get("execution", {}).get("saved_id") is None
                and candidate.get("execution", {}).get("published") is False
                and candidate.get("execution", {}).get("precise_permit") is None,
                "Blog content candidate differs or was written")
        require(qa.get("action_id") == action_id and qa.get("candidate_version") == version
                and qa.get("scope") == expected["scope"]
                and qa.get("qa_result") == "HOLD_NEEDS_WORK"
                and qa.get("gate_status") == "HOLD_NEEDS_WORK",
                "Blog original R1 QA is not the frozen hold")
        targets[version] = {
            **expected,
            "candidate_shape": "native_remaining186_blog_registration",
            "candidate": (pins["candidate"]["path"], pins["candidate"]["sha256"]),
            "source_frozen_candidate": (pins["candidate"]["path"], pins["candidate"]["sha256"]),
            "qa_outbox": (pins["qa_blocked_outbox"]["path"], pins["qa_blocked_outbox"]["sha256"]),
            "native_registration_only": True,
            "release_ready": False,
            "production_authorized": False,
            "requires_completed_parent": True,
            "native_source_manifest": MANIFEST_PATH,
        }
    require(seen == set(IDENTITIES), "Blog exact registration set incomplete")
    return targets


def validate_remaining186_blog_candidate(root: Path, candidate: dict, target: dict) -> None:
    frozen = load_remaining186_blog_registration(root).get(target.get("candidate_version"))
    require(frozen is not None and target == frozen, "Blog target must remain exact registration-only")
    source = pinned_json(root, {"path": target["candidate"][0], "sha256": target["candidate"][1]})
    require(candidate == source, "Blog candidate differs from frozen source")
