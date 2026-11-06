"""Original PUB provider-origin reads for one authenticated forward-only source.

Context must come from the work-order/admission validator. Pure validators do
not authenticate caller files. read_actual re-reads existing official native
history and GitHub GET/archive data; it never executes SQL, dispatches work,
creates a permit, extracts arbitrary archives, or writes files/credentials.
"""
from pathlib import Path
import datetime as dt
import copy
import contextvars
import functools
import hashlib
import io
import json
import re
import subprocess
import zipfile
import workflow_control as w

WORKFLOW = '.github/workflows/content-publish-approved.yml'
COLUMNS = ('permit_id,task_id,action_id,operation,scope,candidate_version,record_id,slug,'
           'expected_updated_at,github_run_id,github_run_attempt,policy_decision_id,'
           'issued_at,expires_at,status,claimed_at,writing_at,completed_at,saved_id,saved_updated_at')
ARTIFACT_FILES = ('locked-candidate.json','desired.json','dry-run.json',
                  'locked-dry-run-receipt.json','managed-payload-digest.json',
                  'managed-identity-probe.json','backup.json')


def need(ok, message):
    if not ok:
        raise w.WorkflowError('singlefield PUB provider: '+message)


def unique(pairs):
    result = {}
    for key, value in pairs:
        need(key not in result, 'duplicate provider JSON field')
        result[key] = value
    return result


def loads(raw):
    return json.loads(raw, object_pairs_hook=unique,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError('nonfinite provider JSON')))


def _context(ctx):
    need(isinstance(ctx,dict) and isinstance(ctx.get('target'),dict)
         and isinstance(ctx.get('web_context'),dict) and isinstance(ctx.get('pub_binding'),dict),
         'authenticated context and fixed provider bindings required')
    target = ctx['target']; web = ctx['web_context']
    project = ctx.get('project_ref',web.get('project_ref'))
    need(isinstance(project,str) and re.fullmatch('[a-z0-9]+',project)
         and re.fullmatch('[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',str(web.get('repository')))
         and type(web.get('repository_id')) is int and web['repository_id']>0
         and type(web.get('actor_id')) is int and web['actor_id']>0
         and re.fullmatch('[0-9a-f]{40}',str(web.get('commit'))), 'exact real project/repository/actor/main required')
    w.validate_task_id(ctx.get('task'))
    need(target.get('taskId')==ctx['task'] and target.get('table')=='services'
         and re.fullmatch('[0-9a-f-]{36}',str(target.get('id')))
         and re.fullmatch('[a-z0-9-]+',str(target.get('slug')))
         and re.fullmatch('[a-z0-9-]+',str(target.get('candidateVersion')))
         and target.get('actionId')=='publish-'+target['candidateVersion']
         and target.get('changedFields')==['content_zh'] and target.get('rollbackAllowed') is False
         and target.get('scope')=='company.example:services:'+target['id']+':content_zh'
         and isinstance(target.get('baselineProjectionFields'),list)
         and len(target['baselineProjectionFields'])==len(set(target['baselineProjectionFields']))==41
         and isinstance(target.get('retainedProjectionFields'),list)
         and len(target['retainedProjectionFields'])==len(set(target['retainedProjectionFields']))==38
         and set(target['retainedProjectionFields'])==set(target['baselineProjectionFields'])-{'content_zh','updated_at','version'}
         and sum(k.endswith('_ms') for k in target['retainedProjectionFields'])==11,
         'one real forward-only service full41/protect38/MS11 target required')
    return target,web,project


def sql_queries(ctx):
    """Generate only the original exact row and complete effect SELECTs."""
    t,_,_ = _context(ctx);record=t['id'];task=ctx['task'];action=t['actionId'];version=t['candidateVersion']
    return {
      'row':"SELECT clock_timestamp()::text AS server_observed_at, row_to_json(s)::text AS raw_full_record FROM public.services AS s WHERE s.id::text='"+record+"' AND s.slug='"+t['slug']+"';",
      'key':f"select {COLUMNS} from public.managed_cms_release_permits where record_id::text='{record}' and (task_id='{task}' or action_id='{action}' or candidate_version='{version}') order by issued_at,permit_id;",
      'same_row':f"select {COLUMNS} from public.managed_cms_release_permits where record_id::text='{record}' order by issued_at,permit_id;",
    }


