"""Normal issuer adapter for authenticated, appended professional CMS sources."""
from pathlib import Path
import datetime as dt
import hashlib,json
import workflow_control as w
import department_autonomy as a
import professional_cms_execution as src
MODEL='professional_cms_source_selfcheck_v1'
PENDING_STAGE_MODEL='professional_cms_current_stage_pending_v1'
EVENT='professional_cms_issuer_contract'

def _en2_source_observation(task_id, source, name, physical):
    """Project only an already authenticated source; never an executable target."""
    tuple_value=source.get('original_PUB_tuples',{}).get(name,{})
    a.require(source.get('protected_body_source_custody') is True and source.get('task')==task_id
      and source.get('owner')=='publishing' and tuple_value.get('execution_owner')=='publishing'
      and all(tuple_value.get(k)==v for k,v in {'task_id':task_id,'action_id':physical.get('actionId'),
          'candidate_version':physical.get('candidateVersion'),'record_id':physical.get('id'),
          'slug':physical.get('slug'),'table':physical.get('table'),'changed_fields':physical.get('changedFields'),
          'business_scope':source.get('scope'),'physical_scope':physical.get('scope'),
          'full_fields':41,'protect_fields':37,'MS_fields':11,'rollback_allowed':False}.items())
      and physical.get('taskId')==task_id and physical.get('changedFields')==['title_en','excerpt_en']
      and len(physical.get('baselineProjectionFields',[]))==41
      and len(physical.get('retainedProjectionFields',[]))==37
      and sum(k.endswith('_ms') for k in physical['retainedProjectionFields'])==11
      and physical.get('rollbackAllowed') is False,
      'exact authenticated EN2 task/actor/tuple/full41/protect37/MS11 source required')
    return {'candidate_shape':'professional_en2_full41_source_only_v1',
        'task_id':task_id,'action_id':physical['actionId'],'candidate_version':physical['candidateVersion'],
        'scope':source['scope'],'execution_scope':physical['scope'],'execution_owner':source['owner'],
        'record_id':physical['id'],'slug':physical['slug'],'table':physical['table'],
        'changed_fields':physical['changedFields'],'physical_target':physical,
        'source_registration':source['registration'],'source_event_id':source['event_id'],
        'baseline_is_current_CAS':False,'current_effect':'UNKNOWN','rollback_allowed':False,
        'actual_action_allowed':False,'permit_issued':False,'production_READY':False}

def external(root,pin,binding):
    p=Path(pin.get('path',''));allowed=Path(binding['cwd']).resolve()
    a.require(p.is_absolute() and p.resolve().is_relative_to(allowed) and not p.is_symlink(), 'exact original external WEB source path')
    try:
        from goal_source_recovery import _normal_prepare_input_bytes
        b=_normal_prepare_input_bytes(root,p)
    except FileNotFoundError:
        from professional_cms_source_custody import recovered_bytes
        b=recovered_bytes(root,pin)
    a.require(hashlib.sha256(b).hexdigest()==pin.get('sha256') and len(b)==pin.get('size'),'exact external source bytes')
    return json.loads(b)

