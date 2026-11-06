"""Authenticated single-field standing successor; source-only, never a permit."""
from pathlib import Path
import hashlib
import re
import workflow_control as w
import department_autonomy as a
import goal_delivery_runtime as g
import professional_cms_execution as cms

SCHEMA='professional-standing-single-field-pending-source/v1'
EVENT='professional_single_field_pending_source'

def _pin(root,pin):
    a.require(isinstance(pin,dict) and set(pin)=={'path','sha256','size'},'exact source pin required')
    p=Path(pin['path']); p=p if p.is_absolute() else Path(root)/p
    a.require(p.resolve().is_relative_to(Path(root).resolve()) and not p.is_symlink(),'project-owned source only')
    from goal_source_recovery import _normal_prepare_input_bytes
    b=_normal_prepare_input_bytes(root,p);a.require(hashlib.sha256(b).hexdigest()==pin['sha256'] and len(b)==pin['size'],'source bytes differ')
    import json
    return json.loads(b)

def _same_pin(root,left,right):
    if not isinstance(left,dict)or not isinstance(right,dict):return False
    def absolute(pin):
        p=Path(pin.get('path',''));return (p if p.is_absolute()else Path(root)/p).resolve()
    return (absolute(left)==absolute(right) and all(left.get(k)==right.get(k)for k in ('sha256','size')))

