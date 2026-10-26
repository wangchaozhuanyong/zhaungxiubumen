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

def test_assertions_only(before,after):
    """Retain each assertion/call; only strengthen its exact string expectation."""
    left=before.splitlines(keepends=True);right=after.splitlines(keepends=True)
    need(len(left)==len(right),'same complete test structure, no removed/skipped case')
    changed=[(a,b)for a,b in zip(left,right)if a!=b];need(changed,'actual assertion delta required')
    literal=r'"(?:[^"\\]|\\.)*"'
    for old,new in changed:
        m=re.fullmatch(r'(\s*expect\(.+\)\.(toBe|toHaveAttribute)\()(.*)(\);\s*)',old)
        n=re.fullmatch(r'(\s*expect\(.+\)\.(toBe|toHaveAttribute)\()(.*)(\);\s*)',new)
        need(m and n and m[1]==n[1]and m[4]==n[4],'same actual subject and strict assertion, no weakening/replacement')
        if m[2]=='toHaveAttribute':
            x=re.fullmatch('('+literal+r'),\s*('+literal+')',m[3]);y=re.fullmatch('('+literal+r'),\s*('+literal+')',n[3])
            need(x and y and x[1]==y[1]and json.loads(x[1])=='href','same exact href assertion')
            need(json.loads(y[2]).startswith(json.loads(x[2])+'?text='),'same safe destination with source query only')
        else:
            need(re.fullmatch(literal,m[3]),'original exact string expectation')
            expected=json.loads(m[3]);ternary=re.fullmatch(r'[A-Za-z_$][\w$]*\s*===\s*'+literal+r'\s*\?\s*('+literal+r')\s*:\s*('+literal+')',n[3])
            values=[json.loads(n[3])]if re.fullmatch(literal,n[3])else [json.loads(ternary[1]),json.loads(ternary[2])]if ternary else []
            need(values and all(v.startswith(expected+'\n\n')and len(v)>len(expected)+2 for v in values),'retain enquiry plus exact appended localized reference; no broad matcher')
    return len(changed)

