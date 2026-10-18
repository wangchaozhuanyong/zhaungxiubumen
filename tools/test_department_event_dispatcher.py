import datetime as dt
import json
from pathlib import Path
import select
import tempfile
import subprocess
import unittest
from unittest import mock

import department_event_dispatcher as d


RESULT = {'task_id': 'original-result-v1', 'sender_department': 'producer',
          'candidate_version': 'immutable-v1', 'result_sha256': 'a' * 64}


class Transport:
    def __init__(self):
        self.state = 'idle'
        self.calls = []
        self.effects = {}
        self.fail_after_effect = False
        self.become_busy = False

    def status(self, role):
        return self.state

    def recover(self, role, event, expected_identity):
        return self.effects.get(event)

    def wake(self, role, event, value):
        if self.become_busy:
            return None
        self.calls.append((role, event, value))
        self.effects[event] = 'actual-turn-1'
        if self.fail_after_effect:
            raise ConnectionError('response lost after acceptance')
        return self.effects[event]


class QueueTransport:
    queues_busy_recipient = True

    def __init__(self):
        self.calls = []
        self.fail_prepare = False
        self.fail_after_effect = False
        self.effects = {}

    def status(self, role):
        raise AssertionError('queue transport must not guess busy/idle')

    def prepare(self, role, event, value):
        if self.fail_prepare:
            raise d.DispatchError('exact policy refused')
        return role, event, value

    def enqueue(self, prepared):
        self.calls.append(prepared)
        self.effects[prepared[1]] = 'actual-completed-input-turn'
        if self.fail_after_effect:
            raise subprocess.TimeoutExpired('official queue', 30)
        return {'message_id': 'native-queue-message-id'}

    def recover(self, role, event, value):
        return self.effects.get(event)


class DispatcherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = d.Store(self.root)
        self.event = self.store.put(RESULT, 'assistant')
        self.transport = Transport()

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def test_idle_one_wakeup_and_duplicate_resume(self):
        worker = d.Dispatcher(self.store, self.transport)
        worker.pump()
        self.store.put(RESULT, 'assistant')
        worker.pump()
        self.assertEqual(len(self.transport.calls), 1)
        self.assertEqual(self.store.rows()[0]['state'], 'wake_acknowledged')

    def test_busy_then_completion_event_continues(self):
        self.transport.state = 'active'
        worker = d.Dispatcher(self.store, self.transport)
        worker.pump()
        self.assertFalse(self.transport.calls)
        self.assertEqual(self.store.rows()[0]['state'], 'waiting_recipient')
        self.transport.state = 'idle'
        worker.pump()  # supplied native completion event, not a timer
        self.assertEqual(len(self.transport.calls), 1)

    def test_transport_absent_retains_pending(self):
        d.Dispatcher(self.store).pump()
        self.assertEqual(self.store.rows()[0]['state'], 'waiting_transport')
        self.assertFalse(self.transport.calls)

    def test_disconnect_after_send_recovers_without_second_send(self):
        self.transport.fail_after_effect = True
        d.Dispatcher(self.store, self.transport).pump()
        self.assertEqual(self.store.rows()[0]['state'], 'uncertain')
        self.store.close()
        self.store = d.Store(self.root)
        d.Dispatcher(self.store, self.transport).pump()
        self.assertEqual(self.store.rows()[0]['state'], 'wake_acknowledged')
        self.assertEqual(len(self.transport.calls), 1)

    def test_crash_after_intent_no_blind_retry(self):
        self.store.set(self.event, 'sending')
        d.Dispatcher(self.store, self.transport).pump()
        self.assertEqual(self.store.rows()[0]['state'], 'uncertain')
        self.assertFalse(self.transport.calls)

    def test_race_becomes_busy_retains_original(self):
        self.transport.become_busy = True
        d.Dispatcher(self.store, self.transport).pump()
        self.assertEqual(self.store.rows()[0]['state'], 'waiting_recipient')
        self.assertFalse(self.transport.calls)

    def test_target_change_refused(self):
        with self.assertRaises(d.DispatchError):
            self.store.put(RESULT, 'different-assistant')

    def test_resolved_intake_never_reawakens(self):
        self.store.set(self.event, 'resolved_by_original_intake')
        d.Dispatcher(self.store, self.transport).pump()
        self.assertFalse(self.transport.calls)

    def test_invalid_or_deleted_source_does_not_wake_stored_event(self):
        d.Dispatcher(self.store, self.transport).pump(valid_events=set())
        self.assertEqual(self.store.rows()[0]['state'], 'waiting_valid_source')
        self.assertFalse(self.transport.calls)
        d.Dispatcher(self.store, self.transport).pump(valid_events={self.event})
        self.assertEqual(len(self.transport.calls), 1)

    def test_one_invalid_event_does_not_block_other_result(self):
        other = self.store.put({**RESULT, 'candidate_version': 'second-valid'}, 'assistant')
        d.Dispatcher(self.store, self.transport).pump(valid_events={other})
        self.assertEqual(len(self.transport.calls), 1)
        self.assertEqual(self.transport.calls[0][1], other)

    def test_real_workflow_validation_failure_is_isolated_during_ingest(self):
        import workflow_control as workflow
        directory = self.root / 'logs/result-notifications'
        directory.mkdir(parents=True)
        bad = {**RESULT, 'candidate_version': 'bad-source'}
        (directory / 'bad.json').write_text(json.dumps({'identity': bad}))
        (directory / 'good.json').write_text(json.dumps({'identity': RESULT}))
        with mock.patch.object(d, 'validate_notification', side_effect=[
                workflow.WorkflowError('exact source mismatch'), (RESULT, 'assistant', False)]):
            valid, errors = d.ingest(self.root, self.store, {d.key(bad): bad, self.event: RESULT})
        self.assertEqual(valid, {self.event})
        self.assertEqual(len(errors), 1)
        self.assertFalse(errors[0]['blocks_other_events'])

    def test_future_admission_uses_native_queue_time_not_edited_transport_time(self):
        import workflow_control as workflow
        import result_coordination as rc
        (self.root/'data').mkdir()
        (self.root/d.CONFIG).write_text(json.dumps({'admit_new_goal_results_since':'2026-10-16T00:00:00Z'}))
        record={'identity':RESULT,'queued_at':'2026-10-16T00:01:00Z'}
        original={**RESULT,'event':'notification_queued','created_at':'2026-10-15T00:01:00Z'}
        with mock.patch.object(workflow,'_result_handoff_rows',return_value=[original]):
            self.assertFalse(d.admitted_result(self.root,record,{}))
        original['created_at']='2026-10-16T00:01:00Z'
        with mock.patch.object(workflow,'_result_handoff_rows',return_value=[original]), \
                mock.patch.object(rc,'result_lane',return_value={'lane':'professional_acceptance'}), \
                mock.patch.object(d,'binding',return_value={'task_id':'original-fixed'}):
            self.assertTrue(d.admitted_result(self.root,record,{}))
        with mock.patch.object(workflow,'_result_handoff_rows',return_value=[original]), \
                mock.patch.object(rc,'result_lane',return_value={'lane':'legacy_unmapped'}):
            with self.assertRaisesRegex(d.DispatchError,'authenticated goal'):
                d.admitted_result(self.root,record,{})

    def test_single_service_owner(self):
        with d.exclusive_service(self.root):
            with self.assertRaises(d.DispatchError):
                with d.exclusive_service(self.root):
                    pass

    def test_partial_failed_and_rework_all_keep_identity(self):
        for version in ['complete', 'partial', 'rework', 'blocked', 'failed']:
            self.store.put({**RESULT, 'candidate_version': version}, 'assistant')
        d.Dispatcher(self.store, self.transport).pump()
        self.assertEqual(len(self.transport.calls), 6)
        self.assertTrue(all(call[2]['task_id'] == RESULT['task_id'] for call in self.transport.calls))

    def test_official_queue_retains_message_not_turn_and_never_checks_idle(self):
        transport = QueueTransport()
        worker = d.Dispatcher(self.store, transport)
        worker.pump(valid_events={self.event})
        worker.pump(valid_events={self.event})
        row = self.store.rows()[0]
        self.assertEqual(len(transport.calls), 1)
        self.assertEqual(row['state'], 'native_queue_accepted')
        self.assertEqual(row['native_message_id'], 'native-queue-message-id')
        self.assertIsNone(row['turn_id'])

    def test_existing_background_process_is_not_started_again(self):
        with mock.patch.object(d,'native_queue_capability',return_value='/valid/cli'), \
                mock.patch.object(d,'background_status',return_value={'running':True,'pid':123}), \
                mock.patch.object(d.subprocess,'Popen') as spawn:
            self.assertTrue(d.background_start(self.root)['duplicate_start_ignored'])
            spawn.assert_not_called()

    def test_reused_pid_for_unrelated_process_is_not_stopped(self):
        with mock.patch.object(d,'background_status',return_value={'running':False,'pid':123}), \
                mock.patch.object(d.os,'kill') as kill:
            self.assertFalse(d.background_stop(self.root)['stop_requested'])
            kill.assert_not_called()

    def test_queue_timeout_recovers_exact_effect_without_requeue(self):
        transport = QueueTransport()
        transport.fail_after_effect = True
        worker = d.Dispatcher(self.store, transport)
        worker.pump()
        self.assertEqual(self.store.rows()[0]['state'], 'uncertain')
        worker.pump()
        self.assertEqual(len(transport.calls), 1)
        self.assertEqual(self.store.rows()[0]['turn_id'], 'actual-completed-input-turn')

    def test_unknown_queue_effect_is_not_retried_after_restart(self):
        self.store.set(self.event, 'sending')
        transport = QueueTransport()
        worker = d.Dispatcher(self.store, transport)
        worker.pump()
        worker.pump()
        self.assertEqual(self.store.rows()[0]['state'], 'uncertain')
        self.assertFalse(transport.calls)

    def test_refused_policy_never_queues_and_other_results_continue(self):
        transport = QueueTransport()
        transport.fail_prepare = True
        d.Dispatcher(self.store, transport).pump()
        self.assertFalse(transport.calls)
        self.assertEqual(self.store.rows()[0]['state'], 'waiting_policy_or_source')

    def test_official_queue_runs_exact_cli_and_rejects_wrong_thread_ack(self):
        transport = object.__new__(d.OfficialQueueTransport)
        transport.root, transport.cli = self.root, '/exact/bundled/codex'
        thread = '00000000-0000-0000-0000-000000000001'
        message = 'frozen text with $(literal shell bytes)'
        prepared = {'directory': self.root, 'thread_id': thread, 'message': message,
                    'payload_sha256': 'a' * 64, 'policy_decision_id': 'exact-policy'}
        result = subprocess.CompletedProcess([], 0,
            'Queued message 00000000-0000-0000-0000-000000000002 for thread ' + thread + '.\n', '')
        with mock.patch.object(d.subprocess, 'run', return_value=result) as run:
            self.assertEqual(transport.enqueue(prepared)['message_id'], '00000000-0000-0000-0000-000000000002')
            self.assertEqual(run.call_args.args[0], [transport.cli, 'queue', '--thread', thread, '--message', message])
            self.assertNotIn('shell', run.call_args.kwargs)
        result.stdout = result.stdout.replace(thread, '00000000-0000-0000-0000-000000000099')
        with mock.patch.object(d.subprocess, 'run', return_value=result):
            with self.assertRaisesRegex(d.DispatchError, 'uncertain'):
                transport.enqueue(prepared)

    def test_queue_recovery_matches_exact_original_bytes_only(self):
        transport = object.__new__(d.OfficialQueueTransport)
        transport.root, transport.history = self.root, mock.Mock()
        wanted = transport.message('assistant', self.event, RESULT)
        transport.history.call.return_value = {'data': [
            {'id': 'wrong-prefix', 'items': [{'type': 'userMessage', 'content': [{'type': 'text', 'text': wanted + '\nextra'}]}]},
            {'id': 'exact-turn', 'items': [{'type': 'userMessage', 'content': [{'type': 'text', 'text': wanted}]}]}]}
        with mock.patch.object(d, 'binding', return_value={'task_id': 'original-fixed'}):
            self.assertEqual(transport.recover('assistant', self.event, RESULT), 'exact-turn')
        self.assertEqual(transport.history.call.call_args.args[0], 'thread/turns/list')

    def test_queue_history_identity_is_checked_and_not_used_as_live_status(self):
        transport = object.__new__(d.OfficialQueueTransport)
        transport.root, transport.history = self.root, mock.Mock()
        expected = {'task_id': 'original-fixed', 'title': 'fixed', 'cwd': str(self.root)}
        raw = {'id': 'original-fixed', 'name': 'fixed', 'cwd': str(self.root), 'status': {'type': 'notLoaded'}}
        transport.history.call.side_effect = [{'thread': raw}, {'data': [{'id': 'persisted', 'status': 'completed'}]}]
        with mock.patch.object(d, 'binding', return_value=expected):
            result = transport._read('assistant')
        self.assertEqual(result['thread']['title'], 'fixed')
        self.assertEqual(result['raw_thread_response']['thread'], raw)
        self.assertEqual([v.args[0] for v in transport.history.call.call_args_list], ['thread/read', 'thread/turns/list'])

    def test_history_only_server_cannot_claim_shared_runtime(self):
        rpc = mock.Mock()
        expected = {'task_id': 'hq', 'title': 'fixed', 'cwd': str(self.root)}
        rpc.call.return_value = {'thread': {'id': 'hq', 'name': 'fixed', 'cwd': str(self.root),
                                            'status': {'type': 'notLoaded'}}}
        transport = d.SharedTransport(self.root, rpc)
        proof = {'role': 'operations', 'thread_id': 'hq', 'status': 'active',
                 'observed_at': dt.datetime.now(dt.timezone.utc).isoformat()}
        with mock.patch.object(d, 'binding', return_value=expected):
            with self.assertRaisesRegex(d.DispatchError, 'does not share'):
                transport.verify(proof)
        self.assertFalse(transport.verified)
        self.assertEqual(rpc.call.call_count, 1)

    def test_wakeup_is_typed_tool_output_and_no_permissions(self):
        rpc = mock.Mock()
        expected = {'task_id': 'assistant-id', 'title': 'fixed', 'cwd': str(self.root)}
        thread = {'id': 'assistant-id', 'name': 'fixed', 'cwd': str(self.root), 'status': {'type': 'idle'}}
        rpc.call.side_effect = [{'thread': thread}, {'thread': thread}, {'thread': thread},
                                {'turn': {'id': 'new-native-turn'}}]
        transport = d.SharedTransport(self.root, rpc)
        transport.verified = True
        with mock.patch.object(d, 'binding', return_value=expected):
            self.assertEqual(transport.wake('assistant', self.event, RESULT), 'new-native-turn')
        method, params = rpc.call.call_args.args
        self.assertEqual(method, 'turn/start')
        self.assertEqual(params['input'], [])
        payload = json.loads(params['toolOutput']['output'])
        self.assertEqual(params['toolOutput']['namespace'], 'flashcast_dispatcher')
        self.assertFalse(payload['permission_granted'])
        self.assertFalse(payload['result_received_claimed'])

    def test_recovery_rejects_same_event_with_wrong_original_identity(self):
        rpc = mock.Mock()
        thread = {'id': 'assistant-id', 'name': 'fixed', 'cwd': str(self.root), 'status': {'type': 'idle'}}
        payload = {'schema': 'flashcast-result-wakeup/v1', 'event_key': self.event,
                   'receiver': 'assistant', 'identity': {**RESULT, 'candidate_version': 'wrong'},
                   'permission_granted': False}
        item = {'type': 'functionCallOutput', 'name': 'frozen_result_ready',
                'namespace': 'flashcast_dispatcher', 'output': json.dumps(payload)}
        rpc.call.side_effect = [{'thread': thread}, {'data': [{'id': 'wrong-turn', 'items': [item]}]}]
        transport = d.SharedTransport(self.root, rpc)
        transport.verified = True
        with mock.patch.object(d, 'binding', return_value={'task_id': 'assistant-id', 'title': 'fixed', 'cwd': str(self.root)}):
            self.assertIsNone(transport.recover('assistant', self.event, RESULT))

    def test_paths_cannot_escape_project(self):
        for path in ['../bad', '/tmp/bad']:
            with self.assertRaises(d.DispatchError):
                d.inside(self.root, path)

    @unittest.skipUnless(hasattr(select, 'kqueue'), 'macOS event backend required')
    def test_real_file_event_and_atomic_replacement(self):
        directory = self.root / 'events'
        directory.mkdir()
        watched = directory / 'result.json'
        watched.write_text('{}')
        watcher = d.VnodeEvents([directory])
        try:
            replacement = directory / 'replacement.tmp'
            replacement.write_text('{"frozen":true}')
            replacement.replace(watched)
            self.assertTrue(watcher.wait(timeout=2))
            watched.write_text('{"frozen":false}')
            self.assertTrue(watcher.wait(timeout=2))
        finally:
            watcher.close()

    @unittest.skipUnless(hasattr(select, 'kqueue'), 'macOS event backend required')
    def test_actual_intake_jsonl_append_is_an_event_without_chat_polling(self):
        directory=self.root/'intake';directory.mkdir()
        journal=directory/'original-task.jsonl';journal.write_text('{}\n')
        watcher=d.VnodeEvents([directory])
        try:
            with journal.open('a') as stream:stream.write('{"event":"controller_received"}\n')
            self.assertTrue(watcher.wait(timeout=2))
        finally:watcher.close()


if __name__ == '__main__':
    unittest.main()
