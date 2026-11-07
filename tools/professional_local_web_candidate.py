"""Exact original professional local-only WEB preparation; never a production permit."""
from pathlib import Path
import json,hashlib
import workflow_control as w

SCHEMA='professional-local-web-candidate-source/v1'
EVENT='professional_local_web_candidate_source'
MARKER='professional_local_web_candidate_source'
TASK='fc-20261010-assistant1-remaining-business-continuation-v2'
SCOPE='project:flashcast:assistant1:remaining-original-goals:v2'
ACTION='SEO2-WEB-shop-render-local-candidate-20261108-v1'
ROOTDIR='reports/local-department-system-repair-20261030-v1/SOURCE-RELEASE-AND-VERIFIED-CLEANUP-20261107-v1/SYS52-shop-local-source-v1/'
IDENTITY=('task_id','scope','action_id','sender_department','action_class','source_project_id','target_project_id',
 'target_department','target_thread_id','target_thread_title','target_cwd','target_sidebar_section_id',
 'payload','payload_sha256','delivery_mode','assignment_record_required','authorization_changes')
FRESH={'actual_target_state','actual_sender_state','actual_live_inventory','live_observed_at'}
BODY=('task_id='+TASK+'\nscope='+SCOPE+'\naction_id='+ACTION+'\nsender_department=seo-content-research\n'
      'target_department=designated-development\nassignment_record_required=false\n\n'
      '沿原店铺中英文服务页初始 HTML 原目标，仅在原网站项目隔离工作区准备本地候选及定向自检。'
      '复用现有 shop-renovation 文案，仅允许 functions/expandedReadableBody.ts 和 '
      'src/lib/expandedReadableBody.test.ts 的必要差异；保护 office、其他页面、马来语、CMS 和并行 WIP。'
      '原评估与 HQ 决定及其完整哈希见来源登记；先查实际效果，完成后归原 SEO2。'
      '本消息不授权 push、PR、merge、部署、CMS Save、账号或费用；候选不等于上线。\n')


def doc(root,pin):
    if not isinstance(pin,dict) or w.file_digest(root,pin.get('path',''))!=pin:raise w.WorkflowError('exact immutable local preparation source required')
    return w.read_json(w.safe_path(root,pin['path']))


