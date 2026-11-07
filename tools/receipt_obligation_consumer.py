"""Consume a committed receipt's next obligation on the existing owned dispatcher.

This module sends transport events/exact registered messages, never decides as a
human, creates a producer result, records READY, or grants production authority.
The workflow event journal owns one intent; original result records stay frozen.
"""
from pathlib import Path
import datetime as dt
import json
import re
import time
import workflow_control as w

OWNER_DELEGATION = {'path': 'reports/local-department-system-repair-20261030-v1/AUTONOMOUS-DELIVERY-REPAIR-20261104-v1/ACTUAL-OWNER-DELEGATION-SOURCE.json', 'sha256': '82f03e76d785bef3dd866ee7128b32c2d360a3ba08aff39faa071e37e4e714ec', 'size': 852}
SERVICE_ORIGIN = 'existing_owned_department_event_dispatcher'
MARKER = 'receipt_obligation'
PURPOSE = 'committed_receipt_system_continuation_event'
FIELDS = ('task_id','action_id','action_class','scope','source_project_id',
          'target_project_id','target_department','target_thread_id',
          'target_thread_title','target_cwd','target_sidebar_section_id','payload_sha256')
FORBIDDEN = {'approval_id','consume_approval','execution_request','execution_tuple',
             'execution_tuples','professional_execution_source','production_write_allowed',
             'permission_issued','qa_verdict','parent_task_id','goal_responsibility_dispatch',
             'business_goal_closed','result_notification','result_identity'}
VERIFIED = {'dispatch_sent','execution_verified','prior_action_verified',
            'inflight_result_verified','subsequent_action_verified','dependency_resolved',
            'internal_control_completed'}
WAITING = {'external_wait_registered','blocked_with_owner','no_executable_work'}


def require(ok, reason):
    if not ok:
        raise w.WorkflowError('receipt obligation: ' + reason)


def doc(root, pin):
    require(isinstance(pin,dict) and w.file_digest(root,pin.get('path','')) == pin,
            'unchanged project-owned source pin required')
    value = json.loads(w.safe_path(root,pin['path']).read_text())
    require(isinstance(value,dict), 'object source required')
    return value


def context(root, record, intake):
    """Authenticate frozen receiver AND the actual SQL/native handling actor."""
    import result_coordination as rc
    import department_autonomy as a
    import goal_delivery_runtime as g
    import chief_assistant_coordination as chief
    value = rc.exact_identity(record.get('identity',{}))
    route = rc.frozen_notification_route(root,record)
    require(rc.received_notification(root,record) == intake, 'one actual original committed intake required')
    rc._committed_result(root,intake)
    actor, owner = rc._committed_intake_actor(root,intake)
    logical = route['target_department']
    require(intake.get('target_department') == logical
            and intake.get('coordinator_role',logical) == actor
            and intake.get('coordinator_owner',owner) == owner,
            'frozen logical receiver and actual named actor/owner cannot change')
    if actor != logical:
        chief.receiver_context(root,intake,logical)  # real delegation; no generic A1 alias
    require(a.current_mode(root), 'current live authority withdrew the autonomous mode; historical pins cannot revive it')
    if actor in {'operations','operations-assistant'}:
        require(chief.authority(root) is not None and chief.actor_allowed(root,value,logical,actor),
                'current live delegated coordinator authority required; frozen source is not an irrevocable grant')
    a.authority(root)
    require(not w.validate_workflow_events(root,value['task_id']), 'intact original workflow event chain required')
    delegated = doc(root,OWNER_DELEGATION)
    require(delegated.get('project_root') == str(Path(root).resolve())
            and delegated.get('source') == 'first_party_read_thread'
            and delegated.get('role') == 'human'
            and delegated.get('message_id') == 'example-native-f438de429bc93cd7'
            and delegated.get('source_thread_id') == w.department_registry(root)['operations']['chat_binding']['task_id']
            and delegated.get('not_a_synthetic_authorization') is True,
            'exact actual new human delegation source required; service labels grant nothing')
    snapshot = g.restore_goal(root,w.read_json(w.snapshot_path(root,value['task_id'])))
    goal = snapshot.get('goal_delivery',{}); frozen = doc(root,snapshot.get('goal_contract'))
    immutable = ('primary_owner','producer_departments','authorized_scope','human_authorization','required_execution_actions')
    require(all(goal.get(k) == frozen.get(k) for k in immutable), 'unchanged frozen task/owner/producers/authority required')
    require(a.professional(root,goal.get('primary_owner')), 'current original professional owner required; retired actors cannot receive new work')
    box = doc(root,intake.get('outbox')); scope = box.get('scope')
    if scope is None and len(goal.get('authorized_scope',[])) == 1:
        scope = goal['authorized_scope'][0]
    require(box.get('task_id') == value['task_id'] == snapshot.get('task_id')
            and box.get('department') == value['sender_department']
            and intake['outbox']['sha256'] == value['result_sha256']
            and value['sender_department'] in goal.get('producer_departments',[])
            and value['sender_department'] not in a.ASSISTANTS
            and scope in goal.get('authorized_scope',[])
            and box.get('primary_owner',goal.get('primary_owner')) == goal.get('primary_owner'),
            'same original task/scope/current owner/declared producer required')
    require(logical in {'operations','operations-assistant',goal.get('primary_owner')}
            and (actor in {'operations','operations-assistant',goal.get('primary_owner')}),
            'only original owner or real delegated coordinator may consume a receipt')
    # A scope alone is not authority: retain and validate the real source bytes.
    doc(root,goal.get('authorization_pin'))
    return {'identity':value,'intake':intake,'record':record,'snapshot':snapshot,'goal':goal,
            'scope':scope,'original_owner':goal['primary_owner'],'logical_receiver':logical,
            'handling_actor':actor,'handling_owner':owner}


def _causal(root, value, ctx, depth=0, visited=None):
    """Bounded pinned data traversal; never execute a stored script/source file."""
    visited = set() if visited is None else visited
    if isinstance(value,list):
        return any(_causal(root,v,ctx,depth,visited) for v in value)
    if not isinstance(value,dict):
        return False
    if value == ctx['intake']['outbox']:
        return True
    receipt = value.get('received_record_id',value.get('receipt'))
    if (receipt == ctx['intake']['record_id'] and value.get('task_id') == ctx['identity']['task_id']
            and value.get('result_sha256') == ctx['identity']['result_sha256']
            and value.get('owner',ctx['original_owner']) == ctx['original_owner']):
        return True
    if (all(value.get(k) == v for k,v in ctx['identity'].items())
            and value.get('received_record_id') == ctx['intake']['record_id']):
        return True
    if set(value) == {'path','sha256','size'} and depth < 2:
        path = value.get('path','')
        if path.endswith('.json') and value.get('size',2**21) <= 2**20 and path not in visited:
            visited.add(path)
            return _causal(root,doc(root,value),ctx,depth+1,visited)
        return False
    return any(_causal(root,v,ctx,depth,visited) for v in value.values())


def successor(root, ctx):
    """Reuse a real native owner result causally following this exact receipt.

    This proves that the owner already continued, not acceptance/publication or
    full task completion. The newer result retains its own unsatisfied intake.
    """
    import result_coordination as rc
    rows = w._result_handoff_rows(root,ctx['identity']['task_id'])
    index = next(i for i,r in enumerate(rows) if r == ctx['intake'])
    for row in reversed(rows[index+1:]):
        if row.get('event') != 'notification_queued' or row.get('sender_department') != ctx['original_owner']:
            continue
        value = rc.exact_identity(row)
        queued = rc._validate_queued(root,value)  # validates actual native READY/final, not free text
        pin = queued.get('outbox') or row.get('outbox'); box = doc(root,pin)
        if (box.get('scope') != ctx['scope'] or box.get('primary_owner',ctx['original_owner']) != ctx['original_owner']
                or box.get('status') in {None,'','pending','in_progress','active'}):
            continue
        if _causal(root,box.get('evidence',[]),ctx):
            return {'state':'causal_owner_successor_proven','successor_identity':value,
                    'successor_record_id':row['record_id'],'successor_outbox':pin,
                    'original_receipt_obligation_transferred':True,'business_goal_closed':False}
    return None


def _ordinary_action(root, action, ctx):
    import goal_delivery_runtime as g
    import department_autonomy as a
    registry = w.department_registry(root)
    require(not any(k in action for k in FORBIDDEN), 'production/assignment/result fields are outside this consumer')
    require(action.get('action_class') == 'thread_message'
            and action.get('task_id') == ctx['identity']['task_id']
            and action.get('scope') == ctx['scope']
            and not action.get('authorization_changes') and not action.get('internal_repairs')
            and not action.get('assignment_record_required')
            and action.get('delivery_mode') in {None,'official_native_queue'}
            and action.get('sender_department') in {ctx['original_owner'],*ctx['goal']['producer_departments'],ctx['handling_actor']}
            and action.get('target_department') in {ctx['original_owner'],*ctx['goal']['producer_departments']}
            and action.get('target_department') in registry
            and action.get('sender_department') not in a.ASSISTANTS - {'operations-assistant'},
            'same-task ordinary registered owner/producer message only; external targets refused')
    for role in (action['sender_department'],action['target_department']):
        fixed = registry[role]['chat_binding']
        require(Path(fixed['cwd']).resolve() == Path(root).resolve()
                and fixed['project_id'] == a.PROJECT, 'same current project and directory required')
    requested = {k:action.get(k) for k in ('task_id','action_id','action_class','scope','payload_sha256','target_thread_id')}
    require(g.approved_action(root,ctx['snapshot'],requested) == action, 'one exact already-registered normal action required')
    target = registry[action['target_department']]['chat_binding']
    require(all(action.get(k) == target[v] for k,v in {'target_thread_id':'task_id','target_thread_title':'title',
            'target_cwd':'cwd','target_project_id':'project_id','target_sidebar_section_id':'sidebar_section_id'}.items()),
            'original current recipient cannot change')
    return action


def action_effect(root, ctx, action):
    """Any known intent/UNKNOWN wins over a new send; normal proofs rank effects."""
    import goal_delivery_runtime as g
    states = g._collaboration_wait_states(root,ctx['snapshot'],only_action_id=action['action_id'])
    if states:
        require(len(states) == 1, 'one original action effect required')
        item = states[0]
        return {'state':'original_action_' + item['status'], 'original_action_effect':item,
                'actionable':False, 'effect_unknown':item.get('proof_state') != 'PROVEN'}
    receipts, invalid = w._validate_receipt_chain(root,ctx['identity']['task_id'])
    require(not invalid, 'original receipt chain invalid; inspect original action before sending')
    same = [r for r in receipts if r.get('action_id') == action['action_id']
            and r.get('receipt_type') in {'dispatch_sent','chat_ack','outbox_received'}]
    if same:
        require(all(r.get('department') == action['target_department'] for r in same), 'original action recipient differs')
        return {'state':'original_action_receipt_proven','actionable':False,
                'receipt_ids':[r['receipt_id'] for r in same]}
    for e in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS,where={'task_id':ctx['identity']['task_id']}):
        for name in ('collaboration_queue_intent','native_queue_intent','dispatch_intent','routine_decision_reply_intent','receipt_obligation_intent'):
            item = e.get('details',{}).get(name,{})
            if item.get('action_id') == action['action_id']:
                return {'state':'original_action_intent_readback_required','actionable':False,
                        'original_intent':item,'effect_unknown':True}
    return None


def routine_semantics(root, ctx, decision):
    """Read normal chief rows without translating them into legacy enums/rows.

    A lease, preparation, accepted queue, ACK, or acknowledgement decision is
    never completion. A native causal owner result is stronger evidence; a
    bounded wait remains an open obligation with a real holder/input/time.
    """
    import chief_assistant_coordination as chief
    import result_coordination as rc
    if decision is None:
        return None
    if not decision.get('routine_delegation') and decision.get('decision') not in chief.DECISIONS:
        return None
    require(decision.get('routine_delegation') == chief.SOURCE
            and decision.get('decision') in chief.DECISIONS
            and rc.exact_identity(decision) == ctx['identity']
            and decision.get('received_record_id') == ctx['intake']['record_id']
            and decision.get('outbox') == ctx['intake']['outbox']
            and decision.get('scope') == ctx['scope']
            and decision.get('target_department') == ctx['logical_receiver']
            and decision.get('coordinator_role') == ctx['handling_actor']
            and decision.get('coordinator_owner') == ctx['handling_owner'],
            'normal routine decision must retain the exact receipt/result/scope/real actor and frozen receiver')
    rc._committed_result(root,decision)
    require(rc._committed_intake_actor(root,decision) == (ctx['handling_actor'],ctx['handling_owner']),
            'actual SQL/native decision actor differs from original intake')
    chief.receiver_context(root,decision,ctx['logical_receiver'])
    # Existing helper authenticates original decision_source + actual actor's
    # native message naming its precise path/SHA. Discard its generated return
    # row: this adapter never appends or changes a decision/followthrough.
    chief.decision(root,decision)
    source = chief.doc(root,decision['decision_source'])
    at = w._parse_observed_at(decision.get('created_at'))
    require(at is not None,'actual original routine decision time required')
    semantics = {'original_decision_record_id':decision['record_id'],
        'original_decision':decision['decision'],'original_decision_source':decision['decision_source'],
        'received_record_id':ctx['intake']['record_id'],'handling_actor':ctx['handling_actor'],
        'logical_receiver':ctx['logical_receiver'],'next_owner':decision['next_owner'],
        'compatibility_row_written':False,'original_name_preserved':True,
        'acceptance_proven':False,'qa_proven':False,'external_permission_issued':False,
        'business_goal_closed':False,'actionable':False}
    if decision['decision'] == 'wait_exact_dependency':
        holder = source.get('next_owner'); trigger = source.get('unblock_condition')
        revisit = w._parse_observed_at(source.get('next_check_at'))
        evidence = source.get('evidence') or decision.get('evidence')
        require(holder == ctx['original_owner'] and isinstance(trigger,str) and trigger.strip()
                and revisit is not None and isinstance(evidence,list) and evidence
                and all(isinstance(p,dict) and w.file_digest(root,p.get('path','')) == p for p in evidence),
                'routine wait requires a named original holder, exact release trigger, time and frozen evidence')
        return {**semantics,'state':'routine_named_dependency_wait' if revisit > dt.datetime.now(dt.timezone.utc) else 'routine_dependency_due',
                'dependency_owner':holder,'unblock_condition':trigger,'next_check_at':source['next_check_at'],
                'evidence':evidence,'obligation_completed':False}
    if decision['decision'] in {'acknowledge_completed_scope','escalate_sensitive'}:
        return {**semantics,'state':'routine_acknowledgement_only' if decision['decision'] == 'acknowledge_completed_scope' else 'routine_sensitive_escalation_pending',
                'obligation_completed':False}
    later = successor(root,ctx); causal = None
    if later:
        row = next(r for r in w._result_handoff_rows(root,ctx['identity']['task_id'])
                   if r.get('record_id') == later['successor_record_id'])
        created = w._parse_observed_at(row.get('created_at'))
        if created is not None and created >= at:
            causal = later  # still inspect every already-existing normal reply below
    # Find the real normal reply by its immutable decision ID, never an old
    # lease, similar message text, or an arbitrary caller-provided action ID.
    replies = [e['details']['routine_decision_reply_intent'] for e in
        w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS,where={'task_id':ctx['identity']['task_id']})
        if e.get('details',{}).get('routine_decision_reply_intent',{}).get('decision_record_id') == decision['record_id']]
    require(len(replies) <= 1,'ambiguous normal reply for this exact routine decision; inspect original keys')
    if not replies:
        return ({**semantics,'state':'routine_causal_followthrough_proven',
                 'causal_successor':causal,'obligation_completed':True} if causal is not None else
                {**semantics,'state':'routine_decision_awaiting_actual_followthrough','obligation_completed':False})
    intent = replies[0]; request = chief.doc(root,intent['request'])
    marker = request.get('routine_decision_reply',{})
    require(rc.exact_identity(marker) == ctx['identity']
            and marker.get('decision_record_id') == decision['record_id']
            and request.get('task_id') == ctx['identity']['task_id']
            and request.get('scope') == ctx['scope']
            and request.get('sender_department') == intent.get('handling_actor') == ctx['handling_actor']
            and request.get('target_department') == intent.get('target_department') == decision['next_owner'] == ctx['original_owner']
            and request.get('action_class') == 'thread_message'
            and request.get('delivery_mode') == 'official_native_queue',
            'normal reply must be this exact decision/receipt/identity/actor/original next owner')
    effect = chief.reply_effect(root,ctx['identity']['task_id'],intent['action_id'])
    require(effect.get('intent') == intent,'normal helper returned a different reply intent')
    route = chief.message_route(root,ctx['snapshot'],request)
    require(route and route.get('purpose') == 'routine_decision_direct_reply'
            and route.get('decision_record_id') == decision['record_id'],
            'normal original-decision reply route required')
    directory = w.safe_path(root,intent['directory']); prepared = w.read_json(directory/'normal-preparation.json')
    policy = prepared.get('policy_decision',{})
    policies = [p for p in w.read_jsonl(Path(root)/w.POLICY_DECISIONS) if p.get('decision_id') == intent.get('policy_decision_id')]
    require(policies == [policy] and policy.get('status') == 'allow'
            and policy.get('department') == ctx['handling_actor']
            and policy.get('routing_status') == 'routing_allowed'
            and not policy.get('approval_id') and not policy.get('consume_approval')
            and prepared.get('status') == 'ready_to_queue' and prepared.get('payload') == request.get('payload')
            and policy.get('external_permission_issued') is False
            and all(policy.get(k) == request.get(k) for k in FIELDS),
            'exact original normal reply preparation/policy source required')
    readback_intent = {**intent,'normal_preparation':w.file_digest(root,str((directory/'normal-preparation.json').relative_to(root)))}
    native_path = directory/'native-queue-intent.json'
    native = w.read_json(native_path) if native_path.exists() else {}
    sent_at = w._parse_observed_at(native.get('started_at'))
    if effect.get('state') == 'official_queue_accepted_not_received':
        checked = w._parse_observed_at(policy.get('checked_at'))
        require(native.get('thread_id') == request['target_thread_id']
                and native.get('payload_sha256') == request['payload_sha256']
                and native.get('policy_decision_id') == policy['decision_id']
                and native.get('transport') == 'official_codex_queue'
                and checked is not None and sent_at is not None
                and at <= checked <= sent_at <= dt.datetime.now(dt.timezone.utc),
                'actual original routine reply intent/policy chronology required')
    cutoff = max(at,sent_at) if sent_at is not None else at
    receipts, invalid = w._validate_receipt_chain(root,ctx['identity']['task_id'])
    require(not invalid,'intact original receipt chain before routine reply semantic advancement')
    exact = [r for r in receipts if r.get('task_id') == ctx['identity']['task_id']
        and r.get('action_id') == intent['action_id'] and r.get('scope') == ctx['scope']
        and r.get('department') == ctx['original_owner']
        and r.get('payload_sha256',request['payload_sha256']) == request['payload_sha256']
        and w._parse_observed_at(r.get('created_at')) is not None
        and w._parse_observed_at(r['created_at']) >= cutoff]
    ack = [r for r in exact if r.get('receipt_type') == 'chat_ack']
    results = [r for r in exact if r.get('receipt_type') == 'outbox_received'
               and any(w._parse_observed_at(r['created_at']) >= w._parse_observed_at(a['created_at']) for a in ack)]
    native_owner_handoff = registered_owner_handoff(root,ctx,decision,intent)
    if native_owner_handoff is not None:
        return {**semantics,'state':'routine_native_owner_handoff_proven','normal_reply_effect':effect,
                'routine_reply_intent':readback_intent,'native_owner_handoff':native_owner_handoff,
                'coordination_obligation_only':True,'coordination_obligation_completed':True,
                'queue_acceptance_is_completion':False,'obligation_completed':True}
    proven = causal is not None or effect.get('state') == 'official_queue_accepted_not_received' and bool(ack and results)
    return {**semantics,'state':'routine_causal_followthrough_proven' if causal is not None else
                'routine_reply_followthrough_proven' if proven else 'routine_reply_awaiting_actual_followthrough',
            **({'causal_successor':causal} if causal is not None else {}),
            'normal_reply_effect':effect,'routine_reply_intent':readback_intent,
            'ack_receipt_ids':[r['receipt_id'] for r in ack],
            'result_receipt_ids':[r['receipt_id'] for r in results],
            'queue_acceptance_is_completion':False,'obligation_completed':proven}


