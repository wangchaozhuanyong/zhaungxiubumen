"""Exact original C1 authority / WEB executor representation, with no permit issuance."""
from pathlib import Path
import json
import workflow_control as w
TASK='fc-20261021-brand-corrected-v4-site-production-stage-v1'
ISSUER='content-organic-website';EXECUTOR='designated-development'
SCOPE='company.example:brand-main-name-preservation-dual-query:20261021:v4-production'
BASE='logs/handoffs/2026-10-20-clean-department-window-rotation-v1/operations/unfinished-business-followthrough-20261021-v1/shanzhu-brand-google-visibility-v1/main-name-correction-and-dual-query-20261021-v1/HQ-corrected-v4-production-decision-20261021-v1'
STAGE={'path':BASE+'/A1-actual-production-stage-continuation-v1/bounded-corrected-v4-production-phase-contract-v1.json','sha256':'331275e4c6b8ac4a51c3ce4103d3330f38a53004091ec5827970613696326298','size':13508}
INPUT={'path':'drafts/seo/fc-20261021-brand-main-name-preservation-and-dual-query-v1/content-organic-website/C1-ISSUER-SOURCE-R2-V4-PRODUCTION-BINDING-INPUT-v1.json','sha256':'29f500b9fab90b167637535c720ceb7a1745612cae90cc83af85629ffe9f3f4c','size':13590}


def _fail(message):raise w.WorkflowError('original brand issuer/WEB: '+message)

def _pin(root,pin):
    if not isinstance(pin,dict)or w.file_digest(root,pin.get('path',''))!=pin:_fail('exact original source bytes changed')
    return w.read_json(w.safe_path(root,pin['path']))


def context(root,goal,action=None):
    if goal.get('task_id')!=TASK:return None
    frozen=_pin(root,STAGE);source=_pin(root,INPUT)
    fields=('task_id','parent_task_id','primary_owner','producer_departments','responsible_assistant','authorized_scope',
            'source_mode','human_authorization','collaboration_scopes','required_execution_actions',
            'standing_authorization_id','authorization_issuer_department','actual_executor_department','actual_executor_binding',
            'selected_candidate','selected_patch','risk','completion_kind','completion_criteria','completion_requirements')
    if any(goal.get(k)!=frozen.get(k)for k in fields):_fail('frozen original parent/actor/scope/version/risk/action contract differs')
    if (goal['primary_owner']!=ISSUER or goal['producer_departments']!=[ISSUER]
            or goal['authorization_issuer_department']!=ISSUER or goal['actual_executor_department']!=EXECUTOR
            or goal['risk']['level']!='R2' or goal['risk'].get('high_risk_change_detected')is not False
            or goal.get('production_permission_issued_by_contract')is not False):_fail('original roles/R2 and unchanged permission boundary required')
    if (goal['selected_candidate']!=source['selected_candidate'] or goal['selected_patch']!=source['full_patch']
            or goal['risk']!=source['risk'] or source['formal_execution_permits_issued_by_this_packet']is not False
            or source['production_executed']is not False):_fail('original actually received issuer input/version required')
    _pin(root,source['HQ_precise_decision'])
    for pin in goal['existing_results']:_pin(root,pin)
    rows=w._result_handoff_rows(root,goal['parent_task_id'])
    intakes=[x for x in rows if x.get('record_id')=='b7388ce4-aeaa-492f-a9ba-3cbc76c2ce50'
             and x.get('event')=='controller_received' and x.get('sender_department')==ISSUER
             and x.get('coordinator_role')=='operations-assistant']
    if len(intakes)!=1:_fail('original A1 actual issuer-input intake required')
    from scoped_candidate_adoption import _committed
    _committed(root,intakes[0])
    box=_pin(root,intakes[0]['outbox'])
    if box.get('primary_deliverable')!=INPUT or INPUT not in box.get('evidence',[]):
        _fail('actual received issuer outbox must pin this original binding input')
    policy=w.load_policy(root)
    standing=w.matching_standing_authorization(policy,department=ISSUER,action_class='site_publish',scope=SCOPE)
    if (not standing or standing!=source['standing_authorization_source']['registered_entry']
            or standing.get('authorization_id')!=goal['standing_authorization_id']
            or standing.get('source_repository')!=goal['actual_executor_binding']['repository']
            or standing.get('site')!='company.example'):_fail('actual original active C1 standing source required; no relabelling')
    binding=w.read_json(Path(root)/'data/department-registry.json')['collaboration_bindings'].get(EXECUTOR,{})
    actual=goal['actual_executor_binding']
    if (binding.get('thread_id')!=actual['thread_id']or binding.get('project_id')!=actual['project_id']
            or not Path(actual['repository']).is_relative_to(Path(binding.get('cwd','/invalid')))
            or not binding.get('existing_authorization_required') or not binding.get('runtime_goal_authorization_required')):
        _fail('real declared original WEB collaboration binding/repository required')
    if action is not None:
        matches=[x for x in frozen['required_execution_actions']if x==action]
        if len(matches)!=1 or action.get('department')!=EXECUTOR or action.get('issuer_department')!=ISSUER or action.get('actual_executor_department')!=EXECUTOR:
            _fail('one exact action/issuer/executor/version required')
    return {'issuer_department':ISSUER,'actual_executor_department':EXECUTOR,'executor_binding':binding,
            'issuer_input':INPUT,'candidate_commit':goal['selected_candidate']['commit'],'candidate_parent':goal['selected_candidate']['parent'],
            'standing_authorization_id':standing['authorization_id'],'scope':SCOPE,'standing_authorization':standing,
            'production_permission_issued':False}


