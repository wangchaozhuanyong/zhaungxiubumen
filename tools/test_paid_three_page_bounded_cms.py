"""Isolated candidate-consumer checks; no fixture is real production evidence.

Original three-row field bytes are copied read-only into a project-owned test
directory. Native responsibility, original receipt admission, generic outbox
admission and transaction commitment are fixture services. Row recomputation,
native UTF-8, bounded identity, preflight and decision validation run for real.
"""
from __future__ import annotations

import ast
import copy
import datetime as dt
import hashlib
import json
from pathlib import Path
import tempfile
import types
import sys
import unittest
from unittest import mock

# Keep candidate consumers first; original unchanged dependencies are read
# from the confirmed company tools directory, including direct script runs.
for _parent in Path(__file__).resolve().parents:
    if (_parent / "data/task-contract.json").is_file() and (_parent / "tools").is_dir():
        if str(_parent / "tools") not in sys.path:
            sys.path.append(str(_parent / "tools"))
        break

import goal_delivery_runtime as g
import paid_three_page_bounded_cms as b
import qa_review_plan as q
import scoped_candidate_adoption as adoption
import workflow_control as w


def project_root(source=__file__):
    for parent in Path(source).resolve().parents:
        if (parent / "data/task-contract.json").is_file() and (parent / "tools").is_dir():
            return parent
    raise RuntimeError("Confirmed FLASH CAST project root is required")


REAL = project_root()


def package_root(source=__file__):
    source = Path(source).resolve()
    for parent in source.parents:
        if source.parent == parent / "candidate/tools" and (parent / "candidate/tools/paid_three_page_bounded_cms.py").is_file():
            return parent
    return project_root(source) / "logs/handoffs/2026-10-11-paid-three-page-v5-source-and-effect-compatibility-v1/developer-v2"


PACKAGE = package_root()
TMP = PACKAGE / "checks/agent-v4-tmp"
SOURCE = REAL / b.BASE
UTC = dt.timezone.utc
V4 = SOURCE / "production-forward-preview-v4"
A2_SOURCES = REAL / "logs/handoffs/2026-10-10-paid-three-page-original-followthrough-v1/assistant2-owned"
COHERENCE_SOURCE = A2_SOURCES / "T3-v4-workflow-9f917-runtime-5237-source-equivalence-preliminary-v1.json"


def candidate_issuer_functions():
    """Load full candidate bytes at their adopted location without writing it.

    Import-time registrations are read from the confirmed company. All consumer
    calls below use their isolated fixture root. No CLI, endpoint, network,
    credential lookup or permit issuance is executed.
    """
    source = PACKAGE / "candidate/tools/managed_cms_permit_issuer.py"
    module = types.ModuleType("candidate_managed_cms_permit_issuer_fixture")
    module.__file__ = str(REAL / "tools/managed_cms_permit_issuer.py")
    module.__package__ = ""
    with mock.patch.object(sys, "path", list(sys.path)):
        exec(compile(source.read_bytes(), str(source), "exec"), module.__dict__)
    return module


