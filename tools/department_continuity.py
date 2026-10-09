"""Bounded professional R0 consumer: execute, freeze, enqueue, advance original task.

An admitted fixed chat supplies its professional executor and actual native
reply observer. No interpreter or application JS is invoked. This adapter is
not an automatic wakeup; no authorized ready step ends the current invocation.
"""
import datetime as dt
import fcntl
import json
import os
from pathlib import Path
import re
import tempfile
import human_control
import department_next_work as next_work
import owner_direct_intake
import workflow_control as w


def immutable_json(path, value):
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n'
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise w.WorkflowError('frozen result symlink forbidden')
    if path.exists():
        if path.read_text() != raw:
            raise w.WorkflowError('existing frozen result differs; preserve and recover exact bytes')
        return
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=path.parent,
                                         prefix='.freeze-',delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(raw); handle.flush(); os.fsync(handle.fileno())
        try: os.link(temporary,path)  # Publish complete bytes exclusively; never replace.
        except FileExistsError:
            if path.is_symlink() or path.read_text() != raw:
                raise w.WorkflowError('concurrent frozen result differs; preserve original')
        directory_fd = os.open(path.parent,os.O_RDONLY)
        try: os.fsync(directory_fd)
        finally: os.close(directory_fd)
    finally:
        if temporary is not None: temporary.unlink(missing_ok=True)


