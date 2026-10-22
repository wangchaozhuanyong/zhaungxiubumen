"""Read the original rotation's real SYS adoption and existing-business pilot.

No source installation, acceptance, parent rewrite, dispatch or permission effect.
The caller still resolves the latest exact accepted result and requires the
assigned assistant's real native completion for the supplied journal.
"""
import json
import hashlib
import datetime as dt
from pathlib import Path
import workflow_control as w

TASK = 'fc-20261020-clean-department-window-rotation-runtime-v1'
SCOPE = 'project:flashcast:clean-department-window-rotation:20261020:v1'
BASE = 'logs/handoffs/2026-10-20-clean-department-window-rotation-v1/'
REVIEW = BASE + 'operations-assistant-2/runtime-independent-review-v1/two-P1-recheck-20261020-v1/v7-current-dispatch-final-review/'
CONTRACT = {'path': BASE + 'operations/runtime-goal-source-binding-input-v1.json',
            'sha256': '395e41a6e0b6017470c7519588954e6cb8b921a311f83efe85b00eccb9646b28', 'size': 4099}
AUTHORITY = {'path': BASE + 'operations/runtime-original-authority-source.json',
             'sha256': 'cd20867a7ade92103464a7ced1a4908ef799cecb4061f81020e32ab1c536b9c8', 'size': 4691}
REPORT = {'path': REVIEW + 'A2-V7-INDEPENDENT-WHOLE-GOAL-REPORT-v1.json',
          'sha256': 'a6276fd5edf1b3a4bada3c7590cf57323f793737b840c7bd462f256f82d84d9f', 'size': 9412}
PILOT = {'path': REVIEW + 'A2-V7-ACTUAL-EXISTING-ORIGINAL-CONTINUATION-JOURNAL-v1.json',
         'sha256': '8ff7e596f68d469c4555a324589b01d8e43355d5089283cae8cc987aea08b030', 'size': 2408}
QA_ID = '4fc868ee-1ed5-45ff-95c4-9d45b706bf09'
QA_HASH = 'd14c7a440b008a8e9d676215b9f6b9965ba81c4619e193ade346ff1f3c602ff0'
# The first post-PASS review-consumer repair adds this existing source file.
# Its actual pre-repair fingerprint is not renamed as an earlier SYS adoption.
REVIEW_SOURCE_BASE = '36b4fcef2dd06dc246ce912c1a814323b36bdfed2e3309f76177c15713e4e113'
# Exact existing predecessors of the separately queued historical HQ reader delta.
# These files were not part of the old V7 adoption; a real CAS backup is required.
HISTORICAL_READ_SOURCE_BASES = {
    'tools/direct_system_repair.py': '07cbb5e8d6ef9cb0747107c9b4a938ac1f0b8130a15e9cae9006408adc44105f',
    'tools/test_direct_system_close.py': 'ad90853da843aa765caf36f8b00e402ad3427edac32fb4b6a8172a8f917b3a91',
}


def document(root, pin):
    if not isinstance(pin, dict) or w.file_digest(root, pin.get('path', '')) != pin:
        raise w.WorkflowError('exact original rotation completion evidence pin changed')
    return json.loads(w.safe_path(root, pin['path']).read_text(encoding='utf-8'))


