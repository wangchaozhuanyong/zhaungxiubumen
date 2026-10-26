"""Isolated recovery and admission checks; these fixtures are not live sends."""
import copy
import datetime as dt
import json
from pathlib import Path
import unittest
from unittest import mock
import goal_source_recovery as recovery
import goal_continuity as continuity
import goal_delivery_runtime as runtime
import workflow_control as w
import managed_cms_permit_issuer as cms
import test_goal_runtime_consumers as fixture


class OfficialQueueAssignmentTests(unittest.TestCase):
    setUp=fixture.GoalRuntimeConsumerTests.setUp
    write=fixture.GoalRuntimeConsumerTests.write
    initialize=fixture.GoalRuntimeConsumerTests.initialize
    make_goal=fixture.GoalRuntimeConsumerTests.make_goal
    snapshot=fixture.GoalRuntimeConsumerTests.snapshot
    requested=fixture.GoalRuntimeConsumerTests.requested

    def queued(self, department=fixture.ASSISTANT):
        registry=w.read_json(self.root/'data/department-registry.json')
        for row in registry['departments']:
            if row['id']==department:
                row['chat_binding']['task_id']='11111111-1111-4111-8111-111111111111'
        w.atomic_write_json(self.root/'data/department-registry.json',registry)
        self.initialize();goal=self.snapshot()['goal_delivery'];contract=self.snapshot()['goal_contract']
        payload='reports/queued-assignment.txt'
        (self.root/payload).write_text(self.task_id+' contract '+contract['path'])
        request=self.requested(sender='operations',target=department,
                               scope=goal['authorized_scope'][0],payload=w.file_digest(self.root,payload))
        fixed=w.department_registry(self.root)[department]['chat_binding']
        source=w.department_registry(self.root)['operations']['chat_binding']
        now=dt.datetime.now(dt.timezone.utc)-dt.timedelta(seconds=1)
        native=self.write('reports/queue-target.json',{'thread':{'id':fixed['task_id'],
            'title':fixed['title'],'cwd':fixed['cwd']},'turns':[{'status':'inProgress'}]})
        request.update(action_id=('assign-goal-review:' if department==fixture.ASSISTANT else 'HQ-producer:')+self.task_id,delivery_mode='official_native_queue',
            assignment_record_required=True,authorization_changes=[],actual_target_state=w.file_digest(self.root,native))
        with mock.patch('department_event_dispatcher.native_queue_capability',return_value='/fixture/cli'), \
                mock.patch.object(w,'utc_timestamp',return_value=(now-dt.timedelta(seconds=10)).isoformat()):
            prepared=recovery.prepare_message(self.root,request)
        self.assertEqual(prepared['status'],'ready_to_queue',prepared)
        rp=self.write('reports/original-prepare.json',request)
        pp=self.write('reports/original-prepared-result.json',prepared)
        qid='22222222-2222-4222-8222-222222222222'
        intent={'started_at':now.isoformat(),'thread_id':fixed['task_id'],
            'payload_sha256':request['payload_sha256'],'policy_decision_id':prepared['policy_decision']['decision_id'],
            'transport':'official_codex_queue','intake_claimed':False}
        ip=self.write('reports/original-queue/native-queue-intent.json',intent)
        result={**intent,'finished_at':now.isoformat(),'exit_code':0,'stderr':'',
                'stdout':f"Queued message {qid} for thread {fixed['task_id']}.\n"}
        qp=self.write('reports/original-queue/native-queue-result.json',result)
        call={'type':'commandExecution','id':'actual-original-queue-call','status':'completed','exitCode':0,
            'cwd':source['cwd'],'command':f"OfficialQueueTransport(...).enqueue(...) # reports/original-queue {rp} {pp}"}
        sender=self.write('reports/queue-sender-native.json',{'thread':{'id':source['task_id'],
            'title':source['title'],'cwd':source['cwd']},'turns':[{'id':'sending-turn','status':'completed',
            'startedAt':now.timestamp()-2,'completedAt':now.timestamp()+0.1,'items':[call]}]})
        recipient=self.write('reports/queue-recipient-native.json',{'thread':{'id':fixed['task_id'],
            'title':fixed['title'],'cwd':fixed['cwd']},'turns':[{'id':'receiving-turn','status':'inProgress',
            'startedAt':now.timestamp()+0.2,'items':[{'type':'userMessage','id':'different-user-message-id',
                'content':[{'type':'text','text':(self.root/payload).read_text()}]},
                {'type':'agentMessage','id':'actual-ACK','phase':'commentary','text':'Accepted the complete fixture task.'}]}]})
        item={'schema':continuity.ASSIGNMENT_SCHEMA,'task_id':self.task_id,'department':department,
            'sender_department':'operations','action_id':request['action_id'],'scope':goal['authorized_scope'][0],
            'source_kind':'official_native_queue','goal_contract':contract,'authorization_pin':goal['authorization_pin'],
            'payload':request['payload'],'original_prepare_request':w.file_digest(self.root,rp),
            'original_prepare_result':w.file_digest(self.root,pp),'actual_queue_intent':w.file_digest(self.root,ip),
            'actual_queue_result':w.file_digest(self.root,qp),'actual_native_invocation':w.file_digest(self.root,sender),
            'actual_native_recipient':w.file_digest(self.root,recipient),'source_call_id':call['id'],
            'queue_message_id':qid,'receiver_turn_id':'receiving-turn','receiver_message_id':'different-user-message-id',
            'ack_message_id':'actual-ACK','restore_position':'suspended'}
        item['dispatch_idempotency_key']='queue-assignment-'+w.sha256_value([
            self.task_id,department,qid,intent['policy_decision_id'],request['payload']])
        return self.write('reports/queue-assignment-recovery.json',item),item

    def test_delivered_queue_recovers_once_and_normal_initial_review_reads_it(self):
        import qa_review_plan as review
        path,item=self.queued()
        original={'assignments':{fixture.ASSISTANT:{'preserved':'other-task'}}}
        w.atomic_write_json(self.root/'data/department-current-assignment.json',original)
        with mock.patch.object(w,'policy_check',side_effect=AssertionError('must not reissue policy')):
            first=recovery.recover_queued_assignment(self.root,path)
            before=w.read_jsonl(w.receipts_path(self.root,self.task_id))
            second=recovery.recover_queued_assignment(self.root,path)
        self.assertEqual(first['dispatch_receipt_id'],second['dispatch_receipt_id'])
        self.assertEqual(first['result'],'recorded')
        self.assertEqual(first['ack_receipt_id'],second['ack_receipt_id'])
        self.assertEqual(second['result'],'duplicate_ignored')
        self.assertEqual(before,w.read_jsonl(w.receipts_path(self.root,self.task_id)))
        current=w.read_json(self.root/'data/department-current-assignment.json')
        self.assertEqual(current['assignments'],original['assignments'])
        self.assertEqual(current['suspended_assignments'][fixture.ASSISTANT],[w.file_digest(self.root,path)])
        rows,bad=w._validate_receipt_chain(self.root,self.task_id);self.assertEqual(bad,[])
        self.assertTrue(review._initial_assignment(self.root,self.snapshot(),rows[0]))
        self.assertTrue(recovery.initial_assignment_source(self.root,self.snapshot(),rows[0],item['goal_contract']))
        self.assertGreaterEqual(w._parse_observed_at(rows[0]['created_at']),
                                w._parse_observed_at(w.read_json(self.root/item['actual_queue_result']['path'])['finished_at']))

    def test_accepted_queue_without_real_receiver_and_ack_cannot_record(self):
        path,item=self.queued()
        for key,value in [('receiver_message_id','absent'),('ack_message_id','absent'),
                          ('receiver_turn_id','another-turn'),('source_call_id','another-call'),
                          ('department',fixture.PRODUCER),('scope','wrong-scope'),
                          ('queue_message_id','33333333-3333-4333-8333-333333333333')]:
            with self.subTest(key=key),self.assertRaises(w.WorkflowError):
                recovery.queued_assignment_source(self.root,{**item,key:value},require_dispatch=False)
        self.assertFalse(w.read_jsonl(w.receipts_path(self.root,self.task_id)))

    def test_changed_source_policy_native_and_transport_are_rejected_even_with_new_pin(self):
        _,item=self.queued()
        cases=[('original_prepare_request',lambda d:d.update(authorization_changes=['new_fee'])),
               ('original_prepare_result',lambda d:d['policy_decision'].update(decision_id='wrong-policy')),
               ('actual_queue_result',lambda d:d.update(exit_code=1)),
               ('actual_queue_result',lambda d:d.update(stderr='uncertain failure')),
               ('actual_native_invocation',lambda d:d['turns'][0]['items'][0].update(exitCode=1)),
               ('actual_native_invocation',lambda d:d['turns'][0]['items'][0].update(truncated=True)),
               ('actual_native_invocation',lambda d:d['thread'].update(id='wrong-sender')),
               ('actual_native_recipient',lambda d:d['turns'][0]['items'][0]['content'][0].update(text='different assignment')),
               ('actual_native_recipient',lambda d:d['turns'][0]['items'][1].update(text='  ')),
               ('actual_native_recipient',lambda d:d['turns'][0].update(startedAt=0))]
        for key,mutate in cases:
            with self.subTest(key=key,mutate=mutate):
                doc=copy.deepcopy(w.read_json(self.root/item[key]['path']));mutate(doc)
                path=self.write('reports/changed-source.json',doc)
                with self.assertRaises(w.WorkflowError):
                    recovery.queued_assignment_source(self.root,{**item,key:w.file_digest(self.root,path)},require_dispatch=False)

    def test_uncommitted_or_modified_queue_assignment_does_not_become_current(self):
        path,item=self.queued()
        with self.assertRaises(w.WorkflowError):continuity._dispatch_source(self.root,item)
        recovery.recover_queued_assignment(self.root,path)
        (self.root/item['payload']['path']).write_text('tampered')
        with self.assertRaises(w.WorkflowError):continuity._dispatch_source(self.root,item)


