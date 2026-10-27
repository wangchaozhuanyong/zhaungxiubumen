"""Append-only professional Ads object sources; no browser or provider writes.

A source is not a permit. The original executor must supply fresh native facts
before the existing normal policy writer can issue one single-action decision.
"""
from pathlib import Path
import argparse
import datetime as dt
import json
import re
from urllib.parse import urlsplit, parse_qs
import workflow_control as w

SCHEMA = 'professional-ads-object-source-registration/v1'
PREFLIGHT = 'professional-ads-object-preflight/v1'
PLAN_SCHEMA = 'professional-ads-plan-object-source-registration/v2'
SUPPLEMENT_SCHEMA = 'professional-ads-plan-supplement-source-registration/v3'
OBJECT_PREFLIGHT = 'professional-ads-planned-object-preflight/v2'
EVENT = 'professional_ads_object_source'
IDENTITY = ('task_id', 'department', 'action_id', 'action_class', 'scope')


def need(value, reason):
    if not value:
        raise w.WorkflowError('professional Ads object: ' + reason)


def doc(root, pin):
    from department_autonomy import document
    return document(root, pin)


def same(left, right, fields=IDENTITY):
    return all(left.get(k) == right.get(k) for k in fields)


def native_identity(root, pin, role):
    from goal_delivery_runtime import _native_document
    from department_autonomy import PROJECT
    page = _native_document(root, pin)
    binding = w.department_registry(root)[role]['chat_binding']
    need(all(page.get('thread', {}).get(k) == binding[v] for k, v in
             {'id': 'task_id', 'title': 'title', 'cwd': 'cwd'}.items())
         and binding.get('project_id') == PROJECT
         and binding.get('cwd') == str(Path(root).resolve()), 'actual fixed professional native identity')
    return page


def source(root, item):
    if item.get('schema') == SUPPLEMENT_SCHEMA:
        return supplement_source(root, item)
    if item.get('schema') == PLAN_SCHEMA:
        return plan_source(root, item)
    import department_autonomy as a
    import goal_delivery_runtime as g
    need(item.get('schema') == SCHEMA and item.get('action_class') == 'ads_write', 'known bounded source schema')
    need(a.current_mode(root) and a.professional(root, item.get('department')), 'current original professional, never an assistant')
    snap = g.restore_goal(root, w.read_json(w.snapshot_path(root, item['task_id'])))
    goal = snap.get('goal_delivery', {})
    need(snap.get('current_state') not in w.TERMINAL_STATES
         and goal.get('primary_owner') == item['department']
         and item['department'] in goal.get('producer_departments', [])
         and item['scope'] in goal.get('authorized_scope', [])
         and snap.get('goal_contract') == item.get('original_goal_contract'), 'unchanged open parent owner/scope/contract')
    a.document(root, snap['goal_contract'])
    a.original_assignment_ready(root, snap, item['department'])
    need(not w.validate_workflow_events(root, item['task_id']), 'intact original event chain')
    packet = doc(root, item['packet'])
    request = doc(root, packet['request'])
    intent = doc(root, packet['intent'])
    coord = doc(root, item['coordination_source'])
    plan = doc(root, coord['exact_professional_plan'])
    need(same(item, packet) and same(item, request) and same(item, intent)
         and same(item, plan, ('task_id', 'department', 'action_class', 'scope', 'source_project_id')),
         'exact original packet/request/intent/plan identity')
    need(coord.get('schema') == 'HQ-exact-existing-human-promotion-source-coordination/v1'
         and coord.get('task_id') == item['task_id'] and coord.get('scope') == item['scope']
         and coord.get('professional_owner') == item['department']
         and packet['original_plan_unchanged'] == coord['exact_professional_plan'], 'unchanged actual bounded coordination and plan')
    page = native_identity(root, coord['actual_original_human_native'], item['department'])
    sources = request['sources']
    original = [(t, m) for t in page.get('turns', []) if t.get('id') == sources['original_owner_turn_id']
                for m in t.get('items', []) if m.get('id') == sources['original_owner_message_id']]
    continued = [(t, m) for t in page.get('turns', []) if t.get('id') == sources['completed_continuation_turn']
                 for m in t.get('items', []) if m.get('id') == sources['continuation_human_message_id']]
    need(len(original) == len(continued) == 1, 'actual original human and subsequent continuation')
    ot, om = original[0]; ct, cm = continued[0]
    need(om.get('type') == cm.get('type') == 'userMessage'
         and coord.get('human_message_id') == om['id']
         and any(c.get('type') == 'text' and str(c.get('text', '')).strip() for c in om.get('content', []))
         and ''.join(c.get('text', '') for c in cm.get('content', [])).strip() == '继续'
         and ct.get('status') == 'completed' and not ct.get('error')
         and type(ot.get('startedAt')) in {int, float}
         and type(ct.get('startedAt')) in {int, float} and ot['startedAt'] < ct['startedAt'],
         'genuine ordered human instruction; failed original turn is not rewritten')
    professional = native_identity(root, item['professional_native'], item['department'])
    completed = [t for t in professional.get('turns', []) if t.get('status') == 'completed' and not t.get('error')
                 and any(m.get('type') == 'agentMessage' and m.get('phase') == 'final_answer'
                         and packet['request']['path'] in m.get('text', '') for m in t.get('items', []))]
    need(len(completed) == 1 and completed[0].get('startedAt', 0) >= ct['startedAt'], 'actual completed original professional request')
    need(request.get('operation') == 'create_ad_group_only' and intent.get('operation') == request['operation']
         and request.get('actual_action_allowed') is False and request.get('non_executable_readonly_preparation') is True,
         'group-only preparation, never a draft/inspection permit or an ad write')
    selected = [x for x in plan.get('items', []) if x.get('group_name') == request['logical_object']['name'] and x.get('group_new') is True]
    need(len(selected) == 1 and request['logical_object'].get('future_platform_object_id') is None,
         'one missing planned logical group; no manufactured platform ID')
    operation_map = doc(root, coord['exact_logical_operation_map'])
    mapped = [x for x in operation_map.get('operation_map', [])
              if x.get('group_name') == request['logical_object']['name']]
    need(len(mapped) == 1 and mapped[0].get('operation') == 'create_group_then_ad', 'exact original mapped group substep, ad excluded')
    labels = request['desired'].get('native_field_labels', {})
    defaults = request['desired'].get('retain_observed_native_defaults', {})
    need(set(labels) == {'Parent Campaign', 'Ad group name', 'Context hints (optional)'}
         and labels['Ad group name'] == selected[0]['group_name']
         and labels['Context hints (optional)'] == selected[0]['context_hints']
         and defaults == {'Bid strategy': 'Autobid', 'Manual: Max CPC': False, 'Tracking parameters': ''}
         and request['desired'] == intent['desired'], 'only planned group name/hints, native Autobid and blank tracking')
    need(request['account_id'] == intent['account_id'] == plan['account_id'] == coord['bounds']['account_id']
         and request['parent_campaign_id'] == intent['parent_campaign_id'] == plan['campaign_id']
         and labels['Parent Campaign'] == intent['parent_campaign_name'], 'exact account and original parent campaign')
    bounds = intent['bounds']; end = w._parse_observed_at(plan['end_MYT'])
    need(bounds['shared_average_MYR_day'] == plan['budget_shared_average_MYR_day'] == coord['bounds']['shared_average_MYR_day']
         and bounds['paid_end_MYT'] == plan['end_MYT'] == coord['bounds']['end_MYT']
         and bounds['parent_geo'] == plan['geo'] and plan['creative_enhancement'] == 'Off inherited; do not alter campaign'
         and end is not None and dt.datetime.now(dt.timezone.utc) < end,
         'unchanged shared budget/end/geography/enhancement; no extension or new fee')
    for name in ('facts', 'selfcheck', 'backup', 'recovery'):
        doc(root, packet[name])
    need(packet['facts'] == request['facts'] and packet['selfcheck'] == request['self_check']
         and packet['backup'] == request['backup'] and packet['recovery'] == request['recovery'], 'original evidence mapping')
    return {'snapshot': snap, 'packet': packet, 'request': request, 'intent': intent, 'plan': plan,
            'authorization': coord['actual_original_human_native'], 'coordination': coord}


def record(root, task, input_path):
    pin = w.file_digest(root, input_path); item = doc(root, pin)
    need(item.get('task_id') == task, 'original task')
    with w.workflow_lock(root):
        context = source(root, item)
        events = [e for e in w.read_jsonl(Path(root) / w.WORKFLOW_EVENTS)
                  if e.get('task_id') == task and e.get('details', {}).get(EVENT)]
        matches = [e for e in events if same(doc(root, e['details'][EVENT]), item)]
        if matches:
            need(len(matches) == 1 and matches[0]['details'][EVENT] == pin, 'preserve exact source; no replacement')
            return {'result': 'duplicate_ignored', 'source_event_id': matches[0]['event_id'], 'source_registration': pin, 'external_permission_issued': False}, []
        event = w.append_workflow_event(root, task, context['snapshot']['current_state'],
                                       {EVENT: pin, 'original_contract_unchanged': True, 'external_permission_issued': False})
    return {'result': 'recorded', 'source_event_id': event['event_id'], 'source_registration': pin, 'external_permission_issued': False}, [Path(root) / w.WORKFLOW_EVENTS]


def match(root, snapshot, requested):
    if requested.get('action_class') != 'ads_write':
        return None
    events = [e for e in w.read_jsonl(Path(root) / w.WORKFLOW_EVENTS)
              if e.get('task_id') == snapshot.get('task_id') and e.get('details', {}).get(EVENT)]
    rows = [(e, doc(root, e['details'][EVENT])) for e in events]
    exact_old = [(e,x) for e,x in rows if x.get('schema') not in {PLAN_SCHEMA,SUPPLEMENT_SCHEMA} and same(x,requested)]
    if exact_old:
        need(len(exact_old)==1,'one immutable original object source')
        event,item=exact_old[0]
        return {**source(root,item),'registration':event['details'][EVENT],'source_event_id':event['event_id']}
    selected = []
    for event, item in rows:
        if item.get('schema') in {PLAN_SCHEMA,SUPPLEMENT_SCHEMA}:
            context = source(root, item)
            specs = operation_specs(root, context)
            spec = specs.get(requested.get('action_id'))
            if spec and same(spec, requested):
                selected.append((event, item, context, spec))
        elif same(item, requested):
            selected.append((event, item, None, None))
    rows = selected
    if not rows:
        return None
    need(len(rows) == 1, 'one immutable registered action')
    event, item, result, spec = rows[0]
    result = result or source(root, item)
    if spec:
        result = {**result, 'plan_objects': True, 'object_spec': spec}
    return {**result, 'registration': event['details'][EVENT], 'source_event_id': event['event_id']}


