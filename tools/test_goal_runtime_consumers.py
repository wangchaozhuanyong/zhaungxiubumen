"""Real local entry points in synthetic fixtures; not a native chat pilot."""
import argparse
import contextlib
import copy
import datetime as dt
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import controller_stop_hook as stop
import flashcast_ops as ops
import goal_delivery_runtime as runtime
import qa_review_plan as review
import result_coordination as coordination
import test_goal_result_coordination as claims
import test_workflow_control as legacy
import workflow_control as w

TMP = Path(__file__).resolve().parents[1] / ".test-tmp"
ASSISTANT = "operations-assistant-2"
PRODUCER = "content-organic-website"


class GoalRuntimeConsumerTests(unittest.TestCase):
    def setUp(self):
        TMP.mkdir(parents=True, exist_ok=True)
        self.fixture = legacy.WorkflowControlTests("runTest")
        original = tempfile.TemporaryDirectory
        with mock.patch.object(tempfile, "TemporaryDirectory", side_effect=lambda *a, **k: original(*a, dir=TMP, **k)):
            self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.root = self.fixture.root
        claims.configure(self.root)
        registry = w.read_json(self.root / "data/department-registry.json")
        for row in registry["departments"]:
            if row.get("coordination_authority"):
                row["coordination_authority"]["dispatch_approved_next"] = True
        w.atomic_write_json(self.root / "data/department-registry.json", registry)
        self.task_id = "goal-consumer-test-001"

    def write(self, path, value):
        w.atomic_write_json(self.root / path, value)
        return path

    def make_goal(self, **changes):
        goal = {**claims.goal(ASSISTANT), "authorized_scope": ["department:" + PRODUCER], **changes}
        goal["human_authorization"] = {**goal["human_authorization"], "scope": goal["authorized_scope"][0]}
        return goal

    def initialize(self, **changes):
        path = self.write("drafts/operations/consumer-goal.json", self.make_goal(**changes))
        plan = runtime.initialize_goal(self.root, self.task_id, path)
        self.fixture.task_id = self.task_id
        self.fixture.routing_decisions = {}
        return plan

    def snapshot(self):
        return w.read_json(w.snapshot_path(self.root, self.task_id))

    def requested(self, sender=ASSISTANT, target=PRODUCER, scope=None, payload=None):
        binding = w.department_registry(self.root)[target]["chat_binding"]
        if payload is None:
            path = "drafts/operations/approved-message.txt"
            w.safe_path(self.root, path).parent.mkdir(parents=True, exist_ok=True)
            w.safe_path(self.root, path).write_text("Synthetic bounded next instruction; no actual send.")
            payload = w.file_digest(self.root, path)
        return {"task_id": self.task_id, "sender_department": sender,
                "source_project_id": "flashcast-test-project", "target_project_id": binding["project_id"],
                "target_department": target, "target_thread_id": binding["task_id"], "target_thread_title": binding["title"],
                "target_cwd": binding["cwd"], "target_sidebar_section_id": binding["sidebar_section_id"],
                "payload_sha256": payload["sha256"], "action_id": "bounded-next-" + target,
                "action_class": "thread_message", "scope": scope or "department:" + target, "payload": payload}

    def policy(self, request):
        fields = {k: v for k, v in request.items() if k not in {"sender_department", "payload", "live_identity", "decision_record_id"}}
        return w.policy_check(self.root, department=request["sender_department"], **fields)[0]

    def dispatch(self, department=PRODUCER):
        request = self.requested(sender="operations", target=department)
        decision = self.policy(request)
        self.assertEqual(decision["status"], "allow", decision.get("reason"))
        return self.fixture.receipt("dispatch_sent", department, "actual-local-dispatch-" + department,
                                    policy_decision_id=decision["decision_id"], action_id=request["action_id"],
                                    action_class="thread_message", scope=request["scope"])

    def preflight(self, scope="flashcast.com.my:synthetic-exact-result"):
        identity = {"action_id": "synthetic-exact-publish", "action_class": "site_publish",
                    "scope": scope, "department": PRODUCER}
        item = {**identity, "risk_level": "R2"}
        for name in ("facts", "self_check", "backup", "rollback"):
            path = "reports/synthetic-preflight-" + name + ".json"
            self.write(path, {**identity, "fixture_only": True, "status": "PASS"})
            item[name] = w.file_digest(self.root, path)
        return item

    def initial_assignment(self):
        contract = self.snapshot()["goal_contract"]
        request = self.requested(sender="operations", target=ASSISTANT,
                                 scope=self.snapshot()["goal_delivery"]["authorized_scope"][0], payload=contract)
        request["action_id"] = "assign-goal-review:" + self.task_id
        decision = self.policy(request)
        self.assertEqual(decision["status"], "allow", decision.get("reason"))
        self.fixture.receipt("dispatch_sent", ASSISTANT, "initial-complete-goal-assignment",
                             policy_decision_id=decision["decision_id"], action_id=request["action_id"],
                             action_class="thread_message", scope=request["scope"], evidence=contract["path"])
        self.fixture.receipt("chat_ack", ASSISTANT, "initial-complete-goal-ack")

    def result_box(self, role, version, candidate):
        return {"schema_version": "2.0", "task_id": self.task_id, "department": role,
                "fixed_chat_task_id": "fixed-" + role, "candidate_version": version, "status": "completed",
                "conclusion": "Synthetic local complete-goal result", "evidence": [candidate], "risks": [],
                "next_actions": [], "handoff": {"receiver": ASSISTANT}, "approval_required": False,
                "learning": {"status": "no_new_learning"}, "risk_level": "R0", "production_write_allowed": False,
                "external_permission_issued": False, "production_release_eligible": False,
                "chat_reply": {"nonempty": True, "in_current_fixed_department_chat": True,
                               "ref": "synthetic-local-only-reply", "sha256": "a" * 64}}

    def producer_result(self, version="v1"):
        candidate_path = self.write("drafts/operations/" + self.task_id + "/" + version + "/candidate.json",
                                    {"fixture_only": True, "task_id": self.task_id, "department": PRODUCER,
                                     "candidate_version": version, "content": "Synthetic changed result " + version})
        candidate = w.file_digest(self.root, candidate_path)
        producer_path = self.write("logs/department-outbox/goal-producer-" + version + ".json",
                                   self.result_box(PRODUCER, version, candidate))
        self.fixture.receipt("outbox_received", PRODUCER, "producer-result-" + version, evidence=producer_path)
        return candidate, w.file_digest(self.root, producer_path)

    def review_plan(self, candidate):
        return {"schema_version": 1, "task_id": self.task_id, "action_id": "review-complete-goal",
                "action_class": "internal_control_candidate", "scope": self.snapshot()["goal_delivery"]["authorized_scope"][0],
                "candidate_version": w.read_json(w.safe_path(self.root, candidate["path"]))["candidate_version"],
                "candidate_sha256": candidate["sha256"], "candidate": candidate,
                "producer_department": PRODUCER, "reviewer_department": ASSISTANT, "reviewer_thread_id": "fixed-" + ASSISTANT,
                "controller_department": ASSISTANT, "controller_thread_id": "fixed-" + ASSISTANT,
                "single_final_reviewer": True, "risk_level": "R0", "production_write_allowed": False,
                "external_permission_issued": False}

    def assistant_verdict(self, plan, producer_pin, verdict="pass", **box_changes):
        binding = self.snapshot()["qa_review_plan"]
        box = self.result_box(ASSISTANT, plan["candidate_version"], plan["candidate"])
        goal = self.snapshot()["goal_delivery"]
        box.update(evidence=[binding["pin"], plan["candidate"]], qa_verdict=verdict,
                   review_identity={key: plan[key] for key in review.IDENTITY},
                   goal_acceptance={**{key: goal[key] for key in ("completion_criteria", "primary_owner", "responsible_assistant")},
                                    "accepted_scope": goal["authorized_scope"] if verdict == "pass" else [],
                                    "remaining_scope": [] if verdict == "pass" else ["correct synthetic candidate result"],
                                    "producer_results": {PRODUCER: producer_pin}})
        box.update(box_changes)
        path = self.write("logs/department-outbox/goal-reviewer-" + plan["candidate_version"] + ".json", box)
        self.fixture.receipt("outbox_received", ASSISTANT, "reviewer-result-" + plan["candidate_version"], evidence=path)
        return self.fixture.receipt("qa_verdict", ASSISTANT, "reviewer-verdict-" + plan["candidate_version"],
                                    evidence=path, verdict=verdict, **{key: plan[key] for key in ("action_id", "action_class", "scope")})

    def prepare_initial_review(self):
        self.initialize(); self.initial_assignment(); self.dispatch()
        self.fixture.receipt("chat_ack", PRODUCER, "producer-ack-v1")
        candidate, producer_pin = self.producer_result()
        plan = self.review_plan(candidate)
        path = self.write("drafts/operations/" + self.task_id + "/v1/review-plan.json", plan)
        review.bind_plan(self.root, task_id=self.task_id, plan_path=path, coordinator_role=ASSISTANT)
        return plan, producer_pin

    def test_initial_goal_assignment_ack_producer_result_assistant_bind_and_final_accept(self):
        plan, producer_pin = self.prepare_initial_review()
        verdict = self.assistant_verdict(plan, producer_pin)
        self.assertEqual(verdict["workflow_state"], "closed")
        receipts, invalid = w._validate_receipt_chain(self.root, self.task_id)
        self.assertEqual(invalid, [])
        review_dispatches = [row for row in receipts if row["department"] == ASSISTANT and row["receipt_type"] == "dispatch_sent"]
        self.assertEqual(len(review_dispatches), 1)
        self.assertEqual(review_dispatches[0]["action_id"], "assign-goal-review:" + self.task_id)
        self.assertNotIn(plan["candidate"], review_dispatches[0]["evidence"])
        self.assertNotIn(self.snapshot()["qa_review_plan"]["pin"], review_dispatches[0]["evidence"])
        self.assertEqual(w.validate_workflow_events(self.root, self.task_id), [])

    def test_initial_assignment_final_outbox_still_requires_current_exact_plan_and_candidate(self):
        plan, producer_pin = self.prepare_initial_review()
        with self.assertRaisesRegex((w.WorkflowError, ops.OpsError), "actual review plan and candidate"):
            self.assistant_verdict(plan, producer_pin, evidence=[plan["candidate"]])

    def test_initial_assignment_rejects_other_contract_payload_before_producers(self):
        self.initialize()
        request = self.requested(sender="operations", target=ASSISTANT,
                                 scope=self.snapshot()["goal_delivery"]["authorized_scope"][0])
        request["action_id"] = "assign-goal-review:" + self.task_id
        self.assertEqual(self.policy(request)["status"], "deny")

    def blocked_rework_plan(self):
        plan, producer_pin = self.prepare_initial_review()
        blocked = self.assistant_verdict(plan, producer_pin, verdict="blocked")
        self.assertEqual(blocked["workflow_state"], "qa_blocked")
        old_binding = self.snapshot()["qa_review_plan"]
        candidate, new_producer_pin = self.producer_result("v2")
        new = {**plan, "candidate": candidate, "candidate_sha256": candidate["sha256"], "candidate_version": "v2",
               "rework_of": blocked["receipt_id"], "changed_scope": [plan["scope"]],
               "evidence_diff": {"previous_candidate": plan["candidate"], "candidate": candidate,
                                 "summary": "Synthetic v2 repairs the exact blocked behavior."},
               "revalidation_methods": {plan["scope"]: "Repeat the changed behavior and retain complete-goal criteria."}}
        path = self.write("drafts/operations/" + self.task_id + "/v2/review-plan.json", new)
        return new, new_producer_pin, path, old_binding, blocked

    def test_blocked_same_task_producer_new_version_assistant_rebind_pass_preserves_old_chain(self):
        plan, producer_pin, path, old, blocked = self.blocked_rework_plan()
        bound = review.bind_plan(self.root, task_id=self.task_id, plan_path=path, coordinator_role=ASSISTANT)
        self.assertEqual(bound["result"], "recorded")
        self.assertIn(old, self.snapshot()["qa_review_plan_history"])
        final = self.assistant_verdict(plan, producer_pin, revalidation={"changed_scope": plan["changed_scope"],
                                                                       "methods": plan["revalidation_methods"]})
        self.assertEqual(final["workflow_state"], "closed")
        receipts, invalid = w._validate_receipt_chain(self.root, self.task_id)
        self.assertEqual(invalid, [])
        self.assertEqual([row["verdict"] for row in receipts if row["receipt_type"] == "qa_verdict"], ["blocked", "pass"])
        self.assertEqual(next(row for row in receipts if row["receipt_id"] == blocked["receipt_id"]),
                         {key: value for key, value in blocked.items() if key not in {"result", "workflow_state"}})
        self.assertEqual(w.validate_workflow_events(self.root, self.task_id), [])
        # Recover both bindings from append-only events, not rewritten plan bytes.
        snapshot = self.snapshot(); snapshot.pop("qa_review_plan_history"); snapshot.pop("qa_review_plan")
        w.atomic_write_json(w.snapshot_path(self.root, self.task_id), snapshot)
        self.assertEqual(w._validate_receipt_chain(self.root, self.task_id)[1], [])
        w.snapshot_path(self.root, self.task_id).unlink()
        self.assertEqual(w._validate_receipt_chain(self.root, self.task_id)[1], [])
        rebuilt, _ = w.reconcile_workflow(self.root, task_id=self.task_id)
        self.assertEqual(rebuilt["current_state"], "closed")
        self.assertEqual(rebuilt["goal_delivery"]["responsible_assistant"], ASSISTANT)

    def test_rework_requires_exact_latest_blocked_diff_scope_new_version_and_methods(self):
        plan, _, path, old, _ = self.blocked_rework_plan()
        for changes in ({"rework_of": "unrelated-blocked-receipt"}, {"changed_scope": ["foreign:scope"]},
                        {"candidate_version": "v1"}, {"revalidation_methods": {}},
                        {"evidence_diff": {"summary": "missing exact pins"}}, {"scope": "department:paid-growth-data"}):
            with self.subTest(changes=changes):
                self.write(path, {**plan, **changes})
                with self.assertRaises(w.WorkflowError):
                    review.bind_plan(self.root, task_id=self.task_id, plan_path=path, coordinator_role=ASSISTANT)
                self.assertEqual(self.snapshot()["qa_review_plan"], old)

    def test_current_rework_verdict_requires_changed_scope_revalidation_description(self):
        plan, producer_pin, path, _, _ = self.blocked_rework_plan()
        review.bind_plan(self.root, task_id=self.task_id, plan_path=path, coordinator_role=ASSISTANT)
        with self.assertRaisesRegex((w.WorkflowError, ops.OpsError), "revalidation methods"):
            self.assistant_verdict(plan, producer_pin)

    def test_pass_cannot_be_reopened_as_rework(self):
        plan, producer_pin = self.prepare_initial_review()
        passed = self.assistant_verdict(plan, producer_pin)
        candidate_path = self.write("drafts/operations/" + self.task_id + "/v2/candidate.json",
                                    {"task_id": self.task_id, "candidate_version": "v2", "department": PRODUCER})
        candidate = w.file_digest(self.root, candidate_path)
        path = self.write("drafts/operations/" + self.task_id + "/v2/review-plan.json",
                          {**plan, "candidate": candidate, "candidate_sha256": candidate["sha256"],
                           "candidate_version": "v2", "rework_of": passed["receipt_id"]})
        with self.assertRaisesRegex(w.WorkflowError, "PASS cannot reopen"):
            review.bind_plan(self.root, task_id=self.task_id, plan_path=path, coordinator_role=ASSISTANT)

    def routine_decision(self, producer_pin, decision="rework"):
        identity = {"task_id": self.task_id, "sender_department": PRODUCER,
                    "candidate_version": "v1", "outbox_path": producer_pin["path"], "result_sha256": producer_pin["sha256"]}
        w.record_result_handoff(self.root, {**identity, "event": "notification_queued", "idempotency_key": "queue-routine-result"})
        store = coordination.CoordinationStore(self.root); self.addCleanup(store.close)
        lease = store.claim(identity, ASSISTANT, "synthetic-assistant-owner", "claim-routine-result")
        actor = {"coordinator_role": ASSISTANT, "coordinator_owner": lease["owner"], "coordination_claim": lease}
        w.record_result_handoff(self.root, {**identity, **actor, "event": "controller_received", "idempotency_key": "receive-routine-result",
                                "intake_mode": "queue", "source_thread_id": "fixed-" + PRODUCER,
                                "source_reply_sha256": "a" * 64, "reply_observed_at": w.utc_timestamp()})
        row, _ = w.record_result_handoff(self.root, {**identity, **actor, "event": "controller_decision", "idempotency_key": "decide-routine-result",
                 "decision": decision, "next_owner": PRODUCER, "next_action": "correct exact original authorized behavior",
                 "evidence_paths": [producer_pin["path"]]})
        return row

    def test_approved_action_record_requires_real_claimed_decision_and_does_not_send(self):
        plan, producer_pin = self.prepare_initial_review()
        self.assistant_verdict(plan, producer_pin, verdict="blocked")
        request = self.requested(); request["action_id"] = "rework-producer-v2"
        path = self.write("reports/synthetic-approved-next.json", {**request, "decision_record_id": "missing"})
        with self.assertRaisesRegex(w.WorkflowError, "actual assigned routine decision"):
            runtime.record_approved_action(self.root, self.task_id, path)
        decision = self.routine_decision(producer_pin)
        request["decision_record_id"] = decision["record_id"]; self.write(path, request)
        saved = runtime.record_approved_action(self.root, self.task_id, path)
        self.assertFalse(saved["actual_message_sent"]); self.assertFalse(saved["external_permission_issued"])
        self.assertEqual(runtime.record_approved_action(self.root, self.task_id, path)["result"], "duplicate_ignored")
        self.assertEqual(self.policy(request)["status"], "allow")
        receipts, invalid = w._validate_receipt_chain(self.root, self.task_id)
        self.assertEqual(invalid, [])
        self.assertEqual(len([row for row in receipts if row["department"] == PRODUCER and row["receipt_type"] == "dispatch_sent"]), 1)
        for changes in ({"sender_department": "operations-assistant-3"}, {"scope": "foreign:scope"},
                        {"target_thread_id": "other-thread"}, {"payload_sha256": "b" * 64}):
            self.write(path, {**request, **changes})
            with self.assertRaises(w.WorkflowError): runtime.record_approved_action(self.root, self.task_id, path)

    def test_complete_goal_init_uses_exact_producer_and_single_assistant_route(self):
        plan = self.initialize()
        self.assertEqual(plan["route"]["source"], "complete_goal")
        self.assertEqual(plan["parallel_departments"], [PRODUCER])
        self.assertEqual(plan["follow_up_departments"], [ASSISTANT])
        self.assertEqual(plan["department_dependencies"][ASSISTANT], [PRODUCER])
        self.assertFalse(plan["controller_may_execute_specialist_work"])
        self.assertEqual(w.read_jsonl(self.root / w.RECEIPTS_DIR / (self.task_id + ".jsonl")), [])
        self.assertNotIn("qa", {r["department"] for r in self.snapshot()["departments"]})

    def test_daily_growth_new_goal_hands_to_assistant_and_legacy_still_requires_qa(self):
        self.initialize()
        artifact = self.write("reports/synthetic-daily-growth-artifact.json", {"fixture_only": True, "actual_local_delta": "fixture"})
        box = {"task_id": self.task_id, "promotion_gap_matrix": {key: "synthetic checked" for key in w.PROMOTION_GAP_CATEGORIES},
               "growth_delivery": {"backlog_item_id": "synthetic-growth-item", "previous_status": "planned",
                   "current_status": "candidate_ready", "artifact_type": "internal_candidate", "artifact_path": artifact,
                   "assistant_handoff_status": "ready_for_assistant_acceptance"},
               "evidence": {"growth_artifact": artifact}, "handoff": {"receiver": ASSISTANT}}
        w.validate_content_growth_daily_output(self.root, box)
        with self.assertRaises(w.WorkflowError):
            w.validate_content_growth_daily_output(self.root, {**box, "handoff": {"receiver": "qa"}})
        box["task_id"] = "workflow-test-001"
        with self.assertRaises(w.WorkflowError): w.validate_content_growth_daily_output(self.root, box)
        box["growth_delivery"]["qa_handoff_status"] = "ready_for_qa"; box["handoff"] = {"receiver": "qa"}
        w.validate_content_growth_daily_output(self.root, box)

    def test_incomplete_goal_and_self_review_rejected_before_workflow_creation(self):
        for changes in ({"completion_criteria": []}, {"producer_departments": []}, {"responsible_assistant": PRODUCER},
                        {"authorized_scope": [{"scope": "dict-is-not-exact-string"}]}):
            with self.subTest(changes=changes), self.assertRaises((w.WorkflowError, ops.OpsError)):
                self.initialize(**changes)
        self.assertFalse(w.snapshot_path(self.root, self.task_id).exists())

    def test_init_cli_is_plan_only_and_reports_no_chat_side_effects(self):
        self.write("drafts/operations/consumer-goal.json", self.make_goal())
        output = io.StringIO()
        with mock.patch("sys.argv", ["goal-delivery", "--project-root", str(self.root), "init", "--task-id", self.task_id,
                                    "--input", "drafts/operations/consumer-goal.json"]), contextlib.redirect_stdout(output):
            self.assertEqual(runtime.main(), 0)
        self.assertEqual(json.loads(output.getvalue())["mode"], "plan_only_no_chat_side_effects")
        self.assertEqual(w._validate_receipt_chain(self.root, self.task_id)[0], [])

    def test_owner_direct_accepts_real_local_ack_without_fabricated_hq_dispatch(self):
        self.initialize(source_mode="owner_direct")
        self.assertTrue(runtime.owner_direct(self.root, self.snapshot(), PRODUCER))
        self.fixture.receipt("chat_ack", PRODUCER, "synthetic-owner-direct-ack")
        rows, errors = w._validate_receipt_chain(self.root, self.task_id)
        self.assertFalse(errors)
        self.assertEqual([r["receipt_type"] for r in rows], ["chat_ack"])
        self.assertNotIn("dispatch_sent:" + PRODUCER, w.reconcile_workflow(self.root, task_id=self.task_id)[0]["missing_receipts"])

    def test_changed_human_source_invalidates_owner_direct_provenance(self):
        self.initialize(source_mode="owner_direct")
        self.write("reports/synthetic-owner-message.json", {"changed": True})
        self.assertFalse(runtime.owner_direct(self.root, self.snapshot(), PRODUCER))
        with self.assertRaisesRegex(w.WorkflowError, "authorization changed"):
            runtime.restore_goal(self.root, self.snapshot())

    def test_exact_approved_assistant_payload_allows_ordinary_dispatch_receipt(self):
        requested = self.requested()
        self.initialize(approved_actions=[requested])
        decision = self.policy(requested)
        self.assertEqual(decision["status"], "allow", decision["reason"])
        self.assertEqual(decision["department"], ASSISTANT)
        self.fixture.receipt("dispatch_sent", PRODUCER, "synthetic-assistant-dispatch",
                             policy_decision_id=decision["decision_id"], action_id=requested["action_id"],
                             action_class="thread_message", scope=requested["scope"])
        self.assertEqual(w._validate_receipt_chain(self.root, self.task_id)[1], [])

    def test_goal_scope_alone_cannot_authorize_unapproved_or_changed_assistant_message(self):
        requested = self.requested(); self.initialize()
        denied = self.policy(requested)
        self.assertEqual(denied["status"], "deny")
        self.assertIn("goal_assistant_exact_approved_next_message_required", denied["reason"])

    def test_changed_frozen_payload_or_wrong_assistant_is_rejected(self):
        requested = self.requested(); self.initialize(approved_actions=[requested])
        self.assertEqual(self.policy({**requested, "sender_department": "operations-assistant-3"})["status"], "deny")
        w.safe_path(self.root, requested["payload"]["path"]).write_text("Changed synthetic message")
        self.assertEqual(self.policy(requested)["status"], "deny")

    def test_wait_has_only_real_dispatched_inflight_for_assigned_assistant(self):
        self.initialize()
        self.assertEqual(runtime.wait_plan(self.root, ASSISTANT)["batches"], [])
        self.dispatch()
        plan = runtime.wait_plan(self.root, ASSISTANT, {"fixed-" + PRODUCER: "cursor-one"})
        self.assertEqual(plan["batches"], [[{"threadId": "fixed-" + PRODUCER, "afterCursor": "cursor-one"}]])
        self.assertEqual(plan["timeoutMs"], 60000)
        self.assertEqual(runtime.wait_plan(self.root, "operations-assistant-3")["batches"], [])
        self.assertFalse(plan["native_wakeup_guaranteed"])
        self.assertFalse(plan["creates_automation"])

    def test_pending_and_wait_ignore_unrelated_legacy_or_other_assistant_corrupted_ledgers(self):
        plan, producer_pin = self.prepare_initial_review()
        foreign = copy.deepcopy(self.snapshot()); foreign["task_id"] = "goal-other-assistant-001"
        foreign["goal_delivery"]["responsible_assistant"] = "operations-assistant-3"
        foreign["goal_delivery"]["authorization_pin"] = {"path": "missing-unrelated-proof.json", "sha256": "f" * 64}
        w.atomic_write_json(w.snapshot_path(self.root, foreign["task_id"]), foreign)
        for task in ("workflow-test-001", foreign["task_id"]):
            path = w.result_handoff_path(self.root, task); path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("invalid unrelated local fixture ledger\n")
            w.receipts_path(self.root, task).write_text("invalid unrelated local fixture receipt\n")
        self.assertEqual(runtime.wait_plan(self.root, ASSISTANT)["batches"], [[{"threadId": "fixed-" + PRODUCER}]])
        identity = {"task_id": self.task_id, "sender_department": PRODUCER, "candidate_version": "v1",
                    "outbox_path": producer_pin["path"], "result_sha256": producer_pin["sha256"]}
        w.record_result_handoff(self.root, {**identity, "event": "notification_queued", "idempotency_key": "owned-queue"})
        pending = runtime.pending(self.root, ASSISTANT)
        self.assertEqual(pending["pending_count"], 1)
        self.assertEqual(pending["pending"][0]["task_id"], self.task_id)
        self.assertEqual(runtime.wait_plan(self.root, ASSISTANT)["batches"], [])
        w.result_handoff_path(self.root, self.task_id).write_text("invalid owned fixture ledger\n")
        with self.assertRaises((ValueError, w.WorkflowError)): runtime.pending(self.root, ASSISTANT)

    def test_retired_registered_role_cannot_receive_new_dispatch_but_old_receipt_is_readable(self):
        self.initialize(); self.dispatch()
        registry = w.read_json(self.root / "data/department-registry.json")
        next(row for row in registry["departments"] if row["id"] == PRODUCER)["new_dispatch_enabled"] = False
        w.atomic_write_json(self.root / "data/department-registry.json", registry)
        request = self.requested(sender="operations"); request["action_id"] = "new-retired-role-dispatch"
        self.assertEqual(self.policy(request)["status"], "deny")
        self.assertEqual(w._validate_receipt_chain(self.root, self.task_id)[1], [])

    def test_wait_batches_dynamic_nine_registered_producers_and_limits_eight(self):
        registry = w.read_json(self.root / "data/department-registry.json")
        template = copy.deepcopy(next(r for r in registry["departments"] if r["id"] == PRODUCER))
        producers = [PRODUCER]
        for i in range(8):
            role = "synthetic-specialist-" + str(i)
            row = copy.deepcopy(template); row["id"] = role
            row["chat_binding"].update(task_id="fixed-" + role, title=role)
            registry["departments"].append(row); producers.append(role)
        w.atomic_write_json(self.root / "data/department-registry.json", registry)
        self.initialize(producer_departments=producers, authorized_scope=["department:" + role for role in producers])
        for producer in producers: self.dispatch(producer)
        plan = runtime.wait_plan(self.root, ASSISTANT)
        self.assertEqual(sorted(map(len, plan["batches"])), [1, 8])
        self.assertEqual(len({x["threadId"] for batch in plan["batches"] for x in batch}), 9)

    def test_wait_cursor_record_binds_batch_and_does_not_prove_next_action(self):
        self.initialize(); self.dispatch()
        begin = self.write("reports/wait-begin.json", {"targets": runtime.wait_plan(self.root, ASSISTANT)["batches"][0]})
        batch = runtime.begin_wait(self.root, ASSISTANT, begin)
        record = {"batch_id": batch["batch_id"], "fixture_only": True, "tool": "mcp__codex_app__wait_threads", "native_receipt_ref": "synthetic-wait-receipt",
                  "timeoutMs": 60000, "cursors": {"fixed-" + PRODUCER: "cursor-two"}}
        path = self.write("reports/synthetic-native-wait.json", record)
        saved = runtime.record_wait(self.root, ASSISTANT, path)
        self.assertEqual(saved["cursors"], record["cursors"]); self.assertFalse(saved["proves_next_action"])
        record["cursors"] = {"other-project-thread": "foreign-cursor"}; self.write(path, record)
        with self.assertRaisesRegex(w.WorkflowError, "in-flight batch"):
            runtime.record_wait(self.root, ASSISTANT, path)
        self.write(path, {**record, "cursors": {}, "timeoutMs": 60001})
        with self.assertRaisesRegex(w.WorkflowError, "bounded"):
            runtime.record_wait(self.root, ASSISTANT, path)

    def test_production_preflight_late_record_is_frozen_and_not_a_permit(self):
        item = self.preflight(); self.initialize(authorized_scope=[item["scope"]])
        path = self.write("reports/synthetic-production-preflight.json", item)
        result = runtime.record_preflight(self.root, self.task_id, path)
        self.assertFalse(result["external_permission_issued"])
        self.assertEqual(runtime.record_preflight(self.root, self.task_id, path)["result"], "duplicate_ignored")
        self.write(path, {**item, "risk_level": "R1"})
        with self.assertRaisesRegex(w.WorkflowError, "preflight frozen"):
            runtime.record_preflight(self.root, self.task_id, path)

    def test_production_self_check_still_requires_actual_precise_approval(self):
        item = self.preflight(); self.initialize(authorized_scope=[item["scope"]], execution_preflights=[item])
        fields = {k: item[k] for k in ("action_id", "action_class", "scope", "department")}
        denied, _ = w.policy_check(self.root, task_id=self.task_id, **fields)
        self.assertEqual(denied["status"], "deny")
        self.assertIn("exact_active_owner_approval_or_standing_scope_required", denied["reason"])
        self.assertNotIn("qa_verdict:pass", denied["required_receipts"])
        policy = w.read_json(self.root / "data/action-policy.json")
        policy["standing_authorizations"] = [{"authorization_id": "synthetic-standing", "status": "active",
             "source_message_ref": "synthetic-only", "department": PRODUCER,
             "action_classes": ["site_publish"], "allowed_scope_prefixes": ["flashcast.com.my:"]}]
        w.atomic_write_json(self.root / "data/action-policy.json", policy)
        permitted, _ = w.policy_check(self.root, task_id=self.task_id, consume_approval=True, **fields)
        self.assertEqual(permitted["status"], "allow", permitted["reason"])
        self.assertEqual(permitted["approval_status"], "consumed")
        self.assertEqual(w._validate_receipt_chain(self.root, self.task_id)[0], [])

    def test_preflight_rejects_changed_facts_and_unregistered_channel(self):
        item = self.preflight(); self.initialize(authorized_scope=[item["scope"]])
        self.write(item["facts"]["path"], {"changed": True})
        path = self.write("reports/synthetic-production-preflight.json", item)
        with self.assertRaisesRegex(w.WorkflowError, "evidence required"):
            runtime.record_preflight(self.root, self.task_id, path)
        self.write(path, {**item, "action_class": "invented_external_channel"})
        with self.assertRaisesRegex(w.WorkflowError, "existing production channel"):
            runtime.record_preflight(self.root, self.task_id, path)

    def collaboration(self):
        registry = w.read_json(self.root / "data/department-registry.json")
        binding = {"thread_id": "synthetic-fixed-development", "project_id": "synthetic-development-project",
                   "title": "Synthetic designated development", "cwd": str(self.root / "synthetic-code-project")}
        registry["collaboration_bindings"] = {"designated-development": binding}
        w.atomic_write_json(self.root / "data/department-registry.json", registry)
        requested = self.requested(); requested.update(target_department="designated-development", target_project_id=binding["project_id"],
                      target_thread_id=binding["thread_id"], target_thread_title=binding["title"], target_cwd=binding["cwd"],
                      target_sidebar_section_id="synthetic-development-sidebar", scope="project:test:designated-development")
        source = w.department_registry(self.root)[ASSISTANT]["chat_binding"]
        live_path = self.write("reports/synthetic-native-live.json", {"fixture_only": True, "observed_at": w.utc_timestamp(),
            "native_receipt_ref": "synthetic-live-read", "target_sidebar_section_id": requested["target_sidebar_section_id"],
            "threads": [{"id": binding["thread_id"], "projectId": binding["project_id"], "title": binding["title"], "cwd": binding["cwd"], "status": "idle"},
                        {"id": source["task_id"], "projectId": source["project_id"], "title": source["title"], "cwd": source["cwd"]}]})
        requested["live_identity"] = w.file_digest(self.root, live_path)
        self.initialize(authorized_scope=[requested["scope"]], approved_actions=[requested])
        return requested, binding

    def test_designated_collaboration_exact_sender_scope_does_not_require_fake_department(self):
        request, _ = self.collaboration()
        decision = self.policy(request)
        self.assertEqual(decision["status"], "allow", decision["reason"])
        self.assertEqual(decision["department"], ASSISTANT)
        self.assertNotIn("designated-development", w.department_registry(self.root))
        self.assertEqual(self.policy({**request, "sender_department": "operations-assistant-3"})["status"], "deny")

    def test_collaboration_result_audit_is_not_registered_ack_or_parent_close(self):
        request, binding = self.collaboration()
        decision = self.policy(request)
        self.assertEqual(decision["status"], "allow", decision["reason"])
        result_path = self.write("reports/synthetic-development-result.json", {"fixture_only": True, "parent_task_id": self.task_id})
        reply_path = "reports/synthetic-visible-reply.txt"; w.safe_path(self.root, reply_path).write_text("Synthetic nonempty developer fixture reply.")
        receipt = {"fixture_only": True, "task_id": self.task_id, "action_id": request["action_id"], "scope": request["scope"],
                   "tool": "mcp__codex_app__send_message_to_thread", "native_receipt_ref": "synthetic-collaboration-receipt",
                   "status": "result_received", "target_thread_id": binding["thread_id"], "payload_sha256": request["payload_sha256"],
                   "policy_decision_id": decision["decision_id"],
                   "message_ref": "synthetic-message-ref", "result": w.file_digest(self.root, result_path), "visible_reply": w.file_digest(self.root, reply_path)}
        path = self.write("reports/synthetic-collaboration-receipt.json", receipt)
        result = runtime.record_collaboration(self.root, self.task_id, path)
        self.assertFalse(result["parent_closed"]); self.assertTrue(result["does_not_grant_permission"])
        self.assertEqual(runtime.record_collaboration(self.root, self.task_id, path)["result"], "duplicate_ignored")
        self.assertEqual(w._validate_receipt_chain(self.root, self.task_id)[0], [])
        self.assertNotEqual(runtime.status(self.root, self.task_id)["state"], "completed_scope")
        self.assertEqual(self.policy(request)["status"], "deny")

    def completion_receipts(self):
        """Inputs for the pure state derivation, never persisted as real receipts."""
        return [{"fixture_only": True, "receipt_type": "dispatch_sent", "department": PRODUCER},
                {"fixture_only": True, "receipt_type": "chat_ack", "department": PRODUCER, "ack_nonempty": True},
                {"fixture_only": True, "receipt_type": "outbox_received", "department": PRODUCER},
                {"fixture_only": True, "receipt_type": "qa_verdict", "department": ASSISTANT, "verdict": "pass"}]

    def test_declared_production_action_cannot_close_without_preflight_execution_and_postcheck(self):
        item = self.preflight()
        declared = {k: item[k] for k in ("action_id", "action_class", "scope", "department")}
        self.initialize(authorized_scope=[item["scope"]], required_execution_actions=[declared])
        state = w._derive_state(self.root, self.snapshot(), self.completion_receipts())
        self.assertEqual(state["state"], "qa_passed")
        self.assertEqual(state["missing"], ["production_preflight:" + item["action_id"]])
        path = self.write("reports/synthetic-production-preflight.json", item)
        runtime.record_preflight(self.root, self.task_id, path)
        receipts = self.completion_receipts()
        self.assertEqual(w._derive_state(self.root, self.snapshot(), receipts)["missing"], ["exact_execution_and_postcheck:" + item["action_id"]])
        receipts.append({**declared, "fixture_only": True, "receipt_type": "execution_result", "verdict": "pass"})
        self.assertNotEqual(w._derive_state(self.root, self.snapshot(), receipts)["state"], "closed")
        receipts.append({**declared, "fixture_only": True, "receipt_type": "postcheck", "verdict": "pass"})
        self.assertEqual(w._derive_state(self.root, self.snapshot(), receipts)["state"], "closed")

    def test_external_dependency_waits_for_exact_owner_input_and_does_not_replace_acceptance(self):
        scope = "project:test:dependency"
        dependency = {"id": "synthetic-facts", "owner": "synthetic-facts-custodian", "scope": scope,
                      "unblock_condition": "exact factual input available"}
        self.initialize(authorized_scope=[scope], dependencies=[dependency])
        state = w._derive_state(self.root, self.snapshot(), self.completion_receipts())
        self.assertEqual(state["state"], "qa_passed")
        self.assertIn("external_dependency:synthetic-facts:owner:synthetic-facts-custodian", state["missing"])
        evidence_path = self.write("reports/synthetic-dependency-input.json", {"fixture_only": True, "value": "safe factual fixture"})
        resolution = {**dependency, "task_id": self.task_id, "dependency_id": dependency["id"], "status": "resolved",
                      "native_receipt_ref": "synthetic-only-dependency-receipt", "evidence": w.file_digest(self.root, evidence_path)}
        path = self.write("reports/synthetic-dependency-resolution.json", {**resolution, "owner": "wrong-custodian"})
        with self.assertRaisesRegex(w.WorkflowError, "exact named"):
            runtime.record_dependency(self.root, self.task_id, path)
        self.write(path, resolution)
        result = runtime.record_dependency(self.root, self.task_id, path)
        self.assertFalse(result["parent_closed"]); self.assertTrue(result["assistant_acceptance_required"])
        self.assertEqual(runtime.record_dependency(self.root, self.task_id, path)["result"], "duplicate_ignored")
        self.assertEqual(runtime.completion_dependencies(self.root, self.snapshot()), [])
        self.assertNotEqual(runtime.status(self.root, self.task_id)["state"], "completed_scope")
        self.write(evidence_path, {"fixture_only": True, "changed": "data"})
        with self.assertRaisesRegex(w.WorkflowError, "dependency input changed"):
            runtime.completion_dependencies(self.root, self.snapshot())

    def test_designated_collaboration_only_sent_result_cannot_close_goal(self):
        request, binding = self.collaboration()
        decision = self.policy(request); self.assertEqual(decision["status"], "allow", decision["reason"])
        receipt = {"fixture_only": True, "task_id": self.task_id, "action_id": request["action_id"], "scope": request["scope"],
                   "tool": "mcp__codex_app__send_message_to_thread", "native_receipt_ref": "synthetic-native-send-receipt",
                   "status": "sent", "target_thread_id": binding["thread_id"], "payload_sha256": request["payload_sha256"],
                   "message_ref": "synthetic-sent-message", "policy_decision_id": decision["decision_id"]}
        path = self.write("reports/synthetic-collaboration-sent.json", {**receipt, "policy_decision_id": "unknown"})
        with self.assertRaisesRegex(w.WorkflowError, "permitted collaboration policy"):
            runtime.record_collaboration(self.root, self.task_id, path)
        self.write(path, receipt); runtime.record_collaboration(self.root, self.task_id, path)
        state = w._derive_state(self.root, self.snapshot(), self.completion_receipts())
        self.assertEqual(state["state"], "qa_passed")
        self.assertEqual(state["missing"], ["collaboration_result:" + request["action_id"]])
        self.assertEqual(self.policy(request)["status"], "deny")

    def test_parent_child_status_and_growth_metrics_do_not_auto_close_parent(self):
        self.initialize(); parent = self.task_id
        self.task_id = "goal-consumer-child-001"; self.initialize(parent_task_id=parent)
        child = self.snapshot(); child["current_state"] = "closed"
        w.atomic_write_json(w.snapshot_path(self.root, self.task_id), child)
        result = runtime.status(self.root, parent)
        self.assertFalse(result["business_goal_closed"])
        self.assertEqual(result["children"][0]["task_id"], self.task_id)
        self.assertTrue(result["children"][0]["does_not_auto_close_parent"])
        self.assertEqual(result["organic_ip_goal"], "DATA_MISSING")
        self.assertEqual(result["AI_effect"], "NOT_MEASURED")
        self.assertNotEqual(result["state"], "completed_scope")

    def test_hq_new_model_can_end_with_inflight_and_legacy_still_blocks(self):
        now = dt.datetime.now(dt.timezone.utc)
        with mock.patch.object(stop, "ROOT", self.root), mock.patch.object(stop, "PROJECT", "flashcast-test-project"), mock.patch.object(stop, "CONTROLLER", "fixed-operations"):
            event = {"hook_event_name": "Stop", "session_id": "fixed-operations", "cwd": str(self.root), "stop_hook_active": False}
            state = {"project_id": "flashcast-test-project", "controller_thread_id": "fixed-operations", "cwd": str(self.root),
                     "updated_at": now.isoformat(), "watched_tasks": [{"task_id": self.task_id}], "ready_internal_actions": [],
                     "coordination_model": runtime.MODEL, "HQ_may_end_coordination": True}
            pending = {"pending_count": 1, "followthrough_pending_count": 1}
            self.assertEqual(stop.decide(event, state, pending, now), {})
            state.pop("coordination_model")
            self.assertEqual(stop.decide(event, state, pending, now)["decision"], "block")


if __name__ == "__main__":
    unittest.main()