def project(root, record, intake):
    """Read-only next-obligation projection, never completed by receipt alone."""
    from department_event_dispatcher import _handoff_effect
    from chief_assistant_coordination import notification_task_pause
    ctx = context(root,record,intake); handoff = _handoff_effect(root,record,intake)
    base = {**ctx['identity'],'kind':'received_next_obligation','scope':ctx['scope'],
            'received_record_id':intake['record_id'],'original_owner':ctx['original_owner'],
            'logical_receiver':ctx['logical_receiver'],'handling_actor':ctx['handling_actor'],
            'transport_resolved_by_actual_intake':True,'receipt_is_business_completion':False,
            'business_goal_closed':False,'external_permission_issued':False,'actionable':False}
    pause = notification_task_pause(root,ctx['identity']['task_id'])
    if pause or ctx['snapshot'].get('current_state') in w.TERMINAL_STATES:
        return {**base,'state':'original_task_boundary_wait','owner_pause':pause}
    if handoff.get('next_step_status') in VERIFIED:
        return {**base,'state':'normal_followthrough_proven','normal_followthrough':handoff}
    if handoff.get('next_step_status') in WAITING:
        due = w._parse_observed_at(handoff.get('next_check_at'))
        require(handoff.get('next_owner') and handoff.get('unblock_condition') and due,
                'named exact dependency owner, release input and next check required')
        if due > dt.datetime.now(dt.timezone.utc):
            return {**base,'state':'named_future_dependency_wait','normal_followthrough':handoff}
    same = [r for r in w._result_handoff_rows(root,ctx['identity']['task_id'])
            if r.get('record_id') == handoff.get('decision_record_id')]
    routine = routine_semantics(root,ctx,same[0] if same else None)
    if routine is not None:
        base['routine_semantics'] = routine
        if routine.get('obligation_completed'):
            return {**base,'state':'routine_followthrough_proven'}
        if routine['state'] == 'routine_named_dependency_wait':
            return {**base,'state':'named_future_dependency_wait','next_owner':routine['dependency_owner'],
                    'unblock_condition':routine['unblock_condition'],'next_check_at':routine['next_check_at'],
                    'normal_followthrough':handoff}
        if routine['state'] == 'routine_reply_awaiting_actual_followthrough':
            return {**base,'state':'routine_reply_awaiting_actual_followthrough'}
    later = successor(root,ctx)
    if later:
        return {**base,**later}
    for action in ctx['goal'].get('approved_actions',[]):
        linked = action.get('decision_record_id') in {r['record_id'] for r in same}
        if not linked and not _causal(root,{k:v for k,v in action.items() if k != 'payload'},ctx):
            continue
        _ordinary_action(root,action,ctx)
        effect = action_effect(root,ctx,action)
        if effect:
            return {**base,**effect}
        return {**base,'state':'registered_ordinary_action_ready','actionable':True,'action':action}
    # The event goes to its real receiver, not a fabricated new handler/producer.
    target = ctx['handling_actor'] if ctx['handling_actor'] in {'operations','operations-assistant'} else ctx['original_owner']
    generation = [intake['record_id'],handoff.get('decision_record_id'),handoff.get('next_action_record_id')]
    return {**base,'state':'ordinary_handler_action_required','actionable':True,'next_owner':target,
            'action_id':'receipt-followthrough-' + w.sha256_value(generation)[:40],
            'trigger_fingerprint':w.sha256_value(generation),'normal_followthrough':handoff}


def body(view):
    facts = {k:view[k] for k in ('task_id','sender_department','candidate_version','result_sha256',
             'scope','received_record_id','original_owner','logical_receiver','handling_actor','next_owner','trigger_fingerprint')}
    facts.update(service_origin=SERVICE_ORIGIN,owner_delegation=OWNER_DELEGATION)
    return ('【系统实收后接续事件；不是老板新授权、producer回复或技术审批】\n'
            + json.dumps(facts,ensure_ascii=False,sort_keys=True) + '\n'
            + 'FLASHCAST_RECEIPT_OBLIGATION ' + view['action_id'] + '\n'
            + '原结果已实收，不得重收或重发。请在本真实原窗口沿原task/scope处理下一义务：'
              '普通判断由真实总助理优先、HQ补位；专业owner连续落实已有授权且输入齐全的后继，'
              '经原prepare/policy核原发送键和接单/后续结果。已有可验证后继须复用。'
              '需要等待时在真实普通决定及原证据中登记具名owner、解除输入和复查时间；已有合法followthrough保留，不补造兼容行。'
              '已取消或明确暂停的原范围保持停止，只接续当前未取消的合法范围；索引final_goal_closed=false不是授权。'
              '保留冻结receiver和真实actor，不代造producer/READY/ACK，不增生产、账号、费用、部署或外部发送权限。'
              '回报须点名原task、received_record_id和本action_id；入队或ACK本身不算业务完成。\n')


def _sdk_supplement_matches(root, role, fixed, canonical, supplied):
    """Authenticate current SDK and inventory against the exact canonical turn."""
    require(isinstance(supplied,dict) and set(supplied)=={'native','inventory'}, 'DATA_MISSING exact SDK native and project inventory pins')
    sdk=doc(root,supplied['native']); inv=doc(root,supplied['inventory'])
    require(sdk.get('source')=='first_party_read_thread' and inv.get('source')=='first_party_list_threads', 'actual first-party read and inventory required')
    now=dt.datetime.now(dt.timezone.utc)
    for value in (sdk,inv):
        at=w._parse_observed_at(value.get('observed_at_UTC'))
        require(at is not None and 0 <= (now-at).total_seconds() <= 300, 'fresh SDK source observation required')
    page=sdk.get('native',{}); thread=page.get('thread',{}); target=canonical.get('thread',{})
    mapping={'id':'task_id','title':'title','cwd':'cwd','hostId':'host_id'}
    require(all(thread.get(k)==fixed.get(v) for k,v in mapping.items()) and thread.get('kind')=='codex', 'exact SDK fixed role identity required')
    require(target.get('id')==thread.get('id') and (target.get('title') or target.get('name'))==thread.get('title') and target.get('cwd')==thread.get('cwd') and all(target.get(k) in (None,thread.get(k)) for k in ('hostId','kind')) and all(t.get('projectId') in (None,fixed.get('project_id')) for t in (thread,target)), 'canonical and SDK thread must match without invented fields')
    turns=page.get('turns',[]); actual=canonical.get('turns',[])
    require(isinstance(turns,list) and isinstance(actual,list) and len(turns)>0 and len(actual)>0 and all(turns[0].get(k)==actual[0].get(k) for k in ('id','status','error')) and turns[0].get('status') in {'completed','inProgress','pending'} and not turns[0].get('error'), 'exact same latest real canonical SDK turn required')
    rows=inv.get('native',{}); require(isinstance(rows,dict), 'actual first-party inventory required')
    threads=rows.get('threads',[]); pinned=rows.get('pinnedThreads',[])
    require(isinstance(threads,list) and isinstance(pinned,list), 'actual SDK inventory arrays required')
    matches=[x for x in [*threads,*pinned] if isinstance(x,dict) and x.get('id')==fixed['task_id']]
    require(len(matches)==1 and all(matches[0].get(k)==fixed.get(v) for k,v in {'id':'task_id','title':'title','cwd':'cwd','hostId':'host_id','projectId':'project_id'}.items()) and matches[0].get('kind')=='codex', 'exact current SDK project inventory required')
    return True


def event_route(root, snapshot, request):
    """Narrow normal-policy route for a deterministic transport-only event."""
    marker = request.get(MARKER)
    if marker is None:
        return None
    allowed = set(FIELDS) | {'sender_department','payload','actual_sender_state','actual_target_state',
                'live_observed_at','delivery_mode','authorization_changes','service_origin','owner_delegation',MARKER}
    require(set(request) in (allowed, allowed | {'actual_native_sources'}) and request['authorization_changes'] == []
            and request.get('action_class') == 'thread_message' and request.get('delivery_mode') == 'official_native_queue'
            and request.get('service_origin') == SERVICE_ORIGIN and request.get('owner_delegation') == OWNER_DELEGATION,
            'exact transport-only event fields required; no production or arbitrary action fields')
    require(isinstance(marker,dict) and set(marker) == {'notification','received_record_id','trigger_fingerprint'},
            'one original receipt event source required')
    record = doc(root,marker['notification'])
    import result_coordination as rc
    intake = rc.received_notification(root,record)
    require(intake and intake['record_id'] == marker['received_record_id'], 'same real receipt required')
    view = project(root,record,intake); ctx = context(root,record,intake)
    require(snapshot['task_id'] == view['task_id'] == request['task_id']
            and view['state'] == 'ordinary_handler_action_required' and view['actionable']
            and marker['trigger_fingerprint'] == view['trigger_fingerprint']
            and request['action_id'] == view['action_id'] and request['scope'] == view['scope']
            and request['sender_department'] == view['handling_actor']
            and request['target_department'] == view['next_owner'],
            'same active original obligation, real sender/handler and scope required')
    shared = shared_serial_guard(root,target_thread_id=request['target_thread_id'])
    require(shared.get('new_activation_allowed') is True,'root serial blocks ordinary event: '+str(shared.get('reasons')))
    require(not _intents(root,view['task_id'],view['action_id']), 'original receipt continuation intent exists; inspect original effect')
    registry = w.department_registry(root)
    import department_autonomy as a
    import goal_delivery_runtime as g
    observed = w._parse_observed_at(request.get('live_observed_at'))
    require(observed and 0 <= (dt.datetime.now(dt.timezone.utc)-observed).total_seconds() <= 300,
            'fresh actual observation required')
    for field,role in (('actual_sender_state',request['sender_department']),('actual_target_state',request['target_department'])):
        fixed = registry[role]['chat_binding']; page = g._collaboration_native(root,request[field])
        require(registry[role].get('new_dispatch_enabled') is True and w._chat_binding_healthy(fixed,verification_ttl_hours=26)
                and fixed['project_id'] == a.PROJECT and Path(fixed['cwd']).resolve() == Path(root).resolve()
                and all(page.get('thread',{}).get(k) == fixed[v] for k,v in
                        {'id':'task_id','title':'title','cwd':'cwd'}.items()) and page.get('turns')
                and page['turns'][0].get('status') in {'completed','inProgress','pending'}
                and not page['turns'][0].get('error'), 'real current healthy fixed role/native turn required')
        sources=request.get('actual_native_sources')
        if sources is not None:
            require(isinstance(sources,dict) and set(sources)=={request['sender_department'],request['target_department']}, 'exact sender/target SDK sources required')
            _sdk_supplement_matches(root,role,fixed,page,sources[role])
        else:
            require(page['thread'].get('hostId') == fixed['host_id'] and page['thread'].get('kind') == 'codex', 'DATA_MISSING original SDK host/kind; canonical-only identity denied')
    source = registry[request['sender_department']]['chat_binding']; target = registry[request['target_department']]['chat_binding']
    require(request['source_project_id'] == source['project_id']
            and all(request.get(k) == target[v] for k,v in {'target_project_id':'project_id','target_thread_id':'task_id',
                'target_thread_title':'title','target_cwd':'cwd','target_sidebar_section_id':'sidebar_section_id'}.items()),
            'exact original same-project recipient required')
    require(w.file_digest(root,request['payload'].get('path','')) == request['payload']
            and request['payload']['sha256'] == request['payload_sha256']
            and w.safe_path(root,request['payload']['path']).read_text() == body(view),
            'deterministic system event only; free-text next_actions cannot become authority')
    return {'mode':a.MODE,'purpose':PURPOSE,'source':request['payload'],'scope':view['scope'],
            'sender_department':request['sender_department'],'target_department':request['target_department'],
            'received_record_id':intake['record_id'],'logical_receiver':ctx['logical_receiver'],
            'handling_actor':ctx['handling_actor'],'handling_owner':ctx['handling_owner'],
            'external_permission_issued':False,'business_producer_added':False,'system_event_only':True,
            'service_origin':SERVICE_ORIGIN,'owner_delegation':OWNER_DELEGATION,
            'root_serial_source':shared['source']}


def prepare_message(root, request):
    """Normal policy entry for this exact event, no permission-result shortcut."""
    import goal_delivery_runtime as g
    snapshot = g.restore_goal(root,w.read_json(w.snapshot_path(root,request['task_id'])))
    event_route(root,snapshot,request)
    policy, _ = w.policy_check(root,department=request['sender_department'],
            **{k:request[k] for k in FIELDS},delivery_mode='official_native_queue',original_message=request)
    return {'status':'ready_to_queue' if policy['status'] == 'allow' else 'blocked',
            'policy_decision':policy,'payload':request['payload'],'delivery_mode':'official_native_queue',
            'ordinary_send_allowed':False,'message_sent':False,'external_permission_issued':False}


ROOT_SERIAL_PATH = 'logs/handoffs/2026-10-28-serial-original-window-recovery-v1/operations/EXACT-SERIAL-RESUME-INTENT.json'
ROOT_SERIAL_SLOT = 'root-original-window-serial-slot'


def _root_serial_read(root):
    """Fresh bytes, not a cached permission or an old index summary."""
    import hashlib
    path = w.safe_path(root,ROOT_SERIAL_PATH)
    require(path.is_file() and not path.is_symlink(),'DATA_MISSING root serial record')
    raw = path.read_bytes()
    def unique(pairs):
        value = {}
        for key,item in pairs:
            require(key not in value,'contradictory duplicate root serial field')
            value[key] = item
        return value
    record = json.loads(raw,object_pairs_hook=unique)
    require(isinstance(record,dict),'DATA_MISSING root serial object')
    pin = {'path':ROOT_SERIAL_PATH,'sha256':hashlib.sha256(raw).hexdigest(),'size':len(raw)}
    return record,pin


def _root_serial_native(page, window, turn_id, observed):
    """Accept the normal read_thread or compact first-party wait projection."""
    require(isinstance(page,dict) and page.get('isError',False) is False
            and not page.get('error') and page.get('truncated',False) is False,
            'UNKNOWN root native source failure')
    value = page.get('native',page.get('actual',page))
    if isinstance(value,dict) and isinstance(value.get('polls'),list):
        rows = [p for p in value['polls'] if p.get('thread',{}).get('id') == window]
        require(len(rows) == 1,'DATA_MISSING one exact root native poll')
        poll = rows[0]; latest = dict(poll.get('latestTurn') or {}); message = poll.get('latestAssistantMessage')
        require(isinstance(message,dict) and message.get('turnId') == latest.get('id'),
                'DATA_MISSING root final belongs to exact completed turn')
        latest['items'] = [message]
        value = {'thread':poll['thread'],'turns':[latest]}
    require(isinstance(value,dict) and value.get('thread',{}).get('id') == window,
            'contradictory root native original window')
    state = value['thread'].get('status',{})
    state = state.get('type') if isinstance(state,dict) else state
    require(state in {None,'idle','notLoaded'},'root original window is active or UNKNOWN')
    turns = value.get('turns',[])
    require(isinstance(turns,list) and turns,'DATA_MISSING root native turn')
    require(all(isinstance(t.get('startedAt'),(int,float)) for t in turns),
            'DATA_MISSING ordered root native turns')
    latest = max(turns,key=lambda t:t['startedAt'])
    require(latest.get('id') == turn_id and latest.get('status') == 'completed'
            and not latest.get('error'),'root current turn active/UNKNOWN/changed; no new activation')
    finish = latest.get('completedAt')
    require(isinstance(finish,(int,float)) and latest['startedAt'] <= finish <= observed.timestamp(),
            'contradictory root native completion time')
    finals = [m for m in latest.get('items',[]) if m.get('type') == 'agentMessage'
              and m.get('phase') == 'final_answer' and isinstance(m.get('text'),str) and m['text'].strip()]
    require(len(finals) == 1 and finals[0].get('id'),'DATA_MISSING one actual nonempty root final')
    return value['thread'],latest,finals[0]


def _root_safe_dependency(root, wait, box, final):
    require(isinstance(wait,dict) and all(isinstance(wait.get(k),str) and wait[k].strip()
            for k in ('owner','action','dependency_input')) and wait['owner'] in w.department_registry(root),
            'DATA_MISSING exact safe dependency owner/action/input')
    stated = box.get('safe_dependency')
    structured = isinstance(stated,dict) and all(stated.get(k) == wait[k] for k in ('owner','action','dependency_input'))
    native = all(wait[k] in final['text'] for k in ('owner','action','dependency_input'))
    require(structured or native,'safe dependency is not stated by the exact normal batch/native final')


def _root_commentary_ready(turn):
    """Read one structured READY declaration from the completed turn."""
    from qa_review_plan import _review_native_containers

    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('duplicate original READY field')
            result[key] = value
        return result

    declarations = []
    for message in turn.get('items', []):
        if message.get('type') != 'agentMessage' or message.get('phase') != 'commentary':
            continue
        _review_native_containers(message)
        for line in str(message.get('text', '')).splitlines():
            if line.startswith('FLASHCAST_DELIVERY_READY '):
                declarations.append(json.loads(line[len('FLASHCAST_DELIVERY_READY '):], object_pairs_hook=unique))
    return declarations[0] if len(declarations) == 1 else None


def _root_same_turn_ready_report(root, proof, record, final, identity, pin, box):
    """Bind an exact queued finite batch through its real same-turn READY.

    The completed final must also name an unchanged evidence artifact from
    that outbox. A generic maintenance final, ACK or another turn cannot pass.
    Normal queue/producer/outbox checks remain in _root_serial_batch.
    """
    try:
        _, turn, actual_final = _root_serial_native(
            proof, record['current_active_original_window'],
            record['current_active_turn'], dt.datetime.now(dt.timezone.utc))
        if actual_final.get('id') != final.get('id') or actual_final.get('text') != final.get('text'):
            return False
        ready = _root_commentary_ready(turn)
        if (not isinstance(ready, dict) or set(ready) != set(identity) | {'outbox_path', 'batch_complete'}
                or ready.get('batch_complete') is not True
                or any(ready.get(key) != value for key, value in identity.items())
                or ready.get('outbox_path') != pin['path']):
            return False
        evidence = box.get('evidence', [])
        if not isinstance(evidence, list):
            return False
        return any(isinstance(item, dict) and set(item) == {'path', 'sha256', 'size'}
                   and isinstance(item.get('path'), str) and item['path']
                   and item['path'] in final['text'] and w.file_digest(root, item['path']) == item
                   for item in evidence)
    except (w.WorkflowError, ValueError, OSError, KeyError, TypeError, AttributeError):
        return False


def _root_same_turn_queued_report(root, proof, record, final, identity, pin, box, queued):
    """A committed original notification binds its exact native delivery reply.

    Older normal producer replies use the admitted key/value READY format.
    Read the already validated queue source, rather than inventing JSON READY
    or requiring the final to repeat its SHA. This proves a finite batch only.
    """
    import hashlib
    try:
        _, turn, actual_final = _root_serial_native(
            proof, record['current_active_original_window'],
            record['current_active_turn'], dt.datetime.now(dt.timezone.utc))
        if (actual_final != final or str(box.get('status', '')).lower() != 'completed'
                or box.get('batch_complete') is False
                or queued.get('event') != 'notification_queued'
                or not queued.get('record_id')
                or queued.get('result_source_phase') != 'delivery_ready'
                or queued.get('outbox') != pin
                or any(queued.get(key) != value for key, value in identity.items())
                or queued.get('source_thread_id') != record['current_active_original_window']
                or queued.get('source_turn_id') != turn['id']):
            return False
        messages = [item for item in turn.get('items', [])
                    if item.get('type') == 'agentMessage' and item.get('phase') == 'commentary'
                    and item.get('id') == queued.get('source_message_id')
                    and isinstance(item.get('text'), str)]
        if (len(messages) != 1
                or hashlib.sha256(messages[0]['text'].encode()).hexdigest()
                    != queued.get('source_reply_sha256')):
            return False
        if ('primary_deliverable' in box and 'primary_delivery' in box
                and box['primary_deliverable'] != box['primary_delivery']):
            return False
        evidence = box.get('primary_deliverable', box.get('primary_delivery'))
        return (isinstance(evidence, dict) and set(evidence) == {'path', 'sha256', 'size'}
                and isinstance(evidence.get('path'), str) and bool(evidence['path'])
                and evidence['path'] in final['text']
                and evidence in box.get('evidence', [])
                and w.file_digest(root, evidence['path']) == evidence)
    except (w.WorkflowError, ValueError, OSError, KeyError, TypeError, AttributeError):
        return False