def checked_preflight(root, item, registered, *, fresh=True):
    if registered.get('plan_objects'):
        return planned_preflight(root, item, registered, fresh=fresh)
    need(item.get('schema') == PREFLIGHT and same(item, registered['request'])
         and item.get('source_registration') == registered['registration'], 'exact current registered preflight')
    req = doc(root, item['request']); original = registered['request']
    stable = ('task_id', 'scope', 'department', 'action_id', 'action_class', 'source_project_id',
              'operation', 'account_id', 'parent_campaign_id', 'logical_object', 'desired', 'sources', 'intent')
    need(same(req, original, stable), 'fresh observation cannot change original intent or source')
    facts = doc(root, req['facts']); check = doc(root, req['self_check'])
    backup = doc(root, req['backup']); recovery = doc(root, req['recovery'])
    for value in (facts, check, backup, recovery):
        need(same(value, req, ('task_id', 'department', 'action_id', 'action_class', 'source_project_id'))
             and value.get('intent') == original['intent'], 'same object facts/selfcheck/backup/recovery')
    need(check.get('passed') is True and check.get('facts') == req['facts']
         and check.get('checks') and all(v is True for v in check['checks'].values()), 'actual professional object selfcheck')
    at = w._parse_observed_at(req.get('observed_at')); now = dt.datetime.now(dt.timezone.utc)
    need(at is not None and (not fresh or 0 <= (now - at).total_seconds() <= 300), 'fresh execution facts, not expired preparation')
    channel = facts['channel']; url = urlsplit(channel['account_url'])
    from chatgpt_fe689_draft_admission import BROWSER_PROFILE, BROWSER_EXTENSION
    need(channel.get('profile') == BROWSER_PROFILE and channel.get('stable_extension') == BROWSER_EXTENSION
         and url.scheme == 'https' and url.netloc == 'ads.openai.com'
         and parse_qs(url.query).get('act') == [req['account_id']]
         and channel.get('runtime_browser') and channel.get('runtime_tab'), 'actual stable original browser/account; handles may change')
    inventory = doc(root, facts.get('native_inventory'))
    browser = inventory.get('channel', {}); tabs = inventory.get('ads_tabs', [])
    need(browser.get('family') == 'chrome' and browser.get('type') == 'extension'
         and browser.get('profileName') == BROWSER_PROFILE
         and browser.get('metadata', {}).get('extensionInstanceId') == BROWSER_EXTENSION
         and browser.get('id') == channel['runtime_browser']
         and len([t for t in tabs if t.get('id') == channel['runtime_tab']
                  and t.get('browserId') == browser.get('id') and t.get('url') == channel['account_url']]) == 1,
         'one exact current native Chrome profile/extension/tab inventory')
    inventory_at = w._parse_observed_at(inventory.get('at'))
    need(inventory_at is not None and at is not None and abs((inventory_at-at).total_seconds()) <= 300,
         'current native inventory chronology')
    need(facts.get('observed_at') == req['observed_at'], 'same fresh observation timestamp')
    parent = facts.get('native_parent', {})
    need(parent.get('business_id') == req['parent_campaign_id']
         and parent.get('name') == req['desired']['native_field_labels']['Parent Campaign'], 'same actual original parent campaign option')
    parent_pin = parent.get('proof')
    need(isinstance(parent_pin, dict) and w.file_digest(root, parent_pin.get('path', '')) == parent_pin
         and req['parent_campaign_id'] in w.safe_path(root, parent_pin['path']).read_text(), 'current native parent option evidence')
    rows = facts['actual_current_lists']; names = rows['group_names']; target = req['logical_object']['name']
    need(isinstance(names, list) and len(names) == len(set(names)) and target not in names
         and len(names) == registered['plan']['preserve_existing']['groups']
         and rows.get('ads_count') == registered['plan']['preserve_existing']['ads']
         and rows.get('list_completeness'), 'complete current absence and original entity preservation')
    evidence = facts.get('raw_evidence')
    need(isinstance(evidence, list) and evidence, 'actual current native evidence')
    for p in evidence:
        need(w.file_digest(root, p['path']) == p, 'current native evidence bytes')
    original_facts = doc(root, registered['packet']['facts'])
    def protected_table(values, columns):
        need(isinstance(values, list) and len(values) > 1 and all(k in values[0] for k in columns), 'native table columns')
        indexes = [values[0].index(k) for k in columns]
        return sorted(tuple(str(row[i]) for i in indexes) for row in values[1:])
    for name, columns in (('actual-groups-rows.json', ('Active', 'Name', 'Campaign name', 'Status', 'Context Hints', 'Bid strategy')),
                          ('actual-existing-ads-rows.json', ('Active', 'Ad', 'Status', 'URL', 'Campaign name', 'Ad group'))):
        before = [p for p in original_facts['raw_evidence'] if Path(p['path']).name == name]
        current = [p for p in evidence if Path(p['path']).name == name]
        need(len(before) == len(current) == 1, 'original and current complete native object tables')
        need(w.file_digest(root, before[0]['path']) == before[0], 'unchanged original native table bytes')
        need(protected_table(json.loads(w.safe_path(root, before[0]['path']).read_text()), columns)
             == protected_table(json.loads(w.safe_path(root, current[0]['path']).read_text()), columns),
             'preserve every original group/ad content, parent and state; statistics may change')
    defaults = facts['actual_form_defaults']
    need(defaults.get('Autobid') is True and defaults.get('Manual: Max CPC') is False
         and all(defaults.get(k) == '' for k in ('Ad group name', 'Context hints (optional)', 'Tracking parameters')),
         'exact new empty form/defaults; no parent settings writes')
    need(recovery.get('permits_issued_or_consumed', 0) == 0, 'recovery source cannot issue an inverse grant')
    return req


def record_preflight(root, task, input_path):
    pin = w.file_digest(root, input_path); item = doc(root, pin)
    snapshot = w.read_json(w.snapshot_path(root, task)); registered = match(root, snapshot, item)
    need(registered is not None, 'registered original source first')
    checked_preflight(root, item, registered)
    with w.workflow_lock(root):
        # Never refresh after an issued/uncertain action by adding another observation.
        key = w.sha256_value([item[k] for k in IDENTITY])
        need(not any(p.get('autonomous_action_key') == key and p.get('status') == 'allow'
                     for p in w.read_jsonl(Path(root) / w.POLICY_DECISIONS)), 'existing issued/unknown effect must be read, not retried')
        prior = [e for e in w.read_jsonl(Path(root) / w.WORKFLOW_EVENTS) if e.get('task_id') == task
                 and e.get('details', {}).get('professional_ads_object_preflight') == pin]
        if prior:
            return {'result': 'duplicate_ignored', 'event_id': prior[0]['event_id'], 'external_permission_issued': False}, []
        event = w.append_workflow_event(root, task, snapshot['current_state'], {'professional_ads_object_preflight': pin,
                                       'source_registration': registered['registration'], 'external_permission_issued': False})
    return {'result': 'recorded', 'event_id': event['event_id'], 'external_permission_issued': False}, [Path(root) / w.WORKFLOW_EVENTS]


def execution_context(root, snapshot, requested):
    registered = match(root, snapshot, requested)
    if registered is None:
        return None
    events = [e for e in w.read_jsonl(Path(root) / w.WORKFLOW_EVENTS) if e.get('task_id') == snapshot['task_id']
              and e.get('details', {}).get('source_registration') == registered['registration']
              and e.get('details', {}).get('professional_ads_object_preflight')
              and same(doc(root, e['details']['professional_ads_object_preflight']), requested)]
    need(events, 'original professional fresh object preflight required; source registration is not permission')
    item = doc(root, events[-1]['details']['professional_ads_object_preflight'])
    req = checked_preflight(root, item, registered)
    need(requested.get('payload_sha256', item['request']['sha256']) == item['request']['sha256'], 'exact fresh request SHA')
    return {'action': {k: req[k] for k in IDENTITY}, 'request': req, 'pin': item['request'],
            'authorization': registered.get('authority70', registered['authorization']), 'department': req['department'],
            'preflight': item, 'source_registration': registered['registration']}


def reserve(root, item, decision_id):
    import department_autonomy as a
    snapshot = w.read_json(w.snapshot_path(root, item['task_id']))
    context = execution_context(root, snapshot, item)
    need(context is not None, 'current object context')
    key = w.sha256_value([item[k] for k in IDENTITY])
    path = Path(root) / 'logs/professional-ads-object-attempts' / (key + '.jsonl')
    with w.workflow_lock(root):
        decisions = [d for d in w.read_jsonl(Path(root) / w.POLICY_DECISIONS) if d.get('decision_id') == decision_id]
        need(len(decisions) == 1 and decisions[0].get('status') == 'allow'
             and decisions[0].get('autonomous_action_key') == key
             and decisions[0].get('mode_authorization') == a.OWNER
             and decisions[0].get('exact_request') == context['pin'], 'one exact newly issued normal single-use policy')
        need(not path.exists(), 'prior reserved/unknown/completed effect cannot be replayed')
        row = {'state': 'reserved_before_native_effect', 'at': w.utc_timestamp(), **{k: item[k] for k in IDENTITY},
               'policy_decision_id': decision_id, 'request': context['pin'], 'source_registration': context['source_registration'],
               'actual_provider_effect_claimed': False, 'unknown_effect_requires_readback_no_retry': True}
        w.append_jsonl_locked(path, row)
    return row


def plan_source(root, item):
    """One real plan and new human budget source; no per-object HQ approval."""
    anchor = doc(root, item['original_object_source'])
    need(anchor.get('schema') == SCHEMA, 'original already-adopted object source, not a source cycle')
    base = source(root, anchor)
    need(same(item, anchor, ('task_id', 'department', 'action_class', 'scope', 'source_project_id'))
         and item.get('original_goal_contract') == anchor['original_goal_contract'], 'same original owner/contract/scope/project')
    anchor_events = [e for e in w.read_jsonl(Path(root) / w.WORKFLOW_EVENTS)
                     if e.get('task_id') == item['task_id'] and e.get('details', {}).get(EVENT) == item['original_object_source']]
    need(len(anchor_events) == 1 and anchor_events[0]['event_id'] == item['original_object_source_event_id'],
         'one real original source event; no new task or rewritten dispatch')
    budget = doc(root, item['new_human_budget_source'])
    need(budget.get('schema') == 'HQ-actual-new-original-human-budget-source/v1'
         and budget.get('task_id') == item['task_id'] and budget.get('scope') == item['scope'], 'exact current human budget relation')
    page = native_identity(root, budget['actual_human_native'], item['department'])
    pairs = [(t,m) for t in page.get('turns', []) if t.get('id') == budget.get('source_turn')
             for m in t.get('items', []) if m.get('id') == budget.get('actual_human_message')]
    need(len(pairs) == 1 and pairs[0][1].get('type') == 'userMessage', 'real owner message, not an assistant/coordination assertion')
    turn, message = pairs[0]
    text = ''.join(c.get('text','') for c in message.get('content', []) if c.get('type') == 'text')
    import hashlib
    amounts = re.findall(r'我现在把预算提高到([0-9]+(?:\.[0-9]+)?)一天\s*$', text)
    need(len(amounts) == 1 and hashlib.sha256(text.encode()).hexdigest() == budget.get('actual_human_UTF8_SHA256')
         and budget.get('specific_new_instruction') in text
         and float(amounts[0]) == budget.get('authorized_new_shared_average_MYR_per_day')
         and type(turn.get('startedAt')) in {int,float}
         and turn['startedAt'] <= dt.datetime.now(dt.timezone.utc).timestamp(), 'exact actual human daily-budget words/hash/time')
    plan = base['plan']; limit = budget['authorized_new_shared_average_MYR_per_day']
    need(type(limit) in {int,float} and plan['budget_shared_average_MYR_day'] < limit
         and budget.get('account_id') == plan['account_id']
         and budget.get('single_existing_campaign') == plan['campaign_id']
         and budget.get('original_end_MYT_retained') == plan['end_MYT'], 'shared original campaign only; no account, deadline or per-ad fee expansion')
    need(item.get('action_id') == plan['action_id'] + '-object-sources-v2', 'original batch source identity')
    budget_request = doc(root, item['original_budget_request'])
    delta = doc(root, item['remaining_object_delta'])
    need(same(budget_request, item, ('task_id','scope','department','source_project_id','action_class'))
         and same(delta, item, ('task_id','scope','department','source_project_id','action_class'))
         and budget_request.get('account_id') == delta.get('account_id') == plan['account_id']
         and budget_request.get('campaign_id') == delta.get('campaign_id') == plan['campaign_id']
         and budget_request.get('human_message_id') == delta.get('actual_human_message_id') == message['id']
         and delta.get('original_plan_unchanged') == base['coordination']['exact_professional_plan']
         and delta.get('budget_only_request') == item['original_budget_request'],
         'real original owner budget request and unchanged plan delta identity/source')
    need(budget_request.get('operation') == 'set_existing_campaign_daily_budget_only'
         and budget_request.get('actual_action_allowed') is False
         and budget_request.get('non_executable_readonly_preparation') is True
         and budget_request.get('before',{}).get('amount') == plan['budget_shared_average_MYR_day']
         and budget_request['before'].get('currency') == 'MYR'
         and budget_request['before'].get('budget_type') == 'Daily budget'
         and budget_request.get('desired') == {'budget_type':'Daily budget','currency':'MYR','amount':limit}
         and budget_request.get('protect',{}).get('end_MYT') == plan['end_MYT']
         and budget_request['protect'].get('geo') == plan['geo'],
         'separate original before35/after70 daily-only request; original deadline/geography')
    need(re.fullmatch(r'chatgpt-set-campaign-daily-budget'+str(limit)+r'-20[0-9]{6}-v1',budget_request.get('action_id','')),
         'one bounded original budget action')
    for pin in (budget_request['human_source'], budget_request['before']['source'], budget_request['before']['DOM_source']):
        doc_value = w.file_digest(root,pin['path'])
        need(doc_value == pin,'original budget request native pins')

    whole = doc(root, item['actual_original_group_result'])
    result = doc(root, whole['actual_result'])
    need(whole.get('state') == 'ONE_GROUP_CREATED_AND_NATIVE_READBACK_PASSED'
         and whole.get('task_id') == item['task_id'] and whole.get('scope') == item['scope']
         and result.get('task_id') == item['task_id'] and result.get('account_id') == plan['account_id']
         and result.get('parent_campaign_id') == plan['campaign_id']
         and result.get('source_event') == anchor_events[0]['event_id']
         and result.get('new_group_id') == whole.get('new_group_id')
         and re.fullmatch(r'adgrp_[A-Za-z0-9_-]+', str(result.get('new_group_id',''))), 'real existing created group result, never create it again')
    identity = {k:anchor[k] for k in IDENTITY}; key = w.sha256_value(list(identity.values()))
    policies = [p for p in w.read_jsonl(Path(root) / w.POLICY_DECISIONS)
                if p.get('decision_id') == result.get('normal_policy_decision_id')]
    attempts = w.read_jsonl(Path(root) / 'logs/professional-ads-object-attempts' / (key + '.jsonl'))
    need(len(policies) == 1 and policies[0].get('status') == 'allow' and policies[0].get('autonomous_action_key') == key
         and same(policies[0], anchor) and len(attempts) == 1
         and attempts[0].get('policy_decision_id') == policies[0]['decision_id'], 'original consumed group-only policy/reservation retained')
    next_ad = doc(root, item['original_next_ad_input'])
    selected = [x for x in plan['items'] if x['group_name'] == result['new_group_name']]
    need(len(selected) == 1 and next_ad.get('source_plan') == base['coordination']['exact_professional_plan']
         and next_ad.get('parent_group_id') == result['new_group_id']
         and next_ad.get('actual_parent_created_result') == whole['actual_result'], 'same planned next ad and actual parent')
    selected_item=selected[0]
    need(next_ad.get('desired_UI_labels')=={
        'Parent Campaign':base['intent']['parent_campaign_name'],'Parent Ad Group':selected_item['group_name'],
        'Ad Name':selected_item['ad_name'],'Title':selected_item['title'],'Description':selected_item['body'],
        'Link':selected_item['url'],'Tracking parameters':selected_item['tracking'],'Image':selected_item['image']},
        'unchanged original next-ad copy/link/tracking/image; no unrelated candidate')
    group_option = next_ad['current_parent_option_source']
    need(w.file_digest(root, group_option['path']) == group_option
         and ('Value: '+result['new_group_name']+', ID: select-option-'+result['new_group_id'])
             in w.safe_path(root,group_option['path']).read_text(), 'real original group option/source')
    return {**base, 'source_item': item, 'budget_source': budget, 'budget_limit': limit,
            'authority70': budget['actual_human_native'], 'budget_request':budget_request,
            'known_groups': {selected[0]['key']: result['new_group_id']}, 'next_ad': next_ad}


