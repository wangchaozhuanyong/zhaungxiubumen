"""Authenticated owner-adopted metadata expectations; no platform operation."""
from pathlib import Path
from copy import deepcopy
import argparse,datetime as dt,hashlib,json,re
import workflow_control as w
import department_autonomy as a
EVENT='professional_WEB_adopted_metadata_increment'
SCHEMA='professional-external-WEB-adopted-metadata-increment/v1'
CI_EVENT='professional_WEB_CI_path_successor'
CI_SCHEMA='professional-external-WEB-CI-path-successor/v1'
ORD_EVENT='professional_WEB_ordinary_code_successor'
ORD_SCHEMA='professional-external-WEB-ordinary-code-successor/v1'
OPS={'git_push','pull_request','official_ci','merge'}
def need(ok,msg):a.require(ok,'adopted WEB increment: '+msg)
def same(root,p,q):
    return isinstance(p,dict)and isinstance(q,dict)and p.get('sha256')==q.get('sha256')and p.get('size')==q.get('size')and w.safe_path(root,p['path'])==w.safe_path(root,q['path'])
def metadata_only(text0,text1,titles,base):
    marker='const binding = '
    need(text0.count(marker)==text1.count(marker)==1,'one structured target metadata binding')
    i0=text0.index(marker)+len(marker);i1=text1.index(marker)+len(marker);obj0,end0=json.JSONDecoder().raw_decode(text0[i0:]);obj1,end1=json.JSONDecoder().raw_decode(text1[i1:])
    need(text0[:i0]==text1[:i1]and text0[i0+end0:]==text1[i1+end1:],'publisher/target implementation outside metadata remains byte-identical')
    from urllib.parse import urlparse
    bypath={urlparse(x['URL']).path:x for x in titles};expected=deepcopy(obj0)
    for row in expected.get('publicPaths',[]):
        p=bypath.get(row.get('path'));need(p and row.get('strictMetadataTitle')is True and row.get('expected')==p.get('old_expected')and p.get('new_expected')==p.get('actual_complete_title')and p.get('new_expected')!=p.get('old_expected'),'actual accepted source-derived complete title; strict comparison remains true')
        row['expected']=p['new_expected']
    need(0<len(expected.get('publicPaths',[]))==len(titles) and expected==obj1
      and obj1.get('taskId')==base['task']and obj1.get('actionId')==base['registered_CMS']['action']['action_id']
      and obj1.get('changedFields')==base['registered_CMS']['action']['changed_fields']and obj1.get('scope')==base['registered_CMS']['action']['scope'],'only exact expected-title fields change; CMS tuple/strict checks do not')

