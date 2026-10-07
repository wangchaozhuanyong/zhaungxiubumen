"""Synthetic project-local integration tests against REAL workflow entry points."""
import datetime as dt
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest import mock

import result_coordination as coordination
import workflow_control as w
import test_workflow_control as legacy

CANDIDATE = Path(__file__).resolve().parents[1]


class ResultCoordinationIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.fixture = legacy.WorkflowControlTests("runTest")
        original = tempfile.TemporaryDirectory
        def bounded_temp(*args, **kwargs):
            kwargs["dir"] = CANDIDATE / ".test-tmp"
            return original(*args, **kwargs)
        with mock.patch.object(legacy.tempfile, "TemporaryDirectory", side_effect=bounded_temp):
            self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.root = self.fixture.root
        registry_path = self.root / "data/department-registry.json"
        registry = json.loads(registry_path.read_text())
        registry["departments"].append({"id": "operations-assistant", "chat_binding": {
            "task_id": "fixed-operations-assistant", "project_id": "flashcast-test-project",
            "cwd": str(self.root), "title": "operations-assistant"}})
        registry_path.write_text(json.dumps(registry))
        self.base, _ = self.fixture._result_handoff_fixture()
        self.queue = {**self.base, "event": "notification_queued", "idempotency_key": "queue-v1"}
        w.record_result_handoff(self.root, self.queue)
        self.identity = coordination.exact_identity(self.base)
        self.a = coordination.CoordinationStore(self.root)
        self.b = coordination.CoordinationStore(self.root)
        self.addCleanup(self.a.close)
        self.addCleanup(self.b.close)

    def receive(self, **changes):
        request = {**self.base, "event": "controller_received", "idempotency_key": "received-v1",
                   "intake_mode": "queue", "source_reply_sha256": "b"*64,
                   "source_thread_id": "fixed-content-organic-website",
                   "reply_observed_at": dt.datetime.now(dt.timezone.utc).isoformat()}
        request.update(changes)
        return request

    def claim(self, role="operations-assistant", owner="assistant-1", request_id="wake-v1", **kwargs):
        return self.a.claim(self.identity, role, owner, request_id, **kwargs)

    def draft(self, lease, status="partial", **kwargs):
        return self.a.precheck(self.identity, lease["role"], lease["owner"], lease, status,
                               "operations", "verify exact result then decide", "native result accepted", **kwargs)

    def claimed_request(self, lease, **kwargs):
        return self.receive(coordinator_role=lease["role"], coordinator_owner=lease["owner"],
                            coordination_claim=lease, **kwargs)

    def test_real_native_queue_remains_noninterrupting_and_idempotent(self):
        duplicate, _ = w.record_result_handoff(self.root, self.queue)
        self.assertEqual(duplicate["result"], "duplicate_ignored")
        self.assertFalse(duplicate["interrupts_active_thread"])

    def test_two_connections_cannot_own_one_result(self):
        first = self.claim()
        with self.assertRaisesRegex(w.WorkflowError, "already claimed"):
            self.b.claim(self.identity, "operations", "controller-2", "wake-2")
        self.assertEqual(self.b.readback(self.identity)["token"], first["token"])

    def test_concurrent_connections_have_exactly_one_winner(self):
        barrier = threading.Barrier(2)
        results = []
        def contender(owner):
            store = coordination.CoordinationStore(self.root)
            try:
                barrier.wait()
                results.append(store.claim(self.identity, "operations", owner, owner))
            except w.WorkflowError as exc:
                results.append(str(exc))
            finally:
                store.close()
        threads = [threading.Thread(target=contender, args=(owner,)) for owner in ("c1", "c2")]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(10)
            self.assertFalse(thread.is_alive())
        self.assertEqual(sum(isinstance(result, dict) for result in results), 1)
        self.assertEqual(sum("already claimed" in result for result in results if isinstance(result, str)), 1)

    def test_repeated_wake_reuses_current_claim(self):
        first = self.claim()
        second = self.claim()
        self.assertTrue(second["duplicate"])
        self.assertEqual(first["token"], second["token"])
        self.assertEqual(first["fence"], second["fence"])

    def test_no_speculative_claim_before_native_queue(self):
        other = {**self.identity, "candidate_version": "not-yet-queued"}
        with self.assertRaisesRegex(w.WorkflowError, "existing exact native"):
            self.a.claim(other, "operations", "controller", "wake")

    def test_ttl_bounds_reject_bool_and_over_15_minutes(self):
        for ttl in (0, 901, True, 1.2):
            with self.subTest(ttl=ttl), self.assertRaisesRegex(w.WorkflowError, "TTL"):
                self.claim(ttl_seconds=ttl)

    def test_unregistered_coordinator_rejected(self):
        with self.assertRaisesRegex(w.WorkflowError, "registered coordinator"):
            self.claim(role="qa")

    def test_hash_and_version_are_exact_identity(self):
        for changes in ({"candidate_version": "v2"}, {"result_sha256": "c"*64}, {"task_id": "different-task"}):
            with self.subTest(changes=changes), self.assertRaises(w.WorkflowError):
                self.a.claim({**self.identity, **changes}, "operations", "controller", "wake")

    def test_changed_final_outbox_blocks_claim_and_readback(self):
        self.claim()
        box = self.root / self.base["outbox_path"]
        box.write_text(box.read_text()+"\n")
        with self.assertRaisesRegex(w.WorkflowError, "bytes changed"):
            self.a.readback(self.identity)

    def test_assistant_cannot_final_without_claim(self):
        with self.assertRaisesRegex(w.WorkflowError, "assistant precheck"):
            w.record_result_handoff(self.root, self.receive(coordinator_role="operations-assistant"))

    def test_active_assistant_blocks_legacy_controller(self):
        self.claim()
        with self.assertRaisesRegex(w.WorkflowError, "coordinator owner|foreign coordination"):
            w.record_result_handoff(self.root, self.receive())

    def test_assistant_claim_cannot_record_any_final_event(self):
        lease = self.claim()
        for event in sorted(coordination.FINAL_EVENTS):
            with self.subTest(event=event), self.assertRaisesRegex(w.WorkflowError, "assistant precheck"):
                w.record_result_handoff(self.root, self.claimed_request(lease, event=event))

    def test_ops_owned_claim_requires_exact_owner_token_fence(self):
        lease = self.claim(role="operations", owner="controller")
        for changes in ({"coordinator_owner": "other"}, {"coordination_claim": {**lease, "token": "wrong"}},
                        {"coordination_claim": {**lease, "fence": lease["fence"]+1}},
                        {"coordination_claim": {**lease, "result_key": "wrong"}}):
            with self.subTest(changes=changes), self.assertRaisesRegex(w.WorkflowError, "foreign coordination"):
                w.record_result_handoff(self.root, {**self.claimed_request(lease), **changes})
        row, _ = w.record_result_handoff(self.root, self.claimed_request(lease))
        self.assertEqual(row["event"], "controller_received")

    def test_expired_claim_requires_explicit_recovery_and_new_fence(self):
        now = dt.datetime.now(dt.timezone.utc)
        self.a.clock = lambda: now
        old = self.claim(ttl_seconds=1)
        self.a.clock = lambda: now+dt.timedelta(seconds=2)
        with self.assertRaisesRegex(w.WorkflowError, "explicit recovery"):
            self.a.claim(self.identity, "operations", "controller", "wake-2")
        new = self.a.recover(self.identity, "operations", "controller", "wake-2", "interrupted worker expired")
        self.assertGreater(new["fence"], old["fence"])
        with self.assertRaisesRegex(w.WorkflowError, "foreign coordination"):
            self.a.renew(self.identity, "operations-assistant", "assistant-1", old)

    def test_renew_does_not_change_fence_or_allow_expired_holder(self):
        now = dt.datetime.now(dt.timezone.utc)
        self.a.clock = lambda: now
        lease = self.claim(ttl_seconds=2)
        renewed = self.a.renew(self.identity, lease["role"], lease["owner"], lease, 900)
        self.assertEqual(renewed["fence"], lease["fence"])
        self.a.clock = lambda: now+dt.timedelta(seconds=901)
        with self.assertRaises(w.WorkflowError):
            self.a.renew(self.identity, lease["role"], lease["owner"], renewed)

    def test_release_invalidates_old_fence_and_unlocks_legacy_controller(self):
        lease = self.claim()
        released = self.a.release(self.identity, lease["role"], lease["owner"], lease, "draft delivered")
        self.assertFalse(released["claimed"])
        with self.assertRaises(w.WorkflowError):
            self.a.renew(self.identity, lease["role"], lease["owner"], lease)
        row, _ = w.record_result_handoff(self.root, self.receive())
        self.assertEqual(row["result"], "recorded")

    def test_explicit_transfer_requires_draft_and_fences_assistant(self):
        lease = self.claim()
        with self.assertRaisesRegex(w.WorkflowError, "precheck"):
            self.a.transfer(self.identity, lease["role"], lease["owner"], lease, "operations", "controller", "handoff")
        self.draft(lease)
        transferred = self.a.transfer(self.identity, lease["role"], lease["owner"], lease, "operations", "controller", "handoff")
        self.assertGreater(transferred["fence"], lease["fence"])
        with self.assertRaises(w.WorkflowError):
            self.draft(lease)
        self.assertEqual(w.record_result_handoff(self.root, self.claimed_request(transferred))[0]["result"], "recorded")

    def test_all_actual_report_states_remain_drafts_and_keep_ownership(self):
        lease = self.claim()
        native_count = len(w._result_handoff_rows(self.root, self.base["task_id"]))
        for status in sorted(coordination.REPORT_STATES):
            result = self.draft(lease, status)
            self.assertEqual(result["owner"], lease["owner"])
            self.assertEqual(result["precheck"]["status"], status)
            self.assertTrue(result["precheck"]["draft_only"])
            self.assertFalse(result["precheck"]["controller_decision_recorded"])
            self.assertFalse(result["external_permission_issued"])
        self.assertEqual(len(w._result_handoff_rows(self.root, self.base["task_id"])), native_count)

    def test_precheck_cannot_invent_scope_or_omit_next_owner(self):
        lease = self.claim()
        with self.assertRaisesRegex(w.WorkflowError, "scope"):
            self.draft(lease, scope="invented-scope")
        with self.assertRaisesRegex(w.WorkflowError, "next owner"):
            self.a.precheck(self.identity, lease["role"], lease["owner"], lease, "queue_failed", "", "retry safe queue", "native queue readback")

    def test_crash_before_native_append_requires_explicit_recovery(self):
        request = self.receive()
        with self.assertRaises(RuntimeError):
            with coordination.handoff_guard(self.root, request):
                raise RuntimeError("simulated interruption before append")
        with self.assertRaisesRegex(w.WorkflowError, "explicit recover_reservation"):
            w.record_result_handoff(self.root, request)
        result = coordination.recover_reservation(self.root, request, "confirmed native append absent")
        self.assertEqual(result["status"], "retry_ready")
        self.assertFalse(result["side_effect_executed"])
        self.assertEqual(w.record_result_handoff(self.root, request)[0]["result"], "recorded")

    def test_crash_after_native_append_readbacks_without_repeat_effect(self):
        request = self.receive()
        with mock.patch.object(coordination.HandoffAdmission, "complete", side_effect=RuntimeError("simulated crash after native append")):
            with self.assertRaises(RuntimeError):
                w.record_result_handoff(self.root, request)
        rows = w._result_handoff_rows(self.root, self.base["task_id"])
        exact = [row for row in rows if row["event"] == "controller_received"]
        self.assertEqual(len(exact), 1)
        replay, _ = w.record_result_handoff(self.root, request)
        self.assertEqual(replay["record_id"], exact[0]["record_id"])
        self.assertEqual(replay["result"], "duplicate_ignored")
        self.assertEqual(len(w._result_handoff_rows(self.root, self.base["task_id"])), len(rows))

    def test_uncertain_effect_rejects_changed_semantic_payload(self):
        request = self.receive()
        with self.assertRaises(RuntimeError):
            with coordination.handoff_guard(self.root, request):
                raise RuntimeError("interrupted")
        with self.assertRaisesRegex(w.WorkflowError, "different semantic payload"):
            w.record_result_handoff(self.root, {**request, "source_reply_sha256": "c"*64})

    def test_uncertain_effect_rejects_evidence_bytes_changed(self):
        evidence = self.root / "reports/reply-proof.md"
        evidence.parent.mkdir(exist_ok=True)
        evidence.write_text("frozen proof")
        request = self.receive(evidence_paths=["reports/reply-proof.md"])
        with self.assertRaises(RuntimeError):
            with coordination.handoff_guard(self.root, request):
                raise RuntimeError("interrupted")
        evidence.write_text("different proof")
        with self.assertRaisesRegex(w.WorkflowError, "different semantic payload"):
            w.record_result_handoff(self.root, request)

    def test_replayed_legacy_controller_request_keeps_native_duplicate(self):
        request = self.receive()
        first, _ = w.record_result_handoff(self.root, request)
        again, _ = w.record_result_handoff(self.root, request)
        self.assertEqual(again["result"], "duplicate_ignored")
        self.assertEqual(first["record_id"], again["record_id"])

    def test_legacy_default_final_decision_and_followthrough_use_real_native_rules(self):
        w.record_result_handoff(self.root, self.receive())
        proof = self.root / "reports/next-action.md"
        proof.parent.mkdir(exist_ok=True)
        proof.write_text("Internal controller draft reconciled")
        decision = {**self.base, "event": "controller_decision", "idempotency_key": "decision-v1",
                    "decision": "continue", "next_owner": "operations", "next_action": "reconcile bounded control step",
                    "evidence_paths": ["reports/next-action.md"]}
        row, _ = w.record_result_handoff(self.root, decision)
        self.assertEqual(row["execution_status"], "NOT_EXECUTED")
        follow = {**self.base, "event": "controller_followthrough", "idempotency_key": "follow-v1",
                  "followthrough_status": "internal_control_completed", "action_reference": "exact synthetic control step",
                  "evidence_paths": ["reports/next-action.md"]}
        self.assertEqual(w.record_result_handoff(self.root, follow)[0]["result"], "recorded")
        self.assertFalse(w.result_handoff_status(self.root, self.base["task_id"])["business_goal_closed"])

    def test_assistant_queue_notification_does_not_require_final_permission(self):
        request = {**self.queue, "coordinator_role": "operations-assistant"}
        row, _ = w.record_result_handoff(self.root, request)
        self.assertEqual(row["result"], "duplicate_ignored")
        self.assertFalse(row["interrupts_active_thread"])

    def test_different_effect_idempotency_key_cannot_repeat_native_stage(self):
        w.record_result_handoff(self.root, self.receive())
        with self.assertRaisesRegex(w.WorkflowError, "已记录"):
            w.record_result_handoff(self.root, self.receive(idempotency_key="other-received-key"))

    def test_existing_native_readback_cannot_bypass_required_payload_fields(self):
        request = self.receive()
        w.record_result_handoff(self.root, request)
        # Remove only the synthetic coordination reservation to exercise an
        # older native record that predates this new module, without rewriting
        # or rehashing the native ledger itself.
        self.a.conn.execute("DELETE FROM reservations")
        malformed = {key: value for key, value in request.items() if key != "source_reply_sha256"}
        with self.assertRaisesRegex(w.WorkflowError, "payload/evidence differs"):
            w.record_result_handoff(self.root, malformed)

    def test_native_validation_refusal_readbacks_absent_then_allows_repair(self):
        request = self.receive(source_reply_sha256="invalid")
        with self.assertRaisesRegex(w.WorkflowError, "非空回复哈希"):
            w.record_result_handoff(self.root, request)
        rows = w._result_handoff_rows(self.root, self.base["task_id"])
        self.assertFalse(any(row["event"] == "controller_received" for row in rows))
        request["source_reply_sha256"] = "b"*64
        self.assertEqual(w.record_result_handoff(self.root, request)[0]["result"], "recorded")

    def test_operations_control_pin_conversion_commits_and_replays_once(self):
        w.record_result_handoff(self.root, self.receive())
        proof = self.root / 'reports/applied-control.json'
        proof.parent.mkdir(exist_ok=True)
        proof.write_text('{"synthetic": true}')
        pin = w.file_digest(self.root, 'reports/applied-control.json')
        decision = {**self.base, 'event': 'controller_decision', 'idempotency_key': 'ops-rework',
                    'decision': 'rework', 'next_owner': 'operations', 'next_action': 'apply exact internal control',
                    'evidence_paths': ['reports/applied-control.json']}
        w.record_result_handoff(self.root, decision)
        request = {**self.base, 'event': 'controller_followthrough', 'idempotency_key': 'ops-applied',
                   'followthrough_status': 'internal_control_completed', 'action_reference': 'synthetic-control',
                   'control_applied_proof': 'reports/applied-control.json',
                   'evidence_paths': ['reports/applied-control.json']}
        # Only the independent-control verifier is stubbed; native append,
        # path-to-pin normalization, reservation commit and replay are real.
        with mock.patch.object(w, '_verify_operations_rework_completion',
                               return_value={'control_applied_proof': pin}):
            first, _ = w.record_result_handoff(self.root, request)
        again, _ = w.record_result_handoff(self.root, request)
        self.assertEqual(first['control_applied_proof'], pin)
        self.assertEqual(again['record_id'], first['record_id'])
        self.assertEqual(again['result'], 'duplicate_ignored')
        committed = self.a.conn.execute("SELECT status FROM reservations WHERE effect_key=?",
                                       (coordination._sha(['controller_followthrough', 'ops-applied']),)).fetchone()
        self.assertEqual(committed['status'], 'committed')
        proof.write_text('{"synthetic": "changed"}')
        with self.assertRaisesRegex(w.WorkflowError, 'different semantic payload|payload/evidence differs'):
            w.record_result_handoff(self.root, request)

    def test_pending_malformed_outbox_type_is_controlled_recovery(self):
        rows = w._result_handoff_rows(self.root, self.base['task_id'])
        for malformed in [None, [], 'not-an-object', True]:
            bad = [dict(row, outbox=malformed) for row in rows]
            with self.subTest(malformed=malformed), mock.patch.object(w, '_result_handoff_rows', return_value=bad):
                with self.assertRaisesRegex(w.WorkflowError, 'outbox'):
                    w.result_handoff_pending(self.root)


if __name__ == "__main__":
    unittest.main()
