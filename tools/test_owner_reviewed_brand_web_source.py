"""Bounded tests against the actual read-only source inputs; no platform calls."""
import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch
import owner_reviewed_brand_web_source as s
import professional_web_execution as web
import workflow_control as w
import goal_delivery_runtime as g

ROOT = Path(__file__).resolve().parents[1]

class BrandSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.snapshot = w.read_json(w.snapshot_path(ROOT, s.TASK))
        cls.item = w.read_json(ROOT / s.NATIVE_DIR / 'EXACT-CURRENT-BRAND-SOURCE.json')
        cls.context = s.validate(ROOT, cls.snapshot, cls.item)

    def rejected(self, item=None, snapshot=None):
        with self.assertRaises(w.WorkflowError):
            s.validate(ROOT, snapshot or self.snapshot, item or self.item)

    def test_actual_reviewed_source_and_restricted_operations(self):
        self.assertEqual(self.context['commit'], s.HEAD)
        self.assertEqual(set(self.context['paths']), s.PATHS)
        self.assertEqual(set(self.context['allowed_operations']), {'git_push','pull_request','official_ci','merge','pages_deploy'})
        self.assertFalse(any(k in self.context for k in ('approval_id','actual_action_allowed','platform_permission_issued')))

    def test_wrong_task_scope_contract_or_schema(self):
        for field, value in [('task_id','fc-20261015-industry-keywords-site-coverage-plan-v1'),
                             ('scope','another:scope'),('schema','caller-approval'),('goal_contract',{})]:
            with self.subTest(field=field):
                item = copy.deepcopy(self.item); item[field] = value; self.rejected(item=item)

    def test_pause_closed_and_owner_or_producer_reassignment(self):
        for field, value in [('current_state','paused'),('current_state','closed')]:
            snap = copy.deepcopy(self.snapshot); snap[field] = value; self.rejected(snapshot=snap)
        for field, value in [('primary_owner','operations'),('producer_departments',['designated-development']),
                             ('parent_task_id','another-parent'),('authorization_pin',{})]:
            with self.subTest(field=field):
                snap=copy.deepcopy(self.snapshot);snap['goal_delivery'][field]=value;self.rejected(snapshot=snap)

    def test_all_evidence_pins_missing_tampered_or_substituted(self):
        for name in s.PINS:
            with self.subTest(pin=name):
                item=copy.deepcopy(self.item);item['sources'][name]['sha256']='0'*64;self.rejected(item=item)
        item=copy.deepcopy(self.item);item['sources'].pop('C1_native');self.rejected(item=item)

    def test_incomplete_or_failed_native_commands_rejected(self):
        for update in [{'status':'failed'},{'exitCode':1},{'output':{'text':'34 passed','truncated':True}}]:
            cmd={'id':'x','type':'commandExecution','status':'completed','exitCode':0,'output':{'text':'34 passed','truncated':False}}
            cmd.update(update)
            with self.assertRaises(w.WorkflowError):s.command({'items':[cmd]},'x')

    def test_git_parent_and_selected_paths_cannot_drift(self):
        actual_git=web.git
        def changed(ctx,*args):
            if args[:3]==('show','-s','--format=%H %P %T'):return (s.HEAD+' '+'0'*40+' '+s.TREE).encode()
            return actual_git(ctx,*args)
        with patch.object(web,'git',side_effect=changed):self.rejected()
        def paths(ctx,*args):
            if args[:2]==('diff','--name-only'):return b'functions/_middleware.ts\n.env\n'
            return actual_git(ctx,*args)
        with patch.object(web,'git',side_effect=paths):self.rejected()

    def test_altered_human_type_and_independent_native_identity(self):
        native=g._native_document
        def forged(root,pin):
            page=copy.deepcopy(native(root,pin))
            if pin==s.pin(ROOT,'owner_native'):
                for item in page['turns'][0]['items']:
                    if item.get('type')=='userMessage':item['type']='agentMessage'
            return page
        with patch.object(g,'_native_document',side_effect=forged):self.rejected()
        def wrong_receiver(root,pin):
            page=copy.deepcopy(native(root,pin))
            if pin==s.pin(ROOT,'C1_native'):page['thread']['id']='retired-role'
            return page
        with patch.object(g,'_native_document',side_effect=wrong_receiver):self.rejected()

    def test_existing_per_action_clean_worktree_and_candidate_guard(self):
        state={'candidate_commit':s.HEAD,'candidate_base':s.BASE,'candidate_parent':s.BASE,
               'candidate_tree':s.TREE,'worktree':self.context['worktree'],'branch':self.context['branch']}
        self.assertEqual(web.candidate(self.context,state),(s.HEAD,s.BASE))
        web.working_source(self.context,s.HEAD)
        for field,value in [('candidate_commit','0'*40),('candidate_base','0'*40),
                            ('branch','other'),('worktree','/tmp/other'),('source_mode','remove_own_delta')]:
            bad={**state,field:value}
            with self.subTest(field=field),self.assertRaises(w.WorkflowError):web.candidate(self.context,bad)

    def test_return_only_reports_actual_existing_owner_knowledge(self):
        request=w.read_json(ROOT/s.PINS['return_request'][0]); ctx={**self.context,'registration':{'path':'test','sha256':'0'*64,'size':0}}
        with patch.object(web,'records',return_value=[ctx]):
            result=s.readonly_return(ROOT,self.snapshot,request)
            self.assertTrue(result['actual_owner_knowledge_proven'])
            self.assertFalse(result['formal_result_received_proven'])
            self.assertFalse(result['external_permission_issued'])
            for field,value in [('target_department','operations'),('scope','other'),('payload_sha256','0'*64),
                                ('operation','git_push'),('consume_approval',True),('assignment_record_required',True)]:
                with self.subTest(field=field),self.assertRaises(w.WorkflowError):
                    s.readonly_return(ROOT,self.snapshot,{**request,field:value})

    def test_other_tasks_and_retired_senders_do_not_get_new_route(self):
        request=w.read_json(ROOT/s.PINS['return_request'][0])
        self.assertIsNone(s.readonly_return(ROOT,{**self.snapshot,'task_id':'other'},request))
        self.assertIsNone(s.readonly_return(ROOT,self.snapshot,{**request,'sender_department':'operations-assistant-2'}))

    def test_normal_cli_source_dispatch_does_not_skip_source_validation(self):
        path=s.NATIVE_DIR+'EXACT-CURRENT-BRAND-SOURCE.json'
        with patch.object(web,'record_source',return_value={'result':'validated-source-only'}) as record:
            self.assertEqual(g.record_approved_action(ROOT,s.TASK,path)['result'],'validated-source-only')
            record.assert_called_once_with(ROOT,s.TASK,path)

    def test_time_and_unknown_effect_guards_remain_required(self):
        import datetime as dt
        item={'request':{'path':'isolated-request','sha256':'digest','size':1}}
        requested={'task_id':s.TASK,'action_id':'isolated-action','action_class':'site_ci_prepare',
                   'scope':s.SCOPE,'department':s.ROLE,'source_project_id':s.a.PROJECT,'payload_sha256':'digest'}
        for stamp,effect in [('2000-01-01T00:00:00+00:00','NOT_STARTED'),
                             ('2999-01-01T00:00:00+00:00','NOT_STARTED'),
                             (dt.datetime.now(dt.timezone.utc).isoformat(),'UNKNOWN')]:
            req={'state':{'candidate_commit':s.HEAD,'remote_branch_sha':None,'effect_state':effect},
                 'operation':'git_push','observed_at':stamp}
            with patch.object(web,'preflight',return_value=(item,req,{},self.context)),\
                 patch.object(w,'append_jsonl_locked') as append:
                with self.assertRaises(w.WorkflowError):web.policy(ROOT,requested)
                append.assert_not_called()

    def test_registration_uses_original_mutex_and_preserves_conflicting_source(self):
        # Isolated metadata store; real authority validation was exercised above.
        from contextlib import contextmanager
        from concurrent.futures import ThreadPoolExecutor
        from threading import Lock
        calls=[];store=[]
        mutex=Lock()
        @contextmanager
        def lock(_):
            with mutex:
                calls.append('lock');yield
        def append(root,task,state,details):
            self.assertEqual(calls[-1],'lock');store.append(details);return {'event_id':'isolated-event'}
        source_path=str(Path(s.NATIVE_DIR)/'EXACT-CURRENT-BRAND-SOURCE.json')
        with patch.object(w,'workflow_lock',side_effect=lock),patch.object(g,'restore_goal',return_value=self.snapshot),\
             patch.object(web,'validate_source',return_value=self.context),patch.object(w,'append_workflow_event',side_effect=append),\
             patch.object(web,'records',side_effect=lambda *args:[] if not store else [{'registration':store[0][web.EVENT]}]):
            with ThreadPoolExecutor(max_workers=2) as pool:
                results=list(pool.map(lambda _:web.record_source(ROOT,s.TASK,source_path),range(2)))
            self.assertEqual(sorted(r['result'] for r in results),['duplicate_ignored','recorded'])
            self.assertEqual(len(store),1);self.assertEqual(len(calls),2)
        with patch.object(w,'workflow_lock',side_effect=lock),patch.object(g,'restore_goal',return_value=self.snapshot),\
             patch.object(web,'validate_source',return_value=self.context),patch.object(web,'records',return_value=[{'registration':{}}]),\
             patch.object(w,'append_workflow_event') as append:
            with self.assertRaises(w.WorkflowError):web.record_source(ROOT,s.TASK,source_path)
            append.assert_not_called()

if __name__=='__main__':unittest.main(verbosity=2)