def consume(root, packet_path, live, execute_step, observe_reply, *, max_steps=8, now=None):
    """Callbacks are the fixed professional chat boundary, not authority inputs.

    Each executor returns a V2 outbox and project-local artifact paths. The
    observer reads an actual nonempty reply only after execution. Interrupted
    unsealed output requires exact recovery, never re-executes automatically.
    """
    root = Path(root).resolve()
    human_control.guard(root)
    from routine_grants import validate_adoption
    validate_adoption(root)
    if not callable(execute_step) or not callable(observe_reply) or not 1 <= max_steps <= 32:
        raise w.WorkflowError('bounded professional executor and native observer required')
    packet = w.read_json(w.safe_path(root, packet_path))
    task = w.validate_task_id(packet.get('task_id'))
    lock = w.safe_path(root, 'logs/continuity/' + task + '.lock')
    lock.parent.mkdir(parents=True, exist_ok=True)
    completed = []
    with lock.open('a+') as handle:
        try: fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return {'mode':'ACTIVE_CONSUMER_ALREADY_RUNNING','completed':[], 'business_goal_closed':False}
        for _ in range(max_steps):
            human_control.guard(root, task)
            view = next_work.inspect(root, packet_path, live, now)
            step = view['next_step']
            if step is None:
                return {**view, 'completed': completed, 'invocation_ended':True}
            directory = w.safe_path(root, step['output_dir'])
            seal = directory / '.frozen-result.json'
            expected = view['step_bindings'][step['step_id']]
            if directory.exists():
                if seal.is_symlink(): raise w.WorkflowError('frozen seal symlink forbidden')
                if not seal.is_file():
                    return {**view, 'mode':'RECOVER_INTERRUPTED_OUTPUT','completed':completed,
                            'invocation_ended':True,'automatic_reexecution':False}
                frozen = w.read_json(seal)
                if frozen.get('step_binding') != expected:
                    raise w.WorkflowError('recovery must bind exact original step and inputs')
                box_path = frozen['outbox']['path']
                if w.file_digest(root,box_path) != frozen['outbox']:
                    raise w.WorkflowError('frozen interrupted outbox bytes changed')
                stamp = w._parse_observed_at(frozen.get('reply',{}).get('observed_at'))
                clock = now or dt.datetime.now(dt.timezone.utc)
                if stamp is None or not 0 <= (clock-stamp).total_seconds() <= 300:
                    observed = observe_reply(root,step,{'outbox':w.read_json(w.safe_path(root,box_path)),
                                                      'recovery':True})
                    fresh = w._parse_observed_at(observed.get('observed_at'))
                    if (fresh is None or not 0 <= (clock-fresh).total_seconds() <= 300
                            or observed.get('sha256') != frozen['reply'].get('sha256')
                            or observed.get('thread_id') != packet['fixed_chat_task_id']
                            or observed.get('nonempty') is not True
                            or observed.get('trusted_native_readback') is not True):
                        raise w.WorkflowError('fresh readback of exact original completion reply required')
                    frozen = {**frozen,'reply':observed}  # Preserve the original immutable seal.
            else:
                directory.mkdir(parents=True)
                immutable_json(directory/'.execution-start.json', {'step_binding':expected})
                produced = execute_step(root, step, directory)
                # Re-read packet, expiry, input pins and identity after execution.
                current = next_work.inspect(root, packet_path, live, now)
                if current['step_bindings'].get(step['step_id']) != expected:
                    raise w.WorkflowError('authorized inputs changed during execution')
                if not isinstance(produced, dict) or not isinstance(produced.get('outbox'), dict):
                    raise w.WorkflowError('professional executor must return actual V2 outbox')
                paths = produced.get('artifacts')
                if not isinstance(paths,list) or not paths:
                    raise w.WorkflowError('actual nonempty output artifacts required')
                artifacts = []
                for path in paths:
                    actual = w.safe_path(root,path)
                    if directory not in actual.parents or actual.is_symlink() or not actual.is_file():
                        raise w.WorkflowError('artifacts must belong to this exact step directory')
                    pin = w.file_digest(root,path)
                    if pin['size'] == 0: raise w.WorkflowError('empty artifact cannot prove execution')
                    artifacts.append(pin)
                reply = observe_reply(root, step, produced)
                stamp = w._parse_observed_at(reply.get('observed_at')) if isinstance(reply,dict) else None
                clock = now or dt.datetime.now(dt.timezone.utc)
                if (stamp is None or not 0 <= (clock-stamp).total_seconds() <= 300
                        or reply.get('thread_id') != packet['fixed_chat_task_id']
                        or reply.get('nonempty') is not True
                        or reply.get('trusted_native_readback') is not True
                        or not re.fullmatch('[a-f0-9]{64}',str(reply.get('sha256','')))):
                    raise w.WorkflowError('actual fresh fixed-chat nonempty completion reply required')
                box = dict(produced['outbox'])
                for key,value in dict(task_id=task,department=packet['department'],
                    candidate_version=step['candidate_version'],fixed_chat_task_id=packet['fixed_chat_task_id']).items():
                    if box.get(key) != value: raise w.WorkflowError('executor result identity differs from step')
                if box.get('external_permission_issued') is not False or box.get('production_write_allowed') is not False:
                    raise w.WorkflowError('R0 result cannot imply external authority')
                box.update(step_binding=expected, artifacts=artifacts,
                    chat_reply={'nonempty':True,'in_current_fixed_department_chat':True,
                                'ref':reply.get('ref'),'sha256':reply['sha256']})
                origin = owner_direct_intake.existing(root,task)
                if origin: box['owner_authorization_message_id'] = origin['human_message']['message_id']
                box_path = w.rel_path(root,directory/'outbox.json')
                immutable_json(w.safe_path(root,box_path),box)
                w.validate_outbox(root,[w.file_digest(root,box_path)],packet['department'],task)
                frozen = {'step_binding':expected,'outbox':w.file_digest(root,box_path),'reply':reply}
                immutable_json(seal,frozen)
            # Frozen local completion is only queued; never invent HQ intake/QA.
            box = w.read_json(w.safe_path(root,box_path))
            for pin in box.get('artifacts',[]):
                if w.file_digest(root,pin.get('path','')) != pin:
                    raise w.WorkflowError('frozen output artifact bytes changed')
            request = dict(task_id=task,event='notification_queued',sender_department=packet['department'],
                candidate_version=step['candidate_version'],result_sha256=frozen['outbox']['sha256'],
                outbox_path=box_path,idempotency_key='workpack-'+expected['step_sha256'],evidence_paths=[p['path'] for p in w.read_json(w.safe_path(root,box_path)).get('artifacts',[])])
            origin = owner_direct_intake.existing(root,task)
            if origin: request.update(source_mode='owner_direct',authorized_scope=origin['authorized_scope'],
                source_thread_id=frozen['reply']['thread_id'],source_reply_sha256=frozen['reply']['sha256'],
                reply_observed_at=frozen['reply']['observed_at'])
            row,_ = w.record_result_handoff(root,request)
            completed.append({'step_id':step['step_id'],'outbox':frozen['outbox'],'queue_record_id':row['record_id']})
        return {'mode':'BOUNDED_INVOCATION_COMPLETE','task_id':task,'completed':completed,
                'invocation_ended':True,'next_invocation_requires_fresh_identity':True,
                'business_goal_closed':False,'external_permission_issued':False}