class BoundedCMSFixture(unittest.TestCase):
    def setUp(self):
        self.assertTrue(TMP.is_relative_to(REAL))
        TMP.mkdir(parents=True, exist_ok=True)
        temp = tempfile.TemporaryDirectory(prefix="bounded-cms-", dir=TMP)
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.assertTrue(self.root.is_relative_to(PACKAGE))
        self.now = dt.datetime.now(UTC)
        self.review_time = self.now - dt.timedelta(seconds=60)
        self.continue_time = self.now - dt.timedelta(seconds=50)
        self.fixed = "fixture-fixed-A2"
        self.registry = {b.ROLE: {"chat_binding": {"task_id": self.fixed, "cwd": str(self.root)}}}
        self.registry[b.PRODUCER] = {"chat_binding": {"task_id": "fixture-fixed-publishing", "cwd": str(self.root)}, "approved_subskills": []}
        self.source_pins = []
        for rel in b.SOURCES:
            source = PACKAGE / "candidate" / rel
            self.source_pins.append(self.raw(rel, source.read_bytes()))
        self.authority_pin = self.write("evidence/human.json", {"source": "fixture-human-service"})
        self.contract_pin = self.write("evidence/original-goal.json", {"scope": b.SCOPE})
        self.plan_pin = self.write("evidence/original-plan.json", {"task_id": b.TASK, "scope": b.SCOPE})
        self.snapshot = {"task_id": b.TASK, "goal_contract": self.contract_pin,
            "goal_delivery": {"source_mode": "owner_direct", "primary_owner": b.PRODUCER,
                "producer_departments": [b.PRODUCER], "authorized_scope": [b.SCOPE],
                "acceptance_capability": "cms", "responsible_assistant": b.ROLE,
                "authorization_pin": self.authority_pin}}
        original = json.loads((SOURCE / "outbox-v2.json").read_text())
        bindings = json.loads((SOURCE / "three-page-current-exact-bindings-v1.json").read_text())
        self.bindings = copy.deepcopy(bindings)
        actual_checks = json.loads((SOURCE / "production-followthrough-v3/actual-fresh-three-row-CAS-and-candidate-reuse-check-v3.json").read_text())
        self.checks = copy.deepcopy(actual_checks)
        self.artifacts = []
        self.backups = []
        for binding, fresh in zip(self.bindings["records"], self.checks["records"]):
            slug = binding["slug"]
            before_path = Path(binding["backup"]["path"])
            after_path = Path(binding["candidate"]["path"])
            binding["backup"] = self.raw(f"rows/{slug}.before.json", before_path.read_bytes())
            binding["candidate"] = self.raw(f"rows/{slug}.after.json", after_path.read_bytes())
            fresh_backup_path = REAL / fresh["backup"]["path"]
            typed_path = REAL / fresh["typed_preview"]["path"]
            fresh["backup"] = self.raw(f"rows/{slug}.fresh-before.json", fresh_backup_path.read_bytes())
            fresh["typed_preview"] = self.raw(f"rows/{slug}.typed.json", typed_path.read_bytes())
            self.artifacts.append(fresh["typed_preview"])
            self.backups.append(fresh["backup"])
        self.bindings_pin = self.write("evidence/bindings.json", self.bindings)
        self.original = {"schema_version": "2.0", "task_id": b.TASK, "department": b.PRODUCER,
            "candidate_version": b.VERSION, "evidence": {"bindings": self.bindings_pin}}
        self.original_pin = self.write("evidence/original-producer.json", self.original)
        self.manifest = {"task_id": b.TASK, "candidate_version": b.VERSION,
            "artifact_pins": self.artifacts, "fresh_backup_pins": self.backups}
        self.manifest_pin = self.write("evidence/current-manifest.json", self.manifest)
        self.checks_pin = self.write("evidence/current-checks.json", self.checks)
        self.current = {"schema_version": "2.0", "task_id": b.TASK, "department": b.PRODUCER,
            "candidate_version": b.VERSION, "evidence": {"original_V2": self.original_pin,
                "manifest": self.manifest_pin, "fresh_CAS_input_checks": self.checks_pin}}
        machine_source = SOURCE / "production-followthrough-v3/actual-authorization-review-and-machine-channel-readback-v3.json"
        self.machine_origin_pin = self.raw("evidence/original-machine-source.json", machine_source.read_bytes())
        self.current["evidence"]["original_authority_review_machine_channel"] = self.machine_origin_pin
        self.current_pin = self.write("evidence/current-producer.json", self.current)
        self.origin = {"prepared_only": True, "proof": {"producer_outbox": self.original_pin}}
        self.receipts = [{"receipt_id": "fixture-current-publisher-receipt", "receipt_type": "outbox_received",
            "department": b.PRODUCER, "evidence": [self.current_pin]}]
        self.actual_producer_native = b._producer_native
        patches = [mock.patch.object(g, "restore_goal", side_effect=lambda root, snap: snap),
            mock.patch.object(g, "enabled", return_value=True), mock.patch.object(g, "validate_goal", return_value=self.snapshot["goal_delivery"]),
            mock.patch.object(q, "_review_context", side_effect=lambda root, snap: snap),
            mock.patch.object(q, "_goal_reviewer", side_effect=lambda root, snap: snap["goal_delivery"]["responsible_assistant"]),
            mock.patch.object(q, "owner_direct_review_context", return_value=self.origin),
            mock.patch.object(q, "_binding", return_value={"pin": self.plan_pin}),
            mock.patch.object(w, "_validate_receipt_chain", side_effect=lambda *args, **kwargs: (self.receipts, [])),
            mock.patch.object(w, "validate_workflow_events", return_value=[]),
            mock.patch.object(w, "validate_outbox", return_value=None),
            mock.patch.object(w, "department_registry", return_value=self.registry),
            mock.patch.object(w, "_chat_binding_healthy", return_value=True),
            mock.patch.object(b, "_producer_native", return_value=None),
            mock.patch.object(adoption, "_committed", return_value=None)]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        self.write_snapshot()
        self.rows, _, _ = b._rows(self.root, self.current)
        self.target_map = b.targets(self.root)
        self.preflight_docs = []
        for row in self.rows:
            self.preflight_docs.append(self.make_preflight(row))
        self.box = self.make_box()
        self.sync_box()

    def raw(self, rel, raw):
        path = self.root / rel
        self.assertTrue(path.is_relative_to(self.root))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        return w.file_digest(self.root, rel)

    def write(self, rel, value):
        return self.raw(rel, (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8"))

    def write_snapshot(self):
        self.write(str(w.snapshot_path(self.root, b.TASK).relative_to(self.root)), self.snapshot)

    def make_preflight(self, row, operation="publish", version=None):
        identity = {"task_id": b.TASK, "action_id": row["action_id"], "action_class": "cms_write",
            "scope": row["scope"], "department": b.PRODUCER, "candidate_version": version or b.VERSION,
            "record_id": row["record_id"], "operation": operation}
        prefix = f"preflight/{row['slug']}-{operation}"
        payload = hashlib.sha256((row["action_id"] + "fixture-payload").encode()).hexdigest()
        facts = {**identity, "raw_updated_at": row["raw_updated_at"], "native_version": row["native_version"],
            "baseline_sha256": row["baseline_sha256"], "desired_sha256": row["desired_sha256"],
            "checked_at": (self.now - dt.timedelta(seconds=70 if operation == "publish" else 28)).isoformat()}
        check = {**identity, "status": "PASS", "payload_sha256": payload,
            "protected_preview_zero_write": True, "production_endpoint_verified": True,
            "actor_workflow_run_verified": True, "single_use_state": "unused", "evidence": []}
        rollback = {**identity, "rollback_execution_ready": True, "binding_strategy": "fresh_saved_CAS_after_exact_Save",
            "backup": row["backup"], "candidate": row["candidate"]}
        item = {**identity, "risk_level": "R3", "payload_sha256": payload, "backup": row["backup"]}
        machine = self.make_machine(row, identity, payload)
        source_docs = {}
        if operation == "publish":
            snapshots = [self.raw(prefix + "/sources/" + name, b"// Isolated test fixture; not deployed source.\n")
                for name in ("service.ts", "managed-targets.ts")]
            deployment = {"status": "DEPLOYED", "actual_execution": True,
                "repository": machine["machine"]["repository"], "production_sha": machine["machine"]["main_sha"],
                "source_snapshots": snapshots}
            deployment_pin = self.write(prefix + "-deployment.json", deployment)
            source = {**identity, "status": "DEPLOYED_RESTORE_IMPLEMENTATION_VERIFIED",
                "repository": deployment["repository"], "production_sha": deployment["production_sha"],
                "saved_CAS_required": True, "protected_route": "content-publish",
                "successful_rollback_preview_performed": False, "deployment_record": deployment_pin,
                "source_snapshots": snapshots}
            source_pin = self.write(prefix + "-source-verification.json", source)
            rollback.update(stage="before_Save", restore_fields_sha256=b.digest(
                {key: b.doc(self.root, row["backup"])[key] for key in row["changed_fields"]}),
                required_after_Save=["fresh_SavedCAS", "completed_publish_permit_and_run",
                    "successful_protected_rollback_preview", "independent_rollback_acceptance", "new_single_use_rollback_permit"],
                source_verification=source_pin)
            check["evidence"] = [source_pin]
            source_docs = {"source": source, "deployment": deployment}
        else:
            rollback.update(stage="after_Save", completed_parent=self.current["evidence"]["completed_parent"],
                saved_record=self.current["evidence"]["saved_record"])
        for name, value in (("facts", facts), ("self_check", check), ("rollback", rollback)):
            item[name] = self.write(prefix + f"-{name}.json", value)
        item["machine_identity"] = self.write(prefix + "-machine.json", machine["machine"])
        return {"item": item, "facts": facts, "self_check": check, "rollback": rollback, **source_docs, **machine}

    def make_machine(self, row, identity, payload):
        origin = w.read_json(self.root / self.machine_origin_pin["path"])["actual_original_machine_channel_metadata"]
        operation = identity.get("operation", "publish")
        run_id = 38111111111 + (1 if operation == "rollback" else 0)
        machine = {**identity, "schema": "actual_t3_protected_machine_binding_v1", "payload_sha256": payload,
            "original_machine_source": self.machine_origin_pin,
            "issuer_source": next(p for p in self.source_pins if p["path"] == "tools/managed_cms_permit_issuer.py"),
            "github_actor_id": origin["existing_actor_id"], "repository": origin["repository"],
            "workflow_id": origin["workflow_id"], "workflow_path": origin["workflow_path"], "repository_id": 1248188229,
            "workflow_ref": "wangchaozhuanyong/zhuangxiuwangzhan/.github/workflows/content-publish-approved.yml@refs/heads/main",
            "run_id": run_id, "run_attempt": 1, "workflow_sha": "2" * 40, "main_sha": "1" * 40}
        run = {"id": machine["run_id"], "run_attempt": 1, "actor": {"id": machine["github_actor_id"]},
            "workflow_id": machine["workflow_id"], "path": machine["workflow_path"], "head_sha": machine["main_sha"],
            "head_branch": "main", "event": "workflow_dispatch", "conclusion": "success",
            "updated_at": (self.now - dt.timedelta(seconds=70 if operation == "publish" else 28)).isoformat()}
        probe = {"ok": True, "dry_run": True, "performed_write": False, "identity": {
            "runId": machine["run_id"], "runAttempt": 1, "actorId": machine["github_actor_id"],
            "repositoryId": machine["repository_id"], "workflowRef": machine["workflow_ref"], "workflowSha": machine["workflow_sha"]}}
        receipt = {"task_id": b.TASK, "candidate_version": identity["candidate_version"], "action_id": row["action_id"], "scope": row["scope"],
            "operation": operation, "http_status": 200, "dry_run": True, "performed_write": False,
            "external_writes": 0, "row_unchanged_after_dry_run": True}
        payload_doc = {"task_id": b.TASK, "operation": operation, "payload_sha256": payload,
            "expected_updated_at": row["raw_updated_at"]}
        for name, value in (("run_snapshot", run), ("identity_probe", probe), ("locked_preview", receipt), ("payload_digest", payload_doc)):
            machine[name] = self.write(f"preflight/{row['slug']}-{operation}-{name}.json", value)
        return {"machine": machine, "run": run, "probe": probe, "receipt": receipt, "payload": payload_doc}

    def make_box(self):
        text = f"{b.TASK}\n{b.VERSION}\n{self.current_pin['sha256']}\nPASS_CANDIDATE_ONLY：三行五字段，Save与公开核验仍待执行。"
        visible = self.raw("evidence/A2-visible-UTF8.txt", text.encode("utf-8"))
        native = {"thread": {"id": self.fixed, "cwd": str(self.root)}, "turns": [{"id": "fixture-review-turn",
            "status": "completed", "startedAt": (self.review_time - dt.timedelta(seconds=5)).timestamp(),
            "items": [{"type": "agentMessage", "id": "fixture-review-message", "phase": "final_answer", "text": text}]}]}
        self.native = native
        native_pin = self.write("evidence/A2-native.json", native)
        proof = {"schema": b.MODEL, "task_id": b.TASK, "candidate_version": b.VERSION, "reviewer": b.ROLE,
            "producer": b.PRODUCER, "verdict": "PASS_CANDIDATE_ONLY", "project_scope": b.SCOPE,
            "authority": self.authority_pin, "goal_contract": self.contract_pin, "review_plan": self.plan_pin,
            "original_producer": self.original_pin, "current_producer": self.current_pin,
            "bindings": self.bindings_pin, "source_manifest": self.manifest_pin, "rows": self.rows,
            "remaining_actions": ["exact_Save_and_SavedCAS", "public_desktop_mobile_noJS_verification"],
            "consumer_sources": self.source_pins, "execution_preflights": [x["item"] for x in self.preflight_docs],
            "original_machine_source": self.machine_origin_pin,
            **{key: False for key in b.FLAGS}}
        return {"schema_version": "2.0", "task_id": b.TASK, "department": b.ROLE, "candidate_version": b.VERSION,
            "fixed_chat_task_id": self.fixed, "status": "partial", "cms_candidate_acceptance": proof,
            **{key: False for key in b.FLAGS}, "source_turn_id": "fixture-review-turn", "source_message_id": "fixture-review-message",
            "actual_native_reply": native_pin, "visible_reply": visible, "source_reply_sha256": visible["sha256"],
            "created_at": self.review_time.isoformat(), "reply_observed_at": self.review_time.isoformat(),
            "chat_reply": {"nonempty": True, "in_current_fixed_department_chat": True,
                "message_sha256": visible["sha256"], "utf8_bytes": visible["size"],
                "source_turn_id": "fixture-review-turn", "source_message_id": "fixture-review-message"},
            "evidence": [self.plan_pin, self.current_pin, self.bindings_pin, self.manifest_pin, *self.source_pins]}

    def sync_box(self):
        self.box_pin = self.write("evidence/A2-bounded-outbox.json", self.box)
        self.continuation = {"record_id": "fixture-real-continue-record", "task_id": b.TASK,
            "event": "controller_decision", "sender_department": b.PRODUCER, "outbox": self.current_pin,
            "decision": "continue", "coordinator_role": b.ROLE, "decision_actor": b.ROLE,
            "responsible_assistant": b.ROLE, "coordination_fence": 1, "next_owner": b.PRODUCER,
            "candidate_version": b.VERSION, "business_goal_closed": False, "qa_status": "PASS_CANDIDATE_ONLY_FULL_GOAL_OPEN",
            "created_at": self.continue_time.isoformat(), "evidence": [self.box_pin]}
        self.sync_continuation()

    def sync_continuation(self):
        self.continuation["previous_hash"] = ""
        self.continuation.pop("record_hash", None)
        self.continuation["record_hash"] = w.sha256_value(self.continuation)
        rel = str(w.result_handoff_path(self.root, b.TASK).relative_to(self.root))
        self.raw(rel, (json.dumps(self.continuation, ensure_ascii=False) + "\n").encode())

    def change_preflight(self, name, key, value, index=0):
        record = self.preflight_docs[index]
        record[name][key] = value
        record["item"][name] = self.write(record["item"][name]["path"], record[name])
        self.sync_preflights()

    def sync_preflights(self):
        kind = "cms_rollback_acceptance" if "cms_rollback_acceptance" in self.box else "cms_candidate_acceptance"
        self.box[kind]["execution_preflights"] = [x["item"] for x in self.preflight_docs]
        if hasattr(self, "rollback_state"):
            self.sync_rollback()
        else:
            self.sync_box()

    def sync_source_verification(self, index=0):
        record = self.preflight_docs[index]
        record["source"]["deployment_record"] = self.write(record["source"]["deployment_record"]["path"], record["deployment"])
        source_pin = self.write(record["rollback"]["source_verification"]["path"], record["source"])
        record["rollback"]["source_verification"] = source_pin
        record["self_check"]["evidence"] = [source_pin]
        for name in ("rollback", "self_check"):
            record["item"][name] = self.write(record["item"][name]["path"], record[name])
        self.sync_preflights()

    def sync_machine(self, index=0):
        """Re-pin mutated fixtures so identity checks, not stale hashes, decide."""
        record = self.preflight_docs[index]
        for name, local in (("run_snapshot", "run"), ("identity_probe", "probe"),
                ("locked_preview", "receipt"), ("payload_digest", "payload")):
            record["machine"][name] = self.write(record["machine"][name]["path"], record[local])
        record["item"]["machine_identity"] = self.write(record["item"]["machine_identity"]["path"], record["machine"])
        self.sync_preflights()

    def prepare_rollback(self, index=0):
        """Create only an isolated, explicitly synthetic after-Save fixture."""
        issuer = candidate_issuer_functions()
        patch = mock.patch.dict(sys.modules, {"managed_cms_permit_issuer": issuer})
        patch.start(); self.addCleanup(patch.stop)
        self.rollback_issuer = issuer
        row = self.rows[index]
        before, desired = b.doc(self.root, row["backup"]), b.doc(self.root, row["candidate"])
        saved = copy.deepcopy(desired)
        saved["updated_at"] = (self.now - dt.timedelta(seconds=35)).isoformat(timespec="microseconds")
        saved["version"] = row["native_version"] + 1
        restore = {**saved, **{key: before[key] for key in row["changed_fields"]}}
        parent = {"permitId": "7ba874ae-f1aa-4152-82bd-05185c305b7f", "status": "completed",
            "operation": "publish", "taskId": b.TASK, "actionId": row["action_id"],
            "candidateVersion": b.VERSION, "githubRunId": 38111111111,
            "savedId": row["record_id"], "savedUpdatedAt": saved["updated_at"]}
        root = f"rollback/{row['slug']}"
        parent_pin, saved_pin = self.write(root + "-parent.json", parent), self.write(root + "-saved.json", saved)
        restore_pin = self.write(root + "-restore.json", restore)
        typed = {"request": {"mode": "dry-run", "contentType": "service", "expectedUpdatedAt": saved["updated_at"],
            "record": restore, "managedCandidate": {"taskId": b.TASK, "actionId": f"rollback-{b.VERSION}",
                "operation": "rollback", "scope": row["scope"], "candidateVersion": b.ROLLBACK_VERSION}}}
        typed_pin = self.write(root + "-typed.json", typed)
        original_continue, publish_box, publish_pin = copy.deepcopy(self.continuation), copy.deepcopy(self.box), self.box_pin
        self.current["evidence"].update(completed_parent=parent_pin, saved_record=saved_pin)
        self.current_pin = self.write("evidence/current-producer-after-save.json", self.current)
        self.receipts[:] = [{"receipt_id": "fixture-after-save-publisher-receipt", "receipt_type": "outbox_received",
            "department": b.PRODUCER, "evidence": [self.current_pin]}]
        recovery_row = {**row, "action_id": f"rollback-{b.VERSION}", "raw_updated_at": saved["updated_at"],
            "native_version": saved["version"], "baseline_sha256": b.digest(saved), "desired_sha256": b.digest(restore),
            "candidate": restore_pin, "typed_preview": typed_pin}
        self.preflight_docs = [self.make_preflight(recovery_row, "rollback", b.ROLLBACK_VERSION)]
        proof = {"schema": b.MODEL + "_rollback", "task_id": b.TASK, "candidate_version": b.ROLLBACK_VERSION,
            "operation": "rollback", "reviewer": b.ROLE, "producer": b.PRODUCER, "project_scope": b.SCOPE,
            "verdict": "PASS_ROLLBACK_CANDIDATE_ONLY", "row": row, "authority": self.authority_pin,
            "goal_contract": self.contract_pin, "review_plan": self.plan_pin,
            "original_producer": self.original_pin, "current_producer": self.current_pin,
            "bindings": self.bindings_pin, "source_manifest": self.manifest_pin,
            "original_machine_source": self.machine_origin_pin, "consumer_sources": self.source_pins,
            "remaining_actions": ["distinct_single_use_rollback", "restored_public_verification"],
            "publish_review_outbox": publish_pin, "publish_continue_record_id": original_continue["record_id"],
            "parent_run_id": parent["githubRunId"], "parent_permit_id": parent["permitId"],
            "completed_parent": parent_pin, "saved_record": saved_pin, "restore_candidate": restore_pin,
            "typed_preview": typed_pin, "execution_preflights": [x["item"] for x in self.preflight_docs],
            **{key: False for key in b.FLAGS}}
        self.box = copy.deepcopy(publish_box)
        self.box.pop("cms_candidate_acceptance")
        self.box.update(candidate_version=b.ROLLBACK_VERSION, cms_rollback_acceptance=proof,
            source_turn_id="fixture-rollback-review-turn", source_message_id="fixture-rollback-review-message",
            created_at=(self.now - dt.timedelta(seconds=25)).isoformat(),
            reply_observed_at=(self.now - dt.timedelta(seconds=25)).isoformat())
        self.continuation = {**original_continue, "record_id": "fixture-new-rollback-continue-record",
            "qa_status": "PASS_ROLLBACK_CANDIDATE_ONLY_FULL_GOAL_OPEN", "outbox": self.current_pin,
            "created_at": (self.now - dt.timedelta(seconds=20)).isoformat()}
        self.rollback_state = {"index": index, "path": root, "parent": parent, "saved": saved, "restore": restore,
            "typed": typed, "publish_continue": original_continue, "publish_box": publish_box, "publish_pin": publish_pin}
        self.sync_rollback()

    def sync_rollback(self):
        state, proof = self.rollback_state, self.box["cms_rollback_acceptance"]
        for field, local, suffix in (("completed_parent", "parent", "parent"), ("saved_record", "saved", "saved"),
                ("restore_candidate", "restore", "restore"), ("typed_preview", "typed", "typed")):
            proof[field] = self.write(state["path"] + f"-{suffix}.json", state[local])
        self.current["evidence"].update(completed_parent=proof["completed_parent"], saved_record=proof["saved_record"])
        self.current_pin = self.write("evidence/current-producer-after-save.json", self.current)
        self.receipts[0]["evidence"] = [self.current_pin]
        proof["current_producer"] = self.current_pin
        text = f"{b.TASK}\n{b.ROLLBACK_VERSION}\n{self.current_pin['sha256']}\nPASS_ROLLBACK_CANDIDATE_ONLY；fixture only"
        visible = self.raw("evidence/A2-rollback-visible-UTF8.txt", text.encode())
        native = {"thread": {"id": self.fixed, "cwd": str(self.root)}, "turns": [{"id": self.box["source_turn_id"],
            "status": "completed", "startedAt": (self.now - dt.timedelta(seconds=30)).timestamp(), "items": [
                {"type": "agentMessage", "id": self.box["source_message_id"], "phase": "final_answer", "text": text}]}]}
        self.box.update(visible_reply=visible, source_reply_sha256=visible["sha256"],
            actual_native_reply=self.write("evidence/A2-rollback-native.json", native))
        self.box["chat_reply"].update(message_sha256=visible["sha256"], utf8_bytes=visible["size"],
            source_turn_id=self.box["source_turn_id"], source_message_id=self.box["source_message_id"])
        self.box["evidence"] = [self.plan_pin, self.current_pin, state["publish_pin"], self.bindings_pin, self.manifest_pin,
            *self.source_pins, proof["completed_parent"], proof["saved_record"], proof["restore_candidate"], proof["typed_preview"]]
        self.box_pin = self.write("evidence/A2-independent-rollback-outbox.json", self.box)
        self.continuation.update(outbox=self.current_pin, evidence=[self.box_pin], previous_hash=state["publish_continue"]["record_hash"])
        self.continuation.pop("record_hash", None)
        self.continuation["record_hash"] = w.sha256_value(self.continuation)
        rows = [state["publish_continue"], self.continuation]
        self.raw(str(w.result_handoff_path(self.root, b.TASK).relative_to(self.root)),
            ("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n").encode())

    def rollback_accepted(self):
        return b.acceptance(self.root, self.snapshot, self.target(self.rollback_state["index"]), "rollback")

    def rollback_preflight(self):
        target = self.target(self.rollback_state["index"])
        return b.preflight(self.root, self.snapshot, f"rollback-{b.VERSION}", "cms_write", target["scope"], b.PRODUCER)

    def rollback_decision(self):
        accepted = self.rollback_accepted(); row = accepted["row"]
        return {"department": b.ROLE, "assistant_chat_task_id": self.fixed, "decision": "EXECUTE_AUTHORIZED_ACTION",
            "operation": "rollback", "task_id": b.TASK, "action_id": row["action_id"], "action_class": "cms_write",
            "scope": row["scope"], "candidate_version": b.ROLLBACK_VERSION, "record_id": row["record_id"],
            "payload_sha256": self.preflight_docs[0]["item"]["payload_sha256"],
            "candidate_acceptance_record_id": accepted["candidate_acceptance_record_id"],
            "controller_decision_record_id": accepted["candidate_acceptance_record_id"],
            "review_outbox": accepted["review_outbox"], "review_plan": accepted["review_plan"],
            "authorization_pin": accepted["authorization_pin"], "decision_id": "fixture-new-rollback-decision",
            "machine_identity": self.preflight_docs[0]["item"]["machine_identity"],
            "decided_at": (self.now - dt.timedelta(seconds=19)).isoformat()}

    def target(self, index=0):
        return self.target_map[self.rows[index]["action_id"]]

    def accepted(self, index=0):
        return b.acceptance(self.root, self.snapshot, self.target(index))

    def production_preflight(self, index=0):
        row = self.rows[index]
        return b.preflight(self.root, self.snapshot, row["action_id"], "cms_write", row["scope"], b.PRODUCER)

    def decision_value(self, index=0):
        accepted = self.accepted(index)
        row = self.rows[index]
        return {"department": b.ROLE, "assistant_chat_task_id": self.fixed, "decision": "EXECUTE_AUTHORIZED_ACTION",
            "operation": "publish", "task_id": b.TASK, "action_id": row["action_id"], "action_class": "cms_write",
            "scope": row["scope"], "candidate_version": b.VERSION, "record_id": row["record_id"],
            "payload_sha256": self.preflight_docs[index]["item"]["payload_sha256"],
            "candidate_acceptance_record_id": accepted["candidate_acceptance_record_id"],
            "controller_decision_record_id": accepted["candidate_acceptance_record_id"],
            "review_outbox": accepted["review_outbox"], "review_plan": accepted["review_plan"],
            "authorization_pin": accepted["authorization_pin"], "decision_id": "fixture-exact-decision",
            "machine_identity": self.preflight_docs[index]["item"]["machine_identity"],
            "decided_at": (self.continue_time + dt.timedelta(seconds=1)).isoformat()}


class BoundedCMSTests(BoundedCMSFixture):
    def test_original_three_rows_accept_and_keep_two_retained_digest_namespaces(self):
        for index, counts in enumerate(((29, 27), (28, 26), (28, 26))):
            with self.subTest(row=index):
                accepted = self.accepted(index)
                self.assertEqual(accepted["verdict"], "pass_candidate_only")
                self.assertEqual((accepted["row"]["retained_count"], accepted["row"]["website_retained_count"]), counts)
                self.assertNotEqual(accepted["row"]["retained_sha256"], accepted["row"]["website_retained_sha256"])
                self.assertFalse(accepted["business_goal_closed"])
                self.assertFalse(accepted["production_write_allowed"])

    def test_exact_tuple_does_not_alias_task_scope_action_class_or_executor(self):
        row = self.rows[0]
        valid = (b.TASK, row["action_id"], row["scope"], b.PRODUCER, "cms_write")
        self.assertTrue(b.exact_tuple(*valid))
        for index, wrong in enumerate(("wrong-task", "wrong-action", b.SCOPE, b.ROLE, "ads_write")):
            case = list(valid); case[index] = wrong
            with self.subTest(index=index): self.assertFalse(b.exact_tuple(*case))

    def test_wrong_target_version_or_namespace_is_rejected(self):
        for key, value in (("task_id", "wrong-task"), ("candidate_version", "old-version"),
                ("scope", b.SCOPE), ("execution_owner", b.ROLE), ("candidate_shape", "legacy")):
            target = copy.deepcopy(self.target()); target[key] = value
            with self.subTest(key=key), self.assertRaises(w.WorkflowError):
                b.acceptance(self.root, self.snapshot, target)

    def test_wrong_record_cannot_relabel_another_exact_target(self):
        target = copy.deepcopy(self.target())
        other = self.target(1)
        for key in ("record_id", "bounded_row", "changed_fields", "candidate", "rollback"):
            target[key] = copy.deepcopy(other[key])
        with self.assertRaises(w.WorkflowError): b.acceptance(self.root, self.snapshot, target)

    def test_current_goal_producer_self_review_and_scope_broadening_rejected(self):
        for key, value in (("responsible_assistant", b.PRODUCER), ("producer_departments", [b.PRODUCER, b.ROLE]),
                ("primary_owner", b.ROLE), ("authorized_scope", [b.SCOPE, "project:unrelated"]), ("source_mode", "approved_dispatch")):
            snapshot = copy.deepcopy(self.snapshot); snapshot["goal_delivery"][key] = value
            with self.subTest(key=key), self.assertRaises(w.WorkflowError):
                b.acceptance(self.root, snapshot, self.target())

    def test_sixth_field_or_retained_mutation_rejected_even_with_new_file_pins(self):
        path = self.bindings["records"][0]["candidate"]["path"]
        changed = w.read_json(self.root / path); changed["title_en"] += " unauthorized"
        self.bindings["records"][0]["candidate"] = self.write(path, changed)
        self.bindings_pin = self.write(self.bindings_pin["path"], self.bindings)
        original = copy.deepcopy(self.original); original["evidence"]["bindings"] = self.bindings_pin
        original_pin = self.write(self.original_pin["path"], original)
        current = copy.deepcopy(self.current); current["evidence"]["original_V2"] = original_pin
        with self.assertRaisesRegex(w.WorkflowError, "sixth field or retained"):
            b._rows(self.root, current)

    def test_original_digest_drift_rejected_with_self_consistent_pin(self):
        self.bindings["records"][0]["retained_fields_sha256"] = "0" * 64
        binding_pin = self.write(self.bindings_pin["path"], self.bindings)
        original = copy.deepcopy(self.original); original["evidence"]["bindings"] = binding_pin
        original_pin = self.write(self.original_pin["path"], original)
        current = copy.deepcopy(self.current); current["evidence"]["original_V2"] = original_pin
        with self.assertRaisesRegex(w.WorkflowError, "native digests"):
            b._rows(self.root, current)

    def test_current_raw_cas_drift_rejected_after_repinning_checks(self):
        self.checks["records"][0]["raw_updated_at"] = "2026-10-10T00:00:00.000001+00:00"
        pin = self.write(self.checks_pin["path"], self.checks)
        current = copy.deepcopy(self.current); current["evidence"]["fresh_CAS_input_checks"] = pin
        with self.assertRaisesRegex(w.WorkflowError, "raw CAS"):
            b._rows(self.root, current)

    def test_consumer_source_digest_drift_rejected(self):
        (self.root / self.source_pins[0]["path"]).write_bytes(b"changed consumer source")
        with self.assertRaisesRegex(w.WorkflowError, "frozen source bytes"):
            self.accepted()

    def test_bounded_identity_flags_and_remaining_scope_reject_mutations(self):
        original = copy.deepcopy(self.box)
        cases = [("task_id", "wrong-task"), ("department", b.PRODUCER), ("candidate_version", "old-cv"),
            ("status", "completed"), ("qa_verdict", "pass"), ("goal_acceptance", {"accepted_scope": [b.SCOPE]}),
            ("production_write_allowed", True), ("production_release_eligible", True), ("external_permission_issued", True)]
        for key, value in cases:
            self.box = copy.deepcopy(original); self.box[key] = value; self.sync_box()
            with self.subTest(key=key), self.assertRaises(w.WorkflowError): self.accepted()
        self.box = copy.deepcopy(original); self.box["cms_candidate_acceptance"]["remaining_actions"] = []
        self.sync_box()
        with self.assertRaisesRegex(w.WorkflowError, "bounded review differs"):
            self.accepted()

    def test_native_utf8_bytes_message_or_fixed_turn_rejected(self):
        original_box, original_native = copy.deepcopy(self.box), copy.deepcopy(self.native)
        cases = [lambda box, native: box["chat_reply"].update(utf8_bytes=1),
            lambda box, native: native["turns"][0]["items"][0].update(text="unrelated text"),
            lambda box, native: native["thread"].update(id="other-fixed-chat"),
            lambda box, native: native["thread"].update(cwd=str(self.root.parent)),
            lambda box, native: native["turns"][0].update(id="another-turn"),
            lambda box, native: native["turns"][0]["items"][0].update(text="")]
        for index, change in enumerate(cases):
            self.box = copy.deepcopy(original_box); native = copy.deepcopy(original_native)
            change(self.box, native); self.box["actual_native_reply"] = self.write("evidence/A2-native.json", native)
            self.sync_box()
            with self.subTest(index=index), self.assertRaises(w.WorkflowError): self.accepted()

    def test_native_reply_and_review_timestamp_must_precede_continue(self):
        self.box["created_at"] = (self.now + dt.timedelta(hours=1)).isoformat(); self.sync_box()
        with self.assertRaises(w.WorkflowError): self.accepted()

    def test_native_source_and_verdict_references_must_be_exact_tokens(self):
        original_box, original_native = copy.deepcopy(self.box), copy.deepcopy(self.native)
        for ref in (b.TASK, b.VERSION, self.current_pin["sha256"], "PASS_CANDIDATE_ONLY"):
            self.box = copy.deepcopy(original_box); native = copy.deepcopy(original_native)
            text = native["turns"][0]["items"][0]["text"].replace(ref, ref + "-unrelated")
            native["turns"][0]["items"][0]["text"] = text
            visible = self.raw("evidence/A2-visible-UTF8.txt", text.encode())
            self.box["visible_reply"] = visible; self.box["source_reply_sha256"] = visible["sha256"]
            self.box["chat_reply"].update(message_sha256=visible["sha256"], utf8_bytes=visible["size"])
            self.box["actual_native_reply"] = self.write("evidence/A2-native.json", native); self.sync_box()
            with self.subTest(ref=ref), self.assertRaisesRegex(w.WorkflowError, "exact source and bounded verdict"):
                self.accepted()

    def test_continue_must_be_actual_current_independent_fenced_not_accept(self):
        original = copy.deepcopy(self.continuation)
        for key, value in (("decision", "accept"), ("qa_status", "pass"), ("coordination_fence", 0),
                ("coordinator_role", b.PRODUCER), ("decision_actor", b.PRODUCER),
                ("business_goal_closed", True), ("outbox", self.original_pin)):
            self.continuation = copy.deepcopy(original); self.continuation[key] = value; self.sync_continuation()
            with self.subTest(key=key), self.assertRaises(w.WorkflowError): self.accepted()

    def test_uncommitted_continue_and_hash_chain_tamper_rejected(self):
        with mock.patch.object(adoption, "_committed", side_effect=w.WorkflowError("not committed")):
            with self.assertRaisesRegex(w.WorkflowError, "not committed"): self.accepted()
        self.continuation["record_hash"] = "0" * 64
        self.raw(str(w.result_handoff_path(self.root, b.TASK).relative_to(self.root)),
            (json.dumps(self.continuation) + "\n").encode())
        with self.assertRaises(w.WorkflowError): self.accepted()

    def test_three_exact_production_preflights_map_original_project_only(self):
        for index in range(3):
            with self.subTest(index=index):
                item = self.production_preflight(index)
                self.assertEqual(item["authorized_project_scope"], b.SCOPE)
                self.assertEqual(item["scope"], self.rows[index]["scope"])

    def test_three_reviewed_actor_a_run_a_machines_match_issuer_downloads(self):
        for index in range(3):
            with self.subTest(index=index):
                record = self.preflight_docs[index]
                accepted = self.accepted(index)
                result = b.validate_machine(self.root, record["item"], accepted)
                self.assertEqual(result["github_actor_id"], 276684684)
                self.assertEqual(result["run_id"], 38111111111)
                self.assertEqual(result, b.validate_issuer_machine(self.root, self.target(index), accepted,
                    record["run"], record["probe"], result["github_actor_id"], record["payload"], record["receipt"]))

    def test_self_consistent_actor_b_and_run_b_cannot_replace_original_actor_a(self):
        record = self.preflight_docs[0]
        record["machine"]["github_actor_id"] = 987654321
        record["machine"]["run_id"] += 1
        record["run"]["actor"]["id"] = record["machine"]["github_actor_id"]
        record["run"]["id"] = record["machine"]["run_id"]
        record["probe"]["identity"].update(actorId=record["machine"]["github_actor_id"], runId=record["machine"]["run_id"])
        self.sync_machine()
        with self.assertRaisesRegex(w.WorkflowError, "original actor/run"):
            self.production_preflight()

    def test_runtime_actor_run_attempt_workflow_and_main_cannot_replace_frozen_machine(self):
        record = self.preflight_docs[0]
        accepted = self.accepted()
        for case in ("actor", "run", "attempt", "workflowSha", "mainSha", "receipt", "payload"):
            run, probe = copy.deepcopy(record["run"]), copy.deepcopy(record["probe"])
            receipt, payload = copy.deepcopy(record["receipt"]), copy.deepcopy(record["payload"])
            actor = record["machine"]["github_actor_id"]
            if case == "actor":
                actor = 987654321; run["actor"]["id"] = actor; probe["identity"]["actorId"] = actor
                run["id"] += 1; probe["identity"]["runId"] = run["id"]
            elif case == "run":
                run["id"] += 1; probe["identity"]["runId"] = run["id"]
            elif case == "attempt":
                run["run_attempt"] += 1; probe["identity"]["runAttempt"] = run["run_attempt"]
            elif case == "workflowSha": probe["identity"]["workflowSha"] = "3" * 40
            elif case == "mainSha": run["head_sha"] = "4" * 40
            elif case == "receipt": receipt["row_unchanged_after_dry_run"] = False
            else: payload["expected_updated_at"] = "2026-10-10T00:00:00.000001+00:00"
            with self.subTest(case=case), self.assertRaisesRegex(w.WorkflowError, "CLI/download cannot replace"):
                b.validate_issuer_machine(self.root, self.target(), accepted, run, probe, actor, payload, receipt)

    def test_machine_missing_original_source_or_changed_issuer_source_rejected(self):
        record = self.preflight_docs[0]
        original = copy.deepcopy(record["machine"])
        for field, value in (("original_machine_source", self.plan_pin),
                ("issuer_source", self.source_pins[0]), ("schema", "historical_machine_readback")):
            record["machine"] = copy.deepcopy(original); record["machine"][field] = value
            self.sync_machine()
            with self.subTest(field=field), self.assertRaisesRegex(w.WorkflowError, "machine and issuer source"):
                self.production_preflight()
        record["item"].pop("machine_identity")
        self.box["cms_candidate_acceptance"]["execution_preflights"] = [x["item"] for x in self.preflight_docs]
        self.sync_box()
        with self.assertRaises(w.WorkflowError): self.production_preflight()

    def test_machine_run_snapshot_and_server_probe_must_bind_exact_fields(self):
        record = self.preflight_docs[0]
        original = copy.deepcopy(record)
        for field, value in (("run_attempt", 2), ("workflow_id", 111), ("path", "other.yml"),
                ("head_sha", "4" * 40), ("head_branch", "feature"), ("event", "push"), ("conclusion", "failure")):
            record.update(copy.deepcopy(original)); record["run"][field] = value; self.sync_machine()
            with self.subTest(field=field), self.assertRaisesRegex(w.WorkflowError, "server OIDC probe"):
                self.production_preflight()
        for field in ("runId", "runAttempt", "actorId", "repositoryId", "workflowRef", "workflowSha"):
            record.update(copy.deepcopy(original)); record["probe"]["identity"].pop(field); self.sync_machine()
            with self.subTest(probe_field=field), self.assertRaisesRegex(w.WorkflowError, "server OIDC probe"):
                self.production_preflight()

    def test_machine_preview_payload_and_raw_cas_are_zero_write_exact_and_fresh(self):
        record = self.preflight_docs[0]
        original = copy.deepcopy(record)
        cases = [("receipt", "http_status", 401), ("receipt", "dry_run", False),
            ("receipt", "performed_write", True), ("receipt", "external_writes", 1),
            ("receipt", "row_unchanged_after_dry_run", False), ("receipt", "scope", b.SCOPE),
            ("receipt", "operation", "rollback"), ("payload", "payload_sha256", "0" * 64),
            ("payload", "expected_updated_at", "2026-10-10T00:00:00.000001+00:00")]
        for local, field, value in cases:
            record.update(copy.deepcopy(original)); record[local][field] = value; self.sync_machine()
            with self.subTest(local=local, field=field), self.assertRaisesRegex(w.WorkflowError, "zero-write preview/payload/raw CAS"):
                self.production_preflight()
        for stamp in ((self.now - dt.timedelta(hours=1)).isoformat(), (self.now + dt.timedelta(hours=1)).isoformat()):
            record.update(copy.deepcopy(original)); record["run"]["updated_at"] = stamp; self.sync_machine()
            with self.subTest(stamp=stamp), self.assertRaisesRegex(w.WorkflowError, "stale or future"):
                self.production_preflight()

    def test_decision_cannot_replace_frozen_machine_identity(self):
        value = self.decision_value(); accepted = self.accepted()
        value["machine_identity"] = self.preflight_docs[1]["item"]["machine_identity"]
        with self.assertRaisesRegex(w.WorkflowError, "exact routine continue"):
            b.decision(self.root, value, self.target(), value["payload_sha256"], accepted, self.now)

    def test_issuer_policy_requires_same_consumed_continue_and_machine(self):
        issuer = candidate_issuer_functions()
        operations = self.decision_value(); target = self.target()
        policy = {"status": "allow", "department": b.PRODUCER, "task_id": b.TASK,
            "action_id": target["action_id"], "action_class": "cms_write", "scope": target["scope"],
            "payload_sha256": operations["payload_sha256"], "approval_status": "consumed",
            "decision_id": "fixture-policy-decision", "checked_at": (self.now - dt.timedelta(seconds=10)).isoformat(),
            "cms_candidate_acceptance": {"acceptance_model": b.MODEL,
                "candidate_acceptance_record_id": operations["candidate_acceptance_record_id"],
                "machine_identity": operations["machine_identity"]}}
        self.assertEqual(issuer.validate_policy(policy, target, "publish", operations["payload_sha256"], operations, self.now), policy)
        for key, value in (("candidate_acceptance_record_id", "historical-continue"),
                ("machine_identity", self.preflight_docs[1]["item"]["machine_identity"]),
                ("acceptance_model", "goal_delivery_assistant_v1")):
            changed = copy.deepcopy(policy); changed["cms_candidate_acceptance"][key] = value
            with self.subTest(key=key), self.assertRaisesRegex(issuer.PermitEvidenceError, "same actual A2-frozen"):
                issuer.validate_policy(changed, target, "publish", operations["payload_sha256"], operations, self.now)
        for key, value in (("approval_status", "active"), ("checked_at", (self.now - dt.timedelta(hours=1)).isoformat())):
            changed = copy.deepcopy(policy); changed[key] = value
            with self.subTest(key=key), self.assertRaises(issuer.PermitEvidenceError):
                issuer.validate_policy(changed, target, "publish", operations["payload_sha256"], operations, self.now)

    def test_missing_actor_endpoint_preview_and_replayed_permission_rejected(self):
        original = copy.deepcopy(self.preflight_docs[0]["self_check"])
        for key, value in (("actor_workflow_run_verified", False), ("production_endpoint_verified", False),
                ("protected_preview_zero_write", False), ("single_use_state", "consumed")):
            self.preflight_docs[0]["self_check"] = copy.deepcopy(original)
            self.change_preflight("self_check", key, value)
            with self.subTest(key=key), self.assertRaisesRegex(w.WorkflowError, "endpoint/actor"):
                self.production_preflight()

    def test_absent_actor_endpoint_cas_and_single_use_members_fail_closed(self):
        record = self.preflight_docs[0]
        original_check, original_facts = copy.deepcopy(record["self_check"]), copy.deepcopy(record["facts"])
        for name, key in (("self_check", "actor_workflow_run_verified"), ("self_check", "production_endpoint_verified"),
                ("self_check", "single_use_state"), ("facts", "raw_updated_at"), ("facts", "checked_at")):
            record["self_check"], record["facts"] = copy.deepcopy(original_check), copy.deepcopy(original_facts)
            record[name].pop(key)
            for restored in ("self_check", "facts"):
                record["item"][restored] = self.write(record["item"][restored]["path"], record[restored])
            self.box["cms_candidate_acceptance"]["execution_preflights"] = [x["item"] for x in self.preflight_docs]
            self.sync_box()
            reason = "endpoint/actor" if name == "self_check" else "CAS/self-check" if key == "raw_updated_at" else "fresh authenticated"
            with self.subTest(name=name, key=key), self.assertRaisesRegex(w.WorkflowError, reason): self.production_preflight()

    def test_stale_cas_and_changed_raw_timestamp_rejected(self):
        self.change_preflight("facts", "checked_at", (self.now - dt.timedelta(hours=1)).isoformat())
        with self.assertRaisesRegex(w.WorkflowError, "fresh authenticated"): self.production_preflight()
        self.change_preflight("facts", "checked_at", self.now.isoformat())
        self.change_preflight("facts", "raw_updated_at", "2026-10-10T00:00:00.000001+00:00")
        with self.assertRaisesRegex(w.WorkflowError, "CAS/self-check"): self.production_preflight()

    def test_before_save_plan_requires_future_gates_and_verified_deployed_sources(self):
        self.change_preflight("rollback", "rollback_execution_ready", False)
        with self.assertRaisesRegex(w.WorkflowError, "executable recovery plan"): self.production_preflight()
        self.change_preflight("rollback", "rollback_execution_ready", True)
        self.change_preflight("rollback", "stage", "after_Save")
        with self.assertRaisesRegex(w.WorkflowError, "before-Save plan"): self.production_preflight()
        self.change_preflight("rollback", "stage", "before_Save")
        required = copy.deepcopy(self.preflight_docs[0]["rollback"]["required_after_Save"])
        self.change_preflight("rollback", "required_after_Save", required[:-1])
        with self.assertRaisesRegex(w.WorkflowError, "every later SavedCAS"): self.production_preflight()
        self.change_preflight("rollback", "required_after_Save", required)
        self.change_preflight("rollback", "source_verification", None)
        with self.assertRaisesRegex(w.WorkflowError, "deployed recovery source proof"): self.production_preflight()

    def test_before_save_deployed_source_is_exact_and_does_not_claim_restore_pass(self):
        record = self.preflight_docs[0]
        original = copy.deepcopy(record)
        for key, value in (("status", "NOT_DEPLOYED"), ("successful_rollback_preview_performed", True),
                ("saved_CAS_required", False), ("protected_route", "other-route"), ("production_sha", "3" * 40)):
            record.update(copy.deepcopy(original)); record["source"][key] = value; self.sync_source_verification()
            with self.subTest(key=key), self.assertRaisesRegex(w.WorkflowError,
                    "deployed original recovery implementation|exact actual deployment/source version required"):
                self.production_preflight()
        for key, value in (("status", "PREPARED"), ("actual_execution", False), ("production_sha", "3" * 40)):
            record.update(copy.deepcopy(original)); record["deployment"][key] = value; self.sync_source_verification()
            with self.subTest(deployment_key=key), self.assertRaisesRegex(w.WorkflowError, "exact actual deployment/source"):
                self.production_preflight()
        record.update(copy.deepcopy(original)); record["source"]["source_snapshots"] = []
        self.sync_source_verification()
        with self.assertRaisesRegex(w.WorkflowError, "deployed restore source snapshots"): self.production_preflight()
        record.update(copy.deepcopy(original)); self.sync_source_verification()
        snapshot = record["source"]["source_snapshots"][0]
        (self.root / snapshot["path"]).write_bytes(b"changed deployed source snapshot")
        with self.assertRaisesRegex(w.WorkflowError, "frozen source bytes changed"): self.production_preflight()

    def test_before_save_409_guard_is_separate_from_successful_rollback_preview(self):
        guard = {"http_status": 409, "performed_write": False, "external_writes": 0,
            "expected_baseline_rejection": True, "successful_rollback_preview_performed": False}
        pin = self.write("preflight/builtin-baseline-guard.json", guard)
        self.change_preflight("rollback", "guard_evidence", pin)
        self.assertEqual(self.production_preflight()["authorized_project_scope"], b.SCOPE)
        for key, value in (("http_status", 200), ("performed_write", True), ("external_writes", 1),
                ("expected_baseline_rejection", False), ("successful_rollback_preview_performed", True)):
            changed = {**guard, key: value}
            pin = self.write("preflight/builtin-baseline-guard.json", changed)
            self.change_preflight("rollback", "guard_evidence", pin)
            with self.subTest(key=key), self.assertRaisesRegex(w.WorkflowError, "409 proves the baseline guard"):
                self.production_preflight()

    def test_original_routine_decision_uses_real_continue_id_without_qa_receipt(self):
        for index in range(3):
            value = self.decision_value(index); accepted = self.accepted(index)
            result = b.decision(self.root, value, self.target(index), value["payload_sha256"], accepted, self.now)
            self.assertEqual(result["candidate_acceptance_record_id"], self.continuation["record_id"])
            self.assertNotIn("qa_receipt_id", result)

    def test_decision_wrong_actor_scope_payload_receipt_and_qa_alias_rejected(self):
        accepted = self.accepted(); original = self.decision_value()
        for key, value in (("department", b.PRODUCER), ("scope", b.SCOPE), ("payload_sha256", "0"*64),
                ("controller_decision_record_id", "fake-record"), ("qa_receipt_id", "fake-qa")):
            changed = copy.deepcopy(original); changed[key] = value
            with self.subTest(key=key), self.assertRaises(w.WorkflowError):
                b.decision(self.root, changed, self.target(), original["payload_sha256"], accepted, self.now)

    def test_full_goal_acceptance_function_keeps_exact_original_bytes(self):
        def function_bytes(path):
            raw = path.read_text(); tree = ast.parse(raw)
            node = next(x for x in tree.body if isinstance(x, ast.FunctionDef) and x.name == "_validate_goal_acceptance")
            return "".join(raw.splitlines(keepends=True)[node.lineno-1:node.end_lineno])
        self.assertEqual(function_bytes(REAL / "tools/qa_review_plan.py"), function_bytes(PACKAGE / "candidate/tools/qa_review_plan.py"))

    def test_candidate_and_adopted_test_paths_share_confirmed_project_output(self):
        for source in (PACKAGE / "candidate/tools/test_paid_three_page_bounded_cms.py", REAL / "tools/test_paid_three_page_bounded_cms.py"):
            self.assertEqual(project_root(source), REAL)
            self.assertEqual(package_root(source), PACKAGE)
            self.assertTrue(TMP.is_relative_to(project_root(source)))
            self.assertEqual(TMP, PACKAGE / "checks/agent-v4-tmp")
            self.assertNotEqual(TMP.parent, REAL.parent)

    def test_missing_manifest_membership_and_ambiguous_source_json_rejected(self):
        manifest = copy.deepcopy(self.manifest); manifest["artifact_pins"] = []
        current = copy.deepcopy(self.current)
        current["evidence"]["manifest"] = self.write(self.manifest_pin["path"], manifest)
        with self.assertRaises(w.WorkflowError): b._rows(self.root, current)
        duplicate = self.raw("evidence/duplicate-source.json", b'{"task_id":"first","task_id":"second"}')
        with self.assertRaisesRegex(w.WorkflowError, "unambiguous"): b.doc(self.root, duplicate)

    def test_malformed_target_proof_fails_with_public_workflow_error(self):
        for value in ({}, None, {"task_id": b.TASK, "candidate_shape": b.MODEL}):
            with self.subTest(value=value), self.assertRaises(w.WorkflowError):
                b.acceptance(self.root, self.snapshot, value)

    def test_producer_completed_utf8_intake_is_verified_without_native_service_mock(self):
        text = "原发布部当前结果；fixture only"
        visible = self.raw("evidence/publisher-final.txt", text.encode())
        native = {"thread": {"id": "fixture-fixed-publishing", "cwd": str(self.root)},
            "turn_id": "fixture-publisher-turn", "status": "completed", "message": {
                "turnId": "fixture-publisher-turn", "id": "fixture-publisher-final", "phase": "final_answer", "text": text}}
        native_pin = self.write("evidence/publisher-native.json", native)
        intake = {"task_id": b.TASK, "record_id": "fixture-current-intake", "event": "controller_received",
            "outbox": self.current_pin, "coordinator_role": b.ROLE, "actual_native_completion": native_pin,
            "source_thread_id": "fixture-fixed-publishing", "source_turn_id": "fixture-publisher-turn",
            "visible_reply": visible, "source_reply_sha256": visible["sha256"], "previous_hash": ""}
        intake["record_hash"] = w.sha256_value(intake)
        self.raw(str(w.result_handoff_path(self.root, b.TASK).relative_to(self.root)), (json.dumps(intake) + "\n").encode())
        self.actual_producer_native(self.root, self.current_pin)
        native["message"]["text"] = "altered completed source"
        intake["actual_native_completion"] = self.write(native_pin["path"], native)
        intake.pop("record_hash"); intake["record_hash"] = w.sha256_value(intake)
        self.raw(str(w.result_handoff_path(self.root, b.TASK).relative_to(self.root)), (json.dumps(intake) + "\n").encode())
        with self.assertRaisesRegex(w.WorkflowError, "UTF-8"):
            self.actual_producer_native(self.root, self.current_pin)

    def test_review_candidate_hook_never_calls_full_goal_verdict(self):
        with mock.patch.object(q, "validate_verdict", side_effect=AssertionError("full goal must stay separate")):
            for index in range(3):
                result = q.validate_cms_candidate_acceptance(self.root, self.snapshot, self.target(index))
                self.assertEqual(result["acceptance_model"], b.MODEL)

    def test_execution_preflight_hook_maps_rows_and_preserves_generic_scope_gate(self):
        for index in range(3):
            row = self.rows[index]
            result = g.execution_preflight(self.root, self.snapshot, row["action_id"], "cms_write", row["scope"], b.PRODUCER)
            self.assertEqual(result["authorized_project_scope"], b.SCOPE)
        with self.assertRaisesRegex(w.WorkflowError, "outside complete-goal authorized scope"):
            g.execution_preflight(self.root, self.snapshot, "unrelated-action", "cms_write", self.rows[0]["scope"], b.PRODUCER)

    def test_issuer_candidate_policy_and_decision_hooks_use_actual_continue_identity(self):
        issuer = candidate_issuer_functions()
        for index in range(3):
            row = self.rows[index]; payload = self.preflight_docs[index]["item"]["payload_sha256"]
            accepted = issuer.validate_goal_cms_acceptance(self.root, self.target(index), "publish")
            policy = issuer.validate_goal_cms_policy(self.root, b.TASK, row["action_id"], row["scope"], b.PRODUCER, payload)
            self.assertEqual(policy["acceptance_receipt_id"], self.continuation["record_id"])
            self.assertEqual(policy["acceptance_model"], b.MODEL)
            self.assertFalse(policy["external_permission_issued"])
            value = self.decision_value(index)
            self.assertEqual(issuer.validate_goal_cms_decision(self.root, value, self.target(index), "publish", payload, accepted, self.now), value)

    def test_issuer_t3_publish_proof_cannot_replace_rollback_or_legacy_fullpass(self):
        issuer = candidate_issuer_functions()
        accepted = self.accepted()
        with self.assertRaises(w.WorkflowError):
            issuer.validate_goal_cms_acceptance(self.root, self.target(), "rollback")
        for value in (None, {"acceptance_model": "goal_delivery_assistant_v1", "task_id": b.TASK,
                "scope": self.target()["scope"], "verdict": "pass"}, {**accepted, "verdict": "pass"}):
            with self.subTest(value=value), self.assertRaises(issuer.PermitEvidenceError):
                issuer.validate_new_permit_target(self.target(), assistant_acceptance=value)

    def test_policy_second_preflight_reuses_exact_bounded_context_without_scope_bypass(self):
        issuer = candidate_issuer_functions()
        self.write("data/action-policy.json", {"action_classes": {"cms_write": {}}, "paid_promotion_enabled": False})
        row = self.rows[0]; payload = self.preflight_docs[0]["item"]["payload_sha256"]
        approval = {"approval_id": "fixture-active-owner-approval", "status": "active", "task_id": b.TASK,
            "action_id": row["action_id"], "action_class": "cms_write", "scope": row["scope"]}
        with mock.patch.dict(sys.modules, {"managed_cms_permit_issuer": issuer}), \
                mock.patch.object(w, "effective_approvals", return_value={approval["approval_id"]: approval}), \
                mock.patch.object(g, "execution_preflight", wraps=g.execution_preflight) as checked:
            result, _ = w.policy_check(self.root, task_id=b.TASK, department=b.PRODUCER,
                action_id=row["action_id"], action_class="cms_write", scope=row["scope"],
                payload_sha256=payload, approval_id=approval["approval_id"])
            self.assertEqual(result["status"], "allow", result["reason"])
            self.assertEqual(checked.call_count, 1)
            self.assertIn("assistant_acceptance:bounded_candidate_only", result["required_receipts"])
            self.assertEqual(result["cms_candidate_acceptance"], {"acceptance_model": b.MODEL,
                "candidate_acceptance_record_id": self.continuation["record_id"],
                "machine_identity": self.preflight_docs[0]["item"]["machine_identity"]})
        self.change_preflight("self_check", "production_endpoint_verified", False)
        with mock.patch.dict(sys.modules, {"managed_cms_permit_issuer": issuer}), \
                mock.patch.object(w, "effective_approvals", return_value={approval["approval_id"]: approval}):
            denied, _ = w.policy_check(self.root, task_id=b.TASK, department=b.PRODUCER,
                action_id=row["action_id"], action_class="cms_write", scope=row["scope"],
                payload_sha256=payload, approval_id=approval["approval_id"])
            self.assertEqual(denied["status"], "deny")
            self.assertTrue(any("endpoint/actor" in reason for reason in denied["reason"]))


class BoundedCMSRollbackTests(BoundedCMSFixture):
    def assert_exact_recovery(self, index):
        self.prepare_rollback(index)
        target, issuer = self.target(index), self.rollback_issuer
        accepted = self.rollback_accepted()
        item = self.rollback_preflight()
        self.assertEqual(accepted["candidate_version"], b.ROLLBACK_VERSION)
        self.assertEqual(accepted["verdict"], "pass_rollback_candidate_only")
        self.assertEqual(accepted["row"]["raw_updated_at"], self.rollback_state["parent"]["savedUpdatedAt"])
        self.assertNotEqual(accepted["row"]["raw_updated_at"], self.rows[index]["raw_updated_at"])
        self.assertEqual(item["operation"], "rollback")
        self.assertEqual(item["authorized_project_scope"], b.SCOPE)
        self.assertFalse(accepted["business_goal_closed"])
        self.assertFalse(accepted["production_write_allowed"])
        self.assertEqual(accepted, q.validate_cms_candidate_acceptance(self.root, self.snapshot, target, "rollback"))
        self.assertEqual(item, g.execution_preflight(self.root, self.snapshot, f"rollback-{b.VERSION}", "cms_write", target["scope"], b.PRODUCER))
        self.assertEqual(accepted, issuer.validate_goal_cms_acceptance(self.root, target, "rollback"))
        issuer.validate_new_permit_target(target, assistant_acceptance=accepted)
        policy = issuer.validate_goal_cms_policy(self.root, b.TASK, f"rollback-{b.VERSION}", target["scope"], b.PRODUCER, item["payload_sha256"])
        self.assertEqual(policy["operation"], "rollback")
        self.assertEqual(policy["acceptance_receipt_id"], self.continuation["record_id"])
        value = self.rollback_decision()
        self.assertEqual(value, issuer.validate_goal_cms_decision(self.root, value, target, "rollback", value["payload_sha256"], accepted, self.now))
        record = self.preflight_docs[0]
        machine = b.validate_issuer_machine(self.root, target, accepted, record["run"], record["probe"],
            record["machine"]["github_actor_id"], record["payload"], record["receipt"])
        self.assertNotEqual(machine["run_id"], accepted["parent_run_id"])
        binding = issuer.rollback_parent_binding(target["action_id"], "rollback", accepted["parent_permit_id"], accepted["parent_run_id"])
        self.assertEqual(binding, {"parentPermitId": accepted["parent_permit_id"], "parentRunId": accepted["parent_run_id"]})

    def test_builtin_distinct_after_save_rollback_acceptance_preflight_and_hooks(self):
        self.assert_exact_recovery(0)

    def test_kitchen_distinct_after_save_rollback_acceptance_preflight_and_hooks(self):
        self.assert_exact_recovery(1)

    def test_renovation_distinct_after_save_rollback_acceptance_preflight_and_hooks(self):
        self.assert_exact_recovery(2)

    def test_publish_only_proof_never_authorizes_restore(self):
        for index in range(3):
            with self.subTest(index=index), self.assertRaisesRegex(w.WorkflowError, "bounded V2 required"):
                b.acceptance(self.root, self.snapshot, self.target(index), "rollback")

    def test_completed_parent_exact_permit_run_task_action_version_and_saved_id(self):
        self.prepare_rollback()
        state, original = self.rollback_state, copy.deepcopy(self.rollback_state["parent"])
        for key, value in (("permitId", "another-permit"), ("githubRunId", 987654),
                ("taskId", "another-task"), ("actionId", self.rows[1]["action_id"]),
                ("candidateVersion", b.ROLLBACK_VERSION), ("savedId", self.rows[1]["record_id"]),
                ("status", "prepared"), ("operation", "rollback"), ("savedUpdatedAt", "")):
            state["parent"] = copy.deepcopy(original); state["parent"][key] = value; self.sync_rollback()
            with self.subTest(key=key), self.assertRaisesRegex(self.rollback_issuer.PermitEvidenceError, "completed exact publish run"):
                self.rollback_accepted()

    def test_parent_reference_and_original_publish_continue_are_distinct_real_records(self):
        self.prepare_rollback()
        proof = self.box["cms_rollback_acceptance"]
        original = copy.deepcopy(proof)
        for key, value in (("parent_run_id", 987654), ("parent_permit_id", "another-permit"),
                ("publish_continue_record_id", self.continuation["record_id"]),
                ("publish_review_outbox", self.plan_pin)):
            proof.clear(); proof.update(copy.deepcopy(original)); proof[key] = value; self.sync_rollback()
            with self.subTest(key=key), self.assertRaises((w.WorkflowError, self.rollback_issuer.PermitEvidenceError)):
                self.rollback_accepted()
        proof.clear(); proof.update(original); self.sync_rollback()
        def committed(root, row):
            if row["record_id"] == self.rollback_state["publish_continue"]["record_id"]:
                raise w.WorkflowError("original publish continue is uncommitted")
        with mock.patch.object(adoption, "_committed", side_effect=committed), \
                self.assertRaisesRegex(w.WorkflowError, "original publish continue is uncommitted"):
            self.rollback_accepted()

    def test_saved_id_version_old_cas_microsecond_cas_and_retained_values_are_exact(self):
        self.prepare_rollback()
        state, original = self.rollback_state, copy.deepcopy(self.rollback_state["saved"])
        stamp = dt.datetime.fromisoformat(original["updated_at"])
        cases = [("id", self.rows[1]["record_id"]), ("version", self.rows[0]["native_version"]),
            ("version", "2"), ("updated_at", self.rows[0]["raw_updated_at"]),
            ("updated_at", (stamp + dt.timedelta(microseconds=1)).isoformat(timespec="microseconds")),
            ("title_en", original["title_en"] + " unauthorized")]
        for key, value in cases:
            state["saved"] = copy.deepcopy(original); state["saved"][key] = value; self.sync_rollback()
            with self.subTest(key=key, value=value), self.assertRaisesRegex(w.WorkflowError, "Saved ID/microsecond CAS"):
                self.rollback_accepted()

    def test_restore_candidate_changes_only_original_five_fields_and_saved_metadata(self):
        self.prepare_rollback(1)
        state, original = self.rollback_state, copy.deepcopy(self.rollback_state["restore"])
        for key, value in (("title_en", original["title_en"] + " sixth field"),
                ("updated_at", self.rows[1]["raw_updated_at"]), ("version", self.rows[1]["native_version"]),
                ("title_zh", self.rollback_state["saved"]["title_zh"])):
            state["restore"] = copy.deepcopy(original); state["restore"][key] = value; self.sync_rollback()
            with self.subTest(key=key), self.assertRaisesRegex(w.WorkflowError, "backup-only restore"):
                self.rollback_accepted()

    def test_rollback_typed_preview_cannot_reuse_publish_tuple_or_old_saved_cas(self):
        self.prepare_rollback()
        state, original = self.rollback_state, copy.deepcopy(self.rollback_state["typed"])
        cases = [("expectedUpdatedAt", self.rows[0]["raw_updated_at"]), ("mode", "write"),
            ("contentType", "blog"), ("record", self.rollback_state["saved"])]
        for key, value in cases:
            state["typed"] = copy.deepcopy(original); state["typed"]["request"][key] = value; self.sync_rollback()
            with self.subTest(key=key), self.assertRaisesRegex(w.WorkflowError, "distinct rollback tuple"):
                self.rollback_accepted()
        for key, value in (("operation", "publish"), ("actionId", self.rows[0]["action_id"]),
                ("candidateVersion", b.VERSION), ("taskId", "another-task"), ("scope", b.SCOPE)):
            state["typed"] = copy.deepcopy(original); state["typed"]["request"]["managedCandidate"][key] = value; self.sync_rollback()
            with self.subTest(tuple_key=key), self.assertRaisesRegex(w.WorkflowError, "distinct rollback tuple"):
                self.rollback_accepted()

    def test_independent_rollback_identity_sources_backup_and_version_cannot_alias_publish(self):
        self.prepare_rollback()
        proof = self.box["cms_rollback_acceptance"]; original = copy.deepcopy(proof)
        for key, value in (("candidate_version", b.VERSION), ("operation", "publish"), ("reviewer", b.PRODUCER),
                ("schema", b.MODEL), ("remaining_actions", []),
                ("row", {**self.rows[0], "backup": self.rows[1]["backup"]})):
            proof.clear(); proof.update(copy.deepcopy(original)); proof[key] = value; self.sync_rollback()
            with self.subTest(key=key), self.assertRaisesRegex(w.WorkflowError, "rollback authority/source/row/version"):
                self.rollback_accepted()
        proof.clear(); proof.update(original); self.sync_rollback()
        for key, value in (("department", b.PRODUCER), ("candidate_version", b.VERSION),
                ("production_write_allowed", True), ("qa_verdict", "pass")):
            original_value = self.box.get(key); self.box[key] = value; self.sync_rollback()
            with self.subTest(box_key=key), self.assertRaisesRegex(w.WorkflowError, "new independent rollback result|without production permission"):
                self.rollback_accepted()
            if original_value is None: self.box.pop(key)
            else: self.box[key] = original_value

    def test_rollback_target_cannot_replace_original_candidate_or_backup_tuple(self):
        self.prepare_rollback()
        for name, value in (("candidate", self.target(1)["candidate"]), ("rollback", self.target(1)["rollback"]),
                ("execution_owner", b.ROLE), ("scope", b.SCOPE), ("candidate_version", b.ROLLBACK_VERSION),
                ("rollback_allowed", False)):
            target = copy.deepcopy(self.target()); target[name] = value
            with self.subTest(name=name), self.assertRaises(w.WorkflowError):
                b.acceptance(self.root, self.snapshot, target, "rollback")

    def test_after_save_plan_uses_exact_parent_saved_source_and_unused_new_permission(self):
        self.prepare_rollback()
        record = self.preflight_docs[0]; original = copy.deepcopy(record["rollback"])
        for key, value in (("stage", "before_Save"), ("completed_parent", self.plan_pin), ("saved_record", self.plan_pin)):
            record["rollback"] = copy.deepcopy(original); self.change_preflight("rollback", key, value)
            with self.subTest(key=key), self.assertRaisesRegex(w.WorkflowError, "actual after-Save recovery binding"):
                self.rollback_preflight()
        record["rollback"] = copy.deepcopy(original)
        record["item"]["rollback"] = self.write(record["item"]["rollback"]["path"], record["rollback"])
        self.change_preflight("self_check", "single_use_state", "consumed")
        with self.assertRaisesRegex(w.WorkflowError, "unused permit"): self.rollback_preflight()

    def test_after_save_successful_rollback_preview_is_independently_frozen_zero_write(self):
        self.prepare_rollback()
        record, original = self.preflight_docs[0], copy.deepcopy(self.preflight_docs[0])
        for key, value in (("http_status", 409), ("dry_run", False), ("performed_write", True),
                ("row_unchanged_after_dry_run", False), ("operation", "publish"), ("candidate_version", b.VERSION)):
            record.update(copy.deepcopy(original)); record["receipt"][key] = value; self.sync_machine()
            with self.subTest(key=key), self.assertRaisesRegex(w.WorkflowError, "exact zero-write preview"):
                self.rollback_preflight()

    def test_after_save_machine_b_source_substitution_and_replayed_publish_decision_rejected(self):
        self.prepare_rollback()
        record, original = self.preflight_docs[0], copy.deepcopy(self.preflight_docs[0])
        record["machine"]["github_actor_id"] = 987654321
        record["machine"]["run_id"] += 1
        record["run"].update(id=record["machine"]["run_id"], actor={"id": record["machine"]["github_actor_id"]})
        record["probe"]["identity"].update(runId=record["machine"]["run_id"], actorId=record["machine"]["github_actor_id"])
        self.sync_machine()
        with self.assertRaisesRegex(w.WorkflowError, "original actor/run"): self.rollback_preflight()
        record.update(copy.deepcopy(original)); record["machine"]["issuer_source"] = self.source_pins[0]; self.sync_machine()
        with self.assertRaisesRegex(w.WorkflowError, "machine and issuer source"): self.rollback_preflight()
        record.update(copy.deepcopy(original)); self.sync_machine()
        accepted, original_value = self.rollback_accepted(), self.rollback_decision()
        for key, value in (("operation", "publish"), ("candidate_version", b.VERSION),
                ("candidate_acceptance_record_id", self.rollback_state["publish_continue"]["record_id"]),
                ("controller_decision_record_id", self.rollback_state["publish_continue"]["record_id"])):
            changed = copy.deepcopy(original_value); changed[key] = value
            with self.subTest(key=key), self.assertRaisesRegex(w.WorkflowError, "exact routine continue"):
                b.decision(self.root, changed, self.target(), changed["payload_sha256"], accepted, self.now)

    def test_rollback_policy_reuses_only_exact_new_candidate_context(self):
        self.prepare_rollback()
        self.write("data/action-policy.json", {"action_classes": {"cms_write": {}}, "paid_promotion_enabled": False})
        target, payload = self.target(), self.preflight_docs[0]["item"]["payload_sha256"]
        approval = {"approval_id": "fixture-new-rollback-owner-approval", "status": "active", "task_id": b.TASK,
            "action_id": f"rollback-{b.VERSION}", "action_class": "cms_write", "scope": target["scope"]}
        with mock.patch.object(w, "effective_approvals", return_value={approval["approval_id"]: approval}), \
                mock.patch.object(g, "execution_preflight", wraps=g.execution_preflight) as checked:
            result, _ = w.policy_check(self.root, task_id=b.TASK, department=b.PRODUCER,
                action_id=approval["action_id"], action_class="cms_write", scope=target["scope"],
                payload_sha256=payload, approval_id=approval["approval_id"])
            self.assertEqual(result["status"], "allow", result["reason"])
            self.assertEqual(checked.call_count, 1)
            self.assertEqual(result["cms_candidate_acceptance"]["candidate_acceptance_record_id"], self.continuation["record_id"])
            self.assertNotEqual(result["cms_candidate_acceptance"]["candidate_acceptance_record_id"], self.rollback_state["publish_continue"]["record_id"])


class RealV4ReadOnlySourceTests(unittest.TestCase):
    """Actual stored sources are read; no acceptance, permit or platform call."""
    def setUp(self):
        self.current = json.loads((SOURCE / "outbox-production-forward-preview-v4.json").read_bytes())

    def test_real_v4_rows_recompute_original_ninety_values_and_retained_namespaces(self):
        rows, _, manifest = b._rows(REAL, self.current)
        self.assertEqual([row["changed_fields"] for row in rows],
            [["content_zh"], ["title_zh", "excerpt_zh"], ["title_zh", "excerpt_zh"]])
        self.assertEqual(sum(row["retained_count"] for row in rows), 85)
        self.assertEqual(sum(row["website_retained_count"] for row in rows), 79)
        self.assertEqual(manifest, b.pin(REAL, self.current["evidence"]["manifest"]))

    def test_real_v4_machine_sources_keep_original_authority_and_actual_previews_separate(self):
        sources = b._machine_sources(REAL, self.current)
        original = b.doc(REAL, self.current["evidence"]["original_V3"])
        self.assertEqual(sources["original_machine_source"],
            b.pin(REAL, original["evidence"]["original_authority_review_machine_channel"]))
        self.assertEqual(sources["actual_machine_source"],
            b.pin(REAL, self.current["evidence"]["actual_machine_identity_and_preview_facts"]))
        facts = b.doc(REAL, sources["actual_machine_source"])
        self.assertEqual([(row["identity"]["runId"], row["identity"]["runAttempt"]) for row in facts["records"]],
            [(38062909715, 1), (38062912368, 2), (38062914967, 1)])
        self.assertNotEqual(facts["machine_workflow_sha"], facts["native_frontend_loaded_sha"])


class ActualV4Fixture(BoundedCMSFixture):
    """Exact V4/GH source bytes plus explicitly local A2 wrapper fixtures.

    The fixture clock is the original A2 technical source observation time.
    Freshness tests therefore assess that frozen snapshot without renewing a
    real run or changing its updated_at. The real diagnostic uses wall time.
    Original website deployment evidence and Git blobs are read, never mocked.
    """
    def setUp(self):
        original_datetime = dt.datetime
        observation = original_datetime.fromisoformat(json.loads(COHERENCE_SOURCE.read_bytes())["observed_at"])
        class SnapshotDatetime(original_datetime):
            @classmethod
            def now(cls, tz=None):
                return observation.astimezone(tz) if tz else observation.replace(tzinfo=None)
        clock = mock.patch.object(dt, "datetime", SnapshotDatetime)
        clock.start(); self.addCleanup(clock.stop)
        self.v4_ready = False
        super().setUp()
        current = json.loads((SOURCE / "outbox-production-forward-preview-v4.json").read_bytes())
        self.manifest = json.loads((REAL / current["evidence"]["manifest"]["path"]).read_bytes())
        self.checks = json.loads((REAL / current["evidence"]["fresh_CAS_input_checks"]["path"]).read_bytes())
        for frozen in self.manifest["artifacts"] + self.manifest["backups"]:
            source = Path(frozen["path"])
            source = source if source.is_absolute() else REAL / source
            self.assertTrue(source.resolve().is_relative_to(REAL))
            copied = self.raw(str(source.resolve().relative_to(REAL)), source.read_bytes())
            self.assertEqual(copied["sha256"], frozen["sha256"])
        self.manifest_pin = self.write("evidence/current-manifest.json", self.manifest)
        self.checks_pin = self.write("evidence/current-checks.json", self.checks)
        previous = {"task_id": b.TASK, "candidate_version": b.VERSION,
            "evidence": {"original_V2": self.original_pin,
                "original_authority_review_machine_channel": self.machine_origin_pin}}
        previous_pin = self.write("evidence/original-v3.json", previous)
        self.current = current
        self.current["evidence"].update(original_V2=self.original_pin, original_V3=previous_pin,
            manifest=self.manifest_pin, fresh_CAS_input_checks=self.checks_pin)
        self.current_pin = self.write("evidence/current-producer.json", self.current)
        self.receipts[0]["evidence"] = [self.current_pin]
        self.rows, _, _ = b._rows(self.root, self.current)
        self.machine_sources = b._machine_sources(self.root, self.current)
        self.machine_facts = b.doc(self.root, self.machine_sources["actual_machine_source"])
        self.coherence = json.loads(COHERENCE_SOURCE.read_bytes())
        self.coherence_pin = self.raw("evidence/A2-original-source-coherence.json", COHERENCE_SOURCE.read_bytes())
        self.target_map = b.targets(self.root)
        self.v4_ready = True
        self.preflight_docs = [self.make_preflight(row) for row in self.rows]
        self.box = self.make_box(); self.sync_box()

    def make_machine(self, row, identity, payload):
        if not self.v4_ready:
            return super().make_machine(row, identity, payload)
        actual = next(item for item in self.machine_facts["records"] if item["slug"] == row["slug"])
        payload = actual["actual_payload_sha256"]
        record = super().make_machine(row, identity, payload)
        machine = record["machine"]
        oidc = actual["identity"]
        machine.update(run_id=oidc["runId"], run_attempt=oidc["runAttempt"],
            workflow_sha=oidc["workflowSha"], main_sha=self.machine_facts["machine_workflow_sha"],
            actual_machine_source=self.machine_sources["actual_machine_source"])
        raw_gh = A2_SOURCES / f"T3-v4-{row['slug']}-actual-GH-run-snapshot-preliminary-v1.json"
        record["run"] = json.loads(raw_gh.read_bytes())
        machine["run_snapshot"] = self.raw(f"preflight/{row['slug']}-actual-full-GH-run.json", raw_gh.read_bytes())
        record["probe"] = b.doc(self.root, actual["identity_probe"])
        machine["identity_probe"] = b.pin(self.root, actual["identity_probe"])
        record["receipt"] = copy.deepcopy(actual["protected_forward_receipt"])
        machine["locked_preview"] = self.write(f"preflight/{row['slug']}-actual-locked-receipt.json", record["receipt"])
        binding = next(item for item in self.manifest["records"] if item["slug"] == row["slug"])
        record["payload"] = b.doc(self.root, binding["machine_payload_digest"])
        machine["payload_digest"] = b.pin(self.root, binding["machine_payload_digest"])
        return record

    def make_preflight(self, row, operation="publish", version=None):
        record = super().make_preflight(row, operation, version)
        if not self.v4_ready:
            return record
        payload = record["machine"]["payload_sha256"]
        record["item"]["payload_sha256"] = record["self_check"]["payload_sha256"] = payload
        snapshots = []
        runtime_manifest = b._website_json(self.coherence["actual_deployed_runtime_manifest"])
        deployment_root = b.WEBSITE / b.DEPLOYMENT_EVIDENCE / "production-r3-run-38061480070-artifacts/readback/edge-after/supabase/functions"
        for runtime in ("content-publish/service.ts", "_shared/managed-targets.ts"):
            entry = next(item for item in runtime_manifest["files"] if item["path"] == runtime)
            raw = (deployment_root / runtime).read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), entry["sha256"])
            snapshots.append(self.raw(f"preflight/{row['slug']}/deployed-source/{Path(runtime).name}", raw))
        production = self.coherence["actual_deployed_runtime_sha"]
        record["deployment"].update(production_sha=production, function_version=77,
            deployment_run_id=38061480070, original_deployment_source_proof=self.coherence["actual_deployment_source_proof"],
            source_snapshots=snapshots)
        record["source"].update(production_sha=production, function_version=77,
            source_coherence=self.coherence_pin, source_snapshots=snapshots)
        record["source"]["deployment_record"] = self.write(record["source"]["deployment_record"]["path"], record["deployment"])
        source_pin = self.write(record["rollback"]["source_verification"]["path"], record["source"])
        record["rollback"]["source_verification"] = source_pin
        record["self_check"]["evidence"] = [source_pin, self.coherence_pin]
        for name in ("self_check", "rollback"):
            record["item"][name] = self.write(record["item"][name]["path"], record[name])
        return record

    def make_box(self):
        box = super().make_box()
        if self.v4_ready:
            box["cms_candidate_acceptance"].update(self.machine_sources)
            box["evidence"] += list(self.machine_sources.values())
        return box

    def sync_machine(self, index=0):
        # Negative wrappers use new private fixture paths. They cannot mutate
        # the real V4 artifact copies already frozen in the producer manifest.
        record = self.preflight_docs[index]
        slug = self.rows[index]["slug"]
        for name, local in (("run_snapshot", "run"), ("identity_probe", "probe"),
                ("locked_preview", "receipt"), ("payload_digest", "payload")):
            record["machine"][name] = self.write(f"preflight/{slug}-changed-{name}.json", record[local])
        record["item"]["machine_identity"] = self.write(record["item"]["machine_identity"]["path"], record["machine"])
        self.sync_preflights()


