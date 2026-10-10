"""Literal three-target zero-CMS-write workflow preparation. No execution/network/issuer."""
from pathlib import Path
import datetime as dt
import original_task_publisher_handover as handover
ROOT=Path('<PROJECT_ROOT>')
TASK='fc-20261008-publisher-three-protected-preview-refresh-v1'
BUSINESS='fc-20260928-keyword-page-answer-implementation-v1'
PROFILE='publishing_three_zero_write_preview_v1'
PUB='<LOCAL_TASK_ID>'
QA='<LOCAL_TASK_ID>'
PROJECT='<LOCAL_PROJECT_ID>'
MAIN='e384666d46467c48355a7cf8f914b128f6215184'
CONTROL_TASK='fc-20261008-publisher-three-preview-call-binding-control-qa-v1'
CV='publisher-three-preview-call-binding-control-v1-20261008'
QA_ACTION='qa-publisher-three-preview-call-binding-control-v1'
QA_SCOPE='project:publisher-three:protected-zero-write-preview-call-control:v1:R0:20261008'
CONTROL_PATH='drafts/operations/fc-20261007-owner-publisher-execution-takeover-v1/three-preview-call-binding-control-candidate-v1-20261008/candidate.json'
OUTBOX_PREFIX='logs/department-outbox/'
RUNTIME_PREFIX='drafts/publishing/'+TASK+'/protected-preview-control-request-v1-20261008/runtime-preflight/'
REQUESTS=[{'item': 'v17', 'pin': {'path': 'drafts/publishing/fc-20261008-publisher-three-protected-preview-refresh-v1/protected-preview-control-request-v1-20261008/v17-exact-zero-write-preview-control-request.json', 'sha256': 'fb8786e29bc2b4512c2d8cef294284e90d56d0ba0e27da1d1273d5b796c062c2', 'size': 4289}, 'value': {'schema_version': '1.0', 'status': 'FROZEN_REQUEST_NOT_ADMITTED_NOT_EXECUTED', 'task_id': 'fc-20261008-publisher-three-protected-preview-refresh-v1', 'candidate_version': 'publisher-three-protected-preview-refresh-v1-20261008', 'original_business_task_id': 'fc-20260928-keyword-page-answer-implementation-v1', 'item': 'v17', 'department': 'publishing', 'fixed_thread_id': '<LOCAL_TASK_ID>', 'original_publish_action_id': 'publish-v17-owner-publisher-native-preparation-v2-20261007', 'preview_request_id': 'preview-v17-owner-publisher-native-preparation-v2-20261007', 'scope': 'flashcast.com.my:services:example-cms-record-1:faqs_en,faqs_zh', 'frozen_candidate_version': 'v17-owner-publisher-native-preparation-v2-20261007', 'candidate': {'path': 'drafts/publishing/fc-20261007-publisher-three-rollback-projection-rework-v1/three-native-preparation-v2-20261007/v17/cms-content-candidate.json', 'sha256': '84dc43809179627bb811068d686eed60eb683b05838dab62b497f19d82342ca0', 'size': 14339}, 'repository': 'wangchaozhuanyong/zhuangxiuwangzhan', 'workflow': '.github/workflows/content-publish-approved.yml', 'ref': 'main', 'expected_main_sha': 'e384666d46467c48355a7cf8f914b128f6215184', 'inputs': {'mode': 'dry-run', 'target': 'v17-owner-publisher-native-preparation-v2-20261007', 'approval_id': 'owner-standing-flashcast-site-publish-20260906', 'managed_operation': 'publish'}, 'input_semantics': 'mode=dry-run exits before execute; managed_operation=publish selects forward preview; no production permit supplied', 'changed_fields': ['faqs_en', 'faqs_zh'], 'row': {'table': 'services', 'record_id': 'example-cms-record-1', 'slug': 'old-house', 'status': 'published', 'observed_version': 1, 'expected_updated_at_raw': '2026-06-08T07:45:35.480828+00:00'}, 'baseline_fields_sha256': 'cc27f87d98e1c3bedaf517fdbe0a8d5ab703b3ba655f05b225a451d12e4e4ee8', 'desired_fields_sha256': '56891d2e9c49d90e665734354d752ac058c028128ef969da9db25c217a6e8f94', 'rollback_fields_sha256': '3a31d956abc417dc0fe04fb3328fff83cdb7202fbe15f8224b1f87bfd5c84af1', 'retained_fields_sha256': '2e8c4496296b8207cae1745c7aaf56f371246e031f5ac7c0be67966a680549b4', 'last_actual_native_source': {'path': 'drafts/publishing/fc-20261007-publisher-three-source-refresh-after-control-v1/native-source-refresh-v1-20261007/v17/native-source-refresh.json', 'sha256': '89d18d01a31063500ea329597ba9e2cc3bcb8aa529dcabd35580938bb045d2c3', 'size': 10382}, 'source_refreshed_this_task': False, 'proposed_argv_not_executed': ['gh', 'workflow', 'run', 'content-publish-approved.yml', '-R', 'wangchaozhuanyong/zhuangxiuwangzhan', '--ref', 'main', '-f', 'mode=dry-run', '-f', 'target=v17-owner-publisher-native-preparation-v2-20261007', '-f', 'approval_id=owner-standing-flashcast-site-publish-20260906', '-f', 'managed_operation=publish'], 'expected_artifact_name': 'approved-content-publish-<actual_run_id>', 'required_target_artifacts': ['locked-dry-run-receipt.json', 'managed-payload-digest.json', 'rollback-payload-digest.json', 'managed-identity-probe.json', 'backup.json'], 'mandatory_validations': {'main_sha_unchanged': True, 'current_raw_CAS_unchanged': True, 'exact_two_changed_fields': True, 'http_status': 200, 'dry_run': True, 'performed_write': False, 'external_writes': 0, 'row_unchanged_after_dry_run': True, 'identity_repository_id': 1248188229, 'identity_actor_id': 276684684, 'identity_workflow_sha_matches_main': True, 'payload_and_rollback_hashes_match_frozen': True, 'freshness_at_permit_issue_minutes_max': 30}, 'forbidden': ['mode=publish', '--execute', 'permit issuance/consumption', 'ordinary Save', 'code changes/push/merge/deploy', 'account changes', 'other targets/rows/fields', 'token/cookie copying'], 'required_minimum_control_next_action': 'operations obtain independently reviewed exact zero-write workflow invocation admission for publishing; do not reinterpret native-read admission or existing code-CI rule'}}, {'item': 'v18', 'pin': {'path': 'drafts/publishing/fc-20261008-publisher-three-protected-preview-refresh-v1/protected-preview-control-request-v1-20261008/v18-exact-zero-write-preview-control-request.json', 'sha256': '3089a197ffd180a9caa3fd0724ac94e135b9ed3734e7bf7070646ad92a891184', 'size': 4335}, 'value': {'schema_version': '1.0', 'status': 'FROZEN_REQUEST_NOT_ADMITTED_NOT_EXECUTED', 'task_id': 'fc-20261008-publisher-three-protected-preview-refresh-v1', 'candidate_version': 'publisher-three-protected-preview-refresh-v1-20261008', 'original_business_task_id': 'fc-20260928-keyword-page-answer-implementation-v1', 'item': 'v18', 'department': 'publishing', 'fixed_thread_id': '<LOCAL_TASK_ID>', 'original_publish_action_id': 'publish-v18-owner-publisher-native-preparation-v2-20261007', 'preview_request_id': 'preview-v18-owner-publisher-native-preparation-v2-20261007', 'scope': 'flashcast.com.my:blog_posts:example-cms-record-2:content_en,content_zh', 'frozen_candidate_version': 'v18-owner-publisher-native-preparation-v2-20261007', 'candidate': {'path': 'drafts/publishing/fc-20261007-publisher-three-rollback-projection-rework-v1/three-native-preparation-v2-20261007/v18/cms-content-candidate.json', 'sha256': '0d3dbaec1c183979e58969dfced524b104f08c92800123c0ea545b8f9f73b02e', 'size': 23706}, 'repository': 'wangchaozhuanyong/zhuangxiuwangzhan', 'workflow': '.github/workflows/content-publish-approved.yml', 'ref': 'main', 'expected_main_sha': 'e384666d46467c48355a7cf8f914b128f6215184', 'inputs': {'mode': 'dry-run', 'target': 'v18-owner-publisher-native-preparation-v2-20261007', 'approval_id': 'owner-standing-flashcast-site-publish-20260906', 'managed_operation': 'publish'}, 'input_semantics': 'mode=dry-run exits before execute; managed_operation=publish selects forward preview; no production permit supplied', 'changed_fields': ['content_en', 'content_zh'], 'row': {'table': 'blog_posts', 'record_id': 'example-cms-record-2', 'slug': 'renovation-quotation-checklist-malaysia', 'status': 'published', 'observed_version': 1, 'expected_updated_at_raw': '2026-09-25T20:54:18.773194+00:00'}, 'baseline_fields_sha256': 'ae53dcc1a90fee545ee189a3ce8cde1a1d755f27cefdd1c41accedcaf0513d0a', 'desired_fields_sha256': '0b63be321e97797d65df2dcbf123279b5aec0e43f1929bafd97c1e589d2acbea', 'rollback_fields_sha256': '5b86bcfae21a0bbe685a2cf133428a8a86b190ab5900f9fa8bf29af4f9d52fee', 'retained_fields_sha256': 'f9567fe044a9f8123e1069e2d3a0e692f4a51d207c018cefdbd543cf111970ea', 'last_actual_native_source': {'path': 'drafts/publishing/fc-20261007-publisher-three-source-refresh-after-control-v1/native-source-refresh-v1-20261007/v18/native-source-refresh.json', 'sha256': '80de25191eabdbdfa8c8491a1cdf9171647c899d5016a1ba477a67ae838827c1', 'size': 10335}, 'source_refreshed_this_task': False, 'proposed_argv_not_executed': ['gh', 'workflow', 'run', 'content-publish-approved.yml', '-R', 'wangchaozhuanyong/zhuangxiuwangzhan', '--ref', 'main', '-f', 'mode=dry-run', '-f', 'target=v18-owner-publisher-native-preparation-v2-20261007', '-f', 'approval_id=owner-standing-flashcast-site-publish-20260906', '-f', 'managed_operation=publish'], 'expected_artifact_name': 'approved-content-publish-<actual_run_id>', 'required_target_artifacts': ['locked-dry-run-receipt.json', 'managed-payload-digest.json', 'rollback-payload-digest.json', 'managed-identity-probe.json', 'backup.json'], 'mandatory_validations': {'main_sha_unchanged': True, 'current_raw_CAS_unchanged': True, 'exact_two_changed_fields': True, 'http_status': 200, 'dry_run': True, 'performed_write': False, 'external_writes': 0, 'row_unchanged_after_dry_run': True, 'identity_repository_id': 1248188229, 'identity_actor_id': 276684684, 'identity_workflow_sha_matches_main': True, 'payload_and_rollback_hashes_match_frozen': True, 'freshness_at_permit_issue_minutes_max': 30}, 'forbidden': ['mode=publish', '--execute', 'permit issuance/consumption', 'ordinary Save', 'code changes/push/merge/deploy', 'account changes', 'other targets/rows/fields', 'token/cookie copying'], 'required_minimum_control_next_action': 'operations obtain independently reviewed exact zero-write workflow invocation admission for publishing; do not reinterpret native-read admission or existing code-CI rule'}}, {'item': 'v20', 'pin': {'path': 'drafts/publishing/fc-20261008-publisher-three-protected-preview-refresh-v1/protected-preview-control-request-v1-20261008/v20-exact-zero-write-preview-control-request.json', 'sha256': 'eb04bd605fb4afcdcdbc7c6db6f3ba23b507504a3565e7273ed2a9df83cd04b6', 'size': 4286}, 'value': {'schema_version': '1.0', 'status': 'FROZEN_REQUEST_NOT_ADMITTED_NOT_EXECUTED', 'task_id': 'fc-20261008-publisher-three-protected-preview-refresh-v1', 'candidate_version': 'publisher-three-protected-preview-refresh-v1-20261008', 'original_business_task_id': 'fc-20260928-keyword-page-answer-implementation-v1', 'item': 'v20', 'department': 'publishing', 'fixed_thread_id': '<LOCAL_TASK_ID>', 'original_publish_action_id': 'publish-v20-owner-publisher-native-preparation-v2-20261007', 'preview_request_id': 'preview-v20-owner-publisher-native-preparation-v2-20261007', 'scope': 'flashcast.com.my:services:example-cms-record-3:faqs_en,faqs_zh', 'frozen_candidate_version': 'v20-owner-publisher-native-preparation-v2-20261007', 'candidate': {'path': 'drafts/publishing/fc-20261007-publisher-three-rollback-projection-rework-v1/three-native-preparation-v2-20261007/v20/cms-content-candidate.json', 'sha256': '58b554e334381fbbc37da2b10b30a25edafa3db709f2c6d5c071308f4193130b', 'size': 14544}, 'repository': 'wangchaozhuanyong/zhuangxiuwangzhan', 'workflow': '.github/workflows/content-publish-approved.yml', 'ref': 'main', 'expected_main_sha': 'e384666d46467c48355a7cf8f914b128f6215184', 'inputs': {'mode': 'dry-run', 'target': 'v20-owner-publisher-native-preparation-v2-20261007', 'approval_id': 'owner-standing-flashcast-site-publish-20260906', 'managed_operation': 'publish'}, 'input_semantics': 'mode=dry-run exits before execute; managed_operation=publish selects forward preview; no production permit supplied', 'changed_fields': ['faqs_en', 'faqs_zh'], 'row': {'table': 'services', 'record_id': 'example-cms-record-3', 'slug': 'design', 'status': 'published', 'observed_version': 1, 'expected_updated_at_raw': '2026-09-24T16:55:25.345204+00:00'}, 'baseline_fields_sha256': '5356b7c855efa2cc68973556ffb3ac6017aaf167025d7223773101b5da9f5d68', 'desired_fields_sha256': '0fc23b7d728f9a715cf2f1142feaa549e49d3a218f968486b3147878dfb6c7eb', 'rollback_fields_sha256': '17fa4ffffcc155496337da6f2e10ac0ebd84d488f4e14351e7346c6bce8630b9', 'retained_fields_sha256': '8f079351ad38ad880829e7e46f9dda322e60c796d60af3535ed2309274ba2d46', 'last_actual_native_source': {'path': 'drafts/publishing/fc-20261007-publisher-three-source-refresh-after-control-v1/native-source-refresh-v1-20261007/v20/native-source-refresh.json', 'sha256': '990878d86b6ed2576635439872cf15a74465c3af70824a0959b4983dd2706ca6', 'size': 11854}, 'source_refreshed_this_task': False, 'proposed_argv_not_executed': ['gh', 'workflow', 'run', 'content-publish-approved.yml', '-R', 'wangchaozhuanyong/zhuangxiuwangzhan', '--ref', 'main', '-f', 'mode=dry-run', '-f', 'target=v20-owner-publisher-native-preparation-v2-20261007', '-f', 'approval_id=owner-standing-flashcast-site-publish-20260906', '-f', 'managed_operation=publish'], 'expected_artifact_name': 'approved-content-publish-<actual_run_id>', 'required_target_artifacts': ['locked-dry-run-receipt.json', 'managed-payload-digest.json', 'rollback-payload-digest.json', 'managed-identity-probe.json', 'backup.json'], 'mandatory_validations': {'main_sha_unchanged': True, 'current_raw_CAS_unchanged': True, 'exact_two_changed_fields': True, 'http_status': 200, 'dry_run': True, 'performed_write': False, 'external_writes': 0, 'row_unchanged_after_dry_run': True, 'identity_repository_id': 1248188229, 'identity_actor_id': 276684684, 'identity_workflow_sha_matches_main': True, 'payload_and_rollback_hashes_match_frozen': True, 'freshness_at_permit_issue_minutes_max': 30}, 'forbidden': ['mode=publish', '--execute', 'permit issuance/consumption', 'ordinary Save', 'code changes/push/merge/deploy', 'account changes', 'other targets/rows/fields', 'token/cookie copying'], 'required_minimum_control_next_action': 'operations obtain independently reviewed exact zero-write workflow invocation admission for publishing; do not reinterpret native-read admission or existing code-CI rule'}}]
PUBLISHER_OUTBOX={'path': 'logs/department-outbox/fc-20261008-publisher-three-protected-preview-refresh-v1-publishing-publisher-three-protected-preview-refresh-v1-20261008-v2.json', 'sha256': '5d1836b169d032c547f388b64761034f45d987ef729d943f08152e20f61455c1', 'size': 12560}
MANIFEST={'path': 'drafts/operations/fc-20261007-owner-publisher-execution-takeover-v1/publisher-production-readiness-control-v2-20261007/final-admission-manifest.json', 'sha256': 'd4cdeb41b19948f4bcec78e501593b456fdd462a1cd976635e7e03f454bbb213', 'size': 11805}
SOURCE_VERIFICATION={'path': 'drafts/operations/fc-20261007-owner-publisher-execution-takeover-v1/three-preview-call-binding-source-verification-v1-20261008/source-verification.json', 'sha256': 'c6baeff251408ee15402f3db786002a798941b94ad9630d4851e0f5368a475c7', 'size': 6055}