def validate_related_tests(root,base,parent,item):
    import professional_web_execution as web
    need(base.get('code_only_release')and parent.get('ordinary_increment')and item.get('task_id')==base['task']and item.get('scope')==base['scope']
         and item.get('original_source_registration')==base['registration']and same(root,item.get('parent_increment_source'),parent['increment_registration']), 'actual registered ordinary parent and same original authority/task/scope')
    data=web.code_document(root,item['source_bundle']);typed=web.external(root,data['candidate'],base['binding'])
    output=json.loads(ordinary_native(root,base,item,item['source_command']))
    need(data.get('task_id')==typed.get('task_id')==base['task']and data.get('scope')==typed.get('scope')==base['scope']
         and data.get('original_HQ_decision_sha256')==base['decision']['sha256']and output.get('receipt')=={'path':data['candidate']['path'],'sha256':data['candidate']['sha256'],'bytes':data['candidate']['size']}, 'real original complete WEB source binds exact candidate bytes')
    ctx={**parent,'commit':typed['head'],'git_parent':typed['candidate_parent'],'base':typed['candidate_base'],'tree':typed['tree']}
    need(ctx['git_parent']==parent['commit']and ctx['base']==parent['base']and typed['worktree']==base['worktree']and typed['branch']==base['branch']
         and all(data.get(k)==ctx[v]for k,v in {'head':'commit','parent':'git_parent','integration_base':'base','tree':'tree','worktree':'worktree','branch':'branch'}.items())
         and all(output.get(k)==ctx[v]for k,v in {'head':'commit','parent':'git_parent','base':'base','tree':'tree'}.items())
         and web.git(ctx,'show','-s','--format=%H %P %T',ctx['commit']).decode().strip()==' '.join([ctx['commit'],ctx['git_parent'],ctx['tree']]), 'real linear head/parent/tree, same integration base/worktree/branch')
    need(data['test_blobs']==typed['test_blobs']and data['original_16_blobs']==typed['original_16_blobs'],'whole original/test source maps agree with actual typed receipt')
    paths=set(web.git(ctx,'diff','--name-only',ctx['git_parent'],ctx['commit']).decode().splitlines());need(paths==set(data['increment_paths'])==set(typed['increment_paths'])
         and paths and paths.isdisjoint(parent['paths'])and all(re.fullmatch(r'src/[\w/.-]+\.test\.tsx?',p)for p in paths),'only exact new related existing test paths, never production/CI/config')
    changed=0
    for path in paths:
        before=web.git(ctx,'show',ctx['git_parent']+':'+path);after=web.git(ctx,'show',ctx['commit']+':'+path)
        changed+=test_assertions_only(before.decode(),after.decode())
        need(web.git(ctx,'ls-tree',ctx['git_parent'],'--',path).split()[0]==web.git(ctx,'ls-tree',ctx['commit'],'--',path).split()[0],'test mode unchanged')
        rows=[x for x in data['test_blobs']if x['path']==path];need(len(rows)==1,'one exact test blob source');x=rows[0]
        for key,head,raw in [('parent',ctx['git_parent'],before),('head',ctx['commit'],after)]:need(x[key+'_sha256']==hashlib.sha256(raw).hexdigest()and x[key+'_blob']==web.git(ctx,'rev-parse',head+':'+path).decode().strip(),'actual before/after test bytes')
    facts=json.loads(ordinary_native(root,base,item,item['CI_facts_command']));runs=[x for x in facts.get('runs',[])if x.get('path')==web.CODE_CI_PATHS['interaction-standards']and x.get('head_sha')==parent['commit']and x.get('conclusion')=='failure'and x.get('status')=='completed']
    failure=web.code_document(root,item['actual_failure']);text=re.sub(r'\x1b\[[0-9;]*m','',failure.get('excerpt',''));failed=set(re.findall(r'FAIL\s+([^\s]+\.test\.tsx?)',text))
    need(len(runs)==1 and failure.get('head')==parent['commit']and failure.get('run')==typed.get('old_failed_official_run_preserved')==runs[0]['id']
         and failure.get('PR')==facts['PR']['number']==parent['existing_pull_number']and facts['PR']['head']==parent['commit']and failed==paths
         and any(x.get('id')==failure.get('job')and x.get('head_sha')==parent['commit']and x.get('name')=='interaction-standards'and x.get('conclusion')=='failure'for x in facts.get('checks',[])),
         'real official predecessor failure belongs to exactly these test files/PR, not a future green result')
    checks=typed.get('checks',[]);need(len(checks)==2 and all(x.get('exit_code')==0 for x in checks),'real affected checks succeed')
    import goal_delivery_runtime as g,shlex
    page=g._native_document(root,item['actual_completed_native']);readback=ordinary_native(root,base,item,item['checks_readback_command'])
    for index,command in enumerate([item['test_command'],item['lint_command']]):
        pairs=[(t,m)for t in page['turns']for m in t['items']if m.get('id')==command];need(len(pairs)==1,'one real affected test/lint execution')
        turn,cmd=pairs[0];shell=shlex.split(cmd.get('command',''));expected=shlex.split(checks[index]['command'])
        need(turn.get('status')=='completed'and not turn.get('error')and cmd.get('type')=='commandExecution'and cmd.get('status')=='completed'and cmd.get('exitCode')==0
             and shell[:2]==['/bin/zsh','-lc']and len(shell)==3 and shlex.split(shell[2])==expected+['>',checks[index]['path'],'2>&1']
             and set(expected[(3 if index==0 else 2):])==paths and expected[:(3 if index==0 else 2)]==(['npm','test','--']if index==0 else ['npx','eslint'])
             and Path(cmd['cwd']).resolve()==Path(ctx['worktree']).resolve(),'actual exact redirected check command; no ignored failure or alternate test scope')
    for x in checks:
        raw=web._external_bytes({'path':x['path'],'sha256':x['sha256'],'size':x['bytes']},base['binding'])
        if x.get('tests_passed'):need(raw in readback and re.search(rb'Tests\s+'+str(x['tests_passed']).encode()+rb' passed',raw),'actual passing test count/log and native output')
    artifacts=data['source_patches'];need(artifacts==typed['artifacts']==output['patches']and len(artifacts)==4,'exact immutable incremental and cumulative reverse sources')
    for pin,(left,right)in zip(artifacts,[(ctx['git_parent'],ctx['commit']),(ctx['commit'],ctx['git_parent']),(ctx['base'],ctx['commit']),(ctx['commit'],ctx['base'])]):
        need(web._external_bytes({'path':pin['path'],'sha256':pin['sha256'],'size':pin['bytes']},base['binding'])==web.git(ctx,'diff','--no-ext-diff','--binary','--full-index',left,right),'actual exact forward/inverse patch')
    need(set(typed['cumulative_paths'])==set(parent['paths'])|paths==set(web.git(ctx,'diff','--name-only',ctx['base'],ctx['commit']).decode().splitlines()),'cumulative original source plus exact test delta only')
    oldfiles=data['original_16_blobs'];need({x['path']for x in oldfiles}==set(parent['paths']),'complete original source map')
    for x in oldfiles:
        path=x['path'];need(x['parent_blob']==x['head_blob']==web.git(ctx,'rev-parse',ctx['commit']+':'+path).decode().strip()
           and hashlib.sha256(web.git(ctx,'show',ctx['commit']+':'+path)).hexdigest()==parent['paths'][path],'original production/source bytes unchanged')
    return {**ctx,'paths':{**parent['paths'],**{x:hashlib.sha256(web.git(ctx,'show',ctx['commit']+':'+x)).hexdigest()for x in paths}},'increment_source_mode':'related_test_assertions','related_assertion_line_count':changed}

def fixture_isolation_only(before,after):
    """Keep every scenario byte; align one SUT import with reset and cleanup."""
    marker='\ndescribe(';need(before.count(marker)==after.count(marker)==1,'one complete original scenario suite')
    prefix,scenarios=before.split(marker,1);new_prefix,new_scenarios=after.split(marker,1)
    count=len(re.findall(r'(?m)^\s*it\(',scenarios));need(scenarios==new_scenarios and count>0,'every original test body/assertion/timeout remains byte-identical')
    imports=list(re.finditer(r'(?m)^import ([A-Za-z_$][\w$]*) from "(\./[\w/-]+)";\n',prefix))
    need(len(imports)==1,'one original relative SUT import');match=imports[0];name,module=match[1],match[2]
    roots=list(re.finditer(r'(?m)^let ([A-Za-z_$][\w$]*): Root;\n',prefix));need(len(roots)==1,'one original React test root');root=roots[0][1]
    mocks=[line for line in prefix.splitlines(True)if 'vi.doMock('in line];need(len(mocks)==1 and prefix.count('beforeEach(() => {')==1,'original mock and module-reset fixture')
    teardown=re.search(r'(?m)^afterEach\(async \(\) => \{ await act\(async \(\) => '+re.escape(root)+r'\.unmount\(\)\); (.+) \}\);\n',prefix)
    need(teardown is not None and 'vi.resetModules();'in prefix,'original per-case module reset and teardown')
    replacement=('afterEach(async () => {\n  await act(async () => { '+root+'.unmount(); await vi.dynamicImportSettled(); });\n  '+teardown[1]+'\n});\n')
    expected=prefix.replace(match[0],'',1).replace(roots[0][0],'let '+name+': typeof import("'+module+'").default;\n'+roots[0][0],1)
    expected=expected.replace('beforeEach(() => {','beforeEach(async () => {',1).replace(mocks[0],mocks[0]+'  '+name+' = (await import("'+module+'")).default;\n',1).replace(teardown[0],replacement,1)
    need(expected==new_prefix,'only reset-aligned SUT import and awaited unmount/import settling; all other fixture bytes exact')
    return count

