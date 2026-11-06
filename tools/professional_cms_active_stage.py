"""Candidate: authenticate two owner-proposed CMS rows; never admit execution."""
from pathlib import Path
import hashlib
import json


def validate(root, owner_path, pub_paths, owner_native_path, snapshot):
    root = Path(root).resolve(strict=True)

    def need(value, message):
        if not value:
            raise ValueError(message)

    def read_pin(pin, allowed):
        p = Path(pin['path'])
        p = (root / p).resolve(strict=True) if not p.is_absolute() else p.resolve(strict=True)
        need(any(p.is_relative_to(Path(x).resolve(strict=True)) for x in allowed), 'source project boundary')
        data = p.read_bytes()
        need(hashlib.sha256(data).hexdigest() == pin['sha256'] and
             ('size' not in pin or len(data) == pin['size']), 'source pin mismatch')
        return json.loads(data)

    owner_path = Path(owner_path).resolve(strict=True)
    need(owner_path.is_relative_to(root), 'owner source project boundary')
    owner_raw = owner_path.read_bytes(); owner = json.loads(owner_raw)
    owner_digest = hashlib.sha256(owner_raw).hexdigest()
    task = owner['parent_task_id']; scope = owner['parent_scope']
    goal = snapshot['goal_delivery']
    frozen = read_pin(snapshot['goal_contract'], [root])
    need(owner['schema'] == 'Paid2-actual-owned-two-service-six-excerpt-execution-intent/v1'
         and snapshot['task_id'] == task and goal['primary_owner'] == owner['decision_actor'] == 'paid-growth-data-2'
         and scope in goal['authorized_scope'] and snapshot['current_state'] not in {'completed','cancelled','closed','failed'}
         and all(goal.get(k) == frozen.get(k) for k in ('primary_owner','producer_departments',
                 'authorized_scope','human_authorization','required_execution_actions')),
         'real active original owner and scope required')
    registry = json.loads((root/'data/department-registry.json').read_text())
    departments = {x['id']: x for x in registry['departments']}; binding = departments[owner['decision_actor']]['chat_binding']
    external = registry['collaboration_bindings']['designated-development']
    owner_source = read_pin(owner['actual_owner_execution_source'], [root])
    need(owner_source['original_task'] == task and owner_source['human_message'] == owner['actual_owner_execution_source']['human_message'],
         'current original human source binding required')
    human_native = read_pin(owner_source['evidence']['owner_native'], [root])
    need(human_native.get('isError') is False, 'actual original human native required')
    human = json.loads(human_native['content'][0]['text'])
    ops = departments['operations']['chat_binding']
    need(human.get('thread',{}).get('id') == ops['task_id'] and human['thread'].get('cwd') == ops['cwd'],
         'actual original human source thread required')
    matches = [(t,i) for t in human['turns'] for i in t['items'] if i.get('type') == 'userMessage' and i.get('id') == owner_source['human_message']]
    need(len(matches) == 1 and matches[0][0]['id'] == owner_source['human_turn'], 'real human message and turn required')
    native = json.loads(Path(owner_native_path).read_text()); need(native.get('isError') is False, 'real owner native required')
    native = json.loads(native['content'][0]['text']); thread = native['thread']
    need(all(thread.get(k) == binding[v] for k,v in {'id':'task_id','title':'title','cwd':'cwd','hostId':'host_id'}.items()),
         'fixed actual owner identity required')
    commands = [i for t in native['turns'] for i in t['items'] if i.get('type') == 'commandExecution'
                and i.get('status') == 'completed' and i.get('exitCode') == 0 and not i.get('output',{}).get('truncated')
                and owner_digest in i.get('output',{}).get('text','')]
    need(len(commands) == 1, 'one actual completed owner source command required')
    output = json.loads(commands[0]['output']['text']); actions = owner['actions']
    need(output.get('path') == str(owner_path.relative_to(root)) and output.get('sha256') == owner_digest
         and output.get('size') == len(owner_raw) and output.get('not_platform_permission') is True
         and len(actions) == len(pub_paths) == 2 and len({a['action_id'] for a in actions}) == 2
         and output.get('action_ids') == [a['action_id'] for a in actions], 'exact owner actions and output required')
    need(owner['action_metadata_status'].startswith('OWNER_DECIDED_AND_FROZEN_HERE; NOT_YET_REGISTERED')
         and owner['business_parent_complete'] is False, 'source only, no execution admission')
    requests = [json.loads(Path(p).read_text()) for p in pub_paths]
    need(len({r['record_id'] for r in requests}) == 2, 'two unique real records required')
    results = []
    for action in actions:
        matched = [r for r in requests if r['record_id'] == action['record_id']]
        need(len(matched) == 1, 'one PUB source per original record')
        request = matched[0]; fields = action['changed_fields']; desired = action['desired_fields']
        need(fields == ['excerpt_zh','excerpt_en','excerpt_ms'] and set(desired) == set(fields)
             and action['action_class'] == 'cms_write' and action['table'] == 'services'
             and action['business_owner'] == owner['decision_actor'] and action['execution_department'] == 'publishing'
             and request['task_id'] == task and request['business_scope'] == scope and request['executor'] == 'publishing'
             and request['owner'] == owner['decision_actor'] and request['record_id'] == action['record_id']
             and request['slug'] == action['slug'] and request['changed_fields'] == fields
             and request['physical_scope'] == action['physical_scope']
             and action['physical_scope'] == 'company.example:services:' + action['record_id'] + ':' + ','.join(fields)
             and request['write_payload_only'] == desired and action['platform_permission'] == 'NOT_ISSUED'
             and action['requested_issuer_role'] == 'designated-development'
             and action['actual_issued_issuer_target'] == 'NOT_YET_ISSUED_BY_REAL_ROLE'
             and action['requested_issuer_target'] == {'table':'services','id':action['record_id'],
                 'slug':action['slug'],'changedFields':fields,'candidateVersion':action['candidate_version'],
                 'actionId':action['action_id']},
             'exact original independent task, fields, scope, payload and role required')
        need(request['original_key_effect'] == 'UNKNOWN' and request['source_only_not_permit'] is True
             and action['original_key_effect'] == 'MUST_QUERY_ACTUAL_REGISTERED_KEY_AND_PREVIOUS_SAME_LOGICAL_ATTEMPT; no zero assertion',
             'unknown original effect remains unknown')
        need(request['owner_instruction']['sha256'] == owner_source['evidence']['brief']['sha256'],
             'actual original human-context brief required')
        brief = Path(request['owner_instruction']['path']).resolve(strict=True)
        need(brief.is_relative_to(root), 'brief project boundary')
        brief_bytes = brief.read_bytes()
        need(hashlib.sha256(brief_bytes).hexdigest() == request['owner_instruction']['sha256']
             and len(brief_bytes) == request['owner_instruction']['size'], 'exact original brief bytes')
        for key in ('current_owner_source','PUB_native','PUB_full41_raw'):
            read_pin(request[key], [root])
        frozen = read_pin(request['frozen_candidate'], [external['cwd']])
        read_pin(request['WEB_delivery'], [external['cwd']]); read_pin(request['WEB_continuation'], [external['cwd']])
        targets = [x for x in frozen['targets'] if x['id'] == action['record_id']]
        row = read_pin(request['PUB_full41_raw'], [root])
        need(request['current_owner_source']['sha256'] == owner['actual_owner_execution_source']['sha256']
             and frozen['current_execution_source']['sha256'] == owner['actual_owner_execution_source']['sha256']
             and frozen['task_id'] == task and len(targets) == 1 and targets[0]['desired'] == desired
             and targets[0]['fields'] == fields and len(row) == 41 and row['id'] == action['record_id']
             and row['slug'] == action['slug'] and row['updated_at'] == request['raw_updated_at']
             and row['version'] == request['version'] and len([x for x in row if x.endswith('_ms')]) == 11
             and all(row[x] == targets[0]['before'][x] for x in fields),
             'original candidate and dated full41/rawCAS required')
        need(action['candidate_sha256'] == request['frozen_candidate']['sha256']
             and action['candidate_version'] == owner['candidate_version'], 'exact shared original candidate required')
        results.append({'action_id':action['action_id'],'record_id':action['record_id'],
                        'candidate_version':action['candidate_version'],'physical_scope':action['physical_scope'],
                        'original_key_effect':'UNKNOWN','actual_action_allowed':False,'permit_issued':False})
    return {'status':'SOURCE_ONLY_NOT_REGISTERED','owner_source_sha256':owner_digest,'rows':results,
            'issuer_target':'NOT_ISSUED','production_READY':False}


