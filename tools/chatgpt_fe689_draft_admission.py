"""Candidate exact paused-draft channel; no Ads client or global rotation waiver.

Preparation validates a project-local projection, not actual UI provenance.
Permits additionally require normal independent child acceptance, exact source
adoption and the original parent A1's committed decision on real Paid2 intake.
Installing/importing this module or passing an editable flag grants nothing.
"""
from __future__ import annotations
from pathlib import Path
import copy, datetime as dt, json
from urllib.parse import urlsplit, parse_qs
import workflow_control as w

TASK = 'fc-20261019-chatgpt-paid2-execution-followthrough-v1'
CHILD = 'fc-20261022-chatgpt-fe689-paused-draft-admission-repair-v1'
VERSION = 'chatgpt-fe689-paused-draft-admission-candidate-v4'
ADOPTION_STAGE = 'fc-20261023-chatgpt-fe689-runtime-adoption-stage-v1'
ADOPTION_SCOPE = 'project:flashcast:chatgpt-fe689:runtime-adoption-stage:20261023:v1'
ADOPTION_VERSION = 'chatgpt-fe689-exact-runtime-adoption-stage-v4-20261023'
ADOPTION_AUTH = {'path': 'logs/handoffs/2026-10-20-clean-department-window-rotation-v1/operations/unfinished-business-followthrough-20261021-v1/owner-delegated-nonpayment-decisions-system-repair-v1/owner-current-human-native-v1.json', 'sha256': '5568a10ef0e63fc7558695704a4e10d500605a7340de31cc35012edc25aab0df', 'size': 1207}
SCOPE = 'project:flashcast:chatgpt-ads:existing-paused-pilot:20261019:paid2'
CHILD_SCOPE = 'project:flashcast:chatgpt-fe689:paused-draft-admission-repair:20261022:v1'
ROLE, REVIEWER = 'paid-growth-data-2', 'operations-assistant'
THREAD = '<LOCAL_TASK_ID>'
PROJECT = '<LOCAL_PROJECT_ID>'
ACCOUNT, EMAIL = 'adacct_example_3620baed04d9c3e5', 'user-0c721c9ec022@example.invalid'
CAMPAIGN = 'EXAMPLE_EXISTING_CAMPAIGN'
ACTION = 'chatgpt-fe689-residential-paused-draft-save-readback-20261022-v29'
BASE = 'logs/handoffs/2026-10-19-chatgpt-paid2-task-transfer/offer-account-preparation-20261021-v1/resume-20261021-v1/authorized-dispatch-v1/'
OWNER = {'path': BASE+'owner-execute-approved-plan-v28.json', 'sha256':'efb04208f346697c22b0730f389d9c6fd42e66c5458de60e1ed222c8712c584d','size':2222}
PLAN = {'path': BASE+'residential-draft-execution-plan-fe689-v29.json','sha256':'41d38e2280788e57481d7388a8c18a25222cbf5f04e98542ea123e9eca8be8b1','size':4955}
LOCAL_AUTH = {'path': BASE+'owner-system-admission-repair-send-authorized-v31.json','sha256':'c6a485833e516d7b5e137b925071dcae27312cf15f42d986f75f8e0bc56e4fa4','size':2772}
TARGETS = {'tools/workflow_control.py','tools/goal_delivery_runtime.py','tools/chatgpt_fe689_draft_admission.py'}
EXISTING_AD_NAMES = {'ZH_WHOLE_HOME': {'A - 全屋收纳与材料范围', 'B - 新屋空间与使用习惯'},
                     'ZH_KITCHEN': {'A - 厨房收纳与动线', 'B - 厨房报价与施工范围'}}
TTL_SECONDS = 300


def require(value, reason):
    if not value:
        raise w.WorkflowError('exact fe689 paused draft: '+reason)


def document(root, pin):
    require(isinstance(pin, dict) and set(pin)=={'path','sha256','size'}, 'exact immutable pin required')
    raw = Path(pin['path'])
    require(not raw.is_absolute() and '..' not in raw.parts, 'project-relative evidence required')
    path = Path(root)/raw
    require(not any(p.is_symlink() for p in [path,*path.parents]) and path.resolve().is_relative_to(Path(root).resolve()), 'no symlink or cross-project source')
    require(w.file_digest(root,pin['path'])==pin, 'source bytes/hash changed')
    def unique(pairs):
        value={}
        for key,item in pairs:
            require(key not in value, 'ambiguous JSON field');value[key]=item
        return value
    value=json.loads(path.read_text(),object_pairs_hook=unique,
                     parse_constant=lambda _: require(False,'nonfinite JSON number'))
    require(isinstance(value,dict), 'object evidence required')
    return value


def current_parent(root):
    snapshot=w.read_json(w.snapshot_path(root,TASK));goal=snapshot.get('goal_delivery',{})
    require(snapshot.get('task_id')==TASK and snapshot.get('current_state') not in w.TERMINAL_STATES,
            'open original parent required')
    require(goal.get('primary_owner')==ROLE and goal.get('responsible_assistant')==REVIEWER
            and goal.get('authorized_scope')==[SCOPE], 'original owner/unique A1/scope required')
    contract=document(root,snapshot['goal_contract']);contract=contract.get('goal_delivery',contract)
    require(goal.get('required_execution_actions')==contract.get('required_execution_actions'),
            'frozen original actions cannot be edited to add this action')
    binding=w.department_registry(root)[ROLE]['chat_binding']
    require(binding.get('task_id')==THREAD and binding.get('project_id')==PROJECT
            and Path(binding.get('cwd','')).resolve()==Path(root).resolve(), 'exact current Paid2 window/project required')
    return snapshot


def _fresh_at(value, checked_at):
    observed=w._parse_observed_at(value)
    require(observed is not None and 0 <= (checked_at-observed).total_seconds() <= TTL_SECONDS,
            'fresh nonfuture complete native readback required')


def fresh(value):
    _fresh_at(value, dt.datetime.now(dt.timezone.utc))


BROWSER_PROFILE = '2233'
BROWSER_EXTENSION = '611cd409-140a-4d13-abbd-0929062b241f'


def _native_browser_identity(root, before, channel):
    """Bind ephemeral handles to one observed original Chrome profile/extension.

    This reads the existing native inventory projection, not a new browser API.
    Editable projection validity is not proof of UI provenance or permission.
    """
    require(channel.get('profile_name') == BROWSER_PROFILE,
            'original Chrome profile required')
    for value in (before, channel):
        require(('profile_name' not in value or value['profile_name'] == BROWSER_PROFILE)
                and ('extension_instance_id' not in value
                     or value['extension_instance_id'] == BROWSER_EXTENSION),
                'contradictory projected stable browser identity')
    browser_id, tab_id = channel.get('browser_id'), channel.get('tab_id')
    require(isinstance(browser_id, str) and browser_id.strip()
            and browser_id == before.get('browser_id')
            and isinstance(tab_id, str) and tab_id.strip()
            and tab_id == before.get('tab_id'),
            'same observed browser and tab handles required')
    url = urlsplit(channel.get('url', ''))
    require(url.scheme == 'https' and url.netloc == 'ads.openai.com'
            and url.path == '/manage/campaigns'
            and parse_qs(url.query).get('act') == [ACCOUNT],
            'original existing campaign/account URL required')
    pins = []
    for value in (before, channel):
        require(isinstance(value.get('native_evidence'), list)
                and value['native_evidence'], 'actual native evidence pins required')
        for pin in value['native_evidence']:
            require(w.file_digest(root, pin.get('path', '')) == pin,
                    'native evidence bytes changed')
            if pin not in pins:
                pins.append(pin)
    inventories = []
    for pin in pins:
        # Native evidence can also contain screenshots or AX text. Only the
        # observed, already-supported inventory shape is an identity source.
        if Path(pin['path']).suffix.lower() != '.json':
            continue
        value = document(root, pin)
        if isinstance(value.get('channel'), dict) and isinstance(value.get('ads_tabs'), list):
            inventories.append((pin, value))
    require(len(inventories) == 1, 'one exact native Chrome inventory required')
    pin, inventory = inventories[0]
    observed = inventory['channel']
    require(observed.get('family') == 'chrome' and observed.get('type') == 'extension'
            and observed.get('id') == browser_id
            and observed.get('profileName') == BROWSER_PROFILE
            and observed.get('metadata', {}).get('extensionInstanceId') == BROWSER_EXTENSION,
            'original stable Chrome profile/extension and observed handle required')
    matches = [tab for tab in inventory['ads_tabs'] if tab.get('id') == tab_id]
    require(len(matches) == 1 and matches[0].get('browserId') == browser_id
            and matches[0].get('url') == channel.get('url'),
            'one actual matching account tab in observed Chrome inventory required')
    require(w._parse_observed_at(inventory.get('at')) is not None,
            'native inventory observation timestamp required')
    return {'native_inventory': pin, 'observed_at': inventory['at'],
            'profile_name': BROWSER_PROFILE, 'extension_instance_id': BROWSER_EXTENSION,
            'browser_id': browser_id, 'tab_id': tab_id,
            'projection_only_not_permission': True}


def expected_new_group(root):
    plan=document(root,PLAN);group=copy.deepcopy(plan['new_group'])
    require(plan['account_id']==ACCOUNT and plan['existing_campaign']==CAMPAIGN
            and plan['intended_total']['budget_shared_average_myr_day']==35
            and plan['intended_total']['pause_all'] is True, 'original v29 exact plan required')
    require(w.file_digest(root,plan['image']['asset']['path'])==plan['image']['asset'], 'image bytes changed')
    group.update(id=None,status='Draft',enabled=False)
    for ad in group['ads']:
        ad.update(id=None,status='Draft',enabled=False,image_asset_sha256=plan['image']['asset']['sha256'])
    return group


def _immutable_intent(root, request_pin):
    """Validate frozen scope and bytes; age alone never changes saved intent."""
    current_parent(root);request=document(root,request_pin)
    required={'task_id','department','action_id','action_class','scope','source_project_id','source_thread_id',
              'account_id','login_email','campaign_id','campaign_name','operation','owner_authority','plan',
              'live_before','desired_state','legal_channel','old_permit_id'}
    require(set(request)==required, 'exact bounded request fields required')
    expected={'task_id':TASK,'department':ROLE,'action_id':ACTION,'action_class':'ads_write','scope':SCOPE,
              'source_project_id':PROJECT,'source_thread_id':THREAD,'account_id':ACCOUNT,'login_email':EMAIL,
              'campaign_name':CAMPAIGN,'operation':'save-as-draft/readback','owner_authority':OWNER,'plan':PLAN,
              'old_permit_id':None}
    require(all(request.get(k)==v for k,v in expected.items()), 'account/window/action/authority mismatch; old permits never transfer')
    authority=document(root,OWNER)
    require(authority.get('source_thread_id')==THREAD and authority.get('source_message_id')=='example-native-7ca065870419168f'
            and authority.get('message',{}).get('type')=='userMessage'
            and authority['message'].get('id')==authority['source_message_id'], 'actual v28 human source required')
    before=document(root,request['live_before']);after=document(root,request['desired_state']);channel=document(root,request['legal_channel'])
    for value in (before,after,channel):
        require(value.get('account_id')==ACCOUNT and value.get('login_email')==EMAIL
                and value.get('source_project_id')==PROJECT and value.get('source_thread_id')==THREAD,
                'every projection/channel must retain exact current account and executor')
    require(isinstance(request['campaign_id'],str) and request['campaign_id'].strip(), 'actual existing campaign ID required, not only a name')
    campaign=before.get('campaign',{});desired=after.get('campaign',{})
    require(campaign.get('id')==request['campaign_id'] and campaign.get('name')==CAMPAIGN
            and campaign.get('status')=='Draft' and campaign.get('enabled') is False
            and campaign.get('creative_enabled') is False, 'complete actual Draft/OFF baseline required')
    require(campaign.get('budget')=={'currency':'MYR','average_per_day':35}
            and type(campaign['budget']['average_per_day']) is int, 'shared average MYR35 only, no per-group increase')
    groups=campaign.get('groups',[])
    require(len(groups)==2 and {g.get('name') for g in groups}=={'ZH_WHOLE_HOME','ZH_KITCHEN'}, 'only original two groups before save; recover existing effect instead of recreate')
    identifiers=[campaign['id']]
    for group in groups:
        require(group.get('status')=='Draft' and group.get('enabled') is False and len(group.get('ads',[]))==2,
                'original two groups/four ads must all be OFF')
        require({ad.get('name')for ad in group['ads']}==EXISTING_AD_NAMES[group['name']],
                'exact original four ad identities required, not arbitrary replacement objects')
        identifiers.append(group.get('id'))
        for ad in group['ads']:
            require(ad.get('status')=='Draft' and ad.get('enabled') is False, 'original ad OFF required')
            identifiers.append(ad.get('id'))
    require(all(isinstance(x,str)and x.strip()for x in identifiers)and len(set(identifiers))==7,
            'complete unique original object IDs required')
    require({k:v for k,v in desired.items()if k!='groups'}=={k:v for k,v in campaign.items()if k!='groups'},
            'campaign/budget/schedule/tracking and all parallel fields must be preserved')
    require(desired.get('groups')==[*groups,expected_new_group(root)],
            'only exact v29 residential group/two OFF ads; protect full original objects and WIP')
    require(channel.get('kind')=='authenticated_existing_browser' and channel.get('origin')=='https://ads.openai.com'
            and channel.get('control')=='Save as draft' and channel.get('readback_supported') is True
            and channel.get('terms_acceptance') is False and channel.get('publish') is False
            and channel.get('activate') is False and channel.get('payment') is False,
            'existing legal Save as draft/readback channel only; no Terms/Publish/activate/payment')
    browser_identity = _native_browser_identity(root, before, channel)
    for value in (before,channel):
        require(isinstance(value.get('native_evidence'),list)and value['native_evidence'], 'actual native evidence pins required')
        for pin in value['native_evidence']:
            require(w.file_digest(root,pin.get('path',''))==pin, 'native evidence bytes changed')
    return {'state':'IMMUTABLE_SCOPE_ONLY_NOT_AUTHORIZED','request':request_pin,
            'intent':request,'protected_objects_sha256':w.sha256_value(campaign),
            'external_permission_issued':False,'actual_action_allowed':False,'writes_performed':False,
            'browser_identity':browser_identity}


def prepare(root, request_pin):
    """Pre-effect preparation remains strictly fresh and never issues a permit."""
    staged=_immutable_intent(root,request_pin)
    for name in ('live_before','legal_channel'):
        fresh(document(root,staged['intent'][name]).get('observed_at'))
    fresh(staged['browser_identity']['observed_at'])
    return {**staged,'state':'PREPARED_FOR_INDEPENDENT_REVIEW_NOT_AUTHORIZED'}


