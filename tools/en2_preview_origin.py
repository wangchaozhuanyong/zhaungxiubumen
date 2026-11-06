"""Read-only EN2 GitHub preview-origin verifier; never a permit or a Save."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import datetime as dt
import hashlib
import json
import re
import subprocess
import tempfile
import zipfile
import workflow_control as w

REPO = 'example-owner/example-website'
WORKFLOW = '.github/workflows/content-publish-approved.yml'
NAME = 'english-kitchen-en2-exact-v1'
TASK = 'fc-20261011-english-kitchen-actual-publication-goal-v1'
ACTOR = 276684684
REPO_ID = 1248188229


def need(condition, message):
    if not condition:
        raise w.WorkflowError('EN2 preview origin: ' + message)


def _api(path):
    # Constant repository and numeric IDs only; no credentials are written.
    from en2_preview_github_evidence import _get
    return _get(path)


def _archive(artifact_id):
    p = subprocess.run(['gh', 'api', f'repos/{REPO}/actions/artifacts/{artifact_id}/zip'],
                       check=True, capture_output=True)
    need(len(p.stdout) <= 50 * 1024 * 1024, 'artifact archive too large')
    return p.stdout


def _unpack(raw, directory):
    # Never extract arbitrary names or follow links from a remote archive.
    import io
    wanted = ['locked-candidate.json', 'desired.json', 'dry-run.json',
              'locked-dry-run-receipt.json', 'managed-payload-digest.json',
              'managed-identity-probe.json', 'backup.json']
    out = {}
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        entries = z.infolist()
        for name in wanted:
            path = NAME + '/' + name
            matches = [x for x in entries if x.filename == path]
            need(len(matches) == 1 and matches[0].file_size <= 2 * 1024 * 1024
                 and not matches[0].is_dir() and (matches[0].external_attr >> 16) & 0o170000 != 0o120000,
                 'one bounded regular artifact file required: ' + name)
            out[name] = json.loads(z.read(matches[0]))
    return out


def _validate(run_id, run, workflow, ref, artifact, docs, target, now, *, historical=False):
    """Pure checker. Caller data is not provider proof; used by live reader only."""
    need(type(run_id) is int and run_id > 0, 'positive original run ID required')
    sha = run.get('head_sha', '')
    need(run.get('id') == run_id and run.get('event') == 'workflow_dispatch'
         and run.get('status') == 'completed' and run.get('conclusion') == 'success'
         and run.get('run_attempt') == 1 and run.get('head_branch') == 'main'
         and run.get('path') == WORKFLOW and run.get('name') in {'Approved website content publish', f'{NAME} | dry-run'}
         and run.get('repository', {}).get('full_name') == REPO
         and run.get('repository', {}).get('id') == REPO_ID and run.get('actor', {}).get('id') == ACTOR
         and bool(re.fullmatch('[0-9a-f]{40}', str(sha))) and ref.get('object', {}).get('sha') == sha,
         'original completed first-attempt main workflow/repo/actor/head required')
    need(workflow.get('id') == run.get('workflow_id') and workflow.get('path') == WORKFLOW
         and workflow.get('state') == 'active' and workflow.get('name') == 'Approved website content publish',
         'active original workflow identity required')
    need(artifact.get('name') == f'approved-content-publish-{run_id}' and type(artifact.get('id')) is int
         and artifact['id'] > 0 and artifact.get('expired') is False
         and artifact.get('workflow_run', {}).get('id') == run_id
         and artifact['workflow_run'].get('repository_id') == REPO_ID
         and artifact['workflow_run'].get('head_sha') == sha, 'same-run artifact identity required')
    t=target; need(t.get('taskId') == TASK and t.get('changedFields') == ['title_en','excerpt_en']
         and t.get('rollbackAllowed') is False and len(t.get('baselineProjectionFields', [])) == 41
         and len(t.get('retainedProjectionFields', [])) == 37
         and sum(k.endswith('_ms') for k in t['retainedProjectionFields']) == 11,
         'authenticated original 41/37/MS11 forward target required')
    receipt=docs['locked-dry-run-receipt.json']; digest=docs['managed-payload-digest.json']
    preview=docs['dry-run.json']; probe=docs['managed-identity-probe.json']; locked=docs['locked-candidate.json']
    backup=docs['backup.json']; desired=docs['desired.json']; row=backup.get('record', {})
    scope=t['scope']; version=t['candidateVersion']; action=t['actionId']; ts=t['expectedUpdatedAt']
    need(all(receipt.get(k)==v for k,v in {'task_id':TASK,'candidate_version':version,'action_id':action,
         'operation':'publish','scope':scope,'http_status':200,'dry_run':True,'performed_write':False,
         'external_writes':0,'row_unchanged_after_dry_run':True,'expected_updated_at':ts}.items()),
         'same-action zero-write receipt required')
    at=w._parse_observed_at(receipt.get('checked_at'))
    start=w._parse_observed_at(run.get('run_started_at')); end=w._parse_observed_at(run.get('updated_at'))
    need(at is not None and start is not None and end is not None and start <= at <= end <= now
         and (historical or 0 <= (now-at).total_seconds() <= 300), 'fresh receipt within original completed run required')
    ident=probe.get('identity', {})
    need(probe.get('ok') is True and probe.get('dry_run') is True and probe.get('performed_write') is False
         and ident.get('runId')==run_id and ident.get('runAttempt')==1 and ident.get('repositoryId')==REPO_ID
         and ident.get('actorId')==ACTOR and ident.get('workflowSha')==sha
         and ident.get('workflowRef')==f'{REPO}/{WORKFLOW}@refs/heads/main', 'server OIDC probe must match run')
    need(all(locked.get(k)==v for k,v in {'task_id':TASK,'candidate_version':version,'action_id':action,
         'scope':scope,'expected_updated_at':ts,'changed_fields':t['changedFields'],
         'baseline_fields_sha256':t['baselineFieldsSha256'],'desired_fields_sha256':t['desiredFieldsSha256']}.items()),
         'original locked tuple and source digests required')
    key_field=backup.get('keyField','slug')
    need(backup.get('target')==NAME and backup.get('table')==t['table']
         and key_field in {'id','slug'} and backup.get('key')==t[key_field]
         and isinstance(row,dict) and set(row)==set(t['baselineProjectionFields']) and row.get('id')==t['id']
         and row.get('updated_at')==ts and type(row.get('version')) is int
         and w.sha256_value(row)==t['baselineFieldsSha256']
         and w.sha256_value({k:row[k] for k in t['retainedProjectionFields']})==t['retainedFieldsSha256'],
         'actual full41 backup and retained fields differ')
    patch=preview.get('payload_preview');after=desired.get('record')
    # The Edge dry-run response may omit this flag. The authenticated locked
    # receipt and OIDC probe above must both explicitly attest zero writes.
    need(preview.get('ok') is True and preview.get('dry_run') is True and preview.get('performed_write',False) is False
         and isinstance(patch,dict) and set(patch)==set(t['changedFields'])
         and w.sha256_value(patch)==t['desiredFieldsSha256'] and desired.get('target')==NAME
         and desired.get('operation')=='optimize' and after=={**row,**patch}
         and all(digest.get(k)==v for k,v in {'task_id':TASK,'candidate_version':version,
             'operation':'publish','payload_sha256':t['desiredFieldsSha256'],'expected_updated_at':ts}.items()),
         'preview, desired full row and original two-field digest required')
    return {'preview_origin':'VERIFIED_HISTORICAL_ZERO_WRITE' if historical else 'VERIFIED_GITHUB_PROVIDER_READ','run_id':run_id,'artifact_id':artifact['id'],
            'receipt_checked_at':receipt['checked_at'],'head_sha':sha,'task_id':TASK,'action_id':action,
            'candidate_version':version,'physical_scope':scope,'expected_updated_at':ts,
            'desired_fields_sha256':t['desiredFieldsSha256'],'full_fields':41,'protected_fields':37,
            'actual_action_allowed':False,'external_permission_issued':False,'preflight_registered':False,
            'key_effect_origin':'NOT_VERIFIED','production_READY':False}


def read_actual(root, run_id):
    """Fetch trusted GitHub APIs directly; accepts no caller-supplied run or receipt."""
    return _read_provider(root,run_id,historical=False)


def read_historical_zero_write(root, run_id):
    """Evidence for preview refresh only, never valid for forward issuance."""
    return _read_provider(root,run_id,historical=True)


def _read_provider(root,run_id,*,historical,include_artifacts=False):
    from professional_cms_issuer import targets
    root=Path(root).resolve(); source=targets(root,task_id=TASK).get(NAME)
    need(isinstance(source,dict) and source.get('source_event_id')=='698ae455-16d7-4ad1-8744-ebfc8fd763e1'
         and source.get('actual_action_allowed') is False, 'one original registered source required')
    need(type(run_id) is int and run_id>0,'positive run ID required')
    prefix=f'repos/{REPO}'
    with ThreadPoolExecutor(max_workers=4) as reads:
        run,workflow,ref,listing=reads.map(_api,(
            f'{prefix}/actions/runs/{run_id}',
            f'{prefix}/actions/workflows/content-publish-approved.yml',
            f'{prefix}/git/ref/heads/main',
            f'{prefix}/actions/runs/{run_id}/artifacts?per_page=100'))
    need(listing.get('total_count',101)<=100 and isinstance(listing.get('artifacts'),list), 'complete artifact listing required')
    rows=[x for x in listing['artifacts'] if x.get('name')==f'approved-content-publish-{run_id}']
    need(len(rows)==1 and type(rows[0].get('id')) is int and rows[0]['id']>0,'one actual original artifact required')
    raw=_archive(rows[0]['id'])
    need(rows[0].get('digest') == 'sha256:' + hashlib.sha256(raw).hexdigest(),
         'GitHub artifact digest must authenticate downloaded bytes')
    docs=_unpack(raw,root)
    verified=_validate(run_id,run,workflow,ref,rows[0],docs,source['physical_target'],dt.datetime.now(dt.timezone.utc),historical=historical)
    return (verified,docs) if include_artifacts else verified


if __name__ == '__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--run-id',type=int,required=True)
    args=parser.parse_args()
    with w.request_validation_context():
        print(json.dumps(read_actual(Path(__file__).resolve().parents[1],args.run_id),ensure_ascii=False,indent=2))