def validate_supplement(root, owner_path, pub_paths, owner_native_path, snapshot,
                        supplement_path, supplement_native_path, pub_completed_native_path):
    """Bind owner-decided row versions to authenticated source, without issuing."""
    root = Path(root).resolve(strict=True)
    original = validate(root, owner_path, pub_paths, owner_native_path, snapshot)
    owner_path = Path(owner_path).resolve(strict=True)
    supplement_path = Path(supplement_path).resolve(strict=True)
    if not supplement_path.is_relative_to(root):
        raise ValueError('supplement project boundary')
    raw = supplement_path.read_bytes(); supplement = json.loads(raw)
    digest = hashlib.sha256(raw).hexdigest(); owner = json.loads(owner_path.read_bytes())
    prior = supplement.get('previous_owner_intent', {})
    if (supplement.get('schema') != 'Paid2-owned-record-qualified-CMS-candidate-identity-supplement/v1'
        or supplement.get('parent_task') != owner['parent_task_id'] or supplement.get('scope') != owner['parent_scope']
        or prior != {'path':str(owner_path.relative_to(root)), 'sha256':original['owner_source_sha256'], 'size':len(owner_path.read_bytes())}
        or supplement.get('content_or_object_or_action_id_changes') is not False
        or supplement.get('source_or_permit_or_future_version_claimed') is not False):
        raise ValueError('exact original owner supplement and preserved history required')
    native = json.loads(Path(supplement_native_path).read_text())
    if native.get('capture_kind') != 'first_party_read_thread_selected_items_not_full_raw':
        raise ValueError('actual selected native source required')
    registry = json.loads((root/'data/department-registry.json').read_text())
    binding = next(x['chat_binding'] for x in registry['departments'] if x['id'] == owner['decision_actor'])
    if any(native['thread'].get(k) != binding[v] for k,v in {'id':'task_id','title':'title','cwd':'cwd','hostId':'host_id'}.items()):
        raise ValueError('exact original owner identity required')
    cmds = [i for i in native['turn']['items'] if i.get('type') == 'commandExecution'
            and i.get('status') == 'completed' and i.get('exitCode') == 0
            and not i.get('output',{}).get('truncated') and digest in i.get('output',{}).get('text','')]
    if len(cmds) != 1:
        raise ValueError('actual completed supplemental source command required')
    out = json.loads(cmds[0]['output']['text']); rows = supplement['records']
    if (out.get('path') != str(supplement_path.relative_to(root)) or out.get('sha256') != digest
        or out.get('size') != len(raw) or len(rows) != 2
        or out.get('versions') != [x['record_candidate_version'] for x in rows]
        or len({x['record_candidate_version'] for x in rows}) != 2):
        raise ValueError('two actual distinct owner-decided candidate versions required')
    pub_native = json.loads(Path(pub_completed_native_path).read_text())
    pub = next(x['chat_binding'] for x in registry['departments'] if x['id'] == 'publishing')
    if (pub_native.get('capture_kind') != 'first_party_read_thread_selected_items_not_full_raw'
        or any(pub_native['thread'].get(k) != pub[v] for k,v in {'id':'task_id','title':'title','cwd':'cwd','hostId':'host_id'}.items())
        or pub_native['turn'].get('status') != 'completed'):
        raise ValueError('actual original PUB completed native required')
    expected_hashes = [json.loads(Path(p).read_text())['PUB_full41_raw']['sha256'] for p in pub_paths]
    checks = [x for x in pub_native['turn']['items'] if x.get('type') == 'commandExecution'
              and x.get('status') == 'completed' and x.get('exitCode') == 0
              and not x.get('output',{}).get('truncated')
              and all(d in x.get('output',{}).get('text','') for d in expected_hashes)]
    if len(checks) != 1:
        raise ValueError('actual original PUB row check required')
    pub_output = checks[0]['output']['text']
    import workflow_control as w
    records = []
    for row in rows:
        matches = [x for x in owner['actions'] if x['action_id'] == row['action_id'] and x['record_id'] == row['record_id']]
        if len(matches) != 1:
            raise ValueError('one exact original action and record required')
        action = matches[0]; version = row['record_candidate_version']
        req = next(x for x in (json.loads(Path(p).read_text()) for p in pub_paths) if x['record_id'] == action['record_id'])
        target = {'table':'services','id':action['record_id'],'slug':action['slug'],
                  'changedFields':action['changed_fields'],'candidateVersion':version,'actionId':action['action_id']}
        if (row['slug'] != action['slug'] or row['desired_fields'] != action['desired_fields']
            or row['source_package_candidate_version'] != owner['candidate_version']
            or row['source_package_sha256'] != action['candidate_sha256']
            or row['three_field_payload_sha256_canonical_UTF8'] != w.sha256_value(row['desired_fields'])
            or row['requested_issuer_target'] != target or row['actual_issued_target'] != 'NOT_ISSUED'
            or row['phase'] != 'OWNER_METADATA_DECIDED_NOT_REGISTERED_NOT_EXECUTED'
            or req['PUB_full41_raw']['sha256'] not in pub_output):
            raise ValueError('unchanged payload and proposed target provenance required')
        records.append({'action_id':action['action_id'],'record_id':action['record_id'],
                        'candidate_version':version,'payload_sha256':row['three_field_payload_sha256_canonical_UTF8'],
                        'scope':action['physical_scope'],'original_key_effect':'UNKNOWN',
                        'target_issued':False,'actual_action_allowed':False})
    return {'status':'SOURCE_ONLY_NOT_REGISTERED','supplement_sha256':digest,'rows':records,
            'production_READY':False,'permit_issued':False}


