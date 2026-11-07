import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import material_hq_fallback as m
import workflow_control as w


class OriginalMaterialHQSourceTests(unittest.TestCase):
    def test_request_local_source_reuse_invalidates_changed_input(self):
        root = Path(__file__).resolve().parents[1]
        (root / 'logs').mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=root / 'logs') as directory:
            source = Path(directory) / 'source.json'
            source.write_text('{"version":1}')
            def compute(*args):
                return {'input': w.read_json(source), 'external_permission_issued': False}
            with w.request_validation_context(), patch.object(m, '_validate', side_effect=compute) as validate:
                self.assertEqual(m.validate(root, {'original': 'same'}), m.validate(root, {'original': 'same'}))
                self.assertEqual(validate.call_count, 1)
                source.write_text('{"version":2}')
                self.assertEqual(m.validate(root, {'original': 'same'})['input']['version'], 2)
                self.assertEqual(validate.call_count, 2)
            with w.request_validation_context(), patch.object(m, '_validate', side_effect=compute) as validate:
                m.validate(root, {'original': 'same'})
                self.assertEqual(validate.call_count, 1)

    def test_historical_registration_uses_preceding_goal_and_rejects_owner_change(self):
        root = Path(__file__).resolve().parents[1]
        goal = {'primary_owner': 'publishing', 'approved_actions': []}
        pin = {'path': 'source', 'sha256': 'a' * 64, 'size': 1}
        action = {'task_id': m.TASK, 'action_id': m.ACTION}
        event = {'event_id': 'new', 'task_id': m.TASK, 'state': 'evidence_received',
                 'details': {m.EVENT: pin, 'goal_delivery': {**goal, 'approved_actions': [{**action, m.MARKER: pin}]},
                             'actual_message_sent': False, 'external_permission_issued': False}}
        prior = {'event_id': 'old', 'details': {'goal_delivery': goal}}
        formal = {'task_id': m.TASK, 'current_state': 'evidence_received'}
        with patch.object(m.w, 'read_jsonl', return_value=[prior, event]), \
             patch.object(m.a, 'document', return_value={}), \
             patch.object(m, '_validate', return_value={'action': action}) as validate:
            self.assertTrue(m.metadata(root, formal, event))
            self.assertTrue(validate.call_args.kwargs['metadata_only'])
            changed = copy.deepcopy(event)
            changed['details']['goal_delivery']['primary_owner'] = 'operations'
            with patch.object(m.w, 'read_jsonl', return_value=[prior, changed]), self.assertRaises(w.WorkflowError):
                m.metadata(root, formal, changed)

    def test_later_other_action_observation_is_not_claimed(self):
        event = {'details': {'goal_delivery': {'current_route_observations': {m.ACTION: {'path': 'old'}}},
                             'actual_route_observation': {'path': 'another'}, 'external_permission_issued': False}}
        self.assertFalse(m.metadata(Path('/unused'), {}, event))


if __name__ == '__main__':
    unittest.main()
