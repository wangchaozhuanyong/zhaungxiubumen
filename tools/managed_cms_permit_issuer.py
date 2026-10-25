#!/usr/bin/env python3
"""Issue one short-lived CMS permit only from fixed, verified release evidence.

This tool is an issuer, not a substitute for independent acceptance. Its credential is
injected by a protected operator process, never stored in the project.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from pathlib import Path
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from urllib.parse import urlparse
from uuid import uuid4

if __package__:
    from . import workflow_control as wc
else:
    import workflow_control as wc

ROOT = Path(__file__).resolve().parents[1]
SITE_ROOT = Path("<WEBSITE_PROJECT_ROOT>")
REPOSITORY = "wangchaozhuanyong/zhuangxiuwangzhan"
SUPABASE_HOST = 'example-project.supabase.co'
KEYCHAIN_SERVICE = "com.flashcast.managed-cms-permit-issuer"
KEYCHAIN_ACCOUNT = 'example-project'
QA_THREAD_ID = "example-native-11a474422a187c32"
OPERATIONS_THREAD_ID = "example-native-0d0689f4e3a4c895"
if __package__:
    from .native_cms_issuer_integration import (load_native_issuer_targets, validate_native_issuer_candidate, native_release_qa_matches)
else:
    sys.path.insert(0, str(ROOT))
    from tools.native_cms_issuer_integration import (load_native_issuer_targets, validate_native_issuer_candidate, native_release_qa_matches)

if __package__:
    from .native_repair_faq_registration import load_repair_faq_registration, validate_repair_faq_candidate
else:
    from tools.native_repair_faq_registration import load_repair_faq_registration, validate_repair_faq_candidate

if __package__:
    from .native_wave234_body_registration import load_wave234_body_registration, validate_wave234_body_candidate
else:
    from tools.native_wave234_body_registration import load_wave234_body_registration, validate_wave234_body_candidate

if __package__:
    from .native_remaining186_blog_registration import load_remaining186_blog_registration, validate_remaining186_blog_candidate
else:
    from tools.native_remaining186_blog_registration import load_remaining186_blog_registration, validate_remaining186_blog_candidate
if __package__:
    from .native_shop_children_body_registration import load_shop_children_body_registration, validate_shop_children_body_candidate
else:
    from tools.native_shop_children_body_registration import load_shop_children_body_registration, validate_shop_children_body_candidate

if __package__:
    from .native_five_source_projection_registration import load_five_source_projection_registration, validate_five_source_projection_candidate
else:
    from tools.native_five_source_projection_registration import load_five_source_projection_registration, validate_five_source_projection_candidate


if __package__:
    from .native_publisher_exact_registration import load_publisher_exact_registration, validate_publisher_registration_candidate
else:
    from tools.native_publisher_exact_registration import load_publisher_exact_registration, validate_publisher_registration_candidate


if __package__:
    from .publisher_native_sparse_admission import (load_targets as load_sparse_publisher_targets,
        validate_candidate_binding as validate_sparse_publisher_candidate,
        qa_outbox_matches as sparse_publisher_release_qa_matches, require_actual_release_qa_pin)
else:
    from tools.publisher_native_sparse_admission import (load_targets as load_sparse_publisher_targets,
        validate_candidate_binding as validate_sparse_publisher_candidate,
        qa_outbox_matches as sparse_publisher_release_qa_matches, require_actual_release_qa_pin)


if __package__:
    from .paid_three_page_bounded_cms import (english_kitchen_en2_targets,
        validate_english_kitchen_en2_candidate, two_original_material_targets,
        validate_two_original_material_candidate)
else:
    from paid_three_page_bounded_cms import (english_kitchen_en2_targets,
        validate_english_kitchen_en2_candidate, two_original_material_targets,
        validate_two_original_material_candidate)


TARGETS = {}

# ORG-020 exact field-patch targets. QA pins stay absent until the fixed QA
# produces actual per-action evidence; registration alone cannot issue permits.
ORG020_TARGETS = {}
TARGETS.update(ORG020_TARGETS)

NATIVE_TARGETS = {}
if set(TARGETS) & set(NATIVE_TARGETS):
    raise ValueError("Native target conflicts with a historical issuer identity")
TARGETS.update(NATIVE_TARGETS)

REPAIR_FAQ_TARGETS = {}
if set(TARGETS) & set(REPAIR_FAQ_TARGETS):
    raise ValueError("Repair FAQ registration collides with an existing target")
TARGETS.update(REPAIR_FAQ_TARGETS)

WAVE234_BODY_TARGETS = {}
if set(TARGETS) & set(WAVE234_BODY_TARGETS):
    raise ValueError("Wave234 body registration collides with an existing target")
TARGETS.update(WAVE234_BODY_TARGETS)

REMAINING186_BLOG_TARGETS = {}
if set(TARGETS) & set(REMAINING186_BLOG_TARGETS):
    raise ValueError("Remaining186 Blog registration collides with an existing target")
TARGETS.update(REMAINING186_BLOG_TARGETS)

SHOP_CHILDREN_BODY_TARGETS = {}
if set(TARGETS) & set(SHOP_CHILDREN_BODY_TARGETS):
    raise ValueError("Shop/children registration collides with an existing target")
TARGETS.update(SHOP_CHILDREN_BODY_TARGETS)

FIVE_PROJECTION_TARGETS = {}
if set(TARGETS) & set(FIVE_PROJECTION_TARGETS):
    raise ValueError("Five-source projection registration collides with an existing target")
TARGETS.update(FIVE_PROJECTION_TARGETS)

PUBLISHER_EXACT_TARGETS = {}
if set(TARGETS) & set(PUBLISHER_EXACT_TARGETS):
    raise ValueError('Publisher tuple collides with a historical target')
TARGETS.update(PUBLISHER_EXACT_TARGETS)

# Separate successor identities; the old three registrations remain immutable.
SPARSE_PUBLISHER_TARGETS = {}
if set(TARGETS) & set(SPARSE_PUBLISHER_TARGETS):
    raise ValueError('Sparse publisher successor collides with a historical target')
TARGETS.update(SPARSE_PUBLISHER_TARGETS)


def _available_english_kitchen_en2_targets(root: Path) -> dict:
    """An invalid EN2 input disables only EN2; older targets remain readable."""
    try:
        return english_kitchen_en2_targets(root)
    except (OSError, ValueError, TypeError, KeyError, wc.WorkflowError):
        return {}


ENGLISH_KITCHEN_EN2_TARGETS = {}
if set(TARGETS) & set(ENGLISH_KITCHEN_EN2_TARGETS):
    raise ValueError('English kitchen EN2 target collides with a historical target')
TARGETS.update(ENGLISH_KITCHEN_EN2_TARGETS)


def _available_two_original_material_targets(root: Path) -> dict:
    """No formal publisher goal means no two-material Save namespace."""
    try:
        return two_original_material_targets(root)
    except (OSError, ValueError, TypeError, KeyError, wc.WorkflowError):
        return {}


TWO_ORIGINAL_MATERIAL_TARGETS = {}
if set(TARGETS) & set(TWO_ORIGINAL_MATERIAL_TARGETS):
    raise ValueError("Two original material targets collide with historical targets")
TARGETS.update(TWO_ORIGINAL_MATERIAL_TARGETS)

# One new original publisher action. This registration only makes the exact
# namespace discoverable; existing assistant QA, policy and protected permit
# gates still decide whether it can be executed.
CONDO_FAQ_V7_NAME = "condo-faq-v7-current-native-two-fields-20261014"
CONDO_FAQ_V7_SHAPE = "condo_faq_current_native_v7"
CONDO_FAQ_V7_BASE = "drafts/publishing/fc-20261014-condo-faq-v7-cms-publishing-v1/"
CONDO_FAQ_V7_TARGET = {
    "task_id": "fc-20261014-condo-faq-v7-cms-publishing-v1",
    "action_id": "publish-condo-faq-v7-current-native-20261014-v1",
    "candidate_version": "publishing-condo-faq-v7-current-native-v1-20261014",
    "scope": "company.example:blog_posts/701c2406-ba5b-4bbc-8d47-f985047d5c81:content_en,content_zh",
    "record_id": "701c2406-ba5b-4bbc-8d47-f985047d5c81",
    "slug": "condo-renovation-management-approval-malaysia",
    "table": "blog_posts", "content_type": "blog",
    "changed_fields": ["content_en", "content_zh"],
    "expected_updated_at": "2026-09-26T18:34:55.816725+00:00",
    "observed_version": 1,
    "execution_owner": "publishing",
    "execution_thread_id": "example-native-f4ba16119c32b000",
    "candidate_shape": CONDO_FAQ_V7_SHAPE,
    "candidate": (CONDO_FAQ_V7_BASE + "publishing-condo-v7-current-native-candidate-v1.json",
                  "5a717a01629d62bf5fa161c4c377a0467439edf00c6d47143311dc3e755ee821"),
    "source_frozen_candidate": (CONDO_FAQ_V7_BASE + "publishing-condo-v7-current-native-candidate-v1.json",
                                "5a717a01629d62bf5fa161c4c377a0467439edf00c6d47143311dc3e755ee821"),
    "rollback": ("backups/fc-20261014-condo-faq-v7-cms-publishing-v1/condo.before-full-native-record-v1.json",
                 "8a4b333aeb573e461f923b1f954366f8a6fdc9237b95c43dc4cebdf9bee50bed"),
    "rollback_allowed": False,
    "qa_outbox": None,
    "payload_sha256": "bd4c49e6c375208f527e703aaf8a217d7cd8c5f380f7ff337a3e006c0fd2f409",
}
if CONDO_FAQ_V7_NAME in TARGETS:
    raise ValueError("Exact condo FAQ action collides with a registered target")
TARGETS[CONDO_FAQ_V7_NAME] = CONDO_FAQ_V7_TARGET

# The owner-authorized two-page batch has a new single-field publishing goal.
# Its closed Ads parent and older builtin permits are references, never a grant.
BUILTIN_WARDROBE_NAME = "builtin-wardrobe-layout-content-zh-20261014-v1"
BUILTIN_WARDROBE_SHAPE = "builtin_wardrobe_one_field_registration_v1"
BUILTIN_WARDROBE_BASE = "drafts/publishing/fc-20260920-google-ads-rm100-budget-plan/two-quality-pages-20261014-v1/"
BUILTIN_WARDROBE_BINDING = (
    "logs/handoffs/2026-10-14-builtin-wardrobe-registration-v1/system-development-candidate-v1/"
    "exact-registration-binding.json", "6f2383aa27ba012e783b18b97912cfa8b01c6e3f9b4a0119a43f4fbf49236419")
BUILTIN_WARDROBE_GOAL = (
    "logs/handoffs/2026-10-14-builtin-wardrobe-registration-v1/system-development-candidate-v1/"
    "goal-input.json", "3a8ba4375bdae2e7bce3f589c3fe49d7c6aba00a0ab9a0d19b6fe04d166aa99b")
BUILTIN_WARDROBE_TARGET = {
    "task_id": "fc-20261014-builtin-wardrobe-layout-cms-publication-v1",
    "action_id": "publish-builtin-wardrobe-layout-20261014-v1",
    "candidate_version": "two-quality-pages-20261014-v1",
    "scope": "company.example:services/b401a610-a4dc-4a0b-a7e0-efcac6c81d71:content_zh",
    "record_id": "b401a610-a4dc-4a0b-a7e0-efcac6c81d71",
    "slug": "builtin", "table": "services", "content_type": "service",
    "changed_fields": ["content_zh"],
    "expected_updated_at": "2026-10-10T16:08:22.003433+00:00", "observed_version": 1,
    "execution_owner": "publishing",
    "execution_thread_id": "example-native-f4ba16119c32b000",
    "candidate_shape": BUILTIN_WARDROBE_SHAPE,
    "candidate": (BUILTIN_WARDROBE_BASE + "builtin.candidate-full-native-record.json",
                  "35c0d78e6ae84774c94b011c0f8be52f5ba199c08b09dc762a2fdbd64982610e"),
    "rollback": ("backups/fc-20260920-google-ads-rm100-budget-plan/"
                 "two-quality-pages-20261014-v1/builtin.before-full-native-response.json",
                 "1093a1c0541b877f5772528599532042b1ad57dff8138a67367290da7f9a033f"),
    "rollback_allowed": False, "qa_outbox": None,
    "payload_sha256": "ac15ee387764d4a7420edc106cc2b078b3f28ce273d608664cf18ef00ec57e83",
    "registration_binding": BUILTIN_WARDROBE_BINDING, "goal_contract": BUILTIN_WARDROBE_GOAL,
}
if BUILTIN_WARDROBE_NAME in TARGETS:
    raise ValueError("Exact new builtin wardrobe action collides with a registered target")
TARGETS[BUILTIN_WARDROBE_NAME] = BUILTIN_WARDROBE_TARGET

def _available_shop_office_six_targets(root: Path) -> dict:
    # A malformed new namespace must fail closed without disabling historical reads.
    from tools.shop_office_six_field_execution import targets
    try:
        return targets(root)
    except (OSError, ValueError, TypeError, KeyError, wc.WorkflowError):
        return {}


SHOP_OFFICE_SIX_TARGETS = {}
if set(TARGETS) & set(SHOP_OFFICE_SIX_TARGETS):
    raise ValueError('Exact new six-field namespace collides with a historical target')
TARGETS.update(SHOP_OFFICE_SIX_TARGETS)


BLOG_TARGETS = frozenset()
BLOG_MEDIA_TARGETS = frozenset()
PARENT_RUN_TARGETS = {}


class PermitEvidenceError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise PermitEvidenceError(message)


def load_protected_issuer_secret() -> str:
    """Read the issuer credential without putting it in arguments or logs.

    A protected operator may inject the environment variable. On the local Mac,
    the exact Supabase project's dedicated login-Keychain item is a fallback.
    Neither path creates, rotates, or prints a credential.
    """
    secret = os.environ.get("MANAGED_CMS_PERMIT_ISSUER_SECRET", "")
    if secret:
        require(len(secret) >= 32, "Protected issuer secret is too short")
        return secret
    require(sys.platform == "darwin", "Protected issuer secret is not configured")
    try:
        result = subprocess.run(
            ["/usr/bin/security", "find-generic-password", "-a", KEYCHAIN_ACCOUNT,
             "-s", KEYCHAIN_SERVICE, "-w"],
            capture_output=True, text=True, check=False, timeout=30,
        )
    except subprocess.TimeoutExpired as error:
        raise PermitEvidenceError("Protected Keychain lookup timed out") from error
    require(result.returncode == 0, "Protected issuer secret is not configured in Keychain")
    secret = result.stdout.rstrip("\n")
    require(len(secret) >= 32, "Protected Keychain issuer secret is too short")
    return secret


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    require(parsed.tzinfo is not None, "Evidence timestamp must have a timezone")
    return parsed.astimezone(timezone.utc)


def exact_file(root: Path, item: tuple[str, str]) -> Path:
    path, digest = item
    resolved = (root / path).resolve()
    require(resolved.is_relative_to(root.resolve()) and resolved.is_file(), f"Evidence file missing: {path}")
    require(sha256_file(resolved) == digest, f"Evidence file changed: {path}")
    return resolved


def rollback_parent_binding(target_name: str, operation: str,
                            parent_permit_id: str | None, parent_run_id: int | None) -> dict:
    if operation != "rollback":
        require(not parent_permit_id and parent_run_id is None,
                "Publish cannot reuse a rollback parent")
        return {"parentPermitId": None}
    require(bool(parent_permit_id) and parent_run_id is not None and parent_run_id > 0,
            "Rollback requires the completed parent permit and run")
    binding = {"parentPermitId": parent_permit_id}
    if target_name in PARENT_RUN_TARGETS:
        binding["parentRunId"] = parent_run_id
    return binding


def validate_completed_parent_status(status: dict, target: dict,
                                     parent_permit_id: str, parent_run_id: int) -> None:
    """Fail closed against the protected permit status before bound rollback."""
    require(status.get("permitId") == parent_permit_id
            and status.get("status") == "completed"
            and status.get("operation") == "publish"
            and status.get("taskId") == target["task_id"]
            and status.get("actionId") == target["action_id"]
            and status.get("candidateVersion") == target["candidate_version"]
            and status.get("githubRunId") == parent_run_id
            and status.get("savedId") == target["record_id"]
            and bool(status.get("savedUpdatedAt")),
            "Rollback parent permit is not the completed exact publish run")


def validate_condo_faq_v7_candidate(root: Path, candidate: dict, target: dict) -> None:
    """Read one frozen publisher package; this grants no permit or Save."""
    root = Path(root).resolve()
    require(root == ROOT.resolve() and target == CONDO_FAQ_V7_TARGET,
            "Exact original condo FAQ target and company root required")
    def frozen(path: str, sha: str) -> bytes:
        observed = wc.file_digest(root, path)
        require(observed["sha256"] == sha, "Frozen condo FAQ evidence changed: " + path)
        return wc.safe_path(root, path).read_bytes()
    canonical = json.loads(frozen(*target["candidate"]))
    require(candidate == canonical and candidate.get("schema_version") == "current-native-answer-only-CMS-candidate/1",
            "Exact current publisher candidate bytes required")
    frozen(CONDO_FAQ_V7_BASE + "frozen-exact-production-tuple-v1.json",
           "9e5915c4df6f37567611312e91772e2f275449be638d6ceda67658e0ca7b2fde")
    authority = frozen("logs/handoffs/2026-10-14-assistant1-v7-remaining-followthrough-1818-v1/"
                       "original-human-CMS-publishing-authority-native-context.json",
                       "463bbf764c280221a55e16fb17023dcce94f2041ba3984001cf570a91abe405b")
    contract = frozen("logs/handoffs/2026-10-14-condo-faq-v7-publishing-child-v1/child-goal-input.json",
                      "fa7aae6bd9791360386c9ffb6eb049ed1e868005993a50536dc2708553219967")
    before_raw = frozen(CONDO_FAQ_V7_BASE + "condo.current-full-native-record-v1.json",
                        "8a4b333aeb573e461f923b1f954366f8a6fdc9237b95c43dc4cebdf9bee50bed")
    backup_raw = frozen(target["rollback"][0], target["rollback"][1])
    read = json.loads(frozen(CONDO_FAQ_V7_BASE + "actual-current-native-read-source-v1.json",
                            "92a4a0d15df9831607ab76d3dea4bdfb4e14d388d046e489c571194fb54d2eea"))
    payload = json.loads(frozen(CONDO_FAQ_V7_BASE + "write-only-two-native-fields-v1.json",
                                "11f87d04f38b178904a4a3f9cab92a02493ded170b8688ff7e2f40bae79d6548"))
    wire = frozen(CONDO_FAQ_V7_BASE + "actual-canonical-two-field-payload-wire.json", target["payload_sha256"])
    checks = json.loads(frozen(CONDO_FAQ_V7_BASE + "actual-native-diff-and-serialization-checks-v1.json",
                                "e944675e49725505fd3558be1e4c4b04215967344d2daab65b65977d73ac3443"))
    span = json.loads(frozen(CONDO_FAQ_V7_BASE + "answer-only-native-span-diff-v1.json",
                              "92c46694e9c0a20138431b941f9a04e28520610106035eb7a7a680231b0f5d29"))
    restore = json.loads(frozen(CONDO_FAQ_V7_BASE + "only-two-field-restore-preparation-v1.json",
                                 "4a904f6d15420686ba1fbed71e1fa2620995c7dfda66fa0df9841683a5557d8f"))
    before = json.loads(before_raw)
    exact = {"task_id": target["task_id"], "action_id": target["action_id"],
             "candidate_version": target["candidate_version"], "scope": target["scope"],
             "record_id": target["record_id"], "slug": target["slug"],
             "table": target["table"], "content_type": target["content_type"],
             "execution_owner": target["execution_owner"],
             "execution_thread_id": target["execution_thread_id"],
             "expected_updated_at": target["expected_updated_at"],
             "expected_version": target["observed_version"],
             "payload_sha256": target["payload_sha256"]}
    require(all(candidate.get(key) == value for key, value in exact.items())
            and candidate.get("action_class") == "cms_content_candidate"
            and candidate.get("execution_action_class") == "cms_write"
            and candidate.get("fixed_chat_task_id") == target["execution_thread_id"]
            and candidate.get("changed_fields") == target["changed_fields"]
            and set(candidate.get("desired_fields", {})) == set(target["changed_fields"])
            and candidate.get("new_permit") == candidate.get("protected_preview") == candidate.get("Save") == 0
            and candidate.get("published") is False
            and candidate.get("parent_goal_closed") is False,
            "Exact original task/action/row/two-field current candidate required")
    require(candidate.get("backup") == wc.file_digest(root, target["rollback"][0])
            and candidate.get("actual_current_native_record") == wc.file_digest(
                root, CONDO_FAQ_V7_BASE + "condo.current-full-native-record-v1.json")
            and candidate.get("only_write_projection") == wc.file_digest(
                root, CONDO_FAQ_V7_BASE + "write-only-two-native-fields-v1.json")
            and candidate.get("child_goal_contract") == wc.file_digest(
                root, "logs/handoffs/2026-10-14-condo-faq-v7-publishing-child-v1/child-goal-input.json")
            and backup_raw == before_raw and len(before) == 23
            and before.get("id") == target["record_id"] and before.get("slug") == target["slug"]
            and before.get("status") == "published" and before.get("version") == target["observed_version"]
            and before.get("updated_at") == target["expected_updated_at"],
            "Actual current 23-field row, authorization contract or physical backup changed")
    require(read.get("task_id") == target["task_id"] and read.get("request_method") == "GET"
            and read.get("http_status") == 200 and read.get("record_id") == target["record_id"]
            and read.get("slug") == target["slug"] and read.get("field_count") == 23
            and read.get("version") == before["version"]
            and read.get("raw_updated_at") == before["updated_at"]
            and read.get("network_buffer_truncated") is False
            and read.get("credentials_or_headers_read") is False
            and read.get("Save") == read.get("new_permit") == 0,
            "Actual native before-source observation changed")
    require(payload == candidate["desired_fields"] and set(payload) == set(target["changed_fields"])
            and hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True,
                                          separators=(",", ":")).encode()).hexdigest() == target["payload_sha256"]
            and hashlib.sha256(wire).hexdigest() == target["payload_sha256"]
            and json.loads(wire) == payload
            and wc.sha256_value(before) == candidate.get("baseline_fields_sha256")
            and wc.sha256_value({key: before[key] for key in candidate["retained_business_fields"]})
                == candidate.get("retained_business_fields_sha256")
            and set(before) - set(target["changed_fields"])
                == set(candidate.get("retained_including_metadata_fields", [])),
            "Exact native two-field wire, CAS baseline or retained projection changed")
    projected = json.loads(frozen(CONDO_FAQ_V7_BASE + "desired-full-native-projection-v1.json",
                                  "fbabb060787eb902ae4116696a00b87fe87f7280f3336518650b2e23264ec061"))
    require(projected == {**before, **payload}
            and span.get("all_other_full_field_bytes_preserved") is True
            and set(span.get("changed_native_fields", [])) == set(target["changed_fields"])
            and len(span.get("spans", [])) == 2
            and checks.get("status") == "PASS_BOUNDED_ACTUAL_PAYLOAD_SERIALIZATION_AND_MINIMAL_NATIVE_DIFF"
            and all(value is True for value in checks.get("checks", {}).values())
            and checks.get("actual_payload_sha256") == target["payload_sha256"]
            and checks.get("HTTP_requests") == checks.get("Save") == checks.get("new_permit") == 0
            and restore.get("before_full_backup") == wc.file_digest(root, target["rollback"][0])
            and restore.get("restore_field_count") == 2
            and set(restore.get("restore_fields", {})) == set(target["changed_fields"])
            and restore.get("production_restore_executable") is False
            and restore.get("applied") is False
            and bool(authority) and bool(contract),
            "Actual answer-only diff, local checks or two-field restore preparation changed")


def validate_builtin_wardrobe_one_field_candidate(root: Path, candidate: dict, target: dict) -> None:
    """Bind only the owner-approved new batch; neither history nor metadata permits Save."""
    root = Path(root).resolve()
    require(root == ROOT.resolve() and target == BUILTIN_WARDROBE_TARGET,
            "Exact builtin wardrobe project and registered target required")
    binding = json.loads(exact_file(root, BUILTIN_WARDROBE_BINDING).read_text())
    goal = json.loads(exact_file(root, BUILTIN_WARDROBE_GOAL).read_text())
    expected = {"task_id": target["task_id"], "candidate_version": target["candidate_version"],
                "action_id": target["action_id"], "scope": target["scope"],
                "record_id": target["record_id"], "table": target["table"],
                "changed_fields": target["changed_fields"], "execution_owner": "publishing",
                "execution_thread_id": target["execution_thread_id"],
                "expected_updated_at": target["expected_updated_at"],
                "expected_version": target["observed_version"],
                "payload_sha256": target["payload_sha256"]}
    require(binding.get("schema") == "builtin-wardrobe-exact-registration-binding/v1"
            and all(binding.get(key) == value for key, value in expected.items())
            and binding.get("parent_reference_task_id") == "fc-20260920-google-ads-rm100-budget-plan"
            and binding.get("action_class") == "cms_write"
            and binding.get("production_write_allowed") is False
            and binding.get("permit_issued") is False and binding.get("CMS_Save") is False
            and goal.get("original_parent_reference_task_id") == binding["parent_reference_task_id"]
            and goal.get("primary_owner") == "paid-growth-data"
            and goal.get("responsible_assistant") == "operations-assistant-2"
            and goal.get("producer_departments") == ["paid-growth-data", "publishing"]
            and goal.get("authorized_scope") == [target["scope"]]
            and goal.get("required_execution_actions") == [{"action_id": target["action_id"],
                 "action_class": "cms_write", "scope": target["scope"], "department": "publishing"}]
            and goal.get("source_mode") == "owner_direct"
            and goal.get("production_write_allowed") is False
            and goal.get("external_permission_issued") is False
            and goal.get("CMS_Save") is False,
            "New single-field goal or original owner/executor binding differs")
    sources = binding.get("source")
    required = {"actual-builtin-exact-admission-result.json", "exact-new-builtin-execution-identity.json",
                "original-human-authority-native-fragment.json", "field-preparation-selfchecks.json",
                "actual-native-field-serialization-proof.json", "actual-current-native-read-source.json",
                "builtin.current-native-response.json", "builtin.candidate-full-native-record.json",
                "write-only-content-zh.json", "exact-field-rollback-plan-NOT-ADMITTED.json",
                "protected-dry-run-request-PREPARED-NOT-SENT.json",
                "protected-wire-serialized-NOT-SENT.json", "observed-parent-reference-status.json",
                "physical_before_backup"}
    require(isinstance(sources, dict) and set(sources) == required,
            "Only the original current builtin batch evidence may enter registration")
    for item in (*sources.values(), binding["original_human_authority"],
                 binding["actual_native_human_page"], binding["new_task_request_adapter"]):
        require(wc.file_digest(root, item["path"]) == item,
                "Exact original builtin source changed")
    def source(name):
        return json.loads(wc.safe_path(root, sources[name]["path"]).read_text())
    identity, admission = source("exact-new-builtin-execution-identity.json"), source("actual-builtin-exact-admission-result.json")
    before, after = source("builtin.current-native-response.json"), source("builtin.candidate-full-native-record.json")
    backup = source("physical_before_backup")
    patch = source("write-only-content-zh.json")
    read = source("actual-current-native-read-source.json")
    checks, wire = source("field-preparation-selfchecks.json"), source("actual-native-field-serialization-proof.json")
    parent = source("observed-parent-reference-status.json")
    original_request = source("protected-dry-run-request-PREPARED-NOT-SENT.json")
    adapted = json.loads(wc.safe_path(root, binding["new_task_request_adapter"]["path"]).read_text())
    human = json.loads(wc.safe_path(root, binding["original_human_authority"]["path"]).read_text())
    native = json.loads(wc.safe_path(root, binding["actual_native_human_page"]["path"]).read_text())
    selected = {item.get("id"): item for turn in native.get("turns", [])
                for item in turn.get("items", []) if item.get("type") == "userMessage"}
    require(human.get("source_thread_id") == native.get("thread", {}).get("id")
            == "example-native-0bec6d516b372cb9"
            and selected.get("example-native-8b2eedaf7db63344") == human.get("message")
            and selected.get("example-native-052c3570db5757e7") == human.get("registration_authorization")
            and "授权这两部门完成两页改进" in human["message"]["content"][0]["text"]
            and "授权仅修本批登记" in human["registration_authorization"]["content"][0]["text"]
            and goal.get("human_authorization", {}).get("evidence_path") == binding["original_human_authority"]["path"]
            and goal["human_authorization"].get("message_id") == human["message"]["id"],
            "Original two-page authority and exact registration-only answer required")
    require(identity.get("task_id") == binding["parent_reference_task_id"]
            and identity.get("action_id") == target["action_id"]
            and identity.get("scope") == target["scope"]
            and identity.get("fields") == ["content_zh"]
            and identity.get("payload_sha256") == target["payload_sha256"]
            and admission.get("status") == "REJECTED_BY_ACTUAL_LOCAL_NAMESPACE_CONSUMER"
            and admission.get("matching_current_batch_targets") == []
            and admission.get("permit_issued") is False and admission.get("Save") == 0
            and parent.get("task_id") == binding["parent_reference_task_id"]
            and parent.get("current_state") == "closed" and parent.get("goal_delivery") is None
            and parent.get("parent_reopened_or_modified") is False,
            "Old parent and namespace rejection may be cited, never reused as a current grant")
    require(candidate == after and len(before) == len(after) == len(backup) == 30
            and before == backup and before.get("id") == after.get("id") == target["record_id"]
            and before.get("slug") == after.get("slug") == target["slug"]
            and before.get("status") == after.get("status") == "published"
            and before.get("version") == after.get("version") == target["observed_version"]
            and before.get("updated_at") == after.get("updated_at") == target["expected_updated_at"]
            and {key for key in before if before[key] != after[key]} == {"content_zh"}
            and patch == {"content_zh": after["content_zh"]}
            and hashlib.sha256(json.dumps(patch, ensure_ascii=False, sort_keys=True,
                            separators=(",", ":")).encode()).hexdigest() == target["payload_sha256"],
            "One native content_zh change, full 30-field before backup and exact payload required")
    require(read.get("method") == "GET" and read.get("status") == 200
            and read.get("record_id") == target["record_id"] and read.get("field_count") == 30
            and read.get("updated_at") == target["expected_updated_at"]
            and read.get("credentials_or_headers_read") is False and read.get("Save") == 0
            and all(value is True for value in checks.get("checks", {}).values())
            and all(value is True for value in wire.get("checks", {}).values())
            and wire.get("all_passed") is True and wire.get("remote_request_sent") is False
            and wire.get("permit_issued") is False and wire.get("Save") == 0,
            "Current native observation and local serialization must remain zero-write")
    old_managed, new_managed = original_request.get("managedCandidate"), adapted.get("managedCandidate")
    require(original_request.get("record") == adapted.get("record") == after
            and {key: value for key, value in original_request.items() if key != "managedCandidate"}
                == {key: value for key, value in adapted.items() if key != "managedCandidate"}
            and isinstance(old_managed, dict) and isinstance(new_managed, dict)
            and old_managed.get("taskId") == binding["parent_reference_task_id"]
            and new_managed == {**old_managed, "taskId": target["task_id"]}
            and adapted.get("mode") == "dry-run"
            and adapted.get("expectedUpdatedAt") == target["expected_updated_at"]
            and binding["new_task_request_adapter"]["path"].endswith("NOT-SENT.json"),
            "Only the new task ID may change in the unsent protected request adapter")


def validate_candidate_binding(candidate: dict, target: dict, *, root: Path | None = None) -> None:
    """Bind newly added targets to one approved row and its exact field set."""
    evidence_root = Path(root) if root is not None else ROOT
    shape = target.get("candidate_shape")
    if shape == 'professional_cms_source_selfcheck_v1':
        from professional_cms_issuer import candidate as validate_professional
        validate_professional(evidence_root, candidate, target)
        return
    if shape == 'owner_authorized_shop_office_six_field_v4':
        from tools.shop_office_six_field_execution import validate_candidate
        validate_candidate(evidence_root, candidate, target)
        return
    if shape == CONDO_FAQ_V7_SHAPE:
        validate_condo_faq_v7_candidate(evidence_root, candidate, target)
        return
    if shape == BUILTIN_WARDROBE_SHAPE:
        validate_builtin_wardrobe_one_field_candidate(evidence_root, candidate, target)
        return
    if shape == "english_kitchen_en2_exact":
        validate_english_kitchen_en2_candidate(evidence_root, candidate, target)
        return
    if shape == "two_original_material_body_registration_only_v1":
        validate_two_original_material_candidate(evidence_root, candidate, target)
        return
    from paid_three_page_bounded_cms import MODEL as bounded_model, targets as bounded_targets, doc as bounded_doc
    if shape == bounded_model:
        exact = bounded_targets(evidence_root).get(target.get("action_id"))
        require(exact == target and candidate == bounded_doc(evidence_root, target["bounded_row"]["candidate"]),
                "Original T3 exact full-row candidate source changed")
        return
    if shape == 'native_publisher_sparse_admission':
        try:
            validate_sparse_publisher_candidate(evidence_root, candidate, target)
        except ValueError as error:
            raise PermitEvidenceError(str(error)) from error
        return
    if shape == 'native_publisher_registration':
        try:
            validate_publisher_registration_candidate(evidence_root, candidate, target)
        except ValueError as error:
            raise PermitEvidenceError(str(error)) from error
        return
    if shape == "native_five_projection_registration":
        try:
            validate_five_source_projection_candidate(evidence_root, candidate, target)
        except ValueError as error:
            raise PermitEvidenceError(str(error)) from error
        return
    if shape == "native_shop_children_body_registration":
        try:
            validate_shop_children_body_candidate(evidence_root, candidate, target)
        except ValueError as error:
            raise PermitEvidenceError(str(error)) from error
        return
    if shape == "native_wave234_body_registration":
        try:
            validate_wave234_body_candidate(evidence_root, candidate, target)
        except ValueError as error:
            raise PermitEvidenceError(str(error)) from error
        return
    if shape == "native_remaining186_blog_registration":
        try:
            validate_remaining186_blog_candidate(evidence_root, candidate, target)
        except ValueError as error:
            raise PermitEvidenceError(str(error)) from error
        return
    if shape == "native_repair_faq_registration":
        try:
            validate_repair_faq_candidate(evidence_root, candidate, target)
        except ValueError as error:
            raise PermitEvidenceError(str(error)) from error
        return
    if shape == "native_bilingual_body":
        try:
            validate_native_issuer_candidate(evidence_root, candidate, target)
        except ValueError as error:
            raise PermitEvidenceError(str(error)) from error
        return
    if not shape:
        return
    if shape == "org020_field_patch":
        source = json.loads(exact_file(evidence_root, target["source_frozen_candidate"]).read_text())
        baseline = json.loads(exact_file(evidence_root, target["rollback"]).read_text())
        fields = set(target["changed_fields"])
        projection = target["baseline_projection_fields"]
        require(source.get("task_id") == target["task_id"]
                and source.get("record_id") == target["record_id"] == baseline.get("id")
                and source.get("table") == target["table"]
                and source.get("scope") == target["scope"]
                and source.get("action_class") == "cms_content_candidate"
                and source.get("production_write_executed") is False
                and set(source.get("changed_fields", [])) == fields
                and set(source.get("desired_fields", {})) == fields
                and source.get("baseline_projection_fields") == projection
                and source.get("expected_updated_at") == baseline.get("updated_at") == target["expected_updated_at"]
                and source.get("baseline_fields_sha256") == target["baseline_fields_sha256"]
                and wc.sha256_value({key: baseline.get(key) for key in projection}) == target["baseline_fields_sha256"]
                and source.get("desired_fields_sha256") == target["desired_fields_sha256"]
                and wc.sha256_value(source.get("desired_fields")) == target["desired_fields_sha256"],
                "Pinned ORG-020 frozen source, row, fields, hashes or CAS differs")
        require(candidate.get("task_id") == target["task_id"]
                and candidate.get("action_id") == target["action_id"]
                and candidate.get("candidate_version") == target["candidate_version"]
                and candidate.get("record_id") == target["record_id"]
                and candidate.get("scope") == target["scope"]
                and candidate.get("action_class") == "cms_content_candidate"
                and candidate.get("production_write_executed") is False
                and set(candidate.get("changed_fields", [])) == fields
                and candidate.get("baseline_fields_sha256") == target["baseline_fields_sha256"]
                and candidate.get("desired_fields_sha256") == target["desired_fields_sha256"],
                "Pinned ORG-020 execution candidate identity or field digest differs")
        if target["table"] == "faqs":
            require(source.get("request") is None
                    and candidate.get("source_frozen_candidate_path") == target["source_frozen_candidate"][0]
                    and candidate.get("source_frozen_candidate_sha256") == target["source_frozen_candidate"][1]
                    and candidate.get("original_candidate_version") == source.get("candidate_version")
                    and candidate.get("original_action_id") == source.get("action_id")
                    and candidate.get("content_unchanged_from_frozen_v7") is True
                    and target["slug"] == f"faq-{target['record_id']}"
                    and fields == {"answer_en", "answer_zh"},
                    "FAQ execution adapter is not the frozen answer-only source")
        else:
            require(candidate.get("table") == target["table"]
                    and candidate.get("desired_fields") == source.get("desired_fields")
                    and candidate.get("action_id") == source.get("action_id")
                    and candidate.get("candidate_version") == source.get("candidate_version"),
                    "ORG-020 non-FAQ candidate differs from the frozen source")
        request = candidate.get("request") or {}
        record = request.get("record") or {}
        require(request.get("mode") == "dry-run"
                and request.get("contentType") == target["content_type"]
                and request.get("nextStatus") == baseline.get("status") == "published"
                and request.get("expectedUpdatedAt") == target["expected_updated_at"]
                and record.get("id") == target["record_id"]
                and record.get("updated_at") == target["expected_updated_at"]
                and record.get("status") == baseline.get("status")
                and set(record).issubset(set(baseline) | fields)
                and {key for key in record if record[key] != baseline.get(key)} == fields
                and all(record.get(key) == source["desired_fields"][key] for key in fields)
                and all(key in record for key in projection),
                "ORG-020 request differs from exact dry-run, unchanged baseline or field-only patch")
        if target["table"] == "faqs":
            managed = request.get("managedCandidate") or {}
            require(managed.get("taskId") == target["task_id"]
                    and managed.get("actionId") == target["action_id"]
                    and managed.get("candidateVersion") == target["candidate_version"]
                    and managed.get("scope") == target["scope"]
                    and managed.get("operation") == "publish",
                    "FAQ execution request managed tuple differs")
        elif target["table"] == "site_pages":
            require(record.get("page_key") == target["slug"],
                    "ORG-020 site page stable key differs")
        else:
            require(record.get("slug") == target["slug"],
                    "ORG-020 native slug differs")
        return
    if shape == "cms_media_row":
        fields = set(target["changed_fields"])
        require(candidate.get("task_id") == target["task_id"]
                and candidate.get("action_id") == target["action_id"]
                and candidate.get("candidate_version") == target["candidate_version"]
                and candidate.get("cms_row_id") == target["record_id"]
                and candidate.get("slug") == target["slug"]
                and candidate.get("scope") == target["scope"]
                and candidate.get("candidate_type") == "cms_content_candidate"
                and candidate.get("external_write_executed") is False
                and candidate.get("cms_saved_id") is None
                and candidate.get("body_and_links_unchanged") is True
                and set(candidate.get("allowed_fields", [])) == fields
                and set(candidate.get("field_diff", {})) == fields
                and set(candidate.get("desired_fields", {})) == fields
                and all(candidate["field_diff"][key].get("after") == candidate["desired_fields"][key]
                        for key in fields),
                "Pinned Blog media candidate identity, fields or unpublished status differs")
        return
    require(candidate.get("task_id") == target["task_id"]
            and candidate.get("action_id") == target["action_id"]
            and candidate.get("candidate_version") == target["candidate_version"]
            and candidate.get("published") is False,
            "Pinned candidate identity or unpublished status differs")
    expected_fields = set(target["changed_fields"])
    if shape == "record_key":
        key = candidate.get("record_key", {})
        require(key.get("id") == target["record_id"] and key.get("slug") == target["slug"]
                and candidate.get("scope") == target["scope"]
                and set(candidate.get("modified_fields", [])) == expected_fields
                and set(candidate.get("field_diff", {})) == expected_fields,
                "Pinned single-row candidate differs from exact target")
    elif shape == "items":
        require(set(candidate.get("modified_fields", [])) == expected_fields,
                "Pinned multi-row candidate has extra fields")
        items = candidate.get("items", [])
        matched = [item for item in items if item.get("cms_row_id") == target["record_id"]]
        require(len(matched) == 1 and matched[0].get("slug") == target["slug"]
                and matched[0].get("scope") == target["scope"]
                and set(matched[0].get("allowed_fields", [])) == expected_fields
                and set(matched[0].get("field_diff", {})) == expected_fields,
                "Pinned multi-row candidate differs from exact target")
    else:
        raise PermitEvidenceError("Unknown pinned candidate shape")


def structured_qa_outbox_matches(row: dict, target: dict) -> bool:
    """Require a per-target QA PASS inside a pinned V2.6 outbox."""
    if (target.get("candidate_shape") == "native_bilingual_body"
            and not native_release_qa_matches(row, target)):
        return False
    if target.get('candidate_shape') == 'native_publisher_sparse_admission' and not sparse_publisher_release_qa_matches(row, target):
        return False
    owner_review = (
        target.get("candidate_shape") == "cms_media_row"
        and row.get("gate_status") == "PASS_FOR_OWNER_REVIEW"
        and row.get("risk_level") == "R3"
        and row.get("approval_required") is True
    )
    if not (row.get("department") == "qa" and row.get("task_id") == target["task_id"]
            and row.get("status") == "completed"
            and (row.get("gate_status") == "PASS_FOR_AUTO_RELEASE"
                 and row.get("risk_level") != "R3" or owner_review)
            and row.get("verdict", row.get("qa_verdict")) == "pass"
            and row.get("action_id") == target["action_id"]
            and row.get("candidate_version") == target["candidate_version"]
            and row.get("candidate_sha256") == target["candidate"][1]
            and not any(str(item.get("priority", "")).upper() in {"P0", "P1"}
                        for item in row.get("blockers", []) if isinstance(item, dict))):
        return False
    if target["candidate_shape"] in {"record_key", "cms_media_row", "org020_field_patch", "native_bilingual_body", "native_publisher_sparse_admission"}:
        return row.get("scope") == target["scope"]
    return any(
        item.get("slug") == target["slug"]
        and item.get("record_id") == target["record_id"]
        and item.get("scope") == target["scope"]
        and item.get("action_id") == target["action_id"]
        and item.get("candidate_version") == target["candidate_version"]
        and item.get("candidate_sha256") == target["candidate"][1]
        and item.get("action_class") == "cms_content_candidate"
        and item.get("gate_status") == "PASS_FOR_AUTO_RELEASE"
        and item.get("qa_verdict") == "pass"
        for item in row.get("qa_subactions", []) if isinstance(item, dict)
    )


def _current_registered_targets(root: Path) -> dict:
    """Read current registrations; an import-time cache cannot prove a new tuple."""
    targets = dict(TARGETS)
    from professional_cms_issuer import targets as professional_targets
    for name in PROFESSIONAL_CMS_TARGETS:targets.pop(name,None)
    for name,target in professional_targets(root).items():
        require(name not in targets, "Professional target collision")
        targets[name]=target
    loaders = (load_native_issuer_targets, load_repair_faq_registration,
               load_wave234_body_registration, load_remaining186_blog_registration,
               load_shop_children_body_registration, load_five_source_projection_registration,
               load_publisher_exact_registration, load_sparse_publisher_targets,
               _available_english_kitchen_en2_targets,
               _available_two_original_material_targets, _available_shop_office_six_targets)
    dynamic_names = set(NATIVE_TARGETS) | set(REPAIR_FAQ_TARGETS) | set(WAVE234_BODY_TARGETS) | set(REMAINING186_BLOG_TARGETS) | set(SHOP_CHILDREN_BODY_TARGETS) | set(FIVE_PROJECTION_TARGETS) | set(PUBLISHER_EXACT_TARGETS) | set(SPARSE_PUBLISHER_TARGETS) | set(ENGLISH_KITCHEN_EN2_TARGETS) | set(TWO_ORIGINAL_MATERIAL_TARGETS) | set(SHOP_OFFICE_SIX_TARGETS)
    for name in dynamic_names:
        targets.pop(name, None)
    for loader in loaders:
        fresh = loader(root)
        require(not set(fresh) & set(targets), "Current CMS registration collides with another target")
        targets.update(fresh)
    return targets


CONDO_FAQ_CANDIDATE_ACCEPTANCE_MODEL = "condo_faq_v7_candidate_scope_only_v1"
CONDO_FAQ_PARENT_TASK = "fc-20261010-assistant1-remaining-business-continuation-v2"
CONDO_FAQ_PARENT_RESULT = {
    "path": "logs/department-outbox/fc-20261010-assistant1-remaining-business-continuation-v2-content-organic-website-condo-faq-field-locator-v8-1837MYT.json",
    "sha256": "a2af2e067cab1ec0bb6e408d3f1222b6ea71cd8d34bc08e99401b44a1fc96375", "size": 8466}
CONDO_FAQ_PARENT_REVIEW = {
    "path": "logs/handoffs/2026-10-14-assistant1-v7-remaining-followthrough-1818-v1/V8-once-new-locator-result-bounded-review.json",
    "sha256": "9396ebe0412e17ee24c54a43bc4692e2aefe85b1f1156b17b179de77cadf6012", "size": 3088}
CONDO_FAQ_PUBLISHER_RESULT = {
    "path": "drafts/publishing/fc-20261014-condo-faq-v7-cms-publishing-v1/outbox-v2.json",
    "sha256": "98951c7e4381bd872ca4c6d0f092a38929ab135426aa2f98b5b18bb59ef3accc", "size": 13390}


def _condo_faq_parent_candidate_source(root: Path, snapshot: dict, report: dict) -> None:
    """Keep the original SEO1 V8 locator in its parent task, not a fake child outbox."""
    require(snapshot.get("goal_delivery", {}).get("parent_task_id") == CONDO_FAQ_PARENT_TASK
            and report.get("original_parent_SEO1_result") == CONDO_FAQ_PARENT_RESULT
            and report.get("original_parent_A1_review") == CONDO_FAQ_PARENT_REVIEW,
            "Exact original parent SEO1 locator and A1 bounded review required")
    for pin in (CONDO_FAQ_PARENT_RESULT, CONDO_FAQ_PARENT_REVIEW):
        require(wc.file_digest(root, pin["path"]) == pin, "Original parent result/review bytes changed")
    source = wc.read_json(wc.safe_path(root, CONDO_FAQ_PARENT_RESULT["path"]))
    review = wc.read_json(wc.safe_path(root, CONDO_FAQ_PARENT_REVIEW["path"]))
    require(source.get("task_id") == CONDO_FAQ_PARENT_TASK
            and source.get("department") == "content-organic-website"
            and source.get("candidate_version") == "seo1-condo-faq-cms-field-locator-v8-20261014-1837MYT"
            and review.get("outbox") == CONDO_FAQ_PARENT_RESULT
            and review.get("reviewer") == "operations-assistant"
            and review.get("formal_whole_goal_QA_PASS") is False
            and review.get("production_saved") is False,
            "Parent source is locator-only, not child producer or publication completion")
    parent_rows, invalid = wc._validate_receipt_chain(root, CONDO_FAQ_PARENT_TASK,
                                                       through_receipt_id="65dd7840-0d19-4c09-b5d3-d3bae6bb339a")
    require(not invalid and any(row.get("receipt_id") == "65dd7840-0d19-4c09-b5d3-d3bae6bb339a"
            and row.get("receipt_type") == "outbox_received"
            and row.get("department") == "content-organic-website"
            and CONDO_FAQ_PARENT_RESULT in row.get("evidence", []) for row in parent_rows),
            "Original parent SEO1 result receipt missing")
    history = wc._result_handoff_rows(root, CONDO_FAQ_PARENT_TASK)
    expected = (("notification_queued", "22df53dc-aef4-4227-b2a6-b655adba5014"),
                ("controller_received", "ea40180e-3e2a-4962-9af1-e939eb11ed43"),
                ("controller_decision", "bc0edf1e-822c-4c24-9c3b-15d4ecd8c57b"),
                ("controller_followthrough", "486d3333-29d0-48b9-9c53-761f25a9a65d"))
    for event, record_id in expected:
        matches = [row for row in history if row.get("event") == event
                   and row.get("record_id") == record_id and row.get("outbox") == CONDO_FAQ_PARENT_RESULT]
        require(len(matches) == 1, "Original parent result intake/continue/followthrough missing")
        if event == "controller_decision":
            require(matches[0].get("decision") == "continue"
                    and matches[0].get("coordinator_role") == "operations-assistant"
                    and matches[0].get("responsible_assistant") == "operations-assistant"
                    and matches[0].get("business_goal_closed") is False,
                    "Original A1 parent decision must remain bounded continuation")


def _condo_faq_child_result_history(root: Path) -> None:
    """Preserve the one already-decided publisher result; it is not a Save decision."""
    expected = (("notification_queued", "576663d5-77c7-474a-a03c-2922079380dd"),
                ("controller_received", "0f54a653-b24a-482b-97ee-6e7bde403d8b"),
                ("controller_decision", "e3ee8e33-b013-42da-8cc2-f5d3c2462699"),
                ("controller_followthrough", "169d7716-5131-4109-a4b2-4c4f2edcc59f"))
    rows = wc._result_handoff_rows(root, CONDO_FAQ_V7_TARGET["task_id"])
    for event, record_id in expected:
        matches = [row for row in rows if row.get("event") == event
                   and row.get("record_id") == record_id
                   and row.get("outbox") == CONDO_FAQ_PUBLISHER_RESULT]
        require(len(matches) == 1, "Original child publisher result stage missing")
        if event == "controller_decision":
            require(matches[0].get("decision") == "continue"
                    and matches[0].get("next_owner") == "system-development"
                    and matches[0].get("coordinator_role") == "operations-assistant"
                    and matches[0].get("business_goal_closed") is False,
                    "Original child continue is only the technical repair handoff")


def _condo_faq_candidate_acceptance(root: Path, snapshot: dict, goal: dict, plan: dict,
                                     receipts: list, target: dict, candidate_pin: dict) -> dict:
    """A1's actual candidate-only result can precede Save; final QA stays separate."""
    require(target == CONDO_FAQ_V7_TARGET and goal.get("parent_task_id") == CONDO_FAQ_PARENT_TASK
            and goal.get("primary_owner") == "content-organic-website"
            and goal.get("responsible_assistant") == "operations-assistant"
            and goal.get("producer_departments") == ["content-organic-website", "publishing"]
            and goal.get("source_mode") == "approved_dispatch"
            and goal.get("authorized_scope") == [target["scope"]]
            and goal.get("authorization_pin", {}).get("sha256") == "463bbf764c280221a55e16fb17023dcce94f2041ba3984001cf570a91abe405b"
            and snapshot.get("goal_contract", {}).get("sha256") == "fa7aae6bd9791360386c9ffb6eb049ed1e868005993a50536dc2708553219967"
            and goal.get("required_execution_actions") == [{"action_id": target["action_id"],
                "action_class": "cms_write", "scope": target["scope"], "department": "publishing"}],
            "Only the original exact condo FAQ CMS child is candidate eligible")
    from qa_review_plan import original_condo_faq_child_review_context
    require(original_condo_faq_child_review_context(root, snapshot, receipts, plan) is not None,
            "Current original A1 main-to-child reviewer source required")
    bounded = wc._goal_bounded_candidate_subject(root, snapshot, receipts, plan, "publishing")
    require(bounded.get("state") == "PROVEN"
            and bounded.get("acceptance_scope") == "candidate_source_only"
            and bounded.get("business_goal_closed") is False
            and bounded.get("candidate") == candidate_pin
            and bounded.get("producer_outbox") == CONDO_FAQ_PUBLISHER_RESULT,
            "Current independent exact condo FAQ candidate-only acceptance missing")
    accepted = bounded["acceptance_receipt"]
    require(accepted.get("receipt_type") == "outbox_received"
            and accepted.get("department") == "operations-assistant"
            and accepted.get("task_id") == target["task_id"],
            "Real A1 candidate outbox receipt required; no fabricated QA verdict")
    box = wc.read_json(wc.safe_path(root, bounded["acceptance_outbox"]["path"]))
    report_pin = box.get("bounded_candidate_acceptance")
    report = wc.read_json(wc.safe_path(root, report_pin["path"]))
    require(report.get("goal_completion_claimed") is False
            and report.get("external_permission_issued") is False
            and report.get("producer_outbox") == CONDO_FAQ_PUBLISHER_RESULT
            and box.get("production_write_allowed") is False
            and box.get("external_permission_issued") is False
            and box.get("goal_completion_claimed") is False,
            "A1 conclusion must be candidate-only, not whole-goal or write authority")
    _condo_faq_parent_candidate_source(root, snapshot, report)
    _condo_faq_child_result_history(root)
    require(report.get("decision") == "continue"
            and report.get("next_owner") == "publishing"
            and report.get("next_action_id") == target["action_id"]
            and report.get("next_scope") == target["scope"]
            and report.get("execution_status") == "NOT_EXECUTED"
            and report.get("public_postcheck_status") == "NOT_VERIFIED",
            "Real A1 candidate-only conclusion must explicitly return exact pre-Save work to publishing")
    require(not any(row.get("receipt_type") == "execution_result"
            and row.get("action_id") == target["action_id"]
            and row.get("scope") == target["scope"]
            and row.get("verdict") != "blocked" for row in receipts),
            "Already executed condo FAQ cannot issue a fresh initial permit")
    return {**accepted, "acceptance_model": CONDO_FAQ_CANDIDATE_ACCEPTANCE_MODEL,
            "task_id": target["task_id"], "action_id": target["action_id"],
            "action_class": "cms_content_candidate", "scope": target["scope"],
            "verdict": "pass_candidate_only", "operation": "publish",
            "responsible_assistant": "operations-assistant", "candidate_version": target["candidate_version"],
            "acceptance_capability": goal["acceptance_capability"],
            "candidate_acceptance_record_id": accepted["receipt_id"],
            "candidate_acceptance_record_hash": accepted["receipt_hash"],
            "review_plan": snapshot["qa_review_plan"]["pin"],
            "review_outbox": bounded["acceptance_outbox"], "bounded_report": report_pin,
            "producer_outbox": bounded["producer_outbox"], "candidate": candidate_pin,
            "source_fingerprint": bounded["source_fingerprint"],
            "risk_level": plan["risk_level"], "authorization_pin": goal["authorization_pin"],
            "goal_completion_claimed": False, "production_write_allowed": False}


