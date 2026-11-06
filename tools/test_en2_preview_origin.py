import copy,datetime as dt,importlib.util,io,json,pathlib,unittest,zipfile
from unittest.mock import patch
import workflow_control as w
import en2_preview_origin as m
class Checks(unittest.TestCase):
 def setUp(self):
  self.now=dt.datetime.now(dt.timezone.utc);self.sha='a'*40;self.rid=123;self.ts='2026-10-19T13:39:00.867332+00:00'
  row={**{f'field_{i}':i for i in range(24)},**{f'f{i}_ms':i for i in range(11)},'id':'fixture','slug':'kitchen','title_en':'old','excerpt_en':'old','updated_at':self.ts,'version':1};self.assertEqual(len(row),41)
  fields=['title_en','excerpt_en'];patchv={'title_en':'new','excerpt_en':'new excerpt'};retained=sorted(set(row)-set(fields)-{'updated_at','version'});self.assertEqual(len(retained),37)
  self.t={'taskId':m.TASK,'id':'fixture','slug':'kitchen','table':'services','scope':'physical','actionId':'action','candidateVersion':'version','expectedUpdatedAt':self.ts,'changedFields':fields,'rollbackAllowed':False,'baselineProjectionFields':sorted(row),'retainedProjectionFields':retained,'baselineFieldsSha256':w.sha256_value(row),'retainedFieldsSha256':w.sha256_value({k:row[k] for k in retained}),'desiredFieldsSha256':w.sha256_value(patchv)}
  self.run={'id':self.rid,'name':'Approved website content publish','run_started_at':(self.now-dt.timedelta(seconds=10)).isoformat(),'updated_at':self.now.isoformat(),'event':'workflow_dispatch','status':'completed','conclusion':'success','run_attempt':1,'head_branch':'main','path':m.WORKFLOW,'head_sha':self.sha,'repository':{'id':m.REPO_ID,'full_name':m.REPO},'actor':{'id':m.ACTOR},'workflow_id':7}
  self.workflow={'id':7,'path':m.WORKFLOW,'state':'active','name':'Approved website content publish'};self.ref={'object':{'sha':self.sha}};self.art={'id':88,'name':'approved-content-publish-123','expired':False,'workflow_run':{'id':self.rid,'repository_id':m.REPO_ID,'head_sha':self.sha}}
  self.docs={'locked-dry-run-receipt.json':{'task_id':m.TASK,'candidate_version':'version','action_id':'action','operation':'publish','scope':'physical','http_status':200,'dry_run':True,'performed_write':False,'external_writes':0,'row_unchanged_after_dry_run':True,'expected_updated_at':self.ts,'checked_at':self.now.isoformat()},'managed-payload-digest.json':{'task_id':m.TASK,'candidate_version':'version','operation':'publish','payload_sha256':w.sha256_value(patchv),'expected_updated_at':self.ts},'dry-run.json':{'ok':True,'dry_run':True,'performed_write':False,'payload_preview':patchv},'managed-identity-probe.json':{'ok':True,'dry_run':True,'performed_write':False,'identity':{'runId':self.rid,'runAttempt':1,'repositoryId':m.REPO_ID,'actorId':m.ACTOR,'workflowSha':self.sha,'workflowRef':f'{m.REPO}/{m.WORKFLOW}@refs/heads/main'}},'locked-candidate.json':{'task_id':m.TASK,'candidate_version':'version','action_id':'action','scope':'physical','expected_updated_at':self.ts,'changed_fields':fields,'baseline_fields_sha256':w.sha256_value(row),'desired_fields_sha256':w.sha256_value(patchv)},'backup.json':{'target':m.NAME,'table':'services','key':'kitchen','record':row},'desired.json':{'target':m.NAME,'operation':'optimize','record':{**row,**patchv}}}
 def check(self):return m._validate(self.rid,self.run,self.workflow,self.ref,self.art,self.docs,self.t,self.now)
 def test_valid_fixture_only(self):
  x=self.check();self.assertFalse(x['actual_action_allowed']);self.assertEqual(x['key_effect_origin'],'NOT_VERIFIED')
 def test_live_backup_id_and_optional_raw_write_flag(self):
  self.docs['backup.json'].update(keyField='id',key=self.t['id'])
  self.docs['dry-run.json'].pop('performed_write')
  self.assertEqual(self.check()['preview_origin'],'VERIFIED_GITHUB_PROVIDER_READ')
  self.docs['locked-dry-run-receipt.json']['external_writes']=1
  with self.assertRaises(w.WorkflowError):self.check()
 def test_historical_read_only_never_counts_as_fresh_preview(self):
  later=self.now+dt.timedelta(seconds=301)
  with self.assertRaises(w.WorkflowError):
   m._validate(self.rid,self.run,self.workflow,self.ref,self.art,self.docs,self.t,later)
  proof=m._validate(self.rid,self.run,self.workflow,self.ref,self.art,self.docs,self.t,later,historical=True)
  self.assertEqual(proof['preview_origin'],'VERIFIED_HISTORICAL_ZERO_WRITE')
  self.assertFalse(proof['actual_action_allowed'])
 def test_mismatches(self):
  cases=[('run','id',124),('run','run_attempt',2),('run','head_branch','other'),('art','id',0),('art','expired',True),('ref','object',{'sha':'b'*40}),('workflow','state','disabled'),('t','rollbackAllowed',True)]
  for obj,key,val in cases:
   with self.subTest(obj=obj,key=key):
    orig=copy.deepcopy(getattr(self,obj));getattr(self,obj)[key]=val
    with self.assertRaises(w.WorkflowError):self.check()
    setattr(self,obj,orig)
 def test_bad_receipts(self):
  for name,key,val in [('locked-dry-run-receipt.json','external_writes',1),('locked-dry-run-receipt.json','task_id','wrong'),('managed-payload-digest.json','payload_sha256','0'*64),('locked-dry-run-receipt.json','checked_at',(self.now-dt.timedelta(seconds=301)).isoformat()),('backup.json','record',{}),('dry-run.json','performed_write',True)]:
   with self.subTest(name=name,key=key):
    old=self.docs[name][key];self.docs[name][key]=val
    with self.assertRaises(w.WorkflowError):self.check()
    self.docs[name][key]=old
 def test_zip_requires_one_safe_file(self):
  b=io.BytesIO()
  with zipfile.ZipFile(b,'w') as z:z.writestr('../escape','{}')
  with self.assertRaises(w.WorkflowError):m._unpack(b.getvalue(),pathlib.Path('.'))
 def test_read_actual_never_accepts_caller_documents(self):
  import inspect
  self.assertEqual(list(inspect.signature(m.read_actual).parameters),['root','run_id'])
 def test_live_reader_uses_provider_and_rejects_bad_archive_digest(self):
  import hashlib,professional_cms_issuer
  b=io.BytesIO()
  with zipfile.ZipFile(b,'w') as z:
   for name,doc in self.docs.items():z.writestr(m.NAME+'/'+name,json.dumps(doc))
  raw=b.getvalue();self.art['digest']='sha256:'+hashlib.sha256(raw).hexdigest()
  def api(path):
   if '/actions/runs/123/artifacts?' in path:return {'total_count':1,'artifacts':[self.art]}
   if path.endswith('/actions/runs/123'):return self.run
   if '/actions/workflows/' in path:return self.workflow
   if path.endswith('/git/ref/heads/main'):return self.ref
   raise AssertionError(path)
  source={'source_event_id':'698ae455-16d7-4ad1-8744-ebfc8fd763e1','actual_action_allowed':False,'physical_target':self.t}
  with patch.object(professional_cms_issuer,'targets',return_value={m.NAME:source}), patch.object(m,'_api',side_effect=api), patch.object(m,'_archive',return_value=raw):
   self.assertEqual(m.read_actual(pathlib.Path('.'),123)['preview_origin'],'VERIFIED_GITHUB_PROVIDER_READ')
   self.art['digest']='sha256:'+'0'*64
   with self.assertRaisesRegex(w.WorkflowError,'artifact digest'):m.read_actual(pathlib.Path('.'),123)

if __name__=='__main__':unittest.main(verbosity=2)
