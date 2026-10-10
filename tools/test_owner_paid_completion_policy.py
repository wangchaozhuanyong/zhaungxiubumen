"""Synthetic temporary fixtures; not independent QA or execution evidence."""
import copy
import datetime as dt
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import owner_paid_completion_policy as gate


class ExactCompletionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.patcher = patch.object(gate, "ROOT", str(self.root))
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        self.departments = {did: {"chat_binding": {
            "task_id": tid, "project_id": gate.PROJECT, "cwd": str(self.root), "title": did,
        }} for did, tid in [("paid-growth-data", gate.SOURCE), ("qa", gate.QA)]}
        self.live = {"source_method": "mcp__codex_app__list_threads",
                     "observed_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                     "threads": [{"id": tid, "projectId": gate.PROJECT, "cwd": str(self.root),
                                  "title": did, "status": "idle"} for did, tid in
                                 [("paid-growth-data", gate.SOURCE), ("qa", gate.QA)]],
                     "sections": [{"name": "装修公司部门", "sectionId": "native-section",
                                   "itemKeys": ["codex:thread:local:" + gate.SOURCE, "codex:thread:local:" + gate.QA]}]}
        self.save("live.json", self.live)
        self.auth = {"source_thread_id": gate.SOURCE, "source_method": "mcp__codex_app__read_thread",
                     "messages": [{"id": gate.AUTH, "type": "userMessage", "content": [{"text": "允许\n"}]},
                                  {"id": gate.FUNDS_AUTH, "type": "userMessage", "content": [{"text": "对，FPX由本人结算"}]}],
                     "preceding_question": {"id": "msg_04e57c709d781d12016ac70327c8bc87d0b41943ba051fdba5",
                                            "text": "固定质检部仅复核这次FPX确认；两套新广告启用＋本聊天四小时监控"}}
        self.packet = {"original_task_id": gate.TASK, "candidate_version": "paid-owner-completion-v42",
                       "account_id": "example-ads-account", "campaign_ids": gate.CAMPAIGNS,
                       "group_count": 6, "exact_keyword_count": 40, "rsa_count": 6,
                       "total_ad_fee_each_myr": 1350, "gross_spend_ceiling_myr": 3000,
                       "dates_myt": ["2026-10-08", "2026-10-14"], "hours_myt": "MON-SUN10:00-22:00",
                       "shop_hours_unchanged": True, "funds_owner_message": "对，FPX由本人结算",
                       "owner_authorization": self.save("auth.json", self.auth), "frozen_inputs": [],
                       "live_identity_path": "live.json", "final_qa_proof_path": "proof.json", "actions": {}}
        for key in gate.ACTIONS:
            payload = {"id": "flash-cast-3", "mode": "update", "kind": "heartbeat",
                       "targetThreadId": gate.SOURCE, "status": "ACTIVE",
                       "rrule": "RRULE:FREQ=DAILY;BYHOUR=10,14,18,22;BYMINUTE=0;BYSECOND=0"}
            self.packet["actions"][key] = {"payload": self.save(key + ".json", payload), "attempt_path": key + "-attempt.json"}
        self.policy = {"paid_promotion_enabled": False,
                       "routing_policy": {"source_project_id": gate.PROJECT, "source_project_root": str(self.root)},
                       "owner_paid_completion_v42": {"status": "owner_approved_exact_completion", "packet": self.save("packet.json", self.packet)}}

    def save(self, name, data):
        p = self.root / name
        p.write_text(json.dumps(data, ensure_ascii=False))
        return {"path": name, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}

    def refresh_packet(self):
        self.policy["owner_paid_completion_v42"]["packet"] = self.save("packet.json", self.packet)

    def request(self, key="funds-qa"):
        cls, aid, dept, tid = gate.ACTIONS[key]
        return {"task_id": gate.TASK, "department": "paid-growth-data", "action_id": aid,
                "action_class": cls, "scope": gate.PREFIX + key, "consume_approval": True,
                "source_project_id": gate.PROJECT, "target_project_id": gate.PROJECT,
                "target_department": dept, "target_thread_id": tid, "target_thread_title": dept,
                "target_cwd": str(self.root), "target_sidebar_section_id": "native-section",
                "payload_sha256": self.packet["actions"][key]["payload"]["sha256"]}

    def check(self, request=None, healthy=True):
        return gate.check(self.root, self.policy, self.departments, request or self.request(), lambda *a, **k: healthy)

    def test_exact_qa_and_automation_only(self):
        self.assertEqual(self.check(), [])
        self.assertEqual(self.check(self.request("monitor-update")), [])
        self.assertFalse(self.policy["paid_promotion_enabled"])

    def test_enable_denies_missing_actual_qa(self):
        self.assertTrue(self.check(self.request("enable-two-new-search")))

    def test_unknown_or_wrong_tuple_denied(self):
        for key, val in [("task_id", "other"), ("department", "operations"), ("action_class", "ads_write"),
                         ("action_id", "remove-old"), ("target_project_id", "other"),
                         ("target_thread_id", "other"), ("payload_sha256", "0" * 64),
                         ("scope", gate.PREFIX + "delete-old"), ("skill", "renovation-seo-geo")]:
            with self.subTest(key=key):
                r = self.request(); r[key] = val
                self.assertTrue(self.check(r))

    def test_native_identity_stale_active_missing_denied(self):
        for change in ["stale", "active", "missing", "section"]:
            with self.subTest(change=change):
                live = copy.deepcopy(self.live)
                if change == "stale": live["observed_at"] = "2026-10-01T00:00:00Z"
                if change == "active": live["threads"][1]["status"] = "active"
                if change == "missing": live["threads"] = live["threads"][:1]
                if change == "section": live["sections"][0]["itemKeys"] = []
                self.save("live.json", live)
                self.assertTrue(self.check())
        self.save("live.json", self.live)
        self.assertTrue(self.check(healthy=False))

    def test_replay_and_frozen_drift_denied(self):
        self.save("funds-qa-attempt.json", {"attempt": True})
        self.assertTrue(self.check())
        self.save("monitor-update.json", {"changed": True})
        self.assertTrue(self.check(self.request("monitor-update")))

    def test_changed_launch_scope_denied(self):
        original = copy.deepcopy(self.packet)
        for key, value in [("campaign_ids", ["00074720157", "00063878462"]), ("total_ad_fee_each_myr", 1500),
                           ("hours_myt", "ALLDAY"), ("group_count", 11), ("shop_hours_unchanged", False)]:
            with self.subTest(key=key):
                self.packet = copy.deepcopy(original); self.packet[key] = value; self.refresh_packet()
                self.assertTrue(self.check())

    def test_qa_proof_must_bind_exact_fixed_native_reply(self):
        pin = self.policy["owner_paid_completion_v42"]["packet"]
        native = {"thread_id": gate.QA, "turn_status": "completed", "message_id": "synthetic-fixture-only",
                  "nonempty": True, "body_sha256": "fixture"}
        outbox = {"department": "qa", "qa_verdict": "pass", "candidate_version": self.packet["candidate_version"],
                  "identity": {"chat_task_id": gate.QA}, "chat_reply": {"message_id": native["message_id"], "body_sha256": "fixture"},
                  "evidence": [pin]}
        report = self.save("qa-report.json", {"synthetic_test_only": True})
        for change in [None, "blocked", "other-candidate", "other-reply", "other-packet"]:
            value = copy.deepcopy(outbox)
            if change == "blocked": value["qa_verdict"] = "blocked"
            if change == "other-candidate": value["candidate_version"] = "old"
            if change == "other-reply": value["chat_reply"]["message_id"] = "other"
            if change == "other-packet": value["evidence"] = []
            self.save("proof.json", {"outbox": self.save("qa-outbox.json", value), "native_reply": native, "report": report})
            self.assertEqual(bool(self.check(self.request("enable-two-new-search"))), change is not None)


if __name__ == "__main__":
    unittest.main()
