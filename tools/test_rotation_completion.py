"""Scoped original completion readers; isolated fixtures never send or install."""
import copy
import json
from pathlib import Path
import unittest
from unittest import mock
import rotation_completion as c
import workflow_control as w
import goal_delivery_runtime as g
from test_goal_completion_evidence import CompletionEvidenceTests


class RotationCompletionTests(unittest.TestCase):
    def setUp(self):
        self.base = CompletionEvidenceTests('runTest')
        self.base.setUp(); self.addCleanup(self.base.doCleanups)
        self.root = self.base.root
        self.write, self.raw = self.base.write, self.base.raw
        self.snapshot = self.base.snapshot
        self.req = {**self.base.req, 'requirement_id': 'rotation-original-2'}
        goal = self.snapshot['goal_delivery']
        goal.update(primary_owner='system-development', authorized_scope=[self.base.scope], required_execution_actions=[])
        self.contract = self.write('logs/original-contract.json', {'goal_delivery': {
            'completion_requirements': [self.req, {**self.req, 'criterion_index': 0,
                'requirement_id': 'rotation-original-1', 'requirement_type': 'internal_pilot'}]}})
        self.snapshot['goal_contract'] = self.contract
        self.accepted = self.base.accepted
        self.before = w.file_digest(self.root, 'backups/source.py')
        original = self.write('logs/source-adoption-receipt.json', {'files': [{
            'path': 'tools/source.py', 'status': 'adopted', 'after_sha256': self.before['sha256'],
            'actual_after_sha256': self.before['sha256']}]})
        self.report = {'task_id': self.base.task, 'scope': self.base.scope,
                       'criteria': [{'status': 'PASS'}] * 4, 'evidence': [original],
                       'actual_PUB_continuation': {'action_id': 'test-original-action'}}
        self.report_pin = self.write('logs/independent-report.json', self.report)
        qa_box = self.write('logs/qa-box.json', {'evidence': [self.report_pin]})
        self.receipts = [{'receipt_id': c.QA_ID, 'receipt_hash': c.QA_HASH,
                         'receipt_type': 'qa_verdict', 'verdict': 'pass',
                         'department': 'operations-assistant-2', 'evidence': [qa_box]}]
        for name, value in [('TASK', self.base.task), ('SCOPE', self.base.scope),
                            ('CONTRACT', self.contract), ('AUTHORITY', self.base.auth), ('REPORT', self.report_pin)]:
            patch = mock.patch.object(c, name, value); patch.start(); self.addCleanup(patch.stop)
        candidate = w.file_digest(self.root, 'working/source.py')
        plan = self.write('logs/plan.json', [{'path': 'tools/source.py', 'expected': {
            **self.before, 'path': 'tools/source.py'}, 'candidate': candidate}])
        adoption = self.write('logs/adoption-successor.json', {'task_id': self.base.task,
            'production_permission_issued': False, 'adopted': [{
                'before': {**self.before, 'path': 'tools/source.py'}, 'candidate': candidate,
                'after': {**candidate, 'path': 'tools/source.py'}}]})
        self.accepted['producer_outbox'] = self.write('logs/producer.json', {'source_adoption': adoption})
        self.journal = {'schema': 'flashcast-rotation-SYS-adoption-chain/v1',
                        'runtime_task_id': self.base.task, 'actor': 'system-development',
                        'external_writes': 0, 'permissions_issued': False,
                        'successors': [{'plan': plan, 'journal': adoption, 'backups': [self.before]}]}
        self.proof = {**self.base.proof, 'identity': self.accepted['identity'],
                      'source_fingerprint': self.accepted['source_fingerprint']}

    def context(self, journal=None):
        return c.context(self.root, self.snapshot, self.receipts, self.req, self.accepted, journal or self.journal)

    def prove(self):
        jp = self.write('logs/rotation-journal.json', self.journal)
        self.proof['journal'] = jp
        text = jp['path'] + '\n' + jp['sha256'] + '\n'
        self.base.text = text
        self.base.native['turns'][0]['items'][-1]['text'] = text
        self.proof['actual_native_completion'] = self.write('logs/rotation-native.json', self.base.native)
        self.proof['visible_reply'] = self.raw('logs/rotation-reply.txt', text.encode())
        pin = self.write('logs/rotation-proof.json', self.proof)
        return w.goal_typed_completion_proof(self.root, self.snapshot, self.receipts, self.req,
                                             self.accepted, proof_pin=pin)

    def test_historical_reader_successor_requires_exact_before_and_backup(self):
        for path in ('tools/direct_system_repair.py', 'tools/test_direct_system_close.py'):
            before_raw=b'ISOLATED_EXISTING_SOURCE = 1\n';after_raw=b'ISOLATED_NEW_READER = 2\n'
            before=self.raw('backups/historical-before.py',before_raw)
            candidate=self.raw('working/historical-after.py',after_raw)
            self.raw(path,after_raw)
            plan=self.write('logs/historical-cas-plan.json',[{'path':path,'expected':{**before,'path':path},'candidate':candidate}])
            adoption=self.write('logs/historical-cas-adoption.json',{'task_id':c.TASK,'production_permission_issued':False,
                'adopted':[{'before':{**before,'path':path},'candidate':candidate,'after':{**candidate,'path':path}}]})
            accepted={'producer_outbox':self.write('logs/historical-producer.json',{'source_adoption':adoption})}
            journal=copy.deepcopy(self.journal)
            journal['successors'].append({'plan':plan,'journal':adoption,'backups':[before]})
            with mock.patch.object(c,'HISTORICAL_READ_SOURCE_BASES',{path:before['sha256']}):
                self.assertTrue(c.source_effect(self.root,accepted,journal,self.report))
                journal['successors'][-1]['backups']=[]
                with self.assertRaises(w.WorkflowError):c.source_effect(self.root,accepted,journal,self.report)
            journal['successors'][-1]['backups']=[before]
            with self.assertRaises(w.WorkflowError):c.source_effect(self.root,accepted,journal,self.report)
            (self.root/path).unlink()  # isolated fixture only; the next exact source starts independently

    def test_real_SYS_source_actor_preserved_and_original_contract_unchanged(self):
        before = copy.deepcopy(self.snapshot)
        result = self.prove()
        self.assertEqual(result['state'], 'PROVEN', result)
        self.assertFalse(result['business_goal_closed'])
        self.assertEqual(self.snapshot, before)
        self.assertEqual(self.journal['actor'], 'system-development')

    def test_original_task_authority_owner_and_requirement_cannot_be_replaced(self):
        for target, key, value in [(self.snapshot, 'task_id', 'foreign'),
                (self.snapshot['goal_delivery'], 'responsible_assistant', 'operations-assistant-3'),
                (self.snapshot['goal_delivery'], 'primary_owner', 'operations'),
                (self.snapshot['goal_delivery'], 'required_execution_actions', ['production']),
                (self.req, 'criterion_index', 3), (self.req, 'scope', 'foreign')]:
            original = target.get(key)
            with self.subTest(key=key):
                target[key] = value
                with self.assertRaises(w.WorkflowError): self.context()
            target[key] = original

    def test_old_independent_QA_is_required_but_never_upgraded_by_reader(self):
        for field, value in [('verdict', 'blocked'), ('receipt_hash', '0' * 64), ('receipt_id', 'foreign')]:
            original = self.receipts[0][field]; self.receipts[0][field] = value
            with self.subTest(field=field), self.assertRaises(w.WorkflowError): self.context()
            self.receipts[0][field] = original

    def test_wrong_accepted_identity_or_missing_acceptance_still_fails(self):
        self.accepted['state'] = 'MISSING'
        self.assertEqual(self.prove()['state'], 'MISSING')
        self.accepted['state'] = 'PROVEN'
        self.proof['identity'] = {**self.accepted['identity'], 'candidate_version': 'earlier'}
        self.assertEqual(self.prove()['state'], 'BLOCKED')

    def test_changed_source_or_missing_backup_cannot_be_called_adopted(self):
        self.raw('tools/source.py', b'changed\n')
        with self.assertRaises(w.WorkflowError): c.source_effect(self.root, self.accepted, self.journal, self.report)
        self.raw('tools/source.py', b'VALUE = 2\n')
        self.journal['successors'][0]['backups'] = []
        with self.assertRaises(w.WorkflowError): c.source_effect(self.root, self.accepted, self.journal, self.report)

    def test_tampered_candidate_and_reordered_CAS_are_rejected(self):
        self.raw('working/source.py', b'changed\n')
        self.assertEqual(self.prove()['state'], 'BLOCKED')
        self.raw('working/source.py', b'VALUE = 2\n')
        self.journal['successors'].append(copy.deepcopy(self.journal['successors'][0]))
        self.assertEqual(self.prove()['state'], 'BLOCKED')

    def test_source_effect_cannot_be_substituted_for_pilot(self):
        self.req.update(requirement_type='internal_pilot', criterion_index=0, requirement_id='rotation-original-1')
        self.proof['proof_type'] = 'internal_pilot'
        self.assertEqual(self.prove()['state'], 'BLOCKED')

    def test_new_scope_and_production_flags_remain_rejected(self):
        for field, value in [('external_writes', 1), ('external_writes', False),
                             ('permissions_issued', True), ('actor', 'operations-assistant-2')]:
            original = self.journal[field]; self.journal[field] = value
            with self.subTest(field=field): self.assertEqual(self.prove()['state'], 'BLOCKED')
            self.journal[field] = original

    def test_real_A2_native_confirmation_remains_required(self):
        self.prove()
        self.base.native['thread']['id'] = 'wrong-chat'
        self.assertEqual(self.prove()['state'], 'BLOCKED')

    def test_current_real_QA_can_confirm_journal_without_repeating_adoption(self):
        self.assertEqual(self.prove()['state'], 'PROVEN')
        jp = self.proof['journal']
        confirmation = {'department': self.base.role, 'qa_verdict': 'pass',
                        'candidate_version': self.accepted['identity']['candidate_version'], 'evidence': [jp]}
        cp = self.write('logs/current-independent-qa.json', confirmation)
        self.accepted.update(acceptance_outbox=cp, acceptance_receipt={'evidence': [cp]})
        self.base.native['thread']['id'] = 'wrong-chat'
        self.assertEqual(self.prove()['state'], 'PROVEN')
        confirmation['candidate_version'] = 'earlier'
        cp = self.write('logs/current-independent-qa.json', confirmation)
        self.accepted.update(acceptance_outbox=cp, acceptance_receipt={'evidence': [cp]})
        self.assertEqual(self.prove()['state'], 'BLOCKED')

    def pilot_fixture(self):
        native = self.write('logs/pilot-native.json', {'fixture': 'exact native validator tested separately'})
        ackpin = self.write('logs/pilot-ack.json', {'fixture': 'actual nonempty ACK'})
        assignment = {'task_id': 'existing-original-business', 'department': 'publishing',
                      'actual_native_invocation': native, 'source_call_id': 'test-native-call'}
        ap = self.write('logs/pilot-assignment.json', assignment)
        dispatch = {'receipt_id': 'test-dispatch', 'action_id': 'test-original-action',
                    'task_id': assignment['task_id'], 'department': 'publishing', 'scope': 'original-business',
                    'chat_task_id': 'current-publishing', 'policy_decision_id': 'test-allow'}
        ack = {**dispatch, 'receipt_id': 'test-ack', 'receipt_type': 'chat_ack',
               'ack_nonempty': True, 'evidence': [ackpin]}
        pilot = {'pilot_task_id': assignment['task_id'], 'actual_original_PUB_continuation': {
            'actual_assignment': ap, 'actual_native_source': native, 'native_send_call_id': 'test-native-call',
            'actual_ACK': ackpin, 'dispatch_receipt_id': 'test-dispatch', 'ACK_receipt_id': 'test-ack'},
            'existing_completed_SEO2_V4_delivery': {'received_record_id': 'test-intake',
                'result_sha256': 'a' * 64, 'native_turn_id': 'original-SEO-turn'}}
        pp = self.write('logs/original-pilot.json', pilot)
        journal = {'schema': 'flashcast-rotation-original-business-pilot/v1', 'original_pilot': pp}
        self.write('data/department-current-assignment.json', {'assignments': {'publishing': ap}})
        received = {'record_id': 'test-intake', 'event': 'controller_received',
                    'result_sha256': 'a' * 64, 'source_turn_id': 'original-SEO-turn'}
        patches = __import__('contextlib').ExitStack()
        patches.enter_context(mock.patch.object(c, 'PILOT', pp))
        patches.enter_context(mock.patch.object(w, '_validate_receipt_chain', return_value=([dispatch, ack], [])))
        patches.enter_context(mock.patch.object(w, 'validate_workflow_events', return_value=[]))
        patches.enter_context(mock.patch('goal_continuity._dispatch_source', return_value=({}, dispatch)))
        patches.enter_context(mock.patch.object(w, '_result_handoff_rows', return_value=[received]))
        patches.enter_context(mock.patch('scoped_candidate_adoption._committed'))
        self.addCleanup(patches.close)
        return journal, pilot, ack, received

    def test_existing_business_pilot_uses_actual_sources_without_parent_rewrite(self):
        journal, pilot, ack, received = self.pilot_fixture()
        self.assertEqual(len(c.pilot_effect(self.root, journal, self.report)), 4)
        self.assertNotIn('parent_task_id', pilot)

    def test_existing_pilot_requires_nonempty_exact_ACK(self):
        journal, pilot, ack, received = self.pilot_fixture()
        for key, value in [('ack_nonempty', False), ('scope', 'foreign'), ('policy_decision_id', 'other')]:
            original = ack[key]; ack[key] = value
            with self.subTest(key=key), self.assertRaises(w.WorkflowError):
                c.pilot_effect(self.root, journal, self.report)
            ack[key] = original

    def test_existing_pilot_requires_real_assignment_and_exact_SEO_native_turn(self):
        journal, pilot, ack, received = self.pilot_fixture()
        received['source_turn_id'] = 'invented-turn'
        with self.assertRaises(w.WorkflowError): c.pilot_effect(self.root, journal, self.report)
        received['source_turn_id'] = 'original-SEO-turn'
        self.write('data/department-current-assignment.json', {'assignments': {}})
        with self.assertRaises(w.WorkflowError): c.pilot_effect(self.root, journal, self.report)

    def test_pilot_source_replacement_or_fabricated_child_is_rejected(self):
        journal, pilot, ack, received = self.pilot_fixture()
        journal['original_pilot'] = self.write('logs/fabricated-child.json', {'pilot_task_id': 'new-child'})
        with self.assertRaises(w.WorkflowError): c.pilot_effect(self.root, journal, self.report)

    def test_source_reader_has_no_ledger_or_assignment_effect(self):
        before = {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        evidence = c.effect(self.root, self.snapshot, self.receipts, self.req, self.accepted, self.journal)
        self.assertTrue(evidence)
        after = {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        self.assertEqual(before, after)

    def test_normal_recorder_keeps_unique_A2_and_replays_without_new_event(self):
        self.assertEqual(self.prove()['state'], 'PROVEN')
        self.base.snapshot = self.snapshot; self.base.req = self.req; self.base.accepted = self.accepted
        with self.base.record_context(), mock.patch.object(w, '_validate_receipt_chain', return_value=(self.receipts, [])):
            first = g.record_completion_evidence(self.root, self.base.task, 'logs/rotation-proof.json',
                                                self.base.role, self.req['requirement_id'])
            before = (self.root / w.WORKFLOW_EVENTS).read_bytes()
            again = g.record_completion_evidence(self.root, self.base.task, 'logs/rotation-proof.json',
                                                self.base.role, self.req['requirement_id'])
            self.assertEqual(first['result'], 'recorded')
            self.assertEqual(again['result'], 'duplicate_ignored')
            self.assertEqual(before, (self.root / w.WORKFLOW_EVENTS).read_bytes())


if __name__ == '__main__':
    unittest.main()