def _hq_intake_batch(root, proof, record, final):
    """Read back an admitted HQ intake; it never prepares or grants an action."""
    import chief_assistant_coordination as chief
    import department_autonomy as autonomy
    import goal_delivery_runtime as goal
    import result_coordination as rc
    packet_pin = proof.get('hq_intake_batch')
    packet = doc(root, packet_pin)
    require(set(packet) == {'schema','request','preparation','queue_intent','queue_result'}
            and packet['schema'] == 'hq-original-result-intake-finite-batch/v1', 'exact HQ finite intake packet')
    request, normal, intent, effect = [doc(root,packet[k]) for k in
                                     ('request','preparation','queue_intent','queue_result')]
    fields = ('task_id','action_id','action_class','scope','source_project_id','target_project_id',
              'target_department','target_thread_id','target_thread_title','target_cwd',
              'target_sidebar_section_id','payload_sha256')
    require(request.get('sender_department') == 'operations'
            and request.get('target_department') == 'operations-assistant'
            and request.get('action_class') == 'thread_message'
            and request.get('delivery_mode') == 'official_native_queue'
            and not any(request.get(k) for k in ('authorization_changes','approval_id','consume_approval',
                'execution_request','permission_issued','production_write_allowed','assignment_record_required')),
            'original HQ intake transport only')
    require(chief.authority(root) is not None, 'authentic current chief delegation')
    autonomy.authority(root)
    snapshot = goal.restore_goal(root,w.read_json(w.snapshot_path(root,request['task_id'])))
    frozen = doc(root,snapshot.get('goal_contract'))
    current_goal = snapshot['goal_delivery']
    require(snapshot.get('current_state') not in w.TERMINAL_STATES
            and request['scope'] in current_goal.get('authorized_scope',[])
            and all(current_goal.get(k) == frozen.get(k) for k in ('primary_owner','producer_departments',
                'authorized_scope','human_authorization','required_execution_actions')), 'unchanged open original goal')
    history = chief.ordinary_source_history(root,request['task_id'])
    chief._ordinary_original_task(root,snapshot,frozen,history)
    source = chief._hq_original_queued_intake(root,snapshot,request,current_goal,require_pending=False)
    require(normal.get('status') == 'ready_to_queue'
            and normal.get('delivery_mode') == 'official_native_queue'
            and all(normal.get(k) is False for k in ('message_sent','external_permission_issued','ordinary_send_allowed'))
            and normal.get('payload') == request.get('payload'), 'actual normal queued preparation')
    policy = normal.get('policy_decision',{})
    policies = w.read_jsonl(Path(root)/w.POLICY_DECISIONS,where={'decision_id':policy.get('decision_id')})
    require(policies == [policy] and policy.get('status') == 'allow'
            and policy.get('department') == 'operations' and policy.get('external_permission_issued') is False
            and all(policy.get(k) == request.get(k) for k in fields)
            and policy.get('routine_delegation') == chief.SOURCE,
            'one genuine original normal policy for exact HQ request')
    require(policy.get('routine_message_source') == {
                'goal_contract':snapshot['goal_contract'],'routine_delegation':chief.SOURCE,
                'payload':request['payload'],'live_observed_at':request['live_observed_at'],
                'actual_sender_state':request['actual_sender_state'],'actual_target_state':request['actual_target_state'],
                'external_permission_issued':False}, 'unchanged actual normal source facts')
    checked, start, finish = [w._parse_observed_at(x) for x in
                            (policy.get('checked_at'),intent.get('started_at'),effect.get('finished_at'))]
    now = dt.datetime.now(dt.timezone.utc)
    accepted = re.fullmatch(r'Queued message ([0-9a-f-]{36}) for thread ([0-9a-f-]{36})\.\s*',effect.get('stdout',''))
    require(checked is not None and start is not None and finish is not None
            and checked <= start <= finish <= now and (start-checked).total_seconds() <= 300
            and type(effect.get('exit_code')) is int and effect['exit_code'] == 0
            and isinstance(effect.get('stderr'),str) and accepted and accepted[2] == request['target_thread_id']
            and all(effect.get(k) == v for k,v in intent.items())
            and intent.get('transport') == 'official_codex_queue' and intent.get('intake_claimed') is False
            and intent.get('thread_id') == request['target_thread_id']
            and intent.get('payload_sha256') == request['payload_sha256']
            and intent.get('policy_decision_id') == policy['decision_id'], 'exact original queue effect, not UNKNOWN')
    require(record.get('current_active_original_window') == request['target_thread_id']
            and record.get('current_scope') == request['scope']
            and record.get('current_action_id') == request['action_id']
            and record.get('current_hq_intake_batch') == packet_pin, 'same original HQ intake boundary')
    thread,turn,actual_final = _root_serial_native(proof,request['target_thread_id'],record['current_active_turn'],now)
    require(actual_final == final and start.timestamp() <= turn['startedAt'] <= turn['completedAt'],
            'actual complete recipient turn follows original queue')
    fixed = w.department_registry(root)['operations-assistant']['chat_binding']
    actual_target = goal._collaboration_native(root,request['actual_target_state'])['thread']
    require(all(actual_target.get(k) == fixed[v] for k,v in
                {'id':'task_id','title':'title','cwd':'cwd','hostId':'host_id'}.items())
            and thread.get('name',thread.get('title')) == fixed['title']
            and thread.get('cwd') == fixed['cwd'] and thread.get('hostId') in {None,fixed['host_id']}
            and thread.get('projectId') in {None,fixed['project_id']}, 'real same fixed recipient metadata')
    wanted = w.safe_path(root,request['payload']['path']).read_text()
    items = turn.get('items',[])
    inputs = [(n,m) for n,m in enumerate(items) if m.get('type') == 'userMessage'
              and _exact_notification_text_content(m.get('content'),wanted)]
    require(len(inputs) == 1, 'one exact original HQ queue input')
    final_positions = [n for n,m in enumerate(items) if m == final]
    require(len(final_positions) == 1, 'one actual finite final position')
    store = rc.CoordinationStore(root)
    receipts = []
    try:
        for entry in source['results']:
            identity = rc.exact_identity(entry['identity'])
            rows = [x for x in chief.rows(root,identity) if x.get('event') == 'controller_received']
            require(len(rows) == 1, 'one actual original result intake')
            intake = rows[0]
            rc._committed_result(root,intake)
            actor,owner = rc._committed_intake_actor(root,intake)
            require(actor == 'operations-assistant' and owner.split(':',1)[0] == request['target_thread_id']
                    and store.readback(identity).get('claimed') is False, 'actual own SQL/native intake and released claim')
            native = goal._native_document(root,intake['actual_receiver_native'])
            matches = [(t,m) for t in native.get('turns',[]) for m in t.get('items',[])
                       if m.get('id') == intake.get('actual_receiver_message_id')]
            require(len(matches) == 1 and matches[0][0]['id'] == turn['id'], 'intake belongs to exact original receiving turn')
            real = [(n,m) for n,m in enumerate(items) if m.get('id') == intake['actual_receiver_message_id']]
            require(len(real) == 1 and inputs[0][0] < real[0][0] <= final_positions[0]
                    and _same_notification_intake_message(real[0][1],matches[0][1])
                    and identity['result_sha256'] in real[0][1].get('text','')
                    and final['text'].count(intake['record_id']) == 1, 'exact actual receipt message and finite final')
            receipts.append(intake['record_id'])
    finally:
        store.close()
    return {'kind':'source_bound_HQ_finite_result_intake','received_record_ids':receipts,
            'native_queue_message_id':accepted[1],'business_goal_closed':False,'external_permission_issued':False}


def _observe_hq_intake_serial(root, transport, record, before, slot):
    require(slot is None, 'HQ intake cannot release another original reservation')
    if (record.get('current_state') == 'completed'
            and record.get('current_release_observer',{}).get('kind') == 'source_bound_HQ_finite_result_intake'):
        fresh = shared_serial_guard(root,transport=transport)
        if fresh.get('new_activation_allowed') is True:
            return {'schema':'root-original-serial-observation/v1','state':'root_serial_release_already_fresh',
                    'root_release_recorded':False,'source':before,'business_goal_closed':False,'external_permission_issued':False}
    packet = doc(root,record.get('current_hq_intake_batch'))
    request = doc(root,packet.get('request'))
    require(record.get('current_active_original_window') == request.get('target_thread_id'), 'HQ batch cannot replace another current window')
    history = getattr(transport,'history',None)
    require(history is not None and callable(getattr(history,'call',None)), 'original readonly native history')
    thread = history.call('thread/read',{'threadId':request['target_thread_id'],'includeTurns':False})['thread']
    status = thread.get('status'); status = status.get('type') if isinstance(status,dict) else status
    require(status in {'idle','notLoaded'}, 'current HQ intake receiver still active/UNKNOWN')
    turns = history.call('thread/turns/list',{'threadId':request['target_thread_id'],'limit':1,
                                           'sortDirection':'desc','itemsView':'full'})['data']
    require(len(turns) == 1, 'one actual current recipient head')
    stamp = dt.datetime.now(dt.timezone.utc)
    actual_turn = turns[0]['id']
    require(record.get('current_active_turn') in {None,actual_turn}, 'current root owns another recipient turn')
    current = {**record,'current_active_turn':actual_turn,'current_state':'completed'}
    finite = {**turns[0],'items':[m for m in turns[0].get('items',[]) if m.get('type') in {'userMessage','agentMessage'}]}
    proof = {'source':'official_app_server_readonly_history','service_origin':SERVICE_ORIGIN,
             'thread':thread,'turns':[finite],'hq_intake_batch':record['current_hq_intake_batch']}
    _,_,final = _root_serial_native(proof,request['target_thread_id'],actual_turn,stamp)
    _hq_intake_batch(root,proof,current,final)
    with w.workflow_lock(root),w.request_validation_context() as validation:
        require(_root_serial_read(root)[1] == before and _root_slot_read(root) is None, 'original root or reservation changed')
        _hq_intake_batch(root,proof,current,final)
        validation.recheck()
        directory = w.safe_path(root,'logs/department-event-dispatcher/root-serial-release')
        directory.mkdir(parents=True,exist_ok=True)
        digest = __import__('hashlib').sha256(json.dumps(proof,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
        path = directory/(digest+'.json')
        if not path.exists(): w.atomic_write_json(path,proof)
        pin = w.file_digest(root,str(path.relative_to(root)))
        current.update(current_original_thread=request['target_thread_id'],current_active_was_new_recovery=False,
            current_recovery_receipt_state='completed_original_window_with_fresh_native_proof',
            current_release_native_proof=pin,current_release_observed_at_UTC=stamp.isoformat(),
            current_release_observer={'kind':'source_bound_HQ_finite_result_intake','service_origin':SERVICE_ORIGIN,
                'source_root':before,'normal_intent_request':packet['request'],
                'business_goal_closed':False,'external_permission_issued':False})
        w.atomic_write_json(w.safe_path(root,ROOT_SERIAL_PATH),current)
    return {'schema':'root-original-serial-observation/v1','state':'hq_finite_intake_release_recorded',
            'root_release_recorded':True,'release_proof':pin,'business_goal_closed':False,'external_permission_issued':False}


def _root_serial_batch(root, proof, record, final):
    """A maintenance-only final cannot release a different business batch."""
    import result_coordination as rc
    if proof.get('hq_intake_batch') is not None:
        return _hq_intake_batch(root,proof,record,final)
    if proof.get('notification_capacity') is not None:
        return _notification_capacity_batch(root,proof,record,final)
    window = record['current_active_original_window']; turn = record['current_active_turn']
    declarations = [line[len('FLASHCAST_DELIVERY_READY '):] for line in final['text'].splitlines()
                    if line.startswith('FLASHCAST_DELIVERY_READY ')]
    ready = json.loads(declarations[0]) if len(declarations) == 1 else None
    if isinstance(proof.get('result_identity'),dict):
        identity = rc.exact_identity(proof['result_identity']); queued = rc._validate_queued(root,identity)
        pin = queued.get('outbox') or proof.get('outbox'); box = doc(root,pin)
        status = str(box.get('status','')).lower()
        same_turn_ready = (_root_same_turn_ready_report(root,proof,record,final,identity,pin,box)
                           or _root_same_turn_queued_report(root,proof,record,final,identity,pin,box,queued))
        require(status not in {'','active','pending','in_progress','unknown','uncertain'}
                and (status not in {'blocked','waiting','partial_blocked'} or record['current_state'] == 'safe_dependency'),
                'contradictory root finite batch or missing safe dependency')
        require(proof.get('outbox') == pin and pin['sha256'] == identity['result_sha256']
                and queued.get('source_thread_id') == window and queued.get('source_turn_id') == turn
                and box.get('task_id') == identity['task_id'] and box.get('department') == identity['sender_department']
                and box.get('scope') == record.get('current_scope')
                and (box.get('batch_complete') is True or ('batch_complete' not in box
                     and isinstance(ready,dict) and ready.get('batch_complete') is True
                     and all(ready.get(k) == v for k,v in identity.items()) and ready.get('outbox_path') == pin['path'])
                     or ('batch_complete' not in box and same_turn_ready))
                and (pin['sha256'] in final['text'] or same_turn_ready),
                'DATA_MISSING exact root business batch result; terminal maintenance is not completion')
        if record['current_state'] == 'safe_dependency':
            _root_safe_dependency(root,proof.get('safe_dependency'),box,final)
        return {'kind':'normal_producer_batch','identity':identity,'outbox':pin}
    # A real finite READY is enough for the serial batch boundary, never for
    # notification/intake/adoption. Do not fabricate a notification_queued row.
    if len(declarations) == 1:
        identity = rc.exact_identity(ready)
        pin = w.file_digest(root,ready.get('outbox_path',''));box = doc(root,pin)
        status = str(box.get('status','')).lower()
        require(status not in {'','active','pending','in_progress','unknown','uncertain'}
                and (status not in {'blocked','waiting','partial_blocked'} or record['current_state'] == 'safe_dependency'),
                'contradictory unqueued READY finite batch or missing safe dependency')
        import department_autonomy as a
        import goal_delivery_runtime as g
        snapshot = g.restore_goal(root,w.read_json(w.snapshot_path(root,identity['task_id'])))
        fixed = w.department_registry(root)[identity['sender_department']]['chat_binding']
        require(ready.get('batch_complete') is True and box.get('batch_complete',True) is True
                and pin['sha256'] == identity['result_sha256'] and box.get('candidate_version') == identity['candidate_version']
                and box.get('department') == identity['sender_department'] and box.get('task_id') == identity['task_id']
                and box.get('scope') == record.get('current_scope') and box.get('fixed_chat_task_id') == window == fixed['task_id']
                and identity['sender_department'] in snapshot['goal_delivery']['producer_departments']
                and record['current_scope'] in snapshot['goal_delivery']['authorized_scope'],
                'DATA_MISSING exact unqueued READY original producer/task/scope/batch')
        if record['current_state'] == 'safe_dependency':
            _root_safe_dependency(root,proof.get('safe_dependency'),box,final)
        a.original_assignment_ready(root,snapshot,identity['sender_department'])
        w.validate_outbox(root,[pin],identity['sender_department'],identity['task_id'])
        return {'kind':'actual_unqueued_producer_READY_batch','identity':identity,'outbox':pin,
                'queued':False,'received':False,'business_goal_closed':False}
    notice = proof.get('routine_receipt')
    require(isinstance(notice,dict),'DATA_MISSING normal batch or exact routine receipt proof')
    record_notice = doc(root,notice); intake = rc.received_notification(root,record_notice)
    require(intake is not None,'DATA_MISSING actual routine intake')
    ctx = context(root,record_notice,intake); view = project(root,record_notice,intake)
    routine = view.get('routine_semantics',{})
    decisions = [r for r in w._result_handoff_rows(root,ctx['identity']['task_id'])
                 if r.get('record_id') == routine.get('original_decision_record_id')]
    require(len(decisions) == 1 and ctx['handling_actor'] in {'operations','operations-assistant'}
            and w.department_registry(root)[ctx['handling_actor']]['chat_binding']['task_id'] == window
            and ctx['scope'] == record.get('current_scope'),
            'DATA_MISSING same root actor/scope and normal decision final')
    import goal_delivery_runtime as g
    native = g._native_document(root,decisions[0]['actual_decision_native'])
    require(any(t.get('id') == turn for t in native.get('turns',[])),'root routine decision belongs to another turn')
    if record['current_state'] == 'completed':
        require(view.get('state') == 'routine_followthrough_proven','root routine batch still lacks actual followthrough')
    else:
        require(view.get('state') == 'named_future_dependency_wait' and routine.get('state') == 'routine_named_dependency_wait',
                'root routine safe dependency lacks exact holder/trigger/time')
    if decisions[0]['decision_source']['sha256'] not in final['text']:
        # The original event body asks for task/receipt/action IDs in final.
        # An exact same-turn SQL/native decision plus real closure may bind
        # those IDs instead of requiring an extra SHA echo in the final. A
        # maintenance-only final, partial reply or caller-supplied action does
        # not qualify. Preserve the old source-SHA final branch unchanged.
        same_turn = [t for t in native.get('turns',[]) if t.get('id') == turn and not t.get('error')]
        named = [m for t in same_turn for m in t.get('items',[])
                 if m.get('id') == decisions[0].get('actual_decision_message_id')
                 and m.get('type') == 'agentMessage'
                 and decisions[0]['decision_source']['path'] in m.get('text','')
                 and decisions[0]['decision_source']['sha256'] in m.get('text','')]
        slot = _root_slot_read(root)
        require(len(same_turn) == len(named) == 1,
                'DATA_MISSING same-turn actual routine decision and original slot')
        if slot is None:
            # Normal release deletes the ephemeral checkpoint. Revalidation
            # uses its already preserved original request, backed by the one
            # hashed workflow intent, never a newly supplied action label.
            observer = record.get('current_release_observer',{})
            require(observer.get('service_origin') == SERVICE_ORIGIN
                    and observer.get('business_goal_closed') is False
                    and observer.get('external_permission_issued') is False,
                    'DATA_MISSING original release observer after slot settled')
            request_pin = observer.get('normal_intent_request'); original = doc(root,request_pin)
            intents = _intents(root,original.get('task_id'),original.get('action_id'))
            require(len(intents) == 1 and intents[0].get('request') == request_pin,
                    'DATA_MISSING original committed routine intent after slot settled')
            slot = {'task_id':original.get('task_id'),'scope':original.get('scope'),
                    'action_id':original.get('action_id'),'request':request_pin}
        require(isinstance(slot,dict),'DATA_MISSING exact original routine slot')
        original = doc(root,slot.get('request')); marker = original.get(MARKER,{})
        action = slot.get('action_id')
        require(isinstance(action,str) and action and action == record.get('current_action_id')
                and slot.get('task_id') == original.get('task_id') == ctx['identity']['task_id']
                and slot.get('scope') == original.get('scope') == ctx['scope']
                and original.get('action_id') == action and original.get('action_class') == 'thread_message'
                and original.get('target_department') == ctx['handling_actor']
                and original.get('target_thread_id') == window
                and marker.get('notification') == notice and marker.get('received_record_id') == intake['record_id']
                and all(value in final['text'] for value in (ctx['identity']['task_id'],intake['record_id'],action)),
                'DATA_MISSING exact original slot task/receipt/action final; maintenance-only is not routine closure')
    return {'kind':'normal_routine_batch','identity':ctx['identity'],
            'received_record_id':intake['record_id'],'decision_record_id':decisions[0]['record_id']}


def _root_slot_read(root):
    import sqlite3
    path = Path(root)/'logs/department-event-dispatcher/transport.sqlite3'
    if not path.is_file():return None
    connection = sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)
    try:
        if not connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='checkpoints'").fetchone():return None
        row = connection.execute('SELECT value FROM checkpoints WHERE name=?',(ROOT_SERIAL_SLOT,)).fetchone()
        return json.loads(row[0]) if row else None
    finally:connection.close()


def shared_serial_guard(root, *, target_thread_id=None, transport=None, original_intent=None):
    """Strict shared read-only root gate. Readbacks never require this new-send gate."""
    result = {'schema':'shared-original-window-serial-guard/v1','state':'root_serial_DATA_MISSING',
        'new_activation_allowed':False,'original_intent_commit_allowed':False,'root_serial_released':False,
        'source':None,'reasons':[],'external_permission_issued':False}
    try:
        record,pin = _root_serial_read(root)
        result.update(source=pin,**{k:record.get(k) for k in ('current_active_original_window','current_active_turn',
            'current_state','current_scope','release_condition','assigned_next_original_window')})
        require(record.get('schema') == 'hq-serial-original-recovery-intent/v1'
                and record.get('one_new_window_at_a_time') is True,'DATA_MISSING current serial schema/one-window policy')
        require(all(isinstance(record.get(k),str) and record[k].strip() for k in
                ('current_active_original_window','current_active_turn','current_state','current_scope','release_condition')),
                'DATA_MISSING root current original window/turn/scope/state/release condition')
        require(record.get('current_original_thread',record['current_active_original_window']) == record['current_active_original_window'],
                'contradictory root current original window aliases')
        expected = {'completed':'completed_original_window_with_fresh_native_proof',
                    'safe_dependency':'safe_dependency_with_fresh_native_proof'}
        require(record['current_state'] in expected and record.get('current_active_was_new_recovery') is False,
                'root original window active/UNKNOWN or root serial not explicitly released')
        require(record.get('current_recovery_receipt_state') == expected[record['current_state']],
                'contradictory root release state/proof status')
        stamp = w._parse_observed_at(record.get('current_release_observed_at_UTC'))
        now = dt.datetime.now(dt.timezone.utc)
        require(stamp is not None and 0 <= (now-stamp).total_seconds() <= 300,
                'DATA_MISSING fresh root release native proof within 300 seconds')
        proof = doc(root,record.get('current_release_native_proof'))
        thread,turn,final = _root_serial_native(proof,record['current_active_original_window'],record['current_active_turn'],stamp)
        result['batch_evidence'] = _root_serial_batch(root,proof,record,final)
        head_id = turn['id']
        if result['batch_evidence'].get('kind') == NOTIFICATION_KIND:
            head_id = _notification_refresh_head(proof, thread['id'], turn, stamp)['id']
        history = getattr(transport,'history',None)
        if history is not None and callable(getattr(history,'call',None)):
            fresh_thread = history.call('thread/read',{'threadId':record['current_active_original_window'],'includeTurns':False})['thread']
            turns = history.call('thread/turns/list',{'threadId':record['current_active_original_window'],'limit':1,
                       'sortDirection':'desc','itemsView':'full'})['data']
            _root_serial_native({'thread':fresh_thread,'turns':turns},record['current_active_original_window'],
                                head_id,dt.datetime.now(dt.timezone.utc))
            result['fresh_original_window_readback'] = True
        else:result['fresh_original_window_readback'] = 'bounded_300_second_first_party_proof_fallback'
        require(_root_serial_read(root)[1] == pin,'root serial source changed during fresh read')
        slot = _root_slot_read(root)
        if slot is not None:
            if original_intent is not None and slot.get('request') == original_intent and slot.get('root_source') == pin:
                request = doc(root,original_intent)
                require(request.get('target_thread_id') == target_thread_id == slot.get('target_thread_id')
                        and request.get('task_id') == slot.get('task_id') and request.get('action_id') == slot.get('action_id'),
                        'root original intent identity differs')
                require(slot.get('status') == 'reserved_not_sent' and not (w.safe_path(root,slot['directory'])/'native-queue-intent.json').exists(),
                        'root original queue already started/UNKNOWN; read original key')
                return {**result,'state':'root_original_intent_commit_only','root_serial_released':True,
                        'original_intent_commit_allowed':True,'slot':slot}
            return {**result,'state':'root_shared_original_slot_inflight','slot':slot,
                    'reasons':['existing original reservation/UNKNOWN must settle before new activation']}
        assigned = record.get('assigned_next_original_window')
        consumed = record.get('current_assigned_next_consumed')
        if assigned and not (isinstance(consumed,dict) and consumed.get('thread_id') == assigned
                and consumed.get('completed_turn') == record['current_active_turn']
                and consumed.get('release_proof') == record['current_release_native_proof']):
            require(target_thread_id is None or target_thread_id == assigned,'root has a different explicit next original window reservation')
        return {**result,'state':'root_serial_released_verified','new_activation_allowed':True,'root_serial_released':True}
    except (w.WorkflowError,ValueError,OSError,KeyError,TypeError,AttributeError) as error:
        return {**result,'state':'root_serial_blocked','reasons':[str(error)]}


def reserve_root_serial(root, request, intent, *, transport=None, already_locked=False):
    """Persist one exact normal intent in the existing transport checkpoint store."""
    from contextlib import nullcontext
    from department_event_dispatcher import Store
    with nullcontext() if already_locked else w.workflow_lock(root):
        guard = shared_serial_guard(root,target_thread_id=request['target_thread_id'],transport=transport)
        require(guard.get('new_activation_allowed') is True,'root serial guard blocks new reservation: '+str(guard.get('reasons')))
        require(doc(root,intent.get('request')) == request,'exact normal request pin before shared reservation')
        policies = [p for p in w.read_jsonl(Path(root)/w.POLICY_DECISIONS) if p.get('decision_id') == intent.get('policy_decision_id')]
        require(len(policies) == 1 and policies[0].get('status') == 'allow'
                and policies[0].get('external_permission_issued') is False
                and policies[0].get('department') == request['sender_department']
                and all(policies[0].get(k) == request.get(k) for k in FIELDS),
                'actual exact normal policy required before root reservation')
        events = w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS,where={'task_id':request['task_id']})
        require(any(e.get('details',{}).get(name) == intent for e in events for name in
                    ('receipt_obligation_intent','publication_deadline_coordination_intent')),
                'existing durable normal intent required; root slot cannot create an assignment')
        preparation = intent.get('normal_preparation') or w.file_digest(root,
            str((w.safe_path(root,intent['directory'])/'normal-preparation.json').relative_to(root)))
        prepared = doc(root,preparation)
        require(prepared.get('policy_decision') == policies[0] and prepared.get('status') == 'ready_to_queue'
                and prepared.get('payload') == request['payload'] and prepared.get('external_permission_issued') is False,
                'exact original normal preparation pin required before root reservation')
        slot = {'schema':'root-original-resume-slot/v1','status':'reserved_not_sent','request':intent['request'],
                'root_source':guard['source'],'task_id':request['task_id'],'action_id':request['action_id'],
                'scope':request['scope'],'target_thread_id':request['target_thread_id'],'directory':intent['directory'],
                'normal_preparation':preparation,
                'policy_decision_id':intent['policy_decision_id'],'service_origin':SERVICE_ORIGIN,
                'business_goal_closed':False,'external_permission_issued':False}
        store = Store(Path(root))
        try:
            store.checkpoint_value(ROOT_SERIAL_SLOT)
            store.db.execute('BEGIN IMMEDIATE')
            require(store.db.execute('SELECT value FROM checkpoints WHERE name=?',(ROOT_SERIAL_SLOT,)).fetchone() is None,
                    'root original shared slot already owned')
            require(_root_serial_read(root)[1] == guard['source'],'root changed before shared intent reservation')
            store.db.execute('INSERT INTO checkpoints VALUES(?,?)',(ROOT_SERIAL_SLOT,json.dumps(slot,ensure_ascii=False,sort_keys=True)))
            store.db.commit()
        except Exception:
            store.db.rollback();raise
        finally:store.close()
        return slot