STAGE_SCHEMA = 'professional-cms-active-parent-source-stage/v1'
STAGE_EVENT = 'professional_cms_active_parent_source_stage'


def validate_stage(root, source):
    """Validate a pinned source-stage; a successful read never grants a write."""
    import workflow_control as w
    root = Path(root).resolve(strict=True)
    expected = {'schema','parent_task_id','maintenance_task_id','owner_source','owner_native',
                'pub_requests','pub_report','supplement','supplement_native','pub_completed_native','identity_inventory'}
    if not isinstance(source,dict) or set(source) != expected or source['schema'] != STAGE_SCHEMA:
        raise w.WorkflowError('exact source-only active stage schema required')
    parent = w.validate_task_id(source['parent_task_id']); maintenance = w.validate_task_id(source['maintenance_task_id'])
    if parent == maintenance or len(source['pub_requests']) != 2:
        raise w.WorkflowError('distinct existing parent/maintenance and two sources required')
    def path(pin):
        if not isinstance(pin,dict) or set(pin) != {'path','sha256','size'} or w.file_digest(root,pin['path']) != pin:
            raise w.WorkflowError('exact immutable stage input pin required')
        return w.safe_path(root,pin['path'])
    owner_path = path(source['owner_source']); owner_native = path(source['owner_native'])
    requests = [path(x) for x in source['pub_requests']]; report_path = path(source['pub_report'])
    supplement = path(source['supplement']); supp_native = path(source['supplement_native'])
    pub_native = path(source['pub_completed_native']); report = json.loads(report_path.read_bytes())
    inventory = json.loads(path(source['identity_inventory']).read_bytes())
    registry = json.loads((root/'data/department-registry.json').read_text())
    for role in ('paid-growth-data-2','publishing'):
        binding = next(x['chat_binding'] for x in registry['departments'] if x['id'] == role)
        matches = [x for x in inventory.get('threads',[])+inventory.get('pinnedThreads',[]) if x.get('id') == binding['task_id']]
        if (len(matches) != 1 or any(matches[0].get(k) != binding[v] for k,v in
             {'id':'task_id','title':'title','cwd':'cwd','hostId':'host_id','projectId':'project_id'}.items())):
            raise w.WorkflowError('real unique current native role, host and project required')
    snapshot = w.read_json(w.snapshot_path(root,parent)); ms = w.read_json(w.snapshot_path(root,maintenance))
    if not snapshot or not ms or ms.get('current_state') in w.TERMINAL_STATES or report.get('task_id') != parent:
        raise w.WorkflowError('original active parent/maintenance and PUB report required')
    if report.get('status') != 'AUTHENTICATED_FULL41_SOURCE_PREPARED_BINDINGS_NOT_REGISTERED' or report.get('CMS_Save') != 0:
        raise w.WorkflowError('actual original PUB source-only report required')
    report_pins = [x.get('execution_request',{}) for x in report.get('rows',[])]
    # Original PUB files record absolute paths; compare their exact content pin,
    # not a rewritten original report or a fabricated receipt.
    if len(report_pins) != 2 or sorted((x.get('sha256'),x.get('size')) for x in report_pins) != sorted((x['sha256'],x['size']) for x in source['pub_requests']):
        raise w.WorkflowError('one complete original PUB report pin per request required')
    value = validate_supplement(root,owner_path,requests,owner_native,snapshot,supplement,supp_native,pub_native)
    if value['production_READY'] or value['permit_issued'] or len(value['rows']) != 2:
        raise w.WorkflowError('only non-executable source rows may be recorded')
    return {'parent_task_id':parent,'maintenance_task_id':maintenance,'rows':value['rows'],
            'owner_supplement_sha256':value['supplement_sha256'],
            'pub_native_completed':True,'formal_PUB_result_receipt':'NOT_PROVEN',
            'issuer_target':'NOT_ISSUED','production_READY':False,'actual_action_allowed':False,'permit_issued':False}


