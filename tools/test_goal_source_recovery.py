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

    def test_declared_external_collaborator_uses_binding_without_becoming_a_department(self):
        request,binding=fixture.GoalRuntimeConsumerTests.collaboration(self)
        snapshot=self.snapshot();goal=snapshot['goal_delivery']
        declaration={'sender_department':goal['primary_owner'],'target_department':'designated-development','scope':request['scope']}
        snapshot['goal_delivery']={**goal,'collaboration_scopes':[declaration]}
        w.append_workflow_event(self.root,self.task_id,snapshot['current_state'],{'goal_delivery':snapshot['goal_delivery']})
        w.atomic_write_json(w.snapshot_path(self.root,self.task_id),snapshot)
        p=self.write('reports/external-current-turn.json',{'thread':{'id':binding['thread_id'],'title':binding['title'],'cwd':binding['cwd']},
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


if __name__=='__main__':unittest.main()