def require(ok,reason):
    if not ok:raise ValueError(reason)


def pinned(root,w,p):
    require(isinstance(p,dict) and set(p)=={'path','sha256','size'},'preview_exact_pin_required')
    require(w.file_digest(root,p['path'])==p,'preview_frozen_current_bytes_changed')
    return w.read_json(w.safe_path(root,p['path']))


def handles(task_id,action_id):
    # Known action stays in this guard even with a wrong task/role/scope.
    return action_id in {r['value']['preview_request_id'] for r in REQUESTS} or task_id==TASK


def validate_argv(request,argv):
    expected=['gh','workflow','run','content-publish-approved.yml','-R','wangchaozhuanyong/zhuangxiuwangzhan','--ref','main',
       '-f','mode=dry-run','-f','target='+request['frozen_candidate_version'],
       '-f','approval_id=owner-standing-flashcast-site-publish-20260906','-f','managed_operation=publish']
    require(request['inputs']=={'mode':'dry-run','target':request['frozen_candidate_version'],
       'approval_id':'owner-standing-flashcast-site-publish-20260906','managed_operation':'publish'}
       and type(argv) is list and argv==expected,'preview_only_exact_four_input_zero_write_argv')
    return expected


def validate_request(request,entry):
    require(type(request) is dict and set(request)==set(entry['value']) and request==entry['value'],
       'preview_complete_literal_request_required')
    validate_argv(request,request['proposed_argv_not_executed'])
    flags=request['mandatory_validations']
    require(all(type(flags[k]) is bool and flags[k] is v for k,v in {
       'main_sha_unchanged':True,'current_raw_CAS_unchanged':True,'exact_two_changed_fields':True,
       'dry_run':True,'performed_write':False,'row_unchanged_after_dry_run':True,
       'identity_workflow_sha_matches_main':True,'payload_and_rollback_hashes_match_frozen':True}.items())
       and type(flags['external_writes']) is int and flags['external_writes']==0,'preview_strict_boolean_and_zero_flags_required')