def _validate_sql_turn(ctx, turn, refs, now, *, observation_only=False):
    """Pure structure/content check; only read_actual attests provider origin."""
    from en2_supabase_origin import _provider_result
    t,_,project = _context(ctx);queries=sql_queries(ctx)
    need(isinstance(turn,dict) and turn.get('id')==refs.get('turn_id')
         and turn.get('status') in {'inProgress','completed'} and not turn.get('error')
         and type(turn.get('startedAt')) in {int,float}, 'one actual original PUB turn required')
    finish=turn.get('completedAt')
    need((turn['status']=='inProgress' and finish is None) or
         (turn['status']=='completed' and type(finish) in {int,float} and turn['startedAt']<=finish<=now.timestamp()),
         'honest original turn state and chronology required')
    names=('row_call','key_call','same_row_call')
    need(all(isinstance(refs.get(k),str) and refs[k] for k in names)
         and len({refs[k] for k in names})==3, 'three distinct actual original provider calls required')
    calls=[];values=[];indices=[];items=turn.get('items',[])
    for ref,key in zip(names,('row','key','same_row')):
        found=[(i,m) for i,m in enumerate(items) if m.get('id')==refs[ref]]
        need(len(found)==1, 'DATA_MISSING: one actual '+key+' provider item required')
        index,call=found[0];args=call.get('arguments')
        need(call.get('type')=='mcpToolCall' and call.get('server')=='codex_apps'
             and call.get('tool')=='supabase.execute_sql' and call.get('status')=='completed'
             and not call.get('error') and isinstance(args,dict) and set(args)=={'project_id','query'}
             and args['project_id']==project and ' '.join(str(args['query']).split())==' '.join(queries[key].split()),
             'exact completed original project and bounded SELECT required')
        start,end=call.get('startedAtMs'),call.get('completedAtMs')
        need(type(start) is int and type(end) is int and turn['startedAt']*1000<=start<=end<=now.timestamp()*1000
             and (finish is None or end<=finish*1000+999), 'actual provider call timing must belong to original turn')
        values.append(_provider_result(call));calls.append(call);indices.append(index)
    need(indices==sorted(indices) and calls[0]['completedAtMs']<=calls[1]['startedAtMs']
         and calls[1]['completedAtMs']<=calls[2]['startedAtMs'], 'row, original key and complete same-row calls must be ordered')
    rows,keys,same=values
    need(len(rows)==1 and isinstance(rows[0],dict) and isinstance(rows[0].get('raw_full_record'),str),
         'one complete server-clock/full-row result required')
    row=loads(rows[0]['raw_full_record']);observed=w._parse_observed_at(rows[0].get('server_observed_at'))
    need(isinstance(ctx.get('desired'),dict) and set(ctx['desired'])=={'content_zh'}
         and w.sha256_value(ctx['desired'])==t['desiredFieldsSha256'], 'exact authenticated desired field required')
    need(isinstance(row,dict) and set(row)==set(t['baselineProjectionFields'])
         and row.get('id')==t['id'] and row.get('slug')==t['slug']
         and type(row.get('version')) is int and isinstance(row.get('updated_at'),str)
         and w._parse_observed_at(row['updated_at']) is not None,
         'one actual full41 row/id/slug/integer version/raw microsecond CAS with complete protect38/MS11 required')
    protected_match=w.sha256_value({k:row[k] for k in t['retainedProjectionFields']})==t['retainedFieldsSha256']
    baseline_match=(row.get('updated_at')==t['expectedUpdatedAt'] and w.sha256_value(row)==t['baselineFieldsSha256']
                    and protected_match and row==ctx['before'])
    if not observation_only:
        need(baseline_match,'fresh full41/raw microsecond CAS/version/baseline/protect38/MS11 drift blocks execution')
    need(observed is not None and calls[0]['startedAtMs']<=observed.timestamp()*1000<=calls[0]['completedAtMs']
         and 0<=(now-observed).total_seconds()<=300, 'actual SQL server clock expired, future or outside provider call')
    need(all(isinstance(x,dict) and x.get('record_id')==t['id'] for x in keys+same), 'only exact same-record permit effects may be returned')
    expected=[x for x in same if x.get('task_id')==ctx['task'] or x.get('action_id')==t['actionId'] or x.get('candidate_version')==t['candidateVersion']]
    need(keys==expected,'original-key and independently complete same-row results must agree')
    # The broad key SELECT includes the same parent task's historical actions.
    # Preserve all rows; only the exact current identity/alias or non-completed
    # same-record effects block this new action. A completed distinct action is
    # history, never evidence of current in-flight work or a renewed permit.
    current_effects=[x for x in same if x.get('action_id')==t['actionId'] or x.get('candidate_version')==t['candidateVersion']]
    historical_completed=[x for x in same if x not in current_effects and x.get('status')=='completed']
    blocking_effects=bool(current_effects) or any(x.get('status')!='completed' for x in same)
    if not observation_only:
        need(not blocking_effects,'original action has prior/UNKNOWN effect or same-row active/UNKNOWN conflict; no replay')
    return {'row':row,'observed_at':rows[0]['server_observed_at'],'raw_updated_at':row['updated_at'],
            'observation_only':observation_only,'baseline_matches':baseline_match,'protected_fields_match':protected_match,
            'desired_effect_present':row.get('content_zh')==ctx['desired']['content_zh'],'blocking_original_or_same_row_effects':blocking_effects,
            'execution_permission':False,'actual_action_allowed':False,'external_permission_issued':False,
            'version':row['version'],'keys':keys,'same_row':same,'current_or_aliased_action_effects':current_effects,
            'historical_completed_other_effects':historical_completed,'same_row_completed_at_ms':calls[2]['completedAtMs'],
            'native_turn':turn,'row_call':refs['row_call'],'key_call':refs['key_call'],'same_row_call':refs['same_row_call']}


