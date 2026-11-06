import copy,datetime as dt,importlib.util,json,pathlib,tempfile,unittest
from unittest.mock import patch
import workflow_control as w, department_autonomy as a
import en2_supabase_origin as m
PROJECT=pathlib.Path(__file__).resolve().parents[2]
class Fixture(unittest.TestCase):
 def setUp(self):
  root=pathlib.Path.cwd();self.temp=tempfile.TemporaryDirectory(prefix='en2-native-fixture-',dir=root/'backups');self.addCleanup(self.temp.cleanup);self.root=pathlib.Path(self.temp.name)
  now=dt.datetime.now(dt.timezone.utc);self.now=now;row={**{f'field{i}':i for i in range(24)},**{f'f{i}_ms':i for i in range(11)},'id':m.RECORD,'slug':'kitchen','title_en':'old','excerpt_en':'old','updated_at':'2026-10-19T13:39:00.867332+00:00','version':1};self.row=row; self.assertEqual(len(row),41);ret=sorted(set(row)-{'title_en','excerpt_en','updated_at','version'});
  self.target={'baselineProjectionFields':sorted(row),'retainedProjectionFields':ret,'baselineFieldsSha256':w.sha256_value(row),'retainedFieldsSha256':w.sha256_value({k:row[k] for k in ret})};self.source={'source_event_id':'698ae455-16d7-4ad1-8744-ebfc8fd763e1','actual_action_allowed':False,'physical_target':self.target};self.binding={'task_id':'pub','title':'PUB','cwd':str(self.root),'project_id':a.PROJECT}
  def result(rows):
   return {'content':[{'type':'text','text':json.dumps({'result':'provider <untrusted-data-a12-b34>\n'+json.dumps(rows)+'\n</untrusted-data-a12-b34> end'})}],'structuredContent':None}
  def call(id,query,rows):return {'id':id,'type':'mcpToolCall','server':'codex_apps','tool':'supabase.execute_sql','status':'completed','arguments':{'project_id':m.PROJECT,'query':query},'output':result(rows)}
  self.native={'thread':{'id':'pub','title':'PUB','cwd':str(self.root)},'turns':[{'id':'turn','status':'completed','startedAt':now.timestamp()-5,'completedAt':now.timestamp()-1,'items':[call('row',m.ROW_SQL,[{'server_observed_at':(now-dt.timedelta(seconds=2)).isoformat(),'raw_full_record':json.dumps(row)}]),call('key',m.KEY_SQL,[]),call('same',m.SAME_ROW_SQL,[])]}]}
  self.patches=[patch.object(w,'department_registry',return_value={'publishing':{'chat_binding':self.binding}}),patch('professional_cms_issuer.targets',return_value={'english-kitchen-en2-exact-v1':self.source})]
  for x in self.patches:x.start()
  self.addCleanup(lambda:[x.stop() for x in reversed(self.patches)])
 def save(self):
  p=self.root/'native.json';p.write_text(json.dumps(self.native));return w.file_digest(self.root,'native.json')
 def check(self):return m.inspect_native(self.root,self.save(),'row','key','same')
 def test_valid_is_structural_only(self):
  x=self.check();self.assertEqual(x['provider_origin'],'NOT_VERIFIED');self.assertFalse(x['actual_action_allowed']);self.assertTrue(x['fresh_within_300_seconds'])
 def test_wrong_pub_and_arguments(self):
  for path,value in [('thread','other'),('project','other'),('query','SELECT 1;')]:
   with self.subTest(path=path):
    n=copy.deepcopy(self.native)
    if path=='thread':self.native['thread']['id']=value
    elif path=='project':self.native['turns'][0]['items'][0]['arguments']['project_id']=value
    else:self.native['turns'][0]['items'][1]['arguments']['query']=value
    with self.assertRaises(w.WorkflowError):self.check()
    self.native=n
 def test_fake_print_failed_and_output_missing(self):
  for change in ('print','failed','error','missing','truncated'):
   with self.subTest(change=change):
    n=copy.deepcopy(self.native);x=self.native['turns'][0]['items'][0]
    if change=='print':x['type']='commandExecution'
    if change=='failed':x['status']='failed'
    if change=='error':x['output']['isError']=True
    if change=='missing':x.pop('output')
    if change=='truncated':x['output']['truncated']=True
    with self.assertRaises(w.WorkflowError):self.check()
    self.native=n
 def test_tampered_pin_and_missing_same(self):
  pin=self.save();(self.root/'native.json').write_text('{}')
  with self.assertRaises(Exception):m.inspect_native(self.root,pin,'row','key','same')
  self.native['turns'][0]['items'].pop()
  with self.assertRaisesRegex(w.WorkflowError,'DATA_MISSING'):self.check()
 def test_old_row_and_unknown_effect(self):
  self.row.pop('f0_ms');q=self.native['turns'][0]['items'][0]['output']['content'][0];q['text']=json.dumps({'result':'<untrusted-data-a12>\n'+json.dumps([{'server_observed_at':(self.now-dt.timedelta(seconds=2)).isoformat(),'raw_full_record':json.dumps(self.row)}])+'\n</untrusted-data-a12>'})
  with self.assertRaises(w.WorkflowError):self.check()
  self.setUp()
  q=self.native['turns'][0]['items'][2]['output']['content'][0];q['text']=json.dumps({'result':'<untrusted-data-a12>\n'+json.dumps([{'record_id':m.RECORD,'task_id':'other','action_id':'other','candidate_version':'other','status':'writing'}])+'\n</untrusted-data-a12>'})
  with self.assertRaisesRegex(w.WorkflowError,'unknown/in-flight'):self.check()
 def test_stale_is_separately_reported(self):
  old=self.now-dt.timedelta(seconds=301);t=self.native['turns'][0];t['startedAt']=old.timestamp()-2;t['completedAt']=old.timestamp()+1;q=t['items'][0]['output']['content'][0];q['text']=json.dumps({'result':'<untrusted-data-a12>\n'+json.dumps([{'server_observed_at':old.isoformat(),'raw_full_record':json.dumps(self.row)}])+'\n</untrusted-data-a12>'});self.assertFalse(self.check()['fresh_within_300_seconds'])
 def test_exact_query_source_and_order(self):
  original=copy.deepcopy(self.native)
  self.native['turns'][0]['items'][0]['arguments']['query']=m.ROW_SQL.replace("'kitchen'","'KITCHEN'")
  with self.assertRaises(w.WorkflowError):self.check()
  self.native=copy.deepcopy(original);self.native['turns'][0]['items'][0]['arguments']['query']=m.ROW_SQL+' select 1;'
  with self.assertRaises(w.WorkflowError):self.check()
  self.native=copy.deepcopy(original);self.native['turns'][0]['items'].reverse()
  with self.assertRaisesRegex(w.WorkflowError,'ordered'):self.check()
  self.native=original;self.source['source_event_id']='wrong'
  with self.assertRaises(w.WorkflowError):self.check()
 def test_prior_own_completed_is_not_absence(self):
  row={'record_id':m.RECORD,'task_id':m.TASK,'action_id':m.ACTION,'candidate_version':m.VERSION,'status':'completed'}
  for i in (1,2):
   q=self.native['turns'][0]['items'][i]['output']['content'][0];q['text']=json.dumps({'result':'<untrusted-data-a12>\n'+json.dumps([row])+'\n</untrusted-data-a12>'})
  with self.assertRaisesRegex(w.WorkflowError,'prior effect'):self.check()
 def test_other_completed_preserved(self):
  row={'record_id':m.RECORD,'task_id':'other','action_id':'other','candidate_version':'other','status':'completed'}
  q=self.native['turns'][0]['items'][2]['output']['content'][0];q['text']=json.dumps({'result':'<untrusted-data-a12>\n'+json.dumps([row])+'\n</untrusted-data-a12>'})
  self.assertEqual(self.check()['same_row_count'],1)

if __name__=='__main__':unittest.main(verbosity=2)