def stage_catalog(root, maintenance, parent):
    import workflow_control as w
    root = Path(root); results = []
    for event in w.read_jsonl(root/w.WORKFLOW_EVENTS,where={'task_id':maintenance}):
        entry = event.get('details',{}).get(STAGE_EVENT)
        if entry is None or entry.get('parent_task_id') != parent:
            continue
        pin = entry['source']; path = w.safe_path(root,pin['path'])
        if w.file_digest(root,pin['path']) != pin:
            raise w.WorkflowError('registered stage source changed')
        value = validate_stage(root,json.loads(path.read_bytes()))
        if value['maintenance_task_id'] != maintenance or value['parent_task_id'] != parent:
            raise w.WorkflowError('exact original stage parent required')
        results.append({**value,'registration':pin,'event_id':event['event_id']})
    if len(results) > 1:
        raise w.WorkflowError('ambiguous current source stages')
    return results


def register_stage(root, source_path):
    import workflow_control as w
    root = Path(root).resolve(); pin = w.file_digest(root,source_path)
    path = w.safe_path(root,pin['path']); source = json.loads(path.read_bytes())
    value = validate_stage(root,source)
    with w.workflow_lock(root):
        if w.file_digest(root,source_path) != pin:
            raise w.WorkflowError('stage source changed before append')
        value = validate_stage(root,source)
        rows = stage_catalog(root,value['maintenance_task_id'],value['parent_task_id'])
        if rows:
            if rows[0]['registration'] != pin:
                raise w.WorkflowError('different current stage already exists')
            return {'result':'duplicate_ignored',**rows[0]}
        if w.validate_workflow_events(root,value['parent_task_id']) or w.validate_workflow_events(root,value['maintenance_task_id']):
            raise w.WorkflowError('intact original workflow history required')
        action_ids = {x['action_id'] for x in value['rows']}
        for event in w.read_jsonl(root/w.WORKFLOW_EVENTS):
            if any(x in json.dumps(event,ensure_ascii=False) for x in action_ids):
                raise w.WorkflowError('existing action event requires original effect reconciliation')
        for policy in w.read_jsonl(root/w.POLICY_DECISIONS):
            if policy.get('action_id') in action_ids:
                raise w.WorkflowError('existing action policy requires original effect reconciliation')
        state = w.read_json(w.snapshot_path(root,value['maintenance_task_id']))['current_state']
        event = w.append_workflow_event(root,value['maintenance_task_id'],state,
                   {STAGE_EVENT:{'parent_task_id':value['parent_task_id'],'source':pin},'external_permission_issued':False})
    return {'result':'recorded',**value,'registration':pin,'event_id':event['event_id']}


