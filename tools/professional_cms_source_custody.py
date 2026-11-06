"""Read missing frozen external bytes only from an authenticated custody event.

The original path and all historical records remain unchanged. This provides
source bytes, not a worktree, current state, execution authority or permit.
"""
from pathlib import Path
import hashlib
import json
import subprocess
import tarfile
import workflow_control as w
import department_autonomy as a

SCHEMA='immutable-external-source-custody/v1'
EVENT='immutable_external_source_custody'


def _pin(root,pin):
    a.require(isinstance(pin,dict) and set(pin)=={'path','sha256','size'}
              and w.file_digest(root,pin['path'])==pin,'exact custody evidence pin required')
    return json.loads(w.safe_path(root,pin['path']).read_bytes())


def validate(root,item):
    root=Path(root).resolve(strict=True)
    keys={'schema','maintenance_task_id','parent_task_id','original_stage_event_id',
          'original_stage_source','original_candidate','recovered_candidate','recovery_receipt',
          'archive_member','archive'}
    a.require(isinstance(item,dict) and set(item)==keys and item['schema']==SCHEMA,'exact immutable custody schema required')
    parent=w.validate_task_id(item['parent_task_id']);maint=w.validate_task_id(item['maintenance_task_id'])
    a.require(parent!=maint,'distinct original parent and maintenance required')
    events=[e for e in w.read_jsonl(root/w.WORKFLOW_EVENTS) if e.get('event_id')==item['original_stage_event_id']]
    a.require(len(events)==1 and events[0].get('task_id')==maint,'one actual original stage event required')
    details=events[0].get('details',{})
    original=details.get('professional_cms_legacy_current_stage_source')
    issuer=details.get('professional_cms_legacy_stage_issuer_source')
    a.require((isinstance(original,dict)) != (isinstance(issuer,dict)),'one genuine original stage or issuer event required')
    entry=original if original is not None else issuer
    a.require(entry.get('parent_task_id' if original is not None else 'task_id')==parent
              and entry.get('source')==item['original_stage_source'], 'actual committed original parent/source pin required')
    stage=_pin(root,item['original_stage_source']);a.require(stage['parent_task_id']==parent and stage['maintenance_task_id']==maint,
          'unchanged original parent/maintenance required')
    report=_pin(root,stage['web_result' if original is not None else 'WEB_report'])
    native=_pin(root,stage['web_native' if original is not None else 'WEB_completed_native'])
    receipt=_pin(root,item['recovery_receipt'])
    pinned_candidate=stage['candidate'] if original is not None else report['frozen_source']
    a.require(pinned_candidate==item['original_candidate'],'unchanged original candidate pin required')
    registry=w.read_json(root/'data/department-registry.json');external=registry['collaboration_bindings']['designated-development']
    webroot=Path(external['cwd']).resolve(strict=True);candidate=Path(item['original_candidate']['path'])
    a.require(candidate.is_absolute() and candidate.resolve(strict=False).is_relative_to(webroot)
              and not candidate.exists(),'only the actually missing original external candidate can be recovered')
    a.require(native.get('capture_kind')=='first_party_read_thread_selected_items_not_full_raw'
              and native.get('thread',{}).get('id')==external['thread_id']
              and native['thread'].get('cwd')==external['cwd']
              and native['thread'].get('title')==external['title'] and native['thread'].get('hostId')==external['host_id']
              and native.get('turn',{}).get('status')=='completed' and report.get('task_id')==parent,
              'actual original WEB completed native required')
    gitinfo=report['actual_git' if original is not None else 'code'];wt=Path(gitinfo['worktree']);member=Path(item['archive_member'])
    archives=[gitinfo['archive']] if original is not None else report['source_backups_and_recovery']['archives']
    a.require(not member.is_absolute() and '..' not in member.parts and str(wt/member)==str(candidate)
              and item['archive'] in archives,'actual original worktree/archive/member relationship required')
    archived=Path(item['archive']['path']);a.require(archived.is_absolute() and archived.resolve(strict=True).is_relative_to(webroot)
             and not archived.is_symlink(),'actual original WEB archive location required')
    raw=archived.read_bytes();a.require(len(raw)==item['archive']['size']
             and hashlib.sha256(raw).hexdigest()==item['archive']['sha256'],'actual original archive bytes required')
    with tarfile.open(fileobj=__import__('io').BytesIO(raw),mode='r:*') as tar:
        found=[x for x in tar.getmembers() if x.name==item['archive_member']]
        a.require(len(found)==1 and found[0].isfile() and found[0].size==item['original_candidate']['size'],
                  'one exact regular original archive member required')
        archived_bytes=tar.extractfile(found[0]).read()
    restored_path=w.safe_path(root,item['recovered_candidate']['path'])
    a.require(w.file_digest(root,item['recovered_candidate']['path'])==item['recovered_candidate'],
              'unchanged recovered candidate pin required')
    recovered=restored_path.read_bytes();original_pin=item['original_candidate']
    receipt_ok=(receipt.get('sha256')==original_pin['sha256'] and receipt.get('old_worktree_path_missing') is True
                if original is not None else receipt.get('recovered_candidate')==item['recovered_candidate']
                and receipt.get('archive_sha256')==item['archive']['sha256']
                and receipt.get('original_git_commit')==gitinfo['head'] and receipt.get('original_worktree_missing') is True
                and receipt.get('archive_and_git_bytes_equal') is True and receipt.get('permission_issued') is False)
    a.require(recovered==archived_bytes and len(recovered)==original_pin['size']
              and hashlib.sha256(recovered).hexdigest()==original_pin['sha256'] and receipt_ok,
              'original, archive and recovered bytes must match exactly')
    # A missing worktree does not excuse an absent original Git object. Read the
    # exact original commit, blob and mode from the real existing website repo.
    repo=wt.parent.parent.resolve(strict=True);a.require(repo.is_relative_to(webroot),'original website repository required')
    def git(*args):
        p=subprocess.run(['git',*args],cwd=repo,capture_output=True,timeout=20)
        a.require(p.returncode==0,'actual original Git object unavailable');return p.stdout
    actual=git('show','-s','--format=%H %P %T',gitinfo['head']).decode().strip().split()
    parents=[gitinfo['parent']] if original is not None else gitinfo['parents']
    a.require(actual==[gitinfo['head'],*parents,gitinfo['tree']],'actual original Git commit/parent/tree required')
    files=[x for x in gitinfo['files'] if x.get('path')==item['archive_member']]
    entry=git('ls-tree',gitinfo['head'],'--',item['archive_member']).decode().strip().split()
    a.require(len(files)==1 and entry==[files[0]['mode'],'blob',files[0]['blob'],item['archive_member']]
              and files[0]['sha256']==original_pin['sha256'] and files[0]['size']==original_pin['size']
              and git('show',gitinfo['head']+':'+item['archive_member'])==recovered,
              'actual original Git blob, mode and bytes required')
    return {'parent_task_id':parent,'maintenance_task_id':maint,'original_candidate':original_pin,
            'recovered_candidate':item['recovered_candidate'],'original_git_head':gitinfo['head'],
            'original_worktree':str(wt),'actual_repository':str(repo),
            'source_only':True,'actual_action_allowed':False,'permit_issued':False}