def _received_native_source(root, queue, receipts, producer_index, fixed):
    """Read a committed READY's original receipt prefix, not later dispatches.

    This is only called after exact original intake commitment is verified.
    It cannot create a new queue or relax that entry's admission checks.
    """
    if queue.get('result_source_phase') != 'delivery_ready':
        return w._validate_goal_completed_result(root, queue, fixed,
            through_receipt_id=receipts[producer_index]['receipt_id'])
    from goal_delivery_runtime import _collaboration_native
    page = _collaboration_native(root, queue.get('actual_native_completion'))
    binding = w.department_registry(root)[queue['sender_department']]['chat_binding']
    selected = [(turn, message) for turn in page.get('turns', [])
                if turn.get('id') == queue.get('source_turn_id') for message in turn.get('items', [])
                if message.get('type') == 'agentMessage' and message.get('id') == queue.get('source_message_id')]
    reply = queue.get('visible_reply')
    if (len(selected) != 1 or any(page.get('thread', {}).get(key) != binding.get(field)
            for key, field in (('id', 'task_id'), ('title', 'title'), ('cwd', 'cwd')))
            or not isinstance(reply, dict) or w.file_digest(root, reply.get('path', '')) != reply):
        raise w.WorkflowError('exact committed READY native identity and immutable reply required')
    turn, message = selected[0]
    raw = w.safe_path(root, reply['path']).read_bytes()
    observed = w._parse_observed_at(queue.get('reply_observed_at'))
    prior = [row for row in receipts[:producer_index + 1] if row.get('department') == queue['sender_department']
             and row.get('chat_task_id') == fixed and row.get('receipt_type') in {'dispatch_sent', 'chat_ack'}]
    declarations = [line[len('FLASHCAST_DELIVERY_READY '):] for line in message.get('text', '').splitlines()
                    if line.startswith('FLASHCAST_DELIVERY_READY ')]
    if (turn.get('status') not in {'inProgress', 'completed'} or turn.get('error')
            or raw != message.get('text', '').encode('utf-8')
            or hashlib.sha256(raw).hexdigest() != queue.get('source_reply_sha256')
            or observed is None or observed > dt.datetime.now(dt.timezone.utc)
            or type(turn.get('startedAt')) not in {int, float} or turn['startedAt'] > observed.timestamp()
            or not prior or any(w._parse_observed_at(row['created_at']) > observed for row in prior)
            or len(declarations) != 1):
        raise w.WorkflowError('original committed READY bytes and preceding actual source receipt prefix required')
    declaration = json.loads(declarations[0])
    if (any(declaration.get(key) != queue.get(key) for key in
            ('task_id', 'sender_department', 'candidate_version', 'result_sha256'))
            or declaration.get('outbox_path') != queue['outbox']['path']
            or declaration.get('batch_complete') is not True
            or queue.get('batch_delivery_frozen') is not True):
        raise w.WorkflowError('exact original frozen complete READY declaration required')
    return queue


