from __future__ import annotations
import test_runtime_paths
import copy
import datetime as dt
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent))
sys.path.insert(1,"<PROJECT_ROOT>/tools")
import department_next_work as target
import workflow_control as w

class WorkpackTests(unittest.TestCase):
    def setUp(self):
        test_base = test_runtime_paths.root()
        test_base.mkdir(exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=test_base)
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.now = dt.datetime.now(dt.timezone.utc)
        self.task = "fc-20261006-workpack-test-v1"
        self.dep = "seo-content-research"
        self.bind = dict(task_id="fixed-seo",project_id="project",title="SEO",cwd=str(self.root),
                         sidebar_section_id="section",status="bound_and_visible",dispatch_eligible=True,
                         reply_health="healthy_visible_reply_verified",last_health_check_at=self.now.isoformat())
        self.live = dict(observed_at=self.now.isoformat(),threads=[
            dict(id="fixed-seo",projectId="project",title="SEO",cwd=str(self.root),status="active")],
            sections=[dict(id="section",name="装修公司部门",itemKeys=["codex:thread:local:fixed-seo"])])
        self.packet = dict(task_id=self.task,department=self.dep,project_id="project",fixed_chat_task_id="fixed-seo",
            continuation_plan=dict(version=1,mode="same_task_local_r0_only",external_actions_allowed=False,
                expires_at=(self.now+dt.timedelta(hours=1)).isoformat(),steps=[
                    dict(step_id="a",candidate_version="a-v1",kind="local_candidate",scope="page-A",requires_controller_gate=False,
                         output_dir=f"drafts/seo/{self.task}/a-v1",depends_on=[],subskills=["renovation-seo-geo"]),
                    dict(step_id="b",candidate_version="b-v1",kind="public_source_check",scope="page-B",requires_controller_gate=False,
                         output_dir=f"drafts/seo/{self.task}/b-v1",depends_on=[],subskills=["renovation-seo-geo"])]))
        self.path = "logs/handoffs/workpack.json"
        self.write(self.path,self.packet)
        self.registry = {self.dep:dict(chat_binding=self.bind,approved_subskills=["renovation-seo-geo"])}
        self.dispatch = dict(receipt_type="dispatch_sent",department=self.dep,chat_task_id="fixed-seo",
                             created_at=(self.now-dt.timedelta(minutes=1)).isoformat(),
                             evidence=[w.file_digest(self.root,self.path)])
        self.ack = dict(receipt_type="chat_ack",department=self.dep,chat_task_id="fixed-seo",ack_nonempty=True,
                        created_at=(self.now-dt.timedelta(seconds=30)).isoformat())
        self.receipts = [self.dispatch,self.ack]
        self.registry_patch = patch.object(w,"department_registry",lambda root:self.registry)
        self.receipt_patch = patch.object(w,"_validate_receipt_chain",lambda root,task:(self.receipts,[]))
        self.registry_patch.start(); self.receipt_patch.start()
        self.addCleanup(self.registry_patch.stop); self.addCleanup(self.receipt_patch.stop)
    def write(self,path,obj):
        p=self.root/path;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(obj),encoding="utf-8")
    def update(self):
        self.write(self.path,self.packet)
        self.dispatch["evidence"]=[w.file_digest(self.root,self.path)]
    def check(self):
        return target.inspect(self.root,self.path,self.live,self.now)
    def queued(self,sid="a",status="completed"):
        cv=sid+"-v1"; path=f"logs/department-outbox/{sid}.json"
        box=dict(schema_version="2.0",task_id=self.task,department=self.dep,fixed_chat_task_id="fixed-seo",
                 candidate_version=cv,status=status,conclusion="test",evidence=[],risks=[],next_actions=[],handoff={},
                 approval_required=True,learning=dict(status="no_new_learning"),
                 chat_reply=dict(nonempty=True,in_current_fixed_department_chat=True))
        step=next(s for s in self.packet["continuation_plan"]["steps"] if s["step_id"]==sid)
        box["step_binding"]=target.make_step_binding(self.root,self.packet,step,w.file_digest(self.root,self.path)["sha256"])
        self.write(path,box);digest=w.file_digest(self.root,path)
        ledger=w.result_handoff_path(self.root,self.task)
        rows=w._result_handoff_rows(self.root,self.task)
        row=dict(task_id=self.task,event="notification_queued",sender_department=self.dep,candidate_version=cv,
                 result_sha256=digest["sha256"],outbox=digest,previous_hash=rows[-1]["record_hash"] if rows else "")
        row["record_hash"]=w.sha256_value(row)
        ledger.parent.mkdir(parents=True,exist_ok=True)
        with ledger.open("a",encoding="utf-8") as fh:fh.write(json.dumps(row)+"\n")
    def test_ready_before_controller(self):
        self.assertEqual(self.check()["next_step"]["step_id"],"a")
    def test_reported_candidate_does_not_block_independent(self):
        self.queued();self.assertEqual(self.check()["next_step"]["step_id"],"b")
    def test_partial_only_blocks_dependants(self):
        self.packet["continuation_plan"]["steps"][1]["depends_on"]=["a"];self.update()
        self.queued(status="partial")
        self.assertEqual(self.check()["mode"],"RETURN_FOR_CONTROLLER_DECISION")
    def test_blocked_only_blocks_dependants(self):
        self.queued(status="blocked");self.assertEqual(self.check()["next_step"]["step_id"],"b")
    def test_completed_dependency_ready(self):
        self.packet["continuation_plan"]["steps"][1]["depends_on"]=["a"];self.update()
        self.queued();self.assertEqual(self.check()["next_step"]["step_id"],"b")
    def test_repeated_check_reads_same_next_without_record(self):
        self.queued(); before=sorted(str(p) for p in self.root.rglob("*"))
        self.assertEqual(self.check(),self.check())
        self.assertEqual(before,sorted(str(p) for p in self.root.rglob("*")))
    def test_accepted_all_releases_window_not_goal(self):
        self.queued();self.queued("b");answer=self.check()
        self.assertEqual(answer["mode"],"RETURN_FOR_CONTROLLER_DECISION")
        self.assertFalse(answer["business_goal_closed"]);self.assertFalse(answer["external_permission_issued"])
    def test_existing_output_is_recovery_not_redelivery(self):
        (self.root/self.packet["continuation_plan"]["steps"][0]["output_dir"]).mkdir(parents=True)
        self.assertEqual(self.check()["mode"],"RECOVER_EXISTING_OUTPUT")
    def test_tampered_packet_rejected(self):
        self.packet["project_id"]="other";self.write(self.path,self.packet)
        with self.assertRaises(w.WorkflowError):self.check()
    def test_packet_not_in_actual_dispatch_rejected(self):
        self.dispatch["evidence"]=[]
        with self.assertRaises(w.WorkflowError):self.check()
    def test_missing_nonempty_ack_rejected(self):
        self.ack["ack_nonempty"]=False
        with self.assertRaises(w.WorkflowError):self.check()
    def test_stale_health_rejected(self):
        self.bind["last_health_check_at"]=(self.now-dt.timedelta(hours=27)).isoformat()
        with self.assertRaises(w.WorkflowError):self.check()
    def test_future_health_rejected(self):
        self.bind["last_health_check_at"]=(self.now+dt.timedelta(hours=1)).isoformat()
        with self.assertRaises(w.WorkflowError):self.check()
    def test_wrong_live_project_rejected(self):
        self.live["threads"][0]["projectId"]="other"
        with self.assertRaises(w.WorkflowError):self.check()
    def test_stale_live_rejected(self):
        self.live["observed_at"]=(self.now-dt.timedelta(minutes=6)).isoformat()
        with self.assertRaises(w.WorkflowError):self.check()
    def test_future_live_rejected(self):
        self.live["observed_at"]=(self.now+dt.timedelta(seconds=2)).isoformat()
        with self.assertRaises(w.WorkflowError):self.check()
    def test_wrong_or_duplicate_group_rejected(self):
        self.live["sections"][0]["name"]="Other"
        with self.assertRaises(w.WorkflowError):self.check()
    def test_overlong_authorization_rejected(self):
        self.packet["continuation_plan"]["expires_at"]=(self.now+dt.timedelta(hours=27)).isoformat();self.update()
        with self.assertRaises(w.WorkflowError):self.check()
    def test_expired_packet_rejected(self):
        self.packet["continuation_plan"]["expires_at"]=(self.now-dt.timedelta(seconds=1)).isoformat();self.update()
        with self.assertRaises(w.WorkflowError):self.check()
    def test_forbidden_actions_rejected(self):
        for kind in ["cms_write","site_publish","account_read","thread_message","render_video","ads_write"]:
            with self.subTest(kind=kind):
                self.packet["continuation_plan"]["steps"][0]["kind"]=kind;self.update()
                with self.assertRaises(w.WorkflowError):self.check()
    def test_qa_gate_cannot_be_bypassed(self):
        self.packet["continuation_plan"]["steps"][0]["requires_controller_gate"]=True;self.update()
        with self.assertRaises(w.WorkflowError):self.check()
    def test_cross_project_directory_rejected(self):
        self.packet["continuation_plan"]["steps"][0]["output_dir"]="/tmp/other";self.update()
        with self.assertRaises(w.WorkflowError):self.check()
    def test_overlapping_output_rejected(self):
        self.packet["continuation_plan"]["steps"][1]["output_dir"]=self.packet["continuation_plan"]["steps"][0]["output_dir"]+"/nested";self.update()
        with self.assertRaises(w.WorkflowError):self.check()
    def test_new_subskill_rejected(self):
        self.packet["continuation_plan"]["steps"][0]["subskills"]=["unapproved"];self.update()
        with self.assertRaises(w.WorkflowError):self.check()
    def test_duplicate_candidate_rejected(self):
        self.packet["continuation_plan"]["steps"][1]["candidate_version"]="a-v1";self.update()
        with self.assertRaises(w.WorkflowError):self.check()
    def test_circular_or_future_dependency_rejected(self):
        self.packet["continuation_plan"]["steps"][0]["depends_on"]=["b"];self.update()
        with self.assertRaises(w.WorkflowError):self.check()
    def test_queue_failure_cannot_advance(self):
        (self.root/"logs/department-outbox").mkdir(parents=True)
        self.write("logs/department-outbox/a.json",{"status":"completed"})
        self.assertEqual(self.check()["next_step"]["step_id"],"a")
    def test_changed_frozen_result_rejected(self):
        self.queued();self.write("logs/department-outbox/a.json",{})
        with self.assertRaises(w.WorkflowError):self.check()
    def test_damaged_result_ledger_rejected(self):
        self.queued();p=w.result_handoff_path(self.root,self.task);p.write_text(p.read_text().replace("notification_queued","notification_sent"))
        with self.assertRaises(w.WorkflowError):self.check()

if __name__ == "__main__":
    unittest.main()
