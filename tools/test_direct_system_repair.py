"""Regression checks for source transactions and lossless native evidence.

All actions use isolated project-local fixtures, never provider messages.
"""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import goal_delivery_runtime as runtime
import qa_review_plan as q
import source_patch_transaction as source
import workflow_control as w
import result_coordination as coordination
import test_goal_runtime_consumers as fixture
import datetime as dt


class NativeEvidenceTests(unittest.TestCase):
    def wrapper(self):
        return {"actual_thread_id": "fixed-registered-target",
                "exact_consumed_prompt": {"path": "reports/message.txt", "sha256": "a" * 64, "size": 12},
                "raw_tool_return": {"isError": False, "content": [{"type": "text", "text": json.dumps({"threadId": "fixed-registered-target"})}]}}

    def test_legacy_and_typed_wrappers_preserve_the_original_bytes(self):
        legacy = self.wrapper()
        before = json.dumps(legacy, sort_keys=True)
        normalized = q._review_same_goal_send_wrapper(legacy)
        self.assertEqual(normalized["thread_id"], legacy["actual_thread_id"])
        self.assertEqual(q._review_same_goal_send_wrapper(normalized), normalized)
        self.assertEqual(json.dumps(legacy, sort_keys=True), before)

    def test_target_tool_and_payload_mismatch_are_rejected(self):
        wrong = [dict(self.wrapper(), actual_thread_id="another-target"),
                 dict(self.wrapper(), exact_consumed_prompt=True),
                 dict(self.wrapper(), actual_tool="another-tool"),
                 dict(self.wrapper(), unknown=True)]
        for value in wrong:
            with self.subTest(value=value), self.assertRaises(ValueError):
                q._review_same_goal_send_wrapper(value)

    def test_failure_truncation_and_conflicting_structured_data_are_rejected(self):
        for change in ({"isError": True}, {"truncated": True}, {"failed": True},
                       {"errors": ["failed"]}, {"structuredContent": {"threadId": "wrong"}}):
            value = self.wrapper()
            value["raw_tool_return"].update(change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                q._review_same_goal_send_wrapper(value)

    def test_duplicate_json_and_nonfinite_numbers_are_rejected(self):
        for text in ('{"threadId":"one","threadId":"two"}', '{"threadId":NaN}'):
            value = self.wrapper()
            value["raw_tool_return"]["content"][0]["text"] = text
            with self.subTest(text=text), self.assertRaises(ValueError):
                q._review_same_goal_send_wrapper(value)

    def test_optional_false_error_flag_is_not_required(self):
        value = self.wrapper()
        del value["raw_tool_return"]["isError"]
        self.assertEqual(q._review_same_goal_send_wrapper(value)["thread_id"], "fixed-registered-target")


class SourceTransactionTests(unittest.TestCase):
    def setUp(self):
        area = Path(__file__).resolve().parents[1] / ".test-tmp"
        area.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=area)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for directory in ("tools", "working", "logs", "backups"):
            (self.root / directory).mkdir()
        for name in ("one", "two"):
            (self.root / "tools" / (name + ".py")).write_text("VALUE = 'before'\n")
            (self.root / "working" / (name + ".py")).write_text("VALUE = 'after'\n")
        self.changes = [{"path": "tools/" + name + ".py",
                         "before": source.fingerprint(self.root, "tools/" + name + ".py"),
                         "candidate": "working/" + name + ".py"} for name in ("one", "two")]

    def apply(self, prepared):
        return source.apply(self.root, prepared, "backups/exact", task_id="local-source-test")

    def test_actual_replacement_modes_backups_and_normal_readback(self):
        (self.root / "tools/one.py").chmod(0o600)
        self.changes[0]["before"] = source.fingerprint(self.root, "tools/one.py")
        result = self.apply(source.prepare(self.root, self.changes))
        self.assertEqual(source.readback(self.root, result["journal"])["files"], 2)
        self.assertEqual((self.root / "tools/one.py").stat().st_mode & 0o777, 0o600)
        self.assertEqual((self.root / "backups/exact/tools/one.py").read_text(), "VALUE = 'before'\n")
        self.assertFalse(source.readback(self.root, result["journal"])["business_goal_closed"])

    def test_newer_source_prevents_any_replacement(self):
        prepared = source.prepare(self.root, self.changes)
        (self.root / "tools/two.py").write_text("VALUE = 'newer work'\n")
        with self.assertRaises(w.WorkflowError):
            self.apply(prepared)
        self.assertEqual((self.root / "tools/one.py").read_text(), "VALUE = 'before'\n")
        self.assertFalse((self.root / "backups/exact").exists())

    def test_candidate_changes_cannot_enter_the_write_transaction(self):
        prepared = source.prepare(self.root, self.changes)
        (self.root / "working/one.py").write_text("VALUE = 'unreviewed'\n")
        with self.assertRaises(w.WorkflowError):
            self.apply(prepared)

    def test_unrelated_result_does_not_invalidate_an_unchanged_source(self):
        prepared = source.prepare(self.root, self.changes)
        (self.root / "logs/unrelated-result.json").write_text('{"result":"new"}')
        self.assertEqual(self.apply(prepared)["state"], "adopted")

    def test_failed_second_write_restores_only_our_changed_files(self):
        prepared = source.prepare(self.root, self.changes)
        replace, calls = source._replace, []
        def fail(path, raw, mode):
            calls.append(path)
            if len(calls) == 3:
                raise OSError("simulated second-file backup failure")
            return replace(path, raw, mode)
        with mock.patch.object(source, "_replace", side_effect=fail), self.assertRaises(OSError):
            self.apply(prepared)
        self.assertEqual((self.root / "tools/one.py").read_text(), "VALUE = 'before'\n")
        self.assertEqual((self.root / "tools/two.py").read_text(), "VALUE = 'before'\n")
        self.assertEqual(json.loads((self.root / "backups/exact/journal.json").read_text())["state"], "rolled_back")

    def test_changed_applied_source_is_preserved_during_failure_recovery(self):
        prepared = source.prepare(self.root, self.changes)
        replace, calls = source._replace, []
        def fail(path, raw, mode):
            calls.append(path)
            if len(calls) == 3:
                (self.root / "tools/one.py").write_text("VALUE = 'parallel newer'\n")
                raise OSError("simulated parallel edit")
            return replace(path, raw, mode)
        with mock.patch.object(source, "_replace", side_effect=fail), self.assertRaises(OSError):
            self.apply(prepared)
        self.assertEqual((self.root / "tools/one.py").read_text(), "VALUE = 'parallel newer'\n")
        self.assertEqual(json.loads((self.root / "backups/exact/journal.json").read_text())["state"], "rollback_conflict")

    def test_path_escape_symlink_and_duplicate_targets_are_rejected(self):
        (self.root / "tools/link.py").symlink_to(self.root / "tools/one.py")
        for changes in ([dict(self.changes[0], path="../escape.py")],
                        [dict(self.changes[0], path="tools/link.py")], self.changes * 2):
            with self.subTest(changes=changes), self.assertRaises(w.WorkflowError):
                source.prepare(self.root, changes)

    def test_invalid_python_is_rejected_before_any_source_write(self):
        (self.root / "working/one.py").write_text("not valid python !")
        with self.assertRaises(SyntaxError):
            source.prepare(self.root, self.changes)
        self.assertEqual((self.root / "tools/one.py").read_text(), "VALUE = 'before'\n")


