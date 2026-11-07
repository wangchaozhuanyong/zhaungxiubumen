import unittest
from pathlib import Path
from unittest.mock import patch, Mock
from contextlib import ExitStack, nullcontext
import datetime as dt
import tempfile

import material_edge_live as live
import professional_web_execution as web
import r3_platform_binding_transport as carrier
import workflow_control as w


class MaterialEdgeLiveTests(unittest.TestCase):
    def test_current_material_preview_backup_binds_the_declared_id_or_slug_key(self):
        from paid_three_page_bounded_cms import _material_preview_backup_identity as valid

        target = {'record_id': 'original-record', 'slug': 'original-slug'}
        backup = {'table': 'materials', 'keyField': 'id', 'key': 'original-record',
                  'record': {'id': 'original-record'}}
        self.assertTrue(valid(backup, target, True))
        self.assertFalse(valid(backup, target, False))
        for changes in ({'key': 'original-slug'}, {'key': 'another-record'},
                        {'record': {'id': 'another-record'}}, {'keyField': 'other'}, {'table': 'services'}):
            self.assertFalse(valid({**backup, **changes}, target, True))
        legacy = {'table': 'materials', 'key': 'original-slug'}
        self.assertTrue(valid(legacy, target, False))
        self.assertTrue(valid({**legacy, 'keyField': 'slug'}, target, True))

    def test_current_material_preview_run_name_is_only_its_own_successful_first_preview(self):
        from paid_three_page_bounded_cms import _material_preview_run_identity as valid

        target = {'slug': 'sintered-stone-grey'}
        run = {'name': 'two-original-material-body-sintered-stone-grey | dry-run',
               'status': 'completed', 'run_attempt': 1}
        self.assertTrue(valid(run, target, True))
        self.assertFalse(valid(run, target, False))
        for changes in ({'name': 'two-original-material-body-solid-surface-warm-white | dry-run'},
                        {'name': 'two-original-material-body-sintered-stone-grey | publish'},
                        {'status': 'in_progress'}, {'run_attempt': 2}):
            self.assertFalse(valid({**run, **changes}, target, True))
        self.assertTrue(valid({'name': 'Approved website content publish'}, target, False))

    def test_only_bound_current_web_source_can_read_redundant_deployment_sha(self):
        import paid_three_page_bounded_cms as cms

        source = {'schema': cms.MATERIAL_CURRENT_PROOF, 'task_id': cms.MATERIAL_PUBLICATION_TASK,
                  'source_issuer': 'designated-development', 'registration_grants_CMS_write_authority': False}
        deployed = {'schema': 'original-materials-actual-WEB-deployment/v2',
                    'task_id': cms.MATERIAL_PUBLICATION_TASK, 'production_website_sha': 'a' * 40}
        self.assertEqual(cms._material_source_production_sha(source, deployed), 'a' * 40)
        self.assertNotIn('production_sha', source)
        self.assertEqual(cms._material_source_production_sha({**source, 'production_sha': 'b' * 40}, deployed), 'b' * 40)
        self.assertIsNone(cms._material_source_production_sha({**source, 'production_sha': None}, deployed))
        for changed in ({'schema': 'two-original-material-protected-source/v1'},
                        {'source_issuer': 'operations'}, {'registration_grants_CMS_write_authority': True}):
            self.assertIsNone(cms._material_source_production_sha({**source, **changed}, deployed))
        self.assertIsNone(cms._material_source_production_sha(source, {**deployed, 'task_id': 'other'}))

    def test_direct_material_target_reader_owns_and_reuses_bounded_request_context(self):
        import paid_three_page_bounded_cms as cms

        project = Path(__file__).resolve().parents[1]
        (project / 'logs').mkdir(exist_ok=True)
        seen = []
        def source(root):
            context = w._VALIDATION_CONTEXT.get()
            self.assertIsNotNone(context)
            seen.append(context)
            return {}
        with tempfile.TemporaryDirectory(dir=project / 'logs') as directory, \
             patch.object(cms, 'two_original_material_source_contract', side_effect=source):
            self.assertEqual(cms.two_original_material_targets(Path(directory)), {})
            self.assertIsNone(w._VALIDATION_CONTEXT.get())
            with w.request_validation_context() as outer:
                cms.two_original_material_targets(Path(directory))
                self.assertIs(seen[-1], outer)

    def test_current_runtime_accepts_only_actual_shared_javascript_dependencies(self):
        from paid_three_page_bounded_cms import _material_runtime_path

        for path in ('_shared/content-links.mjs', '_shared/material-terminology.mjs'):
            self.assertTrue(_material_runtime_path(path, True))
            self.assertFalse(_material_runtime_path(path, False))
        self.assertTrue(_material_runtime_path('content-publish/index.ts', False))
        for path in ('_shared/other.mjs', 'content-publish/content-links.mjs',
                     '../_shared/content-links.mjs', '_shared/../content-links.mjs', None):
            self.assertFalse(_material_runtime_path(path, True))

    def test_live_provider_refresh_never_extends_binding_or_reissues_consumed_reference(self):
        root = Path.cwd()
        pin = {'path': 'preflight', 'sha256': 'a' * 64, 'size': 1}
        request_pin = {'path': 'request'}
        request = {'task_id': live.TASK, 'action_id': 'edge', 'action_class': 'site_publish',
                   'scope': 'exact', 'operation': 'edge_deploy', 'department': 'designated-development',
                   'observed_at': '2000-01-01T00:00:00+00:00',
                   'state': {'candidate_commit': 'c' * 40, 'main_sha': 'a' * 40, 'r3_run': {'id': 123}}}
        ctx = {'task': live.TASK, 'role': 'designated-development', 'material_registry_test_successor': True,
               'authorization': {'path': 'human'}, 'decision': {'path': 'decision'},
               'edge_scope': 'exact', 'repository': 'owner/repo'}
        item = {'request': request_pin}
        documents = {'preflight': item, 'request': request,
                     'human': {'source_thread_id': 'hq', 'message': {'id': 'grant'}}}
        arguments = dict(task_id=live.TASK, action_id='edge', action_class='site_publish', scope='exact',
                         source_evidence='preflight', source_thread_id='hq', source_message_ref='grant')
        with ExitStack() as stack:
            stack.enter_context(patch.object(web.w, 'file_digest', return_value=pin))
            stack.enter_context(patch.object(web.a, 'document', side_effect=lambda root, pin: documents[pin['path']]))
            stack.enter_context(patch.object(web, 'preflight', return_value=(item, request, pin, ctx)))
            stack.enter_context(patch.object(web, 'reference', return_value='apr-' + 'b' * 20))
            stack.enter_context(patch.object(web.w, 'workflow_lock', return_value=nullcontext()))
            approvals = stack.enter_context(patch.object(web.w, 'effective_approvals', return_value={}))
            append = stack.enter_context(patch.object(web.w, 'append_jsonl_locked'))
            refresh = stack.enter_context(patch.object(live, 'pending', return_value={
                'observed_at': dt.datetime.now(dt.timezone.utc).isoformat(), 'external_permission_issued': False}))
            result, _ = web.record_approval(root, **arguments)
            binding = result['platform_binding']
            self.assertEqual((w._parse_observed_at(binding['expiresAt']) -
                              w._parse_observed_at(binding['issuedAt'])).total_seconds(), 900)
            self.assertTrue(binding['singleUse'])
            self.assertEqual(request['observed_at'], '2000-01-01T00:00:00+00:00')
            approvals.return_value = {result['approval_id']: {**result, 'status': 'consumed'}}
            with self.assertRaises(w.WorkflowError):
                web.record_approval(root, **arguments)
            self.assertEqual(append.call_count, 1)
            ctx['material_registry_test_successor'] = False
            with self.assertRaises(w.WorkflowError):
                web.record_approval(root, **arguments)
            self.assertEqual(refresh.call_count, 2)

    def test_live_check_requires_actual_dispatch_and_unique_pending_run(self):
        root = Path.cwd()
        ctx = {'material_registry_test_successor': True, 'task': live.TASK,
               'role': 'designated-development', 'edge_scope': 'exact', 'commit': 'c' * 40,
               'worktree': str(root), 'decision': {'path': 'original'}, 'repository': 'owner/repo', 'paths': ['material']}
        state = {'main_sha': 'a' * 40, 'r3_run': {'id': 123}, 'actor': {'id': 5, 'login': 'owner'}}
        request = {'task_id': live.TASK, 'department': ctx['role'], 'operation': 'edge_deploy',
                   'action_class': 'site_publish', 'scope': 'exact', 'action_id': 'edge_deploy',
                   'state': state, 'desired': {'approval_id': 'original'}}
        row = {'consume_approval': True, 'original_professional_source': ctx['decision'],
               'external_execution_department': ctx['role'], 'decision_id': 'policy', 'exact_request': {'path': 'dispatch'}}
        original = {'operation': 'r3_dispatch', 'state': state,
                    'desired': {'approval_id': 'original', 'release_action_id': request['action_id']}}
        api = Mock()
        api.call.return_value = {'status': 'completed', 'conclusion': 'cancelled'}
        with patch.object(web, 'action_id', side_effect=lambda ctx, op, head, main: op), \
             patch.object(live.w, 'read_jsonl', return_value=[row]) as ledger, \
             patch.object(live.a, 'document', return_value=original), \
             patch.object(carrier, 'GitHub', return_value=api), \
             patch.object(carrier, 'platform_facts', return_value={'run_id': 123}), \
             patch.object(web, '_material_github_read', return_value={'total_count': 1, 'workflow_runs': [{'id': 123}]}) as runs, \
             patch.object(web, 'working_source'), patch.object(web, 'git', return_value=b''):
            result = live.pending(root, ctx, request)
            self.assertFalse(result['external_permission_issued'])
            self.assertFalse(result['source_request_timestamp_changed'])
            self.assertTrue(all(call.args[0] == 'GET' for call in api.call.call_args_list))
            runs.return_value = {'total_count': 2, 'workflow_runs': [{'id': 123}, {'id': 456}]}
            with self.assertRaises(w.WorkflowError):
                live.pending(root, ctx, request)
            ledger.return_value = []
            with self.assertRaises(w.WorkflowError):
                live.pending(root, ctx, request)


if __name__ == '__main__':
    unittest.main()