class ProducerOfficialQueueTests(unittest.TestCase):
    setUp=OfficialQueueAssignmentTests.setUp
    write=OfficialQueueAssignmentTests.write
    initialize=OfficialQueueAssignmentTests.initialize
    make_goal=OfficialQueueAssignmentTests.make_goal
    snapshot=OfficialQueueAssignmentTests.snapshot
    requested=OfficialQueueAssignmentTests.requested

    def queued(self):
        return OfficialQueueAssignmentTests.queued(self, department=fixture.PRODUCER)

    def test_actual_producer_queue_registers_current_and_preserves_prior_once(self):
        path,item=self.queued()
        prior=self.write('reports/prior-original-assignment.json',{'task_id':'prior-original-goal'})
        prior_pin=w.file_digest(self.root,prior)
        w.atomic_write_json(self.root/'data/department-current-assignment.json',
            {'assignments':{fixture.PRODUCER:prior_pin}})
        item.pop('restore_position');self.write(path,item)
        first=recovery.recover_queued_assignment(self.root,path)
        before=w.read_jsonl(w.receipts_path(self.root,self.task_id))
        second=recovery.recover_queued_assignment(self.root,path)
        self.assertEqual(second['result'],'duplicate_ignored')
        self.assertEqual(first['dispatch_receipt_id'],second['dispatch_receipt_id'])
        self.assertEqual(before,w.read_jsonl(w.receipts_path(self.root,self.task_id)))
        current=w.read_json(self.root/'data/department-current-assignment.json')
        self.assertEqual(current['assignments'][fixture.PRODUCER],w.file_digest(self.root,path))
        self.assertEqual(current['suspended_assignments'][fixture.PRODUCER],[prior_pin])
        events=w.read_jsonl(self.root/w.WORKFLOW_EVENTS)
        self.assertFalse(any(e.get('details',{}).get('initial_responsibility_assignment_source') for e in events))

    def test_wrong_role_action_goal_and_source_do_not_register(self):
        _,item=self.queued()
        for key,value in [('department',fixture.ASSISTANT),('action_id','assign-goal-review:'+self.task_id),
                          ('action_id','different-action'),('goal_contract',{}),('authorization_pin',{}),
                          ('queue_message_id','different-queue'),('source_call_id','absent'),
                          ('ack_message_id','absent')]:
            with self.subTest(key=key),self.assertRaises(w.WorkflowError):
                recovery.queued_assignment_source(self.root,{**item,key:value},require_dispatch=False)
        self.assertFalse(w.read_jsonl(w.receipts_path(self.root,self.task_id)))

    def test_changed_original_precheck_is_not_new_producer_authority(self):
        _,item=self.queued()
        for key,value in [('status','authorization_change_required'),('original_authorization',{}),
                          ('external_permission_issued',True),('actual_action_allowed',True)]:
            doc=copy.deepcopy(w.read_json(self.root/item['original_prepare_result']['path']))
            doc['authorization_precheck'][key]=value
            p=self.write('reports/changed-producer-precheck.json',doc)
            with self.subTest(key=key),self.assertRaises(w.WorkflowError):
                recovery.queued_assignment_source(self.root,{**item,'original_prepare_result':w.file_digest(self.root,p)},require_dispatch=False)

    def test_completed_call_inside_unfinished_source_round_still_waits(self):
        _,item=self.queued();doc=w.read_json(self.root/item['actual_native_invocation']['path'])
        doc['turns'][0]['status']='inProgress'
        p=self.write('reports/unfinished-producer-source.json',doc)
        with self.assertRaises(w.WorkflowError):
            recovery.queued_assignment_source(self.root,{**item,'actual_native_invocation':w.file_digest(self.root,p)},require_dispatch=False)

    def test_altered_transport_receiver_or_chronology_is_rejected(self):
        _,item=self.queued()
        for key,mutate in [('actual_queue_result',lambda d:d.update(exit_code=1)),
                           ('actual_native_recipient',lambda d:d['thread'].update(id='different-receiver')),
                           ('actual_native_recipient',lambda d:d['turns'][0]['items'][0]['content'][0].update(text='wrong task')),
                           ('actual_native_recipient',lambda d:d['turns'][0]['items'][1].update(text='')),
                           ('actual_native_recipient',lambda d:d['turns'][0].update(startedAt=0))]:
            doc=copy.deepcopy(w.read_json(self.root/item[key]['path']));mutate(doc)
            p=self.write('reports/changed-producer-source.json',doc)
            with self.subTest(key=key),self.assertRaises(w.WorkflowError):
                recovery.queued_assignment_source(self.root,{**item,key:w.file_digest(self.root,p)},require_dispatch=False)