def _single_field_contract(root,snapshot,item):
    # Match the actual already-registered source family, never a caller flag.
    import professional_cms_single_field_pending as pending
    registered=[e for e in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS,where={'task_id':snapshot['task_id']})
      if e.get('details',{}).get(pending.EVENT)
      and pending._same_pin(root,e['details'][pending.EVENT].get('source'),item.get('source_registration'))]
    if not registered:return None
    keys={'schema','task_id','source_registration','target_name','WEB_delivery','WEB_completed_result','WEB_completed_native','WEB_next_input'}
    a.require(set(item)==keys and item.get('schema')=='professional-cms-issuer-contract/v1'
      and item.get('task_id')==snapshot['task_id'] and len(registered)==1,
      'exact existing single-field issuer source and metadata-only contract required')
    event=registered[0];registration=event['details'][pending.EVENT]['source']
    original=a.document(root,registration);v=pending.validate(root,snapshot,original)
    a.require(v['candidate_version']==event['details'][pending.EVENT]['candidate_version']==item['target_name'],
      'original single-field source event and namespace required')
    registry=w.read_json(Path(root)/'data/department-registry.json');binding=registry['collaboration_bindings']['designated-development']
    delivery=external(root,item['WEB_delivery'],binding);result=external(root,item['WEB_completed_result'],binding)
    source=pending._pin(root,original['WEB_input']);proposal=pending._pin(root,source['new_single_field_binding_input'])
    before=pending._pin(root,v['dated_baseline']);retained=sorted(set(before)-{'content_zh','updated_at','version'})
    expected={'id':v['record_id'],'slug':v['slug'],'table':'services','contentType':'service','taskId':v['task_id'],
      'actionId':v['action_id'],'candidateVersion':v['candidate_version'],'scope':v['physical_scope'],
      'changedFields':['content_zh'],'baselineProjectionFields':sorted(before),
      'baselineFieldsSha256':v['baseline_fields_sha256'],'desiredFieldsSha256':v['desired_fields_sha256'],
      'rollbackFieldsSha256':v['inverse_fields_sha256'],'expectedUpdatedAt':before['updated_at'],
      'retainedProjectionFields':retained,'retainedFieldsSha256':v['retained_fields_sha256'],
      'rollbackAllowed':False,'requiresParentRun':True}
    a.require(len(before)==41 and len(retained)==38 and sum(k.endswith('_ms')for k in retained)==11
      and set(proposal['desired'])==set(proposal['inverse_values'])=={'content_zh'}
      and w.sha256_value(before)==expected['baselineFieldsSha256']
      and w.sha256_value(proposal['desired'])==expected['desiredFieldsSha256']
      and w.sha256_value(proposal['inverse_values'])==expected['rollbackFieldsSha256'],
      'actual single-field/full41/protect38/MS11 and unchanged forward/inverse digests required')
    a.require(delivery.get('schema')=='WEB-next8-zh05971-single-field-local-delivery/v1'
      and result.get('schema')=='WEB-next8-renovation-zh05971-actual-local-producer-result/v1'
      and delivery.get('task_id')==result.get('task_id')==v['task_id']
      and delivery.get('scope')==result.get('business_scope')==v['scope']
      and delivery.get('producer')==result.get('producer')=='designated-development'
      and delivery.get('producer_thread')==result.get('original_WEB_thread')==binding['thread_id']
      and delivery.get('producer_turn')==result.get('native_turn_id')
      and delivery.get('owner')==v['owner'] and delivery.get('execution_owner')==v['executor']
      and delivery.get('source_registration')==result.get('original_source_registration')==registration
      and delivery.get('source_event_id')==result.get('source_event_id')==event['event_id']
      and delivery.get('owner_source')==result.get('candidate_source')==v['candidate']
      and delivery.get('producer_report')==item['WEB_completed_result']
      and delivery.get('target')==result.get('exact_target')==expected
      and delivery.get('rollbackAllowed') is False and delivery.get('production_READY') is False
      and delivery.get('local_only') is True and result.get('stage')=='LOCAL_CODE_AND_VALIDATION_COMPLETE',
      'actual original WEB delivery/result/owner/source event and exact one-field target required')
    frozen=external(root,delivery.get('source_json'),binding)
    a.require(frozen.get('schema')=='next8-renovation-zh05971-single-field-frozen-source/v1'
      and result.get('frozen_source')==delivery['source_json'] and frozen.get('task_id')==v['task_id']
      and frozen.get('business_scope')==v['scope'] and frozen.get('execution_department')==v['executor']
      and frozen.get('source_registration')==registration and frozen.get('source_event_id')==event['event_id']
      and frozen.get('candidate_source')==v['candidate'] and pending._same_pin(root,frozen.get('baseline_source'),v['dated_baseline'])
      and frozen.get('runtime_target')==expected and frozen.get('before')==before
      and frozen.get('desired')==proposal['desired'] and frozen.get('inverse_values')==proposal['inverse_values']
      and frozen.get('conditional_inverse')==v['conditional_inverse']
      and frozen.get('registration_grants_write_authority') is False and frozen.get('baseline_is_current_CAS') is False
      and frozen.get('issuer_contract') is None and frozen.get('runtime_loaded')=='NOT_OBSERVED'
      and frozen.get('original_key_effect')=='UNKNOWN',
      'actual frozen one-field source body and conditional inverse; no synthetic forward tuple or runtime claim')
    cli=delivery.get('Node_CLI',{});runtime=delivery.get('runtime',{});permissions=result.get('runtime_and_permissions',{})
    a.require(cli.get('target')==v['candidate_version'] and cli.get('record_id')==v['record_id']
      and cli.get('scope')==v['physical_scope'] and cli.get('workflow')=='.github/workflows/content-publish-approved.yml'
      and cli.get('path')=='scripts/publish-content-trust-fixes.mjs'
      and runtime.get('issuer_contract') is None and runtime.get('runtime_loaded')=='NOT_OBSERVED'
      and permissions.get('issuer_contract') is None and permissions.get('production_READY') is False
      and permissions.get('new_policy_or_permit_issued') is False
      and all(type(permissions.get(k))is int and permissions[k]==0 for k in
        ('git_push','PR_create_or_update','merge','Pages_dispatch','R3_dispatch','Edge_deploy','CMS_preview','CMS_Save'))
      and delivery.get('git')==result.get('git') and delivery['git'].get('head') and delivery['git'].get('tree'),
      'actual local CLI/runtime/result metadata only; no execution or deployment claim')
    for pin in (cli.get('loader'),cli.get('entry'),cli.get('workflow_source'),runtime.get('target_source'),runtime.get('registry_source')):
        p=Path(pin.get('path','')) if isinstance(pin,dict)else Path()
        a.require(p.is_absolute() and p.resolve().is_relative_to(Path(binding['cwd']).resolve()) and not p.is_symlink(),
          'original external WEB artifact only')
        from goal_source_recovery import _normal_prepare_input_bytes
        raw=_normal_prepare_input_bytes(root,p);a.require(hashlib.sha256(raw).hexdigest()==pin.get('sha256') and len(raw)==pin.get('size'),
          'actual completed WEB artifact bytes changed')
    next_input=a.document(root,item['WEB_next_input'])
    a.require(next_input.get('schema')=='original-WEB-single-field-producer-to-SYS-issuer-input/v1'
      and next_input.get('task_id')==v['task_id'] and next_input.get('scope')==v['scope']
      and next_input.get('WEB_delivery')==item['WEB_delivery'] and next_input.get('WEB_completed_result')==item['WEB_completed_result']
      and next_input.get('source_registration')==registration and next_input.get('source_event_id')==event['event_id']
      and next_input.get('exact_target')==expected,'actual completed WEB next-input binds exact delivery/result/source')
    import goal_delivery_runtime as g
    native=g._native_document(root,item['WEB_completed_native']);thread=native.get('thread',{})
    turns=[t for t in native.get('turns',[])if t.get('id')==delivery['producer_turn']]
    a.require(all(thread.get(k)==binding[vv]for k,vv in {'id':'thread_id','title':'title','cwd':'cwd','hostId':'host_id'}.items())
      and len(turns)==1 and turns[0].get('status')=='completed' and not turns[0].get('error'),
      'actual completed original fixed WEB turn required')
    turn=turns[0];finals=[m for m in turn.get('items',[])if m.get('type')=='agentMessage' and m.get('phase')=='final_answer' and m.get('text','').strip()]
    start=turn.get('startedAt');finish=turn.get('completedAt')
    result_path=str(Path(item['WEB_completed_result']['path']).resolve());next_path=str(w.safe_path(root,item['WEB_next_input']['path']).resolve())
    a.require(type(start)in {int,float} and type(finish)in {int,float} and start<=finish<=dt.datetime.now(dt.timezone.utc).timestamp()
      and len(finals)==1 and result_path in finals[0]['text'] and next_path in finals[0]['text'],
      'real completed WEB chronology and final naming exact original result and next-input')
    target=pending.pending_targets(root,snapshot['task_id'])[v['candidate_version']]
    action={'task_id':v['task_id'],'action_id':v['action_id'],'candidate_version':v['candidate_version'],
      'record_id':v['record_id'],'slug':v['slug'],'table':v['table'],'scope':v['physical_scope'],
      'changed_fields':['content_zh'],'action_class':'cms_write'}
    return {'source_only_single_field_contract':True,'pending_target':target,'registration':registration,
      'action':action,'source':v['candidate'],'owner':v['owner'],'business_scope':v['scope'],
      'executor':v['executor'],'before':{'content_zh':before['content_zh']},'desired':proposal['desired'],
      'protected_fields':{'stable_business_readback_fields':retained},'baseline_pin':v['dated_baseline'],
      'permission_issued':False,'rollback_allowed':False},original,expected

