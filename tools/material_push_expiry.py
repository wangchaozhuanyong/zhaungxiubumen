"""Evidence adapter for the original two-materials push stopped before Git."""

import hashlib
from pathlib import Path

import department_autonomy as a
import workflow_control as w


SCHEMA = 'original-two-materials-1f92-pretransport-expiry-recovery/v1'
TASK = 'fc-20261014-two-original-materials-exact-body-publication-v1'
ACTION = TASK + '-original-body-1f92eaeb2008-git-push-v1'
POLICY = 'pol-9ba82a228b8dd44a923e'
TURN = 'example-native-a57025468c640f90'
FAILED = 'exec-9f999dd9-ee2e-4eb2-b58a-61976d1af335'
READBACK = 'exec-4f75a4af-1408-4f4c-b57b-9cd5428dd4ee'
ADMISSION = 'exec-84612c16-7885-4454-b5fd-3f9d76da1675'
SECOND_POLICY = 'pol-5d01550c26fd2f85c8c1'
SECOND_TURN = 'example-native-f70601548b8dd69b'
OWNER_THREAD = '<LOCAL_TASK_ID>'
OWNER_TURN = 'example-native-28a5912532b57210'
OWNER_MESSAGE = 'example-native-5607b59e26bea75b'
REQUEST_TURN = 'example-native-2719ac52a0e57ce8'
REQUEST_MESSAGE = 'msg_eb9ffc8c3d946d25f786a2a7a9a0fbd2928c2fd620ee5c2eca81edf45136b191'
EVIDENCE_DIR = Path('logs/handoffs/2026-10-29-two-materials-current-owner-WEB-continuation-v1/'
                    'designated-development/actual-currentc5f5a1-20261106.4VNdI2f4/'
                    'ACTUAL-RECOVERY-1F92-20261106.f7by6ypz')
OWNER_DISPOSITION = EVIDENCE_DIR/'EXACT-OWNER-ADDITIONAL-PUSH-DISPOSITION-20261106.json'


def source(root, pin, envelope):
    import professional_web_execution as web
    from goal_delivery_runtime import restore_goal

    need = web.need
    need(set(envelope) == {'schema', 'result_receipt'} and envelope['schema'] == SCHEMA,
         'only this exact original material pre-transport expiry is recoverable here')
    receipt_pin = envelope['result_receipt']
    receipt = a.document(root, receipt_pin)
    snapshot = restore_goal(root, w.read_json(w.snapshot_path(root, TASK)))
    events = w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS, where={
        'task_id': TASK, ('details', 'collaboration_receipt'): receipt_pin,
        ('details', 'actual_transport_status'): 'result_received',
    })
    need(receipt_pin in snapshot['goal_delivery'].get('collaboration_records', [])
         and len(events) == 1 and events[0]['details'].get('external_permission_issued') is False
         and receipt.get('task_id') == TASK and receipt.get('status') == 'result_received'
         and receipt.get('source_kind') == 'official_native_queue'
         and receipt.get('recipient_turn_id') == TURN,
         'actual original PUB receipt for the completed WEB expiry is required')
    report = a.document(root, receipt['result'])
    policies = w.read_jsonl(Path(root)/w.POLICY_DECISIONS, where={'decision_id': POLICY})
    need(len(policies) == 1, 'one original consumed push policy')
    policy = policies[0]
    request = a.document(root, policy['exact_request'])
    ctx = web.static_intent(root, request)
    head, base = web.candidate(ctx, request['state'])
    key = w.sha256_value([TASK, ctx['role'], ACTION, web.OPS['git_push'], ctx['scope']])
    need(ctx['task'] == TASK and ctx.get('current_owner_reviewed_release') and ctx['owner'] == 'publishing'
         and receipt.get('target_thread_id') == ctx['binding']['thread_id']
         and receipt.get('scope') == ctx['scope'] == request['scope']
         and request['action_id'] == report.get('action_id') == policy.get('action_id') == ACTION
         and report.get('schema') == 'WEB-materials-original-push-policy-consumed-no-transport-expiry/v1'
         and report.get('task_id') == TASK and report.get('policy_id') == POLICY
         and report.get('git') == request['state'] and report.get('original_action_key') == key
         and report.get('bound_request') == policy['exact_request']
         and report.get('preflight') == policy['source_preflight']
         and policy.get('autonomous_action_key') == key and policy.get('status') == 'allow'
         and policy.get('actual_action_allowed') is True and policy.get('consume_approval') is True
         and policy.get('payload_sha256') == policy['exact_request']['sha256']
         and request.get('operation') == 'git_push'
         and request.get('desired') == {'repository': ctx['repository'], 'branch': ctx['branch'],
                                        'head': head, 'force': False, 'admin_bypass': False},
         'same original action, material source, request, account and policy')
    preflights = w.read_jsonl(Path(root)/w.WORKFLOW_EVENTS, where={'task_id': TASK,
                                                             'event_id': report['preflight_event']})
    need(len(preflights) == 1 and preflights[0]['details'].get('professional_WEB_preflight') ==
         {'action_id': ACTION, 'request': policy['exact_request'], 'input': policy['source_preflight']},
         'original consumed request must match its registered preflight')
    native = receipt['actual_native_result']
    admit = web._recovery_command(root, ctx, native, ADMISSION, controller_admission=True)
    failed = web._recovery_command(root, ctx, native, FAILED, failed=True)
    readback = web._recovery_command(root, ctx, native, READBACK)
    need(all(item[0]['id'] == TURN for item in (admit, failed, readback))
         and admit[1] < failed[1] < readback[1]
         and report.get('transport_wrapper_command_id') == FAILED
         and report.get('readback_command_id') == READBACK,
         'actual completed original WEB admission, guard refusal and remote readback chronology')
    web._output_document(admit[3], policy)
    need(hashlib.sha256(failed[2]['command'].encode()).hexdigest() ==
         'f37aeb4489d40cd6ddb57bb9b11a3ddae603251d28413bde1bbc81a0fe511c61'
         and failed[3] == b'FRESHNESS_EXPIRED_BEFORE_TRANSPORT age_seconds=303.314\n'
         and hashlib.sha256(readback[2]['command'].encode()).hexdigest() ==
         'ea33012856705e1973ff8ac8b0b6b157a8d71b83590f920300bacfd5db4cc87e'
         and readback[3] == (base + '\n[]\n[]\n').encode(),
         'exact refusal before Git and actual same-main missing branch and PR')
    return {'ctx': ctx, 'original_request': request, 'original_policy': policy, 'key': key, 'source': pin}


