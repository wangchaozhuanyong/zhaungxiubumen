"""Boundary intake tests: real isolated ledgers, no provider or production writes."""
import unittest
from unittest import mock
import goal_continuity as c
import result_coordination as rc
import workflow_control as w
import test_goal_continuity as fixtures


class WorkBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.fixture=fixtures.ContinuityTests('runTest');self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups);self.root=self.fixture.root
        self.role='operations-assistant-2'

    def test_frozen_arrival_blocks_false_no_change_without_sending(self):
        identity,request,_=self.fixture.ready();w.record_result_handoff(self.root,request)
        result=c.work_boundary(self.root,self.role,read_assignment=False)
        self.assertFalse(result['can_report_no_change'])
        self.assertEqual(result['ready_actions'][0]['result_sha256'],identity['result_sha256'])
        self.assertEqual(result['messages_sent'],0);self.assertFalse(result['inventory_is_permission'])

    def test_unfinished_assignment_resumes_before_maintenance(self):
        self.fixture.t.initialize()
        assignment={'task_id':self.fixture.t.task_id,'resume_required':True}
        result=c.work_boundary(self.root,self.role,assignment=assignment,read_assignment=False)
        self.assertEqual(result['ready_actions'][0]['next_action'],'reconcile_original_unfinished_scope')
        self.assertTrue(result['resume_before_maintenance'])

    def test_completed_assignment_does_not_keep_headquarters_waiting(self):
        result=c.work_boundary(self.root,self.role,assignment={'task_id':'done','resume_required':False},read_assignment=False)
        self.assertTrue(result['can_report_no_change']);self.assertFalse(result['HQ_continuous_watch_required'])

    def test_busy_notice_is_waiting_not_immediate_work(self):
        notice={'identity':{'task_id':'test-notice'},'delivery_owner':self.role,
                'actionable':False,'next_action':'refresh_busy_target_at_next_legal_opportunity'}
        with mock.patch.object(rc,'notification_plan',return_value={'notifications':[notice],'errors':[]}):
            result=c.work_boundary(self.root,self.role,read_assignment=False)
        self.assertEqual(result['actionable_count'],0);self.assertTrue(result['can_report_no_change'])
        self.assertEqual(len(result['waiting_actions']),1)

    def test_received_hq_knowledge_needs_no_second_decision(self):
        self.fixture.t.initialize()
        task=self.fixture.t.task_id
        rows=[{'task_id':task,'sender_department':self.role,'candidate_version':'v1',
               'result_sha256':'a'*64,'event':event} for event in ['notification_queued','controller_received']]
        with mock.patch.object(w,'_result_handoff_rows',return_value=rows),mock.patch.object(rc,'notification_plan',return_value={'notifications':[],'errors':[]}):
            (self.root/w.RESULT_HANDOFF_DIR).mkdir(parents=True,exist_ok=True)
            (self.root/w.RESULT_HANDOFF_DIR/(task+'.jsonl')).write_text('')
            result=c.work_boundary(self.root,'operations',read_assignment=False)
        self.assertEqual(result['actionable_count'],0);self.assertTrue(result['can_report_no_change'])

    def test_one_damaged_task_does_not_hide_frozen_arrival(self):
        identity,request,_=self.fixture.ready();w.record_result_handoff(self.root,request)
        bad='bad-goal-boundary';snap=w.read_json(w.snapshot_path(self.root,identity['task_id']))
        snap['task_id']=bad;w.atomic_write_json(w.snapshot_path(self.root,bad),snap)
        (self.root/w.RESULT_HANDOFF_DIR/(bad+'.jsonl')).write_text('{invalid}\n')
        result=c.work_boundary(self.root,self.role,read_assignment=False)
        self.assertTrue(result['ready_actions']);self.assertTrue(result['source_errors'])
        self.assertFalse(result['source_errors'][0]['blocks_other_tasks'])

    def test_other_role_damaged_history_does_not_block_boundary(self):
        task='other-boundary';w.atomic_write_json(w.snapshot_path(self.root,task),
            {'goal_delivery':{'responsible_assistant':'operations-assistant-3','producer_departments':['visual-design-video']}})
        (self.root/w.RESULT_HANDOFF_DIR).mkdir(parents=True,exist_ok=True)
        (self.root/w.RESULT_HANDOFF_DIR/(task+'.jsonl')).write_text('{invalid}\n')
        result=c.work_boundary(self.root,self.role,read_assignment=False)
        self.assertTrue(result['can_report_no_change']);self.assertEqual(result['source_errors'],[])

    def test_knowledge_inventory_resolves_only_proven_actual_intake(self):
        item={'task_id':'test-hq','sender_department':self.role,'candidate_version':'v1',
              'result_sha256':'a'*64,'received':True,'queued':True}
        queue={'results':[item],'followthrough_results':[],'pending_count':1}
        with mock.patch.object(w,'result_handoff_pending',return_value=queue),mock.patch.object(rc,'result_lane',return_value={'lane':'HQ_knowledge'}),mock.patch.object(rc,'hq_knowledge_source',return_value={}),mock.patch.object(rc,'_received_delivery',return_value={'record_id':'real-intake'}):
            result=c.pending_intake(self.root)
        self.assertEqual(result['pending_count'],0)
        self.assertFalse(result['received_HQ_knowledge_without_second_review'][0]['formal_decision_fabricated'])

    def test_changed_knowledge_proof_stays_pending_without_hiding_other_work(self):
        item={'task_id':'test-hq','sender_department':self.role,'candidate_version':'v1',
              'result_sha256':'a'*64,'received':True,'queued':True}
        queue={'results':[item],'followthrough_results':[],'pending_count':1}
        with mock.patch.object(w,'result_handoff_pending',return_value=queue),mock.patch.object(rc,'result_lane',return_value={'lane':'HQ_knowledge'}),mock.patch.object(rc,'hq_knowledge_source',side_effect=w.WorkflowError('changed exact source')):
            result=c.pending_intake(self.root)
        self.assertEqual(result['pending_count'],1);self.assertTrue(result['knowledge_source_errors'])

    def test_partial_bundle_rejects_fake_pass_and_missing_next_action(self):
        pin={'path':'reports/absent.json','sha256':'a'*64,'size':0}
        for status in [{'qa_verdict':'pass'},{'goal_completion_claimed':True},{'production_write_allowed':True}]:
            with self.subTest(status=status),self.assertRaises(w.WorkflowError):
                rc.assistant_decision_bundle(self.root,{'status':'partial','qa_verdict':'NOT_VERIFIED',
                    'goal_completion_claimed':False,'production_write_allowed':False,
                    'external_permission_issued':False,'assistant_decision_bundle':pin,'evidence':[pin],**status},
                    {'producer_departments':['content-organic-website']},self.role)

    def test_partial_bundle_does_not_admit_unrelated_producer_or_uncommitted_decision(self):
        identity={'task_id':'goal-consumer-test-001','sender_department':'content-organic-website',
                  'candidate_version':'v1','result_sha256':'a'*64}
        path=self.fixture.t.write('reports/bundle.json',{'schema':'assistant-actual-decision-bundle/v1',
            'items':[{'identity':identity,'decision_record_id':'missing','followthrough_record_id':'missing'}]})
        pin=w.file_digest(self.root,path);box={'status':'partial','qa_verdict':'NOT_VERIFIED',
             'goal_completion_claimed':False,'production_write_allowed':False,'external_permission_issued':False,
             'assistant_decision_bundle':pin,'evidence':[pin]}
        with self.assertRaises(w.WorkflowError):
            rc.assistant_decision_bundle(self.root,box,{'producer_departments':['paid-growth-data']},self.role)
        with mock.patch.object(rc,'result_lane',return_value={'lane':'professional_acceptance','target_department':self.role}),mock.patch.object(rc,'_validate_queued',return_value={}):
            with self.assertRaises(w.WorkflowError):
                rc.assistant_decision_bundle(self.root,box,{'producer_departments':['content-organic-website']},self.role)

    def test_owner_result_return_admission_is_exact_and_cannot_grant_execution(self):
        identity={'task_id':'owner-result','sender_department':'content-organic-website',
                  'candidate_version':'v1','result_sha256':'a'*64}
        contract=w.read_json(self.root/'data/task-contract.json')
        contract.setdefault('result_handoff_contract',{})['owner_direct_return_sources']=[{
            'identity':identity,'execution_rights_granted':True}]
        w.atomic_write_json(self.root/'data/task-contract.json',contract)
        self.assertIsNone(rc.supplemental_owner_return_source(self.root,{**identity,'candidate_version':'v2'}))
        with self.assertRaises(w.WorkflowError):rc.supplemental_owner_return_source(self.root,identity)


if __name__=='__main__':unittest.main()
