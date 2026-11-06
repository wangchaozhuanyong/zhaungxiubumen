import copy,datetime as dt,importlib.util,json,pathlib,unittest
from unittest.mock import patch
import department_event_dispatcher as d
import workflow_control as w
import tools.test_en2_supabase_origin as base
import en2_supabase_origin as m;base.m=m

class Live(base.Fixture):
 def setUp(self):
  super().setUp();
  for q in self.native['turns'][0]['items']:
   raw=json.loads(q['output']['content'][0]['text']);raw['result']=raw['result'].replace('provider <','provider\n<');q['output']['content'][0]['text']=json.dumps(raw)
  self.calls=[];self.closed=[];self.thread={'id':'pub','name':'PUB','cwd':str(self.root),'projectId':None};self.turn=copy.deepcopy(self.native['turns'][0]);self.turn['itemsView']='full';at=self.now.timestamp()
  for idx,x in enumerate(self.turn['items']):
   x['result']=x.pop('output'); raw=json.loads(x['result']['content'][0]['text']);raw['result']=raw['result'].replace('provider <','provider\n<');x['result']['content'][0]['text']=json.dumps(raw);x['result']['_meta']={'io.modelcontextprotocol/serverInfo':{'name':'supabase','title':'Supabase','version':'0.15.0'}}
   x['startedAtMs']=int((at+[-3,-1.8,-1.3][idx])*1000);x['completedAtMs']=int((at+[-1.9,-1.4,-1.1][idx])*1000)
  parent=self
  class RPC:
   def __init__(self,command):parent.calls.append(('init',command))
   def call(self,method,params):
    parent.calls.append((method,params))
    if method=='thread/read':return {'thread':copy.deepcopy(parent.thread)}
    if method=='thread/turns/list':return {'data':[copy.deepcopy(parent.turn)]}
    raise AssertionError('write or other method attempted')
   def close(self):parent.closed.append(True)
  self.rpcs=[patch.object(d,'RPC',RPC),patch.object(d,'native_queue_capability',return_value='/trusted/codex')]
  for x in self.rpcs:x.start()
  self.addCleanup(lambda:[x.stop() for x in reversed(self.rpcs)])
 def live(self,same=None):return m.read_actual(self.root,'turn','row','key',same)
 def test_live_two_only_fresh_without_project_fabrication(self):
  x=self.live();self.assertEqual(x['row_call_origin'],'VERIFIED_OFFICIAL_RPC');self.assertEqual(x['same_row_call_origin'],'DATA_MISSING');self.assertIsNone(x['thread_project_id_actual']);self.assertFalse(x['actual_action_allowed']);self.assertEqual(x['preflight_origin'],'NOT_VERIFIED');self.assertTrue(self.closed);self.assertEqual([x[0] for x in self.calls],['init','thread/read','thread/turns/list'])
 def test_live_same_row_and_failed_result(self):
  x=self.live('same');self.assertEqual(x['same_row_effect'],'NO_BLOCKING_ROW_OBSERVED')
  self.turn['items'][1]['result']['isError']=True
  with self.assertRaises(w.WorkflowError):self.live('same')
 def test_live_publisher_uses_authenticated_clock_without_turn_end(self):
  self.turn.update(status='interrupted',completedAt=None)
  with patch('en2_preview_web_identity._desktop_live_turn',return_value=True) as prove:
   result=m.read_actual(self.root,'turn','row','key','same',live_publisher=True)
   self.assertEqual(result['same_row_effect'],'NO_BLOCKING_ROW_OBSERVED')
   prove.assert_called_once()
   with self.assertRaises(w.WorkflowError):self.live('same')
 def test_postgres_server_clock_with_hour_offset_and_short_fraction(self):
  self.assertEqual(w._parse_observed_at('2026-11-05 14:58:19.2554+00'),
                   dt.datetime(2026,11,5,14,58,19,255400,tzinfo=dt.timezone.utc))
 def test_wrong_thread_project_sql_or_missing_result(self):
  for which in ('thread','project','sql','output','print','error'):
   with self.subTest(which=which):
    oldthread=copy.deepcopy(self.thread);oldt=copy.deepcopy(self.turn)
    if which=='thread':self.thread['name']='wrong'
    if which=='project':self.thread['projectId']='other'
    if which=='sql':self.turn['items'][1]['arguments']['query']='SELECT 1;'
    if which=='output':self.turn['items'][0].pop('result')
    if which=='print':self.turn['items'][0]['type']='commandExecution'
    if which=='error':self.turn['items'][1]['error']={'message':'failed'}
    with self.assertRaises(w.WorkflowError):self.live()
    self.thread=oldthread;self.turn=oldt
 def test_saved_export_must_match_live(self):
  result=copy.deepcopy(self.turn['items'][0]['result']);result.pop('_meta');result['isError']=False
  p=self.root/'export.json';p.write_text(json.dumps({'status':'fulfilled','value':result}));self.assertTrue(m.read_actual(self.root,'turn','row','key',row_export='export.json')['row_export_match'])
  result['content'][0]['text']='{}';p.write_text(json.dumps({'status':'fulfilled','value':result}))
  with self.assertRaisesRegex(w.WorkflowError,'differs'):m.read_actual(self.root,'turn','row','key',row_export='export.json')
 def test_old_clock_reports_not_fresh(self):
  old=self.now-dt.timedelta(seconds=301);self.turn['startedAt']=old.timestamp()-2;self.turn['completedAt']=old.timestamp()+3
  for idx,item in enumerate(self.turn['items']):item['startedAtMs']=int((old.timestamp()+[-1,.1,.6][idx])*1000);item['completedAtMs']=int((old.timestamp()+[.05,.55,1][idx])*1000)
  obj={'server_observed_at':old.isoformat(),'raw_full_record':json.dumps(self.row)};self.turn['items'][0]['result']['content'][0]['text']=json.dumps({'result':'<untrusted-data-a12>\n'+json.dumps([obj])+'\n</untrusted-data-a12>'})
  self.assertFalse(self.live()['fresh_within_300_seconds'])
if __name__=='__main__':unittest.main(verbosity=2)