def validate(root,base,item):
    import professional_web_execution as web
    import goal_delivery_runtime as g
    import goal_source_recovery as recovery
    need(item.get('schema')==SCHEMA and item.get('task_id')==base['task']and item.get('original_source_registration')==base['registration'],'original immutable WEB source/task')
    data=a.document(root,item.get('owner_input'));adopt_pin=data.get('C1_actual_adoption');adopt=a.document(root,adopt_pin);result_pin=data.get('actual_complete_WEB_result');result=a.document(root,result_pin);version=result.get('actual_local_version',{})
    need(data.get('task_id')==adopt.get('task_id')==result.get('task_id')==base['task']and data.get('scope')==adopt.get('scope')==result.get('scope')==base['scope']
      and data.get('primary_owner')==adopt.get('department')==base['owner']and adopt.get('original_executor')==result.get('department')==base['role']
      and same(root,adopt.get('original_human_authorization'),base['authorization'])and same(root,adopt.get('original_HQ_bounded_decision'),base['decision'])
      and same(root,result.get('C1_adoption'),adopt_pin),'real same-task owner adoption, original authority/decision and executor')
    snap=g.restore_goal(root,w.read_json(w.snapshot_path(root,base['task'])));records=[a.document(root,p)for p in snap['goal_delivery'].get('collaboration_records',[])]
    selected=[r for r in records if r.get('action_id')==result.get('received_action_id')and r.get('status')=='result_received'and same(root,r.get('result'),result_pin)]
    states=[s for s in g._collaboration_wait_states(root,snap)if s.get('action_id')==result.get('received_action_id')and s.get('department')==base['role']and s.get('status')=='result_received'and s.get('proof_state')=='PROVEN']
    need(len(selected)==len(states)==1,'actual original WEB receive/ACK/completed result relation')
    recovery.collaboration_queue_source(root,snap,selected[0]);request=a.document(root,selected[0]['original_prepare_request']);body=w.safe_path(root,request['payload']['path']).read_text()
    need(adopt_pin['sha256']in body and adopt_pin['path']in body and request.get('sender_department')==base['owner']and request.get('target_department')==base['role'],'actual prepared/sent original owner adoption source, no caller labels')
    # Read original output bytes and later real completed metadata separately;
    # never turn the earlier inProgress snapshot into completed.
    original=web._external_bytes(result['first_party_native']['document'],base['binding'])
    custody=w.safe_path(root,item['original_WEB_native_custody']['path']);need(w.file_digest(root,item['original_WEB_native_custody']['path'])==item['original_WEB_native_custody']and w.validation_bytes(custody)==original,'unmodified original WEB native bytes, no rewritten completion')
    old=g._native_document(root,item['original_WEB_native_custody']);completed=g._native_document(root,data['actual_completed_WEB_native']);binding=base['binding']
    for page in (old,completed):need(all(page.get('thread',{}).get(k)==binding[v]for k,v in {'id':'thread_id','title':'title','cwd':'cwd'}.items()),'actual fixed external WEB/native context')
    output={};last_turn=None
    for name in ('local_commit','Git_GitHub_facts'):
        cmd=result['first_party_native']['command_ids'][name];before=[(t,m)for t in old.get('turns',[])for m in t.get('items',[])if m.get('id')==cmd];after=[(t,m)for t in completed.get('turns',[])for m in t.get('items',[])if m.get('id')==cmd]
        need(len(before)==len(after)==1,'one genuine original command and later completed observation');t,m=before[0];ct,cm=after[0];last_turn=ct
        need(ct.get('status')=='completed'and not ct.get('error')and t.get('id')==ct.get('id')and not t.get('error')
          and all(m.get(k)==cm.get(k)for k in ('id','type','status','exitCode','cwd','command'))and m.get('type')=='commandExecution'and m.get('status')=='completed'and m.get('exitCode')==0
          and Path(m.get('cwd','')).resolve()==Path(version.get('worktree','')).resolve(),'real successful command in adopted worktree; completed status never invented')
        output[name]=w._completion_execution_output(m)
    selected=adopt['selected_local_version'];need(version.get('worktree')==selected['worktree']and version.get('branch')==selected['branch']and version.get('parent')==selected['base']and version.get('tree')==selected['candidate_tree'],'owner selected exact new context/tree/base')
    need(Path(version['worktree']).resolve().is_relative_to(Path(base['site']).resolve()/'.worktrees')and Path(version['worktree']).resolve()!=Path(base['worktree']).resolve(),'real isolated original website worktree, not moved into old context')
    ctx={**base,'worktree':version['worktree'],'branch':version['branch'],'commit':version['commit'],'base':version['parent'],'tree':version['tree']}
    need(web.git(ctx,'show','-s','--format=%H %P %T',ctx['commit']).decode().strip()==' '.join([ctx['commit'],ctx['base'],ctx['tree']])
      and web.git(ctx,'merge-base',base['commit'],ctx['base']).decode().strip()==base['commit'],'real commit/tree/parent and original production ancestry')
    need(web.git(ctx,'rev-parse','--git-common-dir')==web.git(base,'rev-parse','--git-common-dir'),'same actual repository, no substitute worktree project')
    approved={x['path']:x for x in selected['selected_source_files']};files={x['path']:x for x in version['files']};paths=set(web.git(ctx,'diff','--name-only',ctx['base'],ctx['commit']).decode().splitlines())
    production=[p for p in paths if '.test.'not in p];tests=[p for p in paths if '.test.'in p]
    need(paths==set(approved)==set(files)and len(production)==len(tests)==1 and paths<=set(base['paths'])and production[0].startswith('scripts/managed-cms-targets-'),'exact adopted metadata target and its related existing test only')
    for path in paths:
        raw=web.git(ctx,'show',ctx['commit']+':'+path);prior=web.git(ctx,'show',ctx['base']+':'+path)
        need(hashlib.sha256(raw).hexdigest()==files[path]['sha256']==approved[path]['candidate']['sha256']and len(raw)==files[path]['size']
          and web._external_bytes(approved[path]['candidate'],binding)==raw and web._external_bytes(approved[path]['base'],binding)==prior
          and web.git(ctx,'rev-parse',ctx['commit']+':'+path).decode().strip()==files[path]['git_blob'],'actual adopted before/after source and blob identities')
    for key,oldkey,left,right in [('forward_patch','exact_forward_patch',ctx['base'],ctx['commit']),('inverse_patch','exact_inverse_patch',ctx['commit'],ctx['base'])]:
        raw=web._external_bytes(version[key],binding);need(version[key]==selected[oldkey]and raw==web.git(ctx,'diff','--no-ext-diff',left,right),'exact forward/inverse source patch, not production rollback')
    metadata_only(web.git(ctx,'show',ctx['base']+':'+production[0]).decode(),web.git(ctx,'show',ctx['commit']+':'+production[0]).decode(),a.document(root,adopt['necessary_C1_selfcheck']).get('same_response_old_false_candidate_true',[]),base)
    facts=json.loads(output['Git_GitHub_facts']).get('state');need(facts==result.get('current_observed_GitHub_state')and facts['candidate_commit']==ctx['commit']and facts['candidate_base']==ctx['base']and facts['branch']==ctx['branch']
      and facts['repository']==base['repository']and facts['repository_id']==1248188229 and facts['actor']['login']==base['repository'].split('/')[0]and type(facts['actor']['id'])is int and facts['actor']['id']>0,'actual successful original Git/GitHub identity facts')
    need(all(str(version[k]).encode()in output['local_commit']for k in ('commit','parent','tree'))and all(x['sha256'].encode()in output['local_commit']for x in files.values()),'real command binds actual source objects')
    when=w._parse_observed_at(adopt['decided_at_MYT']);observed=w._parse_observed_at(facts['observed_at']);need(when and observed and when.timestamp()<=last_turn['startedAt']<=observed.timestamp()<=last_turn['completedAt'],'real adoption -> WEB command -> completed chronology')
    return {**ctx,'paths':{p:files[p]['sha256']for p in paths},'adopted_increment':item,'increment_actor_id':facts['actor']['id'],'increment_source_mode':'metadata_expectations_only','increment_allowed_operations':sorted(OPS),'increment_forward_patch':version['forward_patch'],'increment_inverse_patch':version['inverse_patch']}
