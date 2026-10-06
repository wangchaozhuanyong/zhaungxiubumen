import json
import tempfile
import unittest
from pathlib import Path

from department_reply import _read_reply
from workflow_control import WorkflowError


class DepartmentReplyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "session.jsonl"
        self.rows = [
            {"type": "session_meta", "payload": {"id": "fixed-content", "cwd": self.tmp.name}},
            {"type": "event_msg", "payload": {"type": "task_started", "turn_id": "turn-1"}},
            {"type": "turn_context", "payload": {"turn_id": "turn-1", "cwd": self.tmp.name}},
            {"type": "response_item", "timestamp": "2026-09-12T08:28:52Z", "payload": {
                "type": "message", "role": "assistant", "id": "msg-1", "phase": "final_answer",
                "content": [{"type": "output_text", "text": "HEALTH_OK"}]}},
            {"type": "event_msg", "payload": {"type": "task_complete", "turn_id": "turn-1", "last_agent_message": "HEALTH_OK"}},
        ]

    def tearDown(self):
        self.tmp.cleanup()

    def check(self):
        self.path.write_text("\n".join(json.dumps(row) for row in self.rows), encoding="utf-8")
        return _read_reply(self.path, "fixed-content", self.tmp.name, "turn-1")

    def test_final_reply_is_verified_without_exposing_body(self):
        result = self.check()
        self.assertEqual(result["status"], "reply_verified")
        self.assertEqual(result["reply_ref"], "msg-1")
        self.assertEqual(len(result["reply_sha256"]), 64)
        self.assertNotIn("HEALTH_OK", json.dumps(result))

    def test_empty_or_mismatched_completion_is_not_healthy(self):
        self.rows[-1]["payload"]["last_agent_message"] = ""
        self.assertEqual(self.check()["status"], "reply_unverified")
        self.rows.pop(3)
        self.assertFalse(self.check()["reply_nonempty"])

    def test_other_thread_is_rejected(self):
        self.rows[0]["payload"]["id"] = "unrelated-project-thread"
        with self.assertRaises(WorkflowError):
            self.check()

    def test_latest_completed_reply_remains_verifiable_during_new_active_turn(self):
        self.rows.append({"type": "event_msg", "payload": {"type": "task_started", "turn_id": "turn-2"}})
        self.assertEqual(self.check()["status"], "reply_verified")

    def test_old_reply_cannot_hide_new_completed_failed_turn(self):
        self.rows.append({"type": "event_msg", "payload": {"type": "task_started", "turn_id": "turn-2"}})
        self.rows.append({"type": "event_msg", "payload": {"type": "task_complete", "turn_id": "turn-2", "last_agent_message": ""}})
        with self.assertRaises(WorkflowError):
            self.check()

    def test_commentary_cannot_be_final_reply(self):
        self.rows[3]["payload"]["phase"] = "commentary"
        self.assertEqual(self.check()["status"], "reply_unverified")

    def test_wrong_cwd_is_rejected(self):
        self.rows[2]["payload"]["cwd"] = "/other/project"
        with self.assertRaises(WorkflowError):
            self.check()

    def test_only_structured_trailing_memory_metadata_may_be_omitted(self):
        self.rows[3]["payload"]["content"][0]["text"] += (
            "<oai-mem-citation>\n<citation_entries>MEMORY.md:1-2</citation_entries>"
            "\n<rollout_ids>test-id</rollout_ids>\n</oai-mem-citation>")
        self.assertEqual(self.check()["status"], "reply_verified")
        self.rows[-1]["payload"]["last_agent_message"] = "OTHER_REPLY"
        self.assertEqual(self.check()["status"], "reply_unverified")

    def test_arbitrary_trailing_text_or_malformed_metadata_cannot_match(self):
        for suffix in (" extra words", "<oai-mem-citation>broken",
                       "<oai-mem-citation><other>text</other></oai-mem-citation>",
                       "<oai-mem-citation><citation_entries/><rollout_ids/>"
                       "</oai-mem-citation>extra"):
            self.rows[3]["payload"]["content"][0]["text"] = "HEALTH_OK" + suffix
            self.assertEqual(self.check()["status"], "reply_unverified")