def supplement_source(root, item):
    """Authenticate a new professional supplement; keep every prior map/action intact."""
    parent_item = doc(root, item['original_plan_source'])
    need(parent_item.get('schema') == PLAN_SCHEMA, 'one original authenticated plan source')
    base = plan_source(root, parent_item)
    need(same(item,parent_item,('task_id','department','action_class','scope','source_project_id','original_goal_contract')),
         'same original professional task/scope/project/contract')
    events = [e for e in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS)
              if e.get('task_id') == item['task_id'] and e.get('details',{}).get(EVENT) == item['original_plan_source']]
    need(len(events) == 1 and events[0]['event_id'] == item.get('original_plan_source_event_id'), 'actual immutable parent source event')
    plan = doc(root,item['supplement_plan']); original = base['plan']
    need(same(plan,item,('task_id','department','action_class','scope','source_project_id'))
         and plan.get('account_id') == original['account_id'] and plan.get('campaign_id') == original['campaign_id']
         and plan.get('original_plan_unchanged') == base['coordination']['exact_professional_plan']
         and plan.get('budget_shared_average_MYR_day') == base['budget_limit']
         and all(plan.get(k) == original[k] for k in ('end_MYT','geo','bid','creative_enhancement'))
         and item.get('action_id') == plan.get('action_id','')+'-object-sources-v3'
         and plan.get('actual_action_allowed') is False, 'same paid bounds and original plan; source is never a permit')
    page = native_identity(root,item['professional_native'],item['department'])
    def human(message_id):
        rows=[(t,m)for t in page.get('turns',[])for m in t.get('items',[])if m.get('id')==message_id]
        need(len(rows)==1 and rows[0][1].get('type')=='userMessage','one real original human, not an assistant assertion')
        turn,message=rows[0];text=''.join(c.get('text','')for c in message.get('content',[])if c.get('type')=='text')
        need(text.strip() and type(turn.get('startedAt'))in {int,float} and turn['startedAt']<=dt.datetime.now(dt.timezone.utc).timestamp(),'actual human words/time')
        return turn,message,text
    ht,hm,words=human(item['actual_human_message_id']);st,sm,services=human(item['specific_service_human_message_id'])
    declared=doc(root,plan['human_source'])
    need(plan.get('human_message_id')==hm['id']and declared.get('message')==hm
         and declared.get('turn',{}).get('id')==ht['id']and declared['turn'].get('status')==ht.get('status')
         and all(declared.get('thread',{}).get(k)==page['thread'].get(k)for k in ('id','title','cwd'))
         and st['startedAt']<=ht['startedAt'],'same frozen human observation; interrupted original is retained')
    pairs=[(t,m)for t in page.get('turns',[])for m in t.get('items',[])if m.get('id')==item.get('professional_plan_command_id')]
    need(len(pairs)==1,'one original professional plan production command')
    turn,command=pairs[0]
    need(turn.get('status')=='completed'and not turn.get('error')and turn.get('startedAt',0)>=ht['startedAt']
         and any(m.get('type')=='agentMessage'and m.get('phase')=='final_answer'and m.get('text','').strip()for m in turn.get('items',[]))
         and command.get('type')=='commandExecution'and command.get('status')=='completed'and command.get('exitCode')==0
         and command.get('cwd')==str(Path(root).resolve()),'actual completed professional result after human source')
    native=json.loads(w._completion_execution_output(command))
    need(native.get('supplement')==item['supplement_plan'],'real untruncated command binds exact complete plan bytes')
    rows=plan.get('items');terms=item.get('service_source_terms');assets=doc(root,item['asset_manifest'])
    need(isinstance(rows,list)and rows and isinstance(terms,dict)and len(terms)==len(rows)
         and set(terms)=={r.get('key')for r in rows}and len({r.get('group_name')for r in rows})==len(rows)
         and not(set(terms)&{r['key']for r in original['items']})
         and not({r.get('group_name')for r in rows}&{r['group_name']for r in original['items']}),'unique genuinely additional items, never overwrite or recreate original objects')
    need(plan.get('additions')=={'new_groups':len(rows),'new_ads':len(rows),'context_hints':4*len(rows),'new_reference_images':len(rows)},'complete exact supplement counts')
    landing=doc(root,plan['landing_readback']);original_host=urlsplit(original['items'][0]['url']).netloc
    for row in rows:
        term=terms[row['key']];image=row.get('image',{});url=urlsplit(row.get('url',''))
        need(isinstance(term,str)and len(term)>=2 and term in services and term in row.get('service','')
             and row.get('group_new')is True and row.get('actual_platform_id')is None
             and isinstance(row.get('title'),str)and 0<len(row['title'])<=32
             and isinstance(row.get('body'),str)and 0<len(row['body'])<=54
             and isinstance(row.get('context_hints'),list)and len(row['context_hints'])==4
             and all(isinstance(h,str)and h.strip()for h in row['context_hints'])
             and url.scheme=='https'and url.netloc==original_host and not url.username and not url.password,
             'actual requested service and finite original fields; no invented platform ID or substitute account/site')
        if url.path.endswith('/quote'):
            need(row['url'] in json.dumps(landing,ensure_ascii=False),'actual readback of the unchanged quote entry')
        image_path=Path(image.get('local_path',''));need(image_path.resolve().is_relative_to(Path(root).resolve()),'same project image')
        matches=[x for x in assets.get('assets',[])if x.get('key')==row['key']and x.get('path')==str(image_path.relative_to(root))]
        need(len(matches)==1 and matches[0].get('sha256')==image.get('sha256')and matches[0].get('bytes')==image.get('size'), 'real exact asset provenance; no upload claim')
    result={**base,'plan':plan,'source_item':item,'known_groups':{},'supplement_only':True,
            'supplement_human_native':item['professional_native'],'unchanged_parent_source':item['original_plan_source']}
    new_specs=operation_specs(root,result)
    need(not(set(new_specs)&set(operation_specs(root,base))),'new actions cannot collide with original policy/attempt keys')
    return result


def operation_specs(root, context):
    """Derive only the unchanged approved map; never accept caller desire labels."""
    plan = context['plan']; fields = {k:plan[k] for k in ('task_id','department','action_class','scope','source_project_id')}
    days = re.findall(r'20\d{6}', plan['action_id']); need(len(days) == 1, 'original plan action date')
    day = days[0]; result = {}; image_keys = {}
    campaign_name = context['intent']['parent_campaign_name']
    for item in plan['items']:
        key = item['key']; need(re.fullmatch(r'[a-z][a-z0-9_-]*',key), 'stable logical plan key')
        group = item['group_name']
        base = {**fields, 'account_id':plan['account_id'], 'parent_campaign_id':plan['campaign_id'],
                'object_key':key, 'parent_group_name':group}
        if item.get('group_new') and key not in context['known_groups']:
            spec = {**base,'action_id':f'chatgpt-create-{key}-adgroup-{day}-v1','operation':'create_ad_group_only',
                    'desired':{'Parent Campaign':campaign_name,'Ad group name':group,'Context hints (optional)':item['context_hints'],
                               'Bid strategy':'Autobid','Tracking parameters':''}}
            result[spec['action_id']] = spec
        image = item.get('image')
        if image:
            path = Path(image['local_path']); need(path.resolve().is_relative_to(Path(root).resolve()) and not path.is_symlink(), 'project-owned original image')
            need(w.file_digest(root,str(path.relative_to(root))) == {'path':str(path.relative_to(root)), 'sha256':image['sha256'],'size':image['size']}, 'unchanged approved image bytes')
            image_keys.setdefault(image['sha256'],key)
            canonical = image_keys[image['sha256']]
            if key == canonical:
                spec = {**base,'action_id':f'chatgpt-upload-{key}-reference-image-{day}-v1','operation':'upload_reference_image',
                        'desired':{'Image':image},'upload_key':canonical}
                result[spec['action_id']] = spec
        spec = {**base,'action_id':f'chatgpt-create-{key}-ad-{day}-v1','operation':'create_ad_only',
                'desired':{'Parent Campaign':campaign_name,'Parent Ad Group':group,'Ad Name':item['ad_name'],
                           'Title':item['title'],'Description':item['body'],'Link':item['url'],
                           'Tracking parameters':item['tracking'],'Image':image},
                'upload_key':image_keys[image['sha256']] if image else None}
        result[spec['action_id']] = spec
    if context.get('supplement_only'):
        return result
    spec = {**fields,'account_id':plan['account_id'],'parent_campaign_id':plan['campaign_id'],
            'object_key':'shared_budget','action_id':context['budget_request']['action_id'],
            'operation':'set_shared_daily_budget','desired':{'currency':'MYR','budget_kind':'average_daily',
             'value':context['budget_limit'],'original_paid_end_retained':plan['end_MYT']}}
    result[spec['action_id']] = spec
    return result


