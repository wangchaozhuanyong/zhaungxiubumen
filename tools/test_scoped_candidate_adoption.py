"""Owned isolated actual file CAS/SQL; synthetic native fixtures are not a live trial."""
import copy
import datetime as dt
import difflib
import json
from pathlib import Path
import unittest

import goal_delivery_runtime as g
import parent_initial_dispatch as initial
import qa_review_plan as q
import result_coordination as c
import scoped_candidate_adoption as s
import test_native_multi_goal_review_source as native
import workflow_control as w


class ScopedAdoptionTests(unittest.TestCase):
    def setUp(self):
        self.native = native.NativeMultiGoalReviewTests("runTest")
        self.native.setUp(); self.addCleanup(self.native.doCleanups)
        self.root, self.consumer, self.fixture = self.native.root, self.native.consumer, self.native.fixture
        self.native.use(s.TASK)
        self.field = {"department_id": "operations-assistant-3", "field": "approved_subskills",
                      "expected": ["old"], "replacement": ["old", "development-review"]}
        registry = w.read_json(self.root / "data/department-registry.json")
        a3 = next(row for row in registry["departments"] if row["id"] == "operations-assistant-3")
        a3[self.field["field"]] = self.field["expected"]
        w.atomic_write_json(self.root / "data/department-registry.json", registry)
        self.field["expected_sha256"] = s._hash(self.field["expected"])
        migration = {"source_registry": "data/department-registry.json", "mode": "field_CAS_only",
                     "preserve_all_other_fields": True, "changes": [self.field]}
        migration_pin = self.write_pin("reports/migration.json", migration)
        before, after = b"VALUE = 'before'\n", b"VALUE = 'after'\n"
        self.source = "tools/adopted-test.py"
        self.raw("reports/baseline.py", before); self.raw("reports/candidate.py", after)
        self.raw("reports/source.diff", "".join(difflib.unified_diff(before.decode().splitlines(True),
            after.decode().splitlines(True), fromfile="a/" + self.source, tofile="b/" + self.source)).encode())
        baseline = w.file_digest(self.root, "reports/baseline.py")
        payload = {"task_id": s.TASK, "scope": s.SCOPE, "changes": [{"path": self.source,
            "baseline": baseline, "expected_source": {"sha256": baseline["sha256"], "size": baseline["size"]},
            "candidate": w.file_digest(self.root, "reports/candidate.py"), "diff": w.file_digest(self.root, "reports/source.diff")}],
            "field_changes": [migration_pin]}
        self.manifest = {**payload, "candidate_version": s.VERSION, "candidate_fingerprint": s._hash(payload),
                         "primary_owner": s.PRODUCER, "responsible_assistant": s.ROLE, "external_writes": False}
        manifest_pin = self.write_pin("reports/manifest.json", self.manifest)
        # A new immutable producer version uses actual receipt entry points.
        candidate = self.write_pin("drafts/operations/exact-v3-candidate.json", {
            "task_id": s.TASK, "department": s.PRODUCER, "candidate_version": s.VERSION})
        producer = self.consumer.result_box(s.PRODUCER, s.VERSION, candidate)
        producer["evidence"].append(manifest_pin)
        producer_pin = self.write_pin("logs/department-outbox/exact-v3-producer.json", producer)
        self.fixture.receipt("outbox_received", s.PRODUCER, "exact-v3-producer", evidence=producer_pin["path"])
        self.plan = self.consumer.review_plan(candidate)
        self.plan["native_multi_goal_review"] = self.native.plans[s.TASK]["native_multi_goal_review"]
        plan_pin = self.write_pin("drafts/operations/exact-v3-plan.json", self.plan)
        q.bind_plan(self.root, task_id=s.TASK, plan_path=plan_pin["path"], coordinator_role=s.ROLE)
        parent = self.snapshot()
        review = {"task_id": s.TASK, "candidate_version": s.VERSION, "scope": s.SCOPE,
            "candidate_fingerprint": self.manifest["candidate_fingerprint"], "reviewer": s.ROLE,
            "producer_department": s.PRODUCER, "acceptance_capability": "development",
            "phase": "candidate_source_only", "verdict": "PASS_CANDIDATE_SCOPE_ONLY",
            "goal_completion_claimed": False, "final_goal_verdict": False, "pilot_complete": False,
            "candidate_manifest": manifest_pin, "producer_outbox": producer_pin, "review_plan": plan_pin,
            "human_authorization": parent["goal_delivery"]["authorization_pin"], "goal_contract": parent["goal_contract"],
            "independent_evidence": [w.file_digest(self.root, "reports/source.diff")]}
        review_pin = self.write_pin("reports/independent-review.json", review)
        text = " ".join([s.TASK, s.VERSION, producer_pin["sha256"], self.manifest["candidate_fingerprint"],
                         review_pin["path"], review_pin["sha256"], "candidate scope accepted; trial pending"])
        self.raw("reports/a2-reply.txt", text.encode())
        reply_pin = w.file_digest(self.root, "reports/a2-reply.txt")
        native_pin = self.write_pin("reports/a2-native-reply.json", {"thread": {"id": "fixed-" + s.ROLE, "cwd": str(self.root)},
            "turns": [{"id": "native-limited-review-turn", "status": "inProgress",
                "startedAt": dt.datetime.now(dt.timezone.utc).timestamp(), "items": [{
                "id": "native-limited-review-message", "type": "agentMessage", "phase": "commentary", "text": text}]}]})
        box = self.consumer.result_box(s.ROLE, s.VERSION, review_pin)
        box.update(status="partial", actual_native_reply=native_pin, visible_reply=reply_pin,
            reply_observed_at=dt.datetime.now(dt.timezone.utc).isoformat(),
            source_turn_id="native-limited-review-turn", source_message_id="native-limited-review-message",
            source_reply_sha256=reply_pin["sha256"])
        box_pin = self.write_pin("reports/limited-review-outbox.json", box)
        # Actual isolated CAS and original backups, never a declared adopted flag alone.
        self.raw(self.source, before); self.raw("backups/before.py", before)
        self.assertEqual(w.file_digest(self.root, self.source)["sha256"], baseline["sha256"])
        registry_before = self.write_pin("backups/registry-before.json", registry)
        self.raw(self.source, after)
        a3[self.field["field"]] = self.field["replacement"]
        w.atomic_write_json(self.root / "data/department-registry.json", registry)
        registry_after = self.write_pin("backups/registry-after.json", registry)
        operations = [{"path": self.source, "before_sha256": baseline["sha256"],
            "after_sha256": w.file_digest(self.root, "reports/candidate.py")["sha256"],
            "backup": w.file_digest(self.root, "backups/before.py")}]
        fields = [{"department_id": self.field["department_id"], "field": self.field["field"],
                   "before": self.field["expected"], "after": self.field["replacement"]}]
        self.journal = {"task_id": s.TASK, "candidate_version": s.VERSION, "scope": s.SCOPE,
            "candidate_fingerprint": self.manifest["candidate_fingerprint"], "actor": s.ROLE,
            "state": "adopted", "execution_id": "12345678-1234-1234-1234-123456789abc",
            "independent_review": review_pin, "review_outbox": box_pin,
            "authorized_source": parent["goal_delivery"]["authorization_pin"],
            "started_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "completed_at": dt.datetime.now(dt.timezone.utc).isoformat(), "external_writes": 0,
            "permissions_issued": False, "source_operations": operations, "field_operations": fields,
            "registry_before": registry_before, "registry_after": registry_after}
        journal_pin = self.write_pin("backups/journal.json", self.journal)
        self.raw("reports/postapply.txt", b"Ran 1 test in 0.01s\n\nOK\n")
        report = {"task_id": s.TASK, "candidate_version": s.VERSION, "actor": s.ROLE,
            "execution_id": self.journal["execution_id"], "candidate_manifest": manifest_pin,
            "started_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "completed_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "exit_code": 0, "actual_execution": True, "external_writes": 0}
        post_pin = self.write_pin("reports/postapply.json", {**report, "stage": "postapply",
            "tests": {"run": 1, "failures": 0, "errors": 0}, "output": w.file_digest(self.root, "reports/postapply.txt")})
        rollback_output = self.write_pin("reports/rollback-output.json", {
            "source_paths": [self.source], "field_operations": fields, "result": "PASS"})
        rollback_pin = self.write_pin("reports/rollback.json", {**report, "stage": "rollback_preflight",
            "read_only": True, "actual_rollback": False, "source_paths": [self.source],
            "field_operations": fields, "output": rollback_output})
        self.proof = {"mode": "scoped_candidate_actual_adoption", "candidate_review": review_pin,
            "candidate_review_outbox": box_pin, "candidate_manifest": manifest_pin, "producer_outbox": producer_pin,
            "review_plan": plan_pin, "adoption_journal": journal_pin, "postapply": post_pin, "rollback_preflight": rollback_pin}
        self.producer_pin = producer_pin

    def raw(self, path, value):
        target = self.root / path; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(value)

    def write_pin(self, path, value):
        self.consumer.write(path, value)
        return w.file_digest(self.root, path)

    def snapshot(self):
        return w.read_json(w.snapshot_path(self.root, s.TASK))

    def validate(self, proof=None):
        return s.validate_adoption(self.root, self.snapshot(), proof or self.proof)

    def change_doc(self, name, **changes):
        pin = self.proof[name]; value = w.read_json(w.safe_path(self.root, pin["path"]))
        value.update(changes); w.atomic_write_json(w.safe_path(self.root, pin["path"]), value)
        return {**self.proof, name: w.file_digest(self.root, pin["path"])}

    def test_candidate_stage_allows_actual_adoption_before_full_PASS_without_writes(self):
        before = {str(path): path.read_bytes() for path in self.root.rglob("*") if path.is_file()}
        result = self.validate()
        self.assertEqual(result["adoption_stage"], "scoped_candidate_actual_adoption")
        self.assertFalse(result["final_goal_pass"]); self.assertFalse(result["business_goal_closed"])
        self.assertFalse(any(row.get("verdict") == "pass" for row in s._receipts(self.root, s.TASK)))
        self.assertEqual(before, {str(path): path.read_bytes() for path in self.root.rglob("*") if path.is_file()})

    def test_bare_historical_full_PASS_proof_no_longer_admits_F4_initial_send(self):
        with self.assertRaisesRegex(w.WorkflowError, "bounded candidate"):
            self.validate({"control_qa_outbox_path": "old", "control_applied_proof": "old", "control_qa_receipt_id": "old"})

    def test_wrong_stage_self_review_version_and_goal_preclaim_are_rejected(self):
        original = w.safe_path(self.root, self.proof["candidate_review"]["path"]).read_bytes()
        for changes in ({"reviewer": s.PRODUCER}, {"candidate_version": "wrong"}, {"phase": "whole_goal"},
                        {"goal_completion_claimed": True}, {"final_goal_verdict": True}):
            with self.subTest(changes=changes), self.assertRaises(w.WorkflowError):
                self.validate(self.change_doc("candidate_review", **changes))
            w.safe_path(self.root, self.proof["candidate_review"]["path"]).write_bytes(original)

    def test_declared_adoption_wrong_actor_simulation_new_permissions_and_failed_checks_rejected(self):
        original = w.safe_path(self.root, self.proof["adoption_journal"]["path"]).read_bytes()
        for changes in ({"state": "prepared"}, {"actor": s.PRODUCER}, {"simulation": True},
                        {"permissions_issued": True}, {"external_writes": 1}):
            with self.subTest(changes=changes), self.assertRaises(w.WorkflowError):
                self.validate(self.change_doc("adoption_journal", **changes))
            w.safe_path(self.root, self.proof["adoption_journal"]["path"]).write_bytes(original)
        with self.assertRaises(w.WorkflowError): self.validate(self.change_doc("postapply", exit_code=1))

    def test_drifted_actual_source_field_backup_and_unrelated_registry_change_rejected(self):
        self.raw(self.source, b"different source")
        with self.assertRaisesRegex(w.WorkflowError, "current source"): self.validate()
        self.raw(self.source, w.safe_path(self.root, self.manifest["changes"][0]["candidate"]["path"]).read_bytes())
        registry = w.read_json(self.root / "data/department-registry.json")
        next(row for row in registry["departments"] if row["id"] == "operations-assistant-3")["approved_subskills"] = []
        w.atomic_write_json(self.root / "data/department-registry.json", registry)
        with self.assertRaisesRegex(w.WorkflowError, "current exact reviewed field"): self.validate()

    def test_actual_native_A2_reply_and_manifest_pins_cannot_be_replaced(self):
        self.raw("reports/a2-reply.txt", b"pretended acceptance")
        with self.assertRaises(w.WorkflowError): self.validate()

    def test_native_review_accepts_exact_absolute_file_link(self):
        box_pin = self.proof["candidate_review_outbox"]
        box = w.read_json(w.safe_path(self.root, box_pin["path"]))
        native_pin = box["actual_native_reply"]
        native_doc = w.read_json(w.safe_path(self.root, native_pin["path"]))
        item = native_doc["turns"][0]["items"][0]
        item["text"] = item["text"].replace(self.proof["candidate_review"]["path"],
            "[review](" + str(w.safe_path(self.root, self.proof["candidate_review"]["path"])) + ")")
        self.raw(box["visible_reply"]["path"], item["text"].encode())
        box.update(actual_native_reply=self.write_pin(native_pin["path"], native_doc),
            visible_reply=w.file_digest(self.root, box["visible_reply"]["path"]),
            source_reply_sha256=w.file_digest(self.root, box["visible_reply"]["path"])["sha256"])
        self.proof["candidate_review_outbox"] = self.write_pin(box_pin["path"], box)
        self.proof = self.change_doc("adoption_journal", review_outbox=self.proof["candidate_review_outbox"])
        self.validate()

    def test_actual_adoption_alone_cannot_issue_full_goal_PASS(self):
        with self.assertRaisesRegex(w.WorkflowError, "subsequent read-only child"):
            s.validate_final_goal_pass(self.root, self.snapshot(), {"system_goal_completion": {"scoped_adoption": self.proof}})

    def prepare_child(self):
        registry = w.read_json(self.root / "data/department-registry.json")
        next(row for row in registry["departments"] if row["id"] == s.PRODUCER)["mode"] = "coordinator"
        w.atomic_write_json(self.root / "data/department-registry.json", registry)
        parent = self.snapshot()
        self.child = "fc-v3-read-only-trial-child"
        contract = copy.deepcopy(parent["goal_delivery"])
        contract.update(parent_task_id=s.TASK, initial_dispatch_mode="read_only",
                        objective="Isolated read-only trial", completion_criteria=["read-only return"])
        contract.pop("approved_actions", None)
        child_pin = self.write_pin("drafts/operations/child-v3.json", contract)
        g.initialize_goal(self.root, self.child, child_pin["path"])
        auth = parent["goal_delivery"]["authorization_pin"]
        text = " ".join([self.child, s.TASK, s.SCOPE, child_pin["path"], child_pin["sha256"], auth["path"], auth["sha256"]])
        self.raw("drafts/operations/child-message.txt", text.encode())
        action = self.consumer.requested(sender=s.ROLE, target=s.PRODUCER, scope=s.SCOPE,
                                         payload=w.file_digest(self.root, "drafts/operations/child-message.txt"))
        action.update(task_id=self.child, parent_task_id=s.TASK, action_id="exact-v3-read-only-child")
        self.initial_proof = {"schema_version": 1, "mode": "read_only", "child_contract": child_pin,
            "action": action, "adoption": self.proof, "attempt_path": "logs/goal-initial-dispatch/" + self.child + "/attempt.json",
            "native_send_receipt_path": "logs/goal-initial-dispatch/" + self.child + "/native.json"}
        base = {"task_id": s.TASK, "sender_department": s.PRODUCER, "candidate_version": s.VERSION,
                "result_sha256": self.producer_pin["sha256"], "outbox_path": self.producer_pin["path"]}
        completed = self.consumer.completed_result_fields()
        w.record_result_handoff(self.root, {**base, **completed, "event": "notification_queued", "idempotency_key": "v3-queued"})
        self.store = c.CoordinationStore(self.root); self.addCleanup(self.store.close)
        lease = self.store.claim(base, s.ROLE, "isolated-a2", "v3-claim")
        authority = {"coordinator_role": s.ROLE, "coordinator_owner": "isolated-a2", "coordination_claim": lease}
        w.record_result_handoff(self.root, {**base, **completed, **authority, "event": "controller_received",
            "intake_mode": "queue", "idempotency_key": "v3-intake"})
        evidence = [child_pin, action["payload"], parent["goal_contract"], auth] + [self.proof[key] for key in s.PIN_FIELDS]
        request = {**base, **authority, "event": "controller_decision", "idempotency_key": "v3-child-decision",
            "decision": "continue", "next_owner": s.PRODUCER, "next_action": "one read-only child",
            "next_task_id": self.child, "next_action_id": action["action_id"], "next_scope": s.SCOPE,
            "initial_dispatch": self.initial_proof, "evidence_paths": [pin["path"] for pin in evidence]}
        decision, _ = w.record_result_handoff(self.root, request)
        self.action = {**action, "decision_record_id": decision["record_id"], "parent_initial_dispatch": self.initial_proof}
        self.base, self.authority, self.decision = base, authority, decision
        return decision

    def send_child(self):
        decision = self.prepare_child()
        action_path = self.consumer.write("drafts/operations/approved-v3-child.json", self.action)
        g.record_approved_action(self.root, self.child, action_path)
        request = {key: self.action[key] for key in initial.ACTION_FIELDS if key not in {"payload", "parent_task_id", "sender_department"}}
        routing = w.policy_check(self.root, department=s.ROLE, **request)[0]
        self.assertEqual(routing["status"], "allow", routing.get("reason"))
        begin_path = self.consumer.write("drafts/operations/begin-v3.json", {"task_id": self.child,
            "action_id": self.action["action_id"], "policy_decision_id": routing["decision_id"]})
        attempt = initial.begin(self.root, begin_path)
        self.assertFalse(attempt["actual_message_sent"])
        raw_attempt = w.read_json(w.safe_path(self.root, self.initial_proof["attempt_path"]))
        self.consumer.write(self.initial_proof["native_send_receipt_path"], {"tool": initial.TOOL,
            "arguments": raw_attempt["arguments"], "attempt_id": raw_attempt["attempt_id"],
            "observed_at": dt.datetime.now(dt.timezone.utc).isoformat(), "actual_native_send": {
                "isError": False, "content": [{"type": "text", "text": json.dumps({"threadId": "fixed-" + s.PRODUCER})}]}})
        self.fixture.task_id = self.child
        receipt = self.fixture.receipt("dispatch_sent", s.PRODUCER, "v3-send-receipt",
            policy_decision_id=routing["decision_id"], action_id=self.action["action_id"], action_class="thread_message",
            scope=s.SCOPE, evidence=self.initial_proof["attempt_path"] + ";" + self.initial_proof["native_send_receipt_path"])
        self.assertEqual(receipt["parent_initial_dispatch"]["decision_record_id"], decision["record_id"])
        self.assertEqual(w._validate_receipt_chain(self.root, self.child)[1], [])
        with self.assertRaises(w.WorkflowError): initial.begin(self.root, begin_path)
        self.assertFalse(any(row.get("verdict") == "pass" for row in s._receipts(self.root, s.TASK)))
        self.routing = routing
        return receipt

    def test_actual_candidate_CAS_parent_fenced_decision_first_policy_begin_and_native_receipt(self):
        self.send_child()

    def test_old_v2_intake_or_decision_cannot_start_adopted_v3_child(self):
        self.prepare_child()
        for changes in ({"candidate_version": "system-flow-throughput-ledger-cleanup-v2"},
                        {"result_sha256": "a" * 64}, {"outbox_path": "reports/unrelated.json"},
                        {"sender_department": s.ROLE}):
            with self.subTest(changes=changes), self.assertRaisesRegex(w.WorkflowError, "exact independently adopted producer"):
                initial._candidate_result(self.snapshot(), {**self.decision, **changes}, self.initial_proof)

    def finish_trial(self, status="completed", intake=True, formal_child_review=False):
        dispatch = self.send_child()
        self.fixture.receipt("chat_ack", s.PRODUCER, "v3-child-ack")
        self.consumer.task_id = self.child
        candidate = self.write_pin("reports/child-readonly-result.json", {
            "task_id": self.child, "candidate_version": "child-read-only-v1", "department": s.PRODUCER})
        box = self.consumer.result_box(s.PRODUCER, "child-read-only-v1", candidate)
        box.update(parent_task_id=s.TASK, status=status)
        child_pin = self.write_pin("logs/department-outbox/v3-child.json", box)
        outbox = self.fixture.receipt("outbox_received", s.PRODUCER, "v3-child-result", evidence=child_pin["path"])
        completed = self.consumer.completed_result_fields()
        child_base = {"task_id": self.child, "sender_department": s.PRODUCER, "candidate_version": "child-read-only-v1",
                      "result_sha256": child_pin["sha256"], "outbox_path": child_pin["path"]}
        w.record_result_handoff(self.root, {**child_base, **completed, "event": "notification_queued", "idempotency_key": "child-completed-queue"})
        if intake:
            child_lease = self.store.claim(child_base, s.ROLE, "isolated-a2", "child-claim")
            w.record_result_handoff(self.root, {**child_base, **completed, "event": "controller_received", "intake_mode": "queue",
                "idempotency_key": "child-completed-intake", "coordinator_role": s.ROLE, "coordinator_owner": "isolated-a2",
                "coordination_claim": child_lease})
        if formal_child_review:
            from parent_initial_child_review import build_proof
            child_snapshot = w.read_json(w.snapshot_path(self.root, self.child))
            child_proof = build_proof(self.root, child_snapshot, child_pin)
            child_plan = self.consumer.review_plan(candidate)
            child_plan.update(parent_initial_child_review=child_proof, action_class="read_only_candidate")
            child_plan_pin = self.write_pin("drafts/operations/child-independent-review.json", child_plan)
            q.bind_plan(self.root, task_id=self.child, plan_path=child_plan_pin["path"], coordinator_role=s.ROLE)
            child_verdict = self.consumer.assistant_verdict(child_plan, child_pin,
                parent_initial_child_review=child_proof)
            self.assertEqual(child_verdict["verdict"], "pass")
            self.assertEqual(w.read_json(w.snapshot_path(self.root, self.child))["current_state"], "closed")
            self.assertFalse(any(row.get("department") == s.ROLE and row.get("receipt_type") in {"dispatch_sent", "chat_ack"}
                                 for row in s._receipts(self.root, self.child)))
        self.consumer.task_id = self.fixture.task_id = s.TASK
        follow, _ = w.record_result_handoff(self.root, {**self.base, **self.authority, "event": "controller_followthrough",
            "idempotency_key": "v3-trial-followthrough", "followthrough_status": "subsequent_action_verified",
            "linked_task_id": self.child, "action_receipt_id": outbox["receipt_id"],
            "linked_dispatch_receipt_id": dispatch["receipt_id"], "linked_outbox_path": child_pin["path"],
            "evidence_paths": [child_pin["path"]]})
        completion = {"scoped_adoption": self.proof, "pilot_followthrough_record_id": follow["record_id"]}
        return completion

    def test_actual_trial_returns_completed_native_child_intake_then_full_goal_PASS(self):
        completion = self.finish_trial(formal_child_review=True)
        self.assertTrue(s.validate_final_goal_pass(self.root, self.snapshot(), {
            "system_goal_completion": completion})["actual_native_trial_verified"])
        verdict = self.consumer.assistant_verdict(self.plan, self.producer_pin,
            native_multi_goal_review=self.plan["native_multi_goal_review"], system_goal_completion=completion)
        self.assertEqual(verdict["verdict"], "pass")
        self.assertEqual(w._validate_receipt_chain(self.root, s.TASK)[1], [])

    def test_parent_final_PASS_rejects_child_without_own_formal_acceptance(self):
        completion = self.finish_trial()
        with self.assertRaisesRegex(w.WorkflowError, "own independent formal PASS and closed scope"):
            s.validate_final_goal_pass(self.root, self.snapshot(), {"system_goal_completion": completion})

    def test_partial_child_cannot_be_whole_parent_goal_PASS(self):
        completion = self.finish_trial(status="partial")
        with self.assertRaisesRegex(w.WorkflowError, "completed original read-only child"):
            s.validate_final_goal_pass(self.root, self.snapshot(), {"system_goal_completion": completion})

    def test_native_child_outbox_without_actual_assistant_intake_cannot_be_full_PASS(self):
        completion = self.finish_trial(intake=False)
        with self.assertRaisesRegex(w.WorkflowError, "unique original assistant intake"):
            s.validate_final_goal_pass(self.root, self.snapshot(), {"system_goal_completion": completion})

    def test_extra_registry_adoption_and_changed_backup_rejected(self):
        after_pin = self.journal["registry_after"]
        after = w.read_json(w.safe_path(self.root, after_pin["path"]))
        after["unreviewed_change"] = True
        w.atomic_write_json(w.safe_path(self.root, after_pin["path"]), after)
        proof = self.change_doc("adoption_journal", registry_after=w.file_digest(self.root, after_pin["path"]))
        with self.assertRaisesRegex(w.WorkflowError, "outside exact reviewed"): self.validate(proof)


if __name__ == "__main__":
    unittest.main()
