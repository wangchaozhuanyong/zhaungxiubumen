"""Stage an authorized public source only after exact adoption and real R0 pilot.

No network, git mutation, push or history rewrite is performed by this tool.
The fixed developer continues the original authorized task after these gates.
"""
from pathlib import Path
import export_department_system as exporter
import routine_grants
import workflow_control as w

AUTHORIZED_REPOSITORY = 'wangchaozhuanyong/zhaungxiubumen'


def pinned(root, pin):
    if not isinstance(pin,dict) or w.file_digest(root,pin.get('path','')) != pin:
        raise w.WorkflowError('exact unchanged evidence pin required')
    return w.read_json(w.safe_path(root,pin['path']))


def source_allowlist(root):
    """Exactly the source files prepare() consumes; no partial readback allowed."""
    root=Path(root)
    paths={'AGENTS.md','README.md','.codex/config.toml','data/department-registry.json',
           'data/action-policy.json',*('data/'+name for name in exporter.POLICIES)}
    for name in ('.env.example','.codex/hooks.json','ci/department-system-checks.yml.example'):
        if (root/name).is_file():paths.add(name)
    for base,suffixes in (('tools',{'.py','.md'}),('playbooks',{'.md'}),('prompts',{'.md'})):
        for p in (root/base).glob('*'):
            if p.is_file() and p.suffix.casefold() in suffixes:
                if p.stem.startswith('test_') and exporter.private_module(p.stem[5:]):continue
                paths.add(p.relative_to(root).as_posix())
    for role in w.department_registry(root).values():
        paths.add(role['role_config'])
        base=root/'departments'/role['id']
        for p in base.rglob('*'):
            rel=p.relative_to(base)
            if (p.is_file() and p.suffix.casefold() in {'.md','.py','.yaml'}
                    and not exporter.EXCLUDED_PARTS.intersection(rel.parts)
                    and (str(rel) in {'README.md','SKILL.md'} or rel.parts[0] in {'agents','references','scripts','tests'})):
                paths.add(p.relative_to(root).as_posix())
    for name in ('flashcast-department-learning','flashcast-cms-publishing'):
        for p in (root/'skills'/name).rglob('*'):
            if p.is_file() and p.suffix.casefold() in {'.md','.py','.yaml'}:paths.add(p.relative_to(root).as_posix())
    for name in ('packet.json','step-a-result.json','claim-input.json','qa2-review-plan.json'):
        if (root/'examples'/name).is_file():paths.add('examples/'+name)
    return paths


