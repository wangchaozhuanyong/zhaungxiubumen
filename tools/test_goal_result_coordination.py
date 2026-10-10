"""Synthetic bounded fixtures, real coordination/native append, no platform actions."""
import copy
import datetime as dt
import json
from pathlib import Path
import threading
import unittest
from unittest import mock

import qa_review_plan as review
import result_coordination as coordination
import test_result_coordination as existing
import test_runtime_qa_admission as qa_existing
import workflow_control as w

TMP = Path(__file__).resolve().parents[1] / ".test-tmp"
ASSISTANTS = ("operations-assistant", "operations-assistant-2", "operations-assistant-3")


def configure(root):
    w.atomic_write_json(root / "data/task-contract.json", {"goal_delivery_runtime": {
        "model": "goal_delivery_assistant_v1", "assistant_decisions_enabled": True}})
    registry = w.read_json(root / "data/department-registry.json")
    template = copy.deepcopy(next(r for r in registry["departments"] if r["id"] == "operations"))
    for role in (*ASSISTANTS, "new-registered-assistant"):
        row = next((r for r in registry["departments"] if r["id"] == role), None)
        if row is None:
            row = copy.deepcopy(template); row["id"] = role; registry["departments"].append(row)
        row["chat_binding"] = {**template["chat_binding"], "task_id": "fixed-" + role, "title": role}
        row["coordination_authority"] = {"routine_decisions": True, "review_capabilities": ["development"]}
    w.atomic_write_json(root / "data/department-registry.json", registry)
    w.atomic_write_json(root / "reports/synthetic-owner-message.json", {
        "fixture_only": True, "source_thread_id": "synthetic-owner-thread", "message": {
            "type": "userMessage", "id": "synthetic-owner-message", "content": [
                {"type": "text", "text": "Synthetic local fixture authorization, no provider action."}]}})


def goal(assistant=ASSISTANTS[0]):
    return {"objective": "complete exact internal result", "completion_criteria": ["exact evidence accepted"],
            "primary_owner": "content-organic-website", "responsible_assistant": assistant,
            "existing_results": [], "authorized_scope": ["project:test:exact-v1"], "dependencies": [],
            "producer_departments": ["content-organic-website"], "acceptance_capability": "development",
            "human_authorization": {"source_thread_id": "synthetic-owner-thread", "message_id": "synthetic-owner-message",
                                    "executor": "content-organic-website", "scope": "project:test:exact-v1",
                                    "evidence_path": "reports/synthetic-owner-message.json"}}


