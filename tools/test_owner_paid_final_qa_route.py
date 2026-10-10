from __future__ import annotations
import datetime as dt
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import owner_paid_final_qa_route as route


class ExactPaidQaRouteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.patch = patch.object(route, "ROOT", str(self.root))
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.request = {"task_id": route.TASK, "action_id": route.ACTION, "scope": route.SCOPE,
                        "action_class": "thread_message", "sender_department": "paid-growth-data",
                        "source_project_id": route.PROJECT, "target_project_id": route.PROJECT,
                        "target_department": "qa", "target_thread_id": route.TARGET,
                        "target_thread_title": "FLASH CAST｜质检与Reality Checker部｜2026-09",
                        "target_cwd": str(self.root), "target_sidebar_section_id": "section",
                        "review_only": True, "ads_write_allowed": False,
                        "production_authority_granted": False, "payload_path": "message.md",
                        "live_identity_path": "live.json", "native_attempt_receipt_path": "attempt.json",
                        "native_send_receipt_path": "sent.json"}
        raw = "<send_user_message_question_reply>" + json.dumps([
            {"questionItemId": route.QUESTION, "answer": "允许一次准确独立审核"}
        ]) + "</send_user_message_question_reply>"
        self.auth = {"source_thread_id": route.SOURCE, "turn_id": route.AUTH_TURN,
                     "message_id": route.AUTH_MESSAGE, "source_method": "mcp__codex_app__read_thread",
                     "user_message": {"type": "userMessage", "id": route.AUTH_MESSAGE,
                                      "content": [{"type": "text", "text": raw}]}}
        self.request["owner_authorization"] = self.write("auth.json", self.auth)
        self.packet = {"original_task_id": route.TASK, "candidate_version": "paid-final-qa-v39",
                       "account_id": "example-ads-account", "campaign_ids": ["00057225103", "00063878462"],
                       "group_count": 6, "exact_keyword_count": 40, "gross_spend_ceiling_myr": 3000,
                       "frozen_inputs": [self.write("input.json", {"unchanged": True})]}
        self.request["packet"] = self.write("packet.json", self.packet)
        (self.root / "message.md").write_text("one exact review", encoding="utf-8")
        self.request["payload_sha256"] = hashlib.sha256((self.root / "message.md").read_bytes()).hexdigest()
        self.departments = {}
        self.live = {"observed_at": dt.datetime.now(dt.timezone.utc).isoformat(), "threads": [],
                     "sections": [{"name": "装修公司部门", "sectionId": "section", "itemKeys": []}]}
        for did, tid, title in [("paid-growth-data", route.SOURCE, "paid"),
                                ("qa", route.TARGET, self.request["target_thread_title"])]:
            self.departments[did] = {"chat_binding": {"task_id": tid, "project_id": route.PROJECT,
                                                     "cwd": str(self.root), "title": title}}
            self.live["threads"].append({"id": tid, "projectId": route.PROJECT, "cwd": str(self.root),
                                         "title": title, "status": "idle"})
            self.live["sections"][0]["itemKeys"].append("codex:thread:local:" + tid)
        self.write("live.json", self.live)
        self.pin()

    def write(self, name, obj):
        p = self.root / name
        p.write_text(json.dumps(obj), encoding="utf-8")
        return {"path": name, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}

    def pin(self):
        pin = self.write("request.json", self.request)
        self.policy = {"routing_policy": {"source_project_id": route.PROJECT,
                       "source_project_root": str(self.root), "controller_sender_department": "operations",
                       "owner_paid_final_qa": {"status": "approved_single_use", "request_path": pin["path"],
                                               "request_sha256": pin["sha256"]}}, "paid_promotion_enabled": False}

    def check(self, requested=None, healthy=True):
        return route.check(self.root, self.policy, self.departments, requested or self.request,
                           lambda *a, **k: healthy)

    def test_exact_review_passes_without_enabling_paid_gate(self):
        self.assertEqual(self.check(), [])
        self.assertFalse(self.policy["paid_promotion_enabled"])
        self.assertEqual(self.policy["routing_policy"]["controller_sender_department"], "operations")

    def test_all_identity_action_and_payload_mutations_deny(self):
        for key in ["task_id", "action_id", "scope", "action_class", "sender_department", "source_project_id",
                    "target_project_id", "target_department", "target_thread_id", "target_thread_title",
                    "target_cwd", "target_sidebar_section_id", "payload_sha256"]:
            with self.subTest(key=key):
                self.assertTrue(self.check(dict(self.request, **{key: "WRONG"})))

    def test_attempt_and_sent_each_prevent_replay(self):
        for name in ["attempt.json", "sent.json"]:
            with self.subTest(name=name):
                p = self.root / name
                p.write_text("{}")
                self.assertTrue(self.check())
                p.unlink()

    def test_active_stale_or_ambiguous_native_target_denies(self):
        for kind in ["active", "stale", "duplicate_section", "duplicate_target"]:
            live = json.loads(json.dumps(self.live))
            if kind == "active": live["threads"][1]["status"] = "active"
            if kind == "stale": live["observed_at"] = (dt.datetime.now(dt.timezone.utc)-dt.timedelta(minutes=6)).isoformat()
            if kind == "duplicate_section": live["sections"].append(live["sections"][0])
            if kind == "duplicate_target": live["threads"].append(live["threads"][1])
            self.write("live.json", live)
            with self.subTest(kind=kind): self.assertTrue(self.check())

    def test_unhealthy_target_denies(self):
        self.assertTrue(self.check(healthy=False))

    def test_missing_native_human_or_changed_answer_denies(self):
        self.auth["user_message"]["type"] = "agentMessage"
        self.request["owner_authorization"] = self.write("auth.json", self.auth)
        self.pin()
        self.assertTrue(self.check())

    def test_packet_or_source_drift_denies(self):
        (self.root / "input.json").write_text("{}")
        self.assertTrue(self.check())

    def test_expanded_authority_and_outside_path_deny(self):
        self.request["ads_write_allowed"] = True
        self.pin()
        self.assertTrue(self.check())
        self.request["ads_write_allowed"] = False
        self.request["native_send_receipt_path"] = "../escape.json"
        self.pin()
        self.assertTrue(self.check())


