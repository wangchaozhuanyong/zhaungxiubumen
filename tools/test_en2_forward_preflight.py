"""Isolated local fixtures only. No fixture is a native business receipt."""
import copy
import datetime as dt
import importlib.util
import json
import pathlib
import tempfile
import threading
import sys
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import workflow_control as w
import department_autonomy as a
REAL_NATIVE_EXECUTION = a.native_execution

PROJECT = pathlib.Path(__file__).resolve().parents[1]
import professional_cms_execution as m


class ForwardPreflight(unittest.TestCase):
    def setUp(self):
        (PROJECT / 'backups').mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix='en2-test-fixture-', dir=PROJECT / 'backups')
        self.root = pathlib.Path(self.temp.name)
        # Synthetic values with the verified existing 41-column shape.
        self.row = dict.fromkeys(['alt_en', 'alt_ms', 'alt_zh', 'common_projects_en', 'common_projects_ms', 'common_projects_zh', 'content_en', 'content_ms', 'content_zh', 'created_at', 'excerpt_en', 'excerpt_ms', 'excerpt_zh', 'faqs_en', 'faqs_ms', 'faqs_zh', 'id', 'image_url', 'process_steps_en', 'process_steps_ms', 'process_steps_zh', 'scope_items_en', 'scope_items_ms', 'scope_items_zh', 'seo_description_en', 'seo_description_ms', 'seo_description_zh', 'seo_title_en', 'seo_title_ms', 'seo_title_zh', 'slug', 'sort_order', 'status', 'suitable_for_en', 'suitable_for_ms', 'suitable_for_zh', 'title_en', 'title_ms', 'title_zh', 'updated_at', 'version'])
        self.row.update(id='ce4156db-9034-42c8-ba29-b35724ea7d6d', slug='kitchen',
                        version=1, updated_at='2026-10-19T13:39:00.867332+00:00',
                        status='published', title_en='Old title', excerpt_en='Old excerpt')
        self.fields = ['title_en', 'excerpt_en']
        self.desired = {'title_en': 'Isolated test title', 'excerpt_en': 'Isolated test excerpt'}
        retained = sorted(set(self.row) - set(self.fields) - {'updated_at', 'version'})
        self.physical = 'company.example:services:' + self.row['id'] + ':title_en,excerpt_en'
        self.target = {'id': self.row['id'], 'slug': 'kitchen', 'table': 'services',
            'taskId': m._EN2_FORWARD_TASK, 'actionId': 'save-kitchen-english-two-fields-v1',
            'candidateVersion': 'publishing-english-kitchen-en2-actual-publication-v1-20261011',
            'scope': self.physical, 'changedFields': self.fields,
            'baselineProjectionFields': sorted(self.row), 'baselineFieldsSha256': w.sha256_value(self.row),
            'retainedProjectionFields': retained,
            'retainedFieldsSha256': w.sha256_value({k: self.row[k] for k in retained}),
            'desiredFieldsSha256': w.sha256_value(self.desired), 'rollbackAllowed': False}
        self.registration = self.save('source.json', {'fixture': 'not production authority'})
        t = self.target
        tup = {'task_id': m._EN2_FORWARD_TASK, 'action_id': t['actionId'],
            'candidate_version': t['candidateVersion'], 'record_id': t['id'], 'slug': t['slug'],
            'table': t['table'], 'changed_fields': self.fields, 'execution_owner': 'publishing',
            'execution_thread_id': 'original-test-PUB', 'business_scope': 'cms:services:kitchen:english-two-fields:publication:v1',
            'physical_scope': self.physical, 'full_fields': 41, 'protect_fields': 37,
            'MS_fields': 11, 'rollback_allowed': False}
        self.source = {'task': m._EN2_FORWARD_TASK, 'owner': 'publishing',
            'event_id': m._EN2_SOURCE_EVENT, 'protected_body_source_custody': True,
            'registration': self.registration, 'scope': tup['business_scope'],
            'original_PUB_tuples': {m._EN2_NAMESPACE: tup},
            'registered_protected_body_targets': {m._EN2_NAMESPACE: self.target}}
        self.snapshot = {'task_id': m._EN2_FORWARD_TASK, 'current_state': 'evidence_received'}
        self.binding = {'task_id': 'original-test-PUB', 'title': 'fixture PUB', 'project_id': a.PROJECT, 'cwd': str(self.root)}
        self.native = {}
        self.patches = [patch('professional_cms_channel.original_body_records', side_effect=lambda *args: [copy.deepcopy(self.source)]),
            patch.object(w, 'department_registry', return_value={'publishing': {'chat_binding': self.binding}}),
            patch.object(a, 'native_execution', side_effect=self.native_execution)]
        for p in self.patches: p.start()
        self.addCleanup(lambda: [p.stop() for p in reversed(self.patches)])
        self.addCleanup(self.temp.cleanup)

    def save(self, name, obj):
        p = self.root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(obj, ensure_ascii=False) + '\n')
        return w.file_digest(self.root, name)

    def witness(self, name, value):
        self.native[name] = copy.deepcopy(value)
        return {'actual_native': self.save(name + '-native.json', {'fixture': True}), 'command_id': name}

    def native_execution(self, root, pin, command, role):
        if role != 'publishing' or command not in self.native:
            raise w.WorkflowError('no native fixture')
        now = dt.datetime.now(dt.timezone.utc).timestamp()
        return {'startedAt': now - 1000, 'completedAt': now + 1}, {'id': command}, json.dumps(self.native[command])

    def request(self, mutate=None):
        t = self.target
        req = {'task_id': m._EN2_FORWARD_TASK, 'department': 'publishing', 'sender_department': 'publishing',
            'action_id': t['actionId'], 'action_class': 'cms_write', 'scope': self.source['scope'],
            'source_project_id': a.PROJECT, 'operation': 'field_patch', 'business_scope': self.source['scope'],
            'physical_scope': self.physical, 'table': 'services', 'slug': 'kitchen', 'object_ids': [t['id']],
            'changed_fields': self.fields, 'candidate_version': t['candidateVersion'],
            'professional_execution_source': self.registration, 'desired': self.desired,
            'before': self.save('before.json', self.row), 'expected_updated_at': self.row['updated_at'],
            'expected_version': self.row['version']}
        if mutate: mutate(req)
        intent = w.sha256_value(req)
        identity = {k: req[k] for k in ('task_id', 'department', 'action_id', 'action_class', 'scope')}
        observed = dt.datetime.now(dt.timezone.utc).isoformat()
        preview_request = {'contentType': 'service', 'mode': 'dry-run', 'record': {**self.row, **self.desired},
            'nextStatus': 'published', 'expectedUpdatedAt': self.row['updated_at'], 'managedCandidate': {
                'taskId': m._EN2_FORWARD_TASK, 'actionId': t['actionId'], 'operation': 'publish',
                'scope': self.physical, 'candidateVersion': t['candidateVersion']}}
        response = {'ok': True, 'dry_run': True, 'performed_write': False, 'content_type': 'service',
            'action': 'update', 'slug': 'kitchen', 'existing_id': t['id'], 'status': 'published',
            'payload_preview': self.desired}
        preview = {'request': preview_request, 'response': response,
            'url': 'https://exampleproject000000.supabase.co/functions/v1/content-publish', 'http_status': 200}
        preview.update(self.witness('preview', preview))
        effects = {'lookup_scope': {'task_id': m._EN2_FORWARD_TASK, 'action_id': t['actionId'],
            'candidate_version': t['candidateVersion'], 'record_id': t['id'], 'scope': self.physical},
            'rows': [], 'unknown_effect': False, 'same_row_conflict': False}
        effects.update(self.witness('effects', effects))
        facts = {**identity, 'intent_sha256': intent, 'current_row': req['before'], 'observed_at': observed,
            'protected_preview': self.save('preview.json', preview),
            'original_key_effect_lookup': self.save('effects.json', effects)}
        facts.update(self.witness('facts', facts))
        check = {**identity, 'intent_sha256': intent, 'status': 'PASS', 'production_write_allowed': False}
        check.update(self.witness('check', check))
        req.update(facts=self.save('facts.json', facts), self_check=self.save('check.json', check),
            backup=self.save('backup.json', {**identity, 'intent_sha256': intent, 'complete_row': req['before']}))
        return req

    def validate(self, req):
        return m._request(self.root, self.snapshot, self.save('request.json', req))

    def repin(self, req, field, mutate):
        p = self.root / req[field]['path']; value = json.loads(p.read_text()); mutate(value)
        req[field] = self.save(req[field]['path'], value)

    def test_valid_forward_not_authority(self):
        out = self.validate(self.request())
        self.assertTrue(out['preflight_only']); self.assertTrue(out['source_only'])
        self.assertEqual(out['external_origin_state'], 'NOT_VERIFIED')
        self.assertFalse(out['actual_action_allowed']); self.assertFalse(out['production_READY'])
        with self.assertRaises(w.WorkflowError): m.execution_context(self.root, self.snapshot, {})

    def test_wrong_identity_and_scope(self):
        for key, value in [('task_id', 'other'), ('department', 'operations-assistant-2'),
            ('target_department', 'content-organic-website'), ('candidate_version', 'other'),
            ('action_id', 'other'), ('physical_scope', 'other'), ('operation', 'field_patch_rollback')]:
            with self.subTest(key=key), self.assertRaises(w.WorkflowError):
                self.validate(self.request(lambda r: r.update({key: value})))

    def test_paused_and_terminal_and_old_source(self):
        req = self.request()
        for state in ('paused', 'suspended', 'closed', 'cancelled', 'failed'):
            self.snapshot['current_state'] = state
            with self.subTest(state=state), self.assertRaises(w.WorkflowError): self.validate(req)
        self.snapshot['current_state'] = 'evidence_received'; self.source['event_id'] = 'unregistered'
        with self.assertRaises(w.WorkflowError): self.validate(req)

    def test_old30_and_missing_ms_and_tampered_row(self):
        for mutate in (lambda row: row.pop('title_ms'),
                       lambda row: [row.pop(k) for k in list(row) if k.endswith('_ms')],
                       lambda row: row.update(content_zh='changed protected field')):
            req = self.request(); self.repin(req, 'before', mutate)
            with self.assertRaises(w.WorkflowError): self.validate(req)

    def test_missing_preview_and_missing_native(self):
        req = self.request(); self.repin(req, 'facts', lambda d: d.pop('protected_preview'))
        with self.assertRaisesRegex(w.WorkflowError, 'missing original PUB protected_preview'): self.validate(req)
        req = self.request(); self.repin(req, 'self_check', lambda d: d.pop('actual_native'))
        with self.assertRaises(w.WorkflowError): self.validate(req)

    def test_hosted_publish_dry_run_response_shape(self):
        for action in ('publish', 'delete'):
            req = self.request()
            facts = w.read_json(self.root / req['facts']['path'])
            preview = w.read_json(self.root / facts['protected_preview']['path'])
            preview['response'].update(action=action)
            preview['response'].pop('performed_write')
            self.native['preview']['response'] = copy.deepcopy(preview['response'])
            facts['protected_preview'] = self.save('preview.json', preview)
            self.native['facts']['protected_preview'] = facts['protected_preview']
            req['facts'] = self.save('facts.json', facts)
            if action == 'publish':
                self.assertTrue(self.validate(req)['preflight_only'])
            else:
                with self.assertRaisesRegex(w.WorkflowError, 'dry-run'):
                    self.validate(req)

    def test_expired_and_future_observation(self):
        for seconds in (-301, 30):
            req = self.request()
            self.repin(req, 'facts', lambda d: d.update(observed_at=(dt.datetime.now(dt.timezone.utc)
                + dt.timedelta(seconds=seconds)).isoformat()))
            with self.subTest(seconds=seconds), self.assertRaisesRegex(w.WorkflowError, 'expired or future'): self.validate(req)

    def test_bad_sha_and_native_output(self):
        req = self.request(); (self.root / req['facts']['path']).write_text('{}')
        with self.assertRaises(w.WorkflowError): self.validate(req)
        req = self.request(); self.native['preview']['response']['performed_write'] = True
        with self.assertRaisesRegex(w.WorkflowError, 'native output'): self.validate(req)

    def test_unknown_effect_and_changed_preview(self):
        req = self.request(); facts = json.loads((self.root / req['facts']['path']).read_text())
        effects = json.loads((self.root / facts['original_key_effect_lookup']['path']).read_text())
        effects['unknown_effect'] = True
        facts['original_key_effect_lookup'] = self.save('effects.json', effects)
        req['facts'] = self.save('facts.json', facts)
        with self.assertRaisesRegex(w.WorkflowError, 'UNKNOWN'): self.validate(req)
        req = self.request(); facts = json.loads((self.root / req['facts']['path']).read_text())
        preview = json.loads((self.root / facts['protected_preview']['path']).read_text())
        preview['request']['mode'] = 'publish'
        facts['protected_preview'] = self.save('preview.json', preview); req['facts'] = self.save('facts.json', facts)
        with self.assertRaisesRegex(w.WorkflowError, 'dry-run'): self.validate(req)

    def test_native_wrong_receiver_real_guard(self):
        with patch.object(a, 'native_execution', wraps=REAL_NATIVE_EXECUTION), \
             patch('goal_delivery_runtime._native_document', return_value={'thread': {
                 'id': 'other-receiver', 'title': 'fixture PUB', 'cwd': str(self.root)}}):
            with self.assertRaisesRegex(w.WorkflowError, 'executor/project/directory'):
                m._en2_native_json(self.root, {'actual_native': self.registration, 'command_id': 'x'})

    def test_status_exposes_only_original_source_not_execution(self):
        with patch('goal_delivery_runtime.restore_goal', return_value=self.snapshot):
            status = m.status(self.root, m._EN2_FORWARD_TASK)
        self.assertTrue(status['forward_preflight_validator_available'])
        self.assertTrue(status['structural_validator_available'])
        self.assertTrue(status['issuer_binding_implemented'])
        expected_state = ('requires_live_preflight_revalidation' if getattr(self, 'events', [])
                          else 'waiting_for_original_publisher_preflight')
        self.assertEqual(status['issuer_binding_state'], expected_state)
        self.assertEqual(status['pending_issuer_owner'], 'publishing')
        self.assertFalse(status['execution_binding_available'])
        self.assertFalse(status['production_READY'])
        self.assertFalse(status['actual_action_allowed'])
        self.assertEqual(status['source_event_id'], m._EN2_SOURCE_EVENT)

    def test_other_old_task_cannot_borrow_en2_route(self):
        other = {'task_id': 'fc-unrelated-old-task', 'current_state': 'evidence_received'}
        req = self.request()
        with patch.object(m, 'match', return_value=None) as original_match:
            with self.assertRaisesRegex(w.WorkflowError, 'registered CMS source required'):
                m._request(self.root, other, self.save('other-task-request.json', req))
            original_match.assert_called_once()

    def trusted_origin_fixture(self, *args, **kwargs):
        # Test the journal protocol independently of the unimplemented remote
        # origin consumer. This stub never runs outside an isolated test root.
        result = self.real_forward_validator(*args, **kwargs)
        return {**result, 'external_origin_state': 'VERIFIED_PROTECTED_PROVIDER_RECEIPTS'}

    def test_self_printed_json_cannot_register_preflight(self):
        import goal_delivery_runtime as g
        for forged_label in (False, True):
            req = self.request(lambda r: r.update(external_origin_state='VERIFIED_PROTECTED_PROVIDER_RECEIPTS')
                               if forged_label else None)
            pin = self.save('request.json', req)
            envelope = self.save('envelope.json', {'schema': 'professional-cms-fresh-preflight/v1',
                'task_id': m._EN2_FORWARD_TASK, 'request': pin})
            old_unverified = {'task_id': m._EN2_FORWARD_TASK, 'details': {'professional_cms_preflight': {
                'action_id': req['action_id'], 'request': pin, 'preflight_only': True,
                'source_event_id': m._EN2_SOURCE_EVENT, 'external_origin_state': 'NOT_VERIFIED'}}}
            with self.subTest(forged_label=forged_label), \
                 patch.object(g, 'restore_goal', return_value=self.snapshot), \
                 patch.object(w, 'read_jsonl', return_value=[old_unverified]), \
                 patch.object(w, 'append_workflow_event') as append:
                with self.assertRaisesRegex(w.WorkflowError, 'command-printed JSON cannot register'):
                    m.record_preflight(self.root, m._EN2_FORWARD_TASK, envelope['path'])
                append.assert_not_called()

    def test_normal_runtime_route_and_uncertain_retry(self):
        import goal_delivery_runtime as g
        req = self.request(); pin = self.save('request.json', req)
        envelope = self.save('envelope.json', {'schema': 'professional-cms-fresh-preflight/v1',
            'task_id': m._EN2_FORWARD_TASK, 'request': pin})
        events = []
        def append(root, task, state, details): events.append({'task_id': task, 'details': copy.deepcopy(details)})
        self.real_forward_validator = m._en2_forward_request
        with patch.object(m, '_en2_forward_request', side_effect=self.trusted_origin_fixture), \
             patch.dict(sys.modules, {'professional_cms_execution': m}), \
             patch.object(g, 'restore_goal', return_value=self.snapshot), \
             patch.object(w, 'read_jsonl', side_effect=lambda *args, **kwargs: copy.deepcopy(events)), \
             patch.object(w, 'append_workflow_event', side_effect=append):
            self.assertEqual(g.record_preflight(self.root, m._EN2_FORWARD_TASK, envelope['path'])['result'], 'recorded')
            # Simulate lost acknowledgement/elapsed freshness without changing
            # the frozen request. A retry may recover the receipt, never act.
            with patch.object(m, '_en2_forward_request', side_effect=AssertionError('must read original receipt first')):
                result = g.record_preflight(self.root, m._EN2_FORWARD_TASK, envelope['path'])
            self.assertEqual(result['result'], 'duplicate_ignored')
            self.assertFalse(result['replay_authorized'])
            self.assertTrue(result['requires_fresh_validation_for_execution'])
            self.assertEqual(len(events), 1)

    def test_duplicate_and_concurrent_journal(self):
        req = self.request(); pin = self.save('request.json', req)
        envelope = self.save('envelope.json', {'schema': 'professional-cms-fresh-preflight/v1',
            'task_id': m._EN2_FORWARD_TASK, 'request': pin})
        events = []; guard = threading.Lock()
        def append(root, task, state, details):
            with guard: events.append({'task_id': task, 'details': copy.deepcopy(details)})
        def rows(*args, **kwargs): return copy.deepcopy(events)
        self.real_forward_validator = m._en2_forward_request
        with patch.object(m, '_en2_forward_request', side_effect=self.trusted_origin_fixture), \
             patch('goal_delivery_runtime.restore_goal', return_value=self.snapshot), \
             patch.object(w, 'read_jsonl', side_effect=rows), \
             patch.object(w, 'append_workflow_event', side_effect=append):
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(lambda _: m.record_preflight(self.root, m._EN2_FORWARD_TASK,
                    envelope['path']), range(2)))
        self.assertEqual(len(events), 1)
        self.assertEqual(sorted(r['result'] for r in results), ['duplicate_ignored', 'recorded'])
        self.assertTrue(all(r['actual_action_allowed'] is False for r in results))


if __name__ == '__main__': unittest.main(verbosity=2)