class ActualV4ConsumerTests(ActualV4Fixture):
    def preflight(self, index=0):
        row = self.rows[index]
        return b.preflight(self.root, self.snapshot, row["action_id"], "cms_write", row["scope"], b.PRODUCER)

    def test_v4_three_actual_full_gh_machines_and_distinct_source_sha_preflights(self):
        for index, row in enumerate(self.rows):
            target = self.target_map[row["action_id"]]
            accepted = b.acceptance(self.root, self.snapshot, target)
            record = self.preflight_docs[index]
            machine = b.validate_machine(self.root, record["item"], accepted)
            self.assertGreater(len(record["run"]), 25)
            self.assertEqual(record["run"]["actor"]["id"], 276684684)
            self.assertNotEqual(machine["main_sha"], record["source"]["production_sha"])
            preflight = b.preflight(self.root, self.snapshot, row["action_id"], "cms_write", row["scope"], b.PRODUCER)
            self.assertEqual(preflight["machine_identity"], record["item"]["machine_identity"])
            self.assertEqual(b.validate_issuer_machine(self.root, target, accepted, record["run"], record["probe"],
                276684684, record["payload"], record["receipt"]), machine)

    def test_v4_no_independent_bounded_v2_still_refuses_real_sources(self):
        self.box.pop("cms_candidate_acceptance"); self.sync_box()
        with self.assertRaisesRegex(w.WorkflowError, "one real A2 bounded V2"):
            b.acceptance(self.root, self.snapshot, self.target_map[self.rows[0]["action_id"]])

    def test_v4_manifest_rejects_mixed_schema_mismatched_records_or_duplicate_membership(self):
        original = copy.deepcopy(self.manifest)
        mutations = [lambda value: value.update(artifact_pins=[]),
            lambda value: value["records"][0].update(raw_updated_at="different"),
            lambda value: value["artifacts"].append(copy.deepcopy(self.checks["records"][0]["typed_preview"]))]
        for mutate in mutations:
            value = copy.deepcopy(original); mutate(value)
            current = copy.deepcopy(self.current)
            current["evidence"]["manifest"] = self.write("evidence/changed-v4-manifest.json", value)
            with self.assertRaises(w.WorkflowError): b._rows(self.root, current)

    def test_v4_machine_source_cannot_replace_original_provenance_or_allow_permissions(self):
        current = copy.deepcopy(self.current)
        current["evidence"]["original_authority_review_machine_channel"] = self.original_pin
        with self.assertRaisesRegex(w.WorkflowError, "conflicting original machine"): b._machine_sources(self.root, current)
        facts = copy.deepcopy(self.machine_facts); facts["cms_save"] = 1
        current = copy.deepcopy(self.current)
        current["evidence"]["actual_machine_identity_and_preview_facts"] = self.write("evidence/mutated-v4-facts.json", facts)
        with self.assertRaisesRegex(w.WorkflowError, "actual current V4"): b._machine_sources(self.root, current)

    def test_v4_machine_cannot_self_consistently_replace_current_run_oidc_probe_receipt_or_payload(self):
        record, original = self.preflight_docs[0], copy.deepcopy(self.preflight_docs[0])
        mutations = [lambda value: (value["machine"].update(run_id=38043188134), value["run"].update(id=38043188134),
                value["probe"]["identity"].update(runId=38043188134)),
            lambda value: value["receipt"].update(checked_at="2026-10-10T15:17:00.000Z"),
            lambda value: (value["machine"].update(payload_sha256="a" * 64), value["item"].update(payload_sha256="a" * 64),
                value["payload"].update(payload_sha256="a" * 64))]
        for mutate in mutations:
            record.clear(); record.update(copy.deepcopy(original)); mutate(record); self.sync_machine()
            accepted = b.acceptance(self.root, self.snapshot, self.target_map[self.rows[0]["action_id"]])
            with self.assertRaisesRegex(w.WorkflowError, "latest V4|original machine/run"):
                b.validate_machine(self.root, record["item"], accepted)

    def test_v4_current_source_pin_must_be_frozen_in_bounded_evidence(self):
        self.box["evidence"].remove(self.machine_sources["actual_machine_source"]); self.sync_box()
        with self.assertRaisesRegex(w.WorkflowError, "freeze all current evidence"):
            b.acceptance(self.root, self.snapshot, self.target_map[self.rows[0]["action_id"]])

    def test_v4_cross_sha_coherence_missing_or_not_in_selfcheck_is_rejected(self):
        record = self.preflight_docs[0]
        record["source"].pop("source_coherence"); self.sync_source_verification()
        with self.assertRaises(w.WorkflowError): self.preflight()
        record["source"]["source_coherence"] = self.coherence_pin; self.sync_source_verification()
        with self.assertRaisesRegex(w.WorkflowError, "coherence"): self.preflight()

    def test_v4_real_coherence_maps_and_separate_shas_cannot_be_self_consistently_changed(self):
        record = self.preflight_docs[0]
        accepted = b.acceptance(self.root, self.snapshot, self.target_map[self.rows[0]["action_id"]])
        mutations = [lambda proof: proof.update(actual_machine_main_sha="a" * 40),
            lambda proof: proof.update(actual_runtime_source_closure_digest="a" * 64),
            lambda proof: proof["runtime_file_map"][0].update(workflow_commit_sha256="a" * 64),
            lambda proof: proof["workflow_and_CLI_source_map"][0].update(workflow_commit_bytes=1),
            lambda proof: proof.update(runtime_file_map=proof["runtime_file_map"][:-1])]
        for mutate in mutations:
            proof = copy.deepcopy(self.coherence); mutate(proof)
            source = copy.deepcopy(record["source"])
            source["source_coherence"] = self.write("evidence/mutated-coherence.json", proof)
            with self.assertRaises(w.WorkflowError):
                b.source_coherence(self.root, source, record["deployment"], record["machine"], accepted)

    def test_v4_coherence_foreign_deployment_and_unsupported_source_paths_are_refused(self):
        record = self.preflight_docs[0]
        accepted = b.acceptance(self.root, self.snapshot, self.target_map[self.rows[0]["action_id"]])
        proof = copy.deepcopy(self.coherence)
        proof["actual_deployment_source_proof"] = self.contract_pin
        source = {**record["source"], "source_coherence": self.write("evidence/foreign-coherence.json", proof)}
        deployment = {**record["deployment"], "original_deployment_source_proof": self.contract_pin}
        with self.assertRaises(w.WorkflowError):
            b.source_coherence(self.root, source, deployment, record["machine"], accepted)
        with self.assertRaises(w.WorkflowError): b._git_source(record["machine"]["main_sha"], "../../outside")
        with self.assertRaises(w.WorkflowError): b._website_json(self.contract_pin)

    def test_v4_actual_run_and_server_preview_bytes_expire_without_source_refresh(self):
        record = self.preflight_docs[0]
        accepted = self.accepted()
        before = {name: (self.root / record["machine"][name]["path"]).read_bytes()
            for name in ("run_snapshot", "locked_preview")}
        expired = self.now + dt.timedelta(hours=1)
        snapshot_datetime = dt.datetime
        class ExpiredDatetime(snapshot_datetime):
            @classmethod
            def now(cls, tz=None):
                return expired.astimezone(tz) if tz else expired.replace(tzinfo=None)
        with mock.patch.object(dt, "datetime", ExpiredDatetime), self.assertRaises(w.WorkflowError):
            b.validate_machine(self.root, record["item"], accepted)
        for name, raw in before.items():
            self.assertEqual((self.root / record["machine"][name]["path"]).read_bytes(), raw)

    def test_v4_fresh_private_run_metadata_cannot_extend_expired_server_preview(self):
        record = self.preflight_docs[0]
        accepted = self.accepted()
        expired = self.now + dt.timedelta(hours=1)
        # Only a new private wrapper pin is changed. The frozen original GH
        # snapshot, V4 producer and actual server receipt bytes stay intact.
        original_run = (self.root / record["machine"]["run_snapshot"]["path"]).read_bytes()
        original_receipt = (self.root / record["machine"]["locked_preview"]["path"]).read_bytes()
        run = copy.deepcopy(record["run"])
        run["updated_at"] = (expired - dt.timedelta(seconds=10)).isoformat()
        machine = copy.deepcopy(record["machine"])
        machine["run_snapshot"] = self.write("preflight/private-fresh-metadata-only.json", run)
        item = {**record["item"], "machine_identity": self.write("preflight/private-fresh-metadata-machine.json", machine)}
        snapshot_datetime = dt.datetime
        class ExpiredDatetime(snapshot_datetime):
            @classmethod
            def now(cls, tz=None):
                return expired.astimezone(tz) if tz else expired.replace(tzinfo=None)
        with mock.patch.object(dt, "datetime", ExpiredDatetime), self.assertRaisesRegex(w.WorkflowError,
                "actual protected preview expired"):
            b.validate_machine(self.root, item, accepted)
        self.assertEqual((self.root / record["machine"]["run_snapshot"]["path"]).read_bytes(), original_run)
        self.assertEqual((self.root / record["machine"]["locked_preview"]["path"]).read_bytes(), original_receipt)