def _runtime_adopted_stage(root, journal, local_accepted):
    """An independently accepted internal stage can adopt the original local code.

    Local-only PASS is retained as provenance; it cannot itself grant adoption
    or account permission. The exact current stage must prove actual source
    adoption through the normal typed reader, including real A1 native effect.
    """
    import goal_delivery_runtime as g
    stage = w.read_json(w.snapshot_path(root, ADOPTION_STAGE))
    goal = g.restore_goal(root, stage).get('goal_delivery', {})
    require(goal.get('parent_task_id') == CHILD
            and goal.get('primary_owner') == 'system-development'
            and goal.get('producer_departments') == ['system-development']
            and goal.get('responsible_assistant') == REVIEWER
            and goal.get('authorized_scope') == [ADOPTION_SCOPE]
            and goal.get('required_execution_actions') == []
            and goal.get('production_write_allowed') is False
            and goal.get('authorization_pin') == ADOPTION_AUTH,
            'exact independent internal adoption stage and original owner delegation required')
    rows, bad = w._validate_receipt_chain(root, ADOPTION_STAGE)
    require(not bad and not w.validate_workflow_events(root, ADOPTION_STAGE), 'intact actual adoption-stage chains required')
    accepted = w.goal_completion_subject(root, stage, rows,
        {'mode':'latest_exact_accepted_result','producer_department':'system-development'})
    require(accepted.get('state') == 'PROVEN'
            and accepted.get('identity',{}).get('candidate_version') == ADOPTION_VERSION,
            'normal independent actual adoption-stage acceptance required')
    manifest = document(root, accepted['candidate'])
    require(manifest.get('task_id') == ADOPTION_STAGE
            and manifest.get('department') == 'system-development'
            and manifest.get('reviewed_local_predecessor') == local_accepted['candidate']
            and manifest.get('candidate_fingerprint') == accepted.get('source_fingerprint')
            and journal.get('task_id') == ADOPTION_STAGE
            and journal.get('candidate_manifest') == accepted['candidate']
            and journal.get('candidate_fingerprint') == accepted['source_fingerprint']
            and journal.get('authorized_source') == ADOPTION_AUTH,
            'exact stage/current source/local predecessor/adoption journal identity required')
    requirements = [x for x in goal.get('completion_requirements', [])
                    if x.get('requirement_type') == 'source_adoption']
    require(bool(requirements), 'actual typed source-adoption requirement required')
    proven = [w.goal_typed_completion_proof(root, stage, rows, req, accepted) for req in requirements]
    require(all(x.get('state') == 'PROVEN' for x in proven),
            'normal typed actual adopted source/native evidence required before parent execution')
    stage_box = document(root, accepted['producer_outbox'])
    require(stage_box.get('candidate_manifest') == accepted['candidate'], 'one actual independently accepted stage source required')
    return accepted, manifest, [w.file_digest(root,str(w.snapshot_path(root,ADOPTION_STAGE).relative_to(root))),
        w.file_digest(root,str(w.receipts_path(root,ADOPTION_STAGE).relative_to(root))),
        accepted['producer_outbox'],accepted['candidate'],*sum([p.get('evidence',[]) for p in proven],[])]


def _release_sources(root, envelope):
    """Authenticate original review/adoption/decision without renewing execution."""
    require(isinstance(envelope,dict)and set(envelope)=={'request','release'}, 'exact request and independent release pins required')
    staged=_immutable_intent(root,envelope['request']);release=document(root,envelope['release'])
    require(set(release)=={'adoption_journal','parent_decision_record_id'}, 'no caller allow flag')
    child=w.read_json(w.snapshot_path(root,CHILD));goal=child.get('goal_delivery',{})
    require(goal.get('parent_task_id')==TASK and goal.get('responsible_assistant')==REVIEWER
            and 'system-development'in goal.get('producer_departments',[])and goal.get('authorization_pin')==LOCAL_AUTH,
            'actual original child and unique independent A1 required')
    rows,bad=w._validate_receipt_chain(root,CHILD);require(not bad,'intact actual child source chain required')
    accepted=w.goal_completion_subject(root,child,rows,{'mode':'latest_exact_accepted_result','producer_department':'system-development'})
    require(accepted.get('state')=='PROVEN'and accepted.get('identity',{}).get('candidate_version')==VERSION,
            'normal independent current candidate acceptance required; local PASS is insufficient')
    box=document(root,accepted['producer_outbox']);manifest=document(root,box['candidate_manifest'])
    require(manifest.get('task_id')==CHILD and manifest.get('department')=='system-development'
            and manifest.get('candidate_version')==VERSION and {x['path']for x in manifest.get('changes',[])}==TARGETS
            and len(manifest['changes'])==3 and box['candidate_manifest']==accepted.get('candidate')
            and manifest.get('candidate_fingerprint')==accepted.get('source_fingerprint'), 'exact reviewed three-file candidate required')
    journal=document(root,release['adoption_journal'])
    require(journal.get('executor')==REVIEWER and journal.get('actor')==REVIEWER
            and journal.get('state')=='adopted' and journal.get('fixture_only') is False
            and journal.get('external_writes')==0 and journal.get('permissions_issued') is False,
            'actual original independent A1 adoption required; no local-only or SYS self-sign')
    stage_accepted, effective, stage_guards = _runtime_adopted_stage(root,journal,accepted)
    require(len(effective.get('changes',[]))==3
            and {x['path']for x in effective['changes']}==TARGETS,
            'exact independent adopted three-file runtime stage required')
    operations=journal.get('source_operations',[])
    require(len(operations)==3 and {x['path']for x in operations}==TARGETS,
            'exact adopted three-file source operation set required')
    import source_patch_transaction as tx
    for change in effective['changes']:
        operation=next(x for x in operations if x['path']==change['path'])
        actual=tx.fingerprint(root,change['path'])
        require(actual['sha256']==operation.get('after_sha256')==change['candidate']['sha256']
                and actual['size']==change['candidate']['size']
                and actual['mode']==int(change['mode'],8),
                'reviewed/adopted/current runtime source mismatch or parallel WIP')
    parent=current_parent(root)
    _,parent_bad=w._validate_receipt_chain(root,TASK)
    require(not parent_bad and not w.validate_workflow_events(root,TASK), 'original parent chains required')
    events=w._result_handoff_rows(root,TASK)
    decisions=[x for x in events if x.get('record_id')==release['parent_decision_record_id']]
    require(len(decisions)==1,'one actual parent assistant decision required');decision=decisions[0]
    require(decision.get('event')=='controller_decision'and decision.get('decision')=='continue'
            and decision.get('decision_actor')==decision.get('coordinator_role')==REVIEWER
            and decision.get('next_owner')==ROLE and decision.get('next_action')=='authorize-exact-'+ACTION
            and envelope['request']in decision.get('evidence',[]), 'exact parent A1 decision on this request required')
    from scoped_candidate_adoption import _committed
    _committed(root,decision)
    source=document(root,decision['outbox'])
    require(source.get('task_id')==TASK and source.get('department')==ROLE
            and source.get('draft_admission_request')==envelope['request'], 'real original Paid2 readiness result required')
    same=lambda row:all(row.get(k)==decision.get(k)for k in ('task_id','sender_department','candidate_version','result_sha256'))
    queued=[x for x in events if same(x)and x.get('event')=='notification_queued']
    received=[x for x in events if same(x)and x.get('event')=='controller_received']
    require(len(queued)==len(received)==1 and received[0].get('decision_actor')==REVIEWER
            and events.index(queued[0])<events.index(received[0])<events.index(decision), 'actual original A1 intake/decision chain required')
    _committed(root,received[0]);w._validate_goal_completed_result(root,queued[0],THREAD)
    adopted=w._parse_observed_at(journal.get('completed_at'));decided=w._parse_observed_at(decision.get('created_at'))
    reviewed=w._parse_observed_at(stage_accepted.get('acceptance_receipt',{}).get('created_at'))
    started=w._parse_observed_at(journal.get('started_at'))
    require(all(x is not None for x in (reviewed,started,adopted,decided))
            and reviewed<=started<=adopted<=decided<=dt.datetime.now(dt.timezone.utc),
            'actual independent review, adoption and original A1 decision must retain their real order')
    guards=[w.file_digest(root,str(w.snapshot_path(root,t).relative_to(root)))for t in (TASK,CHILD)]
    guards += [w.file_digest(root,str(w.receipts_path(root,t).relative_to(root)))for t in (TASK,CHILD)]
    guards += [envelope['request'],envelope['release'],release['adoption_journal'],box['candidate_manifest'],
               decision['outbox'],OWNER,PLAN,LOCAL_AUTH,
               staged['intent']['live_before'],staged['intent']['desired_state'],staged['intent']['legal_channel']]
    guards += stage_guards
    guards += [w.file_digest(root,path)for path in TARGETS]
    guards += [w.file_digest(root,str(w.result_handoff_path(root,TASK).relative_to(root)))]
    for kind in ('live_before','legal_channel'):
        guards += document(root,staged['intent'][kind])['native_evidence']
    return {**staged,'guards':guards,'decision_record_id':decision['record_id'],
            'execution_key':w.sha256_value([TASK,ROLE,ACCOUNT,staged['intent']['campaign_id'],ACTION])}


def released(root, envelope):
    """Only the execution path may consume this still-fresh source context."""
    context=_release_sources(root,envelope)
    for name in ('live_before','legal_channel'):
        fresh(document(root,context['intent'][name]).get('observed_at'))
    fresh(context['browser_identity']['observed_at'])
    return context


def action_binding(root, snapshot, request):
    context=released(root,request.get('draft_admission'))
    intent=context['intent']
    require(snapshot.get('task_id')==TASK and all(request.get(k)==intent[k]for k in ('task_id','department','action_id','action_class','scope')),
            'new action cannot inherit another original action identity')
    require(request.get('sender_department')==ROLE and request.get('payload_sha256')==context['request']['sha256'],
            'exact Paid2 request payload required')
    return context


def policy(root, requested, envelope):
    if (isinstance(envelope, dict) and isinstance(envelope.get('request'), dict)
            and document(root, envelope['request']).get('operation') == UNSAVED_OPERATION):
        return unsaved_policy(root, requested, envelope)
    if (isinstance(envelope, dict) and isinstance(envelope.get('request'), dict)
            and document(root, envelope['request']).get('operation') == INSPECTION_OPERATION):
        return inspection_policy(root, requested, envelope)
    context=released(root,envelope);intent=context['intent']
    require(all(requested.get(k)==intent[k]for k in ('task_id','department','action_id','action_class','scope'))
            and requested.get('source_project_id')==PROJECT and requested.get('payload_sha256')==context['request']['sha256']
            and requested.get('approval_id')=='' and requested.get('skill')=='chatgpt-ads',
            'exact new policy identity, skill and payload; no previous approval')
    require(not any(requested.get(k)for k in ('target_project_id','target_department','target_thread_id',
            'target_thread_title','target_cwd','target_sidebar_section_id','target_automation_status',
            'retry_blocked_execution_receipt_id')), 'no cross-target, automation or legacy retry channel')
    # Recheck normal health and scoped facts; no editable global Ads switch.
    require(w._chat_binding_healthy(w.department_registry(root)[ROLE]['chat_binding'],verification_ttl_hours=26,
                                   now=dt.datetime.now(dt.timezone.utc)), 'fresh actual fixed-role health required')
    require(w.department_registry(root)[ROLE].get('new_dispatch_enabled') is True
            and 'chatgpt-ads'in w.department_registry(root)[ROLE].get('approved_subskills',[]),
            'current enabled original Paid2 role and registered skill required')
    decision={**requested,'draft_admission':envelope,'exact_draft_key':context['execution_key'],
              'allowed_operations':['save-as-draft','readback'],'account_id':ACCOUNT,'campaign_id':intent['campaign_id'],
              'enabled':False,'budget_average_myr_day':35,'production_release_eligible':False,
              'paid_promotion_enabled':bool(w.load_policy(root).get('paid_promotion_enabled',False)),
              'exact_paused_draft_exception':True,'promotion_activation_or_payment_authority':False,
              'required_receipts':['independent_child_current_candidate_acceptance','actual_exact_three_file_adoption',
                  'actual_original_A1_readiness_intake_and_decision','full_native_before_backup',
                  'fresh_legal_Save_as_draft_channel','reserve_once_before_native_effect'],
              'approval_basis':'actual_independently_adopted_exact_draft_and_parent_A1_decision',
              'checked_at':w.utc_timestamp()}
    with w.workflow_lock(root):
        for pin in context['guards']:
            require(w.file_digest(root,pin['path'])==pin,'source changed before exact policy commit')
        for name in ('live_before','legal_channel'):
            fresh(document(root,intent[name]).get('observed_at'))
        fresh(context['browser_identity']['observed_at'])
        prior=[x for x in w.read_jsonl(Path(root)/w.POLICY_DECISIONS)
               if x.get('exact_draft_key')==context['execution_key']and x.get('status')=='allow']
        require(not prior,'new action already issued; inspect actual effect, never replay')
        if not requested.get('consume_approval'):
            return {**decision,'status':'preflight_ready_not_a_permit','actual_action_allowed':False},[]
        decision.update(status='allow',decision_id='pol-'+w.sha256_value([context['execution_key'],decision['checked_at']])[:20],
                        approval_status='consumed_for_exact_draft_only',actual_action_allowed=True)
        w.append_jsonl_locked(Path(root)/w.POLICY_DECISIONS,decision)
    return decision,[Path(root)/w.POLICY_DECISIONS]


def _attempt_path(root, execution_key):
    return Path(root)/'logs/exact-chatgpt-draft-attempts'/(execution_key+'.jsonl')


def reserve_native_attempt(root, envelope, decision_id):
    """Reserve once BEFORE browser effect. Uncertain effects can never auto-retry."""
    context=released(root,envelope)
    with w.workflow_lock(root):
        for pin in context['guards']:
            require(w.file_digest(root,pin['path'])==pin,'source changed before native reservation')
        rows=[x for x in w.read_jsonl(Path(root)/w.POLICY_DECISIONS)if x.get('decision_id')==decision_id]
        require(len(rows)==1 and rows[0].get('status')=='allow'and rows[0].get('exact_draft_key')==context['execution_key']
                and rows[0].get('draft_admission')==envelope,'one exact fresh newly issued draft permit required')
        fresh(rows[0].get('checked_at'))
        for name in ('live_before','legal_channel'):
            fresh(document(root,context['intent'][name]).get('observed_at'))
        fresh(context['browser_identity']['observed_at'])
        path=_attempt_path(root,context['execution_key'])
        require(not path.exists(),'prior attempted/uncertain/successful effect must not be replayed')
        row={'state':'reserved_before_native_effect','task_id':TASK,'action_id':ACTION,'account_id':ACCOUNT,
             'campaign_id':context['intent']['campaign_id'],'decision_id':decision_id,'draft_admission':envelope,
             'reserved_at':w.utc_timestamp(),'actual_save_or_readback_claimed':False}
        w.append_jsonl_locked(path,row)
    return row