def action_context(root,snapshot,action_id,action_class,scope,department):
    if snapshot.get('task_id')!=TASK:return None
    goal=snapshot.get('goal_delivery',{})
    actions=[x for x in goal.get('required_execution_actions',[])if all(x.get(k)==v for k,v in
        {'action_id':action_id,'action_class':action_class,'scope':scope,'department':department}.items())]
    if len(actions)!=1:_fail('original exact declared action required')
    return context(root,goal,actions[0])


def approval_binding(ctx):
    return {k:ctx[k]for k in ('issuer_department','actual_executor_department','issuer_input','candidate_commit','candidate_parent','standing_authorization_id','scope')}


def validate_native_gate(root,item,goal):
    """The actual original WEB source/risk guard must execute before any permit."""
    import goal_delivery_runtime as g
    ctx=context(root,goal)
    if item.get('issuer_executor_binding')!=approval_binding(ctx):_fail('self-check must retain exact issuer/executor/version binding')
    pin=item.get('native_final_source_risk_gate');proof=_pin(root,pin)
    page=g._collaboration_native(root,proof.get('actual_native'));binding=ctx['executor_binding']
    if any(page.get('thread',{}).get(k)!=binding.get(v)for k,v in {'id':'thread_id','title':'title','cwd':'cwd'}.items()):_fail('actual original WEB native source required')
    calls=[(t,c)for t in page.get('turns',[])for c in t.get('items',[])if c.get('id')==proof.get('native_execution_id')and c.get('type')=='commandExecution']
    if len(calls)!=1:_fail('one actual WEB final source/risk execution required')
    turn,call=calls[0];output=call.get('output',{})
    raw=output.get('text')if isinstance(output,dict)else output
    try:result=json.loads(raw)
    except (ValueError,TypeError):_fail('actual untruncated source/risk JSON output required')
    selected=goal['selected_candidate']
    expected={'task_id':TASK,'issuer_department':ISSUER,'actual_executor_department':EXECUTOR,'scope':SCOPE,
        'candidate_commit':selected['commit'],'candidate_parent':selected['parent'],'risk_level':'R2','high_risk_change_detected':False,
        'source_clean':True,'actual_remote_effect':False,'excluded_change_detected':False,'all_downstream_actions':[x['action_id']for x in goal['required_execution_actions']]}
    if (turn.get('error')or call.get('status')!='completed'or call.get('exitCode')!=0
            or call.get('cwd')!=selected['worktree']or not isinstance(output,dict)or output.get('truncated')is not False
            or any(result.get(k)!=v for k,v in expected.items())or any(x not in call.get('command','')for x in [selected['commit'],selected['parent']])):
        _fail('real exact clean version/R2/pre-effect full downstream coverage required')
    return ctx


def preflight(root,snapshot,item,*,require_all=False):
    ctx=action_context(root,snapshot,item.get('action_id'),item.get('action_class'),item.get('scope'),item.get('department'))
    if ctx is None:return None
    goal=snapshot['goal_delivery']
    if item.get('risk_level')!='R2':_fail('true R3 or changed risk requires original additional authorization')
    validate_native_gate(root,item,goal)
    # Every downstream action must have its own complete original preflight
    # before the first remote action; each later permit stays single-use.
    if require_all and {x.get('action_id')for x in goal.get('execution_preflights',[])}!={x['action_id']for x in goal['required_execution_actions']}:
        _fail('all five exact downstream self-check/backup/rollback bindings must exist before remote effects')
    for row in goal['execution_preflights']:
        if row.get('issuer_executor_binding')!=approval_binding(ctx):_fail('all downstream actor/version bindings required')
        for name in ('facts','self_check','backup','rollback'):_pin(root,row.get(name))
        check=_pin(root,row['self_check'])
        if row.get('risk_level')!='R2' or check.get('status')!='PASS' or any(check.get(k)!=row.get(k)for k in ('action_id','action_class','scope','department')):
            _fail('all exact original R2 downstream self-checks required')
    return ctx