def validate_contract(root,snapshot,item):
    if snapshot.get('current_state') in w.TERMINAL_STATES and item.get('schema') == 'professional-cms-issuer-contract/v1':
        from professional_cms_stage_issuer import contract
        return contract(root,snapshot,item)
    if item.get('channel_source_registration') is not None:
        from professional_cms_channel import issuer_context
        return issuer_context(root,snapshot,item)
    single=_single_field_contract(root,snapshot,item)
    if single is not None:return single
    sources=[x for x in src.records(root,snapshot) if x['registration']==item.get('source_registration')]
    a.require(item.get('schema')=='professional-cms-issuer-contract/v1' and item.get('task_id')==snapshot['task_id']
              and len(sources)==1,'one real registered source for issuer contract')
    x=sources[0];original=a.document(root,x['source']);registry=w.read_json(Path(root)/'data/department-registry.json')
    if x.get('original_explicit_delivery'):
        a.require(item.get('target_name') == x['action']['candidate_version']
                  and item.get('original_source_delivery') == x['owner_result'], 'exact original explicit issuer source namespace')
        return x, original, x['physical_target']
    binding=registry['collaboration_bindings'][x['channel']];web=external(root,item.get('WEB_delivery'),binding)
    action=x['action'];target=web.get('target',{});fields=action['changed_fields']
    from professional_cms_channel import baseline as source_baseline
    baseline=a.document(root,source_baseline(root,x))
    retained=x['protected_fields']['stable_business_readback_fields']
    content_type={'services':'service','blog_posts':'blog'}.get(action['table'])
    a.require(content_type is not None and action.get('content_type',content_type)==content_type,'exact supported table/content type')
    expected={'id':action['record_id'],'slug':action['slug'],'contentType':content_type,'table':action['table'],
      'taskId':snapshot['task_id'],'actionId':action['action_id'],'candidateVersion':action['candidate_version'],
      'scope':action['scope'],'changedFields':fields,'baselineProjectionFields':sorted(baseline),
      'baselineFieldsSha256':w.sha256_value(baseline),'desiredFieldsSha256':w.sha256_value(x['desired']),
      'rollbackFieldsSha256':w.sha256_value(x['before']),'expectedUpdatedAt':baseline['updated_at'],
      'retainedProjectionFields':sorted(retained),'retainedFieldsSha256':w.sha256_value({k:baseline[k]for k in retained}),
      'rollbackAllowed':True,'requiresParentRun':True}
    a.require(target==expected and web.get('task_id')==snapshot['task_id'] and web.get('scope')==x['business_scope']
              and web.get('producer')==x['channel'] and web.get('producer_thread')==binding['thread_id']
              and all(web.get('source_registration',{}).get(k)==x['registration'][k]for k in ('path','sha256'))
              and web.get('owner_source')==x['source'],'actual WEB target/CLI must match every registered source field/digest')
    frozen=external(root,web.get('source_json'),binding)
    a.require(frozen.get('before')==baseline and frozen.get('desired')==x['desired']
              and frozen.get('task_id')==snapshot['task_id'] and frozen.get('forward_tuple')==action,
              'real WEB frozen full29 before and exact desired/carrier required')
    cli=web.get('Node_CLI',{})
    a.require(cli.get('target')==action['candidate_version'] and cli.get('scope')==action['scope']
              and cli.get('record_id')==action['record_id'] and cli.get('workflow')=='.github/workflows/content-publish-approved.yml',
              'actual normal Node CLI target/workflow binding required')
    return x,original,target