def _condo_faq_candidate_decision(root: Path, decision: dict, target: dict,
                                  payload_sha256: str, acceptance: dict, now: datetime) -> dict:
    """Bind A1's later native candidate conclusion, not a forbidden second decision."""
    expected = {"department": "operations-assistant",
        "assistant_chat_task_id": "example-native-51808768551cf834",
        "decision": "EXECUTE_AUTHORIZED_ACTION", "operation": "publish",
        "task_id": target["task_id"], "action_id": target["action_id"],
        "action_class": "cms_write", "scope": target["scope"],
        "candidate_version": target["candidate_version"], "record_id": target["record_id"],
        "payload_sha256": payload_sha256,
        "candidate_acceptance_record_id": acceptance["candidate_acceptance_record_id"],
        "candidate_acceptance_record_hash": acceptance["candidate_acceptance_record_hash"],
        "review_outbox": acceptance["review_outbox"], "review_plan": acceptance["review_plan"],
        "bounded_report": acceptance["bounded_report"],
        "producer_outbox": acceptance["producer_outbox"],
        "source_fingerprint": acceptance["source_fingerprint"],
        "authorization_pin": acceptance["authorization_pin"],
        "candidate_scope_only": True, "goal_completion_claimed": False}
    require(target == CONDO_FAQ_V7_TARGET and acceptance.get("acceptance_model") == CONDO_FAQ_CANDIDATE_ACCEPTANCE_MODEL
            and all(decision.get(key) == value for key, value in expected.items())
            and not decision.get("qa_receipt_id")
            and not decision.get("controller_decision_record_id")
            and len(str(acceptance.get("candidate_acceptance_record_hash") or "")) == 64
            and decision.get("decision_id") == "condo-faq-v7-candidate-" + acceptance["candidate_acceptance_record_hash"][:20],
            "Exact A1 candidate-only CMS decision differs from current source/authority")
    report = wc.read_json(wc.safe_path(root, acceptance["bounded_report"]["path"]))
    require(wc.file_digest(root, acceptance["bounded_report"]["path"]) == acceptance["bounded_report"]
            and report.get("decision") == "continue"
            and report.get("next_owner") == "publishing"
            and report.get("next_action_id") == target["action_id"]
            and report.get("next_scope") == target["scope"],
            "A1 native bounded report must direct only this Save preparation")
    decided_at = timestamp(str(decision.get("decided_at", "")))
    require(timestamp(acceptance["created_at"]) <= decided_at <= now
            and now - timedelta(hours=24) <= decided_at,
            "A1 candidate decision is stale, future or predates current acceptance")
    return {**decision, "candidate_scope_only": True,
            "decision_source": "native_A1_bounded_candidate_conclusion"}