def validate_sql_turn(ctx, turn, refs, now):
    """Strict execution check; observation output cannot enter this path."""
    return _validate_sql_turn(ctx,turn,refs,now,observation_only=False)


_READ_DIAGNOSTIC = contextvars.ContextVar('singlefield_provider_read_diagnostic',default=None)


def _capture_readback(thread=None,turn=None,*,step=None,sdk=None):
    state=_READ_DIAGNOSTIC.get()
    if state is None:return
    if thread is not None:state['thread']=copy.deepcopy(thread)
    if turn is not None:state['turn']=copy.deepcopy(turn)
    if step is not None:state['step']=step
    if sdk is not None:state['sdk']=copy.deepcopy(sdk)


def _diagnostic_turn(turn,refs):
    if not isinstance(turn,dict):return None
    ids={refs.get(k) for k in ('row_call','key_call','same_row_call') if isinstance(refs,dict)}
    # Deliberately exclude unrelated commands/tool arguments and user bodies,
    # which may include authentication material. This is labelled a projection,
    # not a fabricated full original turn. Exact provider items retain payloads.
    items=[copy.deepcopy(x) for x in turn.get('items',[]) if x.get('id') in ids or
           x.get('type')=='agentMessage' and x.get('phase')=='commentary' and x.get('text','').strip()]
    value={k:copy.deepcopy(v) for k,v in turn.items() if k!='items'}
    value['items']=items
    return value


def provider_diagnostic(ctx,refs,reason,*,thread=None,turn=None,sdk_source=None,sdk=None,step=None):
    """Safe failure evidence; no status reinterpretation or provider PASS."""
    identity=('id','name','title','cwd','projectId','hostId','status','createdAt','updatedAt')
    return {'schema':'actual-singlefield-provider-read-failure/v1','at_UTC':dt.datetime.now(dt.timezone.utc).isoformat(),
       'task_id':ctx.get('task') if isinstance(ctx,dict) else None,
       'reason':str(reason),'step':step,'provider_references':copy.deepcopy(refs),
       'canonical_readback':'RETURNED' if isinstance(turn,dict) else 'NOT_RETURNED',
       'canonical_thread':{k:copy.deepcopy(thread[k]) for k in identity if isinstance(thread,dict) and k in thread},
       'canonical_turn':_diagnostic_turn(turn,refs),
       'canonical_turn_projection':'original_metadata_and_exact_provider_items_plus_ACKs',
       'complete_canonical_turn_sha256':w.sha256_value(turn) if isinstance(turn,dict) else None,
       'complete_canonical_item_ids':[x.get('id') for x in turn.get('items',[])] if isinstance(turn,dict) else [],
       'sdk_source':copy.deepcopy(sdk_source),'sdk_comparison':copy.deepcopy(sdk),
       'actual_action_allowed':False,'external_permission_issued':False,'provider_PASS':False,
       'business_completion_claimed':False}


def _capture_provider_failure(fn):
    @functools.wraps(fn)
    def wrapped(root,ctx,refs,*,sdk_source=None):
        state={'thread':None,'turn':None,'sdk':None,'step':'before_provider_read'}
        token=_READ_DIAGNOSTIC.set(state)
        try:
            return fn(root,ctx,refs,sdk_source=sdk_source)
        except (w.WorkflowError,ValueError,KeyError,TypeError,OSError,subprocess.SubprocessError) as error:
            failure=error if isinstance(error,w.WorkflowError) else w.WorkflowError('singlefield PUB provider: unreadable provider source ('+type(error).__name__+')')
            failure.provider_diagnostic=provider_diagnostic(ctx,refs,failure,thread=state['thread'],turn=state['turn'],
                sdk_source=sdk_source,sdk=state['sdk'],step=state['step'])
            if failure is error:raise
            raise failure from error
        finally:_READ_DIAGNOSTIC.reset(token)
    return wrapped


