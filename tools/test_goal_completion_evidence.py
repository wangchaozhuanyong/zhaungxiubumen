"""Typed completion compatibility in isolated fixtures; no native writes or sends."""
import copy
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import goal_delivery_runtime as g
import workflow_control as w


class CompletionEvidenceTests(unittest.TestCase):
    def setUp(self):
        area = Path(__file__).resolve().parents[1] / '.test-tmp'
        area.mkdir(exist_ok=True)
        temp = tempfile.TemporaryDirectory(dir=area)
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.task = 'test-completion-evidence-compat'
        self.role = 'operations-assistant-2'
        self.scope = 'project:test:source-only'
        self.fixed = {'task_id': 'test-fixed-assistant', 'title': 'test-assistant',
                      'cwd': str(self.root), 'project_id': 'test-project'}
        self.write('data/department-registry.json', {'departments': [{
            'id': self.role, 'chat_binding': self.fixed,
            'coordination_authority': {'routine_decisions': True}}]})
        self.auth = self.write('logs/auth.json', {'fixture': 'no external authority'})
        self.snapshot = {'task_id': self.task, 'current_state': 'qa_passed',
                         'goal_delivery': {'responsible_assistant': self.role,
                                           'producer_departments': ['system-development'],
                                           'authorization_pin': self.auth}}
        self.req = {'requirement_id': 'source-actually-adopted', 'criterion_index': 1,
                    'requirement_type': 'source_adoption', 'scope': self.scope,
                    'subject': {'mode': 'latest_exact_accepted_result',
                                'producer_department': 'system-development'}}
        before = self.raw('backups/source.py', b'VALUE = 1\n')
        candidate = self.raw('working/source.py', b'VALUE = 2\n')
        self.raw('tools/source.py', b'VALUE = 2\n')
        (self.root / 'tools/source.py').chmod(0o644)
        self.manifest = self.write('logs/manifest.json', {'changes': [{
            'path': 'tools/source.py', 'candidate': candidate,
            'expected_source': before, 'mode': '0644'}], 'field_changes': []})
        self.accepted = {'state': 'PROVEN', 'identity': {'task_id': self.task,
            'sender_department': 'system-development', 'candidate_version': 'test-v2',
            'result_sha256': 'a' * 64}, 'source_fingerprint': 'b' * 64,
            'source_turn_id': 'test-producer-turn', 'scope': self.scope,
            'candidate': self.manifest, 'acceptance_receipt': {'fixture_only': True},
            'evidence': [self.manifest]}
        self.journal = {'state': 'adopted', 'actor': self.role, 'authorized_source': self.auth,
                        'candidate_fingerprint': self.accepted['source_fingerprint'],
                        'external_writes': 0, 'permissions_issued': False,
                        'candidate_manifest': self.manifest, 'source_operations': [{
                            'path': 'tools/source.py', 'before_sha256': before['sha256'],
                            'after_sha256': candidate['sha256'], 'backup': before}]}
        jp = self.write('logs/adoption.json', self.journal)
        self.text = jp['path'] + '\n' + jp['sha256'] + '\n' + self.manifest['sha256'] + '\n'
        self.output = self.raw('logs/output.txt', self.text.encode('utf-8'))
        self.command = {'type': 'commandExecution', 'id': 'test-cas-command',
                        'status': 'completed', 'exitCode': 0, 'cwd': str(self.root),
                        'command': 'test-only-local-adoption',
                        'output': {'text': self.text, 'truncated': False}}
        self.native = {'thread': {'id': self.fixed['task_id'], 'title': self.fixed['title'],
                                  'cwd': str(self.root), 'projectId': 'test-project'},
                       'turns': [{'id': 'test-assistant-final-turn', 'status': 'completed',
                                  'items': [self.command, {'type': 'agentMessage',
                                      'id': 'test-final', 'phase': 'final_answer', 'text': self.text}]}]}
        np = self.write('logs/native.json', self.native)
        self.proof = {'proof_type': 'source_adoption', 'identity': self.accepted['identity'],
                      'source_fingerprint': self.accepted['source_fingerprint'], 'scope': self.scope,
                      'journal': jp, 'actual_native_execution': np, 'native_execution_id': self.command['id'],
                      'execution_command': self.command['command'], 'execution_output': self.output,
                      'actual_native_completion': np, 'visible_reply': self.output,
                      'source_turn_id': 'test-assistant-final-turn', 'source_message_id': 'test-final'}
        self.proof_pin = self.write('logs/proof.json', self.proof)

    def write(self, path, value):
        w.atomic_write_json(self.root / path, value)
        return w.file_digest(self.root, path)

    def raw(self, path, value):
        p = self.root / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(value)
        return w.file_digest(self.root, path)

    def prove(self, *, committed=False):
        if committed:
            return w.goal_typed_completion_proof(self.root, self.snapshot, [], self.req, self.accepted)
        return w.goal_typed_completion_proof(self.root, self.snapshot, [], self.req, self.accepted,
                                             proof_pin=self.proof_pin)

    def refresh_native(self):
        pin = self.write('logs/native.json', self.native)
        self.proof.update(actual_native_execution=pin, actual_native_completion=pin)
        self.proof_pin = self.write('logs/proof.json', self.proof)

    def test_missing_selector_resolves_without_changing_frozen_requirement(self):
        original = copy.deepcopy(self.req)
        self.assertEqual(g.completion_proof_selector(self.req), {
            'mode': 'committed_completion_evidence', 'requirement_id': self.req['requirement_id']})
        self.assertEqual(self.req, original)
        self.assertEqual(self.prove()['state'], 'PROVEN')

    def test_native_dictionary_and_legacy_string_both_preserve_exact_output(self):
        for output in ({'text': self.text, 'truncated': False}, self.text):
            with self.subTest(shape=type(output).__name__):
                self.command['output'] = output
                self.refresh_native()
                result = self.prove()
                self.assertEqual(result['state'], 'PROVEN', result)
                self.assertFalse(result['business_goal_closed'])

    def test_missing_selector_is_missing_without_committed_effect(self):
        self.assertEqual(self.prove(committed=True)['state'], 'MISSING')

    def test_explicit_selector_never_falls_back_to_another_requirement(self):
        self.req['proof_ref'] = {'mode': 'committed_completion_evidence', 'requirement_id': 'foreign'}
        self.assertEqual(self.prove(committed=True)['state'], 'BLOCKED')
        self.req['proof_ref'] = self.write('logs/frozen-proof.json', {'wrong': 'proof'})
        self.assertEqual(self.prove()['state'], 'BLOCKED')
        self.req['proof_ref'] = {}
        self.assertIsNotNone(g.completion_proof_selector(self.req))
        self.assertEqual(self.prove()['state'], 'BLOCKED')
        self.assertEqual(self.prove(committed=True)['state'], 'MISSING')

    def test_non_effect_requirements_get_no_implicit_adoption_selector(self):
        for kind in ('accepted_delivery', 'execution_postcheck', 'unknown'):
            with self.subTest(kind=kind):
                self.assertIsNone(g.completion_proof_selector({**self.req, 'requirement_type': kind}))

    def test_output_missing_truncated_ambiguous_or_failed_is_rejected(self):
        original = copy.deepcopy(self.command)
        bad = [None, {}, {'text': self.text}, {'text': 1, 'truncated': False},
               {'text': self.text, 'truncated': True}, {'text': self.text, 'truncated': 0},
               {'text': self.text, 'truncated': False, 'other': 'ambiguous'}]
        for output in bad:
            with self.subTest(output=output):
                self.command['output'] = output
                self.refresh_native()
                self.assertEqual(self.prove()['state'], 'BLOCKED')
        self.command.update(original)
        for field in ('truncated', 'failed', 'superseded'):
            with self.subTest(field=field):
                self.command[field] = True
                self.refresh_native()
                self.assertEqual(self.prove()['state'], 'BLOCKED')
                del self.command[field]

    def test_command_identity_exit_cwd_and_output_bytes_remain_bound(self):
        original = copy.deepcopy(self.command)
        for changes in ({'id': 'other'}, {'exitCode': 1}, {'status': 'failed'},
                        {'cwd': '/other-project'}, {'command': 'other-command'},
                        {'output': {'text': self.text + 'changed', 'truncated': False}}):
            with self.subTest(changes=changes):
                self.command.clear(); self.command.update(original); self.command.update(changes)
                self.refresh_native()
                self.assertEqual(self.prove()['state'], 'BLOCKED')
        self.command.clear(); self.command.update(original)
        self.native['turns'][0]['items'].append(copy.deepcopy(self.command))
        self.refresh_native()
        self.assertEqual(self.prove()['state'], 'BLOCKED')

    def test_wrong_task_scope_fingerprint_and_missing_acceptance_are_rejected(self):
        original = copy.deepcopy(self.proof)
        for changes in ({'scope': 'foreign'}, {'source_fingerprint': 'c' * 64},
                        {'identity': {**self.accepted['identity'], 'task_id': 'other'}},
                        {'actual_native_completion': self.write('logs/no-final.json', {'thread': {}})}):
            with self.subTest(changes=changes):
                self.proof = {**original, **changes}
                self.proof_pin = self.write('logs/proof.json', self.proof)
                self.assertEqual(self.prove()['state'], 'BLOCKED')
        self.accepted['state'] = 'MISSING'
        self.assertEqual(self.prove()['state'], 'MISSING')

    def test_real_journal_readback_and_source_pin_stay_required(self):
        self.raw('tools/source.py', b'VALUE = 3\n')
        self.assertEqual(self.prove()['state'], 'BLOCKED')
        self.raw('tools/source.py', b'VALUE = 2\n')
        self.raw('backups/source.py', b'changed backup\n')
        self.assertEqual(self.prove()['state'], 'BLOCKED')

    def record_context(self):
        stack = __import__('contextlib').ExitStack()
        stack.enter_context(mock.patch.object(g, 'restore_goal', return_value=self.snapshot))
        stack.enter_context(mock.patch.object(g, 'enabled', return_value=True))
        stack.enter_context(mock.patch.object(w, '_validate_receipt_chain', return_value=([], [])))
        stack.enter_context(mock.patch.object(w, 'validate_workflow_events', return_value=[]))
        stack.enter_context(mock.patch.object(g, '_completion_contract', return_value={
            'state': 'declared', 'requirements': [self.req]}))
        stack.enter_context(mock.patch.object(w, 'goal_completion_subject', return_value=self.accepted))
        self.write(str(w.snapshot_path(self.root, self.task).relative_to(self.root)), self.snapshot)
        return stack

    def test_record_and_reader_use_same_pin_and_replay_has_no_new_event(self):
        with self.record_context():
            first = g.record_completion_evidence(self.root, self.task, 'logs/proof.json', self.role,
                                                 self.req['requirement_id'])
            before = (self.root / w.WORKFLOW_EVENTS).read_bytes()
            again = g.record_completion_evidence(self.root, self.task, 'logs/proof.json', self.role,
                                                 self.req['requirement_id'])
            self.assertEqual(first['result'], 'recorded')
            self.assertEqual(again['result'], 'duplicate_ignored')
            self.assertEqual(before, (self.root / w.WORKFLOW_EVENTS).read_bytes())
            result = self.prove(committed=True)
            self.assertEqual(result['state'], 'PROVEN', result)
            self.assertEqual(result['evidence'][0], self.proof_pin)

    def test_recorder_still_requires_assigned_role_and_current_independent_acceptance(self):
        with self.record_context():
            for role in ('operations', 'system-development'):
                with self.subTest(role=role), self.assertRaises(w.WorkflowError):
                    g.record_completion_evidence(self.root, self.task, 'logs/proof.json', role,
                                                 self.req['requirement_id'])
            self.accepted.pop('acceptance_receipt')
            with self.assertRaises(w.WorkflowError):
                g.record_completion_evidence(self.root, self.task, 'logs/proof.json', self.role,
                                             self.req['requirement_id'])


if __name__ == '__main__':
    unittest.main()