def ci_paths_only(before,after,paths):
    """Accept list entries in the PR paths block, preserving every other byte."""
    need(paths and len(paths)==len(set(paths)),'unique adopted PR trigger paths')
    lines=after.splitlines(keepends=True);start=lines.index('    paths:\n') if lines.count('    paths:\n')==1 else -1
    need(start>=0 and 'on:\n' in lines[:start] and '  pull_request:\n' in lines[:start],'unambiguous original PR paths section')
    stop=start+1
    while stop<len(lines) and lines[stop].startswith('      '):stop+=1
    additions={'      - '+p+'\n' for p in paths}
    need(all(lines[start+1:stop].count(line)==1 for line in additions),'each adopted path occurs once in original PR paths')
    prior=''.join(line for i,line in enumerate(lines)if not(start<i<stop and line in additions))
    need(prior==before,'only adopted PR trigger entries change; jobs/Node/permissions/CMS bytes preserved')
def patch_hunks(raw):
    return b'\n'.join(re.sub(rb'^(@@.*?@@).*',rb'\1',line)for line in raw.splitlines()if not line.startswith((b'diff --git ',b'index ')))
def validate_ci(root,base,parent,item):
    import professional_web_execution as web,goal_delivery_runtime as g,goal_source_recovery as recovery
    need(item.get('schema')==CI_SCHEMA and item.get('task_id')==base['task']and item.get('original_source_registration')==base['registration']
         and same(root,item.get('parent_increment_source'),parent.get('increment_registration')),'actual immutable parent source and original task')
    data=a.document(root,item.get('owner_input'));adopt_pin=data.get('business_adoption');adopt=a.document(root,adopt_pin)
    early_pin=adopt.get('original_exact_CI_adoption');early=a.document(root,early_pin);result_pin=data.get('actual_local_successor_result');result=a.document(root,result_pin);version=result.get('actual_local_version',{})
    need(all(d.get('task_id')==base['task']and d.get('scope')==base['scope']for d in (data,adopt,early,result))
         and data.get('primary_owner')==adopt.get('department')==early.get('department')==base['owner']and result.get('department')==base['role']
         and same(root,adopt.get('actual_complete_WEB_result'),result_pin)and same(root,result.get('C1_adoption'),early_pin)
         and same(root,adopt.get('actual_WEB_completed_native'),data.get('actual_local_successor_native'))
         and version==adopt.get('selected_local_version')==data.get('real_version_and_patches'),'original owner selection, exact same result/native/version and scope')
    snap=g.restore_goal(root,w.read_json(w.snapshot_path(root,base['task'])));records=[a.document(root,p)for p in snap['goal_delivery'].get('collaboration_records',[])]
    matched=[r for r in records if r.get('action_id')==result.get('received_action_id')and r.get('status')=='result_received'and same(root,r.get('result'),result_pin)]
    states=[s for s in g._collaboration_wait_states(root,snap)if s.get('action_id')==result.get('received_action_id')and s.get('department')==base['role']and s.get('status')=='result_received'and s.get('proof_state')=='PROVEN']
    need(len(matched)==len(states)==1,'actual original owner-to-WEB receive/ACK/completed result')
    recovery.collaboration_queue_source(root,snap,matched[0]);req=a.document(root,matched[0]['original_prepare_request']);body=w.safe_path(root,req['payload']['path']).read_text()
    need(req.get('sender_department')==base['owner']and req.get('target_department')==base['role']and early_pin['path']in body and early_pin['sha256']in body,'real prepared/policy/queue source for selected change')
    original=web._external_bytes(result['first_party_native']['document'],base['binding']);custody=item.get('original_WEB_native_custody')
    need(w.file_digest(root,custody['path'])==custody and w.validation_bytes(w.safe_path(root,custody['path']))==original,'unaltered original output; no rewritten native completion')
    old=g._native_document(root,custody);completed=g._native_document(root,data['actual_local_successor_native']);out={};turn=None
    for page in (old,completed):need(all(page.get('thread',{}).get(k)==base['binding'][v]for k,v in {'id':'thread_id','title':'title','cwd':'cwd'}.items()),'original external WEB fixed native identity')
    for name,command in result['first_party_native']['commands'].items():
        p=[(t,m)for t in old.get('turns',[])for m in t.get('items',[])if m.get('id')==command];q=[(t,m)for t in completed.get('turns',[])for m in t.get('items',[])if m.get('id')==command]
        need(len(p)==len(q)==1,'one real original command and completed observation');t,m=p[0];turn,cm=q[0]
        need(turn.get('status')=='completed'and not turn.get('error')and not t.get('error')and t.get('id')==turn.get('id')
             and all(m.get(k)==cm.get(k)for k in ('id','type','status','exitCode','cwd','command'))
             and m.get('type')=='commandExecution'and m.get('status')=='completed'and m.get('exitCode')==0
             and Path(m.get('cwd','')).resolve()==Path(parent['worktree']).resolve(),'real successful original worktree commands, not fabricated status')
        out[name]=w._completion_execution_output(m)
    need({'local_commit','post_commit_remote_facts'}<=set(out),'actual commit and remote facts commands')
    committed=[json.loads(line)for line in out['local_commit'].decode().splitlines()if line.startswith('{')]
    need(len(committed)==1 and all(version.get(k)==v for k,v in committed[0].items()),'real command binds full selected version and patch pins')
    ctx={**parent,'commit':version['commit'],'git_parent':version['parent'],'base':version['cumulative_base'],'tree':version['tree']}
    need(version.get('head')==ctx['commit']and version.get('branch')==parent['branch']and version.get('worktree')==parent['worktree']
         and ctx['git_parent']==parent['commit']and ctx['base']==parent['base']and ctx['commit']!=ctx['git_parent']
         and web.git(ctx,'show','-s','--format=%H %P %T',ctx['commit']).decode().strip()==' '.join([ctx['commit'],ctx['git_parent'],ctx['tree']])
         and web.git(ctx,'merge-base',ctx['base'],ctx['git_parent']).decode().strip()==ctx['base'],'real linear parent distinct from cumulative integration base; original branch/worktree')
    selected=early['only_selected_change'];delta=adopt['adopted_only_delta'];path=selected['path'];paths=selected['add_exact_paths']
    need(path.startswith('.github/workflows/')and path.endswith('.yml')and selected['section']==delta.get('section')=='on.pull_request.paths'
         and delta.get('file')==path and paths==delta.get('added_exact_paths')and set(paths)==set(parent['paths'])
         and set(web.git(ctx,'diff','--name-only',ctx['git_parent'],ctx['commit']).decode().splitlines())=={path}
         and set(web.git(ctx,'diff','--name-only',ctx['base'],ctx['commit']).decode().splitlines())==set(parent['paths'])|{path},'exact adopted CI trigger increment and cumulative source set')
    before=web.git(ctx,'show',ctx['git_parent']+':'+path);after=web.git(ctx,'show',ctx['commit']+':'+path)
    need(hashlib.sha256(before).hexdigest()==selected['base_sha256']and hashlib.sha256(after).hexdigest()==selected['candidate_sha256']
         and web._external_bytes(delta['backup_original_workflow'],base['binding'])==before
         and web._external_bytes(delta['backup_successor_workflow'],base['binding'])==after,'actual selected workflow before/after bytes')
    ci_paths_only(before.decode(),after.decode(),paths)
    files={r['path']:r for r in version['files']};need(set(files)==set(parent['paths'])|{path},'exact cumulative blob manifest')
    for p,f in files.items():
        raw=web.git(ctx,'show',ctx['commit']+':'+p)
        need(hashlib.sha256(raw).hexdigest()==f['sha256']and len(raw)==f['size']and web.git(ctx,'rev-parse',ctx['commit']+':'+p).decode().strip()==f['git_blob'],'actual full Git blobs and hashes')
        if p in parent['paths']:need(f['sha256']==parent['paths'][p],'adopted target/test bytes preserved')
    patches=version['patches'];pairs=[(ctx['git_parent'],ctx['commit']),(ctx['commit'],ctx['git_parent']),(ctx['base'],ctx['commit']),(ctx['commit'],ctx['base'])]
    need(len(patches)==len(pairs),'exact incremental/cumulative forward/reverse patches')
    for pin,(left,right)in zip(patches.values(),pairs):need(web._external_bytes(pin,base['binding'])==web.git(ctx,'diff','--no-ext-diff',left,right),'real forward/reverse Git patch bytes')
    for key,sha,canonical in [('applied_original592_patch','forward_sha256',list(patches.values())[0]),('original592_inverse','inverse_sha256',list(patches.values())[1])]:
        pin=delta[key];need(pin['sha256']==selected[sha]and patch_hunks(web._external_bytes(pin,base['binding']))==patch_hunks(web._external_bytes(canonical,base['binding'])),'adopted patch hunks equal canonical patch; original representations retained')
    facts=json.loads(out['post_commit_remote_facts']);observed=result['current_remote_observation'];pr=facts['PR']
    need(pr==observed.get('PR')and facts['actual_local_head']==ctx['commit']and facts['actual_remote_branch_head']==pr['headRefOid']==ctx['git_parent']
         and facts['actual_remote_main']==pr['baseRefOid']==ctx['base']and pr['headRefName']==ctx['branch']and pr['baseRefName']=='main'
         and type(pr.get('number'))is int and pr['number']>0 and pr['state']=='OPEN'and pr.get('mergedAt')is None
         and pr['url']=='https://github.com/'+ctx['repository']+'/pull/'+str(pr['number']),'actual existing original PR, remote main and branch; no future platform facts')
    at=w._parse_observed_at(early['decided_at_MYT']);observed_at=w._parse_observed_at(facts['observed_at']);adopted_at=w._parse_observed_at(adopt['decided_at_MYT'])
    need(at and observed_at and adopted_at and at.timestamp()<=turn['startedAt']<=observed_at.timestamp()<=turn['completedAt']<=adopted_at.timestamp(),'real owner selection -> WEB execution/completion -> exact version adoption')
    return {**ctx,'paths':{p:f['sha256']for p,f in files.items()},'adopted_increment':item,'increment_source_mode':'CI_paths_only','increment_allowed_operations':sorted(OPS),
            'existing_pull_number':pr['number'],'increment_forward_patch':list(patches.values())[2],'increment_inverse_patch':list(patches.values())[3]}
