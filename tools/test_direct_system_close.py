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
        native='example-native-96718e10d87c30cc';message='msg_'+'a'*40
        text='中文账户example-ads-account以及窗口'+native+'及消息'+message
        public=export.public_text(text,self.root)
        self.assertNotIn('example-ads-account',public);self.assertNotIn(native,public);self.assertNotIn(message,public)

    def test_closed_history_does_not_claim_current_source_after_later_changes(self):
        pin=self.adopted(1);(self.root/'tools/control.py').write_text('VALUE=2\n')
        history=direct.source_chain(self.root,[pin],direct.TASK,verify_live=False)
        self.assertTrue(history['historical_adoption_proven']);self.assertFalse(history['source_readback_passed'])
        with self.assertRaises(w.WorkflowError):direct.source_chain(self.root,[pin],direct.TASK)

    def test_one_direct_repair_error_does_not_abort_other_task_owners(self):
        with mock.patch.object(direct,'context',side_effect=w.WorkflowError('one old task failed')):
            self.assertEqual(direct.owners(self.root),{})

    def test_successor_association_does_not_apply_to_other_task_or_new_version(self):
        self.assertIsNone(direct.existing_result_resolution(self.root,{'task_id':'unrelated'}))
        self.assertIsNone(direct.existing_result_resolution(self.root,{'task_id':coordination.ORIGINAL_A3_CONCLUSION['task_id'],'candidate_version':'new-unreviewed'}))

if __name__=='__main__':unittest.main()
