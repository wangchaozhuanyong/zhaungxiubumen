import hashlib
import json
import tempfile
import unittest
import copy
from pathlib import Path
from unittest.mock import patch

import qa_dispatch_priority as priority


class PriorityEvidenceRecoveryTest(unittest.TestCase):
    def setUp(self):
        fixtures = Path(__file__).resolve().parents[1] / "drafts/operations/qa-priority-evidence-recovery-v1/test-runtime"
        fixtures.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=fixtures)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = "logs/department-outbox/qa-result.json"
        (self.root / self.path).parent.mkdir(parents=True)
        self.old = self.write_result("old")
        self.result = {"receipt_id": "verdict", "receipt_type": "qa_verdict",
                       "department": "qa", "verdict": "blocked", "evidence": [self.old]}

    def write_result(self, version):
        path = self.root / self.path
        path.write_text(json.dumps({"candidate_version": version}))
        return {"path": self.path, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "size": path.stat().st_size}

    def replacement(self, pin, target="verdict", department="qa", identity="replacement"):
        return {"receipt_id": identity, "receipt_type": "evidence_replacement",
                "supersedes_receipt_id": target, "department": department, "evidence": [pin]}

    def test_unchanged_result_uses_original_pin(self):
        self.assertEqual(priority._qa_result_outbox(self.root, [self.result], self.result, self.old),
                         {"candidate_version": "old"})

    def test_explicit_replacement_recovers_bytes_without_changing_verdict(self):
        new = self.write_result("new")
        receipts = [self.result, self.replacement(new)]
        self.assertEqual(priority._qa_result_outbox(self.root, receipts, self.result, self.old),
                         {"candidate_version": "new"})
        self.assertEqual(self.result["verdict"], "blocked")

    def test_two_append_only_replacements_resolve_current_bytes(self):
        middle = self.write_result("middle")
        new = self.write_result("new")
        receipts = [self.result, self.replacement(middle),
                    self.replacement(new, target="replacement", identity="replacement2")]
        self.assertEqual(priority._qa_result_outbox(self.root, receipts, self.result, self.old),
                         {"candidate_version": "new"})

    def test_unrecorded_foreign_unrelated_and_archived_changes_are_rejected(self):
        new = self.write_result("new")
        archived = self.replacement(new)
        archived["receipt_type"] = "evidence_archive"
        for extra in ([], [self.replacement(new, department="sales")],
                      [self.replacement(new, target="other-verdict")], [archived]):
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                priority._qa_result_outbox(self.root, [self.result, *extra], self.result, self.old)

    def test_mismatch_after_recorded_replacement_still_rejects(self):
        pinned = self.write_result("recorded")
        self.write_result("unrecorded-later-change")
        with self.assertRaises(ValueError):
            priority._qa_result_outbox(self.root, [self.result, self.replacement(pinned)],
                                       self.result, self.old)

    def test_invalid_native_chain_cannot_reach_replacement_resolution(self):
        def file_pin(name, data):
            path = self.root / name
            path.write_text(json.dumps(data))
            return {"path": name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        registry = {"qa": {"chat_binding": {"task_id": "qa", "project_id": "project"}},
                    "operations": {"chat_binding": {"task_id": "ops", "project_id": "project"}}}
        queue = {"schema_version": "1.0", "project_id": "project", "controller_thread_id": "ops",
                 "qa_thread_id": "qa", "cwd": str(self.root), "items": [{
                     "task_id": "task", "candidate_version": "candidate", "action_id": "action",
                     "source_outbox": file_pin("source.json", {"task_id": "task", "candidate_version": "candidate"}),
                     "controller_decision": file_pin("decision.json", {
                         "task_id": "task", "candidate_version": "candidate",
                         "controller_received": True, "controller_decision": "send_qa"}),
                     "packet": file_pin("packet.json", {})}]}
        with patch.object(priority.workflow, "department_registry", return_value=registry), \
                patch.object(priority.workflow, "_validate_receipt_chain", return_value=([], ["hash-invalid"])), \
                patch.object(priority, "_qa_result_outbox") as resolver:
            result = priority.inspect(self.root, queue)
        self.assertEqual(result["mode"], "BLOCKED_INVALID_PRIORITY_EVIDENCE")
        resolver.assert_not_called()


class ExactPacketDispatchTest(unittest.TestCase):
    def setUp(self):
        fixtures = Path(__file__).resolve().parents[1] / "drafts/operations/qa-priority-evidence-recovery-v1/test-runtime"
        fixtures.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=fixtures)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        def pin(name, data):
            path = self.root / name
            path.write_text(json.dumps(data))
            return {"path": name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        self.registry = {"qa": {"chat_binding": {"task_id": "qa", "project_id": "project"}},
                         "operations": {"chat_binding": {"task_id": "ops", "project_id": "project"}}}
        self.item = {"task_id": "task", "candidate_version": "new", "action_id": "same-action",
                     "source_outbox": pin("source.json", {"task_id": "task", "candidate_version": "new"}),
                     "controller_decision": pin("decision.json", {"task_id": "task", "candidate_version": "new",
                                                                 "controller_received": True, "controller_decision": "send_qa"}),
                     "packet": pin("packet.json", {}), "require_exact_packet_dispatch": True}
        self.queue = {"schema_version": "1.0", "project_id": "project", "controller_thread_id": "ops",
                      "qa_thread_id": "qa", "cwd": str(self.root), "items": [self.item]}
        self.send = {"receipt_type": "dispatch_sent", "department": "qa", "chat_task_id": "qa",
                     "action_id": "same-action", "evidence": []}

    def inspect(self, sends):
        with patch.object(priority.workflow, "department_registry", return_value=self.registry), \
                patch.object(priority.workflow, "_validate_receipt_chain", return_value=(sends, [])):
            return priority.inspect(self.root, self.queue)

    def test_old_same_action_and_other_packet_do_not_dispatch_new_candidate(self):
        for evidence in ([], [{"path": "old-packet.json", "sha256": self.item["packet"]["sha256"]}],
                         [{"path": self.item["packet"]["path"], "sha256": "old-hash"}]):
            with self.subTest(evidence=evidence):
                result = self.inspect([{**self.send, "evidence": evidence}])
                self.assertEqual(result["mode"], "DEFER_DAILY_AWAIT_CONTROLLER_DISPATCH")
                self.assertEqual(len(result["waiting_dispatch"]), 1)

    def test_exact_packet_native_receipt_dispatches_only_this_candidate(self):
        result = self.inspect([{**self.send, "evidence": [self.item["packet"]]}])
        self.assertEqual(result["mode"], "RESUME_DISPATCHED_QA")
        self.assertEqual(len(result["dispatched_without_result"]), 1)

    def test_legacy_unflagged_dispatch_behavior_is_preserved(self):
        self.item.pop("require_exact_packet_dispatch")
        self.assertEqual(self.inspect([self.send])["mode"], "RESUME_DISPATCHED_QA")


class ReportOnlyVerdictIntakeTest(unittest.TestCase):
    def setUp(self):
        fixtures = Path(__file__).resolve().parents[1] / "drafts/operations/qa-priority-evidence-recovery-v1/test-runtime"
        fixtures.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=fixtures)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = "logs/department-outbox/qa-result.json"
        (self.root / self.path).parent.mkdir(parents=True)
        self.box = {
            "task_id": "task", "department": "qa", "candidate_version": "candidate",
            "action_id": "review", "action_class": "analysis", "scope": "internal:task:candidate",
            "qa_verdict": "pass", "status": "completed", "conclusion": "limited source acceptance",
            "evidence": [], "risks": [], "next_actions": [], "handoff": {},
            "approval_required": False, "learning": {"status": "no_new_learning"},
            "chat_reply": {"thread_id": "qa", "nonempty": True,
                           "in_current_fixed_department_chat": True},
        }
        self.result = {"receipt_id": "verdict", "receipt_type": "qa_verdict", "task_id": "task",
                       "department": "qa", "chat_task_id": "qa", "action_id": "review",
                       "action_class": "analysis", "scope": "internal:task:candidate", "verdict": "pass",
                       "evidence": [{"path": "reports/review.md", "sha256": "report-hash"}]}
        self.item = {"task_id": "task", "candidate_version": "candidate", "action_id": "review"}
        self.received = {**self.result, "receipt_id": "outbox", "receipt_type": "outbox_received"}
        self.pin_box()

    def pin_box(self):
        path = self.root / self.path
        path.write_text(json.dumps(self.box))
        self.received["evidence"] = [{"path": self.path, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}]

    def matches(self):
        return priority._received_result_matches(
            self.root, [{"receipt_type": "dispatch_sent"}, self.received, self.result],
            0, self.result, self.item, "qa")

    def test_report_only_verdict_uses_exact_received_v2(self):
        self.assertTrue(self.matches())

    def test_canonical_fixed_chat_id_completes_actual_result(self):
        self.box["chat_reply"].pop("thread_id")
        self.box["chat_reply"]["fixed_chat_task_id"] = "qa"
        self.pin_box()
        self.assertTrue(self.matches())

    def test_conflicting_chat_ids_cannot_complete_actual_result(self):
        self.box["chat_reply"]["fixed_chat_task_id"] = "foreign"
        self.pin_box()
        self.assertFalse(self.matches())

    def test_missing_chat_ids_cannot_complete_actual_result(self):
        self.box["chat_reply"].pop("thread_id")
        self.pin_box()
        self.assertFalse(self.matches())

    def test_receipt_after_verdict_cannot_retroactively_complete_round(self):
        self.assertFalse(priority._received_result_matches(
            self.root, [{"receipt_type": "dispatch_sent"}, self.result, self.received],
            0, self.result, self.item, "qa"))
        self.assertTrue(self.matches())

    def test_verdict_outside_dispatch_round_is_rejected(self):
        self.assertFalse(priority._received_result_matches(
            self.root, [{"receipt_type": "dispatch_sent"}, self.received],
            0, self.result, self.item, "qa"))
        self.assertFalse(priority._received_result_matches(
            self.root, [self.result, {"receipt_type": "dispatch_sent"}, self.received],
            1, self.result, self.item, "qa"))

    def test_wrong_candidate_action_scope_verdict_or_chat_cannot_complete_round(self):
        for key, value in (("candidate_version", "old"), ("action_id", "other"),
                           ("scope", "internal:task:other"), ("action_class", "site_publish"),
                           ("qa_verdict", "blocked"), ("department", "sales"),
                           ("chat_reply", "completed")):
            with self.subTest(key=key):
                saved = copy.deepcopy(self.box)
                self.box[key] = value
                self.pin_box()
                self.assertFalse(self.matches())
                self.box = saved
        for key, value in (("thread_id", "foreign"), ("nonempty", False),
                           ("in_current_fixed_department_chat", False)):
            with self.subTest(chat_key=key):
                saved = copy.deepcopy(self.box)
                self.box["chat_reply"][key] = value
                self.pin_box()
                self.assertFalse(self.matches())
                self.box = saved

    def test_unpinned_bytes_and_missing_v2_fields_fail_closed(self):
        (self.root / self.path).write_text(json.dumps({**self.box, "status": "changed"}))
        with self.assertRaises(ValueError):
            self.matches()
        self.box.pop("learning")
        self.pin_box()
        with self.assertRaises(priority.workflow.WorkflowError):
            self.matches()

    def test_unrelated_receipt_or_pre_dispatch_receipt_does_not_complete_round(self):
        self.received["action_id"] = "other"
        self.assertFalse(self.matches())
        self.received["action_id"] = "review"
        self.assertFalse(priority._received_result_matches(
            self.root, [self.received, {"receipt_type": "dispatch_sent"}, self.result],
            1, self.result, self.item, "qa"))


if __name__ == "__main__":
    unittest.main()