def observe_root_serial(root, transport, *, store=None, completion_event=None, protected_original_slot_source=None, protected_head_native_sources=None):
    """Existing completion/watch observer: exact finite batch -> coordination CAS.

    No global history scan, business completion, permission or HQ impersonation.
    Missing transport, a maintenance-only final, UNKNOWN or missing exact source
    stays blocked. A root slot is cleared only with the same current native key.
    """
    import hashlib
    import result_coordination as rc
    from department_event_dispatcher import Store
    result = {'schema':'root-original-serial-observation/v1','state':'root_serial_observation_blocked',
              'root_release_recorded':False,'business_goal_closed':False,'external_permission_issued':False,
              'service_origin':SERVICE_ORIGIN}
    try:
        if protected_original_slot_source is not None:
            return settle_protected_original_slot(root,transport,protected_original_slot_source,protected_head_native_sources=protected_head_native_sources)
        record,before = _root_serial_read(root); slot = _root_slot_read(root)
        if (record.get('current_hq_intake_batch') is not None and record.get('current_active_original_window')
                == w.department_registry(root)['operations-assistant']['chat_binding']['task_id']):
            packet = doc(root,record['current_hq_intake_batch'])
            intake_request = doc(root,packet.get('request'))
            if (record.get('current_action_id') == intake_request.get('action_id')
                    and record.get('current_scope') == intake_request.get('scope')):
                return _observe_hq_intake_serial(root,transport,record,before,slot)
        if (isinstance(slot,dict) and slot.get('kind') == NOTIFICATION_KIND
                or slot is None and record.get('current_release_observer',{}).get('kind') == NOTIFICATION_KIND):
            return _observe_notification_serial(root,transport)
        history = getattr(transport,'history',None)
        require(history is not None and callable(getattr(history,'call',None)),
                'DATA_MISSING existing readonly native transport for original root observation')
        require(record.get('schema') == 'hq-serial-original-recovery-intent/v1' and record.get('one_new_window_at_a_time') is True,
                'DATA_MISSING normal root serial record')
        request = doc(root,slot['request']) if slot else None
        if slot and before != slot['root_source']:
            require(record.get('current_active_original_window') == slot['target_thread_id']
                    and record.get('current_scope') == request['scope'],
                    'root moved to another current original window; do not overwrite or release it')
        if not slot:
            require(str(record.get('current_state','')).lower() not in {'unknown','uncertain','sending','queued'},
                    'UNKNOWN root transport lacks an exact owned original key')
        window = slot['target_thread_id'] if slot else record.get('current_active_original_window')
        observed = None
        if slot:
            # Original key first. Queue acceptance or ACK does not release it.
            observed = _observe_original(root,transport,slot)
            require(observed.get('turn_id'),'UNKNOWN original root reservation; inspect the exact original key')
            turn_id = observed['turn_id']
            if before != slot['root_source']:
                require(record.get('current_active_turn') == turn_id,'root now reserves a different turn; no release')
        else:turn_id = record.get('current_active_turn')
        native_thread = history.call('thread/read',{'threadId':window,'includeTurns':False})['thread']
        native_turns = history.call('thread/turns/list',{'threadId':window,'limit':1,'sortDirection':'desc','itemsView':'full'})['data']
        stamp = dt.datetime.now(dt.timezone.utc)
        thread,turn,final = _root_serial_native({'thread':native_thread,'turns':native_turns},window,turn_id,stamp)
        if slot:
            queue_start = w._parse_observed_at(w.read_json(w.safe_path(root,slot['directory'])/'native-queue-intent.json').get('started_at'))
            require(queue_start is not None and turn['completedAt'] >= queue_start.timestamp(),
                    'root terminal batch predates this original queue intent')
        if not slot and record.get('current_state') in {'completed','safe_dependency'}:
            existing = shared_serial_guard(root,transport=transport)
            if existing.get('new_activation_allowed'):
                return {**result,'state':'root_serial_release_already_fresh','source':before}
        current = {**record,'current_active_original_window':window,'current_active_turn':turn_id,
                   'current_scope':request['scope'] if request else record.get('current_scope'),'current_state':'completed'}
        # Keep actual commentary bytes, including admitted multiline READY.
        # The committed queue source message id/hash, not marker typography,
        # authenticates a producer batch in _root_same_turn_queued_report.
        proof = {'source':'official_app_server_readonly_history','service_origin':SERVICE_ORIGIN,
                 'thread':thread,'turns':[{k:v for k,v in turn.items() if k != 'items'} | {'items':[m for m in turn.get('items',[]) if m == final or (m.get('type') == 'agentMessage' and m.get('phase') == 'commentary')]}]}
        candidates = []
        if record.get('current_release_native_proof'):
            try:
                prior = doc(root,record['current_release_native_proof'])
                candidates.append({k:prior[k] for k in ('result_identity','outbox','routine_receipt','safe_dependency') if k in prior})
            except (w.WorkflowError,ValueError,OSError,KeyError,TypeError,AttributeError):
                pass  # A stale optional proof cannot suppress this current native READY.
        if completion_event is not None:candidates.append(completion_event)
        # Discover the exact queued result even when the final links evidence
        # without repeating the SHA. The normal batch validator still checks
        # the committed queue source, same turn, scope and final evidence.
        try:
            ready = _root_commentary_ready(proof['turns'][0])
            if isinstance(ready, dict):
                identity = rc.exact_identity(ready)
                if set(ready) == set(identity) | {'outbox_path', 'batch_complete'} and ready['batch_complete'] is True:
                    candidates.append({'result_identity': identity})
        except (w.WorkflowError, ValueError, OSError, KeyError, TypeError, AttributeError):
            pass  # Other independently authenticated batch sources still apply.
        if request and request.get(MARKER):
            notice = doc(root,request[MARKER]['notification']); intake = rc.received_notification(root,notice)
            require(intake is not None,'DATA_MISSING original root routine receipt')
            consumed = consume(root,notice,intake,transport,allow_new=False)
            require(not any(x.get('state') in {'original_followthrough_effect_unknown','original_followthrough_effect_waiting_transport'}
                    for x in consumed.get('original_transport',[])), 'UNKNOWN earlier original receipt effect still owns root slot')
            if consumed.get('state') in {'routine_followthrough_proven','named_future_dependency_wait'}:
                candidates.append({**proof,'routine_receipt':request[MARKER]['notification'],
                    'routine_current_state':'safe_dependency' if consumed['state'] == 'named_future_dependency_wait' else 'completed'})
        if store is not None:
            for row in store.rows():
                value = json.loads(row['identity_json'])
                if value.get('result_sha256') in final['text']:candidates.append({'result_identity':value})
        # READY can precede durable result queueing, but it is not receipt. Read
        # only the exact producer-declared outbox path in this actual final.
        if 'FLASHCAST_DELIVERY_READY ' in final['text']:
            candidates.append(proof)
        valid = None
        for candidate in candidates:
            try:
                item = {**proof,**candidate}
                candidate_current = dict(current)
                if isinstance(item.get('result_identity'),dict) and not item.get('outbox'):
                    item['outbox'] = rc._validate_queued(root,rc.exact_identity(item['result_identity']))['outbox']
                routine_state = item.pop('routine_current_state',None)
                if item.get('safe_dependency') or routine_state == 'safe_dependency':
                    candidate_current['current_state'] = 'safe_dependency'
                _root_serial_batch(root,item,candidate_current,final)
                current = candidate_current
                valid = item;break
            except (w.WorkflowError,ValueError,OSError,KeyError,TypeError,AttributeError):continue
        require(valid is not None,'DATA_MISSING exact normal completed batch or named safe dependency; maintenance final cannot release root')
        # Exact current/slot evidence is revalidated while holding the existing
        # normal workflow lock. No stale observer may overwrite a newer root.
        with w.workflow_lock(root):
            require(_root_serial_read(root)[1] == before,'root changed during normal completion observation')
            require(_root_slot_read(root) == slot,'root shared slot changed during observation')
            directory = w.safe_path(root,'logs/department-event-dispatcher/root-serial-release')
            directory.mkdir(parents=True,exist_ok=True)
            digest = hashlib.sha256(json.dumps(valid,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
            path = directory/(digest+'.json')
            if not path.exists():w.atomic_write_json(path,valid)
            pin = w.file_digest(root,str(path.relative_to(root)))
            receipt_state = ('safe_dependency_with_fresh_native_proof' if current['current_state'] == 'safe_dependency'
                             else 'completed_original_window_with_fresh_native_proof')
            updated = {**record,'current_active_original_window':window,'current_original_thread':window,
                'current_active_turn':turn_id,'current_scope':current['current_scope'],'current_state':current['current_state'],
                'current_active_was_new_recovery':False,'current_recovery_receipt_state':receipt_state,
                'current_release_native_proof':pin,'current_release_observed_at_UTC':stamp.isoformat(),
                'current_release_observer':{'service_origin':SERVICE_ORIGIN,'source_root':before,
                    'normal_intent_request':slot['request'] if slot else None,'business_goal_closed':False,'external_permission_issued':False}}
            if slot and record.get('assigned_next_original_window') == window:
                updated['current_assigned_next_consumed'] = {'thread_id':window,'completed_turn':turn_id,
                    'request':slot['request'],'release_proof':pin,'root_source':slot['root_source']}
            w.atomic_write_json(w.safe_path(root,ROOT_SERIAL_PATH),updated)
            if slot:
                own = Store(Path(root))
                try:
                    own.db.execute('DELETE FROM checkpoints WHERE name=? AND value=?',
                        (ROOT_SERIAL_SLOT,json.dumps(slot,ensure_ascii=False,sort_keys=True)))
                    own.db.commit()
                finally:own.close()
            return {**result,'state':'root_serial_coordination_release_recorded','root_release_recorded':True,
                    'source':w.file_digest(root,ROOT_SERIAL_PATH),'release_proof':pin,'current_state':current['current_state']}
    except (w.WorkflowError,ValueError,OSError,KeyError,TypeError,AttributeError) as error:
        return {**result,'reason':str(error)}


def _intents(root, task, action_id):
    return [e['details']['receipt_obligation_intent'] for e in
            w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS,where={'task_id':task})
            if e.get('details',{}).get('receipt_obligation_intent',{}).get('action_id') == action_id]


def _observe_original(root, transport, intent):
    """Exact original native effect recovery; never retry unknown/inflight sends."""
    request = doc(root,intent['request']); directory = w.safe_path(root,intent['directory'])
    prepared = doc(root,intent['normal_preparation'])
    policy = prepared.get('policy_decision',{})
    matches = [p for p in w.read_jsonl(Path(root)/w.POLICY_DECISIONS) if p.get('decision_id') == intent['policy_decision_id']]
    require(matches == [policy] and policy.get('status') == 'allow'
            and all(policy.get(k) == request[k] for k in FIELDS)
            and policy.get('department') == request['sender_department']
            and policy.get('external_permission_issued') is False,
            'original exact committed normal policy required before effect readback')
    result_path = directory/'native-queue-result.json'
    native_path = directory/'native-queue-intent.json'
    native = w.read_json(native_path) if native_path.exists() else {}
    result = w.read_json(result_path) if result_path.exists() else {}
    match = re.fullmatch(r'Queued message ([0-9a-f-]{36}) for thread ([0-9a-f-]{36})\.\s*',result.get('stdout',''))
    accepted = bool(result.get('exit_code') == 0 and match and match[2] == request['target_thread_id']
                    and result.get('payload_sha256') == request['payload_sha256']
                    and result.get('policy_decision_id') == intent['policy_decision_id']
                    and native and all(result.get(k) == v for k,v in native.items())
                    and native.get('transport') == 'official_codex_queue'
                    and w._parse_observed_at(native.get('started_at')) is not None
                    and w._parse_observed_at(result.get('finished_at')) is not None
                    and w._parse_observed_at(native['started_at']) <= w._parse_observed_at(result['finished_at']) <= dt.datetime.now(dt.timezone.utc))
    require(transport.history is not None,'original native readback connection required; unknown effect retained')
    page = transport.history.call('thread/turns/list',{'threadId':request['target_thread_id'],
                'limit':30,'sortDirection':'desc','itemsView':'full'})
    raw = directory/'latest-original-effect-readback.json'
    wanted = w.safe_path(root,request['payload']['path']).read_text(); seen = []
    for turn in page.get('data',[]):
        items = turn.get('items',[])
        for i,item in enumerate(items):
            if item.get('type') != 'userMessage': continue
            texts = [p.get('text','') for p in item.get('content',[]) if p.get('type') == 'text']
            if ''.join(texts) == wanted or '\n'.join(texts) == wanted:
                seen.append((turn,i))
    require(len(seen) <= 1, 'duplicate exact original native inputs; inspect original key')
    # Persist only the exact effect's IDs/hashes/native times. Unrelated turns,
    # message bodies and the raw 30-turn history are never written to disk.
    selected = []
    for turn,index in seen:
        item = turn['items'][index]
        require(isinstance(item.get('id'),str) and item['id'], 'exact native input message ID required')
        selected.append({'turn_id':turn.get('id'),'input_message_id':item['id'],
            'input_payload_sha256':request['payload_sha256'],'turn_status':turn.get('status'),
            'started_at_native':turn.get('startedAt'),'completed_at_native':turn.get('completedAt'),
            'matching_reply_messages':[{'id':m.get('id'),'sha256':__import__('hashlib').sha256(m.get('text','').encode()).hexdigest(),
                                      'phase':m.get('phase')}
                for m in turn.get('items',[])[index+1:] if m.get('type') == 'agentMessage'
                and request['task_id'] in m.get('text','') and request['action_id'] in m.get('text','')]})
    projection = {'schema':'exact-receipt-obligation-native-effect/v1','service_origin':SERVICE_ORIGIN,
        'task_id':request['task_id'],'action_id':request['action_id'],'thread_id':request['target_thread_id'],
        'request':intent['request'],'payload_sha256':request['payload_sha256'],
        'official_queue_message_id':match[1] if accepted else None,'matching_native_effects':selected}
    previous = w.read_json(raw) if raw.exists() else {}
    if {k:v for k,v in previous.items() if k != 'observed_at'} != projection:
        w.atomic_write_json(raw,{**projection,'observed_at':w.utc_timestamp()})
    if seen:
        turn, index = seen[0]
        acks = [] if turn.get('error') or turn.get('status') in {'failed','interrupted'} else [m for m in turn.get('items',[])[index+1:] if m.get('type') == 'agentMessage'
                and request['task_id'] in m.get('text','') and request['action_id'] in m.get('text','')]
        return {'state':'original_followthrough_ack_observed' if acks else 'original_followthrough_message_received',
                'turn_id':turn['id'],'ack_message_ids':[m['id'] for m in acks], 'actionable':False,
                'effect_readback':w.file_digest(root,str(raw.relative_to(root))),'business_goal_closed':False}
    return {'state':'original_followthrough_queue_accepted' if accepted else 'original_followthrough_effect_unknown',
            'message_id':match[1] if accepted else None,'actionable':False,'repeat_allowed':False,
            'effect_readback':w.file_digest(root,str(raw.relative_to(root))),'business_goal_closed':False}


def consume(root, record, intake, transport, *, allow_new=True, actual_native_sources=None, before_new_send=None):
    """One real normal-policy send, durable intent first, then native ACK/result tracking."""
    import department_event_dispatcher as dispatcher
    import goal_delivery_runtime as g
    view = project(root,record,intake)
    # Read ALL prior system-event keys first, even when a later normal routine
    # reply/result already proves business followthrough. No individual branch
    # may hide an earlier UNKNOWN or release its serial slot.
    existing_all = [e.get('details',{}).get('receipt_obligation_intent') for e in
                    w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS,where={'task_id':view['task_id']})]
    action = view.get('action')
    action_id = action['action_id'] if action else view.get('action_id')
    original = [x for x in existing_all if x and x.get('received_record_id') == intake['record_id']]
    observations = []; blocked_by_original = False
    def observe(intent, kind):
        if transport is None:
            found = {'state':'original_followthrough_effect_waiting_transport','actionable':False}
        else:
            try:
                found = _observe_original(root,transport,intent)
            except (w.WorkflowError,ValueError,OSError,KeyError,TypeError,AttributeError) as error:
                found = {'state':'original_followthrough_effect_unknown','actionable':False,
                         'original_effect_readback_error':str(error),'repeat_allowed':False}
        return {**found,'intent_kind':kind,'action_id':intent.get('action_id'),
                'received_record_id':intake['record_id']}
    for intent in original:
        observed = observe(intent,'receipt_obligation_intent')
        observations.append(observed)
        blocked_by_original = blocked_by_original or intent['action_id'] == action_id or observed['state'] != 'original_followthrough_ack_observed'
    routine_intent = view.get('routine_semantics',{}).get('routine_reply_intent')
    if routine_intent is not None:
        observations.append(observe(routine_intent,'routine_decision_reply_intent'))
    unknown = any(item['state'] in {'original_followthrough_effect_unknown',
                  'original_followthrough_effect_waiting_transport'} for item in observations)
    if routine_intent is not None or blocked_by_original:
        return {**view,'original_transport':observations,'original_transport_unknown':unknown,
                'message_sent':False,'actionable':False}
    if not view['actionable'] or transport is None or not allow_new:
        return {**view,'transport_available':transport is not None,'new_activation_allowed':allow_new,
                'message_sent':False,'original_transport':observations}
    target_thread = action['target_thread_id'] if action else dispatcher.binding(root,view['next_owner'])['task_id']
    shared = shared_serial_guard(root,target_thread_id=target_thread,transport=transport)
    if not shared.get('new_activation_allowed'):
        return {**view,'obligation_state':view['state'],'state':'waiting_root_serial_safe_boundary',
                'root_serial_guard':shared,'original_transport':observations,'message_sent':False,'actionable':False}
    require(isinstance(transport,dispatcher.OfficialQueueTransport), 'existing official native transport only')
    if before_new_send is not None:
        # Transport serialization only, after the actual fresh projection and
        # root guard. The callback grants no authority and creates no source.
        before_new_send()
    ctx = context(root,record,intake)
    action = view.get('action')
    action_id = action['action_id'] if action else view['action_id']
    directory = Path('logs/handoffs')/view['task_id']/'receipt-obligations'/w.sha256_value([intake['record_id'],action_id])
    dest = w.safe_path(root,str(directory))
    require(not dest.exists(), 'existing original directory/UNKNOWN must be read by original key')
    # Preparation input files are not a transport intent and grant no effect.
    preparation = Path('logs/department-event-dispatcher/receipt-prepared')/w.sha256_value([intake['record_id'],action_id])
    prepare_dir = w.safe_path(root,str(preparation)); prepare_dir.mkdir(parents=True,exist_ok=True)
    if action:
        request = dict(_ordinary_action(root,action,ctx)); request['delivery_mode'] = 'official_native_queue'
    else:
        path = prepare_dir/'message.txt'; expected = body(view)
        require(not path.exists() or path.read_text() == expected, 'frozen original system event changed')
        path.write_text(expected)
        source = dispatcher.binding(root,ctx['handling_actor']); target = dispatcher.binding(root,view['next_owner'])
        request = {'task_id':view['task_id'],'action_id':action_id,'action_class':'thread_message','scope':view['scope'],
                   'sender_department':ctx['handling_actor'],'source_project_id':source['project_id'],
                   'target_project_id':target['project_id'],'target_department':view['next_owner'],
                   'target_thread_id':target['task_id'],'target_thread_title':target['title'],'target_cwd':target['cwd'],
                   'target_sidebar_section_id':target['sidebar_section_id'],'payload':w.file_digest(root,str(path.relative_to(root))),
                   'payload_sha256':w.file_digest(root,str(path.relative_to(root)))['sha256'],
                   'authorization_changes':[],'delivery_mode':'official_native_queue',
                   'service_origin':SERVICE_ORIGIN,'owner_delegation':OWNER_DELEGATION,
                   MARKER:{'notification':w.file_digest(root,str(__import__('result_coordination')._notification_path(root,ctx['identity']).relative_to(root))),
                           'received_record_id':intake['record_id'],'trigger_fingerprint':view['trigger_fingerprint']}}
    for field,role in (('actual_sender_state',request['sender_department']),('actual_target_state',request['target_department'])):
        path = prepare_dir/(field+'.json'); w.atomic_write_json(path,transport._read(role))
        request[field] = w.file_digest(root,str(path.relative_to(root)))
    request['live_observed_at'] = w.utc_timestamp()
    if actual_native_sources is not None:
        require(action is None, 'SDK supplemental source applies only to original receipt system events')
        request['actual_native_sources'] = actual_native_sources
    request_path = prepare_dir/'request.json'; w.atomic_write_json(request_path,request)
    if action:
        from goal_source_recovery import prepare_message as normal_prepare
        prepared = normal_prepare(root,request)
    else:
        prepared = prepare_message(root,request)
    w.atomic_write_json(prepare_dir/'normal-preparation.json',prepared)
    require(prepared.get('status') == 'ready_to_queue' and prepared.get('external_permission_issued') is False
            and prepared.get('payload') == request['payload'] and prepared.get('policy_decision',{}).get('status') == 'allow',
            'actual normal official queue readiness required')
    with w.workflow_lock(root):
        shared = shared_serial_guard(root,target_thread_id=request['target_thread_id'],transport=transport)
        require(shared.get('new_activation_allowed') is True,'root serial changed before durable intent')
        fresh = project(root,record,intake)
        require(fresh == view and not _intents(root,view['task_id'],action_id) and not dest.exists(),
                'source/action/effect changed before original intent; no stale send')
        if action:
            _ordinary_action(root,action,context(root,record,intake))
            require(action_effect(root,context(root,record,intake),action) is None,'original action already in flight')
        else:
            event_route(root,g.restore_goal(root,w.read_json(w.snapshot_path(root,view['task_id']))),request)
        checked = w._parse_observed_at(prepared['policy_decision'].get('checked_at'))
        require(checked and 0 <= (dt.datetime.now(dt.timezone.utc)-checked).total_seconds() <= 300,'fresh normal policy before original intent required')
        dest.mkdir(parents=True)
        intent = {'received_record_id':intake['record_id'],'action_id':action_id,'request':w.file_digest(root,str(request_path.relative_to(root))),
                  'directory':str(directory),'policy_decision_id':prepared['policy_decision']['decision_id'],
                  'normal_preparation':w.file_digest(root,str((prepare_dir/'normal-preparation.json').relative_to(root))),
                  'logical_receiver':ctx['logical_receiver'],'handling_actor':ctx['handling_actor'],
                  'original_owner':ctx['original_owner'],'system_event_only':not bool(action),'external_permission_issued':False,
                  'service_origin':SERVICE_ORIGIN,'owner_delegation':OWNER_DELEGATION}
        w.append_workflow_event(root,view['task_id'],ctx['snapshot']['current_state'],{'receipt_obligation_intent':intent,'external_permission_issued':False})
        reserve_root_serial(root,request,intent,transport=transport,already_locked=True)
    commit = shared_serial_guard(root,target_thread_id=request['target_thread_id'],transport=transport,original_intent=intent['request'])
    require(commit.get('original_intent_commit_allowed') is True,'root original reservation cannot commit; preserve UNKNOWN and read original key')
    # No result identity is supplied: this is NEVER original result notification replay.
    effect = transport.enqueue({'directory':dest,'thread_id':request['target_thread_id'],
            'message':w.safe_path(root,request['payload']['path']).read_text(),'payload_sha256':request['payload_sha256'],
            'policy_decision_id':intent['policy_decision_id']})
    return {**view,'state':'followthrough_queue_accepted_not_received','message_id':effect['message_id'],
            'message_sent':True,'actionable':False,'business_goal_closed':False}


