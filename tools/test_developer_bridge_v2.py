import copy
import datetime as dt
import unittest
import developer_bridge as bridge
import workflow_control as w
import test_runtime_qa_admission as runtime


class DeveloperBridgeV2Tests(unittest.TestCase):
    setUp=runtime.ExactRuntimeQA.setUp
    tearDown=runtime.ExactRuntimeQA.tearDown
    dispatch=runtime.ExactRuntimeQA.dispatch
    receipt=runtime.ExactRuntimeQA.receipt
    routing_decision=runtime.ExactRuntimeQA.routing_decision
    write=runtime.ExactRuntimeQA.write
    bind=runtime.ExactRuntimeQA.bind
    box=runtime.ExactRuntimeQA.box
    producer=runtime.ExactRuntimeQA.producer
    review=runtime.ExactRuntimeQA.review
    verdict=runtime.ExactRuntimeQA.verdict

    def request(self,status='active'):
        self.write('drafts/bridge-authority.json',{'source':'current_human_message',
            'original_software_task_id':'fc-20261008-department-system-upgrade-v1'})
        self.write('drafts/bridge-packet.json',{'original_task':'fc-20261008-department-system-upgrade-v1','bounded':'v9 rework'})
        packet=w.file_digest(self.root,'drafts/bridge-packet.json')
        policy=w.load_policy(self.root);binding=w.department_registry(self.root)['operations']['chat_binding']
        req={**bridge.DEVELOPER,'task_id':'developer-route-any-v9','scope':'owner_project_handoff:developer-route-any-v9',
            'sender_department':'operations','action_id':'send-v9','target_department':'designated-website-developer',
            'source_project_id':policy['routing_policy']['source_project_id'],'target_sidebar_section_id':'real-custom-group',
            'owner_authorization_ref':'drafts/bridge-authority.json',
            'owner_authorization_sha256':w.file_digest(self.root,'drafts/bridge-authority.json')['sha256'],
            'packet_path':packet['path'],'packet_sha256':packet['sha256'],'payload_sha256':packet['sha256'],
            'production_authority_granted':False,'live_identity_path':'drafts/bridge-live.json',
            'native_send_receipt_path':'logs/bridge-sent.json','native_attempt_receipt_path':'logs/bridge-attempt.json'}
        live={'observed_at':dt.datetime.now(dt.timezone.utc).isoformat(),
            'pinnedThreads':[{'id':bridge.DEVELOPER['target_thread_id'],'projectId':bridge.DEVELOPER['target_project_id'],
                'title':bridge.DEVELOPER['target_thread_title'],'cwd':bridge.DEVELOPER['target_cwd'],'status':status}],
            'threads':[{'id':binding['task_id'],'projectId':binding['project_id'],'cwd':str(self.root),
                'title':binding['title'],'status':'active'}],
            'sections':[{'id':'real-custom-group','itemKeys':['codex:project:'+bridge.DEVELOPER['target_project_id']]}]}
        self.write('drafts/bridge-request.json',req);self.write(req['live_identity_path'],live)
        return req,w.file_digest(self.root,'drafts/bridge-request.json'),live

    def test_readonly_candidate_review_accepts_actual_group_and_active_target_before_send(self):
        request,pin,live=self.request()
        result=bridge.review_candidate(self.root,pin,live)
        self.assertTrue(result['qa_review_eligible']);self.assertFalse(result['activated']);self.assertFalse(result['sent'])
        self.assertFalse((self.root/request['native_send_receipt_path']).exists())

    def test_duplicate_inventory_wrong_group_stale_and_changed_request_deny(self):
        request,pin,live=self.request()
        variants=[]
        d=copy.deepcopy(live);d['threads'].append(d['pinnedThreads'][0]);variants.append(d)
        d=copy.deepcopy(live);d['sections'][0]['id']='old-pinned-assumption';variants.append(d)
        d=copy.deepcopy(live);d['observed_at']=(dt.datetime.now(dt.timezone.utc)-dt.timedelta(minutes=6)).isoformat();variants.append(d)
        for d in variants:
            with self.assertRaises(w.WorkflowError):bridge.review_candidate(self.root,pin,d)
        self.write(pin['path'],{**request,'target_cwd':'/other/project'})
        with self.assertRaises(w.WorkflowError):bridge.review_candidate(self.root,pin,live)

    def test_native_control_qa_binds_current_request_without_literal_version_or_prior_send(self):
        request,pin,live=self.request('idle')
        self.write(self.candidate,{**w.read_json(self.root/self.candidate),'request':pin,'production_write_allowed':False})
        self.pin=w.file_digest(self.root,self.candidate)
        self.plan.update(candidate=self.pin,candidate_sha256=self.pin['sha256'])
        self.bind();self.producer()
        self.review(qa_result='PASS_INTERNAL_APPLICATION_ALLOWED',candidate_path=self.candidate,candidate_sha256=self.pin['sha256'])
        qa=self.verdict();outbox=w.file_digest(self.root,self.qa_path)
        accepted={'task_id':self.task_id,'qa_department':'qa-technical','qa_receipt_id':qa['receipt_id'],
            'qa_outbox_path':outbox['path'],'qa_outbox_sha256':outbox['sha256'],
            'candidate_path':self.candidate,'candidate_sha256':self.pin['sha256']}
        self.write('drafts/bridge-acceptance.json',accepted)
        acceptance=w.file_digest(self.root,'drafts/bridge-acceptance.json')
        policy=w.load_policy(self.root);policy['routing_policy']['owner_directed_code_handoff']={
            'status':'approved_single_use','request_path':pin['path'],'request_sha256':pin['sha256'],
            'control_acceptance_path':acceptance['path'],'control_acceptance_sha256':acceptance['sha256']}
        routing={k:request[k] for k in ['task_id','sender_department','action_id','scope','source_project_id',
            'target_project_id','target_department','target_thread_id','target_thread_title','target_cwd',
            'target_sidebar_section_id','payload_sha256']}|{'action_class':'thread_message'}
        reasons,_=bridge.precheck(self.root,routing,policy)
        self.assertEqual(reasons,[])
        self.assertFalse((self.root/request['native_send_receipt_path']).exists())
        self.write(request['native_attempt_receipt_path'],{'uncertain':True})
        self.assertTrue(bridge.precheck(self.root,routing,policy)[0])


if __name__=='__main__':unittest.main()