def record_from_parent(root, task_id, input_path):
    import workflow_control as w
    root = Path(root).resolve()
    source = w.read_json(w.safe_path(root,input_path))
    if source.get('schema') != STAGE_SCHEMA or source.get('parent_task_id') != task_id:
        raise w.WorkflowError('exact original parent stage source required')
    return register_stage(root,input_path)


if __name__ == '__main__':
    import argparse
    import workflow_control as w
    parser = argparse.ArgumentParser(description='Source-only active-parent CMS stage; never issues a permit')
    parser.add_argument('command', choices=['check','register','describe','issuer-discovery'])
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--input'); parser.add_argument('--parent-task-id'); parser.add_argument('--maintenance-task-id')
    parser.add_argument('--action-id'); parser.add_argument('--record-id')
    args = parser.parse_args(); root = args.root.resolve()
    try:
        if args.command in {'check','register'}:
            if not args.input: raise w.WorkflowError('pinned stage source input required')
            pin = w.file_digest(root,args.input)
            value = validate_stage(root,json.loads(w.safe_path(root,pin['path']).read_bytes())) if args.command == 'check' else register_stage(root,args.input)
        else:
            rows = stage_catalog(root,args.maintenance_task_id,args.parent_task_id)
            if len(rows) != 1: raise w.WorkflowError('one registered original source stage required')
            matches = [x for x in rows[0]['rows'] if x['action_id'] == args.action_id and x['record_id'] == args.record_id]
            if len(matches) != 1: raise w.WorkflowError('exact action and record required')
            value = {'source_stage_event_id':rows[0]['event_id'],'registration':rows[0]['registration'],
                     'row':matches[0],'formal_PUB_result_receipt':rows[0]['formal_PUB_result_receipt'],
                     'production_READY':False,'permit_issued':False}
            if args.command == 'issuer-discovery':
                import professional_cms_issuer as issuer
                target = issuer.targets(root,task_id=args.parent_task_id).get(matches[0]['candidate_version'])
                if target is not None and (target.get('action_id') != args.action_id or target.get('record_id') != args.record_id):
                    raise w.WorkflowError('issuer candidate collision; exact action and record required')
                value['issuer_target'] = ('LOCAL_SOURCE_ONLY_PENDING' if target and target.get('candidate_shape') == issuer.PENDING_STAGE_MODEL else 'REGISTERED' if target else 'NOT_REGISTERED')
                value['runtime_loaded'] = 'NOT_OBSERVED'
                value['original_key_effect'] = 'UNKNOWN'
        print(json.dumps(value,ensure_ascii=False,indent=2))
    except (w.WorkflowError,ValueError,KeyError,OSError,TypeError) as exc:
        parser.exit(1,str(exc)+'\n')