class PreparedResultQueueAssignmentTests(OfficialQueueAssignmentTests):
    """The frozen prepared-result form, through the unchanged normal recovery entry."""
    def queued(self):
        path,item=super().queued()
        native=w.read_json(self.root/item['actual_native_invocation']['path'])
        native['turns'][0]['items'][0]['command']=(
            "python3 - <<'PY'\nimport json\nfrom pathlib import Path\n"
            "from department_event_dispatcher import OfficialQueueTransport\n"
            +"r=Path("+repr(str(self.root))+");s=r/'reports'\n"
            +"p=json.loads((s/'original-prepared-result.json').read_text())\n"
            +"directory=s/'original-queue'\n"
            +"OfficialQueueTransport(r,None).enqueue({'directory':directory,"
            "'thread_id':p['policy_decision']['target_thread_id'],"
            "'payload_sha256':p['payload']['sha256'],"
            "'policy_decision_id':p['policy_decision']['decision_id'],"
            "'message':(r/p['payload']['path']).read_text()})\nPY")
        # The original frozen observation was in progress. Its real later
        # native read may finish the turn without altering the original call.
        original=copy.deepcopy(native)
        original['turns'][0].update(status='inProgress',completedAt=None)
        reference=self.write('reports/frozen-original-queue-invocation.json',original)
        sender=self.write('reports/real-later-completed-sender.json',native)
        item['actual_native_invocation']=w.file_digest(self.root,sender)
        expected={key:copy.deepcopy(item[key]) for key in (
            'scope','department','source_call_id','queue_message_id','original_prepare_request',
            'original_prepare_result','actual_queue_intent','actual_queue_result')}
        expected['original_native']=w.file_digest(self.root,reference)
        patch=mock.patch.object(recovery,'_PREPARED_RESULT_QUEUE_SOURCES',{self.task_id:expected})
        patch.start();self.addCleanup(patch.stop)
        self.write(path,item)
        self.assertNotIn(Path(item['original_prepare_request']['path']).name,native['turns'][0]['items'][0]['command'])
        return path,item

    def test_prepared_result_without_request_literal_reads_exact_original_call(self):
        _,item=self.queued()
        snapshot,source=recovery.queued_assignment_source(self.root,item,require_dispatch=False)
        self.assertEqual(snapshot['task_id'],self.task_id)
        self.assertEqual(source['idempotency_key'],item['dispatch_idempotency_key'])
        self.assertFalse(w.read_jsonl(w.receipts_path(self.root,self.task_id)))

    def test_request_name_annotation_cannot_replace_changed_original_command(self):
        _,item=self.queued();doc=w.read_json(self.root/item['actual_native_invocation']['path'])
        doc['turns'][0]['items'][0]['command']+='\n# '+Path(item['original_prepare_request']['path']).name
        pin=self.write('reports/changed-call-with-request-name.json',doc)
        with self.assertRaises(w.WorkflowError):
            recovery.queued_assignment_source(self.root,{**item,'actual_native_invocation':w.file_digest(self.root,pin)},require_dispatch=False)

    def test_copied_or_renamed_packet_files_are_not_original_source(self):
        _,item=self.queued()
        for key in ('original_prepare_request','original_prepare_result','actual_queue_intent','actual_queue_result'):
            pin=self.write('reports/renamed-'+key+'.json',w.read_json(self.root/item[key]['path']))
            with self.subTest(key=key),self.assertRaises(w.WorkflowError):
                recovery.queued_assignment_source(self.root,{**item,key:w.file_digest(self.root,pin)},require_dispatch=False)

    def test_source_in_progress_remains_a_real_event_wait_without_effects(self):
        _,item=self.queued();doc=w.read_json(self.root/item['actual_native_invocation']['path'])
        doc['turns'][0].update(status='inProgress',completedAt=None)
        pin=self.write('reports/source-still-in-progress.json',doc)
        before=w.read_json(self.root/'data/department-current-assignment.json')
        with self.assertRaises(w.WorkflowError):
            recovery.queued_assignment_source(self.root,{**item,'actual_native_invocation':w.file_digest(self.root,pin),
                'source_turn_completed':True},require_dispatch=False)
        self.assertFalse(w.read_jsonl(w.receipts_path(self.root,self.task_id)))
        self.assertEqual(before,w.read_json(self.root/'data/department-current-assignment.json'))

    def test_original_call_turn_and_timestamp_cannot_move_to_another_round(self):
        _,item=self.queued()
        for change in ({'id':'another-source-turn'},{'startedAt':0}):
            doc=w.read_json(self.root/item['actual_native_invocation']['path']);doc['turns'][0].update(change)
            pin=self.write('reports/another-round.json',doc)
            with self.subTest(change=change),self.assertRaises(w.WorkflowError):
                recovery.queued_assignment_source(self.root,{**item,'actual_native_invocation':w.file_digest(self.root,pin)},require_dispatch=False)

    def test_tampered_frozen_original_source_pin_cannot_be_replaced(self):
        _,item=self.queued();profile=recovery._PREPARED_RESULT_QUEUE_SOURCES[self.task_id]
        (self.root/profile['original_native']['path']).write_text('{}')
        with self.assertRaises(w.WorkflowError):recovery.queued_assignment_source(self.root,item,require_dispatch=False)

    def test_complete_source_without_genuine_recipient_ack_does_not_admit(self):
        _,item=self.queued();doc=w.read_json(self.root/item['actual_native_recipient']['path'])
        doc['turns'][0]['items']=doc['turns'][0]['items'][:1]
        pin=self.write('reports/only-queued-user-message.json',doc)
        with self.assertRaises(w.WorkflowError):
            recovery.queued_assignment_source(self.root,{**item,'actual_native_recipient':w.file_digest(self.root,pin)},require_dispatch=False)
        self.assertFalse(w.read_jsonl(w.receipts_path(self.root,self.task_id)))

    def test_queue_and_receipt_times_keep_the_original_causal_guards(self):
        _,item=self.queued()
        for key,change in [('actual_native_invocation',{'completedAt':0}),
                           ('actual_native_recipient',{'startedAt':0})]:
            doc=w.read_json(self.root/item[key]['path']);doc['turns'][0].update(change)
            pin=self.write('reports/wrong-chronology.json',doc)
            with self.subTest(key=key),self.assertRaises(w.WorkflowError):
                recovery.queued_assignment_source(self.root,{**item,key:w.file_digest(self.root,pin)},require_dispatch=False)

    def test_unprofiled_other_task_does_not_gain_prepared_result_exemption(self):
        _,item=self.queued()
        with mock.patch.object(recovery,'_PREPARED_RESULT_QUEUE_SOURCES',{}),self.assertRaises(w.WorkflowError):
            recovery.queued_assignment_source(self.root,item,require_dispatch=False)

    def test_authorization_goal_policy_and_queue_identity_tampering_rejected(self):
        _,item=self.queued()
        for key,value in [('authorization_pin',{'path':'reports/absent.json','sha256':'0'*64,'size':0}),
                          ('goal_contract',{'path':'reports/absent.json','sha256':'0'*64,'size':0})]:
            with self.subTest(key=key),self.assertRaises(w.WorkflowError):
                recovery.queued_assignment_source(self.root,{**item,key:value},require_dispatch=False)
        for key,mutate in [('actual_queue_result',lambda d:d.update(stdout='Queued message 33333333-3333-4333-8333-333333333333 for thread 11111111-1111-4111-8111-111111111111.\n')),
                           ('actual_queue_intent',lambda d:d.update(policy_decision_id='forged')),
                           ('actual_queue_intent',lambda d:d.update(thread_id='wrong-target'))]:
            doc=w.read_json(self.root/item[key]['path']);mutate(doc);path=self.write('reports/tampered-original-identity.json',doc)
            with self.subTest(key=key),self.assertRaises(w.WorkflowError):
                recovery.queued_assignment_source(self.root,{**item,key:w.file_digest(self.root,path)},require_dispatch=False)

    def test_recovered_dispatch_receipt_hash_tampering_is_rejected(self):
        path,item=self.queued();recovery.recover_queued_assignment(self.root,path)
        rows=w.read_jsonl(w.receipts_path(self.root,self.task_id));rows[0]['receipt_hash']='0'*64
        w.receipts_path(self.root,self.task_id).write_text(''.join(json.dumps(row)+'\n' for row in rows))
        with self.assertRaises(w.WorkflowError):recovery.queued_assignment_source(self.root,item)

    def test_real_policy_target_tampering_is_rejected(self):
        _,item=self.queued();path=self.root/w.POLICY_DECISIONS;rows=w.read_jsonl(path)
        policy=w.read_json(self.root/item['original_prepare_result']['path'])['policy_decision']['decision_id']
        next(row for row in rows if row['decision_id']==policy)['target_thread_id']='wrong-target'
        path.write_text(''.join(json.dumps(row)+'\n' for row in rows))
        with self.assertRaises(w.WorkflowError):recovery.queued_assignment_source(self.root,item,require_dispatch=False)

    def recovery_preparer(self):
        import runpy
        script=Path(w.__file__).resolve().parents[1]/'logs/handoffs/2026-10-20-clean-department-window-rotation-v1/operations/unfinished-business-followthrough-20261021-v1/KL-review-queue-source-technical-followthrough-v1/system-development-v1/PREPARE-ORIGINAL-RECOVERY-v1.py'
        if (Path(w.__file__).resolve().parents[1] / 'release-manifest.json').is_file() and not script.is_file():
            self.skipTest('Native company recovery preparer is excluded from the public package')
        return runpy.run_path(str(script))['prepare']

    def test_delivered_preparer_uses_actual_facts_then_normal_recovery_once(self):
        _,item=self.queued();prepare=self.recovery_preparer()
        result=prepare(self.root,item['actual_native_invocation']['path'],item['actual_native_recipient']['path'],
                       'reports/operator-inputs',task_id=self.task_id)
        self.assertEqual(result['state'],'READY_NOT_RECOVERED')
        self.assertFalse(w.read_jsonl(w.receipts_path(self.root,self.task_id)))
        first=recovery.recover_queued_assignment(self.root,result['input']['path'])
        before=w.receipts_path(self.root,self.task_id).read_bytes()
        after=prepare(self.root,item['actual_native_invocation']['path'],item['actual_native_recipient']['path'],
                      'reports/operator-inputs',task_id=self.task_id)
        self.assertEqual(after['state'],'ALREADY_RECOVERED_NO_REPLAY')
        self.assertEqual(after['dispatch_receipt_id'],first['dispatch_receipt_id'])
        self.assertEqual(before,w.receipts_path(self.root,self.task_id).read_bytes())

    def test_delivered_preparer_reports_true_wait_and_emits_no_fake_input(self):
        _,item=self.queued();prepare=self.recovery_preparer()
        native=w.read_json(self.root/item['actual_native_invocation']['path'])
        native['turns'][0].update(status='inProgress',completedAt=None)
        path=self.write('reports/real-source-not-finished.json',native)
        before=w.read_json(self.root/'data/department-current-assignment.json')
        result=prepare(self.root,path,None,'reports/operator-inputs',task_id=self.task_id)
        self.assertEqual(result['state'],'WAIT_REAL_EVENTS');self.assertEqual(len(result['pending']),2)
        self.assertFalse((self.root/'reports/operator-inputs').exists())
        self.assertFalse(w.read_jsonl(w.receipts_path(self.root,self.task_id)))
        self.assertEqual(before,w.read_json(self.root/'data/department-current-assignment.json'))

    def test_preparer_rejects_wrong_identity_and_call_before_classifying_wait(self):
        _,item=self.queued();prepare=self.recovery_preparer()
        for part in ('identity','command'):
            doc=w.read_json(self.root/item['actual_native_invocation']['path'])
            doc['turns'][0].update(status='inProgress',completedAt=None)
            if part=='identity':doc['thread']['id']='another-source'
            else:doc['turns'][0]['items'][0]['command']+=' # modified'
            path=self.write('reports/invalid-pending-source.json',doc)
            with self.subTest(part=part),self.assertRaises(w.WorkflowError):
                prepare(self.root,path,None,'reports/operator-inputs',task_id=self.task_id)
        self.assertFalse((self.root/'reports/operator-inputs').exists())

    def test_preparer_retains_same_input_for_interrupted_local_recovery(self):
        import argparse
        _,item=self.queued();prepare=self.recovery_preparer()
        result=prepare(self.root,item['actual_native_invocation']['path'],item['actual_native_recipient']['path'],
                       'reports/operator-inputs',task_id=self.task_id)
        source_item=w.read_json(self.root/result['input']['path'])
        _,source=recovery.queued_assignment_source(self.root,source_item,require_dispatch=False)
        args=dict(task_id=self.task_id,department=item['department'],evidence=result['input']['path'],ack_nonempty=False,**source)
        first,_=w.record_receipt(self.root,argparse.Namespace(**args,receipt_type='dispatch_sent'))
        waiting=prepare(self.root,item['actual_native_invocation']['path'],item['actual_native_recipient']['path'],
                        'reports/operator-inputs',task_id=self.task_id)
        self.assertEqual(waiting['state'],'READY_TO_FINISH_EXISTING_RECOVERY')
        self.assertEqual(waiting['input'],result['input'])
        recovered=recovery.recover_queued_assignment(self.root,waiting['input']['path'])
        self.assertEqual(first['receipt_id'],recovered['dispatch_receipt_id'])
        self.assertEqual(len(w.read_jsonl(w.receipts_path(self.root,self.task_id))),2)