def validate_fixture_successor(root,base,parent,item):
    import professional_web_execution as web,goal_delivery_runtime as g,shlex
    need(base.get('code_only_release')and parent.get('ordinary_increment')and item.get('task_id')==base['task']and item.get('scope')==base['scope']
         and item.get('original_source_registration')==base['registration']and same(root,item.get('parent_increment_source'),parent['increment_registration']),'same original source/task/scope and actual registered parent')
    page=g._native_document(root,item['actual_completed_native'])
    for command in (item['source_command'],item['CI_facts_command'],item['full_test_readback_command']):
        current=[m for turn in page.get('turns',[])for m in turn.get('items',[])if m.get('id')==command]
        need(len(current)==1 and w._completion_execution_output(current[0])==ordinary_native(root,base,item,command),'both original and actual completed native outputs must be complete and byte-identical')
    data=web.code_document(root,item['source_bundle']);typed=web.external(root,data['candidate'],base['binding']);output=json.loads(ordinary_native(root,base,item,item['source_command']))
    need(output.get('candidate')==data['candidate']and output.get('checks')==typed.get('local_checks')and data.get('task_id')==typed.get('task_id')==base['task']
         and data.get('scope')==typed.get('scope')==base['scope']and data.get('business_owner')==base['owner']and data.get('executor')==base['role']
         and data.get('original_HQ_decision_sha256')==base['decision']['sha256'],'real completed WEB binds the exact typed fixture source and original authority')
    ctx={**parent,'commit':typed['head'],'git_parent':typed['candidate_parent'],'base':typed['candidate_base'],'tree':typed['tree']}
    need(ctx['git_parent']==parent['commit']and ctx['base']==parent['base']and typed['branch']==base['branch']and typed['worktree']==base['worktree']
         and all(data.get(k)==ctx[v]and output.get('base'if k=='integration_base'else k)==ctx[v]for k,v in {'head':'commit','parent':'git_parent','integration_base':'base','tree':'tree'}.items())
         and web.git(ctx,'show','-s','--format=%H %P %T',ctx['commit']).decode().strip()==' '.join([ctx['commit'],ctx['git_parent'],ctx['tree']]),'actual linear head/parent/tree and original worktree/branch/base')
    path=data.get('increment_path');need(path==typed.get('increment_path')and re.fullmatch(r'src/[\w/.-]+\.test\.tsx?',str(path))
         and path not in parent['paths']and set(web.git(ctx,'diff','--name-only',ctx['git_parent'],ctx['commit']).decode().splitlines())=={path},'one exact existing related test only')
    before=web.git(ctx,'show',ctx['git_parent']+':'+path);after=web.git(ctx,'show',ctx['commit']+':'+path);count=fixture_isolation_only(before.decode(),after.decode())
    blob=data['test_blob'];need(blob==typed['test_blob']and blob['before_sha256']==hashlib.sha256(before).hexdigest()and blob['after_sha256']==hashlib.sha256(after).hexdigest()
         and blob['before']==web.git(ctx,'rev-parse',ctx['git_parent']+':'+path).decode().strip()and blob['after']==web.git(ctx,'rev-parse',ctx['commit']+':'+path).decode().strip()
         and web.git(ctx,'ls-tree',ctx['git_parent'],'--',path).split()[0]==web.git(ctx,'ls-tree',ctx['commit'],'--',path).split()[0],'actual exact before/after blob, mode and content hashes')
    unchanged=data['unchanged_18_blobs'];need(unchanged==typed['original18_blobs']and {x['path']for x in unchanged}==set(parent['paths']),'complete original parent source set')
    for x in unchanged:
        need(x['parent_blob']==x['head_blob']==web.git(ctx,'rev-parse',ctx['commit']+':'+x['path']).decode().strip()
             and hashlib.sha256(web.git(ctx,'show',ctx['commit']+':'+x['path'])).hexdigest()==parent['paths'][x['path']],'all prior production and source/test bytes unchanged')
    artifacts=data['source_patches'];need(artifacts==typed['source_patches']and output['increment_source_patches']==artifacts[:2]and len(artifacts)==4,'exact original incremental/cumulative recovery sources')
    for pin,(left,right)in zip(artifacts,[(ctx['git_parent'],ctx['commit']),(ctx['commit'],ctx['git_parent']),(ctx['base'],ctx['commit']),(ctx['commit'],ctx['base'])]):
        need(web._external_bytes(pin,base['binding'])==web.git(ctx,'diff','--no-ext-diff','--binary','--full-index',left,right),'exact Git forward/reverse bytes')
    facts=json.loads(ordinary_native(root,base,item,item['CI_facts_command']));runs=[x for x in facts.get('runs',[])if x.get('path')==web.CODE_CI_PATHS['interaction-standards']and x.get('head_sha')==parent['commit']and x.get('status')=='completed'and x.get('conclusion')=='failure']
    failure=web.code_document(root,item['actual_failure'])
    need(len(runs)==1 and failure.get('head')==facts['PR']['head']==parent['commit']and failure.get('run')==runs[0]['id']
         and facts['PR']['number']==parent['existing_pull_number']and path in failure.get('filtered_error_and_surrounding_lines','')
         and any(x.get('id')==failure.get('job')and x.get('head_sha')==parent['commit']and x.get('conclusion')=='failure'for x in facts.get('checks',[])),'actual official parent failure for this test and existing PR')
    scenario=web.external(root,data['all_four_scenarios_unchanged'],base['binding'])
    need(scenario.get('path')==path and scenario.get('before_sha256')==blob['before_sha256']and scenario.get('candidate_sha256')==blob['after_sha256']and scenario.get('scenario_count')==count,'independently recomputed complete scenario relation')
    logs=typed['local_checks']['evidence'];page=g._native_document(root,item['actual_completed_native'])
    for log in logs:web._external_bytes(log,base['binding'])
    full=next(x for x in logs if 'FULL-SUITE'in x['path']);lint=next(x for x in logs if 'LINT'in x['path'])
    for command,expected in [(item['full_test_command'],['npm','test','>',full['path'],'2>&1']),(item['lint_command'],['npx','eslint',path,'>',lint['path'],'2>&1'])]:
        pairs=[(t,m)for t in page['turns']for m in t['items']if m.get('id')==command];need(len(pairs)==1,'one actual test/lint execution');turn,cmd=pairs[0];shell=shlex.split(cmd.get('command',''))
        need(turn.get('status')=='completed'and not turn.get('error')and cmd.get('type')=='commandExecution'and cmd.get('status')=='completed'and cmd.get('exitCode')==0
             and shell[:2]==['/bin/zsh','-lc']and len(shell)==3 and shlex.split(shell[2])==expected and Path(cmd.get('cwd','')).resolve()==Path(ctx['worktree']).resolve(),'real successful check with no ignored failure; local Node version never proves official new-head CI')
    readback=ordinary_native(root,base,item,item['full_test_readback_command']);total=typed['local_checks']['full_tests_passed']
    need(re.search(rb'Tests\s+'+str(total).encode()+rb' passed',readback)and re.search(rb'Tests\s+'+str(total).encode()+rb' passed',web._external_bytes(full,base['binding'])),'real complete local passing log/readback')
    need(set(typed['cumulative_paths'])==set(parent['paths'])|{path}==set(web.git(ctx,'diff','--name-only',ctx['base'],ctx['commit']).decode().splitlines()),'original full source plus exact fixture path only')
    return {**ctx,'paths':{**parent['paths'],path:hashlib.sha256(after).hexdigest()},'increment_source_mode':'related_test_fixture_isolation','unchanged_scenario_count':count}

