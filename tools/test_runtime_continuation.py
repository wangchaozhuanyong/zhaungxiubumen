"""Real native queues + atomic ownership + repaired read-only continuation."""
import datetime as dt
import unittest
import workflow_control as w
import department_next_work as next_work
import result_coordination as coordination
import test_runtime_qa_admission as qa_fixture


class RuntimeContinuation(unittest.TestCase):
    def setUp(self):
        self.fixture=qa_fixture.ExactRuntimeQA("runTest");self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown);self.root=self.fixture.root;self.task=self.fixture.task_id
        self.dep="content-organic-website";self.now=dt.datetime.now(dt.timezone.utc)
        bind=w.department_registry(self.root)[self.dep]["chat_binding"]
        self.packet={"task_id":self.task,"department":self.dep,"project_id":bind["project_id"],
                     "fixed_chat_task_id":bind["task_id"],"continuation_plan":{
                         "version":1,"mode":"same_task_local_r0_only","external_actions_allowed":False,
                         "expires_at":(self.now+dt.timedelta(hours=1)).isoformat(),"steps":[
                             {"step_id":sid,"candidate_version":sid+"-v1","scope":"project:test:"+sid,
                              "kind":"local_candidate","inputs":[],"output_dir":f"drafts/operations/{self.task}/{sid}-v1",
                              "depends_on":["a"] if sid=="b" else [],"subskills":[],"requires_controller_gate":False}
                             for sid in ["a","b","c"]]}}
        self.path="logs/handoffs/workpack.json";self.fixture.write(self.path,self.packet)
        self.fixture.receipt("dispatch_sent",self.dep,"original-pack-send",evidence=self.path)
        self.fixture.receipt("chat_ack",self.dep,"original-pack-ACK")
        self.live={"observed_at":self.now.isoformat(),"threads":[{"id":bind["task_id"],"projectId":bind["project_id"],
                    "title":bind["title"],"cwd":bind["cwd"]}],"sections":[{"id":bind["sidebar_section_id"],
                    "name":"装修公司部门","itemKeys":["codex:thread:local:"+bind["task_id"]]}]}
        self.store=coordination.CoordinationStore(self.root);self.addCleanup(self.store.close)

    def inspect(self):
        return next_work.inspect(self.root,self.path,self.live)

    def queue(self,status="completed"):
        box=self.fixture.box(self.dep);box.update(candidate_version="a-v1",status=status,scope="project:test:a")
        box["step_binding"]=next_work.make_step_binding(self.root,self.packet,self.packet["continuation_plan"]["steps"][0],
                                                       w.file_digest(self.root,self.path)["sha256"])
        path="logs/department-outbox/step-a.json";self.fixture.write(path,box)
        self.fixture.receipt("outbox_received",self.dep,"step-a-result",evidence=path)
        self.identity={"task_id":self.task,"sender_department":self.dep,"candidate_version":"a-v1",
                       "result_sha256":w.file_digest(self.root,path)["sha256"]}
        self.request={**self.identity,"outbox_path":path}
        result,_=w.record_result_handoff(self.root,dict(self.request,event="notification_queued",idempotency_key="queue-a"))
        return result

    def own(self,status):
        claim=self.store.claim(self.identity,"operations-assistant","assistant-test","wake-a")
        draft=self.store.precheck(self.identity,"operations-assistant","assistant-test",claim,status,
                    "operations","verify exact queued result","fixed QA or legal external input",scope="project:test:a")
        self.assertFalse(draft["precheck"]["controller_decision_recorded"])
        return claim

    def test_complete_real_queue_releases_dependency_under_assistant_lease(self):
        self.queue();self.own("completed");answer=self.inspect()
        self.assertEqual(answer["step_states"]["a"],"done")
        self.assertEqual(answer["next_step"]["step_id"],"b")
        self.assertFalse(answer["external_permission_issued"])
        before=w.read_jsonl(w.result_handoff_path(self.root,self.task))
        self.assertEqual(answer,self.inspect());self.assertEqual(before,w.read_jsonl(w.result_handoff_path(self.root,self.task)))

    def test_partial_real_queue_keeps_dependency_and_continues_independent(self):
        self.queue("partial");self.own("partial");answer=self.inspect()
        self.assertEqual(answer["step_states"]["a"],"blocked_or_partial")
        self.assertEqual(answer["next_step"]["step_id"],"c")
        self.assertEqual(answer["dependency_waits"],[{"step_id":"b","waiting_on":["a"]}])

    def test_qa_rework_owned_draft_never_releases_dependency(self):
        self.queue("blocked");self.own("qa_rework")
        self.assertEqual(self.inspect()["next_step"]["step_id"],"c")
        self.assertFalse(self.inspect()["business_goal_closed"])

    def test_external_blocked_owned_draft_never_grants_permission(self):
        self.queue("needs_input");self.own("external_blocked")
        self.assertEqual(self.inspect()["step_states"]["a"],"blocked_or_partial")
        self.assertFalse(self.inspect()["external_permission_issued"])

    def test_queue_failed_recovers_existing_output_without_speculative_claim(self):
        output=self.root/self.packet["continuation_plan"]["steps"][0]["output_dir"];output.mkdir(parents=True)
        self.assertEqual(self.inspect()["mode"],"RECOVER_EXISTING_OUTPUT")
        identity={"task_id":self.task,"sender_department":self.dep,"candidate_version":"a-v1","result_sha256":"a"*64}
        with self.assertRaises(w.WorkflowError):self.store.claim(identity,"operations-assistant","assistant-test","failed-queue")
        self.assertEqual(self.store.conn.execute("SELECT COUNT(*) FROM claims").fetchone()[0],0)


if __name__=="__main__":unittest.main()
