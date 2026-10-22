"""Read the original T3 candidate acceptance; never issue permission or a goal PASS.

The three tuples come from the original publisher, not a generic scope alias.
An independent native V2 and a committed continue are necessary even when the
producer has a full-goal verdict. Production preflight remains a separate gate.
"""
from __future__ import annotations

import datetime as dt
import difflib
import functools
import hashlib
import json
import re
import subprocess
from pathlib import Path

import workflow_control as w

TASK = "fc-20261010-paid-three-page-exact-publication-followthrough-v1"
SCOPE = "project:flashcast:paid-three-page-original-publication-followthrough:v1"
VERSION = "paid-three-page-exact-native-diff-v1-20261010"
ROLLBACK_VERSION = VERSION + "-rollback-v1"
ROLE = "operations-assistant-2"
PRODUCER = "publishing"
MODEL = "paid_three_page_bounded_cms_candidate_v1"
BASE = f"drafts/publishing/{TASK}"
ROWS = (("builtin", "b401a610-a4dc-4a0b-a7e0-efcac6c81d71", ("content_zh",)),
        ("kitchen", "ce4156db-9034-42c8-ba29-b35724ea7d6d", ("title_zh", "excerpt_zh")),
        ("renovation", "0d947129-0595-43ef-baa1-0fd9d8b870e6", ("title_zh", "excerpt_zh")))
SOURCES = ("tools/paid_three_page_bounded_cms.py", "tools/qa_review_plan.py",
           "tools/managed_cms_permit_issuer.py", "tools/goal_delivery_runtime.py",
           "tools/workflow_control.py")
FLAGS = ("production_write_allowed", "production_release_eligible", "external_permission_issued")
WEBSITE = Path("<WEBSITE_PROJECT_ROOT>")
DEPLOYMENT_EVIDENCE = "reports/paid-three-page-exact-entry-repair-20261010/production-closeout-20261010"
WEBSITE_SOURCE_VERSION = "paid-three-page-exact-entry-source-v3-20261010"
WORKFLOW_CLI = (".github/workflows/content-publish-approved.yml",
                "scripts/managed-cms-targets-paid-three-page-v1.mjs",
                "scripts/publish-content-trust-fixes.mjs")


def require(condition, message):
    if not condition:
        raise w.WorkflowError("bounded T3 CMS: " + message)


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(",", ":")).encode("utf-8")).hexdigest()


def strict(reader):
    @functools.wraps(reader)
    def read(*args, **kwargs):
        try:
            return reader(*args, **kwargs)
        except (OSError, ValueError, TypeError, KeyError, AttributeError, StopIteration) as error:
            raise w.WorkflowError("bounded T3 CMS: malformed or changed exact evidence: " + str(error)) from error
    return read


def pin(root, value):
    require(isinstance(value, dict), "frozen pin required")
    # Original publisher pins use absolute paths and bytes. Read those exact
    # bytes, but return the company's canonical pin; never rewrite the source.
    path = Path(str(value.get("path", "")))
    if path.is_absolute():
        require(path.resolve().is_relative_to(Path(root).resolve()), "evidence must belong to this project")
        path = path.resolve().relative_to(Path(root).resolve())
    actual = w.file_digest(root, str(path))
    require(actual["sha256"] == value.get("sha256")
            and actual["size"] == value.get("size", value.get("bytes")), "frozen source bytes changed")
    return actual


def doc(root, value):
    value = pin(root, value)
    def unique(pairs):
        result = {}
        for key, item in pairs:
            require(key not in result, "unambiguous frozen JSON fields required")
            result[key] = item
        return result
    result = json.loads(w.safe_path(root, value["path"]).read_bytes(), object_pairs_hook=unique)
    require(isinstance(result, dict), "object evidence required")
    require(not any(result.get(key) is True for key in
            ("fixture_only", "simulation", "simulated", *FLAGS)), "actual evidence without production permission required")
    return result


def exact_tuple(task, action, scope, department, action_class="cms_write"):
    return task == TASK and department == PRODUCER and action_class == "cms_write" and any(
        action in {f"paid-three-page-{slug}-exact-fields-v1", f"rollback-{VERSION}"}
        and scope == f"company.example:services/{record}:{','.join(fields)}"
        for slug, record, fields in ROWS)


# The V5 producer has a distinct, frozen shape. Do not alias a V3/V4 field,
# edit the producer's evidence, or infer a successful preview for a Saved row.
EFFECT_SCHEMA = "actual_t3_mixed_saved_effects_v1"
V5_EVIDENCE = ("actual_existing_Saved_ID_receipts", "actual_current_workflow_source",
               "actual_current_frontend_version", "actual_main_and_deployed_source_comparison")


def _v5_shape(root, current):
    evidence = current.get("evidence", {})
    present = [key in evidence for key in V5_EVIDENCE]
    if not any(present):
        return False
    require(all(present) and "source_and_original_backups" not in evidence,
            "one explicit V5 producer evidence shape required")
    facts = doc(root, evidence["actual_machine_identity_and_preview_facts"])
    require(facts.get("task_id") == TASK and facts.get("candidate_version") == VERSION
            and facts.get("original_source_candidate_version") == WEBSITE_SOURCE_VERSION
            and facts.get("new_permits_issued") == facts.get("new_CMS_Save") == 0
            and facts.get("actual_time_not_overwritten") is True
            and "native_frontend_loaded_sha" not in facts
            and "website_deployed_source_candidate_version" not in facts,
            "actual V5 facts required without old-field aliases or invented writes")
    for key in V5_EVIDENCE:
        pin(root, evidence[key])
    return True


def _v5_row_effect(root, current, fresh, row, before, desired, artifacts):
    """Observe the complete current row; an incomplete effect never permits Save."""
    facts = {"schema": EFFECT_SCHEMA, "publication_state": "effect_unresolved", "publish_allowed": False,
             "current_record": pin(root, fresh["backup"]), "dependencies": []}
    try:
        after_pin = pin(root, fresh.get("after_readback"))
        require(artifacts.count(after_pin) == 1, "current after-readback must be frozen once")
        native = doc(root, facts["current_record"])
        require(set(native) == set(before) and native.get("id") == row["record_id"]
                and doc(root, after_pin) == native
                and native.get("updated_at") == fresh.get("raw_updated_at")
                and native.get("version") == fresh.get("native_version")
                and type(native.get("version")) is int and native["version"] > 0,
                "complete stable current native ID/CAS/version required")
        facts.update(current_after_readback=after_pin, current_raw_updated_at=native["updated_at"],
                     current_native_version=native["version"], current_full_sha256=digest(native))
        receipts_pin = pin(root, current["evidence"]["actual_existing_Saved_ID_receipts"])
        receipts = doc(root, receipts_pin)
        require(receipts.get("task_id") == TASK and receipts.get("read_only") is True
                and receipts.get("new_Save_by_this_publisher") == 0,
                "historical effects must be distinct from this preview's zero writes")
        matches = [entry for entry in receipts.get("records", []) if entry.get("slug") == row["slug"]]
        require(len(matches) <= 1, "duplicate Saved effect forbidden")
        if native == before and not matches:
            require(row["slug"] == "renovation", "V5 remaining Save is only the original renovation row")
            facts.update(publication_state="pending_save", publish_allowed=True)
            return facts
        require(len(matches) == 1, "unknown current effect needs source reconciliation")
        entry = matches[0]
        receipt_pin = pin(root, entry.get("actual_publish_receipt"))
        require(artifacts.count(receipt_pin) == 1, "historical publish receipt must be frozen once")
        receipt = doc(root, receipt_pin)
        saved = receipt.get("published", {})
        require(receipt.get("target") == row["action_id"] and receipt.get("operation") == "optimize"
                and saved.get("ok") is True and saved.get("dry_run") is False
                and saved.get("content_type") == "service" and saved.get("action") == "publish"
                and saved.get("slug") == row["slug"] and saved.get("status") == "published"
                and saved.get("existing_id") == saved.get("saved_id") == entry.get("actual_existing_SavedID") == row["record_id"]
                and saved.get("saved_updated_at") == entry.get("saved_raw_updated_at") == native["updated_at"]
                and native["updated_at"] != before["updated_at"]
                and all(native[k] == desired[k] for k in row["changed_fields"])
                and all(native[k] == before[k] for k in native if k not in {*row["changed_fields"], "updated_at", "version"})
                and type(entry.get("original_run_id")) is int and entry["original_run_id"] > 0,
                "exact historical nested Save, current SavedCAS and all retained values required")
        facts.update(publication_state="saved_effect_observed_no_replay", saved_id=saved["saved_id"],
                     saved_raw_updated_at=saved["saved_updated_at"], historical_run_id=entry["original_run_id"],
                     saved_receipt=receipt_pin, saved_effect_source=receipts_pin,
                     original_postcheck_ok=receipt.get("postcheck", {}).get("ok"),
                     dependencies=["original_completed_permit_authority_and_source_mapping",
                                   "successful_protected_rollback_preview_and_new_independent_rollback_review"])
    except (w.WorkflowError, OSError, ValueError, TypeError, KeyError, AttributeError) as error:
        facts["dependencies"] = ["exact_saved_effect_reconciliation: " + str(error)]
    return facts


def _saved_parent(root, row, value, authority, original_machine_source):
    """Read a genuine original parent; never fabricate an earlier company PASS."""
    require(row.get("current_full_Saved_readback_verified") is not False
            and row.get("current_raw_updated_at") == row.get("saved_raw_updated_at"),
            "partial Saved notice prevents recovery until complete exact native reread")
    parent = doc(root, value)
    require(parent.get("schema") == EFFECT_SCHEMA + "_completed_parent"
            and parent.get("task_id") == TASK and parent.get("candidate_version") == VERSION
            and parent.get("action_id") == row["action_id"] and parent.get("scope") == row["scope"]
            and parent.get("record_id") == row["record_id"] and parent.get("original_authority") == authority
            and parent.get("native_batch_permission_inherited") is False
            and parent.get("historical_company_PASS_invented") is False,
            "independent exact original parent/authority mapping required")
    from managed_cms_permit_issuer import validate_completed_parent_status
    status = doc(root, parent.get("completed_status"))
    # Freeze the original safe issuer response, not a rewritten status object.
    if status.get("schema") in {"A2-original-issuer-kitchen-permit-readonly-status/v1",
                                 "A2-original-issuer-builtin-permit-readonly-status/v1"}:
        require(status.get("read_only") is True and status.get("endpoint") == "https://rbsnyexjifounogswrjp.supabase.co/functions/v1/content-publish",
                "original protected issuer readback required")
        status = status["actual_safe_response"]
    if status.get("schema") == "A2-original-issuer-renovation-permit-readonly-status/v1":
        frozen_status = pin(root, parent["completed_status"])
        require(frozen_status["sha256"] == "9dc8d68e1cc20e16b301f22a2a7934c63ebdfecf017bc647afc490a557cb201e"
                and frozen_status["size"] == 1085 and status.get("task_id") == TASK
                and status.get("read_only") is True and status.get("status_request_succeeded") is True
                and status.get("exact_original_tuple_and_SavedCAS_match") is True
                and status.get("request", {}).get("controlAction") == "status"
                and type(status.get("root_new_Save")) is int and status["root_new_Save"] == 0
                and type(status.get("root_new_permit_issued")) is int and status["root_new_permit_issued"] == 0
                and status.get("formal_T3_PASS") is False and status.get("secret_logged_or_persisted") is False,
                "exact actual third original completed status readback required")
        status = status["actual_safe_response"]
    validate_completed_parent_status(status, {"task_id": TASK, "action_id": row["action_id"],
        "candidate_version": VERSION, "record_id": row["record_id"]}, parent.get("parent_permit_id"), parent.get("parent_run_id"))
    require(status.get("ok") is True and status.get("savedUpdatedAt") == row["saved_raw_updated_at"]
            and status.get("githubRunId") == row["historical_run_id"]
            and type(status.get("githubRunAttempt")) is int and status["githubRunAttempt"] > 0,
            "completed parent must be the observed original Save and exact SavedCAS")
    require(pin(root, parent.get("original_machine_source")) == pin(root, original_machine_source),
            "historical recovery must retain the independently frozen original machine channel")
    machine = doc(root, original_machine_source)["actual_original_machine_channel_metadata"]
    run = doc(root, parent.get("full_original_gh_run"))
    probe = doc(root, parent.get("identity_probe"))
    payload = doc(root, parent.get("payload_digest"))
    require(run.get("id") == status["githubRunId"] and run.get("run_attempt") == status["githubRunAttempt"]
            and run.get("actor", {}).get("id") == machine["existing_actor_id"]
            and run.get("repository", {}).get("id") == probe.get("identity", {}).get("repositoryId") == 1248188229
            and run.get("repository", {}).get("full_name") == machine["repository"]
            and run.get("workflow_id") == machine["workflow_id"] and run.get("path") == machine["workflow_path"]
            and run.get("event") == "workflow_dispatch" and run.get("head_branch") == "main"
            and probe.get("ok") is True and probe.get("dry_run") is True
            and probe.get("performed_write") is False
            and probe.get("identity") == {"repositoryId": 1248188229, "actorId": machine["existing_actor_id"],
                "workflowRef": machine["repository"] + "/" + machine["workflow_path"] + "@refs/heads/main",
                "runId": run["id"], "runAttempt": run["run_attempt"], "workflowSha": run["head_sha"]}
            and payload.get("task_id") == TASK and payload.get("operation") == "publish"
            and payload.get("expected_updated_at") == row["raw_updated_at"]
            and w.SHA256_PATTERN.fullmatch(str(payload.get("payload_sha256", ""))) is not None,
            "raw historical actor/run/attempt/OIDC/original payload required")
    issued = doc(root, parent.get("issued_evidence"))
    issued_context = issued.get("evidence", {})
    require(issued.get("issued", {}).get("permitId") == status["permitId"]
            and issued["issued"].get("operation") == "publish"
            and issued_context.get("target") == row["action_id"]
            and issued_context.get("identity") == probe["identity"]
            and issued_context.get("actualPayloadSha256") == payload["payload_sha256"]
            and all(isinstance(issued_context.get(key), str) and issued_context[key]
                    for key in ("authorizationId", "operationsDecisionId", "policyDecisionId")),
            "actual historical issued permit/target/payload/identity/authority chain required")
    source_review = doc(root, parent.get("historical_source_review"))
    require(source_review.get("schema") == EFFECT_SCHEMA + "_historical_source_review"
            and source_review.get("reviewer") == ROLE and source_review.get("task_id") == TASK
            and source_review.get("action_id") == row["action_id"] and source_review.get("scope") == row["scope"]
            and source_review.get("full_original_gh_run") == parent["full_original_gh_run"]
            and source_review.get("saved_receipt") == row["saved_receipt"]
            and source_review.get("payload_digest") == parent["payload_digest"]
            and source_review.get("completed_status") == parent["completed_status"]
            and source_review.get("issued_evidence") == parent["issued_evidence"]
            and source_review.get("original_authority") == authority
            and source_review.get("source_branch") == "exact_original_target_branch_verified"
            and source_review.get("producer_summary_is_permission") is False,
            "new independent historical source/authority mapping required; effect does not grant native-batch permission")
    workflow = pin(root, source_review.get("workflow_source"))
    workflow_raw = w.safe_path(root, workflow["path"]).read_bytes()
    require((workflow["sha256"], workflow["size"]) in {
                ("fbaf3ba910422dcf858349642e84320ee85409e0e26379ee77a2ce0dda32cc0a", 20603),
                ("32eb9be1a7f90dad8ea4477da9ebad1e84421d3a5ea7acc2547786aa57512e50", 22350)}
            and _git_source(run["head_sha"], WORKFLOW_CLI[0]) == workflow_raw,
            "historical original branch requires exact immutable audited whole workflow")
    original_deployment_pin = source_review.get("deployment_source_proof")
    require(isinstance(original_deployment_pin, dict)
            and original_deployment_pin.get("sha256") == "032c9cb72e3aa45ff8b76f3921aa2c91f302a11453a5d6d32bc5d7f5398b9955"
            and original_deployment_pin.get("size", original_deployment_pin.get("bytes")) == 10892,
            "exact original actual deployed77 source proof required for historical recovery")
    original_deployment = _website_json(original_deployment_pin)
    require(original_deployment.get("status") == "PASS_ACTUAL_PRODUCTION_EDGE_SOURCE_AND_RECOVERY_BACKUP"
            and original_deployment.get("task_id") == TASK and original_deployment.get("run_id") == 38061480070
            and original_deployment.get("production_website_sha") == "5237d068b49a20a9ce6dc395f8c6a45d7f961d8b"
            and original_deployment.get("actual_function", {}).get("after_download_version") == 77,
            "genuine original deployment identity required")
    deployed = _website_json(source_review.get("runtime_manifest"))
    paths = sorted(entry["path"] for entry in deployed.get("files", []))
    require(len(paths) == 21 and len(set(paths)) == 21
            and deployed.get("schema") == "content-publish-runtime-source/v1"
            and source_review["runtime_manifest"].get("sha256") == "e46d5d31388d2ea98872c1dd6727003ccff80f1e1d4daec61ff457263fa6d39a",
            "original deployed runtime closure required for historical parent")
    mappings = source_review.get("runtime_files")
    require(isinstance(mappings, list) and sorted(entry["source_path"] for entry in mappings) == ["supabase/functions/" + path for path in paths],
            "all 21 original historical runtime files required")
    for entry in mappings:
        raw = _website_bytes(entry["deployed_snapshot"])
        definition = next(item for item in deployed["files"] if "supabase/functions/" + item["path"] == entry["source_path"])
        require(hashlib.sha256(raw).hexdigest() == definition["sha256"] and len(raw) == definition["bytes"]
                and _git_source(run["head_sha"], entry["source_path"]) == raw,
                "historical parent runtime differs from original deployment")
    cli = source_review.get("cli_files")
    require(isinstance(cli, list) and sorted(entry["source_path"] for entry in cli) == sorted(WORKFLOW_CLI[1:]),
            "both historical original CLIs required")
    for entry in cli:
        approved = [value for value in original_deployment["source_pins"] if value["path"] == entry["source_path"]]
        raw = _git_source(run["head_sha"], entry["source_path"])
        require(len(approved) == 1 and entry.get("sha256") == approved[0]["sha256"]
                and entry.get("size") == approved[0]["bytes"]
                and hashlib.sha256(raw).hexdigest() == entry["sha256"] and len(raw) == entry["size"]
                and raw == _git_source("5237d068b49a20a9ce6dc395f8c6a45d7f961d8b", entry["source_path"]),
                "historical original CLI bytes differ")
    # Current A2 bounded V2 freezes and independently attests all these pins.
    for key in ("completed_status", "full_original_gh_run", "identity_probe", "payload_digest", "historical_source_review", "issued_evidence"):
        pin(root, parent[key])
    return parent, status


def _effect_review(root, proof, expected, rows, box):
    value = pin(root, proof.get("effect_reconciliation"))
    effect = doc(root, value)
    header = {"schema": EFFECT_SCHEMA, "task_id": TASK, "candidate_version": VERSION,
              "reviewer": ROLE, "producer": PRODUCER,
              **{key: expected[key] for key in ("authority", "goal_contract", "review_plan", "current_producer", "bindings", "source_manifest")}}
    require(all(effect.get(k) == v for k, v in header.items()) and value in box.get("evidence", [])
            and all(effect.get(k) is False for k in FLAGS), "explicit independent frozen V5 effect review required")
    reviewed = effect.get("rows")
    require(isinstance(reviewed, list) and len(reviewed) == 3, "all three exact effect facts required")
    required = [value]
    for original, observed in zip(rows, reviewed):
        actual = dict(observed)
        parent = actual.pop("completed_parent", None)
        state = actual.get("publication_state")
        if state == "effect_reconciled":
            require(original.get("publication_state") == "saved_effect_observed_no_replay", "only an actual observed Save may reconcile")
            actual["publication_state"] = original["publication_state"]
            actual["dependencies"] = original["dependencies"]
            require(actual == original, "reconciliation cannot change original row or Saved effect")
            _saved_parent(root, original, parent, expected["authority"], expected["original_machine_source"])
            required += [pin(root, parent)]
        else:
            require(parent is None and actual == original, "review must retain recomputed effect facts and named dependencies")
    remaining = [r["action_id"] for r in rows if r.get("publication_state") == "pending_save"]
    require(remaining in ([], ["paid-three-page-renovation-exact-fields-v1"])
            and effect.get("remaining_publish_rows") == proof.get("remaining_publish_rows") == remaining,
            "only still-pending exact renovation may enter publication")
    require(all(p in box.get("evidence", []) for p in required), "new effect/parent proof must be frozen in the actual A2 V2")
    preflights = proof.get("execution_preflights")
    require(isinstance(preflights, list) and len(preflights) == len(remaining)
            and (not remaining or (preflights[0].get("action_id") == remaining[0]
                and preflights[0].get("operation") == "publish"
                and preflights[0].get("scope") == rows[2]["scope"])), "Saved rows cannot acquire new publish preflights")
    return value


# Accurate in-task read-only incremental evidence. This pin is an irreversible
# no-replay barrier, not permission, a replacement producer, or full native QA.
SAVED_EFFECT_UPDATE_PIN = {
    "path": "logs/handoffs/2026-10-10-paid-three-page-original-followthrough-v1/assistant2-owned/current-V5-bounded-review-preparation-v1/new-native-publish-38073003426-safe-effect-delta-readonly-v1.json",
    "sha256": "2ef2749a57036e5adcc2345f18c75e56ae343fc9bdb42969538cd4457296a14b", "size": 14830}


def _apply_saved_notices(root, rows):
    """A later observed Save blocks a stale pending snapshot, even before full reread."""
    notice = doc(root, SAVED_EFFECT_UPDATE_PIN)
    require(notice.get("schema") == "A2_new_native_publish_actual_effect_safe_allowlist_readonly_delta_v1"
            and notice.get("read_only_GET") is True and notice.get("run_id") == 38073003426
            and notice.get("workflow_sha") == "c4adb0bf4cd97eb6e3c76e619380783ec24372bb"
            and notice.get("source_api") == "repos/wangchaozhuanyong/zhuangxiuwangzhan/actions/artifacts/11677491592/zip"
            and notice.get("GitHub_metadata_digest") == "sha256:" + notice.get("archive_sha256", ""),
            "actual exact later Saved effect notice required; missing notice cannot revive old pending state")
    metadata = doc(root, notice["source_artifact_metadata_pin"])
    artifacts = metadata.get("artifacts", [])
    require(metadata.get("read_only_GET") is True and len(artifacts) == 1
            and artifacts[0].get("id") == 11677491592
            and artifacts[0].get("digest") == notice["GitHub_metadata_digest"]
            and artifacts[0].get("workflow_run", {}).get("id") == notice["run_id"]
            and artifacts[0]["workflow_run"].get("repository_id") == 1248188229
            and artifacts[0]["workflow_run"].get("head_sha") == notice["workflow_sha"],
            "later Saved artifact/run/repository/full archive digest must match")
    matches = [entry for entry in notice.get("selected_safe_JSON_fields_only", [])
               if entry.get("archive_path") == "paid-three-page-renovation-exact-fields-v1/publish-receipt.json"]
    require(len(matches) == 1 and matches[0].get("source_json_sha256") == "815a9f566a83c0c00bdeae846655e64b9c72ecbf0d727311cb4e567eb04b04c7"
            and matches[0].get("source_json_bytes") == 1835, "actual exact later renovation publish receipt required")
    receipt = matches[0]["safe_fields"]
    saved = receipt.get("nested_published", {})
    require(receipt.get("target") == "paid-three-page-renovation-exact-fields-v1" and receipt.get("operation") == "optimize"
            and saved.get("ok") is True and saved.get("dry_run") is False
            and saved.get("saved_id") == saved.get("existing_id") == ROWS[2][1]
            and saved.get("saved_updated_at") == "2026-10-10T17:45:51.559189+00:00"
            and saved.get("action") == "publish" and saved.get("content_type") == "service"
            and saved.get("slug") == "renovation", "later nested Save must block replay despite failed postcheck")
    result = [dict(row) for row in rows]
    row = result[2]
    if row.get("saved_raw_updated_at") != saved["saved_updated_at"]:
        row.update(publication_state="saved_effect_observed_no_replay", publish_allowed=False,
            saved_id=saved["saved_id"], saved_raw_updated_at=saved["saved_updated_at"],
            historical_run_id=notice["run_id"], saved_effect_notice=pin(root, SAVED_EFFECT_UPDATE_PIN),
            saved_receipt_source_sha256=matches[0]["source_json_sha256"],
            saved_receipt_source_bytes=matches[0]["source_json_bytes"], original_postcheck_ok=False,
            current_full_Saved_readback_verified=False,
            dependencies=["latest_complete_native_30_field_SavedCAS_and_retained_readback",
                          "original_completed_permit_authority_and_source_mapping",
                          "independent_public_postcheck_review_without_sixth_field_changes"])
    return result


def _rows(root, current):
    """Recompute all 90 values; preserve both publisher and website digests."""
    original = doc(root, current["evidence"]["original_V2"])
    bindings_pin = pin(root, original["evidence"]["bindings"])
    bindings = doc(root, bindings_pin)
    require(bindings.get("task_id") == TASK and bindings.get("candidate_version") == VERSION
            and bindings.get("delta_count") == 5 and len(bindings.get("records", [])) == 3,
            "original three-row/five-field bindings required")
    manifest_pin = pin(root, current["evidence"]["manifest"])
    manifest = doc(root, manifest_pin)
    require(manifest.get("task_id") == TASK and manifest.get("candidate_version") == VERSION,
            "current producer source manifest required")
    legacy = "artifact_pins" in manifest or "fresh_backup_pins" in manifest
    modern = "artifacts" in manifest or "backups" in manifest
    require(legacy != modern, "one unambiguous producer manifest pin shape required")
    artifacts_key, backups_key = (("artifact_pins", "fresh_backup_pins") if legacy else ("artifacts", "backups"))
    require(isinstance(manifest.get(artifacts_key), list) and isinstance(manifest.get(backups_key), list),
            "complete current producer artifact/backup pins required")
    artifacts = [pin(root, frozen) for frozen in manifest[artifacts_key]]
    backups = [pin(root, frozen) for frozen in manifest[backups_key]]
    checks = doc(root, current["evidence"]["fresh_CAS_input_checks"])
    require(checks.get("task_id") == TASK and checks.get("candidate_version") == VERSION
            and len(checks.get("records", [])) == 3, "current exact producer row checks required")
    if modern:
        require(manifest.get("source_candidate_version") == WEBSITE_SOURCE_VERSION
                and manifest.get("records") == checks["records"], "V4 manifest must freeze the same three current row checks")
    v5 = _v5_shape(root, current)
    results = []
    for (slug, record, fields), binding, fresh in zip(ROWS, bindings["records"], checks["records"]):
        identity = {"taskId": TASK, "actionId": f"paid-three-page-{slug}-exact-fields-v1",
                    "operation": "publish", "scope": f"company.example:services/{record}:{','.join(fields)}",
                    "candidateVersion": VERSION}
        require(binding.get("slug") == fresh.get("slug") == slug
                and binding.get("record_id") == fresh.get("record_id") == record
                and binding.get("proposed_target_identity") == identity
                and binding.get("changed_fields") == fresh.get("changed_fields") == list(fields),
                "original row/action/scope/field identity changed")
        backup_pin, candidate_pin = pin(root, binding["backup"]), pin(root, binding["candidate"])
        before, after = doc(root, backup_pin), doc(root, candidate_pin)
        require(binding.get("raw_updated_at") == before.get("updated_at")
                and binding.get("version") == before.get("version"), "original raw CAS/version must retain exact source values")
        require(set(before) == set(after) and len(before) == 30 and before.get("id") == after.get("id") == record,
                "exact full native row required")
        changes = {key for key in before if before[key] != after[key]}
        require(changes == set(fields), "sixth field or retained value changed")
        retained = {key: value for key, value in before.items() if key not in fields}
        website_retained = {key: value for key, value in retained.items() if key not in {"updated_at", "version"}}
        require(digest(before) == binding["before_full_fields_sha256"]
                and digest(after) == binding["after_full_fields_sha256"]
                and digest(retained) == binding["retained_fields_sha256"]
                and len(retained) == binding["retained_field_count"], "original native digests changed")
        fresh_backup, typed_pin = pin(root, fresh["backup"]), pin(root, fresh["typed_preview"])
        require(backups.count(fresh_backup) == 1 and artifacts.count(typed_pin) == 1,
                "current source manifest must freeze each row input")
        typed = doc(root, typed_pin)
        request = typed.get("request", {})
        base_row = {"slug": slug, "record_id": record, "action_id": identity["actionId"],
                    "scope": identity["scope"], "changed_fields": list(fields), "raw_updated_at": before["updated_at"]}
        effect = _v5_row_effect(root, current, fresh, base_row, before, after, artifacts) if v5 else {}
        if not v5 or effect.get("publication_state") == "pending_save":
            require(doc(root, fresh_backup) == before
                    and fresh.get("raw_updated_at") == binding["raw_updated_at"] == before["updated_at"]
                    and fresh.get("native_version") == binding["version"] == before["version"]
                    and request.get("mode") == "dry-run" and request.get("contentType") == "service"
                    and request.get("expectedUpdatedAt") == before["updated_at"]
                    and request.get("managedCandidate") == identity and request.get("record") == after,
                    "current raw CAS/typed request differs from original exact candidate")
        results.append({"slug": slug, "record_id": record, "action_id": identity["actionId"],
            "scope": identity["scope"], "changed_fields": list(fields), "raw_updated_at": before["updated_at"],
            "native_version": before["version"], "baseline_sha256": digest(before), "desired_sha256": digest(after),
            "retained_sha256": digest(retained), "retained_count": len(retained),
            "website_retained_sha256": digest(website_retained), "website_retained_count": len(website_retained),
            "candidate": candidate_pin, "backup": backup_pin if v5 and not effect.get("publish_allowed") else fresh_backup,
            "typed_preview": typed_pin, **effect})
    return results, bindings_pin, manifest_pin



V5_SOURCE_TASK = "fc-20261011-paid-three-page-v5-source-and-effect-compatibility-v1"
V5_SOURCE_VERSION = "paid-three-page-v5-source-effect-compatibility-v2-20261011"
V5_SOURCE_SCOPE = "project:flashcast:paid-three-page-v5-source-and-effect-compatibility:v1"
V5_SOURCE_SCHEMA = "actual_t3_v5_original_target_workflow_bridge_v1"
V5_BASELINE_COMMIT = "5237d068b49a20a9ce6dc395f8c6a45d7f961d8b"
V5_WORKFLOW_BEFORE = {"sha256": "fbaf3ba910422dcf858349642e84320ee85409e0e26379ee77a2ce0dda32cc0a", "size": 20603}
V5_WORKFLOW_AFTER = {"sha256": "32eb9be1a7f90dad8ea4477da9ebad1e84421d3a5ea7acc2547786aa57512e50", "size": 22350}
V5_CHANGED_SOURCES = {"tools/paid_three_page_bounded_cms.py", "tools/test_paid_three_page_bounded_cms.py",
                      "tools/managed_cms_permit_issuer.py"}
V5_PROTECTED_SOURCES = {"tools/qa_review_plan.py", "tools/goal_delivery_runtime.py", "tools/workflow_control.py"}
V5_REVIEW_FLAGS = (*FLAGS, "goal_completion_claimed", "final_goal_verdict", "pilot_complete")


def _content_pair(raw):
    return {"sha256": hashlib.sha256(raw).hexdigest(), "size": len(raw)}


def _v5_bridge_header(proof):
    require(proof.get("schema") == V5_SOURCE_SCHEMA and proof.get("task_id") == TASK
            and proof.get("candidate_version") == VERSION and proof.get("operation") in {"publish", "rollback"}
            and proof.get("source_task_id") == V5_SOURCE_TASK
            and proof.get("source_candidate_version") == V5_SOURCE_VERSION
            and proof.get("source_scope") == V5_SOURCE_SCOPE
            and proof.get("scoped_result") == "exact_original_target_branch_verified"
            and proof.get("whole_workflow_bytes_equal") is False and proof.get("formal_T3_PASS") is False
            and proof.get("baseline_commit") == V5_BASELINE_COMMIT
            and re.fullmatch(r"[0-9a-f]{40}", str(proof.get("current_commit", ""))) is not None
            and proof.get("actual_machine_main_sha") == proof.get("actual_machine_workflow_sha") == proof["current_commit"]
            and proof.get("actual_deployed_runtime_sha") == V5_BASELINE_COMMIT
            and proof.get("actual_function_version") == 77 and type(proof.get("actual_function_version")) is int
            and proof.get("actual_deployment_run") == 38061480070 and type(proof.get("actual_deployment_run")) is int
            and proof.get("prepared_only", False) is False
            and all(proof.get(key) is False for key in V5_REVIEW_FLAGS),
            "explicit exact V5 source bridge required; preliminary preparation is not source acceptance")


def _v5_machine_sources(root, current, source_bridge):
    proof = doc(root, source_bridge)
    _v5_bridge_header(proof)
    require(doc(root, proof.get("current_producer")) == current, "V5 bridge must bind exact latest producer bytes")
    evidence = current["evidence"]
    previous = doc(root, evidence["original_V3"])
    require(previous.get("task_id") == TASK and previous.get("candidate_version") == VERSION
            and current.get("task_id") == TASK and current.get("candidate_version") == VERSION
            and pin(root, previous["evidence"]["original_V2"]) == pin(root, evidence["original_V2"]),
            "V5 must retain the exact original V3/V2 authority provenance")
    original = pin(root, previous["evidence"]["original_authority_review_machine_channel"])
    require(evidence.get("original_authority_review_machine_channel") is None
            or pin(root, evidence["original_authority_review_machine_channel"]) == original,
            "conflicting V5 original machine authority forbidden")
    actual = pin(root, evidence["actual_machine_identity_and_preview_facts"])
    facts = doc(root, actual)
    require(pin(root, proof.get("actual_machine_source")) == actual
            and pin(root, proof.get("workflow_current")) == pin(root, evidence["actual_current_workflow_source"])
            and pin(root, proof.get("frontend_version")) == pin(root, evidence["actual_current_frontend_version"])
            and pin(root, proof.get("source_comparison")) == pin(root, evidence["actual_main_and_deployed_source_comparison"])
            and facts.get("task_id") == TASK and facts.get("candidate_version") == VERSION
            and facts.get("machine_workflow_sha") == proof["current_commit"]
            and re.fullmatch(r"[0-9a-f]{40}", str(facts.get("native_frontend_actual_version", ""))) is not None
            and facts.get("original_source_candidate_version") == WEBSITE_SOURCE_VERSION
            and facts.get("actual_time_not_overwritten") is True
            and type(facts.get("new_permits_issued")) is int and facts["new_permits_issued"] == 0
            and type(facts.get("new_CMS_Save")) is int and facts["new_CMS_Save"] == 0
            and len(facts.get("records", [])) == 3
            and [row.get("slug") for row in facts["records"]] == [row[0] for row in ROWS]
            and all(type(row.get("writes")) is int and row["writes"] == 0
                    and row.get("old_run_or_permission_reused") is False
                    and row.get("actual_machine_requests_completed") is True for row in facts["records"]),
            "actual V5 field schema and frozen three-target zero-write facts required")
    require(not any(key in facts for key in ("native_frontend_loaded_sha", "website_deployed_source_candidate_version",
                                            "new_account_permission", "cms_save", "signing_authority")),
            "V5 facts cannot alias the V4 source schema")
    frontend = doc(root, proof["frontend_version"])
    require(frontend.get("deploymentVersion") == facts["native_frontend_actual_version"],
            "actual frontend version must be independent of deployed runtime commit")
    return {"original_machine_source": original, "actual_machine_source": actual,
            "source_bridge": pin(root, source_bridge)}


def _v5_workflow_bridge_bytes(root, proof):
    """Only the reviewed whole-blob pair is admitted; every diff byte is recomputed."""
    before_pin, after_pin, diff_pin = [pin(root, proof.get(key)) for key in
                                      ("workflow_baseline", "workflow_current", "full_workflow_diff")]
    before, after, delta = [w.safe_path(root, value["path"]).read_bytes() for value in (before_pin, after_pin, diff_pin)]
    require(_content_pair(before) == V5_WORKFLOW_BEFORE and _content_pair(after) == V5_WORKFLOW_AFTER, "unknown full V5 workflow/diff hash-size pair forbidden")
    require(_git_source(V5_BASELINE_COMMIT, WORKFLOW_CLI[0]) == before
            and _git_source(proof["current_commit"], WORKFLOW_CLI[0]) == after,
            "V5 whole workflows must equal their immutable commit objects")
    exact = "".join(difflib.unified_diff(before.decode("utf-8").splitlines(keepends=True),
        after.decode("utf-8").splitlines(keepends=True),
        fromfile=V5_BASELINE_COMMIT + ":" + WORKFLOW_CLI[0],
        tofile=proof["current_commit"] + ":" + WORKFLOW_CLI[0])).encode("utf-8")
    require(delta == exact, "complete V5 workflow diff changed; no hunk may be ignored")


def _v5_source_decision_fence(root, decision, role=ROLE):
    """Validate permanent source-effect claim provenance without its token."""
    import sqlite3
    import result_coordination as c
    database = w.safe_path(root, str(c.DATABASE))
    require(database.is_file() and not database.is_symlink(), "original source coordination audit required")
    connection = sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)
    try:
        records = connection.execute("SELECT seq,payload_json,previous_hash,record_hash FROM coordination_audit ORDER BY seq").fetchall()
    finally:
        connection.close()
    rows, previous = [], ""
    for seq, raw, before, recorded in records:
        value = json.loads(raw)
        require(before == previous and recorded == c._sha([previous, value]), "original source claim audit chain changed")
        rows.append((seq, value));previous = recorded
    identity, effect = c.exact_identity(decision), c._sha([decision["event"], decision["idempotency_key"]])
    exact = [(seq,value) for seq,value in rows if value.get("identity") == identity]
    reserved = [(seq,value) for seq,value in exact if value.get("event") == "effect_reserved" and value.get("details", {}).get("effect_key") == effect]
    commits = [(seq,value) for seq,value in exact if value.get("event") == "effect_readback_committed" and value.get("details", {}).get("effect_key") == effect]
    require(len(reserved) == 1 and commits and all(value.get("details", {}).get("native_record_id") == decision["record_id"] for _,value in commits), "original unique source reserve/commit required")
    start, reservation = reserved[0];end = commits[0][0]
    claims = [(seq,value) for seq,value in exact if seq < start and value.get("event") in {"claim", "recover_expired"}]
    require(claims, "original source decision claim audit required")
    claim_seq, claim = claims[-1]
    require(all(claim.get("details", {}).get(k) == v for k,v in
            {"role":role,"owner":decision["coordinator_owner"],"fence":decision["coordination_fence"]}.items())
            and all(reservation.get("details", {}).get(k) == v for k,v in {"role":role,"owner":decision["coordinator_owner"]}.items())
            and claim_seq < start < end and not any(claim_seq < seq < end and value.get("event") in {"claim", "recover_expired", "transfer", "release"} for seq,value in exact),
            "source decision must retain its actual original independent owner/fence")
    claimed, reserved_at, committed_at = (claim.get("at"), reservation.get("at"), commits[0][1].get("at"))
    require(all(type(value) in {int, float} for value in (claimed, reserved_at, committed_at))
            and 0 < claimed <= reserved_at <= committed_at <= dt.datetime.now(dt.timezone.utc).timestamp(),
            "ordered actual source-effect claim, reserve and commit audit times required")
    return {"claimed_at":claimed,"reserved_at":reserved_at,"committed_at":committed_at}


def _v5_source_responsibility(root, snapshot, manifest, producer_pin, review_pin, decision):
    """This ST's direct-human source-only lane; never a generic QA assignment.

    Permanent committed source provenance outlives its lease. Execution still
    needs the operator's separate current private claim/fence before every write.
    """
    import goal_delivery_runtime as g
    import qa_review_plan as q
    import result_coordination as c
    from scoped_candidate_adoption import _committed, _receipts
    snapshot = g.restore_goal(root, q._review_context(root, snapshot))
    goal = g.validate_goal(root, snapshot.get("goal_delivery"))
    registry = w.department_registry(root)
    producer_binding = registry["system-development"]["chat_binding"]
    review_binding = registry[ROLE]["chat_binding"]
    require(snapshot.get("task_id") == manifest.get("task_id") == V5_SOURCE_TASK
            and manifest.get("candidate_version") == V5_SOURCE_VERSION and manifest.get("scope") == V5_SOURCE_SCOPE
            and manifest.get("candidate_fingerprint") == digest({k:v for k,v in manifest.items() if k != "candidate_fingerprint"})
            and all(manifest.get(k) is False for k in V5_REVIEW_FLAGS)
            and goal.get("source_mode") == "owner_direct" and goal.get("parent_task_id") == TASK
            and goal.get("primary_owner") == "system-development" and goal.get("producer_departments") == ["system-development"]
            and goal.get("authorized_scope") == [V5_SOURCE_SCOPE] and goal.get("acceptance_capability") == "development"
            and goal.get("responsible_assistant") == q._goal_reviewer(root, snapshot) == ROLE
            and not goal.get("required_execution_actions") and not goal.get("assignment_history"),
            "only this exact direct-human sole-A2 ST source candidate is eligible")
    contract_pin = pin(root, snapshot.get("goal_contract"))
    authority_pin = pin(root, goal.get("authorization_pin"))
    require(manifest.get("goal_contract") == contract_pin and manifest.get("human_authorization") == authority_pin
            and {k:contract_pin[k] for k in ("sha256", "size")} == {"sha256":"a28aae0841546efbcfe92ee5a25ef7376770319d1925649502494bdf5c63d455", "size":3576}
            and {k:authority_pin[k] for k in ("sha256", "size")} == {"sha256":"fbbe14e162ecc0a601ba9290e87719416f2b233122f2b2b38a5555b3e80c6fee", "size":2887},
            "original frozen ST human/goal bytes cannot be replaced by HQ or old CT3")
    contract, human = doc(root, contract_pin), doc(root, authority_pin)
    require(all(contract.get(k) == goal.get(k) for k in (*q.GOAL_IDENTITY, "parent_task_id", "source_mode", "human_authorization", "required_execution_actions"))
            and human.get("actual_provider") == "read_thread" and human.get("source_thread_id") == review_binding["task_id"]
            and human.get("message", {}).get("id") == goal["human_authorization"]["message_id"] == "example-native-41cad79d533ba8b9"
            and human["message"].get("type") == "userMessage" and human.get("push_merge_deploy_authorized") is False
            and any(item.get("executor") == "system-development" and item.get("thread_id") == producer_binding["task_id"]
                    and item.get("scope") == V5_SOURCE_SCOPE and item.get("candidate_and_exact_adoption") is True
                    for item in human.get("target_authorizations", [])),
            "actual original A2 fixed-chat human authorization is required")
    require(all(w._chat_binding_healthy(binding, verification_ttl_hours=26)
                and binding.get("cwd") == str(Path(root).resolve()) for binding in (producer_binding, review_binding))
            and producer_binding.get("project_id") == review_binding.get("project_id")
            and producer_binding["task_id"] != review_binding["task_id"], "healthy same-project independent fixed chats required")
    binding = q._binding(root, snapshot) or {}
    plan_pin = pin(root, binding.get("pin"))
    plan = doc(root, plan_pin)
    q.validate_plan(root, snapshot, plan)
    producer_pin, review_pin = pin(root, producer_pin), pin(root, review_pin)
    producer, box = doc(root, producer_pin), doc(root, review_pin)
    require(plan.get("candidate_version") == V5_SOURCE_VERSION and plan.get("scope") == V5_SOURCE_SCOPE
            and plan.get("producer_department") == "system-development" and plan.get("reviewer_department") == ROLE
            and plan.get("controller_department") == ROLE and plan.get("action_class") == "internal_control_candidate"
            and plan.get("risk_level") == "R0" and not any(key in plan for key in
                ("owner_direct_review", "native_multi_goal_review", "parent_initial_child_review", "review_delegation"))
            and q._producer_candidate_bound(root, plan, producer_pin, producer), "actual exact bound source-only plan and producer required")
    w.validate_outbox(root, [producer_pin], "system-development", V5_SOURCE_TASK)
    w.validate_outbox(root, [review_pin], ROLE, V5_SOURCE_TASK)
    review = box.get("candidate_review", {})
    manifest_pin = producer.get("evidence", {}).get("candidate_manifest")
    require(doc(root, manifest_pin) == manifest and producer.get("candidate_version") == V5_SOURCE_VERSION
            and producer.get("task_id") == V5_SOURCE_TASK and producer.get("scope") == V5_SOURCE_SCOPE
            and producer.get("department") == producer.get("sender_department") == "system-development"
            and producer.get("source_mode") == "owner_direct"
            and producer.get("candidate_fingerprint") == manifest["candidate_fingerprint"]
            and box.get("status") == "partial" and box.get("candidate_version") == V5_SOURCE_VERSION and box.get("scope") == V5_SOURCE_SCOPE
            and review.get("actor") == ROLE and review.get("verdict") == "PASS_SOURCE_CANDIDATE_ONLY"
            and review.get("phase") == "candidate_source_only" and review.get("direction") in {"forward", "reverse"}
            and review.get("candidate_manifest") == pin(root, manifest_pin)
            and review.get("candidate_fingerprint") == manifest["candidate_fingerprint"]
            and review.get("producer_outbox") == producer_pin and review.get("review_plan") == plan_pin
            and review.get("goal_contract") == contract_pin and review.get("human_authorization") == authority_pin
            and all(review.get(k) == v for k,v in manifest["current_source_context"].items())
            and all(box.get(k) is False and review.get(k) is False for k in V5_REVIEW_FLAGS)
            and not box.get("goal_acceptance") and box.get("qa_verdict") != "pass" and box.get("prepared_only", False) is False,
            "actual new same-version independent source-only PASS required; no old/HQ/full-goal verdict")
    _native(root, box, [V5_SOURCE_TASK, V5_SOURCE_VERSION, manifest["candidate_fingerprint"],
                        manifest["current_source_context"]["workflow_commit"], "PASS_SOURCE_CANDIDATE_ONLY"])
    receipts = _receipts(root, V5_SOURCE_TASK)
    require(not w.validate_workflow_events(root, V5_SOURCE_TASK), "intact original source workflow events required")
    received = [row for row in receipts if row.get("receipt_type") == "outbox_received" and row.get("department") == "system-development"]
    require(received and producer_pin in received[-1].get("evidence", []), "latest exact same-version producer result must be received")
    acks = [row for row in receipts if row.get("receipt_type") == "chat_ack" and row.get("department") == "system-development"
            and row.get("ack_nonempty") is True and row.get("chat_task_id") == producer_binding["task_id"]]
    ack_valid = False
    for ack in acks:
        documents = [doc(root, frozen) for frozen in ack.get("evidence", [])]
        acknowledgments = [value for value in documents if value.get("message", {}).get("type") == "agentMessage"]
        incoming = [value for value in documents if value.get("item", {}).get("type") == "functionCallOutput"]
        for acknowledgment in acknowledgments:
            for source in incoming:
                item = source["item"];output = item.get("output", {})
                raw = output.get("text", "")
                wrapper = re.fullmatch(r"<codex_delegation>\n  <source_thread_id>([^<\n]+)</source_thread_id>\n  <input>([\s\S]+)</input>\n</codex_delegation>\n?", raw) if isinstance(raw, str) else None
                valid = all(value.get("actual_provider") == "read_thread" and value.get("actual_receiver_thread_id") == producer_binding["task_id"]
                    and value.get("thread", {}).get("id") == producer_binding["task_id"]
                    and value["thread"].get("cwd") == str(Path(root).resolve()) and value["thread"].get("title") == producer_binding["title"]
                    for value in (acknowledgment, source))
                message = acknowledgment["message"]
                ack_at = w._parse_observed_at(ack.get("created_at"))
                started = acknowledgment.get("turn", {}).get("startedAt")
                valid = valid and bool(acknowledgment.get("turn", {}).get("id")) and acknowledgment["turn"]["id"] == source.get("turn", {}).get("id") and bool(message.get("id")) and bool(item.get("id"))
                valid = valid and acknowledgment["turn"].get("status") in {"inProgress", "completed"} and source.get("turn", {}).get("status") in {"inProgress", "completed"}
                valid = valid and type(started) in {int, float} and ack_at is not None and 0 < started <= ack_at.timestamp() <= dt.datetime.now(dt.timezone.utc).timestamp()
                valid = valid and message.get("phase") in {"commentary", "final_answer"} and isinstance(message.get("text"), str) and bool(message["text"].strip())
                valid = valid and item.get("name") == "send_message_to_thread" and item.get("namespace") == "codex_app" and output.get("truncated") is False
                valid = valid and wrapper is not None and wrapper.group(1) == review_binding["task_id"]
                if valid:
                    ack_valid = all(q._exact_text_reference(wrapper.group(2), value) for value in
                        (V5_SOURCE_TASK, V5_SOURCE_SCOPE, TASK, goal["human_authorization"]["message_id"]))
                if ack_valid: break
            if ack_valid: break
        if ack_valid: break
    require(ack_valid, "actual original producer native ACK and authorized A2 input required; no synthetic reviewer ACK")
    identity = c.exact_identity(decision)
    require(identity == {"task_id":V5_SOURCE_TASK,"sender_department":"system-development",
                        "candidate_version":V5_SOURCE_VERSION,"result_sha256":producer_pin["sha256"]}, "exact current source decision identity required")
    c._validate_queued(root, identity)
    c._goal_actor(root, identity, ROLE)
    rows = w._result_handoff_rows(root, V5_SOURCE_TASK)
    selected = [row for row in rows if all(row.get(k) == v for k,v in identity.items())]
    queues = [row for row in selected if row.get("event") == "notification_queued"]
    intakes = [row for row in selected if row.get("event") == "controller_received"]
    require(len(queues) == len(intakes) == 1 and queues[0].get("outbox") == producer_pin
            and queues[0].get("source_mode") == "owner_direct" and intakes[0].get("outbox") == producer_pin
            and intakes[0].get("coordinator_role") == intakes[0].get("responsible_assistant") == ROLE
            and rows.index(queues[0]) < rows.index(intakes[0]) < rows.index(decision), "unique actual completed queue and independent intake before decision required")
    w._validate_goal_completed_result(root, queues[0], producer_binding["task_id"])
    _committed(root, intakes[0])
    require(decision.get("event") == "controller_decision" and decision.get("decision") == "continue"
            and decision.get("coordinator_role") == decision.get("decision_actor") == decision.get("responsible_assistant") == ROLE
            and decision.get("outbox") == producer_pin and review_pin in decision.get("evidence", [])
            and decision.get("next_owner") == ROLE and decision.get("next_action") ==
                ("adopt-" if review["direction"] == "forward" else "restore-") + V5_SOURCE_VERSION
            and isinstance(decision.get("coordinator_owner"), str) and bool(decision["coordinator_owner"].strip())
            and type(decision.get("coordination_fence")) is int and decision["coordination_fence"] > 0
            and decision.get("business_goal_closed") is False and decision.get("qa_status") != "pass",
            "actual independent same-version owner/fence source-only continue required")
    _committed(root, decision)
    _v5_source_decision_fence(root, decision)
    return {"source_mode":"owner_direct_source_only", "responsible_assistant":ROLE,
            "review_plan":plan_pin,"producer_outbox":producer_pin,"queue_record_id":queues[0]["record_id"],
            "intake_record_id":intakes[0]["record_id"],"decision_record_id":decision["record_id"],
            "formal_full_goal_responsibility_satisfied":False,"external_authority_granted":False}


NATIVE_SOURCE_TASK = "fc-20261011-native-control-and-qualified-assistant-entry-repair-v1"
NATIVE_SOURCE_SCOPE = "project:flashcast:native-control-and-qualified-assistant-entry-repair:v1"
NATIVE_SOURCE_PATHS = V5_PROTECTED_SOURCES | {
    "tools/paid_three_page_bounded_cms.py", "tools/result_coordination.py",
    "tools/technical_review_backup.py", "tools/native_control_result.py"}


def _v5_historical_sources(root, manifest):
    """Frozen adoption bytes are historical facts, not today's mutable paths."""
    result = {}
    for row in manifest["files"]:
        frozen = pin(root, row["candidate"])
        result[row["path"]] = {"path": row["path"], **{k: frozen[k] for k in ("sha256", "size")}}
    for frozen in manifest.get("protected_sources", []):
        require(isinstance(frozen, dict) and set(frozen) == {"path", "sha256", "size"}
                and frozen.get("path") not in result
                and re.fullmatch(r"[0-9a-f]{64}", str(frozen.get("sha256", "")))
                and type(frozen.get("size")) is int and frozen["size"] > 0,
                "unambiguous reviewed historical protected source pin required")
        result[frozen["path"]] = frozen
    require(set(result) == V5_CHANGED_SOURCES | V5_PROTECTED_SOURCES,
            "exact original historical source set required")
    return result


def _native_source_review(root, continuation, old_manifest_pin, historical):
    """Same strict independent review reader for pre-write CAS and permanent lineage."""
    import goal_delivery_runtime as g
    import qa_review_plan as q
    require(continuation.get("schema") == "actual_native_control_source_continuation/v1"
            and continuation.get("historical_V5_manifest") == old_manifest_pin
            and continuation.get("task_id") == NATIVE_SOURCE_TASK
            and continuation.get("prepared_only", False) is False
            and all(continuation.get(k) is False for k in V5_REVIEW_FLAGS),
            "one exact internal source continuation required; no external authority")
    snapshot = g.restore_goal(root, w.read_json(w.snapshot_path(root, NATIVE_SOURCE_TASK)))
    goal = g.validate_goal(root, snapshot.get("goal_delivery"), task_id=NATIVE_SOURCE_TASK)
    role = q._goal_reviewer(root, snapshot)
    require(goal.get("primary_owner") == "system-development"
            and goal.get("producer_departments") == ["system-development"]
            and goal.get("parent_task_id") == "fc-20261010-weekly-safe-cleanup-native-enablement-v1"
            and goal.get("source_mode") == "approved_dispatch"
            and goal.get("authorized_scope") == [NATIVE_SOURCE_SCOPE]
            and goal.get("acceptance_capability") == "development"
            and not goal.get("required_execution_actions") and role not in goal["producer_departments"],
            "exact original source goal and independent assigned development reviewer required")
    from technical_review_backup import _qualified_responsibility
    require(goal.get("assignment_history") or _qualified_responsibility(root, role, goal, NATIVE_SOURCE_TASK),
            "actual original same-goal independent responsibility send and ACK required")
    contract_pin, authority_pin = pin(root, snapshot.get("goal_contract")), pin(root, goal.get("authorization_pin"))
    contract = doc(root, contract_pin)
    require(all(contract.get(k) == goal.get(k) for k in
                (*[k for k in q.GOAL_IDENTITY if k != "responsible_assistant"], "parent_task_id", "source_mode", "human_authorization", "required_execution_actions")),
            "new source goal must preserve original frozen contract")
    manifest_pin = pin(root, continuation.get("candidate_manifest")); manifest = doc(root, manifest_pin)
    version = manifest.get("candidate_version")
    require(manifest.get("schema") == "flashcast-exact-source-candidate/v1"
            and manifest.get("task_id") == NATIVE_SOURCE_TASK and manifest.get("scope") == NATIVE_SOURCE_SCOPE
            and isinstance(version, str) and version.strip()
            and manifest.get("candidate_fingerprint") == digest({k:v for k,v in manifest.items() if k != "candidate_fingerprint"})
            and manifest.get("goal_contract") == contract_pin and manifest.get("human_authorization") == authority_pin
            and manifest.get("source_lineage", {}).get("historical_V5_manifest") == old_manifest_pin
            and all(manifest.get(k) is False for k in V5_REVIEW_FLAGS),
            "exact newly reviewed source manifest, original authority and immutable lineage required")
    files = manifest.get("files", [])
    require(len(files) == len(NATIVE_SOURCE_PATHS) and {row.get("path") for row in files} == NATIVE_SOURCE_PATHS,
            "continuation is limited to the seven reviewed internal sources")
    protected = [pin(root, value) for value in manifest.get("protected_sources", [])]
    require({p["path"] for p in protected} >= {
                "tools/managed_cms_permit_issuer.py", "tools/test_paid_three_page_bounded_cms.py"}
            and all(p == historical[p["path"]] for p in protected if p["path"] in historical),
            "original issuer and source regression must remain unchanged")
    review_pin = pin(root, continuation.get("source_qa")); box = doc(root, review_pin)
    plan_pin = pin(root, continuation.get("review_plan")); plan = doc(root, plan_pin)
    producer_pin = pin(root, continuation.get("producer_outbox")); producer = doc(root, producer_pin)
    binding = q._binding(root, snapshot) or {}
    require(binding.get("pin") == plan_pin, "actual bound new source review plan required")
    q.validate_plan(root, snapshot, plan)
    require(plan.get("candidate_version") == version and plan.get("scope") == NATIVE_SOURCE_SCOPE
            and plan.get("producer_department") == "system-development"
            and plan.get("reviewer_department") == role and plan.get("controller_department") == role
            and plan.get("action_class") == "internal_control_candidate" and plan.get("risk_level") == "R0"
            and producer.get("task_id") == NATIVE_SOURCE_TASK and producer.get("candidate_version") == version
            and producer.get("candidate_fingerprint") == manifest["candidate_fingerprint"]
            and manifest_pin in list(q._evidence_pins(producer.get("evidence", [])))
            and q._producer_candidate_bound(root, plan, producer_pin, producer),
            "one newly frozen candidate and actual independent same-version plan required")
    for frozen, actor in ((producer_pin, "system-development"), (review_pin, role)):
        w.validate_outbox(root, [frozen], actor, NATIVE_SOURCE_TASK)
    review = box.get("candidate_review", {})
    require(box.get("department") == role and box.get("task_id") == NATIVE_SOURCE_TASK
            and box.get("candidate_version") == version and box.get("scope") == NATIVE_SOURCE_SCOPE
            and box.get("status") == "partial" and not box.get("goal_acceptance") and box.get("qa_verdict") != "pass"
            and box.get("prepared_only", False) is False
            and review.get("actor") == role and review.get("verdict") == "PASS_SOURCE_CANDIDATE_ONLY"
            and review.get("phase") == "candidate_source_only" and review.get("direction") == "forward"
            and review.get("candidate_manifest") == manifest_pin
            and review.get("candidate_fingerprint") == manifest["candidate_fingerprint"]
            and review.get("producer_outbox") == producer_pin and review.get("review_plan") == plan_pin
            and review.get("goal_contract") == contract_pin and review.get("human_authorization") == authority_pin
            and all(box.get(k) is False and review.get(k) is False for k in V5_REVIEW_FLAGS),
            "new actual independent source-only PASS required; candidate or old PASS is insufficient")
    _native(root, box, [NATIVE_SOURCE_TASK, version, manifest["candidate_fingerprint"],
                        producer_pin["sha256"], manifest_pin["sha256"], "PASS_SOURCE_CANDIDATE_ONLY"], role)
    return {"snapshot":snapshot,"goal":goal,"role":role,"manifest":manifest,"manifest_pin":manifest_pin,
            "version":version,"files":files,"box":box,"review_pin":review_pin,"plan":plan,"plan_pin":plan_pin,
            "producer_pin":producer_pin,"contract_pin":contract_pin,"authority_pin":authority_pin}


def _v5_current_lineage(root, proof, accepted, old_manifest_pin, historical):
    """Only this repair's independently accepted, committed exact CAS may succeed V5.

    This is a read-only permanent provenance check. It grants no execution,
    permission or lease and cannot replace the operator's pre-write checks.
    """
    import goal_delivery_runtime as g
    import qa_review_plan as q
    import result_coordination as c
    from scoped_candidate_adoption import _committed, _receipts
    current = [pin(root, value) for value in proof.get("current_consumer_sources", [])]
    require(len(current) == len(SOURCES) and {x["path"] for x in current} == set(SOURCES)
            and current == [pin(root, x) for x in accepted.get("consumer_sources", [])],
            "all five actual current sources must match bounded acceptance")
    continuation_pin = proof.get("consumer_source_continuation")
    if continuation_pin is None:
        require(all(value == historical[value["path"]] for value in current),
                "changed consumer source requires independently adopted continuation")
        return current
    continuation = doc(root, continuation_pin)
    reviewed = _native_source_review(root, continuation, old_manifest_pin, historical)
    successor_pin = proof.get("consumer_source_repair_continuation")
    successor = doc(root, successor_pin) if successor_pin is not None else None
    successor_manifest = doc(root, successor.get("candidate_manifest")) if successor is not None else None
    successor_before = {row.get("path"): row.get("before") for row in successor_manifest.get("files", [])} if successor_manifest else {}
    weekly_pin = proof.get("consumer_weekly_native_source_continuation")
    repair_pin = proof.get("consumer_weekly_lineage_key_contract_repair_continuation")
    functional_pin = proof.get("consumer_weekly_functional_result_entry_repair_continuation")
    require(functional_pin is None or repair_pin is not None, "functional entry successor requires the complete actual original four layers")
    require(repair_pin is None or weekly_pin is not None, "current repair cannot replace or omit its original V2 layer")
    require(weekly_pin is None or successor_pin is not None, "weekly source continuation requires the original boundary continuation")
    weekly = doc(root, weekly_pin) if weekly_pin is not None else None
    weekly_manifest = doc(root, weekly.get("candidate_manifest")) if weekly is not None else None
    weekly_before = {row.get("path"): row.get("before") for row in weekly_manifest.get("files", [])} if weekly_manifest else {}
    snapshot, goal, role, manifest, manifest_pin, version, files, box, review_pin, plan, plan_pin, producer_pin, contract_pin, authority_pin = [reviewed[k] for k in
        ("snapshot","goal","role","manifest","manifest_pin","version","files","box","review_pin","plan","plan_pin","producer_pin","contract_pin","authority_pin")]
    journal_pin = pin(root, continuation.get("source_adoption")); journal = doc(root, journal_pin)
    operations = journal.get("source_operations", [])
    require(journal.get("task_id") == NATIVE_SOURCE_TASK and journal.get("candidate_version") == version
            and journal.get("candidate_fingerprint") == manifest["candidate_fingerprint"]
            and journal.get("candidate_manifest") == manifest_pin and journal.get("review_outbox") == review_pin
            and journal.get("authorized_source") == authority_pin and journal.get("actor") == role
            and journal.get("direction") == "forward" and journal.get("status") == "complete"
            and type(journal.get("external_writes")) is int and journal["external_writes"] == 0
            and journal.get("effect_uncertain") is False and journal.get("permissions_issued") is False
            and isinstance(journal.get("execution_id"), str) and bool(journal["execution_id"].strip())
            and len(operations) == len(files) and {x.get("path") for x in operations} == NATIVE_SOURCE_PATHS
            and len(journal.get("applied", [])) == len(files) and set(journal["applied"]) == NATIVE_SOURCE_PATHS,
            "actual complete new source CAS journal and authority required")
    installed = {}
    for row in files:
        path = row["path"]; candidate = pin(root, row.get("candidate"))
        after = w.safe_path(root, candidate["path"]).read_bytes()
        require(row.get("after") == _content_pair(after)
                and row.get("candidate_relative_path") == "candidate/" + path
                and candidate["path"] == str(Path(manifest_pin["path"]).parent / row["candidate_relative_path"]),
                "new candidate source pins must exactly match CAS fields")
        before = b"" if row.get("before") == {"exists":False} else w.safe_path(root, pin(root, row.get("baseline"))["path"]).read_bytes()
        expected_before = {"exists":False} if not before else _content_pair(before)
        require(row.get("before") == expected_before and (path not in historical or expected_before == {
                    k:historical[path][k] for k in ("sha256", "size")}),
                "new baseline must preserve original V5 adoption bytes")
        for direction, first, last in (("forward", before, after), ("reverse", after, before)):
            delta = pin(root, row.get(direction + "_diff"))
            expected = "".join(difflib.unified_diff(first.decode().splitlines(keepends=True),
                last.decode().splitlines(keepends=True), fromfile="a/"+path if first else "/dev/null",
                tofile="b/"+path if last else "/dev/null")).encode()
            require(w.safe_path(root, delta["path"]).read_bytes() == expected, "new exact reversible diff required")
        operation = next(x for x in operations if x["path"] == path)
        require(operation.get("before") == expected_before and operation.get("after_expected") == operation.get("after_actual") == row["after"]
                and operation.get("write_attempted") is True and operation.get("verified_after") is True,
                "new actual exact before/write/readback CAS effect required")
        if before:
            backup = pin(root, operation.get("backup"))
            require({k:backup[k] for k in ("sha256", "size")} == expected_before
                    and backup["path"].startswith(f"backups/{NATIVE_SOURCE_TASK}/{manifest['candidate_fingerprint']}/forward/")
                    and type(operation.get("before_mode")) is int
                    and w.safe_path(root, backup["path"]).stat().st_mode & 0o777 == operation["before_mode"],
                    "new original-byte backup and mode required")
        else:
            require(path == "tools/native_control_result.py" and operation.get("backup") is None,
                    "only the reviewed new native reader may have an absent baseline")
        if successor is not None and path in SOURCE_REPAIR_PATHS:
            require(successor_before.get(path) == row["after"], "new source repair must begin at exact old V6 installed bytes")
            installed[path] = {"path":path, **row["after"]}
        elif weekly is not None and path in WEEKLY_SOURCE_PATHS:
            require(weekly_before.get(path) == row["after"], "weekly source before must preserve exact original V6 installed overlap")
            installed[path] = {"path": path, **row["after"]}
        else:
            installed[path] = pin(root, {"path":path, **row["after"]})
    if successor is None:
        require(all(value == installed.get(value["path"], historical.get(value["path"])) for value in current),
                "current consumers must equal the independently reviewed actual CAS result")
    receipts = _receipts(root, NATIVE_SOURCE_TASK)
    require(q._assigned_review_round(root, snapshot, receipts, plan) is not None,
            "original exact assigned review round or committed same-capability transfer required")
    received = [r for r in receipts if r.get("receipt_type") == "outbox_received" and r.get("department") == "system-development"]
    require(received and producer_pin in received[-1].get("evidence", [])
            and not w.validate_workflow_events(root, NATIVE_SOURCE_TASK), "latest actual producer receipt and intact workflow required")
    handoffs = w._result_handoff_rows(root, NATIVE_SOURCE_TASK)
    decisions = [r for r in handoffs if r.get("record_id") == journal.get("decision_record_id")]
    require(len(decisions) == 1, "unique new source adoption decision required")
    decision = decisions[0]; identity = c.exact_identity(decision)
    require(identity == {"task_id":NATIVE_SOURCE_TASK,"sender_department":"system-development",
                         "candidate_version":version,"result_sha256":producer_pin["sha256"]},
            "exact new adoption decision identity required")
    c._validate_queued(root, identity); c._goal_actor(root, identity, role)
    rows = [r for r in handoffs if c.exact_identity(r) == identity]
    queues = [r for r in rows if r.get("event") == "notification_queued"]
    intakes = [r for r in rows if r.get("event") == "controller_received"]
    require(len(queues) == len(intakes) == 1 and intakes[0].get("coordinator_role") == role
            and handoffs.index(queues[0]) < handoffs.index(intakes[0]) < handoffs.index(decision),
            "unique completed result queue and independent actual intake required")
    w._validate_goal_completed_result(root, queues[0], w.department_registry(root)["system-development"]["chat_binding"]["task_id"])
    _committed(root, intakes[0])
    require(decision.get("event") == "controller_decision" and decision.get("decision") == "continue"
            and decision.get("coordinator_role") == decision.get("decision_actor") == decision.get("responsible_assistant") == role
            and decision.get("outbox") == producer_pin and review_pin in decision.get("evidence", [])
            and decision.get("next_owner") == role and decision.get("next_action") == "adopt-" + version
            and decision.get("business_goal_closed") is False and decision.get("qa_status") != "pass",
            "actual independent exact new source adoption continue required")
    _committed(root, decision); _v5_source_decision_fence(root, decision, role)
    follows = [r for r in handoffs if r.get("record_id") == continuation.get("adoption_followthrough_record_id")]
    require(len(follows) == 1, "new adopted source committed followthrough required")
    follow = follows[0]
    require(follow.get("event") == "controller_followthrough" and follow.get("followthrough_status") == "blocked_with_owner"
            and c.exact_identity(follow) == identity and follow.get("outbox") == producer_pin
            and follow.get("coordinator_role") == follow.get("decision_actor") == follow.get("responsible_assistant") == role
            and follow.get("coordinator_owner") == decision.get("coordinator_owner")
            and follow.get("coordination_fence") == decision.get("coordination_fence")
            and follow.get("unblock_condition") == "source-adopted:" + journal["execution_id"] + ";remaining:weekly-native-control-and-functional-acceptance"
            and journal_pin in follow.get("evidence", []) and follow.get("business_goal_closed") is False
            and handoffs.index(decision) < handoffs.index(follow), "actual exact new source effects followthrough required")
    _committed(root, follow); audit = _v5_source_decision_fence(root, follow, role)
    if functional_pin is not None:
        _source_release_readback(root, follow, audit)
    reviewed, started, completed = [w._parse_observed_at(x) for x in
        (box.get("created_at"), journal.get("started_at"), journal.get("completed_at"))]
    require(all(x is not None for x in (reviewed, started, completed))
            and reviewed <= started <= completed <= dt.datetime.now(dt.timezone.utc)
            and completed.timestamp() <= audit["reserved_at"] <= audit["committed_at"],
            "ordered independent review, actual new CAS and committed readback required")
    if successor is not None:
        if weekly_pin is not None:
            _weekly_source_successor(root, weekly_pin, continuation_pin, old_manifest_pin, successor_pin, repair_pin, functional_pin)
        installed.update(_source_repair_successor(root, successor_pin, continuation_pin, old_manifest_pin, installed, weekly_pin, repair_pin, functional_pin))
        if weekly_pin is not None:
            installed.update(_weekly_source_successor(root, weekly_pin, continuation_pin, old_manifest_pin, successor_pin, repair_pin, functional_pin))
        if repair_pin is not None:
            installed.update(_weekly_lineage_key_repair_successor(root, repair_pin, weekly_pin,
                continuation_pin, old_manifest_pin, successor_pin, functional_pin))
        require(all(value == installed.get(value["path"], historical.get(value["path"])) for value in current),
                "current consumers must equal the exact independently adopted five-source successor")
    if functional_pin is not None:
        installed.update(_weekly_functional_result_entry_successor(root, functional_pin, repair_pin, weekly_pin,
            continuation_pin, old_manifest_pin, successor_pin))
        require(all(value == installed.get(value["path"], historical.get(value["path"])) for value in current),
                "current consumers must equal the complete five-layer exact adopted endpoint")
    return current


QUALIFIED_NATIVE_HANDOFF_TASK = "fc-20261011-qualified-native-handoff-envelope-recovery-v1"
QUALIFIED_NATIVE_HANDOFF_SCOPE = "project:flashcast:qualified-native-handoff-envelope-recovery:v1"
QUALIFIED_NATIVE_HANDOFF_VERSION = "qualified-native-handoff-envelope-recovery-source-candidate-v3-20261011"
QUALIFIED_NATIVE_HANDOFF_PATHS = {"tools/qa_review_plan.py", "tools/paid_three_page_bounded_cms.py"}
QUALIFIED_NATIVE_HANDOFF_PREDECESSORS = (
    "historical_V5_manifest", "original_native_control_continuation", "original_source_repair_continuation",
    "original_weekly_native_source_continuation", "original_weekly_lineage_key_contract_repair_continuation",
    "original_weekly_functional_result_entry_repair_continuation", "existing_T1_manifest")


def _qualified_native_handoff_context(root, continuation_pin, predecessor_pins):
    """Select an independently accepted helper; it must authenticate actual CAS before projection."""
    import importlib.util
    import result_coordination as c
    from scoped_candidate_adoption import _committed
    role = "operations-assistant-2"
    continuation = doc(root, continuation_pin)
    fields = {"schema", "task_id", "scope", "candidate_version", *QUALIFIED_NATIVE_HANDOFF_PREDECESSORS,
        "candidate_manifest", "source_qa", "review_plan", "producer_outbox", "source_adoption",
        "adoption_followthrough_record_id", "review_context_helper", "prepared_only", *V5_REVIEW_FLAGS}
    require(set(continuation) == fields
        and continuation.get("schema") == "actual_qualified_native_handoff_source_continuation/v1"
        and continuation.get("task_id") == QUALIFIED_NATIVE_HANDOFF_TASK
        and continuation.get("scope") == QUALIFIED_NATIVE_HANDOFF_SCOPE
        and continuation.get("candidate_version") == QUALIFIED_NATIVE_HANDOFF_VERSION
        and set(predecessor_pins) == set(QUALIFIED_NATIVE_HANDOFF_PREDECESSORS)
        and all(continuation.get(key) == predecessor_pins[key] for key in QUALIFIED_NATIVE_HANDOFF_PREDECESSORS)
        and continuation.get("prepared_only") is False
        and all(continuation.get(key) is False for key in V5_REVIEW_FLAGS),
        "one exact actual qualified handoff successor must retain the entire original five-layer lineage")
    manifest_pin = pin(root, continuation.get("candidate_manifest")); manifest = doc(root, manifest_pin)
    helper_pin = pin(root, continuation.get("review_context_helper"))
    review_pin = pin(root, continuation.get("source_qa")); box = doc(root, review_pin)
    producer_pin = pin(root, continuation.get("producer_outbox")); review = box.get("candidate_review", {})
    require(manifest.get("schema") == "flashcast-exact-source-candidate/v1"
        and manifest.get("task_id") == QUALIFIED_NATIVE_HANDOFF_TASK
        and manifest.get("scope") == QUALIFIED_NATIVE_HANDOFF_SCOPE
        and manifest.get("candidate_version") == QUALIFIED_NATIVE_HANDOFF_VERSION
        and manifest.get("primary_owner") == "system-development" and manifest.get("responsible_assistant") == role
        and manifest.get("candidate_fingerprint") == digest({key:value for key,value in manifest.items() if key != "candidate_fingerprint"})
        and len(manifest.get("files", [])) == len(QUALIFIED_NATIVE_HANDOFF_PATHS)
        and {row.get("path") for row in manifest["files"]} == QUALIFIED_NATIVE_HANDOFF_PATHS
        and helper_pin["path"] == str(Path(manifest_pin["path"]).parent / "rollback/source_review_context.py")
        and helper_pin in manifest.get("inputs", [])
        and box.get("department") == role and box.get("task_id") == QUALIFIED_NATIVE_HANDOFF_TASK
        and box.get("candidate_version") == QUALIFIED_NATIVE_HANDOFF_VERSION and box.get("scope") == QUALIFIED_NATIVE_HANDOFF_SCOPE
        and box.get("status") == "partial" and box.get("prepared_only", False) is False
        and not box.get("goal_acceptance") and box.get("qa_verdict") != "pass"
        and review.get("actor") == role and review.get("verdict") == "PASS_SOURCE_CANDIDATE_ONLY"
        and review.get("phase") == "candidate_source_only" and review.get("direction") == "forward"
        and review.get("candidate_manifest") == manifest_pin and review.get("candidate_fingerprint") == manifest["candidate_fingerprint"]
        and review.get("producer_outbox") == producer_pin and review.get("review_plan") == continuation.get("review_plan")
        and review.get("goal_contract") == manifest.get("goal_contract") and review.get("human_authorization") == manifest.get("human_authorization")
        and all(manifest.get(key) is False and box.get(key) is False and review.get(key) is False for key in V5_REVIEW_FLAGS),
        "independent exact source-only QA must accept the new helper before loading it")
    w.validate_outbox(root, [review_pin], role, QUALIFIED_NATIVE_HANDOFF_TASK)
    _native(root, box, [QUALIFIED_NATIVE_HANDOFF_TASK, QUALIFIED_NATIVE_HANDOFF_VERSION, manifest["candidate_fingerprint"],
        producer_pin["sha256"], manifest_pin["sha256"], "PASS_SOURCE_CANDIDATE_ONLY"], role)
    journal = doc(root, pin(root, continuation.get("source_adoption")))
    handoffs = w._result_handoff_rows(root, QUALIFIED_NATIVE_HANDOFF_TASK)
    decisions = [row for row in handoffs if row.get("record_id") == journal.get("decision_record_id")]
    require(len(decisions) == 1, "one actual qualified handoff adoption decision required")
    decision = decisions[0]
    require(c.exact_identity(decision) == {"task_id":QUALIFIED_NATIVE_HANDOFF_TASK,"sender_department":"system-development",
        "candidate_version":QUALIFIED_NATIVE_HANDOFF_VERSION,"result_sha256":producer_pin["sha256"]}
        and decision.get("event") == "controller_decision" and decision.get("decision") == "continue"
        and decision.get("outbox") == producer_pin and review_pin in decision.get("evidence", [])
        and decision.get("coordinator_role") == decision.get("decision_actor") == decision.get("responsible_assistant") == role
        and decision.get("next_owner") == role and decision.get("next_action") == "adopt-" + QUALIFIED_NATIVE_HANDOFF_VERSION
        and decision.get("business_goal_closed") is False and decision.get("qa_status") != "pass",
        "new consumer namespace requires its real independent exact adoption continue")
    _committed(root, decision); _v5_source_decision_fence(root, decision, role)
    spec = importlib.util.spec_from_file_location("_flashcast_qualified_native_handoff_review_context", w.safe_path(root, helper_pin["path"]))
    helper = importlib.util.module_from_spec(spec); spec.loader.exec_module(helper)
    require(helper.TASK == QUALIFIED_NATIVE_HANDOFF_TASK and helper.SCOPE == QUALIFIED_NATIVE_HANDOFF_SCOPE
        and helper.VERSION == QUALIFIED_NATIVE_HANDOFF_VERSION and helper.ROLE == role
        and helper.PRODUCER == "system-development" and helper.SOURCE_PATHS == QUALIFIED_NATIVE_HANDOFF_PATHS,
        "new reviewed helper cannot substitute an old goal, actor or source set")
    return helper.source_successor_context(root, pin(root, continuation_pin), predecessor_pins)


def _qualified_native_handoff_current_lineage(root, proof, accepted, old_manifest_pin, historical):
    """Authenticate the new actual effect, read all predecessors, then compare the real endpoint."""
    continuation_pin = proof.get("consumer_qualified_native_handoff_continuation")
    if continuation_pin is None:
        return _v5_current_lineage(root, proof, accepted, old_manifest_pin, historical)
    current = [pin(root, value) for value in proof.get("current_consumer_sources", [])]
    require(len(current) == len(SOURCES) and {value["path"] for value in current} == set(SOURCES)
        and current == [pin(root, value) for value in accepted.get("consumer_sources", [])],
        "all actual current consumers must retain exact bounded acceptance")
    predecessor_pins = {
        "historical_V5_manifest":pin(root, old_manifest_pin),
        "original_native_control_continuation":pin(root, proof.get("consumer_source_continuation")),
        "original_source_repair_continuation":pin(root, proof.get("consumer_source_repair_continuation")),
        "original_weekly_native_source_continuation":pin(root, proof.get("consumer_weekly_native_source_continuation")),
        "original_weekly_lineage_key_contract_repair_continuation":pin(root, proof.get("consumer_weekly_lineage_key_contract_repair_continuation")),
        "original_weekly_functional_result_entry_repair_continuation":pin(root, proof.get("consumer_weekly_functional_result_entry_repair_continuation"))}
    predecessor_pins["existing_T1_manifest"] = pin(root, doc(root,
        predecessor_pins["original_weekly_functional_result_entry_repair_continuation"])["candidate_manifest"])
    with _qualified_native_handoff_context(root, continuation_pin, predecessor_pins) as context:
        require(isinstance(context, dict) and isinstance(context.get("modules"), dict)
            and isinstance(context.get("installed"), dict) and isinstance(context.get("predecessor_endpoint"), list),
            "authenticated isolated successor context required")
        predecessor = context["predecessor_endpoint"]
        require(len(predecessor) == len(SOURCES) and [value.get("path") for value in predecessor] == list(SOURCES),
            "complete ordered actual predecessor endpoint required")
        before_proof = dict(proof); before_proof.pop("consumer_qualified_native_handoff_continuation")
        before_proof["current_consumer_sources"] = predecessor
        before_accepted = dict(accepted); before_accepted["consumer_sources"] = predecessor
        reader = context["modules"].get("paid_three_page_bounded_cms")
        require(reader is not None and reader._qualified_native_handoff_current_lineage is not _qualified_native_handoff_current_lineage,
            "fresh reviewed consumer namespace required")
        actual_predecessor = reader._v5_current_lineage(root, before_proof, before_accepted, old_manifest_pin, historical)
        require(actual_predecessor == predecessor, "entire original five-layer QA/CAS/committed chain must still pass")
        installed = context["installed"]
        require(set(installed) == QUALIFIED_NATIVE_HANDOFF_PATHS
            and all(isinstance(value, dict) and set(value) == {"path","sha256","size"} and value.get("path") == path
                for path,value in installed.items()), "only the exact adopted qualified handoff sources may succeed the old endpoint")
        endpoint = {value["path"]:value for value in actual_predecessor}; endpoint.update(installed)
        require(all(value == endpoint.get(value["path"]) for value in current),
            "actual current consumers must equal the complete independently adopted six-layer endpoint")
    require(current == [pin(root, value) for value in proof.get("current_consumer_sources", [])],
        "actual qualified successor consumers must remain exact after complete historical readback")
    return current


QUALIFIED_RULE_HISTORY_VERSION = "qualified-native-handoff-envelope-recovery-source-candidate-v6-20261011"
QUALIFIED_RULE_HISTORY_PATHS = {"tools/qa_review_plan.py", "tools/paid_three_page_bounded_cms.py"}


def _qualified_rule_history_context(root, continuation_pin, predecessor_pins):
    """Select an independently accepted helper; it must authenticate actual CAS before projection."""
    import importlib.util
    import result_coordination as c
    from scoped_candidate_adoption import _committed
    role = "operations-assistant-2"
    continuation = doc(root, continuation_pin)
    fields = {"schema", "task_id", "scope", "candidate_version", "original_qualified_native_handoff_continuation", "rule_history_contract",
        "candidate_manifest", "source_qa", "review_plan", "producer_outbox", "source_adoption",
        "adoption_followthrough_record_id", "review_context_helper", "prepared_only", *V5_REVIEW_FLAGS}
    require(set(continuation) == fields
        and continuation.get("schema") == "actual_qualified_rule_history_source_continuation/v1"
        and continuation.get("task_id") == QUALIFIED_NATIVE_HANDOFF_TASK
        and continuation.get("scope") == QUALIFIED_NATIVE_HANDOFF_SCOPE
        and continuation.get("candidate_version") == QUALIFIED_RULE_HISTORY_VERSION
        and set(predecessor_pins) == {*QUALIFIED_NATIVE_HANDOFF_PREDECESSORS, "original_qualified_native_handoff_continuation"}
        and continuation.get("original_qualified_native_handoff_continuation") == predecessor_pins["original_qualified_native_handoff_continuation"]
        and continuation.get("prepared_only") is False
        and all(continuation.get(key) is False for key in V5_REVIEW_FLAGS),
        "exact actual seventh successor must retain the original sixth and complete five-layer lineage")
    manifest_pin = pin(root, continuation.get("candidate_manifest")); manifest = doc(root, manifest_pin)
    helper_pin = pin(root, continuation.get("review_context_helper"))
    review_pin = pin(root, continuation.get("source_qa")); box = doc(root, review_pin)
    producer_pin = pin(root, continuation.get("producer_outbox")); review = box.get("candidate_review", {})
    require(manifest.get("schema") == "flashcast-exact-source-candidate/v1"
        and manifest.get("task_id") == QUALIFIED_NATIVE_HANDOFF_TASK
        and manifest.get("scope") == QUALIFIED_NATIVE_HANDOFF_SCOPE
        and manifest.get("candidate_version") == QUALIFIED_RULE_HISTORY_VERSION
        and manifest.get("primary_owner") == "system-development" and manifest.get("responsible_assistant") == role
        and manifest.get("candidate_fingerprint") == digest({key:value for key,value in manifest.items() if key != "candidate_fingerprint"})
        and len(manifest.get("files", [])) == len(QUALIFIED_RULE_HISTORY_PATHS)
        and {row.get("path") for row in manifest["files"]} == QUALIFIED_RULE_HISTORY_PATHS
        and helper_pin["path"] == str(Path(manifest_pin["path"]).parent / "rollback/source_review_context.py")
        and helper_pin in manifest.get("inputs", [])
        and manifest.get("predecessor_qualified_native_handoff_continuation") == continuation.get("original_qualified_native_handoff_continuation")
        and manifest.get("rule_history_contract") == continuation.get("rule_history_contract")
        and continuation.get("rule_history_contract") in manifest.get("inputs", [])
        and box.get("department") == role and box.get("task_id") == QUALIFIED_NATIVE_HANDOFF_TASK
        and box.get("candidate_version") == QUALIFIED_RULE_HISTORY_VERSION and box.get("scope") == QUALIFIED_NATIVE_HANDOFF_SCOPE
        and box.get("status") == "partial" and box.get("prepared_only", False) is False
        and not box.get("goal_acceptance") and box.get("qa_verdict") != "pass"
        and review.get("actor") == role and review.get("verdict") == "PASS_SOURCE_CANDIDATE_ONLY"
        and review.get("phase") == "candidate_source_only" and review.get("direction") == "forward"
        and review.get("candidate_manifest") == manifest_pin and review.get("candidate_fingerprint") == manifest["candidate_fingerprint"]
        and review.get("producer_outbox") == producer_pin and review.get("review_plan") == continuation.get("review_plan")
        and review.get("goal_contract") == manifest.get("goal_contract") and review.get("human_authorization") == manifest.get("human_authorization")
        and all(manifest.get(key) is False and box.get(key) is False and review.get(key) is False for key in V5_REVIEW_FLAGS),
        "independent exact source-only QA must accept the new helper before loading it")
    w.validate_outbox(root, [review_pin], role, QUALIFIED_NATIVE_HANDOFF_TASK)
    _native(root, box, [QUALIFIED_NATIVE_HANDOFF_TASK, QUALIFIED_RULE_HISTORY_VERSION, manifest["candidate_fingerprint"],
        producer_pin["sha256"], manifest_pin["sha256"], "PASS_SOURCE_CANDIDATE_ONLY"], role)
    journal = doc(root, pin(root, continuation.get("source_adoption")))
    handoffs = w._result_handoff_rows(root, QUALIFIED_NATIVE_HANDOFF_TASK)
    decisions = [row for row in handoffs if row.get("record_id") == journal.get("decision_record_id")]
    require(len(decisions) == 1, "one actual qualified handoff adoption decision required")
    decision = decisions[0]
    require(c.exact_identity(decision) == {"task_id":QUALIFIED_NATIVE_HANDOFF_TASK,"sender_department":"system-development",
        "candidate_version":QUALIFIED_RULE_HISTORY_VERSION,"result_sha256":producer_pin["sha256"]}
        and decision.get("event") == "controller_decision" and decision.get("decision") == "continue"
        and decision.get("outbox") == producer_pin and review_pin in decision.get("evidence", [])
        and decision.get("coordinator_role") == decision.get("decision_actor") == decision.get("responsible_assistant") == role
        and decision.get("next_owner") == role and decision.get("next_action") == "adopt-" + QUALIFIED_RULE_HISTORY_VERSION
        and decision.get("business_goal_closed") is False and decision.get("qa_status") != "pass",
        "new consumer namespace requires its real independent exact adoption continue")
    _committed(root, decision); _v5_source_decision_fence(root, decision, role)
    spec = importlib.util.spec_from_file_location("_flashcast_qualified_rule_history_review_context", w.safe_path(root, helper_pin["path"]))
    helper = importlib.util.module_from_spec(spec); spec.loader.exec_module(helper)
    require(helper.TASK == QUALIFIED_NATIVE_HANDOFF_TASK and helper.SCOPE == QUALIFIED_NATIVE_HANDOFF_SCOPE
        and helper.VERSION == QUALIFIED_RULE_HISTORY_VERSION and helper.ROLE == role
        and helper.PRODUCER == "system-development" and helper.SOURCE_PATHS == QUALIFIED_RULE_HISTORY_PATHS,
        "new reviewed helper cannot substitute an old goal, actor or source set")
    return helper.source_successor_context(root, pin(root, continuation_pin), predecessor_pins)



def _qualified_rule_history_current_lineage(root, proof, accepted, old_manifest_pin, historical):
    """Retain the actual sixth; authenticate the seventh's exact new effects."""
    if "consumer_authenticated_source_successions" in proof:
        return _qualified_source_successions_current_lineage(root, proof, accepted, old_manifest_pin, historical)
    if proof.get("consumer_qualified_history_window_continuation") is not None:
        return _qualified_history_window_current_lineage(root, proof, accepted, old_manifest_pin, historical)
    continuation_pin = proof.get("consumer_qualified_rule_history_continuation")
    if continuation_pin is None:
        return _qualified_native_handoff_current_lineage(root, proof, accepted, old_manifest_pin, historical)
    current = [pin(root, value) for value in proof.get("current_consumer_sources", [])]
    require(len(current) == len(SOURCES) and {value["path"] for value in current} == set(SOURCES)
        and current == [pin(root, value) for value in accepted.get("consumer_sources", [])],
        "all actual current consumers must retain exact bounded acceptance")
    predecessor_pins = {
        "historical_V5_manifest":pin(root, old_manifest_pin),
        "original_native_control_continuation":pin(root, proof.get("consumer_source_continuation")),
        "original_source_repair_continuation":pin(root, proof.get("consumer_source_repair_continuation")),
        "original_weekly_native_source_continuation":pin(root, proof.get("consumer_weekly_native_source_continuation")),
        "original_weekly_lineage_key_contract_repair_continuation":pin(root, proof.get("consumer_weekly_lineage_key_contract_repair_continuation")),
        "original_weekly_functional_result_entry_repair_continuation":pin(root, proof.get("consumer_weekly_functional_result_entry_repair_continuation")),
        "original_qualified_native_handoff_continuation":pin(root, proof.get("consumer_qualified_native_handoff_continuation"))}
    predecessor_pins["existing_T1_manifest"] = pin(root, doc(root,
        predecessor_pins["original_weekly_functional_result_entry_repair_continuation"])["candidate_manifest"])
    with _qualified_rule_history_context(root, continuation_pin, predecessor_pins) as context:
        require(isinstance(context, dict) and isinstance(context.get("modules"), dict)
            and isinstance(context.get("installed"), dict) and isinstance(context.get("predecessor_endpoint"), list),
            "authenticated isolated seventh-source context required")
        predecessor = context["predecessor_endpoint"]
        require(len(predecessor) == len(SOURCES) and [value.get("path") for value in predecessor] == list(SOURCES),
            "complete ordered actually adopted V3 endpoint required")
        before_proof = dict(proof); before_proof.pop("consumer_qualified_rule_history_continuation")
        before_proof["current_consumer_sources"] = predecessor
        before_accepted = dict(accepted); before_accepted["consumer_sources"] = predecessor
        reader = context["modules"].get("paid_three_page_bounded_cms")
        require(reader is not None and reader._qualified_rule_history_current_lineage is not _qualified_rule_history_current_lineage,
            "fresh exact reviewed consumer namespace required")
        actual_predecessor = reader._qualified_native_handoff_current_lineage(root, before_proof, before_accepted,
            old_manifest_pin, historical)
        require(actual_predecessor == predecessor,
            "complete original five layers and actual V3 sixth QA/CAS/committed/release chain must pass")
        installed = context["installed"]
        require(set(installed) == QUALIFIED_RULE_HISTORY_PATHS
            and all(isinstance(value, dict) and set(value) == {"path","sha256","size"} and value.get("path") == path
                for path,value in installed.items()), "only the independently adopted exact two-source set may succeed V3")
        endpoint = {value["path"]:value for value in actual_predecessor}; endpoint.update(installed)
        require(all(value == endpoint.get(value["path"]) for value in current),
            "actual consumers must equal the complete independently adopted seven-layer endpoint")
    require(current == [pin(root, value) for value in proof.get("current_consumer_sources", [])],
        "actual seventh successor consumers must remain exact after full historical readback")
    return current


QUALIFIED_HISTORY_WINDOW_VERSION = "qualified-native-handoff-envelope-recovery-source-candidate-v7-20261012"


def _history_window_helper(root, manifest_pin):
    """Load only the exact adjacent, full-pinned new source package helper."""
    import importlib.util
    manifest_pin = pin(root, manifest_pin)
    manifest = doc(root, manifest_pin)
    helper_pin = pin(root, manifest.get("history_window_helper"))
    require(manifest.get("task_id") == QUALIFIED_NATIVE_HANDOFF_TASK
        and manifest.get("scope") == QUALIFIED_NATIVE_HANDOFF_SCOPE
        and manifest.get("candidate_version") == QUALIFIED_HISTORY_WINDOW_VERSION
        and helper_pin["path"] == str(Path(manifest_pin["path"]).parent / "rollback/source_review_context.py")
        and helper_pin in manifest.get("inputs", [])
        and manifest.get("candidate_fingerprint") == digest({k:v for k,v in manifest.items() if k != "candidate_fingerprint"}),
        "exact same-goal history-window candidate helper required")
    spec = importlib.util.spec_from_file_location("_flashcast_qualified_history_window_context", w.safe_path(root, helper_pin["path"]))
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    require(helper.TASK == QUALIFIED_NATIVE_HANDOFF_TASK and helper.SCOPE == QUALIFIED_NATIVE_HANDOFF_SCOPE
        and helper.VERSION == QUALIFIED_HISTORY_WINDOW_VERSION and helper.ROLE == "operations-assistant-2"
        and helper.PRODUCER == "system-development" and helper.SOURCE_PATHS == QUALIFIED_RULE_HISTORY_PATHS,
        "new exact reviewed history-window helper identity required")
    helper.validate_package(root, manifest_pin)
    return helper


def _qualified_history_window_current_lineage(root, proof, accepted, old_manifest_pin, historical):
    """Read the real eighth effects while retaining all seven original layers."""
    if "consumer_authenticated_source_successions" in proof:
        return _qualified_source_successions_current_lineage(root, proof, accepted, old_manifest_pin, historical)
    continuation_pin = pin(root, proof["consumer_qualified_history_window_continuation"])
    continuation = doc(root, continuation_pin)
    helper = _history_window_helper(root, continuation.get("candidate_manifest"))
    current = [pin(root, value) for value in proof.get("current_consumer_sources", [])]
    require(len(current) == len(SOURCES) and {value["path"] for value in current} == set(SOURCES)
        and current == [pin(root, value) for value in accepted.get("consumer_sources", [])]
        and continuation.get("original_qualified_rule_history_continuation") == proof.get("consumer_qualified_rule_history_continuation")
        and continuation.get("original_qualified_native_handoff_continuation") == proof.get("consumer_qualified_native_handoff_continuation"),
        "actual eighth must retain exact original sixth/seventh and complete current consumers")
    with helper.source_successor_context(root, continuation_pin) as context:
        predecessor = context["predecessor_endpoint"]
        before_proof = dict(proof)
        before_proof.pop("consumer_qualified_history_window_continuation")
        before_proof["current_consumer_sources"] = predecessor
        before_accepted = dict(accepted)
        before_accepted["consumer_sources"] = predecessor
        reader = context["modules"]["paid_three_page_bounded_cms"]
        previous = reader._qualified_rule_history_current_lineage(root, before_proof, before_accepted, old_manifest_pin, historical)
        require(previous == predecessor, "complete actual original seven-layer history must return normally")
        endpoint = {value["path"]:value for value in previous}
        endpoint.update(context["installed"])
        require(all(value == endpoint.get(value["path"]) for value in current),
            "current endpoint must equal the real independently adopted eighth effects")
    require(current == [pin(root, value) for value in proof.get("current_consumer_sources", [])],
        "actual eighth current consumers must remain unchanged after the complete read")
    return current


SOURCE_SUCCESSION_SCHEMA = "flashcast-actual-authenticated-source-successor/v1"
SOURCE_BOOTSTRAP_SUCCESSION_SCHEMA = "flashcast-actual-source-bootstrap-successor/v1"
SOURCE_SUCCESSION_FIELD_SCHEMA = "flashcast-actual-config-field-cas/v1"
SOURCE_SUCCESSION_VERSION = "qualified-native-handoff-envelope-recovery-source-candidate-v9-20261012"
EN2_OWNER_SUCCESSION_TASK = "fc-20261014-english-kitchen-en2-original-dependency-continuation-v1"
EN2_OWNER_SUCCESSION_SCOPE = "project:flashcast:english-kitchen-exact-en2-registration:v1"
EN2_OWNER_SUCCESSION_VERSION = "english-kitchen-en2-exact-registration-candidate-v9-20261014"
EN2_OWNER_ORIGINAL_HISTORY = {"path": "logs/handoffs/2026-10-11-qualified-native-handoff-envelope-recovery-v1/assistant2-independent-review/post-V3-remaining-original-scope-v1/actual-v7-completed-intake-independent-adoption-v1/ROOT-ACTUAL-V7-stage-B-two-source-CAS-and-actual-readback-v1/actual-V7-eighth-source-durable-continuation.json",
    "sha256": "cdca07d63216ea2b058f26d125e676a5fb168b5391b142cc66b74d514dda360b", "size": 3868}
EN2_OWNER_RECOVERED_INDEX = {"path": "logs/handoffs/2026-10-14-complete-goal-continuity-v1/assistant2-CMS-business-continuation-v1/A2-EN2-current-seven-runtime-provenance-recovered-index-v1.json",
    "sha256": "62aa3bd07fd3e6d02e48f13e2e4e2176e62985ea812c9cbfa215af62d2a3ddfd", "size": 47112}
EN2_OWNER_RECOVERED_DECISION = {"path": "logs/handoffs/2026-10-14-complete-goal-continuity-v1/assistant2-CMS-business-continuation-v1/A2-ROOT-EN2-v4-real-source-facts-recovered-and-bounded-rework-v5.json",
    "sha256": "0b724fef41cecf6059420507c3b4c77c91ee94b68f61dbd3b33c471968c299b0", "size": 1338}
EN2_OWNER_HUMAN_AUTH = {"path": "logs/handoffs/2026-10-14-complete-goal-continuity-v1/assistant2-CMS-business-continuation-v1/actual-human-original-EN2-source-lineage-compatibility-authorization-v1.json",
    "sha256": "587881d4f9d84223ed4df26857547f952349df97f72d577b44f29cf7be86c103", "size": 5970}
EN2_OWNER_SOURCE_PATHS = {"tools/paid_three_page_bounded_cms.py", "tools/managed_cms_permit_issuer.py"}


def _source_successor_doc(root, value):
    import qa_review_plan as q
    value = _source_successor_shape(value)
    document = q._review_source_document(root,value)
    require(not any(document.get(key) is True for key in ("fixture_only","simulation","simulated",*V5_REVIEW_FLAGS)),
        "readback_required: original non-simulated source document required")
    return document


def _source_successor_shape(value):
    """A logical version is an exact identity, not an assertion about live bytes."""
    require(isinstance(value, dict) and set(value) == {"path", "sha256", "size"}
        and isinstance(value["path"], str) and bool(value["path"])
        and not Path(value["path"]).is_absolute() and str(Path(value["path"])) == value["path"]
        and ".." not in Path(value["path"]).parts
        and isinstance(value["sha256"], str) and re.fullmatch(r"[0-9a-f]{64}", value["sha256"])
        and type(value["size"]) is int and value["size"] >= 0,
        "readback_required: canonical complete source version required")
    return dict(value)


def _source_successor_versions(values):
    require(isinstance(values, list) and values and all(isinstance(value, dict) for value in values),
        "readback_required: complete predecessor source boundary required")
    values = [_source_successor_shape(value) for value in values]
    require(len({value["path"] for value in values}) == len(values),
        "readback_required: unique predecessor source paths required")
    require(not any(value["path"] == "data/task-contract.json" for value in values),
        "field CAS configuration must not become a whole-file source version")
    return values


def _source_successor_files(root, manifest_pin, manifest, journal_pin, journal, predecessor, continuation_pin):
    """Read exact physical CAS backups; this alone does not authenticate adoption."""
    directory = Path(manifest_pin["path"]).parent
    files, operations = manifest.get("files"), journal.get("source_operations")
    require(isinstance(files, list) and files and isinstance(operations, list)
        and all(isinstance(row, dict) for row in files + operations)
        and len(files) == len(operations) == len({row.get("path") for row in files})
        and {row.get("path") for row in files} == {row.get("path") for row in operations}
        and isinstance(journal.get("applied"), list) and len(journal["applied"]) == len(files)
        and set(journal["applied"]) == {row["path"] for row in files},
        "readback_required: every reviewed source needs one actual CAS operation")
    before_map = {row["path"]: row for row in _source_successor_versions(predecessor)}
    installed, backings = {}, []
    execution = journal.get("execution_id")
    require(isinstance(execution, str) and bool(execution.strip())
        and type(journal.get("operator_source_syscalls_attempted")) is int
        and journal["operator_source_syscalls_attempted"] == len(files),
        "readback_required: actual complete source syscall identity required")
    for row in files:
        path = row.get("path")
        require(isinstance(path, str) and path != "data/task-contract.json" and path in before_map,
            "reviewed source must retain its real immediate predecessor; configuration uses field CAS")
        op = next(value for value in operations if value["path"] == path)
        baseline, candidate, backup = [pin(root, value) for value in
            (row.get("baseline"), row.get("candidate"), op.get("backup"))]
        first = w.safe_path(root, baseline["path"]).read_bytes()
        last = w.safe_path(root, candidate["path"]).read_bytes()
        require(baseline["path"] == str(directory / "baseline" / path)
            and candidate["path"] == str(directory / "candidate" / path)
            and row.get("candidate_relative_path") == "candidate/" + path
            and row.get("before") == _content_pair(first)
            and row.get("after") == _content_pair(last)
            and before_map[path] == {"path":path, **row["before"]}
            and backup["path"] == f"backups/{manifest['task_id']}/{manifest['candidate_fingerprint']}/forward/{path}"
            and backup["sha256"] == baseline["sha256"] and backup["size"] == baseline["size"]
            and w.safe_path(root, backup["path"]).read_bytes() == first,
            "readback_required: immediate before and original physical journal backup must match")
        require(op.get("before") == row["before"] and op.get("after_expected") == op.get("after_actual") == row["after"]
            and op.get("write_attempted") is True and op.get("source_syscall_attempted") is True
            and op.get("verified_after") is True and type(row.get("before_mode")) is int
            and type(row.get("after_mode")) is int and 0 <= row["before_mode"] <= 0o777
            and 0 <= row["after_mode"] <= 0o777 and op.get("before_mode") == row["before_mode"]
            and all(w.safe_path(root, value["path"]).stat().st_mode & 0o777 == mode for value, mode in
                ((baseline,row["before_mode"]),(backup,row["before_mode"]),(candidate,row["after_mode"])))
            and op.get("temporary_path") == path + ".cas-" + execution,
            "readback_required: actual attempted, verified CAS bytes and physical modes required")
        for direction, old, new in (("forward", first, last), ("reverse", last, first)):
            frozen = pin(root, row.get(direction + "_diff"))
            expected = "".join(difflib.unified_diff(old.decode("utf-8").splitlines(keepends=True),
                new.decode("utf-8").splitlines(keepends=True), fromfile="a/" + path, tofile="b/" + path)).encode("utf-8")
            require(w.safe_path(root, frozen["path"]).read_bytes() == expected,
                "readback_required: original complete forward/reverse source deltas required")
        installed[path] = {"path":path, **row["after"]}
        backings.append({"logical":before_map[path], "backup":backup, "mode":row["before_mode"],
            "journal_pin":journal_pin, "continuation_pin":continuation_pin})
    return installed, backings


def _source_successor_field_effects(root, continuation, manifest_pin, manifest, source_journal):
    """Prove only the reviewed field change; never project an old entire config."""
    changes, journals = manifest.get("field_changes", []), continuation.get("field_adoptions")
    require(isinstance(changes, list) and isinstance(journals, list) and len(changes) == len(journals),
        "readback_required: every field change needs its independent actual field CAS journal")
    require(source_journal.get("field_adoptions", []) == journals,
        "readback_required: committed source effect journal must bind every exact field effect journal")
    effects, identities = [], set()
    for candidate_pin, journal_pin in zip(changes, journals):
        candidate_pin, journal_pin = pin(root, candidate_pin), pin(root, journal_pin)
        candidate, journal = _source_successor_doc(root, candidate_pin), _source_successor_doc(root, journal_pin)
        source, field = candidate.get("source"), candidate.get("field")
        require(source == "data/task-contract.json" and isinstance(field, str) and bool(field)
            and (source,field) not in identities and candidate_pin in manifest.get("inputs", [])
            and candidate.get("schema_version") == "flashcast-exact-config-field-candidate-v1"
            and candidate.get("task_id") == manifest["task_id"] and candidate.get("mode") == "field_CAS_only"
            and candidate.get("preserve_all_other_fields") is True and candidate.get("actual_configuration_write") is False
            and candidate.get("expected_sha256") == digest(candidate.get("expected")),
            "exact reviewed single-field candidate and canonical before required")
        identities.add((source,field))
        require(journal.get("schema") == SOURCE_SUCCESSION_FIELD_SCHEMA
            and all(journal.get(key) == value for key,value in {
                "task_id":manifest["task_id"], "candidate_version":manifest["candidate_version"],
                "candidate_fingerprint":manifest["candidate_fingerprint"], "candidate_manifest":manifest_pin,
                "review_outbox":continuation["source_qa"], "authorized_source":manifest["human_authorization"],
                "actor":ROLE, "source":source, "field":field, "candidate":candidate_pin,
                "direction":"forward", "status":"complete", "execution_id":source_journal["execution_id"],
                "decision_record_id":source_journal["decision_record_id"]}.items())
            and journal.get("write_attempted") is True and journal.get("verified_after") is True
            and journal.get("preserve_all_other_fields") is True and journal.get("effect_uncertain") is False
            and journal.get("permissions_issued") is False and type(journal.get("external_writes")) is int
            and journal["external_writes"] == 0,
            "readback_required: exact actual independently reviewed field CAS effect required")
        before_pin, after_pin = pin(root, journal.get("before_backup")), pin(root, journal.get("after_readback"))
        before, after = _source_successor_doc(root, before_pin), _source_successor_doc(root, after_pin)
        prefix = f"backups/{manifest['task_id']}/{manifest['candidate_fingerprint']}/forward/fields/"
        require(before_pin["path"].startswith(prefix) and after_pin["path"].startswith(prefix)
            and field in before and field in after and before[field] == candidate.get("expected")
            and after[field] == candidate.get("replacement")
            and {key:value for key,value in before.items() if key != field} == {key:value for key,value in after.items() if key != field}
            and journal.get("before_canonical_sha256") == digest(before[field])
            and journal.get("after_canonical_sha256") == digest(after[field]),
            "readback_required: true field backup/after readback must preserve every other field")
        started, completed = [w._parse_observed_at(journal.get(key)) for key in ("started_at", "completed_at")]
        source_started, source_completed = [w._parse_observed_at(source_journal.get(key)) for key in ("started_at", "completed_at")]
        require(all(value is not None for value in (started,completed,source_started,source_completed))
            and source_started <= started <= completed <= source_completed,
            "readback_required: field effects must belong to the real source execution interval")
        effects.append({"source":source, "field":field, "candidate_pin":candidate_pin, "journal_pin":journal_pin,
            "before_backup":before_pin, "after_readback":after_pin, "replacement":after[field]})
    return effects


def _source_successor_assignment_round(root, snapshot, receipts, plan, source_pins, backings, field_effects):
    """Read one original responsibility round with exact historical digest IO.

    This private reader grants no binding, QA or adoption authority. Its caller
    first checks every layer's immutable governance and physical effects. Only
    the original closed-pin guard receives historical bytes; native documents,
    package files, current configuration and all ledgers use their real paths.
    """
    import qa_review_plan as q
    root = Path(root).resolve()
    by_version = {}
    maker = "logs/handoffs/2026-10-10-weekly-safe-cleanup-native-enablement-v1/actual-native-configuration-v1/make_actual_weekly_native_evidence.py"
    prompts = {"prompts/department-dispatch.md", "prompts/department-single-primary-dispatch.md",
        "prompts/master-controller.md"}
    for row in backings:
        logical = _source_successor_shape(row["logical"])
        executable = (logical["path"].startswith("tools/") and logical["path"].endswith(".py")) or logical["path"] == maker
        require(executable or logical["path"] in prompts,
            "only exact original source bytes may supply a responsibility closure")
        backup = pin(root, row["backup"])
        require(all(backup[key] == logical[key] for key in ("sha256", "size"))
            and type(row["mode"]) is int and w.safe_path(root, backup["path"]).stat().st_mode & 0o777 == row["mode"],
            "exact physical responsibility source backup byte/mode required")
        if not executable:
            continue
        key = tuple(logical[name] for name in ("path", "sha256", "size"))
        by_version.setdefault(key, []).append((backup, row["mode"]))
    for effect in field_effects:
        require(effect["source"] == "data/task-contract.json", "only an exact reviewed field snapshot input is legal")
        for name in ("before_backup", "after_readback"):
            backup = pin(root, effect[name])
            logical = {"path":effect["source"], **{key:backup[key] for key in ("sha256", "size")}}
            key = tuple(logical[name] for name in ("path", "sha256", "size"))
            by_version.setdefault(key, []).append((backup, None))
    original_closed, original_digest = q._closed_review_source_pins, w.file_digest
    def closed(project, values):
        require(Path(project).resolve() == root, "original responsibility project mismatch")
        values = list(values); selected = {}
        for value in values:
            logical = _source_successor_shape(value)
            key = tuple(logical[name] for name in ("path", "sha256", "size"))
            if key in by_version:
                require(logical["path"] not in selected or selected[logical["path"]][0] == logical,
                    "conflicting original responsibility source versions refused")
                selected[logical["path"]] = (logical, by_version[key])
        def digest_only(base, name):
            require(Path(base).resolve() == root, "historical digest project mismatch")
            if name not in selected:
                return original_digest(base, name)
            logical, physical = selected[name]
            for backup, mode in physical:
                observed = original_digest(base, backup["path"])
                require(observed == backup and all(observed[key] == logical[key] for key in ("sha256", "size"))
                    and (mode is None or w.safe_path(base, backup["path"]).stat().st_mode & 0o777 == mode),
                    "responsibility physical backup changed during exact digest read")
            return dict(logical)
        prior = w.file_digest
        try:
            require(prior is original_digest, "nested or foreign historical digest provider refused")
            w.file_digest = digest_only
            return original_closed(project, values)
        finally:
            w.file_digest = prior
    try:
        q._closed_review_source_pins = closed
        with _source_bootstrap_assignment_context(root,backings):
            return q._assigned_review_round(root, snapshot, receipts, plan, source_pins=source_pins)
    finally:
        q._closed_review_source_pins, w.file_digest = original_closed, original_digest


def _source_bootstrap_assignment_context(root,backings):
    """After actual-layer preflight only, supplement an old plan's native reads."""
    import contextlib,importlib.util,qa_review_plan as q
    stack=contextlib.ExitStack();seen={}
    try:
        for row in backings:
            frozen=pin(root,row.get('journal_pin'));journal=_source_successor_doc(root,frozen)
            if 'bootstrap_review_contract' not in journal:continue
            seen[frozen['path']]=(frozen,journal)
        require(len(seen)<=1,'only the precise original TNEW bootstrap native supplement may be read')
        for frozen,journal in seen.values():
            mp=pin(root,journal.get('candidate_manifest'));manifest=_source_successor_doc(root,mp)
            require(manifest.get('task_id')=='fc-20261011-goal-publication-notice-followthrough-repair-v1'
                and manifest.get('scope')=='project:flashcast:goal-publication-notice-followthrough-repair:v1'
                and manifest.get('candidate_version')=='goal-publication-notice-followthrough-source-candidate-v29-20261013'
                and journal.get('status')=='complete' and journal.get('effect_uncertain') is False
                and journal.get('field_adoptions')==[] and manifest.get('field_changes')==[],
                'readback_required: actual exact zero-field bootstrap journal owns additional native source reads')
            helper_pin=pin(root,manifest.get('source_review_helper'))
            require(helper_pin==manifest.get('source_successor_helper') and helper_pin in manifest.get('inputs',[])
                and helper_pin['path']==str(Path(mp['path']).parent/'rollback/source_review_context.py'),
                'exact independently reviewed adjacent native supplement helper required')
            spec=importlib.util.spec_from_file_location('_flashcast_actual_bootstrap_assignment_context',w.safe_path(root,helper_pin['path']))
            helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
            _,contract=helper.bootstrap_contract(root,mp,pin(root,journal['bootstrap_review_contract']))
            stack.enter_context(helper.bootstrap_history_responsibility(root,q,w,manifest,contract))
        return stack
    except BaseException:stack.close();raise


def _source_bootstrap_governance(root,continuation,manifest_pin,manifest,journal_pin,journal,*,
        defer_assignment=False,assignment_backings=None,assignment_fields=()):
    """Independent real bootstrap before new binding; ordinary layers are unchanged."""
    import importlib.util
    import goal_delivery_runtime as g,qa_review_plan as q,result_coordination as c
    from scoped_candidate_adoption import _committed
    task,version,scope=manifest['task_id'],manifest['candidate_version'],manifest['scope']
    require(task=='fc-20261011-goal-publication-notice-followthrough-repair-v1'
        and scope=='project:flashcast:goal-publication-notice-followthrough-repair:v1'
        and version=='goal-publication-notice-followthrough-source-candidate-v29-20261013'
        and manifest.get('field_changes')==[] and continuation.get('field_adoptions')==[]
        and {row.get('path') for row in manifest.get('files',[])}=={'tools/qa_review_plan.py','tools/paid_three_page_bounded_cms.py',
            'tools/workflow_control.py','tools/goal_delivery_runtime.py','tools/parent_initial_dispatch.py',
            'tools/result_coordination.py'},
        'readback_required: only original authorized six-source zero-field TNEW entry bootstrap')
    helper_pin=pin(root,continuation.get('review_context_helper'))
    require(helper_pin==manifest.get('source_review_helper')==manifest.get('source_successor_helper')
        and helper_pin in manifest.get('inputs',[])
        and helper_pin['path']==str(Path(manifest_pin['path']).parent/'rollback/source_review_context.py'),
        'readback_required: exact independently reviewed adjacent bootstrap helper')
    spec=importlib.util.spec_from_file_location('_flashcast_actual_tnew_bootstrap_reader',w.safe_path(root,helper_pin['path']))
    helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
    require(helper.TASK==task and helper.SCOPE==scope and helper.VERSION==version and helper.ROLE==ROLE
        and helper.BOOTSTRAP_SUCCESSOR_SCHEMA=='flashcast-actual-source-bootstrap-successor/v1',
        'readback_required: exact reviewed bootstrap helper identity')
    snapshot=g.restore_goal(root,w.read_json(w.snapshot_path(root,task)))
    contract_pin=pin(root,continuation.get('bootstrap_review_contract'))
    responsibility=q.tnew_entry_bootstrap_responsibility(root,snapshot,manifest_pin,contract_pin,
        defer_assignment=defer_assignment,assignment_backings=assignment_backings,assignment_fields=assignment_fields)
    producer_pin=pin(root,continuation.get('producer_outbox'));review_pin=pin(root,continuation.get('source_qa'))
    require(responsibility['producer_pin']==producer_pin,'exact current bootstrap PP responsibility')
    reviewed=helper.bootstrap_review(root,manifest_pin,manifest,contract_pin,review_pin)
    require(reviewed['producer_pin']==producer_pin and journal_pin['path']==f"backups/{task}/{manifest['candidate_fingerprint']}/forward/journal.json"
        and all(journal.get(k)==v for k,v in {'task_id':task,'candidate_version':version,'candidate_fingerprint':manifest['candidate_fingerprint'],
            'candidate_manifest':manifest_pin,'review_outbox':review_pin,'bootstrap_review_contract':contract_pin,
            'authorized_source':manifest['human_authorization'],'actor':ROLE,'direction':'forward','status':'complete',
            'source_effect_state':'ALL_REVIEWED_AFTER_VERIFIED'}.items())
        and journal.get('effect_uncertain') is False and journal.get('permissions_issued') is False
        and type(journal.get('external_writes')) is int and journal['external_writes']==0
        and journal.get('field_adoptions')==[] and type(journal.get('operator_field_syscalls_attempted')) is int
        and journal['operator_field_syscalls_attempted']==0,
        'readback_required: actual certain zero-field independent bootstrap source CAS journal')
    rows=w._result_handoff_rows(root,task)
    decisions=[row for row in rows if row.get('record_id')==journal.get('decision_record_id')]
    follows=[row for row in rows if row.get('record_id')==continuation.get('adoption_followthrough_record_id')]
    require(len(decisions)==len(follows)==1,'readback_required: unique actual bootstrap adoption and readback')
    decision,follow=decisions[0],follows[0];identity=responsibility['identity']
    intake=next(row for row in rows if row.get('record_id')==responsibility['intake_record_id'])
    require(c.exact_identity(decision)==c.exact_identity(follow)==identity and decision.get('event')=='controller_decision'
        and decision.get('decision')=='continue' and decision.get('outbox')==producer_pin
        and review_pin in decision.get('evidence',[]) and contract_pin in decision.get('evidence',[])
        and decision.get('next_owner')==ROLE and decision.get('next_action')=='adopt-'+version
        and decision.get('business_goal_closed') is False and decision.get('qa_status')!='pass'
        and all(row.get('coordinator_role')==row.get('decision_actor')==row.get('responsible_assistant')==ROLE for row in (decision,follow))
        and follow.get('event')=='controller_followthrough' and follow.get('followthrough_status')=='blocked_with_owner'
        and follow.get('outbox')==producer_pin and follow.get('business_goal_closed') is False
        and follow.get('coordinator_owner')==intake.get('coordinator_owner')==decision.get('coordinator_owner')
        and follow.get('coordination_fence')==decision.get('coordination_fence')
        and journal_pin in follow.get('evidence',[]) and isinstance(follow.get('unblock_condition'),str)
        and follow['unblock_condition'].startswith('source-adopted:'+journal['execution_id']+';remaining:')
        and bool(follow['unblock_condition'].split(';remaining:',1)[1].strip())
        and rows.index(intake)<rows.index(decision)<rows.index(follow),
        'readback_required: same original independent claim/fence intake/decision/actual followthrough')
    require(journal.get('coordination_epoch_sources')==continuation.get('coordination_epoch_sources'),
        'readback_required: exact actual bootstrap epoch sources in CP and JP')
    require(journal.get('registry_health_registration_sources')==continuation.get('registry_health_registration_sources'),'exact runtime registration sources in JP/CP')
    helper.bootstrap_registry_capture_guard(root,manifest,journal.get('registry_control_capture'),journal=journal)
    lifecycle=helper.bootstrap_lifecycle(root,manifest,intake,decision,follow=follow,journal=journal,epoch_sources=continuation['coordination_epoch_sources'])
    _committed(root,decision);_v5_source_decision_fence(root,decision,ROLE)
    _committed(root,follow);fence=_v5_source_decision_fence(root,follow,ROLE)
    released=_source_release_readback(root,follow,fence)
    box=_source_successor_doc(root,review_pin)
    times=[w._parse_observed_at(value) for value in (box.get('created_at'),decision.get('created_at'),journal.get('started_at'),journal.get('completed_at'))]
    require(all(value is not None for value in times)
        and times[0].timestamp()<=lifecycle['decision_reserved_at']<=lifecycle['decision_committed_at']<=times[2].timestamp()<=times[3].timestamp()
        and times[-1]<=dt.datetime.now(dt.timezone.utc)
        and times[-1].timestamp()<=fence['reserved_at']<=fence['committed_at']<=released['released_at'],
        'readback_required: independent native bootstrap QA/actual decision/CAS/commit/release order')
    return {'governance_model':'independent_source_bootstrap','bootstrap_review_contract':contract_pin,
        'producer_pin':producer_pin,'review_pin':review_pin,'historical_review_plan':responsibility['historical_plan_pin'],
        'historical_source_continuation':responsibility['historical_continuation_pin'],
        'decision_record_id':decision['record_id'],'follow_record_id':follow['record_id'],
        'released_at':released['released_at'],'started_at':times[2].timestamp(),'completed_at':times[3].timestamp()}


def _source_successor_governance(root, continuation, manifest_pin, manifest, journal_pin, journal, *,
        defer_assignment=False, assignment_backings=None, assignment_fields=(), exact_en2=False):
    """Authenticate original authority, A2 native QA, producer and committed effects."""
    if continuation.get("schema") == SOURCE_BOOTSTRAP_SUCCESSION_SCHEMA:
        return _source_bootstrap_governance(root,continuation,manifest_pin,manifest,journal_pin,journal,
            defer_assignment=defer_assignment,assignment_backings=assignment_backings,assignment_fields=assignment_fields)
    import goal_delivery_runtime as g
    import qa_review_plan as q
    import result_coordination as c
    from scoped_candidate_adoption import _committed, _receipts
    require(type(defer_assignment) is bool and not (defer_assignment and assignment_backings is not None),
        "separate read-only effect preflight and complete responsibility stage required")
    task, version, scope = manifest["task_id"], manifest["candidate_version"], manifest["scope"]
    snapshot = g.restore_goal(root, w.read_json(w.snapshot_path(root, task)))
    goal = g.validate_goal(root, snapshot.get("goal_delivery"), task_id=task)
    require(snapshot.get("task_id") == task and snapshot.get("goal_contract") == manifest.get("goal_contract")
        and goal.get("authorization_pin") == manifest.get("human_authorization")
        and goal.get("primary_owner") == "system-development" and goal.get("producer_departments") == ["system-development"]
        and goal.get("responsible_assistant") == ROLE and q._goal_reviewer(root, snapshot) == ROLE
        and scope in goal.get("authorized_scope", []) and goal.get("acceptance_capability") == "development",
        "readback_required: actual original human authorization and sole independent A2 source goal required")
    producer_pin, review_pin, plan_pin = [pin(root, continuation.get(key)) for key in
        ("producer_outbox", "source_qa", "review_plan")]
    producer, box, plan = [_source_successor_doc(root, value) for value in (producer_pin,review_pin,plan_pin)]
    evidence = producer.get("evidence")
    require(isinstance(evidence, (dict, list)) and bool(evidence),
        "exact native producer PP requires complete named or listed evidence pins")
    evidence_values = list(evidence.values()) if isinstance(evidence, dict) else evidence
    require(all(isinstance(value, dict) and set(value) == {"path", "sha256", "size"} for value in evidence_values),
        "exact native producer PP requires direct complete evidence pins")
    evidence_pins = [_source_successor_shape(value) for value in q._evidence_pins(evidence)]
    manifest_evidence = [value for value in evidence_pins if value["path"] == manifest_pin["path"]]
    require(producer.get("candidate_fingerprint") == manifest["candidate_fingerprint"]
        and len(manifest_evidence) == 1 and manifest_evidence[0] == manifest_pin
        and (not isinstance(evidence, dict) or evidence.get("candidate_manifest") == manifest_pin)
        and producer.get("scope") == scope and producer.get("prepared_only") is False
        and all(producer.get(key) is False for key in V5_REVIEW_FLAGS),
        "exact native producer PP must bind the reviewed MP/fingerprint and source-only bounds")
    receipts = _receipts(root, task)
    require(not w.validate_workflow_events(root, task), "readback_required: intact original workflow events required")
    events = [row for row in w.read_jsonl(Path(root) / w.WORKFLOW_EVENTS) if row.get("task_id") == task]
    if exact_en2:
        import importlib.util
        require(task == EN2_OWNER_SUCCESSION_TASK and scope == EN2_OWNER_SUCCESSION_SCOPE
                and version == EN2_OWNER_SUCCESSION_VERSION
                and {row.get("path") for row in manifest.get("files", [])} == EN2_OWNER_SOURCE_PATHS
                and len(manifest.get("files", [])) == 2 and manifest.get("field_changes") == [],
                "readback_required: exact EN2 local source-only responsibility only")
        helper_pin = pin(root, continuation.get("review_context_helper"))
        require(helper_pin == manifest.get("source_review_helper")
                and helper_pin == manifest.get("source_successor_helper")
                and helper_pin in manifest.get("inputs", [])
                and helper_pin["path"] == str(Path(manifest_pin["path"]).parent / "rollback/source_review_context.py"),
                "readback_required: exact adjacent EN2 helper required")
        spec = importlib.util.spec_from_file_location("_flashcast_exact_en2_source_context", w.safe_path(root, helper_pin["path"]))
        helper = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(helper)
        require(helper.TASK == task and helper.VERSION == version and helper.SCOPE == scope,
                "readback_required: exact EN2 helper identity required")
        local = helper.successor_plan(root, manifest_pin, producer_pin, plan_pin)
        bound = [{"created_at": local["created_at"]}]
    else:
        bound = [row for row in events if row.get("details", {}).get("qa_review_plan_bound", {}).get("pin") == plan_pin]
        require(len(bound) == 1, "readback_required: one immutable exact source-plan binding required")
        binding = bound[0]["details"]["qa_review_plan_bound"]
        require(binding in q._bindings(root, snapshot) and binding.get("reviewer_department") == ROLE,
            "readback_required: actual original A2 binding required")
        original_snapshot = {**snapshot, "qa_review_plan":binding}
        q.validate_plan(root, original_snapshot, plan)
        require(isinstance(plan.get("original_goal_continuation_sources", []), list)
            and all(value in manifest.get("inputs", []) for value in plan.get("original_goal_continuation_sources", [])),
            "reviewed manifest must close every saved original responsibility source in its exact plan")
        require(plan.get("task_id") == task and plan.get("scope") == scope and plan.get("candidate_version") == version
            and plan.get("candidate") == producer_pin and plan.get("candidate_sha256") == producer_pin["sha256"]
            and plan.get("producer_department") == "system-development" and plan.get("reviewer_department") == ROLE
            and plan.get("controller_department") == ROLE and plan.get("action_class") == "internal_control_candidate"
            and q._producer_candidate_bound(root, plan, producer_pin, producer),
            "readback_required: exact MP/PP/plan and full actual responsibility/native ACK chain required")
        if not defer_assignment:
            assigned = (q._assigned_review_round(root, original_snapshot, receipts, plan, source_pins=manifest.get("inputs"))
                if assignment_backings is None else _source_successor_assignment_round(root, original_snapshot,
                    receipts, plan, manifest.get("inputs"), assignment_backings, assignment_fields))
            require(assigned is not None, "readback_required: complete actual original responsibility/native ACK chain required")
    for frozen, actor in ((producer_pin,"system-development"),(review_pin,ROLE)):
        w.validate_outbox(root, [frozen], actor, task)
    review = box.get("candidate_review", {})
    require(box.get("department") == ROLE and box.get("task_id") == task and box.get("candidate_version") == version
        and box.get("scope") == scope and box.get("status") == "partial" and not box.get("goal_acceptance")
        and box.get("qa_verdict") != "pass" and box.get("prepared_only", False) is False
        and all(review.get(key) == value for key,value in {"actor":ROLE,"verdict":"PASS_SOURCE_CANDIDATE_ONLY",
            "phase":"candidate_source_only","direction":"forward","candidate_manifest":manifest_pin,
            "candidate_fingerprint":manifest["candidate_fingerprint"],"producer_outbox":producer_pin,
            "review_plan":plan_pin,"goal_contract":manifest["goal_contract"],"human_authorization":manifest["human_authorization"]}.items())
        and all(box.get(key) is False and review.get(key) is False for key in V5_REVIEW_FLAGS),
        "readback_required: actual independent exact A2 source-only QA required")
    _native(root, box, [task,version,manifest["candidate_fingerprint"],producer_pin["sha256"],
        manifest_pin["sha256"],"PASS_SOURCE_CANDIDATE_ONLY"], ROLE)
    require(journal_pin["path"] == f"backups/{task}/{manifest['candidate_fingerprint']}/forward/journal.json"
        and all(journal.get(key) == value for key,value in {"task_id":task,"candidate_version":version,
            "candidate_fingerprint":manifest["candidate_fingerprint"],"candidate_manifest":manifest_pin,
            "review_outbox":review_pin,"authorized_source":manifest["human_authorization"],"actor":ROLE,
            "direction":"forward","status":"complete","source_effect_state":"ALL_REVIEWED_AFTER_VERIFIED"}.items())
        and type(journal.get("external_writes")) is int and journal["external_writes"] == 0
        and journal.get("effect_uncertain") is False and journal.get("permissions_issued") is False,
        "readback_required: actual certain independent source CAS journal required")
    rows = w._result_handoff_rows(root, task)
    decisions = [row for row in rows if row.get("record_id") == journal.get("decision_record_id")]
    follows = [row for row in rows if row.get("record_id") == continuation.get("adoption_followthrough_record_id")]
    require(len(decisions) == len(follows) == 1, "readback_required: unique actual adoption and effect readback required")
    decision, follow = decisions[0], follows[0]
    identity = {"task_id":task,"sender_department":"system-development","candidate_version":version,
        "result_sha256":producer_pin["sha256"]}
    require(c.exact_identity(decision) == c.exact_identity(follow) == identity
        and decision.get("event") == "controller_decision" and decision.get("decision") == "continue"
        and decision.get("outbox") == producer_pin and review_pin in decision.get("evidence", [])
        and (not exact_en2 or plan_pin in decision.get("evidence", []))
        and decision.get("next_owner") == ROLE and decision.get("next_action") == "adopt-" + version
        and decision.get("business_goal_closed") is False and decision.get("qa_status") != "pass"
        and all(row.get("coordinator_role") == row.get("decision_actor") == row.get("responsible_assistant") == ROLE for row in (decision,follow))
        and follow.get("event") == "controller_followthrough" and follow.get("followthrough_status") == "blocked_with_owner"
        and follow.get("outbox") == producer_pin and follow.get("business_goal_closed") is False
        and follow.get("coordinator_owner") == decision.get("coordinator_owner")
        and follow.get("coordination_fence") == decision.get("coordination_fence")
        and journal_pin in follow.get("evidence", []) and isinstance(follow.get("unblock_condition"), str)
        and follow["unblock_condition"].startswith("source-adopted:" + journal["execution_id"] + ";remaining:")
        and bool(follow["unblock_condition"].split(";remaining:",1)[1].strip()) and rows.index(decision) < rows.index(follow),
        "readback_required: authentic committed source decision/followthrough required")
    c._validate_queued(root, identity); c._goal_actor(root, identity, ROLE)
    queues = [row for row in rows if row.get("event") == "notification_queued" and c.exact_identity(row) == identity]
    intakes = [row for row in rows if row.get("event") == "controller_received" and c.exact_identity(row) == identity]
    received = [row for row in receipts if row.get("department") == "system-development"
        and row.get("receipt_type") == "outbox_received" and producer_pin in row.get("evidence", [])]
    require(len(queues) == len(intakes) == len(received) == 1
        and intakes[0].get("coordinator_role") == ROLE and rows.index(queues[0]) < rows.index(intakes[0]) < rows.index(decision),
        "readback_required: real completed producer queue, intake and receipt required")
    fixed = w.department_registry(root)["system-development"]["chat_binding"]["task_id"]
    require(queues[0].get("source_thread_id") == fixed and queues[0].get("source_turn_id") == producer.get("source_turn_id"),
        "original native producer turn must exactly own its source result")
    w._validate_goal_completed_result(root, queues[0], fixed, through_receipt_id=received[0]["receipt_id"])
    _committed(root, intakes[0]); _committed(root, decision); _v5_source_decision_fence(root, decision, ROLE)
    _committed(root, follow); fence = _v5_source_decision_fence(root, follow, ROLE)
    released = _source_release_readback(root, follow, fence)
    times = [w._parse_observed_at(value) for value in
        (bound[0].get("created_at"),box.get("created_at"),journal.get("started_at"),journal.get("completed_at"))]
    require(all(value is not None for value in times) and times == sorted(times)
        and times[-1] <= dt.datetime.now(dt.timezone.utc)
        and times[-1].timestamp() <= fence["reserved_at"] <= fence["committed_at"] <= released["released_at"],
        "readback_required: native QA, actual CAS and permanent commit/release order required")
    return {"review_plan":plan_pin,"producer_pin":producer_pin,"review_pin":review_pin,
        "decision_record_id":decision["record_id"],"follow_record_id":follow["record_id"],
        "released_at":released["released_at"],"started_at":times[2].timestamp(),"completed_at":times[3].timestamp()}


def _source_bootstrap_prior_history_context(root,continuation_pins):
    """A real last bootstrap journal provides context; full auth still follows."""
    import contextlib
    selected=[]
    for frozen in continuation_pins:
        continuation=_source_successor_doc(root,pin(root,frozen))
        if continuation.get('schema')!=SOURCE_BOOTSTRAP_SUCCESSION_SCHEMA:continue
        require(continuation.get('task_id')=='fc-20261011-goal-publication-notice-followthrough-repair-v1'
            and continuation.get('scope')=='project:flashcast:goal-publication-notice-followthrough-repair:v1'
            and continuation.get('candidate_version')=='goal-publication-notice-followthrough-source-candidate-v29-20261013'
            and frozen==continuation_pins[-1] and continuation.get('prepared_only') is False
            and all(continuation.get(key) is False for key in V5_REVIEW_FLAGS),
            'readback_required: only the actual final original bootstrap owns historical semantic context')
        mp=pin(root,continuation.get('candidate_manifest'));manifest=_source_successor_doc(root,mp)
        require(manifest.get('source_review_helper')==continuation.get('review_context_helper')
            and continuation.get('source_adoption') not in (None,{}),
            'readback_required: exact original reviewed helper and physical source journal required')
        selected.append({'journal_pin':pin(root,continuation['source_adoption'])})
    require(len(selected)<=1,'readback_required: no ambiguous bootstrap historical context')
    return _source_bootstrap_assignment_context(root,selected) if selected else contextlib.nullcontext()


def _en2_owner_predecessor_boundary(root, manifest_pin, manifest):
    """Keep the old proof and read the one later endpoint from the same helper."""
    index = doc(root, EN2_OWNER_RECOVERED_INDEX)
    decision = doc(root, EN2_OWNER_RECOVERED_DECISION)
    pin(root, EN2_OWNER_HUMAN_AUTH)
    old = doc(root, EN2_OWNER_ORIGINAL_HISTORY)
    require(old.get("schema") == "actual_qualified_history_window_source_continuation/v1"
        and old.get("task_id") == QUALIFIED_NATIVE_HANDOFF_TASK
        and old.get("scope") == QUALIFIED_NATIVE_HANDOFF_SCOPE,
        "readback_required: exact original eighth source history retained")
    require(index.get("task_id") == EN2_OWNER_SUCCESSION_TASK
        and index.get("runtime_source_count") == index.get("current_sha_size_mode_verified_count") == 7
        and index.get("input_pin_checks_count") == 30
        and index.get("all_selected_input_artifact_pins_rechecked_unchanged") is True
        and decision.get("result") == "REWORK_WITH_REAL_ORIGINAL_SOURCE_FACTS_RECOVERED"
        and decision.get("formal_source_QA") is False and decision.get("source_adopted") is False,
        "readback_required: exact real owner predecessor recovery required")
    rows = index.get("sources", [])
    require(isinstance(rows, list) and len(rows) == 7
        and len({row.get("source_path") for row in rows if isinstance(row, dict)}) == 7
        and {row.get("source_path") for row in rows} == {
            "tools/managed_cms_permit_issuer.py", "tools/paid_three_page_bounded_cms.py",
            "tools/goal_delivery_runtime.py", "tools/qa_review_plan.py", "tools/workflow_control.py",
            "tools/result_coordination.py", "tools/goal_continuity.py"},
        "readback_required: only seven named original runtime predecessors")
    versions, modes = [], {}
    for row in rows:
        value = row.get("actual_current", {})
        require(value.get("path") == row["source_path"] and type(value.get("mode")) is int,
            "readback_required: original current source pin/mode missing")
        canonical = _source_successor_shape({key:value[key] for key in ("path","sha256","size")})
        modes[canonical["path"]] = value["mode"]
        versions.append(canonical)
        require(row.get("new_source_QA_or_adoption") is False
            and any(row.get(key) is True for key in (
                "current_sha_size_mode_equal_original_actual_after",
                "current_sha_size_mode_equal_actual_after",
                "current_sha_size_mode_equal_reconstructed_actual_bytes")),
            "readback_required: actual old effect or native byte reconstruction required")
        if row.get("proof_type") in {"existing_historical_source_only_CAS_complete_with_after_actual",
                                     "existing_real_adopted_source_transaction_and_physical_before_backup"}:
            physical = row.get("actual_physical_before_backup")
            journal = row.get("actual_historical_CAS_journal",row.get("actual_historical_journal"))
            require(isinstance(physical,dict) and isinstance(journal,dict)
                and (row.get("actual_historical_CAS_status") == "complete"
                     or row.get("actual_journal_state") == "adopted"),
                "readback_required: actual prior source-only CAS/journal and physical backup")
            pin(root, physical); pin(root, journal)
        else:
            require(row.get("proof_type") in {
                "existing_physical_base_plus_complete_actual_native_patch_chain_reconstructed_in_memory",
                "actual_absence_guard_exclusive_creation_then_existing_CAS_and_complete_native_patch_chain"}
                and isinstance(row.get("actual_native_patch_chain"),list)
                and bool(row["actual_native_patch_chain"]),
                "readback_required: actual owner native patch chain required")
            pin(root,row["actual_physical_base"])
            pin(root,row["Root_independent_byte_reconstruction_check"])
    for item in index.get("input_pin_checks", []):
        require(item.get("sha_size_and_available_mode_match") is True,
            "readback_required: one of 30 actual predecessor evidence pins failed")
        observed = pin(root,item["actual"])
        mode = item["actual"].get("mode")
        require(mode is None or w.safe_path(root, observed["path"]).stat().st_mode & 0o777 == mode,
            "readback_required: original predecessor evidence mode drift")
    require(len(index.get("input_pin_checks", [])) == 30,
        "readback_required: all 30 recovered original evidence pins required")
    import importlib.util
    helper_pin = pin(root, manifest.get("source_review_helper"))
    require(helper_pin == manifest.get("source_successor_helper")
        and helper_pin["path"] == str(Path(manifest_pin["path"]).parent / "rollback/source_review_context.py"),
        "readback_required: one exact adjacent source review helper required")
    spec = importlib.util.spec_from_file_location("_flashcast_exact_en2_current_endpoint", w.safe_path(root, helper_pin["path"]))
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    require(helper.TASK == EN2_OWNER_SUCCESSION_TASK
        and helper.SCOPE == EN2_OWNER_SUCCESSION_SCOPE
        and helper.VERSION == EN2_OWNER_SUCCESSION_VERSION
        and helper.INDEX == EN2_OWNER_RECOVERED_INDEX
        and manifest.get("actual_owner_provenance") == helper.INDEX
        and manifest.get("actual_current_owner_endpoint") == helper.CURRENT_ENDPOINT_A2
        and manifest.get("actual_owner_g70_native_tail") == helper.CURRENT_G70_NATIVE
        and helper.CURRENT_ENDPOINT_A2 in manifest.get("inputs", [])
        and helper.CURRENT_G70_NATIVE in manifest.get("inputs", []),
        "readback_required: one exact later seven-source proof layer required")
    endpoint = helper.current_owner_endpoint(root)
    actual = [_source_successor_shape({key:value[key] for key in ("path", "sha256", "size")})
              for value in endpoint.values()]
    current_modes = {path:value["mode"] for path,value in endpoint.items()}
    require(len(actual) == len(current_modes) == 7
        and endpoint["tools/paid_three_page_bounded_cms.py"]["sha256"]
            == next(row["actual_current"]["sha256"] for row in rows
                    if row["source_path"] == "tools/paid_three_page_bounded_cms.py"),
        "readback_required: current endpoint cannot replace original paid source")
    return actual,current_modes


def _en2_owner_successor_is_exact(root, continuation_pins):
    if not isinstance(continuation_pins,list) or len(continuation_pins) != 1:
        return False
    candidate = _source_successor_doc(root,pin(root,continuation_pins[0]))
    return candidate.get("schema") == SOURCE_SUCCESSION_SCHEMA and all(
        candidate.get(key) == value for key,value in {
            "task_id":EN2_OWNER_SUCCESSION_TASK,"scope":EN2_OWNER_SUCCESSION_SCOPE,
            "candidate_version":EN2_OWNER_SUCCESSION_VERSION}.items())


def _en2_owner_authenticated_source_successions(root, continuation_pins, *, predecessor_sources,
                                                 original_history_pin, current_sources=None):
    """One exact EN2 effect after the recovered real owner endpoint, never a general bridge."""
    require(original_history_pin == EN2_OWNER_ORIGINAL_HISTORY,
        "readback_required: original eighth source history changed")
    original = _source_successor_versions(predecessor_sources)
    continuation_pin = pin(root,continuation_pins[0])
    continuation = _source_successor_doc(root,continuation_pin)
    fields = {"schema","task_id","scope","candidate_version","predecessor_sources",
        "original_history_continuation","candidate_manifest","source_qa","review_plan",
        "producer_outbox","source_adoption","adoption_followthrough_record_id",
        "review_context_helper","field_adoptions","prepared_only",*V5_REVIEW_FLAGS}
    require(set(continuation) == fields and continuation.get("prepared_only") is False
        and all(continuation.get(key) is False for key in V5_REVIEW_FLAGS)
        and continuation.get("original_history_continuation") == EN2_OWNER_ORIGINAL_HISTORY
        and _source_successor_versions(continuation.get("predecessor_sources")) == original,
        "readback_required: exact one-time EN2 continuation and real predecessor required")
    manifest_pin = pin(root,continuation.get("candidate_manifest"))
    manifest = _source_successor_doc(root,manifest_pin)
    actual,modes = _en2_owner_predecessor_boundary(root,manifest_pin,manifest)
    require(original == actual, "readback_required: exact seven-source real owner endpoint required")
    require(manifest.get("schema") == "flashcast-exact-source-candidate/v1"
        and all(manifest.get(key) == continuation.get(key) for key in
                ("task_id","scope","candidate_version"))
        and manifest.get("original_task_id") == "fc-20261011-english-kitchen-exact-en2-registration-source-v1"
        and manifest.get("project_root") == str(root)
        and manifest.get("primary_owner") == "system-development"
        and manifest.get("responsible_assistant") == ROLE
        and manifest.get("candidate_fingerprint") == digest({key:value for key,value in manifest.items()
            if key != "candidate_fingerprint"})
        and manifest.get("source_predecessor_sources") == original
        and manifest.get("actual_owner_provenance") == EN2_OWNER_RECOVERED_INDEX
        and manifest.get("actual_current_owner_endpoint") == manifest.get("source_lineage", {}).get("actual_owner_current_endpoint")
        and manifest.get("actual_owner_g70_native_tail") == manifest.get("source_lineage", {}).get("actual_owner_g70_native_tail")
        and manifest.get("A2_bounded_rework_decision") == EN2_OWNER_RECOVERED_DECISION
        and manifest.get("source_lineage_compatibility_authorization") == EN2_OWNER_HUMAN_AUTH
        and manifest.get("source_lineage",{}).get("original_qualified_history_window_continuation") == EN2_OWNER_ORIGINAL_HISTORY
        and set(manifest.get("source_predecessor_modes",{})) == set(modes)
        and manifest["source_predecessor_modes"] == modes
        and {row.get("path") for row in manifest.get("files",[])} == EN2_OWNER_SOURCE_PATHS
        and len(manifest["files"]) == 2 and manifest.get("field_changes") == []
        and {row.get("path") for row in manifest.get("protected_sources",[])} == set(modes)-EN2_OWNER_SOURCE_PATHS
        and all(value in manifest.get("inputs",[]) for value in (
            EN2_OWNER_RECOVERED_INDEX,EN2_OWNER_RECOVERED_DECISION,EN2_OWNER_HUMAN_AUTH,
            manifest.get("actual_current_owner_endpoint"),manifest.get("actual_owner_g70_native_tail"),
            EN2_OWNER_ORIGINAL_HISTORY,manifest.get("goal_contract"),manifest.get("human_authorization"))),
        "readback_required: exact original EN2 two-source reviewed manifest required")
    require(pin(root,continuation.get("review_context_helper")) == manifest.get("source_review_helper")
        == manifest.get("source_successor_helper")
        and manifest["source_review_helper"] in manifest["inputs"],
        "readback_required: adjacent exact reviewed EN2 source helper required")
    journal_pin = pin(root,continuation.get("source_adoption"))
    journal = _source_successor_doc(root,journal_pin)
    installed,backings = _source_successor_files(root,manifest_pin,manifest,journal_pin,journal,
        original,continuation_pin)
    require(set(installed) == EN2_OWNER_SOURCE_PATHS and journal.get("field_adoptions",[]) == []
        and continuation.get("field_adoptions") == [],
        "readback_required: exactly two source effects and zero field effects")
    preflight = _source_successor_governance(root,continuation,manifest_pin,manifest,journal_pin,journal,
        defer_assignment=True, exact_en2=True)
    endpoint = [installed.get(row["path"],row) for row in original]
    require(all(pin(root,row) == row and w.safe_path(root,row["path"]).stat().st_mode & 0o777
                == modes[row["path"]] for row in endpoint)
        and (current_sources is None or _source_successor_versions(current_sources) == endpoint),
        "readback_required: real complete EN2 after endpoint and protected five source modes")
    committed = _source_successor_governance(root,continuation,manifest_pin,manifest,journal_pin,journal,
        assignment_backings=backings,assignment_fields=[], exact_en2=True)
    require(committed == preflight and all(pin(root,row["backup"]) == row["backup"] for row in backings)
        and all(pin(root,row) == row for row in endpoint),
        "readback_required: EN2 independent QA, original owner backups and after bytes changed")
    return {"original_history_pin":EN2_OWNER_ORIGINAL_HISTORY,
        "continuation_pins":[continuation_pin],"predecessor_sources":original,
        "endpoint":endpoint,"layers":[{"continuation_pin":continuation_pin,
            "task_id":EN2_OWNER_SUCCESSION_TASK,"scope":EN2_OWNER_SUCCESSION_SCOPE,
            "candidate_version":EN2_OWNER_SUCCESSION_VERSION,"manifest_pin":manifest_pin,
            "journal_pin":journal_pin,"predecessor_sources":original,"installed":installed,
            "backups":backings,**committed}],"source_backings":backings,"field_effects":[]}


@strict
def authenticated_source_successions(root, continuation_pins, *, predecessor_sources, original_history_pin, current_sources=None):
    # This context gives original normal readers their authenticated old binding;
    # it does not declare the input CP authenticated. Every prior/full guard is
    # still executed by the unchanged body before a result can escape.
    root=Path(root).resolve()
    require(isinstance(continuation_pins,list) and continuation_pins,'readback_required: exact actual continuations required')
    if _en2_owner_successor_is_exact(root,continuation_pins):
        return _en2_owner_authenticated_source_successions(root,continuation_pins,
            predecessor_sources=predecessor_sources,original_history_pin=original_history_pin,
            current_sources=current_sources)
    with _source_bootstrap_prior_history_context(root,continuation_pins):
        return _authenticated_source_successions(root,continuation_pins,predecessor_sources=predecessor_sources,
            original_history_pin=original_history_pin,current_sources=current_sources)


@strict
def _source_bootstrap_historical_control(root,frozen,pending):
    """Only after every actual layer preflight, read one proven health archive."""
    import importlib.util
    selected=[(mp,manifest) for continuation,mp,manifest,jp,journal,governance in pending
        if continuation.get('schema')==SOURCE_BOOTSTRAP_SUCCESSION_SCHEMA]
    require(len(selected)==1,'readback_required: exact actual bootstrap layer required for historical control')
    mp,manifest=selected[0];helper_pin=pin(root,manifest.get('source_review_helper'))
    require(helper_pin==manifest.get('source_successor_helper') and helper_pin in manifest.get('inputs',[])
        and helper_pin['path']==str(Path(mp['path']).parent/'rollback/source_review_context.py'),
        'readback_required: exact independently reviewed historical-control helper')
    spec=importlib.util.spec_from_file_location('_flashcast_actual_bootstrap_control',w.safe_path(root,helper_pin['path']))
    helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
    require(helper.VERSION=='goal-publication-notice-followthrough-source-candidate-v29-20261013',
        'readback_required: exact health-only source lifecycle version')
    return pin(root,helper.bootstrap_control_history(root,manifest,frozen))


def _authenticated_source_successions(root, continuation_pins, *, predecessor_sources, original_history_pin, current_sources=None):
    """Authenticate only already adopted source successors; never send, QA or CAS.

    Physical backups and each predecessor/after are different identities. No
    caller-supplied dictionary, future candidate or old same-body report grants
    a source effect. The complete original eight are read by the history context.
    """
    root = Path(root).resolve()
    predecessor_sources = _source_successor_versions(predecessor_sources)
    original_history_pin = pin(root, original_history_pin)
    original = _source_successor_doc(root, original_history_pin)
    require(original.get("schema") == "actual_qualified_history_window_source_continuation/v1"
        and original.get("task_id") == QUALIFIED_NATIVE_HANDOFF_TASK
        and original.get("scope") == QUALIFIED_NATIVE_HANDOFF_SCOPE
        and original.get("candidate_version") == QUALIFIED_HISTORY_WINDOW_VERSION
        and original.get("prepared_only") is False and all(original.get(key) is False for key in V5_REVIEW_FLAGS),
        "readback_required: immutable actual original eighth continuation required")
    old_manifest = _source_successor_doc(root, original.get("candidate_manifest"))
    require(old_manifest.get("schema") == "flashcast-exact-source-candidate/v1"
        and old_manifest.get("task_id") == QUALIFIED_NATIVE_HANDOFF_TASK
        and old_manifest.get("scope") == QUALIFIED_NATIVE_HANDOFF_SCOPE
        and old_manifest.get("candidate_version") == QUALIFIED_HISTORY_WINDOW_VERSION
        and old_manifest.get("candidate_fingerprint") == digest({key:value for key,value in old_manifest.items() if key != "candidate_fingerprint"})
        and {row.get("path") for row in old_manifest.get("files", [])} == QUALIFIED_RULE_HISTORY_PATHS,
        "exact immutable original eighth reviewed manifest identity required")
    original_endpoint = {value["path"]:_source_successor_shape(value) for value in old_manifest.get("protected_sources", [])}
    original_endpoint.update({row["path"]:_source_successor_shape({"path":row["path"], **row["after"]})
        for row in old_manifest.get("files", [])})
    require({value["path"]:value for value in predecessor_sources} == original_endpoint,
        "readback_required: first successor must start at complete real V7 installed/protected boundary")
    require(isinstance(continuation_pins, list) and continuation_pins,
        "readback_required: no actual source successor has been recorded")
    continuation_pins = [pin(root,value) for value in continuation_pins]
    require(len({value["path"] for value in continuation_pins}) == len(continuation_pins),
        "unique ordered actual source successors required")
    fields = {"schema","task_id","scope","candidate_version","predecessor_sources","original_history_continuation",
        "candidate_manifest","source_qa","review_plan","producer_outbox","source_adoption",
        "adoption_followthrough_record_id","review_context_helper","field_adoptions","prepared_only",*V5_REVIEW_FLAGS}
    endpoint = {value["path"]:value for value in predecessor_sources}
    layers, backings, field_effects, closures, pending = [], [], [], [], []
    actual_modes = {}
    for index, continuation_pin in enumerate(continuation_pins):
        continuation = _source_successor_doc(root, continuation_pin)
        bootstrap = continuation.get("schema") == SOURCE_BOOTSTRAP_SUCCESSION_SCHEMA
        exact_fields = (fields - {"review_plan"}) | {"bootstrap_review_contract","predecessor_continuations","coordination_epoch_sources","registry_health_registration_sources"} if bootstrap else fields
        require(set(continuation) == exact_fields and continuation.get("schema") in {SOURCE_SUCCESSION_SCHEMA,SOURCE_BOOTSTRAP_SUCCESSION_SCHEMA}
            and continuation.get("prepared_only") is False and all(continuation.get(key) is False for key in V5_REVIEW_FLAGS)
            and continuation.get("original_history_continuation") == original_history_pin,
            "readback_required: exact actual source successor descriptor required")
        if bootstrap:
            require(index > 0 and continuation.get("predecessor_continuations") == continuation_pins[:index],
                "readback_required: exact already-authenticated predecessor prefix for bootstrap")
        manifest_pin = pin(root, continuation.get("candidate_manifest")); manifest = _source_successor_doc(root, manifest_pin)
        before = _source_successor_versions(continuation.get("predecessor_sources"))
        before_map = {value["path"]:value for value in before}
        require(manifest.get("schema") == "flashcast-exact-source-candidate/v1"
            and all(manifest.get(key) == continuation.get(key) for key in ("task_id","scope","candidate_version"))
            and manifest.get("project_root") == str(root) and manifest.get("primary_owner") == "system-development"
            and manifest.get("responsible_assistant") == ROLE
            and manifest.get("candidate_fingerprint") == digest({key:value for key,value in manifest.items() if key != "candidate_fingerprint"})
            and all(manifest.get(key) is False for key in V5_REVIEW_FLAGS)
            and manifest.get("source_predecessor_sources") == before
            and manifest.get("source_lineage", {}).get("original_qualified_history_window_continuation") == original_history_pin
            and all(before_map.get(path) == value for path,value in endpoint.items())
            and set(before_map) - set(endpoint) <= {row.get("path") for row in manifest.get("files", [])},
            "readback_required: true immediate predecessor, exact reviewed MP and immutable original history required")
        if index == 0:
            require(continuation.get("task_id") == QUALIFIED_NATIVE_HANDOFF_TASK
                and continuation.get("scope") == QUALIFIED_NATIVE_HANDOFF_SCOPE
                and continuation.get("candidate_version") == SOURCE_SUCCESSION_VERSION
                and {row.get("path") for row in manifest.get("files", [])} == QUALIFIED_RULE_HISTORY_PATHS
                and before == predecessor_sources,
                "first actual successor must be this independently adopted new TH q/b identity")
        helper_pin = pin(root, continuation.get("review_context_helper"))
        require(helper_pin["path"] == str(Path(manifest_pin["path"]).parent / "rollback/source_review_context.py")
            and helper_pin in manifest.get("inputs", [])
            and manifest.get("source_successor_helper") == helper_pin,
            "one exact independently reviewed adjacent source successor helper required")
        journal_pin = pin(root, continuation.get("source_adoption")); journal = _source_successor_doc(root, journal_pin)
        installed, layer_backings = _source_successor_files(root,manifest_pin,manifest,journal_pin,journal,before,continuation_pin)
        for row in manifest["files"]:
            require(row["path"] not in actual_modes or actual_modes[row["path"]] == row["before_mode"],
                "readback_required: immediate predecessor source mode differs from prior real after")
            actual_modes[row["path"]] = row["after_mode"]
        governance = _source_successor_governance(root,continuation,manifest_pin,manifest,journal_pin,journal,
            defer_assignment=True)
        require(not layers or layers[-1]["released_at"] <= governance["started_at"],
            "readback_required: each successor must follow the predecessor's permanent effect release")
        effects = _source_successor_field_effects(root,continuation,manifest_pin,manifest,journal)
        require(all(pin(root,value) == value for value in
            (manifest.get("goal_contract"),manifest.get("human_authorization"))), "unchanged original immutable authority pins required")
        inputs, protected = manifest.get("inputs"), manifest.get("protected_sources")
        require(isinstance(inputs,list) and inputs and isinstance(protected,list)
            and len({value.get("path") for value in inputs}) == len(inputs)
            and len({value.get("path") for value in protected}) == len(protected)
            and all(value in inputs for value in (manifest["goal_contract"],manifest["human_authorization"],helper_pin))
            and original_history_pin in inputs,
            "complete unique actual source input closure required")
        require(all(value in inputs and before_map.get(value.get("path")) == value
            and value.get("path") not in installed for value in protected),
            "unchanged exact protected source predecessor must remain closed")
        closures.append(inputs)
        endpoint = dict(before_map); endpoint.update(installed)
        backings.extend(layer_backings); field_effects.extend(effects)
        layers.append({"continuation_pin":continuation_pin,"task_id":manifest["task_id"],"scope":manifest["scope"],
            "candidate_version":manifest["candidate_version"],"manifest_pin":manifest_pin,"journal_pin":journal_pin,
            "helper_pin":helper_pin,"predecessor_sources":before,"installed":installed,"backups":layer_backings, **governance})
        pending.append((continuation, manifest_pin, manifest, journal_pin, journal, governance))
    # A later *authenticated* journal may hold an earlier protected version.
    # Wait until every actual layer passes before authorizing any such mapping.
    for inputs in closures:
        for frozen in inputs:
            _source_successor_shape(frozen)
            if frozen["path"] == "data/task-contract.json":
                snapshots = [effect[key] for effect in field_effects for key in ("before_backup","after_readback")
                    if all(effect[key][part] == frozen[part] for part in ("sha256","size"))]
                if snapshots:
                    require(all(pin(root,value) == value for value in snapshots),
                        "exact physical field snapshot required for historical config input closure")
                    continue
            mapped = [value for value in backings if value["logical"] == frozen]
            if mapped:
                require(all(pin(root,value["backup"]) == value["backup"]
                    and w.safe_path(root,value["backup"]["path"]).stat().st_mode & 0o777 == value["mode"] for value in mapped),
                    "authenticated original backup byte/mode boundary changed")
            else:
                if frozen['path']=='data/department-registry.json':
                    _source_bootstrap_historical_control(root,frozen,pending)
                else:pin(root,frozen)
    actual_endpoint = [pin(root,value) for value in endpoint.values()]
    require(all(w.safe_path(root,path).stat().st_mode & 0o777 == mode for path,mode in actual_modes.items()),
        "readback_required: current source modes must equal the last real adopted effects")
    if current_sources is not None:
        observed = [pin(root,value) for value in _source_successor_versions(current_sources)]
        require({value["path"]:value for value in actual_endpoint} == {value["path"]:value for value in observed},
            "readback_required: final complete source endpoint differs from real installed bytes")
    latest_fields = {(value["source"],value["field"]):value for value in field_effects}
    for (source,field), effect in latest_fields.items():
        require(w.read_json(w.safe_path(root,source)).get(field) == effect["replacement"],
            "readback_required: current field must equal its last actual adopted effect")
    # Physical effects, native QA/completion, actual bindings, committed fences,
    # releases, full input closures and current endpoints have all been checked.
    # Complete the still-mandatory original responsibility guards using only
    # those exact source backups. No authenticated result escapes before this.
    for continuation, manifest_pin, manifest, journal_pin, journal, observed in pending:
        require(_source_successor_governance(root,continuation,manifest_pin,manifest,journal_pin,journal,
            assignment_backings=backings, assignment_fields=field_effects) == observed,
            "actual source governance changed while interpreting original responsibility")
    require(all(pin(root,value) == value for value in actual_endpoint)
        and all(w.safe_path(root,path).stat().st_mode & 0o777 == mode for path,mode in actual_modes.items()),
        "readback_required: current source endpoint changed during original responsibility read")
    require(all(pin(root,row["backup"]) == row["backup"]
        and w.safe_path(root,row["backup"]["path"]).stat().st_mode & 0o777 == row["mode"] for row in backings),
        "readback_required: exact physical backups changed during original responsibility read")
    require(all(w.read_json(w.safe_path(root,source)).get(field) == effect["replacement"]
        for (source,field),effect in latest_fields.items()),
        "readback_required: current field changed during original responsibility read")
    require(all(all(pin(root,effect[key]) == effect[key] for key in
        ("candidate_pin","journal_pin","before_backup","after_readback")) for effect in field_effects),
        "readback_required: any layer's exact field evidence changed during original responsibility read")
    return {"original_history_pin":original_history_pin,"continuation_pins":continuation_pins,
        "predecessor_sources":predecessor_sources,"endpoint":actual_endpoint,
        "layers":layers,"source_backings":backings,"field_effects":field_effects}


def _qualified_source_successions_current_lineage(root, proof, accepted, old_manifest_pin, historical):
    """Read old eight only after real current succession, using authenticated backups."""
    import importlib.util
    pins = proof.get("consumer_authenticated_source_successions")
    require(isinstance(pins,list) and pins, "readback_required: current source succession effects missing")
    first = _source_successor_doc(root,pins[0])
    require(first.get("original_history_continuation") == proof.get("consumer_qualified_history_window_continuation"),
        "original eighth identity must remain in the public proof")
    authenticated = authenticated_source_successions(root,pins,predecessor_sources=first.get("predecessor_sources"),
        original_history_pin=proof.get("consumer_qualified_history_window_continuation"))
    current = [pin(root,value) for value in proof.get("current_consumer_sources", [])]
    endpoint = {value["path"]:value for value in authenticated["endpoint"]}
    require([value["path"] for value in current] == list(SOURCES)
        and current == [pin(root,value) for value in accepted.get("consumer_sources", [])]
        and all(endpoint.get(value["path"]) == value for value in current),
        "exact new g/w and complete current five-consumer acceptance required")
    helper_pin = authenticated["layers"][0]["helper_pin"]
    spec = importlib.util.spec_from_file_location("_flashcast_authenticated_source_history_v9",w.safe_path(root,helper_pin["path"]))
    helper = importlib.util.module_from_spec(spec); spec.loader.exec_module(helper)
    require(helper.TASK == QUALIFIED_NATIVE_HANDOFF_TASK and helper.SCOPE == QUALIFIED_NATIVE_HANDOFF_SCOPE
        and helper.VERSION == SOURCE_SUCCESSION_VERSION and helper.ROLE == ROLE
        and helper.PRODUCER == "system-development" and helper.SOURCE_PATHS == QUALIFIED_RULE_HISTORY_PATHS,
        "independently reviewed new TH helper identity required")
    with helper.authenticated_history_context(root,authenticated) as context:
        predecessor = [value for value in authenticated["predecessor_sources"] if value["path"] in SOURCES]
        predecessor = [next(value for value in predecessor if value["path"] == path) for path in SOURCES]
        require(context.get("original_endpoint") == predecessor and isinstance(context.get("modules"),dict),
            "authenticated original eighth endpoint and fresh historical namespace required")
        reader = context["modules"].get("paid_three_page_bounded_cms")
        require(reader is not None and reader._qualified_history_window_current_lineage is not _qualified_history_window_current_lineage,
            "a fresh exact historical reader is required")
        before_proof = dict(proof); before_proof.pop("consumer_authenticated_source_successions")
        before_proof["current_consumer_sources"] = predecessor
        before_accepted = dict(accepted); before_accepted["consumer_sources"] = predecessor
        require(reader._qualified_history_window_current_lineage(root,before_proof,before_accepted,old_manifest_pin,historical) == predecessor,
            "the entire original eight actual history layers must return normally")
    require(authenticated_source_successions(root,pins,predecessor_sources=first["predecessor_sources"],
        original_history_pin=authenticated["original_history_pin"]) == authenticated
        and current == [pin(root,value) for value in proof["current_consumer_sources"]],
        "real current source effects and before/backup bindings must remain unchanged")
    return current


def read_qualified_history_candidate(root, manifest_pin):
    """Read the complete actual seven layers; this never claims candidate adoption."""
    import copy
    helper = _history_window_helper(root, manifest_pin)
    root, manifest, _, _ = helper.validate_package(root, manifest_pin, require_before=True)
    require(Path(__file__).resolve() == w.safe_path(root, next(row["candidate"]["path"] for row in manifest["files"]
        if row["path"] == "tools/paid_three_page_bounded_cms.py")),
        "candidate-only reader must execute the exact frozen candidate source")
    contract = helper.doc(root, manifest["history_window_contract"])
    original = doc(root, contract["original_complete_full5_input"])
    proof = copy.deepcopy(original)
    proof["consumer_qualified_native_handoff_continuation"] = contract["original_actual_sixth_source"]
    proof["consumer_qualified_rule_history_continuation"] = contract["original_actual_seventh_source"]
    with helper.candidate_history_context(root, manifest_pin) as context:
        proof["current_consumer_sources"] = context["predecessor_endpoint"]
        require(all(proof[key] == value for key,value in original.items() if key != "current_consumer_sources"),
            "all original five-layer fields must remain intact")
        reader = context["modules"]["paid_three_page_bounded_cms"]
        result = reader._v5_source_adoption(root, proof, {"consumer_sources":proof["current_consumer_sources"]})
        require(result is None, "the complete original history reader must return normally")
    return {"candidate_version":QUALIFIED_HISTORY_WINDOW_VERSION, "complete_original_seven_layers_read":True,
        "actual_candidate_adoption":False, "source_writes":0, "ledger_writes":0,
        "parent_goal_closed":False}




SOURCE_REPAIR_TASK = "fc-20261011-acceptance-message-and-historical-adoption-boundary-repair-v1"
SOURCE_REPAIR_SCOPE = "project:flashcast:acceptance-message-and-historical-adoption-boundary-repair:v1"
SOURCE_REPAIR_VERSION = "acceptance-message-historical-adoption-boundary-candidate-v1-20261011"
SOURCE_REPAIR_PATHS = {"tools/qa_review_plan.py", "tools/scoped_candidate_adoption.py", "tools/parent_initial_dispatch.py",
                       "tools/technical_review_backup.py", "tools/paid_three_page_bounded_cms.py"}
SOURCE_REPAIR_CONTEXT_BYTES = {"sha256":"f0222bf7912165fa7702efacc4b9dfc8057242b335bf3b250cecea388e5ddcb0", "size":18180}


def _source_repair_successor(root, continuation_pin, native_continuation_pin, old_manifest_pin, original_installed, weekly_continuation_pin=None, repair_continuation_pin=None, functional_continuation_pin=None):
    """Exact second-level permanent source provenance; never a lease or permission.

    Called only after the full original V6 review/CAS/committed chain passes.
    Its overlapping before bytes must equal that verified V6 installed effect.
    """
    import importlib.util
    import result_coordination as c
    from scoped_candidate_adoption import _committed
    role = "operations-assistant-3"
    continuation = doc(root, continuation_pin)
    fields = {"schema", "task_id", "scope", "candidate_version", "historical_V5_manifest",
              "original_native_control_continuation", "candidate_manifest", "source_qa", "review_plan",
              "producer_outbox", "source_adoption", "adoption_followthrough_record_id", "review_context_helper",
              "prepared_only", *V5_REVIEW_FLAGS}
    require(set(continuation) == fields and continuation.get("schema") == "actual_acceptance_message_historical_adoption_source_continuation/v1"
            and continuation.get("task_id") == SOURCE_REPAIR_TASK and continuation.get("scope") == SOURCE_REPAIR_SCOPE
            and continuation.get("candidate_version") == SOURCE_REPAIR_VERSION
            and continuation.get("historical_V5_manifest") == old_manifest_pin
            and continuation.get("original_native_control_continuation") == native_continuation_pin
            and continuation.get("prepared_only") is False and all(continuation.get(key) is False for key in V5_REVIEW_FLAGS),
            "one exact accepted five-source successor with original V5/V6 links required")
    manifest_pin = pin(root, continuation.get("candidate_manifest")); manifest = doc(root, manifest_pin)
    helper_pin = pin(root, continuation.get("review_context_helper"))
    require(helper_pin["path"] == str(Path(manifest_pin["path"]).parent / "rollback/source_review_context.py")
            and helper_pin in manifest.get("inputs", [])
            and {key:helper_pin[key] for key in ("sha256", "size")} == SOURCE_REPAIR_CONTEXT_BYTES
            and manifest.get("source_lineage", {}).get("historical_V5_manifest") == old_manifest_pin
            and manifest.get("source_lineage", {}).get("native_control_continuation") == native_continuation_pin
            and len(manifest.get("files", [])) == len(SOURCE_REPAIR_PATHS)
            and {row.get("path") for row in manifest["files"]} == SOURCE_REPAIR_PATHS,
            "exact frozen reviewed helper and five-target original lineage required")
    journal_pin = pin(root, continuation.get("source_adoption")); journal = doc(root, journal_pin)
    handoffs = w._result_handoff_rows(root, SOURCE_REPAIR_TASK)
    decisions = [row for row in handoffs if row.get("record_id") == journal.get("decision_record_id")]
    require(len(decisions) == 1, "one committed new repair adoption decision required")
    decision = decisions[0]
    review_pin = pin(root, continuation.get("source_qa")); box = doc(root, review_pin)
    review = box.get("candidate_review", {}); producer_pin = pin(root, continuation.get("producer_outbox"))
    require(manifest.get("schema") == "flashcast-exact-source-candidate/v1"
            and manifest.get("task_id") == SOURCE_REPAIR_TASK and manifest.get("scope") == SOURCE_REPAIR_SCOPE
            and manifest.get("candidate_version") == SOURCE_REPAIR_VERSION
            and manifest.get("primary_owner") == "system-development" and manifest.get("responsible_assistant") == role
            and manifest.get("candidate_fingerprint") == digest({key:value for key,value in manifest.items() if key != "candidate_fingerprint"})
            and box.get("department") == role and box.get("task_id") == SOURCE_REPAIR_TASK
            and box.get("candidate_version") == SOURCE_REPAIR_VERSION and box.get("scope") == SOURCE_REPAIR_SCOPE
            and box.get("status") == "partial" and box.get("prepared_only", False) is False
            and not box.get("goal_acceptance") and box.get("qa_verdict") != "pass"
            and review.get("actor") == role and review.get("verdict") == "PASS_SOURCE_CANDIDATE_ONLY"
            and review.get("phase") == "candidate_source_only" and review.get("direction") == "forward"
            and review.get("candidate_manifest") == manifest_pin and review.get("candidate_fingerprint") == manifest["candidate_fingerprint"]
            and review.get("producer_outbox") == producer_pin and review.get("review_plan") == continuation.get("review_plan")
            and review.get("goal_contract") == manifest.get("goal_contract") and review.get("human_authorization") == manifest.get("human_authorization")
            and all(manifest.get(key) is False and box.get(key) is False and review.get(key) is False for key in V5_REVIEW_FLAGS),
            "independently accepted exact source manifest required before executing its frozen helper")
    w.validate_outbox(root, [review_pin], role, SOURCE_REPAIR_TASK)
    _native(root, box, [SOURCE_REPAIR_TASK, SOURCE_REPAIR_VERSION, manifest["candidate_fingerprint"],
                       producer_pin["sha256"], manifest_pin["sha256"], "PASS_SOURCE_CANDIDATE_ONLY"], role)
    require(decision.get("event") == "controller_decision" and decision.get("decision") == "continue"
            and decision.get("task_id") == SOURCE_REPAIR_TASK and decision.get("candidate_version") == SOURCE_REPAIR_VERSION
            and decision.get("outbox") == producer_pin and review_pin in decision.get("evidence", [])
            and decision.get("coordinator_role") == decision.get("decision_actor") == decision.get("responsible_assistant") == role
            and decision.get("next_owner") == role and decision.get("next_action") == "adopt-" + SOURCE_REPAIR_VERSION
            and decision.get("business_goal_closed") is False and decision.get("qa_status") != "pass",
            "actual independent source-only adoption decision must bind the accepted helper manifest")
    _committed(root, decision); _v5_source_decision_fence(root, decision, role)
    source = {key: continuation[key] for key in ("task_id", "scope", "candidate_version", "candidate_manifest",
                                               "source_qa", "review_plan", "producer_outbox", "prepared_only", *V5_REVIEW_FLAGS)}
    source["schema"] = "flashcast-actual-source-review-input/v1"
    if weekly_continuation_pin is None:
        spec = importlib.util.spec_from_file_location("_flashcast_permanent_source_repair_context", w.safe_path(root, helper_pin["path"]))
        helper = importlib.util.module_from_spec(spec); spec.loader.exec_module(helper)
        require(helper.SOURCE_PATHS == SOURCE_REPAIR_PATHS, "reviewed helper must retain exactly five source targets")
        # A preview may already have the weekly n/w modules loaded. The exact
        # unchanged predecessor helper reads its own real reviewed dependency
        # files; isolate those module objects and restore the caller afterward.
        import sys
        previous_modules = {name: sys.modules.get(name) for name in helper.DEPENDENCIES}
        try:
            for name in helper.DEPENDENCIES:
                sys.modules.pop(name, None)
            manifest, reviewed, actual_decision, identity = helper.review_context(root, manifest_pin, source,
                decision["record_id"], role, decision.get("coordinator_owner"))
        finally:
            for name, previous in previous_modules.items():
                sys.modules.pop(name, None)
                if previous is not None:
                    sys.modules[name] = previous
        weekly_manifest = None
    else:
        _weekly_source_successor(root, weekly_continuation_pin, native_continuation_pin, old_manifest_pin, continuation_pin, repair_continuation_pin, functional_continuation_pin)
        weekly = doc(root, weekly_continuation_pin)
        weekly_helper_pin = pin(root, weekly["review_context_helper"])
        require({key: weekly_helper_pin[key] for key in ("sha256", "size")} == WEEKLY_SOURCE_CONTEXT_BYTES,
                "only independently reviewed exact weekly helper may read historical boundary")
        helper = _weekly_key_context(root) if functional_continuation_pin is None else _weekly_functional_context(root, functional_continuation_pin)
        args = (root, manifest_pin, source, decision["record_id"], role, decision.get("coordinator_owner"), weekly_continuation_pin, repair_continuation_pin)
        manifest, reviewed, actual_decision, identity = helper.historical_review_context(*args) if functional_continuation_pin is None else helper.historical_review_context(*args, functional_continuation_pin)
        weekly_manifest = doc(root, weekly["candidate_manifest"])
    repair_manifest = None
    if repair_continuation_pin is not None:
        repair = doc(root, repair_continuation_pin)
        repair_manifest = doc(root, repair["candidate_manifest"])
    require(actual_decision == decision and identity == {"task_id":SOURCE_REPAIR_TASK,"sender_department":"system-development",
            "candidate_version":SOURCE_REPAIR_VERSION,"result_sha256":reviewed["producer_pin"]["sha256"]},
            "exact actual new repair producer and independent decision identity required")
    operations = journal.get("source_operations", [])
    require(journal.get("task_id") == SOURCE_REPAIR_TASK and journal.get("candidate_version") == SOURCE_REPAIR_VERSION
            and journal.get("candidate_fingerprint") == manifest["candidate_fingerprint"] and journal.get("candidate_manifest") == manifest_pin
            and journal.get("review_outbox") == reviewed["review_pin"] and journal.get("authorized_source") == reviewed["authority_pin"]
            and journal.get("actor") == role and journal.get("direction") == "forward" and journal.get("status") == "complete"
            and type(journal.get("external_writes")) is int and journal["external_writes"] == 0
            and journal.get("effect_uncertain") is False and journal.get("permissions_issued") is False
            and isinstance(journal.get("execution_id"), str) and bool(journal["execution_id"].strip())
            and len(operations) == len(SOURCE_REPAIR_PATHS) and {row.get("path") for row in operations} == SOURCE_REPAIR_PATHS
            and len(journal.get("applied", [])) == len(SOURCE_REPAIR_PATHS) and set(journal["applied"]) == SOURCE_REPAIR_PATHS,
            "actual complete independent five-target repair CAS journal required")
    installed = {}
    for row in manifest["files"]:
        path = row["path"]
        require(row.get("before") != {"exists":False}
                and (path not in original_installed or row["before"] == {key:original_installed[path][key] for key in ("sha256", "size")}),
                "new repair before must preserve exact verified original V6 overlap")
        operation = next(value for value in operations if value["path"] == path)
        backup = pin(root, operation.get("backup")); candidate = pin(root, row.get("candidate")); baseline = pin(root, row.get("baseline"))
        require(operation.get("before") == row["before"] == {key:baseline[key] for key in ("sha256", "size")}
                == {key:backup[key] for key in ("sha256", "size")}
                and operation.get("after_expected") == operation.get("after_actual") == row["after"]
                == {key:candidate[key] for key in ("sha256", "size")}
                and operation.get("write_attempted") is True and operation.get("verified_after") is True
                and backup["path"].startswith(f"backups/{SOURCE_REPAIR_TASK}/{manifest['candidate_fingerprint']}/forward/")
                and type(operation.get("before_mode")) is int and operation["before_mode"] == row.get("before_mode")
                and w.safe_path(root, backup["path"]).stat().st_mode & 0o777 == operation["before_mode"]
                and w.safe_path(root, baseline["path"]).stat().st_mode & 0o777 == row["before_mode"]
                and (weekly_manifest is not None and path in WEEKLY_SOURCE_PATHS
                     or w.safe_path(root, path).stat().st_mode & 0o777 == row.get("after_mode")),
                "exact new repair original backup, before/write/readback effects and installed modes required")
        if weekly_manifest is not None and path in WEEKLY_SOURCE_PATHS:
            overlapping = [value for value in weekly_manifest["files"] if value["path"] == path]
            require(len(overlapping) == 1 and overlapping[0]["before"] == row["after"]
                    and overlapping[0]["before_mode"] == row["after_mode"],
                    "weekly source must begin at exact verified boundary installed bytes and mode")
            installed[path] = {"path": path, **row["after"]}
        elif repair_manifest is not None and path in WEEKLY_KEY_REPAIR_PATHS:
            overlapping = [value for value in repair_manifest["files"] if value["path"] == path]
            require(len(overlapping) == 1 and overlapping[0]["before"] == row["after"]
                    and overlapping[0]["before_mode"] == row["after_mode"],
                    "current repair must begin at exact independently adopted boundary bytes/mode")
            installed[path] = {"path": path, **row["after"]}
        else:
            installed[path] = pin(root, {"path":path, **row["after"]})
    follows = [row for row in handoffs if row.get("record_id") == continuation.get("adoption_followthrough_record_id")]
    require(len(follows) == 1, "unique actual new repair adopted-effects followthrough required")
    follow = follows[0]
    require(follow.get("event") == "controller_followthrough" and follow.get("followthrough_status") == "blocked_with_owner"
            and c.exact_identity(follow) == identity and follow.get("outbox") == reviewed["producer_pin"]
            and follow.get("coordinator_role") == follow.get("decision_actor") == follow.get("responsible_assistant") == role
            and follow.get("coordinator_owner") == decision.get("coordinator_owner")
            and follow.get("coordination_fence") == decision.get("coordination_fence") and follow.get("business_goal_closed") is False
            and follow.get("unblock_condition") == "source-adopted:" + journal["execution_id"] + ";remaining:original-T3-acceptance-and-historical-readback"
            and journal_pin in follow.get("evidence", []) and handoffs.index(decision) < handoffs.index(follow),
            "exact new repair committed installed-source readback and original consumer boundaries required")
    _committed(root, follow); audit = _v5_source_decision_fence(root, follow, role)
    if functional_continuation_pin is not None:
        _source_release_readback(root, follow, audit)
    box = doc(root, reviewed["review_pin"])
    moments = [w._parse_observed_at(value) for value in (box.get("created_at"), journal.get("started_at"), journal.get("completed_at"))]
    require(all(value is not None for value in moments) and moments == sorted(moments)
            and moments[-1] <= dt.datetime.now(dt.timezone.utc)
            and moments[-1].timestamp() <= audit["reserved_at"] <= audit["committed_at"],
            "ordered independent new repair review, CAS and permanent committed followthrough required")
    return installed



WEEKLY_SOURCE_TASK = "fc-20261011-weekly-native-structured-create-response-compatibility-v1"
WEEKLY_SOURCE_SCOPE = "project:flashcast:weekly-native-structured-create-response-compatibility:v1"
WEEKLY_SOURCE_VERSION = "weekly-native-structured-create-response-compatibility-candidate-v2-20261011"
WEEKLY_SOURCE_PATHS = {"tools/native_control_result.py", "tools/technical_review_backup.py", "tools/workflow_control.py",
                       "tools/paid_three_page_bounded_cms.py",
                       "logs/handoffs/2026-10-10-weekly-safe-cleanup-native-enablement-v1/actual-native-configuration-v1/make_actual_weekly_native_evidence.py"}
WEEKLY_SOURCE_CONTEXT_BYTES = {"sha256": "551ac6a5a98df3db9cf0c4c5b13975537a2501959761016d67257921fc0adae7", "size": 55030}

def _weekly_source_successor(root, continuation_pin, native_continuation_pin, old_manifest_pin, source_repair_continuation_pin, repair_continuation_pin=None, functional_continuation_pin=None):
    """Exact third-level permanent source provenance; never a lease or permission.

    Called only after the original manifests are frozen. The caller still validates each preceding
    review/CAS/committed chain; this authenticates only the new exact effect.
    Its overlapping before bytes must equal that verified V6 installed effect.
    """
    import importlib.util
    import result_coordination as c
    from scoped_candidate_adoption import _committed
    role = "operations-assistant-2"
    continuation = doc(root, continuation_pin)
    fields = {"schema", "task_id", "scope", "candidate_version", "historical_V5_manifest",
              "original_native_control_continuation", "original_source_repair_continuation", "candidate_manifest", "source_qa", "review_plan",
              "producer_outbox", "source_adoption", "adoption_followthrough_record_id", "review_context_helper",
              "prepared_only", *V5_REVIEW_FLAGS}
    require(set(continuation) == fields and continuation.get("schema") == "actual_weekly_native_source_compatibility_continuation/v1"
            and continuation.get("task_id") == WEEKLY_SOURCE_TASK and continuation.get("scope") == WEEKLY_SOURCE_SCOPE
            and continuation.get("candidate_version") == WEEKLY_SOURCE_VERSION
            and continuation.get("historical_V5_manifest") == old_manifest_pin
            and continuation.get("original_native_control_continuation") == native_continuation_pin
            and continuation.get("original_source_repair_continuation") == source_repair_continuation_pin
            and continuation.get("prepared_only") is False and all(continuation.get(key) is False for key in V5_REVIEW_FLAGS),
            "one exact accepted five-source successor with original V5/V6 links required")
    manifest_pin = pin(root, continuation.get("candidate_manifest")); manifest = doc(root, manifest_pin)
    helper_pin = pin(root, continuation.get("review_context_helper"))
    require(helper_pin["path"] == str(Path(manifest_pin["path"]).parent / "rollback/source_review_context.py")
            and helper_pin in manifest.get("inputs", [])
            and {key:helper_pin[key] for key in ("sha256", "size")} == WEEKLY_SOURCE_CONTEXT_BYTES
            and manifest.get("source_lineage", {}).get("historical_V5_manifest") == old_manifest_pin
            and manifest.get("source_lineage", {}).get("original_native_control_continuation") == native_continuation_pin
            and manifest.get("source_lineage", {}).get("original_source_repair_continuation") == source_repair_continuation_pin
            and len(manifest.get("files", [])) == len(WEEKLY_SOURCE_PATHS)
            and {row.get("path") for row in manifest["files"]} == WEEKLY_SOURCE_PATHS,
            "exact frozen reviewed helper and five-target original lineage required")
    journal_pin = pin(root, continuation.get("source_adoption")); journal = doc(root, journal_pin)
    require(journal_pin["path"] == f"backups/{WEEKLY_SOURCE_TASK}/{manifest['candidate_fingerprint']}/forward/journal.json",
            "canonical reviewed weekly forward journal required")
    handoffs = w._result_handoff_rows(root, WEEKLY_SOURCE_TASK)
    decisions = [row for row in handoffs if row.get("record_id") == journal.get("decision_record_id")]
    require(len(decisions) == 1, "one committed new repair adoption decision required")
    decision = decisions[0]
    review_pin = pin(root, continuation.get("source_qa")); box = doc(root, review_pin)
    review = box.get("candidate_review", {}); producer_pin = pin(root, continuation.get("producer_outbox"))
    require(manifest.get("schema") == "flashcast-exact-source-candidate/v1"
            and manifest.get("task_id") == WEEKLY_SOURCE_TASK and manifest.get("scope") == WEEKLY_SOURCE_SCOPE
            and manifest.get("candidate_version") == WEEKLY_SOURCE_VERSION
            and manifest.get("primary_owner") == "system-development" and manifest.get("responsible_assistant") == role
            and manifest.get("candidate_fingerprint") == digest({key:value for key,value in manifest.items() if key != "candidate_fingerprint"})
            and box.get("department") == role and box.get("task_id") == WEEKLY_SOURCE_TASK
            and box.get("candidate_version") == WEEKLY_SOURCE_VERSION and box.get("scope") == WEEKLY_SOURCE_SCOPE
            and box.get("status") == "partial" and box.get("prepared_only", False) is False
            and not box.get("goal_acceptance") and box.get("qa_verdict") != "pass"
            and review.get("actor") == role and review.get("verdict") == "PASS_SOURCE_CANDIDATE_ONLY"
            and review.get("phase") == "candidate_source_only" and review.get("direction") == "forward"
            and review.get("candidate_manifest") == manifest_pin and review.get("candidate_fingerprint") == manifest["candidate_fingerprint"]
            and review.get("producer_outbox") == producer_pin and review.get("review_plan") == continuation.get("review_plan")
            and review.get("goal_contract") == manifest.get("goal_contract") and review.get("human_authorization") == manifest.get("human_authorization")
            and all(manifest.get(key) is False and box.get(key) is False and review.get(key) is False for key in V5_REVIEW_FLAGS),
            "independently accepted exact source manifest required before executing its frozen helper")
    w.validate_outbox(root, [review_pin], role, WEEKLY_SOURCE_TASK)
    _native(root, box, [WEEKLY_SOURCE_TASK, WEEKLY_SOURCE_VERSION, manifest["candidate_fingerprint"],
                       producer_pin["sha256"], manifest_pin["sha256"], "PASS_SOURCE_CANDIDATE_ONLY"], role)
    require(decision.get("event") == "controller_decision" and decision.get("decision") == "continue"
            and decision.get("task_id") == WEEKLY_SOURCE_TASK and decision.get("candidate_version") == WEEKLY_SOURCE_VERSION
            and decision.get("outbox") == producer_pin and review_pin in decision.get("evidence", [])
            and decision.get("coordinator_role") == decision.get("decision_actor") == decision.get("responsible_assistant") == role
            and decision.get("next_owner") == role and decision.get("next_action") == "adopt-" + WEEKLY_SOURCE_VERSION
            and decision.get("business_goal_closed") is False and decision.get("qa_status") != "pass",
            "actual independent source-only adoption decision must bind the accepted helper manifest")
    _committed(root, decision); _v5_source_decision_fence(root, decision, role)
    source = {key: continuation[key] for key in ("task_id", "scope", "candidate_version", "candidate_manifest",
                                               "source_qa", "review_plan", "producer_outbox", "prepared_only", *V5_REVIEW_FLAGS)}
    source["schema"] = "flashcast-actual-source-review-input/v1"
    repair_installed = None if repair_continuation_pin is None else _weekly_lineage_key_repair_successor(root,
        repair_continuation_pin, continuation_pin, native_continuation_pin, old_manifest_pin, source_repair_continuation_pin, functional_continuation_pin)
    helper = _weekly_key_context(root) if functional_continuation_pin is None else _weekly_functional_context(root, functional_continuation_pin)
    args = (root, manifest_pin, source, decision["record_id"], role, decision.get("coordinator_owner"), continuation_pin, repair_continuation_pin)
    manifest, reviewed, actual_decision, identity = helper.historical_weekly_review_context(*args) if functional_continuation_pin is None else helper.historical_weekly_review_context(*args, functional_continuation_pin)
    require(actual_decision == decision and identity == {"task_id":WEEKLY_SOURCE_TASK,"sender_department":"system-development",
            "candidate_version":WEEKLY_SOURCE_VERSION,"result_sha256":reviewed["producer_pin"]["sha256"]},
            "exact actual new repair producer and independent decision identity required")
    previous_native = doc(root, native_continuation_pin)
    previous_boundary = doc(root, source_repair_continuation_pin)
    require(previous_native.get("schema") == "actual_native_control_source_continuation/v1"
            and previous_native.get("task_id") == NATIVE_SOURCE_TASK
            and previous_native.get("historical_V5_manifest") == old_manifest_pin
            and previous_boundary.get("schema") == "actual_acceptance_message_historical_adoption_source_continuation/v1"
            and previous_boundary.get("task_id") == SOURCE_REPAIR_TASK
            and previous_boundary.get("historical_V5_manifest") == old_manifest_pin
            and previous_boundary.get("original_native_control_continuation") == native_continuation_pin,
            "immutable exact V5/V6/boundary predecessor links required")
    native_manifest = doc(root, previous_native.get("candidate_manifest"))
    boundary_manifest = doc(root, previous_boundary.get("candidate_manifest"))
    original_installed = {row["path"]: {"path": row["path"], **row["after"]} for row in native_manifest["files"]}
    original_installed.update({row["path"]: {"path": row["path"], **row["after"]} for row in boundary_manifest["files"]})
    operations = journal.get("source_operations", [])
    require(journal.get("task_id") == WEEKLY_SOURCE_TASK and journal.get("candidate_version") == WEEKLY_SOURCE_VERSION
            and journal.get("candidate_fingerprint") == manifest["candidate_fingerprint"] and journal.get("candidate_manifest") == manifest_pin
            and journal.get("review_outbox") == reviewed["review_pin"] and journal.get("authorized_source") == reviewed["authority_pin"]
            and journal.get("actor") == role and journal.get("direction") == "forward" and journal.get("status") == "complete"
            and type(journal.get("external_writes")) is int and journal["external_writes"] == 0
            and journal.get("effect_uncertain") is False and journal.get("permissions_issued") is False
            and journal.get("source_effect_state") == "ALL_REVIEWED_AFTER_VERIFIED"
            and type(journal.get("operator_source_syscalls_attempted")) is int
            and journal["operator_source_syscalls_attempted"] == len(WEEKLY_SOURCE_PATHS)
            and isinstance(journal.get("execution_id"), str) and bool(journal["execution_id"].strip())
            and len(operations) == len(WEEKLY_SOURCE_PATHS) and {row.get("path") for row in operations} == WEEKLY_SOURCE_PATHS
            and len(journal.get("applied", [])) == len(WEEKLY_SOURCE_PATHS) and set(journal["applied"]) == WEEKLY_SOURCE_PATHS,
            "actual complete independent five-target repair CAS journal required")
    installed = {}
    for row in manifest["files"]:
        path = row["path"]
        require(row.get("before") != {"exists":False}
                and (path not in original_installed or row["before"] == {key:original_installed[path][key] for key in ("sha256", "size")}),
                "new repair before must preserve exact verified original V6 overlap")
        operation = next(value for value in operations if value["path"] == path)
        backup = pin(root, operation.get("backup")); candidate = pin(root, row.get("candidate")); baseline = pin(root, row.get("baseline"))
        require(operation.get("before") == row["before"] == {key:baseline[key] for key in ("sha256", "size")}
                == {key:backup[key] for key in ("sha256", "size")}
                and operation.get("after_expected") == operation.get("after_actual") == row["after"]
                == {key:candidate[key] for key in ("sha256", "size")}
                and operation.get("write_attempted") is True and operation.get("verified_after") is True
                and operation.get("source_syscall_attempted") is True
                and operation.get("temporary_path") == path + ".cas-" + journal["execution_id"]
                and backup["path"] == f"backups/{WEEKLY_SOURCE_TASK}/{manifest['candidate_fingerprint']}/forward/" + path
                and backup["path"].startswith(f"backups/{WEEKLY_SOURCE_TASK}/{manifest['candidate_fingerprint']}/forward/")
                and type(operation.get("before_mode")) is int and operation["before_mode"] == row.get("before_mode")
                and w.safe_path(root, backup["path"]).stat().st_mode & 0o777 == operation["before_mode"]
                and w.safe_path(root, baseline["path"]).stat().st_mode & 0o777 == row["before_mode"]
                and w.safe_path(root, path).stat().st_mode & 0o777 == row.get("after_mode"),
                "exact new repair original backup, before/write/readback effects and installed modes required")
        if repair_installed is not None and path in WEEKLY_KEY_REPAIR_PATHS:
            repair = doc(root, repair_continuation_pin)
            next_manifest = doc(root, repair["candidate_manifest"])
            next_rows = [value for value in next_manifest["files"] if value["path"] == path]
            require(len(next_rows) == 1 and next_rows[0]["before"] == row["after"]
                    and next_rows[0]["before_mode"] == row["after_mode"], "current repair must begin at exact V2 installed bytes/mode")
            installed[path] = {"path":path, **row["after"]}
        else:
            installed[path] = pin(root, {"path":path, **row["after"]})
    follows = [row for row in handoffs if row.get("record_id") == continuation.get("adoption_followthrough_record_id")]
    require(len(follows) == 1, "unique actual new repair adopted-effects followthrough required")
    follow = follows[0]
    require(follow.get("event") == "controller_followthrough" and follow.get("followthrough_status") == "blocked_with_owner"
            and c.exact_identity(follow) == identity and follow.get("outbox") == reviewed["producer_pin"]
            and follow.get("coordinator_role") == follow.get("decision_actor") == follow.get("responsible_assistant") == role
            and follow.get("coordinator_owner") == decision.get("coordinator_owner")
            and follow.get("coordination_fence") == decision.get("coordination_fence") and follow.get("business_goal_closed") is False
            and follow.get("unblock_condition") == "source-adopted:" + journal["execution_id"] + ";remaining:original-weekly-functional-and-T3-acceptance"
            and journal_pin in follow.get("evidence", []) and handoffs.index(decision) < handoffs.index(follow),
            "exact new repair committed installed-source readback and original consumer boundaries required")
    _committed(root, follow); audit = _v5_source_decision_fence(root, follow, role)
    if functional_continuation_pin is not None:
        _source_release_readback(root, follow, audit)
    box = doc(root, reviewed["review_pin"])
    moments = [w._parse_observed_at(value) for value in (box.get("created_at"), journal.get("started_at"), journal.get("completed_at"))]
    require(all(value is not None for value in moments) and moments == sorted(moments)
            and moments[-1] <= dt.datetime.now(dt.timezone.utc)
            and moments[-1].timestamp() <= audit["reserved_at"] <= audit["committed_at"],
            "ordered independent new repair review, CAS and permanent committed followthrough required")
    return installed


def _v5_source_adoption(root, proof, accepted):
    """Read actual independent source QA and committed source effects, never make them."""
    import goal_delivery_runtime as g
    import qa_review_plan as q
    from scoped_candidate_adoption import _committed, _receipts
    snapshot = g.restore_goal(root, w.read_json(w.snapshot_path(root, V5_SOURCE_TASK)))
    goal = snapshot.get("goal_delivery", {})
    g.validate_goal(root, goal)
    require(snapshot.get("task_id") == V5_SOURCE_TASK and goal.get("parent_task_id") == TASK
            and goal.get("primary_owner") == "system-development" and goal.get("producer_departments") == ["system-development"]
            and goal.get("authorized_scope") == [V5_SOURCE_SCOPE] and goal.get("acceptance_capability") == "development"
            and q._goal_reviewer(root, snapshot) == ROLE
            and pin(root, proof.get("goal_contract")) == pin(root, snapshot.get("goal_contract"))
            and pin(root, proof.get("human_authorization")) == pin(root, goal.get("authorization_pin")),
            "actual V5 source goal/human authorization and independent development A2 required")
    manifest_pin = pin(root, proof.get("candidate_manifest"))
    manifest = doc(root, manifest_pin)
    require(manifest.get("schema") == "flashcast-exact-source-candidate/v1"
            and manifest.get("task_id") == V5_SOURCE_TASK and manifest.get("candidate_version") == V5_SOURCE_VERSION
            and manifest.get("scope") == V5_SOURCE_SCOPE
            and manifest.get("candidate_fingerprint") == digest({k: v for k, v in manifest.items() if k != "candidate_fingerprint"})
            and manifest.get("goal_contract") == pin(root, proof["goal_contract"])
            and manifest.get("human_authorization") == pin(root, proof["human_authorization"]),
            "exact immutable V5 source manifest and complete fingerprint required")
    require(manifest.get("current_source_context") == {
                "workflow_commit": proof["current_commit"],
                "workflow_source": pin(root, proof["workflow_current"]),
                "frontend_version": pin(root, proof["frontend_version"])},
            "source adoption and consumer must retain one reviewed workflow/frontend context")
    files = manifest.get("files", [])
    require(len(files) == len(V5_CHANGED_SOURCES) and {row.get("path") for row in files} == V5_CHANGED_SOURCES,
            "V5 source adoption is limited to bounded helper, issuer Saved guard, and tests")
    for row in files:
        baseline, candidate, delta = [pin(root, row.get(key)) for key in ("baseline", "candidate", "diff")]
        before, after = [w.safe_path(root, value["path"]).read_bytes() for value in (baseline, candidate)]
        require(row.get("before") == row.get("expected_source") == _content_pair(before)
                and row.get("after") == row.get("candidate_content") == _content_pair(after)
                and row.get("candidate_relative_path") == "candidate/" + row["path"]
                and candidate["path"] == str(Path(manifest_pin["path"]).parent / row["candidate_relative_path"])
                and baseline["path"] == str(Path(manifest_pin["path"]).parent / ("baseline/" + row["path"]))
                and delta["path"] == str(Path(manifest_pin["path"]).parent / row["forward_diff_relative_path"])
                and row.get("forward_diff_content") == {key: delta[key] for key in ("sha256", "size")},
                "manifest consumer pins must equal the exact source CAS fields")
        for direction, first, last, prefix, suffix in (("forward", before, after, "a/", "b/"),
                                                       ("reverse", after, before, "a/", "b/")):
            frozen = pin(root, {"path": str(Path(manifest_pin["path"]).parent / row[direction + "_diff_relative_path"]), **row[direction + "_diff_content"]})
            raw = w.safe_path(root, frozen["path"]).read_bytes()
            expected = "".join(difflib.unified_diff(first.decode("utf-8").splitlines(keepends=True),
                last.decode("utf-8").splitlines(keepends=True), fromfile=prefix + row["path"],
                tofile=suffix + row["path"])).encode("utf-8")
            require(raw == expected, "exact source forward/reverse diff must be recomputed")
    historical = _v5_historical_sources(root, manifest)
    current = _qualified_rule_history_current_lineage(root, proof, accepted, manifest_pin, historical)
    protected = manifest.get("protected_sources", [])
    require(len(protected) == len(V5_PROTECTED_SOURCES) and {value["path"] for value in protected} == V5_PROTECTED_SOURCES
            and all(value == historical[value["path"]] for value in protected),
            "original reviewed QA/runtime/workflow bytes must remain in the verified source lineage")
    require(isinstance(proof.get("source_qa"), dict), "new actual independent A2 development source-only QA is missing")
    review_pin = pin(root, proof.get("source_qa"))
    box = doc(root, review_pin)
    review = box.get("candidate_review", {})
    binding = q._binding(root, snapshot) or {}
    plan_pin = pin(root, proof.get("review_plan"))
    plan = doc(root, plan_pin)
    require(binding.get("pin") == plan_pin, "actual bound V5 source review plan required")
    q.validate_plan(root, snapshot, plan)
    receipts = _receipts(root, V5_SOURCE_TASK)
    require(not w.validate_workflow_events(root, V5_SOURCE_TASK)
            and plan.get("candidate_version") == V5_SOURCE_VERSION and plan.get("scope") == V5_SOURCE_SCOPE
            and plan.get("reviewer_department") == ROLE and plan.get("producer_department") == "system-development",
            "actual same-version source dispatch and independent review round required")
    producer_pin = pin(root, proof.get("producer_outbox"))
    producer = doc(root, producer_pin)
    w.validate_outbox(root, [producer_pin], "system-development", V5_SOURCE_TASK)
    require(producer.get("candidate_version") == V5_SOURCE_VERSION and producer.get("candidate_fingerprint") == manifest["candidate_fingerprint"]
            and producer.get("evidence", {}).get("candidate_manifest") == manifest_pin
            and q._producer_candidate_bound(root, plan, producer_pin, producer), "same exact source producer and plan required")
    w.validate_outbox(root, [review_pin], ROLE, V5_SOURCE_TASK)
    require(box.get("schema_version") == "2.0" and box.get("task_id") == V5_SOURCE_TASK
            and box.get("department") == ROLE and box.get("candidate_version") == V5_SOURCE_VERSION
            and box.get("scope") == V5_SOURCE_SCOPE and box.get("status") == "partial"
            and review.get("actor") == ROLE and review.get("verdict") == "PASS_SOURCE_CANDIDATE_ONLY"
            and review.get("phase") == "candidate_source_only" and review.get("direction") == "forward"
            and review.get("candidate_manifest") == manifest_pin and review.get("candidate_fingerprint") == manifest["candidate_fingerprint"]
            and review.get("review_plan") == plan_pin and review.get("producer_outbox") == producer_pin
            and review.get("goal_contract") == pin(root, proof["goal_contract"])
            and review.get("human_authorization") == pin(root, proof["human_authorization"])
            and review.get("workflow_commit") == proof["current_commit"]
            and review.get("workflow_source") == pin(root, proof["workflow_current"])
            and review.get("frontend_version") == pin(root, proof["frontend_version"])
            and manifest_pin in list(q._evidence_pins(box.get("evidence", [])))
            and all(box.get(key) is False and review.get(key) is False for key in V5_REVIEW_FLAGS)
            and box.get("prepared_only", False) is False and not box.get("goal_acceptance") and box.get("qa_verdict") != "pass",
            "new actual A2 source-only QA required; old PASS/preparation cannot migrate")
    _native(root, box, [V5_SOURCE_TASK, V5_SOURCE_VERSION, manifest["candidate_fingerprint"],
                        proof["current_commit"], "PASS_SOURCE_CANDIDATE_ONLY"])
    require(isinstance(proof.get("source_adoption"), dict), "actual adopted V5 source journal is missing")
    journal_pin = pin(root, proof.get("source_adoption"))
    journal = doc(root, journal_pin)
    operations = journal.get("source_operations", [])
    require(journal.get("task_id") == V5_SOURCE_TASK and journal.get("candidate_version") == V5_SOURCE_VERSION
            and journal.get("candidate_fingerprint") == manifest["candidate_fingerprint"]
            and journal.get("direction") == "forward" and journal.get("status") == "complete" and journal.get("actor") == ROLE
            and journal.get("review_outbox") == review_pin and journal.get("external_writes") == 0
            and type(journal.get("external_writes")) is int and journal.get("effect_uncertain", False) is False
            and isinstance(journal.get("execution_id"), str) and bool(journal["execution_id"].strip())
            and len(operations) == len(files) and {row.get("path") for row in operations} == V5_CHANGED_SOURCES
            and len(journal.get("applied", [])) == len(files) and set(journal["applied"]) == V5_CHANGED_SOURCES,
            "actual complete same-fingerprint source adoption journal required")
    for operation in operations:
        row = next(value for value in files if value["path"] == operation["path"])
        actual = {"path": row["path"], **row["after"]}
        require(actual == historical[row["path"]], "original installed effect must equal its immutable candidate")
        backup = pin(root, operation.get("backup"))
        require(operation.get("before") == row["before"] and operation.get("after_expected") == operation.get("after_actual") == row["after"]
                and operation.get("write_attempted") is True and operation.get("verified_after") is True
                and {key: backup[key] for key in ("sha256", "size")} == row["before"]
                and backup["path"].startswith(f"backups/{V5_SOURCE_TASK}/{manifest['candidate_fingerprint']}/forward/")
                and type(operation.get("before_mode")) is int
                and w.safe_path(root, backup["path"]).stat().st_mode & 0o777 == operation["before_mode"]
                and (row["path"] in NATIVE_SOURCE_PATHS or pin(root, actual) == actual),
                "exact historical source CAS effect, unchanged protected source and original backup required")
    handoffs = w._result_handoff_rows(root, V5_SOURCE_TASK)
    decisions = [row for row in handoffs if row.get("record_id") == journal.get("decision_record_id")]
    require(len(decisions) == 1, "unique actual V5 source adoption decision required")
    decision = decisions[0]
    require(decision.get("event") == "controller_decision" and decision.get("decision") == "continue"
            and decision.get("coordinator_role") == decision.get("decision_actor") == decision.get("responsible_assistant") == ROLE
            and decision.get("sender_department") == "system-development" and decision.get("candidate_version") == V5_SOURCE_VERSION
            and decision.get("outbox") == producer_pin and review_pin in decision.get("evidence", [])
            and decision.get("business_goal_closed") is False and decision.get("qa_status") != "pass"
            and decision.get("next_owner") == ROLE and type(decision.get("coordination_fence")) is int
            and decision["coordination_fence"] > 0, "actual fenced source-only A2 continue required")
    _v5_source_responsibility(root, snapshot, manifest, producer_pin, review_pin, decision)
    _committed(root, decision)
    follows = [row for row in handoffs if row.get("record_id") == proof.get("adoption_followthrough_record_id")]
    require(len(follows) == 1, "actual source adoption followthrough required; journal alone is not a committed effect")
    follow = follows[0]
    # The protected ordinary service permits a continue's named dependency
    # carrier. It cannot mint execution_verified or a formal QA assignment.
    # Installed source effects were independently checked above; this carrier
    # records those exact bytes while keeping the original business work open.
    require(follow.get("event") == "controller_followthrough" and follow.get("followthrough_status") == "blocked_with_owner"
            and follow.get("coordinator_role") == follow.get("decision_actor") == follow.get("responsible_assistant") == ROLE
            and follow.get("candidate_version") == V5_SOURCE_VERSION and follow.get("sender_department") == "system-development"
            and follow.get("outbox") == decision["outbox"]
            and follow.get("unblock_condition") == "source-adopted:" + journal["execution_id"] + ";remaining:original-T3-current-Saved-readback-and-public-postcheck"
            and journal_pin in follow.get("evidence", []) and follow.get("business_goal_closed") is False
            and follow.get("coordinator_owner") == decision.get("coordinator_owner")
            and follow.get("coordination_fence") == decision["coordination_fence"]
            and handoffs.index(decision) < handoffs.index(follow),
            "exact installed-source journal and committed A2 dependency followthrough required")
    _committed(root, follow)
    audit = _v5_source_decision_fence(root, follow)
    observed, created, started, completed, followed = [w._parse_observed_at(value) for value in
        (box.get("reply_observed_at"), box.get("created_at"), journal.get("started_at"), journal.get("completed_at"), follow.get("created_at"))]
    next_check = w._parse_observed_at(follow.get("next_check_at"))
    require(all(value is not None for value in (observed, created, started, completed, followed))
            and observed <= created <= started <= completed <= dt.datetime.now(dt.timezone.utc)
            and completed.timestamp() <= audit["reserved_at"] <= audit["committed_at"]
            and followed <= dt.datetime.now(dt.timezone.utc) and next_check is not None and next_check > followed,
            "ordered real source review, adoption and followthrough times required")


def _v5_source_bridge(root, source, deployment, machine, accepted, proof):
    _v5_bridge_header(proof)
    bridge_pin = pin(root, source.get("source_coherence"))
    require(bridge_pin == pin(root, accepted.get("source_bridge")) == pin(root, machine.get("source_bridge"))
            and pin(root, proof.get("current_producer")) == pin(root, accepted.get("current_producer"))
            and proof.get("operation") == accepted.get("operation"),
            "one exact source bridge must be frozen by A2 and this machine")
    producer = doc(root, accepted["current_producer"])
    require(_machine_sources(root, producer, bridge_pin)["actual_machine_source"] == pin(root, accepted["actual_machine_source"]),
            "V5 source bridge must bind the latest original publisher evidence")
    _v5_workflow_bridge_bytes(root, proof)
    _v5_source_adoption(root, proof, accepted)
    production, main = source["production_sha"], machine["main_sha"]
    require(production == V5_BASELINE_COMMIT and main == machine["workflow_sha"] == proof["current_commit"]
            and source.get("function_version") == deployment.get("function_version") == 77
            and deployment.get("deployment_run_id") == 38061480070
            and deployment.get("original_deployment_source_proof") == proof.get("actual_deployment_source_proof"),
            "V5 workflow, frontend and original deployed runtime identities remain distinct")
    original = _website_json(proof["actual_deployment_source_proof"])
    require(original.get("task_id") == TASK and original.get("content_candidate_version") == VERSION
            and original.get("source_candidate_version") == WEBSITE_SOURCE_VERSION
            and original.get("status") == "PASS_ACTUAL_PRODUCTION_EDGE_SOURCE_AND_RECOVERY_BACKUP"
            and original.get("production_website_sha") == production and original.get("run_id") == 38061480070
            and original.get("actual_function", {}).get("name") == "content-publish"
            and original["actual_function"].get("status") == "ACTIVE"
            and original["actual_function"].get("after_version") == original["actual_function"].get("after_download_version") == 77
            and pin(WEBSITE, original["actual_readback"]["manifest"]) == pin(WEBSITE, proof["actual_deployed_runtime_manifest"]),
            "original real deployed v77 source and download provenance required")
    run = _website_json(original["run_proof"])["run"]
    require(run.get("id") == 38061480070 and run.get("head_sha") == production and run.get("status") == "completed"
            and run.get("conclusion") == "success" and run.get("event") == "workflow_dispatch", "original completed deployment run required")
    for name in ("functions-after.json", "functions-after-download.json"):
        matches = [value for value in original["artifact_metadata_pins"] if value["path"].endswith("/" + name)]
        require(len(matches) == 1, "actual original deployment metadata required")
        functions = _website_json(matches[0])
        require(isinstance(functions, list) and len([value for value in functions if value.get("name") == "content-publish"
                and value.get("version") == 77 and value.get("status") == "ACTIVE"]) == 1, "actual deployed function version differs")
    manifest = _website_json(proof["actual_deployed_runtime_manifest"])
    files, mapping = manifest.get("files", []), proof.get("runtime_file_map", [])
    closure = hashlib.sha256(json.dumps(files, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
    require(manifest.get("schema") == "content-publish-runtime-source/v1" and manifest.get("entrypoint") == "content-publish/index.ts"
            and len(files) == len(mapping) == proof.get("actual_runtime_source_closure_file_count") == 21
            and len({value.get("path") for value in files}) == len({value.get("runtime_path") for value in mapping}) == 21
            and {value.get("path") for value in files} == {value.get("runtime_path") for value in mapping}
            and closure == proof.get("actual_runtime_source_closure_digest") == original["actual_readback"]["source_sha256"],
            "all original 21 downloaded runtime files required for V5")
    readback = WEBSITE / DEPLOYMENT_EVIDENCE / "production-r3-run-38061480070-artifacts/readback/edge-after/supabase/functions"
    require(Path(original["actual_readback"]["root"]).resolve() == readback.resolve(), "original downloaded runtime root required")
    for entry in files:
        path = entry["path"]
        require(re.fullmatch(r"(?:_shared|content-publish)/[a-zA-Z0-9_-]+\.ts", path) is not None, "exact runtime source path required")
        mapped = next(value for value in mapping if value["runtime_path"] == path)
        require(mapped.get("git_path") == "supabase/functions/" + path and mapped.get("workflow_commit") == main
                and mapped.get("workflow_commit_sha256") == mapped.get("actual_deployed_v77_sha256") == entry["sha256"]
                and mapped.get("workflow_commit_bytes") == mapped.get("actual_deployed_v77_bytes") == entry["bytes"], "V5 runtime map digest differs")
        raw = _website_bytes({"path": str(readback / path), "sha256": entry["sha256"], "size": entry["bytes"]})
        require(_git_source(main, mapped["git_path"]) == _git_source(production, mapped["git_path"]) == raw,
                "V5 immutable workflow/deployed runtime bytes differ")
    cli = proof.get("workflow_and_CLI_source_map", [])
    require(len(cli) == 2 and {value.get("path") for value in cli} == set(WORKFLOW_CLI[1:]),
            "V5 keeps two original CLI files separate from the reviewed whole workflow diff")
    for mapped in cli:
        approved = [value for value in original["source_pins"] if value.get("path") == mapped["path"]]
        require(len(approved) == 1 and mapped.get("workflow_commit") == main
                and mapped.get("workflow_commit_sha256") == mapped.get("approved_5237_source_sha256") == approved[0]["sha256"]
                and mapped.get("workflow_commit_bytes") == mapped.get("approved_5237_source_bytes") == approved[0]["bytes"], "V5 exact CLI digest differs")
        raw = _git_source(main, mapped["path"])
        require(raw == _git_source(production, mapped["path"]) and _content_pair(raw) ==
                {"sha256": approved[0]["sha256"], "size": approved[0]["bytes"]}, "V5 original CLI bytes differ")
    for runtime in ("content-publish/service.ts", "_shared/managed-targets.ts"):
        entry = next(value for value in files if value["path"] == runtime)
        require(any(value.get("path", "").endswith("/" + runtime.rsplit("/", 1)[-1])
                and value.get("sha256") == entry["sha256"] and value.get("size") == entry["bytes"]
                for value in source.get("source_snapshots", [])), "V5 recovery snapshots must match deployed restore source")
    facts = doc(root, accepted["actual_machine_source"])
    records = [value for value in facts["records"] if value.get("slug") == accepted["row"]["slug"]]
    require(pin(root, proof.get("raw_machine_run")) == pin(root, machine.get("run_snapshot")),
            "V5 source bridge must freeze the full original machine run")
    if machine.get("action_id") != f"rollback-{VERSION}":
        require(len(records) == 1 and pin(root, proof["raw_machine_run"]) == pin(root, records[0].get("full_original_gh_run")),
                "V5 publish source bridge must freeze this pending row's actual run")
    return bridge_pin


def _machine_sources(root, current, source_bridge=None):
    """Original authority and current preview are separately pinned provenance."""
    if source_bridge is not None:
        return _v5_machine_sources(root, current, source_bridge)
    evidence = current["evidence"]
    actual = evidence.get("actual_machine_identity_and_preview_facts")
    if actual is None:
        return {"original_machine_source": pin(root, evidence["original_authority_review_machine_channel"])}
    previous = doc(root, evidence["original_V3"])
    require(previous.get("task_id") == TASK and previous.get("candidate_version") == VERSION
            and pin(root, previous["evidence"]["original_V2"]) == pin(root, evidence["original_V2"]),
            "current V4 must retain original V3/V2 authority provenance")
    original = pin(root, previous["evidence"]["original_authority_review_machine_channel"])
    require(evidence.get("original_authority_review_machine_channel") is None
            or pin(root, evidence["original_authority_review_machine_channel"]) == original,
            "conflicting original machine source forbidden")
    actual_pin = pin(root, actual)
    facts = doc(root, actual_pin)
    require(facts.get("task_id") == TASK and facts.get("candidate_version") == VERSION
            and len(facts.get("records", [])) == 3
            and [x.get("slug") for x in facts["records"]] == [r[0] for r in ROWS]
            and re.fullmatch(r"[0-9a-f]{40}", str(facts.get("machine_workflow_sha", "")))
            and re.fullmatch(r"[0-9a-f]{40}", str(facts.get("native_frontend_loaded_sha", "")))
            and facts.get("website_deployed_source_candidate_version") == WEBSITE_SOURCE_VERSION
            and facts.get("new_account_permission") is False and facts.get("cms_save") == 0
            and facts.get("signing_authority", {}).get("new_single_use_CMS_permits_issued") == 0,
            "actual current V4 machine facts required")
    return {"original_machine_source": original, "actual_machine_source": actual_pin}


def _producer_native(root, current_pin):
    import goal_delivery_runtime as g
    from scoped_candidate_adoption import _committed
    rows = [r for r in w._result_handoff_rows(root, TASK) if r.get("event") == "controller_received"
            and r.get("outbox") == current_pin and r.get("coordinator_role") == ROLE]
    require(len(rows) == 1, "one actual current producer native intake required")
    row = rows[0]
    _committed(root, row)
    native = g._collaboration_native(root, row.get("actual_native_completion"))
    fixed = w.department_registry(root)[PRODUCER]["chat_binding"]
    require(native.get("thread", {}).get("id") == fixed["task_id"] == row.get("source_thread_id")
            and w._same_resolved_path(str(native.get("thread", {}).get("cwd", "")), str(Path(root).resolve())),
            "current producer original fixed chat required")
    visible = pin(root, row.get("visible_reply"))
    raw = w.safe_path(root, visible["path"]).read_bytes()
    message = g._collaboration_final_message(native, fixed["task_id"])
    require(message.get("turnId") == row.get("source_turn_id")
            and message.get("phase") == "final_answer" and isinstance(message.get("text"), str)
            and message["text"].strip() and message["text"].encode("utf-8") == raw
            and row.get("source_reply_sha256") == visible["sha256"],
            "exact current producer completed UTF-8 required")


def _current(root, snapshot):
    import goal_delivery_runtime as g
    import qa_review_plan as q
    snapshot = g.restore_goal(root, q._review_context(root, snapshot))
    require(snapshot.get("task_id") == TASK and g.enabled(root, snapshot)
            and snapshot.get("current_state") not in w.TERMINAL_STATES, "active original modern T3 required")
    goal = snapshot["goal_delivery"]
    g.validate_goal(root, goal)
    require(goal.get("source_mode") == "owner_direct" and goal.get("primary_owner") == PRODUCER
            and goal.get("producer_departments") == [PRODUCER] and goal.get("authorized_scope") == [SCOPE]
            and goal.get("acceptance_capability") == "cms" and q._goal_reviewer(root, snapshot) == ROLE,
            "original publisher-only authority and sole independent A2 required")
    origin = q.owner_direct_review_context(root, snapshot)
    require(isinstance(origin, dict) and origin.get("prepared_only") is True,
            "original adopted owner-direct review provenance required")
    plan_pin = q._binding(root, snapshot)["pin"]
    receipts, invalid = w._validate_receipt_chain(root, TASK)
    require(not invalid and not w.validate_workflow_events(root, TASK), "valid original receipt/event chains required")
    received = [row for row in receipts if row.get("receipt_type") == "outbox_received" and row.get("department") == PRODUCER]
    require(bool(received), "current publishing result required")
    current_pin = next((p for p in received[-1].get("evidence", []) if str(p.get("path", "")).endswith(".json")), None)
    current = doc(root, current_pin)
    w.validate_outbox(root, [current_pin], PRODUCER, TASK)
    require(current.get("task_id") == TASK and current.get("candidate_version") == VERSION
            and current.get("evidence", {}).get("original_V2") == origin["proof"]["producer_outbox"],
            "latest producer must retain original source/version")
    _producer_native(root, current_pin)
    rows, bindings, manifest = _rows(root, current)
    if _v5_shape(root, current):
        rows = _apply_saved_notices(root, rows)
    return snapshot, origin, plan_pin, current_pin, rows, bindings, manifest


@strict
def targets(root):
    """Expose only the original proposed tuples; registration is not admission."""
    snapshot = w.read_json(w.snapshot_path(root, TASK))
    if not snapshot or not isinstance(snapshot.get("goal_delivery"), dict):
        return {}
    _, _, _, _, rows, _, _ = _current(root, snapshot)
    return {f"paid-three-page-{row['slug']}-exact-fields-v1": {
        "task_id": TASK, "action_id": row["action_id"], "scope": row["scope"], "candidate_version": VERSION,
        "execution_owner": PRODUCER, "record_id": row["record_id"], "slug": row["slug"],
        "candidate_shape": MODEL, "changed_fields": row["changed_fields"], "evidence_root": str(Path(root).resolve()),
        "candidate": (row["candidate"]["path"], row["candidate"]["sha256"]),
        "rollback": (row["backup"]["path"], row["backup"]["sha256"]), "rollback_allowed": True,
        "bounded_row": row, **({"publication_state": row["publication_state"],
            "publish_allowed": row["publish_allowed"]} if "publication_state" in row else {})} for row in rows}


def _native(root, box, references, role=ROLE):
    import goal_delivery_runtime as g
    fixed = w.department_registry(root)[role]["chat_binding"]
    require(w._chat_binding_healthy(fixed, verification_ttl_hours=26), "current independent reviewer binding health required")
    native = g._collaboration_native(root, box.get("actual_native_reply"))
    thread = native.get("thread", {})
    reply = pin(root, box.get("visible_reply"))
    raw = w.safe_path(root, reply["path"]).read_bytes()
    turns = [turn for turn in native.get("turns", []) if turn.get("id") == box.get("source_turn_id")]
    require(thread.get("id") == box.get("fixed_chat_task_id") == fixed["task_id"]
            and w._same_resolved_path(str(thread.get("cwd", "")), str(Path(root).resolve()))
            and len(turns) == 1 and turns[0].get("status") in {"inProgress", "completed"}, "actual original A2 native turn required")
    messages = [item for item in turns[0].get("items", []) if item.get("type") == "agentMessage"
                and item.get("id") == box.get("source_message_id") and item.get("phase") in {"commentary", "final_answer"}
                and isinstance(item.get("text"), str) and item["text"].strip() and item["text"].encode("utf-8") == raw]
    reply_meta = box.get("chat_reply", {})
    require(len(messages) == 1 and box.get("source_reply_sha256") == reply["sha256"]
            and reply_meta.get("nonempty") is True and reply_meta.get("in_current_fixed_department_chat") is True
            and reply_meta.get("message_sha256") == reply["sha256"] and reply_meta.get("utf8_bytes") == len(raw)
            and reply_meta.get("source_turn_id") == box["source_turn_id"]
            and reply_meta.get("source_message_id") == box["source_message_id"], "one exact nonempty A2 UTF-8 message required")
    text = messages[0]["text"]
    require(all(re.search(r"(?<![A-Za-z0-9_./:-])" + re.escape(str(value))
                         + r"(?![A-Za-z0-9_./:-])", text) for value in references),
            "native candidate result must identify its exact source and bounded verdict")
    observed = w._parse_observed_at(box.get("reply_observed_at"))
    created = w._parse_observed_at(box.get("created_at"))
    started = turns[0].get("startedAt")
    require(type(started) in {int, float} and observed is not None and created is not None
            and 0 <= started <= observed.timestamp() and observed <= created <= dt.datetime.now(dt.timezone.utc),
            "ordered nonfuture actual review times required")


def _review_box(root, current_pin, kind):
    handoffs = w._result_handoff_rows(root, TASK)
    decisions = [row for row in handoffs if row.get("event") == "controller_decision"
                 and row.get("sender_department") == PRODUCER and row.get("outbox") == current_pin]
    require(bool(decisions), "actual current producer continuation required")
    decision = decisions[-1]
    require(decision.get("decision") == "continue" and decision.get("coordinator_role") == ROLE
            and decision.get("decision_actor") == ROLE and decision.get("responsible_assistant") == ROLE
            and type(decision.get("coordination_fence")) is int and decision["coordination_fence"] > 0
            and decision.get("next_owner") == PRODUCER and decision.get("candidate_version") == VERSION
            and decision.get("business_goal_closed") is False and decision.get("qa_status") != "pass",
            "actual fenced bounded continue required; full-goal PASS cannot substitute")
    from scoped_candidate_adoption import _committed
    _committed(root, decision)
    candidates = [(p, doc(root, p)) for p in decision.get("evidence", []) if str(p.get("path", "")).endswith(".json")]
    candidates = [(p, box) for p, box in candidates if isinstance(box.get(kind), dict)]
    require(len(candidates) == 1, "one real A2 bounded V2 required in committed continue evidence")
    box_pin, box = candidates[0]
    w.validate_outbox(root, [box_pin], ROLE, TASK)
    proof = box[kind]
    return decision, box_pin, box, proof


@strict
def acceptance(root, snapshot, target, operation="publish"):
    if operation == "rollback":
        return rollback_acceptance(root, snapshot, target)
    require(operation == "publish", "known exact operation required")
    snapshot, origin, plan_pin, current_pin, rows, bindings, manifest = _current(root, snapshot)
    if any("publication_state" in row for row in rows):
        match = [row for row in rows if row["action_id"] == target.get("action_id") and row["scope"] == target.get("scope")]
        require(len(match) == 1 and match[0].get("publication_state") == "pending_save"
                and match[0].get("publish_allowed") is True, "Saved or unresolved effects cannot be published again")
    require(exact_tuple(target.get("task_id"), target.get("action_id"), target.get("scope"), target.get("execution_owner"))
            and target.get("candidate_version") == VERSION and target.get("candidate_shape") == MODEL,
            "only original exact T3 tuple allowed")
    decision, box_pin, box, proof = _review_box(root, current_pin, "cms_candidate_acceptance")
    require(box.get("schema_version") == "2.0" and box.get("task_id") == TASK and box.get("department") == ROLE
            and box.get("candidate_version") == VERSION and box.get("status") == "partial"
            and box.get("qa_verdict") != "pass" and not box.get("goal_acceptance")
            and all(box.get(key) is False and proof.get(key) is False for key in FLAGS), "independent bounded V2 only; no production/full-goal PASS")
    expected = {"schema": MODEL, "task_id": TASK, "candidate_version": VERSION, "reviewer": ROLE,
                "producer": PRODUCER, "verdict": "PASS_CANDIDATE_ONLY", "project_scope": SCOPE,
                "authority": snapshot["goal_delivery"]["authorization_pin"], "goal_contract": snapshot["goal_contract"],
                "review_plan": plan_pin, "original_producer": origin["proof"]["producer_outbox"],
                "current_producer": current_pin, "bindings": bindings, "source_manifest": manifest, "rows": rows,
                **_machine_sources(root, doc(root, current_pin), proof.get("source_bridge")),
                "remaining_actions": ["exact_Save_and_SavedCAS", "public_desktop_mobile_noJS_verification"]}
    require(all(proof.get(key) == value for key, value in expected.items()), "bounded review differs from original/current authority, sources or rows")
    effect_pin = None
    if any("publication_state" in row for row in rows):
        effect_pin = _effect_review(root, proof, expected, rows, box)
    source_pins = proof.get("consumer_sources", [])
    require(isinstance(source_pins, list) and all(isinstance(p, dict) for p in source_pins)
            and sorted(p.get("path", "") for p in source_pins) == sorted(SOURCES),
            "current adopted consumer source versions required")
    for source in source_pins:
        pin(root, source)
    frozen = [plan_pin, current_pin, bindings, manifest, *source_pins]
    if "actual_machine_source" in expected:
        frozen += [expected["original_machine_source"], expected["actual_machine_source"]]
    if "source_bridge" in expected:
        frozen.append(expected["source_bridge"])
    require(all(p in box.get("evidence", []) for p in frozen), "bounded V2 must freeze all current evidence")
    _native(root, box, [TASK, VERSION, current_pin["sha256"], "PASS_CANDIDATE_ONLY"])
    reviewed = w._parse_observed_at(box.get("created_at"))
    continued = w._parse_observed_at(decision.get("created_at"))
    require(reviewed is not None and continued is not None and reviewed <= continued <= dt.datetime.now(dt.timezone.utc),
            "candidate review must precede committed continue")
    matching = [item for item in rows if all(target.get(k) == item[k] for k in ("record_id", "action_id", "scope", "slug"))]
    require(len(matching) == 1, "target record must match its original action/scope")
    row = matching[0]
    require(target.get("bounded_row") == row and target.get("changed_fields") == row["changed_fields"]
            and list(target.get("candidate", ())) == [row["candidate"]["path"], row["candidate"]["sha256"]]
            and list(target.get("rollback", ())) == [row["backup"]["path"], row["backup"]["sha256"]], "current exact target source required")
    return {"task_id": TASK, "scope": row["scope"], "acceptance_model": MODEL, "verdict": "pass_candidate_only", "operation": "publish", "candidate_version": VERSION,
            "candidate_acceptance_record_id": decision["record_id"], "candidate_acceptance_record_hash": decision["record_hash"],
            "created_at": box["created_at"], "responsible_assistant": ROLE, "risk_level": "R3",
            "review_outbox": box_pin, "review_plan": plan_pin, "candidate": row["candidate"],
            "authorization_pin": expected["authority"], "current_producer": current_pin, "row": row,
            **{k: expected[k] for k in ("original_machine_source", "actual_machine_source", "source_bridge") if k in expected},
            "consumer_sources": source_pins,
            "preflights": proof.get("execution_preflights", []), "business_goal_closed": False,
            "production_write_allowed": False, **({"effect_reconciliation": effect_pin,
                "remaining_publish_rows": proof["remaining_publish_rows"]} if effect_pin else {})}


@strict
def rollback_acceptance(root, snapshot, target):
    """A distinct independent review follows a real Save and fresh Saved CAS."""
    snapshot, origin, plan_pin, current_pin, rows, bindings, manifest = _current(root, snapshot)
    matching = [r for r in rows if all(target.get(k) == r[k] for k in ("record_id", "action_id", "scope", "slug"))]
    require(len(matching) == 1 and target.get("candidate_shape") == MODEL
            and target.get("task_id") == TASK and target.get("candidate_version") == VERSION
            and target.get("execution_owner") == PRODUCER
            and target.get("rollback_allowed") is True, "only the original three-row recovery namespace allowed")
    row = matching[0]
    require(target.get("bounded_row") == row and target.get("changed_fields") == row["changed_fields"]
            and list(target.get("candidate", ())) == [row["candidate"]["path"], row["candidate"]["sha256"]]
            and list(target.get("rollback", ())) == [row["backup"]["path"], row["backup"]["sha256"]],
            "rollback target must retain original fields and backup")
    continued, review_pin, box, proof = _review_box(root, current_pin, "cms_rollback_acceptance")
    require(box.get("schema_version") == "2.0" and box.get("task_id") == TASK and box.get("department") == ROLE
            and box.get("candidate_version") == ROLLBACK_VERSION and box.get("status") == "partial"
            and box.get("qa_verdict") != "pass" and not box.get("goal_acceptance")
            and all(box.get(k) is False and proof.get(k) is False for k in FLAGS),
            "new independent rollback result required; publish PASS cannot authorize recovery")
    expected = {"schema": MODEL + "_rollback", "task_id": TASK, "candidate_version": ROLLBACK_VERSION,
        "operation": "rollback", "reviewer": ROLE, "producer": PRODUCER, "project_scope": SCOPE,
        "verdict": "PASS_ROLLBACK_CANDIDATE_ONLY", "row": row, "authority": snapshot["goal_delivery"]["authorization_pin"],
        "goal_contract": snapshot["goal_contract"], "review_plan": plan_pin,
        "original_producer": origin["proof"]["producer_outbox"], "current_producer": current_pin,
        "bindings": bindings, "source_manifest": manifest,
        **_machine_sources(root, doc(root, current_pin), proof.get("source_bridge")),
        "remaining_actions": ["distinct_single_use_rollback", "restored_public_verification"]}
    require(all(proof.get(k) == v for k, v in expected.items()), "rollback authority/source/row/version differs")
    sources = proof.get("consumer_sources", [])
    require(isinstance(sources, list) and all(isinstance(p, dict) for p in sources)
            and sorted(p.get("path", "") for p in sources) == sorted(SOURCES), "current recovery consumer source pins required")
    for frozen in sources:
        pin(root, frozen)
    native_effect = proof.get("recovery_effect_schema") == EFFECT_SCHEMA
    publish_pin = None
    if native_effect:
        require(row.get("publication_state") == "saved_effect_observed_no_replay"
                and proof.get("publish_review_outbox") is None and proof.get("publish_continue_record_id") is None,
                "genuine native Save recovery cannot invent a prior company publish review or continue")
        parent_mapping, parent = _saved_parent(root, row, proof.get("saved_effect_completed_parent"), expected["authority"], expected["original_machine_source"])
        require(proof.get("completed_parent") == parent_mapping["completed_status"]
                and proof.get("parent_permit_id") == parent_mapping["parent_permit_id"]
                and proof.get("parent_run_id") == parent_mapping["parent_run_id"],
                "recovery must use the observed exact completed parent")
    else:
        publish_pin = pin(root, proof.get("publish_review_outbox"))
        publish_box = doc(root, publish_pin)
        published_review = publish_box.get("cms_candidate_acceptance", {})
        require(published_review.get("schema") == MODEL and published_review.get("verdict") == "PASS_CANDIDATE_ONLY"
                and published_review.get("rows") == rows and published_review.get("authority") == expected["authority"]
                and published_review.get("goal_contract") == expected["goal_contract"]
                and published_review.get("original_producer") == expected["original_producer"]
                and publish_box.get("department") == ROLE and publish_box.get("task_id") == TASK
                and publish_box.get("candidate_version") == VERSION and not publish_box.get("goal_acceptance")
                and all(publish_box.get(k) is False and published_review.get(k) is False for k in FLAGS)
                and published_review.get("current_producer") != current_pin,
                "original independent publish review and subsequent real Save result required")
        _native(root, publish_box, [TASK, VERSION, published_review["current_producer"]["sha256"], "PASS_CANDIDATE_ONLY"])
        parent_rows = [r for r in w._result_handoff_rows(root, TASK) if r.get("record_id") == proof.get("publish_continue_record_id")]
        require(len(parent_rows) == 1 and parent_rows[0].get("event") == "controller_decision"
                and parent_rows[0].get("decision") == "continue" and parent_rows[0].get("coordinator_role") == ROLE
                and parent_rows[0].get("decision_actor") == ROLE and parent_rows[0].get("responsible_assistant") == ROLE
                and parent_rows[0].get("outbox") == published_review["current_producer"]
                and publish_pin in parent_rows[0].get("evidence", []), "actual original publish continue record required")
        from scoped_candidate_adoption import _committed
        _committed(root, parent_rows[0])
    if not native_effect:
        parent = doc(root, proof.get("completed_parent"))
    from managed_cms_permit_issuer import validate_completed_parent_status
    parent_run = proof.get("parent_run_id")
    parent_permit = proof.get("parent_permit_id")
    require(type(parent_run) is int and parent_run > 0 and isinstance(parent_permit, str) and parent_permit,
            "real original completed parent permit/run required")
    validate_completed_parent_status(parent, target, parent_permit, parent_run)
    current = doc(root, proof.get("saved_record"))
    before = doc(root, row["backup"])
    desired = doc(root, row["candidate"])
    require(set(current) == set(before) and current.get("id") == row["record_id"]
            and current.get("updated_at") == parent["savedUpdatedAt"]
            and current["updated_at"] != row["raw_updated_at"]
            and type(current.get("version")) is int
            and (current["version"] == row.get("current_native_version") if native_effect else current["version"] > row["native_version"])
            and all(current[k] == desired[k] for k in row["changed_fields"])
            and all(current[k] == before[k] for k in current if k not in {*row["changed_fields"], "updated_at", "version"}),
            "fresh exact Saved ID/microsecond CAS and unchanged retained values required")
    producer = doc(root, current_pin)
    if native_effect:
        require(proof["saved_record"] == row["current_record"] and current["updated_at"] == row["saved_raw_updated_at"],
                "new native effect recovery must retain current producer's exact Saved readback")
    else:
        require(producer["evidence"].get("completed_parent") == proof["completed_parent"]
                and producer["evidence"].get("saved_record") == proof["saved_record"],
                "current producer must freeze actual protected Save/status/readback")
    restored = {**current, **{k: before[k] for k in row["changed_fields"]}}
    restore_pin = pin(root, proof.get("restore_candidate"))
    require(doc(root, restore_pin) == restored, "original backup-only restore; no other field changes")
    typed_pin = pin(root, proof.get("typed_preview"))
    typed = doc(root, typed_pin).get("request", {})
    require(typed.get("mode") == "dry-run" and typed.get("contentType") == "service"
            and typed.get("expectedUpdatedAt") == current["updated_at"] and typed.get("record") == restored
            and typed.get("managedCandidate") == {"taskId": TASK, "actionId": f"rollback-{VERSION}",
                "operation": "rollback", "scope": row["scope"], "candidateVersion": ROLLBACK_VERSION},
            "distinct rollback tuple and fresh Saved CAS request required")
    frozen = [plan_pin, current_pin, bindings, manifest, *sources,
              proof["completed_parent"], proof["saved_record"], restore_pin, typed_pin]
    if native_effect:
        frozen += [pin(root, proof["saved_effect_completed_parent"])]
    else:
        frozen.append(publish_pin)
    if "actual_machine_source" in expected:
        frozen += [expected["original_machine_source"], expected["actual_machine_source"]]
    if "source_bridge" in expected:
        frozen.append(expected["source_bridge"])
    require(all(p in box.get("evidence", []) for p in frozen), "new rollback V2 must freeze all source/readback/recovery bytes")
    _native(root, box, [TASK, ROLLBACK_VERSION, current_pin["sha256"], "PASS_ROLLBACK_CANDIDATE_ONLY"])
    reviewed, continued_at = w._parse_observed_at(box.get("created_at")), w._parse_observed_at(continued.get("created_at"))
    require(reviewed is not None and continued_at is not None and reviewed <= continued_at <= dt.datetime.now(dt.timezone.utc),
            "new rollback review must precede its actual continue")
    recovery_row = {**row, "action_id": f"rollback-{VERSION}", "raw_updated_at": current["updated_at"],
        "native_version": current["version"], "baseline_sha256": digest(current), "desired_sha256": digest(restored),
        "candidate": restore_pin, "typed_preview": typed_pin}
    return {"task_id": TASK, "scope": row["scope"], "acceptance_model": MODEL, "operation": "rollback",
        "candidate_version": ROLLBACK_VERSION, "verdict": "pass_rollback_candidate_only",
        "candidate_acceptance_record_id": continued["record_id"], "candidate_acceptance_record_hash": continued["record_hash"],
        "created_at": box["created_at"], "responsible_assistant": ROLE, "risk_level": "R3",
        "review_outbox": review_pin, "review_plan": plan_pin, "candidate": restore_pin,
        "authorization_pin": expected["authority"], "current_producer": current_pin, "row": recovery_row,
        **{k: expected[k] for k in ("original_machine_source", "actual_machine_source", "source_bridge") if k in expected},
        "consumer_sources": sources,
        "preflights": proof.get("execution_preflights", []), "parent_run_id": parent_run, "parent_permit_id": parent_permit,
        "completed_parent": proof["completed_parent"], "saved_record": proof["saved_record"],
        "business_goal_closed": False, "production_write_allowed": False}


@strict
def validate_machine(root, item, accepted):
    """Bind the reviewed run and original issuer, not a self-consistent new actor."""
    machine_pin = pin(root, item.get("machine_identity"))
    machine = doc(root, machine_pin)
    original_pin = pin(root, accepted["original_machine_source"])
    original = doc(root, original_pin)["actual_original_machine_channel_metadata"]
    issuer_pin = next(p for p in accepted["consumer_sources"] if p["path"] == "tools/managed_cms_permit_issuer.py")
    require(machine.get("schema") == "actual_t3_protected_machine_binding_v1"
            and machine.get("original_machine_source") == original_pin
            and machine.get("issuer_source") == issuer_pin, "original reviewed machine and issuer source pins required")
    pin(root, issuer_pin)
    expected = {"task_id": TASK, "candidate_version": item["candidate_version"], "department": PRODUCER,
        "action_id": item["action_id"], "scope": item["scope"], "action_class": "cms_write",
        "record_id": accepted["row"]["record_id"], "payload_sha256": item["payload_sha256"],
        "github_actor_id": original["existing_actor_id"], "repository": original["repository"],
        "workflow_id": original["workflow_id"], "workflow_path": original["workflow_path"],
        "repository_id": 1248188229,
        "workflow_ref": "wangchaozhuanyong/zhuangxiuwangzhan/.github/workflows/content-publish-approved.yml@refs/heads/main"}
    require(all(machine.get(k) == v for k, v in expected.items())
            and machine["repository"] == "wangchaozhuanyong/zhuangxiuwangzhan"
            and machine["workflow_path"] == ".github/workflows/content-publish-approved.yml"
            and type(machine.get("github_actor_id")) is int and machine["github_actor_id"] > 0
            and type(machine.get("run_id")) is int and machine["run_id"] > 0
            and type(machine.get("run_attempt")) is int and machine["run_attempt"] > 0
            and re.fullmatch(r"[0-9a-f]{40}", str(machine.get("workflow_sha", "")))
            and re.fullmatch(r"[0-9a-f]{40}", str(machine.get("main_sha", ""))),
            "exact original actor/run/attempt/workflow/source identity required")
    run, probe, receipt, payload = [doc(root, machine.get(k)) for k in
                                  ("run_snapshot", "identity_probe", "locked_preview", "payload_digest")]
    identity = probe.get("identity", {})
    require(run.get("id") == machine["run_id"] and run.get("run_attempt") == machine["run_attempt"]
            and run.get("actor", {}).get("id") == machine["github_actor_id"]
            and run.get("workflow_id") == machine["workflow_id"] and run.get("path") == machine["workflow_path"]
            and run.get("head_sha") == machine["main_sha"] and run.get("head_branch") == "main"
            and run.get("event") == "workflow_dispatch" and run.get("conclusion") == "success"
            and probe.get("ok") is True and probe.get("dry_run") is True and probe.get("performed_write") is False
            and all(identity.get(k) == machine[v] for k, v in {
                "runId": "run_id", "runAttempt": "run_attempt", "actorId": "github_actor_id",
                "repositoryId": "repository_id", "workflowRef": "workflow_ref", "workflowSha": "workflow_sha"}.items()),
            "reviewed server OIDC probe must bind the same original machine/run")
    require(receipt.get("task_id") == TASK and receipt.get("candidate_version") == item["candidate_version"]
            and receipt.get("action_id") == item["action_id"] and receipt.get("scope") == item["scope"]
            and receipt.get("operation") == item.get("operation", "publish") and receipt.get("http_status") == 200
            and receipt.get("dry_run") is True and receipt.get("performed_write") is False
            and receipt.get("external_writes") == 0 and receipt.get("row_unchanged_after_dry_run") is True
            and payload.get("task_id") == TASK and payload.get("operation") == item.get("operation", "publish")
            and payload.get("payload_sha256") == item["payload_sha256"]
            and payload.get("expected_updated_at") == accepted["row"]["raw_updated_at"],
            "reviewed machine must freeze this exact zero-write preview/payload/raw CAS")
    if "actual_machine_source" in accepted:
        actual_pin = pin(root, accepted["actual_machine_source"])
        facts = doc(root, actual_pin)
        require(machine.get("actual_machine_source") == actual_pin, "reviewed machine must bind latest V4 facts")
        if "source_bridge" in accepted:
            bridge = doc(root, accepted["source_bridge"])
            _v5_bridge_header(bridge)
            require(pin(root, machine.get("source_bridge")) == pin(root, accepted["source_bridge"])
                    and bridge.get("operation") == accepted.get("operation") == item.get("operation", "publish")
                    and machine["main_sha"] == machine["workflow_sha"] == bridge["current_commit"]
                    and pin(root, machine["run_snapshot"]) == pin(root, bridge.get("raw_machine_run"))
                    and run.get("status") == "completed"
                    and run.get("repository", {}).get("id") == machine["repository_id"]
                    and run.get("repository", {}).get("full_name") == machine["repository"],
                    "V5 publish/rollback source bridge must bind the actual completed full machine run")
        if item.get("operation", "publish") == "publish":
            records = [r for r in facts["records"] if r.get("slug") == accepted["row"]["slug"]]
            require(len(records) == 1, "one current V4 preview for this exact row required")
            current = records[0]
            if "source_bridge" in accepted:
                require(pin(root, machine["run_snapshot"]) == pin(root, current.get("full_original_gh_run"))
                        and current.get("run_id") == machine["run_id"]
                        and current.get("run_attempt") == machine["run_attempt"]
                        and current.get("conclusion") == "success"
                        and current.get("run_updated_at") == run.get("updated_at")
                        and current.get("checked_at") == receipt.get("checked_at")
                        and current.get("guard_rejected_changed_original_CAS") is False,
                        "V5 must bind exact completed original raw GH run and unchanged preview timestamps")
            require(current.get("identity") == identity
                    and pin(root, current.get("identity_probe")) == pin(root, machine["identity_probe"])
                    and current.get("protected_forward_receipt") == receipt
                    and current.get("actual_payload_sha256") == item["payload_sha256"]
                    and current.get("writes") == 0 and machine["workflow_sha"] == facts["machine_workflow_sha"]
                    and machine["main_sha"] == facts["machine_workflow_sha"],
                    "latest V4 run/attempt/probe/preview/payload cannot use historical V3 facts")
    stamp = w._parse_observed_at(run.get("updated_at"))
    now = dt.datetime.now(dt.timezone.utc)
    require(stamp is not None and now - dt.timedelta(minutes=30) <= stamp <= now,
            "reviewed run is stale or future; new run requires new independent proof")
    if "actual_machine_source" in accepted:
        previewed = w._parse_observed_at(receipt.get("checked_at"))
        require(previewed is not None and now - dt.timedelta(minutes=30) <= previewed <= stamp,
                "actual protected preview expired; metadata read cannot refresh its time")
    return machine


@strict
def validate_issuer_machine(root, target, accepted, run, probe, actor, payload, receipt):
    if accepted.get("operation") == "publish" and "publication_state" in target.get("bounded_row", {}):
        require(target["bounded_row"].get("publication_state") == "pending_save"
                and accepted.get("row") == target["bounded_row"], "Saved effect cannot enter original issuer machine admission")
    action = target["action_id"] if accepted["operation"] == "publish" else f"rollback-{VERSION}"
    matches = [item for item in accepted.get("preflights", []) if item.get("action_id") == action
               and item.get("scope") == target["scope"]]
    require(len(matches) == 1, "one reviewed row machine preflight required")
    machine = validate_machine(root, matches[0], accepted)
    require(actor == machine["github_actor_id"] and run == doc(root, machine["run_snapshot"])
            and probe == doc(root, machine["identity_probe"])
            and payload == doc(root, machine["payload_digest"])
            and receipt == doc(root, machine["locked_preview"]),
            "issuer CLI/download cannot replace the A2-frozen actor/run/attempt/workflow/source")
    return machine


def _website_bytes(value):
    """Read only the original website's frozen T3 deployment evidence."""
    require(isinstance(value, dict), "frozen original website source pin required")
    path = Path(str(value.get("path", "")))
    require(path.is_absolute() and path.resolve().is_relative_to((WEBSITE / DEPLOYMENT_EVIDENCE).resolve()),
            "website evidence outside original T3 deployment package forbidden")
    raw = path.read_bytes()
    require(type(value.get("size", value.get("bytes"))) is int
            and len(raw) == value.get("size", value.get("bytes"))
            and hashlib.sha256(raw).hexdigest() == value.get("sha256"), "original deployed website source bytes changed")
    return raw


def _website_json(value):
    def unique(pairs):
        result = {}
        for key, item in pairs:
            require(key not in result, "unambiguous website source JSON required")
            result[key] = item
        return result
    return json.loads(_website_bytes(value), object_pairs_hook=unique)


def _git_source(commit, path):
    require(re.fullmatch(r"[0-9a-f]{40}", str(commit)) is not None, "exact source commit required")
    try:
        result = subprocess.run(["git", "show", f"{commit}:{path}"], cwd=WEBSITE,
                                capture_output=True, timeout=15, check=False)
    except subprocess.TimeoutExpired as error:
        raise w.WorkflowError("bounded T3 CMS: source commit read timed out") from error
    require(result.returncode == 0, "actual website commit source unavailable")
    return result.stdout


@strict
def source_coherence(root, source, deployment, machine, accepted):
    """Compare original deployment bytes with the actual run commit, never a SHA alias."""
    proof = doc(root, source.get("source_coherence"))
    if proof.get("schema") == V5_SOURCE_SCHEMA:
        return _v5_source_bridge(root, source, deployment, machine, accepted, proof)
    production, main = source["production_sha"], machine["main_sha"]
    require(proof.get("schema") == "A2_owned_T3_v4_workflow_commit_runtime_digest_equivalence_preliminary_v1"
            and proof.get("task_id") == TASK and proof.get("formal_T3_PASS") is False
            and proof.get("actual_machine_main_sha") == main
            and proof.get("actual_machine_workflow_sha") == machine["workflow_sha"]
            and proof.get("actual_deployed_runtime_sha") == production
            and type(proof.get("actual_function_version")) is int
            and type(proof.get("actual_deployment_run")) is int
            and source.get("function_version") == deployment.get("function_version") == proof["actual_function_version"]
            and deployment.get("deployment_run_id") == proof["actual_deployment_run"]
            and deployment.get("original_deployment_source_proof") == proof.get("actual_deployment_source_proof"),
            "separate actual workflow/deployment source proof required")
    if "actual_machine_source" in accepted:
        facts = doc(root, accepted["actual_machine_source"])
        producer = doc(root, accepted.get("current_producer"))
        require(_machine_sources(root, producer)["actual_machine_source"] == pin(root, accepted["actual_machine_source"]),
                "coherence must belong to latest reviewed producer")
        source_facts = doc(root, producer["evidence"]["source_and_original_backups"])
        require(facts["machine_workflow_sha"] == main == machine["workflow_sha"]
                and facts["native_frontend_loaded_sha"] == production
                and source_facts.get("task_id") == TASK and source_facts.get("content_candidate_version") == VERSION
                and source_facts.get("source_candidate_version") == WEBSITE_SOURCE_VERSION
                and source_facts.get("production_website_sha") == production
                and pin(WEBSITE, source_facts["deployment_proof"]) == pin(WEBSITE, proof["actual_deployment_source_proof"]),
                "source proof must bind current V4 workflow and deployed runtime separately")
    original = _website_json(proof["actual_deployment_source_proof"])
    require(original.get("task_id") == TASK and original.get("content_candidate_version") == VERSION
            and original.get("source_candidate_version") == WEBSITE_SOURCE_VERSION
            and original.get("status") == "PASS_ACTUAL_PRODUCTION_EDGE_SOURCE_AND_RECOVERY_BACKUP"
            and original.get("production_website_sha") == production
            and original.get("run_id") == proof["actual_deployment_run"]
            and original.get("actual_function", {}).get("name") == "content-publish"
            and original["actual_function"].get("status") == "ACTIVE"
            and original["actual_function"].get("after_version") == original["actual_function"].get("after_download_version")
                == proof["actual_function_version"]
            and pin(WEBSITE, original["actual_readback"]["manifest"]) == pin(WEBSITE, proof["actual_deployed_runtime_manifest"]),
            "original actual deployed version77/source provenance required")
    run = _website_json(original["run_proof"])["run"]
    require(run.get("id") == proof["actual_deployment_run"] and run.get("head_sha") == production
            and run.get("status") == "completed" and run.get("conclusion") == "success"
            and run.get("event") == "workflow_dispatch", "original completed deployment run required")
    for name in ("functions-after.json", "functions-after-download.json"):
        matches = [p for p in original["artifact_metadata_pins"] if p["path"].endswith("/" + name)]
        require(len(matches) == 1, "actual deployment metadata snapshots required")
        functions = _website_json(matches[0])
        require(isinstance(functions, list) and len([f for f in functions if f.get("name") == "content-publish"
                and f.get("version") == proof["actual_function_version"] and f.get("status") == "ACTIVE"]) == 1,
                "actual deployed function version differs")
    manifest = _website_json(proof["actual_deployed_runtime_manifest"])
    files, mapping = manifest.get("files", []), proof.get("runtime_file_map", [])
    closure_digest = hashlib.sha256(json.dumps(files, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
    require(manifest.get("schema") == "content-publish-runtime-source/v1"
            and manifest.get("entrypoint") == "content-publish/index.ts"
            and len(files) == len(mapping) == proof.get("actual_runtime_source_closure_file_count") == 21
            and len({f.get("path") for f in files}) == 21
            and len({f.get("runtime_path") for f in mapping}) == 21
            and {f.get("path") for f in files} == {f.get("runtime_path") for f in mapping}
            and closure_digest == proof.get("actual_runtime_source_closure_digest") == original["actual_readback"]["source_sha256"],
            "complete exact deployed21 runtime closure required")
    readback = WEBSITE / DEPLOYMENT_EVIDENCE / f"production-r3-run-{run['id']}-artifacts/readback/edge-after/supabase/functions"
    require(Path(original["actual_readback"]["root"]).resolve() == readback.resolve(), "original runtime download root required")
    for entry in files:
        path = entry["path"]
        require(re.fullmatch(r"(?:_shared|content-publish)/[a-zA-Z0-9_-]+\.ts", path) is not None,
                "exact runtime source path required")
        mapped = next(m for m in mapping if m["runtime_path"] == path)
        require(mapped.get("git_path") == "supabase/functions/" + path and mapped.get("workflow_commit") == main
                and mapped.get("workflow_commit_sha256") == mapped.get("actual_deployed_v77_sha256") == entry["sha256"]
                and mapped.get("workflow_commit_bytes") == mapped.get("actual_deployed_v77_bytes") == entry["bytes"],
                "runtime source map digest differs")
        raw = _website_bytes({"path": str(readback / path), "sha256": entry["sha256"], "size": entry["bytes"]})
        require(_git_source(main, mapped["git_path"]) == _git_source(production, mapped["git_path"]) == raw,
                "actual workflow/deployed runtime byte coherence failed")
    workflow_map = proof.get("workflow_and_CLI_source_map", [])
    require(len(workflow_map) == 3 and {p.get("path") for p in workflow_map} == set(WORKFLOW_CLI),
            "original protected workflow and exact CLI/target closure required")
    for mapped in workflow_map:
        approved = [p for p in original["source_pins"] if p.get("path") == mapped["path"]]
        require(len(approved) == 1 and mapped.get("workflow_commit") == main
                and mapped.get("workflow_commit_sha256") == mapped.get("approved_5237_source_sha256") == approved[0]["sha256"]
                and mapped.get("workflow_commit_bytes") == mapped.get("approved_5237_source_bytes") == approved[0]["bytes"],
                "original protected workflow/CLI source map differs")
        raw = _git_source(main, mapped["path"])
        require(raw == _git_source(production, mapped["path"])
                and hashlib.sha256(raw).hexdigest() == approved[0]["sha256"] and len(raw) == approved[0]["bytes"],
                "actual workflow/CLI/target source bytes differ")
    for runtime in ("content-publish/service.ts", "_shared/managed-targets.ts"):
        entry = next(f for f in files if f["path"] == runtime)
        require(any(p.get("path", "").endswith("/" + runtime.rsplit("/", 1)[-1])
                and p.get("sha256") == entry["sha256"] and p.get("size") == entry["bytes"]
                for p in source.get("source_snapshots", [])), "recovery snapshots must match actual deployed restore implementation")
    return pin(root, source["source_coherence"])


@strict
def preflight(root, snapshot, action, action_class, scope, department):
    require(exact_tuple(snapshot.get("task_id"), action, scope, department, action_class), "exact native row cannot broaden project authority")
    operation = "rollback" if action == f"rollback-{VERSION}" else "publish"
    target = next(t for t in targets(root).values() if t["scope"] == scope
                  and (operation == "rollback" or t["action_id"] == action))
    accepted = acceptance(root, snapshot, target, operation)
    expected = {"task_id": TASK, "action_id": action, "action_class": action_class, "scope": scope,
                "department": department, "candidate_version": accepted["candidate_version"], "record_id": target["record_id"]}
    items = [item for item in accepted["preflights"] if isinstance(item, dict) and all(item.get(k) == v for k, v in expected.items())]
    require(len(items) == 1, "one exact row production self-check still required")
    item = items[0]
    require(item.get("operation", "publish") == operation, "distinct reviewed production operation required")
    require(item.get("risk_level") == "R3" and w.SHA256_PATTERN.fullmatch(str(item.get("payload_sha256", ""))) is not None,
            "exact production risk/payload required")
    machine = validate_machine(root, item, accepted)
    facts, check, rollback = [doc(root, item.get(k)) for k in ("facts", "self_check", "rollback")]
    require(pin(root, item.get("backup")) == accepted["row"]["backup"], "original current native backup required")
    require(all(check.get(k) == v and facts.get(k) == v and rollback.get(k) == v for k, v in expected.items())
            and check.get("status") == "PASS" and check.get("payload_sha256") == item["payload_sha256"]
            and facts.get("raw_updated_at") == accepted["row"]["raw_updated_at"]
            and facts.get("native_version") == accepted["row"]["native_version"]
            and facts.get("baseline_sha256") == accepted["row"]["baseline_sha256"]
            and facts.get("desired_sha256") == accepted["row"]["desired_sha256"], "exact successful row CAS/self-check required")
    observed = w._parse_observed_at(facts.get("checked_at"))
    now = dt.datetime.now(dt.timezone.utc)
    require(observed is not None and now - dt.timedelta(minutes=30) <= observed <= now,
            "fresh authenticated native raw CAS required")
    require(check.get("protected_preview_zero_write") is True and check.get("production_endpoint_verified") is True
            and check.get("actor_workflow_run_verified") is True and check.get("single_use_state") == "unused",
            "real endpoint/actor/workflow/run/unused permit preflight required")
    require(rollback.get("rollback_execution_ready") is True
            and rollback.get("binding_strategy") == "fresh_saved_CAS_after_exact_Save"
            and rollback.get("backup") == accepted["row"]["backup"]
            and rollback.get("candidate") == accepted["row"]["candidate"], "original exact backup and executable recovery plan required")
    if operation == "publish":
        # The protected restore dry-run correctly rejects the old baseline.
        # Successful rollback preview requires Saved CAS, so it is a later gate.
        before = doc(root, accepted["row"]["backup"])
        require(rollback.get("stage") == "before_Save"
                and rollback.get("restore_fields_sha256") == digest({k: before[k] for k in target["changed_fields"]})
                and rollback.get("required_after_Save") == ["fresh_SavedCAS", "completed_publish_permit_and_run",
                    "successful_protected_rollback_preview", "independent_rollback_acceptance", "new_single_use_rollback_permit"],
                "before-Save plan must retain every later SavedCAS/review/permit gate")
        source_pin = rollback.get("source_verification")
        require(isinstance(source_pin, dict) and source_pin in check.get("evidence", []), "reviewed deployed recovery source proof required")
        source = doc(root, source_pin)
        require(all(source.get(k) == v for k, v in expected.items())
                and source.get("status") == "DEPLOYED_RESTORE_IMPLEMENTATION_VERIFIED"
                and source.get("repository") == "wangchaozhuanyong/zhuangxiuwangzhan"
                and re.fullmatch(r"[0-9a-f]{40}", str(source.get("production_sha", "")))
                and source.get("saved_CAS_required") is True and source.get("protected_route") == "content-publish"
                and source.get("successful_rollback_preview_performed") is False,
                "deployed original recovery implementation required; no fabricated pre-Save recovery PASS")
        deployment = doc(root, source.get("deployment_record"))
        require(deployment.get("status") == "DEPLOYED" and deployment.get("actual_execution") is True
                and deployment.get("repository") == source["repository"]
                and deployment.get("production_sha") == source["production_sha"], "exact actual deployment/source version required")
        snapshots = source.get("source_snapshots", [])
        require(isinstance(snapshots, list) and len(snapshots) >= 2
                and {p.get("path", "").rsplit("/", 1)[-1] for p in snapshots} >= {"service.ts", "managed-targets.ts"}
                and deployment.get("source_snapshots") == snapshots,
                "frozen deployed restore source snapshots must belong to the same actual deployment")
        for frozen in snapshots:
            pin(root, frozen)
        if "actual_machine_source" in accepted or source["production_sha"] != machine["main_sha"]:
            require(source.get("source_coherence") in check.get("evidence", [])
                    and isinstance(source.get("source_coherence"), dict),
                    "reviewed cross-commit deployed recovery source coherence required")
            source_coherence(root, source, deployment, machine, accepted)
        if rollback.get("guard_evidence") is not None:
            guard = doc(root, rollback["guard_evidence"])
            require(guard.get("http_status") == 409 and guard.get("performed_write") is False
                    and guard.get("external_writes") == 0 and guard.get("expected_baseline_rejection") is True
                    and guard.get("successful_rollback_preview_performed") is False,
                    "a pre-Save 409 proves the baseline guard, never a recovery PASS")
    else:
        require(rollback.get("stage") == "after_Save"
                and rollback.get("completed_parent") == accepted["completed_parent"]
                and rollback.get("saved_record") == accepted["saved_record"], "actual after-Save recovery binding required")
        # validate_machine has already matched the successful rollback preview,
        # fresh Saved CAS, exact actor/run/source and independently reviewed pins.
    return {**item, "authorized_project_scope": SCOPE, "candidate_acceptance_record_id": accepted["candidate_acceptance_record_id"]}


@strict
def decision(root, value, target, payload_sha256, accepted, now):
    require(accepted.get("acceptance_model") == MODEL, "bounded acceptance required")
    expected = {"department": ROLE, "assistant_chat_task_id": w.department_registry(root)[ROLE]["chat_binding"]["task_id"],
        "decision": "EXECUTE_AUTHORIZED_ACTION", "operation": accepted["operation"], "task_id": TASK,
        "action_id": target["action_id"] if accepted["operation"] == "publish" else f"rollback-{VERSION}", "action_class": "cms_write", "scope": target["scope"],
        "candidate_version": accepted["candidate_version"], "record_id": target["record_id"], "payload_sha256": payload_sha256,
        "candidate_acceptance_record_id": accepted["candidate_acceptance_record_id"],
        "controller_decision_record_id": accepted["candidate_acceptance_record_id"],
        "review_outbox": accepted["review_outbox"], "review_plan": accepted["review_plan"],
        "authorization_pin": accepted["authorization_pin"]}
    verified_preflight = preflight(root, w.read_json(w.snapshot_path(root, TASK)), expected["action_id"],
                                  "cms_write", target["scope"], PRODUCER)
    require(verified_preflight.get("payload_sha256") == payload_sha256, "routine decision cannot replace reviewed row payload")
    expected["machine_identity"] = verified_preflight["machine_identity"]
    require(all(value.get(k) == v for k, v in expected.items()) and value.get("decision_id")
            and not value.get("qa_receipt_id"), "exact routine continue; no invented QA receipt")
    fresh = acceptance(root, w.read_json(w.snapshot_path(root, TASK)), target, accepted["operation"])
    require(fresh == accepted, "candidate acceptance changed before production decision")
    stamp = w._parse_observed_at(value.get("decided_at"))
    row = next(r for r in w._result_handoff_rows(root, TASK) if r["record_id"] == accepted["candidate_acceptance_record_id"])
    continued = w._parse_observed_at(row["created_at"])
    require(stamp is not None and continued <= stamp <= now and now - dt.timedelta(hours=24) <= stamp,
            "fresh original continue decision required")
    return value



WEEKLY_KEY_REPAIR_TASK = WEEKLY_SOURCE_TASK
WEEKLY_KEY_REPAIR_SCOPE = WEEKLY_SOURCE_SCOPE
WEEKLY_KEY_REPAIR_VERSION = "weekly-native-structured-create-response-compatibility-candidate-v4-20261011"
WEEKLY_KEY_REPAIR_PATHS = {"tools/workflow_control.py", "tools/qa_review_plan.py", "tools/paid_three_page_bounded_cms.py"}
WEEKLY_KEY_REPAIR_CONTEXT_PATH = "logs/handoffs/2026-10-11-weekly-native-structured-create-response-compatibility-v1/developer-v4/rollback/source_review_context.py"
WEEKLY_KEY_REPAIR_CONTEXT_BYTES = {"sha256":"8c80f0db2981a7d5f344002c5b8db25626259db9fc09c055827f714d924c9728","size":90136}


# The original kitchen EN2 dependency is one distinct, registered production
# identity. These frozen preparation bytes do not establish a current Save CAS.
EN2_TASK = "fc-20261011-english-kitchen-actual-publication-goal-v1"
EN2_ACTION = "save-kitchen-english-two-fields-v1"
EN2_VERSION = "publishing-english-kitchen-en2-actual-publication-v1-20261011"
EN2_SCOPE = "cms:services:kitchen:english-two-fields:publication:v1"
EN2_RECORD = "ce4156db-9034-42c8-ba29-b35724ea7d6d"
EN2_FIELDS = ("title_en", "excerpt_en")
EN2_PUBLISHER = "example-native-f4ba16119c32b000"
EN2_CANDIDATE = {"path": "drafts/publishing/fc-20261011-english-kitchen-actual-publication-goal-v1/publishing-production-input-candidate-v1.json",
                 "sha256": "fcc055acb530d2debdb86469321b61c28c124200c7d045155798f575b55ed7c8", "size": 12221}
EN2_HANDOFF = {"path": "drafts/publishing/fc-20261011-english-kitchen-actual-publication-goal-v1/production-input-exact-original-dependency-handoff-v1.json",
               "sha256": "bdb4a4be0ac630bf8d20b12db8934e014cb087fa29771d29095bae1f065c856d", "size": 2738}
EN2_BINDINGS = {"path": "drafts/publishing/fc-20261011-english-kitchen-actual-publication-goal-v1/actual-production-source-bindings-v1.json",
                "sha256": "99fbe36b5cfe68fe1aed68f5edcbb7ec1067b7827005c0b27dd1cca52dd256a5", "size": 15020}
EN2_PREPARATION_PASS = {"path": "logs/handoffs/2026-10-11-qualified-native-handoff-envelope-recovery-v1/assistant2-independent-review/post-adoption-real-PUB-preparation-pilot-readonly-preparation-v1/ROOT-actual-installed-V3-original-PUB-preparation-pilot-v1/ROOT-ACTUAL-original-TP-full7-preparation-only-independent-PASS-outbox-v1.json",
                        "sha256": "31af2885ba30150802092d6f0903d91a6121c04ccda4445f2b77efd26d8d1aa6", "size": 14847}
EN2_AUTH = {"path": "logs/handoffs/2026-10-10-owner-direct-paid/assistant2-owned/english-kitchen-CMS-readiness-independent-lane/EN2-exact-three-original-target-messages-APPROVED-v1/actual-human-EN2-three-original-continuations-authorization-selected-v1.json",
            "sha256": "060e68362fe56228838d410fb35d089a8f5df5c1be1e2f1ebae46cf4832bae7f", "size": 2208}


def english_kitchen_en2_targets(root):
    """Read the one frozen EN2 registration; never infer a new field or tuple."""
    root = Path(root).resolve()
    candidate, handoff, bindings = (doc(root, item) for item in
                                    (EN2_CANDIDATE, EN2_HANDOFF, EN2_BINDINGS))
    preparation = doc(root, EN2_PREPARATION_PASS)
    pin(root, EN2_AUTH)
    require(preparation.get("status") == "qa_pass"
            and preparation.get("qa_verdict") == "pass"
            and preparation.get("department") == "operations-assistant-2"
            and preparation.get("task_id") == "fc-20261011-english-kitchen-en2-current-row-preparation-v1",
            "original seven-check preparation acceptance required")
    tuple_value = {"Save_task_id": EN2_TASK, "Save_action_id": EN2_ACTION,
                   "Save_action_class": "cms_write", "Save_candidate_version": EN2_VERSION,
                   "Save_scope": EN2_SCOPE, "Save_department": "publishing",
                   "fixed_chat_task_id": EN2_PUBLISHER}
    require(all(candidate.get("production_tuple", {}).get(k) == v
                and handoff.get("production_tuple", {}).get(k) == v
                and bindings.get("production_tuple", {}).get(k) == v
                for k, v in tuple_value.items()), "one exact original EN2 Save tuple required")
    require(candidate.get("task_id") == handoff.get("task_id") == bindings.get("task_id") == EN2_TASK
            and candidate.get("action_id") == EN2_ACTION
            and candidate.get("candidate_version") == bindings.get("candidate_version") == EN2_VERSION
            and candidate.get("scope") == EN2_SCOPE
            and candidate.get("department") == "publishing"
            and candidate.get("fixed_chat_task_id") == EN2_PUBLISHER
            and handoff.get("publisher_actual_bound_candidate") == EN2_CANDIDATE
            and handoff.get("source_bindings") == EN2_BINDINGS
            and candidate.get("source_bindings") == EN2_BINDINGS,
            "frozen publisher, handoff, binding or human authority differs")
    pin(root, bindings["actual_human_authorization_pin"])
    require(candidate.get("production_write_executed") is False
            and candidate.get("new_permit") == 0 and candidate.get("Save") == 0
            and handoff.get("new_permit") == 0 and handoff.get("Save") == 0,
            "registration input must remain preparation only")

    target = candidate.get("target", {})
    source = doc(root, candidate["source_frozen_candidate"])
    require((target.get("table"), target.get("record_id"), target.get("slug"), target.get("content_type"))
            == ("services", EN2_RECORD, "kitchen", "service")
            and candidate.get("changed_fields") == target.get("changed_fields") == list(EN2_FIELDS)
            and set(candidate.get("desired_fields", {})) == set(EN2_FIELDS)
            and target.get("desired_fields") == candidate["desired_fields"]
            and target.get("original_Paid_candidate_pin") == candidate["source_frozen_candidate"]
            and source.get("target", {}).get("record_id") == EN2_RECORD
            and source.get("target", {}).get("table") == "services"
            and [x.get("field") for x in source.get("exact_changes", [])] == list(EN2_FIELDS)
            and all(x.get("after") == candidate["desired_fields"][x["field"]]
                    for x in source["exact_changes"]), "original Paid EN2 content or exact target differs")

    before = doc(root, candidate["native_current_record"])
    require(doc(root, candidate["backup"]) == before
            and candidate["backup"]["sha256"] == candidate["native_current_record"]["sha256"],
            "complete original native backup required")
    require(before.get("id") == EN2_RECORD and before.get("slug") == "kitchen"
            and before.get("status") == "published" and type(before.get("version")) is int
            and before["version"] == candidate.get("expected_version")
            and before.get("updated_at") == candidate.get("expected_updated_at")
            and set(before) == set(candidate.get("baseline_projection_fields", []))
            and len(before) == 30, "complete 30-field baseline and raw CAS required")
    desired = dict(before, **candidate["desired_fields"])
    require({k for k in before if before[k] != desired[k]} == set(EN2_FIELDS)
            and all(before[x["field"]] == x.get("before") for x in source["exact_changes"]),
            "only the original two English fields may change")
    projections = (("baseline_projection", before, "baseline_fields_sha256"),
                   ("desired_full_projection", desired, "desired_full_record_fields_sha256"),
                   ("only_write_projection", candidate["desired_fields"], "desired_fields_sha256"),
                   ("retained_projection", {k: before[k] for k in candidate["retained_projection_fields"]}, "retained_fields_sha256"),
                   ("retained_including_metadata_projection", {k: before[k] for k in candidate["retained_including_metadata_projection_fields"]}, "retained_including_metadata_fields_sha256"))
    for name, expected, hash_key in projections:
        require(doc(root, candidate[name]) == expected and digest(expected) == candidate.get(hash_key),
                "EN2 full-row projection, retention or digest differs: " + name)
    require(set(candidate["retained_projection_fields"]) == set(before) - set(EN2_FIELDS) - {"updated_at", "version"}
            and set(candidate["retained_including_metadata_projection_fields"]) == set(before) - set(EN2_FIELDS)
            and digest({k: before[k] for k in EN2_FIELDS}) == candidate.get("rollback_fields_sha256"),
            "retained fields or rollback field digest differs")
    difference = doc(root, candidate["two_field_diff"])
    require(difference.get("record_id") == EN2_RECORD
            and difference.get("before_cas") == {"version": before["version"], "updated_at": before["updated_at"]}
            and [(x.get("field"), x.get("before"), x.get("after")) for x in difference.get("changes", [])]
                == [(x["field"], before[x["field"]], desired[x["field"]]) for x in source["exact_changes"]],
            "frozen EN2 two-field diff or source CAS differs")
    recovery = doc(root, candidate["rollback"])
    bound_recovery = doc(root, candidate["bound_production_recovery_input"])
    request = doc(root, candidate["protected_dry_run_request_prepared"])
    require(recovery.get("record_id") == EN2_RECORD
            and recovery.get("changed_fields") == list(EN2_FIELDS)
            and recovery.get("restore_fields") == {k: before[k] for k in EN2_FIELDS}
            and bound_recovery.get("forward_production_tuple") == candidate["production_tuple"]
            and bound_recovery.get("record_identity") == target
            and bound_recovery.get("restore_fields") == {k: before[k] for k in EN2_FIELDS}
            and bound_recovery.get("before_full_backup") == candidate["backup"]
            and bound_recovery.get("production_recovery_executable") is False
            and request.get("contentType") == "service" and request.get("mode") == "dry-run"
            and request.get("expectedUpdatedAt") == before["updated_at"]
            and request.get("record") == desired
            and request.get("managedCandidate") == {"taskId": EN2_TASK, "actionId": EN2_ACTION,
                "operation": "publish", "scope": EN2_SCOPE, "candidateVersion": EN2_VERSION},
            "frozen dry-run and recovery must bind only the exact row and two fields")
    pin(root, candidate["offline_recovery_guard"])
    return {"english-kitchen-en2-exact-v1": {
        "task_id": EN2_TASK, "action_id": EN2_ACTION, "candidate_version": EN2_VERSION,
        "scope": EN2_SCOPE, "table": "services", "record_id": EN2_RECORD,
        "slug": "kitchen", "content_type": "service", "changed_fields": list(EN2_FIELDS),
        "execution_owner": "publishing", "execution_thread_id": EN2_PUBLISHER,
        "candidate_shape": "english_kitchen_en2_exact", "candidate": (EN2_CANDIDATE["path"], EN2_CANDIDATE["sha256"]),
        "source_frozen_candidate": (candidate["source_frozen_candidate"]["path"], candidate["source_frozen_candidate"]["sha256"]),
        "rollback": (candidate["backup"]["path"], candidate["backup"]["sha256"]),
        "rollback_package": candidate["rollback"],
        "bound_recovery_input": candidate["bound_production_recovery_input"],
        "baseline_projection_fields": candidate["baseline_projection_fields"],
        "baseline_fields_sha256": candidate["baseline_fields_sha256"],
        "desired_fields_sha256": candidate["desired_fields_sha256"],
        "retained_fields_sha256": candidate["retained_fields_sha256"],
        "expected_updated_at": before["updated_at"], "observed_version": before["version"],
        "rollback_allowed": False, "registration_only": True,
    }}


def validate_english_kitchen_en2_candidate(root, candidate, target):
    exact = english_kitchen_en2_targets(root)["english-kitchen-en2-exact-v1"]
    require(target == exact and candidate == doc(root, EN2_CANDIDATE),
            "one unchanged frozen original EN2 candidate and registered target required")


# The two original materials are source candidates only until the publisher
# freezes its own exact production goal. A website tuple proposal and the old
# read-only row input cannot create a CMS Save action.
MATERIAL_SOURCE_TASK = "fc-20261014-two-original-materials-exact-registration-source-v1"
MATERIAL_PUBLICATION_TASK = "fc-20261014-two-original-materials-exact-body-publication-v1"
MATERIAL_PARENT = "fc-20261010-original-cms-materials-execution-recovery-v2"
MATERIAL_MERGE_VERSION = "seo1-material-merge-and-warehouse-release-handoff-v1-20261010"
MATERIAL_FIELDS = ("content_en", "content_zh")
MATERIAL_BASE = ("drafts/publishing/fc-20261010-publishing-current-native-input-and-original-preview-v1/"
                 "continuation-current-materials-20261014-v2/")
MATERIAL_INPUT = {
    "path": MATERIAL_BASE + "two-material-current-original-dependency-input.json",
    "sha256": "3828dcefcb382409f095b28a85ac660b7e02c55c14d65e67cfbaa12d4460bf13",
    "size": 9623,
}
MATERIAL_AUTH = {
    "path": ("logs/handoffs/2026-10-14-complete-goal-continuity-v1/"
             "assistant2-CMS-business-continuation-v1/"
             "actual-human-two-original-materials-channel-authorization-selected-v1.json"),
    "sha256": "25fcce1639899c803661e70c6d3befadcfea159aab7a885635824e0579bbc3f4",
    "size": 2116,
}
MATERIAL_WEBSITE_RETURN = {
    "path": ("logs/handoffs/2026-10-14-complete-goal-continuity-v1/"
             "assistant2-CMS-business-continuation-v1/"
             "original-website-two-materials-v2-returned-source-candidate.json"),
    "sha256": "864d47ac8347b9004151ad9f851ca7739cd9191ad7f1d5488697269100d90fe5",
    "size": 11680,
}
MATERIAL_EXPECTED_SOURCE = {
    "path": ("logs/handoffs/2026-10-15-two-materials-readiness-continuation-v1/"
             "A2-independent/readiness-consumer-review/"
             "actual-b5f54dea-canonical-runtime-manifest-readonly-v1.json"),
    "sha256": "aa9e40fef963a4f4b93be5bbd15ba9f24bfe047450ca9db0adfb910cf06ee2e2",
    "size": 3932,
}
MATERIAL_ROWS = (
    ("sintered-stone-grey", "00db44f6-c26a-4140-b12d-601d9fbaedf7",
     "save-sintered-stone-grey-bilingual-body-v1",
     "publishing-sintered-stone-grey-exact-bilingual-body-v1-20261014"),
    ("solid-surface-warm-white", "1bce8dd6-26b5-443b-990b-7e7d6bc9147a",
     "save-solid-surface-warm-white-bilingual-body-v1",
     "publishing-solid-surface-warm-white-exact-bilingual-body-v1-20261014"),
)


def _material_tuple(slug, record_id, action, version):
    return (MATERIAL_PUBLICATION_TASK, action, version,
            f"company.example:materials/{record_id}:content_en,content_zh",
            "publishing", "cms_write")


def validate_two_material_row(before, candidate, publisher, slug, record_id):
    """Check the actual 46-field source without treating its CAS as current."""
    require(isinstance(before, dict) and isinstance(candidate, dict)
            and isinstance(publisher, dict), "two material source objects required")
    require(len(before) == 46 and set(candidate) == set(before)
            and before.get("id") == candidate.get("id") == publisher.get("record_id") == record_id
            and before.get("slug") == candidate.get("slug") == publisher.get("slug") == slug
            and before.get("status") == candidate.get("status") == "published"
            and type(before.get("version")) is int
            and before.get("version") == candidate.get("version") == publisher.get("current_version")
            and before.get("updated_at") == candidate.get("updated_at") == publisher.get("current_raw_updated_at")
            and re.fullmatch(r".*\.\d{6}\+00:00", str(before["updated_at"])),
            "exact material identity, 46 fields and raw microsecond CAS required")
    changed = {key for key in before if before[key] != candidate[key]}
    require(changed == set(MATERIAL_FIELDS)
            and set(publisher.get("exact_two_body_patch", {})) == set(MATERIAL_FIELDS)
            and {key: candidate[key] for key in MATERIAL_FIELDS} == publisher["exact_two_body_patch"]
            and publisher.get("changed_fields") in
                (list(MATERIAL_FIELDS), list(reversed(MATERIAL_FIELDS)))
            and set(publisher.get("retained_field_names", [])) == set(before) - set(MATERIAL_FIELDS)
            and publisher.get("retained_field_count") == 44
            and publisher.get("retained_values") ==
                {key: before[key] for key in before if key not in MATERIAL_FIELDS}
            and publisher.get("Save") == publisher.get("protected_preview") == 0
            and publisher.get("fresh_row_before_future_preview_or_Save_required") is True,
            "only two original material bodies may differ; old input is not a Save")


@strict
def two_original_material_source_contract(root):
    """Reviewable source facts; this never registers a production target."""
    root = Path(root).resolve()
    summary = doc(root, MATERIAL_INPUT)
    authority = doc(root, MATERIAL_AUTH)
    website = doc(root, MATERIAL_WEBSITE_RETURN)
    pin(root, authority["actual_native_source"])
    pin(root, authority["reviewable_specification"])
    require(summary.get("parent_task_id") == MATERIAL_PARENT
            and summary.get("merge_candidate_version") == MATERIAL_MERGE_VERSION
            and summary.get("Save") == 0 and summary.get("parent_goal_closed") is False
            and authority.get("source_thread_id") == "example-native-2ab501c514875e3b"
            and authority.get("message", {}).get("type") == "userMessage"
            and "允许这两项最小补齐及部门系统精确采用"
                in authority["message"]["content"][0]["text"]
            and website.get("source_candidate_head") == "b5f54dea9d6277b51daab2e0c0e23fe65bdac46a"
            and website.get("production_goal_registered") is False
            and website.get("issuer_registration_adopted") is False
            and website.get("actual_Save") == 0,
            "actual original human authority, source return and no-Save status required")
    records = summary.get("records")
    require(isinstance(records, list) and len(records) == len(MATERIAL_ROWS)
            and {x.get("record_id") for x in records}
                == {item[1] for item in MATERIAL_ROWS}
            and isinstance(website.get("proposed_production_bindings"), list)
            and len(website["proposed_production_bindings"]) == len(MATERIAL_ROWS),
            "exactly the two original publisher rows required")
    result = {}
    for slug, record_id, action, version in MATERIAL_ROWS:
        source = next(item for item in records if item.get("record_id") == record_id)
        publisher_path = MATERIAL_BASE + slug + ".current-two-field-publisher-input.json"
        publisher = w.read_json(w.safe_path(root, publisher_path))
        require(source.get("slug") == slug and publisher.get("current_full_record") == source.get("current_full_record")
                and publisher.get("snapshot_backup") == source.get("snapshot_backup")
                and publisher.get("original_candidate") == source.get("original_candidate"),
                "original publisher and source candidate pins differ")
        before = doc(root, source["current_full_record"])
        backup = doc(root, source["snapshot_backup"])
        candidate = doc(root, source["original_candidate"])
        require(before == backup and source["current_full_record"]["sha256"] == source["snapshot_backup"]["sha256"]
                and source.get("current_version") == before.get("version")
                and source.get("current_raw_updated_at") == before.get("updated_at")
                and source.get("current_full46_equal_frozen_before_record") is True
                and source.get("fresh_row_before_future_preview_or_Save_required") is True,
                "frozen full-row material source and backup required")
        validate_two_material_row(before, candidate, publisher, slug, record_id)
        proposal = [item for item in website["proposed_production_bindings"]
                    if item.get("recordId") == record_id]
        require(len(proposal) == 1, "one exact website proposal per material required")
        proposal = proposal[0]
        task, proposed_action, proposed_version, scope, owner, action_class = (
            _material_tuple(slug, record_id, action, version))
        require((proposal.get("taskId"), proposal.get("actionId"),
                 proposal.get("candidateVersion"), proposal.get("scope"))
                == (task, proposed_action, proposed_version, scope)
                and (proposal.get("recordId"), proposal.get("slug"),
                     proposal.get("table"), proposal.get("contentType"))
                    == (record_id, slug, "materials", "material")
                and proposal.get("actionClass") == action_class
                and proposal.get("changedFields") == list(MATERIAL_FIELDS)
                and proposal.get("expectedUpdatedAt") == before["updated_at"]
                and proposal.get("expectedVersion") == before["version"]
                and proposal.get("baselineFieldsSha256") == digest(before)
                and proposal.get("desiredFieldsSha256") ==
                    digest({field: candidate[field] for field in MATERIAL_FIELDS})
                and proposal.get("retainedFieldsSha256") ==
                    digest({key: before[key] for key in before
                            if key not in {*MATERIAL_FIELDS, "updated_at", "version"}})
                and proposal.get("rollbackFieldsSha256") ==
                    digest({field: before[field] for field in MATERIAL_FIELDS}),
                "website tuple proposal must match the original publisher bytes exactly")
        request = doc(root, source["prepared_comparison_request"])
        recovery = doc(root, source["restore_input"])
        require(request.get("mode") == "dry-run" and request.get("contentType") == "material"
                and request.get("expectedUpdatedAt") == before["updated_at"]
                and request.get("record") == candidate and "managedCandidate" not in request
                and recovery.get("record_id") == record_id
                and recovery.get("exact_restore_fields") ==
                    {field: before[field] for field in MATERIAL_FIELDS}
                and recovery.get("future_actual_Saved_ID") is None,
                "zero-write material preview and future-only restoration required")
        result[slug] = {
            "slug": slug, "record_id": record_id,
            "tuple": _material_tuple(slug, record_id, action, version),
            "candidate": source["original_candidate"], "backup": source["snapshot_backup"],
            "expected_updated_at": before["updated_at"], "observed_version": before["version"],
            "payload_sha256": digest({field: candidate[field] for field in MATERIAL_FIELDS}),
        }
    return result


def validate_two_material_formal_goal(formal, rows):
    """The publisher's actual goal, not the website proposal, gates discovery."""
    require(isinstance(formal, dict) and formal.get("task_id") == MATERIAL_PUBLICATION_TASK
            and formal.get("current_state") not in w.TERMINAL_STATES,
            "active original publisher production goal required")
    goal = formal.get("goal_delivery", {})
    required = goal.get("required_execution_actions")
    expected = {row["tuple"] for row in rows.values()}
    actual = {(x.get("task_id", MATERIAL_PUBLICATION_TASK), x.get("action_id"),
               x.get("candidate_version"), x.get("scope"), x.get("department"),
               x.get("action_class")) for x in required} if isinstance(required, list) else set()
    require(actual == expected and len(required) == 2
            and goal.get("primary_owner") == "publishing"
            and "publishing" in goal.get("producer_departments", [])
            and goal.get("responsible_assistant") == ROLE
            and set(goal.get("authorized_scope", [])) == {row["tuple"][3] for row in rows.values()}
            and goal.get("human_authorization", {}).get("executor") == "publishing"
            and goal["human_authorization"].get("evidence_path")
            and goal.get("original_business_task_id", MATERIAL_PARENT) == MATERIAL_PARENT,
            "publisher must freeze two exact Save tuples and real publishing authority")


@strict
def authenticated_formal_goal_source(root, formal, contract, task_id):
    """Confirm the existing goal initializer's human source and committed history."""
    import goal_delivery_runtime as goal_runtime
    validated = goal_runtime.validate_goal(root, contract, task_id=task_id)
    goal = formal.get("goal_delivery", {})
    require(goal.get("authorization_pin") == validated["authorization_pin"]
            and goal.get("human_authorization") == validated["human_authorization"]
            and goal.get("required_execution_actions") == validated["required_execution_actions"]
            and goal.get("authorized_scope") == validated["authorized_scope"],
            "original goal must match its validated human source and exact contract")
    task_events = [event for event in w.read_jsonl(Path(root) / w.WORKFLOW_EVENTS)
                   if event.get("task_id") == task_id]
    require(task_events and task_events[0].get("state") == "planned"
            and formal.get("event_count") == len(task_events)
            and formal.get("current_state") == task_events[-1].get("state")
            and not w.validate_workflow_events(root, task_id),
            "real committed original workflow history required")
    frozen_goals = [event.get("details", {}).get("goal_delivery") for event in task_events
                    if isinstance(event.get("details", {}).get("goal_delivery"), dict)]
    require(frozen_goals, "original event-frozen goal required")
    restored = goal_runtime.restore_goal(root, formal)
    immutable = ("authorization_pin", "human_authorization", "required_execution_actions",
                 "authorized_scope", "primary_owner", "responsible_assistant",
                 "producer_departments")
    original = frozen_goals[0]
    require(restored.get("task_id") == task_id
            and all(all(event_goal.get(key) == original.get(key) for key in immutable)
                    for event_goal in frozen_goals)
            and all(original.get(key) == goal.get(key) ==
                    restored["goal_delivery"].get(key) == validated.get(key)
                    for key in immutable),
            "snapshot and contract must match the original event-frozen goal and authority")


@strict
def two_original_material_targets(root):
    rows = two_original_material_source_contract(root)
    root = Path(root).resolve()
    formal_path = root / "data/workflows" / (MATERIAL_PUBLICATION_TASK + ".json")
    if not formal_path.exists():
        return {}
    formal = w.read_json(formal_path)
    validate_two_material_formal_goal(formal, rows)
    require(not w.validate_workflow_events(root, MATERIAL_PUBLICATION_TASK),
            "intact original publisher workflow events required")
    contract = doc(root, formal["goal_contract"])
    require(contract.get("task_id", MATERIAL_PUBLICATION_TASK) == MATERIAL_PUBLICATION_TASK
            and contract.get("parent_task_id") == MATERIAL_PARENT
            and contract.get("required_execution_actions") ==
                formal["goal_delivery"]["required_execution_actions"]
            and contract.get("human_authorization") ==
                formal["goal_delivery"]["human_authorization"],
            "formal publisher contract and workflow must freeze the same two actions")
    authenticated_formal_goal_source(root, formal, contract, MATERIAL_PUBLICATION_TASK)
    return build_two_original_material_targets(rows)


def build_two_original_material_targets(rows):
    """Build only the two already validated source rows after formal freeze."""
    targets = {}
    for slug, row in rows.items():
        task, action, version, scope, owner, _ = row["tuple"]
        targets["two-original-material-body-" + slug] = {
            "task_id": task, "action_id": action, "candidate_version": version,
            "scope": scope, "table": "materials", "record_id": row["record_id"],
            "slug": slug, "content_type": "material", "changed_fields": list(MATERIAL_FIELDS),
            "execution_owner": owner, "execution_thread_id": "example-native-f4ba16119c32b000",
            "candidate_shape": "two_original_material_body_registration_only_v1",
            "candidate": (row["candidate"]["path"], row["candidate"]["sha256"]),
            "rollback": (row["backup"]["path"], row["backup"]["sha256"]),
            "rollback_allowed": False, "qa_outbox": None,
            "expected_updated_at": row["expected_updated_at"],
            "observed_version": row["observed_version"],
            "payload_sha256": row["payload_sha256"],
            "native_registration_only": True, "release_ready": False,
        }
    return targets


def validate_two_original_material_candidate(root, candidate, target):
    exact = two_original_material_targets(root)
    matches = [row for row in exact.values() if row == target]
    require(len(matches) == 1 and candidate == doc(root, {
        "path": target["candidate"][0], "sha256": target["candidate"][1],
        "size": w.file_digest(root, target["candidate"][0])["size"]}),
        "only the exact original two-body material candidate can bind")


def _material_site_doc(value):
    """Read a pinned website release artifact; local candidate paths are excluded."""
    require(isinstance(value, dict), "actual website release pin required")
    path = Path(str(value.get("path", ""))).resolve()
    release_root = WEBSITE / "reports"
    require(path.is_file() and path.is_relative_to(release_root.resolve())
            and ".worktrees" not in path.parts,
            "website proof must be an actual project release artifact")
    raw = path.read_bytes()
    require(type(value.get("size")) is int and len(raw) == value["size"]
            and hashlib.sha256(raw).hexdigest() == value.get("sha256"),
            "website release proof bytes changed")
    return json.loads(raw)


@strict
def two_original_material_readiness(root, target, accepted):
    """Read the publisher's committed selfcheck and real website release proof.

    Registration, a local website candidate, or an A2 source PASS alone never
    makes either material ready for a permit.
    """
    root = Path(root).resolve()
    exact = two_original_material_targets(root)
    require(sum(value == target for value in exact.values()) == 1
            and target.get("candidate_shape") == "two_original_material_body_registration_only_v1"
            and target.get("native_registration_only") is True
            and target.get("release_ready") is False
            and target.get("rollback_allowed") is False,
            "only one original two-body registration may seek later readiness")
    require(isinstance(accepted, dict)
            and accepted.get("acceptance_model") == "goal_authorized_cms_selfcheck_v1"
            and accepted.get("verdict") == "selfcheck_ready"
            and accepted.get("task_id") == target["task_id"]
            and accepted.get("action_id") == target["action_id"]
            and accepted.get("scope") == target["scope"]
            and accepted.get("candidate_version") == target["candidate_version"]
            and accepted.get("candidate", {}).get("sha256") == target["candidate"][1]
            and accepted.get("goal_completion_claimed") is False,
            "committed exact original publisher selfcheck required")
    preflight = doc(root, accepted.get("execution_preflight"))
    check = doc(root, preflight.get("self_check"))
    source_pin = check.get("source_verification")
    require(isinstance(source_pin, dict) and source_pin in check.get("evidence", []),
            "committed publisher selfcheck must pin deployed source proof")
    source = doc(root, source_pin)
    required = {"task_id": target["task_id"], "action_id": target["action_id"],
                "candidate_version": target["candidate_version"],
                "scope": target["scope"], "record_id": target["record_id"]}
    require(source.get("schema") == "two-original-material-protected-source/v1"
            and all(source.get(key) == value for key, value in required.items())
            and source.get("status") == "DEPLOYED_SOURCE_VERIFIED"
            and source.get("source_candidate_version") ==
                "two-original-materials-protected-body-channel-v2-20261014"
            and source.get("source_candidate_head") ==
                "b5f54dea9d6277b51daab2e0c0e23fe65bdac46a",
            "exact original website source and publisher tuple required")
    deployed = _material_site_doc(source.get("website_deployment"))
    sha = deployed.get("production_website_sha")
    require(deployed.get("status") == "PASS_ACTUAL_PRODUCTION_EDGE_SOURCE_AND_RECOVERY_BACKUP"
            and deployed.get("source_candidate_version") == source["source_candidate_version"]
            and deployed.get("source_candidate_head") == source["source_candidate_head"]
            and re.fullmatch(r"[0-9a-f]{40}", str(sha))
            and sha == source.get("production_sha")
            and deployed.get("actual_function", {}).get("name") == "content-publish"
            and deployed["actual_function"].get("status") == "ACTIVE"
            and type(deployed["actual_function"].get("after_version")) is int
            and deployed["actual_function"].get("after_download_version") ==
                deployed["actual_function"]["after_version"],
            "actual Edge deployment/version readback required")
    release_run = _material_site_doc(deployed.get("run_proof")).get("run", {})
    require(release_run.get("head_sha") == sha and release_run.get("event") == "workflow_dispatch"
            and release_run.get("conclusion") == "success"
            and release_run.get("status") == "completed"
            and type(release_run.get("id")) is int and release_run["id"] > 0
            and release_run["id"] == deployed.get("run_id")
            and release_run.get("head_branch") == "main"
            and release_run.get("name") == "Release managed content-publish R3"
            and release_run.get("path") == ".github/workflows/supabase-content-publish-r3.yml"
            and release_run.get("repository", {}).get("full_name") ==
                "wangchaozhuanyong/zhuangxiuwangzhan"
            and release_run["repository"].get("id") == 1248188229
            and release_run.get("head_repository", {}).get("full_name") ==
                "wangchaozhuanyong/zhuangxiuwangzhan",
            "actual protected R3 repository/main/workflow run must own the deployed source")
    release_artifacts = (WEBSITE / "reports" /
        "two-original-materials-protected-body-channel-20261014-v2" /
        f"production-r3-run-{release_run['id']}-artifacts").resolve()
    require(Path(str(deployed.get("actual_readback", {}).get("manifest", {}).get("path", "")))
            .resolve().is_relative_to(release_artifacts),
            "Edge source manifest must belong to the exact R3 readback artifact")
    expected = doc(root, MATERIAL_EXPECTED_SOURCE)
    files = expected.get("files", [])
    types = expected.get("typeOnlyFileRecovery", [])
    paths = [item.get("path") for item in files]
    type_paths = [item.get("path") for item in types]
    require(expected.get("schema") == "content-publish-runtime-source/v1"
            and expected.get("entrypoint") == "content-publish/index.ts"
            and "content-publish/index.ts" in paths
            and isinstance(files, list) and len(files) == len(set(paths)) == 21
            and isinstance(types, list) and len(types) == len(set(type_paths))
            and set(expected.get("typeOnlyFiles", [])) == set(type_paths)
            and not set(paths) & set(type_paths),
            "reviewed exact source-expected dependency closure required")
    for item in files + types:
        path = item.get("path")
        require(isinstance(path, str)
                and re.fullmatch(r"(?:_shared|content-publish)/[a-zA-Z0-9_-]+\.ts", path)
                and type(item.get("bytes")) is int and item["bytes"] > 0,
                "reviewed source closure contains an unexpected path or size")
        original = _git_source(source["source_candidate_head"], "supabase/functions/" + path)
        require(len(original) == item["bytes"]
                and hashlib.sha256(original).hexdigest() == item.get("sha256")
                and _git_source(sha, "supabase/functions/" + path) == original,
                "reviewed and released Edge dependency source differs")
    manifest = _material_site_doc(deployed.get("actual_readback", {}).get("manifest"))
    recovered = manifest.get("typeOnlyFileRecovery", [])
    require(manifest.get("schema") == expected["schema"]
            and manifest.get("entrypoint") == expected["entrypoint"]
            and manifest.get("files") == files
            and manifest.get("typeOnlyFiles") == expected["typeOnlyFiles"]
            and manifest.get("externalImports") == expected["externalImports"]
            and isinstance(recovered, list)
            and len({item.get("path") for item in recovered}) == len(recovered)
            and all(item in types for item in recovered),
            "actual download must match the complete reviewed runtime and type-only source")
    canonical = [{"path": item["path"], "bytes": item["bytes"], "sha256": item["sha256"]}
                 for item in sorted(files + recovered, key=lambda value: value["path"])]
    closure_digest = hashlib.sha256(json.dumps(canonical, ensure_ascii=False,
        separators=(",", ":")).encode()).hexdigest()
    require(deployed["actual_readback"].get("source_sha256") == closure_digest,
            "actual Edge runtime/type recovery digest differs")
    readback = Path(str(deployed["actual_readback"].get("root", ""))).resolve()
    require(readback == release_artifacts / "readback/edge-after/supabase/functions"
            and readback.is_dir(), "actual downloaded Edge source root required")
    metadata = deployed.get("artifact_metadata_pins", [])
    require(isinstance(metadata, list) and len(metadata) == 2
            and {Path(str(item.get("path", ""))).name for item in metadata}
                == {"functions-after.json", "functions-after-download.json"},
            "actual Edge function metadata and download metadata required")
    for item in metadata:
        require(Path(str(item.get("path", ""))).resolve().is_relative_to(release_artifacts),
                "Edge function metadata must belong to the same release run artifact")
        functions = _material_site_doc(item)
        require(isinstance(functions, list)
                and len([row for row in functions if row.get("name") == "content-publish"
                         and row.get("status") == "ACTIVE"
                         and row.get("version") == deployed["actual_function"]["after_version"]]) == 1,
                "actual Edge function metadata version differs")
    actual_paths = set(paths) | {item["path"] for item in recovered}
    observed_paths = set()
    for entry in readback.rglob("*"):
        require(not entry.is_symlink(), "Edge source download contains a symbolic link")
        if entry.is_dir():
            continue
        require(entry.is_file(), "Edge source download contains an unsupported entry")
        observed_paths.add(entry.relative_to(readback).as_posix())
    require(observed_paths == actual_paths,
            "complete downloaded Edge file set must equal the reviewed dependency closure")
    for item in files + recovered:
        path = item["path"]
        raw = (readback / path).read_bytes()
        require(type(item.get("bytes")) is int and len(raw) == item["bytes"]
                and hashlib.sha256(raw).hexdigest() == item.get("sha256")
                and _git_source(sha, "supabase/functions/" + path) == raw,
                "deployed Edge source differs from the release commit")
    website = doc(root, MATERIAL_WEBSITE_RETURN)
    require(len(website.get("source_file_pins", [])) == 11,
            "all eleven reviewed website source files required")
    for item in website["source_file_pins"]:
        path = item.get("path", "")
        marker = "/reports/two-original-materials-protected-body-channel-20261014-v2/after/"
        require(isinstance(path, str) and path.startswith(str(WEBSITE) + marker),
                "only original reviewed website source files may be checked")
        relative = path.split(marker, 1)[1]
        original = _git_source(source["source_candidate_head"], relative)
        require(len(original) == item.get("bytes")
                and hashlib.sha256(original).hexdigest() == item.get("sha256")
                and _git_source(sha, relative) == original,
                "released code must retain every reviewed material channel file")
    machine_pin = check.get("actual_machine")
    require(isinstance(machine_pin, dict) and machine_pin in check.get("evidence", []),
            "publisher selfcheck must pin the actual protected preview machine")
    machine = doc(root, machine_pin)
    require(machine.get("task_id") == target["task_id"]
            and machine.get("action_id") == target["action_id"]
            and machine.get("scope") == target["scope"]
            and machine.get("candidate_version") == target["candidate_version"]
            and type(machine.get("github_actor_id")) is int
            and machine["github_actor_id"] > 0,
            "exact publisher workflow actor and machine binding required")
    run, probe, payload, receipt, backup = [doc(root, machine.get(key)) for key in
        ("run_snapshot", "identity_probe", "payload_digest", "locked_preview", "backup")]
    before = doc(root, {"path": target["rollback"][0],
                        "sha256": target["rollback"][1],
                        "size": w.file_digest(root, target["rollback"][0])["size"]})
    current = backup.get("record")
    candidate = doc(root, {"path": target["candidate"][0],
                           "sha256": target["candidate"][1],
                           "size": w.file_digest(root, target["candidate"][0])["size"]})
    require(isinstance(current, dict) and len(current) == 46
            and type(current.get("version")) is int and current == before
            and current.get("version") == target["observed_version"]
            and current.get("updated_at") == target["expected_updated_at"]
            and re.fullmatch(r".*\.\d{6}\+00:00", str(current.get("updated_at", "")))
            and {key for key in current if current[key] != candidate[key]} == set(MATERIAL_FIELDS)
            and backup.get("table") == "materials" and backup.get("key") == target["slug"]
            and payload.get("task_id") == target["task_id"]
            and payload.get("candidate_version") == target["candidate_version"]
            and payload.get("operation") == "publish"
            and payload.get("payload_sha256") == target["payload_sha256"]
            and payload.get("expected_updated_at") == current["updated_at"]
            and receipt.get("task_id") == target["task_id"]
            and receipt.get("action_id") == target["action_id"]
            and receipt.get("candidate_version") == target["candidate_version"]
            and receipt.get("scope") == target["scope"]
            and receipt.get("operation") == "publish"
            and receipt.get("expected_updated_at") == current["updated_at"]
            and receipt.get("http_status") == 200 and receipt.get("dry_run") is True
            and receipt.get("performed_write") is False
            and receipt.get("external_writes") == 0
            and receipt.get("row_unchanged_after_dry_run") is True
            and run.get("event") == "workflow_dispatch"
            and run.get("head_branch") == "main"
            and run.get("name") == "Approved website content publish"
            and run.get("path") == ".github/workflows/content-publish-approved.yml"
            and run.get("conclusion") == "success"
            and type(run.get("id")) is int and run["id"] > 0
            and run.get("head_sha") == sha
            and run.get("actor", {}).get("id") == machine["github_actor_id"]
            and probe.get("ok") is True and probe.get("dry_run") is True
            and probe.get("performed_write") is False
            and probe.get("identity", {}).get("actorId") == machine["github_actor_id"]
            and probe["identity"].get("runId") == run["id"]
            and probe["identity"].get("runAttempt") == run.get("run_attempt")
            and probe["identity"].get("repositoryId") == 1248188229
            and probe["identity"].get("workflowRef") ==
                "wangchaozhuanyong/zhuangxiuwangzhan/.github/workflows/content-publish-approved.yml@refs/heads/main"
            and probe["identity"].get("workflowSha") == run["head_sha"] == sha,
            "actual protected preview must bind exact full row, CAS, actor and deployed code")
    checked = w._parse_observed_at(receipt.get("checked_at"))
    captured = w._parse_observed_at(backup.get("capturedAt"))
    completed = w._parse_observed_at(run.get("updated_at"))
    now = dt.datetime.now(dt.timezone.utc)
    require(checked is not None and captured is not None and completed is not None
            and now - dt.timedelta(minutes=30) <= captured <= checked <= completed <= now,
            "full-row backup and zero-write preview must be fresh")
    return {"source": source_pin, "production_sha": sha,
            "function_version": deployed["actual_function"]["after_version"],
            "machine": machine_pin}


@strict
def validate_two_original_material_machine(root, target, accepted, run, probe, payload,
                                           receipt, backup, actor):
    """Tie the live protected preview to the exact current full row and source."""
    ready = two_original_material_readiness(root, target, accepted)
    preflight = doc(root, accepted["execution_preflight"])
    check = doc(root, preflight["self_check"])
    machine = doc(root, check.get("actual_machine"))
    require(check.get("actual_machine") == ready["machine"]
            and machine.get("task_id") == target["task_id"]
            and machine.get("action_id") == target["action_id"]
            and machine.get("scope") == target["scope"]
            and machine.get("candidate_version") == target["candidate_version"]
            and machine.get("github_actor_id") == actor
            and all(actual == doc(root, machine.get(key)) for actual, key in
                    ((run, "run_snapshot"), (probe, "identity_probe"),
                     (payload, "payload_digest"), (receipt, "locked_preview"),
                     (backup, "backup"))),
            "protected run artifacts must equal the committed publisher selfcheck")
    return ready


def _weekly_key_context(root):
    import importlib.util
    frozen = pin(root, {"path": WEEKLY_KEY_REPAIR_CONTEXT_PATH, **WEEKLY_KEY_REPAIR_CONTEXT_BYTES})
    spec = importlib.util.spec_from_file_location("_flashcast_weekly_key_repair_reviewed_context", w.safe_path(root, frozen["path"]))
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    require(helper.SOURCE_PATHS == WEEKLY_KEY_REPAIR_PATHS, "only exact three-source formal-entry/key-contract helper required")
    return helper

def _weekly_lineage_key_repair_successor(root, continuation_pin, weekly_continuation_pin, native_continuation_pin, old_manifest_pin, source_repair_continuation_pin, functional_continuation_pin=None):
    """Exact fourth-level permanent source provenance; never a lease or permission.

    Called only after the original manifests are frozen. The caller still validates each preceding
    review/CAS/committed chain; this authenticates only the new exact effect.
    Its overlapping before bytes must equal that verified V2 or boundary installed effect.
    """
    import importlib.util
    import result_coordination as c
    from scoped_candidate_adoption import _committed
    role = 'operations-assistant-2'
    continuation = doc(root, continuation_pin)
    fields = {'schema', 'task_id', 'scope', 'candidate_version', 'original_weekly_native_source_continuation', 'historical_V5_manifest', 'original_native_control_continuation', 'original_source_repair_continuation', 'candidate_manifest', 'source_qa', 'review_plan', 'producer_outbox', 'source_adoption', 'adoption_followthrough_record_id', 'review_context_helper', 'prepared_only', *V5_REVIEW_FLAGS}
    require(set(continuation) == fields and continuation.get('schema') == 'actual_weekly_native_lineage_key_contract_repair_continuation/v1' and (continuation.get('task_id') == WEEKLY_KEY_REPAIR_TASK) and (continuation.get('scope') == WEEKLY_KEY_REPAIR_SCOPE) and (continuation.get('candidate_version') == WEEKLY_KEY_REPAIR_VERSION) and (continuation.get('original_weekly_native_source_continuation') == weekly_continuation_pin and continuation.get('historical_V5_manifest') == old_manifest_pin) and (continuation.get('original_native_control_continuation') == native_continuation_pin) and (continuation.get('original_source_repair_continuation') == source_repair_continuation_pin) and (continuation.get('prepared_only') is False) and all((continuation.get(key) is False for key in V5_REVIEW_FLAGS)), 'one exact accepted three-source successor with original V5/V6 links required')
    manifest_pin = pin(root, continuation.get('candidate_manifest'))
    manifest = doc(root, manifest_pin)
    helper_pin = pin(root, continuation.get('review_context_helper'))
    require(helper_pin['path'] == str(Path(manifest_pin['path']).parent / 'rollback/source_review_context.py') and helper_pin in manifest.get('inputs', []) and ({key: helper_pin[key] for key in ('sha256', 'size')} == WEEKLY_KEY_REPAIR_CONTEXT_BYTES) and (manifest.get('source_lineage', {}).get('historical_V5_manifest') == old_manifest_pin) and (manifest.get('source_lineage', {}).get('original_native_control_continuation') == native_continuation_pin) and (manifest.get('source_lineage', {}).get('original_source_repair_continuation') == source_repair_continuation_pin) and (manifest.get('source_lineage', {}).get('original_weekly_native_source_continuation') == weekly_continuation_pin and len(manifest.get('files', [])) == len(WEEKLY_KEY_REPAIR_PATHS)) and ({row.get('path') for row in manifest['files']} == WEEKLY_KEY_REPAIR_PATHS), 'exact frozen reviewed helper and three-target original lineage required')
    journal_pin = pin(root, continuation.get('source_adoption'))
    journal = doc(root, journal_pin)
    require(journal_pin['path'] == f"backups/{WEEKLY_KEY_REPAIR_TASK}/{manifest['candidate_fingerprint']}/forward/journal.json", 'canonical reviewed weekly forward journal required')
    handoffs = w._result_handoff_rows(root, WEEKLY_KEY_REPAIR_TASK)
    decisions = [row for row in handoffs if row.get('record_id') == journal.get('decision_record_id')]
    require(len(decisions) == 1, 'one committed new repair adoption decision required')
    decision = decisions[0]
    review_pin = pin(root, continuation.get('source_qa'))
    box = doc(root, review_pin)
    review = box.get('candidate_review', {})
    producer_pin = pin(root, continuation.get('producer_outbox'))
    require(manifest.get('schema') == 'flashcast-exact-source-candidate/v1' and manifest.get('task_id') == WEEKLY_KEY_REPAIR_TASK and (manifest.get('scope') == WEEKLY_KEY_REPAIR_SCOPE) and (manifest.get('candidate_version') == WEEKLY_KEY_REPAIR_VERSION) and (manifest.get('primary_owner') == 'system-development') and (manifest.get('responsible_assistant') == role) and (manifest.get('candidate_fingerprint') == digest({key: value for (key, value) in manifest.items() if key != 'candidate_fingerprint'})) and (box.get('department') == role) and (box.get('task_id') == WEEKLY_KEY_REPAIR_TASK) and (box.get('candidate_version') == WEEKLY_KEY_REPAIR_VERSION) and (box.get('scope') == WEEKLY_KEY_REPAIR_SCOPE) and (box.get('status') == 'partial') and (box.get('prepared_only', False) is False) and (not box.get('goal_acceptance')) and (box.get('qa_verdict') != 'pass') and (review.get('actor') == role) and (review.get('verdict') == 'PASS_SOURCE_CANDIDATE_ONLY') and (review.get('phase') == 'candidate_source_only') and (review.get('direction') == 'forward') and (review.get('candidate_manifest') == manifest_pin) and (review.get('candidate_fingerprint') == manifest['candidate_fingerprint']) and (review.get('producer_outbox') == producer_pin) and (review.get('review_plan') == continuation.get('review_plan')) and (review.get('goal_contract') == manifest.get('goal_contract')) and (review.get('human_authorization') == manifest.get('human_authorization')) and all((manifest.get(key) is False and box.get(key) is False and (review.get(key) is False) for key in V5_REVIEW_FLAGS)), 'independently accepted exact source manifest required before executing its frozen helper')
    w.validate_outbox(root, [review_pin], role, WEEKLY_KEY_REPAIR_TASK)
    _native(root, box, [WEEKLY_KEY_REPAIR_TASK, WEEKLY_KEY_REPAIR_VERSION, manifest['candidate_fingerprint'], producer_pin['sha256'], manifest_pin['sha256'], 'PASS_SOURCE_CANDIDATE_ONLY'], role)
    require(decision.get('event') == 'controller_decision' and decision.get('decision') == 'continue' and (decision.get('task_id') == WEEKLY_KEY_REPAIR_TASK) and (decision.get('candidate_version') == WEEKLY_KEY_REPAIR_VERSION) and (decision.get('outbox') == producer_pin) and (review_pin in decision.get('evidence', [])) and (decision.get('coordinator_role') == decision.get('decision_actor') == decision.get('responsible_assistant') == role) and (decision.get('next_owner') == role) and (decision.get('next_action') == 'adopt-' + WEEKLY_KEY_REPAIR_VERSION) and (decision.get('business_goal_closed') is False) and (decision.get('qa_status') != 'pass'), 'actual independent source-only adoption decision must bind the accepted helper manifest')
    _committed(root, decision)
    _v5_source_decision_fence(root, decision, role)
    source = {key: continuation[key] for key in ('task_id', 'scope', 'candidate_version', 'candidate_manifest', 'source_qa', 'review_plan', 'producer_outbox', 'prepared_only', *V5_REVIEW_FLAGS)}
    source['schema'] = 'flashcast-actual-source-review-input/v1'
    spec = importlib.util.spec_from_file_location('_flashcast_permanent_weekly_source_context', w.safe_path(root, helper_pin['path']))
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    require(helper.SOURCE_PATHS == WEEKLY_KEY_REPAIR_PATHS, 'reviewed helper must retain exactly three source targets')
    if functional_continuation_pin is None:
        (manifest, reviewed, actual_decision, identity) = helper.review_context(root, manifest_pin, source, decision['record_id'], role, decision.get('coordinator_owner'))
    else:
        functional_helper = _weekly_functional_context(root, functional_continuation_pin)
        (manifest, reviewed, actual_decision, identity) = functional_helper.historical_key_review_context(root, manifest_pin, source,
            decision['record_id'], role, decision.get('coordinator_owner'), functional_continuation_pin)
    require(actual_decision == decision and identity == {'task_id': WEEKLY_KEY_REPAIR_TASK, 'sender_department': 'system-development', 'candidate_version': WEEKLY_KEY_REPAIR_VERSION, 'result_sha256': reviewed['producer_pin']['sha256']}, 'exact actual new repair producer and independent decision identity required')
    previous_native = doc(root, native_continuation_pin)
    previous_boundary = doc(root, source_repair_continuation_pin)
    require(previous_native.get('schema') == 'actual_native_control_source_continuation/v1' and previous_native.get('task_id') == NATIVE_SOURCE_TASK and (previous_native.get('historical_V5_manifest') == old_manifest_pin) and (previous_boundary.get('schema') == 'actual_acceptance_message_historical_adoption_source_continuation/v1') and (previous_boundary.get('task_id') == SOURCE_REPAIR_TASK) and (previous_boundary.get('historical_V5_manifest') == old_manifest_pin) and (previous_boundary.get('original_native_control_continuation') == native_continuation_pin), 'immutable exact V5/V6/boundary predecessor links required')
    native_manifest = doc(root, previous_native.get('candidate_manifest'))
    boundary_manifest = doc(root, previous_boundary.get('candidate_manifest'))
    original_installed = {row['path']: {'path': row['path'], **row['after']} for row in native_manifest['files']}
    original_installed.update({row['path']: {'path': row['path'], **row['after']} for row in boundary_manifest['files']})
    previous_weekly = doc(root, weekly_continuation_pin)
    require(previous_weekly.get('candidate_version') == WEEKLY_SOURCE_VERSION and previous_weekly.get('task_id') == WEEKLY_SOURCE_TASK and previous_weekly.get('historical_V5_manifest') == old_manifest_pin and previous_weekly.get('original_native_control_continuation') == native_continuation_pin and previous_weekly.get('original_source_repair_continuation') == source_repair_continuation_pin, 'exact original independently adopted V2 predecessor required')
    previous_weekly_manifest = doc(root, previous_weekly['candidate_manifest'])
    original_installed.update({row['path']: {'path': row['path'], **row['after']} for row in previous_weekly_manifest['files']})
    operations = journal.get('source_operations', [])
    require(journal.get('task_id') == WEEKLY_KEY_REPAIR_TASK and journal.get('candidate_version') == WEEKLY_KEY_REPAIR_VERSION and (journal.get('candidate_fingerprint') == manifest['candidate_fingerprint']) and (journal.get('candidate_manifest') == manifest_pin) and (journal.get('review_outbox') == reviewed['review_pin']) and (journal.get('authorized_source') == reviewed['authority_pin']) and (journal.get('actor') == role) and (journal.get('direction') == 'forward') and (journal.get('status') == 'complete') and (type(journal.get('external_writes')) is int) and (journal['external_writes'] == 0) and (journal.get('effect_uncertain') is False) and (journal.get('permissions_issued') is False) and (journal.get('source_effect_state') == 'ALL_REVIEWED_AFTER_VERIFIED') and (type(journal.get('operator_source_syscalls_attempted')) is int) and (journal['operator_source_syscalls_attempted'] == len(WEEKLY_KEY_REPAIR_PATHS)) and isinstance(journal.get('execution_id'), str) and bool(journal['execution_id'].strip()) and (len(operations) == len(WEEKLY_KEY_REPAIR_PATHS)) and ({row.get('path') for row in operations} == WEEKLY_KEY_REPAIR_PATHS) and (len(journal.get('applied', [])) == len(WEEKLY_KEY_REPAIR_PATHS)) and (set(journal['applied']) == WEEKLY_KEY_REPAIR_PATHS), 'actual complete independent three-target repair CAS journal required')
    installed = {}
    for row in manifest['files']:
        path = row['path']
        require(row.get('before') != {'exists': False} and (path not in original_installed or row['before'] == {key: original_installed[path][key] for key in ('sha256', 'size')}), 'new repair before must preserve exact verified original V6 overlap')
        operation = next((value for value in operations if value['path'] == path))
        backup = pin(root, operation.get('backup'))
        candidate = pin(root, row.get('candidate'))
        baseline = pin(root, row.get('baseline'))
        require(operation.get('before') == row['before'] == {key: baseline[key] for key in ('sha256', 'size')} == {key: backup[key] for key in ('sha256', 'size')} and operation.get('after_expected') == operation.get('after_actual') == row['after'] == {key: candidate[key] for key in ('sha256', 'size')} and (operation.get('write_attempted') is True) and (operation.get('verified_after') is True) and (operation.get('source_syscall_attempted') is True) and (operation.get('temporary_path') == path + '.cas-' + journal['execution_id']) and (backup['path'] == f"backups/{WEEKLY_KEY_REPAIR_TASK}/{manifest['candidate_fingerprint']}/forward/" + path) and backup['path'].startswith(f"backups/{WEEKLY_KEY_REPAIR_TASK}/{manifest['candidate_fingerprint']}/forward/") and (type(operation.get('before_mode')) is int) and (operation['before_mode'] == row.get('before_mode')) and (w.safe_path(root, backup['path']).stat().st_mode & 511 == operation['before_mode']) and (w.safe_path(root, baseline['path']).stat().st_mode & 511 == row['before_mode']) and (w.safe_path(root, path).stat().st_mode & 511 == row.get('after_mode')), 'exact new repair original backup, before/write/readback effects and installed modes required')
        if functional_continuation_pin is not None and path in WEEKLY_FUNCTIONAL_ENTRY_PATHS:
            new = doc(root, doc(root, functional_continuation_pin)['candidate_manifest'])
            newer = next(value for value in new['files'] if value['path'] == path)
            require(newer['before'] == row['after'] and newer['before_mode'] == row['after_mode'],
                    'new functional source must begin at exact original V4 endpoint')
            installed[path] = pin(root, {'path': path, **newer['after']})
        else:
            installed[path] = pin(root, {'path': path, **row['after']})
    follows = [row for row in handoffs if row.get('record_id') == continuation.get('adoption_followthrough_record_id')]
    require(len(follows) == 1, 'unique actual new repair adopted-effects followthrough required')
    follow = follows[0]
    require(follow.get('event') == 'controller_followthrough' and follow.get('followthrough_status') == 'blocked_with_owner' and (c.exact_identity(follow) == identity) and (follow.get('outbox') == reviewed['producer_pin']) and (follow.get('coordinator_role') == follow.get('decision_actor') == follow.get('responsible_assistant') == role) and (follow.get('coordinator_owner') == decision.get('coordinator_owner')) and (follow.get('coordination_fence') == decision.get('coordination_fence')) and (follow.get('business_goal_closed') is False) and (follow.get('unblock_condition') == 'source-adopted:' + journal['execution_id'] + ';remaining:original-weekly-functional-and-source-goal-formal-QA') and (journal_pin in follow.get('evidence', [])) and (handoffs.index(decision) < handoffs.index(follow)), 'exact new repair committed installed-source readback and original consumer boundaries required')
    _committed(root, follow)
    audit = _v5_source_decision_fence(root, follow, role)
    if functional_continuation_pin is not None:
        _source_release_readback(root, follow, audit)
    box = doc(root, reviewed['review_pin'])
    moments = [w._parse_observed_at(value) for value in (box.get('created_at'), journal.get('started_at'), journal.get('completed_at'))]
    require(all((value is not None for value in moments)) and moments == sorted(moments) and (moments[-1] <= dt.datetime.now(dt.timezone.utc)) and (moments[-1].timestamp() <= audit['reserved_at'] <= audit['committed_at']), 'ordered independent new repair review, CAS and permanent committed followthrough required')
    return installed


WEEKLY_FUNCTIONAL_ENTRY_TASK = "fc-20261011-weekly-functional-result-continuation-entry-repair-v1"
WEEKLY_FUNCTIONAL_ENTRY_SCOPE = "project:flashcast:weekly-functional-result-continuation-entry-repair:v1"
WEEKLY_FUNCTIONAL_ENTRY_VERSION = "weekly-functional-result-continuation-entry-repair-candidate-v3-20261011"
WEEKLY_FUNCTIONAL_ENTRY_PATHS = {"tools/qa_review_plan.py", "tools/paid_three_page_bounded_cms.py"}
WEEKLY_FUNCTIONAL_ENTRY_CONTEXT_BYTES = {'sha256': '42eca0264b07362cb55d272d504f2093b4ff09edf9bef10a54d502cf35004e26', 'size': 42917}


def _weekly_functional_context(root, continuation_pin):
    """Only the reviewed new-goal helper may read the fifth layer."""
    import importlib.util
    continuation = doc(root, continuation_pin)
    manifest_pin = pin(root, continuation.get("candidate_manifest"))
    helper_pin = pin(root, continuation.get("review_context_helper"))
    require(helper_pin["path"] == str(Path(manifest_pin["path"]).parent / "rollback/source_review_context.py")
        and {key:helper_pin[key] for key in ("sha256","size")} == WEEKLY_FUNCTIONAL_ENTRY_CONTEXT_BYTES,
        "exact reviewed new-goal helper bytes required")
    spec = importlib.util.spec_from_file_location("_flashcast_weekly_functional_entry_review_context",w.safe_path(root,helper_pin["path"]))
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    require(helper.TASK == WEEKLY_FUNCTIONAL_ENTRY_TASK and helper.VERSION == WEEKLY_FUNCTIONAL_ENTRY_VERSION
        and helper.SOURCE_PATHS == WEEKLY_FUNCTIONAL_ENTRY_PATHS,"new helper cannot inherit an old task or target set")
    return helper
def _weekly_functional_result_entry_successor(root, continuation_pin, repair_continuation_pin, weekly_continuation_pin, native_continuation_pin, old_manifest_pin, source_repair_continuation_pin):
    """Exact fifth-level permanent source provenance; never a lease or permission.

    Called only after the original manifests are frozen. The caller still validates each preceding
    review/CAS/committed chain; this authenticates only the new exact effect.
    Its overlapping before bytes must equal that verified V2 or boundary installed effect.
    """
    import importlib.util
    import result_coordination as c
    from scoped_candidate_adoption import _committed
    role = 'operations-assistant-2'
    continuation = doc(root, continuation_pin)
    fields = {'schema', 'task_id', 'scope', 'candidate_version', 'original_weekly_native_source_continuation', 'original_weekly_lineage_key_contract_repair_continuation', 'historical_V5_manifest', 'original_native_control_continuation', 'original_source_repair_continuation', 'candidate_manifest', 'source_qa', 'review_plan', 'producer_outbox', 'source_adoption', 'adoption_followthrough_record_id', 'review_context_helper', 'prepared_only', *V5_REVIEW_FLAGS}
    require(set(continuation) == fields and continuation.get('schema') == 'actual_weekly_functional_result_entry_repair_continuation/v1' and (continuation.get('task_id') == WEEKLY_FUNCTIONAL_ENTRY_TASK) and (continuation.get('scope') == WEEKLY_FUNCTIONAL_ENTRY_SCOPE) and (continuation.get('candidate_version') == WEEKLY_FUNCTIONAL_ENTRY_VERSION) and continuation.get('original_weekly_lineage_key_contract_repair_continuation') == repair_continuation_pin and (continuation.get('original_weekly_native_source_continuation') == weekly_continuation_pin and continuation.get('historical_V5_manifest') == old_manifest_pin) and (continuation.get('original_native_control_continuation') == native_continuation_pin) and (continuation.get('original_source_repair_continuation') == source_repair_continuation_pin) and (continuation.get('prepared_only') is False) and all((continuation.get(key) is False for key in V5_REVIEW_FLAGS)), 'one exact accepted two-source successor with original V5/V6 links required')
    manifest_pin = pin(root, continuation.get('candidate_manifest'))
    manifest = doc(root, manifest_pin)
    helper_pin = pin(root, continuation.get('review_context_helper'))
    require(helper_pin['path'] == str(Path(manifest_pin['path']).parent / 'rollback/source_review_context.py') and helper_pin in manifest.get('inputs', []) and ({key: helper_pin[key] for key in ('sha256', 'size')} == WEEKLY_FUNCTIONAL_ENTRY_CONTEXT_BYTES) and (manifest.get('source_lineage', {}).get('historical_V5_manifest') == old_manifest_pin) and (manifest.get('source_lineage', {}).get('original_native_control_continuation') == native_continuation_pin) and (manifest.get('source_lineage', {}).get('original_source_repair_continuation') == source_repair_continuation_pin) and manifest.get('source_lineage', {}).get('original_weekly_lineage_key_contract_repair_continuation') == repair_continuation_pin and (manifest.get('source_lineage', {}).get('original_weekly_native_source_continuation') == weekly_continuation_pin and len(manifest.get('files', [])) == len(WEEKLY_FUNCTIONAL_ENTRY_PATHS)) and ({row.get('path') for row in manifest['files']} == WEEKLY_FUNCTIONAL_ENTRY_PATHS), 'exact frozen reviewed helper and two-target original lineage required')
    journal_pin = pin(root, continuation.get('source_adoption'))
    journal = doc(root, journal_pin)
    require(journal_pin['path'] == f"backups/{WEEKLY_FUNCTIONAL_ENTRY_TASK}/{manifest['candidate_fingerprint']}/forward/journal.json", 'canonical reviewed weekly forward journal required')
    handoffs = w._result_handoff_rows(root, WEEKLY_FUNCTIONAL_ENTRY_TASK)
    decisions = [row for row in handoffs if row.get('record_id') == journal.get('decision_record_id')]
    require(len(decisions) == 1, 'one committed new repair adoption decision required')
    decision = decisions[0]
    review_pin = pin(root, continuation.get('source_qa'))
    box = doc(root, review_pin)
    review = box.get('candidate_review', {})
    producer_pin = pin(root, continuation.get('producer_outbox'))
    require(manifest.get('schema') == 'flashcast-exact-source-candidate/v1' and manifest.get('task_id') == WEEKLY_FUNCTIONAL_ENTRY_TASK and (manifest.get('scope') == WEEKLY_FUNCTIONAL_ENTRY_SCOPE) and (manifest.get('candidate_version') == WEEKLY_FUNCTIONAL_ENTRY_VERSION) and (manifest.get('primary_owner') == 'system-development') and (manifest.get('responsible_assistant') == role) and (manifest.get('candidate_fingerprint') == digest({key: value for (key, value) in manifest.items() if key != 'candidate_fingerprint'})) and (box.get('department') == role) and (box.get('task_id') == WEEKLY_FUNCTIONAL_ENTRY_TASK) and (box.get('candidate_version') == WEEKLY_FUNCTIONAL_ENTRY_VERSION) and (box.get('scope') == WEEKLY_FUNCTIONAL_ENTRY_SCOPE) and (box.get('status') == 'partial') and (box.get('prepared_only', False) is False) and (not box.get('goal_acceptance')) and (box.get('qa_verdict') != 'pass') and (review.get('actor') == role) and (review.get('verdict') == 'PASS_SOURCE_CANDIDATE_ONLY') and (review.get('phase') == 'candidate_source_only') and (review.get('direction') == 'forward') and (review.get('candidate_manifest') == manifest_pin) and (review.get('candidate_fingerprint') == manifest['candidate_fingerprint']) and (review.get('producer_outbox') == producer_pin) and (review.get('review_plan') == continuation.get('review_plan')) and (review.get('goal_contract') == manifest.get('goal_contract')) and (review.get('human_authorization') == manifest.get('human_authorization')) and all((manifest.get(key) is False and box.get(key) is False and (review.get(key) is False) for key in V5_REVIEW_FLAGS)), 'independently accepted exact source manifest required before executing its frozen helper')
    w.validate_outbox(root, [review_pin], role, WEEKLY_FUNCTIONAL_ENTRY_TASK)
    _native(root, box, [WEEKLY_FUNCTIONAL_ENTRY_TASK, WEEKLY_FUNCTIONAL_ENTRY_VERSION, manifest['candidate_fingerprint'], producer_pin['sha256'], manifest_pin['sha256'], 'PASS_SOURCE_CANDIDATE_ONLY'], role)
    require(decision.get('event') == 'controller_decision' and decision.get('decision') == 'continue' and (decision.get('task_id') == WEEKLY_FUNCTIONAL_ENTRY_TASK) and (decision.get('candidate_version') == WEEKLY_FUNCTIONAL_ENTRY_VERSION) and (decision.get('outbox') == producer_pin) and (review_pin in decision.get('evidence', [])) and (decision.get('coordinator_role') == decision.get('decision_actor') == decision.get('responsible_assistant') == role) and (decision.get('next_owner') == role) and (decision.get('next_action') == 'adopt-' + WEEKLY_FUNCTIONAL_ENTRY_VERSION) and (decision.get('business_goal_closed') is False) and (decision.get('qa_status') != 'pass'), 'actual independent source-only adoption decision must bind the accepted helper manifest')
    _committed(root, decision)
    _v5_source_decision_fence(root, decision, role)
    source = {key: continuation[key] for key in ('task_id', 'scope', 'candidate_version', 'candidate_manifest', 'source_qa', 'review_plan', 'producer_outbox', 'prepared_only', *V5_REVIEW_FLAGS)}
    source['schema'] = 'flashcast-actual-source-review-input/v1'
    spec = importlib.util.spec_from_file_location('_flashcast_permanent_weekly_source_context', w.safe_path(root, helper_pin['path']))
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    require(helper.TASK == WEEKLY_FUNCTIONAL_ENTRY_TASK and helper.VERSION == WEEKLY_FUNCTIONAL_ENTRY_VERSION and helper.SOURCE_PATHS == WEEKLY_FUNCTIONAL_ENTRY_PATHS, 'exact new-goal two-source helper required')
    (manifest, reviewed, actual_decision, identity) = helper.review_context(root, manifest_pin, source, decision['record_id'], role, decision.get('coordinator_owner'))
    require(actual_decision == decision and identity == {'task_id': WEEKLY_FUNCTIONAL_ENTRY_TASK, 'sender_department': 'system-development', 'candidate_version': WEEKLY_FUNCTIONAL_ENTRY_VERSION, 'result_sha256': reviewed['producer_pin']['sha256']}, 'exact actual new repair producer and independent decision identity required')
    previous_native = doc(root, native_continuation_pin)
    previous_boundary = doc(root, source_repair_continuation_pin)
    require(previous_native.get('schema') == 'actual_native_control_source_continuation/v1' and previous_native.get('task_id') == NATIVE_SOURCE_TASK and (previous_native.get('historical_V5_manifest') == old_manifest_pin) and (previous_boundary.get('schema') == 'actual_acceptance_message_historical_adoption_source_continuation/v1') and (previous_boundary.get('task_id') == SOURCE_REPAIR_TASK) and (previous_boundary.get('historical_V5_manifest') == old_manifest_pin) and (previous_boundary.get('original_native_control_continuation') == native_continuation_pin), 'immutable exact V5/V6/boundary predecessor links required')
    native_manifest = doc(root, previous_native.get('candidate_manifest'))
    boundary_manifest = doc(root, previous_boundary.get('candidate_manifest'))
    original_installed = {row['path']: {'path': row['path'], **row['after']} for row in native_manifest['files']}
    original_installed.update({row['path']: {'path': row['path'], **row['after']} for row in boundary_manifest['files']})
    previous_weekly = doc(root, weekly_continuation_pin)
    require(previous_weekly.get('candidate_version') == WEEKLY_SOURCE_VERSION and previous_weekly.get('task_id') == WEEKLY_SOURCE_TASK and previous_weekly.get('historical_V5_manifest') == old_manifest_pin and previous_weekly.get('original_native_control_continuation') == native_continuation_pin and previous_weekly.get('original_source_repair_continuation') == source_repair_continuation_pin, 'exact original independently adopted V2 predecessor required')
    previous_weekly_manifest = doc(root, previous_weekly['candidate_manifest'])
    original_installed.update({row['path']: {'path': row['path'], **row['after']} for row in previous_weekly_manifest['files']})
    previous_key = doc(root, repair_continuation_pin)
    require(previous_key.get('schema') == 'actual_weekly_native_lineage_key_contract_repair_continuation/v1'
        and previous_key.get('task_id') == WEEKLY_KEY_REPAIR_TASK and previous_key.get('scope') == WEEKLY_KEY_REPAIR_SCOPE
        and previous_key.get('candidate_version') == WEEKLY_KEY_REPAIR_VERSION
        and previous_key.get('original_weekly_native_source_continuation') == weekly_continuation_pin
        and previous_key.get('historical_V5_manifest') == old_manifest_pin
        and previous_key.get('original_native_control_continuation') == native_continuation_pin
        and previous_key.get('original_source_repair_continuation') == source_repair_continuation_pin,
        'new goal may only succeed the actual original V4 endpoint')
    key_manifest = doc(root, previous_key['candidate_manifest'])
    require(len(key_manifest.get('files', [])) == len(WEEKLY_KEY_REPAIR_PATHS)
        and {row.get('path') for row in key_manifest['files']} == WEEKLY_KEY_REPAIR_PATHS,
        'original V4 endpoint remains the exact three-target layer')
    original_installed.update({row['path']: {'path': row['path'], **row['after']} for row in key_manifest['files']})
    operations = journal.get('source_operations', [])
    require(journal.get('task_id') == WEEKLY_FUNCTIONAL_ENTRY_TASK and journal.get('candidate_version') == WEEKLY_FUNCTIONAL_ENTRY_VERSION and (journal.get('candidate_fingerprint') == manifest['candidate_fingerprint']) and (journal.get('candidate_manifest') == manifest_pin) and (journal.get('review_outbox') == reviewed['review_pin']) and (journal.get('authorized_source') == reviewed['authority_pin']) and (journal.get('actor') == role) and (journal.get('direction') == 'forward') and (journal.get('status') == 'complete') and (type(journal.get('external_writes')) is int) and (journal['external_writes'] == 0) and (journal.get('effect_uncertain') is False) and (journal.get('permissions_issued') is False) and (journal.get('source_effect_state') == 'ALL_REVIEWED_AFTER_VERIFIED') and (type(journal.get('operator_source_syscalls_attempted')) is int) and (journal['operator_source_syscalls_attempted'] == len(WEEKLY_FUNCTIONAL_ENTRY_PATHS)) and isinstance(journal.get('execution_id'), str) and bool(journal['execution_id'].strip()) and (len(operations) == len(WEEKLY_FUNCTIONAL_ENTRY_PATHS)) and ({row.get('path') for row in operations} == WEEKLY_FUNCTIONAL_ENTRY_PATHS) and (len(journal.get('applied', [])) == len(WEEKLY_FUNCTIONAL_ENTRY_PATHS)) and (set(journal['applied']) == WEEKLY_FUNCTIONAL_ENTRY_PATHS), 'actual complete independent two-target repair CAS journal required')
    installed = {}
    for row in manifest['files']:
        path = row['path']
        require(row.get('before') != {'exists': False} and (path not in original_installed or row['before'] == {key: original_installed[path][key] for key in ('sha256', 'size')}), 'new repair before must preserve exact verified original V6 overlap')
        operation = next((value for value in operations if value['path'] == path))
        backup = pin(root, operation.get('backup'))
        candidate = pin(root, row.get('candidate'))
        baseline = pin(root, row.get('baseline'))
        require(operation.get('before') == row['before'] == {key: baseline[key] for key in ('sha256', 'size')} == {key: backup[key] for key in ('sha256', 'size')} and operation.get('after_expected') == operation.get('after_actual') == row['after'] == {key: candidate[key] for key in ('sha256', 'size')} and (operation.get('write_attempted') is True) and (operation.get('verified_after') is True) and (operation.get('source_syscall_attempted') is True) and (operation.get('temporary_path') == path + '.cas-' + journal['execution_id']) and (backup['path'] == f"backups/{WEEKLY_FUNCTIONAL_ENTRY_TASK}/{manifest['candidate_fingerprint']}/forward/" + path) and backup['path'].startswith(f"backups/{WEEKLY_FUNCTIONAL_ENTRY_TASK}/{manifest['candidate_fingerprint']}/forward/") and (type(operation.get('before_mode')) is int) and (operation['before_mode'] == row.get('before_mode')) and (w.safe_path(root, backup['path']).stat().st_mode & 511 == operation['before_mode']) and (w.safe_path(root, baseline['path']).stat().st_mode & 511 == row['before_mode']) and (w.safe_path(root, path).stat().st_mode & 511 == row.get('after_mode')), 'exact new repair original backup, before/write/readback effects and installed modes required')
        installed[path] = pin(root, {'path': path, **row['after']})
    follows = [row for row in handoffs if row.get('record_id') == continuation.get('adoption_followthrough_record_id')]
    require(len(follows) == 1, 'unique actual new repair adopted-effects followthrough required')
    follow = follows[0]
    require(follow.get('event') == 'controller_followthrough' and follow.get('followthrough_status') == 'blocked_with_owner' and (c.exact_identity(follow) == identity) and (follow.get('outbox') == reviewed['producer_pin']) and (follow.get('coordinator_role') == follow.get('decision_actor') == follow.get('responsible_assistant') == role) and (follow.get('coordinator_owner') == decision.get('coordinator_owner')) and (follow.get('coordination_fence') == decision.get('coordination_fence')) and (follow.get('business_goal_closed') is False) and (follow.get('unblock_condition') == 'source-adopted:' + journal['execution_id'] + ';remaining:original-weekly-functional-and-source-goal-formal-QA') and (journal_pin in follow.get('evidence', [])) and (handoffs.index(decision) < handoffs.index(follow)), 'exact new repair committed installed-source readback and original consumer boundaries required')
    _committed(root, follow)
    audit = _v5_source_decision_fence(root, follow, role)
    box = doc(root, reviewed['review_pin'])
    moments = [w._parse_observed_at(value) for value in (box.get('created_at'), journal.get('started_at'), journal.get('completed_at'))]
    require(all((value is not None for value in moments)) and moments == sorted(moments) and (moments[-1] <= dt.datetime.now(dt.timezone.utc)) and (moments[-1].timestamp() <= audit['reserved_at'] <= audit['committed_at']), 'ordered independent new repair review, CAS and permanent committed followthrough required')
    _source_release_readback(root, follow, audit)
    return installed


def _source_release_readback(root, effect, fence_audit):
    """Prove an actual release from read-only audit and non-secret claim columns."""
    import sqlite3
    import os
    import result_coordination as c
    database = w.safe_path(root, str(c.DATABASE))
    require(database.is_file() and not database.is_symlink(), "actual coordination database required")
    connection = sqlite3.connect(os.fsdecode(database.as_uri()) + "?mode=ro", uri=True)
    try:
        records = connection.execute("SELECT seq,payload_json,previous_hash,record_hash FROM coordination_audit ORDER BY seq").fetchall()
        claims = connection.execute("SELECT identity_json,role,owner,fence,expires FROM claims WHERE result_key=?", (c._key(c.exact_identity(effect)),)).fetchall()
    finally:
        connection.close()
    identity = c.exact_identity(effect)
    previous = ""
    exact = []
    for seq, raw, before, recorded in records:
        value = json.loads(raw)
        require(before == previous and recorded == c._sha([previous,value]), "complete permanent release audit chain changed")
        previous = recorded
        if value.get("identity") == identity:
            exact.append((seq,value))
    changes = [(seq,value) for seq,value in exact if value.get("event") in {"claim","recover_expired","transfer","release"}
        and type(value.get("at")) in (int,float) and value["at"] >= fence_audit["committed_at"]]
    require(changes and changes[0][1].get("event") == "release"
        and changes[0][1].get("details", {}).get("previous_owner") == effect.get("coordinator_owner")
        and isinstance(changes[0][1].get("details", {}).get("reason"),str)
        and bool(changes[0][1]["details"]["reason"].strip()),
        "actual original source-effect owner must release before any later claim")
    released_seq,released = changes[0]
    prior_changes = [(seq,value) for seq,value in exact if seq < released_seq
        and value.get("event") in {"claim","recover_expired","transfer","release"}]
    require(prior_changes and prior_changes[-1][1].get("event") in {"claim","recover_expired"}
        and all(prior_changes[-1][1].get("details", {}).get(key) == val for key,val in
            {"role":effect.get("coordinator_role"),"owner":effect.get("coordinator_owner"),"fence":effect.get("coordination_fence")}.items()),
        "original effect release must retain its committed owner/fence")
    # A later legitimate formal review may claim and release this same result.
    # Authenticate its final release instead of erasing or rejecting that history.
    final_seq,final_release = changes[-1]
    final_claims = [(seq,value) for seq,value in exact if seq < final_seq
        and value.get("event") in {"claim","recover_expired","transfer","release"}]
    require(final_release.get("event") == "release" and final_claims
        and final_claims[-1][1].get("event") in {"claim","recover_expired"}
        and final_claims[-1][1].get("details", {}).get("role") == effect.get("coordinator_role")
        and final_release.get("details", {}).get("previous_owner") == final_claims[-1][1].get("details", {}).get("owner")
        and type(final_claims[-1][1].get("details", {}).get("fence")) is int,
        "latest same-capability source-result claim must be genuinely released")
    final_fence = final_claims[-1][1]["details"]["fence"]
    require(len(claims) == 1 and json.loads(claims[0][0]) == identity
        and claims[0][1] == claims[0][2] == "" and claims[0][3] == final_fence + 1
        and claims[0][4] == 0 and effect["coordination_fence"] <= final_fence
        and fence_audit["committed_at"] <= released["at"] <= final_release["at"] <= dt.datetime.now(dt.timezone.utc).timestamp(),
        "actual released source result cannot retain an active owner")
    return {"released_at":released["at"],"source_release_proved":True,"read_only":True}