class RecoveryTests(unittest.TestCase):
    setUp=fixture.GoalRuntimeConsumerTests.setUp
    write=fixture.GoalRuntimeConsumerTests.write
    initialize=fixture.GoalRuntimeConsumerTests.initialize
    make_goal=fixture.GoalRuntimeConsumerTests.make_goal
    snapshot=fixture.GoalRuntimeConsumerTests.snapshot
    requested=fixture.GoalRuntimeConsumerTests.requested
    result_box=fixture.GoalRuntimeConsumerTests.result_box

    def source(self, **changes):
        owner=w.department_registry(self.root)[fixture.PRODUCER]['chat_binding']['task_id']
        auth=w.read_json(self.root/'reports/synthetic-owner-message.json');auth['source_thread_id']=owner
        self.write('reports/synthetic-owner-message.json',auth)
        declared=self.make_goal()['human_authorization'];declared['source_thread_id']=owner
        self.initialize(source_mode='owner_direct',human_authorization=declared,original_parent_reference_task_id='historic-closed-001')
        goal=self.snapshot()['goal_delivery'];binding=w.department_registry(self.root)[fixture.PRODUCER]['chat_binding']
        human=w.read_json(self.root/goal['authorization_pin']['path'])
        # Fixture auth is synthetic; it is linked to the real fixture fixed source.
        page={'thread':{'id':binding['task_id'],'title':binding['title'],'cwd':binding['cwd']},
              'turns':[{'id':'original-turn','status':'completed','error':None,'startedAt':1,
                        'items':[human['message']]}]}
        path=self.write('reports/original-source.json',page)
        item={'schema':continuity.ASSIGNMENT_SCHEMA,'task_id':self.task_id,
              'department':fixture.PRODUCER,'sender_department':fixture.PRODUCER,
              'scope':goal['authorized_scope'][0],'source_kind':'owner_direct_native',
              'original_task_id':'historic-closed-001','authorization_pin':goal['authorization_pin'],
              'actual_native_invocation':w.file_digest(self.root,path),**changes}
        return self.write('reports/recovery.json',item),item,page

    def test_recovery_records_now_without_dispatch_or_policy_and_is_idempotent(self):
        path,item,_=self.source();before=w.read_jsonl(w.receipts_path(self.root,self.task_id))
        result=recovery.record(self.root,path)
        self.assertIsNone(result['source_recovery']['receipt_id'])
        self.assertFalse(result['source_recovery']['dispatch_fabricated'])
        self.assertEqual(w.read_jsonl(w.receipts_path(self.root,self.task_id)),before)
        self.assertEqual(recovery.record(self.root,path)['result'],'duplicate_ignored')
        current=continuity.current_assignment(self.root,fixture.PRODUCER,w.file_digest(self.root,path))
        self.assertTrue(current['resume_required'])
        self.assertEqual(current['actual_source_receipt']['original_task_id'],'historic-closed-001')

    def test_suspended_recovery_preserves_current_other_assignment(self):
        path,item,_=self.source(restore_position='suspended')
        w.atomic_write_json(self.root/'data/department-current-assignment.json',
                            {'assignments':{fixture.PRODUCER:{'unchanged':'other-current'}}})
        recovery.record(self.root,path);d=w.read_json(self.root/'data/department-current-assignment.json')
        self.assertEqual(d['assignments'][fixture.PRODUCER],{'unchanged':'other-current'})
        self.assertEqual(d['suspended_assignments'][fixture.PRODUCER],[w.file_digest(self.root,path)])
        recovery.record(self.root,path)
        self.assertEqual(w.read_json(self.root/'data/department-current-assignment.json'),d)

    def test_wrong_identity_scope_original_task_and_owner_are_rejected(self):
        path,item,_=self.source()
        for changes in ({'scope':'other-scope'},{'original_task_id':'other-old'},
                        {'department':'publishing'},{'sender_department':'operations'}):
            with self.subTest(changes=changes),self.assertRaises(w.WorkflowError):
                recovery.validate(self.root,{**item,**changes},require_record=False)

    def test_changed_native_human_source_is_rejected(self):
        path,item,page=self.source();page['turns'][0]['items'][0]['type']='agentMessage'
        self.write(item['actual_native_invocation']['path'],page)
        with self.assertRaises(w.WorkflowError): recovery.record(self.root,path)

    def test_uncommitted_recovery_cannot_be_used_as_assignment(self):
        path,item,_=self.source()
        with self.assertRaises(w.WorkflowError): continuity._dispatch_source(self.root,item)

    def test_corrupt_recovery_journal_is_rejected_without_touching_assignment(self):
        path,item,_=self.source();recovery.record(self.root,path)
        before=(self.root/'data/department-current-assignment.json').read_bytes()
        rows=w.read_jsonl(self.root/w.WORKFLOW_EVENTS)
        rows[-1]['details']['native_source_recovery']['scope']='tampered-scope'
        (self.root/w.WORKFLOW_EVENTS).write_text(''.join(json.dumps(x)+'\n' for x in rows))
        with self.assertRaises(w.WorkflowError): recovery.validate(self.root,item)
        self.assertEqual((self.root/'data/department-current-assignment.json').read_bytes(),before)

    def test_real_preparation_consumes_auth_and_policy_and_busy_target_does_not_send(self):
        self.initialize();req=self.requested(sender='operations')
        b=w.department_registry(self.root)[fixture.PRODUCER]['chat_binding']
        p=self.write('reports/live-target.json',{'thread':{'id':b['task_id'],'title':b['title'],'cwd':b['cwd']},
                   'turns':[{'id':'actual-turn','status':'inProgress'}]})
        req['actual_target_state']=w.file_digest(self.root,p)
        with mock.patch.object(w,'policy_check') as policy:
            self.assertEqual(recovery.prepare_message(self.root,req)['status'],'waiting_target_completion')
            policy.assert_not_called()
        d=w.read_json(self.root/p);d['turns'][0]['status']='completed';self.write(p,d)
        req['actual_target_state']=w.file_digest(self.root,p)
        with mock.patch.object(w,'policy_check',return_value=({'status':'allow','decision_id':'actual-test'},[])) as policy:
            self.assertEqual(recovery.prepare_message(self.root,req)['status'],'ready_to_send')
            policy.assert_called_once()
        req['authorization_changes']=['new_fee']
        with mock.patch.object(w,'policy_check') as policy:
            self.assertEqual(recovery.prepare_message(self.root,req)['status'],'blocked');policy.assert_not_called()

    def test_busy_native_queue_requires_capability_and_consumes_exact_policy(self):
        import department_event_dispatcher as dispatcher
        self.initialize();req=self.requested(sender='operations')
        b=w.department_registry(self.root)[fixture.PRODUCER]['chat_binding']
        p=self.write('reports/busy-queue-target.json',{'thread':{'id':b['task_id'],'title':b['title'],'cwd':b['cwd']},
                   'turns':[{'id':'actual-busy-turn','status':'inProgress'}]})
        req.update(actual_target_state=w.file_digest(self.root,p),delivery_mode='official_native_queue')
        with mock.patch.object(dispatcher,'native_queue_capability',return_value='/admitted/cli') as capability, \
                mock.patch.object(w,'policy_check',return_value=({'status':'allow','decision_id':'exact-policy'},[])) as policy:
            result=recovery.prepare_message(self.root,req)
            self.assertEqual(result['status'],'ready_to_queue')
            self.assertFalse(result['ordinary_send_allowed'])
            self.assertFalse(result['message_sent'])
            capability.assert_called_once_with(self.root);policy.assert_called_once()
        with mock.patch.object(dispatcher,'native_queue_capability',side_effect=ValueError('unproven capability')), \
                mock.patch.object(w,'policy_check') as policy:
            with self.assertRaisesRegex(ValueError,'unproven'):
                recovery.prepare_message(self.root,req)
            policy.assert_not_called()
        with mock.patch.object(dispatcher,'native_queue_capability',return_value='/admitted/cli'), \
                mock.patch.object(w,'policy_check',return_value=({'status':'deny'},[])):
            self.assertEqual(recovery.prepare_message(self.root,req)['status'],'blocked')
        req['authorization_changes']=['new_fee']
        with mock.patch.object(dispatcher,'native_queue_capability') as capability:
            self.assertEqual(recovery.prepare_message(self.root,req)['status'],'blocked')
            capability.assert_not_called()

    def test_partial_frozen_result_without_invented_ACK_enters_normal_intake(self):
        path,item,_=self.source();recovery.record(self.root,path)
        candidate=self.write('reports/finite-candidate.json',{'synthetic':True})
        box=self.result_box(fixture.PRODUCER,'partial-v1',w.file_digest(self.root,candidate));box['status']='partial'
        out=self.write('logs/department-outbox/partial-result.json',box);pin=w.file_digest(self.root,out)
        identity={'task_id':self.task_id,'sender_department':fixture.PRODUCER,'candidate_version':'partial-v1',
                  'result_sha256':pin['sha256']}
        text=continuity.READY_MARKER+json.dumps({**identity,'outbox_path':out,'batch_complete':True})+'\n'
        reply=self.root/'reports/ready-reply.txt';reply.write_text(text)
        b=w.department_registry(self.root)[fixture.PRODUCER]['chat_binding'];now=dt.datetime.now(dt.timezone.utc)
        native=self.write('reports/ready-source.json',{'thread':{'id':b['task_id'],'title':b['title'],'cwd':b['cwd']},
                'turns':[{'id':'new-delivery-turn','status':'inProgress','error':None,'startedAt':now.timestamp()-1,
                          'items':[{'type':'agentMessage','id':'ready-partial','phase':'commentary','text':text}]}]})
        request={**identity,'event':'notification_queued','idempotency_key':'recover-partial-once','outbox_path':out,
                 'result_source_phase':'delivery_ready','source_thread_id':b['task_id'],'source_turn_id':'new-delivery-turn',
                 'source_message_id':'ready-partial','source_reply_sha256':w.file_digest(self.root,'reports/ready-reply.txt')['sha256'],
                 'reply_observed_at':now.isoformat(),'actual_native_completion':w.file_digest(self.root,native),
                 'visible_reply':w.file_digest(self.root,'reports/ready-reply.txt')}
        row,_=w.record_result_handoff(self.root,request)
        self.assertTrue(row['batch_delivery_frozen']);self.assertFalse(row['business_goal_closed'])
        self.fixture.receipt('outbox_received',fixture.PRODUCER,'recovered-partial-intake',evidence=out)
        rows,bad=w._validate_receipt_chain(self.root,self.task_id)
        self.assertFalse(bad);self.assertFalse(any(r['receipt_type']=='chat_ack' for r in rows))
        self.assertEqual(w.record_result_handoff(self.root,request)[0]['result'],'duplicate_ignored')

    def test_new_assignment_without_exact_task_id_stops_before_policy_or_send(self):
        self.initialize();req=self.requested(sender='operations');req['assignment_record_required']=True
        for body in ('bounded work without identity',self.task_id+'-different-task'):
            w.safe_path(self.root,req['payload']['path']).write_text(body)
            req['payload']=w.file_digest(self.root,req['payload']['path']);req['payload_sha256']=req['payload']['sha256']
            with mock.patch.object(w,'policy_check') as policy,self.assertRaisesRegex(w.WorkflowError,'identify original task'):
                recovery.prepare_message(self.root,req)
            policy.assert_not_called()

    def test_notLoaded_is_resolved_by_actual_turn_and_new_active_turn_is_respected(self):
        self.initialize();b=w.department_registry(self.root)[fixture.PRODUCER]['chat_binding']
        page={'thread':{'id':b['task_id'],'title':b['title'],'cwd':b['cwd'],'updatedAt':3},
              'turns':[{'id':'true-turn','status':'completed'}]}
        p=self.write('reports/target-turn.json',page)
        live={'actual_native_target_turn':w.file_digest(self.root,p)}
        row={'status':'notLoaded','updatedAt':2}
        self.assertEqual(recovery.actual_target_turn_status(self.root,live,row,b),'idle')
        page['turns'][0]['status']='inProgress';self.write(p,page);live['actual_native_target_turn']=w.file_digest(self.root,p)
        self.assertEqual(recovery.actual_target_turn_status(self.root,live,{'status':'idle','updatedAt':2},b),'active')
        page['turns'][0]['status']='completed';page['thread']['updatedAt']=1;self.write(p,page)
        live['actual_native_target_turn']=w.file_digest(self.root,p)
        self.assertEqual(recovery.actual_target_turn_status(self.root,live,row,b),'unknown_target')

    def original_owner_external_collaboration(self):
        """One complete isolated contract; no mutation of a frozen declaration."""
        registry=w.read_json(self.root/'data/department-registry.json')
        source=next(r for r in registry['departments']if r['id']==fixture.PRODUCER)['chat_binding']
        source['host_id']='local'
        binding={'thread_id':'synthetic-fixed-development','project_id':'synthetic-development-project',
                 'title':'Synthetic designated development','cwd':str(self.root/'synthetic-code-project'),
                 'host_id':'local'}
        registry['collaboration_bindings']={'designated-development':binding}
        w.atomic_write_json(self.root/'data/department-registry.json',registry)
        request=self.requested(sender=fixture.PRODUCER,scope='project:test:designated-development')
        request.update(target_department='designated-development',target_project_id=binding['project_id'],
                       target_thread_id=binding['thread_id'],target_thread_title=binding['title'],
                       target_cwd=binding['cwd'],target_sidebar_section_id='synthetic-development-sidebar',
                       action_id='bounded-original-external-collaboration')
        live={'fixture_only':True,'observed_at':w.utc_timestamp(),'native_receipt_ref':'synthetic-live-read',
              'target_sidebar_section_id':request['target_sidebar_section_id'],
              'threads':[{'id':binding['thread_id'],'projectId':binding['project_id'],'title':binding['title'],
                          'cwd':binding['cwd'],'hostId':'local','status':'idle'},
                         {'id':source['task_id'],'projectId':source['project_id'],'title':source['title'],
                          'cwd':source['cwd'],'hostId':'local'}]}
        request['live_identity']=w.file_digest(self.root,self.write('reports/synthetic-original-owner-live.json',live))
        self.initialize(authorized_scope=[request['scope']],approved_actions=[request],collaboration_scopes=[{
            'sender_department':fixture.PRODUCER,'target_department':'designated-development','scope':request['scope']}])
        return request,binding

    def test_declared_external_collaborator_uses_binding_without_becoming_a_department(self):
        request,binding=self.original_owner_external_collaboration()
        p=self.write('reports/external-current-turn.json',{'thread':{'id':binding['thread_id'],'title':binding['title'],'cwd':binding['cwd'],'kind':'codex','hostId':'local'},
                                                       'turns':[{'id':'actual-external-turn','status':'completed'}]})
        request['actual_target_state']=w.file_digest(self.root,p)
        live=w.read_json(self.root/request['live_identity']['path'])
        inventory=self.write('reports/actual-external-inventory.json',{'threads':live['threads']})
        request['actual_live_inventory']=w.file_digest(self.root,inventory)
        request['live_observed_at']=dt.datetime.now(dt.timezone.utc).isoformat()
        before=w.read_json(self.root/'data/department-registry.json')
        result=recovery.prepare_message(self.root,request)
        self.assertEqual(result['status'],'ready_to_send',result)
        self.assertEqual(before,w.read_json(self.root/'data/department-registry.json'))

    def test_external_notLoaded_consumes_completed_native_turn_without_rewriting_inventory(self):
        request,binding=self.original_owner_external_collaboration()
        live=w.read_json(self.root/request['live_identity']['path'])
        live['threads'][0].update(status='notLoaded',updatedAt=2)
        inventory=self.write('reports/unloaded-external-inventory.json',{'threads':live['threads']})
        native=self.write('reports/completed-external-turn.json',
            {'thread':{'id':binding['thread_id'],'title':binding['title'],'cwd':binding['cwd'],'kind':'codex','hostId':'local','updatedAt':3},
             'turns':[{'id':'completed-external','status':'completed','error':None}]})
        request.update(actual_target_state=w.file_digest(self.root,native),
                       actual_live_inventory=w.file_digest(self.root,inventory),
                       live_observed_at=dt.datetime.now(dt.timezone.utc).isoformat())
        result=recovery.prepare_message(self.root,request)
        self.assertEqual(result['status'],'ready_to_send',result)
        snapshot=self.snapshot();proof=snapshot['goal_delivery']['current_route_observations'][request['action_id']]
        observed=w.read_json(self.root/proof['path'])
        target=next(row for row in observed['threads'] if row['id']==binding['thread_id'])
        self.assertEqual(target['status'],'notLoaded')
        self.assertEqual(observed['actual_native_target_turns'][binding['thread_id']],request['actual_target_state'])
        self.assertEqual(w.file_digest(self.root,inventory),request['actual_live_inventory'])

    def test_external_prepare_rejects_wrong_owner_host_project_and_payload(self):
        request,binding=self.original_owner_external_collaboration()
        page={'thread':{'id':binding['thread_id'],'title':binding['title'],'cwd':binding['cwd'],
                        'kind':'codex','hostId':'local'},'turns':[{'id':'exact-turn','status':'completed'}]}
        request['actual_target_state']=w.file_digest(self.root,self.write('reports/external-identity.json',page))
        live=w.read_json(self.root/request['live_identity']['path'])
        request.update(actual_live_inventory=w.file_digest(self.root,self.write('reports/external-inventory.json',{'threads':live['threads']})),
                       live_observed_at=w.utc_timestamp())
        contract=self.snapshot()['goal_contract']
        for name,changes in [('owner',{'sender_department':fixture.ASSISTANT}),
                             ('project',{'target_project_id':'wrong-project'}),
                             ('payload',{'payload_sha256':'0'*64}),('host',{})]:
            with self.subTest(name=name):
                current={**request,**changes}
                if name=='host':
                    wrong=copy.deepcopy(page);wrong['thread']['hostId']='wrong-host'
                    current['actual_target_state']=w.file_digest(self.root,self.write('reports/wrong-host.json',wrong))
                try:result=recovery.prepare_message(self.root,current)
                except w.WorkflowError:pass
                else:self.assertNotIn(result.get('status'),{'ready_to_send','ready_to_queue'})
                self.assertEqual(w.file_digest(self.root,contract['path']),contract)

    def test_external_idle_resolution_rejects_active_stale_wrong_and_missing_turn_proofs(self):
        request,binding=self.original_owner_external_collaboration()
        original=w.read_json(self.root/request['live_identity']['path'])
        original['threads'][0].update(status='notLoaded',updatedAt=2)
        for name,changes in [('active',{'turn_status':'inProgress'}),
                             ('stale',{'updatedAt':1}),('wrong',{'id':'another-thread'}),
                             ('missing',{'no_native':True}),('tampered',{'tampered':True})]:
            with self.subTest(name=name):
                page={'thread':{'id':changes.get('id',binding['thread_id']),
                      'title':binding['title'],'cwd':binding['cwd'],'kind':'codex','hostId':'local','updatedAt':changes.get('updatedAt',3)},
                      'turns':[{'id':'exact-turn','status':changes.get('turn_status','completed')}]}
                path=self.write('reports/'+name+'-native.json',page)
                pin=w.file_digest(self.root,path)
                if changes.get('tampered'):pin={**pin,'sha256':'0'*64}
                live={**original,'actual_native_target_turns':{} if changes.get('no_native') else {binding['thread_id']:pin}}
                lp=self.write('reports/'+name+'-observation.json',live)
                snapshot=self.snapshot();snapshot['goal_delivery']={**snapshot['goal_delivery'],
                    'current_route_observations':{request['action_id']:w.file_digest(self.root,lp)}}
                reasons=runtime.collaboration_route(self.root,snapshot,{k:v for k,v in request.items()
                    if k not in {'payload','live_identity'}})
                self.assertTrue(reasons,(name,reasons))