@_capture_provider_failure
def observe_actual(root,ctx,refs,*,sdk_source=None):
    """Read actual current row/effects only, including NO_CHANGE or conflicts.

    No preview, execution admission, policy, permit or Save is granted. The
    production read_actual path independently re-reads strict baseline/effects.
    """
    _context(ctx)
    need(isinstance(refs,dict) and set(refs)=={'turn_id','row_call','key_call','same_row_call','preview_run_id'}
         and refs.get('preview_run_id') is None
         and all(isinstance(refs.get(k),str) and refs[k] for k in ('turn_id','row_call','key_call','same_row_call')),
         'observation only accepts the original three SQL call references and no preview')
    thread,canonical_turn=_read_pub_turn(Path(root).resolve(),ctx,refs['turn_id'])
    _capture_readback(thread,canonical_turn,step='canonical_returned_before_SDK_and_SQL_validation')
    turn,sdk_metadata=supplement_pub_metadata(root,ctx,thread,canonical_turn,refs,sdk_source)
    checked=dt.datetime.now(dt.timezone.utc)
    sql=_validate_sql_turn(ctx,turn,refs,checked,observation_only=True)
    return {**sql,'thread':thread,'canonical_thread':thread,'canonical_turn':canonical_turn,
            'sdk_metadata_supplement':sdk_metadata,'thread_project_id_actual':thread['projectId'],
            'row_call_origin':'VERIFIED_OFFICIAL_RPC','original_key_call_origin':'VERIFIED_OFFICIAL_RPC',
            'same_row_call_origin':'VERIFIED_OFFICIAL_RPC','preview':None,'provider_checked_at':checked.isoformat(),
            'execution_permission':False,'actual_action_allowed':False,'external_permission_issued':False}


def unpack_archive(raw, name):
    """Read only the seven bounded regular JSON members, never extract files."""
    need(isinstance(raw,bytes) and len(raw)<=50*1024*1024, 'bounded actual artifact archive required')
    out={}
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        entries=archive.infolist()
        need(len(entries)<=128, 'bounded original artifact member count required')
        for filename in ARTIFACT_FILES:
            matches=[x for x in entries if x.filename==name+'/'+filename]
            need(len(matches)==1 and 0<matches[0].file_size<=2*1024*1024 and not matches[0].is_dir()
                 and (matches[0].external_attr>>16)&0o170000!=0o120000,
                 'one bounded regular original artifact member required: '+filename)
            out[filename]=loads(archive.read(matches[0]))
    return out