def conditional_completion(root,snapshot,action,accepted):
    if snapshot.get('task_id')!=TASK or action.get('operation')!='workflow_dispatch':return None
    ctx=context(root,snapshot['goal_delivery'],action)
    entries=[x for x in snapshot['goal_delivery'].get('conditional_not_needed',[])if x.get('action_id')==action['action_id']]
    if not entries:return None
    if len(entries)!=1:_fail('one actual same-version automatic-run observation required')
    item=entries[0];proof=_pin(root,item.get('proof'))
    # Reuse the existing typed native result reader; no execution_result is invented.
    import qa_review_plan as q
    q._review_native_containers(proof)
    result=q._review_raw_native_result(proof.get('actual_tool_result',{}))
    expected={'task_id':TASK,'action_id':action['action_id'],'department':EXECUTOR,'issuer_department':ISSUER,
              'scope':SCOPE,'candidate_commit':action['selected_source_commit'],'verdict':'NOT_NEEDED',
              'operation':'workflow_dispatch','same_version_automatic_run_confirmed':True,'manual_dispatch_performed':False}
    run_id=result.get('actual_automatic_run_id')
    if (any(result.get(k)!=v for k,v in expected.items())or type(run_id)not in {str,int}
            or not str(run_id).strip()or result.get('actual_automatic_run_head_sha')!=action['selected_source_commit']
            or result.get('actual_automatic_run_conclusion')!='success'):
        _fail('actual successful same-head automatic workflow run proof required')
    import goal_delivery_runtime as g
    page=g._collaboration_native(root,proof.get('actual_native'));binding=ctx['executor_binding']
    if any(page.get('thread',{}).get(k)!=binding.get(v)for k,v in {'id':'thread_id','title':'title','cwd':'cwd'}.items()):
        _fail('actual fixed original WEB automatic-run reader required')
    calls=[(t,c)for t in page.get('turns',[])for c in t.get('items',[])if c.get('id')==proof.get('native_execution_id')and c.get('type')=='commandExecution']
    if len(calls)!=1:_fail('one actual original WEB read-only run observation required')
    turn,call=calls[0];output=call.get('output',{});command=call.get('command','')
    try:observed=json.loads(output.get('text',''))
    except (ValueError,TypeError,AttributeError):_fail('actual untruncated run readback required')
    if (turn.get('status')!='completed'or turn.get('error')or call.get('status')!='completed'or call.get('exitCode')!=0
            or call.get('cwd')!=snapshot['goal_delivery']['selected_candidate']['worktree']
            or not isinstance(output,dict)or output.get('truncated')is not False or observed!=result
            or any(x not in command for x in ['gh run view',str(run_id),'--json',action['selected_source_commit']])):
        _fail('real successful fixed WEB same-version automatic-run command/output required')
    if not accepted or accepted.get('state')!='PROVEN':_fail('actual current independent accepted producer source required')
    return {'state':'PROVEN','identity':accepted['identity'],'source_fingerprint':accepted['source_fingerprint'],
            'source_turn_id':accepted['source_turn_id'],'scope':SCOPE,'operation_status':'NOT_NEEDED',
            'execution_fabricated':False,'evidence':[item['proof']]}


def require_complete_permit_set(root,snapshot,ctx):
    """Before any consumption, every original downstream action has its bound permit."""
    approvals=w.effective_approvals(root);binding=approval_binding(ctx)
    for action in snapshot['goal_delivery']['required_execution_actions']:
        found=[x for x in approvals.values() if all(x.get(k)==v for k,v in
            {'task_id':TASK,'action_id':action['action_id'],'action_class':'site_publish','scope':SCOPE,
             'issuer_executor_binding':binding,'single_use':True}.items())]
        if len(found)!=1 or found[0].get('status')not in {'active','consumed'}:
            _fail('all exact downstream permits must exist before the first remote effect; revoked/missing refuses')
        if found[0]['status']=='consumed':
            rows,invalid=w._validate_receipt_chain(root,TASK)
            if invalid or not any(x.get('receipt_type')=='execution_result' and x.get('department')==EXECUTOR
                and x.get('action_id')==action['action_id'] and x.get('approval_id')==found[0]['approval_id']
                and x.get('verdict')=='pass' for x in rows):
                _fail('consumed or uncertain earlier remote effect requires actual original successful readback')
