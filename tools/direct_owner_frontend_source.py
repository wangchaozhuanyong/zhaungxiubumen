"""Candidate codec for an actual owner-directed, code-only WEB source.

Source registration supplies no external permit and no execution fact.
"""
from pathlib import Path
import hashlib
import json
import xml.etree.ElementTree as ET
import workflow_control as w
import department_autonomy as a

SCHEMA = 'direct-owner-frontend-WEB-source/v1'
EVENT = 'direct_owner_frontend_WEB_source'

def need(value, reason):
    a.require(value, 'direct frontend WEB source: ' + reason)

def validate(root, snapshot, item):
    import goal_delivery_runtime as g
    import professional_web_execution as web
    from professional_cms_issuer import external
    root = Path(root).resolve()
    need(set(item) == {'schema','task_id','scope','goal_contract','input','report',
                       'HQ_completed_native','WEB_completed_native','owner_completed_native'}
         and item.get('schema') == SCHEMA and item['task_id'] == snapshot['task_id']
         and item['goal_contract'] == snapshot.get('goal_contract'), 'exact source and goal identity')
    goal = a.participant(root, snapshot, snapshot['goal_delivery']['primary_owner'])
    frozen = a.document(root, snapshot['goal_contract'])
    owner = goal['primary_owner']; scope = item['scope']
    need(scope in goal['authorized_scope'] and owner in goal['producer_departments']
         and all(goal.get(k) == frozen.get(k) for k in
                 ('primary_owner','producer_departments','authorized_scope','human_authorization','collaboration_scopes')),
         'unchanged owner, contract, producers and exact scope')
    data = a.document(root,item['input']); report = a.document(root,item['report'])
    need(data.get('schema') == 'exact-direct-owner-frontend-WEB-normal-registration-input/v1'
         and data.get('task_id') == report.get('task_id') == snapshot['task_id']
         and data.get('scope') == report.get('scope') == scope
         and data.get('primary_business_owner') == report.get('owner') == owner
         and data.get('business_producers_unchanged') == goal['producer_departments']
         and report.get('source_registration_input',{}).get('sha256') == item['input']['sha256']
         and report.get('production_READY') is False and data.get('execution_permit') is None,
         'genuine original candidate and result, never a permit')
    role = data['external_technical_executor']['department']; binding = g._collaboration_binding(root,snapshot,role)
    need(binding and role not in goal['producer_departments']
         and {'sender_department':owner,'target_department':role,'scope':scope} in frozen['collaboration_scopes']
         and all(data['external_technical_executor'].get(k) == binding.get(v) for k,v in
                 {'thread_id':'thread_id','project_id':'project_id','project_cwd':'cwd'}.items())
         and binding['project_id'] != a.PROJECT and report.get('executor') == role,
         'original owner/external WEB project binding')
    need(web.code_pin(root,data['actual_human']) == goal['authorization_pin'], 'exact original human source pin')
    human = a.document(root,goal['authorization_pin']); hq = g._native_document(root,item['HQ_completed_native'])
    origin = a.document(root,web.code_pin(root,human['original_full_native_pin']))
    original = origin.get('original_implementation_source',{})
    owner_binding = w.department_registry(root)[owner]['chat_binding']
    need(origin.get('schema') == 'actual-owner-whatsapp-opening-publication-source/v1'
         and origin.get('owner_release',{}).get('message') == human['message']['id']
         and original.get('thread') == owner_binding['task_id']
         and original.get('message') and original.get('turn')
         and origin.get('original_owner_completion',{}).get('turn') == original['turn']
         and origin['original_owner_completion'].get('status') == 'completed; local only before current new publication authorization',
         'actual original professional owner implementation source and completion')
    owner_native=g._native_document(root,item['owner_completed_native'])
    need(all(owner_native.get('thread',{}).get(k)==owner_binding[v] for k,v in
             {'id':'task_id','title':'title','cwd':'cwd','hostId':'host_id'}.items()), 'actual professional owner identity')
    owner_turns=[t for t in owner_native.get('turns',[]) if t.get('id')==original['turn']]
    need(len(owner_turns)==1 and owner_turns[0].get('status')=='completed' and not owner_turns[0].get('error')
         and len([m for m in owner_turns[0].get('items',[]) if m.get('type')=='userMessage'
                  and m.get('id')==original['message'] and m.get('content')==original['exact_text']])==1
         and len([m for m in owner_turns[0].get('items',[]) if m.get('id')==origin['original_owner_completion']['final']
                  and m.get('type')=='agentMessage' and m.get('phase')=='final_answer' and m.get('text','').strip()])==1,
         'actual completed original professional implementation human and final')
    registry = w.department_registry(root); hq_binding = registry['operations']['chat_binding']
    need(all(hq.get('thread',{}).get(k) == hq_binding[v] for k,v in
             {'id':'task_id','title':'title','cwd':'cwd'}.items()), 'actual HQ identity')
    matches = [(t,m) for t in hq.get('turns',[]) for m in t.get('items',[])
               if t.get('id') == human.get('source_turn_id') and m == human.get('message')]
    need(len(matches) == 1 and matches[0][0].get('status') == 'completed'
         and not matches[0][0].get('error') and human.get('source_thread_id') == hq_binding['task_id']
         and matches[0][1].get('type') == 'userMessage'
         and any(x.get('type') == 'text' and x.get('text','').strip() for x in matches[0][1].get('content',[])),
         'actual completed human source, not caller grant')
    decision = web.code_pin(root,data['actual_HQ_exact18_release_scope'])
    selected = a.document(root,decision)
    need(selected.get('task_id') == snapshot['task_id'] and selected.get('professional_owner') == owner
         and selected.get('code_executor') == role and selected.get('business_parent') == goal.get('parent_task_id'),
         'actual HQ scope and original professional parent')
    source_native = g._native_document(root,item['WEB_completed_native'])
    need(all(source_native.get('thread',{}).get(k) == binding[v] for k,v in
             {'id':'thread_id','title':'title','cwd':'cwd','hostId':'host_id'}.items()), 'actual WEB identity')
    witnessed=[]
    for turn in source_native.get('turns',[]):
        if turn.get('status') != 'completed' or turn.get('error'): continue
        echoes=[]; emits=[]; facts=[]
        for x in turn.get('items',[]):
            out=x.get('output',{}); txt=out.get('text','') if isinstance(out,dict) else ''
            if x.get('type') == 'functionCallOutput':
                try: xml=ET.fromstring(txt)
                except ET.ParseError: continue
                body=xml.findtext('input') or ''
                if xml.tag == 'codex_delegation' and xml.findtext('source_thread_id') == hq_binding['task_id'] and all(y in body for y in (scope,snapshot['task_id'],decision['sha256'])): echoes.append(x)
            if x.get('type') == 'commandExecution' and x.get('status') == 'completed' and x.get('exitCode') == 0 and out.get('truncated') is False:
                try: value=json.loads(txt)
                except (ValueError,TypeError): continue
                if value.get('result',{}).get('sha256') == item['report']['sha256'] and value.get('result',{}).get('size') == item['report']['size']: emits.append(x)
                if isinstance(value.get('state'),dict): facts.append(value['state'])
        finals=[x for x in turn.get('items',[]) if x.get('type') == 'agentMessage' and x.get('phase') == 'final_answer' and x.get('text','').strip()]
        if len(echoes)==len(emits)==len(finals)==1 and facts: witnessed.append((turn, facts))
    need(len(witnessed)==1, 'one actual completed WEB delivery and original report command')
    meta=data['selected_actual_candidate']; account=data['actual_repository_actor']; worktree=Path(data['external_technical_executor']['worktree']).resolve()
    need(worktree.is_relative_to(Path(binding['cwd']).resolve()) and str(worktree)==report['worktree']
         and meta['commit']==report['actual_head'] and meta['base']==report['actual_parent']
         and meta['parents']==[meta['base']] and meta['tree']==report['actual_tree']
         and meta['branch']==report['branch'] and selected['base']==meta['base'], 'actual source lineage')
    ctx={'root':str(root),'task':snapshot['task_id'],'scope':scope,'owner':owner,'role':role,'binding':binding,
         'contract':snapshot['goal_contract'],'authorization':goal['authorization_pin'],'decision':decision,
         'worktree':str(worktree),'site':data['external_technical_executor']['git_root'],
         'branch':meta['branch'],'commit':meta['commit'],'base':meta['base'],'tree':meta['tree'],
         'repository':account['repository'],'repository_id':account['repository_id'],'actor_id':account['actor']['id'],
         'code_only_release':True,'direct_owner_frontend_source':True,'allowed_operations':web.CODE_OPS,'pages_scope':scope.split(':',1)[0]+':pages:production',
         'prefix':snapshot['task_id']+'-frontend','backup':data['backup'],'rollback':data['recovery']}
    actual_facts=[v for v in witnessed[0][1] if all(v.get(k)==value for k,value in
                 {'repository':ctx['repository'],'repository_id':ctx['repository_id'],'branch':ctx['branch'],
                  'worktree':ctx['worktree'],'candidate_commit':ctx['commit'],'candidate_base':ctx['base'],
                  'candidate_parent':ctx['base'],'candidate_tree':ctx['tree']}.items()) and v.get('actor')==account['actor']]
    need(len(actual_facts)==1, 'actual original native repository/actor/source observation')
    remote=web.git(ctx,'config','--get','remote.origin.url').decode().strip()
    need(remote in {'https://github.com/'+ctx['repository'], 'https://github.com/'+ctx['repository']+'.git',
                    'user-3de132cd98be@example.invalid:'+ctx['repository']+'.git'}
         and account['actor']['login']==ctx['repository'].split('/')[0]
         and type(ctx['repository_id']) is int and type(ctx['actor_id']) is int
         and ctx['repository_id']>0 and ctx['actor_id']>0, 'actual original repository and actor')
    need(web.git(ctx,'show','-s','--format=%H %P %T',ctx['commit']).decode().strip() == ' '.join([ctx['commit'],ctx['base'],ctx['tree']]), 'real Git commit/parent/tree')
    files=meta['files']; paths={f['path']:f['sha256'] for f in files}; ctx['paths']=paths
    need(files and len(paths)==len(files)==len(selected['source_files']) and set(paths)==set(web.git(ctx,'diff','--name-only',ctx['base'],ctx['commit']).decode().splitlines()), 'complete exact bounded Git paths')
    selected_files={f['path']:f['after_sha256'] for f in selected['source_files']}
    need(paths==selected_files, 'actual HQ selected original file bytes')
    for row in files:
        path=row['path']; need(not Path(path).is_absolute() and '..' not in Path(path).parts, 'safe original path')
        raw=web.git(ctx,'show',ctx['commit']+':'+path); tree=web.git(ctx,'ls-tree',ctx['commit'],'--',path).split()
        need(hashlib.sha256(raw).hexdigest()==row['sha256'] and len(raw)==row['size'] and tree[:3]==[row['mode'].encode(),b'blob',row['blob'].encode()], 'exact Git blob/mode/size')
    actual=web._patch_effect(web._delta(ctx,ctx['base'],ctx['commit']))
    original=web._external_bytes(data['original_exact_patch'],binding)
    recovery=external(root,data['recovery'],binding)
    forward=web._external_bytes(recovery['forward'],binding); reverse=web._external_bytes(recovery['inverse'],binding)
    need(web._patch_effect(web._patch_delta(original))==actual==web._patch_effect(web._patch_delta(forward))
         and web._patch_effect(web._patch_delta(reverse))=={p:(v[1],v[0]) for p,v in actual.items()}, 'actual exact forward and inverse own-source effects')
    need(set(data['requested_normal_operations'])==set(web.CODE_OPS)
         and set(data['forbidden_operations']) >= {'CMS Save','Supabase Functions/R3/Edge','Ads/budget/GA4 settings','DB/auth/account/secret changes'}
         and data.get('production_READY') is False, 'frontend-only scope; excluded platform operations')
    return ctx

def record(root, task, path):
    import goal_delivery_runtime as g
    pin=w.file_digest(root,path); item=a.document(root,pin)
    with w.workflow_lock(root):
        snapshot=g.restore_goal(root,w.read_json(w.snapshot_path(root,task)))
        validate(root,snapshot,item)
        import professional_web_execution as web
        from professional_cms_channel import original_body_records
        need(not original_body_records(root,task) and not [e for e in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS,where={'task_id':task})
             if e.get('task_id')==task and e.get('details',{}).get(web.EVENT)], 'no competing original source registration')
        prior=[e for e in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS,where={'task_id':task})
               if e.get('task_id')==task and e.get('details',{}).get(EVENT)]
        if prior:
            need(len(prior)==1 and prior[0]['details'][EVENT]==pin, 'unique original source; no replacement')
            return {'result':'duplicate_ignored','source':pin,'event_id':prior[0]['event_id'],'permission_issued':False}
        event=w.append_workflow_event(root,task,snapshot['current_state'],{EVENT:pin,'external_permission_issued':False})
    return {'result':'recorded','source':pin,'event_id':event['event_id'],'permission_issued':False,'production_READY':False}