def publisher_source(root,w):
    box=pinned(root,w,PUBLISHER_OUTBOX);pinned(root,w,SOURCE_VERIFICATION)
    require(box.get('task_id')==TASK and box.get('department')=='publishing' and box.get('fixed_chat_task_id')==PUB
       and box.get('candidate_version')=='publisher-three-protected-preview-refresh-v1-20261008'
       and box.get('production_write_allowed') is False,'preview_exact_publisher_source_required')
    rows,invalid=w._validate_receipt_chain(root,TASK)
    require(not invalid and not w.validate_workflow_events(root,TASK),'preview_publisher_native_chains_invalid')
    sent=next((r for r in rows if r.get('receipt_id')==box['dispatch_receipt_id']),{})
    ack=next((r for r in rows if r.get('receipt_id')==box['ACK_receipt_id']),{})
    require(sent.get('receipt_type')=='dispatch_sent' and ack.get('receipt_type')=='chat_ack'
       and rows.index(sent)<rows.index(ack) and ack.get('ack_nonempty') is True
       and all(all(r.get(k)==v for k,v in {'task_id':TASK,'department':'publishing','chat_task_id':PUB,
          'action_id':box['action_id'],'action_class':box['action_class'],'scope':box['scope']}.items()) for r in [sent,ack]),
       'preview_exact_publisher_dispatch_nonempty_ACK_required')
    for p in sent.get('evidence',[])+ack.get('evidence',[]):pinned(root,w,p)
    require(any(i>rows.index(ack) and r.get('receipt_type')=='outbox_received' and r.get('department')=='publishing'
       and PUBLISHER_OUTBOX in r.get('evidence',[]) for i,r in enumerate(rows)),'preview_exact_received_publisher_outbox_required')
    native=box['native_reply_binding'];proof=pinned(root,w,native['source_proof'])
    reply=box['chat_reply']
    require(proof.get('thread_id')==PUB and proof.get('nonempty') is True
       and proof.get('source_method')=='mcp__codex_app__read_thread'
       and proof.get('reply_sha256',proof.get('source_reply_sha256'))==reply['reply_sha256']
       and native.get('source_thread_id')==PUB and reply.get('reported_before_outbox') is True,
       'preview_actual_publisher_native_reply_proof_required')
    hq=w._result_handoff_rows(root,TASK)
    exact=[r for r in hq if r.get('outbox')==PUBLISHER_OUTBOX and r.get('result_sha256')==PUBLISHER_OUTBOX['sha256']]
    require(any(r.get('record_id')=='d96be6dc-87f8-46af-a763-6ffa6b21caac' and r.get('event')=='controller_received' for r in exact)
       and any(r.get('record_id')=='b632c419-00d6-4868-80e8-5f5378a3b37e' and r.get('event')=='controller_decision'
          and r.get('decision')=='rework' and r.get('next_owner')=='operations-assistant' for r in exact),
       'preview_real_HQ_source_rework_required')


