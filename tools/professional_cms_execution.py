"""Append-only professional CMS source binding; never a platform permit."""
from pathlib import Path
from copy import deepcopy
import argparse
import json
import re
import workflow_control as w

SCHEMA = 'professional-cms-execution-source-registration/v1'
EVENT = 'professional_cms_execution_source'

# This codec consumes original required actions and received professional sources;
# it creates no business task, execution grant, current CAS or WEB completion.
INCREMENT_SCHEMA = 'original-received-CMS-content-increment-source/v1'

def _original_increment_delta(before, desired, fragment, row):
    import department_autonomy as a
    from html import unescape
    need = a.require
    need(set(desired) == {'content_zh'} and isinstance(desired['content_zh'],str)
         and fragment and fragment not in before['content_zh'] and desired['content_zh'].count(fragment) == 1
         and desired['content_zh'].replace(fragment,'',1) == before['content_zh']
         and w.sha256_value(before['content_zh']) == row['before_digest']
         and w.sha256_value(desired) == row['desired_digest']
         and row['expected_title'] in fragment and row['expected_CTA_text'] in fragment
         and row['expected_CTA_href'] in unescape(fragment),
         'only the actual original missing fragment may be inserted; no whole-field rewrite or duplicate')
    return True


def received_increment_context(root, snapshot, item):
    import department_autonomy as a
    import goal_delivery_runtime as g
    import result_coordination as rc
    from html import unescape
    need = a.require
    goal = a.participant(root, snapshot, snapshot['goal_delivery']['primary_owner'])
    frozen = a.document(root, snapshot['goal_contract'])
    need(a.current_mode(root) and not a.autonomous_goal(frozen)
         and item.get('schema') == INCREMENT_SCHEMA
         and set(item) == {'schema','task_id','source_action_id','owner_input','action_id'}
         and item.get('task_id') == snapshot['task_id']
         and all(goal.get(k) == frozen.get(k) for k in ('primary_owner','producer_departments',
                    'authorized_scope','human_authorization','required_execution_actions','completion_criteria')),
         'unchanged active original professional contract and exact increment source required')
    owner = goal['primary_owner']; request_pin = item['owner_input']; request = a.document(root, request_pin)
    scope = request.get('scope')
    need(a.professional(root, owner) and request.get('task_id') == snapshot['task_id']
         and request.get('original_owner') == owner and scope in frozen['authorized_scope']
         and request.get('original_goal_contract') == snapshot['goal_contract']
         and request.get('original_authorization') == goal['authorization_pin'],
         'actual original owner/input/task/scope/human and contract required')
    human = a.document(root, goal['authorization_pin'])
    native = g._native_document(root, human.get('native_evidence'))
    auth = frozen['human_authorization']; message = human.get('message', {})
    originals = [(t,m) for t in native.get('turns',[]) for m in t.get('items',[])
                 if m.get('id') == auth.get('message_id') and m.get('type') == 'userMessage']
    need(message.get('type') == 'userMessage' and message.get('id') == auth.get('message_id')
         and human.get('source_thread_id') == auth.get('source_thread_id') == native.get('thread',{}).get('id')
         and len(originals) == 1 and originals[0][1].get('content') == message.get('content')
         and auth.get('executor') == owner and auth.get('scope') == scope,
         'unchanged actual original human native message, never a caller authorization label')
    states = g._collaboration_wait_states(root, snapshot, only_action_id=item['source_action_id'])
    need(len(states) == 1 and states[0].get('status') in {'message_received','result_received'}
         and states[0].get('received') is True, 'real original owner-to-SYS receipt and nonempty ACK required')
    order = states[0]['approved_action']; body = w.safe_path(root, order['payload']['path']).read_text()
    need(all(order.get(k) == v for k,v in {'task_id':snapshot['task_id'],'sender_department':owner,
         'target_department':'system-development','action_class':'thread_message','scope':scope}.items())
         and w.file_digest(root, order['payload']['path']) == order['payload']
         and request_pin['path'] in body and request_pin['sha256'] in body,
         'actual frozen owner transport must bind the whole exact input')
    report_pin = request['actual_PUB_result']; report = a.document(root, report_pin)
    box_pin = request['actual_PUB_outbox']; box = a.document(root, box_pin)
    identity = rc.exact_identity({'task_id':snapshot['task_id'],'sender_department':'publishing',
                                 'candidate_version':box['candidate_version'],'result_sha256':box_pin['sha256']})
    received = rc._received_delivery(root, identity, {'target_department':owner})
    need(received is not None and received.get('outbox') == box_pin
         and box.get('department') == report.get('department') == 'publishing'
         and box.get('task_id') == report.get('task_id') == snapshot['task_id']
         and box.get('scope') == report.get('scope') == scope
         and report.get('original_business_owner') == owner and report_pin in box.get('evidence',[]),
         'one actual committed SQL/native PUB result in original owner custody required')
    actions = [x for x in frozen['required_execution_actions'] if x.get('action_id') == item['action_id']]
    rows = [x for x in report.get('rows',[]) if x.get('original_action') == item['action_id']]
    need(len(actions) == len(rows) == 1 and actions[0].get('action_class') == 'cms_write'
         and actions[0].get('department') == 'publishing' and actions[0].get('scope') in frozen['authorized_scope'],
         'one original required CMS action and independently received row only')
    row = rows[0]
    need(any(isinstance(v,dict) and v == row for v in request.values())
         and row.get('field') == 'content_zh' and row.get('stable38_MS11_required') is True
         and all(type(row.get(k)) is int and row[k] == 0 for k in
                 ('own_permit_or_Saved_count','active_or_unknown_permits','actual_Save','actual_preview','actual_policy_or_permit')),
         'exact independently requested row with no known pending/unknown effect; held rows cannot be promoted')
    fragment_pin = row['existing_HTML_fragment_reused_no_recreation']; fragment_path = w.safe_path(root, fragment_pin['path'])
    need(w.file_digest(root,str(fragment_path)) == fragment_pin and row['MD_source'] in frozen.get('existing_results',[]),
         'original frozen content source and received unchanged native fragment required')
    md_path = w.safe_path(root,row['MD_source']['path'])
    need(w.file_digest(root,str(md_path)) == row['MD_source'] and md_path.suffix == '.md', 'exact original MD bytes')
    before_pin = row['independent_before_backup']; before = a.document(root,before_pin)
    observed = a.document(root,row['current_authenticated_full41'])
    need(observed.get('rows') == [{'record':before}], 'actual authenticated full41 and independent full backup must agree')
    stable = sorted(set(before)-{'content_zh','updated_at','version'}); ms = sorted(k for k in before if k.endswith('_ms'))
    need(len(before) == 41 and len(stable) == 38 and len(ms) == 11
         and before.get('id') == row['record_id'] and before.get('slug') == row['slug']
         and before.get('status') == 'published' and type(before.get('version')) is int
         and before['version'] == row['version'] and before['updated_at'] == row['observed_rawCAS']
         and w._parse_observed_at(before['updated_at']) is not None,
         'full41/stable38/MS11 and exact existing published record/rawCAS required as dated source only')
    effects = a.document(root,row['original_key_and_same_record_effects'])
    need(isinstance(effects.get('rows'),list) and len(effects['rows']) == row['other_completed_same_record_permits']
         and all(x.get('record_id') == row['record_id'] and x.get('slug') == row['slug']
                 and x.get('task_id') != snapshot['task_id'] and x.get('status') == 'completed' for x in effects['rows']),
         'original-key and same-row pending/unknown effects must remain absent in the actual source observation')
    # A shoe/other held row has no actual current one-field merge. No synthetic
    # default or W baseline is accepted in place of that future own source.
    desired = a.document(root,row.get('current_one_field_patch'))
    fragment = fragment_path.read_text()
    _original_increment_delta(before, desired, fragment, row)
    observed_at = w._parse_observed_at(observed.get('observed_at')); reported_at = w._parse_observed_at(report.get('actual_at'))
    requested_at = w._parse_observed_at(request.get('at'))
    need(observed_at and reported_at and requested_at and observed_at <= reported_at <= requested_at,
         'real dated source/report/request chronology; this does not refresh execution facts')
    pub = w.department_registry(root)['publishing']['chat_binding']
    returned = g._native_document(root,received['actual_native_completion'])
    need(all(returned.get('thread',{}).get(k) == pub[v] for k,v in
             {'id':'task_id','title':'title','cwd':'cwd'}.items()) and pub['project_id'] == a.PROJECT,
         'actual current original PUB completion identity/project/directory required')
    channel = w.read_json(Path(root)/'data/department-registry.json')['collaboration_bindings'].get('designated-development')
    need(channel and channel['project_id'] != a.PROJECT and channel['cwd'] != str(Path(root).resolve()),
         'registered original external WEB channel remains separate')
    act = actions[0]; version = act['action_id']
    action = {'task_id':snapshot['task_id'],'action_id':act['action_id'],'action_class':'cms_write',
              'scope':act['scope'],'business_scope':scope,'candidate_version':version,'table':'services',
              'record_id':before['id'],'slug':before['slug'],'changed_fields':['content_zh'],'execution_department':'publishing'}
    target = {'id':before['id'],'slug':before['slug'],'contentType':'service','table':'services','taskId':snapshot['task_id'],
              'actionId':act['action_id'],'candidateVersion':version,'scope':act['scope'],'changedFields':['content_zh'],
              'baselineProjectionFields':sorted(before),'baselineFieldsSha256':w.sha256_value(before),
              'desiredFieldsSha256':w.sha256_value(desired),'rollbackFieldsSha256':w.sha256_value({'content_zh':before['content_zh']}),
              'expectedUpdatedAt':before['updated_at'],'retainedProjectionFields':stable,
              'retainedFieldsSha256':w.sha256_value({k:before[k]for k in stable}), 'rollbackAllowed':True,'requiresParentRun':True}
    need(not w.validate_workflow_events(root,snapshot['task_id']) and not w._validate_receipt_chain(root,snapshot['task_id'])[1],
         'intact original workflow and receipt chains')
    return {'action':action,'source':request_pin,'baseline_pin':before_pin,'owner':owner,'business_scope':scope,
            'executor':'publishing','channel':'designated-development','carrier':request_pin,'desired':desired,
            'before':{'content_zh':before['content_zh']},'protected_fields':{'not_written_fields':sorted(set(before)-{'content_zh'}),
                'server_CAS_metadata':['updated_at','version'],'stable_business_readback_fields':stable},
            'owner_result':box_pin,'original_explicit_delivery':True,'physical_target':target,
            'dated_source_not_execution_CAS':True,'current_PUB_binding':pub,'external_WEB_binding':channel,
            'business_contract_unchanged':True,'permission_issued':False}


ANSWER_SOURCE_SCHEMA = 'original-received-CMS-answer-span-source/v1'