SELF_CHECK_EXECUTION_MODEL = "goal_authorized_cms_selfcheck_v1"


def _authorized_cms_selfcheck(root: Path, snapshot: dict, target: dict, operation: str) -> dict:
    """Admission to existing protected execution, not final acceptance or a permit."""
    from goal_delivery_runtime import execution_preflight
    goal = snapshot["goal_delivery"]
    require(operation == "publish" and snapshot.get("current_state") not in wc.TERMINAL_STATES,
            "Active exact forward CMS goal required; history cannot grant a new write")
    preflight = execution_preflight(root, snapshot, target["action_id"], "cms_write", target["scope"], "publishing")
    payload_digest = target.get("payload_sha256")
    if target.get("candidate_shape") == "english_kitchen_en2_exact":
        original_digest = target.get("desired_fields_sha256")
        require(not payload_digest or payload_digest == original_digest,
                "Exact EN2 payload digest aliases cannot disagree")
        payload_digest = original_digest
    require(preflight.get("risk_level") in {"R1", "R2"}
            and wc.SHA256_PATTERN.fullmatch(str(payload_digest or ""))
            and preflight.get("payload_sha256") == payload_digest,
            "Ordinary selfcheck mode retains exact payload; sensitive R3 still uses its original gate")
    candidate_path = exact_file(Path(target.get("evidence_root",root)),target["candidate"])
    require(candidate_path.is_relative_to(root), "Exact project-owned native candidate required")
    candidate_pin = wc.file_digest(root,str(candidate_path.relative_to(root)))
    candidate = json.loads(candidate_path.read_text())
    validate_candidate_binding(candidate,target,root=root)
    exact_file(root,target["rollback"])
    require(wc._chat_binding_healthy(wc.department_registry(root)["publishing"]["chat_binding"],
                                    verification_ttl_hours=26), "Fresh actual publisher health required")
    require(not wc.validate_workflow_events(root,target["task_id"])
            and not wc._validate_receipt_chain(root,target["task_id"])[1],
            "Original goal event and receipt chains must be intact")
    events = [e for e in wc.read_jsonl(root/wc.WORKFLOW_EVENTS) if e.get("task_id")==target["task_id"]
              and isinstance(e.get("details",{}).get("production_preflight_registered"),dict)]
    matches = []
    for event in events:
        pin = event["details"]["production_preflight_registered"]
        require(wc.file_digest(root,pin.get("path",""))==pin,"Committed execution selfcheck changed")
        if wc.read_json(wc.safe_path(root,pin["path"])) == preflight: matches.append((event,pin))
    require(len(matches)==1,"One actual committed current execution selfcheck required")
    event,pin=matches[0]
    check=wc.read_json(wc.safe_path(root,preflight["self_check"]["path"]))
    require(check.get("candidate") == candidate_pin and check.get("payload_sha256")==payload_digest
            and check.get("expected_updated_at")==target["expected_updated_at"]
            and check.get("record_id")==target["record_id"]
            and check.get("changed_fields")==target["changed_fields"]
            and check.get("executor_department")=="publishing"
            and check.get("production_write_allowed") is False,
            "Publisher selfcheck must bind the actual candidate, row/version, fields and payload")
    return {"acceptance_model":SELF_CHECK_EXECUTION_MODEL,"verdict":"selfcheck_ready",
            "task_id":target["task_id"],"action_id":target["action_id"],"scope":target["scope"],
            "candidate_version":target["candidate_version"],"candidate":candidate_pin,
            "risk_level":preflight["risk_level"],"authorization_pin":goal["authorization_pin"],
            "execution_preflight":pin,"execution_preflight_event_id":event["event_id"],
            "receipt_id":event["event_id"],"receipt_hash":event["event_hash"],"created_at":event["created_at"],
            "review_plan":None,"review_outbox":None,"goal_completion_claimed":False,
            "final_assistant_acceptance_required":True,"production_write_allowed":False}