class V5EffectFixture(BoundedCMSFixture):
    """Isolated services only: synthetic receipts never become real evidence."""
    def setUp(self):
        super().setUp()
        # This fixture exercises the historical mixed state. The new incremental
        # native Saved notice is covered by a separate actual read-only test.
        notice_service = mock.patch.object(b, "_apply_saved_notices", side_effect=lambda root, rows: rows)
        notice_service.start(); self.addCleanup(notice_service.stop)
        self.effects = {"task_id": b.TASK, "read_only": True, "new_Save_by_this_publisher": 0, "records": []}
        self.facts_v5 = {"task_id": b.TASK, "candidate_version": b.VERSION,
            "original_source_candidate_version": b.WEBSITE_SOURCE_VERSION,
            "new_permits_issued": 0, "new_CMS_Save": 0, "actual_time_not_overwritten": True}
        for key in b.V5_EVIDENCE[1:]:
            self.current["evidence"][key] = self.write("evidence/"+key+".json", {"isolated_service": True})
        for index, (fresh, row) in enumerate(zip(self.checks["records"], self.rows)):
            native = copy.deepcopy(b.doc(self.root, row["candidate"] if index < 2 else row["backup"]))
            if index < 2:
                native["updated_at"] = (self.now-dt.timedelta(seconds=90-index)).isoformat(timespec="microseconds")
                native["version"] = 1
                receipt = {"ok": index == 0, "operation": "optimize", "target": row["action_id"],
                    "published": {"ok": True, "dry_run": False, "content_type": "service", "action": "publish",
                        "slug": row["slug"], "status": "published", "existing_id": row["record_id"],
                        "saved_id": row["record_id"], "saved_updated_at": native["updated_at"], "auth_mode": "cron"},
                    "postcheck": {"ok": index == 0}}
                rp = self.write("evidence/"+row["slug"]+"-saved.json", receipt)
                self.effects["records"].append({"slug": row["slug"], "actual_existing_SavedID": row["record_id"],
                    "saved_raw_updated_at": native["updated_at"], "original_run_id": 38066380587+index,
                    "actual_publish_receipt": rp})
                self.artifacts.append(rp)
                fresh["typed_preview"] = self.write("rows/"+row["slug"]+"-typed-saved.json", {"request": None})
                self.artifacts.append(fresh["typed_preview"])
            fresh["backup"] = self.write("rows/"+row["slug"]+"-current.json", native)
            fresh.update(after_readback=fresh["backup"], raw_updated_at=native["updated_at"], native_version=native["version"])
            self.artifacts.append(fresh["after_readback"])
        self.sync_v5()

    def sync_v5(self):
        e = self.current["evidence"]
        e["actual_existing_Saved_ID_receipts"] = self.write("evidence/v5-effects.json", self.effects)
        e["actual_machine_identity_and_preview_facts"] = self.write("evidence/v5-facts.json", self.facts_v5)
        e["fresh_CAS_input_checks"] = self.write("evidence/current-checks.json", self.checks)
        manifest = {"task_id": b.TASK, "candidate_version": b.VERSION, "source_candidate_version": b.WEBSITE_SOURCE_VERSION,
            "records": self.checks["records"], "artifacts": self.artifacts, "backups": [r["backup"] for r in self.checks["records"]]}
        self.manifest_pin = self.write("evidence/current-manifest.json", manifest)
        e["manifest"] = self.manifest_pin
        self.current_pin = self.write("evidence/current-producer.json", self.current)
        self.receipts[0]["evidence"] = [self.current_pin]
        self.rows, self.bindings_pin, _ = b._rows(self.root, self.current)
        self.target_map = b.targets(self.root)

    def replace_pin(self, old, new):
        self.artifacts = [new if item == old else item for item in self.artifacts]

    def mutate_receipt(self, key, value, index=1):
        entry = self.effects["records"][index]; old = entry["actual_publish_receipt"]
        receipt = b.doc(self.root, old)
        if key in ("target", "operation"): receipt[key] = value
        else: receipt["published"][key] = value
        entry["actual_publish_receipt"] = self.write(old["path"], receipt)
        self.replace_pin(old, entry["actual_publish_receipt"]); self.sync_v5()

    def mutate_row(self, key, value, index=1):
        fresh = self.checks["records"][index]; old = fresh["backup"]
        native = b.doc(self.root, old); native[key] = value
        fresh["backup"] = self.write(old["path"], native)
        fresh.update(after_readback=fresh["backup"], raw_updated_at=native["updated_at"], native_version=native["version"])
        self.replace_pin(old, fresh["backup"]); self.sync_v5()

    def new_effect_review(self):
        expected = {"authority": self.authority_pin, "goal_contract": self.contract_pin, "review_plan": self.plan_pin,
            "current_producer": self.current_pin, "bindings": self.bindings_pin, "source_manifest": self.manifest_pin, "original_machine_source": self.machine_origin_pin}
        remaining = [r["action_id"] for r in self.rows if r["publication_state"] == "pending_save"]
        effect = {"schema": b.EFFECT_SCHEMA, "task_id": b.TASK, "candidate_version": b.VERSION, "reviewer": b.ROLE,
            "producer": b.PRODUCER, **expected, "rows": copy.deepcopy(self.rows), "remaining_publish_rows": remaining,
            **{key: False for key in b.FLAGS}}
        ep = self.write("evidence/new-effect-review.json", effect)
        proof = {"effect_reconciliation": ep, "remaining_publish_rows": remaining, "execution_preflights":
            [{"action_id": self.rows[2]["action_id"], "scope": self.rows[2]["scope"], "operation": "publish"}] if remaining else []}
        return expected, effect, proof, {"evidence": [ep]}


