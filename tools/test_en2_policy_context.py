import copy,datetime as dt,importlib.util,json,pathlib,sys,unittest
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
import workflow_control as w
import department_autonomy as a
import professional_cms_execution as m
import tools.test_en2_forward_preflight as base
base.m=m;base.a=a
class Context(base.ForwardPreflight):
 def setUp(self):
  super().setUp();at=dt.datetime.now(dt.timezone.utc).isoformat();self.req=self.request(lambda r:r.update(observed_at=at));facts=json.loads((self.root/self.req['facts']['path']).read_text());facts['observed_at']=at;self.native['facts']['observed_at']=at;self.req['facts']=self.save('facts.json',facts);self.pin=self.save('request-context.json',self.req);self.auth=self.save('human.json',{'fixture':'not real authorization'});self.snapshot['goal_delivery']={'primary_owner':'publishing','producer_departments':['publishing'],'authorization_pin':self.auth,'delivery_model':'historic'};self.evidence={'request':self.pin,'action_id':self.req['action_id'],'human_source':self.auth,'HQ_decision':self.auth,'preflight_event_id':'fixture','source_event_id':m._EN2_SOURCE_EVENT};self.requested={'task_id':m._EN2_FORWARD_TASK,'action_id':self.req['action_id'],'action_class':'cms_write','scope':self.req['business_scope'],'department':'publishing','source_project_id':a.PROJECT,'payload_sha256':self.pin['sha256'],'consume_approval':False};self.reads=[];self.patches2=[patch.object(a,'effective_mode',return_value=True),patch.object(m,'en2_current_forward_evidence',side_effect=self.actual_evidence)]
  for z in self.patches2:z.start()
  self.addCleanup(lambda:[z.stop() for z in reversed(self.patches2)])
 def actual_evidence(self,*args):self.reads.append('provider recheck');return copy.deepcopy(self.evidence)
 def test_exact_context_still_no_permit(self):
  x=m.execution_context(self.root,self.snapshot,self.requested);self.assertEqual(x['pin'],self.pin);self.assertFalse(x['external_permission_issued']);self.assertNotIn('rollback',x['preflight']);self.assertEqual(x['preflight']['payload_sha256'],w.sha256_value(self.req['desired']))
 def test_wrong_identity_source_and_scope_rejected(self):
  for key,value in [('task_id','other'),('department','operations-assistant-2'),('action_id','other'),('scope',self.req['physical_scope']),('source_project_id','other'),('payload_sha256','0'*64),('target_department','other'),('execution_instance',{})]:
   with self.subTest(key=key),self.assertRaises(w.WorkflowError):m.execution_context(self.root,self.snapshot,{**self.requested,key:value})
 def test_retired_or_disabled_publisher_rejected(self):
  with patch.object(a,'professional',return_value=False):
   with self.assertRaises(w.WorkflowError):m.execution_context(self.root,self.snapshot,self.requested)
 def test_pause_source_only_and_expiry_rejected(self):
  self.snapshot['current_state']='paused'
  with self.assertRaises(w.WorkflowError):m.execution_context(self.root,self.snapshot,self.requested)
  self.snapshot['current_state']='evidence_received'
  with patch.object(m,'en2_current_forward_evidence',side_effect=w.WorkflowError('DATA_MISSING')):
   with self.assertRaisesRegex(w.WorkflowError,'DATA_MISSING'):m.execution_context(self.root,self.snapshot,self.requested)
  old=(dt.datetime.now(dt.timezone.utc)-dt.timedelta(seconds=301)).isoformat();req={**self.req,'observed_at':old};self.pin=self.save('request-expired.json',req);self.evidence['request']=self.pin;self.requested['payload_sha256']=self.pin['sha256']
  with self.assertRaises(w.WorkflowError):m.execution_context(self.root,self.snapshot,self.requested)
 def policy_setup(self):
  import professional_web_execution as web, tools.shop_office_web_execution as shop,professional_ads_execution as ads
  snap=w.snapshot_path(self.root,m._EN2_FORWARD_TASK);snap.parent.mkdir(parents=True,exist_ok=True);snap.write_text(json.dumps(self.snapshot));self.rows=[]
  def append(path,row):self.rows.append(copy.deepcopy(row))
  def read(path,*,where=None):
   is_policy=path==self.root/w.POLICY_DECISIONS
   return copy.deepcopy([r for r in self.rows if ('status' in r)==is_policy and (where is None or w._jsonl_matches(r,where))])
  pp=[patch.object(web,'applies',return_value=False),patch.object(shop,'applies',return_value=False),patch.object(ads,'match',return_value=None),patch.object(w,'_chat_binding_healthy',return_value=True),patch.object(w,'read_jsonl',side_effect=read),patch.object(w,'append_jsonl_locked',side_effect=append)]
  for p in pp:p.start()
  self.addCleanup(lambda:[p.stop()for p in reversed(pp)])
 def test_normal_execution_preflight_internal_tuple(self):
  import goal_delivery_runtime as g
  with patch.object(g,'enabled',return_value=True):
   x=g.execution_preflight(self.root,self.snapshot,self.req['action_id'],'cms_write',self.req['scope'],'publishing')
  self.assertEqual(x['request'],self.pin);self.assertEqual(x['payload_sha256'],w.sha256_value(self.req['desired']))
 def test_policy_missing_request_hash_fails(self):
  self.policy_setup();req={k:v for k,v in self.requested.items() if k!='payload_sha256'}
  with self.assertRaises(w.WorkflowError):a.policy(self.root,req)
 def test_normal_legacy_policy_only_preview_no_grant(self):
  self.policy_setup();result,_=a.policy(self.root,self.requested);self.assertEqual(result['status'],'preflight_ready_not_a_permit');self.assertFalse(result['actual_action_allowed']);self.assertEqual(self.rows,[]);self.assertEqual(self.reads,['provider recheck'])
 def test_existing_envelope_uses_actual_fact_time_without_invention(self):
  self.req=self.request();self.pin=self.save('request-no-top-time.json',self.req);self.evidence['request']=self.pin;self.requested['payload_sha256']=self.pin['sha256'];self.policy_setup()
  result,_=a.policy(self.root,self.requested);self.assertEqual(result['status'],'preflight_ready_not_a_permit');self.assertNotIn('observed_at',self.req)
 def test_legacy_prior_policy_blocks_any_scope(self):
  self.policy_setup();self.rows.append({'status':'allow','task_id':m._EN2_FORWARD_TASK,'action_id':self.req['action_id'],'action_class':'cms_write','scope':self.req['physical_scope'],'department':'publishing'})
  with self.assertRaisesRegex(w.WorkflowError,'already issued'):a.policy(self.root,self.requested)
 def test_own_once_and_concurrent_policy(self):
  self.policy_setup();req={**self.requested,'consume_approval':True}
  self.rows.append({'task_id':m._EN2_FORWARD_TASK,'details':{'professional_cms_preflight':{'request':self.pin,'provider_origin_evidence':{'preview_receipt_checked_at':self.req['observed_at']}}}})
  def run(_):
   try:return a.policy(self.root,req)[0]['status']
   except w.WorkflowError:return 'rejected'
  with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(run,range(2)))
  self.assertEqual(sorted(results),['allow','rejected']);self.assertEqual(len([r for r in self.rows if r.get('status')=='allow']),1)
 def test_insufficient_time_does_not_consume_policy(self):
  self.policy_setup()
  checked=(dt.datetime.now(dt.timezone.utc)-dt.timedelta(seconds=240)).isoformat()
  self.rows.append({'task_id':m._EN2_FORWARD_TASK,'details':{'professional_cms_preflight':{'request':self.pin,'provider_origin_evidence':{'preview_receipt_checked_at':checked}}}})
  with self.assertRaisesRegex(w.WorkflowError,'75 seconds'):
   a.policy(self.root,{**self.requested,'consume_approval':True})
  self.assertFalse(any('status' in row for row in self.rows))
 def test_bound_readiness_launches_original_issuer_only_after_real_allow(self):
  import en2_forward_preflight_prepare as prepare
  from subprocess import CalledProcessError
  pin=self.save('request.json',self.req)
  ready=self.save('readiness.json',{'execution_preflight':pin,'execution_preflight_event_id':'event'})
  self.save('base.json',{'refs':{'preview_run_id':42}})
  policy={'status':'allow','actual_action_allowed':True,'decision_id':'fixture-policy','exact_request':pin}
  with patch.dict(prepare.os.environ,{'SUPABASE_URL':''}), patch.object(w,'read_jsonl',return_value=[{}]), patch.object(w,'policy_check') as check, patch.object(prepare.subprocess,'run') as issue:
   check.return_value=({'status':'preflight_ready_not_a_permit'},[])
   with self.assertRaises(w.WorkflowError):prepare.apply_original_policy_and_issue(self.root,self.root,ready)
   issue.assert_not_called()
   check.return_value=(policy,[])
   issue.side_effect=CalledProcessError(1,'issuer')
   with self.assertRaises(CalledProcessError):prepare.apply_original_policy_and_issue(self.root,self.root,ready)
   issue.assert_called_once()
   self.assertIn('--issue-and-dispatch',issue.call_args.args[0])
   self.assertIn('fixture-policy',issue.call_args.args[0])
 def test_wrong_supabase_project_rejects_before_policy(self):
  import en2_forward_preflight_prepare as prepare
  from en2_forward_issuer import project_url
  from en2_supabase_origin import PROJECT
  self.assertEqual(project_url(''),f'https://{PROJECT}.supabase.co')
  with patch.dict(prepare.os.environ,{'SUPABASE_URL':'https://other.supabase.co'}), patch.object(w,'policy_check') as policy:
   with self.assertRaisesRegex(w.WorkflowError,'Wrong Supabase project'):
    prepare.apply_original_policy_and_issue(self.root,self.root,{})
   policy.assert_not_called()
import tools.test_en2_forward_evidence as evidence_base
evidence_base.m=m
class IntegratedEvidence(evidence_base.Evidence):
 def test_original_evidence_to_context_fixture_only(self):
  self.snapshot['goal_delivery']={'primary_owner':'publishing','producer_departments':['publishing'],'authorization_pin':self.save('auth.json',{'fixture':'not human authority'}),'delivery_model':'historic'}
  req=self.struct['request'];requested={'task_id':m._EN2_FORWARD_TASK,'action_id':req['action_id'],'action_class':'cms_write','department':'publishing','scope':req['scope'],'source_project_id':a.PROJECT,'payload_sha256':self.struct['pin']['sha256']}
  with patch.object(a,'effective_mode',return_value=True):out=m.execution_context(self.root,self.snapshot,requested)
  self.assertEqual(out['pin'],self.struct['pin']);self.assertFalse(out['external_permission_issued'])

if __name__=='__main__':unittest.main(verbosity=2)