def _pump_readback_keys(root, store, rows):
    """Selection only. Preserve every durable original receipt key."""
    import department_event_dispatcher as d
    import result_coordination as rc
    keys = set()
    owner = store.checkpoint_value('current-receipt-followthrough-inflight')
    if owner: keys.add(owner)
    pending = {}
    path = Path(root)/w.WORKFLOW_EVENTS
    if path.is_file():
        with path.open('rb') as handle:
            for line in handle:
                if b'"receipt_obligation_intent"' not in line: continue
                event = json.loads(line)
                intent = event.get('details',{}).get('receipt_obligation_intent')
                if isinstance(intent,dict) and isinstance(intent.get('received_record_id'),str):
                    pending.setdefault(event['task_id'],set()).add(intent['received_record_id'])
    for task, ids in pending.items():
        for received in w._result_handoff_rows(root,task):
            if received.get('record_id') in ids:
                keys.add(d.key(rc.exact_identity(received)))
    return keys


def _pump_candidate_rows(root, store, transport, *, only_events, allow_new):
    """Cheap negative eligibility, never a permission or business completion."""
    import department_event_dispatcher as d
    import result_coordination as rc
    rows = store.rows()
    readbacks = _pump_readback_keys(root,store,rows)
    if only_events is not None:
        rows = [r for r in rows if r['event_key'] in only_events or r['event_key'] in readbacks]
    guard = shared_serial_guard(root,transport=transport)
    store.receipt_scan_full_selection = only_events is None and allow_new and guard.get('new_activation_allowed') is True
    if not allow_new or guard.get('new_activation_allowed') is not True:
        return [r for r in rows if r['event_key'] in readbacks], readbacks
    registry = w.department_registry(root)
    states = {}
    selected = []
    for row in rows:
        if row['event_key'] in readbacks:
            selected.append(row); continue
        role = registry.get(row['target'],{})
        if role.get('new_dispatch_enabled') is False: continue
        value = json.loads(row['identity_json']); task = value['task_id']
        if task not in states:
            path = w.snapshot_path(root,task)
            states[task] = w.read_json(path).get('current_state') if path.is_file() else None
        if states[task] in w.TERMINAL_STATES: continue
        selected.append(row)
    try:
        record,_ = _root_serial_read(root)
        preferred = rc.exact_identity(record.get('current_next_obligation_identity',{}))
        preferred_key = d.key(preferred)
    except (w.WorkflowError,ValueError,KeyError,TypeError,OSError):
        preferred_key = None
    store.receipt_scan_preferred_key = preferred_key
    selected.sort(key=lambda r:(r['event_key'] not in readbacks,r['event_key'] != preferred_key))
    return selected,readbacks


SCAN_CONTINUE = 'receipt-obligation-scan-continue'
SCAN_CHECKPOINT = 'receipt-obligation-bounded-sweep-v1'
SCAN_MAX_ROWS = 4
SCAN_SOFT_SECONDS = 2.0


def _scan_checkpoint(store, value):
    # The existing transport checkpoint is a fair work cursor, never a receipt,
    # authorization cache or business status. Original wakeup rows stay intact.
    store.db.execute('INSERT OR REPLACE INTO checkpoints VALUES(?,?)',
                     (SCAN_CHECKPOINT,json.dumps(value,sort_keys=True,separators=(',',':'))))
    store.db.commit()


def _scan_plan(store, rows, readbacks, *, continuation):
    raw = store.checkpoint_value(SCAN_CHECKPOINT)
    old = json.loads(raw) if raw else None
    if old is not None:
        require(isinstance(old,dict) and old.get('schema') == SCAN_CHECKPOINT
                and set(old) == {'schema','known','pending'}
                and all(isinstance(old[k],list) and len(set(old[k])) == len(old[k])
                        and all(isinstance(v,str) for v in old[k]) for k in ('known','pending'))
                and set(old['pending']) <= set(old['known']), 'intact original scan cursor required')
    keys = [r['event_key'] for r in rows]
    require(len(keys) == len(set(keys)), 'one original transport row per scan key')
    # A completed sweep is revisited only on a real existing event/check; an
    # internal finite continuation never starts another historical sweep.
    if old is None or not old['pending'] and not continuation:
        old = {'schema':SCAN_CHECKPOINT,'known':[],'pending':[]}
    known = set(old['known']); pending = list(old['pending'])
    full_selection = getattr(store,'receipt_scan_full_selection',False)
    if full_selection:
        # Current terminal/retired negative eligibility may remove a cursor
        # entry, never its original row or unfinished business goal.
        pending = [key for key in pending if key in set(keys)]
    # Blocked/exact-event selection has not examined the other historical
    # rows. Retain their original keys as deferred work, not a completed scan.
    universe = keys if full_selection else [r['event_key'] for r in store.rows()]
    for key in universe:
        if key not in known:
            old['known'].append(key); known.add(key); pending.append(key)
    preferred = getattr(store,'receipt_scan_preferred_key',None)
    if not continuation:
        # A real event always revisits original UNKNOWN/inflight effects, even
        # when that key was already examined earlier in this bounded sweep.
        for key in keys:
            if (key in readbacks or key == preferred) and key not in pending: pending.insert(0,key)
    priority = [key for key in keys if key in readbacks and key in pending]
    if preferred in pending and preferred in keys and preferred not in priority: priority.append(preferred)
    old['pending'] = priority + [key for key in pending if key not in set(priority)]
    _scan_checkpoint(store,old)
    by_key = {r['event_key']:r for r in rows}
    return old,[by_key[key] for key in old['pending'] if key in by_key]


def _scan_progress(store, plan, candidates, readbacks, *, sent, examined, elapsed):
    owner = store.checkpoint_value('current-receipt-followthrough-inflight')
    eligible = [r['event_key'] for r in candidates if r['event_key'] in plan['pending']
                and (not sent or r['event_key'] in readbacks)
                and (owner in {None,r['event_key']} or r['event_key'] in readbacks)]
    store.receipt_scan_progress = {
        'schema':'bounded-receipt-scan-progress/v1','examined_rows':examined,
        'elapsed_seconds':round(elapsed,6),'max_rows':SCAN_MAX_ROWS,'soft_seconds':SCAN_SOFT_SECONDS,
        'remaining_rows':len(plan['pending']),'next_event_key':plan['pending'][0] if plan['pending'] else None,
        'historical_sweep_complete':not plan['pending'],'continuation_ready':bool(eligible),
        'continuation_trigger':SCAN_CONTINUE if eligible else 'existing_source_completion_or_original_check',
        'cursor_checkpoint':SCAN_CHECKPOINT,'business_goal_closed':False,'permission_cached':False,
        'soft_budget_does_not_interrupt_an_inflight_row':True}


def pump(root, store, transport, *, only_events=None, allow_new=True):
    """One new activation, bounded fair historical work, original effects first.

    Each selected row reauthenticates sources in its own request context. No
    PASS, actor permission, accepted message or parent completion is cached.
    Budgets are checked only between rows; an in-flight operation is not killed.
    """
    import department_event_dispatcher as d
    import result_coordination as rc
    from readonly_work_view_cache import inventory_active
    require(not inventory_active(root), 'receipt effects require uncached normal context')
    started = time.monotonic(); examined = 0
    outcomes = []; slot = 'current-receipt-followthrough-inflight'; sent = False
    continuation = only_events is not None and SCAN_CONTINUE in only_events
    if only_events is not None and ('receipt-obligation-due' in only_events or continuation):
        only_events = None
    if only_events is None and not continuation:
        store.receipt_wait_deadline = None
    def remember_deadline(view):
        if view.get('state') != 'named_future_dependency_wait': return
        stamp = w._parse_observed_at(view.get('next_check_at') or view.get('normal_followthrough',{}).get('next_check_at'))
        old = getattr(store,'receipt_wait_deadline',None)
        if stamp is not None and (old is None or stamp < old): store.receipt_wait_deadline = stamp
    store.checkpoint_value(slot)
    rows,readback_keys = _pump_candidate_rows(root,store,transport,only_events=only_events,allow_new=allow_new)
    plan,candidates = _scan_plan(store,rows,readback_keys,continuation=continuation)
    for row in candidates:
        if examined >= SCAN_MAX_ROWS or examined and time.monotonic()-started >= SCAN_SOFT_SECONDS:
            break
        owner = store.checkpoint_value(slot)
        if (owner not in {None,row['event_key']} or sent) and row['event_key'] not in readback_keys:
            continue  # Preserve this pending cursor for its original safe trigger.
        value = None; intake = None
        examined += 1
        try:
            with d.observed_phase(store,'receipt_row',row['event_key']), w.request_validation_context():
                value = json.loads(row['identity_json']); record = d._activation_record(root,value)
                intake = rc.received_notification(root,record)
                if intake is None: continue
                owner = store.checkpoint_value(slot)
                can_start = allow_new and not sent and owner in {None,row['event_key']}
                def reserve_slot():
                    store.db.execute('BEGIN IMMEDIATE')
                    try:
                        current = store.db.execute('SELECT value FROM checkpoints WHERE name=?',(slot,)).fetchone()
                        require(current is None or current[0] == row['event_key'], 'another original recovery owns this serial slot')
                        store.db.execute('INSERT OR REPLACE INTO checkpoints VALUES(?,?)',(slot,row['event_key']))
                        store.db.commit()
                    except Exception:
                        store.db.rollback(); raise
                # consume makes the one real projection and invokes the slot
                # callback only after its fresh shared-root guard allows a send.
                result = consume(root,record,intake,transport,allow_new=can_start,before_new_send=reserve_slot)
                remember_deadline(result)
                outcomes.append({**value,'event_key':row['event_key'],**result})
                sent = sent or result.get('message_sent') is True
                unknown_original = any(item.get('state') in {'original_followthrough_effect_unknown',
                        'original_followthrough_effect_waiting_transport'} for item in result.get('original_transport',[]))
                if not unknown_original and result['state'] in {'causal_owner_successor_proven','normal_followthrough_proven','routine_followthrough_proven',
                        'named_future_dependency_wait','original_task_boundary_wait','original_action_result_received'}:
                    store.db.execute('DELETE FROM checkpoints WHERE name=? AND value=?',(slot,row['event_key']))
                    store.db.commit()
        except (w.WorkflowError,ValueError,OSError,KeyError,TypeError,AttributeError) as error:
            if value is not None and intake is not None:
                existing = [e for e in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS,where={'task_id':value['task_id']})
                    if e.get('details',{}).get('receipt_obligation_intent',{}).get('received_record_id') == intake['record_id']]
                if not existing:
                    store.db.execute('DELETE FROM checkpoints WHERE name=? AND value=?',(slot,row['event_key']))
                    store.db.commit()
            outcomes.append({'event_key':row['event_key'],'state':'receipt_next_obligation_source_or_effect_blocked',
                             'owner':'system-development','reason':str(error),'actionable':False,'message_sent':False})
        finally:
            # Examined is not completed: every business row remains unchanged,
            # and any future real event revalidates sources from their bytes.
            plan['pending'].remove(row['event_key']); _scan_checkpoint(store,plan)
            _scan_progress(store,plan,candidates,readback_keys,sent=sent,examined=examined,elapsed=time.monotonic()-started)
    _scan_progress(store,plan,candidates,readback_keys,sent=sent,examined=examined,elapsed=time.monotonic()-started)
    return outcomes

# A normal ordinary-decision return is a finite coordination handoff, not a
# producer outbox, legacy receipt, QA/adoption/publication or parent closure.
OWNER_HANDOFF_SCHEMA = 'normal-decision-owner-native-readback/v1'
OWNER_HANDOFF_EVENT = 'normal_decision_owner_native_handoff_readback'


