"""Read exact EN2 preview history; no policy, run, mutation or permission."""
import base64,datetime as dt,json,re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import workflow_control as w
import department_autonomy as a
import en2_preview_github_evidence as gh
TASK=gh.TASK
NAME=gh.NAME
ACTION=TASK+'-original-protected-preview-dry-run-v1'
RECONCILED='en2_expired_preview_policy_without_dispatch'
REFRESH='en2_original_zero_write_preview_refresh'
SUCCESSOR='en2_zero_write_after_forward_receipt_repair'
PREISSUE_RETRY='en2_zero_write_after_verified_preissue_expiry'
PREISSUE_RUN=42064196823
PREISSUE_POLICY='pol-92101cbfb2f34b3dc323'
POLICY_TIMING_RETRY='en2_zero_write_after_verified_nonconsuming_policy_timeout'
POLICY_TIMING_RUN=42074166677
POLICY_TIMING_PREFLIGHT='4dc7f69c-f782-4ed6-9300-01e8499bad89'
NO_TRANSPORT_RETRY='en2_zero_write_after_verified_issuer_project_refusal'
NO_TRANSPORT_RUN=42078248351
NO_TRANSPORT_POLICY='pol-ab2a235a696ff6c5989d'
NO_TRANSPORT_PREFLIGHT='4e3ae9ed-6ee1-4cd8-a92b-cd3382ae0d63'
ORIGINAL_ISSUER_INTENT='logs/en2-forward-issuer-once-ca74880c3ea61ff646e6e87ed93f24260a8fdc6564fdde5b788a6d353f32fc86.json'
MAIN_MOVE_RETRY='en2_zero_write_after_verified_main_move'
MAIN_MOVE_RUN=42167494036
MAIN_MOVE_FROM='f5591dbc1c08c2a033d951a7c85016cb98986f18'
MAIN_MOVE_TO='9177e06c28f84a8e93a6ae1e51fc3c47dbfd8cce'
MAIN_MOVE_REVIEW='337cf6f4-24ee-4645-983f-8b63a805b2cd'
REFUSAL_RUN=42049799511
REFUSAL={
    'path':f'drafts/publishing/{TASK}/forward-save-{REFUSAL_RUN}-20261105-v1/PUB-EN2-ACTUAL-FORWARD-PREFLIGHT-REFUSAL.json',
    'sha256':'029e776824d429fc8a72eb52dfc66af20c1458c9d24f446b11c940b377448451',
    'size':3086,
}

def original_intent_path(root):
    key=w.sha256_value([TASK,'designated-development',ACTION,'site_ci_prepare','cms:services:kitchen:english-two-fields:publication:v1'])
    return Path(root)/'logs'/('en2-protected-preview-intent-'+key+'.json')


def refresh_record(root):
    events=w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS,where={'task_id':TASK})
    return _refresh_from_events(root,events)


def _refresh_from_events(root,events):
    rows=[e['details'][REFRESH] for e in events if REFRESH in e.get('details',{})]
    if not rows:
        return None
    a.require(len(rows)==1 and not w.validate_workflow_events(root,TASK),
              'EN2 preview: exactly one intact zero-write refresh registration allowed')
    row=rows[0];old=original_intent_path(root)
    a.require(row.get('original_intent')==w.file_digest(root,str(old.relative_to(root)))
              and row.get('preview',{}).get('preview_origin')=='VERIFIED_HISTORICAL_ZERO_WRITE'
              and row.get('preview',{}).get('actual_action_allowed') is False
              and row.get('external_permission_issued') is False,
              'EN2 preview: original immutable intent and historical zero-write receipt required')
    return row


def intent_path(root):
    records=retired_receipts(root)
    return _intent_path(root, len(records))


def _intent_path(root, count):
    original=original_intent_path(root)
    suffix={0:'',1:'-fresh-proof-once',2:'-forward-receipt-repair-once',3:'-preissue-expiry-recovery-once',
            4:'-policy-timing-repair-once',5:'-issuer-project-refusal-once',6:'-verified-main-move-once'}[count]
    return original.with_name(original.stem+suffix+'.json')