def _reserved_original_attempt(root, context, envelope, decision_id):
    """Read one already-issued/occupied attempt; never issue or reserve again."""
    intent=context['intent']
    grants=[row for row in w.read_jsonl(Path(root)/w.POLICY_DECISIONS)
            if row.get('exact_draft_key')==context['execution_key'] and row.get('status')=='allow']
    require(len(grants)==1 and grants[0].get('decision_id')==decision_id,
            'one original exact issued permit required for post-effect readback')
    grant=grants[0]
    require(all(grant.get(k)==v for k,v in {
        'task_id':TASK,'department':ROLE,'action_id':ACTION,'action_class':'ads_write','scope':SCOPE,
        'draft_admission':envelope,'account_id':ACCOUNT,'campaign_id':intent['campaign_id'],
        'payload_sha256':context['request']['sha256'],'consume_approval':True,'approval_id':'',
        'allowed_operations':['save-as-draft','readback'],'enabled':False,'budget_average_myr_day':35,
        'approval_status':'consumed_for_exact_draft_only','actual_action_allowed':True,
        'exact_paused_draft_exception':True,'promotion_activation_or_payment_authority':False}.items()),
        'original issued permit identity differs')
    path=_attempt_path(root,context['execution_key'])
    require(not path.is_symlink() and path.is_file(), 'original occupied attempt required; never Save to repair evidence')
    attempts=w.read_jsonl(path)
    require(len(attempts)==1, 'one exact original occupied attempt required')
    attempt=attempts[0]
    require(all(attempt.get(k)==v for k,v in {
        'state':'reserved_before_native_effect','task_id':TASK,'action_id':ACTION,'account_id':ACCOUNT,
        'campaign_id':intent['campaign_id'],'decision_id':decision_id,'draft_admission':envelope,
        'actual_save_or_readback_claimed':False}.items()), 'original occupied attempt identity differs')
    issued=w._parse_observed_at(grant.get('checked_at'))
    reserved=w._parse_observed_at(attempt.get('reserved_at'))
    require(issued is not None and reserved is not None and issued<=reserved<=dt.datetime.now(dt.timezone.utc),
            'original permit must precede reservation; future or reversed attempts refuse')
    _fresh_at(grant.get('checked_at'),reserved)
    for name in ('live_before','legal_channel'):
        observed=document(root,intent[name]).get('observed_at')
        _fresh_at(observed,issued);_fresh_at(observed,reserved)
    _fresh_at(context['browser_identity']['observed_at'],issued)
    _fresh_at(context['browser_identity']['observed_at'],reserved)
    return attempt


def validate_readback_projection(root, request_pin, after_pin, *, envelope, decision_id):
    """Read an original occupied effect after delay; never renew a write permit."""
    require(isinstance(envelope,dict) and envelope.get('request')==request_pin,
            'original frozen request/envelope required for post-effect readback')
    staged=_release_sources(root,envelope);intent=staged['intent']
    attempt=_reserved_original_attempt(root,staged,envelope,decision_id)
    expected=document(root,intent['desired_state']);actual=document(root,after_pin)
    fresh(actual.get('observed_at'))
    require(w._parse_observed_at(attempt['reserved_at'])<=w._parse_observed_at(actual['observed_at']),
            'post-effect observation must follow original reservation')
    for key in ('account_id','login_email','source_project_id','source_thread_id'):
        require(actual.get(key)==expected.get(key), 'readback account/executor differs')
    campaign=copy.deepcopy(actual.get('campaign',{}));groups=campaign.get('groups',[])
    require(len(groups)==3, 'actual three groups/six ads required')
    # Only server-created IDs of the NEW group/ads may differ from desired.
    ids=[campaign.get('id')]
    for group in groups:
        ids.append(group.get('id'));ids += [ad.get('id')for ad in group.get('ads',[])]
    require(len(ids)==10 and len(set(ids))==10 and all(isinstance(x,str)and x.strip()for x in ids),
            'actual unique campaign/group/ad object IDs required')
    groups[-1]['id']=None
    for ad in groups[-1].get('ads',[]):ad['id']=None
    require(campaign==expected['campaign'], 'readback drift: protect original two groups/four ads and every retained field')
    require(actual.get('native_evidence'), 'actual native readback evidence pins required')
    for pin in actual['native_evidence']:require(w.file_digest(root,pin['path'])==pin,'native readback bytes changed')
    return {'state':'FULL_PROJECTION_MATCH_ONLY','native_save_or_business_completion_claimed':False,
            'after':after_pin,'request':request_pin,'original_decision_id':decision_id,
            'original_reserved_at':attempt['reserved_at'],
            'protected_objects_sha256':staged['protected_objects_sha256']}


# Current-four preparation is separate from the unchanged residential ACTION.
# These functions never issue a release/permit or execute a browser action.
EXISTING_FOUR_OPERATION = 'existing-four-settings-save/readback'
EXISTING_FOUR_ACTION = 'chatgpt-existing-paused-draft-save-readback'
EXISTING_FOUR_CAMPAIGN = 'cmpn_290f58568b5481a1aef7c89b6a7fb7e0'
EXISTING_FOUR_IDS = {
    'ZH_WHOLE_HOME': ('adgrp_7b14d9f4ac6881a1a50e3c70c28fd82b',
        {'ad_f56b6e3d7240819e9252deee4e22ee7e', 'ad_a0f9b8fa937c819294743834554da5f0'}),
    'ZH_KITCHEN': ('adgrp_de485cd9f3ac81a19b7716356eacefbf',
        {'ad_be787a0943b08194a9a9a38e48f78c02', 'ad_1f8923eca59081a09060225baf217f4c'})}


def existing_four_visible_fields():
    """The real UI projection contract; local hashes are never server CAS."""
    return {
        'identity': ['account_id', 'login_email', 'source_project_id', 'source_thread_id',
                     'browser_id', 'tab_id', 'profile_name', 'extension_instance_id'],
        'campaign': ['id', 'name', 'status', 'enabled', 'budget', 'creative_enabled'],
        'original_objects': 'exact two groups/four ads: id/name/status/enabled plus every observed field',
        'changed_controls': ['budget type/currency/amount', 'creative enhancement',
                             'actual included/excluded locations', 'start/end/account timezone'],
        'write_impact': 'All observed fields in actual affected controls/objects; full editor needs all included fields',
        'not_platform_hard_fields': ['revision', 'etag', 'server_CAS', 'hidden_backend_tree'],
        'local_projection_sha256_is_server_CAS': False,
        'not_provided_is_not_an_empty_value': True,
        'read_only_preparation_grants_no_permission': True}


def prepare_existing_four(root, request_pin):
    """Validate a precise original-four request without borrowing residential permission.

    Fresh UI evidence and an exact affected-control map are necessary. This is
    intentionally preparation: normal parent action/source/independent decision,
    a separately bound execution stage and an unused permit still govern effects.
    """
    current_parent(root)
    request = document(root, request_pin)
    require(set(request) == {'task_id', 'department', 'scope', 'operation', 'action_id',
            'account_id', 'login_email', 'source_project_id', 'source_thread_id',
            'before', 'desired', 'channel', 'control_map'}, 'exact original-four request schema required')
    require(all(request.get(k) == v for k, v in {
        'task_id': TASK, 'department': ROLE, 'scope': SCOPE,
        'operation': EXISTING_FOUR_OPERATION, 'action_id': EXISTING_FOUR_ACTION,
        'account_id': ACCOUNT, 'login_email': EMAIL,
        'source_project_id': PROJECT, 'source_thread_id': THREAD}.items()),
        'original-four parent/account/owner/action only; no residential or activation substitution')
    before, desired, channel, controls = [document(root, request[k])
                                         for k in ('before', 'desired', 'channel', 'control_map')]
    for value in (before, desired, channel):
        require(all(value.get(k) == request[k] for k in
                    ('account_id', 'login_email', 'source_project_id', 'source_thread_id')),
                'all original-four projections must retain original account and executor')
    for value in (before, channel, controls):
        fresh(value.get('observed_at'))
        require(isinstance(value.get('native_evidence'), list) and value['native_evidence'],
                'fresh real control/native evidence required')
        for pin in value['native_evidence']:
            require(w.file_digest(root, pin.get('path', '')) == pin, 'original-four native bytes changed')
    browser = _native_browser_identity(root, before, channel)
    fresh(browser['observed_at'])
    require(channel.get('kind') == 'authenticated_existing_browser'
            and channel.get('origin') == 'https://ads.openai.com'
            and channel.get('terms_acceptance') is False and channel.get('publish') is False
            and channel.get('activate') is False and channel.get('payment') is False,
            'settings preparation cannot accept Terms, publish, activate or pay')
    require(before.get('state_source') == 'saved_native_readback',
            'saved native observation required; unsaved wizard is not saved state')
    campaign, target = before.get('campaign', {}), desired.get('campaign', {})
    require(campaign.get('id') == EXISTING_FOUR_CAMPAIGN and campaign.get('name') == CAMPAIGN
            and campaign.get('status') == 'Draft' and campaign.get('enabled') is False,
            'exact existing original campaign Draft/OFF required')
    require(type(campaign.get('creative_enabled')) is bool,
            'actual saved creative flag required; On cannot be relabelled OFF')
    budget = campaign.get('budget', {})
    require(set(budget) == {'type', 'currency', 'amount'} and budget['currency'] == 'MYR'
            and budget['type'] in {'average_daily', 'campaign_total'}
            and type(budget['amount']) in {int, float} and budget['amount'] >= 0,
            'actual saved budget type and amount required, not inferred daily35')
    groups = campaign.get('groups', [])
    require(len(groups) == 2 and {g.get('name') for g in groups} == set(EXISTING_FOUR_IDS),
            'only original two groups, no residential addition')
    for group in groups:
        group_id, ad_ids = EXISTING_FOUR_IDS[group['name']]
        require(group.get('id') == group_id and group.get('status') == 'Draft'
                and group.get('enabled') is False and len(group.get('ads', [])) == 2
                and {a.get('id') for a in group['ads']} == ad_ids
                and {a.get('name') for a in group['ads']} == EXISTING_AD_NAMES[group['name']],
                'exact original group and four ad identities required')
        require(all(a.get('status') == 'Draft' and a.get('enabled') is False for a in group['ads']),
                'all original four ads must remain Draft/OFF in settings preparation')
    permitted = {'budget', 'creative_enabled', 'locations', 'schedule'}
    changed = {k for k in set(campaign) | set(target) if campaign.get(k) != target.get(k)}
    require(changed and changed <= permitted and all(k in target for k in changed),
            'only precise current campaign settings may change; observed fields cannot disappear')
    require(target.get('groups') == groups and target.get('budget') ==
            {'type': 'average_daily', 'currency': 'MYR', 'amount': 35}
            and target.get('creative_enabled') is False,
            'one shared average daily35 and saved creativeOFF target; protect all four ads')
    require(isinstance(target.get('locations'), dict)
            and set(target['locations'].get('include', [])) == {'Kuala Lumpur', 'Selangor'}
            and isinstance(target['locations'].get('exclude'), list)
            and isinstance(target.get('schedule'), dict)
            and all(target['schedule'].get(k) for k in ('start', 'end', 'timezone')),
            'exact current locations, exclusions and future schedule required from original A1 decision')
    schedule = target['schedule']
    start, end = w._parse_observed_at(schedule['start']), w._parse_observed_at(schedule['end'])
    require(start is not None and end is not None and dt.datetime.now(dt.timezone.utc) < start < end,
            'future ordered explicit schedule required; expired dates cannot transfer')
    require(set(controls.get('fields', {})) == changed, 'each changed control must have an exact impact map')
    for field, control in controls['fields'].items():
        require(isinstance(control, dict) and control.get('label') and control.get('route')
                and control.get('effect') == 'explicit_save'
                and control.get('mode') in {'single_field', 'bounded_fields', 'whole_visible_editor'}
                and isinstance(control.get('writes'), list) and control['writes']
                and len(set(control['writes'])) == len(control['writes'])
                and field in control['writes'] and set(control['writes']) <= set(campaign) & set(target)
                and field in campaign and control.get('observed_value') == campaign[field]
                and control.get('object_id') == campaign['id'],
                'actual control and every affected observed field required; unknown/autosave effects rejected')
        if control['mode'] == 'single_field':
            require(control['writes'] == [field], 'single-field control cannot hide broader writes')
        else:
            require(control.get('included_fields') == control['writes']
                    and control.get('visible_fields_projection') ==
                    {key: campaign[key] for key in control['writes']},
                    'full actual included UI projection required; no invented hidden backend tree')
        if field == 'budget':
            require(control.get('supported_type') == 'average_daily',
                    'campaign-total popup is not a supported daily-budget control')
    return {'state': 'EXISTING_FOUR_PREPARED_NOT_AUTHORIZED', 'request': request_pin,
        'request_sha256': request_pin['sha256'], 'browser_identity': browser,
        'changed_fields': sorted(changed), 'protected_objects_sha256': w.sha256_value(groups),
        'local_before_projection_sha256': w.sha256_value(campaign), 'server_CAS_provided': False,
        'normal_parent_action_request': {k: request[k] for k in
            ('task_id', 'department', 'action_id', 'scope')},
        'separate_execution_stage_required': True,
        'next_owner': REVIEWER, 'actual_action_allowed': False, 'external_permission_issued': False,
        'writes_performed': False, 'residential_permission_reused': False}


# A protected editor open is an effect, not an unrestricted read or a Save.
# Keep the residential and settings contracts above intact. The normal policy
# entry already routes an exact request/release envelope through this module.
INSPECTION_STAGE = 'fc-20261024-chatgpt-existing-four-inspection-admission-v1'
INSPECTION_SCOPE = 'project:flashcast:chatgpt-fe689:existing-four-inspection-admission:20261024:v1'
INSPECTION_VERSION = 'chatgpt-existing-four-protected-inspection-admission-v1-20261024'
INSPECTION_OPERATION = 'open_original_Edit_Campaign_once_capture_visible_fields_leave'
INSPECTION_CONTRACT = {
    'path': 'logs/handoffs/2026-10-24-chatgpt-priority-watch-v1/HQ-V76-exact-intake-and-execution-stage-v1/COMPLETE-BOUNDED-EXISTING-FOUR-INSPECTION-GOAL-v1.json',
    'sha256': 'fa294554eed36ef6a7e0a0483be4a5034160994b9b8e6f181a129a4875cc4d96',
    'size': 7656}
INSPECTION_HQ_DECISION = {
    'path': 'logs/handoffs/2026-10-24-chatgpt-priority-watch-v1/HQ-V75-exact-intake-and-protected-inspection-decision-v1/HQ-precise-original-editor-inspection-decision-v1.json',
    'sha256': 'b88beba5c74fc2031df7cffe365762c4643d0c3f3257b3f2e8096fc00a184547',
    'size': 2979}
INSPECTION_FORBIDDEN = ['input', 'toggle', 'change_budget_type', 'Next', 'Back',
    'Close', 'Save', 'Publish', 'Enable', 'Terms', 'create', 'clone']
INSPECTION_ALLOWED = ['open_original_Edit_Campaign_once', 'capture_visible_fields_and_save_state',
    'leave_editor_at_position']