def _answer_span_projection(source,current,original,spans):
    import department_autonomy as a
    need=a.require
    fields=sorted(x['field']for x in source['existing_two_answer_spans'])
    need(fields==sorted(original['changed_fields'])==['content_en','content_zh']
         and source['scope']==f"company.example:blog_posts/{current['id']}:content_en,content_zh",
         'only original two answer fields and exact physical scope')
    desired={};deltas=[]
    import hashlib
    digest=lambda x:hashlib.sha256(x.encode()).hexdigest()
    for proposed in source['existing_two_answer_spans']:
        field=proposed['field'];old=[x for x in spans['spans']if x['field']==field]
        need(len(old)==1 and proposed['question']==old[0]['question']
             and proposed['actual_answer_inner_html']==old[0]['before_inner_html']
             and proposed['approved_after_inner_html']==old[0]['after_inner_html'], 'literal original before/approved after only; SYS authors no copy')
        text=current[field];pattern=re.compile(r'<h3>\s*'+re.escape(proposed['question'])+r'\s*</h3>\s*<p>([\s\S]*?)</p>')
        found=list(pattern.finditer(text));need(len(found)==1 and text.count(proposed['question'])==1,'one unique original h3-followed-p answer required')
        begin,end=found[0].span(1);need(text[begin:end]==proposed['actual_answer_inner_html']
            and [begin,end]==proposed['current_answer_offsets'] and digest(text[:begin])==proposed['prefix_utf8_sha256']
            and digest(text[end:])==proposed['suffix_utf8_sha256'] and digest(text)==proposed['current_full_field_sha256'],
            'exact current unique answer and every prefix/suffix byte preserved')
        desired[field]=text[:begin]+proposed['approved_after_inner_html']+text[end:]
        deltas.append({'field':field,'question':proposed['question'],'before':text[begin:end],
                       'after':proposed['approved_after_inner_html'],'offsets':[begin,end],
                       'prefix_sha256':digest(text[:begin]),'suffix_sha256':digest(text[end:])})
    stable=sorted(set(current)-set(fields)-{'updated_at','version'});ms=sorted(k for k in current if k.endswith('_ms'))
    need(len(stable)==source['protection']['stable_business_fields']==25 and len(ms)==source['protection']['MS_fields']==6
         and set(ms)<=set(stable), 'full25 business protection including all6 MS required')
    return fields,desired,deltas,stable,ms


def received_answer_source_context(root, snapshot, item):
    """Current owner custody may register dated answer facts, never an execution target."""
    import department_autonomy as a
    import goal_delivery_runtime as g
    import chief_assistant_coordination as chief
    import result_coordination as rc
    from managed_cms_permit_issuer import TARGETS
    need = a.require
    need(set(item) == {'schema','task_id','owner_input','owner_intake_record_id','original_candidate',
                       'original_transport_source','actual_PUB_completion'}, 'exact original answer source envelope only')
    frozen=a.document(root,snapshot['goal_contract']);goal=g.restore_goal(root,snapshot)['goal_delivery']
    history=chief.ordinary_source_history(root,snapshot['task_id'])
    chief._ordinary_original_task(root,snapshot,frozen,history)
    need(item.get('task_id')==snapshot['task_id'] and snapshot.get('current_state') not in w.TERMINAL_STATES
         and all(goal.get(k)==frozen.get(k)for k in ('primary_owner','producer_departments','authorized_scope',
             'human_authorization','required_execution_actions')), 'unchanged open original answer task/owner/authority required')
    owner=goal['primary_owner'];need(a.professional(root,owner), 'actual original professional owner required')
    rows=[r for r in w._result_handoff_rows(root,snapshot['task_id'])if r.get('event')=='controller_received'
          and r.get('record_id')==item.get('owner_intake_record_id') and r.get('sender_department')==owner]
    need(len(rows)==1,'one actual original owner result intake required')
    intake=rows[0];rc._committed_result(root,intake);box=a.document(root,intake['outbox'])
    input_pin=item['owner_input'];source=a.document(root,input_pin)
    need(input_pin in box.get('evidence',[]) and source.get('task_id')==box.get('task_id')==snapshot['task_id']
         and source.get('original_owner')==owner and source.get('scope')in frozen['authorized_scope']
         and source.get('original_contract')==snapshot['goal_contract']
         and source.get('original_human')==goal['authorization_pin'], 'real committed owner custody of exact source/contract/human/scope')
    original=a.document(root,item['original_candidate']);action_id=source.get('original_required_action')
    actions=[x for x in frozen['required_execution_actions']if x.get('action_id')==action_id]
    targets=[x for x in TARGETS.values()if x.get('task_id')==snapshot['task_id']and x.get('action_id')==action_id]
    need(len(actions)==len(targets)==1 and actions[0].get('action_class')=='cms_write'
         and actions[0].get('department')==source.get('original_CMS_executor')=='publishing'
         and actions[0].get('scope')==source['scope'] and tuple(targets[0].get('source_frozen_candidate',()))==
             (item['original_candidate']['path'],item['original_candidate']['sha256'])
         and original.get('task_id')==snapshot['task_id'] and original.get('action_id')==action_id
         and original.get('scope')==source['scope'], 'one genuine original frozen answer action/candidate; no target registration')
    spans=a.document(root,original['answer_only_span_diff']);need(spans['source_copy']in frozen['existing_results'], 'original approved V7 copy only')
    a.document(root,spans['source_copy']) if not spans['source_copy']['path'].endswith('.md') else need(
        w.file_digest(root,spans['source_copy']['path'])==spans['source_copy'],'original copy bytes unchanged')
    current=a.document(root,source['current_source']);backup=a.document(root,source['current_backup'])
    report=a.document(root,source['actual_PUB_complete_report']);context=a.document(root,report['authenticated_UI_context'])
    need(source['actual_PUB_complete_report']in box['evidence'] and report.get('task_id')==snapshot['task_id']
         and report.get('primary_owner')==owner and report.get('actual_CMS_executor')=='publishing'
         and report.get('current_row')==source['current_source'] and report.get('backup')==source['current_backup']
         and current==backup and source['current_source']['sha256']==source['current_backup']['sha256']
         and current.get('id')==source['target']['id']==original.get('record_id')
         and current.get('slug')==source['target']['slug']==original.get('slug')
         and len(current)==source['target']['field_count']==29 and type(current.get('version'))is int
         and current['version']==source['target']['server_version'] and current['updated_at']==source['target']['raw_server_CAS']
         and w._parse_observed_at(current['updated_at']) is not None
         and context.get('id')==current['id'] and context.get('raw_server_updated_at')==current['updated_at']
         and context.get('server_version')==current['version'] and context.get('field_count')==29
         and context.get('authenticated_admin_UI') is True and context.get('http_status')==200
         and context.get('observed_at_UTC')==source['target']['observed_at_UTC'], 'actual dated authenticated full29/raw CAS/version and exact independent backup')
    fields,desired,deltas,stable,ms=_answer_span_projection(source,current,original,spans)
    # Read actual policy/native effects as source observations. This deliberately
    # does not call record_collaboration_queue or create its missing prior intent.
    import goal_source_recovery as recovery
    transport=a.document(root,item['original_transport_source']);gap=a.document(root,source['own_normal_transport_source_gap'])
    request,prepared,policy,sender,pub=recovery._collaboration_queue_preparation(root,snapshot,
        transport['original_prepare_request'],transport['original_prepare_result'])
    need(request['sender_department']==owner and request['target_department']=='publishing'
         and request['task_id']==snapshot['task_id'] and request['scope']==source['scope'], 'actual original owner-to-PUB readonly source route')
    intent=a.document(root,transport['actual_queue_intent']);result=a.document(root,transport['actual_queue_result'])
    expected={'thread_id':pub['thread_id'],'payload_sha256':request['payload_sha256'],'policy_decision_id':policy['decision_id']}
    need(all(intent.get(k)==v and result.get(k)==v for k,v in expected.items())
         and all(result.get(k)==v for k,v in intent.items()) and result.get('exit_code')==0 and not result.get('stderr')
         and result.get('stdout')==f"Queued message {transport['queue_message_id']} for thread {pub['thread_id']}.\n"
         and gap.get('actual_message_id')==transport['queue_message_id'] and gap.get('actual_send')==result,
         'exact original policy/key/queue effect and preserved gap, not a reconstructed durable normal intent')
    selected=a.document(root,transport['actual_native_invocation']);call=selected.get('actual_command',{});turn=selected.get('turn',{})
    need(transport['actual_native_invocation']in box['evidence'] and selected.get('thread',{}).get('id')==sender['task_id']
         and selected['thread'].get('cwd')==str(Path(root).resolve()) and call.get('id')==transport['queue_command_id']
         and call.get('type')=='commandExecution' and call.get('status')=='completed' and call.get('exitCode')==0
         and call.get('cwd')==str(Path(root).resolve()) and 'OfficialQueueTransport'in call.get('command','')
         and '.enqueue(prepared)'in call['command'] and 'queue-collaboration'not in call['command'],
         'genuine selected native CLI invocation kept as CLI, never relabeled MCP or normal queue command')
    output=json.loads(w._completion_execution_output(call))
    need(all(output.get(k)==v for k,v in {'state':'accepted','message_id':transport['queue_message_id'],
         'target_thread_id':pub['thread_id'],'payload_sha256':request['payload_sha256'],'policy':policy['decision_id'],
         'task_id':snapshot['task_id'],'action_id':request['action_id'],'actual_received':False,'new_production_permission':False}.items()),
         'actual native call output must match the original immutable queue result')
    completed=g._collaboration_native(root,item['actual_PUB_completion']);binding=w.department_registry(root)['publishing']['chat_binding']
    need(item['actual_PUB_completion']in box['evidence'] and all(completed.get('thread',{}).get(k)==binding[v]for k,v in
         {'id':'task_id','title':'title','cwd':'cwd','hostId':'host_id'}.items()),'actual current PUB completion, no retired alias')
    turns=[t for t in completed.get('turns',[])if t.get('id')==gap.get('actual_PUB_turn_id')]
    need(len(turns)==1 and turns[0].get('status')=='completed' and not turns[0].get('error'), 'actual PUB completed turn required')
    pt=turns[0];users=[m for m in pt.get('items',[])if m.get('type')=='userMessage'];acks=[m for m in pt.get('items',[])if m.get('id')==gap.get('actual_PUB_ACK_message_id')and m.get('type')=='agentMessage'and m.get('text','').strip()]
    need(len(users)==len(acks)==1 and ''.join(x.get('text','')for x in users[0].get('content',[])if x.get('type')=='text').encode()==w.safe_path(root,request['payload']['path']).read_bytes(),
         'actual PUB user UTF8 and nonempty original ACK required')
    start=w._parse_observed_at(result.get('started_at'));finish=w._parse_observed_at(result.get('finished_at'));checked=w._parse_observed_at(policy.get('checked_at'));observed=w._parse_observed_at(context['observed_at_UTC'])
    need(start and finish and checked and observed and checked<=start<=finish and (start-checked).total_seconds()<=300
         and turn.get('startedAt',float('inf'))<=start.timestamp() and finish.timestamp()<=pt.get('startedAt',0)
         and pt['startedAt']<=observed.timestamp()<=pt.get('completedAt',0), 'real policy/send/recipient/read/complete chronology; old source never made fresh')
    action={'task_id':snapshot['task_id'],'action_id':action_id,'action_class':'cms_write','scope':source['scope'],
            'candidate_version':original['candidate_version'],'table':'blog_posts','record_id':current['id'],
            'slug':current['slug'],'changed_fields':fields,'execution_department':'publishing'}
    return {'action':action,'source':input_pin,'owner':owner,'executor':'publishing','channel':'designated-development',
            'business_scope':source['scope'],'source_only':True,'dated_observation':context['observed_at_UTC'],
            'baseline_pin':source['current_source'],'baseline':current,'desired':desired,'answer_only_deltas':deltas,
            'protected_fields':{'stable_business_fields':stable,'MS_fields':ms,'not_written_fields':sorted(set(current)-set(fields))},
            'current_PUB_binding':binding,'owner_intake_record_id':intake['record_id'],
            'transport_facts':{'original_message_id':transport['queue_message_id'],'actual_user_received':True,'actual_nonempty_ACK':True,
                'actual_completed_read':True,'formal_collaboration_PROVEN':False,'missing_original_normal_intent_recreated':False,
                'original_refusal_preserved':source['own_normal_transport_source_gap'],'current_facts_registered_now_not_backdated':True},
            'remote_key_effects':'DATA_MISSING_NOT_ZERO','remote_channel_ready':'NOT_OBSERVED','production_READY':False,
            'CMS_target_registered':False,'actual_platform_permit_issued':False}


