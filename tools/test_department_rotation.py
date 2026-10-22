"""Isolated native/registry fixtures; no real messaging or provider writes."""
import copy
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import unittest
from unittest import mock
import department_rotation as rotation
import goal_continuity as continuity
import goal_source_recovery as recovery
import goal_delivery_runtime as runtime
import result_coordination as coordination
import workflow_control as w
import test_goal_continuity as continuity_fixture
import test_goal_runtime_consumers as fixture
import test_goal_source_recovery as recovery_fixture
import test_assistant_responsibility_resume as responsibility_fixture

_here = Path(__file__).resolve()
_delivery = (_here.parent.parent if _here.parent.name == 'source'
             else _here.parents[1] / rotation.OUTPUT)
fixture.TMP = _delivery / 'checks/test-tmp'
responsibility_fixture.TMP = fixture.TMP


class RotationTests(unittest.TestCase):
    def setUp(self):
        self.base = continuity_fixture.ContinuityTests('runTest')
        self.base.setUp(); self.addCleanup(self.base.doCleanups)
        self.root = self.base.root

    def write(self, path, document):
        w.atomic_write_json(self.root / path, document)
        return w.file_digest(self.root, path)

    def prepare(self, roles, *, active=None, bad_project=False, empty_reply=False):
        registry = w.department_registry(self.root)
        entries, threads, keys = [], [], []
        for role in roles:
            old = registry[role]['chat_binding']
            new_id = 'new-' + role
            entries.append({'role': role, 'old_binding': old, 'new_thread_id': new_id})
            self.write(rotation.BASE + '/' + role + '/HANDOFF.json', {'role': role, 'old_binding': old})
            native = {'thread': {'id': new_id, 'title': 'new ' + old['title'], 'cwd': old['cwd']},
                'turns': [{'id': 'handoff', 'status': 'completed', 'items': [{
                    'type': 'agentMessage', 'phase': 'final_answer', 'id': 'new-final',
                    'text': '' if empty_reply else 'Read original handoff; awaiting adoption.'}]}]}
            self.write(rotation.BASE + '/' + role + '/new-handoff-native-readback.json', native)
            self.write(rotation.OUTPUT + '/native/old-' + role + '.json', {
                'observed_at': dt.datetime.now(dt.timezone.utc).isoformat(),
                'thread': {'id': old['task_id'], 'title': old['title'], 'cwd': old['cwd'],
                           'status': {'type': 'active' if role == active else 'idle'}},
                'turns': [{'status': 'inProgress' if role == active else 'completed'}]})
            threads.append({'id': new_id, 'title': native['thread']['title'], 'cwd': old['cwd'],
                            'projectId': 'wrong-project' if bad_project else old['project_id']})
            keys.append('codex:thread:local:' + new_id)
        self.write(rotation.BASE + '/rotation-manifest.json', {
            'schema': 'flashcast-clean-window-rotation/v1', 'owner_request': 'fixture owner requested rotation',
            'records': entries})
        self.write(rotation.OUTPUT + '/native/thread-inventory.json', {
            'threads': threads, 'sections': [{'sectionId': 'fixture-group', 'itemKeys': keys}]})
        return rotation.prepare(self.root, rotation.BASE + '/rotation-manifest.json',
                                rotation.OUTPUT + '/native/thread-inventory.json')

    def apply(self):
        return rotation.apply(self.root, rotation.OUTPUT + '/plan.json', dry_run=False)

    def assignment(self):
        item, pin = self.base.assignment()
        continuity.record_assignment(self.root, item, pin)
        return item, pin

    def queued_original(self):
        item, pin = self.assignment()
        _, outbox = self.base.t.producer_result()
        identity = {'task_id': item['task_id'], 'sender_department': fixture.PRODUCER,
                    'candidate_version': 'v1', 'result_sha256': outbox['sha256']}
        native = self.base.t.completed_result_fields()
        request = {**identity, **native, 'event': 'notification_queued',
                   'idempotency_key': 'original-native-final', 'outbox_path': outbox['path']}
        w.record_result_handoff(self.root, request)
        return item, pin, identity, request

    def receive_original(self, identity, queued, *, next_owner=fixture.PRODUCER, decision='rework'):
        store = coordination.CoordinationStore(self.root); self.addCleanup(store.close)
        role = fixture.ASSISTANT
        owner = w.department_registry(self.root)[role]['chat_binding']['task_id']
        claim = store.claim(identity, role, owner, 'new-window-intake')
        request = {**identity, 'event': 'controller_received', 'idempotency_key': 'native-received-after-rotation',
            'outbox_path': queued['outbox_path'], 'intake_mode': 'queue',
            'source_reply_sha256': queued['source_reply_sha256'], 'source_thread_id': queued['source_thread_id'],
            'reply_observed_at': dt.datetime.now(dt.timezone.utc).isoformat(),
            'coordinator_role': role, 'coordinator_owner': owner, 'coordination_claim': claim}
        received, _ = w.record_result_handoff(self.root, request)
        replay, _ = w.record_result_handoff(self.root, request)
        self.assertEqual(replay['record_id'], received['record_id'])
        self.assertEqual(replay['result'], 'duplicate_ignored')
        proof = self.write('reports/native-rework-evidence.json', {'fixture_only': True, 'requires': 'bounded rework'})
        decision_request = {**request, 'event': 'controller_decision', 'idempotency_key': 'native-rework-after-rotation',
            'decision': decision, 'next_owner': next_owner, 'next_action': 'Resume exact original changed batch',
            'evidence_paths': [proof['path']]}
        decision, _ = w.record_result_handoff(self.root, decision_request)
        self.assertEqual(w.record_result_handoff(self.root, decision_request)[0]['record_id'], decision['record_id'])
        return received, decision

    def test_old_frozen_result_real_native_receive_and_decision_after_cutover(self):
        item, _, identity, queued = self.queued_original()
        old_outbox = (self.root / queued['outbox_path']).read_bytes()
        old_receipts = w.receipts_path(self.root, item['task_id']).read_bytes()
        self.prepare((fixture.PRODUCER, fixture.ASSISTANT)); self.apply()
        received, decision = self.receive_original(identity, queued)
        self.assertEqual(received['source_thread_id'], 'fixed-' + fixture.PRODUCER)
        self.assertEqual(received['coordinator_owner'], 'new-' + fixture.ASSISTANT)
        self.assertEqual(decision['decision'], 'rework')
        self.assertEqual((self.root / queued['outbox_path']).read_bytes(), old_outbox)
        self.assertEqual(w.receipts_path(self.root, item['task_id']).read_bytes(), old_receipts)

    def queued_ready_original(self):
        item, pin = self.assignment()
        _, outbox = self.base.t.producer_result()
        identity = {'task_id': item['task_id'], 'sender_department': fixture.PRODUCER,
                    'candidate_version': 'v1', 'result_sha256': outbox['sha256']}
        declaration = {**identity, 'outbox_path': outbox['path'], 'batch_complete': True}
        text = 'Frozen original whole batch.\n' + continuity.READY_MARKER + json.dumps(declaration) + '\n'
        visible = self.root / 'reports/old-ready.txt'; visible.write_bytes(text.encode('utf-8'))
        binding = w.department_registry(self.root)[fixture.PRODUCER]['chat_binding']
        native = {'thread': {'id': binding['task_id'], 'title': binding['title'], 'cwd': binding['cwd']},
            'turns': [{'id': 'old-ready-turn', 'status': 'inProgress', 'error': None,
                       'startedAt': dt.datetime.now(dt.timezone.utc).timestamp() - 1,
                       'items': [{'id': 'old-ready-message', 'type': 'agentMessage',
                                  'phase': 'commentary', 'text': text}]}]}
        native_pin = self.write('reports/old-ready-native.json', native)
        request = {**identity, 'event': 'notification_queued', 'idempotency_key': 'original-ready-once',
            'outbox_path': outbox['path'], 'result_source_phase': 'delivery_ready',
            'source_thread_id': binding['task_id'], 'source_turn_id': 'old-ready-turn',
            'source_message_id': 'old-ready-message', 'source_reply_sha256': hashlib.sha256(text.encode()).hexdigest(),
            'reply_observed_at': dt.datetime.now(dt.timezone.utc).isoformat(),
            'actual_native_completion': native_pin, 'visible_reply': w.file_digest(self.root, 'reports/old-ready.txt')}
        w.record_result_handoff(self.root, request)
        return item, pin, identity, request

    def test_frozen_old_ready_real_receive_decision_and_duplicates(self):
        item, _, identity, queued = self.queued_ready_original()
        files = [self.root / queued['outbox_path'], self.root / queued['actual_native_completion']['path'],
                 self.root / queued['visible_reply']['path'], w.receipts_path(self.root, item['task_id'])]
        originals = {str(p): p.read_bytes() for p in files}
        self.prepare((fixture.PRODUCER, fixture.ASSISTANT)); self.apply()
        received, decision = self.receive_original(identity, queued)
        self.assertEqual(received['source_thread_id'], 'fixed-' + fixture.PRODUCER)
        self.assertEqual(received['source_message_id'], 'old-ready-message')
        self.assertEqual(received['result_source_phase'], 'delivery_ready')
        self.assertTrue(received['batch_delivery_frozen'])
        self.assertEqual(decision['decision'], 'rework')
        self.assertEqual({str(p): p.read_bytes() for p in files}, originals)

    def test_old_ready_cannot_create_a_new_queue_after_cutover(self):
        _, _, identity, queued = self.queued_ready_original()
        self.prepare((fixture.PRODUCER, fixture.ASSISTANT)); self.apply()
        before = w.result_handoff_path(self.root, identity['task_id']).read_bytes()
        with self.assertRaises(w.WorkflowError):
            w.record_result_handoff(self.root, {**queued, 'idempotency_key': 'forbidden-old-ready-new-queue'})
        self.assertEqual(w.result_handoff_path(self.root, identity['task_id']).read_bytes(), before)

    def test_old_ready_refuses_replaced_provenance_or_unfrozen_request(self):
        _, _, identity, queued = self.queued_ready_original()
        self.prepare((fixture.PRODUCER, fixture.ASSISTANT)); self.apply()
        original = next(row for row in w._result_handoff_rows(self.root, identity['task_id'])
                        if row['event'] == 'notification_queued')
        copied = self.write('reports/copied-ready-native.json', w.read_json(self.root / queued['actual_native_completion']['path']))
        (self.root / 'reports/copied-ready.txt').write_bytes((self.root / queued['visible_reply']['path']).read_bytes())
        copied_reply = w.file_digest(self.root, 'reports/copied-ready.txt')
        replacements = [{'source_message_id': 'not-original'}, {'source_turn_id': 'not-original'},
            {'source_reply_sha256': 'f' * 64}, {'actual_native_completion': copied},
            {'visible_reply': copied_reply}, {'scope': 'project:unapproved:other'},
            {'result_source_phase': 'completed_final'}, {'record_hash': 'f' * 64}, {'batch_delivery_frozen': False}]
        for change in replacements:
            with self.subTest(change=change), self.assertRaises(w.WorkflowError):
                continuity.ready_source(self.root, {**original, **change}, 'fixed-' + fixture.PRODUCER)
        with self.assertRaises(w.WorkflowError):
            continuity.ready_source(self.root, queued, 'fixed-' + fixture.PRODUCER)

    def ordinary_resume(self):
        item, pin, identity, queued = self.queued_original()
        path = w.snapshot_path(self.root, item['task_id'])
        snapshot = w.read_json(path)
        snapshot['plan_status'] = 'blocked_health_stale'
        w.atomic_write_json(path, snapshot)
        original_plan = copy.deepcopy(snapshot['departments'])
        self.prepare((fixture.PRODUCER, fixture.ASSISTANT)); self.apply()
        _, decision = self.receive_original(identity, queued)
        scope = snapshot['goal_delivery']['authorized_scope'][0]
        payload = self.root / 'reports/exact-current-resume.txt'
        payload.write_text(item['task_id'] + ' Resume the frozen corrected batch once.')
        request = self.base.t.requested(sender=fixture.ASSISTANT, target=fixture.PRODUCER,
            scope=scope, payload=w.file_digest(self.root, str(payload.relative_to(self.root))))
        request['action_id'] = 'same-task-new-window-exact-resume-v1'
        action = {**request, 'decision_record_id': decision['record_id']}
        action_path = self.write('reports/current-resume-action.json', action)['path']
        runtime.record_approved_action(self.root, item['task_id'], action_path)
        binding = w.department_registry(self.root)[fixture.PRODUCER]['chat_binding']
        request.update(authorization_changes=[], assignment_record_required=True,
            actual_target_state=self.write('reports/current-resume-target.json', {
                'thread': {'id': binding['task_id'], 'title': binding['title'], 'cwd': binding['cwd']},
                'turns': [{'id': 'new-target-ready', 'status': 'completed', 'items': []}]}))
        return item, request, original_plan

    def test_current_ordinary_resume_prepares_and_records_current_dispatch(self):
        item, request, original_plan = self.ordinary_resume()
        tid = item['task_id']
        old_receipts = w.read_jsonl(w.receipts_path(self.root, tid))
        prepared = recovery.prepare_message(self.root, request)
        self.assertEqual(prepared['status'], 'ready_to_send', prepared)
        self.assertEqual(prepared['authorization_precheck']['status'], 'within_original_authorization')
        args = argparse.Namespace(task_id=tid, receipt_type='dispatch_sent', department=fixture.PRODUCER,
            chat_task_id=request['target_thread_id'], idempotency_key='actual-new-target-dispatch',
            policy_decision_id=prepared['policy_decision']['decision_id'], action_id=request['action_id'],
            action_class='thread_message', scope=request['scope'], ack_nonempty=False, evidence='')
        sent, _ = w.record_receipt(self.root, args)
        self.assertEqual(sent['chat_task_id'], 'new-' + fixture.PRODUCER)
        self.assertEqual(w.record_receipt(self.root, args)[0]['result'], 'duplicate_ignored')
        ack, _ = w.record_receipt(self.root, argparse.Namespace(**{**vars(args),
            'receipt_type': 'chat_ack', 'idempotency_key': 'actual-new-target-ack', 'ack_nonempty': True}))
        self.assertEqual(ack['chat_task_id'], 'new-' + fixture.PRODUCER)
        self.assertEqual(w.read_json(w.snapshot_path(self.root, tid))['departments'], original_plan)
        self.assertEqual(w.read_jsonl(w.receipts_path(self.root, tid))[:len(old_receipts)], old_receipts)
        self.assertEqual(w._validate_receipt_chain(self.root, tid)[1], [])
        self.assertEqual(recovery.prepare_message(self.root, request)['status'], 'blocked')

    def test_rotation_cannot_replay_old_sent_action_to_new_window(self):
        item, _ = self.assignment()
        self.prepare((fixture.PRODUCER, fixture.ASSISTANT)); self.apply()
        snapshot = w.read_json(w.snapshot_path(self.root, item['task_id']))
        source = next(r for r in w.read_jsonl(w.receipts_path(self.root, item['task_id']))
                      if r['receipt_id'] == item['dispatch_receipt_id'])
        reasons = w._ordinary_thread_dispatch_precheck(self.root, snapshot=snapshot,
            task_id=item['task_id'], target_department=fixture.PRODUCER,
            target_thread_id='new-' + fixture.PRODUCER, action_id=source['action_id'], scope=source['scope'],
            sender_department=fixture.ASSISTANT, payload_sha256=item['payload']['sha256'])
        self.assertIn('thread_dispatch_exact_action_already_sent', reasons)

    def coordination_resume(self, *, ack=True, assigned=True):
        original = responsibility_fixture.AssistantResponsibilityResumeTests('runTest')
        original.setUp(); self.addCleanup(original.doCleanups)
        self.root = original.root
        original.initialize(); original.initial_assignment(ack=ack)
        snapshot = original.snapshot(); role = responsibility_fixture.ASSISTANT
        payload = snapshot['goal_contract']; body = (self.root / payload['path']).read_text()
        registry = w.department_registry(self.root); source = registry['operations']['chat_binding']
        target = registry[role]['chat_binding']
        dispatch = w.read_jsonl(w.receipts_path(self.root, original.task_id))[0]
        page = {'thread': {'id': source['task_id'], 'title': source['title'], 'cwd': source['cwd']},
            'turns': [{'id': 'original-invocation', 'error': None, 'items': [{
                'id': 'original-call', 'type': 'mcpToolCall', 'server': 'codex_app',
                'tool': 'send_message_to_thread', 'status': 'completed', 'error': None,
                'arguments': {'threadId': target['task_id'], 'prompt': body}}]}]}
        item = {'schema': continuity.ASSIGNMENT_SCHEMA, 'task_id': original.task_id,
            'department': role, 'sender_department': 'operations', 'scope': original.scope, 'payload': payload,
            'actual_native_invocation': self.write('reports/frozen-original-invocation.json', page),
            'actual_native_send': self.write('reports/frozen-original-send.json', {
                'actual_tool': 'mcp__codex_app__send_message_to_thread', 'thread_id': target['task_id'],
                'raw_tool_return': original.send_document, 'exact_consumed_prompt': payload}),
            'source_call_id': 'original-call', 'dispatch_receipt_id': dispatch['receipt_id']}
        item_pin = self.write('reports/frozen-original-assignment.json', item)
        if assigned:
            continuity.record_assignment(self.root, item, item_pin)
        self.prepare(('operations', role)); self.apply()
        requested = original.requested()
        requested['sender_department'] = requested.pop('department')
        requested.update(payload=w.file_digest(self.root, 'reports/read-only-resume-message.txt'),
            assignment_record_required=True, authorization_changes=[],
            actual_target_state=self.write('reports/current-assistant-ready.json', {
                'thread': {'id': requested['target_thread_id'], 'title': requested['target_thread_title'],
                           'cwd': requested['target_cwd']}, 'turns': [{'id': 'current', 'status': 'completed'}]}))
        return original, item, requested

    def coordination_precheck(self, original, request):
        return w._ordinary_thread_dispatch_precheck(self.root, snapshot=original.snapshot(),
            **{k: request[k] for k in ('task_id', 'sender_department', 'target_department',
                                      'target_thread_id', 'action_id', 'scope', 'payload_sha256')})

    def test_rotated_actual_coordination_assignment_prepares_without_operations_result(self):
        original, _, request = self.coordination_resume()
        protected = {path: path.read_bytes() for path in (
            w.snapshot_path(self.root, original.task_id), w.receipts_path(self.root, original.task_id),
            self.root / 'data/department-current-assignment.json')}
        answer = recovery.prepare_message(self.root, request)
        self.assertEqual(answer['status'], 'ready_to_send', answer)
        self.assertEqual(answer['authorization_precheck']['status'], 'within_original_authorization')
        self.assertFalse(answer['message_sent'])
        self.assertEqual({path: path.read_bytes() for path in protected}, protected)
        self.assertFalse(any(r['receipt_type'] == 'outbox_received' for r in
                             w.read_jsonl(w.receipts_path(self.root, original.task_id))))
        sent, _ = w.record_receipt(self.root, argparse.Namespace(task_id=original.task_id,
            receipt_type='dispatch_sent', department=request['target_department'],
            chat_task_id=request['target_thread_id'], idempotency_key='fixture-current-coordination-send',
            policy_decision_id=answer['policy_decision']['decision_id'], action_id=request['action_id'],
            action_class='thread_message', scope=request['scope'], ack_nonempty=False, evidence=''))
        self.assertEqual(sent['chat_task_id'], request['target_thread_id'])
        self.assertIn('thread_dispatch_exact_action_already_sent', self.coordination_precheck(original, request))

    def test_rotated_coordination_keeps_original_assignment_deduplication(self):
        original, _, request = self.coordination_resume()
        request.update(action_id='assign-goal-review:' + original.task_id,
                       payload_sha256=original.snapshot()['goal_contract']['sha256'])
        self.assertIn('thread_dispatch_exact_action_already_sent', self.coordination_precheck(original, request))

    def test_rotated_coordination_needs_frozen_actual_assignment_and_native_ack(self):
        for options in ({'ack': False}, {'assigned': False}):
            with self.subTest(options=options):
                original, _, request = self.coordination_resume(**options)
                self.assertIn('goal_dispatch_dependency_missing:operations', self.coordination_precheck(original, request))

    def test_rotated_coordination_refuses_changed_original_native_source(self):
        original, item, request = self.coordination_resume()
        (self.root / item['actual_native_invocation']['path']).write_text('{}')
        self.assertIn('goal_dispatch_dependency_missing:operations', self.coordination_precheck(original, request))

    def test_rotated_coordination_does_not_waive_other_dependencies_or_scope(self):
        original, _, request = self.coordination_resume()
        fields = {k: request[k] for k in ('task_id', 'sender_department', 'target_department',
                                         'target_thread_id', 'action_id', 'scope', 'payload_sha256')}
        snapshot = original.snapshot()
        next(x for x in snapshot['departments'] if x['department'] == request['target_department'])['depends_on'].append('paid-growth-data')
        reasons = w._ordinary_thread_dispatch_precheck(self.root, snapshot=snapshot, **fields)
        self.assertIn('goal_dispatch_dependency_missing:paid-growth-data', reasons)
        self.assertNotIn('goal_dispatch_dependency_missing:operations', reasons)
        self.assertIn('goal_dispatch_dependency_missing:operations',
                      self.coordination_precheck(original, {**request, 'scope': 'project:foreign:v1'}))
        self.assertIn('goal_dispatch_dependency_missing:operations',
                      self.coordination_precheck(original, {**request, 'sender_department': 'operations-assistant-2'}))

    def test_rotated_coordination_keeps_named_dependency_and_production_gates(self):
        original, _, request = self.coordination_resume()
        snapshot = original.snapshot()
        snapshot['goal_delivery']['dependencies'] = [{'id': 'original-business-input', 'owner': 'paid-growth-data',
            'scope': original.scope, 'unblock_condition': 'Real input required',
            'applies_to': [request['target_department']]}]
        fields = {k: request[k] for k in ('task_id', 'sender_department', 'target_department',
                                         'target_thread_id', 'action_id', 'scope', 'payload_sha256')}
        reasons = w._ordinary_thread_dispatch_precheck(self.root, snapshot=snapshot, **fields)
        self.assertIn('goal_dispatch_named_dependency_missing:original-business-input', reasons)
        with self.assertRaisesRegex(w.WorkflowError, 'fresh exact production admission'):
            w.policy_check(self.root, task_id=original.task_id, department='operations',
                           action_id='not-authorized', action_class='cms_write', scope=original.scope)

    def test_rotated_coordination_requires_original_coordination_contract(self):
        original, _, request = self.coordination_resume()
        snapshot = original.snapshot()
        snapshot['goal_delivery']['coordination_review_contract'] = {}
        fields = {k: request[k] for k in ('task_id', 'sender_department', 'target_department',
                                         'target_thread_id', 'action_id', 'scope', 'payload_sha256')}
        self.assertIn('goal_dispatch_dependency_missing:operations',
                      w._ordinary_thread_dispatch_precheck(self.root, snapshot=snapshot, **fields))

    def planned_unsent(self, *, approve=True, old_dispatched=False, freeze_old_result=True):
        registry = w.read_json(self.root / 'data/department-registry.json')
        publisher = copy.deepcopy(next(x for x in registry['departments'] if x['id'] == fixture.PRODUCER))
        publisher['id'] = 'publishing'
        publisher['chat_binding'].update(task_id='fixed-publishing', title='publishing')
        registry['departments'].append(publisher)
        w.atomic_write_json(self.root / 'data/department-registry.json', registry)
        self.base.t.initialize(producer_departments=[fixture.PRODUCER, 'publishing'],
            dependencies=[{'department': 'publishing', 'depends_on': [fixture.PRODUCER]}])
        item, pin = self.base.assignment(initialize=False)
        continuity.record_assignment(self.root, item, pin)
        _, outbox = self.base.t.producer_result()
        identity = {'task_id': item['task_id'], 'sender_department': fixture.PRODUCER,
                    'candidate_version': 'v1', 'result_sha256': outbox['sha256']}
        queued = {**identity, **self.base.t.completed_result_fields(), 'event': 'notification_queued',
                  'idempotency_key': 'actual-original-result', 'outbox_path': outbox['path']}
        w.record_result_handoff(self.root, queued)
        decision = None
        if old_dispatched:
            _, decision = self.receive_original(identity, queued, next_owner='publishing', decision='continue')
            body = self.root / 'reports/original-publisher-message.txt'
            body.write_text(item['task_id'] + ' Original finite publisher work.')
            old_action = self.base.t.requested(target='publishing', scope=self.base.t.snapshot()['goal_delivery']['authorized_scope'][0],
                payload=w.file_digest(self.root, 'reports/original-publisher-message.txt'))
            old_action.update(action_id='original-publisher-already-sent', decision_record_id=decision['record_id'])
            action_pin = self.write('reports/original-publisher-action.json', old_action)
            runtime.record_approved_action(self.root, item['task_id'], action_pin['path'])
            allowed = self.base.t.policy(old_action)
            self.assertEqual(allowed['status'], 'allow', allowed)
            self.base.t.fixture.receipt('dispatch_sent', 'publishing', 'original-publisher-send',
                policy_decision_id=allowed['decision_id'], action_id=old_action['action_id'],
                action_class='thread_message', scope=old_action['scope'], evidence=old_action['payload']['path'])
            self.base.t.fixture.receipt('chat_ack', 'publishing', 'original-publisher-ack')
            if freeze_old_result:
                with mock.patch.object(fixture, 'PRODUCER', 'publishing'):
                    _, old_box = self.base.t.producer_result('publisher-old-v1')
                text = item['task_id'] + ' Original publisher final.'
                visible = self.root / 'reports/original-publisher-final.txt'; visible.write_text(text)
                completion = self.write('reports/original-publisher-final.json', {
                    'thread': {'id': 'fixed-publishing'}, 'turn_id': 'publisher-original-final',
                    'status': 'completed', 'error': None, 'completedAt': dt.datetime.now(dt.timezone.utc).timestamp(),
                    'message': {'id': 'publisher-original-message', 'turnId': 'publisher-original-final',
                                'phase': 'final_answer', 'text': text}})
                w.record_result_handoff(self.root, {'task_id': item['task_id'], 'sender_department': 'publishing',
                    'candidate_version': 'publisher-old-v1', 'result_sha256': old_box['sha256'],
                    'event': 'notification_queued', 'idempotency_key': 'original-publisher-result',
                    'outbox_path': old_box['path'], 'source_thread_id': 'fixed-publishing',
                    'source_turn_id': 'publisher-original-final', 'source_reply_sha256': hashlib.sha256(text.encode()).hexdigest(),
                    'reply_observed_at': dt.datetime.now(dt.timezone.utc).isoformat(),
                    'actual_native_completion': completion, 'visible_reply': w.file_digest(self.root, 'reports/original-publisher-final.txt')})
        snapshot = self.base.t.snapshot(); snapshot['plan_status'] = 'blocked_health_stale'
        w.atomic_write_json(w.snapshot_path(self.root, item['task_id']), snapshot)
        original_plan = copy.deepcopy(snapshot['departments'])
        self.prepare((fixture.PRODUCER, fixture.ASSISTANT, 'publishing')); self.apply()
        if decision is None:
            _, decision = self.receive_original(identity, queued, next_owner='publishing', decision='continue')
        path = self.root / 'reports/unsent-publisher-message.txt'
        path.write_text(item['task_id'] + ' Original publishing source inspection only; no Save.')
        request = self.base.t.requested(target='publishing', scope=snapshot['goal_delivery']['authorized_scope'][0],
            payload=w.file_digest(self.root, 'reports/unsent-publisher-message.txt'))
        request['decision_record_id'] = decision['record_id']
        action = self.write('reports/unsent-publisher-approved-action.json', request)
        if approve:
            runtime.record_approved_action(self.root, item['task_id'], action['path'])
        request.update(authorization_changes=[], assignment_record_required=True,
            actual_target_state=self.write('reports/current-publisher-native.json', {
                'thread': {'id': request['target_thread_id'], 'title': request['target_thread_title'],
                           'cwd': request['target_cwd']}, 'turns': [{'id': 'publisher-ready', 'status': 'completed'}]}))
        return item, request, original_plan

    def test_legacy_dispatched_role_without_assignment_uses_frozen_result_and_old_assistant(self):
        item, request, plan = self.planned_unsent(old_dispatched=True)
        history = w.read_json(self.root / rotation.OUTPUT / 'history-v2.json')
        self.assertFalse(any(e['department'] == 'publishing' for e in history['assignments'].values()))
        receipts = w.receipts_path(self.root, item['task_id']).read_bytes()
        self.assertEqual(recovery.prepare_message(self.root, request)['status'], 'ready_to_send')
        self.assertEqual(w.read_json(w.snapshot_path(self.root, item['task_id']))['departments'], plan)
        self.assertEqual(w.receipts_path(self.root, item['task_id']).read_bytes(), receipts)

    def test_legacy_dispatch_without_frozen_result_or_new_exact_action_remains_blocked(self):
        _, request, _ = self.planned_unsent(old_dispatched=True, freeze_old_result=False)
        self.assertEqual(recovery.prepare_message(self.root, request)['status'], 'blocked')

    def test_legacy_dispatch_with_frozen_result_still_requires_registered_current_action(self):
        _, request, _ = self.planned_unsent(old_dispatched=True, approve=False)
        self.assertEqual(recovery.prepare_message(self.root, request)['status'], 'blocked')

    def test_legacy_dispatched_role_cannot_replay_original_action_or_production(self):
        item, request, _ = self.planned_unsent(old_dispatched=True)
        answer = recovery.prepare_message(self.root, {**request, 'action_id': 'original-publisher-already-sent'})
        self.assertEqual(answer['status'], 'blocked')
        self.assertIn('thread_dispatch_exact_action_already_sent', answer['policy_decision']['reason'])
        with self.assertRaisesRegex(w.WorkflowError, 'fresh exact production admission'):
            w.policy_check(self.root, task_id=item['task_id'], department='publishing',
                action_id='unapproved-production', action_class='cms_write', scope=request['scope'])

    def test_planned_unsent_uses_actual_decision_and_records_current_dispatch_ack(self):
        item, request, original_plan = self.planned_unsent()
        receipts = w.read_jsonl(w.receipts_path(self.root, item['task_id']))
        self.assertFalse(any(r['department'] == 'publishing' for r in receipts))
        history = w.read_json(self.root / rotation.OUTPUT / 'history-v2.json')
        self.assertFalse(any(e['department'] == 'publishing' for e in history['assignments'].values()))
        answer = recovery.prepare_message(self.root, request)
        self.assertEqual(answer['status'], 'ready_to_send', answer)
        args = argparse.Namespace(task_id=item['task_id'], receipt_type='dispatch_sent', department='publishing',
            chat_task_id=request['target_thread_id'], idempotency_key='fixture-first-current-publisher-send',
            policy_decision_id=answer['policy_decision']['decision_id'], action_id=request['action_id'],
            action_class='thread_message', scope=request['scope'], ack_nonempty=False, evidence='')
        sent, _ = w.record_receipt(self.root, args)
        self.assertEqual(sent['chat_task_id'], 'new-publishing')
        ack, _ = w.record_receipt(self.root, argparse.Namespace(**{**vars(args), 'receipt_type': 'chat_ack',
            'idempotency_key': 'fixture-first-current-publisher-ack', 'ack_nonempty': True}))
        self.assertEqual(ack['chat_task_id'], 'new-publishing')
        self.assertEqual(w.record_receipt(self.root, args)[0]['result'], 'duplicate_ignored')
        # Keep the synthetic post-send policy observation distinct from the
        # original second-resolution allow; it must not invent an ID collision.
        with mock.patch.object(w, 'utc_timestamp', return_value=dt.datetime.now(dt.timezone.utc).isoformat()):
            self.assertEqual(recovery.prepare_message(self.root, request)['status'], 'blocked')
        self.assertEqual(w.read_json(w.snapshot_path(self.root, item['task_id']))['departments'], original_plan)
        self.assertEqual(w.read_jsonl(w.receipts_path(self.root, item['task_id']))[:len(receipts)], receipts)
        self.assertEqual(w._validate_receipt_chain(self.root, item['task_id'])[1], [])

        sender = w.department_registry(self.root)[fixture.ASSISTANT]['chat_binding']
        page = {'thread': {'id': sender['task_id'], 'title': sender['title'], 'cwd': sender['cwd']},
            'turns': [{'id': 'new-publisher-send-turn', 'error': None, 'items': [{
                'id': 'new-publisher-send-call', 'type': 'mcpToolCall', 'server': 'codex_app',
                'tool': 'send_message_to_thread', 'status': 'completed', 'error': None,
                'arguments': {'threadId': request['target_thread_id'],
                              'prompt': (self.root / request['payload']['path']).read_text()}}]}]}
        current = {'schema': continuity.ASSIGNMENT_SCHEMA, 'task_id': item['task_id'],
            'department': 'publishing', 'sender_department': fixture.ASSISTANT,
            'payload': request['payload'], 'actual_native_invocation': self.write('reports/new-publisher-call.json', page),
            'actual_native_send': self.write('reports/new-publisher-send.json', {
                'actual_tool': 'mcp__codex_app__send_message_to_thread', 'thread_id': request['target_thread_id'],
                'raw_tool_return': {'content': [{'type': 'text', 'text': json.dumps({'threadId': request['target_thread_id']})}],
                                    'isError': False}, 'exact_consumed_prompt': request['payload']}),
            'source_call_id': 'new-publisher-send-call', 'dispatch_receipt_id': sent['receipt_id']}
        pin = self.write('reports/new-publisher-current-assignment.json', current)
        self.assertEqual(continuity.record_assignment(self.root, current, pin)['result'], 'recorded')
        self.assertEqual(w.read_json(self.root / 'data/department-current-assignment.json')['assignments']['publishing'], pin)

    def test_planned_unsent_needs_committed_exact_approved_action(self):
        _, request, _ = self.planned_unsent(approve=False)
        answer = recovery.prepare_message(self.root, request)
        self.assertEqual(answer['status'], 'blocked')
        self.assertIn('thread_dispatch_planned_fixed_chat_mismatch', answer['policy_decision']['reason'])

    def test_planned_unsent_rejects_changed_original_plan_and_closed_goal(self):
        item, request, _ = self.planned_unsent()
        original = self.base.t.snapshot()
        for change in ('plan', 'terminal', 'successor'):
            snapshot = copy.deepcopy(original)
            if change == 'plan':
                next(x for x in snapshot['departments'] if x['department'] == 'publishing')['depends_on'] = []
            elif change == 'terminal':
                snapshot['current_state'] = 'closed'
            else:
                snapshot['workflow_successor_link'] = {'task_id': 'actual-successor'}
            w.atomic_write_json(w.snapshot_path(self.root, item['task_id']), snapshot)
            with self.subTest(change=change):
                self.assertEqual(recovery.prepare_message(self.root, request)['status'], 'blocked')

    def test_planned_unsent_rejects_wrong_project_scope_payload_and_action(self):
        _, request, _ = self.planned_unsent()
        for changes in ({'target_project_id': 'foreign-project'}, {'scope': 'project:foreign:v1'},
                        {'action_id': 'unapproved-action'}, {'payload_sha256': 'a' * 64},
                        {'target_thread_id': 'fixed-publishing'}, {'target_department': 'paid-growth-data'}):
            with self.subTest(changes=changes):
                try:
                    result = recovery.prepare_message(self.root, {**request, **changes})
                except w.WorkflowError:
                    continue
                self.assertNotEqual(result['status'], 'ready_to_send')

    def test_planned_unsent_rejects_changed_contract_action_or_decision_source(self):
        item, request, _ = self.planned_unsent()
        paths = [self.root / self.base.t.snapshot()['goal_contract']['path'],
                 self.root / 'reports/unsent-publisher-approved-action.json',
                 w.result_handoff_path(self.root, item['task_id'])]
        for path in paths:
            data = path.read_bytes()
            try:
                path.write_bytes(data + b' ')
                with self.subTest(path=path.name):
                    if path == paths[-1]:
                        path.write_bytes(data + b'{}\n')
                    try:
                        answer = recovery.prepare_message(self.root, request)
                    except w.WorkflowError:
                        continue
                    self.assertNotEqual(answer['status'], 'ready_to_send')
            finally:
                path.write_bytes(data)

    def test_planned_unsent_still_rejects_production_and_old_window_receipts(self):
        item, request, _ = self.planned_unsent()
        answer = recovery.prepare_message(self.root, request)
        with self.assertRaisesRegex(w.WorkflowError, 'fresh exact production admission'):
            w.policy_check(self.root, task_id=item['task_id'], department='publishing',
                           action_id='no-production', action_class='cms_write', scope=request['scope'])
        with self.assertRaises(w.WorkflowError):
            w.record_receipt(self.root, argparse.Namespace(task_id=item['task_id'], receipt_type='dispatch_sent',
                department='publishing', chat_task_id='fixed-publishing', idempotency_key='forbidden-old-send',
                policy_decision_id=answer['policy_decision']['decision_id'], action_id=request['action_id'],
                action_class='thread_message', scope=request['scope'], ack_nonempty=False, evidence=''))

    def test_new_queue_cannot_use_old_frozen_producer_identity(self):
        _, _, _, queued = self.queued_original()
        self.prepare((fixture.PRODUCER, fixture.ASSISTANT)); self.apply()
        with self.assertRaises(w.WorkflowError):
            w.record_result_handoff(self.root, {**queued, 'idempotency_key': 'forbidden-old-new-queue'})

    def test_current_dispatch_projection_rejects_unrelated_closed_and_invalid_scope(self):
        item, request, _ = self.ordinary_resume()
        snapshot = w.read_json(w.snapshot_path(self.root, item['task_id']))
        for patch in ({'task_id': 'unrelated-not-frozen-task'}, {'current_state': 'closed'},
                      {'workflow_successor_link': {'task_id': 'successor'}}):
            original = {**snapshot, **patch}
            self.assertEqual(rotation.current_dispatch_snapshot(self.root, original, fixture.PRODUCER), original)
        blocked = {**snapshot, 'plan_status': 'blocked_missing_inputs'}
        reasons = w._ordinary_thread_dispatch_precheck(self.root, snapshot=blocked,
            **{k: request[k] for k in ('task_id','target_department','target_thread_id','action_id',
                                     'scope','sender_department','payload_sha256')})
        self.assertIn('thread_dispatch_plan_not_ready', reasons)
        wrong = {**request, 'scope': 'project:unapproved:new-scope'}
        self.assertEqual(recovery.prepare_message(self.root, wrong)['status'], 'blocked')
        self.assertEqual(recovery.prepare_message(self.root,
            {**request, 'target_thread_id': 'fixed-' + fixture.PRODUCER})['status'], 'blocked')

    def test_current_dispatch_receipt_still_requires_current_target_and_allowed_policy(self):
        item, request, _ = self.ordinary_resume()
        prepared = recovery.prepare_message(self.root, request)
        common = dict(task_id=item['task_id'], receipt_type='dispatch_sent', department=fixture.PRODUCER,
            idempotency_key='must-not-forge-dispatch', action_id=request['action_id'],
            action_class='thread_message', scope=request['scope'], ack_nonempty=False, evidence='')
        for target, policy in [('fixed-' + fixture.PRODUCER, prepared['policy_decision']['decision_id']),
                               ('new-' + fixture.PRODUCER, 'forged-policy')]:
            with self.subTest(target=target, policy=policy), self.assertRaises(w.WorkflowError):
                w.record_receipt(self.root, argparse.Namespace(**common, chat_task_id=target, policy_decision_id=policy))
        external = argparse.Namespace(**{**common, 'action_class': 'cms_write'},
            chat_task_id='new-' + fixture.PRODUCER, policy_decision_id=prepared['policy_decision']['decision_id'])
        with self.assertRaises(w.WorkflowError): w.record_receipt(self.root, external)

    def test_actual_dispatch_survives_rotation_and_new_identity_is_current(self):
        item, pin = self.assignment()
        old_receipts = (w.receipts_path(self.root, item['task_id'])).read_bytes()
        old_assignment = (self.root / 'data/department-current-assignment.json').read_bytes()
        self.prepare(('operations', fixture.PRODUCER, fixture.ASSISTANT))
        self.assertEqual(len(self.apply()['results']), 3)
        result = continuity.current_assignment(self.root, fixture.PRODUCER, pin)
        self.assertTrue(result['resume_required'])
        self.assertEqual(old_receipts, w.receipts_path(self.root, item['task_id']).read_bytes())
        self.assertEqual(old_assignment, (self.root / 'data/department-current-assignment.json').read_bytes())
        current = w.department_registry(self.root)[fixture.PRODUCER]['chat_binding']
        self.assertEqual(current['task_id'], 'new-' + fixture.PRODUCER)
        self.assertNotEqual(current['last_reply_ref'], 'old-final')

    def test_already_queued_result_survives_and_notification_targets_new_assistant(self):
        identity, request, _ = self.base.ready()
        w.record_result_handoff(self.root, request)
        self.prepare((fixture.PRODUCER, fixture.ASSISTANT)); self.apply()
        self.assertEqual(coordination._validate_queued(self.root, identity)['department'], fixture.PRODUCER)
        delivery = coordination.delivery_identity(self.root, identity)
        self.assertEqual(delivery['target_thread_id'], 'new-' + fixture.ASSISTANT)
        self.assertEqual(coordination._validate_queued(self.root, identity)['fixed_chat_task_id'], 'fixed-' + fixture.PRODUCER)

    def test_wrong_role_or_changed_original_source_is_rejected(self):
        item, pin = self.assignment(); self.prepare(('operations', fixture.PRODUCER)); self.apply()
        for change in ({'department': fixture.ASSISTANT}, {'source_call_id': 'forged'}):
            with self.subTest(change=change), self.assertRaises(w.WorkflowError):
                continuity._dispatch_source(self.root, {**item, **change})
        (self.root / item['payload']['path']).write_text('tampered')
        with self.assertRaises(w.WorkflowError):
            continuity._dispatch_source(self.root, item)

    def test_wrong_project_empty_reply_and_active_old_are_blocked(self):
        self.assignment()
        plan = self.prepare((fixture.PRODUCER,), bad_project=True)
        self.assertFalse(plan['records']); self.assertTrue(plan['blocked'])
        # Frozen manifests deliberately cannot be overwritten by another plan.
        self.assertEqual(w.department_registry(self.root)[fixture.PRODUCER]['chat_binding']['task_id'], 'fixed-' + fixture.PRODUCER)

    def test_active_old_refuses_cutover(self):
        self.assignment(); plan = self.prepare((fixture.PRODUCER,), active=fixture.PRODUCER)
        self.assertFalse(plan['records']); self.assertTrue(plan['blocked'])

    def test_empty_new_handoff_refuses_cutover(self):
        self.assignment(); plan = self.prepare((fixture.PRODUCER,), empty_reply=True)
        self.assertFalse(plan['records']); self.assertTrue(plan['blocked'])

    def test_duplicate_apply_and_crash_after_registry_write_are_idempotent(self):
        self.assignment(); self.prepare((fixture.PRODUCER,))
        real = w.atomic_write_json
        def fail_after_registry(path, data):
            if str(path).endswith('-applied.json'):
                raise OSError('isolated crash after registry commit')
            return real(path, data)
        with mock.patch.object(w, 'atomic_write_json', side_effect=fail_after_registry), self.assertRaises(OSError):
            self.apply()
        before = (self.root / rotation.REGISTRY).read_bytes()
        self.assertEqual(self.apply()['results'][0]['status'], 'duplicate_ignored')
        self.assertEqual(before, (self.root / rotation.REGISTRY).read_bytes())
        self.assertEqual(self.apply()['results'][0]['status'], 'duplicate_ignored')

    def test_binding_cas_protects_concurrent_changes(self):
        self.assignment(); self.prepare((fixture.PRODUCER,))
        doc = w.read_json(self.root / rotation.REGISTRY)
        next(x for x in doc['departments'] if x['id'] == fixture.PRODUCER)['chat_binding']['last_reply_ref'] = 'parallel-result'
        self.write(rotation.REGISTRY, doc)
        with self.assertRaises(w.WorkflowError): self.apply()
        self.assertEqual(w.department_registry(self.root)[fixture.PRODUCER]['chat_binding']['last_reply_ref'], 'parallel-result')

    def test_tampered_or_forged_mapping_is_rejected(self):
        self.assignment(); plan = self.prepare((fixture.PRODUCER,))
        pin = plan['records'][0]; doc = w.read_json(self.root / pin['path'])
        doc['new_binding']['project_id'] = 'forged-project'
        plan['records'][0] = self.write(pin['path'], doc)
        self.write(rotation.OUTPUT + '/plan.json', plan)
        with self.assertRaises(w.WorkflowError): self.apply()

    def test_pinned_mapping_cannot_be_changed_after_adoption(self):
        item, pin = self.assignment(); plan = self.prepare((fixture.PRODUCER,)); self.apply()
        record = self.root / plan['records'][0]['path']
        record.write_text(record.read_text() + ' ')
        with self.assertRaises(w.WorkflowError): continuity._dispatch_source(self.root, item)

    def test_preview_never_changes_registry_and_old_permits_do_not_transfer(self):
        self.assignment(); self.prepare((fixture.PRODUCER,))
        before = (self.root / rotation.REGISTRY).read_bytes()
        rotation.apply(self.root, rotation.OUTPUT + '/plan.json')
        self.assertEqual(before, (self.root / rotation.REGISTRY).read_bytes())
        self.apply()
        with self.assertRaisesRegex(w.WorkflowError, 'fresh exact production admission'):
            w.policy_check(self.root, task_id=self.base.t.task_id, department=fixture.PRODUCER,
                           action_id='old-consumed-permit', action_class='cms_write', scope='old-scope',
                           approval_id='already-consumed', consume_approval=True)

    def test_rotation_preserves_existing_lease_token_fence_and_expiry(self):
        identity, request, _ = self.base.ready(); w.record_result_handoff(self.root, request)
        store = coordination.CoordinationStore(self.root); self.addCleanup(store.close)
        store.claim(identity, fixture.ASSISTANT, 'fixed-' + fixture.ASSISTANT, 'existing-claim')
        before = store.readback(identity)
        self.prepare((fixture.PRODUCER, fixture.ASSISTANT)); self.apply()
        self.assertEqual(store.readback(identity), before)

    def test_closed_old_source_does_not_create_new_authority_or_new_events(self):
        item, pin = self.assignment(); self.prepare(('operations', fixture.PRODUCER)); self.apply()
        path = w.snapshot_path(self.root, item['task_id']); snapshot = w.read_json(path)
        snapshot['current_state'] = 'closed'; w.atomic_write_json(path, snapshot)
        before = (self.root / w.WORKFLOW_EVENTS).read_bytes()
        result = continuity.current_assignment(self.root, fixture.PRODUCER, pin)
        self.assertFalse(result['permissions_inherited'])
        self.assertEqual(before, (self.root / w.WORKFLOW_EVENTS).read_bytes())

    def test_original_owner_direct_authorization_survives_without_new_permission(self):
        helper = recovery_fixture.RecoveryTests('runTest'); helper.setUp()
        self.addCleanup(helper.doCleanups); self.root = helper.root
        path, item, _ = helper.source(); recovery.record(self.root, path)
        self.prepare((fixture.PRODUCER,)); self.apply()
        _, proof = recovery.validate(self.root, item)
        self.assertFalse(proof['external_permission_issued'])
        self.assertEqual(proof['original_task_id'], 'historic-closed-001')
        with self.assertRaises(w.WorkflowError):
            recovery.validate(self.root, {**item, 'original_task_id': 'new-authority'})

    def test_original_official_queue_source_survives_without_transport_replay(self):
        helper = recovery_fixture.OfficialQueueAssignmentTests('runTest'); helper.setUp()
        self.addCleanup(helper.doCleanups); self.root = helper.root
        path, item = helper.queued(); recovery.recover_queued_assignment(self.root, path)
        self.prepare(('operations', fixture.ASSISTANT)); self.apply()
        _, receipt = recovery.queued_assignment_source(self.root, item)
        self.assertEqual(receipt['chat_task_id'], '11111111-1111-4111-8111-111111111111')
        with self.assertRaises(w.WorkflowError):
            recovery.queued_assignment_source(self.root, {**item, 'queue_message_id': 'forged'})

    def test_historical_review_keeps_full_proof_checks_and_forbids_writes(self):
        plan, producer = self.base.t.prepare_initial_review()
        self.base.t.assistant_verdict(plan, producer)
        task = self.base.t.task_id
        pin = self.write('reports/retained-position.json', {'task_id': task, 'department': fixture.PRODUCER})
        self.write('data/department-current-assignment.json', {'assignments': {fixture.PRODUCER: pin}})
        rows, bad = w._validate_receipt_chain(self.root, task)
        self.assertEqual(bad, [])
        self.prepare(('operations', fixture.PRODUCER, fixture.ASSISTANT)); self.apply()
        self.assertEqual(w._validate_receipt_chain(self.root, task)[1], [])
        receipt = next(x for x in rows if x['receipt_type'] == 'qa_verdict')
        with rotation.historical_receipt_validation(self.root, receipt):
            with self.assertRaisesRegex(w.WorkflowError, 'read-only'):
                w.atomic_write_json(self.root / 'reports/forbidden.json', {})
            with self.assertRaisesRegex(w.WorkflowError, 'read-only'):
                w.policy_check(self.root, task_id=task, department=fixture.PRODUCER,
                    action_id='cannot-create-authority', action_class='local_read', scope='project:fixture')
        self.assertFalse((self.root / 'reports/forbidden.json').exists())
        (self.root / producer['path']).write_text('tampered historical candidate')
        self.assertTrue(w._validate_receipt_chain(self.root, task)[1])