def remaining_review_stage(root, snapshot, receipts, old_binding, plan):
    """Admit only a real received completion-stage successor after original PASS."""
    import qa_review_plan as q
    import result_coordination as coordination
    from scoped_candidate_adoption import _committed
    goal = snapshot.get('goal_delivery', {})
    original = document(root, CONTRACT)
    document(root, AUTHORITY)
    original_goal = original.get('goal_delivery', original)
    stage = plan.get('original_rotation_remaining_stage')
    fields = {'schema_version', 'prior_plan', 'prior_pass_receipt_id', 'producer_outbox_receipt_id',
              'queue_record_id', 'intake_record_id', 'remaining_requirement_ids'}
    if (snapshot.get('task_id') != TASK or snapshot.get('goal_contract') != CONTRACT
            or goal.get('authorization_pin') != AUTHORITY or snapshot.get('current_state') != 'qa_passed'
            or any(goal.get(key) != original_goal.get(key) for key in q.GOAL_IDENTITY)
            or goal.get('primary_owner') != 'system-development'
            or goal.get('producer_departments') != ['system-development']
            or goal.get('responsible_assistant') != 'operations-assistant-2'
            or goal.get('authorized_scope') != [SCOPE] or goal.get('required_execution_actions')
            or goal.get('completion_requirements') != original_goal.get('completion_requirements')
            or not isinstance(stage, dict) or set(stage) != fields or stage.get('schema_version') != 1
            or stage.get('remaining_requirement_ids') != ['rotation-original-1', 'rotation-original-2']
            or old_binding not in q._bindings(root, snapshot) or stage.get('prior_plan') != old_binding.get('pin')
            or any(key in plan for key in ('rework_of', 'adopted_source_continuation', 'post_pass_remaining_stage',
                'owner_direct_review', 'native_multi_goal_review', 'parent_initial_child_review',
                'business_rework_successor', 'original_parent_review_source'))):
        raise w.WorkflowError('unchanged original rotation goal and exact remaining-stage selector required')
    old = q.load_plan(root, snapshot, old_binding)
    same = ('task_id', 'action_class', 'scope', 'producer_department', 'reviewer_department',
            'reviewer_thread_id', 'controller_department', 'controller_thread_id', 'risk_level',
            'single_final_reviewer', 'production_write_allowed', 'external_permission_issued')
    if (any(plan.get(key) != old.get(key) for key in same)
            or plan.get('scope') != SCOPE or plan.get('action_class') != 'internal_control_candidate'
            or plan.get('risk_level') != 'R0' or plan.get('candidate_version') == old.get('candidate_version')
            or plan.get('action_id') == old.get('action_id') or plan.get('candidate') == old.get('candidate')):
        raise w.WorkflowError('remaining completion review must retain exact role/scope and distinct current result')
    verdicts = [(i, row) for i, row in enumerate(receipts) if row.get('receipt_type') == 'qa_verdict']
    if not verdicts:
        raise w.WorkflowError('actual original independent PASS required')
    prior_index, prior = verdicts[-1]
    if (prior.get('receipt_id') != QA_ID or prior.get('receipt_hash') != QA_HASH
            or prior.get('verdict') != 'pass' or stage['prior_pass_receipt_id'] != prior['receipt_id']
            or prior.get('department') != goal['responsible_assistant']
            or any(prior.get(key) != old.get(key) for key in ('task_id', 'action_id', 'action_class', 'scope'))
            or not any(REPORT in document(root, pin).get('evidence', []) for pin in prior.get('evidence', []))):
        raise w.WorkflowError('preserve the actual latest original PASS and its old plan')
    document(root, REPORT)
    producers = [(i, row) for i, row in enumerate(receipts) if row.get('receipt_type') == 'outbox_received'
                 and row.get('department') == plan['producer_department']]
    if (not producers or producers[-1][0] <= prior_index
            or producers[-1][1].get('receipt_id') != stage['producer_outbox_receipt_id']):
        raise w.WorkflowError('latest actual producer result after original PASS required')
    producer = producers[-1][1]
    pin = plan['candidate']
    box = document(root, pin)
    if (pin not in producer.get('evidence', []) or not q._producer_candidate_bound(root, plan, pin, box)
            or box.get('scope') != SCOPE
            or any(box.get(key) is not False for key in ('production_write_allowed', 'external_permission_issued'))):
        raise w.WorkflowError('exact latest received producer outbox and unchanged permission boundary required')
    identity = {'task_id': TASK, 'sender_department': plan['producer_department'],
                'candidate_version': plan['candidate_version'], 'result_sha256': pin['sha256']}
    coordination._validate_queued(root, identity)
    rows = w._result_handoff_rows(root, TASK)
    exact = [row for row in rows if w._result_identity(row) == tuple(identity[key] for key in
             ('sender_department', 'candidate_version', 'result_sha256'))]
    queues = [row for row in exact if row.get('event') == 'notification_queued']
    intakes = [row for row in exact if row.get('event') == 'controller_received']
    if (len(queues) != 1 or len(intakes) != 1 or queues[0].get('record_id') != stage['queue_record_id']
            or intakes[0].get('record_id') != stage['intake_record_id']
            or any(row.get('outbox') != pin for row in (queues[0], intakes[0]))
            or intakes[0].get('coordinator_role') != goal['responsible_assistant']
            or intakes[0].get('coordinator_owner') not in {
                plan['reviewer_thread_id'], goal['responsible_assistant'] + ':' + plan['reviewer_thread_id']}):
        raise w.WorkflowError('one exact current native queue and original A2 committed intake required')
    fixed = w.department_registry(root)[plan['producer_department']]['chat_binding']['task_id']
    _committed(root, intakes[0])
    source = _received_native_source(root, queues[0], receipts, producers[-1][0], fixed)
    if any(intakes[0].get(key) != source.get(key) for key in ('source_thread_id', 'source_turn_id', 'source_reply_sha256')):
        raise w.WorkflowError('remaining stage must retain the actual original producer native source')
    assigned = q._assigned_review_round(root, snapshot, receipts, plan)
    if assigned is None or assigned.get('ack_index', len(receipts)) >= prior_index:
        raise w.WorkflowError('retain the actual original unique assistant responsibility, without new dispatch')
    return {**stage, 'identity': identity, 'prior_PASS_preserved': True,
            'actual_intake_record_hash': intakes[0]['record_hash'],
            'new_dispatch_created': False, 'source_reapplied': False, 'production_permission_issued': False}


