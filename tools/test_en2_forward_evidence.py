import copy,importlib.util,pathlib,unittest
from unittest.mock import patch
import workflow_control as w
import tools.test_en2_forward_preflight as forward
import professional_cms_execution as m;forward.m=m
class Evidence(forward.ForwardPreflight):
 def setUp(self):
  super().setUp();self.struct=self.validate(self.request());self.refs={'turn_id':'t','row_call':'row','key_call':'key','same_row_call':'same','preview_run_id':100};self.env=self.save('evidence-envelope.json',{'schema':'professional-cms-fresh-preflight/v1','task_id':m._EN2_FORWARD_TASK,'request':self.struct['pin'],'provider_sources':self.refs});self.proof={'external_origin_state':'VERIFIED_PROTECTED_PROVIDER_RECEIPTS','pub_turn_id':'t','row_call':'row','key_call':'key','same_row_call':'same','server_observed_at':'2026-01-01T00:00:00Z','preview_run_id':100,'preview_artifact_id':1,'preview_receipt_checked_at':'2026-01-01T00:00:01Z'};keys=('pub_turn_id','row_call','key_call','same_row_call','server_observed_at','preview_run_id','preview_artifact_id','preview_receipt_checked_at');self.event={'task_id':m._EN2_FORWARD_TASK,'event_id':'fixture-event','details':{'professional_cms_preflight':{'action_id':self.target['actionId'],'request':self.struct['pin'],'source_registration':self.registration,'source_event_id':m._EN2_SOURCE_EVENT,'preflight_only':True,'preflight_envelope':self.env,'provider_origin_evidence':{k:self.proof[k] for k in keys},'external_origin_state':'VERIFIED_PROTECTED_PROVIDER_RECEIPTS','actual_action_allowed':False}}};self.events=[self.event];self.reviewed={'current_owner_reviewed_release':True,'source_custody_registration':self.registration,'task':m._EN2_FORWARD_TASK,'scope':self.source['scope'],'authorization':{'path':'fixture-human'},'decision':{'path':'fixture-decision'}}
  self.real_verifier=m._en2_verify_provider_origins
  self.extra=[patch.object(w,'read_jsonl',side_effect=lambda *x,**y:copy.deepcopy(self.events)),patch.object(w,'validate_workflow_events',return_value=[]),patch.object(w,'_validate_receipt_chain',return_value=([],[])),patch('reviewed_web_release.current',side_effect=lambda *x:copy.deepcopy(self.reviewed)),patch.object(m,'_en2_verify_provider_origins',side_effect=lambda *x:copy.deepcopy(self.proof))]
  for x in self.extra:x.start()
  self.addCleanup(lambda:[x.stop() for x in reversed(self.extra)])
 def check(self):return m.en2_current_forward_evidence(self.root,self.snapshot)
 def test_self_printed_json_cannot_register_preflight(self):
  with patch.object(m,'_en2_verify_provider_origins',wraps=self.real_verifier):
   super().test_self_printed_json_cannot_register_preflight()
 def test_real_conditions_fixture_only_no_execution(self):
  x=self.check();self.assertFalse(x['actual_action_allowed']);self.assertFalse(x['issuer_binding_available']);self.assertEqual(x['preflight_event_id'],'fixture-event')
  with self.assertRaises(w.WorkflowError):m.execution_context(self.root,self.snapshot,{})
 def test_no_event_paused_or_wrong_task(self):
  self.events=[]
  with self.assertRaisesRegex(w.WorkflowError,'DATA_MISSING'):self.check()
  self.events=[self.event];self.snapshot['current_state']='paused'
  with self.assertRaises(w.WorkflowError):self.check()
  self.snapshot['current_state']='evidence_received';self.snapshot['task_id']='wrong'
  with self.assertRaises(w.WorkflowError):self.check()
 def test_tamper_custody_evidence_or_authority(self):
  for change in ('source','origin','receipt','authority'):
   with self.subTest(change=change):
    old=copy.deepcopy(self.event);rev=copy.deepcopy(self.reviewed)
    row=self.event['details']['professional_cms_preflight']
    if change=='source':row['source_event_id']='other'
    if change=='origin':row['external_origin_state']='NOT_VERIFIED'
    if change=='receipt':row['provider_origin_evidence']['preview_artifact_id']=999
    if change=='authority':self.reviewed['current_owner_reviewed_release']=False
    with self.assertRaises(w.WorkflowError):self.check()
    self.event.clear();self.event.update(old);self.reviewed=rev
 def test_corrupt_history_or_current_provider_failure(self):
  with patch.object(w,'validate_workflow_events',return_value=['bad']):
   with self.assertRaises(w.WorkflowError):self.check()
  with patch.object(m,'_en2_verify_provider_origins',side_effect=w.WorkflowError('stale or unknown')):
   with self.assertRaisesRegex(w.WorkflowError,'stale or unknown'):self.check()
 def test_issuer_phase_reuses_target_but_rechecks_age_and_refreshes_at_next_phase(self):
  import datetime as dt
  import en2_forward_issuer as issuer
  now=dt.datetime.now(dt.timezone.utc)
  evidence={'preflight_request':self.struct['pin'],'preview_receipt_checked_at':now.isoformat(),
            'record_id':self.target['id']}
  with patch.object(issuer,'_read_target',return_value=evidence) as provider:
   with issuer.issuer_request_reads():
    value=issuer.target(self.root);value['record_id']='changed local copy'
    self.assertEqual(issuer.target(self.root),evidence)
    provider.assert_called_once()
    with patch.object(issuer,'_fresh_inputs',side_effect=w.WorkflowError('expired')):
     with self.assertRaisesRegex(w.WorkflowError,'expired'):issuer.target(self.root)
   with issuer.issuer_request_reads():
    self.assertEqual(issuer.target(self.root),evidence)
   self.assertEqual(provider.call_count,2)
if __name__=='__main__':unittest.main(verbosity=2)