def control_approval(root,w,a):
    require(set(a)=={'status','control_candidate','control_QA_outbox','control_QA_receipt_id','controller_received_record_id',
       'controller_decision_record_id'},'preview_complete_control_acceptance_required')
    require(a['status']=='approved_exact_zero_write_preview_only','preview_HQ_adoption_pending')
    cp=a['control_candidate'];control=pinned(root,w,cp)
    require(cp['path']==CONTROL_PATH and control.get('task_id')==CONTROL_TASK and control.get('candidate_version')==CV
       and control.get('department')=='operations-assistant' and control.get('risk_level')=='R0'
       and control.get('publisher_source_outbox')==PUBLISHER_OUTBOX and control.get('profile')==PROFILE and control.get('requests')==[r['pin'] for r in REQUESTS]
       and control.get('production_write_allowed') is False,'preview_exact_new_control_candidate_required')
    qp=a['control_QA_outbox'];box=pinned(root,w,qp);rows,invalid=w._validate_receipt_chain(root,CONTROL_TASK)
    require(not invalid and not w.validate_workflow_events(root,CONTROL_TASK),'preview_control_QA_chains_invalid')
    latest=[r for r in rows if r.get('receipt_type')=='qa_verdict' and r.get('department')=='qa']
    require(latest and latest[-1].get('receipt_id')==a['control_QA_receipt_id'],'preview_latest_exact_control_QA_required')
    verdict=latest[-1]
    require(all(verdict.get(k)==v for k,v in {'task_id':CONTROL_TASK,'department':'qa','chat_task_id':QA,
       'verdict':'pass','action_id':QA_ACTION,'action_class':'internal_control_candidate','scope':QA_SCOPE}.items())
       and qp in verdict.get('evidence',[]),'preview_exact_control_QA_pass_pin_required')
    before=rows[:rows.index(verdict)];sends=[(i,r) for i,r in enumerate(before) if all(r.get(k)==v for k,v in {
       'receipt_type':'dispatch_sent','task_id':CONTROL_TASK,'department':'qa','chat_task_id':QA,'action_id':QA_ACTION,
       'action_class':'internal_control_candidate','scope':QA_SCOPE}.items())]
    require(sends,'preview_control_QA_native_dispatch_required');i,sent=sends[-1]
    acks=[(j,r) for j,r in enumerate(before) if j>i and r.get('receipt_type')=='chat_ack' and r.get('department')=='qa'
       and r.get('chat_task_id')==QA and r.get('ack_nonempty') is True
       and r.get('task_id')==CONTROL_TASK and r.get('action_id')==QA_ACTION
       and r.get('action_class')=='internal_control_candidate' and r.get('scope')==QA_SCOPE]
    require(acks and any(j>acks[-1][0] and r.get('receipt_type')=='outbox_received' and r.get('department')=='qa'
       and r.get('chat_task_id')==QA and r.get('task_id')==CONTROL_TASK
       and r.get('action_id')==QA_ACTION and r.get('action_class')=='internal_control_candidate'
       and r.get('scope')==QA_SCOPE and qp in r.get('evidence',[]) for j,r in enumerate(before)),
       'preview_same_current_control_QA_ACK_received_PASS_required')
    require(sent.get('evidence') and acks[-1][1].get('evidence'),'preview_control_QA_native_send_ACK_proofs_missing')
    for p in sent['evidence']+acks[-1][1]['evidence']:pinned(root,w,p)
    require(str(qp['path']).startswith(OUTBOX_PREFIX),'preview_native_QA_outbox_location_required');w.validate_outbox(root,[qp],'qa',CONTROL_TASK)
    require(all(box.get(k)==v for k,v in {'task_id':CONTROL_TASK,'department':'qa','fixed_chat_task_id':QA,
       'status':'completed','action_id':QA_ACTION,'action_class':'internal_control_candidate','scope':QA_SCOPE,
       'candidate_version':CV,'candidate_path':CONTROL_PATH,'candidate_sha256':cp['sha256'],'qa_verdict':'pass','risk_level':'R0',
       'production_write_allowed':False,'production_release_eligible':False}.items())
       and box.get('verdict',box.get('qa_verdict'))=='pass' and cp in box.get('evidence',[])
       and all(r['pin'] in box.get('evidence',[]) for r in REQUESTS),'preview_same_current_QA_JSON_candidate_requests_required')
    require(box.get('chat_reply',{}).get('thread_id')==QA and box['chat_reply'].get('nonempty') is True
       and box['chat_reply'].get('reported_before_outbox') is True,'preview_native_QA_report_first_required')
    hq=w._result_handoff_rows(root,CONTROL_TASK)
    exact=[r for r in hq if r.get('sender_department')=='qa' and r.get('candidate_version')==CV
       and r.get('result_sha256')==qp['sha256'] and r.get('outbox')==qp]
    received=next((r for r in exact if r.get('record_id')==a['controller_received_record_id'] and r.get('event')=='controller_received'),{})
    decision=next((r for r in exact if r.get('record_id')==a['controller_decision_record_id'] and r.get('event')=='controller_decision'),{})
    require(received and decision and received.get('intake_mode')=='queue' and exact.index(received)<exact.index(decision)
       and any(r.get('event')=='notification_queued' for r in exact[:exact.index(received)])
       and decision.get('decision')=='continue' and decision.get('next_owner') in {'publishing','operations-assistant'}
       and bool(decision.get('next_action')) and cp in decision.get('evidence',[]) and qp in decision.get('evidence',[]),
       'preview_actual_HQ_exact_control_adoption_required')