def validate_owner_handoff_source(root, item):
    """Revalidate actual SQL/native decision, normal transport and owner work.

    Provider IDs select raw evidence, never a caller completion flag. Stored
    scripts/commands are parsed as data only; nothing is executed here.
    """
    import hashlib, shlex
    import chief_assistant_coordination as chief
    import result_coordination as rc
    import goal_delivery_runtime as g
    from qa_review_plan import _review_native_containers
    keys = {'schema','task_id','identity','notification','received_record_id','decision_record_id',
            'reply_action_id','original_reply_request','completed_owner_native','original_input_effect_readback','owner_turn_id',
            'input_message_id','ACK_message_id','decision_source_command_id','final_message_id'}
    require(isinstance(item,dict) and set(item) == keys and item.get('schema') == OWNER_HANDOFF_SCHEMA,
            'exact normal native owner-handoff source; no caller completion/permission flags')
    require(isinstance(item.get('identity'),dict) and set(item['identity']) == set(rc.IDENTITY_FIELDS),
            'exact original result identity fields; no nested completion flags')
    identity = rc.exact_identity(item['identity'])
    require(item.get('task_id') == identity['task_id'], 'same original native handoff task')
    notice = doc(root,item['notification']); intake = rc.received_notification(root,notice)
    require(intake is not None and intake.get('record_id') == item['received_record_id'],
            'real original committed receipt required for ordinary owner return')
    ctx = context(root,notice,intake)
    require(ctx['identity'] == identity, 'original receipt/result identity cannot change')
    selected = [r for r in w._result_handoff_rows(root,identity['task_id'])
                if r.get('event') == 'controller_decision' and r.get('record_id') == item['decision_record_id']]
    require(len(selected) == 1, 'one actual original decision required')
    decision = selected[0];rc._committed_result(root,decision)
    require(rc.exact_identity(decision) == identity and decision.get('routine_delegation') == chief.SOURCE
            and decision.get('decision') in {'continue_original_owner','coordinate_original_scope'}
            and decision.get('received_record_id') == intake['record_id'] and decision.get('outbox') == intake['outbox']
            and decision.get('scope') == ctx['scope'] and decision.get('target_department') == ctx['logical_receiver']
            and decision.get('next_owner') == ctx['original_owner']
            and rc._committed_intake_actor(root,decision) == (ctx['handling_actor'],ctx['handling_owner']),
            'same actual bounded decision/receipt/source/actor and original owner only')
    chief.receiver_context(root,decision,ctx['logical_receiver']);chief.decision(root,decision)  # discard generated row
    replies = [e['details']['routine_decision_reply_intent'] for e in
        w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS,where={'task_id':identity['task_id']})
        if e.get('details',{}).get('routine_decision_reply_intent',{}).get('decision_record_id') == decision['record_id']]
    require(len(replies) == 1, 'one original normal reply intent across action IDs required')
    intent = replies[0];request = chief.doc(root,intent.get('request'));marker=request.get('routine_decision_reply',{})
    require(intent.get('request') == item['original_reply_request']
            and intent.get('action_id') == item['reply_action_id'] == request.get('action_id')
            and request.get('task_id') == identity['task_id'] and request.get('scope') == ctx['scope']
            and request.get('sender_department') == intent.get('handling_actor') == ctx['handling_actor']
            and request.get('target_department') == intent.get('target_department') == ctx['original_owner']
            and request.get('action_class') == 'thread_message' and request.get('delivery_mode') == 'official_native_queue'
            and marker.get('decision_record_id') == decision['record_id'] and rc.exact_identity(marker) == identity,
            'exact immutable normal reply request, original actor and owner target')
    route=chief.message_route(root,ctx['snapshot'],request)
    require(route and route.get('purpose') == 'routine_decision_direct_reply'
            and route.get('decision_record_id') == decision['record_id'], 'normal authenticated decision reply route')
    effect=chief.reply_effect(root,identity['task_id'],intent['action_id'])
    require(effect.get('state') == 'official_queue_accepted_not_received' and effect.get('intent') == intent,
            'normal original queue effect must be known; accepted alone is not handoff')
    directory=w.safe_path(root,intent['directory']);prepared=w.read_json(directory/'normal-preparation.json')
    policy=prepared.get('policy_decision',{})
    policies=[p for p in w.read_jsonl(Path(root)/w.POLICY_DECISIONS) if p.get('decision_id') == intent.get('policy_decision_id')]
    require(policies == [policy] and policy.get('status') == 'allow' and policy.get('routing_status') == 'routing_allowed'
            and policy.get('department') == ctx['handling_actor'] and policy.get('external_permission_issued') is False
            and not policy.get('approval_id') and not policy.get('consume_approval')
            and prepared.get('status') == 'ready_to_queue' and prepared.get('payload') == request.get('payload')
            and all(policy.get(k) == request.get(k) for k in FIELDS),
            'exact original normal preparation/policy and payload; no permission inferred')
    queue=w.read_json(directory/'native-queue-intent.json');returned=w.read_json(directory/'native-queue-result.json')
    match=re.fullmatch(r'Queued message ([0-9a-f-]{36}) for thread ([0-9a-f-]{36})\.\s*',returned.get('stdout',''))
    checked=w._parse_observed_at(policy.get('checked_at'));sent=w._parse_observed_at(queue.get('started_at'))
    finished=w._parse_observed_at(returned.get('finished_at'));now=dt.datetime.now(dt.timezone.utc)
    require(queue and all(returned.get(k) == v for k,v in queue.items()) and returned.get('exit_code') == 0
            and match and match[1] == effect.get('message_id') and match[2] == request.get('target_thread_id')
            and queue.get('transport') == 'official_codex_queue' and queue.get('intake_claimed') is False
            and queue.get('thread_id') == request.get('target_thread_id')
            and queue.get('payload_sha256') == request.get('payload_sha256')
            and queue.get('policy_decision_id') == policy.get('decision_id')
            and checked and sent and finished and checked <= sent <= finished <= now,
            'durable exact original queue request/key/policy/chronology required')
    raw=doc(root,item['completed_owner_native'])
    require(set(raw) == {'source','observed_at_UTC','native'} and raw.get('source') == 'first_party_read_thread',
            'actual complete first-party owner source wrapper required')
    page=raw.get('native',{});_review_native_containers(raw);_review_native_containers(page)
    observed=w._parse_observed_at(raw.get('observed_at_UTC'))
    fixed=w.department_registry(root)[ctx['original_owner']]['chat_binding'];thread=page.get('thread',{})
    require(page.get('schemaVersion') == 1 and all(thread.get(k) == fixed[v] for k,v in
            {'id':'task_id','title':'title','cwd':'cwd','hostId':'host_id'}.items())
            and thread.get('kind') == 'codex' and all(thread.get(k,fixed['project_id']) == fixed['project_id']
            for k in ('projectId','project_id')) and Path(fixed['cwd']).resolve() == Path(root).resolve()
            and fixed['task_id'] == request.get('target_thread_id'),
            'actual fixed original owner host/project/thread/title/cwd only')
    payload=doc_bytes_for_owner_handoff(root,request.get('payload'))
    require(hashlib.sha256(payload).hexdigest() == request.get('payload_sha256'), 'original reply bytes unchanged')
    turns=page.get('turns');require(isinstance(turns,list) and turns and all(isinstance(t,dict) for t in turns),
                                  'complete original owner turns required')
    inputs=[]
    for turn in turns:
        items=turn.get('items',[]);require(isinstance(items,list) and all(isinstance(m,dict) for m in items),
                                         'complete original owner native items')
        for index,message in enumerate(items):
            if message.get('type') != 'userMessage':continue
            parts=message.get('content',[])
            if not isinstance(parts,list) or not all(isinstance(p,dict) for p in parts):continue
            if all(p.get('type') == 'text' for p in parts) and ''.join(p.get('text','') for p in parts).encode() == payload:
                inputs.append((turn,index,message))
    require(len(inputs) == 1,'one unique exact queued input bytes required; no historical or duplicate input')
    turn,index,incoming=inputs[0];_review_native_containers(turn)
    items=turn['items'];start=turn.get('startedAt');end=turn.get('completedAt')
    require(index == 0 and turn.get('id') == item['owner_turn_id'] and incoming.get('id') == item['input_message_id']
            and sum(m.get('type') == 'userMessage' for m in items) == 1
            and turn.get('status') == 'completed' and not turn.get('error')
            and type(start) in {int,float} and type(end) in {int,float}
            and observed and finished.timestamp() <= start <= end <= observed.timestamp() <= now.timestamp(),
            'exact queued input starts this completed finite owner turn; maintenance insertion cannot count')
    # The original key observer read the bounded current history and stored
    # only exact input IDs/hashes/times. Cross it against this complete turn;
    # a provider limit-one page alone does not prove absence of duplicate keys.
    original_effect=doc(root,item['original_input_effect_readback'])
    effect_at=w._parse_observed_at(original_effect.get('observed_at'))
    matches=original_effect.get('matching_native_effects')
    require(original_effect.get('schema') == 'exact-receipt-obligation-native-effect/v1'
            and original_effect.get('service_origin') == SERVICE_ORIGIN
            and original_effect.get('task_id') == identity['task_id']
            and original_effect.get('action_id') == intent['action_id']
            and original_effect.get('thread_id') == fixed['task_id']
            and original_effect.get('request') == intent['request']
            and original_effect.get('payload_sha256') == request['payload_sha256']
            and original_effect.get('official_queue_message_id') == match[1]
            and isinstance(matches,list) and len(matches) == 1
            and all(matches[0].get(k) == v for k,v in {'turn_id':turn['id'],
                'input_message_id':incoming['id'],'input_payload_sha256':request['payload_sha256'],
                'turn_status':'completed','started_at_native':start,'completed_at_native':end}.items())
            and effect_at and end <= effect_at.timestamp() <= now.timestamp(),
            'exact original-key native projection must prove one matching input and same provider turn/times')
    acknowledgements=[(i,m) for i,m in enumerate(items) if m.get('id') == item['ACK_message_id']
                      and m.get('type') == 'agentMessage' and m.get('phase') == 'commentary'
                      and isinstance(m.get('text'),str) and m['text'].strip()]
    commands=[(i,m) for i,m in enumerate(items) if m.get('id') == item['decision_source_command_id']]
    finals=[(i,m) for i,m in enumerate(items) if m.get('type') == 'agentMessage' and m.get('phase') == 'final_answer']
    require(len(acknowledgements) == len(commands) == len(finals) == 1,'nonempty ACK, actual source read and one final required')
    ack_index,ack=acknowledgements[0];command_index,command=commands[0];final_index,final=finals[0]
    require(final.get('id') == item['final_message_id'] and isinstance(final.get('text'),str) and final['text'].strip()
            and 0 < ack_index < command_index < final_index,
            'source work must follow ACK and precede same-turn completed final')
    for value in (incoming,ack,command,final):_review_native_containers(value)
    source=decision['decision_source'];source_bytes=doc_bytes_for_owner_handoff(root,source)
    argv=shlex.split(command.get('command',''))
    if len(argv) == 3 and argv[0] in {'/bin/zsh','/bin/bash'} and argv[1] in {'-lc','-c'}:argv=shlex.split(argv[2])
    require(argv == ['shasum','-a','256',source['path'],'&&','cat',source['path']]
            and command.get('type') == 'commandExecution' and command.get('status') == 'completed'
            and command.get('exitCode') == 0 and Path(command.get('cwd','')).resolve() == Path(root).resolve(),
            'successful exact read-only shasum+cat original decision command required; no arbitrary script')
    output=w._completion_execution_output(command)
    require(output == (source['sha256']+'  '+source['path']+'\n').encode()+source_bytes,
            'actual complete command output must contain exact decision digest and original bytes')
    return {'state':'normal_owner_decision_handoff_verified','identity':identity,'received_record_id':intake['record_id'],
            'decision_record_id':decision['record_id'],'reply_action_id':intent['action_id'],
            'normal_reply_request':intent['request'],'policy_decision_id':policy['decision_id'],
            'official_queue_message_id':match[1],'owner_thread_id':fixed['task_id'],'owner_turn_id':turn['id'],
            'input_message_id':incoming['id'],'input_payload_sha256':request['payload_sha256'],
            'ACK_message_id':ack['id'],'decision_source_command_id':command['id'],'final_message_id':final['id'],
            'completed_owner_native':item['completed_owner_native'],
            'original_input_effect_readback':item['original_input_effect_readback'],'decision_source':source,
            'coordination_obligation_only':True,'coordination_obligation_completed':True,
            'producer_outbox_created':False,'receipt_created':False,'acceptance_proven':False,'qa_proven':False,
            'external_permission_issued':False,'actual_production_performed':False,'business_goal_closed':False}


def doc_bytes_for_owner_handoff(root,pin):
    require(isinstance(pin,dict) and set(pin) == {'path','sha256','size'}
            and w.file_digest(root,pin.get('path','')) == pin, 'unchanged exact handoff source bytes required')
    return w.validation_bytes(w.safe_path(root,pin['path']))


def _owner_handoff_entries(root,task,decision_id,action_id):
    return [e for e in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS,where={'task_id':task})
            if e.get('details',{}).get(OWNER_HANDOFF_EVENT,{}).get('decision_record_id') == decision_id
            and e['details'][OWNER_HANDOFF_EVENT].get('reply_action_id') == action_id]


def registered_owner_handoff(root,ctx,decision,intent):
    entries=_owner_handoff_entries(root,ctx['identity']['task_id'],decision['record_id'],intent['action_id'])
    if not entries:return None
    require(len(entries) == 1,'one immutable ordinary owner-handoff readback source')
    source=entries[0]['details'][OWNER_HANDOFF_EVENT]['source'];item=doc(root,source)
    value=validate_owner_handoff_source(root,item)  # no stored completion bool or source-validation cache
    require(value['identity'] == ctx['identity'] and value['received_record_id'] == ctx['intake']['record_id']
            and value['decision_record_id'] == decision['record_id'] and value['reply_action_id'] == intent['action_id'],
            'registered normal owner-handoff proof must retain original obligation')
    return {**value,'source_registration':source,'source_event_id':entries[0]['event_id']}


def record_owner_handoff_source(root,task_id,input_path):
    from department_rotation import prohibit_validation_write
    prohibit_validation_write();pin=w.file_digest(root,input_path);item=doc(root,pin)
    require(item.get('task_id') == task_id,'same original coordination task required')
    with w.workflow_lock(root),w.request_validation_context() as validation:
        result=validate_owner_handoff_source(root,item)
        old=_owner_handoff_entries(root,task_id,item['decision_record_id'],item['reply_action_id'])
        if old:
            require(len(old) == 1 and old[0]['details'][OWNER_HANDOFF_EVENT]['source'] == pin,
                    'immutable original handoff proof already bound; never replace or renew')
            return {'result':'duplicate_ignored','source':pin,'coordination_obligation_only':True,
                    'business_goal_closed':False,'external_permission_issued':False}
        snapshot=w.read_json(w.snapshot_path(root,task_id));require(snapshot,'original task required')
        validation.recheck()
        event=w.append_workflow_event(root,task_id,snapshot['current_state'],{OWNER_HANDOFF_EVENT:{'source':pin,
              'decision_record_id':item['decision_record_id'],'reply_action_id':item['reply_action_id']},
              'coordination_obligation_only':True,'business_goal_closed':False,'external_permission_issued':False})
    return {'result':'recorded','source':pin,'event_id':event['event_id'],'coordination_obligation_only':True,
            'native_owner_turn':result['owner_turn_id'],'business_goal_closed':False,'external_permission_issued':False,
            'producer_outbox_created':False,'receipt_created':False,'message_sent':False}

# Historical original-key settlement is independent of current root activation.
# It never relabels an old page as latest or overwrites another original window.
PROTECTED_SLOT_SCHEMA = 'protected-original-root-slot-settlement/v1'


def _protected_head(root, history, fixed, minimum_started, protected_head_native_sources=None):
    """Actual current head, not the protected historical evidence page."""
    thread=history.call('thread/read',{'threadId':fixed['task_id'],'includeTurns':False})['thread']
    page=history.call('thread/turns/list',{'threadId':fixed['task_id'],'limit':1,'sortDirection':'desc','itemsView':'full'})
    require(isinstance(thread,dict) and isinstance(page,dict) and not page.get('error')
            and page.get('isError',False) is False and page.get('truncated',False) is False,
            'UNKNOWN fresh protected-owner head source')
    title=thread.get('title',thread.get('name'))
    require(thread.get('id') == fixed['task_id'] and title == fixed['title']
            and Path(thread.get('cwd','')).resolve() == Path(root).resolve(),
            'fresh actual protected-owner fixed identity required')
    if protected_head_native_sources is None:
        require(all(thread.get(k,fixed[v]) == fixed[v] for k,v in {'hostId':'host_id','projectId':'project_id','project_id':'project_id'}.items()),
                'fresh actual protected-owner fixed identity required')
    else:
        require(isinstance(protected_head_native_sources,dict) and set(protected_head_native_sources)=={'native','inventory'},
                'exact protected-owner first-party SDK and project inventory sources required')
        _sdk_supplement_matches(root,'operations-assistant',fixed,{'thread':thread,'turns':page.get('data',[])},protected_head_native_sources)
    status=thread.get('status',{});status=status.get('type') if isinstance(status,dict) else status
    require(status in {'idle','notLoaded'},'protected-owner current head active/UNKNOWN; preserve in-flight work')
    turns=page.get('data');require(isinstance(turns,list) and len(turns) == 1,'one fresh actual current head required')
    head=turns[0];stamp=dt.datetime.now(dt.timezone.utc)
    _,head,final=_root_serial_native({'thread':thread,'turns':turns},fixed['task_id'],head.get('id'),stamp)
    require(type(head.get('startedAt')) in {int,float} and head['startedAt'] >= minimum_started,
            'fresh head predates the actual historical source; wrong runtime/history')
    signature=(fixed['task_id'],status,head['id'],head['startedAt'],head['completedAt'],final['id'],w.sha256_value(final['text']))
    return {'observed_at':stamp.isoformat(),'thread':thread,'turns':turns,'signature':signature,
            'purpose':'fresh_current_idle_head_only_not_original_batch_completion'}


def validate_protected_original_slot(root, transport, item, slot, protected_head_native_sources=None):
    """Pure source/current-head validation; no queue, receipt, SQL or root write."""
    import result_coordination as rc
    from qa_review_plan import _review_native_containers
    require(isinstance(item,dict) and set(item) == {'schema','task_id','scope','slot_request','slot_action_id','slot_fingerprint',
        'protected_original_native','protected_original_turn_id','original_input_message_id','original_ACK_message_id',
        'original_decision_message_id','original_decision_commit_command_id','original_final_message_id','normal_owner_handoff_source'}
        and item.get('schema') == PROTECTED_SLOT_SCHEMA, 'exact protected original slot source; no completion flags')
    require(isinstance(slot,dict) and slot.get('schema') == 'root-original-resume-slot/v1'
            and slot.get('service_origin') == SERVICE_ORIGIN and slot.get('business_goal_closed') is False
            and slot.get('external_permission_issued') is False and w.sha256_value(slot) == item['slot_fingerprint']
            and slot.get('request') == item['slot_request'] and slot.get('action_id') == item['slot_action_id']
            and slot.get('task_id') == item['task_id'] and slot.get('scope') == item['scope'],
            'exact original checkpoint/request/task/scope/key fingerprint required')
    request=doc(root,slot['request']);marker=request.get(MARKER,{})
    require(request.get('task_id') == item['task_id'] and request.get('scope') == item['scope']
            and request.get('action_id') == item['slot_action_id'] and request.get('action_class') == 'thread_message'
            and request.get('delivery_mode') == 'official_native_queue'
            and request.get('target_thread_id') == slot.get('target_thread_id'), 'original normal system event request required')
    source=doc(root,item['normal_owner_handoff_source']);handoff=validate_owner_handoff_source(root,source)
    registered=_owner_handoff_entries(root,item['task_id'],source['decision_record_id'],source['reply_action_id'])
    require(len(registered) == 1 and registered[0]['details'][OWNER_HANDOFF_EVENT].get('source') == item['normal_owner_handoff_source']
            and marker.get('notification') == source['notification'] and marker.get('received_record_id') == handoff['received_record_id']
            and handoff['coordination_obligation_only'] is True and handoff['coordination_obligation_completed'] is True
            and handoff['business_goal_closed'] is False, 'normal registered and freshly revalidated owner-handoff source required')
    notice=doc(root,source['notification']);intake=rc.received_notification(root,notice);ctx=context(root,notice,intake)
    fixed=w.department_registry(root)[ctx['handling_actor']]['chat_binding']
    require(ctx['handling_actor'] in {'operations','operations-assistant'} and fixed['task_id'] == slot['target_thread_id']
            and ctx['scope'] == item['scope'] and ctx['identity'] == source['identity'], 'exact original handling actor and slot')
    original=[e['details']['receipt_obligation_intent'] for e in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS,where={'task_id':item['task_id']})
        if e.get('details',{}).get('receipt_obligation_intent',{}).get('action_id') == item['slot_action_id']]
    require(len(original) == 1 and original[0].get('request') == slot['request']
            and original[0].get('received_record_id') == handoff['received_record_id'], 'one hashed original receipt-obligation intent')
    prepared=doc(root,slot['normal_preparation']);policy=prepared.get('policy_decision',{})
    policies=[p for p in w.read_jsonl(Path(root)/w.POLICY_DECISIONS) if p.get('decision_id') == slot.get('policy_decision_id')]
    require(policies == [policy] and policy.get('status') == 'allow' and policy.get('routing_status') == 'routing_allowed'
            and policy.get('department') == request.get('sender_department')
            and all(policy.get(k) == request.get(k) for k in FIELDS)
            and policy.get('external_permission_issued') is False and not policy.get('approval_id') and not policy.get('consume_approval')
            and prepared.get('status') == 'ready_to_queue' and prepared.get('payload') == request.get('payload'),
            'actual original slot normal preparation and policy required')
    directory=w.safe_path(root,slot['directory']);queued=w.read_json(directory/'native-queue-intent.json');returned=w.read_json(directory/'native-queue-result.json')
    accepted=re.fullmatch(r'Queued message ([0-9a-f-]{36}) for thread ([0-9a-f-]{36})\.\s*',returned.get('stdout',''))
    sent=w._parse_observed_at(queued.get('started_at'));finished=w._parse_observed_at(returned.get('finished_at'))
    checked=w._parse_observed_at(policy.get('checked_at'));now=dt.datetime.now(dt.timezone.utc)
    require(queued and all(returned.get(k) == v for k,v in queued.items()) and returned.get('exit_code') == 0
            and accepted and accepted[2] == fixed['task_id'] and queued.get('thread_id') == fixed['task_id']
            and queued.get('transport') == 'official_codex_queue' and queued.get('intake_claimed') is False
            and queued.get('payload_sha256') == request.get('payload_sha256')
            and queued.get('policy_decision_id') == policy.get('decision_id')
            and checked and sent and finished and checked <= sent <= finished <= now,
            'original exact durable queue effect/chronology required; UNKNOWN cannot settle')
    raw=doc(root,item['protected_original_native']);page=raw.get('native',{})
    require(set(raw) == {'source','observed_at_UTC','native'} and raw.get('source') == 'first_party_read_thread',
            'actual original bounded SDK source, never a caller current-head projection')
    _review_native_containers(raw);_review_native_containers(page)
    require(all(page.get('thread',{}).get(k) == fixed[v] for k,v in
            {'id':'task_id','title':'title','cwd':'cwd','hostId':'host_id'}.items()), 'original protected native actor identity')
    turns=page.get('turns');require(isinstance(turns,list) and turns and all(isinstance(t,dict) for t in turns), 'actual bounded history required')
    payload=doc_bytes_for_owner_handoff(root,request['payload']);matches=[]
    for turn in turns:
        items=turn.get('items',[]);require(isinstance(items,list) and all(isinstance(m,dict) for m in items), 'complete protected turn items')
        for index,message in enumerate(items):
            if message.get('type') == 'userMessage':
                parts=message.get('content',[])
                if isinstance(parts,list) and all(isinstance(p,dict) and p.get('type') == 'text' for p in parts) and ''.join(p.get('text','') for p in parts).encode() == payload:
                    matches.append((turn,index,message))
    require(len(matches) == 1,'one actual original queued input, no duplicate or assumed old turn')
    turn,index,incoming=matches[0];_review_native_containers(turn)
    observed=w._parse_observed_at(raw.get('observed_at_UTC'));start=turn.get('startedAt');end=turn.get('completedAt')
    require(index == 0 and incoming.get('id') == item['original_input_message_id']
            and turn.get('id') == item['protected_original_turn_id'] and turn.get('status') == 'completed' and not turn.get('error')
            and sum(m.get('type') == 'userMessage' for m in turn['items']) == 1
            and type(start) in {int,float} and type(end) in {int,float} and observed
            and finished.timestamp() <= start <= end <= observed.timestamp() <= now.timestamp(),
            'actual exact original finite input/turn/completion, not a later maintenance turn')
    decisions=[d for d in w._result_handoff_rows(root,item['task_id']) if d.get('record_id') == handoff['decision_record_id']]
    require(len(decisions) == 1,'one actual original routine decision')
    decision=decisions[0];rc._committed_result(root,decision)
    messages={m.get('id'):(i,m) for i,m in enumerate(turn['items']) if m.get('id')}
    selected=[messages.get(item[k]) for k in ('original_ACK_message_id','original_decision_message_id',
                                            'original_decision_commit_command_id','original_final_message_id')]
    require(all(x is not None for x in selected), 'exact original ACK/decision/commit/final IDs')
    (ai,ack),(di,stated),(ci,command),(fi,final)=selected
    require(0 < ai < di < ci < fi and ack.get('type') == stated.get('type') == final.get('type') == 'agentMessage'
            and ack.get('phase') == stated.get('phase') == 'commentary' and ack.get('text','').strip()
            and stated.get('id') == decision.get('actual_decision_message_id')
            and decision['decision_source']['path'] in stated.get('text','') and decision['decision_source']['sha256'] in stated.get('text','')
            and final.get('phase') == 'final_answer' and final.get('text','').strip()
            and all(value in final['text'] for value in (item['task_id'],handoff['received_record_id'],item['slot_action_id'],handoff['decision_record_id'])),
            'original finite final must bind exact task/receipt/action/decision; newer maintenance final cannot substitute')
    for value in (incoming,ack,stated,command,final):_review_native_containers(value)
    require(command.get('type') == 'commandExecution' and command.get('status') == 'completed' and command.get('exitCode') == 0
            and Path(command.get('cwd','')).resolve() == Path(root).resolve()
            and w._completion_execution_output(command) == ('decision '+handoff['decision_record_id']+' recorded\nreleased True\n').encode(),
            'actual original normal decision commit/release output required; stored command is never executed')
    history=getattr(transport,'history',None);require(history is not None and callable(getattr(history,'call',None)),
                                                  'existing real readonly history transport required')
    latest_started=max(t.get('startedAt',0) for t in turns)
    head=_protected_head(root,history,fixed,latest_started,protected_head_native_sources)
    require(head['turns'][0]['id'] != turn['id'] and head['turns'][0]['startedAt'] > start,
            'this narrow path only settles original keys behind a newer verified safe head')
    return {'kind':'protected_original_slot_settlement_verified','slot':slot,'slot_fingerprint':item['slot_fingerprint'],
            'task_id':item['task_id'],'action_id':item['slot_action_id'],'original_turn_id':turn['id'],
            'original_input_message_id':incoming['id'],'original_final_message_id':final['id'],
            'protected_original_native':item['protected_original_native'],'normal_owner_handoff_source':item['normal_owner_handoff_source'],
            'owner_handoff':handoff,'fresh_current_head':head,'current_root_update_allowed':False,
            'coordination_obligation_only':True,'business_goal_closed':False,'external_permission_issued':False}


