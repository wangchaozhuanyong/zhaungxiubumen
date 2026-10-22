"""Affected direct-takeover boundaries; isolated fixtures, no provider calls."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import direct_system_repair as direct
import source_patch_transaction as source
import workflow_control as w
import export_department_system as export
import safe_cleanup
import result_coordination as coordination


class DirectCloseTests(unittest.TestCase):
    def setUp(self):
        base=Path(__file__).resolve().parents[1]/'.test-tmp'
        base.mkdir(exist_ok=True)
        self.tmp=tempfile.TemporaryDirectory(dir=base)
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        for directory in ('tools','working','data','logs','backups'):
            (self.root/directory).mkdir()
        self.binding={'task_id':'test-fixed-HQ','cwd':str(self.root),'title':'test-HQ'}
        self.write('data/department-registry.json',{'departments':[{'id':'operations','chat_binding':self.binding}]})
        text='PLEASE IMPLEMENT THIS PLAN '+direct.TASK+' 直接完成 不再交开发部门返工 真实接续试点 不扩大日常权限'
        self.native={'thread':{'id':self.binding['task_id'],'cwd':str(self.root),'title':'test-HQ'},
                     'turns':[{'id':'test-turn','status':'inProgress','error':None,
                               'items':[{'type':'userMessage','id':'test-human','content':[{'type':'text','text':text}]}]}]}
        self.write('logs/human.json',self.native)
        self.auth={'native':w.file_digest(self.root,'logs/human.json'),'turn_id':'test-turn',
                   'message_id':'test-human','text_sha256':hashlib.sha256(text.encode()).hexdigest()}

    def write(self,path,value):
        w.atomic_write_json(self.root/path,value)

    def test_actual_human_identity_and_text_are_read(self):
        self.assertEqual(direct._human(self.root,self.auth)['message_id'],'test-human')

    def test_wrong_task_turn_message_hash_and_identity_rejected(self):
        for change in ({'turn_id':'wrong'},{'message_id':'wrong'},{'text_sha256':'a'*64}):
            with self.subTest(change=change),self.assertRaises(w.WorkflowError):
                direct._human(self.root,{**self.auth,**change})
        broken=copy.deepcopy(self.native);broken['thread']['cwd']='/other-project'
        self.write('logs/other.json',broken)
        with self.assertRaises(w.WorkflowError):
            direct._human(self.root,{**self.auth,'native':w.file_digest(self.root,'logs/other.json')})

    def test_tampered_native_bytes_rejected(self):
        self.write('logs/human.json',{})
        with self.assertRaises(w.WorkflowError):direct._human(self.root,self.auth)

    def adopted(self,round_number):
        name='tools/control.py'
        if not (self.root/name).exists():(self.root/name).write_text('VALUE=0\n')
        (self.root/'working/control.py').write_text('VALUE='+str(round_number)+'\n')
        prepared=source.prepare(self.root,[{'path':name,'before':source.fingerprint(self.root,name),'candidate':'working/control.py'}])
        result=source.apply(self.root,prepared,'backups/layer'+str(round_number),task_id=direct.TASK)
        path='logs/report'+str(round_number)+'.json';self.write(path,result)
        return w.file_digest(self.root,path)

    def test_contiguous_actual_adoption_layers(self):
        first=self.adopted(1);second=self.adopted(2)
        self.assertEqual(direct.source_chain(self.root,[first,second],direct.TASK)['files'],1)
        with self.assertRaises(w.WorkflowError):direct.source_chain(self.root,[first],direct.TASK)

    def test_source_and_rollback_drift_fail_closed(self):
        first=self.adopted(1)
        (self.root/'backups/layer1/tools/control.py').write_text('lost backup\n')
        with self.assertRaises(w.WorkflowError):direct.source_chain(self.root,[first],direct.TASK)

    def test_other_task_and_missing_admission_have_no_override(self):
        self.write('data/task-contract.json',{'goal_delivery_runtime':{}})
        self.assertIsNone(direct.context(self.root,'another-task'))
        self.assertIsNone(direct.context(self.root,direct.TASK))
        self.assertEqual(direct.owners(self.root),{})

    def test_internal_adoption_does_not_close_missing_real_pilot(self):
        active={'document':{'source_adoptions':[]},'pin':{},'adoption':{'sources':[]}}
        requirements=[{'requirement_id':'source','requirement_type':'source_adoption'},
                      {'requirement_id':'pilot','requirement_type':'internal_pilot'}]
        with mock.patch('goal_delivery_runtime._completion_contract',return_value={'state':'declared','completion_kind':'internal_delivery','requirements':requirements}):
            view=direct.completion_view(self.root,{'task_id':direct.TASK},active)
        self.assertTrue(view['source_adopted']);self.assertFalse(view['control_scope_completed'])
        self.assertFalse(view['business_goal_closed'])

    def test_public_export_removes_actual_direct_authority(self):
        value={'goal_delivery_runtime':{'model':'goal_delivery_assistant_v1',
               'direct_execution_takeovers':{'private':{'path':'logs/human.json'}},
               'direct_message_packets':{'private':{'path':'logs/payload.json'}}}}
        safe=export.public_policy(value)['goal_delivery_runtime']
        self.assertNotIn('direct_execution_takeovers',safe);self.assertNotIn('direct_message_packets',safe)

    def test_ordinary_message_does_not_use_direct_exception(self):
        self.assertIsNone(direct.message_precheck(self.root,{'task_id':'ordinary','action_id':'direct-system-test'}))
        self.assertIsNone(direct.message_precheck(self.root,{'task_id':direct.TASK,'action_id':'ordinary'}))

    def test_ordinary_result_has_no_direct_intake(self):
        self.assertIsNone(direct.received_original_knowledge(self.root,{'task_id':'unrelated'}))

    def test_health_template_contains_only_registered_identity_and_no_business(self):
        text=direct.health_message({'name':'test-role','chat_binding':{'task_id':'test-fixed','project_id':'test-project','cwd':str(self.root)}})
        self.assertIn('不执行业务、不改文件、不写代码、不修改账号',text)
        self.assertIn('test-fixed',text)

    def test_empty_cleanup_plan_does_not_replay_all_historic_references(self):
        with mock.patch.object(safe_cleanup,'reference_state',side_effect=AssertionError('unnecessary history scan')):
            result=safe_cleanup.scan(self.root,{'trusted_use_observations':True,'files':[]})
        self.assertEqual(result['items'],[]);self.assertFalse(result['deletion_executed'])

    def test_unrelated_heartbeat_and_ack_do_not_finish_original_pilot(self):
        turn={'status':'completed','error':None}
        for text in ['<heartbeat>cleanup complete</heartbeat>','another-task completed','ACK']:
            self.assertFalse(coordination._pilot_final_matches(turn,{'phase':'final_answer','text':text}))
        self.assertTrue(coordination._pilot_final_matches(turn,{'phase':'final_answer','text':coordination.ORIGINAL_A3_CONCLUSION['task_id']+' partial; named dependency retained'}))
        self.assertFalse(coordination._pilot_final_matches({'status':'inProgress'}, {'phase':'final_answer','text':coordination.ORIGINAL_A3_CONCLUSION['task_id']}))

    def test_no_current_assignment_is_readonly_and_does_not_create_one(self):
        self.assertIsNone(coordination.current_assignment_for_role(self.root,'operations'))
        self.assertFalse((self.root/'data/department-current-assignment.json').exists())

    def test_public_privacy_filter_works_next_to_chinese_words(self):
        native = '01a13652' + '-0dda-74e3-b5bd-2d10eaed502c'
        message = 'msg_' + 'a' * 40
        account = '814' + '-251-0200'
        text = '中文账户' + account + '以及窗口' + native + '及消息' + message
        public = export.public_text(text, self.root)
        for private in (account, native, message):
            self.assertNotIn(private, public)

    def test_closed_history_does_not_claim_current_source_after_later_changes(self):
        pin=self.adopted(1);(self.root/'tools/control.py').write_text('VALUE=2\n')
        history=direct.source_chain(self.root,[pin],direct.TASK,verify_live=False)
        self.assertTrue(history['historical_adoption_proven']);self.assertFalse(history['source_readback_passed'])
        with self.assertRaises(w.WorkflowError):direct.source_chain(self.root,[pin],direct.TASK)

    def test_one_direct_repair_error_does_not_abort_other_task_owners(self):
        with mock.patch.object(direct,'_read_context',side_effect=w.WorkflowError('one old task failed')):
            self.assertEqual(direct.owners(self.root),{})

    def test_successor_association_does_not_apply_to_other_task_or_new_version(self):
        self.assertIsNone(direct.existing_result_resolution(self.root,{'task_id':'unrelated'}))
        self.assertIsNone(direct.existing_result_resolution(self.root,{'task_id':coordination.ORIGINAL_A3_CONCLUSION['task_id'],'candidate_version':'new-unreviewed'}))



class HistoricalHQReadTests(unittest.TestCase):
    """Real isolated takeover/events/source CAS and trusted rotation, no provider calls."""
    def setUp(self):
        import test_department_rotation as rotations
        self.rotation = rotations.RotationTests('runTest')
        self.rotation.setUp(); self.addCleanup(self.rotation.doCleanups)
        self.root = self.rotation.root
        self.write = self.rotation.write
        binding = w.department_registry(self.root)['operations']['chat_binding']
        text = 'PLEASE IMPLEMENT THIS PLAN '+direct.TASK+' 直接完成 不再交开发部门返工 真实接续试点 不扩大日常权限'
        self.native = {'thread': {'id': binding['task_id'], 'cwd': binding['cwd'], 'title': binding['title']},
            'turns': [{'id': 'human-turn', 'status': 'completed', 'error': None,
                'items': [{'type': 'userMessage', 'id': 'human-message', 'content': [{'type': 'text', 'text': text}]}]}]}
        self.auth = {'native': self.write('reports/original-human.json', self.native),
            'turn_id': 'human-turn', 'message_id': 'human-message', 'text_sha256': hashlib.sha256(text.encode()).hexdigest()}
        (self.root/'tools').mkdir(exist_ok=True)
        (self.root/'working').mkdir(exist_ok=True)
        self.report = DirectCloseTests.adopted(self, 1)
        registry=w.read_json(self.root/'data/department-registry.json')
        sys_role=copy.deepcopy(next(row for row in registry['departments'] if row['id']=='content-organic-website'))
        sys_role['id']='system-development';sys_role['chat_binding']['task_id']='fixed-system-development'
        registry['departments'].append(sys_role);self.write('data/department-registry.json',registry)
        t = self.rotation.base.t; t.task_id = direct.TASK
        t.initialize(primary_owner='system-development', producer_departments=['system-development'], authorized_scope=[direct.SCOPE], required_execution_actions=[], human_authorization={**t.make_goal()['human_authorization'],'executor':'system-development'})
        document = {'model': direct.MODEL, 'task_id': direct.TASK, 'scope': direct.SCOPE,
            'executor': 'operations', 'external_permission_issued': False, 'business_permissions_changed': False,
            'human_authorization': self.auth, 'source_adoptions': [self.report]}
        self.takeover = self.write('reports/takeover.json', document)
        config = w.read_json(self.root/'data/task-contract.json')
        config['goal_delivery_runtime']['direct_execution_takeovers'] = {direct.TASK: self.takeover}
        self.write('data/task-contract.json', config)
        w.append_workflow_event(self.root, direct.TASK, t.snapshot()['current_state'], {'owner_direct_execution': self.takeover})
        w.append_workflow_event(self.root, direct.TASK, 'closed', {'owner_direct_completion': self.takeover, 'closed_scope_only': True})
        snapshot = w.read_json(w.snapshot_path(self.root,direct.TASK));snapshot['current_state']='closed'
        self.write(str(w.snapshot_path(self.root,direct.TASK).relative_to(self.root)), snapshot)
        self.rotation.prepare(('operations',)); self.rotation.apply()
        self.assertEqual(w.validate_workflow_events(self.root,direct.TASK), [])

    def test_exact_closed_historical_source_and_owner_are_read_without_writes(self):
        before = {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        read = direct._read_context(self.root,direct.TASK)
        self.assertEqual(read['executor'],'operations')
        self.assertEqual(read['document']['human_authorization'],self.auth)
        self.assertEqual(direct.owners(self.root),{direct.TASK:'operations'})
        self.assertEqual({p:p.read_bytes() for p in self.root.rglob('*') if p.is_file()},before)

    def test_current_execution_context_still_rejects_old_human_after_read(self):
        direct._read_context(self.root,direct.TASK)
        with self.assertRaisesRegex(w.WorkflowError,'actual fixed headquarters human source'):
            direct.context(self.root,direct.TASK)
        with self.assertRaises(w.WorkflowError): direct._human(self.root,self.auth)

    def test_historical_source_cannot_add_source_adoption_or_completion_or_messages(self):
        before = (self.root/w.WORKFLOW_EVENTS).read_bytes()
        for callback in (lambda:direct.record_source_adoption(self.root,self.report,'forbidden-after-closed'),
                         lambda:direct.record_completion(self.root,{},'forbidden-after-closed'),
                         lambda:direct.message_precheck(self.root,{'task_id':direct.TASK,'action_id':'direct-system-new'})):
            with self.subTest(callback=callback), self.assertRaises(w.WorkflowError): callback()
        self.assertEqual((self.root/w.WORKFLOW_EVENTS).read_bytes(),before)

    def test_reopened_snapshot_does_not_gain_historical_admission(self):
        path = w.snapshot_path(self.root,direct.TASK);snapshot=w.read_json(path);snapshot['current_state']='planned'
        self.write(str(path.relative_to(self.root)),snapshot)
        with self.assertRaisesRegex(w.WorkflowError,'committed closed repair'):direct._read_context(self.root,direct.TASK)

    def test_no_closed_event_cannot_use_historical_human(self):
        events=[e for e in w.read_jsonl(self.root/w.WORKFLOW_EVENTS) if 'owner_direct_completion' not in e.get('details',{})]
        (self.root/w.WORKFLOW_EVENTS).write_text(''.join(json.dumps(e)+'\n' for e in events))
        with self.assertRaises(w.WorkflowError):direct._read_context(self.root,direct.TASK)

    def test_other_task_has_no_historical_context(self):
        self.assertIsNone(direct._read_context(self.root,'unrelated'))

    def test_native_pin_message_turn_and_text_tampering_still_reject(self):
        for change in ({'turn_id':'forged'},{'message_id':'forged'},{'text_sha256':'a'*64}):
            with self.subTest(change=change), self.assertRaises(w.WorkflowError):
                direct._closed_human(self.root,{**self.auth,**change})
        self.write('reports/original-human.json',{})
        with self.assertRaises(w.WorkflowError):direct._read_context(self.root,direct.TASK)

    def test_repinning_cross_role_or_project_native_still_rejects(self):
        for key,value in (('id','fixed-operations-assistant-2'),('cwd','/other-project'),('title','other role'),('projectId','other-project')):
            native=copy.deepcopy(self.native);native['thread'][key]=value
            pin=self.write('reports/forged-human.json',native)
            with self.subTest(key=key), self.assertRaises(w.WorkflowError):
                direct._closed_human(self.root,{**self.auth,'native':pin})

    def test_tampered_rotation_or_current_binding_still_rejects(self):
        registry=w.read_json(self.root/'data/department-registry.json')
        pin=registry['window_rotation_records'][0]
        record=w.read_json(self.root/pin['path']);record['role']='operations-assistant-2'
        self.write(pin['path'],record)
        with self.assertRaises(w.WorkflowError):direct._read_context(self.root,direct.TASK)

    def test_untrusted_old_hq_without_current_same_role_mapping_rejects(self):
        registry=w.read_json(self.root/'data/department-registry.json')
        registry['window_rotation_records']=[];self.write('data/department-registry.json',registry)
        with self.assertRaises(w.WorkflowError):direct._read_context(self.root,direct.TASK)

    def test_current_project_binding_drift_still_rejects(self):
        registry=w.read_json(self.root/'data/department-registry.json')
        role=next(row for row in registry['departments'] if row['id']=='operations')
        role['chat_binding']['project_id']='other-project';self.write('data/department-registry.json',registry)
        with self.assertRaises(w.WorkflowError):direct._read_context(self.root,direct.TASK)

    def test_historical_validation_scope_forbids_policy_and_ledger_writes(self):
        with direct._closed_read_validation(self.root):
            with self.assertRaisesRegex(w.WorkflowError,'read-only'):
                w.atomic_write_json(self.root/'reports/forbidden.json',{'forged':True})
            with self.assertRaisesRegex(w.WorkflowError,'read-only'):
                w.append_workflow_event(self.root,direct.TASK,'closed',{'forged':True})
            with self.assertRaisesRegex(w.WorkflowError,'read-only'):
                w.policy_check(self.root,department='operations',task_id=direct.TASK,action_id='forbidden',action_class='site_publish',scope=direct.SCOPE)
        self.assertFalse((self.root/'reports/forbidden.json').exists())
        with self.assertRaises(w.WorkflowError):direct._human(self.root,self.auth)

    def test_closed_event_chain_tampering_and_duplicate_closure_reject(self):
        path=self.root/w.WORKFLOW_EVENTS;raw=path.read_bytes();events=w.read_jsonl(path)
        events[-1]['details']['forged']=True
        path.write_text(''.join(json.dumps(e)+'\n' for e in events))
        with self.assertRaises(w.WorkflowError):direct._read_context(self.root,direct.TASK)
        path.write_bytes(raw)
        w.append_workflow_event(self.root,direct.TASK,'closed',{'owner_direct_completion':self.takeover,'closed_scope_only':True})
        with self.assertRaisesRegex(w.WorkflowError,'one exact committed closed repair'):
            direct._read_context(self.root,direct.TASK)

    def test_takeover_event_pin_is_not_replaceable(self):
        config=w.read_json(self.root/'data/task-contract.json')
        doc=w.read_json(self.root/self.takeover['path']);doc['human_authorization']['text_sha256']='a'*64
        config['goal_delivery_runtime']['direct_execution_takeovers'][direct.TASK]=self.write('reports/replacement.json',doc)
        self.write('data/task-contract.json',config)
        with self.assertRaisesRegex(w.WorkflowError,'committed direct takeover'):direct._read_context(self.root,direct.TASK)

if __name__=='__main__':unittest.main()