def current_context(root,w,request):
    runtime_path=RUNTIME_PREFIX+request['item']+'-current-main-workflow.json'
    observation=pinned(root,w,w.file_digest(root,runtime_path))
    require(set(observation)=={'schema_version','task_id','item','source_method','observed_at_utc','repository','main_sha',
       'expected_sha','main_matches','workflow','workflow_git_blob_sha'}
       and observation.get('schema_version')=='publisher_three_preview_runtime_preflight_v1'
       and observation.get('task_id')==TASK and observation.get('item')==request['item']
       and observation.get('source_method')=='existing_authenticated_gh_api_metadata_reads'
       and observation['workflow']['path']==RUNTIME_PREFIX+request['item']+'-current-workflow.yml',
       'preview_per_action_literal_runtime_metadata_shape_required')
    stamp=w._parse_observed_at(observation.get('observed_at_utc'))
    now=dt.datetime.now(dt.timezone.utc)
    require(stamp and dt.timedelta()<=now-stamp<=dt.timedelta(minutes=5)
       and observation.get('repository')==request['repository'] and observation.get('main_sha')==MAIN
       and observation.get('expected_sha')==MAIN and observation.get('main_matches') is True
       and observation.get('workflow_git_blob_sha')=='cc066a558073f0894621ff8138db6e24dc6c159d',
       'preview_fresh_exact_main_workflow_observation_required')
    workflow=pinned_text(root,w,observation['workflow'])
    require(observation['workflow']['sha256']=='57ef63b435baf5f98d14d8d4996dbf6a4fb27f7bfa4497e3be0e967127c1616e',
       'preview_exact_workflow_bytes_required')
    source=pinned(root,w,request['last_actual_native_source']);row=source['record']
    require(row.get('id')==request['row']['record_id'] and row.get('updated_at')==request['row']['expected_updated_at_raw']
       and row.get('version')==request['row']['observed_version'] and row.get('status')=='published',
       'preview_exact_raw_CAS_source_required')
    manifest=pinned(root,w,MANIFEST);entry=next(e for e in manifest['entries'] if e['item']==request['item'])
    require(request['candidate']==entry['publisher_candidate'] and request['changed_fields']==entry['changed_fields']
       and all(request[k]==entry[k] for k in ['baseline_fields_sha256','desired_fields_sha256','rollback_fields_sha256','retained_fields_sha256']),
       'preview_exact_CV_candidate_two_fields_hashes_required')
    pinned(root,w,request['candidate'])
    b=handover.binding(root,BUSINESS)
    require(b and request['frozen_candidate_version'] in b['targets'],'preview_native_owner_execution_only_binding_required')


def pinned_text(root,w,p):
    require(w.file_digest(root,p['path'])==p,'preview_workflow_copy_pin_changed')
    return w.safe_path(root,p['path']).read_text()