def _source(root,item,snapshot):
    import department_autonomy as a
    from qa_review_plan import _review_native_containers
    required={'schema','task_id','decision','HQ_native','SEO2_input','SEO2_outbox','SEO2_native','WEB_native','payload'}
    if not isinstance(item,dict) or set(item)!=required or item['schema']!=SCHEMA or item['task_id']!=TASK:raise w.WorkflowError('exact local preparation source shape required')
    if item['decision']['sha256']!='56b9dde1eeee4a0cadc56d85a19bc8605794fd5d72a029062fadd427edee0d0e' or item['SEO2_input']['sha256']!='df441cf6c1e782923a8e42b1fb44e883151da0b3f590fc48007ff377b8ad5f19' or item['SEO2_outbox']['sha256']!='457c50b24daf7811721c3b06ce73e1261a62d306b12726c7d0e0d867b786b84c':raise w.WorkflowError('original HQ decision and professional input required')
    if (item['HQ_native']['sha256']!='0a454da4df31e3b506a81fe9c0000cf3c7f80f89b38426cbade038e5d13f7845'
            or item['SEO2_native']['sha256']!='c5b1d87dd12bba60ba0dba681a42377f1efd988b2fe31488f5234cd80a6a13b8'
            or item['WEB_native']['sha256']!='c161fe4e9124217a194627bcaf1317f67c3576ace8f1f3b65a27ec3eb8f41f8e'):
        raise w.WorkflowError('exact first-party HQ, professional and WEB native sources required')
    d=doc(root,item['decision']); seo=doc(root,item['SEO2_input']);box=doc(root,item['SEO2_outbox']);hq=doc(root,item['HQ_native']);sn=doc(root,item['SEO2_native']);web=doc(root,item['WEB_native'])
    delegation=doc(root,d['owner_delegation']);a.authority(root)
    goal=snapshot.get('goal_delivery',{});frozen=doc(root,snapshot['goal_contract'])
    fields=('primary_owner','producer_departments','authorized_scope','human_authorization','required_execution_actions','collaboration_scopes')
    if not (snapshot.get('task_id')==TASK and snapshot.get('current_state') not in w.TERMINAL_STATES
            and all(goal.get(k)==frozen.get(k) for k in fields) and goal.get('primary_owner')=='seo-content-research'
            and SCOPE in goal.get('authorized_scope',[]) and d.get('task_id')==seo.get('task_id')==TASK
            and d.get('scope')==seo.get('scope')==SCOPE and d.get('actor')=='operations'
            and d.get('professional_owner')==seo.get('owner')=='seo-content-research'
            and d.get('technical_executor')=='designated-development'
            and d.get('push_merge_deploy_CMS_permission_issued') is False and d.get('account_or_fee_change') is False
            and d.get('parent_goal_closed') is False and seo.get('HQ_exact_decision')==item['decision']
            and box.get('task_id')==TASK and box.get('sender_department')=='seo-content-research' and box.get('primary_delivery')==item['SEO2_input']
            and seo.get('actual_WEB_evaluation_native')==item['WEB_native']
            and delegation.get('source')=='first_party_read_thread' and delegation.get('role')=='human'
            and delegation.get('not_a_synthetic_authorization') is True):raise w.WorkflowError('actual original owner, goal, human delegation and local decision required')
    human=doc(root,goal['authorization_pin']);auth=goal['human_authorization']
    if not (human.get('message',{}).get('type')=='userMessage' and human['message'].get('id')==auth.get('message_id') and human.get('source_thread_id')==auth.get('source_thread_id') and human['message'].get('content')):raise w.WorkflowError('original human source required')
    hpage=hq.get('native',{});ht=[t for t in hpage.get('turns',[]) if t.get('id')=='example-native-bd1a7e5f0e445eb1'];hc=[c for t in ht for c in t.get('items',[]) if c.get('id')=='exec-0b428398-d26c-435c-90e1-8e53680b2be7']
    if not (hq.get('source')=='first_party_read_thread' and hpage.get('thread',{}).get('id')==d.get('decision_thread','<LOCAL_TASK_ID>') and hpage['thread'].get('hostId')=='local' and Path(hpage['thread'].get('cwd','')).resolve()==Path(root).resolve() and len(ht)==len(hc)==1 and ht[0].get('status')=='completed' and not ht[0].get('error') and hc[0].get('server')=='codex_app' and hc[0].get('tool')=='send_message_to_thread' and hc[0].get('status')=='completed' and item['decision']['sha256'] in hc[0].get('arguments',{}).get('prompt','') and item['decision']['path'] in hc[0]['arguments']['prompt']):raise w.WorkflowError('genuine HQ native exact local decision required')
    registry=w.department_registry(root);owner=registry['seo-content-research']['chat_binding'];external=w.read_json(Path(root)/'data/department-registry.json')['collaboration_bindings']['designated-development']
    if hc[0]['arguments'].get('threadId')!=owner['task_id'] or external.get('generic_cross_project_access_allowed') is not False or external.get('runtime_goal_authorization_required') is not True:raise w.WorkflowError('exact original professional and external binding required')
    spage=sn.get('native',{});st=[t for t in spage.get('turns',[]) if t.get('id')=='example-native-8b811c250d1f2193'];sm=[m for t in st for m in t.get('items',[]) if m.get('id')=='msg_846747397f461b2849259011f59e73ed366dbb892b4a4959beaee06b3612ae9a']
    if not (sn.get('source')=='first_party_read_thread' and all(spage.get('thread',{}).get(k)==owner[v] for k,v in {'id':'task_id','title':'title','cwd':'cwd','hostId':'host_id'}.items()) and len(st)==len(sm)==1 and st[0].get('status')=='completed' and not st[0].get('error') and '457c50b24daf7811721c3b06ce73e1261a62d306b12726c7d0e0d867b786b84c' in sm[0].get('text','')):raise w.WorkflowError('actual completed original professional source required')
    _review_native_containers(web)
    if web.get('isError') is not False or len(web.get('content',[]))!=1:raise w.WorkflowError('actual original WEB native required')
    wp=json.loads(web['content'][0]['text']);wt=[t for t in wp.get('turns',[]) if t.get('id')=='example-native-874be7ae3e74acbf'];wm=[m for t in wt for m in t.get('items',[]) if m.get('id')=='msg_173bff3d45ac25eb40083f6d4cdedd5a0358311502de3632895bf47201b18318']
    if not (all(wp.get('thread',{}).get(k)==external[v] for k,v in {'id':'thread_id','title':'title','cwd':'cwd','hostId':'host_id'}.items()) and wp['thread'].get('kind')=='codex' and len(wt)==len(wm)==1 and wt[0].get('status')=='completed' and not wt[0].get('error') and wm[0].get('phase')=='final_answer' and wm[0].get('text')):raise w.WorkflowError('actual original WEB completed evaluation required')
    expected=['functions/expandedReadableBody.ts','src/lib/expandedReadableBody.test.ts'];proposal=seo.get('proposed_binding_requirements',{})
    if not (proposal.get('allowed_files')==expected and proposal.get('object')==['/zh/services/shop-renovation','/en/services/shop-renovation'] and d.get('reuse_existing_copy') is True and proposal.get('executor')=='designated-development'):raise w.WorkflowError('exact original two-file shop zh/en preparation required')
    report=seo.get('WEB_evaluation',{});webroot=Path('<WEBSITE_PROJECT_ROOT>').resolve();rp=Path(report.get('path','')).resolve(strict=True)
    if not rp.is_relative_to(webroot/'reports/next20-shop-server-render-evaluation-20261108-v1'):
        raise w.WorkflowError('original WEB evaluation location required')
    raw=w.validation_bytes(rp)
    if len(raw)!=report.get('size') or hashlib.sha256(raw).hexdigest()!=report.get('sha256'):
        raise w.WorkflowError('actual original WEB evaluation bytes required')
    payload=w.safe_path(root,item['payload']['path']);data=w.validation_bytes(payload)
    if w.file_digest(root,item['payload']['path'])!=item['payload'] or data!=BODY.encode():raise w.WorkflowError('exact nonproduction local-only message required')
    return {'task_id':TASK,'scope':SCOPE,'action_id':ACTION,'sender_department':'seo-content-research','action_class':'thread_message',
      'source_project_id':owner['project_id'],'target_project_id':external['project_id'],'target_department':'designated-development',
      'target_thread_id':external['thread_id'],'target_thread_title':external['title'],'target_cwd':external['cwd'],
      'target_sidebar_section_id':external['sidebar_section_id'],'payload':item['payload'],'payload_sha256':item['payload']['sha256'],
      'delivery_mode':'official_native_queue','assignment_record_required':False,'authorization_changes':[]}


