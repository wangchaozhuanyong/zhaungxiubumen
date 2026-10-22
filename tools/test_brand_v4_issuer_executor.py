"""Only scoped bridge checks and isolated permit fixtures; never website actions."""
from pathlib import Path
import copy,json,tempfile
from unittest import TestCase,mock
import workflow_control as w
import goal_delivery_runtime as g
import brand_v4_issuer_executor as b
ROOT=next(p for p in Path(__file__).resolve().parents if (p/'tools/workflow_control.py').is_file())

class ExactIssuerExecutorTests(TestCase):
    def setUp(self):self.goal=w.read_json(ROOT/b.STAGE['path'])
    def test_original_normal_stage_validator_preserves_C1_producer_and_real_WEB_actor(self):
        result=g.validate_goal(ROOT,self.goal,task_id=b.TASK)
        self.assertEqual(result['producer_departments'],[b.ISSUER]);self.assertEqual(result['actual_executor_department'],b.EXECUTOR)
        for action in result['required_execution_actions']:self.assertEqual(b.context(ROOT,result,action)['issuer_department'],b.ISSUER)
    def test_changed_issuer_executor_scope_candidate_parent_or_declared_actions_rejected(self):
        for key,value in [('primary_owner',b.EXECUTOR),('authorization_issuer_department',b.EXECUTOR),
            ('actual_executor_department',b.ISSUER),('authorized_scope',['unrelated.example:']),
            ('parent_task_id','fc-unrelated-parent'),('producer_departments',[b.EXECUTOR]),('required_execution_actions',[])]:
            with self.subTest(key=key),self.assertRaises(w.WorkflowError):b.context(ROOT,{**self.goal,key:value})
        for key in ['commit','parent','worktree','branch']:
            changed=copy.deepcopy(self.goal);changed['selected_candidate'][key]='wrong-value'
            with self.subTest(key=key),self.assertRaises(w.WorkflowError):b.context(ROOT,changed)
    def test_R3_or_new_excluded_business_scope_cannot_inherit_standing(self):
        for patch in [{'level':'R3'},{'high_risk_change_detected':True}]:
            changed=copy.deepcopy(self.goal);changed['risk'].update(patch)
            with self.subTest(patch=patch),self.assertRaises(w.WorkflowError):b.context(ROOT,changed)
    def test_real_standing_revoked_changed_issuer_or_repository_refuses(self):
        policy=w.load_policy(ROOT)
        for field,value in [('status','revoked'),('department',b.EXECUTOR),('source_repository','/unrelated-repo')]:
            changed=copy.deepcopy(policy);entry=next(x for x in changed['standing_authorizations']if x['authorization_id']==self.goal['standing_authorization_id']);entry[field]=value
            with mock.patch.object(w,'load_policy',return_value=changed),self.subTest(field=field),self.assertRaises(w.WorkflowError):b.context(ROOT,self.goal)
    def test_unregistered_collaborator_or_wrong_fixed_WEB_binding_refuses(self):
        original=w.read_json;registry=original(ROOT/'data/department-registry.json')
        for field,value in [('thread_id','wrong-thread'),('project_id','wrong-project'),('cwd','/other-project')]:
            changed=copy.deepcopy(registry);changed['collaboration_bindings'][b.EXECUTOR][field]=value
            def read(path):return changed if Path(path)==ROOT/'data/department-registry.json'else original(path)
            with mock.patch.object(w,'read_json',side_effect=read),self.subTest(field=field),self.assertRaises(w.WorkflowError):b.context(ROOT,self.goal)
    def test_no_other_task_gets_external_actor_compatibility(self):
        self.assertIsNone(b.context(ROOT,{**self.goal,'task_id':'fc-other-production'}))
        self.assertIsNone(b.action_context(ROOT,{'task_id':'fc-other-production'},'action','site_publish',b.SCOPE,b.EXECUTOR))
    def test_exact_action_family_and_version_cannot_be_changed(self):
        for action in self.goal['required_execution_actions']:
            for key,value in [('department',b.ISSUER),('issuer_department',b.EXECUTOR),('action_class','cms_write'),('selected_source_commit','0'*40)]:
                changed={**action,key:value}
                with self.subTest(action=action['operation'],key=key),self.assertRaises(w.WorkflowError):b.context(ROOT,self.goal,changed)
    def test_no_preflight_means_normal_execution_refuses_without_issuing_permits(self):
        action=self.goal['required_execution_actions'][0];snapshot={'task_id':b.TASK,'goal_delivery':self.goal}
        with self.assertRaisesRegex(w.WorkflowError,'self-check'):g.execution_preflight(ROOT,snapshot,action['action_id'],'site_publish',b.SCOPE,b.EXECUTOR)
    def test_metadata_or_PASS_without_actual_WEB_native_gate_is_insufficient(self):
        ctx=b.context(ROOT,self.goal);item={**self.goal['required_execution_actions'][0],'risk_level':'R2','issuer_executor_binding':b.approval_binding(ctx)}
        with self.assertRaises(w.WorkflowError):b.preflight(ROOT,{'task_id':b.TASK,'goal_delivery':self.goal},item)
    def test_queue_or_NOT_NEEDED_flag_cannot_fake_automatic_run(self):
        action=next(x for x in self.goal['required_execution_actions']if x['operation']=='workflow_dispatch');s={'task_id':b.TASK,'goal_delivery':self.goal}
        self.assertIsNone(b.conditional_completion(ROOT,s,action,None))
        changed=copy.deepcopy(s);changed['goal_delivery']['conditional_not_needed']=[{'action_id':action['action_id'],'proof':{'path':'missing-proof.json','sha256':'0'*64,'size':0}}]
        with self.assertRaises(w.WorkflowError):b.conditional_completion(ROOT,changed,action,{'state':'PROVEN'})
    def test_automatic_run_requires_actual_fixed_WEB_command_and_exact_output(self):
        # Isolated reader fixtures only; these are never saved as business proof.
        action=next(x for x in self.goal['required_execution_actions']if x['operation']=='workflow_dispatch')
        s={'task_id':b.TASK,'goal_delivery':copy.deepcopy(self.goal)};ctx=b.context(ROOT,self.goal)
        s['goal_delivery']['conditional_not_needed']=[{'action_id':action['action_id'],'proof':{'path':'isolated-fixture'}}]
        result={'task_id':b.TASK,'action_id':action['action_id'],'department':b.EXECUTOR,'issuer_department':b.ISSUER,
                'scope':b.SCOPE,'candidate_commit':action['selected_source_commit'],'verdict':'NOT_NEEDED',
                'operation':'workflow_dispatch','same_version_automatic_run_confirmed':True,'manual_dispatch_performed':False,
                'actual_automatic_run_id':123456,'actual_automatic_run_head_sha':action['selected_source_commit'],
                'actual_automatic_run_conclusion':'success'}
        proof={'actual_tool_result':{'content':[{'type':'text','text':json.dumps(result)}],'isError':False},
               'actual_native':{'path':'isolated-native'},'native_execution_id':'isolated-call'}
        thread={k:ctx['executor_binding'][v]for k,v in {'id':'thread_id','title':'title','cwd':'cwd'}.items()}
        call={'id':'isolated-call','type':'commandExecution','status':'completed','exitCode':0,
              'cwd':self.goal['selected_candidate']['worktree'],
              'command':'gh run view 123456 --json headSha,status,conclusion # '+action['selected_source_commit'],
              'output':{'text':json.dumps(result),'truncated':False}}
        page={'thread':thread,'turns':[{'status':'completed','items':[call]}]}
        accepted={'state':'PROVEN','identity':{},'source_fingerprint':{},'source_turn_id':'isolated-independent-turn'}
        def check(document):
            with mock.patch.object(b,'context',return_value=ctx),mock.patch.object(b,'_pin',return_value=proof),mock.patch.object(g,'_collaboration_native',return_value=document):
                return b.conditional_completion(ROOT,s,action,accepted)
        self.assertEqual(check(page)['operation_status'],'NOT_NEEDED')
        variants=[]
        for field,value in [('id','other-thread'),('title','other-role'),('cwd','/other-project')]:
            wrong=copy.deepcopy(page);wrong['thread'][field]=value;variants.append(wrong)
        for field,value in [('status','failed'),('exitCode',1),('cwd','/other-project'),('command','gh workflow run unauthorized')]:
            wrong=copy.deepcopy(page);wrong['turns'][0]['items'][0][field]=value;variants.append(wrong)
        wrong=copy.deepcopy(page);wrong['turns'][0]['items'][0]['output']['truncated']=True;variants.append(wrong)
        wrong=copy.deepcopy(page);wrong['turns'][0]['items'][0]['output']['text']='{}';variants.append(wrong)
        wrong=copy.deepcopy(page);wrong['turns'][0]['status']='inProgress';variants.append(wrong)
        for value in variants:
            with self.assertRaises(w.WorkflowError):check(value)

    def test_isolated_permits_pin_actual_issuer_WEB_actor_version_and_single_use(self):
        ctx=b.context(ROOT,self.goal);binding=b.approval_binding(ctx);standing=ctx['standing_authorization'];parent=ROOT/'.test-tmp';parent.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=parent)as directory:
            root=Path(directory);(root/'logs').mkdir();created=[]
            for action in self.goal['required_execution_actions']:
                result=w._materialize_standing_approval(root,authorization=standing,task_id=b.TASK,action_id=action['action_id'],action_class='site_publish',scope=b.SCOPE,executor_binding=binding);created.append(result)
                self.assertEqual(result['issuer_executor_binding'],binding);self.assertTrue(result['single_use'])
            b.require_complete_permit_set(root,{'goal_delivery':self.goal},ctx)
            with w.workflow_lock(root):used=w._consume_approval(root,created[0])
            self.assertEqual(used['status'],'consumed')
            with self.assertRaises(w.WorkflowError):b.require_complete_permit_set(root,{'goal_delivery':self.goal},ctx)
            repeat=w._materialize_standing_approval(root,authorization=standing,task_id=b.TASK,action_id=created[0]['action_id'],action_class='site_publish',scope=b.SCOPE,executor_binding=binding)
            self.assertEqual(repeat['status'],'consumed')
    def test_missing_revoked_or_wrong_actor_permit_refuses_complete_set(self):
        ctx=b.context(ROOT,self.goal);binding=b.approval_binding(ctx)
        approvals={str(i):{'task_id':b.TASK,'action_id':x['action_id'],'action_class':'site_publish','scope':b.SCOPE,'issuer_executor_binding':binding,'single_use':True,'status':'active'}for i,x in enumerate(self.goal['required_execution_actions'])}
        variants=[{k:v for k,v in approvals.items()if k!='0'},copy.deepcopy(approvals),copy.deepcopy(approvals)]
        variants[1]['0']['status']='revoked';variants[2]['0']['issuer_executor_binding']={**binding,'actual_executor_department':b.ISSUER}
        for value in variants:
            with mock.patch.object(w,'effective_approvals',return_value=value),self.assertRaises(w.WorkflowError):b.require_complete_permit_set(ROOT,{'goal_delivery':self.goal},ctx)