def validate_preview(ctx, run_id, run, workflow, ref, artifact, docs, now):
    """Pure exact protected preview validator, no catalog/issuer dependency."""
    t,web,_ = _context(ctx);repo=web['repository'];name=t['candidateVersion'];head=web['commit']
    need(type(run_id) is int and run_id>0 and set(docs)==set(ARTIFACT_FILES),'one actual run and complete seven-file protected artifact required')
    need(run.get('id')==run_id and run.get('event')=='workflow_dispatch'
         and run.get('status')=='completed' and run.get('conclusion')=='success' and run.get('run_attempt')==1
         and run.get('head_branch')=='main' and run.get('head_sha')==head
         and run.get('path')==WORKFLOW and run.get('name') in {'Approved website content publish',name+' | dry-run'}
         and run.get('repository',{}).get('full_name')==repo and run.get('repository',{}).get('id')==web['repository_id']
         and run.get('actor',{}).get('id')==web['actor_id'] and ref.get('object',{}).get('sha')==head,
         'exact original first-attempt successful workflow/repo/actor/current main required')
    need(workflow.get('id')==run.get('workflow_id') and type(workflow.get('id')) is int and workflow['id']>0
         and workflow.get('path')==WORKFLOW and workflow.get('state')=='active'
         and workflow.get('name')=='Approved website content publish','actual active original workflow required')
    need(artifact.get('name')=='approved-content-publish-'+str(run_id) and type(artifact.get('id')) is int and artifact['id']>0
         and artifact.get('expired') is False and artifact.get('workflow_run',{}).get('id')==run_id
         and artifact['workflow_run'].get('repository_id')==web['repository_id']
         and artifact['workflow_run'].get('head_sha')==head,'same-run unexpired actual artifact required')
    receipt=docs['locked-dry-run-receipt.json'];digest=docs['managed-payload-digest.json'];preview=docs['dry-run.json']
    probe=docs['managed-identity-probe.json'];locked=docs['locked-candidate.json'];backup=docs['backup.json'];desired=docs['desired.json']
    identity={'task_id':ctx['task'],'candidate_version':name,'action_id':t['actionId'],'scope':t['scope']}
    need(all(receipt.get(k)==v for k,v in {**identity,'operation':'publish','http_status':200,'dry_run':True,
         'performed_write':False,'external_writes':0,'row_unchanged_after_dry_run':True,'expected_updated_at':t['expectedUpdatedAt']}.items()),
         'exact singlefield zero-write receipt required')
    at=w._parse_observed_at(receipt.get('checked_at'));start=w._parse_observed_at(run.get('run_started_at'));end=w._parse_observed_at(run.get('updated_at'))
    need(at and start and end and start<=at<=end<=now
         and 0<=(now-at).total_seconds()<=1800 and 0<=(now-end).total_seconds()<=1800,
         'actual completed preview receipt/run is older than 30 minutes, future or outside run')
    ident=probe.get('identity',{})
    need(probe.get('ok') is True and probe.get('dry_run') is True and probe.get('performed_write') is False
         and all(ident.get(k)==v for k,v in {'runId':run_id,'runAttempt':1,'repositoryId':web['repository_id'],
          'actorId':web['actor_id'],'workflowSha':head,'workflowRef':repo+'/'+WORKFLOW+'@refs/heads/main'}.items()),
         'server-verified original OIDC probe must bind exact run/actor/head')
    need(all(locked.get(k)==v for k,v in {**identity,'expected_updated_at':t['expectedUpdatedAt'],
          'changed_fields':t['changedFields'],'baseline_fields_sha256':t['baselineFieldsSha256'],
          'desired_fields_sha256':t['desiredFieldsSha256']}.items()),'exact original locked target/digests required')
    row=backup.get('record')
    need(backup.get('target')==name and backup.get('table')==t['table'] and backup.get('key')==t['slug']
         and row==ctx['before'] and isinstance(row,dict) and set(row)==set(t['baselineProjectionFields'])
         and row.get('id')==t['id'] and row.get('updated_at')==t['expectedUpdatedAt'] and type(row.get('version')) is int
         and w.sha256_value(row)==t['baselineFieldsSha256']
         and w.sha256_value({k:row[k] for k in t['retainedProjectionFields']})==t['retainedFieldsSha256'],
         'actual protected backup/full41/CAS/protect38/MS11 differs')
    patch=preview.get('payload_preview')
    need(preview.get('ok') is True and preview.get('dry_run') is True and preview.get('performed_write') is False
         and isinstance(patch,dict) and set(patch)=={'content_zh'} and patch==ctx['desired']
         and w.sha256_value(patch)==t['desiredFieldsSha256'] and desired.get('target')==name
         and desired.get('operation')=='optimize' and desired.get('record')=={**row,**patch}
         and all(digest.get(k)==v for k,v in {'task_id':ctx['task'],'candidate_version':name,'operation':'publish',
             'payload_sha256':t['desiredFieldsSha256'],'expected_updated_at':t['expectedUpdatedAt']}.items()),
         'only exact content_zh desired preview/digest may differ')
    return {'run':run,'workflow':workflow,'ref':ref,'artifact':artifact,'docs':docs,'run_id':run_id,
            'receipt_checked_at':receipt['checked_at'],'head_sha':head,'preview_origin':'VERIFIED_GITHUB_PROVIDER_READ',
            'actual_action_allowed':False,'external_permission_issued':False}


def _api(path, *, archive=False):
    process=subprocess.run(['gh','api',path],check=True,capture_output=True,timeout=60)
    return process.stdout if archive else loads(process.stdout)


def _read_pub_turn(root,ctx,turn_id):
    import department_event_dispatcher as dispatcher
    binding=ctx['pub_binding'];need(isinstance(turn_id,str) and turn_id,'exact original PUB turn ID required')
    rpc=dispatcher.RPC([dispatcher.native_queue_capability(root),'app-server','--listen','stdio://'])
    try:
        thread=rpc.call('thread/read',{'threadId':binding['task_id'],'includeTurns':False})['thread']
        _capture_readback(thread=thread,step='canonical_thread_returned_before_turn_read')
        response=rpc.call('thread/turns/list',{'threadId':binding['task_id'],'limit':5,'sortDirection':'desc','itemsView':'full'})
    finally:rpc.close()
    rows=[t for t in response.get('data',[]) if t.get('id')==turn_id]
    if len(rows)==1:_capture_readback(thread,rows[0],step='canonical_raw_before_identity_check')
    need(thread.get('id')==binding['task_id'] and thread.get('name')==binding['title'] and thread.get('cwd')==binding['cwd']
         and 'projectId' in thread and thread['projectId'] in (None,binding['project_id']),
         'actual original PUB thread identity; missing project preserved, never fabricated')
    need(len(rows)==1,'DATA_MISSING: exact current PUB turn absent from full official history page')
    return thread,rows[0]