def inspection_fields():
    """Fields actually needed before opening; missing settings are outputs."""
    return {'operation': INSPECTION_OPERATION, 'task_id': TASK,
        'action_id': EXISTING_FOUR_ACTION, 'action_class': 'ads_write', 'scope': SCOPE,
        'department': ROLE, 'technical_stage': INSPECTION_STAGE,
        'account_id': ACCOUNT, 'campaign_id': EXISTING_FOUR_CAMPAIGN,
        'stable_browser_identity': {'profile_name': BROWSER_PROFILE,
                                    'extension_instance_id': BROWSER_EXTENSION},
        'before': ['saved native campaign list Draft/OFF', 'original seven object identities',
                   'current exact profile/extension/tab/account inventory',
                   'observed Actions > Edit Campaign control and its native evidence'],
        'inspection_outputs': ['all actually visible settings', 'Saved/Unsaved/unknown state',
            'Daily control or NOT_PROVIDED', 'enhancement or NOT_PROVIDED',
            'include/exclude geography or NOT_PROVIDED', 'dates/timezone or NOT_PROVIDED'],
        'backup_limit': 'Exact observed list/identity/control bytes only; not unseen settings',
        'rollback_limit': 'Unknown opening effect: preserve position, read back and hold; no compensating UI mutation',
        'allowed_operations': INSPECTION_ALLOWED, 'forbidden_operations': INSPECTION_FORBIDDEN,
        'server_CAS_required': False, 'local_projection_is_server_CAS': False,
        'actual_action_allowed': False, 'external_permission_issued': False}


def prepare_inspection(root, request_pin, *, fresh_required=True):
    """Validate the frozen narrow intent. This never issues a permit."""
    parent = current_parent(root)
    request = document(root, request_pin)
    required = {'task_id', 'department', 'action_id', 'action_class', 'scope', 'operation',
        'technical_stage', 'source_project_id', 'source_thread_id', 'account_id',
        'login_email', 'campaign_id', 'hq_decision', 'before', 'channel', 'preflight'}
    require(set(request) == required, 'exact protected-inspection request fields required')
    identity = {'task_id': TASK, 'department': ROLE, 'action_id': EXISTING_FOUR_ACTION,
        'action_class': 'ads_write', 'scope': SCOPE, 'operation': INSPECTION_OPERATION,
        'technical_stage': INSPECTION_STAGE, 'source_project_id': PROJECT,
        'source_thread_id': THREAD, 'account_id': ACCOUNT, 'login_email': EMAIL,
        'campaign_id': EXISTING_FOUR_CAMPAIGN, 'hq_decision': INSPECTION_HQ_DECISION}
    require(all(request.get(k) == v for k, v in identity.items()),
            'exact original-four protected-open identity required; no Save or residential permission')
    declared = [a for a in parent['goal_delivery'].get('required_execution_actions', [])
                if all(a.get(k) == request[k] for k in ('department', 'action_id', 'action_class', 'scope'))]
    require(len(declared) == 1, 'one unchanged original parent action required')
    contract, decision = document(root, INSPECTION_CONTRACT), document(root, INSPECTION_HQ_DECISION)
    require(contract.get('task_id') == INSPECTION_STAGE and contract.get('parent_task_id') == TASK
            and contract.get('primary_owner') == 'system-development'
            and contract.get('responsible_assistant') == REVIEWER
            and contract.get('authorized_scope') == [INSPECTION_SCOPE]
            and contract.get('production_write_allowed') is False
            and contract.get('external_permission_issued') is False
            and INSPECTION_HQ_DECISION in contract.get('existing_results', []),
            'actual frozen technical goal and pinned HQ decision required')
    require(all(decision.get(k) == v for k, v in {'task_id': TASK, 'scope': SCOPE,
        'decision_owner': 'operations', 'professional_executor': ROLE,
        'sole_assistant': REVIEWER, 'account_id': ACCOUNT,
        'campaign_id': EXISTING_FOUR_CAMPAIGN, 'external_execution_permission_issued': False}.items()),
        'original HQ decision is not an execution permit')
    before, channel, preflight = [document(root, request[k]) for k in ('before', 'channel', 'preflight')]
    for projection in (before, channel):
        require(all(projection.get(k) == request[k] for k in
            ('account_id', 'login_email', 'source_project_id', 'source_thread_id')),
            'original Paid2/account identity in every observation required')
    require(before.get('state_source') == 'saved_native_list'
            and before.get('unobserved_settings') == 'NOT_PROVIDED',
            'list is not a complete editor backup; unseen settings must remain unprovided')
    campaign = before.get('campaign', {})
    require(all(campaign.get(k) == v for k, v in {'id': EXISTING_FOUR_CAMPAIGN,
        'name': CAMPAIGN, 'status': 'Draft', 'enabled': False}.items()),
        'same original native Draft/OFF campaign required')
    groups = before.get('original_objects', [])
    require(len(groups) == 2 and {x.get('name') for x in groups} == set(EXISTING_FOUR_IDS),
            'original two groups/four ads only')
    for group in groups:
        gid, ads = EXISTING_FOUR_IDS[group['name']]
        require(group.get('id') == gid and group.get('enabled') is False
                and group.get('status') == 'Draft' and len(group.get('ads', [])) == 2
                and {a.get('id') for a in group['ads']} == ads
                and {a.get('name') for a in group['ads']} == EXISTING_AD_NAMES[group['name']]
                and all(a.get('enabled') is False and a.get('status') == 'Draft' for a in group['ads']),
                'all original seven object identities and pause states required')
    browser = _native_browser_identity(root, before, channel)
    require(channel.get('kind') == 'authenticated_existing_browser'
            and channel.get('origin') == 'https://ads.openai.com'
            and channel.get('control') == 'Actions > Edit Campaign'
            and channel.get('object_id') == EXISTING_FOUR_CAMPAIGN
            and channel.get('allowed_operations') == INSPECTION_ALLOWED
            and channel.get('forbidden_operations') == INSPECTION_FORBIDDEN
            and all(channel.get(k) is False for k in
                ('terms_acceptance', 'publish', 'activate', 'payment', 'save', 'input', 'toggle')),
            'observed original Edit Campaign only; no broader operation')
    pins = [request_pin, INSPECTION_CONTRACT, INSPECTION_HQ_DECISION, request['before'],
            request['channel'], request['preflight']]
    for name in ('facts', 'self_check', 'backup', 'rollback'):
        pin = preflight.get(name); value = document(root, pin); pins.append(pin)
        require(all(value.get(k) == request[k] for k in
                    ('task_id', 'department', 'action_id', 'action_class', 'scope', 'operation')),
                'exact inspection-specific facts/selfcheck/backup/rollback required')
        require(value.get('before') == request['before'] and value.get('channel') == request['channel'],
                'inspection evidence must refer to these actual observations')
        if name == 'self_check':
            require(value.get('status') == 'PASS' and value.get('risk_level') == 'R2'
                    and value.get('opening_may_have_effect') is True
                    and value.get('permitted_UI_steps') == INSPECTION_ALLOWED
                    and value.get('forbidden_UI_steps') == INSPECTION_FORBIDDEN,
                    'real bounded R2 opening self-check required')
        elif name == 'backup':
            require(value.get('coverage') == 'observed_list_identity_and_control_only'
                    and value.get('full_settings_backup') is False,
                    'observed bytes cannot be claimed as unseen settings backup')
        elif name == 'rollback':
            require(value.get('mode') == 'readback_and_hold_without_compensating_UI'
                    and value.get('unknown_effect_retry') is False
                    and value.get('full_settings_rollback_available') is False,
                    'truthful opening rollback limit and no blind reopen required')
    require(preflight.get('risk_level') == 'R2', 'accurate protected-opening risk required')
    if fresh_required:
        for value in (before, channel): fresh(value.get('observed_at'))
        fresh(browser['observed_at'])
    for value in (before, channel):
        pins.extend(value['native_evidence'])
    return {'state': 'PROTECTED_INSPECTION_PREPARED_NOT_AUTHORIZED', 'request': request_pin,
        'intent': request, 'guards': pins, 'browser_identity': browser,
        'execution_key': w.sha256_value([TASK, ROLE, ACCOUNT, EXISTING_FOUR_CAMPAIGN,
                                        EXISTING_FOUR_ACTION, INSPECTION_OPERATION]),
        'actual_action_allowed': False, 'external_permission_issued': False}


def _inspection_adopted_stage(root):
    """Use the actual normal accepted/adopted stage, never a caller release flag."""
    import goal_delivery_runtime as g
    stage = g.restore_goal(root, w.read_json(w.snapshot_path(root, INSPECTION_STAGE)))
    goal = stage.get('goal_delivery', {})
    require(stage.get('goal_contract') == INSPECTION_CONTRACT
            and goal.get('parent_task_id') == TASK and goal.get('primary_owner') == 'system-development'
            and goal.get('producer_departments') == ['system-development']
            and goal.get('responsible_assistant') == REVIEWER
            and goal.get('authorized_scope') == [INSPECTION_SCOPE]
            and goal.get('authorization_pin') == ADOPTION_AUTH,
            'original technical stage/independent A1/authorization required')
    rows, bad = w._validate_receipt_chain(root, INSPECTION_STAGE)
    require(not bad and not w.validate_workflow_events(root, INSPECTION_STAGE), 'intact original stage chains required')
    accepted = w.goal_completion_subject(root, stage, rows,
        {'mode': 'latest_exact_accepted_result', 'producer_department': 'system-development', 'scope': INSPECTION_SCOPE})
    require(accepted.get('state') == 'PROVEN'
            and accepted.get('identity', {}).get('candidate_version') == INSPECTION_VERSION,
            'normal exact independent inspection-source acceptance required')
    manifest = document(root, accepted['candidate'])
    require(manifest.get('task_id') == INSPECTION_STAGE
            and manifest.get('department') == 'system-development'
            and manifest.get('responsible_assistant') == REVIEWER
            and manifest.get('scope') == INSPECTION_SCOPE
            and manifest.get('candidate_version') == INSPECTION_VERSION
            and manifest.get('candidate_fingerprint') == accepted.get('source_fingerprint')
            and [c.get('path') for c in manifest.get('changes', [])] == ['tools/chatgpt_fe689_draft_admission.py'],
            'exact independently reviewed single-module implementation required')
    requirement = next(x for x in document(root, INSPECTION_CONTRACT)['completion_requirements']
                       if x['requirement_id'] == 'existing-four-inspection-source-adopted')
    effect = w.goal_typed_completion_proof(root, stage, rows, requirement, accepted)
    require(effect.get('state') == 'PROVEN',
            'actual normal completed A1 source adoption required: ' + str(effect.get('reason', effect.get('state'))))
    return {'accepted': accepted, 'proof': effect,
        'guards': [accepted['candidate'], *effect['evidence'],
            w.file_digest(root, 'tools/chatgpt_fe689_draft_admission.py'),
            w.file_digest(root, str(w.snapshot_path(root, INSPECTION_STAGE).relative_to(root)))]}


def inspection_context(root, envelope):
    require(isinstance(envelope, dict) and set(envelope) == {'request', 'release'},
            'exact protected-open request/release pins required')
    context = prepare_inspection(root, envelope['request'])
    stage = _inspection_adopted_stage(root)
    release = document(root, envelope['release'])
    require(set(release) == {'technical_source_manifest', 'parent_decision_record_id'}
            and release['technical_source_manifest'] == stage['accepted']['candidate'],
            'release must retain actual independently adopted stage candidate')
    from scoped_candidate_adoption import _committed
    events = w._result_handoff_rows(root, TASK)
    chosen = [x for x in events if x.get('record_id') == release['parent_decision_record_id']]
    require(len(chosen) == 1, 'one actual original A1 inspection decision required')
    decision = chosen[0]
    require(all(decision.get(k) == v for k, v in {'event': 'controller_decision',
        'decision': 'continue', 'decision_actor': REVIEWER, 'coordinator_role': REVIEWER,
        'next_owner': ROLE, 'next_action': 'authorize-exact-protected-open-inspection'}.items())
        and envelope['request'] in decision.get('evidence', [])
        and INSPECTION_HQ_DECISION in decision.get('evidence', [])
        and stage['accepted']['candidate'] in decision.get('evidence', []),
        'committed original A1 decision on this exact effect/request/source required')
    _committed(root, decision)
    source = document(root, decision['outbox'])
    require(source.get('task_id') == TASK and source.get('department') == ROLE
            and source.get('inspection_admission_request') == envelope['request'],
            'real original Paid2 readiness result required')
    same = lambda row: all(row.get(k) == decision.get(k) for k in
                          ('task_id', 'sender_department', 'candidate_version', 'result_sha256'))
    queued = [x for x in events if same(x) and x.get('event') == 'notification_queued']
    received = [x for x in events if same(x) and x.get('event') == 'controller_received']
    require(len(queued) == len(received) == 1
            and received[0].get('decision_actor') == REVIEWER
            and events.index(queued[0]) < events.index(received[0]) < events.index(decision),
            'original queued, committed intake and independent decision order required')
    _committed(root, received[0]); w._validate_goal_completed_result(root, queued[0], THREAD)
    times = [w._parse_observed_at(x.get('created_at')) for x in (queued[0], received[0], decision)]
    require(all(x is not None for x in times)
            and times == sorted(times) and times[-1] <= dt.datetime.now(dt.timezone.utc),
            'real original request/intake/decision chronology required')
    binding = w.department_registry(root)[ROLE]['chat_binding']
    require(w._chat_binding_healthy(binding, verification_ttl_hours=26, now=dt.datetime.now(dt.timezone.utc))
            and w.department_registry(root)[ROLE].get('new_dispatch_enabled') is True
            and 'chatgpt-ads' in w.department_registry(root)[ROLE].get('approved_subskills', []),
            'current healthy original Paid2 and registered Ads method required')
    context['guards'] += [envelope['release'], decision['outbox'], *stage['guards'],
        w.file_digest(root, str(w.result_handoff_path(root, TASK).relative_to(root))),
        w.file_digest(root, 'data/department-registry.json')]
    return {**context, 'state': 'NORMAL_PROTECTED_INSPECTION_CONTEXT',
        'issuer_department': REVIEWER, 'parent_decision_record_id': decision['record_id'],
        'technical_source_manifest': stage['accepted']['candidate']}


def _inspection_attempt_path(root, key):
    return Path(root)/'logs/exact-chatgpt-inspection-attempts'/(key+'.jsonl')


def _inspection_fresh_sources(root, context, checked_at=None):
    moment = checked_at or dt.datetime.now(dt.timezone.utc)
    for name in ('before', 'channel'):
        _fresh_at(document(root, context['intent'][name]).get('observed_at'), moment)
    _fresh_at(context['browser_identity']['observed_at'], moment)