def additional_policy(root, proof, rows):
    """Bind one new human-authorized issue to both immutable zero-launch records."""
    import professional_web_execution as web
    from goal_delivery_runtime import _native_document

    need=web.need
    ctx=proof['ctx'];first=proof['original_policy']
    need(len(rows)==2 and rows[0]==first and first['decision_id']==POLICY
         and ctx['task']==TASK and proof['original_request']['action_id']==ACTION,
         'only two exact exhausted original material policy rows')
    second=rows[1]
    need(second.get('decision_id')==SECOND_POLICY and second.get('action_id')==ACTION
         and second.get('autonomous_action_key')==proof['key']
         and second.get('recovery_of_policy')==POLICY and second.get('recovery_attempt')==1
         and second.get('known_zero_push_recovery')==proof['source']
         and second.get('actual_action_allowed') is True and second.get('consume_approval') is True,
         'actual consumed first recovery, with immutable prior key')
    pin=w.file_digest(root,str(OWNER_DISPOSITION));record=a.document(root,pin)
    need(set(record)=={'owner','web','report'},'exact disposition evidence fields')
    owner=_native_document(root,record['owner'])
    need(owner['thread']['id']==OWNER_THREAD and owner['thread']['cwd']==str(Path(root).resolve())
         and owner['thread']['hostId']=='local', 'actual original HQ human authorization context')
    turns=owner['turns']
    need(len(turns)==2 and [x['id'] for x in turns]==[OWNER_TURN,REQUEST_TURN]
         and turns[1]['status']=='completed' and turns[0]['startedAt']>=turns[1]['completedAt'],
         'exact sequential owner prompt and reply')
    messages=[x for x in turns[0]['items'] if x.get('type')=='userMessage']
    replies=[x for x in turns[1]['items'] if x.get('phase')=='final_answer']
    need(len(messages)==len(replies)==1 and messages[0]['id']==OWNER_MESSAGE
         and len(messages[0]['content'])==1 and messages[0]['content'][0]['type']=='text'
         and messages[0]['content'][0]['text'].strip()=='允许' and replies[0]['id']==REQUEST_MESSAGE
         and '为这两个材料页的原推送动作额外签发一次单次许可' in replies[0]['text'],
         'human approved only one additional exact push policy')
    report=a.document(root,record['report'])
    old=a.document(root,second['exact_request'])
    need(report.get('schema')=='WEB-materials-original-push-recovery-consumed-no-transport/v1'
         and report.get('task_id')==TASK and report.get('action_id')==ACTION and report.get('key')==proof['key']
         and report.get('original_policy')==POLICY and report.get('consumed_recovery_policy')==SECOND_POLICY
         and report.get('bound_request')==second['exact_request'] and report.get('preflight')==second['source_preflight']
         and report.get('actual_bound_desired')==old['desired']
         and report.get('candidate')==ctx['commit'] and report.get('base')==ctx['base']
         and report.get('git_push_invocations')==0 and report.get('persisted_transport_intent') is False
         and report.get('remote_branch_present') is False and report.get('matching_PRs')==[],
         'exact original WEB report proves second zero launch')
    failed=web._recovery_command(root,ctx,record['web'],report['abort_command_id'],failed=True,controller_admission=True)
    readback=web._recovery_command(root,ctx,record['web'],report['remote_readback_command_id'])
    need(failed[0]['id']==readback[0]['id']==SECOND_TURN and failed[1]<readback[1]
         and hashlib.sha256(failed[2]['command'].encode()).hexdigest()=='54bf84cf5a197c1232806a30890f761cd17d420e3f85abc90d6b92842f2b04b8'
         and ('"policy_id": "'+SECOND_POLICY+'"').encode() in failed[3]
         and failed[3].endswith(b'  File "<stdin>", line 45, in <module>\nAssertionError\n')
         and hashlib.sha256(readback[2]['command'].encode()).hexdigest()=='a575fae3f30013e7a39a93eb5055c228bf80b49013f224cfc3cdaa1051c9b441'
         and readback[3]==(ctx['base']+'\n[]\n[]\n').encode(),
         'completed original WEB turn confirms abort before Git and exact empty remote effect')
    return {'known_zero_push_recovery':proof['source'],'recovery_of_policy':SECOND_POLICY,
            'recovery_attempt':2,'additional_owner_authorization':pin,'owner_message_id':OWNER_MESSAGE}
