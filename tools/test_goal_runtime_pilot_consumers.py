"""Local isolated pilot-consumer checks. These never perform a native pilot."""
import copy
import datetime as dt
import json
import threading
import unittest
from unittest import mock

import flashcast_ops as ops
import goal_delivery_runtime as runtime
import qa_review_plan as review
import test_goal_runtime_consumers as base
import workflow_control as w

A = base.ASSISTANT
P = base.PRODUCER


class PilotConsumerTests(unittest.TestCase):
    def setUp(self):
        self.t = base.GoalRuntimeConsumerTests('runTest')
        self.t.setUp(); self.addCleanup(self.t.doCleanups)
        self.root = self.t.root

    def source(self):
        t = self.t
        self.parent = 'synthetic-business-parent'
        self.source_id = 'synthetic-legacy-complete-assignment'
        self.children = ['synthetic-approved-pilot', 'synthetic-approved-next']
        approval = {'parent_task_id': self.parent, 'authorized_by': 'operations', 'reviewer': A,
                    'state': 'approved_internal_pilot_not_dispatched', 'no_external_write': True,
                    'prepared_at': (dt.datetime.now(dt.timezone.utc)-dt.timedelta(seconds=3)).isoformat(), 'tasks': []}
        for child in self.children:
            path = 'reports/' + child + '-message.txt'
            (self.root / path).write_text('Synthetic approved internal instruction ' + child)
            approval['tasks'].append({'task_id': child, 'department': P, 'message_path': path,
                                      'message_sha256': w.file_digest(self.root, path)['sha256'],
                                      'approved_scope': 'department:' + P, 'already_sent': False})
        self.approval = w.file_digest(self.root, t.write('reports/approved-children.json', approval))
        message_path = 'reports/complete-message.txt'
        (self.root / message_path).write_text(self.source_id + ' ' + self.parent + ' full acceptance and internal pilot ' + self.approval['path'])
        message = w.file_digest(self.root, message_path)
        send = w.file_digest(self.root, t.write('reports/native-send.json', {'content': [{'type': 'text', 'text': json.dumps({'threadId': 'fixed-' + A})}], 'isError': False}))
        ack = w.file_digest(self.root, t.write('reports/native-ack.json', {'thread': {'id': 'fixed-' + A}, 'turns': [{'items': [{'type': 'agentMessage', 'id': 'synthetic-actual-ack', 'text': 'Synthetic nonempty complete assignment ACK.'}]}]}))
        t.task_id = self.source_id; t.fixture.task_id = self.source_id
        snapshot = {'task_id': self.source_id, 'current_state': 'dispatch_ready', 'plan_status': 'ready_to_send',
                    'owner_approval_required': False, 'departments': [{'department': A, 'chat_task_id': 'fixed-' + A}]}
        w.append_workflow_event(self.root, self.source_id, 'planned', dict(snapshot))
        w.append_workflow_event(self.root, self.source_id, 'dispatch_ready', {'plan_status':'ready_to_send'})
        w.atomic_write_json(w.snapshot_path(self.root, self.source_id), snapshot)
        request = t.requested(sender='operations', target=A, scope='project:synthetic:complete-assignment', payload=message)
        request['action_id'] = 'send-complete-accept-adopt-pilot'
        decision = t.policy(request)
        self.assertEqual(decision['status'], 'allow', decision)
        t.fixture.receipt('dispatch_sent', A, 'source-complete-dispatch', action_class='thread_message',
                          scope=request['scope'], action_id=request['action_id'], policy_decision_id=decision['decision_id'],
                          evidence=message['path'] + ';' + send['path'])
        t.fixture.receipt('chat_ack', A, 'source-complete-ack', evidence=ack['path'])
        rows = w._validate_receipt_chain(self.root, self.source_id)[0]
        self.source_bytes = w.receipts_path(self.root, self.source_id).read_bytes()
        self.binding = {'delegation_task_id': self.source_id, 'parent_task_id': self.parent, 'responsible_assistant': A,
                        'dispatch': {k: rows[0][k] for k in ('receipt_id', 'receipt_hash')},
                        'ack': {k: rows[1][k] for k in ('receipt_id', 'receipt_hash')},
                        'message': message, 'native_send': send, 'native_ack': ack, 'ack_message_id': 'synthetic-actual-ack',
                        'approved_goals': self.approval}
        binding = self.child(self.children[0])
        contract=w.read_json(self.root/'data/task-contract.json')
        contract['goal_delivery_runtime']['review_delegation_admission']=[{k:v for k,v in binding.items() if k not in {'task_id','child_message'}}]
        w.atomic_write_json(self.root/'data/task-contract.json',contract)
        return binding

    def child(self, task):
        t = self.t; t.task_id = task; t.fixture.task_id = task; t.fixture.routing_decisions = {}
        path = t.write('reports/' + task + '-goal.json', t.make_goal(parent_task_id=self.parent))
        runtime.initialize_goal(self.root, task, path)
        entry = next(x for x in w.read_json(self.root / self.approval['path'])['tasks'] if x['task_id'] == task)
        return {**self.binding, 'task_id': task, 'authority': t.snapshot()['goal_delivery']['authorization_pin'],
                'child_message': w.file_digest(self.root, entry['message_path'])}

    def bind(self, binding):
        path = self.t.write('reports/delegation-input.json', binding)
        return runtime.bind_review_delegation(self.root, self.t.task_id, path, A)

    def finish(self, binding, **changes):
        t = self.t
        self.bind(binding); t.dispatch(); t.fixture.receipt('chat_ack', P, 'producer-ack-' + t.task_id)
        candidate, producer_pin = t.producer_result(version=t.task_id)
        plan = t.review_plan(candidate)
        path = t.write('reports/' + t.task_id + '-review-plan.json', plan)
        review.bind_plan(self.root, task_id=t.task_id, plan_path=path, coordinator_role=A)
        return t.assistant_verdict(plan, producer_pin, review_delegation=binding, **changes)

    def test_legacy_complete_assignment_inherited_by_both_approved_children_then_final_accept(self):
        binding = self.source()
        for task in self.children:
            binding = binding if task == self.children[0] else self.child(task)
            result = self.finish(binding)
            self.assertEqual(result['workflow_state'], 'closed')
            self.assertEqual(self.bind(binding)['result'], 'duplicate_ignored')
            rows, invalid = w._validate_receipt_chain(self.root, task)
            self.assertEqual(invalid, [])
            self.assertFalse(any(r['department'] == A and r['receipt_type'] in {'dispatch_sent', 'chat_ack'} for r in rows))
            self.assertEqual(w.receipts_path(self.root, self.source_id).read_bytes(), self.source_bytes)
            self.assertNotEqual(w.read_json(w.snapshot_path(self.root, self.source_id))['current_state'], 'closed')

    def test_unapproved_identity_scope_fake_ack_and_pin_changes_rejected_without_child_receipts(self):
        binding = self.source()
        wrong = [dict(binding, delegation_task_id=self.parent), dict(binding, responsible_assistant='operations-assistant'),
                 dict(binding, parent_task_id='unapproved-parent'), dict(binding, task_id='unapproved-child'),
                 dict(binding, ack_message_id='fake-or-empty-ack'), dict(binding, ack=binding['dispatch']),
                 dict(binding, authority={**binding['authority'], 'sha256': '0'*64}),
                 dict(binding, approved_goals={**binding['approved_goals'], 'sha256': '0'*64}),
                 dict(binding, native_send=binding['native_ack']), dict(binding, child_message=binding['message'])]
        for item in wrong:
            with self.subTest(item=item), self.assertRaises((w.WorkflowError, ValueError, FileNotFoundError)):
                self.bind(item)
        self.assertEqual(w._validate_receipt_chain(self.root, self.t.task_id)[0], [])
        snap=self.t.snapshot();snap['goal_delivery']['authorized_scope'].append('unapproved-external-scope')
        w.append_workflow_event(self.root, self.t.task_id, snap['current_state'], {'goal_delivery': snap['goal_delivery']})
        w.atomic_write_json(w.snapshot_path(self.root, self.t.task_id), snap)
        with self.assertRaisesRegex(w.WorkflowError, 'exact approved child'):
            self.bind(binding)

    def test_native_ack_empty_or_other_fixed_thread_and_corrupt_source_chain_rejected(self):
        binding = self.source()
        native = runtime._native_document(self.root, binding['native_ack'])
        for change in [dict(native, thread={'id': 'foreign-thread'}), dict(native, turns=[])]:
            with self.subTest(change=change), mock.patch.object(runtime, '_native_document', side_effect=lambda root,pin: change if pin == binding['native_ack'] else {'threadId': 'fixed-'+A}):
                with self.assertRaisesRegex(w.WorkflowError, 'nonempty native ACK'):
                    self.bind(binding)
        with w.receipts_path(self.root, self.source_id).open('a') as stream: stream.write('{malformed-json}\n')
        with self.assertRaisesRegex(w.WorkflowError, 'intact actual delegation'):
            self.bind(binding)

    def test_binding_recovers_from_events_and_parent_can_append_without_new_dispatch(self):
        binding = self.source(); self.bind(binding)
        snap = self.t.snapshot(); snap.pop('review_delegation'); w.atomic_write_json(w.snapshot_path(self.root, self.t.task_id), snap)
        w.append_workflow_event(self.root, self.source_id, 'acknowledged', {'source_continuation': True})
        self.assertEqual(runtime.review_delegation(self.root, snap)['binding'], binding)
        self.assertEqual(self.bind(binding)['result'], 'duplicate_ignored')
        self.assertEqual(w.receipts_path(self.root, self.source_id).read_bytes(), self.source_bytes)

    def test_inherited_final_outbox_still_requires_exact_plan_candidate_and_delegation(self):
        binding = self.source()
        with self.assertRaises((w.WorkflowError, ops.OpsError)):
            self.finish(binding, evidence=[])

    def start_wait(self, role=A, targets=None):
        prior=w.read_json(self.root/"logs/goal-delivery-waits"/(role+".json"))
        plan=runtime.wait_plan(self.root,role,prior.get("cursors",{}))
        path=self.t.write('reports/begin-wait.json', {'targets': targets or plan['batches'][0], 'timeoutMs': 30000})
        return runtime.begin_wait(self.root,role,path)

    def save_wait(self, batch, cursors=None, role=A, name='completion'):
        path=self.t.write('reports/'+name+'.json', {'batch_id':batch['batch_id'], 'tool':'mcp__codex_app__wait_threads',
                         'timeoutMs':30000,'native_receipt_ref':'synthetic-native-'+name,'cursors':cursors or {batch['targets'][0]['threadId']:'cursor-'+name}})
        return runtime.record_wait(self.root,role,path)

    def test_original_wait_batch_can_close_after_result_queued_and_duplicate_is_idempotent(self):
        t=self.t;plan,producer=t.prepare_initial_review(); batch=self.start_wait()
        identity={'task_id':t.task_id,'sender_department':P,'candidate_version':'v1','outbox_path':producer['path'],'result_sha256':producer['sha256']}
        w.record_result_handoff(self.root,{**identity,'event':'notification_queued','idempotency_key':'queue-before-native-return'})
        self.assertEqual(runtime.wait_plan(self.root,A)['batches'],[])
        saved=self.save_wait(batch); self.assertEqual(self.save_wait(batch),saved)
        self.assertFalse(saved['proves_next_action']); self.assertFalse(saved['native_wakeup_guaranteed'])
        with self.assertRaisesRegex(w.WorkflowError,'conflicting'):
            self.save_wait(batch, name='conflicting')

    def test_wait_completion_commit_interruption_repaired_without_conflicting_result(self):
        t=self.t;t.initialize();t.dispatch();batch=self.start_wait()
        real=w.atomic_write_json
        def crash(path, value):
            if str(path).endswith('/'+A+'.json'):
                raise OSError('synthetic interruption after durable native completion')
            return real(path,value)
        with mock.patch.object(w,'atomic_write_json',side_effect=crash):
            with self.assertRaisesRegex(OSError,'interruption'):
                self.save_wait(batch)
        self.assertEqual(w.read_json(self.root/'logs/goal-delivery-waits/batches'/ (batch['batch_id']+'.json'))['state'],'completed')
        with self.assertRaisesRegex(w.WorkflowError,'conflicting'):
            self.save_wait(batch,name='wrong-native-result')
        saved=self.save_wait(batch)
        self.assertEqual(w.read_json(self.root/'logs/goal-delivery-waits'/ (A+'.json'))['cursors'],saved['cursors'])
        newer=self.start_wait(); self.save_wait(newer,name='newer-completion')
        before=w.read_json(self.root/'logs/goal-delivery-waits'/ (A+'.json'))['cursors']
        self.save_wait(batch)
        self.assertEqual(w.read_json(self.root/'logs/goal-delivery-waits'/ (A+'.json'))['cursors'],before)

    def test_wait_foreign_unfrozen_and_never_dispatched_targets_rejected(self):
        t=self.t;t.initialize();t.dispatch();batch=self.start_wait()
        for role,cursors in [(A,{'foreign-thread':'fake'}),('operations-assistant',None)]:
            with self.subTest(role=role), self.assertRaisesRegex(w.WorkflowError,'in-flight batch'):
                self.save_wait(batch,cursors,role)
        with self.assertRaisesRegex(w.WorkflowError,'in-flight batch'):
            self.start_wait(targets=[{'threadId':'never-dispatched'}])
        with self.assertRaisesRegex(w.WorkflowError,'in-flight batch'):
            self.save_wait(dict(batch,batch_id='00000000-0000-0000-0000-000000000000'))

    def test_wait_targets_original_dispatch_thread_when_registry_rebound(self):
        t=self.t;t.initialize();t.dispatch()
        registry=w.read_json(self.root/'data/department-registry.json')
        next(x for x in registry['departments'] if x['id']==P)['chat_binding']['task_id']='new-unassigned-thread'
        w.atomic_write_json(self.root/'data/department-registry.json',registry)
        batch=self.start_wait()
        self.assertEqual(batch['targets'],[{'threadId':'fixed-'+P}])
        self.save_wait(batch)

    def test_parallel_disjoint_wait_batches_merge_cursors_without_lost_updates(self):
        t=self.t; registry=w.read_json(self.root/'data/department-registry.json'); producers=[P]
        for i in range(8):
            role='synthetic-producer-'+str(i)
            row=copy.deepcopy(next(x for x in registry['departments'] if x['id']==P));row['id']=role;row['chat_binding'].update(task_id='fixed-'+role,title=role);registry['departments'].append(row);producers.append(role)
        w.atomic_write_json(self.root/'data/department-registry.json',registry)
        t.initialize(producer_departments=producers,authorized_scope=['department:'+role for role in producers])
        for role in producers:t.dispatch(role)
        plan=runtime.wait_plan(self.root,A)
        batches=[self.start_wait(targets=targets) for targets in plan['batches']]
        errors=[]; paths=[]
        for i,b in enumerate(batches):
            tid=b['targets'][0]['threadId'];paths.append(t.write('reports/parallel-'+str(i)+'.json',{'batch_id':b['batch_id'],'tool':b['tool'],'timeoutMs':30000,'native_receipt_ref':'synthetic-'+str(i),'cursors':{tid:'cursor-'+str(i)}}))
        def consume(path):
            try:runtime.record_wait(self.root,A,path)
            except Exception as error:errors.append(str(error))
        threads=[threading.Thread(target=consume,args=(path,)) for path in paths]
        for thread in threads:thread.start()
        for thread in threads:thread.join()
        self.assertEqual(errors,[])
        self.assertEqual(len(w.read_json(self.root/'logs/goal-delivery-waits'/ (A+'.json'))['cursors']),2)

    def test_same_target_second_wait_rejected_until_original_batch_completed(self):
        t=self.t;t.initialize();t.dispatch();batch=self.start_wait()
        with self.assertRaisesRegex(w.WorkflowError,'overlapping'):
            self.start_wait()
        self.save_wait(batch);self.start_wait()

    def test_third_child_not_in_original_approval_is_rejected(self):
        binding=self.source();t=self.t;t.task_id='synthetic-unapproved-third';t.initialize(parent_task_id=self.parent)
        with self.assertRaisesRegex(w.WorkflowError,'not in the original approved list'):
            self.bind({**binding,'task_id':t.task_id})
        self.assertEqual(w._validate_receipt_chain(self.root,t.task_id)[0],[])

    def test_recomputed_changed_approval_pin_and_unapproved_third_child_rejected(self):
        binding=self.source()
        approval=w.read_json(self.root/self.approval['path']);approval['tasks'][0]['approved_scope']='unapproved-scope'
        w.atomic_write_json(self.root/self.approval['path'],approval)
        altered={**binding,'approved_goals':w.file_digest(self.root,self.approval['path'])}
        with self.assertRaisesRegex(w.WorkflowError,'original frozen delegation admission'):
            self.bind(altered)

    def test_exact_coordinator_producer_approved_message_passes_with_modes_unchanged(self):
        t=self.t;role='operations-assistant-3';registry=w.read_json(self.root/'data/department-registry.json')
        next(x for x in registry['departments'] if x['id']==role)['mode']='coordinator';w.atomic_write_json(self.root/'data/department-registry.json',registry)
        policy=w.read_json(self.root/'data/action-policy.json');policy['routing_policy']['thread_message_target_modes']=['worker','gate'];w.atomic_write_json(self.root/'data/action-policy.json',policy)
        request=t.requested(target=role,scope='department:'+role)
        t.initialize(primary_owner=role,producer_departments=[role],authorized_scope=[request['scope']],approved_actions=[request],human_authorization={**t.make_goal()['human_authorization'],'executor':role,'scope':request['scope']})
        self.assertEqual(t.policy(request)['status'],'allow')
        self.assertEqual(w.read_json(self.root/'data/action-policy.json')['routing_policy']['thread_message_target_modes'],['worker','gate'])
        for key,value in [('action_id','unapproved'),('payload_sha256','0'*64),('scope','outside'),('target_thread_id','foreign'),('sender_department',role),('target_department','operations')]:
            with self.subTest(key=key):self.assertEqual(t.policy({**request,key:value})['status'],'deny')
        registry=w.read_json(self.root/'data/department-registry.json');next(x for x in registry['departments'] if x['id']==role)['new_dispatch_enabled']=False;w.atomic_write_json(self.root/'data/department-registry.json',registry)
        self.assertEqual(t.policy(request)['status'],'deny')


if __name__ == '__main__':
    unittest.main()
