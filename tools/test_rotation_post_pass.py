"""Isolated complete normal-entry integration; synthetic native pages, no sends.

No mocks of bind_plan, verdict/receipt validators, subject reader, proof reader,
completion recorder, native queue validation or committed intake validation.
Only fixed original evidence constants are redirected to each isolated fixture.
"""
import copy
import contextlib
import io
import sys
import runpy
import datetime as dt
import hashlib
import json
from pathlib import Path
import unittest
from unittest import mock
import workflow_control as w
import qa_review_plan as q
import goal_delivery_runtime as g
import goal_continuity as continuity
import result_coordination as coordination
import rotation_completion as c
import test_goal_runtime_consumers as fixture
import test_goal_continuity as assignment_fixture


class RotationPostPassTests(unittest.TestCase):
    def setUp(self):
        area = Path(__file__).resolve().parents[1] / '.test-tmp'
        area.mkdir(parents=True, exist_ok=True)
        for patch in (mock.patch.object(fixture, 'TMP', area),
                      mock.patch.object(fixture, 'PRODUCER', 'system-development')):
            patch.start(); self.addCleanup(patch.stop)
        self.t = fixture.GoalRuntimeConsumerTests('runTest')
        self.t.setUp(); self.addCleanup(self.t.doCleanups)
        self.root = self.t.root
        registry = w.read_json(self.root / 'data/department-registry.json')
        row = copy.deepcopy(next(row for row in registry['departments'] if row['id'] == 'content-organic-website'))
        row.update(id='system-development', name='system-development', new_dispatch_enabled=True)
        row['chat_binding'].update(task_id='fixed-system-development', title='system-development')
        registry['departments'].append(row); w.atomic_write_json(self.root / 'data/department-registry.json', registry)
        self.pilot_pin, pub_action = self.existing_business()
        self.t.task_id = c.TASK
        self.goal = self.t.make_goal(primary_owner='system-development', producer_departments=['system-development'],
            authorized_scope=[c.SCOPE], source_mode='approved_dispatch', completion_kind='internal_delivery',
            completion_criteria=['source recovery', 'actual SYS adoption', 'negative gates', 'original continuation'],
            completion_requirements=[{'criterion_index': i, 'requirement_id': 'rotation-original-' + str(i + 1),
                'requirement_type': kind, 'scope': c.SCOPE,
                'subject': {'mode': 'latest_exact_accepted_result', 'producer_department': 'system-development'}}
                for i, kind in enumerate(('internal_pilot', 'source_adoption', 'accepted_delivery', 'accepted_delivery'))])
        self.goal['human_authorization']['executor'] = 'system-development'
        contract_path = self.t.write('reports/original-runtime-goal.json', self.goal)
        g.initialize_goal(self.root, c.TASK, contract_path)
        self.t.fixture.task_id = c.TASK; self.t.fixture.routing_decisions = {}
        self.t.initial_assignment()
        request = self.t.requested(sender='operations', target='system-development', scope=c.SCOPE)
        policy = self.t.policy(request); self.assertEqual(policy['status'], 'allow', policy.get('reason'))
        self.t.fixture.receipt('dispatch_sent', 'system-development', 'producer-original-dispatch',
            policy_decision_id=policy['decision_id'], action_id=request['action_id'],
            action_class='thread_message', scope=c.SCOPE)
        self.t.fixture.receipt('chat_ack', 'system-development', 'producer-original-ack')
        snapshot = self.t.snapshot()
        for name, value in [('CONTRACT', snapshot['goal_contract']), ('AUTHORITY', snapshot['goal_delivery']['authorization_pin']),
                            ('PILOT', self.pilot_pin)]:
            patch = mock.patch.object(c, name, value); patch.start(); self.addCleanup(patch.stop)
        source = self.root / 'tools/local-synthetic-source.py'; source.parent.mkdir(exist_ok=True)
        source.write_text('SYNTHETIC_FIXTURE = 1\n')
        sha = w.file_digest(self.root, 'tools/local-synthetic-source.py')['sha256']
        self.baseline = self.pin('reports/initial/source-adoption-receipt.json', {'files': [{
            'path': 'tools/local-synthetic-source.py', 'status': 'adopted',
            'after_sha256': sha, 'actual_after_sha256': sha}]})
        self.report = self.pin('reports/original-four-criterion-report.json', {'task_id': c.TASK, 'scope': c.SCOPE,
            'criteria': [{'status': 'PASS'}] * 4, 'evidence': [self.baseline],
            'actual_PUB_continuation': {'action_id': pub_action}})
        patch = mock.patch.object(c, 'REPORT', self.report); patch.start(); self.addCleanup(patch.stop)
        self.old_pin, _ = self.producer('v7')
        self.old_plan = self.t.review_plan(self.old_pin)
        path = self.t.write('reports/v7-review-plan.json', self.old_plan)
        q.bind_plan(self.root, task_id=c.TASK, plan_path=path, coordinator_role=fixture.ASSISTANT)
        self.old_binding = copy.deepcopy(self.t.snapshot()['qa_review_plan'])
        self.old_qa = self.t.assistant_verdict(self.old_plan, self.old_pin,
            evidence=[self.old_binding['pin'], self.old_pin, self.report])
        for name, value in [('QA_ID', self.old_qa['receipt_id']), ('QA_HASH', self.old_qa['receipt_hash'])]:
            patch = mock.patch.object(c, name, value); patch.start(); self.addCleanup(patch.stop)
        self.source_journal = self.pin('logs/department-outbox/SOURCE-JOURNAL-PREPARED-v10.json', {
            'schema': 'flashcast-rotation-SYS-adoption-chain/v1', 'runtime_task_id': c.TASK,
            'actor': 'system-development', 'external_writes': 0, 'permissions_issued': False, 'successors': []})
        self.pilot_journal = self.pin('logs/department-outbox/PILOT-JOURNAL-PREPARED-v10.json', {
            'schema': 'flashcast-rotation-original-business-pilot/v1', 'runtime_task_id': c.TASK,
            'original_pilot': self.pilot_pin, 'external_writes': 0, 'permissions_issued': False})
        self.current_pin, self.current_receipt = self.producer('v10')
        self.identity, self.queue = self.queue_result('v10', self.current_pin)
        self.intake = self.receive(self.identity, self.queue)
        self.plan = self.t.review_plan(self.current_pin)
        self.plan['action_id'] = 'review-current-completion-stage-v10'
        self.stage = {'schema_version': 1, 'prior_plan': self.old_binding['pin'],
                      'prior_pass_receipt_id': self.old_qa['receipt_id'],
                      'producer_outbox_receipt_id': self.current_receipt['receipt_id'],
                      'queue_record_id': self.queue['record_id'], 'intake_record_id': self.intake['record_id'],
                      'remaining_requirement_ids': ['rotation-original-1', 'rotation-original-2']}
        self.plan['original_rotation_remaining_stage'] = self.stage

    def pin(self, path, value):
        return w.file_digest(self.root, self.t.write(path, value))

    def producer(self, version):
        draft = self.pin('reports/' + self.t.task_id + '/' + version + '-candidate.json', {
            'task_id': self.t.task_id, 'department': 'system-development', 'candidate_version': version})
        box = self.t.result_box('system-development', version, draft)
        box.update(scope=self.t.snapshot()['goal_delivery']['authorized_scope'][0])
        if hasattr(self, 'baseline'): box['source_adoption'] = self.baseline
        path = self.t.write('logs/department-outbox/' + ('outbox-v10.json' if version == 'v10'
                            else self.t.task_id + '-' + version + '.json'), box)
        receipt = self.t.fixture.receipt('outbox_received', 'system-development', 'producer-result-' + version, evidence=path)
        return w.file_digest(self.root, path), receipt

    def queue_result(self, version, pin, *, ready=False):
        identity = {'task_id': self.t.task_id, 'sender_department': 'system-development',
                    'candidate_version': version, 'result_sha256': pin['sha256']}
        text = self.t.task_id + ' Synthetic complete result ' + version
        if ready:
            text += '\nFLASHCAST_DELIVERY_READY ' + json.dumps({**identity, 'outbox_path': pin['path'], 'batch_complete': True})
        prefix = 'reports/' + self.t.task_id + '/' + version
        reply = self.root / (prefix + '-reply.txt'); reply.parent.mkdir(parents=True, exist_ok=True); reply.write_text(text)
        native = {'thread': {'id': 'fixed-system-development'}, 'turns': [{
            'id': version + '-native-turn', 'status': 'completed', 'error': None,
            'completedAt': dt.datetime.now(dt.timezone.utc).timestamp(),
            'items': [{'id': version + '-final', 'type': 'agentMessage', 'phase': 'final_answer', 'text': text}]}]}
        if ready:
            binding = w.department_registry(self.root)['system-development']['chat_binding']
            native['thread'].update(title=binding['title'], cwd=binding['cwd'])
            native['turns'][0].update(status='inProgress', startedAt=dt.datetime.now(dt.timezone.utc).timestamp() - 1)
            native['turns'][0]['items'][0]['phase'] = 'commentary'
        np = self.pin(prefix + '-native.json', native)
        request = {**identity, 'event': 'notification_queued', 'idempotency_key': 'queue-' + version,
            'outbox_path': pin['path'], 'source_thread_id': 'fixed-system-development',
            'source_turn_id': version + '-native-turn', 'source_reply_sha256': hashlib.sha256(text.encode()).hexdigest(),
            'reply_observed_at': dt.datetime.now(dt.timezone.utc).isoformat(),
            'actual_native_completion': np, 'visible_reply': w.file_digest(self.root, prefix + '-reply.txt')}
        if ready:
            request.update(result_source_phase='delivery_ready', source_message_id=version + '-final')
        queued, _ = w.record_result_handoff(self.root, request)
        return identity, queued

    def receive(self, identity, queue):
        store = coordination.CoordinationStore(self.root); self.addCleanup(store.close)
        owner = fixture.ASSISTANT + ':fixed-' + fixture.ASSISTANT
        claim = store.claim(identity, fixture.ASSISTANT, owner, 'claim-' + identity['candidate_version'])
        request = {**identity, 'event': 'controller_received', 'outbox_path': queue['outbox']['path'],
            'idempotency_key': 'receive-' + identity['candidate_version'], 'intake_mode': 'queue',
            'source_thread_id': queue['source_thread_id'], 'source_reply_sha256': queue['source_reply_sha256'],
            'reply_observed_at': dt.datetime.now(dt.timezone.utc).isoformat(),
            'coordinator_role': fixture.ASSISTANT, 'coordinator_owner': owner, 'coordination_claim': claim}
        return w.record_result_handoff(self.root, request)[0]

    def existing_business(self):
        self.t.task_id = 'synthetic-existing-original-business-v1'
        goal = self.t.make_goal(primary_owner='system-development', producer_departments=['system-development'],
                                authorized_scope=['project:synthetic-original-business:v1'])
        goal['human_authorization']['executor'] = 'system-development'
        path = self.t.write('reports/original-business-goal.json', goal)
        g.initialize_goal(self.root, self.t.task_id, path)
        self.t.fixture.task_id = self.t.task_id; self.t.fixture.routing_decisions = {}
        assignment = assignment_fixture.ContinuityTests('runTest'); assignment.t = self.t; assignment.root = self.root
        item, ap = assignment.assignment(role='system-development', initialize=False)
        continuity.record_assignment(self.root, item, ap)
        dispatch = next(row for row in w.read_jsonl(w.receipts_path(self.root, self.t.task_id))
                        if row['receipt_id'] == item['dispatch_receipt_id'])
        ackpin = self.pin('reports/original-business-actual-ack.json', {'thread': {'id': 'fixed-system-development'},
            'turns': [{'id': 'actual-ACK-turn', 'items': [{'type': 'agentMessage', 'text': 'Synthetic nonempty original ACK'}]}]})
        ack = self.t.fixture.receipt('chat_ack', 'system-development', 'business-exact-ACK',
            evidence=ackpin['path'], **{key: dispatch[key] for key in ('action_id', 'action_class', 'scope', 'policy_decision_id')})
        pp, _ = self.producer('existing-v4'); identity, queue = self.queue_result('existing-v4', pp)
        received = self.receive(identity, queue)
        pilot = {'pilot_task_id': self.t.task_id, 'actual_original_PUB_continuation': {
            'dispatch_receipt_id': dispatch['receipt_id'], 'ACK_receipt_id': ack['receipt_id'],
            'actual_assignment': ap, 'actual_native_source': item['actual_native_invocation'],
            'native_send_call_id': item['source_call_id'], 'actual_ACK': ackpin},
            'existing_completed_SEO2_V4_delivery': {'received_record_id': received['record_id'],
                'result_sha256': pp['sha256'], 'native_turn_id': queue['source_turn_id']}}
        return self.pin('reports/original-existing-business-pilot.json', pilot), dispatch['action_id']

    def bind(self):
        path = self.t.write(getattr(self, 'prepared_plan_path', 'reports/current-review-plan.json'), self.plan)
        output = io.StringIO()
        argv = ['qa_review_plan.py', '--project-root', str(self.root), '--task-id', c.TASK,
                '--plan', path, '--coordinator-role', fixture.ASSISTANT]
        with mock.patch.object(sys, 'argv', argv), contextlib.redirect_stdout(output):
            code = q.main()
        result = json.loads(output.getvalue())
        if code: raise w.WorkflowError(result.get('reason', 'normal CLI refused'))
        return result

    def complete_stage(self):
        self.assertEqual(self.t.snapshot()['current_state'], 'qa_passed')
        receipts = w._validate_receipt_chain(self.root, c.TASK)[0]
        self.assertEqual(w.goal_completion_subject(self.root, self.t.snapshot(), receipts,
            {'mode': 'latest_exact_accepted_result', 'producer_department': 'system-development'})['state'], 'BLOCKED')
        self.assertEqual(self.bind()['result'], 'recorded')
        binding = self.t.snapshot()['qa_review_plan']
        verdict = self.t.assistant_verdict(self.plan, self.current_pin,
            evidence=[binding['pin'], self.current_pin, self.report, self.source_journal, self.pilot_journal])
        self.assertEqual(verdict['verdict'], 'pass')
        receipts, invalid = w._validate_receipt_chain(self.root, c.TASK)
        self.assertEqual(invalid, [])
        self.assertIn({key: value for key, value in self.old_qa.items() if key not in ('result', 'workflow_state')}, receipts)
        accepted = w.goal_completion_subject(self.root, self.t.snapshot(), receipts,
            {'mode': 'latest_exact_accepted_result', 'producer_department': 'system-development'})
        self.assertEqual(accepted['state'], 'PROVEN', accepted)
        self.assertEqual(accepted['producer_outbox'], self.current_pin)
        prepared = self.input_preparer('completion') if hasattr(self, 'input_preparer') else None
        for rid, kind, journal in [('rotation-original-1', 'internal_pilot', self.pilot_journal),
                                    ('rotation-original-2', 'source_adoption', self.source_journal)]:
            proof = {'proof_type': kind, 'identity': accepted['identity'], 'scope': c.SCOPE,
                     'source_fingerprint': accepted['source_fingerprint'], 'journal': journal}
            path = (next(row['proof']['path'] for row in prepared['prepared_not_registered'] if row['requirement_id'] == rid)
                    if prepared else self.t.write('reports/' + rid + '-proof.json', proof))
            result = g.record_completion_evidence(self.root, c.TASK, path, fixture.ASSISTANT, rid)
            self.assertEqual(result['result'], 'recorded')
            self.assertEqual(g.record_completion_evidence(self.root, c.TASK, path, fixture.ASSISTANT, rid)['result'], 'duplicate_ignored')
        obligations = g.completion_obligations(self.root, self.t.snapshot())
        self.assertEqual([row['state'] for row in obligations['requirements']], ['PROVEN'] * 4, obligations)
        self.assertTrue(obligations['business_goal_closed'])
        self.assertEqual(w.reconcile_workflow(self.root, task_id=c.TASK)[0]['current_state'], 'closed')
        self.assertEqual(w.effective_approvals(self.root), {})

    def test_normal_PASS_receive_bind_accept_both_typed_records_and_close(self):
        self.complete_stage()

    def test_delivered_input_preparer_normal_CLI_acceptance_and_both_records(self):
        script = (Path(w.__file__).resolve().parents[1] / c.BASE / 'runtime-migration/post-pass-admission-v10/PREPARE-A2-INPUTS-v10.py')
        if not script.is_file():
            self.skipTest('Native company delivery preparer is not part of the public source package')
        namespace = runpy.run_path(str(script))
        self.input_preparer = namespace['prepare']
        self.input_preparer.__globals__.update(ROOT=self.root, HERE=self.root / 'logs/department-outbox')
        prepared = self.input_preparer('plan')
        self.prepared_plan_path = prepared['prepared_not_bound']['path']
        self.plan = w.read_json(self.root / self.prepared_plan_path)
        self.stage = self.plan['original_rotation_remaining_stage']
        command = prepared['normal_bind_command']
        self.assertEqual(command[:3], ['python3', 'tools/qa_review_plan.py', '--task-id'])
        self.complete_stage()

    def test_committed_READY_with_later_ACK_keeps_original_prefix_and_completes(self):
        self.current_pin, self.current_receipt = self.producer('ready-successor')
        self.identity, self.queue = self.queue_result('ready-successor', self.current_pin, ready=True)
        self.intake = self.receive(self.identity, self.queue)
        self.stage.update(producer_outbox_receipt_id=self.current_receipt['receipt_id'],
                          queue_record_id=self.queue['record_id'], intake_record_id=self.intake['record_id'])
        self.plan = self.t.review_plan(self.current_pin)
        self.plan.update(action_id='review-current-READY-completion', original_rotation_remaining_stage=self.stage)
        with mock.patch.object(w, 'utc_timestamp', return_value=dt.datetime.now(dt.timezone.utc).isoformat()):
            self.t.fixture.receipt('chat_ack', 'system-development', 'later-accurate-source-ACK')
        # A committed READY source retains its exact authenticated prefix;
        # later ACK bookkeeping must not invalidate the original final.
        w._validate_goal_completed_result(self.root, self.queue, 'fixed-system-development')
        self.complete_stage()

    def test_plain_plan_still_cannot_reopen_PASS(self):
        del self.plan['original_rotation_remaining_stage']
        with self.assertRaisesRegex(w.WorkflowError, 'PASS cannot reopen'): self.bind()

    def test_repeated_binding_does_not_append_or_replace_old_PASS(self):
        self.bind(); paths = [self.root / w.WORKFLOW_EVENTS, w.receipts_path(self.root, c.TASK)]
        before = [p.read_bytes() for p in paths]
        self.assertEqual(self.bind()['result'], 'duplicate_ignored')
        self.assertEqual(before, [p.read_bytes() for p in paths])

    def test_missing_or_unrelated_actual_intake_is_rejected(self):
        self.stage['intake_record_id'] = 'no-real-intake'
        with self.assertRaisesRegex(w.WorkflowError, 'committed intake'): self.bind()

    def test_older_producer_result_never_replaces_latest(self):
        self.producer('v11')
        with self.assertRaisesRegex(w.WorkflowError, 'latest actual producer'): self.bind()

    def test_wrong_original_pass_and_remaining_selector_are_rejected(self):
        for key, value in [('prior_pass_receipt_id', 'fabricated-pass'),
                           ('remaining_requirement_ids', ['rotation-original-3'])]:
            original = self.stage[key]; self.stage[key] = value
            with self.subTest(key=key), self.assertRaises(w.WorkflowError): self.bind()
            self.stage[key] = original

    def test_forged_queue_or_tampered_native_completion_is_rejected(self):
        self.stage['queue_record_id'] = 'not-the-actual-source'
        with self.assertRaises(w.WorkflowError): self.bind()
        self.stage['queue_record_id'] = self.queue['record_id']
        (self.root / self.queue['actual_native_completion']['path']).write_text('{}')
        with self.assertRaises(w.WorkflowError): self.bind()

    def test_original_scope_reviewer_and_production_guards_remain(self):
        for key, value in [('scope', 'project:foreign'), ('reviewer_department', 'operations-assistant-3'),
                           ('production_write_allowed', True)]:
            old = self.plan[key]; self.plan[key] = value
            with self.subTest(key=key), self.assertRaises(w.WorkflowError): self.bind()
            self.plan[key] = old

    def test_incompatible_rework_or_foreign_stage_cannot_be_combined(self):
        for key in ('rework_of', 'post_pass_remaining_stage', 'owner_direct_review'):
            self.plan[key] = {}
            with self.subTest(key=key), self.assertRaises(w.WorkflowError): self.bind()
            del self.plan[key]

    def test_rejected_binding_preserves_plan_receipts_and_event_bytes(self):
        paths = [w.snapshot_path(self.root, c.TASK), w.receipts_path(self.root, c.TASK), self.root / w.WORKFLOW_EVENTS]
        before = [p.read_bytes() for p in paths]
        self.stage['prior_pass_receipt_id'] = 'invented'
        with self.assertRaises(w.WorkflowError): self.bind()
        self.assertEqual(before, [p.read_bytes() for p in paths])

    def test_only_original_A2_can_bind_this_remaining_stage(self):
        path = self.t.write('reports/current-review-plan.json', self.plan)
        with self.assertRaisesRegex(w.WorkflowError, 'original assigned assistant'):
            q.bind_plan(self.root, task_id=c.TASK, plan_path=path, coordinator_role='operations')

    def test_existing_review_source_requires_exact_real_base_and_backup(self):
        path = 'tools/qa_review_plan.py'
        (self.root / path).write_text('SYNTHETIC_BEFORE = 1\n')
        before = w.file_digest(self.root, path)
        backup_path = self.root / 'reports/review-before.py'; backup_path.write_bytes((self.root / path).read_bytes())
        backup = w.file_digest(self.root, 'reports/review-before.py')
        (self.root / path).write_text('SYNTHETIC_AFTER = 2\n')
        candidate_path = self.root / 'reports/review-after.py'; candidate_path.write_bytes((self.root / path).read_bytes())
        candidate = w.file_digest(self.root, 'reports/review-after.py')
        plan = self.pin('reports/fixture-cas-plan.json', [{'path': path, 'expected': before, 'candidate': candidate}])
        adoption = self.pin('reports/fixture-cas-adoption.json', {'task_id': c.TASK,
            'production_permission_issued': False, 'adopted': [{
                'before': before, 'candidate': candidate, 'after': w.file_digest(self.root, path)}]})
        box = self.pin('reports/fixture-adoption-subject.json', {'source_adoption': adoption})
        journal = {'schema': 'flashcast-rotation-SYS-adoption-chain/v1', 'actor': 'system-development',
                   'successors': [{'plan': plan, 'journal': adoption, 'backups': [backup]}]}
        report = c.document(self.root, self.report)
        with mock.patch.object(c, 'REVIEW_SOURCE_BASE', before['sha256']):
            self.assertTrue(c.source_effect(self.root, {'producer_outbox': box}, journal, report))
            journal['successors'][0]['backups'] = []
            with self.assertRaises(w.WorkflowError): c.source_effect(self.root, {'producer_outbox': box}, journal, report)
        with mock.patch.object(c, 'REVIEW_SOURCE_BASE', '0' * 64), self.assertRaises(w.WorkflowError):
            c.source_effect(self.root, {'producer_outbox': box}, journal, report)


if __name__ == '__main__':
    unittest.main()
