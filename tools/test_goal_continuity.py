"""Real local entry points with synthetic isolated data; zero native sends."""
import copy
import datetime as dt
import hashlib
import json
import re
from pathlib import Path
import unittest
from unittest import mock
import goal_continuity as c
import goal_delivery_runtime as g
import result_coordination as r
import workflow_control as w
import test_goal_runtime_consumers as fixture
import test_direct_system_repair as notices


class ContinuityTests(unittest.TestCase):
    def setUp(self):
        self.t=fixture.GoalRuntimeConsumerTests('runTest');self.t.setUp()
        self.addCleanup(self.t.doCleanups);self.root=self.t.root

    def ready(self):
        plan,producer=self.t.prepare_initial_review()
        identity={'task_id':self.t.task_id,'sender_department':fixture.PRODUCER,
                  'candidate_version':'v1','result_sha256':producer['sha256']}
        declaration={**identity,'outbox_path':producer['path'],'batch_complete':True}
        text='Finished the whole synthetic batch.\n'+c.READY_MARKER+json.dumps(declaration)+'\n'
        (self.root/'reports/ready.txt').write_text(text)
        binding=w.department_registry(self.root)[fixture.PRODUCER]['chat_binding']
        page={'thread':{'id':binding['task_id'],'title':binding['title'],'cwd':binding['cwd']},
              'turns':[{'id':'ready-turn','status':'inProgress','error':None,
                        'startedAt':int(dt.datetime.now(dt.timezone.utc).timestamp())-1,
                        'items':[{'type':'agentMessage','id':'ready-message','phase':'commentary','text':text}]}]}
        path=self.t.write('reports/ready-native.json',page)
        request={**identity,'event':'notification_queued','idempotency_key':'ready-one',
                 'outbox_path':producer['path'],'result_source_phase':'delivery_ready',
                 'source_thread_id':binding['task_id'],'source_turn_id':'ready-turn',
                 'source_message_id':'ready-message','source_reply_sha256':hashlib.sha256(text.encode()).hexdigest(),
                 'reply_observed_at':dt.datetime.now(dt.timezone.utc).isoformat(),
                 'actual_native_completion':w.file_digest(self.root,path),
                 'visible_reply':w.file_digest(self.root,'reports/ready.txt')}
        return identity,request,page

    def queue_notification_request(self,daily=False):
        identity,request,_=self.daily_ready() if daily else self.ready()
        w.record_result_handoff(self.root,request)
        canonical={}
        registry=w.department_registry(self.root)
        for role in (fixture.PRODUCER,fixture.ASSISTANT):
            binding=registry[role]['chat_binding']
            page={'source_transport':'official_app_server_readonly_history',
                  'thread':{'id':binding['task_id'],'title':binding['title'],'cwd':binding['cwd'],'projectId':None,
                            'status':{'type':'notLoaded'}},
                  'turns':[{'id':'persisted-only-turn','status':'completed'}]}
            canonical[role]=w.file_digest(self.root,self.t.write('reports/canonical-'+role+'.json',page))
        proof={'schema':'official-native-queue-identities/v1','identity':identity,
               'target_thread_id':registry[fixture.ASSISTANT]['chat_binding']['task_id'],
               'observed_at':dt.datetime.now(dt.timezone.utc).isoformat(),'canonical_sources':canonical}
        proof=w.file_digest(self.root,self.t.write('reports/native-queue-identities.json',proof))
        message=self.root/'reports/native-result-notice.txt';message.write_text('Original frozen result notice; zero new business authority.')
        return {'task_id':identity['task_id'],'sender_department':fixture.PRODUCER,'result_notification':identity,
                'notification_request_id':'original-result-native-queue','delivery_mode':'official_native_queue',
                'actual_target_state':proof,'payload':w.file_digest(self.root,str(message.relative_to(self.root)))}

    def test_result_queue_entry_uses_original_sender_policy_and_no_busy_inference(self):
        import goal_source_recovery as recovery
        import department_event_dispatcher as dispatcher
        request=self.queue_notification_request()
        with mock.patch.object(dispatcher,'native_queue_capability',return_value='/valid/cli'), \
                mock.patch.object(recovery,'actual_target_turn_status',side_effect=AssertionError('no idle inference')):
            result=recovery.prepare_message(self.root,request)
        self.assertEqual(result['status'],'ready_to_queue',result)
        self.assertEqual(result['policy_decision']['department'],fixture.PRODUCER)
        self.assertTrue(result['policy_decision']['scope'].startswith('department_result:'))
        self.assertFalse(result['ordinary_send_allowed']);self.assertFalse(result['message_sent'])

    def test_scheduled_result_queue_entry_does_not_invent_goal_or_dispatch(self):
        import goal_source_recovery as recovery
        import department_event_dispatcher as dispatcher
        request=self.queue_notification_request(daily=True)
        with mock.patch.object(dispatcher,'native_queue_capability',return_value='/valid/cli'):
            result=recovery.prepare_message(self.root,request)
        self.assertEqual(result['status'],'ready_to_queue',result)
        self.assertFalse(w.snapshot_path(self.root,self.t.task_id).exists())
        self.assertFalse(w.receipts_path(self.root,self.t.task_id).exists())

    def test_native_result_queue_refuses_changed_identity_and_unadmitted_transport(self):
        import goal_source_recovery as recovery
        import department_event_dispatcher as dispatcher
        request=self.queue_notification_request()
        with self.assertRaises(w.WorkflowError):
            recovery.prepare_message(self.root,{**request,'sender_department':'operations'})
        with mock.patch.object(dispatcher,'native_queue_capability',side_effect=ValueError('not admitted')):
            with self.assertRaisesRegex(ValueError,'not admitted'):
                recovery.prepare_message(self.root,request)

    def test_frozen_whole_batch_can_queue_before_turn_ends_once(self):
        identity,request,_=self.ready()
        row,_=w.record_result_handoff(self.root,request)
        self.assertTrue(row['batch_delivery_frozen']);self.assertFalse(row['source_turn_completed'])
        self.assertEqual(w.record_result_handoff(self.root,request)[0]['result'],'duplicate_ignored')
        self.assertFalse(row['business_goal_closed'])

    def test_ready_intake_uses_original_frozen_declaration_without_new_ack(self):
        identity,request,_=self.ready();w.record_result_handoff(self.root,request)
        store=r.CoordinationStore(self.root);self.addCleanup(store.close)
        claim=store.claim(identity,fixture.ASSISTANT,'test-a2','claim-ready')
        receive={**request,'event':'controller_received','idempotency_key':'receive-ready',
                 'intake_mode':'queue','coordinator_role':fixture.ASSISTANT,'coordinator_owner':'test-a2','coordination_claim':claim}
        row,_=w.record_result_handoff(self.root,receive)
        self.assertEqual(row['source_turn_id'],'ready-turn');self.assertTrue(row['batch_delivery_frozen'])

    def test_only_frozen_verified_batch_satisfies_dispatch_dependency(self):
        identity,request,_=self.ready()
        self.assertFalse(c.frozen_dependency_available(self.root,self.t.task_id,fixture.PRODUCER))
        w.record_result_handoff(self.root,request)
        self.assertTrue(c.frozen_dependency_available(self.root,self.t.task_id,fixture.PRODUCER))
        path=self.root/request['outbox_path'];path.write_text('{}')
        self.assertFalse(c.frozen_dependency_available(self.root,self.t.task_id,fixture.PRODUCER))

    def daily_ready(self):
        identity,request,page=self.ready()
        contract=w.read_json(self.root/'data/task-contract.json')
        contract.setdefault('result_handoff_contract',{})['scheduled_daily_sources']=[{
            'automation_id':'test-current-daily','department':fixture.PRODUCER,
            'task_id_pattern':re.escape(self.t.task_id),'responsible_assistant':fixture.ASSISTANT,
            'acceptance_capability':'development'}]
        w.atomic_write_json(self.root/'data/task-contract.json',contract)
        w.snapshot_path(self.root,self.t.task_id).unlink()
        w.receipts_path(self.root,self.t.task_id).unlink()
        now=dt.datetime.now(dt.timezone.utc)
        box=w.read_json(self.root/request['outbox_path'])
        box['reported_at_myt']=(now-dt.timedelta(seconds=2)).isoformat()
        w.atomic_write_json(self.root/request['outbox_path'],box)
        digest=w.file_digest(self.root,request['outbox_path']);identity['result_sha256']=digest['sha256']
        declaration={**identity,'outbox_path':request['outbox_path'],'batch_complete':True}
        text=c.READY_MARKER+json.dumps(declaration)+'\n'
        (self.root/'reports/ready.txt').write_text(text)
        page['turns'][0]['id']='11111111-1111-1111-1111-111111111111'
        page['turns'][0]['items'][0]['text']=text
        w.atomic_write_json(self.root/'reports/ready-native.json',page)
        request.update(**identity,source_mode='scheduled_run',source_automation_id='test-current-daily',
            source_turn_id=page['turns'][0]['id'],source_reply_sha256=hashlib.sha256(text.encode()).hexdigest(),
            visible_reply=w.file_digest(self.root,'reports/ready.txt'),
            actual_native_completion=w.file_digest(self.root,'reports/ready-native.json'))
        return identity,request,page

    def test_daily_batch_can_deliver_before_end_without_fabricated_goal_or_dispatch(self):
        identity,request,_=self.daily_ready()
        row,_=w.record_result_handoff(self.root,request)
        self.assertTrue(row['batch_delivery_frozen']);self.assertFalse(row['source_turn_completed'])
        self.assertFalse(w.snapshot_path(self.root,self.t.task_id).exists())
        self.assertEqual(w.record_result_handoff(self.root,request)[0]['result'],'duplicate_ignored')
        with self.assertRaises(w.WorkflowError):
            w.record_result_handoff(self.root,{**request,'source_automation_id':'wrong-source'})

    def test_daily_idle_backup_routes_and_recovers_without_creating_workflow(self):
        identity,request,_=self.daily_ready();w.record_result_handoff(self.root,request)
        self.shared_methods('operations-assistant')
        self.assertEqual(c.shared_pending(self.root,'operations-assistant')['results'][0]['task_id'],self.t.task_id)
        selection={**identity,'actor':fixture.PRODUCER,
                    'request_id':'daily-resource-select','live_identity':self.live()}
        selected=c.select_result(self.root,selection)
        self.assertEqual(selected['selected'],'operations-assistant')
        self.assertEqual(r.result_lane(self.root,identity)['target_department'],'operations-assistant')
        self.assertFalse(w.snapshot_path(self.root,self.t.task_id).exists())
        self.assertFalse(selected['accepted'])
        self.assertEqual(c.recover_selection(self.root,selection)['selected'],'operations-assistant')

    def test_daily_turn_end_is_additive_without_fabricated_workflow(self):
        identity,request,page=self.daily_ready();w.record_result_handoff(self.root,request)
        page['turns'][0]['status']='completed'
        pin=w.file_digest(self.root,self.t.write('reports/daily-ended.json',page))
        self.assertEqual(c.record_turn_completion(self.root,identity,pin)['result'],'recorded')
        self.assertEqual(c.record_turn_completion(self.root,identity,pin)['result'],'duplicate_ignored')
        self.assertFalse(w.snapshot_path(self.root,self.t.task_id).exists())

    def test_ack_progress_or_changed_result_is_not_frozen_delivery(self):
        _,req,page=self.ready()
        for change in [{'result_sha256':'a'*64},{'source_message_id':'wrong'},{'source_reply_sha256':'b'*64}]:
            with self.subTest(change=change),self.assertRaises(w.WorkflowError):
                c.ready_source(self.root,{**req,**change},req['source_thread_id'])
        page['turns'][0]['items'][0]['text']='ACK: starting work'
        path=self.t.write('reports/ack-only.json',page)
        req['actual_native_completion']=w.file_digest(self.root,path)
        with self.assertRaises(w.WorkflowError):c.ready_source(self.root,req,req['source_thread_id'])

    def test_actual_turn_completion_is_additive_and_idempotent(self):
        identity,req,page=self.ready();w.record_result_handoff(self.root,req)
        page['turns'][0]['status']='completed';page['turns'][0]['completedAt']=dt.datetime.now(dt.timezone.utc).timestamp()
        pin=w.file_digest(self.root,self.t.write('reports/ready-ended.json',page))
        self.assertEqual(c.record_turn_completion(self.root,identity,pin)['result'],'recorded')
        self.assertEqual(c.record_turn_completion(self.root,identity,pin)['result'],'duplicate_ignored')
        source=w._result_handoff_rows(self.root,self.t.task_id)[0]
        self.assertEqual(source['actual_native_completion'],req['actual_native_completion'])

    def test_completed_read_thread_uses_exact_turn_and_authenticates_late_ack(self):
        identity,request,page=self.ready()
        now=dt.datetime.now(dt.timezone.utc);completed=now.timestamp()-1
        ack_text=self.t.task_id+' received the complete original goal'
        ack={'type':'agentMessage','id':'original-ack','phase':'commentary','text':ack_text}
        final_text=self.t.task_id+' original whole delivered result'
        page['turns'][0].update(status='completed',completedAt=completed)
        page['turns'][0]['items']=[ack,{'type':'agentMessage','id':'actual-final','phase':'final_answer','text':final_text}]
        (self.root/'reports/final.txt').write_text(final_text)
        source=self.t.write('reports/exact-completed-source.json',page)
        # Model a late recovery entry with a real original same-turn ACK.
        proof=self.t.write('reports/original-ack.json',{'task_id':self.t.task_id,'department':fixture.PRODUCER,
           'source_thread_id':request['source_thread_id'],'turn':{'id':'ready-turn'},'message':ack})
        rows=w.read_jsonl(w.receipts_path(self.root,self.t.task_id))
        for row in rows:
            if row.get('department')==fixture.PRODUCER and row.get('receipt_type')=='chat_ack':
                row['created_at']=now.isoformat();row['evidence']=[w.file_digest(self.root,proof)]
            else:row['created_at']=(now-dt.timedelta(seconds=3)).isoformat()
        previous=''
        for row in rows:
            row['previous_hash']=previous;row['receipt_hash']=w.sha256_value(w._receipt_payload_for_hash(row));previous=row['receipt_hash']
        w.receipts_path(self.root,self.t.task_id).write_text(''.join(json.dumps(row)+'\n' for row in rows))
        request.update(result_source_phase='completed_final',reply_observed_at=(now+dt.timedelta(microseconds=1)).isoformat(),
            source_reply_sha256=hashlib.sha256(final_text.encode()).hexdigest(),visible_reply=w.file_digest(self.root,'reports/final.txt'),
            actual_native_completion=w.file_digest(self.root,source))
        result=w._validate_goal_completed_result(self.root,request,request['source_thread_id'])
        self.assertEqual(result['source_turn_id'],'ready-turn')
        page['turns'][0]['items'][0]['id']='not-the-actual-ack'
        w.atomic_write_json(self.root/source,page);request['actual_native_completion']=w.file_digest(self.root,source)
        with self.assertRaises(w.WorkflowError):w._validate_goal_completed_result(self.root,request,request['source_thread_id'])

    def live(self,default_status='active',other_status='idle'):
        rows=[]
        for role in ('operations-assistant',fixture.ASSISTANT,'operations-assistant-3'):
            b=w.department_registry(self.root)[role]['chat_binding']
            rows.append({'id':b['task_id'],'title':b['title'],'cwd':b['cwd'],'projectId':b['project_id'],
                         'status':default_status if role==fixture.ASSISTANT else other_status})
        pin=w.file_digest(self.root,self.t.write('reports/select-native.json',{'threads':rows}))
        return w.file_digest(self.root,self.t.write('reports/select-live.json',{
            'observed_at':dt.datetime.now(dt.timezone.utc).isoformat(),'actual_native_observation':pin}))

    def shared_methods(self,role):
        path=self.t.write('reports/shared-method.md.json',{'method':'synthetic complete-result independent review'})
        method=w.file_digest(self.root,path)
        manifest=self.t.write('reports/shared-'+role+'.json',{'production_permissions_inherited':False,
                              'methods':{'development':[method]}})
        registry=w.read_json(self.root/'data/department-registry.json')
        row=next(d for d in registry['departments'] if d['id']==role)
        row['coordination_authority']['shared_review_methods']=w.file_digest(self.root,manifest)
        w.atomic_write_json(self.root/'data/department-registry.json',registry)

    def test_busy_default_routes_once_to_capable_idle_assistant(self):
        identity,req,_=self.ready();w.record_result_handoff(self.root,req)
        self.shared_methods('operations-assistant')
        live=self.live()
        selected=c.select_result(self.root,{**identity,'actor':fixture.PRODUCER,'request_id':'selection-one','live_identity':live})
        self.assertEqual(selected['selected'],'operations-assistant')
        self.assertEqual(self.t.snapshot()['goal_delivery']['responsible_assistant'],'operations-assistant')
        notice=r.notification_plan(self.root,fixture.PRODUCER)['notifications'][0]
        self.assertEqual(notice['route']['target_department'],'operations-assistant')
        self.assertFalse(notice['delivered']);self.assertFalse(selected['accepted'])

    def test_all_busy_waits_without_artificial_future_deadline(self):
        identity,req,_=self.ready();w.record_result_handoff(self.root,req)
        answer=c.selection_plan(self.root,identity,self.live('active','active'))
        self.assertEqual(answer['state'],'shared_waiting');self.assertIsNone(answer['selected'])
        self.assertNotIn('next_check_at',answer)

    def test_existing_claim_retains_unique_owner(self):
        identity,req,_=self.ready();w.record_result_handoff(self.root,req)
        store=r.CoordinationStore(self.root);self.addCleanup(store.close)
        store.claim(identity,fixture.ASSISTANT,'current-reviewer','already-started')
        answer=c.selection_plan(self.root,identity,self.live())
        self.assertEqual(answer['state'],'already_owned');self.assertEqual(answer['selected'],fixture.ASSISTANT)

    def test_expired_same_result_claim_does_not_reserve_assistant(self):
        identity,req,_=self.ready();w.record_result_handoff(self.root,req)
        self.shared_methods('operations-assistant')
        store=r.CoordinationStore(self.root);self.addCleanup(store.close)
        store.claim(identity,fixture.ASSISTANT,'expired-reviewer','expired-start')
        store.conn.execute('UPDATE claims SET expires=0');store.conn.commit()
        answer=c.selection_plan(self.root,identity,self.live())
        self.assertEqual(answer['state'],'ready')
        self.assertEqual(answer['selected'],'operations-assistant')
        self.assertEqual(store.conn.execute('SELECT COUNT(*) FROM claims').fetchone()[0],1)
        selected=c.select_result(self.root,{**identity,'actor':fixture.PRODUCER,
                  'request_id':'expired-lease-real-transfer','live_identity':self.live()})
        self.assertTrue(selected['assignment_committed'])

    def test_expired_unrelated_claim_does_not_make_idle_backup_busy(self):
        identity,req,_=self.ready();w.record_result_handoff(self.root,req)
        self.shared_methods('operations-assistant')
        store=r.CoordinationStore(self.root);self.addCleanup(store.close)
        other={**identity,'candidate_version':'older-unrelated-result'}
        store.claim(identity,fixture.ASSISTANT,'expired-other-reviewer','other-start')
        store.conn.execute("UPDATE claims SET identity_json=?, role='operations-assistant', expires=0", (json.dumps(other),));store.conn.commit()
        answer=c.selection_plan(self.root,identity,self.live())
        self.assertEqual(answer['selected'],'operations-assistant')

    def test_committed_selection_interruption_recovers_without_second_review(self):
        identity,req,_=self.ready();w.record_result_handoff(self.root,req)
        self.shared_methods('operations-assistant')
        request={**identity,'actor':fixture.PRODUCER,'request_id':'selection-interrupted','live_identity':self.live()}
        original=w.atomic_write_json
        def interrupt(path,value):
            if Path(path)==w.snapshot_path(self.root,self.t.task_id):raise RuntimeError('modeled stop after selection commit')
            return original(path,value)
        with mock.patch.object(w,'atomic_write_json',side_effect=interrupt),self.assertRaises(RuntimeError):
            c.select_result(self.root,request)
        answer=c.recover_selection(self.root,request)
        self.assertEqual(answer['selected'],'operations-assistant');self.assertFalse(answer['accepted'])
        self.assertEqual(c.recover_selection(self.root,request)['selected'],'operations-assistant')
        self.assertEqual(len(self.t.snapshot()['goal_delivery']['assignment_history']),1)

    def test_idle_backup_has_shared_inventory_and_can_select_at_own_work_boundary(self):
        identity,req,_=self.ready();w.record_result_handoff(self.root,req)
        self.shared_methods('operations-assistant')
        pool=c.shared_pending(self.root,'operations-assistant')
        self.assertEqual(pool['results'][0]['task_id'],self.t.task_id)
        self.assertFalse(pool['inventory_is_permission'])
        request={**identity,'actor':'operations-assistant','at_work_boundary':True,
                 'request_id':'self-boundary-one','live_identity':self.live('active','active')}
        answer=c.select_result(self.root,request)
        self.assertEqual(answer['selected'],'operations-assistant')
        store=r.CoordinationStore(self.root);self.addCleanup(store.close)
        lease=store.claim(identity,'operations-assistant','boundary-handler','claim-after-select')
        self.assertEqual(lease['role'],'operations-assistant')

    def test_ready_statement_must_be_complete_not_a_small_progress_step(self):
        _,request,page=self.ready()
        text=page['turns'][0]['items'][0]['text'].replace('"batch_complete": true','"batch_complete": false')
        page['turns'][0]['items'][0]['text']=text
        (self.root/'reports/not-complete.txt').write_text(text)
        request.update(visible_reply=w.file_digest(self.root,'reports/not-complete.txt'),
                       source_reply_sha256=hashlib.sha256(text.encode()).hexdigest(),
                       actual_native_completion=w.file_digest(self.root,self.t.write('reports/not-complete.json',page)))
        with self.assertRaisesRegex(w.WorkflowError,'complete batch'):
            c.ready_source(self.root,request,request['source_thread_id'])

    def test_changed_shared_method_cannot_grant_backup_capability(self):
        self.shared_methods('operations-assistant')
        goal=fixture.GoalRuntimeConsumerTests.make_goal(self.t)
        self.assertTrue(c.shared_capable(self.root,'operations-assistant',goal))
        (self.root/'reports/shared-method.md.json').write_text('{}')
        self.assertFalse(c.shared_capable(self.root,'operations-assistant',goal))

    def test_shared_skill_requires_real_aligned_path_and_unchanged_bytes(self):
        role='operations-assistant';self.shared_methods(role)
        path=self.root/'reports/installed-method/SKILL.md';path.parent.mkdir();path.write_text('synthetic independent method')
        resource={'path':str(path),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'size':path.stat().st_size}
        registry=w.read_json(self.root/'data/department-registry.json');row=next(x for x in registry['departments'] if x['id']==role)
        row.update(approved_subskills=['renovation-seo-geo'],approved_subskill_paths=[str(path)])
        manifest=self.root/row['coordination_authority']['shared_review_methods']['path'];doc=w.read_json(manifest)
        doc.update(resources={'renovation-seo-geo':resource},method_skill_requirements={'development':['renovation-seo-geo']})
        w.atomic_write_json(manifest,doc);row['coordination_authority']['shared_review_methods']=w.file_digest(self.root,w.rel_path(self.root,manifest))
        w.atomic_write_json(self.root/'data/department-registry.json',registry)
        goal=self.t.make_goal()
        self.assertTrue(c.shared_capable(self.root,role,goal))
        path.write_text('changed method');self.assertFalse(c.shared_capable(self.root,role,goal))
        path.write_text('synthetic independent method');row['approved_subskill_paths']=[]
        w.atomic_write_json(self.root/'data/department-registry.json',registry)
        self.assertFalse(c.shared_capable(self.root,role,goal))

    def assignment(self,role=fixture.PRODUCER,initialize=True):
        if initialize:self.t.initialize()
        payload='reports/assignment.txt';(self.root/payload).write_text(self.t.task_id+' complete original goal')
        pin=w.file_digest(self.root,payload)
        req=self.t.requested(sender='operations',target=role,payload=pin,
                             scope=self.t.snapshot()['goal_delivery']['authorized_scope'][0])
        decision=self.t.policy(req)
        sent=self.t.fixture.receipt('dispatch_sent',role,'assignment-send',
             policy_decision_id=decision['decision_id'],action_id=req['action_id'],action_class='thread_message',scope=req['scope'])
        self.t.fixture.receipt('chat_ack',role,'assignment-ack')
        binding=w.department_registry(self.root)['operations']['chat_binding']
        page={'thread':{'id':binding['task_id'],'cwd':binding['cwd'],'title':binding['title']},
              'turns':[{'id':'sending-turn','error':None,'items':[{'id':'actual-call','type':'mcpToolCall',
                  'server':'codex_app','tool':'send_message_to_thread','status':'completed','error':None,
                  'arguments':{'threadId':'fixed-'+role,'prompt':(self.root/payload).read_text()}}]}]}
        call=w.file_digest(self.root,self.t.write('reports/assignment-call.json',page))
        result={'content':[{'type':'text','text':json.dumps({'threadId':'fixed-'+role})}],'isError':False}
        transport=w.file_digest(self.root,self.t.write('reports/assignment-send.json',{
            'actual_tool':'mcp__codex_app__send_message_to_thread','thread_id':'fixed-'+role,
            'raw_tool_return':result,'exact_consumed_prompt':pin}))
        item={'schema':c.ASSIGNMENT_SCHEMA,'task_id':self.t.task_id,'department':role,
              'sender_department':'operations','payload':pin,'actual_native_invocation':call,'actual_native_send':transport,
              'source_call_id':'actual-call','dispatch_receipt_id':sent['receipt_id']}
        path=self.t.write('reports/assignment.json',item)
        return item,w.file_digest(self.root,path)

    def test_whole_goal_assignment_admits_first_plan_without_old_qa_round(self):
        import qa_review_plan as review
        self.t.initialize();self.t.dispatch()
        self.t.fixture.receipt('chat_ack',fixture.PRODUCER,'producer-before-review')
        candidate,producer=self.t.producer_result()
        item,pin=self.assignment(role=fixture.ASSISTANT,initialize=False);c.record_assignment(self.root,item,pin)
        plan=self.t.review_plan(candidate)
        path=self.t.write('reports/whole-result-review-plan.json',plan)
        answer=review.bind_plan(self.root,task_id=self.t.task_id,plan_path=path,coordinator_role=fixture.ASSISTANT)
        self.assertEqual(answer['current_assignment_review_source'],pin)
        self.assertEqual(review.bind_plan(self.root,task_id=self.t.task_id,plan_path=path,
                             coordinator_role=fixture.ASSISTANT)['result'],'duplicate_ignored')
        verdict=self.t.assistant_verdict(plan,producer)
        self.assertEqual(verdict['workflow_state'],'qa_passed')
        receipts,errors=w._validate_receipt_chain(self.root,self.t.task_id)
        self.assertEqual(errors,[])
        self.assertEqual(w.reconcile_workflow(self.root,task_id=self.t.task_id)[0]['current_state'],'qa_passed')
        changed={**plan,'reviewer_department':'operations-assistant-3'}
        self.assertIsNone(review._current_goal_assignment_round(self.root,self.t.snapshot(),
                          w._validate_receipt_chain(self.root,self.t.task_id)[0],changed))
        (self.root/item['payload']['path']).write_text('tampered')
        with self.assertRaisesRegex(w.WorkflowError,'frozen whole-goal'):
            review._assigned_review_round(self.root,self.t.snapshot(),w._validate_receipt_chain(self.root,self.t.task_id)[0],plan)

    def test_generic_producer_assignment_restores_without_historical_repair(self):
        item,pin=self.assignment();answer=c.record_assignment(self.root,item,pin)
        self.assertTrue(answer['actual_message_delivered'])
        active=r.current_assignment_for_role(self.root,fixture.PRODUCER)
        self.assertEqual(active['task_id'],self.t.task_id);self.assertTrue(active['resume_required'])
        self.assertFalse(active['permissions_inherited'])
        self.assertEqual(c.record_assignment(self.root,item,pin)['result'],'duplicate_ignored')

    def test_assignment_wrong_role_original_call_or_bytes_rejected(self):
        item,pin=self.assignment()
        for change in [{'source_call_id':'missing'},{'sender_department':'sales'},{'department':'operations-assistant-3'}]:
            with self.subTest(change=change),self.assertRaises((w.WorkflowError,KeyError,ValueError)):
                c.record_assignment(self.root,{**item,**change},pin)
        (self.root/item['payload']['path']).write_text('changed by another writer')
        with self.assertRaises(w.WorkflowError):c.record_assignment(self.root,item,pin)

    def test_preapproved_next_batch_does_not_require_a_new_hq_decision(self):
        request=self.t.requested();request['action_id']='next-whole-batch-2'
        action={**request,'payload':request['payload']}
        self.t.initialize(continuation_actions=[{k:action[k] for k in ('action_id','action_class','scope','target_department','payload')}])
        self.t.dispatch()
        path=self.t.write('reports/authorized-next.json',action)
        self.assertEqual(g.record_approved_action(self.root,self.t.task_id,path)['result'],'recorded')
        self.assertEqual(self.t.policy(action)['status'],'allow')
        self.assertEqual(w._result_handoff_rows(self.root,self.t.task_id),[])

    def knowledge_read_fixture(self):
        identity,source,page=self.ready()
        binding=w.department_registry(self.root)['operations']['chat_binding']
        caller={'thread':{'id':binding['task_id'],'title':binding['title'],'cwd':binding['cwd']},
           'turns':[{'id':'hq-turn','items':[{'id':'one-real-read','type':'mcpToolCall',
             'server':'codex_app','tool':'read_thread','status':'completed','error':None,
             'arguments':{'threadId':source['source_thread_id']}}]}]}
        pin=w.file_digest(self.root,self.t.write('reports/hq-read-caller.json',caller))
        observation={'native_invocation':pin,'source_call_id':'one-real-read',
                     'actual_read_result':source['actual_native_completion']}
        input_pin=w.file_digest(self.root,self.t.write('reports/hq-read-observation.json',observation))
        return {'actual_recipient_read':input_pin},{'identity':identity,'queued_source':source,'dependency_pins':[]},observation

    def test_actual_hq_read_can_receive_knowledge_without_claiming_message_sent(self):
        request,proof,_=self.knowledge_read_fixture()
        result=c.actual_knowledge_read(self.root,request,proof)
        self.assertTrue(result['native_conclusion_received']);self.assertFalse(result['native_notification_sent'])
        self.assertNotIn('qa_verdict',result)

    def test_knowledge_intake_never_copies_queue_event_id_or_receipt_time(self):
        identity,source,_=self.ready();queued,_=w.record_result_handoff(self.root,source)
        store=r.CoordinationStore(self.root);self.addCleanup(store.close)
        claim=store.claim(identity,fixture.ASSISTANT,'intake-emitter-fixture','one-intake')
        request={**source,'event':'controller_received','idempotency_key':'distinct-intake',
                 'reply_observed_at':dt.datetime.now(dt.timezone.utc).isoformat(),'intake_mode':'queue',
                 'coordinator_role':fixture.ASSISTANT,'coordinator_owner':'intake-emitter-fixture','coordination_claim':claim}
        # The public guard separately authenticates the HQ reader. Exercise its
        # native emitter with the full queue object, which caused ID overwrite.
        proof={'queued_source':queued,'transport_binding':'actual_recipient_native_read',
               'actual_recipient_read':source['actual_native_completion'],'dependency_fingerprint':'fixture-only'}
        row,_=w._record_result_handoff_uncoordinated(self.root,request,knowledge_source=proof)
        self.assertEqual(row['event'],'controller_received')
        self.assertNotEqual(row['record_id'],queued['record_id'])
        self.assertEqual(row['idempotency_key'],'distinct-intake')
        self.assertEqual(row['reply_observed_at'],request['reply_observed_at'])

    def test_knowledge_queue_alone_or_wrong_actual_read_never_counts_as_receipt(self):
        request,proof,observation=self.knowledge_read_fixture()
        with self.assertRaises(w.WorkflowError):c.actual_knowledge_read(self.root,{},proof)
        observation['source_call_id']='unrelated-call'
        pin=w.file_digest(self.root,self.t.write('reports/wrong-reader.json',observation))
        with self.assertRaises(w.WorkflowError):c.actual_knowledge_read(self.root,{'actual_recipient_read':pin},proof)

    def test_divergent_native_append_keeps_uncertain_reservation(self):
        identity,source,_=self.ready();w.record_result_handoff(self.root,source)
        store=r.CoordinationStore(self.root);self.addCleanup(store.close)
        claim=store.claim(identity,fixture.ASSISTANT,'divergent-native-test','one-receive')
        request={**source,'event':'controller_received','idempotency_key':'expected-native-key',
                 'intake_mode':'queue','coordinator_role':fixture.ASSISTANT,
                 'coordinator_owner':'divergent-native-test','coordination_claim':claim}
        with self.assertRaises(w.WorkflowError),r.handoff_guard(self.root,request):
            w._record_result_handoff_uncoordinated(self.root,{**request,'idempotency_key':'divergent-native-key'})
            raise w.WorkflowError('modeled divergence after a native append')
        row=store.conn.execute('SELECT status FROM reservations WHERE result_key=? AND effect_key=?',
                    (r._key(identity),r._sha([request['event'],request['idempotency_key']]))).fetchone()
        self.assertEqual(row['status'],'uncertain')


