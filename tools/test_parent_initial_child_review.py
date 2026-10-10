"""Isolated existing-consumer fixtures; never a native or company trial."""
import copy
import json
import unittest

import goal_delivery_runtime as g
import flashcast_ops as ops
import parent_initial_child_review as child_review
import qa_review_plan as q
import scoped_candidate_adoption as s
import test_scoped_candidate_adoption as existing
import workflow_control as w


class ParentInitialChildReviewTests(unittest.TestCase):
    def setUp(self):
        self.fixture = existing.ScopedAdoptionTests("runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        f = self.fixture
        self.root = f.root
        self.dispatch = f.send_child()
        self.ack = f.fixture.receipt("chat_ack", s.PRODUCER, "v4-source-child-ack")
        self.child = f.child
        f.consumer.task_id = self.child
        self.candidate = f.write_pin("reports/v4-child-result.json", {
            "task_id": self.child, "candidate_version": "child-read-only-v1", "department": s.PRODUCER})
        box = f.consumer.result_box(s.PRODUCER, "child-read-only-v1", self.candidate)
        box.update(parent_task_id=s.TASK)
        self.producer_pin = f.write_pin("logs/department-outbox/v4-source-child.json", box)
        self.outbox = f.fixture.receipt("outbox_received", s.PRODUCER, "v4-source-child-result", evidence=self.producer_pin["path"])
        self.completed = f.consumer.completed_result_fields()
        self.identity = {"task_id": self.child, "sender_department": s.PRODUCER,
            "candidate_version": "child-read-only-v1", "result_sha256": self.producer_pin["sha256"],
            "outbox_path": self.producer_pin["path"]}
        self.queued, _ = w.record_result_handoff(self.root, {**self.identity, **self.completed,
            "event": "notification_queued", "idempotency_key": "v4-source-child-queue"})
        lease = f.store.claim(self.identity, s.ROLE, "isolated-a2", "v4-source-child-claim")
        self.intake, _ = w.record_result_handoff(self.root, {**self.identity, **self.completed,
            "event": "controller_received", "intake_mode": "queue", "idempotency_key": "v4-source-child-intake",
            "coordinator_role": s.ROLE, "coordinator_owner": "isolated-a2", "coordination_claim": lease})
        self.proof = child_review.build_proof(self.root, self.snapshot(), self.producer_pin)
        self.plan = f.consumer.review_plan(self.candidate)
        self.plan.update(action_class="read_only_candidate", parent_initial_child_review=self.proof)

    def snapshot(self):
        return w.read_json(w.snapshot_path(self.root, self.child))

    def prepare(self, proof=None):
        return child_review.prepare(self.root, self.snapshot(), proof or self.proof)

    def bind(self, plan=None):
        plan = plan or self.plan
        path = self.fixture.consumer.write("drafts/operations/v4-child-formal-review.json", plan)
        return q.bind_plan(self.root, task_id=self.child, plan_path=path, coordinator_role=s.ROLE)

    def test_real_consumers_bind_formal_result_PASS_and_close_only_child_without_reviewer_send_ACK(self):
        before = {path: path.read_bytes() for path in self.root.rglob("*") if path.is_file()}
        context = self.prepare()
        self.assertEqual(context["source_kind"], "parent_initial_child_review")
        self.assertEqual(context["producer_dispatch"]["department"], s.PRODUCER)
        self.assertNotIn("dispatch", context); self.assertNotIn("ack", context)
        self.assertFalse(context["reviewer_dispatch_fabricated"]); self.assertFalse(context["parent_goal_completed"])
        self.assertEqual(before, {path: path.read_bytes() for path in self.root.rglob("*") if path.is_file()})
        self.bind()
        resumed = q._assigned_review_round(self.root, self.snapshot(), s._receipts(self.root, self.child), self.plan)
        self.assertEqual(resumed["source_kind"], "parent_initial_child_review")
        verdict = self.fixture.consumer.assistant_verdict(self.plan, self.producer_pin,
            parent_initial_child_review=self.proof)
        self.assertEqual(verdict["workflow_state"], "closed")
        self.assertEqual(w._validate_receipt_chain(self.root, self.child)[1], [])
        self.assertEqual(w.validate_workflow_events(self.root, self.child), [])
        rows = s._receipts(self.root, self.child)
        self.assertFalse(any(row["department"] == s.ROLE and row["receipt_type"] in {
            "dispatch_sent", "dispatch_failed", "chat_ack"} for row in rows))
        self.assertFalse(any(row.get("verdict") == "pass" for row in s._receipts(self.root, s.TASK)))
        self.assertEqual(self.snapshot()["goal_delivery"]["source_mode"], "approved_dispatch")
        self.assertEqual(self.bind()["result"], "duplicate_ignored")

    def test_wrong_parent_child_action_scope_human_role_policy_and_result_references_rejected(self):
        for changes in ({"parent_task_id": "fc-unrelated-parent"}, {"task_id": s.TASK},
                        {"action_id": "different-action"}, {"scope": "project:flashcast:other:v1"},
                        {"authority": self.proof["goal_contract"]}, {"responsible_assistant": s.PRODUCER},
                        {"producer_department": s.ROLE}, {"policy_decision_id": "missing-policy"},
                        {"parent_decision_record_id": "missing-decision"}, {"dispatch_receipt_hash": "a" * 64},
                        {"ack_receipt_id": self.outbox["receipt_id"]}, {"producer_outbox": self.candidate},
                        {"notification_record_id": self.intake["record_id"]},
                        {"controller_received_record_id": self.queued["record_id"]}):
            with self.subTest(changes=changes), self.assertRaises(w.WorkflowError):
                self.prepare({**self.proof, **changes})

    def test_wrong_candidate_version_result_source_mode_and_self_review_plan_rejected(self):
        for changes in ({"candidate_version": "wrong-child-version"}, {"candidate": self.producer_pin},
                        {"reviewer_department": s.PRODUCER}, {"producer_department": s.ROLE},
                        {"action_class": "external_publish"}, {"production_write_allowed": True},
                        {"native_multi_goal_review": self.fixture.plan["native_multi_goal_review"]}):
            with self.subTest(changes=changes), self.assertRaises(w.WorkflowError):
                q.validate_plan(self.root, self.snapshot(), {**self.plan, **changes})

    def test_missing_initial_source_or_queue_intake_cannot_admit_a_child(self):
        paths = [w.receipts_path(self.root, self.child), w.snapshot_path(self.root, self.child),
                 self.root / "logs/goal-initial-dispatch" / self.child / "native.json"]
        for path in paths:
            original = path.read_bytes()
            with self.subTest(path=str(path)), self.assertRaises((w.WorkflowError, KeyError)):
                if path == w.receipts_path(self.root, self.child):
                    path.write_text("", encoding="utf-8")
                elif path == w.snapshot_path(self.root, self.child):
                    value = json.loads(original); value["goal_contract"] = self.proof["parent_goal_contract"]
                    w.atomic_write_json(path, value)
                else:
                    path.unlink()
                self.prepare()
            path.write_bytes(original)
        handoff = w.result_handoff_path(self.root, self.child)
        original = handoff.read_bytes()
        rows = [json.loads(line) for line in original.decode().splitlines()]
        handoff.write_text("\n".join(json.dumps(row) for row in rows if row.get("task_id") != self.child) + "\n", encoding="utf-8")
        with self.assertRaises(w.WorkflowError): self.prepare()
        handoff.write_bytes(original)

    def test_cross_project_permissions_and_parent_human_contract_drift_rejected(self):
        registry_path = self.root / "data/department-registry.json"
        original = registry_path.read_bytes()
        registry = json.loads(original)
        for role in (s.ROLE, s.PRODUCER):
            value = copy.deepcopy(registry)
            next(row for row in value["departments"] if row["id"] == role)["chat_binding"]["project_id"] = "other-project"
            w.atomic_write_json(registry_path, value)
            with self.subTest(role=role), self.assertRaises(w.WorkflowError): self.prepare()
            registry_path.write_bytes(original)
        child_path = w.safe_path(self.root, self.proof["goal_contract"]["path"])
        original = child_path.read_bytes()
        value = json.loads(original); value["production_write_allowed"] = True
        w.atomic_write_json(child_path, value)
        with self.assertRaises(w.WorkflowError): self.prepare()
        child_path.write_bytes(original)
        authority = w.safe_path(self.root, self.proof["authority"]["path"])
        original = authority.read_bytes(); authority.write_bytes(original + b"\n")
        with self.assertRaises(w.WorkflowError): self.prepare()
        authority.write_bytes(original)

    def test_original_record_and_native_effect_drift_cannot_be_rehashed_into_new_source(self):
        receipt_path = w.receipts_path(self.root, self.child)
        original = receipt_path.read_bytes()
        rows = [json.loads(line) for line in original.decode().splitlines()]
        rows[0]["parent_initial_dispatch"]["coordinator_role"] = s.PRODUCER
        previous = ""
        for row in rows:
            row["previous_hash"] = previous
            row["receipt_hash"] = w.sha256_value(w._receipt_payload_for_hash(row)); previous = row["receipt_hash"]
        receipt_path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
        proof = copy.deepcopy(self.proof)
        proof["dispatch_receipt_hash"], proof["ack_receipt_hash"], proof["producer_outbox_receipt_hash"] = [row["receipt_hash"] for row in rows]
        with self.assertRaises(w.WorkflowError): self.prepare(proof)
        receipt_path.write_bytes(original)
        native = w.safe_path(self.root, self.dispatch["parent_initial_dispatch"]["actual_native_transport"]["path"])
        original = native.read_bytes(); value = json.loads(original)
        value["actual_native_send"]["isError"] = True
        w.atomic_write_json(native, value)
        with self.assertRaises(w.WorkflowError): self.prepare()
        native.write_bytes(original)

    def test_unbound_review_old_source_and_missing_final_outbox_declaration_rejected(self):
        with self.assertRaises(w.WorkflowError):
            q.validate_verdict(self.root, self.snapshot(), s._receipts(self.root, self.child),
                {"task_id": self.child, "department": s.ROLE, "verdict": "pass"})
        self.bind()
        with self.assertRaisesRegex((w.WorkflowError, ops.OpsError), "declare the exact original first-send source"):
            self.fixture.consumer.assistant_verdict(self.plan, self.producer_pin)

    def test_valid_append_retains_original_history_but_stale_result_cannot_accept_current_goal(self):
        self.bind()
        blocked = self.fixture.consumer.assistant_verdict(self.plan, self.producer_pin, verdict="blocked",
            parent_initial_child_review=self.proof)
        old_box = w.read_json(w.safe_path(self.root, next(pin for pin in blocked["evidence"] if pin["path"].endswith(".json"))["path"]))
        self.fixture.consumer.producer_result("child-read-only-v2")
        self.prepare()
        self.assertEqual(child_review.build_proof(self.root, self.snapshot(), self.producer_pin), self.proof)
        self.assertEqual(w._validate_receipt_chain(self.root, self.child)[1], [])
        old_box["qa_verdict"] = "pass"
        old_box["goal_acceptance"].update(accepted_scope=[s.SCOPE], remaining_scope=[])
        path = self.fixture.consumer.write("logs/department-outbox/v4-stale-child-review.json", old_box)
        self.fixture.fixture.receipt("outbox_received", s.ROLE, "v4-stale-child-review-result", evidence=path)
        with self.assertRaisesRegex((w.WorkflowError, ops.OpsError), "producer current result bytes differ"):
            self.fixture.fixture.receipt("qa_verdict", s.ROLE, "v4-stale-child-review-verdict", evidence=path,
                verdict="pass", **{key: self.plan[key] for key in ("action_id", "action_class", "scope")})
        self.assertEqual(w._validate_receipt_chain(self.root, self.child)[1], [])


if __name__ == "__main__":
    unittest.main()