class AdoptionNoticeTests(unittest.TestCase):
    """Use committed native/SQL fixture decisions, never invented real dispatch."""
    def setUp(self):
        self.t=fixture.GoalRuntimeConsumerTests('runTest');self.t.setUp()
        self.addCleanup(self.t.doCleanups);self.root=self.t.root

    def prepare(self, sender=fixture.ASSISTANT):
        import result_coordination as rc
        t=self.t;plan,pp=t.prepare_initial_review();t.assistant_verdict(plan,pp,verdict='pass')
        identity={'task_id':t.task_id,'sender_department':fixture.PRODUCER,'candidate_version':'v1',
                  'result_sha256':pp['sha256'],'outbox_path':pp['path']}
        w.record_result_handoff(self.root,{**identity,**t.completed_result_fields(),
            'event':'notification_queued','idempotency_key':'adoption-fixture-queued'})
        store=rc.CoordinationStore(self.root);self.addCleanup(store.close)
        lease=store.claim(identity,fixture.ASSISTANT,'fixture-adoption-owner','adoption-fixture-claim')
        actor={'coordinator_role':fixture.ASSISTANT,'coordinator_owner':lease['owner'],'coordination_claim':lease}
        w.record_result_handoff(self.root,{**identity,**actor,'event':'controller_received',
            'idempotency_key':'adoption-fixture-intake','intake_mode':'queue',
            'source_thread_id':'fixed-'+fixture.PRODUCER,
            'source_reply_sha256':w.file_digest(self.root,'reports/native-final.txt')['sha256'],
            'reply_observed_at':w.utc_timestamp()})
        decision,_=w.record_result_handoff(self.root,{**identity,**actor,'event':'controller_decision',
            'idempotency_key':'adoption-fixture-decision','decision':'continue','next_owner':fixture.ASSISTANT,
            'next_action':'adopt exact fixture source','evidence_paths':[pp['path']]})
        backup=t.write('backups/source-before.json',{'before':True});source=t.write('tools/adopted-source.json',{'after':True})
        bp=w.file_digest(self.root,backup);sp=w.file_digest(self.root,source)
        journal={'task_id':t.task_id,'actor':fixture.ASSISTANT,'status':'complete','direction':'forward',
            'external_writes':0,'effect_uncertain':False,'permissions_issued':False,'execution_id':'fixture-source-effect',
            'candidate_version':'v1','decision_record_id':decision['record_id'],'source_operations':[
                {'path':source,'before':{k:bp[k] for k in ('sha256','size')},'after_expected':{k:sp[k] for k in ('sha256','size')},
                 'after_actual':{k:sp[k] for k in ('sha256','size')},'backup':bp,'write_attempted':True,'verified_after':True}]}
        jp=t.write('reports/adoption-journal.json',journal);pin=w.file_digest(self.root,jp)
        follow,_=w.record_result_handoff(self.root,{**identity,**actor,'event':'controller_followthrough',
            'idempotency_key':'adoption-fixture-followthrough','followthrough_status':'blocked_with_owner',
            'next_check_at':(dt.datetime.now(dt.timezone.utc)+dt.timedelta(hours=1)).isoformat(),
            'unblock_condition':'source-adopted:fixture-source-effect;remaining:fixture publisher Save',
            'evidence_paths':[jp]})
        req=t.requested(sender=sender);req['post_adoption_notice']={'journal':pin,'followthrough_record_id':follow['record_id']}
        req['action_id']='notify-adoption-'+w.sha256_value([t.task_id,sender,fixture.PRODUCER,pin])
        body=recovery.adoption_notice_message(self.root,req)
        p=self.root/'reports/adoption-notice.txt';p.write_text(json.dumps(body,ensure_ascii=False,sort_keys=True,indent=2)+'\n')
        req['payload']=w.file_digest(self.root,str(p.relative_to(self.root)));req['payload_sha256']=req['payload']['sha256']
        binding=w.department_registry(self.root)[fixture.PRODUCER]['chat_binding']
        live=t.write('reports/adoption-target.json',{'thread':{'id':binding['task_id'],'title':binding['title'],'cwd':binding['cwd']},
             'turns':[{'id':'original-idle-turn','status':'completed'}]})
        req['actual_target_state']=w.file_digest(self.root,live)
        return req

    def test_assistant_return_after_adoption_uses_existing_real_policy_without_new_decision(self):
        req=self.prepare();before=w._result_handoff_rows(self.root,self.t.task_id)
        result=recovery.prepare_message(self.root,req)
        self.assertEqual(result['status'],'ready_to_send',result)
        self.assertEqual(before,w._result_handoff_rows(self.root,self.t.task_id))
        self.assertEqual(recovery.prepare_message(self.root,req)['status'],'ready_to_send')
        actions=self.t.snapshot()['goal_delivery']['approved_actions']
        self.assertEqual(len([a for a in actions if a['action_id']==req['action_id']]),1)
        self.assertFalse(result['message_sent']);self.assertFalse(w.read_jsonl(w.receipts_path(self.root,self.t.task_id))[-1].get('actual_message_sent',False))

    def test_busy_original_producer_retains_notice_without_freezing_new_dispatch(self):
        req=self.prepare();p=req['actual_target_state']['path'];d=w.read_json(self.root/p);d['turns'][0]['status']='inProgress';self.t.write(p,d)
        req['actual_target_state']=w.file_digest(self.root,p);before=self.t.snapshot()
        self.assertEqual(recovery.prepare_message(self.root,req)['status'],'waiting_target_completion')
        self.assertEqual(before,self.t.snapshot())

    def test_rejected_wrong_source_project_does_not_poison_corrected_retry(self):
        req=self.prepare();before=self.t.snapshot()
        with self.assertRaisesRegex(w.WorkflowError,'sender project'):
            recovery.prepare_message(self.root,{**req,'source_project_id':'wrong-source-project'})
        self.assertEqual(before,self.t.snapshot())
        self.assertEqual(recovery.prepare_message(self.root,req)['status'],'ready_to_send')

    def second_sender(self,req):
        other={**req,'sender_department':'operations'}
        other['action_id']='notify-adoption-'+w.sha256_value([self.t.task_id,'operations',fixture.PRODUCER,req['post_adoption_notice']['journal']])
        msg=recovery.adoption_notice_message(self.root,other)
        p=self.root/'reports/HQ-adoption-notice.txt';p.write_text(json.dumps(msg,ensure_ascii=False,sort_keys=True,indent=2)+'\n')
        other['payload']=w.file_digest(self.root,str(p.relative_to(self.root)));other['payload_sha256']=other['payload']['sha256']
        return other

    def test_HQ_and_assistant_cannot_prepare_parallel_returns_for_one_adoption(self):
        req=self.prepare();self.assertEqual(recovery.prepare_message(self.root,req)['status'],'ready_to_send')
        other=self.second_sender(req);before=self.t.snapshot()
        result=recovery.prepare_message(self.root,other)
        self.assertEqual(result['status'],'waiting_existing_callback_effect');self.assertFalse(result['message_sent'])
        self.assertEqual(before,self.t.snapshot())

    def test_sent_fact_blocks_same_and_other_senders_without_second_policy_or_dispatch(self):
        req=self.prepare();self.assertEqual(recovery.prepare_message(self.root,req)['status'],'ready_to_send')
        other=self.second_sender(req)
        receipt={'task_id':self.t.task_id,'receipt_type':'dispatch_sent','action_id':req['action_id'],
                 'department':fixture.PRODUCER,'receipt_id':'fixture-only-actual-receipt'}
        real=w.read_jsonl
        def read(path):
            values=real(path)
            return values+[receipt] if Path(path)==w.receipts_path(self.root,self.t.task_id) else values
        with mock.patch.object(w,'read_jsonl',side_effect=read),mock.patch.object(w,'policy_check') as policy:
            for request in (req,other):
                result=recovery.prepare_message(self.root,request)
                self.assertEqual(result['status'],'duplicate_ignored');self.assertFalse(result['message_sent'])
            policy.assert_not_called()

    def test_factual_return_rejects_new_instruction_or_wrong_receiver(self):
        req=self.prepare();p=self.root/req['payload']['path'];p.write_text('Make a new paid campaign')
        req['payload']=w.file_digest(self.root,req['payload']['path']);req['payload_sha256']=req['payload']['sha256']
        with self.assertRaisesRegex(w.WorkflowError,'arbitrary new instructions'):recovery.prepare_message(self.root,req)
        with self.assertRaises(w.WorkflowError):recovery.adoption_notice_message(self.root,{**req,'target_department':'sales'})

    def test_tampered_or_uncommitted_adoption_and_changed_source_are_rejected(self):
        req=self.prepare();source=req['post_adoption_notice'];jp=source['journal']['path'];original=w.read_json(self.root/jp)
        for delta in ({'external_writes':1},{'effect_uncertain':True},{'actor':'operations-assistant-3'},
                      {'execution_id':'not-committed'},{'task_id':'different-task'},{'source_operations':[]}):
            with self.subTest(delta=delta):
                self.t.write(jp,{**original,**delta});changed={**req,'post_adoption_notice':{**source,'journal':w.file_digest(self.root,jp)}}
                with self.assertRaises(w.WorkflowError):recovery.adoption_notice_message(self.root,changed)
        self.t.write(jp,original)
        self.t.write(original['source_operations'][0]['path'],{'changed':True})
        with self.assertRaises(w.WorkflowError):recovery.adoption_notice_message(self.root,req)


class CMSAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.fixture=fixture.GoalRuntimeConsumerTests('runTest');self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups);self.root=self.fixture.root

    def ordinary_goal(self,risk='R1'):
        t=self.fixture;scope='company.example:services/synthetic-row:content_zh'
        registry=w.read_json(self.root/'data/department-registry.json')
        publisher=copy.deepcopy(next(d for d in registry['departments'] if d['id']==fixture.PRODUCER))
        publisher['id']='publishing';publisher['chat_binding']['task_id']='synthetic-publisher-chat'
        registry['departments'].append(publisher)
        w.atomic_write_json(self.root/'data/department-registry.json',registry)
        action={'action_id':'exact-forward','action_class':'cms_write','scope':scope,'department':'publishing'}
        t.initialize(authorized_scope=[scope],producer_departments=[fixture.PRODUCER,'publishing'],
                     required_execution_actions=[action])
        candidate=t.write('reports/candidate.json',{'id':'synthetic-row','content_zh':'synthetic answer'})
        rollback=t.write('reports/backup.json',{'id':'synthetic-row','content_zh':'before'})
        cp=w.file_digest(self.root,candidate);bp=w.file_digest(self.root,rollback)
        payload=w.sha256_value({'content_zh':'synthetic answer'})
        check={**action,'status':'PASS','candidate':cp,'payload_sha256':payload,
               'expected_updated_at':'2026-10-01T00:00:00+00:00','record_id':'synthetic-row',
               'changed_fields':['content_zh'],'executor_department':'publishing','production_write_allowed':False}
        check_path=t.write('reports/selfcheck.json',check)
        facts=t.write('reports/facts.json',{'synthetic':True});restore=t.write('reports/rollback-plan.json',{'synthetic':True})
        pf={**action,'risk_level':risk,'payload_sha256':payload,'facts':w.file_digest(self.root,facts),
            'self_check':w.file_digest(self.root,check_path),'backup':bp,'rollback':w.file_digest(self.root,restore)}
        path=t.write('reports/preflight.json',pf);runtime.record_preflight(self.root,t.task_id,path)
        target={'task_id':t.task_id,'action_id':action['action_id'],'scope':scope,'execution_owner':'publishing',
                'candidate_version':'v1','candidate_shape':'isolated_native_fixture','changed_fields':['content_zh'],
                'candidate':[candidate,cp['sha256']],'rollback':[rollback,bp['sha256']],
                'expected_updated_at':check['expected_updated_at'],'record_id':'synthetic-row','payload_sha256':payload}
        return target,pf

    def test_committed_selfcheck_enters_protected_channel_without_full_goal_PASS(self):
        target,_=self.ordinary_goal()
        with mock.patch.object(cms,'validate_candidate_binding'),mock.patch.object(w,'_chat_binding_healthy',return_value=True),\
             mock.patch('qa_review_plan.validate_verdict',side_effect=AssertionError('full goal PASS must not precede Save')):
            accepted=cms.validate_goal_cms_acceptance(self.root,target,'publish')
        self.assertEqual(accepted['verdict'],'selfcheck_ready');self.assertIsNone(accepted['review_plan'])
        self.assertFalse(accepted['goal_completion_claimed']);self.assertTrue(accepted['final_assistant_acceptance_required'])
        self.assertFalse(w.read_jsonl(w.receipts_path(self.root,target['task_id'])))

    def test_missing_legacy_goal_mode_uses_validated_default_without_rewriting_contract(self):
        target,_=self.ordinary_goal();p=w.snapshot_path(self.root,target['task_id'])
        snap=w.read_json(p);snap['goal_delivery'].pop('execution_mode')
        w.append_workflow_event(self.root,target['task_id'],snap['current_state'],{'goal_delivery':snap['goal_delivery']})
        w.atomic_write_json(p,snap);before=p.read_bytes()
        with mock.patch.object(cms,'validate_candidate_binding'),mock.patch.object(w,'_chat_binding_healthy',return_value=True),\
             mock.patch('qa_review_plan.validate_verdict',side_effect=AssertionError('missing default must not require old review')):
            result=cms.validate_goal_cms_acceptance(self.root,target,'publish')
        self.assertEqual(result['verdict'],'selfcheck_ready');self.assertEqual(before,p.read_bytes())

    def test_original_EN2_desired_digest_is_consumed_without_modifying_target(self):
        target,_=self.ordinary_goal();target['candidate_shape']='english_kitchen_en2_exact'
        target['desired_fields_sha256']=target.pop('payload_sha256');before=copy.deepcopy(target)
        with mock.patch.object(cms,'validate_candidate_binding'),mock.patch.object(w,'_chat_binding_healthy',return_value=True):
            self.assertEqual(cms.validate_goal_cms_acceptance(self.root,target,'publish')['verdict'],'selfcheck_ready')
        self.assertEqual(target,before)
        target['payload_sha256']='b'*64
        with mock.patch.object(cms,'validate_candidate_binding'),mock.patch.object(w,'_chat_binding_healthy',return_value=True),\
             self.assertRaisesRegex(cms.PermitEvidenceError,'aliases cannot disagree'):
            cms.validate_goal_cms_acceptance(self.root,target,'publish')

    def test_EN2_missing_or_changed_digest_and_explicit_legacy_still_reject(self):
        target,_=self.ordinary_goal();digest=target.pop('payload_sha256');target['candidate_shape']='english_kitchen_en2_exact'
        for changed in (None,'b'*64):
            target['desired_fields_sha256']=changed
            with mock.patch.object(cms,'validate_candidate_binding'),mock.patch.object(w,'_chat_binding_healthy',return_value=True),\
                 self.assertRaisesRegex(cms.PermitEvidenceError,'exact payload'):
                cms.validate_goal_cms_acceptance(self.root,target,'publish')
        target['desired_fields_sha256']=digest
        snap=w.read_json(w.snapshot_path(self.root,target['task_id']));snap['goal_delivery']['execution_mode']='legacy_exact_gate'
        w.append_workflow_event(self.root,target['task_id'],snap['current_state'],{'goal_delivery':snap['goal_delivery']})
        w.atomic_write_json(w.snapshot_path(self.root,target['task_id']),snap)
        with mock.patch.object(cms,'validate_candidate_binding'),mock.patch.object(w,'_chat_binding_healthy',return_value=True),\
             mock.patch.object(cms,'_authorized_cms_selfcheck',side_effect=AssertionError('explicit legacy must remain old exact path')),\
             self.assertRaisesRegex(cms.PermitEvidenceError,'review plan missing'):
            cms.validate_goal_cms_acceptance(self.root,target,'publish')

    def test_sensitive_risk_and_changed_row_cannot_use_ordinary_admission(self):
        target,_=self.ordinary_goal('R3')
        with mock.patch.object(cms,'validate_candidate_binding'),mock.patch.object(w,'_chat_binding_healthy',return_value=True),\
             mock.patch.object(cms,'_authorized_cms_selfcheck',side_effect=AssertionError('R3 must retain its original gate')),\
             self.assertRaisesRegex(cms.PermitEvidenceError,'review plan missing'):
            cms.validate_goal_cms_acceptance(self.root,target,'publish')

    def test_rollback_retains_existing_gate_instead_of_entering_forward_selfcheck(self):
        target,_=self.ordinary_goal()
        with mock.patch.object(cms,'validate_candidate_binding'),mock.patch.object(w,'_chat_binding_healthy',return_value=True),\
             mock.patch.object(cms,'_authorized_cms_selfcheck',side_effect=AssertionError('rollback must retain its original gate')),\
             self.assertRaisesRegex(cms.PermitEvidenceError,'review plan missing'):
            cms.validate_goal_cms_acceptance(self.root,target,'rollback')

    def test_stale_candidate_field_or_changed_selfcheck_source_is_rejected(self):
        target,pf=self.ordinary_goal()
        with mock.patch.object(cms,'validate_candidate_binding'),mock.patch.object(w,'_chat_binding_healthy',return_value=True):
            for changed in ({'changed_fields':['content_en']},{'expected_updated_at':'new-version'},{'payload_sha256':'b'*64}):
                with self.subTest(changed=changed),self.assertRaises(cms.PermitEvidenceError):
                    cms.validate_goal_cms_acceptance(self.root,{**target,**changed},'publish')
            (self.root/pf['self_check']['path']).write_text('{}')
            with self.assertRaises(w.WorkflowError):cms.validate_goal_cms_acceptance(self.root,target,'publish')

    def test_readiness_is_not_final_qa_and_wrong_target_cannot_inherit_it(self):
        target={'task_id':'new-goal','scope':'exact','candidate':['candidate.json','a'*64]}
        accepted={'acceptance_model':cms.SELF_CHECK_EXECUTION_MODEL,'verdict':'selfcheck_ready',
                  'task_id':'new-goal','scope':'exact','candidate':{'sha256':'a'*64},
                  'execution_preflight_event_id':'real-event','goal_completion_claimed':False}
        cms.validate_new_permit_target(target,assistant_acceptance=accepted)
        for change in ({'task_id':'closed-old'},{'scope':'other'},{'goal_completion_claimed':True},
                       {'verdict':'pass'},{'execution_preflight_event_id':None}):
            with self.subTest(change=change),self.assertRaises(cms.PermitEvidenceError):
                cms.validate_new_permit_target(target,assistant_acceptance={**accepted,**change})

    def test_executor_decision_consumes_original_selfcheck_not_assistant_pass(self):
        now=dt.datetime.now(dt.timezone.utc)
        target={'task_id':'t','action_id':'a','scope':'s','candidate_version':'v','record_id':'r','payload_sha256':'a'*64}
        accepted={'acceptance_model':cms.SELF_CHECK_EXECUTION_MODEL,'authorization_pin':{'actual':'authority'},
                  'execution_preflight':{'actual':'check'},'execution_preflight_event_id':'real-event',
                  'created_at':(now-dt.timedelta(seconds=1)).isoformat()}
        decision={**target,'department':'publishing','decision':'EXECUTE_ORIGINAL_AUTHORIZED_ACTION',
                  'action_class':'cms_write','authorization_pin':accepted['authorization_pin'],
                  'execution_preflight':accepted['execution_preflight'],'execution_preflight_event_id':'real-event',
                  'decision_id':'executor-readiness','decided_at':now.isoformat()}
        cms.validate_goal_cms_decision(None,decision,target,'publish','a'*64,accepted,now)
        for changes in ({'department':'operations-assistant-2'},{'execution_preflight_event_id':'other'},
                        {'payload_sha256':'b'*64}):
            with self.subTest(changes=changes),self.assertRaises(cms.PermitEvidenceError):
                cms.validate_goal_cms_decision(None,{**decision,**changes},target,'publish','a'*64,accepted,now)
        with self.assertRaises(cms.PermitEvidenceError):
            cms.validate_goal_cms_decision(None,decision,target,'rollback','a'*64,accepted,now)