def record_contract(root,task,path):
    import goal_delivery_runtime as g
    pin=w.file_digest(root,path);item=a.document(root,pin)
    with w.workflow_lock(root):
        snapshot=g.restore_goal(root,w.read_json(w.snapshot_path(root,task)));validate_contract(root,snapshot,item)
        if snapshot.get('current_state') in w.TERMINAL_STATES:
            # The stage event already durably binds this exact original contract.
            # Never append to the closed business parent or enable issuance here.
            from professional_cms_stage_issuer import catalog
            groups=catalog(root,task)
            a.require(len(groups)==1 and any(row['contract']==pin for row in groups[0]['records']),
                      'exact original current-stage contract pin required')
            return {'result':'already_registered_in_current_stage','registration':pin,
                    'stage_event_id':groups[0]['event_id'],'permit_issued':False,'remote_loaded':False,
                    'actual_action_allowed':False}
        rows=[e['details'][EVENT]for e in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS)if e.get('task_id')==task and EVENT in e.get('details',{})
              and a.document(root,e['details'][EVENT]).get('target_name')==item.get('target_name')]
        if rows:
            a.require(rows==[pin],'original issuer contract already registered to different bytes')
            return {'result':'duplicate_ignored','registration':pin,'permit_issued':False}
        w.append_workflow_event(root,task,snapshot['current_state'],{EVENT:pin})
    return {'result':'recorded','registration':pin,'permit_issued':False,'remote_loaded':False}

def targets(root, *, task_id=None):
    # The optional exact-task view is read-only; the global issuer catalog
    # still validates all targets and collision checks before any issue.
    if task_id is not None: w.validate_task_id(task_id)
    with w.request_validation_context():return _targets(root,task_id=task_id)

