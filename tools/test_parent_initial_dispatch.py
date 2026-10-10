"""Synthetic project-owned real workflow/SQL tests; no native messages sent."""
import copy
import datetime as dt
import json
from pathlib import Path
import time
import unittest
from unittest import mock

import goal_delivery_runtime as g
import parent_initial_dispatch as initial
import qa_review_plan as review
import result_coordination as c
import test_goal_runtime_consumers as existing
import workflow_control as w
import flashcast_ops as ops

ASSISTANT = "operations-assistant-2"
PRODUCER = "system-development"
SCOPE = "project:flashcast:parent-initial-test:v1"


class ParentInitialDispatchTests(unittest.TestCase):
    def setUp(self):
        # Reuse the existing owned isolation and real complete-goal consumers.
        patcher = mock.patch.object(existing, "PRODUCER", PRODUCER)
        patcher.start(); self.addCleanup(patcher.stop)
        self.consumer = existing.GoalRuntimeConsumerTests("runTest")
        self.consumer.setUp(); self.addCleanup(self.consumer.doCleanups)
        self.root = self.consumer.root
        self.fixture = self.consumer.fixture
        registry = w.read_json(self.root / "data/department-registry.json")
        template = copy.deepcopy(next(row for row in registry["departments"] if row["id"] == "content-organic-website"))
        template.update(id=PRODUCER, name=PRODUCER, mode="worker", new_dispatch_enabled=True)
        template["chat_binding"].update(task_id="fixed-" + PRODUCER, title=PRODUCER)
        registry["departments"].append(template)
        w.atomic_write_json(self.root / "data/department-registry.json", registry)
        self.parent_id = self.consumer.task_id
        self.child_id = "parent-initial-child-001"
        auth = {**existing.claims.goal(ASSISTANT)["human_authorization"], "executor": PRODUCER, "scope": SCOPE}
        self.consumer.initialize(primary_owner=PRODUCER, producer_departments=[PRODUCER],
                                 authorized_scope=[SCOPE], human_authorization=auth)
        self.consumer.initial_assignment()
        parent_action = self.consumer.requested(sender="operations", target=PRODUCER, scope=SCOPE)
        parent_policy = self.consumer.policy(parent_action)
        self.assertEqual(parent_policy["status"], "allow", parent_policy.get("reason"))
        self.fixture.receipt("dispatch_sent", PRODUCER, "parent-producer-dispatch",
            policy_decision_id=parent_policy["decision_id"], action_id=parent_action["action_id"],
            action_class="thread_message", scope=SCOPE)
        self.fixture.receipt("chat_ack", PRODUCER, "parent-producer-ack")
        candidate, self.producer_pin = self.consumer.producer_result()
        plan = self.consumer.review_plan(candidate)
        plan_path = self.consumer.write("drafts/operations/parent-plan.json", plan)
        review.bind_plan(self.root, task_id=self.parent_id, plan_path=plan_path, coordinator_role=ASSISTANT)
        self.consumer.write("tools/synthetic-internal-control.py", {"fixture_only": True})
        self.source_pin = w.file_digest(self.root, "tools/synthetic-internal-control.py")
        self.manifest_path = self.consumer.write("reports/synthetic-adopted-manifest.json", {
            "task_id": self.parent_id, "external_writes": False, "candidate_fingerprint": "synthetic-fingerprint",
            "changes": [{"path": self.source_pin["path"]}]})
        self.manifest_pin = w.file_digest(self.root, self.manifest_path)
        binding = self.consumer.snapshot()["qa_review_plan"]
        verdict = self.consumer.assistant_verdict(plan, self.producer_pin,
            evidence=[binding["pin"], plan["candidate"], self.manifest_pin])
        qa_path = "logs/department-outbox/goal-reviewer-v1.json"
        self.applied_path = self.consumer.write("reports/synthetic-applied-proof.json", {
            "task_id": self.parent_id, "candidate_version": "v1", "external_writes": 0,
            "no_external_permission_issued": True, "postapply_tests": {"run": 1, "failures": 0, "errors": 0},
            "qa_outbox": w.file_digest(self.root, qa_path), "candidate_manifest": self.manifest_pin,
            "candidate_fingerprint": "synthetic-fingerprint", "applied_files": [self.source_pin]})
        self.adoption = {"control_qa_outbox_path": qa_path, "control_applied_proof": self.applied_path,
                         "control_qa_receipt_id": verdict["receipt_id"]}
        # This invokes the real independent QA/current applied-source verifier.
        w._verify_operations_rework_completion(self.root, self.adoption, self.parent_id)
        registry = w.read_json(self.root / "data/department-registry.json")
        next(row for row in registry["departments"] if row["id"] == PRODUCER)["mode"] = "coordinator"
        w.atomic_write_json(self.root / "data/department-registry.json", registry)
        child = copy.deepcopy(self.consumer.snapshot()["goal_delivery"])
        child.update(parent_task_id=self.parent_id, initial_dispatch_mode="read_only",
                     objective="Synthetic local read-only next child", completion_criteria=["read-only evidence returned"])
        child.pop("approved_actions", None)
        self.child_path = self.consumer.write("drafts/operations/child-contract.json", child)
        g.initialize_goal(self.root, self.child_id, self.child_path)
        child_pin = w.file_digest(self.root, self.child_path)
        parent = self.consumer.snapshot()
        message = (self.child_id + "\r\n" + self.parent_id + "\r\n" + SCOPE + "\n"
                   + child_pin["path"] + " " + child_pin["sha256"] + "\n"
                   + parent["goal_delivery"]["authorization_pin"]["path"] + " "
                   + parent["goal_delivery"]["authorization_pin"]["sha256"] + "\n只读检查，禁止实际写入。")
        path = "drafts/operations/first-child-message.txt"
        w.safe_path(self.root, path).write_bytes(message.encode("utf-8"))
        action = self.consumer.requested(sender=ASSISTANT, target=PRODUCER, scope=SCOPE,
                                        payload=w.file_digest(self.root, path))
        action.update(task_id=self.child_id, parent_task_id=self.parent_id, action_id="first-read-only-child")
        self.proof = {"schema_version": 1, "mode": "read_only", "child_contract": child_pin, "action": action,
                      "adoption": self.adoption, "attempt_path": "logs/goal-initial-dispatch/" + self.child_id + "/attempt.json",
                      "native_send_receipt_path": "logs/goal-initial-dispatch/" + self.child_id + "/native.json"}
        self.base = {"task_id": self.parent_id, "sender_department": PRODUCER, "candidate_version": "v1",
                     "result_sha256": self.producer_pin["sha256"], "outbox_path": self.producer_pin["path"]}
        final_path = "reports/synthetic-parent-final.txt"
        w.safe_path(self.root, final_path).write_bytes((self.parent_id + " 合成 fixture 完成。\n").encode("utf-8"))
        final_pin = w.file_digest(self.root, final_path)
        self.consumer.write("reports/synthetic-parent-native.json", {
            "thread": {"id": "fixed-" + PRODUCER}, "turn_id": "synthetic-parent-final-turn",
            "status": "completed", "error": None, "completedAt": dt.datetime.now(dt.timezone.utc).timestamp(),
            "message": {"id": "synthetic-parent-final-message", "turnId": "synthetic-parent-final-turn",
                        "phase": "final_answer", "text": w.safe_path(self.root, final_path).read_text()}})
        completed = {"source_thread_id": "fixed-" + PRODUCER, "source_turn_id": "synthetic-parent-final-turn",
                     "source_reply_sha256": final_pin["sha256"], "visible_reply": final_pin,
                     "actual_native_completion": w.file_digest(self.root, "reports/synthetic-parent-native.json"),
                     "reply_observed_at": dt.datetime.now(dt.timezone.utc).isoformat()}
        w.record_result_handoff(self.root, {**self.base, **completed,
                                           "event": "notification_queued", "idempotency_key": "parent-queue"})
        self.store = c.CoordinationStore(self.root); self.addCleanup(self.store.close)
        self.lease = self.store.claim(self.base, ASSISTANT, "synthetic-original-a2", "fixture-claim")
        self.authority = {"coordinator_role": ASSISTANT, "coordinator_owner": "synthetic-original-a2",
                          "coordination_claim": self.lease}
        self.intake, _ = w.record_result_handoff(self.root, {**self.base, **self.authority, **completed,
            "event": "controller_received", "idempotency_key": "parent-intake", "intake_mode": "queue",
            "reply_observed_at": dt.datetime.now(dt.timezone.utc).isoformat()})
        evidence = [self.proof["child_contract"], action["payload"], parent["goal_contract"],
                    parent["goal_delivery"]["authorization_pin"], w.file_digest(self.root, qa_path),
                    w.file_digest(self.root, self.applied_path)]
        self.decision_request = {**self.base, **self.authority, "event": "controller_decision",
            "idempotency_key": "parent-next-decision", "decision": "continue", "next_owner": PRODUCER,
            "next_action": "send exact read-only child once", "next_task_id": self.child_id,
            "next_action_id": action["action_id"], "next_scope": SCOPE, "initial_dispatch": self.proof,
            "evidence_paths": [pin["path"] for pin in evidence]}
        self.decision, _ = w.record_result_handoff(self.root, self.decision_request)
        self.action = {**action, "decision_record_id": self.decision["record_id"], "parent_initial_dispatch": self.proof}

    def snapshot(self):
        return w.read_json(w.snapshot_path(self.root, self.child_id))

    def approve(self, **changes):
        action = {**self.action, **changes}
        path = self.consumer.write("drafts/operations/approved-first-action.json", action)
        return g.record_approved_action(self.root, self.child_id, path)

    def policy(self):
        request = {key: self.action[key] for key in initial.ACTION_FIELDS
                   if key not in {"payload", "parent_task_id", "sender_department"}}
        return w.policy_check(self.root, department=ASSISTANT, **request)[0]

    def begin(self):
        self.approve()
        self.routing = self.policy()
        self.assertEqual(self.routing["status"], "allow", self.routing.get("reason"))
        self.begin_path = self.consumer.write("drafts/operations/begin-first.json", {
            "task_id": self.child_id, "action_id": self.action["action_id"], "policy_decision_id": self.routing["decision_id"]})
        return initial.begin(self.root, self.begin_path)

    def sent(self, mode="send", **changes):
        attempted = w.read_json(w.safe_path(self.root, self.proof["attempt_path"]))
        native = {"tool": initial.TOOL, "arguments": attempted["arguments"],
                  "attempt_id": attempted["attempt_id"], "observed_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                  "actual_native_send": {"isError": False, "content": [
                      {"type": "text", "text": json.dumps({"threadId": self.action["target_thread_id"]})}]}}
        if mode == "readback":
            native.pop("actual_native_send")
            native.update(proof_mode="readback", tool="mcp__codex_app__read_thread",
                          arguments={"threadId": self.action["target_thread_id"]}, actual_native_readback={
                              "isError": False, "content": [{"type": "text", "text": json.dumps({
                                  "thread": {"id": self.action["target_thread_id"]}, "turns": [{
                                      "id": "synthetic-original-native-turn",
                                      "startedAt": int(dt.datetime.now(dt.timezone.utc).timestamp()), "items": [{
                                          "type": "userMessage", "id": "synthetic-original-user-message",
                                          "content": [{"type": "text", "text": attempted["arguments"]["prompt"]}]}]}]})}]})
        native.update(changes)
        self.consumer.write(self.proof["native_send_receipt_path"], native)
        self.fixture.task_id = self.child_id
        return self.fixture.receipt("dispatch_sent", PRODUCER, "first-actual-send-receipt",
            policy_decision_id=self.routing["decision_id"], action_id=self.action["action_id"],
            action_class="thread_message", scope=SCOPE,
            evidence=self.proof["attempt_path"] + ";" + self.proof["native_send_receipt_path"])

    def test_real_parent_freeze_approved_policy_reserved_native_receipt_once(self):
        self.assertEqual(self.decision["initial_dispatch"], self.proof)
        result = self.begin()
        self.assertFalse(result["actual_message_sent"])
        self.assertEqual(result["arguments"]["prompt"].encode("utf-8"),
                         w.safe_path(self.root, self.action["payload"]["path"]).read_bytes())
        self.assertNotIn("token", json.dumps(result))
        receipt = self.sent()
        self.assertTrue(receipt["parent_initial_dispatch"]["actual_message_sent"])
        self.assertFalse(receipt["parent_initial_dispatch"]["external_permission_issued"])
        self.assertEqual(w._validate_receipt_chain(self.root, self.child_id)[1], [])
        self.assertEqual(w.validate_workflow_events(self.root, self.child_id), [])

    def test_exact_initial_child_ack_result_followthrough_and_wrong_next_tuple(self):
        self.begin()
        dispatch = self.sent()
        self.fixture.receipt("chat_ack", PRODUCER, "exact-child-ack")
        candidate_path = self.consumer.write("reports/exact-child-candidate.json", {
            "task_id": self.child_id, "parent_task_id": self.parent_id,
            "department": PRODUCER, "candidate_version": "child-read-only-v1", "fixture_only": True})
        box = self.consumer.result_box(PRODUCER, "child-read-only-v1", w.file_digest(self.root, candidate_path))
        box.update(task_id=self.child_id, parent_task_id=self.parent_id)
        outbox_path = self.consumer.write("logs/department-outbox/exact-child-result.json", box)
        received = self.fixture.receipt("outbox_received", PRODUCER, "exact-child-result", evidence=outbox_path)
        request = {**self.base, **self.authority, "event": "controller_followthrough",
                   "idempotency_key": "exact-child-subsequent-proof", "followthrough_status": "subsequent_action_verified",
                   "linked_task_id": self.child_id, "action_receipt_id": received["receipt_id"],
                   "linked_dispatch_receipt_id": dispatch["receipt_id"], "linked_outbox_path": outbox_path,
                   "evidence_paths": [outbox_path]}
        linked_record = {**request, "linked_outbox": w.file_digest(self.root, outbox_path)}
        for field, value in (("next_task_id", "wrong-complete-child"), ("next_action_id", "wrong-action"),
                             ("next_scope", "project:flashcast:wrong-scope"), ("record_id", "wrong-decision")):
            with self.subTest(field=field), self.assertRaisesRegex(w.WorkflowError, "exact child/action/scope/decision"):
                w._verify_inflight_followthrough(self.root, linked_record, {**self.decision, field: value})
        result, _ = w.record_result_handoff(self.root, request)
        self.assertTrue(result["dispatch_after_decision"])
        self.assertFalse(result["business_goal_closed"])
        self.assertEqual(w.record_result_handoff(self.root, request)[0]["result"], "duplicate_ignored")

    def test_legacy_parent_decision_with_no_exact_next_fields_stays_unchanged(self):
        request = {key: value for key, value in self.decision_request.items() if key not in initial.NEXT_FIELDS}
        self.assertEqual(initial.freeze_next(self.root, self.consumer.snapshot(), request, []), {})

    def test_partial_next_fields_and_changed_child_parent_rejected(self):
        with self.assertRaisesRegex(w.WorkflowError, "declared together"):
            initial.freeze_next(self.root, self.consumer.snapshot(), {"next_task_id": self.child_id}, [])
        self.assert_rejected_action(parent_task_id="wrong-parent-task")

    def assert_rejected_action(self, **changes):
        before = self.snapshot()["goal_delivery"].get("approved_actions", [])
        with self.assertRaises(w.WorkflowError):
            self.approve(**changes)
        self.assertEqual(self.snapshot()["goal_delivery"].get("approved_actions", []), before)

    def test_wrong_actor_original_producer_and_scope_rejected(self):
        for changes in ({"sender_department": "operations"}, {"target_department": "content-organic-website"},
                        {"scope": "project:flashcast:other-scope"}, {"action_class": "site_publish"}):
            with self.subTest(changes=changes):
                self.assert_rejected_action(**changes)

    def test_changed_original_human_and_contract_bytes_rejected(self):
        self.root.joinpath(self.proof["child_contract"]["path"]).write_bytes(b"{}")
        self.assert_rejected_action()

    def test_not_actually_adopted_and_drifted_applied_source_rejected(self):
        self.root.joinpath(self.source_pin["path"]).write_text("changed source")
        self.assert_rejected_action()

    def test_stale_or_foreign_current_fence_rejected_before_native_attempt(self):
        self.store.release(self.base, ASSISTANT, self.lease["owner"], self.lease, "synthetic interruption")
        self.assert_rejected_action()
        self.assertFalse(w.safe_path(self.root, self.proof["attempt_path"]).exists())

    def test_committed_decision_native_and_audit_payload_tamper_rejected(self):
        self.store.conn.execute("UPDATE reservations SET native_record_json='{}' WHERE effect_key=?",
                                (c._sha(["controller_decision", "parent-next-decision"]),))
        self.assert_rejected_action()

    def test_duplicate_uncertain_begin_and_policy_rejected(self):
        self.begin()
        with self.assertRaisesRegex(w.WorkflowError, "uncertain"):
            initial.begin(self.root, self.begin_path)
        self.assertEqual(self.policy()["status"], "deny")
        self.assertEqual(w.read_jsonl(w.receipts_path(self.root, self.child_id)), [])

    def test_child_wide_uncertain_marker_blocks_changed_action_and_paths(self):
        # A prior call marker at another action/path still blocks this otherwise
        # fully proven original action, not only an exact attempt_path collision.
        marker = "logs/goal-initial-dispatch/" + self.child_id + "/another-action-attempt.json"
        self.consumer.write(marker, {"state": "called_no_response", "action_id": "previous-action"})
        with self.assertRaisesRegex(w.WorkflowError, "uncertain"):
            self.approve()
        self.assertFalse(w.safe_path(self.root, self.proof["attempt_path"]).exists())

    def test_changed_audit_hash_and_missing_actual_allow_policy_rejected(self):
        self.approve()
        path = self.consumer.write("drafts/operations/no-policy-begin.json", {
            "task_id": self.child_id, "action_id": self.action["action_id"], "policy_decision_id": "invented-allow"})
        with self.assertRaisesRegex(w.WorkflowError, "actual exact allow"):
            initial.begin(self.root, path)
        self.store.conn.execute("UPDATE coordination_audit SET record_hash='changed' WHERE seq=(SELECT MAX(seq) FROM coordination_audit)")
        with self.assertRaisesRegex(w.WorkflowError, "audit hash"):
            initial.validate_action(self.root, self.snapshot(), self.action)
        self.assertFalse(w.safe_path(self.root, self.proof["attempt_path"]).exists())

    def test_readback_without_actual_user_body_remains_uncertain(self):
        self.begin()
        response = {"isError": False, "content": [{"type": "text", "text": json.dumps({
            "thread": {"id": self.action["target_thread_id"]}, "turns": [{"id": "native-turn",
                "startedAt": int(dt.datetime.now(dt.timezone.utc).timestamp()), "items": [
                    {"type": "functionCallOutput", "id": "opaque-provider-output"}]}]})}]}
        with self.assertRaisesRegex((w.WorkflowError, ops.OpsError), "positive native readback"):
            self.sent(mode="readback", actual_native_readback=response)
        self.assertEqual(w.read_jsonl(w.receipts_path(self.root, self.child_id)), [])
        with self.assertRaisesRegex(w.WorkflowError, "uncertain"):
            initial.begin(self.root, self.begin_path)

    def test_read_only_container_rejects_undeclared_permission_fields(self):
        proof = {**self.proof, "production_write_allowed": True}
        self.assert_rejected_action(parent_initial_dispatch=proof)

    def test_before_call_attempt_pin_cannot_be_rewritten(self):
        self.begin()
        path = w.safe_path(self.root, self.proof["attempt_path"])
        path.write_bytes(path.read_bytes() + b"\n")
        with self.assertRaisesRegex((w.WorkflowError, ops.OpsError), "hash-chained"):
            self.sent()

    def test_positive_native_readback_settles_original_without_new_begin(self):
        self.begin()
        self.store.release(self.base, ASSISTANT, self.lease["owner"], self.lease, "native response absent")
        registry = w.read_json(self.root / "data/department-registry.json")
        for row in registry["departments"]:
            row["chat_binding"]["last_health_check_at"] = "2000-01-01T00:00:00+00:00"
        w.atomic_write_json(self.root / "data/department-registry.json", registry)
        # The real read-thread API exposes whole-second startedAt. A same-second
        # observation cannot prove it followed a subsecond attempt reservation.
        time.sleep(1.05)
        result = self.sent(mode="readback")
        self.assertEqual(result["parent_initial_dispatch"]["proof_mode"], "readback")
        with self.assertRaises(w.WorkflowError):
            initial.begin(self.root, self.begin_path)

    def test_native_wrong_tool_args_target_or_error_rejected(self):
        self.begin()
        for changes in ({"tool": "mcp__codex_app__list_threads"}, {"arguments": {"threadId": "other", "prompt": "changed"}},
                        {"actual_native_send": {"isError": True, "content": []}}):
            with self.subTest(changes=changes), self.assertRaises((w.WorkflowError, ops.OpsError)):
                self.sent(**changes)

    def test_missing_receipt_action_id_cannot_bypass_original_action_proof(self):
        self.begin()
        self.fixture.task_id = self.child_id
        with self.assertRaisesRegex((w.WorkflowError, ops.OpsError), "missing fields"):
            self.fixture.receipt("dispatch_sent", PRODUCER, "omitted-action-id",
                                 policy_decision_id=self.routing["decision_id"], action_class="thread_message", scope=SCOPE)


if __name__ == "__main__":
    unittest.main()