class V5EffectConsumerTests(V5EffectFixture):
    def test_saved_outer_postcheck_failure_and_version_one_do_not_hide_save(self):
        self.assertEqual([r["publication_state"] for r in self.rows],
            ["saved_effect_observed_no_replay", "saved_effect_observed_no_replay", "pending_save"])
        self.assertEqual([r["publish_allowed"] for r in self.rows], [False, False, True])
        self.assertEqual(self.rows[1]["current_native_version"], 1)
        self.assertFalse(self.rows[1]["original_postcheck_ok"])
        self.assertNotEqual(self.rows[1]["raw_updated_at"], self.rows[1]["saved_raw_updated_at"])
        expected, effect, proof, box = self.new_effect_review()
        self.assertEqual(b._effect_review(self.root, proof, expected, self.rows, box), proof["effect_reconciliation"])
        self.assertEqual(len(self.target_map), 3)

    def test_saved_rows_deny_acceptance_preflight_issuer_and_machine(self):
        issuer = candidate_issuer_functions()
        for index in (0, 1):
            with self.subTest(index=index):
                target = self.target(index)
                accepted = {"acceptance_model": b.MODEL, "operation": "publish", "row": self.rows[index]}
                with self.assertRaises(w.WorkflowError): b.acceptance(self.root, self.snapshot, target)
                with self.assertRaises(w.WorkflowError): b.preflight(self.root, self.snapshot, target["action_id"], "cms_write", target["scope"], b.PRODUCER)
                with self.assertRaises(issuer.PermitEvidenceError): issuer.validate_new_permit_target(target, assistant_acceptance=accepted)
                with self.assertRaises(w.WorkflowError): b.validate_issuer_machine(self.root, target, accepted, {}, {}, 0, {}, {})

    def test_wrong_saved_receipt_identity_cas_tuple_and_write_fail_closed(self):
        entry = self.effects["records"][1]
        original = copy.deepcopy(b.doc(self.root, entry["actual_publish_receipt"]))
        for key, value in (("saved_id", "other-id"), ("saved_updated_at", "2026-10-10T16:00:00.000001Z"),
                          ("target", self.rows[2]["action_id"]), ("operation", "rollback"), ("dry_run", True), ("ok", False)):
            with self.subTest(key=key):
                old = entry["actual_publish_receipt"]
                entry["actual_publish_receipt"] = self.write(old["path"], original)
                self.replace_pin(old, entry["actual_publish_receipt"])
                # Each mutation still has valid hashes; identity, not stale pins, must reject it.
                self.mutate_receipt(key, value)
                self.assertEqual(self.rows[1]["publication_state"], "effect_unresolved")
                self.assertFalse(self.rows[1]["publish_allowed"])

    def test_retained_drift_parallel_save_and_missing_readback_cannot_replay(self):
        self.mutate_row("title_en", "retained-sixth-field-drift")
        self.assertEqual(self.rows[1]["publication_state"], "effect_unresolved")
        self.mutate_row("updated_at", "2026-10-11T00:00:00.000001+00:00", index=0)
        self.assertEqual(self.rows[0]["publication_state"], "effect_unresolved")
        self.checks["records"][0]["after_readback"] = None; self.sync_v5()
        self.assertEqual(self.rows[0]["publication_state"], "effect_unresolved")

    def test_unknown_third_effect_empty_remaining_and_duplicate_receipt_deny_new_save(self):
        self.mutate_row("updated_at", "2026-10-11T00:00:00.000001+00:00", index=2)
        self.assertEqual(self.rows[2]["publication_state"], "effect_unresolved")
        expected, effect, proof, box = self.new_effect_review()
        self.assertEqual(proof["remaining_publish_rows"], [])
        self.assertEqual(b._effect_review(self.root, proof, expected, self.rows, box), proof["effect_reconciliation"])
        with self.assertRaises(w.WorkflowError): b.acceptance(self.root, self.snapshot, self.target(2))
        self.effects["records"].append(copy.deepcopy(self.effects["records"][1])); self.sync_v5()
        self.assertEqual(self.rows[1]["publication_state"], "effect_unresolved")

    def test_effect_review_requires_parent_before_reconciled_and_no_saved_preflights(self):
        expected, effect, proof, box = self.new_effect_review()
        proof["execution_preflights"].append({"action_id": self.rows[0]["action_id"], "scope": self.rows[0]["scope"], "operation": "publish"})
        with self.assertRaises(w.WorkflowError): b._effect_review(self.root, proof, expected, self.rows, box)
        expected, effect, proof, box = self.new_effect_review(); effect["rows"][0]["publication_state"] = "effect_reconciled"
        proof["effect_reconciliation"] = self.write(proof["effect_reconciliation"]["path"], effect)
        box["evidence"] = [proof["effect_reconciliation"]]
        with self.assertRaises(w.WorkflowError): b._effect_review(self.root, proof, expected, self.rows, box)

    def test_ambiguous_v5_old_aliases_fake_new_save_and_timestamp_refresh_rejected(self):
        for key, value in (("native_frontend_loaded_sha", "1"*40), ("new_CMS_Save", 1), ("actual_time_not_overwritten", False)):
            with self.subTest(key=key):
                self.current["evidence"]["actual_machine_identity_and_preview_facts"] = self.write("evidence/bad-facts.json", {**self.facts_v5, key: value})
                with self.assertRaises(w.WorkflowError): b._rows(self.root, self.current)
        self.current["evidence"]["actual_machine_identity_and_preview_facts"] = self.write("evidence/v5-facts.json", self.facts_v5)
        self.current["evidence"]["source_and_original_backups"] = self.authority_pin
        with self.assertRaises(w.WorkflowError): b._rows(self.root, self.current)


