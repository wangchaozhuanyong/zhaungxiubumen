import unittest
from pathlib import Path
import material_current_pub_admission as m
import workflow_control as w


class CurrentPUBMaterialAdmissionTests(unittest.TestCase):
    def test_only_canonical_normal_registration_command_is_proven(self):
        root = Path('/original/project')
        path = 'drafts/own.json'
        command = '/usr/bin/python3 -B tools/goal_delivery_runtime.py preflight-record --task-id ' + m.TASK + ' --input ' + path
        self.assertTrue(m.canonical_registration(root, command, path))
        for altered in (command.replace(m.TASK, 'another-task'), command.replace('own.json', 'another.json'),
                        command.replace('preflight-record', 'status'), command + ' ; echo fake', 'echo recorded'):
            self.assertFalse(m.canonical_registration(root, altered, path))

    def test_ordinary_or_other_actor_cannot_request_material_rotation_admission(self):
        for request in ({'task_id': 'another'}, {'task_id': m.TASK, 'department': 'operations'},
                        {'task_id': m.TASK, 'department': 'publishing', 'action_class': 'cms_write',
                         'consume_approval': True, 'approval_id': 'borrowed-old'}):
            with self.assertRaises(w.WorkflowError):
                m.admit(Path('/unused'), request)


if __name__ == '__main__':
    unittest.main()
