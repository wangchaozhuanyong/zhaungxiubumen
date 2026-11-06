"""Append-only source catalog for a current stage of a closed legacy parent.

This records provenance and logical rows only. It never creates a goal, CMS
action, effect, policy, permit, current row or permission to write.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import workflow_control as w

SCHEMA = 'professional-cms-legacy-current-stage-source/v1'
EVENT = 'professional_cms_legacy_current_stage_source'


def _need(value, message):
    if not value:
        raise w.WorkflowError(message)


def _pinned(root, pin, *, external_root=None):
    _need(isinstance(pin, dict) and set(pin) == {'path', 'sha256', 'size'}, 'exact source pin required')
    path = Path(pin['path'])
    if external_root is None:
        path = w.safe_path(root, path)
    else:
        try:
            path = path.resolve(strict=True)
        except FileNotFoundError:
            _need(path.is_absolute() and path.resolve(strict=False).is_relative_to(Path(external_root).resolve(strict=True)),
                  'source outside original website project')
            from professional_cms_source_custody import recovered_bytes
            return recovered_bytes(root, pin)
        _need(path.is_relative_to(Path(external_root).resolve(strict=True)), 'source outside original website project')
    raw = path.read_bytes()
    _need(len(raw) == pin['size'] and hashlib.sha256(raw).hexdigest() == pin['sha256'], 'source bytes differ')
    return raw


def _json(root, pin, *, external_root=None):
    value = json.loads(_pinned(root, pin, external_root=external_root))
    _need(isinstance(value, dict), 'source object required')
    return value


def _final(turn):
    return [i for i in turn.get('items', []) if i.get('type') == 'agentMessage' and i.get('phase') == 'final_answer']


def validate(root, source):
    import department_autonomy as a
    root = Path(root).resolve()
    keys = {'schema', 'parent_task_id', 'maintenance_task_id', 'owner', 'executor',
            'website_role', 'parent_snapshot', 'coordination', 'owner_adoption', 'owner_native',
            'web_result', 'web_native', 'candidate'}
    _need(isinstance(source, dict) and set(source) == keys and source['schema'] == SCHEMA,
          'exact source-only stage schema required')
    parent = source['parent_task_id']; maintenance = source['maintenance_task_id']
    _need(w.validate_task_id(parent) == parent and w.validate_task_id(maintenance) == maintenance and parent != maintenance,
          'distinct original parent and existing maintenance task required')
    parent_path = w.snapshot_path(root, parent)
    _need(w.file_digest(root, str(parent_path.relative_to(root))) == source['parent_snapshot'], 'original parent pin changed')
    snapshot = w.read_json(parent_path)
    _need(snapshot.get('task_id') == parent and snapshot.get('current_state') == 'closed'
          and not snapshot.get('goal_delivery') and not snapshot.get('goal_contract'),
          'closed historical parent without current goal required')
    maint = w.read_json(w.snapshot_path(root, maintenance))
    _need(maint.get('task_id') == maintenance and maint.get('current_state') not in w.TERMINAL_STATES
          and maint.get('goal_delivery', {}).get('primary_owner') == 'system-development'
          and isinstance(maint.get('goal_contract'),dict)
          and w.file_digest(root,maint['goal_contract']['path']) == maint['goal_contract']
          and isinstance(maint.get('goal_delivery',{}).get('authorization_pin'),dict)
          and w.file_digest(root,maint['goal_delivery']['authorization_pin']['path']) == maint['goal_delivery']['authorization_pin'],
          'active original system maintenance task and frozen authority required')
    _need(not w.validate_workflow_events(root, parent) and not w.validate_workflow_events(root, maintenance),
          'intact parent and maintenance event chains required')
    registry = w.department_registry(root)
    owner = source['owner']; executor = source['executor']; webrole = source['website_role']
    _need(owner == 'paid-growth-data' and executor == 'publishing' and webrole == 'designated-development'
          and a.professional(root, owner) and a.professional(root, executor), 'exact existing professional roles required')
    external = w.read_json(root / 'data/department-registry.json').get('collaboration_bindings', {}).get(webrole, {})
    _need(external.get('thread_id') and external.get('cwd') and external.get('project_id'), 'actual original WEB binding required')
    coordination = _pinned(root, source['coordination']).decode('utf-8')
    _need(all(x in coordination for x in (parent, owner, executor, source['candidate']['sha256'][:6])),
          'actual bounded current coordination must identify original parent, roles and candidate')
    owner_native = _json(root, source['owner_native'])
    web_native = _json(root, source['web_native'])
    owner_binding = registry[owner]['chat_binding']
    _need(owner_native.get('capture_kind') == web_native.get('capture_kind') == 'first_party_read_thread_selected_items_not_full_raw'
          and owner_native.get('thread', {}).get('id') == owner_binding['task_id']
          and owner_native['thread'].get('cwd') == owner_binding['cwd']
          and web_native.get('thread', {}).get('id') == external['thread_id']
          and web_native['thread'].get('cwd') == external['cwd'], 'exact actual native identities required')
    turns = owner_native.get('turns', [])
    _need(len(turns) == 4 and all(t.get('status') == 'completed' for t in turns), 'four actual completed owner context turns required')
    users = [i for t in turns for i in t.get('items', []) if i.get('type') == 'userMessage']
    finals = [i for t in turns for i in _final(t)]
    _need(len(users) >= 3 and len(finals) == 4 and all(i.get('id') for i in users + finals)
          and sum(i['id'] in coordination for i in users) >= 2
          and any('按照你的方案执行' in json.dumps(i.get('content', []), ensure_ascii=False) for i in users)
          and any('方案' in i.get('text', '') for i in finals),
          'actual original human, proposal and professional adoption context required')
    webturn = web_native.get('turn', {}); webfinal = _final(webturn)
    _need(webturn.get('status') == 'completed' and len(webfinal) == 1, 'actual completed original WEB result required')
    report = _json(root, source['web_result'])
    _need(report.get('task_id') == parent and report.get('business_primary_owner') == owner
          and report.get('WEB_executor') == webrole and report.get('concrete_local_candidate') == source['candidate'],
          'original producer result and exact candidate required')
    owner_text = _pinned(root, source['owner_adoption']).decode('utf-8')
    _need(parent in owner_text and owner in owner_text and source['candidate']['sha256'] in owner_text
          and source['web_result']['sha256'] in owner_text and any(source['owner_adoption']['path'] in i.get('text', '') for i in finals),
          'actual completed owner adoption must name both original sources')
    _need(report.get('actual_git', {}).get('head', '')[:8] in webfinal[0].get('text', ''),
          'actual WEB final must identify its own candidate')
    candidate = _json(root, source['candidate'], external_root=external['cwd'])
    _need(candidate.get('task_id') == parent and candidate.get('business_owner') == owner
          and candidate.get('code_executor') == webrole and candidate.get('future_CMS_executor') == 'original publishing'
          and candidate.get('production_grant_or_CMS_permit') is False,
          'original nonexecuting candidate identity required')
    rows = candidate.get('changes')
    _need(isinstance(rows, list) and len(rows) == 4, 'four independently identified source rows required')
    result=[]; ids=set(); slugs=set()
    for row in rows:
        rid=row.get('record_id');slug=row.get('slug');before=row.get('before',{}).get('content_zh');desired=row.get('desired',{}).get('content_zh');fragment=row.get('append_html')
        _need(row.get('table') == 'services' and row.get('changed_fields') == ['content_zh']
              and isinstance(rid,str) and isinstance(slug,str) and rid not in ids and slug not in slugs
              and isinstance(before,str) and isinstance(desired,str) and isinstance(fragment,str) and fragment
              and desired.startswith(before) and desired[len(before):].strip() == fragment
              and before.count(fragment)==0 and desired.count(fragment)==1
              and hashlib.sha256(before.encode()).hexdigest()==row.get('before_content_sha256')
              and hashlib.sha256(desired.encode()).hexdigest()==row.get('desired_content_sha256'),
              'unique exact one-field append and candidate bytes required')
        ids.add(rid);slugs.add(slug)
        key=w.sha256_value([parent,source['candidate']['sha256'],'services',rid,'content_zh'])
        result.append({'logical_source_key':key,'table':'services','record_id':rid,'slug':slug,
                       'field':'content_zh','before_sha256':row['before_content_sha256'],
                       'desired_sha256':row['desired_content_sha256'],
                       'prior_key_effect':'UNKNOWN','current_full41':'NOT_OBTAINED'})
    return {'parent_task_id':parent,'maintenance_task_id':maintenance,'owner':owner,'executor':executor,
            'candidate':source['candidate'],'logical_rows':result,'source_only':True,
            'execution_action_registered':False,'platform_permit_issued':False,'production_READY':False}


def catalog(root, parent):
    import department_autonomy as a
    root=Path(root); rows=[]
    for event in w.read_jsonl(root / w.WORKFLOW_EVENTS):
        item=event.get('details', {}).get(EVENT)
        if item and item.get('parent_task_id') == parent:
            source=a.document(root,item['source'])
            value=validate(root,source)
            _need(event.get('task_id') == value['maintenance_task_id'], 'exact maintenance event required')
            rows.append({**value,'registration':item['source'],'event_id':event['event_id']})
    _need(len(rows) <= 1, 'conflicting legacy stage source registrations')
    return rows


def register(root, source_path):
    import department_autonomy as a
    root=Path(root);pin=w.file_digest(root,source_path);source=a.document(root,pin)
    value=validate(root,source)
    with w.workflow_lock(root):
        _need(w.file_digest(root,source_path)==pin,'stage source changed before append')
        value=validate(root,source)
        rows=catalog(root,value['parent_task_id'])
        if rows:
            _need(rows[0]['registration']==pin,'same parent already has a different stage source')
            return {'result':'duplicate_ignored',**rows[0]}
        snapshot=w.read_json(w.snapshot_path(root,value['maintenance_task_id']))
        event=w.append_workflow_event(root,value['maintenance_task_id'],snapshot['current_state'],
            {EVENT:{'parent_task_id':value['parent_task_id'],'source':pin},'external_permission_issued':False})
    return {'result':'recorded',**value,'registration':pin,'event_id':event['event_id']}


EXEC_SCHEMA = 'professional-cms-legacy-current-execution-source/v1'
EXEC_EVENT = 'professional_cms_legacy_current_execution_source'


def _same_pin(root, left, right):
    if not isinstance(left, dict) or not isinstance(right, dict): return False
    return (left.get('sha256') == right.get('sha256') and left.get('size') == right.get('size')
            and w.safe_path(root,left.get('path','')) == w.safe_path(root,right.get('path','')))


def validate_execution_source(root, source):
    """Admit actual dated PUB observations as bounded stage metadata only.

    The derived IDs have never been permits or prior provider keys. This reader
    cannot produce a policy, alter a row, or declare an issuer/target live.
    """
    root=Path(root).resolve()
    _need(isinstance(source,dict) and set(source)=={'schema','parent_task_id','maintenance_task_id',
          'source_event_id','report','PUB_completed_native','requests'} and source['schema']==EXEC_SCHEMA,
          'exact current execution source envelope required')
    parent=source['parent_task_id'];prior=catalog(root,parent)
    _need(len(prior)==1 and prior[0]['event_id']==source['source_event_id']
          and prior[0]['maintenance_task_id']==source['maintenance_task_id'], 'one actual original source catalog event required')
    original=prior[0];old=_json(root,original['registration']);report=_json(root,source['report'])
    complete=_json(root,source['PUB_completed_native'])
    registry=w.department_registry(root);pub=registry[original['executor']]['chat_binding']
    turn=complete.get('turn',{});finals=_final(turn)
    _need(complete.get('capture_kind')=='first_party_read_thread_selected_items_not_full_raw'
          and complete.get('thread',{}).get('id')==pub['task_id']
          and complete['thread'].get('cwd')==pub['cwd'] and turn.get('status')=='completed'
          and len(finals)==1 and Path(source['report']['path']).name in finals[0].get('text','')
          and report.get('task_id')==parent and report.get('status_source_only_event')==original['event_id']
          and report.get('CMS_Save')==0 and report.get('original_key_effects')=='UNKNOWN',
          'actual PUB completed source and unchanged original stage required')
    pins=source['requests'];rows=report.get('rows')
    _need(isinstance(pins,list) and len(pins)==4 and isinstance(rows,list) and len(rows)==4,
          'four actual separate PUB request pins required')
    expected={x['record_id']:x for x in original['logical_rows']};found=set();out=[]
    for pin in pins:
        req=_json(root,pin);rid=req.get('record_id');priorrow=expected.get(rid)
        _need(priorrow is not None and rid not in found,'distinct original registered row required');found.add(rid)
        rr=[x for x in rows if x.get('record_id')==rid]
        _need(len(rr)==1 and _same_pin(root,pin,rr[0].get('source_request'))
              and _same_pin(root,req.get('current_authenticated_raw_full41'),rr[0].get('raw')),
              'actual PUB report must bind the exact request and raw row')
        _need(req.get('schema')=='PUB-four-row-original-current-execution-source-request/v1'
              and req.get('business_parent')==parent and req.get('owner')==original['owner']
              and req.get('executor')==original['executor'] and req.get('table')=='services'
              and req.get('slug')==priorrow['slug'] and req.get('changed_fields')==['content_zh']
              and req.get('physical_scope')==f'company.example:services:{rid}:content_zh'
              and _same_pin(root,req.get('adopted_catalog'),original['registration'])
              and req.get('candidate')==original['candidate']
              and _same_pin(root,req.get('human_and_owner_native_evidence'),old['owner_native'])
              and _same_pin(root,req.get('business_adoption'),old['owner_adoption'])
              and _same_pin(root,req.get('WEB_source'),old['web_result']),
              'original owner, target, scope, candidate and source lineage required')
        _need(all(req.get(k)=='DATA_MISSING' for k in ('execution_action_id','candidate_version',
              'issuer_namespace','target_binding','prior_permit_id','prior_run_id'))
              and req.get('original_key_effect')=='UNKNOWN' and req.get('semantic_dedup_not_zero_proof') is True
              and req.get('proposed_scope_not_authority') is True and req.get('status')=='PREPARED_INPUT_NOT_REGISTERED_NOT_READY'
              and req.get('save') is False and req.get('permit_issued') is False and req.get('fresh_again_before_execution') is True,
              'missing prior effects and unissued permission must remain unknown')
        native=_json(root,req['PUB_actual_native']);historical=native.get('turns',[])
        _need(native.get('thread',{}).get('id')==pub['task_id'] and native['thread'].get('cwd')==pub['cwd']
              and len(historical)==1 and historical[0].get('id')==turn.get('id')
              and historical[0].get('status') in {'inProgress','completed'}, 'same actual PUB native turn required')
        calls=[i for i in historical[0].get('items',[]) if i.get('type')=='mcpToolCall' and i.get('status')=='completed'
               and i.get('server')=='cua_repl' and i.get('tool')=='js']
        codes=[i.get('arguments',{}).get('code','') for i in calls]
        _need(any('Network.getResponseBody' in c for c in codes)
              and any('writeFile' in c and (req['slug']+'.response.json') in c for c in codes),
              'actual PUB native response read and exact raw file capture required')
        row=_json(root,req['current_authenticated_raw_full41']);ms=[k for k in row if k.endswith('_ms')]
        stable=set(row)-{'content_zh','created_at','updated_at','version'}
        content=row.get('content_zh');observed=w._parse_observed_at(req.get('observation_utc'))
        import datetime as dt
        _need(len(row)==41 and len(ms)==11 and len(stable)==37 and row.get('id')==rid
              and row.get('slug')==req['slug'] and row.get('status')=='published'
              and type(row.get('version')) is int and row['version']==req.get('server_version')
              and row.get('updated_at')==req.get('raw_server_updated_at') and w._parse_observed_at(row['updated_at'])
              and observed is not None and observed<=dt.datetime.now(dt.timezone.utc)
              and isinstance(content,str) and hashlib.sha256(content.encode()).hexdigest()==req.get('current_content_sha256')
              and req.get('current_content_sha256')==req.get('candidate_before_sha256')==priorrow['before_sha256']
              and req.get('candidate_desired_sha256')==priorrow['desired_sha256'] and req.get('current_semantic_state')=='BEFORE_MATCH'
              and req.get('protection')=={'total_fields':41,'non_write_fields':40,'malay_fields':11,'stable_business_fields_required':37},
              'dated actual full41/MS11/version/raw CAS and original before match required')
        token=w.sha256_value([parent,original['candidate']['sha256'],'services',rid,'content_zh'])
        action='current-stage-cms-'+token[:24];version='current-stage-source-'+token[:24]
        out.append({'action_id':action,'candidate_version':version,'issuer_namespace':version,
                    'parent_task_id':parent,'owner':original['owner'],'department':original['executor'],
                    'action_class':'cms_write','table':'services','record_id':rid,'slug':req['slug'],
                    'changed_fields':['content_zh'],'physical_scope':req['physical_scope'],
                    'candidate_sha256':original['candidate']['sha256'],
                    'desired_sha256':priorrow['desired_sha256'],'PUB_request':pin,
                    'dated_full41':req['current_authenticated_raw_full41'],'observation_utc':req['observation_utc'],
                    'prior_permit_id':'DATA_MISSING','prior_run_id':'DATA_MISSING','original_key_effect':'UNKNOWN',
                    'runtime_target_registered':False,'issuer_target_registered':False,
                    'actual_action_allowed':False,'production_READY':False})
    _need(found==set(expected) and len({v['action_id'] for v in out})==4,
          'complete distinct original four-row stage required')
    return {'parent_task_id':parent,'maintenance_task_id':source['maintenance_task_id'],
            'source_event_id':source['source_event_id'],'actions':out,'stage_execution_metadata_registered':True,
            'current_authority_not_inferred':True,'external_permission_issued':False,'production_READY':False}


def execution_catalog(root,parent):
    import department_autonomy as a
    root=Path(root);result=[]
    for e in w.read_jsonl(root/w.WORKFLOW_EVENTS,where={('details',EXEC_EVENT,'parent_task_id'):parent}):
        detail=e.get('details',{}).get(EXEC_EVENT);item=a.document(root,detail['source'])
        val=validate_execution_source(root,item)
        _need(e.get('task_id')==val['maintenance_task_id'],'exact original maintenance event required')
        result.append({**val,'registration':detail['source'],'event_id':e['event_id']})
    _need(len(result)<=1,'conflicting current execution source registrations')
    return result


def register_execution_source(root,path):
    import department_autonomy as a
    root=Path(root);pin=w.file_digest(root,path);source=a.document(root,pin);val=validate_execution_source(root,source)
    with w.workflow_lock(root):
        _need(w.file_digest(root,path)==pin,'current execution source changed before registration')
        val=validate_execution_source(root,source);prior=execution_catalog(root,val['parent_task_id'])
        if prior:
            _need(prior[0]['registration']==pin,'different execution stage source already registered')
            return {'result':'duplicate_ignored',**prior[0]}
        snap=w.read_json(w.snapshot_path(root,val['maintenance_task_id']))
        ev=w.append_workflow_event(root,val['maintenance_task_id'],snap['current_state'],
            {EXEC_EVENT:{'parent_task_id':val['parent_task_id'],'source':pin},'external_permission_issued':False})
    return {'result':'recorded',**val,'registration':pin,'event_id':ev['event_id']}


def pending_execution_action(root,task,request):
    rows=execution_catalog(root,task)
    if not rows:return None
    selected=[x for x in rows[0]['actions'] if x['action_id']==request.get('action_id')]
    if not selected:return None
    action=selected[0]
    exact_optional={'record_id':action['record_id'],'object_ids':[action['record_id']],
                    'table':action['table'],'changed_fields':action['changed_fields'],
                    'physical_scope':action['physical_scope'],'candidate_sha256':action['candidate_sha256'],
                    'issuer_namespace':action['issuer_namespace']}
    _need(request.get('sender_department')==action['department']
          and request.get('department',action['department'])==action['department']
          and request.get('scope')==action['physical_scope']
          and request.get('candidate_version')==action['candidate_version']
          and all(k not in request or request[k]==v for k,v in exact_optional.items())
          and not any(request.get(k) for k in ('approval_id','consume_approval','actual_action_allowed',
                        'production_READY','permit_issued','prior_permit_id','prior_run_id')),
          'exact pending original actor/target/version; no caller execution or prior permit claims')
    return {**action,'registration':rows[0]['registration'],'event_id':rows[0]['event_id']}


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('command',choices=['check','register','status','execution-check','execution-register','execution-status'])
    parser.add_argument('--input');parser.add_argument('--task-id')
    args=parser.parse_args();root=Path(__file__).resolve().parents[1]
    try:
        if args.command == 'check':
            import department_autonomy as a
            result=validate(root,a.document(root,w.file_digest(root,args.input)))
        elif args.command == 'register':result=register(root,args.input)
        elif args.command == 'execution-check':
            import department_autonomy as a
            result=validate_execution_source(root,a.document(root,w.file_digest(root,args.input)))
        elif args.command == 'execution-register':result=register_execution_source(root,args.input)
        elif args.command == 'execution-status':result={'task_id':args.task_id,'execution_sources':execution_catalog(root,args.task_id)}
        else:result={'task_id':args.task_id,'registered_sources':catalog(root,args.task_id),'source_only':True}
        print(json.dumps(result,ensure_ascii=False,indent=2))
    except (w.WorkflowError,ValueError,KeyError,OSError) as error:
        parser.exit(1,str(error)+'\n')