def settle_protected_original_slot(root, transport, source_pin, *, protected_head_native_sources=None):
    """Normal observer's explicit exact-key CAS; never changes ROOT metadata."""
    import hashlib
    from department_event_dispatcher import Store
    from department_rotation import prohibit_validation_write
    prohibit_validation_write();item=doc(root,source_pin)
    record,before=_root_serial_read(root);slot=_root_slot_read(root)
    directory=w.safe_path(root,'logs/department-event-dispatcher/root-serial-release/protected-original-slots')
    require(w.SHA256_PATTERN.fullmatch(str(item.get('slot_fingerprint',''))),'exact original slot fingerprint')
    receipt_path=directory/(item['slot_fingerprint']+'-settled.json')
    if slot is None and receipt_path.exists():
        receipt=w.read_json(receipt_path)
        require(receipt.get('source') == source_pin and receipt.get('slot_fingerprint') == item['slot_fingerprint']
                and receipt.get('kind') == 'protected_original_slot_compare_delete_readback',
                'original settlement receipt differs; inspect exact prior effect')
        proof=doc(root,receipt.get('proof'))
        require(proof.get('source') == source_pin and w.sha256_value(proof.get('original_slot')) == item['slot_fingerprint'],
                'original settlement proof/source changed')
        validate_protected_original_slot(root,transport,item,proof['original_slot'],protected_head_native_sources)
        # This is original-key effect readback, not permission to wake anybody.
        return {'state':'protected_original_slot_already_settled','source':source_pin,'checkpoint_absent_observed':True,
                'current_root_preserved':True,'root_release_recorded':False,'new_activation_allowed':False,
                'business_goal_closed':False,'external_permission_issued':False}
    require(not receipt_path.exists(),'settlement receipt already exists but a checkpoint is present; inspect original effect, never delete twice')
    require(slot is not None,'UNKNOWN original slot absence without own settlement readback; no blind replay')
    first=validate_protected_original_slot(root,transport,item,slot,protected_head_native_sources)
    with w.workflow_lock(root),w.request_validation_context() as validation:
        require(_root_serial_read(root)[1] == before and _root_slot_read(root) == slot,
                'current ROOT or original checkpoint changed; no old-key settlement')
        second=validate_protected_original_slot(root,transport,item,slot,protected_head_native_sources)
        require(second['fresh_current_head']['signature'] == first['fresh_current_head']['signature'],
                'protected-owner current head moved during settlement; preserve in-flight work')
        validation.recheck()
        require(_root_serial_read(root)[1] == before and _root_slot_read(root) == slot,
                'ROOT/checkpoint changed before compare-delete')
        directory.mkdir(parents=True,exist_ok=True)
        proof={'schema':'protected-original-slot-verified-proof/v1','source':source_pin,
               'root_before':before,'original_slot':slot,'first_readback':first,'second_readback':second,
               'ROOT_bytes_must_remain_unchanged':True,'business_goal_closed':False,'external_permission_issued':False}
        proof_path=directory/(item['slot_fingerprint']+'-'+w.sha256_value(proof)[:16]+'-verified.json')
        if proof_path.exists():
            old=w.read_json(proof_path)
            require(old.get('source') == source_pin and old.get('original_slot') == slot,
                    'original key proof already belongs to another source')
        else:w.atomic_write_json(proof_path,proof)
        store=Store(Path(root))
        try:
            store.db.execute('BEGIN IMMEDIATE')
            row=store.db.execute('SELECT value FROM checkpoints WHERE name=?',(ROOT_SERIAL_SLOT,)).fetchone()
            require(row is not None and json.loads(row[0]) == slot and _root_serial_read(root)[1] == before,
                    'exact checkpoint/root CAS changed inside transaction')
            deleted=store.db.execute('DELETE FROM checkpoints WHERE name=? AND value=?',(ROOT_SERIAL_SLOT,row[0]))
            require(deleted.rowcount == 1,'exact original checkpoint compare-delete failed')
            require(_root_serial_read(root)[1] == before,'current ROOT changed before settlement commit')
            store.db.commit()
        except BaseException:
            store.db.rollback();raise
        finally:store.close()
        require(_root_serial_read(root)[1] == before,'ROOT changed after old-key commit; inspect actual readback')
        require(_root_slot_read(root) is None,'checkpoint changed after old-key commit; preserve new current key')
        receipt={'kind':'protected_original_slot_compare_delete_readback','source':source_pin,
                 'slot_fingerprint':item['slot_fingerprint'],'proof':w.file_digest(root,str(proof_path.relative_to(root))),
                 'root_before':before,'root_after':_root_serial_read(root)[1],'checkpoint_absent_observed':True,
                 'observed_at':w.utc_timestamp(),'coordination_obligation_only':True,'business_goal_closed':False,
                 'external_permission_issued':False}
        w.atomic_write_json(receipt_path,receipt)
    return {'state':'protected_original_slot_settled_current_root_preserved','source':source_pin,
            'settlement_readback':w.file_digest(root,str(receipt_path.relative_to(root))),
            'current_root_preserved':True,'root_release_recorded':False,'new_activation_allowed':False,
            'business_goal_closed':False,'external_permission_issued':False}


# Result notifications occupy capacity only when they activate an ended window.
# These are transport/coordination records, never receipt-obligation messages.
NOTIFICATION_KIND = 'result_notification'
NOTIFICATION_CAPACITY_EVENT = 'notification_capacity_intent'


def _notification_binding(root, identity, target_role, *, notice=None):
    import result_coordination as rc
    value = rc.exact_identity(identity)
    registry = w.department_registry(root)
    require(target_role in registry and registry[target_role].get('new_dispatch_enabled') is True,
            'notification original receiver must remain enabled')
    source = registry[value['sender_department']]['chat_binding']
    target = registry[target_role]['chat_binding']
    route = rc.frozen_notification_route(root,notice) if notice is not None else rc.result_lane(root,value)
    require(route.get('lane') in {'professional_acceptance','HQ_knowledge'}
            and route.get('target_department') == target_role
            and source.get('project_id') == target.get('project_id')
            and source.get('project_id') and all(Path(x.get('cwd','')).resolve() == Path(root).resolve() for x in (source,target)),
            'original same-project sender/receiver and normal notification route required')
    return value,source,target,route


def _notification_active(root, identity, target_role, observation):
    from goal_delivery_runtime import _collaboration_native
    from goal_source_recovery import _native_container_valid
    require(isinstance(observation,dict),'DATA_MISSING first-party ACTIVE desktop observation')
    observed=doc(root,observation); now=dt.datetime.now(dt.timezone.utc)
    for name in ('observed_at','live_observed_at'):
        at=w._parse_observed_at(observed.get(name))
        require(at is not None and 0 <= (now-at).total_seconds() <= 300,'fresh original ACTIVE desktop/inventory required')
    value,source,target,_=_notification_binding(root,identity,target_role)
    page=_collaboration_native(root,observed.get('actual_native_target_turn'))
    require(_native_container_valid(observed) and _native_container_valid(page)
            and page.get('source_transport') != 'official_app_server_readonly_history'
            and page.get('page',{}).get('order') == 'newest_first',
            'actual first-party desktop, never readonly app-server ACTIVE inference')
    thread=page.get('thread',{})
    require(thread.get('kind') == 'codex' and thread.get('archived') is not True
            and all(thread.get(k)==target.get(v) for k,v in
                    {'id':'task_id','title':'title','cwd':'cwd','hostId':'host_id'}.items())
            and thread.get('projectId') in {None,target['project_id']},
            'actual ACTIVE receiver primary identity must match; explicit project mismatch refused')
    status=thread.get('status'); status=status.get('type') if isinstance(status,dict) else status
    turns=page.get('turns',[])
    require(status in {'active','inProgress','running','busy'} and turns
            and all(type(t.get('startedAt')) in {int,float} for t in turns)
            and turns[0] == max(turns,key=lambda t:t['startedAt'])
            and turns[0].get('id') and turns[0].get('status') == 'inProgress'
            and turns[0].get('completedAt') is None and not turns[0].get('error')
            and turns[0]['startedAt'] <= now.timestamp(),
            'notLoaded/idle/pending alone cannot prove an already ACTIVE original receiver')
    # SDK thread/read can omit projectId; the same fresh inventory supplies
    # that fact for this exact original thread. Never invent a provider field.
    inventory=_collaboration_native(root,observed.get('actual_live_inventory'))
    require(_native_container_valid(inventory),'actual ACTIVE scoped inventory required')
    for fixed in (source,target):
        rows=[r for r in inventory.get('threads',[])+inventory.get('pinnedThreads',[]) if r.get('id')==fixed['task_id']]
        memberships=[p.get('sectionId') for p in inventory.get('sections',[])
                     if 'codex:thread:'+fixed['host_id']+':'+fixed['task_id'] in p.get('itemKeys',[])]
        require(len(rows)==1 and rows[0].get('archived') is not True
                and memberships==[fixed['sidebar_section_id']]
                and all(rows[0].get(k)==fixed.get(v) for k,v in
                        {'id':'task_id','title':'title','cwd':'cwd','hostId':'host_id','projectId':'project_id'}.items()),
                'actual ACTIVE sender/receiver inventory and sidebar must match original bindings')
    return {'observation':observation,'target_thread_id':target['task_id'],'turn_id':turns[0]['id'],
            'actual_native_target_turn':observed['actual_native_target_turn'],
            'actual_live_inventory':observed['actual_live_inventory'],'observed_at':observed['observed_at']}


def notification_queue_admission(root, identity, target_role, transport, *, actual_active_observation=None):
    """Capacity only: real busy queue or normal one-new-window root reservation."""
    result={'kind':NOTIFICATION_KIND,'queue_allowed':False,'requires_reservation':True,
            'state':'notification_capacity_DATA_MISSING','source':None,'external_permission_issued':False}
    try:
        value,_,target,_=_notification_binding(root,identity,target_role)
        existing=_root_slot_read(root)
        intents=[e.get('details',{}).get(NOTIFICATION_CAPACITY_EVENT) for e in
            w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS,where={'task_id':value['task_id']})
            if e.get('details',{}).get(NOTIFICATION_CAPACITY_EVENT,{}).get('identity')==value]
        if intents or isinstance(existing,dict) and existing.get('kind')==NOTIFICATION_KIND and existing.get('identity')==value:
            return {**result,'state':'original_notification_capacity_intent_readback_required',
                'source':existing.get('root_source') if isinstance(existing,dict) else None,
                'original_intent_present':bool(intents),'original_slot':existing,
                'reason':'reserved_not_sent/UNKNOWN must retain its original preparation pins; no new prepare or ACTIVE bypass'}
        if actual_active_observation is not None:
            try:
                active=_notification_active(root,value,target_role,actual_active_observation)
                return {**result,'queue_allowed':True,'requires_reservation':False,
                        'state':'existing_ACTIVE_original_receiver_queue','active_source':active,
                        'source':actual_active_observation}
            except (w.WorkflowError,ValueError,OSError,KeyError,TypeError,AttributeError) as error:
                result['active_source_unproven']=str(error)
        guard=shared_serial_guard(root,target_thread_id=target['task_id'],transport=transport)
        return {**result,'queue_allowed':guard.get('new_activation_allowed') is True,
                'state':'new_notification_window_capacity' if guard.get('new_activation_allowed') is True else 'notification_wait_original_capacity',
                'source':guard.get('source'),'root_guard':guard}
    except (w.WorkflowError,ValueError,OSError,KeyError,TypeError,AttributeError) as error:
        return {**result,'reason':str(error)}


def _notification_preparation(root, identity, prepared, *, before_send):
    import result_coordination as rc
    from department_event_dispatcher import key, OfficialQueueTransport
    value=rc.exact_identity(identity); directory=Path(prepared.get('directory','')).resolve()
    expected=(Path(root)/'logs/department-event-dispatcher/prepared'/key(value)).resolve()
    require(directory==expected and directory.is_relative_to(Path(root).resolve()),'one normal original notification preparation directory')
    request_pin=w.file_digest(root,str((directory/'actual-prepare-request.json').relative_to(root)))
    preparation=w.file_digest(root,str((directory/'actual-prepare-result.json').relative_to(root)))
    request=doc(root,request_pin); normal=doc(root,preparation); notification=normal.get('notification',{})
    value,source,target,route=_notification_binding(root,value,request.get('target_department'),
        notice=None if before_send else w.read_json(rc._notification_path(root,value)))
    exact=rc.delivery_identity(root,value,route=route) if before_send else notification.get('delivery_identity',{})
    fields={name:notification.get(name) for name in FIELDS}
    action='notify-result-'+rc._delivery_key(exact).split(':',1)[-1]
    require(prepared.get('message')==OfficialQueueTransport.message(None,request.get('target_department'),key(value),value),
            'canonical original dispatcher notification text required; notify action is not an arbitrary body carrier')
    require(request.get('result_notification')==value and request.get('task_id')==value['task_id']
            and request.get('sender_department')==value['sender_department']
            and request.get('delivery_mode')=='official_native_queue' and request.get('authorization_changes')==[]
            and MARKER not in request and request.get('payload')==normal.get('payload')
            and w.file_digest(root,request.get('payload',{}).get('path',''))==request.get('payload')
            and prepared.get('identity')==value and prepared.get('thread_id')==target['task_id']
            and prepared.get('message')==w.safe_path(root,request['payload']['path']).read_text()
            and prepared.get('payload_sha256')==request.get('payload_sha256')==request['payload']['sha256']
            and normal.get('status')=='ready_to_queue' and normal.get('delivery_mode')=='official_native_queue'
            and all(normal.get(k) is False for k in ('ordinary_send_allowed','message_sent','external_permission_issued'))
            and notification.get('result')=='ready' and notification.get('identity')==value
            and notification.get('delivery_identity')==exact and fields.get('action_id')==action
            and fields.get('scope')=='department_result:'+value['task_id']+':'+value['sender_department']
            and fields.get('task_id')==value['task_id'] and fields.get('action_class')=='thread_message'
            and notification.get('department')==value['sender_department']
            and fields.get('source_project_id')==source['project_id']
            and all(fields.get(k)==target.get(v) for k,v in {'target_project_id':'project_id','target_thread_id':'task_id',
                'target_thread_title':'title','target_cwd':'cwd','target_sidebar_section_id':'sidebar_section_id'}.items())
            and fields.get('target_department')==request.get('target_department')
            and fields.get('payload_sha256')==request['payload_sha256']
            and all(request.get(k,fields[k])==fields[k] for k in FIELDS),
            'actual normal result-notification request/result/identity/payload/FIELDS only; no receipt disguise')
    policy=normal.get('policy_decision',{})
    policies=w.read_jsonl(Path(root)/w.POLICY_DECISIONS,where={'decision_id':prepared.get('policy_decision_id')})
    require(policies==[policy] and policy.get('decision_id')==prepared.get('policy_decision_id')
            and policy.get('status')=='allow' and policy.get('department')==value['sender_department']
            and policy.get('external_permission_issued') is False
            and all(policy.get(k)==v for k,v in fields.items()),'one real original normal notification allow policy required')
    if before_send:
        checked=w._parse_observed_at(policy.get('checked_at'))
        require(checked is not None and 0 <= (dt.datetime.now(dt.timezone.utc)-checked).total_seconds() <= 300,
                'fresh normal notification policy before capacity reservation')
        delivery=rc.validate_notification_delivery(root,value)
        require(delivery.get('delivery_identity')==exact and delivery.get('payload')==request['payload']
                and delivery.get('delivery_owner')==value['sender_department'] and delivery.get('state')=='prepared',
                'actual original notification lease/identity/payload must still be prepared')
    return {'identity':value,'fields':fields,'request':request,'request_pin':request_pin,
            'normal_preparation':preparation,'prepared':normal,'directory':str(directory.relative_to(root)),
            'target':target,'target_role':request['target_department'],'delivery_identity':exact,'policy':policy}


def reserve_notification_serial(root, identity, prepared, transport, *, actual_active_observation=None, allow_new_capacity=True):
    """Reserve real new capacity; an ACTIVE queue consumes no new root window."""
    from department_event_dispatcher import Store
    with w.workflow_lock(root),w.request_validation_context() as validation:
        normal=_notification_preparation(root,identity,prepared,before_send=True)
        admission=notification_queue_admission(root,identity,normal['target_role'],transport,
            actual_active_observation=actual_active_observation)
        require(admission.get('queue_allowed') is True,'notification capacity is not admitted: '+str(admission))
        require(admission.get('requires_reservation') is False or allow_new_capacity is True,
                'this pump already used new-window capacity; an ACTIVE proof cannot fall back to another new reservation')
        if admission['requires_reservation'] is False:
            validation.recheck()
            return {'queue_allowed':True,'requires_reservation':False,'state':admission['state'],'active_source':admission['active_source']}
        require(_root_serial_read(root)[1]==admission['source'],'root changed before normal notification reservation')
        fields=normal['fields']
        intent={'schema':'normal-result-notification-capacity-intent/v1','kind':NOTIFICATION_KIND,
            'identity':normal['identity'],'delivery_identity':normal['delivery_identity'],
            'request':normal['request_pin'],'normal_preparation':normal['normal_preparation'],
            'notification_fields':fields,'directory':normal['directory'],
            'policy_decision_id':normal['policy']['decision_id'],'root_source':admission['source'],
            'service_origin':SERVICE_ORIGIN,'business_goal_closed':False,'external_permission_issued':False}
        events=w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS,where={'task_id':fields['task_id']})
        prior=[e for e in events if e.get('details',{}).get(NOTIFICATION_CAPACITY_EVENT,{}).get('identity')==normal['identity']]
        require(not prior or len(prior)==1 and prior[0]['details'][NOTIFICATION_CAPACITY_EVENT]==intent,
                'original notification capacity intent differs; inspect its key before a new intent')
        slot={'schema':'root-original-resume-slot/v1','kind':NOTIFICATION_KIND,'status':'reserved_not_sent',
            **{k:intent[k] for k in ('identity','delivery_identity','request','normal_preparation','notification_fields',
                                   'directory','policy_decision_id','root_source','service_origin','business_goal_closed','external_permission_issued')},
            **{k:fields[k] for k in ('task_id','action_id','scope','target_thread_id')},'capacity_intent':intent}
        own=Store(Path(root))
        try:
            own.checkpoint_value(ROOT_SERIAL_SLOT);own.db.execute('BEGIN IMMEDIATE')
            require(own.db.execute('SELECT value FROM checkpoints WHERE name=?',(ROOT_SERIAL_SLOT,)).fetchone() is None,
                    'root capacity already has an original reservation/UNKNOWN')
            require(_root_serial_read(root)[1]==admission['source'],'root changed at notification capacity commit')
            _notification_preparation(root,identity,prepared,before_send=True)
            validation.recheck()
            if not prior:w.append_workflow_event(root,fields['task_id'],w.read_json(w.snapshot_path(root,fields['task_id']))['current_state'],
                {NOTIFICATION_CAPACITY_EVENT:intent,'actual_sender':identity['sender_department'],'external_permission_issued':False})
            own.db.execute('INSERT INTO checkpoints VALUES(?,?)',(ROOT_SERIAL_SLOT,json.dumps(slot,ensure_ascii=False,sort_keys=True)))
            own.db.commit()
            require(_root_serial_read(root)[1]==admission['source'] and _root_slot_read(root)==slot,
                    'normal notification root/slot changed before returning to original enqueue')
        except Exception:own.db.rollback();raise
        finally:own.close()
        return {'queue_allowed':True,'requires_reservation':True,'state':'notification_capacity_reserved','slot':slot}


def _notification_slot_prepared(root, slot):
    require(slot.get('kind')==NOTIFICATION_KIND and slot.get('schema')=='root-original-resume-slot/v1'
            and slot.get('status')=='reserved_not_sent','exact typed result-notification slot required')
    request=doc(root,slot.get('request'));prepared=doc(root,slot.get('normal_preparation'))
    outer={'directory':w.safe_path(root,slot['directory']),'identity':slot['identity'],'thread_id':slot['target_thread_id'],
           'message':w.safe_path(root,request['payload']['path']).read_text(),'payload_sha256':request['payload_sha256'],
           'policy_decision_id':slot['policy_decision_id']}
    normal=_notification_preparation(root,slot['identity'],outer,before_send=False)
    require(normal['request_pin']==slot['request'] and normal['normal_preparation']==slot['normal_preparation']
            and normal['fields']==slot['notification_fields'] and normal['delivery_identity']==slot['delivery_identity']
            and all(slot.get(k)==normal['fields'].get(k) for k in ('task_id','action_id','scope','target_thread_id')),
            'original notification slot/request/normal preparation fields changed')
    events=w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS,where={'task_id':slot['task_id']})
    intents=[e.get('details',{}).get(NOTIFICATION_CAPACITY_EVENT) for e in events
             if e.get('details',{}).get(NOTIFICATION_CAPACITY_EVENT,{}).get('identity')==slot['identity']]
    require(intents==[slot.get('capacity_intent')] and slot['capacity_intent'].get('root_source')==slot['root_source']
            and slot['capacity_intent'].get('request')==slot['request']
            and slot['capacity_intent'].get('notification_fields')==slot['notification_fields'],
            'one actual append-only notification capacity intent required')
    require(not w.validate_workflow_events(root,slot['task_id']),'intact normal notification source workflow chain')
    return normal


