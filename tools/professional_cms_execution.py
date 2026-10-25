"""Append-only professional CMS source binding; never a platform permit."""
from pathlib import Path
import argparse
import json
import re
import workflow_control as w

SCHEMA = 'professional-cms-execution-source-registration/v1'
EVENT = 'professional_cms_execution_source'

def validate(root, snapshot, item):
    import department_autonomy as a
    import goal_delivery_runtime as g
    import result_coordination as rc
    need = a.require
    goal = a.participant(root, snapshot, snapshot['goal_delivery']['primary_owner'])
    frozen = a.document(root, snapshot['goal_contract'])
    need(a.autonomous_goal(frozen) and a.current_mode(root)
         and all(goal.get(k) == frozen.get(k) for k in
                 ('primary_owner','parent_task_id','producer_departments','authorized_scope',
                  'human_authorization','required_execution_actions','collaboration_scopes')),
         'unchanged autonomous contract, authority, actions and original participants required')
    need(item.get('schema') == SCHEMA and item.get('task_id') == snapshot['task_id']
         and item.get('goal_contract') == snapshot['goal_contract']
         and item.get('authorization') == goal['authorization_pin'], 'exact source registration contract/task/authority')
    scope = item.get('business_scope'); owner = goal['primary_owner']
    need(scope in frozen['authorized_scope'], 'original business scope required')
    criterion = [x for x in goal['completion_requirements'] if x.get('requirement_id') == item.get('requirement_id')]
    need(len(criterion) == 1 and criterion[0]['producer_department'] == owner
         and criterion[0]['scope'] == scope, 'original owner criterion required')
    identity = rc.exact_identity(item.get('owner_result_identity', {}))
    need(identity['task_id'] == snapshot['task_id'] and identity['sender_department'] == owner,
         'original professional business result identity required')
    rows = w._result_handoff_rows(root, snapshot['task_id'])
    queued = [r for r in rows if r.get('event') == 'notification_queued'
              and w._result_identity(r) == tuple(identity[k] for k in rc.IDENTITY_FIELDS[1:])]
    need(len(queued) == 1 and queued[0].get('target_department') == 'operations', 'unique original HQ knowledge source required')
    q = queued[0]; a.native_result(root, q, w.department_registry(root)[owner]['chat_binding']['task_id'])
    intake = rc._received_delivery(root, identity, {'target_department':'operations'})
    need(intake and intake['record_id'] == item.get('owner_result_received_record_id'),
         'real committed SQL/native original result intake required')
    report = a.document(root, q['outbox']); pin = item.get('owner_source'); source = a.document(root, pin)
    need(pin in report.get('evidence', []) and report.get('exact_CMS_business_execution_source') == pin
         and report.get('primary_owner') == owner and report.get('scope') == scope,
         'actual full professional report must bind this exact execution source')
    need(source.get('task_id') == snapshot['task_id'] and source.get('scope') == scope
         and source.get('primary_owner') == source.get('department') == owner
         and source.get('goal_contract') == snapshot['goal_contract']
         and source.get('human_authorization') == goal['authorization_pin']
         and source.get('original_requirement') == frozen['completion_criteria'][criterion[0]['criterion_index']],
         'unchanged original owner source/criterion/scope/authorization required')
    native = g._native_document(root, item.get('owner_native'))
    fixed = w.department_registry(root)[owner]['chat_binding']
    need(all(native.get('thread',{}).get(k) == fixed[v] for k,v in
             {'id':'task_id','title':'title','cwd':'cwd'}.items()) and fixed['project_id'] == a.PROJECT,
         'actual fixed same-project professional source required')
    calls = [(t,m) for t in native.get('turns',[]) for m in t.get('items',[])
             if m.get('id') == item.get('source_command_id')]
    need(len(calls) == 1, 'one actual original source command required')
    turn, call = calls[0]
    need(turn.get('status') == 'completed' and not turn.get('error')
         and call.get('type') == 'commandExecution' and call.get('status') == 'completed'
         and call.get('exitCode') == 0 and Path(call.get('cwd','')).resolve() == Path(root).resolve(),
         'successful completed original owner source command required')
    output = json.loads(w._completion_execution_output(call))
    need(output.get('exact_source') == pin, 'native output must identify the exact immutable source bytes')
    decided = w._parse_observed_at(source.get('decided_at_UTC'))
    observed = w._parse_observed_at(q.get('reply_observed_at'))
    ready = [m for m in turn.get('items',[]) if m.get('id') == q.get('source_message_id')]
    need(decided is not None and observed is not None and type(turn.get('completedAt')) in {int,float}
         and turn.get('startedAt',float('inf')) <= decided.timestamp() <= observed.timestamp() <= turn['completedAt']
         and turn.get('id') == q.get('source_turn_id') and len(ready) == 1
         and turn['items'].index(call) < turn['items'].index(ready[0]),
         'real ordered source decision, command, and READY required')
    carrier = a.document(root, source.get('source_carrier'))
    a.document(root,source.get('original_C1_source_input'))
    need(w.file_digest(root,source['original_work_order']['path'])==source['original_work_order'],
         'unchanged original owner work-order text required')
    need(carrier.get('source_contract')==snapshot['goal_contract']
         and carrier.get('source_human_authorization')==goal['authorization_pin'],
         'carrier retains original frozen contract and human source')
    proposed = carrier['proposed_exact_tuple']; action = source['exact_CMS_action_requested']
    need(all(action.get(k) == v for k,v in proposed.items())
         and action.get('business_scope') == scope == proposed.get('business_policy_scope')
         and action.get('original_professional_owner') == owner
         and action.get('action_class') == 'cms_write'
         and action.get('action_id') == 'publish-' + action.get('candidate_version',''),
         'exact original carrier action/version/owner/business scope required')
    fields = action.get('changed_fields',[])
    need(isinstance(fields,list) and 0 < len(fields) <= 8 and fields == sorted(set(fields))
         and all(re.fullmatch(r'content_(en|zh|ms)', x) for x in fields)
         and re.fullmatch(r'[a-z][a-z0-9_]*', action.get('table',''))
         and re.fullmatch(r'[0-9a-f-]{36}',action.get('record_id','')),
         'bounded existing content fields and exact record required')
    physical = 'company.example:' + action['table'] + ':' + action['record_id'] + ':' + ','.join(fields)
    need(action.get('scope') == action.get('physical_target_scope') == physical,
         'explicit original business to physical scope mapping required')
    proposal = a.document(root, source.get('original_PUB_proposal'))
    baseline = a.document(root, source['original_source_baseline_only']['complete_row'])
    before = {k:baseline[k] for k in fields}; desired = source['exact_two_field_desired_values']
    need(source.get('original_PUB_proposal') == carrier['source_proposal']
         and source.get('original_C1_source_input') == carrier['source_input']
         and proposal.get('task_id') == snapshot['task_id'] and proposal.get('scope') == scope
         and proposal.get('table') == action['table'] and proposal.get('id') == action['record_id']
         and proposal.get('slug') == action['slug'] and sorted(proposal.get('fields',[])) == fields
         and desired == proposal.get('after') == carrier['exact_forward_values']
         and before == proposal.get('before') and source['original_source_baseline_only'] == carrier['source_baseline_only'],
         'original before/desired field source and unchanged baseline carrier required')
    need(w.sha256_value(before) == source['original_source_baseline_only']['before_fields_sha256']
         and w.sha256_value(desired) == source['original_source_baseline_only']['desired_fields_sha256'],
         'exact business before/desired field digests required')
    protected = source['protected_fields']
    need(protected == carrier['protected_fields'] and set(protected['not_written_fields']) == set(baseline)-set(fields)
         and set(protected['server_CAS_metadata']) == {'updated_at','version'}
         and set(protected['stable_business_readback_fields']) == set(baseline)-set(fields)-{'updated_at','version'},
         'all other business fields/MS and server-owned CAS must remain protected')
    reverse = source['restore_only_own_two_field_delta']; original_reverse = carrier['reverse_carrier']
    need(reverse == original_reverse and reverse.get('restore_only_original_two_fields') == before
         and reverse.get('scope') == physical and reverse.get('requiresParentRun') is True
         and reverse.get('action_id') == 'rollback-' + action['candidate_version']
         and reverse.get('candidate_version') == action['candidate_version'] + '-rollback-v1'
         and all(reverse.get(k) is None for k in ('parentPermitId','parentRunId','saved_updated_at','current_post_Save_complete_row')),
         'conditional own-parent inverse only; no invented run or post-Save CAS')
    executor = source['original_PUB_executor']; channel = source['original_channel_owner']; role = executor['department']
    need(role == action['execution_department'] and a.professional(root,role) and role != owner,
         'actual original professional CMS executor required')
    binding = w.department_registry(root)[role]['chat_binding']
    need(all(executor.get(k) == binding.get(v) for k,v in
             {'thread_id':'task_id','title':'title','project_id':'project_id','cwd':'cwd'}.items())
         and binding['project_id'] == a.PROJECT and Path(binding['cwd']).resolve() == Path(root).resolve(),
         'exact original PUB identity/project/directory required')
    current_channel = w.read_json(Path(root)/'data/department-registry.json')['collaboration_bindings'].get(channel['department'])
    need(current_channel and all(channel['binding'].get(k) == current_channel.get(k) for k in
         ('thread_id','title','project_id','cwd','host_id')), 'original external channel identity required')
    need(not w.validate_workflow_events(root,snapshot['task_id']), 'intact append-only original workflow required')
    return {'action':action,'source':pin,'owner':owner,'business_scope':scope,'executor':role,
            'channel':channel['department'],'carrier':source['source_carrier'],'desired':desired,'before':before,
            'protected_fields':protected,'owner_result':q['outbox'],'actual_HQ_intake':intake['record_id']}

