import unittest
from pathlib import Path
from unittest.mock import patch
import material_original_owner_approval as m
import workflow_control as w


class OriginalMaterialApprovalTests(unittest.TestCase):
    def test_identity_cannot_change_actor_body_task_or_scope(self):
        request = {'task_id': m.TASK, 'action_id': 'original', 'action_class': 'cms_write',
                   'scope': 'original-row', 'department': 'publishing', 'payload_sha256': 'a' * 64}
        row = {**request, 'execution_department': 'publishing'}
        m.identity(row, request)
        for change in ({'scope': 'other'}, {'task_id': 'other'}, {'payload_sha256': 'b' * 64},
                       {'department': 'operations'}, {'action_class': 'site_publish'}):
            with self.assertRaises(w.WorkflowError):
                m.identity(row, {**request, **change})

    def test_consumed_or_expired_reference_is_not_renewed(self):
        request = {'task_id': m.TASK, 'action_id': 'original', 'action_class': 'cms_write',
                   'scope': 'original-row', 'department': 'publishing', 'payload_sha256': 'a' * 64}
        row = {**request, 'execution_department': 'publishing', 'status': 'consumed', 'single_use': True,
               'granted_by': 'operations', 'decision_actor': 'operations',
               'approval_basis': 'existing_owner_goal_and_real_HQ_routine_decision',
               'not_a_new_human_instruction': True, 'expires_at': '2099-01-01T00:00:00Z'}
        with patch.object(w, 'effective_approvals', return_value={'apr-material-original': row}), self.assertRaises(w.WorkflowError):
            m.active(Path('/unused'), request, 'apr-material-original')
        row.update(status='active', expires_at='2000-01-01T00:00:00Z')
        with patch.object(w, 'effective_approvals', return_value={'apr-material-original': row}), self.assertRaises(w.WorkflowError):
            m.active(Path('/unused'), request, 'apr-material-original')


if __name__ == '__main__':
    unittest.main()
