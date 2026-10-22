"""Bounded readonly-source and isolated transition regressions; no real QA writes."""
import copy
import json
from pathlib import Path
from unittest import TestCase, mock
import workflow_control as w
import qa_review_plan as q
import owner_adopted_pilot_consumer as c

ROOT = next(p for p in Path(__file__).resolve().parents if (p/'tools/workflow_control.py').is_file())
BASE = ROOT/'logs/handoffs/2026-10-20-clean-department-window-rotation-v1/operations/unfinished-business-followthrough-20261021-v1/owner-delegated-nonpayment-decisions-system-repair-v1'
D = BASE/'system-development-pilot-consumer-rework-v1'
A = BASE/'operations-assistant-2-independent-review-v1'


class AdoptedPilotConsumerTests(TestCase):
    def setUp(self):
        self.snapshot=w.read_json(w.snapshot_path(ROOT,c.TASK))
        self.rows=w.read_jsonl(w.receipts_path(ROOT,c.TASK))
        self.item=w.read_json(D/'ACTUAL-QUEUED-REWORK-ASSIGNMENT-v1.json')
        self.notice=w.read_json(D/'ACTUAL-ORIGINAL-PILOT-NOTIFICATION-INPUT-v1.json')
        self.received=next(x for x in w._result_handoff_rows(ROOT,c.TASK)if x['record_id']=='81ae7049-860f-43af-9827-f8275d187cf5')

    def test_actual_queued_continuation_resumes_original_receipt_without_new_dispatch_or_ACK(self):
        before=w.receipts_path(ROOT,c.TASK).read_bytes()
        _,row=c.queued_rework_source(ROOT,self.item)
        self.assertEqual(row['receipt_id'],'7ba27f6f-52e4-40b1-ae2e-cfb621467073')
        self.assertEqual(before,w.receipts_path(ROOT,c.TASK).read_bytes())

    def test_wrong_queued_role_scope_contract_or_authority_rejected(self):
        for key,value in [('sender_department','operations-assistant'),('department','operations-assistant-2'),
                          ('scope','project:flashcast:other:v1'),('action_id','wrong-action'),
                          ('goal_contract',self.item['authorization_pin']),('authorization_pin',self.item['goal_contract'])]:
            with self.subTest(key=key),self.assertRaises(w.WorkflowError):
                c.queued_rework_source(ROOT,{**self.item,key:value})

    def test_queued_transport_without_actual_recipient_or_ACK_rejected(self):
        for key in ('receiver_turn_id','receiver_message_id','ack_message_id','queue_message_id','source_call_id'):
            with self.subTest(key=key),self.assertRaises(w.WorkflowError):
                c.queued_rework_source(ROOT,{**self.item,key:'00000000-0000-0000-0000-000000000000'})

    def test_queued_rework_cannot_be_registered_as_another_original_dispatch_ACK(self):
        with self.assertRaisesRegex(w.WorkflowError,'existing original assignment'):
            c.queued_rework_source(ROOT,self.item,require_dispatch=False)

    def test_wrong_fixed_native_role_project_cwd_or_title_rejected(self):
        bind=c._binding(ROOT,c.ROLE)
        for field,value in [('id',c._binding(ROOT,c.PRODUCER)['task_id']),('cwd','/unrelated-project'),('title','wrong fixed title')]:
            with self.subTest(field=field),self.assertRaises(w.WorkflowError):
                page={'thread':{'id':bind['task_id'],'title':bind['title'],'cwd':bind['cwd']}}
                page['thread'][field]=value;c._binding(ROOT,c.ROLE,page)

    def test_parent_child_scope_authority_or_producer_contract_tamper_rejected(self):
        for field,value in [('parent_task_id','fc-unrelated-parent'),('responsible_assistant','operations-assistant'),
                            ('authorized_scope',['project:flashcast:other:v1']),('producer_departments',[c.ROLE]),
                            ('production_write_allowed',True),('external_permission_issued',True)]:
            with self.subTest(field=field),self.assertRaises(w.WorkflowError):
                changed=copy.deepcopy(self.snapshot);changed['goal_delivery'][field]=value;c._core(ROOT,changed)

    def test_missing_committed_intake_cannot_be_inferred_from_queued_source(self):
        rows=[x for x in w._result_handoff_rows(ROOT,c.TASK)if x.get('event')!='controller_received']
        with self.assertRaises(w.WorkflowError):c._received(ROOT,rows,self.received['outbox'])

    def test_nonunique_or_changed_actual_intake_rejected(self):
        rows=w._result_handoff_rows(ROOT,c.TASK)
        with self.assertRaises(w.WorkflowError):c._received(ROOT,rows+[self.received],self.received['outbox'])
        altered={**self.received,'created_at':'2000-01-01T00:00:00+00:00'}
        with self.assertRaises(w.WorkflowError):c._received(ROOT,[altered],altered['outbox'])

    def test_actual_queue_input_and_committed_intake_is_truthful_notice(self):
        actual=c.received_notification(ROOT,self.snapshot,self.received,self.notice)
        self.assertEqual(actual['notification_representation'],'actual_official_queue_received')
        self.assertFalse(actual['notification_sent_fabricated'])

    def test_queue_accepted_or_queued_row_alone_is_not_notification(self):
        row=next(x for x in w._result_handoff_rows(ROOT,c.TASK)if x.get('event')=='notification_queued')
        with self.assertRaises(w.WorkflowError):c.received_notification(ROOT,self.snapshot,row,self.notice)

    def test_wrong_actual_notice_input_or_missing_native_source_rejected(self):
        for patch in ({'receiver_message_id':'wrong-input'}, {'receiver_turn_id':'wrong-turn'},
                      {'mode':'queue_acceptance'}, {'native_recipient':self.item['actual_native_recipient']}):
            with self.subTest(patch=patch),self.assertRaises(w.WorkflowError):
                c.received_notification(ROOT,self.snapshot,self.received,{**self.notice,**patch})

    def test_wrong_notice_receiver_or_intake_identity_rejected(self):
        for patch in ({'coordinator_role':c.PRODUCER},{'intake_mode':'notification'},
                      {'task_id':c.PARENT},{'sender_department':c.ROLE}):
            with self.subTest(patch=patch),self.assertRaises(w.WorkflowError):
                c.received_notification(ROOT,self.snapshot,{**self.received,**patch},self.notice)

    def test_receipt_prefix_and_later_handoff_hash_corruption_rejected(self):
        with self.assertRaises(w.WorkflowError):c._rows(ROOT,c.TASK,[{**self.rows[0],'receipt_hash':'0'*64}])
        rows=w._result_handoff_rows(ROOT,c.TASK);changed=copy.deepcopy(rows);changed[-1]['record_hash']='0'*64
        with mock.patch.object(w,'_result_handoff_rows',return_value=changed),self.assertRaises(w.WorkflowError):
            c._handoffs(ROOT,c.TASK)

    def test_failed_queue_wrong_policy_payload_target_or_time_is_not_delivery(self):
        directory=A/'owner-pilot-admission-rework-official-queue-v1';intent=w.read_json(directory/'native-queue-intent.json');result=w.read_json(directory/'native-queue-result.json');target=c._binding(ROOT,c.PRODUCER)
        for patch in ({'exit_code':1},{'exit_code':False},{'payload_sha256':'0'*64},{'policy_decision_id':'wrong-policy'},
                      {'thread_id':c._binding(ROOT,c.ROLE)['task_id']},{'finished_at':'2000-01-01T00:00:00+00:00'}):
            with self.subTest(patch=patch),self.assertRaises(w.WorkflowError):
                c._queue_effect(ROOT,self.item['payload'],intent['policy_decision_id'],intent,{**result,**patch},target,self.item['queue_message_id'])

    def transition(self):
        old=w.read_json(A/'OWNER-REAL-PILOT-A2-NORMAL-REVIEW-PLAN-v1.json')
        pin=w.file_digest(ROOT,str((A/'OWNER-REAL-PILOT-A2-NORMAL-REVIEW-PLAN-v1.json').relative_to(ROOT)))
        plan=copy.deepcopy(old);plan.update(candidate_version='isolated-unit-new-version',candidate_sha256='a'*64,
            candidate={'path':'isolated-unit-new-manifest.json','sha256':'a'*64,'size':1},
            pre_admission_rework={'mode':'same_original_adopted_pilot_admission_repair','previous_plan':pin,
                'diagnosis':w.file_digest(ROOT,str((A/'A2-OWNER-PILOT-EXACT-INHERITED-REVIEW-ADMISSION-REJECTION-v1.json').relative_to(ROOT))),
                'decision_record_id':'ecd9198b-fa60-484c-a8cf-fcadbb5b7a10'},changed_scope=[c.SCOPE],
            evidence_diff={'previous_candidate':old['candidate'],'candidate':{'path':'isolated-unit-new-manifest.json','sha256':'a'*64,'size':1},'summary':'isolated transition only'},
            revalidation_methods={c.SCOPE:'isolated new-consumer tests; old seven executions reused'})
        binding={'pin':pin,'reviewer_department':c.ROLE};return plan,binding

    def test_real_unverdicted_failure_transition_needs_no_fabricated_blocked_QA(self):
        plan,binding=self.transition()
        with mock.patch.object(c,'review_context',return_value={'isolated_source_fixture':True}):
            value=c.admission_rework(ROOT,self.snapshot,self.rows,binding,plan)
        self.assertFalse(value['old_verdict_migrated']);self.assertEqual(value['receipt_prefix_length'],len(self.rows))

    def test_existing_PASS_or_blocked_or_reviewer_outbox_cannot_use_pre_admission_transition(self):
        plan,binding=self.transition()
        for kind,verdict in [('qa_verdict','pass'),('qa_verdict','blocked'),('outbox_received','')]:
            with self.subTest(kind=kind,verdict=verdict),self.assertRaises(w.WorkflowError):
                c.admission_rework(ROOT,self.snapshot,self.rows+[{'department':c.ROLE,'receipt_type':kind,'verdict':verdict}],binding,plan)

    def test_wrong_predecessor_identity_delta_or_decision_rejected(self):
        plan,binding=self.transition()
        variants=[{'reviewer_department':c.PRODUCER},{'scope':'project:flashcast:other:v1'},
                  {'candidate_version':w.read_json(A/'OWNER-REAL-PILOT-A2-NORMAL-REVIEW-PLAN-v1.json')['candidate_version']},
                  {'changed_scope':[]},{'rework_of':'invented-blocked-QA'}]
        for patch in variants:
            with self.subTest(patch=patch),self.assertRaises(w.WorkflowError):
                c.admission_rework(ROOT,self.snapshot,self.rows,binding,{**plan,**patch})
        altered=copy.deepcopy(plan);altered['pre_admission_rework']['decision_record_id']='missing'
        with self.assertRaises(w.WorkflowError):c.admission_rework(ROOT,self.snapshot,self.rows,binding,altered)

    def test_later_real_QA_does_not_invalidate_its_authenticated_pre_admission_boundary(self):
        plan,binding=self.transition()
        with mock.patch.object(c,'review_context',return_value={'isolated_source_fixture':True}):
            stage=c.admission_rework(ROOT,self.snapshot,self.rows,binding,plan)
            event={'task_id':c.TASK,'details':{'qa_review_plan_bound':{'pin':{'path':'unit-new-plan.json','sha256':'b'*64,'size':1},'pre_admission_rework':plan['pre_admission_rework']},'pre_admission_rework':stage}}
            actual=w.read_jsonl
            def read(path):return actual(path)+[event]if Path(path)==ROOT/w.WORKFLOW_EVENTS else actual(path)
            later=self.rows+[{'department':c.ROLE,'receipt_type':'qa_verdict','verdict':'pass'}]
            with mock.patch.object(w,'read_jsonl',side_effect=read):
                result=c.admission_rework(ROOT,self.snapshot,later,binding,plan)
            self.assertEqual(result['receipt_prefix_length'],len(self.rows))

    def test_cross_task_pre_admission_and_source_fallback_refused(self):
        plan,binding=self.transition()
        with self.assertRaises(w.WorkflowError):c.admission_rework(ROOT,{'task_id':c.PARENT},self.rows,binding,plan)
        self.assertIsNone(c.review_context(ROOT,{'task_id':c.PARENT}))
        self.assertIsNone(c.queued_rework_source(ROOT,{**self.item,'task_id':c.PARENT}))