def records(root, snapshot):
    import department_autonomy as a
    rows = [e for e in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS)
            if e.get('task_id') == snapshot['task_id'] and EVENT in e.get('details',{})]
    result=[]; seen=set()
    for row in rows:
        pin=row['details'][EVENT]; item=a.document(root,pin); context=validate(root,snapshot,item)
        key=context['action']['action_id'];a.require(key not in seen,'ambiguous execution source registration')
        seen.add(key);result.append({**context,'registration':pin,'event_id':row['event_id']})
    return result

def record(root, task, input_path):
    import goal_delivery_runtime as g
    import department_autonomy as a
    pin=w.file_digest(root,input_path);item=a.document(root,pin)
    with w.workflow_lock(root):
        snapshot=g.restore_goal(root,w.read_json(w.snapshot_path(root,task))); context=validate(root,snapshot,item)
        existing=[x for x in records(root,snapshot) if x['action']['action_id']==context['action']['action_id']]
        if existing:
            a.require(existing[0]['registration']==pin,'immutable source action already registered to different bytes')
            return {'result':'duplicate_ignored',**existing[0],'external_permission_issued':False,'production_READY':False}
        w.append_workflow_event(root,task,snapshot['current_state'],{EVENT:pin,'frozen_contract_unchanged':True})
    return {'result':'recorded','registration':pin,**context,'external_permission_issued':False,'production_READY':False}

