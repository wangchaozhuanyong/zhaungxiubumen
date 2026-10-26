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
    rows = [(e, x) for e, x in rows if same(x, requested)]
    if not rows:
        return None
    need(len(rows) == 1, 'one immutable registered action')
    event, item = rows[0]; result = source(root, item)
    return {**result, 'registration': event['details'][EVENT], 'source_event_id': event['event_id']}


def checked_preflight(root, item, registered, *, fresh=True):
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
              and e.get('details', {}).get('professional_ads_object_preflight')]
    need(events, 'original professional fresh object preflight required; source registration is not permission')
    item = doc(root, events[-1]['details']['professional_ads_object_preflight'])
    req = checked_preflight(root, item, registered)
    need(requested.get('payload_sha256', item['request']['sha256']) == item['request']['sha256'], 'exact fresh request SHA')
    return {'action': {k: req[k] for k in IDENTITY}, 'request': req, 'pin': item['request'],
            'authorization': registered['authorization'], 'department': req['department'],
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


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', default=str(Path(__file__).resolve().parents[1]))
    p.add_argument('command', choices=['source-check', 'status', 'reserve'])
    p.add_argument('--input', required=True); p.add_argument('--decision-id')
    args = p.parse_args(); root = Path(args.root).resolve(); item = w.read_json(w.safe_path(root, args.input))
    if args.command == 'source-check':
        c = source(root, item)
        out = {'state': 'SOURCE_VALID_NOT_A_PERMIT', 'request': c['packet']['request'], 'actual_action_allowed': False}
    elif args.command == 'reserve':
        out = reserve(root, item, args.decision_id)
    else:
        m = match(root, w.read_json(w.snapshot_path(root, item['task_id'])), item)
        out = {'state': 'SOURCE_REGISTERED_FRESH_PREFLIGHT_REQUIRED' if m else 'SOURCE_NOT_REGISTERED',
               'source_registration': m['registration'] if m else None, 'actual_action_allowed': False}
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