def catalog(root,original_pin):
    root=Path(root);found=[]
    for event in w.read_jsonl(root/w.WORKFLOW_EVENTS):
        record=event.get('details',{}).get(EVENT)
        if not isinstance(record,dict) or record.get('original_candidate')!=original_pin:continue
        value=validate(root,_pin(root,record['source']))
        a.require(event.get('task_id')==value['maintenance_task_id'],'original custody event task required')
        found.append({**value,'registration':record['source'],'event_id':event['event_id']})
    a.require(len(found)<=1,'ambiguous original source recovery');return found


def recovered_bytes(root,original_pin):
    rows=catalog(root,original_pin);a.require(len(rows)==1,'one registered exact original source custody required')
    pin=rows[0]['recovered_candidate'];p=w.safe_path(Path(root),pin['path'])
    a.require(w.file_digest(Path(root),pin['path'])==pin,'recovered source changed after validation')
    return p.read_bytes()


def repository_for_original(root,original_pin,worktree,head):
    rows=catalog(root,original_pin);a.require(len(rows)==1,'one registered original Git custody required')
    row=rows[0]
    a.require(row['original_worktree']==str(worktree) and row['original_git_head']==head,
              'exact original missing worktree and immutable Git head required')
    repo=Path(row['actual_repository']).resolve(strict=True)
    p=subprocess.run(['git','rev-parse','--show-toplevel'],cwd=repo,capture_output=True,timeout=20)
    a.require(p.returncode==0 and Path(p.stdout.decode().strip()).resolve()==repo,
              'actual original Git repository root required')
    return repo


def register(root,source_path):
    root=Path(root).resolve();pin=w.file_digest(root,source_path);item=_pin(root,pin);value=validate(root,item)
    with w.workflow_lock(root):
        a.require(w.file_digest(root,source_path)==pin,'custody source changed before append')
        value=validate(root,item);existing=catalog(root,item['original_candidate'])
        if existing:
            a.require(existing[0]['registration']==pin,'different custody source already registered')
            return {'result':'duplicate_ignored',**existing[0]}
        a.require(not w.validate_workflow_events(root,value['parent_task_id'])
                  and not w.validate_workflow_events(root,value['maintenance_task_id']), 'intact original histories required')
        snap=w.read_json(w.snapshot_path(root,value['maintenance_task_id']))
        event=w.append_workflow_event(root,value['maintenance_task_id'],snap['current_state'],
              {EVENT:{'original_candidate':item['original_candidate'],'source':pin},'external_permission_issued':False})
    return {'result':'recorded',**value,'registration':pin,'event_id':event['event_id']}


def record_from_parent(root,task_id,path):
    root=Path(root).resolve();item=w.read_json(w.safe_path(root,path))
    a.require(item.get('schema')==SCHEMA and item.get('parent_task_id')==task_id,
              'exact original custody parent required')
    return register(root,path)
