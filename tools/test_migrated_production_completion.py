import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import department_autonomy as a
import goal_delivery_runtime as g
import workflow_control as w


class MigratedProductionCompletionTests(unittest.TestCase):
    def setUp(self):
        self.action={'action_id':'original-save','action_class':'cms_write','scope':'original:row',
                     'department':'publishing'}
        self.goal={'objective':'original','completion_criteria':['Actual Save and public readback'],
                   'primary_owner':'publishing','producer_departments':['publishing'],
                   'authorized_scope':['original:row'],'human_authorization':'original.json',
                   'required_execution_actions':[self.action], 'completion_kind':'production_release',
                   'completion_requirements':[{'requirement_id':'saved','criterion_index':0,
                     'requirement_type':'execution_postcheck','subject':{'mode':'latest_exact_accepted_result',
                     'producer_department':'publishing'},**self.action}]}
        self.frozen=copy.deepcopy(self.goal)
        self.snapshot={'task_id':'original-goal','current_state':'evidence_received',
                       'goal_contract':{'path':'original-contract.json'},'goal_delivery':self.goal}

    def eligible(self):
        with patch.object(a,'effective_mode',return_value=True), \
                patch.object(a,'professional',return_value=True), \
                patch.object(a,'document',return_value=self.frozen):
            return a.migrated_production_completion(Path('/fixture'),self.snapshot)

    def test_preserves_frozen_release_mapping_and_original_professional(self):
        self.assertTrue(self.eligible())
        self.assertEqual(a.requirement_rows(self.goal)[0]['producer_department'],'publishing')
        self.assertEqual(self.goal,self.frozen)

    def test_changed_frozen_standard_owner_action_or_authority_is_rejected(self):
        for key,value in (('completion_criteria',['less']),('primary_owner','operations'),
                          ('human_authorization','new.json'),('required_execution_actions',[])):
            with self.subTest(key=key):
                self.snapshot['goal_delivery']=copy.deepcopy(self.frozen)
                self.snapshot['goal_delivery'][key]=value
                if key=='required_execution_actions': self.assertFalse(self.eligible())
                else:
                    with self.assertRaises(w.WorkflowError):self.eligible()

    def test_current_mode_is_required_and_nonproduction_keeps_original_reader(self):
        with patch.object(a,'effective_mode',return_value=False):
            self.assertFalse(a.migrated_production_completion(Path('/fixture'),self.snapshot))
        self.goal['completion_kind']='internal_delivery'
        self.assertFalse(self.eligible())

    def test_dispatches_only_to_existing_actual_effect_recorder(self):
        with patch.object(g,'restore_goal',return_value=self.snapshot), \
                patch.object(w,'read_json',return_value=self.snapshot), \
                patch.object(a,'migrated_production_completion',return_value=True), \
                patch.object(a,'record_completion',return_value={'result':'actual-recorder'}) as record:
            result=g.record_completion_evidence(Path('/fixture'),'original-goal','proof.json','publishing','saved')
        self.assertEqual(result,{'result':'actual-recorder'})
        record.assert_called_once_with(Path('/fixture'),'original-goal','proof.json','publishing','saved')

    def test_existing_recorder_does_not_allow_HQ_to_impersonate_professional(self):
        area=Path(__file__).resolve().parents[1]/'.test-tmp';area.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=area) as directory:
            root=Path(directory);(root/'proof.json').write_text('{}')
            with patch.object(g,'restore_goal',return_value=self.snapshot), \
                    patch.object(w,'read_json',return_value=self.snapshot), \
                    patch.object(a,'effective_mode',return_value=True):
                with self.assertRaisesRegex(w.WorkflowError,'original professional'):
                    a.record_completion(root,'original-goal','proof.json','operations','saved')
            self.assertFalse((root/w.WORKFLOW_EVENTS).exists())

    def test_status_reports_proven_scope_without_reactivating_old_QA(self):
        self.goal['responsible_assistant']='operations-assistant-2'
        with patch.object(g,'restore_goal',return_value=self.snapshot), \
                patch.object(a,'migrated_local_completion',return_value=False), \
                patch.object(a,'migrated_production_completion',return_value=True), \
                patch.object(a,'completion',return_value={'state':'PROVEN'}), \
                patch.object(w,'read_jsonl',side_effect=AssertionError('old QA must not run')):
            result=a.legacy_status(Path('/fixture'),self.snapshot)
        self.assertEqual(result['state'],'completed_scope')
        self.assertIsNone(result['responsible_assistant'])
        self.assertEqual(result['historical_responsible_assistant'],'operations-assistant-2')
        self.assertFalse(result['business_goal_closed'])


if __name__=='__main__':unittest.main()
