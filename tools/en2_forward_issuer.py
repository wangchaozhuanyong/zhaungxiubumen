"""EN2 forward issuer evidence. No function issues, dispatches or writes a permit."""
from pathlib import Path
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
import datetime as dt
import json
import workflow_control as w
import department_autonomy as a
import professional_cms_execution as src

MODEL='professional_en2_forward_selfcheck_v1'
NAME='english-kitchen-en2-exact-v1'
TASK=src._EN2_FORWARD_TASK
_ISSUER_READS=ContextVar('en2_issuer_request_reads', default=None)


def project_url(configured):
    """Use the exact existing EN2 Supabase binding when the local URL is unset."""
    from en2_supabase_origin import PROJECT
    pinned=f'https://{PROJECT}.supabase.co'
    a.require((configured or pinned) in (pinned,pinned+'/'),
              'Wrong Supabase project for original EN2 issuer')
    return pinned


@contextmanager
def issuer_request_reads():
    """Share authenticated inputs only within this issuer phase."""
    token=_ISSUER_READS.set({})
    try:
        yield
    finally:
        _ISSUER_READS.reset(token)


def _fresh_inputs(root, req, preview_at, now):
    facts=a.document(root,req['facts'])
    for label,observed in (('row',facts.get('observed_at')),('preview',preview_at)):
        timestamp=w._parse_observed_at(observed)
        a.require(timestamp and 0 <= (now-timestamp).total_seconds() <= 300,
                  'fresh '+label+' evidence required for original EN2 forward request')


def target(root):
    phase=_ISSUER_READS.get()
    if phase is None:
        return _read_target(root)
    key=Path(root).resolve()
    if key not in phase:
        phase[key]=_read_target(root)
    value=phase[key]
    req=a.document(root,value['preflight_request'])
    _fresh_inputs(root,req,value['preview_receipt_checked_at'],dt.datetime.now(dt.timezone.utc))
    return deepcopy(value)


def _read_target(root):
    """Derive a separate current target only from revalidated committed evidence."""
    import goal_delivery_runtime as g
    snapshot=g.restore_goal(root,w.read_json(w.snapshot_path(root,TASK)))
    evidence=src.en2_current_forward_evidence(root,snapshot)
    source,physical=src._en2_forward_source(root,snapshot)
    req=a.document(root,evidence['request']); before=a.document(root,req['before'])
    a.require(evidence.get('actual_action_allowed') is False and evidence.get('external_permission_issued') is False
              and evidence.get('source_event_id')==source['event_id']
              and req.get('professional_execution_source')==source['registration']
              and req.get('operation')=='field_patch' and req.get('rollback') is None
              and physical.get('rollbackAllowed') is False and physical.get('changedFields')==['title_en','excerpt_en']
              and len(physical.get('baselineProjectionFields',[]))==41
              and len(physical.get('retainedProjectionFields',[]))==37
              and sum(k.endswith('_ms') for k in physical['retainedProjectionFields'])==11
              and req.get('scope')==req.get('business_scope')==source['scope']
              and req.get('physical_scope')==physical['scope'] and req.get('department')=='publishing'
              and req.get('candidate_version')==physical['candidateVersion']
              and w.sha256_value(before)==physical['baselineFieldsSha256']
              and w.sha256_value(req['desired'])==physical['desiredFieldsSha256'],
              'exact revalidated EN2 forward preflight and original source required')
    events=[e for e in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS) if e.get('task_id')==TASK
            and e.get('event_id')==evidence['preflight_event_id']]
    a.require(len(events)==1, 'one exact committed preflight required')
    origin=events[0].get('details',{}).get('professional_cms_preflight',{}).get('provider_origin_evidence',{})
    a.require(type(origin.get('preview_run_id')) is int and origin['preview_run_id']>0
              and type(origin.get('preview_artifact_id')) is int and origin['preview_artifact_id']>0
              and isinstance(origin.get('preview_receipt_checked_at'),str),
              'committed protected preview identity required')
    return {'candidate_shape':MODEL,'namespace':NAME,'task_id':TASK,'action_id':physical['actionId'],
      'candidate_version':physical['candidateVersion'],'scope':source['scope'],'execution_scope':physical['scope'],
      'execution_owner':'publishing','record_id':physical['id'],'slug':physical['slug'],'table':physical['table'],
      'content_type':'service','changed_fields':physical['changedFields'],
      'candidate':(evidence['request']['path'],evidence['request']['sha256']),
      'rollback':(req['before']['path'],req['before']['sha256']),
      'payload_sha256':physical['desiredFieldsSha256'],'desired_fields_sha256':physical['desiredFieldsSha256'],
      'baseline_projection_fields':physical['baselineProjectionFields'],'baseline_fields_sha256':physical['baselineFieldsSha256'],
      'retained_fields_sha256':physical['retainedFieldsSha256'],'expected_updated_at':req['expected_updated_at'],
      'rollback_allowed':False,'source_registration':source['registration'],'source_event_id':source['event_id'],
      'preflight_event_id':evidence['preflight_event_id'],'preflight_request':evidence['request'],
      'preview_run_id':origin['preview_run_id'],'preview_artifact_id':origin['preview_artifact_id'],
      'preview_receipt_checked_at':origin['preview_receipt_checked_at'],
      'human_source':evidence['human_source'],'HQ_decision':evidence['HQ_decision']}