def check_adopted_source(root, applied_pin, pilot_pin, source_qa_pin=None):
    adoption = routine_grants.validate_adoption(root)
    applied = pinned(root,applied_pin)
    files = applied.get('files')
    if (applied.get('status') != 'APPLIED_AND_READ_BACK'
            or applied.get('candidate_sha256') != adoption.get('candidate_sha256')
            or applied.get('controller_decision_record_id') != adoption.get('controller_decision_record_id')
            or not isinstance(files,list) or not files):
        raise w.WorkflowError('current exactly adopted source readback required')
    accepted = pinned(root,w.file_digest(root,adoption['candidate_path']))
    expected = {p['path']:p for p in accepted.get('export_source_files',[]) if isinstance(p,dict)}
    allowlist = source_allowlist(root)
    if not expected or set(expected) != allowlist:
        raise w.WorkflowError('adopted candidate must contain complete current export source manifest')
    paths = set()
    for pin in files:
        if (not isinstance(pin,dict) or pin.get('path') not in expected
                or pin.get('path') in paths or w.file_digest(root,pin.get('path','')) != pin):
            raise w.WorkflowError('applied source drift or duplicate path')
        paths.add(pin['path'])
        # Live bindings and policy state are separately QA-reviewed below.
        # Every code/method file must still be the actual adopted version.
        if not pin['path'].startswith('data/') and pin != expected[pin['path']]:
            raise w.WorkflowError('code or method source differs from adopted candidate')
    if paths != allowlist:
        raise w.WorkflowError('applied source manifest omitted or added export inputs')
    decisions=w._result_handoff_rows(root,adoption['task_id']) if adoption.get('task_id') else w._result_handoff_rows(
        root,w.read_json(w.safe_path(root,adoption['qa_outbox']['path']))['task_id'])
    adopted_at=w._parse_observed_at(next(r['created_at'] for r in decisions
        if r.get('record_id')==adoption['controller_decision_record_id']))
    qa_box=pinned(root,source_qa_pin)
    qa_rows,qa_invalid=w._validate_receipt_chain(root,qa_box.get('task_id'))
    qa_matches=[r for r in qa_rows if r.get('receipt_type')=='qa_verdict' and r.get('verdict')=='pass'
        and r.get('department')==qa_box.get('department') and source_qa_pin in r.get('evidence',[])]
    qa_at=w._parse_observed_at(qa_matches[-1].get('created_at')) if qa_matches else None
    if (qa_invalid or not qa_matches or qa_box.get('department') not in {'qa','qa-technical'}
            or qa_box.get('risk_level')!='R0' or qa_box.get('production_release_eligible') is not False
            or qa_box.get('approved_export_source')!=applied_pin
            or qa_box.get('system_candidate_sha256')!=adoption['candidate_sha256']
            or qa_box.get('system_candidate_version')!=accepted.get('candidate_version')
            or applied_pin not in qa_box.get('evidence',[])
            or qa_at is None or adopted_at is None or qa_at <= adopted_at):
        raise w.WorkflowError('post-adoption independent QA must bind the complete current export source')
    w.validate_outbox(root,[source_qa_pin],qa_box['department'],qa_box['task_id'])
    pilot = pinned(root,pilot_pin)
    task = w.validate_task_id(pilot.get('task_id'))
    outbox_pin = pilot.get('outbox')
    box = pinned(root,outbox_pin)
    rows,invalid = w._validate_receipt_chain(root,task)
    results = [r for r in rows if r.get('receipt_id') == pilot.get('outbox_receipt_id')
               and r.get('receipt_type') == 'outbox_received'
               and r.get('department') == box.get('department') and outbox_pin in r.get('evidence',[])]
    queued = [r for r in w._result_handoff_rows(root,task) if r.get('event') == 'notification_queued'
              and r.get('outbox') == outbox_pin]
    bind = w.department_registry(root).get(box.get('department'),{}).get('chat_binding',{})
    executed_at=w._parse_observed_at(box.get('executed_at'))
    result_at=w._parse_observed_at(results[0].get('created_at')) if len(results)==1 else None
    queued_at=w._parse_observed_at(queued[0].get('created_at')) if len(queued)==1 else None
    original=accepted.get('task_id')
    if (invalid or len(results) != 1 or len(queued) != 1
            or pilot.get('status') != 'REAL_R0_PILOT_COMPLETED'
            or pilot.get('candidate_sha256') != adoption.get('candidate_sha256')
            or pilot.get('simulation') is not False
            or box.get('risk_level') != 'R0' or box.get('status') != 'completed'
            or box.get('production_write_allowed') is not False
            or box.get('external_permission_issued') is not False
            or not original or not (task == original or task.startswith(original+'-'))
            or box.get('system_candidate_sha256') != adoption['candidate_sha256']
            or box.get('system_candidate_version') != accepted.get('candidate_version')
            or box.get('applied_source') != applied_pin
            or applied_pin not in box.get('step_binding',{}).get('step_identity',{}).get('inputs',[])
            or executed_at is None or adopted_at is None or not adopted_at < executed_at
            or result_at is None or queued_at is None or result_at < executed_at or queued_at < executed_at
            or box.get('fixed_chat_task_id') != bind.get('task_id')
            or box.get('chat_reply',{}).get('nonempty') is not True):
        raise w.WorkflowError('exact real registered R0 pilot result and native chain required')
    return {'adoption':adoption,'applied_source':applied_pin,'pilot':pilot_pin,'source_qa':source_qa_pin}


def prepare_adopted(root, target, applied_pin, pilot_pin, source_qa_pin=None):
    root,target=Path(root).resolve(),Path(target).resolve()
    proof=check_adopted_source(root,applied_pin,pilot_pin,source_qa_pin)
    if target != root/'releases/zhaungxiubumen':
        raise w.WorkflowError('original authorized project release path required')
    result=exporter.prepare(root,target)
    return {**result,'authorized_repository':AUTHORIZED_REPOSITORY,'evidence':proof,
            'stage_only':True,'push_executed':False,'force_push_allowed':False,
            'remote_history_must_be_preserved':True}