class GoalCoordinationTests(unittest.TestCase):
    receive = existing.ResultCoordinationIntegrationTests.receive
    claim = existing.ResultCoordinationIntegrationTests.claim
    draft = existing.ResultCoordinationIntegrationTests.draft
    claimed_request = existing.ResultCoordinationIntegrationTests.claimed_request

    def setUp(self):
        TMP.mkdir(parents=True, exist_ok=True)
        existing.ResultCoordinationIntegrationTests.setUp(self)
        configure(self.root)
        self.set_goal()

    def set_goal(self, assistant=ASSISTANTS[0], **changes):
        snapshot = w.read_json(w.snapshot_path(self.root, self.identity["task_id"]))
        snapshot["goal_delivery"] = {**goal(assistant), **changes}
        snapshot["goal_delivery"]["authorization_pin"] = w.file_digest(self.root, "reports/synthetic-owner-message.json")
        w.atomic_write_json(w.snapshot_path(self.root, self.identity["task_id"]), snapshot)

    def test_three_assistants_and_new_registered_role_can_own_assigned_results(self):
        for role in (*ASSISTANTS, "new-registered-assistant"):
            self.set_goal(role)
            lease = self.a.claim(self.identity, role, role, "wake-" + role)
            self.assertEqual(lease["role"], role)
            self.a.release(self.identity, role, role, lease, "bounded synthetic owner finished")

    def test_three_assistants_contend_only_assigned_role_wins(self):
        barrier = threading.Barrier(3); results = []
        def contender(role):
            store = coordination.CoordinationStore(self.root)
            try:
                barrier.wait()
                results.append(store.claim(self.identity, role, role, "wake-" + role))
            except w.WorkflowError as exc:
                results.append(str(exc))
            finally:
                store.close()
        threads = [threading.Thread(target=contender, args=(role,)) for role in ASSISTANTS]
        for thread in threads: thread.start()
        for thread in threads:
            thread.join(10); self.assertFalse(thread.is_alive())
        self.assertEqual(len([r for r in results if isinstance(r, dict)]), 1)
        self.assertEqual(len([r for r in results if isinstance(r, str) and "assigned" in r]), 2)

    def test_assigned_assistant_records_real_native_final_event_once(self):
        lease = self.claim()
        request = self.claimed_request(lease)
        first, _ = w.record_result_handoff(self.root, request)
        again, _ = w.record_result_handoff(self.root, request)
        self.assertEqual(first["event"], "controller_received")
        self.assertEqual(again["record_id"], first["record_id"])
        self.assertEqual(again["result"], "duplicate_ignored")

    def test_new_task_requires_claim_even_for_operations_bootstrap(self):
        for role in ("operations", ASSISTANTS[0]):
            with self.subTest(role=role), self.assertRaisesRegex(w.WorkflowError, "claim"):
                w.record_result_handoff(self.root, self.receive(coordinator_role=role, coordinator_owner=role))

    def test_unassigned_and_self_review_rejected_before_claim(self):
        with self.assertRaisesRegex(w.WorkflowError, "assigned"):
            self.claim(role=ASSISTANTS[1])
        self.set_goal(producer_departments=["content-organic-website", ASSISTANTS[0]])
        with self.assertRaisesRegex(w.WorkflowError, "self review"):
            self.claim()

    def test_capability_and_registry_authority_are_required(self):
        self.set_goal(acceptance_capability="paid")
        with self.assertRaisesRegex(w.WorkflowError, "capability"):
            self.claim()
        registry = w.read_json(self.root / "data/department-registry.json")
        next(r for r in registry["departments"] if r["id"] == ASSISTANTS[0])["coordination_authority"]["routine_decisions"] = False
        w.atomic_write_json(self.root / "data/department-registry.json", registry)
        with self.assertRaisesRegex(w.WorkflowError, "registered coordinator"):
            self.claim()

    def test_transfer_fences_old_owner_and_records_actual_assignment_binding(self):
        lease = self.claim(); self.draft(lease)
        target = self.a.transfer(self.identity, lease["role"], lease["owner"], lease, ASSISTANTS[1], "assistant-2", "transfer-1")
        self.assertTrue(target["assignment_change"]["snapshot_binding_required"])
        self.assertGreater(target["fence"], lease["fence"])
        with self.assertRaisesRegex(w.WorkflowError, "foreign coordination"):
            self.a.renew(self.identity, lease["role"], lease["owner"], lease)
        self.assertEqual(w.read_json(w.snapshot_path(self.root, self.identity["task_id"]))["goal_delivery"]["responsible_assistant"], ASSISTANTS[1])
        self.assertIn("assignment_receipt", target)
        self.assertEqual(w.record_result_handoff(self.root, self.claimed_request(target))[0]["result"], "recorded")

    def test_transfer_cannot_change_to_different_capability(self):
        lease = self.claim(); self.draft(lease)
        registry = w.read_json(self.root / "data/department-registry.json")
        next(r for r in registry["departments"] if r["id"] == ASSISTANTS[1])["coordination_authority"]["review_capabilities"] = ["paid"]
        w.atomic_write_json(self.root / "data/department-registry.json", registry)
        with self.assertRaisesRegex(w.WorkflowError, "capability"):
            self.a.transfer(self.identity, lease["role"], lease["owner"], lease, ASSISTANTS[1], "assistant-2", "transfer")
        self.assertEqual(self.a.readback(self.identity)["token"], lease["token"])

    def assert_transfer_rejected_without_mutation(self, lease, message):
        before = dict(self.a._row(self.identity))
        audit = [dict(row) for row in self.a.conn.execute("SELECT * FROM coordination_audit ORDER BY seq")]
        paths = [w.snapshot_path(self.root, self.identity["task_id"]),
                 w.receipts_path(self.root, self.identity["task_id"]), self.root / w.WORKFLOW_EVENTS]
        original = {path: path.read_bytes() if path.exists() else None for path in paths}
        with self.assertRaisesRegex(w.WorkflowError, message):
            self.a.transfer(self.identity, lease["role"], lease["owner"], lease,
                            ASSISTANTS[1], "assistant-2", "invalid-no-plan-transfer")
        self.assertEqual(dict(self.a._row(self.identity)), before)
        self.assertEqual([dict(row) for row in self.a.conn.execute("SELECT * FROM coordination_audit ORDER BY seq")], audit)
        self.assertEqual({path: path.read_bytes() if path.exists() else None for path in paths}, original)
        renewed = self.a.renew(self.identity, lease["role"], lease["owner"], lease)
        self.assertEqual((renewed["role"], renewed["owner"], renewed["token"], renewed["fence"]),
                         (lease["role"], lease["owner"], lease["token"], lease["fence"]))

    def test_no_plan_expired_target_rejection_preserves_renewable_original_claim(self):
        lease = self.claim(); self.draft(lease)
        registry = w.read_json(self.root / "data/department-registry.json")
        target = next(row for row in registry["departments"] if row["id"] == ASSISTANTS[1])
        target["chat_binding"]["last_health_check_at"] = "2000-01-01T00:00:00+00:00"
        w.atomic_write_json(self.root / "data/department-registry.json", registry)
        self.assert_transfer_rejected_without_mutation(lease, "fresh actual target assistant binding")

    def test_no_plan_invalid_target_health_states_preserve_original_claim(self):
        lease = self.claim(); self.draft(lease)
        original = w.read_json(self.root / "data/department-registry.json")
        states = ({"last_health_check_at": "2999-01-01T00:00:00+00:00"},
                  {"status": "unbound"}, {"dispatch_eligible": False}, {"reply_health": "failed"})
        for state in states:
            with self.subTest(state=state):
                registry = copy.deepcopy(original)
                target = next(row for row in registry["departments"] if row["id"] == ASSISTANTS[1])
                target["chat_binding"].update(state)
                w.atomic_write_json(self.root / "data/department-registry.json", registry)
                self.assert_transfer_rejected_without_mutation(lease, "fresh actual target assistant binding")

    def test_no_plan_existing_verdict_history_preserves_original_claim(self):
        lease = self.claim(); self.draft(lease)
        path = w.receipts_path(self.root, self.identity["task_id"])
        original = path.read_bytes() if path.exists() else b""
        for verdict in ("pass", "blocked"):
            with self.subTest(verdict=verdict):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(original)
                receipts = w.read_jsonl(path)
                # Deliberately anomalous local history, not a legal native verdict:
                # modern review has no plan and must fail closed before lease commit.
                row = {"task_id": self.identity["task_id"], "receipt_type": "qa_verdict",
                       "receipt_id": "synthetic-unbound-verdict", "department": ASSISTANTS[0],
                       "verdict": verdict, "evidence": [], "fixture_only": True,
                       "previous_hash": receipts[-1]["receipt_hash"] if receipts else ""}
                row["receipt_hash"] = w.sha256_value(w._receipt_payload_for_hash(row))
                w.append_jsonl_locked(path, row)
                self.assert_transfer_rejected_without_mutation(lease, "intact original chains|verdict cannot be migrated")

    def test_no_plan_damaged_receipt_chain_preserves_original_claim(self):
        lease = self.claim(); self.draft(lease)
        w.append_jsonl_locked(w.receipts_path(self.root, self.identity["task_id"]),
                             {"task_id": self.identity["task_id"], "receipt_type": "chat_ack",
                              "receipt_hash": "0" * 64, "evidence": [], "fixture_only": True})
        self.assert_transfer_rejected_without_mutation(lease, "intact original chains")

    def test_no_plan_damaged_event_chain_preserves_original_claim(self):
        lease = self.claim(); self.draft(lease)
        w.append_jsonl_locked(self.root / w.WORKFLOW_EVENTS,
                             {"task_id": self.identity["task_id"], "state": "evidence_received",
                              "event_hash": "0" * 64, "fixture_only": True})
        self.assert_transfer_rejected_without_mutation(lease, "intact original chains")

    def test_no_plan_changed_human_pin_preserves_original_claim(self):
        lease = self.claim(); self.draft(lease)
        path = self.root / "reports/synthetic-owner-message.json"
        path.write_text(path.read_text() + "\n")
        self.assert_transfer_rejected_without_mutation(lease, "frozen human authorization changed")

    def test_transfer_holds_workflow_lock_through_validation_commit_and_assignment(self):
        import fcntl
        import goal_delivery_runtime as runtime
        lease = self.claim(); self.draft(lease)
        stages = []
        prepare = runtime.prepare_assignment_transfer

        def locked_prepare(*args):
            # An independent descriptor cannot obtain the workflow flock at either
            # precommit validation or committed assignment apply.
            with (self.root / w.LOCK_FILE).open("a+") as handle:
                with self.assertRaises(BlockingIOError):
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            stages.append(self.a.conn.in_transaction)
            return prepare(*args)

        with mock.patch.object(runtime, "prepare_assignment_transfer", side_effect=locked_prepare):
            target = self.a.transfer(self.identity, lease["role"], lease["owner"], lease,
                                     ASSISTANTS[1], "assistant-2", "locked-transfer")
        self.assertEqual(stages, [True, False])
        self.assertEqual(target["fence"], lease["fence"] + 1)
        snapshot = w.read_json(w.snapshot_path(self.root, self.identity["task_id"]))
        self.assertEqual(snapshot["goal_delivery"]["responsible_assistant"], ASSISTANTS[1])
        self.assertTrue(any(row["department"] == ASSISTANTS[1] for row in snapshot["departments"]))

    def test_frozen_reviewer_transfer_requires_new_plan_before_changing_lease(self):
        snapshot_path = w.snapshot_path(self.root, self.identity["task_id"])
        snapshot = w.read_json(snapshot_path)
        snapshot["departments"] = [{"department": role, "chat_task_id": "fixed-" + role}
                                  for role in ("content-organic-website", ASSISTANTS[0])]
        w.atomic_write_json(snapshot_path, snapshot)
        path = "drafts/operations/coordination-candidate.json"
        w.atomic_write_json(self.root / path, {"task_id": self.identity["task_id"], "department": "content-organic-website",
                                             "candidate_version": self.identity["candidate_version"]})
        pin = w.file_digest(self.root, path)
        plan = {"schema_version": 1, "task_id": self.identity["task_id"], "action_id": "review-result",
                "action_class": "internal_control_candidate", "scope": "project:test:exact-v1",
                "candidate_version": self.identity["candidate_version"], "candidate_sha256": pin["sha256"], "candidate": pin,
                "producer_department": "content-organic-website", "reviewer_department": ASSISTANTS[0],
                "reviewer_thread_id": "fixed-" + ASSISTANTS[0], "controller_department": "operations",
                "controller_thread_id": "fixed-operations", "single_final_reviewer": True,
                "risk_level": "R0", "production_write_allowed": False, "external_permission_issued": False}
        plan_path = "drafts/operations/coordination-review-plan.json"; w.atomic_write_json(self.root / plan_path, plan)
        review.bind_plan(self.root, task_id=self.identity["task_id"], plan_path=plan_path, coordinator_role=ASSISTANTS[0])
        lease = self.claim(); self.draft(lease)
        with self.assertRaisesRegex(w.WorkflowError, "new frozen review plan required"):
            self.a.transfer(self.identity, lease["role"], lease["owner"], lease, ASSISTANTS[1], "assistant-2", "transfer")
        self.assertEqual(self.a.readback(self.identity)["token"], lease["token"])
        new_path = "drafts/operations/coordination-review-plan-transfer.json"
        w.atomic_write_json(self.root / new_path, {**plan, "reviewer_department": ASSISTANTS[1], "reviewer_thread_id": "fixed-" + ASSISTANTS[1]})
        transferred = self.a.transfer(self.identity, lease["role"], lease["owner"], lease, ASSISTANTS[1], "assistant-2", "transfer",
                                      review_plan_path=new_path)
        current = w.read_json(snapshot_path)
        self.assertEqual(current["goal_delivery"]["responsible_assistant"], ASSISTANTS[1])
        self.assertEqual(review.reviewer_department(self.root, current), ASSISTANTS[1])
        history = current["goal_delivery"]["assignment_history"]
        self.assertTrue(history)
        self.assertEqual(history[-1]["review_plan_transfer"]["previous_binding"]["pin"], w.file_digest(self.root, plan_path))
        self.assertGreater(transferred["fence"], lease["fence"])

    def test_expired_new_assistant_recovery_renews_fence_and_denies_stale_token(self):
        now = dt.datetime.now(dt.timezone.utc); self.a.clock = lambda: now
        lease = self.claim(ttl_seconds=1); self.a.clock = lambda: now + dt.timedelta(seconds=2)
        with self.assertRaisesRegex(w.WorkflowError, "explicit recovery"):
            self.claim(request_id="restart")
        recovered = self.a.recover(self.identity, lease["role"], lease["owner"], "restart", "native state reconciled")
        self.assertGreater(recovered["fence"], lease["fence"])
        with self.assertRaises(w.WorkflowError): self.draft(lease)
        renewed = self.a.renew(self.identity, recovered["role"], recovered["owner"], recovered, 900)
        self.assertEqual(renewed["fence"], recovered["fence"])

    def test_committed_transfer_interruption_recovers_assignment_without_old_token(self):
        import goal_delivery_runtime as runtime
        lease = self.claim(); self.draft(lease)
        with mock.patch.object(runtime, "record_assignment_transfer", side_effect=RuntimeError("synthetic crash after SQL commit")):
            with self.assertRaises(RuntimeError):
                self.a.transfer(self.identity, lease["role"], lease["owner"], lease, ASSISTANTS[1], "assistant-2", "transfer-interrupted")
        current = self.a.readback(self.identity)
        self.assertGreater(current["fence"], lease["fence"])
        self.assertEqual(w.read_json(w.snapshot_path(self.root, self.identity["task_id"]))["goal_delivery"]["responsible_assistant"], ASSISTANTS[0])
        with self.assertRaises(w.WorkflowError): self.a.renew(self.identity, lease["role"], lease["owner"], lease)
        path = "reports/synthetic-transfer-recovery.json"; w.atomic_write_json(self.root / path, self.identity)
        recovered = runtime.recover_transfer(self.root, path)
        self.assertEqual(recovered["responsible_assistant"], ASSISTANTS[1])
        self.assertEqual(runtime.recover_transfer(self.root, path)["result"], "duplicate_ignored")
        self.assertEqual(self.a.readback(self.identity)["token"], current["token"])
        self.assertNotEqual(current["token"], lease["token"])

    def test_assistant_uncertain_append_requires_readback_before_retry(self):
        lease = self.claim(); request = self.claimed_request(lease)
        with self.assertRaises(RuntimeError):
            with coordination.handoff_guard(self.root, request): raise RuntimeError("synthetic crash before append")
        with self.assertRaisesRegex(w.WorkflowError, "explicit recover_reservation"):
            w.record_result_handoff(self.root, request)
        recovered = coordination.recover_reservation(self.root, request, "actual native append readback absent")
        self.assertFalse(recovered["side_effect_executed"])
        self.assertEqual(recovered["status"], "retry_ready")
        self.assertEqual(w.record_result_handoff(self.root, request)[0]["result"], "recorded")

    def test_global_switch_does_not_migrate_old_task(self):
        snapshot = w.read_json(w.snapshot_path(self.root, self.identity["task_id"]))
        del snapshot["goal_delivery"]; w.atomic_write_json(w.snapshot_path(self.root, self.identity["task_id"]), snapshot)
        with self.assertRaisesRegex(w.WorkflowError, "registered coordinator"):
            self.claim(role=ASSISTANTS[1])
        with self.assertRaisesRegex(w.WorkflowError, "assistant precheck"):
            w.record_result_handoff(self.root, self.receive(coordinator_role=ASSISTANTS[0]))
        self.assertEqual(w.record_result_handoff(self.root, self.receive())[0]["result"], "recorded")