COMPLETED_PROFILE='completed_successor_readback_v2'
COMPLETED_REQUESTS=[{'item': 'v17', 'pin': {'path': 'logs/handoffs/2026-10-10-goal-delivery-assistant-runtime-v1/developer/original-cms-development-followthrough-v1/requests/v17-completed-successor-readback.json', 'sha256': 'ccba302295218fe39ecf1c888d447585e3be15579df7eaa6560ee9f367784e3b', 'size': 3114}, 'value': {'schema_version': '1.0', 'control_task_id': 'fc-20261010-assistant2-original-cms-development-followthrough-v1', 'original_business_task_id': 'fc-20260928-keyword-page-answer-implementation-v1', 'original_preparation_task_id': 'fc-20261008-publisher-three-protected-preview-refresh-v1', 'item': 'v17', 'department': 'publishing', 'action_id': 'preview-v17-owner-publisher-native-preparation-v2-20261007', 'scope': 'flashcast.com.my:services:example-cms-record-1:faqs_en,faqs_zh', 'profile': 'completed_successor_readback_v2', 'status': 'retired_completed', 'original_request': {'path': 'drafts/publishing/fc-20261008-publisher-three-protected-preview-refresh-v1/protected-preview-control-request-v1-20261008/v17-exact-zero-write-preview-control-request.json', 'sha256': 'fb8786e29bc2b4512c2d8cef294284e90d56d0ba0e27da1d1273d5b796c062c2', 'size': 4289}, 'original_candidate': {'path': 'drafts/publishing/fc-20261007-publisher-three-rollback-projection-rework-v1/three-native-preparation-v2-20261007/v17/cms-content-candidate.json', 'sha256': '84dc43809179627bb811068d686eed60eb683b05838dab62b497f19d82342ca0', 'size': 14339}, 'successor_guard': {'path': 'logs/handoffs/2026-10-10-goal-delivery-assistant-runtime-v1/developer/original-cms-development-followthrough-v1/evidence/cms-37903094390-completed-nine-rows-fresh-guard.json', 'sha256': 'a34295e935952bb64e59c2cb740e1dac609b267a661590de402901846ce488b0', 'size': 52719}, 'successor_field_linkage': {'path': 'logs/handoffs/2026-10-10-goal-delivery-assistant-runtime-v1/developer/original-cms-development-followthrough-v1/evidence/successor-field-linkage.json', 'sha256': 'fdec7895e66a4f474ff9196c23339bcf49f5919b2e92b881901d1b701638502e', 'size': 8039}, 'assistant_acceptance': {'path': 'logs/handoffs/2026-10-10-goal-delivery-assistant-runtime-v1/developer/original-cms-development-followthrough-v1/requests/assistant2-acceptance-binding.json', 'sha256': '5753ad17d872c0281eb3b4ab125c275968934169c5410bcade329d7250a2c979', 'size': 606}, 'successor': {'target': 'v17-owner-publisher-native-preparation-v2-20261007', 'origin_run_id': 37893433883, 'saved_updated_at': '2026-10-09T06:25:51.005255+00:00', 'desired_fields_sha256': '56891d2e9c49d90e665734354d752ac058c028128ef969da9db25c217a6e8f94', 'original_desired_fields_sha256': '56891d2e9c49d90e665734354d752ac058c028128ef969da9db25c217a6e8f94', 'original_changed_fields': ['faqs_en', 'faqs_zh'], 'observed_at': '2026-10-09T08:08:40.870Z', 'completed_stage': 'COMPLETED_ROW_GUARD_PASS', 'permit_status': 'FRESH_COMPLETED'}, 'production_write_allowed': False, 'preview_execution_allowed': False, 'save_allowed': False, 'permit_issuance_allowed': False, 'permit_consumption_allowed': False, 'can_generate_argv': False, 'current_CMS_read_this_batch': False, 'website_code_change_required': False, 'restoration': 'new forward correction only after actual fresh row CAS; no old snapshot/permit/target replay'}}, {'item': 'v18', 'pin': {'path': 'logs/handoffs/2026-10-10-goal-delivery-assistant-runtime-v1/developer/original-cms-development-followthrough-v1/requests/v18-completed-successor-readback.json', 'sha256': '284aab909f9f2239a4b57dc80a07557d842c89ebfba5390d8f38d3dbfd0958da', 'size': 3128}, 'value': {'schema_version': '1.0', 'control_task_id': 'fc-20261010-assistant2-original-cms-development-followthrough-v1', 'original_business_task_id': 'fc-20260928-keyword-page-answer-implementation-v1', 'original_preparation_task_id': 'fc-20261008-publisher-three-protected-preview-refresh-v1', 'item': 'v18', 'department': 'publishing', 'action_id': 'preview-v18-owner-publisher-native-preparation-v2-20261007', 'scope': 'flashcast.com.my:blog_posts:example-cms-record-2:content_en,content_zh', 'profile': 'completed_successor_readback_v2', 'status': 'retired_completed', 'original_request': {'path': 'drafts/publishing/fc-20261008-publisher-three-protected-preview-refresh-v1/protected-preview-control-request-v1-20261008/v18-exact-zero-write-preview-control-request.json', 'sha256': '3089a197ffd180a9caa3fd0724ac94e135b9ed3734e7bf7070646ad92a891184', 'size': 4335}, 'original_candidate': {'path': 'drafts/publishing/fc-20261007-publisher-three-rollback-projection-rework-v1/three-native-preparation-v2-20261007/v18/cms-content-candidate.json', 'sha256': '0d3dbaec1c183979e58969dfced524b104f08c92800123c0ea545b8f9f73b02e', 'size': 23706}, 'successor_guard': {'path': 'logs/handoffs/2026-10-10-goal-delivery-assistant-runtime-v1/developer/original-cms-development-followthrough-v1/evidence/cms-37903094390-completed-nine-rows-fresh-guard.json', 'sha256': 'a34295e935952bb64e59c2cb740e1dac609b267a661590de402901846ce488b0', 'size': 52719}, 'successor_field_linkage': {'path': 'logs/handoffs/2026-10-10-goal-delivery-assistant-runtime-v1/developer/original-cms-development-followthrough-v1/evidence/successor-field-linkage.json', 'sha256': 'fdec7895e66a4f474ff9196c23339bcf49f5919b2e92b881901d1b701638502e', 'size': 8039}, 'assistant_acceptance': {'path': 'logs/handoffs/2026-10-10-goal-delivery-assistant-runtime-v1/developer/original-cms-development-followthrough-v1/requests/assistant2-acceptance-binding.json', 'sha256': '5753ad17d872c0281eb3b4ab125c275968934169c5410bcade329d7250a2c979', 'size': 606}, 'successor': {'target': 'v18-owner-publisher-native-preparation-v2-20261007', 'origin_run_id': 37893433883, 'saved_updated_at': '2026-10-09T06:26:00.016334+00:00', 'desired_fields_sha256': '0b63be321e97797d65df2dcbf123279b5aec0e43f1929bafd97c1e589d2acbea', 'original_desired_fields_sha256': '0b63be321e97797d65df2dcbf123279b5aec0e43f1929bafd97c1e589d2acbea', 'original_changed_fields': ['content_en', 'content_zh'], 'observed_at': '2026-10-09T08:08:40.870Z', 'completed_stage': 'COMPLETED_ROW_GUARD_PASS', 'permit_status': 'FRESH_COMPLETED'}, 'production_write_allowed': False, 'preview_execution_allowed': False, 'save_allowed': False, 'permit_issuance_allowed': False, 'permit_consumption_allowed': False, 'can_generate_argv': False, 'current_CMS_read_this_batch': False, 'website_code_change_required': False, 'restoration': 'new forward correction only after actual fresh row CAS; no old snapshot/permit/target replay'}}, {'item': 'v20', 'pin': {'path': 'logs/handoffs/2026-10-10-goal-delivery-assistant-runtime-v1/developer/original-cms-development-followthrough-v1/requests/v20-completed-successor-readback.json', 'sha256': '2d9ba1b84e9094e836be602dcd0bd05e30e059feae2cadc65b518fb9ad7c4feb', 'size': 3102}, 'value': {'schema_version': '1.0', 'control_task_id': 'fc-20261010-assistant2-original-cms-development-followthrough-v1', 'original_business_task_id': 'fc-20260928-keyword-page-answer-implementation-v1', 'original_preparation_task_id': 'fc-20261008-publisher-three-protected-preview-refresh-v1', 'item': 'v20', 'department': 'publishing', 'action_id': 'preview-v20-owner-publisher-native-preparation-v2-20261007', 'scope': 'flashcast.com.my:services:example-cms-record-3:faqs_en,faqs_zh', 'profile': 'completed_successor_readback_v2', 'status': 'superseded_completed', 'original_request': {'path': 'drafts/publishing/fc-20261008-publisher-three-protected-preview-refresh-v1/protected-preview-control-request-v1-20261008/v20-exact-zero-write-preview-control-request.json', 'sha256': 'eb04bd605fb4afcdcdbc7c6db6f3ba23b507504a3565e7273ed2a9df83cd04b6', 'size': 4286}, 'original_candidate': {'path': 'drafts/publishing/fc-20261007-publisher-three-rollback-projection-rework-v1/three-native-preparation-v2-20261007/v20/cms-content-candidate.json', 'sha256': '58b554e334381fbbc37da2b10b30a25edafa3db709f2c6d5c071308f4193130b', 'size': 14544}, 'successor_guard': {'path': 'logs/handoffs/2026-10-10-goal-delivery-assistant-runtime-v1/developer/original-cms-development-followthrough-v1/evidence/cms-37903094390-completed-nine-rows-fresh-guard.json', 'sha256': 'a34295e935952bb64e59c2cb740e1dac609b267a661590de402901846ce488b0', 'size': 52719}, 'successor_field_linkage': {'path': 'logs/handoffs/2026-10-10-goal-delivery-assistant-runtime-v1/developer/original-cms-development-followthrough-v1/evidence/successor-field-linkage.json', 'sha256': 'fdec7895e66a4f474ff9196c23339bcf49f5919b2e92b881901d1b701638502e', 'size': 8039}, 'assistant_acceptance': {'path': 'logs/handoffs/2026-10-10-goal-delivery-assistant-runtime-v1/developer/original-cms-development-followthrough-v1/requests/assistant2-acceptance-binding.json', 'sha256': '5753ad17d872c0281eb3b4ab125c275968934169c5410bcade329d7250a2c979', 'size': 606}, 'successor': {'target': 'design-body-faq-unified-20261009-v1', 'origin_run_id': 37898568406, 'saved_updated_at': '2026-10-09T07:22:50.912627+00:00', 'desired_fields_sha256': 'cc86fb6efa12a41424b94b90aa8c9797586a110bf02b2367b9758300791300c9', 'original_desired_fields_sha256': '0fc23b7d728f9a715cf2f1142feaa549e49d3a218f968486b3147878dfb6c7eb', 'original_changed_fields': ['faqs_en', 'faqs_zh'], 'observed_at': '2026-10-09T08:08:40.870Z', 'completed_stage': 'COMPLETED_ROW_GUARD_PASS', 'permit_status': 'FRESH_COMPLETED'}, 'production_write_allowed': False, 'preview_execution_allowed': False, 'save_allowed': False, 'permit_issuance_allowed': False, 'permit_consumption_allowed': False, 'can_generate_argv': False, 'current_CMS_read_this_batch': False, 'website_code_change_required': False, 'restoration': 'new forward correction only after actual fresh row CAS; no old snapshot/permit/target replay'}}]


