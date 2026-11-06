import datetime as dt
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import receipt_obligation_consumer as consumer
import result_coordination as results
import workflow_control as workflow


class RootSerialReadyDiscoveryTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(
            dir=Path(__file__).resolve().parents[1] / '.test-tmp')
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.window = 'original-window'
        self.turn_id = 'original-turn'
        self.scope = 'project:example:delivery'
        evidence = self.write('evidence.json', {'checked': True})
        self.outbox = self.write('outbox.json', {
            'task_id': 'original-goal-v1', 'department': 'system-development',
            'scope': self.scope, 'status': 'partial', 'evidence': [evidence],
        })
        self.identity = {
            'task_id': 'original-goal-v1', 'sender_department': 'system-development',
            'candidate_version': 'batch-v1', 'result_sha256': self.outbox['sha256'],
        }
        self.ready = {'type': 'agentMessage', 'phase': 'commentary', 'id': 'ready',
                      'text': 'FLASHCAST_DELIVERY_READY ' + json.dumps({
                          **self.identity, 'outbox_path': self.outbox['path'], 'batch_complete': True,
                      })}
        self.final = {'type': 'agentMessage', 'phase': 'final_answer', 'id': 'final',
                      'text': 'Readback complete. Evidence: evidence.json'}
        self.turn = {'id': self.turn_id, 'status': 'completed', 'startedAt': 1,
                     'completedAt': 2, 'items': [self.ready, self.final]}
        self.thread = {'id': self.window, 'status': {'type': 'idle'}}
        self.queue = {'outbox': self.outbox, 'source_thread_id': self.window,
                      'source_turn_id': self.turn_id}
        self.record_path = 'serial.json'
        self.write(self.record_path, {
            'schema': 'hq-serial-original-recovery-intent/v1', 'one_new_window_at_a_time': True,
            'current_active_original_window': self.window, 'current_active_turn': self.turn_id,
            'current_scope': self.scope, 'current_state': 'inProgress',
        })

    def write(self, relative, document):
        (self.root / relative).write_text(json.dumps(document), encoding='utf-8')
        return workflow.file_digest(self.root, relative)

    def observe(self):
        history = Mock()
        history.call.side_effect = [{'thread': self.thread}, {'data': [self.turn]}]
        with patch.object(consumer, 'ROOT_SERIAL_PATH', self.record_path), \
                patch.object(consumer, '_root_slot_read', return_value=None), \
                patch.object(results, '_validate_queued', return_value=self.queue) as queued:
            outcome = consumer.observe_root_serial(self.root, SimpleNamespace(history=history))
        return outcome, queued

    def test_recovers_from_exact_ready_without_sha_in_final_or_caller_event(self):
        outcome, queued = self.observe()
        self.assertTrue(outcome['root_release_recorded'], outcome)
        self.assertFalse(outcome['business_goal_closed'])
        queued.assert_called_with(self.root, self.identity)

    def test_maintenance_final_cannot_release_business(self):
        self.final['text'] = 'Maintenance complete.'
        outcome, _ = self.observe()
        self.assertFalse(outcome['root_release_recorded'])

    def test_completed_notification_accepts_separate_newer_finite_head(self):
        latest = {**self.turn, 'id': 'later-turn', 'startedAt': 3, 'completedAt': 4,
                  'items': [{**self.final, 'id': 'later-final'}]}
        proof = {'fresh_current_head': {'thread': self.thread, 'turns': [latest]}}
        observed = dt.datetime.fromtimestamp(5, dt.timezone.utc)
        self.assertEqual(consumer._notification_refresh_head(proof, self.window, self.turn, observed),
                         latest)
        self.assertEqual(self.turn['id'], self.turn_id)

    def test_notification_refresh_rejects_overlapping_or_active_head(self):
        latest = {**self.turn, 'id': 'later-turn', 'startedAt': 1.5, 'completedAt': 4}
        proof = {'fresh_current_head': {'thread': dict(self.thread), 'turns': [latest]}}
        observed = dt.datetime.fromtimestamp(5, dt.timezone.utc)
        with self.assertRaisesRegex(workflow.WorkflowError, 'overlap'):
            consumer._notification_refresh_head(proof, self.window, self.turn, observed)
        latest['startedAt'] = 3
        proof['fresh_current_head']['thread']['status'] = {'type': 'active'}
        with self.assertRaisesRegex(workflow.WorkflowError, 'active'):
            consumer._notification_refresh_head(proof, self.window, self.turn, observed)

    def test_queued_result_from_other_turn_cannot_release_current_turn(self):
        self.queue['source_turn_id'] = 'previous-turn'
        outcome, _ = self.observe()
        self.assertFalse(outcome['root_release_recorded'])

    def test_conflicting_ready_declarations_do_not_supply_identity(self):
        self.turn['items'].insert(1, {**self.ready, 'id': 'duplicate'})
        outcome, queued = self.observe()
        self.assertFalse(outcome['root_release_recorded'])
        queued.assert_not_called()


if __name__ == '__main__':
    unittest.main()
