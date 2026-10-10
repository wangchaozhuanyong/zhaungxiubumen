"""Synthetic local sources through real binding/verdict entry points; no sends."""
import copy
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import unittest
from unittest import mock

import goal_delivery_runtime as g
import qa_review_plan as review
import test_goal_runtime_consumers as existing
import workflow_control as w

A2, PRODUCER = "operations-assistant-2", "system-development"
TO = "fc-20261010-system-development-onboarding-v1"
F4 = "fc-20261010-system-flow-throughput-and-ledger-close-v1"
SCOPES = {TO: "project:flashcast:department-system-development-onboarding:v1",
          F4: "project:flashcast:system-flow-throughput-ledger-cleanup:v1"}


class NativeMultiGoalReviewTests(unittest.TestCase):
    def setUp(self):
        area = Path(os.environ.get("NATIVE_MULTI_GOAL_TEST_OUTPUT", str(Path(__file__).resolve().parents[1] / ".test-tmp")))
        area.mkdir(parents=True, exist_ok=True)
        patches = [mock.patch.object(existing, "PRODUCER", PRODUCER), mock.patch.object(existing, "TMP", area)]
        for patch in patches:
            patch.start(); self.addCleanup(patch.stop)
        self.consumer = existing.GoalRuntimeConsumerTests("runTest")
        self.consumer.setUp(); self.addCleanup(self.consumer.doCleanups)
        self.root, self.fixture = self.consumer.root, self.consumer.fixture
        registry = w.read_json(self.root / "data/department-registry.json")
        row = copy.deepcopy(next(row for row in registry["departments"] if row["id"] == "content-organic-website"))
        row.update(id=PRODUCER, name=PRODUCER, mode="worker", new_dispatch_enabled=True)
        row["chat_binding"].update(task_id="fixed-" + PRODUCER, title=PRODUCER)
        registry["departments"] = [entry for entry in registry["departments"] if entry["id"] != PRODUCER]
        registry["departments"].append(row)
        w.atomic_write_json(self.root / "data/department-registry.json", registry)
        self.plans, self.producer_pins = {}, {}
        for task in (TO, F4):
            self.use(task)
            goal = self.consumer.make_goal(primary_owner=PRODUCER, producer_departments=[PRODUCER],
                authorized_scope=[SCOPES[task]], source_mode="owner_direct" if task == TO else "approved_dispatch",
                parent_task_id="fc-original-parent-v1", completion_criteria=["candidate reviewed", "actual adoption and internal trial"])
            goal["human_authorization"]["executor"] = PRODUCER
            path = self.consumer.write("drafts/operations/" + task + "/goal.json", goal)
            g.initialize_goal(self.root, task, path)
            if task == F4:
                action = self.consumer.requested(sender="operations", target=PRODUCER, scope=SCOPES[task])
                policy = self.consumer.policy(action)
                self.assertEqual(policy["status"], "allow", policy.get("reason"))
                self.fixture.receipt("dispatch_sent", PRODUCER, "producer-original-dispatch-" + task,
                    policy_decision_id=policy["decision_id"], action_id=action["action_id"],
                    action_class="thread_message", scope=SCOPES[task])
            self.fixture.receipt("chat_ack", PRODUCER, "producer-original-ack-" + task)
            candidate, producer_pin = self.consumer.producer_result(task)
            self.producer_pins[task] = producer_pin
            self.plans[task] = self.consumer.review_plan(candidate)
        self.use(TO)
        text = ("Synthetic local original multi-goal responsibility, never a platform grant.\n"
                + "1. 原 " + TO + " system-development 独立验收及复用采用。\n"
                + "4. 新完整系统 " + F4 + " system-development scope " + SCOPES[F4]
                + "，你是唯一 development 验收/采用负责人。\n")
        self.input_path = "reports/original-multi-goal-input.txt"
        (self.root / self.input_path).write_bytes(text.encode("utf-8"))
        input_pin = w.file_digest(self.root, self.input_path)
        request = self.consumer.requested(sender="operations", target=A2, scope=SCOPES[TO], payload=input_pin)
        request["action_id"] = "assign-assistant2-original-multiple-goals"
        policy = self.consumer.policy(request)
        self.assertEqual(policy["status"], "allow", policy.get("reason"))
        wrapper = "<codex_delegation>\n  <source_thread_id>fixed-operations</source_thread_id>\n  <input>" + text + "</input>\n</codex_delegation>"
        now = dt.datetime.now(dt.timezone.utc).timestamp() - 1
        native = {"schema_version": 1, "source_tool": "mcp__codex_app__read_thread",
            "actual_receiver_thread_id": "fixed-" + A2, "actual_receiver_department": A2,
            "actual_receiver_project_root": str(self.root), "source_is_actual_native_function_call_output": True,
            "no_synthetic_userMessage_or_dispatch": True, "new_production_permissions": False,
            "actual_receiving_turn": {"id": "synthetic-original-batch-turn", "status": "completed", "startedAt": now},
            "actual_function_call_output": {"type": "functionCallOutput", "id": "synthetic-original-batch-fco",
                "name": "send_message_to_thread", "namespace": "codex_app", "output": {"text": wrapper, "truncated": False}}}
        self.native_path = self.consumer.write("reports/original-multi-goal-native.json", native)
        send_path = self.consumer.write("reports/original-multi-goal-send.json", {"threadId": "fixed-" + A2})
        self.dispatch = self.fixture.receipt("dispatch_sent", A2, "original-native-batch-send",
            policy_decision_id=policy["decision_id"], action_id=request["action_id"], action_class="thread_message",
            scope=SCOPES[TO], evidence=send_path)
        self.ack_path = self.consumer.write("reports/original-multi-goal-ack.json", {"thread": {
            "id": "fixed-" + A2, "title": A2, "cwd": str(self.root)}, "turns": [{"id": "synthetic-original-batch-turn",
            "startedAt": now, "status": "completed", "items": [{"type": "functionCallOutput",
                "id": "synthetic-original-batch-fco", "name": "send_message_to_thread", "namespace": "codex_app"},
                {"type": "agentMessage", "id": "synthetic-original-batch-ack", "phase": "commentary", "text": "Fixture ACK only."}]}]})
        self.ack = self.fixture.receipt("chat_ack", A2, "original-native-batch-ack", evidence=self.ack_path)
        for task in (TO, F4):
            snapshot = w.read_json(w.snapshot_path(self.root, task))
            self.plans[task]["native_multi_goal_review"] = {"schema_version": 1, "task_id": task,
                "responsible_assistant": A2, "producer_department": PRODUCER, "scope": SCOPES[task],
                "authority": snapshot["goal_delivery"]["authorization_pin"], "goal_contract": snapshot["goal_contract"],
                "reviewer_native_responsibility": w.file_digest(self.root, self.native_path),
                "reviewer_responsibility_input": input_pin, "source_task_id": TO,
                "dispatch_receipt_id": self.dispatch["receipt_id"], "dispatch_receipt_hash": self.dispatch["receipt_hash"],
                "ack_receipt_id": self.ack["receipt_id"], "ack_receipt_hash": self.ack["receipt_hash"]}

    def use(self, task):
        self.consumer.task_id = self.fixture.task_id = task
        self.fixture.routing_decisions = {}

    def snapshot(self, task=F4):
        return w.read_json(w.snapshot_path(self.root, task))

    def prepare(self, task=F4, proof=None):
        return review.prepare_native_multi_goal_review(self.root, self.snapshot(task),
            proof or self.plans[task]["native_multi_goal_review"])

    def bind(self, task):
        self.use(task)
        path = self.consumer.write("drafts/operations/" + task + "/formal-review.json", self.plans[task])
        return review.bind_plan(self.root, task_id=task, plan_path=path, coordinator_role=A2)

    def test_actual_source_pair_recognizes_both_original_goals_without_relabelled_send(self):
        before = {task: w.receipts_path(self.root, task).read_bytes() for task in (TO, F4)}
        for task in (TO, F4):
            context = self.prepare(task)
            actual = review._assigned_review_round(self.root, self.snapshot(task),
                w.read_jsonl(w.receipts_path(self.root, task)), self.plans[task])
            self.assertIsNotNone(actual)
            self.assertEqual(actual["source_task_id"], TO)
            self.assertEqual(actual["dispatch"]["task_id"], TO)
            self.assertFalse(context["reviewer_dispatch_fabricated"])
            self.assertFalse(context["parent_goal_completed"])
        actual_dispatch = next(row for row in w.read_jsonl(w.receipts_path(self.root, TO))
                               if row.get("receipt_id") == self.dispatch["receipt_id"])
        self.assertTrue(review._initial_assignment(self.root, self.snapshot(TO), actual_dispatch,
            self.plans[TO]["native_multi_goal_review"]))
        self.assertFalse(review._initial_assignment(self.root, self.snapshot(F4), actual_dispatch,
            self.plans[F4]["native_multi_goal_review"]))
        self.assertEqual(before, {task: w.receipts_path(self.root, task).read_bytes() for task in (TO, F4)})

    def test_formal_binding_is_exact_and_duplicate_does_not_add_event_or_receipt(self):
        for task in (TO, F4):
            result = self.bind(task)
            self.assertEqual(result["result"], "recorded")
            paths = [self.root / w.WORKFLOW_EVENTS, w.receipts_path(self.root, task), w.snapshot_path(self.root, task)]
            before = {path: path.read_bytes() for path in paths}
            self.assertEqual(self.bind(task)["result"], "duplicate_ignored")
            self.assertEqual(before, {path: path.read_bytes() for path in paths})

    def test_original_TO_can_issue_real_formal_verdict_with_source_mode_unchanged(self):
        self.bind(TO)
        result = self.consumer.assistant_verdict(self.plans[TO], self.producer_pins[TO],
            native_multi_goal_review=self.plans[TO]["native_multi_goal_review"])
        self.assertEqual(result["verdict"], "pass")
        self.assertEqual(self.snapshot(TO)["goal_delivery"]["source_mode"], "owner_direct")
        self.assertEqual(w._validate_receipt_chain(self.root, TO)[1], [])

    def test_original_F4_formal_blocked_does_not_claim_whole_goal_completed(self):
        self.bind(F4)
        result = self.consumer.assistant_verdict(self.plans[F4], self.producer_pins[F4], verdict="blocked",
            native_multi_goal_review=self.plans[F4]["native_multi_goal_review"])
        self.assertEqual(result["verdict"], "blocked")
        self.assertEqual(self.snapshot(F4)["goal_delivery"]["source_mode"], "approved_dispatch")
        self.assertEqual(w._validate_receipt_chain(self.root, F4)[1], [])

    def test_wrong_goal_scope_actor_source_task_and_human_pin_are_rejected(self):
        for changes in ({"task_id": TO}, {"scope": SCOPES[TO]}, {"responsible_assistant": "operations-assistant-3"},
                        {"producer_department": A2}, {"source_task_id": "fc-unrelated-goal"},
                        {"authority": self.plans[TO]["native_multi_goal_review"]["goal_contract"]}):
            with self.subTest(changes=changes), self.assertRaises(w.WorkflowError):
                self.prepare(proof={**self.plans[F4]["native_multi_goal_review"], **changes})

    def test_original_fco_or_turn_forgery_rejected_even_when_rehashed(self):
        path = self.root / self.native_path; original = path.read_bytes()
        for mutate in (lambda value: value["actual_function_call_output"].update(id="forged-fco"),
                       lambda value: value["actual_receiving_turn"].update(id="forged-turn"),
                       lambda value: value.update(actual_receiver_department="operations-assistant-3")):
            path.write_bytes(original); value = json.loads(original); mutate(value); w.atomic_write_json(path, value)
            proof = {**self.plans[F4]["native_multi_goal_review"], "reviewer_native_responsibility": w.file_digest(self.root, self.native_path)}
            with self.assertRaises(w.WorkflowError): self.prepare(proof=proof)
        path.write_bytes(original)

    def test_message_forgery_rejected_by_original_policy_even_if_native_and_input_rehashed(self):
        value = w.read_json(self.root / self.native_path)
        text = (self.root / self.input_path).read_text() + "changed source bytes\n"
        (self.root / self.input_path).write_bytes(text.encode())
        value["actual_function_call_output"]["output"]["text"] = "<codex_delegation>\n  <source_thread_id>fixed-operations</source_thread_id>\n  <input>" + text + "</input>\n</codex_delegation>"
        w.atomic_write_json(self.root / self.native_path, value)
        proof = {**self.plans[F4]["native_multi_goal_review"],
            "reviewer_native_responsibility": w.file_digest(self.root, self.native_path),
            "reviewer_responsibility_input": w.file_digest(self.root, self.input_path)}
        with self.assertRaisesRegex(w.WorkflowError, "policy bytes"): self.prepare(proof=proof)

    def test_mutated_source_pins_and_duplicate_original_receipt_rejected(self):
        (self.root / self.input_path).write_bytes(b"drifted source")
        with self.assertRaises(w.WorkflowError): self.prepare()

    def test_duplicate_original_effect_receipt_cannot_be_selected_twice(self):
        w.append_jsonl_locked(w.receipts_path(self.root, TO), self.ack)
        with self.assertRaisesRegex(w.WorkflowError, "one exact original"): self.prepare()

    def test_self_review_or_new_permission_cannot_become_formal_plan(self):
        for changes in ({"reviewer_department": PRODUCER}, {"production_write_allowed": True}, {"external_permission_issued": True}):
            with self.subTest(changes=changes), self.assertRaises(w.WorkflowError):
                review.validate_plan(self.root, self.snapshot(), {**self.plans[F4], **changes})

    def test_foreign_project_binding_or_wrong_capability_rejected_before_preparation(self):
        original = w.read_json(self.root / "data/department-registry.json")
        for role, field, value in ((PRODUCER, "project_id", "foreign-project"),
                                   (A2, "cwd", str(self.root.parent)),
                                   ("operations", "project_id", "foreign-project")):
            registry = copy.deepcopy(original)
            next(row for row in registry["departments"] if row["id"] == role)["chat_binding"][field] = value
            w.atomic_write_json(self.root / "data/department-registry.json", registry)
            with self.subTest(role=role, field=field), self.assertRaises(w.WorkflowError): self.prepare()
        w.atomic_write_json(self.root / "data/department-registry.json", original)
        snapshot = self.snapshot(); snapshot["goal_delivery"]["acceptance_capability"] = "publishing"
        with self.assertRaises(w.WorkflowError):
            review.prepare_native_multi_goal_review(self.root, snapshot, self.plans[F4]["native_multi_goal_review"])


if __name__ == "__main__":
    unittest.main()