def optional_string_only(before,after):
    """An indexed optional string passed to includes gets an empty fallback only."""
    left=before.splitlines(keepends=True);right=after.splitlines(keepends=True)
    need(len(left)==len(right),'one line type compatibility, no structural change')
    changed=[i for i,(x,y)in enumerate(zip(left,right))if x!=y]
    need(len(changed)==1,'one exact optional-string line')
    index=changed[0];old=left[index];new=right[index]
    matches=list(re.finditer(r"\.includes\((?P<value>[A-Za-z_$][\w$]*\[(?:0|[1-9]\d*)\])\)",old))
    accepted=[m for m in matches for empty in ("''",'""')if old[:m.end('value')]+" ?? "+empty+old[m.end('value'):]==new]
    need(len(accepted)==1,'only empty-string fallback in existing includes; no behavior/permission replacement')
    return index+1

def ordinary_native(root,base,item,command):
    import professional_web_execution as web,goal_delivery_runtime as g
    old=g._native_document(root,item['original_native_custody']);fresh=g._native_document(root,item['actual_completed_native'])
    for page in (old,fresh):
        need(all(page.get('thread',{}).get(k)==base['binding'][v]for k,v in {'id':'thread_id','title':'title','cwd':'cwd'}.items()),'actual fixed original WEB native identity')
    left=[(t,m)for t in old.get('turns',[])for m in t.get('items',[])if m.get('id')==command]
    right=[(t,m)for t in fresh.get('turns',[])for m in t.get('items',[])if m.get('id')==command]
    need(len(left)==len(right)==1,'one actual original command and later completion')
    t,m=left[0];ct,cm=right[0]
    need(t.get('id')==ct.get('id')and not t.get('error')and ct.get('status')=='completed'and not ct.get('error')
         and all(m.get(k)==cm.get(k)for k in ('id','type','status','exitCode','cwd','command'))
         and m.get('type')=='commandExecution'and m.get('status')=='completed'and m.get('exitCode')==0
         and Path(m.get('cwd','')).resolve().is_relative_to(Path(base['binding']['cwd']).resolve())
         and any(x.get('type')=='agentMessage'and x.get('phase')=='final_answer'and x.get('text','').strip()for x in ct.get('items',[])),
         'real successful WEB command and completed final, never rewrite old native')
    need(type(ct.get('startedAt'))in {int,float}and type(ct.get('completedAt'))in {int,float}
         and ct['startedAt']<=ct['completedAt']<=dt.datetime.now(dt.timezone.utc).timestamp(),'real native completion chronology')
    return w._completion_execution_output(m)

