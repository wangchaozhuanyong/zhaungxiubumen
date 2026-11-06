import hashlib
import unittest
from contextlib import ExitStack, nullcontext
from pathlib import Path
from unittest.mock import Mock, patch

from direct_handoff_readback import native_effect
import en2_serial_closeout as closeout


class DirectHandoffReadbackTests(unittest.TestCase):
    def setUp(self):
        self.body = 'task_id=original\nscope=exact\n'
        self.output = ('<codex_delegation>\n  <source_thread_id>hq</source_thread_id>\n'
                       f'  <input>{self.body}</input>\n</codex_delegation>')
        self.input = {'type': 'functionCallOutput', 'id': 'native-input',
                      'namespace': 'codex_app', 'name': 'send_message_to_thread', 'output': self.output}
        self.final = {'type': 'agentMessage', 'id': 'native-final', 'phase': 'final_answer', 'text': 'Done'}
        self.turn = {'id': 'original-turn', 'startedAt': 120, 'completedAt': 145,
                     'status': 'completed', 'items': [self.input, self.final]}

    def effect(self):
        return native_effect({'data': [self.turn]}, source_thread='hq', body=self.body, since=119)

    def test_actual_completed_raw_and_projected_representations(self):
        for output in (self.output, {'text': self.output, 'truncated': False}):
            with self.subTest(output=type(output)):
                self.input['output'] = output
                effect = self.effect()
                self.assertEqual(effect['state'], 'direct_final_observed')
                self.assertEqual(effect['final_sha256'], hashlib.sha256(b'Done').hexdigest())

    def test_unrelated_and_truncated_inputs_stay_unknown(self):
        for output in (self.output.replace('>hq<', '>elsewhere<'),
                       self.output.replace('scope=exact', 'scope=other'),
                       {'text': self.output, 'truncated': True}):
            with self.subTest(output=output):
                self.input['output'] = output
                self.assertEqual(self.effect()['state'], 'direct_effect_unknown')

    def test_native_xml_escaping_preserves_exact_prompt_identity(self):
        self.body += '参数 <request> & literal &lt;'
        self.input['output'] = self.output.replace(
            '</input>', '参数 &lt;request&gt; &amp; literal &amp;lt;</input>')
        self.assertEqual(self.effect()['state'], 'direct_final_observed')
        self.input['output'] = self.input['output'].replace('&amp;lt;', '&lt;')
        self.assertEqual(self.effect()['state'], 'direct_effect_unknown')

    def test_duplicate_input_stays_unknown(self):
        self.turn['items'].append({**self.input, 'id': 'duplicate'})
        self.assertEqual(self.effect()['state'], 'direct_effect_unknown')

    def test_invalid_chronology_stays_unknown(self):
        self.turn['startedAt'] = 118
        self.assertEqual(self.effect()['state'], 'direct_effect_unknown')

    def test_failed_turn_with_a_reply_stays_failed(self):
        self.turn.update(status='failed', error={'message': 'model unavailable'})
        self.assertEqual(self.effect()['state'], 'direct_turn_failed')

    def test_completed_turn_without_final_text_stays_input_only(self):
        self.final['text'] = ' '
        self.assertEqual(self.effect()['state'], 'direct_input_observed')

    def test_working_reply_is_visible_before_completion(self):
        self.turn.update(status='inProgress', completedAt=None)
        self.final['phase'] = 'commentary'
        self.assertEqual(self.effect()['state'], 'direct_reply_in_progress')


class En2SerialCloseoutTests(unittest.TestCase):
    def setUp(self):
        self.root = Path.cwd()
        self.record = {'assigned_next_original_window': closeout.PUBLISHER,
                       'assigned_next_action': closeout.RESERVATION, 'untouched': 'original'}
        self.pin = {'sha256': 'fixture'}
        self.effect = {'state': 'direct_final_observed', 'turn_id': closeout.TURN,
                       'intent_event_id': closeout.INTENT, 'task_id': closeout.TASK,
                       'action_id': closeout.ACTION, 'business_goal_closed': False, 'final_message_id': 'final'}
        self.result = {'task_id': closeout.TASK, 'completed_scope': 'original_EN2_two_fields_saved_and_publicly_verified',
                       'publish_run_id': 42170829866, 'publish_run_status': 'completed_success',
                       'permit_status': 'completed', 'target_matches_desired': True, 'protected37_preserved': True,
                       'MS11_preserved': True, 'public_rendered_title_and_excerpt': 'PASS_actual_browser_AX',
                       'business_parent_closed': False}
        self.history = Mock()
        self.history.call.side_effect = [{'thread': {}}, {'data': []}]
        stack = ExitStack()
        self.addCleanup(stack.close)
        for target, name, replacement in (
            (closeout.w, 'workflow_lock', lambda root: nullcontext()),
            (closeout.serial, '_root_serial_read', lambda root: (self.record.copy(), self.pin)),
            (closeout.serial, '_root_slot_read', lambda root: None),
            (closeout.serial, 'shared_serial_guard', lambda *args, **kwargs: {'new_activation_allowed': True, 'source': self.pin}),
            (closeout.direct, 'observe', lambda *args: self.effect),
            (closeout.serial, '_root_serial_native', lambda *args: ({}, {}, {'id': 'final'})),
            (closeout.serial, 'doc', lambda *args: self.result),
        ):
            stack.enter_context(patch.object(target, name, replacement))
        self.write = stack.enter_context(patch.object(closeout.w, 'atomic_write_json'))

    def test_clear_only_verified_reservation(self):
        self.assertEqual(closeout.close(self.root, self.history)['state'], 'completed_en2_reservation_reconciled')
        written = self.write.call_args.args[1]
        self.assertIsNone(written['assigned_next_original_window'])
        self.assertEqual(written['untouched'], 'original')
        self.assertEqual(written['en2_completed_direct_reservation']['assigned_next_action'], closeout.RESERVATION)

    def test_foreign_reservation_is_preserved(self):
        self.record['assigned_next_action'] = 'different original action'
        with self.assertRaises(closeout.w.WorkflowError):
            closeout.close(self.root, self.history)
        self.write.assert_not_called()

    def test_completed_message_without_public_proof_cannot_release(self):
        self.result['public_rendered_title_and_excerpt'] = 'UNKNOWN'
        with self.assertRaises(closeout.w.WorkflowError):
            closeout.close(self.root, self.history)
        self.write.assert_not_called()
