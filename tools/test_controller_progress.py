import datetime as dt
import unittest
from pathlib import Path
from unittest.mock import patch

import controller_progress as progress


class ControllerContinuationTest(unittest.TestCase):
    def test_zero_intake_and_active_department_do_not_allow_stop(self):
        result = progress.decide_continuation(
            [{"department": "qa", "thread_id": "fixed", "native_status": "active", "identity_verified": True}],
            {"active_tasks": [{"department": "qa"}]},
            {"pending_count": 0, "followthrough_pending_count": 0}, {}, [])
        self.assertFalse(result["ordinary_stop_allowed"])
        self.assertEqual(result["next_mode"], "NATIVE_EVENT_WAIT")
        self.assertFalse(result["project_queue_wakes_ended_controller"])

    def test_idle_owned_task_requires_result_intake(self):
        result = progress.decide_continuation(
            [{"department": "seo", "thread_id": "fixed", "native_status": "idle", "identity_verified": True}],
            {"active_tasks": [{"department": "seo"}]}, {}, {}, [])
        self.assertFalse(result["ordinary_stop_allowed"])
        self.assertIn("owned_task_ended_collect_actual_reply_before_stopping", result["reasons"])

    def test_old_closed_workflow_does_not_cancel_followthrough(self):
        result = progress.decide_continuation([], {"workflow_state": "closed"},
            {"pending_count": 0, "followthrough_pending_count": 4}, {}, [])
        self.assertFalse(result["ordinary_stop_allowed"])
        self.assertFalse(result["business_goal_closed"])

    def test_queued_QA_requires_real_dispatch(self):
        result = progress.decide_continuation([], {}, {}, {"waiting_dispatch": [{"packet": "new"}]}, [])
        self.assertFalse(result["ordinary_stop_allowed"])
        self.assertIn("exact_QA_dispatch_pending", result["reasons"])

    def test_no_pending_control_scope_is_not_business_goal_complete(self):
        result = progress.decide_continuation([], {}, {}, {}, [])
        self.assertTrue(result["ordinary_stop_allowed"])
        self.assertFalse(result["business_goal_closed"])

    def test_partial_department_turn_must_be_received_and_decided(self):
        result = progress.decide_continuation(
            [{"department": "seo", "thread_id": "fixed", "native_status": "idle", "identity_verified": True}],
            {"active_tasks": [{"department": "seo", "status": "partial"}]},
            {"pending_count": 1}, {}, [])
        self.assertFalse(result["ordinary_stop_allowed"])
        self.assertIn("result_intake_or_decision_pending", result["reasons"])

    def test_failed_notification_recovery_is_not_zero_work(self):
        result = progress.decide_continuation([], {},
            {"pending_count": 1, "legacy_recovery_count": 1}, {}, [])
        self.assertFalse(result["ordinary_stop_allowed"])

    def test_due_external_dependency_requires_fresh_followthrough_review(self):
        result = progress.decide_continuation([], {},
            {"pending_count": 0, "followthrough_pending_count": 1}, {}, [])
        self.assertFalse(result["ordinary_stop_allowed"])
        self.assertFalse(result["business_goal_closed"])

    def test_missing_native_identity_is_never_filled_from_registry(self):
        now = dt.datetime.now(dt.timezone.utc)
        registry = {"qa": {"name": "QA", "chat_binding": {
            "task_id": "fixed", "project_id": "project", "cwd": "/project", "title": "QA"}}}
        roles, _ = progress.inspect_live(registry, {
            "observed_at": now.isoformat(), "threads": [{"id": "fixed", "cwd": "/project", "title": "QA"}],
            "sections": [{"name": "装修公司部门", "itemKeys": ["codex:thread:local:fixed"]}]}, now)
        self.assertFalse(roles[0]["identity_verified"])
        self.assertEqual(roles[0]["identity_issue"], "fixed_thread_identity_mismatch")
        result = progress.decide_continuation(roles, {}, {}, {}, [])
        self.assertFalse(result["ordinary_stop_allowed"])

    def test_stale_snapshot_cannot_verify_active_task(self):
        now = dt.datetime.now(dt.timezone.utc)
        roles, errors = progress.inspect_live({}, {
            "observed_at": (now - dt.timedelta(minutes=6)).isoformat()}, now)
        self.assertIn("live_snapshot_stale_or_future", errors)
        result = progress.decide_continuation(roles, {}, {}, {}, errors)
        self.assertFalse(result["ordinary_stop_allowed"])

    def test_old_followthrough_cannot_hide_new_department_delivery(self):
        common = {"task_id": "original", "sender_department": "seo"}
        rows = [dict(common, candidate_version="old", result_sha256="old-hash",
                     event="controller_decision", decision="send_qa", next_owner="qa",
                     created_at="2026-10-05T01:00:00Z"),
                dict(common, candidate_version="new", result_sha256="new-hash",
                     event="notification_queued", created_at="2026-10-05T02:00:00Z"),
                dict(common, candidate_version="old", result_sha256="old-hash",
                     event="controller_followthrough", created_at="2026-10-05T03:00:00Z")]
        with patch.object(Path, "glob", return_value=[Path("original.jsonl")]), \
             patch.object(progress.workflow, "_result_handoff_rows", return_value=rows):
            result = progress.latest_results(Path("/project"))
        self.assertEqual(result["seo"]["candidate_version"], "new")

    def test_followthrough_preserves_result_decision_and_next_owner(self):
        common = {"task_id": "original", "sender_department": "seo",
                  "candidate_version": "v1", "result_sha256": "hash"}
        rows = [dict(common, event="controller_decision", decision="send_qa", next_owner="qa",
                     next_action="review exact v1", created_at="2026-10-05T01:00:00Z"),
                dict(common, event="controller_followthrough", created_at="2026-10-05T02:00:00Z")]
        with patch.object(Path, "glob", return_value=[Path("original.jsonl")]), \
             patch.object(progress.workflow, "_result_handoff_rows", return_value=rows):
            result = progress.latest_results(Path("/project"))
        self.assertEqual(result["seo"]["next_owner"], "qa")
        self.assertEqual(result["seo"]["decision"], "send_qa")

    def test_empty_control_queue_cannot_hide_actionable_business_work(self):
        result = progress.decide_continuation([], {}, {}, {}, [], [
            {"parent_id": "ORG-020", "requires_action": True}])
        self.assertFalse(result["ordinary_stop_allowed"])
        self.assertIn("business_backlog_action_or_dependency_reconciliation_pending", result["reasons"])

    def test_verified_parent_keeps_unsaved_child_even_without_next_action(self):
        now = dt.datetime(2026, 10, 6, 0, 0, tzinfo=dt.timezone.utc)
        rows = progress.business_work_items({"items": [{"id": "ORG-020", "status": "verified",
            "wave2": {"CMS_saved": False, "public_verified": False}}]}, now)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["scope_path"], "ORG-020/wave2")
        self.assertTrue(rows[0]["requires_action"])
        self.assertTrue(rows[0]["not_release_authorization"])

    def test_future_named_wait_defers_only_exact_scope(self):
        now = dt.datetime(2026, 10, 6, 0, 0, tzinfo=dt.timezone.utc)
        rows = progress.business_work_items({"items": [{"id": "ORG-006", "status": "blocked_data_missing",
            "owner": "paid-growth-data", "unblock_condition": "lawful fresh source export",
            "next_check_at": "2026-10-06T18:00:00+08:00"}]}, now)
        self.assertFalse(rows[0]["requires_action"])
        result = progress.decide_continuation([], {}, {}, {}, [], rows)
        self.assertTrue(result["ordinary_stop_allowed"])
        self.assertFalse(result["business_goal_closed"])

    def test_overdue_business_wait_requires_review(self):
        now = dt.datetime(2026, 10, 6, 12, 0, tzinfo=dt.timezone.utc)
        rows = progress.business_work_items({"items": [{"id": "ORG-006", "status": "blocked_data_missing",
            "owner": "paid-growth-data", "unblock_condition": "source export",
            "next_check_at": "2026-10-06T18:00:00+08:00"}]}, now)
        self.assertTrue(rows[0]["requires_action"])

    def test_incomplete_external_wait_cannot_authorize_stop(self):
        now = dt.datetime(2026, 10, 6, 0, 0, tzinfo=dt.timezone.utc)
        for missing in ("owner", "unblock_condition", "next_check_at"):
            row = {"id": "ORG-006", "status": "blocked_data_missing", "owner": "paid-growth-data",
                   "unblock_condition": "source export", "next_check_at": "2026-10-06T18:00:00+08:00"}
            del row[missing]
            with self.subTest(missing=missing):
                self.assertTrue(progress.business_work_items({"items": [row]}, now)[0]["requires_action"])

    def test_progress_report_names_exact_inflight_and_unlock_condition(self):
        report = progress.render({"generated_at_myt": "2026-10-06T08:00:00+08:00", "roles": [{
            "name": "SEO", "department": "seo", "native_status": "active", "identity_verified": True,
            "latest_recorded_result": {"candidate_version": "old-v1", "unblock_condition": "exact-source-pin",
                "next_check_at": "2026-10-06T18:00:00+08:00"},
            "current_checkpoint_tasks": [{"department": "seo", "task_id": "original-task",
                "candidate_version": "new-v2", "turn_id": "real-native-turn", "next_owner": "fixed-seo",
                "status": "actual_QA_wait_result", "unblock_condition": "current-exact-source-pin",
                "next_check_at": "2026-10-06T18:30:00+08:00", "next_action": "minimum-source-repair"}]}], "business_backlog_rows": [],
            "business_unfinished_scopes": [], "unfinished_control_rows": [],
            "control_counts": {"total_actionable_count": 0}, "distinct_control_task_count": 0,
            "continuation": {"ordinary_stop_allowed": False, "reasons": ["inflight"]}})
        for evidence in ("original-task", "new-v2", "real-native-turn", "fixed-seo", "minimum-source-repair",
                         "actual_QA_wait_result", "current-exact-source-pin", "2026-10-06T18:30:00+08:00"):
            self.assertIn(evidence, report)

    def test_explicit_prepared_packet_not_hidden_by_closed_priority_queue(self):
        result = progress.decide_continuation([], {"prepared_waiting_qa": [
            {"task_id": "original", "candidate_version": "new"}]}, {}, {}, [])
        self.assertFalse(result["ordinary_stop_allowed"])
        self.assertIn("explicit_prepared_QA_packet_requires_real_dispatch", result["reasons"])

    def test_verified_public_scope_is_not_requeued_without_an_unsaved_child(self):
        now = dt.datetime.now(dt.timezone.utc)
        rows = progress.business_work_items({"items": [{"id": "ORG-020", "status": "verified",
            "old": {"status": "verified_public", "next_action": "do not repeat Save"},
            "new": {"status": "verified_public", "CMS_saved": False}}]}, now)
        self.assertEqual([row["scope_path"] for row in rows], ["ORG-020/new"])

    def test_completed_followthrough_display_is_not_a_new_dispatch_instruction(self):
        report = progress.render({"generated_at_myt": "2026-10-06T08:00:00+08:00", "roles": [{
            "name": "SEO", "department": "seo", "native_status": "idle", "identity_verified": True,
            "latest_recorded_result": {"latest_event": "controller_followthrough",
                "followthrough_status": "internal_control_completed", "candidate_version": "reconcile-v1",
                "next_action": "reconcile old results", "next_owner": "operations"},
            "current_checkpoint_tasks": []}], "business_backlog_rows": [], "business_unfinished_scopes": [],
            "unfinished_control_rows": [], "control_counts": {"total_actionable_count": 0},
            "distinct_control_task_count": 0, "prepared_QA_packets": [{"task_id": "original",
                "candidate_version": "new-exact-packet", "department": "qa", "packet_path": "project/packet.json",
                "next_action": "one real dispatch"}],
            "continuation": {"ordinary_stop_allowed": False, "reasons": ["prepared"]}})
        self.assertIn("该条结果的后续动作已关联", report)
        self.assertIn("原决策动作已接续", report)
        self.assertIn("new-exact-packet", report)
        self.assertIn("project/packet.json", report)


if __name__ == "__main__":
    unittest.main()