def validate(root, snapshot, item):
    from professional_cms_single_field_admission import ADMISSION_SCHEMA, validate_admission
    if item.get('schema') == ADMISSION_SCHEMA:
        return validate_admission(root, snapshot, item)
    if item.get('schema') == ANSWER_SOURCE_SCHEMA:
        return received_answer_source_context(root,snapshot,item)
    if item.get('schema') == INCREMENT_SCHEMA:
        return received_increment_context(root, snapshot, item)
    import department_autonomy as a
    import goal_delivery_runtime as g
    import result_coordination as rc
    need = a.require
    goal = a.participant(root, snapshot, snapshot['goal_delivery']['primary_owner'])
    frozen = a.document(root, snapshot['goal_contract'])
    need(a.autonomous_goal(frozen) and a.current_mode(root)
         and all(goal.get(k) == frozen.get(k) for k in
                 ('primary_owner','parent_task_id','producer_departments','authorized_scope',
                  'human_authorization','required_execution_actions','collaboration_scopes')),
         'unchanged autonomous contract, authority, actions and original participants required')
    need(item.get('schema') == SCHEMA and item.get('task_id') == snapshot['task_id']
         and item.get('goal_contract') == snapshot['goal_contract']
         and item.get('authorization') == goal['authorization_pin'], 'exact source registration contract/task/authority')
    scope = item.get('business_scope'); owner = goal['primary_owner']
    need(scope in frozen['authorized_scope'], 'original business scope required')
    criterion = [x for x in goal['completion_requirements'] if x.get('requirement_id') == item.get('requirement_id')]
    need(len(criterion) == 1 and criterion[0]['producer_department'] == owner
         and criterion[0]['scope'] == scope, 'original owner criterion required')
    identity = rc.exact_identity(item.get('owner_result_identity', {}))
    need(identity['task_id'] == snapshot['task_id'] and identity['sender_department'] == owner,
         'original professional business result identity required')
    rows = w._result_handoff_rows(root, snapshot['task_id'])
    queued = [r for r in rows if r.get('event') == 'notification_queued'
              and w._result_identity(r) == tuple(identity[k] for k in rc.IDENTITY_FIELDS[1:])]
    need(len(queued) == 1 and queued[0].get('target_department') == 'operations', 'unique original HQ knowledge source required')
    q = queued[0]; a.native_result(root, q, w.department_registry(root)[owner]['chat_binding']['task_id'])
    intake = rc._received_delivery(root, identity, {'target_department':'operations'})
    need(intake and intake['record_id'] == item.get('owner_result_received_record_id'),
         'real committed SQL/native original result intake required')
    report = a.document(root, q['outbox']); pin = item.get('owner_source'); source = a.document(root, pin)
    need(pin in report.get('evidence', []) and report.get('exact_CMS_business_execution_source') == pin
         and report.get('primary_owner') == owner and report.get('scope') == scope,
         'actual full professional report must bind this exact execution source')
    need(source.get('task_id') == snapshot['task_id'] and source.get('scope') == scope
         and source.get('primary_owner') == source.get('department') == owner
         and source.get('goal_contract') == snapshot['goal_contract']
         and source.get('human_authorization') == goal['authorization_pin']
         and source.get('original_requirement') == frozen['completion_criteria'][criterion[0]['criterion_index']],
         'unchanged original owner source/criterion/scope/authorization required')
    native = g._native_document(root, item.get('owner_native'))
    fixed = w.department_registry(root)[owner]['chat_binding']
    need(all(native.get('thread',{}).get(k) == fixed[v] for k,v in
             {'id':'task_id','title':'title','cwd':'cwd'}.items()) and fixed['project_id'] == a.PROJECT,
         'actual fixed same-project professional source required')
    calls = [(t,m) for t in native.get('turns',[]) for m in t.get('items',[])
             if m.get('id') == item.get('source_command_id')]
    need(len(calls) == 1, 'one actual original source command required')
    turn, call = calls[0]
    need(turn.get('status') == 'completed' and not turn.get('error')
         and call.get('type') == 'commandExecution' and call.get('status') == 'completed'
         and call.get('exitCode') == 0 and Path(call.get('cwd','')).resolve() == Path(root).resolve(),
         'successful completed original owner source command required')
    output = json.loads(w._completion_execution_output(call))
    need(output.get('exact_source') == pin, 'native output must identify the exact immutable source bytes')
    decided = w._parse_observed_at(source.get('decided_at_UTC'))
    observed = w._parse_observed_at(q.get('reply_observed_at'))
    ready = [m for m in turn.get('items',[]) if m.get('id') == q.get('source_message_id')]
    need(decided is not None and observed is not None and type(turn.get('completedAt')) in {int,float}
         and turn.get('startedAt',float('inf')) <= decided.timestamp() <= observed.timestamp() <= turn['completedAt']
         and turn.get('id') == q.get('source_turn_id') and len(ready) == 1
         and turn['items'].index(call) < turn['items'].index(ready[0]),
         'real ordered source decision, command, and READY required')
    carrier = a.document(root, source.get('source_carrier'))
    a.document(root,source.get('original_C1_source_input'))
    need(w.file_digest(root,source['original_work_order']['path'])==source['original_work_order'],
         'unchanged original owner work-order text required')
    need(carrier.get('source_contract')==snapshot['goal_contract']
         and carrier.get('source_human_authorization')==goal['authorization_pin'],
         'carrier retains original frozen contract and human source')
    proposed = carrier['proposed_exact_tuple']; action = source['exact_CMS_action_requested']
    need(all(action.get(k) == v for k,v in proposed.items())
         and action.get('business_scope') == scope == proposed.get('business_policy_scope')
         and action.get('original_professional_owner') == owner
         and action.get('action_class') == 'cms_write'
         and action.get('action_id') == 'publish-' + action.get('candidate_version',''),
         'exact original carrier action/version/owner/business scope required')
    fields = action.get('changed_fields',[])
    need(isinstance(fields,list) and 0 < len(fields) <= 8 and fields == sorted(set(fields))
         and all(re.fullmatch(r'content_(en|zh|ms)', x) for x in fields)
         and re.fullmatch(r'[a-z][a-z0-9_]*', action.get('table',''))
         and re.fullmatch(r'[0-9a-f-]{36}',action.get('record_id','')),
         'bounded existing content fields and exact record required')
    physical = 'company.example:' + action['table'] + ':' + action['record_id'] + ':' + ','.join(fields)
    need(action.get('scope') == action.get('physical_target_scope') == physical,
         'explicit original business to physical scope mapping required')
    proposal = a.document(root, source.get('original_PUB_proposal'))
    baseline = a.document(root, source['original_source_baseline_only']['complete_row'])
    before = {k:baseline[k] for k in fields}; desired = source['exact_two_field_desired_values']
    need(source.get('original_PUB_proposal') == carrier['source_proposal']
         and source.get('original_C1_source_input') == carrier['source_input']
         and proposal.get('task_id') == snapshot['task_id'] and proposal.get('scope') == scope
         and proposal.get('table') == action['table'] and proposal.get('id') == action['record_id']
         and proposal.get('slug') == action['slug'] and sorted(proposal.get('fields',[])) == fields
         and desired == proposal.get('after') == carrier['exact_forward_values']
         and before == proposal.get('before') and source['original_source_baseline_only'] == carrier['source_baseline_only'],
         'original before/desired field source and unchanged baseline carrier required')
    need(w.sha256_value(before) == source['original_source_baseline_only']['before_fields_sha256']
         and w.sha256_value(desired) == source['original_source_baseline_only']['desired_fields_sha256'],
         'exact business before/desired field digests required')
    protected = source['protected_fields']
    need(protected == carrier['protected_fields'] and set(protected['not_written_fields']) == set(baseline)-set(fields)
         and set(protected['server_CAS_metadata']) == {'updated_at','version'}
         and set(protected['stable_business_readback_fields']) == set(baseline)-set(fields)-{'updated_at','version'},
         'all other business fields/MS and server-owned CAS must remain protected')
    reverse = source['restore_only_own_two_field_delta']; original_reverse = carrier['reverse_carrier']
    need(reverse == original_reverse and reverse.get('restore_only_original_two_fields') == before
         and reverse.get('scope') == physical and reverse.get('requiresParentRun') is True
         and reverse.get('action_id') == 'rollback-' + action['candidate_version']
         and reverse.get('candidate_version') == action['candidate_version'] + '-rollback-v1'
         and all(reverse.get(k) is None for k in ('parentPermitId','parentRunId','saved_updated_at','current_post_Save_complete_row')),
         'conditional own-parent inverse only; no invented run or post-Save CAS')
    executor = source['original_PUB_executor']; channel = source['original_channel_owner']; role = executor['department']
    need(role == action['execution_department'] and a.professional(root,role) and role != owner,
         'actual original professional CMS executor required')
    binding = w.department_registry(root)[role]['chat_binding']
    need(all(executor.get(k) == binding.get(v) for k,v in
             {'thread_id':'task_id','title':'title','project_id':'project_id','cwd':'cwd'}.items())
         and binding['project_id'] == a.PROJECT and Path(binding['cwd']).resolve() == Path(root).resolve(),
         'exact original PUB identity/project/directory required')
    current_channel = w.read_json(Path(root)/'data/department-registry.json')['collaboration_bindings'].get(channel['department'])
    need(current_channel and all(channel['binding'].get(k) == current_channel.get(k) for k in
         ('thread_id','title','project_id','cwd','host_id')), 'original external channel identity required')
    need(not w.validate_workflow_events(root,snapshot['task_id']), 'intact append-only original workflow required')
    return {'action':action,'source':pin,'owner':owner,'business_scope':scope,'executor':role,
            'channel':channel['department'],'carrier':source['source_carrier'],'desired':desired,'before':before,
            'protected_fields':protected,'owner_result':q['outbox'],'actual_HQ_intake':intake['record_id']}

