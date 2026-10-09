"""Native local synthetic integration; no independent approval or production claim."""
import copy
import datetime as dt
import json
import unittest
from unittest import mock
from argparse import Namespace
import owner_direct_intake as direct
import result_coordination as coordination
import routine_authority as authority
import routine_grants as grants
import workflow_control as w
import test_department_upgrade as prior


class UpgradeV2Tests(unittest.TestCase):
    setUp = prior.DepartmentUpgradeIntegrationTests.setUp
    dispatch = prior.DepartmentUpgradeIntegrationTests.dispatch
    receipt = prior.DepartmentUpgradeIntegrationTests.receipt
    routing_decision = prior.DepartmentUpgradeIntegrationTests.routing_decision
    write = prior.DepartmentUpgradeIntegrationTests.write
    bind = prior.DepartmentUpgradeIntegrationTests.bind
    box = prior.DepartmentUpgradeIntegrationTests.box
    producer = prior.DepartmentUpgradeIntegrationTests.producer
    review = prior.DepartmentUpgradeIntegrationTests.review
    verdict = prior.DepartmentUpgradeIntegrationTests.verdict
    make_grant = prior.DepartmentUpgradeIntegrationTests.make_grant
    request = prior.DepartmentUpgradeIntegrationTests.request
    route_fixture = prior.DepartmentUpgradeIntegrationTests.route_fixture

    def test_exact_internal_close_records_actual_assistant_and_keeps_business_open(self):
        self.make_grant(accepted_scopes=[self.plan['scope']],accepted_candidate=self.pin,risk_level='R0')
        w.record_result_handoff(self.root,self.request())
        request=self.request('controller_decision',decision='close_scope',next_owner='content-organic-website',
            next_action='keep unrelated business queue open',qa_status='pass',acceptance_scope=self.plan['scope'],
            evidence_paths=[self.qa_path])
        row,_=w.record_result_handoff(self.root,request)
        self.assertEqual(row['actor_role'],'operations-assistant-2')
        self.assertTrue(row['delegated_bounded_authority'])
        self.assertFalse(row['business_goal_closed'])
        self.assertEqual(w.record_result_handoff(self.root,request)[0]['record_id'],row['record_id'])

    def test_close_cannot_expand_scope_or_use_changed_accepted_candidate(self):
        self.make_grant(accepted_scopes=[self.plan['scope']],accepted_candidate=self.pin,risk_level='R0')
        for scope in ['whole company',self.plan['scope']]:
            with self.subTest(scope=scope):
                if scope==self.plan['scope']:self.write(self.candidate,{'changed':'candidate'})
                with self.assertRaises(w.WorkflowError):
                    authority.check_special_decision(self.root,{'decision':'close_scope','qa_status':'pass',
                        'acceptance_scope':scope},grants._w().read_json(self.root/self.grant_path))

    def owner_request(self):
        now=dt.datetime.now(dt.timezone.utc).isoformat();role='content-organic-website'
        b=w.department_registry(self.root)[role]['chat_binding']
        return {'task_id':'owner-direct-v2','executor_role':role,'authorized_scope':'internal:owner-exact',
            'executor_binding':{k:b[k] for k in ('task_id','title','project_id','cwd')},
            'human_message':{'source':'human_user_message','message_id':'synthetic-real-human-reference',
                'thread_id':b['task_id'],'message_sha256':'b'*64,'authorized_at':now,'observed_at':now,
                'explicit_task_id':'owner-direct-v2','explicit_scope':'internal:owner-exact',
                'trusted_native_readback':True}}

    def test_owner_direct_enters_real_queue_without_dispatch_or_ack(self):
        request=self.owner_request();direct.intake(self.root,request)
        box=self.box('content-organic-website');box.update(task_id=request['task_id'],
            owner_authorization_message_id=request['human_message']['message_id'])
        path='logs/department-outbox/owner-direct-v2.json';self.write(path,box)
        result={'task_id':request['task_id'],'sender_department':'content-organic-website',
            'candidate_version':'v1','result_sha256':w.file_digest(self.root,path)['sha256'],
            'outbox_path':path,'event':'notification_queued','idempotency_key':'owner-direct-queue',
            'authorized_scope':request['authorized_scope'],'source_thread_id':'fixed-content-organic-website',
            'source_reply_sha256':'c'*64,'reply_observed_at':dt.datetime.now(dt.timezone.utc).isoformat()}
        row,_=w.record_result_handoff(self.root,result)
        self.assertEqual(row['source_mode'],'owner_direct')
        self.assertFalse(row['headquarters_dispatch_synthesized'])
        self.assertFalse(w.receipts_path(self.root,request['task_id']).exists())
        claimed=self.store.claim(coordination.exact_identity(result),'operations-assistant','assistant-one','owner-wake')
        self.assertTrue(claimed)

    def test_owner_intake_tampering_and_wrong_fixed_chat_are_denied(self):
        request=self.owner_request();wrong=copy.deepcopy(request);wrong['human_message']['thread_id']='other'
        with self.assertRaises(w.WorkflowError):direct.intake(self.root,wrong)
        direct.intake(self.root,request)
        path=direct.path_for(self.root,request['task_id']);value=w.read_json(path);value['authorized_scope']='broader'
        w.atomic_write_json(path,value)
        with self.assertRaises(w.WorkflowError):direct.existing(self.root,request['task_id'])

    def test_default_lanes_and_qa_return_to_original_coordinator(self):
        self.assertEqual(authority.default_lane('content-organic-website',kind='cms'),'operations-assistant-2')
        self.assertEqual(authority.default_lane('seo-content-research'),'operations-assistant')
        self.assertEqual(authority.default_lane('visual-design-video'),'operations-assistant-3')
        self.assertEqual(authority.default_lane('qa',parent_owner='operations-assistant-3'),'operations-assistant-3')
        with self.assertRaises(w.WorkflowError):authority.default_lane('qa')

    def test_delegate_without_current_claim_or_readiness_denied_by_native_policy(self):
        release={'task_id':self.task_id,'action_id':'release-v2','action_class':'site_publish',
            'scope':self.plan['scope'],'risk_level':'R2','candidate':self.pin,
            'permission_department':'content-organic-website','executor':'designated-website-developer'}
        self.make_grant(release=release)
        decision,_=w.policy_check(self.root,task_id=self.task_id,department='content-organic-website',
            action_id=release['action_id'],action_class='site_publish',scope=self.plan['scope'],
            delegate_actor_role='operations-assistant-2',delegate_grant=self.grant)
        self.assertEqual(decision['status'],'deny')
        self.assertIn('exact_admitted_policy_delegate_required',decision['reason'])
        self.assertEqual(decision['actor_role'],'operations-assistant-2')

    def prepare_site_release(self):
        # Control-adoption QA above remains intact; create a separate native professional task.
        self.routing_decisions={}
        self.task_id='site-release-v2';scope='flashcast.com.my:/en/services/kitchen'
        w.initialize_workflow(self.root,task_id=self.task_id,request='synthetic bounded code release',
            plan_status='ready_to_send',owner_approval_required=False,
            departments=[{'department':r,'chat_task_id':'fixed-'+r} for r in ['content-organic-website','qa']])
        self.candidate='drafts/site-release-v2/candidate.json';self.write(self.candidate,{'synthetic_code_diff':'one bounded change'})
        self.pin=w.file_digest(self.root,self.candidate)
        release={'task_id':self.task_id,'action_id':'publish-site-v2','action_class':'site_publish',
            'scope':scope,'risk_level':'R2','candidate':self.pin,'permission_department':'content-organic-website',
            'executor':'designated-website-developer'}
        gates={}
        for gate in ['facts','exact_diff','checks','backup','rollback','lawful_channel','current_version']:
            path='reports/site-release-v2-'+gate+'.json';self.write(path,{'synthetic_verified_gate':gate})
            gates[gate]={'status':'pass','evidence':[w.file_digest(self.root,path)]}
        readiness='drafts/site-release-v2/readiness.json'
        self.write(readiness,{k:release[k] for k in ['task_id','action_id','action_class','scope','risk_level','candidate']}|{'gates':gates})
        release['readiness']=w.file_digest(self.root,readiness)
        self.receipt('dispatch_sent','content-organic-website','site-send')
        self.receipt('chat_ack','content-organic-website','site-ack')
        self.source='logs/department-outbox/site-source-v2.json';self.write(self.source,self.box('content-organic-website'))
        self.receipt('outbox_received','content-organic-website','site-result',evidence=self.source)
        self.receipt('dispatch_sent','qa','site-qa-send');self.receipt('chat_ack','qa','site-qa-ack')
        box=self.box('qa');box.update(action_id=release['action_id'],action_class='site_code_candidate',scope=scope,
            risk_level='R2',candidate_path=self.candidate,candidate_sha256=self.pin['sha256'],release_readiness=release['readiness'])
        self.qa_path='logs/department-outbox/site-qa-v2.json';self.write(self.qa_path,box)
        self.receipt('outbox_received','qa','site-qa-outbox',evidence=self.qa_path)
        self.receipt('qa_verdict','qa','site-qa-verdict',verdict='pass',evidence=self.qa_path,
            action_id=release['action_id'],action_class='site_code_candidate',scope=scope)
        policy=w.load_policy(self.root);policy['standing_authorizations']=[{
            'authorization_id':'synthetic-standing-site','status':'active','source_message_ref':'synthetic-human-standing',
            'department':'content-organic-website','action_classes':['site_publish'],'allowed_scope_prefixes':['flashcast.com.my:']}]
        self.write('data/action-policy.json',policy)
        self.base={'task_id':self.task_id,'sender_department':'content-organic-website','candidate_version':'v1',
            'outbox_path':self.source,'result_sha256':w.file_digest(self.root,self.source)['sha256'],'scope':scope}
        self.identity=coordination.exact_identity(self.base)
        w.record_result_handoff(self.root,{**self.base,'event':'notification_queued','idempotency_key':'site-queue'})
        self.plan={'scope':scope};self.make_grant(release=release,risk_level='R2')
        return release

    def test_native_r2_proxy_is_exact_idempotent_and_does_not_consume_or_publish(self):
        release=self.prepare_site_release();request=self.request(release=release)
        value=authority.proxy_auto_release(self.root,self.grant,'operations-assistant-2',request)
        self.assertEqual(value['status'],'AUTO_RELEASE_ARRANGED')
        self.assertFalse(value['permission_consumed']);self.assertFalse(value['external_write_executed'])
        again=authority.proxy_auto_release(self.root,self.grant,'operations-assistant-2',request)
        self.assertEqual(again['policy_decision_id'],value['policy_decision_id'])
        native=[r for r in w.read_jsonl(self.root/w.POLICY_DECISIONS) if r.get('delegate_grant')==self.grant]
        self.assertEqual(len(native),1);self.assertEqual(native[0]['actor_role'],'operations-assistant-2')
        self.assertEqual(native[0]['approval_status'],'active')

    def test_r2_readiness_changed_and_r3_escalate_without_release(self):
        release=self.prepare_site_release();request=self.request(release=release)
        self.write(release['readiness']['path'],{'changed':'readiness'})
        with self.assertRaises(w.WorkflowError):authority.proxy_auto_release(self.root,self.grant,'operations-assistant-2',request)
        self.assertFalse(any(r.get('status')=='AUTO_RELEASE_ARRANGED' for r in w.read_jsonl(self.root/w.POLICY_DECISIONS)))

    def test_admitted_result_queue_releases_hq_but_stale_grant_returns_to_hq(self):
        policy=w.load_policy(self.root);policy['department_system_upgrade']['result_grants']={coordination._key(self.identity):self.grant}
        self.write('data/action-policy.json',policy)
        queue=w.result_handoff_pending(self.root);view=authority.partition_queue(self.root,queue)
        self.assertEqual(view['pending_count'],queue['pending_count']);self.assertEqual(view['headquarters_pending_count'],queue['pending_count']-1)
        self.assertEqual(view['assistant_ready_results'][0]['coordinator_role'],'operations-assistant-2')
        self.write(self.grant_path,{'tampered':'grant'})
        self.assertEqual(authority.partition_queue(self.root,queue)['headquarters_pending_count'],queue['pending_count'])

    def test_real_ack_releases_short_lease_and_preserves_next_owner(self):
        route,request=self.route_fixture()
        decision,_=w.policy_check(self.root,task_id=route['task_id'],department=route['sender_department'],
            action_id=route['action_id'],action_class=route['action_class'],scope=route['scope'],
            **{k:v for k,v in route.items() if k not in {'task_id','action_id','action_class','scope','sender_department'}})
        reserved=grants.reserve_route(self.root,self.grant,'operations-assistant-2',request)
        proof={'source':'trusted_native_send_readback','reservation_id':reserved['reservation_id'],
            'message_sent':True,'target_thread_id':route['target_thread_id'],'payload_sha256':route['payload_sha256'],
            'message_id':'synthetic-native-v2','actor_thread_id':'fixed-operations-assistant-2','nonempty':True,'observed_at':dt.datetime.now(dt.timezone.utc).isoformat()}
        grants.commit_route(self.root,self.grant,'operations-assistant-2',proof)
        fields=dict(task_id=route['task_id'],department=route['target_department'],chat_task_id=route['target_thread_id'],
            action_id=route['action_id'],action_class=route['action_class'],scope=route['scope'],
            evidence='',verdict='',policy_decision_id=decision['decision_id'],ack_nonempty=False)
        w.record_receipt(self.root,Namespace(**fields,receipt_type='dispatch_sent',idempotency_key='v2-native-dispatch'))
        fields.update(ack_nonempty=True)
        ack,_=w.record_receipt(self.root,Namespace(**fields,receipt_type='chat_ack',idempotency_key='v2-native-ack'))
        self.assertNotIn('coordination_release_pending',ack)
        self.assertTrue(ack['coordination_continuation']['claim_released'])
        self.assertEqual(ack['coordination_continuation']['next_owner'],'content-organic-website')
        after=self.store.claim(self.identity,'operations-assistant-3','assistant-three','parallel-other-result')
        self.assertEqual(after['role'],'operations-assistant-3')

    def test_owner_direct_real_delivery_can_enter_independent_qa_without_fake_ack(self):
        self.test_owner_direct_enters_real_queue_without_dispatch_or_ack()
        result=direct.prepare_review(self.root,'owner-direct-v2')
        self.assertFalse(result['dispatch_sent_created']);self.assertFalse(result['chat_ack_created'])
        rows,invalid=w._validate_receipt_chain(self.root,'owner-direct-v2')
        self.assertFalse(invalid);self.assertEqual([r['receipt_type'] for r in rows],['outbox_received'])
        self.task_id='owner-direct-v2';self.routing_decisions={}
        self.receipt('dispatch_sent','qa','owner-qa-send');self.receipt('chat_ack','qa','owner-qa-ack')
        path='logs/department-outbox/owner-direct-v2-qa.json';self.write(path,self.box('qa'))
        self.receipt('outbox_received','qa','owner-qa-outbox',evidence=path)
        self.receipt('qa_verdict','qa','owner-qa-verdict',evidence=path,verdict='pass')
        rows,invalid=w._validate_receipt_chain(self.root,self.task_id)
        self.assertFalse(invalid);self.assertFalse(any(r['receipt_type']=='chat_ack' and r['department']=='content-organic-website' for r in rows))

    def test_proxy_interruption_recovers_native_policy_once_without_reissue(self):
        release=self.prepare_site_release();request=self.request(release=release)
        original=w.atomic_write_json
        def crash(path,value):
            if 'routine-release' in str(path):raise OSError('simulated process interruption after native policy append')
            return original(path,value)
        with mock.patch.object(w,'atomic_write_json',side_effect=crash):
            with self.assertRaises(OSError):authority.proxy_auto_release(self.root,self.grant,'operations-assistant-2',request)
        value=authority.recover_proxy_release(self.root,self.grant,'operations-assistant-2',request)
        self.assertTrue(value['recovered_from_native_policy_readback'])
        self.assertEqual(len([r for r in w.read_jsonl(self.root/w.POLICY_DECISIONS) if r.get('delegate_grant')==self.grant]),1)

    def test_r3_and_ads_proxy_requests_escalate_before_policy_effect(self):
        release=self.prepare_site_release()
        for action,risk in [('site_publish','R3'),('ads_write','R2'),('cms_write','R2')]:
            updated={**release,'action_class':action,'risk_level':risk}
            self.make_grant(release=updated)
            with self.assertRaises(w.WorkflowError):
                authority.proxy_auto_release(self.root,self.grant,'operations-assistant-2',self.request(release=updated))
        self.assertFalse(any(r.get('delegate_grant') for r in w.read_jsonl(self.root/w.POLICY_DECISIONS)))


if __name__=='__main__':unittest.main()
