import copy
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from en2_preview_web_identity import _desktop_live_turn
from en2_preview_normal import build_and_record_preflight, prepare_and_selfcheck
from en2_preview_github_evidence import _get
import en2_preview_history as history
import workflow_control as workflow


class DesktopLiveTurnTests(unittest.TestCase):
    def setUp(self):
        self.binding = {'thread_id': 'original-web', 'host_id': 'local', 'title': 'WEB',
                        'cwd': '/website', 'project_id': 'original-project'}
        self.live_turn = {'id': 'current-turn', 'status': 'inProgress',
                          'startedAt': 100, 'completedAt': None}
        self.live_thread = {'id': 'original-web', 'hostId': 'local', 'title': 'WEB',
                            'cwd': '/website', 'kind': 'codex', 'status': {'type': 'active'}}
        self.read = {'type': 'mcpToolCall', 'server': 'codex_app', 'tool': 'read_thread',
                     'status': 'completed', 'startedAtMs': 103000, 'completedAtMs': 104000,
                     'arguments': {'threadId': 'original-web', 'hostId': 'local', 'turnLimit': 1}}
        self.history = {**self.live_turn, 'status': 'interrupted',
                        'items': [{'id': 'anchor', 'completedAtMs': 102000}, self.read]}

    def verify(self, now=110000):
        payload = {'thread': self.live_thread, 'turns': [self.live_turn]}
        self.read['result'] = {'content': [{'type': 'text', 'text': json.dumps(payload)}]}
        return _desktop_live_turn(self.history, self.binding, 'anchor', now)

    def test_authentic_same_turn_can_resolve_history_projection(self):
        self.assertTrue(self.verify())

    def test_expired_or_wrong_chronology_is_rejected(self):
        self.assertFalse(self.verify(now=224001))
        self.read['startedAtMs'] = 101000
        self.assertFalse(self.verify())

    def test_wrong_window_or_turn_is_rejected(self):
        self.live_thread['cwd'] = '/other-website'
        self.assertFalse(self.verify())
        self.live_thread['cwd'] = '/website'
        self.live_turn['id'] = 'other-turn'
        self.assertFalse(self.verify())

    def test_newer_interruption_does_not_fall_back_to_active_read(self):
        self.assertTrue(self.verify())
        interrupted = copy.deepcopy(self.read)
        self.live_turn['status'] = 'interrupted'
        self.verify()
        self.history['items'] = [self.history['items'][0], interrupted, self.read]
        self.assertFalse(self.verify())

    def test_completed_history_cannot_be_overridden_by_live_read(self):
        self.history['completedAt'] = 105
        self.assertFalse(self.verify())

    def test_build_and_record_uses_one_full_validation(self):
        with TemporaryDirectory() as path:
            root = Path(path)
            (root / 'request.json').write_text('{}', encoding='utf-8')
            with patch('en2_preview_normal._verify', return_value=({}, {}, {})) as verify, \
                 patch('en2_preview_normal._commit_preflight', return_value={'result': 'recorded'}) as commit:
                result = build_and_record_preflight(root, 'request.json', 'turn', 'command', 'preflight.json')
            self.assertEqual(result, {'result': 'recorded'})
            verify.assert_called_once()
            commit.assert_called_once()
            saved = json.loads((root / 'preflight.json').read_text(encoding='utf-8'))
            self.assertEqual(saved, commit.call_args.args[2])
            self.assertEqual(saved['web_selfcheck_command'], 'command')

    def test_prepare_selfcheck_constructs_request_once(self):
        with TemporaryDirectory() as path:
            root = Path(path)
            (root / 'state.json').write_text('{"main_sha":"example"}', encoding='utf-8')
            request = {'state': {'main_sha': 'example'}}
            context = {'decision': {'sha256': 'reviewed'}}
            with patch('en2_preview_entry._verified_request', return_value=(request, None, None, context)) as verify, \
                 patch('en2_preview_normal._selfcheck_result', return_value={'permission_issued': False}) as output:
                result = prepare_and_selfcheck(root, 'state.json', 'request.json')
            verify.assert_called_once_with(root, history.TASK, request['state'])
            self.assertEqual(json.loads((root / 'request.json').read_text()), request)
            self.assertEqual(output.call_args.args[0]['path'], 'request.json')
            self.assertEqual(output.call_args.args[1], context)
            self.assertFalse(result['permission_issued'])

    def test_combined_preflight_passes_only_its_verified_context_to_policy_commit(self):
        with TemporaryDirectory() as path:
            root = Path(path)
            (root / 'request.json').write_text('{}', encoding='utf-8')
            context = {'authorization': {'path': 'original'}}
            with patch('en2_preview_normal._verify', return_value=({}, {}, context)) as verify, \
                 patch('en2_preview_normal._commit_preflight', return_value={'result': 'recorded'}) as commit:
                build_and_record_preflight(root, 'request.json', 'turn', 'command', 'preflight.json',
                                           consume_preview_policy=True)
            verify.assert_called_once()
            self.assertEqual(commit.call_args.kwargs, {'policy_context': context})

    def test_github_get_retries_only_once_after_timeout(self):
        timeout = subprocess.TimeoutExpired('gh', 8)
        with patch('en2_preview_github_evidence.subprocess.run',
                   side_effect=[timeout, subprocess.CompletedProcess('gh', 0, b'{"total_count":0}')]) as run:
            self.assertEqual(_get('pending'), {'total_count': 0})
        self.assertEqual([call.kwargs['timeout'] for call in run.call_args_list], [8, 12])
        with patch('en2_preview_github_evidence.subprocess.run', side_effect=timeout) as run:
            with self.assertRaises(subprocess.TimeoutExpired):
                _get('pending')
        self.assertEqual(run.call_count, 2)

    def test_reconciliation_keeps_policy_in_ledger_and_excludes_it_from_dispatch(self):
        policy = {'decision_id': 'original', 'status': 'allow'}
        retired = {'policy_id': 'original', 'policy_sha256': workflow.sha256_value(policy),
                   'effect': 'NO_DISPATCH_INTENT_AND_NO_HOSTED_RUN', 'external_permission_issued': False}
        events = [{'details': {history.RECONCILED: retired}}]
        with patch.object(workflow, 'read_jsonl', side_effect=[[], [policy], events]), \
             patch.object(workflow, 'validate_workflow_events', return_value=[]):
            self.assertEqual(history.unresolved_preview_policies(Path('/project')), [])
        self.assertEqual(policy['status'], 'allow')
        retired['policy_sha256'] = 'unrelated'
        with patch.object(workflow, 'read_jsonl', side_effect=[[], [policy], events]), \
             patch.object(workflow, 'validate_workflow_events', return_value=[]):
            with self.assertRaises(workflow.WorkflowError):
                history.unresolved_preview_policies(Path('/project'))

    def test_only_exact_refused_forward_receipt_can_admit_one_successor(self):
        root = Path('/project')
        original = {'preview': {'run_id': 42041137937}}
        prior = {'path': 'existing-preview-intent', 'sha256': 'unchanged'}
        successor = {
            'original_intent': prior, 'forward_refusal': history.REFUSAL,
            'preview': {'run_id': history.REFUSAL_RUN,
                        'preview_origin': 'VERIFIED_HISTORICAL_ZERO_WRITE',
                        'actual_action_allowed': False},
            'external_permission_issued': False,
        }
        event = {'details': {history.SUCCESSOR: successor}}
        with patch.object(history, '_refresh_from_events', return_value=original), \
             patch.object(workflow, 'read_jsonl', return_value=[event]) as events, \
             patch.object(workflow, 'validate_workflow_events', return_value=[]), \
             patch.object(workflow, 'file_digest', return_value=prior), \
             patch.object(history.a, 'document', return_value={'preview_run': history.REFUSAL_RUN}):
            self.assertEqual(history.retired_receipts(root), [original, successor])
            self.assertTrue(history.intent_path(root).name.endswith('-forward-receipt-repair-once.json'))
            successor['preview']['run_id'] += 1
            with self.assertRaises(workflow.WorkflowError):
                history.retired_receipts(root)
            successor['preview']['run_id'] = history.REFUSAL_RUN
            events.return_value = [event, event]
            with self.assertRaises(workflow.WorkflowError):
                history.retired_receipts(root)

    def test_en2_policy_filter_keeps_other_decisions_and_checks_original_spent_bytes(self):
        root = Path('/project')
        spent = {'decision_id': history.PREISSUE_POLICY, 'status': 'allow'}
        current = {'decision_id': 'current', 'status': 'allow'}
        record = {'retired_cms_policy_sha256': workflow.sha256_value(spent)}
        with patch.object(workflow, 'read_jsonl', return_value=[spent, current]), \
             patch.object(history, 'retired_receipts', return_value=[{}, {}, record]):
            self.assertEqual(history.live_cms_policy_rows(root), [current])
            spent['status'] = 'changed'
            with self.assertRaises(workflow.WorkflowError):
                history.live_cms_policy_rows(root)