def match(root,snapshot,request):
    found=[x for x in records(root,snapshot) if request.get('action_id') in {x['action']['action_id'],'rollback-'+x['action']['candidate_version']}]
    if not found:return None
    import department_autonomy as a
    a.require(len(found)==1,'one exact registered execution source required');x=found[0];action=x['action']
    a.require(request.get('task_id')==snapshot['task_id'] and request.get('department')==x['executor']
              and request.get('sender_department',x['executor'])==x['executor']
              and request.get('action_class')=='cms_write' and request.get('scope') in {x['business_scope'],action['scope']}
              and request.get('authorization_changes',[])==[], 'registered exact task/executor/action/scope; no expansion')
    if request['action_id'] != action['action_id']:
        return {**x,'operation':'rollback','action':{**action,'action_id':request['action_id'],
                    'candidate_version':action['candidate_version']+'-rollback-v1'},'before':x['desired'],'desired':x['before']}
    return {**x,'operation':'publish'}

def collaboration_scopes(root,snapshot):
    result=list(snapshot.get('goal_delivery',{}).get('collaboration_scopes',[]))
    for x in records(root,snapshot):
        for role in (x['executor'],x['channel']):
            declaration={'sender_department':x['owner'],'target_department':role,'scope':x['business_scope']}
            if declaration not in result:result.append(declaration)
    return result

