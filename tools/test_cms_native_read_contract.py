import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import cms_native_read_contract as contract


class NativeReadTests(unittest.TestCase):
    def setUp(self):
        self.request = dict(task_id=contract.TASK, action_id=contract.ACTION,
            action_class='cms_native_read', scope=contract.SCOPE,
            department='content-organic-website', table='services', slug='artistic-coating',
            field_pointers=contract.FIELDS, metadata_fields=contract.METADATA,
            lookup={'slug_equals': 'artistic-coating', 'require_exactly_one_row': True},
            read_only=True, production_write_allowed=False, protected_preview_allowed=False,
            login_or_account_change_allowed=False, credential_capture_allowed=False,
            full_row_export_allowed=False,
            source_method='existing_owner_signed_in_chrome_native_service_view')

    def test_only_original_two_description_fields_allowed(self):
        self.assertEqual(contract.validate_request(self.request), [])

    def test_no_operations_actor_or_publishing_handover(self):
        for department in ['operations', 'publishing', 'paid-growth-data']:
            request = {**self.request, 'department': department}
            self.assertTrue(contract.validate_request(request))

    def test_no_other_service_table_or_wildcard(self):
        for key, value in [('table', 'blog_posts'), ('slug', 'design'), ('slug', '*')]:
            self.assertTrue(contract.validate_request({**self.request, key: value}))

    def test_write_preview_credentials_and_account_changes_denied(self):
        for key in ['production_write_allowed', 'protected_preview_allowed',
                    'login_or_account_change_allowed', 'credential_capture_allowed',
                    'full_row_export_allowed']:
            self.assertTrue(contract.validate_request({**self.request, key: True}))

    def test_extra_pointer_or_metadata_denied(self):
        for key in ['field_pointers', 'metadata_fields']:
            self.assertTrue(contract.validate_request({**self.request, key: self.request[key] + ['*']}))

    def test_lookup_must_prove_unique_exact_slug(self):
        request = copy.deepcopy(self.request)
        request['lookup']['require_exactly_one_row'] = False
        self.assertTrue(contract.validate_request(request))

    def test_unknown_read_method_denied(self):
        self.assertTrue(contract.validate_request({**self.request, 'source_method': 'SQL'}))

    def test_mismatched_task_action_and_scope_denied(self):
        for key in ['task_id', 'action_id', 'scope']:
            self.assertTrue(contract.validate_request({**self.request, key: 'other'}))

    def test_frozen_request_payload_hash_is_required(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); path = root / 'request.json'
            path.write_text(json.dumps(self.request)); sha = hashlib.sha256(path.read_bytes()).hexdigest()
            binding = {k: self.request[k] for k in ['task_id', 'action_id', 'scope', 'department']}
            binding.update(request_path='request.json', request_sha256=sha)
            args = (root, binding, contract.TASK, contract.ACTION, contract.SCOPE,
                    'content-organic-website')
            self.assertEqual(contract.check_binding(*args, sha), [])
            self.assertTrue(contract.check_binding(*args, '0' * 64))
            path.write_text('{}')
            self.assertTrue(contract.check_binding(*args, sha))

    def test_missing_or_outside_project_request_denied(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            binding = {k: self.request[k] for k in ['task_id', 'action_id', 'scope', 'department']}
            for path in ['missing.json', '../request.json', '/tmp/request.json']:
                binding['request_path'] = path
                self.assertTrue(contract.check_binding(root, binding, contract.TASK, contract.ACTION,
                    contract.SCOPE, 'content-organic-website', '0' * 64))


if __name__ == '__main__':
    unittest.main()