def validate_goal_cms_acceptance(root: Path, target: dict, operation: str,
                                 *, allow_blocked_retry: bool = False) -> dict:
    """New goals use their one current independent assistant, never retired QA.

    This consumes existing review and original authority bytes. It grants no
    account access, approval, permit, or production write.
    """
    from goal_delivery_runtime import enabled, restore_goal, validate_goal
    if target.get('candidate_shape') == 'professional_cms_source_selfcheck_v1':
        from professional_cms_issuer import acceptance
        return acceptance(root,target,operation)
    import qa_review_plan as review
    from paid_three_page_bounded_cms import TASK as bounded_task, MODEL as bounded_model
    if target.get("task_id") == bounded_task:
        require(operation in {"publish", "rollback"} and target.get("candidate_shape") == bounded_model,
                "Original bounded T3 cannot inherit another target or operation")
        snapshot = wc.read_json(wc.snapshot_path(root, target["task_id"]))
        return review.validate_cms_candidate_acceptance(root, snapshot, target, operation)
    root = Path(root).resolve()
    if target.get('candidate_shape') == 'owner_authorized_shop_office_six_field_v4':
        from tools.shop_office_six_field_execution import acceptance
        return acceptance(root, target, operation)
    snapshot = restore_goal(root, wc.read_json(wc.snapshot_path(root, target["task_id"])))
    require(enabled(root, snapshot), "Current complete goal is required for assistant CMS acceptance")
    goal = snapshot["goal_delivery"]
    checked_goal = validate_goal(root, goal)
    require(checked_goal.get("authorization_pin") == goal.get("authorization_pin"),
            "Original complete-goal authority bytes changed")
    require(target.get("execution_owner") == "publishing"
            and "publishing" in goal["producer_departments"]
            and target["scope"] in goal["authorized_scope"],
            "CMS execution must use the existing publishing role and exact authorized scope")
    require(operation in {"publish", "rollback"}, "Known exact CMS operation required")
    require(isinstance(target.get("candidate_shape"), str) and bool(target["candidate_shape"])
            and isinstance(target.get("changed_fields"), list) and bool(target["changed_fields"])
            and len(set(target["changed_fields"])) == len(target["changed_fields"]),
            "Modern CMS target needs its existing exact candidate shape and field namespace")
    preflights=[p for p in goal.get('execution_preflights',[]) if all(p.get(k)==v for k,v in
                {'action_id':target['action_id'],'action_class':'cms_write','scope':target['scope'],
                 'department':'publishing'}.items())]
    typed_selfcheck=False
    if len(preflights)==1:
        if wc.file_digest(root,preflights[0]['self_check']['path'])!=preflights[0]['self_check']:
            raise wc.WorkflowError('exact committed CMS selfcheck source changed')
        check=wc.read_json(wc.safe_path(root,preflights[0]['self_check']['path']))
        typed_selfcheck=all(k in check for k in ('candidate','executor_department','changed_fields','expected_updated_at'))
    if (operation == 'publish' and checked_goal.get("execution_mode") == "authorized_selfcheck_then_execute"
            and target.get("candidate_shape") != CONDO_FAQ_V7_SHAPE
            and (target.get('candidate_shape')==BUILTIN_WARDROBE_SHAPE or typed_selfcheck)
            and (not preflights or preflights[0].get('risk_level') in {'R1','R2'})):
        return _authorized_cms_selfcheck(root,snapshot,target,operation)
    expected_action = target["action_id"] if operation == "publish" else f"rollback-{target['candidate_version']}"
    expected_version = target["candidate_version"] if operation == "publish" else f"{target['candidate_version']}-rollback-v1"
    evidence_root = Path(target.get("evidence_root", root)).resolve()
    candidate_spec = target["candidate"] if operation == "publish" else target.get("rollback_review_candidate", target["rollback"])
    candidate_path = exact_file(evidence_root, candidate_spec)
    exact_file(evidence_root, target["rollback"])
    require(candidate_path.is_relative_to(root), "Assistant review candidate must belong to this company task")
    if operation == "publish" and target.get("candidate_shape"):
        validate_candidate_binding(json.loads(candidate_path.read_text()), target, root=root)
    plan = review.load_plan(root, snapshot)
    require(isinstance(plan, dict), "Current exact assistant CMS review plan missing")
    candidate_pin = wc.file_digest(root, str(candidate_path.relative_to(root)))
    require(all(plan.get(key) == value for key, value in {
        "task_id": target["task_id"], "action_id": expected_action,
        "action_class": "cms_content_candidate", "scope": target["scope"],
        "candidate_version": expected_version, "candidate_sha256": candidate_spec[1],
        "candidate": candidate_pin, "reviewer_department": goal["responsible_assistant"],
    }.items()), "Current assistant plan differs from exact CMS task/action/version/row candidate")
    reviewer = goal["responsible_assistant"]
    registry = wc.department_registry(root)
    require(wc._chat_binding_healthy(registry[reviewer].get("chat_binding", {}), verification_ttl_hours=26),
            "Current fixed responsible assistant health proof required")
    receipts, invalid = wc._validate_receipt_chain(root, target["task_id"])
    require(not invalid and not wc.validate_workflow_events(root, target["task_id"]),
            "Current assistant CMS receipt/event chains are invalid")
    if target == CONDO_FAQ_V7_TARGET and operation == "publish":
        return _condo_faq_candidate_acceptance(root, snapshot, goal, plan, receipts, target, candidate_pin)
    verdicts = [row for row in receipts if row.get("receipt_type") == "qa_verdict"
                and row.get("department") == reviewer
                and row.get("action_id") == expected_action and row.get("scope") == target["scope"]]
    require(bool(verdicts) and verdicts[-1].get("verdict") == "pass",
            "Current assigned assistant exact CMS acceptance PASS missing")
    accepted = verdicts[-1]
    require(accepted.get("action_class") == "cms_content_candidate", "Assistant acceptance must review CMS content")
    review.validate_verdict(root, snapshot, receipts, accepted)
    outbox_pin = next((pin for pin in accepted.get("evidence", [])
                       if str(pin.get("path", "")).endswith(".json")), None)
    require(isinstance(outbox_pin, dict), "Exact current assistant result bytes missing")
    outbox = wc.read_json(wc.safe_path(root, outbox_pin["path"]))
    require(outbox.get("review_identity") == {key: plan[key] for key in review.IDENTITY}
            and review._binding(root, snapshot)["pin"] in outbox.get("evidence", [])
            and candidate_pin in outbox.get("evidence", [])
            and not any(str(item.get("priority", "")).upper() in {"P0", "P1"}
                        for item in outbox.get("blockers", []) if isinstance(item, dict)),
            "Assistant PASS must freeze the current CMS plan/candidate and have no unresolved P0/P1")
    blocked = snapshot.get("current_state") == "blocked"
    require(not blocked or allow_blocked_retry and snapshot.get("blockers") == ["execution_result_blocked"]
            and snapshot.get("resume_from") == "owner_approved",
            "Blocked CMS action requires its exact existing retry path")
    return {**accepted, "acceptance_model": "goal_delivery_assistant_v1",
            "responsible_assistant": reviewer, "acceptance_capability": goal["acceptance_capability"],
            "review_plan": review._binding(root, snapshot)["pin"], "review_outbox": outbox_pin,
            "candidate": candidate_pin, "risk_level": plan["risk_level"],
            "authorization_pin": goal["authorization_pin"], "production_write_allowed": False}