def validate_message(root,snapshot,action):
    """An appended collaborator receives this exact binding, not general authority."""
    import department_autonomy as a
    pin=action.get('professional_execution_source')
    found=[x for x in records(root,snapshot) if x['registration']==pin]
    a.require(len(found)==1, 'exact appended execution source required for this collaborator')
    x=found[0]
    a.require(action.get('task_id')==snapshot['task_id'] and action.get('sender_department')==x['owner']
              and action.get('target_department') in {x['executor'],x['channel']}
              and action.get('scope')==x['business_scope'] and action.get('action_class')=='thread_message'
              and action.get('execution_tuple')==x['action'], 'original owner and exact execution tuple/collaborator required')
    payload=action.get('payload');a.require(w.file_digest(root,payload.get('path',''))==payload,
                                           'exact collaboration payload required')
    text=w.safe_path(root,payload['path']).read_text()
    a.require(all(value in text for value in (snapshot['task_id'],x['business_scope'],x['source']['path'],
                  x['source']['sha256'],x['action']['action_id'],x['action']['scope'])),
              'collaboration body must retain original task/business source/action/physical tuple')
    return x

def _request(root,snapshot,pin):
    """Fresh PUB evidence binds the immutable source, never the old readonly grant."""
    import department_autonomy as a
    import goal_delivery_runtime as g
    req=a.document(root,pin);x=match(root,snapshot,req);a.require(x is not None,'registered CMS source required')
    action=x['action'];fields=action['changed_fields']
    a.require(req.get('professional_execution_source')==x['registration']
              and req.get('source_project_id')==a.PROJECT
              and req.get('operation')==('field_patch_rollback'if x['operation']=='rollback'else'field_patch') and req.get('object_ids')==[action['record_id']]
              and req.get('table')==action['table'] and req.get('slug')==action['slug']
              and req.get('business_scope')==x['business_scope'] and req.get('physical_scope')==action['scope']
              and req.get('changed_fields')==fields and req.get('desired')==x['desired'],
              'only the registered exact row/content fields/desired effect and both scopes may execute')
    before=a.document(root,req.get('before'));a.require(set(before)==set(x['protected_fields']['not_written_fields'])|set(fields)
              and all(before.get(k)==v for k,v in x['before'].items())
              and before.get('id')==action['record_id'] and before.get('slug')==action['slug']
              and isinstance(before.get('version'),int) and isinstance(before.get('updated_at'),str)
              and req.get('expected_updated_at')==before['updated_at'] and req.get('expected_version')==before['version'],
              'fresh complete original row/server CAS and unchanged two before fields required')
    intent=w.sha256_value({k:v for k,v in req.items()if k not in {'facts','self_check','backup','rollback'}})
    docs={}
    for name in ('facts','self_check','backup','rollback'):
        doc=a.document(root,req.get(name));docs[name]=doc
        a.require(all(doc.get(k)==req.get(k)for k in ('task_id','department','action_id','action_class','scope'))
                  and doc.get('intent_sha256')==intent, 'exact request-bound actual '+name+' required')
    a.require(docs['self_check'].get('status')=='PASS' and docs['facts'].get('current_row')==req['before']
              and docs['backup'].get('complete_row')==req['before']
              and docs['facts'].get('protected_preview') and docs['facts'].get('original_key_effect_lookup'),
              'successful PUB selfcheck, full row backup, zero-write preview and original-key lookup required')
    a.document(root,docs['facts']['protected_preview']);a.document(root,docs['facts']['original_key_effect_lookup'])
    inverse=docs['rollback']
    a.require(inverse.get('requires_completed_own_parent') is True
              and inverse.get('restore_fields')==x['before'] and inverse.get('server_CAS_fields_not_written')==['updated_at','version']
              and inverse.get('requires_fresh_post_Save_CAS') is True and inverse.get('requires_new_single_use_inverse_permit') is True,
              'own exact two-field inverse and future actual parent/post-Save CAS required')
    actions=[v for v in snapshot['goal_delivery'].get('approved_actions',[])if v.get('target_department')==x['executor']
             and v.get('professional_execution_source')==x['registration']]
    received={s.get('action_id')for s in g._collaboration_wait_states(root,snapshot)
              if (s.get('status'),s.get('proof_state')) in {('message_received','RECEIVED'),('result_received','PROVEN')}}
    a.require(any(v['action_id']in received for v in actions), 'original PUB must actually receive this precise execution collaboration; old readonly receipt is insufficient')
    a.require(a.sensitive_state(root,snapshot,req)['state']=='within_original_authorization','sensitive expansion is not this source')
    return {**x,'request':req,'pin':pin,'authorization':snapshot['goal_delivery']['authorization_pin'],
            'department':x['executor'],'preflight':{**{k:req[k]for k in ('task_id','department','action_id','action_class','scope','facts','self_check','backup','rollback')},
            'risk_level':'R2','request':pin,'source_registration':x['registration']}}