def records(root, snapshot):
    from professional_cms_single_field_admission import base_source_validation_active
    if base_source_validation_active():return _records_uncached(root, snapshot)
    # Authenticated historical source bindings only. The operator request,
    # current effects/CAS, policy and single-use state are outside this memo.
    context=w._VALIDATION_CONTEXT.get()
    if context is None:return _records_uncached(root,snapshot)
    cache=getattr(context,'_professional_cms_binding_proofs',{})
    key=(str(Path(root).resolve()),w.sha256_value(snapshot));cached=cache.get(key)
    if cached is not None:
        for path,version in cached['dependencies'].items():
            context.bytes(path)
            if context.files[path]['version']!=version:cached=None;break
        if cached is not None:return deepcopy(cached['value'])
    value=_records_uncached(root,snapshot)
    cache[key]={'value':deepcopy(value),'dependencies':{p:x['version']for p,x in context.files.items()}}
    context._professional_cms_binding_proofs=cache
    return value

def _records_uncached(root, snapshot):
    import department_autonomy as a
    rows = [e for e in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS,where=({'task_id':snapshot['task_id']} if 'task_id' in snapshot else None))
            if e.get('task_id') == snapshot['task_id'] and EVENT in e.get('details',{})]
    result=[]; seen=set()
    for row in rows:
        pin=row['details'][EVENT]; item=a.document(root,pin)
        from professional_cms_single_field_admission import ADMISSION_SCHEMA, base_source_validation_active
        if item.get('schema')==ADMISSION_SCHEMA and base_source_validation_active():continue
        from professional_cms_integration import SCHEMA as standing_schema, validate as standing_validate
        if item.get('schema') == 'original-explicit-production-delivery-source/v1':
            from original_production_delivery import contexts as original_contexts
            contexts = [original_contexts(root, snapshot, item)[0]]
        else:
            contexts=(standing_validate(root,snapshot,item)[0] if item.get('schema')==standing_schema
                      else [validate(root,snapshot,item)])
        for context in contexts:
            key=context['action']['action_id'];a.require(key not in seen,'ambiguous execution source registration')
            seen.add(key);result.append({**context,'registration':pin,'event_id':row['event_id']})
    return result

def record(root, task, input_path):
    from professional_cms_single_field_admission import base_source_validation_active
    if base_source_validation_active():raise w.WorkflowError('original base-source validation is read-only')
    import goal_delivery_runtime as g
    import department_autonomy as a
    pin=w.file_digest(root,input_path);item=a.document(root,pin)
    with w.workflow_lock(root):
        snapshot=g.restore_goal(root,w.read_json(w.snapshot_path(root,task)))
        from professional_cms_single_field_admission import ADMISSION_SCHEMA, verify_admission_for_record
        context=(verify_admission_for_record(root,snapshot,item) if item.get('schema')==ADMISSION_SCHEMA
                 else validate(root,snapshot,item))
        existing=[x for x in records(root,snapshot) if x['action']['action_id']==context['action']['action_id']]
        if existing:
            a.require(existing[0]['registration']==pin,'immutable source action already registered to different bytes')
            return {'result':'duplicate_ignored',**existing[0],'external_permission_issued':False,'production_READY':False}
        w.append_workflow_event(root,task,snapshot['current_state'],{EVENT:pin,'frozen_contract_unchanged':True})
    return {'result':'recorded','registration':pin,**context,'external_permission_issued':False,'production_READY':False}

def match(root,snapshot,request):
    if snapshot.get('task_id') == _EN2_FORWARD_TASK and request.get('action_class') == 'cms_write':
        return _en2_execution_context(root, snapshot, request)
    found=[x for x in records(root,snapshot) if request.get('action_id') in {x['action']['action_id'],'rollback-'+x['action']['candidate_version']}]
    if not found:return None
    import department_autonomy as a
    a.require(len(found)==1,'one exact registered execution source required');x=found[0];action=x['action']
    a.require(not x.get('source_only'), 'dated answer source registered only; exact remote/key/executor stages and own new gates still required')
    a.require(request.get('task_id')==snapshot['task_id'] and request.get('department')==x['executor']
              and request.get('sender_department',x['executor'])==x['executor']
              and request.get('action_class')=='cms_write' and request.get('scope') in {x['business_scope'],action['scope']}
              and request.get('authorization_changes',[])==[], 'registered exact task/executor/action/scope; no expansion')
    if x.get('singlefield_forward_admission'):
        a.require(x.get('rollback_allowed') is False and request['action_id']==action['action_id'],
                  'authenticated single-field admission is forward-only; inverse requires independent authority')
    if request['action_id'] != action['action_id']:
        return {**x,'operation':'rollback','action':{**action,'action_id':request['action_id'],
                    'candidate_version':action['candidate_version']+'-rollback-v1'},'before':x['desired'],'desired':x['before']}
    return {**x,'operation':'publish'}

def collaboration_scopes(root,snapshot):
    result=list(snapshot.get('goal_delivery',{}).get('collaboration_scopes',[]))
    for x in records(root,snapshot):
        if x.get('source_only'):continue  # Source facts add no collaboration or execution permission.
        if x.get('singlefield_forward_admission'):continue  # Exact HQ/PUB bridge is independently authenticated; never add generic HQ/WEB authority.
        for role in (x['executor'],x['channel']):
            declaration={'sender_department':x.get('message_owner',x['owner']),'target_department':role,'scope':x['business_scope']}
            if declaration not in result:result.append(declaration)
    return result

def validate_message(root,snapshot,action):
    """An appended collaborator receives this exact binding, not general authority."""
    import department_autonomy as a
    pin=action.get('professional_execution_source')
    if action.get('execution_tuples'):
        from professional_cms_integration import message_context
        context=message_context(root,snapshot,action)
        a.require(context is not None,'normal exact standing integration message required')
        return context
    found=[x for x in records(root,snapshot) if x['registration']==pin]
    a.require(len(found)==1, 'exact appended execution source required for this collaborator')
    x=found[0]
    a.require(not x.get('source_only'), 'dated answer source is not a new collaboration authorization')
    a.require(action.get('task_id')==snapshot['task_id'] and action.get('sender_department')==x['owner']
              and action.get('target_department') in {x['executor'],x['channel']}
              and action.get('scope')==x['business_scope'] and action.get('action_class')=='thread_message'
              and action.get('execution_tuple')==x['action'], 'original owner and exact execution tuple/collaborator required')
    payload=action.get('payload');a.require(w.file_digest(root,payload.get('path',''))==payload,
                                           'exact collaboration payload required')
    text=w.safe_path(root,payload['path']).read_text()
    a.require(all(value in text for value in (snapshot['task_id'],x['business_scope'],x['source']['path'],
                  x['source']['sha256'],x['action']['action_id'],x['action']['scope'])),
              'collaboration body must retain original task/business source/action/physical tuple')
    return x

_EN2_FORWARD_TASK = 'fc-20261011-english-kitchen-actual-publication-goal-v1'
_EN2_SOURCE_EVENT = '698ae455-16d7-4ad1-8744-ebfc8fd763e1'
_EN2_NAMESPACE = 'english-kitchen-en2-exact-v1'


def _en2_forward_source(root, snapshot):
    """Authenticate the existing body source without making it executable."""
    import department_autonomy as a
    from professional_cms_channel import original_body_records
    a.require(snapshot.get('task_id') == _EN2_FORWARD_TASK
              and snapshot.get('current_state') not in w.TERMINAL_STATES | {'paused', 'suspended'},
              'active original EN2 goal required; pause and terminal history cannot resume')
    rows = original_body_records(root, _EN2_FORWARD_TASK)
    a.require(len(rows) == 1, 'one authenticated original EN2 source required')
    source = rows[0]
    targets = source.get('registered_protected_body_targets', {})
    a.require(source.get('event_id') == _EN2_SOURCE_EVENT
              and source.get('task') == _EN2_FORWARD_TASK and source.get('owner') == 'publishing'
              and source.get('protected_body_source_custody') is True
              and set(targets) == {_EN2_NAMESPACE}, 'exact existing EN2 source and owner required')
    target = targets[_EN2_NAMESPACE]
    from professional_cms_issuer import _en2_source_observation
    # Reuse the installed full41/protect37/MS11/no-inverse source validator.
    _en2_source_observation(_EN2_FORWARD_TASK, source, _EN2_NAMESPACE, target)
    binding = w.department_registry(root)['publishing']['chat_binding']
    a.require(binding.get('task_id') == source['original_PUB_tuples'][_EN2_NAMESPACE]['execution_thread_id']
              and binding.get('project_id') == a.PROJECT
              and Path(binding.get('cwd', '')).resolve() == Path(root).resolve(),
              'current original PUB binding required; retired assistant is not executor')
    return source, target


def _en2_native_json(root, document):
    """Reuse the native original-executor reader; labels alone are not proof."""
    import department_autonomy as a
    a.require(isinstance(document.get('actual_native'), dict)
              and isinstance(document.get('command_id'), str) and document['command_id'],
              'EN2 missing original PUB native pin or command ID')
    turn, call, raw = a.native_execution(root, document.get('actual_native'),
                                        document.get('command_id'), 'publishing')
    try:
        value = json.loads(raw)
    except (ValueError, TypeError) as exc:
        raise w.WorkflowError('EN2 requires complete original PUB native JSON output') from exc
    a.require(isinstance(value, dict), 'EN2 original PUB native output must be an object')
    return turn, call, value