def validate_goal_cms_policy(root: Path, task_id: str, action_id: str, scope: str,
                             department: str, payload_sha256: str) -> dict:
    """Exact registered namespace for the actual policy consumer; no fallback."""
    from goal_delivery_runtime import restore_goal, execution_preflight
    require(department == "publishing", "CMS goal policy executor must be publishing")
    from professional_cms_issuer import MODEL as professional_model, policy_context
    matching=[x for x in _current_registered_targets(root).values() if x.get('candidate_shape')==professional_model
              and x['task_id']==task_id and x['scope']==scope
              and action_id in {x['action_id'],'rollback-'+x['candidate_version']}]
    if matching:
        require(len(matching)==1, "One exact professional namespace")
        op='publish' if action_id==matching[0]['action_id'] else 'rollback'
        return policy_context(root,matching[0],op,payload_sha256)
    require(wc.SHA256_PATTERN.fullmatch(str(payload_sha256 or "")) is not None,
            "Exact CMS payload digest required")
    matches = []
    from paid_three_page_bounded_cms import TASK as bounded_task, targets as bounded_targets
    if task_id == "fc-20261025-shop-office-existing-six-and-five-implementation-release-v1":
        from tools.shop_office_six_field_execution import targets as original_six_targets
        registered = original_six_targets(root)
    else:
        registered = bounded_targets(root) if task_id == bounded_task else _current_registered_targets(Path(root))
    for name, target in registered.items():
        if (target.get("task_id") != task_id or target.get("scope") != scope
                or target.get("execution_owner") != department):
            continue
        for operation, expected in (("publish", target["action_id"]),
                                    ("rollback", f"rollback-{target['candidate_version']}")):
            if action_id == expected:
                matches.append((name, target, operation))
    require(len(matches) == 1, "One current exact registered CMS task/action/executor namespace required")
    name, target, operation = matches[0]
    if target.get("candidate_shape") == CONDO_FAQ_V7_SHAPE:
        require(name == CONDO_FAQ_V7_NAME and operation == "publish"
                and target == CONDO_FAQ_V7_TARGET
                and payload_sha256 == target["payload_sha256"],
                "Exact current condo FAQ publisher payload and forward action required")
    if target.get("candidate_shape") == BUILTIN_WARDROBE_SHAPE:
        require(name == BUILTIN_WARDROBE_NAME and operation == "publish"
                and target == BUILTIN_WARDROBE_TARGET
                and payload_sha256 == target["payload_sha256"],
                "Only the new builtin wardrobe content_zh payload and forward action required")
    require(operation != "rollback" or target.get("rollback_allowed", True), "Exact target does not allow rollback")
    accepted = validate_goal_cms_acceptance(Path(root), target, operation, allow_blocked_retry=True)
    validate_new_permit_target(target, assistant_acceptance=accepted)
    snapshot = restore_goal(root, wc.read_json(wc.snapshot_path(Path(root), task_id)))
    preflight = execution_preflight(root, snapshot, action_id, "cms_write", scope, department)
    require(isinstance(preflight, dict) and preflight.get("risk_level") == accepted["risk_level"],
            "CMS production preflight risk must equal current assistant acceptance")
    require(preflight.get("payload_sha256") == payload_sha256,
            "Exact CMS payload must be frozen in its current production preflight")
    return {"target_name": name, "operation": operation, "risk_level": accepted["risk_level"],
            "acceptance_receipt_id": accepted.get("candidate_acceptance_record_id", accepted.get("receipt_id")),
            "acceptance_model": accepted["acceptance_model"], "task_id": task_id, "action_id": action_id,
            "scope": scope, "department": department, "payload_sha256": payload_sha256,
            "review_outbox": accepted["review_outbox"],
            "review_plan": accepted["review_plan"], "candidate": accepted["candidate"],
            "authorization_pin": accepted["authorization_pin"], "preflight": preflight,
            "candidate_acceptance_record_hash": accepted.get("candidate_acceptance_record_hash"),
            "source_fingerprint": accepted.get("source_fingerprint"),
            "bounded_report": accepted.get("bounded_report"),
            "producer_outbox": accepted.get("producer_outbox"),
            "goal_completion_claimed": accepted.get("goal_completion_claimed", False),
            "external_permission_issued": False}


def validate_goal_cms_decision(root: Path, decision: dict, target: dict, operation: str,
                               payload_sha256: str, acceptance: dict, now: datetime) -> dict:
    """Reuse the real assigned-assistant decision; do not invent a HQ review."""
    from paid_three_page_bounded_cms import MODEL as bounded_model, decision as bounded_decision
    if acceptance.get("acceptance_model") == bounded_model:
        require(operation == acceptance.get("operation"), "Publish proof cannot grant rollback permission")
        return bounded_decision(root, decision, target, payload_sha256, acceptance, now)
    if acceptance.get("acceptance_model") == CONDO_FAQ_CANDIDATE_ACCEPTANCE_MODEL:
        require(operation == "publish" and payload_sha256 == CONDO_FAQ_V7_TARGET["payload_sha256"],
                "Condo FAQ candidate acceptance cannot authorize another operation or payload")
        return _condo_faq_candidate_decision(root, decision, target, payload_sha256, acceptance, now)
    if (target.get("candidate_shape") == "owner_authorized_shop_office_six_field_v4"
            and operation == "rollback" and acceptance.get("acceptance_model") == SELF_CHECK_EXECUTION_MODEL):
        from tools.shop_office_six_field_execution import reverse_decision
        return reverse_decision(root, decision, target, payload_sha256, acceptance, now)
    if target.get('candidate_shape') == 'professional_cms_source_selfcheck_v1':
        from professional_cms_issuer import decision as professional_decision
        return professional_decision(root,decision,target,operation,payload_sha256,acceptance,now)
    if acceptance.get("acceptance_model") == SELF_CHECK_EXECUTION_MODEL:
        require(operation=="publish" and payload_sha256==target["payload_sha256"],
                "Selfcheck cannot grant a different operation or payload")
        expected={"department":"publishing","decision":"EXECUTE_ORIGINAL_AUTHORIZED_ACTION",
            "task_id":target["task_id"],"action_id":target["action_id"],"action_class":"cms_write",
            "scope":target["scope"],"candidate_version":target["candidate_version"],
            "record_id":target["record_id"],"payload_sha256":payload_sha256,
            "authorization_pin":acceptance["authorization_pin"],
            "execution_preflight":acceptance["execution_preflight"],
            "execution_preflight_event_id":acceptance["execution_preflight_event_id"]}
        require(all(decision.get(k)==v for k,v in expected.items()) and bool(decision.get("decision_id")),
                "Original executor readiness differs from its committed exact authority/selfcheck")
        decided=timestamp(str(decision.get("decided_at","")))
        require(timestamp(acceptance["created_at"])<=decided<=now and now-timedelta(hours=24)<=decided,
                "Execution readiness is stale or predates actual selfcheck")
        return decision
    require(acceptance.get("acceptance_model") == "goal_delivery_assistant_v1", "Exact assistant acceptance required")
    action_id = target["action_id"] if operation == "publish" else f"rollback-{target['candidate_version']}"
    version = target["candidate_version"] if operation == "publish" else f"{target['candidate_version']}-rollback-v1"
    assistant = acceptance["responsible_assistant"]
    fixed = wc.department_registry(root)[assistant]["chat_binding"]["task_id"]
    expected = {"department": assistant, "assistant_chat_task_id": fixed,
                "decision": "EXECUTE_AUTHORIZED_ACTION", "operation": operation,
                "task_id": target["task_id"], "action_id": action_id, "action_class": "cms_write",
                "scope": target["scope"], "candidate_version": version, "record_id": target["record_id"],
                "payload_sha256": payload_sha256, "qa_receipt_id": acceptance["receipt_id"],
                "review_outbox": acceptance["review_outbox"], "review_plan": acceptance["review_plan"],
                "authorization_pin": acceptance["authorization_pin"]}
    require(all(decision.get(key) == value for key, value in expected.items())
            and isinstance(decision.get("decision_id"), str) and bool(decision["decision_id"]),
            "Assigned assistant routine decision differs from exact CMS action/authority/acceptance")
    rows = [row for row in wc._result_handoff_rows(root, target["task_id"])
            if row.get("record_id") == decision.get("controller_decision_record_id")]
    require(len(rows) == 1, "Actual assigned assistant native decision record missing or ambiguous")
    row = rows[0]
    accepted_box = wc.read_json(wc.safe_path(root, acceptance["review_outbox"]["path"]))
    producer_pin = accepted_box["goal_acceptance"]["producer_results"].get(row.get("sender_department"))
    require(row.get("event") == "controller_decision" and row.get("decision") in {"accept", "release_gate"}
            and row.get("coordinator_role") == assistant and row.get("decision_actor") == assistant
            and row.get("responsible_assistant") == assistant
            and isinstance(row.get("coordination_fence"), int) and row["coordination_fence"] > 0
            and row.get("outbox") == producer_pin and producer_pin is not None
            and acceptance["review_outbox"] in row.get("evidence", [])
            and row.get("qa_status") == "pass" and row.get("next_owner") == "publishing",
            "Actual fenced assistant decision must bind accepted current producer/result and publishing continuation")
    decided_at = timestamp(str(decision.get("decided_at", "")))
    require(timestamp(acceptance["created_at"]) <= timestamp(row["created_at"]) <= decided_at <= now
            and now - timedelta(hours=24) <= decided_at,
            "Assistant decision is stale, future, or predates current acceptance")
    return decision


