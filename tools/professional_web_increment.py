"""Authenticated owner-adopted metadata expectations; no platform operation."""
from pathlib import Path
from copy import deepcopy
import argparse,datetime as dt,hashlib,json,re
import workflow_control as w
import department_autonomy as a
EVENT='professional_WEB_adopted_metadata_increment'
SCHEMA='professional-external-WEB-adopted-metadata-increment/v1'
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
def sources(root,base):
    rows=[e for e in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS)if e.get('task_id')==base['task']and e.get('details',{}).get(EVENT)]
    values=[];seen=set()
    for e in rows:
        pin=e['details'][EVENT];value=validate(root,base,a.document(root,pin));need(value['commit']not in seen,'ambiguous adopted increment');seen.add(value['commit']);values.append({**value,'increment_registration':pin,'increment_event_id':e['event_id']})
    return values
def select(root,base,state):
    matches=[x for x in sources(root,base)if x['commit']==state.get('candidate_commit')]
    need(len(matches)<=1,'one exact adopted source context');return matches[0]if matches else base
def record(root,task,path):
    import professional_web_execution as web,goal_delivery_runtime as g
    pin=w.file_digest(root,path);base=web.records(root,task)[0];item=a.document(root,pin)
    with w.workflow_lock(root):
        ctx=validate(root,base,item);prior=[x for x in sources(root,base)if x['commit']==ctx['commit']]
        if prior:need(prior[0]['increment_registration']==pin,'immutable increment already recorded');return {'result':'duplicate_ignored','source':pin,'event_id':prior[0]['increment_event_id'],'permission_issued':False}
        s=g.restore_goal(root,w.read_json(w.snapshot_path(root,task)));need(s['current_state']not in w.TERMINAL_STATES,'closed task cannot add a new execution source');event=w.append_workflow_event(root,task,s['current_state'],{EVENT:pin})
    return {'result':'recorded','source':pin,'event_id':event['event_id'],'permission_issued':False,'old_source_or_producers_changed':False}
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('command',choices=['record']);p.add_argument('--task-id',required=True);p.add_argument('--input',required=True);args=p.parse_args();root=Path(__file__).resolve().parents[1]
    try:
        with w.request_validation_context():result=record(root,args.task_id,args.input)
        print(json.dumps(result,ensure_ascii=False,indent=2))
    except (w.WorkflowError,ValueError,KeyError,OSError)as e:p.exit(1,str(e)+'\n')