@_capture_provider_failure
def read_actual(root,ctx,refs,*,sdk_source=None):
    """Provider reads only. References locate actual calls/run, never authorize."""
    t,web,_=_context(ctx)
    need(isinstance(refs,dict) and set(refs)=={'turn_id','row_call','key_call','same_row_call','preview_run_id'}
         and all(isinstance(refs.get(k),str) and refs[k] for k in ('turn_id','row_call','key_call','same_row_call'))
         and (refs['preview_run_id'] is None or type(refs['preview_run_id']) is int and refs['preview_run_id']>0),
         'exact original PUB provider identifiers required; missing evidence is not success')
    thread,canonical_turn=_read_pub_turn(Path(root).resolve(),ctx,refs['turn_id'])
    _capture_readback(thread,canonical_turn,step='canonical_returned_before_SDK_and_SQL_validation')
    turn,sdk_metadata=supplement_pub_metadata(root,ctx,thread,canonical_turn,refs,sdk_source)
    now=dt.datetime.now(dt.timezone.utc);sql=validate_sql_turn(ctx,turn,refs,now)
    result={**sql,'thread':thread,'canonical_thread':thread,'canonical_turn':canonical_turn,
            'sdk_metadata_supplement':sdk_metadata,'thread_project_id_actual':thread['projectId'],
            'row_call_origin':'VERIFIED_OFFICIAL_RPC','original_key_call_origin':'VERIFIED_OFFICIAL_RPC',
            'same_row_call_origin':'VERIFIED_OFFICIAL_RPC','preview':None,'provider_checked_at':now.isoformat(),'actual_action_allowed':False,
            'external_permission_issued':False}
    run_id=refs['preview_run_id']
    if run_id is None:return result  # Only inspect/preview admission, never a production admission.
    prefix='repos/'+web['repository'];run=_api(prefix+'/actions/runs/'+str(run_id))
    workflow=_api(prefix+'/actions/workflows/content-publish-approved.yml');ref=_api(prefix+'/git/ref/heads/main')
    listing=_api(prefix+'/actions/runs/'+str(run_id)+'/artifacts?per_page=100')
    need(type(listing.get('total_count')) is int and isinstance(listing.get('artifacts'),list)
         and listing['total_count']==len(listing['artifacts'])<=100,'complete exact preview artifact listing required')
    rows=[a for a in listing['artifacts'] if a.get('name')=='approved-content-publish-'+str(run_id)]
    need(len(rows)==1 and type(rows[0].get('id')) is int and rows[0]['id']>0,'one actual protected preview artifact required')
    artifact=rows[0];raw=_api(prefix+'/actions/artifacts/'+str(artifact['id'])+'/zip',archive=True)
    need(artifact.get('digest')=='sha256:'+hashlib.sha256(raw).hexdigest(),'actual GitHub artifact digest differs')
    docs=unpack_archive(raw,t['candidateVersion'])
    preview=validate_preview(ctx,run_id,run,workflow,ref,artifact,docs,dt.datetime.now(dt.timezone.utc))
    observed=w._parse_observed_at(sql['observed_at']);checked=dt.datetime.now(dt.timezone.utc)
    need(observed and 0<=(checked-observed).total_seconds()<=300
         and sql['row']==preview['docs']['backup.json']['record'],
         'current SQL row/CAS must still equal protected preview backup; fresh keys required without TTL extension')
    result['preview']=preview
    result['provider_checked_at']=checked.isoformat()
    return result


def _sdk_document(root,pin):
    """Read the exact original SDK page; never accept caller status flags."""
    need(isinstance(pin,dict) and set(pin)=={'path','sha256','size'},'exact real SDK supplement pin required')
    path=Path(root,pin['path'])
    need(path.resolve().is_relative_to(Path(root).resolve()) and not path.is_symlink(), 'SDK source belongs to the original project')
    raw=w.validation_bytes(path)
    need(hashlib.sha256(raw).hexdigest()==pin['sha256'] and len(raw)==pin['size'],'original SDK supplement bytes changed')
    page=loads(raw)
    need(isinstance(page,dict) and isinstance(page.get('thread'),dict) and isinstance(page.get('turns'),list),
         'real SDK thread/turns source required, not a caller metadata declaration')
    from qa_review_plan import _review_native_containers
    _review_native_containers(page)
    return page


