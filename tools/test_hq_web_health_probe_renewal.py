import json
import unittest
from unittest.mock import patch

import department_autonomy as a
import goal_delivery_runtime as g
import hq_web_health_probe as probe
import workflow_control as w


class RenewalTests(unittest.TestCase):
    def setUp(self):
        self.request = {'task_id': probe.TASK, 'action_id': probe.ACTION,
                        'delivery_mode': 'mcp_direct_send', 'target_thread_id': 'web',
                        'actual_target_state': 'current', 'actual_live_inventory': 'inventory',
                        'live_observed_at': '2026-11-05T06:00:00+00:00', 'payload': 'original-payload'}
        self.previous = {'checked_at': '2026-11-05T04:33:28+00:00'}
        self.snapshot = {'task_id': probe.TASK, 'goal_delivery': {'current_route_observations': {probe.ACTION: 'live'}}}
        self.head = {'id': 'original', 'completedAt': 1793752422, 'status': 'completed', 'error': None}
        self.page = {'thread': {'kind': 'codex', 'hostId': 'local', 'status': {'type': 'idle'}},
                     'page': {'order': 'newest_first'}, 'turns': [dict(self.head)]}
        self.documents = {'registration': {'decision': 'decision'},
                          'decision': {'actual_one_open_readback': 'opened'},
                          'opened': {'native': {'turns': [dict(self.head)]}},
                          'live': {'observed_at': self.request['live_observed_at'],
                                   'delivery_mode': 'mcp_direct_send', 'actual_native_observation': 'inventory',
                                   'actual_native_target_turns': {'web': 'current'}}}

    def renewal(self):
        with patch.object(probe.origin, 'digest', side_effect=lambda root, pin: json.dumps(self.documents[pin])), \
                patch.object(g, '_collaboration_native', return_value=self.page):
            return probe.renewal_source('.', self.snapshot, self.request, self.previous, 'registration')

    def test_renewal_pins_unchanged_native_head_and_payload(self):
        self.assertEqual(self.renewal()['original_target_turn'], 'original')
        self.assertEqual(self.renewal()['payload'], 'original-payload')

    def test_changed_head_missing_head_and_active_target_are_refused(self):
        original = dict(self.page)
        for change in ({'turns': [{**self.head, 'id': 'later'}]}, {'turns': []},
                       {'thread': {**self.page['thread'], 'status': {'type': 'active'}}}):
            with self.subTest(change=change):
                self.page = {**original, **change}
                with self.assertRaisesRegex(w.WorkflowError, 'effect is unknown'):
                    self.renewal()

    def test_old_observation_and_queue_mode_are_refused(self):
        self.request['live_observed_at'] = self.previous['checked_at']
        with self.assertRaisesRegex(w.WorkflowError, 'new normal direct probe observation'):
            self.renewal()
        self.request['live_observed_at'] = self.documents['live']['observed_at']
        self.request['delivery_mode'] = 'official_native_queue'
        with self.assertRaisesRegex(w.WorkflowError, 'new normal direct probe observation'):
            self.renewal()

    def test_reserved_direct_attempt_blocks_retry_even_without_receipt(self):
        event = {'details': {probe.DIRECT_INTENT: {'action_id': probe.ACTION}}}
        with patch.object(w, 'safe_path') as path, patch.object(w, 'read_jsonl', return_value=[event]):
            path.return_value.exists.return_value = False
            with self.assertRaisesRegex(w.WorkflowError, 'no new policy'):
                a._owner_message_transport_not_started('.', self.snapshot, self.request)
