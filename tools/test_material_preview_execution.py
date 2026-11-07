import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import material_preview_execution as m
import workflow_control as w


class MaterialPreviewTests(unittest.TestCase):
    def write_request(self, root):
        folder = m.directory(root, m.SLUGS[0]); folder.mkdir(parents=True, exist_ok=True)
        temporary = folder / 'fixture.json'
        w.atomic_write_json(temporary, {'same': 'source'})
        pin = w.file_digest(root, str(temporary.relative_to(root)))
        path = m.request_path(root, m.SLUGS[0], pin['sha256'])
        path.parent.mkdir(parents=True, exist_ok=True); temporary.rename(path)
        return pin['sha256']

    def test_late_identity_refresh_cannot_change_source_target_or_actual_turn(self):
        original = {'schema': m.SCHEMA, 'task_id': m.TASK, 'slug': m.SLUGS[0],
                    'source_verification': {'sha256': 'original'}, 'PUB_native': {'path': 'old'}}
        fresh = {**original, 'PUB_native': {'path': 'fresh'}}
        with patch('goal_delivery_runtime._native_document', return_value={'turns': [{'id': 'original-turn'}]}):
            self.assertEqual(m.validate_identity_refresh(Path('/unused'), original, fresh), fresh)
            for changes in ({'task_id': 'another'}, {'slug': m.SLUGS[1]},
                            {'source_verification': {'sha256': 'changed'}}, {'mode': 'publish'}):
                with self.assertRaises(w.WorkflowError):
                    m.validate_identity_refresh(Path('/unused'), original, {**fresh, **changes})
        with patch('goal_delivery_runtime._native_document', side_effect=[{'turns': [{'id': 'old'}]}, {'turns': [{'id': 'other'}]}]), self.assertRaises(w.WorkflowError):
            m.validate_identity_refresh(Path('/unused'), original, fresh)

    def test_same_process_source_phase_fences_inputs_and_never_skips_live_identity(self):
        project = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(dir=project / 'logs') as directory:
            root = Path(directory); dep = root / 'static.json'; dep.write_text('{"version":1}')
            def source(*args):
                return (w.read_json(dep), {'project_id': 'original'}, 'a' * 40)
            with w.request_validation_context(), m.source_phase(), \
                 patch.object(m, '_source_context', side_effect=source) as check, patch.object(m, 'publisher_live') as live:
                m.context(root, {'same': 'request', 'PUB_native': 'old'})
                extra = root / 'new-identity.json'; extra.write_text('{}'); w.read_json(extra)
                m.context(root, {'same': 'request', 'PUB_native': 'fresh'})
                self.assertEqual(check.call_count, 1); self.assertEqual(live.call_count, 2)
                dep.write_text('{"version":2}')
                with self.assertRaises(w.WorkflowError):
                    m.context(root, {'same': 'request', 'PUB_native': 'fresh'})

    def test_desktop_anchor_uses_real_id_and_completed_status_not_omitted_time(self):
        self.assertEqual(m.native_anchor({'items': [{'id': 'exec-real', 'type': 'commandExecution',
                                                    'status': 'completed', 'exitCode': 0}]}), 'exec-real')
        for item in ({'id': 'running', 'type': 'commandExecution', 'status': 'inProgress'},
                     {'id': 'failed', 'type': 'mcpToolCall', 'status': 'completed', 'error': {'message': 'x'}},
                     {'id': 'text', 'type': 'agentMessage', 'status': 'completed'}):
            with self.assertRaises(w.WorkflowError):
                m.native_anchor({'items': [item]})

    def test_static_source_reuse_never_caches_live_executor_identity(self):
        project = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(dir=project / 'logs') as directory:
            root = Path(directory); dep = root / 'source.json'; dep.write_text('{"version":1}')
            def source(*args):
                return (w.read_json(dep), {'project_id': 'original'}, 'a' * 40)
            with w.request_validation_context(), patch.object(m, '_source_context', side_effect=source) as check, \
                 patch.object(m, 'publisher_live') as live:
                m.context(root, {'same': 'request'}); m.context(root, {'same': 'request'})
                self.assertEqual(check.call_count, 1)
                self.assertEqual(live.call_count, 2)
                dep.write_text('{"version":2}')
                self.assertEqual(m.context(root, {'same': 'request'})[0]['version'], 2)
                self.assertEqual(check.call_count, 2)

    def test_transport_is_literal_zero_write_and_only_two_targets(self):
        for slug in m.SLUGS:
            argv = m.dispatch_argv(slug)
            self.assertIn('mode=dry-run', argv)
            self.assertIn('target=two-original-material-body-' + slug, argv)
            self.assertIn('managed_operation=publish', argv)
            self.assertNotIn('mode=publish', argv)
            self.assertFalse(any('permit' in value or '--execute' in value for value in argv))
        with self.assertRaises(w.WorkflowError):
            m.dispatch_argv('english-kitchen-en2-exact-v1')

    def test_policy_does_not_claim_other_routes_and_rejects_wrong_actor(self):
        self.assertIsNone(m.policy(Path('/unused'), {'action_id': 'ordinary'}))
        for department, action_class, consume in [('operations', 'site_ci_prepare', True),
                                                  ('publishing', 'cms_write', True),
                                                  ('publishing', 'site_ci_prepare', False)]:
            with self.assertRaises(w.WorkflowError):
                m.policy(Path('/unused'), {'task_id': m.TASK, 'action_id': m.action(m.SLUGS[0]),
                    'department': department, 'action_class': action_class, 'consume_approval': consume})

    def test_live_read_refuses_existing_run_busy_workflow_and_wrong_main(self):
        target = {'slug': m.SLUGS[0]}; sha = 'a' * 40
        answers = [{'id': 276684684}, {'object': {'sha': sha}},
                   {'path': m.WORKFLOW, 'state': 'active'}, {'total_count': 0, 'workflow_runs': []}]
        with patch.object(m, 'gh', side_effect=answers):
            self.assertEqual(m.live(target, sha)['prior_run_ids'], [])
        for change in ({'display_title': 'two-original-material-body-' + m.SLUGS[0] + ' | dry-run', 'status': 'completed'},
                       {'display_title': 'other', 'status': 'in_progress'}):
            with patch.object(m, 'gh', side_effect=answers[:3] + [{'total_count': 1, 'workflow_runs': [change]}]), self.assertRaises(w.WorkflowError):
                m.live(target, sha)
        with patch.object(m, 'gh', side_effect=[answers[0], {'object': {'sha': 'b' * 40}}, *answers[2:]]), self.assertRaises(w.WorkflowError):
            m.live(target, sha)

    def test_request_schema_cannot_supply_a_command_or_save_override(self):
        with self.assertRaises(w.WorkflowError):
            m.context(Path('/unused'), {'schema': m.SCHEMA, 'task_id': m.TASK,
                'slug': m.SLUGS[0], 'source_verification': {}, 'PUB_native': {}, 'mode': 'publish'})

    def test_existing_intent_and_allow_are_never_replayed(self):
        root = Path(__file__).resolve().parents[1]
        (root / 'logs').mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=root / 'logs') as temporary:
            root = Path(temporary)
            sha = self.write_request(root)
            target = {'scope': 'object'}; binding = {'project_id': 'project'}
            requested = {'task_id': m.TASK, 'action_id': m.action(m.SLUGS[0]),
                         'department': 'publishing', 'action_class': 'site_ci_prepare',
                         'consume_approval': True, 'scope': 'object', 'source_project_id': 'project',
                         'payload_sha256': sha}
            with patch.object(m, 'context', return_value=(target, binding, 'a' * 40)), \
                 patch.object(m.w, 'read_jsonl', return_value=[{'status': 'allow'}]), \
                 patch.object(m, 'live') as live, self.assertRaises(w.WorkflowError):
                m.policy(root, requested)
            live.assert_not_called()

    def test_only_exact_own_policy_append_is_reconciled_in_outer_request(self):
        project = Path(__file__).resolve().parents[1]
        (project / 'logs').mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=project / 'logs') as temporary:
            root = Path(temporary); sha = self.write_request(root)
            requested = {'task_id': m.TASK, 'action_id': m.action(m.SLUGS[0]),
                         'department': 'publishing', 'action_class': 'site_ci_prepare',
                         'consume_approval': True, 'scope': 'object', 'source_project_id': 'project',
                         'payload_sha256': sha}
            with w.request_validation_context() as validation, \
                 patch.object(m, 'context', return_value=({'scope': 'object'}, {'project_id': 'project'}, 'a' * 40)), \
                 patch.object(m, 'live', return_value={'observed_at': 'actual'}):
                row, _ = m.policy(root, requested)
                self.assertTrue(row['consume_approval'])
                self.assertFalse(row['Save_allowed'])
                validation.recheck()
                with self.assertRaises(w.WorkflowError):
                    m.policy(root, requested)
            self.assertEqual(len(w.read_jsonl(root / w.POLICY_DECISIONS)), 1)


if __name__ == '__main__':
    unittest.main()