def _en2_forward_request(root, snapshot, pin, *, checked_source=None):
    """Validate a forward zero-write preflight, never an execution/issuer grant.

    The existing request/facts/self_check/backup envelope is retained. Native
    preview.response is the existing content-publish dry-run response, not a
    new endpoint or a caller-created production receipt. No inverse is admitted.
    """
    import datetime as dt
    import department_autonomy as a
    source, target = _en2_forward_source(root, snapshot) if checked_source is None else checked_source
    req = a.document(root, pin)
    expected = {'task_id': _EN2_FORWARD_TASK, 'department': 'publishing',
                'action_id': target['actionId'], 'action_class': 'cms_write',
                'source_project_id': a.PROJECT, 'operation': 'field_patch',
                'business_scope': source['scope'], 'physical_scope': target['scope'],
                'table': target['table'], 'slug': target['slug'],
                'object_ids': [target['id']], 'changed_fields': target['changedFields'],
                'candidate_version': target['candidateVersion'],
                'professional_execution_source': source['registration']}
    a.require(all(req.get(k) == v for k, v in expected.items())
              and req.get('scope') in {source['scope'], target['scope']}
              and req.get('sender_department', 'publishing') == 'publishing'
              and req.get('target_department', 'publishing') == 'publishing'
              and req.get('authorization_changes', []) == [] and req.get('rollback') is None,
              'exact EN2 forward task/PUB/recipient/row/source/fields only; no inverse or authority expansion')
    fields = target['changedFields']
    before = a.document(root, req.get('before'))
    a.require(set(before) == set(target['baselineProjectionFields'])
              and len(before) == 41 and before.get('id') == target['id']
              and before.get('slug') == target['slug'] and type(before.get('version')) is int
              and before['version'] >= 0 and isinstance(before.get('updated_at'), str)
              and w.sha256_value(before) == target['baselineFieldsSha256']
              and w.sha256_value({k: before[k] for k in target['retainedProjectionFields']}) == target['retainedFieldsSha256']
              and req.get('expected_updated_at') == before['updated_at']
              and req.get('expected_version') == before['version'],
              'EN2 authenticated full41/protect37/MS11 baseline and raw server CAS/version required')
    desired = req.get('desired')
    a.require(isinstance(desired, dict) and set(desired) == set(fields)
              and w.sha256_value(desired) == target['desiredFieldsSha256'],
              'only the original two English desired fields may differ')
    facts = a.document(root, req.get('facts'))
    a.require(isinstance(facts.get('protected_preview'), dict)
              and isinstance(req.get('self_check'), dict) and isinstance(req.get('backup'), dict),
              'EN2 missing original PUB protected_preview/self_check/backup; readonly facts are not a preflight')
    check = a.document(root, req['self_check'])
    backup = a.document(root, req['backup'])
    intent = w.sha256_value({k: v for k, v in req.items()
                             if k not in {'facts', 'self_check', 'backup', 'rollback'}})
    identity = ('task_id', 'department', 'action_id', 'action_class', 'scope')
    a.require(all(all(doc.get(k) == req[k] for k in identity)
                  and doc.get('intent_sha256') == intent for doc in (facts, check, backup))
              and facts.get('current_row') == backup.get('complete_row') == req['before']
              and check.get('status') == 'PASS' and check.get('production_write_allowed') is False,
              'request-bound real PUB facts/selfcheck/full backup required')
    observed = w._parse_observed_at(facts.get('observed_at'))
    now = dt.datetime.now(dt.timezone.utc)
    a.require(observed is not None and 0 <= (now - observed).total_seconds() <= 300,
              'EN2 PUB observation expired or future; obtain a fresh original row/preview, do not relabel time')
    preview = a.document(root, facts['protected_preview'])
    preview_request, response = preview.get('request', {}), preview.get('response', {})
    candidate = {'taskId': _EN2_FORWARD_TASK, 'actionId': target['actionId'],
                 'operation': 'publish', 'scope': target['scope'],
                 'candidateVersion': target['candidateVersion']}
    a.require(preview_request == {'contentType': 'service', 'mode': 'dry-run',
                  'record': {**before, **desired}, 'nextStatus': 'published',
                  'expectedUpdatedAt': before['updated_at'], 'managedCandidate': candidate}
              and type(preview.get('http_status')) is int and preview['http_status'] == 200
              and preview.get('url') == 'https://exampleproject000000.supabase.co/functions/v1/content-publish'
              and response.get('ok') is True and response.get('dry_run') is True
              and response.get('performed_write', False) is False
              and response.get('action') in {'publish', 'update'}
              and all(response.get(k) == v for k, v in {'ok': True, 'dry_run': True,
                  'content_type': 'service',
                  'slug': target['slug'], 'existing_id': target['id'], 'status': 'published',
                  'payload_preview': desired}.items()),
              'actual existing protected dry-run request/response only; identity probe or Save is not preview')
    effects = a.document(root, facts.get('original_key_effect_lookup'))
    lookup = {'task_id': _EN2_FORWARD_TASK, 'action_id': target['actionId'],
              'candidate_version': target['candidateVersion'], 'record_id': target['id'],
              'scope': target['scope']}
    a.require(effects.get('lookup_scope') == lookup and effects.get('rows') == []
              and effects.get('unknown_effect') is False and effects.get('same_row_conflict') is False,
              'fresh original-key and same-row effects required; UNKNOWN/active/completed effects cannot replay')
    # All four independently pinned observations must have real PUB commands.
    # No AST-only fixture output is allowed into a production preflight.
    for doc, expected_native in (
        (facts, {**{k: facts[k] for k in identity}, 'intent_sha256': intent,
                 'current_row': req['before'], 'protected_preview': facts['protected_preview'],
                 'original_key_effect_lookup': facts['original_key_effect_lookup'],
                 'observed_at': facts['observed_at']}),
        (check, {**{k: check[k] for k in identity}, 'intent_sha256': intent,
                 'status': 'PASS', 'production_write_allowed': False}),
        (preview, {'request': preview_request, 'response': response,
                   'url': preview['url'], 'http_status': preview['http_status']}),
        (effects, {'lookup_scope': lookup, 'rows': [], 'unknown_effect': False,
                   'same_row_conflict': False}),
    ):
        turn, call, native = _en2_native_json(root, doc)
        a.require(all(native.get(k) == v for k, v in expected_native.items()),
                  'original PUB native output must bind exact EN2 evidence; caller PASS is insufficient')
        start, end = turn.get('startedAt'), turn.get('completedAt')
        a.require(type(start) in {int, float} and start <= observed.timestamp() <= now.timestamp()
                  and (end is None or type(end) in {int, float} and observed.timestamp() <= end),
                  'EN2 observation must belong to the real PUB native turn')
    return {'source_only': True, 'preflight_only': True, 'operation': 'publish',
            'external_origin_state': 'NOT_VERIFIED',
            'structural_validation_only': True,
            'registration': source['registration'], 'source_event_id': source['event_id'],
            'action': {'action_id': target['actionId'], 'candidate_version': target['candidateVersion']},
            'request': req, 'pin': pin, 'department': 'publishing',
            'actual_action_allowed': False, 'external_permission_issued': False,
            'production_READY': False}


def _en2_verify_provider_origins(root, structural, references):
    """Re-fetch both providers; identifiers only locate evidence, never grant it."""
    import datetime as dt
    import department_autonomy as a
    from en2_supabase_origin import read_actual as read_supabase
    from en2_preview_origin import read_actual as read_preview
    names={'turn_id','row_call','key_call','same_row_call','preview_run_id'}
    a.require(isinstance(references,dict) and set(references)==names
              and all(isinstance(references.get(k),str) and references[k] for k in names-{'preview_run_id'})
              and type(references.get('preview_run_id')) is int and references['preview_run_id']>0,
              'DATA_MISSING: original PUB turn/row/key/same-row calls and existing protected preview run required; command-printed JSON cannot register')
    req=structural['request'];facts=a.document(root,req['facts']);before=a.document(root,req['before'])
    sql=read_supabase(root,references['turn_id'],references['row_call'],references['key_call'],
                      references['same_row_call'],live_publisher=True)
    a.require(sql.get('row_call_origin')=='VERIFIED_OFFICIAL_RPC'
              and sql.get('original_key_call_origin')=='VERIFIED_OFFICIAL_RPC'
              and sql.get('same_row_call_origin')=='VERIFIED_OFFICIAL_RPC'
              and sql.get('same_row_effect')=='NO_BLOCKING_ROW_OBSERVED'
              and sql.get('original_key_count')==0 and sql.get('fresh_within_300_seconds') is True
              and sql.get('task_id')==req['task_id'] and sql.get('record_id')==req['object_ids'][0]
              and sql.get('raw_updated_at')==req['expected_updated_at']
              and sql.get('version')==req['expected_version']
              and sql.get('row_sha256')==w.sha256_value(before)
              and w._parse_observed_at(sql.get('server_observed_at'))==w._parse_observed_at(facts.get('observed_at')),
              'fresh official PUB row, original key and complete same-row effects must bind exact request')
    preview=read_preview(root,references['preview_run_id'])
    a.require(preview.get('preview_origin')=='VERIFIED_GITHUB_PROVIDER_READ'
              and preview.get('run_id')==references['preview_run_id']
              and preview.get('task_id')==req['task_id'] and preview.get('action_id')==req['action_id']
              and preview.get('candidate_version')==req['candidate_version']
              and preview.get('physical_scope')==req['physical_scope']
              and preview.get('expected_updated_at')==req['expected_updated_at']
              and preview.get('desired_fields_sha256')==w.sha256_value(req['desired'])
              and preview.get('actual_action_allowed') is False,
              'actual protected GitHub preview must bind the original exact forward tuple and payload')
    observed=w._parse_observed_at(sql['server_observed_at']);checked=w._parse_observed_at(preview.get('receipt_checked_at'))
    now=dt.datetime.now(dt.timezone.utc);same_ms=sql.get('same_row_completed_at_ms')
    # The protected preview already authenticates the entire baseline and its
    # CAS. The publisher can re-read that identical baseline after the preview.
    # Do not admit a query sequence straddling the preview receipt.
    a.require(observed is not None and checked is not None and type(same_ms) is int
              and int(observed.timestamp()*1000)<=same_ms<=int(now.timestamp()*1000)
              and (same_ms<=int(checked.timestamp()*1000) or observed>=checked)
              and 0<=(now-observed).total_seconds()<=300 and 0<=(now-checked).total_seconds()<=300,
              'fresh identical baseline queries and protected preview must be fully ordered; no TTL extension')
    return {'external_origin_state':'VERIFIED_PROTECTED_PROVIDER_RECEIPTS',
            'source_event_id':structural['source_event_id'],'pub_turn_id':references['turn_id'],
            'row_call':references['row_call'],'key_call':references['key_call'],'same_row_call':references['same_row_call'],
            'server_observed_at':sql['server_observed_at'],'preview_run_id':preview['run_id'],
            'preview_artifact_id':preview['artifact_id'],'preview_receipt_checked_at':preview['receipt_checked_at'],
            'actual_action_allowed':False,'external_permission_issued':False}


def _record_en2_forward_preflight(root, task, input_path):
    """The existing workflow journal/lock owns deduplication; no second ledger."""
    import department_autonomy as a
    import goal_delivery_runtime as g
    with w.workflow_lock(root), w.request_validation_context() as validation:
        item = a.document(root, w.file_digest(root, input_path))
        a.require(item.get('schema') == 'professional-cms-fresh-preflight/v1'
                  and item.get('task_id') == task == _EN2_FORWARD_TASK,
                  'normal exact EN2 preflight envelope required')
        request_pin = item.get('request')
        req = a.document(root, request_pin)
        prior = [e['details']['professional_cms_preflight']
                 for e in w.read_jsonl(Path(root) / w.WORKFLOW_EVENTS)
                 if e.get('task_id') == task and e.get('details', {}).get(
                     'professional_cms_preflight', {}).get('action_id') == req.get('action_id')]
        # An uncertain retry first reads the exact original local receipt. This
        # reports only its existence; it cannot extend CAS freshness or execute.
        if any(row.get('request') == request_pin and row.get('preflight_only') is True
               and row.get('source_event_id') == _EN2_SOURCE_EVENT
               and row.get('external_origin_state') == 'VERIFIED_PROTECTED_PROVIDER_RECEIPTS' for row in prior):
            validation.recheck()
            return {'result': 'duplicate_ignored', 'preflight_only': True,
                    'external_permission_issued': False, 'actual_action_allowed': False,
                    'requires_fresh_validation_for_execution': True, 'replay_authorized': False}
        snapshot = g.restore_goal(root, w.read_json(w.snapshot_path(root, task)))
        x = _en2_forward_request(root, snapshot, request_pin)
        # Source IDs only locate the official history and GitHub run; the
        # two providers are reread and validated here, never caller labels.
        if x.get('external_origin_state') != 'VERIFIED_PROTECTED_PROVIDER_RECEIPTS':
            origins = _en2_verify_provider_origins(root, x, item.get('provider_sources'))
            x = {**x, **origins}
        a.require(x.get('external_origin_state') == 'VERIFIED_PROTECTED_PROVIDER_RECEIPTS',
                  'EN2 protected preview/effects origin NOT_VERIFIED')
        validation.recheck()
        w.append_workflow_event(root, task, snapshot['current_state'], {
            'professional_cms_preflight': {'action_id': x['action']['action_id'],
                'request': x['pin'], 'source_registration': x['registration'],
                'source_event_id': x['source_event_id'], 'preflight_only': True,
                'preflight_envelope': w.file_digest(root, input_path),
                'provider_origin_evidence': {k: x.get(k) for k in (
                    'pub_turn_id','row_call','key_call','same_row_call','server_observed_at',
                    'preview_run_id','preview_artifact_id','preview_receipt_checked_at')},
                'external_origin_state': x['external_origin_state'],
                'actual_action_allowed': False}})
    return {'result': 'recorded', 'request': x['pin'], 'preflight_only': True,
            'external_permission_issued': False, 'actual_action_allowed': False}