def validate(root,snapshot,item):
    root=Path(root).resolve();task=snapshot['task_id'];goal=snapshot['goal_delivery'];frozen=a.document(root,snapshot['goal_contract'])
    a.require(item.get('schema')==SCHEMA and item.get('task_id')==task and a.current_mode(root)
      and snapshot.get('current_state') not in w.TERMINAL_STATES | {'paused','suspended'}
      and all(goal.get(k)==frozen.get(k)for k in ('primary_owner','producer_departments','authorized_scope','human_authorization')),
      'active exact original goal, owner and authority required')
    source=_pin(root,item['WEB_input']);web=_pin(root,item['WEB_result']);native=_pin(root,item['WEB_completed_native'])
    a.require(source.get('schema')=='WEB-original-next8-05971-exact-normal-source-issuer-binding-gap/v1'
      and source.get('task_id')==task and source.get('scope')in goal['authorized_scope']
      and web.get('schema')=='WEB-actual-NEXT8-05971-one-field-source-channel-result/v1'
      and web.get('task_id')==task and web.get('scope')==source['scope']
      and web.get('candidate_source')==source.get('actual_candidate_source')
      and all(web.get('next_normal_source_binding_input',{}).get(k)==item['WEB_input'][k] for k in ('sha256','size'))
      and web.get('production_READY') is False and web.get('actual_execution_source_registered_for05971') is False,
      'exact original completed WEB report and input required')
    bind=w.read_json(root/'data/department-registry.json')['collaboration_bindings']['designated-development']
    thread=native.get('thread',{});turns=native.get('turns',[])
    a.require(thread.get('id')==bind.get('thread_id') and thread.get('title')==bind.get('title')
      and thread.get('cwd')==bind.get('cwd') and thread.get('hostId')==bind.get('host_id')
      and len(turns)==1 and turns[0].get('status')=='completed' and not turns[0].get('error'),
      'actual original completed WEB fixed identity required')
    finals=[x for x in turns[0].get('items',[])if x.get('type')=='agentMessage' and x.get('phase')=='final_answer']
    reportpath=str((root/item['WEB_result']['path']).resolve())
    a.require(len(finals)==1 and reportpath in finals[0].get('text','') and item['WEB_input']['path'] in finals[0].get('text',''),
      'original WEB final must identify these exact local result and input paths')
    candidate=_pin(root,source['actual_candidate_source']);proposal=_pin(root,source['new_single_field_binding_input']);pub=_pin(root,source['actual_PUB_result']);protection=_pin(root,source['protected_baseline_and_inverse'])
    import result_coordination as rc
    identity=rc.exact_identity(item['C1_result_identity']);a.require(identity['task_id']==task
      and identity['sender_department'] in frozen['producer_departments'],'original C1 result identity required')
    queued=rc._validate_queued(root,identity);box=a.document(root,queued['outbox'])
    summary=a.document(root,item['C1_result_summary'])
    received=rc._received_delivery(root,identity,{'target_department':goal['primary_owner']})
    a.require(item['C1_result_summary'] in box.get('evidence',[])and summary.get('task_id')==task
      and summary.get('owner')==goal['primary_owner']and summary.get('producer')==identity['sender_department']
      and summary.get('source')==source['actual_candidate_source']
      and all(summary.get('pub_result',{}).get(k)==source['actual_PUB_result'][k] for k in ('sha256','size'))
      and received and received.get('outbox')==queued['outbox'] and received.get('record_id')==item['C1_received_record'],
      'real original C1 result, PUB source and committed owner intake required')
    row=_pin(root,protection['baseline_source']); owner=goal['primary_owner']; object_id=proposal['record_id'];field='content_zh'
    a.require(candidate.get('task_id')==task and candidate.get('scope')==source['scope'] and candidate.get('owner')==owner
      and candidate.get('source_producer') in frozen['producer_departments'] and candidate.get('publishing_owner')=='publishing'
      and proposal.get('task_id')==task and proposal.get('candidate_source')==source['actual_candidate_source']
      and proposal.get('schema')=='WEB-proposed-single-field-source-target-not-registered/v1'
      and proposal.get('proposal_names_are_not_registered_actions_or_source_or_permission') is True
      and proposal.get('new_code_or_runtime_loading_is_not_claimed') is True
      and proposal.get('table')=='services' and proposal.get('changed_fields')==[field]
      and web.get('actual_record')==object_id
      and candidate.get('target',{}).get('record_id')==object_id and candidate['target'].get('slug')==proposal.get('slug')
      and candidate['target'].get('field')==field and pub.get('record_id')==object_id and pub.get('candidate')==source['actual_candidate_source']
      and pub.get('current',{}).get('row')==protection['baseline_source'] and row.get('id')==object_id and row.get('slug')==proposal['slug'],
      'exact original owner, producer, PUB, candidate and one-field object required')
    fields=set(row); ms={k for k in fields if k.endswith('_ms')};before=row[field];after=proposal['desired'][field];inverse=proposal['inverse_values'][field]
    a.require(len(row)==41 and len(ms)==11 and set(proposal['desired'])==set(proposal['inverse_values'])=={field}
      and set(protection['baselineProjectionFields'])==fields and set(protection['retainedProjectionFields'])==fields-{field,'updated_at','version'}
      and protection.get('protected_field_count')==38 and protection.get('MS_count')==11
      and inverse==before==candidate['historical_before'] and after==candidate['illustrative_after']
      and before.count(candidate['anchor_before'])==1 and after.count(candidate['exact_insert_text'])==1
      and after.replace('<p>'+candidate['exact_insert_text']+'</p>','',1)==before
      and hashlib.sha256(before.encode()).hexdigest()==candidate['historical_before_sha256']
      and hashlib.sha256(after.encode()).hexdigest()==candidate['illustrative_after_sha256']
      and w.sha256_value(row)==protection['dated_baselineFieldsSha256']
      and w.sha256_value({k:row[k]for k in protection['retainedProjectionFields']})==protection['dated_retainedFieldsSha256']
      and w.sha256_value(proposal['desired'])==proposal['desired_fields_sha256']==protection['desiredFieldsSha256']
      and w.sha256_value(proposal['inverse_values'])==proposal['inverse_fields_sha256']==protection['inverseFieldsSha256'],
      'exact single insertion and conditional inverse with full41/protect38/MS11 required')
    reverse=protection.get('conditional_inverse',{})
    a.require(reverse.get('only_field')==field and reverse.get('must_equal_own_forward_after_SHA')==candidate['illustrative_after_sha256']
      and reverse.get('inverse_value_SHA')==candidate['historical_before_sha256']
      and all(reverse.get(k) is None for k in ('required_own_completed_forward_permit_id','required_own_completed_forward_run_id',
       'required_actual_postSaveCAS','required_actual_postSaveVersion','required_new_independent_inverse_permission'))
      and reverse.get('inverse_issued_or_allowed') is False,'conditional inverse cannot imply a future permit or post-Save state')
    physical='company.example:services:'+object_id+':'+field
    a.require(source['only_object']==proposal['physical_scope']==protection['physical_scope']==physical,
      'exact physical scope required')
    old=[x for x in cms.records(root,snapshot)if _same_pin(root,x['registration'],source['original_standing_registration'])
      and x['action'].get('record_id')==object_id and x['action'].get('table')=='services'
      and x['action'].get('changed_fields')==['content_en','content_zh']]
    a.require(len(old)==1 and old[0]['owner']==owner and old[0]['executor']=='publishing'
      and _same_pin(root,old[0]['source'],source['historical_full_source']), 'actual original standing owner/executor lineage required')
    name=proposal.get('implementation_namespace_proposal');action=proposal.get('implementation_forward_action_proposal')
    a.require(isinstance(name,str)and re.fullmatch(r'[a-z0-9][a-z0-9-]{2,159}',name)and action=='publish-'+name,
      'exact proposed single-field namespace and action required')
    return {'task_id':task,'scope':source['scope'],'owner':owner,'executor':'publishing','record_id':object_id,
      'slug':proposal['slug'],'table':'services','field':field,'physical_scope':physical,'candidate_version':name,'action_id':action,
      'candidate':source['actual_candidate_source'],'dated_baseline':protection['baseline_source'],
      'baseline_fields_sha256':protection['dated_baselineFieldsSha256'],'desired_fields_sha256':proposal['desired_fields_sha256'],
      'inverse_fields_sha256':proposal['inverse_fields_sha256'],'retained_fields_sha256':protection['dated_retainedFieldsSha256'],
      'conditional_inverse':protection['conditional_inverse'],'runtime_loaded':'NOT_OBSERVED','original_key_effect':'UNKNOWN',
      'dated_baseline_not_fresh_CAS':True,'production_READY':False,'permit_issued':False,'actual_action_allowed':False}