def _native_table(root, pin):
    need(isinstance(pin,dict) and w.file_digest(root,pin.get('path','')) == pin, 'exact native table pin')
    value = json.loads(w.safe_path(root,pin['path']).read_text())
    need(isinstance(value,list) and len(value)>1 and isinstance(value[0],list), 'complete native table')
    return value


def _protected_rows(root, original, current, columns):
    before = _native_table(root,original); after = _native_table(root,current)
    need(all(k in before[0] and k in after[0] for k in columns), 'supported protected native columns')
    left = [tuple(str(row[before[0].index(k)]) for k in columns) for row in before[1:]]
    right = [tuple(str(row[after[0].index(k)]) for k in columns) for row in after[1:]]
    need(all(right.count(row) == left.count(row) for row in left), 'original objects/content/state protected; newly added planned rows may coexist')
    return after


def _exact_created_row(root, original, current, spec):
    """Attribute the one fresh delta to this action, never another planned row."""
    from collections import Counter
    operation=spec['operation']
    if operation=='create_ad_group_only':
        columns=('Name','Campaign name','Context Hints','Bid strategy')
        expected={'Name':spec['desired']['Ad group name'],'Campaign name':spec['desired']['Parent Campaign'],
                  'Context Hints':spec['desired']['Context hints (optional)'],'Bid strategy':spec['desired']['Bid strategy']}
    else:
        need(operation=='create_ad_only','only an exact create action has a new object row')
        columns=('Ad','URL','Campaign name','Ad group')
        expected={'Ad':spec['desired']['Ad Name'],'URL':spec['desired']['Link'],
                  'Campaign name':spec['desired']['Parent Campaign'],'Ad group':spec['parent_group_name']}
    before=_native_table(root,original);after=_native_table(root,current)
    need(all(k in before[0]and k in after[0]for k in columns),'complete supported created-row fields')
    def project(rows):return Counter(tuple(str(row[rows[0].index(k)])for k in columns)for row in rows[1:])
    left,right=project(before),project(after)
    need(not(left-right)and sum((right-left).values())==1 and right-left==Counter({tuple(str(expected[k])for k in columns):1}),
         'one fresh row must belong to this exact reserved object; no foreign/planned-peer delta')
    return {'operation':operation,'exact_created_fields':expected,'only_one_new_row':True}


def _protected_groups_after_child(root, original, current, request, spec):
    """Only the new child's exact parent may gain a derived serving status."""
    columns=('Active','Name','Campaign name','Status','Context Hints','Billing Event','Bid strategy')
    before=_native_table(root,original);after=_native_table(root,current)
    need(all(k in before[0]and k in after[0]for k in columns),'complete protected group columns')
    name=spec['parent_group_name'];campaign=spec['desired']['Parent Campaign']
    def selected(rows):return [r for r in rows[1:]if r[rows[0].index('Name')]==name and r[rows[0].index('Campaign name')]==campaign]
    left,right=selected(before),selected(after)
    need(len(left)==len(right)==1 and request.get('parent_group_id'),'one exact original target parent')
    prior={k:left[0][before[0].index(k)]for k in columns};latest={k:right[0][after[0].index(k)]for k in columns}
    need(all(latest[k]==prior[k]for k in columns if k!='Status'),'parent content, active switch, campaign/hints/bid remain unchanged')
    need(latest['Status']==prior['Status']or prior['Status']=='Not serving'and latest['Status']in {'In review','Pending review','Under review','Serving'},'only attributable parent review/serving transition after own new child')
    def projection(rows,normalize=False):
        values=[]
        for r in rows[1:]:
            row={k:r[rows[0].index(k)]for k in columns}
            if normalize and row['Name']==name and row['Campaign name']==campaign:row['Status']=prior['Status']
            values.append(tuple(str(row[k])for k in columns))
        return values
    left_values=projection(before);right_values=projection(after,True)
    need(len(left_values)==len(right_values)and all(right_values.count(x)==left_values.count(x)for x in left_values),'all other groups and fields remain exact')
    return after


def _budget_projection(root, projection, expected):
    need(isinstance(projection,dict) and projection.get('currency')=='MYR'
         and projection.get('budget_kind')=='average_daily' and projection.get('value') in expected,
         'actual saved shared MYR daily value, not total budget or an unsaved wizard')
    pin = projection.get('native_source'); need(isinstance(pin,dict) and w.file_digest(root,pin.get('path',''))==pin, 'actual visible saved budget source')
    raw = w.safe_path(root,pin['path']).read_text(); value_text=projection.get('value_text');kind_text=projection.get('kind_text')
    need(isinstance(value_text,str) and value_text in raw and isinstance(kind_text,str) and kind_text in raw
         and re.search(r'(?<![0-9])'+re.escape(str(projection['value']))+r'(?:\.0+)?(?![0-9])',value_text)
         and re.search(r'MYR|RM',value_text) and re.search(r'daily|per day|每日|日均',kind_text,re.I)
         and not re.search(r'total|lifetime|总额',kind_text,re.I), 'literal actual value and daily-kind fragments')
    return projection['value']


def _effect_rows(root, source_pin, action_id):
    return [e for e in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS)
            if e.get('details',{}).get('professional_ads_object_effect',{}).get('source_registration')==source_pin
            and e['details']['professional_ads_object_effect'].get('action_id')==action_id]


def planned_preflight(root, item, context, *, fresh=True):
    need(item.get('schema')==OBJECT_PREFLIGHT and item.get('source_registration')==context['registration'], 'same normal plan/object preflight')
    request = doc(root,item['request']); spec = context['object_spec']
    need(same(item,request) and same(request,spec,(*IDENTITY,'source_project_id','account_id','parent_campaign_id','object_key','operation','desired')),
         'exact derived original object/intent; no caller label or changed field')
    at=w._parse_observed_at(request.get('observed_at'));now=dt.datetime.now(dt.timezone.utc)
    need(at is not None and (not fresh or 0 <= (now-at).total_seconds() <= 300), 'fresh actual execution observations, not expiring reports')
    docs={name:doc(root,request.get(name)) for name in ('facts','self_check','backup','recovery')}
    intent=w.sha256_value(spec)
    for value in docs.values():
        need(same(value,request) and value.get('intent_sha256')==intent, 'same exact object facts/selfcheck/backup/recovery')
    facts=docs['facts'];check=docs['self_check']
    need(check.get('status')=='PASS' and check.get('facts')==request['facts'] and check.get('checks')
         and all(x is True for x in check['checks'].values()), 'actual original professional successful selfcheck')
    need(facts.get('observed_at')==request['observed_at'], 'same current observations')
    channel=facts['channel'];inv=doc(root,facts['native_inventory']);browser=inv.get('channel',{})
    from chatgpt_fe689_draft_admission import BROWSER_PROFILE,BROWSER_EXTENSION
    url=urlsplit(channel.get('account_url',''))
    need(channel.get('profile')==browser.get('profileName')==BROWSER_PROFILE
         and channel.get('stable_extension')==browser.get('metadata',{}).get('extensionInstanceId')==BROWSER_EXTENSION
         and browser.get('family')=='chrome' and browser.get('type')=='extension'
         and channel.get('runtime_browser')==browser.get('id') and channel.get('runtime_tab')
         and url.scheme=='https' and url.netloc=='ads.openai.com' and parse_qs(url.query).get('act')==[spec['account_id']]
         and len([t for t in inv.get('ads_tabs',[])if t.get('id')==channel['runtime_tab'] and t.get('browserId')==browser['id']and t.get('url')==channel['account_url']])==1,
         'real stable profile/extension/account and observed handles')
    inv_at=w._parse_observed_at(inv.get('at'));need(inv_at is not None and abs((inv_at-at).total_seconds())<=300,'current native inventory time')
    evidence=facts.get('raw_evidence');need(isinstance(evidence,list)and evidence,'actual current native evidence')
    for pin in evidence:need(w.file_digest(root,pin.get('path',''))==pin,'current native bytes')
    original=doc(root,context['packet']['facts'])
    groups_base=next(p for p in original['raw_evidence']if Path(p['path']).name=='actual-groups-rows.json')
    ads_base=next(p for p in original['raw_evidence']if Path(p['path']).name=='actual-existing-ads-rows.json')
    groups=_protected_rows(root,groups_base,facts['groups_table'],('Active','Name','Campaign name','Status','Context Hints','Bid strategy'))
    ads=_protected_rows(root,ads_base,facts['ads_table'],('Active','Ad','Status','URL','Campaign name','Ad group'))
    need(facts.get('complete_groups_list')is True and facts.get('complete_ads_list')is True,'complete supported current lists, not hidden backend metadata')
    budget=_budget_projection(root,facts['saved_campaign_budget'],{context['plan']['budget_shared_average_MYR_day'],context['budget_limit']})
    need(facts.get('campaign_name')==context['intent']['parent_campaign_name'], 'same current original campaign name')
    operation=spec['operation']
    if operation=='set_shared_daily_budget':
        need(budget==context['plan']['budget_shared_average_MYR_day'],'already desired budget or changed before: read saved effect, never save again')
        need(facts.get('actual_budget_control_kind')=='average_daily','same daily control; total/lifetime editor rejected')
    elif operation=='create_ad_group_only':
        need(spec['parent_group_name']not in [row[groups[0].index('Name')]for row in groups[1:]],'group already exists; no duplicate create')
        need(facts.get('form_defaults')=={'Ad group name':'','Context hints (optional)':'','Tracking parameters':'','Autobid':True,'Manual: Max CPC':False},'actual empty new-group form/defaults')
    else:
        parent=facts.get('parent_group',{});gid=parent.get('id');name=spec['parent_group_name']
        need(isinstance(gid,str)and re.fullmatch(r'adgrp_[A-Za-z0-9_-]+',gid)and parent.get('name')==name
             and request.get('parent_group_id')==gid,'real current original parent group ID')
        if spec['object_key']in context['known_groups']:need(gid==context['known_groups'][spec['object_key']],'original already-created group is not replaced')
        option=parent.get('native_option');need(isinstance(option,dict)and w.file_digest(root,option['path'])==option
             and ('Value: '+name+', ID: select-option-'+gid)in w.safe_path(root,option['path']).read_text(),'exact native group option/name/ID')
        need(name in [row[groups[0].index('Name')]for row in groups[1:]],'parent must really exist')
        if operation=='upload_reference_image':
            need(facts.get('current_asset_selection')=='empty'and facts.get('own_prior_upload_effect')=='none',
                 'existing/unknown upload must be read first; one new upload only')
        else:
            need(spec['desired']['Ad Name']not in [row[ads[0].index('Ad')]for row in ads[1:]],'ad already exists; no duplicate Create')
            if facts.get('native_client_image_stage') is not None:
                binding=_native_client_image_binding(root,context,spec,facts['native_client_image_stage'],facts)
                need(request.get('asset_binding')==binding,'exact backend-derived original client image stage, not a fabricated server asset')
            else:
                upload_id=next(k for k,s in operation_specs(root,context).items()if s['operation']=='upload_reference_image'and s['object_key']==spec['upload_key'])
                effects=_effect_rows(root,context['registration'],upload_id)
                need(len(effects)==1,'real uploaded asset/crop readback first; old group permit is not an upload')
                effect=effects[0]['details']['professional_ads_object_effect'];asset=doc(root,effect['observation'])
                need(request.get('asset_binding')=={'upload_effect_event_id':effects[0]['event_id'],'asset_id':asset['asset_id'],'image_sha256':spec['desired']['Image']['sha256']},'same real uploaded image ID and original image SHA')
                need(isinstance(asset['asset_id'],str)and not asset['asset_id'].startswith(('blob:','data:','http:','https:')),'a local blob URL is never a server asset ID')
                need(facts.get('selected_asset_id')==asset['asset_id']and facts.get('crop_preview',{}).get('asset_id')==asset['asset_id']
                     and facts['crop_preview'].get('image_sha256')==spec['desired']['Image']['sha256'], 'current exact crop/preview and asset; no substitute image')
                preview=facts['crop_preview'].get('native_evidence');need(isinstance(preview,dict)and w.file_digest(root,preview['path'])==preview,'actual native preview evidence')
            need(facts.get('actual_form_fields')=={k:''for k in ('Ad Name','Title','Description','Link','Tracking parameters')}, 'actual empty ad fields; desired values derive from plan')
    return request