def record_preflight(root,task,input_path):
    import department_autonomy as a
    import goal_delivery_runtime as g
    item=a.document(root,w.file_digest(root,input_path))
    with w.workflow_lock(root):
        snapshot=g.restore_goal(root,w.read_json(w.snapshot_path(root,task)));x=_request(root,snapshot,item.get('request'))
        a.require(item.get('schema')=='professional-cms-fresh-preflight/v1' and item.get('task_id')==task,
                  'normal fresh PUB preflight envelope required')
        prior=[e['details']['professional_cms_preflight']for e in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS)
               if e.get('task_id')==task and e.get('details',{}).get('professional_cms_preflight',{}).get('action_id')==x['action']['action_id']]
        if prior and prior[-1]['request']==x['pin']:return {'result':'duplicate_ignored','external_permission_issued':False}
        w.append_workflow_event(root,task,snapshot['current_state'],{'professional_cms_preflight':{'action_id':x['action']['action_id'],'request':x['pin'],'source_registration':x['registration']}})
    return {'result':'recorded','request':x['pin'],'external_permission_issued':False,'actual_action_allowed':False}

def execution_context(root,snapshot,requested):
    import department_autonomy as a
    x=match(root,snapshot,requested)
    if x is None:return None
    rows=[e['details']['professional_cms_preflight']for e in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS)
          if e.get('task_id')==snapshot['task_id'] and e.get('details',{}).get('professional_cms_preflight',{}).get('action_id')==x['action']['action_id']]
    a.require(rows and rows[-1]['source_registration']==x['registration'],
              'source already registered; fresh received original PUB preflight/preview/CAS still required')
    context=_request(root,snapshot,rows[-1]['request'])
    a.require(requested.get('payload_sha256',context['pin']['sha256'])==context['pin']['sha256'], 'current exact PUB request hash required')
    return context

def status(root,task):
    import goal_delivery_runtime as g
    snapshot=g.restore_goal(root,w.read_json(w.snapshot_path(root,task)))
    return {'task_id':task,'registered_sources':records(root,snapshot),'collaboration_scopes':collaboration_scopes(root,snapshot),
            'actual_platform_permit_issued':False,'remote_channel_ready':'NOT_OBSERVED',
            'next_owner':snapshot['goal_delivery']['primary_owner'],'next_action':'original owner normally records exact PUB/WEB payload; original WEB supplies protected target/CLI/runtime only; original PUB obtains fresh actual execution evidence before any Save'}

if __name__ == '__main__':
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=['status']);parser.add_argument('--task-id',required=True)
    args=parser.parse_args()
    try:print(json.dumps(status(Path(__file__).resolve().parents[1],args.task_id),ensure_ascii=False,indent=2))
    except (w.WorkflowError,KeyError,ValueError) as error:parser.exit(1,str(error)+'\n')
