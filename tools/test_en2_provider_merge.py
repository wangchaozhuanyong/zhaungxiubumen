import copy,datetime as dt,importlib.util,pathlib,unittest
from unittest.mock import patch
import tools.test_en2_forward_preflight as base
import workflow_control as w
import professional_cms_execution as m;base.m=m
class Merge(base.ForwardPreflight):
 def setUp(self):
  super().setUp();self.refs={'turn_id':'fixture-turn','row_call':'row','key_call':'key','same_row_call':'same','preview_run_id':123}
 def values(self):
  req=self.request();x=self.validate(req);facts=json_read(self.root/req['facts']['path']);at=w._parse_observed_at(facts['observed_at']);now=dt.datetime.now(dt.timezone.utc)
  sql={'row_call_origin':'VERIFIED_OFFICIAL_RPC','original_key_call_origin':'VERIFIED_OFFICIAL_RPC','same_row_call_origin':'VERIFIED_OFFICIAL_RPC','same_row_effect':'NO_BLOCKING_ROW_OBSERVED','original_key_count':0,'fresh_within_300_seconds':True,'task_id':req['task_id'],'record_id':req['object_ids'][0],'raw_updated_at':req['expected_updated_at'],'version':req['expected_version'],'row_sha256':w.sha256_value(self.row),'server_observed_at':facts['observed_at'],'same_row_completed_at_ms':int(at.timestamp()*1000)}
  preview={'preview_origin':'VERIFIED_GITHUB_PROVIDER_READ','run_id':123,'artifact_id':45,'task_id':req['task_id'],'action_id':req['action_id'],'candidate_version':req['candidate_version'],'physical_scope':req['physical_scope'],'expected_updated_at':req['expected_updated_at'],'desired_fields_sha256':w.sha256_value(req['desired']),'actual_action_allowed':False,'receipt_checked_at':now.isoformat()}
  return x,sql,preview
 def verify(self,x,sql,preview,refs=None):
  with patch('en2_supabase_origin.read_actual',return_value=sql),patch('en2_preview_origin.read_actual',return_value=preview):return m._en2_verify_provider_origins(self.root,x,self.refs if refs is None else refs)
 def test_status_lists_required_origin_locators_without_permission(self):
  with patch('goal_delivery_runtime.restore_goal',return_value=self.snapshot):out=m.status(self.root,m._EN2_FORWARD_TASK)
  self.assertTrue(out['provider_origin_merge_implemented']);self.assertFalse(out['provider_origin_merge_live_preview_proven']);self.assertEqual(out['provider_sources_fields'],['turn_id','row_call','key_call','same_row_call','preview_run_id']);self.assertFalse(out['actual_action_allowed'])
 def test_verified_both_sources_is_still_not_permission(self):
  x,sql,preview=self.values();out=self.verify(x,sql,preview);self.assertEqual(out['external_origin_state'],'VERIFIED_PROTECTED_PROVIDER_RECEIPTS');self.assertFalse(out['actual_action_allowed'])
 def test_queries_after_preview_must_still_bind_exact_baseline(self):
  x,sql,preview=self.values()
  observed=w._parse_observed_at(sql['server_observed_at'])
  preview['receipt_checked_at']=(observed-dt.timedelta(seconds=1)).isoformat()
  self.assertEqual(self.verify(x,sql,preview)['external_origin_state'],'VERIFIED_PROTECTED_PROVIDER_RECEIPTS')
  sql['raw_updated_at']='changed'
  with self.assertRaises(w.WorkflowError):self.verify(x,sql,preview)
 def test_normal_record_verifies_both_providers_and_is_idempotent(self):
  import goal_delivery_runtime as g
  x,sql,preview=self.values();envelope=self.save('provider-envelope.json',{'schema':'professional-cms-fresh-preflight/v1','task_id':m._EN2_FORWARD_TASK,'request':x['pin'],'provider_sources':self.refs});events=[]
  def append(root,task,state,details):events.append({'task_id':task,'details':copy.deepcopy(details)})
  with patch.object(g,'restore_goal',return_value=self.snapshot),patch.object(w,'read_jsonl',side_effect=lambda *args,**kwargs:copy.deepcopy(events)),patch.object(w,'append_workflow_event',side_effect=append),patch('en2_supabase_origin.read_actual',return_value=sql) as rsql,patch('en2_preview_origin.read_actual',return_value=preview) as rpreview:
   result=m.record_preflight(self.root,m._EN2_FORWARD_TASK,envelope['path']);self.assertEqual(result['result'],'recorded');self.assertFalse(result['actual_action_allowed']);self.assertEqual(len(events),1);self.assertEqual(events[0]['details']['professional_cms_preflight']['preflight_envelope'],envelope);self.assertEqual(events[0]['details']['professional_cms_preflight']['provider_origin_evidence']['preview_artifact_id'],45);rsql.assert_called_once();rpreview.assert_called_once()
   result=m.record_preflight(self.root,m._EN2_FORWARD_TASK,envelope['path']);self.assertEqual(result['result'],'duplicate_ignored');self.assertFalse(result['replay_authorized']);self.assertEqual(len(events),1)

 def test_wrong_sql_origin_row_task_cas_effect_rejected(self):
  for key,val in [('row_call_origin','NOT_VERIFIED'),('same_row_call_origin','DATA_MISSING'),('same_row_effect','UNKNOWN'),('original_key_count',1),('record_id','other'),('task_id','other'),('raw_updated_at','other'),('row_sha256','0'*64),('version',2),('fresh_within_300_seconds',False)]:
   with self.subTest(key=key):
    x,sql,p=self.values();sql[key]=val
    with self.assertRaises(w.WorkflowError):self.verify(x,sql,p)
 def test_preview_source_and_chronology_rejected(self):
  for key,val in [('preview_origin','NOT_VERIFIED'),('run_id',124),('action_id','other'),('candidate_version','other'),('physical_scope','other'),('desired_fields_sha256','0'*64),('actual_action_allowed',True),('receipt_checked_at',(dt.datetime.now(dt.timezone.utc)-dt.timedelta(seconds=301)).isoformat())]:
   with self.subTest(key=key):
    x,sql,p=self.values();p[key]=val
    with self.assertRaises(w.WorkflowError):self.verify(x,sql,p)
 def test_missing_refs_or_self_assertion_cannot_grant(self):
  x,sql,p=self.values()
  with self.assertRaisesRegex(w.WorkflowError,'DATA_MISSING'):self.verify(x,sql,p,{})
  refs={**self.refs,'external_origin_state':'VERIFIED_PROTECTED_PROVIDER_RECEIPTS'}
  with self.assertRaises(w.WorkflowError):self.verify(x,sql,p,refs)

def json_read(p):
 import json
 return json.loads(p.read_text())
if __name__=='__main__':unittest.main(verbosity=2)