class ReadyReceiptPrefixTests(unittest.TestCase):
    """Isolated causal-prefix regression; these are never live business receipts."""
    setUp=ContinuityTests.setUp
    ready=ContinuityTests.ready

    def source(self):
        self.now=dt.datetime.now(dt.timezone.utc)
        self.observed=self.now-dt.timedelta(seconds=20)
        with mock.patch.object(w,'utc_timestamp',return_value=(self.now-dt.timedelta(seconds=60)).isoformat()):
            identity,request,page=self.ready()
        page['turns'][0]['startedAt']=self.observed.timestamp()-1
        request.update(reply_observed_at=self.observed.isoformat(),
            actual_native_completion=w.file_digest(self.root,self.t.write('reports/prefix-ready-native.json',page)))
        return identity,request,page

    def append(self,offset=5,ack=True,failed=False,label='later'):
        request=self.t.requested(sender='operations',target=fixture.PRODUCER)
        request['action_id']='normal-continuation-'+label
        stamp=(self.observed+dt.timedelta(seconds=offset)).isoformat()
        with mock.patch.object(w,'utc_timestamp',return_value=stamp):
            policy=self.t.policy(request);self.assertEqual(policy['status'],'allow',policy)
            fields=dict(action_id=request['action_id'],action_class='thread_message',scope=request['scope'],
                        chat_task_id=w.department_registry(self.root)[fixture.PRODUCER]['chat_binding']['task_id'],
                        policy_decision_id=policy['decision_id'])
            sent=self.t.fixture.receipt('dispatch_sent',fixture.PRODUCER,label+'-sent',**fields)
            if failed:
                evidence=self.t.write('reports/failed-source-'+label+'.json',{'fixture_only':True,'failure':'original transport failed'})
                return self.t.fixture.receipt('dispatch_failed',fixture.PRODUCER,label+'-failed',evidence=evidence,
                    supersedes_receipt_id=sent['receipt_id'],replacement_reason='actual-fixture-transport-failed',**fields)
            if ack:self.t.fixture.receipt('chat_ack',fixture.PRODUCER,label+'-ack',**fields)
            return sent

    def rewrite_fixture_rows(self,mutate):
        rows=w.read_jsonl(w.receipts_path(self.root,self.t.task_id));rows=mutate(rows)
        previous=''
        for row in rows:
            row['previous_hash']=previous;row['receipt_hash']=w.sha256_value(w._receipt_payload_for_hash(row));previous=row['receipt_hash']
        w.receipts_path(self.root,self.t.task_id).write_text(''.join(json.dumps(x)+'\n' for x in rows))

    def validate(self,request):
        return w._validate_goal_completed_result(self.root,request,request['source_thread_id'])

    def test_legal_prefix_survives_later_ordinary_dispatch_ACK_without_writes(self):
        _,request,_=self.source();self.append()
        before=w.receipts_path(self.root,self.t.task_id).read_bytes()
        self.assertTrue(self.validate(request)['batch_delivery_frozen'])
        self.assertEqual(w.receipts_path(self.root,self.t.task_id).read_bytes(),before)

    def test_later_pending_dispatch_does_not_erase_frozen_source(self):
        _,request,_=self.source();self.append(ack=False)
        self.assertTrue(self.validate(request)['batch_delivery_frozen'])

    def test_later_failed_continuation_does_not_rewrite_the_earlier_source(self):
        _,request,_=self.source();self.append(failed=True)
        self.assertTrue(self.validate(request)['batch_delivery_frozen'])

    def test_normal_queue_then_actual_intake_survives_later_continuation_once(self):
        identity,request,_=self.source();w.record_result_handoff(self.root,request);self.append()
        store=r.CoordinationStore(self.root);self.addCleanup(store.close)
        claim=store.claim(identity,fixture.ASSISTANT,'prefix-a2','claim-prefix')
        receive={**request,'event':'controller_received','idempotency_key':'receive-prefix',
                 'intake_mode':'queue','coordinator_role':fixture.ASSISTANT,'coordinator_owner':'prefix-a2','coordination_claim':claim}
        first,_=w.record_result_handoff(self.root,receive)
        second,_=w.record_result_handoff(self.root,receive)
        self.assertEqual(first['record_id'],second['record_id'])
        self.assertEqual(second['result'],'duplicate_ignored')

    def test_only_late_task_dispatch_ACK_cannot_authorize_old_READY(self):
        _,request,_=self.source()
        self.rewrite_fixture_rows(lambda rows:[x for x in rows if not (x.get('department')==fixture.PRODUCER and x.get('receipt_type') in {'dispatch_sent','chat_ack'})])
        self.append()
        with self.assertRaises(w.WorkflowError):self.validate(request)

    def test_missing_original_dispatch_is_rejected(self):
        _,request,_=self.source()
        self.rewrite_fixture_rows(lambda rows:[x for x in rows if not (x.get('department')==fixture.PRODUCER and x.get('receipt_type')=='dispatch_sent')])
        with self.assertRaises(w.WorkflowError):self.validate(request)

    def test_missing_original_ACK_is_rejected_even_with_later_ACK(self):
        _,request,_=self.source()
        self.rewrite_fixture_rows(lambda rows:[x for x in rows if not (x.get('department')==fixture.PRODUCER and x.get('receipt_type')=='chat_ack')])
        self.append()
        with self.assertRaises(w.WorkflowError):self.validate(request)

    def test_missing_all_sources_cannot_be_replaced_by_caller_flags(self):
        _,request,_=self.source()
        self.rewrite_fixture_rows(lambda rows:[x for x in rows if not (x.get('department')==fixture.PRODUCER and x.get('receipt_type') in {'dispatch_sent','chat_ack'})])
        with self.assertRaises(w.WorkflowError):self.validate({**request,'allow_late_source':True,'ignore_late_receipts':True})

    def test_newer_dispatch_before_READY_requires_its_own_ACK(self):
        _,request,_=self.source();self.append(offset=-2,ack=False)
        with self.assertRaises(w.WorkflowError):self.validate(request)

    def test_failure_before_READY_cannot_reuse_an_older_success(self):
        _,request,_=self.source();self.append(offset=-2,failed=True)
        with self.assertRaises(w.WorkflowError):self.validate(request)

    def test_latest_successful_pre_READY_pair_is_selected(self):
        _,request,_=self.source();sent=self.append(offset=-2)
        rows,_=w._validate_receipt_chain(self.root,self.t.task_id)
        sources=[x for x in rows if x.get('department')==fixture.PRODUCER and x.get('receipt_type') in {'dispatch_sent','chat_ack','dispatch_failed'}]
        pair,bad=c._ready_receipt_prefix(sources,self.observed)
        self.assertFalse(bad);self.assertEqual(pair[0]['receipt_id'],sent['receipt_id'])
        self.assertTrue(self.validate(request)['batch_delivery_frozen'])

    def test_action_or_policy_mismatched_ACK_is_not_the_dispatch_ACK(self):
        _,request,_=self.source();original=w.read_jsonl(w.receipts_path(self.root,self.t.task_id))
        for field in ('action_id','policy_decision_id','scope'):
            with self.subTest(field=field):
                self.rewrite_fixture_rows(lambda _:copy.deepcopy(original))
                def alter(rows):
                    for row in rows:
                        if row.get('department')==fixture.PRODUCER and row.get('receipt_type')=='chat_ack':row[field]='wrong-exact-source'
                    return rows
                self.rewrite_fixture_rows(alter)
                with self.assertRaises(w.WorkflowError):self.validate(request)

    def test_empty_ACK_is_not_a_nonempty_source(self):
        _,request,_=self.source()
        def alter(rows):
            for row in rows:
                if row.get('department')==fixture.PRODUCER and row.get('receipt_type')=='chat_ack':row['ack_nonempty']=False
            return rows
        self.rewrite_fixture_rows(alter)
        with self.assertRaises(w.WorkflowError):self.validate(request)

    def test_later_backdated_source_cannot_be_filtered_into_the_old_prefix(self):
        _,request,_=self.source();self.append(label='first')
        def alter(rows):
            rows[-1]['created_at']=(self.observed-dt.timedelta(seconds=1)).isoformat();return rows
        self.rewrite_fixture_rows(alter)
        with self.assertRaises(w.WorkflowError):self.validate(request)

    def test_ACK_before_its_dispatch_is_rejected_even_with_equal_timestamps(self):
        _,request,_=self.source()
        def reorder(rows):
            send=next(i for i,x in enumerate(rows) if x.get('department')==fixture.PRODUCER and x.get('receipt_type')=='dispatch_sent')
            ack=next(i for i,x in enumerate(rows) if x.get('department')==fixture.PRODUCER and x.get('receipt_type')=='chat_ack')
            rows[send],rows[ack]=rows[ack],rows[send];return rows
        self.rewrite_fixture_rows(reorder)
        with self.assertRaises(w.WorkflowError):self.validate(request)

    def test_reordered_source_timestamps_are_rejected(self):
        _,request,_=self.source()
        def alter(rows):
            for row in rows:
                if row.get('department')==fixture.PRODUCER and row.get('receipt_type')=='chat_ack':row['created_at']=(self.now-dt.timedelta(seconds=61)).isoformat()
            return rows
        self.rewrite_fixture_rows(alter)
        with self.assertRaises(w.WorkflowError):self.validate(request)

    def test_malformed_or_future_late_time_is_not_ignored(self):
        _,request,_=self.source();self.append();original=w.read_jsonl(w.receipts_path(self.root,self.t.task_id))
        for stamp in ('not-a-real-time',(self.now+dt.timedelta(minutes=2)).isoformat()):
            def alter(_):
                rows=copy.deepcopy(original);rows[-1]['created_at']=stamp;return rows
            self.rewrite_fixture_rows(alter)
            with self.subTest(stamp=stamp),self.assertRaises(w.WorkflowError):self.validate(request)

    def test_late_receipt_hash_corruption_remains_a_full_chain_error(self):
        _,request,_=self.source();self.append()
        rows=w.read_jsonl(w.receipts_path(self.root,self.t.task_id));rows[-1]['receipt_hash']='0'*64
        w.receipts_path(self.root,self.t.task_id).write_text(''.join(json.dumps(x)+'\n' for x in rows))
        with self.assertRaises(w.WorkflowError):self.validate(request)

    def test_wrong_fixed_identity_project_version_SHA_and_payload_still_reject(self):
        _,request,page=self.source();self.append()
        for change in ({'candidate_version':'forged-version'},{'result_sha256':'0'*64},{'sender_department':'operations'}):
            with self.subTest(change=change),self.assertRaises(w.WorkflowError):self.validate({**request,**change})
        for field,value in [('id','wrong-fixed-person'),('cwd',str(self.root/'other-project')),('title','wrong-fixed-title')]:
            altered=copy.deepcopy(page);altered['thread'][field]=value
            path=self.t.write('reports/wrong-native-source.json',altered)
            with self.subTest(field=field),self.assertRaises(w.WorkflowError):self.validate({**request,'actual_native_completion':w.file_digest(self.root,path)})
        (self.root/request['visible_reply']['path']).write_text('altered source bytes')
        with self.assertRaises(w.WorkflowError):self.validate(request)


