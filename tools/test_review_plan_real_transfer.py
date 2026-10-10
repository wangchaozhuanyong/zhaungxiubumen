"""Original frozen goal versus actual backup transfer; synthetic bounded data.

These tests call read-only plan consumers and existing fixture lease gates.
They never bind a plan, issue a verdict, or mutate live project evidence.
"""
import copy
import datetime as dt
import json
import os
from pathlib import Path
import unittest
from unittest import mock

import qa_review_plan as review
import test_technical_review_backup as fixtures
import workflow_control as w


class RealTransferPlanTests(unittest.TestCase):
    def setUp(self):
        output = Path(__file__).resolve().parents[1] / ".test-tmp"
        self.fixture = fixtures.TechnicalBackupTests("runTest")
        with mock.patch.dict(os.environ, {"TECHNICAL_BACKUP_TEST_OUTPUT": str(output)}):
            self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        self.task = self.fixture.identity["task_id"]
        snapshot = self.fixture.snapshot()
        self.frozen = copy.deepcopy(snapshot["goal_delivery"])
        path = "reports/frozen-original-goal.json"
        w.atomic_write_json(self.root / path, self.frozen)
        self.pin = w.file_digest(self.root, path)
        snapshot["goal_contract"] = self.pin
        snapshot["departments"] = [{"department": role, "chat_task_id": "fixed-" + role,
                                    "depends_on": [], "execution_wave": 1}
                                   for role in (self.frozen["primary_owner"], fixtures.A2)]
        snapshot["plan_status"] = "ready_to_send"
        w.atomic_write_json(w.snapshot_path(self.root, self.task), snapshot)
        self.frozen_bytes = (self.root / path).read_bytes()

    def transferred(self):
        self.old_lease = self.fixture.ready_lease()
        self.lease = self.fixture.transfer(self.old_lease)
        return self.fixture.snapshot()

    def source(self, role=fixtures.A3):
        stamp = dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=1)
        dispatch = {"receipt_type": "dispatch_sent", "task_id": self.task,
                    "department": role, "chat_task_id": "fixed-" + role,
                    "action_id": "assign-goal-review:" + self.task,
                    "scope": fixtures.SCOPE, "evidence": [self.pin],
                    "created_at": stamp.isoformat()}
        ack = {"receipt_type": "chat_ack", "task_id": self.task,
               "department": role, "chat_task_id": "fixed-" + role,
               "ack_nonempty": True, "created_at": (stamp + dt.timedelta(milliseconds=100)).isoformat()}
        plan = {"reviewer_thread_id": "fixed-" + role, "scope": fixtures.SCOPE}
        return dispatch, ack, plan

    def assert_source_rejected(self, snapshot):
        dispatch, _, _ = self.source()
        self.assertFalse(review._initial_assignment(self.root, snapshot, dispatch))

    def test_actual_committed_backup_transfer_recognizes_current_initial_round(self):
        snapshot = self.transferred()
        dispatch, ack, plan = self.source()
        self.assertTrue(review._initial_assignment(self.root, snapshot, dispatch))
        source = review._assigned_review_round(self.root, snapshot, [dispatch, ack], plan)
        self.assertEqual(source["dispatch"], dispatch)
        self.assertEqual(source["ack"], ack)
        self.assertEqual(snapshot["goal_delivery"]["responsible_assistant"], fixtures.A3)
        self.assertEqual(self.frozen["responsible_assistant"], fixtures.A2)
        self.assertEqual((self.root / self.pin["path"]).read_bytes(), self.frozen_bytes)
        self.assertIsNone(snapshot.get("qa_review_plan"))

    def test_original_untransferred_initial_assignment_remains_valid(self):
        snapshot = self.fixture.snapshot()
        dispatch, ack, plan = self.source(fixtures.A2)
        self.assertTrue(review._initial_assignment(self.root, snapshot, dispatch))
        self.assertIsNotNone(review._assigned_review_round(self.root, snapshot, [dispatch, ack], plan))

    def test_source_qualification_does_not_reuse_expired_or_released_result_lease(self):
        snapshot = self.transferred()
        dispatch, _, _ = self.source()
        self.fixture.a.conn.execute("UPDATE claims SET expires=0 WHERE result_key=?", (self.lease["result_key"],))
        self.assertTrue(review._initial_assignment(self.root, snapshot, dispatch))
        with self.assertRaisesRegex(w.WorkflowError, "stale|expired|foreign"):
            self.fixture.a.renew(self.fixture.identity, fixtures.A3, fixtures.A3, self.lease)
        self.fixture.a.conn.execute("UPDATE claims SET expires=? WHERE result_key=?", (self.lease["expires"], self.lease["result_key"]))
        self.fixture.a.release(self.fixture.identity, fixtures.A3, fixtures.A3, self.lease, "bounded fixture release")
        self.assertTrue(review._initial_assignment(self.root, snapshot, dispatch))
        with self.assertRaisesRegex(w.WorkflowError, "stale|expired|foreign"):
            self.fixture.a.renew(self.fixture.identity, fixtures.A3, fixtures.A3, self.lease)

    def test_current_round_still_requires_same_task_thread_scope_and_nonempty_ack(self):
        snapshot = self.transferred()
        dispatch, ack, plan = self.source()
        for changes in ({"task_id": "other-task"}, {"chat_task_id": "other-thread"},
                        {"scope": "project:other-company:review"}, {"receipt_type": "dispatch_failed"}):
            with self.subTest(dispatch=changes):
                self.assertIsNone(review._assigned_review_round(self.root, snapshot, [{**dispatch, **changes}, ack], plan))
        for changes in ({"chat_task_id": "other-thread"}, {"ack_nonempty": False}, {"department": fixtures.A2}):
            with self.subTest(ack=changes):
                self.assertIsNone(review._assigned_review_round(self.root, snapshot, [dispatch, {**ack, **changes}], plan))

    def test_arbitrary_current_reviewer_without_committed_transfer_is_rejected(self):
        snapshot = self.fixture.snapshot()
        snapshot["goal_delivery"].update(responsible_assistant=fixtures.A3, assignment_history=[{
            "previous_assistant": fixtures.A2, "target_assistant": fixtures.A3,
            "result_identity": self.fixture.identity, "fence": 1}])
        self.assert_source_rejected(snapshot)

    def test_all_other_frozen_goal_identity_fields_remain_exact(self):
        original = self.transferred()
        mutations = {"objective": "different objective", "completion_criteria": ["different"],
                     "primary_owner": "publishing", "authorized_scope": ["project:other-company:review"],
                     "producer_departments": ["publishing"], "acceptance_capability": "paid"}
        for key, value in mutations.items():
            with self.subTest(field=key):
                snapshot = copy.deepcopy(original)
                snapshot["goal_delivery"][key] = value
                self.assert_source_rejected(snapshot)

    def test_transfer_source_task_fence_and_history_cannot_be_forged(self):
        original = self.transferred()
        mutations = ({"previous_assistant": "operations"}, {"target_assistant": fixtures.A2},
                     {"fence": original["goal_delivery"]["assignment_history"][0]["fence"] + 1},
                     {"result_identity": {**self.fixture.identity, "task_id": "other-task"}})
        for changes in mutations:
            with self.subTest(changes=changes):
                snapshot = copy.deepcopy(original)
                snapshot["goal_delivery"]["assignment_history"][0].update(changes)
                self.assert_source_rejected(snapshot)
        for history in ([], ["invalid"], original["goal_delivery"]["assignment_history"] * 2):
            with self.subTest(history=history):
                snapshot = copy.deepcopy(original)
                snapshot["goal_delivery"]["assignment_history"] = history
                self.assert_source_rejected(snapshot)

    def test_corrupted_transfer_audit_or_event_cannot_activate_plan_source(self):
        snapshot = self.transferred()
        path = self.root / w.WORKFLOW_EVENTS
        original = path.read_bytes()
        events = w.read_jsonl(path)
        events[-1]["event_hash"] = "0" * 64
        path.write_text("".join(json.dumps(row) + "\n" for row in events))
        self.assert_source_rejected(snapshot)
        path.write_bytes(original)
        self.fixture.a.conn.execute("UPDATE coordination_audit SET record_hash=? WHERE seq=(SELECT MAX(seq) FROM coordination_audit)", ("0" * 64,))
        self.assert_source_rejected(snapshot)

    def test_human_parent_capability_and_production_boundaries_remain_required(self):
        original = self.transferred()
        for changes in ({"parent_task_id": "other-parent"},
                        {"human_authorization": {**original["goal_delivery"]["human_authorization"], "message_id": "other-message"}},
                        {"required_execution_actions": [{"action_class": "site_publish"}]},
                        {"producer_departments": [self.frozen["primary_owner"], fixtures.A3]}):
            with self.subTest(changes=changes):
                snapshot = copy.deepcopy(original)
                snapshot["goal_delivery"].update(changes)
                self.assert_source_rejected(snapshot)
        self.fixture.install_backup(enabled=False)
        self.assert_source_rejected(original)

    def test_old_reviewers_verdict_is_never_migrated_to_current_initial_source(self):
        snapshot = self.transferred()
        path = w.receipts_path(self.root, self.task)
        with path.open("a") as stream:
            stream.write(json.dumps({"receipt_type": "qa_verdict", "department": fixtures.A2,
                                     "verdict": "pass", "fixture_only": True}) + "\n")
        self.assert_source_rejected(snapshot)


if __name__ == "__main__":
    unittest.main()