class ContinuedReadyTests(unittest.TestCase):
    """Actual normal queue/claim/intake/decision entries in isolated synthetic data."""
    def setUp(self):
        self.r=RotationTests('runTest');self.r.setUp();self.addCleanup(self.r.doCleanups)
        self.root=self.r.root;self.t=self.r.base.t;self.write=self.r.write
        self.item,self.assignment=self.r.assignment()
        rows=w.read_jsonl(w.receipts_path(self.root,self.t.task_id))
        evidence=self.write('reports/old-actual-ack.json',{'thread':w.department_registry(self.root)[fixture.PRODUCER]['chat_binding'],
            'turns':[{'id':'old-ack','status':'completed','error':None,'items':[
                {'type':'agentMessage','id':'ack-message','phase':'commentary','text':self.t.task_id+' received original task'}]}]})
        for row in rows:
            if row['receipt_type']=='dispatch_sent' and row['department']==fixture.PRODUCER:
                row['evidence']=[self.item['actual_native_invocation'],self.item['actual_native_send'],self.item['payload']]
            if row['receipt_type']=='chat_ack' and row['department']==fixture.PRODUCER:row['evidence']=[evidence]
        self.rehash_receipts(rows)

    def rehash_receipts(self,rows):
        previous=''
        for row in rows:
            row['previous_hash']=previous;row['receipt_hash']=w.sha256_value(w._receipt_payload_for_hash(row));previous=row['receipt_hash']
        w.receipts_path(self.root,self.t.task_id).write_text(''.join(json.dumps(row)+'\n' for row in rows))

    def prepare(self,kind='old'):
        path='reports/frozen-box.json';candidate=self.write('reports/frozen-deliverable.json',{'isolated':True})
        box=self.t.result_box(fixture.PRODUCER,'continued-v1',candidate)
        if kind=='current':
            box['fixed_chat_task_id']='new-'+fixture.PRODUCER;box['chat_reply']['in_current_fixed_department_chat']=False
        if kind=='missing':
            del box['fixed_chat_task_id'];del box['chat_reply'];box['source_chat']={'thread_id':'new-'+fixture.PRODUCER}
        self.box=self.write(path,box);self.box_bytes=(self.root/path).read_bytes()
        self.r.prepare((fixture.PRODUCER,fixture.ASSISTANT));self.r.apply()
        self.identity={'task_id':self.t.task_id,'sender_department':fixture.PRODUCER,'candidate_version':'continued-v1','result_sha256':self.box['sha256']}
        self.ready()
        return self.request

    def ready(self):
        self.request={**self.identity,'event':'notification_queued','idempotency_key':'continued-original-ready-once',
            'outbox_path':self.box['path'],'result_source_phase':'delivery_ready'}
        text=continuity.READY_MARKER+json.dumps({**self.identity,'outbox_path':self.box['path'],'batch_complete':True})+'\n'
        (self.root/'reports/current-ready.txt').write_bytes(text.encode())
        binding=w.department_registry(self.root)[fixture.PRODUCER]['chat_binding']
        native={'thread':{'id':binding['task_id'],'title':binding['title'],'cwd':binding['cwd']},
            'turns':[{'id':'current-ready','status':'inProgress','error':None,'startedAt':dt.datetime.now(dt.timezone.utc).timestamp()-1,
                'items':[{'type':'agentMessage','id':'current-complete-batch','phase':'commentary','text':text}]}]}
        self.native=native
        self.request.update(source_thread_id=binding['task_id'],source_turn_id='current-ready',source_message_id='current-complete-batch',
            source_reply_sha256=hashlib.sha256(text.encode()).hexdigest(),reply_observed_at=dt.datetime.now(dt.timezone.utc).isoformat(),
            actual_native_completion=self.write('reports/current-ready.json',native),visible_reply=w.file_digest(self.root,'reports/current-ready.txt'))

    def queue(self):return w.record_result_handoff(self.root,self.request)[0]

    def lifecycle(self,kind):
        self.prepare(kind);before=w.receipts_path(self.root,self.t.task_id).read_bytes()
        queued=self.queue();proof=queued['original_rotation_continuation']
        self.assertEqual(proof['original_thread_id'],'fixed-'+fixture.PRODUCER)
        self.assertEqual(proof['current_thread_id'],'new-'+fixture.PRODUCER)
        self.assertFalse(proof['production_permission_inherited'])
        self.assertEqual(self.queue()['record_id'],queued['record_id'])
        received,decision=self.r.receive_original(self.identity,self.request,decision='continue')
        self.assertTrue(received['controller_handoff']['results'][0]['controller_received'])
        self.assertEqual(decision['decision'],'continue')
        self.assertEqual(w.receipts_path(self.root,self.t.task_id).read_bytes(),before)
        self.assertEqual((self.root/self.box['path']).read_bytes(),self.box_bytes)
        self.assertEqual(len(w._result_handoff_rows(self.root,self.t.task_id)),3)

    def test_original_old_chat_metadata_reaffirmed_by_real_new_ready_lifecycle(self):self.lifecycle('old')
    def test_current_finite_result_with_frozen_false_chat_flag_lifecycle(self):self.lifecycle('current')
    def test_missing_old_top_level_chat_metadata_lifecycle(self):self.lifecycle('missing')

    def test_current_ready_followed_by_later_current_receipts_keeps_original_prefix(self):
        self.prepare()
        import time
        time.sleep(1.1)
        request=self.t.requested(sender='operations',target=fixture.PRODUCER);request['action_id']='later-current-original-work'
        decision=self.t.policy(request);self.assertEqual(decision['status'],'allow',decision)
        self.t.fixture.receipt('dispatch_sent',fixture.PRODUCER,'later-current-send',chat_task_id='new-'+fixture.PRODUCER,
            policy_decision_id=decision['decision_id'],action_id=request['action_id'],action_class='thread_message',scope=request['scope'])
        row=self.t.fixture.receipt('chat_ack',fixture.PRODUCER,'later-current-ack',chat_task_id='new-'+fixture.PRODUCER)
        self.assertGreater(w._parse_observed_at(row['created_at']),w._parse_observed_at(self.request['reply_observed_at']))
        self.assertIn('original_rotation_continuation',self.queue())

    def test_ack_progress_and_tampered_native_are_not_whole_results(self):
        self.prepare()
        for changed in ({'source_message_id':'forged'},{'source_reply_sha256':'a'*64}):
            with self.subTest(changed=changed),self.assertRaises(w.WorkflowError):
                w.record_result_handoff(self.root,{**self.request,**changed})
        self.native['turns'][0]['items'][0]['text']='ACK only'
        self.request['actual_native_completion']=self.write('reports/ack-only.json',self.native)
        with self.assertRaises(w.WorkflowError):self.queue()

    def test_frozen_assignment_and_native_send_cannot_be_tampered(self):
        self.prepare();(self.root/self.item['actual_native_invocation']['path']).write_text('{}')
        with self.assertRaises(w.WorkflowError):self.queue()

    def test_missing_original_ack_still_rejects(self):
        self.prepare();rows=w.read_jsonl(w.receipts_path(self.root,self.t.task_id))
        for row in rows:
            if row.get('receipt_type')=='chat_ack':row['ack_nonempty']=False
        self.rehash_receipts(rows)
        with self.assertRaises(w.WorkflowError):self.queue()

    def test_failed_original_dispatch_and_ack_before_dispatch_still_reject(self):
        self.prepare();rows=w.read_jsonl(w.receipts_path(self.root,self.t.task_id));original=copy.deepcopy(rows)
        for row in rows:
            if row.get('receipt_type')=='dispatch_sent' and row.get('department')==fixture.PRODUCER:
                row['receipt_type']='dispatch_failed'
        self.rehash_receipts(rows)
        with self.assertRaises(w.WorkflowError):self.queue()
        for row in original:
            if row.get('receipt_type')=='chat_ack':row['created_at']='2000-01-01T00:00:00+00:00'
        self.rehash_receipts(original)
        with self.assertRaises(w.WorkflowError):self.queue()

    def test_tampered_committed_queue_marker_cannot_admit_claim(self):
        self.prepare();queued=self.queue();rows=w._result_handoff_rows(self.root,self.t.task_id)
        rows[0]['original_rotation_continuation']['ack_receipt_id']='forged'
        rows[0]['record_hash']=w.sha256_value({k:v for k,v in rows[0].items() if k!='record_hash'})
        w.result_handoff_path(self.root,self.t.task_id).write_text(json.dumps(rows[0])+'\n')
        store=coordination.CoordinationStore(self.root);self.addCleanup(store.close)
        with self.assertRaises(w.WorkflowError):store.claim(self.identity,fixture.ASSISTANT,'current-A2','no-forged-queue-marker')

    def test_current_dispatch_before_ready_must_have_current_ack(self):
        self.prepare('current')
        request=self.t.requested(sender='operations',target=fixture.PRODUCER);request['action_id']='new-current-actual-rework'
        decision=self.t.policy(request)
        self.assertEqual(decision['status'],'allow',decision)
        self.t.fixture.receipt('dispatch_sent',fixture.PRODUCER,'new-current-actual-send',
            policy_decision_id=decision['decision_id'],action_id=request['action_id'],action_class='thread_message',scope=request['scope'],chat_task_id='new-'+fixture.PRODUCER)
        self.ready()
        with self.assertRaises(w.WorkflowError):self.queue()

    def test_cross_role_project_version_and_outbox_hash_still_reject(self):
        self.prepare()
        for changed in ({'sender_department':fixture.ASSISTANT},{'task_id':'wrong-original-task'},
                        {'candidate_version':'wrong-version'},{'result_sha256':'a'*64}):
            with self.subTest(changed=changed),self.assertRaises(w.WorkflowError):
                w.record_result_handoff(self.root,{**self.request,**changed})
        registry=w.read_json(self.root/'data/department-registry.json')
        next(x for x in registry['departments'] if x['id']==fixture.PRODUCER)['chat_binding']['project_id']='foreign'
        self.write('data/department-registry.json',registry)
        with self.assertRaises(w.WorkflowError):self.queue()

    def test_wrong_old_outbox_chat_is_not_replaced_from_new_ready(self):
        self.prepare();box=w.read_json(self.root/self.box['path']);box['fixed_chat_task_id']='another-role'
        self.box=self.write(self.box['path'],box);self.identity['result_sha256']=self.box['sha256'];self.ready()
        with self.assertRaises(w.WorkflowError):self.queue()

    def test_caller_provenance_flag_cannot_replace_actual_frozen_sources(self):
        self.prepare();self.request['original_rotation_continuation']={'fake':True}
        queued=self.queue();self.assertNotEqual(queued['original_rotation_continuation'],{'fake':True})
        self.assertEqual(queued['original_rotation_continuation']['assignment'],self.assignment)

    def test_claim_rechecks_queue_provenance_and_original_native(self):
        self.prepare();self.queue();(self.root/'reports/current-ready.json').write_text('{}')
        store=coordination.CoordinationStore(self.root);self.addCleanup(store.close)
        with self.assertRaises(w.WorkflowError):store.claim(self.identity,fixture.ASSISTANT,'current-A2','no-forged-claim')

    def test_actual_result_does_not_inherit_production_permission(self):
        self.prepare();self.queue();self.assertTrue(rotation.external_write_blocked(self.root,fixture.PRODUCER))
        with self.assertRaisesRegex(w.WorkflowError,'fresh exact production admission'):
            w.policy_check(self.root,department=fixture.PRODUCER,task_id=self.t.task_id,
                action_id='forbidden-production-after-result',action_class='site_publish',scope='company.example:production')


if __name__ == '__main__': unittest.main()