def _targets(root, *, task_id=None):
    import goal_delivery_runtime as g
    result={}
    for event in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS):
        pin=event.get('details',{}).get(EVENT)
        if pin is None or (task_id is not None and event.get('task_id')!=task_id):continue
        snapshot=g.restore_goal(root,w.read_json(w.snapshot_path(root,event['task_id'])))
        # This is the executable catalog, not the historical source reader.
        # A closed goal retains its evidence but cannot advertise a new action.
        if snapshot.get('current_state') in w.TERMINAL_STATES:continue
        item=a.document(root,pin)
        x,original,t=validate_contract(root,snapshot,item);act=x['action'];name=act['candidate_version']
        a.require(name not in result,'ambiguous professional issuer target')
        if x.get('source_only_single_field_contract'):
            if task_id is None:continue  # Local contract is not an executable global target.
            result[name]={**x['pending_target'],'issuer_contract':pin,
              'issuer_registration_status':'REGISTERED_LOCAL_SOURCE_ONLY',
              'source_only_single_field_contract':True,'physical_target':t,'WEB_delivery':item['WEB_delivery']}
            continue
        result[name]={'candidate_shape':MODEL,'task_id':snapshot['task_id'],'action_id':act['action_id'],'candidate_version':name,
          'scope':x['business_scope'],'execution_scope':act['scope'],'execution_owner':x['executor'],'record_id':act['record_id'],
          'slug':act['slug'],'table':act['table'],'content_type':t['contentType'],'changed_fields':act['changed_fields'],
          'candidate':(x['source']['path'],x['source']['sha256']),
          'rollback':_baseline_tuple(root,x),
          'payload_sha256':t['desiredFieldsSha256'],'baseline_projection_fields':t['baselineProjectionFields'],
          'baseline_fields_sha256':t['baselineFieldsSha256'],'desired_fields_sha256':t['desiredFieldsSha256'],
          'retained_fields_sha256':t['retainedFieldsSha256'],'rollback_fields_sha256':t['rollbackFieldsSha256'],
          'expected_updated_at':t['expectedUpdatedAt'],'rollback_allowed':True,'source_registration':x['registration'],
          'issuer_contract':pin,'physical_target':t}
    # Registered legacy current-stage contracts are discoverable, but are
    # explicitly non-executable until their independent live gates are proven.
    from professional_cms_stage_issuer import EVENT as STAGE_EVENT, catalog as stage_catalog
    tasks={e['details'][STAGE_EVENT]['task_id'] for e in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS)
           if STAGE_EVENT in e.get('details',{})}
    for task in tasks:
        if task_id is not None and task!=task_id:continue
        for group in stage_catalog(root,task):
            for row in group['records']:
                act=row['action'];t=row['target'];name=act['candidate_version']
                a.require(name not in result,'professional current-stage target collision')
                result[name]={'candidate_shape':PENDING_STAGE_MODEL,'task_id':task,
                    'action_id':act['action_id'],'candidate_version':name,'scope':act['physical_scope'],
                    'execution_scope':act['physical_scope'],'execution_owner':act['department'],
                    'owner':act['owner'],'record_id':act['record_id'],'slug':act['slug'],
                    'table':act['table'],'content_type':'service','changed_fields':act['changed_fields'],
                    'candidate':(row['source_registration']['path'],row['source_registration']['sha256']),
                    'rollback':(act['dated_full41']['path'],act['dated_full41']['sha256']),
                    'payload_sha256':t['desiredFieldsSha256'],'baseline_projection_fields':t['baselineProjectionFields'],
                    'baseline_fields_sha256':t['baselineFieldsSha256'],'desired_fields_sha256':t['desiredFieldsSha256'],
                    'retained_fields_sha256':t['retainedFieldsSha256'],'rollback_fields_sha256':t['rollbackFieldsSha256'],
                    'expected_updated_at':t['expectedUpdatedAt'],'rollback_allowed':False,
                    'source_registration':row['source_registration'],'issuer_contract':row['contract'],
                    'stage_registration':group['registration'],'stage_event_id':group['event_id'],
                    'physical_target':t,'runtime_loaded':'NOT_OBSERVED','original_key_effect':'UNKNOWN',
                    'actual_action_allowed':False,'permit_issued':False}
    # Active-stage WEB tuples are available only in an exact-task source view.
    # They remain PENDING and cannot become an issuer/permit grant here.
    if task_id is not None:
        from professional_cms_single_field_pending import pending_targets as single_field_pending_targets
        for name, item in single_field_pending_targets(root, task_id).items():
            if name in result:
                registered=result[name]
                a.require(registered.get('source_only_single_field_contract') is True
                  and all(registered.get(k)==v for k,v in item.items() if k not in {'issuer_contract','issuer_registration_status'}),
                  'single-field issuer contract must preserve every original pending source fact')
                continue
            result[name] = item
        from professional_cms_active_web_target import pending_targets
        for name, item in pending_targets(root, task_id).items():
            a.require(name not in result, 'professional issuer target collision')
            result[name] = item
        # An existing source-only EN2 event exposes its authenticated full-row
        # carrier for exact-task inspection only. It is deliberately excluded
        # from the global executable catalog and does not create an issuer grant.
        from professional_cms_channel import ORIGINAL_BODY_EVENT, original_body_records
        sources=[e.get('details',{}).get(ORIGINAL_BODY_EVENT) for e in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS,
                 where={('details',ORIGINAL_BODY_EVENT,'target_task_id'):task_id})
                 if e.get('details',{}).get(ORIGINAL_BODY_EVENT,{}).get('target_task_id')==task_id]
        a.require(len(sources)<=1,'one exact original body source only')
        if sources and a.document(root,sources[0]['source']).get('schema')=='original-protected-EN2-fields-WEB-source/v1':
            snapshot=w.read_json(w.snapshot_path(root,task_id))
            a.require(snapshot.get('current_state') not in w.TERMINAL_STATES | {'paused','suspended'},
                      'paused or terminal EN2 source cannot be projected')
            rows=original_body_records(root,task_id)
            a.require(len(rows)==1 and rows[0].get('protected_body_source_custody') is True,
                      'one authenticated original EN2 source required')
            source=rows[0]
            for name,physical in source['registered_protected_body_targets'].items():
                a.require(name not in result,'professional issuer target collision')
                result[name]=_en2_source_observation(task_id,source,name,physical)
    for name, item in _singlefield_admission_targets(root, task_id=task_id).items():
        if name in result:
            old=result[name]
            a.require(old.get('candidate_shape')==PENDING_STAGE_MODEL
              and old.get('source_only_single_field_contract') is True
              and old.get('source_registration')==item['pending_source_registration']
              and old.get('source_event_id')==item['pending_source_event_id']
              and old.get('issuer_contract')==item['issuer_contract']
              and old.get('physical_target')==item['physical_target']
              and all(old.get(k)==item.get(k) for k in ('task_id','action_id','candidate_version','record_id',
                    'slug','table','changed_fields','execution_scope','execution_owner','payload_sha256',
                    'baseline_fields_sha256','desired_fields_sha256','retained_fields_sha256','rollback_fields_sha256')),
              'only the exact authenticated pending/local-contract and new production admission may share a namespace')
        result[name]=item
    return result


