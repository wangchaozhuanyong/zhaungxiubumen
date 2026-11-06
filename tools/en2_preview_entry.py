"""Narrow, non-authorizing EN2 preview entry; never executes a workflow."""
import datetime as dt
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import workflow_control as w
import department_autonomy as a

TASK='fc-20261011-english-kitchen-actual-publication-goal-v1'
OP='protected_preview'
REF_KEYS={'turn_id','row_call','key_call','same_row_call'}

def request_base(root,task,state, *, allowed_policy=None):
    request, _, _ = _request_and_evidence(root, task, state, allowed_policy=allowed_policy)
    return request


def _reviewed_context(root):
    import professional_web_execution as web
    sources=web.records(Path(root),TASK)
    a.require(len(sources)==1 and sources[0].get('current_owner_reviewed_release') is True
              and sources[0].get('role')=='designated-development' and sources[0].get('scope')=='cms:services:kitchen:english-two-fields:publication:v1'
              and sources[0].get('registration',{}).get('sha256')=='f52a048ab07e02f2e90984b5a40a31b0f52faf3f9f7164ddacb578f58871ecb3',
              'EN2 preview: original current reviewed WEB source required')
    return sources[0]


def _request_and_evidence(root,task,state, *, allowed_policy=None):
    request, identity, actual, _ = _verified_request(root, task, state, allowed_policy=allowed_policy)
    return request, identity, actual


def _verified_request(root,task,state, *, allowed_policy=None):
    a.require(task==TASK and isinstance(state,dict),'EN2 preview: exact original business task and state required')
    # A caller's timestamp may cause refusal, never establish freshness.
    observed=w._parse_observed_at(state.get('publisher_server_observed_at'))
    a.require(observed is not None and 0 <= (dt.datetime.now(dt.timezone.utc)-observed).total_seconds() <= 300,
              'EN2 preview DATA_MISSING: fresh original PUB three-query observation required; no old observation reuse')
    refs=state.get('original_pub_provider_calls')
    a.require(isinstance(refs,dict) and set(refs)==REF_KEYS and all(isinstance(refs[k],str) and refs[k] for k in REF_KEYS)
              and len({refs[k] for k in ('row_call','key_call','same_row_call')})==3,
              'EN2 preview DATA_MISSING: original PUB turn and three distinct actual provider call IDs required')
    webref=state.get('original_web_inventory')
    a.require(isinstance(webref,dict) and set(webref)=={'turn_id','call_id'} and all(isinstance(webref[k],str) and webref[k] for k in webref),
              'EN2 preview DATA_MISSING: original WEB turn and actual inventory call IDs required')
    from en2_supabase_origin import read_actual
    actual=read_actual(Path(root),refs['turn_id'],refs['row_call'],refs['key_call'],refs['same_row_call'])
    a.require(actual.get('row_call_origin')=='VERIFIED_OFFICIAL_RPC'
              and actual.get('original_key_call_origin')=='VERIFIED_OFFICIAL_RPC'
              and actual.get('same_row_call_origin')=='VERIFIED_OFFICIAL_RPC'
              and actual.get('fresh_within_300_seconds') is True and actual.get('original_key_count')==0
              and actual.get('same_row_effect')=='NO_BLOCKING_ROW_OBSERVED'
              and w._parse_observed_at(actual.get('server_observed_at'))==observed,
              'EN2 preview: authentic fresh original PUB full-row/key/same-row evidence required')
    from en2_preview_web_identity import _attest_reviewed_source
    ctx=_reviewed_context(root)
    identity=_attest_reviewed_source(root,ctx,webref['turn_id'],webref['call_id'])
    a.require(identity.get('state')=='WEB_IDENTITY_ATTESTED_ONLY' and identity.get('permission_issued') is False
              and identity.get('dispatch_allowed') is False,'EN2 preview: actual WEB identity evidence required')
    from en2_preview_github_evidence import _read_hosted_channel
    from en2_preview_history import _history_inputs, _read_hosted_history
    created,epoch,prior_run=_history_inputs(Path(root),ctx,allowed_policy)
    # Only provider GETs run in workers. Local source and policy pins are
    # collected on the original validation context before starting them.
    with ThreadPoolExecutor(max_workers=2) as reads:
        channel_read=reads.submit(_read_hosted_channel,state.get('main_sha'))
        history_read=reads.submit(_read_hosted_history,created,epoch,prior_run)
        channel,history=channel_read.result(),history_read.result()
    a.require(channel.get('state')=='GITHUB_CHANNEL_OBSERVED_ONLY' and channel.get('permission_issued') is False
              and channel.get('dispatch_allowed') is False and channel.get('previous_effect')=='UNKNOWN_REQUIRES_ORIGINAL_KEY_CHECK',
              'EN2 preview: original GitHub channel evidence required')
    a.require(history.get('state')=='NO_ORIGINAL_PREVIEW_OBSERVED_COMPLETE_HISTORY'
              and history.get('permission_issued') is False and history.get('dispatch_allowed') is False,
              'EN2 preview: actual original preview history and key evidence required')
    # Request construction is non-executing. The separate preflight, policy and
    # durable transport are mandatory and independently revalidate this evidence.
    from professional_cms_issuer import targets
    from en2_preview_history import ACTION
    source=targets(Path(root),task_id=TASK).get('english-kitchen-en2-exact-v1')
    a.require(isinstance(source,dict) and source.get('candidate_shape')=='professional_en2_full41_source_only_v1'
              and source.get('actual_action_allowed') is False and source.get('source_event_id')=='698ae455-16d7-4ad1-8744-ebfc8fd763e1',
              'EN2 preview: exact immutable source-only carrier required')
    target=source['physical_target'];human_id=ctx.get('current_owner_message',{}).get('message',{}).get('id')
    a.require(target.get('taskId')==TASK and target.get('actionId')=='save-kitchen-english-two-fields-v1'
              and target.get('candidateVersion')=='publishing-english-kitchen-en2-actual-publication-v1-20261011'
              and target.get('id')=='ce4156db-9034-42c8-ba29-b35724ea7d6d' and target.get('slug')=='kitchen'
              and target.get('table')=='services' and target.get('scope')=='company.example:services:ce4156db-9034-42c8-ba29-b35724ea7d6d:title_en,excerpt_en'
              and target.get('changedFields')==['title_en','excerpt_en'] and target.get('rollbackAllowed') is False
              and len(target.get('baselineProjectionFields',[]))==41 and len(target.get('retainedProjectionFields',[]))==37
              and sum(x.endswith('_ms') for x in target.get('retainedProjectionFields',[]))==11,
              'EN2 preview: exact original forward-only full41/protect37/MS11 tuple required')
    _verify_local_git(root,ctx,state)
    inputs={'mode':'dry-run','target':'english-kitchen-en2-exact-v1','approval_id':human_id,
            'managed_operation':'publish','managed_permit_id':'','parent_run_id':''}
    a.require(isinstance(human_id,str) and human_id and state.get('expected_inputs')==inputs and state.get('target')==target
              and state.get('repository')=='example-owner/example-website' and state.get('repository_id')==1248188229
              and state.get('actual_local_branch')=='main' and state.get('actual_local_HEAD')==state.get('main_sha')==state.get('remote_main_sha')
              and actual.get('row_sha256')==target.get('baselineFieldsSha256')
              and actual.get('raw_updated_at')==target.get('expectedUpdatedAt') and actual.get('full_fields')==41,
              'EN2 preview: exact original target, human reference, current main and full41 required')
    desired={'repository':'example-owner/example-website','workflow':'.github/workflows/content-publish-approved.yml',
      'ref':'main','head':state['main_sha'],'inputs':inputs,'business_scope':ctx['scope'],'physical_scope':target['scope'],
      'record_id':target['id'],'changed_fields':['title_en','excerpt_en'],'rollback_allowed':False}
    validation=w._VALIDATION_CONTEXT.get()
    if validation is not None:validation.recheck()
    return {'task_id':TASK,'sender_department':'designated-development','department':'designated-development',
      'action_id':ACTION,'action_class':'site_ci_prepare','scope':ctx['scope'],'source_project_id':a.PROJECT,
      'execution_project_id':ctx['binding']['project_id'],'operation':OP,'state':state,'observed_at':actual['server_observed_at'],
      'authorization_changes':[],'exact_original_production_source':ctx['registration'],'desired':desired}, identity, actual, ctx