def validate_qa(root: Path, target: dict, operation: str, *, allow_blocked_retry: bool = False) -> dict:
    # Presence of a modern goal is fail-closed even if its global switch is off;
    # a broken new contract must never be laundered through a legacy QA PASS.
    snapshot = wc.read_json(wc.snapshot_path(root, target["task_id"]))
    if isinstance(snapshot.get("goal_delivery"), dict):
        return validate_goal_cms_acceptance(root, target, operation, allow_blocked_retry=allow_blocked_retry)
    task_id = target["task_id"]
    expected_action = target["action_id"] if operation == "publish" else f"rollback-{target['candidate_version']}"
    expected_version = target["candidate_version"] if operation == "publish" else f"{target['candidate_version']}-rollback-v1"
    pinned_qa_path = exact_file(root, target["qa_outbox"]) if target.get("qa_outbox") else None
    if target.get("candidate_shape"):
        candidate = json.loads(exact_file(root, target["candidate"]).read_text())
        validate_candidate_binding(candidate, target)
    if target.get("qa_request"):
        evidence_root = target.get("evidence_root", root)
        candidate = json.loads(exact_file(evidence_root, target["candidate"]).read_text())
        rollback = json.loads(exact_file(evidence_root, target["rollback"]).read_text())
        request = json.loads(exact_file(evidence_root, target["qa_request"]).read_text())
        require(request.get("mode") == "dry-run" and request.get("contentType") == "service"
                and request.get("record") == candidate
                and request.get("expectedUpdatedAt") == rollback.get("updated_at")
                and candidate.get("id") == rollback.get("id") == target["record_id"]
                and candidate.get("slug") == rollback.get("slug") == target["slug"]
                and {key for key in candidate if candidate[key] != rollback.get(key)} == {"faqs_en", "faqs_zh"},
                "Pinned QA request, candidate, or rollback row differs from the two-field V4 scope")
    registry_path = root / "data/department-registry.json"
    if registry_path.is_file():
        registry = json.loads(registry_path.read_text())
        fixed = [row for row in registry.get("departments", []) if row.get("id") == "qa"]
        binding = fixed[0].get("chat_binding", {}) if len(fixed) == 1 else {}
        require(binding.get("task_id") == QA_THREAD_ID
                and binding.get("status") == "bound_and_visible"
                and binding.get("dispatch_eligible") is True
                and binding.get("reply_health") == "healthy_visible_reply_verified",
                "Fixed QA registry identity changed; refresh the exact binding")
        verified_at = timestamp(str(binding.get("last_verified_at", "")))
        now = datetime.now(timezone.utc)
        require(now - timedelta(hours=26) <= verified_at <= now,
                "Fixed QA health proof is stale; refresh before issuing a permit")
    snapshot = json.loads((root / "data/workflows" / f"{task_id}.json").read_text())
    if operation == "publish" and target.get("candidate_shape") == "native_publisher_sparse_admission":
        from original_task_publisher_handover import progress
        exact_native_cycle = progress(root, task_id, target["action_id"], target["scope"])
        require(bool(exact_native_cycle and exact_native_cycle["qa_passed"]), "Exact publisher native cycle missing")
    # A sibling action can close a shared task. Exact action QA, pinned evidence,
    # policy, CAS and one-use permit checks below still apply to every target.
    normal_states = {"qa_passed", "waiting_owner_approval", "owner_approved", "execution_completed", "verified", "closed"}
    blocked_retry = (allow_blocked_retry and snapshot.get("current_state") == "blocked"
                     and snapshot.get("blockers") == ["execution_result_blocked"]
                     and snapshot.get("resume_from") == "owner_approved")
    handover_qa = False
    if (operation == "publish" and target.get("candidate_shape") == "native_publisher_sparse_admission"
            and target.get("execution_owner") == "publishing" and snapshot.get("current_state") == "qa_blocked"):
        from original_task_publisher_handover import progress
        try:
            exact_progress = progress(root, task_id, target["action_id"], target["scope"])
            handover_qa = bool(exact_progress and exact_progress["qa_passed"])
        except (ValueError, KeyError, OSError) as error:
            raise PermitEvidenceError(str(error)) from error
    require(snapshot.get("current_state") in normal_states or blocked_retry or handover_qa,
            "Original workflow has no current exact QA PASS")
    receipts, invalid = wc._validate_receipt_chain(root, task_id)
    require(not invalid, f"Workflow receipt chain invalid: {invalid[:2]}")
    qa_rows = [row for row in receipts if row.get("receipt_type") == "qa_verdict" and row.get("department") == "qa"
               and row.get("chat_task_id") == QA_THREAD_ID
               and row.get("task_id") == task_id and row.get("scope") == target["scope"]
               and row.get("action_class") == "cms_content_candidate"
               and row.get("action_id") == expected_action]
    require(bool(qa_rows), "Fixed QA receipt is not an exact release PASS")
    qa = qa_rows[-1]
    require(qa.get("verdict") == "pass", "Latest fixed QA receipt is not an exact release PASS")
    outboxes = []
    for evidence in qa.get("evidence", []):
        path = str(evidence.get("path", ""))
        if path.startswith("logs/department-outbox/") and path.endswith(".json"):
            outboxes.append((path, json.loads((root / path).read_text())))
    if pinned_qa_path is not None:
        # Older QA workflows registered their exact outbox in an earlier
        # outbox_received receipt, while qa_verdict cited the shared report.
        # The receipt chain and pinned file digest must both match; never infer
        # a PASS merely from a loose file on disk.
        qa_index = next(index for index, row in enumerate(receipts)
                        if row.get("receipt_id") == qa.get("receipt_id"))
        for receipt in receipts[:qa_index]:
            if (receipt.get("receipt_type") != "outbox_received"
                    or receipt.get("department") != "qa"
                    or receipt.get("chat_task_id") != QA_THREAD_ID
                    or receipt.get("task_id") != task_id):
                continue
            for evidence in receipt.get("evidence", []):
                path = str(evidence.get("path", ""))
                if (path == target["qa_outbox"][0]
                        and evidence.get("sha256") == target["qa_outbox"][1]):
                    outboxes.append((path, json.loads(pinned_qa_path.read_text())))
    if target.get("candidate_shape") and operation == "publish":
        require(pinned_qa_path is not None and any(
            (root / path).resolve() == pinned_qa_path
            and structured_qa_outbox_matches(row, target)
            for path, row in outboxes),
            "Pinned structured QA PASS does not bind the exact candidate, row, fields, and scope")
        return qa
    require(any(row.get("department") == "qa" and row.get("task_id") == task_id
                and row.get("status") == "completed" and row.get("gate_status") == "PASS_FOR_AUTO_RELEASE"
                and row.get("verdict", row.get("qa_verdict")) == "pass"
                and (row.get("scope") or row.get("release_boundary", {}).get("scope")) == target["scope"]
                and (not target.get("qa_candidate_only") and row.get("candidate_version") == expected_version
                     and row.get("release_boundary", {}).get("publish_authorized") is True
                     or target.get("qa_candidate_only") and row.get("action_id") == expected_action
                     and (row.get("candidate_version") == expected_version
                          or operation == "publish" and row.get("candidate_version") is None)
                     and ((pinned_qa_path is not None and (root / path).resolve() == pinned_qa_path)
                          or (row.get("candidate", {}).get("row_id") == target["record_id"]
                              and row.get("candidate", {}).get("slug") == target["slug"]
                              and (operation == "rollback" or
                                   (row.get("candidate", {}).get("candidate_row_sha256")
                                    or row.get("candidate", {}).get("candidate_row", {}).get("sha256")) == target["candidate"][1]))))
                and not any(str(item.get("priority", "")).upper() in {"P0", "P1"}
                            for item in row.get("blockers", []) if isinstance(item, dict))
                for path, row in outboxes), "QA PASS evidence does not bind the exact candidate and scope")
    return qa


def validate_operations(decision: dict, target: dict, operation: str, payload_sha256: str, qa_receipt_id: str, now: datetime) -> dict:
    action_id = target["action_id"] if operation == "publish" else f"rollback-{target['candidate_version']}"
    version = target["candidate_version"] if operation == "publish" else f"{target['candidate_version']}-rollback-v1"
    require(decision.get("department") == "operations" and decision.get("operations_chat_task_id") == OPERATIONS_THREAD_ID
            and decision.get("decision") == "AUTO_RELEASE"
            and decision.get("operation") == operation and decision.get("task_id") == target["task_id"]
            and decision.get("action_id") == action_id and decision.get("action_class") == "cms_write"
            and decision.get("scope") == target["scope"] and decision.get("candidate_version") == version
            and decision.get("record_id") == target["record_id"]
            and decision.get("payload_sha256") == payload_sha256
            and decision.get("qa_receipt_id") == qa_receipt_id
            and isinstance(decision.get("decision_id"), str) and decision["decision_id"],
            "Operations AUTO_RELEASE is missing or does not match the exact action")
    decided_at = timestamp(str(decision.get("decided_at", "")))
    require(now - timedelta(hours=24) <= decided_at <= now, "Operations decision is stale or future-dated")
    return decision


def validate_policy(row: dict, target: dict, operation: str, payload_sha256: str, operations: dict, now: datetime) -> dict:
    if target.get('candidate_shape') == 'professional_cms_source_selfcheck_v1':
        from professional_cms_issuer import consumed
        return consumed(ROOT,row,target,operation,payload_sha256,operations,now)
    if target.get('candidate_shape') == 'owner_authorized_shop_office_six_field_v4':
        from tools.shop_office_six_field_execution import consumed_policy
        return consumed_policy(ROOT, row, target, operation, payload_sha256, operations, now)
    action_id = target["action_id"] if operation == "publish" else f"rollback-{target['candidate_version']}"
    require(row.get("status") == "allow" and row.get("department") == target.get("execution_owner", "content-organic-website")
            and row.get("task_id") == target["task_id"] and row.get("action_id") == action_id
            and row.get("action_class") == "cms_write" and row.get("scope") == target["scope"]
            and row.get("payload_sha256") == payload_sha256
            and row.get("approval_status") == "consumed"
            and isinstance(row.get("decision_id"), str) and row["decision_id"],
            "Policy decision is not exact, allowed, and consumed")
    if target == CONDO_FAQ_V7_TARGET and operations.get("candidate_scope_only") is True:
        context = row.get("cms_candidate_acceptance", {})
        require(context.get("acceptance_model") == CONDO_FAQ_CANDIDATE_ACCEPTANCE_MODEL
                and context.get("candidate_acceptance_record_id") == operations.get("candidate_acceptance_record_id")
                and context.get("candidate_acceptance_record_hash") == operations.get("candidate_acceptance_record_hash")
                and context.get("source_fingerprint") == operations.get("source_fingerprint")
                and context.get("bounded_report") == operations.get("bounded_report")
                and context.get("producer_outbox") == operations.get("producer_outbox")
                and context.get("goal_completion_claimed") is False
                and row.get("approval_basis") == "original_exact_condo_publishing_v1",
                "Policy must consume the same exact original A1 candidate and owner approval")
    from paid_three_page_bounded_cms import TASK as bounded_task, MODEL as bounded_model
    if target.get("task_id") == bounded_task:
        context = row.get("cms_candidate_acceptance", {})
        require(context.get("acceptance_model") == bounded_model
                and context.get("candidate_acceptance_record_id") == operations.get("candidate_acceptance_record_id")
                and context.get("machine_identity") == operations.get("machine_identity")
                and isinstance(context.get("machine_identity"), dict),
                "Policy must consume the same actual A2-frozen machine and candidate continue")
    checked_at = timestamp(str(row.get("checked_at", "")))
    require(timestamp(operations["decided_at"]) <= checked_at <= now
            and now - timedelta(minutes=30) <= checked_at, "Policy allow is stale or predates operations")
    return row