def _singlefield_admission_targets(root, *, task_id=None):
    """Add a source-verified forward view; never mutate an old PENDING record.

    Historical source/native authenticity is checked here. A fresh executor
    preflight, original keys/CAS, policy, once and permit remain separate gates.
    """
    import goal_delivery_runtime as g
    from professional_cms_single_field_admission import ADMISSION_SCHEMA, base_source_validation
    events=w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS,where={'task_id':task_id} if task_id else None)
    tasks=set()
    for event in events:
        pin=event.get('details',{}).get(src.EVENT)
        if pin is not None and a.document(root,pin).get('schema')==ADMISSION_SCHEMA:
            tasks.add(event['task_id'])
    result={}
    for task in sorted(tasks):
        snapshot=g.restore_goal(root,w.read_json(w.snapshot_path(root,task)))
        if snapshot.get('current_state') in w.TERMINAL_STATES|{'paused','suspended','user_paused'}:continue
        for x in src.records(root,snapshot):
            if not x.get('singlefield_forward_admission'):continue
            action=x['action'];name=action['candidate_version'];physical=x['physical_target']
            a.require(name not in result and x.get('rollback_allowed') is False
              and x.get('executor')=='publishing' and action.get('changed_fields')==['content_zh']
              and physical.get('rollbackAllowed') is False and physical.get('changedFields')==['content_zh'],
              'one authenticated forward-only single-field production view')
            contract=x['local_issuer_contract']
            originals=[event for event in events if event.get('task_id')==task
                       and event.get('details',{}).get(EVENT)==contract]
            a.require(len(originals)==1,'original actually registered local issuer contract must remain present')
            with base_source_validation():
                original,_,target=validate_contract(root,snapshot,a.document(root,contract))
            pending=original.get('pending_target',{})
            a.require(original.get('source_only_single_field_contract') is True and target==physical
              and pending.get('source_registration')==x.get('pending_source_registration')
              and pending.get('source_event_id')==x.get('pending_source_event_id')
              and pending.get('task_id')==task and pending.get('action_id')==action.get('action_id')
              and pending.get('candidate_version')==name and pending.get('record_id')==action.get('record_id')
              and pending.get('changed_fields')==['content_zh']
              and all(physical.get(k)==action.get(v) for k,v in {'taskId':'task_id','actionId':'action_id',
                  'candidateVersion':'candidate_version','id':'record_id','slug':'slug','table':'table','scope':'scope'}.items()),
              'new source must pair exactly with its original pending event/local target; no borrowed source or namespace')
            baseline=a.document(root,x['baseline_pin']);retained=x['protected_fields']['stable_business_readback_fields']
            a.require(len(baseline)==41 and len(retained)==38 and len({f for f in baseline if f.endswith('_ms')})==11
              and physical.get('baselineProjectionFields')==sorted(baseline)
              and physical.get('retainedProjectionFields')==sorted(retained)
              and physical.get('baselineFieldsSha256')==w.sha256_value(baseline)
              and physical.get('retainedFieldsSha256')==w.sha256_value({f:baseline[f] for f in retained})
              and physical.get('expectedUpdatedAt')==baseline.get('updated_at')
              and physical.get('desiredFieldsSha256')==w.sha256_value(x['desired'])
              and physical.get('rollbackFieldsSha256')==w.sha256_value(x['before']),
              'exact immutable full41/protect38/MS11/single-field source; execution-time CAS is never inferred')
            result[name]={'candidate_shape':MODEL,'task_id':task,'action_id':action['action_id'],'candidate_version':name,
              'scope':x['business_scope'],'execution_scope':action['scope'],'execution_owner':x['executor'],
              'owner':x['owner'],'record_id':action['record_id'],'slug':action['slug'],'table':action['table'],
              'content_type':physical['contentType'],'changed_fields':['content_zh'],
              'candidate':(x['source']['path'],x['source']['sha256']),
              'rollback':(x['baseline_pin']['path'],x['baseline_pin']['sha256']),
              'payload_sha256':physical['desiredFieldsSha256'],'baseline_projection_fields':physical['baselineProjectionFields'],
              'baseline_fields_sha256':physical['baselineFieldsSha256'],'desired_fields_sha256':physical['desiredFieldsSha256'],
              'retained_fields_sha256':physical['retainedFieldsSha256'],'rollback_fields_sha256':physical['rollbackFieldsSha256'],
              'expected_updated_at':physical['expectedUpdatedAt'],'rollback_allowed':False,
              'source_registration':x['registration'],'issuer_contract':contract,'physical_target':physical,
              'singlefield_forward_admission':True,'admission_event_id':x['event_id'],
              'pending_source_registration':x['pending_source_registration'],'pending_source_event_id':x['pending_source_event_id']}
    return result

