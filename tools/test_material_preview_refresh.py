import copy
import datetime as dt
import unittest
from pathlib import Path
from unittest.mock import patch

import material_preview_execution as m
import material_preview_refresh as refresh
import workflow_control as w


class MaterialPreviewRefreshTests(unittest.TestCase):
    def fixture(self):
        target = {'slug': 'sintered-stone-grey', 'action_id': 'save-sintered-stone-grey-bilingual-body-v1',
                  'record_id': 'original', 'scope': 'original-scope', 'candidate_version': 'original-version',
                  'payload_sha256': 'a' * 64}
        now = dt.datetime(2026, 11, 7, 8, tzinfo=dt.timezone.utc)
        parent = {'id': 123, 'event': 'workflow_dispatch', 'status': 'completed', 'conclusion': 'success',
                  'run_attempt': 1, 'head_sha': 'b' * 40, 'head_branch': 'main', 'path': m.WORKFLOW,
                  'actor': {'id': 276684684}, 'repository': {'id': 1248188229}}
        receipt = {'task_id': m.TASK, 'action_id': target['action_id'], 'scope': target['scope'],
                   'candidate_version': target['candidate_version'], 'operation': 'publish',
                   'http_status': 200, 'dry_run': True, 'performed_write': False, 'external_writes': 0,
                   'row_unchanged_after_dry_run': True, 'checked_at': '2026-11-07T07:00:00Z',
                   'expected_updated_at': 'original-CAS'}
        record = {'id': target['record_id'], 'slug': target['slug'], 'updated_at': 'original-CAS',
                  **{'original_' + str(i): 'retained' for i in range(56)}}
        docs = {'locked-dry-run-receipt.json': receipt,
                'managed-identity-probe.json': {'ok': True, 'dry_run': True, 'performed_write': False,
                    'identity': {'runId': 123, 'runAttempt': 1, 'actorId': 276684684,
                                 'repositoryId': 1248188229, 'workflowSha': 'b' * 40,
                                 'workflowRef': m.REPO + '/' + m.WORKFLOW + '@refs/heads/main'}},
                'managed-payload-digest.json': {'task_id': m.TASK, 'operation': 'publish',
                    'payload_sha256': 'a' * 64, 'expected_updated_at': 'original-CAS'},
                'backup.json': {'table': 'materials', 'record': record}}
        return target, parent, docs, now

    def test_only_expired_provider_zero_receipt_can_have_one_successor(self):
        target, parent, docs, now = self.fixture()
        refresh.validate_parent(parent, target, 'b' * 40, docs, now)
        for changes in ({'performed_write': True}, {'external_writes': 1}, {'checked_at': '2026-11-07T07:59:00Z'},
                        {'action_id': 'another-action'}, {'scope': 'another-scope'}):
            altered = copy.deepcopy(docs); altered['locked-dry-run-receipt.json'].update(changes)
            with self.assertRaises(w.WorkflowError):
                refresh.validate_parent(parent, target, 'b' * 40, altered, now)
        for changes in ({'conclusion': 'failure'}, {'run_attempt': 2}, {'head_sha': 'c' * 40}):
            with self.assertRaises(w.WorkflowError):
                refresh.validate_parent({**parent, **changes}, target, 'b' * 40, docs, now)

    def test_successor_scope_has_deterministic_key_and_cannot_refresh_a_save_command(self):
        root = Path('/original')
        slug = m.SLUGS[0]
        base = m.action(slug)
        with m.previous_preview(root, 123):
            self.assertEqual(m.action(slug), base + '-after-zero-123')
            self.assertEqual(m.parse_action(m.action(slug)), (slug, 123))
            self.assertIn('mode=dry-run', m.dispatch_argv(slug))
            self.assertNotIn('mode=publish', m.dispatch_argv(slug))
        self.assertEqual(m.action(slug), base)
        for bad in (0, -1, '123', True):
            with self.assertRaises(w.WorkflowError), m.previous_preview(root, bad):
                pass

    def test_preflight_refresh_cannot_change_body_cas_or_inherit_save_permission(self):
        target, parent, docs, now = self.fixture()
        old = {'task_id': m.TASK, 'department': 'publishing', 'action_id': target['action_id'],
               'action_class': 'cms_write', 'scope': target['scope'], 'candidate_version': target['candidate_version'],
               'risk_level': 'R2', 'payload_sha256': target['payload_sha256'], 'self_check': {'path': 'old-check'}}
        new = {**old, 'self_check': {'path': 'new-check'}, 'replaces_preflight': {'path': 'old'}}
        check = {'candidate': {'path': 'candidate'}, 'record_id': 'original', 'changed_fields': ['content_en','content_zh'],
                 'expected_updated_at': 'original-CAS', 'payload_sha256': 'a' * 64,
                 'source_verification': {'path': 'WEB'}, 'executor_department': 'publishing'}
        new_run = {**parent, 'id': 456, 'display_title': 'two-original-material-body-sintered-stone-grey | dry-run'}
        values = {'old': old, 'old-check': {**check, 'actual_machine': {'path': 'old-machine'}},
                  'new-check': {**check, 'actual_machine': {'path': 'new-machine'}},
                  'old-machine': {'run_snapshot': {'path': 'old-run'}}, 'new-machine': {'run_snapshot': {'path': 'new-run'}},
                  'old-run': parent, 'new-run': new_run}
        policy = {'action_id': m.PREFIX + 'sintered-stone-grey-after-zero-123', 'department': 'publishing',
                  'action_class': 'site_ci_prepare', 'Save_allowed': False,
                  'provider_facts': {'verified_zero_write_predecessor': {'run_id': 123}}}
        with patch('paid_three_page_bounded_cms.doc', side_effect=lambda root, pin: values[pin['path']]), \
             patch.object(refresh.w, 'read_jsonl', return_value=[policy]):
            self.assertTrue(refresh.validate_preflight_refresh(Path('/unused'), old, new))
            with self.assertRaises(w.WorkflowError):
                refresh.validate_preflight_refresh(Path('/unused'), old, {**new, 'payload_sha256': 'changed'})
            values['new-check']['expected_updated_at'] = 'changed-CAS'
            with self.assertRaises(w.WorkflowError):
                refresh.validate_preflight_refresh(Path('/unused'), old, new)


if __name__ == '__main__':
    unittest.main()