COLD_SEMANTICS_READER="// Trusted parser only: no eval, transpilation, app imports or source execution.\nconst fs=require('node:fs'),path=require('node:path').posix,crypto=require('node:crypto');\nconst ts=require(process.argv[2]||process.argv[1]),input=JSON.parse(fs.readFileSync(0,'utf8'));\nconst need=(v,m)=>{if(!v)throw Error(m)},sha=s=>crypto.createHash('sha256').update(s).digest('hex');\nfunction parse(files){const result={};for(const [file,text]of Object.entries(files)){if(text===null)continue;const sf=ts.createSourceFile(file,text,ts.ScriptTarget.Latest,true);need(!sf.parseDiagnostics.length,'valid original TypeScript');const decl={},other=[],imports=[];for(const n of sf.statements){if(ts.isImportDeclaration(n)){imports.push(n);continue}if(ts.isVariableStatement(n)){for(const d of n.declarationList.declarations){need(ts.isIdentifier(d.name),'no new destructuring declaration');need(!decl[d.name.text],'unique top declaration');decl[d.name.text]={node:d,raw:d.getText(sf),stmt:n,kind:'variable',flags:n.declarationList.flags,type:d.type?.getText(sf)||'',exported:!!n.modifiers?.some(m=>m.kind===ts.SyntaxKind.ExportKeyword)}}}else if((ts.isFunctionDeclaration(n)||ts.isTypeAliasDeclaration(n)||ts.isInterfaceDeclaration(n)||ts.isClassDeclaration(n)||ts.isEnumDeclaration(n))&&n.name){decl[n.name.text]={node:n,raw:n.getText(sf),stmt:n,kind:String(n.kind),flags:0,type:'',exported:!!n.modifiers?.some(m=>m.kind===ts.SyntaxKind.ExportKeyword)}}else other.push(n.getText(sf))}result[file]={sf,text,decl,other,imports}}return result}\nlet B=parse(input.before),A=parse(input.after);const all=new Set([...Object.keys(B),...Object.keys(A)]);\nfunction moduleFile(file,module){if(!module.startsWith('.')&&!module.startsWith('@/'))return 'external:'+module;let p=module.startsWith('@/')?'src/'+module.slice(2):path.normalize(path.join(path.dirname(file),module));return [p,p+'.ts',p+'.tsx',p+'/index.ts',p+'/index.tsx'].find(x=>all.has(x))||p.replace(/\\.(?:tsx?)$/,'')}\nfunction bindings(tree,file){const m={};for(const n of tree[file]?.imports||[]){const mod=moduleFile(file,n.moduleSpecifier.text);if(!n.importClause){m['!'+mod]={mod,exported:'!',type:false};continue}let c=n.importClause;if(c.name)m[c.name.text]={mod,exported:'default',type:!!c.isTypeOnly};if(c.namedBindings){if(ts.isNamespaceImport(c.namedBindings))m[c.namedBindings.name.text]={mod,exported:'*',type:!!c.isTypeOnly};else for(const e of c.namedBindings.elements)m[e.name.text]={mod,exported:(e.propertyName||e.name).text,type:!!c.isTypeOnly||!!e.isTypeOnly}}}return m}\nconst BI=Object.fromEntries(Object.keys(B).map(f=>[f,bindings(B,f)])),AI=Object.fromEntries(Object.keys(A).map(f=>[f,bindings(A,f)]));\nconst ident=(f,n)=>f+'#'+n,plain=r=>r.raw.replace(/^export\\s+/,''),sameDecl=(l,r)=>l&&r&&l.kind===r.kind&&l.flags===r.flags&&l.type===r.type&&plain(l)===plain(r);\nfunction constant(tree,im,file,node,seen=new Set()){need(node,'constant exists');if(ts.isAsExpression(node)||ts.isParenthesizedExpression(node)||ts.isTypeAssertionExpression(node))return constant(tree,im,file,node.expression,seen);if(ts.isStringLiteral(node)||ts.isNumericLiteral(node))return ts.isStringLiteral(node)?node.text:Number(node.text);if(node.kind===ts.SyntaxKind.TrueKeyword)return true;if(node.kind===ts.SyntaxKind.FalseKeyword)return false;if(node.kind===ts.SyntaxKind.NullKeyword)return null;if(ts.isObjectLiteralExpression(node)){const out={};for(const p of node.properties){need(ts.isPropertyAssignment(p)&& (ts.isIdentifier(p.name)||ts.isStringLiteral(p.name)),'plain dictionary property only');const name=p.name.text;need(!['__proto__','prototype','constructor'].includes(name)&&!Object.hasOwn(out,name),'no prototype or duplicate dictionary key');out[name]=constant(tree,im,file,p.initializer,new Set(seen))}return out}if(ts.isIdentifier(node)){const key=ident(file,node.text);need(!seen.has(key),'no circular dictionary');seen.add(key);const local=tree[file]?.decl[node.text];if(local?.kind==='variable')return constant(tree,im,file,local.node.initializer,seen);const b=im[file]?.[node.text];need(b&&b.exported!=='*','constant binding');return constant(tree,im,b.mod,tree[b.mod]?.decl[b.exported]?.node.initializer,seen)}if(ts.isPropertyAccessExpression(node)){const object=constant(tree,im,file,node.expression,seen);need(object&&Object.hasOwn(object,node.name.text),'real dictionary reference');return object[node.name.text]}throw Error('not a non-executable plain constant')}\nconst leaves=new Map(),origin=new Map();\nfor(const [f,x]of Object.entries(A))for(const [name,row]of Object.entries(x.decl)){const exact=[];for(const [bf,bx]of Object.entries(B)){const old=bx.decl[name];if(sameDecl(old,row))exact.push([bf,old])}if(exact.length){const preferred=exact.find(([bf])=>bf===f)|| (exact.length===1?exact[0]:null);need(preferred,'unambiguous original declaration origin');origin.set(ident(f,name),ident(preferred[0],name));continue}if(B[f]?.decl[name])continue;need(row.kind==='variable'&&row.flags===ts.NodeFlags.Const,'only copied declarations or new constant projection');let val;try{val=constant(A,AI,f,row.node.initializer)}catch{throw Error('new code is not an original constant projection')}need(val&&typeof val==='object'&&!Array.isArray(val)&&Object.keys(val).length&&Object.values(val).every(v=>typeof v==='string'),'new loading leaf is string dictionary only');const matches=[];for(const [bf,bx]of Object.entries(B))for(const [bn,br]of Object.entries(bx.decl)){try{const old=constant(B,BI,bf,br.node.initializer);for(const key of Object.keys(old?.[Object.keys(val)[0]]||{}))if(Object.keys(old).length===Object.keys(val).length&&Object.keys(val).every(lang=>old[lang]?.[key]===val[lang]))matches.push({file:bf,name:bn,property:key,value:val})}catch{}}need(matches.length===1,'unique literal-preserving loading projection');leaves.set(ident(f,name),matches[0]);origin.set(ident(f,name),'projection:'+ident(matches[0].file,matches[0].name)+'.'+matches[0].property)}\nfunction oldOrigin(b){return ident(b.mod,b.exported)}\nfunction newOrigin(b){return origin.get(ident(b.mod,b.exported))||ident(b.mod,b.exported)}\n// Normalize only binding-proven namespace calls and equivalent dictionary leaf access.\nconst normalized={},namespaceMigrations={};\nfor(const [file,b]of Object.entries(B)){const namespaces={};function scan(n){if(ts.isVariableDeclaration(n)&&ts.isIdentifier(n.name)){let v=n.initializer;if(v&&ts.isAwaitExpression(v))v=v.expression;if(v&&ts.isCallExpression(v)&&v.expression.kind===ts.SyntaxKind.ImportKeyword&&v.arguments.length===1&&ts.isStringLiteral(v.arguments[0])){const mod=moduleFile(file,v.arguments[0].text);namespaces[n.name.text]??=new Set();namespaces[n.name.text].add(mod)}}ts.forEachChild(n,scan)}scan(b.sf);const edits=[];function walk(n){if(ts.isPropertyAccessExpression(n)&&ts.isIdentifier(n.expression)&&namespaces[n.expression.text]?.size===1){const mod=[...namespaces[n.expression.text]][0],target=ident(mod,n.name.text);const named=Object.entries(AI[file]||{}).filter(([local,imp])=>local===imp.exported&&newOrigin(imp)===target);if(named.length===1&&origin.has(ident(named[0][1].mod,named[0][1].exported))){const original=B[mod]?.decl[n.name.text];let hasThis=false;if(original){function check(x){if(x.kind===ts.SyntaxKind.ThisKeyword)hasThis=true;ts.forEachChild(x,check)}check(original.node)}need(original&&!hasThis,'namespace migration retains no this binding');namespaceMigrations[file]??=new Set();namespaceMigrations[file].add(target);edits.push([n.getStart(b.sf),n.end,named[0][0]])}}if(ts.isPropertyAccessExpression(n)&&ts.isElementAccessExpression(n.expression)&&ts.isIdentifier(n.expression.expression)){const old=BI[file]?.[n.expression.expression.text];if(old){const matches=Object.entries(AI[file]||{}).filter(([name,imp])=>{const leaf=leaves.get(ident(imp.mod,imp.exported));return leaf&&leaf.file===old.mod&&leaf.name===old.exported&&leaf.property===n.name.text});if(matches.length===1)edits.push([n.getStart(b.sf),n.end,matches[0][0]+'['+n.expression.argumentExpression.getText(b.sf)+']'])}}ts.forEachChild(n,walk)}walk(b.sf);let text=b.text;for(const [start,end,value]of edits.sort((a,b)=>b[0]-a[0]))text=text.slice(0,start)+value+text.slice(end);normalized[file]=text}\nconst N=parse(normalized);let copied=0,projected=0;\nfor(const [file,x]of Object.entries(A)){need(JSON.stringify(x.other)===JSON.stringify(N[file]?.other||[]),'test bodies/top-level effects unchanged');for(const [name,row]of Object.entries(x.decl)){const id=ident(file,name);if(origin.has(id)){const old=origin.get(id);if(!old.startsWith('projection:')){const [f,n]=old.split('#'),original=B[f].decl[n];if(f===file)need(original.exported===row.exported,'unchanged existing export boundary');if(f!==file){need(row.kind!=='variable'||row.flags===ts.NodeFlags.Const,'no copied mutable state');if(row.kind==='variable'&&A[f]?.decl[n])need(ts.isArrowFunction(row.node.initializer)||ts.isFunctionExpression(row.node.initializer)||ts.isStringLiteral(row.node.initializer)||ts.isNumericLiteral(row.node.initializer),'no duplicate stateful initializer');copied++}need(sameDecl(original,row),'exact original declaration');}else projected++;continue}const before=N[file]?.decl[name];need(before&&before.kind===row.kind&&before.flags===row.flags&&before.type===row.type&&before.exported===row.exported,'no unrelated declaration');if(sameDecl(before,row)){origin.set(id,id);continue}need(row.kind==='variable'&&row.flags===ts.NodeFlags.Const,'runtime declaration changed');const left=constant(B,BI,file,B[file].decl[name].node.initializer),right=constant(A,AI,file,row.node.initializer);need(JSON.stringify(left)===JSON.stringify(right),'complete dictionary values/order unchanged');origin.set(id,id)}}\nfor(const [f,x]of Object.entries(B))for(const [name,row]of Object.entries(x.decl)){need([...origin.values()].includes(ident(f,name)),'no original declaration dropped')}\nfor(const [file,x]of Object.entries(A)){const origins=new Set();for(const name of Object.keys(x.decl)){const id=origin.get(ident(file,name));if(id&&!id.startsWith('projection:'))origins.add(id.split('#')[0])}if(B[file])origins.add(file);const allowed=new Set();for(const f of origins){for(const [n,b]of Object.entries(BI[f]||{}))allowed.add(oldOrigin(b));for(const n of Object.keys(B[f]?.decl||{}))allowed.add(ident(f,n))}for(const [local,b]of Object.entries(AI[file]||{})){const old=BI[file]?.[local];if(old&&JSON.stringify(old)===JSON.stringify(b))continue;need(b.exported!=='default'&&b.exported!=='*'&&!local.startsWith('!')&&local===b.exported,'no new side effect/alias/namespace import');const source=newOrigin(b);const leaf=leaves.get(ident(b.mod,b.exported));need(allowed.has(source)||namespaceMigrations[file]?.has(source)||(leaf&&(origins.has(leaf.file)||Object.values(BI[file]||{}).some(x=>x.mod===leaf.file&&x.exported===leaf.name))),'import must resolve original '+file+' '+local+' '+source+' allowed '+[...allowed].join(','));let used=false;function walk(n){if(ts.isIdentifier(n)&&n.text===local)used=true;ts.forEachChild(n,walk)}for(const n of x.sf.statements)if(!ts.isImportDeclaration(n))walk(n);need(used,'no extra unused import')}}\nfunction testBody(x){let text=x.text;for(const n of [...x.imports].reverse())text=text.slice(0,n.getStart(x.sf))+text.slice(n.end);return text.split('\\n').filter(x=>x.trim()).join('\\n')}\nlet expects=0;for(const file of Object.keys(A).filter(f=>/\\.test\\.tsx?$/.test(f))){need(testBody(N[file])===testBody(A[file]),'complete test setup/scenarios/assertions/comments unchanged');function count(sf){let n=0;function walk(x){if(ts.isCallExpression(x)&&/^expect\\(/.test(x.getText(sf)))n++;ts.forEachChild(x,walk)}walk(sf);return n}need(count(B[file].sf)===count(A[file].sf),'all expect calls retained');expects+=count(A[file].sf)}\nfor(const d of input.proof.declarations){const l=B[d.before_file]?.decl[d.name],r=A[d.after_file]?.decl[d.name];need(l&&r&&l.raw===r.raw&&sha(l.raw)===d.sha256,'actual exact declaration proof, not a caller boolean')}\nlet gzipTotal=0;if(input.build){const zlib=require('node:zlib');for(const r of input.build.files){const b=fs.readFileSync(r.path);need(b.length===r.bytes&&sha(b)===r.sha256&&zlib.gzipSync(b).length===r.gzip,'actual unchanged build asset bytes/gzip');gzipTotal+=r.gzip}need(gzipTotal===input.build.total&&gzipTotal<=input.build.budget,'unchanged initial JS budget')}\nprocess.stdout.write(JSON.stringify({initial_js_gzip_bytes:gzipTotal,declarations:input.proof.declarations.length,unchanged_expect_calls:expects,copied_declarations:copied,loading_projections:projected,all_changed_files_semantically_bounded:true}));\n"

