"""Project-local synthetic integration; no live ledger or platform mutations."""
import copy
import datetime as dt
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock

import workflow_control as w
import test_workflow_control as legacy
import test_goal_result_coordination as goals
import result_coordination as coordination


class ThroughputTests(unittest.TestCase):
    def setUp(self):
        self.f = legacy.WorkflowControlTests('runTest')
        self.f.setUp()
        self.addCleanup(self.f.tearDown)
        self.root = self.f.root

    def native(self, base, **changes):
        text = base['task_id'] + ' 实际完成本次有限交付；候选等待独立验收。\n'
        native = {'thread': {'id': 'fixed-content-organic-website'}, 'turn_id': 'synthetic-final-turn',
                  'status': 'completed', 'error': None, 'completedAt': dt.datetime.now(dt.timezone.utc).timestamp(),
                  'message': {'id': 'synthetic-final-message', 'turnId': 'synthetic-final-turn',
                              'phase': 'final_answer', 'text': text}}
        native.update(changes)
        w.atomic_write_json(self.root / 'reports/completed.json', native)
        (self.root / 'reports/final.txt').write_bytes(text.encode('utf-8'))
        return {**base, 'event': 'notification_queued', 'idempotency_key': 'queue-final',
                'source_thread_id': 'fixed-content-organic-website', 'source_turn_id': 'synthetic-final-turn',
                'source_reply_sha256': hashlib.sha256(text.encode('utf-8')).hexdigest(),
                'reply_observed_at': dt.datetime.now(dt.timezone.utc).isoformat(),
                'actual_native_completion': w.file_digest(self.root, 'reports/completed.json'),
                'visible_reply': w.file_digest(self.root, 'reports/final.txt')}

    def goal_queue(self, status='partial'):
        base, _ = self.f._result_handoff_fixture()
        path = self.root / base['outbox_path']
        box = w.read_json(path); box['status'] = status
        w.atomic_write_json(path, box)
        base['result_sha256'] = w.file_digest(self.root, base['outbox_path'])['sha256']
        goals.configure(self.root)
        snapshot = w.read_json(w.snapshot_path(self.root, base['task_id']))
        snapshot['goal_delivery'] = goals.goal('operations-assistant-2')
        snapshot['goal_delivery']['authorization_pin'] = w.file_digest(self.root, 'reports/synthetic-owner-message.json')
        w.atomic_write_json(w.snapshot_path(self.root, base['task_id']), snapshot)
        return self.native(base)

    def test_terminal_delivery_statuses_queue_completed_final_without_claiming_whole_goal(self):
        request = self.goal_queue()
        for index, status in enumerate(('completed', 'partial', 'qa_rework', 'external_blocked', 'queue_failed')):
            path = self.root / request['outbox_path']
            box = w.read_json(path); box.update(status=status, candidate_version=f'candidate-{index}')
            w.atomic_write_json(path, box)
            current = {**request, 'candidate_version': box['candidate_version'],
                       'result_sha256': w.file_digest(self.root, request['outbox_path'])['sha256'],
                       'idempotency_key': f'queue-{index}'}
            with self.subTest(status=status):
                row, _ = w.record_result_handoff(self.root, current)
                self.assertEqual(row['actual_native_completion'], request['actual_native_completion'])
                self.assertFalse(row['business_goal_closed'])
                self.assertFalse(row['interrupts_active_thread'])
                again, _ = w.record_result_handoff(self.root, current)
                self.assertEqual(again['record_id'], row['record_id'])
                self.assertEqual(again['result'], 'duplicate_ignored')

    def test_missing_native_or_ack_commentary_wrong_turn_fail_without_ledger(self):
        request = self.goal_queue()
        bads = [{**request, 'actual_native_completion': None}, {**request, 'source_turn_id': 'other'},
                {**request, 'source_thread_id': 'other'}, {**request, 'source_reply_sha256': 'a'*64}]
        original = w.read_json(self.root / 'reports/completed.json')
        for field, value in [('status', 'in_progress'), ('status', 'idle'), ('error', 'failed')]:
            doc = copy.deepcopy(original); doc[field] = value
            w.atomic_write_json(self.root / f'reports/bad-{field}-{value}.json', doc)
            bads.append({**request, 'actual_native_completion': w.file_digest(self.root, f'reports/bad-{field}-{value}.json')})
        doc = copy.deepcopy(original); doc['message']['phase'] = 'commentary'
        w.atomic_write_json(self.root / 'reports/commentary.json', doc)
        bads.append({**request, 'actual_native_completion': w.file_digest(self.root, 'reports/commentary.json')})
        for bad in bads:
            with self.subTest(bad=bad['actual_native_completion']), self.assertRaises(w.WorkflowError):
                w.record_result_handoff(self.root, bad)
        self.assertFalse(w.result_handoff_path(self.root, request['task_id']).exists())
        self.assertEqual(w.record_result_handoff(self.root, request)[0]['result'], 'recorded')

    def test_assistant_intake_preserves_original_final_and_rejects_later_ack(self):
        request = self.goal_queue()
        w.record_result_handoff(self.root, request)
        store = coordination.CoordinationStore(self.root); self.addCleanup(store.close)
        identity = coordination.exact_identity(request)
        lease = store.claim(identity, 'operations-assistant-2', 'a2-fixture', 'wake-final')
        receive = {**request, 'event': 'controller_received', 'idempotency_key': 'receive-final',
                   'intake_mode': 'queue', 'coordinator_role': lease['role'], 'coordinator_owner': lease['owner'],
                   'coordination_claim': lease}
        with self.assertRaisesRegex(w.WorkflowError, 'original completed final'):
            w.record_result_handoff(self.root, {**receive, 'source_reply_sha256': 'a'*64})
        row, _ = w.record_result_handoff(self.root, receive)
        self.assertEqual(row['source_turn_id'], request['source_turn_id'])
        self.assertEqual(row['actual_native_completion'], request['actual_native_completion'])

    def test_subsequent_completed_child_exact_parent_closes_only_control_link_once(self):
        request = self.f._inflight_result_fixture(linked_task=True, dispatch_after=True)
        request['followthrough_status'] = 'subsequent_action_verified'
        row, _ = w.record_result_handoff(self.root, request)
        self.assertFalse(row['dispatch_before_decision'])
        self.assertTrue(row['dispatch_after_decision'])
        self.assertFalse(row['business_goal_closed'])
        self.assertEqual(w.record_result_handoff(self.root, request)[0]['result'], 'duplicate_ignored')
        pending = w.result_handoff_pending(self.root, [self.f.task_id])
        self.assertEqual(pending['followthrough_pending_count'], 0)
        self.assertEqual(pending['historical_resolved_control_count'], 1)
        self.assertFalse(pending['control_records_are_business_jobs'])

    def test_subsequent_child_unrelated_parent_rejected(self):
        request = self.f._inflight_result_fixture(linked_task=True, dispatch_after=True, parent=False)
        request['followthrough_status'] = 'subsequent_action_verified'
        with self.assertRaisesRegex(w.WorkflowError, '原父任务'):
            w.record_result_handoff(self.root, request)

    def test_scoped_pending_ignores_unrelated_damaged_legacy_but_unscoped_is_strict(self):
        request = self.f._inflight_result_fixture(linked_task=True, dispatch_after=True)
        path = self.root / w.RESULT_HANDOFF_DIR / 'unrelated-legacy.jsonl'
        path.write_text('{broken historical ledger\n')
        with self.assertRaises(w.WorkflowError):
            w.result_handoff_pending(self.root)
        value = w.result_handoff_pending(self.root, [self.f.task_id])
        self.assertEqual(value['scope_task_ids'], [self.f.task_id])
        self.assertEqual(value['followthrough_pending_count'], 1)

    def test_readback_accepts_valid_handoff_path_and_rejects_outside_project(self):
        base, _ = self.f._result_handoff_fixture()
        target = self.root / 'logs/handoffs/exact-department/outbox.json'
        target.parent.mkdir(parents=True)
        target.write_bytes((self.root / base['outbox_path']).read_bytes())
        base['outbox_path'] = target.relative_to(self.root).as_posix()
        w.record_result_handoff(self.root, {**base, 'event':'notification_queued', 'idempotency_key':'valid-handoff'})
        tool = str(Path(__file__).with_name('result_handoff_readback.py'))
        result = subprocess.run([sys.executable, tool, '--root', str(self.root), '--outbox', str(target)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)['queue_verified'])
        outside = subprocess.run([sys.executable, tool, '--root', str(self.root), '--outbox', str(self.root.parent / 'outside.json')], capture_output=True, text=True)
        self.assertNotEqual(outside.returncode, 0)

    def test_future_named_wait_is_separate_from_due_and_historical_resolved(self):
        request = self.f._inflight_result_fixture(linked_task=True)
        # Existing actual continue decision may register a named, bounded wait.
        request.update(followthrough_status='blocked_with_owner', idempotency_key='named-future-wait',
                       next_check_at=(dt.datetime.now(dt.timezone.utc)+dt.timedelta(days=1)).isoformat(),
                       unblock_condition='named custodian supplies the exact current source')
        for key in ('linked_outbox_path', 'linked_task_id', 'linked_dispatch_receipt_id', 'action_receipt_id'):
            request.pop(key, None)
        w.record_result_handoff(self.root, request)
        value = w.result_handoff_pending(self.root, [self.f.task_id])
        self.assertEqual(value['named_waiting_dependency_count'], 1)
        self.assertEqual(value['followthrough_pending_count'], 0)
        self.assertEqual(value['historical_resolved_control_count'], 0)


if __name__ == '__main__':
    unittest.main()