def _baseline_tuple(root,source):
    from professional_cms_channel import baseline
    pin=baseline(root,source)
    return pin['path'],pin['sha256']

def exact(root,target):
    # A pending-stage lookup uses only its exact registered parent. Actual
    # issuance is forbidden for that shape by the issuer and acceptance gates.
    only=target.get('task_id') if target.get('candidate_shape')==PENDING_STAGE_MODEL else None
    current=targets(root,task_id=only).get(target.get('candidate_version'))
    a.require(current==target,'exact fresh professional issuer registration required')
    return current

def candidate(root,value,target):
    exact(root,target)
    a.require(target.get('candidate_shape')!=PENDING_STAGE_MODEL,'pending current-stage source is not execution admission')
    a.require(value==a.document(root,w.file_digest(root,target['candidate'][0])),'exact candidate source bytes required')

def pending_stage_preflight(root,target,operation,request):
    # Discover and bind the exact current-stage tuple. This is a read-only
    # pending assessment, never a selfcheck PASS or permission to issue.
    exact(root,target)
    a.require(target.get('candidate_shape')==PENDING_STAGE_MODEL and operation=='publish',
              'only exact current-stage forward metadata is admitted')
    expected={'task_id':target['task_id'],'action_id':target['action_id'],
      'candidate_version':target['candidate_version'],'department':target['execution_owner'],
      'scope':target['execution_scope'],'record_id':target['record_id'],
      'source_registration':target['source_registration'],'issuer_contract':target['issuer_contract']}
    a.require(isinstance(request,dict) and set(request)==set(expected) and request==expected,
              'exact original task/action/version/owner/record/scope and source pins required')
    return {'status':'BLOCKED_PENDING_ACTUAL_EXECUTION_GATES','task_id':target['task_id'],
      'action_id':target['action_id'],'candidate_version':target['candidate_version'],
      'record_id':target['record_id'],'original_key_effect':'UNKNOWN',
      'runtime_loaded':'NOT_OBSERVED','issuer_identity':'NOT_OBSERVED',
      'required':['actual_authorized_runtime_target','original_key_effect_readback',
        'fresh_full41_microsecond_CAS_and_backup','PUB_native_preflight_and_zero_write_preview',
        'independent_fresh_policy_and_single_use_permit'],
      'actual_action_allowed':False,'permit_issued':False,'production_READY':False}

def acceptance(root,target,operation):
    import goal_delivery_runtime as g
    exact(root,target);a.require(operation in {'publish','rollback'},'known exact own operation')
    if target.get('singlefield_forward_admission'):
        a.require(operation=='publish' and target.get('rollback_allowed') is False,
                  'single-field production admission does not authorize an inverse')
    a.require(target.get('candidate_shape')!=PENDING_STAGE_MODEL,
              'current-stage target discovered; actual runtime/key/PUB preflight and issuer gates not admitted')
    snapshot=g.restore_goal(root,w.read_json(w.snapshot_path(root,target['task_id'])))
    action=target['action_id']if operation=='publish'else'rollback-'+target['candidate_version']
    context=src.execution_context(root,snapshot,{'task_id':target['task_id'],'action_id':action,'action_class':'cms_write','scope':target['scope'],'department':target['execution_owner']})
    req=context['request'];before=a.document(root,req['before']);fields=target['changed_fields']
    baseline=a.document(root,w.file_digest(root,target['rollback'][0]));stable=context['protected_fields']['stable_business_readback_fields']
    a.require(all(before[k]==baseline[k]for k in stable),'all25 retained fields including MS6 must match source')
    if operation=='publish':a.require(w.sha256_value(before)==target['baseline_fields_sha256'],'actual fresh full29 must match protected locked target baseline')
    else:
        parent=a.document(root,req['facts']);parent=a.document(root,parent.get('completed_parent'))
        a.require(parent.get('status')=='completed' and parent.get('operation')=='publish'
           and parent.get('taskId')==target['task_id']and parent.get('actionId')==target['action_id']
           and parent.get('candidateVersion')==target['candidate_version']and parent.get('savedId')==target['record_id']
           and parent.get('permitId')==req.get('parent_permit_id') and parent.get('githubRunId')==req.get('parent_run_id')
           and type(req.get('parent_run_id'))is int and req['parent_run_id']>0
           and parent.get('savedUpdatedAt')==before['updated_at'],'own completed parent and exact current postSave CAS required')
    rows=[e for e in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS)if e.get('task_id')==target['task_id']
          and e.get('details',{}).get('professional_cms_preflight',{}).get('request')==context['pin']]
    a.require(len(rows)==1,'one exact committed professional selfcheck event')
    event=rows[0]
    return {'acceptance_model':MODEL,'verdict':'selfcheck_ready','operation':operation,'task_id':target['task_id'],'action_id':action,
      'scope':target['scope'],'candidate_version':target['candidate_version']+('-rollback-v1'if operation=='rollback'else''),
      'risk_level':'R2','receipt_id':event['event_id'],'receipt_hash':event['event_hash'],'created_at':event['created_at'],
      'authorization_pin':snapshot['goal_delivery']['authorization_pin'],'candidate':w.file_digest(root,target['candidate'][0]),
      'execution_preflight':context['pin'],'execution_preflight_event_id':event['event_id'],
      'review_outbox':context['owner_result'],'review_plan':context['registration'],
      'parent_permit_id':req.get('parent_permit_id'),'parent_run_id':req.get('parent_run_id'),
      'production_write_allowed':False}

