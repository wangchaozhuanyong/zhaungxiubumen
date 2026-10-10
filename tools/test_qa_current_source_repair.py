"""Original outbox identity and owner-direct reviewer sources; isolated fixtures."""
import copy
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import unittest
from unittest import mock

import qa_review_plan as review
import result_coordination as coordination
import test_goal_result_coordination as claims
import test_result_coordination as existing
import workflow_control as w

A2, PRODUCER = "operations-assistant-2", "content-organic-website"


class CurrentSourceQATests(unittest.TestCase):
    receive = existing.ResultCoordinationIntegrationTests.receive
    claim = existing.ResultCoordinationIntegrationTests.claim
    draft = existing.ResultCoordinationIntegrationTests.draft
    claimed_request = existing.ResultCoordinationIntegrationTests.claimed_request
    set_goal = claims.GoalCoordinationTests.set_goal

    def setUp(self):
        area = Path(os.environ.get("QA_CURRENT_SOURCE_TEST_OUTPUT", str(Path(__file__).resolve().parents[1] / ".test-tmp")))
        area.mkdir(parents=True, exist_ok=True); (area / ".test-tmp").mkdir(exist_ok=True)
        with mock.patch.object(existing, "CANDIDATE", area), mock.patch.object(claims, "TMP", area):
            claims.GoalCoordinationTests.setUp(self)
        handoff = self.root / "reports/original-handoff.md"
        handoff.write_text("Synthetic original bounded handoff, not platform permission.\n")
        self.set_goal(A2, source_mode="owner_direct", existing_results=[w.file_digest(self.root, "reports/original-handoff.md")])
        self.snapshot = w.read_json(w.snapshot_path(self.root, self.identity["task_id"]))
        self.snapshot["departments"] = [{"department": role, "chat_task_id": "fixed-" + role} for role in (PRODUCER, A2)]
        w.atomic_write_json(self.root / "reports/original-goal.json", self.snapshot["goal_delivery"])
        self.snapshot["goal_contract"] = w.file_digest(self.root, "reports/original-goal.json")
        w.atomic_write_json(w.snapshot_path(self.root, self.identity["task_id"]), self.snapshot)
        self.producer_pin = w.file_digest(self.root, self.base["outbox_path"])
        self.producer = w.read_json(self.root / self.base["outbox_path"])
        self.fixture.receipt("outbox_received", PRODUCER, "original-producer-outbox", evidence=self.base["outbox_path"])
        lease = self.a.claim(self.identity, A2, A2, "original-assigned-intake")
        self.intake = w.record_result_handoff(self.root, self.claimed_request(lease))[0]
        w.atomic_write_json(self.root / "reports/original-native-send.json", {
            "content": [{"type": "text", "text": json.dumps({"threadId": "fixed-" + PRODUCER})}], "isError": False})
        producer_input = ("Synthetic local native source, never a production permission.\n"
            + "task_id=" + self.identity["task_id"] + "; human=synthetic-owner-message; original-handoff; "
            + A2 + "; " + PRODUCER + "; " + str(self.root / "reports/original-goal.json"))
        responsibility = "Synthetic original independent responsibility.\n3. 原包reports/。\n保持原目标和原授权。"
        self.native_input("producer", PRODUCER, A2, producer_input)
        self.native_input("reviewer-responsibility", A2, "operations", responsibility)
        w.atomic_write_json(self.root / "reports/original-native-send-attempt.json", {
            "task_id": self.identity["task_id"], "target_thread_id": "fixed-" + PRODUCER,
            "source_mode": "owner_direct_human_authorized_forwarding", "human_message_id": "synthetic-owner-message",
            "payload_sha256": hashlib.sha256(producer_input.encode()).hexdigest(), "payload_size": len(producer_input.encode()),
            "native_send_started": True, "ordinary_dispatch_or_allow_fabricated": False,
            "CMS_permission_created": False, "production_executed": False})
        text = "Synthetic real-source-shaped existing reviewer reply; not a fabricated dispatch.\n"
        sha = hashlib.sha256(text.encode()).hexdigest()
        native = {"task_id": self.identity["task_id"], "fixed_chat_task_id": "fixed-" + A2, "cwd": str(self.root),
            "source_turn_id": "synthetic-original-reviewer-turn", "source_message_id": "synthetic-original-reviewer-message",
            "text": text, "message_sha256": sha, "utf8_bytes": len(text.encode()),
            "nonempty": True, "in_current_fixed_department_chat": True, "phase": "commentary"}
        w.atomic_write_json(self.root / "reports/original-reviewer-native.json", native)
        source = {"schema_version": "2.0", "task_id": self.identity["task_id"], "department": A2,
            "fixed_chat_task_id": "fixed-" + A2, "candidate_version": "old-partial-source-only",
            "status": "needs_input", "conclusion": "Synthetic original partial source, not a formal verdict",
            "evidence": [], "risks": [], "next_actions": [], "handoff": {"receiver": "operations"},
            "approval_required": False, "learning": {"status": "no_new_learning"},
            "created_at": w.utc_timestamp(), "chat_reply": {
                "proof": w.file_digest(self.root, "reports/original-reviewer-native.json"), "message_sha256": sha,
                "source_message_id": native["source_message_id"], "source_turn_id": native["source_turn_id"],
                "nonempty": True, "in_current_fixed_department_chat": True}}
        w.atomic_write_json(self.root / "reports/original-reviewer-outbox.json", source)
        self.proof = {"schema_version": 1, "task_id": self.identity["task_id"], "responsible_assistant": A2,
            "scope": self.snapshot["goal_delivery"]["authorized_scope"][0],
            "producer_department": PRODUCER, "authority": self.snapshot["goal_delivery"]["authorization_pin"],
            "goal_contract": self.snapshot["goal_contract"], "original_handoff": w.file_digest(self.root, "reports/original-handoff.md"),
            "producer_outbox": self.producer_pin, "producer_native_send": w.file_digest(self.root, "reports/original-native-send.json"),
            "producer_native_received": w.file_digest(self.root, "reports/original-producer-native-received.json"),
            "producer_native_input": w.file_digest(self.root, "reports/original-producer-input.md"),
            "producer_send_attempt": w.file_digest(self.root, "reports/original-native-send-attempt.json"),
            "reviewer_native_responsibility": w.file_digest(self.root, "reports/original-reviewer-responsibility-native-received.json"),
            "reviewer_responsibility_input": w.file_digest(self.root, "reports/original-reviewer-responsibility-input.md"),
            "intake_record_id": self.intake["record_id"], "reviewer_source_outbox": w.file_digest(self.root, "reports/original-reviewer-outbox.json"),
            "reviewer_native_reply": w.file_digest(self.root, "reports/original-reviewer-native.json")}
        self.plan = {"schema_version": 1, "task_id": self.identity["task_id"], "action_id": "review-original-result",
            "action_class": "internal_control_candidate", "scope": self.snapshot["goal_delivery"]["authorized_scope"][0],
            "candidate_version": self.identity["candidate_version"], "candidate_sha256": self.producer_pin["sha256"],
            "candidate": self.producer_pin, "producer_department": PRODUCER, "reviewer_department": A2,
            "reviewer_thread_id": "fixed-" + A2, "controller_department": A2, "controller_thread_id": "fixed-" + A2,
            "single_final_reviewer": True, "risk_level": "R0", "production_write_allowed": False, "external_permission_issued": False}

    def native_input(self, name, receiver, sender, text):
        raw = "<codex_delegation>\n  <source_thread_id>fixed-" + sender + "</source_thread_id>\n  <input>" + text + "</input>\n</codex_delegation>"
        native = {"schema_version": 1, "source_tool": "mcp__codex_app__read_thread",
            "actual_receiver_thread_id": "fixed-" + receiver, "actual_receiver_department": receiver,
            "actual_receiver_project_root": str(self.root), "source_is_actual_native_function_call_output": True,
            "no_synthetic_userMessage_or_dispatch": True, "new_production_permissions": False,
            "actual_receiving_turn": {"id": "synthetic-local-" + name + "-turn", "status": "completed",
                "startedAt": dt.datetime.now(dt.timezone.utc).timestamp() - 1},
            "actual_function_call_output": {"type": "functionCallOutput", "id": "synthetic-local-" + name,
                "name": "send_message_to_thread", "namespace": "codex_app", "output": {"text": raw, "truncated": False}},
            "actual_wrapper_sha256": hashlib.sha256(raw.encode()).hexdigest(), "actual_wrapper_bytes": len(raw.encode()),
            "actual_input_utf8_sha256": hashlib.sha256(text.encode()).hexdigest(), "actual_input_utf8_bytes": len(text.encode())}
        w.atomic_write_json(self.root / ("reports/original-" + name + "-native-received.json"), native)
        (self.root / ("reports/original-" + name + "-input.md")).write_bytes(text.encode())

    def repin_changed_native(self, name, change):
        proof = copy.deepcopy(self.proof)
        path = self.root / proof[name]["path"]
        native = w.read_json(path); change(native); w.atomic_write_json(path, native)
        proof[name] = w.file_digest(self.root, proof[name]["path"])
        return proof

    def bind(self, direct=True):
        plan = {**self.plan, **({"owner_direct_review": self.proof} if direct else {})}
        path = "drafts/operations/review-original-result.json"
        w.atomic_write_json(self.root / path, plan)
        review.bind_plan(self.root, task_id=self.identity["task_id"], plan_path=path, coordinator_role=A2)
        self.snapshot = w.read_json(w.snapshot_path(self.root, self.identity["task_id"]))
        return plan

    def final_inputs(self, direct=True):
        plan = self.bind(direct)
        goal = self.snapshot["goal_delivery"]
        box = {"schema_version": "2.0", "task_id": self.identity["task_id"], "department": A2,
            "fixed_chat_task_id": "fixed-" + A2, "candidate_version": plan["candidate_version"], "status": "completed",
            "conclusion": "Synthetic bounded independent review", "evidence": [self.snapshot["qa_review_plan"]["pin"], self.producer_pin],
            "risks": [], "next_actions": [], "handoff": {"receiver": "operations"}, "approval_required": False,
            "learning": {"status": "no_new_learning"}, "risk_level": "R0", "production_write_allowed": False,
            "external_permission_issued": False, "production_release_eligible": False,
            "chat_reply": {"nonempty": True, "in_current_fixed_department_chat": True, "ref": "synthetic-current-final", "sha256": "a" * 64},
            "review_identity": {key: plan[key] for key in review.IDENTITY}, "qa_verdict": "pass",
            "goal_acceptance": {**{key: goal[key] for key in ("completion_criteria", "primary_owner", "responsible_assistant")},
                "accepted_scope": goal["authorized_scope"], "remaining_scope": [], "producer_results": {PRODUCER: self.producer_pin}}}
        if direct: box["owner_direct_review"] = self.proof
        path = "logs/department-outbox/current-independent-review.json"
        w.atomic_write_json(self.root / path, box); pin = w.file_digest(self.root, path)
        stamp = dt.datetime.now(dt.timezone.utc).isoformat()
        receipts = w._validate_receipt_chain(self.root, self.identity["task_id"])[0]
        if not direct:
            receipts += [{"receipt_type": "dispatch_sent", "department": A2, "chat_task_id": "fixed-" + A2,
                "scope": plan["scope"], "evidence": [self.snapshot["qa_review_plan"]["pin"], self.producer_pin], "created_at": stamp},
                {"receipt_type": "chat_ack", "department": A2, "chat_task_id": "fixed-" + A2, "ack_nonempty": True, "created_at": stamp}]
        receipts += [{"receipt_type": "outbox_received", "department": A2, "evidence": [pin], "created_at": stamp}]
        verdict = {"receipt_type": "qa_verdict", "department": A2, "chat_task_id": "fixed-" + A2,
            "evidence": [pin], "verdict": "pass", "created_at": stamp,
            **{key: plan[key] for key in ("task_id", "action_id", "action_class", "scope")}}
        return receipts, verdict, path, box

    def test_original_outbox_self_identity_has_no_hash_cycle(self):
        before = (self.root / self.base["outbox_path"]).read_bytes()
        self.assertFalse(any(self.producer_pin == value for value in self.producer["evidence"].values()))
        receipts, verdict, _, _ = self.final_inputs(direct=False)
        review.validate_verdict(self.root, self.snapshot, receipts, verdict)
        self.assertEqual((self.root / self.base["outbox_path"]).read_bytes(), before)

    def test_named_dictionary_evidence_pin_is_read_exactly(self):
        candidate = self.snapshot["goal_delivery"]["authorization_pin"]
        self.assertTrue(review._producer_candidate_bound(self.root, {**self.plan, "candidate": candidate},
            self.producer_pin, {**self.producer, "evidence": {"result": candidate}}))

    def test_owner_direct_prepare_and_final_use_original_sources_without_fake_receipts(self):
        origin = review.prepare_owner_direct_review(self.root, self.snapshot, self.proof)
        self.assertTrue(origin["prepared_only"]); self.assertFalse(origin["reviewer_dispatch_fabricated"])
        before = w.receipts_path(self.root, self.identity["task_id"]).read_bytes()
        receipts, verdict, _, _ = self.final_inputs()
        review.validate_verdict(self.root, self.snapshot, receipts, verdict)
        self.assertEqual(w.receipts_path(self.root, self.identity["task_id"]).read_bytes(), before)
        self.assertFalse(any(row.get("department") == A2 and row.get("receipt_type") in {"dispatch_sent", "chat_ack"} for row in receipts))

    def test_missing_original_source_pin_rejected(self):
        for key in ("authority", "goal_contract", "original_handoff", "producer_outbox", "producer_native_send",
                    "producer_native_received", "producer_native_input", "producer_send_attempt",
                    "reviewer_native_responsibility", "reviewer_responsibility_input",
                    "reviewer_source_outbox", "reviewer_native_reply"):
            with self.subTest(key=key), self.assertRaises(w.WorkflowError):
                proof = copy.deepcopy(self.proof); proof.pop(key)
                review.prepare_owner_direct_review(self.root, self.snapshot, proof)

    def test_wrong_receiving_identity_or_source_tool_is_rejected_even_after_repin(self):
        path = self.root / self.proof["reviewer_native_responsibility"]["path"]
        original = path.read_bytes()
        for changes in ({"actual_receiver_department": "operations-assistant-3"},
                        {"actual_receiver_thread_id": "fixed-operations-assistant-3"},
                        {"actual_receiver_project_root": str(self.root.parent)},
                        {"source_tool": "synthetic-sidecar"},
                        {"source_is_actual_native_function_call_output": False}):
            path.write_bytes(original)
            proof = self.repin_changed_native("reviewer_native_responsibility", lambda row: row.update(changes))
            with self.subTest(changes=changes), self.assertRaises(w.WorkflowError):
                review.prepare_owner_direct_review(self.root, self.snapshot, proof)
        path.write_bytes(original)

    def test_wrong_native_sender_and_non_native_item_rejected(self):
        for name in ("reviewer_native_responsibility", "producer_native_received"):
            path = self.root / self.proof[name]["path"]; original = path.read_bytes()
            for field, value in (("type", "userMessage"), ("name", "read_thread"), ("namespace", "foreign")):
                path.write_bytes(original)
                proof = self.repin_changed_native(name, lambda row: row["actual_function_call_output"].update({field: value}))
                with self.subTest(name=name, field=field), self.assertRaises(w.WorkflowError):
                    review.prepare_owner_direct_review(self.root, self.snapshot, proof)
            path.write_bytes(original)
            proof = self.repin_changed_native(name, lambda row: row["actual_function_call_output"]["output"].update(
                {"text": row["actual_function_call_output"]["output"]["text"].replace("<source_thread_id>", "<source_thread_id>wrong-")}))
            with self.assertRaisesRegex(w.WorkflowError, "delegation source"):
                review.prepare_owner_direct_review(self.root, self.snapshot, proof)
            path.write_bytes(original)

    def test_changed_received_utf8_and_wrong_frozen_input_rejected(self):
        for name in ("reviewer_native_responsibility", "producer_native_received"):
            path = self.root / self.proof[name]["path"]; original = path.read_bytes()
            proof = self.repin_changed_native(name, lambda row: row["actual_function_call_output"]["output"].update(
                {"text": row["actual_function_call_output"]["output"]["text"].replace("</input>", "\n</input>")}))
            with self.subTest(name=name), self.assertRaisesRegex(w.WorkflowError, "UTF8"):
                review.prepare_owner_direct_review(self.root, self.snapshot, proof)
            path.write_bytes(original)
        proof = {**self.proof, "reviewer_responsibility_input": self.proof["producer_native_input"]}
        with self.assertRaisesRegex(w.WorkflowError, "UTF8"):
            review.prepare_owner_direct_review(self.root, self.snapshot, proof)

    def test_old_producer_task_input_same_target_is_rejected(self):
        self.native_input("producer", PRODUCER, A2, "task_id=fc-old-unrelated; synthetic-owner-message; original-handoff; "
            + A2 + "; " + PRODUCER + "; " + str(self.root / "reports/original-goal.json"))
        proof = {**self.proof, "producer_native_received": w.file_digest(self.root, self.proof["producer_native_received"]["path"]),
                 "producer_native_input": w.file_digest(self.root, self.proof["producer_native_input"]["path"])}
        with self.assertRaisesRegex(w.WorkflowError, "exact task/goal/human"):
            review.prepare_owner_direct_review(self.root, self.snapshot, proof)

    def test_old_send_document_same_target_with_conflicting_task_input_rejected(self):
        value = {"threadId": "fixed-" + PRODUCER, "task_id": "fc-old-unrelated", "input": "Old unrelated task"}
        w.atomic_write_json(self.root / self.proof["producer_native_send"]["path"], value)
        proof = {**self.proof, "producer_native_send": w.file_digest(self.root, self.proof["producer_native_send"]["path"])}
        with self.assertRaisesRegex(w.WorkflowError, "target mismatch"):
            review.prepare_owner_direct_review(self.root, self.snapshot, proof)

    def test_old_reviewer_task_scope_or_missing_original_packet_rejected(self):
        for text in ("Original responsibility for an unrelated old task.",
                     "3. Original packet reports/ and fc-old-unrelated.",
                     "3. Original packet reports/ and project:test:stale-v0."):
            self.native_input("reviewer-responsibility", A2, "operations", text)
            proof = {**self.proof, "reviewer_native_responsibility": w.file_digest(self.root, self.proof["reviewer_native_responsibility"]["path"]),
                     "reviewer_responsibility_input": w.file_digest(self.root, self.proof["reviewer_responsibility_input"]["path"])}
            with self.subTest(text=text), self.assertRaises(w.WorkflowError):
                review.prepare_owner_direct_review(self.root, self.snapshot, proof)

    def test_wrong_scope_and_stale_human_grant_are_rejected(self):
        for changes in ({"scope": "project:test:stale-v0"}, {"authority": self.proof["reviewer_source_outbox"]}):
            with self.subTest(changes=changes), self.assertRaises(w.WorkflowError):
                review.prepare_owner_direct_review(self.root, self.snapshot, {**self.proof, **changes})
        path = self.root / self.proof["producer_send_attempt"]["path"]
        attempt = w.read_json(path); attempt["human_message_id"] = "synthetic-old-grant"
        w.atomic_write_json(path, attempt)
        proof = {**self.proof, "producer_send_attempt": w.file_digest(self.root, self.proof["producer_send_attempt"]["path"])}
        with self.assertRaisesRegex(w.WorkflowError, "send attempt/task/input/human"):
            review.prepare_owner_direct_review(self.root, self.snapshot, proof)

    def test_native_provenance_cannot_create_account_or_execution_permission(self):
        path = self.root / self.proof["producer_native_received"]["path"]
        proof = self.repin_changed_native("producer_native_received", lambda row: row.update({"new_production_permissions": True}))
        with self.assertRaises(w.WorkflowError):
            review.prepare_owner_direct_review(self.root, self.snapshot, proof)
        native = w.read_json(path); native["new_production_permissions"] = False; w.atomic_write_json(path, native)
        proof = {**self.proof, "producer_native_received": w.file_digest(self.root, self.proof["producer_native_received"]["path"])}
        prepared = review.prepare_owner_direct_review(self.root, self.snapshot, proof)
        self.assertFalse(prepared["external_permission_issued"])
        self.assertFalse(prepared["reviewer_dispatch_fabricated"])

    def test_missing_future_turn_or_truncated_received_source_rejected(self):
        path = self.root / self.proof["reviewer_native_responsibility"]["path"]
        original = path.read_bytes()
        for change in (lambda row: row.update({"actual_receiving_turn": {}}),
                       lambda row: row["actual_receiving_turn"].update({"startedAt": dt.datetime.now(dt.timezone.utc).timestamp() + 900}),
                       lambda row: row["actual_function_call_output"]["output"].update({"truncated": True})):
            path.write_bytes(original); proof = self.repin_changed_native("reviewer_native_responsibility", change)
            with self.assertRaises(w.WorkflowError):
                review.prepare_owner_direct_review(self.root, self.snapshot, proof)
        path.write_bytes(original)

    def test_original_receipt_prefix_rejects_missing_duplicate_id_and_corrupt_json(self):
        path = w.receipts_path(self.root, self.identity["task_id"])
        original = path.read_bytes()
        rows = w.read_jsonl(path)
        producer = next(row for row in rows if row.get("receipt_type") == "outbox_received" and row.get("department") == PRODUCER)
        for changes in (lambda allrows: [{**row, "receipt_id": ""} if row == producer else row for row in allrows],
                        lambda allrows: allrows + [{**producer, "receipt_type": "chat_ack"}]):
            bad = changes(copy.deepcopy(rows))
            path.write_text("".join(json.dumps(row) + "\n" for row in bad))
            with self.assertRaises(w.WorkflowError):
                review.prepare_owner_direct_review(self.root, self.snapshot, self.proof)
            path.write_bytes(original)
        for suffix in (b"not-json\n", b"[]\n"):
            path.write_bytes(original + suffix)
            with self.assertRaises(w.WorkflowError):
                review.prepare_owner_direct_review(self.root, self.snapshot, self.proof)
            path.write_bytes(original)
        receipts, invalid = w._validate_receipt_chain(self.root, self.identity["task_id"], through_receipt_id="not-a-real-receipt")
        self.assertTrue(invalid); self.assertEqual(receipts, [])

    def test_complete_qa_readback_still_rejects_mutated_formal_verdict(self):
        _, verdict, path, _ = self.final_inputs()
        self.fixture.receipt("outbox_received", A2, "current-original-reviewer-outbox", evidence=path)
        self.fixture.receipt("qa_verdict", A2, "current-original-reviewer-verdict", evidence=path,
            verdict="pass", action_id=verdict["action_id"], action_class=verdict["action_class"], scope=verdict["scope"])
        receiptpath = w.receipts_path(self.root, self.identity["task_id"])
        rows = w.read_jsonl(receiptpath)
        rows[-1]["scope"] = "project:test:wrong-formal-verdict"
        rows[-1]["receipt_hash"] = w.sha256_value(w._receipt_payload_for_hash(rows[-1]))
        receiptpath.write_text("".join(json.dumps(row) + "\n" for row in rows))
        self.assertTrue(review.prepare_owner_direct_review(self.root, self.snapshot, self.proof)["prepared_only"])
        _, invalid = w._validate_receipt_chain(self.root, self.identity["task_id"])
        self.assertTrue(any("exact_review_invalid" in item for item in invalid))

    def test_wrong_owner_producer_or_self_review_rejected(self):
        for changes in ({"responsible_assistant": "operations-assistant-3"}, {"producer_department": A2}, {"intake_record_id": "not-an-original-intake"}):
            with self.subTest(changes=changes), self.assertRaises(w.WorkflowError):
                review.prepare_owner_direct_review(self.root, self.snapshot, {**self.proof, **changes})
        snapshot = copy.deepcopy(self.snapshot); snapshot["goal_delivery"]["producer_departments"].append(A2)
        with self.assertRaisesRegex(w.WorkflowError, "self review"):
            review.prepare_owner_direct_review(self.root, snapshot, self.proof)

    def test_changed_native_source_or_goal_pin_rejected(self):
        for key in ("reviewer_native_reply", "goal_contract"):
            pin = self.proof[key]; path = self.root / pin["path"]; raw = path.read_bytes()
            with self.subTest(key=key), self.assertRaises(w.WorkflowError):
                path.write_bytes(raw + b"\n")
                review.prepare_owner_direct_review(self.root, self.snapshot, self.proof)
            path.write_bytes(raw)

    def test_current_formal_outbox_must_declare_exact_original_proof(self):
        receipts, verdict, path, box = self.final_inputs()
        box.pop("owner_direct_review"); w.atomic_write_json(self.root / path, box)
        pin = w.file_digest(self.root, path); receipts[-1]["evidence"] = [pin]; verdict["evidence"] = [pin]
        with self.assertRaisesRegex(w.WorkflowError, "declare the exact original owner-direct"):
            review.validate_verdict(self.root, self.snapshot, receipts, verdict)

    def test_authorized_unrelated_allowed_scope_migration_does_not_repin_history(self):
        before = review.prepare_owner_direct_review(self.root, self.snapshot, self.proof)
        registry = w.read_json(self.root / "data/department-registry.json")
        chat_before = {row["id"]: row.get("chat_binding") for row in registry["departments"]}
        registry.setdefault("collaboration_bindings", {})["designated-development"] = {
            "allowed_scope": ["Synthetic exactly authorized website scope", "Synthetic retained historical company runtime task"]}
        w.atomic_write_json(self.root / "data/department-registry.json", registry)
        after = review.prepare_owner_direct_review(self.root, self.snapshot, self.proof)
        self.assertEqual(before, after)
        self.assertEqual(chat_before, {row["id"]: row.get("chat_binding") for row in registry["departments"]})

    def test_relevant_current_fixed_identity_or_capability_drift_is_rejected(self):
        original = w.read_json(self.root / "data/department-registry.json")
        for field in ("chat_binding", "coordination_authority"):
            registry = copy.deepcopy(original)
            row = next(row for row in registry["departments"] if row["id"] == A2)
            if field == "chat_binding": row[field]["task_id"] = "wrong-current-reviewer-chat"
            else: row[field]["review_capabilities"] = []
            w.atomic_write_json(self.root / "data/department-registry.json", registry)
            with self.subTest(field=field), self.assertRaises(w.WorkflowError):
                review.prepare_owner_direct_review(self.root, self.snapshot, self.proof)
        w.atomic_write_json(self.root / "data/department-registry.json", original)

    def test_actual_receipt_consumer_records_formal_outbox_and_verdict_without_fake_dispatch(self):
        _, verdict, path, _ = self.final_inputs()
        self.fixture.receipt("outbox_received", A2, "current-original-reviewer-outbox", evidence=path)
        self.fixture.receipt("qa_verdict", A2, "current-original-reviewer-verdict", evidence=path,
            verdict="pass", action_id=verdict["action_id"], action_class=verdict["action_class"], scope=verdict["scope"])
        receipts, invalid = w._validate_receipt_chain(self.root, self.identity["task_id"])
        self.assertEqual(invalid, [])
        self.assertEqual([row["receipt_type"] for row in receipts if row.get("department") == A2], ["outbox_received", "qa_verdict"])
        self.assertFalse(any(row.get("production_write_allowed") is True for row in receipts))


if __name__ == "__main__":
    unittest.main()