def _inspection_original_grant(root, context, envelope, decision_id):
    grants = [x for x in w.read_jsonl(Path(root)/w.POLICY_DECISIONS)
              if x.get('inspection_key') == context['execution_key'] and x.get('status') == 'allow']
    exact = {'decision_id': decision_id, 'task_id': TASK, 'department': ROLE,
        'action_id': EXISTING_FOUR_ACTION, 'action_class': 'ads_write', 'scope': SCOPE,
        'source_project_id': PROJECT, 'payload_sha256': envelope['request']['sha256'],
        'account_id': ACCOUNT, 'campaign_id': EXISTING_FOUR_CAMPAIGN,
        'draft_admission': envelope, 'operation': INSPECTION_OPERATION,
        'technical_stage': INSPECTION_STAGE, 'issuer_department': REVIEWER,
        'consume_approval': True, 'approval_id': '', 'skill': 'chatgpt-ads',
        'allowed_operations': INSPECTION_ALLOWED, 'forbidden_operations': INSPECTION_FORBIDDEN,
        'actual_action_allowed': True, 'approval_status': 'consumed_for_exact_protected_open_only',
        'promotion_activation_or_payment_authority': False, 'settings_Save_authority': False}
    require(len(grants) == 1 and all(grants[0].get(k) == v for k, v in exact.items()),
            'one actual exact protected-open permit required; old or broader permits cannot transfer')
    return grants[0]


def inspection_policy(root, requested, envelope):
    context = inspection_context(root, envelope); request = context['intent']
    require(all(requested.get(k) == request[k] for k in
                ('task_id', 'department', 'action_id', 'action_class', 'scope', 'source_project_id'))
            and requested.get('payload_sha256') == envelope['request']['sha256']
            and requested.get('skill') == 'chatgpt-ads' and requested.get('approval_id') == ''
            and type(requested.get('consume_approval')) is bool,
            'exact original protected-inspection policy identity and request SHA required')
    require(not any(requested.get(k) for k in ('target_project_id', 'target_department',
        'target_thread_id', 'target_thread_title', 'target_cwd', 'target_sidebar_section_id',
        'target_automation_status', 'retry_blocked_execution_receipt_id')),
        'no alternate target, retry or old permit channel')
    key = context['execution_key']
    result = {**requested, 'draft_admission': envelope, 'inspection_key': key,
        'operation': INSPECTION_OPERATION, 'technical_stage': INSPECTION_STAGE,
        'issuer_department': REVIEWER, 'parent_decision_record_id': context['parent_decision_record_id'],
        'account_id': ACCOUNT, 'campaign_id': EXISTING_FOUR_CAMPAIGN,
        'allowed_operations': INSPECTION_ALLOWED, 'forbidden_operations': INSPECTION_FORBIDDEN,
        'approval_basis': 'actual_independently_adopted_inspection_source_and_original_A1_exact_effect_decision',
        'checked_at': w.utc_timestamp(), 'actual_action_allowed': False,
        'promotion_activation_or_payment_authority': False, 'settings_Save_authority': False}
    with w.workflow_lock(root):
        for pin in context['guards']:
            require(w.file_digest(root, pin['path']) == pin, 'protected-inspection source changed before permit')
        _inspection_fresh_sources(root, context)
        grants = [x for x in w.read_jsonl(Path(root)/w.POLICY_DECISIONS)
                  if x.get('inspection_key') == key and x.get('status') == 'allow']
        require(not grants and not _inspection_attempt_path(root, key).exists(),
                'inspection already issued or attempted; read actual effect, never reopen')
        if not requested['consume_approval']:
            return {**result, 'status': 'preflight_ready_not_a_permit'}, []
        result.update(status='allow', decision_id='pol-'+w.sha256_value([key, result['checked_at']])[:20],
            approval_status='consumed_for_exact_protected_open_only', actual_action_allowed=True)
        w.append_jsonl_locked(Path(root)/w.POLICY_DECISIONS, result)
    return result, [Path(root)/w.POLICY_DECISIONS]


def reserve_inspection(root, envelope, decision_id):
    """Durably occupy the original operation BEFORE any UI effect; no reset API."""
    context = inspection_context(root, envelope); key = context['execution_key']
    with w.workflow_lock(root):
        for pin in context['guards']:
            require(w.file_digest(root, pin['path']) == pin, 'inspection source changed before occupancy')
        grant = _inspection_original_grant(root, context, envelope, decision_id)
        fresh(grant.get('checked_at')); _inspection_fresh_sources(root, context)
        path = _inspection_attempt_path(root, key)
        require(not path.exists(), 'reserved/successful/unknown effect must not be retried')
        row = {'schema': 'original-chatgpt-protected-inspection-occupancy/v1',
            'state': 'reserved_before_native_effect', 'task_id': TASK, 'department': ROLE,
            'action_id': EXISTING_FOUR_ACTION, 'operation': INSPECTION_OPERATION,
            'scope': SCOPE, 'account_id': ACCOUNT, 'campaign_id': EXISTING_FOUR_CAMPAIGN,
            'decision_id': decision_id, 'draft_admission': envelope,
            'technical_source_manifest': context['technical_source_manifest'],
            'reserved_at': w.utc_timestamp(), 'effect_outcome': 'NOT_OBSERVED',
            'retry_allowed': False, 'opening_or_saved_effect_claimed': False}
        w.append_jsonl_locked(path, row)
    return {'reservation': row, 'reservation_pin': w.file_digest(root, str(path.relative_to(root))),
        'next_owner': ROLE, 'next_native_operation': INSPECTION_OPERATION,
        'allowed_operations': INSPECTION_ALLOWED, 'forbidden_operations': INSPECTION_FORBIDDEN,
        'unknown_effect_rule': 'Read current original editor and report; never issue or open again',
        'actual_UI_execution_performed': False}


def inspection_status(root):
    """An occupied effect stays visible even when later sources are unavailable."""
    current_parent(root)
    key = w.sha256_value([TASK, ROLE, ACCOUNT, EXISTING_FOUR_CAMPAIGN,
                          EXISTING_FOUR_ACTION, INSPECTION_OPERATION])
    path = _inspection_attempt_path(root, key)
    if not path.exists():
        return {'state': 'NO_ATTEMPT', 'retry_authorized': False,
                'next_owner': REVIEWER, 'actual_UI_execution_performed': False}
    require(not path.is_symlink(), 'original inspection occupancy cannot be aliased')
    rows = w.read_jsonl(path)
    require(len(rows) == 1 and all(rows[0].get(k) == v for k, v in {
        'schema': 'original-chatgpt-protected-inspection-occupancy/v1',
        'state': 'reserved_before_native_effect', 'task_id': TASK, 'department': ROLE,
        'action_id': EXISTING_FOUR_ACTION, 'operation': INSPECTION_OPERATION, 'scope': SCOPE,
        'account_id': ACCOUNT, 'campaign_id': EXISTING_FOUR_CAMPAIGN, 'retry_allowed': False}.items()),
        'one intact original inspection occupancy required')
    envelope = rows[0].get('draft_admission', {})
    context = prepare_inspection(root, envelope.get('request'), fresh_required=False)
    grant = _inspection_original_grant(root, context, envelope, rows[0].get('decision_id'))
    issued, reserved = (w._parse_observed_at(value) for value in
                       (grant.get('checked_at'), rows[0].get('reserved_at')))
    require(issued is not None and reserved is not None
            and issued <= reserved <= dt.datetime.now(dt.timezone.utc),
            'original issued permit must precede actual occupancy')
    _fresh_at(grant['checked_at'], reserved)
    _inspection_fresh_sources(root, context, issued)
    _inspection_fresh_sources(root, context, reserved)
    return {'state': 'OCCUPIED_EFFECT_REQUIRES_NATIVE_READBACK', 'reservation': rows[0],
        'retry_authorized': False, 'next_owner': ROLE,
        'next_action': 'Read current original editor; capture visible settings and Saved/Unsaved/unknown state; leave position',
        'actual_UI_execution_or_success_not_inferred': True}


def inspection_main():
    """Executable normal policy + occupancy integration; no browser driver or Ads calls."""
    import argparse
    parser = argparse.ArgumentParser(description='Exact original-four protected inspection')
    parser.add_argument('command', choices=['inspection-fields', 'inspection-prepare',
        'inspection-context', 'inspection-policy-check', 'inspection-issue',
        'inspection-reserve', 'inspection-status', 'unsaved-fields', 'unsaved-prepare',
        'unsaved-context', 'unsaved-policy-check', 'unsaved-issue', 'unsaved-reserve',
        'unsaved-status', 'unsaved-readback', 'unsaved-source-chain'])
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--input', type=Path)
    parser.add_argument('--decision-id')
    args = parser.parse_args(); root = args.root.resolve()
    if args.command.startswith('unsaved-'):
        value = unsaved_command(root, args)
        print(json.dumps(value, ensure_ascii=False, indent=2)); return
    if args.command == 'inspection-fields': value = inspection_fields()
    elif args.command == 'inspection-status': value = inspection_status(root)
    else:
        require(args.input is not None, 'project-local exact input required')
        relative = str(args.input.resolve().relative_to(root)) if args.input.is_absolute() else str(args.input)
        pin = w.file_digest(root, relative)
        if args.command == 'inspection-prepare': value = prepare_inspection(root, pin)
        else:
            envelope = document(root, pin)
            if args.command == 'inspection-context': value = inspection_context(root, envelope)
            elif args.command == 'inspection-reserve': value = reserve_inspection(root, envelope, args.decision_id)
            else:
                request = document(root, envelope['request'])
                # The same normal workflow policy entry used by callers. No
                # caller allow/source-only flag or generic rotation exception.
                value, _ = w.policy_check(root, **{k: request[k] for k in
                    ('task_id', 'department', 'action_id', 'action_class', 'scope', 'source_project_id')},
                    skill='chatgpt-ads', payload_sha256=envelope['request']['sha256'],
                    consume_approval=args.command == 'inspection-issue', draft_admission=envelope)
    print(json.dumps(value, ensure_ascii=False, indent=2))


UNSAVED_STAGE = 'fc-20261024-chatgpt-unsaved-existing-four-settings-save-admission-v1'
UNSAVED_SCOPE = 'project:flashcast:chatgpt-fe689:unsaved-existing-four-settings-save:20261024:v1'
UNSAVED_VERSION = 'chatgpt-unsaved-existing-four-settings-save-admission-v2-20261024'
UNSAVED_OPERATION = 'edit_existing_unsaved_four_settings_save_as_draft_readback'
UNSAVED_DATE_QUESTION = {'path': 'logs/handoffs/2026-10-24-chatgpt-unsaved-existing-four-settings-save-admission-v1/system-development-v1/intake/ACTUAL-ORIGINAL-HQ-DATE-QUESTION-NATIVE-v1.json',
    'sha256': '1deb133919205bc148d597c02735f4e76d8265b7c9b3f816f2e789479d0c38a0', 'size': 2358}
UNSAVED_CONTRACT = {'path': 'logs/handoffs/2026-10-24-chatgpt-priority-watch-v1/HQ-A1-V80-actual-intake-and-unsaved-settings-next-v1/COMPLETE-BOUNDED-UNSAVED-EXISTING-FOUR-SETTINGS-GOAL-v1.json',
    'sha256': '3a55034e6ed4c9cd86a3c85d16244a34e193125f457e71bbd7a0ea83e1c15b2f', 'size': 7841}
UNSAVED_OWNER_SCHEDULE = {'path':'logs/handoffs/2026-10-24-chatgpt-priority-watch-v1/HQ-owner-24h-ready-launch-authorization-v1/ACTUAL-OWNER-24H-AND-HQ-BOUNDED-LAUNCH-DECISION-v1.json',
    'sha256':'18a21456d4dcd4bab7f72f761db700797e14d98b4a94dbc132ad998bf646993b','size':2938}


UNSAVED_ALLOWED = ['set_exact_approved_future_schedule', 'set_creative_enhancement_Off',
                   'Save_as_draft_once', 'capture_Saved_and_exact_readback']
UNSAVED_FORBIDDEN = ['open_editor', 'create', 'clone', 'new_group', 'new_ad', 'change_budget_type',
                     'increase_budget', 'change_geography', 'Next', 'Back', 'Close', 'Publish',
                     'Enable', 'Terms', 'payment']


def unsaved_fields():
    return {'task_id': TASK, 'department': ROLE, 'action_id': EXISTING_FOUR_ACTION,
        'action_class': 'ads_write', 'scope': SCOPE, 'operation': UNSAVED_OPERATION,
        'technical_stage': UNSAVED_STAGE, 'account_id': ACCOUNT, 'campaign_id': EXISTING_FOUR_CAMPAIGN,
        'request_pins': ['before', 'desired', 'channel', 'control_map', 'preflight'],
        'before_state_source': 'actual_open_original_editor_unsaved_native_UI',
        'save_state': 'Unsaved changes', 'saved_server_values': 'NOT_PROVIDED',
        'date_authorization_missing': 'WAIT_OWNER_DATE; prepare and independent source adoption continue',
        'no_reopen': True, 'allowed_operations': UNSAVED_ALLOWED, 'forbidden_operations': UNSAVED_FORBIDDEN,
        'backup_scope': 'Observed current editor only; unknown saved server values cannot be restored',
        'rollback_scope': 'Hold/readback; no automatic compensating Save or reuse of inspection permit',
        'actual_action_allowed': False, 'server_CAS_provided': False}


def _unsaved_original_inspection(root, before):
    """Read the consumed inspection, never reopen or renew it."""
    occupied = inspection_status(root)
    require(occupied.get('state') == 'OCCUPIED_EFFECT_REQUIRES_NATIVE_READBACK',
            'actual original inspection occupancy required; never open to prepare Save')
    contract = document(root, UNSAVED_CONTRACT)
    source = document(root, contract['existing_results'][1])
    require(source.get('actual_persistent_reservation') == occupied['reservation']
            and source.get('actual_native_open', {}).get('count') == 1
            and source.get('actual_field_edits') == source.get('actual_Save_Publish_Enable_Terms_payment') == 0,
            'frozen actual once-open result and unchanged original occupancy required')
    from goal_delivery_runtime import _collaboration_native
    native = _collaboration_native(root, source['actual_native_open']['native_source'])
    require(native.get('thread', {}).get('id') == THREAD,
            'real original Paid2 inspection native source required')
    envelope = occupied['reservation']['draft_admission']
    inspection_request = document(root, envelope['request'])
    original_before = document(root, inspection_request['before'])
    require(before.get('tab_id') == original_before.get('tab_id'),
            'same already-open editor tab required; do not reopen or substitute a new editor')
    return occupied['reservation'], contract['existing_results'][1]