def en2_current_forward_evidence(root, snapshot):
    """Revalidate the latest committed original PUB preflight; no policy/permit.

    Returns an evidence view only. This is deliberately not execution_context
    or an issuer target and cannot override source-only/no-inverse guards.
    """
    import department_autonomy as a
    from reviewed_web_release import current as reviewed_current
    a.require(snapshot.get('task_id') == _EN2_FORWARD_TASK
              and snapshot.get('current_state') not in w.TERMINAL_STATES | {'paused','suspended'},
              'active exact original EN2 goal required')
    events=w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS,where={
        'task_id':_EN2_FORWARD_TASK,('details','professional_cms_preflight','preflight_only'):True})
    a.require(events, 'DATA_MISSING: original PUB verified forward preflight is not recorded')
    a.require(not w.validate_workflow_events(root,_EN2_FORWARD_TASK)
              and not w._validate_receipt_chain(root,_EN2_FORWARD_TASK)[1],
              'intact original workflow and receipt histories required')
    event=events[-1];stored=event['details']['professional_cms_preflight']
    a.require(stored.get('source_event_id')==_EN2_SOURCE_EVENT
              and stored.get('external_origin_state')=='VERIFIED_PROTECTED_PROVIDER_RECEIPTS'
              and stored.get('actual_action_allowed') is False,
              'one latest original validation-only provider-verified event required')
    envelope=a.document(root,stored.get('preflight_envelope'))
    a.require(envelope.get('schema')=='professional-cms-fresh-preflight/v1'
              and envelope.get('task_id')==_EN2_FORWARD_TASK
              and envelope.get('request')==stored.get('request'),
              'exact committed original preflight envelope and request required')
    source,target=_en2_forward_source(root,snapshot)
    structural=_en2_forward_request(root,snapshot,stored['request'],checked_source=(source,target))
    a.require(stored.get('action_id')==structural['action']['action_id']
              and stored.get('source_registration')==structural['registration'],
              'exact original action and immutable source required')
    authority=reviewed_current(root,snapshot,source)
    a.require(authority.get('current_owner_reviewed_release') is True
              and authority.get('source_custody_registration')==source['registration']
              and authority.get('task')==_EN2_FORWARD_TASK and authority.get('scope')==source['scope']
              and isinstance(authority.get('authorization'),dict)
              and isinstance(authority.get('decision'),dict),
              'actual original human/HQ current source and exact original custody required')
    verified=_en2_verify_provider_origins(root,structural,envelope.get('provider_sources'))
    keys=('pub_turn_id','row_call','key_call','same_row_call','server_observed_at',
          'preview_run_id','preview_artifact_id','preview_receipt_checked_at')
    a.require(stored.get('provider_origin_evidence')=={k:verified.get(k) for k in keys},
              'current independently reread providers must match committed evidence')
    return {'result':'ORIGINAL_FORWARD_EVIDENCE_REVALIDATED_ONLY',
            'task_id':_EN2_FORWARD_TASK,'action_id':structural['action']['action_id'],
            'request':structural['pin'],'preflight_event_id':event['event_id'],
            'source_event_id':source['event_id'],'human_source':authority['authorization'],
            'HQ_decision':authority['decision'],'external_origin_state':verified['external_origin_state'],
            'actual_action_allowed':False,'external_permission_issued':False,
            'execution_binding_available':False,'issuer_binding_available':False}


def _request(root,snapshot,pin):
    """Fresh PUB evidence binds the immutable source, never the old readonly grant."""
    import department_autonomy as a
    import goal_delivery_runtime as g
    if snapshot.get('task_id') == _EN2_FORWARD_TASK:
        return _en2_forward_request(root, snapshot, pin)
    req=a.document(root,pin);x=match(root,snapshot,req);a.require(x is not None,'registered CMS source required')
    if x.get('singlefield_forward_admission'):
        from professional_cms_single_field_admission import validate_execution_request
        return validate_execution_request(root, snapshot, pin)
    action=x['action'];fields=action['changed_fields']
    a.require(req.get('professional_execution_source')==x['registration']
              and req.get('source_project_id')==a.PROJECT
              and req.get('operation')==('field_patch_rollback'if x['operation']=='rollback'else'field_patch') and req.get('object_ids')==[action['record_id']]
              and req.get('table')==action['table'] and req.get('slug')==action['slug']
              and req.get('business_scope')==x['business_scope'] and req.get('physical_scope')==action['scope']
              and req.get('changed_fields')==fields and req.get('desired')==x['desired'],
              'only the registered exact row/content fields/desired effect and both scopes may execute')
    before=a.document(root,req.get('before'));a.require(set(before)==set(x['protected_fields']['not_written_fields'])|set(fields)
              and all(before.get(k)==v for k,v in x['before'].items())
              and before.get('id')==action['record_id']
              and before.get('page_key' if action['table']=='cms_pages' else 'slug')==action['slug']
              and isinstance(before.get('version'),int) and isinstance(before.get('updated_at'),str)
              and req.get('expected_updated_at')==before['updated_at'] and req.get('expected_version')==before['version'],
              'fresh complete original row/server CAS and unchanged two before fields required')
    intent=w.sha256_value({k:v for k,v in req.items()if k not in {'facts','self_check','backup','rollback'}})
    docs={}
    for name in ('facts','self_check','backup','rollback'):
        doc=a.document(root,req.get(name));docs[name]=doc
        a.require(all(doc.get(k)==req.get(k)for k in ('task_id','department','action_id','action_class','scope'))
                  and doc.get('intent_sha256')==intent, 'exact request-bound actual '+name+' required')
    a.require(docs['self_check'].get('status')=='PASS' and docs['facts'].get('current_row')==req['before']
              and docs['backup'].get('complete_row')==req['before']
              and docs['facts'].get('protected_preview') and docs['facts'].get('original_key_effect_lookup'),
              'successful PUB selfcheck, full row backup, zero-write preview and original-key lookup required')
    a.document(root,docs['facts']['protected_preview']);a.document(root,docs['facts']['original_key_effect_lookup'])
    inverse=docs['rollback']
    a.require(inverse.get('requires_completed_own_parent') is True
              and inverse.get('restore_fields')==x['before'] and inverse.get('server_CAS_fields_not_written')==['updated_at','version']
              and inverse.get('requires_fresh_post_Save_CAS') is True and inverse.get('requires_new_single_use_inverse_permit') is True,
              'own exact two-field inverse and future actual parent/post-Save CAS required')
    actions=[v for v in snapshot['goal_delivery'].get('approved_actions',[])if v.get('target_department')==x['executor']
             and v.get('professional_execution_source')==x['registration']]
    received={s.get('action_id')for s in g._collaboration_wait_states(root,snapshot)
              if (s.get('status'),s.get('proof_state')) in {('message_received','RECEIVED'),('result_received','PROVEN')}}
    a.require(any(v['action_id']in received for v in actions), 'original PUB must actually receive this precise execution collaboration; old readonly receipt is insufficient')
    a.require(a.sensitive_state(root,snapshot,req)['state']=='within_original_authorization','sensitive expansion is not this source')
    if req.get('execution_instance') is not None:
        from professional_cms_pre_main_recovery import instance
        instance(root,req)
    return {**x,'request':req,'pin':pin,'authorization':snapshot['goal_delivery']['authorization_pin'],
            'department':x['executor'],'preflight':{**{k:req[k]for k in ('task_id','department','action_id','action_class','scope','facts','self_check','backup','rollback')},
            'risk_level':'R2','request':pin,'source_registration':x['registration']}}

def record_preflight(root,task,input_path):
    from professional_cms_single_field_admission import base_source_validation_active
    if base_source_validation_active():raise w.WorkflowError('original base-source validation is read-only')
    if task == _EN2_FORWARD_TASK:
        return _record_en2_forward_preflight(root, task, input_path)
    import department_autonomy as a
    import goal_delivery_runtime as g
    item=a.document(root,w.file_digest(root,input_path))
    with w.workflow_lock(root):
        snapshot=g.restore_goal(root,w.read_json(w.snapshot_path(root,task)));x=_request(root,snapshot,item.get('request'))
        a.require(item.get('schema')=='professional-cms-fresh-preflight/v1' and item.get('task_id')==task,
                  'normal fresh PUB preflight envelope required')
        prior=[e['details']['professional_cms_preflight']for e in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS)
               if e.get('task_id')==task and e.get('details',{}).get('professional_cms_preflight',{}).get('action_id')==x['action']['action_id']]
        if prior and prior[-1]['request']==x['pin']:return {'result':'duplicate_ignored','external_permission_issued':False}
        w.append_workflow_event(root,task,snapshot['current_state'],{'professional_cms_preflight':{'action_id':x['action']['action_id'],'request':x['pin'],'source_registration':x['registration']}})
    return {'result':'recorded','request':x['pin'],'external_permission_issued':False,'actual_action_allowed':False}

def _en2_execution_context(root, snapshot, requested, *, verified_input=None):
    """Original exact PUB action after a current independent evidence recheck.

    This produces only the input for the existing ordinary policy. It never
    issues a permit, changes the frozen source, or enables an inverse action.
    """
    import department_autonomy as a
    import datetime as dt
    a.require(requested.get('task_id')==_EN2_FORWARD_TASK and requested.get('department')=='publishing'
              and requested.get('action_class')=='cms_write',
              'exact original EN2 publishing action required')
    a.require(a.effective_mode(root,snapshot) and snapshot.get('task_id')==_EN2_FORWARD_TASK
              and snapshot.get('current_state') not in w.TERMINAL_STATES | {'paused','suspended'},
              'active original EN2 goal and current authorized delivery mode required')
    evidence=(en2_current_forward_evidence(root,snapshot) if verified_input is None else verified_input)
    req=a.document(root,evidence['request']);facts=a.document(root,req.get('facts'))
    goal=snapshot.get('goal_delivery',{});pin=goal.get('authorization_pin')
    a.require(goal.get('primary_owner')=='publishing' and 'publishing' in goal.get('producer_departments',[])
              and a.professional(root,'publishing')
              and isinstance(pin,dict) and a.document(root,pin) is not None,
              'unchanged original PUB owner and actual original authority required')
    expected={'task_id':_EN2_FORWARD_TASK,'action_id':req.get('action_id'),'action_class':'cms_write',
              'department':'publishing','scope':req.get('business_scope')}
    a.require(all(requested.get(k)==v for k,v in expected.items())
              and requested.get('source_project_id',a.PROJECT)==a.PROJECT
              and requested.get('payload_sha256',evidence['request']['sha256'])==evidence['request']['sha256']
              and req.get('scope')==req.get('business_scope')==requested.get('scope')
              and req.get('action_id')==evidence['action_id'] and req.get('department')=='publishing'
              and requested.get('sender_department','publishing')=='publishing'
              and not requested.get('target_department') and not requested.get('target_project_id')
              and requested.get('authorization_changes',[])==[]
              and req.get('operation')=='field_patch' and req.get('rollback') is None
              and req.get('execution_instance') is None and requested.get('execution_instance') is None,
              'exact original PUB business-scope forward request only; no inverse or borrowed instance')
    facts_at=w._parse_observed_at(facts.get('observed_at'))
    observed=w._parse_observed_at(req.get('observed_at',facts.get('observed_at')))
    now=dt.datetime.now(dt.timezone.utc)
    a.require(observed is not None and facts_at==observed and 0<=(now-observed).total_seconds()<=300,
              'request must preserve the actual fresh PUB observation; no relabel or TTL extension')
    action={k:req[k] for k in ('task_id','department','action_id','action_class','scope')}
    return {'action':action,'operation':'publish','executor':'publishing','department':'publishing',
            'business_scope':req['business_scope'],'request':req,'pin':evidence['request'],
            'authorization':pin,'current_human_source':evidence['human_source'],
            'current_HQ_decision':evidence['HQ_decision'],
            'preflight':{**action,'risk_level':'R2','request':evidence['request'],
                         'facts':req['facts'],'self_check':req['self_check'],'backup':req['backup'],
                         'payload_sha256':w.sha256_value(req['desired'])},
            'preflight_only':True,'external_permission_issued':False}