def intent(root,req,ctx,check_desired=True, *, allowed_policy=None):
    rebuilt=request_base(root,req.get('task_id'),req.get('state'),allowed_policy=allowed_policy)
    base={k:v for k,v in req.items() if k not in {'facts','self_check','backup','rollback'}}
    a.require(base==rebuilt and ctx.get('registration')==rebuilt['exact_original_production_source'],
              'EN2 preview: exact verified request and source required')
    return ctx,OP,req['state'],rebuilt['desired']


def _verify_local_git(root,ctx,state):
    import subprocess
    # Only the directly supplied, immutable original WEB readiness input can
    # anchor code bytes; it is not an authorization or a freshness source.
    pin={'path':'logs/handoffs/2026-11-01-EN2-protected-preview-WEB-readiness-v1/EXACT-EN2-ZERO-WRITE-PREVIEW-NORMAL-GATE-INPUT-v1.json',
         'sha256':'7ef0119d586961a47f93f9720b8fce72f159398e1f20b51fece4fae7bebfb33e','size':7194}
    source=a.document(root,pin);baseline=source.get('current_main_at_recorded_observation')
    a.require(source.get('schema')=='exact-original-EN2-zero-write-preview-normal-admission-gap/v1'
              and source.get('task_id')==TASK and source.get('namespace')=='english-kitchen-en2-exact-v1'
              and isinstance(baseline,str) and __import__('re').fullmatch('[0-9a-f]{40}',baseline),
              'EN2 preview: exact original WEB source baseline required')
    allowed=Path(ctx['binding']['cwd']).resolve(strict=True)
    wt=Path(state.get('worktree','')).resolve(strict=True)
    a.require(wt.is_dir() and wt.is_relative_to(allowed),'EN2 preview: original WEB project worktree required')
    def run(*args):
        return subprocess.run(['git',*args],cwd=wt,capture_output=True,text=True,timeout=20)
    def read(*args):
        result=run(*args);a.require(result.returncode==0,'EN2 preview: actual local Git source required');return result.stdout.strip()
    main=state.get('main_sha')
    a.require(Path(read('rev-parse','--show-toplevel')).resolve()==wt
              and read('symbolic-ref','--short','HEAD')=='main'
              and read('rev-parse','HEAD')==main and read('rev-parse','refs/heads/main')==main,
              'EN2 preview: actual local original main and HEAD required')
    a.require(run('merge-base','--is-ancestor',baseline,main).returncode==0,
              'EN2 preview: current main must descend from actual original WEB baseline')
    paths=['.github/workflows/content-publish-approved.yml','package.json','package-lock.json','scripts/',
           'drafts/publishing/fc-20261011-english-kitchen-actual-publication-goal-v1/frozen-current-english-kitchen-en2-candidate.json']
    if run('diff','--quiet',baseline,main,'--',*paths).returncode==0:
        return

    # WEB subsequently read back the live shared workflow after the NEXT8
    # target addition. Use only that exact, formally received review.
    receipt_pin={'path':'reports/local-department-system-repair-20261030-v1/OPEN-SOURCE-REFERENCE-REVIEW-20261105-v1/IMPLEMENTATION-CONTINUATION-v1/original-en2-readonly-send-2026-11-05T073553Z/collaboration-actual-result-input.json',
                 'sha256':'b47f10e77bbf83bcb8860a816717ce88b2a0de557b04268ba0fb1cef8ab6fdef','size':1847}
    events=w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS,where={'task_id':TASK,
                      'event_id':'6864c609-70d3-4959-9962-c99a147d0464'})
    a.require(len(events)==1 and events[0]['details'].get('collaboration_receipt')==receipt_pin
              and not w.validate_workflow_events(root,TASK),'EN2 preview: original WEB review receipt required')
    receipt=a.document(root,receipt_pin); report=a.document(root,receipt['result'])
    reviewed_main='f5591dbc1c08c2a033d951a7c85016cb98986f18'
    a.require(receipt.get('status')=='result_received'
              and receipt.get('target_thread_id')==ctx['binding']['thread_id']
              and report.get('schema')=='WEB-original-EN2-SYS50-readonly-runtime-result/v1'
              and report.get('task_id')==TASK and report.get('scope')==ctx['scope']
              and report.get('actual_executor')==ctx['role'] and report.get('remote_main')==reviewed_main
              and report.get('CLI_namespace')=='english-kitchen-en2-exact-v1'
              and report.get('hosted_workflow_choice_verified_at_main') is True
              and report.get('web_code_or_production_mutations')==0
              and run('merge-base','--is-ancestor',reviewed_main,main).returncode==0,
              'EN2 preview: exact received WEB review must bind the current preview source')
    if run('diff','--quiet',reviewed_main,main,'--',*paths).returncode==0:
        return

    # The source review received after the v14 main move applies only to its
    # exact revision, exact protected paths and the original WEB/PUB route.
    review_event='337cf6f4-24ee-4645-983f-8b63a805b2cd'
    events=w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS,where={'task_id':TASK,'event_id':review_event})
    a.require(len(events)==1 and events[0]['details'].get('external_permission_issued') is False,
              'EN2 preview: original WEB must provide a normally received new source review')
    receipt=a.document(root,events[0]['details']['collaboration_receipt'])
    report=a.document(root,receipt['result'])
    current_review='9177e06c28f84a8e93a6ae1e51fc3c47dbfd8cce'
    a.require(receipt.get('status')=='result_received' and receipt.get('task_id')==TASK
              and receipt.get('action_id')=='PUB-EN2-original-WEB-main9177e-readonly-source-20261106-v1'
              and receipt.get('scope')==ctx['scope'] and receipt.get('target_thread_id')==ctx['binding']['thread_id']
              and report.get('schema')=='original-WEB-readonly-result-intake/v1' and report.get('task_id')==TASK
              and report.get('source_thread')==receipt['target_thread_id']
              and report.get('source_turn')==receipt['recipient_turn_id']
              and report.get('source_final')==receipt['message_ref']
              and report.get('native')==receipt['actual_native_result']
              and report.get('local_main')==reviewed_main and report.get('github_main')==main==current_review
              and report.get('preview_run')==42167494036 and report.get('preview_artifact')==13479895807
              and report.get('production_ready') is False and report.get('save') is False,
              'EN2 preview: exact new reviewed GitHub main and verified original receipt required')
    a.document(root,receipt['actual_native_result'])
    changed=set(read('diff','--name-only',reviewed_main,main,'--',*paths).splitlines())
    a.require(changed=={'package.json','package-lock.json','scripts/record-recovery-status.mjs',
                       'scripts/supabase-content-publish-release.mjs','scripts/supabase-content-publish-release.test.mjs',
                       'scripts/verify-admin-foundation.mjs'},
              'EN2 preview: protected path changes differ from the original WEB review')
