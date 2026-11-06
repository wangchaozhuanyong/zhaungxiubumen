"""Reconcile the exact completed EN2 direct handoff with its legacy root reservation."""

import datetime as dt
import json
from pathlib import Path
from types import SimpleNamespace

import direct_handoff_readback as direct
import receipt_obligation_consumer as serial
import workflow_control as w

TASK = 'fc-20261011-english-kitchen-actual-publication-goal-v1'
PUBLISHER = '<LOCAL_TASK_ID>'
TURN = 'example-native-e6b04f80d7cf1fc9'
INTENT = 'b05be716-c013-4b89-9fe2-f6a2c7d6dc8f'
ACTION = 'HQ-original-PUB-EN2-forward-save-after-fresh-preview-42170362152-20261106-v1'
RESERVATION = ('EN2 original PUB resumes after fresh actual health and normal prepare/policy. '
               'First original key/same row/full41/CAS/backup, zero-write preview and forward preflight; '
               'only original once-only publish path and public readback. Existing protected work preserved.')
RESULT = {'path': f'drafts/publishing/{TASK}/forward-save-42170362152-20261106-v1/PUB-ACTUAL-EN2-SAVED-AND-PUBLIC-RESULT.json',
          'sha256': '7866d873d50b5d7752b4c63c7d515490099d344addcac5422caf7912c4596e19', 'size': 2667}


def close(root, history):
    """Clear only the historical reservation that the actual EN2 Save fulfilled."""
    with w.workflow_lock(root):
        record, before = serial._root_serial_read(root)
        if record.get('assigned_next_original_window') is None and record.get('en2_completed_direct_reservation'):
            return {'state': 'already_reconciled', 'proof': record['en2_completed_direct_reservation']}
        serial.require(record.get('assigned_next_original_window') == PUBLISHER
                       and record.get('assigned_next_action') == RESERVATION
                       and not record.get('current_assigned_next_consumed'), 'exact historical EN2 reservation required')
        gate = serial.shared_serial_guard(root, target_thread_id=PUBLISHER, transport=SimpleNamespace(history=history))
        serial.require(gate.get('new_activation_allowed') is True and gate.get('source') == before,
                       'fresh original root release and no outstanding queue slot required')
        effect = direct.observe(root, PUBLISHER, history) or {}
        serial.require(all(effect.get(k) == v for k, v in {
            'state': 'direct_final_observed', 'turn_id': TURN, 'intent_event_id': INTENT,
            'task_id': TASK, 'action_id': ACTION, 'business_goal_closed': False,
        }.items()), 'exact completed original EN2 direct handoff required')
        thread = history.call('thread/read', {'threadId': PUBLISHER, 'includeTurns': False})['thread']
        turns = history.call('thread/turns/list', {'threadId': PUBLISHER, 'limit': 1,
                            'sortDirection': 'desc', 'itemsView': 'full'})['data']
        _, _, final = serial._root_serial_native({'thread': thread, 'turns': turns}, PUBLISHER, TURN,
                                                 dt.datetime.now(dt.timezone.utc))
        serial.require(final['id'] == effect['final_message_id'], 'exact latest publisher final required')
        result = serial.doc(root, RESULT)
        serial.require(all(result.get(k) == v for k, v in {
            'task_id': TASK, 'completed_scope': 'original_EN2_two_fields_saved_and_publicly_verified',
            'publish_run_id': 42170829866, 'publish_run_status': 'completed_success', 'permit_status': 'completed',
            'target_matches_desired': True, 'protected37_preserved': True, 'MS11_preserved': True,
            'public_rendered_title_and_excerpt': 'PASS_actual_browser_AX', 'business_parent_closed': False,
        }.items()), 'original permit, Save, protected fields and public proof required')
        serial.require(serial._root_serial_read(root)[1] == before and serial._root_slot_read(root) is None,
                       'root or queue slot changed before reconciliation')
        proof = {'prior_root': before, 'assigned_next_original_window': PUBLISHER, 'assigned_next_action': RESERVATION,
                 'direct_effect': effect, 'original_publisher_result': RESULT, 'observed_at_UTC': w.utc_timestamp(),
                 'business_goal_closed': False, 'external_permission_issued': False}
        record.update(assigned_next_original_window=None, assigned_next_action=None,
                      en2_completed_direct_reservation=proof)
        w.atomic_write_json(w.safe_path(root, serial.ROOT_SERIAL_PATH), record)
        return {'state': 'completed_en2_reservation_reconciled', 'proof': proof}


if __name__ == '__main__':
    from department_event_dispatcher import RPC, native_queue_capability

    root = Path(__file__).resolve().parents[1]
    history = RPC([native_queue_capability(root), 'app-server', '--listen', 'stdio://'])
    try:
        print(json.dumps(close(root, history), ensure_ascii=False))
    finally:
        history.close()