def _unsaved_feasible_start(root, proof, decision, now):
    """A real original HQ/executor declares one future point; no automatic shift."""
    record = document(root,proof.get('feasible_start_binding'))
    expected = {'schema':'original-fe689-feasible-future-start/v1', 'task_id':TASK,
        'technical_task_id':UNSAVED_STAGE, 'source_candidate_version':UNSAVED_VERSION,
        'scope':SCOPE, 'original_schedule_decision':UNSAVED_OWNER_SCHEDULE,
        'account_id':ACCOUNT, 'campaign_id':EXISTING_FOUR_CAMPAIGN,
        'start':proof['start'], 'end':decision['schedule_decision']['end'], 'timezone':'GMT+8',
        'shared_average_daily_MYR':35, 'daily_schedule':'24_hours',
        'existing_ad_groups':2, 'existing_ads':4, 'production_permission_issued':False}
    require(set(record) == set(expected)|{'recorded_by','observed_at'}
            and all(record.get(k) == v for k,v in expected.items())
            and record.get('production_permission_issued') is False
            and record.get('recorded_by') in {'operations',ROLE},
            'exact original HQ/executor feasible-start record; no extra object/budget/end/version authority')
    from goal_delivery_runtime import _collaboration_native
    native = _collaboration_native(root,proof.get('actual_native_feasible_start'))
    binding = w.department_registry(root)[record['recorded_by']]['chat_binding']
    require(all(native.get('thread',{}).get(k) == binding[v] for k,v in
                {'id':'task_id','title':'title','cwd':'cwd'}.items())
            and native.get('thread',{}).get('hostId','local') == 'local'
            and native.get('thread',{}).get('projectId',PROJECT) == PROJECT,
            'actual original same-project HQ/executor feasible-start native required')
    selected = [(t,m)for t in native.get('turns',[])if t.get('id') == proof.get('feasible_start_turn_id')
                for m in t.get('items',[])if m.get('id') == proof.get('feasible_start_message_id')]
    require(len(selected) == 1, 'one actual feasible-start declaration required')
    turn,message = selected[0];at = w._parse_observed_at(record.get('observed_at'))
    issued = w._parse_observed_at(decision.get('created_at')); start = w._parse_observed_at(proof['start'])
    require(turn.get('status') in {'completed','inProgress'} and not turn.get('error')
            and message.get('type') == 'agentMessage' and message.get('phase') in {'commentary','final_answer'}
            and type(turn.get('startedAt')) in {int,float} and at is not None and issued is not None
            and issued <= at <= now < start and turn['startedAt'] <= at.timestamp(),
            'real ordered source record must precede exact future start; no caller timestamp default')
    body = 'FLASHCAST_FE689_FEASIBLE_START '+json.dumps(record,ensure_ascii=False,sort_keys=True,separators=(',',':'))
    raw = proof.get('feasible_start_utf8')
    require(message.get('text') == body and isinstance(raw,dict)
            and w.file_digest(root,raw.get('path','')) == raw
            and (Path(root)/raw['path']).read_bytes() == body.encode(),
            'exact actual feasible-start declaration/UTF8 required; proposal labels are not source')


def _unsaved_delegated_schedule(root, proof, text, question_turn, owner_turn, now):
    """Consume the real async question-reply plus frozen original HQ decision."""
    prefix,suffix = '<send_user_message_question_reply>','</send_user_message_question_reply>'
    require(text.strip().startswith(prefix) and text.strip().endswith(suffix), 'actual native question-reply wrapper required')
    def unique(pairs):
        result = {}
        for key,value in pairs:
            require(key not in result,'ambiguous owner question-reply field'); result[key] = value
        return result
    try:
        rows = json.loads(text.strip()[len(prefix):-len(suffix)].strip(),object_pairs_hook=unique)
        require(isinstance(rows,list) and len(rows) == 1 and isinstance(rows[0],dict)
                and set(rows[0]) == {'questionItemId','question','answer'}, 'one exact actual question-reply row required')
        origin = json.loads(rows[0]['questionItemId'])
    except (ValueError,TypeError,KeyError) as error:
        raise w.WorkflowError('exact fe689 paused draft: malformed actual owner question-reply source') from error
    original = question_turn['items'][0]
    require(origin == ['request_user_input_async',original['id'],0] and type(origin[2]) is int
            and rows[0]['question'] == original['text'].split('\n- ',1)[0]
            and isinstance(rows[0]['answer'],str) and rows[0]['answer'].strip(),
            'real original question/call/object mapping and nonempty owner answer required')
    require(proof.get('actual_HQ_bounded_schedule_decision') == UNSAVED_OWNER_SCHEDULE
            and proof.get('owner_literally_selected_dates') is False,
            'real delegated schedule source required; never relabel it as literal owner date selection')
    decision = document(root,UNSAVED_OWNER_SCHEDULE)
    expected = {'schema':'HQ-owner-24h-ready-launch-decision/v1','task_id':TASK,'technical_task_id':UNSAVED_STAGE,
        'original_owner':ROLE,'sole_assistant':REVIEWER,'technical_owner':'system-development',
        'account_id':ACCOUNT,'campaign_id':EXISTING_FOUR_CAMPAIGN,'existing_ad_groups':2,'existing_ads':4}
    require(all(decision.get(k) == v for k,v in expected.items())
            and decision.get('actual_human_source') == proof['actual_native_human']
            and decision.get('source_turn_id') == proof['source_turn_id']
            and decision.get('source_message_id') == proof['source_message_id']
            and decision.get('actual_human_answer') == rows[0]['answer']
            and decision.get('source_thread_id') == w.department_registry(root)['operations']['chat_binding']['task_id']
            and decision.get('daily_schedule') == {'coverage':'24 hours every day',
                'daypart_restriction':'none; do not create an unobserved platform control'}
            and decision.get('budget',{}).get('shared_average_daily') == 35
            and decision.get('budget',{}).get('new_increase_authorized') is False,
            'unchanged exact original human delegation/HQ role/account/four objects/daily35 source required')
    schedule = decision['schedule_decision'];decided = w._parse_observed_at(decision.get('created_at'))
    end = w._parse_observed_at(schedule.get('end'));start = w._parse_observed_at(proof['start'])
    require(schedule.get('owner_literally_selected_dates') is False
            and schedule.get('end') == proof['end'] == '2026-10-31T18:00:00+08:00'
            and schedule.get('timezone') == 'Asia/Kuala_Lumpur'
            and decided is not None and owner_turn['startedAt'] <= decided.timestamp() <= now.timestamp()
            and start is not None and end is not None and now < end and start < end,
            'actual ordered bounded HQ schedule and fixed end required; expired intervals cannot be consumed')
    if proof['start'] != schedule['start']:
        require(start >= w._parse_observed_at(schedule['start']), 'feasible start cannot backdate the original interval')
        _unsaved_feasible_start(root,proof,decision,now)
    require(now < start, 'WAIT_FEASIBLE_START_BINDING: owner delegation is accepted; original HQ/Paid2 must record an exact future start before A1 request/permit, keeping October31 18:00 end and daily35')
    return {'start':proof['start'],'end':proof['end'],'timezone':'GMT+8'}


def _unsaved_owner_dates(root, pin, now):
    """A real exact human reply or actual offered-option answer, never a proposal."""
    if pin is None: return None
    proof = document(root, pin)
    require(all(proof.get(k) == v for k, v in {'task_id': TASK, 'scope': SCOPE,
        'account_id': ACCOUNT, 'campaign_id': EXISTING_FOUR_CAMPAIGN, 'timezone': 'GMT+8'}.items()),
        'exact original account/campaign date authority required')
    start, end = (w._parse_observed_at(proof.get(k)) for k in ('start', 'end'))
    try:
        offsets = [dt.datetime.fromisoformat(proof[k]).utcoffset() for k in ('start', 'end')]
    except (KeyError, TypeError, ValueError):
        offsets = []
    require(start is not None and end is not None and start < end
            and offsets == [dt.timedelta(hours=8), dt.timedelta(hours=8)],
            'genuinely approved future GMT+8 interval required')
    from goal_delivery_runtime import _collaboration_native
    page = _collaboration_native(root, proof.get('actual_native_human'))
    fixed = w.department_registry(root)['operations']['chat_binding']
    require(all(page.get('thread', {}).get(k) == fixed.get(v)
                for k, v in {'id': 'task_id', 'title': 'title', 'cwd': 'cwd'}.items()),
            'original current HQ human reply source required; assistant labels are insufficient')
    found = [(t, m) for t in page.get('turns', []) if t.get('id') == proof.get('source_turn_id')
             for m in t.get('items', []) if m.get('id') == proof.get('source_message_id')
             and m.get('type') == 'userMessage']
    require(len(found) == 1 and not found[0][0].get('error')
            and found[0][0].get('status') in {'inProgress', 'completed'}, 'one actual owner reply required')
    content = found[0][1].get('content')
    require(isinstance(content, list) and len(content) == 1 and content[0].get('type') == 'text',
            'unambiguous exact owner reply required')
    text = content[0].get('text', '')
    raw = proof.get('exact_human_utf8')
    require(isinstance(raw, dict) and w.file_digest(root, raw.get('path', '')) == raw
            and (Path(root)/raw['path']).read_bytes() == text.encode('utf-8'),
            'unchanged actual owner reply UTF8 required')
    require(proof.get('actual_native_question') == UNSAVED_DATE_QUESTION,
            'the actual already-asked original four-account question required, not an unrelated HQ question')
    question = _collaboration_native(root, UNSAVED_DATE_QUESTION)
    question_turn = question['turns'][0]
    require(question.get('thread', {}).get('id') == fixed['task_id']
            and question_turn.get('status') == 'completed' and not question_turn.get('error')
            and type(found[0][0].get('startedAt')) in {int, float}
            and question_turn.get('completedAt', float('inf')) <= found[0][0]['startedAt'] <= now.timestamp(),
            'actual owner answer must follow the original completed date question')
    if text.strip().startswith('<send_user_message_question_reply>'):
        return _unsaved_delegated_schedule(root,proof,text,question_turn,found[0][0],now)
    require(now < start, 'genuinely approved future GMT+8 interval required')
    explicit = text.strip() in {proof['start']+' 至 '+proof['end'], proof['start']+'至'+proof['end']}
    if not explicit:
        # First-party read_thread preserves the original option picker as its
        # real agentMessage. Do not invent a request_user_input tool envelope.
        label = proof.get('selected_option'); body = question_turn['items'][0].get('text', '')
        require(isinstance(label, str) and text.strip() == label and ('- '+label) in body,
                'actual selected original option required; proposal/caller choice is not approval')
        plan = document(root, document(root, UNSAVED_CONTRACT)['existing_results'][4])
        pairs = {'按今天18:00至10月31日18:00准备':
                    (plan['planned_exact_changes'][1]['proposed_after'], plan['planned_exact_changes'][2]['proposed_after']),
                 '改为明天10:00至11月1日10:00准备':
                    (plan['date_choice_alternative']['start'], plan['date_choice_alternative']['end'])}
        require(pairs.get(label) == (proof['start'], proof['end']),
                'exact original offered interval mapping required')
    return {'start': proof['start'], 'end': proof['end'], 'timezone': 'GMT+8'}


def prepare_unsaved_settings(root, request_pin, *, fresh_required=True, checked_at=None):
    """Keep observed Unsaved values separate from unknown saved server state."""
    current_parent(root); request = document(root, request_pin)
    require(set(request) == {'task_id', 'department', 'action_id', 'action_class', 'scope', 'operation',
        'technical_stage', 'source_project_id', 'source_thread_id', 'account_id', 'login_email',
        'campaign_id', 'before', 'desired', 'channel', 'control_map', 'preflight'},
        'exact unsaved-settings request schema required')
    require(all(request.get(k) == v for k, v in {'task_id': TASK, 'department': ROLE,
        'action_id': EXISTING_FOUR_ACTION, 'action_class': 'ads_write', 'scope': SCOPE,
        'operation': UNSAVED_OPERATION, 'technical_stage': UNSAVED_STAGE,
        'source_project_id': PROJECT, 'source_thread_id': THREAD, 'account_id': ACCOUNT,
        'login_email': EMAIL, 'campaign_id': EXISTING_FOUR_CAMPAIGN}.items()),
        'original four/parent/Paid2/exact unsaved Save only')
    before, desired, channel, controls, preflight = [document(root, request[k])
        for k in ('before', 'desired', 'channel', 'control_map', 'preflight')]
    for value in (before, desired, channel):
        require(all(value.get(k) == request[k] for k in
            ('account_id', 'login_email', 'source_project_id', 'source_thread_id')), 'exact original observation identity required')
    require(before.get('state_source') == 'actual_open_original_editor_unsaved_native_UI'
            and before.get('save_state') == 'Unsaved changes'
            and before.get('saved_server_values') == 'NOT_PROVIDED',
            'real Unsaved UI cannot be relabelled as saved_native_readback')
    browser = _native_browser_identity(root, before, channel)
    require(channel.get('kind') == 'authenticated_existing_browser' and channel.get('control') == 'Save as draft'
            and channel.get('object_id') == EXISTING_FOUR_CAMPAIGN
            and channel.get('editor_already_open') is True
            and channel.get('allowed_operations') == UNSAVED_ALLOWED
            and channel.get('forbidden_operations') == UNSAVED_FORBIDDEN
            and all(channel.get(k) is False for k in ('terms_acceptance', 'publish', 'activate', 'payment', 'reopen')),
            'only original existing-editor Save channel; no inspection permit transfer')
    campaign, target = before.get('campaign', {}), desired.get('campaign', {})
    require(campaign.get('id') == EXISTING_FOUR_CAMPAIGN and campaign.get('name') == CAMPAIGN
            and campaign.get('budget') == {'type': 'average_daily', 'currency': 'MYR', 'amount': 35}
            and type(campaign.get('creative_enabled')) is bool,
            'actual rendered daily35/creative state required, never list total0 or a saved claim')
    require(campaign.get('locations') == {'include': ['Wilayah Persekutuan Kuala Lumpur', 'Selangor'], 'exclude': []},
            'actual unchanged KL/Selangor and visible exclusion state required')
    objects = before.get('original_objects', [])
    require(len(objects) == 2 and {x.get('name') for x in objects} == set(EXISTING_FOUR_IDS), 'original two groups required')
    for group in objects:
        gid, ids = EXISTING_FOUR_IDS[group['name']]
        require(group.get('id') == gid and len(group.get('ads', [])) == 2
                and {x.get('id') for x in group['ads']} == ids
                and {x.get('name') for x in group['ads']} == EXISTING_AD_NAMES[group['name']], 'exact original seven IDs required')
    now = checked_at or dt.datetime.now(dt.timezone.utc)
    dates = _unsaved_owner_dates(root, desired.get('date_authorization'), now)
    require(set(desired) == {'account_id', 'login_email', 'source_project_id', 'source_thread_id',
                             'campaign', 'date_authorization'}, 'no hidden desired write fields')
    expected = {**campaign, 'creative_enabled': False, 'schedule': dates}
    require(target == expected, 'only enhancement Off and actual owner-approved future schedule may change')
    require(controls.get('object_id') == EXISTING_FOUR_CAMPAIGN
            and controls.get('control') == 'Save as draft' and controls.get('effect') == 'explicit_native_save'
            and controls.get('mode') == 'existing_editor_visible_projection'
            and controls.get('visible_fields_projection') == campaign
            and controls.get('protected_original_objects') == objects
            and set(controls.get('fields', {})) == {'creative_enabled', 'schedule'},
            'complete observed affected editor projection and original objects must be protected')
    for name, value in controls['fields'].items():
        require(isinstance(value, dict) and value.get('label') and value.get('route')
                and value.get('observed_value') == campaign.get(name), 'actual narrow field control/source required')
    reservation, inspection_source = _unsaved_original_inspection(root, before)
    guards = [request_pin, UNSAVED_CONTRACT, inspection_source]
    for key in ('before', 'desired', 'channel', 'control_map', 'preflight'): guards.append(request[key])
    if desired.get('date_authorization'): guards.append(desired['date_authorization'])
    require(preflight.get('risk_level') == 'R2', 'real limited Save risk required')
    for name in ('facts', 'self_check', 'backup', 'rollback'):
        value = document(root, preflight.get(name)); guards.append(preflight[name])
        require(all(value.get(k) == request[k] for k in
                    ('task_id', 'department', 'action_id', 'action_class', 'scope', 'operation'))
                and all(value.get(k) == request[k] for k in ('before', 'desired', 'channel', 'control_map')),
                'exact real Save facts/selfcheck/limited backup/rollback source required')
        if name == 'self_check':
            require(value.get('status') in ({'PASS'} if dates else {'PASS', 'WAIT_OWNER_DATE'})
                    and value.get('server_saved_values_unknown') is True
                    and value.get('permitted_UI_steps') == UNSAVED_ALLOWED,
                    'real bounded Save self-check and accurate owner-date dependency required')
        elif name == 'backup':
            require(value.get('coverage') == 'observed_unsaved_editor_and_original_objects_only'
                    and value.get('full_saved_server_backup') is False, 'do not invent saved backend backup')
        elif name == 'rollback':
            require(value.get('mode') == 'hold_readback_original_A1_separate_recovery_decision'
                    and value.get('automatic_compensating_save') is False
                    and value.get('unknown_effect_retry') is False, 'no blind retry or unapproved compensating Save')
    for observation in (before, channel, controls):
        require(isinstance(observation.get('native_evidence'), list) and observation['native_evidence'],
                'actual editor/control native evidence pins required')
        for pin in observation['native_evidence']:
            require(w.file_digest(root, pin.get('path', '')) == pin, 'native editor/control bytes changed'); guards.append(pin)
        if fresh_required: _fresh_at(observation.get('observed_at'), now)
    if fresh_required: _fresh_at(browser['observed_at'], now)
    return {'state': 'UNSAVED_SETTINGS_PREPARED_NOT_AUTHORIZED' if dates else 'WAIT_OWNER_DATE',
        'request': request_pin, 'intent': request, 'guards': guards, 'browser_identity': browser,
        'approved_schedule': dates, 'independent_preparation_complete': True,
        'date_wait_owner': 'operations / original human date answer' if not dates else None,
        'inspection_reservation_unchanged': reservation,
        'execution_key': w.sha256_value([TASK, ROLE, ACCOUNT, EXISTING_FOUR_CAMPAIGN, EXISTING_FOUR_ACTION, UNSAVED_OPERATION]),
        'actual_action_allowed': False, 'external_permission_issued': False}