class ContinuationFaultTests(unittest.TestCase):
    """The three observed failures, in disposable project-local fixtures."""
    def setUp(self):
        self.f=ContinuityTests('runTest');self.f.setUp()
        self.addCleanup(self.f.doCleanups);self.root=self.f.root

    def assignments(self, current=True):
        config={'assignments':{'sales':{'path':'current'}} if current else {},
                'suspended_assignments':{'sales':[{'path':'bad'},{'path':'older'},{'path':'older'}]}}
        path=self.root/'data/department-current-assignment.json';w.atomic_write_json(path,config)
        def read(root,role,pin):
            if pin['path']=='bad':raise w.WorkflowError('intact original receipt chain required')
            return {'task_id':pin['path'],'resume_required':True,'permissions_inherited':False}
        return path,read

    def test_bad_old_assignment_does_not_hide_valid_current_or_other_pending(self):
        path,read=self.assignments();before=path.read_bytes()
        with mock.patch.object(c,'current_assignment',side_effect=read):
            actual=r.current_assignment_for_role(self.root,'sales')
        self.assertEqual(actual['task_id'],'current')
        self.assertEqual([x['task_id'] for x in actual['unfinished_assignment_queue']],['older'])
        self.assertEqual(len(actual['assignment_errors']),1)
        self.assertFalse(actual['assignment_errors'][0]['blocks_other_tasks'])
        self.assertEqual(path.read_bytes(),before)

    def test_missing_or_bad_current_preserves_valid_pending_without_accepting_bad_record(self):
        for current in (False,True):
            path,read=self.assignments(current)
            def read_bad_current(root,role,pin):
                if pin['path']=='current':raise w.WorkflowError('tampered current source')
                return read(root,role,pin)
            with self.subTest(current=current),mock.patch.object(c,'current_assignment',side_effect=read_bad_current):
                actual=r.current_assignment_for_role(self.root,'sales')
                self.assertEqual(actual['task_id'],'older')
                self.assertFalse(actual['permissions_inherited'])
                self.assertEqual(len(actual['assignment_errors']),2 if current else 1)

    def test_real_malformed_and_unknown_schema_assignments_preserve_valid_work(self):
        import test_goal_source_recovery as recovery_tests
        import goal_source_recovery as recovery
        t=recovery_tests.RecoveryTests('runTest');t.setUp();self.addCleanup(t.doCleanups)
        path,_,_=t.source();recovery.record(t.root,path)
        config=w.read_json(t.root/'data/department-current-assignment.json');valid=config['assignments'][fixture.PRODUCER]
        (t.root/'reports/bad-json.json').write_text('{')
        config['suspended_assignments']={fixture.PRODUCER:[{'path':'reports/missing.json','sha256':'a'*64,'size':1},
            w.file_digest(t.root,'reports/bad-json.json'),valid,valid]}
        w.atomic_write_json(t.root/'data/department-current-assignment.json',config)
        actual=r.current_assignment_for_role(t.root,fixture.PRODUCER)
        self.assertTrue(actual['resume_required']);self.assertEqual(len(actual['assignment_errors']),2)
        self.assertEqual(actual['unfinished_assignment_queue'],[])
        bad=t.write('reports/unsupported.json',{'schema':'unsupported-assignment-version'})
        config['assignments'][fixture.PRODUCER]=w.file_digest(t.root,bad)
        config['suspended_assignments'][fixture.PRODUCER]=[valid]
        w.atomic_write_json(t.root/'data/department-current-assignment.json',config)
        actual=r.current_assignment_for_role(t.root,fixture.PRODUCER)
        self.assertEqual(actual['task_id'],t.task_id);self.assertTrue(actual['resumed_suspended_assignment'])
        self.assertTrue(actual['current_assignment_invalid']);self.assertEqual(len(actual['assignment_errors']),1)

    def test_daily_close_and_external_wait_are_not_reported_as_new_intake(self):
        identity,request,_=self.f.daily_ready();w.record_result_handoff(self.root,request)
        queued=w._result_handoff_rows(self.root,identity['task_id'])
        for decision in ('close_scope','wait_external'):
            rows=queued+[{**identity,'event':'controller_received'},
                         {**identity,'event':'controller_decision','decision':decision},
                         {**identity,'event':'controller_followthrough','followthrough_status':'blocked_with_owner',
                          'next_check_at':(dt.datetime.now(dt.timezone.utc)+dt.timedelta(hours=1)).isoformat()}]
            with self.subTest(decision=decision),mock.patch.object(w,'_result_handoff_rows',return_value=rows):
                b=c.work_boundary(self.root,fixture.ASSISTANT,read_assignment=False)
            self.assertFalse(b['source_errors'])
            self.assertFalse(any(x.get('task_id')==identity['task_id'] for x in b['ready_actions']))
        # A genuine queued-only result must still be actionable.
        b=c.work_boundary(self.root,fixture.ASSISTANT,read_assignment=False)
        self.assertTrue(any(x.get('task_id')==identity['task_id'] for x in b['ready_actions']))

    def turn_live(self, default='notLoaded', other='active', chosen=None, turn_status='completed'):
        chosen=chosen or fixture.ASSISTANT;pin=self.f.live(default,other)
        live=w.read_json(self.root/pin['path']);inventory=w.read_json(self.root/live['actual_native_observation']['path'])
        now=int(dt.datetime.now(dt.timezone.utc).timestamp())
        for row in inventory['threads']:row['updatedAt']=now-1
        live['actual_native_observation']=w.file_digest(self.root,self.f.t.write('reports/select-native.json',inventory))
        binding=w.department_registry(self.root)[chosen]['chat_binding']
        page={'thread':{'id':binding['task_id'],'title':binding['title'],'cwd':binding['cwd'],
                        'status':'notLoaded','updatedAt':now},
              'turns':[{'id':'exact-fresh-turn','status':turn_status,'error':None}]}
        p=self.f.t.write('reports/current-reviewer-native.json',page)
        live['actual_native_target_turns']={binding['task_id']:w.file_digest(self.root,p)}
        return w.file_digest(self.root,self.f.t.write('reports/select-live.json',live))

    def test_notloaded_completed_assistant_is_available_and_new_active_turn_is_not(self):
        identity,request,_=self.f.ready();w.record_result_handoff(self.root,request)
        actual=c.selection_plan(self.root,identity,self.turn_live())
        self.assertEqual(actual['selected'],fixture.ASSISTANT)
        actual=c.selection_plan(self.root,identity,self.turn_live(turn_status='inProgress'))
        self.assertEqual(actual['state'],'shared_waiting')

    def test_daily_selected_backup_sees_same_result_and_its_closed_events(self):
        identity,request,_=self.f.daily_ready();w.record_result_handoff(self.root,request)
        self.f.shared_methods('operations-assistant')
        answer=c.select_result(self.root,{**identity,'actor':fixture.PRODUCER,'request_id':'daily-backup-recovery',
                     'live_identity':self.turn_live('active','notLoaded',chosen='operations-assistant')})
        self.assertEqual(answer['selected'],'operations-assistant')
        self.assertTrue(any(x.get('task_id')==identity['task_id'] for x in
                            c.work_boundary(self.root,'operations-assistant',read_assignment=False)['ready_actions']))
        rows=w._result_handoff_rows(self.root,identity['task_id'])+[
            {**identity,'event':'controller_received'},{**identity,'event':'controller_decision','decision':'close_scope'}]
        with mock.patch.object(w,'_result_handoff_rows',return_value=rows):
            b=c.work_boundary(self.root,'operations-assistant',read_assignment=False)
        self.assertFalse(any(x.get('task_id')==identity['task_id'] for x in b['ready_actions']))

    def test_notloaded_notification_claim_and_policy_share_same_native_turn(self):
        n=notices.NoticeResumeTests('runTest');n.setUp();self.addCleanup(n.doCleanups)
        live=n.live('notLoaded');value=w.read_json(n.root/live['path'])
        inventory=w.read_json(n.root/value['actual_native_observation']['path']);inventory['threads'][0]['updatedAt']=2
        w.atomic_write_json(n.root/value['actual_native_observation']['path'],inventory)
        value['actual_native_observation']=w.file_digest(n.root,value['actual_native_observation']['path'])
        binding=w.department_registry(n.root)[fixture.ASSISTANT]['chat_binding']
        page={'thread':{'id':binding['task_id'],'title':binding['title'],'cwd':binding['cwd'],'updatedAt':3},
              'turns':[{'status':'completed'}]}
        value['actual_native_target_turns']={binding['task_id']:w.file_digest(n.root,n.t.write('reports/receiver.json',page))}
        live=w.file_digest(n.root,n.t.write('reports/live-notLoaded.json',value))
        actual=r.notification_claim(n.root,n.identity,fixture.PRODUCER,'fixture-producer','native-notloaded',live,n.payload)
        self.assertEqual(actual['result'],'ready')
        self.assertEqual(r.validate_notification_delivery(n.root,n.identity)['state'],'prepared')
        self.assertFalse(actual['delivered'])
        sender=w.department_registry(n.root)[fixture.PRODUCER]['chat_binding']
        before={'sender':w.file_digest(n.root,n.t.write('reports/native-sender-before.json',{
                    'schemaVersion':1,'page':{'order':'newest_first','limit':1,'hasMore':False},
                    'thread':{'id':sender['task_id'],'title':sender['title'],'cwd':sender['cwd'],'status':'active'},
                    'turns':[{'id':'actual-active','status':'inProgress','items':[]}]})),
                'receiver':w.file_digest(n.root,n.t.write('reports/native-receiver-before.json',{
                    'schemaVersion':1,'page':{'order':'newest_first','limit':1,'hasMore':False},
                    'thread':{**page['thread'],'status':'notLoaded'},
                    'turns':[{'id':'actual-ended','status':'completed','items':[]}]}))}
        current=w.read_json(r._notification_path(n.root,n.identity))
        self.assertEqual(r._notification_before(n.root,current,before)[1]['turns'][0]['status'],'completed')
        stale=w.read_json(n.root/before['receiver']['path']);stale['thread']['updatedAt']=1
        old_before={**before,'receiver':w.file_digest(n.root,n.t.write('reports/older-native-before.json',stale))}
        unchanged=r._notification_path(n.root,n.identity).read_bytes()
        with self.assertRaises(w.WorkflowError):
            r.notification_send_started(n.root,n.identity,actual['claim'],native_before=old_before)
        self.assertEqual(r._notification_path(n.root,n.identity).read_bytes(),unchanged)
        # Replacing the latest observed turn with active blocks policy as well.
        page['turns'][0]['status']='inProgress'
        w.atomic_write_json(n.root/'reports/receiver.json',page)
        with self.assertRaises(w.WorkflowError):r.validate_notification_delivery(n.root,n.identity)

    def test_owner_direct_internal_ops_batch_is_not_an_automation_result(self):
        import goal_source_recovery as recovery
        t=self.f.t;binding=w.department_registry(self.root)['operations']['chat_binding']
        human=w.read_json(self.root/'reports/synthetic-owner-message.json')
        human['source_thread_id']=binding['task_id'];t.write('reports/synthetic-owner-message.json',human)
        auth=t.make_goal()['human_authorization'];auth.update(source_thread_id=binding['task_id'],executor='operations')
        scope='department:'+fixture.PRODUCER
        t.initialize(primary_owner='operations',producer_departments=['operations'],source_mode='owner_direct',
            human_authorization=auth,completion_kind='internal_delivery',completion_requirements=[{
                'requirement_id':'internal-only','criterion_index':0,'scope':scope,'requirement_type':'accepted_delivery',
                'subject':{'mode':'latest_exact_accepted_result','producer_department':'operations'}}])
        native=t.write('reports/ops-owner.json',{'thread':{'id':binding['task_id'],'title':binding['title'],'cwd':binding['cwd']},
            'turns':[{'id':'owner-turn','status':'completed','items':[human['message']]}]})
        source=t.write('reports/ops-current.json',{'schema':c.ASSIGNMENT_SCHEMA,'task_id':t.task_id,
            'original_task_id':t.task_id,'department':'operations','sender_department':'operations','scope':scope,
            'source_kind':'owner_direct_native','authorization_pin':t.snapshot()['goal_delivery']['authorization_pin'],
            'actual_native_invocation':w.file_digest(self.root,native)})
        recovery.record(self.root,source)
        out=t.write('logs/department-outbox/ops-result.json',t.result_box('operations','ops-v1',
            w.file_digest(self.root,t.write('reports/ops-candidate.json',{'synthetic_internal_only':True}))))
        identity={'task_id':t.task_id,'sender_department':'operations','candidate_version':'ops-v1',
                  'result_sha256':w.file_digest(self.root,out)['sha256']}
        text=c.READY_MARKER+json.dumps({**identity,'outbox_path':out,'batch_complete':True})+'\n'
        (self.root/'reports/ops-ready.txt').write_text(text)
        p=t.write('reports/ops-ready-native.json',{'thread':{'id':binding['task_id'],'title':binding['title'],'cwd':binding['cwd']},
            'turns':[{'id':'ops-delivery','status':'inProgress','startedAt':dt.datetime.now(dt.timezone.utc).timestamp()-1,
                'items':[{'id':'ops-ready','type':'agentMessage','phase':'commentary','text':text}]}]})
        request={**identity,'outbox_path':out,'event':'notification_queued','idempotency_key':'ops-ready-once',
            'result_source_phase':'delivery_ready','source_thread_id':binding['task_id'],'source_turn_id':'ops-delivery',
            'source_message_id':'ops-ready','source_reply_sha256':hashlib.sha256(text.encode()).hexdigest(),
            'reply_observed_at':dt.datetime.now(dt.timezone.utc).isoformat(),'actual_native_completion':w.file_digest(self.root,p),
            'visible_reply':w.file_digest(self.root,'reports/ops-ready.txt')}
        self.assertTrue(w.record_result_handoff(self.root,request)[0]['batch_delivery_frozen'])
        self.assertEqual(w.record_result_handoff(self.root,request)[0]['result'],'duplicate_ignored')

    def test_old_invalid_knowledge_is_blocked_without_hiding_valid_conclusion(self):
        identity,request,_=self.f.ready();w.record_result_handoff(self.root,request)
        identity={**identity,'sender_department':fixture.ASSISTANT}
        older={**identity,'candidate_version':'historical-missing-source','result_sha256':'b'*64}
        rows=[{**x,'event':'notification_queued'} for x in [older,identity]]
        def proof(root,x):
            if x==older:raise w.WorkflowError('exact historical conclusion missing')
            return {'identity':x,'acceptance_proven':True}
        with mock.patch.object(w,'_result_handoff_rows',return_value=rows),\
             mock.patch.object(r,'hq_knowledge_source',side_effect=proof),\
             mock.patch.object(r,'notification_plan',return_value={'notifications':[],'errors':[]}):
            actual=c.work_boundary(self.root,'operations',read_assignment=False)
        self.assertEqual(len(actual['ready_actions']),1)
        self.assertEqual(actual['ready_actions'][0]['candidate_version'],identity['candidate_version'])
        self.assertEqual(actual['source_errors'][0]['identity'],older)
        self.assertFalse(actual['source_errors'][0]['actionable'])
        self.assertFalse(actual['source_errors'][0]['blocks_other_tasks'])
        # Genuine prior receipt does not become a new review or a source error.
        rows.append({**older,'event':'controller_received'})
        with mock.patch.object(w,'_result_handoff_rows',return_value=rows),\
             mock.patch.object(r,'hq_knowledge_source',side_effect=proof),\
             mock.patch.object(r,'notification_plan',return_value={'notifications':[],'errors':[]}):
            actual=c.work_boundary(self.root,'operations',read_assignment=False)
        self.assertFalse(actual['source_errors'])


class BusyWaitTests(unittest.TestCase):
    def test_busy_notice_waits_for_native_completion_and_does_not_spin(self):
        n=notices.NoticeResumeTests('runTest');n.setUp();self.addCleanup(n.doCleanups)
        n.claim('active')
        notice=r.notification_plan(n.root,fixture.PRODUCER)['notifications'][0]
        self.assertFalse(notice['actionable']);self.assertTrue(notice['waiting_for_native_completion'])
        p=g.wait_plan(n.root,fixture.ASSISTANT,queue={'notification_delivery_pending':[notice]})
        self.assertEqual(p['state'],'inflight_event_wait')
        self.assertEqual(p['batches'],[[{'threadId':'fixed-'+fixture.ASSISTANT}]])
        self.assertFalse(p['wait_deferred_for_ready_work'])


if __name__=='__main__':unittest.main()