def validate_ordinary(root,base,item):
    import professional_web_execution as web
    need(base.get('code_only_release')and item.get('schema')==ORD_SCHEMA and item.get('task_id')==base['task']
         and item.get('scope')==base['scope']and item.get('original_source_registration')==base['registration'],
         'original authenticated code-release task/scope/source only')
    data=web.code_document(root,item['source_bundle']);typed=web.external(root,item['typed_candidate'],base['binding'])
    versions=data.get('versions',[]);reported=json.loads(ordinary_native(root,base,item,item['source_command']))
    need(reported==versions and isinstance(reported,list),'actual original WEB output binds whole immutable version source')
    rows=[x for x in versions if web._external_bytes(x['typed'],base['binding'])==web._external_bytes(item['typed_candidate'],base['binding'])]
    need(len(rows)==1 and typed.get('task_id')==base['task']and typed.get('original_selected_source_commit')==base['commit']
         and typed.get('worktree')==base['worktree']and typed.get('branch')==base['branch'],'one exact typed candidate, original task/worktree/branch')
    row=rows[0];ctx={**base,'commit':typed['head'],'git_parent':typed['parent'],'base':typed['base'],'tree':typed['tree']}
    need(all(row.get(k)==typed.get(k)for k in ('head','base','tree','forward','inverse'))
         and web.git(ctx,'show','-s','--format=%H %P %T',ctx['commit']).decode().strip()==' '.join([ctx['commit'],ctx['git_parent'],ctx['tree']])
         and ctx['commit']!=ctx['git_parent'],'actual linear successor Git head/parent/tree')
    # The parent must still be the already authorized source on its real later base.
    web.candidate(base,{'candidate_commit':ctx['git_parent'],'candidate_base':ctx['base']})
    files=typed.get('files',[]);paths={x['path']:x['sha256']for x in files}
    actual=set(web.git(ctx,'diff','--name-only',ctx['base'],ctx['commit']).decode().splitlines())
    delta=set(web.git(ctx,'diff','--name-only',ctx['git_parent'],ctx['commit']).decode().splitlines())
    need(len(paths)==len(files)==row.get('files')and actual==set(paths)and len(delta)==1,'complete exact cumulative files and single compatibility path')
    for x in files:
        raw=web.git(ctx,'show',ctx['commit']+':'+x['path'])
        present=bool(web.git(ctx,'ls-tree',ctx['base'],'--',x['path']).strip())
        before_ok=web._external_bytes(x['before'],base['binding'])==web.git(ctx,'show',ctx['base']+':'+x['path'])if present else x.get('before')is None
        need(hashlib.sha256(raw).hexdigest()==x['sha256']and len(raw)==x['size']and web.git(ctx,'rev-parse',ctx['commit']+':'+x['path']).decode().strip()==x['blob']
             and web._external_bytes(x['candidate'],base['binding'])==raw
             and before_ok,'actual whole Git blob SHA/size/identity and source backup')
    for key,left,right in [('forward',ctx['base'],ctx['commit']),('inverse',ctx['commit'],ctx['base'])]:
        need(web._external_bytes(typed[key],base['binding'])==web.git(ctx,'diff','--no-ext-diff','--binary','--full-index',left,right),'exact source-only forward/reverse bytes')
    path=next(iter(delta));before=web.git(ctx,'show',ctx['git_parent']+':'+path).decode();after=web.git(ctx,'show',ctx['commit']+':'+path).decode()
    need(web.git(ctx,'ls-tree',ctx['git_parent'],'--',path).split()[0]==web.git(ctx,'ls-tree',ctx['commit'],'--',path).split()[0],'existing source mode preserved')
    kind=item.get('kind')
    if kind=='optional_string_type_compatibility':
        need(path in base['paths']and set(paths)==set(base['paths']),'only original owned source path')
        line=optional_string_only(before,after)
        facts=web.code_document(root,item['actual_failed_CI']);observed=json.loads(ordinary_native(root,base,item,item['CI_facts_command']))
        need(observed==facts and facts.get('PR',{}).get('head')==ctx['git_parent']and facts['PR'].get('base')==ctx['base']
             and facts['PR'].get('state')=='open'and facts['PR'].get('merged')is False,'actual existing original failed-CI PR, not proposed or merged')
        runs=[x for x in facts.get('runs',[])if x.get('path')==web.CODE_CI_PATHS['interaction-standards']and x.get('head_sha')==ctx['git_parent']and x.get('status')=='completed'and x.get('conclusion')=='failure'and x.get('event')=='pull_request']
        need(len(runs)==1,'real exact original official strict CI failure')
        error=web.code_document(root,item['failure_excerpt']);checks=web.code_document(root,item['successful_checks'])
        need(error.get('head')==checks.get('failure_head')==ctx['git_parent']and error.get('run_id')==checks.get('failed_run')==runs[0]['id']
             and error.get('job_id')==checks.get('failed_check')and error.get('PR')==facts['PR']['number']
             and any(re.search(re.escape(path)+r'\('+str(line)+r',\d+\): error TS2345:',s)and "'string | undefined'"in s and "'string'"in s for s in error.get('lines',[])), 'real failure path/line/type and run/job association')
        check_rows=checks.get('checks',[]);out=ordinary_native(root,base,item,item['checks_command']).decode()
        actual_checks=[json.loads(s)for s in out.splitlines()if s.startswith('{')]
        need(actual_checks==check_rows and len(check_rows)>=2 and all(x.get('exit')==0 for x in check_rows)
             and any(x.get('argv')==['npm','run','typecheck:strict-core']for x in check_rows)
             and any(x.get('argv')==['npm','test','--',str(Path(path).with_suffix('.test.ts'))]for x in check_rows), 'actual successful strict-core and affected test commands')
        ctx['existing_pull_number']=facts['PR']['number']
    elif kind=='original_PR_trigger_paths':
        need(path==web.CODE_CI_PATHS['r3-managed-cms-pr-checks']and path not in base['paths']and set(paths)==set(base['paths'])|{path},'existing required workflow and original production paths only')
        ci_paths_only(before,after,sorted(base['paths']))
        import fnmatch
        entries=[s.strip()[2:].strip("'\"")for s in before.split('    paths:\n',1)[1].splitlines()if s.startswith('      - ')]
        need(all(not any(fnmatch.fnmatchcase(p,x)for x in entries)for p in base['paths']),'real preexisting PR path coverage gap')
        gap=web.code_document(root,item['actual_trigger_gap']);out=json.loads(ordinary_native(root,base,item,item['gap_command']))
        rows=[{'path':p,'matches':[]}for p in base['paths']]
        need(gap.get('head')==ctx['git_parent']and gap.get('workflow')==path and gap.get('actual_original3_paths')==rows
             and gap.get('proposed_exact3_additions')==list(base['paths'])and out.get('result')=='PASS_CONFIG_GAP_PROOF'and out.get('rows')==rows,'actual config-derived gap proof, no invented failed run')
    else:need(False,'known narrowly validated ordinary code difference required')
    for p,sha in base['paths'].items():
        if p!=path:need(paths[p]==sha,'all unchanged original production/test blobs preserved')
        need(web.git(ctx,'ls-tree',ctx['commit'],'--',p).split()[0]==web.git(ctx,'ls-tree',base['commit'],'--',p).split()[0],'original owned source file modes preserved')
    return {**ctx,'paths':paths,'ordinary_increment':True,'increment_actor_id':base['actor_id'],
            'increment_allowed_operations':base['allowed_operations'],'increment_source_mode':kind,
            'increment_forward_patch':typed['forward'],'increment_inverse_patch':typed['inverse']}