class RealV5ReadOnlyEffectTests(unittest.TestCase):
    def test_historical_frozen_actual_rows_recompute_without_claiming_current_execution(self):
        current = json.loads((SOURCE/"outbox-production-forward-preview-v5.json").read_bytes())
        rows, _, _ = b._rows(REAL, current)
        self.assertEqual([r["publication_state"] for r in rows],
            ["saved_effect_observed_no_replay", "saved_effect_observed_no_replay", "pending_save"])
        self.assertEqual([r.get("current_native_version") for r in rows], [1, 1, 1])
        self.assertEqual(rows[0]["saved_raw_updated_at"], "2026-10-10T16:08:22.003433+00:00")
        self.assertEqual(rows[1]["saved_raw_updated_at"], "2026-10-10T16:51:33.869215+00:00")
        self.assertFalse(rows[1]["original_postcheck_ok"])
        self.assertFalse(any(r.get("production_write_allowed") for r in rows))
        actual_current = b._apply_saved_notices(REAL, rows)
        self.assertEqual([r["publish_allowed"] for r in actual_current], [False, False, False])
        self.assertEqual(actual_current[2]["saved_raw_updated_at"], "2026-10-10T17:45:51.559189+00:00")
        self.assertFalse(actual_current[2]["current_full_Saved_readback_verified"])
        self.assertEqual([r["action_id"] for r in actual_current if r["publish_allowed"]], [])
        with self.assertRaises(w.WorkflowError):
            b._saved_parent(REAL, actual_current[2], {}, {}, {})


    def test_third_completed_status_is_real_but_does_not_upgrade_partial_saved_row(self):
        path = REAL / "logs/handoffs/2026-10-10-paid-three-page-original-followthrough-v1/assistant2-owned/A2-T3-third-actual-Saved-original-issuer-readonly-completed-permit-status-v1.json"
        raw = path.read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), "9dc8d68e1cc20e16b301f22a2a7934c63ebdfecf017bc647afc490a557cb201e")
        self.assertEqual(len(raw), 1085)
        status = json.loads(raw)["actual_safe_response"]
        issuer = candidate_issuer_functions()
        issuer.validate_completed_parent_status(status, {"task_id": b.TASK, "action_id": "paid-three-page-renovation-exact-fields-v1", "candidate_version": b.VERSION, "record_id": b.ROWS[2][1]}, status["permitId"], 38073003426)
        current = b._apply_saved_notices(REAL, b._rows(REAL, json.loads((REAL/b.BASE/"outbox-production-forward-preview-v5.json").read_bytes()))[0])
        self.assertFalse(current[2]["current_full_Saved_readback_verified"])
        with self.assertRaisesRegex(w.WorkflowError, "partial Saved notice"):
            b._saved_parent(REAL, current[2], {}, {}, {})


class V5NativeRecoveryTests(V5EffectFixture):
    """A genuine isolated parent permits version=1; absence never authorizes replay."""
    def setUp(self):
        super().setUp()
        self.native_issuer = candidate_issuer_functions()
        issuer_service = mock.patch.dict(sys.modules, {"managed_cms_permit_issuer": self.native_issuer})
        issuer_service.start(); self.addCleanup(issuer_service.stop)

    def native_parent(self, index=1):
        row = self.rows[index]
        origin = b.doc(self.root, self.machine_origin_pin)["actual_original_machine_channel_metadata"]
        commit = "3"*40
        identity = {"repositoryId": 1248188229, "actorId": origin["existing_actor_id"],
            "workflowRef": origin["repository"]+"/"+origin["workflow_path"]+"@refs/heads/main",
            "runId": row["historical_run_id"], "runAttempt": 1, "workflowSha": commit}
        status = {"ok": True, "permitId": "fixture-parent-original-permit", "status": "completed", "operation": "publish",
            "taskId": b.TASK, "actionId": row["action_id"], "candidateVersion": b.VERSION,
            "githubRunId": row["historical_run_id"], "githubRunAttempt": 1, "savedId": row["record_id"],
            "savedUpdatedAt": row["saved_raw_updated_at"]}
        run = {"id": row["historical_run_id"], "run_attempt": 1, "actor": {"id": origin["existing_actor_id"]},
            "repository": {"id": 1248188229, "full_name": origin["repository"]}, "workflow_id": origin["workflow_id"],
            "path": origin["workflow_path"], "event": "workflow_dispatch", "head_branch": "main", "head_sha": commit,
            "status": "completed", "conclusion": "failure"}
        payload = {"task_id": b.TASK, "candidate_version": b.VERSION, "operation": "publish",
            "payload_sha256": "5"*64, "expected_updated_at": row["raw_updated_at"]}
        parent = {"schema": b.EFFECT_SCHEMA+"_completed_parent", "task_id": b.TASK, "candidate_version": b.VERSION,
            "action_id": row["action_id"], "scope": row["scope"], "record_id": row["record_id"],
            "original_authority": self.authority_pin, "native_batch_permission_inherited": False,
            "historical_company_PASS_invented": False, "parent_run_id": run["id"], "parent_permit_id": status["permitId"],
            "completed_status": self.write("recovery/status.json", status),
            "full_original_gh_run": self.write("recovery/run.json", run),
            "identity_probe": self.write("recovery/probe.json", {"ok": True, "dry_run": True, "performed_write": False, "identity": identity}),
            "payload_digest": self.write("recovery/payload.json", payload), "original_machine_source": self.machine_origin_pin,
            "issued_evidence": self.write("recovery/issued.json", {"issued": {"permitId": status["permitId"], "operation": "publish"},
                "evidence": {"target": row["action_id"], "identity": identity, "actualPayloadSha256": payload["payload_sha256"],
                    "authorizationId": "fixture-original-authority", "operationsDecisionId": "fixture-original-operations",
                    "policyDecisionId": "fixture-original-policy"}})}
        actual = json.loads((A2_SOURCES/"T3-v5-workflow-93716-runtime-5237-source-equivalence-preliminary-v1.json").read_bytes())
        original = b._website_json(actual["actual_deployment_source_proof"])
        manifest = b._website_json(actual["actual_deployed_runtime_manifest"])
        runtime_files, git_files = [], {}
        for entry in manifest["files"]:
            wp = {"path": str(Path(original["actual_readback"]["root"])/entry["path"]), "sha256": entry["sha256"], "size": entry["bytes"]}
            path = "supabase/functions/"+entry["path"]
            runtime_files.append({"source_path": path, "deployed_snapshot": wp})
            git_files[path] = b._website_bytes(wp)
        cli = []
        for path in b.WORKFLOW_CLI[1:]:
            entry = next(p for p in original["source_pins"] if p["path"] == path)
            cli.append({"source_path": path, "sha256": entry["sha256"], "size": entry["bytes"]})
            git_files[path] = b._git_source("5237d068b49a20a9ce6dc395f8c6a45d7f961d8b", path)
        workflow = (SOURCE/"production-forward-preview-v5/actual-machine-content-publish-workflow-v5.yml").read_bytes()
        git_files[b.WORKFLOW_CLI[0]] = workflow
        review = {"schema": b.EFFECT_SCHEMA+"_historical_source_review", "reviewer": b.ROLE,
            "task_id": b.TASK, "action_id": row["action_id"], "scope": row["scope"], "saved_receipt": row["saved_receipt"],
            "original_authority": self.authority_pin, "source_branch": "exact_original_target_branch_verified",
            "producer_summary_is_permission": False, "workflow_source": self.raw("recovery/workflow.yml", workflow),
            "runtime_manifest": actual["actual_deployed_runtime_manifest"], "deployment_source_proof": actual["actual_deployment_source_proof"],
            "runtime_files": runtime_files, "cli_files": cli,
            **{key: parent[key] for key in ("full_original_gh_run", "payload_digest", "completed_status", "issued_evidence")}}
        parent["historical_source_review"] = self.write("recovery/source-review.json", review)
        git_service = mock.patch.object(b, "_git_source", side_effect=lambda sha, path: git_files[path] if sha in {commit, "5237d068b49a20a9ce6dc395f8c6a45d7f961d8b"} else b.require(False, "fixture immutable commit unavailable"))
        git_service.start(); self.addCleanup(git_service.stop)
        return row, parent, self.write("recovery/parent-mapping.json", parent), status

    def test_version_one_exact_parent_all_runtime_and_cli_bytes_accept_without_prior_company_pass(self):
        row, parent, value, status = self.native_parent()
        self.assertEqual(row["current_native_version"], 1)
        parsed, original_status = b._saved_parent(self.root, row, value, self.authority_pin, self.machine_origin_pin)
        self.assertEqual(parsed, parent); self.assertEqual(original_status, status)
        self.assertNotIn("publish_review_outbox", parent)
        self.assertNotIn("publish_continue_record_id", parent)

    def test_native_parent_status_payload_actor_and_source_substitution_fail_closed(self):
        row, parent, value, status = self.native_parent()
        originals = {key: copy.deepcopy(b.doc(self.root, parent[key])) for key in ("completed_status", "payload_digest", "full_original_gh_run", "issued_evidence")}
        for key, field, wrong in (("completed_status", "actionId", self.rows[2]["action_id"]),
                                  ("completed_status", "status", "unused"), ("completed_status", "savedUpdatedAt", row["raw_updated_at"]),
                                  ("payload_digest", "payload_sha256", "6"*64), ("full_original_gh_run", "run_attempt", 2)):
            with self.subTest(key=key, field=field):
                changed = {**originals[key], field: wrong}
                mutated = copy.deepcopy(parent); mutated[key] = self.write("recovery/altered-input.json", changed)
                pin = self.write("recovery/altered-mapping.json", mutated)
                with self.assertRaises((w.WorkflowError, self.native_issuer.PermitEvidenceError)):
                    b._saved_parent(self.root, row, pin, self.authority_pin, self.machine_origin_pin)
        mutated = {**parent, "historical_company_PASS_invented": True}
        with self.assertRaises(w.WorkflowError): b._saved_parent(self.root, row, self.write("recovery/fake-prior-pass.json", mutated), self.authority_pin, self.machine_origin_pin)

    def test_historical_parent_cannot_substitute_even_self_consistent_original_machine_channel(self):
        row, parent, value, _ = self.native_parent()
        parent = b.doc(self.root, value)
        foreign = b.doc(self.root, self.machine_origin_pin)
        foreign["actual_original_machine_channel_metadata"]["existing_actor_id"] += 1
        parent["original_machine_source"] = self.write("recovery/foreign-original-machine.json", foreign)
        with self.assertRaisesRegex(w.WorkflowError, "independently frozen original machine"):
            b._saved_parent(self.root, row, self.write("recovery/foreign-parent.json", parent), self.authority_pin, self.machine_origin_pin)

    def test_missing_original_completed_parent_cannot_upgrade_saved_effect_to_recovery(self):
        row = self.rows[1]
        self.assertFalse(row["publish_allowed"])
        with self.assertRaises(w.WorkflowError): b._saved_parent(self.root, row, {}, self.authority_pin, self.machine_origin_pin)
        self.assertFalse(row["publish_allowed"])

    def test_version_one_native_recovery_requires_new_review_continue_preview_and_no_fake_prior_pass(self):
        row, mapping, mapping_pin, status = self.native_parent()
        self.prepare_rollback(1)
        state = self.rollback_state
        state["saved"] = b.doc(self.root, row["current_record"])
        state["parent"] = status
        before = b.doc(self.root, row["backup"])
        state["restore"] = {**state["saved"], **{key: before[key] for key in row["changed_fields"]}}
        state["typed"]["request"].update(expectedUpdatedAt=state["saved"]["updated_at"], record=state["restore"])
        recovery_row = {**row, "action_id": "rollback-"+b.VERSION, "raw_updated_at": state["saved"]["updated_at"],
            "native_version": 1, "baseline_sha256": b.digest(state["saved"]), "desired_sha256": b.digest(state["restore"]),
            "candidate": self.write(state["path"]+"-restore.json", state["restore"]),
            "typed_preview": self.write(state["path"]+"-typed.json", state["typed"])}
        self.preflight_docs = [self.make_preflight(recovery_row, "rollback", b.ROLLBACK_VERSION)]
        self.sync_rollback()
        proof = self.box["cms_rollback_acceptance"]
        mapping["completed_status"] = proof["completed_parent"]
        source_review = b.doc(self.root, mapping["historical_source_review"])
        source_review["completed_status"] = mapping["completed_status"]
        mapping["historical_source_review"] = self.write(mapping["historical_source_review"]["path"], source_review)
        mapping_pin = self.write(mapping_pin["path"], mapping)
        proof.update(recovery_effect_schema=b.EFFECT_SCHEMA, saved_effect_completed_parent=mapping_pin,
            publish_review_outbox=None, publish_continue_record_id=None, saved_record=row["current_record"],
            parent_run_id=status["githubRunId"], parent_permit_id=status["permitId"])
        # Re-freeze the new successful rollback preview, not the discarded old fixture preview.
        preview = self.preflight_docs[0]
        preview["rollback"].update(completed_parent=proof["completed_parent"], saved_record=proof["saved_record"])
        preview["item"]["rollback"] = self.write(preview["item"]["rollback"]["path"], preview["rollback"])
        proof["execution_preflights"] = [preview["item"]]
        self.box["evidence"] += [mapping_pin, row["current_record"]]
        self.box_pin = self.write("evidence/new-native-rollback-review.json", self.box)
        self.continuation.update(evidence=[self.box_pin], previous_hash="")
        self.continuation.pop("record_hash", None)
        self.continuation["record_hash"] = w.sha256_value(self.continuation)
        # A single new rollback decision exists. No old company publish review or
        # continue is invented to describe the original native Save.
        self.raw(str(w.result_handoff_path(self.root,b.TASK).relative_to(self.root)), (json.dumps(self.continuation)+"\n").encode())
        with mock.patch.object(b, "_machine_sources", return_value={"original_machine_source": self.machine_origin_pin}):
            accepted = b.rollback_acceptance(self.root, self.snapshot, self.target(1))
            self.assertEqual(accepted["row"]["native_version"], 1)
            self.assertFalse(accepted["production_write_allowed"])
            checked = b.preflight(self.root, self.snapshot, "rollback-"+b.VERSION, "cms_write", row["scope"], b.PRODUCER)
            self.assertEqual(checked["operation"], "rollback")
            self.assertEqual(checked["facts"], self.preflight_docs[0]["item"]["facts"])
            self.preflight_docs[0]["self_check"]["single_use_state"] = "consumed"
            self.preflight_docs[0]["item"]["self_check"] = self.write(self.preflight_docs[0]["item"]["self_check"]["path"], self.preflight_docs[0]["self_check"])
            proof["execution_preflights"] = [self.preflight_docs[0]["item"]]
            self.box_pin = self.write(self.box_pin["path"], self.box)
            self.continuation["evidence"] = [self.box_pin]; self.sync_continuation()
            with self.assertRaises(w.WorkflowError):
                b.preflight(self.root, self.snapshot, "rollback-"+b.VERSION, "cms_write", row["scope"], b.PRODUCER)



# V5 whole workflow, full runtime and independent source adoption checks.
import ast
import copy
import datetime as dt
import difflib
import functools
import hashlib
import json
from pathlib import Path
import re
import sys
import tempfile
import types
import unittest
from unittest import mock

V5_SOURCE_STAGE = PACKAGE
V5_SOURCE_PROJECT = REAL
V5_SOURCE_PRELIMINARY = V5_SOURCE_PROJECT / 'logs/handoffs/2026-10-10-paid-three-page-original-followthrough-v1/assistant2-owned/T3-v5-workflow-93716-runtime-5237-source-equivalence-preliminary-v1.json'
V5_CURRENT_WORKFLOW = V5_SOURCE_PROJECT / 'drafts/publishing/fc-20261010-paid-three-page-exact-publication-followthrough-v1/production-forward-preview-v5/actual-machine-content-publish-workflow-v5.yml'
V5_SOURCE_TMP = V5_SOURCE_STAGE / 'checks/.source-machine-v5-tmp'
V5_NEW_HEAD = 'c4adb0bf4cd97eb6e3c76e619380783ec24372bb'
V5_OLD_HEAD = '93716aaed5ef30ca209aa4a89db5230d47bd19fd'


def v5_source_under_test():
    # Exercise the complete imported candidate (or adopted) source, not the
    # independently authored patch. No import or live consumer occurs here.
    return Path(b.__file__).read_text(encoding="utf-8")


def v5_baseline_workflow(current):
    """Invert the frozen complete diff only for a local exact-byte fixture."""
    delta = json.loads(V5_SOURCE_PRELIMINARY.read_bytes())['source_differences'][0]['unified_diff'].splitlines(keepends=True)
    current = current.decode().splitlines(keepends=True)
    output, cursor, index = [], 0, 2
    while index < len(delta):
        match = re.match(r'@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@', delta[index])
        assert match
        start = int(match.group(1)) - 1
        output += current[cursor:start]
        cursor, index = start, index + 1
        while index < len(delta) and not delta[index].startswith('@@ '):
            tag, value = delta[index][0], delta[index][1:]
            if tag in ' +':
                assert current[cursor] == value
                cursor += 1
            if tag in ' -':
                output.append(value)
            index += 1
    return ''.join(output + current[cursor:]).encode()