def derive(root, registration, key, kind):
    item=doc(root,registration);need(item.get('schema')in {PLAN_SCHEMA,SUPPLEMENT_SCHEMA},'one registered original plan source')
    snapshot=w.read_json(w.snapshot_path(root,item['task_id']));context=source(root,item)
    events=[e for e in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS)if e.get('details',{}).get(EVENT)==registration]
    need(len(events)==1,'actual plan source registration before deriving actions')
    names={'group':'create_ad_group_only','upload':'upload_reference_image','ad':'create_ad_only','budget':'set_shared_daily_budget'}
    need(kind in names,'supported bounded operation kind')
    specs=operation_specs(root,context)
    if kind=='upload':
        selected=next((x for x in context['plan']['items']if x['key']==key),None);need(selected and selected.get('image'),'planned reference image')
        key=next(x['key']for x in context['plan']['items']if x.get('image',{}).get('sha256')==selected['image']['sha256'])
    wanted=[s for s in specs.values()if s['operation']==names[kind]and s['object_key']==('shared_budget'if kind=='budget'else key)]
    need(len(wanted)==1,'one original planned action; already-created groups are not reissued')
    spec=wanted[0];logical=w.sha256_value([spec[k]for k in IDENTITY])
    prior=[p for p in w.read_jsonl(Path(root)/w.POLICY_DECISIONS)if p.get('autonomous_action_key')==logical and p.get('status')=='allow']
    return {'schema':'professional-ads-derived-object-request/v2',**spec,'source_registration':registration,
            'intent_sha256':w.sha256_value(spec),'observed_at':None,'facts':None,'self_check':None,'backup':None,'recovery':None,
            'parent_group_id':context['known_groups'].get(key),'asset_binding':None,
            'actual_action_allowed':False,'source_is_not_a_permit':True,
            'existing_issued_policy_ids':[p['decision_id']for p in prior],
            'next_action':'read_existing_effect_no_retry'if prior else'original_executor_fresh_native_facts_and_preflight'}


def record_effect(root, proof):
    """Read original executor's native effect; no external action or retry grant."""
    need(proof.get('schema')=='professional-ads-object-native-effect/v2','normal native effect schema')
    snapshot=w.read_json(w.snapshot_path(root,proof['task_id']));context=match(root,snapshot,proof)
    need(context and context.get('plan_objects'),'exact registered plan object')
    key=w.sha256_value([proof[k]for k in IDENTITY]);attempts=w.read_jsonl(Path(root)/'logs/professional-ads-object-attempts'/(key+'.jsonl'))
    need(len(attempts)==1 and attempts[0].get('policy_decision_id')==proof.get('policy_decision_id'),'one real reserved normal effect')
    policy=[p for p in w.read_jsonl(Path(root)/w.POLICY_DECISIONS)if p.get('decision_id')==proof['policy_decision_id']]
    need(len(policy)==1 and policy[0].get('status')=='allow'and policy[0].get('exact_request')==attempts[0]['request'],'original exact policy/request')
    observation=doc(root,proof['observation']);need(same(observation,proof)and observation.get('account_id')==context['plan']['account_id']
         and observation.get('parent_campaign_id')==context['plan']['campaign_id'],'actual effect same account/parent/object')
    page=native_identity(root,proof['actual_native_observation'],proof['department'])
    pairs=[(t,m)for t in page.get('turns',[])for m in t.get('items',[])if m.get('id')==proof.get('native_call_id')]
    need(len(pairs)==1 and not pairs[0][0].get('error')and pairs[0][0].get('status')in {'inProgress','completed'}
         and pairs[0][1].get('status')=='completed'and not pairs[0][1].get('error'),'real successful original native observation call')
    call=pairs[0][1]
    need(call.get('type')=='mcpToolCall'and call.get('server')in {'cua_repl','node_repl'}and call.get('tool')=='js',
         'first-party actual native UI observation, not a successful file writer')
    observed=w._parse_observed_at(observation.get('observed_at'));reserved=w._parse_observed_at(attempts[0]['at'])
    need(observed is not None and reserved is not None and reserved<=observed<=dt.datetime.now(dt.timezone.utc)
         and pairs[0][0].get('startedAt',float('inf'))<=observed.timestamp(),'real reservation then native readback chronology')
    evidence=observation.get('native_evidence');need(isinstance(evidence,list)and evidence,'actual native effect/preview evidence')
    for pin in evidence:need(w.file_digest(root,pin.get('path',''))==pin,'native effect bytes')
    text='\n'.join(w.safe_path(root,p['path']).read_text()for p in evidence if Path(p['path']).suffix.lower()in {'.txt','.md'})
    spec=context['object_spec'];operation=spec['operation']
    issued_request=doc(root,policy[0]['exact_request']);before_facts=doc(root,issued_request['facts'])
    after_groups=(_protected_groups_after_child(root,before_facts['groups_table'],observation['groups_table'],issued_request,spec)if operation=='create_ad_only'else _protected_rows(root,before_facts['groups_table'],observation['groups_table'],('Active','Name','Campaign name','Status','Context Hints','Bid strategy')))
    after_ads=_protected_rows(root,before_facts['ads_table'],observation['ads_table'],('Active','Ad','Status','URL','Campaign name','Ad group'))
    before_groups=_native_table(root,before_facts['groups_table']);before_ads=_native_table(root,before_facts['ads_table'])
    need(len(after_groups)==len(before_groups)+(1 if operation=='create_ad_group_only'else 0)
         and len(after_ads)==len(before_ads)+(1 if operation=='create_ad_only'else 0),'only the single reserved object changed; all original/current rows protected')
    if operation in {'create_ad_group_only','create_ad_only'}:
        _exact_created_row(root,before_facts['groups_table']if operation=='create_ad_group_only'else before_facts['ads_table'],
                           observation['groups_table']if operation=='create_ad_group_only'else observation['ads_table'],spec)
    if operation=='upload_reference_image':
        asset=observation.get('asset_id');need(isinstance(asset,str)and asset and asset in text and not asset.startswith(('select-option-','node-','blob:','data:','http:','https:'))
             and not any(x.rstrip('.,;').endswith('/'+asset)for x in re.findall(r"blob:[^\s'\"<>]+",text))
             and observation.get('image_sha256')==spec['desired']['Image']['sha256'],'actual platform asset ID and exact uploaded source SHA')
        need(observation.get('crop_preview_evidence')in evidence,'real crop/preview evidence after upload')
    elif operation=='create_ad_only':
        need(isinstance(observation.get('ad_id'),str)and observation['ad_id']in text
             and spec['desired']['Ad Name']in text and isinstance(observation.get('parent_group_id'),str)
             and observation['parent_group_id']==issued_request.get('parent_group_id')and observation['parent_group_id']in text,
             'real created ad ID/name/parent readback')
        need(observation.get('delivery_status')and observation.get('fields_not_exposed')is not None,'review/Serving and unexposed fields reported separately')
        image=issued_request.get('asset_binding',{})
        if image.get('kind')=='native_client_image_ready':
            original_stage=doc(root,image['stage_proof']);client=_native_client_image_proof(root,original_stage)
            _native_client_created_readback(root,client,issued_request,attempts[0],observation,page,call,proof)
            need(image['image_sha256']==client['image_sha256']and image['form_tab']==client['form_tab']
                 and observation.get('native_client_image_stage_event_id')==image['stage_event_id']
                 and observation.get('input_image_sha256')==client['image_sha256']
                 and observation.get('created_ad_preview')in evidence,'real final ad/preview linked to exact original client crop; no upload success inferred')
            if observation.get('asset_id') is not None:
                need(isinstance(observation['asset_id'],str)and observation['asset_id']in text and not observation['asset_id'].startswith(('blob:','data:','http:','https:')),'only a genuinely exposed final server asset ID')
            else:need('server_asset_id'in observation['fields_not_exposed']or 'file_id'in observation['fields_not_exposed'],'unexposed server ID must be reported honestly')
    elif operation=='create_ad_group_only':
        need(isinstance(observation.get('group_id'),str)and observation['group_id']in text
             and spec['desired']['Ad group name']in text,'real created group ID/name')
    else:
        _budget_projection(root,observation.get('saved_budget'),{context['budget_limit']})
        need(observation.get('saved_list_or_reopened_source')in evidence,'actual saved/reopened daily70 source, not an input value')
    with w.workflow_lock(root):
        old=_effect_rows(root,context['registration'],proof['action_id'])
        value={**{k:proof[k]for k in IDENTITY},'source_registration':context['registration'],'observation':proof['observation'],
               'native_observation':proof['actual_native_observation'],'native_call_id':proof['native_call_id'],
               'policy_decision_id':proof['policy_decision_id'],'request':attempts[0]['request'],
               **({'native_create_call_id':proof['native_create_call_id'],'native_client_image_stage_event_id':issued_request['asset_binding']['stage_event_id']}if issued_request.get('asset_binding',{}).get('kind')=='native_client_image_ready'else{}),
               'new_permission_issued':False,'business_parent_closed':False}
        if old:
            need(len(old)==1 and old[0]['details']['professional_ads_object_effect']==value,'preserve original effect; no replacement')
            return {'result':'duplicate_ignored','event_id':old[0]['event_id']}
        event=w.append_workflow_event(root,proof['task_id'],snapshot['current_state'],{'professional_ads_object_effect':value})
    return {'result':'recorded','event_id':event['event_id'],'new_permission_issued':False}


def source_status(root, item, pin):
    if item.get('schema')in {PLAN_SCHEMA,SUPPLEMENT_SCHEMA}:
        context=source(root,item)
        events=[e for e in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS)if e.get('details',{}).get(EVENT)==pin]
        return {'state':'PLAN_SOURCE_REGISTERED_NOT_A_PERMIT'if len(events)==1 else'PLAN_SOURCE_NOT_REGISTERED',
                'source_registration':pin,'planned_actions':[{'action_id':x['action_id'],'object_key':x['object_key'],'operation':x['operation']}for x in operation_specs(root,context).values()],
                'latest_real_human_shared_daily_budget_limit':context['budget_limit'],'budget_saved_not_claimed':True,'actual_action_allowed':False}
    context=match(root,w.read_json(w.snapshot_path(root,item['task_id'])),item)
    key=w.sha256_value([item[k]for k in IDENTITY]);policies=[p for p in w.read_jsonl(Path(root)/w.POLICY_DECISIONS)if p.get('autonomous_action_key')==key and p.get('status')=='allow']
    effects=_effect_rows(root,context['registration'],item['action_id'])if context else[]
    return {'state':'SOURCE_NOT_REGISTERED'if not context else'ORIGINAL_EFFECT_RECORDED_NO_REPLAY'if effects else'ISSUED_OR_UNKNOWN_EFFECT_READBACK_REQUIRED'if policies else'SOURCE_REGISTERED_FRESH_PREFLIGHT_REQUIRED',
            'source_registration':context['registration']if context else None,'policy_ids':[p['decision_id']for p in policies],
            'effect_event_ids':[e['event_id']for e in effects],'actual_action_allowed':False}