def execution_context(root,snapshot,requested):
    if snapshot.get('task_id') == _EN2_FORWARD_TASK:
        return _en2_execution_context(root,snapshot,requested)
    import department_autonomy as a
    x=match(root,snapshot,requested)
    if x is None:return None
    rows=[e['details']['professional_cms_preflight']for e in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS)
          if e.get('task_id')==snapshot['task_id'] and e.get('details',{}).get('professional_cms_preflight',{}).get('action_id')==x['action']['action_id']]
    a.require(rows and rows[-1]['source_registration']==x['registration'],
              'source already registered; fresh received original PUB preflight/preview/CAS still required')
    context=_request(root,snapshot,rows[-1]['request'])
    a.require(requested.get('payload_sha256',context['pin']['sha256'])==context['pin']['sha256'], 'current exact PUB request hash required')
    return context

def status(root,task):
    if task == _EN2_FORWARD_TASK:
        import goal_delivery_runtime as g
        with w.request_validation_context():
            snapshot = g.restore_goal(root, w.read_json(w.snapshot_path(root, task)))
            source, target = _en2_forward_source(root, snapshot)
            rows = [e['details']['professional_cms_preflight']
                    for e in w.read_jsonl(Path(root) / w.WORKFLOW_EVENTS)
                    if e.get('task_id') == task and e.get('details', {}).get(
                        'professional_cms_preflight', {}).get('preflight_only') is True]
            return {'task_id': task, 'registered_source': source['registration'],
                    'source_event_id': source['event_id'], 'physical_target': target,
                    'forward_preflight_validator_available': True,
                    'structural_validator_available': True,
                    'current_forward_evidence_reader_implemented': True,
                    'forward_policy_context_implemented': True,
                    'issuer_binding_implemented': True,
                    'issuer_binding_state': ('requires_live_preflight_revalidation' if rows
                                             else 'waiting_for_original_publisher_preflight'),
                    'provider_origin_merge_implemented': True,
                    'provider_origin_merge_live_preview_proven': False,
                    'provider_sources_fields': ['turn_id','row_call','key_call','same_row_call','preview_run_id'],
                    'external_origin_state': 'NOT_VERIFIED',
                    'preflight_input_schema': 'professional-cms-fresh-preflight/v1',
                    'preflight_request': 'existing facts/self_check/backup envelope; no inverse',
                    'recorded_validation_only_preflights': rows,
                    'actual_action_allowed': False, 'actual_platform_permit_issued': False,
                    'production_READY': False, 'baseline_is_current_CAS': False,
                    'execution_binding_available': False, 'pending_issuer_owner': 'publishing',
                    'runtime_loaded': 'NOT_OBSERVED_BY_THIS_READER', 'next_owner': 'publishing',
                    'required': ['fresh original PUB full41/raw CAS/version and complete backup',
                                 'same original PUB turn with official Supabase read-only row/key/same-row results',
                                 'native zero-write protected preview and original-key/same-row effect lookup',
                                 'request-bound real original PUB selfcheck',
                                 'separate normal current issuer/execution binding before any Save']}
    import goal_delivery_runtime as g
    snapshot=g.restore_goal(root,w.read_json(w.snapshot_path(root,task)))
    if not snapshot.get('goal_delivery'):
        from professional_cms_legacy_stage import catalog
        staged=catalog(root,task)
        if not staged:
            raise w.WorkflowError('original legacy task has no current admitted CMS source')
        from professional_cms_legacy_stage import execution_catalog
        current=execution_catalog(root,task)
        return {'task_id':task,'registered_sources':staged,'current_stage_execution_sources':current,'collaboration_scopes':[],
                'source_only':True,'stage_execution_metadata_registered':bool(current),'execution_action_registered':False,
                'actual_platform_permit_issued':False,'remote_channel_ready':'NOT_OBSERVED',
                'next_owner':staged[0]['owner'],'next_action':'original PUB checks exact prior key/effects and fresh full-row facts; stage metadata grants no CMS execution'}
    return {'task_id':task,'registered_sources':records(root,snapshot),'collaboration_scopes':collaboration_scopes(root,snapshot),
            'actual_platform_permit_issued':False,'remote_channel_ready':'NOT_OBSERVED',
            'next_owner':snapshot['goal_delivery']['primary_owner'],'next_action':'original owner normally records exact PUB/WEB payload; original WEB supplies protected target/CLI/runtime only; original PUB obtains fresh actual execution evidence before any Save'}

if __name__ == '__main__':
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=['status','check-request','check-forward-evidence']);parser.add_argument('--task-id',required=True)
    parser.add_argument('--input', help='Project-local existing request JSON; check-request never records a preflight')
    args=parser.parse_args()
    try:
        root = Path(__file__).resolve().parents[1]
        if args.command == 'check-request':
            if args.task_id != _EN2_FORWARD_TASK or not args.input:
                parser.error('check-request requires the exact original EN2 task and --input')
            import goal_delivery_runtime as g
            with w.request_validation_context():
                snapshot = g.restore_goal(root, w.read_json(w.snapshot_path(root, args.task_id)))
                checked = _request(root, snapshot, w.file_digest(root, args.input))
                result = {'result': 'structural_validated_only', 'request': checked['pin'],
                          'external_origin_state': checked['external_origin_state'],
                          'source_event_id': checked['source_event_id'], 'preflight_only': True,
                          'actual_action_allowed': False, 'external_permission_issued': False}
        elif args.command == 'check-forward-evidence':
            if args.task_id != _EN2_FORWARD_TASK:
                parser.error('check-forward-evidence requires the exact original EN2 task')
            import goal_delivery_runtime as g
            with w.request_validation_context() as validation:
                snapshot = g.restore_goal(root, w.read_json(w.snapshot_path(root, args.task_id)))
                result = en2_current_forward_evidence(root, snapshot)
                validation.recheck()
        else:
            result = status(root, args.task_id)
        print(json.dumps(result,ensure_ascii=False,indent=2))
    except (w.WorkflowError,KeyError,ValueError) as error:parser.exit(1,str(error)+'\n')

WEB_INCREMENT_SCHEMA = 'original-received-CMS-channel-production-source/v1'


