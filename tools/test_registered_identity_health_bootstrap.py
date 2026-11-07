import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import department_autonomy as autonomy
import workflow_control as workflow


class RegisteredIdentityHealthBootstrapTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        raw = b'{"identity_only": true}'
        (self.root / 'packet.json').write_bytes(raw)
        pin = {'path': 'packet.json', 'sha256': hashlib.sha256(raw).hexdigest(), 'size': len(raw)}
        fixed = {'task_id': 'original-role-chat', 'title': 'Original role',
                 'project_id': autonomy.PROJECT, 'cwd': str(self.root), 'sidebar_section_id': 'original-group'}
        self.registry = {'operations': {'chat_binding': {**fixed, 'task_id': 'original-hq'}},
                         'system-development': {'chat_binding': fixed}}
        self.snapshot = {'goal_contract': {'path': 'original-contract.json'}}
        self.request = {'action_class': 'thread_message', 'sender_department': 'operations',
                        'target_department': 'system-development',
                        'scope': 'department_health_probe:system-development',
                        'source_project_id': autonomy.PROJECT, 'target_project_id': autonomy.PROJECT,
                        'target_thread_id': fixed['task_id'], 'target_thread_title': fixed['title'],
                        'target_cwd': str(self.root), 'target_sidebar_section_id': fixed['sidebar_section_id'],
                        'assignment_record_required': False, 'payload': pin, 'payload_sha256': pin['sha256']}

    def route(self, request=None, exact=True):
        with patch.object(workflow, 'department_registry', return_value=self.registry), \
             patch.object(workflow, 'exact_health_probe', return_value=exact), \
             patch.object(workflow, '_chat_binding_healthy', return_value=True), \
             patch.object(autonomy, 'participant', return_value={}), \
             patch.object(autonomy, 'authority', return_value={}):
            return autonomy._registered_identity_health_route(self.root, self.snapshot, request or self.request)

    def test_exact_probe_has_no_business_or_external_permission(self):
        result = self.route()
        self.assertEqual(result['purpose'], 'registered_identity_health_bootstrap')
        self.assertFalse(result['business_producer_added'])
        self.assertFalse(result['external_permission_issued'])

    def test_unregistered_packet_and_business_scope_do_not_bootstrap(self):
        self.assertIsNone(self.route(exact=False))
        self.assertIsNone(self.route({**self.request, 'scope': 'business:implementation'}))

    def test_other_actor_cannot_bootstrap(self):
        self.assertIsNone(self.route({**self.request, 'sender_department': 'system-development'}))

    def test_execution_fields_and_wrong_target_are_rejected(self):
        for delta in ({'execution_request': {'operation': 'save'}}, {'consume_approval': True},
                      {'target_project_id': 'another-project'}, {'target_thread_id': 'another-chat'}):
            with self.subTest(delta=delta), self.assertRaises(workflow.WorkflowError):
                self.route({**self.request, **delta})

    def test_changed_payload_is_rejected(self):
        (self.root / 'packet.json').write_text(json.dumps({'business': 'save'}))
        with self.assertRaises(workflow.WorkflowError):
            self.route()


if __name__ == '__main__':
    unittest.main()
