"""Normal issuer adapter for authenticated, appended professional CMS sources."""
from pathlib import Path
import datetime as dt
import hashlib,json
import workflow_control as w
import department_autonomy as a
import professional_cms_execution as src
MODEL='professional_cms_source_selfcheck_v1'
EVENT='professional_cms_issuer_contract'

def external(root,pin,binding):
    p=Path(pin.get('path',''));allowed=Path(binding['cwd']).resolve()
    a.require(p.is_absolute() and p.resolve().is_relative_to(allowed) and not p.is_symlink(), 'exact original external WEB source path')
    b=p.read_bytes();a.require(hashlib.sha256(b).hexdigest()==pin.get('sha256') and len(b)==pin.get('size'),'exact external source bytes')
    return json.loads(b)

def validate_contract(root,snapshot,item):
    if item.get('channel_source_registration') is not None:
        from professional_cms_channel import issuer_context
        return issuer_context(root,snapshot,item)
    sources=[x for x in src.records(root,snapshot) if x['registration']==item.get('source_registration')]
    a.require(item.get('schema')=='professional-cms-issuer-contract/v1' and item.get('task_id')==snapshot['task_id']
              and len(sources)==1,'one real registered source for issuer contract')
    x=sources[0];original=a.document(root,x['source']);registry=w.read_json(Path(root)/'data/department-registry.json')
    binding=registry['collaboration_bindings'][x['channel']];web=external(root,item.get('WEB_delivery'),binding)
    action=x['action'];target=web.get('target',{});fields=action['changed_fields']
    baseline=a.document(root,original['original_source_baseline_only']['complete_row'])
    retained=x['protected_fields']['stable_business_readback_fields']
    expected={'id':action['record_id'],'slug':action['slug'],'contentType':action['content_type'],'table':action['table'],
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
        rows=[e['details'][EVENT]for e in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS)if e.get('task_id')==task and EVENT in e.get('details',{})
              and a.document(root,e['details'][EVENT]).get('target_name')==item.get('target_name')]
        if rows:
            a.require(rows==[pin],'original issuer contract already registered to different bytes')
            return {'result':'duplicate_ignored','registration':pin,'permit_issued':False}
        w.append_workflow_event(root,task,snapshot['current_state'],{EVENT:pin})
    return {'result':'recorded','registration':pin,'permit_issued':False,'remote_loaded':False}

def targets(root):
    # One catalog read shares completed-source proofs, never execution permits.
    with w.request_validation_context():return _targets(root)

def _targets(root):
    import goal_delivery_runtime as g
    result={}
    for event in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS):
        pin=event.get('details',{}).get(EVENT)
        if pin is None:continue
        snapshot=g.restore_goal(root,w.read_json(w.snapshot_path(root,event['task_id'])))
        # This is the executable catalog, not the historical source reader.
        # A closed goal retains its evidence but cannot advertise a new action.
        if snapshot.get('current_state') in w.TERMINAL_STATES:continue
        item=a.document(root,pin)
        x,original,t=validate_contract(root,snapshot,item);act=x['action'];name=act['candidate_version']
        a.require(name not in result,'ambiguous professional issuer target')
        result[name]={'candidate_shape':MODEL,'task_id':snapshot['task_id'],'action_id':act['action_id'],'candidate_version':name,
          'scope':x['business_scope'],'execution_scope':act['scope'],'execution_owner':x['executor'],'record_id':act['record_id'],
          'slug':act['slug'],'table':act['table'],'content_type':t['contentType'],'changed_fields':act['changed_fields'],
          'candidate':(x['source']['path'],x['source']['sha256']),
          'rollback':(original['original_source_baseline_only']['complete_row']['path'],original['original_source_baseline_only']['complete_row']['sha256']),
          'payload_sha256':t['desiredFieldsSha256'],'baseline_projection_fields':t['baselineProjectionFields'],
          'baseline_fields_sha256':t['baselineFieldsSha256'],'desired_fields_sha256':t['desiredFieldsSha256'],
          'retained_fields_sha256':t['retainedFieldsSha256'],'rollback_fields_sha256':t['rollbackFieldsSha256'],
          'expected_updated_at':t['expectedUpdatedAt'],'rollback_allowed':True,'source_registration':x['registration'],
          'issuer_contract':pin,'physical_target':t}
    return result

def exact(root,target):
    current=targets(root).get(target.get('candidate_version'))
    a.require(current==target,'exact fresh professional issuer registration required')
    return current

def candidate(root,value,target):
    exact(root,target);a.require(value==a.document(root,w.file_digest(root,target['candidate'][0])),'exact candidate source bytes required')

def acceptance(root,target,operation):
    import goal_delivery_runtime as g
    exact(root,target);a.require(operation in {'publish','rollback'},'known exact own operation')
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