class NoticeResumeTests(unittest.TestCase):
    def setUp(self):
        self.t = fixture.GoalRuntimeConsumerTests("runTest")
        self.t.setUp()
        self.addCleanup(self.t.doCleanups)
        self.root = self.t.root
        _, producer = self.t.prepare_initial_review()
        self.identity = {"task_id": self.t.task_id, "sender_department": fixture.PRODUCER,
                         "candidate_version": "v1", "result_sha256": producer["sha256"]}
        w.record_result_handoff(self.root, {**self.identity, **self.t.completed_result_fields(),
            "outbox_path": producer["path"], "event": "notification_queued", "idempotency_key": "notice-resume-queue"})
        self.payload_path = "reports/complete-result-notice.txt"
        (self.root / self.payload_path).write_text(" ".join(self.identity.values()))
        self.payload = w.file_digest(self.root, self.payload_path)

    def live(self, status):
        binding = w.department_registry(self.root)[fixture.ASSISTANT]["chat_binding"]
        native = {"threads": [{"id": binding["task_id"], "status": status,
                  "projectId": binding["project_id"], "title": binding["title"], "cwd": binding["cwd"]}]}
        path = self.t.write("reports/live-native-" + status + ".json", native)
        wrapper = {"observed_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                   "actual_native_observation": w.file_digest(self.root, path)}
        path = self.t.write("reports/live-" + status + ".json", wrapper)
        return w.file_digest(self.root, path)

    def claim(self, status):
        return coordination.notification_claim(self.root, self.identity, fixture.PRODUCER,
            "fixture-producer", "notice-" + status, self.live(status), self.payload)

    def test_sender_can_find_its_own_notification_before_recipient_acceptance(self):
        plan = coordination.notification_plan(self.root, fixture.PRODUCER)
        self.assertEqual(plan["pending_count"], 1)
        self.assertEqual(plan["notifications"][0]["delivery_owner"], fixture.PRODUCER)
        self.assertFalse(plan["queue_is_delivery"])

    def test_busy_deferral_retains_a_real_recheck_action_without_interrupting(self):
        result = self.claim("active")
        self.assertEqual(result["result"], "deferred")
        self.assertFalse(result["interrupts_active_thread"])
        item = coordination.notification_plan(self.root, fixture.PRODUCER)["notifications"][0]
        self.assertFalse(item["actionable"]); self.assertTrue(item["waiting_for_native_completion"])
        self.assertEqual(item["next_action"], "refresh_busy_target_at_next_legal_opportunity")
        self.assertFalse(item["delivered"])

    def test_deferred_notice_can_be_prepared_once_after_fresh_idle_observation(self):
        self.claim("active")
        result = self.claim("idle")
        self.assertEqual(result["result"], "ready")
        self.assertFalse(result["delivered"])
        self.assertEqual(coordination.validate_notification_delivery(self.root, self.identity)["state"], "prepared")

    def test_future_named_dependency_is_not_due_and_unrelated_roles_do_not_own_notice(self):
        path = coordination._notification_path(self.root, self.identity)
        value = w.read_json(path)
        value.update(state="deferred", defer_reason="external_input",
                     next_check_at=(dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=1)).isoformat())
        w.atomic_write_json(path, value)
        self.assertFalse(coordination.notification_plan(self.root, fixture.PRODUCER)["notifications"][0]["actionable"])
        self.assertEqual(coordination.notification_plan(self.root, "operations-assistant-3")["pending_count"], 0)


if __name__ == "__main__":
    unittest.main()
