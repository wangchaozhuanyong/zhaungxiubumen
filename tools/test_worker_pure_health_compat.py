"""Exact nonbusiness health packets support registered worker windows too."""
import datetime as dt
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent))
import workflow_control as w
import goal_delivery_runtime as g

class WorkerPureHealthCompat(unittest.TestCase):
    def test_healthy_lane_continues_without_waiving_other_gates(self):
        role={'new_dispatch_enabled':True,'chat_binding':{'task_id':'fixed-ready'}}
        snap={'plan_status':'blocked_health_stale','goal_delivery':{},'departments':[{'department':'ready','chat_task_id':'fixed-ready'},{'department':'stale','chat_task_id':'fixed-stale'}]}
        with patch.object(w,'department_registry',return_value={'ready':role}),patch.object(w,'read_json',return_value={'health_policy':{'verification_ttl_hours':26}}),patch.object(w,'_chat_binding_healthy',return_value=True):
            self.assertTrue(w._target_dispatch_plan_ready(Path('/fixture'),snap,'ready'))
            self.assertFalse(w._target_dispatch_plan_ready(Path('/fixture'),snap,'stale'))
            self.assertFalse(w._target_dispatch_plan_ready(Path('/fixture'),{**snap,'plan_status':'blocked_route_invalid'},'ready'))
            self.assertFalse(w._target_dispatch_plan_ready(Path('/fixture'),{**snap,'goal_delivery':None},'ready'))
        with patch.object(w,'department_registry',return_value={'ready':role}),patch.object(w,'read_json',return_value={}),patch.object(w,'_chat_binding_healthy',return_value=False):
            self.assertFalse(w._target_dispatch_plan_ready(Path('/fixture'),snap,'ready'))
        with patch.object(w,'department_registry',return_value={'ready':{**role,'new_dispatch_enabled':False}}),patch.object(w,'read_json',return_value={}),patch.object(w,'_chat_binding_healthy',return_value=True):
            self.assertFalse(w._target_dispatch_plan_ready(Path('/fixture'),snap,'ready'))
    def probe(self, mode='worker', active=True, business=False, tampered=False):
        project=Path(__file__).resolve().parents[1]
        area = project / '.test-tmp'
        area.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=area) as tmp:
            root=Path(tmp);role='publishing';task='fixture-worker-health';scope='department_health_probe:'+role
            fixed={'task_id':'fixture-fixed-pub','project_id':'fixture-project','cwd':str(root),'title':'Fixture publisher','sidebar_section_id':'fixture-group'}
            row={'id':role,'new_dispatch_enabled':active,'mode':mode,'chat_binding':fixed,'coordination_authority':{'routine_decisions':mode=='coordinator'}}
            goal={'producer_departments':[role],'responsible_assistant':'fixture-assistant','authorized_scope':[scope],'required_execution_actions':[{'action_id':'not-health'}] if business else []}
            expected={'schema_version':'goal-health-probe-v1','task_id':task,'target_department':role,'target_thread_id':fixed['task_id'],'scope':scope,'request':'请仅确认当前项目、目录、固定身份是否一致及是否可接续。'}
            if tampered:expected['request']='Save CMS content'
            live={'observed_at':dt.datetime.now(dt.timezone.utc).isoformat(),'threads':[{'id':fixed['task_id'],'projectId':fixed['project_id'],'cwd':str(root),'title':fixed['title'],'status':'idle'}],'sections':[{'sectionId':fixed['sidebar_section_id'],'itemKeys':['codex:thread:local:'+fixed['task_id']]}]}
            for name,data in [('packet.json',expected),('live.json',live),('contract.json',goal)]:
                (root/name).write_text(json.dumps(data,ensure_ascii=False))
            packet=w.file_digest(root,'packet.json');native=w.file_digest(root,'live.json');contract=w.file_digest(root,'contract.json')
            snapshot={'task_id':task,'goal_contract':contract,'goal_delivery':{**goal,'approved_actions':[{'payload':packet,'payload_sha256':packet['sha256'],'scope':scope,'live_identity':native}]}}
            with patch.object(g,'enabled',return_value=True),patch.object(g,'validate_goal',return_value=goal),patch.object(g,'REQUIRED',tuple(goal)),patch.object(w,'department_registry',return_value={role:row}):
                return w.exact_health_probe(root,snapshot,sender='operations',target=role,scope=scope,payload_sha256=packet['sha256'])
    def test_active_registered_worker_allowed(self):self.assertTrue(self.probe())
    def test_coordinator_still_allowed(self):self.assertTrue(self.probe(mode='coordinator'))
    def test_retired_or_disabled_rejected(self):
        self.assertFalse(self.probe(mode='retired_history'));self.assertFalse(self.probe(active=False))
    def test_business_action_or_changed_message_rejected(self):
        self.assertFalse(self.probe(business=True));self.assertFalse(self.probe(tampered=True))

if __name__=='__main__':unittest.main()