class GoalReviewPlanTests(unittest.TestCase):
    write = qa_existing.ExactRuntimeQA.write
    dispatch = qa_existing.ExactRuntimeQA.dispatch
    receipt = qa_existing.ExactRuntimeQA.receipt
    routing_decision = qa_existing.ExactRuntimeQA.routing_decision

    def setUp(self):
        qa_existing.ExactRuntimeQA.setUp(self)
        self.addCleanup(self.temp_dir.cleanup)
        configure(self.root)
        self.snapshot = w.read_json(w.snapshot_path(self.root, self.task_id))
        self.snapshot["goal_delivery"] = goal(ASSISTANTS[1])
        self.snapshot["goal_delivery"]["authorization_pin"] = w.file_digest(self.root, "reports/synthetic-owner-message.json")
        self.snapshot["departments"] = [{"department": role, "chat_task_id": "fixed-" + role}
                                         for role in ("content-organic-website", ASSISTANTS[1])]
        w.atomic_write_json(w.snapshot_path(self.root, self.task_id), self.snapshot)
        self.plan.update(reviewer_department=ASSISTANTS[1], reviewer_thread_id="fixed-" + ASSISTANTS[1])

    def test_assigned_assistant_binds_one_frozen_plan(self):
        self.write(self.plan_path, self.plan)
        bound = review.bind_plan(self.root, task_id=self.task_id, plan_path=self.plan_path, coordinator_role=ASSISTANTS[1])
        self.assertEqual(bound["reviewer_department"], ASSISTANTS[1]); self.assertFalse(bound["production_write_allowed"])
        self.assertEqual(review.reviewer_department(self.root, w.read_json(w.snapshot_path(self.root, self.task_id))), ASSISTANTS[1])

    def test_assistant_controller_exact_binding_and_busy_hq_do_not_add_second_review(self):
        self.plan.update(controller_department=ASSISTANTS[1], controller_thread_id="fixed-" + ASSISTANTS[1])
        registry = w.read_json(self.root / "data/department-registry.json")
        next(r for r in registry["departments"] if r["id"] == "operations")["chat_binding"]["last_health_check_at"] = "2020-01-01T00:00:00+00:00"
        w.atomic_write_json(self.root / "data/department-registry.json", registry)
        self.write(self.plan_path, self.plan)
        result = review.bind_plan(self.root, task_id=self.task_id, plan_path=self.plan_path, coordinator_role=ASSISTANTS[1])
        self.assertEqual(result["result"], "recorded")
        with self.assertRaisesRegex(w.WorkflowError, "exact fixed"):
            review.validate_plan(self.root, self.snapshot, {**self.plan, "controller_thread_id": "other-assistant-thread"})

    def test_assistant_keeps_ops_audit_source_without_waiting_hq_health(self):
        registry = w.read_json(self.root / "data/department-registry.json")
        next(r for r in registry["departments"] if r["id"] == "operations")["chat_binding"]["reply_health"] = "unhealthy_no_visible_reply"
        w.atomic_write_json(self.root / "data/department-registry.json", registry)
        self.write(self.plan_path, self.plan)
        self.assertEqual(review.bind_plan(self.root, task_id=self.task_id, plan_path=self.plan_path,
                                          coordinator_role=ASSISTANTS[1])["result"], "recorded")

    def test_production_result_review_does_not_grant_new_permission(self):
        self.plan.update(risk_level="R2", action_class="site_code_candidate", scope="flashcast.com.my:exact-result")
        self.snapshot["owner_approval_required"] = True
        review.validate_plan(self.root, self.snapshot, self.plan)
        for flag in ("production_write_allowed", "external_permission_issued"):
            with self.subTest(flag=flag), self.assertRaises(w.WorkflowError):
                review.validate_plan(self.root, self.snapshot, {**self.plan, flag: True})

    def test_reviewer_is_unique_assigned_capable_and_not_a_producer(self):
        for changes in ({"reviewer_department": ASSISTANTS[0]}, {"reviewer_department": "qa-technical"}):
            with self.subTest(changes=changes), self.assertRaises(w.WorkflowError):
                review.validate_plan(self.root, self.snapshot, {**self.plan, **changes})
        self.snapshot["goal_delivery"]["producer_departments"].append(ASSISTANTS[1])
        with self.assertRaisesRegex(w.WorkflowError, "self review"):
            review.validate_plan(self.root, self.snapshot, self.plan)

    def test_fixed_qa_does_not_return_to_new_planned_route(self):
        self.snapshot["departments"].append({"department": "qa", "chat_task_id": "fixed-qa"})
        with self.assertRaises(w.WorkflowError): review.validate_plan(self.root, self.snapshot, self.plan)

    def test_new_verdict_requires_exact_frozen_identity(self):
        with self.assertRaisesRegex(w.WorkflowError, "frozen review plan"):
            review.validate_verdict(self.root, self.snapshot, [], {"department": ASSISTANTS[1]})

    def review_receipts(self):
        self.plan.update(risk_level="R2", action_class="site_code_candidate", scope="flashcast.com.my:exact-result")
        self.write(self.plan_path, self.plan)
        review.bind_plan(self.root, task_id=self.task_id, plan_path=self.plan_path, coordinator_role=ASSISTANTS[1])
        self.snapshot = w.read_json(w.snapshot_path(self.root, self.task_id))
        reviewer = ASSISTANTS[1]
        producer_path = "logs/department-outbox/goal-producer.json"
        producer = qa_existing.ExactRuntimeQA.box(self, "content-organic-website")
        self.write(producer_path, producer)
        producer_pin = w.file_digest(self.root, producer_path)
        box = qa_existing.ExactRuntimeQA.box(self, reviewer)
        box.update(risk_level="R2", review_identity={k: self.plan[k] for k in review.IDENTITY}, qa_verdict="pass")
        task_goal = self.snapshot["goal_delivery"]
        box["goal_acceptance"] = {**{k: task_goal[k] for k in ("completion_criteria", "primary_owner", "responsible_assistant")},
                                  "accepted_scope": task_goal["authorized_scope"], "remaining_scope": [],
                                  "producer_results": {"content-organic-website": producer_pin}}
        path = "logs/department-outbox/goal-reviewer.json"; self.write(path, box)
        pin = w.file_digest(self.root, path)
        stamp = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=1)).isoformat()
        dispatch = {"receipt_type": "dispatch_sent", "department": reviewer, "chat_task_id": "fixed-" + reviewer,
                    "scope": self.plan["scope"], "evidence": [self.snapshot["qa_review_plan"]["pin"], self.pin], "created_at": stamp}
        ack = {"receipt_type": "chat_ack", "department": reviewer, "chat_task_id": "fixed-" + reviewer,
               "ack_nonempty": True, "created_at": stamp}
        outbox = {"receipt_type": "outbox_received", "department": reviewer, "evidence": [pin], "created_at": stamp}
        producer_receipt = {"receipt_type": "outbox_received", "department": "content-organic-website",
                            "evidence": [producer_pin], "created_at": stamp}
        producer_dispatch = {"receipt_type": "dispatch_sent", "department": "content-organic-website",
                             "chat_task_id": "fixed-content-organic-website", "created_at": stamp}
        producer_ack = {"receipt_type": "chat_ack", "department": "content-organic-website",
                        "chat_task_id": "fixed-content-organic-website", "ack_nonempty": True, "created_at": stamp}
        verdict = {"receipt_type": "qa_verdict", "department": reviewer, "chat_task_id": "fixed-" + reviewer,
                   "evidence": [pin], "verdict": "pass", "created_at": stamp,
                   **{k: self.plan[k] for k in ("task_id", "action_id", "action_class", "scope")}}
        return [producer_dispatch, producer_ack, producer_receipt, dispatch, ack, outbox], verdict, path, box

    def test_complete_production_result_verdict_accepts_only_one_assistant(self):
        receipts, verdict, _, _ = self.review_receipts()
        review.validate_verdict(self.root, self.snapshot, receipts, verdict)
        with self.assertRaisesRegex(w.WorkflowError, "single-reviewer"):
            review.validate_verdict(self.root, self.snapshot, receipts, {**verdict, "department": ASSISTANTS[0]})

    def test_new_verdict_rejects_missing_actual_ack_or_changed_outbox(self):
        receipts, verdict, path, box = self.review_receipts()
        with self.assertRaisesRegex(w.WorkflowError, "ACK"):
            review.validate_verdict(self.root, self.snapshot, [r for r in receipts if r["receipt_type"] != "chat_ack"], verdict)
        box["external_permission_issued"] = True; self.write(path, box)
        with self.assertRaisesRegex(w.WorkflowError, "outbox bytes"):
            review.validate_verdict(self.root, self.snapshot, receipts, verdict)

    def changed_acceptance(self, changes, *, verdict_value="pass"):
        receipts, verdict, path, box = self.review_receipts()
        box["goal_acceptance"].update(changes); box["qa_verdict"] = verdict_value; self.write(path, box)
        pin = w.file_digest(self.root, path)
        receipts[-1]["evidence"] = [pin]; verdict.update(evidence=[pin], verdict=verdict_value)
        return receipts, verdict

    def test_goal_verdict_rejects_partial_pass_and_changed_completion_criteria(self):
        for changes in ({"accepted_scope": []}, {"completion_criteria": ["one child result passed"]},
                        {"responsible_assistant": ASSISTANTS[0]}, {"remaining_scope": ["unfinished action"]}):
            with self.subTest(changes=changes):
                receipts, verdict = self.changed_acceptance(changes)
                with self.assertRaisesRegex(w.WorkflowError, "goal|full exact"):
                    review.validate_verdict(self.root, self.snapshot, receipts, verdict)

    def test_goal_verdict_rejects_missing_other_producer_and_old_pin(self):
        receipts, verdict, path, box = self.review_receipts()
        self.snapshot["goal_delivery"]["producer_departments"].append("paid-growth-data")
        w.atomic_write_json(w.snapshot_path(self.root, self.task_id), self.snapshot)
        with self.assertRaisesRegex(w.WorkflowError, "every producer"):
            review.validate_verdict(self.root, self.snapshot, receipts, verdict)
        self.snapshot["goal_delivery"]["producer_departments"].pop()
        w.atomic_write_json(w.snapshot_path(self.root, self.task_id), self.snapshot)
        old = box["goal_acceptance"]["producer_results"]["content-organic-website"]
        box["goal_acceptance"]["producer_results"]["content-organic-website"] = {**old, "sha256": "f" * 64}
        self.write(path, box); pin = w.file_digest(self.root, path)
        receipts[-1]["evidence"] = [pin]; verdict["evidence"] = [pin]
        with self.assertRaisesRegex(w.WorkflowError, "current result bytes"):
            review.validate_verdict(self.root, self.snapshot, receipts, verdict)

    def test_goal_blocked_verdict_requires_accurate_remaining_and_does_not_pass_partial_scope(self):
        receipts, verdict = self.changed_acceptance({"accepted_scope": [], "remaining_scope": ["fix exact internal behavior"]}, verdict_value="blocked")
        review.validate_verdict(self.root, self.snapshot, receipts, verdict)
        receipts, verdict = self.changed_acceptance({"remaining_scope": []}, verdict_value="blocked")
        with self.assertRaisesRegex(w.WorkflowError, "blocked must state"):
            review.validate_verdict(self.root, self.snapshot, receipts, verdict)

    def test_candidate_drift_is_rejected(self):
        self.write(self.candidate, {"task_id": self.task_id, "candidate_version": "changed", "department": "content-organic-website"})
        with self.assertRaisesRegex(w.WorkflowError, "candidate file pin"):
            review.validate_plan(self.root, self.snapshot, self.plan)

    def prepare_transfer(self, **changes):
        self.write(self.plan_path, self.plan)
        review.bind_plan(self.root, task_id=self.task_id, plan_path=self.plan_path, coordinator_role=ASSISTANTS[1])
        new = {**self.plan, "reviewer_department": ASSISTANTS[0], "reviewer_thread_id": "fixed-" + ASSISTANTS[0], **changes}
        path = "drafts/operations/reviewer-transfer-plan.json"; self.write(path, new)
        return path

    def test_transfer_plan_prepares_same_candidate_and_preserves_old_binding(self):
        path = self.prepare_transfer()
        before = w.read_json(w.snapshot_path(self.root, self.task_id))
        packet = review.transfer_plan(self.root, task_id=self.task_id, plan_path=path, target_role=ASSISTANTS[0], prepare_only=True)
        self.assertEqual(packet["previous_binding"], before["qa_review_plan"])
        self.assertEqual(packet["candidate"], self.pin)
        self.assertFalse(packet["old_verdict_migrated"])
        self.assertEqual(w.read_json(w.snapshot_path(self.root, self.task_id)), before)

    def test_transfer_plan_rejects_candidate_change_and_completed_verdict(self):
        path = self.prepare_transfer(candidate_version="v2")
        with self.assertRaisesRegex(w.WorkflowError, "retain exact candidate"):
            review.transfer_plan(self.root, task_id=self.task_id, plan_path=path, target_role=ASSISTANTS[0], prepare_only=True)
        self.write(path, {**self.plan, "reviewer_department": ASSISTANTS[0], "reviewer_thread_id": "fixed-" + ASSISTANTS[0]})
        with mock.patch.object(w, "_validate_receipt_chain", return_value=([{"receipt_type": "qa_verdict", "verdict": "pass"}], [])):
            with self.assertRaisesRegex(w.WorkflowError, "verdict cannot be moved"):
                review.transfer_plan(self.root, task_id=self.task_id, plan_path=path, target_role=ASSISTANTS[0], prepare_only=True)

    def test_no_goal_keeps_legacy_exact_qa_plan_readable(self):
        self.snapshot.pop("goal_delivery")
        self.snapshot["departments"][-1] = {"department": "qa-technical", "chat_task_id": "fixed-qa-technical"}
        self.plan.update(reviewer_department="qa-technical", reviewer_thread_id="fixed-qa-technical")
        review.validate_plan(self.root, self.snapshot, self.plan)
        with self.assertRaisesRegex(w.WorkflowError, "fixed qa"):
            review.validate_verdict(self.root, self.snapshot, [], {"department": ASSISTANTS[1]})


if __name__ == "__main__":
    unittest.main()