def _notification_native_metadata(normal, fresh_thread, original_page):
    # Canonical provider metadata may be absent, never explicitly conflicting.
    # The committed real intake SDK and original normal request are separate
    # pinned evidence; no value is inserted into the canonical native object.
    fixed=normal['target']; original=original_page.get('thread',{})
    for thread in (fresh_thread,original):
        require(all(thread.get(k)==fixed.get(v) for k,v in {'id':'task_id','cwd':'cwd'}.items())
                and thread.get('name',thread.get('title'))==fixed['title'],
                'canonical and committed receiver must retain exact native id/title/cwd')
        require(thread.get('hostId') in {None,fixed['host_id']}
                and thread.get('projectId') in {None,fixed['project_id']},
                'explicit native host/project conflict cannot use supplementary metadata')
    if fresh_thread.get('hostId') is None:
        require(original.get('hostId')==fixed['host_id'],
                'DATA_MISSING real committed receiver SDK host supplement')
    if fresh_thread.get('projectId') is None:
        require(original.get('projectId')==fixed['project_id']
                or normal['request'].get('target_project_id')==fixed['project_id'],
                'DATA_MISSING actual committed SDK/normal pinned request project supplement')
    return {'canonical_metadata_preserved':True,
            'actual_receiver_native_required':True,'normal_request':normal['request_pin']}


def _exact_notification_text_content(content, wanted):
    """Match only the original single text plus optional empty native metadata."""
    if not isinstance(content, list) or len(content) != 1 or not isinstance(content[0], dict):
        return False
    item = content[0]
    return (set(item) in ({"type", "text"}, {"type", "text", "text_elements"})
            and item.get("type") == "text" and item.get("text") == wanted
            and ("text_elements" not in item or item["text_elements"] == []))


def _same_notification_intake_message(current, original):
    """Match frozen intake to actual full-native message without inventing fields."""
    if not isinstance(current, dict) or not isinstance(original, dict):
        return False
    core = {'type', 'id', 'text', 'phase'}
    if set(original) != core or not core.issubset(current):
        return False
    if any(current.get(k) != original.get(k) for k in core):
        return False
    if not set(current).issubset(core | {'memoryCitation', 'delivery', 'questions', 'startedAtMs', 'completedAtMs'}):
        return False
    if any(current.get(k) is not None for k in ('memoryCitation', 'delivery', 'questions')):
        return False
    for key in ('startedAtMs', 'completedAtMs'):
        if key in current and (type(current[key]) not in (int, float) or not __import__('math').isfinite(current[key])):
            return False
    return True


def _notification_capacity_batch(root, proof, record, final):
    """Revalidate original notice transport/intake/finite turn; no A1 decision."""
    import result_coordination as rc
    from goal_delivery_runtime import _native_document
    slot=proof.get('notification_capacity');require(isinstance(slot,dict),'typed notification capacity source required')
    from department_event_dispatcher import key
    normal=_notification_slot_prepared(root,slot);directory=w.safe_path(root,slot['directory'])
    notice=w.read_json(rc._notification_path(root,slot['identity']))
    require(rc.exact_identity(notice.get('identity',{}))==slot['identity']
            and rc.frozen_notification_route(root,notice).get('target_department')==normal['target_role'],
            'one original fixed notification source/receiver required')
    native=w.read_json(directory/'native-queue-intent.json');effect=w.read_json(directory/'native-queue-result.json')
    match=re.fullmatch(r'Queued message ([0-9a-f-]{36}) for thread ([0-9a-f-]{36})\.\s*',effect.get('stdout',''))
    start=w._parse_observed_at(native.get('started_at'));finish=w._parse_observed_at(effect.get('finished_at'))
    checked=w._parse_observed_at(normal['policy'].get('checked_at'));queue=notice.get('native_queue_transport',{})
    require(native and type(effect.get('exit_code')) is int and effect['exit_code']==0 and isinstance(effect.get('stderr'),str)
            and match and match[2]==slot['target_thread_id'] and all(effect.get(k)==v for k,v in native.items())
            and native.get('transport')=='official_codex_queue' and native.get('thread_id')==slot['target_thread_id']
            and native.get('payload_sha256')==normal['fields']['payload_sha256']
            and native.get('policy_decision_id')==slot['policy_decision_id'] and native.get('intake_claimed') is False
            and start is not None and finish is not None and checked is not None
            and checked<=start<=finish<=dt.datetime.now(dt.timezone.utc) and (start-checked).total_seconds()<=300
            and queue.get('state')=='accepted' and queue.get('native_message_id')==match[1]
            and queue.get('payload_sha256')==normal['fields']['payload_sha256']
            and all(queue.get(k)==v for k,v in native.items()) and queue.get('event_key')==key(slot['identity']),
            'UNKNOWN/accepted mismatch original notification key is not a finite receipt')
    intake=rc.received_notification(root,notice)
    require(isinstance(intake,dict),'accepted/ACK alone cannot release notification capacity')
    rc._committed_result(root,intake);actor,owner=rc._committed_intake_actor(root,intake)
    require(actor==normal['target_role'] and isinstance(owner,str) and owner.split(':',1)[0]==slot['target_thread_id']
            and intake.get('actual_receiver_native') and intake.get('actual_receiver_message_id'),
            'real SQL/native intake must belong to this fixed original receiver')
    original=_native_document(root,intake['actual_receiver_native'])
    _notification_native_metadata(normal,proof.get('thread',{}),original)
    occurrences=[t for t in original.get('turns',[]) if any(m.get('id')==intake['actual_receiver_message_id'] for m in t.get('items',[]))]
    require(len(occurrences)==1 and occurrences[0].get('id')==record['current_active_turn'],
            'actual committed intake belongs to the exact receiving turn')
    require(record.get('current_active_original_window')==slot['target_thread_id']
            and record.get('current_scope')==normal['fields']['scope'] and proof.get('thread',{}).get('id')==slot['target_thread_id'],
            'finite notification proof must not release another root window/scope')
    turns=[t for t in proof.get('turns',[]) if t.get('id')==record['current_active_turn']]
    require(len(turns)==1,'one exact current finite notification turn')
    turn=turns[0];items=turn.get('items',[]);wanted=w.safe_path(root,normal['request']['payload']['path']).read_text()
    inputs=[(i,m) for i,m in enumerate(items) if m.get('type')=='userMessage'
            and _exact_notification_text_content(m.get('content'),wanted)]
    intake_messages=[(i,m) for i,m in enumerate(items) if m.get('id')==intake['actual_receiver_message_id']]
    finals=[(i,m) for i,m in enumerate(items) if m.get('type')=='agentMessage' and m.get('phase')=='final_answer'
            and isinstance(m.get('text'),str) and m['text'].strip()]
    require(len(inputs)==len(intake_messages)==len(finals)==1 and inputs[0][0]<intake_messages[0][0]<=finals[0][0]
            and finals[0][1]==final and sum(_same_notification_intake_message(intake_messages[0][1], item) for item in occurrences[0].get('items',[])) == 1
            and slot['identity']['result_sha256'] in intake_messages[0][1].get('text','')
            and type(turn.get('startedAt')) in {int,float} and type(turn.get('completedAt')) in {int,float}
            and start.timestamp()<=turn['startedAt']<=turn['completedAt']<=dt.datetime.now(dt.timezone.utc).timestamp()
            and turn.get('status')=='completed' and not turn.get('error'),
            'unique original notification input plus committed native intake and exact finite final required')
    # A separate later final cannot be a maintenance-only ACK. It must actually
    # discuss this task/result or declare a structured exact dependency.
    dependency=proof.get('safe_dependency')
    related=(intake['record_id'] in final['text'] or slot['identity']['task_id'] in final['text'] or slot['identity']['result_sha256'] in final['text'])
    if dependency is not None:
        require(isinstance(dependency,dict) and all(isinstance(dependency.get(k),str) and dependency[k].strip()
                for k in ('owner','action','dependency_input')) and dependency['owner'] in w.department_registry(root)
                and all(dependency[k] in final['text'] for k in ('owner','action','dependency_input')),
                'structured notification safe dependency must be native and exactly named')
        related=True
    require(related and (finals[0][0]==intake_messages[0][0] or final.get('text','').strip()!=intake_messages[0][1].get('text','').strip()),
            'maintenance-only or unrelated final cannot release the original notification batch')
    return {'kind':NOTIFICATION_KIND,'identity':slot['identity'],'received_record_id':intake['record_id'],
            'recipient_turn_id':turn['id'],'native_message_id':match[1],'business_goal_closed':False,
            'coordination_obligation_only':True,'current_state':'safe_dependency' if dependency is not None else 'completed'}


def _settle_notification_partial_release(root, transport, record, before, slot):
    # Recover only our own verified root-write/SQL-delete crash window. The
    # current root bytes are not rewritten or attributed to another original.
    from department_event_dispatcher import Store
    observer=record.get('current_release_observer',{})
    require(observer.get('kind')==NOTIFICATION_KIND and observer.get('service_origin')==SERVICE_ORIGIN
            and observer.get('source_root')==slot['root_source']
            and observer.get('normal_intent_request')==slot['request']
            and record.get('current_active_original_window')==slot['target_thread_id']
            and record.get('current_scope')==slot['scope'] and record.get('current_action_id')==slot['action_id'],
            'root drift is not this exact notification partial release')
    proof=doc(root,record.get('current_release_native_proof'))
    require(proof.get('notification_capacity')==slot,'current typed release proof does not own this original slot')
    at=w._parse_observed_at(record.get('current_release_observed_at_UTC'))
    require(at is not None,'actual notification release proof time required')
    _,turn,final=_root_serial_native(proof,slot['target_thread_id'],record['current_active_turn'],at)
    _notification_capacity_batch(root,proof,record,final)
    history=getattr(transport,'history',None)
    require(history is not None and callable(getattr(history,'call',None)),'fresh original native for partial notification release')
    thread=history.call('thread/read',{'threadId':slot['target_thread_id'],'includeTurns':False})['thread']
    turns=history.call('thread/turns/list',{'threadId':slot['target_thread_id'],'limit':1,'sortDirection':'desc','itemsView':'full'})['data']
    _root_serial_native({'thread':thread,'turns':turns},slot['target_thread_id'],turn['id'],dt.datetime.now(dt.timezone.utc))
    with w.workflow_lock(root),w.request_validation_context() as validation:
        require(_root_serial_read(root)[1]==before and _root_slot_read(root)==slot,'root or exact old slot changed before partial-release cleanup')
        _notification_capacity_batch(root,proof,record,final);validation.recheck()
        own=Store(Path(root))
        try:
            own.db.execute('BEGIN IMMEDIATE')
            row=own.db.execute('SELECT value FROM checkpoints WHERE name=?',(ROOT_SERIAL_SLOT,)).fetchone()
            require(row and json.loads(row[0])==slot and _root_serial_read(root)[1]==before,
                    'partial notification cleanup cannot release a different slot/root')
            own.db.execute('DELETE FROM checkpoints WHERE name=? AND value=?',(ROOT_SERIAL_SLOT,json.dumps(slot,ensure_ascii=False,sort_keys=True)))
            own.db.commit()
        except Exception:own.db.rollback();raise
        finally:own.close()
    require(_root_serial_read(root)[1]==before,'current root must remain byte-for-byte unchanged after partial cleanup')
    return {'schema':'root-original-serial-observation/v1','kind':NOTIFICATION_KIND,
            'state':'notification_capacity_own_partial_release_settled','root_release_recorded':True,
            'source':before,'current_root_preserved':True,'business_goal_closed':False,'external_permission_issued':False}


def _notification_refresh_head(proof, window, receiving_turn, observed):
    """A newer finite head proves availability, never the original receipt."""
    head = proof.get('fresh_current_head')
    if head is None:
        return receiving_turn
    require(isinstance(head, dict) and isinstance(head.get('turns'), list)
            and len(head['turns']) == 1 and isinstance(head['turns'][0], dict),
            'one separate current notification receiver head required')
    head_id = head['turns'][0].get('id')
    require(isinstance(head_id, str) and bool(head_id), 'exact current notification receiver head ID required')
    _, turn, _ = _root_serial_native(head, window, head_id, observed)
    require(turn['id'] == receiving_turn['id'] or turn['startedAt'] >= receiving_turn['completedAt'],
            'notification receiver head cannot precede or overlap the original completed intake')
    return turn


def _observe_notification_serial(root, transport):
    """Exact notification slot observer, separate from producer/routine batches."""
    import hashlib
    import result_coordination as rc
    from department_event_dispatcher import Store
    result={'schema':'root-original-serial-observation/v1','kind':NOTIFICATION_KIND,
            'state':'notification_capacity_observation_blocked','root_release_recorded':False,
            'business_goal_closed':False,'external_permission_issued':False,'service_origin':SERVICE_ORIGIN}
    try:
        before_record,before=_root_serial_read(root);slot=_root_slot_read(root);refresh=slot is None
        if refresh:
            prior=doc(root,before_record.get('current_release_native_proof'))
            slot=prior.get('notification_capacity')
            require(isinstance(slot,dict) and slot.get('kind')==NOTIFICATION_KIND
                    and before_record.get('current_release_observer',{}).get('kind')==NOTIFICATION_KIND
                    and before_record.get('current_active_original_window')==slot['target_thread_id']
                    and before_record.get('current_action_id')==slot['action_id']
                    and before_record.get('current_scope')==slot['scope'],
                    'only the same already released notification proof may be refreshed')
            fresh=shared_serial_guard(root,transport=transport)
            if fresh.get('new_activation_allowed') is True:
                return {**result,'state':'root_serial_release_already_fresh','source':before}
        elif isinstance(slot,dict) and slot.get('kind')==NOTIFICATION_KIND and slot.get('root_source')!=before:
            return _settle_notification_partial_release(root,transport,before_record,before,slot)
        require(isinstance(slot,dict) and slot.get('kind')==NOTIFICATION_KIND
                and (refresh or slot['root_source']==before),
                'notification observer cannot overwrite a newer root or a different slot')
        normal=_notification_slot_prepared(root,slot)
        history=getattr(transport,'history',None)
        require(history is not None and callable(getattr(history,'call',None)),'original readonly native connection required')
        thread=history.call('thread/read',{'threadId':slot['target_thread_id'],'includeTurns':False})['thread']
        turns=history.call('thread/turns/list',{'threadId':slot['target_thread_id'],'limit':30,'sortDirection':'desc','itemsView':'full'})['data']
        require(all(thread.get(k)==normal['target'].get(v) for k,v in {'id':'task_id','cwd':'cwd'}.items())
                and thread.get('hostId') in {None,normal['target']['host_id']}
                and thread.get('name',thread.get('title'))==normal['target']['title']
                and thread.get('projectId') in {None,normal['target']['project_id']},'fresh fixed notification receiver native identity')
        status=thread.get('status');status=status.get('type') if isinstance(status,dict) else status
        require(status in {'idle','notLoaded'} and turns and all(type(t.get('startedAt')) in {int,float} for t in turns),
                'notification receiver still active/UNKNOWN; retain capacity')
        latest=max(turns,key=lambda t:t['startedAt'])
        require(latest.get('status')=='completed' and not latest.get('error'),'current receiving window must be at a real finite boundary')
        notice=w.read_json(rc._notification_path(root,slot['identity']));intake=rc.received_notification(root,notice)
        require(intake is not None,'real original notification intake is still missing')
        from goal_delivery_runtime import _native_document
        original=_native_document(root,intake.get('actual_receiver_native'))
        metadata=_notification_native_metadata(normal,thread,original)
        received=[t for t in original.get('turns',[]) if any(m.get('id')==intake.get('actual_receiver_message_id') for m in t.get('items',[]))]
        require(len(received)==1,'one SQL-native intake turn')
        actual=[t for t in turns if t.get('id')==received[0].get('id')]
        require(len(actual)==1 and (actual[0].get('id')==latest.get('id') or
                refresh and actual[0].get('id')==before_record.get('current_active_turn')),
                'first release requires the exact current intake; refresh requires its exact previously released turn')
        wanted=w.safe_path(root,normal['request']['payload']['path']).read_text()
        matches=[t for t in turns for m in t.get('items',[]) if m.get('type')=='userMessage'
                 and _exact_notification_text_content(m.get('content'),wanted)]
        require(len(matches)==1 and matches[0].get('id')==actual[0].get('id'),
                'duplicate or copied original notification input; retain original capacity')
        turn=actual[0];finals=[m for m in turn.get('items',[]) if m.get('type')=='agentMessage' and m.get('phase')=='final_answer'
                                    and isinstance(m.get('text'),str) and m['text'].strip()]
        require(len(finals)==1,'one exact normal finite notification final')
        stamp=dt.datetime.now(dt.timezone.utc)
        current={**before_record,'current_active_original_window':slot['target_thread_id'],
                 'current_active_turn':turn['id'],'current_action_id':slot['action_id'],'current_scope':normal['fields']['scope'],'current_state':'completed'}
        keep={intake['actual_receiver_message_id'],finals[0]['id']}
        keep.update(m['id'] for m in turn['items'] if m.get('type')=='userMessage'
                    and _exact_notification_text_content(m.get('content'),wanted))
        finite={**{k:v for k,v in turn.items() if k!='items'},
                'items':[m for m in turn['items'] if m.get('id') in keep]}
        _, _, head_final = _root_serial_native({'thread':thread,'turns':[latest]},thread['id'],latest['id'],stamp)
        head={**{k:v for k,v in latest.items() if k!='items'},'items':[head_final]}
        proof={'source':'official_app_server_readonly_history','service_origin':SERVICE_ORIGIN,
               'thread':{**thread,'title':thread.get('name',thread.get('title'))},'turns':[finite],
               'notification_capacity':slot,'original_root_record':before_record,'metadata_supplement':metadata,
               'fresh_current_head':{'thread':thread,'turns':[head]}}
        # Safe dependency is accepted only as structured native JSON, never a
        # free-form caller flag. It remains an open business obligation.
        declarations=[line[len('FLASHCAST_NOTIFICATION_SAFE_DEPENDENCY '):] for line in finals[0]['text'].splitlines()
                      if line.startswith('FLASHCAST_NOTIFICATION_SAFE_DEPENDENCY ')]
        if declarations:
            require(len(declarations)==1,'one normal structured notification dependency')
            proof['safe_dependency']=json.loads(declarations[0])
        batch=_notification_capacity_batch(root,proof,current,finals[0]);current['current_state']=batch['current_state']
        _notification_refresh_head(proof, thread['id'], turn, stamp)
        assigned=before_record.get('assigned_next_original_window');consumed=before_record.get('current_assigned_next_consumed')
        prior_consumed=bool(assigned and isinstance(consumed,dict) and consumed.get('thread_id')==assigned
            and consumed.get('completed_turn')==before_record['current_active_turn']
            and consumed.get('release_proof')==before_record.get('current_release_native_proof'))
        require(not assigned or assigned==slot['target_thread_id'] or prior_consumed,
                'a different unconsumed original next window cannot be cleared by notification completion')
        if assigned and assigned!=slot['target_thread_id']:
            proof['prior_consumed_assignment']={'assigned_next_original_window':assigned,'consumed':consumed,'root_source':before}
        with w.workflow_lock(root),w.request_validation_context() as validation:
            require(_root_serial_read(root)[1]==before and _root_slot_read(root)==(None if refresh else slot),'root/notification slot changed before exact release CAS')
            _notification_capacity_batch(root,proof,current,finals[0]);validation.recheck()
            if refresh and head['id'] != turn['id']:
                fresh_thread=history.call('thread/read',{'threadId':thread['id'],'includeTurns':False})['thread']
                fresh_turns=history.call('thread/turns/list',{'threadId':thread['id'],'limit':1,
                                        'sortDirection':'desc','itemsView':'full'})['data']
                _root_serial_native({'thread':fresh_thread,'turns':fresh_turns},thread['id'],head['id'],
                                    dt.datetime.now(dt.timezone.utc))
            directory=w.safe_path(root,'logs/department-event-dispatcher/root-serial-release');directory.mkdir(parents=True,exist_ok=True)
            path=directory/(hashlib.sha256(json.dumps(proof,ensure_ascii=False,sort_keys=True).encode()).hexdigest()+'.json')
            if not path.exists():w.atomic_write_json(path,proof)
            pin=w.file_digest(root,str(path.relative_to(root)))
            updated={**before_record,**{k:current[k] for k in ('current_active_original_window','current_active_turn','current_action_id','current_scope','current_state')},
                'current_original_thread':slot['target_thread_id'],'current_active_was_new_recovery':False,
                'current_recovery_receipt_state':'safe_dependency_with_fresh_native_proof' if current['current_state']=='safe_dependency' else 'completed_original_window_with_fresh_native_proof',
                'current_release_native_proof':pin,'current_release_observed_at_UTC':stamp.isoformat(),
                'current_release_observer':{'service_origin':SERVICE_ORIGIN,'kind':NOTIFICATION_KIND,
                    'source_root':slot['root_source'],'previous_root_source':before,'normal_intent_request':slot['request'],'business_goal_closed':False,'external_permission_issued':False}}
            if assigned==slot['target_thread_id']:
                updated['current_assigned_next_consumed']={'thread_id':assigned,'completed_turn':turn['id'],
                    'request':slot['request'],'release_proof':pin,'root_source':slot['root_source']}
            elif assigned and prior_consumed:
                updated['assigned_next_original_window']=None;updated.pop('current_assigned_next_consumed',None)
            own=Store(Path(root))
            try:
                own.db.execute('BEGIN IMMEDIATE')
                actual_slot=own.db.execute('SELECT value FROM checkpoints WHERE name=?',(ROOT_SERIAL_SLOT,)).fetchone()
                require((actual_slot is None if refresh else actual_slot and json.loads(actual_slot[0])==slot)
                        and _root_serial_read(root)[1]==before,'exact original slot/root before release')
                w.atomic_write_json(w.safe_path(root,ROOT_SERIAL_PATH),updated)
                if not refresh:own.db.execute('DELETE FROM checkpoints WHERE name=? AND value=?',(ROOT_SERIAL_SLOT,json.dumps(slot,ensure_ascii=False,sort_keys=True)))
                own.db.commit()
            except Exception:own.db.rollback();raise
            finally:own.close()
        return {**result,'state':'notification_capacity_finite_intake_released','root_release_recorded':True,
                'source':w.file_digest(root,ROOT_SERIAL_PATH),'release_proof':pin,'received_record_id':batch['received_record_id']}
    except (w.WorkflowError,ValueError,OSError,KeyError,TypeError,AttributeError) as error:
        return {**result,'reason':str(error)}
