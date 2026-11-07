import copy
import unittest
from pathlib import Path
from unittest.mock import patch

import material_preflight_metadata as m
import workflow_control as w


class MaterialSelfcheckMetadataTests(unittest.TestCase):
    def setUp(self):
        self.item = {'task_id': m.TASK, 'department': 'publishing', 'action_id': 'original',
                     'action_class': 'cms_write', 'scope': 'original-object',
                     'candidate_version': 'frozen', 'risk_level': 'R2'}
        self.before = {'primary_owner': 'publishing', 'authorization_pin': {'sha256': 'original'},
                       'required_execution_actions': [self.item.copy()], 'execution_preflights': []}
        self.after = {**self.before, 'execution_preflights': [self.item]}

    def test_only_original_append_is_neutral_and_cannot_mutate_authority(self):
        m.goal_delta(self.before, self.after, self.item)
        for changes in ({'primary_owner': 'operations'}, {'authorization_pin': {'sha256': 'new'}},
                        {'execution_preflights': []}, {'new_permission': True}):
            with self.assertRaises(w.WorkflowError):
                m.goal_delta(self.before, {**self.after, **changes}, self.item)

    def test_duplicate_other_actor_scope_and_sensitive_registration_are_rejected(self):
        with self.assertRaises(w.WorkflowError):
            m.goal_delta(self.after, {**self.after, 'execution_preflights': [self.item, self.item]}, self.item)
        for changes in ({'department': 'operations'}, {'scope': 'another-object'},
                        {'risk_level': 'R3'}, {'task_id': 'another-task'}):
            item = {**self.item, **changes}
            with self.assertRaises(w.WorkflowError):
                m.goal_delta(self.before, {**self.before, 'execution_preflights': [item]}, item)

    def test_unrelated_metadata_is_not_claimed_and_permission_event_is_rejected(self):
        self.assertFalse(m.metadata(Path('/unused'), {}, {'details': {'other': True}}))
        event = {'task_id': m.TASK, 'state': 'evidence_received', 'details':
                 {'goal_delivery': self.after, 'production_preflight_registered': {}, 'external_permission_issued': True}}
        with self.assertRaises(w.WorkflowError):
            m.metadata(Path('/unused'), {'task_id': m.TASK, 'current_state': 'evidence_received'}, event)


if __name__ == '__main__':
    unittest.main()