def freeze_preflight(root, bundle, output):
    """Bind actual owner facts/selfcheck; derive backup/recovery without new approval."""
    request=doc(root,bundle['derived_request'])
    context=match(root,w.read_json(w.snapshot_path(root,request['task_id'])),request)
    need(context and context.get('plan_objects'),'one normal derived plan object')
    facts=doc(root,bundle['facts']);check=doc(root,bundle['self_check'])
    need(check.get('facts')==bundle['facts'],'professional selfcheck must bind exact current facts')
    binding=None
    if request['operation']=='create_ad_only':
        spec=context['object_spec']
        if facts.get('native_client_image_stage') is not None:
            binding=_native_client_image_binding(root,context,spec,facts['native_client_image_stage'],facts)
        else:
            upload=next(s for s in operation_specs(root,context).values()if s['operation']=='upload_reference_image'and s['object_key']==spec['upload_key'])
            effects=_effect_rows(root,context['registration'],upload['action_id']);need(len(effects)==1,'real upload/crop readback before ad')
            observed=doc(root,effects[0]['details']['professional_ads_object_effect']['observation'])
            need(isinstance(observed.get('asset_id'),str)and not observed['asset_id'].startswith(('blob:','data:','http:','https:')),'connector/asset branch requires the real server file ID')
            binding={'upload_effect_event_id':effects[0]['event_id'],'asset_id':observed['asset_id'],'image_sha256':spec['desired']['Image']['sha256']}
    target=w.safe_path(root,output);need(not target.exists(),'new immutable actual input directory; preserve prior effects')
    target.mkdir(parents=True)
    def put(name,value):
        path=target/name;w.atomic_write_json(path,value);return w.file_digest(root,str(path.relative_to(root)))
    request.update(observed_at=facts['observed_at'],facts=bundle['facts'],self_check=bundle['self_check'])
    request['parent_group_id']=facts.get('parent_group',{}).get('id')
    if request['operation']=='create_ad_only':request['asset_binding']=binding
    common={k:request[k]for k in IDENTITY};common['intent_sha256']=w.sha256_value(context['object_spec'])
    request['backup']=put('CURRENT-VISIBLE-BACKUP.json',{**common,'schema':'professional-visible-before-backup/v2','facts':bundle['facts'],
        'groups_table':facts['groups_table'],'ads_table':facts['ads_table'],'native_evidence':facts['raw_evidence'],
        'coverage':'supported visible current objects only; not a hidden backend/server CAS backup'})
    request['recovery']=put('EXACT-NO-REPLAY-RECOVERY.json',{**common,'schema':'professional-single-effect-recovery/v2',
        'before_effect':'cancel unsupported or changed state; never consume an old permit',
        'unknown_effect':'read original policy/reservation and supported actual result; never retry the same logical effect',
        'after_effect':'record actual native IDs/fields/preview and protected rows; report unavailable fields honestly',
        'inverse_permission_issued':False,'inverse':'any real corrective write needs its own applicable original authority and exact current object; no implicit delete/archive/pause'})
    request_pin=put('CURRENT-EXECUTION-REQUEST.json',request)
    item={k:request[k]for k in (*IDENTITY,'source_project_id')}
    item.update(schema=OBJECT_PREFLIGHT,source_registration=context['registration'],request=request_pin)
    input_pin=put('NORMAL-OBJECT-PREFLIGHT.json',item)
    planned_preflight(root,item,context)
    return {'state':'CURRENT_INPUT_FROZEN_NOT_REGISTERED_NOT_A_PERMIT','request':request_pin,'preflight':input_pin,'actual_action_allowed':False}



NATIVE_IMAGE_SCHEMA = 'professional-ads-native-client-image-stage/v1'
NATIVE_IMAGE_EVENT = 'professional_ads_native_client_image_preparation'


def _native_client_image_proof(root, proof):
    """Authenticate an original retained client image; never claim server upload."""
    need(proof.get('schema')==NATIVE_IMAGE_SCHEMA and proof.get('action_class')=='ads_write','typed original native client-image source')
    context=match(root,w.read_json(w.snapshot_path(root,proof['task_id'])),proof)
    need(context and context.get('plan_objects') and context['object_spec']['operation']=='create_ad_only'
         and proof.get('source_registration')==context['registration'],'one original mapped ad; no new action or borrowed source')
    spec=context['object_spec'];req=doc(root,proof['original_upload_request']);upload=next(s for s in operation_specs(root,context).values()if s['operation']=='upload_reference_image'and s['object_key']==spec['upload_key'])
    need(same(req,upload,(*IDENTITY,'source_project_id','account_id','parent_campaign_id','object_key','operation','desired'))
         and req['source_registration']==context['registration'],'same exact original mapped image/request')
    logical=w.sha256_value([req[k]for k in IDENTITY]);attempt_path='logs/professional-ads-object-attempts/'+logical+'.jsonl'
    need(w.file_digest(root,attempt_path)==proof.get('original_upload_attempt'),'original image reservation bytes stay frozen')
    attempts=w.read_jsonl(Path(root)/attempt_path);policies=[p for p in w.read_jsonl(Path(root)/w.POLICY_DECISIONS)if p.get('decision_id')==proof.get('upload_policy_decision_id')]
    need(len(attempts)==len(policies)==1 and attempts[0].get('state')=='reserved_before_native_effect'
         and attempts[0]['policy_decision_id']==policies[0]['decision_id']and policies[0].get('status')=='allow'
         and policies[0].get('autonomous_action_key')==logical and policies[0].get('exact_request')==proof['original_upload_request']==attempts[0].get('request'),
         'one original consumed image policy/reservation; never re-sign or release it')
    data=doc(root,proof['professional_source_input']);native=data['native_image_preparation'];image=spec['desired']['Image'];facts=doc(root,req['facts']);channel=facts['channel'];parent=facts['parent_group']
    target=proof.get('target_parent_binding',parent)
    need(isinstance(target,dict)and target.get('name')==spec['parent_group_name']and proof.get('parent_group_id')==target.get('id'),'exact mapped target parent native source required for shared-image reuse; upload parent is not the target by default')
    if target!=parent:
        need(data.get('target_parent_binding')==target,'original professional shared-image target binding source required')
    option=target.get('native_option');need(isinstance(option,dict)and w.file_digest(root,option['path'])==option and ('Value: '+target['name']+', ID: select-option-'+target['id'])in w.safe_path(root,option['path']).read_text(),'actual independent target-parent option/ID')
    need(data.get('task_id')==spec['task_id']and data.get('scope')==spec['scope']and data.get('account_id')==spec['account_id']and data.get('campaign_id')==spec['parent_campaign_id']
         and native.get('request')==proof['original_upload_request']and native.get('policy')==policies[0]['decision_id']and native.get('action')==upload['action_id']
         and native.get('source_image')==image and req.get('parent_group_id')==parent['id']
         and parent['name']==upload['parent_group_name']and native.get('live_form_tab')==proof.get('form_tab')==channel['runtime_tab'], 'actual original account/parent/image/retained form source')
    from chatgpt_fe689_draft_admission import BROWSER_PROFILE,BROWSER_EXTENSION
    inv=doc(root,facts['native_inventory']);browser=inv['channel']
    need(channel['profile']==proof.get('profile')==browser.get('profileName')==BROWSER_PROFILE
         and channel['stable_extension']==proof.get('stable_extension')==browser.get('metadata',{}).get('extensionInstanceId')==BROWSER_EXTENSION
         and channel['runtime_browser']==browser.get('id')and parse_qs(urlsplit(channel['account_url']).query).get('act')==[spec['account_id']], 'stable real profile/extension/account, never a runtime number whitelist')
    for pin in native['proofs']:need(w.file_digest(root,pin['path'])==pin,'unchanged original native preparation evidence')
    for field in ('retained_calls','crop_DOM','crop_image'):
        need(proof.get(field)in native['proofs'],'exact original professional source must bind this evidence')
    rows=json.loads(w.safe_path(root,proof['retained_calls']['path']).read_text())
    need(w.file_digest(root,proof['retained_calls']['path'])==proof['retained_calls']and isinstance(rows,list)and len(rows)==2,'two original chooser/crop call-output pairs')
    fixed=w.department_registry(root)[proof['department']]['chat_binding'];relative=Path(proof.get('canonical_log_relative',''))
    need(relative.parts and not relative.is_absolute()and '..'not in relative.parts and fixed['task_id']in relative.name and relative.suffix=='.jsonl','original actor canonical source path')
    path=CANONICAL_SESSIONS/relative
    need(path.is_file()and not any(p.is_symlink()for p in [path,*path.parents])and path.resolve().is_relative_to(CANONICAL_SESSIONS.resolve()),'real original canonical history, not an alternate caller log')
    wanted=[proof.get('chooser_call_id'),proof.get('crop_call_id')];need(len(set(wanted))==2 and all(isinstance(x,str)and x for x in wanted),'two exact original UI calls')
    found={cid:[]for cid in wanted};all_calls=[];outputs={};meta=None
    with path.open()as f:
        for line in f:
            row=json.loads(line);p=row.get('payload',{})
            if row.get('type')=='session_meta':need(meta is None,'one canonical session');meta=p
            if p.get('call_id')in found:found[p['call_id']].append(row)
            if p.get('type')=='function_call'and p.get('namespace')in {'mcp__cua_repl','mcp__node_repl'}:
                try:code=json.loads(p.get('arguments','{}')).get('code','')
                except (ValueError,AttributeError):continue
                all_calls.append((row,code))
            elif p.get('type')=='function_call_output'and any(p.get('call_id')==x[0]['payload'].get('call_id')for x in all_calls):outputs[p.get('call_id')]=row
    need(meta and meta.get('id')==fixed['task_id']and meta.get('cwd')==str(Path(root).resolve()),'original canonical role/project identity')
    calls=[]
    for index,cid in enumerate(wanted):
        pair=found[cid];need(len(pair)==2 and pair==[rows[index]['call'],rows[index]['output']]
             and pair[0]['payload'].get('type')=='function_call'and pair[0]['payload'].get('namespace')in {'mcp__cua_repl','mcp__node_repl'}
             and pair[1]['payload'].get('type')=='function_call_output','actual canonical exact call/output, never a summary')
        code=json.loads(pair[0]['payload']['arguments'])['code'];out=pair[1]['payload']['output'];need(isinstance(out,list)and all(x.get('type')=='input_text'and isinstance(x.get('text'),str)for x in out),'complete original native output')
        start=w._parse_observed_at(pair[0]['timestamp']);end=w._parse_observed_at(pair[1]['timestamp']);reserved=w._parse_observed_at(attempts[0]['at'])
        need(start and end and reserved and reserved<=start<=end<=dt.datetime.now(dt.timezone.utc),'original reservation/call/output sequence')
        calls.append({'id':cid,'code':code,'text':'\n'.join(x['text']for x in out),'start':start,'end':end})
    choose,crop=calls;need(choose['end']<=crop['start'],'chooser completes before real crop save')
    for source_row,source_code in all_calls:
        source_at=w._parse_observed_at(source_row.get('timestamp'))
        if source_at and choose['end']<source_at<crop['start']:
            need(not re.search(r"(?:name:\x27(?:Create|Upload image)\x27|\.setFiles\s*\()",source_code),'intervening Create or image reselection requires actual new native source')
    code=choose['code'];binding=re.search(r'var\s+(\w+)\s*=\s*JSON\.parse\(await\s+\w+\.readFile\((\w+)\+\x27/input/CURRENT-EXECUTION-REQUEST.json\x27',code)
    tab=re.search(r'(\w+)\.playwright\.getByRole\(\x27button\x27,\{name:\x27Upload image\x27,exact:true\}\)\.click\(\)',code)
    need(binding and tab and proof['upload_policy_decision_id']in code and proof['original_upload_request']['sha256']in code
         and '.setFiles(['+binding[1]+'.desired.Image.local_path])'in code and 'filechooser'in code,'real visible chooser and original request image binding')
    dirvar=binding[2];tabvar=tab[1];folder=str(w.safe_path(root,req['facts']['path']).parent)
    definitions=[];tabdefs=[]
    for row,script in all_calls:
        stamp=w._parse_observed_at(row.get('timestamp'))
        if not stamp or stamp>choose['start']:continue
        for m in re.finditer(r'(?:var|let|const)\s+'+re.escape(dirvar)+r'\s*=\s*([\x27\x22])([^\x27\x22]+)\1',script):definitions.append(m[2])
        m=re.search(r'(?:var|let|const)\s+'+re.escape(tabvar)+r'\s*=\s*await cua\.createBrowserTab\(([\x27\x22])([^\x27\x22]+)\1,([\x27\x22])([^\x27\x22]+)\3\)',script)
        if m:tabdefs.append((row,m[2],m[4]))
    need(definitions and all(x==folder for x in definitions)and tabdefs,'real original request directory and tab creation source')
    tabrow,bid,url=tabdefs[-1];tabout=outputs.get(tabrow['payload']['call_id'],{}).get('payload',{}).get('output',[]);tabtext='\n'.join(x.get('text','')for x in tabout)
    need(bid==channel['runtime_browser']and url==channel['account_url']and 'Browser tab: '+channel['runtime_tab']+','in tabtext,'original real tab/account/browser response, not guessed handles')
    need('filechooser: \'received\''in choose['text']and 'setFiles: \'completed\''in choose['text']and 'Edit image'in choose['text']
         and tabvar+".playwright.getByRole('button',{name:'Save changes',exact:true}).click()"in crop['code'],'actual chooser receipt and crop-save UI call/output')
    dom=doc(root,proof['crop_DOM']);need(dom.get('url')==channel['account_url']and isinstance(dom.get('dialogs'),list)and len(dom['dialogs'])==1,'actual retained form/account DOM')
    dialog=dom['dialogs'][0];blob=[x['src']for x in dialog.get('images',[])if x.get('src','').startswith('blob:https://ads.openai.com/')]
    need(blob and len(blob)==len(set(blob))and all(x in crop['text']for x in blob)
         and all(x in dialog.get('text','')and x in crop['text']for x in ('Create Ad',context['intent']['parent_campaign_name'],spec['parent_group_name']))
         and 'Edit image'not in dialog.get('text',''),'actual original crop returned to same ad form; blob is not server ID')
    proof_at=w._parse_observed_at(data.get('at_UTC'));dom_at=w._parse_observed_at(dom.get('at'))
    need(proof_at and dom_at and crop['start']<=dom_at<=crop['end']<=proof_at<=dt.datetime.now(dt.timezone.utc),'real crop/source times, not freshened old observations')
    return {'context':context,'upload':upload,'upload_request':req,'image_sha256':image['sha256'],'parent_group_id':target['id'],'original_upload_parent_group_id':parent['id'],
            'channel':channel,'form_tab':channel['runtime_tab'],'blob_urls':blob,'crop_at':dom_at,'crop_evidence':proof['crop_image'],
            'tab_variable':tabvar,'canonical_calls':all_calls,'canonical_outputs':outputs,'crop_call_end':crop['end'],'upload_policy_decision_id':policies[0]['decision_id']}


