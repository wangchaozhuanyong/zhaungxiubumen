import copy
import datetime as dt
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import workflow_control as w
import flashcast_ops as ops
import department_flow_reconcile as m


class FlowChecks(unittest.TestCase):
    def setUp(self):
        test_base = Path(os.environ.get('FLASHCAST_FLOW_TEST_BASE', str(Path(__file__).resolve().parents[1]/'.test-tmp')))
        test_base.mkdir(parents=True, exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=test_base)
        self.root = Path(self.tmp.name)
        (self.root / 'data').mkdir()
        self.at = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=5)
        self.binding = {'task_id': 'fixed-pub', 'project_id': 'fixture-project', 'cwd': str(self.root),
                        'title': 'Fixture PUB', 'sidebar_section_id': 'fixture-group', 'status': 'bound_and_visible',
                        'dispatch_eligible': True, 'reply_health': 'healthy_visible_reply_verified',
                        'last_run_status': 'success', 'last_verified_at': (self.at - dt.timedelta(days=3)).isoformat(),
                        'last_health_check_at': (self.at - dt.timedelta(days=3)).isoformat()}
        self.registry = {'departments': [{'id': 'publishing', 'new_dispatch_enabled': True, 'mode': 'worker', 'chat_binding': self.binding},
                                        {'id': 'sales', 'new_dispatch_enabled': True, 'mode': 'worker', 'chat_binding': {**self.binding, 'task_id': 'fixed-sales'}}],
                         'health_policy': {'verification_ttl_hours': 26},
                         'collaboration_bindings': {'designated-development': {'thread_id': 'fixed-web', 'title': 'Fixture WEB',
                              'cwd': str(self.root / 'website'), 'project_id': 'fixture-web-project', 'host_id': 'local'}}}
        self.write('data/department-registry.json', self.registry)
        self.native = {'thread': {'id': 'fixed-pub', 'title': 'Fixture PUB', 'cwd': str(self.root),
                                  'projectId': 'fixture-project', 'hostId': 'local', 'status': {'type': 'idle'}},
                       'turns': [{'id': 'turn-pub', 'status': 'completed', 'error': None, 'completedAt': self.at.timestamp(),
                                  'items': [{'type': 'agentMessage', 'phase': 'final_answer', 'id': 'msg-pub', 'text': 'actual fixture final'}]}]}
        self.pin = self.write('native.json', self.native)
        self.health = {'schema': m.HEALTH_SCHEMA, 'observations': [{'department': 'publishing', 'native': self.pin}]}
        self.manifest = self.write('manifest.json', self.health)
        self.goal = {'goal_key': 'original-en2', 'original_task_refs': [m.TASK], 'professional_owner': 'publishing',
                     'final_goal_closed': False, 'next_actor': 'old', 'latest_updated_at_UTC': (self.at-dt.timedelta(hours=1)).isoformat()}
        self.index = {'open_goals': [self.goal], 'HQ_parallel_wip': {'preserve': True}}
        self.write('data/operations-goal-followthrough.json', self.index)
        self.report = {'schema': 'actual-original-WEB-EN2-protected-preview-readiness-result/v1', 'task_id': m.TASK,
                       'scope': m.SCOPE, 'business_owner': 'publishing', 'WEB_executor': 'designated-development',
                       'normal_preview_request': 'ACTUAL_REFUSED: autonomous delivery: external WEB: registered operation',
                       'business_goal_closed': False, 'production_READY': False, 'preview_completed': False,
                       'at_UTC': (self.at-dt.timedelta(seconds=10)).isoformat(),
                       'effects': {k: 0 for k in ['workflow_dispatch','reserve','issue','consume','preflight_record',
                           'policy_allow_or_consume','CMS_Save','push_PR_merge_deploy','cancel_reissue_TTL_change','other_thread_message_or_activation']}}
        module = self.root/'tools/professional_web_execution.py'
        module.parent.mkdir();module.write_text('# original fixture source')
        self.module_pin = w.file_digest(self.root, str(module))
        self.write('ACTUAL-NORMAL-PREVIEW-ENTRY-READONLY-PROBE.json', {'module': self.module_pin})
        self.report_pin = self.write('report.json', self.report)
        self.web = copy.deepcopy(self.native)
        self.web['thread'] = {'id': 'fixed-web', 'title': 'Fixture WEB', 'cwd': str(self.root/'website'), 'hostId': 'local', 'projectId': 'fixture-web-project'}
        self.web['turns'][0]['items'][0]['text'] = 'Actual result [' + str(self.root/'report.json') + ']'
        self.web_pin = self.write('web.json', self.web)
        self.handoff = {'schema': m.HANDOFF_SCHEMA, 'task_id': m.TASK, 'native': self.web_pin,
                        'report': self.report_pin, 'expected_goal_sha256': w.sha256_value(self.goal)}
        self.handoff_pin = self.write('handoff.json', self.handoff)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name, data):
        p = self.root/name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(data, ensure_ascii=False))
        return w.file_digest(self.root, name)

    def update_native(self):
        self.health['observations'][0]['native'] = self.write('native.json', self.native)
        self.manifest = self.write('manifest.json', self.health)

    def saved(self):
        return json.loads((self.root/'data/department-registry.json').read_text())

    def test_default_health_check_only_does_not_write(self):
        before = (self.root/'data/department-registry.json').read_bytes()
        result = m.sync_health(self.root, self.manifest)
        self.assertEqual(result['status'], 'verified')
        self.assertFalse(result['writes_performed'])
        self.assertEqual(before, (self.root/'data/department-registry.json').read_bytes())
        self.assertFalse((self.root/'logs').exists())

    def test_real_fixture_health_consumption_preserves_original_time_and_unrelated_role(self):
        sales = copy.deepcopy(self.registry['departments'][1])
        result = m.sync_health(self.root, self.manifest, check_only=False)
        self.assertTrue(result['writes_performed'])
        actual = self.saved()['departments'][0]['chat_binding']
        self.assertEqual(actual['last_verified_at'], self.at.isoformat())
        self.assertEqual(actual['last_health_check_at'], self.at.isoformat())
        self.assertEqual(self.saved()['departments'][1], sales)
        self.assertNotIn('actual fixture final', (self.root/'logs/department-health.jsonl').read_text())

    def test_repeated_same_observation_is_idempotent(self):
        m.sync_health(self.root, self.manifest, check_only=False)
        before = (self.root/'logs/department-health.jsonl').read_bytes()
        result = m.sync_health(self.root, self.manifest, check_only=False)
        self.assertFalse(result['writes_performed'])
        self.assertEqual(before, (self.root/'logs/department-health.jsonl').read_bytes())

    def test_later_failed_terminal_blocks_old_success(self):
        self.native['turns'].append({'id': 'failed-newer', 'status': 'failed', 'error': {'message': 'fixture'},
                                     'completedAt': (self.at+dt.timedelta(seconds=1)).timestamp(), 'items': []})
        self.update_native()
        self.assertEqual(m.sync_health(self.root, self.manifest)['status'], 'partial_blocked')

    def test_new_success_recovers_after_older_failed_terminal(self):
        self.native['turns'].append({'id': 'older-failure', 'status': 'failed', 'error': 'fixture',
            'completedAt': (self.at-dt.timedelta(seconds=1)).timestamp(), 'items': []})
        self.update_native()
        self.assertEqual(m.sync_health(self.root, self.manifest)['status'], 'verified')

    def test_newer_active_turn_does_not_discard_latest_success(self):
        self.native['turns'].insert(0, {'id': 'active', 'status': 'inProgress', 'items': []})
        self.update_native()
        self.assertEqual(m.sync_health(self.root, self.manifest)['status'], 'verified')

    def test_latest_empty_final_cannot_fallback_to_older_success(self):
        new = copy.deepcopy(self.native['turns'][0]);new.update(id='new', completedAt=(self.at+dt.timedelta(seconds=1)).timestamp())
        new['items'][0]['text'] = ''
        self.native['turns'].insert(0, new);self.update_native()
        self.assertEqual(m.sync_health(self.root, self.manifest)['status'], 'partial_blocked')

    def test_missing_or_ambiguous_terminal_time_rejected(self):
        for turn in [{'id':'bad','status':'failed','error':'failure'}, copy.deepcopy(self.native['turns'][0])]:
            old = copy.deepcopy(self.native['turns']);self.native['turns'].append(turn);self.update_native()
            self.assertEqual(m.sync_health(self.root, self.manifest)['status'], 'partial_blocked')
            self.native['turns'] = old

    def test_expired_or_future_reply_is_not_refreshed(self):
        for delta in [dt.timedelta(hours=-27), dt.timedelta(minutes=2)]:
            self.native['turns'][0]['completedAt'] = (dt.datetime.now(dt.timezone.utc)+delta).timestamp();self.update_native()
            self.assertEqual(m.sync_health(self.root, self.manifest)['status'], 'partial_blocked')

    def test_wrong_identity_and_tampered_pin_are_rejected(self):
        self.native['thread']['id']='unrelated';self.update_native()
        self.assertEqual(m.sync_health(self.root, self.manifest)['status'], 'partial_blocked')
        self.native['thread']['id']='fixed-pub';self.write('native.json',self.native)
        self.assertEqual(m.sync_health(self.root, self.manifest)['status'], 'partial_blocked')

    def test_retired_role_cannot_restore_health(self):
        self.registry['departments'][0].update(mode='retired_history',new_dispatch_enabled=False)
        self.write('data/department-registry.json',self.registry)
        self.assertEqual(m.sync_health(self.root, self.manifest)['status'], 'partial_blocked')

    def test_duplicate_role_manifest_rejects_before_any_writes(self):
        self.health['observations'] *= 2
        pin = self.write('manifest.json', self.health)
        before=(self.root/'data/department-registry.json').read_bytes()
        with self.assertRaises(w.WorkflowError):m.sync_health(self.root,pin,check_only=False)
        self.assertEqual(before,(self.root/'data/department-registry.json').read_bytes())

    def test_bad_role_is_isolated_without_suppressing_valid_role(self):
        self.health['observations'].append({'department':'sales','native':self.pin})
        pin=self.write('manifest.json',self.health)
        result=m.sync_health(self.root,pin,check_only=False)
        self.assertEqual(result['status'],'partial_blocked')
        self.assertEqual(self.saved()['departments'][0]['chat_binding']['last_verified_at'],self.at.isoformat())
        self.assertEqual(self.saved()['departments'][1],self.registry['departments'][1])

    def test_older_evidence_cannot_overwrite_newer_success_or_failure(self):
        for failure in [False,True]:
            self.binding['last_verified_at']=(self.at+dt.timedelta(seconds=1)).isoformat()
            if failure:self.binding.update(last_run_status='failed',last_health_check_at=(self.at+dt.timedelta(seconds=2)).isoformat())
            self.write('data/department-registry.json',self.registry)
            before=(self.root/'data/department-registry.json').read_bytes()
            result=m.sync_health(self.root,self.manifest,check_only=False)
            self.assertEqual(result['status'],'partial_blocked')
            self.assertEqual(before,(self.root/'data/department-registry.json').read_bytes())

    def test_readonly_check_also_rejects_older_evidence(self):
        self.binding['last_verified_at'] = (self.at + dt.timedelta(seconds=1)).isoformat()
        self.write('data/department-registry.json', self.registry)
        self.assertEqual(m.sync_health(self.root, self.manifest)['status'], 'partial_blocked')

    def health_args(self):
        import argparse, hashlib
        return argparse.Namespace(department='publishing', **{k:self.binding[k] for k in
            ['task_id','project_id','cwd','title','sidebar_section_id']},
            reply_ref='msg-pub', reply_sha256=hashlib.sha256(b'actual fixture final').hexdigest(),
            reply_nonempty=True, reply_observed_at=self.at.isoformat(), native_reply_evidence='native.json',
            live_status='idle',last_run_status='success',failure_class='',next_retry_at='')

    def test_direct_health_record_cannot_revive_disabled_role(self):
        self.registry['departments'][0]['new_dispatch_enabled'] = False
        self.write('data/department-registry.json', self.registry)
        with self.assertRaises(ops.OpsError):ops.department_health_record(self.root,self.health_args())

    def test_direct_health_record_cannot_use_old_success_after_failure(self):
        self.native['turns'].append({'id':'new-failure','status':'failed','error':'fixture',
            'completedAt':(self.at+dt.timedelta(seconds=1)).timestamp(),'items':[]})
        self.update_native()
        with self.assertRaises(ops.OpsError):ops.department_health_record(self.root,self.health_args())

    def test_lock_rechecks_role_and_preserves_parallel_unrelated_edit(self):
        from contextlib import contextmanager
        @contextmanager
        def concurrent_edit(root):
            current=self.saved();current['departments'][1]['parallel_WIP']='keep'
            self.write('data/department-registry.json',current)
            yield
        with patch.object(w,'workflow_lock',side_effect=concurrent_edit):
            self.assertEqual(m.sync_health(self.root,self.manifest,check_only=False)['status'],'verified')
        self.assertEqual(self.saved()['departments'][1]['parallel_WIP'],'keep')

    def test_role_retired_during_validation_is_not_overwritten(self):
        from contextlib import contextmanager
        @contextmanager
        def retire(root):
            current=self.saved();current['departments'][0].update(mode='retired_history',new_dispatch_enabled=False)
            self.write('data/department-registry.json',current)
            yield
        with patch.object(w,'workflow_lock',side_effect=retire):
            self.assertEqual(m.sync_health(self.root,self.manifest,check_only=False)['status'],'partial_blocked')
        self.assertFalse(self.saved()['departments'][0]['new_dispatch_enabled'])

    def test_status_explicitly_consumes_existing_evidence_before_gate(self):
        def status(root):
            return {'fresh':w._chat_binding_healthy(self.saved()['departments'][0]['chat_binding'],verification_ttl_hours=26)},[]
        with patch.object(ops,'department_status',side_effect=status):
            result,_=ops.department_status_with_health(self.root,'manifest.json')
        self.assertTrue(result['fresh'])
        self.assertEqual(result['health_evidence_consumption']['provider_calls'],0)

    def test_handoff_is_precise_readonly_CAS_proposal(self):
        before=(self.root/'data/operations-goal-followthrough.json').read_bytes()
        result=m.plan_en2_handoff(self.root,self.handoff_pin)
        self.assertEqual(result['patch']['next_actor'],'system-development')
        self.assertEqual(result['patch']['latest_handoff_reconciliation']['business_owner'],'publishing')
        self.assertFalse(result['writes_performed']);self.assertIsNone(result['apply_entry'])
        self.assertNotIn('dispatch_state',result['patch'])
        self.assertEqual(before,(self.root/'data/operations-goal-followthrough.json').read_bytes())

    def test_handoff_does_not_overwrite_changed_HQ_goal(self):
        self.goal['next_actor']='HQ parallel update';self.write('data/operations-goal-followthrough.json',self.index)
        with self.assertRaises(w.WorkflowError):m.plan_en2_handoff(self.root,self.handoff_pin)

    def test_handoff_rejects_newer_goal_or_pause(self):
        for key,value in [('latest_updated_at_UTC',(self.at+dt.timedelta(seconds=1)).isoformat()),('user_paused',True)]:
            old=copy.deepcopy(self.goal);self.goal[key]=value;self.write('data/operations-goal-followthrough.json',self.index)
            self.handoff['expected_goal_sha256']=w.sha256_value(self.goal);pin=self.write('handoff.json',self.handoff)
            with self.assertRaises(w.WorkflowError):m.plan_en2_handoff(self.root,pin)
            self.goal.clear();self.goal.update(old)

    def test_handoff_rejects_effect_or_unknown(self):
        for value in [1,'UNKNOWN',False]:
            self.report['effects']['workflow_dispatch']=value
            self.handoff['report']=self.write('report.json',self.report);pin=self.write('handoff.json',self.handoff)
            with self.assertRaises(w.WorkflowError):m.plan_en2_handoff(self.root,pin)

    def partial_SYS_report(self):
        fixed = {'id':'fixed-sys','title':'Fixture SYS','cwd':str(self.root),'hostId':'local','projectId':'fixture-project'}
        self.registry['departments'].append({'id':'system-development','chat_binding':{
            'task_id':fixed['id'],'title':fixed['title'],'cwd':fixed['cwd'],'host_id':'local','project_id':'fixture-project'}})
        self.write('data/department-registry.json',self.registry)
        p=self.root/'tools/en2_preview_entry.py';p.write_text('# fail closed fixture')
        report={'state':'PARTIAL_ADOPTED_FAIL_CLOSED_NOT_EXECUTABLE','at_utc':self.report['at_UTC'],
            'installed':{name:w.file_digest(self.root,name)['sha256'] for name in
                ['tools/professional_web_execution.py','tools/en2_preview_entry.py']},
            'effects':{key:False for key in ['policy_issued','permit_issued','workflow_run','CMS_Save','cross_thread_message']},
            'still_missing':['normal policy and once-only transport']}
        self.handoff['report']=self.write('report.json',report)
        self.web['thread']=fixed;self.handoff['native']=self.write('web.json',self.web)
        return report

    def test_old_WEB_refusal_cannot_override_changed_entry(self):
        (self.root/'tools/professional_web_execution.py').write_text('# parallel source already repaired')
        with self.assertRaises(w.WorkflowError):m.plan_en2_handoff(self.root,self.handoff_pin)

    def test_current_partial_SYS_successor_keeps_original_owner_and_stops_PUB_refresh(self):
        self.partial_SYS_report();pin=self.write('handoff.json',self.handoff)
        result=m.plan_en2_handoff(self.root,pin)
        self.assertEqual(result['patch']['observed_state'],'EN2_PROTECTED_PREVIEW_LOCAL_CHAIN_INCOMPLETE')
        self.assertEqual(result['patch']['next_actor'],'system-development')
        self.assertEqual(result['patch']['latest_handoff_reconciliation']['business_owner'],'publishing')
        self.assertFalse(result['dispatch_performed'])

    def test_partial_SYS_source_drift_or_effect_rejects(self):
        report=self.partial_SYS_report();pin=self.write('handoff.json',self.handoff)
        (self.root/'tools/en2_preview_entry.py').write_text('# newer implementation')
        with self.assertRaises(w.WorkflowError):m.plan_en2_handoff(self.root,pin)
        report['installed']['tools/en2_preview_entry.py']=w.file_digest(self.root,'tools/en2_preview_entry.py')['sha256']
        report['effects']['workflow_run']=True
        self.handoff['report']=self.write('report.json',report);pin=self.write('handoff.json',self.handoff)
        with self.assertRaises(w.WorkflowError):m.plan_en2_handoff(self.root,pin)

    def test_handoff_rejects_wrong_WEB_and_unrelated_final(self):
        for change in ['wrong-thread','wrong-report']:
            doc=copy.deepcopy(self.web)
            if change=='wrong-thread':doc['thread']['id']='another'
            else:doc['turns'][0]['items'][0]['text']='unrelated completed task'
            self.handoff['native']=self.write('web.json',doc);pin=self.write('handoff.json',self.handoff)
            with self.assertRaises(w.WorkflowError):m.plan_en2_handoff(self.root,pin)


if __name__ == '__main__':
    unittest.main(verbosity=2)