def record(root,task,input_path):
    root=Path(root);pin=w.file_digest(root,input_path);item=a.document(root,pin)
    with w.workflow_lock(root),w.request_validation_context() as context:
        snapshot=g.restore_goal(root,w.read_json(w.snapshot_path(root,task)));a.require(item.get('task_id')==task,'exact task required')
        result=validate(root,snapshot,item)
        prior=[e for e in w.read_jsonl(root/w.WORKFLOW_EVENTS,where={'task_id':task})if e.get('details',{}).get(EVENT)]
        matches=[e for e in prior if e['details'][EVENT].get('candidate_version')==result['candidate_version']]
        if matches:
            a.require(len(matches)==1 and matches[0]['details'][EVENT]['source']==pin,'existing source must match exact bytes')
            return {'result':'duplicate_ignored','event_id':matches[0]['event_id'],'registration':pin,**result}
        context.recheck()
        event=w.append_workflow_event(root,task,snapshot['current_state'],{EVENT:{'source':pin,'candidate_version':result['candidate_version']},'frozen_contract_unchanged':True,'external_permission_issued':False})
        return {'result':'recorded','event_id':event['event_id'],'registration':pin,**result}

def pending_targets(root,task):
    root=Path(root);snapshot=w.read_json(w.snapshot_path(root,task));result={}
    for e in w.read_jsonl(root/w.WORKFLOW_EVENTS,where={'task_id':task}):
        bound=e.get('details',{}).get(EVENT)
        if not bound:continue
        v=validate(root,snapshot,a.document(root,bound['source']));name=v['candidate_version']
        a.require(name==bound['candidate_version'] and name not in result,'one exact pending target required')
        result[name]={'candidate_shape':'professional_cms_current_stage_pending_v1','task_id':task,'action_id':v['action_id'],
          'candidate_version':name,'scope':v['scope'],'execution_scope':v['physical_scope'],'execution_owner':v['executor'],
          'owner':v['owner'],'record_id':v['record_id'],'slug':v['slug'],'table':v['table'],'content_type':'service',
          'changed_fields':[v['field']],'candidate':(v['candidate']['path'],v['candidate']['sha256']),
          'rollback':(v['dated_baseline']['path'],v['dated_baseline']['sha256']),
          'payload_sha256':v['desired_fields_sha256'],'baseline_fields_sha256':v['baseline_fields_sha256'],
          'desired_fields_sha256':v['desired_fields_sha256'],'retained_fields_sha256':v['retained_fields_sha256'],
          'rollback_fields_sha256':v['inverse_fields_sha256'],'rollback_allowed':False,'conditional_inverse':v['conditional_inverse'],
          'source_registration':bound['source'],'source_event_id':e['event_id'],
          'issuer_contract':None,'issuer_registration_status':'NOT_REGISTERED','runtime_loaded':'NOT_OBSERVED',
          'original_key_effect':'UNKNOWN','dated_baseline_not_fresh_CAS':True,'actual_action_allowed':False,'permit_issued':False}
    return result