def _native_client_image_live(root, proof, stage):
    ctx=stage['context']
    need(not _effect_rows(root,ctx['registration'],stage['upload']['action_id']),'real server upload effect must use the existing asset-ID branch')
    need(not _effect_rows(root,ctx['registration'],proof['action_id']),'actual created ad is final; never restage or replay')
    for row,code in stage['canonical_calls']:
        at=w._parse_observed_at(row.get('timestamp'))
        if at and at>stage['crop_call_end']and stage['tab_variable']in code:
            need(not re.search(re.escape(stage['tab_variable'])+r'(?:\.playwright[^;]*|)\.(?:click|goto|reload|setFiles|submit|dispatchEvent)\s*\(',code),
                 'retained form has a later UI trigger; unknown Create or changed image must be read, not replayed')
    return {'state':'NATIVE_CLIENT_IMAGE_PREPARED_NOT_SERVER_UPLOAD','task_id':proof['task_id'],'action_id':proof['action_id'],
            'image_sha256':stage['image_sha256'],'parent_group_id':stage['parent_group_id'],'form_tab':stage['form_tab'],
            'blob_urls':stage['blob_urls'],'crop_observed_at':stage['crop_at'].isoformat(),'server_asset_id':'NOT_EXPOSED',
            'server_upload_effect':'UNKNOWN_NOT_CLAIMED','original_upload_attempt_released':False,'actual_action_allowed':False,'new_permission_issued':False}


def native_client_image_check(root, proof):
    return _native_client_image_live(root,proof,_native_client_image_proof(root,proof))

def record_native_client_image(root, proof, pin):
    with w.workflow_lock(root):
        need(doc(root,pin)==proof,'exact immutable native client image source')
        checked=native_client_image_check(root,proof)
        old=[e for e in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS)if e.get('details',{}).get(NATIVE_IMAGE_EVENT,{}).get('proof')==pin
             or same(e.get('details',{}).get(NATIVE_IMAGE_EVENT,{}),proof)]
        need(not old,'native image stage already recorded; no duplicate or concurrent restage')
        snapshot=w.read_json(w.snapshot_path(root,proof['task_id']));need(snapshot['current_state']not in w.TERMINAL_STATES,'closed task is historical')
        value={**{k:proof[k]for k in IDENTITY},'proof':pin,'source_registration':proof['source_registration'],'stage':checked}
        event=w.append_workflow_event(root,proof['task_id'],snapshot['current_state'],{NATIVE_IMAGE_EVENT:value})
    return {'result':'recorded_client_stage_only','event_id':event['event_id'],'proof':pin,'server_asset_id':'NOT_EXPOSED',
            'original_upload_attempt_released':False,'actual_action_allowed':False,'new_permission_issued':False}


def _native_client_created_readback(root, client, issued, attempt, observation, page, native_call, proof):
    """After-write evidence uses the historical image, never the pre-click ban."""
    tab=client['tab_variable'];create_id=proof.get('native_create_call_id')
    need(isinstance(create_id,str)and create_id and create_id!=native_call['id'],'one actual Create invocation then actual observation')
    create=[]
    pattern=re.escape(tab)+r"\.playwright\.getByRole\(\x27button\x27,\{name:\x27Create\x27,exact:true\}\)\.click\(\)"
    for row,code in client['canonical_calls']:
        at=w._parse_observed_at(row.get('timestamp'))
        if at and at>client['crop_call_end']and re.search(pattern,code):create.append((row,code))
    need(len(create)==1 and create[0][0]['payload']['call_id']==create_id,'only one exact original retained-form Create; unknown/duplicate effects cannot close')
    call=create[0][0];output=client['canonical_outputs'].get(create_id)
    observations=[(row,code)for row,code in client['canonical_calls']if row['payload'].get('call_id')==native_call['id']]
    need(output and len(observations)==1,'complete original canonical Create/observation outputs')
    obsrow,code=observations[0];obsout=client['canonical_outputs'].get(native_call['id']);need(obsout,'complete actual native readback output')
    expected=re.fullmatch(r"\s*await "+re.escape(tab)+r"\.getAXState\(\{disableDiffing:true\}\);?\s*",code)
    need(expected and json.loads(obsrow['payload']['arguments'])==native_call.get('arguments'),'actual same-form pure native UI readback, not an agent ID assertion')
    raw=obsout['payload'].get('output',[]);need(raw and all(x.get('type')=='input_text'and isinstance(x.get('text'),str)for x in raw),'actual complete native UI output')
    text='\n'.join(x['text']for x in raw)
    need(all(x in text for x in (observation['ad_id'],observation['parent_group_id'],client['context']['object_spec']['desired']['Ad Name'])),'actual returned ad ID/name/parent must be in the canonical UI read')
    source_calls=[m for t in page.get('turns',[])for m in t.get('items',[])if m.get('id')==create_id]
    need(len(source_calls)==1 and source_calls[0].get('type')=='mcpToolCall'and source_calls[0].get('server')in {'cua_repl','node_repl'}and source_calls[0].get('tool')=='js'
         and json.loads(call['payload']['arguments'])==source_calls[0].get('arguments'),'same original first-party Create call, no borrowed native source')
    for cid in (create_id,native_call['id']):
        turns=[t for t in page.get('turns',[])if any(m.get('id')==cid for m in t.get('items',[]))]
        need(len(turns)==1 and turns[0].get('status')=='completed'and not turns[0].get('error'),'actual completed first-party action/observation turn')
        begin=dt.datetime.fromtimestamp(turns[0]['startedAt'],dt.timezone.utc);finish=dt.datetime.fromtimestamp(turns[0]['completedAt'],dt.timezone.utc)
        source=call if cid==create_id else obsrow;result=output if cid==create_id else obsout
        need(begin<=w._parse_observed_at(source['timestamp'])<=w._parse_observed_at(result['timestamp'])<=finish,'first-party completed turn contains actual canonical action/output')
    reserved=w._parse_observed_at(attempt['at']);start=w._parse_observed_at(call.get('timestamp'));end=w._parse_observed_at(output.get('timestamp'));read_at=w._parse_observed_at(obsrow.get('timestamp'));read_end=w._parse_observed_at(obsout.get('timestamp'));at=w._parse_observed_at(observation.get('observed_at'))
    need(all(x is not None for x in (reserved,start,end,read_at,read_end,at))and reserved<=start<=end<=read_at<=read_end<=at<=dt.datetime.now(dt.timezone.utc),'actual reserved action -> one Create -> full native result chronology')
    return {'create_call_id':create_id,'readback_call_id':native_call['id'],'reserved_at':attempt['at'],'Create_at':call['timestamp'],'readback_at':obsout['timestamp'],'one_provider_Create_effect_only':True}


def _native_client_image_binding(root, context, spec, stage_pin, facts):
    proof=doc(root,stage_pin);source=_native_client_image_proof(root,proof);stage=_native_client_image_live(root,proof,source)
    need(same(proof,spec)and proof['source_registration']==context['registration'],'same planned ad and original image source')
    rows=[e for e in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS)if e.get('details',{}).get(NATIVE_IMAGE_EVENT,{}).get('proof')==stage_pin]
    need(len(rows)==1 and rows[0]['details'][NATIVE_IMAGE_EVENT]['source_registration']==context['registration'],'one real committed native client stage; a flag is not admission')
    observed=w._parse_observed_at(facts.get('observed_at'));channel=facts['channel']
    need(observed and observed>=source['crop_at']and all(channel.get(k)==source['channel'][k]for k in ('profile','stable_extension','runtime_browser','runtime_tab','account_url'))
         and facts['parent_group']['id']==source['parent_group_id']and facts.get('selected_asset_id')is None,'same retained real form/channel/parent; no fabricated asset ID')
    crop=facts.get('crop_preview',{});need(crop.get('image_sha256')==stage['image_sha256']and crop.get('form_tab')==stage['form_tab']and crop.get('blob_urls')==stage['blob_urls'], 'current exact original local crop, never a blob UUID as server ID')
    pin=crop.get('native_evidence');need(isinstance(pin,dict)and w.file_digest(root,pin['path'])==pin,'actual fresh current crop evidence')
    return {'kind':'native_client_image_ready','stage_event_id':rows[0]['event_id'],'stage_proof':stage_pin,'image_sha256':stage['image_sha256'],
            'parent_group_id':stage['parent_group_id'],'form_tab':stage['form_tab'],'blob_urls':stage['blob_urls'],'server_asset_id':None}


FAILURE_STAGE = 'professional-ads-pre-provider-failure-stage/v1'
FAILURE_EVENT = 'professional_ads_pre_provider_failure_stage'
CANONICAL_SESSIONS = Path.home() / '.codex/sessions'