def _sdk_result_binding(root,sdk_turn,sdk_call,canonical_call):
    """Match the complete decoded provider payload, not an ID/hash assertion.

    Compact SDK pages omit MCP results. Their same-turn completed fileChange
    may instead contain the unchanged complete successful response bytes saved
    immediately after this exact call. Those bytes must still exist at that
    exact project-owned path and match the native save in full.
    """
    from en2_supabase_origin import _provider_result
    actual=_provider_result(canonical_call)
    if sdk_call.get('result') is not None or sdk_call.get('output') is not None:
        need(_provider_result(sdk_call)==actual,'SDK/canonical complete provider result conflict')
        return {'call_id':sdk_call['id'],'mode':'direct_complete_provider_result'}
    items=sdk_turn.get('items',[]);indices=[i for i,x in enumerate(items) if x.get('id')==sdk_call['id']]
    need(len(indices)==1,'one exact SDK provider call required before saved response')
    start=indices[0];end=next((i for i in range(start+1,len(items)) if items[i].get('type')=='mcpToolCall'),len(items))
    matches=[]
    for item in items[start+1:end]:
        if item.get('type')!='fileChange' or item.get('status')!='completed':continue
        for change in item.get('changes',[]):
            diff=change.get('diff',{})
            if not isinstance(diff,dict) or diff.get('truncated') is not False or not isinstance(diff.get('text'),str):continue
            try:export=loads(diff['text'])
            except (ValueError,TypeError,w.WorkflowError):continue
            if not isinstance(export,dict) or set(export)!={'args','response'} or export['args']!=sdk_call.get('arguments'):continue
            response=export['response']
            need(isinstance(response,dict) and set(response)=={'status','value'} and response['status']=='fulfilled',
                 'SDK native saved response must be a real fulfilled provider result')
            need(_provider_result({'result':response['value']})==actual,
                 'SDK saved complete provider payload differs from the exact canonical call')
            path=Path(change.get('path',''))
            need(path.is_absolute() and path.resolve().is_relative_to(Path(root).resolve()) and not path.is_symlink(),
                 'SDK native response save must name its exact project path')
            raw=w.validation_bytes(path)
            need(raw==diff['text'].encode('utf-8'),'SDK native saved response bytes/path changed')
            need(isinstance(item.get('id'),str) and item['id'],'one actual completed SDK save item ID required')
            matches.append({'call_id':sdk_call['id'],'mode':'same_turn_completed_native_response_save',
                'save_item_id':item['id'],'response_source':{'path':str(path.relative_to(Path(root))),
                   'sha256':hashlib.sha256(raw).hexdigest(),'size':len(raw)}})
    need(len(matches)==1,'DATA_MISSING: one original same-turn complete SDK provider response source required')
    return matches[0]