def validate_retry_state(root: Path, target: dict, operation: str, policy: dict) -> None:
    if target.get('candidate_shape') == 'professional_cms_source_selfcheck_v1':
        snapshot=wc.read_json(wc.snapshot_path(root,target['task_id']))
        require(snapshot.get('current_state') not in {'blocked','closed','blocked_evidence_invalid'},
                "Read original effect; no automatic professional retry or closed-scope reopen")
        return
    """Bind a blocked execution to its one permitted policy retry before issuing."""
    snapshot = json.loads((root / "data/workflows" / f"{target['task_id']}.json").read_text())
    if (operation == "publish" and target.get("candidate_shape") == "native_publisher_sparse_admission"
            and policy.get("approval_basis") == "blocked_execution_retry"):
        from original_task_publisher_handover import retry_projection
        projected = retry_projection(root, target["task_id"], target["action_id"], target["scope"],
                                     policy.get("retry_source_receipt_id"), policy.get("approval_id"))
        require(projected is not None, "Exact publisher blocked retry projection missing")
        snapshot = {**snapshot, **{k: projected[k] for k in ("current_state", "blockers", "resume_from")}}
    else:
        projected = None
    if snapshot.get("current_state") != "blocked":
        require(policy.get("approval_basis") != "blocked_execution_retry",
                "Retry policy requires the original blocked workflow")
        return
    require(snapshot.get("blockers") == ["execution_result_blocked"]
            and snapshot.get("resume_from") == "owner_approved"
            and policy.get("approval_basis") == "blocked_execution_retry",
            "Blocked workflow requires an exact execution retry policy")
    receipts, invalid = wc._validate_receipt_chain(root, target["task_id"])
    require(not invalid, f"Workflow receipt chain invalid: {invalid[:2]}")
    executions = projected["executions"] if projected else [row for row in receipts if row.get("receipt_type") == "execution_result"]
    require(bool(executions), "Blocked workflow has no execution receipt")
    latest = executions[-1]
    action_id = target["action_id"] if operation == "publish" else f"rollback-{target['candidate_version']}"
    expected = {"receipt_type": "execution_result", "verdict": "blocked",
                "department": target.get("execution_owner", "content-organic-website"), "task_id": target["task_id"],
                "action_id": action_id, "action_class": "cms_write", "scope": target["scope"],
                "approval_id": policy.get("approval_id")}
    require(all(latest.get(key) == value for key, value in expected.items())
            and policy.get("retry_source_receipt_id") == latest.get("receipt_id"),
            "Retry policy does not bind the latest exact blocked execution")


def gh_json(*args: str) -> dict:
    result = subprocess.run(["gh", *args], check=True, capture_output=True, text=True)
    return json.loads(result.stdout)


def artifact_for_run(run_id: int, target_name: str, folder: Path) -> tuple[dict, dict, dict, Path]:
    run = gh_json("api", f"repos/{REPOSITORY}/actions/runs/{run_id}")
    valid_name = run.get("name") == "Approved website content publish"
    if not valid_name and target_name in {
            "shop-office-shop-six-v4-ba79401d2ed2-20261025-v1",
            "shop-office-office-six-v4-eb6eef35d390-20261025-v1"}:
        from tools.shop_office_six_field_execution import targets as exact_targets
        actual_target = exact_targets(ROOT).get(target_name)
        require(actual_target is not None and TARGETS.get(target_name) == actual_target,
                "Exact original registered shop/office target required")
        workflow = gh_json("api", f"repos/{REPOSITORY}/actions/workflows/content-publish-approved.yml")
        require(workflow.get("name") == "Approved website content publish"
                and workflow.get("path") == ".github/workflows/content-publish-approved.yml"
                and workflow.get("id") == run.get("workflow_id")
                and type(workflow.get("id")) is int and workflow["id"] > 0
                and workflow.get("state") == "active"
                and run.get("repository", {}).get("full_name") == REPOSITORY
                and run.get("repository", {}).get("id") == 1248188229
                and run.get("status") == "completed" and run.get("run_attempt") == 1,
                "Exact active original workflow/repository and first completed preview required")
        valid_name = run.get("name") == f"{target_name} | dry-run"
    require(run.get("event") == "workflow_dispatch" and run.get("head_branch") == "main"
            and run.get("conclusion") == "success" and valid_name
            and run.get("path") == ".github/workflows/content-publish-approved.yml"
            and run.get("id") == run_id and len(str(run.get("head_sha", ""))) == 40,
            "Dry-run workflow identity or conclusion is invalid")
    subprocess.run(["gh", "run", "download", str(run_id), "-R", REPOSITORY,
                    "-n", f"approved-content-publish-{run_id}", "-D", str(folder)], check=True, capture_output=True)
    target_dir = folder / target_name
    receipt = json.loads((target_dir / "locked-dry-run-receipt.json").read_text())
    digest = json.loads((target_dir / "managed-payload-digest.json").read_text())
    probe = json.loads((target_dir / "managed-identity-probe.json").read_text())
    backup = json.loads((target_dir / "rollback-payload-digest.json").read_text()) if (target_dir / "rollback-payload-digest.json").is_file() else {}
    require(receipt.get("http_status") == 200 and receipt.get("dry_run") is True
            and receipt.get("performed_write") is False and receipt.get("external_writes") == 0
            and receipt.get("row_unchanged_after_dry_run") is True,
            "Protected dry-run did not prove zero writes and exact row readback")
    identity = probe.get("identity", {})
    require(probe.get("ok") is True and probe.get("dry_run") is True and probe.get("performed_write") is False
            and identity.get("runId") == run_id and identity.get("runAttempt") == run.get("run_attempt")
            and identity.get("repositoryId") == 1248188229
            and identity.get("workflowRef") == f"{REPOSITORY}/.github/workflows/content-publish-approved.yml@refs/heads/main"
            and identity.get("actorId") == run.get("actor", {}).get("id")
            and len(str(identity.get("workflowSha", ""))) == 40,
            "Server-verified OIDC identity probe does not match the dry-run run")
    return run, receipt, digest, target_dir / "backup.json"


def safe_control_http_diagnostic(error: HTTPError, control: dict) -> dict:
    """Classify a bounded error; never emit credentials, raw body or raw headers."""
    categories = {
        "Origin not allowed": "origin_not_allowed",
        "Managed permit issuer authentication failed": "issuer_authentication_failed",
        "Managed permit issuer is not configured": "issuer_not_configured",
        "Managed CMS release is disabled": "managed_release_disabled",
        "Invalid managed permit control body": "invalid_control_body",
        "Managed permit identity, evidence, or short expiry is invalid": "invalid_permit_identity_evidence_or_expiry",
        "Exact frozen target version or changed-fields payload digest is invalid": "target_version_or_payload_mismatch",
        "Publish requires the exact independently restorable prior payload digest": "invalid_prior_payload_binding",
        "Rollback requires a distinct completed publish permit": "invalid_rollback_parent",
        "Managed rollback requires the exact completed parent run ID": "invalid_rollback_parent_run",
        "Rollback does not restore the completed candidate's exact prior version": "rollback_parent_source_mismatch",
        "Unknown permit or control action": "unknown_permit_or_action",
        "Invalid permit ID": "invalid_permit_id",
    }
    result = {"http_status": error.code if type(error.code) is int else None,
              "error_category": "unclassified_http_error", "raw_body_or_headers_logged": False,
              "execution_effect": "UNKNOWN_READ_ORIGINAL_KEY_NO_AUTOMATIC_RETRY"}
    if control.get("controlAction") in {"issue", "status", "revoke"}:
        result["control_action"] = control["controlAction"]
    if control.get("operation") in {"publish", "rollback"}:
        result["operation"] = control["operation"]
    permit = control.get("permitId")
    if isinstance(permit, str) and re.fullmatch(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}", permit):
        result["permit_id_sha256"] = hashlib.sha256(permit.encode()).hexdigest()
    policy = control.get("policyDecisionId")
    if isinstance(policy, str) and re.fullmatch(r"pol-[0-9a-f]{20}", policy):
        result["policy_decision_id"] = policy
    ids = {}
    for name in ("sb-request-id", "x-request-id", "x-deno-execution-id", "cf-ray"):
        value = error.headers.get(name) if error.headers else None
        pattern = r"[0-9a-fA-F]{16}-[A-Z]{3}" if name == "cf-ray" else r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}"
        if isinstance(value, str) and re.fullmatch(pattern, value):ids[name] = value
    if ids:result["request_ids"] = ids
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:raise ValueError("ambiguous error object")
            value[key] = item
        return value
    try:
        raw = error.read(8193)
        if len(raw) <= 8192:
            body = json.loads(raw.decode("utf-8"), object_pairs_hook=unique,
                              parse_constant=lambda value: (_ for _ in ()).throw(ValueError("finite JSON required")))
            message = body.get("error") if isinstance(body, dict) else None
            if isinstance(message, str):
                result["error_category"] = categories.get(message, "permit_insert_failed" if message.startswith("Managed permit insert failed: ") else "unclassified_http_error")
    except (OSError, ValueError, TypeError, UnicodeError, RecursionError):
        pass
    finally:
        error.close()
    return result


def endpoint_request(control: dict, secret: str, base_url: str) -> dict:
    parsed = urlparse(base_url)
    require(parsed.scheme == "https" and parsed.netloc == SUPABASE_HOST and parsed.path in {"", "/"}, "Wrong Supabase project")
    request = Request(f"{base_url.rstrip('/')}/functions/v1/content-publish",
                      data=json.dumps(control, separators=(",", ":")).encode(), method="POST",
                      headers={"Content-Type": "application/json", "x-managed-permit-issuer-secret": secret})
    try:
        with urlopen(request, timeout=20) as response:
            body = json.load(response)
    except HTTPError as error:
        diagnostic = safe_control_http_diagnostic(error, control)
        raise PermitEvidenceError("Managed permit HTTP rejection: " + json.dumps(diagnostic, sort_keys=True)) from None
    require(body.get("ok") is True, "Permit issuer endpoint did not confirm success")
    return body


def validate_new_permit_target(target: dict, *, assistant_acceptance: dict | None = None) -> None:
    """Keep historical evidence readable without reissuing a colliding action."""
    from paid_three_page_bounded_cms import MODEL as bounded_model
    if target.get('candidate_shape') == 'professional_cms_source_selfcheck_v1':
        from professional_cms_issuer import acceptance
        require(isinstance(assistant_acceptance,dict) and assistant_acceptance==acceptance(ROOT,target,assistant_acceptance.get('operation')),
                "Actual current professional selfcheck, not registration, is required")
        return
    if target.get('candidate_shape') == 'owner_authorized_shop_office_six_field_v4':
        require(isinstance(assistant_acceptance, dict), 'Exact original publisher selfcheck required; registration is not a permit')
        from tools.shop_office_six_field_execution import acceptance
        require(assistant_acceptance == acceptance(ROOT, target, assistant_acceptance.get('operation', 'publish')), 'Original registered current selfcheck/effect source differs')
    if target.get("candidate_shape") == bounded_model:
        require(isinstance(assistant_acceptance, dict)
                and assistant_acceptance.get("acceptance_model") == bounded_model,
                "Original T3 cannot use legacy or full-goal PASS as candidate admission")
        if "publication_state" in target.get("bounded_row", {}) and assistant_acceptance.get("operation") == "publish":
            require(target["bounded_row"].get("publication_state") == "pending_save"
                    and target["bounded_row"].get("publish_allowed") is True
                    and assistant_acceptance.get("row") == target["bounded_row"],
                    "Original T3 Saved or unresolved effects cannot issue another publish permit")
    if target.get("candidate_shape") == "english_kitchen_en2_exact":
        require(target == english_kitchen_en2_targets(ROOT)["english-kitchen-en2-exact-v1"]
                and isinstance(assistant_acceptance, dict),
                "Kitchen EN2 registration alone cannot issue a permit; exact current A2 acceptance is required")
    if target.get("candidate_shape") == "two_original_material_body_registration_only_v1":
        from paid_three_page_bounded_cms import two_original_material_readiness
        require(isinstance(assistant_acceptance, dict),
                "Two-material registration alone cannot issue a permit")
        two_original_material_readiness(ROOT, target, assistant_acceptance)
    if target.get('candidate_shape') == 'native_publisher_registration':
        raise PermitEvidenceError('Publisher registration cannot issue a permit; protected preview and exact production QA remain required')
    if target.get("candidate_shape") == "native_five_projection_registration":
        raise PermitEvidenceError("Five-source registration has no separately reviewed production capability or exact protected preview; no new permit")
    if target.get("candidate_shape") == "native_shop_children_body_registration":
        raise PermitEvidenceError("Shop/children registration has no separately deployed native capability or exact protected preview; no new permit")
    if target.get("candidate_shape") == "native_wave234_body_registration":
        raise PermitEvidenceError("Wave234 body registration has no separately reviewed production capability or protected preview; no new permit")
    if target.get("candidate_shape") == "native_remaining186_blog_registration":
        raise PermitEvidenceError("Remaining186 Blog registration has no deployed native capability or exact protected preview; no new permit")
    if target.get("candidate_shape") == "native_repair_faq_registration":
        raise PermitEvidenceError("Repair FAQ registration has no deployed native capability or exact protected preview; no new permit")
    if target.get('candidate_shape') == 'native_publisher_sparse_admission':
        if assistant_acceptance is None:
            try:
                require_actual_release_qa_pin(ROOT, target)
            except ValueError as error:
                raise PermitEvidenceError(str(error)) from error
        # main() still consumes exact acceptance/decision, protected preview,
        # single-use policy, actor/freshness/main-SHA and the protected endpoint.
    require(not target.get("retired_for_new_permit", False),
            "Target action identity is retired; use its independently reviewed row-specific successor")
    if target.get("candidate_shape") == "native_bilingual_body":
        require(target.get("native_registration_only") is False
                and target.get("release_ready") is True,
                "Native registration has no actual release readiness; exact QA and protected preview required")
    if target.get("candidate_shape") in {"org020_field_patch", "native_bilingual_body"}:
        if assistant_acceptance is None:
            pin = target.get("qa_outbox")
            require(bool(pin) and len(pin) == 2 and len(str(pin[1])) == 64,
                    "ORG-020 target has no pinned actual fixed QA outbox")
    if assistant_acceptance is not None:
        if assistant_acceptance.get("acceptance_model") == SELF_CHECK_EXECUTION_MODEL:
            require(assistant_acceptance.get("verdict")=="selfcheck_ready"
                    and assistant_acceptance.get("task_id")==target["task_id"]
                    and assistant_acceptance.get("scope")==target["scope"]
                    and assistant_acceptance.get("candidate",{}).get("sha256")==target["candidate"][1]
                    and assistant_acceptance.get("execution_preflight_event_id")
                    and assistant_acceptance.get("goal_completion_claimed") is False,
                    "Exact ordinary selfcheck readiness required; not an assistant verdict")
            return
        if assistant_acceptance.get("acceptance_model") == CONDO_FAQ_CANDIDATE_ACCEPTANCE_MODEL:
            require(target == CONDO_FAQ_V7_TARGET
                    and assistant_acceptance.get("operation") == "publish"
                    and assistant_acceptance.get("task_id") == target["task_id"]
                    and assistant_acceptance.get("scope") == target["scope"]
                    and assistant_acceptance.get("candidate_version") == target["candidate_version"]
                    and assistant_acceptance.get("verdict") == "pass_candidate_only"
                    and assistant_acceptance.get("goal_completion_claimed") is False
                    and assistant_acceptance.get("production_write_allowed") is False
                    and assistant_acceptance.get("candidate", {}).get("sha256") == target["candidate"][1]
                    and assistant_acceptance.get("candidate_acceptance_record_id")
                    and assistant_acceptance.get("candidate_acceptance_record_hash"),
                    "Only the original independent condo FAQ candidate may enter the protected permit path")
            return
        from paid_three_page_bounded_cms import TASK as bounded_task, MODEL as bounded_model, exact_tuple
        if assistant_acceptance.get("acceptance_model") == bounded_model:
            require(target.get("task_id") == bounded_task and target.get("candidate_shape") == bounded_model
                    and exact_tuple(target.get("task_id"), target.get("action_id"), target.get("scope"), target.get("execution_owner"))
                    and assistant_acceptance.get("task_id") == bounded_task
                    and assistant_acceptance.get("scope") == target.get("scope")
                    and assistant_acceptance.get("verdict") == ("pass_candidate_only" if assistant_acceptance.get("operation") == "publish" else "pass_rollback_candidate_only")
                    and assistant_acceptance.get("candidate_acceptance_record_id"),
                    "Exact original bounded candidate acceptance required")
            return
        require(assistant_acceptance.get("acceptance_model") == "goal_delivery_assistant_v1"
                and assistant_acceptance.get("task_id") == target["task_id"]
                and assistant_acceptance.get("scope") == target["scope"]
                and assistant_acceptance.get("verdict") == "pass",
                "Current exact assistant acceptance required for a modern permit target")