def retired_receipts(root):
    events=w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS,where={'task_id':TASK})
    refresh=_refresh_from_events(root,events)
    rows=[e['details'][SUCCESSOR] for e in events if SUCCESSOR in e.get('details',{})]
    retries=[e['details'][PREISSUE_RETRY] for e in events if PREISSUE_RETRY in e.get('details',{})]
    timing=[e['details'][POLICY_TIMING_RETRY] for e in events if POLICY_TIMING_RETRY in e.get('details',{})]
    transport=[e['details'][NO_TRANSPORT_RETRY] for e in events if NO_TRANSPORT_RETRY in e.get('details',{})]
    main_moves=[e['details'][MAIN_MOVE_RETRY] for e in events if MAIN_MOVE_RETRY in e.get('details',{})]
    a.require(not main_moves or len(main_moves)==1 and len(transport)==1,
              'EN2 preview: one exact reviewed main move only after intact issuer reconciliation')
    a.require(not transport or len(transport)==1 and len(timing)==1 and len(retries)==1,
              'EN2 preview: exactly one original issuer project refusal recovery after intact history')
    if not rows:
        a.require(not retries and not timing,'EN2 preview: recovery requires original successor')
        return [refresh] if refresh else []
    a.require(refresh is not None and len(rows)==1 and not w.validate_workflow_events(root,TASK),
              'EN2 preview: one bounded successor of the original refresh required')
    row=rows[0];prior=_intent_path(root,1)
    a.require(row.get('original_intent')==w.file_digest(root,str(prior.relative_to(root)))
              and row.get('forward_refusal')==REFUSAL and a.document(root,REFUSAL).get('preview_run')==REFUSAL_RUN
              and row.get('preview',{}).get('run_id')==REFUSAL_RUN
              and row.get('preview',{}).get('preview_origin')=='VERIFIED_HISTORICAL_ZERO_WRITE'
              and row.get('preview',{}).get('actual_action_allowed') is False
              and row.get('external_permission_issued') is False,
              'EN2 preview: unchanged original refresh and exact forward refusal required')
    if not retries:
        a.require(not timing,'EN2 preview: policy timing recovery requires original preissue recovery')
        return [refresh,row]
    a.require(len(retries)==1,'EN2 preview: one exact preissue-expiry recovery only')
    retry=retries[0]; prior=_intent_path(root,2)
    a.require(retry.get('original_intent')==w.file_digest(root,str(prior.relative_to(root)))
              and retry.get('preview',{}).get('run_id')==PREISSUE_RUN
              and retry.get('preview',{}).get('preview_origin')=='VERIFIED_HISTORICAL_ZERO_WRITE'
              and retry.get('preview',{}).get('actual_action_allowed') is False
              and retry.get('retired_cms_policy_id')==PREISSUE_POLICY
              and retry.get('external_permission_issued') is False,
              'EN2 preview: intact successor and exact expired preissue policy required')
    records=[refresh,row,retry]
    if not timing:
        return records
    a.require(len(timing)==1,'EN2 preview: one original non-consuming policy timing recovery only')
    timing=timing[0];prior=_intent_path(root,3)
    a.require(timing.get('original_intent')==w.file_digest(root,str(prior.relative_to(root)))
              and timing.get('preview',{}).get('run_id')==POLICY_TIMING_RUN
              and timing.get('preview',{}).get('preview_origin')=='VERIFIED_HISTORICAL_ZERO_WRITE'
              and timing.get('preview',{}).get('actual_action_allowed') is False
              and timing.get('preflight_event_id')==POLICY_TIMING_PREFLIGHT
              and timing.get('external_permission_issued') is False,
              'EN2 preview: intact prior recovery and exact non-consuming policy refusal required')
    records.append(timing)
    if transport:
        refused=transport[0]
        a.require(refused.get('original_intent')==w.file_digest(root,str(_intent_path(root,4).relative_to(root)))
                  and refused.get('issuer_intent')==w.file_digest(root,ORIGINAL_ISSUER_INTENT)
                  and refused.get('preview',{}).get('run_id')==NO_TRANSPORT_RUN
                  and refused.get('preview',{}).get('preview_origin')=='VERIFIED_HISTORICAL_ZERO_WRITE'
                  and refused.get('retired_cms_policy_id')==NO_TRANSPORT_POLICY
                  and refused.get('preflight_event_id')==NO_TRANSPORT_PREFLIGHT
                  and refused.get('external_permission_issued') is False,
                  'EN2 preview: original v13 pre-transport refusal and immutable intent required')
        records.append(refused)
    if main_moves:
        move=main_moves[0]
        a.require(move.get('original_intent')==w.file_digest(root,str(_intent_path(root,5).relative_to(root)))
                  and move.get('review_event_id')==MAIN_MOVE_REVIEW and move.get('requested_head')==MAIN_MOVE_FROM
                  and move.get('preview',{}).get('head_sha')==MAIN_MOVE_TO
                  and move.get('preview',{}).get('run_id')==MAIN_MOVE_RUN
                  and move.get('preview',{}).get('artifact_id')==13479895807
                  and move.get('preview',{}).get('preview_origin')=='VERIFIED_HISTORICAL_ZERO_WRITE'
                  and move.get('preview',{}).get('actual_action_allowed') is False
                  and move.get('external_permission_issued') is False,
                  'EN2 preview: exact v14 mismatched zero-write run and normally received new main review required')
        records.append(move)
    return records