def _canonical_failure_calls(root, proof, request, attempt):
    """Read original platform history, not a caller's zero-effect statement."""
    import hashlib
    role = proof['department']; fixed = w.department_registry(root)[role]['chat_binding']
    relative = Path(proof.get('canonical_log_relative', ''))
    need(not relative.is_absolute() and relative.parts and '..' not in relative.parts
         and fixed['task_id'] in relative.name and relative.suffix == '.jsonl', 'exact original canonical actor log path')
    path = CANONICAL_SESSIONS / relative
    need(path.is_file() and not any(p.is_symlink() for p in [path,*path.parents])
         and path.resolve().is_relative_to(CANONICAL_SESSIONS.resolve()), 'original canonical log required; no replacement path')
    page = native_identity(root, proof['actual_native_source'], role)
    wanted = (proof.get('failed_call_id'), proof.get('observation_call_id'))
    need(all(isinstance(x,str) and x for x in wanted) and wanted[0] != wanted[1], 'two exact original native calls required')
    native = {}
    for cid in wanted:
        pairs = [(t,c) for t in page.get('turns',[]) for c in t.get('items',[]) if c.get('id') == cid]
        need(len(pairs)==1 and pairs[0][1].get('type')=='mcpToolCall'
             and pairs[0][1].get('server') in {'cua_repl','node_repl'} and pairs[0][1].get('tool')=='js'
             and pairs[0][0].get('status') in {'inProgress','completed','failed','interrupted'}, 'genuine original UI call, not a writer or summary')
        native[cid] = pairs[0][1]
    need(native[wanted[0]].get('status')=='failed' and native[wanted[1]].get('status')=='completed', 'actual failed chooser then completed observation required')
    rows = []; selected = {cid:[] for cid in wanted}; meta = None
    reserved = w._parse_observed_at(attempt['at']); need(reserved is not None,'real reservation time')
    # Canonical path/meta and exact first-party call arguments are both checked.
    with path.open() as handle:
        for number, line in enumerate(handle,1):
            raw = json.loads(line); payload = raw.get('payload',{})
            if raw.get('type')=='session_meta':
                need(meta is None,'one canonical session identity');meta=payload
            stamp = w._parse_observed_at(raw.get('timestamp'))
            if payload.get('call_id') in selected:
                selected[payload['call_id']].append((number,raw,hashlib.sha256(line.encode()).hexdigest()))
            if stamp is not None and stamp >= reserved and raw.get('type')=='response_item' and payload.get('type')in {'function_call','custom_tool_call'}:
                rows.append((stamp,payload))
            if len(selected[wanted[1]])==2: break
    need(meta and meta.get('id')==fixed['task_id'] and meta.get('cwd')==str(Path(root).resolve()), 'actual canonical actor/project, never proxy metadata')
    result = []
    for cid in wanted:
        entries = selected[cid]
        need(len(entries)==2 and [r[1]['payload'].get('type')for r in entries]==['function_call','function_call_output'], 'complete original call/output pair; no summary substitute')
        call, output = [r[1] for r in entries]; cp=call['payload'];op=output['payload']
        need(cp.get('name')=='js' and cp.get('namespace') in {'mcp__cua_repl','mcp__node_repl'}
             and json.loads(cp.get('arguments','null'))==native[cid].get('arguments'), 'canonical and first-party native call must match byte-valued arguments')
        start=w._parse_observed_at(call.get('timestamp'));end=w._parse_observed_at(output.get('timestamp'))
        need(start is not None and end is not None and reserved<=start<=end<=dt.datetime.now(dt.timezone.utc), 'original reservation/call/output order; no rewritten timestamps')
        text=op.get('output');need(isinstance(text,list)and text and all(isinstance(v,dict)and v.get('type')=='input_text'and isinstance(v.get('text'),str)for v in text),'complete actual first-party output text')
        result.append({'call_id':cid,'code':native[cid]['arguments'].get('code',''),'start':start,'end':end,
                       'text':'\n'.join(v['text']for v in text),'canonical_lines':[r[0]for r in entries], 'canonical_line_sha256':[r[2]for r in entries]})
    need(result[0]['end']<=result[1]['start'],'failure output precedes actual observation')
    relevant=[p for at,p in rows if at<=result[1]['end']]
    return result,relevant


def failure_stage_check(root, proof):
    """No provider call, no permit and no clearing of an original UNKNOWN."""
    need(proof.get('schema')==FAILURE_STAGE and proof.get('action_class')=='ads_write','bounded pre-provider failure schema')
    snapshot=w.read_json(w.snapshot_path(root,proof['task_id']));context=match(root,snapshot,proof)
    need(context and context.get('plan_objects') and context['object_spec'].get('operation')=='upload_reference_image','original registered upload object only')
    request=doc(root,proof['original_request']);need(same(request,proof)and request.get('source_registration')==context['registration'],'same original request/source/action, never new nonce')
    key=w.sha256_value([proof[k]for k in IDENTITY]);path=Path(root)/'logs/professional-ads-object-attempts'/(key+'.jsonl')
    need(w.file_digest(root,str(path.relative_to(root)))==proof.get('original_attempt'),'exact frozen original attempt bytes; no clearing or replacing')
    attempts=w.read_jsonl(path);policies=[p for p in w.read_jsonl(Path(root)/w.POLICY_DECISIONS)if p.get('decision_id')==proof.get('policy_decision_id')]
    need(len(attempts)==len(policies)==1 and attempts[0].get('state')=='reserved_before_native_effect'
         and attempts[0].get('policy_decision_id')==policies[0]['decision_id']and policies[0].get('status')=='allow'
         and policies[0].get('autonomous_action_key')==key and policies[0].get('exact_request')==proof['original_request']==attempts[0].get('request')
         and attempts[0].get('source_registration')==context['registration'],'original consumed policy and one exact reservation')
    need(not _effect_rows(root,context['registration'],proof['action_id']),'real successful effect cannot be reclassified or replayed')
    from chatgpt_fe689_draft_admission import BROWSER_PROFILE,BROWSER_EXTENSION
    facts=doc(root,request['facts']);channel=facts['channel'];inventory=doc(root,facts['native_inventory'])
    need(proof.get('account_id')==request.get('account_id')==context['plan']['account_id']
         and proof.get('parent_campaign_id')==request.get('parent_campaign_id')==context['plan']['campaign_id']
         and proof.get('profile')==channel.get('profile')==inventory.get('channel',{}).get('profileName')==BROWSER_PROFILE
         and proof.get('stable_extension')==channel.get('stable_extension')==BROWSER_EXTENSION
         and parse_qs(urlsplit(channel.get('account_url','')).query).get('act')==[proof['account_id']], 'real same account/profile/extension/parent, never a caller waiver')
    pairs,calls=_canonical_failure_calls(root,proof,request,attempts[0]);failed,observed=pairs
    # Only a pure wait and pure DOM input getter are provably non-invoking.
    # A selector click/setFiles/Upload, mixed code, dynamic helper, or unknown call
    # is deliberately NOT certified by a timeout or an empty input afterwards.
    tab=json.dumps(channel['runtime_tab']);browser=json.dumps(channel['runtime_browser'])
    pure_wait='var t=await cua.getTab('+tab+',{browser:'+browser+'});await t.playwright.waitForEvent("filechooser",{timeoutMs:10000});'
    pure_read="""nodeRepl.write(await t.playwright.locator('input[type="file"]').evaluate(el=>({value:el.value,files:Array.from(el.files).map(f=>({name:f.name,size:f.size,type:f.type}))})));"""
    compact=lambda value:re.sub(r'\s+','',value)
    blockers=[]
    if compact(failed['code'])!=compact(pure_wait):blockers.append('failed_call_contains_UI_trigger_or_unclassified_capability; provider boundary not proven')
    if compact(observed['code'])!=compact(pure_read):blockers.append('observation_is_not_a_pure_input_getter; caller no-click flags are not evidence')
    if {c.get('call_id')for c in calls}!={failed['call_id'],observed['call_id']}:
        blockers.append('additional_native_calls_in_reserved_interval_require_original_invocation_boundary')
    if 'Timed out after 10000ms waiting for file chooser.' not in failed['text']:blockers.append('exact_original_wait_failure_output_missing_or_ambiguous')
    # The supported pure getter emits this exact JSON; never use agent booleans.
    value=None
    for line in observed['text'].splitlines():
        try: parsed=json.loads(line)
        except ValueError:continue
        if isinstance(parsed,dict):
            if value is not None:blockers.append('ambiguous_observation_output')
            value=parsed
    if value!={'value':'','files':[]}:blockers.append('exact_actual_empty_input_output_missing_or_has_asset_or_success')
    return {'state':'BLOCKED_EVIDENCE_INSUFFICIENT'if blockers else'VERIFIED_PRE_PROVIDER_FAILURE_STAGE_ONLY',
            **{k:proof[k]for k in IDENTITY},'policy_decision_id':proof['policy_decision_id'],
            'original_request':proof['original_request'],'original_attempt':proof['original_attempt'],
            'failed_call_id':failed['call_id'],'observation_call_id':observed['call_id'],
            'canonical_call_lines':[{k:p[k]for k in ('call_id','canonical_lines','canonical_line_sha256')}for p in pairs],
            'provider_not_invoked_in_verified_interval':not blockers,'blockers':blockers,
            'scope_of_any_stage_record':'only original reserved non-invoking preparation interval; never account/server zero-effect certificate',
            'original_attempt_provider_effect':'UNKNOWN','original_policy_or_attempt_released':False,
            'actual_action_allowed':False,'retry_authorized':False,'new_permission_issued':False}


def record_failure_stage(root, proof, pin):
    """Append verified local stage only; existing policy/attempt guards remain."""
    with w.workflow_lock(root):
        need(doc(root,pin)==proof,'exact immutable failure-stage input bytes')
        checked=failure_stage_check(root,proof)
        need(checked['state']=='VERIFIED_PRE_PROVIDER_FAILURE_STAGE_ONLY','original provider boundary is not proven; keep UNKNOWN; use failure-check blockers')
        prior=[e for e in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS)if same(e.get('details',{}).get(FAILURE_EVENT,{}),proof)]
        need(not prior,'failure stage already recorded; no duplicate closure or concurrent retry')
        snapshot=w.read_json(w.snapshot_path(root,proof['task_id']))
        need(snapshot.get('current_state')not in w.TERMINAL_STATES,'closed goal is historical only')
        event=w.append_workflow_event(root,proof['task_id'],snapshot['current_state'],{FAILURE_EVENT:{**checked,'proof':pin}})
    return {'result':'recorded_stage_only','event_id':event['event_id'],'original_attempt_provider_effect':'UNKNOWN',
            'old_policy_request_attempt_unchanged':True,'actual_action_allowed':False,'retry_authorized':False}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', default=str(Path(__file__).resolve().parents[1]))
    p.add_argument('command', choices=['source-check', 'status', 'reserve','derive','effect-record','native-image-check','native-image-record','failure-check','failure-record','freeze-preflight','preflight','policy-check','issue'])
    p.add_argument('--input', required=True); p.add_argument('--decision-id')
    p.add_argument('--key');p.add_argument('--kind',choices=['group','upload','ad','budget']);p.add_argument('--output')
    args = p.parse_args(); root = Path(args.root).resolve(); item = w.read_json(w.safe_path(root, args.input))
    if args.command in {'native-image-check','native-image-record'}:
        out=(native_client_image_check(root,item)if args.command=='native-image-check'else record_native_client_image(root,item,w.file_digest(root,args.input)))
    elif args.command in {'failure-check','failure-record'}:
        out=(failure_stage_check(root,item)if args.command=='failure-check'else record_failure_stage(root,item,w.file_digest(root,args.input)))
    elif args.command=='derive':
        out=derive(root,w.file_digest(root,args.input),args.key,args.kind)
        if args.output:
            target=w.safe_path(root,args.output);need(not target.exists(),'immutable derived request output')
            w.atomic_write_json(target,out)
    elif args.command=='effect-record':
        out=record_effect(root,item)
    elif args.command=='freeze-preflight':
        need(args.output,'project-local immutable output directory')
        out=freeze_preflight(root,item,args.output)
    elif args.command=='preflight':
        from goal_delivery_runtime import record_preflight as normal_preflight
        out=normal_preflight(root,item['task_id'],args.input)
    elif args.command in {'policy-check','issue'}:
        need(item.get('schema')in {PREFLIGHT,OBJECT_PREFLIGHT},'normal object preflight input')
        q={k:item[k]for k in (*IDENTITY,'source_project_id')}
        out=w.policy_check(root,**q,payload_sha256=item['request']['sha256'],consume_approval=args.command=='issue')[0]
    elif args.command == 'source-check':
        c = source(root, item)
        out = ({'state':'PLAN_SOURCE_VALID_NOT_A_PERMIT','plan':item['supplement_plan']if item.get('schema')==SUPPLEMENT_SCHEMA else c['coordination']['exact_professional_plan'],
                'planned_actions':list(operation_specs(root,c)),'budget_limit':c['budget_limit'],'actual_action_allowed':False}
               if item.get('schema')in {PLAN_SCHEMA,SUPPLEMENT_SCHEMA} else
               {'state': 'SOURCE_VALID_NOT_A_PERMIT', 'request': c['packet']['request'], 'actual_action_allowed': False})
    elif args.command == 'reserve':
        out = reserve(root, item, args.decision_id)
    else:
        out = source_status(root,item,w.file_digest(root,args.input))
    print(json.dumps(out, ensure_ascii=False, indent=2))
    if args.command=='failure-check' and out.get('state')=='BLOCKED_EVIDENCE_INSUFFICIENT':raise SystemExit(2)


if __name__ == '__main__':
    main()