def policy_context(root,target,operation,payload):
    import goal_delivery_runtime as g
    accepted=acceptance(root,target,operation);snapshot=g.restore_goal(root,w.read_json(w.snapshot_path(root,target['task_id'])))
    context=src.execution_context(root,snapshot,{'task_id':target['task_id'],'action_id':accepted['action_id'],'action_class':'cms_write','scope':target['scope'],'department':target['execution_owner']})
    expected=target['payload_sha256']if operation=='publish'else target['rollback_fields_sha256']
    a.require(payload==expected,'exact actual two-field operator payload digest required')
    return {'preflight':{**context['preflight'],'payload_sha256':payload},'acceptance_model':MODEL,'risk_level':'R2',
            'task_id':target['task_id'],'action_id':accepted['action_id'],'scope':target['scope'],'department':target['execution_owner'],
            'payload_sha256':payload,'external_permission_issued':False}

def decision(root,value,target,operation,payload,accepted,now):
    current=acceptance(root,target,operation);a.require(current==accepted,'current exact own selfcheck evidence')
    expected={'department':target['execution_owner'],'decision':'EXECUTE_ORIGINAL_AUTHORIZED_ACTION','task_id':target['task_id'],
      'action_id':accepted['action_id'],'action_class':'cms_write','scope':target['scope'],'candidate_version':accepted['candidate_version'],
      'record_id':target['record_id'],'payload_sha256':payload,'authorization_pin':accepted['authorization_pin'],
      'execution_preflight':accepted['execution_preflight'],'execution_preflight_event_id':accepted['execution_preflight_event_id']}
    at=w._parse_observed_at(value.get('decided_at'));start=w._parse_observed_at(accepted['created_at'])
    a.require(all(value.get(k)==v for k,v in expected.items())and value.get('decision_id')and at and start<=at<=now
              and (now-at).total_seconds()<=300,'fresh actual executor readiness; no HQ/assistant approval substitute')
    return value

def consumed(root,row,target,operation,payload,ready,now):
    ctx=policy_context(root,target,operation,payload)
    a.require(row.get('status')=='allow' and row.get('approval_basis')==a.MODE
      and row.get('approval_status')=='consumed_for_original_exact_autonomous_action'
      and all(row.get(k)==ctx[k]for k in ('task_id','action_id','scope','department'))
      and row.get('action_class')=='cms_write' and row.get('payload_sha256')==ready.get('execution_preflight',{}).get('sha256')
      and row.get('exact_request')==ready.get('execution_preflight'),'exact consumed current original request policy')
    at=w._parse_observed_at(row.get('checked_at'));decided=w._parse_observed_at(ready.get('decided_at'))
    a.require(at and decided<=at<=now and (now-at).total_seconds()<=300,'fresh single original policy sequence')
    return row

def artifacts(root,target,operation,qa,receipt,digest,backup,parent_permit,parent_run):
    a.require(qa==acceptance(root,target,operation),'current operator selfcheck before artifacts')
    row=backup.get('record');req=a.document(root,qa['execution_preflight'])
    a.require(isinstance(row,dict) and row==a.document(root,req['before']) and row.get('id')==target['record_id'],'real protected full-row artifact equals exact fresh operator snapshot')
    action=qa['action_id'];expected=target['payload_sha256']if operation=='publish'else target['rollback_fields_sha256']
    a.require(receipt.get('action_id')==action and digest.get('payload_sha256')==expected
              and digest.get('expected_updated_at')==row.get('updated_at'),'protected artifact binds exact current row/CAS and two-field payload')
    if operation=='rollback':a.require(parent_permit==qa['parent_permit_id']and parent_run==qa['parent_run_id'],
                                      'CLI inverse arguments match own reviewed actual completed parent')