def live_cms_policy_rows(root):
    """Filter only an authenticated, append-only retirement of a zero-effect policy."""
    root=Path(root)
    rows=[p for p in w.read_jsonl(root/w.POLICY_DECISIONS,where={
        'task_id':TASK,'action_id':'save-kitchen-english-two-fields-v1','action_class':'cms_write',
        'department':'publishing','status':'allow'})]
    retired=retired_receipts(root)
    if len(retired)<3:
        return rows
    prior={PREISSUE_POLICY:retired[2]}
    if len(retired)>=5:
        prior[NO_TRANSPORT_POLICY]=retired[4]
    for decision, evidence in prior.items():
        old=[p for p in rows if p.get('decision_id')==decision]
        a.require(len(old)==1 and w.sha256_value(old[0])==evidence.get('retired_cms_policy_sha256'),
                  'EN2 preview: original spent policy must remain unchanged')
    return [p for p in rows if p.get('decision_id') not in prior]


def unresolved_preview_policies(root):
    """Retired policies remain immutable and cannot authorize transport."""
    return _unresolved_preview_policies(root, retired_receipts(root))


def _unresolved_preview_policies(root, records):
    root=Path(root)
    policies=[p for p in w.read_jsonl(root/w.POLICY_DECISIONS,where={'task_id':TASK,'action_id':ACTION})
              if p.get('status')=='allow']
    events=w.read_jsonl(root/w.WORKFLOW_EVENTS,where={'task_id':TASK})
    retired=[e['details'][RECONCILED] for e in events if RECONCILED in e.get('details',{})]
    retired.extend(records)
    if not retired:
        return policies
    a.require(not w.validate_workflow_events(root,TASK),'EN2 preview: intact reconciliation journal required')
    seen=set()
    for record in retired:
        matches=[p for p in policies if p.get('decision_id')==record.get('policy_id')]
        a.require(len(matches)==1 and record.get('policy_id') not in seen
                  and record.get('policy_sha256')==w.sha256_value(matches[0])
                  and record.get('effect') in {'NO_DISPATCH_INTENT_AND_NO_HOSTED_RUN','COMPLETED_ZERO_WRITE_RECEIPT_EXPIRED'}
                  and record.get('external_permission_issued') is False,
                  'EN2 preview: unique exact expired-policy reconciliation required')
        seen.add(record['policy_id'])
    return [p for p in policies if p.get('decision_id') not in seen]

def read_actual(root, *, allowed_policy=None):
    import professional_web_execution as web
    root=Path(root).resolve();sources=web.records(root,TASK)
    a.require(len(sources)==1 and sources[0].get('current_owner_reviewed_release') is True and sources[0].get('role')=='designated-development'
              and sources[0].get('registration',{}).get('sha256')=='f52a048ab07e02f2e90984b5a40a31b0f52faf3f9f7164ddacb578f58871ecb3',
              'EN2 preview history: original authenticated source required')
    created,epoch,prior_run=_history_inputs(root,sources[0],allowed_policy)
    return _read_hosted_history(created,epoch,prior_run)


def _history_inputs(root,source,allowed_policy):
    human=a.document(root,source['authorization']);epoch=human.get('selected_native',{}).get('turn',{}).get('startedAt')
    a.require(type(epoch) in (int,float) and 0<epoch<=dt.datetime.now(dt.timezone.utc).timestamp(),'EN2 preview history DATA_MISSING: original owner time required')
    source_doc=a.document(root,source['registration']);contract=a.document(root,source_doc.get('goal_contract'))
    created=w._parse_observed_at(contract.get('created_at'))
    a.require(source_doc.get('task_id')==TASK and contract.get('task_id')==TASK and created is not None
              and created.timestamp()<=epoch,'EN2 preview history DATA_MISSING: exact original goal creation source required')
    records=retired_receipts(root)
    a.require(not _intent_path(root,len(records)).exists(),'EN2 preview history: original durable intent exists, effect unknown; inspect before retry')
    prior=root/'logs'/'preview-dispatch'/TASK
    a.require(not prior.exists() or prior.is_dir() and not any(prior.iterdir()),'EN2 preview history: existing original dispatch records require effect readback')
    rows=w.read_jsonl(root/w.POLICY_DECISIONS,where={'task_id':TASK})
    current_ids={p.get('decision_id') for p in _unresolved_preview_policies(root,records)}
    allowed_count=0
    for policy in rows:
        if not (policy.get('task_id')==TASK and policy.get('status')=='allow' and policy.get('action_class')=='site_ci_prepare'):
            continue
        if policy.get('action_id')==ACTION and policy.get('decision_id') not in current_ids:
            continue
        if policy.get('action_id')==ACTION and allowed_policy is not None and policy==allowed_policy:
            allowed_count+=1
            a.require(allowed_count==1 and policy.get('status')=='allow', 'EN2 preview history: duplicate own policy')
            continue
        a.require('preview' not in str(policy.get('action_id','')).lower(),
                  'EN2 preview history: existing preview policy requires original-key investigation')
        pin=policy.get('exact_request')
        a.require(isinstance(pin,dict),'EN2 preview history DATA_MISSING: same-task policy request cannot be classified')
        prior_request=a.document(root,pin)
        a.require(all(prior_request.get(k)==policy.get(k) for k in ('task_id','action_id','action_class','scope','department')),
                  'EN2 preview history: original same-task policy/request identity differs')
        a.require(prior_request.get('operation') in {'git_push','pull_request','official_ci','merge','r3_cancel','r3_retire','r3_dispatch'},
                  'EN2 preview history: same-task policy operation is preview or unknown')
    a.require(allowed_policy is None or allowed_count==1,'EN2 preview history: actual own policy not present exactly once')
    return created,epoch,tuple(record['preview']['run_id'] for record in records)


