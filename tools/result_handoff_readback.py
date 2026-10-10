"""Read an exact queued result after concurrent controller intake; never mutate it."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from result_handoff_key import describe_outbox


def verify_readback(status: dict, events: list, identity: dict) -> dict:
    keys = ('sender_department', 'candidate_version', 'result_sha256')
    def matches(row):
        return all(row.get(key) == identity[key] for key in keys)
    results = [row for row in status.get('results', []) if matches(row)]
    queued = [row for row in events if matches(row)
              and row.get('task_id') == identity['task_id']
              and row.get('event') == 'notification_queued']
    if len(results) != 1 or len(queued) != 1:
        raise ValueError('Expected one exact result and its unique notification_queued receipt')
    result = results[0]
    received = result.get('controller_received') is True
    decision = result.get('controller_decision', 'pending')
    if decision != 'pending' and not received:
        raise ValueError('Controller decision lacks controller intake')
    phase = 'controller_decided' if decision != 'pending' else 'controller_received' if received else 'queued'
    return {key: identity[key] for key in ('task_id', *keys)} | {
        'queue_verified': True,
        'queue_receipt_id': queued[0].get('record_id'),
        'current_phase': phase,
        'controller_decision': decision,
        'controller_followthrough': result.get('controller_followthrough', 'pending'),
        'business_goal_closed': False,
        'mutation_count': 0,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--outbox', type=Path, required=True)
    parser.add_argument('--root', type=Path, help='准确项目根；默认当前工具所属项目')
    args = parser.parse_args()
    import workflow_control as workflow
    root = (args.root or Path(__file__).resolve().parents[1]).resolve()
    try:
        path = workflow.safe_path(root, str(args.outbox))
        relative = path.relative_to(root).as_posix()
        identity = describe_outbox(path, 'notification_queued')
        workflow.validate_outbox(root, [workflow.file_digest(root, relative)], identity['sender_department'], identity['task_id'])
    except (workflow.WorkflowError, ValueError, OSError) as error:
        parser.error(str(error))
    identity = describe_outbox(path, 'notification_queued')
    value = verify_readback(workflow.result_handoff_status(root, identity['task_id']),
                            workflow._result_handoff_rows(root, identity['task_id']), identity)
    print(json.dumps(value, ensure_ascii=False))


if __name__ == '__main__':
    main()