def context(root, snapshot, receipts, requirement, accepted, journal):
    goal = snapshot.get('goal_delivery', {})
    kind = requirement.get('requirement_type')
    index = {'internal_pilot': 0, 'source_adoption': 1}.get(kind)
    original = document(root, CONTRACT)
    document(root, AUTHORITY)
    if (snapshot.get('task_id') != TASK or snapshot.get('goal_contract') != CONTRACT
            or goal.get('authorization_pin') != AUTHORITY
            or goal.get('primary_owner') != 'system-development'
            or goal.get('producer_departments') != ['system-development']
            or goal.get('responsible_assistant') != 'operations-assistant-2'
            or goal.get('required_execution_actions') or goal.get('authorized_scope') != [SCOPE]
            or index is None or requirement.get('criterion_index') != index
            or requirement.get('requirement_id') != 'rotation-original-' + str(index + 1)
            or requirement not in original.get('goal_delivery', original).get('completion_requirements', [])
            or accepted.get('state') != 'PROVEN' or accepted.get('scope') != SCOPE
            or accepted.get('identity', {}).get('task_id') != TASK
            or accepted['identity'].get('sender_department') != 'system-development'
            or journal.get('runtime_task_id') != TASK
            or journal.get('external_writes') != 0 or type(journal.get('external_writes')) is not int
            or journal.get('permissions_issued') is not False):
        raise w.WorkflowError('only unchanged original rotation completion requirements allowed')
    report = document(root, REPORT)
    qa = [row for row in receipts if row.get('receipt_id') == QA_ID]
    if (len(qa) != 1 or qa[0].get('receipt_hash') != QA_HASH
            or qa[0].get('receipt_type') != 'qa_verdict' or qa[0].get('verdict') != 'pass'
            or qa[0].get('department') != goal['responsible_assistant']
            or report.get('task_id') != TASK or report.get('scope') != SCOPE
            or [item.get('status') for item in report.get('criteria', [])] != ['PASS'] * 4
            or not any(REPORT in document(root, pin).get('evidence', []) for pin in qa[0].get('evidence', []))):
        raise w.WorkflowError('original independent four-criterion PASS receipt and report required')
    return report


def source_effect(root, accepted, journal, report):
    if journal.get('schema') != 'flashcast-rotation-SYS-adoption-chain/v1' or journal.get('actor') != 'system-development':
        raise w.WorkflowError('actual authorized SYS adoption lineage required')
    # These immutable journals were already independently accepted in the V7 report.
    endpoints = {}
    evidence = [REPORT]
    for pin in report['evidence']:
        if not pin['path'].endswith(('source-adoption-receipt.json', '/adoption-receipt.json')):
            continue
        adopted = document(root, pin)
        for row in adopted.get('files', []):
            if row.get('status') != 'adopted' or row.get('after_sha256') != row.get('actual_after_sha256'):
                raise w.WorkflowError('original accepted source adoption effect differs')
            endpoints[row['path']] = row['after_sha256']
        for row in adopted.get('adopted', []):
            if w.file_digest(root, row['candidate']['path']) != row['candidate']:
                raise w.WorkflowError('original accepted candidate source changed')
            endpoints[row['after']['path']] = row['after']['sha256']
        evidence.append(pin)
    if not endpoints:
        raise w.WorkflowError('original accepted installed source baseline missing')
    successors = journal.get('successors')
    if not isinstance(successors, list):
        raise w.WorkflowError('explicit actual source successor list required')
    allowed_new = {'tools/rotation_completion.py', 'tools/test_rotation_completion.py', 'tools/test_rotation_post_pass.py'}
    for layer in successors:
        plan = document(root, layer['plan'])
        adoption = document(root, layer['journal'])
        operations = adoption.get('adopted')
        backups = {pin['sha256']: pin for pin in layer.get('backups', [])}
        if (adoption.get('task_id') != TASK or adoption.get('production_permission_issued') is not False
                or not isinstance(plan, list) or not plan or not isinstance(operations, list)
                or len(plan) != len(operations)):
            raise w.WorkflowError('actual same-task source CAS successor required')
        seen = set()
        for change, operation in zip(plan, operations):
            path, before, candidate = change['path'], change['expected'], change['candidate']
            document_source = w.file_digest(root, candidate['path'])
            prior = endpoints.get(path)
            if prior is None and path == 'tools/qa_review_plan.py':
                prior = REVIEW_SOURCE_BASE
            if prior is None:
                prior = HISTORICAL_READ_SOURCE_BASES.get(path)
            if (path in seen or (prior is None and path not in allowed_new)
                    or (prior is None and before != 'ABSENT')
                    or (prior is not None and (not isinstance(before, dict) or before.get('path') != path or before.get('sha256') != prior))
                    or operation.get('before') != before or operation.get('candidate') != candidate
                    or document_source != candidate
                    or operation.get('after') != {'path': path, 'sha256': candidate['sha256'], 'size': candidate['size']}):
                raise w.WorkflowError('source successor must retain exact ordered CAS before/candidate/after')
            if prior is not None:
                backup = backups.get(prior)
                if (not backup or w.file_digest(root, backup['path']) != backup
                        or backup['size'] != before['size']):
                    raise w.WorkflowError('actual recoverable source predecessor backup required')
            endpoints[path] = candidate['sha256']; seen.add(path)
        evidence.extend([layer['plan'], layer['journal'], *layer.get('backups', [])])
    box = document(root, accepted['producer_outbox'])
    if successors and box.get('source_adoption') != successors[-1]['journal']:
        raise w.WorkflowError('accepted producer must identify the actual final source adoption')
    if not successors and box.get('source_adoption') not in evidence:
        raise w.WorkflowError('accepted producer actual source adoption missing')
    for path, sha in endpoints.items():
        if w.file_digest(root, path)['sha256'] != sha:
            raise w.WorkflowError('installed source differs from exact adopted lineage: ' + path)
    return evidence