def registered(root,snapshot,request):
    if not isinstance(request,dict) or request.get('action_id')!=ACTION:return None
    if set(request)-set(IDENTITY)-FRESH-{MARKER}:raise w.WorkflowError('local-only message forbids production fields')
    events=[e for e in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS,where={'task_id':TASK}) if e.get('details',{}).get(EVENT)]
    if not events:return None
    if len(events)!=1 or snapshot.get('task_id')!=TASK or w.validate_workflow_events(root,TASK):raise w.WorkflowError('one intact registered local source required')
    pin=events[0]['details'][EVENT];action={**_source(root,doc(root,pin),snapshot),MARKER:pin}
    rows=[x for x in snapshot['goal_delivery'].get('approved_actions',[]) if x.get('action_id')==ACTION]
    if rows!=[action] or any(request[k]!=action[k] for k in request if k not in FRESH):raise w.WorkflowError('exact registered local preparation message required')
    return {'action':action,'registration':pin,'local_code_work_authorized':True,'production_READY':False,'external_permission_issued':False}


def approved_action(root,snapshot,request):
    v=registered(root,snapshot,request);return v['action'] if v else None


def binding(root,snapshot,request):
    if not registered(root,snapshot,request):return None
    source=w.department_registry(root)['seo-content-research']['chat_binding'];target=w.read_json(Path(root)/'data/department-registry.json')['collaboration_bindings']['designated-development']
    return source,{**target,'task_id':target['thread_id']}


