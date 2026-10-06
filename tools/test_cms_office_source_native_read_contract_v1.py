import copy,json,hashlib,tempfile,unittest
from pathlib import Path
import cms_office_source_native_read_contract_v1 as c
BASE=json.loads((Path(__file__).resolve().parents[1]/'drafts/operations/fc-20261006-office-exact-native-source-read-control-v2/exact-source-read-request.json').read_text())
class OfficeReadTests(unittest.TestCase):
 def test_exact_published_office_read_allowed(self):self.assertEqual(c.validate_request(BASE),[])
 def test_other_task_action_scope_actor_table_slug_denied(self):
  for key in ('task_id','action_id','scope','department','table','slug','fixed_executor_chat_task_id'):
   with self.subTest(key=key):self.assertTrue(c.validate_request({**BASE,key:'other'}))
 def test_no_extra_field_or_metadata(self):
  for key in ('field_pointers','metadata_fields'):self.assertTrue(c.validate_request({**BASE,key:BASE[key]+['*']}))
 def test_no_guessed_record_or_extra_access(self):
  self.assertTrue(c.validate_request({**BASE,'record_id':'invented'}))
 def test_raw_CAS_and_same_snapshot_required(self):
  for key in ('require_raw_updated_at','same_snapshot_required'):
   self.assertTrue(c.validate_request({**BASE,key:False}))
 def test_no_write_preview_login_credentials_export(self):
  for key in ('production_write_allowed','protected_preview_allowed','login_or_account_change_allowed','credential_capture_allowed','full_row_export_allowed'):
   self.assertTrue(c.validate_request({**BASE,key:True}))
 def test_boolean_integers_denied(self):
  for key in ('read_only','same_snapshot_required'):self.assertTrue(c.validate_request({**BASE,key:1}))
 def test_only_published_exact_unique_slug(self):
  for key,value in [('status_equals','draft'),('slug_equals','*'),('require_exactly_one_row',False)]:
   d=copy.deepcopy(BASE);d['lookup'][key]=value;self.assertTrue(c.validate_request(d))
 def test_only_owner_Chrome_method(self):self.assertTrue(c.validate_request({**BASE,'source_method':'SQL'}))
 def test_frozen_payload_binding(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);p=root/'request.json';p.write_text(json.dumps(BASE));sha=hashlib.sha256(p.read_bytes()).hexdigest()
   binding={k:BASE[k] for k in ('task_id','action_id','scope','department')};binding.update(request_path='request.json',request_sha256=sha)
   args=(root,binding,c.TASK,c.ACTION,c.SCOPE,'publishing')
   self.assertEqual(c.check_binding(*args,sha),[]);self.assertTrue(c.check_binding(*args,'0'*64))
   p.write_text('{}');self.assertTrue(c.check_binding(*args,sha))
 def test_outside_or_missing_request_denied(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);b={k:BASE[k] for k in ('task_id','action_id','scope','department')}
   for p in ('../request.json','/tmp/request.json','missing.json'):
    b['request_path']=p;self.assertTrue(c.check_binding(root,b,c.TASK,c.ACTION,c.SCOPE,'publishing','0'*64))
if __name__=='__main__':unittest.main()