def received_increment_web_context(root, snapshot, item):
    """An actual owner-selected WEB delivery for an already registered CMS action.

    Registered CMS source, producer final and owner custody are separate facts.
    The original WEB callback is not promoted to result_received by this reader.
    Current facts, per-stage selfcheck/policy and single-use effects stay outside.
    """
    import hashlib
    import datetime as dt
    import department_autonomy as a
    import goal_delivery_runtime as g
    import professional_web_execution as web
    need = a.require
    need(item.get('schema') == WEB_INCREMENT_SCHEMA and item.get('task_id') == snapshot['task_id']
         and set(item) == {'schema','task_id','CMS_source_registration','owner_message_action_id','owner_selection',
              'WEB_completed_native','WEB_audit_native','evidence_manifest','source_backup','rollback_runbook'},
         'exact original received CMS-channel WEB source schema required')
    contexts = [x for x in records(root,snapshot) if x['registration'] == item['CMS_source_registration']]
    need(len(contexts) == 1 and contexts[0].get('dated_source_not_execution_CAS') is True,
         'one actual registered original CMS increment source; issuer is not a WEB source')
    source = contexts[0]; owner = source['owner']; scope = source['business_scope']; role = source['channel']
    goal = snapshot['goal_delivery']; frozen = a.document(root,snapshot['goal_contract'])
    binding = g._collaboration_binding(root,snapshot,role)
    need(binding and role not in w.department_registry(root) and binding.get('project_id') != a.PROJECT
         and all(goal.get(k) == frozen.get(k) for k in ('primary_owner','producer_departments',
                    'authorized_scope','human_authorization','required_execution_actions')),
         'original external WEB role and unchanged owner/contract/authority/scopes required')
    orders = [s for s in g._collaboration_wait_states(root,snapshot,only_action_id=item['owner_message_action_id'])
              if s.get('received') is True and s.get('status') in {'message_received','result_received'}
              and s.get('department') == 'system-development']
    need(len(orders) == 1, 'actual original owner-to-SYS source-return receipt required')
    order = orders[0]['approved_action']; route = a._registered_owner_result_message(root,snapshot,order)
    need(route is not None and order.get('sender_department') == owner and order.get('scope') == scope,
         'authenticated original owner normal result-message source required')
    owner_report = a.document(root,route['report']); selection = a.document(root,item['owner_selection'])
    need(owner_report.get('primary_deliverable') == item['owner_selection']
         and item['owner_selection'] in owner_report.get('evidence',[])
         and selection.get('task_id') == snapshot['task_id'] and selection.get('scope') == scope
         and selection.get('owner') == owner, 'exact real professional owner selection, not caller permission metadata')
    report_pin = selection['source']; report = web.external(root,report_pin,binding)
    body = w.safe_path(root,order['payload']['path']).read_text()
    need(report_pin['path'] in body and report_pin['sha256'] in body
         and report.get('task_id') == snapshot['task_id'] and report.get('scope') == scope
         and report.get('sender_department') == role and report.get('target_department') == owner,
         'actual delivered owner message must bind exact original external WEB report and participants')
    callbacks = [s for s in g._collaboration_wait_states(root,snapshot,only_action_id=report['action_id'])
                 if s.get('received') is True and s.get('department') == role
                 and s.get('status') in {'message_received','result_received'}]
    need(len(callbacks) == 1 and callbacks[0]['approved_action'].get('professional_execution_source') == source['registration']
         and callbacks[0]['approved_action'].get('execution_tuple') == source['action']
         and callbacks[0]['approved_action'].get('sender_department') == owner,
         'actual received original WEB work order for this exact registered CMS tuple required')
    page = g._native_document(root,item['WEB_completed_native'])
    need(all(page.get('thread',{}).get(k) == binding[v] for k,v in {'id':'thread_id','title':'title','cwd':'cwd'}.items()),
         'real original fixed external WEB completion identity required')
    completed = [(t,m) for t in page.get('turns',[]) for m in t.get('items',[])
                 if t.get('status') == 'completed' and not t.get('error') and m.get('type') == 'agentMessage'
                 and m.get('phase') == 'final_answer' and report_pin['path'] in m.get('text','')]
    need(len(completed) == 1, 'one real independently completed producer final linking this exact report required')
    turn,final = completed[0]; made = w._parse_observed_at(report.get('created_at')); selected_at = w._parse_observed_at(selection.get('at'))
    need(made and selected_at and type(turn.get('startedAt')) in {int,float} and type(turn.get('completedAt')) in {int,float}
         and turn['startedAt'] <= made.timestamp() <= turn['completedAt'] <= selected_at.timestamp() <= dt.datetime.now(dt.timezone.utc).timestamp(),
         'actual source/final/owner selection chronology required; no changed old native status')
    original = report['original_owner_and_sources']
    need(original.get('professional_owner') == owner and original.get('content_executor') == source['executor']
         and original.get('source_registration') == source['registration']
         and original.get('source_event') == source['event_id'], 'unchanged exact registered CMS source and event')
    from professional_cms_issuer import validate_contract
    issuer_pin = original['issuer_contract']; issuer_doc = a.document(root,issuer_pin)
    issuer_rows = [e for e in w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS) if e.get('task_id') == snapshot['task_id']
                   and e.get('details',{}).get('professional_cms_issuer_contract') == issuer_pin]
    need(len(issuer_rows) == 1 and issuer_rows[0]['event_id'] == original.get('issuer_event')
         and validate_contract(root,snapshot,issuer_doc)[2] == source['physical_target'],
         'actual same-action issuer registration, never borrowed W or other namespace')
    manifest = web.external(root,item['evidence_manifest'],binding)
    need(selection['frozen'] == item['evidence_manifest'] and manifest.get('task_id') == snapshot['task_id']
         and isinstance(manifest.get('pins'),list) and manifest.get('pin_count') == len(manifest['pins']) > 0,
         'complete exact frozen original producer evidence manifest')
    for pin in manifest['pins']:
        if Path(pin['path']).is_absolute() and not Path(pin['path']).resolve().is_relative_to(Path(root).resolve()):
            web._external_bytes(pin,binding)
        else:
            actual = w.file_digest(root,pin['path']);need(all(actual[k] == pin[k] for k in ('sha256','size')),
                                                       'immutable original company-side source pin changed')
    audit = web.external(root,item['WEB_audit_native'],binding)
    need(report['actual_checks']['native'] == item['WEB_audit_native']
         and all(audit.get('thread',{}).get(k) == binding[v] for k,v in {'id':'thread_id','title':'title','cwd':'cwd'}.items())
         and audit.get('turn',{}).get('id') == turn['id'] and audit['turn'].get('startedAt') == turn['startedAt'],
         'same actual producer audit excerpt and later real completed turn required')
    state = web.code_document(root,report['exact_normal_production_entry_gap']['request_state'])
    state_calls = []
    for command in audit.get('items',[]):
        if command.get('type') != 'commandExecution' or command.get('status') != 'completed' or command.get('exitCode') != 0:
            continue
        need(Path(command.get('cwd','')).resolve().is_relative_to(Path(binding['cwd']).resolve()), 'real external command cwd required')
        try: output = json.loads(w._completion_execution_output(command))
        except ValueError: continue
        if isinstance(output,dict) and output.get('state') == state:state_calls.append((command,output))
    need(len(state_calls) == 1, 'one actual complete native output of the original request state required')
    failed = state_calls[0][1].get('normal_request',{})
    need(failed.get('exit_code') == report['exact_normal_production_entry_gap']['request_actual_exit_code'] == 1
         and failed.get('stdout') == '' and 'IndexError: list index out of range' in failed.get('stderr','')
         and report['exact_normal_production_entry_gap'].get('request_output_created') is False,
         'actual pre-request empty-source failure retained; not a successful preflight/push')
    meta = report['actual_local_version']; ctx = {'worktree':meta['worktree']}; head = meta['candidate_commit']; base = meta['candidate_base']
    files = meta['files']; paths = {x['path']:x['sha256'] for x in files}
    need(meta['task_id'] == snapshot['task_id'] and selection['local_candidate'] == head
         and head[:8] in final.get('text','') and len(paths) == len(files) == meta['file_count'] and 0 < len(paths) <= 40
         and Path(meta['worktree']).resolve().is_relative_to(Path(binding['cwd']).resolve())
         and all(state.get(k) == meta.get(k) for k in ('candidate_commit','candidate_parent','candidate_parents','candidate_base','candidate_tree','branch','worktree'))
         and meta['candidate_parent'] == base and meta['candidate_parents'] == [base]
         and web.git(ctx,'show','-s','--format=%H %P %T',head).decode().strip() == ' '.join([head,base,meta['candidate_tree']])
         and set(web.git(ctx,'diff','--name-only',base,head).decode().splitlines()) == set(paths),
         'actual bounded Git head/parent/tree/branch/worktree/source map, never a future or substituted version')
    for f in files:
        path = f['path'];need(not Path(path).is_absolute() and '..' not in Path(path).parts,'exact repository relative source path')
        raw = web.git(ctx,'show',head+':'+path);tree = web.git(ctx,'ls-tree',head,'--',path).decode().split()
        old = web.git(ctx,'ls-tree',base,'--',path).decode().split()
        need(hashlib.sha256(raw).hexdigest() == f['sha256'] and len(raw) == f['size']
             and tree[:3] == [f['mode'],'blob',f['blob']] and f['mode'] in {'100644','100755'}
             and (not old or old[0] == f['mode']), 'every original blob/hash/size/mode must survive')
    delta = web._patch_effect(web._delta({**ctx,'paths':paths},base,head))
    forward, inverse = meta['forward'],meta['inverse_source_only']
    need(web._patch_effect(web._patch_delta(web._external_bytes(forward,binding))) == delta
         and web._patch_effect(web._patch_delta(web._external_bytes(inverse,binding))) == {p:(added,removed)for p,(removed,added)in delta.items()},
         'exact original forward/inverse source effects, never compiled runtime restore proof')
    alignment = report['CLI_workflow_runtime_local_alignment']; runtime_path = alignment['runtime_selector']; cli_path = alignment['new_exact_reader']
    need(runtime_path in paths and cli_path in paths and report['exact_Kitchen_runtime_target'] == source['physical_target'],
         'actual original registered one-field full41/stable38/MS11 target only')
    runtime = web.git(ctx,'show',head+':'+runtime_path).decode(); decoder = json.JSONDecoder()
    match = re.search(r'=\s*(\[)',runtime);need(match is not None,'actual immutable runtime target array required')
    targets,end = decoder.raw_decode(runtime[match.start(1):]);need(targets == [source['physical_target']], 'one exact runtime target; no shoe/W/default namespace')
    cli = web.git(ctx,'show',head+':'+cli_path).decode()
    constants = {k:json.loads(v) for k,v in re.findall(r'const\s+(sourcePath|sourceSha256|name|taskId|scope)\s*=\s*("[^"\n]*")\s*;',cli)}
    need(set(constants) == {'sourcePath','sourceSha256','name','taskId','scope'}
         and constants['sourcePath'] in paths and constants['sourceSha256'] == paths[constants['sourcePath']]
         and all(constants[k] == v for k,v in {'name':source['action']['candidate_version'],'taskId':snapshot['task_id'],'scope':source['action']['scope']}.items()),
         'original CLI/frozen source must bind this exact task/action/scope/bytes')
    frozen_bytes = web.git(ctx,'show',head+':'+constants['sourcePath']); carrier = json.loads(frozen_bytes)
    need(carrier.get('registration_input') == source['registration'] and carrier.get('owner_source') == source['source']
         and carrier.get('runtime_target') == source['physical_target'] and carrier.get('forward_tuple') == source['action']
         and carrier.get('before') == a.document(root,source['baseline_pin']) and carrier.get('desired') == source['desired']
         and carrier.get('original_professional_owner') == owner and carrier.get('business_scope') == scope
         and carrier.get('new_permission_issued') is False and carrier.get('baseline_only_not_execution_CAS') is True,
         'immutable original full-row source/carrier/only-field delta retained')
    account = web.external(root,report['actual_remote_current_effects']['fresh_facts'],binding)
    native_state = state_calls[0][1]['state']; repo = native_state['repository']; actor = native_state['actor']; rawgh = account.get('raw_GitHub',{}).get('data',{})
    need(account.get('state') == state and rawgh.get('viewer') == {'login':actor.get('login'),'databaseId':actor.get('id')}
         and rawgh.get('repository',{}).get('nameWithOwner') == repo and rawgh['repository'].get('databaseId') == state['repository_id']
         and type(actor.get('id')) is int and actor['id'] > 0 and actor.get('login') == repo.split('/')[0]
         and web.git(ctx,'config','--get','remote.origin.url').decode().strip() in {'user-3de132cd98be@example.invalid:'+repo+'.git','https://github.com/'+repo,'https://github.com/'+repo+'.git'},
         'actual same original repository/actor raw native identity; no copied other-task permission')
    components = [{'head':head,'base':base,'parent':meta['candidate_parent'],'tree':meta['candidate_tree'],
                   'worktree':meta['worktree'],'paths':paths,'forward':forward,'inverse':inverse}]
    backup = a.document(root,item['source_backup']); recovery = a.document(root,item['rollback_runbook'])
    need(backup == {'task_id':snapshot['task_id'],'source_components':components,'actual_platform_backup_or_restore_proven':False}
         and recovery == {'task_id':snapshot['task_id'],'goal_contract':snapshot['goal_contract'],'source_components':components,
            'unknown_effect_replay_allowed':False,'CMS_inverse_requires_own_completed_parent':True,
            'source_inverse_is_not_production_rollback':True,'execution_requires_actual_platform_backup':True},
         'exact source-only backup/recovery provenance; no invented actual platform restore or future parent')
    from managed_cms_permit_issuer import SUPABASE_HOST
    project_ref = SUPABASE_HOST.split('.')[0]
    return {'root':str(Path(root).resolve()),'task':snapshot['task_id'],'scope':scope,'owner':owner,'role':role,'binding':binding,
            'decision':item['owner_selection'],'authorization':goal['authorization_pin'],'contract':snapshot['goal_contract'],
            'worktree':meta['worktree'],'site':binding['cwd'],'branch':meta['branch'],'commit':head,'base':base,'tree':meta['candidate_tree'],
            'paths':paths,'source_components':components,'registered_CMS':source,'backup':item['source_backup'],'rollback':item['rollback_runbook'],
            'repository':repo,'repository_id':state['repository_id'],'actor_id':actor['id'],'original_production_channel':True,
            'prefix':snapshot['task_id']+'-original-web','edge_scope':'company.example:edge:'+project_ref+':content-publish',
            'pages_scope':'company.example:pages:production','project_ref':project_ref,
            'producer_final_proven':True,'owner_source_selection_proven':True,'formal_WEB_result_receipt_not_inferred':True}
