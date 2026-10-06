import copy
import unittest
from result_handoff_readback import verify_readback


class ReadbackTests(unittest.TestCase):
    def setUp(self):
        self.identity = dict(task_id='fc-original-v1', sender_department='qa',
                             candidate_version='v2', result_sha256='a' * 64)
        self.row = {**self.identity, 'notification': 'queued',
                    'controller_received': False, 'controller_decision': 'pending',
                    'controller_followthrough': 'pending'}
        self.events = [{**self.identity, 'event': 'notification_queued', 'record_id': 'real-queue'}]

    def test_pending_received_and_decided_are_all_successful_queue_readbacks(self):
        for received, decision, expected in [(False, 'pending', 'queued'),
                (True, 'pending', 'controller_received'), (True, 'rework', 'controller_decided')]:
            row = {**self.row, 'controller_received': received, 'controller_decision': decision}
            self.assertEqual(verify_readback({'results': [row]}, self.events,
                                           self.identity)['current_phase'], expected)

    def test_selects_exact_second_result_without_using_global_pending_count(self):
        other = {**self.row, 'candidate_version': 'v1'}
        status = {'pending_count': 0, 'results': [other,
                  {**self.row, 'controller_received': True, 'controller_decision': 'continue'}]}
        before = copy.deepcopy((status, self.events))
        for _ in range(2):
            result = verify_readback(status, self.events, self.identity)
            self.assertEqual(result['queue_receipt_id'], 'real-queue')
            self.assertFalse(result['business_goal_closed'])
            self.assertEqual(result['mutation_count'], 0)
        self.assertEqual((status, self.events), before)

    def test_wrong_hash_version_department_or_task_cannot_replace_queue_receipt(self):
        for key, wrong in [('result_sha256', 'b' * 64), ('candidate_version', 'v1'),
                           ('sender_department', 'publishing'), ('task_id', 'fc-other-v1')]:
            with self.assertRaises(ValueError):
                verify_readback({'results': [self.row]}, [{**self.events[0], key: wrong}], self.identity)

    def test_missing_or_duplicate_queue_receipt_fails_closed(self):
        for events in [[], self.events * 2]:
            with self.assertRaises(ValueError):
                verify_readback({'results': [self.row]}, events, self.identity)

    def test_decision_without_intake_or_duplicate_exact_result_fails_closed(self):
        for rows in [[{**self.row, 'controller_decision': 'continue'}], [self.row, self.row]]:
            with self.assertRaises(ValueError):
                verify_readback({'results': rows}, self.events, self.identity)


if __name__ == '__main__':
    unittest.main()
