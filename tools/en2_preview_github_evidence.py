"""Original EN2 preview GitHub channel evidence; read-only, never a grant."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import datetime as dt,json,re,subprocess
import workflow_control as w
import department_autonomy as a
TASK='fc-20261011-english-kitchen-actual-publication-goal-v1'
REPO='example-owner/example-website'
WORKFLOW='.github/workflows/content-publish-approved.yml'
NAME='english-kitchen-en2-exact-v1'
STATUSES=('queued','in_progress','waiting','pending','requested')

def _get(path):
    args=['gh','api','--method','GET',path]
    try:
        p=subprocess.run(args,capture_output=True,check=True,timeout=8)
    except subprocess.TimeoutExpired:
        # Only this read is retried. An unavailable result still fails closed.
        p=subprocess.run(args,capture_output=True,check=True,timeout=12)
    return json.loads(p.stdout)

def read_actual(root,expected_main):
    import professional_web_execution as web
    source=web.records(Path(root),TASK)
    a.require(len(source)==1 and source[0].get('current_owner_reviewed_release') is True and source[0].get('role')=='designated-development'
       and source[0].get('registration',{}).get('sha256')=='f52a048ab07e02f2e90984b5a40a31b0f52faf3f9f7164ddacb578f58871ecb3'
       and source[0].get('repository')==REPO,'EN2 preview: actual original f52 WEB authority required')
    return _read_hosted_channel(expected_main)


def _read_hosted_channel(expected_main):
    a.require(isinstance(expected_main,str) and re.fullmatch('[0-9a-f]{40}',expected_main),'EN2 preview: actual main SHA required')
    start=dt.datetime.now(dt.timezone.utc);pre='repos/'+REPO
    endpoint=pre+'/actions/workflows/content-publish-approved.yml'
    with ThreadPoolExecutor(max_workers=4) as reads:
        who,repo,ref,workflow=reads.map(_get,('user',pre,pre+'/git/ref/heads/main',endpoint))
    a.require(who.get('id')==276684684 and who.get('login')=='example-owner' and repo.get('id')==1248188229 and repo.get('full_name')==REPO
       and ref.get('object',{}).get('sha')==expected_main and workflow.get('path')==WORKFLOW and workflow.get('state')=='active'
       and workflow.get('name')=='Approved website content publish','EN2 preview: original authenticated GitHub actor/repo/main/workflow required')
    # Fail closed if the original shared workflow is busy or any result page is incomplete.
    with ThreadPoolExecutor(max_workers=4) as reads:
        for rows in reads.map(_get,(endpoint+'/runs?per_page=100&status='+status for status in STATUSES)):
            a.require(type(rows.get('total_count')) is int and isinstance(rows.get('workflow_runs'),list)
                and rows['total_count']==len(rows['workflow_runs'])==0,'EN2 preview: shared workflow busy, unknown or truncated')
    # No claim that this proves absence of a prior untracked run; a separately
    # authenticated original-key/intent check is still mandatory.
    end=dt.datetime.now(dt.timezone.utc);a.require(0<=(end-start).total_seconds()<=300,'EN2 preview: current GitHub reads expired')
    return {'state':'GITHUB_CHANNEL_OBSERVED_ONLY','repository':REPO,'main_sha':expected_main,'actor_id':who['id'],
      'workflow_path':WORKFLOW,'workflow_id':workflow['id'],'observed_at':end.isoformat(),
      'previous_effect':'UNKNOWN_REQUIRES_ORIGINAL_KEY_CHECK','permission_issued':False,'dispatch_allowed':False}
