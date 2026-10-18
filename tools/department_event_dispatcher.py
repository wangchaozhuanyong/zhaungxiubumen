#!/usr/bin/env python3
"""Event-driven, project-scoped result wakeups; never decides or publishes.

The supported desktop queue command delivers without steering active work. The
optional direct transport must share the desktop's actual app-server runtime.
A separate app server is allowed only for read-only identity/history queries.
Transport receipts below are not result-handoff, acceptance or business receipts.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
import signal
import queue
import re
import select
import socket
import sqlite3
import subprocess
import sys
import threading

ROOT = Path(__file__).resolve().parents[1]
CONFIG = Path('data/department-event-dispatcher.json')
STATE = Path('logs/department-event-dispatcher')
IDENTITY = ('task_id', 'sender_department', 'candidate_version', 'result_sha256')


class DispatchError(ValueError):
    pass


def inside(root, rel):
    path = Path(rel)
    if path.is_absolute() or '..' in path.parts:
        raise DispatchError('project-relative path required')
    result = root / path
    if result.is_symlink() or not result.resolve().is_relative_to(root.resolve()):
        raise DispatchError('project-owned non-symlink path required')
    return result


def identity(value):
    if not isinstance(value, dict) or any(not isinstance(value.get(k), str) or not value[k] for k in IDENTITY):
        raise DispatchError('exact original result identity required')
    return {k: value[k] for k in IDENTITY}


def key(value):
    return hashlib.sha256(json.dumps(identity(value), sort_keys=True).encode()).hexdigest()


def binding(root, role):
    registry = json.loads((root / 'data/department-registry.json').read_text())
    matches = [v for v in registry['departments'] if v['id'] == role and v.get('new_dispatch_enabled')]
    if len(matches) != 1:
        raise DispatchError('one current enabled role required')
    value = matches[0]['chat_binding']
    if Path(value['cwd']).resolve() != root.resolve():
        raise DispatchError('cross-project wakeup refused')
    return value


def validate_notification(root, record):
    """Use the existing authenticated queue/route, not arbitrary file instructions."""
    import result_coordination as rc
    value = identity(record.get('identity'))
    rc._validate_queued(root, value)
    route = rc.result_lane(root, value)
    if route.get('lane') not in {'professional_acceptance', 'HQ_knowledge'}:
        raise DispatchError('exact current professional/knowledge route required')
    if route.get('target_department') != record.get('route', {}).get('target_department'):
        raise DispatchError('original frozen recipient changed')
    target = route['target_department']
    binding(root, target)
    # A result already actually received must not wake a reviewer a second time.
    return value, target, rc._received_delivery(root, value, route) is not None


class Store:
    """A transport outbox only. Original workflow/permission ledgers are untouched."""
    def __init__(self, root):
        self.root = root
        directory = root / STATE
        directory.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(directory / 'transport.sqlite3'))
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.execute('''CREATE TABLE IF NOT EXISTS wakeups (
            event_key TEXT PRIMARY KEY, identity_json TEXT NOT NULL,
            target TEXT NOT NULL, state TEXT NOT NULL, detail TEXT,
            turn_id TEXT, updated_at TEXT NOT NULL)''')
        if 'native_message_id' not in {r[1] for r in self.db.execute('PRAGMA table_info(wakeups)')}:
            self.db.execute('ALTER TABLE wakeups ADD COLUMN native_message_id TEXT')
        self.db.commit()

    def close(self):
        self.db.close()

    def put(self, value, target):
        event = key(value)
        row = self.db.execute('SELECT * FROM wakeups WHERE event_key=?', (event,)).fetchone()
        if row and row['target'] != target:
            raise DispatchError('existing event recipient is immutable; explicit transfer required')
        self.db.execute('INSERT OR IGNORE INTO wakeups(event_key,identity_json,target,state,detail,turn_id,updated_at) VALUES(?,?,?,?,?,?,?)',
                        (event, json.dumps(identity(value), sort_keys=True), target, 'pending', '', None, now()))
        self.db.commit()
        return event

    def set(self, event, state, detail='', turn_id=None, native_message_id=None):
        self.db.execute('UPDATE wakeups SET state=?,detail=?,turn_id=COALESCE(?,turn_id),native_message_id=COALESCE(?,native_message_id),updated_at=? WHERE event_key=?',
                        (state, detail, turn_id, native_message_id, now(), event))
        self.db.commit()

    def rows(self):
        return [dict(v) for v in self.db.execute('SELECT * FROM wakeups ORDER BY updated_at,event_key')]


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def background_status(root):
    pid_path = root / STATE / 'service.pid'
    if not pid_path.exists():
        return {'running': False, 'login_autostart_enabled': False}
    pid = int(pid_path.read_text().strip())
    observed = subprocess.run(['/bin/ps', '-p', str(pid), '-o', 'pid=,ppid=,etime=,command='],
                              capture_output=True, text=True)
    running = (observed.returncode == 0
               and str(root / 'tools/department_event_dispatcher.py') + ' serve-queue' in observed.stdout)
    return {'running': running, 'pid': pid, 'actual_process': observed.stdout.strip(),
            'login_autostart_enabled': False}


def background_start(root):
    native_queue_capability(root)
    status = background_status(root)
    if status['running']:
        return {**status, 'duplicate_start_ignored': True}
    directory = root / STATE
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / 'app-background.stdout.jsonl').open('a') as out, \
            (directory / 'app-background.stderr.log').open('a') as err:
        child = subprocess.Popen([sys.executable, '-u', '-B', str(root / 'tools/department_event_dispatcher.py'), 'serve-queue'],
                                 cwd=root, stdin=subprocess.DEVNULL, stdout=out, stderr=err,
                                 start_new_session=True, close_fds=True)
    (directory / 'service.pid').write_text(str(child.pid) + '\n')
    return {'started_pid': child.pid, 'readback_required': True, 'login_autostart_enabled': False}


def background_stop(root):
    status = background_status(root)
    if status['running']:
        os.kill(status['pid'], signal.SIGTERM)
    return {**status, 'stop_requested': status['running'], 'unrelated_processes_signalled': False}


@contextmanager
def exclusive_service(root):
    directory = root / STATE
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / 'service.lock').open('a') as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise DispatchError('one dispatcher already owns this project') from exc
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


class RPC:
    """JSON-RPC connection; the transport determines permitted methods."""
    def __init__(self, command, notify=lambda: None):
        self.proc = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.DEVNULL, text=True, bufsize=1)
        self.pending = {}
        self.events = queue.Queue()
        self.counter = 0
        self.notify = notify
        self.closed = False
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()
        try:
            self.call('initialize', {'clientInfo': {'name': 'flashcast_result_dispatcher',
                      'title': 'FLASH CAST result dispatcher', 'version': '0.1.0'}})
            self.send({'method': 'initialized', 'params': {}})
        except Exception:
            self.close()
            raise

    def send(self, value):
        self.proc.stdin.write(json.dumps(value) + '\n')
        self.proc.stdin.flush()

    def _read(self):
        try:
            for line in self.proc.stdout:
                value = json.loads(line)
                if 'id' in value and ('result' in value or 'error' in value):
                    waiting = self.pending.get(value['id'])
                    if waiting is not None:
                        waiting.put(value)
                elif 'id' in value:
                    # No implicit approval, user-input answer or dynamic tool execution.
                    self.send({'id': value['id'], 'error': {'code': -32000,
                               'message': 'dispatcher cannot approve tools or answer user questions'}})
                else:
                    self.events.put(value)
                    self.notify()
        finally:
            self.closed = True
            for waiting in list(self.pending.values()):
                waiting.put({'error': {'message': 'shared transport disconnected'}})
            self.notify()

    def call(self, method, params, timeout=20):
        if self.closed:
            raise DispatchError('shared transport is closed')
        self.counter += 1
        number = self.counter
        waiting = queue.Queue()
        self.pending[number] = waiting
        try:
            self.send({'id': number, 'method': method, 'params': params})
            value = waiting.get(timeout=timeout)
            if 'error' in value:
                raise DispatchError(str(value['error'].get('message', 'RPC error')))
            return value['result']
        except queue.Empty as exc:
            raise DispatchError('RPC response uncertain: ' + method) from exc
        finally:
            self.pending.pop(number, None)

    def close(self):
        self.proc.terminate()
        try:
            self.proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait()


class SharedTransport:
    def __init__(self, root, rpc):
        self.root, self.rpc = root, rpc
        self.verified = False

    def verify(self, live_proof):
        """An independently observed ACTIVE sentinel detects history-only servers."""
        observed = dt.datetime.fromisoformat(live_proof['observed_at'].replace('Z', '+00:00'))
        if not 0 <= (dt.datetime.now(dt.timezone.utc) - observed).total_seconds() <= 120:
            raise DispatchError('fresh desktop native observation required')
        sentinel = binding(self.root, live_proof['role'])
        if live_proof.get('thread_id') != sentinel['task_id'] or live_proof.get('status') != 'active':
            raise DispatchError('independent exact ACTIVE desktop sentinel required')
        thread = self.rpc.call('thread/read', {'threadId': sentinel['task_id'], 'includeTurns': False})['thread']
        self._identity(thread, sentinel)
        if thread.get('status', {}).get('type') != 'active':
            raise DispatchError('server does not share the observed active desktop runtime; refuse writes')
        self.verified = True

    @staticmethod
    def _identity(thread, expected):
        if (thread.get('id') != expected['task_id'] or thread.get('name') != expected['title']
                or Path(thread.get('cwd', '')).resolve() != Path(expected['cwd']).resolve()):
            raise DispatchError('fixed recipient thread/title/cwd differs')

    def _thread(self, role):
        if not self.verified:
            raise DispatchError('shared live transport has not been verified')
        expected = binding(self.root, role)
        thread = self.rpc.call('thread/read', {'threadId': expected['task_id'], 'includeTurns': False})['thread']
        self._identity(thread, expected)
        return thread, expected

    def status(self, role):
        thread, expected = self._thread(role)
        state = thread.get('status', {}).get('type')
        if state == 'notLoaded':
            turns = self.rpc.call('thread/turns/list', {'threadId': expected['task_id'], 'limit': 1,
                                  'sortDirection': 'desc', 'itemsView': 'notLoaded'})['data']
            if not turns or turns[0].get('status') not in {'completed', 'failed', 'interrupted'}:
                return 'unknown'
            return 'idle'
        return state

    def recover(self, role, event, expected_identity):
        """Never replay an uncertain turn/start. Require exact persisted output."""
        _, expected = self._thread(role)
        page = self.rpc.call('thread/turns/list', {'threadId': expected['task_id'], 'limit': 20,
                             'sortDirection': 'desc', 'itemsView': 'full'})
        for turn in page.get('data', []):
            for item in turn.get('items', []):
                if (item.get('type') != 'functionCallOutput' or item.get('namespace') != 'flashcast_dispatcher'
                        or item.get('name') != 'frozen_result_ready'):
                    continue
                raw = item.get('output')
                if isinstance(raw, str):
                    try:
                        value = json.loads(raw)
                    except ValueError:
                        continue
                    if (value.get('schema') == 'flashcast-result-wakeup/v1'
                            and value.get('event_key') == event and value.get('receiver') == role
                            and value.get('identity') == identity(expected_identity)
                            and value.get('permission_granted') is False):
                        return turn['id']
        return None  # Absence from a bounded page is NOT proof that sending failed.

    def wake(self, role, event, value):
        # Caller journaled 'sending' first. Second status check narrows the race;
        # the shared server queues toolOutput if a normal turn became active.
        if self.status(role) != 'idle':
            return None
        _, expected = self._thread(role)
        result = self.rpc.call('thread/resume', {'threadId': expected['task_id'], 'excludeTurns': True})
        self._identity(result['thread'], expected)
        payload = {'schema': 'flashcast-result-wakeup/v1', 'event_key': event,
                   'identity': identity(value), 'receiver': role,
                   'purpose': 'receive original frozen result and continue already-authorized work',
                   'instructions': '本消息仅是原结果到达通知，不是老板新授权或验收结论。恢复原任务，使用现有唯一认领/收取入口；已收取则不重复验收。按原授权落实下一动作。',
                   'permission_granted': False, 'result_received_claimed': False}
        result = self.rpc.call('turn/start', {'threadId': expected['task_id'], 'input': [],
                              'toolOutput': {'name': 'frozen_result_ready', 'namespace': 'flashcast_dispatcher',
                                             'output': json.dumps(payload, ensure_ascii=False)}})
        turn = result.get('turn', {})
        if not turn.get('id'):
            raise DispatchError('missing actual new turn acknowledgement')
        return turn['id']


class Dispatcher:
    def __init__(self, store, transport=None):
        self.store, self.transport = store, transport

    def pump(self, valid_events=None):
        for row in self.store.rows():
            if row['state'] in {'wake_acknowledged', 'native_queue_accepted', 'resolved_by_original_intake'}:
                continue
            if valid_events is not None and row['event_key'] not in valid_events:
                # A deleted/changed/invalid source cannot awaken a stale stored
                # event; uncertain actual effects still require readback first.
                if row['state'] not in {'sending', 'uncertain'}:
                    self.store.set(row['event_key'], 'waiting_valid_source', 'original source must revalidate')
                    continue
            if self.transport is None:
                self.store.set(row['event_key'], row['state'] if row['state'] in {'sending', 'uncertain'}
                               else 'waiting_transport', 'verified shared native transport required')
                continue
            if getattr(self.transport, 'queues_busy_recipient', False):
                if row['state'] in {'sending', 'uncertain'}:
                    # Queue acceptance is not a turn id. Recovery reads exact
                    # persisted message bytes; it never blindly queues again.
                    turn = self.transport.recover(row['target'], row['event_key'], json.loads(row['identity_json']))
                    self.store.set(row['event_key'], 'wake_acknowledged' if turn else 'uncertain',
                                   'exact persisted queue input recovered' if turn else 'queue effect uncertain; no blind replay', turn)
                    continue
                value = json.loads(row['identity_json'])
                try:
                    prepared = self.transport.prepare(row['target'], row['event_key'], value)
                except Exception as exc:
                    self.store.set(row['event_key'], 'waiting_policy_or_source', str(exc))
                    continue
                self.store.set(row['event_key'], 'sending')
                try:
                    receipt = self.transport.enqueue(prepared)
                except Exception as exc:
                    self.store.set(row['event_key'], 'uncertain', str(exc))
                else:
                    self.store.set(row['event_key'], 'native_queue_accepted',
                                   'official queue acknowledged; recipient intake not claimed',
                                   native_message_id=receipt['message_id'])
                continue
            if row['state'] in {'sending', 'uncertain'}:
                turn = self.transport.recover(row['target'], row['event_key'], json.loads(row['identity_json']))
                self.store.set(row['event_key'], 'wake_acknowledged' if turn else 'uncertain',
                               'recovered exact native effect' if turn else 'read exact native effect; no blind resend', turn)
                continue
            state = self.transport.status(row['target'])
            if state != 'idle':
                self.store.set(row['event_key'], 'waiting_recipient', 'actual recipient state: ' + str(state))
                continue
            # Commit intent before a side effect. Crash recovery never blindly resends.
            self.store.set(row['event_key'], 'sending')
            try:
                turn = self.transport.wake(row['target'], row['event_key'], json.loads(row['identity_json']))
            except Exception as exc:
                self.store.set(row['event_key'], 'uncertain', type(exc).__name__ + ': ' + str(exc))
            else:
                self.store.set(row['event_key'], 'wake_acknowledged' if turn else 'waiting_recipient',
                               'native wake acknowledged; acceptance not claimed' if turn else 'became busy before send', turn)


def native_queue_capability(root):
    """Require the actual successful installed CLI/recipient pilot, not a flag."""
    config = json.loads((root / CONFIG).read_text())
    capability = config.get('native_queue_transport', {})
    if capability.get('schema') != 'official-codex-queue/v1':
        raise DispatchError('official queue capability is not admitted')
    cli = capability.get('cli')
    if cli != '/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex' or not Path(cli).is_file():
        raise DispatchError('exact installed application CLI required')
    sent = json.loads(inside(root, capability['actual_send_proof']).read_text())
    received = json.loads(inside(root, capability['actual_receiver_proof']).read_text())
    completed = json.loads(inside(root, capability['actual_completed_turn_proof']).read_text())
    polls = []
    for part in completed.get('content', []):
        if part.get('type') == 'text':
            polls.extend(json.loads(part['text']).get('polls', []))
    actual_completion = any(
        row.get('thread', {}).get('id') == received.get('fixed_thread_id')
        and row.get('latestTurn', {}).get('id') == received.get('actual_turn_id')
        and row.get('latestTurn', {}).get('status') == 'completed'
        and row.get('latestTurn', {}).get('error') is None
        and row.get('latestAssistantMessage', {}).get('phase') == 'final_answer'
        and ('FLASHCAST_QUEUE_PROBE_OK ' + received.get('task_id', '') + ' '
             + received.get('actual_sha256', '')) == row.get('latestAssistantMessage', {}).get('text')
        for row in polls)
    if (sent.get('tool') != 'official_codex_queue' or sent.get('exit_code') != 0
            or not re.fullmatch(r'Queued message [0-9a-f-]{36} for thread [0-9a-f-]{36}\.\s*', sent.get('stdout', ''))
            or received.get('fixed_thread_id') != sent.get('target_thread_id')
            or received.get('actual_sha256') != received.get('expected_sha256')
            or received.get('sha256_matches') is not True or not received.get('actual_turn_id')
            or not actual_completion):
        raise DispatchError('actual native queue send and original recipient proof required')
    return cli


class OfficialQueueTransport:
    """Use the desktop's supported queue command, never a second live runtime.

    The independent RPC is used ONLY to read canonical persisted identities and
    recover exact message effects. Its busy/idle status is never used.
    """
    queues_busy_recipient = True

    def __init__(self, root, history):
        self.root, self.history = root, history
        self.cli = native_queue_capability(root)

    def message(self, role, event, value):
        return ('【后台结果接续通知；不是老板新增授权】\n'
                + 'FLASHCAST_NATIVE_QUEUE_EVENT ' + event + '\n'
                + json.dumps({'identity': identity(value), 'receiver': role}, ensure_ascii=False, sort_keys=True)
                + '\n沿原任务恢复：从现有结果队列唯一认领并实际收取准确成果，只验收本批变化，不重复原内容PASS。'
                  '按既有授权落实下一动作或准确具名等待；不把收到消息当验收、保存或发布。'
                  '完整批次处理后汇报。若来源或准入失败，保存准确拒绝和下一负责人，不修改历史原件；其他独立已授权工作继续。'
                  '保留原未完任务位置，本通知不授新账号、费用或生产权限。')

    def _read(self, role):
        expected = binding(self.root, role)
        raw = self.history.call('thread/read', {'threadId': expected['task_id'], 'includeTurns': False})
        thread = raw['thread']
        SharedTransport._identity(thread, expected)
        turns = self.history.call('thread/turns/list', {'threadId': expected['task_id'], 'limit': 1,
                                  'sortDirection': 'desc', 'itemsView': 'notLoaded'})['data']
        if not turns:
            raise DispatchError('original fixed recipient history required')
        # Explicit, lossless field-name normalization; original RPC fields kept.
        return {'thread': {**thread, 'title': thread['name']}, 'turns': turns,
                'source_transport': 'official_app_server_readonly_history',
                'normalization': {'thread.title': 'original thread.name'}, 'raw_thread_response': raw}

    def prepare(self, role, event, value):
        import workflow_control as workflow
        import goal_source_recovery as recovery
        import result_coordination as rc
        route=rc.result_lane(self.root,value)
        if role!=route.get('target_department') or route.get('lane') not in {'professional_acceptance','HQ_knowledge'}:
            raise DispatchError('original assigned recipient required')
        directory = self.root / STATE / 'prepared' / event
        directory.mkdir(parents=True, exist_ok=True)
        message = self.message(role, event, value)
        path = directory / 'message.txt'
        if path.exists() and path.read_text() != message:
            raise DispatchError('frozen native queue payload changed')
        path.write_text(message)
        canonical={}
        for participant in {value['sender_department'],role}:
            native_path=directory/('actual-canonical-'+participant+'.json')
            native_path.write_text(json.dumps(self._read(participant),ensure_ascii=False,indent=2)+'\n')
            canonical[participant]=workflow.file_digest(self.root,str(native_path.relative_to(self.root)))
        native_path=directory/'actual-queue-identities.json'
        native_path.write_text(json.dumps({'schema':'official-native-queue-identities/v1',
            'identity':identity(value),'target_thread_id':binding(self.root,role)['task_id'],
            'observed_at':now(),'canonical_sources':canonical},ensure_ascii=False,indent=2)+'\n')
        expected = binding(self.root, role)
        request = {'task_id': value['task_id'], 'sender_department': value['sender_department'],
                   'result_notification':identity(value),'notification_request_id':'native-queue:'+event,
                   'source_project_id': binding(self.root,value['sender_department'])['project_id'],
                   'target_project_id': expected['project_id'], 'target_department': role,
                   'target_thread_id': expected['task_id'], 'target_thread_title': expected['title'],
                   'target_cwd': expected['cwd'], 'target_sidebar_section_id': expected['sidebar_section_id'],
                   'payload': workflow.file_digest(self.root, str(path.relative_to(self.root))),
                   'payload_sha256': hashlib.sha256(message.encode()).hexdigest(),
                   'actual_target_state': workflow.file_digest(self.root, str(native_path.relative_to(self.root))),
                   'authorization_changes': [], 'delivery_mode': 'official_native_queue'}
        result = recovery.prepare_message(self.root, request)
        (directory / 'actual-prepare-request.json').write_text(json.dumps(request, ensure_ascii=False, indent=2) + '\n')
        (directory / 'actual-prepare-result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
        if result.get('status') != 'ready_to_queue':
            raise DispatchError('exact native queue preparation refused: ' + json.dumps(result, ensure_ascii=False))
        return {'thread_id': expected['task_id'], 'message': message, 'directory': directory, 'identity': identity(value),
                'payload_sha256': request['payload_sha256'], 'policy_decision_id': result['policy_decision']['decision_id']}

    def enqueue(self, prepared):
        directory = prepared['directory']
        before = {'started_at': now(), 'thread_id': prepared['thread_id'],
                  'payload_sha256': prepared['payload_sha256'], 'policy_decision_id': prepared['policy_decision_id'],
                  'transport': 'official_codex_queue', 'intake_claimed': False}
        value = prepared.get('identity')
        if value is not None:
            self._reserve_original(value, prepared, before)
        (directory / 'native-queue-intent.json').write_text(json.dumps(before, indent=2) + '\n')
        try:
            result = subprocess.run([self.cli, 'queue', '--thread', prepared['thread_id'], '--message', prepared['message']],
                                    cwd=self.root, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=30)
        except Exception:
            if value is not None:
                self._original_queue_state(value, prepared, 'uncertain')
            raise
        receipt = {**before, 'finished_at': now(), 'exit_code': result.returncode,
                   'stdout': result.stdout, 'stderr': result.stderr}
        (directory / 'native-queue-result.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
        match = re.fullmatch(r'Queued message ([0-9a-f-]{36}) for thread ([0-9a-f-]{36})\.\s*', result.stdout)
        if result.returncode or not match or match[2] != prepared['thread_id']:
            if value is not None:
                self._original_queue_state(value, prepared, 'uncertain')
            raise DispatchError('native queue effect uncertain; inspect original receipt before recovery')
        if value is not None:
            self._original_queue_state(value, prepared, 'accepted', match[1])
        return {'message_id': match[1]}

    def _reserve_original(self, value, prepared, before):
        import result_coordination as rc
        import workflow_control as workflow
        with rc.coordination_lock(self.root):
            record = workflow.read_json(rc._notification_path(self.root, value))
            route = rc.result_lane(self.root, value)
            if record.get('delivered') or rc._received_delivery(self.root, value, route):
                raise DispatchError('original notice already sent or actually received; no new native send')
            own_preparation=(record.get('state')=='prepared' and record.get('delivery_mode')=='official_native_queue'
                and record.get('payload',{}).get('sha256')==prepared['payload_sha256'])
            if (record.get('native_queue_transport') or record.get('call_started_at')
                    or record.get('attempts') or record.get('state') in {'sending','sent'}
                    or record.get('state')=='prepared' and not own_preparation):
                raise DispatchError('another original send owns this notice; exact effect recovery required')
            record['native_queue_transport'] = {**before, 'state': 'sending', 'event_key': key(value),
                'payload': workflow.file_digest(self.root, str((prepared['directory'] / 'message.txt').relative_to(self.root))),
                'native_queue_accepted_is_delivery': False}
            workflow.atomic_write_json(rc._notification_path(self.root, value), record)

    def _original_queue_state(self, value, prepared, state, message_id=None):
        import result_coordination as rc
        import workflow_control as workflow
        with rc.coordination_lock(self.root):
            path = rc._notification_path(self.root, value)
            record = workflow.read_json(path)
            current = record.get('native_queue_transport', {})
            if current.get('event_key') != key(value) or current.get('payload_sha256') != prepared['payload_sha256']:
                raise DispatchError('original reserved notification identity changed')
            current.update(state=state, updated_at=now())
            if message_id:
                current['native_message_id'] = message_id
            record['native_queue_transport'] = current
            workflow.atomic_write_json(path, record)

    def recover(self, role, event, value):
        expected = binding(self.root, role)
        page = self.history.call('thread/turns/list', {'threadId': expected['task_id'], 'limit': 20,
                                 'sortDirection': 'desc', 'itemsView': 'full'})
        wanted = self.message(role, event, value)
        for turn in page.get('data', []):
            for item in turn.get('items', []):
                if item.get('type') == 'userMessage':
                    texts = [part.get('text', '') for part in item.get('content', []) if part.get('type') == 'text']
                    if '\n'.join(texts) == wanted or ''.join(texts) == wanted:
                        return turn['id']
        return None


def load_pilot(root):
    config = json.loads((root / CONFIG).read_text())
    if config.get('schema') != 'flashcast-event-dispatcher-pilot/v1':
        raise DispatchError('explicit pilot configuration required')
    allowed = {key(v): identity(v) for v in config.get('pilot_results', [])}
    if not allowed:
        raise DispatchError('one or more exact enrolled pilot identities required')
    command = config.get('shared_proxy_command', [])
    if (len(command) not in {3, 5} or command[1:3] != ['app-server', 'proxy']
            or not Path(command[0]).is_absolute()
            or len(command) == 5 and (command[3] != '--sock' or not Path(command[4]).is_absolute())):
        raise DispatchError('official shared proxy command required; standalone server refused')
    return config, allowed


def admitted_result(root, record, allowed):
    """Recover only named old results; admit new goal results from native facts."""
    value = record.get('identity')
    if key(value) in allowed:
        return True
    config = json.loads((root / CONFIG).read_text())
    since = config.get('admit_new_results_since',config.get('admit_new_goal_results_since'))
    if not since:
        return False
    import workflow_control as workflow
    import result_coordination as rc
    cutoff = workflow._parse_observed_at(since)
    queued_at = workflow._parse_observed_at(record.get('queued_at'))
    if cutoff is None or queued_at is None or queued_at < cutoff:
        return False
    # Do not trust an editable transport timestamp as native source admission.
    rows = [row for row in workflow._result_handoff_rows(root, value['task_id'])
            if row.get('event') == 'notification_queued'
            and workflow._result_identity(row) == tuple(value[k] for k in IDENTITY[1:])]
    if len(rows) != 1:
        raise DispatchError('one original native queued result required for new event')
    native_at = workflow._parse_observed_at(rows[0].get('created_at'))
    if native_at is None or native_at < cutoff:
        return False
    route=rc.result_lane(root,value)
    if route.get('lane') not in {'professional_acceptance','HQ_knowledge'}:
        raise DispatchError('original authenticated goal or admitted daily result route required')
    binding(root, value['sender_department'])
    return True


def ingest(root, store, allowed):
    import workflow_control as workflow
    valid, errors = set(), []
    for path in sorted((root / 'logs/result-notifications').glob('*.json')):
        if path.is_symlink():
            continue
        try:
            record = json.loads(path.read_text())
        except (ValueError, OSError):
            continue  # unrelated corrupt records cannot disable enrolled work
        value = record.get('identity')
        if not isinstance(value, dict) or any(not isinstance(value.get(k), str) or not value[k] for k in IDENTITY):
            continue
        if record.get('delivered'):
            continue
        try:
            if not admitted_result(root, record, allowed):
                continue
            value, target, received = validate_notification(root, record)
        except (workflow.WorkflowError, ValueError, OSError, KeyError, TypeError, AttributeError) as exc:
            errors.append({'event_key': key(value), 'file': str(path.relative_to(root)),
                           'reason': str(exc), 'blocks_other_events': False})
            continue
        event = store.put(value, target)
        if received:
            store.set(event, 'resolved_by_original_intake', 'original responsible intake already committed')
        valid.add(event)
    return valid, errors


class VnodeEvents:
    """macOS kqueue: block on file/native events, never a timed chat poll."""
    def __init__(self, paths):
        if not hasattr(select, 'kqueue'):
            raise DispatchError('kqueue is required on this local macOS host')
        self.queue = select.kqueue()
        self.fds = {}
        self.paths = [Path(v) for v in paths]
        self.refresh()

    def refresh(self):
        current = set(self.paths)
        for directory in self.paths:
            if directory.is_dir():
                for pattern in ('*.json', '*.jsonl'):
                    current.update(p for p in directory.glob(pattern) if not p.is_symlink())
        for path, fd in list(self.fds.items()):
            if not path.exists() or os.fstat(fd).st_ino != path.stat().st_ino:
                os.close(fd)
                del self.fds[path]
        for path in current:
            if path not in self.fds and path.exists() and not path.is_symlink():
                fd = os.open(path, os.O_RDONLY)
                self.fds[path] = fd
                self.queue.control([select.kevent(fd, filter=select.KQ_FILTER_VNODE,
                    flags=select.KQ_EV_ADD | select.KQ_EV_CLEAR,
                    fflags=select.KQ_NOTE_WRITE | select.KQ_NOTE_EXTEND | select.KQ_NOTE_RENAME | select.KQ_NOTE_DELETE)], 0, 0)

    def add_readable(self, fd):
        self.queue.control([select.kevent(fd, filter=select.KQ_FILTER_READ,
                            flags=select.KQ_EV_ADD | select.KQ_EV_CLEAR)], 0, 0)

    def wait(self, timeout=None):
        rows = self.queue.control([], 32, timeout)
        if rows:
            self.refresh()
        return bool(rows)

    def close(self):
        for fd in self.fds.values():
            os.close(fd)
        self.queue.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['stage-once', 'observe', 'serve', 'queue-once', 'serve-queue', 'status', 'probe',
                                          'start-background', 'background-status', 'stop-background'])
    parser.add_argument('--desktop-proof', help='project-relative fresh native ACTIVE observation')
    args = parser.parse_args()
    config, allowed = load_pilot(ROOT)
    if args.command in {'start-background', 'background-status', 'stop-background'}:
        handler = {'start-background': background_start, 'background-status': background_status,
                   'stop-background': background_stop}[args.command]
        print(json.dumps(handler(ROOT), ensure_ascii=False))
        return 0
    if args.command == 'probe':
        rpc = None
        try:
            if not args.desktop_proof:
                raise DispatchError('fresh independent desktop proof required')
            proof = json.loads(inside(ROOT, args.desktop_proof).read_text())
            rpc = RPC(config['shared_proxy_command'])
            SharedTransport(ROOT, rpc).verify(proof)
            print(json.dumps({'shared_transport_verified': True, 'writes_performed': False}))
            return 0
        except Exception as exc:
            print(json.dumps({'shared_transport_verified': False, 'reason': str(exc),
                              'writes_performed': False, 'no_standalone_fallback': True}))
            return 3
        finally:
            if rpc:
                rpc.close()
    store = Store(ROOT)
    try:
        if args.command == 'status':
            print(json.dumps({'transport_only': True, 'wakeups': store.rows(), 'publication_claimed': False}, ensure_ascii=False))
            return 0
        with exclusive_service(ROOT):
            watcher = VnodeEvents([ROOT / 'logs/result-notifications', ROOT / 'logs/result-handoffs',
                                   ROOT / CONFIG, ROOT / 'data/department-registry.json']) \
                if args.command in {'observe', 'serve', 'serve-queue'} else None
            rpc, transport, signal_read, signal_write = None, None, None, None
            try:
                if args.command in {'queue-once', 'serve-queue'}:
                    cli = native_queue_capability(ROOT)
                    # This connection reads persisted identities only. No resume,
                    # turn/start or false busy/idle inference is permitted here.
                    rpc = RPC([cli, 'app-server', '--listen', 'stdio://'])
                    transport = OfficialQueueTransport(ROOT, rpc)
                if args.command == 'serve':
                    if not args.desktop_proof:
                        raise DispatchError('live service requires fresh independent desktop proof')
                    signal_read, signal_write = socket.socketpair()
                    signal_read.setblocking(False)
                    signal_write.setblocking(False)
                    def signal_event():
                        try:
                            signal_write.send(b'E')
                        except (BlockingIOError, OSError):
                            pass
                    rpc = RPC(config['shared_proxy_command'], notify=signal_event)
                    transport = SharedTransport(ROOT, rpc)
                    transport.verify(json.loads(inside(ROOT, args.desktop_proof).read_text()))
                    watcher.add_readable(signal_read.fileno())
                    # Subscribe before checking the queue: completion between scan
                    # and wait remains in the socket/event queue, not a lost edge.
                    targets = set()
                    for result in allowed.values():
                        import result_coordination as rc
                        targets.add(rc.result_lane(ROOT, result)['target_department'])
                    for role in targets:
                        expected = binding(ROOT, role)
                        result = rpc.call('thread/resume', {'threadId': expected['task_id'], 'excludeTurns': True})
                        transport._identity(result['thread'], expected)
                while True:
                    if rpc and rpc.closed:
                        raise DispatchError('shared connection lost; retained outbox requires reconnection')
                    config, allowed = load_pilot(ROOT)
                    valid, errors = ingest(ROOT, store, allowed)
                    Dispatcher(store, transport).pump(valid_events=valid)
                    print(json.dumps({'observed_at': now(), 'enrolled_results_found': len(valid),
                                      'isolated_source_errors': errors,
                                      'mode': 'official_native_queue' if getattr(transport, 'queues_busy_recipient', False)
                                              else 'verified_shared_transport' if transport else 'observer_only',
                                      'wakeups': [{k: row[k] for k in ['event_key', 'target', 'state', 'turn_id']}
                                                  for row in store.rows()]}), flush=True)
                    if watcher is None:
                        break
                    watcher.wait()  # indefinite event wait, not periodic polling
                    if signal_read:
                        try:
                            while signal_read.recv(4096):
                                pass
                        except BlockingIOError:
                            pass
                        while not rpc.events.empty():
                            rpc.events.get_nowait()
            finally:
                if rpc:
                    rpc.close()
                for sock in [signal_read, signal_write]:
                    if sock:
                        sock.close()
                if watcher:
                    watcher.close()
        return 0
    finally:
        store.close()


if __name__ == '__main__':
    raise SystemExit(main())