def _read_hosted_history(created,epoch,prior_run=None):
    prior_runs={prior_run} if type(prior_run) is int else set(prior_run or ())
    prefix='repos/'+gh.REPO;workflow=gh._get(prefix+'/actions/workflows/content-publish-approved.yml')
    a.require(workflow.get('path')==gh.WORKFLOW and workflow.get('state')=='active' and type(workflow.get('id')) is int,'EN2 preview history: actual original workflow required')
    day=created.date().isoformat();seen=set();heads=set();count=None;page=1;total=0;prior_seen=set()
    while True:
        a.require(page<=20,'EN2 preview history DATA_MISSING: history exceeds bounded complete listing')
        result=gh._get(prefix+'/actions/workflows/content-publish-approved.yml/runs?per_page=100&page='+str(page)+'&event=workflow_dispatch&created=%3E%3D'+day)
        runs=result.get('workflow_runs');n=result.get('total_count')
        a.require(type(n) is int and isinstance(runs,list) and len(runs)<=100 and (count is None or count==n),'EN2 preview history DATA_MISSING: incomplete or changing listing')
        count=n;total+=len(runs)
        for run in runs:
            rid=run.get('id');head=run.get('head_sha');run_created=w._parse_observed_at(run.get('created_at'))
            a.require(type(rid) is int and rid>0 and rid not in seen and isinstance(head,str) and re.fullmatch('[0-9a-f]{40}',head)
               and run.get('event')=='workflow_dispatch' and run.get('path')==gh.WORKFLOW and run_created is not None
               and run.get('repository',{}).get('id')==1248188229,'EN2 preview history DATA_MISSING: actual original run identity incomplete')
            seen.add(rid)
            if run_created<created:continue
            heads.add(head)
            title=run.get('display_title');a.require(isinstance(title,str) and re.fullmatch(r'[^|\r\n]+ \| (?:dry-run|publish)',title),'EN2 preview history DATA_MISSING: ambiguous original run title')
            if rid in prior_runs:
                a.require(title==NAME+' | dry-run' and run.get('status')=='completed'
                          and run.get('conclusion')=='success' and run.get('run_attempt')==1,
                          'EN2 preview history: original verified zero-write run changed')
                prior_seen.add(rid)
                continue
            a.require(title not in {NAME+' | dry-run',NAME+' | publish'},'EN2 preview history: original preview effect exists or unknown; never resend')
        if total>=count:break
        a.require(len(runs)==100,'EN2 preview history DATA_MISSING: truncated listing');page+=1
    a.require(total==count,'EN2 preview history DATA_MISSING: nonunique or incomplete listing')
    a.require(prior_seen==prior_runs,'EN2 preview history: original verified zero-write run missing')
    with ThreadPoolExecutor(max_workers=4) as reads:
        for doc in reads.map(gh._get,(prefix+'/contents/'+gh.WORKFLOW+'?ref='+head for head in sorted(heads))):
            a.require(doc.get('encoding')=='base64' and isinstance(doc.get('content'),str),'EN2 preview history DATA_MISSING: run-head workflow source')
            try:text=base64.b64decode(''.join(doc['content'].split()),validate=True).decode('utf-8')
            except (ValueError,UnicodeError) as exc:raise w.WorkflowError('EN2 preview history: invalid workflow source') from exc
            expected="run-name: ${{ format('{0} | {1}', inputs.target, inputs.mode) }}"
            a.require([line for line in text.splitlines() if line.startswith('run-name:')]==[expected],'EN2 preview history DATA_MISSING: historical run-name cannot identify input')
    return {'state':'NO_ORIGINAL_PREVIEW_OBSERVED_COMPLETE_HISTORY','goal_created_at':created.isoformat(),'authority_at_utc':dt.datetime.fromtimestamp(epoch,dt.timezone.utc).isoformat(),'runs_checked':total,'observed_at':dt.datetime.now(dt.timezone.utc).isoformat(),'permission_issued':False,'dispatch_allowed':False}