class V5SourceMachineFixture(unittest.TestCase):
    def setUp(self):
        V5_SOURCE_TMP.mkdir(exist_ok=True)
        temporary = tempfile.TemporaryDirectory(prefix='local-fixture-', dir=V5_SOURCE_TMP)
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.committed = []
        class WorkflowError(Exception):
            pass
        self.w = types.SimpleNamespace(WorkflowError=WorkflowError, safe_path=self.safe,
            file_digest=lambda root, path: self.fpin(path), _parse_observed_at=self.parse_time,
            snapshot_path=lambda root, task: self.root / 'goal.json',
            read_json=lambda path: json.loads(Path(path).read_bytes()),
            validate_outbox=lambda *args: None, validate_workflow_events=lambda *args: [],
            _result_handoff_rows=lambda *args: self.handoffs)
        names = {'require', 'digest', 'strict', 'pin', 'doc', '_content_pair', '_machine_sources',
            '_git_source', '_website_bytes', '_website_json', '_native', 'validate_machine', 'source_coherence'}
        tree = ast.parse(v5_source_under_test())
        body = [node for node in tree.body if isinstance(node, ast.Assign) or
            isinstance(node, ast.FunctionDef) and (node.name in names or node.name.startswith('_v5_'))]
        self.b = types.SimpleNamespace()
        self.ns = dict(dt=dt, difflib=difflib, functools=functools, hashlib=hashlib, json=json,
            re=re, Path=Path, w=self.w)
        exec(compile(ast.Module(body=body, type_ignores=[]), 'isolated-authored-source-helpers', 'exec'), self.ns)
        self.b.__dict__.update(self.ns)
        # Helper global bindings remain self.ns; changes use patch.dict on it.
        self.after = V5_CURRENT_WORKFLOW.read_bytes()
        self.before = v5_baseline_workflow(self.after)
        self.assertEqual(self.pair(self.before), self.b.V5_WORKFLOW_BEFORE)
        self.assertEqual(self.pair(self.after), self.b.V5_WORKFLOW_AFTER)
        self.workflow_before = self.raw('evidence/workflow-before.yml', self.before)
        self.workflow_after = self.raw('evidence/workflow-after.yml', self.after)
        self.proof = self.header(V5_NEW_HEAD)
        self.refresh_delta()
        original_v2 = self.doc('evidence/original-v2.json', {'task_id': self.b.TASK})
        self.origin = self.doc('evidence/original-machine.json', {'actual_original_machine_channel_metadata': {
            'existing_actor_id': 276684684, 'repository': 'wangchaozhuanyong/zhuangxiuwangzhan',
            'workflow_id': 351424533, 'workflow_path': self.b.WORKFLOW_CLI[0]}})
        original_v3 = self.doc('evidence/original-v3.json', {'task_id': self.b.TASK,
            'candidate_version': self.b.VERSION, 'evidence': {'original_V2': original_v2,
                'original_authority_review_machine_channel': self.origin}})
        self.frontend = {'deploymentVersion': V5_NEW_HEAD, 'contentVersion': 'LOCAL_FIXTURE'}
        self.facts = {'task_id': self.b.TASK, 'candidate_version': self.b.VERSION,
            'machine_workflow_sha': V5_NEW_HEAD, 'native_frontend_actual_version': V5_NEW_HEAD,
            'original_source_candidate_version': self.b.WEBSITE_SOURCE_VERSION,
            'actual_time_not_overwritten': True, 'new_permits_issued': 0, 'new_CMS_Save': 0,
            'records': [{'slug': slug, 'writes': 0, 'old_run_or_permission_reused': False,
                'actual_machine_requests_completed': True} for slug, _, _ in self.b.ROWS]}
        self.frontend_pin = self.doc('evidence/frontend.json', self.frontend)
        self.facts_pin = self.doc('evidence/facts.json', self.facts)
        self.comparison_pin = self.doc('evidence/comparison.json', {'task_id': self.b.TASK})
        self.current = {'task_id': self.b.TASK, 'candidate_version': self.b.VERSION, 'evidence': {
            'original_V2': original_v2, 'original_V3': original_v3,
            'actual_machine_identity_and_preview_facts': self.facts_pin,
            'actual_current_workflow_source': self.workflow_after,
            'actual_current_frontend_version': self.frontend_pin,
            'actual_main_and_deployed_source_comparison': self.comparison_pin}}
        self.sync_machine()

    def safe(self, root, path):
        destination = Path(root) / path
        if not destination.resolve().is_relative_to(self.root.resolve()):
            raise self.w.WorkflowError('fixture path escaped')
        return destination

    @staticmethod
    def parse_time(value):
        try:
            parsed = dt.datetime.fromisoformat(str(value).replace('Z', '+00:00'))
            return parsed if parsed.tzinfo else None
        except ValueError:
            return None

    @staticmethod
    def pair(raw):
        return {'sha256': hashlib.sha256(raw).hexdigest(), 'size': len(raw)}

    def fpin(self, path):
        return {'path': str(path), **self.pair(self.safe(self.root, path).read_bytes())}

    def raw(self, path, raw):
        destination = self.safe(self.root, path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(raw)
        return self.fpin(path)

    def doc(self, path, value):
        return self.raw(path, (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode())

    def header(self, current):
        return {'schema': self.b.V5_SOURCE_SCHEMA, 'task_id': self.b.TASK, 'candidate_version': self.b.VERSION,
            'source_task_id': self.b.V5_SOURCE_TASK, 'source_candidate_version': self.b.V5_SOURCE_VERSION,
            'source_scope': self.b.V5_SOURCE_SCOPE, 'operation': 'publish', 'scoped_result': 'exact_original_target_branch_verified',
            'whole_workflow_bytes_equal': False, 'formal_T3_PASS': False,
            'baseline_commit': self.b.V5_BASELINE_COMMIT, 'current_commit': current,
            'actual_machine_main_sha': current, 'actual_machine_workflow_sha': current,
            'actual_deployed_runtime_sha': self.b.V5_BASELINE_COMMIT,
            'actual_function_version': 77, 'actual_deployment_run': 38061480070,
            'workflow_baseline': self.workflow_before, 'workflow_current': self.workflow_after,
            **{key: False for key in self.b.V5_REVIEW_FLAGS}}

    def refresh_delta(self):
        delta = ''.join(difflib.unified_diff(self.before.decode().splitlines(keepends=True),
            self.after.decode().splitlines(keepends=True),
            fromfile=self.b.V5_BASELINE_COMMIT + ':' + self.b.WORKFLOW_CLI[0],
            tofile=self.proof['current_commit'] + ':' + self.b.WORKFLOW_CLI[0])).encode()
        self.proof['full_workflow_diff'] = self.raw('evidence/workflow-full.diff', delta)

    def git(self, commit, path):
        self.assertEqual(path, self.b.WORKFLOW_CLI[0])
        return self.before if commit == self.b.V5_BASELINE_COMMIT else self.after

    def sync_machine(self):
        self.facts_pin = self.doc('evidence/facts.json', self.facts)
        self.frontend_pin = self.doc('evidence/frontend.json', self.frontend)
        self.current['evidence'].update(actual_machine_identity_and_preview_facts=self.facts_pin,
            actual_current_frontend_version=self.frontend_pin)
        self.proof.update(actual_machine_source=self.facts_pin, frontend_version=self.frontend_pin,
            source_comparison=self.comparison_pin,
            current_producer=self.doc('evidence/current-producer.json', self.current))
        self.bridge = self.doc('evidence/source-bridge.json', self.proof)

    def denied(self, call):
        with self.assertRaises(self.w.WorkflowError):
            call()


class V5SourceMachineFocusedTests(V5SourceMachineFixture):
    def test_full_known_workflow_pair_and_all_diff_bytes_pass(self):
        with mock.patch.dict(self.ns, {'_git_source': self.git}):
            self.b._v5_workflow_bridge_bytes(self.root, self.proof)

    def test_same_workflow_bytes_new_head_and_real_frontend_version_pass(self):
        self.b._v5_bridge_header(self.proof)
        result = self.b._machine_sources(self.root, self.current, self.bridge)
        self.assertEqual(result['source_bridge'], self.bridge)
        self.assertEqual(result['original_machine_source'], self.origin)
        with mock.patch.dict(self.ns, {'_git_source': self.git}):
            self.b._v5_workflow_bridge_bytes(self.root, self.proof)

    def test_93716_historical_pair_is_still_explicitly_supported(self):
        self.proof.update(current_commit=V5_OLD_HEAD, actual_machine_main_sha=V5_OLD_HEAD, actual_machine_workflow_sha=V5_OLD_HEAD)
        self.facts['machine_workflow_sha'] = self.facts['native_frontend_actual_version'] = V5_OLD_HEAD
        self.frontend['deploymentVersion'] = V5_OLD_HEAD
        self.refresh_delta(); self.sync_machine()
        self.b._machine_sources(self.root, self.current, self.bridge)
        with mock.patch.dict(self.ns, {'_git_source': self.git}):
            self.b._v5_workflow_bridge_bytes(self.root, self.proof)

    def test_frontend_can_remain_distinct_from_workflow_and_runtime(self):
        self.facts['native_frontend_actual_version'] = V5_OLD_HEAD
        self.frontend['deploymentVersion'] = V5_OLD_HEAD
        self.sync_machine()
        self.b._machine_sources(self.root, self.current, self.bridge)

    def test_missing_actual_online_version_is_not_inferred_from_main(self):
        self.frontend = {'http_status': 403}
        self.sync_machine()
        self.denied(lambda: self.b._machine_sources(self.root, self.current, self.bridge))

    def test_frontend_version_replacement_is_rejected(self):
        self.frontend['deploymentVersion'] = 'a' * 40; self.sync_machine()
        self.denied(lambda: self.b._machine_sources(self.root, self.current, self.bridge))

    def test_unknown_hunk_even_with_rehashed_current_and_diff_is_rejected(self):
        self.after += b'\n# unexpected guard edit\n'
        self.proof['workflow_current'] = self.raw('evidence/changed-workflow.yml', self.after)
        self.refresh_delta()
        with mock.patch.dict(self.ns, {'_git_source': self.git}):
            self.denied(lambda: self.b._v5_workflow_bridge_bytes(self.root, self.proof))

    def test_full_diff_missing_hunk_is_rejected(self):
        raw = self.safe(self.root, self.proof['full_workflow_diff']['path']).read_bytes()
        self.proof['full_workflow_diff'] = self.raw('evidence/missing-hunk.diff', raw[:-50])
        with mock.patch.dict(self.ns, {'_git_source': self.git}):
            self.denied(lambda: self.b._v5_workflow_bridge_bytes(self.root, self.proof))

    def test_git_object_mismatch_is_rejected(self):
        with mock.patch.dict(self.ns, {'_git_source': lambda *args: b'changed object'}):
            self.denied(lambda: self.b._v5_workflow_bridge_bytes(self.root, self.proof))

    def test_wrong_current_commit_header_is_rejected(self):
        self.proof['actual_machine_workflow_sha'] = 'b' * 40
        self.denied(lambda: self.b._v5_bridge_header(self.proof))

    def test_prepared_source_proof_is_rejected(self):
        self.proof['prepared_only'] = True
        self.denied(lambda: self.b._v5_bridge_header(self.proof))

    def test_full_workflow_equivalence_claim_is_rejected(self):
        self.proof['whole_workflow_bytes_equal'] = True
        self.denied(lambda: self.b._v5_bridge_header(self.proof))

    def test_wrong_source_task_and_version_are_rejected(self):
        for key in ('source_task_id', 'source_candidate_version', 'source_scope'):
            changed = {**self.proof, key: 'wrong'}
            self.denied(lambda: self.b._v5_bridge_header(changed))

    def test_v4_aliases_in_v5_facts_are_rejected(self):
        self.facts['native_frontend_loaded_sha'] = self.b.V5_BASELINE_COMMIT; self.sync_machine()
        self.denied(lambda: self.b._machine_sources(self.root, self.current, self.bridge))

    def test_v5_is_not_silently_admitted_through_old_v4_path(self):
        self.denied(lambda: self.b._machine_sources(self.root, self.current))

    def test_new_permission_or_save_fact_is_rejected(self):
        for key in ('new_permits_issued', 'new_CMS_Save'):
            self.facts[key] = 1; self.sync_machine()
            self.denied(lambda: self.b._machine_sources(self.root, self.current, self.bridge))
            self.facts[key] = 0

    def test_original_v2_provenance_substitution_is_rejected(self):
        self.current['evidence']['original_V2'] = self.doc('evidence/wrong-v2.json', {'task_id': 'wrong'})
        self.sync_machine()
        self.denied(lambda: self.b._machine_sources(self.root, self.current, self.bridge))


class V5MachineBindingFocusedTests(V5SourceMachineFixture):
    def setUp(self):
        super().setUp()
        now = dt.datetime.now(dt.timezone.utc)
        self.issuer = self.raw('tools/managed_cms_permit_issuer.py', b'LOCAL_FIXTURE issuer')
        slug, record, fields = self.b.ROWS[2]
        self.row = {'slug': slug, 'record_id': record, 'raw_updated_at': '2026-10-10T00:00:00+00:00'}
        self.item = {'candidate_version': self.b.VERSION, 'action_id': 'paid-three-page-renovation-exact-fields-v1',
            'scope': f'company.example:services/{record}:{",".join(fields)}', 'payload_sha256': 'a' * 64}
        self.run = {'id': 38000000001, 'run_attempt': 1, 'actor': {'id': 276684684},
            'workflow_id': 351424533, 'path': self.b.WORKFLOW_CLI[0], 'head_sha': V5_NEW_HEAD,
            'head_branch': 'main', 'event': 'workflow_dispatch', 'status': 'completed', 'conclusion': 'success',
            'updated_at': (now - dt.timedelta(minutes=1)).isoformat(),
            'repository': {'id': 1248188229, 'full_name': 'wangchaozhuanyong/zhuangxiuwangzhan'}}
        workflow_ref = 'wangchaozhuanyong/zhuangxiuwangzhan/.github/workflows/content-publish-approved.yml@refs/heads/main'
        self.identity = {'runId': self.run['id'], 'runAttempt': 1, 'actorId': 276684684,
            'repositoryId': 1248188229, 'workflowRef': workflow_ref, 'workflowSha': V5_NEW_HEAD}
        self.probe = {'ok': True, 'dry_run': True, 'performed_write': False, 'identity': self.identity}
        self.receipt = {'task_id': self.b.TASK, 'candidate_version': self.b.VERSION,
            'action_id': self.item['action_id'], 'scope': self.item['scope'], 'operation': 'publish',
            'http_status': 200, 'dry_run': True, 'performed_write': False, 'external_writes': 0,
            'row_unchanged_after_dry_run': True, 'checked_at': (now-dt.timedelta(minutes=1, seconds=1)).isoformat()}
        self.payload = {'task_id': self.b.TASK, 'operation': 'publish', 'payload_sha256': self.item['payload_sha256'],
            'expected_updated_at': self.row['raw_updated_at']}
        self.machine = {'schema': 'actual_t3_protected_machine_binding_v1', 'original_machine_source': self.origin,
            'issuer_source': self.issuer, 'task_id': self.b.TASK, 'candidate_version': self.b.VERSION,
            'department': self.b.PRODUCER, 'action_id': self.item['action_id'], 'scope': self.item['scope'],
            'action_class': 'cms_write', 'record_id': record, 'payload_sha256': self.item['payload_sha256'],
            'github_actor_id': 276684684, 'repository': 'wangchaozhuanyong/zhuangxiuwangzhan',
            'workflow_id': 351424533, 'workflow_path': self.b.WORKFLOW_CLI[0], 'repository_id': 1248188229,
            'workflow_ref': workflow_ref, 'run_id': self.run['id'], 'run_attempt': 1,
            'workflow_sha': V5_NEW_HEAD, 'main_sha': V5_NEW_HEAD}
        self.sync_actual_machine()

    def sync_actual_machine(self):
        for key, value in (('run_snapshot', self.run), ('identity_probe', self.probe),
                           ('locked_preview', self.receipt), ('payload_digest', self.payload)):
            self.machine[key] = self.doc('machine/' + key + '.json', value)
        self.facts['records'][2].update(identity=self.identity, identity_probe=self.machine['identity_probe'],
            protected_forward_receipt=self.receipt, actual_payload_sha256=self.item['payload_sha256'],
            run_id=self.run['id'], run_attempt=self.run['run_attempt'], conclusion='success',
            full_original_gh_run=self.machine['run_snapshot'], run_updated_at=self.run['updated_at'],
            checked_at=self.receipt['checked_at'], guard_rejected_changed_original_CAS=False)
        self.proof['raw_machine_run'] = self.machine['run_snapshot']
        self.sync_machine()
        self.machine.update(actual_machine_source=self.facts_pin, source_bridge=self.bridge)
        self.item['machine_identity'] = self.doc('machine/binding.json', self.machine)
        self.accepted = {'original_machine_source': self.origin, 'consumer_sources': [self.issuer],
            'actual_machine_source': self.facts_pin, 'source_bridge': self.bridge, 'row': self.row, 'operation': self.proof['operation']}

    def run_machine(self):
        return self.b.validate_machine(self.root, self.item, self.accepted)

    def test_new_head_full_original_machine_binding_passes(self):
        self.assertEqual(self.run_machine()['main_sha'], V5_NEW_HEAD)

    def test_full_original_run_pin_cannot_be_replaced(self):
        self.machine['run_snapshot'] = self.doc('machine/replaced-run.json', {**self.run, 'id': 38000000002})
        self.item['machine_identity'] = self.doc('machine/binding.json', self.machine)
        self.denied(self.run_machine)

    def test_completed_repository_identity_remains_required(self):
        self.run['repository']['id'] = 2; self.sync_actual_machine(); self.denied(self.run_machine)
        self.run['repository']['id'] = 1248188229; self.run['status'] = 'in_progress'
        self.sync_actual_machine(); self.denied(self.run_machine)

    def test_original_actor_and_server_oidc_probe_cannot_change(self):
        self.machine['github_actor_id'] = 2
        self.item['machine_identity'] = self.doc('machine/binding.json', self.machine)
        self.denied(self.run_machine)

    def test_expired_original_preview_is_not_refreshed_by_run_metadata(self):
        self.receipt['checked_at'] = (dt.datetime.now(dt.timezone.utc)-dt.timedelta(hours=1)).isoformat()
        self.sync_actual_machine(); self.denied(self.run_machine)

    def test_stale_and_future_runs_remain_rejected(self):
        for delta in (-dt.timedelta(hours=1), dt.timedelta(minutes=1)):
            self.run['updated_at'] = (dt.datetime.now(dt.timezone.utc)+delta).isoformat()
            self.sync_actual_machine(); self.denied(self.run_machine)

    def test_wrong_source_bridge_pin_cannot_replace_frozen_acceptance(self):
        self.machine['source_bridge'] = self.doc('machine/changed-bridge.json', {**self.proof, 'prepared_only': True})
        self.item['machine_identity'] = self.doc('machine/binding.json', self.machine)
        self.denied(self.run_machine)

    def test_payload_or_original_raw_cas_change_is_rejected(self):
        self.payload['expected_updated_at'] = 'different'; self.sync_actual_machine(); self.denied(self.run_machine)

    def rollback_machine(self):
        self.proof['operation'] = 'rollback'
        action = 'rollback-' + self.b.VERSION
        self.item.update(candidate_version=self.b.ROLLBACK_VERSION, action_id=action, operation='rollback')
        self.machine.update(candidate_version=self.b.ROLLBACK_VERSION, action_id=action)
        self.run['id'] += 2
        self.machine['run_id'] = self.identity['runId'] = self.run['id']
        self.receipt.update(candidate_version=self.b.ROLLBACK_VERSION, action_id=action, operation='rollback')
        self.payload['operation'] = 'rollback'
        self.row['raw_updated_at'] = '2026-10-10T17:45:51.559189+00:00'
        self.payload['expected_updated_at'] = self.row['raw_updated_at']
        self.sync_actual_machine()

    def test_rollback_has_new_run_probe_receipt_and_exact_rollback_tuple(self):
        self.rollback_machine()
        result = self.run_machine()
        self.assertEqual(result['candidate_version'], self.b.ROLLBACK_VERSION)
        self.assertEqual(self.proof['operation'], 'rollback')

    def test_rollback_cannot_reuse_forward_tuple_or_forward_source_bridge(self):
        self.item.update(candidate_version=self.b.ROLLBACK_VERSION,
            action_id='rollback-' + self.b.VERSION, operation='rollback')
        self.denied(self.run_machine)
        self.rollback_machine()
        self.proof['operation'] = 'publish'; self.sync_actual_machine()
        self.denied(self.run_machine)


class V5CompleteSourceBridgeFocusedTests(V5MachineBindingFocusedTests):
    # Inherit the machine fixture only; inherited test methods are disabled below.
    def setUp(self):
        super().setUp()
        paths = ['content-publish/service.ts', '_shared/managed-targets.ts'] + [
            f'content-publish/fixture_{index}.ts' for index in range(19)]
        self.runtime = {path: ('LOCAL_FIXTURE runtime ' + path).encode() for path in paths}
        entries = [{'path': path, 'sha256': self.pair(raw)['sha256'], 'bytes': len(raw)}
            for path, raw in self.runtime.items()]
        self.runtime_manifest = {'schema': 'content-publish-runtime-source/v1',
            'entrypoint': 'content-publish/index.ts', 'files': entries}
        manifest_pin = self.doc('website-fixture/runtime-manifest.json', self.runtime_manifest)
        self.proof.update(actual_deployed_runtime_manifest=manifest_pin,
            actual_runtime_source_closure_file_count=21,
            actual_runtime_source_closure_digest=hashlib.sha256(json.dumps(entries,
                ensure_ascii=False, separators=(',', ':')).encode()).hexdigest(),
            runtime_file_map=[{'runtime_path': entry['path'], 'git_path': 'supabase/functions/' + entry['path'],
                'workflow_commit': V5_NEW_HEAD, 'workflow_commit_sha256': entry['sha256'],
                'workflow_commit_bytes': entry['bytes'], 'actual_deployed_v77_sha256': entry['sha256'],
                'actual_deployed_v77_bytes': entry['bytes']} for entry in entries])
        self.cli = {path: ('LOCAL_FIXTURE unchanged CLI ' + path).encode() for path in self.b.WORKFLOW_CLI[1:]}
        self.proof['workflow_and_CLI_source_map'] = [{'path': path, 'workflow_commit': V5_NEW_HEAD,
            'workflow_commit_sha256': self.pair(raw)['sha256'], 'approved_5237_source_sha256': self.pair(raw)['sha256'],
            'workflow_commit_bytes': len(raw), 'approved_5237_source_bytes': len(raw)} for path, raw in self.cli.items()]
        source_pins = [{'path': path, 'sha256': self.pair(raw)['sha256'], 'bytes': len(raw)} for path, raw in self.cli.items()]
        deployment_run = self.doc('website-fixture/deployment-run.json', {'run': {'id': 38061480070,
            'head_sha': self.b.V5_BASELINE_COMMIT, 'status': 'completed', 'conclusion': 'success', 'event': 'workflow_dispatch'}})
        function = [{'name': 'content-publish', 'version': 77, 'status': 'ACTIVE'}]
        metadata = [self.doc('website-fixture/' + name, function) for name in ('functions-after.json', 'functions-after-download.json')]
        readback = self.b.WEBSITE / self.b.DEPLOYMENT_EVIDENCE / 'production-r3-run-38061480070-artifacts/readback/edge-after/supabase/functions'
        original = {'task_id': self.b.TASK, 'content_candidate_version': self.b.VERSION,
            'source_candidate_version': self.b.WEBSITE_SOURCE_VERSION,
            'status': 'PASS_ACTUAL_PRODUCTION_EDGE_SOURCE_AND_RECOVERY_BACKUP',
            'production_website_sha': self.b.V5_BASELINE_COMMIT, 'run_id': 38061480070,
            'actual_function': {'name': 'content-publish', 'status': 'ACTIVE', 'after_version': 77, 'after_download_version': 77},
            'actual_readback': {'manifest': manifest_pin, 'root': str(readback),
                'source_sha256': self.proof['actual_runtime_source_closure_digest']},
            'run_proof': deployment_run, 'artifact_metadata_pins': metadata, 'source_pins': source_pins}
        self.proof['actual_deployment_source_proof'] = self.doc('website-fixture/deployment-source.json', original)
        snapshots = [self.raw('recovery/' + Path(path).name, self.runtime[path]) for path in paths[:2]]
        self.source = {'production_sha': self.b.V5_BASELINE_COMMIT, 'function_version': 77,
            'source_snapshots': snapshots}
        self.deployment = {'function_version': 77, 'deployment_run_id': 38061480070,
            'original_deployment_source_proof': self.proof['actual_deployment_source_proof']}
        self.source_adoption = mock.Mock()
        boundary = mock.patch.dict(self.ns, {'_website_json': lambda value: json.loads(self.safe(self.root, value['path']).read_bytes()),
            '_website_bytes': lambda value: self.runtime[Path(value['path']).relative_to(readback).as_posix()],
            '_git_source': self.source_git, '_v5_source_adoption': self.source_adoption})
        boundary.start(); self.addCleanup(boundary.stop)
        self.sync_complete_bridge()

    def source_git(self, commit, path):
        if path == self.b.WORKFLOW_CLI[0]: return self.git(commit, path)
        if path in self.cli: return self.cli[path]
        return self.runtime[path.removeprefix('supabase/functions/')]

    def sync_complete_bridge(self):
        self.sync_machine()
        self.machine['source_bridge'] = self.bridge
        self.accepted.update(source_bridge=self.bridge, current_producer=self.proof['current_producer'], operation='publish')
        self.source['source_coherence'] = self.bridge

    def run_bridge(self):
        return self.b.source_coherence(self.root, self.source, self.deployment, self.machine, self.accepted)

    def test_complete_v5_branch_compares_all_21_runtime_and_two_cli(self):
        self.assertEqual(self.run_bridge(), self.bridge)
        self.source_adoption.assert_called_once()

    def test_complete_v5_branch_refuses_missing_runtime_and_third_cli(self):
        self.proof['runtime_file_map'].pop(); self.sync_complete_bridge(); self.denied(self.run_bridge)
        # Restore the complete runtime mapping, then add a third CLI entry.
        entry = self.runtime_manifest['files'][-1]
        self.proof['runtime_file_map'].append({'runtime_path': entry['path'], 'git_path': 'supabase/functions/' + entry['path'],
            'workflow_commit': V5_NEW_HEAD, 'workflow_commit_sha256': entry['sha256'], 'workflow_commit_bytes': entry['bytes'],
            'actual_deployed_v77_sha256': entry['sha256'], 'actual_deployed_v77_bytes': entry['bytes']})
        self.proof['workflow_and_CLI_source_map'].append(copy.deepcopy(self.proof['workflow_and_CLI_source_map'][0]))
        self.sync_complete_bridge(); self.denied(self.run_bridge)


# This lane reports unique tests; do not re-count inherited machine cases.
for name in dir(V5MachineBindingFocusedTests):
    if name.startswith('test_'):
        setattr(V5CompleteSourceBridgeFocusedTests, name, None)


class V5SourceAdoptionFocusedTests(V5SourceMachineFixture):
    def setUp(self):
        super().setUp()
        self.package = 'source-package'
        self.files, self.operations, self.current_sources = [], [], []
        for path in sorted(self.b.V5_CHANGED_SOURCES):
            before = ('LOCAL_FIXTURE before ' + path + '\n').encode()
            after = ('LOCAL_FIXTURE after ' + path + '\n').encode()
            baseline = self.raw(self.package + '/baseline/' + path, before)
            candidate = self.raw(self.package + '/candidate/' + path, after)
            self.raw(path, after)
            backup = self.raw('backups/' + self.b.V5_SOURCE_TASK + '/FP/forward/' + path, before)
            row = {'path': path, 'before': self.pair(before), 'after': self.pair(after),
                'expected_source': self.pair(before), 'candidate_content': self.pair(after),
                'baseline': baseline, 'candidate': candidate, 'candidate_relative_path': 'candidate/' + path}
            for direction, first, last in [('forward', before, after), ('reverse', after, before)]:
                raw = ''.join(difflib.unified_diff(first.decode().splitlines(keepends=True),
                    last.decode().splitlines(keepends=True), fromfile='a/' + path, tofile='b/' + path)).encode()
                relative = 'diffs/' + path.replace('/', '_') + '.' + direction + '.diff'
                frozen = self.raw(self.package + '/' + relative, raw)
                row[direction + '_diff_relative_path'] = relative
                row[direction + '_diff_content'] = {key: frozen[key] for key in ('sha256', 'size')}
                if direction == 'forward': row['diff'] = frozen
            self.files.append(row)
            self.operations.append({'path': path, 'before': row['before'], 'after_expected': row['after'],
                'after_actual': row['after'], 'backup': backup, 'before_mode': 0o644,
                'write_attempted': True, 'verified_after': True})
        for path in self.b.SOURCES:
            if path not in self.b.V5_CHANGED_SOURCES: self.raw(path, ('LOCAL_FIXTURE protected ' + path).encode())
            self.current_sources.append(self.fpin(path))
        self.proof.update(goal_contract=self.doc('evidence/goal-contract.json', {'task_id': self.b.V5_SOURCE_TASK}),
            human_authorization=self.doc('evidence/human.json', {'source': 'LOCAL_FIXTURE_ONLY'}),
            current_consumer_sources=self.current_sources)
        self.manifest = {'schema': 'flashcast-exact-source-candidate/v1', 'task_id': self.b.V5_SOURCE_TASK,
            'candidate_version': self.b.V5_SOURCE_VERSION, 'scope': self.b.V5_SOURCE_SCOPE,
            'goal_contract': self.proof['goal_contract'], 'human_authorization': self.proof['human_authorization'],
            'current_source_context': {'workflow_commit': V5_NEW_HEAD, 'workflow_source': self.workflow_after, 'frontend_version': self.frontend_pin},
            'files': self.files, 'protected_sources': [p for p in self.current_sources if p['path'] in self.b.V5_PROTECTED_SOURCES]}
        fingerprint = self.b.digest(self.manifest); self.manifest['candidate_fingerprint'] = fingerprint
        self.manifest_pin = self.doc(self.package + '/candidate-manifest.json', self.manifest)
        # Freeze backups under the exact local fixture fingerprint, never live backups.
        for operation in self.operations:
            operation['backup'] = self.raw(operation['backup']['path'].replace('/FP/', '/' + fingerprint + '/'),
                self.safe(self.root, operation['backup']['path']).read_bytes())
        self.proof['candidate_manifest'] = self.manifest_pin
        self.producer = {'task_id': self.b.V5_SOURCE_TASK, 'department': 'system-development',
            'candidate_version': self.b.V5_SOURCE_VERSION, 'candidate_fingerprint': fingerprint,
            'evidence': {'candidate_manifest': self.manifest_pin}}
        self.producer_pin = self.doc('evidence/source-producer.json', self.producer)
        self.plan = {'candidate_version': self.b.V5_SOURCE_VERSION, 'scope': self.b.V5_SOURCE_SCOPE,
            'reviewer_department': self.b.ROLE, 'producer_department': 'system-development'}
        self.plan_pin = self.doc('evidence/source-plan.json', self.plan)
        self.proof.update(producer_outbox=self.producer_pin, review_plan=self.plan_pin)
        self.now = dt.datetime.now(dt.timezone.utc)
        self.box = {'schema_version': '2.0', 'task_id': self.b.V5_SOURCE_TASK, 'department': self.b.ROLE,
            'candidate_version': self.b.V5_SOURCE_VERSION, 'scope': self.b.V5_SOURCE_SCOPE, 'status': 'partial',
            'evidence': [self.manifest_pin], **{key: False for key in self.b.V5_REVIEW_FLAGS},
            'reply_observed_at': (self.now-dt.timedelta(minutes=4)).isoformat(),
            'created_at': (self.now-dt.timedelta(minutes=3)).isoformat(),
            'candidate_review': {'actor': self.b.ROLE, 'verdict': 'PASS_SOURCE_CANDIDATE_ONLY',
                'phase': 'candidate_source_only', 'direction': 'forward', 'candidate_manifest': self.manifest_pin,
                'candidate_fingerprint': fingerprint, 'review_plan': self.plan_pin,
                'producer_outbox': self.producer_pin, 'goal_contract': self.proof['goal_contract'],
                'human_authorization': self.proof['human_authorization'], 'workflow_commit': V5_NEW_HEAD,
                'workflow_source': self.workflow_after, 'frontend_version': self.frontend_pin,
                **{key: False for key in self.b.V5_REVIEW_FLAGS}}}
        self.review_pin = self.doc('evidence/source-qa.json', self.box)
        self.proof['source_qa'] = self.review_pin
        self.journal = {'task_id': self.b.V5_SOURCE_TASK, 'candidate_version': self.b.V5_SOURCE_VERSION,
            'candidate_fingerprint': fingerprint, 'direction': 'forward', 'status': 'complete', 'actor': self.b.ROLE,
            'review_outbox': self.review_pin, 'external_writes': 0, 'execution_id': 'LOCAL_FIXTURE_EXECUTION',
            'decision_record_id': 'LOCAL_FIXTURE_DECISION', 'source_operations': self.operations,
            'applied': [p['path'] for p in self.operations],
            'started_at': (self.now-dt.timedelta(minutes=2)).isoformat(),
            'completed_at': (self.now-dt.timedelta(minutes=1)).isoformat()}
        self.journal_pin = self.doc('evidence/source-adoption.json', self.journal)
        self.proof.update(source_adoption=self.journal_pin, adoption_followthrough_record_id='LOCAL_FIXTURE_FOLLOW')
        common = {'task_id': self.b.V5_SOURCE_TASK, 'coordinator_role': self.b.ROLE, 'decision_actor': self.b.ROLE,
            'responsible_assistant': self.b.ROLE, 'candidate_version': self.b.V5_SOURCE_VERSION,
            'sender_department': 'system-development', 'outbox': self.producer_pin,
            'business_goal_closed': False, 'coordinator_owner': 'LOCAL_FIXTURE_A2_OWNER', 'coordination_fence': 42}
        self.decision = {**common, 'record_id': 'LOCAL_FIXTURE_DECISION', 'event': 'controller_decision',
            'decision': 'continue', 'next_owner': self.b.ROLE, 'evidence': [self.review_pin]}
        self.follow = {**common, 'record_id': 'LOCAL_FIXTURE_FOLLOW', 'event': 'controller_followthrough',
            'followthrough_status': 'blocked_with_owner',
            'unblock_condition': 'source-adopted:' + self.journal['execution_id'] + ';remaining:original-T3-current-Saved-readback-and-public-postcheck',
            'next_check_at': (self.now+dt.timedelta(minutes=30)).isoformat(),
            'evidence': [self.journal_pin], 'created_at': self.now.isoformat()}
        self.handoffs = [self.decision, self.follow]
        goal = {'parent_task_id': self.b.TASK, 'primary_owner': 'system-development',
            'producer_departments': ['system-development'], 'authorized_scope': [self.b.V5_SOURCE_SCOPE],
            'acceptance_capability': 'development', 'authorization_pin': self.proof['human_authorization']}
        self.doc('goal.json', {'task_id': self.b.V5_SOURCE_TASK, 'goal_contract': self.proof['goal_contract'],
            'goal_delivery': goal, 'qa_review_plan': {'pin': self.plan_pin}})
        g = types.ModuleType('goal_delivery_runtime');g.restore_goal=lambda root,snapshot:snapshot;g.validate_goal=lambda *args:None
        q = types.ModuleType('qa_review_plan');q._goal_reviewer=lambda *args:self.b.ROLE
        q._binding=lambda root,snapshot:snapshot['qa_review_plan'];q.validate_plan=lambda *args:None
        q._assigned_review_round=lambda *args:{'LOCAL_FIXTURE':'assigned'}
        q._producer_candidate_bound=lambda *args:True;q._evidence_pins=lambda value:iter(value)
        c = types.ModuleType('scoped_candidate_adoption');c._committed=lambda root,row:self.committed.append(row['record_id'])
        c._receipts=lambda *args:[]
        modules = mock.patch.dict(sys.modules, {'goal_delivery_runtime':g,'qa_review_plan':q,'scoped_candidate_adoption':c})
        modules.start();self.addCleanup(modules.stop)
        self.native = mock.Mock()
        boundary = mock.patch.dict(self.ns, {'_native':self.native,
            '_v5_source_responsibility':mock.Mock(return_value={'structural_fixture_only':True}),
            '_v5_source_decision_fence':mock.Mock(return_value={'reserved_at':self.now.timestamp(),'committed_at':self.now.timestamp()})});boundary.start();self.addCleanup(boundary.stop)
        self.accepted = {'consumer_sources':self.current_sources}

    def run_adoption(self):
        return self.b._v5_source_adoption(self.root,self.proof,self.accepted)

    def sync_review(self):
        self.review_pin=self.doc('evidence/source-qa.json',self.box);self.proof['source_qa']=self.review_pin
        self.journal['review_outbox']=self.review_pin;self.decision['evidence']=[self.review_pin]
        self.sync_journal()

    def sync_journal(self):
        self.journal_pin=self.doc('evidence/source-adoption.json',self.journal)
        self.proof['source_adoption']=self.journal_pin;self.follow['evidence']=[self.journal_pin]

    def test_new_head_source_only_qa_and_exact_cas_journal_pass(self):
        self.run_adoption()
        self.assertEqual(self.committed,['LOCAL_FIXTURE_DECISION','LOCAL_FIXTURE_FOLLOW'])
        self.assertIn(V5_NEW_HEAD,self.native.call_args.args[2])

    def test_manifest_source_context_cannot_be_relabelled_after_exact_review(self):
        self.manifest["current_source_context"]["workflow_commit"] = V5_OLD_HEAD
        self.manifest["candidate_fingerprint"] = self.b.digest({k:v for k,v in self.manifest.items() if k!="candidate_fingerprint"})
        self.proof["candidate_manifest"] = self.doc(self.package+"/candidate-manifest.json",self.manifest)
        self.denied(self.run_adoption)

    def test_new_head_requires_new_qa_commit_binding(self):
        self.box['candidate_review']['workflow_commit']=V5_OLD_HEAD;self.sync_review()
        self.denied(self.run_adoption)

    def test_missing_independent_source_qa_fails_closed(self):
        self.proof['source_qa']=None;self.denied(self.run_adoption)

    def test_prepared_or_old_task_qa_cannot_migrate(self):
        self.box['prepared_only']=True;self.sync_review();self.denied(self.run_adoption)
        self.box.pop('prepared_only');self.box['task_id']='fc-20261010-paid-three-page-candidate-consumer-source-repair-v1'
        self.sync_review();self.denied(self.run_adoption)

    def test_self_review_actor_is_rejected(self):
        self.box['candidate_review']['actor']='system-development';self.sync_review();self.denied(self.run_adoption)

    def test_full_goal_pass_or_platform_permission_claim_is_rejected(self):
        self.box['candidate_review']['production_write_allowed']=True;self.sync_review();self.denied(self.run_adoption)

    def test_journal_without_actual_committed_followthrough_is_rejected(self):
        self.handoffs.pop();self.denied(self.run_adoption)

    def test_wrong_execution_id_or_fence_is_rejected(self):
        original=self.follow['unblock_condition'];self.follow['unblock_condition']='wrong';self.denied(self.run_adoption)
        self.follow['unblock_condition']=original;self.follow['coordination_fence']=43
        self.denied(self.run_adoption)

    def test_uncommitted_source_effect_is_rejected(self):
        def deny_commit(root,row):
            if row['record_id']=='LOCAL_FIXTURE_FOLLOW':raise self.w.WorkflowError('fixture uncommitted')
        with mock.patch.object(sys.modules['scoped_candidate_adoption'],'_committed',deny_commit):
            self.denied(self.run_adoption)

    def test_current_source_wip_drift_is_rejected(self):
        self.raw('tools/paid_three_page_bounded_cms.py',b'LOCAL_FIXTURE concurrent WIP')
        self.denied(self.run_adoption)

    def test_original_backup_drift_is_rejected(self):
        self.raw(self.operations[0]['backup']['path'],b'changed backup');self.denied(self.run_adoption)

    def test_partial_or_duplicate_operations_are_rejected(self):
        self.journal['status']='partial_complete';self.sync_journal();self.denied(self.run_adoption)
        self.journal['status']='complete';self.journal['source_operations'][-1]=self.journal['source_operations'][0]
        self.sync_journal();self.denied(self.run_adoption)

    def test_fingerprint_or_reverse_diff_change_is_rejected(self):
        self.manifest['candidate_fingerprint']='0'*64
        self.proof['candidate_manifest']=self.doc(self.package+'/candidate-manifest.json',self.manifest)
        self.denied(self.run_adoption)

    def test_missing_native_review_is_rejected(self):
        self.native.side_effect=self.w.WorkflowError('fixture no actual native review');self.denied(self.run_adoption)




if __name__ == "__main__":
    unittest.main()