def exact_execution_scope(root: Path, target: dict) -> str:
    """Physical transport only; ordinary policy/contract scope is unchanged."""
    if target.get('candidate_shape') == 'professional_cms_source_selfcheck_v1':
        from professional_cms_issuer import exact
        return exact(root,target)['execution_scope']
    if target.get("candidate_shape") == "owner_authorized_shop_office_six_field_v4":
        from tools.shop_office_six_field_execution import physical_scope
        return physical_scope(root, target)
    return target["scope"]


def main() -> None:
    # Reuse parsing/native proofs only inside this invocation. No disk PASS,
    # policy or permit cache; all observed bytes are fenced before HTTP issue.
    raise ValueError("public_template_has_no_native_authorization")
    with wc.request_validation_context() as validation:
        _main(validation)


def _main(validation) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    from paid_three_page_bounded_cms import ROWS as bounded_rows, MODEL as bounded_model, targets as bounded_targets
    bounded_names = {f"paid-three-page-{slug}-exact-fields-v1" for slug, _, _ in bounded_rows}
    parser.add_argument("--target", choices=sorted(set(_current_registered_targets(ROOT)) | bounded_names), required=True)
    parser.add_argument("--operation", choices=["publish", "rollback"], required=True)
    parser.add_argument("--dry-run-run-id", type=int, required=True)
    parser.add_argument("--operations-decision", required=True)
    parser.add_argument("--policy-decision-id", required=True)
    parser.add_argument("--github-actor-id", type=int, required=True)
    parser.add_argument("--parent-permit-id")
    parser.add_argument("--parent-run-id", type=int)
    parser.add_argument("--issue-and-dispatch", action="store_true")
    args = parser.parse_args()
    target = bounded_targets(ROOT)[args.target] if args.target in bounded_names else _current_registered_targets(ROOT)[args.target]
    if target.get("candidate_shape") == "owner_authorized_shop_office_six_field_v4":
        from tools.shop_office_six_field_execution import target_for
        target = target_for(ROOT, target["action_id"])
        validation.strict_unchanged = True
    require(args.operation != "rollback" or target.get("rollback_allowed", True),
            "Rollback to the prior public media is not rights-safe")
    parent_binding = rollback_parent_binding(args.target, args.operation,
                                             args.parent_permit_id, args.parent_run_id)
    now = datetime.now(timezone.utc)
    evidence_root = target.get("evidence_root", ROOT)
    exact_file(evidence_root, target["candidate"])
    exact_file(evidence_root, target["rollback"])
    qa = validate_qa(ROOT, target, args.operation, allow_blocked_retry=True)
    if args.issue_and_dispatch:
        validate_new_permit_target(target, assistant_acceptance=qa if qa.get("acceptance_model") else None)
    require(args.github_actor_id > 0, "GitHub actor ID must be positive")

    artifact_root = ROOT / "logs/permit-artifacts"
    artifact_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="managed-cms-", dir=artifact_root) as temporary:
        folder = Path(temporary)
        run, receipt, digest, backup_path = artifact_for_run(args.dry_run_run_id, args.target, folder)
        require(run.get("actor", {}).get("id") == args.github_actor_id, "Dry-run GitHub actor does not match the intended publisher")
        require(now - timedelta(minutes=30) <= timestamp(run["updated_at"]) <= now,
                "Protected dry-run is stale or future-dated")
        expected_action = target["action_id"] if args.operation == "publish" else f"rollback-{target['candidate_version']}"
        receipt_version = qa["candidate_version"] if (qa.get("acceptance_model") == bounded_model or target.get("candidate_shape") in {"owner_authorized_shop_office_six_field_v4","professional_cms_source_selfcheck_v1"}) else target["candidate_version"]
        receipt_versions = {receipt_version}
        if target.get("candidate_shape") in {"owner_authorized_shop_office_six_field_v4","professional_cms_source_selfcheck_v1"} and args.operation == "rollback":
            receipt_versions.add(target["candidate_version"])  # Existing CLI artifacts retain the base candidate; permit identity is still inverse.
        require(receipt.get("task_id") == target["task_id"] and receipt.get("candidate_version") in receipt_versions
                and receipt.get("action_id") == expected_action and receipt.get("operation") == args.operation
                and receipt.get("scope") == exact_execution_scope(ROOT, target),
                "Dry-run receipt target differs from the locked candidate")
        require(digest.get("task_id") == target["task_id"] and digest.get("operation") == args.operation
                and len(str(digest.get("payload_sha256", ""))) == 64,
                "Payload digest evidence missing")
        payload_sha256 = digest["payload_sha256"]
        rollback_digest = json.loads((backup_path.parent / "rollback-payload-digest.json").read_text()) if args.operation == "publish" else None
        if args.operation == "publish":
            require(rollback_digest.get("task_id") == target["task_id"] and len(str(rollback_digest.get("payload_sha256", ""))) == 64,
                    "Prior version rollback digest missing")
            require(json.loads(backup_path.read_text()).get("record", {}).get("id") == target["record_id"],
                    "Parent backup does not contain the target record")
        else:
            require(json.loads(backup_path.read_text()).get("record", {}).get("id") == target["record_id"],
                    "Rollback readback does not contain the target record")

        exact_reverse_binding = None
        if target.get('candidate_shape') == 'professional_cms_source_selfcheck_v1':
            from professional_cms_issuer import artifacts
            artifacts(ROOT,target,args.operation,qa,receipt,digest,json.loads(backup_path.read_text()),args.parent_permit_id,args.parent_run_id)
        if target.get("candidate_shape") == "owner_authorized_shop_office_six_field_v4" and args.operation == "rollback":
            from tools.shop_office_six_field_execution import reverse_artifacts
            exact_reverse_binding = reverse_artifacts(ROOT, target, qa, run, receipt, digest,
                json.loads(backup_path.read_text()), args.parent_permit_id, args.parent_run_id)
        bound_machine = None
        if qa.get("acceptance_model") == bounded_model:
            from paid_three_page_bounded_cms import validate_issuer_machine
            bound_machine = validate_issuer_machine(ROOT, target, qa, run,
                json.loads((backup_path.parent / "managed-identity-probe.json").read_text()),
                args.github_actor_id, digest, receipt)
            if args.operation == "rollback":
                require(args.parent_permit_id == qa["parent_permit_id"] and args.parent_run_id == qa["parent_run_id"],
                        "Rollback issuer must use independently reviewed completed parent permit/run")
        if target.get("candidate_shape") == "two_original_material_body_registration_only_v1":
            from paid_three_page_bounded_cms import validate_two_original_material_machine
            require(args.operation == "publish" and payload_sha256 == target["payload_sha256"],
                    "Two original material bodies only allow their exact forward payload")
            validate_two_original_material_machine(ROOT, target, qa, run,
                json.loads((backup_path.parent / "managed-identity-probe.json").read_text()),
                digest, receipt, json.loads(backup_path.read_text()), args.github_actor_id)
        decision_path = (ROOT / args.operations_decision).resolve()
        require(decision_path.is_relative_to(ROOT) and decision_path.is_file(), "Operations decision file is missing")
        decision = json.loads(decision_path.read_text())
        if qa.get("acceptance_model") in {"goal_delivery_assistant_v1", SELF_CHECK_EXECUTION_MODEL, bounded_model,
                                          CONDO_FAQ_CANDIDATE_ACCEPTANCE_MODEL, "professional_cms_source_selfcheck_v1"}:
            validate_goal_cms_policy(ROOT, target["task_id"], expected_action, target["scope"],
                                     target.get("execution_owner", ""), payload_sha256)
            operations = validate_goal_cms_decision(ROOT, decision, target, args.operation,
                                                    payload_sha256, qa, now)
        else:
            operations = validate_operations(decision, target, args.operation,
                                             payload_sha256, qa["receipt_id"], now)
        policies = [json.loads(line) for line in (ROOT / "logs/policy-decisions.jsonl").read_text().splitlines() if line.strip()]
        matches = [row for row in policies if row.get("decision_id") == args.policy_decision_id]
        require(len(matches) == 1, "Exact policy decision ID is missing or ambiguous")
        policy = validate_policy(matches[0], target, args.operation, payload_sha256, operations, now)
        validate_retry_state(ROOT, target, args.operation, policy)
        require(timestamp(qa["created_at"]) <= timestamp(operations["decided_at"]),
                "Operations decision predates QA PASS")

        acceptance_id = qa.get("candidate_acceptance_record_id", qa.get("receipt_id"))
        acceptance_hash = qa.get("candidate_acceptance_record_hash", qa.get("receipt_hash"))
        require(bool(acceptance_id) and bool(acceptance_hash), "Actual current acceptance record required")
        evidence = {"candidate": target["candidate"][1], "rollback": target["rollback"][1],
                    "qa_receipt_hash": acceptance_hash, "acceptance_model": qa.get("acceptance_model", "legacy_QA"), "operations_file_sha256": sha256_file(decision_path),
                    "policy_decision_id": policy["decision_id"], "dry_run_id": args.dry_run_run_id,
                    "dry_run_receipt_sha256": sha256_file(backup_path.parent / "locked-dry-run-receipt.json"),
                    "payload_sha256": payload_sha256}
        if target.get("candidate_shape") == "owner_authorized_shop_office_six_field_v4":
            from tools.shop_office_six_field_execution import scope_carrier
            evidence["physical_scope_carrier"] = scope_carrier(ROOT)
            evidence["business_scope"] = target["scope"]
            evidence["execution_scope"] = exact_execution_scope(ROOT, target)
        if target.get('candidate_shape') == 'professional_cms_source_selfcheck_v1':
            evidence.update(physical_scope_carrier=target['issuer_contract'],business_scope=target['scope'],
                            execution_scope=exact_execution_scope(ROOT,target))
        if exact_reverse_binding is not None:
            evidence["exact_original_reverse_binding"] = exact_reverse_binding
        evidence_sha256 = hashlib.sha256(json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        action_id = target["action_id"] if args.operation == "publish" else f"rollback-{target['candidate_version']}"
        candidate_version = target["candidate_version"] if args.operation == "publish" else f"{target['candidate_version']}-rollback-v1"
        request = {"controlAction": "issue", "permitId": str(uuid4()), "taskId": target["task_id"],
                   "actionId": action_id, "actionClass": "cms_write", "operation": args.operation,
                   "scope": exact_execution_scope(ROOT, target), "candidateVersion": candidate_version,
                   "recordId": target["record_id"], "slug": target["slug"],
                   "expectedUpdatedAt": digest["expected_updated_at"], "payloadSha256": payload_sha256,
                   "rollbackPayloadSha256": rollback_digest["payload_sha256"] if rollback_digest else None,
                   **parent_binding,
                   "githubActorId": bound_machine["github_actor_id"] if bound_machine else args.github_actor_id,
                   "githubWorkflowSha": (bound_machine["workflow_sha"] if bound_machine else
                       json.loads((backup_path.parent / "managed-identity-probe.json").read_text())["identity"]["workflowSha"]),
                   # Existing endpoint carrier; this is the real committed candidate
                   # record for bounded T3, not a fabricated qa_verdict receipt.
                   "qaReceiptId": acceptance_id, "operationsDecisionId": operations["decision_id"],
                   "policyDecisionId": policy["decision_id"], "issuerEvidenceSha256": evidence_sha256,
                   "expiresAt": (now + timedelta(minutes=10)).isoformat().replace("+00:00", "Z")}
        if not args.issue_and_dispatch:
            print(json.dumps({"status": "LOCAL_EVIDENCE_VALIDATED", "target": args.target,
                              "operation": args.operation, "dry_run_run_id": args.dry_run_run_id,
                              "evidence_sha256": evidence_sha256, "production_write": False}))
            return
        current_main = gh_json("api", f"repos/{REPOSITORY}/commits/main")
        require(current_main.get("sha") == run["head_sha"],
                "Main changed after the protected dry-run; obtain fresh QA and dry-run evidence")
        secret = load_protected_issuer_secret()
        base_url = os.environ.get("SUPABASE_URL", "")
        if args.operation == "rollback" and args.target in PARENT_RUN_TARGETS:
            parent_status = endpoint_request({"controlAction": "status", "permitId": args.parent_permit_id},
                                             secret, base_url)
            validate_completed_parent_status(parent_status, target, args.parent_permit_id, args.parent_run_id)
            if target.get("candidate_shape") == "owner_authorized_shop_office_six_field_v4":
                from tools.shop_office_six_field_execution import live_reverse_parent
                live_reverse_parent(ROOT, target, qa, parent_status, args.parent_permit_id, args.parent_run_id, request["permitId"])
            if qa.get("acceptance_model") == bounded_model:
                from paid_three_page_bounded_cms import doc as bounded_document
                require(parent_status == bounded_document(ROOT, qa["completed_parent"])
                        and parent_status.get("savedUpdatedAt") == qa["row"]["raw_updated_at"]
                        and request["permitId"] != args.parent_permit_id,
                        "Exact actual SavedCAS/completed parent and new distinct rollback permit required")
        if target.get("candidate_shape") == "owner_authorized_shop_office_six_field_v4":
            from tools.shop_office_six_field_execution import final_instance_check
            validation.recheck()
            final_instance_check(ROOT, policy, target)
        issued = endpoint_request(request, secret, base_url)
        require(issued.get("status") == "issued" and issued.get("permitId") == request["permitId"],
                "Permit issue receipt mismatch; inspect status before retry")
        fields = ["-f", "mode=publish", "-f", f"target={args.target}",
                  "-f", f"managed_operation={args.operation}",
                  "-f", f"managed_permit_id={request['permitId']}"]
        if args.operation == "rollback":
            fields += ["-f", f"parent_run_id={args.parent_run_id}"]
        subprocess.run(["gh", "workflow", "run", "content-publish-approved.yml", "-R", REPOSITORY,
                        "--ref", "main", *fields], check=True, capture_output=True)
        print(json.dumps({"status": "DISPATCHED", "target": args.target, "operation": args.operation,
                          "permit_id_sha256": hashlib.sha256(request["permitId"].encode()).hexdigest(),
                          "evidence_sha256": evidence_sha256, "production_write": "pending-run-result"}))


from professional_cms_issuer import targets as _professional_cms_targets
PROFESSIONAL_CMS_TARGETS = {}
if set(PROFESSIONAL_CMS_TARGETS)&set(TARGETS):
    raise ValueError('Professional CMS target collides with existing identity')
TARGETS.update(PROFESSIONAL_CMS_TARGETS)
PARENT_RUN_TARGETS = frozenset()

if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError:
        raise SystemExit("BLOCKED_MANAGED_CMS_PERMIT: External GitHub command failed; inspect permit status before retry")
    except (PermitEvidenceError, OSError, ValueError, KeyError) as error:
        raise SystemExit(f"BLOCKED_MANAGED_CMS_PERMIT: {error}")
