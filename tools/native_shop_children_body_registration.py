"""Frozen Shop/children registration only. Never grants a new CMS permit."""
from __future__ import annotations
import hashlib, importlib.util, json
from pathlib import Path

ROOT = Path('<PROJECT_ROOT>')
PROJECT = '<LOCAL_PROJECT_ID>'
MANIFEST_PATH = 'drafts/operations/fc-20261002-two-cms-issuer-registration-only-v1/registration-manifest.json'
MANIFEST_SHA256 = '20979d9a9915e1ac1e9b082cd8ddd164f906cfefbeea50ec794c8bc0676e7b76'
APPROVED_PROPOSAL = {'path': 'drafts/operations/fc-20261002-two-cms-exact-admission-control-v2/registration-proposal.json', 'sha256': '79295b635e1d11a14142c1760fa374c8c383110fa878c00a272c60b05a826224', 'size': 5026}
APPROVED_VALIDATOR = {'path': 'drafts/operations/fc-20261002-two-cms-exact-admission-control-v2/validate_registration.py', 'sha256': '7c7dc47a3b7c8dda133cbc03565ddab59fad6877d80aab5bcbfaa7edf662f4ea', 'size': 8163}
EXPECTED = {
    'shop': ('fc-20261002-shop-v10-current-source-binding-v1', 'd1-shop-v10-protected-source-preview-v2-1510', 'shop-v10-protected-source-preview-v2-20261002', '32f5374f-9919-41ea-80c7-00b5ac917532', 'shop-renovation'),
    'children': ('fc-20261002-children-v11-current-source-binding-v1', 'd1-children-v11-protected-source-preview-v2-1510', 'children-v11-protected-source-preview-v2-20261002', 'b401a610-a4dc-4a0b-a7e0-efcac6c81d71', 'builtin'),
}

def require(ok, reason):
    if not ok: raise ValueError(reason)

def pinned(root, pin):
    root=root.resolve();relative=Path(pin['path']);p=(root/relative).resolve()
    require(root==ROOT and not relative.is_absolute() and p.is_relative_to(root) and p.is_file(),'exact project boundary')
    raw=p.read_bytes();require(hashlib.sha256(raw).hexdigest()==pin['sha256'],'frozen source hash changed')
    return p, raw

def validate_registration(root, manifest):
    require(manifest.get('schema_version')=='shop_children_body_registration_only_v1'
        and manifest.get('project_id')==PROJECT
        and manifest.get('candidate_version')=='two-cms-issuer-registration-only-v1-20261002'
        and manifest.get('execution_owner')=='content-organic-website'
        and manifest.get('mode')=='REGISTRATION_ONLY_NO_PERMIT'
        and manifest.get('release_ready') is False
        and manifest.get('production_authorized') is False
        and manifest.get('native_registration_only') is True
        and manifest.get('actual_remote_preview') is None,'registration cannot assert release or preview')
    require(manifest.get('approved_proposal')==APPROVED_PROPOSAL
        and manifest.get('approved_validator')==APPROVED_VALIDATOR,'only exact approved proposal and validator')
    _,raw=pinned(root,manifest['approved_proposal']);proposal=json.loads(raw)
    require(proposal.get('project_id')==PROJECT and proposal.get('execution_owner')=='content-organic-website'
        and proposal.get('candidate_version')=='two-cms-exact-admission-control-v2-20261002'
        and proposal.get('mode')=='TWO_TARGET_REGISTRATION_PROPOSAL_ONLY'
        and proposal.get('production_authorized') is False
        and proposal.get('applied_to_active_issuer') is False,'approved proposal identity')
    vp,_=pinned(root,manifest['approved_validator'])
    spec=importlib.util.spec_from_file_location('flashcast_frozen_two_target_validator',vp)
    validator=importlib.util.module_from_spec(spec);spec.loader.exec_module(validator)
    rows=proposal.get('entries',[]);require(len(rows)==2 and {r.get('target_name') for r in rows}==set(EXPECTED),'only exact original two targets')
    targets={}
    for row in rows:
        keys=['task_id','action_id','candidate_version','record_id','slug']
        require(tuple(row.get(k) for k in keys)==EXPECTED[row['target_name']],'exact task action version record slug')
        validator.validate_entry(row)
        _,rr=pinned(root,row['admission_request']);req=json.loads(rr)
        cv=row['candidate_version'];require(cv not in targets,'duplicate target')
        targets[cv]={**{k:row[k] for k in keys},'table':'services','scope':row['scope'],
            'candidate_shape':'native_shop_children_body_registration',
            'changed_fields':['content_en','content_zh'],
            'candidate':(row['source_candidate']['path'],row['source_candidate']['sha256']),
            'source_frozen_candidate':(row['source_candidate']['path'],row['source_candidate']['sha256']),
            'rollback':(req['source']['path'],req['source']['sha256']),
            'expected_updated_at':req['expected_updated_at'],
            **{k:row[k] for k in ['baseline_fields_sha256','desired_fields_sha256','retained_fields_sha256','rollback_fields_sha256']},
            'native_registration_only':True,'release_ready':False,'production_authorized':False,
            'qa_outbox':None,'requires_completed_parent':True,'native_source_manifest':MANIFEST_PATH}
    return targets

def load_shop_children_body_registration(root):
    _,raw=pinned(root,{'path':MANIFEST_PATH,'sha256':MANIFEST_SHA256})
    return validate_registration(root,json.loads(raw))

def validate_shop_children_body_candidate(root,candidate,target):
    frozen=load_shop_children_body_registration(root).get(target.get('candidate_version'))
    require(frozen is not None and target==frozen,'target must remain frozen registration only')
    _,raw=pinned(root,{'path':target['candidate'][0],'sha256':target['candidate'][1]})
    require(candidate==json.loads(raw),'exact original candidate required')