def cold_source_semantics(before,after,proof,compiler,build=None):
    """Static AST and byte reader only; never evaluate/transpile application input."""
    import subprocess,shutil,json
    node=shutil.which('node')
    if not node:
        fallback=Path.home()/'.local/bin/node'
        node=str(fallback)if fallback.is_file()else None
    need(node,'existing Node runtime for the existing project TypeScript parser; never install a dependency')
    value={'before':before,'after':after,'proof':proof,'build':build}
    result=subprocess.run([node,'-e',COLD_SEMANTICS_READER,str(compiler)],input=json.dumps(value),capture_output=True,text=True,timeout=30)
    need(result.returncode==0,'bounded cold-module AST relation rejected: '+result.stderr[-1800:])
    return json.loads(result.stdout)

def validate_cold_boundary(root,base,parent,item):
    import professional_web_execution as web,goal_delivery_runtime as g
    need(base.get('code_only_release')and parent.get('ordinary_increment')and item.get('task_id')==base['task']
         and item.get('scope')==base['scope']and item.get('original_source_registration')==base['registration']
         and same(root,item.get('parent_increment_source'),parent['increment_registration']),'same original bounded owner/task/scope and registered causal parent')
    data=web.code_document(root,item['source_bundle']);typed=web.external(root,data['candidate'],base['binding']);page=g._native_document(root,item['actual_completed_native'])
    def actual(command):
        value=ordinary_native(root,base,item,command);commands=[m for t in page.get('turns',[])for m in t.get('items',[])if m.get('id')==command]
        need(len(commands)==1 and w._completion_execution_output(commands[0])==value,'complete matching original and completed native output')
        return value
    output=json.loads(actual(item['source_command']))
    need(output.get('candidate')==data['candidate']and data.get('task_id')==typed.get('task_id')==base['task']
         and data.get('scope')==typed.get('scope')==base['scope']and data.get('business_owner')==base['owner']
         and data.get('executor')==base['role']and data.get('original_HQ_decision_sha256')==base['decision']['sha256'],
         'actual complete professional source and original human/HQ owner/executor relation')
    ctx={**parent,'commit':typed['head'],'git_parent':typed['candidate_parent'],'base':typed['candidate_base'],'tree':typed['tree']}
    need(ctx['git_parent']==parent['commit']and ctx['base']==parent['base']and typed['branch']==base['branch']and typed['worktree']==base['worktree']
         and all(data.get(k)==ctx[v]and output.get('base'if k=='integration_base'else k)==ctx[v]for k,v in {'head':'commit','parent':'git_parent','integration_base':'base','tree':'tree'}.items())
         and web.git(ctx,'show','-s','--format=%H %P %T',ctx['commit']).decode().strip()==' '.join([ctx['commit'],ctx['git_parent'],ctx['tree']]),'actual linear Git objects and same original working branch/base')
    files=data['increment_files'];paths={f['path']for f in files}
    need(len(paths)==len(files)and paths==set(data['increment_paths'])==set(typed['increment_paths'])
         and files==typed['increment_files']and paths==set(web.git(ctx,'diff','--name-only',ctx['git_parent'],ctx['commit']).decode().splitlines())
         and all(re.fullmatch(r'src/[\w/.-]+\.tsx?',p)and'..'not in Path(p).parts for p in paths),'only exact original TypeScript source/test causal delta')
    before={};after={}
    for f in files:
        path=f['path'];old=web.git(ctx,'ls-tree',ctx['git_parent'],'--',path).split();new=web.git(ctx,'ls-tree',ctx['commit'],'--',path).split()
        need(new and new[0]==b'100644'and new[2].decode()==f['candidate_blob'],'regular exact candidate blob/mode, no deletion or executable')
        current=web.git(ctx,'show',ctx['commit']+':'+path);need(current==web._external_bytes(f['candidate'],base['binding']),'exact candidate source bytes')
        if old:
            need(old[0]==new[0]and old[2].decode()==f.get('parent_blob')and'before'in f,'exact original before blob/mode')
            original=web.git(ctx,'show',ctx['git_parent']+':'+path);need(original==web._external_bytes(f['before'],base['binding']),'exact original source before bytes');before[path]=original.decode()
        else:
            need(f.get('parent_blob')is None and'before'not in f,'new module has no invented original');before[path]=None
        after[path]=current.decode()
    proof=web.external(root,data['exact_semantic_and_build_proof'],base['binding']);checks=typed['local_checks']
    need(data['exact_semantic_and_build_proof']in checks['evidence']and proof.get('base')==ctx['git_parent'],'exact originally checked semantic source')
    protected=proof['protected_bytes'];need(len({x['path']for x in protected})==len(protected)and protected and not(paths&{x['path']for x in protected}),'all exact protected source/config/lock/limits outside the delta')
    for pin in protected:
        original=web.git(ctx,'show',ctx['git_parent']+':'+pin['path']);current=web.git(ctx,'show',ctx['commit']+':'+pin['path'])
        need(original==current and hashlib.sha256(current).hexdigest()==pin['sha256'],'protected bytes cannot change for performance or new source')
    limits=[x for x in protected if x['path'].endswith('/verify-performance-budget.mjs')]
    need(len(limits)==1,'original unchanged budget implementation')
    budget_code=web.git(ctx,'show',ctx['commit']+':'+limits[0]['path']).decode();unit=re.search(r'const\s+kib\s*=\s*(\d+)',budget_code);limit=re.search(r'initialJsGzip:\s*(\d+)\s*\*\s*kib',budget_code)
    need(unit and limit,'original literal initial-JS budget, no caller override');budget=int(unit[1])*int(limit[1])
    need(proof.get('unchanged_budget')==checks.get('unchanged_budget')==budget and proof.get('initial_js_gzip_bytes')==checks.get('initial_js_gzip_bytes')and type(proof['initial_js_gzip_bytes'])is int and proof['initial_js_gzip_bytes']<=budget,'same original byte budget; local only, no official CI claim')
    directory=Path(item['build_directory']).resolve();need(directory.is_relative_to(Path(base['binding']['cwd']).resolve()),'build evidence stays inside the original project')
    graph=proof['initial_graph'];need(graph and len({v['ref']for v in graph})==len(graph),'one complete immutable original initial graph')
    build=[]
    for asset in graph:
        need(re.fullmatch(r'/assets/[A-Za-z0-9_.-]+\.js',asset['ref']),'exact build JavaScript asset reference')
        path=directory/asset['ref'].lstrip('/');raw=path.read_bytes()
        need(len(raw)==asset['bytes']and hashlib.sha256(raw).hexdigest()==asset['sha256'],'real previously checked local build asset')
        build.append({**asset,'path':str(path)})
    parser=Path(item['parser_source']['path']);canonical=Path(ctx['worktree'])/'node_modules/typescript/lib/typescript.js'
    need(parser.resolve()==canonical.resolve()and canonical.is_file(),'only the original fixed worktree installed TypeScript parser')
    installed=json.loads((canonical.parent.parent/'package.json').read_text());locked=json.loads(web.git(ctx,'show',ctx['commit']+':package-lock.json'))
    need('package-lock.json'in {x['path']for x in protected}and installed.get('name')=='typescript'and installed.get('version')==locked.get('packages',{}).get('node_modules/typescript',{}).get('version'),'unchanged original lock and installed parser identity/version')
    web._external_bytes(item['parser_source'],base['binding'])
    relation=cold_source_semantics(before,after,proof,parser,{'files':build,'total':proof['initial_js_gzip_bytes'],'budget':budget})
    semantic=json.loads(actual(item['semantic_command']))
    need(semantic.get('status')=='PASS'and semantic.get('declarations')==relation['declarations']and semantic.get('unchanged_expect_calls')==relation['unchanged_expect_calls']
         and proof.get('unchanged_expect_calls')==relation['unchanged_expect_calls']and semantic.get('initial_js_gzip_bytes')==relation['initial_js_gzip_bytes']
         and semantic.get('budget')==budget and semantic.get('protected_source_files')==len(protected),'actual native semantic check, recomputed AST and exact build bytes agree')
    logs=checks['evidence']
    for pin in logs:web._external_bytes(pin,base['binding'])
    summary=actual(item['checks_readback_command']);need(re.search(rb'Tests\s+'+str(checks['affected_tests_passed']).encode()+rb' passed',summary)and b'[performance-budget] PASS'in summary,'original successful local test and budget output; never new-head official CI')
    for command in item['checks_commands']:
        pairs=[(t,m)for t in page.get('turns',[])for m in t.get('items',[])if m.get('id')==command]
        need(len(pairs)==1,'one actual original check call');turn,call=pairs[0]
        need(turn.get('status')=='completed'and not turn.get('error')and call.get('type')=='commandExecution'and call.get('status')=='completed'and call.get('exitCode')==0
             and Path(call.get('cwd','')).resolve()==Path(ctx['worktree']).resolve(),'real successful original professional check/cwd/status')
    patches=data['source_patches'];need(patches==typed['source_patches']==output['source_patches']and len(patches)==4,'complete native-bound exact forward/reverse source patches')
    for pin,(left,right)in zip(patches,[(ctx['git_parent'],ctx['commit']),(ctx['commit'],ctx['git_parent']),(ctx['base'],ctx['commit']),(ctx['commit'],ctx['base'])]):
        need(web._external_bytes(pin,base['binding'])==web.git(ctx,'diff','--no-ext-diff','--binary','--full-index',left,right),'exact causal Git patch bytes')
    for path,sha in parent['paths'].items():
        if path not in paths:need(hashlib.sha256(web.git(ctx,'show',ctx['commit']+':'+path)).hexdigest()==sha,'unchanged prior adopted source retained')
    cumulative=set(web.git(ctx,'diff','--name-only',ctx['base'],ctx['commit']).decode().splitlines())
    need(cumulative==set(data['cumulative_paths'])==set(typed['cumulative_paths'])and cumulative<=set(parent['paths'])|paths,'exact complete cumulative scope; no unrelated new path')
    return {**ctx,'paths':{path:hashlib.sha256(web.git(ctx,'show',ctx['commit']+':'+path)).hexdigest()for path in cumulative},'increment_source_mode':'cold_module_boundary_relocation','cold_semantics':relation,'local_budget_headroom_bytes':budget-relation['initial_js_gzip_bytes']}

def _validate_item(root,base,item,values):
    if item.get('schema')==ORD_SCHEMA and item.get('kind')=='cold_module_boundary_relocation':
        parents=[v for v in values if same(root,v.get('increment_registration'),item.get('parent_increment_source'))]
        need(len(parents)==1,'one exact existing ordinary causal parent')
        return validate_cold_boundary(root,base,parents[0],item),ORD_EVENT
    if item.get('schema')==ORD_SCHEMA and item.get('kind')=='related_test_fixture_isolation':
        parents=[v for v in values if same(root,v.get('increment_registration'),item.get('parent_increment_source'))]
        need(len(parents)==1,'one existing exact ordinary parent')
        return validate_fixture_successor(root,base,parents[0],item),ORD_EVENT
    if item.get('schema')==ORD_SCHEMA and item.get('kind')=='related_test_assertions':
        parents=[v for v in values if same(root,v.get('increment_registration'),item.get('parent_increment_source'))]
        need(len(parents)==1,'one real previously registered ordinary successor')
        return validate_related_tests(root,base,parents[0],item),ORD_EVENT
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
