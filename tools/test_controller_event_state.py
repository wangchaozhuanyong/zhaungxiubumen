import copy
import datetime as dt
import unittest
from unittest import mock

import controller_event_state as state
import workflow_control as workflow
import test_runtime_qa_admission as fixture


class CurrentEventStateTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixture.ExactRuntimeQA('runTest')
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.root, self.task = self.fixture.root, self.fixture.task_id
        self.department = 'content-organic-website'
        sent = self.fixture.receipt('dispatch_sent', self.department, 'event-test-send')
        self.fixture.receipt('chat_ack', self.department, 'event-test-ack')
        self.watch = {'task_id': self.task, 'department': self.department,
                      'candidate_version': 'v1', 'dispatch_receipt_id': sent['receipt_id'],
                      'turn_id': 'exact-turn', 'event_cursor': 'exact-cursor'}
        self.checkpoint = {'active_tasks': [self.watch]}
        self.fixture.write('logs/current-checkpoint.json', self.checkpoint)
        self.fixture.write('data/content/organic-execution-policy.json', {
            'keyword_content_coverage_acceptance': {'controller_checkpoint': 'logs/current-checkpoint.json'}})
        self.queue = {'pending_count': 0, 'followthrough_pending_count': 0}

    def inspect(self, rows=None):
        with mock.patch.object(workflow, 'result_handoff_pending', return_value=self.queue), \
                mock.patch.object(workflow, '_result_handoff_rows', return_value=rows or []):
            return state.derive(self.root)[0]

    def result(self, status='completed', decision='continue', follow=True):
        path = 'logs/department-outbox/current-result.json'
        box = self.fixture.box(self.department)
        box.update(status=status)
        self.fixture.write(path, box)
        digest = workflow.file_digest(self.root, path)['sha256']
        base = {'task_id': self.task, 'sender_department': self.department,
                'candidate_version': 'v1', 'result_sha256': digest,
                'outbox': workflow.file_digest(self.root, path),
                'created_at': dt.datetime.now(dt.timezone.utc).isoformat()}
        rows = [dict(base, event='controller_received', record_id='actual-intake'),
                dict(base, event='controller_decision', record_id='actual-decision', decision=decision)]
        if follow:
            rows.append(dict(base, event='controller_followthrough', record_id='actual-follow'))
        return rows

    def test_current_receipts_create_one_bounded_event_target(self):
        answer = self.inspect()
        self.assertEqual(answer['validation_errors'], [])
        self.assertEqual(answer['event_wait_targets'], [{'thread_id': 'fixed-content-organic-website',
                                                        'host_id': 'local', 'after_cursor': 'exact-cursor'}])
        self.assertEqual(answer['max_wait_ms_per_call'], 60000)
        self.assertFalse(answer['result_queue_auto_wakes_ended_controller'])

    def test_yesterdays_manual_cache_is_not_read(self):
        self.fixture.write('data/controller-event-continuation.json', {'watched_tasks': [{'task_id': 'yesterday'}]})
        self.assertEqual(self.inspect()['watched_tasks'][0]['task_id'], self.task)

    def test_latest_policy_pointer_replaces_old_checkpoint(self):
        self.fixture.write('logs/new-checkpoint.json', {'active_tasks': []})
        self.fixture.write('data/content/organic-execution-policy.json', {
            'keyword_content_coverage_acceptance': {'controller_checkpoint': 'logs/new-checkpoint.json'}})
        self.assertEqual(self.inspect()['watched_tasks'], [])

    def test_duplicate_checkpoint_watch_is_one_wait(self):
        self.fixture.write('logs/current-checkpoint.json', {'active_tasks': [self.watch, self.watch]})
        self.assertEqual(len(self.inspect()['watched_tasks']), 1)

    def test_missing_cursor_on_second_exact_watch_requires_fresh_snapshot(self):
        other = dict(self.watch, candidate_version='v2', event_cursor='')
        self.fixture.write('logs/current-checkpoint.json', {'active_tasks': [self.watch, other]})
        self.assertEqual(self.inspect()['event_wait_targets'], [{
            'thread_id': 'fixed-content-organic-website', 'host_id': 'local'}])

    def test_closed_workflow_does_not_stand_in_for_intake(self):
        path = workflow.snapshot_path(self.root, self.task)
        snapshot = workflow.read_json(path)
        snapshot['current_state'] = 'closed'
        workflow.atomic_write_json(path, snapshot)
        self.assertEqual(len(self.inspect()['watched_tasks']), 1)

    def test_received_without_decision_remains_watched(self):
        self.assertEqual(len(self.inspect(self.result()[:1])['watched_tasks']), 1)

    def test_decided_without_action_remains_watched(self):
        self.assertEqual(len(self.inspect(self.result(follow=False))['watched_tasks']), 1)

    def test_exact_accepted_close_scope_clears_only_watch(self):
        answer = self.inspect(self.result(decision='close_scope', follow=False))
        self.assertEqual(answer['watched_tasks'], [])
        self.assertFalse(answer['business_goal_closed'])

    def test_real_followthrough_clears_completed_partial_rework_or_external_scope(self):
        for status in ['completed', 'partial', 'blocked', 'needs_input']:
            with self.subTest(status=status):
                answer = self.inspect(self.result(status))
                self.assertEqual(len(answer['resolved_watches']), 1)
                self.assertFalse(answer['business_goal_closed'])

    def test_old_candidate_cannot_clear_new_watch(self):
        rows = self.result()
        for row in rows:
            row['candidate_version'] = 'old-v0'
        self.assertEqual(len(self.inspect(rows)['watched_tasks']), 1)

    def test_changed_outbox_pin_is_recovery_not_closed(self):
        rows = self.result()
        self.fixture.write(rows[0]['outbox']['path'], {'changed': True})
        answer = self.inspect(rows)
        self.assertEqual(len(answer['watched_tasks']), 1)
        self.assertEqual(answer['validation_errors'][0]['reason'], 'settled_result_hash_changed')

    def test_actual_nested_outbox_ledger_schema_resolves_without_input_only_field(self):
        rows = self.result()
        self.assertNotIn('outbox_path', rows[0])
        answer = self.inspect(rows)
        self.assertEqual(answer['validation_errors'], [])
        self.assertEqual(len(answer['resolved_watches']), 1)

    def test_missing_or_outside_outbox_is_recovery_without_crash(self):
        for path in [None, '/outside-project/result.json']:
            rows = self.result()
            rows[0]['outbox'] = {'path': path}
            answer = self.inspect(rows)
            self.assertEqual(len(answer['watched_tasks']), 1)
            self.assertEqual(answer['validation_errors'][0]['reason'], 'settled_result_outbox_unavailable')

    def test_legacy_flat_outbox_path_still_requires_matching_real_bytes(self):
        rows = self.result()
        rows[0]['outbox_path'] = rows[0].pop('outbox')['path']
        self.assertEqual(len(self.inspect(rows)['resolved_watches']), 1)

    def test_malformed_outbox_type_keeps_watch_and_reports_recovery(self):
        for malformed in ['not-an-object', [], True, 1]:
            with self.subTest(malformed=malformed):
                rows = self.result()
                rows[0]['outbox'] = malformed
                answer = self.inspect(rows)
                self.assertEqual(len(answer['watched_tasks']), 1)
                self.assertEqual(answer['resolved_watches'], [])
                self.assertEqual(answer['validation_errors'][0]['reason'], 'settled_result_outbox_not_object')

    def test_null_or_absent_outbox_without_legacy_path_keeps_watch(self):
        for missing in [True, False]:
            rows = self.result()
            if missing:
                rows[0].pop('outbox')
            else:
                rows[0]['outbox'] = None
            self.assertEqual(len(self.inspect(rows)['watched_tasks']), 1)

    def test_invalid_checkpoint_cannot_silently_erase_active_work(self):
        path = self.root / 'logs/current-checkpoint.json'
        for raw in ['{"active_tasks": []}\\n', 'null', '{}']:
            path.write_text(raw)
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                self.inspect()
        raw = '{"active_tasks": [null]}'
        path.write_text(raw)
        with self.subTest(raw=raw):
            answer = self.inspect()
            self.assertEqual(answer['validation_errors'], [{
                'task_id': None, 'reason': 'active task row must be object', 'row_quarantined': True}])
            self.assertEqual(answer['watched_tasks'], [])
            self.assertEqual(answer['resolved_watches'], [])
            self.assertEqual(answer['event_wait_targets'], [])
            self.assertFalse(answer['business_goal_closed'])
            self.assertEqual(answer['permissions_issued'], 0)
            self.assertEqual(path.read_text(), raw)

    def test_invalid_checkpoint_row_does_not_erase_valid_watch(self):
        before = self.inspect()
        self.fixture.write('logs/current-checkpoint.json', {'active_tasks': [self.watch, None]})
        path = self.root / 'logs/current-checkpoint.json'
        checkpoint_before = path.read_bytes()
        answer = self.inspect()
        self.assertEqual(answer['validation_errors'], [{
            'task_id': None, 'reason': 'active task row must be object', 'row_quarantined': True}])
        self.assertEqual(answer['watched_tasks'], before['watched_tasks'])
        self.assertEqual(answer['event_wait_targets'], before['event_wait_targets'])
        self.assertEqual(len(answer['watched_tasks']), 1)
        self.assertEqual(answer['resolved_watches'], [])
        self.assertFalse(answer['business_goal_closed'])
        self.assertEqual(answer['permissions_issued'], 0)
        self.assertEqual(path.read_bytes(), checkpoint_before)

    def test_unknown_dispatch_id_does_not_create_native_wait_target(self):
        watch = dict(self.watch, dispatch_receipt_id='not-sent')
        self.fixture.write('logs/current-checkpoint.json', {'active_tasks': [watch]})
        answer = self.inspect()
        self.assertEqual(answer['event_wait_targets'], [])
        self.assertTrue(answer['validation_errors'])

    def test_stale_chat_binding_is_not_rebound_or_guessed(self):
        registry = workflow.read_json(self.root / 'data/department-registry.json')
        next(row for row in registry['departments'] if row['id'] == self.department)['chat_binding']['task_id'] = 'replacement'
        workflow.atomic_write_json(self.root / 'data/department-registry.json', registry)
        self.assertTrue(self.inspect()['validation_errors'])

    def test_other_project_is_not_a_watch(self):
        registry = workflow.read_json(self.root / 'data/department-registry.json')
        next(row for row in registry['departments'] if row['id'] == self.department)['chat_binding']['project_id'] = 'other'
        workflow.atomic_write_json(self.root / 'data/department-registry.json', registry)
        self.assertEqual(self.inspect()['validation_errors'][0]['reason'], 'incomplete_or_cross_project_watch')

    def test_no_ACK_and_failed_queue_never_claim_finished(self):
        with mock.patch.object(workflow, '_validate_receipt_chain', return_value=([
                row for row in workflow.read_jsonl(workflow.receipts_path(self.root, self.task))
                if row['receipt_type'] == 'dispatch_sent'], [])):
            answer = self.inspect()
        self.assertEqual(answer['validation_errors'][0]['reason'], 'nonempty_ACK_missing')

    def test_repeated_inspection_preserves_all_original_ledgers(self):
        before = workflow.receipts_path(self.root, self.task).read_bytes()
        first, second = self.inspect(), self.inspect()
        for answer in [first, second]:
            self.assertEqual(answer['messages_sent'], 0)
            self.assertEqual(answer['permissions_issued'], 0)
        self.assertEqual(before, workflow.receipts_path(self.root, self.task).read_bytes())


if __name__ == '__main__':
    unittest.main()