def completed_successor_readback(root,w,policy,*,task_id,department,action_id,scope,payload_sha256):
    """Read archival completion bindings; always rejects execution and never returns argv."""
    require(Path(root).resolve()==ROOT and task_id==TASK and department=='publishing',
       'completed_readback_exact_task_and_actor_required')
    entries=[r for r in COMPLETED_REQUESTS if r['value']['action_id']==action_id and r['value']['scope']==scope]
    require(len(entries)==1,'completed_readback_exact_action_scope_required')
    entry=entries[0];request=pinned(root,w,entry['pin'])
    require(request==entry['value'] and payload_sha256==entry['pin']['sha256'],'completed_readback_exact_payload_required')
    expected={'task_id':TASK,'department':'publishing','action_id':action_id,'scope':scope,'profile':COMPLETED_PROFILE,
       'request_path':entry['pin']['path'],'request_sha256':entry['pin']['sha256'],'control_acceptance':request['assistant_acceptance']}
    bindings=[b for b in policy['action_classes']['site_ci_prepare']['exact_requests'] if b.get('action_id')==action_id]
    require(len(bindings)==1 and bindings[0]==expected,'completed_readback_unique_nonexecuting_binding_required')
    require(all(type(request[k]) is bool and request[k] is False for k in ['production_write_allowed',
       'preview_execution_allowed','save_allowed','permit_issuance_allowed','permit_consumption_allowed','can_generate_argv']),
       'completed_readback_no_preview_Save_or_permit_authority')
    require(not any(k in request for k in ['argv','inputs','permit','execute','proposed_argv_not_executed']),
       'completed_readback_no_execution_inputs')
    original=pinned(root,w,request['original_request']);candidate=pinned(root,w,request['original_candidate'])
    guard=pinned(root,w,request['successor_guard']);link=pinned(root,w,request['successor_field_linkage'])
    acceptance=pinned(root,w,request['assistant_acceptance'])
    require(acceptance.get('status')=='pending' and acceptance.get('framework')=='goal_delivery_assistant_v1'
       and acceptance.get('responsible_assistant_id')=='operations-assistant-2' and acceptance.get('review_lane')=='cms'
       and acceptance.get('producer_department')=='designated-development'
       and acceptance.get('independent_acceptance_issued') is False and acceptance.get('requires_HQ_second_review') is False
       and acceptance.get('production_write_allowed') is False and acceptance.get('preview_execution_allowed') is False,
       'completed_readback_unique_independent_assistant_pending_binding_required')
    require(original['preview_request_id']==action_id and original['scope']==scope
       and original['candidate']==request['original_candidate']
       and candidate['desired_fields_sha256']==request['successor']['original_desired_fields_sha256'],
       'completed_readback_original_linkage_required')
    successor=request['successor'];matches=[r for r in guard['rows'] if r['target']==successor['target']]
    require(len(matches)==1,'completed_readback_unique_successor_required');row=matches[0]
    require(row['stage']=='COMPLETED_ROW_GUARD_PASS' and row['permitStatus']=='FRESH_COMPLETED'
       and row['originRunId']==successor['origin_run_id'] and row['actualUpdatedAt']==successor['saved_updated_at']
       and row['desiredSha256']==successor['desired_fields_sha256'] and guard['checkedAt']==successor['observed_at'],
       'completed_readback_completed_guard_identity_required')
    if request['item']=='v20':
        require(request['status']=='superseded_completed' and successor['target']=='design-body-faq-unified-20261009-v1'
           and link['original_faq_subset']==candidate['desired_fields']
           and link['successor_faq_subset']==candidate['desired_fields']
           and link['original_faq_subset_sha256']==candidate['desired_fields_sha256']
           and link['successor_four_fields_sha256']==row['desiredSha256']
           and link['old_retained_digest_not_equated_to_unified_retained_digest'] is True,
           'completed_readback_v20_exact_FAQ_subset_not_old_body_restore_required')
    else:
        require(request['status']=='retired_completed' and successor['target']==original['frozen_candidate_version']
           and row['desiredSha256']==candidate['desired_fields_sha256']
           and row['retainedSha256']==candidate['retained_fields_sha256'],
           'completed_readback_exact_two_field_successor_required')
    return ['completed_successor_readback_non_executable_do_not_replay']