def exact(root, supplied):
    a.require(supplied.get('candidate_shape')==MODEL and supplied==target(root),
              'exact current EN2 admitted target, never source-only, required')
    return supplied


def candidate(root, value, supplied):
    exact(root,supplied)
    a.require(value==a.document(root,supplied['preflight_request']), 'exact actual PUB request bytes required')


def acceptance(root, supplied, operation):
    import goal_delivery_runtime as g
    a.require(operation=='publish','EN2 is forward-only; no inverse authority')
    exact(root,supplied);snapshot=g.restore_goal(root,w.read_json(w.snapshot_path(root,TASK)))
    events=[e for e in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS) if e.get('task_id')==TASK
            and e.get('event_id')==supplied['preflight_event_id']]
    a.require(len(events)==1 and events[0].get('details',{}).get('professional_cms_preflight',{}).get('request')==supplied['preflight_request']
              and events[0].get('event_hash') and events[0].get('created_at'), 'one actual committed exact PUB preflight event required')
    e=events[0]
    return {'acceptance_model':MODEL,'verdict':'selfcheck_ready','operation':'publish','task_id':TASK,
      'action_id':supplied['action_id'],'scope':supplied['scope'],'candidate_version':supplied['candidate_version'],
      'risk_level':'R2','receipt_id':e['event_id'],'receipt_hash':e['event_hash'],'created_at':e['created_at'],
      'authorization_pin':snapshot['goal_delivery']['authorization_pin'],
      'candidate':w.file_digest(root,supplied['candidate'][0]),'execution_preflight':supplied['preflight_request'],
      'execution_preflight_event_id':e['event_id'],'review_outbox':None,'review_plan':supplied['source_registration'],
      'goal_completion_claimed':False,'production_write_allowed':False}


def policy_context(root, supplied, operation, payload):
    import goal_delivery_runtime as g
    accepted=acceptance(root,supplied,operation);snapshot=g.restore_goal(root,w.read_json(w.snapshot_path(root,TASK)))
    requested={'task_id':TASK,'action_id':supplied['action_id'],'action_class':'cms_write',
               'scope':supplied['scope'],'department':'publishing'}
    ctx=src._en2_execution_context(root,snapshot,requested, verified_input={
        'request':supplied['preflight_request'],'action_id':supplied['action_id'],
        'human_source':supplied['human_source'],'HQ_decision':supplied['HQ_decision']})
    a.require(payload==supplied['payload_sha256'] and ctx['pin']==supplied['preflight_request'],
              'exact original desired digest and committed request required')
    return {'preflight':ctx['preflight'],'acceptance_model':MODEL,'risk_level':'R2','task_id':TASK,
            'action_id':supplied['action_id'],'scope':supplied['scope'],'department':'publishing',
            'payload_sha256':payload,'external_permission_issued':False}


def decision(root, value, supplied, operation, payload, accepted, now):
    a.require(accepted==acceptance(root,supplied,operation) and payload==supplied['payload_sha256'],
              'current selfcheck and original payload required')
    expected={'department':'publishing','decision':'EXECUTE_ORIGINAL_AUTHORIZED_ACTION','task_id':TASK,
      'action_id':supplied['action_id'],'action_class':'cms_write','scope':supplied['scope'],
      'candidate_version':supplied['candidate_version'],'record_id':supplied['record_id'],'payload_sha256':payload,
      'authorization_pin':accepted['authorization_pin'],'execution_preflight':accepted['execution_preflight'],
      'execution_preflight_event_id':accepted['execution_preflight_event_id']}
    a.require(all(value.get(k)==v for k,v in expected.items()) and isinstance(value.get('decision_id'),str)
              and value['decision_id'] and isinstance(value.get('actual_native'),dict)
              and isinstance(value.get('command_id'),str) and value['command_id'],
              'actual exact original PUB readiness and native command required')
    turn,call,raw=a.native_execution(root,value['actual_native'],value['command_id'],'publishing')
    try: native=json.loads(raw)
    except (TypeError,ValueError) as exc: raise w.WorkflowError('complete PUB native readiness JSON required') from exc
    a.require(native=={k:v for k,v in value.items() if k not in {'actual_native','command_id'}},
              'actual PUB native readiness must bind exact decision bytes')
    at=w._parse_observed_at(value.get('decided_at'));start=w._parse_observed_at(accepted['created_at'])
    a.require(at and start and start<=at<=now and (now-at).total_seconds()<=300
              and type(turn.get('startedAt')) in {int,float} and turn['startedAt']<=at.timestamp(),
              'fresh real publisher readiness after preflight required')
    return value