class ExactPaidReworkQaRouteTests(ExactPaidQaRouteTests):
    def pin(self):
        super().pin()
        if self.request["scope"] == route.REWORK_SCOPE:
            self.policy["routing_policy"]["owner_paid_final_qa_v40"] = self.policy["routing_policy"].pop("owner_paid_final_qa")

    def setUp(self):
        super().setUp()
        self.request.update(scope=route.REWORK_SCOPE, action_id="send-owner-approved-paid-final-qa-v40")
        message = "example-native-adf7260eec4d7fa4"
        raw = "<send_user_message_question_reply>" + json.dumps([
            {"questionItemId": '["request_user_input_async","call_069fad82e4124364937056ba893db163",0]',
             "answer": "批准降预算及一次定向复验"}
        ]) + "</send_user_message_question_reply>"
        self.auth.update(message_id=message, user_message={"type": "userMessage", "id": message,
                         "content": [{"type": "text", "text": raw}]})
        self.request["owner_authorization"] = self.write("auth.json", self.auth)
        self.packet.update(candidate_version="paid-final-qa-v39-rework1", total_ad_fee_each_myr=1350,
                           dates_myt=["2026-10-08", "2026-10-14"], hours_myt="MON-SUN10:00-22:00",
                           shop_hours_unchanged=True, review_only=True)
        self.request["packet"] = self.write("packet.json", self.packet)
        self.pin()

    def test_rework_expanded_budget_dates_hours_or_scope_deny(self):
        for field, wrong in [("total_ad_fee_each_myr", 1388.88), ("dates_myt", ["2026-10-09", "2026-10-15"]),
                             ("hours_myt", "ALL_DAY"), ("review_only", False), ("shop_hours_unchanged", False)]:
            packet = dict(self.packet, **{field: wrong})
            self.request["packet"] = self.write("packet.json", packet)
            self.pin()
            with self.subTest(field=field):
                self.assertTrue(self.check())

    def test_original_one_use_authorization_cannot_approve_rework(self):
        self.auth["message_id"] = route.AUTH_MESSAGE
        self.request["owner_authorization"] = self.write("auth.json", self.auth)
        self.pin()
        self.assertTrue(self.check())


if __name__ == "__main__":
    unittest.main()
