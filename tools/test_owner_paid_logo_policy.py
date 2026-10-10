"""Synthetic unit tests only; never independent QA or Ads execution evidence."""
import copy
import datetime as dt
import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import owner_paid_logo_policy as gate


class LogoChannelTests(unittest.TestCase):
    def setUp(self):
        # Rebuildable test output remains inside this owning project.
        runtime = Path(os.environ.get("FLASHCAST_TEST_RUNTIME", Path(__file__).resolve().parents[1] / "test-runtime"))
        runtime.mkdir(parents=True, exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(prefix="logo-policy-test-", dir=runtime)
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        p = patch.object(gate, "ROOT", str(self.root)); p.start(); self.addCleanup(p.stop)
        self.departments = {did: {"approved_subskills": ["google-ads-renovation-ppc"], "chat_binding": {
            "task_id": tid, "project_id": gate.PROJECT, "cwd": str(self.root), "title": did}}
            for did, tid in [("paid-growth-data", gate.SOURCE), ("qa", gate.QA)]}
        self.live = {"source_method": "mcp__codex_app__list_threads",
                     "observed_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                     "threads": [{"id": tid, "projectId": gate.PROJECT, "cwd": str(self.root),
                                  "title": did, "status": "idle"}
                                 for did, tid in [("paid-growth-data", gate.SOURCE), ("qa", gate.QA)]],
                     "sections": [{"name": "装修公司部门", "sectionId": "fixture",
                                   "itemKeys": ["codex:thread:local:" + gate.SOURCE, "codex:thread:local:" + gate.QA]}]}
        self.save("live.json", self.live)
        auth = {"source_method": "mcp__codex_app__read_thread", "source_thread_id": gate.SOURCE,
                "turn_id": gate.AUTH_TURN, "message": {"id": gate.AUTH_MESSAGE, "type": "userMessage",
                "content": [{"text": "FLASH CAST｜质检与Reality Checker部｜2026-09 仅两套新系列Logo关联 批准执行"}]}}
        self.candidate = {"task_id": gate.TASK, "scope": gate.LOGO_SCOPE,
                          "targets": [{"id": c} for c in gate.CAMPAIGNS],
                          "asset": {"id": gate.ASSET, "dimensions": "512x512"},
                          "association_level": "CAMPAIGN_ONLY", "unchanged": gate.UNCHANGED}
        self.packet = {"original_task_id": gate.TASK, "candidate_version": gate.VERSION,
                       "account_id": "example-ads-account", "campaign_ids": gate.CAMPAIGNS,
                       "asset_id": gate.ASSET, "association_level": "CAMPAIGN_ONLY", "unchanged": gate.UNCHANGED,
                       "owner_authorization": self.save("auth.json", auth),
                       "logo_candidate": self.save("candidate.json", self.candidate),
                       "frozen_inputs": [], "live_identity_path": "live.json", "final_qa_proof_path": "proof.json",
                       "actions": {"review": {"payload": self.save_text("review.md", "Exact Logo review only\n"),
                                               "attempt_path": "review-attempt.json"},
                                   "associate": {"payload": self.save("associate.json", {
                                       "action": "associate_existing_business_logo", "account_id": "example-ads-account",
                                       "campaign_ids": gate.CAMPAIGNS, "asset_id": gate.ASSET,
                                       "association_level": "CAMPAIGN_ONLY", "unchanged": gate.UNCHANGED}),
                                                 "attempt_path": "associate-attempt.json"}}}
        self.policy = {"paid_promotion_enabled": False,
                       "routing_policy": {"source_project_id": gate.PROJECT, "source_project_root": str(self.root)},
                       "owner_paid_logo_v1": {"status": "owner_approved_exact_logo_channel",
                       "global_paid_gate_unchanged": True, "unrelated_ads_or_payment_authority": False}}
        historical = self.save(gate.HISTORICAL_QA1_BLOCKED_PIN["path"], {"qa_verdict": "blocked", "synthetic": True})
        p = patch.object(gate, "HISTORICAL_QA1_BLOCKED_PIN", historical); p.start(); self.addCleanup(p.stop)
        self.refresh()

    def save_text(self, name, text):
        p = self.root / name; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(text, encoding="utf-8")
        return {"path": name, "sha256": hashlib.sha256(p.read_bytes()).hexdigest(), "size": p.stat().st_size}

    def save(self, name, value):
        return self.save_text(name, json.dumps(value, ensure_ascii=False))

    def refresh(self):
        self.policy["owner_paid_logo_v1"]["packet"] = self.save("packet.json", self.packet)

    def request(self, key="review"):
        cls, aid, dept, tid = gate.ACTIONS[key]
        return {"task_id": gate.TASK, "department": "paid-growth-data", "action_id": aid, "action_class": cls,
                "scope": gate.PREFIX + key, "skill": "google-ads-renovation-ppc", "consume_approval": True,
                "source_project_id": gate.PROJECT, "target_project_id": gate.PROJECT,
                "target_department": dept, "target_thread_id": tid, "target_thread_title": dept,
                "target_cwd": str(self.root), "target_sidebar_section_id": "fixture",
                "payload_sha256": self.packet["actions"][key]["payload"]["sha256"]}

    def check(self, request=None, healthy=True):
        return gate.check(self.root, self.policy, self.departments, request or self.request(), lambda *a, **k: healthy)

    def qa_proof(self, change=None):
        text = "PASS narrow two-campaign official Logo only\n"
        native = {"thread_id": gate.QA, "turn": {"id": "synthetic-only", "status": "completed", "items": [
            {"id": "request", "type": "userMessage", "content": [{"text": "Exact Logo review only\n"}]},
            {"id": "reply", "type": "agentMessage", "text": text}]}}
        outbox = {"task_id": gate.TASK, "department": "qa", "qa_verdict": "pass", "candidate_version": gate.VERSION,
                  "identity": {"chat_task_id": gate.QA},
                  "chat_reply": {"message_id": "reply", "body_sha256": hashlib.sha256(text.encode()).hexdigest()},
                  "evidence": [self.policy["owner_paid_logo_v1"]["packet"]]}
        if change == "self": native["thread_id"] = gate.SOURCE
        if change == "active": native["turn"]["status"] = "inProgress"
        if change == "other-request": native["turn"]["items"][0]["content"][0]["text"] = "other"
        if change == "blocked": outbox["qa_verdict"] = "blocked"
        if change == "other-candidate": outbox["candidate_version"] = "old"
        if change == "other-packet": outbox["evidence"] = []
        if change == "forged-reply": outbox["chat_reply"]["body_sha256"] = "0" * 64
        proof = {"source_method": "mcp__codex_app__read_thread", "message_id": "reply",
                 "native_turn": self.save("native.json", native), "outbox": self.save("outbox.json", outbox),
                 "report": self.save_text("report.md", "Synthetic fixture only\n")}
        dep = {"schema_version": 1, "kind": "owner_paid_logo.final_qa_evidence.v1",
               "proof_format": "legacy_wrapper.v1", "proof": self.save("proof.json", proof),
               "outbox": proof["outbox"], "report": proof["report"],
               "native_observation": {"schema_version": 1, "format": "read_thread.turn.v1",
                                      "pin": proof["native_turn"], "message_id": "reply"}}
        self.policy["owner_paid_logo_v1"]["final_qa_evidence"] = self.save("final-dependency.json", dep)
        self.technical_qa2()

    def technical_qa2(self):
        """Actual plan/receipt formats with fictitious R0 identities; never real QA."""
        import workflow_control as w
        import qa_review_plan as q
        for did in ("qa-technical", "operations", "operations-assistant"):
            self.departments[did] = {"id": did, "chat_binding": {"task_id": "fixed-" + did,
                "project_id": gate.PROJECT, "cwd": str(self.root), "title": did}}
        for did, value in self.departments.items(): value["id"] = did
        self.save("data/department-registry.json", {"departments": list(self.departments.values())})
        sources = [self.save_text("tools/owner_paid_logo_policy.py", Path(gate.__file__).read_text()),
                   self.save_text("tools/workflow_control.py", Path(w.__file__).read_text())]
        control = self.save("control.json", {"task_id": gate.TASK, "candidate_version": "original-control-v1",
            "action_class": "internal_control_candidate", "scope": gate.CONTROL_SCOPE, "risk_level": "R0"})
        rule = self.policy["owner_paid_logo_v1"]
        technical = {"schema_version": 1, "task_id": "synthetic-logo-control-001", "department": "operations-assistant",
            "candidate_version": "synthetic-current-control-v3", "action_id": "review-synthetic-logo-control-v3",
            "action_class": "internal_control_candidate", "scope": "project:synthetic-logo-control:exact-v3",
            "source_business_task_id": gate.TASK, "source_candidate_version": "original-control-v1",
            "source_candidate": control, "frozen_sources": sources + [rule["packet"], control]}
        candidate_pin = self.save("technical-candidate.json", technical)
        self.plan = {**{k: technical[k] for k in gate.IDENTITY[:-1]}, "schema_version": 1,
            "candidate_sha256": candidate_pin["sha256"], "candidate": candidate_pin,
            "producer_department": "operations-assistant", "reviewer_department": "qa-technical",
            "reviewer_thread_id": "fixed-qa-technical", "controller_department": "operations",
            "controller_thread_id": "fixed-operations", "single_final_reviewer": True, "risk_level": "R0",
            "production_write_allowed": False, "external_permission_issued": False}
        plan_pin = self.save("review-plan.json", self.plan)
        identity = {k: self.plan[k] for k in gate.IDENTITY}
        request_payload = self.save_text("technical-request.md", "Synthetic exact technical QA2 request\n")
        request = {"candidate": candidate_pin, "review_plan": plan_pin, "review_identity": identity,
            "request_payload": request_payload,
            "reviewer_department": "qa-technical", "reviewer_thread_id": "fixed-qa-technical",
            "source_business_task_id": gate.TASK, "source_candidate_version": "original-control-v1",
            "minimum_review_sources": sources}
        request_pin = self.save("technical-request.json", request)
        snapshot = {"task_id": technical["task_id"], "owner_approval_required": False,
            "departments": [{"department": d, "chat_task_id": "fixed-" + d}
                            for d in ("operations-assistant", "qa-technical")],
            "qa_review_plan": {"pin": plan_pin, "reviewer_department": "qa-technical"}}
        self.save("data/workflows/" + technical["task_id"] + ".json", snapshot)
        event = {"task_id": technical["task_id"], "state": "planned", "previous_event_hash": "",
                 "details": {"departments": snapshot["departments"], "qa_review_plan_bound": snapshot["qa_review_plan"]}}
        event["event_hash"] = w.sha256_value(event)
        self.save_text("logs/workflow-events.jsonl", json.dumps(event) + "\n")
        text = "Synthetic QA2 control PASS only; no external authority. 中文\n"
        native_pin = self.save("technical-native.json", {"source_method": "mcp__codex_app__read_thread",
            "thread_id": "fixed-qa-technical", "turn_id": "synthetic-qa2-turn", "turn_status": "completed",
            "result_message": {"type": "agentMessage", "id": "msg_synthetic-qa2", "text": text, "phase": "commentary"}})
        native_request = {"schema_version": 1, "format": "read_thread.userMessage.v1", "message_id": "synthetic-qa2-request",
            "pin": self.save("technical-native-request.json", {"thread_id": "fixed-qa-technical",
                "turn": {"id": "synthetic-qa2-turn", "status": "completed", "items": [{"id": "synthetic-qa2-request",
                "type": "userMessage", "content": [{"text": "Synthetic exact technical QA2 request\n"}]}]}})}
        reply = {"message_id": "msg_synthetic-qa2", "turn_id": "synthetic-qa2-turn", "ref": "msg_synthetic-qa2",
                 "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(), "nonempty": True,
                 "in_current_fixed_department_chat": True}
        self.tech_box = {"schema_version": "2.0", **{k: self.plan[k] for k in gate.IDENTITY[:-1]},
            "department": "qa-technical", "fixed_chat_task_id": "fixed-qa-technical", "status": "completed",
            "conclusion": "Synthetic fixture only", "evidence": [candidate_pin, plan_pin, request_pin, rule["packet"], request_payload] + sources,
            "risks": [], "next_actions": [], "handoff": {"receiver": "operations"}, "approval_required": False,
            "learning": {"status": "no_new_learning"}, "risk_level": "R0", "review_identity": identity,
            "production_write_allowed": False, "external_permission_issued": False, "production_release_eligible": False,
            "qa_verdict": "pass", "chat_reply": reply}
        box_pin = self.save("technical-outbox.json", self.tech_box)
        producer_pin = self.save("technical-producer.json", {"candidate_version": technical["candidate_version"],
                                                             "evidence": [candidate_pin]})
        stamp = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=30)).isoformat()
        self.receipts = []
        for kind, department, rid, evidence in [
            ("outbox_received", "operations-assistant", "producer", [producer_pin]),
            ("dispatch_sent", "qa-technical", "dispatch", [plan_pin, candidate_pin, request_payload, request_pin]),
            ("chat_ack", "qa-technical", "ack", []),
            ("outbox_received", "qa-technical", "box", [box_pin]),
            ("qa_verdict", "qa-technical", "verdict", [box_pin])]:
            row = {"receipt_id": rid, "task_id": technical["task_id"], "department": department,
                "chat_task_id": "fixed-" + department, "receipt_type": kind, "created_at": stamp, "evidence": evidence,
                "action_id": self.plan["action_id"], "action_class": self.plan["action_class"], "scope": self.plan["scope"]}
            if kind == "chat_ack": row["ack_nonempty"] = True
            if kind == "qa_verdict": row["verdict"] = "pass"
            self.receipts.append(row)
        self.write_receipts()
        self.tech_dep = {"schema_version": 1, "kind": "owner_paid_logo.technical_qa2.v1", "review_identity": identity,
            "candidate": candidate_pin, "review_plan": plan_pin, "technical_request": request_pin,
            "logo_packet": rule["packet"], "consumer_source_pins": sources, "outbox": box_pin,
            "outbox_receipt_id": "box", "verdict_receipt_id": "verdict",
            "request_payload": request_payload, "native_request": native_request,
            "native_observation": {"schema_version": 1, "format": "read_thread.completed-result.v1", "pin": native_pin}}
        rule["technical_qa2"] = self.save("technical-dependency.json", self.tech_dep)
        # This assertion verifies the fixture uses the real validators, with no validator mocks.
        self.assertEqual(w._validate_receipt_chain(self.root, technical["task_id"])[1], [])
        self.assertEqual(w.validate_workflow_events(self.root, technical["task_id"]), [])

    def write_receipts(self):
        import workflow_control as w
        previous = ""
        for row in self.receipts:
            row["previous_hash"] = previous
            row["receipt_hash"] = w.sha256_value(w._receipt_payload_for_hash(row))
            previous = row["receipt_hash"]
        self.save_text("logs/receipts/" + self.plan["task_id"] + ".jsonl",
                       "".join(json.dumps(row) + "\n" for row in self.receipts))

    def test_review_only_does_not_allow_missing_qa_save(self):
        self.assertEqual(self.check(), [])
        self.assertTrue(self.check(self.request("associate")))
        self.assertFalse(self.policy["paid_promotion_enabled"])

    def test_exact_independent_qa_required(self):
        for change in [None, "self", "active", "other-request", "blocked", "other-candidate", "other-packet", "forged-reply"]:
            with self.subTest(change=change):
                self.qa_proof(change)
                self.assertEqual(bool(self.check(self.request("associate"))), change is not None)

    def test_no_other_action_account_route_or_skill(self):
        for key, value in [("scope", "owner_paid_logo:other:v1:review"), ("scope", gate.PREFIX + "enable"),
                           ("department", "operations"), ("action_id", "payment"), ("action_class", "ads_write"),
                           ("target_thread_id", "other"), ("target_project_id", "other"),
                           ("skill", "other"), ("payload_sha256", "0" * 64)]:
            with self.subTest(key=key, value=value):
                request = self.request(); request[key] = value; self.assertTrue(self.check(request))

    def test_scope_cannot_expand_to_old_campaign_or_asset_or_budget(self):
        original = copy.deepcopy(self.packet)
        for key, value in [("campaign_ids", ["00074720157", "00063878462"]), ("asset_id", "000429069271"),
                           ("association_level", "ACCOUNT"), ("unchanged", [])]:
            with self.subTest(key=key):
                self.packet = copy.deepcopy(original); self.packet[key] = value; self.refresh()
                self.assertTrue(self.check())

    def test_native_stale_active_duplicate_missing_and_health(self):
        for change in ["stale", "active", "duplicate", "missing", "section"]:
            live = copy.deepcopy(self.live)
            if change == "stale": live["observed_at"] = "2026-10-01T00:00:00Z"
            if change == "active": live["threads"][1]["status"] = "active"
            if change == "duplicate": live["threads"].append(live["threads"][1])
            if change == "missing": live["threads"].pop()
            if change == "section": live["sections"][0]["itemKeys"] = []
            self.save("live.json", live); self.assertTrue(self.check(), change)
        self.save("live.json", self.live); self.assertTrue(self.check(healthy=False))

    def test_replay_pin_drift_and_unconsumed_denied(self):
        self.qa_proof()
        r = self.request("associate"); r["consume_approval"] = False; self.assertTrue(self.check(r))
        self.save("review-attempt.json", {"attempted": True}); self.assertTrue(self.check())
        self.save("associate-attempt.json", {"attempted": True}); self.assertTrue(self.check(self.request("associate")))
        self.save("candidate.json", {"changed": True}); self.assertTrue(self.check())

    def update_technical_box(self):
        box_pin = self.save("technical-outbox.json", self.tech_box)
        self.tech_dep["outbox"] = box_pin
        for row in self.receipts:
            if row["receipt_type"] in ("outbox_received", "qa_verdict") and row["department"] == "qa-technical":
                row["evidence"] = [box_pin]
        self.write_receipts()
        self.policy["owner_paid_logo_v1"]["technical_qa2"] = self.save("technical-dependency.json", self.tech_dep)

    def actual_logo_proof(self, *, local=False, blocked=False):
        self.qa_proof()
        text = "Synthetic final Logo result, 中文。\n"
        mid = "msg_synthetic-final"
        native = {"source_method": "mcp__codex_app__read_thread", "thread_id": gate.QA,
                  "turn_id": "synthetic-final-turn", "turn_status": "completed",
                  "result_message": {"type": "agentMessage", "id": mid, "text": text, "phase": "commentary"}}
        descriptor = {"schema_version": 1, "format": "read_thread.completed-result.v1",
                      "pin": self.save("actual-native.json", native)}
        chat = {"message_id": mid, "turn_id": native["turn_id"], "sha256": hashlib.sha256(text.encode()).hexdigest(),
                "nonempty": True, "in_current_fixed_department_chat": True, "body_stored": False}
        identity = {"task_id": gate.TASK, "department": "qa", "fixed_chat_task_id": gate.QA,
                    "candidate_version": gate.VERSION, "candidate_sha256": self.packet["logo_candidate"]["sha256"],
                    "action_id": gate.ACTIONS["associate"][1], "action_class": "ads_write", "scope": gate.LOGO_SCOPE}
        proof = {**identity, "schema_version": "flashcast-qa-proof/1", "result": "BLOCKED" if blocked else "PASS",
                 "qa_verdict": "blocked" if blocked else "pass", "chat_reply": chat,
                 "frozen_inputs_verified": [self.policy["owner_paid_logo_v1"]["packet"]]}
        box = {**identity, "schema_version": "department-outbox/2", "status": "blocked" if blocked else "completed",
               "qa_verdict": proof["qa_verdict"], "chat_reply": chat,
               "evidence": [self.policy["owner_paid_logo_v1"]["packet"], self.packet["actions"]["review"]["payload"]]}
        request_descriptor = {"schema_version": 1, "format": "read_thread.userMessage.v1", "message_id": "synthetic-final-request",
            "pin": self.save("actual-native-request.json", {"thread_id": gate.QA,
                "turn": {"id": native["turn_id"], "items": [{"id": "synthetic-final-request", "type": "userMessage",
                    "content": [{"text": "Exact Logo review only\n"}]}]}})}
        if local:
            session_root = self.root / "sessions"; session_root.mkdir()
            p = patch.object(gate, "SESSION_ROOT", session_root); p.start(); self.addCleanup(p.stop)
            rows = [{"type": "session_meta", "payload": {"id": gate.QA, "cwd": str(self.root)}},
                    {"type": "turn_context", "payload": {"turn_id": native["turn_id"], "cwd": str(self.root)}},
                    {"type": "response_item", "payload": {"type": "message", "id": "msg_synthetic-final-request", "role": "user",
                     "content": [{"type": "input_text", "text": "Exact Logo review only\n"}]}},
                    {"type": "event_msg", "payload": {"type": "item_completed", "turn_id": native["turn_id"]}},
                    {"type": "response_item", "payload": {"type": "message", "id": mid, "role": "assistant",
                     "content": [{"type": "output_text", "text": text}], "phase": "commentary"}}]
            self.save_text("sessions/synthetic.jsonl", "".join(json.dumps(r) + "\n" for r in rows))
            provenance = {"schema_version": 1, "rows": [{"kind": "logo_qa1_reply", "thread_id": gate.QA,
                "turn_id": native["turn_id"], "message_id": mid, "session_path": str(session_root / "synthetic.jsonl"),
                "exact_turn_context": [{"line": 2, "turn_id": native["turn_id"], "cwd": str(self.root)}],
                "expected_sha256": chat["sha256"], "native_message": {"line": 5,
                "local_response_item_message_id": mid, "sha256": chat["sha256"], "utf8_bytes": len(text.encode())}}]}
            descriptor = {"schema_version": 1, "format": "local_session.response_item.v1", "kind": "logo_qa1_reply",
                          "pin": self.save("provenance.json", provenance), "completion": descriptor}
            request_descriptor = {"schema_version": 1, "format": "local_session.user_message.v1", "line": 3,
                "source_path": str(session_root / "synthetic.jsonl"), "message_id": "msg_synthetic-final-request"}
        dep = {"schema_version": 1, "kind": "owner_paid_logo.final_qa_evidence.v1", "proof_format": "logo_result.v1",
               "proof": self.save("proof.json", proof), "outbox": self.save("actual-outbox.json", box),
               "report": self.save_text("report.md", "Synthetic final result only\n"), "native_observation": descriptor,
               "native_request": request_descriptor}
        self.policy["owner_paid_logo_v1"]["final_qa_evidence"] = self.save("final-dependency.json", dep)
        return dep, proof, box

    def test_missing_technical_result_status_alone_never_admits(self):
        self.qa_proof()
        self.policy["owner_paid_logo_v1"].pop("technical_qa2")
        self.assertTrue(self.check(self.request("associate")))
        self.policy["owner_paid_logo_v1"]["technical_qa2"] = self.save("technical-dependency.json", {"status": "pass"})
        self.assertTrue(self.check(self.request("associate")))

    def test_technical_identity_and_current_sources_are_exact(self):
        for field in gate.IDENTITY:
            with self.subTest(field=field):
                self.qa_proof(); self.tech_dep["review_identity"][field] = "unrelated"
                self.policy["owner_paid_logo_v1"]["technical_qa2"] = self.save("technical-dependency.json", self.tech_dep)
                self.assertTrue(self.check(self.request("associate")))
        for field, value in [("logo_packet", self.save("unrelated.json", {})),
                             ("outbox_receipt_id", "old-box"), ("verdict_receipt_id", "old-verdict")]:
            with self.subTest(field=field):
                self.qa_proof(); self.tech_dep[field] = value
                self.policy["owner_paid_logo_v1"]["technical_qa2"] = self.save("technical-dependency.json", self.tech_dep)
                self.assertTrue(self.check(self.request("associate")))
        self.qa_proof(); self.save_text("tools/owner_paid_logo_policy.py", "unrelated source\n")
        self.assertTrue(self.check(self.request("associate")))

    def test_technical_blocked_stale_reply_and_missing_evidence_refuse(self):
        for change in ("blocked", "digest", "reviewer", "packet", "candidate", "plan", "request", "sources"):
            with self.subTest(change=change):
                self.qa_proof()
                if change == "blocked":
                    self.tech_box.update(status="blocked", qa_verdict="blocked"); self.receipts[-1]["verdict"] = "blocked"
                elif change == "digest": self.tech_box["chat_reply"]["sha256"] = "0" * 64
                elif change == "reviewer": self.tech_box["fixed_chat_task_id"] = gate.QA
                else:
                    pin = {"packet": self.tech_dep["logo_packet"], "candidate": self.tech_dep["candidate"],
                           "plan": self.tech_dep["review_plan"], "request": self.tech_dep["technical_request"],
                           "sources": self.tech_dep["consumer_source_pins"][0]}[change]
                    self.tech_box["evidence"].remove(pin)
                self.update_technical_box()
                self.assertTrue(self.check(self.request("associate")))

    def test_technical_receipt_and_plan_tampering_and_later_block_refuse(self):
        for change in ("chain", "future", "missing-ack", "changed-plan", "later-block", "later-dispatch", "later-ack", "later-failed"):
            with self.subTest(change=change):
                self.qa_proof()
                if change == "chain":
                    p = self.root / "logs/receipts" / (self.plan["task_id"] + ".jsonl")
                    p.write_text(p.read_text().replace('"previous_hash": ""', '"previous_hash": "tampered"', 1))
                elif change == "changed-plan": self.save("review-plan.json", {"changed": True})
                else:
                    if change == "future": self.receipts[-1]["created_at"] = "2999-01-01T00:00:00Z"
                    if change == "missing-ack": self.receipts = [r for r in self.receipts if r["receipt_type"] != "chat_ack"]
                    if change == "later-block":
                        later = copy.deepcopy(self.receipts[-1]); later.update(receipt_id="later-block", verdict="blocked")
                        self.receipts.append(later)
                    if change == "later-dispatch":
                        later = copy.deepcopy(self.receipts[1]); later.update(receipt_id="new-dispatch")
                        self.receipts.append(later)
                    if change in ("later-ack", "later-failed"):
                        later = copy.deepcopy(self.receipts[2] if change == "later-ack" else self.receipts[1])
                        later.update(receipt_id=change, receipt_type="chat_ack" if change == "later-ack" else "dispatch_failed")
                        self.receipts.append(later)
                    self.write_receipts()
                self.assertTrue(self.check(self.request("associate")))

    def test_actual_completed_result_format_can_pass_synthetic_chain(self):
        self.actual_logo_proof()
        self.assertEqual(self.check(self.request("associate")), [])

    def test_actual_blocked_proof_is_preserved_and_no_successor_fallback(self):
        dep, proof, box = self.actual_logo_proof(blocked=True)
        self.assertTrue(self.check(self.request("associate")))
        self.save("review-attempt.json", {"attempted": True})
        self.assertTrue(self.check())
        # An alternate passing file cannot replace the immutable packet's old proof path.
        proof.update(result="PASS", qa_verdict="pass"); box.update(status="completed", qa_verdict="pass")
        dep["proof"] = self.save("alternate-proof.json", proof); dep["outbox"] = self.save("alternate-outbox.json", box)
        self.policy["owner_paid_logo_v1"]["final_qa_evidence"] = self.save("final-dependency.json", dep)
        self.assertTrue(self.check(self.request("associate")))

    def test_local_response_item_reads_raw_utf8_and_own_namespace(self):
        self.actual_logo_proof(local=True)
        self.assertEqual(self.check(self.request("associate")), [])
        p = self.root / "sessions/synthetic.jsonl"
        # Even a whitespace-only mutation of the raw assistant reply is refused.
        p.write_text(p.read_text().replace("Synthetic final Logo result", "Synthetic final Logo result "))
        self.assertTrue(self.check(self.request("associate")))

    def test_local_app_uuid_and_turn_context_are_not_invented(self):
        for change in ("app-uuid", "context", "completion", "wrong-line", "unsupported-version"):
            with self.subTest(change=change):
                # Remove only the earlier synthetic fixture directory before reusing this test case.
                if (self.root / "sessions").exists():
                    for p in (self.root / "sessions").iterdir(): p.unlink()
                    (self.root / "sessions").rmdir()
                dep, proof, box = self.actual_logo_proof(local=True)
                if change == "app-uuid":
                    box["chat_reply"]["message_id"] = "synthetic-final"
                    dep["outbox"] = self.save("actual-outbox.json", box)
                elif change == "context":
                    p = self.root / "sessions/synthetic.jsonl"
                    rows = [json.loads(line) for line in p.read_text().splitlines()]
                    rows[1]["payload"]["turn_id"] = "other-turn"
                    p.write_text("".join(json.dumps(r) + "\n" for r in rows))
                elif change == "completion": dep["native_observation"].pop("completion")
                elif change == "unsupported-version": dep["native_observation"]["schema_version"] = 2
                else:
                    provenance = json.loads((self.root / "provenance.json").read_text())
                    provenance["rows"][0]["native_message"]["line"] = 3
                    dep["native_observation"]["pin"] = self.save("provenance.json", provenance)
                self.policy["owner_paid_logo_v1"]["final_qa_evidence"] = self.save("final-dependency.json", dep)
                self.assertTrue(self.check(self.request("associate")))

    def test_unknown_native_shape_and_boolean_claims_do_not_authenticate(self):
        self.qa_proof()
        self.tech_dep["native_observation"] = {"schema_version": 1, "format": "caller-claims-native",
                                               "authentic": True, "completed": True}
        self.policy["owner_paid_logo_v1"]["technical_qa2"] = self.save("technical-dependency.json", self.tech_dep)
        self.assertTrue(self.check(self.request("associate")))

    def test_native_technical_request_must_match_approved_payload(self):
        for change in ("missing", "text", "type", "identity", "payload-pin", "dispatch-pin"):
            with self.subTest(change=change):
                self.qa_proof()
                descriptor = self.tech_dep["native_request"]
                native = json.loads((self.root / descriptor["pin"]["path"]).read_text())
                if change == "missing": self.tech_dep.pop("native_request")
                elif change in ("text", "type", "identity"):
                    item = native["turn"]["items"][0]
                    if change == "text": item["content"][0]["text"] = "Unrelated review\n"
                    if change == "type": item["content"][0]["type"] = "image"
                    if change == "identity": native["turn"]["id"] = "unrelated-turn"
                    descriptor["pin"] = self.save(descriptor["pin"]["path"], native)
                elif change == "payload-pin":
                    request = json.loads((self.root / "technical-request.json").read_text())
                    request["request_payload"] = self.save_text("other.md", "Other request\n")
                    self.tech_dep["technical_request"] = self.save("technical-request.json", request)
                else:
                    self.receipts[1]["evidence"].remove(self.tech_dep["technical_request"])
                    self.write_receipts()
                self.policy["owner_paid_logo_v1"]["technical_qa2"] = self.save("technical-dependency.json", self.tech_dep)
                self.assertTrue(self.check(self.request("associate")))

    def test_native_final_request_text_type_and_identity_must_match(self):
        for change in ("missing", "text", "type", "identity", "extra-text"):
            with self.subTest(change=change):
                dep, _, _ = self.actual_logo_proof()
                if change == "missing": dep.pop("native_request")
                else:
                    descriptor = dep["native_request"]
                    native = json.loads((self.root / descriptor["pin"]["path"]).read_text())
                    item = native["turn"]["items"][0]
                    if change == "text": item["content"][0]["text"] = "Unrelated final review\n"
                    if change == "type": item["content"][0]["type"] = "image"
                    if change == "identity": native["thread_id"] = gate.SOURCE
                    if change == "extra-text": item["content"].append({"text": "Unrelated extra request"})
                    descriptor["pin"] = self.save(descriptor["pin"]["path"], native)
                self.policy["owner_paid_logo_v1"]["final_qa_evidence"] = self.save("final-dependency.json", dep)
                self.assertTrue(self.check(self.request("associate")))

    def test_historical_blocked_pin_cannot_be_relabelled_pass(self):
        self.actual_logo_proof()
        self.save(gate.HISTORICAL_QA1_BLOCKED_PIN["path"], {"qa_verdict": "pass", "synthetic": True})
        reasons = self.check(self.request("associate"))
        self.assertIn("owner_paid_logo_denied:frozen_pin_changed", reasons)

    def test_old_review_attempt_cannot_move_to_a_fresh_path(self):
        self.save(gate.HISTORICAL_REVIEW_ATTEMPT_PATH, {"attempted": True, "synthetic": True})
        self.packet["actions"]["review"]["attempt_path"] = "fresh-attempt.json"
        self.refresh()
        self.assertIn("owner_paid_logo_denied:single_use_attempt_already_recorded", self.check())

    def test_owner_deadline_and_candidate_scope_stay_closed(self):
        real_datetime = dt.datetime
        class Expired(real_datetime):
            @classmethod
            def now(cls, tz=None): return cls(2026, 10, 14, 14, 0, 1, tzinfo=dt.timezone.utc)
        with patch.object(gate.dt, "datetime", Expired): self.assertTrue(self.check())
        self.candidate["asset"]["dimensions"] = "1024x1024"
        self.packet["logo_candidate"] = self.save("candidate.json", self.candidate); self.refresh()
        self.assertTrue(self.check())


    def native_tool_fixture(self):
        """Fictitious local/app observations and same original validators; no real send."""
        self.qa_proof()
        import workflow_control as w
        old_plan = self.tech_dep["review_plan"]
        old_request = self.tech_dep["technical_request"]
        for role, tid in (("operations", gate.HEADQUARTERS), ("qa-technical", gate.QA_TECHNICAL)):
            self.departments[role]["chat_binding"]["task_id"] = tid
        self.save("data/department-registry.json", {"departments": list(self.departments.values())})
        self.plan.update(controller_thread_id=gate.HEADQUARTERS, reviewer_thread_id=gate.QA_TECHNICAL)
        new_plan = self.save("review-plan.json", self.plan)
        self.tech_dep["review_plan"] = new_plan
        req = json.loads((self.root / "technical-request.json").read_text())
        req.update(review_plan=new_plan, reviewer_thread_id=gate.QA_TECHNICAL)
        new_request = self.save("technical-request.json", req)
        self.tech_dep["technical_request"] = new_request
        snapshot_path = "data/workflows/" + self.plan["task_id"] + ".json"
        snapshot = json.loads((self.root / snapshot_path).read_text())
        snapshot["qa_review_plan"]["pin"] = new_plan
        for row in snapshot["departments"]:
            if row["department"] == "qa-technical": row["chat_task_id"] = gate.QA_TECHNICAL
        self.save(snapshot_path, snapshot)
        event = {"task_id": self.plan["task_id"], "state": "planned", "previous_event_hash": "",
                 "details": {"departments": snapshot["departments"], "qa_review_plan_bound": snapshot["qa_review_plan"]}}
        event["event_hash"] = w.sha256_value(event)
        self.save_text("logs/workflow-events.jsonl", json.dumps(event) + "\n")
        for row in self.receipts:
            if row["department"] == "qa-technical": row["chat_task_id"] = gate.QA_TECHNICAL
            row["evidence"] = [new_plan if v == old_plan else new_request if v == old_request else v for v in row["evidence"]]
        self.tech_box["fixed_chat_task_id"] = gate.QA_TECHNICAL
        self.tech_box["evidence"] = [new_plan if v == old_plan else new_request if v == old_request else v for v in self.tech_box["evidence"]]
        reply_native = json.loads((self.root / "technical-native.json").read_text())
        reply_native["thread_id"] = gate.QA_TECHNICAL
        self.tech_dep["native_observation"]["pin"] = self.save("technical-native.json", reply_native)
        session_root = self.root / "native-tool-session"; session_root.mkdir(exist_ok=True)
        patcher = patch.object(gate, "SESSION_ROOT", session_root); patcher.start(); self.addCleanup(patcher.stop)
        inner = (self.root / self.tech_dep["request_payload"]["path"]).read_text()
        self.tool_raw = "<codex_delegation>\n  <source_thread_id>" + gate.HEADQUARTERS + "</source_thread_id>\n  <input>" + inner + "</input>\n</codex_delegation>"
        now = dt.datetime.now(dt.timezone.utc)
        self.tool_app = {"schema_version": 1, "source_method": "mcp__codex_app__read_thread",
            "thread_id": gate.QA_TECHNICAL, "turn": {"id": reply_native["turn_id"], "status": "completed", "items": [{
            "type": "functionCallOutput", "id": "fco_synthetic-tool", "name": "send_message_to_thread",
            "namespace": "codex_app", "output": {"text": self.tool_raw, "truncated": False}}]}}
        self.tool_local_rows = [{"type": "session_meta", "payload": {"id": gate.QA_TECHNICAL, "cwd": str(self.root)}},
            {"type": "turn_context", "payload": {"turn_id": reply_native["turn_id"], "cwd": str(self.root)}},
            {"type": "response_item", "payload": {"type": "function_call_output", "id": "fco_synthetic-tool",
             "name": "send_message_to_thread", "namespace": "codex_app", "output": self.tool_raw,
             "internal_chat_message_metadata_passthrough": {"turn_id": reply_native["turn_id"], "create_time": (now-dt.timedelta(seconds=35)).timestamp()},}, "metadata": {"client_authored": False, "sender_user_messages": {"receiver_turn_id": reply_native["turn_id"], "receiver_message_id": "fco_synthetic-tool"}}}]
        self.tool_descriptor = {"schema_version": 1, "format": gate.TOOL_REQUEST_FORMAT,
            "source_thread_id": gate.HEADQUARTERS, "target_thread_id": gate.QA_TECHNICAL,
            "turn_id": reply_native["turn_id"], "tool_output_id": "fco_synthetic-tool",
            "wrapper_sha256": hashlib.sha256(self.tool_raw.encode()).hexdigest(), "wrapper_utf8_bytes": len(self.tool_raw.encode()),
            "dispatch_receipt_id": "dispatch", "local_record": {"source_path": str(session_root/"synthetic.jsonl"),
            "line": 3, "turn_context_line": 2}}
        self.tool_policy = {"decision_id": "synthetic-tool-policy", "status": "allow", "routing_status": "routing_allowed",
            "task_id": self.plan["task_id"], "action_id": self.plan["action_id"], "action_class": "thread_message",
            "scope": self.plan["scope"], "department": "operations", "target_department": "qa-technical",
            "source_project_id": gate.PROJECT, "target_project_id": gate.PROJECT,
            "target_thread_id": gate.QA_TECHNICAL, "target_cwd": str(self.root),
            "payload_sha256": self.tech_dep["request_payload"]["sha256"], "checked_at": (now-dt.timedelta(seconds=40)).isoformat()}
        self.receipts[1]["policy_decision_id"] = self.tool_policy["decision_id"]
        self.update_tool_fixture()

    def update_tool_fixture(self):
        raw_lines = [json.dumps(row, ensure_ascii=False) + "\n" for row in self.tool_local_rows]
        self.save_text("native-tool-session/synthetic.jsonl", "".join(raw_lines))
        line = self.tool_descriptor["local_record"]["line"]
        selected = raw_lines[line-1].encode() if type(line) is int and line>0 and line<=len(raw_lines) else raw_lines[2].encode()
        self.tool_descriptor["local_record"].update(raw_sha256=hashlib.sha256(selected).hexdigest(), raw_utf8_bytes=len(selected))
        self.tool_descriptor["pin"] = self.save("native-tool-app.json", self.tool_app)
        self.tech_dep["native_request"] = self.tool_descriptor
        self.save_text("logs/policy-decisions.jsonl", json.dumps(self.tool_policy) + "\n")
        self.update_technical_box()

    def test_real_shaped_tool_request_with_original_local_record_passes_control(self):
        self.native_tool_fixture()
        self.assertEqual(self.check(self.request("associate")), [])
        self.assertLess(self.tool_local_rows[2]["payload"]["internal_chat_message_metadata_passthrough"]["create_time"],
                        dt.datetime.fromisoformat(self.receipts[1]["created_at"]).timestamp())
        self.assertEqual(sum(x["type"] == "userMessage" for x in self.tool_app["turn"]["items"]), 0)

    def test_tool_type_name_namespace_id_and_context_are_exact(self):
        for change in ("type", "name", "namespace", "id", "target", "turn", "source", "version", "duplicate"):
            with self.subTest(change=change):
                self.native_tool_fixture()
                item = self.tool_app["turn"]["items"][0]
                if change in ("type", "name", "namespace", "id"): item[change] = "unrelated"
                if change == "target": self.tool_app["thread_id"] = gate.SOURCE
                if change == "turn": self.tool_app["turn"]["id"] = "different-turn"
                if change == "source": self.tool_descriptor["source_thread_id"] = gate.SOURCE
                if change == "version": self.tool_descriptor["schema_version"] = True
                if change == "duplicate": self.tool_app["turn"]["items"].append(copy.deepcopy(item))
                self.update_tool_fixture(); self.assertTrue(self.check(self.request("associate")))

    def test_truncated_missing_and_non_boolean_complete_flags_deny(self):
        for value in (True, 0, None, "false", "missing"):
            with self.subTest(value=value):
                self.native_tool_fixture(); output = self.tool_app["turn"]["items"][0]["output"]
                if value == "missing": output.pop("truncated")
                else: output["truncated"] = value
                self.update_tool_fixture(); self.assertTrue(self.check(self.request("associate")))

    def test_malformed_nested_or_extra_wrapper_and_utf8_changes_deny(self):
        for change in ("extra", "nested", "closing", "sender", "space", "unicode", "newline"):
            with self.subTest(change=change):
                self.native_tool_fixture(); raw = self.tool_raw
                if change == "extra": raw += "\nextra"
                if change == "nested": raw = raw.replace("<input>", "<input><codex_delegation>")
                if change == "closing": raw = raw.replace("</input>", "</inputs>")
                if change == "sender": raw = raw.replace(gate.HEADQUARTERS, gate.SOURCE)
                if change == "space": raw = raw.replace("Synthetic exact", "Synthetic  exact")
                if change == "unicode": raw = raw.replace("Synthetic", "Synthetíc")
                if change == "newline": raw = raw.replace("request\n", "request")
                self.tool_app["turn"]["items"][0]["output"]["text"] = raw
                self.tool_local_rows[2]["payload"]["output"] = raw
                self.tool_descriptor.update(wrapper_sha256=hashlib.sha256(raw.encode()).hexdigest(), wrapper_utf8_bytes=len(raw.encode()))
                self.update_tool_fixture(); self.assertTrue(self.check(self.request("associate")))

    def test_app_or_local_record_repin_cannot_forge_crosscheck(self):
        for change in ("app", "local", "local-name", "local-type", "local-turn", "local-duplicate", "digest"):
            with self.subTest(change=change):
                self.native_tool_fixture()
                if change == "app": self.tool_app["turn"]["items"][0]["output"]["text"] += "changed"
                if change == "local": self.tool_local_rows[2]["payload"]["output"] += "changed"
                if change == "local-name": self.tool_local_rows[2]["payload"]["name"] = "unrelated"
                if change == "local-type": self.tool_local_rows[2]["payload"]["type"] = "message"
                if change == "local-turn": self.tool_local_rows[2]["payload"]["internal_chat_message_metadata_passthrough"]["turn_id"] = "unrelated"
                if change == "local-duplicate": self.tool_local_rows.append(copy.deepcopy(self.tool_local_rows[2]))
                self.update_tool_fixture()
                if change == "digest":
                    self.tool_descriptor["local_record"]["raw_sha256"] = "0"*64
                    self.tech_dep["native_request"] = self.tool_descriptor
                    self.policy["owner_paid_logo_v1"]["technical_qa2"] = self.save("technical-dependency.json", self.tech_dep)
                self.assertTrue(self.check(self.request("associate")))

    def test_local_identity_latest_context_path_and_line_must_be_original(self):
        for change in ("meta", "cwd", "context", "context-line", "latest-context", "bool-line", "path", "client-authored", "receiver-turn", "receiver-id"):
            with self.subTest(change=change):
                self.native_tool_fixture()
                if change == "meta": self.tool_local_rows[0]["payload"]["id"] = gate.SOURCE
                if change == "cwd": self.tool_local_rows[1]["payload"]["cwd"] = "/unrelated"
                if change == "context": self.tool_local_rows[1]["payload"]["turn_id"] = "unrelated"
                if change == "context-line": self.tool_descriptor["local_record"]["turn_context_line"] = 1
                if change == "latest-context":
                    self.tool_local_rows.insert(2,{"type":"turn_context","payload":{"turn_id":"unrelated","cwd":str(self.root)}})
                    self.tool_descriptor["local_record"]["line"] = 4
                if change == "bool-line": self.tool_descriptor["local_record"]["line"] = True
                if change == "path": self.tool_descriptor["local_record"]["source_path"] = str(self.root/"outside.jsonl")
                if change == "client-authored": self.tool_local_rows[2]["metadata"]["client_authored"] = True
                if change == "receiver-turn": self.tool_local_rows[2]["metadata"]["sender_user_messages"]["receiver_turn_id"] = "unrelated"
                if change == "receiver-id": self.tool_local_rows[2]["metadata"]["sender_user_messages"]["receiver_message_id"] = "unrelated"
                self.update_tool_fixture(); self.assertTrue(self.check(self.request("associate")))

    def test_old_tool_evidence_wrong_policy_or_dispatch_cannot_be_reused(self):
        for change in ("receipt", "policy-time", "policy-scope", "policy-payload", "policy-target", "no-policy", "duplicate-policy"):
            with self.subTest(change=change):
                self.native_tool_fixture()
                if change == "receipt": self.tool_descriptor["dispatch_receipt_id"] = "old-dispatch"
                if change == "policy-time": self.tool_policy["checked_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
                if change == "policy-scope": self.tool_policy["scope"] = "unrelated"
                if change == "policy-payload": self.tool_policy["payload_sha256"] = "0"*64
                if change == "policy-target": self.tool_policy["target_thread_id"] = gate.QA
                self.update_tool_fixture()
                if change == "no-policy": self.save_text("logs/policy-decisions.jsonl", "")
                if change == "duplicate-policy": self.save_text("logs/policy-decisions.jsonl", (json.dumps(self.tool_policy)+"\n")*2)
                self.assertTrue(self.check(self.request("associate")))

    def test_native_numeric_timestamp_rejects_bool_nan_inf_future_and_negative(self):
        for value in (True, float("nan"), float("inf"), -1, 999999999999):
            with self.subTest(value=value):
                self.native_tool_fixture(); self.tool_local_rows[2]["payload"]["internal_chat_message_metadata_passthrough"]["create_time"] = value
                self.update_tool_fixture(); self.assertTrue(self.check(self.request("associate")))

    def final_successor_fixture(self):
        """Synthetic future-input contract only; no fixed-chat send or permission use."""
        import workflow_control as w
        if not hasattr(self, "final_original_packet_value"):
            self.final_original_packet_value = copy.deepcopy(self.packet)
        self.packet = copy.deepcopy(self.final_original_packet_value)
        self.save(gate.HISTORICAL_QA1_BLOCKED_PIN["path"], {"qa_verdict": "blocked", "synthetic": True})
        original = self.save("historical/original-logo-packet.json", copy.deepcopy(self.packet))
        old_attempt = self.save(gate.HISTORICAL_REVIEW_ATTEMPT_PATH,
                                {"synthetic": True, "attempted": True})
        old_send = self.save("historical/original-logo-review-send.json",
                             {"synthetic": True, "sent": True})
        for name, pin in (("HISTORICAL_LOGO_PACKET_PIN", original),
                          ("HISTORICAL_REVIEW_ATTEMPT_PIN", old_attempt),
                          ("HISTORICAL_REVIEW_SEND_PIN", old_send)):
            patcher = patch.object(gate, name, pin, create=True)
            patcher.start(); self.addCleanup(patcher.stop)
        self.final_payload = self.save_text("final-successor/request.md",
                                            "Synthetic new final Logo content and association review. 中文\n")
        self.packet["final_qa_proof_path"] = "final-successor/proof.json"
        self.packet["frozen_inputs"] = [original, old_attempt, old_send, gate.HISTORICAL_QA1_BLOCKED_PIN]
        self.refresh()
        self.technical_qa2()
        self._final_successor_technical_identity()
        rule = self.policy["owner_paid_logo_v1"]
        self.final_refs = {
            "business_identity": {"task_id": gate.TASK, "action_id": gate.ACTIONS["associate"][1],
                "action_class": gate.ACTIONS["associate"][0], "scope": gate.LOGO_SCOPE,
                "candidate_version": gate.VERSION, "candidate_sha256": self.packet["logo_candidate"]["sha256"]},
            "original_logo_packet": original, "logo_candidate": self.packet["logo_candidate"],
            "owner_authorization": self.packet["owner_authorization"],
            "historical_final_qa": gate.HISTORICAL_QA1_BLOCKED_PIN,
            "historical_review_attempt": old_attempt, "historical_review_send": old_send,
            "account_id": "example-ads-account", "campaign_ids": gate.CAMPAIGNS, "asset_id": gate.ASSET,
            "association_level": "CAMPAIGN_ONLY", "unchanged": gate.UNCHANGED,
            "owner_expires_at": "2026-10-14T14:00:00Z"}
        self.final_carrier = {
            "schema_version": 1, "kind": "owner_paid_logo.final_review_carrier.v1",
            "task_id": "synthetic-logo-final-successor-001", "department": "operations-assistant",
            "action_id": "review-synthetic-logo-final-successor-v1", "action_class": "internal_control_candidate",
            "scope": "project:synthetic-logo-final-successor:exact-v1", "candidate_version": "synthetic-final-carrier-v1",
            "risk_level": "R0", "production_write_allowed": False, "external_permission_issued": False,
            "production_release_eligible": False, "source_refs": self.final_refs,
            "logo_packet": rule["packet"], "technical_qa2": rule["technical_qa2"],
            "attempt_path": "final-successor/attempt.json",
            "frozen_sources": [rule["packet"], rule["technical_qa2"], original, old_attempt, old_send,
                self.packet["logo_candidate"], self.packet["owner_authorization"], gate.HISTORICAL_QA1_BLOCKED_PIN]
                + self.tech_dep["consumer_source_pins"]}
        self.final_plan = {**{k: self.final_carrier[k] for k in gate.IDENTITY[:-1]}, "schema_version": 1,
            "producer_department": "operations-assistant", "reviewer_department": "qa", "reviewer_thread_id": gate.QA,
            "controller_department": "operations", "controller_thread_id": gate.HEADQUARTERS,
            "single_final_reviewer": True, "risk_level": "R0", "production_write_allowed": False,
            "external_permission_issued": False}
        self.final_request = {"schema_version": 1, "kind": "owner_paid_logo.final_review_request.v1",
            "request_payload": self.final_payload, "source_refs": self.final_refs,
            "logo_packet": rule["packet"], "technical_qa2": rule["technical_qa2"],
            "reviewer_department": "qa", "reviewer_thread_id": gate.QA}
        text = "Synthetic fixed QA1 final Logo PASS: content and association only. 中文\n"
        self.final_reply_native = {"source_method": "mcp__codex_app__read_thread", "thread_id": gate.QA,
            "turn_id": "synthetic-final-successor-turn", "turn_status": "completed",
            "result_message": {"type": "agentMessage", "id": "msg_synthetic-final-successor", "text": text}}
        self.final_chat = {"namespace": "app.agentMessage", "message_id": "msg_synthetic-final-successor",
            "turn_id": self.final_reply_native["turn_id"], "ref": "msg_synthetic-final-successor",
            "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(), "nonempty": True,
            "in_current_fixed_department_chat": True}
        self.final_logo_review = {"content_verdict": "pass", "association_verdict": "pass", "scope": gate.LOGO_SCOPE}
        self.final_proof = {"schema_version": "owner-paid-logo-final-proof/1", "proof_format": "logo_final_successor.v1",
            "department": "qa", "fixed_chat_task_id": gate.QA, "qa_verdict": "pass", "result": "PASS",
            "source_refs": self.final_refs, "logo_packet": rule["packet"], "technical_qa2": rule["technical_qa2"],
            "chat_reply": copy.deepcopy(self.final_chat), "logo_review": copy.deepcopy(self.final_logo_review)}
        self.final_box = {"schema_version": "2.0", "department": "qa", "fixed_chat_task_id": gate.QA,
            "status": "completed", "qa_verdict": "pass", "conclusion": "Synthetic final successor fixture only",
            "risks": [], "next_actions": [], "handoff": {"receiver": "operations"}, "approval_required": False,
            "learning": {"status": "no_new_learning"}, "risk_level": "R0", "production_write_allowed": False,
            "external_permission_issued": False, "production_release_eligible": False,
            "source_refs": self.final_refs, "logo_packet": rule["packet"], "technical_qa2": rule["technical_qa2"],
            "logo_review": copy.deepcopy(self.final_logo_review), "chat_reply": copy.deepcopy(self.final_chat)}
        session_root = self.root / "final-successor/native-session"; session_root.mkdir(parents=True, exist_ok=True)
        patcher = patch.object(gate, "SESSION_ROOT", session_root); patcher.start(); self.addCleanup(patcher.stop)
        inner = (self.root / self.final_payload["path"]).read_text(encoding="utf-8")
        self.final_wrapper = "<codex_delegation>\n  <source_thread_id>" + gate.HEADQUARTERS + "</source_thread_id>\n  <input>" + inner + "</input>\n</codex_delegation>"
        now = dt.datetime.now(dt.timezone.utc)
        sent = (now - dt.timedelta(seconds=30)).isoformat()
        self.final_tool_app = {"schema_version": 1, "source_method": "mcp__codex_app__read_thread", "thread_id": gate.QA,
            "turn": {"id": self.final_chat["turn_id"], "status": "completed", "items": [{"type": "functionCallOutput",
                "id": "fco_synthetic-final-successor", "name": "send_message_to_thread", "namespace": "codex_app",
                "output": {"text": self.final_wrapper, "truncated": False}},
                {"type": "agentMessage", "id": "msg_synthetic-final-ack", "text": "Synthetic fixed QA1 ACK: exact new carrier received."},
                {"type": "agentMessage", "id": self.final_chat["message_id"], "text": text}]}}
        self.final_tool_rows = [{"type": "session_meta", "payload": {"id": gate.QA, "cwd": str(self.root)}},
            {"type": "turn_context", "payload": {"turn_id": self.final_chat["turn_id"], "cwd": str(self.root)}},
            {"type": "response_item", "payload": {"type": "function_call_output", "id": "fco_synthetic-final-successor",
                "name": "send_message_to_thread", "namespace": "codex_app", "output": self.final_wrapper,
                "internal_chat_message_metadata_passthrough": {"turn_id": self.final_chat["turn_id"],
                    "create_time": (now - dt.timedelta(seconds=35)).timestamp()}},
                "metadata": {"client_authored": False, "sender_user_messages": {"receiver_turn_id": self.final_chat["turn_id"],
                    "receiver_message_id": "fco_synthetic-final-successor"}}}]
        self.final_native_request = {"schema_version": 1, "format": gate.TOOL_REQUEST_FORMAT,
            "source_thread_id": gate.HEADQUARTERS, "target_thread_id": gate.QA, "turn_id": self.final_chat["turn_id"],
            "tool_output_id": "fco_synthetic-final-successor", "dispatch_receipt_id": "final-dispatch",
            "wrapper_sha256": hashlib.sha256(self.final_wrapper.encode("utf-8")).hexdigest(),
            "wrapper_utf8_bytes": len(self.final_wrapper.encode("utf-8")),
            "local_record": {"source_path": str(session_root / "synthetic.jsonl"), "line": 3, "turn_context_line": 2}}
        self.final_policy = {"decision_id": "synthetic-final-policy", "status": "allow", "routing_status": "routing_allowed",
            "task_id": self.final_carrier["task_id"], "action_id": self.final_carrier["action_id"], "action_class": "thread_message",
            "scope": self.final_carrier["scope"], "department": "operations", "target_department": "qa",
            "source_project_id": gate.PROJECT, "target_project_id": gate.PROJECT, "target_thread_id": gate.QA,
            "target_cwd": str(self.root), "payload_sha256": self.final_payload["sha256"],
            "checked_at": (now - dt.timedelta(seconds=40)).isoformat()}
        self.final_attempt = {"task_id": self.final_carrier["task_id"], "action_id": self.final_carrier["action_id"],
            "policy_decision_id": self.final_policy["decision_id"], "target_thread_id": gate.QA,
            "payload_sha256": self.final_payload["sha256"], "started_at": (now - dt.timedelta(seconds=37)).isoformat(),
            "status": "native_send_started_not_yet_claimed_success"}
        self.final_receipts = []
        for kind, department, rid in (("outbox_received", "operations-assistant", "final-producer"),
            ("dispatch_sent", "qa", "final-dispatch"), ("chat_ack", "qa", "final-ack"),
            ("outbox_received", "qa", "final-box"), ("qa_verdict", "qa", "final-verdict")):
            row = {"receipt_id": rid, "task_id": self.final_carrier["task_id"], "department": department,
                "chat_task_id": gate.QA if department == "qa" else "fixed-operations-assistant",
                "receipt_type": kind, "created_at": sent, "evidence": [],
                **{k: self.final_plan[k] for k in ("action_id", "action_class", "scope")}}
            if kind == "dispatch_sent": row["policy_decision_id"] = self.final_policy["decision_id"]
            if kind == "chat_ack": row["ack_nonempty"] = True
            if kind == "qa_verdict": row["verdict"] = "pass"
            self.final_receipts.append(row)
        self.final_dep = {"schema_version": 1, "kind": "owner_paid_logo.final_successor.v1",
            "proof_format": "logo_final_successor.v1", "request_payload": self.final_payload,
            "logo_packet": rule["packet"], "technical_qa2": rule["technical_qa2"],
            "attempt_format": "codex_app.send_message_to_thread.attempt.v1",
            "ack_receipt_id": "final-ack", "outbox_receipt_id": "final-box", "verdict_receipt_id": "final-verdict",
            "report": self.save_text("final-successor/report.md", "Synthetic final-successor fixture only\n")}
        self._rebind_final_successor()
        self.assertEqual(w._validate_receipt_chain(self.root, self.final_plan["task_id"])[1], [])
        self.assertEqual(w.validate_workflow_events(self.root, self.final_plan["task_id"]), [])

    def _final_successor_technical_identity(self):
        """Keep the existing QA2 dependency separate while fixing its registry identity."""
        import workflow_control as w
        old_plan, old_request = self.tech_dep["review_plan"], self.tech_dep["technical_request"]
        for role, tid in (("operations", gate.HEADQUARTERS), ("qa-technical", gate.QA_TECHNICAL)):
            self.departments[role]["chat_binding"]["task_id"] = tid
        self.save("data/department-registry.json", {"departments": list(self.departments.values())})
        self.plan.update(controller_thread_id=gate.HEADQUARTERS, reviewer_thread_id=gate.QA_TECHNICAL)
        plan_pin = self.save("review-plan.json", self.plan)
        request = json.loads((self.root / "technical-request.json").read_text())
        request.update(review_plan=plan_pin, reviewer_thread_id=gate.QA_TECHNICAL)
        request_pin = self.save("technical-request.json", request)
        self.tech_dep.update(review_plan=plan_pin, technical_request=request_pin)
        snapshot = json.loads((self.root / ("data/workflows/" + self.plan["task_id"] + ".json")).read_text())
        snapshot["qa_review_plan"]["pin"] = plan_pin
        for row in snapshot["departments"]:
            if row["department"] == "qa-technical": row["chat_task_id"] = gate.QA_TECHNICAL
        self.save("data/workflows/" + self.plan["task_id"] + ".json", snapshot)
        self.final_technical_event = {"task_id": self.plan["task_id"], "state": "planned", "previous_event_hash": "",
            "details": {"departments": snapshot["departments"], "qa_review_plan_bound": snapshot["qa_review_plan"]}}
        self.final_technical_event["event_hash"] = w.sha256_value(self.final_technical_event)
        for row in self.receipts:
            if row["department"] == "qa-technical": row["chat_task_id"] = gate.QA_TECHNICAL
            row["evidence"] = [plan_pin if v == old_plan else request_pin if v == old_request else v for v in row["evidence"]]
        self.tech_box["fixed_chat_task_id"] = gate.QA_TECHNICAL
        self.tech_box["evidence"] = [plan_pin if v == old_plan else request_pin if v == old_request else v for v in self.tech_box["evidence"]]
        native = json.loads((self.root / "technical-native.json").read_text()); native["thread_id"] = gate.QA_TECHNICAL
        self.tech_dep["native_observation"]["pin"] = self.save("technical-native.json", native)
        native = json.loads((self.root / "technical-native-request.json").read_text()); native["thread_id"] = gate.QA_TECHNICAL
        self.tech_dep["native_request"]["pin"] = self.save("technical-native-request.json", native)
        self.update_technical_box()

    def _rebind_final_successor(self):
        """Freeze the synthetic graph in dependency order; proof is never in outbox evidence."""
        import workflow_control as w
        carrier = self.save("final-successor/carrier.json", self.final_carrier)
        self.final_plan.update({k: self.final_carrier[k] for k in gate.IDENTITY[:-1]})
        self.final_plan.update(candidate=carrier, candidate_sha256=carrier["sha256"])
        plan = self.save("final-successor/plan.json", self.final_plan)
        identity = {k: self.final_plan[k] for k in gate.IDENTITY}
        self.final_request.update(carrier=carrier, review_plan=plan, review_identity=identity)
        request = self.save("final-successor/final-request.json", self.final_request)
        self.final_attempt.update(task_id=self.final_plan["task_id"], action_id=self.final_plan["action_id"])
        for value in (self.final_proof, self.final_box): value.update(identity)
        self.final_box["review_identity"] = identity
        self.final_result_core = {"schema_version": "owner-paid-logo-final-result/1", "review_identity": identity,
            "source_refs": self.final_refs, "logo_packet": self.final_dep["logo_packet"],
            "technical_qa2": self.final_dep["technical_qa2"], "logo_review": copy.deepcopy(self.final_logo_review),
            "qa_verdict": "pass", "result": "PASS", "risk_level": "R0", "production_write_allowed": False,
            "external_permission_issued": False, "production_release_eligible": False}
        result_text = json.dumps(self.final_result_core, ensure_ascii=False)
        self.final_reply_native["result_message"]["text"] = result_text
        self.final_tool_app["turn"]["items"][-1]["text"] = result_text
        digest = hashlib.sha256(result_text.encode("utf-8")).hexdigest()
        for value in (self.final_proof, self.final_box):
            value["chat_reply"]["sha256"] = digest
            value.update(risk_level="R0", production_write_allowed=False, external_permission_issued=False,
                         production_release_eligible=False)
        self.final_dep.update(carrier=carrier, review_plan=plan, final_request=request, review_identity=identity)
        producer = self.save("final-successor/producer-outbox.json",
                             {"candidate_version": self.final_plan["candidate_version"], "evidence": [carrier]})
        for row in self.final_receipts:
            row.update(task_id=self.final_plan["task_id"], **{k: self.final_plan[k] for k in ("action_id", "action_class", "scope")})
            if row["receipt_id"] == "final-producer": row["evidence"] = [producer]
            if row["receipt_id"] == "final-dispatch": row["evidence"] = [carrier, plan, request, self.final_payload, self.final_dep["logo_packet"]]
        snapshot = {"task_id": self.final_plan["task_id"], "owner_approval_required": False,
            "departments": [{"department": "operations-assistant", "chat_task_id": "fixed-operations-assistant"},
                            {"department": "qa", "chat_task_id": gate.QA}],
            "qa_review_plan": {"pin": plan, "reviewer_department": "qa"}}
        self.save("data/workflows/" + self.final_plan["task_id"] + ".json", snapshot)
        event = {"task_id": self.final_plan["task_id"], "state": "planned", "previous_event_hash": self.final_technical_event["event_hash"],
                 "details": {"departments": snapshot["departments"], "qa_review_plan_bound": snapshot["qa_review_plan"]}}
        event["event_hash"] = w.sha256_value(event)
        self.save_text("logs/workflow-events.jsonl", json.dumps(self.final_technical_event) + "\n" + json.dumps(event) + "\n")
        self._write_final_successor()

    def _write_final_successor(self, *, bind_inputs=True):
        import workflow_control as w
        raw_lines = [json.dumps(row, ensure_ascii=False) + "\n" for row in self.final_tool_rows]
        self.save_text("final-successor/native-session/synthetic.jsonl", "".join(raw_lines))
        line = self.final_native_request["local_record"]["line"]
        selected = raw_lines[line - 1].encode("utf-8") if type(line) is int and 0 < line <= len(raw_lines) else raw_lines[2].encode("utf-8")
        self.final_native_request["local_record"].update(raw_sha256=hashlib.sha256(selected).hexdigest(), raw_utf8_bytes=len(selected))
        self.final_native_request["pin"] = self.save("final-successor/native-tool-app.json", self.final_tool_app)
        attempt = self.save(self.final_carrier["attempt_path"], self.final_attempt)
        required = [self.final_dep[k] for k in ("carrier", "review_plan", "final_request")]
        required += [self.final_payload, self.final_dep["logo_packet"], self.final_dep["technical_qa2"], attempt]
        if "evidence" not in self.final_box: self.final_box["evidence"] = required
        elif bind_inputs:
            paths = {p["path"] for p in required}
            self.final_box["evidence"] = [p for p in self.final_box["evidence"] if p["path"] not in paths] + required
        self.final_proof["frozen_inputs_verified"] = required
        box = self.save("final-successor/outbox.json", self.final_box)
        proof = self.save("final-successor/proof.json", self.final_proof)
        observation = {"schema_version": 1, "format": "read_thread.completed-result.v1",
                       "pin": self.save("final-successor/native-reply.json", self.final_reply_native)}
        self.final_dep.update(attempt=attempt, outbox=box, proof=proof, native_observation=observation,
                              native_request=self.final_native_request)
        if "native_ack" not in self.final_dep:
            self.final_dep["native_ack"] = {"schema_version": 1, "format": "read_thread.turn.v1",
                "pin": self.final_native_request["pin"], "message_id": "msg_synthetic-final-ack"}
        else: self.final_dep["native_ack"]["pin"] = self.final_native_request["pin"]
        previous = ""
        for row in self.final_receipts:
            if row["receipt_type"] in {"outbox_received", "qa_verdict"} and row["department"] == "qa": row["evidence"] = [box]
            if bind_inputs and row["receipt_type"] == "chat_ack" and row["department"] == "qa": row["evidence"] = [self.final_native_request["pin"]]
            row["previous_hash"] = previous
            row["receipt_hash"] = w.sha256_value(w._receipt_payload_for_hash(row)); previous = row["receipt_hash"]
        self.save_text("logs/receipts/" + self.final_plan["task_id"] + ".jsonl", "".join(json.dumps(row) + "\n" for row in self.final_receipts))
        self.save_text("logs/policy-decisions.jsonl", json.dumps(self.final_policy) + "\n")
        self.policy["owner_paid_logo_v1"]["final_qa_evidence"] = self.save("final-successor/dependency.json", self.final_dep)

    def test_final_successor_full_control_pass_and_original_review_stays_consumed(self):
        self.final_successor_fixture()
        self.assertEqual(self.check(self.request("associate")), [])
        self.assertIn("owner_paid_logo_denied:single_use_attempt_already_recorded", self.check())
        self.assertFalse(self.policy["paid_promotion_enabled"])
        self.assertNotEqual(self.final_plan["task_id"], gate.TASK)
        self.assertNotEqual(self.final_dep["request_payload"]["sha256"], self.packet["actions"]["review"]["payload"]["sha256"])
        self.assertEqual(sum(item["type"] == "userMessage" for item in self.final_tool_app["turn"]["items"]), 0)
        self.assertNotIn(self.final_dep["proof"], self.final_box["evidence"])

    def test_final_successor_exact_original_source_refs_and_business_identity(self):
        for change in ("business-task", "business-action", "business-class", "business-scope", "business-version", "business-hash",
                       "account", "campaigns", "asset", "level", "unchanged", "expiry", "historical-proof", "original-packet"):
            with self.subTest(change=change):
                self.final_successor_fixture()
                if change.startswith("business-"):
                    key = {"task": "task_id", "action": "action_id", "class": "action_class", "scope": "scope",
                           "version": "candidate_version", "hash": "candidate_sha256"}[change.removeprefix("business-")]
                    self.final_refs["business_identity"][key] = "unrelated"
                elif change == "account": self.final_refs["account_id"] = "other-account"
                elif change == "campaigns": self.final_refs["campaign_ids"] = [gate.CAMPAIGNS[0]]
                elif change == "asset": self.final_refs["asset_id"] = "other-asset"
                elif change == "level": self.final_refs["association_level"] = "ACCOUNT"
                elif change == "unchanged": self.final_refs["unchanged"] = []
                elif change == "expiry": self.final_refs["owner_expires_at"] = "2026-12-31T00:00:00Z"
                elif change == "historical-proof": self.final_refs["historical_final_qa"] = self.save("other-blocked.json", {"qa_verdict": "blocked"})
                else: self.final_refs["original_logo_packet"] = self.policy["owner_paid_logo_v1"]["packet"]
                self._rebind_final_successor(); self.assertTrue(self.check(self.request("associate")))

    def test_final_successor_carrier_and_result_identities_cannot_be_relabelled(self):
        for change in ("carrier-task", "carrier-review-action", "carrier-associate-action", "carrier-version", "carrier-class",
                       "proof-task", "proof-hash", "box-version", "box-scope", "box-review-identity"):
            with self.subTest(change=change):
                self.final_successor_fixture()
                if change.startswith("carrier-"):
                    if change == "carrier-task": self.final_carrier["task_id"] = gate.TASK
                    elif change == "carrier-review-action": self.final_carrier["action_id"] = gate.ACTIONS["review"][1]
                    elif change == "carrier-associate-action": self.final_carrier["action_id"] = gate.ACTIONS["associate"][1]
                    elif change == "carrier-version": self.final_carrier["candidate_version"] = gate.VERSION
                    else: self.final_carrier["action_class"] = "ads_write"
                    self._rebind_final_successor()
                else:
                    if change == "proof-task": self.final_proof["task_id"] = gate.TASK
                    elif change == "proof-hash": self.final_proof["candidate_sha256"] = "0" * 64
                    elif change == "box-version": self.final_box["candidate_version"] = gate.VERSION
                    elif change == "box-scope": self.final_box["scope"] = gate.LOGO_SCOPE
                    else: self.final_box["review_identity"] = {**self.final_box["review_identity"], "action_id": "other"}
                    self._write_final_successor()
                self.assertTrue(self.check(self.request("associate")))

    def test_final_successor_packet_request_and_attempt_bindings_are_exact(self):
        for change in ("dep-packet", "carrier-packet", "request-packet", "proof-packet", "box-packet", "request-source",
                       "old-payload", "attempt-task", "attempt-policy", "attempt-payload", "attempt-target", "attempt-status", "attempt-action", "attempt-time"):
            with self.subTest(change=change):
                self.final_successor_fixture()
                if change == "dep-packet": self.final_dep["logo_packet"] = gate.HISTORICAL_LOGO_PACKET_PIN
                elif change == "carrier-packet": self.final_carrier["logo_packet"] = gate.HISTORICAL_LOGO_PACKET_PIN
                elif change == "request-packet": self.final_request["logo_packet"] = gate.HISTORICAL_LOGO_PACKET_PIN
                elif change == "proof-packet": self.final_proof["logo_packet"] = gate.HISTORICAL_LOGO_PACKET_PIN
                elif change == "box-packet": self.final_box["logo_packet"] = gate.HISTORICAL_LOGO_PACKET_PIN
                elif change == "request-source": self.final_request["source_refs"] = {}
                elif change == "old-payload": self.final_dep["request_payload"] = self.packet["actions"]["review"]["payload"]
                elif change == "attempt-task": self.final_attempt["task_id"] = gate.TASK
                elif change == "attempt-policy": self.final_attempt["policy_decision_id"] = "old-policy"
                elif change == "attempt-payload": self.final_attempt["payload_sha256"] = self.packet["actions"]["review"]["payload"]["sha256"]
                elif change == "attempt-target": self.final_attempt["target_thread_id"] = gate.QA_TECHNICAL
                elif change == "attempt-status": self.final_attempt["status"] = "sent"
                elif change == "attempt-action": self.final_attempt["action_id"] = gate.ACTIONS["review"][1]
                else: self.final_attempt["started_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
                if change in ("carrier-packet", "request-packet", "request-source"): self._rebind_final_successor()
                else: self._write_final_successor()
                self.assertTrue(self.check(self.request("associate")))

    def test_final_successor_current_policy_native_input_and_once_only_chain_required(self):
        for change in ("policy-time", "policy-target", "policy-payload", "policy-scope", "policy-class", "duplicate-dispatch",
                       "earlier-failed", "later-dispatch", "later-failed", "later-ack", "later-box", "later-verdict", "no-ack", "empty-ack", "blocked"):
            with self.subTest(change=change):
                self.final_successor_fixture()
                if change == "policy-time": self.final_policy["checked_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
                elif change == "policy-target": self.final_policy["target_department"] = "qa-technical"
                elif change == "policy-payload": self.final_policy["payload_sha256"] = "0" * 64
                elif change == "policy-scope": self.final_policy["scope"] = "project:other:scope"
                elif change == "policy-class": self.final_policy["action_class"] = "ads_write"
                elif change in ("duplicate-dispatch", "earlier-failed"):
                    row = copy.deepcopy(self.final_receipts[1]); row["receipt_id"] = "other-attempt"
                    if change == "earlier-failed": row["receipt_type"] = "dispatch_failed"
                    self.final_receipts.insert(1, row)
                elif change.startswith("later-"):
                    source = {"dispatch": 1, "failed": 1, "ack": 2, "box": 3, "verdict": 4}[change.removeprefix("later-")]
                    row = copy.deepcopy(self.final_receipts[source]); row["receipt_id"] = "later-receipt"
                    if change == "later-failed": row["receipt_type"] = "dispatch_failed"
                    self.final_receipts.append(row)
                elif change == "no-ack": self.final_receipts = [r for r in self.final_receipts if r["receipt_type"] != "chat_ack"]
                elif change == "empty-ack": self.final_receipts[2]["ack_nonempty"] = False
                else:
                    self.final_proof.update(result="BLOCKED", qa_verdict="blocked")
                    self.final_box.update(status="blocked", qa_verdict="blocked"); self.final_receipts[-1]["verdict"] = "blocked"
                self._write_final_successor(); self.assertTrue(self.check(self.request("associate")))

    def test_final_successor_native_tool_type_context_digest_and_rawreply_are_required(self):
        for change in ("type", "namespace", "name", "truncated", "local-context", "local-client", "local-receiver",
                       "local-duplicate", "wrapper-text", "future-input", "proof-reply-hash", "box-reply-hash", "reply-namespace", "reply-thread", "reply-active"):
            with self.subTest(change=change):
                self.final_successor_fixture()
                item = self.final_tool_app["turn"]["items"][0]
                if change in ("type", "namespace", "name"): item[change] = "unrelated"
                elif change == "truncated": item["output"]["truncated"] = True
                elif change == "local-context": self.final_tool_rows[1]["payload"]["turn_id"] = "other"
                elif change == "local-client": self.final_tool_rows[2]["metadata"]["client_authored"] = True
                elif change == "local-receiver": self.final_tool_rows[2]["metadata"]["sender_user_messages"]["receiver_message_id"] = "fco_other"
                elif change == "local-duplicate": self.final_tool_rows.append(copy.deepcopy(self.final_tool_rows[2]))
                elif change == "wrapper-text": item["output"]["text"] += "extra"
                elif change == "future-input": self.final_tool_rows[2]["payload"]["internal_chat_message_metadata_passthrough"]["create_time"] = 999999999999
                elif change == "proof-reply-hash": self.final_proof["chat_reply"]["sha256"] = "0" * 64
                elif change == "box-reply-hash": self.final_box["chat_reply"]["sha256"] = "0" * 64
                elif change == "reply-namespace":
                    self.final_proof["chat_reply"]["namespace"] = "local_session.response_item"
                    self.final_box["chat_reply"]["namespace"] = "local_session.response_item"
                elif change == "reply-thread": self.final_reply_native["thread_id"] = gate.QA_TECHNICAL
                else: self.final_reply_native["turn_status"] = "inProgress"
                self._write_final_successor(); self.assertTrue(self.check(self.request("associate")))

    def test_final_successor_content_and_association_passes_are_both_required(self):
        for where in ("proof", "box"):
            for key in ("content_verdict", "association_verdict", "scope"):
                with self.subTest(where=where, key=key):
                    self.final_successor_fixture()
                    value = self.final_proof if where == "proof" else self.final_box
                    value["logo_review"][key] = "blocked" if key != "scope" else "google_ads:other"
                    self._write_final_successor(); self.assertTrue(self.check(self.request("associate")))

    def test_final_successor_actual_raw_reply_must_carry_exact_logo_verdict(self):
        for change in ("generic-pass", "route-only", "blocked", "wrong-identity", "content-blocked", "association-blocked",
                       "missing-source", "extra-pin", "risk", "write-allowed", "numeric-false", "duplicate-key", "app-reply-mismatch"):
            with self.subTest(change=change):
                self.final_successor_fixture()
                core = copy.deepcopy(self.final_result_core)
                if change == "generic-pass": text = "PASS received the route only."
                elif change == "route-only": text = json.dumps({"qa_verdict": "pass", "result": "PASS", "routing_status": "routing_allowed"})
                else:
                    if change == "blocked": core.update(qa_verdict="blocked", result="BLOCKED")
                    elif change == "wrong-identity": core["review_identity"]["task_id"] = gate.TASK
                    elif change == "content-blocked": core["logo_review"]["content_verdict"] = "blocked"
                    elif change == "association-blocked": core["logo_review"]["association_verdict"] = "blocked"
                    elif change == "missing-source": core.pop("source_refs")
                    elif change == "extra-pin": core["outbox_sha256"] = "0" * 64
                    elif change == "risk": core["risk_level"] = "R1"
                    elif change == "write-allowed": core["production_write_allowed"] = True
                    elif change == "numeric-false": core["production_write_allowed"] = 0
                    text = json.dumps(core, ensure_ascii=False)
                    if change == "duplicate-key": text = text.replace('"qa_verdict": "pass"', '"qa_verdict": "blocked", "qa_verdict": "pass"', 1)
                self.final_reply_native["result_message"]["text"] = text
                self.final_tool_app["turn"]["items"][-1]["text"] = text if change != "app-reply-mismatch" else "Different raw final result"
                digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
                for value in (self.final_proof, self.final_box): value["chat_reply"]["sha256"] = digest
                self._write_final_successor(); self.assertTrue(self.check(self.request("associate")))

    def test_final_successor_ack_requires_actual_nonempty_reply_in_request_turn_order(self):
        for change in ("empty", "whitespace", "wrong-id", "same-final", "before-tool", "after-final", "duplicate",
                       "wrong-type", "wrong-format", "wrong-version", "wrong-receipt", "missing-evidence"):
            with self.subTest(change=change):
                self.final_successor_fixture()
                items = self.final_tool_app["turn"]["items"]
                if change == "empty": items[1]["text"] = ""
                elif change == "whitespace": items[1]["text"] = " \n "
                elif change == "wrong-id": self.final_dep["native_ack"]["message_id"] = "msg_unrelated_ack"
                elif change == "same-final": self.final_dep["native_ack"]["message_id"] = self.final_chat["message_id"]
                elif change == "before-tool": items[0], items[1] = items[1], items[0]
                elif change == "after-final": items[1], items[2] = items[2], items[1]
                elif change == "duplicate": items.insert(2, copy.deepcopy(items[1]))
                elif change == "wrong-type": items[1]["type"] = "userMessage"
                elif change == "wrong-format": self.final_dep["native_ack"]["format"] = "read_thread.completed-result.v1"
                elif change == "wrong-version": self.final_dep["native_ack"]["schema_version"] = True
                elif change == "wrong-receipt": self.final_dep["ack_receipt_id"] = "unrelated-ack"
                else: self.final_receipts[2]["evidence"] = []
                self._write_final_successor(bind_inputs=change != "missing-evidence")
                self.assertTrue(self.check(self.request("associate")))

    def test_final_successor_outbox_must_freeze_every_current_input(self):
        for key in ("carrier", "review_plan", "final_request", "request_payload", "logo_packet", "technical_qa2", "attempt"):
            with self.subTest(input=key):
                self.final_successor_fixture()
                self.final_box["evidence"].remove(self.final_dep[key])
                self._write_final_successor(bind_inputs=False); self.assertTrue(self.check(self.request("associate")))

    def test_final_successor_typed_contract_and_technical_dependency_stay_fail_closed(self):
        for change in ("dep-version", "dep-kind", "carrier-version", "carrier-kind", "request-version", "request-kind", "attempt-format",
                       "proof-version", "box-version", "missing-qa2", "blocked-qa2", "qa2-pin"):
            with self.subTest(change=change):
                self.final_successor_fixture()
                if change == "dep-version": self.final_dep["schema_version"] = True
                elif change == "dep-kind": self.final_dep["kind"] = "other"
                elif change == "carrier-version": self.final_carrier["schema_version"] = True
                elif change == "carrier-kind": self.final_carrier["kind"] = "other"
                elif change == "request-version": self.final_request["schema_version"] = True
                elif change == "request-kind": self.final_request["kind"] = "other"
                elif change == "attempt-format": self.final_dep["attempt_format"] = "owner_paid_logo.final_review_attempt.v1"
                elif change == "proof-version": self.final_proof["schema_version"] = "flashcast-qa-proof/1"
                elif change == "box-version": self.final_box["schema_version"] = "department-outbox/2"
                elif change == "missing-qa2": self.policy["owner_paid_logo_v1"].pop("technical_qa2")
                elif change == "blocked-qa2":
                    self.tech_box["qa_verdict"] = "blocked"; self.receipts[-1]["verdict"] = "blocked"
                    self.update_technical_box()
                else: self.final_dep["technical_qa2"] = self.save("unrelated-qa2.json", {"status": "pass"})
                if change.startswith("carrier-") or change.startswith("request-"): self._rebind_final_successor()
                else: self._write_final_successor()
                self.assertTrue(self.check(self.request("associate")))

    def test_final_successor_historical_bytes_owner_deadline_and_attempt_paths_stay_closed(self):
        for pin_name in ("HISTORICAL_LOGO_PACKET_PIN", "HISTORICAL_REVIEW_ATTEMPT_PIN", "HISTORICAL_REVIEW_SEND_PIN", "HISTORICAL_QA1_BLOCKED_PIN"):
            with self.subTest(pin=pin_name):
                self.final_successor_fixture(); pin = getattr(gate, pin_name)
                self.save(pin["path"], {"synthetic": True, "changed": True}); self.assertTrue(self.check(self.request("associate")))
        self.final_successor_fixture()
        real_datetime = dt.datetime
        class Expired(real_datetime):
            @classmethod
            def now(cls, tz=None): return cls(2026, 10, 14, 14, 0, 1, tzinfo=dt.timezone.utc)
        with patch.object(gate.dt, "datetime", Expired): self.assertTrue(self.check(self.request("associate")))
        for path in ("review-attempt.json", "associate-attempt.json", gate.HISTORICAL_REVIEW_ATTEMPT_PATH):
            with self.subTest(attempt_path=path):
                self.final_successor_fixture(); self.final_carrier["attempt_path"] = path
                self._rebind_final_successor(); self.assertTrue(self.check(self.request("associate")))

    def test_old_native_input_cannot_bind_new_dispatch_with_old_policy(self):
        for change in ("same-policy-sent", "same-policy-failed", "old-window", "fresh-window"):
            with self.subTest(change=change):
                self.native_tool_fixture()
                checked = dt.datetime.fromisoformat(self.tool_policy["checked_at"])
                prior = copy.deepcopy(self.receipts[1])
                prior["receipt_id"] = "previous-dispatch"
                prior["receipt_type"] = "dispatch_failed" if change == "same-policy-failed" else "dispatch_sent"
                prior["created_at"] = (checked - dt.timedelta(seconds=5)).isoformat()
                if change in ("old-window", "fresh-window"):
                    prior["policy_decision_id"] = "different-previous-policy"
                if change == "old-window":
                    prior["created_at"] = (checked + dt.timedelta(seconds=6)).isoformat()
                self.receipts.insert(1, prior)
                self.update_tool_fixture()
                result = self.check(self.request("associate"))
                if change == "fresh-window":
                    self.assertEqual(result, [])
                else:
                    reason = ("native_tool_policy_must_follow_prior_dispatch_attempts" if change == "old-window"
                              else "native_tool_dispatch_policy_already_used")
                    self.assertTrue(any(reason in value for value in result), result)


if __name__ == "__main__":
    unittest.main()