class ProfessionalCMSCatalogLifecycleTests(unittest.TestCase):
    setUp=fixture.GoalRuntimeConsumerTests.setUp
    write=fixture.GoalRuntimeConsumerTests.write
    make_goal=fixture.GoalRuntimeConsumerTests.make_goal
    initialize=fixture.GoalRuntimeConsumerTests.initialize
    snapshot=fixture.GoalRuntimeConsumerTests.snapshot

    def catalog_source(self,state):
        import professional_cms_issuer as issuer
        self.initialize()
        # Synthetic terminal state and source stay entirely in .test-tmp.
        # An incomplete source may never enter the active execution catalog.
        pin=w.file_digest(self.root,self.write('reports/synthetic-issuer-source.json',{
            'fixture_only':True,'schema':'professional-cms-issuer-contract/v1','task_id':self.task_id}))
        snapshot=self.snapshot();snapshot['current_state']=state
        w.atomic_write_json(w.snapshot_path(self.root,self.task_id),snapshot)
        w.append_workflow_event(self.root,self.task_id,state,{issuer.EVENT:pin})
        return issuer,pin

    def test_terminal_goal_keeps_history_and_refuses_new_forward_or_inverse(self):
        issuer,pin=self.catalog_source('closed')
        source_before=(self.root/w.WORKFLOW_EVENTS).read_bytes()
        for state in sorted(w.TERMINAL_STATES):
            snapshot=self.snapshot();snapshot['current_state']=state
            w.atomic_write_json(w.snapshot_path(self.root,self.task_id),snapshot)
            with self.subTest(state=state):
                self.assertEqual(issuer.targets(self.root),{})
                for op in ('publish','rollback'):
                    with self.assertRaises(w.WorkflowError):
                        issuer.acceptance(self.root,{'candidate_version':'closed-target'},op)
                self.assertEqual(w.file_digest(self.root,pin['path']),pin)
                self.assertEqual((self.root/w.WORKFLOW_EVENTS).read_bytes(),source_before)

    def test_unverified_active_source_is_not_silently_admitted(self):
        issuer,_=self.catalog_source('producer_working')
        with self.assertRaises((w.WorkflowError,KeyError)):
            issuer.targets(self.root)



if __name__=='__main__':unittest.main()