def message_route(root,snapshot,request):
    import department_autonomy as a
    if request.get('action_id')==ACTION and not all(k in request for k in IDENTITY):raise w.WorkflowError('complete exact local preparation message required')
    v=registered(root,snapshot,request)
    if not v:return None
    return {**a.authority(root),'source':v['registration'],'report':v['action']['payload'],'scope':SCOPE,'sender_department':'seo-content-research','target_department':'designated-development','purpose':'professional_local_web_candidate_transport','external_permission_issued':False,'business_producer_added':False,'current_assignment_changed':False}


def record(root,task_id,input_path):
    import department_autonomy as a,goal_delivery_runtime as g
    from department_rotation import prohibit_validation_write
    prohibit_validation_write();pin=w.file_digest(root,input_path);item=doc(root,pin)
    if task_id!=TASK:raise w.WorkflowError('original task required')
    with w.workflow_lock(root),w.request_validation_context() as ctx:
        path=w.snapshot_path(root,TASK);before=w.file_digest(root,str(path.relative_to(root)));raw=path.read_bytes();s=g.restore_goal(root,w.read_json(path));action={**_source(root,item,s),MARKER:pin}
        old=[e for e in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS,where={'task_id':TASK}) if e.get('details',{}).get(EVENT)];rows=[x for x in s['goal_delivery'].get('approved_actions',[]) if x.get('action_id')==ACTION]
        if old or rows:
            if len(old)==1 and old[0]['details'][EVENT]==pin and rows==[action]:return {'result':'duplicate_ignored','source':pin,'external_permission_issued':False}
            raise w.WorkflowError('original local action exists; reconcile effect')
        a._owner_message_transport_not_started(root,s,action)
        if any(x.get('task_id')==TASK and x.get('action_id')==ACTION for x in w.read_jsonl(Path(root)/w.POLICY_DECISIONS)) or w.validate_workflow_events(root,TASK):raise w.WorkflowError('prior policy or invalid original history')
        ctx.recheck()
        if w.file_digest(root,str(path.relative_to(root)))!=before:raise w.WorkflowError('original snapshot changed')
        backup=Path(root)/'backups/fc-20261024-original-flow-recovery-execution-stage-v1/SYS52-shop-source-v1'/('snapshot-'+before['sha256']+'.json')
        if backup.exists():
            if backup.read_bytes()!=raw:raise w.WorkflowError('backup mismatch')
        else:w.atomic_write_text(backup,raw.decode())
        goal=s['goal_delivery'];s['goal_delivery']={**goal,'approved_actions':[*goal.get('approved_actions',[]),action]}
        event=w.append_workflow_event(root,TASK,s['current_state'],{EVENT:pin,'goal_delivery':s['goal_delivery'],'actual_actor':'operations','external_permission_issued':False,'message_sent':False})
        w.atomic_write_json(path,s);journal={'schema':'professional-local-web-source-journal/v1','source':pin,'before':before,'after':w.file_digest(root,str(path.relative_to(root))),'backup':w.file_digest(root,str(backup.relative_to(root))),'event':event,'message_sent':False,'external_permission_issued':False}
        w.atomic_write_json(backup.parent/'journal.json',journal)
    return {'result':'recorded','source':pin,'journal':w.file_digest(root,str((backup.parent/'journal.json').relative_to(root))),'local_code_work_authorized':True,'production_READY':False,'message_sent':False,'external_permission_issued':False}