def consumed(root,row,supplied,operation,payload,ready,now):
    ctx=policy_context(root,supplied,operation,payload)
    key=w.sha256_value([TASK,'publishing',supplied['action_id'],'cms_write',supplied['scope']])
    expected={'task_id':TASK,'action_id':supplied['action_id'],'action_class':'cms_write',
              'scope':supplied['scope'],'department':'publishing'}
    from en2_preview_history import live_cms_policy_rows
    rows=live_cms_policy_rows(root)
    a.require(len(rows)==1 and rows[0]==row and all(row.get(k)==v for k,v in expected.items())
              and row.get('approval_basis')==a.MODE and row.get('mode_authorization')==a.OWNER
              and row.get('actual_action_allowed') is True and isinstance(row.get('decision_id'),str) and row['decision_id']
              and row.get('approval_status')=='consumed_for_original_exact_autonomous_action'
              and row.get('autonomous_action_key')==key and row.get('exact_request')==supplied['preflight_request']
              and row.get('payload_sha256')==supplied['preflight_request']['sha256']
              and row.get('original_authority')==ready['authorization_pin'],
              'one real original consumed same-request policy required')
    at=w._parse_observed_at(row.get('checked_at'));decided=w._parse_observed_at(ready.get('decided_at'))
    a.require(at and decided and decided<=at<=now and (now-at).total_seconds()<=300,
              'fresh readiness and one-time policy sequence required')
    return row


def artifacts(root,supplied,operation,qa,run,receipt,digest,backup):
    # acceptance authenticates the current committed preview with the provider.
    # Reuse that same issuer phase's verified target for the artifact comparison.
    a.require(qa==acceptance(root,supplied,operation),'current exact PUB selfcheck required')
    req=a.document(root,supplied['preflight_request'])
    a.require(run.get('id')==supplied['preview_run_id']
              and receipt.get('checked_at')==supplied['preview_receipt_checked_at']
              and receipt.get('action_id')==supplied['action_id'] and receipt.get('scope')==supplied['execution_scope']
              and digest.get('payload_sha256')==supplied['payload_sha256']
              and digest.get('expected_updated_at')==req['expected_updated_at']
              and backup.get('record')==a.document(root,req['before']),
              'real protected preview, original scope and exact fresh full41 backup required')


def reserve(root, supplied, policy, operation, payload, ready, request, validation, now):
    """Durably fence the logical action before the first issuer network call.

    A crash or ambiguous reply remains blocked for original-key investigation.
    This function neither calls a provider nor clears an existing reservation.
    """
    import os
    root=Path(root).resolve()
    key=w.sha256_value([TASK,'publishing',supplied['action_id'],'cms_write',supplied['scope']])
    path=root/'logs'/('en2-forward-issuer-once-'+key+'.json')
    with w.workflow_lock(root):
        validation.recheck()
        from en2_preview_history import NO_TRANSPORT_POLICY, ORIGINAL_ISSUER_INTENT, retired_receipts
        if len(retired_receipts(root))>=5:
            a.require(path==root/ORIGINAL_ISSUER_INTENT and policy.get('decision_id')!=NO_TRANSPORT_POLICY,
                      'v13 issuer reconciliation authorizes only a distinct fresh original policy')
            path=path.with_name(path.stem+'-issuer-project-refusal-successor.json')
        # The issue boundary rereads the authenticated sources and providers
        # independently of the earlier artifact and policy validation.
        with issuer_request_reads():
            consumed(root,policy,supplied,operation,payload,ready,now)
        a.require(request.get('taskId')==TASK and request.get('actionId')==supplied['action_id']
                  and request.get('scope')==supplied['execution_scope']
                  and request.get('policyDecisionId')==policy['decision_id']
                  and request.get('payloadSha256')==payload and request.get('operation')=='publish'
                  and isinstance(request.get('permitId'),str) and request['permitId'],
                  'one exact original EN2 issue intent required')
        current=dt.datetime.now(dt.timezone.utc)
        req=a.document(root,supplied['preflight_request'])
        _fresh_inputs(root,req,supplied['preview_receipt_checked_at'],current)
        for label,observed in (('policy',policy.get('checked_at')),('readiness',ready.get('decided_at'))):
            timestamp=w._parse_observed_at(observed)
            a.require(timestamp and 0 <= (current-timestamp).total_seconds() <= 300,
                      'fresh '+label+' evidence required immediately before EN2 issue intent')
        validation.recheck()
        value={'schema':'en2-forward-issuer-once/v1','task_id':TASK,'action_id':supplied['action_id'],
               'business_scope':supplied['scope'],'physical_scope':supplied['execution_scope'],
               'policy_decision_id':policy['decision_id'],'request_sha256':w.sha256_value(request),
               'permit_id_sha256':__import__('hashlib').sha256(request['permitId'].encode()).hexdigest(),
               'state':'ISSUE_INTENT_EFFECT_UNKNOWN','created_at':now.isoformat()}
        try:
            fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        except FileExistsError as exc:
            raise w.WorkflowError('original EN2 issuer intent already exists; inspect original key and unknown effect') from exc
        with os.fdopen(fd,'w',encoding='utf-8') as f:
            json.dump(value,f,sort_keys=True,separators=(',',':'));f.flush();os.fsync(f.fileno())
    return {'path':str(path.relative_to(root)),'sha256':w.file_digest(root,str(path.relative_to(root)))['sha256']}
