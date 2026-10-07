import datetime as dt
import contextlib
import io
import json
import unittest
from unittest import mock

import controller_stop_hook as hook


class StopHookTests(unittest.TestCase):
    def setUp(self):
        controller = mock.patch.object(hook, 'CONTROLLER', 'fixed-operations')
        project = mock.patch.object(hook, 'PROJECT', 'test-project')
        controller.start(); project.start()
        self.addCleanup(controller.stop); self.addCleanup(project.stop)
        self.now = dt.datetime(2026, 10, 6, 5, 0, tzinfo=dt.timezone.utc)
        self.event = {'hook_event_name': 'Stop', 'session_id': hook.CONTROLLER,
                      'cwd': str(hook.ROOT), 'stop_hook_active': False}
        self.state = {'project_id': hook.PROJECT, 'controller_thread_id': hook.CONTROLLER,
                      'cwd': str(hook.ROOT), 'updated_at': self.now.isoformat(),
                      'watched_tasks': [], 'ready_internal_actions': []}
        self.pending = {'pending_count': 0, 'followthrough_pending_count': 0}

    def check(self):
        return hook.decide(self.event, self.state, self.pending, self.now)

    def test_other_department_is_never_continued(self):
        self.event['session_id'] = '<LOCAL_TASK_ID>'
        self.pending['pending_count'] = 1
        self.assertEqual(self.check(), {})

    def test_other_project_is_never_continued(self):
        self.event['cwd'] = '<WEBSITE_PROJECT_ROOT>'
        self.pending['pending_count'] = 1
        self.assertEqual(self.check(), {})

    def test_interrupt_is_not_restarted(self):
        self.event['hook_event_name'] = 'Interrupt'
        self.pending['pending_count'] = 1
        self.assertEqual(self.check(), {})

    def test_delivery_needs_actual_intake(self):
        self.pending['pending_count'] = 1
        self.assertEqual(self.check()['decision'], 'block')

    def test_invalid_current_receipts_require_recovery_not_silent_stop(self):
        self.state['validation_errors'] = [{'reason': 'missing-current-ACK'}]
        self.assertEqual(self.check()['decision'], 'block')

    def test_unbound_installation_never_matches_an_empty_session(self):
        with mock.patch.object(hook, 'CONTROLLER', ''):
            self.assertEqual(hook.evaluate(dict(self.event, session_id='')), {})

    def test_decision_needs_real_next_action(self):
        self.pending['followthrough_pending_count'] = 1
        self.assertEqual(self.check()['decision'], 'block')

    def test_inflight_keeps_controller_waiting(self):
        self.state['watched_tasks'] = [{'task_id': 'original-v1', 'cursor': 'native:1'}]
        self.assertIn('wait_threads', self.check()['reason'])

    def test_prepared_is_not_dispatched(self):
        self.state['ready_internal_actions'] = [{'task_id': 'original-v1'}]
        self.assertEqual(self.check()['decision'], 'block')

    def test_external_wait_and_growth_target_allow_stop(self):
        self.state['external_waits'] = [{'task_id': 'facts-v1', 'owner': 'sales'}]
        self.state['IP_goal'] = 'DATA_MISSING'
        self.assertEqual(self.check(), {})

    def test_stale_state_demands_live_refresh_not_dispatch(self):
        self.state['updated_at'] = (self.now - dt.timedelta(minutes=6)).isoformat()
        self.state['watched_tasks'] = [{'task_id': 'original-v1'}]
        self.assertIn('先重新核实', self.check()['reason'])

    def test_repeated_stop_is_bounded(self):
        self.event['stop_hook_active'] = True
        self.pending['pending_count'] = 1
        a = self.check()
        self.assertEqual(a, self.check())
        self.assertEqual(a, {})

    def test_missing_identity_does_not_trap_user(self):
        del self.state['project_id']
        self.assertNotIn('decision', self.check())

    def test_repeated_stop_does_not_even_read_local_workflow(self):
        self.event['stop_hook_active'] = True
        loader = mock.Mock(side_effect=RuntimeError('must not be called'))
        self.assertEqual(hook.evaluate(self.event, loader, self.now), {})
        loader.assert_not_called()

    def test_malformed_state_and_queue_are_nonblocking(self):
        for state, pending in [(None, {}), ([], {}), ({}, []), (self.state, None)]:
            with self.subTest(state=state, pending=pending):
                output = hook.evaluate(self.event, lambda: (state, pending), self.now)
                self.assertNotIn('decision', output)
                self.assertIn('systemMessage', output)

    def test_malformed_watch_and_ready_are_nonblocking(self):
        for key in ['watched_tasks', 'ready_internal_actions']:
            for value in [None, 'bad', [None]]:
                with self.subTest(key=key, value=value):
                    state = dict(self.state, **{key: value})
                    output = hook.evaluate(self.event, lambda: (state, self.pending), self.now)
                    self.assertNotIn('decision', output)

    def test_workflow_error_is_nonblocking(self):
        from workflow_control import WorkflowError
        def broken():
            raise WorkflowError('controlled workflow failure')
        output = hook.evaluate(self.event, broken, self.now)
        self.assertNotIn('decision', output)
        self.assertIn('WorkflowError', output['systemMessage'])

    def test_missing_timestamp_requires_refresh_once(self):
        del self.state['updated_at']
        self.pending['pending_count'] = 1
        self.assertIn('观测时间缺失', self.check()['reason'])
        self.event['stop_hook_active'] = True
        self.assertEqual(self.check(), {})

    def test_invalid_stop_flag_is_nonblocking(self):
        for flag in [None, 'true', 1, [], {}]:
            with self.subTest(flag=flag):
                event = dict(self.event, stop_hook_active=flag)
                output = hook.evaluate(event, lambda: (self.state, self.pending), self.now)
                self.assertNotIn('decision', output)

    def test_invalid_stdin_exits_zero_with_json(self):
        for source in ['[]', 'null', '42', '"string"', '{bad']:
            with self.subTest(source=source):
                output = io.StringIO()
                with mock.patch('sys.stdin', io.StringIO(source)), contextlib.redirect_stdout(output):
                    self.assertEqual(hook.main(), 0)
                parsed = json.loads(output.getvalue())
                self.assertIsInstance(parsed, dict)
                self.assertNotIn('decision', parsed)


if __name__ == '__main__':
    unittest.main()
