"""Authenticates one real CI-driven test-only successor, never a permit."""
from pathlib import Path
import difflib,hashlib,io,json,re,tarfile
import workflow_control as w
import department_autonomy as a
SCHEMA='direct-owner-frontend-CI-test-successor/v1'
def need(v,msg):a.require(v,'frontend test successor: '+msg)

def validate(root,base,item):
    import professional_web_execution as web
    import goal_delivery_runtime as g
    root=Path(root).resolve()
    need(set(item)=={'schema','task_id','scope','original_source','input','report','WEB_completed_native','official_results'}
         and item['schema']==SCHEMA and item['task_id']==base['task'] and item['scope']==base['scope']
         and item['original_source']==base['registration'] and base.get('direct_owner_frontend_source'),
         'same authenticated original frontend source, owner and scope')
    source=a.document(root,item['input']);report=a.document(root,item['report']);native=g._native_document(root,item['WEB_completed_native'])
    need(source.get('schema')=='exact-original-frontend-three-test-successor-source-input/v1'
         and source.get('task_id')==report.get('task_id')==base['task'] and source.get('scope')==report.get('scope')==base['scope']
         and source.get('business_owner')==report.get('business_owner')==base['owner']
         and source.get('external_WEB_executor')==report.get('executor')==base['role']
         and source.get('actual_registered_original_source',{}).get('sha256')==base['registration']['sha256']
         and source.get('actual_registered_original_source',{}).get('event')==base['event_id']
         and report.get('source_input',{}).get('sha256')==item['input']['sha256']
         and report.get('new_candidate_not_pushed') is True, 'same original owner/source and genuine new result')
    binding=base['binding'];need(all(native.get('thread',{}).get(k)==binding[v] for k,v in
             {'id':'thread_id','title':'title','cwd':'cwd','hostId':'host_id'}.items()),'original WEB native identity')
    meta=source['actual_new_version']; found=[]
    for t in native.get('turns',[]):
        if t.get('status')!='completed' or t.get('error'):continue
        cmds=[x for x in t.get('items',[]) if x.get('type')=='commandExecution' and x.get('status')=='completed'
              and x.get('exitCode')==0 and x.get('output',{}).get('truncated') is False]
        outputs=[]
        for cmd in cmds:
            try:outputs.append(json.loads(cmd['output']['text']))
            except (ValueError,TypeError,KeyError):pass
        finals=[x for x in t.get('items',[]) if x.get('type')=='agentMessage' and x.get('phase')=='final_answer' and x.get('text','').strip()]
        tests=[x for x in cmds if 'Test Files' in x.get('output',{}).get('text','') and '22 passed' in x['output']['text']
               and all(f['path'] in x.get('command','') for f in meta['increment_files'])]
        if len(finals)==1 and len(tests)==1 and meta in outputs and any(x.get('result',{}).get('sha256')==item['report']['sha256'] for x in outputs if isinstance(x,dict)) and any(x.get('source_input',{}).get('sha256')==item['input']['sha256'] for x in outputs if isinstance(x,dict)):found.append(t)
    need(len(found)==1,'completed original WEB commands bind exact source, report and 22 local tests')
    work=meta['worktree'];ctx={**base,'worktree':work,'branch':meta['branch'],'commit':meta['head'],
          'git_parent':meta['parent'],'base':meta['base'],'tree':meta['tree']}
    need(work==base['worktree'] and meta['branch']==base['branch'] and meta['parent']==base['commit']
         and meta['base']==base['base'] and web.git(ctx,'show','-s','--format=%H %P %T',meta['head']).decode().strip()==' '.join([meta['head'],meta['parent'],meta['tree']]),
         'actual linear parent, base, tree and branch')
    added=meta['increment_files']; paths={x['path'] for x in added}; full={x['path']:x for x in source['all21_blob_modes']}
    need(len(paths)==len(added)>0 and paths.isdisjoint(base['paths'])
         and all(re.fullmatch(r'src/[\w/.-]+\.test\.tsx?',p) for p in paths)
         and paths==set(web.git(ctx,'diff','--name-only',meta['parent'],meta['head']).decode().splitlines())
         and set(full)==set(base['paths'])|paths==set(meta['cumulative_paths'])
         ==set(web.git(ctx,'diff','--name-only',meta['base'],meta['head']).decode().splitlines()), 'only exact new tests and complete cumulative paths')
    for p,row in full.items():
        raw=web.git(ctx,'show',meta['head']+':'+p);tree=web.git(ctx,'ls-tree',meta['head'],'--',p).split()
        need(hashlib.sha256(raw).hexdigest()==row['sha256'] and len(raw)==row['size']
             and tree[:3]==[row['mode'].encode(),b'blob',row['blob'].encode()], 'exact cumulative blob and mode')
        if p in base['paths']:
            old=web.git(ctx,'ls-tree',meta['parent'],'--',p).split()
            need(row['sha256']==base['paths'][p] and old[:3]==tree[:3], 'all original source bytes and modes unchanged')
    for row in added:
        p=row['path']; old=web.git(ctx,'show',meta['parent']+':'+p).decode().splitlines();new=web.git(ctx,'show',meta['head']+':'+p).decode().splitlines()
        for tag,i,j,k,l in difflib.SequenceMatcher(a=old,b=new,autojunk=False).get_opcodes():
            if tag=='equal':continue
            removed=old[i:j];inserted=new[k:l]
            need(all('expect(' in line for line in removed) and all('expect(' in line or re.match(r'^\s*const\s+\w+\s*=.*;',line) for line in inserted)
                 and not any(re.search(r'\b(skip|only|todo)\b',line) for line in inserted), 'only assertion/expectation repair; no test removal or skip')
    results=a.document(root,item['official_results']);runs=[x['actual'] for x in results['runs']]
    failed=[x for x in runs if x.get('path')==web.CODE_CI_PATHS['interaction-standards']]
    pr=source['existing_PR'];need(len(failed)==1 and failed[0]['head_sha']==base['commit']
         and failed[0]['status']=='completed' and failed[0]['conclusion']=='failure'
         and failed[0]['repository']['id']==base['repository_id']
         and any(x.get('number')==pr and x.get('head',{}).get('sha')==base['commit'] for x in failed[0].get('pull_requests',[]))
         and report['actual_PR']['number']==pr and report['actual_PR']['head']==base['commit'], 'real failed original exact-head PR CI')
    native_ci=[]
    for command in found[0].get('items',[]):
        output=command.get('output',{})
        if command.get('type')!='commandExecution' or command.get('status')!='completed' or command.get('exitCode')!=0 or output.get('truncated') is not False:continue
        try:value=json.loads(output.get('text',''))
        except (TypeError,ValueError):continue
        if isinstance(value,list):native_ci += [x for x in value if isinstance(x,dict) and x.get('id')==failed[0]['id']]
    need(any(x.get('head')==base['commit'] and x.get('status')=='completed' and x.get('conclusion')=='failure' for x in native_ci), 'actual native CI result for same failed run and original head')
    log=w.safe_path(root,web.code_pin(root,source['actual_official_failed_log'])['path']).read_text()
    log=re.sub(r'\^\[\[[0-9;]*m','',log); failures=re.findall(r'FAIL\s+(src/[^\s]+\.test\.tsx?)',log)
    need(set(failures)==paths and len(failures)>0, 'real CI failure paths exactly match changed tests')
    for k,left,right in [('increment_forward',meta['parent'],meta['head']),('increment_inverse',meta['head'],meta['parent']),('cumulative_forward',meta['base'],meta['head']),('cumulative_inverse',meta['head'],meta['base'])]:
        real=web.git(ctx,'diff','--no-ext-diff','--binary','--full-index',left,right)
        need(web._patch_effect(web._patch_delta(web._external_bytes(source[k],binding)))==web._patch_effect(web._patch_delta(real)), 'real forward/inverse source patch')
    with tarfile.open(fileobj=io.BytesIO(web._external_bytes(source['test_source_archive'],binding))) as tar:
        files=[m for m in tar.getmembers() if m.isfile()]
        need(len(files)==len(paths) and {m.name for m in files}==paths and all(m.isfile() or m.isdir() for m in tar.getmembers())
             and all(hashlib.sha256(tar.extractfile(m).read()).hexdigest()==full[m.name]['sha256'] for m in files), 'real test-source archive, not platform restore')
    return {**ctx,'paths':{p:row['sha256'] for p,row in full.items()},'increment_allowed_operations':web.CODE_OPS,
            'increment_actor_id':base['actor_id'],'existing_pull_number':pr,
            'direct_owner_frontend_source':True,'increment_source_mode':'actual_CI_test_successor',
            'increment_forward_patch':source['cumulative_forward'],'increment_inverse_patch':source['cumulative_inverse']}