def supplement_pub_metadata(root,ctx,canonical_thread,canonical_turn,refs,sdk_source=None):
    """Return a separate reproducible metadata copy; never modify canonical.

    Only independently matched three provider results and a genuine nonempty
    original ACK let the SDK fill missing turn/call metadata. Explicit source
    conflicts, failed/cancelled/pending state or missing payloads never heal.
    """
    if sdk_source is None:return canonical_turn,None
    _context(ctx);binding=ctx['pub_binding'];sdk=_sdk_document(root,sdk_source);thread=sdk['thread']
    need(all(canonical_thread.get(k)==binding.get(v) for k,v in {'id':'task_id','name':'title','cwd':'cwd'}.items())
         and 'projectId' in canonical_thread and canonical_thread.get('projectId') in (None,binding['project_id'])
         and all(thread.get(k)==binding.get(v) for k,v in {'id':'task_id','title':'title','cwd':'cwd','hostId':'host_id'}.items())
         and thread.get('kind')=='codex' and thread.get('projectId') in (None,binding['project_id'])
         and canonical_thread.get('hostId') in (None,thread.get('hostId')),
         'independent canonical/SDK original PUB stable identity conflict')
    for key in ('createdAt',):
        if canonical_thread.get(key) is not None and thread.get(key) is not None:
            need(canonical_thread[key]==thread[key],'canonical/SDK original thread creation metadata conflict')
    turns=[t for t in sdk['turns'] if t.get('id')==refs.get('turn_id')]
    need(len(turns)==1 and canonical_turn.get('id')==refs.get('turn_id'), 'one same original canonical/SDK PUB turn required')
    sturn=turns[0]
    _capture_readback(step='SDK_supplement_identity_and_call_comparison',sdk={'source':sdk_source,
        'thread':{k:copy.deepcopy(thread[k]) for k in ('id','title','cwd','projectId','hostId','status','createdAt','updatedAt') if k in thread},
        'turn':_diagnostic_turn(sturn,refs),'result_binding_progress':[]})
    need(not canonical_turn.get('error') and not sturn.get('error')
         and sturn.get('status') in {'inProgress','completed'} and type(sturn.get('startedAt')) in {int,float},
         'SDK supplement requires a real successful current/completed turn')
    need((sturn['status']=='inProgress' and sturn.get('completedAt') is None) or
         (sturn['status']=='completed' and type(sturn.get('completedAt')) in {int,float}
          and sturn['startedAt']<=sturn['completedAt']), 'real SDK turn chronology required')
    result=copy.deepcopy(canonical_turn);supplied=[]
    for key in ('status','startedAt','completedAt'):
        old=canonical_turn.get(key);new=sturn.get(key)
        missing=old is None or key=='status' and old=='unknown'
        if missing:
            result[key]=new
            if old!=new:supplied.append(key)
        else:need(old==new,'explicit canonical/SDK '+key+' metadata conflict')
    names=('row_call','key_call','same_row_call')
    need(all(isinstance(refs.get(k),str) and refs[k] for k in names) and len({refs[k] for k in names})==3,
         'three exact distinct provider identities required for supplement')
    bindings=[];call_fills=[];first_sdk=None;first_canonical=None
    queries=sql_queries(ctx);project=ctx.get('project_ref',ctx['web_context'].get('project_ref'))
    for name,query_kind in zip(names,('row','key','same_row')):
        sdk_rows=[(i,x) for i,x in enumerate(sturn.get('items',[])) if x.get('id')==refs[name]]
        original_rows=[(i,x) for i,x in enumerate(canonical_turn.get('items',[])) if x.get('id')==refs[name]]
        need(len(sdk_rows)==len(original_rows)==1,'DATA_MISSING: exact canonical and SDK provider call required')
        si,scall=sdk_rows[0];ci,ccall=original_rows[0]
        need(all(scall.get(k)==ccall.get(k) for k in ('id','type','server','tool','arguments','status'))
             and ccall.get('type')=='mcpToolCall' and ccall.get('server')=='codex_apps'
             and ccall.get('tool')=='supabase.execute_sql' and ccall.get('status')=='completed'
             and not scall.get('error') and not ccall.get('error'), 'canonical/SDK exact provider ID/arguments/status conflict')
        args=ccall.get('arguments')
        need(isinstance(args,dict) and set(args)=={'project_id','query'} and args['project_id']==project
             and ' '.join(str(args['query']).split())==' '.join(queries[query_kind].split()),
             'SDK supplement cannot bind another project or query')
        bindings.append(_sdk_result_binding(root,sturn,scall,ccall))
        state=_READ_DIAGNOSTIC.get()
        if state is not None and state.get('sdk') is not None:state['sdk']['result_binding_progress']=copy.deepcopy(bindings)
        first_sdk=si if first_sdk is None else min(first_sdk,si);first_canonical=ci if first_canonical is None else min(first_canonical,ci)
        copied=result['items'][ci]
        for key in ('startedAtMs','completedAtMs','durationMs'):
            old=ccall.get(key);new=scall.get(key)
            if old is not None and new is not None:need(old==new,'canonical/SDK actual provider timing conflict')
            elif old is None and new is not None:
                need(type(new) is int,'actual SDK provider timing required, never a default')
                copied[key]=new;call_fills.append({'call_id':ccall['id'],'field':key})
    acks=[x for x in sturn['items'][:first_sdk] if x.get('type')=='agentMessage' and x.get('phase')=='commentary'
          and isinstance(x.get('text'),str) and x['text'].strip()]
    actual_acks=[]
    for ack in acks:
        pair=[x for x in canonical_turn['items'][:first_canonical] if x.get('id')==ack.get('id')]
        if len(pair)==1 and all(pair[0].get(k)==ack.get(k) for k in ('type','phase','text')):actual_acks.append(ack['id'])
    need(actual_acks,'real nonempty original same-turn canonical/SDK ACK required before queries')
    proof={'source':sdk_source,'matched_call_results':bindings,'original_ACK_ids':actual_acks,
           'filled_turn_fields':supplied,'filled_call_fields':call_fills,
           'canonical_metadata_preserved':True,'comparison':'complete_provider_payload_deep_equality'}
    return result,proof


def validate_supplement_proof(root,ctx,refs,proof):
    """Read-only historical recheck of SDK supplement against original bytes.

    The containing provider proof must itself retain its normal immutable pin.
    This routine is not a live provider attestation or an execution grant.
    """
    need(isinstance(proof,dict) and isinstance(proof.get('canonical_thread'),dict)
         and isinstance(proof.get('canonical_turn'),dict),'original canonical thread and turn proof required')
    saved=proof.get('sdk_metadata_supplement')
    if saved is None:
        need(proof.get('native_turn')==proof['canonical_turn'],'unsupplemented native turn must remain exactly canonical')
        return proof['canonical_turn']
    need(isinstance(saved,dict) and isinstance(saved.get('source'),dict),'exact SDK metadata source proof required')
    turn,derived=supplement_pub_metadata(root,ctx,proof['canonical_thread'],proof['canonical_turn'],refs,saved['source'])
    need(turn==proof.get('native_turn') and derived==saved,'SDK supplement copy/proof no longer matches original source bytes')
    return turn
