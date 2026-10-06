"""Synthetic P1 regressions; do not constitute fixed QA or runtime adoption."""
import datetime as dt
import json
import unittest

import department_next_work as target
import workflow_control as w
import test_department_next_work as baseline


class ReworkTests(unittest.TestCase):
    setUp=baseline.WorkpackTests.setUp
    write=baseline.WorkpackTests.write
    update=baseline.WorkpackTests.update
    check=baseline.WorkpackTests.check
    queued=baseline.WorkpackTests.queued

    def assert_blocked(self, match):
        with self.assertRaisesRegex(w.WorkflowError,match):self.check()

    def rewrite_synthetic_box(self, change):
        """Generate a self-consistent legacy/wrong binding fixture, never real receipts."""
        path='logs/department-outbox/a.json';box=w.read_json(self.root/path)
        change(box);self.write(path,box);proof=w.file_digest(self.root,path)
        ledger=w.result_handoff_path(self.root,self.task)
        rows=[json.loads(line) for line in ledger.read_text().splitlines() if line]
        previous=''
        for row in rows:
            row.pop('record_hash',None);row['previous_hash']=previous
            if row['candidate_version']=='a-v1':row['outbox']=proof;row['result_sha256']=proof['sha256']
            row['record_hash']=w.sha256_value(row);previous=row['record_hash']
        ledger.write_text(''.join(json.dumps(row)+'\n' for row in rows),encoding='utf-8')

    def add_input(self):
        self.write('logs/inputs/source.json',{'synthetic':1})
        self.packet['continuation_plan']['steps'][0]['inputs']=[w.file_digest(self.root,'logs/inputs/source.json')]
        self.update()

    def test_missing_dispatch_time_rejected(self):
        self.dispatch.pop('created_at');self.assert_blocked('dispatch timestamp')

    def test_invalid_dispatch_time_rejected(self):
        self.dispatch['created_at']='not-a-time';self.assert_blocked('dispatch timestamp')

    def test_future_dispatch_and_ack_rejected(self):
        self.dispatch['created_at']=(self.now+dt.timedelta(minutes=1)).isoformat()
        self.ack['created_at']=(self.now+dt.timedelta(minutes=2)).isoformat()
        self.assert_blocked('dispatch timestamp')

    def test_missing_ack_time_rejected(self):
        self.ack.pop('created_at');self.assert_blocked('ACK timestamp')

    def test_invalid_ack_time_rejected(self):
        self.ack['created_at']='not-a-time';self.assert_blocked('ACK timestamp')

    def test_future_ack_rejected(self):
        self.ack['created_at']=(self.now+dt.timedelta(seconds=1)).isoformat()
        self.assert_blocked('ACK timestamp')

    def test_ack_time_before_dispatch_rejected(self):
        self.ack['created_at']=(self.now-dt.timedelta(minutes=2)).isoformat()
        self.assert_blocked('ACK timestamp')

    def test_latest_nonempty_ack_does_not_fall_back_to_earlier_good_ack(self):
        self.receipts.append(dict(self.ack,created_at=(self.now+dt.timedelta(seconds=1)).isoformat()))
        self.assert_blocked('ACK timestamp')

    def test_unrelated_future_ack_does_not_replace_fixed_ack(self):
        self.receipts.append(dict(self.ack,department='sales',created_at=(self.now+dt.timedelta(seconds=1)).isoformat()))
        self.assertEqual(self.check()['mode'],'CONTINUE_SCOPED_R0')

    def test_new_dispatch_cannot_reuse_ack_before_its_ledger_position(self):
        self.receipts.append(dict(self.dispatch,created_at=(self.now-dt.timedelta(seconds=5)).isoformat()))
        self.assert_blocked('nonempty fixed-chat ACK')

    def test_dispatch_ack_equal_now_valid(self):
        self.dispatch['created_at']=self.now.isoformat();self.ack['created_at']=self.now.isoformat()
        self.assertEqual(self.check()['mode'],'CONTINUE_SCOPED_R0')

    def test_exact_26_hour_expiry_valid_and_longer_rejected(self):
        at=w._parse_observed_at(self.dispatch['created_at'])
        self.packet['continuation_plan']['expires_at']=(at+dt.timedelta(hours=26)).isoformat();self.update()
        self.assertEqual(self.check()['mode'],'CONTINUE_SCOPED_R0')
        self.packet['continuation_plan']['expires_at']=(at+dt.timedelta(hours=26,seconds=1)).isoformat();self.update()
        self.assert_blocked('bounded expiry')

    def test_same_cv_different_scope_cannot_release_dependency(self):
        self.queued();self.packet['continuation_plan']['steps'][0]['scope']='different-page'
        self.packet['continuation_plan']['steps'][1]['depends_on']=['a'];self.update()
        self.assert_blocked('exact dispatched packet')

    def test_same_cv_different_kind_cannot_complete_step(self):
        self.queued();self.packet['continuation_plan']['steps'][0]['kind']='local_validation';self.update()
        self.assert_blocked('exact dispatched packet')

    def test_same_cv_different_output_directory_cannot_complete_step(self):
        self.queued();self.packet['continuation_plan']['steps'][0]['output_dir']+= '-changed';self.update()
        self.assert_blocked('exact dispatched packet')

    def test_same_cv_new_input_pin_cannot_complete_step(self):
        self.queued();self.add_input();self.assert_blocked('exact dispatched packet')

    def test_same_cv_changed_input_pin_cannot_complete_step(self):
        self.add_input();self.queued();self.write('logs/inputs/source.json',{'synthetic':2})
        self.packet['continuation_plan']['steps'][0]['inputs']=[w.file_digest(self.root,'logs/inputs/source.json')]
        self.update();self.assert_blocked('exact dispatched packet')

    def test_actual_input_bytes_changed_without_new_pin_rejected(self):
        self.add_input();self.write('logs/inputs/source.json',{'synthetic':2})
        self.assert_blocked('input bytes changed')

    def test_legacy_queued_result_without_binding_rejected(self):
        self.queued();self.rewrite_synthetic_box(lambda box:box.pop('step_binding'))
        self.assert_blocked('exact dispatched packet')

    def test_wrong_workpack_hash_in_frozen_result_rejected(self):
        self.queued();self.rewrite_synthetic_box(lambda box:box['step_binding'].update(workpack_sha256='0'*64))
        self.assert_blocked('exact dispatched packet')

    def test_wrong_step_fingerprint_in_frozen_result_rejected(self):
        self.queued();self.rewrite_synthetic_box(lambda box:box['step_binding'].update(step_sha256='0'*64))
        self.assert_blocked('exact dispatched packet')

    def test_cross_packet_expiry_change_with_identical_steps_still_requires_controller(self):
        self.queued();self.packet['continuation_plan']['expires_at']=(self.now+dt.timedelta(hours=2)).isoformat();self.update()
        self.assert_blocked('exact dispatched packet')

    def test_same_step_kind_scope_inputs_and_directory_are_in_fingerprint(self):
        self.add_input();answer=self.check();bind=answer['step_bindings']['a']
        expected=self.packet['continuation_plan']['steps'][0]
        for key in ('kind','scope','inputs','output_dir'):
            self.assertEqual(bind['step_identity'][key],expected[key])
        self.assertEqual(bind['step_sha256'],w.sha256_value(bind['step_identity']))

    def test_exact_result_recovers_without_repeat_output_or_new_queue(self):
        self.packet['continuation_plan']['steps'][1]['depends_on']=['a'];self.update();self.add_input();self.queued()
        ledger=w.result_handoff_path(self.root,self.task);before=ledger.read_bytes()
        a=self.check();b=self.check();self.assertEqual(a,b);self.assertEqual(a['next_step']['step_id'],'b')
        self.assertEqual(ledger.read_bytes(),before)

    def test_output_exists_but_queue_failed_is_recovery_only(self):
        step=self.packet['continuation_plan']['steps'][0]
        directory=self.root/step['output_dir'];directory.mkdir(parents=True)
        (directory/'synthetic-candidate.json').write_text('{"completed":true}')
        self.assertEqual(self.check()['mode'],'RECOVER_EXISTING_OUTPUT')
        self.assertEqual(self.check()['step_states']['a'],'not_reported')

    def test_partial_same_packet_still_allows_independent_step(self):
        self.queued(status='partial');self.assertEqual(self.check()['next_step']['step_id'],'b')

    def test_duplicate_input_pin_rejected(self):
        self.add_input();step=self.packet['continuation_plan']['steps'][0];step['inputs']*=2;self.update()
        self.assert_blocked('duplicate input pin')

    def test_input_missing_hash_or_non_array_rejected(self):
        step=self.packet['continuation_plan']['steps'][0]
        for value in ([{'path':'logs/inputs/source.json'}], 'source.json'):
            step['inputs']=value;self.update();self.assert_blocked('input')

    def test_documented_json_packet_and_result_match_real_parser(self):
        from pathlib import Path
        examples=Path(__file__).resolve().parents[1]/'examples'
        packet_raw=(examples/'packet.json').read_bytes();self.packet=json.loads(packet_raw)
        self.task=self.packet['task_id'];self.dep=self.packet['department'];self.path='logs/handoffs/example-packet.json'
        self.now=dt.datetime(2026,10,6,17,0,tzinfo=dt.timezone.utc)
        self.bind.update(task_id=self.packet['fixed_chat_task_id'],project_id=self.packet['project_id'],
                         last_health_check_at=self.now.isoformat())
        self.registry={self.dep:dict(chat_binding=self.bind,approved_subskills=[])}
        self.live['observed_at']=self.now.isoformat()
        self.live['threads'][0].update(id=self.bind['task_id'],projectId=self.bind['project_id'])
        self.live['sections'][0]['itemKeys']=['codex:thread:local:'+self.bind['task_id']]
        path=self.root/self.path;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(packet_raw)
        self.dispatch.update(department=self.dep,chat_task_id=self.bind['task_id'],
                             created_at=(self.now-dt.timedelta(minutes=1)).isoformat(),
                             evidence=[w.file_digest(self.root,self.path)])
        self.ack.update(department=self.dep,chat_task_id=self.bind['task_id'],created_at=(self.now-dt.timedelta(seconds=30)).isoformat())
        box_path='logs/department-outbox/example-step-a.json';f=self.root/box_path;f.parent.mkdir(parents=True,exist_ok=True)
        f.write_bytes((examples/'step-a-result.json').read_bytes());proof=w.file_digest(self.root,box_path)
        row=dict(task_id=self.task,event='notification_queued',sender_department=self.dep,
                 candidate_version='synthetic-step-a-v1',result_sha256=proof['sha256'],outbox=proof,previous_hash='')
        row['record_hash']=w.sha256_value(row);ledger=w.result_handoff_path(self.root,self.task)
        ledger.parent.mkdir(parents=True,exist_ok=True);ledger.write_text(json.dumps(row)+'\n')
        answer=self.check();self.assertEqual(answer['step_states']['a'],'done')
        self.assertEqual(answer['next_step']['step_id'],'b');self.assertFalse(answer['external_permission_issued'])

    def test_documented_noncompletion_statuses_keep_dependency_waiting(self):
        self.packet['continuation_plan']['steps'][1]['depends_on']=['a'];self.update();self.queued()
        for status in ('needs_input','blocked','failed','waiting_approval','partial'):
            with self.subTest(status=status):
                self.rewrite_synthetic_box(lambda box:box.update(status=status))
                answer=self.check();self.assertEqual(answer['step_states']['a'],'blocked_or_partial')
                self.assertEqual(answer['mode'],'RETURN_FOR_CONTROLLER_DECISION')


if __name__ == '__main__':
    unittest.main()
