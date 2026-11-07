import datetime as dt
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import receipt_obligation_consumer as consumer
import result_coordination as results
import workflow_control as workflow


class RootSerialReadyDiscoveryTest(unittest.TestCase):
    def test_owned_event_observation_uses_its_actual_action_instead_of_earlier_intake_action(self):
        request=self.write('owned-request.json',{'task_id':'original-goal-v1','action_id':'actual-owned-action','scope':self.scope})
        directory=self.root/'owned';directory.mkdir()
        (directory/'native-queue-intent.json').write_text('{"started_at":"1970-01-01T00:00:00+00:00"}')
        slot={'request':request,'root_source':workflow.file_digest(self.root,self.record_path),
              'target_thread_id':self.window,'directory':'owned'}
        history=Mock();history.call.side_effect=[{'thread':self.thread},{'data':[self.turn]}]
        seen=[]
        def inspect(root,proof,record,final):
            seen.append(record['current_action_id']);raise workflow.WorkflowError('stop before any release effect')
        with patch.object(consumer,'ROOT_SERIAL_PATH',self.record_path),patch.object(consumer,'_root_slot_read',return_value=slot), \
                patch.object(consumer,'_observe_original',return_value={'turn_id':self.turn_id}), \
                patch.object(results,'_validate_queued',return_value=self.queue),patch.object(consumer,'_root_serial_batch',side_effect=inspect):
            outcome=consumer.observe_root_serial(self.root,SimpleNamespace(history=history))
        self.assertEqual(seen,['actual-owned-action'])
        self.assertFalse(outcome['root_release_recorded'])

    def test_canonical_owner_projection_requires_same_normal_ready_sdk_identity(self):
        fixed={'task_id':self.window,'cwd':str(self.root),'title':'Original owner','host_id':'local','project_id':'original-project'}
        sdk={'id':self.window,'cwd':str(self.root),'title':fixed['title'],'hostId':'local','kind':'codex'}
        pin=self.write('ready-sdk.json',{'content':[{'type':'text','text':json.dumps({'thread':sdk,'turns':[self.turn]})}]})
        queued={**self.identity,'source_thread_id':self.window,'source_turn_id':self.turn_id,'actual_native_completion':pin}
        raw={'source':'official_app_server_readonly_owner_handoff_projection','observed_at_UTC':dt.datetime.now(dt.timezone.utc).isoformat(),
             'owner_ready_result':self.identity,'native':{'schemaVersion':1,'thread':{'id':self.window,'cwd':str(self.root),'name':fixed['title']},'turns':[self.turn]}}
        with patch.object(results,'_validate_queued',return_value=queued):
            self.assertEqual(consumer._owner_handoff_native_identity(self.root,raw,self.identity,fixed),sdk)
            collaborator={**self.identity,'sender_department':'another-producer'}
            self.assertEqual(consumer._owner_handoff_native_identity(self.root,raw,collaborator,fixed,'system-development'),sdk)
            original_text=raw['native']['turns'][0]['items'][0]['text']
            raw['native']['turns'][0]['items'][0]['text']='fabricated acknowledgement'
            with self.assertRaises(workflow.WorkflowError):consumer._owner_handoff_native_identity(self.root,raw,self.identity,fixed)
            raw['native']['turns'][0]['items'][0]['text']=original_text
            raw['native']['thread']['hostId']='different-host'
            with self.assertRaises(workflow.WorkflowError):consumer._owner_handoff_native_identity(self.root,raw,self.identity,fixed)
            raw['native']['thread'].pop('hostId');queued['source_turn_id']='another-turn'
            with self.assertRaises(workflow.WorkflowError):consumer._owner_handoff_native_identity(self.root,raw,self.identity,fixed)

    def test_owned_return_metadata_is_derived_from_completed_original_input_without_copying_unrelated_outputs(self):
        from department_event_dispatcher import OfficialQueueTransport
        source=self.write('decision.json',{'real':'original decision'});body=(self.root/'decision.json').read_text()
        message=self.write('reply-message.json',{'original':'reply'});text=(self.root/message['path']).read_text()
        notice=self.write('notice.json',{'identity':self.identity})
        request=self.write('reply-request.json',{'task_id':self.identity['task_id'],'payload':message,'routine_decision_reply':{'notification':notice}})
        directory=self.root/'reply';directory.mkdir()
        effect={'matching_native_effects':[{'turn_id':self.turn_id,'turn_status':'completed'}]}
        (directory/'latest-original-effect-readback.json').write_text(json.dumps(effect))
        def command(identifier,text,output):return {'id':identifier,'type':'commandExecution','status':'completed','exitCode':0,
            'cwd':str(self.root),'command':text,'aggregatedOutput':output}
        incoming={'id':'input','type':'userMessage','content':[{'type':'text','text':text}]}
        ack={'id':'ack','type':'agentMessage','phase':'commentary','text':'Read actual source'}
        cat=command('cat','cat decision.json',body);digest=command('hash','shasum -a 256 decision.json',source['sha256']+'  decision.json\n')
        final={'id':'finished','type':'agentMessage','phase':'final_answer','text':'Original owner work returned'}
        turn={**self.turn,'items':[incoming,ack,cat,digest,command('unrelated','echo unrelated','do not copy this output'),final]}
        fixed={'task_id':self.window,'cwd':str(self.root),'title':'owner','host_id':'local','project_id':'p'}
        ctx={'identity':self.identity,'original_owner':'system-development'}
        decision={'record_id':'actual-decision','decision_source':source}
        outbox=self.write('owner-return.json',{'evidence':[source]})
        queued={**self.identity,'event':'notification_queued','source_thread_id':self.window,'source_turn_id':self.turn_id,
                'actual_native_completion':{'actual':'SDK source'},'outbox':outbox}
        intent={'request':request,'directory':'reply','action_id':'actual-reply'}
        view={'routine_semantics':{'routine_reply_intent':intent,'original_decision_record_id':'actual-decision'}}
        transport=OfficialQueueTransport.__new__(OfficialQueueTransport);transport.history=Mock()
        transport.history.call.side_effect=[{'thread':{'id':self.window,'name':'owner','cwd':str(self.root)}},{'data':[turn]}]
        captured=[]
        def register(root,task,path):
            item=workflow.read_json(root/path);native=consumer.doc(root,item['completed_owner_native']);captured.append(native)
            self.assertEqual(item['input_message_id'],'input');self.assertEqual(item['decision_source_command_id'],'cat')
            self.assertNotIn('do not copy this output',json.dumps(native))
            return {'result':'recorded','message_sent':False}
        with patch.object(consumer,'context',return_value=ctx),patch.object(consumer,'_owner_handoff_entries',return_value=[]), \
                patch.object(workflow,'department_registry',return_value={'system-development':{'chat_binding':fixed}}), \
                patch.object(workflow,'_result_handoff_rows',return_value=[decision,queued]), \
                patch.object(consumer,'record_owner_handoff_source',side_effect=register):
            value=consumer.record_observed_owner_handoff(self.root,{'identity':self.identity},{'record_id':'actual-intake'},transport,view)
            self.assertFalse(value['message_sent']);self.assertEqual(len(captured),1)
            effect['matching_native_effects'][0]['turn_status']='inProgress'
            (directory/'latest-original-effect-readback.json').write_text(json.dumps(effect))
            self.assertIsNone(consumer.record_observed_owner_handoff(self.root,{'identity':self.identity},{'record_id':'actual-intake'},transport,view))
            self.assertEqual(transport.history.call.call_count,2)

    def test_released_owner_batch_keeps_original_completion_separate_from_new_finite_head(self):
        at=dt.datetime.now(dt.timezone.utc)
        record={'current_state':'completed','current_active_was_new_recovery':False,
                'current_active_original_window':self.window,'current_active_turn':self.turn_id,
                'current_release_native_proof':self.write('prior.json',{'thread':self.thread,'turns':[self.turn]}),
                'current_release_observed_at_UTC':at.isoformat()}
        new={'id':'later-status-turn','status':'completed','startedAt':3,'completedAt':4,
             'items':[{'type':'agentMessage','id':'later-final','phase':'final_answer','text':'Later status only'}]}
        with patch.object(consumer,'_root_serial_batch',return_value={'kind':'original_event_existing_decision_owner_handoff'}):
            proof=consumer._released_owner_head_proof(self.root,record,self.thread,[new],at)
            self.assertEqual(proof['turns'][0]['id'],self.turn_id)
            self.assertEqual(proof['fresh_current_head']['turns'][0]['id'],'later-status-turn')
            with self.assertRaises(workflow.WorkflowError):
                consumer._released_owner_head_proof(self.root,record,self.thread,[{**new,'status':'inProgress'}],at)
            with self.assertRaises(workflow.WorkflowError):
                consumer._released_owner_head_proof(self.root,record,self.thread,[{**new,'error':{'message':'failed'}}],at)
        with patch.object(consumer,'_root_serial_batch',return_value={'kind':'unverified_maintenance'}):
            with self.assertRaises(workflow.WorkflowError):
                consumer._released_owner_head_proof(self.root,record,self.thread,[new],at)

    def test_owner_handoff_refresh_cannot_change_identity_or_native_work(self):
        old={'task_id':'original','decision_record_id':'actual','completed_owner_native':{'sha':'same'},
             'original_input_effect_readback':{'sha':'old-observation'}}
        new={**old,'original_input_effect_readback':{'sha':'frozen-observation'}}
        self.assertTrue(consumer._same_owner_handoff_except_readback(old,new))
        self.assertFalse(consumer._same_owner_handoff_except_readback(old,{**new,'decision_record_id':'another'}))
        self.assertFalse(consumer._same_owner_handoff_except_readback(old,{**new,'completed_owner_native':{'sha':'fabricated'}}))

    def test_existing_decision_event_releases_only_after_exact_input_ack_and_verified_handoff(self):
        payload=self.write('event-payload.json',{'event':'original'})
        body=(self.root/payload['path']).read_text()
        notice=self.write('notice.json',{'actual':'notice'})
        request={'task_id':'original-goal-v1','action_id':'original-event','scope':self.scope,
                 'target_thread_id':self.window,'payload':payload,
                 consumer.MARKER:{'notification':notice,'received_record_id':'actual-intake'}}
        pin=self.write('original-event.json',request)
        directory=self.root/'queued';directory.mkdir()
        (directory/'native-queue-result.json').write_text(json.dumps({'exit_code':0,'finished_at':'1970-01-01T00:00:00+00:00'}))
        slot={'request':pin,'action_id':request['action_id'],'scope':self.scope,
              'target_thread_id':self.window,'directory':'queued'}
        record={'current_active_original_window':self.window,'current_active_turn':self.turn_id,
                'current_scope':self.scope,'current_action_id':request['action_id']}
        final={'type':'agentMessage','phase':'final_answer','text':'original-goal-v1 actual-intake original-event'}
        items=[{'type':'userMessage','content':[{'type':'text','text':body}]},
               {'type':'agentMessage','phase':'commentary','text':'Taking original event'},final]
        proof={'routine_receipt':notice,'turns':[{'id':self.turn_id,'startedAt':1,'items':items}]}
        ctx={'intake':{'record_id':'actual-intake'},'identity':{'task_id':request['task_id']}}
        routine={'coordination_obligation_completed':True,'native_owner_handoff':{'coordination_obligation_completed':True},
                 'original_decision_record_id':'earlier-actual-decision'}
        with patch.object(consumer,'_root_slot_read',return_value=slot),patch.object(consumer,'_intents',return_value=[{'request':pin}]):
            value=consumer._root_existing_decision_followthrough(self.root,proof,record,final,ctx,routine)
            self.assertFalse(value['business_goal_closed'])
            self.assertEqual(value['decision_record_id'],'earlier-actual-decision')
            items[0]['content'][0]['text']='another event'
            with self.assertRaises(workflow.WorkflowError):
                consumer._root_existing_decision_followthrough(self.root,proof,record,final,ctx,routine)
            items[0]['content'][0]['text']=body
            routine['native_owner_handoff']['coordination_obligation_completed']=False
            with self.assertRaises(workflow.WorkflowError):
                consumer._root_existing_decision_followthrough(self.root,proof,record,final,ctx,routine)
        routine['native_owner_handoff']['coordination_obligation_completed']=True
        record['current_release_observer']={'service_origin':consumer.SERVICE_ORIGIN,'normal_intent_request':pin}
        with patch.object(consumer,'_root_slot_read',return_value=None),patch.object(consumer,'_intents',return_value=[{'request':pin,'directory':'queued'}]):
            value=consumer._root_existing_decision_followthrough(self.root,proof,record,final,ctx,routine)
            self.assertEqual(value['kind'],'original_event_existing_decision_owner_handoff')
            record['current_release_observer'].pop('normal_intent_request')
            value=consumer._root_existing_decision_followthrough(self.root,proof,record,final,ctx,routine)
            self.assertEqual(value['original_action_id'],'original-event')

    def test_direct_send_intent_is_audit_only_with_all_original_pins_and_policy(self):
        payload=self.write('payload.json',{'actual':'body'})
        request={'task_id':'original-goal-v1','action_id':'same-action','scope':self.scope,
                 'sender_department':'operations','target_department':'system-development',
                 'target_thread_id':self.window,'payload':payload,'payload_sha256':payload['sha256'],
                 'action_class':'thread_message','delivery_mode':'mcp_direct_send'}
        policy={**request,'decision_id':'normal-policy','department':'operations',
                'status':'allow','external_permission_issued':False}
        intent={'task_id':request['task_id'],'policy_decision_id':policy['decision_id'],
                'request':self.write('request.json',request),
                'preparation':self.write('prepared.json',{'status':'ready_to_send','policy_decision':policy,'payload':payload})}
        event={'task_id':request['task_id'],'state':'dispatch_intent','details':{
            'actor':'operations','action_id':request['action_id'],'target_department':request['target_department'],
            'target_thread_id':self.window,'policy_decision_id':policy['decision_id'],
            'direct_send_intent':self.write('intent.json',intent)}}
        with patch.object(workflow,'read_jsonl',return_value=[policy]):
            self.assertTrue(workflow._exact_direct_dispatch_audit(self.root,event))
            event['details']['actor']='another-actor'
            self.assertFalse(workflow._exact_direct_dispatch_audit(self.root,event))
            event['details']['actor']='operations'
            (self.root/'payload.json').write_text('changed')
            self.assertFalse(workflow._exact_direct_dispatch_audit(self.root,event))

    def test_actual_separate_owner_cat_and_hash_are_both_required_same_turn(self):
        source={'path':'decision.json','sha256':hashlib.sha256(b'{"real":true}').hexdigest()}
        def command(text,output):
            return {'type':'commandExecution','status':'completed','exitCode':0,'cwd':str(self.root),
                    'command':text,'output':{'text':output,'truncated':False}}
        cat=command('cat decision.json','{"real":true}')
        digest=command('shasum -a 256 decision.json',source['sha256']+'  decision.json\n')
        valid=lambda items,c=cat:consumer._owner_decision_read_matches(self.root,items,0,len(items)-1,c,source,b'{"real":true}')
        self.assertTrue(valid([{},cat,digest,{}]))
        self.assertFalse(valid([{},cat,{}]))
        self.assertFalse(valid([digest,cat,{}]))
        self.assertFalse(valid([{},cat,{**digest,'output':{'text':'wrong','truncated':False}},{}]))
        self.assertFalse(valid([{},cat,digest,{}],{**cat,'command':'cat other.json'}))
        self.assertFalse(valid([{},cat,digest,{}],{**cat,'output':{'text':'changed','truncated':False}}))
        combined=command('shasum -a 256 decision.json && cat decision.json',digest['output']['text']+cat['output']['text'])
        self.assertTrue(valid([{},combined,{}],combined))

    def setUp(self):
        directory = tempfile.TemporaryDirectory(
            dir=Path(__file__).resolve().parents[1] / '.test-tmp')
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.window = 'original-window'
        self.turn_id = 'original-turn'
        self.scope = 'project:example:delivery'
        evidence = self.write('evidence.json', {'checked': True})
        self.outbox = self.write('outbox.json', {
            'task_id': 'original-goal-v1', 'department': 'system-development',
            'scope': self.scope, 'status': 'partial', 'evidence': [evidence],
        })
        self.identity = {
            'task_id': 'original-goal-v1', 'sender_department': 'system-development',
            'candidate_version': 'batch-v1', 'result_sha256': self.outbox['sha256'],
        }
        self.ready = {'type': 'agentMessage', 'phase': 'commentary', 'id': 'ready',
                      'text': 'FLASHCAST_DELIVERY_READY ' + json.dumps({
                          **self.identity, 'outbox_path': self.outbox['path'], 'batch_complete': True,
                      })}
        self.final = {'type': 'agentMessage', 'phase': 'final_answer', 'id': 'final',
                      'text': 'Readback complete. Evidence: evidence.json'}
        self.turn = {'id': self.turn_id, 'status': 'completed', 'startedAt': 1,
                     'completedAt': 2, 'items': [self.ready, self.final]}
        self.thread = {'id': self.window, 'status': {'type': 'idle'}}
        self.queue = {'outbox': self.outbox, 'source_thread_id': self.window,
                      'source_turn_id': self.turn_id}
        self.record_path = 'serial.json'
        self.write(self.record_path, {
            'schema': 'hq-serial-original-recovery-intent/v1', 'one_new_window_at_a_time': True,
            'current_active_original_window': self.window, 'current_active_turn': self.turn_id,
            'current_scope': self.scope, 'current_state': 'inProgress',
        })

    def write(self, relative, document):
        (self.root / relative).write_text(json.dumps(document), encoding='utf-8')
        return workflow.file_digest(self.root, relative)

    def observe(self):
        history = Mock()
        history.call.side_effect = [{'thread': self.thread}, {'data': [self.turn]}]
        with patch.object(consumer, 'ROOT_SERIAL_PATH', self.record_path), \
                patch.object(consumer, '_root_slot_read', return_value=None), \
                patch.object(results, '_validate_queued', return_value=self.queue) as queued:
            outcome = consumer.observe_root_serial(self.root, SimpleNamespace(history=history))
        return outcome, queued

    def test_recovers_from_exact_ready_without_sha_in_final_or_caller_event(self):
        outcome, queued = self.observe()
        self.assertTrue(outcome['root_release_recorded'], outcome)
        self.assertFalse(outcome['business_goal_closed'])
        queued.assert_called_with(self.root, self.identity)

    def test_maintenance_final_cannot_release_business(self):
        self.final['text'] = 'Maintenance complete.'
        outcome, _ = self.observe()
        self.assertFalse(outcome['root_release_recorded'])

    def test_completed_notification_accepts_separate_newer_finite_head(self):
        latest = {**self.turn, 'id': 'later-turn', 'startedAt': 3, 'completedAt': 4,
                  'items': [{**self.final, 'id': 'later-final'}]}
        proof = {'fresh_current_head': {'thread': self.thread, 'turns': [latest]}}
        observed = dt.datetime.fromtimestamp(5, dt.timezone.utc)
        self.assertEqual(consumer._notification_refresh_head(proof, self.window, self.turn, observed),
                         latest)
        self.assertEqual(self.turn['id'], self.turn_id)

    def test_notification_refresh_rejects_overlapping_or_active_head(self):
        latest = {**self.turn, 'id': 'later-turn', 'startedAt': 1.5, 'completedAt': 4}
        proof = {'fresh_current_head': {'thread': dict(self.thread), 'turns': [latest]}}
        observed = dt.datetime.fromtimestamp(5, dt.timezone.utc)
        with self.assertRaisesRegex(workflow.WorkflowError, 'overlap'):
            consumer._notification_refresh_head(proof, self.window, self.turn, observed)
        latest['startedAt'] = 3
        proof['fresh_current_head']['thread']['status'] = {'type': 'active'}
        with self.assertRaisesRegex(workflow.WorkflowError, 'active'):
            consumer._notification_refresh_head(proof, self.window, self.turn, observed)

    def test_queued_result_from_other_turn_cannot_release_current_turn(self):
        self.queue['source_turn_id'] = 'previous-turn'
        outcome, _ = self.observe()
        self.assertFalse(outcome['root_release_recorded'])

    def test_conflicting_ready_declarations_do_not_supply_identity(self):
        self.turn['items'].insert(1, {**self.ready, 'id': 'duplicate'})
        outcome, queued = self.observe()
        self.assertFalse(outcome['root_release_recorded'])
        queued.assert_not_called()

    def committed_legacy_batch(self):
        self.final['text'] = 'Readback complete. Evidence: evidence.json'
        evidence = workflow.file_digest(self.root, 'evidence.json')
        self.outbox = self.write('outbox.json', {
            'task_id': self.identity['task_id'], 'department': 'system-development',
            'scope': self.scope, 'status': 'completed',
            'primary_deliverable': evidence, 'evidence': [evidence],
        })
        self.identity['result_sha256'] = self.outbox['sha256']
        self.ready['text'] = 'FLASHCAST_DELIVERY_READY task_id=original-goal-v1 result_sha256=' + self.outbox['sha256']
        self.queue.update(self.identity, outbox=self.outbox, event='notification_queued',
                          record_id='actual-queue-record', result_source_phase='delivery_ready',
                          source_message_id=self.ready['id'],
                          source_reply_sha256=hashlib.sha256(self.ready['text'].encode()).hexdigest())
        self.proof = {'thread': self.thread, 'turns': [self.turn],
                      'result_identity': self.identity, 'outbox': self.outbox}
        self.record = {'current_active_original_window': self.window,
                       'current_active_turn': self.turn_id,
                       'current_scope': self.scope, 'current_state': 'completed'}

    def batch(self):
        with patch.object(results, '_validate_queued', return_value=self.queue):
            return consumer._root_serial_batch(self.root, self.proof, self.record, self.final)

    def test_committed_same_turn_legacy_reply_and_final_artifact_bind_finite_batch(self):
        self.committed_legacy_batch()
        self.assertEqual(self.batch()['kind'], 'normal_producer_batch')

    def test_admitted_primary_delivery_alias_keeps_original_outbox_bytes(self):
        self.committed_legacy_batch()
        box = workflow.read_json(self.root / 'outbox.json')
        box['primary_delivery'] = box.pop('primary_deliverable')
        self.outbox = self.write('outbox.json', box)
        self.identity['result_sha256'] = self.outbox['sha256']
        self.queue.update(self.identity, outbox=self.outbox)
        self.proof.update(result_identity=self.identity, outbox=self.outbox)
        before = (self.root / 'outbox.json').read_bytes()
        self.assertEqual(self.batch()['kind'], 'normal_producer_batch')
        self.assertEqual((self.root / 'outbox.json').read_bytes(), before)

    def test_conflicting_primary_delivery_alias_cannot_release_serial_capacity(self):
        self.committed_legacy_batch()
        box = workflow.read_json(self.root / 'outbox.json')
        box['primary_delivery'] = self.write('different.json', {'other':True})
        self.outbox = self.write('outbox.json', box)
        self.identity['result_sha256'] = self.outbox['sha256']
        self.queue.update(self.identity, outbox=self.outbox)
        self.proof.update(result_identity=self.identity, outbox=self.outbox)
        with self.assertRaises(workflow.WorkflowError): self.batch()

    def test_observer_preserves_admitted_multiline_ready_for_exact_queue_source_hash(self):
        self.committed_legacy_batch()
        self.ready['text'] = 'FLASHCAST_DELIVERY_READY\n\ntask_id: original-goal-v1\nsha256: ' + self.outbox['sha256']
        self.queue['source_reply_sha256'] = hashlib.sha256(self.ready['text'].encode()).hexdigest()
        self.final['text'] += '\nActual result SHA: ' + self.outbox['sha256']
        history = Mock()
        history.call.side_effect = [{'thread':self.thread},{'data':[self.turn]}]
        store = SimpleNamespace(rows=lambda:[{'identity_json':json.dumps(self.identity)}])
        with patch.object(consumer,'ROOT_SERIAL_PATH',self.record_path), \
             patch.object(consumer,'_root_slot_read',return_value=None), \
             patch.object(results,'_validate_queued',return_value=self.queue):
            outcome = consumer.observe_root_serial(self.root,SimpleNamespace(history=history),store=store)
        self.assertTrue(outcome['root_release_recorded'],outcome)
        self.assertFalse(outcome['business_goal_closed'])

    def blocked_multiline_observation(self, mode=None):
        self.committed_legacy_batch()
        box = workflow.read_json(self.root/'outbox.json')
        box.update(status='blocked',next_actions=[{'owner':'original-handler','action':'decide exact original readonly source'}])
        box['primary_delivery'] = box.pop('primary_deliverable')
        if mode == 'ambiguous':box['next_actions'].append({'owner':'another-handler','action':'different next action'})
        if mode == 'missing_evidence':box['evidence']=[]
        if mode == 'unknown':box['status']='unknown'
        self.outbox=self.write('outbox.json',box)
        self.identity['result_sha256']=self.outbox['sha256']
        self.ready['text']='FLASHCAST_DELIVERY_READY\n\nsha256: '+self.outbox['sha256']
        self.queue.update(self.identity,outbox=self.outbox,source_reply_sha256=hashlib.sha256(self.ready['text'].encode()).hexdigest())
        if mode == 'wrong_turn':self.queue['source_turn_id']='other-turn'
        history=Mock();history.call.side_effect=[{'thread':self.thread},{'data':[self.turn]}]
        store=SimpleNamespace(rows=lambda:[{'identity_json':json.dumps(self.identity)}])
        with patch.object(consumer,'ROOT_SERIAL_PATH',self.record_path), \
             patch.object(consumer,'_root_slot_read',return_value=None), \
             patch.object(results,'_validate_queued',return_value=self.queue), \
             patch.object(workflow,'department_registry',return_value={'original-handler':{}}):
            return consumer.observe_root_serial(self.root,SimpleNamespace(history=history),store=store)

    def test_exact_blocked_report_releases_only_finite_boundary_to_its_named_handler(self):
        outcome=self.blocked_multiline_observation()
        self.assertTrue(outcome['root_release_recorded'],outcome)
        self.assertEqual(outcome['current_state'],'safe_dependency')
        self.assertFalse(outcome['business_goal_closed'])

    def test_ambiguous_unknown_unbound_or_other_turn_blocked_report_cannot_release(self):
        for mode in ('ambiguous','missing_evidence','unknown','wrong_turn'):
            with self.subTest(mode=mode):
                self.assertFalse(self.blocked_multiline_observation(mode)['root_release_recorded'])

    def test_real_notification_intake_prioritizes_its_obligation_without_removing_older_work(self):
        from department_event_dispatcher import Store
        self.thread.update(name='Original handler',cwd=str(self.root),hostId='local',projectId='original-project')
        message='Exact original notification'
        (self.root/'message.txt').write_text(message)
        user={'type':'userMessage','id':'input','content':[{'type':'text','text':message}]}
        ack={'type':'agentMessage','id':'intake-ack','phase':'commentary','text':'Original received'}
        self.turn['items']=[user,ack,self.final]
        normal={'target':{'task_id':self.window,'title':'Original handler','cwd':str(self.root),
                          'host_id':'local','project_id':'original-project'},
                'request':{'payload':{'path':'message.txt'}},'fields':{'scope':self.scope}}
        record=workflow.read_json(self.root/self.record_path)
        record['older_unfinished_marker']={'task_id':'older-original-goal','state':'open'}
        self.write(self.record_path,record)
        slot={'kind':consumer.NOTIFICATION_KIND,'root_source':workflow.file_digest(self.root,self.record_path),
              'target_thread_id':self.window,'action_id':'exact-original-notice','scope':self.scope,
              'identity':self.identity,'request':self.outbox}
        store=Store(self.root)
        store.checkpoint_value(consumer.ROOT_SERIAL_SLOT)
        store.db.execute('INSERT INTO checkpoints VALUES(?,?)',
                         (consumer.ROOT_SERIAL_SLOT,json.dumps(slot,ensure_ascii=False,sort_keys=True)))
        store.db.commit();store.close()
        notice=self.write('notice.json',{})
        intake={'actual_receiver_native':notice,'actual_receiver_message_id':ack['id'],'record_id':'real-intake'}
        history=Mock();history.call.side_effect=[{'thread':self.thread},{'data':[self.turn]}]
        with patch.object(consumer,'ROOT_SERIAL_PATH',self.record_path), \
             patch.object(consumer,'_notification_slot_prepared',return_value=normal), \
             patch.object(consumer,'_notification_native_metadata',return_value={}), \
             patch.object(consumer,'_notification_capacity_batch',return_value={'current_state':'completed','received_record_id':'real-intake'}), \
             patch('goal_delivery_runtime._native_document',return_value={'thread':self.thread,'turns':[self.turn]}), \
             patch.object(results,'_notification_path',return_value=self.root/'notice.json'), \
             patch.object(results,'received_notification',return_value=intake):
            outcome=consumer._observe_notification_serial(self.root,SimpleNamespace(history=history))
        self.assertTrue(outcome['root_release_recorded'],outcome)
        current=workflow.read_json(self.root/self.record_path)
        self.assertEqual(current['current_next_obligation_identity'],self.identity)
        self.assertEqual(current['current_next_obligation_received_record_id'],'real-intake')
        self.assertEqual(current['older_unfinished_marker'],record['older_unfinished_marker'])
        self.assertFalse(outcome['business_goal_closed'])

    def test_owned_unknown_precedes_current_decision_but_old_readbacks_do_not_starve_it(self):
        from department_event_dispatcher import Store
        store=Store(self.root);self.addCleanup(store.close)
        rows=[{'event_key':key}for key in ('historical','current','other')]
        store.receipt_scan_full_selection=True
        store.receipt_scan_preferred_key='current'
        _,ordered=consumer._scan_plan(store,rows,{'historical'},continuation=False)
        self.assertEqual([r['event_key']for r in ordered],['current','historical','other'])
        consumer._scan_checkpoint(store,{'schema':consumer.SCAN_CHECKPOINT,
            'known':['historical','current','other'],'pending':['other']})
        store.receipt_scan_preferred_key=None
        _,ordered=consumer._scan_plan(store,rows,{'historical'},continuation=False)
        self.assertEqual([r['event_key']for r in ordered],['other'])
        store.db.execute('INSERT INTO checkpoints VALUES(?,?)',('current-receipt-followthrough-inflight','historical'))
        store.db.commit();store.receipt_scan_preferred_key='current'
        _,ordered=consumer._scan_plan(store,rows,{'historical'},continuation=False)
        self.assertEqual([r['event_key']for r in ordered],['historical','current','other'])
        store.receipt_scan_event_keys={'other'}
        _,ordered=consumer._scan_plan(store,rows,{'historical'},continuation=False)
        self.assertEqual([r['event_key']for r in ordered],['historical','other','current'])

    def test_source_changed_while_capacity_blocked_is_consumed_once_when_eligible(self):
        from department_event_dispatcher import Store
        store=Store(self.root);self.addCleanup(store.close)
        rows=[{'event_key':key}for key in ('current','older')]
        store.receipt_scan_full_selection=True
        store.receipt_scan_preferred_key='current'
        store.receipt_scan_preferred_trigger='actual-current-source-v1'
        store.checkpoint_value(consumer.SCAN_CHECKPOINT)
        consumer._scan_checkpoint(store,{'schema':consumer.SCAN_CHECKPOINT,
            'known':['current','older'],'pending':['older']})
        plan,ordered=consumer._scan_plan(store,rows,set(),continuation=True)
        self.assertEqual([x['event_key']for x in ordered],['current','older'])
        plan['pending'].remove('current');consumer._scan_checkpoint(store,plan)
        _,ordered=consumer._scan_plan(store,rows,set(),continuation=True)
        self.assertEqual([x['event_key']for x in ordered],['older'])
        store.receipt_scan_preferred_trigger='actual-new-controller-decision-v2'
        _,ordered=consumer._scan_plan(store,rows,set(),continuation=True)
        self.assertEqual([x['event_key']for x in ordered],['current','older'])

    def test_self_handler_event_uses_real_committed_sdk_identity_without_inventing_metadata(self):
        fixed={'task_id':self.window,'title':'Original handler','cwd':str(self.root),'host_id':'local','project_id':'original-project'}
        sdk={'id':self.window,'title':fixed['title'],'cwd':str(self.root),'hostId':'local','kind':'codex','projectId':'original-project'}
        pin=self.write('actual-sdk.json',{'content':[{'type':'text',
            'text':json.dumps({'thread':sdk,'turns':[self.turn]})}]})
        ctx={'handling_actor':'original-handler','handling_owner':self.window,'intake':{'record_id':'committed-intake','actual_receiver_native':pin}}
        request={'sender_department':'original-handler','target_department':'original-handler'}
        canonical={'thread':{k:sdk[k]for k in ('id','title','cwd')},'turns':[self.turn]}
        before=json.dumps(canonical,sort_keys=True)
        proof=consumer._same_handler_receipt_sdk(self.root,request,ctx,fixed,canonical)
        self.assertEqual(proof['actual_receiver_native'],pin)
        self.assertFalse(proof['external_permission_issued'])
        self.assertEqual(json.dumps(canonical,sort_keys=True),before)
        for changed_request,changed_fixed,changed_canonical in (
            ({**request,'target_department':'different-handler'},fixed,canonical),
            (request,{**fixed,'task_id':'new-window'},canonical),
            (request,fixed,{'thread':{**canonical['thread'],'hostId':'another-host'}}),
            (request,fixed,{'thread':{**canonical['thread'],'kind':'chatgpt'}})):
            with self.subTest(request=changed_request,fixed=changed_fixed,current=changed_canonical):
                self.assertIsNone(consumer._same_handler_receipt_sdk(self.root,changed_request,ctx,changed_fixed,changed_canonical))
        self.write('actual-sdk.json',{'thread':{**sdk,'hostId':'tampered'},'turns':[self.turn]})
        with self.assertRaises(workflow.WorkflowError):consumer._same_handler_receipt_sdk(self.root,request,ctx,fixed,canonical)

    def test_legacy_reply_needs_exact_committed_message_hash_turn_and_phase(self):
        for change in ({'source_message_id': 'other'}, {'source_reply_sha256': '0' * 64},
                       {'source_turn_id': 'previous'}, {'event': 'prepared'},
                       {'result_source_phase': 'final'}, {'record_id': ''}):
            with self.subTest(change=change):
                self.committed_legacy_batch()
                self.queue.update(change)
                with self.assertRaises(workflow.WorkflowError): self.batch()

    def test_legacy_queue_does_not_release_partial_or_maintenance_or_changed_artifact(self):
        for mode in ('partial', 'maintenance', 'changed', 'incomplete'):
            with self.subTest(mode=mode):
                self.committed_legacy_batch()
                if mode == 'maintenance': self.final['text'] = 'Maintenance complete.'
                elif mode == 'changed': self.write('evidence.json', {'changed': True})
                else:
                    box = workflow.read_json(self.root / 'outbox.json')
                    if mode == 'partial': box['status'] = 'partial'
                    else: box['batch_complete'] = False
                    self.outbox = self.write('outbox.json', box)
                    self.identity['result_sha256'] = self.outbox['sha256']
                    self.queue.update(self.identity, outbox=self.outbox)
                    self.proof.update(result_identity=self.identity, outbox=self.outbox)
                with self.assertRaises(workflow.WorkflowError): self.batch()


if __name__ == '__main__':
    unittest.main()
