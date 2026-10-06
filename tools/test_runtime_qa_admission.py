from __future__ import annotations
import argparse
import copy
import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock
import workflow_control as w
import qa_review_plan as q
import test_workflow_control as legacy

TMP = Path(__file__).resolve().parents[1] / ".test-tmp"


class ExactRuntimeQA(unittest.TestCase):
    dispatch = legacy.WorkflowControlTests.dispatch
    receipt = legacy.WorkflowControlTests.receipt
    routing_decision = legacy.WorkflowControlTests.routing_decision

    def setUp(self):
        original = tempfile.TemporaryDirectory
        with mock.patch.object(tempfile, "TemporaryDirectory", side_effect=lambda *a, **k: original(*a, dir=TMP, **k)):
            legacy.WorkflowControlTests.setUp(self)
        registry = w.read_json(self.root / "data/department-registry.json")
        for role in ("qa-technical", "operations-assistant"):
            item = copy.deepcopy(registry["departments"][-1]); item["id"] = role
            item["chat_binding"].update(task_id="fixed-" + role, title=role)
            registry["departments"].append(item)
        w.atomic_write_json(self.root / "data/department-registry.json", registry)
        self.task_id = "runtime-qa-test-001"
        w.initialize_workflow(self.root, task_id=self.task_id, request="exact internal candidate",
                              plan_status="ready_to_send", owner_approval_required=False,
                              departments=[{"department": d, "chat_task_id": "fixed-" + d}
                                           for d in ("content-organic-website", "qa-technical")])
        self.candidate = "drafts/operations/runtime-qa-test-001/v1/candidate.json"
        self.write(self.candidate, {"task_id": self.task_id, "candidate_version": "v1",
                                   "department": "content-organic-website", "production_write_allowed": False})
        self.pin = w.file_digest(self.root, self.candidate)
        self.plan_path = "drafts/operations/runtime-qa-test-001/review-plan.json"
        self.plan = {"schema_version": 1, "task_id": self.task_id, "action_id": "review-control",
                     "action_class": "internal_control_candidate", "scope": "project:runtime-control:exact-v1",
                     "candidate_version": "v1", "candidate_sha256": self.pin["sha256"], "candidate": self.pin,
                     "producer_department": "content-organic-website", "reviewer_department": "qa-technical",
                     "reviewer_thread_id": "fixed-qa-technical", "controller_department": "operations",
                     "controller_thread_id": "fixed-operations", "single_final_reviewer": True,
                     "risk_level": "R0", "production_write_allowed": False, "external_permission_issued": False}

    def tearDown(self):
        self.temp_dir.cleanup()

    def write(self, path, payload):
        p = self.root / path; p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")

    def bind(self, **changes):
        self.plan.update(changes); self.write(self.plan_path, self.plan)
        return q.bind_plan(self.root, task_id=self.task_id, plan_path=self.plan_path)

    def box(self, role):
        return {"schema_version": "2.0", "task_id": self.task_id, "department": role,
                "fixed_chat_task_id": "fixed-" + role, "candidate_version": "v1", "status": "completed",
                "conclusion": "Synthetic internal test", "evidence": [self.pin], "risks": [], "next_actions": [],
                "handoff": {"receiver": "operations"}, "approval_required": False,
                "learning": {"status": "no_new_learning"}, "risk_level": "R0",
                "production_write_allowed": False, "external_permission_issued": False,
                "production_release_eligible": False,
                "chat_reply": {"nonempty": True, "in_current_fixed_department_chat": True,
                               "ref": "synthetic-native-reply", "sha256": "a" * 64}}

    def producer(self):
        self.receipt("dispatch_sent", "content-organic-website", "producer-dispatch")
        self.receipt("chat_ack", "content-organic-website", "producer-ack")
        path = "logs/department-outbox/producer.json"; self.write(path, self.box("content-organic-website"))
        self.receipt("outbox_received", "content-organic-website", "producer-result", evidence=path)
        return path

    def review(self, **changes):
        self.receipt("dispatch_sent", "qa-technical", "qa2-dispatch", scope=self.plan["scope"],
                     evidence=self.plan_path + ";" + self.candidate)
        self.receipt("chat_ack", "qa-technical", "qa2-ack")
        self.qa_path = "logs/department-outbox/qa2.json"
        box = self.box("qa-technical")
        box.update(review_identity={k: self.plan[k] for k in q.IDENTITY}, qa_verdict="pass")
        box.update(changes); self.write(self.qa_path, box)
        self.receipt("outbox_received", "qa-technical", "qa2-result", evidence=self.qa_path)

    def verdict(self, **changes):
        fields = {"verdict": "pass", "action_id": self.plan["action_id"],
                  "action_class": self.plan["action_class"], "scope": self.plan["scope"],
                  "evidence": self.qa_path}; fields.update(changes)
        return self.receipt("qa_verdict", "qa-technical", "qa2-verdict", **fields)

    def prepared(self, **changes):
        self.bind(); self.producer(); self.review(**changes)

    def test_real_exact_qa2_chain_closes_r0_and_keeps_role(self):
        self.prepared(); receipt = self.verdict()
        self.assertEqual(receipt["department"], "qa-technical")
        self.assertEqual(receipt["workflow_state"], "closed")
        self.assertEqual(w._validate_receipt_chain(self.root, self.task_id)[1], [])
        self.assertEqual(w.validate_workflow_events(self.root, self.task_id), [])
        self.assertEqual(w.effective_approvals(self.root), {})
        self.assertFalse(w._latest_qa_release_route(w.read_jsonl(w.receipts_path(self.root, self.task_id))))

    def test_repeated_exact_verdict_and_plan_dedup(self):
        self.prepared(); first = self.verdict(); second = self.verdict()
        self.assertEqual(first["receipt_id"], second["receipt_id"])
        self.assertEqual(second["result"], "duplicate_ignored")
        self.assertEqual(q.bind_plan(self.root, task_id=self.task_id, plan_path=self.plan_path)["result"], "duplicate_ignored")

    def test_native_queue_and_current_close_decision_use_exact_reviewer(self):
        self.prepared(); self.verdict()
        path = "logs/department-outbox/producer.json"
        identity = dict(task_id=self.task_id, sender_department="content-organic-website", candidate_version="v1",
                        result_sha256=w.file_digest(self.root, path)["sha256"], outbox_path=path)
        w.record_result_handoff(self.root, dict(identity, event="notification_queued", idempotency_key="queue"))
        w.record_result_handoff(self.root, dict(identity, event="controller_received", idempotency_key="intake",
                               intake_mode="queue", source_thread_id="fixed-content-organic-website",
                               source_reply_sha256="a" * 64, reply_observed_at=w.utc_timestamp()))
        result, _ = w.record_result_handoff(self.root, dict(identity, event="controller_decision", idempotency_key="close",
                               decision="close_scope", next_owner="operations", next_action="archive exact scope",
                               evidence_paths=[self.candidate], qa_status="pass", acceptance_scope=self.plan["scope"]))
        self.assertEqual(result["decision"], "close_scope")
        with self.assertRaises((w.WorkflowError, legacy.ops.OpsError)):
            w.record_result_handoff(self.root, dict(identity, event="controller_decision", idempotency_key="publish",
                                   decision="release_gate", next_owner="operations", next_action="publish",
                                   evidence_paths=[self.candidate], qa_status="pass"))

    def test_wrong_version_outbox_refused(self):
        self.prepared(candidate_version="v2")
        with self.assertRaises((w.WorkflowError, legacy.ops.OpsError)): self.verdict()

    def test_wrong_hash_outbox_refused(self):
        self.prepared(); box=w.read_json(self.root/self.qa_path);box["review_identity"]["candidate_sha256"]="b"*64
        # Use a new exact native outbox receipt rather than altering frozen bytes.
        path="logs/department-outbox/qa2-v2.json";self.write(path,box)
        self.receipt("outbox_received","qa-technical","qa2-result-v2",evidence=path);self.qa_path=path
        with self.assertRaises((w.WorkflowError, legacy.ops.OpsError)): self.verdict()

    def test_wrong_scope_verdict_refused(self):
        self.prepared()
        with self.assertRaises((w.WorkflowError, legacy.ops.OpsError)): self.verdict(scope="project:runtime-control:other")

    def test_wrong_action_verdict_refused(self):
        self.prepared()
        with self.assertRaises((w.WorkflowError, legacy.ops.OpsError)): self.verdict(action_id="other-action")

    def test_wrong_task_plan_refused(self):
        with self.assertRaises((w.WorkflowError, legacy.ops.OpsError)): self.bind(task_id="runtime-other-task")

    def test_wrong_candidate_hash_plan_refused(self):
        with self.assertRaises((w.WorkflowError, legacy.ops.OpsError)): self.bind(candidate_sha256="b"*64)

    def test_self_review_refused(self):
        with self.assertRaises((w.WorkflowError, legacy.ops.OpsError)): self.bind(producer_department="qa-technical")

    def test_unknown_reviewer_refused(self):
        with self.assertRaises((w.WorkflowError, legacy.ops.OpsError)): self.bind(reviewer_department="unknown")

    def test_external_class_plan_refused(self):
        for action in sorted(w.EXTERNAL_ACTION_CLASSES | {"cms_content_candidate","site_code_candidate"}):
            with self.subTest(action=action), self.assertRaises((w.WorkflowError, legacy.ops.OpsError)): self.bind(action_class=action)

    def test_production_flags_refused(self):
        with self.assertRaises((w.WorkflowError, legacy.ops.OpsError)): self.bind(production_write_allowed=True)

    def test_assistant_cannot_bind_final_reviewer(self):
        self.write(self.plan_path,self.plan)
        with self.assertRaises((w.WorkflowError, legacy.ops.OpsError)):
            q.bind_plan(self.root,task_id=self.task_id,plan_path=self.plan_path,coordinator_role="operations-assistant")

    def test_missing_actual_dispatch_refused(self):
        self.bind(); self.producer(); self.qa_path="logs/department-outbox/forged.json"
        self.write(self.qa_path,self.box("qa-technical"))
        with self.assertRaises((w.WorkflowError, legacy.ops.OpsError)): self.verdict()

    def test_missing_actual_ack_refused(self):
        self.bind();self.producer()
        self.receipt("dispatch_sent","qa-technical","dispatch",scope=self.plan["scope"],evidence=self.plan_path+";"+self.candidate)
        with self.assertRaises((w.WorkflowError, legacy.ops.OpsError)):
            self.receipt("outbox_received","qa-technical","forged",evidence=self.candidate)

    def test_cross_candidate_dispatch_refused(self):
        self.bind();self.producer();self.review()
        self.receipt("dispatch_sent","qa-technical","new-send",scope=self.plan["scope"],evidence=self.plan_path)
        self.receipt("chat_ack","qa-technical","new-ack")
        self.receipt("outbox_received","qa-technical","new-result",evidence=self.qa_path)
        with self.assertRaises((w.WorkflowError, legacy.ops.OpsError)): self.verdict()

    def test_no_reply_metadata_refused(self):
        self.prepared(chat_reply={})
        with self.assertRaises((w.WorkflowError, legacy.ops.OpsError)): self.verdict()

    def test_no_production_release_eligibility(self):
        self.prepared(production_release_eligible=True)
        with self.assertRaises((w.WorkflowError, legacy.ops.OpsError)): self.verdict()

    def test_candidate_changed_after_binding_refused(self):
        self.bind();self.write(self.candidate,{"task_id":self.task_id,"candidate_version":"v2"})
        with self.assertRaises((w.WorkflowError, legacy.ops.OpsError)): self.producer()

    def test_changed_frozen_plan_refused(self):
        self.bind();self.plan["scope"]="project:changed";self.write(self.plan_path,self.plan)
        with self.assertRaises((w.WorkflowError, legacy.ops.OpsError)): q.load_plan(self.root,w.read_json(w.snapshot_path(self.root,self.task_id)))

    def test_no_explicit_plan_never_aliases_qa2(self):
        self.producer();self.qa_path="logs/department-outbox/qa2.json";self.write(self.qa_path,self.box("qa-technical"))
        with self.assertRaises((w.WorkflowError, legacy.ops.OpsError)): self.verdict()

    def test_snapshot_loss_recovers_exact_plan_from_events(self):
        self.prepared();self.verdict();w.snapshot_path(self.root,self.task_id).unlink()
        result,_=w.reconcile_workflow(self.root,task_id=self.task_id)
        self.assertEqual(result["current_state"],"closed")
        self.assertEqual(q.reviewer_department(self.root,result),"qa-technical")

    def test_exact_blocked_verdict_remains_rework(self):
        self.prepared(qa_verdict="blocked")
        result=self.verdict(verdict="blocked")
        self.assertEqual(result["workflow_state"],"qa_blocked")

    def test_forged_hashed_verdict_without_dispatch_is_invalid_native_chain(self):
        self.bind();self.producer()
        self.qa_path="logs/department-outbox/forged-qa2.json";box=self.box("qa-technical")
        box.update(review_identity={k:self.plan[k] for k in q.IDENTITY},qa_verdict="pass")
        self.write(self.qa_path,box)
        path=w.receipts_path(self.root,self.task_id);rows=w.read_jsonl(path)
        forged=copy.deepcopy(rows[-1]);forged.update(receipt_type="qa_verdict",department="qa-technical",
                    chat_task_id="fixed-qa-technical",receipt_id="synthetic-forged-verdict",verdict="pass",
                    action_id=self.plan["action_id"],action_class=self.plan["action_class"],scope=self.plan["scope"],
                    evidence=[w.file_digest(self.root,self.qa_path)],idempotency_key="forged",
                    previous_hash=rows[-1]["receipt_hash"],created_at=w.utc_timestamp())
        forged["receipt_hash"]=w.sha256_value(w._receipt_payload_for_hash(forged))
        w.append_jsonl_locked(path,forged)
        invalid=w._validate_receipt_chain(self.root,self.task_id)[1]
        self.assertTrue(any("actual reviewer dispatch required" in x for x in invalid))
        state,_=w.reconcile_workflow(self.root,task_id=self.task_id)
        self.assertEqual(state["current_state"],"blocked_evidence_invalid")

    def test_future_ack_cannot_produce_verdict_even_with_rehashed_chain(self):
        self.prepared();path=w.receipts_path(self.root,self.task_id);rows=w.read_jsonl(path)
        for row in rows:
            if row["receipt_type"]=="chat_ack" and row["department"]=="qa-technical":
                row["created_at"]=(dt.datetime.now(dt.timezone.utc)+dt.timedelta(minutes=1)).isoformat()
        previous=""
        for row in rows:
            row["previous_hash"]=previous;row["receipt_hash"]=w.sha256_value(w._receipt_payload_for_hash(row));previous=row["receipt_hash"]
        path.write_text("".join(json.dumps(row)+"\n" for row in rows))
        with self.assertRaises((w.WorkflowError,legacy.ops.OpsError)):self.verdict()

    def test_other_reviewer_cannot_replace_exact_planned_qa2(self):
        self.prepared()
        with self.assertRaises((w.WorkflowError,legacy.ops.OpsError)):
            self.receipt("qa_verdict","qa","wrong-reviewer",verdict="pass",evidence=self.qa_path)

    def test_read_only_candidate_uses_same_exact_r0_chain(self):
        self.bind(action_class="read_only_candidate");self.producer();self.review()
        result=self.verdict()
        self.assertEqual(result["workflow_state"],"closed")
        self.assertEqual(w.effective_approvals(self.root),{})

    def queue_intake_for_followthrough(self):
        path="logs/department-outbox/producer.json"
        identity=dict(task_id=self.task_id,sender_department="content-organic-website",candidate_version="v1",
                      result_sha256=w.file_digest(self.root,path)["sha256"],outbox_path=path)
        w.record_result_handoff(self.root,dict(identity,event="notification_queued",idempotency_key="queued-for-QA"))
        w.record_result_handoff(self.root,dict(identity,event="controller_received",idempotency_key="intake-for-QA",
                     intake_mode="queue",source_thread_id="fixed-content-organic-website",
                     source_reply_sha256="a"*64,reply_observed_at=w.utc_timestamp()))
        w.record_result_handoff(self.root,dict(identity,event="controller_decision",idempotency_key="send-qa2",
                     decision="send_qa",next_owner="qa-technical",next_action="review exact R0 candidate",
                     evidence_paths=[self.plan_path,self.candidate]))
        return identity

    def test_native_same_task_prior_qa2_result_closes_send_qa_followthrough(self):
        with mock.patch.object(w,"utc_timestamp",side_effect=lambda:dt.datetime.now(dt.timezone.utc).isoformat()):
            self.prepared();self.verdict();identity=self.queue_intake_for_followthrough()
            row=next(r for r in w.read_jsonl(w.receipts_path(self.root,self.task_id))
                     if r["receipt_type"]=="outbox_received" and r["department"]=="qa-technical")
            result,_=w.record_result_handoff(self.root,dict(identity,event="controller_followthrough",idempotency_key="prior-qa2",
                    followthrough_status="prior_action_verified",linked_task_id=self.task_id,
                    action_receipt_id=row["receipt_id"],linked_outbox_path=self.qa_path,evidence_paths=[self.qa_path]))
            self.assertTrue(result["action_before_decision"])
            self.assertFalse(result["business_goal_closed"])

    def test_native_same_task_inflight_qa2_result_closes_send_qa_followthrough(self):
        with mock.patch.object(w,"utc_timestamp",side_effect=lambda:dt.datetime.now(dt.timezone.utc).isoformat()):
            self.bind();self.producer()
            sent=self.receipt("dispatch_sent","qa-technical","qa2-dispatch",scope=self.plan["scope"],
                        evidence=self.plan_path+";"+self.candidate)
            self.receipt("chat_ack","qa-technical","qa2-ack")
            identity=self.queue_intake_for_followthrough()
            self.qa_path="logs/department-outbox/qa2-inflight.json";box=self.box("qa-technical")
            box.update(review_identity={k:self.plan[k] for k in q.IDENTITY},qa_verdict="pass")
            self.write(self.qa_path,box)
            row=self.receipt("outbox_received","qa-technical","qa2-after-decision",evidence=self.qa_path);self.verdict()
            result,_=w.record_result_handoff(self.root,dict(identity,event="controller_followthrough",idempotency_key="inflight-qa2",
                    followthrough_status="inflight_result_verified",linked_task_id=self.task_id,
                    action_receipt_id=row["receipt_id"],linked_dispatch_receipt_id=sent["receipt_id"],
                    linked_outbox_path=self.qa_path,evidence_paths=[self.qa_path]))
            self.assertTrue(result["dispatch_before_decision"])
            self.assertTrue(result["result_after_decision"])
            self.assertFalse(result["business_goal_closed"])


if __name__ == "__main__": unittest.main()