def _validate_item(root,base,item,values):
    if item.get('schema')==ORD_SCHEMA:return validate_ordinary(root,base,item),ORD_EVENT
    if item.get('schema')==SCHEMA:return validate(root,base,item),EVENT
    need(item.get('schema')==CI_SCHEMA,'known original adopted source schema')
    parents=[v for v in values if same(root,v.get('increment_registration'),item.get('parent_increment_source'))]
    need(len(parents)==1,'one previously registered immutable parent increment')
    return validate_ci(root,base,parents[0],item),CI_EVENT
def sources(root,base):
    keys=(EVENT,CI_EVENT,ORD_EVENT)
    rows=[e for e in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS)if e.get('task_id')==base['task']and any(e.get('details',{}).get(k)for k in keys)]
    values=[];seen=set()
    for e in rows:
        pins=[e['details'][k]for k in keys if e['details'].get(k)];need(len(pins)==1,'one source per event');pin=pins[0]
        value,event=_validate_item(root,base,a.document(root,pin),values);need(e['details'].get(event)==pin and value['commit']not in seen,'ambiguous adopted increment');seen.add(value['commit']);values.append({**value,'increment_registration':pin,'increment_event_id':e['event_id']})
    return values
def select(root,base,state):
    import professional_web_execution as web
    values=sources(root,base);matches=[x for x in values if x['commit']==state.get('candidate_commit')]
    if not matches:
        for ctx in values:
            if not ctx.get('ordinary_increment'):continue
            try:web.candidate(ctx,state)
            except w.WorkflowError:continue
            matches.append(ctx)
    need(len(matches)<=1,'one exact adopted source context');return matches[0]if matches else base