def evaluate(root,w,policy,*,task_id,department,action_id,scope,payload_sha256):
    try:
        if action_id in {r['value']['preview_request_id'] for r in REQUESTS}:
            return completed_successor_readback(root,w,policy,task_id=task_id,department=department,
                action_id=action_id,scope=scope,payload_sha256=payload_sha256)
        require(Path(root).resolve()==ROOT and task_id==TASK and department=='publishing','preview_exact_task_and_actor_required')
        entries=[r for r in REQUESTS if r['value']['preview_request_id']==action_id and r['value']['scope']==scope]
        require(len(entries)==1,'preview_only_three_literal_action_scope_pairs')
        entry=entries[0];request=pinned(root,w,entry['pin']);validate_request(request,entry)
        require(payload_sha256==entry['pin']['sha256'],'preview_exact_request_payload_required')
        exact={'task_id':TASK,'department':'publishing','action_id':action_id,'scope':scope,'profile':PROFILE,
           'request_path':entry['pin']['path'],'request_sha256':entry['pin']['sha256']}
        bindings=[b for b in policy['action_classes']['site_ci_prepare']['exact_requests'] if all(b.get(k)==v for k,v in exact.items())]
        require(len(bindings)==1 and set(bindings[0])==set(exact)|{'control_acceptance','attempt_receipt_path','run_receipt_path'},'preview_unique_exact_policy_profile_required')
        for key,suffix in [('attempt_receipt_path','attempt'),('run_receipt_path','run')]:
            expected_path='logs/preview-dispatch/'+TASK+'/'+action_id+'-'+suffix+'.json'
            require(bindings[0][key]==expected_path and not w.safe_path(root,expected_path).exists(),
               'preview_exact_single_attempt_or_run_already_recorded')
        registry=w.department_registry(root);fixed=registry['publishing']['chat_binding']
        require(all(fixed.get(k)==v for k,v in {'task_id':PUB,'project_id':PROJECT,'cwd':str(ROOT),'status':'bound_and_visible',
           'reply_health':'healthy_visible_reply_verified','dispatch_eligible':True}.items())
           and w._chat_binding_healthy(fixed,verification_ttl_hours=26),'preview_current_fixed_publisher_health_required')
        require(registry['qa']['chat_binding'].get('task_id')==QA,'preview_exact_fixed_independent_QA_required')
        publisher_source(root,w)
        acceptance=pinned(root,w,bindings[0]['control_acceptance']);control_approval(root,w,acceptance)
        current_context(root,w,request)
        return []
    except (ValueError,OSError,KeyError,TypeError,AttributeError,w.WorkflowError) as error:return [str(error)]


def invocation_for_decision(root,w,policy,decision):
    """Return exact reviewed argv; performs no command. Callers cannot supply after/extra inputs."""
    require(decision.get('status')=='allow' and decision.get('action_class')=='site_ci_prepare'
       and decision.get('approval_status')=='not_used' and decision.get('approval_id')=='',
       'preview_no_production_approval_or_permit_in_call')
    reasons=evaluate(root,w,policy,**{k:decision[k] for k in ['task_id','department','action_id','scope','payload_sha256']})
    require(not reasons,'preview_evidence_changed_before_invocation:'+','.join(reasons))
    entry=next(r for r in REQUESTS if r['value']['preview_request_id']==decision['action_id'])
    return validate_argv(entry['value'],entry['value']['proposed_argv_not_executed'])