def _unsaved_adopted_stage(root):
    import goal_delivery_runtime as g
    stage = g.restore_goal(root, w.read_json(w.snapshot_path(root, UNSAVED_STAGE))); goal = stage.get('goal_delivery', {})
    require(stage.get('goal_contract') == UNSAVED_CONTRACT and goal.get('parent_task_id') == TASK
            and goal.get('producer_departments') == ['system-development']
            and goal.get('responsible_assistant') == REVIEWER and goal.get('authorization_pin') == ADOPTION_AUTH
            and goal.get('authorized_scope') == [UNSAVED_SCOPE], 'original independent unsaved-source stage required')
    rows, bad = w._validate_receipt_chain(root, UNSAVED_STAGE)
    require(not bad and not w.validate_workflow_events(root, UNSAVED_STAGE), 'intact actual stage chains required')
    accepted = w.goal_completion_subject(root, stage, rows, {'mode': 'latest_exact_accepted_result',
        'producer_department': 'system-development', 'scope': UNSAVED_SCOPE})
    require(accepted.get('state') == 'PROVEN' and accepted.get('identity', {}).get('candidate_version') == UNSAVED_VERSION,
            'normal exact independent unsaved-source acceptance required')
    manifest = document(root, accepted['candidate'])
    require(manifest.get('candidate_fingerprint') == accepted.get('source_fingerprint')
            and [c.get('path') for c in manifest.get('changes', [])] == ['tools/chatgpt_fe689_draft_admission.py'],
            'exact reviewed unsaved-source module required')
    requirement = next(x for x in document(root, UNSAVED_CONTRACT)['completion_requirements']
                       if x['requirement_id'] == 'unsaved-existing-four-settings-source-adopted')
    effect = w.goal_typed_completion_proof(root, stage, rows, requirement, accepted)
    require(effect.get('state') == 'PROVEN', 'real completed A1 unsaved-source adoption required: '+str(effect.get('reason', effect.get('state'))))
    predecessor = _unsaved_predecessor_chain(root, manifest, accepted, effect)
    return {'accepted': accepted, 'proof': effect, 'guards': [accepted['candidate'], *effect['evidence'],
        *predecessor, w.file_digest(root, 'tools/chatgpt_fe689_draft_admission.py')]}


def _unsaved_predecessor_chain(root, manifest, accepted, effect):
    """Keep the real inspection adoption historical; prove the new CAS edge.

    Do not replace the old after SHA or pretend it is still the current file.
    The old native-completed effect and the current normal typed effect are
    separate proofs connected by the actual before/backup bytes.
    """
    closure_pin = document(root, UNSAVED_CONTRACT)['existing_results'][3]
    closure = document(root, closure_pin); prior_pin = closure['actual_typed_source_proof']
    prior = document(root, prior_pin); journal_pin = prior['journal']; journal = document(root, journal_pin)
    require(closure.get('task_id') == INSPECTION_STAGE and closure.get('internal_stage_closed') is True
            and prior.get('proof_type') == 'source_adoption'
            and prior.get('identity', {}).get('task_id') == INSPECTION_STAGE
            and prior.get('identity', {}).get('candidate_version') == INSPECTION_VERSION
            and prior.get('scope') == INSPECTION_SCOPE and journal.get('task_id') == INSPECTION_STAGE
            and journal.get('state') == 'adopted' and journal.get('actor') == REVIEWER
            and journal.get('authorized_source') == ADOPTION_AUTH
            and journal.get('permissions_issued') is False and journal.get('external_writes') == 0,
            'real original completed inspection-source adoption required')
    old_manifest = document(root, journal['candidate_manifest'])
    require(old_manifest.get('candidate_fingerprint') == prior.get('source_fingerprint') == journal.get('candidate_fingerprint'),
            'original inspection manifest/fingerprint cannot be relabelled')
    w._completion_native_stage(root, prior, journal_pin, REVIEWER)
    operations = journal.get('source_operations', [])
    require(len(operations) == 1 and operations[0].get('path') == 'tools/chatgpt_fe689_draft_admission.py'
            and manifest['changes'][0]['expected_source']['sha256'] == operations[0].get('after_sha256')
            and manifest['changes'][0]['expected_source']['mode'] == operations[0].get('mode'),
            'new Save source must be an exact compatible CAS successor to actual inspection bytes/mode')
    new_proof = document(root, effect['evidence'][0]); new_journal = document(root, new_proof['journal'])
    new_operations = new_journal.get('source_operations', [])
    require(len(new_operations) == 1 and new_operations[0].get('before_sha256') == operations[0]['after_sha256']
            and w.file_digest(root, new_operations[0]['backup']['path']) == new_operations[0]['backup']
            and new_operations[0]['backup']['sha256'] == operations[0]['after_sha256']
            and new_journal.get('candidate_manifest') == accepted['candidate'], 'actual new backup/CAS must close the original source edge')
    return [closure_pin, prior_pin, journal_pin, journal['candidate_manifest'], new_proof['journal']]


def _autonomous_unsaved_context(root, envelope, context, release):
    import department_autonomy as a
    auth=a.authority(root)
    stage=a.adopted_save_source(root)
    require(release == {'technical_source_manifest':stage['accepted']['candidate'],'owner_autonomy_source':a.OWNER},
            'exact actually adopted technical source and real owner authority required')
    binding=w.department_registry(root)[ROLE]
    require(binding.get('new_dispatch_enabled') is True and 'chatgpt-ads' in binding.get('approved_subskills',[])
        and w._chat_binding_healthy(binding['chat_binding'],verification_ttl_hours=26), 'healthy original Paid2 executor/method required')
    return {**context,'state':'NORMAL_UNSAVED_SETTINGS_SAVE_CONTEXT','issuer_department':ROLE,
        'authorization_basis':auth,'parent_decision_record_id':'',
        'technical_source_manifest':stage['accepted']['candidate'],
        'guards':context['guards']+[envelope['release'],*stage['guards']]}


def unsaved_context(root, envelope):
    require(isinstance(envelope, dict) and set(envelope) == {'request', 'release'}, 'exact unsaved request/release envelope required')
    context = prepare_unsaved_settings(root, envelope['request'])
    require(context['state'] != 'WAIT_OWNER_DATE', 'WAIT_OWNER_DATE: original human date answer required only before actual settings/Save')
    release = document(root, envelope['release'])
    if 'owner_autonomy_source' in release:
        return _autonomous_unsaved_context(root,envelope,context,release)
    stage = _unsaved_adopted_stage(root)
    require(set(release) == {'technical_source_manifest', 'parent_decision_record_id'}
            and release['technical_source_manifest'] == stage['accepted']['candidate'], 'actual adopted Save-stage source required')
    from scoped_candidate_adoption import _committed
    events = w._result_handoff_rows(root, TASK); selected = [x for x in events if x.get('record_id') == release['parent_decision_record_id']]
    require(len(selected) == 1, 'one real original A1 exact Save decision required'); decision = selected[0]
    require(all(decision.get(k) == v for k, v in {'event': 'controller_decision', 'decision': 'continue',
        'decision_actor': REVIEWER, 'coordinator_role': REVIEWER, 'next_owner': ROLE,
        'next_action': 'authorize-exact-unsaved-existing-four-settings-save'}.items())
        and envelope['request'] in decision.get('evidence', [])
        and document(root, context['intent']['desired'])['date_authorization'] in decision.get('evidence', [])
        and stage['accepted']['candidate'] in decision.get('evidence', []), 'real independent request/date/Save-source decision required')
    _committed(root, decision); source = document(root, decision['outbox'])
    require(source.get('department') == ROLE and source.get('task_id') == TASK
            and source.get('unsaved_settings_request') == envelope['request'], 'real Paid2 exact Save preparation result required')
    same = lambda row: all(row.get(k) == decision.get(k) for k in ('task_id', 'sender_department', 'candidate_version', 'result_sha256'))
    queued = [x for x in events if same(x) and x.get('event') == 'notification_queued']
    received = [x for x in events if same(x) and x.get('event') == 'controller_received']
    require(len(queued) == len(received) == 1 and received[0].get('decision_actor') == REVIEWER
            and events.index(queued[0]) < events.index(received[0]) < events.index(decision), 'real ordered original A1 intake/decision required')
    _committed(root, received[0]); w._validate_goal_completed_result(root, queued[0], THREAD)
    require(w._chat_binding_healthy(w.department_registry(root)[ROLE]['chat_binding'], verification_ttl_hours=26,
                                   now=dt.datetime.now(dt.timezone.utc))
            and w.department_registry(root)[ROLE].get('new_dispatch_enabled') is True
            and 'chatgpt-ads' in w.department_registry(root)[ROLE].get('approved_subskills', []), 'healthy exact current Paid2 method required')
    return {**context, 'state': 'NORMAL_UNSAVED_SETTINGS_SAVE_CONTEXT', 'parent_decision_record_id': decision['record_id'],
        'technical_source_manifest': stage['accepted']['candidate'], 'guards': context['guards']+[envelope['release'], decision['outbox'],
            *stage['guards'], w.file_digest(root, str(w.result_handoff_path(root, TASK).relative_to(root)))]}


def _unsaved_attempt_path(root, key):
    path = Path(root)/'logs/exact-chatgpt-unsaved-settings-attempts'/(key+'.jsonl')
    require(not any(p.is_symlink() for p in [path, *path.parents]), 'no aliased Save occupancy')
    return path


def unsaved_policy(root, requested, envelope):
    context = unsaved_context(root, envelope); intent = context['intent']
    require(all(requested.get(k) == intent[k] for k in ('task_id', 'department', 'action_id', 'action_class', 'scope', 'source_project_id'))
            and requested.get('payload_sha256') == envelope['request']['sha256']
            and requested.get('approval_id') == '' and requested.get('skill') == 'chatgpt-ads'
            and type(requested.get('consume_approval')) is bool
            and not any(requested.get(k) for k in ('target_project_id', 'target_department', 'target_thread_id',
                'target_thread_title', 'target_cwd', 'target_sidebar_section_id', 'target_automation_status', 'retry_blocked_execution_receipt_id')),
            'exact original Save request/role/SHA only; inspection and residential permits cannot transfer')
    key = context['execution_key']; result = {**requested, 'draft_admission': envelope, 'unsaved_save_key': key,
        'operation': UNSAVED_OPERATION, 'technical_stage': UNSAVED_STAGE, 'issuer_department': context.get('issuer_department',REVIEWER),
        'authorization_basis':context.get('authorization_basis'),
        'parent_decision_record_id': context['parent_decision_record_id'], 'account_id': ACCOUNT,
        'campaign_id': EXISTING_FOUR_CAMPAIGN, 'allowed_operations': UNSAVED_ALLOWED, 'forbidden_operations': UNSAVED_FORBIDDEN,
        'exact_field_patch': {'creative_enabled': False, 'schedule': context['approved_schedule']},
        'budget_preserved': {'type': 'average_daily', 'currency': 'MYR', 'amount': 35},
        'promotion_activation_or_payment_authority': False, 'checked_at': w.utc_timestamp(),
        'approval_basis': ('actual_owner_delegation_original_task_selfchecked_Save' if context.get('authorization_basis') else 'actual_A1_adopted_unsaved_source_and_committed_original_exact_date_Save_decision')}
    with w.workflow_lock(root):
        for pin in context['guards']: require(w.file_digest(root, pin['path']) == pin, 'Save source changed before permit')
        prepare_unsaved_settings(root, envelope['request'])
        from department_autonomy import known_original_save
        require(known_original_save(root) is None, 'actual native Save already performed; readback only, no replay')
        require(not _unsaved_attempt_path(root, key).exists() and not any(x.get('unsaved_save_key') == key and x.get('status') == 'allow'
            for x in w.read_jsonl(Path(root)/w.POLICY_DECISIONS)), 'Save already issued/occupied; unknown effect is readback only')
        if not requested['consume_approval']: return {**result, 'status': 'preflight_ready_not_a_permit', 'actual_action_allowed': False}, []
        result.update(status='allow', actual_action_allowed=True, approval_status='consumed_for_exact_unsaved_settings_Save_only',
                      decision_id='pol-'+w.sha256_value([key, result['checked_at']])[:20])
        w.append_jsonl_locked(Path(root)/w.POLICY_DECISIONS, result)
    return result, [Path(root)/w.POLICY_DECISIONS]