def record(root,task,path):
    import professional_web_execution as web,goal_delivery_runtime as g
    pin=w.file_digest(root,path);base=web.records(root,task)[0];item=a.document(root,pin)
    with w.workflow_lock(root):
        values=sources(root,base);ctx,event_key=_validate_item(root,base,item,values);prior=[x for x in values if x['commit']==ctx['commit']]
        if prior:need(prior[0]['increment_registration']==pin,'immutable increment already recorded');return {'result':'duplicate_ignored','source':pin,'event_id':prior[0]['increment_event_id'],'permission_issued':False}
        s=g.restore_goal(root,w.read_json(w.snapshot_path(root,task)));need(s['current_state']not in w.TERMINAL_STATES or event_key==ORD_EVENT and s['current_state']=='closed'and base.get('code_only_release'),'closed task needs its existing real owner-authorized code follow-on source');event=w.append_workflow_event(root,task,s['current_state'],{event_key:pin})
    return {'result':'recorded','source':pin,'event_id':event['event_id'],'permission_issued':False,'old_source_or_producers_changed':False}
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('command',choices=['record']);p.add_argument('--task-id',required=True);p.add_argument('--input',required=True);args=p.parse_args();root=Path(__file__).resolve().parents[1]
    try:
        with w.request_validation_context():result=record(root,args.task_id,args.input)
        print(json.dumps(result,ensure_ascii=False,indent=2))
    except (w.WorkflowError,ValueError,KeyError,OSError)as e:p.exit(1,str(e)+'\n')