def pilot_effect(root, journal, report):
    import goal_continuity as continuity
    if (journal.get('schema') != 'flashcast-rotation-original-business-pilot/v1'
            or journal.get('original_pilot') != PILOT):
        raise w.WorkflowError('exact original existing-business pilot required')
    pilot = document(root, PILOT)
    task = pilot['pilot_task_id']
    rows, invalid = w._validate_receipt_chain(root, task)
    if invalid or w.validate_workflow_events(root, task):
        raise w.WorkflowError('original business pilot receipt/event chain invalid')
    pub = pilot['actual_original_PUB_continuation']
    assignment_pin = pub['actual_assignment']; assignment = document(root, assignment_pin)
    _, dispatch = continuity._dispatch_source(root, assignment)
    acks = [row for row in rows if row.get('receipt_id') == pub['ACK_receipt_id']]
    if (dispatch.get('receipt_id') != pub['dispatch_receipt_id']
            or dispatch.get('action_id') != report['actual_PUB_continuation']['action_id']
            or assignment.get('actual_native_invocation') != pub['actual_native_source']
            or assignment.get('source_call_id') != pub['native_send_call_id']
            or len(acks) != 1 or acks[0].get('receipt_type') != 'chat_ack'
            or acks[0].get('ack_nonempty') is not True
            or any(acks[0].get(key) != dispatch.get(key) for key in
                   ('task_id', 'department', 'chat_task_id', 'action_id', 'scope', 'policy_decision_id'))
            or pub['actual_ACK'] not in acks[0].get('evidence', [])):
        raise w.WorkflowError('actual original PUB dispatch, ACK and assignment must agree')
    document(root, pub['actual_ACK'])
    current = w.read_json(Path(root) / 'data/department-current-assignment.json')
    registered = list(current.get('assignments', {}).values())
    registered += [pin for pins in current.get('suspended_assignments', {}).values() for pin in pins]
    if assignment_pin not in registered:
        raise w.WorkflowError('original real pilot assignment registration missing')
    seo = pilot['existing_completed_SEO2_V4_delivery']
    handoffs = w._result_handoff_rows(root, task)
    matches = [row for row in handoffs if row.get('record_id') == seo['received_record_id']
               and row.get('event') == 'controller_received' and row.get('result_sha256') == seo['result_sha256']
               and row.get('source_turn_id') == seo['native_turn_id']]
    if len(matches) != 1:
        raise w.WorkflowError('actual original SEO2 native result intake missing')
    from scoped_candidate_adoption import _committed
    _committed(root, matches[0])
    return [PILOT, assignment_pin, pub['actual_native_source'], pub['actual_ACK']]


def effect(root, snapshot, receipts, requirement, accepted, journal):
    report = context(root, snapshot, receipts, requirement, accepted, journal)
    if requirement['requirement_type'] == 'source_adoption':
        return source_effect(root, accepted, journal, report)
    return pilot_effect(root, journal, report)