def _unsaved_grant(root, context, envelope, decision_id):
    grants = [x for x in w.read_jsonl(Path(root)/w.POLICY_DECISIONS) if x.get('unsaved_save_key') == context['execution_key'] and x.get('status') == 'allow']
    exact = {'decision_id': decision_id, 'task_id': TASK, 'department': ROLE, 'action_id': EXISTING_FOUR_ACTION,
        'action_class': 'ads_write', 'scope': SCOPE, 'source_project_id': PROJECT, 'payload_sha256': envelope['request']['sha256'],
        'draft_admission': envelope, 'operation': UNSAVED_OPERATION, 'technical_stage': UNSAVED_STAGE,
        'issuer_department': context.get('issuer_department',REVIEWER), 'account_id': ACCOUNT, 'campaign_id': EXISTING_FOUR_CAMPAIGN,
        'allowed_operations': UNSAVED_ALLOWED, 'forbidden_operations': UNSAVED_FORBIDDEN,
        'exact_field_patch': {'creative_enabled': False, 'schedule': context['approved_schedule']},
        'budget_preserved': {'type': 'average_daily', 'currency': 'MYR', 'amount': 35},
        'consume_approval': True, 'approval_id': '', 'actual_action_allowed': True,
        'skill': 'chatgpt-ads',
        'promotion_activation_or_payment_authority': False, 'approval_status': 'consumed_for_exact_unsaved_settings_Save_only'}
    if context.get('authorization_basis'):
        exact['authorization_basis']=context['authorization_basis']
    require(len(grants) == 1 and all(grants[0].get(k) == v for k, v in exact.items()), 'one real exact Save permit required, not inspection/residential permission')
    return grants[0]


def reserve_unsaved_settings(root, envelope, decision_id):
    context = unsaved_context(root, envelope)
    with w.workflow_lock(root):
        for pin in context['guards']: require(w.file_digest(root, pin['path']) == pin, 'Save source changed before occupancy')
        prepare_unsaved_settings(root, envelope['request']); grant = _unsaved_grant(root, context, envelope, decision_id); fresh(grant.get('checked_at'))
        from department_autonomy import known_original_save
        require(known_original_save(root) is None, 'actual native Save already performed; readback only, no replay')
        path = _unsaved_attempt_path(root, context['execution_key']); require(not path.exists(), 'no duplicate edit/Save attempt, including unknown effect')
        row = {'schema': 'original-unsaved-existing-four-Save-occupancy/v1', 'state': 'reserved_before_any_settings_edit',
            'task_id': TASK, 'department': ROLE, 'operation': UNSAVED_OPERATION, 'account_id': ACCOUNT,
            'campaign_id': EXISTING_FOUR_CAMPAIGN, 'decision_id': decision_id, 'draft_admission': envelope,
            'reserved_at': w.utc_timestamp(), 'actual_saved_effect': 'NOT_OBSERVED', 'retry_allowed': False}
        w.append_jsonl_locked(path, row)
    return {'reservation': row, 'next_owner': ROLE, 'allowed_operations': UNSAVED_ALLOWED,
        'exact_field_patch': grant['exact_field_patch'], 'forbidden_operations': UNSAVED_FORBIDDEN,
        'actual_UI_execution_performed': False, 'unknown_effect_rule': 'Read current original editor/list; do not edit or Save again'}


def unsaved_status(root):
    current_parent(root); key = w.sha256_value([TASK, ROLE, ACCOUNT, EXISTING_FOUR_CAMPAIGN, EXISTING_FOUR_ACTION, UNSAVED_OPERATION])
    path = _unsaved_attempt_path(root, key)
    if not path.exists():
        from department_autonomy import known_original_save
        actual=known_original_save(root)
        if actual is not None:return actual
        return {'state': 'NO_SAVE_ATTEMPT', 'actual_saved_effect': False, 'retry_authorized': False}
    rows = w.read_jsonl(path)
    require(len(rows) == 1 and rows[0].get('schema') == 'original-unsaved-existing-four-Save-occupancy/v1'
            and rows[0].get('state') == 'reserved_before_any_settings_edit' and rows[0].get('retry_allowed') is False
            and all(rows[0].get(k) == v for k, v in {'task_id': TASK, 'department': ROLE,
                'operation': UNSAVED_OPERATION, 'account_id': ACCOUNT, 'campaign_id': EXISTING_FOUR_CAMPAIGN}.items()), 'one original intact Save occupancy required')
    row = rows[0]; at = w._parse_observed_at(row.get('reserved_at'))
    require(at is not None and at <= dt.datetime.now(dt.timezone.utc), 'real occupancy time required')
    context = prepare_unsaved_settings(root, row['draft_admission']['request'], fresh_required=False, checked_at=at)
    require(context['approved_schedule'] is not None, 'original occupied Save must have genuine dates')
    release=document(root,row['draft_admission']['release'])
    if 'owner_autonomy_source' in release:
        context=_autonomous_unsaved_context(root,row['draft_admission'],context,release)
    grant = _unsaved_grant(root, context, row['draft_admission'], row['decision_id']); issued = w._parse_observed_at(grant.get('checked_at'))
    require(issued is not None and issued <= at, 'actual permit must precede first edit occupancy'); _fresh_at(grant['checked_at'], at)
    for name in ('before', 'channel', 'control_map'): _fresh_at(document(root, context['intent'][name]).get('observed_at'), at)
    _fresh_at(context['browser_identity']['observed_at'], at)
    return {'state': 'OCCUPIED_SAVE_REQUIRES_NATIVE_READBACK', 'reservation': row, 'retry_authorized': False,
        'actual_saved_effect_not_inferred': True, 'next_owner': ROLE}


def validate_unsaved_save_readback(root, observation_pin):
    """Validate actual native scoped readback; never issue, retry or edit UI."""
    observation = document(root, observation_pin); status = unsaved_status(root)
    require(status.get('state') == 'OCCUPIED_SAVE_REQUIRES_NATIVE_READBACK', 'actual original Save occupancy required')
    row = status['reservation']; at = w._parse_observed_at(row['reserved_at'])
    context = prepare_unsaved_settings(root, row['draft_admission']['request'], fresh_required=False, checked_at=at)
    require(all(observation.get(k) == v for k, v in {'task_id': TASK, 'department': ROLE, 'account_id': ACCOUNT,
        'campaign_id': EXISTING_FOUR_CAMPAIGN, 'decision_id': row['decision_id'], 'save_state': 'Saved'}.items()),
        'no Saved claim without exact original permit/account readback')
    from goal_delivery_runtime import _collaboration_native
    page = _collaboration_native(root, observation.get('actual_native_execution'))
    require(page.get('thread', {}).get('id') == THREAD, 'actual original Paid2 native Save/readback required')
    calls = [(t, m) for t in page.get('turns', []) for m in t.get('items', [])
             if m.get('id') == observation.get('native_execution_id') and m.get('type') == 'mcpToolCall']
    require(len(calls) == 1 and calls[0][1].get('status') == 'completed' and not calls[0][1].get('error')
            and not calls[0][0].get('error'),
            'one real successful post-occupancy native Save invocation required')
    turn, call = calls[0]; items = turn.get('items', []); index = items.index(call)
    import re
    control_pin = observation.get('actual_pre_save_control_text')
    control_index = observation.get('actual_save_control_index')
    require(call.get('server') == 'cua_repl' and call.get('tool') == 'js'
            and type(control_index) is int and control_index > 0
            and isinstance(control_pin, dict) and w.file_digest(root, control_pin.get('path', '')) == control_pin,
            'actual original native Save control and successful first-party UI invocation required')
    control_text = (Path(root)/control_pin['path']).read_text()
    command = call.get('arguments', {}).get('code', '')
    require(CAMPAIGN in control_text and ACCOUNT in control_text
            and re.search(r'(?m)^\s*'+str(control_index)+r'\s+button\s+Save as draft\s*$', control_text)
            and len(re.findall(r'\.click\(\s*'+str(control_index)+r'\s*\)', command)) == 1,
            'one actual observed original Save-as-draft click required, not a label or unrelated successful tool')
    preceding = [m for m in items[:index] if m.get('type') == 'commandExecution'
                 and m.get('status') == 'completed' and m.get('exitCode') == 0
                 and m.get('cwd') == str(Path(root).resolve())
                 and 'unsaved-reserve' in m.get('command', '')
                 and row['decision_id'] in m.get('command', '')]
    observed = w._parse_observed_at(observation.get('observed_at'))
    require((len(preceding) == 1 or turn.get('startedAt', 0) >= at.timestamp())
            and observed is not None and at <= observed <= dt.datetime.now(dt.timezone.utc),
            'real successful reservation must precede the native Save, including within the same turn')
    text_pin = observation.get('actual_saved_native_text')
    require(isinstance(text_pin, dict) and w.file_digest(root, text_pin.get('path', '')) == text_pin, 'exact actual Saved readback bytes required')
    text = (Path(root)/text_pin['path']).read_text()
    require('Unsaved changes' not in text and re.search(r'\bSaved\b|[Dd]raft saved|[Cc]hanges saved', text), 'actual positive Saved state required, not a caller flag')
    target = document(root, context['intent']['desired'])['campaign']
    require(observation.get('campaign') == target
            and observation.get('original_objects') == document(root, context['intent']['before'])['original_objects']
            and observation.get('original_pause_state_preserved') is True,
            'full changed values and original four objects must actually read back; missing fields remain incomplete')
    return {'state': 'SAVED_NATIVE_PROJECTION_VERIFIED_REPORT_TO_OPERATIONS',
        'observation': observation_pin, 'reservation_unchanged': True,
        'server_CAS_provided': False, 'new_permission_or_retry': False, 'business_parent_closed': False}


def unsaved_source_chain(root, manifest_pin):
    """Dedicated read-only lineage entry. Waiting is not source adoption or Ads permission."""
    manifest = document(root,manifest_pin)
    require(manifest.get('schema') == 'flashcast-exact-source-candidate/v1'
            and manifest.get('task_id') == UNSAVED_STAGE and manifest.get('scope') == UNSAVED_SCOPE
            and manifest.get('candidate_version') == UNSAVED_VERSION
            and manifest.get('goal_contract') == UNSAVED_CONTRACT
            and manifest.get('human_authorization') == ADOPTION_AUTH
            and manifest.get('department') == manifest.get('primary_owner') == 'system-development'
            and manifest.get('responsible_assistant') == REVIEWER
            and manifest.get('candidate_fingerprint') == w.sha256_value({k:v for k,v in manifest.items()if k != 'candidate_fingerprint'}),
            'unsaved-source-chain requires the exact current source manifest, never an Ads request/release envelope')
    import goal_delivery_runtime as g,qa_review_plan as q
    stage = g.restore_goal(root,w.read_json(w.snapshot_path(root,UNSAVED_STAGE)));goal = stage.get('goal_delivery',{})
    require(stage.get('goal_contract') == UNSAVED_CONTRACT and goal.get('parent_task_id') == TASK
            and goal.get('producer_departments') == ['system-development'] and goal.get('responsible_assistant') == REVIEWER
            and goal.get('authorization_pin') == ADOPTION_AUTH and goal.get('authorized_scope') == [UNSAVED_SCOPE],
            'unchanged original internal source stage/sole A1/authority required')
    q._review_manifest_source_pins(root,stage,{'scope':UNSAVED_SCOPE,'producer_department':'system-development',
        'reviewer_department':REVIEWER},manifest_pin,candidate_version=UNSAVED_VERSION,fingerprint=manifest['candidate_fingerprint'])
    require([c.get('path') for c in manifest.get('changes',[])] == ['tools/chatgpt_fe689_draft_admission.py'],
            'exact independently reviewed single module required')
    rows,bad = w._validate_receipt_chain(root,UNSAVED_STAGE)
    require(not bad and not w.validate_workflow_events(root,UNSAVED_STAGE), 'intact actual source stage chains required')
    accepted = w.goal_completion_subject(root,stage,rows,{'mode':'latest_exact_accepted_result',
        'producer_department':'system-development','scope':UNSAVED_SCOPE})
    base = {'technical_stage':UNSAVED_STAGE,'manifest':manifest_pin,'candidate_version':UNSAVED_VERSION,
        'next_owner':REVIEWER,'account_request_required':False,'date_or_permit_required':False,
        'actual_action_allowed':False,'external_permission_issued':False,'writes_performed':False}
    if (accepted.get('state') != 'PROVEN' or accepted.get('candidate') != manifest_pin
            or accepted.get('identity',{}).get('candidate_version') != UNSAVED_VERSION):
        return {**base,'state':'WAIT_INDEPENDENT_SOURCE_ADOPTION','reason':'exact current candidate acceptance/adoption not proven',
                'normal_source_subject_state':accepted.get('state'),'source_adopted':False}
    requirement = next(x for x in document(root,UNSAVED_CONTRACT)['completion_requirements']
        if x['requirement_id'] == 'unsaved-existing-four-settings-source-adopted')
    effect = w.goal_typed_completion_proof(root,stage,rows,requirement,accepted)
    if effect.get('state') != 'PROVEN':
        return {**base,'state':'WAIT_REAL_COMPLETED_SOURCE_ADOPTION','reason':effect.get('reason',effect.get('state')),
                'normal_typed_source_state':effect.get('state'),'source_adopted':False}
    actual = _unsaved_adopted_stage(root)
    require(actual['accepted']['candidate'] == manifest_pin, 'current normal adopted source must remain this exact manifest')
    return {**base,'state':'UNSAVED_SOURCE_CHAIN_PROVEN','source_adopted':True,
        'normal_source_proof':actual['proof'],'continuous_original_completed_before_backup_after_guards':actual['guards'],
        'current_runtime_source':w.file_digest(root,'tools/chatgpt_fe689_draft_admission.py')}


def unsaved_command(root, args):
    if args.command == 'unsaved-fields': return unsaved_fields()
    if args.command == 'unsaved-status': return unsaved_status(root)
    require(args.input is not None, 'exact project-local unsaved input required')
    relative = str(args.input.resolve().relative_to(root)) if args.input.is_absolute() else str(args.input)
    pin = w.file_digest(root, relative)
    if args.command == 'unsaved-prepare': return prepare_unsaved_settings(root, pin)
    if args.command == 'unsaved-readback': return validate_unsaved_save_readback(root, pin)
    if args.command == 'unsaved-source-chain': return unsaved_source_chain(root,pin)
    envelope = document(root, pin)
    if args.command == 'unsaved-context': return unsaved_context(root, envelope)
    if args.command == 'unsaved-reserve': return reserve_unsaved_settings(root, envelope, args.decision_id)
    request = document(root, envelope['request'])
    value, _ = w.policy_check(root, **{k: request[k] for k in
        ('task_id', 'department', 'action_id', 'action_class', 'scope', 'source_project_id')},
        skill='chatgpt-ads', payload_sha256=envelope['request']['sha256'],
        consume_approval=args.command == 'unsaved-issue', draft_admission=envelope)
    return value


if __name__ == '__main__':
    import sys
    sys.modules['chatgpt_fe689_draft_admission'] = sys.modules[__name__]
    inspection_main()
