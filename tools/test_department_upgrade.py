"""Synthetic projects only: exercise native receipts, QA, queue and grant consumers."""
import copy
import datetime as dt
import hashlib
import json
import threading
import unittest
from unittest import mock
import business_current_view as view
import controller_event_state as events
import controller_stop_hook as hook
import human_control as human
import native_inventory as inventory
import qa_dispatch_priority as priority
import result_coordination as coordination
import routine_grants as grants
import test_runtime_qa_admission as runtime
import workflow_control as w


class DepartmentUpgradeIntegrationTests(unittest.TestCase):
    dispatch = runtime.ExactRuntimeQA.dispatch
    receipt = runtime.ExactRuntimeQA.receipt
    routing_decision = runtime.ExactRuntimeQA.routing_decision
    write = runtime.ExactRuntimeQA.write
    bind = runtime.ExactRuntimeQA.bind
    box = runtime.ExactRuntimeQA.box
    producer = runtime.ExactRuntimeQA.producer
    review = runtime.ExactRuntimeQA.review
    verdict = runtime.ExactRuntimeQA.verdict

    def setUp(self):
        runtime.ExactRuntimeQA.setUp(self)
        self.addCleanup(self.temp_dir.cleanup)
        registry = w.read_json(self.root / 'data/department-registry.json')
        prototype = next(r for r in registry['departments'] if r['id'] == 'operations-assistant')
        for role in ('operations-assistant-2', 'operations-assistant-3'):
            item = copy.deepcopy(prototype); item['id'] = role
            item['chat_binding'].update(task_id='fixed-' + role, title=role)
            registry['departments'].append(item)
        self.write('data/department-registry.json', registry)
        self.bind(); self.source = self.producer()
        self.review(qa_result='PASS_INTERNAL_APPLICATION_ALLOWED', candidate_path=self.candidate,
                    candidate_sha256=self.pin['sha256'])
        qa = self.verdict()
        self.write('data/test-adoption.json', {
            'status': 'adopted_after_independent_qa', 'qa_department': 'qa-technical',
            'qa_outbox': w.file_digest(self.root, self.qa_path), 'qa_receipt_id': qa['receipt_id'],
            'candidate_path': self.candidate, 'candidate_sha256': self.pin['sha256']})
        policy = w.load_policy(self.root)
        policy['department_system_upgrade'].update(admitted=True,
            adoption=w.file_digest(self.root, 'data/test-adoption.json'))
        self.write('data/action-policy.json', policy)
        source_pin = w.file_digest(self.root, self.source)
        self.base = {'task_id': self.task_id, 'sender_department': 'content-organic-website',
                     'candidate_version': 'v1', 'result_sha256': source_pin['sha256'],
                     'outbox_path': self.source, 'scope': self.plan['scope']}
        w.record_result_handoff(self.root, {**self.base, 'event': 'notification_queued', 'idempotency_key': 'queue-v1'})
        self.identity = coordination.exact_identity(self.base)
        self.store = coordination.CoordinationStore(self.root)
        self.addCleanup(self.store.close)
        self.grant_path = 'data/test-routine-grant.json'
        self.make_grant()

    def make_grant(self, role='operations-assistant-2', **changes):
        now = dt.datetime.now(dt.timezone.utc)
        value = {**self.identity, 'schema_version': 1, 'issuer': 'operations', 'actor_role': role,
                 'actor_thread_id': 'fixed-' + role, 'owner_authorization_ref': 'synthetic-owner-authority',
                 'production_authority_granted': False, 'human_control_revision': 1,
                 'issued_at': now.isoformat(), 'expires_at': (now + dt.timedelta(hours=1)).isoformat(),
                 'status': 'active', 'consumed': False, 'scope': self.plan['scope'],
                 'allowed_events': list(coordination.FINAL_EVENTS),
                 'allowed_decisions': sorted(grants.DECISIONS),
                 'allowed_next_owners': ['content-organic-website', 'qa-technical', 'operations'],
                 'allowed_linked_tasks': [self.task_id]}
        value.update(changes); self.write(self.grant_path, value)
        self.grant = w.file_digest(self.root, self.grant_path)
        return value

    def request(self, event='controller_received', **changes):
        claim = self.store.claim(self.identity, 'operations-assistant-2', 'assistant-two', 'wake-v1')
        request = {**self.base, 'event': event, 'idempotency_key': event + '-v1',
                   'coordinator_role': 'operations-assistant-2', 'coordinator_owner': 'assistant-two',
                   'coordination_claim': claim, 'routine_grant': self.grant}
        if event == 'controller_received':
            request.update(intake_mode='queue',source_thread_id='fixed-content-organic-website',
                           source_reply_sha256='a' * 64,
                           reply_observed_at=dt.datetime.now(dt.timezone.utc).isoformat())
        request.update(changes)
        return request

    def administrative(self, action, revision=1, **changes):
        request = {'action': action, 'actor': 'operations', 'expected_revision': revision,
                   'human_message': {'source': 'human_user_message', 'thread_id': 'fixed-operations',
                        'message_id': 'synthetic-human-' + action, 'reply_sha256': 'f' * 64,
                        'explicit_command': action, 'observed_at': dt.datetime.now(dt.timezone.utc).isoformat()}}
        request.update(changes)
        return human.administrative_control(self.root, request)

    def test_exact_native_independent_qa_admits_one_bounded_actor(self):
        self.assertEqual(grants.validate(self.root, self.grant, 'operations-assistant-2')['actor_thread_id'],
                         'fixed-operations-assistant-2')

    def test_pause_wins_over_closed_workflow_and_preserves_queue(self):
        before = w.result_handoff_path(self.root, self.task_id).read_bytes()
        self.administrative('pause')
        with self.assertRaisesRegex(w.WorkflowError, 'human_pause'):
            self.store.claim(self.identity, 'operations-assistant-3', 'third', 'wake')
        self.assertEqual(before, w.result_handoff_path(self.root, self.task_id).read_bytes())
        self.assertTrue(human.read_state(self.root)['paused'])

    def test_only_explicit_human_resume_with_revision_restores_admission(self):
        self.administrative('pause')
        with self.assertRaises(w.WorkflowError): self.administrative('resume', revision=1)
        self.administrative('resume', revision=2)
        self.assertFalse(human.read_state(self.root)['paused'])
        with self.assertRaises(w.WorkflowError): grants.validate(self.root, self.grant, 'operations-assistant-2')

    def test_stale_forged_or_wrong_administrative_command_is_denied(self):
        for changes in ({'actor': 'operations-assistant-2'}, {'human_message': []}, {'human_message': {}},
                        {'expected_revision': True}):
            with self.subTest(changes=changes), self.assertRaises(w.WorkflowError):
                self.administrative('pause', **changes)
        proof = {'source':'human_user_message', 'thread_id':'other-project', 'message_id':'x',
                 'reply_sha256':'a'*64, 'explicit_command':'pause',
                 'observed_at':dt.datetime.now(dt.timezone.utc).isoformat()}
        with self.assertRaises(w.WorkflowError): self.administrative('pause', human_message=proof)

    def test_missing_state_after_migration_denies_continuation(self):
        (self.root / human.STATE).unlink()
        self.assertTrue(human.read_state(self.root)['paused'])
        with self.assertRaises(w.WorkflowError): human.guard(self.root)

    def test_corrupted_persistent_state_does_not_resume(self):
        (self.root / human.STATE).write_text('{invalid')
        with self.assertRaises(w.WorkflowError): human.guard(self.root)

    def test_stop_pause_returns_before_loading_old_queue(self):
        self.administrative('pause')
        with mock.patch.multiple(hook, ROOT=self.root, CONTROLLER='fixed-operations', PROJECT='flashcast-test-project'):
            loader = mock.Mock(side_effect=AssertionError('old queue must not be derived'))
            result = hook.evaluate({'hook_event_name':'Stop', 'session_id':'fixed-operations',
                                    'cwd':str(self.root), 'stop_hook_active':False}, load_context=loader)
            self.assertEqual(result, {}); loader.assert_not_called()
        state, pending = events.derive(self.root)
        self.assertTrue(state['human_paused']); self.assertTrue(pending['original_queue_preserved'])

    def test_three_assistants_have_one_winner_and_no_speculative_duplicate(self):
        barrier = threading.Barrier(3); results = []
        def worker(role):
            store = coordination.CoordinationStore(self.root)
            try:
                barrier.wait()
                try: results.append(store.claim(self.identity, role, role, role))
                except w.WorkflowError: results.append(None)
            finally: store.close()
        workers = [threading.Thread(target=worker,args=(role,)) for role in sorted(grants.ASSISTANTS)]
        for worker_thread in workers: worker_thread.start()
        for worker_thread in workers: worker_thread.join(timeout=10)
        self.assertFalse(any(t.is_alive() for t in workers))
        self.assertEqual(sum(r is not None for r in results), 1)

    def test_precheck_escalation_preserves_scope_and_invalidates_old_lease(self):
        claim = self.store.claim(self.identity,'operations-assistant-3','third','wake')
        self.store.precheck(self.identity,claim['role'],claim['owner'],claim,'partial','operations',
                            'verify actual result','independent evidence')
        released = self.store.escalate(self.identity,claim['role'],claim['owner'],claim,'HQ decision needed')
        self.assertFalse(released['claimed']); self.assertIsNotNone(released['precheck'])
        with self.assertRaises(w.WorkflowError): self.store.renew(self.identity,claim['role'],claim['owner'],claim)
        self.assertGreater(self.store.claim(self.identity,'operations','HQ','takeover')['fence'],claim['fence'])

    def test_actual_report_states_never_become_final_approval(self):
        claim = self.store.claim(self.identity,'operations-assistant-2','two','wake')
        for status in ('completed','partial','qa_rework','external_blocked','queue_failed','failed'):
            result = self.store.precheck(self.identity,claim['role'],claim['owner'],claim,status,
                                        'operations','review exact candidate','valid native result')
            self.assertTrue(result['precheck']['draft_only'])
            self.assertFalse(result['precheck']['controller_decision_recorded'])

    def test_assistant_receive_is_native_and_audits_actual_actor(self):
        request = self.request()
        result, _ = w.record_result_handoff(self.root, request)
        self.assertEqual(result['actor_role'],'operations-assistant-2')
        self.assertFalse(result['final_authority_exercised'])
        replay, _ = w.record_result_handoff(self.root, request)
        self.assertEqual(replay['result'],'duplicate_ignored')
        self.assertEqual(sum(r['event']=='controller_received' for r in w._result_handoff_rows(self.root,self.task_id)),1)

    def test_routine_decision_and_named_external_wait_have_actual_followthrough(self):
        w.record_result_handoff(self.root,self.request())
        decision = self.request('controller_decision',decision='wait_external',next_owner='operations',
                                next_action='verify missing external access',unblock_condition='exact owner evidence',
                                evidence_paths=[self.candidate])
        w.record_result_handoff(self.root,decision)
        follow = self.request('controller_followthrough',followthrough_status='external_wait_registered',
                              next_check_at=(dt.datetime.now(dt.timezone.utc)+dt.timedelta(hours=1)).isoformat(),
                              unblock_condition='exact owner evidence',evidence_paths=[self.candidate])
        result,_=w.record_result_handoff(self.root,follow)
        self.assertEqual(result['actor_role'],'operations-assistant-2')
        self.assertEqual(w.result_handoff_status(self.root,self.task_id)['followthrough_pending_count'],0)

    def test_final_approval_closure_or_execution_cannot_be_granted_to_assistant(self):
        for decision in ('release_gate','close_scope'):
            with self.subTest(decision=decision), self.assertRaises(w.WorkflowError):
                w.record_result_handoff(self.root,self.request('controller_decision',decision=decision,
                    next_owner='publishing',next_action='publish'))
        with self.assertRaises(w.WorkflowError):
            w.record_result_handoff(self.root,self.request('controller_followthrough',followthrough_status='execution_verified'))

    def test_grant_cannot_be_reused_by_other_actor_result_version_or_scope(self):
        for changes in ({'coordinator_role':'operations-assistant-3'}, {'candidate_version':'v2'},
                        {'result_sha256':'e'*64}, {'scope':'project:other'}, {'task_id':'different-task'}):
            with self.subTest(changes=changes), self.assertRaises(w.WorkflowError):
                grants.check_result(self.root,self.request(**changes))

    def test_expired_consumed_unadmitted_or_changed_grant_denies(self):
        for changes in ({'consumed':True},{'status':'pending'}, {'production_authority_granted':True},
                        {'expires_at':(dt.datetime.now(dt.timezone.utc)-dt.timedelta(seconds=1)).isoformat()}):
            self.make_grant(**changes)
            with self.subTest(changes=changes), self.assertRaises(w.WorkflowError):
                grants.validate(self.root,self.grant,'operations-assistant-2')
        self.make_grant(); old_pin=self.grant
        self.make_grant(scope='another-scope')
        with self.assertRaises(w.WorkflowError): grants.validate(self.root,old_pin,'operations-assistant-2')

    def test_developer_cannot_self_adopt_and_candidate_drift_invalidates_qa(self):
        policy=w.load_policy(self.root);policy['department_system_upgrade']['admitted']=False
        self.write('data/action-policy.json',policy)
        with self.assertRaises(w.WorkflowError): grants.validate(self.root,self.grant,'operations-assistant-2')
        policy['department_system_upgrade']['admitted']=True;self.write('data/action-policy.json',policy)
        self.write(self.candidate,{'different_candidate':True})
        with self.assertRaises(w.WorkflowError): grants.validate(self.root,self.grant,'operations-assistant-2')

    def test_native_qa_receipt_chain_tampering_does_not_admit_grants(self):
        path=w.receipts_path(self.root,self.task_id)
        path.write_text(path.read_text().replace('"verdict": "pass"','"verdict": "blocked"'))
        with self.assertRaises(w.WorkflowError): grants.validate(self.root,self.grant,'operations-assistant-2')

    def test_current_business_view_one_exact_row_preserves_history(self):
        before=w.result_handoff_path(self.root,self.task_id).read_bytes()
        row={'original_business_id':'original-control-business','task_id':self.task_id,
             'outbox':w.file_digest(self.root,self.source),'phase':'awaiting decision','owner':'operations',
             'next_action':'verify source','blocker':'none','unblock_condition':'independent QA',
             'evidence':[self.pin]}
        self.write('data/test-current-business.json',{'schema_version':1,'businesses':[row]})
        result=view.inspect(self.root,w.file_digest(self.root,'data/test-current-business.json'))
        self.assertEqual(result['current_business_count'],1)
        self.assertEqual(before,w.result_handoff_path(self.root,self.task_id).read_bytes())
        self.write('data/test-current-business.json',{'schema_version':1,'businesses':[row,row]})
        with self.assertRaises(w.WorkflowError):view.inspect(self.root,w.file_digest(self.root,'data/test-current-business.json'))

    def test_pinned_and_recents_inventory_are_both_exact_and_duplicates_deny(self):
        self.assertEqual(inventory.threads({'pinnedThreads':[{'id':'developer'}],'threads':[{'id':'HQ'}]}),
                         [{'id':'developer'},{'id':'HQ'}])
        with self.assertRaises(w.WorkflowError): inventory.threads({'pinnedThreads':[{'id':'same'}],'threads':[{'id':'same'}]})
        for root in inventory.CODE_ROOTS:self.assertEqual(inventory.validate_code_source(root),root)
        for root in ('<USER_HOME>/Desktop','/tmp',str(self.root)):
            with self.assertRaises(w.WorkflowError):inventory.validate_code_source(root)

    def test_paused_qa_priority_never_dispatches_or_reopens_history(self):
        self.administrative('pause')
        result=priority.inspect(self.root,{'schema_version':'1.0'})
        self.assertEqual(result['mode'],'BLOCKED_INVALID_PRIORITY_EVIDENCE')
        self.assertEqual(result['external_actions'],0)

    def test_pause_blocks_real_policy_dispatch_and_native_receive(self):
        request=self.request(); self.administrative('pause')
        with self.assertRaises(w.WorkflowError):w.record_result_handoff(self.root,request)
        decision,_=w.policy_check(self.root,task_id=self.task_id,department='operations',action_id='new-dispatch',
                                 action_class='thread_message',scope=self.plan['scope'])
        self.assertEqual(decision['status'],'deny')
        self.assertIn('human_control_paused_or_invalid',decision['reason'])

    def route_fixture(self):
        task='routine-continuation-001'; action='continue-local-step'
        w.initialize_workflow(self.root,task_id=task,request='synthetic internal continuation',
            plan_status='ready_to_send',owner_approval_required=False,
            departments=[{'department':'content-organic-website','chat_task_id':'fixed-content-organic-website'}])
        target=w.department_registry(self.root)['content-organic-website']['chat_binding']
        route={'task_id':task,'action_id':action,'scope':'routine_grant:continuation-v1',
               'action_class':'thread_message','sender_department':'operations-assistant-2',
               'source_project_id':'flashcast-test-project','target_project_id':'flashcast-test-project',
               'target_department':'content-organic-website','target_thread_id':target['task_id'],
               'target_thread_title':target['title'],'target_cwd':target['cwd'],
               'target_sidebar_section_id':target['sidebar_section_id'],'payload_sha256':'b'*64}
        self.write('data/test-live-inventory.json',{'observed_at':dt.datetime.now(dt.timezone.utc).isoformat(),
            'threads':[{'id':target['task_id'],'projectId':target['project_id'],'title':target['title'],
                        'cwd':target['cwd'],'status':'idle'},
                       {'id':'fixed-operations-assistant-2','projectId':'flashcast-test-project',
                        'title':'operations-assistant-2','cwd':str(self.root),'status':'active'}],
            'sections':[{'id':target['sidebar_section_id'],
                         'itemKeys':['codex:thread:local:'+target['task_id']]}]})
        self.make_grant(routing=route,live_identity=w.file_digest(self.root,'data/test-live-inventory.json'),
                        allowed_linked_tasks=[task],native_attempt_receipt_path='logs/test-attempt.json',
                        native_send_receipt_path='logs/test-native-send.json')
        policy=w.load_policy(self.root)
        policy['department_system_upgrade']['routing_grants'][task+':'+action]=self.grant
        self.write('data/action-policy.json',policy)
        claim=self.store.claim(self.identity,'operations-assistant-2','assistant-two','wake-v1')
        return route,{'routing':route,'coordinator_owner':'assistant-two','coordination_claim':claim}

    def test_native_routine_dispatch_consumes_one_reservation_and_audits_actor(self):
        route,request=self.route_fixture()
        self.assertEqual(grants.check_routing(self.root,route)[0],[])
        decision,_=w.policy_check(self.root,task_id=route['task_id'],department=route['sender_department'],
            action_id=route['action_id'],action_class=route['action_class'],scope=route['scope'],
            **{k:v for k,v in route.items() if k not in {'task_id','action_id','action_class','scope','sender_department'}})
        self.assertEqual(decision['status'],'allow',decision.get('reason'))
        reserved=grants.reserve_route(self.root,self.grant,'operations-assistant-2',request)
        with self.assertRaises(w.WorkflowError):grants.reserve_route(self.root,self.grant,'operations-assistant-2',request)
        # Synthetic readback, not a real API call or message.
        proof={'source':'trusted_native_send_readback','reservation_id':reserved['reservation_id'],
               'target_thread_id':route['target_thread_id'],'payload_sha256':route['payload_sha256'],
               'actor_thread_id':'fixed-operations-assistant-2','nonempty':True,'message_id':'synthetic-native-send',
               'observed_at':dt.datetime.now(dt.timezone.utc).isoformat()}
        grants.commit_route(self.root,self.grant,'operations-assistant-2',proof)
        result=self.receipt('dispatch_sent','content-organic-website','routine-native-dispatch',
            task_id=route['task_id'],action_id=route['action_id'],action_class=route['action_class'],
            scope=route['scope'],policy_decision_id=decision['decision_id'])
        self.assertEqual(result['actor_role'],'operations-assistant-2')
        self.assertEqual(result['routine_grant'],self.grant)
        self.assertNotEqual(grants.check_routing(self.root,route)[0],[])

    def test_route_interruption_remains_uncertain_and_never_auto_resends(self):
        route,request=self.route_fixture()
        grants.reserve_route(self.root,self.grant,'operations-assistant-2',request)
        self.assertEqual(w.read_json(self.root/'logs/test-attempt.json')['status'],'reserved_uncertain')
        self.assertNotEqual(grants.check_routing(self.root,route)[0],[])
        with self.assertRaises(w.WorkflowError):grants.commit_route(self.root,self.grant,'operations-assistant-2',{})
        self.assertFalse((self.root/'logs/test-native-send.json').exists())

    def test_unknown_cross_project_route_and_active_target_are_not_admitted(self):
        route,_=self.route_fixture()
        self.assertNotEqual(grants.check_routing(self.root,{**route,'target_project_id':'other-project'})[0],[])
        self.assertNotEqual(grants.check_routing(self.root,{**route,'action_id':'unknown-grant'})[0],[])
        live=w.read_json(self.root/'data/test-live-inventory.json');live['threads'][0]['status']='active'
        self.write('data/test-live-inventory.json',live)
        grant=w.read_json(self.root/self.grant_path);grant['live_identity']=w.file_digest(self.root,'data/test-live-inventory.json')
        self.write(self.grant_path,grant);self.grant=w.file_digest(self.root,self.grant_path)
        policy=w.load_policy(self.root);policy['department_system_upgrade']['routing_grants'][route['task_id']+':'+route['action_id']]=self.grant
        self.write('data/action-policy.json',policy)
        self.assertNotEqual(grants.check_routing(self.root,route)[0],[])

    def test_hq_recovery_of_interrupted_assistant_effect_is_readback_only(self):
        request=self.request()
        with self.assertRaises(RuntimeError):
            with coordination.handoff_guard(self.root,request):raise RuntimeError('synthetic before append crash')
        lease=request['coordination_claim']
        self.store.precheck(self.identity,lease['role'],lease['owner'],lease,'partial','operations',
                            'recover uncertain append','exact native readback')
        self.store.escalate(self.identity,lease['role'],lease['owner'],lease,'HQ recovery')
        hq=self.store.claim(self.identity,'operations','HQ','recover-hq')
        recovery=coordination.recover_reservation(self.root,{**request,'recoverer_role':'operations',
            'recoverer_owner':'HQ','recoverer_claim':hq},'exact append absent after interruption')
        self.assertEqual(recovery['status'],'retry_ready');self.assertFalse(recovery['side_effect_executed'])
        self.assertFalse(any(r['event']=='controller_received' for r in w._result_handoff_rows(self.root,self.task_id)))

    def test_exact_administrative_cancellation_works_after_business_closed(self):
        before=w.result_handoff_path(self.root,self.task_id).read_bytes()
        self.administrative('cancel',task_id=self.task_id)
        self.assertIn(self.task_id,human.read_state(self.root)['cancelled_tasks'])
        with self.assertRaises(w.WorkflowError):self.store.claim(self.identity,'operations','HQ','cancelled-takeover')
        self.assertEqual(before,w.result_handoff_path(self.root,self.task_id).read_bytes())
        self.administrative('resume',revision=2)
        with self.assertRaises(w.WorkflowError):human.guard(self.root,self.task_id)



if __name__ == '__main__': unittest.main()
